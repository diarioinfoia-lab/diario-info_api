#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agregador de Noticias - DiarioInfo
Filtra noticias de las ultimas 2 horas. v10: 20 fuentes (El Liberal 4, Panorama 4, interior SDE 6, nacionales 6).
Optimizaciones v10: sesion HTTP con reintentos, scraping en paralelo (por fuente
y por articulo), rate-limit por dominio, credenciales de Mongo por variable de
entorno, y manejo de errores aislado por fuente.
v11: deteccion de fecha del articulo mas robusta (JSON-LD + meta tags + parseo
flexible con dateutil, ademas del selector CSS por fuente) y, para el caso en
que ninguna de esas fuentes permite determinar la fecha, un fallback basado en
un historial largo de URLs (HISTORIAL_URL_DIAS) en vez de aceptar la nota
siempre por default (eso dejaba pasar notas viejas "pescadas" de widgets de
mas leidas/relacionadas en sitios sin fecha parseable).
"""

import requests
import json
import time
import os
import re
import unicodedata
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import parser as dateutil_parser

# ── pymongo ──────────────────────────────────────────────────────────────────
try:
    from pymongo import MongoClient
    from bson import ObjectId
    PYMONGO_OK = True
except ImportError:
    PYMONGO_OK = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ── Configuracion ─────────────────────────────────────────────────────────────
# La URI de Mongo ahora se toma SIEMPRE de una variable de entorno: nunca debe
# quedar hardcodeada en el codigo (el repo es publico). Ver README para como
# configurarla (export MONGO_URI="...").
MONGO_URI        = os.environ.get("MONGO_URI", "")
MONGO_DB         = "diarioinfo-db"
MONGO_COLLECTION = "articles"
MONGO_FILES_COL  = "files"

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
VERCEL_REWRITE_URL  = "https://diario-info-api.vercel.app/rewrite"

HORAS_MAX = 1.5  # Solo noticias de las ultimas N horas

# ── Concurrencia y rate-limiting ──────────────────────────────────────────────
MAX_WORKERS_FUENTES   = 6    # fuentes cuyo listado se trae en paralelo
MAX_WORKERS_ARTICULOS = 4    # articulos de una misma fuente procesados en paralelo
DOMAIN_MIN_INTERVAL   = 1.5  # segundos minimos entre requests al mismo dominio
REQUEST_TIMEOUT       = 15

FUENTES = [
    # ── SDE: El Liberal ──────────────────────────────────────────────────────────
    {
        "nombre": "El Liberal Policiales",
        "url": "https://www.elliberal.com.ar/policiales/",
        "selector_lista": "a[href*='/nota/']",
        "selector_titulo": "h1.nota__title, h1.article__title, h1",
        "selector_cuerpo": "div.nota__body p, div.article__body p, article p",
        "selector_imagen": "div.nota__image img, div.article__image img, figure img, article img",
        "selector_fecha": "time, span.fecha, .nota__date, .article__date",
        "categoria": "policiales",
        "credito": "El Liberal",
        "es_sde": True
    },
    {
        "nombre": "El Liberal Politica",
        "url": "https://www.elliberal.com.ar/politica/",
        "selector_lista": "a[href*='/nota/']",
        "selector_titulo": "h1.nota__title, h1.article__title, h1",
        "selector_cuerpo": "div.nota__body p, div.article__body p, article p",
        "selector_imagen": "div.nota__image img, div.article__image img, figure img, article img",
        "selector_fecha": "time, span.fecha, .nota__date, .article__date",
        "categoria": "politica",
        "credito": "El Liberal",
        "es_sde": True
    },
    {
        "nombre": "El Liberal Deportes",
        "url": "https://www.elliberal.com.ar/Deportivo",
        "selector_lista": "a[href*='/nota/']",
        "selector_titulo": "h1.nota__title, h1.article__title, h1",
        "selector_cuerpo": "div.nota__body p, div.article__body p, article p",
        "selector_imagen": "div.nota__image img, div.article__image img, figure img, article img",
        "selector_fecha": "time, span.fecha, .nota__date, .article__date",
        "categoria": "deportes",
        "credito": "El Liberal",
        "es_sde": True
    },
    # ── SDE: Diario Panorama ─────────────────────────────────────────────────────
    {
        "nombre": "Diario Panorama Policiales",
        "url": "https://www.diariopanorama.com/secciones/14/policiales",
        "selector_lista": "h2 a, h3 a, .news-title a, a[href*='/noticia/']",
        "selector_titulo": "h1.article-title, h1.entry-title, h1",
        "selector_cuerpo": "div.article-body p, div.entry-content p, article p",
        "selector_imagen": "div.article-image img, div.featured-image img, figure img, article img",
        "selector_fecha": "time, .article-date, .entry-date, span.date",
        "categoria": "policiales",
        "credito": "Diario Panorama",
        "es_sde": True
    },
    {
        "nombre": "Diario Panorama Politica",
        "url": "https://www.diariopanorama.com/secciones/16/pais",
        "selector_lista": "h2 a, h3 a, .news-title a, a[href*='/noticia/']",
        "selector_titulo": "h1.article-title, h1.entry-title, h1",
        "selector_cuerpo": "div.article-body p, div.entry-content p, article p",
        "selector_imagen": "div.article-image img, div.featured-image img, figure img, article img",
        "selector_fecha": "time, .article-date, .entry-date, span.date",
        "categoria": "politica",
        "credito": "Diario Panorama",
        "es_sde": True
    },
    {
        "nombre": "Diario Panorama Deportes",
        "url": "https://www.diariopanorama.com/secciones/48/somos-deporte",
        "selector_lista": "h2 a, h3 a, .news-title a, a[href*='/noticia/']",
        "selector_titulo": "h1.article-title, h1.entry-title, h1",
        "selector_cuerpo": "div.article-body p, div.entry-content p, article p",
        "selector_imagen": "div.article-image img, div.featured-image img, figure img, article img",
        "selector_fecha": "time, .article-date, .entry-date, span.date",
        "categoria": "deportes",
        "credito": "Diario Panorama",
        "es_sde": True
    },
    {
        "nombre": "Diario Panorama Espectaculos",
        "url": "https://www.diariopanorama.com/secciones/18/espectaculos",
        "selector_lista": "h2 a, h3 a, .news-title a, a[href*='/noticia/']",
        "selector_titulo": "h1.article-title, h1.entry-title, h1",
        "selector_cuerpo": "div.article-body p, div.entry-content p, article p",
        "selector_imagen": "div.article-image img, div.featured-image img, figure img, article img",
        "selector_fecha": "time, .article-date, .entry-date, span.date",
        "categoria": "espectaculos",
        "credito": "Diario Panorama",
        "es_sde": True
    },
    # ── Interior SDE: Provincial ─────────────────────────────────────────────────
    {
        "nombre": "Nuevo Diario Web",
        "url": "https://www.nuevodiarioweb.com.ar/",
        "selector_lista": "a[href*='/noticia/']",
        "selector_titulo": "h1.title, h1.article-title, h1",
        "selector_cuerpo": "div.article-body p, div.content p, article p",
        "selector_imagen": "div.article-image img, figure img, article img",
        "selector_fecha": "time, span.date, .article-date",
        "categoria": "interior",
        "credito": "Nuevo Diario Web",
        "es_sde": True
    },
    {
        "nombre": "Info del Estero",
        "url": "https://infodelestero.com",
        "selector_lista": "h2 a, h3 a, article a, .entry-title a",
        "selector_titulo": "h1.entry-title, h1",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, .wp-post-image, article img",
        "selector_fecha": "time, .entry-date, span.fecha",
        "categoria": "interior",
        "credito": "Info del Estero",
        "es_sde": True
    },
    {
        "nombre": "385 Noticias",
        "url": "https://www.385.com.ar",
        "selector_lista": "h2 a, h3 a, article a, .entry-title a",
        "selector_titulo": "h1.entry-title, h1",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "385 Noticias",
        "es_sde": True
    },
    {
        "nombre": "Diario de Santiago",
        "url": "https://diariodesantiago.com",
        "selector_lista": "h2 a, h3 a, article a",
        "selector_titulo": "h1, h1.entry-title",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "Diario de Santiago",
        "es_sde": True
    },
    {
        "nombre": "Noticias del Estero",
        "url": "https://www.noticiasdelestero.com",
        "selector_lista": "h2 a, h3 a, article a",
        "selector_titulo": "h1, h1.entry-title",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "Noticias del Estero",
        "es_sde": True
    },
    # ── Interior SDE: La Banda ───────────────────────────────────────────────────
    {
        "nombre": "La Banda Diario",
        "url": "https://labandadiario.com",
        "selector_lista": "h2 a, h3 a, article a, .entry-title a",
        "selector_titulo": "h1.entry-title, h1",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, .wp-post-image, article img",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "La Banda Diario",
        "es_sde": True
    },
    # ── Interior SDE: Termas de Rio Hondo ────────────────────────────────────────
    {
        "nombre": "Termas Digital",
        "url": "https://termasdigital.com.ar",
        "selector_lista": "h2 a, h3 a, article a",
        "selector_titulo": "h1, h1.entry-title",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "Termas Digital",
        "es_sde": True
    },
    # ── Interior SDE: Sur provincial (Bandera, Frias, Quimili) ──────────────────
    {
        "nombre": "Sur Santiago",
        "url": "https://sursantiago.com.ar",
        "selector_lista": "h2 a, h3 a, article a",
        "selector_titulo": "h1, h1.entry-title",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "Sur Santiago",
        "es_sde": True
    },
    {
        "nombre": "Semanario Conciencia",
        "url": "https://www.semanarioconciencia.com/",
        "selector_lista": "h2 a, h3 a, .entry-title a, article a",
        "selector_titulo": "h1.entry-title, h1",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, .wp-post-image, article img",
        "selector_fecha": "time, .entry-date, span.fecha",
        "categoria": "interior",
        "credito": "Semanario Conciencia",
        "es_sde": True
    },
    {
        "nombre": "El Siglo SDE",
        "url": "https://www.elsigloweb.com/",
        "selector_lista": "h2 a, h3 a, article a, .entry-title a",
        "selector_titulo": "h1.entry-title, h1",
        "selector_cuerpo": "div.entry-content p, article p",
        "selector_imagen": "figure img, article img, .wp-post-image",
        "selector_fecha": "time, .entry-date",
        "categoria": "interior",
        "credito": "El Siglo",
        "es_sde": True
    },
    # ── Nacionales: solo Deportes y Judiciales ───────────────────────────────────
    {
        "nombre": "Ole Deportes",
        "url": "https://www.ole.com.ar/",
        "selector_lista": "h2 a, h3 a, article a",
        "selector_titulo": "h1, h1.title",
        "selector_cuerpo": "div.body-nota p, div.article-body p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, span.date",
        "categoria": "deportes",
        "credito": "Ole",
        "es_sde": False
    },
    {
        "nombre": "Infobae Judiciales",
        "url": "https://www.infobae.com/judiciales/",
        "selector_lista": "h2 a, h3 a, article a",
        "selector_titulo": "h1, h1.article-headline",
        "selector_cuerpo": "div.article-body p, article p",
        "selector_imagen": "figure img, article img",
        "selector_fecha": "time, span.date",
        "categoria": "judiciales",
        "credito": "Infobae",
        "es_sde": False
    }
]

# Colores de autor por categoria (campo diarioinfo)
AUTHOR_COLORS = {
    "policiales":  "#CC0000",   # rojo
    "judiciales":  "#6A0DAD",   # morado
    "politica":    "#003399",   # azul
    "deportes":    "#006600",   # verde
    "espectaculos":"#FF6600",   # naranja
    "interior":    "#8B4513",   # marron
    "sociedad":    "#555555",   # gris
    "economia":    "#555555"    # gris
}

# Color de prefijo "Redaccion" para fuentes SDE
AUTHOR_PREFIX_COLOR_SDE      = "#00AADD"   # celeste
AUTHOR_PREFIX_COLOR_NACIONAL = "#555555"   # gris

# Etiqueta codificada del autor segun origen y categoria
AUTHOR_CATEGORY_LABELS = {
    "policiales":   "Policiales",
    "judiciales":   "Judiciales",
    "politica":     "Política",
    "deportes":     "Deportes",
    "espectaculos": "Espectáculos",
    "interior":     "Interior",
    "sociedad":     "General",
    "economia":     "Economía"
}

def generar_autor_codificado(categoria_id, es_sde=False, paso_por_ia=True):
    """Genera el texto codificado del autor: Red-info SDE-Policiales / NAC-Deportes etc.
    Si la nota NO paso por la IA (fallback), se devuelve solo 'Red-info' como alarma visual."""
    if not paso_por_ia:
        return "Red-info"
    prefijo = "SDE" if es_sde else "NAC"
    etiqueta = AUTHOR_CATEGORY_LABELS.get(categoria_id, categoria_id.capitalize())
    return "Red-info " + prefijo + "-" + etiqueta

CATEGORIAS = {
    "policiales": "policiales",
    "espectaculos":"espectaculos",
    "judiciales": "judiciales",
    "deportes": "deportes",
    "politica": "politica",
    "sociedad": "sociedad",
    "interior": "interior",
    "economia": "economia"
}

# ── Deduplicacion persistente ────────────────────────────────────────────────
# Antes se guardaba un archivo local (urls_procesadas.json) que solo evitaba
# reprocesar la MISMA url, y la comparacion de titulos similares solo miraba
# lo publicado en la corrida actual (se perdia al terminar el script). Ahora
# ambas cosas se guardan en Mongo, en una coleccion propia con TTL, para que
# la deduplicacion funcione tambien ENTRE corridas de cron (ej: una fuente
# publica una nota y dos horas despues otra fuente cubre el mismo hecho).
MONGO_DEDUP_COL = "agregador_dedup"
VENTANA_DEDUP_HORAS = 8  # ventana de comparacion de titulos (> intervalo del cron, hoy 6h)

# Historial largo de URLs (misma coleccion agregador_dedup): se usa SOLO como
# señal de respaldo cuando un articulo no tiene fecha de publicacion
# determinable (ver es_reciente). Si la URL nunca aparecio en los ultimos
# HISTORIAL_URL_DIAS dias, se trata como probablemente nueva; si ya aparecio
# (aunque haya sido hace semanas, tipico de un link reflotado desde un widget
# de "mas leidas"), se descarta en vez de aceptarla a ciegas. El indice TTL de
# la coleccion se configura con esta ventana (ver preparar_coleccion_dedup).
HISTORIAL_URL_DIAS = 15

# ── Sesion HTTP compartida (con reintentos) y rate-limit por dominio ─────────
_DOMAIN_LOCK = threading.Lock()
_DOMAIN_LAST_REQUEST = {}

def _crear_sesion():
    """Crea una requests.Session con reintentos/backoff para errores transitorios
    (timeouts, 429, 5xx) y la reutiliza en todo el script (evita reabrir una
    conexion TCP/TLS nueva por cada request)."""
    sesion = requests.Session()
    reintentos = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=reintentos, pool_maxsize=20)
    sesion.mount("https://", adapter)
    sesion.mount("http://", adapter)
    sesion.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; DiarioInfoBot/1.0)'})
    return sesion

SESSION = _crear_sesion()

def _esperar_turno_dominio(url):
    """Aplica un espaciado minimo entre requests al mismo dominio (thread-safe),
    para no golpear un mismo sitio con varios threads en simultaneo aunque
    distintas fuentes se procesen en paralelo."""
    dominio = urlsplit(url).netloc
    with _DOMAIN_LOCK:
        ahora = time.time()
        ultimo = _DOMAIN_LAST_REQUEST.get(dominio, 0)
        espera = DOMAIN_MIN_INTERVAL - (ahora - ultimo)
        if espera > 0:
            time.sleep(espera)
        _DOMAIN_LAST_REQUEST[dominio] = time.time()

def http_get(url, **kwargs):
    """GET con sesion compartida, reintentos y rate-limit por dominio."""
    _esperar_turno_dominio(url)
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    return SESSION.get(url, **kwargs)

# ── Helpers ───────────────────────────────────────────────────────────────────

def generar_slug(titulo):
    """Genera un slug URL-amigable desde el titulo."""
    s = titulo.lower().strip()
    # Reemplazar caracteres acentuados
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Reemplazar caracteres no alfanumericos por guion
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-')
    # Limitar largo a 80 caracteres
    if len(s) > 80:
        s = s[:80].rsplit('-', 1)[0]
    # Agregar timestamp para unicidad
    ts = datetime.now().strftime('%Y%m%d%H%M')
    return f"{s}-{ts}"

def _parsear_texto_fecha(texto):
    """Convierte un string a datetime timezone-aware (UTC si no trae zona
    horaria explicita). Usa dateutil en modo fuzzy en vez de una lista fija
    de formatos (strptime), para tolerar variaciones de formato entre sitios
    que antes hacian fallar el parseo silenciosamente. dayfirst=True porque
    las fuentes son todas de Argentina (dd/mm/yyyy)."""
    if not texto:
        return None
    try:
        dt = dateutil_parser.parse(texto, fuzzy=True, dayfirst=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _fecha_desde_json_ld(soup):
    """Busca datePublished/dateModified en bloques JSON-LD (schema.org
    NewsArticle/Article), que muchos sitios incluyen aunque el HTML visible
    no tenga un elemento de fecha reconocible por selector_fecha."""
    for script_tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script_tag.string or '')
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        # Algunos CMS anidan los items reales dentro de "@graph"
        expandido = []
        for item in items:
            if not isinstance(item, dict):
                continue
            expandido.append(item)
            grafo = item.get('@graph')
            if isinstance(grafo, list):
                expandido.extend(g for g in grafo if isinstance(g, dict))
        for item in expandido:
            for campo in ('datePublished', 'dateModified', 'uploadDate'):
                dt = _parsear_texto_fecha(item.get(campo))
                if dt:
                    return dt
    return None

def _fecha_desde_meta_tags(soup):
    """Busca la fecha en meta tags estandar que la mayoria de los CMS de
    noticias exponen independientemente del maquetado visible."""
    candidatos = [
        ('meta', {'property': 'article:published_time'}),
        ('meta', {'property': 'article:modified_time'}),
        ('meta', {'property': 'og:updated_time'}),
        ('meta', {'name': 'article:published_time'}),
        ('meta', {'itemprop': 'datePublished'}),
        ('meta', {'itemprop': 'dateModified'}),
        ('time', {'itemprop': 'datePublished'}),
    ]
    for tag, attrs in candidatos:
        el = soup.find(tag, attrs=attrs)
        if el:
            valor = el.get('content') or el.get('datetime') or el.get_text(strip=True)
            dt = _parsear_texto_fecha(valor)
            if dt:
                return dt
    return None

def parsear_fecha_articulo(soup, fuente):
    """Intenta extraer la fecha de publicacion del articulo, probando varias
    fuentes en orden de confiabilidad: 1) JSON-LD schema.org, 2) meta tags
    estandar, 3) el selector_fecha especifico de la fuente. Devuelve None
    solo si ninguna de las tres dio un resultado parseable."""
    dt = _fecha_desde_json_ld(soup)
    if dt:
        return dt

    dt = _fecha_desde_meta_tags(soup)
    if dt:
        return dt

    for sel in fuente['selector_fecha'].split(','):
        el = soup.select_one(sel.strip())
        if el:
            dt_attr = el.get('datetime') or el.get('data-datetime') or el.get('content')
            if dt_attr:
                dt = _parsear_texto_fecha(dt_attr)
                if dt:
                    return dt
            dt = _parsear_texto_fecha(el.get_text(strip=True))
            if dt:
                return dt
    return None

def es_reciente(soup, fuente, url, urls_historial, horas_max=2):
    """Decide si un articulo debe considerarse "reciente" (publicable).

    - Si se pudo determinar la fecha real: se acepta solo si su antiguedad
      es <= horas_max, igual que antes.
    - Si NO se pudo determinar la fecha (selector roto, formato no
      reconocido, sitio sin metadata de fecha): en vez de aceptar siempre
      por default, se usa el historial largo de URLs (HISTORIAL_URL_DIAS)
      como señal de respaldo. Si la URL nunca aparecio en ese historial se
      acepta (probablemente nueva); si ya aparecio se descarta (probablemente
      un link viejo reflotado, ej. desde un widget de "mas leidas").

    Devuelve (aceptar: bool, motivo: str) para poder loguear el criterio
    usado en cada caso.
    """
    fecha = parsear_fecha_articulo(soup, fuente)
    if fecha is not None:
        ahora = datetime.now(timezone.utc)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        antiguedad = ahora - fecha
        logger.debug(f"Fecha articulo: {fecha}, antiguedad: {antiguedad}")
        if antiguedad <= timedelta(hours=horas_max):
            return True, "fecha_reciente"
        return False, f"fecha_vieja ({antiguedad})"

    # Fecha no determinable: fallback por historial largo de URLs.
    if normalizar_url(url) in urls_historial:
        return False, f"sin_fecha_ya_vista_en_historial_{HISTORIAL_URL_DIAS}d"
    return True, f"sin_fecha_nueva_en_historial_{HISTORIAL_URL_DIAS}d"

def extraer_imagen_principal(soup, fuente):
    """Extrae la imagen principal: og:image > twitter:image > primera img del cuerpo."""
    # 1. Prioridad maxima: og:image (imagen destacada de redes sociales)
    og = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name':'og:image'})
    if og:
        src = og.get('content', '')
        if src and src.startswith('http') and not src.endswith('.gif'):
            return src
    # 2. twitter:image
    tw = soup.find('meta', attrs={'name':'twitter:image'}) or soup.find('meta', property='twitter:image')
    if tw:
        src = tw.get('content', '')
        if src and src.startswith('http') and not src.endswith('.gif'):
            return src
    # 3. link rel=image_src
    link_img = soup.find('link', rel='image_src')
    if link_img:
        src = link_img.get('href', '')
        if src and src.startswith('http'):
            return src
    # 4. Primera imagen grande dentro del cuerpo del articulo (NO galeria)
    SKIP_KEYWORDS = ['logo', 'icon', 'avatar', 'ad', 'banner', 'pixel', 'thumb',
                      'galeria', 'gallery', 'slider', 'carousel', 'widget', 'sidebar',
                      'publicidad', 'sponsors', 'footer', 'header', 'nav']
    body_selectors = ['article img', '.nota__body img', '.article-body img',
                       '.entry-content img', '.post-content img', 'main img']
    for sel in body_selectors:
        for img in soup.select(sel):
            # Saltar imagenes en galerias
            parent_classes = ' '.join([
                ' '.join(p.get('class', []))
                for p in img.parents
                if hasattr(p, 'get')
            ][:5]).lower()
            if any(k in parent_classes for k in ['galeria', 'gallery', 'slider', 'carousel']):
                continue
            src = (img.get('src') or img.get('data-src') or
                   img.get('data-lazy-src') or img.get('data-original') or '')
            if not src:
                srcset = img.get('srcset', '')
                if srcset:
                    parts = [p.strip().split(' ')[0] for p in srcset.split(',')]
                    src = next((p for p in reversed(parts) if p.startswith('http')), '')
            if src and src.startswith('http') and not src.endswith('.gif'):
                if not any(skip in src.lower() for skip in SKIP_KEYWORDS):
                    # Descartar imagenes muy pequenas por nombre (thumb, small)
                    if not any(x in src.lower() for x in ['-50x', '-75x', '-100x', '-150x', 'thumbnail']):
                        return src
    return None

def normalizar_url(url):
    """Normaliza una URL para detectar la misma nota aunque cambien parametros
    de tracking (utm_source y similares), barra final, www. vs sin www."""
    try:
        from urllib.parse import urlsplit, urlunsplit
        p = urlsplit(url)
        netloc = p.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        path = p.path.rstrip('/')
        return urlunsplit((p.scheme, netloc, path, '', ''))
    except Exception:
        return url

def preparar_coleccion_dedup(col_dedup):
    """Asegura el indice TTL sobre createdAt, con el TTL fijado por
    HISTORIAL_URL_DIAS (necesita ser mas largo que VENTANA_DEDUP_HORAS porque
    la misma coleccion ahora tambien sirve como historial largo de URLs para
    el fallback de fecha-no-determinable). Si el indice ya existia con otro
    TTL (por ejemplo, de una version anterior del script que usaba 24h), lo
    recrea con el valor nuevo en vez de fallar."""
    ttl_segundos = HISTORIAL_URL_DIAS * 24 * 3600
    try:
        col_dedup.create_index("createdAt", expireAfterSeconds=ttl_segundos)
    except Exception:
        try:
            col_dedup.drop_index("createdAt_1")
            col_dedup.create_index("createdAt", expireAfterSeconds=ttl_segundos)
            logger.info(f"Indice TTL de dedup recreado ({HISTORIAL_URL_DIAS} dias)")
        except Exception as e2:
            logger.warning(f"No se pudo asegurar/actualizar indice TTL de dedup: {e2}")

def cargar_pool_dedup(col_dedup):
    """Trae URLs normalizadas y titulos originales procesados en la ventana
    reciente (incluye corridas de cron anteriores, no solo la actual). Se usa
    para la deduplicacion de notas (misma URL / mismo hecho contado por otra
    fuente), no para decidir si algo es "nuevo" en terminos de fecha."""
    desde = datetime.now(timezone.utc) - timedelta(hours=VENTANA_DEDUP_HORAS)
    try:
        docs = col_dedup.find({"createdAt": {"$gte": desde}}, {"url": 1, "titulo": 1})
        urls, titulos = set(), []
        for d in docs:
            if d.get("url"):
                urls.add(d["url"])
            if d.get("titulo"):
                titulos.append(d["titulo"])
        logger.info(f"Pool de dedup: {len(urls)} URLs, {len(titulos)} titulos (ultimas {VENTANA_DEDUP_HORAS}h)")
        return urls, titulos
    except Exception as e:
        logger.error(f"Error cargando pool de dedup: {e}")
        return set(), []

def cargar_urls_historial(col_dedup):
    """Trae TODAS las URLs normalizadas vistas en los ultimos HISTORIAL_URL_DIAS
    dias (no solo el titulo, y con una ventana mucho mas larga que el pool de
    dedup de arriba). Se usa exclusivamente como señal de respaldo en
    es_reciente() cuando un articulo no tiene fecha determinable: si la URL
    nunca aparecio aca, se trata como probablemente nueva."""
    desde = datetime.now(timezone.utc) - timedelta(days=HISTORIAL_URL_DIAS)
    try:
        docs = col_dedup.find({"createdAt": {"$gte": desde}}, {"url": 1})
        urls = {d["url"] for d in docs if d.get("url")}
        logger.info(f"Historial largo de URLs: {len(urls)} (ultimos {HISTORIAL_URL_DIAS} dias)")
        return urls
    except Exception as e:
        logger.error(f"Error cargando historial largo de URLs: {e}")
        return set()

def registrar_dedup(col_dedup, url, titulo_original):
    """Registra una URL/titulo ya procesados para que corridas futuras
    (dentro de la ventana TTL) no los repitan."""
    try:
        col_dedup.insert_one({
            "url": normalizar_url(url),
            "titulo": titulo_original,
            "createdAt": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error(f"Error registrando dedup: {e}")

def scrape_lista_articulos(fuente):
    """Obtiene lista de URLs de articulos de una fuente."""
    try:
        resp = http_get(fuente['url'])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        urls = set()
        for sel in fuente['selector_lista'].split(','):
            for a in soup.select(sel.strip()):
                href = a.get('href', '')
                if href:
                    if not href.startswith('http'):
                        from urllib.parse import urljoin
                        href = urljoin(fuente['url'], href)
                    urls.add(href)
        logger.info(f"Links {fuente['nombre']}: {len(urls)}")
        return list(urls)[:15]
    except Exception as e:
        logger.error(f"Error scrapeando lista {fuente['nombre']}: {e}")
        return []

def obtener_urls_por_fuente(fuentes):
    """Obtiene, en paralelo, la lista de URLs de articulos de todas las fuentes.
    Es una operacion de solo lectura (no toca Mongo ni estado compartido de
    dedup), asi que paralelizarla es seguro y acelera bastante el arranque de
    cada corrida (antes se hacia una fuente a la vez, de forma secuencial)."""
    resultados = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_FUENTES) as executor:
        futuros = {executor.submit(scrape_lista_articulos, f): f['nombre'] for f in fuentes}
        for fut in as_completed(futuros):
            nombre = futuros[fut]
            try:
                resultados[nombre] = fut.result()
            except Exception as e:
                logger.error(f"Fuente {nombre} fallo al obtener el listado: {e}")
                resultados[nombre] = []
    return resultados

def scrape_articulo(url, fuente, urls_historial):
    """Scrape un articulo y retorna titulo, cuerpo, imagen y url_original."""
    try:
        resp = http_get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # ── Filtro de fecha ──────────────────────────────────────────────────
        aceptar, motivo = es_reciente(soup, fuente, url, urls_historial, HORAS_MAX)
        if not aceptar:
            logger.info(f"Articulo descartado ({motivo}): {url}")
            return None
        if motivo.startswith("sin_fecha"):
            logger.warning(f"Sin fecha determinable, se acepta por no estar en el historial de {HISTORIAL_URL_DIAS}d: {url}")

        # ── Titulo ───────────────────────────────────────────────────────────
        titulo = None
        for sel in fuente['selector_titulo'].split(','):
            el = soup.select_one(sel.strip())
            if el:
                titulo = el.get_text(strip=True)
                break

        # ── Cuerpo ───────────────────────────────────────────────────────────
        parrafos = []
        for sel in fuente['selector_cuerpo'].split(','):
            elements = soup.select(sel.strip())
            for el in elements:
                text = el.get_text(strip=True)
                if len(text) > 50 and text not in parrafos:
                    parrafos.append(text)
            if len(parrafos) >= 4:
                break

        cuerpo = " ".join(parrafos[:8])

        # ── Fallback titulo ──────────────────────────────────────────────────
        if not titulo:
            h1 = soup.find("h1")
            if h1:
                titulo = h1.get_text(strip=True)

        # ── Fallback cuerpo ──────────────────────────────────────────────────
        if not cuerpo:
            all_p = soup.find_all("p")
            parrafos_alt = [p.get_text(strip=True) for p in all_p if len(p.get_text(strip=True)) > 30]
            cuerpo = " ".join(parrafos_alt[:10])

        if not titulo or not cuerpo:
            logger.warning(f"Articulo incompleto en {url}")
            return None

        # ── Imagen principal ─────────────────────────────────────────────────
        imagen_url = extraer_imagen_principal(soup, fuente)

        return {
            "titulo": titulo,
            "cuerpo": cuerpo,
            "url_original": url,
            "imagen_url": imagen_url,
            "credito_imagen": fuente.get("credito", "")
        }
    except Exception as e:
        logger.error(f"Error scrapeando articulo {url}: {e}")
        return None

def reescribir_con_claude(articulo, categoria):
    """Usa Claude via proxy Vercel para reescribir el articulo en formato DiarioInfo."""
    try:
        payload = {
            "titulo":    articulo["titulo"],
            "cuerpo":    articulo["cuerpo"][:3000],
            "categoria": categoria,
            "apiKey":    ANTHROPIC_API_KEY
        }
        resp = SESSION.post(VERCEL_REWRITE_URL, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            raise ValueError(result["error"])
        return result
    except Exception as e:
        err_body = ""
        try:
            err_body = resp.text[:500]
        except Exception:
            pass
        logger.error(f"Error con Claude API: {e} | body: {err_body}")
        return None

def registrar_imagen_en_files(col_files, imagen_url, credito, titulo_articulo):
    """Registra la imagen externa en la coleccion files y retorna su ObjectId."""
    try:
        fecha_ahora = datetime.now(timezone.utc)
        # Extraer nombre de archivo de la URL
        nombre_archivo = imagen_url.split('/')[-1].split('?')[0] or 'imagen.jpg'
        if not any(nombre_archivo.endswith(ext) for ext in ['.jpg','.jpeg','.png','.webp','.gif']):
            nombre_archivo += '.jpg'

        doc_file = {
            "fileName": nombre_archivo,
            "originalName": nombre_archivo,
            "fileUrl": imagen_url,
            "thumbnailUrl": imagen_url,
            "description": f"Imagen de {credito} - {titulo_articulo[:80]}",
            "mimeType": "image/jpeg",
            "size": 0,
            "width": 0,
            "height": 0,
            "uploadedBy": "agregador-automatico",
            "usageCount": 0,
            "isExternal": True,
            "creditSource": credito,
            "createdAt": fecha_ahora,
            "updatedAt": fecha_ahora,
            "__v": 0
        }
        result = col_files.insert_one(doc_file)
        logger.info(f"Imagen registrada en files: {imagen_url[:60]}... (ID: {result.inserted_id})")
        return result.inserted_id
    except Exception as e:
        logger.error(f"Error registrando imagen en files: {e}")
        return None

def generar_tags(titulo, copete, categoria, fuente_nombre):
    """Genera tags automaticos desde el titulo y contenido de la nota."""
    tags = set()
    # Tag fijo: agregador y categoria
    tags.add('agregador')
    tags.add(categoria)
    # Tag del medio fuente
    fuente_tag = fuente_nombre.lower().replace(' ', '-')
    tags.add(fuente_tag)
    # Extraer palabras clave del titulo (nombres propios y palabras importantes)
    texto = (titulo + ' ' + copete).lower()
    # Normalizar acentos para busqueda
    texto_norm = unicodedata.normalize('NFD', texto)
    texto_norm = ''.join(c for c in texto_norm if unicodedata.category(c) != 'Mn')
    # Palabras clave de categorias
    KEYWORDS_POLICIAL = ['detenido', 'arrestado', 'policia', 'robo', 'hurto', 'asesinato',
                          'homicidio', 'droga', 'secuestro', 'accidente', 'choque', 'fallecio',
                          'murio', 'herido', 'dfi', 'penal', 'judicial', 'fiscal', 'imputado',
                          'condena', 'prision', 'carcel', 'fugado', 'allanamiento']
    KEYWORDS_ESPEC = ['musica', 'cine', 'teatro', 'television', 'tele', 'actor', 'actriz',
                       'cantante', 'banda', 'pelicula', 'serie', 'show', 'espectaculo',
                       'famoso', 'celebridad', 'argentina', 'seleccion', 'futbol',
                       'novela', 'album', 'gira', 'concierto', 'partido']
    for kw in KEYWORDS_POLICIAL + KEYWORDS_ESPEC:
        if kw in texto_norm:
            tags.add(kw)
    # Extraer palabras con mayuscula inicial del titulo (posibles nombres propios)
    palabras = titulo.split()
    STOPWORDS = {'el','la','los','las','un','una','unos','unas','de','del','al','en','por',
                 'con','sin','sobre','entre','para','que','se','su','sus','fue','es','era',
                 'son','han','hay','tras','ante','bajo','como','mas','pero','y','e','o','u',
                 'a','le','les','lo','me','te','nos','les','si','no','ya','muy','bien'}
    for i, p in enumerate(palabras):
        p_clean = re.sub(r'[^a-zA-ZaeiouAEIOUntNTÀ-ž]', '', p)
        if (len(p_clean) >= 4 and p_clean[0].isupper() and i > 0
                and p_clean.lower() not in STOPWORDS):
            tags.add(p_clean.lower())
    # Limitar a 8 tags, ordenados
    result = sorted(list(tags))[:8]
    return result

def conectar_mongo():
    """Conecta a MongoDB y retorna (col_articles, col_files, col_dedup) o (None, None, None)."""
    if not PYMONGO_OK:
        logger.error("pymongo no instalado. Ejecutar: pip install pymongo")
        return None, None, None
    if not MONGO_URI:
        logger.error("Variable de entorno MONGO_URI no configurada. Abortando.")
        return None, None, None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client.server_info()
        db = client[MONGO_DB]
        col_art = db[MONGO_COLLECTION]
        col_files = db[MONGO_FILES_COL]
        col_dedup = db[MONGO_DEDUP_COL]
        preparar_coleccion_dedup(col_dedup)
        logger.info("Conexion MongoDB exitosa")
        return col_art, col_files, col_dedup
    except Exception as e:
        logger.error(f"Error conectando MongoDB: {e}")
        return None, None, None

def publicar_articulo(nota_reescrita, categoria_id, col_art, col_files, url_original, imagen_url, credito_imagen, es_sde=False, paso_por_ia=True):
    """Inserta un articulo en MongoDB como DRAFT con imagen y slug."""
    try:
        fecha_ahora = datetime.now(timezone.utc)
        titulo = nota_reescrita['titulo']
        fuente_categoria = categoria_id  # para color de author

        # ── Generar slug unico ───────────────────────────────────────────────
        slug = generar_slug(titulo)

        # ── Registrar imagen si existe ───────────────────────────────────────
        image_id = None
        if imagen_url and col_files is not None:
            image_id = registrar_imagen_en_files(col_files, imagen_url, credito_imagen, titulo)

        # ── Preparar HTML del cuerpo ─────────────────────────────────────────
        cuerpo_html = nota_reescrita.get('cuerpo', '')
        if not cuerpo_html.strip().startswith('<'):
            parrafos = cuerpo_html.split('\n\n') if '\n\n' in cuerpo_html else [cuerpo_html]
            cuerpo_html = ''.join(f'<p>{p.strip()}</p>' for p in parrafos if p.strip())

        doc = {
            "title": titulo,
            "description": nota_reescrita.get('copete', cuerpo_html[:200]),
            "content": cuerpo_html,
            "category": categoria_id,
            "status": "draft",
            "isHighlighted": False,
            "publicationDate": fecha_ahora,
            "commentsDisabled": False,
            "keyPoints": [],
            "priority": 0,
            "destination": [],
            "validityHours": 0,
            "tags": generar_tags(titulo, nota_reescrita.get("copete", ""), categoria_id, credito_imagen),
            "articleType": "nota",
            "sourceUrl": url_original,
            "slug": slug,
            "author": generar_autor_codificado(fuente_categoria, es_sde, paso_por_ia),
            "authorColor": AUTHOR_COLORS.get(fuente_categoria, "#555555"),
            "authorPrefixColor": AUTHOR_PREFIX_COLOR_SDE if es_sde else AUTHOR_PREFIX_COLOR_NACIONAL,
            "createdBy": "agregador-automatico",
            "createdAt": fecha_ahora,
            "updatedAt": fecha_ahora,
            "__v": 0
        }

        # Agregar imageId solo si se registro imagen
        if image_id:
            doc["imageId"] = str(image_id)

        result = col_art.insert_one(doc)
        logger.info(f"Articulo insertado como DRAFT: {titulo} (slug: {slug}) (ID: {result.inserted_id})")
        return True
    except Exception as e:
        logger.error(f"Error insertando articulo MongoDB: {e}")
        return False

STOPWORDS_DEDUP = {
    'el','la','los','las','un','una','unos','unas','de','del','al','en','por',
    'con','sin','sobre','entre','para','que','se','su','sus','fue','es','era',
    'son','han','hay','tras','ante','bajo','como','mas','pero','y','e','o','u',
    'a','le','les','lo','me','te','nos','si','no','ya','muy','bien','este',
    'esta','estos','estas','sera','seran','luego','despues','tambien'
}

# Sinonimos de vocabulario policial/judicial: dos medios cubriendo el mismo
# hecho suelen usar verbos distintos ("arrestaron" vs "detuvieron", "asalto"
# vs "robo"), y como esas palabras no se parecen entre si letra por letra,
# el matching por overlap de palabras las trataba como si no tuvieran nada
# en comun y subestimaba la similitud real. Se normalizan a una forma
# canonica antes de comparar. A proposito NO se incluyen verbos de resultado
# deportivo (goleo/vencio/gano): dos partidos con resultado opuesto ya
# comparten casi todo el resto del titulo (equipos, estadio), asi que
# unificar tambien esos verbos aumentaria falsos positivos en vez de
# reducirlos.
SINONIMOS_DEDUP = {
    'arrestaron':'detener','arresto':'detener','arrestado':'detener','arrestada':'detener',
    'detuvieron':'detener','detuvo':'detener','detenido':'detener','detenida':'detener','detiene':'detener',
    'aprehendieron':'detener','aprehendido':'detener','capturaron':'detener','capturado':'detener',
    'robo':'robar','robaron':'robar','hurto':'robar','hurtaron':'robar',
    'asalto':'robar','asaltaron':'robar','sustrajeron':'robar',
    'choco':'choque','chocaron':'choque','colision':'choque','colisiono':'choque',
    'embistio':'choque','embistieron':'choque',
    'murio':'morir','murieron':'morir','fallecio':'morir','fallecieron':'morir','deceso':'morir',
    'heridos':'herido','lesionado':'herido','lesionados':'herido','lesionada':'herido',
    'procesado':'imputado','acusado':'imputado','acusada':'imputado',
    'investigan':'investigar','investigacion':'investigar','indagan':'investigar',
    'allanaron':'allanamiento','allano':'allanamiento',
}

def normalizar_titulo(titulo):
    """Normaliza un titulo (minuscula, sin acentos, solo alfanumerico)."""
    s = titulo.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9 ]', '', s)
    return s

def palabras_clave(titulo):
    """Palabras con contenido de un titulo (sin stopwords, sinonimos policiales
    normalizados a una forma canonica). Si el titulo es muy corto y queda
    vacio tras filtrar, usa todas las palabras como fallback para no perder
    la comparacion."""
    palabras = normalizar_titulo(titulo).split()
    filtradas = {
        SINONIMOS_DEDUP.get(p, p)
        for p in palabras if p not in STOPWORDS_DEDUP and len(p) > 2
    }
    return filtradas if filtradas else set(palabras)

def titulos_similares(t1, t2, umbral=0.65):
    """Devuelve True si dos titulos parecen tratar el mismo hecho, comparando
    solo palabras con contenido (se ignoran articulos/preposiciones, que antes
    diluian el puntaje y generaban falsos positivos y falsos negativos)."""
    w1, w2 = palabras_clave(t1), palabras_clave(t2)
    if not w1 or not w2:
        return False
    interseccion = w1 & w2
    similitud = len(interseccion) / max(len(w1), len(w2))
    return similitud >= umbral

def procesar_articulo(url, fuente, urls_vistas, titulos_vistos, dedup_lock, col_art, col_files, col_dedup, urls_historial):
    """Procesa (scrape + reescritura + publicacion) un unico articulo.
    Pensado para correr dentro de un thread: las secciones que tocan estado
    compartido de dedup (urls_vistas / titulos_vistos) estan protegidas por
    dedup_lock para evitar condiciones de carrera entre threads.
    urls_historial es de solo lectura (historial largo de URLs para el
    fallback de fecha-no-determinable), no necesita lock.
    Devuelve True si se publico, False si se proceso pero no se publico,
    y None si se descarto antes de scrapear (URL ya vista)."""
    url_norm = normalizar_url(url)

    # Reserva atomica: si dos threads llegaran a tener la misma URL (no deberia
    # pasar dentro de una misma fuente porque scrape_lista_articulos ya usa un
    # set), el primero se queda con el trabajo y el resto corta aca.
    with dedup_lock:
        if url_norm in urls_vistas:
            logger.debug(f"Ya procesada: {url}")
            return None
        urls_vistas.add(url_norm)

    # Scrape del articulo (incluye filtro de fecha)
    articulo = scrape_articulo(url, fuente, urls_historial)
    if not articulo:
        registrar_dedup(col_dedup, url, "")
        return None

    # Reescribir con IA (con fallback si el proxy no responde)
    nota_reescrita = reescribir_con_claude(articulo, fuente['categoria'])
    paso_por_ia = nota_reescrita is not None
    if not nota_reescrita:
        logger.warning("Claude API no disponible, usando contenido original")
        nota_reescrita = {
            "titulo": articulo['titulo'],
            "copete": articulo['cuerpo'][:200].split('.')[0] + ".",
            "cuerpo": articulo['cuerpo']
        }

    # Deduplicacion: comparamos el TITULO ORIGINAL scrapeado (antes de la IA), ya que
    # la reescritura cambia intencionalmente la redaccion, y dos notas del mismo hecho
    # pueden terminar con titulos muy distintos despues de pasar por la IA.
    titulo_original = articulo.get('titulo', '')
    with dedup_lock:
        es_duplicado = any(titulos_similares(titulo_original, t) for t in titulos_vistos)
        if not es_duplicado:
            titulos_vistos.append(titulo_original)

    if es_duplicado:
        logger.info(f" [SKIP-DEDUP] Titulo similar ya existe: {titulo_original[:60]}")
        registrar_dedup(col_dedup, url, titulo_original)
        return False

    # Publicar en MongoDB
    categoria_id = CATEGORIAS[fuente['categoria']]
    publicado = publicar_articulo(
        nota_reescrita,
        categoria_id,
        col_art,
        col_files,
        url,
        articulo.get('imagen_url'),
        articulo.get('credito_imagen', fuente.get('credito', '')),
        es_sde=fuente.get('es_sde', False),
        paso_por_ia=paso_por_ia
    )
    if publicado:
        registrar_dedup(col_dedup, url, titulo_original)
        return True
    return False

def main():
    """Funcion principal del agregador."""
    logger.info("=" * 60)
    logger.info("Iniciando agregador de noticias DiarioInfo")
    logger.info(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Filtrando noticias de las ultimas {HORAS_MAX} horas")
    logger.info("=" * 60)

    # Conectar a MongoDB
    col_art, col_files, col_dedup = conectar_mongo()
    if col_art is None:
        logger.error("No se pudo conectar a MongoDB. Abortando.")
        return

    # Pool de deduplicacion: URLs normalizadas + titulos originales procesados
    # en las ultimas VENTANA_DEDUP_HORAS, sin importar en que corrida de cron
    # se hayan procesado. Se sigue completando en memoria durante esta misma
    # corrida (igual que antes), pero ahora arranca con el historial reciente
    # en vez de una lista vacia. Compartido entre threads -> protegido por lock.
    urls_vistas, titulos_vistos = cargar_pool_dedup(col_dedup)
    dedup_lock = threading.Lock()

    # Historial largo de URLs (independiente del pool de dedup de arriba):
    # solo se consulta cuando un articulo no tiene fecha determinable, para
    # decidir si es probablemente nueva o un link viejo reflotado. Se carga
    # una sola vez al arrancar la corrida (solo lectura, no necesita lock).
    urls_historial = cargar_urls_historial(col_dedup)

    total_publicados = 0

    # Traer el listado de articulos de TODAS las fuentes en paralelo (I/O-bound
    # y de solo lectura, no hay estado compartido que proteger aca).
    urls_por_fuente = obtener_urls_por_fuente(FUENTES)

    # Procesar cada fuente. Un error inesperado en una fuente no debe cortar
    # el resto de la corrida.
    for fuente in FUENTES:
        try:
            logger.info(f"\nProcesando fuente: {fuente['nombre']}")

            urls = urls_por_fuente.get(fuente['nombre'], [])
            if not urls:
                continue

            publicados_fuente = 0

            # Los articulos de una misma fuente se procesan en paralelo (con
            # rate-limit por dominio dentro de http_get). El lock de dedup
            # asegura que dos threads no publiquen el mismo hecho dos veces.
            with ThreadPoolExecutor(max_workers=MAX_WORKERS_ARTICULOS) as executor:
                futuros = [
                    executor.submit(
                        procesar_articulo, url, fuente, urls_vistas, titulos_vistos,
                        dedup_lock, col_art, col_files, col_dedup, urls_historial
                    )
                    for url in urls
                ]
                for fut in as_completed(futuros):
                    try:
                        if fut.result() is True:
                            publicados_fuente += 1
                            total_publicados += 1
                    except Exception as e:
                        logger.error(f"Error procesando articulo de {fuente['nombre']}: {e}")

            logger.info(f"[{fuente['nombre']}] {publicados_fuente} articulos publicados")
        except Exception as e:
            logger.error(f"Error inesperado procesando fuente {fuente['nombre']}: {e}")
            continue

    logger.info(f"\nTOTAL publicados esta ejecucion: {total_publicados}")
    logger.info("Agregador finalizado")

if __name__ == "__main__":
    main()

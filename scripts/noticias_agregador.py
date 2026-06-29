#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agregador de Noticias - DiarioInfo
Scrapea fuentes, reescribe con Gemini, inserta en MongoDB como DRAFT con imagen y slug.
Filtra noticias de las ultimas 5 horas.
"""

import requests
import json
import time
import os
import re
import unicodedata
import logging
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

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
MONGO_URI        = "mongodb+srv://diarioinfoio_db_user:lYcxG4pf5oCOgYnq@cluster0.c621o4c.mongodb.net/?retryWrites=true&w=majority"
MONGO_DB         = "diarioinfo-db"
MONGO_COLLECTION = "articles"
MONGO_FILES_COL  = "files"

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

HORAS_MAX        = 2   # Solo noticias de las ultimas N horas

FUENTES = [
    {
        "nombre": "El Liberal Policiales",
        "url": "https://www.elliberal.com.ar/policiales/",
        "selector_lista": "a[href*='/nota/']",
        "selector_titulo": "h1.nota__title, h1.article__title, h1",
        "selector_cuerpo": "div.nota__body p, div.article__body p, article p",
        "selector_imagen": "div.nota__image img, div.article__image img, figure img, article img",
        "selector_fecha": "time, span.fecha, .nota__date, .article__date",
        "categoria": "policiales",
        "credito": "El Liberal"
    },
    {
        "nombre": "Diario Panorama Policiales",
        "url": "https://www.diariopanorama.com/seccion/policiales_22",
        "selector_lista": "h2 a, h3 a, .news-title a, a[href*='/noticia/']",
        "selector_titulo": "h1.article-title, h1.entry-title, h1",
        "selector_cuerpo": "div.article-body p, div.entry-content p, article p",
        "selector_imagen": "div.article-image img, div.featured-image img, figure img, article img",
        "selector_fecha": "time, .article-date, .entry-date, span.date",
        "categoria": "policiales",
        "credito": "Diario Panorama"
    },
    {
        "nombre": "Diario Panorama Espectaculos",
        "url": "https://www.diariopanorama.com/seccion/espectaculos_47",
        "selector_lista": "h2 a, h3 a, .news-title a, a[href*='/noticia/']",
        "selector_titulo": "h1.article-title, h1.entry-title, h1",
        "selector_cuerpo": "div.article-body p, div.entry-content p, article p",
        "selector_imagen": "div.article-image img, div.featured-image img, figure img, article img",
        "selector_fecha": "time, .article-date, .entry-date, span.date",
        "categoria": "espectaculos",
        "credito": "Diario Panorama"
    },
    {
        "nombre": "La Nacion Espectaculos",
        "url": "https://www.lanacion.com.ar/espectaculos/",
        "selector_lista": "h2 a, h3 a, article a, a[href*='/espectaculos/']",
        "selector_titulo": "h1.headline, h1",
        "selector_cuerpo": "div.article-body p, div.body-article p, article p",
        "selector_imagen": "div.article-image img, figure img, picture img, article img",
        "selector_fecha": "time, span.fecha, .article-date",
        "categoria": "espectaculos",
        "credito": "La Nacion"
    }
]

CATEGORIAS = {
    "policiales": "policiales",
    "espectaculos": "espectaculos",
    "judiciales": "judiciales"
}

URLS_FILE = "/home/diarioin/scripts/urls_procesadas.json"

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


def parsear_fecha_articulo(soup, fuente):
    """Intenta extraer la fecha de publicacion del articulo."""
    for sel in fuente['selector_fecha'].split(','):
        el = soup.select_one(sel.strip())
        if el:
            # Buscar atributo datetime primero
            dt_attr = el.get('datetime') or el.get('data-datetime') or el.get('content')
            if dt_attr:
                try:
                    # Parsear ISO 8601
                    dt_attr = dt_attr.replace('Z', '+00:00')
                    return datetime.fromisoformat(dt_attr)
                except Exception:
                    pass
            # Intentar parsear el texto
            txt = el.get_text(strip=True)
            for fmt in ['%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%d de %B de %Y']:
                try:
                    return datetime.strptime(txt[:16], fmt).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
    return None


def es_reciente(soup, fuente, horas_max=2):
    """Devuelve True si el articulo fue publicado en las ultimas horas_max horas."""
    fecha = parsear_fecha_articulo(soup, fuente)
    if fecha is None:
        # Si no se puede determinar la fecha, aceptar el articulo
        logger.debug("No se pudo determinar fecha, aceptando articulo")
        return True
    ahora = datetime.now(timezone.utc)
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    antiguedad = ahora - fecha
    logger.debug(f"Fecha articulo: {fecha}, antiguedad: {antiguedad}")
    return antiguedad <= timedelta(hours=horas_max)


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
            # Saltar imagenes en galeras
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


def cargar_urls_procesadas():
    """Carga URLs ya procesadas desde archivo."""
    if os.path.exists(URLS_FILE):
        try:
            with open(URLS_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def guardar_url_procesada(url, urls_set):
    """Guarda una URL en el archivo de procesadas."""
    urls_set.add(url)
    try:
        with open(URLS_FILE, 'w') as f:
            json.dump(list(urls_set), f)
    except Exception as e:
        logger.error(f"Error guardando URL procesada: {e}")


def scrape_lista_articulos(fuente):
    """Obtiene lista de URLs de articulos de una fuente."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; DiarioInfoBot/1.0)'}
        resp = requests.get(fuente['url'], headers=headers, timeout=15)
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


def scrape_articulo(url, fuente):
    """Scrape un articulo y retorna titulo, cuerpo, imagen y url_original."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; DiarioInfoBot/1.0)'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # ── Filtro de fecha ──────────────────────────────────────────────────
        if not es_reciente(soup, fuente, HORAS_MAX):
            logger.info(f"Articulo demasiado antiguo (> {HORAS_MAX}h), descartado: {url}")
            return None

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


def reescribir_con_gemini(articulo, categoria):
    """Usa Gemini para reescribir el articulo en formato DiarioInfo."""
    prompt = f"""
Eres un redactor periodistico del Diario Info de Santiago del Estero, Argentina.
Reescribe la siguiente noticia de {categoria} en formato periodistico profesional.
La nota debe ser original, no copiar textualmente la fuente ni tampoco inventar nada.
Responde SOLO con un JSON con esta estructura exacta:
{{
  "titulo": "Titulo atractivo y periodistico (max 100 chars)",
  "copete": "Primer parrafo breve que resume la noticia (max 200 chars)",
  "cuerpo": "Cuerpo completo de la nota bien redactado (min 300 chars)"
}}

NOTICIA ORIGINAL:
Titulo: {articulo['titulo']}
Cuerpo: {articulo['cuerpo'][:1500]}
"""
    try:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY no configurada")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}
        }
        resp = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        text = data['candidates'][0]["content"]["parts"][0]["text"]
        # Limpiar markdown si viene con json
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        return result
    except Exception as e:
        logger.error(f"Error con Gemini: {e}")
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
    import unicodedata
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
    """Conecta a MongoDB y retorna (col_articles, col_files) o (None, None)."""
    if not PYMONGO_OK:
        logger.error("pymongo no instalado. Ejecutar: pip install pymongo")
        return None, None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        client.server_info()
        db = client[MONGO_DB]
        col_art = db[MONGO_COLLECTION]
        col_files = db[MONGO_FILES_COL]
        logger.info("Conexion MongoDB exitosa")
        return col_art, col_files
    except Exception as e:
        logger.error(f"Error conectando MongoDB: {e}")
        return None, None


def publicar_articulo(nota_reescrita, categoria_id, col_art, col_files, url_original, imagen_url, credito_imagen):
    """Inserta un articulo en MongoDB como DRAFT con imagen y slug."""
    try:
        fecha_ahora = datetime.now(timezone.utc)
        titulo = nota_reescrita['titulo']

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
            "author": "Redaccion DiarioInfo",
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


def main():
    """Funcion principal del agregador."""
    logger.info("=" * 60)
    logger.info("Iniciando agregador de noticias DiarioInfo")
    logger.info(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Filtrando noticias de las ultimas {HORAS_MAX} horas")
    logger.info("=" * 60)

    # Cargar URLs ya procesadas
    urls_procesadas = cargar_urls_procesadas()
    logger.info(f"URLs procesadas previamente: {len(urls_procesadas)}")

    # Conectar a MongoDB
    col_art, col_files = conectar_mongo()
    if col_art is None:
        logger.error("No se pudo conectar a MongoDB. Abortando.")
        return

    total_publicados = 0

    # Procesar cada fuente
    for fuente in FUENTES:
        logger.info(f"\nProcesando fuente: {fuente['nombre']}")

        # Obtener lista de articulos
        urls = scrape_lista_articulos(fuente)
        if not urls:
            continue

        publicados_fuente = 0

        for url in urls:
            # Verificar si ya fue procesada
            if url in urls_procesadas:
                logger.debug(f"Ya procesada: {url}")
                continue

            # Scrape del articulo (incluye filtro de fecha)
            articulo = scrape_articulo(url, fuente)
            if not articulo:
                guardar_url_procesada(url, urls_procesadas)
                continue

            # Reescribir con Gemini (con fallback)
            nota_reescrita = reescribir_con_gemini(articulo, fuente['categoria'])
            if not nota_reescrita:
                logger.warning(f"Gemini no disponible, usando contenido original")
                nota_reescrita = {
                    "titulo": articulo['titulo'],
                    "copete": articulo['cuerpo'][:200].split('.')[0] + ".",
                    "cuerpo": articulo['cuerpo']
                }

            # Publicar en MongoDB
            categoria_id = CATEGORIAS[fuente['categoria']]
            if publicar_articulo(
                nota_reescrita,
                categoria_id,
                col_art,
                col_files,
                url,
                articulo.get('imagen_url'),
                articulo.get('credito_imagen', fuente.get('credito', ''))
            ):
                guardar_url_procesada(url, urls_procesadas)
                publicados_fuente += 1
                total_publicados += 1

            # Pausa entre articulos para no sobrecargar
            time.sleep(2)

        logger.info(f"[{fuente['nombre']}] {publicados_fuente} articulos publicados")

    logger.info(f"\nTOTAL publicados esta ejecucion: {total_publicados}")
    logger.info("Agregador finalizado")


if __name__ == "__main__":
    main()

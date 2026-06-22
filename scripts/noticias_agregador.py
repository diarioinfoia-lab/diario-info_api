#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agregador Automatico de Noticias - DiarioInfo
Scraping + Reescritura con Gemini + Publicacion en ia2.diarioinfo.com
Ejecutar cada 2 horas con cron: 0 */2 * * * python3 /path/to/noticias_agregador.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
import hashlib
import os
from datetime import datetime

# ============================================================
# CONFIGURACION
# ============================================================

# API DiarioInfo ia2
CMS_API_URL = "https://api2.diarioinfo.com"
CMS_EMAIL = "admin@diarioinfo.com"
CMS_PASSWORD = "Admin1234!"

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "PLACEHOLDER_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# IDs de categorias en ia2
CATEGORIAS = {
    "espectaculos": "6a3342c75434513110dc600d",  # Interes General
    "policiales":   "6a334334eb8695e5e835fe7b",  # Policiales
    "judiciales":   "6a3343f07a9322b5cad47534",  # Judicial
}

# Archivo para registrar URLs ya procesadas (evitar duplicados)
PROCESADAS_FILE = "/home/diarioin/scripts/urls_procesadas.json"

# Fuentes de noticias
FUENTES = [
    {
        "nombre": "El Liberal - Policiales",
        "url": "https://www.elliberal.com.ar/?is=121",
        "selector_lista": "h3.portada-split-izq-3l__title a, h2.portada-split-izq-2l__title a",
        "selector_titulo": "h1.nota-titulo, h1",
        "selector_cuerpo": ".nota-texto-cuerpo p, article p",
        "base_url": "https://www.elliberal.com.ar",
        "categoria": "policiales",
        "max_articulos": 3
    },
    {
        "nombre": "Diario Panorama - Policiales",
        "url": "https://www.diariopanorama.com/secciones/14/policiales",
        "selector_lista": "h2 a, h3 a, .news-title a",
        "selector_titulo": "h1, .article-title",
        "selector_cuerpo": "article p, .article-body p, .entry-content p",
        "base_url": "https://www.diariopanorama.com",
        "categoria": "policiales",
        "max_articulos": 3
    },
    {
        "nombre": "Diario Panorama - Espectaculos",
        "url": "https://www.diariopanorama.com/secciones/18/espectaculos",
        "selector_lista": "h2 a, h3 a, .news-title a",
        "selector_titulo": "h1, .article-title",
        "selector_cuerpo": "article p, .article-body p, .entry-content p",
        "base_url": "https://www.diariopanorama.com",
        "categoria": "espectaculos",
        "max_articulos": 2
    },
    {
        "nombre": "La Nacion Espectaculos",
        "url": "https://www.lanacion.com.ar/espectaculos/",
        "selector_lista": "article.mod-article a.com-link, h2.com-title a",
        "selector_titulo": "h1.com-title, h1",
        "selector_cuerpo": ".body-nota p, .article-body p, article p",
        "base_url": "https://www.lanacion.com.ar",
        "categoria": "espectaculos",
        "max_articulos": 2
    },
]

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/home/diarioin/scripts/noticias.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}


def cargar_urls_procesadas():
    """Carga el set de URLs ya procesadas para evitar duplicados."""
    if os.path.exists(PROCESADAS_FILE):
        with open(PROCESADAS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def guardar_url_procesada(url, urls_procesadas):
    """Agrega una URL al set de procesadas y guarda en disco."""
    urls_procesadas.add(url)
    os.makedirs(os.path.dirname(PROCESADAS_FILE), exist_ok=True)
    with open(PROCESADAS_FILE, "w") as f:
        json.dump(list(urls_procesadas), f)


def scrape_lista_articulos(fuente):
    """Obtiene la lista de URLs de articulos de una fuente."""
    try:
        resp = requests.get(fuente['url'], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for selector in fuente['selector_lista'].split(","):
            selector = selector.strip()
            for el in soup.select(selector):
                href = el.get("href", "")
                if href and len(href) > 5:
                    if not href.startswith("http"):
                        href = fuente['base_url'] + href
                    if href not in links:
                        links.append(href)
        logger.info(f"[{fuente['nombre']}] {len(links)} links encontrados")
        return links[:fuente['max_articulos'] * 3]  # Tomar extra por si algunos fallan
    except Exception as e:
        logger.error(f"Error scrapeando lista {fuente['nombre']}: {e}")
        return []


def scrape_articulo(url, fuente):
    """Extrae el contenido de un articulo individual."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Titulo
        titulo = ""
        for sel in fuente['selector_titulo'].split(","):
            el = soup.select_one(sel.strip())
            if el:
                titulo = el.get_text(strip=True)
                break
        
        # Cuerpo
        parrafos = []
        for sel in fuente['selector_cuerpo'].split(","):
            elements = soup.select(sel.strip())
            for el in elements:
                text = el.get_text(strip=True)
                if len(text) > 50 and text not in parrafos:
                    parrafos.append(text)
            if len(parrafos) >= 4:
                break
        
        cuerpo = " ".join(parrafos[:8])
        
        if not titulo or not cuerpo:
            logger.warning(f"Articulo incompleto en {url}")
            return None
        
        return {"titulo": titulo, "cuerpo": cuerpo, "url_original": url}
    except Exception as e:
        logger.error(f"Error scrapeando articulo {url}: {e}")
        return None


def reescribir_con_gemini(articulo, categoria):
    """Usa Gemini para reescribir el articulo en formato DiarioInfo."""
    prompt = f"""
Eres un redactor periodistico del Diario Info de Santiago del Estero, Argentina.
Reescribe la siguiente nota en formato periodistico institucional.

NOTA ORIGINAL:
Titulo: {articulo['titulo']}
Contenido: {articulo['cuerpo'][:2000]}

INSTRUCCIONES:
- Estilo periodistico profesional, claro y atractivo
- Sin emojis ni simbolos especiales
- En espaÃÂ±ol rioplatense formal

DEVUELVE SOLO UN JSON valido con esta estructura exacta:
{{
  "titulo": "Titulo atractivo (maximo 15 palabras)",
  "copete": "Bajada breve de 1-2 oraciones que resume lo esencial",
  "cuerpo": "Cuerpo narrativo de 3-4 parrafos separados por \\n\\n"
}}
"""
    
    try:
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
        # Limpiar markdown si viene con ```json
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


def login_cms():
    """Obtiene el token de autenticacion del CMS."""
    try:
        resp = requests.post(
            f"{CMS_API_URL}/auth/signin",
            json={"email": CMS_EMAIL, "password": CMS_PASSWORD},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token") or data.get("data", {}).get("token")
        if token:
            logger.info("Login CMS exitoso")
            return token
        else:
            logger.error(f"Login CMS sin token: {data}")
            return None
    except Exception as e:
        logger.error(f"Error login CMS: {e}")
        return None


def publicar_articulo(nota_reescrita, categoria_id, token, url_original):
    """Publica un articulo en el CMS de DiarioInfo."""
    try:
        fecha_ahora = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        slug = hashlib.md5(nota_reescrita['titulo'].encode()).hexdigest()[:12]
        
        # Formatear el cuerpo como HTML simple
        parrafos = nota_reescrita["cuerpo"].split("\n\n")
        cuerpo_html = "".join(f"<p>{p.strip()}</p>" for p in parrafos if p.strip())
        
        payload = {
            "title": nota_reescrita['titulo'],
            "description": nota_reescrita["copete"],
            "content": cuerpo_html,
            "category": categoria_id,
            "status": "published",
            "publishedAt": fecha_ahora,
            "author": "Redaccion DiarioInfo",
            "slug": slug,
            "tags": ["agregador", "automatico"]
        }
        
        resp = requests.post(
            f"{CMS_API_URL}/articles",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        
        if resp.status_code in (200, 201):
            data = resp.json()
            art_id = data.get("data", {}).get("_id") or data.get("_id", "unknown")
            logger.info(f"Articulo publicado: {nota_reescrita['titulo']} (ID: {art_id})")
            return True
        else:
            logger.error(f"Error publicando ({resp.status_code}): {resp.text[:300]}")
            return False
    except Exception as e:
        logger.error(f"Error publicando articulo: {e}")
        return False


def main():
    """Funcion principal del agregador."""
    logger.info("=" * 60)
    logger.info("Iniciando agregador de noticias DiarioInfo")
    logger.info(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Cargar URLs ya procesadas
    urls_procesadas = cargar_urls_procesadas()
    logger.info(f"URLs procesadas previamente: {len(urls_procesadas)}")
    
    # Login al CMS
    token = login_cms()
    if not token:
        logger.error("No se pudo obtener token. Abortando.")
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
            
            if publicados_fuente >= fuente['max_articulos']:
                break
            
            logger.info(f"Procesando: {url}")
            
            # Scraping del articulo
            articulo = scrape_articulo(url, fuente)
            if not articulo:
                continue
            
            # Reescritura con Gemini
            nota_reescrita = reescribir_con_gemini(articulo, fuente['categoria'])
            if not nota_reescrita:
                continue
            
            # Publicar en CMS
            categoria_id = CATEGORIAS[fuente['categoria']]
            if publicar_articulo(nota_reescrita, categoria_id, token, url):
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

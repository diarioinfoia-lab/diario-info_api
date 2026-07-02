#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

# ==============================================================================
# CHANGELOG AUTOMATICO - VERSIONES
# v3.41 - Bajar notas secundarias 12pt (SEC_H 102.6->98.4mm)
# v3.37 - Sin categoria en Layout A, cotizaciones con API fallback dolarapi.com
# v3.36 - Subir notas secundarias +30pt adicionales (SEC_H 92->102.6mm)
# v3.35 - Subir notas secundarias 20pt (SEC_H 85->92mm)
# v3.34 - Categoria overlay encima imagen secundaria; titulo completo abajo
# v3.33 - Restaurar categoria en notas secundarias; titulo 10pt abajo completo
# v3.32 - Sin categoria nota 1col tapa; TIT_SEC -6pt; sec mas abajo
# v3.31 - Fix sort: publicationDate DESC primero para noticias actualizadas
# v3.30 - Boton dinamico en flipbook; fix cache PDF; fix URL flipbook
# v3.20 - Version base con todas las correcciones iniciales
# ==============================================================================
# NOTAS TECNICAS:
# - Layout A: foto apaisada (ratio>=1.45) full bleed, titulo debajo, SIN categoria
# - Layout B: foto vertical (ratio<1.45) 1col izq, titulo 2da col, SIN categoria
# - Notas secundarias: 3 columnas, imagen + categoria overlay + titulo completo
# - Sort MongoDB: [("publicationDate",-1), ("priority",-1)] - fecha primero
# - SEC_H = 102.6mm (subida total de 17.6mm / 50pt desde version original)
# - Cotizaciones: API bluelytics primero, fallback dolarapi.com
# - Merriweather no disponible -> usa Lato-Bold como fallback titular
# ==============================================================================
Diario Info - Generador de PDF Edicion Impresa v3.34 - cat overlay encima imagen sec; titulo completo abajo
Correcciones: lookup de categorias, URLs de imagenes correctas, clima en Celsius 
"""

import os, sys, re, io, html, urllib.parse
import urllib.request, urllib.error
from datetime import datetime, timedelta

import pymongo
from bson import ObjectId
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ── Configuracion MongoDB ──────────────────────────────────────────────────────
URI_PRIMARY  = "mongodb+srv://diarioinfoio_db_user:lYcxG4pf5oCOgYnq@cluster0.c621o4c.mongodb.net/diarioinfo-db?retryWrites=true&w=majority"
DB_PRIMARY   = "diarioinfo-db"
URI_FALLBACK = "mongodb+srv://diarioinfoio_db_user:lYcxG4pf5oCOgYnq@cluster0.wypjl60.mongodb.net/diario-info-db?retryWrites=true&w=majority"
DB_FALLBACK  = "diario-info-db"
BASE_IMG_URL = "https://ia.diarioinfo.com"

# ── Directorios ────────────────────────────────────────────────────────────────
HOY          = datetime.now()
FECHA_STR    = HOY.strftime("%Y-%m-%d")
DIR_REVISTAS = os.path.expanduser("~/public_html/revistas/diarioinfo")
DIR_FLIPBOOK = os.path.expanduser("~/public_html/flipbook")
DIR_FUENTES  = os.path.expanduser("~/.fonts_diario")
PDF_PATH     = os.path.join(DIR_REVISTAS, f"{FECHA_STR}.pdf")
FLIP_PATH    = os.path.join(DIR_FLIPBOOK, f"{FECHA_STR}.html")

os.makedirs(DIR_REVISTAS, exist_ok=True)
os.makedirs(DIR_FLIPBOOK, exist_ok=True)
os.makedirs(DIR_FUENTES,  exist_ok=True)

# -- Colores (Manual de Estilo Diario Info) --
AZUL_INST  = (0/255,   51/255,  102/255)   # #003366 institucional
NARANJA_C  = (244/255, 124/255,  32/255)   # #F47C20 corporativo
GRIS_TXT   = (85/255,   85/255,  85/255)   # #555555 texto gris oscuro
GRIS_N     = (102/255, 102/255, 102/255)   # #666666 gris neutro
GRIS_L     = (204/255, 204/255, 204/255)   # #CCCCCC gris claro lineas
GRIS_BG    = (0.93,    0.93,    0.93  )   # fondo gris suave
NEGRO      = (0.0,     0.0,     0.0   )   # #000000
BLANCO     = (1.0,     1.0,     1.0   )   # #FFFFFF
# Aliases de compatibilidad
AZUL       = AZUL_INST
NARANJA    = NARANJA_C
GRIS       = GRIS_TXT
GRIS_C     = GRIS_N

# -- Fuentes --
FUENTES_OK = set()
FONT_TB   = "Helvetica-Bold"    # Lato-Bold cuando disponible
FONT_T    = "Helvetica"         # Lato-Regular cuando disponible
FONT_N    = "Helvetica"         # Lato-Regular
FONT_MBold = "Helvetica-Bold"   # Merriweather-Bold cuando disponible
FONT_MReg  = "Helvetica"        # Merriweather-Regular cuando disponible
FONT_BN    = "Helvetica-Bold"   # Bebas Neue cuando disponible

URLS_FUENTES = {
    "Lato-Regular":        "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "Lato-Bold":           "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Lato-Italic":         "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf",
    "Merriweather-Bold":   "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/merriweather/static/Merriweather-Bold.ttf",
    "Merriweather-Regular":"https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/merriweather/static/Merriweather-Regular.ttf",
    "BebasNeue":            "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
}

# -- Variables globales --
db_global  = None
cat_cache  = {}

def instalar_fuentes():
    global FONT_TB, FONT_T, FONT_N, FONT_MBold, FONT_MReg, FUENTES_OK
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for nombre, url in URLS_FUENTES.items():
        ruta = os.path.join(DIR_FUENTES, nombre + ".ttf")
        if not os.path.exists(ruta):
            try:
                urllib.request.urlretrieve(url, ruta)
            except Exception as e:
                print(f"  Error descargando {nombre}: {e}")
                continue
        try:
            pdfmetrics.registerFont(TTFont(nombre, ruta))
            FUENTES_OK.add(nombre)
        except Exception as e:
            print(f"  Error registrando {nombre}: {e}")
    if "Lato-Bold"             in FUENTES_OK: FONT_TB    = "Lato-Bold"
    if "Lato-Regular"          in FUENTES_OK: FONT_T     = "Lato-Regular"; FONT_N = "Lato-Regular"
    if "Merriweather-Bold"     in FUENTES_OK: FONT_MBold = "Merriweather-Bold"
    if "Merriweather-Regular"  in FUENTES_OK: FONT_MReg  = "Merriweather-Regular"
    if "BebasNeue"             in FUENTES_OK: FONT_BN    = "BebasNeue"
    print(f"Fuentes OK: {FUENTES_OK}")

def conectar_mongo():
    global db_global
    for uri, dbname in [(URI_PRIMARY, DB_PRIMARY), (URI_FALLBACK, DB_FALLBACK)]:
        try:
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10000)
            client.server_info()
            db_global = client[dbname]
            print(f"MongoDB conectado: {dbname}")
            return db_global
        except Exception as e:
            print(f"  Fallo {dbname}: {e}")
    raise RuntimeError("No se pudo conectar a MongoDB")

def obtener_nombre_categoria(cat_id):
    """Obtiene el nombre de la categoria desde la coleccion categories"""
    if not cat_id or db_global is None: return "GENERAL"
    cat_str = str(cat_id)
    if cat_str in cat_cache: return cat_cache[cat_str]
    try:
        c = db_global["categories"].find_one({"_id": ObjectId(cat_str)})
        if c:
            nombre = c.get("name") or c.get("title") or c.get("label") or "GENERAL"
            cat_cache[cat_str] = nombre.upper()
            return nombre.upper()
    except Exception:
        pass
    # Si no es ObjectId valido, devolver como string
    if len(cat_str) < 30:
        cat_cache[cat_str] = cat_str.upper()
        return cat_str.upper()
    return "GENERAL"

def obtener_url_imagen(image_id, pub_date=None):
    """Construye URL de imagen desde MongoDB.
    raw_url en DB: /uploads/TIMESTAMP-filename.ext
    URL real: https://api.diarioinfo.com/uploads/TIMESTAMP-filename.ext
    """
    if not image_id or db_global is None: return ""
    try:
        f = db_global["files"].find_one({"_id": ObjectId(str(image_id))})
        if f:
            raw_url = f.get("fileUrl") or f.get("url") or f.get("filename") or ""
            if not raw_url: return ""
            # raw_url es: /uploads/2026-07-01T23-12-04-699Z-belgica.jpg
            # URL real: https://api.diarioinfo.com/uploads/2026-07-01T23-12-04-699Z-belgica.jpg
            if raw_url.startswith('/uploads/'):
                # URL encode para nombres con espacios
                encoded = urllib.parse.quote(raw_url, safe='/:')
                return "https://api.diarioinfo.com" + encoded
            if raw_url.startswith('http'):
                return raw_url
            # Fallback: asumir que es solo el filename
            return "https://api.diarioinfo.com/uploads/" + urllib.parse.quote(raw_url, safe='')
    except Exception as e:
        print(f"  Error imagen {image_id}: {e}")
    return ""

def obtener_notas(limite=15):
    """Obtiene notas: busca hoy + ayer (ajuste UTC-3), fallback 5 dias"""
    db = db_global
    # Ajuste timezone AR (UTC-3): buscar desde ayer a las 21hs UTC = hoy 00hs AR
    hoy_fin    = datetime(HOY.year, HOY.month, HOY.day, 23, 59, 59)
    ayer_inicio = datetime(HOY.year, HOY.month, HOY.day, 0, 0, 0) - timedelta(days=1)

    cursor = db["articles"].find(
        {"status": "published", "publicationDate": {"$gte": ayer_inicio, "$lte": hoy_fin}}
    ).sort([("publicationDate", -1)]).limit(limite * 3)
    notas = list(cursor)

    if len(notas) < limite:
        cinco_dias = ayer_inicio - timedelta(days=4)
        cursor2 = db["articles"].find(
            {"status": "published", "publicationDate": {"$gte": cinco_dias, "$lte": hoy_fin}}
        ).sort([("publicationDate", -1)]).limit(limite * 3)
        notas = list(cursor2)
    
    result = []
    for n in notas:
        _raw_img = n.get("image", "") or ""
        _pub_date = n.get("publicationDate", HOY)
        if _raw_img and str(_raw_img).startswith("http") and "ia.diarioinfo.com" not in str(_raw_img):
            img_url = _raw_img
        else:
            img_url = obtener_url_imagen(n.get("imageId") or n.get("image"), pub_date=_pub_date)
        cat_name = obtener_nombre_categoria(n.get("category"))
        _slug = n.get("slug", "") or n.get("seoSlug", "") or ""
        _nid  = str(n.get("_id", ""))
        _url  = f"https://www.diarioinfo.com/nota/{_slug}" if _slug else f"https://www.diarioinfo.com/nota/{_nid}"
        result.append({
            "title":    limpiar_html(n.get("title", "")),
            "excerpt":  limpiar_html(n.get("description") or n.get("excerpt") or ""),
            "content":  limpiar_html(n.get("content", "")),
            "category": cat_name,
            "img_url":  img_url,
            "priority": n.get("priority", 0),
            "date":     n.get("publicationDate", HOY),
            "url":      _url,
        })
    # Reordenar igual que la home:
    # 1. Dia calendario AR (UTC-3) DESC
    # 2. Prioridad DESC dentro del mismo dia
    # 3. publicationDate DESC como desempate
    def _sort_key(r):
        d = r["date"]
        if hasattr(d, 'hour'):
            ar = d - timedelta(hours=3)
        else:
            ar = d
        dia = (ar.year, ar.month, ar.day) if hasattr(ar, 'year') else (0, 0, 0)
        prio = r.get("priority", 0) or 0
        ts = r["date"].timestamp() if hasattr(r["date"], 'timestamp') else 0
        return (-dia[0], -dia[1], -dia[2], -prio, -ts)
    result.sort(key=_sort_key)
    result = result[:limite]
    print(f"Notas obtenidas: {len(result)}")
    for i, r in enumerate(result[:4]):
        print(f"  {i}: [{r['priority']}] [{r['category']}] {r['date'].strftime('%d/%m %H:%M') if hasattr(r['date'],'strftime') else str(r['date'])[:10]} - {r['title'][:40]}")
        print(f"       img={r['img_url'][:60] if r['img_url'] else 'NONE'}")
    return result

# ── Helpers texto ───────────────────────────────────────────────────────────────
def limpiar_html(texto):
    if not texto: return ""
    t = str(texto)
    # Preservar saltos de parrafo antes de limpiar HTML
    t = re.sub(r'</p>\s*<p[^>]*>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</?p[^>]*>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html.unescape(t)
    # Colapsar espacios pero NO los saltos de linea
    lineas = [re.sub(r' +', ' ', ln).strip() for ln in t.split('\n')]
    return '\n'.join(l for l in lineas if l)

def wrap_lines(c, texto, ancho, fuente, tamanio):
    """Divide texto en lineas que entran en el ancho dado"""
    if not texto: return []
    c.setFont(fuente, tamanio)
    palabras = texto.split()
    lineas = []
    linea = ""
    for p in palabras:
        prueba = (linea + " " + p).strip()
        if c.stringWidth(prueba, fuente, tamanio) <= ancho:
            linea = prueba
        else:
            if linea: lineas.append(linea)
            linea = p
    if linea: lineas.append(linea)
    return lineas

def draw_text_left(c, texto, x, y, ancho, fuente, pts, color, max_lineas=99, lh=None):
    if not texto: return y
    if lh is None: lh = pts * 1.3
    c.setFont(fuente, pts); c.setFillColorRGB(*color)
    lineas = wrap_lines(c, texto, ancho, fuente, pts)
    for i, l in enumerate(lineas[:max_lineas]):
        c.drawString(x, y - i * lh, l)
    return y - min(len(lineas), max_lineas) * lh

def draw_text_center(c, texto, cx, y, ancho, fuente, pts, color, max_lineas=99, lh=None):
    if not texto: return y
    if lh is None: lh = pts * 1.35
    c.setFont(fuente, pts); c.setFillColorRGB(*color)
    lineas = wrap_lines(c, texto, ancho, fuente, pts)
    for i, l in enumerate(lineas[:max_lineas]):
        c.drawCentredString(cx, y - i * lh, l)
    return y - min(len(lineas), max_lineas) * lh

# ── Imagenes ────────────────────────────────────────────────────────────────────
def get_image_data(url):
    """Descarga imagen y retorna (ImageReader, width_px, height_px) o (None,0,0)"""
    if not url: return None, 0, 0
    url = str(url)
    # Lista de URLs a intentar (con variantes de extension)
    urls_to_try = [url]
    if '.' in url.split('/')[-1]:
        stem_url = url.rsplit('.', 1)[0]
        ext = url.rsplit('.', 1)[1].lower()
        for alt_ext in ['avif', 'webp', 'jpg', 'jpeg', 'jfif', 'png']:
            if alt_ext != ext:
                urls_to_try.append(stem_url + '.' + alt_ext)
    # Tambien probar con fecha de ayer (imagen puede estar en carpeta del dia anterior)
    if 'sistema/entidades/' in url:
        from datetime import timedelta as _td
        ayer = (HOY - _td(days=1)).strftime("%d-%m-%Y")
        anteayer = (HOY - _td(days=2)).strftime("%d-%m-%Y")
        fname_only = url.split('/')[-1]
        for alt_date in [ayer, anteayer]:
            base_ayer = url.split('sistema/entidades/')[0] + 'sistema/entidades/' + alt_date + '/'
            urls_to_try.append(base_ayer + fname_only)
            # Y variantes de extension con fecha anterior
            if '.' in fname_only:
                stem_f = fname_only.rsplit('.', 1)[0]
                for alt_ext in ['webp', 'jpg', 'jpeg', 'png']:
                    urls_to_try.append(base_ayer + stem_f + '.' + alt_ext)
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://www.diarioinfo.com/",
        "Accept": "image/webp,image/jpeg,image/*,*/*;q=0.8"
    }
    for try_url in urls_to_try:
        try:
            print(f"  [img] Descargando: {try_url[:90]}")
            req  = urllib.request.Request(try_url, headers=headers)
            data = urllib.request.urlopen(req, timeout=15).read()
            # Convertir con Pillow si es necesario (avif, jfif, etc.)
            # y redimensionar si es demasiado grande (max 1800px)
            try:
                from PIL import Image as _PILImage
                _img = _PILImage.open(io.BytesIO(data)).convert('RGB')
                _max = 1800
                if _img.width > _max or _img.height > _max:
                    _img.thumbnail((_max, _max), _PILImage.LANCZOS)
                _buf = io.BytesIO()
                _img.save(_buf, format='JPEG', quality=82)
                _buf.seek(0)
                ir = ImageReader(_buf)
                iw, ih = ir.getSize()
            except Exception:
                ir = ImageReader(io.BytesIO(data))
                iw, ih = ir.getSize()
            print(f"  [img OK] {iw}x{ih} desde {try_url[:60]}")
            return ir, iw, ih
        except Exception as e:
            print(f"  [img ERR] {try_url[:80]}: {str(e)[:60]}")
    return None, 0, 0

def draw_image_bleed(c, ir, iw, ih, box_x, box_y, box_w, box_h):
    """Dibuja imagen con SANGRADO: escala al factor mayor para cubrir
    todo el box sin bordes blancos. Recorte centrado con clipPath."""
    if ir is None or iw == 0 or ih == 0:
        c.setFillColorRGB(*GRIS_BG)
        c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=0)
        return
    sc_w = float(box_w) / iw   # factor para cubrir ancho
    sc_h = float(box_h) / ih   # factor para cubrir alto
    sc   = max(sc_w, sc_h)     # sangrado: usar el MAYOR
    dw   = iw * sc
    dh   = ih * sc
    ox   = (dw - box_w) / 2.0  # excedente centrado x
    oy   = (dh - box_h) / 2.0  # excedente centrado y
    c.saveState()
    clip = c.beginPath()
    clip.rect(box_x, box_y, box_w, box_h)
    c.clipPath(clip, stroke=0)
    c.drawImage(ir, box_x - ox, box_y - oy, dw, dh)
    c.restoreState()

def draw_image_fit(c, ir, iw, ih, box_x, box_y, box_w, box_h):
    """Dibuja imagen con FIT: escala para que quepa completa dentro del box."""
    if ir is None or iw == 0 or ih == 0:
        c.setFillColorRGB(*GRIS_BG)
        c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=0)
        return
    sc_w = float(box_w) / iw
    sc_h = float(box_h) / ih
    sc   = min(sc_w, sc_h)   # fit: usar el MENOR
    dw   = iw * sc
    dh   = ih * sc
    dx   = box_x + (box_w - dw) / 2.0
    dy   = box_y + (box_h - dh) / 2.0
    c.drawImage(ir, dx, dy, dw, dh)

def draw_image(c, url, x, y, w, h):
    """Compatibilidad: descarga y dibuja con sangrado (bleed)"""
    ir, iw, ih = get_image_data(url)
    draw_image_bleed(c, ir, iw, ih, x, y, w, h)

def draw_logo(c, cx_icon, cy_icon, r=18, escala=1.0):
    import math
    r = r * escala
    # Mitad izquierda AZUL
    c.setFillColorRGB(*AZUL)
    p = c.beginPath()
    for i in range(181):
        ang = math.radians(90 + i)
        px, py = cx_icon + r*math.cos(ang), cy_icon + r*math.sin(ang)
        if i == 0: p.moveTo(px, py)
        else:      p.lineTo(px, py)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    # Mitad derecha NARANJA
    c.setFillColorRGB(*NARANJA)
    p2 = c.beginPath()
    for i in range(181):
        ang = math.radians(270 + i)
        px, py = cx_icon + r*math.cos(ang), cy_icon + r*math.sin(ang)
        if i == 0: p2.moveTo(px, py)
        else:      p2.lineTo(px, py)
    p2.close()
    c.drawPath(p2, fill=1, stroke=0)
    # Triangulo BLANCO (play)
    c.setFillColorRGB(*BLANCO)
    size = r * 0.65
    px0 = cx_icon - size * 0.3
    p3 = c.beginPath()
    p3.moveTo(px0 - size*0.5, cy_icon + size*0.55)
    p3.lineTo(px0 - size*0.5, cy_icon - size*0.55)
    p3.lineTo(px0 + size*0.65, cy_icon)
    p3.close()
    c.drawPath(p3, fill=1, stroke=0)
    # Texto logo
    sx = cx_icon + r + 3*escala
    fs_d = int(26 * escala)
    fs_i = int(28 * escala)
    fs_c = int(13 * escala)
    base_y = cy_icon - fs_d * 0.38
    c.setFont(FONT_TB, fs_d); c.setFillColorRGB(*AZUL)
    c.drawString(sx, base_y, "diario")
    wd = c.stringWidth("diario", FONT_TB, fs_d)
    c.setFont(FONT_TB, fs_i); c.setFillColorRGB(*NARANJA)
    c.drawString(sx + wd, base_y - 1, "info")
    wi = c.stringWidth("info", FONT_TB, fs_i)
    c.setFont(FONT_T, fs_c); c.setFillColorRGB(*GRIS)
    c.drawString(sx + wd + wi, base_y + 2, ".com")
    return sx + wd + wi + c.stringWidth(".com", FONT_T, fs_c)

# ── Cotizaciones y Clima ────────────────────────────────────────────────────────
def obtener_cotizaciones():
    import json, subprocess
    # API 1: bluelytics
    try:
        req = urllib.request.urlopen("https://api.bluelytics.com.ar/v2/latest", timeout=8)
        data = json.loads(req.read())
        of = data.get("oficial", {}).get("value_sell", 0)
        bl = data.get("blue", {}).get("value_sell", 0)
        if of and bl:
            return f"Oficial: ${of:,.0f}", f"Blue: ${bl:,.0f}"
    except Exception as e1:
        print(f"  [cotiz] bluelytics fallo: {e1}")
    # API 2: dolarapi.com
    try:
        r2 = urllib.request.urlopen("https://dolarapi.com/v1/dolares/oficial", timeout=8)
        r3 = urllib.request.urlopen("https://dolarapi.com/v1/dolares/blue", timeout=8)
        d2 = json.loads(r2.read()); d3 = json.loads(r3.read())
        of2 = d2.get("venta", 0); bl2 = d3.get("venta", 0)
        if of2 and bl2:
            return f"Oficial: ${of2:,.0f}", f"Blue: ${bl2:,.0f}"
    except Exception as e2:
        print(f"  [cotiz] dolarapi fallo: {e2}")
    # API 3: via curl
    try:
        rc = subprocess.run(["curl","-sf","--max-time","8","https://api.bluelytics.com.ar/v2/latest"], capture_output=True, timeout=10)
        if rc.returncode == 0 and rc.stdout:
            data3 = json.loads(rc.stdout)
            of3 = data3.get("oficial", {}).get("value_sell", 0)
            bl3 = data3.get("blue", {}).get("value_sell", 0)
            if of3 and bl3:
                return f"Oficial: ${of3:,.0f}", f"Blue: ${bl3:,.0f}"
    except Exception as e3:
        print(f"  [cotiz] curl fallo: {e3}")
    return "Oficial: ---", "Blue: ---"
def obtener_clima():
    """Obtiene temperatura en Celsius"""
    try:
        # format: %C = condicion, %t = temperatura (con -m da Celsius)
        url = "https://wttr.in/Santiago+del+Estero,Argentina?format=%c+%t&m"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        resp = urllib.request.urlopen(req, timeout=8)
        datos = resp.read().decode("utf-8").strip()
        datos = datos.replace("+", "").strip()
        return f"Santiago del Estero {datos}"
    except:
        return "Santiago del Estero"

# ── TAPA ─────────────────────────────────────────────────────────────────────────
def draw_icon(c, cx_icon, cy_icon, r_icon, escala=1.0):
    """Dibuja el icono circular bicolor (izq azul, der naranja) con triangulo blanco."""
    import math
    r = r_icon * escala
    # Mitad izquierda AZUL
    c.setFillColorRGB(*AZUL_INST)
    p = c.beginPath()
    for i in range(181):
        ang = math.radians(90 + i)
        px, py = cx_icon + r*math.cos(ang), cy_icon + r*math.sin(ang)
        if i == 0: p.moveTo(px, py)
        else:      p.lineTo(px, py)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    # Mitad derecha NARANJA
    c.setFillColorRGB(*NARANJA_C)
    p2 = c.beginPath()
    for i in range(181):
        ang = math.radians(270 + i)
        px, py = cx_icon + r*math.cos(ang), cy_icon + r*math.sin(ang)
        if i == 0: p2.moveTo(px, py)
        else:      p2.lineTo(px, py)
    p2.close()
    c.drawPath(p2, fill=1, stroke=0)
    # Triangulo BLANCO (play)
    c.setFillColorRGB(*BLANCO)
    size = r * 0.65
    px0  = cx_icon - size * 0.3
    p3   = c.beginPath()
    p3.moveTo(px0 - size*0.5, cy_icon + size*0.55)
    p3.lineTo(px0 - size*0.5, cy_icon - size*0.55)
    p3.lineTo(px0 + size*0.65, cy_icon)
    p3.close()
    c.drawPath(p3, fill=1, stroke=0)



def draw_cabecera(c, W, H, M, num_pag=None, cotiz_of="", cotiz_bl="", clima=""):
    """Dibuja cabecera: fecha/clima/cotiz centrado. Si num_pag, incluye numero de pagina."""
    DIAS_ES  = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
    MESES_ES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    dia_semana = DIAS_ES[HOY.weekday()]
    mes        = MESES_ES[HOY.month - 1]
    fecha_txt  = f"{dia_semana} {HOY.day} de {mes} de {HOY.year}"
    cli_txt    = f"{clima}" if clima else ""
    cot_txt    = ""
    if cotiz_of: cot_txt += f"  |  {cotiz_of}"
    if cotiz_bl: cot_txt += f"  |  {cotiz_bl}"
    if num_pag:
        cab_line = f"{fecha_txt}  |  Santiago del Estero  |  diarioinfo.com  |  Pag. {num_pag}"
    elif cli_txt:
        cab_line = f"{fecha_txt}  |  {cli_txt}{cot_txt}"
    else:
        cab_line = f"{fecha_txt}  |  Santiago del Estero{cot_txt}"
    c.setFont(FONT_T, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawCentredString(W/2, H - 6*mm, cab_line)


def draw_pie(c, W, M, pie_y):
    """Dibuja pie de pagina con linea divisoria."""
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, pie_y + 4*mm, W - M, pie_y + 4*mm)
    c.setFont(FONT_T, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawString(M, pie_y, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, pie_y, "Edicion Impresa  -  Santiago del Estero")


def draw_categoria_banda(c, cat, x, y, w, font_ui_b):
    """Dibuja banda de categoria: fondo azul + texto blanco."""
    safe_cat = (cat or "GENERAL").encode('ascii','replace').decode('ascii')[:25]
    c.setFillColorRGB(*AZUL_INST)
    c.rect(x, y, w, 5*mm, fill=1, stroke=0)
    c.setFont(font_ui_b, 8)
    c.setFillColorRGB(*BLANCO)
    c.drawString(x + 2*mm, y + 1.3*mm, safe_cat)


def wrap_paragraphs(c, texto, ancho, fuente, pts):
    """Divide texto en lineas respetando parrafos.
    Devuelve lista de (linea, es_inicio_parrafo)."""
    if not texto: return []
    result = []
    # Separar por punto y aparte: punto seguido de 2+ espacios o salto de linea
    import re as _re2
    parrafos = _re2.split(r'\n', texto)
    parrafos = [p.strip() for p in parrafos if p.strip()]
    if len(parrafos) <= 1:
        parrafos = _re2.split(r'\. {2,}|\n\n+', texto)
    if len(parrafos) <= 1:
        parrafos = [texto]
    for ip, parr in enumerate(parrafos):
        parr = parr.strip()
        if not parr: continue
        lineas = wrap_lines(c, parr, ancho, fuente, pts)
        for il, ln in enumerate(lineas):
            result.append((ln, il == 0 and ip > 0))
    return result

def draw_cuerpo_2col(c, cuerpo, x_l1, x_l2, y_start, y_end, col_w, font_body, pts_body, lh_body):
    """Dibuja cuerpo en 2 columnas con separador central. Respeta parrafos.
    Devuelve True si el cuerpo no cabia completo."""
    if not cuerpo: return False
    indent = 3*mm  # sangria de parrafo
    todas = wrap_paragraphs(c, cuerpo, col_w - 2*mm, font_body, pts_body)
    half  = max(1, len(todas) // 2)
    col1  = todas[:half]
    col2  = todas[half:]
    # Separador vertical central
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line((x_l1 + col_w + x_l2) / 2, y_start, (x_l1 + col_w + x_l2) / 2, y_end)
    desborde = False
    min_cy = y_start  # rastrea hasta donde llego el texto
    for col_i, col_lines in enumerate([(col1, x_l1), (col2, x_l2)]):
        lineas, cx = col_lines
        cy = y_start
        c.setFont(font_body, pts_body)
        c.setFillColorRGB(*NEGRO)
        for ln, es_parr in lineas:
            if cy < y_end:
                desborde = True
                break
            dx = indent if es_parr else 0
            if es_parr: cy -= lh_body * 0.4  # espacio entre parrafos
            c.drawString(cx + dx, cy, ln)
            cy -= lh_body
            if cy < min_cy: min_cy = cy
    return desborde, min_cy


def generar_tapa(c, notas, cotiz_of, cotiz_bl, clima):
    """Tapa v3.20 - Layout adaptativo estricto:
       Layout A: ratio>=1.5 -> foto 2 columnas full-width, titulo completo debajo
       Layout B: ratio<1.5  -> foto 1 columna izq, titulo completo 1 columna der al mismo Y
    """
    W, H = A4
    M    = 15*mm
    COL2 = (W - 2*M) / 2

    FUI_R = FONT_T
    FUI_B = FONT_TB
    FTI_B = FONT_MBold   # Merriweather-Bold para titulares
    FTI_R = FONT_MReg
    TIT_PTS   = 22        # titulos tapa principal
    TIT_SEC   = TIT_PTS - 6  # titulos notas secundarias (6pt menos)
    TIT_LH    = TIT_PTS * 1.2 * 0.3528 * mm
    TIT_SEC_LH = TIT_SEC * 1.2 * 0.3528 * mm

    # Fondo blanco
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Cabecera
    draw_cabecera(c, W, H, M, cotiz_of=cotiz_of, cotiz_bl=cotiz_bl, clima=clima)

    # Logo
    cx_icon = W/2 - 28*mm
    cy_icon = H - 22*mm
    r_icon  = 8*mm
    draw_icon(c, cx_icon, cy_icon, r_icon)
    c.setFont(FUI_B, 26)
    dw_d = c.stringWidth("diario", FUI_B, 26)
    dw_i = c.stringWidth("info",   FUI_B, 26)
    tx2  = W/2 - 22*mm
    c.setFillColorRGB(*AZUL_INST)
    c.drawString(tx2, cy_icon - 4*mm, "diario")
    c.setFillColorRGB(*NARANJA_C)
    c.drawString(tx2 + dw_d, cy_icon - 4*mm, "info")
    c.setFont(FUI_R, 14)
    c.setFillColorRGB(*GRIS_N)
    c.drawString(tx2+dw_d+dw_i, cy_icon - 4*mm - 1*mm, ".com")
    c.setFont(FUI_R, 10)
    c.setFillColorRGB(*GRIS_N)
    c.drawCentredString(W/2, H - 38*mm, "Santiago del Estero")

    # Filete doble
    Y_FIL = H - 43*mm
    c.setStrokeColorRGB(*AZUL_INST)
    c.setLineWidth(1.5)
    c.line(M, Y_FIL, W - M, Y_FIL)
    c.setStrokeColorRGB(*NARANJA_C)
    c.setLineWidth(0.8)
    c.line(M, Y_FIL - 1.5*mm, W - M, Y_FIL - 1.5*mm)

    # Zona editorial
    nota_p   = notas[0] if notas else None
    Y_EDIT   = Y_FIL - 3*mm
    PIE_H    = 14*mm
    SEC_H    = 98.4*mm
    Y_SEC_TOP = PIE_H + SEC_H - 10*mm

    if nota_p:
        titulo  = limpiar_html(nota_p.get("title", ""))
        bajada  = limpiar_html(nota_p.get("excerpt") or nota_p.get("content", ""))
        img_url = nota_p.get("img_url", "")
        cat     = nota_p.get("category", "GENERAL")
        print(f"  [tapa] img_url principal: {img_url[:100]}")

        ir_p, iw_p, ih_p = get_image_data(img_url)
        ratio_p = (iw_p / ih_p) if ih_p > 0 else 0

        # ── LAYOUT A: ratio >= 1.45 (apaisada 3:2, 16:9) ────────────────────────
        # Foto ocupa las 2 columnas (ancho completo de pagina)
        # Titulo completo debajo de la foto
        if ratio_p >= 1.45:
            IMG_W  = W               # full bleed
            IMG_H  = IMG_W * (9.0/16.0)
            IMG_X  = 0
            IMG_TOP = Y_EDIT - 2*mm
            IMG_BOT = IMG_TOP - IMG_H
            draw_image_bleed(c, ir_p, iw_p, ih_p, IMG_X, IMG_BOT, IMG_W, IMG_H)


            # Titulo completo debajo de imagen (sin limite de lineas)
            ty = IMG_BOT - 16*mm
            c.setFont(FTI_B, TIT_PTS)
            c.setFillColorRGB(*NEGRO)
            for ln in wrap_lines(c, titulo, W - 2*M, FTI_B, TIT_PTS):
                if ty < Y_SEC_TOP + 3*mm: break
                c.drawCentredString(W/2, ty, ln)
                ty -= TIT_LH

            # Bajada
            ty -= 2*mm
            c.setFont(FTI_R, 10)
            c.setFillColorRGB(*GRIS_TXT)
            for bl_ln in wrap_lines(c, bajada, W - 4*M, FTI_R, 10)[:2]:
                if ty < Y_SEC_TOP + 2*mm: break
                c.drawCentredString(W/2, ty, bl_ln)
                ty -= 5*mm

            # Separador
            c.setStrokeColorRGB(*GRIS_L)
            c.setLineWidth(0.5)
            c.line(M, ty - (2*mm- 5*mm), W - M, ty - (2*mm- 5*mm))

        # ── LAYOUT B: ratio < 1.5 (vertical, cuadrada, 4:3, 9:16) ──────────────
        # Foto en 1 columna izq, titulo completo en columna der al mismo Y
        else:
            area_h  = Y_EDIT - Y_SEC_TOP
            IMG_W   = COL2 - 3*mm
            IMG_H   = min(area_h - 20*mm, IMG_W * (4.0/3.0))
            IMG_X   = M
            IMG_TOP = Y_EDIT - 2*mm
            IMG_BOT = IMG_TOP - IMG_H
            draw_image_bleed(c, ir_p, iw_p, ih_p, IMG_X, IMG_BOT, IMG_W, IMG_H)

            # Titulo columna derecha, arranca al mismo Y que la foto (alineado top)
            TIT_X = M + COL2 + 3*mm
            TIT_W = (W - M) - TIT_X     # ancho disponible hasta margen derecho
            ty    = IMG_TOP - TIT_LH     # baseline primera linea = top imagen
            # (sin categoria en nota de 1 columna - Layout B)
            c.setFont(FTI_B, TIT_PTS)
            c.setFillColorRGB(*NEGRO)
            for ln in wrap_lines(c, titulo, TIT_W, FTI_B, TIT_PTS):
                if ty < IMG_BOT - 5*mm: break
                c.drawString(TIT_X, ty, ln)
                ty -= TIT_LH

            # Bajada ancho completo debajo de imagen
            by = IMG_BOT - 5*mm
            c.setFont(FTI_R, 10)
            c.setFillColorRGB(*GRIS_TXT)
            for bl_ln in wrap_lines(c, bajada, W - 2*M, FTI_R, 10)[:2]:
                if by < Y_SEC_TOP + 2*mm: break
                c.drawCentredString(W/2, by, bl_ln)
                by -= 5*mm

            # Separador
            c.setStrokeColorRGB(*GRIS_L)
            c.setLineWidth(0.5)
            c.line(M, by - 4*mm, W - M, by - 4*mm)

    # ── NOTAS SECUNDARIAS: 3 columnas ───────────────────────────────────────────
    notas_sec = notas[1:4]
    col_n  = 3
    col_w  = (W - 2*M) / col_n
    sec_bot = PIE_H + 3*mm
    pad    = 3*mm
    img_h_sec = col_w * 0.50

    for i, ns in enumerate(notas_sec):
        cx = M + i * col_w
        # Separador vertical
        if i < col_n - 1:
            c.setStrokeColorRGB(*GRIS_L)
            c.setLineWidth(0.5)
            c.line(M + (i+1)*col_w, Y_SEC_TOP - 6.5*mm, M + (i+1)*col_w, sec_bot)
        # Imagen
        img_url_s = ns.get("img_url", "")
        img_x_s   = cx + pad
        img_w_s   = col_w - 2*pad
        img_top_s = Y_SEC_TOP - 7*mm
        ir_s, iw_s, ih_s = get_image_data(img_url_s)
        draw_image_bleed(c, ir_s, iw_s, ih_s, img_x_s, img_top_s - img_h_sec, img_w_s, img_h_sec)
        # Categoria encima de imagen (dibujada despues para ser visible)
        cat_s = ns.get("category", "GENERAL")
        draw_categoria_banda(c, cat_s, img_x_s, img_top_s - img_h_sec + 1*mm, img_w_s * 0.55, FUI_B)
        # Titulo completo (4pt menos que principal)
        tit_s = limpiar_html(ns.get("title", ""))
        ty_s  = img_top_s - img_h_sec - 6.5*mm
        c.setFont(FTI_B, TIT_SEC)
        c.setFillColorRGB(*NEGRO)
        for tsl in wrap_lines(c, tit_s, col_w - 2*pad, FTI_B, TIT_SEC):
            c.drawString(cx + pad, ty_s, tsl)
            ty_s -= TIT_SEC_LH

    # Pie
    draw_pie(c, W, M, PIE_H - 6*mm)


def generar_pagina_interior(c, nota, num_pag):
    """Pagina interior v3.20 - Layout adaptativo:
       Layout A: ratio>=1.5 -> foto full-width 2col, titulo centrado debajo, cuerpo 2col
       Layout B: ratio<1.5  -> foto col izq + titulo col der al mismo Y, cuerpo 2col debajo
       Regla: titulo siempre completo. Si el cuerpo no entra, agrega leyenda al final.
    """
    W, H = A4
    M    = 15*mm
    COL2 = (W - 2*M) / 2

    FUI_R = FONT_T
    FUI_B = FONT_TB
    FTI_B = FONT_MBold
    FTI_R = FONT_MReg
    TIT_PTS  = 22
    TIT_LH   = TIT_PTS * 1.2 * 0.3528 * mm
    BODY_PTS = 10
    BODY_LH  = BODY_PTS * 1.4 * 0.3528 * mm

    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Cabecera
    draw_cabecera(c, W, H, M, num_pag=num_pag)

    # Banda categoria
    cat = nota.get("category", "GENERAL")
    Y_BANDA = H - 9*mm - 7*mm
    draw_categoria_banda(c, cat, M, Y_BANDA, W - 2*M, FUI_B)

    # Datos nota
    titulo  = limpiar_html(nota.get("title", ""))
    bajada  = limpiar_html(nota.get("excerpt") or nota.get("content", ""))
    cuerpo  = limpiar_html(nota.get("content", ""))
    img_url = nota.get("img_url", "")
    print(f"  [pagina] img_url: {img_url[:100]}")

    ir_n, iw_n, ih_n = get_image_data(img_url)
    ratio_n = (iw_n / ih_n) if ih_n > 0 else 0

    Y_CONT = Y_BANDA - 3*mm
    PIE_Y  = 18*mm
    CUERPO_Y = PIE_Y + 6*mm

    # ── LAYOUT A: ratio >= 1.45 (apaisada 3:2, 16:9) ──────────────────────────
    if ratio_n >= 1.45:
        IMG_W  = W
        IMG_H  = IMG_W * (9.0/16.0)
        IMG_X  = 0
        IMG_TOP = Y_CONT - 2*mm
        IMG_BOT = IMG_TOP - IMG_H
        draw_image_bleed(c, ir_n, iw_n, ih_n, IMG_X, IMG_BOT, IMG_W, IMG_H)

        # Titulo completo centrado debajo
        ty = IMG_BOT - 14*mm
        c.setFont(FTI_B, TIT_PTS)
        c.setFillColorRGB(*NEGRO)
        for ln in wrap_lines(c, titulo, W - 2*M, FTI_B, TIT_PTS):
            if ty < CUERPO_Y + 40*mm: break
            c.drawCentredString(W/2, ty, ln)
            ty -= TIT_LH

        # Bajada
        ty -= 2*mm
        c.setFont(FTI_R, 10)
        c.setFillColorRGB(*GRIS_TXT)
        for bl_ln in wrap_lines(c, bajada, W - 4*M, FTI_R, 10)[:3]:
            if ty < CUERPO_Y + 30*mm: break
            c.drawCentredString(W/2, ty, bl_ln)
            ty -= 5*mm

        cuerpo_start = ty - 4*mm

    # ── LAYOUT B: ratio < 1.5 (vertical, cuadrada, 4:3, 9:16) ───────────────
    else:
        IMG_W  = COL2 - 3*mm
        IMG_H  = min(Y_CONT - CUERPO_Y - 35*mm, IMG_W * (4.0/3.0))
        IMG_X  = M
        IMG_TOP = Y_CONT - 2*mm
        IMG_BOT = IMG_TOP - IMG_H
        draw_image_bleed(c, ir_n, iw_n, ih_n, IMG_X, IMG_BOT, IMG_W, IMG_H)

        # Titulo columna derecha, arranca al mismo Y que la foto (alineado top)
        TIT_X = M + COL2 + 3*mm
        TIT_W = COL2 * 0.75          # 75% del ancho de columna
        ty    = IMG_TOP - TIT_LH     # baseline primera linea = top imagen
        c.setFont(FTI_B, TIT_PTS)
        c.setFillColorRGB(*NEGRO)
        for ln in wrap_lines(c, titulo, TIT_W, FTI_B, TIT_PTS):
            if ty < IMG_BOT - 5*mm: break
            c.drawString(TIT_X, ty, ln)
            ty -= TIT_LH

        # Bajada ancho completo debajo de imagen
        by = IMG_BOT - 5*mm
        c.setFont(FTI_R, 10)
        c.setFillColorRGB(*GRIS_TXT)
        for bl_ln in wrap_lines(c, bajada, W - 2*M, FTI_R, 10)[:3]:
            if by < CUERPO_Y + 25*mm: break
            c.drawCentredString(W/2, by, bl_ln)
            by -= 5*mm

        cuerpo_start = by - 4*mm

    # ── CUERPO: 2 columnas ───────────────────────────────────────────────────
    # Espacio disponible para cuerpo (en mm)
    _espacio_mm = round((cuerpo_start - CUERPO_Y) / mm, 1) if cuerpo_start > CUERPO_Y else 0
    _espacio_total_mm = round((cuerpo_start - (PIE_Y + 6*mm)) / mm, 1) if cuerpo_start > PIE_Y else 0
    print(f"  [ESPACIO-PAG{num_pag}] cuerpo_start={round(cuerpo_start/mm,1)}mm PIE_Y={round(PIE_Y/mm,1)}mm CUERPO_Y={round(CUERPO_Y/mm,1)}mm espacio_cuerpo={_espacio_mm}mm")
    if cuerpo and cuerpo_start > CUERPO_Y + 15*mm:
        col_cw  = COL2 - 4*mm
        x_col1  = M
        x_col2  = M + COL2 + 4*mm
        desborde, _y_fin_texto = draw_cuerpo_2col(
            c, cuerpo,
            x_col1, x_col2,
            cuerpo_start, CUERPO_Y,
            col_cw, FUI_R, BODY_PTS, BODY_LH
        )
        _libre_mm = round((_y_fin_texto - PIE_Y) / mm, 1)
        print(f"  [ESPACIO-PAG{num_pag}] desborde={desborde} y_fin_texto={round(_y_fin_texto/mm,1)}mm espacio_libre_hasta_pie={_libre_mm}mm")
        if desborde:
            c.setFont(FUI_R, 8)
            c.setFillColorRGB(*AZUL_INST)
            _nota_url = nota.get("url", "https://diarioinfo.com")
            _mira_txt = ">> Mira la NOTA completa en nuestro Portal: diarioinfo.com"
            _mira_w   = c.stringWidth(_mira_txt, FUI_R, 8)
            _mira_x   = x_col2 + col_cw - _mira_w
            _mira_y   = PIE_Y + 2*mm
            c.drawString(_mira_x, _mira_y, _mira_txt)
            try:
                c.linkURL(_nota_url, (_mira_x, _mira_y - 2, _mira_x + _mira_w, _mira_y + 8), relative=0)
            except Exception:
                pass  # URL annotation not supported in this ReportLab version

    # Pie
    draw_pie(c, W, M, PIE_Y - 4*mm)


def generar_flipbook(pdf_path, pdf_url, fecha_str, notas):
    """Genera flipbook con efecto de pasar paginas usando StPageFlip + imagenes del PDF."""
    import shutil
    titulo = f"Diario Info - Edicion {fecha_str}"
    flip_dir = os.path.join(DIR_FLIPBOOK, fecha_str)
    os.makedirs(flip_dir, exist_ok=True)

    # -- Convertir paginas del PDF a imagenes JPG usando PyMuPDF (fitz) --
    paginas = []
    try:
        try:
            import fitz
        except ImportError:
            import subprocess, sys as _sys
            subprocess.check_call([_sys.executable, "-m", "pip", "install", "--quiet", "--user", "PyMuPDF"])
            import fitz
        doc = fitz.open(pdf_path)
        mat = fitz.Matrix(1.8, 1.8)  # ~130 DPI
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_name = f"page-{i+1:02d}.jpg"
            img_path = os.path.join(flip_dir, img_name)
            pix.save(img_path)
            paginas.append(img_name)
        doc.close()
        print(f"  Flipbook: {len(paginas)} paginas convertidas")
    except ImportError:
        print("  WARN: PyMuPDF no disponible, flipbook sin imagenes")
    except Exception as e:
        print(f"  WARN flipbook imagenes: {e}")

    # -- Construir links por pagina: pag 1=tapa, pag 2..N = notas[0..N-2] --
    # notas[0] es la nota principal (pag 2), notas[1] pag 3, etc.
    links_js = "const PAGE_LINKS = [null"  # index 0 = tapa, sin link
    for i, nota in enumerate(notas):
        url  = nota.get("url", "")
        titl = nota.get("title", "").replace('"', '').replace("'", "")[:60]
        links_js += f',\n  {{url: "{url}", title: "{titl}"}}'
    links_js += "\n];"

    # -- Thumbnails lateral --
    thumbs_html = ""
    for i, img in enumerate(paginas):
        thumbs_html += f'<div class="thumb" onclick="goPage({i+1})" title="Pagina {i+1}"><img src="{fecha_str}/{img}" loading="lazy"></div>\n'

    # -- Paginas del flipbook --
    pages_html = ""
    for i, img in enumerate(paginas):
        pages_html += f'<div class="page" data-page="{i+1}"><img src="{fecha_str}/{img}" alt="Pagina {i+1}" loading="lazy"></div>\n'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
<script src="https://cdn.jsdelivr.net/npm/page-flip@2.0.7/dist/js/page-flip.browser.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #1a1a2e; font-family: 'Helvetica Neue', sans-serif; color: #fff; display: flex; flex-direction: column; align-items: center; min-height: 100vh; }}
header {{ width: 100%; background: #003366; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; }}
.logo {{ color: #F47C20; font-size: 22px; font-weight: bold; letter-spacing: 1px; }}
.header-date {{ color: #ccc; font-size: 13px; }}
.header-links {{ display: flex; gap: 14px; }}
.header-links a {{ color: #F47C20; text-decoration: none; font-size: 13px; border: 1px solid #F47C20; padding: 4px 10px; border-radius: 4px; }}
.header-links a:hover {{ background: #F47C20; color: #fff; }}
.main-wrap {{ display: flex; width: 100%; max-width: 1200px; gap: 12px; padding: 16px; flex: 1; }}
.thumbs {{ width: 110px; overflow-y: auto; max-height: 80vh; display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }}
.thumb {{ cursor: pointer; border: 2px solid transparent; border-radius: 4px; overflow: hidden; transition: border-color 0.2s; }}
.thumb:hover, .thumb.active {{ border-color: #F47C20; }}
.thumb img {{ width: 100%; display: block; }}
.flip-area {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 12px; }}
#book-container {{ width: 100%; max-width: 960px; height: 70vh; position: relative; }}
.stf__parent {{ width: 100% !important; height: 100% !important; }}
.page img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
.page {{ background: #fff; }}
.controls {{ display: flex; align-items: center; gap: 16px; }}
.controls button {{ background: #003366; color: #fff; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }}
.controls button:hover {{ background: #F47C20; }}
.page-info {{ color: #aaa; font-size: 14px; min-width: 100px; text-align: center; }}
.nota-link {{ position: fixed; background: #F47C20; color: #fff; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 13px; font-weight: bold; box-shadow: 0 3px 12px rgba(0,0,0,0.5); display: none; z-index: 200; transition: background 0.2s; border: 2px solid rgba(255,255,255,0.3); }}
.nota-link:hover {{ background: #d4691a; }}
footer {{ background: #003366; width: 100%; text-align: center; padding: 8px; color: #aaa; font-size: 12px; }}
</style>
</head>
<body>
<header>
  <div class="logo">diarioinfo<span style="color:#fff">.com</span></div>
  <div class="header-date">{titulo}</div>
  <div class="header-links">
    <a href="../revistas/diarioinfo/{fecha_str}.pdf" download>&#8595; PDF</a>
    <a href="index.html">Ediciones</a>
  </div>
</header>
<div class="main-wrap">
  <div class="thumbs" id="thumbs">
{thumbs_html}  </div>
  <div class="flip-area">
    <div id="book-container">
{pages_html}    </div>
    <div class="controls">
      <button onclick="pageFlip.flipPrev()">&#8249; Anterior</button>
      <div class="page-info" id="page-info">Pagina 1 / {len(paginas)}</div>
      <button onclick="pageFlip.flipNext()">Siguiente &#8250;</button>
    </div>
  </div>
</div>
<a class="nota-link" id="nota-link" href="#" target="_blank" rel="noopener">&#128196; Leer nota completa</a>
<footer>www.diarioinfo.com.ar &nbsp;|&nbsp; Edicion Impresa {fecha_str}</footer>
<script>
{links_js}

const totalPages = {len(paginas)};
let currentPage = 1;

function updateUI(page) {{
  currentPage = page;
  document.getElementById('page-info').textContent = 'Pagina ' + page + ' / ' + totalPages;
  // Thumbs
  document.querySelectorAll('.thumb').forEach((t, i) => {{
    t.classList.toggle('active', i + 1 === page);
  }});
  // Scroll thumb into view
  const thumb = document.querySelectorAll('.thumb')[page - 1];
  if (thumb) thumb.scrollIntoView({{behavior:'smooth', block:'nearest'}});
  const link = document.getElementById('nota-link');
  const info = PAGE_LINKS[page - 1];
  if (info && info.url) {{
    link.href = info.url;
    link.innerHTML = '&#128279; Mira la NOTA completa &rarr; diarioinfo.com';
    const book = document.getElementById('book-container');
    if (book) {{
      const rect = book.getBoundingClientRect();
      const pageW = rect.width / 2;
      const linkLeft = rect.left + pageW * 0.35;
      const linkBottom = window.innerHeight - rect.bottom + 22;
      link.style.left = linkLeft + 'px';
      link.style.bottom = linkBottom + 'px';
      link.style.right = 'auto';
    }}
    link.style.display = 'block';
  }} else {{
    link.style.display = 'none';
  }}
}}

function goPage(n) {{
  pageFlip.turnToPage(n - 1);
}}

const pageFlip = new St.PageFlip(document.getElementById('book-container'), {{
  width: 480, height: 680,
  size: 'stretch',
  minWidth: 200, maxWidth: 960,
  minHeight: 300, maxHeight: 900,
  showCover: true,
  useMouseEvents: true,
  drawShadow: true,
  flippingTime: 700,
  usePortrait: true,
  startPage: 0,
  autoSize: true,
}});

pageFlip.loadFromHTML(document.querySelectorAll('.page'));

pageFlip.on('flip', (e) => {{
  updateUI(e.data + 1);
}});

updateUI(1);
</script>
</body>
</html>""";

    with open(FLIP_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Flipbook OK: {FLIP_PATH}")

    # -- Actualizar index.html de flipbook --
    idx_html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0; url={fecha_str}.html">
<title>Diario Info - Edicion Impresa</title></head>
<body><p>Redirigiendo a la edicion del dia... <a href="{fecha_str}.html">Click aqui</a></p>
<a href="{fecha_str}.html">Ver edicion</a></body></html>"""
    with open(os.path.join(DIR_FLIPBOOK, "index.html"), "w", encoding="utf-8") as f:
        f.write(idx_html)


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    print("=== Diario Info PDF Generator v3.20 ===")
    print(f"Fecha: {FECHA_STR}")
    # Diagnostico rutas
    import glob as _glob
    _homes = _glob.glob("/home/*/public_html/uploads") + _glob.glob("/home/*/uploads") + _glob.glob("/home/*/")
    print(f"  [diag] /home dirs: {_homes[:5]}")
    
    print("Instalando fuentes...")
    instalar_fuentes()
    
    print("Conectando MongoDB...")
    conectar_mongo()
    
    print("Obteniendo notas...")
    notas = obtener_notas(15)
    if not notas:
        print("ERROR: Sin notas"); sys.exit(1)
    
    print("Cotizaciones...")
    import sys as _sys
    _argv = _sys.argv
    _of_arg = _bl_arg = ''
    for _ai, _av in enumerate(_argv):
        if _av == '--cotiz_of' and _ai+1 < len(_argv): _of_arg = _argv[_ai+1]
        if _av == '--cotiz_bl' and _ai+1 < len(_argv): _bl_arg = _argv[_ai+1]
    if _of_arg and _bl_arg:
        of, bl = _of_arg, _bl_arg
        print(f"  Cotizaciones via args: {of} | {bl}")
    else:
        of, bl = obtener_cotizaciones()
    print(f"  {of} | {bl}")
    
    print("Clima...")
    clima = obtener_clima()
    print(f"  {clima}")
    
    print(f"Generando PDF: {PDF_PATH}")
    cv = canvas.Canvas(PDF_PATH, pagesize=A4)
    cv.setTitle(f"Diario Info - Edicion Impresa {FECHA_STR}")
    cv.setAuthor("DiarioInfo.com.ar")
    
    print("Tapa...")
    generar_tapa(cv, notas, of, bl, clima)
    cv.showPage()
    
    for i, nota in enumerate([notas[0]] + notas[1:], start=2):
        print(f"Pagina {i}: {nota['title'][:45]}...")
        generar_pagina_interior(cv, nota, i)
        cv.showPage()
    
    cv.save()
    tam = os.path.getsize(PDF_PATH)
    print(f"PDF OK! {tam/1024:.1f} KB")
    
    print("Flipbook...")
    pdf_url = f"https://diarioinfo.com/revistas/diarioinfo/{FECHA_STR}.pdf"
    generar_flipbook(PDF_PATH, pdf_url, FECHA_STR, notas)
    
    print(f"\n=== COMPLETADO ===")
    print(f"PDF:      {PDF_PATH}")
    print(f"Acceso:   https://diarioinfo.com/flipbook/{FECHA_STR}.html")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diario Info - Generador de PDF Edicion Impresa v1.6
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

# ── Colores ────────────────────────────────────────────────────────────────────
AZUL    = (0.0,  0.20, 0.40)
NARANJA = (0.957,0.486,0.125)
GRIS    = (0.40, 0.40, 0.40)
GRIS_C  = (0.50, 0.50, 0.50)
GRIS_L  = (0.80, 0.80, 0.80)
GRIS_BG = (0.93, 0.93, 0.93)
NEGRO   = (0.0,  0.0,  0.0)
BLANCO  = (1.0,  1.0,  1.0)

# ── Fuentes ────────────────────────────────────────────────────────────────────
FUENTES_OK = set()
FONT_TB = "Helvetica-Bold"
FONT_T  = "Helvetica"
FONT_N  = "Helvetica"

URLS_FUENTES = {
    "Lato-Regular": "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "Lato-Bold"   : "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Lato-Italic" : "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf",
}

def instalar_fuentes():
    global FONT_TB, FONT_T, FONT_N, FUENTES_OK
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
    if "Lato-Bold" in FUENTES_OK:    FONT_TB = "Lato-Bold"
    if "Lato-Regular" in FUENTES_OK: FONT_T = "Lato-Regular"; FONT_N = "Lato-Regular"
    print(f"Fuentes OK: {FUENTES_OK}")

# ── MongoDB ─────────────────────────────────────────────────────────────────────
db_global = None
cat_cache = {}

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

def obtener_url_imagen(image_id):
    if not image_id or db_global is None: return ""
    try:
        f = db_global["files"].find_one({"_id": ObjectId(str(image_id))})
        if f:
            url = f.get("fileUrl") or f.get("url") or ""
            if url and url.startswith("/"): url = BASE_IMG_URL + url
            # Encode espacios y caracteres especiales en la URL
            url = urllib.parse.quote(url, safe=":/?=&%")
            return url
    except Exception as e:
        print(f"  Error imagen {image_id}: {e}")
    return ""

def obtener_notas(limite=15):
    """Obtiene notas del dia actual con fallback a 3 dias"""
    db = db_global
    hoy_inicio = datetime(HOY.year, HOY.month, HOY.day, 0, 0, 0)
    hoy_fin    = datetime(HOY.year, HOY.month, HOY.day, 23, 59, 59)
    
    cursor = db["articles"].find(
        {"status": "published", "publicationDate": {"$gte": hoy_inicio, "$lte": hoy_fin}}
    ).sort([("priority", -1), ("publicationDate", -1)]).limit(limite)
    notas = list(cursor)
    
    if len(notas) < 4:
        tres_dias = hoy_inicio - timedelta(days=3)
        cursor2 = db["articles"].find(
            {"status": "published", "publicationDate": {"$gte": tres_dias, "$lte": hoy_fin}}
        ).sort([("priority", -1), ("publicationDate", -1)]).limit(limite)
        notas = list(cursor2)
    
    result = []
    for n in notas:
        img_url = obtener_url_imagen(n.get("imageId"))
        cat_name = obtener_nombre_categoria(n.get("category"))
        result.append({
            "title":    limpiar_html(n.get("title", "")),
            "excerpt":  limpiar_html(n.get("description") or n.get("excerpt") or ""),
            "content":  limpiar_html(n.get("content", "")),
            "category": cat_name,
            "img_url":  img_url,
            "priority": n.get("priority", 0),
            "date":     n.get("publicationDate", HOY),
        })
    print(f"Notas obtenidas: {len(result)}")
    for i, r in enumerate(result[:4]):
        print(f"  {i}: [{r['priority']}] [{r['category']}] {r['title'][:45]}")
        print(f"       img={r['img_url'][:60] if r['img_url'] else 'NONE'}")
    return result

# ── Helpers texto ───────────────────────────────────────────────────────────────
def limpiar_html(texto):
    if not texto: return ""
    texto = re.sub(r'<[^>]+>', ' ', str(texto))
    texto = html.unescape(texto)
    return re.sub(r'\s+', ' ', texto).strip()

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
def draw_image(c, url, x, y, w, h):
    """Descarga y dibuja imagen centrada en el rectangulo dado. Si falla -> placeholder"""
    if url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DiarioInfo-PDF/1.6"})
            data = urllib.request.urlopen(req, timeout=12).read()
            img = ImageReader(io.BytesIO(data))
            iw, ih = img.getSize()
            ratio = iw / ih
            box_ratio = w / h
            if ratio > box_ratio:
                dw, dh = w, w / ratio
                dx, dy = x, y + (h - dh) / 2
            else:
                dh, dw = h, h * ratio
                dx, dy = x + (w - dw) / 2, y
            c.drawImage(img, dx, dy, dw, dh, preserveAspectRatio=True, mask="auto")
            return True
        except Exception as e:
            print(f"  Error img {str(url)[:60]}: {e}")
    # Placeholder gris
    c.setFillColorRGB(*GRIS_BG)
    c.roundRect(x, y, w, h, 3, fill=1, stroke=0)
    c.setFillColorRGB(*GRIS_C)
    c.setFont(FONT_N, 7)
    c.drawCentredString(x + w/2, y + h/2 - 3.5, "Imagen no disponible")
    return False

# ── Logo ────────────────────────────────────────────────────────────────────────
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
    try:
        import json
        req = urllib.request.urlopen("https://api.bluelytics.com.ar/v2/latest", timeout=8)
        data = json.loads(req.read())
        of = data.get("oficial", {}).get("value_sell", 0)
        bl = data.get("blue", {}).get("value_sell", 0)
        return f"Oficial: ${of:,.0f}", f"Blue: ${bl:,.0f}"
    except:
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
def generar_tapa(c, notas, cotiz_of, cotiz_bl, clima):
    fn  = "Lato-Regular" if "Lato-Regular" in FUENTES_OK else "Helvetica"
    ftb = "Lato-Bold"    if "Lato-Bold"    in FUENTES_OK else "Helvetica-Bold"
    
    W, H = A4
    M = 10 * mm
    AW = W - 2*M   # ancho util
    
    DIAS   = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
    MESES  = ["enero","febrero","marzo","abril","mayo","junio",
               "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    fecha_txt = f"{DIAS[HOY.weekday()]} {HOY.day} de {MESES[HOY.month-1]} de {HOY.year}"
    
    # Fondo blanco
    c.setFillColorRGB(*BLANCO); c.rect(0, 0, W, H, fill=1, stroke=0)
    
    y = H - M
    
    # ── 1. Barra informativa ─────────────────────────────────────────────────────
    info = f"{fecha_txt}  |  {clima}  |  {cotiz_of}  |  {cotiz_bl}"
    c.setFont(fn, 7.5); c.setFillColorRGB(*GRIS)
    c.drawCentredString(W/2, y - 8, info)
    y -= 14
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
    c.line(M, y, W-M, y); y -= 2
    
    # ── 2. Logo centrado ─────────────────────────────────────────────────────────
    logo_h = 36
    logo_cy = y - logo_h/2 - 2
    # Estimar ancho del logo para centrarlo
    r_icon = 17
    txt_w = (c.stringWidth("diario", ftb, 26) + c.stringWidth("info", ftb, 28) + 
             c.stringWidth(".com", fn, 13) + 3)
    logo_total = r_icon * 2 + txt_w
    logo_icon_x = W/2 - logo_total/2 + r_icon
    
    draw_logo(c, logo_icon_x, logo_cy, r=r_icon)
    
    # Subtitulo bajo logo
    sub_y = logo_cy - r_icon - 3
    c.setFont(fn, 8.5); c.setFillColorRGB(*GRIS)
    c.drawCentredString(W/2, sub_y, "Santiago del Estero")
    
    y = sub_y - 6
    
    # Linea azul
    c.setStrokeColorRGB(*AZUL); c.setLineWidth(1.5)
    c.line(M, y, W-M, y); y -= 8
    
    # ── 3. Nota principal ────────────────────────────────────────────────────────
    n0 = notas[0] if notas else {}
    
    # Titular
    y = draw_text_center(c, n0.get("title",""), W/2, y, AW - 10*mm, ftb, 26, NEGRO, max_lineas=3, lh=31)
    y -= 5
    
    # Bajada
    exc0 = n0.get("excerpt","")[:220]
    if exc0:
        y = draw_text_center(c, exc0, W/2, y, AW - 18*mm, fn, 10.5, GRIS, max_lineas=2, lh=14)
        y -= 7
    
    # Imagen principal
    img_h = min(66*mm, max(35*mm, y - 58*mm))
    img_y = y - img_h
    draw_image(c, n0.get("img_url"), M, img_y, AW, img_h)
    y = img_y - 5
    
    # Linea gris
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.5)
    c.line(M, y, W-M, y); y -= 5
    
    # ── 4. Columnas secundarias ──────────────────────────────────────────────────
    zona_h = y - (10*mm + 8)
    sep = 4     # separador entre columnas
    col_w = (AW - 2*sep) / 3
    
    for i in range(3):
        n_col = notas[i+1] if len(notas) > i+1 else {}
        cx = M + i * (col_w + sep)
        cy = y
        
        # Separador vertical
        if i > 0:
            c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
            c.line(cx - sep/2, y, cx - sep/2, y - zona_h + 2)
        
        # Categoria
        cat = n_col.get("category", "")
        c.setFont(ftb, 8); c.setFillColorRGB(*AZUL)
        c.drawString(cx + 2, cy - 10, cat[:18])
        cy -= 14
        
        # Titulo
        cy = draw_text_left(c, n_col.get("title",""), cx+2, cy, col_w-4, ftb, 10.5, NEGRO, max_lineas=3, lh=13)
        cy -= 4
        
        # Bajada
        cy = draw_text_left(c, n_col.get("excerpt","")[:160], cx+2, cy, col_w-4, fn, 8, GRIS_C, max_lineas=2, lh=11)
        cy -= 4
        
        # Imagen de columna
        img_col_y_base = 10*mm + 8
        img_col_h = cy - img_col_y_base - 3
        if img_col_h > 15:
            draw_image(c, n_col.get("img_url"), cx+2, img_col_y_base, col_w-4, img_col_h)
    
    # ── 5. Pie ───────────────────────────────────────────────────────────────────
    pie_y = 10*mm
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
    c.line(M, pie_y, W-M, pie_y)
    c.setFont(fn, 8); c.setFillColorRGB(*GRIS)
    c.drawString(M, pie_y - 8, "www.diarioinfo.com.ar")
    c.drawRightString(W-M, pie_y - 8, "Edicion Impresa  •  Santiago del Estero")

# ── Paginas interiores ──────────────────────────────────────────────────────────
def generar_pagina_interior(c, nota, num_pag):
    fn  = "Lato-Regular" if "Lato-Regular" in FUENTES_OK else "Helvetica"
    ftb = "Lato-Bold"    if "Lato-Bold"    in FUENTES_OK else "Helvetica-Bold"
    
    W, H = A4
    M = 12*mm
    AW = W - 2*M
    MESES = ["enero","febrero","marzo","abril","mayo","junio",
              "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    fecha_c = f"{HOY.day} de {MESES[HOY.month-1]} de {HOY.year}"
    
    c.setFillColorRGB(*BLANCO); c.rect(0,0,W,H,fill=1,stroke=0)
    
    # Cabecera azul
    cab_h = 14*mm
    c.setFillColorRGB(*AZUL); c.rect(0, H-cab_h, W, cab_h, fill=1, stroke=0)
    cy_cab = H - cab_h/2
    # Logo mini
    c.setFont(ftb, 13); c.setFillColorRGB(*BLANCO)
    c.drawString(M, cy_cab-5, "diario")
    wd = c.stringWidth("diario", ftb, 13)
    c.setFont(ftb, 14); c.setFillColorRGB(*NARANJA)
    c.drawString(M+wd, cy_cab-6, "info")
    wi = c.stringWidth("info", ftb, 14)
    c.setFont(fn, 8.5); c.setFillColorRGB(*BLANCO)
    c.drawString(M+wd+wi, cy_cab-3, ".com")
    # Fecha
    c.setFont(fn, 8); c.setFillColorRGB(*BLANCO)
    c.drawRightString(W-M, cy_cab-3, fecha_c)
    
    y = H - cab_h - 7*mm
    
    # Categoria
    cat = nota.get("category", "GENERAL")
    c.setFont(ftb, 9); c.setFillColorRGB(*NARANJA)
    c.drawString(M, y, cat[:30])
    y -= 5*mm
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
    c.line(M, y, W-M, y); y -= 4*mm
    
    # Titular
    y = draw_text_left(c, nota.get("title",""), M, y, AW, ftb, 20, NEGRO, max_lineas=3, lh=24)
    y -= 3*mm
    
    # Bajada
    exc = nota.get("excerpt","")[:280]
    if exc:
        y = draw_text_left(c, exc, M, y, AW, fn, 10.5, GRIS, max_lineas=2, lh=14)
        y -= 3*mm
    
    # Linea
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
    c.line(M, y, W-M, y); y -= 4*mm
    
    # Imagen
    img_h = min(58*mm, max(30*mm, y - 50*mm))
    img_y = y - img_h
    draw_image(c, nota.get("img_url"), M, img_y, AW, img_h)
    y = img_y - 4*mm
    
    # Cuerpo en 2 columnas
    contenido = (nota.get("content") or nota.get("excerpt") or "")[:2500]
    col_w2 = (AW - 4*mm) / 2
    palabras = contenido.split()
    mid = len(palabras) // 2
    cols = [" ".join(palabras[:mid]), " ".join(palabras[mid:])]
    
    for ci, txt in enumerate(cols):
        cx2 = M + ci * (col_w2 + 4*mm)
        cy2 = y
        c.setFont(fn, 9); c.setFillColorRGB(*NEGRO)
        lineas = wrap_lines(c, txt, col_w2, fn, 9)
        for linea in lineas:
            if cy2 < 14*mm: break
            c.drawString(cx2, cy2, linea)
            cy2 -= 11.5
    
    # Pie
    py = 10*mm
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
    c.line(M, py, W-M, py)
    c.setFont(fn, 7.5); c.setFillColorRGB(*GRIS)
    c.drawString(M, py-7, "www.diarioinfo.com.ar")
    c.drawCentredString(W/2, py-7, "Diario Info - Edicion Impresa")
    c.drawRightString(W-M, py-7, f"Pagina {num_pag}")

# ── Flipbook HTML ───────────────────────────────────────────────────────────────
def generar_flipbook(pdf_url, fecha_str):
    titulo = f"Diario Info - Edicion {fecha_str}"
    flip_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;min-height:100vh;display:flex;flex-direction:column;align-items:center;font-family:Arial,sans-serif;color:#fff;padding:20px}}
h1{{font-size:18px;margin-bottom:12px;color:#F47C20}}
.viewer{{width:95vw;height:85vh;border:none;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,0.5)}}
.links{{margin-top:12px;display:flex;gap:20px}}
a{{color:#F47C20;text-decoration:none;padding:8px 16px;border:1px solid #F47C20;border-radius:4px}}
a:hover{{background:#F47C20;color:#fff}}
</style>
</head>
<body>
<h1>{titulo}</h1>
<iframe class="viewer" src="{pdf_url}" type="application/pdf"></iframe>
<div class="links">
<a href="{pdf_url}" download>Descargar PDF</a>
<a href="index.html">Ultimas ediciones</a>
</div>
</body>
</html>"""
    with open(FLIP_PATH, "w", encoding="utf-8") as f: f.write(flip_html)
    idx = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url={fecha_str}.html">
<title>Diario Info - Edicion Impresa</title></head>
<body><a href="{fecha_str}.html">Ver edicion</a></body></html>"""
    with open(os.path.join(DIR_FLIPBOOK, "index.html"), "w", encoding="utf-8") as f: f.write(idx)

# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    print("=== Diario Info PDF Generator v1.6 ===")
    print(f"Fecha: {FECHA_STR}")
    
    print("Instalando fuentes...")
    instalar_fuentes()
    
    print("Conectando MongoDB...")
    conectar_mongo()
    
    print("Obteniendo notas...")
    notas = obtener_notas(15)
    if not notas:
        print("ERROR: Sin notas"); sys.exit(1)
    
    print("Cotizaciones...")
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
    
    for i, nota in enumerate(notas[1:], start=2):
        print(f"Pagina {i}: {nota['title'][:45]}...")
        generar_pagina_interior(cv, nota, i)
        cv.showPage()
    
    cv.save()
    tam = os.path.getsize(PDF_PATH)
    print(f"PDF OK! {tam/1024:.1f} KB")
    
    print("Flipbook...")
    pdf_url = f"https://diarioinfo.com/revistas/diarioinfo/{FECHA_STR}.pdf"
    generar_flipbook(pdf_url, FECHA_STR)
    
    print(f"\n=== COMPLETADO ===")
    print(f"PDF:      {PDF_PATH}")
    print(f"Acceso:   https://diarioinfo.com/flipbook/{FECHA_STR}.html")

if __name__ == "__main__":
    main()

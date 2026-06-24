#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diario Info - Generador de PDF Edicion Impresa v1.5
Correcciones: publicationDate, fileUrl, filtro por fecha del dia, imagenes reales
"""

import os, sys, re, io, textwrap, urllib.request, urllib.error, html
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
AZUL    = (0.0,  0.20, 0.40)   # #003366
NARANJA = (0.957,0.486,0.125)  # #F47C20
GRIS    = (0.40, 0.40, 0.40)   # #666666
GRIS_C  = (0.55, 0.55, 0.55)   # #8C8C8C
GRIS_L  = (0.80, 0.80, 0.80)   # #CCCCCC
GRIS_BG = (0.95, 0.95, 0.95)   # #F2F2F2
NEGRO   = (0.0,  0.0,  0.0)
BLANCO  = (1.0,  1.0,  1.0)

# ── Fuentes ────────────────────────────────────────────────────────────────────
FUENTES_OK = set()
FONT_TB = "Helvetica-Bold"
FONT_T  = "Helvetica"
FONT_N  = "Helvetica"

URLS_FUENTES = {
    "Lato-Regular"    : "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "Lato-Bold"       : "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Lato-Italic"     : "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf",
    "Merriweather-Bold": "https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Bold.ttf",
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
    if "Lato-Regular" in FUENTES_OK: FONT_T  = "Lato-Regular"; FONT_N = "Lato-Regular"
    print(f"Fuentes OK: {FUENTES_OK}")

# ── Helpers de texto ───────────────────────────────────────────────────────────
def limpiar_html(texto):
    if not texto: return ""
    texto = re.sub(r'<[^>]+>', ' ', texto)
    texto = html.unescape(texto)
    return re.sub(r'\s+', ' ', texto).strip()

def wrap_text(c, texto, x, y, ancho, fuente, tamanio, color, lineas_max=99, interlinea=None):
    if not texto: return y
    c.setFont(fuente, tamanio)
    c.setFillColorRGB(*color)
    if interlinea is None: interlinea = tamanio * 1.25
    palabras = texto.split()
    lineas = []
    linea_actual = ""
    for p in palabras:
        prueba = (linea_actual + " " + p).strip()
        if c.stringWidth(prueba, fuente, tamanio) <= ancho:
            linea_actual = prueba
        else:
            if linea_actual: lineas.append(linea_actual)
            linea_actual = p
    if linea_actual: lineas.append(linea_actual)
    for i, linea in enumerate(lineas[:lineas_max]):
        c.drawString(x, y - i * interlinea, linea)
    return y - min(len(lineas), lineas_max) * interlinea

def wrap_text_center(c, texto, cx, y, ancho, fuente, tamanio, color, lineas_max=99, interlinea=None):
    if not texto: return y
    c.setFont(fuente, tamanio)
    c.setFillColorRGB(*color)
    if interlinea is None: interlinea = tamanio * 1.3
    palabras = texto.split()
    lineas = []
    linea_actual = ""
    for p in palabras:
        prueba = (linea_actual + " " + p).strip()
        if c.stringWidth(prueba, fuente, tamanio) <= ancho:
            linea_actual = prueba
        else:
            if linea_actual: lineas.append(linea_actual)
            linea_actual = p
    if linea_actual: lineas.append(linea_actual)
    for i, linea in enumerate(lineas[:lineas_max]):
        c.drawCentredString(cx, y - i * interlinea, linea)
    return y - min(len(lineas), lineas_max) * interlinea

def dibujar_imagen(c, url, x, y, ancho, alto, placeholder=True):
    """Descarga y dibuja una imagen. Si falla dibuja placeholder gris."""
    if url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=10).read()
            img = ImageReader(io.BytesIO(data))
            iw, ih = img.getSize()
            ratio = iw / ih
            if ratio > (ancho / alto):
                draw_w = ancho
                draw_h = ancho / ratio
                draw_y = y + (alto - draw_h) / 2
                draw_x = x
            else:
                draw_h = alto
                draw_w = alto * ratio
                draw_x = x + (ancho - draw_w) / 2
                draw_y = y
            c.drawImage(img, draw_x, draw_y, draw_w, draw_h, preserveAspectRatio=True, mask='auto')
            return True
        except Exception as e:
            print(f"  Error imagen {url[:60]}: {e}")
    if placeholder:
        c.setFillColorRGB(*GRIS_L)
        c.rect(x, y, ancho, alto, fill=1, stroke=0)
        c.setFillColorRGB(*GRIS)
        c.setFont(FONT_N, 8)
        c.drawCentredString(x + ancho/2, y + alto/2 - 4, "Imagen no disponible")
    return False

# ── Logo ────────────────────────────────────────────────────────────────────────
def dibujar_logo(c, cx, cy, escala=1.0):
    """Dibuja el logo: circulo play azul/naranja + texto diarioinfo.com"""
    r = 18 * escala
    # Mitad izquierda azul
    c.setFillColorRGB(*AZUL)
    p = c.beginPath()
    import math
    cx_l = cx - r
    for i in range(181):
        ang = math.radians(90 + i)
        if i == 0: p.moveTo(cx_l + r*math.cos(ang), cy + r*math.sin(ang))
        else: p.lineTo(cx_l + r*math.cos(ang), cy + r*math.sin(ang))
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    # Mitad derecha naranja  
    c.setFillColorRGB(*NARANJA)
    p2 = c.beginPath()
    for i in range(181):
        ang = math.radians(270 + i)
        if i == 0: p2.moveTo(cx_l + r*math.cos(ang), cy + r*math.sin(ang))
        else: p2.lineTo(cx_l + r*math.cos(ang), cy + r*math.sin(ang))
    p2.close()
    c.drawPath(p2, fill=1, stroke=0)
    # Triangulo play blanco
    c.setFillColorRGB(*BLANCO)
    tr_x = cx_l - r*0.25
    tr_h = r * 0.7
    p3 = c.beginPath()
    p3.moveTo(tr_x - tr_h*0.4, cy + tr_h*0.5)
    p3.lineTo(tr_x - tr_h*0.4, cy - tr_h*0.5)
    p3.lineTo(tr_x + tr_h*0.6, cy)
    p3.close()
    c.drawPath(p3, fill=1, stroke=0)
    # Texto: "diario" azul + "info" naranja + ".com" gris
    sx = cx_l + r + 3*escala
    fs_d = 26 * escala
    fs_i = 28 * escala
    fs_c = 14 * escala
    c.setFont(FONT_TB, fs_d); c.setFillColorRGB(*AZUL)
    c.drawString(sx, cy - fs_d*0.35, "diario")
    w_d = c.stringWidth("diario", FONT_TB, fs_d)
    c.setFont(FONT_TB, fs_i); c.setFillColorRGB(*NARANJA)
    c.drawString(sx + w_d, cy - fs_i*0.38, "info")
    w_i = c.stringWidth("info", FONT_TB, fs_i)
    c.setFont(FONT_TB, fs_c); c.setFillColorRGB(*GRIS)
    c.drawString(sx + w_d + w_i, cy - fs_c*0.35, ".com")

# ── MongoDB ─────────────────────────────────────────────────────────────────────
db_global = None

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

def obtener_url_imagen(imageId):
    if not imageId or not db_global: return ""
    try:
        f = db_global["files"].find_one({"_id": ObjectId(str(imageId))})
        if f:
            url = f.get("fileUrl") or f.get("url") or ""
            if url and url.startswith("/"): url = BASE_IMG_URL + url
            return url
    except Exception as e:
        print(f"  Error imagen {imageId}: {e}")
    return ""

def obtener_notas(limite=15):
    """Obtiene notas del dia actual, con fallback a 3 dias recientes"""
    db = db_global
    hoy_inicio = datetime(HOY.year, HOY.month, HOY.day, 0, 0, 0)
    hoy_fin    = datetime(HOY.year, HOY.month, HOY.day, 23, 59, 59)
    
    # Intento 1: notas del dia actual
    cursor = db["articles"].find(
        {"status": "published", "publicationDate": {"$gte": hoy_inicio, "$lte": hoy_fin}}
    ).sort([("priority", -1), ("publicationDate", -1)]).limit(limite)
    notas = list(cursor)
    
    # Fallback: ultimos 3 dias
    if len(notas) < 4:
        tres_dias = hoy_inicio - timedelta(days=3)
        cursor2 = db["articles"].find(
            {"status": "published", "publicationDate": {"$gte": tres_dias, "$lte": hoy_fin}}
        ).sort([("priority", -1), ("publicationDate", -1)]).limit(limite)
        notas = list(cursor2)
    
    # Agregar URL de imagen a cada nota
    result = []
    for n in notas:
        img_url = obtener_url_imagen(n.get("imageId"))
        result.append({
            "title":    limpiar_html(n.get("title", "")),
            "excerpt":  limpiar_html(n.get("description", n.get("excerpt", ""))),
            "content":  limpiar_html(n.get("content", "")),
            "category": str(n.get("category", "GENERAL")).upper(),
            "img_url":  img_url,
            "priority": n.get("priority", 0),
            "date":     n.get("publicationDate", HOY),
        })
    print(f"Notas obtenidas: {len(result)}")
    for i, r in enumerate(result[:4]):
        print(f"  {i}: [{r['priority']}] {r['title'][:50]} | img={r['img_url'][:50] if r['img_url'] else 'NONE'}")
    return result

# ── Cotizaciones y Clima ────────────────────────────────────────────────────────
def obtener_cotizaciones():
    try:
        req = urllib.request.urlopen("https://api.bluelytics.com.ar/v2/latest", timeout=5)
        import json
        data = json.loads(req.read())
        oficial = data.get("oficial", {}).get("value_sell", 0)
        blue    = data.get("blue", {}).get("value_sell", 0)
        return f"Oficial: ${oficial:.0f}", f"Blue: ${blue:.0f}"
    except:
        return "Oficial: N/D", "Blue: N/D"

def obtener_clima():
    try:
        url = "https://wttr.in/Santiago+del+Estero?format=%C+%t"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        datos = resp.read().decode("utf-8").strip()
        datos = datos.replace("+", " ")
        return f"Santiago del Estero {datos}"
    except:
        return "Santiago del Estero"

# ── Tapa ────────────────────────────────────────────────────────────────────────
def generar_tapa(c, notas, cotiz_ofic, cotiz_blue, clima_str):
    FONT_N  = "Lato-Regular" if "Lato-Regular" in FUENTES_OK else "Helvetica"
    FONT_TB = "Lato-Bold"    if "Lato-Bold"    in FUENTES_OK else "Helvetica-Bold"
    
    W, H = A4
    M = 10 * mm
    
    DIAS = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
    MESES = ["enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    dia_sem = DIAS[HOY.weekday()]
    fecha_larga = f"{dia_sem} {HOY.day} de {MESES[HOY.month-1]} de {HOY.year}"
    
    # Fondo blanco
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    
    y = H - M
    
    # ── 1. Barra info superior ──────────────────────────────────────────────────
    info_parts = [fecha_larga, clima_str, cotiz_ofic, cotiz_blue]
    info_txt = "  |  ".join(info_parts)
    c.setFont(FONT_N, 7.5)
    c.setFillColorRGB(*GRIS)
    c.drawCentredString(W/2, y - 8, info_txt)
    y -= 14
    
    # Linea gris fina
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.4)
    c.line(M, y, W - M, y)
    y -= 2
    
    # ── 2. Logo ─────────────────────────────────────────────────────────────────
    logo_h = 38
    logo_y = y - logo_h
    # Calcular ancho total del logo para centrarlo
    r = 18
    logo_total_w = r*2 + 3 + c.stringWidth("diario", FONT_TB, 26) + c.stringWidth("info", FONT_TB, 28) + c.stringWidth(".com", FONT_TB, 14)
    logo_cx = W/2 - logo_total_w/2 + r
    logo_cy = logo_y + logo_h/2
    dibujar_logo(c, logo_cx, logo_cy, escala=1.0)
    # Subtitulo Santiago del Estero
    c.setFont(FONT_N, 9)
    c.setFillColorRGB(*GRIS)
    c.drawCentredString(W/2 + 10, logo_y + 4, "Santiago del Estero")
    y = logo_y - 4
    
    # Linea azul bajo logo
    c.setStrokeColorRGB(*AZUL)
    c.setLineWidth(1.5)
    c.line(M, y, W - M, y)
    y -= 6
    
    # ── 3. Nota principal ───────────────────────────────────────────────────────
    nota0 = notas[0] if notas else {}
    
    # Titular grande
    titulo = nota0.get("title", "")
    ancho_cont = W - 2*M
    y = wrap_text_center(c, titulo, W/2, y, ancho_cont, FONT_TB, 26, NEGRO, lineas_max=3, interlinea=30)
    y -= 4
    
    # Bajada/copete
    excerpt = nota0.get("excerpt", "")[:200]
    if excerpt:
        y = wrap_text_center(c, excerpt, W/2, y, ancho_cont - 20*mm, FONT_N, 10.5, GRIS, lineas_max=2, interlinea=14)
        y -= 6
    
    # Imagen principal - ocupa zona generosa
    img_zona_h = min(65 * mm, y - 60*mm)
    img_y = y - img_zona_h
    dibujar_imagen(c, nota0.get("img_url"), M, img_y, ancho_cont, img_zona_h)
    y = img_y - 5
    
    # Linea gris separadora
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, y, W - M, y)
    y -= 6
    
    # ── 4. Tres columnas secundarias ─────────────────────────────────────────────
    zona_secundaria_h = y - (10*mm + 8)  # altura disponible para las columnas
    col_w = (ancho_cont - 2*0.4) / 3
    col_img_h = zona_secundaria_h * 0.42
    
    for i in range(3):
        nota = notas[i+1] if len(notas) > i+1 else {}
        col_x = M + i * (col_w + 0.4)
        cy_col = y
        
        # Separador vertical (excepto primera)
        if i > 0:
            c.setStrokeColorRGB(*GRIS_L)
            c.setLineWidth(0.4)
            c.line(col_x - 0.4, y, col_x - 0.4, y - zona_secundaria_h)
        
        # Etiqueta categoria
        cat = nota.get("category", "")[:20]
        c.setFont(FONT_TB, 8)
        c.setFillColorRGB(*AZUL)
        c.drawString(col_x + 2, cy_col - 10, cat)
        cy_col -= 13
        
        # Titulo
        tit = nota.get("title", "")
        cy_col = wrap_text(c, tit, col_x + 2, cy_col, col_w - 4, FONT_TB, 10.5, NEGRO, lineas_max=3, interlinea=13)
        cy_col -= 4
        
        # Bajada
        exc = nota.get("excerpt", "")[:150]
        cy_col = wrap_text(c, exc, col_x + 2, cy_col, col_w - 4, FONT_N, 8, GRIS_C, lineas_max=2, interlinea=11)
        cy_col -= 4
        
        # Imagen de columna
        img_col_y = (10*mm + 8)
        img_col_h = cy_col - img_col_y - 2
        if img_col_h > 15:
            dibujar_imagen(c, nota.get("img_url"), col_x + 2, img_col_y, col_w - 4, img_col_h)
    
    # ── 5. Pie de pagina ─────────────────────────────────────────────────────────
    pie_y = 10*mm
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.4)
    c.line(M, pie_y, W - M, pie_y)
    c.setFont(FONT_N, 8)
    c.setFillColorRGB(*GRIS)
    c.drawString(M, pie_y - 8, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, pie_y - 8, "Edicion Impresa  •  Santiago del Estero")

# ── Paginas Interiores ──────────────────────────────────────────────────────────
def generar_pagina_interior(c, nota, num_pagina):
    FONT_N  = "Lato-Regular" if "Lato-Regular" in FUENTES_OK else "Helvetica"
    FONT_TB = "Lato-Bold"    if "Lato-Bold"    in FUENTES_OK else "Helvetica-Bold"
    
    W, H = A4
    M = 12 * mm
    
    MESES = ["enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    fecha_corta = f"{HOY.day} de {MESES[HOY.month-1]} de {HOY.year}"
    
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    
    # ── Cabecera azul ────────────────────────────────────────────────────────────
    cab_h = 14 * mm
    c.setFillColorRGB(*AZUL)
    c.rect(0, H - cab_h, W, cab_h, fill=1, stroke=0)
    
    # Logo en cabecera (version pequeña)
    logo_cab_y = H - cab_h/2
    c.setFont(FONT_TB, 14); c.setFillColorRGB(*BLANCO)
    c.drawString(M, logo_cab_y - 5, "diario")
    w_d = c.stringWidth("diario", FONT_TB, 14)
    c.setFont(FONT_TB, 15); c.setFillColorRGB(*NARANJA)
    c.drawString(M + w_d, logo_cab_y - 6, "info")
    w_i = c.stringWidth("info", FONT_TB, 15)
    c.setFont(FONT_TB, 9); c.setFillColorRGB(*BLANCO)
    c.drawString(M + w_d + w_i, logo_cab_y - 3, ".com")
    
    # Fecha en cabecera (derecha)
    c.setFont(FONT_N, 8); c.setFillColorRGB(*BLANCO)
    c.drawRightString(W - M, logo_cab_y - 3, fecha_corta)
    
    # ── Contenido ────────────────────────────────────────────────────────────────
    y = H - cab_h - 8*mm
    ancho_cont = W - 2*M
    
    # Categoria
    cat = nota.get("category", "GENERAL")[:30]
    c.setFont(FONT_TB, 9); c.setFillColorRGB(*NARANJA)
    c.drawString(M, y, cat)
    y -= 6*mm
    
    # Linea bajo categoria
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.5)
    c.line(M, y, W - M, y)
    y -= 5*mm
    
    # Titular
    titulo = nota.get("title", "")
    y = wrap_text(c, titulo, M, y, ancho_cont, FONT_TB, 20, NEGRO, lineas_max=3, interlinea=24)
    y -= 3*mm
    
    # Bajada
    excerpt = nota.get("excerpt", "")[:250]
    if excerpt:
        y = wrap_text(c, excerpt, M, y, ancho_cont, FONT_N, 10.5, GRIS, lineas_max=2, interlinea=13)
        y -= 3*mm
    
    # Linea separadora
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.5)
    c.line(M, y, W - M, y)
    y -= 4*mm
    
    # Imagen
    img_h = 55 * mm
    img_y = y - img_h
    if img_y < 55*mm: img_h = y - 55*mm; img_y = 55*mm
    dibujar_imagen(c, nota.get("img_url"), M, img_y, ancho_cont, img_h)
    y = img_y - 4*mm
    
    # Contenido en dos columnas
    contenido = nota.get("content", nota.get("excerpt", ""))[:2000]
    col_w = (ancho_cont - 4*mm) / 2
    col_gap = 4*mm
    
    palabras = contenido.split()
    total = len(palabras)
    mitad = total // 2
    col1 = " ".join(palabras[:mitad])
    col2 = " ".join(palabras[mitad:])
    
    for ci, texto_col in enumerate([col1, col2]):
        cx = M + ci * (col_w + col_gap)
        cy = y
        lineas_col = []
        c.setFont(FONT_N, 9)
        linea_actual = ""
        for p in texto_col.split():
            prueba = (linea_actual + " " + p).strip()
            if c.stringWidth(prueba, FONT_N, 9) <= col_w:
                linea_actual = prueba
            else:
                if linea_actual: lineas_col.append(linea_actual)
                linea_actual = p
        if linea_actual: lineas_col.append(linea_actual)
        c.setFillColorRGB(*NEGRO)
        for linea in lineas_col:
            if cy < 14*mm: break
            c.drawString(cx, cy, linea)
            cy -= 11.5
    
    # Pie
    pie_y = 10*mm
    c.setStrokeColorRGB(*GRIS_L); c.setLineWidth(0.4)
    c.line(M, pie_y, W - M, pie_y)
    c.setFont(FONT_N, 7.5); c.setFillColorRGB(*GRIS)
    c.drawString(M, pie_y - 7, "www.diarioinfo.com.ar")
    c.drawCentredString(W/2, pie_y - 7, "Diario Info - Edicion Impresa")
    c.drawRightString(W - M, pie_y - 7, f"Pagina {num_pagina}")

# ── Flipbook HTML ───────────────────────────────────────────────────────────────
def generar_flipbook(pdf_url, fecha):
    titulo = f"Diario Info - Edicion Impresa {fecha}"
    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
<style>
body {{ margin:0; background:#222; display:flex; flex-direction:column; align-items:center; min-height:100vh; font-family:Arial,sans-serif; color:#fff; }}
h1 {{ margin:20px 0 10px; font-size:20px; }}
iframe {{ width:90vw; height:85vh; border:none; box-shadow:0 4px 20px rgba(0,0,0,0.5); }}
a {{ color:#F47C20; text-decoration:none; margin:10px; display:inline-block; }}
a:hover {{ text-decoration:underline; }}
</style>
</head>
<body>
<h1>{titulo}</h1>
<iframe src="{pdf_url}" type="application/pdf"></iframe>
<a href="{pdf_url}" download>Descargar PDF</a>
<a href="index.html">Ver ultimas ediciones</a>
</body>
</html>"""
    fecha_str = fecha.strftime("%Y-%m-%d") if hasattr(fecha, 'strftime') else fecha
    with open(os.path.join(DIR_FLIPBOOK, f"{fecha_str}.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    # Index
    index_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta http-equiv="refresh" content="0; url={fecha_str}.html">
<title>Diario Info - Edicion Impresa</title></head>
<body><p><a href="{fecha_str}.html">Ver edicion del dia</a></p></body></html>"""
    with open(os.path.join(DIR_FLIPBOOK, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_content)

# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    print("=== Diario Info PDF Generator v1.5 ===")
    print(f"Fecha: {FECHA_STR}")
    
    print("Instalando fuentes...")
    instalar_fuentes()
    
    print("Conectando a MongoDB...")
    conectar_mongo()
    
    print("Obteniendo notas...")
    notas = obtener_notas(15)
    if not notas:
        print("ERROR: No se encontraron notas")
        sys.exit(1)
    
    print("Obteniendo cotizaciones...")
    cotiz_ofic, cotiz_blue = obtener_cotizaciones()
    print(f"  {cotiz_ofic} | {cotiz_blue}")
    
    print("Obteniendo clima...")
    clima_str = obtener_clima()
    print(f"  {clima_str}")
    
    print(f"Generando PDF: {PDF_PATH}")
    c = canvas.Canvas(PDF_PATH, pagesize=A4)
    c.setTitle(f"Diario Info - Edicion Impresa {FECHA_STR}")
    c.setAuthor("DiarioInfo.com.ar")
    
    print("Generando tapa...")
    generar_tapa(c, notas, cotiz_ofic, cotiz_blue, clima_str)
    c.showPage()
    
    for i, nota in enumerate(notas[1:], start=2):
        print(f"Generando pagina {i}: {nota['title'][:50]}...")
        generar_pagina_interior(c, nota, i)
        c.showPage()
    
    c.save()
    tam = os.path.getsize(PDF_PATH)
    print(f"PDF generado exitosamente!")
    print(f"Archivo: {PDF_PATH}")
    print(f"Tamano: {tam/1024:.1f} KB")
    
    print("Generando flipbook HTML...")
    pdf_url = f"https://diarioinfo.com/revistas/diarioinfo/{FECHA_STR}.pdf"
    generar_flipbook(pdf_url, HOY)
    print(f"Flipbook generado: {FLIP_PATH}")
    
    print(f"\n=== COMPLETADO ===")
    print(f"PDF:      {PDF_PATH}")
    print(f"Flipbook: {FLIP_PATH}")
    print(f"Acceso:   https://diarioinfo.com/flipbook/{FECHA_STR}.html")

if __name__ == "__main__":
    main()

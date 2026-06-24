#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diario Info - Generador de PDF Edicion Impresa v3.1 - Layout adaptativo full-bleed, sin badge en tapa
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

URLS_FUENTES = {
    "Lato-Regular":        "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "Lato-Bold":           "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
    "Lato-Italic":         "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf",
    "Merriweather-Bold":   "https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Bold.ttf",
    "Merriweather-Regular":"https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Regular.ttf",
}

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
def get_image_data(url):
    """Descarga imagen y retorna (ImageReader, width_px, height_px) o (None,0,0)"""
    if not url: return None, 0, 0
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DiarioInfo-PDF/1.6"})
        data = urllib.request.urlopen(req, timeout=12).read()
        ir   = ImageReader(io.BytesIO(data))
        iw, ih = ir.getSize()
        return ir, iw, ih
    except Exception as e:
        print(f"  [img download] {str(url)[:60]}: {e}")
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
    """Tapa v3.1 - layout adaptativo segun ratio imagen principal
       Layout A (ratio>=1.5 panoramica): foto FULL BLEED borde a borde, titular+bajada debajo
       Layout B (ratio<1.5 cuadrada/4:3): foto col izq + titular col der, bajada full-width
    """
    W, H = A4
    M    = 15*mm
    COL2 = (W - 2*M) / 2   # ancho de media columna

    FUI_R = FONT_T
    FUI_B = FONT_TB
    FTI_B = FONT_MBold
    FTI_R = FONT_MReg

    # Fondo blanco
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── CABECERA (Y absoluto) ────────────────────────────────────
    dia_semana = HOY.strftime("%A").capitalize()
    mes        = HOY.strftime("%B").capitalize()
    fecha_txt  = f"{dia_semana} {HOY.day} de {mes} de {HOY.year}"
    cli_txt    = f"{clima}" if clima else ""
    cot_txt    = ""
    if cotiz_of: cot_txt += f"  |  Oficial: {cotiz_of}"
    if cotiz_bl: cot_txt += f"  |  Blue: {cotiz_bl}"
    cab_line   = f"{fecha_txt}  |  Santiago del Estero {cli_txt}{cot_txt}"
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawCentredString(W/2, H - 6*mm, cab_line)

    # ── LOGO ─────────────────────────────────────────────────────
    # Icono circular bicolor (izq azul, der naranja) con triangulo blanco
    cx_icon = W/2 - 28*mm
    cy_icon = H - 22*mm
    r_icon  = 8*mm
    draw_icon(c, cx_icon, cy_icon, r_icon)

    # "diario" en azul, "info" en naranja, ".com" en gris
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

    # ── NOTA PRINCIPAL - layout adaptativo por ratio de imagen ───
    nota_p  = notas[0] if notas else None
    Y_EDIT  = Y_FIL - 3*mm   # inicio area editorial bajo filete
    PIE_H   = 14*mm
    SEC_H   = 110*mm          # altura bloque notas secundarias
    Y_SEC_TOP = PIE_H + SEC_H  # tope de notas secundarias

    if nota_p:
        titulo  = limpiar_html(nota_p.get("title", ""))
        bajada  = limpiar_html(nota_p.get("summary", "") or nota_p.get("content", ""))
        img_url = obtener_url_imagen(nota_p.get("image")) if nota_p.get("image") else ""

        # Descargar imagen y detectar ratio
        ir_p, iw_p, ih_p = get_image_data(img_url)
        ratio_p = (iw_p / ih_p) if ih_p > 0 else 0

        # --- LAYOUT A: ratio >= 1.5 (16:9 o panoramica) ---
        # Foto FULL BLEED de borde a borde (x=0, w=W)
        # Titular Merriweather-Bold 22pt negro centrado debajo
        # Bajada Merriweather-Regular 12pt gris centrada debajo
        if ratio_p >= 1.5:
            # Espacio disponible: de Y_EDIT a Y_SEC_TOP
            area_h    = Y_EDIT - Y_SEC_TOP
            tit_h     = 3 * 9.5*mm    # max 3 lineas titular @22pt
            baj_h     = 2 * 6*mm      # max 2 lineas bajada @12pt
            HERO_H    = area_h - tit_h - baj_h - 10*mm
            HERO_W    = W               # FULL BLEED: de borde a borde
            HERO_X    = 0
            HERO_TOP  = Y_EDIT - 2*mm
            HERO_BOT  = HERO_TOP - HERO_H

            # Foto full bleed
            draw_image_bleed(c, ir_p, iw_p, ih_p, HERO_X, HERO_BOT, HERO_W, HERO_H)

            # Titular: Merriweather-Bold 22pt negro centrado
            ty = HERO_BOT - 8*mm
            c.setFont(FTI_B, 22)
            c.setFillColorRGB(*NEGRO)
            for ln in wrap_lines(c, titulo, W - 2*M, FTI_B, 22)[:3]:
                if ty < Y_SEC_TOP + baj_h + 4*mm: break
                c.drawCentredString(W/2, ty, ln)
                ty -= 9.5*mm

            # Bajada: Merriweather-Regular 12pt gris centrada
            c.setFont(FTI_R, 12)
            c.setFillColorRGB(*GRIS_TXT)
            for bl in wrap_lines(c, bajada, W - 4*M, FTI_R, 12)[:2]:
                if ty < Y_SEC_TOP + 2*mm: break
                c.drawCentredString(W/2, ty, bl)
                ty -= 6*mm

        # --- LAYOUT B: ratio < 1.5 (cuadrada, portrait, 4:3) ---
        # Foto columna izquierda (col 1)
        # Titular columna derecha (col 2), arrancando al mismo Y que la foto
        # Bajada a ancho completo debajo de foto+titular
        else:
            area_h   = Y_EDIT - Y_SEC_TOP
            IMG_W    = COL2 - 3*mm
            # Altura de imagen = min del espacio disponible o ratio 4:3
            IMG_H    = min(area_h - 22*mm, IMG_W * (4.0/3.0))
            IMG_X    = M
            IMG_TOP  = Y_EDIT - 2*mm
            IMG_BOT  = IMG_TOP - IMG_H

            # Foto col izq con sangrado
            draw_image_bleed(c, ir_p, iw_p, ih_p, IMG_X, IMG_BOT, IMG_W, IMG_H)

            # Titular: col der, arranca al mismo Y que la foto
            TIT_X    = M + COL2 + 3*mm
            TIT_W    = COL2 - 3*mm
            ty       = IMG_TOP - 2*mm
            c.setFont(FTI_B, 22)
            c.setFillColorRGB(*NEGRO)
            for ln in wrap_lines(c, titulo, TIT_W, FTI_B, 22)[:4]:
                if ty < IMG_BOT: break
                c.drawString(TIT_X, ty, ln)
                ty -= 9.5*mm

            # Bajada: ancho completo debajo de la foto
            by = IMG_BOT - 5*mm
            c.setFont(FTI_R, 12)
            c.setFillColorRGB(*GRIS_TXT)
            for bl in wrap_lines(c, bajada, W - 2*M, FTI_R, 12)[:2]:
                if by < Y_SEC_TOP + 2*mm: break
                c.drawCentredString(W/2, by, bl)
                by -= 6*mm

    # ── NOTAS SECUNDARIAS - 3 columnas ────────────────────────
    notas_sec = notas[1:4]
    col_n     = 3
    col_w     = (W - 2*M) / col_n
    sec_bot   = PIE_H + 3*mm
    pad       = 3*mm
    img_h_sec = col_w * (3.0/4.0)

    for i, ns in enumerate(notas_sec):
        cx = M + i * col_w
        # Separador vertical
        if i < col_n - 1:
            c.setStrokeColorRGB(*GRIS_L)
            c.setLineWidth(0.5)
            c.line(M + (i+1)*col_w, Y_SEC_TOP, M + (i+1)*col_w, sec_bot)
        # Categoria: Lato-Bold 11pt azul
        cat = obtener_nombre_categoria(ns.get("category", ns.get("categoryId", "")))
        c.setFont(FUI_B, 11)
        c.setFillColorRGB(*AZUL_INST)
        c.drawString(cx + pad, Y_SEC_TOP - 4.5*mm, cat[:20])
        c.setStrokeColorRGB(*AZUL_INST)
        c.setLineWidth(1)
        c.line(cx + pad, Y_SEC_TOP - 6*mm, cx + col_w - pad, Y_SEC_TOP - 6*mm)
        # Imagen 4:3 con sangrado
        img_url_s = obtener_url_imagen(ns.get("image")) if ns.get("image") else ""
        img_x_s   = cx + pad
        img_w_s   = col_w - 2*pad
        img_top_s = Y_SEC_TOP - 7.5*mm
        ir_s, iw_s, ih_s = get_image_data(img_url_s)
        draw_image_bleed(c, ir_s, iw_s, ih_s, img_x_s, img_top_s - img_h_sec, img_w_s, img_h_sec)
        # Titular: Merriweather-Bold 22pt negro (fuerza de diseno)
        tit_s = limpiar_html(ns.get("title", ""))
        ty_s  = img_top_s - img_h_sec - 4*mm
        c.setFont(FTI_B, 22)
        c.setFillColorRGB(*NEGRO)
        for tsl in wrap_lines(c, tit_s, col_w - 2*pad, FTI_B, 22)[:2]:
            if ty_s < sec_bot + 2*mm: break
            c.drawString(cx + pad, ty_s, tsl)
            ty_s -= 9*mm
        # Bajada: Lato-Regular 9pt #666666
        baj_s = limpiar_html(ns.get("summary", "") or ns.get("content", ""))
        c.setFont(FUI_R, 9)
        c.setFillColorRGB(*GRIS_N)
        for bsl in wrap_lines(c, baj_s, col_w - 2*pad, FUI_R, 9)[:2]:
            if ty_s < sec_bot: break
            c.drawString(cx + pad, ty_s, bsl)
            ty_s -= 4*mm

    # ── PIE ──────────────────────────────────────────────────────
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, PIE_H - 2*mm, W - M, PIE_H - 2*mm)
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawString(M,          PIE_H - 6*mm, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, PIE_H - 6*mm, "Edición Impresa  •  Santiago del Estero")
def generar_pagina_interior(c, nota, num_pag):
    """Interior v3.1 - layout adaptativo segun ratio de imagen
       Layout A (ratio>=1.5): foto full-bleed ancho completo arriba, titular+bajada debajo, cuerpo 2 col
       Layout B (ratio<1.5): foto col izq + titular col der, bajada+cuerpo 2 col debajo
    """
    W, H = A4
    M    = 15*mm
    COL2 = (W - 2*M) / 2

    FUI_R = FONT_T
    FUI_B = FONT_TB
    FTI_B = FONT_MBold
    FTI_R = FONT_MReg

    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── CABECERA ─────────────────────────────────────────────────
    dia_semana = HOY.strftime("%A").capitalize()
    mes        = HOY.strftime("%B").capitalize()
    fecha_txt  = f"{dia_semana} {HOY.day} de {mes} de {HOY.year}"
    cab_txt    = f"{fecha_txt}  |  Santiago del Estero  |  diarioinfo.com  |  Pag. {num_pag}"
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawCentredString(W/2, H - 7*mm, cab_txt)
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, H - 9*mm, W - M, H - 9*mm)

    # ── BANDA CATEGORIA ──────────────────────────────────────────
    cat = obtener_nombre_categoria(nota.get("category", nota.get("categoryId", "")))
    Y_BANDA = H - 9*mm - 7*mm
    c.setFillColorRGB(*AZUL_INST)
    c.rect(M, Y_BANDA, W - 2*M, 5.5*mm, fill=1, stroke=0)
    c.setFont(FUI_B, 8)
    c.setFillColorRGB(*BLANCO)
    c.drawString(M + 3*mm, Y_BANDA + 1.5*mm, cat)

    # ── DATOS DE LA NOTA ─────────────────────────────────────────
    titulo  = limpiar_html(nota.get("title", ""))
    bajada  = limpiar_html(nota.get("summary", "") or nota.get("content", ""))
    cuerpo  = limpiar_html(nota.get("content", ""))
    img_url = obtener_url_imagen(nota.get("image")) if nota.get("image") else ""

    # Descargar imagen y detectar ratio
    ir_n, iw_n, ih_n = get_image_data(img_url)
    ratio_n = (iw_n / ih_n) if ih_n > 0 else 0

    Y_CONT  = Y_BANDA - 3*mm   # inicio contenido
    PIE_Y   = 18*mm
    CUERPO_Y = PIE_Y + 2*mm    # donde empieza el cuerpo de texto

    # --- LAYOUT A: ratio >= 1.5 (16:9, panoramica) ---
    # Foto FULL BLEED ancho completo arriba
    # Titular Merriweather-Bold 18pt centrado debajo
    # Bajada 12pt gris centrada
    # Cuerpo 2 columnas debajo
    if ratio_n >= 1.5:
        IMG_W   = W               # FULL BLEED
        IMG_H   = IMG_W * (9.0/16.0)
        IMG_X   = 0
        IMG_TOP = Y_CONT - 2*mm
        IMG_BOT = IMG_TOP - IMG_H
        draw_image_bleed(c, ir_n, iw_n, ih_n, IMG_X, IMG_BOT, IMG_W, IMG_H)

        # Titular Merriweather-Bold 18pt centrado
        ty = IMG_BOT - 7*mm
        c.setFont(FTI_B, 18)
        c.setFillColorRGB(*NEGRO)
        for ln in wrap_lines(c, titulo, W - 2*M, FTI_B, 18)[:3]:
            if ty < CUERPO_Y: break
            c.drawCentredString(W/2, ty, ln)
            ty -= 8*mm

        # Bajada Merriweather-Regular 12pt gris centrada
        ty -= 2*mm
        c.setFont(FTI_R, 12)
        c.setFillColorRGB(*GRIS_TXT)
        for bl in wrap_lines(c, bajada, W - 4*M, FTI_R, 12)[:2]:
            if ty < CUERPO_Y: break
            c.drawCentredString(W/2, ty, bl)
            ty -= 6*mm

        cuerpo_start = ty - 4*mm

    # --- LAYOUT B: ratio < 1.5 (cuadrada/4:3) ---
    # Foto columna izq | Titular columna der al mismo Y
    # Bajada ancho completo debajo de foto+titular
    # Cuerpo 2 columnas debajo
    else:
        IMG_W    = COL2 - 3*mm
        IMG_H    = min(Y_CONT - CUERPO_Y - 40*mm, IMG_W * (4.0/3.0))
        IMG_X    = M
        IMG_TOP  = Y_CONT - 2*mm
        IMG_BOT  = IMG_TOP - IMG_H

        draw_image_bleed(c, ir_n, iw_n, ih_n, IMG_X, IMG_BOT, IMG_W, IMG_H)

        # Titular col der
        TIT_X   = M + COL2 + 3*mm
        TIT_W   = COL2 - 3*mm
        ty      = IMG_TOP - 2*mm
        c.setFont(FTI_B, 18)
        c.setFillColorRGB(*NEGRO)
        for ln in wrap_lines(c, titulo, TIT_W, FTI_B, 18)[:4]:
            if ty < IMG_BOT: break
            c.drawString(TIT_X, ty, ln)
            ty -= 8*mm

        # Bajada ancho completo debajo de foto
        by = IMG_BOT - 5*mm
        c.setFont(FTI_R, 12)
        c.setFillColorRGB(*GRIS_TXT)
        for bl in wrap_lines(c, bajada, W - 2*M, FTI_R, 12)[:2]:
            if by < CUERPO_Y + 30*mm: break
            c.drawCentredString(W/2, by, bl)
            by -= 6*mm

        cuerpo_start = by - 4*mm

    # ── CUERPO: 2 columnas Merriweather-Regular 11pt interlineado 1.3
    if cuerpo_start > CUERPO_Y + 10*mm:
        lh     = 11 * 1.3 * 0.3528   # interlineado en mm
        col_cw = COL2 - 3*mm
        lines  = wrap_lines(c, cuerpo, col_cw, FTI_R, 11)
        half   = max(1, len(lines) // 2)
        # Separador central
        c.setStrokeColorRGB(*GRIS_L)
        c.setLineWidth(0.5)
        c.line(W/2, cuerpo_start, W/2, CUERPO_Y)
        for col_i in range(2):
            cx2 = M if col_i == 0 else W/2 + 3*mm
            cy2 = cuerpo_start
            chunk = lines[:half] if col_i == 0 else lines[half:]
            c.setFont(FTI_R, 11)
            c.setFillColorRGB(*NEGRO)
            for ln in chunk:
                if cy2 < CUERPO_Y: break
                c.drawString(cx2, cy2, ln)
                cy2 -= lh*mm

    # ── PIE ──────────────────────────────────────────────────────
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, PIE_Y - 2*mm, W - M, PIE_Y - 2*mm)
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawString(M,          PIE_Y - 6*mm, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, PIE_Y - 6*mm, "Edición Impresa  •  Santiago del Estero")
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
    print("=== Diario Info PDF Generator v2.0 ===")
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

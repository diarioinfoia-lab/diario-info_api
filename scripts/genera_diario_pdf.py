#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diario Info - Generador de PDF Edicion Impresa v2.1 - Manual de Estilo implementado: Merriweather titulares, Lato UI, hex exactos, imagen sangrado
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
    """Tapa Diario Info v2.5 - layout absolutamente fijo"""
    W, H = A4   # 595.28 x 841.89 pts  (210 x 297 mm)
    M = 15*mm   # margen lateral

    FUI_R = FONT_T
    FUI_B = FONT_TB
    FTI_B = FONT_MBold
    FTI_R = FONT_MReg

    # Fondo blanco
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ============================================================
    # COORDENADAS Y ABSOLUTAS (en mm desde el fondo de pagina)
    # ============================================================
    Y_CAB       = 291*mm   # cabecera
    Y_LOGO_MID  = 270*mm   # centro del logo
    Y_SUB_LOGO  = 259*mm   # subtitulo "Santiago del Estero"
    Y_FILETE    = 256*mm   # filete azul
    Y_TIT_TOP   = 248*mm   # primera linea del titular
    Y_BAJ_TOP   = 228*mm   # primera linea de bajada
    Y_HERO_TOP  = 218*mm   # tope del box imagen (10mm bajo bajada)
    Y_HERO_BOT  = Y_HERO_TOP - 95*mm   # = 123mm
    Y_SEC_TOP   = Y_HERO_BOT - 2*mm    # tope notas secundarias
    Y_PIE_LINE  = 14*mm    # linea pie de pagina
    Y_PIE_TXT   = 9*mm     # texto pie

    # Dimensiones del box de imagen (fijas)
    HERO_W = 180*mm
    HERO_H = 95*mm
    HERO_X = W/2 - HERO_W/2   # centrado
    # ── 1. CABECERA ──────────────────────────────────────────────
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
    c.drawCentredString(W/2, Y_CAB, cab_line)

    # ── 2. LOGO ──────────────────────────────────────────────────
    c.setFont(FUI_B, 20)
    dw_diario = c.stringWidth("diario", FUI_B, 20)
    dw_info   = c.stringWidth("info",   FUI_B, 20)
    c.setFont(FUI_R, 11)
    dw_com    = c.stringWidth(".com",   FUI_R, 11)
    icon_r    = 8*mm
    gap       = 2*mm
    total_w   = icon_r*2 + gap + dw_diario + dw_info + dw_com
    lx        = W/2 - total_w/2
    draw_logo(c, lx + icon_r, Y_LOGO_MID, r=icon_r, escala=1.0)
    tx = lx + icon_r*2 + gap
    c.setFont(FUI_B, 20)
    c.setFillColorRGB(*AZUL_INST)
    c.drawString(tx,              Y_LOGO_MID - 3.5*mm, "diario")
    c.setFillColorRGB(*NARANJA_C)
    c.drawString(tx + dw_diario,  Y_LOGO_MID - 3.5*mm, "info")
    c.setFont(FUI_R, 11)
    c.setFillColorRGB(*GRIS_N)
    c.drawString(tx + dw_diario + dw_info, Y_LOGO_MID - 1*mm, ".com")
    c.setFont(FUI_R, 10)
    c.setFillColorRGB(*GRIS_N)
    c.drawCentredString(W/2, Y_SUB_LOGO, "Santiago del Estero")

    # ── 3. FILETE DOBLE ──────────────────────────────────────────
    c.setStrokeColorRGB(*AZUL_INST)
    c.setLineWidth(1.5)
    c.line(M, Y_FILETE, W - M, Y_FILETE)
    c.setStrokeColorRGB(*NARANJA_C)
    c.setLineWidth(0.8)
    c.line(M, Y_FILETE - 1.5*mm, W - M, Y_FILETE - 1.5*mm)
    # ── 4. TITULAR PRINCIPAL (sin badge) ─────────────────────────
    nota_p = notas[0] if notas else None
    if nota_p:
        titulo  = limpiar_html(nota_p.get("title", ""))
        bajada  = limpiar_html(nota_p.get("summary", "") or nota_p.get("content", ""))
        img_url = obtener_url_imagen(nota_p.get("image")) if nota_p.get("image") else ""
        # Titular: Merriweather-Bold 22pt negro centrado
        c.setFont(FTI_B, 22)
        c.setFillColorRGB(*NEGRO)
        tit_lines = wrap_lines(c, titulo, W - 2*M, FTI_B, 22)
        ty = Y_TIT_TOP
        for ln in tit_lines[:3]:
            c.drawCentredString(W/2, ty, ln)
            ty -= 8.5*mm
        # Bajada: Merriweather-Regular 12pt #555555
        c.setFont(FTI_R, 12)
        c.setFillColorRGB(*GRIS_TXT)
        baj_lines = wrap_lines(c, bajada, W - 4*M, FTI_R, 12)
        by = Y_BAJ_TOP
        for bl in baj_lines[:2]:
            c.drawCentredString(W/2, by, bl)
            by -= 5*mm

        # ── 5. IMAGEN HERO: box 180x95mm, centrado, sangrado ─────
        if img_url:
            try:
                ir       = ImageReader(img_url)
                inw, inh = ir.getSize()
                sc_w = HERO_W / float(inw)
                sc_h = HERO_H / float(inh)
                sc   = max(sc_w, sc_h)
                dw   = inw * sc
                dh   = inh * sc
                ox   = (dw - HERO_W) / 2.0
                oy   = (dh - HERO_H) / 2.0
                c.saveState()
                clip = c.beginPath()
                clip.rect(HERO_X, Y_HERO_BOT, HERO_W, HERO_H)
                c.clipPath(clip, stroke=0)
                c.drawImage(ir, HERO_X - ox, Y_HERO_BOT - oy, dw, dh)
                c.restoreState()
            except Exception as e:
                print(f"  [hero] {e}")
                c.setFillColorRGB(*GRIS_BG)
                c.rect(HERO_X, Y_HERO_BOT, HERO_W, HERO_H, fill=1, stroke=0)
        else:
            c.setFillColorRGB(*GRIS_BG)
            c.rect(HERO_X, Y_HERO_BOT, HERO_W, HERO_H, fill=1, stroke=0)
    # ── 6. NOTAS SECUNDARIAS - 3 columnas ────────────────────────
    # Categoria: Lato-Bold 11pt azul
    # Titular: Merriweather-Bold 18pt negro (TRIPLICADO en fuerza)
    # Bajada:  Lato-Regular 10pt #666666
    # Imagen:  4:3 con sangrado max(sc_w,sc_h)
    # Separadores: 0.5pt #CCCCCC
    notas_sec = notas[1:4]
    col_n     = 3
    col_w     = (W - 2*M) / col_n
    sec_bot   = Y_PIE_LINE + 3*mm
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
        if img_url_s:
            try:
                ir_s         = ImageReader(img_url_s)
                inw_s, inh_s = ir_s.getSize()
                sc_ws = img_w_s   / float(inw_s)
                sc_hs = img_h_sec / float(inh_s)
                sc_s  = max(sc_ws, sc_hs)
                dws   = inw_s  * sc_s
                dhs   = inh_s  * sc_s
                ox_s  = (dws - img_w_s)   / 2.0
                oy_s  = (dhs - img_h_sec) / 2.0
                c.saveState()
                ps = c.beginPath()
                ps.rect(img_x_s, img_top_s - img_h_sec, img_w_s, img_h_sec)
                c.clipPath(ps, stroke=0)
                c.drawImage(ir_s, img_x_s - ox_s, img_top_s - img_h_sec - oy_s, dws, dhs)
                c.restoreState()
            except Exception as e:
                print(f"  [sec {i}] {e}")
                c.setFillColorRGB(*GRIS_BG)
                c.rect(img_x_s, img_top_s - img_h_sec, img_w_s, img_h_sec, fill=1, stroke=0)
        else:
            c.setFillColorRGB(*GRIS_BG)
            c.rect(img_x_s, img_top_s - img_h_sec, img_w_s, img_h_sec, fill=1, stroke=0)
        # Titular: Merriweather-Bold 18pt negro (3x fuerza)
        tit_s   = limpiar_html(ns.get("title", ""))
        ty_s    = img_top_s - img_h_sec - 3*mm
        c.setFont(FTI_B, 18)
        c.setFillColorRGB(*NEGRO)
        for tsl in wrap_lines(c, tit_s, col_w - 2*pad, FTI_B, 18)[:2]:
            if ty_s < sec_bot + 2*mm: break
            c.drawString(cx + pad, ty_s, tsl)
            ty_s -= 7*mm
        # Bajada: Lato-Regular 10pt #666666
        baj_s = limpiar_html(ns.get("summary", "") or ns.get("content", ""))
        c.setFont(FUI_R, 10)
        c.setFillColorRGB(*GRIS_N)
        for bsl in wrap_lines(c, baj_s, col_w - 2*pad, FUI_R, 10)[:2]:
            if ty_s < sec_bot: break
            c.drawString(cx + pad, ty_s, bsl)
            ty_s -= 4.5*mm

    # ── 7. PIE ────────────────────────────────────────────────────
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, Y_PIE_LINE, W - M, Y_PIE_LINE)
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*GRIS_TXT)
    c.drawString(M,          Y_PIE_TXT, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, Y_PIE_TXT, "Edición Impresa  •  Santiago del Estero")

def generar_pagina_interior(c, nota, num_pag):
    """Genera pagina interior segun Manual de Estilo Diario Info v2.1"""
    W, H = A4
    M    = 15*mm

    FUI_R  = FONT_T      # Lato-Regular
    FUI_B  = FONT_TB     # Lato-Bold
    FTI_B  = FONT_MBold  # Merriweather-Bold
    FTI_R  = FONT_MReg   # Merriweather-Regular

    C_AZUL  = AZUL_INST
    C_NARA  = NARANJA_C
    C_GTXT  = GRIS_TXT
    C_GNEU  = GRIS_N
    C_GL    = GRIS_L

    # Fondo blanco
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ============================================================
    # CABECERA INTERIOR: fecha + ciudad + temp + logo "diarioinfo.com"
    #   Lato-Regular 9pt #555555 centrado
    # ============================================================
    dia_semana = HOY.strftime("%A").capitalize()
    mes        = HOY.strftime("%B").capitalize()
    fecha_txt  = f"{dia_semana} {HOY.day} de {mes} de {HOY.year}"
    cab_txt    = f"{fecha_txt}  |  Santiago del Estero  |  diarioinfo.com  |  Pag. {num_pag}"
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*C_GTXT)
    c.drawCentredString(W/2, H - 7*mm, cab_txt)
    # Linea bajo cabecera
    c.setStrokeColorRGB(*C_GL)
    c.setLineWidth(0.5)
    c.line(M, H - 9*mm, W - M, H - 9*mm)

    # ============================================================
    # BANDA DE CATEGORIA con color institucional
    # ============================================================
    cat = obtener_nombre_categoria(nota.get("category", nota.get("categoryId", "")))
    banda_y = H - 9*mm - 7*mm
    c.setFillColorRGB(*C_AZUL)
    c.rect(M, banda_y, W - 2*M, 5.5*mm, fill=1, stroke=0)
    c.setFont(FUI_B, 8)
    c.setFillColorRGB(*BLANCO)
    c.drawString(M + 3*mm, banda_y + 1.5*mm, cat)

    # ============================================================
    # TITULAR: Merriweather-Bold 18pt negro (notas principales)
    # ============================================================
    titulo = limpiar_html(nota.get("title", ""))
    bajada = limpiar_html(nota.get("summary", "") or nota.get("content", ""))
    cuerpo = limpiar_html(nota.get("content", ""))
    img_url = obtener_url_imagen(nota.get("image")) if nota.get("image") else ""

    tit_y = banda_y - 4*mm
    c.setFont(FTI_B, 18)
    c.setFillColorRGB(*NEGRO)
    tit_lines = wrap_lines(c, titulo, W - 2*M, FTI_B, 18)
    tit_lines = tit_lines[:3]
    for tl in tit_lines:
        c.drawString(M, tit_y, tl)
        tit_y -= 7.5*mm

    # Bajada: Merriweather-Regular 12pt #555555
    c.setFont(FTI_R, 12)
    c.setFillColorRGB(*C_GTXT)
    baj_lines = wrap_lines(c, bajada, W - 2*M, FTI_R, 12)
    baj_lines = baj_lines[:3]
    for bl in baj_lines:
        c.drawString(M, tit_y, bl)
        tit_y -= 5.5*mm

    # ============================================================
    # IMAGEN PRINCIPAL INTERIOR - sangrado proporcional
    #   16:9 ancho completo, escalar con max(sc_w, sc_h)
    #   sin deformacion, sin bordes blancos, recorte centrado
    # ============================================================
    img_top    = tit_y - 4*mm
    img_w      = W - 2*M
    img_h_max  = img_w * (9.0 / 16.0)   # proporcion 16:9

    if img_url:
        try:
            ir       = ImageReader(img_url)
            inw, inh = ir.getSize()
            sc_w = img_w     / float(inw)
            sc_h = img_h_max / float(inh)
            sc   = max(sc_w, sc_h)
            dw   = inw * sc
            dh   = inh * sc
            off_x = (dw - img_w)     / 2.0
            off_y = (dh - img_h_max) / 2.0
            c.saveState()
            p = c.beginPath()
            p.rect(M, img_top - img_h_max, img_w, img_h_max)
            c.clipPath(p, stroke=0)
            c.drawImage(ir,
                        M - off_x,
                        img_top - img_h_max - off_y,
                        dw, dh)
            c.restoreState()
            cuerpo_y = img_top - img_h_max - 6*mm
        except Exception as e:
            print(f"  [interior p{num_pag}] Error imagen: {e}")
            cuerpo_y = img_top
    else:
        cuerpo_y = img_top
    # ============================================================
    # CUERPO: Merriweather-Regular 11pt #000000 interlineado 1.3
    #   2 columnas si el texto es largo, 1 columna si es corto
    # ============================================================
    if not cuerpo:
        cuerpo = bajada
    texto_len = len(cuerpo)
    lh_body   = 11 * 1.3 * 0.352778  # 1.3 interlineado en mm
    avail_h   = cuerpo_y - 20*mm

    if texto_len > 500:
        # 2 columnas
        col_w2  = (W - 2*M - 4*mm) / 2
        # Separador central
        c.setStrokeColorRGB(*C_GL)
        c.setLineWidth(0.5)
        c.line(W/2, cuerpo_y, W/2, cuerpo_y - avail_h)
        for col_i in range(2):
            cx2 = M if col_i == 0 else W/2 + 2*mm
            cy2 = cuerpo_y
            c.setFont(FTI_R, 11)
            c.setFillColorRGB(*NEGRO)
            text_lines = wrap_lines(c, cuerpo, col_w2, FTI_R, 11)
            half = len(text_lines)//2
            chunk = text_lines[:half] if col_i == 0 else text_lines[half:]
            for ln in chunk:
                if cy2 < 20*mm: break
                c.drawString(cx2, cy2, ln)
                cy2 -= lh_body*mm
    else:
        # 1 columna
        cy1 = cuerpo_y
        c.setFont(FTI_R, 11)
        c.setFillColorRGB(*NEGRO)
        text_lines = wrap_lines(c, cuerpo, W - 2*M, FTI_R, 11)
        for ln in text_lines:
            if cy1 < 20*mm: break
            c.drawString(M, cy1, ln)
            cy1 -= lh_body*mm

    # ============================================================
    # PIE DE PAGINA INTERIOR
    #   Linea 0.5pt #CCCCCC + Lato-Regular 9pt #555555
    # ============================================================
    c.setStrokeColorRGB(*C_GL)
    c.setLineWidth(0.5)
    c.line(M, 16*mm, W - M, 16*mm)
    c.setFont(FUI_R, 9)
    c.setFillColorRGB(*C_GTXT)
    c.drawString(M, 12*mm, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, 12*mm, "Edición Impresa  •  Santiago del Estero")

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

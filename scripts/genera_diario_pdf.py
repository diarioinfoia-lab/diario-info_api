#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genera_diario_pdf.py - Generador de Edicion Impresa PDF para Diario Info
Genera PDF A4 de 16 paginas con tapa institucional y paginas interiores.
Obtiene las ultimas 15 notas publicadas del CMS via MongoDB.
"""

import os, sys, io, re, json, subprocess
import urllib.request
from datetime import datetime, timezone, timedelta

# ============================================================
# CONFIGURACION
# ============================================================
MONGO_URI_PRIMARY    = "mongodb+srv://diarioinfoio_db_user:lYcxG4pf5oCOgYnq@cluster0.c621o4c.mongodb.net/diarioinfo-db?retryWrites=true&w=majority"
MONGO_URI_FALLBACK   = "mongodb+srv://diarioinfoia_db_user:lYcxG4pf5oCOgYnq@cluster0.wypjl60.mongodb.net/diario-info-db?retryWrites=true&w=majority"
MONGO_DB_PRIMARY     = "diarioinfo-db"
MONGO_DB_FALLBACK    = "diario-info-db"
MONGO_COLLECTION     = "articles"
MONGO_FILES_COLL     = "files"

SITE_URL = "https://diarioinfo.com"
LEMA = "Informacion Inteligente"
NOMBRE_DIARIO = "Diario Info"

COLOR_AZUL = (0, 51, 102)
COLOR_GRIS = (102, 102, 102)
COLOR_BLANCO = (255, 255, 255)
COLOR_NEGRO = (0, 0, 0)
COLOR_ROJO = (180, 0, 0)

BASE_DIR = os.path.expanduser("~")
OUTPUT_DIR = os.path.join(BASE_DIR, "public_html", "revistas", "diarioinfo")
ASSETS_DIR = os.path.join(BASE_DIR, "public_html", "assets", "branding")
PLANTILLAS_DIR = os.path.join(BASE_DIR, "public_html", "assets", "diarioinfo", "plantillas")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo_diarioinfo.png")
FLIPBOOK_DIR = os.path.join(BASE_DIR, "public_html", "flipbook")

tz = timezone(timedelta(hours=-3))
HOY = datetime.now(tz).strftime("%Y-%m-%d")
HOY_DT = datetime.now(tz)
MESES_ESP = {"January":"enero","February":"febrero","March":"marzo","April":"abril",
    "May":"mayo","June":"junio","July":"julio","August":"agosto","September":"septiembre",
    "October":"octubre","November":"noviembre","December":"diciembre"}
HOY_LABEL = HOY_DT.strftime("%d de %B de %Y")
for eng,esp in MESES_ESP.items():
    HOY_LABEL = HOY_LABEL.replace(eng, esp)

PDF_PATH = os.path.join(OUTPUT_DIR, HOY + ".pdf")

print("=== GENERADOR DE EDICION IMPRESA DIARIO INFO ===")
print(f"Fecha: {HOY_LABEL}")
print(f"PDF: {PDF_PATH}")

# ============================================================
# VERIFICAR E INSTALAR DEPENDENCIAS
# ============================================================
def instalar_si_falta(paquete, nombre_import=None):
    nombre_import = nombre_import or paquete
    try:
        __import__(nombre_import)
    except ImportError:
        print(f"Instalando {paquete}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "-q", paquete])

instalar_si_falta("pymongo[srv]", "pymongo")
instalar_si_falta("reportlab", "reportlab")
instalar_si_falta("Pillow", "PIL")
instalar_si_falta("requests", "requests")

from pymongo import MongoClient
from bson import ObjectId
import requests as req
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm

# ============================================================
# FUENTES
# ============================================================
FONTS_DIR = os.path.join(BASE_DIR, ".fonts_diario")
os.makedirs(FONTS_DIR, exist_ok=True)

def descargar_fuente(nombre, url):
    ruta = os.path.join(FONTS_DIR, nombre + ".ttf")
    if not os.path.exists(ruta):
        try:
            print(f"  Descargando fuente {nombre}...")
            r = req.get(url, timeout=20)
            if r.status_code == 200:
                with open(ruta, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            print(f"  Error fuente {nombre}: {e}")
    return ruta if os.path.exists(ruta) else None

TTF_URLS = {
    "Merriweather-Regular": "https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Regular.ttf",
    "Merriweather-Bold": "https://github.com/google/fonts/raw/main/ofl/merriweather/Merriweather-Bold.ttf",
    "Lato-Regular": "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "Lato-Bold": "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
}

print("Registrando fuentes...")
FUENTES_OK = set()
for fn, furl in TTF_URLS.items():
    ruta = descargar_fuente(fn, furl)
    if ruta:
        try:
            pdfmetrics.registerFont(TTFont(fn, ruta))
            FUENTES_OK.add(fn)
            print(f"  OK: {fn}")
        except Exception as e:
            print(f"  Error registrando {fn}: {e}")

FONT_H = "Merriweather-Bold" if "Merriweather-Bold" in FUENTES_OK else "Helvetica-Bold"
FONT_H2 = "Merriweather-Regular" if "Merriweather-Regular" in FUENTES_OK else "Helvetica"
FONT_T = "Lato-Regular" if "Lato-Regular" in FUENTES_OK else "Helvetica"
FONT_TB = "Lato-Bold" if "Lato-Bold" in FUENTES_OK else "Helvetica-Bold"

# ============================================================
# MONGODB - Obtener notas
# ============================================================
def obtener_notas(limite=15):
    """Obtiene las ultimas notas publicadas, igual que la API del CMS.
    Intenta primero el cluster principal (c621o4c / diarioinfo-db),
    y hace fallback al cluster secundario (wypjl60 / diario-info-db)."""
    configs = [
        (MONGO_URI_PRIMARY, MONGO_DB_PRIMARY),
        (MONGO_URI_FALLBACK, MONGO_DB_FALLBACK),
    ]
    for uri, db_name in configs:
        print(f"Intentando MongoDB: {db_name}...")
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=8000)
            db = client[db_name]
            col_art = db[MONGO_COLLECTION]
            col_files = db[MONGO_FILES_COLL]
            # Verificar conexion
            client.server_info()
            cursor = col_art.find(
                {"status": "published"},
                {"_id":1,"title":1,"excerpt":1,"content":1,"imageId":1,
                 "slug":1,"tags":1,"category":1,"publishedAt":1,"sourceUrl":1}
            ).sort([("priority", -1), ("publishedAt", -1)]).limit(limite)
            notas = []
            for doc in cursor:
                cat_raw = str(doc.get("category", "NOTICIAS"))
                cat = cat_raw if len(cat_raw) < 30 else "NOTICIAS"
                nota = {
                    "id": str(doc["_id"]),
                    "titulo": doc.get("title", "Sin titulo"),
                    "copete": doc.get("excerpt", ""),
                    "cuerpo": doc.get("content", ""),
                    "slug": doc.get("slug", ""),
                    "tags": doc.get("tags", []),
                    "categoria": cat,
                    "publicado": doc.get("publishedAt", ""),
                    "fuente_url": doc.get("sourceUrl", ""),
                    "imagen_url": None,
                    "imagen_credito": ""
                }
                image_id = doc.get("imageId")
                if image_id and col_files is not None:
                    try:
                        file_doc = col_files.find_one({"_id": ObjectId(str(image_id))})
                        if file_doc:
                            img_url = file_doc.get("fileUrl", file_doc.get("thumbnailUrl",""))
                            if img_url and img_url.startswith("/"):
                                img_url = "https://ia.diarioinfo.com" + img_url
                            nota["imagen_url"] = img_url
                            nota["imagen_credito"] = file_doc.get("creditSource","")
                    except Exception:
                        pass
                notas.append(nota)
            print(f"  {len(notas)} notas obtenidas desde {db_name}")
            client.close()
            return notas
        except Exception as e:
            print(f"  Error con {db_name}: {e}")
            try:
                client.close()
            except Exception:
                pass
    print("  ERROR: No se pudo conectar a ningÃÂºn cluster MongoDB")
    return []
# ============================================================
# DATOS EXTERNOS
# ============================================================
def obtener_cotizaciones():
    try:
        r = req.get("https://api.bluelytics.com.ar/v2/latest", timeout=5)
        if r.status_code == 200:
            d = r.json()
            of = d.get("oficial", {})
            bl = d.get("blue", {})
            return {"dolar_oficial": f"Oficial: ${of.get(chr(118)+chr(97)+chr(108)+chr(117)+chr(101)+chr(95)+chr(115)+chr(101)+chr(108)+chr(108), chr(45)+chr(45))}",
                    "dolar_blue": f"Blue: ${bl.get(chr(118)+chr(97)+chr(108)+chr(117)+chr(101)+chr(95)+chr(115)+chr(101)+chr(108)+chr(108), chr(45)+chr(45))}"}
    except Exception:
        pass
    return {"dolar_oficial": "Dolar Oficial: --", "dolar_blue": "Dolar Blue: --"}

def obtener_clima():
    try:
        r = req.get("https://wttr.in/Santiago+del+Estero?format=%25C+%25t", timeout=5)
        if r.status_code == 200:
            return r.text.strip()
    except Exception:
        pass
    return "Santiago del Estero"

# ============================================================
# DESCARGA DE IMAGEN
# ============================================================
def descargar_imagen(url, max_w=None, max_h=None):
    """Descarga imagen y retorna objeto PIL Image o None"""
    if not url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0 DiarioInfo-PDF-Generator/1.0"}
        r = req.get(url, headers=headers, timeout=15, stream=True)
        if r.status_code == 200:
            img = PILImage.open(io.BytesIO(r.content))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            if max_w and max_h:
                img.thumbnail((max_w, max_h), PILImage.LANCZOS)
            return img
    except Exception as e:
        print(f"    Error img {url[:60]}: {e}")
    return None

def pil_to_imagereader(pil_img):
    """Convierte PIL Image a ReportLab ImageReader"""
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return ImageReader(buf)

def limpiar_html(texto):
    """Elimina etiquetas HTML y limpia el texto"""
    if not texto:
        return ""
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"&nbsp;", " ", texto)
    texto = re.sub(r"&amp;", "&", texto)
    texto = re.sub(r"&lt;", "<", texto)
    texto = re.sub(r"&gt;", ">", texto)
    texto = re.sub(r"&quot;", chr(34), texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto

def truncar(texto, max_chars):
    """Trunca texto con elipsis"""
    texto = limpiar_html(texto)
    if len(texto) <= max_chars:
        return texto
    return texto[:max_chars-3].rsplit(" ", 1)[0] + "..."

# ============================================================
# GENERADOR DE TAPA (Pagina 1)
# ============================================================
def generar_tapa(c, notas, cotizaciones, clima):
    """Tapa institucional fiel al diseno de referencia.
    Estructura: barra-info | logo | linea-azul | TITULAR-GRANDE | bajada | imagen-principal | separador | 3-columnas | pie
    """
    from reportlab.lib.units import mm
    FONT_N  = "Lato-Regular"  if "Lato-Regular"  in FUENTES_OK else "Helvetica"
    W = A4[0]
    H = A4[1]
    M = 12 * mm       # margen exterior
    AW = W - 2 * M   # ancho util

    # ── COLORES ─────────────────────────────────────
    AZUL    = (0.0,   0.20,  0.40)   # #003366
    NARANJA = (0.957, 0.486, 0.125)  # #F47C20
    GRIS    = (0.40,  0.40,  0.40)
    GRIS_L  = (0.80,  0.80,  0.80)
    NEGRO   = (0,     0,     0)
    BLANCO  = (1,     1,     1)

    # Fondo blanco
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    y = H - 6 * mm

    # ── 1. BARRA SUPERIOR INFO ────────────────────────
    dol = cotizaciones.get("dolar_oficial", "Dolar: --")
    blu = cotizaciones.get("dolar_blue", "Blue: --")
    clim = clima if clima else ""
    barra = HOY_LABEL + "   |   Santiago del Estero " + clim + "   |   " + dol + "   |   " + blu
    c.setFont(FONT_N, 7.5)
    c.setFillColorRGB(0.33, 0.33, 0.33)
    c.drawCentredString(W / 2, y - 3*mm, barra)
    y -= 8 * mm

    # Linea gris bajo barra
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.4)
    c.line(M, y, W - M, y)
    y -= 4 * mm

    # ── 2. LOGO ───────────────────────────────────────
    logo_cy = y - 12 * mm
    # Icono "play" circular: circulo degradado azul-naranja con triangulo blanco
    R = 10 * mm
    cx_icon = W / 2 - 48 * mm
    # Semicirculo izq azul
    c.setFillColorRGB(*AZUL)
    c.circle(cx_icon, logo_cy, R, fill=1, stroke=0)
    # Semicirculo der naranja
    c.setFillColorRGB(*NARANJA)
    c.wedge(cx_icon - R, logo_cy - R, cx_icon + R, logo_cy + R, -90, 180, fill=1, stroke=0)
    # Triangulo play blanco
    path = c.beginPath()
    path.moveTo(cx_icon - 3*mm, logo_cy + 5*mm)
    path.lineTo(cx_icon - 3*mm, logo_cy - 5*mm)
    path.lineTo(cx_icon + 5*mm, logo_cy)
    path.close()
    c.setFillColorRGB(*BLANCO)
    c.drawPath(path, fill=1, stroke=0)

    # Texto logo
    tx = cx_icon + R + 3 * mm
    c.setFont(FONT_TB, 28)
    c.setFillColorRGB(*AZUL)
    dw = c.stringWidth("diario", FONT_TB, 28)
    c.drawString(tx, logo_cy - 5*mm, "diario")
    c.setFont(FONT_TB, 30)
    c.setFillColorRGB(*NARANJA)
    iw = c.stringWidth("info", FONT_TB, 30)
    c.drawString(tx + dw, logo_cy - 6*mm, "info")
    c.setFont(FONT_N, 16)
    c.setFillColorRGB(*GRIS)
    c.drawString(tx + dw + iw, logo_cy - 3*mm, ".com")

    # Subtitulo "Santiago del Estero"
    c.setFont(FONT_N, 9)
    c.setFillColorRGB(*GRIS)
    c.drawCentredString(W / 2, logo_cy - 8*mm, "Santiago del Estero")

    y = logo_cy - 12 * mm

    # Linea azul bajo logo
    c.setStrokeColorRGB(*AZUL)
    c.setLineWidth(1.5)
    c.line(M, y, W - M, y)
    y -= 6 * mm

    # ── 3. NOTA PRINCIPAL ─────────────────────────────
    PIE_H = 10 * mm
    nota_p = notas[0] if notas else {}

    # Titulo principal GRANDE
    titulo = nota_p.get("titulo", "")[:200]
    palabras = titulo.split()
    lineas_t = []
    la = ""
    for p in palabras:
        pr = (la + " " + p).strip()
        if c.stringWidth(pr, FONT_TB, 26) < AW:
            la = pr
        else:
            if la: lineas_t.append(la)
            la = p
    if la: lineas_t.append(la)
    lineas_t = lineas_t[:3]

    c.setFillColorRGB(*NEGRO)
    c.setFont(FONT_TB, 26)
    for lt in lineas_t:
        c.drawString(M, y, lt)
        y -= 9.5 * mm
    y -= 1 * mm

    # Bajada / copete centrado
    copete = nota_p.get("copete", "")[:220]
    palabras_c = copete.split()
    lineas_cop = []
    la_c = ""
    for p in palabras_c:
        pr = (la_c + " " + p).strip()
        if c.stringWidth(pr, FONT_N, 11) < AW * 0.9:
            la_c = pr
        else:
            if la_c: lineas_cop.append(la_c)
            la_c = p
    if la_c: lineas_cop.append(la_c)
    lineas_cop = lineas_cop[:2]

    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.setFont(FONT_N, 11)
    for lc in lineas_cop:
        c.drawCentredString(W / 2, y, lc)
        y -= 5.5 * mm
    y -= 3 * mm

    # ── 4. IMAGEN PRINCIPAL (ancho completo) ──────────
    # Calcular zona disponible para imagen + secundarias + pie
    zona_img = (y - M - PIE_H - 50*mm) * 0.60  # 60% para imagen
    img_h = max(zona_img, 35*mm)
    img_y = y - img_h
    img_url = nota_p.get("imagen_url")
    img_path = descargar_imagen(img_url) if img_url else None
    if img_path and os.path.exists(img_path):
        try:
            c.drawImage(img_path, M, img_y, AW, img_h, preserveAspectRatio=True, anchor="c")
        except Exception:
            c.setFillColorRGB(0.55, 0.65, 0.75)
            c.rect(M, img_y, AW, img_h, fill=1, stroke=0)
    else:
        c.setFillColorRGB(0.55, 0.65, 0.75)
        c.rect(M, img_y, AW, img_h, fill=1, stroke=0)
    y = img_y - 4 * mm

    # Linea separadora gris
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.5)
    c.line(M, y, W - M, y)
    y -= 3 * mm

    # ── 5. TRES COLUMNAS SECUNDARIAS ──────────────────
    cw = AW / 3
    notas_s = list(notas[1:4]) + [{}] * max(0, 3 - len(notas[1:4]))
    y_bot = M + PIE_H + 2*mm
    zona_s = y - y_bot
    img_sh = zona_s * 0.46

    for i, ns in enumerate(notas_s):
        cx = M + i * cw
        cy = y
        # separador vertical
        if i > 0:
            c.setStrokeColorRGB(*GRIS_L)
            c.setLineWidth(0.4)
            c.line(cx, y + 1*mm, cx, y_bot)

        if not ns: continue

        tit_s = ns.get("titulo", "")[:100]
        cop_s = ns.get("copete", "")[:120]
        img_us = ns.get("imagen_url")

        # Titulo de seccion (categoria) en azul/naranja
        cat_s = ns.get("categoria", "NOTICIAS")[:20].upper()
        c.setFont(FONT_TB, 8)
        c.setFillColorRGB(*AZUL)
        c.drawString(cx + 2*mm, cy, cat_s)
        cy -= 4.5 * mm

        # Titular bold col
        pals = tit_s.split()
        lins = []
        la_s = ""
        inner = cw - 5*mm
        for p in pals:
            pr = (la_s + " " + p).strip()
            if c.stringWidth(pr, FONT_TB, 11) < inner:
                la_s = pr
            else:
                if la_s: lins.append(la_s)
                la_s = p
        if la_s: lins.append(la_s)
        lins = lins[:3]
        c.setFont(FONT_TB, 11)
        c.setFillColorRGB(*NEGRO)
        for ls in lins:
            c.drawString(cx + 2*mm, cy, ls)
            cy -= 4.8 * mm
        cy -= 1 * mm

        # Bajada gris pequeña
        palsc = cop_s.split()
        linsc = []
        la_sc = ""
        for p in palsc:
            pr = (la_sc + " " + p).strip()
            if c.stringWidth(pr, FONT_N, 8) < inner:
                la_sc = pr
            else:
                if la_sc: linsc.append(la_sc)
                la_sc = p
        if la_sc: linsc.append(la_sc)
        linsc = linsc[:2]
        c.setFont(FONT_N, 8)
        c.setFillColorRGB(*GRIS)
        for lsc in linsc:
            c.drawString(cx + 2*mm, cy, lsc)
            cy -= 4 * mm
        cy -= 2 * mm

        # Imagen al fondo de la columna
        img_ps = descargar_imagen(img_us) if img_us else None
        avail = cy - y_bot - 1*mm
        if avail > 8*mm:
            if img_ps and os.path.exists(img_ps):
                try:
                    c.drawImage(img_ps, cx + 2*mm, cy - avail, cw - 4*mm, avail, preserveAspectRatio=True, anchor="c")
                except Exception:
                    c.setFillColorRGB(0.75, 0.75, 0.75)
                    c.rect(cx + 2*mm, cy - avail, cw - 4*mm, avail, fill=1, stroke=0)
            else:
                c.setFillColorRGB(0.75, 0.75, 0.75)
                c.rect(cx + 2*mm, cy - avail, cw - 4*mm, avail, fill=1, stroke=0)

    # ── 6. PIE DE PAGINA ──────────────────────────────
    pie_y = M + 1.5*mm
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.4)
    c.line(M, pie_y + 5*mm, W - M, pie_y + 5*mm)
    c.setFont(FONT_N, 8)
    c.setFillColorRGB(0.33, 0.33, 0.33)
    c.drawString(M, pie_y + 1*mm, "www.diarioinfo.com.ar")
    c.drawRightString(W - M, pie_y + 1*mm, "Edicion Impresa  •  Santiago del Estero")
    c.showPage()
def generar_pagina_interior(c, nota, num_pagina):
    """Pagina interior: cabecera azul con logo, seccion, titulo, imagen, dos columnas, pie."""
    from reportlab.lib.units import mm
    FONT_N = "Lato-Regular" if "Lato-Regular" in FUENTES_OK else "Helvetica"
    W, H = A4
    M = 12 * mm
    AW = W - 2 * M
    AZUL    = (0.0,   0.20,  0.40)
    NARANJA = (0.957, 0.486, 0.125)
    GRIS    = (0.40,  0.40,  0.40)
    GRIS_L  = (0.80,  0.80,  0.80)
    NEGRO   = (0,     0,     0)
    BLANCO  = (1,     1,     1)

    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── CABECERA AZUL ─────────────────────────────────
    CAB_H = 14 * mm
    c.setFillColorRGB(*AZUL)
    c.rect(0, H - CAB_H, W, CAB_H, fill=1, stroke=0)

    # Logo mini en la cabecera
    c.setFont(FONT_TB, 13)
    c.setFillColorRGB(*BLANCO)
    logo_x = M
    c.drawString(logo_x, H - CAB_H + 4*mm, "diario")
    dw = c.stringWidth("diario", FONT_TB, 13)
    c.setFillColorRGB(*NARANJA)
    c.drawString(logo_x + dw, H - CAB_H + 4*mm, "info")
    iw = c.stringWidth("info", FONT_TB, 13)
    c.setFont(FONT_N, 9)
    c.setFillColorRGB(*BLANCO)
    c.drawString(logo_x + dw + iw, H - CAB_H + 5*mm, ".com")

    # Fecha en cabecera derecha
    c.setFont(FONT_N, 8)
    c.setFillColorRGB(*BLANCO)
    c.drawRightString(W - M, H - CAB_H + 4.5*mm, HOY_LABEL)

    y = H - CAB_H - 5 * mm

    # ── SECCION / CATEGORIA ───────────────────────────
    cat = nota.get("categoria", "NOTICIAS")[:25].upper()
    c.setFont(FONT_TB, 9)
    c.setFillColorRGB(*NARANJA)
    c.drawString(M, y, cat)
    y -= 6 * mm

    # ── TITULO PRINCIPAL ──────────────────────────────
    titulo = nota.get("titulo", "")[:200]
    palabras = titulo.split()
    lineas_t = []
    la = ""
    for p in palabras:
        pr = (la + " " + p).strip()
        if c.stringWidth(pr, FONT_TB, 20) < AW:
            la = pr
        else:
            if la: lineas_t.append(la)
            la = p
    if la: lineas_t.append(la)
    lineas_t = lineas_t[:3]

    c.setFont(FONT_TB, 20)
    c.setFillColorRGB(*NEGRO)
    for lt in lineas_t:
        c.drawString(M, y, lt)
        y -= 7.5 * mm
    y -= 2 * mm

    # ── BAJADA / COPETE ───────────────────────────────
    copete = nota.get("copete", "")[:300]
    palabras_c = copete.split()
    lineas_cop = []
    la_c = ""
    for p in palabras_c:
        pr = (la_c + " " + p).strip()
        if c.stringWidth(pr, FONT_N, 11) < AW:
            la_c = pr
        else:
            if la_c: lineas_cop.append(la_c)
            la_c = p
    if la_c: lineas_cop.append(la_c)
    lineas_cop = lineas_cop[:2]

    c.setFont(FONT_N, 11)
    c.setFillColorRGB(*GRIS)
    for lc in lineas_cop:
        c.drawString(M, y, lc)
        y -= 5.5 * mm
    y -= 3 * mm

    # ── IMAGEN ────────────────────────────────────────
    img_h = min(55 * mm, (y - M - 12*mm) * 0.42)
    img_url = nota.get("imagen_url")
    img_path = descargar_imagen(img_url) if img_url else None
    if img_h > 15*mm:
        if img_path and os.path.exists(img_path):
            try:
                c.drawImage(img_path, M, y - img_h, AW * 0.60, img_h, preserveAspectRatio=True, anchor="c")
            except Exception:
                c.setFillColorRGB(0.75, 0.75, 0.75)
                c.rect(M, y - img_h, AW * 0.60, img_h, fill=1, stroke=0)
        else:
            c.setFillColorRGB(0.78, 0.82, 0.88)
            c.rect(M, y - img_h, AW * 0.60, img_h, fill=1, stroke=0)
    y -= (img_h + 4*mm)

    # ── LINEA DIVISORIA ───────────────────────────────
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.4)
    c.line(M, y, W - M, y)
    y -= 4 * mm

    # ── CUERPO EN DOS COLUMNAS ────────────────────────
    cuerpo = nota.get("cuerpo", "") or nota.get("copete", "")
    # Limpiar HTML basico
    import re
    cuerpo = re.sub(r"<[^>]+>", " ", cuerpo)
    cuerpo = re.sub(r"\s+", " ", cuerpo).strip()
    cuerpo = cuerpo[:2000]

    col_w  = AW / 2 - 3*mm
    col_gap = 6 * mm
    col_x  = [M, M + AW / 2 + col_gap / 2]
    y_bot  = M + 12*mm
    zona   = y - y_bot
    if zona < 10*mm:
        zona = 10*mm
    lh = 4.5 * mm
    max_lineas = int(zona / lh) * 2

    palabras_b = cuerpo.split()
    lineas_b = []
    la_b = ""
    for p in palabras_b:
        pr = (la_b + " " + p).strip()
        if c.stringWidth(pr, FONT_N, 9.5) < col_w:
            la_b = pr
        else:
            if la_b: lineas_b.append(la_b)
            la_b = p
    if la_b: lineas_b.append(la_b)
    lineas_b = lineas_b[:max_lineas]

    col_lineas = int(len(lineas_b) / 2) + 1
    c.setFont(FONT_N, 9.5)
    c.setFillColorRGB(*NEGRO)
    for col_i in range(2):
        cy = y
        start = col_i * col_lineas
        end   = start + col_lineas
        for lb in lineas_b[start:end]:
            if cy < y_bot: break
            c.drawString(col_x[col_i], cy, lb)
            cy -= lh

    # ── PIE DE PAGINA ─────────────────────────────────
    pie_y = M + 1.5*mm
    c.setStrokeColorRGB(*GRIS_L)
    c.setLineWidth(0.4)
    c.line(M, pie_y + 5*mm, W - M, pie_y + 5*mm)
    c.setFont(FONT_N, 7.5)
    c.setFillColorRGB(*GRIS)
    c.drawString(M, pie_y + 1*mm, "www.diarioinfo.com.ar")
    c.drawCentredString(W / 2, pie_y + 1*mm, "diarioinfo.com  |  Informacion Inteligente")
    c.drawRightString(W - M, pie_y + 1*mm, "Pagina " + str(num_pagina))
    c.showPage()
def generar_pdf():
    # Crear directorios necesarios
    for d in [OUTPUT_DIR, ASSETS_DIR, PLANTILLAS_DIR, FLIPBOOK_DIR]:
        os.makedirs(d, exist_ok=True)
    print(f"Directorios creados.")
    # Obtener notas
    notas = obtener_notas(15)
    if not notas:
        print("ERROR: No se pudieron obtener notas del CMS.")
        return None
    # Obtener datos externos
    print("Obteniendo cotizaciones...")
    cotizaciones = obtener_cotizaciones()
    print(f"  {cotizaciones}")
    print("Obteniendo clima...")
    clima = obtener_clima()
    print(f"  {clima}")
    # Crear PDF
    print(f"Generando PDF: {PDF_PATH}")
    c = pdfcanvas.Canvas(PDF_PATH, pagesize=A4)
    c.setTitle(f"Diario Info - Edicion Impresa {HOY_LABEL}")
    c.setAuthor("DiarioInfo - Generador Automatico")
    c.setSubject(f"Edicion impresa {HOY}")
    # --- PAGINA 1: TAPA ---
    print("Generando tapa...")
    generar_tapa(c, notas, cotizaciones, clima)
    c.showPage()
    # --- PAGINAS INTERIORES (notas 1..14, max 15 paginas) ---
    notas_interiores = notas[1:15]
    for i, nota in enumerate(notas_interiores):
        num_pag = i + 2
        print(f"Generando pagina {num_pag}: {nota[chr(116)+chr(105)+chr(116)+chr(117)+chr(108)+chr(111)][:50]}...")
        generar_pagina_interior(c, nota, num_pag)
        c.showPage()
    # Guardar PDF
    c.save()
    print(f"")
    print(f"PDF generado exitosamente!")
    print(f"Archivo: {PDF_PATH}")
    import os as _os
    size = _os.path.getsize(PDF_PATH) / 1024
    print(f"Tamano: {size:.1f} KB")
    return PDF_PATH

# ============================================================
# FLIPBOOK HTML
# ============================================================
def generar_flipbook(pdf_path):
    """Genera el HTML del flipbook interactivo usando PDF.js"""
    pdf_filename = os.path.basename(pdf_path)
    pdf_url = f"/revistas/diarioinfo/{pdf_filename}"
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Diario Info - Edicion Impresa {HOY_LABEL}</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:#1a1a2e; font-family:Arial,sans-serif; color:#fff; }}
        .header {{ background:#003366; padding:15px 20px; display:flex; align-items:center; justify-content:space-between; }}
        .header h1 {{ font-size:24px; color:#fff; }}
        .header p {{ font-size:12px; color:#ccc; }}
        .controls {{ background:#0f3460; padding:10px 20px; display:flex; gap:10px; align-items:center; justify-content:center; }}
        .controls button {{ background:#003366; color:#fff; border:none; padding:8px 16px; cursor:pointer; border-radius:4px; font-size:13px; }}
        .controls button:hover {{ background:#0055a5; }}
        .controls span {{ color:#ccc; font-size:13px; }}
        .viewer {{ display:flex; justify-content:center; padding:20px; }}
        canvas {{ max-width:100%; border:2px solid #333; box-shadow:0 4px 20px rgba(0,0,0,0.5); }}
        .footer {{ background:#003366; padding:12px 20px; text-align:center; font-size:12px; color:#ccc; }}
        .download-btn {{ display:inline-block; background:#c00; color:#fff; padding:8px 20px; text-decoration:none; border-radius:4px; margin:10px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>DIARIO INFO</h1>
            <p>Informacion Inteligente | {HOY_LABEL.title()}</p>
        </div>
        <div>
            <a href="{pdf_url}" download class="download-btn">Descargar PDF</a>
        </div>
    </div>
    <div class="controls">
        <button onclick="anteriorPagina()">Anterior</button>
        <span id="info-pagina">Pagina <span id="pag-actual">1</span> de <span id="total-pag">--</span></span>
        <button onclick="siguientePagina()">Siguiente</button>
        <button onclick="ampliar()">+</button>
        <button onclick="reducir()">-</button>
    </div>
    <div class="viewer">
        <canvas id="pdf-canvas"></canvas>
    </div>
    <div class="footer">
        <p>{SITE_URL} | Edicion Impresa {HOY} | Todos los derechos reservados</p>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
    <script>
        pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        let pdfDoc = null, currentPage = 1, scale = 1.2;
        const canvas = document.getElementById("pdf-canvas");
        const ctx = canvas.getContext("2d");
        async function cargarPDF() {{
            pdfDoc = await pdfjsLib.getDocument("{pdf_url}").promise;
            document.getElementById("total-pag").textContent = pdfDoc.numPages;
            renderPagina(1);
        }}
        async function renderPagina(num) {{
            const page = await pdfDoc.getPage(num);
            const vp = page.getViewport({{ scale: scale }});
            canvas.width = vp.width;
            canvas.height = vp.height;
            await page.render({{ canvasContext: ctx, viewport: vp }}).promise;
            document.getElementById("pag-actual").textContent = num;
        }}
        function anteriorPagina() {{ if(currentPage > 1) {{ currentPage--; renderPagina(currentPage); }} }}
        function siguientePagina() {{ if(currentPage < pdfDoc.numPages) {{ currentPage++; renderPagina(currentPage); }} }}
        function ampliar() {{ scale = Math.min(scale+0.2, 3); renderPagina(currentPage); }}
        function reducir() {{ scale = Math.max(scale-0.2, 0.5); renderPagina(currentPage); }}
        cargarPDF();
    </script>
</body>
</html>"""
    flipbook_path = os.path.join(FLIPBOOK_DIR, f"{HOY}.html")
    with open(flipbook_path, "w", encoding="utf-8") as f:
        f.write(html)
    # Crear index.html que redirige al ultimo numero
    index_path = os.path.join(FLIPBOOK_DIR, "index.html")
    redirect_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0; url=./{HOY}.html">
<title>Diario Info - Edicion Impresa</title>
</head><body><p>Redirigiendo...</p></body></html>"""
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(redirect_html)
    print(f"Flipbook generado: {flipbook_path}")
    return flipbook_path

# ============================================================
# EJECUCION PRINCIPAL
# ============================================================
if __name__ == "__main__":
    pdf = generar_pdf()
    if pdf:
        print("Generando flipbook HTML...")
        flipbook = generar_flipbook(pdf)
        print("")
        print("=== COMPLETADO ===")
        print(f"PDF:      {pdf}")
        print(f"Flipbook: {flipbook}")
        print(f"Acceso:   {SITE_URL}/flipbook/{HOY}.html")
    else:
        print("ERROR: No se pudo generar el PDF")
        sys.exit(1)
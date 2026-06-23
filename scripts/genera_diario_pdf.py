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
MONGO_URI = "mongodb+srv://diarioinfoio_db_user:lYcxG4pf5oCOgYnq@cluster0.c621o4c.mongodb.net/?retryWrites=true&w=majority"
MONGO_DB = "diarioinfo-db"
MONGO_COLLECTION = "articles"
MONGO_FILES_COLLECTION = "files"

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
    print("Conectando a MongoDB...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        db = client[MONGO_DB]
        col_art = db[MONGO_COLLECTION]
        col_files = db[MONGO_FILES_COLLECTION]
        cursor = col_art.find(
            {"status": "published"},
            {"_id":1,"title":1,"excerpt":1,"content":1,"imageId":1,
             "slug":1,"tags":1,"category":1,"publishedAt":1,"sourceUrl":1}
        ).sort("publishedAt", -1).limit(limite)
        notas = []
        for doc in cursor:
            nota = {
                "id": str(doc["_id"]),
                "titulo": doc.get("title", "Sin titulo"),
                "copete": doc.get("excerpt", ""),
                "cuerpo": doc.get("content", ""),
                "slug": doc.get("slug", ""),
                "tags": doc.get("tags", []),
                "categoria": doc.get("category", "General"),
                "url_original": doc.get("sourceUrl", SITE_URL),
                "imagen_url": None,
                "imagen_credito": ""
            }
            image_id = doc.get("imageId")
            if image_id and col_files is not None:
                try:
                    file_doc = col_files.find_one({"_id": ObjectId(str(image_id))})
                    if file_doc:
                        nota["imagen_url"] = file_doc.get("fileUrl", file_doc.get("thumbnailUrl",""))
                        nota["imagen_credito"] = file_doc.get("creditSource","")
                except Exception:
                    pass
            notas.append(nota)
        print(f"  {len(notas)} notas obtenidas")
        client.close()
        return notas
    except Exception as e:
        print(f"  Error MongoDB: {e}")
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
    """Genera la tapa del diario - pagina 1 del PDF"""
    w, h = PAGE_W, PAGE_H
    # --- CABECERA azul institucional ---
    c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
    c.rect(0, h - 35*mm, w, 35*mm, fill=1, stroke=0)
    # Logo (si existe)
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(LOGO_PATH, MARGIN, h - 32*mm, width=60*mm, height=28*mm,
                       preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    # Nombre del diario (si no hay logo)
    else:
        c.setFillColorRGB(1, 1, 1)
        c.setFont(FONT_H, 28)
        c.drawString(MARGIN, h - 20*mm, NOMBRE_DIARIO.upper())
    # Lema
    c.setFillColorRGB(1, 1, 1)
    c.setFont(FONT_T, 10)
    c.drawRightString(w - MARGIN, h - 12*mm, LEMA.upper())
    # Fecha
    c.setFont(FONT_T, 9)
    c.drawRightString(w - MARGIN, h - 20*mm, HOY_LABEL.title())
    # --- BARRA INFO (clima/cotizaciones) ---
    c.setFillColorRGB(*[x/255 for x in COLOR_NEGRO])
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.rect(0, h - 43*mm, w, 8*mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(FONT_T, 8)
    info_txt = f"  Clima: {clima}   |   {cotizaciones.get(chr(100)+chr(111)+chr(108)+chr(97)+chr(114)+chr(95)+chr(111)+chr(102)+chr(105)+chr(99)+chr(105)+chr(97)+chr(108), chr(45)+chr(45))}   |   {cotizaciones.get(chr(100)+chr(111)+chr(108)+chr(97)+chr(114)+chr(95)+chr(98)+chr(108)+chr(117)+chr(101), chr(45)+chr(45))}"
    c.drawString(MARGIN, h - 39*mm, info_txt)
    c.drawRightString(w - MARGIN, h - 39*mm, "Edicion Impresa Digital")
    # --- NOTA PRINCIPAL (nota[0]) ---
    nota_principal = notas[0] if notas else None
    y_start = h - 44*mm
    if nota_principal:
        # Imagen principal grande
        img_h = 85*mm
        img_w = w - 2*MARGIN
        img_y = y_start - img_h
        if nota_principal.get("imagen_url"):
            img = descargar_imagen(nota_principal["imagen_url"], int(img_w*3.78), int(img_h*3.78))
            if img:
                ir = pil_to_imagereader(img)
                c.drawImage(ir, MARGIN, img_y, width=img_w, height=img_h,
                           preserveAspectRatio=True, mask="auto")
            else:
                # Placeholder azul
                c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
                c.rect(MARGIN, img_y, img_w, img_h, fill=1, stroke=0)
        else:
            c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
            c.rect(MARGIN, img_y, img_w, img_h, fill=1, stroke=0)
        # Titulo principal - grande y bold
        c.setFillColorRGB(0, 0, 0)
        titulo = truncar(nota_principal["titulo"], 120)
        c.setFont(FONT_H, 22)
        y_titulo = img_y - 3*mm
        # Ajuste de texto multilinea manual
        palabras = titulo.split()
        linea = ""
        lineas_titulo = []
        max_chars_ln = 55
        for p in palabras:
            if len(linea) + len(p) + 1 <= max_chars_ln:
                linea = (linea + " " + p).strip()
            else:
                lineas_titulo.append(linea)
                linea = p
        if linea:
            lineas_titulo.append(linea)
        for i, ln in enumerate(lineas_titulo[:3]):
            c.drawString(MARGIN, y_titulo - i*9*mm, ln)
        y_copete = y_titulo - (min(len(lineas_titulo), 3))*9*mm - 4*mm
        # Copete/bajada
        if nota_principal.get("copete"):
            copete = truncar(nota_principal["copete"], 200)
            c.setFont(FONT_T, 11)
            c.setFillColorRGB(*[x/255 for x in COLOR_GRIS])
            pals = copete.split()
            lin = ""
            lins = []
            for p in pals:
                if len(lin) + len(p) + 1 <= 80:
                    lin = (lin + " " + p).strip()
                else:
                    lins.append(lin)
                    lin = p
            if lin: lins.append(lin)
            for i, ln in enumerate(lins[:2]):
                c.drawString(MARGIN, y_copete - i*5*mm, ln)
            y_copete -= len(lins[:2]) * 5*mm + 3*mm
        # Linea separadora roja
        c.setStrokeColorRGB(*[x/255 for x in COLOR_ROJO])
        c.setLineWidth(1.5)
        c.line(MARGIN, y_copete - 2*mm, w - MARGIN, y_copete - 2*mm)
        y_notas_sec = y_copete - 5*mm
    else:
        y_notas_sec = h - 100*mm
    # --- NOTAS SECUNDARIAS (notas 1,2,3) en 3 columnas ---
    notas_sec = notas[1:4] if len(notas) > 1 else []
    col_w = (w - 2*MARGIN - 2*4*mm) / 3
    for i, ns in enumerate(notas_sec):
        x_col = MARGIN + i * (col_w + 4*mm)
        # Imagen pequena
        img_sec_h = 28*mm
        y_img = y_notas_sec - img_sec_h
        if ns.get("imagen_url"):
            img2 = descargar_imagen(ns["imagen_url"], int(col_w*3.78), int(img_sec_h*3.78))
            if img2:
                ir2 = pil_to_imagereader(img2)
                c.drawImage(ir2, x_col, y_img, width=col_w, height=img_sec_h,
                           preserveAspectRatio=True, mask="auto")
            else:
                c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
                c.rect(x_col, y_img, col_w, img_sec_h, fill=1, stroke=0)
        else:
            c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
            c.rect(x_col, y_img, col_w, img_sec_h, fill=1, stroke=0)
        # Categoria tag
        c.setFillColorRGB(*[x/255 for x in COLOR_ROJO])
        c.setFont(FONT_TB, 7)
        cat = str(ns.get("categoria","")).upper()
        c.drawString(x_col, y_img - 4*mm, cat)
        # Titulo
        c.setFillColorRGB(0,0,0)
        c.setFont(FONT_H, 11)
        tit = truncar(ns["titulo"], 60)
        pals2 = tit.split()
        lin2 = ""
        lins2 = []
        for p2 in pals2:
            if len(lin2)+len(p2)+1 <= 30:
                lin2 = (lin2+" "+p2).strip()
            else:
                lins2.append(lin2)
                lin2 = p2
        if lin2: lins2.append(lin2)
        for j, ln2 in enumerate(lins2[:3]):
            c.drawString(x_col, y_img - 8*mm - j*5*mm, ln2)
    # --- BANNER PUBLICITARIO INFERIOR ---
    banner_h = 18*mm
    y_banner = MARGIN + 8*mm
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.rect(MARGIN, y_banner, w - 2*MARGIN, banner_h, fill=1, stroke=0)
    c.setFillColorRGB(*[x/255 for x in COLOR_GRIS])
    c.setFont(FONT_T, 9)
    c.drawCentredString(w/2, y_banner + banner_h/2 - 2, "ESPACIO PUBLICITARIO")
    # --- PIE DE PAGINA ---
    c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
    c.rect(0, 0, w, MARGIN + 2*mm, fill=1, stroke=0)
    c.setFillColorRGB(1,1,1)
    c.setFont(FONT_T, 8)
    c.drawString(MARGIN, 4*mm, f"{SITE_URL} | Edicion Impresa | {HOY_LABEL.title()}")
    c.drawRightString(w - MARGIN, 4*mm, "Pagina 1")

# ============================================================
# GENERADOR DE PAGINA INTERIOR
# ============================================================
def generar_pagina_interior(c, nota, num_pagina):
    """Genera una pagina interior con cabecera, cuerpo a 2 columnas, imagen y pie"""
    w, h = PAGE_W, PAGE_H
    # --- CABECERA ---
    c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
    c.rect(0, h - 20*mm, w, 20*mm, fill=1, stroke=0)
    # Logo pequeno
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(LOGO_PATH, MARGIN, h - 18*mm, width=35*mm, height=14*mm,
                       preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    else:
        c.setFillColorRGB(1,1,1)
        c.setFont(FONT_H, 14)
        c.drawString(MARGIN, h - 13*mm, NOMBRE_DIARIO.upper())
    c.setFillColorRGB(1,1,1)
    c.setFont(FONT_T, 8)
    c.drawRightString(w - MARGIN, h - 10*mm, HOY_LABEL.title())
    c.drawRightString(w - MARGIN, h - 16*mm, LEMA.upper())
    # --- LINEA ROJA BAJO CABECERA ---
    c.setStrokeColorRGB(*[x/255 for x in COLOR_ROJO])
    c.setLineWidth(2)
    c.line(0, h - 20*mm, w, h - 20*mm)
    # --- CATEGORIA / SECCION ---
    cat = str(nota.get("categoria","General")).upper()
    c.setFillColorRGB(*[x/255 for x in COLOR_ROJO])
    c.setFont(FONT_TB, 9)
    c.drawString(MARGIN, h - 25*mm, f"SECCION: {cat}")
    # --- TITULO PRINCIPAL ---
    c.setFillColorRGB(0,0,0)
    c.setFont(FONT_H, 20)
    titulo = limpiar_html(nota.get("titulo","Sin titulo"))
    palabras = titulo.split()
    linea = ""
    lineas_t = []
    for p in palabras:
        if len(linea)+len(p)+1 <= 58:
            linea = (linea+" "+p).strip()
        else:
            lineas_t.append(linea)
            linea = p
    if linea: lineas_t.append(linea)
    y_tit = h - 30*mm
    for i, ln in enumerate(lineas_t[:3]):
        c.drawString(MARGIN, y_tit - i*10*mm, ln)
    y_pos = y_tit - len(lineas_t[:3])*10*mm - 3*mm
    # --- SUBTITULO / COPETE ---
    copete = limpiar_html(nota.get("copete",""))
    if copete:
        c.setFont(FONT_H2, 13)
        c.setFillColorRGB(*[x/255 for x in COLOR_GRIS])
        pals = copete.split()
        lin = ""
        lins = []
        for p in pals:
            if len(lin)+len(p)+1 <= 72:
                lin = (lin+" "+p).strip()
            else:
                lins.append(lin)
                lin = p
        if lin: lins.append(lin)
        for i, ln in enumerate(lins[:2]):
            c.drawString(MARGIN, y_pos - i*7*mm, ln)
        y_pos -= len(lins[:2])*7*mm + 4*mm
    # Linea separadora
    c.setStrokeColorRGB(*[x/255 for x in COLOR_AZUL])
    c.setLineWidth(1)
    c.line(MARGIN, y_pos - 1*mm, w-MARGIN, y_pos - 1*mm)
    y_pos -= 4*mm
    # --- IMAGEN DE LA NOTA ---
    img_h = 55*mm
    img_w = w - 2*MARGIN
    y_img = y_pos - img_h
    if nota.get("imagen_url"):
        img = descargar_imagen(nota["imagen_url"], int(img_w*3.78), int(img_h*3.78))
        if img:
            ir = pil_to_imagereader(img)
            c.drawImage(ir, MARGIN, y_img, width=img_w, height=img_h,
                       preserveAspectRatio=True, mask="auto")
        else:
            c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
            c.rect(MARGIN, y_img, img_w, img_h, fill=1, stroke=0)
            c.setFillColorRGB(1,1,1)
            c.setFont(FONT_T, 9)
            c.drawCentredString(w/2, y_img + img_h/2, "IMAGEN NO DISPONIBLE")
    else:
        img_h = 0
    # Credito de imagen
    if nota.get("imagen_credito") and img_h > 0:
        c.setFillColorRGB(*[x/255 for x in COLOR_GRIS])
        c.setFont(FONT_T, 7)
        c.drawRightString(w-MARGIN, y_img - 2.5*mm, f"Imagen: {nota[chr(105)+chr(109)+chr(97)+chr(103)+chr(101)+chr(110)+chr(95)+chr(99)+chr(114)+chr(101)+chr(100)+chr(105)+chr(116)+chr(111)]}")
    y_pos = y_img - (5*mm if img_h > 0 else 0)
    # --- CUERPO DEL TEXTO EN 2 COLUMNAS ---
    content_h = y_pos - MARGIN - 18*mm  # espacio disponible
    col_w = (w - 2*MARGIN - 6*mm) / 2
    col1_x = MARGIN
    col2_x = MARGIN + col_w + 6*mm
    # Texto del cuerpo
    cuerpo = limpiar_html(nota.get("cuerpo",""))
    if not cuerpo:
        cuerpo = limpiar_html(nota.get("copete",""))
    if not cuerpo:
        cuerpo = "Contenido no disponible."
    # Dividir en parrafos
    parrafos = [p.strip() for p in cuerpo.split("\n") if p.strip()]
    if not parrafos:
        parrafos = [cuerpo]
    # Renderizar texto columna a columna
    c.setFont(FONT_T, 9.5)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    line_h = 4.8*mm
    max_lines_col = int(content_h / line_h)
    # Generar todas las lineas
    all_lines = []
    for par in parrafos:
        words = par.split()
        cur = ""
        for w2 in words:
            if len(cur)+len(w2)+1 <= 45:
                cur = (cur+" "+w2).strip()
            else:
                all_lines.append(cur)
                cur = w2
        if cur:
            all_lines.append(cur)
        all_lines.append("")  # linea vacia entre parrafos
    # Col 1
    lines1 = all_lines[:max_lines_col]
    lines2 = all_lines[max_lines_col:max_lines_col*2]
    for i, ln in enumerate(lines1):
        c.drawString(col1_x, y_pos - (i+1)*line_h, ln)
    for i, ln in enumerate(lines2):
        c.drawString(col2_x, y_pos - (i+1)*line_h, ln)
    # Linea divisoria entre columnas
    c.setStrokeColorRGB(*[x/255 for x in COLOR_GRIS])
    c.setLineWidth(0.5)
    c.line(col1_x+col_w+3*mm, y_pos, col1_x+col_w+3*mm, y_pos - content_h)
    # --- ESPACIO PUBLICITARIO (si hay espacio) ---
    y_pub = MARGIN + 10*mm
    if y_pos - content_h > y_pub + 20*mm:
        c.setFillColorRGB(0.93, 0.93, 0.93)
        c.rect(MARGIN, y_pub, w - 2*MARGIN, 14*mm, fill=1, stroke=0)
        c.setFillColorRGB(*[x/255 for x in COLOR_GRIS])
        c.setFont(FONT_T, 8)
        c.drawCentredString(w/2, y_pub + 5*mm, "ESPACIO PUBLICITARIO")
    # --- PIE DE PAGINA ---
    c.setFillColorRGB(*[x/255 for x in COLOR_AZUL])
    c.rect(0, 0, w, 10*mm, fill=1, stroke=0)
    c.setFillColorRGB(1,1,1)
    c.setFont(FONT_T, 8)
    c.drawString(MARGIN, 3.5*mm, f"{SITE_URL} | @diarioinfo | Edicion Impresa {HOY_LABEL.title()}")
    c.drawRightString(w-MARGIN, 3.5*mm, f"Pagina {num_pagina}")

# ============================================================
# FUNCION PRINCIPAL - Genera el PDF
# ============================================================
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
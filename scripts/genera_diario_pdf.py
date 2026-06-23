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
            ).sort("publishedAt", -1).limit(limite)
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
    print("  ERROR: No se pudo conectar a ningÃºn cluster MongoDB")
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
    from reportlab.lib.units import mm
    W = A4[0]
    H = A4[1]
    MARGEN = 15 * mm
    ANCHO = W - 2 * MARGEN
    AZUL      = (0.0, 0.2, 0.4)
    NARANJA   = (0.957, 0.486, 0.125)
    GRIS      = (0.4, 0.4, 0.4)
    GRIS_OSC  = (0.333, 0.333, 0.333)
    NEGRO     = (0, 0, 0)
    BLANCO    = (1, 1, 1)
    GRIS_SEP  = (0.8, 0.8, 0.8)
    c.setFillColorRGB(*BLANCO)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    y = H - MARGEN
    # 1. CABECERA SUPERIOR
    dol = cotizaciones.get("dolar_oficial", "Oficial: --")
    blu = cotizaciones.get("dolar_blue", "Blue: --")
    rp  = cotizaciones.get("riesgo_pais", "")
    clim_txt = clima if clima else ""
    info_bar = HOY_LABEL + "   |   Santiago del Estero  " + clim_txt
    if rp:
        info_bar = info_bar + "   |   " + dol + "   " + blu + "   " + rp
    else:
        info_bar = info_bar + "   |   " + dol + "   " + blu
    c.setFont(FONT_N, 7)
    c.setFillColorRGB(*GRIS_OSC)
    c.drawCentredString(W/2, y - 3*mm, info_bar)
    y -= 7 * mm
    c.setStrokeColorRGB(*GRIS_SEP)
    c.setLineWidth(0.5)
    c.line(MARGEN, y, W - MARGEN, y)
    y -= 4 * mm
    # 2. LOGO INSTITUCIONAL
    logo_base_y = y - 17*mm
    # Icono circular azul con semicirculo naranja
    icono_cx = W/2 - 52*mm
    icono_cy = logo_base_y + 8*mm
    icono_r  = 7*mm
    c.setFillColorRGB(*AZUL)
    c.circle(icono_cx, icono_cy, icono_r, fill=1, stroke=0)
    c.setFillColorRGB(*NARANJA)
    c.wedge(icono_cx - icono_r, icono_cy - icono_r,
            icono_cx + icono_r, icono_cy + icono_r,
            0, 180, fill=1, stroke=0)
    c.setFillColorRGB(*BLANCO)
    c.setFont(FONT_TB, 9)
    c.drawCentredString(icono_cx, icono_cy - 3, "Di")
    # Texto logo
    txt_x = icono_cx + icono_r + 3*mm
    c.setFont(FONT_TB, 24)
    c.setFillColorRGB(*AZUL)
    diario_w = c.stringWidth("diario", FONT_TB, 24)
    c.drawString(txt_x, logo_base_y + 5*mm, "diario")
    c.setFont(FONT_TB, 26)
    c.setFillColorRGB(*NARANJA)
    info_w = c.stringWidth("info", FONT_TB, 26)
    c.drawString(txt_x + diario_w, logo_base_y + 4*mm, "info")
    c.setFont(FONT_N, 13)
    c.setFillColorRGB(*GRIS)
    c.drawString(txt_x + diario_w + info_w, logo_base_y + 7*mm, ".com")
    c.setFont(FONT_N, 9)
    c.setFillColorRGB(*GRIS)
    c.drawCentredString(W/2, logo_base_y - 2*mm, "Santiago del Estero")
    y = logo_base_y - 6*mm
    c.setStrokeColorRGB(*AZUL)
    c.setLineWidth(2)
    c.line(MARGEN, y, W - MARGEN, y)
    c.setLineWidth(0.5)
    y -= 5*mm
    # 3. NOTA PRINCIPAL (60% del espacio)
    PIE_H = 12*mm
    zona_total = y - MARGEN - PIE_H
    zona_principal = zona_total * 0.60
    zona_secundarias = zona_total * 0.40
    y_inicio_principal = y
    if notas:
        nota_p = notas[0]
        img_h = zona_principal * 0.55
        img_y = y - img_h
        img_url = nota_p.get("imagen_url")
        img_path = descargar_imagen(img_url) if img_url else None
        if img_path and os.path.exists(img_path):
            try:
                c.drawImage(img_path, MARGEN, img_y, ANCHO, img_h, preserveAspectRatio=True, anchor="c")
            except Exception:
                c.setFillColorRGB(*AZUL)
                c.rect(MARGEN, img_y, ANCHO, img_h, fill=1, stroke=0)
        else:
            c.setFillColorRGB(*AZUL)
            c.rect(MARGEN, img_y, ANCHO, img_h, fill=1, stroke=0)
            c.setFillColorRGB(*BLANCO)
            c.setFont(FONT_N, 9)
            c.drawCentredString(W/2, img_y + img_h/2, "[ imagen no disponible ]")
        y = img_y - 4*mm
        cat = nota_p.get("categoria", "NOTICIAS").upper()
        c.setFillColorRGB(*NARANJA)
        c.setFont(FONT_TB, 8)
        c.drawString(MARGEN, y, cat)
        y -= 5*mm
        titulo = nota_p.get("titulo", "")[:180]
        palabras = titulo.split()
        lineas_t = []
        linea_act = ""
        for p in palabras:
            prueba = (linea_act + " " + p).strip()
            if c.stringWidth(prueba, FONT_TB, 20) < ANCHO:
                linea_act = prueba
            else:
                if linea_act:
                    lineas_t.append(linea_act)
                linea_act = p
        if linea_act:
            lineas_t.append(linea_act)
        lineas_t = lineas_t[:3]
        c.setFillColorRGB(*NEGRO)
        c.setFont(FONT_TB, 20)
        for lt in lineas_t:
            c.drawString(MARGEN, y, lt)
            y -= 8*mm
        copete = nota_p.get("copete", "")[:200]
        palabras_c = copete.split()
        lineas_c = []
        lc_act = ""
        for p in palabras_c:
            prueba = (lc_act + " " + p).strip()
            if c.stringWidth(prueba, FONT_N, 10) < ANCHO:
                lc_act = prueba
            else:
                if lc_act:
                    lineas_c.append(lc_act)
                lc_act = p
        if lc_act:
            lineas_c.append(lc_act)
        lineas_c = lineas_c[:2]
        c.setFillColorRGB(*GRIS_OSC)
        c.setFont(FONT_N, 10)
        for lc in lineas_c:
            c.drawString(MARGEN, y, lc)
            y -= 5*mm
    y -= 3*mm
    c.setStrokeColorRGB(*GRIS_SEP)
    c.setLineWidth(0.5)
    c.line(MARGEN, y, W - MARGEN, y)
    y -= 4*mm
    # 4. TRES NOTAS SECUNDARIAS
    col_w = ANCHO / 3
    n_disponibles = notas[1:4] if len(notas) >= 4 else notas[1:]
    notas_sec = list(n_disponibles) + [{}] * (3 - len(n_disponibles))
    y_sec_top = y
    y_sec_bot = MARGEN + PIE_H + 3*mm
    zona_sec  = y_sec_top - y_sec_bot
    img_sec_h = zona_sec * 0.42
    etiquetas = ["POLICIALES", "DEPORTES", "POLITICA"]
    for i, nota_s in enumerate(notas_sec):
        col_x = MARGEN + i * col_w
        cy    = y_sec_top
        if i > 0:
            c.setStrokeColorRGB(*GRIS_SEP)
            c.setLineWidth(0.5)
            c.line(col_x, y_sec_top + 1*mm, col_x, y_sec_bot)
        if not nota_s:
            continue
        img_url_s = nota_s.get("imagen_url")
        img_path_s = descargar_imagen(img_url_s) if img_url_s else None
        if img_path_s and os.path.exists(img_path_s):
            try:
                c.drawImage(img_path_s, col_x + 2*mm, cy - img_sec_h,
                            col_w - 4*mm, img_sec_h,
                            preserveAspectRatio=True, anchor="c")
            except Exception:
                c.setFillColorRGB(0.85, 0.85, 0.85)
                c.rect(col_x + 2*mm, cy - img_sec_h, col_w - 4*mm, img_sec_h, fill=1, stroke=0)
        else:
            c.setFillColorRGB(0.85, 0.85, 0.85)
            c.rect(col_x + 2*mm, cy - img_sec_h, col_w - 4*mm, img_sec_h, fill=1, stroke=0)
        cy -= img_sec_h + 3*mm
        etiq = etiquetas[i] if i < len(etiquetas) else nota_s.get("categoria","NOTICIAS").upper()
        c.setFont(FONT_TB, 8)
        c.setFillColorRGB(*AZUL)
        c.drawString(col_x + 2*mm, cy, etiq)
        cy -= 4.5*mm
        tit_s = nota_s.get("titulo", "")[:100]
        palabras_s = tit_s.split()
        lineas_s = []
        ls_act = ""
        col_inner = col_w - 6*mm
        for p in palabras_s:
            prueba = (ls_act + " " + p).strip()
            if c.stringWidth(prueba, FONT_TB, 11) < col_inner:
                ls_act = prueba
            else:
                if ls_act:
                    lineas_s.append(ls_act)
                ls_act = p
        if ls_act:
            lineas_s.append(ls_act)
        lineas_s = lineas_s[:3]
        c.setFont(FONT_TB, 11)
        c.setFillColorRGB(*NEGRO)
        for ls in lineas_s:
            c.drawString(col_x + 2*mm, cy, ls)
            cy -= 5*mm
        cop_s = nota_s.get("copete", "")[:130]
        palabras_cs = cop_s.split()
        lineas_cs = []
        lcs_act = ""
        for p in palabras_cs:
            prueba = (lcs_act + " " + p).strip()
            if c.stringWidth(prueba, FONT_N, 8.5) < col_inner:
                lcs_act = prueba
            else:
                if lcs_act:
                    lineas_cs.append(lcs_act)
                lcs_act = p
        if lcs_act:
            lineas_cs.append(lcs_act)
        lineas_cs = lineas_cs[:3]
        c.setFont(FONT_N, 8.5)
        c.setFillColorRGB(*GRIS)
        for lcs in lineas_cs:
            c.drawString(col_x + 2*mm, cy, lcs)
            cy -= 4*mm
    # 5. PIE DE PAGINA
    pie_y = MARGEN + 1.5*mm
    c.setStrokeColorRGB(*GRIS_SEP)
    c.setLineWidth(0.5)
    c.line(MARGEN, pie_y + 5*mm, W - MARGEN, pie_y + 5*mm)
    c.setFont(FONT_N, 8)
    c.setFillColorRGB(*GRIS_OSC)
    c.drawString(MARGEN, pie_y, "www.diarioinfo.com.ar")
    c.drawRightString(W - MARGEN, pie_y, "Edicion Impresa  •  Santiago del Estero")
    c.showPage()
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
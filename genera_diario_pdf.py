#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DiarioInfo Edicion Impresa v1.9 - Diseno editorial mejorado
import os,sys,io,re,math,urllib.request,json
from datetime import datetime,timezone,timedelta
from bson.objectid import ObjectId
from pymongo import MongoClient
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

W,H=A4; M=12*mm; AW=W-2*M

# Paleta de colores
AZUL=(0.00,0.20,0.63); NARANJA=(0.96,0.49,0.00)
GRIS_OSC=(0.20,0.20,0.20); GRIS_MED=(0.50,0.50,0.50)
GRIS_CLAR=(0.90,0.90,0.90); GRIS_BOX=(0.95,0.95,0.96)
NEGRO=(0.05,0.05,0.05); BLANCO=(1.00,1.00,1.00)
ROJO_POL=(0.72,0.05,0.05); VERDE_ECO=(0.05,0.45,0.20)
AZUL_DEP=(0.00,0.35,0.70); AZUL_OSCURO=(0.00,0.10,0.35)
CREMA=(0.98,0.97,0.93)

CAT_STYLE={
    "policiales": (ROJO_POL,  (0.98,0.93,0.93)),
    "policial":   (ROJO_POL,  (0.98,0.93,0.93)),
    "deportes":   (AZUL_DEP,  (0.90,0.94,0.99)),
    "deporte":    (AZUL_DEP,  (0.90,0.94,0.99)),
    "economia":   (VERDE_ECO, (0.90,0.97,0.92)),
    "politica":   (AZUL,      (0.90,0.93,0.99)),
    "sociedad":   (GRIS_OSC,  (0.93,0.93,0.95)),
    "cultura":    ((0.50,0.15,0.60),(0.95,0.90,0.98)),
}
def cat_style(cn):
    return CAT_STYLE.get((cn or '').lower().strip(),(AZUL,GRIS_BOX))

FONT_DIR=os.path.expanduser('~/.fonts_diario')
MONGO_URI="mongodb+srv://diarioinfoio_db_user:lYcxG4pf5oCOgYnq@cluster0.c621o4c.mongodb.net/diarioinfo-db?retryWrites=true&w=majority"
BASE_IMG_URL="https://api.diarioinfo.com"
db_global=None
fn="Lato-Regular"; fb="Lato-Bold"; fi="Lato-Italic"; ftb="Lato-Bold"

def get_db():
    global db_global
    if db_global is None:
        client=MongoClient(MONGO_URI); db_global=client["diarioinfo-db"]
    return db_global

def cargar_fuentes():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    ok=[]
    for name,fname in [("Lato-Regular","Lato-Regular.ttf"),("Lato-Bold","Lato-Bold.ttf"),
                        ("Lato-Italic","Lato-Italic.ttf"),("Lato-BoldItalic","Lato-BoldItalic.ttf")]:
        p=os.path.join(FONT_DIR,fname)
        if os.path.exists(p):
            try: pdfmetrics.registerFont(TTFont(name,p)); ok.append(name)
            except: pass
    return ok

def limpiar_html(html):
    if not html: return ''
    t=re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    t=re.sub(r'</p>', '\n', t, flags=re.I)
    t=re.sub(r'<[^>]+>', '', t)
    t=t.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"')
    t=re.sub(r'\n{3,}','\n\n',t)
    return t.strip()

def obtener_imagen_url(image_id):
    if not image_id: return ''
    try:
        db=get_db()
        f=db["files"].find_one({"_id":ObjectId(str(image_id))})
        if f:
            url=f.get("fileUrl") or f.get("url") or ""
            if url and url.startswith('/'): url=BASE_IMG_URL+url
            url=url.replace(" ","%20")
            return url
    except Exception as e: print(f'  Error imagen {image_id}: {e}')
    return ''

def descargar_imagen(url):
    if not url: return None
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 DiarioInfo-PDF/1.9"})
        data=urllib.request.urlopen(req,timeout=12).read()
        img=ImageReader(io.BytesIO(data))
        iw,ih=img.getSize()
        return img,iw,ih
    except Exception as e:
        print(f'  Error descarga img: {e}')
    return None
def draw_placeholder(c,x,y,w,h,msg='Imagen no disponible'):
    c.setFillColorRGB(*GRIS_BOX); c.rect(x,y,w,h,fill=1,stroke=0)
    c.setFillColorRGB(*GRIS_MED); c.setFont(fn,7)
    c.drawCentredString(x+w/2,y+h/2-3,msg)

def dibujar_imagen_adaptativa(c,img_data,x,y,w,h):
    if not img_data:
        draw_placeholder(c,x,y,w,h); return False
    img,iw,ih=img_data
    ratio=iw/ih; box_ratio=w/h
    if ratio>box_ratio: dw,dh=w,w/ratio; dx,dy=x,y+(h-dh)/2
    else: dh,dw=h,h*ratio; dx,dy=x+(w-dw)/2,y
    c.drawImage(img,dx,dy,dw,dh,preserveAspectRatio=True,mask='auto')
    return True

def wrap_text(c,texto,fuente,pts,ancho):
    c.setFont(fuente,pts)
    words=texto.split()
    lines=[]; line=''
    for w in words:
        test=line+' '+w if line else w
        if c.stringWidth(test,fuente,pts)<=ancho: line=test
        else:
            if line: lines.append(line)
            line=w
    if line: lines.append(line)
    return lines

def draw_wrapped(c,texto,x,y,ancho,fuente,pts,color=NEGRO,lh=None,max_lines=99,align='left'):
    if not texto: return y
    if lh is None: lh=pts*1.4
    c.setFont(fuente,pts); c.setFillColorRGB(*color)
    lines=wrap_text(c,texto,fuente,pts,ancho)
    for i,line in enumerate(lines[:max_lines]):
        if align=='center': c.drawCentredString(x+ancho/2,y,line)
        elif align=='right': c.drawRightString(x+ancho,y,line)
        else: c.drawString(x,y,line)
        y-=lh
    return y

def draw_badge(c,texto,x,y,color_bg,color_txt=BLANCO,pts=7,pad_h=5,pad_v=3):
    c.setFont(fb,pts)
    tw=c.stringWidth(texto,fb,pts)
    bw=tw+pad_h*2; bh=pts+pad_v*2
    c.setFillColorRGB(*color_bg); c.roundRect(x,y-pad_v,bw,bh,2,fill=1,stroke=0)
    c.setFillColorRGB(*color_txt); c.drawString(x+pad_h,y,texto)
    return bw+4

def draw_linea(c,x,y,w,color,grosor=0.5):
    c.setStrokeColorRGB(*color); c.setLineWidth(grosor)
    c.line(x,y,x+w,y)

def draw_linea_v(c,x,y_top,h,color,grosor=0.5):
    c.setStrokeColorRGB(*color); c.setLineWidth(grosor)
    c.line(x,y_top,x,y_top-h)

def draw_rect_fill(c,x,y,w,h,color):
    c.setFillColorRGB(*color); c.setStrokeColorRGB(*color)
    c.rect(x,y,w,h,fill=1,stroke=0)

def acento_lateral(c,x,y_top,h,color,grosor=3):
    c.setFillColorRGB(*color); c.rect(x,y_top-h,grosor,h,fill=1,stroke=0)

def draw_logo(c,cx,cy,r=17):
    import math
    c.setFillColorRGB(*AZUL)
    p=c.beginPath(); p.circle(cx,cy,r); c.drawPath(p,fill=1,stroke=0)
    c.setFillColorRGB(*BLANCO)
    p2=c.beginPath(); p2.circle(cx,cy,r*0.68); c.drawPath(p2,fill=1,stroke=0)
    c.setFillColorRGB(*NARANJA)
    p3=c.beginPath(); p3.circle(cx,cy,r*0.38); c.drawPath(p3,fill=1,stroke=0)
# -- CABECERA PRINCIPAL -----------------------------------------------------
def cabecera(c,cotiz_of,cotiz_bl,clima,fecha_txt,num_pagina=None):
    y=H-M
    bar_h=7*mm
    draw_rect_fill(c,0,y-bar_h,W,bar_h,AZUL_OSCURO)
    c.setFillColorRGB(*BLANCO); c.setFont(fn,6.5)
    items=[]
    if cotiz_of: items.append(f'USD Oficial: ${cotiz_of}')
    if cotiz_bl:  items.append(f'USD Blue: ${cotiz_bl}')
    if clima:     items.append(f'  {clima}')
    txt_bar='    '.join(items)
    c.drawString(M,y-bar_h+2.2*mm,txt_bar)
    if num_pagina:
        c.setFont(fb,6.5)
        c.drawRightString(W-M,y-bar_h+2.2*mm,f'Pag. {num_pagina}')
    y-=bar_h+3*mm
    r=9; logo_x=W/2-50; logo_cy=y-r-1*mm
    draw_logo(c,logo_x,logo_cy,r)
    tx=logo_x+r+3
    c.setFont(fb,17); c.setFillColorRGB(*AZUL); c.drawString(tx,logo_cy-5.5,'diario')
    tw_d=c.stringWidth('diario',fb,17)
    c.setFont(fb,19); c.setFillColorRGB(*NARANJA); c.drawString(tx+tw_d,logo_cy-6.5,'info')
    tw_i=c.stringWidth('info',fb,19)
    c.setFont(fn,8); c.setFillColorRGB(*GRIS_MED)
    c.drawString(tx+tw_d+tw_i+1,logo_cy-3.5,'.com')
    y=logo_cy-3*mm
    c.setFont(fn,6.5); c.setFillColorRGB(*GRIS_MED)
    c.drawCentredString(W/2,y,'Santiago del Estero')
    y-=2*mm
    draw_linea(c,M,y,AW,AZUL,2.0); y-=1.5*mm
    draw_linea(c,M,y,AW,NARANJA,0.5); y-=2*mm
    c.setFont(fb,8); c.setFillColorRGB(*AZUL)
    c.drawCentredString(W/2,y,fecha_txt.upper())
    y-=3*mm
    draw_linea(c,M,y,AW,GRIS_CLAR,0.5); y-=2*mm
    return y

# -- PIE DE PAGINA -----------------------------------------------------------
def pie_pagina(c,num_pagina=None,y=None):
    if y is None: y=M+10
    draw_linea(c,M,y+6,AW,GRIS_CLAR,0.5)
    c.setFont(fn,7); c.setFillColorRGB(*GRIS_MED)
    c.drawString(M,y,'www.diarioinfo.com.ar')
    c.drawCentredString(W/2,y,'Edicion Impresa  |  Santiago del Estero')
    if num_pagina:
        c.setFont(fb,8); c.setFillColorRGB(*AZUL)
        c.drawRightString(W-M,y,str(num_pagina))
# -- TAPA -------------------------------------------------------------------
def generar_tapa(c,notas,cotiz_of,cotiz_bl,clima,fecha_txt):
    n0=notas[0] if notas else {}
    notas_sec=notas[1:4]
    y=cabecera(c,cotiz_of,cotiz_bl,clima,fecha_txt,num_pagina=None)
    area_total=y-M-14
    titulo0=n0.get('title','')
    desc0=limpiar_html(n0.get('content','') or n0.get('description',''))[:300]
    cat0=n0.get('cat_nombre','')
    col0,bg0=cat_style(cat0)
    img_url0=n0.get('img_url','') or obtener_imagen_url(n0.get('imageId',''))
    img_data0=descargar_imagen(img_url0) if img_url0 else None
    n_sec=len(notas_sec)
    zona_principal=area_total*0.62 if n_sec>0 else area_total
    zona_sec=area_total-zona_principal-4*mm if n_sec>0 else 0
    if img_data0:
        _,iw,ih=img_data0
        es_apaisada=(iw/ih)>=1.2
        if es_apaisada:
            img_h=min(zona_principal*0.58,90*mm)
            img_y=y-img_h
            dibujar_imagen_adaptativa(c,img_data0,M,img_y,AW,img_h)
            y=img_y-5*mm
            if cat0:
                bw=draw_badge(c,cat0.upper(),M,y,col0,BLANCO,8,6,3); y-=16
            y=draw_wrapped(c,titulo0,M,y,AW,ftb,24,NEGRO,lh=30,max_lines=4)
            y-=4
            if desc0: y=draw_wrapped(c,desc0,M,y,AW,fi,10,GRIS_OSC,lh=14,max_lines=3)
            y-=6*mm
        else:
            col_img=AW*0.38; col_txt=AW*0.58; gap=AW*0.04
            img_h=min(zona_principal*0.85,100*mm)
            img_y=y-img_h
            dibujar_imagen_adaptativa(c,img_data0,M,img_y,col_img,img_h)
            tx_x=M+col_img+gap; tx_w=col_txt; y_t=y
            if cat0:
                bw=draw_badge(c,cat0.upper(),tx_x,y_t,col0,BLANCO,8,6,3); y_t-=16
            y_t=draw_wrapped(c,titulo0,tx_x,y_t,tx_w,ftb,23,NEGRO,lh=29,max_lines=5)
            y_t-=4
            if desc0: y_t=draw_wrapped(c,desc0,tx_x,y_t,tx_w,fi,10,GRIS_OSC,lh=14,max_lines=5)
            y=min(img_y,y_t)-6*mm
    else:
        draw_rect_fill(c,M,y-zona_principal*0.75,AW,zona_principal*0.75,CREMA)
        acento_lateral(c,M,y,zona_principal*0.75,col0,4)
        if cat0:
            bw=draw_badge(c,cat0.upper(),M+8,y-10,col0,BLANCO,8,6,3); y-=20
        y=draw_wrapped(c,titulo0,M+8,y,AW-16,ftb,25,NEGRO,lh=31,max_lines=4)
        y-=6
        if desc0: y=draw_wrapped(c,desc0,M+8,y,AW-16,fi,10.5,GRIS_OSC,lh=14,max_lines=3)
        y-=8*mm
    draw_linea(c,M,y,AW,GRIS_CLAR,0.6); y-=4*mm
    if n_sec>0:
        sec_h=y-M-14; col_w=AW/max(n_sec,1)-3
        c.setFont(fb,7); c.setFillColorRGB(*GRIS_MED)
        c.drawString(M,y,'MAS NOTICIAS')
        draw_linea(c,M,y-2,AW,GRIS_CLAR,0.4); y-=10
        for i,ns in enumerate(notas_sec):
            sx=M+i*(col_w+3); cat_s=ns.get('cat_nombre','')
            col_s,bg_s=cat_style(cat_s)
            draw_rect_fill(c,sx,M+12,col_w,sec_h,bg_s)
            acento_lateral(c,sx,y,sec_h,col_s,3)
            sy=y-8
            if cat_s:
                draw_badge(c,cat_s.upper(),sx+6,sy,col_s,BLANCO,6.5,4,2.5); sy-=14
            img_s_url=ns.get('img_url','') or obtener_imagen_url(ns.get('imageId',''))
            img_s=descargar_imagen(img_s_url) if img_s_url else None
            if img_s:
                img_sh=min(35*mm,sec_h*0.40)
                img_sy=sy-img_sh
                dibujar_imagen_adaptativa(c,img_s,sx+4,img_sy,col_w-8,img_sh)
                sy=img_sy-4
            tit_s=ns.get('title','')
            sy=draw_wrapped(c,tit_s,sx+6,sy,col_w-10,ftb,10,NEGRO,lh=13,max_lines=4)
            sy-=3
            desc_s=limpiar_html(ns.get('content','') or ns.get('description',''))[:150]
            if desc_s:
                draw_wrapped(c,desc_s,sx+6,sy,col_w-10,fi,8.5,GRIS_OSC,lh=11,max_lines=3)
            if i<n_sec-1:
                draw_linea_v(c,sx+col_w+1.5,y,sec_h+4,GRIS_CLAR,0.5)
    pie_pagina(c,num_pagina=1)
    c.showPage()
# -- PAGINA INTERNA (una nota por pagina) ------------------------------------
def generar_pagina_nota(c,nota,num_pagina,fecha_txt,clima,cotiz_of,cotiz_bl):
    titulo=nota.get('title','')
    contenido=limpiar_html(nota.get('content','') or nota.get('description',''))
    cat=nota.get('cat_nombre','')
    autor=nota.get('author','') or nota.get('autorNombre','')
    col,bg=cat_style(cat)
    img_url=nota.get('img_url','') or obtener_imagen_url(nota.get('imageId',''))
    img_data=descargar_imagen(img_url) if img_url else None
    y=cabecera(c,cotiz_of,cotiz_bl,clima,fecha_txt,num_pagina=num_pagina)
    # Banda de categoria
    banda_h=8*mm
    draw_rect_fill(c,M,y-banda_h,AW,banda_h,col)
    c.setFont(fb,8); c.setFillColorRGB(*BLANCO)
    c.drawString(M+4,y-banda_h+2.8*mm,(cat.upper() if cat else 'GENERAL'))
    c.setFont(fn,7); c.setFillColorRGB(*BLANCO)
    c.drawRightString(W-M-4,y-banda_h+2.8*mm,f'Pagina {num_pagina}')
    y-=banda_h+4*mm
    # Imagen principal
    if img_data:
        _,iw,ih=img_data
        es_apaisada=(iw/ih)>=1.2
        if es_apaisada:
            img_h=min(75*mm,H*0.28)
            img_y=y-img_h
            draw_rect_fill(c,M+2,img_y-2,AW,img_h,(0.85,0.85,0.85))
            dibujar_imagen_adaptativa(c,img_data,M,img_y,AW,img_h)
            y=img_y-5*mm
            acento_lateral(c,M,y,14*mm,col,4)
            y=draw_wrapped(c,titulo,M+8,y,AW-8,ftb,24,NEGRO,lh=30,max_lines=4)
            y-=5
            if autor:
                c.setFont(fi,8.5); c.setFillColorRGB(*GRIS_MED)
                c.drawString(M+8,y,f'Por {autor}'); y-=14
            draw_linea(c,M,y,AW,col,1.2); y-=7
        else:
            col_img=AW*0.40; col_txt=AW*0.56; gap=AW*0.04
            img_h=min(85*mm,H*0.32)
            img_y=y-img_h
            draw_rect_fill(c,W-M-col_img+2,img_y-2,col_img,img_h,(0.85,0.85,0.85))
            dibujar_imagen_adaptativa(c,img_data,W-M-col_img,img_y,col_img,img_h)
            acento_lateral(c,M,y,img_h+4*mm,col,4)
            y_t=y
            y_t=draw_wrapped(c,titulo,M+8,y_t,col_txt-4,ftb,22,NEGRO,lh=28,max_lines=4)
            y_t-=5
            if autor:
                c.setFont(fi,8); c.setFillColorRGB(*GRIS_MED)
                c.drawString(M+8,y_t,f'Por {autor}'); y_t-=12
            draw_linea(c,M+8,y_t,col_txt-8,col,0.8); y_t-=6
            parrafos=contenido.split('\n')
            for p in parrafos:
                p=p.strip()
                if not p: y_t-=5; continue
                if y_t<img_y+10: break
                y_t=draw_wrapped(c,p,M+8,y_t,col_txt-4,fn,9.5,GRIS_OSC,lh=13.5,max_lines=50)
                y_t-=4
            y=min(img_y,y_t)-6*mm
            pie_pagina(c,num_pagina=num_pagina); c.showPage(); return
    else:
        draw_rect_fill(c,M,y-4*mm,AW,4*mm,bg)
        acento_lateral(c,M,y,10*mm,col,5)
        y-=2*mm
        acento_lateral(c,M,y,14*mm,col,4)
        y=draw_wrapped(c,titulo,M+8,y,AW-8,ftb,24,NEGRO,lh=30,max_lines=4)
        y-=5
        if autor:
            c.setFont(fi,8.5); c.setFillColorRGB(*GRIS_MED)
            c.drawString(M+8,y,f'Por {autor}')
            c.drawRightString(W-M,y,'DiarioInfo')
            y-=14
        draw_linea(c,M,y,AW,col,1.2); y-=7
    # Cuerpo del texto en 2 columnas si es largo
    col_gap=6*mm; col_w2=(AW-col_gap)/2
    texto_plano=' '.join(p.strip() for p in contenido.split('\n') if p.strip())
    if len(texto_plano)>600:
        palabras=texto_plano.split()
        mitad=len(palabras)//2
        col1_txt=' '.join(palabras[:mitad])
        col2_txt=' '.join(palabras[mitad:])
        y_base=y
        y1=draw_wrapped(c,col1_txt,M,y_base,col_w2,fn,9.5,GRIS_OSC,lh=13.5,max_lines=99)
        draw_wrapped(c,col2_txt,M+col_w2+col_gap,y_base,col_w2,fn,9.5,GRIS_OSC,lh=13.5,max_lines=99)
        draw_linea_v(c,M+col_w2+col_gap/2,y_base+2,y_base-min(y1,M+20),GRIS_CLAR,0.5)
    else:
        draw_wrapped(c,texto_plano,M,y,AW,fn,10,GRIS_OSC,lh=14.5,max_lines=99)
    pie_pagina(c,num_pagina=num_pagina)
    c.showPage()
# -- DATOS EXTERNOS ---------------------------------------------------------
def obtener_cotizaciones():
    try:
        url='https://api.diarioinfo.com/api/cotizaciones/latest'
        req=urllib.request.Request(url,headers={'User-Agent':'DiarioInfo-PDF/1.9'})
        data=json.loads(urllib.request.urlopen(req,timeout=8).read())
        return data.get('oficial',''),data.get('blue','')
    except: return '',''

def obtener_clima():
    try:
        url='https://api.diarioinfo.com/api/clima/santiago'
        req=urllib.request.Request(url,headers={'User-Agent':'DiarioInfo-PDF/1.9'})
        data=json.loads(urllib.request.urlopen(req,timeout=8).read())
        desc=data.get('descripcion',''); temp=data.get('temperatura','')
        return f'{desc} {temp}C' if temp else desc
    except: return ''

def obtener_notas(limite=15):
    db=get_db()
    hoy=datetime.now(timezone.utc)
    tres_dias=hoy-timedelta(days=3)
    notas=db['notas'].find({'status':'published','publicationDate':{'$gte':tres_dias}},[('priority',-1),('publicationDate',-1)],limite)
    return notas

def generar_flipbook(pdf_path,html_path,fecha_str):
    html=("<!DOCTYPE html><html><head><meta charset='UTF-8'>\n"
          f"<title>DiarioInfo Edicion Impresa {fecha_str}</title>\n"
          "<style>body{margin:0;background:#222;display:flex;flex-direction:column;align-items:center;font-family:Arial,sans-serif}\n"
          "h1{color:#fff;margin:20px 0 10px;font-size:18px}\n"
          "iframe{width:90vw;height:90vh;border:none;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.5)}\n"
          "</style></head><body>\n"
          f"<h1>DiarioInfo  Edicion Impresa {fecha_str}</h1>\n"
          f"<iframe src='/revistas/diarioinfo/{fecha_str}.pdf'></iframe>\n"
          "</body></html>")
    with open(html_path,'w',encoding='utf-8') as f: f.write(html)

def main():
    global fn,fb,fi,ftb
    loaded=cargar_fuentes()
    print(f'Fuentes OK: {loaded}')
    if 'Lato-Regular' not in loaded: fn=fb=fi=ftb='Helvetica'
    if 'Lato-Bold' not in loaded: fb=ftb='Helvetica-Bold'
    if 'Lato-Italic' not in loaded: fi='Helvetica-Oblique'
    cotiz_of,cotiz_bl=obtener_cotizaciones()
    print(f'  Oficial: {cotiz_of} | Blue: {cotiz_bl}')
    clima=obtener_clima(); print(f'  {clima}')
    hoy=datetime.now(timezone.utc)
    dias_es=['Lunes','Martes','Miercoles','Jueves','Viernes','Sabado','Domingo']
    meses_es=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
    fecha_txt=f'{dias_es[hoy.weekday()]} {hoy.day} de {meses_es[hoy.month-1]} de {hoy.year}'
    fecha_str=hoy.strftime('%Y-%m-%d')
    notas=obtener_notas(15); print(f'  {len(notas)} notas')
    out_dir=os.path.expanduser('~/public_html/revistas/diarioinfo')
    flip_dir=os.path.expanduser('~/public_html/flipbook')
    os.makedirs(out_dir,exist_ok=True); os.makedirs(flip_dir,exist_ok=True)
    pdf_path=os.path.join(out_dir,f'{fecha_str}.pdf')
    html_path=os.path.join(flip_dir,f'{fecha_str}.html')
    print(f'Generando PDF: {pdf_path}')
    c=canvas.Canvas(pdf_path,pagesize=A4)
    c.setTitle(f'Diario Info - Edicion Impresa {fecha_str}')
    c.setAuthor('diarioinfo.com.ar')
    print('Tapa...')
    generar_tapa(c,notas,cotiz_of,cotiz_bl,clima,fecha_txt)
    for i,nota in enumerate(notas):
        print(f'Pagina {i+2}: {nota.get("title","")[:50]}...')
        generar_pagina_nota(c,nota,i+2,fecha_txt,clima,cotiz_of,cotiz_bl)
    c.save()
    sz=os.path.getsize(pdf_path)/1024
    print(f'PDF OK! {sz:.1f} KB')
    generar_flipbook(pdf_path,html_path,fecha_str)
    print('Flipbook...')
    print(f'=== COMPLETADO ===')
    print(f'PDF:    {pdf_path}')
    print(f'Acceso: https://diarioinfo.com/flipbook/{fecha_str}.html')

if __name__=='__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DiarioInfo  Edicion Impresa v1.8  Diseo editorial sofisticado
import os,sys,io,re,math,urllib.request,json
from datetime import datetime,timezone,timedelta
from bson.objectid import ObjectId
from pymongo import MongoClient
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
W,H=A4; M=10*mm; AW=W-2*M
AZUL=(0.00,0.20,0.63); NARANJA=(0.96,0.49,0.00)
GRIS_OSC=(0.25,0.25,0.25); GRIS_MED=(0.50,0.50,0.50)
GRIS_CLAR=(0.93,0.93,0.93); GRIS_BOX=(0.87,0.87,0.89)
NEGRO=(0.05,0.05,0.05); BLANCO=(1.00,1.00,1.00)
ROJO_POL=(0.72,0.05,0.05); VERDE_ECO=(0.05,0.45,0.20)
AZUL_DEP=(0.00,0.35,0.70)
CAT_STYLE={
  "policiales":(ROJO_POL,(0.95,0.90,0.90)),
  "policial":  (ROJO_POL,(0.95,0.90,0.90)),
  "deportes":  (AZUL_DEP,(0.88,0.92,0.97)),
  "deporte":   (AZUL_DEP,(0.88,0.92,0.97)),
  "economia":  (VERDE_ECO,(0.88,0.96,0.90)),
  "economia":  (VERDE_ECO,(0.88,0.96,0.90)),
}
def cat_style(cn):
    return CAT_STYLE.get((cn or "").lower().strip(),(AZUL,GRIS_CLAR))
FONT_DIR=os.path.expanduser("~/.fonts_diario")
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
    if not html: return ""
    t=re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    t=re.sub(r'</p>', '\n', t, flags=re.I)
    t=re.sub(r'<[^>]+>', '', t)
    t=t.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"')
    t=re.sub(r'\n{3,}','\n\n',t)
    return t.strip()

def obtener_imagen_url(image_id):
    if not image_id: return ""
    try:
        db=get_db()
        f=db["files"].find_one({"_id":ObjectId(str(image_id))})
        if f:
            url=f.get("fileUrl") or f.get("url") or ""
            if url and url.startswith("/"): url=BASE_IMG_URL+url
            url=url.replace(" ","%20")
            return url
    except Exception as e: print(f"  Error imagen {image_id}: {e}")
    return ""

def descargar_imagen(url):
    if not url: return None
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 DiarioInfo-PDF/1.8"})
        data=urllib.request.urlopen(req,timeout=12).read()
        img=ImageReader(io.BytesIO(data))
        iw,ih=img.getSize()
        return img,iw,ih
    except Exception as e:
        print(f"  Error descarga img: {e}")
        return None

def draw_placeholder(c,x,y,w,h,msg="Imagen no disponible"):
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
    c.drawImage(img,dx,dy,dw,dh,preserveAspectRatio=True,mask="auto")
    return True
def wrap_text(c,texto,fuente,pts,ancho):
    c.setFont(fuente,pts)
    words=texto.split()
    lines=[]; line=""
    for w in words:
        test=line+" "+w if line else w
        if c.stringWidth(test,fuente,pts)<=ancho: line=test
        else:
            if line: lines.append(line)
            line=w
    if line: lines.append(line)
    return lines

def draw_wrapped(c,texto,x,y,ancho,fuente,pts,color=NEGRO,lh=None,max_lines=99,align="left"):
    if not texto: return y
    if lh is None: lh=pts*1.35
    c.setFont(fuente,pts); c.setFillColorRGB(*color)
    lines=wrap_text(c,texto,fuente,pts,ancho)
    for i,line in enumerate(lines[:max_lines]):
        if align=="center": c.drawCentredString(x+ancho/2,y,line)
        elif align=="right": c.drawRightString(x+ancho,y,line)
        else: c.drawString(x,y,line)
        y-=lh
    return y

def draw_badge(c,texto,x,y,color_bg,color_txt=BLANCO,pts=7,pad_h=4,pad_v=2.5):
    c.setFont(fb,pts)
    tw=c.stringWidth(texto,fb,pts)
    bw=tw+pad_h*2; bh=pts+pad_v*2
    c.setFillColorRGB(*color_bg); c.roundRect(x,y-pad_v,bw,bh,2,fill=1,stroke=0)
    c.setFillColorRGB(*color_txt); c.drawString(x+pad_h,y,texto)
    return bw+4

def draw_linea(c,x,y,w,color,grosor=0.5):
    c.setStrokeColorRGB(*color); c.setLineWidth(grosor)
    c.line(x,y,x+w,y)

def draw_rect_borde(c,x,y,w,h,color_borde,grosor=0.8):
    c.setStrokeColorRGB(*color_borde); c.setFillColorRGB(*BLANCO)
    c.setLineWidth(grosor); c.rect(x,y,w,h,fill=1,stroke=1)

def draw_rect_fill(c,x,y,w,h,color):
    c.setFillColorRGB(*color); c.setStrokeColorRGB(*color)
    c.rect(x,y,w,h,fill=1,stroke=0)

def acento_lateral(c,x,y_top,h,color,grosor=3):
    c.setFillColorRGB(*color); c.rect(x,y_top-h,grosor,h,fill=1,stroke=0)

def draw_logo(c,cx,cy,r=17):
    import math
    c.saveState()
    p=c.beginPath()
    p.arc(cx-r,cy-r,cx+r,cy+r,0,360)
    c.clipPath(p,stroke=0)
    c.setFillColorRGB(*AZUL); c.rect(cx-r,cy-r,r,r*2,fill=1,stroke=0)
    c.setFillColorRGB(*NARANJA); c.rect(cx,cy-r,r,r*2,fill=1,stroke=0)
    tri_size=r*0.55
    c.setFillColorRGB(*BLANCO)
    p2=c.beginPath()
    p2.moveTo(cx-tri_size*0.5,cy+tri_size*0.6)
    p2.lineTo(cx-tri_size*0.5,cy-tri_size*0.6)
    p2.lineTo(cx+tri_size*0.7,cy)
    p2.close(); c.drawPath(p2,fill=1,stroke=0)
    c.restoreState()
def obtener_cotizaciones():
    try:
        import json
        req=urllib.request.Request("https://api.bluelytics.com.ar/v2/latest",headers={"User-Agent":"curl/7.68.0"})
        resp=urllib.request.urlopen(req,timeout=8)
        data=json.loads(resp.read())
        of=data.get("oficial",{}).get("value_sell",0)
        bl=data.get("blue",{}).get("value_sell",0)
        return f"${of:,.0f}",f"${bl:,.0f}"
    except: return "---","---"

def obtener_clima():
    try:
        url="https://wttr.in/Santiago+del+Estero,Argentina?format=%c+%t&m"
        req=urllib.request.Request(url,headers={"User-Agent":"curl/7.68.0"})
        resp=urllib.request.urlopen(req,timeout=8)
        datos=resp.read().decode("utf-8").strip().replace("+"," ")
        return f"Santiago del Estero {datos}"
    except: return "Santiago del Estero"

def cabecera_pagina(c,fecha_txt,clima,cotiz_of,cotiz_bl,numero_pag=None):
    y=H-M
    draw_rect_fill(c,0,y-8*mm,W,8*mm,(0.97,0.97,0.98))
    info=f"{fecha_txt}  |  {clima}  |  Oficial: {cotiz_of}  |  Blue: {cotiz_bl}"
    c.setFont(fn,7); c.setFillColorRGB(*GRIS_OSC)
    c.drawCentredString(W/2,y-5.5*mm,info)
    if numero_pag:
        c.setFont(fn,7); c.setFillColorRGB(*GRIS_MED)
        c.drawRightString(W-M,y-5.5*mm,f"Pg. {numero_pag}")
    y-=8*mm
    draw_linea(c,0,y,W,GRIS_CLAR,0.5)
    y-=3*mm
    r=9; logo_x=W/2-50; logo_cy=y-r-1*mm
    draw_logo(c,logo_x,logo_cy,r)
    tx=logo_x+r+3
    c.setFont(fb,16); c.setFillColorRGB(*AZUL); c.drawString(tx,logo_cy-5.5,"diario")
    tw_d=c.stringWidth("diario",fb,16)
    c.setFont(fb,18); c.setFillColorRGB(*NARANJA); c.drawString(tx+tw_d,logo_cy-6.5,"info")
    tw_i=c.stringWidth("info",fb,18)
    c.setFont(fn,8); c.setFillColorRGB(*GRIS_MED)
    c.drawString(tx+tw_d+tw_i+1,logo_cy-3.5,".com")
    y=logo_cy-r-3*mm
    c.setFont(fn,6.5); c.setFillColorRGB(*GRIS_MED)
    c.drawCentredString(W/2,y,"Santiago del Estero")
    y-=2*mm
    draw_linea(c,M,y,AW,AZUL,1.5)
    y-=2*mm
    return y

def pie_pagina(c,y=None):
    if y is None: y=M+12
    draw_linea(c,M,y+6,AW,GRIS_CLAR,0.5)
    c.setFont(fn,7); c.setFillColorRGB(*GRIS_MED)
    c.drawString(M,y,"www.diarioinfo.com.ar")
    c.drawRightString(W-M,y,"Edicion Impresa    Santiago del Estero")
def generar_tapa(c,notas,cotiz_of,cotiz_bl,clima,fecha_txt):
    n0=notas[0] if notas else {}
    notas_sec=notas[1:4]
    #  Cabecera info bar 
    y=H-M
    draw_rect_fill(c,0,y-7*mm,W,7*mm,(0.97,0.97,0.98))
    info=f"{fecha_txt}  |  {clima}  |  Oficial: {cotiz_of}  |  Blue: {cotiz_bl}"
    c.setFont(fn,7); c.setFillColorRGB(*GRIS_OSC)
    c.drawCentredString(W/2,y-4.8*mm,info)
    y-=7*mm; draw_linea(c,0,y,W,GRIS_CLAR,0.4); y-=1*mm
    #  Logo 
    r=18; logo_x=W/2-55; logo_cy=y-r-2*mm
    draw_logo(c,logo_x,logo_cy,r)
    tx=logo_x+r+4
    c.setFont(fb,26); c.setFillColorRGB(*AZUL); c.drawString(tx,logo_cy-9,"diario")
    tw_d=c.stringWidth("diario",fb,26)
    c.setFont(fb,28); c.setFillColorRGB(*NARANJA); c.drawString(tx+tw_d,logo_cy-10,"info")
    tw_i=c.stringWidth("info",fb,28)
    c.setFont(fn,13); c.setFillColorRGB(*GRIS_MED); c.drawString(tx+tw_d+tw_i+2,logo_cy-5,".com")
    y=logo_cy-r-5
    c.setFont(fn,8); c.setFillColorRGB(*GRIS_MED)
    c.drawCentredString(W/2,y,"Santiago del Estero"); y-=6
    draw_linea(c,M,y,AW,AZUL,1.8); y-=26
    #  Nota principal 
    cat0=n0.get("cat_nombre",""); col0,bg0=cat_style(cat0)
    titulo0=n0.get("title",""); desc0=n0.get("description","")
    img0_url=n0.get("img_url","")
    img0_data=descargar_imagen(img0_url) if img0_url else None
    es_apaisada=True
    if img0_data:
        _,iw0,ih0=img0_data
        es_apaisada=(iw0/ih0)>=1.2
    if img0_data and es_apaisada:
        # LAYOUT APAISADO: titulo + bajada arriba, imagen ancho completo abajo
        draw_badge(c,cat0.upper() if cat0 else "GENERAL",M,y,col0)
        y-=4
        y=draw_wrapped(c,titulo0,M,y,AW,ftb,26,NEGRO,lh=31,max_lines=3,align="center")
        y-=4
        if desc0:
            y=draw_wrapped(c,desc0,M+10*mm,y,AW-20*mm,fi,10.5,GRIS_OSC,lh=14,max_lines=2,align="center")
            y-=5
        img_h=min(72*mm,max(45*mm,y-M-90))
        img_y=y-img_h; dibujar_imagen_adaptativa(c,img0_data,M,img_y,AW,img_h)
        y=img_y
    elif img0_data and not es_apaisada:
        # LAYOUT VERTICAL: imagen en columna izq, texto en columna der
        col_img=AW*0.42; col_txt=AW*0.54; gap=AW*0.04
        img_h=min(110*mm,max(70*mm,y-M-90))
        img_y=y-img_h; dibujar_imagen_adaptativa(c,img0_data,M,img_y,col_img,img_h)
        tx_x=M+col_img+gap; tx_w=col_txt; y_txt=y
        draw_badge(c,cat0.upper() if cat0 else "GENERAL",tx_x,y_txt,col0); y_txt-=16
        y_txt=draw_wrapped(c,titulo0,tx_x,y_txt,tx_w,ftb,22,NEGRO,lh=28,max_lines=5)
        y_txt-=6
        if desc0:
            y_txt=draw_wrapped(c,desc0,tx_x,y_txt,tx_w,fi,10,GRIS_OSC,lh=13,max_lines=4)
        y=img_y
    else:
        # SIN IMAGEN: titulo destacado con fondo
        draw_rect_fill(c,M,y-60,AW,60,GRIS_CLAR)
        draw_badge(c,cat0.upper() if cat0 else "GENERAL",M+6,y-10,col0); y-=18
        y=draw_wrapped(c,titulo0,M+6,y,AW-12,ftb,24,NEGRO,lh=30,max_lines=3)
        y-=6
        if desc0: y=draw_wrapped(c,desc0,M+6,y,AW-12,fi,10.5,GRIS_OSC,lh=14,max_lines=2)
        y-=10
    draw_linea(c,M,y-2,AW,GRIS_CLAR,0.6); y-=8
    #  Notas secundarias (max 3) 
    n_sec=len(notas_sec)
    if n_sec>0:
        sec_h=y-M-16; col_w=AW/max(n_sec,1)-3
        for i,ns in enumerate(notas_sec):
            sx=M+i*(col_w+3); cat_s=ns.get("cat_nombre","")
            col_s,bg_s=cat_style(cat_s)
            # Box de fondo
            draw_rect_fill(c,sx,M+14,col_w,sec_h,bg_s)
            acento_lateral(c,sx,M+14+sec_h,sec_h,col_s,3)
            sy=M+14+sec_h-4
            # Badge categoria
            draw_badge(c,cat_s.upper() if cat_s else "GENERAL",sx+6,sy,col_s,BLANCO,6.5)
            sy-=14
            # Imagen secundaria
            img_s_url=ns.get("img_url","")
            img_s=descargar_imagen(img_s_url) if img_s_url else None
            if img_s:
                img_sh=min(35*mm,sec_h*0.40); img_sy=sy-img_sh
                dibujar_imagen_adaptativa(c,img_s,sx+3,img_sy,col_w-6,img_sh); sy=img_sy-4
            else: sy-=4
            tit_s=ns.get("title","")
            sy=draw_wrapped(c,tit_s,sx+6,sy,col_w-12,fb,9,NEGRO,lh=13,max_lines=4)
            sy-=4
            desc_s=ns.get("description","")
            if desc_s: draw_wrapped(c,desc_s,sx+6,sy,col_w-12,fn,7.5,GRIS_OSC,lh=10.5,max_lines=3)
    pie_pagina(c)
def draw_cuerpo_columnas(c,texto,x,y,w,h_max,fuente,pts,color,lh,n_cols=2,gap=4*mm):
    if not texto or h_max<=0: return y
    col_w=(w-(n_cols-1)*gap)/n_cols
    lines_all=[]
    for parrafo in texto.split('\n'):
        parrafo=parrafo.strip()
        if not parrafo: lines_all.append(""); continue
        lines_all+=wrap_text(c,parrafo,fuente,pts,col_w)
        lines_all.append("")
    lines_per_col=max(1,int(h_max/lh))
    c.setFont(fuente,pts); c.setFillColorRGB(*color)
    ci=0; cx=x; cy=y; count=0
    for line in lines_all:
        if count>=lines_per_col:
            ci+=1
            if ci>=n_cols: break
            cx=x+ci*(col_w+gap); cy=y; count=0
        if line=="": cy-=lh*0.5
        else: c.drawString(cx,cy,line); cy-=lh
        count+=1
    return min(y-lines_per_col*lh, cy)

def generar_pagina_nota(c,nota,n_pagina,fecha_txt,clima,cotiz_of,cotiz_bl):
    c.showPage()
    y=cabecera_pagina(c,fecha_txt,clima,cotiz_of,cotiz_bl,n_pagina)
    y-=4*mm
    cat=nota.get("cat_nombre",""); col,bg=cat_style(cat)
    titulo=nota.get("title",""); desc=nota.get("description","")
    contenido=limpiar_html(nota.get("content","") or nota.get("body","") or "")
    img_url=nota.get("img_url","")
    img_data=descargar_imagen(img_url) if img_url else None
    es_apaisada=True
    if img_data:
        _,iw,ih=img_data; es_apaisada=(iw/ih)>=1.2
    #  Cabecera de nota: badge + linea de acento 
    if cat:
        bw=draw_badge(c,cat.upper(),M,y,col,BLANCO,8,6,3)
        draw_linea(c,M+bw+4,y+4,AW-bw-4,col,1.0)
    else: draw_linea(c,M,y+4,AW,AZUL,1.0)
    y-=18
    #  Imagen + titulo segun orientacion 
    if img_data and es_apaisada:
        # Imagen ancho completo
        img_h=min(70*mm,max(50*mm,(y-M-120)))
        img_y=y-img_h
        dibujar_imagen_adaptativa(c,img_data,M,img_y,AW,img_h)
        y=img_y-6
        y=draw_wrapped(c,titulo,M,y,AW,ftb,22,NEGRO,lh=28,max_lines=3,align="left")
        y-=4
        if desc: y=draw_wrapped(c,desc,M,y,AW,fi,10,GRIS_OSC,lh=14,max_lines=2)
        y-=8; draw_linea(c,M,y,AW,GRIS_CLAR,0.5); y-=8
    elif img_data and not es_apaisada:
        # Imagen vertical en col izq
        col_img=AW*0.38; col_txt=AW*0.58; gap_c=AW*0.04
        img_h=min(100*mm,max(60*mm,(y-M-50))); img_y=y-img_h
        dibujar_imagen_adaptativa(c,img_data,M,img_y,col_img,img_h)
        tx_x=M+col_img+gap_c; tx_w=col_txt; y_t=y
        y_t=draw_wrapped(c,titulo,tx_x,y_t,tx_w,ftb,20,NEGRO,lh=26,max_lines=5)
        y_t-=6
        if desc: y_t=draw_wrapped(c,desc,tx_x,y_t,tx_w,fi,10,GRIS_OSC,lh=14,max_lines=3)
        y=min(img_y,y_t)-8; draw_linea(c,M,y,AW,GRIS_CLAR,0.5); y-=8
    else:
        # Sin imagen: titulo con fondo sutil
        draw_rect_fill(c,M,y-50,AW,50,bg)
        y=draw_wrapped(c,titulo,M+6,y-8,AW-12,ftb,22,NEGRO,lh=28,max_lines=3)
        y-=6
        if desc: y=draw_wrapped(c,desc,M,y,AW,fi,10.5,GRIS_OSC,lh=14,max_lines=2)
        y-=8; draw_linea(c,M,y,AW,GRIS_CLAR,0.5); y-=8
    #  Cuerpo del articulo en 2 columnas 
    espacio_cuerpo=y-M-20
    if contenido and espacio_cuerpo>30:
        draw_cuerpo_columnas(c,contenido,M,y,AW,espacio_cuerpo,fn,9.5,NEGRO,13.5,n_cols=2)
        y-=espacio_cuerpo
    #  Espacio publicitario si sobra 
    if y-M>50*mm:
        pub_h=min(40*mm,y-M-20); pub_y=M+10
        draw_rect_fill(c,M,pub_y,AW,pub_h,GRIS_CLAR)
        draw_rect_borde(c,M,pub_y,AW,pub_h,GRIS_MED,0.5)
        c.setFont(fn,9); c.setFillColorRGB(*GRIS_MED)
        c.drawCentredString(W/2,pub_y+pub_h/2,"ESPACIO PUBLICITARIO")
        c.setFont(fn,7); c.drawCentredString(W/2,pub_y+pub_h/2-12,"publicidad@diarioinfo.com.ar")
    pie_pagina(c)
def obtener_notas(limite=15):
    db=get_db()
    from datetime import datetime,timezone,timedelta
    hoy=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    fin=hoy+timedelta(days=1)
    cats_cache={}
    def get_cat(cid):
        if not cid: return ""
        key=str(cid)
        if key not in cats_cache:
            try:
                cat_doc=db["categories"].find_one({"_id":ObjectId(key)})
                cats_cache[key]=(cat_doc or {}).get("name") or (cat_doc or {}).get("title") or ""
            except: cats_cache[key]=""
        return cats_cache[key]
    def fetch(filtro,orden,lim):
        docs=list(db.articles.find(filtro).sort(orden).limit(lim))
        result=[]
        for n in docs:
            img_url=obtener_imagen_url(n.get("imageId",""))
            cat_nombre=get_cat(n.get("category",""))
            result.append({**n,"img_url":img_url,"cat_nombre":cat_nombre})
        return result
    notas=fetch({"status":"published","publicationDate":{"$gte":hoy,"$lt":fin}},[("priority",-1),("publicationDate",-1)],limite)
    if len(notas)<4:
        tres_dias=hoy-timedelta(days=3)
        notas=fetch({"status":"published","publicationDate":{"$gte":tres_dias}},[("priority",-1),("publicationDate",-1)],limite)
    return notas

def generar_flipbook(pdf_path,html_path,fecha_str):
    html=f"""<!DOCTYPE html><html><head><meta charset='UTF-8'>
<title>DiarioInfo Edicion Impresa {fecha_str}</title>
<style>body{{margin:0;background:#222;display:flex;flex-direction:column;align-items:center;font-family:Arial,sans-serif}}
h1{{color:#fff;margin:20px 0 10px;font-size:18px}}
iframe{{width:90vw;height:90vh;border:none;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.5)}}
</style></head><body>
<h1>DiarioInfo  Edicion Impresa {fecha_str}</h1>
<iframe src='/revistas/diarioinfo/{fecha_str}.pdf'></iframe>
</body></html>"""
    with open(html_path,"w",encoding="utf-8") as f: f.write(html)

def main():
    global fn,fb,fi,ftb
    loaded=cargar_fuentes()
    print(f"Fuentes OK: {loaded}")
    if "Lato-Regular" not in loaded: fn=fb=fi=ftb="Helvetica"
    if "Lato-Bold" not in loaded: fb=ftb="Helvetica-Bold"
    if "Lato-Italic" not in loaded: fi="Helvetica-Oblique"
    cotiz_of,cotiz_bl=obtener_cotizaciones()
    print(f"  Oficial: {cotiz_of} | Blue: {cotiz_bl}")
    clima=obtener_clima(); print(f"  {clima}")
    hoy=datetime.now(timezone.utc)
    dias_es=["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
    meses_es=["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    fecha_txt=f"{dias_es[hoy.weekday()]} {hoy.day} de {meses_es[hoy.month-1]} de {hoy.year}"
    fecha_str=hoy.strftime("%Y-%m-%d")
    notas=obtener_notas(15); print(f"  {len(notas)} notas")
    out_dir=os.path.expanduser("~/public_html/revistas/diarioinfo")
    flip_dir=os.path.expanduser("~/public_html/flipbook")
    os.makedirs(out_dir,exist_ok=True); os.makedirs(flip_dir,exist_ok=True)
    pdf_path=os.path.join(out_dir,f"{fecha_str}.pdf")
    html_path=os.path.join(flip_dir,f"{fecha_str}.html")
    print(f"Generando PDF: {pdf_path}")
    c=canvas.Canvas(pdf_path,pagesize=A4)
    c.setTitle(f"Diario Info - Edicion Impresa {fecha_str}")
    c.setAuthor("diarioinfo.com.ar")
    # Tapa
    print("Tapa...")
    generar_tapa(c,notas,cotiz_of,cotiz_bl,clima,fecha_txt)
    # Paginas internas
    for i,nota in enumerate(notas):
        print(f"Pagina {i+2}: {nota.get('title','')[:50]}...")
        generar_pagina_nota(c,nota,i+2,fecha_txt,clima,cotiz_of,cotiz_bl)
    c.save()
    sz=os.path.getsize(pdf_path)/1024
    print(f"PDF OK! {sz:.1f} KB")
    generar_flipbook(pdf_path,html_path,fecha_str)
    print("Flipbook...")
    print(f"=== COMPLETADO ===")
    print(f"PDF:    {pdf_path}")
    print(f"Acceso: https://diarioinfo.com/flipbook/{fecha_str}.html")

if __name__=="__main__":
    main()

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: Bootlogo HD Satelit, 2026

import os
import sys
import subprocess
from PIL import Image, ImageDraw, ImageFont

L, H = 1920, 1080
TEXT_SEMNATURA = "hdsatelit.com & moneasoftware.com"

def cauta_font():
    candidati = [
        "/usr/share/enigma2/HDSatelit/fonts/HdsRegular.ttf",
        "/usr/share/enigma2/HDSatelit/fonts/HdsCond.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/DejaVuSans.ttf",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "HdsRegular.ttf"),
    ]
    # pe calculator: fontul de langa acest fisier (HDSatelit/fonts din depozit) sau cel din variabila HDS_FONT_BOOTLOGO
    if os.environ.get("HDS_FONT_BOOTLOGO"):
        candidati.insert(0, os.environ["HDS_FONT_BOOTLOGO"])
    for c in candidati:
        if os.path.exists(c):
            return c
    return None

def umple_si_decupeaza(im):
    im = im.convert("RGB")
    scara = max(L / float(im.width), H / float(im.height))
    lat_nou = int(round(im.width * scara))
    inalt_nou = int(round(im.height * scara))
    im = im.resize((lat_nou, inalt_nou), Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.BICUBIC)
    x = (lat_nou - L) // 2
    y = (inalt_nou - H) // 2
    return im.crop((x, y, x + L, y + H))

def aplica_semnatura(cale_intrare, cale_iesire_png=None):
    """
    Ia orice imagine a utilizatorului, o aduce la 1920x1080 si aplica semnatura oficiala
    centrata in partea inferioara: 'hdsatelit.com & moneasoftware.com'.
    """
    im = Image.open(cale_intrare)
    ecran = umple_si_decupeaza(im)
    d = ImageDraw.Draw(ecran)

    cale_font = cauta_font()
    f = None
    if cale_font:
        try:
            f = ImageFont.truetype(cale_font, 28)
        except Exception:
            f = None
    if f is None:
        f = ImageFont.load_default()

    # Calcul lungime text
    try:
        w = d.textlength(TEXT_SEMNATURA, font=f)
    except AttributeError:
        w, _ = d.textsize(TEXT_SEMNATURA, font=f)

    x = (L - int(w)) // 2
    y = H - 64

    # Umbra fina pentru lizibilitate perfecta pe orice fundal (deschis sau inchis)
    d.text((x + 2, y + 2), TEXT_SEMNATURA, font=f, fill=(10, 14, 23))
    d.text((x, y), TEXT_SEMNATURA, font=f, fill=(180, 205, 245))

    if not cale_iesire_png:
        cale_iesire_png = os.path.splitext(cale_intrare)[0] + "_hds_boot.png"

    ecran.save(cale_iesire_png, "PNG")
    return cale_iesire_png

def converteste_in_mvi(cale_png, cale_mvi="/usr/share/bootlogo.mvi"):
    """
    Converteste PNG 1920x1080 in format MPEG-2 I-frame bootlogo.mvi folosind ffmpeg direct pe receptor.
    """
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", cale_png,
        "-vf", "format=yuv420p",
        "-c:v", "mpeg2video",
        "-q:v", "2",
        "-frames:v", "1",
        "-f", "mpeg2video",
        cale_mvi
    ]
    subprocess.run(cmd, check=True)
    return cale_mvi

def proceseaza_bootlogo_complet(cale_imagine_intrare, cale_mvi_destinatie="/usr/share/bootlogo.mvi"):
    png = aplica_semnatura(cale_imagine_intrare)
    mvi = converteste_in_mvi(png, cale_mvi_destinatie)
    return mvi

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Folosire: python3 hds_bootlogo.py <cale_imagine> [cale_iesire_mvi]")
        sys.exit(1)
    img_in = sys.argv[1]
    mvi_out = sys.argv[2] if len(sys.argv) > 2 else "/usr/share/bootlogo.mvi"
    mvi = proceseaza_bootlogo_complet(img_in, mvi_out)
    print("[OK] Bootlogo generat cu succes:", mvi)

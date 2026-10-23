#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: Bootlogo OSD Overlay, 2026

import os
import sys
from PIL import Image, ImageDraw, ImageFont

FB_DEVICE = "/dev/fb0"
L, H = 1920, 1080
TEXT_SEMNATURA = "hdsatelit.com & moneasoftware.com"

def gaseste_font():
    candidati = [
        "/usr/share/enigma2/HDSatelit/fonts/HdsRegular.ttf",
        "/usr/share/enigma2/HDSatelit/fonts/HdsCond.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/DejaVuSans.ttf",
    ]
    for c in candidati:
        if os.path.exists(c):
            return c
    return None

def deseneaza_osd_boot():
    if not os.path.exists(FB_DEVICE):
        return

    img = Image.new("RGBA", (L, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    fpath = gaseste_font()
    f = None
    if fpath:
        try:
            f = ImageFont.truetype(fpath, 26)
        except Exception:
            f = None
    if not f:
        f = ImageFont.load_default()

    try:
        w = d.textlength(TEXT_SEMNATURA, font=f)
    except AttributeError:
        w, _ = d.textsize(TEXT_SEMNATURA, font=f)

    x = int((L - w) // 2)
    y = H - 54

    # Capsula tip 'dark glass' semi-transparenta (lizibilitate pe orice fundal)
    pad_x, pad_y = 22, 8
    d.rounded_rectangle(
        [x - pad_x, y - pad_y, x + int(w) + pad_x, y + 28 + pad_y],
        radius=14,
        fill=(10, 14, 26, 200),
        outline=(56, 189, 248, 140),
        width=1
    )
    d.text((x, y), TEXT_SEMNATURA, font=f, fill=(240, 246, 252, 255))

    # Convertim in BGRA (little-endian uint32 ARGB)
    r, g, b, a = img.split()
    bgra = Image.merge("RGBA", (b, g, r, a))

    linii_de_scris = 90
    crop = bgra.crop((0, H - linii_de_scris, L, H))
    offset = (H - linii_de_scris) * L * 4

    try:
        with open(FB_DEVICE, "r+b") as fb:
            fb.seek(offset)
            fb.write(crop.tobytes())
            fb.flush()
    except Exception as e:
        sys.stderr.write("[HDS-OSD] Eroare scriere fb0: {}\n".format(e))

if __name__ == "__main__":
    deseneaza_osd_boot()

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.8.0: imaginea TV pe afisajul color DM900 (driverul nu are live_enable/sd_detach).
# Bucla in afara enigma2: grab (-v = numai video, mod 1; fara -v = cu OSD, mod 3), 400x240, BGR_565_LE
# (R si B schimbate, ca la afisajul Dream; confirmat de un om pe DM900) in /tmp/lcdtv.raw (scris atomic). Pluginul HdsLcdTv ia fisierul si il scrie pe fd-ul afisajului.
import os, sys, time, subprocess
from PIL import Image, ImageChops
W, H = 400, 240
pauza = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
mod = sys.argv[2] if len(sys.argv) > 2 else "1"
optiuni = ["-v"] if mod != "3" else []
# fisiere proprii (pid), ca doua bucle sa nu-si strice cadrele; iese singura cand enigma2 a murit (parintele devine init)
JPG, TMP = "/tmp/lcdtv-%d.jpg" % os.getpid(), "/tmp/lcdtv-%d.tmp" % os.getpid()
while os.getppid() != 1:
	try:
		subprocess.call(["grab"] + optiuni + ["-j", "75", "-r", str(W), JPG], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		im = Image.open(JPG).convert("RGB").resize((W, H))
		b, g, r = im.split()
		lo = ImageChops.add(r.point(lambda x: x >> 3), g.point(lambda x: ((x >> 2) & 7) << 5))
		hi = ImageChops.add(b.point(lambda x: (x >> 3) << 3), g.point(lambda x: x >> 5))
		d = Image.merge("LA", (lo, hi)).tobytes()
		with open(TMP, "wb") as f:
			f.write(d)
		os.rename(TMP, "/tmp/lcdtv.raw")
	except Exception as e:
		print("lcdtv: %s" % e); sys.stdout.flush()
		time.sleep(2)
	time.sleep(pauza)
for f in (JPG, TMP):
	try:
		os.remove(f)
	except OSError:
		pass

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Posterele si fundalurile filmelor si serialelor: aduse la nevoie, pe un singur fir, micsorate la marimea din ecran si tinute
intr-un cache cu plafon. Niciodata toate odata: ecranul cere numai ce se vede (si cateva inainte), cea mai noua cerere intai.

- image.tmdb.org: se cere direct marimea mica (w185/w342 la postere, w780 la fundal), deci ~15-60 KB in loc de sute.
- alte gazde: cel mult MAX_OCTETI, apoi micsorare cu PIL (JPEG cu draft: decodare direct la marimea mica).
- fundalul se intuneca spre stanga si spre jos chiar in poza (textul de deasupra se citeste fara alt strat), JPEG opac.
- cache-ul: /tmp/hds-vod-poze (memorie, nu flash: posterele se schimba des), MAX_CACHE / MAX_FISIERE, cele vechi sterse intai.
- numele fisierelor sunt sume, fara adrese; adresele nu ajung in jurnal si nici in pagina web (acolo merge numai semnul).
"""
import hashlib
import io
import os
import re
import threading
import time
from collections import OrderedDict

DOSAR = "/tmp/hds-vod-poze"
MAX_OCTETI = 3 * 1024 * 1024
MAX_CACHE = 24 * 1024 * 1024
MAX_FISIERE = 900
MAX_COADA = 48
MAX_SEMNE = 4000
TERMEN_S = 8
REINCEARCA_S = 600
CALITATE = 82
_TMDB = re.compile(r"^(https?://image\.tmdb\.org/t/p/)[^/]+(/.+)$")
_lacat = threading.Lock()
_coada = OrderedDict()           # nume -> (adresa, latime, inaltime, fel)
_ratate = {}                     # nume -> ora
_semne = OrderedDict()           # semn public -> adresa (pentru pagina web)
_fir = None
_generatie = 0


def generatie():
	"""Creste cand o poza noua e gata; ecranul isi redeseneaza randurile vizibile."""
	return _generatie


def marimeTmdb(adresa, latime, fel):
	m = _TMDB.match(adresa or "")
	if not m:
		return adresa
	if fel == "fundal":
		marime = "w780" if latime <= 1000 else "w1280"
	else:
		marime = "w185" if latime <= 190 else ("w342" if latime <= 350 else "w500")
	return m.group(1) + marime + m.group(2)


def _nume(adresa, latime, inaltime, fel):
	return hashlib.sha1(("%s|%d|%d|%s" % (adresa, latime, inaltime, fel)).encode("utf-8", "replace")).hexdigest()[:24]


def cale(adresa, latime, inaltime, fel="poster"):
	"""Fisierul gata (JPEG la marimea ceruta) sau "" daca nu e inca; nu face retea."""
	if not adresa:
		return ""
	p = os.path.join(DOSAR, _nume(adresa, latime, inaltime, fel) + ".jpg")
	return p if os.path.isfile(p) else ""


def cere(adresa, latime, inaltime, fel="poster"):
	"""Fisierul daca e gata, altfel "" si poza intra in coada (cea mai noua cerere se face prima)."""
	global _fir
	latime, inaltime = int(latime), int(inaltime)
	from Components.HdsVod import activ
	if not activ("poze"):
		return ""
	if not adresa or not (16 <= latime <= 1920 and 16 <= inaltime <= 1080):
		return ""
	gata = cale(adresa, latime, inaltime, fel)
	if gata:
		return gata
	n = _nume(adresa, latime, inaltime, fel)
	with _lacat:
		if time.monotonic() - _ratate.get(n, -REINCEARCA_S) < REINCEARCA_S:
			return ""
		_coada.pop(n, None)
		_coada[n] = (adresa, latime, inaltime, fel)
		while len(_coada) > MAX_COADA:
			_coada.popitem(last=False)
		if _fir is None:
			_fir = threading.Thread(target=_bucla, name="HdsVodPoze")
			_fir.daemon = True
			_fir.start()
	return ""


def uita():
	"""Ecranul s-a inchis: ce n-a inceput nu se mai aduce."""
	with _lacat:
		_coada.clear()


def semn(adresa):
	"""Semnul public al unei poze (pentru pagina web), fara adresa in el."""
	if not adresa:
		return ""
	s = hashlib.sha1(adresa.encode("utf-8", "replace")).hexdigest()[:20]
	with _lacat:
		_semne[s] = adresa
		_semne.move_to_end(s)
		while len(_semne) > MAX_SEMNE:
			_semne.popitem(last=False)
	return s


def adresaSemn(s):
	with _lacat:
		return _semne.get(s or "")


def _bucla():
	global _fir, _generatie
	while True:
		with _lacat:
			if not _coada:
				_fir = None
				return
			n, (adresa, latime, inaltime, fel) = _coada.popitem(last=True)
		try:
			if not cale(adresa, latime, inaltime, fel):
				_fa(adresa, latime, inaltime, fel, os.path.join(DOSAR, n + ".jpg"))
				_generatie += 1
		except Exception as e:
			with _lacat:
				_ratate[n] = time.monotonic()
				if len(_ratate) > 2000:
					_ratate.clear()
			print("[HdsVodPoze] %s: %s" % (fel, type(e).__name__))


def _citeste(adresa):
	from Components import HdsIptvClient as C
	inceput = time.monotonic()
	with C.deschide(adresa, termen=TERMEN_S) as r:
		lung = r.headers.get("Content-Length")
		if lung and lung.isdigit() and int(lung) > MAX_OCTETI:
			raise ValueError("marime")
		bucati, n = [], 0
		citire = getattr(r, "read1", r.read)
		while True:
			b = citire(65536)
			if not b:
				return b"".join(bucati)
			n += len(b)
			if n > MAX_OCTETI or time.monotonic() - inceput > 2 * TERMEN_S:
				raise ValueError("marime")
			bucati.append(b)


def micsoreaza(date, latime, inaltime, fel):
	"""Octetii pozei -> JPEG la latime x inaltime (decupat la mijloc, fara benzi negre); fundalul intunecat spre stanga si jos."""
	from PIL import Image
	Image.MAX_IMAGE_PIXELS = 40 * 1000 * 1000
	img = Image.open(io.BytesIO(date))
	if img.format == "JPEG":
		img.draft("RGB", (latime, inaltime))
	img = img.convert("RGB")
	l, h = img.size
	scara = max(float(latime) / l, float(inaltime) / h)
	nl, nh = max(latime, int(l * scara + 0.5)), max(inaltime, int(h * scara + 0.5))
	img = img.resize((nl, nh), Image.BILINEAR)
	x, y = (nl - latime) // 2, (nh - inaltime) // 4 if fel == "fundal" else (nh - inaltime) // 2
	img = img.crop((x, y, x + latime, y + inaltime))
	if fel == "fundal":
		img = _intuneca(img)
	iesire = io.BytesIO()
	img.save(iesire, "JPEG", quality=CALITATE, optimize=False)
	return iesire.getvalue()


def _intuneca(img):
	"""Spre stanga si spre jos, cate o masca liniara (fondul temei #0B1020), ca titlul si randurile de postere sa se citeasca."""
	from PIL import Image
	l, h = img.size
	ml, mh = 64, 36             # masca mica, apoi marita: pe receptor o bucla pe fiecare pixel ar tine o secunda
	masca = Image.new("L", (ml, mh), 0)
	px = masca.load()
	for xx in range(ml):
		a = max(0.0, 1.0 - xx / (0.62 * ml)) * 0.92
		for yy in range(mh):
			b = max(0.0, (yy - 0.38 * mh) / (0.62 * mh)) * 0.95
			px[xx, yy] = int(255 * min(1.0, max(a, b, 0.25)))
	masca = masca.resize((l, h), Image.BILINEAR)
	fond = Image.new("RGB", (l, h), (0x0B, 0x10, 0x20))
	return Image.composite(fond, img, masca)


def _fa(adresa, latime, inaltime, fel, tinta):
	date = _citeste(marimeTmdb(adresa, latime, fel))
	jpeg = micsoreaza(date, latime, inaltime, fel)
	os.makedirs(DOSAR, mode=0o700, exist_ok=True)
	tmp = tinta + ".tmp"
	with open(tmp, "wb") as f:
		f.write(jpeg)
	os.replace(tmp, tinta)
	_curata()


def _curata():
	try:
		fisiere = []
		for f in os.scandir(DOSAR):
			if f.is_file(follow_symlinks=False) and f.name.endswith(".jpg"):
				st = f.stat(follow_symlinks=False)
				fisiere.append((st.st_mtime, st.st_size, f.path))
	except OSError:
		return
	fisiere.sort(reverse=True)
	total = 0
	for i, (_ora, marime, p) in enumerate(fisiere):
		total += marime
		if i >= MAX_FISIERE or total > MAX_CACHE:
			try:
				os.unlink(p)
			except OSError:
				pass

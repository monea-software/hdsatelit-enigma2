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
# Fundalurile: fondul temei (#0B1020) pus peste poza, mai tare unde sta textul (_intuneca). FSV (15.11.2026, LinuxSat 164155): masca
# veche (numai stanga, 0 dupa 62% din latime, si jos de la 38%) lasa titlul si descrierea albe peste o poza luminoasa (zapada, fum)
# aproape fara contrast (1,2..2,8:1 in cel mai rau loc). Acum fiecare text din cele trei ecrane are cel putin 3:1 si peste o poza
# complet alba (teste/test_fsv_contrast_filme_076.py), iar etichetele au si umbra (Screens/HdsFilmeSeriale.py).
# (intunecarea la stanga, la X1, la dreapta, X1 din latime, de unde incepe in jos, unde ajunge jos, cat jos)
MASTI = {
	"fundal": (0.92, 0.75, 0.58, 0.72, 0.30, 0.75, 0.92),          # acasa si pagina serialului: textul sta la stanga si sus
	"fundal_pagina": (0.92, 0.80, 0.72, 0.72, 0.30, 0.75, 0.92),   # pagina filmului: textul ajunge pana aproape de marginea din dreapta
}
VERSIUNE_MASCA = 2      # intra in numele fisierului: un fundal facut cu masca veche (in /tmp, peste o repornire a interfetei) nu ramane
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
	if fel in MASTI:
		marime = "w780" if latime <= 1000 else "w1280"
	else:
		marime = "w185" if latime <= 190 else ("w342" if latime <= 350 else "w500")
	return m.group(1) + marime + m.group(2)


def _nume(adresa, latime, inaltime, fel):
	text = "%s|%d|%d|%s" % (adresa, latime, inaltime, fel)
	if fel in MASTI:
		text += "|m%d" % VERSIUNE_MASCA
	return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:24]


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


# Filmele de pe disc (Components/HdsVodDisc): o poza de langa film ('/media/hdd/movie/x.jpg') sau un cadru din film
# ('cadru:/media/hdd/movie/x.mkv', scos cu ffmpeg tot pe firul pozelor, numai pentru ce se vede).
LOCALE = ("/media/", "/hdd/", "/tmp/hds-vod-")


def _local(cale):
	return cale.startswith(LOCALE) and "/../" not in cale and os.path.isfile(cale)


def _citeste(adresa):
	if adresa.startswith("cadru:"):
		from Components import HdsVodDisc
		cale = adresa[6:].split("#", 1)[0]
		if not _local(cale):
			raise ValueError("cale")
		return HdsVodDisc.cadru(cale)
	if adresa.startswith("/"):
		if not _local(adresa) or os.path.getsize(adresa) > MAX_OCTETI:
			raise ValueError("cale")
		with open(adresa, "rb") as f:
			return f.read(MAX_OCTETI)
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
	x, y = (nl - latime) // 2, (nh - inaltime) // 4 if fel in MASTI else (nh - inaltime) // 2
	img = img.crop((x, y, x + latime, y + inaltime))
	if fel in MASTI:
		img = _intuneca(img, MASTI[fel])
	iesire = io.BytesIO()
	img.save(iesire, "JPEG", quality=CALITATE, optimize=False)
	return iesire.getvalue()


def intunecare(fx, fy, masca=None):
	"""Cat fond se pune peste poza in punctul (fx, fy), ca parte din latime si inaltime (0..1): cea mai mare dintre intunecarea spre
	stanga (scade liniar pana la X1, apoi pana la marginea din dreapta) si cea spre jos (creste liniar de la Y0 la Y1)."""
	stanga, la_x1, dreapta, x1, y0, y1, jos = masca or MASTI["fundal"]
	a = stanga - (stanga - la_x1) * fx / x1 if fx <= x1 else la_x1 - (la_x1 - dreapta) * (fx - x1) / (1.0 - x1)
	b = 0.0 if fy <= y0 else min(jos, jos * (fy - y0) / (y1 - y0))
	return min(1.0, max(a, b))


def _intuneca(img, masca=None):
	"""Fondul temei (#0B1020) peste poza dupa intunecare(), ca titlul, descrierea si randurile de postere sa se citeasca oricat de
	luminoasa e poza."""
	from PIL import Image
	l, h = img.size
	ml, mh = 64, 36             # masca mica, apoi marita: pe receptor o bucla pe fiecare pixel ar tine o secunda
	m = Image.new("L", (ml, mh), 0)
	px = m.load()
	for xx in range(ml):
		for yy in range(mh):
			px[xx, yy] = int(255 * intunecare(xx / (ml - 1.0), yy / (mh - 1.0), masca) + 0.5)
	m = m.resize((l, h), Image.BILINEAR)
	fond = Image.new("RGB", (l, h), (0x0B, 0x10, 0x20))
	return Image.composite(fond, img, m)


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

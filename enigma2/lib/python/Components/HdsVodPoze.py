# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Posterele si fundalurile filmelor si serialelor: aduse la nevoie, pe un singur fir, micsorate la marimea din ecran si tinute
intr-un cache cu plafon. Niciodata toate odata: ecranul cere numai ce se vede (si cateva inainte), cea mai noua cerere intai.

- image.tmdb.org: se cere direct marimea mica (w185/w342 la postere, w780 la fundal), deci ~15-60 KB in loc de sute.
- alte gazde: cel mult MAX_OCTETI, apoi micsorare cu PIL (JPEG cu draft: decodare direct la marimea mica).
- fundalul se intuneca spre stanga si spre jos chiar in poza (textul de deasupra se citeste fara alt strat), JPEG opac.
- cache-ul: pe stickul sau discul montat in /media/hdd, cand se poate scrie acolo (DOSAR_DISC, dosar ascuns, impartit in 256 de
  subdosare dupa primele doua semne ale numelui: pe vfat mii de nume lungi intr-un singur dosar se cauta greu), cu plafon mare
  (MAX_CACHE_DISC, cel mult un sfert din locul liber): posterele raman peste reporniri si nu se mai aduc din nou. Fara stick:
  /tmp/hds-vod-poze (memorie: niciodata pe flash), MAX_CACHE (mai mic pe receptoarele cu memorie putina), MAX_FISIERE.
  Cele vechi se sterg intai. Ce e in cache se tine intr-un index in memorie, facut de firul pozelor: firul principal nu mai
  intreaba discul de fiecare poster (pe un receptor incarcat o singura intrebare a tinut firul principal 5 s). Stickul scos in
  timpul folosirii: nicio eroare catre om, posterele trec pe /tmp; fara fsync pe fiecare poza.
- numele fisierelor sunt sume, fara adrese; adresele nu ajung in jurnal si nici in pagina web (acolo merge numai semnul).
"""
import hashlib
import io
import os
import re
import shutil
import threading
import time
from collections import OrderedDict

DOSAR = "/tmp/hds-vod-poze"
MONTARE = "/media/hdd"
DOSAR_DISC = MONTARE + "/.hds-vod-poze"
MAX_OCTETI = 3 * 1024 * 1024
MAX_CACHE = 24 * 1024 * 1024
MAX_CACHE_MEMORIE_PUTINA = 8 * 1024 * 1024    # /tmp e memorie: pe un receptor sub PRAG_MEMORIE nu tine 24 MB de postere
PRAG_MEMORIE = 600 * 1024 * 1024
MAX_FISIERE = 900
MAX_CACHE_DISC = 256 * 1024 * 1024            # ~15.000 de postere sau ~3.000 de fundaluri
MAX_FISIERE_DISC = 30000
MIN_CACHE_DISC = 16 * 1024 * 1024             # sub atat (stick aproape plin) posterele raman in /tmp
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
_loc = None                      # {"dosar", "max", "fisiere", "disc"}: unde stau pozele acum (ales de firul pozelor)
_index = {}                      # nume -> [ora, marime]: ce e in cache (citit o data, apoi tinut la zi de firul pozelor)
_total = [0]


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


def _caleFisier(loc, nume):
	if loc["disc"]:
		return os.path.join(loc["dosar"], nume[:2], nume + ".jpg")
	return os.path.join(loc["dosar"], nume + ".jpg")


def _locBun(loc):
	return loc is not None and loc["dosar"] == (DOSAR_DISC if loc["disc"] else DOSAR)


def cale(adresa, latime, inaltime, fel="poster"):
	"""Fisierul gata (JPEG la marimea ceruta) sau "" daca nu e inca; nu face retea si nu intreaba discul (indexul din memorie)."""
	loc = _loc
	if not adresa or not _locBun(loc):
		return ""
	n = _nume(adresa, latime, inaltime, fel)
	return _caleFisier(loc, n) if n in _index else ""


def lipsa(cale_fisier):
	"""Ecranul n-a putut citi fisierul (stickul scos, fisier taiat de o pana de curent): iese din index, deci se aduce din nou si
	se scrie peste el; firul pozelor verifica la urmatoarea poza daca dosarul de pe stick mai e (numai atunci reface locul)."""
	global _loc
	nume = os.path.basename(cale_fisier or "")[:-4]
	if _index.pop(nume, None) is not None and _loc is not None and _loc["disc"]:
		_loc = dict(_loc, verifica=True)


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


def _memoriePutina():
	try:
		with open("/proc/meminfo") as f:
			for rand in f:
				if rand.startswith("MemTotal:"):
					return int(rand.split()[1]) * 1024 < PRAG_MEMORIE
	except (IOError, OSError, ValueError, IndexError):
		pass
	return False


def _locTmp():
	return {"dosar": DOSAR, "max": MAX_CACHE_MEMORIE_PUTINA if _memoriePutina() else MAX_CACHE, "fisiere": MAX_FISIERE, "disc": False}


def _montat(cale):
	return os.path.ismount(cale)


def _alegeLoc():
	"""Pe firul pozelor: stickul sau discul din MONTARE daca e montat (nu un dosar de pe flash) si se poate scrie, altfel /tmp."""
	try:
		montare = os.path.realpath(MONTARE)
		if montare != "/" and _montat(montare):
			if not os.path.isdir(DOSAR_DISC):
				os.makedirs(DOSAR_DISC)
			proba = os.path.join(DOSAR_DISC, ".proba")
			with open(proba, "wb") as f:
				f.write(b"1")
			os.unlink(proba)
			return {"dosar": DOSAR_DISC, "max": MAX_CACHE_DISC, "fisiere": MAX_FISIERE_DISC, "disc": True,
				"liber": shutil.disk_usage(DOSAR_DISC).free}
	except (IOError, OSError):
		pass
	return _locTmp()


def _citesteIndex(loc):
	"""nume -> [ora, marime] pentru tot ce e in dosarul ales (o data, pe firul pozelor)."""
	index = {}
	dosare = [loc["dosar"]]
	if loc["disc"]:
		try:
			dosare = [e.path for e in os.scandir(loc["dosar"]) if len(e.name) == 2 and e.is_dir(follow_symlinks=False)]
		except OSError:
			dosare = []
	for d in dosare:
		try:
			for f in os.scandir(d):
				if f.name.endswith(".jpg") and f.is_file(follow_symlinks=False):
					st = f.stat(follow_symlinks=False)
					if st.st_size > 0:              # o poza goala (scrisa pe jumatate, fara fsync) se aduce din nou
						index[f.name[:-4]] = [st.st_mtime, st.st_size]
		except OSError:
			pass
	return index


def _schimbaLoc(loc):
	global _loc, _index, _generatie
	index = _citesteIndex(loc)
	_index, _total[0], _loc = index, sum(m for _o, m in index.values()), loc
	_generatie += 1
	if _total[0] > loc["max"] or len(_index) > loc["fisiere"]:
		_curataIndex()
	return loc


def _pregateste(forteaza=False):
	"""Pe firul pozelor: locul si indexul lui, cand nu sunt inca (sau locul s-a schimbat, ori stickul a fost scos)."""
	if not forteaza and _locBun(_loc):
		if not _loc.get("verifica"):
			return _loc
		if _loc["disc"] and _montat(os.path.realpath(MONTARE)) and os.path.isdir(_loc["dosar"]):
			# stickul e tot acolo: numai poza aceea era stricata (o aduce cere() din nou), indexul ramane
			_loc.pop("verifica", None)
			return _loc
	loc = _alegeLoc()
	if loc["disc"]:
		index = _citesteIndex(loc)
		total = sum(m for _o, m in index.values())
		# un sfert din locul liber (cu tot cu ce tinem deja), dar nu sub MIN_CACHE_DISC: un stick aproape plin ramane al omului
		loc["max"] = min(MAX_CACHE_DISC, (loc.pop("liber") + total) // 4)
		if loc["max"] >= MIN_CACHE_DISC:
			return _schimbaLoc(loc)
		loc = _locTmp()
	return _schimbaLoc(loc)


def _bucla():
	global _fir, _generatie
	while True:
		with _lacat:
			if not _coada:
				_fir = None
				return
			n, (adresa, latime, inaltime, fel) = _coada.popitem(last=True)
		try:
			_pregateste()
			if not cale(adresa, latime, inaltime, fel):
				_faInCache(adresa, latime, inaltime, fel, n)
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
	_scrie(tinta, jpeg)
	return jpeg


def _scrie(tinta, jpeg):
	"""Fara fsync (pe stick ar fi o scriere sincrona la fiecare poster); .tmp + redenumire, deci o poza taiata nu ramane
	cu numele bun nici pe vfat."""
	dosar = os.path.dirname(tinta)
	if not os.path.isdir(dosar):
		os.makedirs(dosar, mode=0o700)
	tmp = tinta + ".tmp"
	with open(tmp, "wb") as f:
		f.write(jpeg)
	os.replace(tmp, tinta)


def _faInCache(adresa, latime, inaltime, fel, n):
	"""Poza in locul ales; daca stickul nu mai primeste (scos, plin, numai citire), locul trece pe /tmp si poza se scrie acolo."""
	loc = _loc
	jpeg = micsoreaza(_citeste(marimeTmdb(adresa, latime, fel)), latime, inaltime, fel)
	try:
		_scrie(_caleFisier(loc, n), jpeg)
	except (IOError, OSError):
		if not loc["disc"]:
			raise
		print("[HdsVodPoze] stickul nu mai primeste posterele: trec pe /tmp")
		loc = _schimbaLoc(_locTmp())
		_scrie(_caleFisier(loc, n), jpeg)
	vechi = _index.get(n)
	_index[n] = [time.time(), len(jpeg)]
	_total[0] += len(jpeg) - (vechi[1] if vechi else 0)
	if _total[0] > loc["max"] or len(_index) > loc["fisiere"]:
		_curataIndex()


def _curataIndex():
	"""Cele mai vechi pana sub 90% din plafon (fisiere si octeti), dupa indexul din memorie: fara sa citeasca tot dosarul."""
	loc = _loc
	if loc is None:
		return
	tinta_octeti, tinta_fisiere = loc["max"] * 9 // 10, loc["fisiere"] * 9 // 10
	for nume, (_ora, marime) in sorted(_index.items(), key=lambda x: x[1][0]):
		if _total[0] <= tinta_octeti and len(_index) <= tinta_fisiere:
			break
		try:
			os.unlink(_caleFisier(loc, nume))
		except OSError:
			pass
		_index.pop(nume, None)
		_total[0] -= marime


def _curata():
	"""Curatenia intreaga a dosarului din /tmp, dupa numarul de fisiere si octeti (cele noi raman); indexul se reface."""
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
	if _locBun(_loc) and not _loc["disc"]:
		_schimbaLoc(_loc)

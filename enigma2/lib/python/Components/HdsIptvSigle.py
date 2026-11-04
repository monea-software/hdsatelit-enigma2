# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Siglele furnizorului, pe un singur fir propriu, fara lucru de retea pe firul TV.

cere(sursa, canale) anticipeaza primele 24 de sigle. cereReferinte(refs) aduce numai
randurile vizibile ale listei (si canalul din bara). Cache separat de piconurile
omului: hds_iptv/sigle, 16 MiB / 256 fisiere. Numele este cel standard, obtinut
din I.refCanal, astfel ca aceeasi sigla apare si in Favorite. Nu pastram URL-uri
in numele fisierelor, in index ori in jurnal. PNG si JPEG, maximum 256 KiB,
512 x 512 si 262144 pixeli; celelalte formate pastreaza pictograma obisnuita.
"""
import hashlib
import json
import os
import re
import struct
import threading
import time
import zlib
from collections import OrderedDict
from itertools import islice
from urllib.parse import unquote

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C

MAX_OCTETI = 256 * 1024
MAX_LATURA = 512
MAX_PIXELI = 262144
MAX_CACHE = 16 * 1024 * 1024
MAX_SIGLE = 256
MAX_ANTICIPATE = 24
MAX_COADA = 64
TERMEN_S = 4
TERMEN_TOTAL_S = 8
VALABIL_S = 7 * 24 * 3600
REINCEARCA_S = 3600
_PNG = b"\x89PNG\r\n\x1a\n"
_NUME = re.compile(r"^[0-9A-Fa-f_]{1,100}$")
_LOCAL = re.compile(r"^http://127[.]0[.]0[.]1:8897/tv/([0-9a-f]{8})/([A-Za-z0-9_.-]{1,64})$")
_lacat = threading.Lock()
_coada = OrderedDict()
_ratate = OrderedDict()
_fir = None
_generatie = 0
_catalog = None                 # numai ultima sursa, fara copii ale adreselor fluxurilor


def dosar():
	return os.path.join(I.DOSAR, "sigle")


def generatie():
	"""Contor citit de UI; workerul nu atinge widgeturi sau temporizatoare enigma2."""
	return _generatie


def nume(ref):
	c = str(ref or "").split(":")[:10]
	if len(c) != 10 or c[0] not in ("4097", "1", "5001", "5002", "5003", "8193", "8739"):
		return ""
	n = "_".join(c).rstrip("_")
	return n if _NUME.match(n) else ""


def cauta(ref):
	"""Numai existenta fisierului local; nici citire de playlist, nici retea."""
	n = nume(ref)
	if n:
		for ext in (".png", ".jpg"):
			cale = os.path.join(dosar(), n + ext)
			if os.path.isfile(cale):
				return cale
	return ""


def _dimensiuni(w, h):
	if not (0 < w <= MAX_LATURA and 0 < h <= MAX_LATURA and w * h <= MAX_PIXELI):
		raise ValueError("dimensiuni")


def _png(date):
	poz, idat, cap, paleta = 8, [], None, False
	sfarsit_idat = False
	while poz + 12 <= len(date):
		lung = struct.unpack(">I", date[poz:poz + 4])[0]
		tip = date[poz + 4:poz + 8]
		sf = poz + 12 + lung
		if sf > len(date):
			raise ValueError("png trunchiat")
		b = date[poz + 8:sf - 4]
		if zlib.crc32(tip + b) & 0xffffffff != struct.unpack(">I", date[sf - 4:sf])[0]:
			raise ValueError("png crc")
		if cap is None:
			if tip != b"IHDR" or lung != 13:
				raise ValueError("png antet")
			w, h, biti, culoare, comp, filtru, interlace = struct.unpack(">IIBBBBB", b)
			_dimensiuni(w, h)
			permise = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
			if biti not in permise.get(culoare, ()) or comp or filtru or interlace not in (0, 1):
				raise ValueError("png format")
			cap = (w, h, biti, culoare)
		elif tip == b"IHDR":
			raise ValueError("png antet repetat")
		elif tip == b"PLTE":
			if idat or not lung or lung % 3 or lung > 768:
				raise ValueError("png paleta")
			paleta = True
		elif tip == b"IDAT":
			if sfarsit_idat:
				raise ValueError("png date")
			idat.append(b)
		elif tip == b"IEND":
			if lung or sf != len(date) or not idat or (cap[3] == 3 and not paleta):
				raise ValueError("png sfarsit")
			w, h, biti, culoare = cap
			canale = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[culoare]
			pasi = ((0, 0, 1, 1),) if not interlace else ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8),
				(2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
			randuri = []
			for x, y, dx, dy in pasi:
				pw, ph = max(0, (w - x + dx - 1) // dx), max(0, (h - y + dy - 1) // dy)
				if pw and ph:
					randuri.extend([(pw * canale * biti + 7) // 8 + 1] * ph)
			maxim = sum(randuri)
			dec = zlib.decompressobj()
			brut = dec.decompress(b"".join(idat), maxim + 1)
			if len(brut) != maxim or not dec.eof or dec.unused_data or dec.unconsumed_tail:
				raise ValueError("png pixeli")
			p = 0
			for rand in randuri:
				if brut[p] > 4:
					raise ValueError("png filtru")
				p += rand
			return ".png"
		elif not (tip[0] & 32) and tip not in (b"PLTE",):
			raise ValueError("png extensie critica")
		if idat and tip != b"IDAT":
			sfarsit_idat = True
		poz = sf
	raise ValueError("png incomplet")


def _jpeg(date):
	"""Citeste segmentele pana la scanare; decoderul nativ primeste doar imagini mici."""
	poz, dim = 2, None
	while poz + 2 <= len(date):
		if date[poz] != 255:
			raise ValueError("jpeg marcaj")
		while poz < len(date) and date[poz] == 255:
			poz += 1
		if poz >= len(date):
			break
		marcaj = date[poz]
		poz += 1
		if marcaj in (0, 0xd8, 0xd9) or 0xd0 <= marcaj <= 0xd7:
			raise ValueError("jpeg ordine")
		if poz + 2 > len(date):
			break
		lung = struct.unpack(">H", date[poz:poz + 2])[0]
		if lung < 2 or poz + lung > len(date):
			break
		if marcaj in (0xc0, 0xc1, 0xc2):
			if dim is not None or lung < 11:
				raise ValueError("jpeg antet")
			biti, h, w, componente = struct.unpack(">BHHB", date[poz + 2:poz + 8])
			_dimensiuni(w, h)
			if biti != 8 or componente not in (1, 3) or lung != 8 + 3 * componente:
				raise ValueError("jpeg format")
			dim = (w, h)
		elif 0xc0 <= marcaj <= 0xcf and marcaj not in (0xc4, 0xc8, 0xcc):
			raise ValueError("jpeg format")
		elif marcaj == 0xda:
			if dim is None or not date.endswith(b"\xff\xd9"):
				raise ValueError("jpeg incomplet")
			return ".jpg"
		poz += lung
	raise ValueError("jpeg incomplet")


def verifica(date):
	"""Extensia reala verificata, sau ValueError; nu ne bazam pe MIME ori extensia URL."""
	if not isinstance(date, bytes) or len(date) > MAX_OCTETI:
		raise ValueError("marime")
	if date.startswith(_PNG):
		return _png(date)
	if date.startswith(b"\xff\xd8"):
		return _jpeg(date)
	raise ValueError("format")


def _citeste(adresa, antete):
	start = time.monotonic()
	with C.deschide(adresa, antete=antete, termen=TERMEN_S) as raspuns:
		lung = raspuns.headers.get("Content-Length")
		if lung and int(lung) > MAX_OCTETI:
			raise ValueError("marime")
		bucati, n = [], 0
		citire = getattr(raspuns, "read1", raspuns.read)
		while True:
			b = citire(min(16384, MAX_OCTETI + 1 - n))
			if time.monotonic() - start > TERMEN_TOTAL_S:
				raise ValueError("termen")
			if not b:
				return b"".join(bucati)
			n += len(b)
			if n > MAX_OCTETI:
				raise ValueError("marime")
			bucati.append(b)


def _curata():
	"""Numai fisierele cache-ului propriu; nu atingem niciun dosar picon al omului."""
	fisiere = []
	for f in os.scandir(dosar()):
		if f.is_file(follow_symlinks=False) and f.name.endswith((".png", ".jpg")) and _NUME.match(f.name[:-4]):
			st = f.stat(follow_symlinks=False)
			fisiere.append((st.st_mtime, st.st_size, f.path))
	fisiere.sort(reverse=True)
	total = 0
	for i, (_ora, marime, cale) in enumerate(fisiere):
		total += marime
		if i >= MAX_SIGLE or total > MAX_CACHE:
			os.unlink(cale)
			try:
				os.unlink(cale[:-4] + ".suma")
			except OSError:
				pass


def _aduce(s, canal):
	global _generatie
	if len(canal) < 5 or not isinstance(canal[4], dict):
		return
	adresa = canal[4].get("logo")
	if not isinstance(adresa, str) or not adresa.lower().startswith(("http://", "https://")):
		return
	ref = I.refCanal(s["id"], canal[0])
	n = nume(ref)
	if not n:
		return
	antete = dict(C.anteteSursa(s), **C.anteteCurate(canal[4].get("antete")))
	suma = hashlib.sha256(json.dumps([adresa, antete], sort_keys=True).encode("utf-8")).hexdigest().encode("ascii")
	veche = cauta(ref)
	cale_suma = os.path.join(dosar(), n + ".suma")
	try:
		with open(cale_suma, "rb") as f:
			if veche and f.read(65) == suma and 0 <= time.time() - os.stat(veche).st_mtime < VALABIL_S:
				return True
	except OSError:
		pass
	date = _citeste(adresa, antete)
	ext = verifica(date)
	os.makedirs(dosar(), mode=0o700, exist_ok=True)
	os.chmod(dosar(), 0o700)
	cale = os.path.join(dosar(), n + ext)
	I._scrie(cale, date, 0o600)
	I._scrie(cale_suma, suma, 0o600)
	if veche and veche != cale:
		try:
			os.unlink(veche)
		except OSError:
			pass
	_curata()
	_generatie += 1
	return True


def _dinDisc(sid, cheie):
	global _catalog
	cale = os.path.join(I.DOSAR, "canale-%s.json" % sid)
	st = os.stat(cale)
	marca = (sid, st.st_mtime_ns, st.st_size)
	if _catalog is None or _catalog[0] != marca:
		s = I.sursa(sid)
		if s is None:
			return None
		# Se retine numai metadatele siglelor, fara URL-urile fluxurilor si fara copii ale playlistului.
		catalog = {}
		for c in I.citesteCanale(sid)[:I.MAX_CANALE]:
			if isinstance(c, list) and len(c) > 4 and isinstance(c[4], dict) and c[4].get("logo"):
				catalog[c[0]] = [c[0], "", "", "", c[4]]
		_catalog = (marca, s, catalog)
	c = _catalog[2].get(cheie)
	return (_catalog[1], c) if c is not None else None


def _bucla():
	global _fir
	while True:
		with _lacat:
			if not _coada:
				_fir = None
				return
			cheie, lucrare = _coada.popitem(last=False)
		reusit = False
		try:
			date = _dinDisc(*lucrare[1:]) if lucrare[0] == "ref" else lucrare[1:]
			if date:
				reusit = bool(_aduce(*date))
		except Exception:
			# Nici URL-uri, nici antete sau exceptii care pot contine parola in jurnal.
			pass
		finally:
			with _lacat:
				if not reusit:
					_ratate[cheie] = time.monotonic()
				while len(_ratate) > 512:
					_ratate.popitem(last=False)


def _pune(cheie, lucrare):
	global _fir
	with _lacat:
		if cheie in _coada:
			if lucrare[0] == "canal":
				_coada[cheie] = lucrare  # o sursa editata repede lasa in coada ultima adresa, nu pe cea veche
			return
		if time.monotonic() - _ratate.get(cheie, -REINCEARCA_S) < REINCEARCA_S:
			return
		if len(_coada) >= MAX_COADA:
			_coada.popitem(last=False)
		_coada[cheie] = lucrare
		if _fir is None:
			_fir = threading.Thread(target=_bucla, name="HdsIptvSigle")
			_fir.daemon = True
			_fir.start()


def cere(s, canale):
	"""Nu asteapta reteaua. Primele sigle sunt aduse pe rand; lista cere apoi viewportul."""
	if not isinstance(s, dict) or not re.match(r"^[0-9a-f]{8}$", str(s.get("id", ""))):
		return
	n = 0
	for c in canale:
		if isinstance(c, (list, tuple)) and len(c) > 4 and isinstance(c[4], dict) and c[4].get("logo"):
			cheie = nume(I.refCanal(s["id"], c[0]))
			with _lacat:
				_ratate.pop(cheie, None)
			_pune(cheie, ("canal", dict(s), list(c)))
			n += 1
			if n >= MAX_ANTICIPATE:
				break


def cereReferinte(refs):
	"""Cel mult 64 de randuri vizibile; playlistul se citeste numai pe worker."""
	for ref in islice(refs, MAX_COADA):
		veche = cauta(ref)
		try:
			if veche and 0 <= time.time() - os.stat(veche).st_mtime < VALABIL_S:
				continue
		except OSError:
			pass
		parti = str(ref or "").split(":", 10)
		if len(parti) < 11:
			continue
		p = _LOCAL.match(unquote(parti[10]).rstrip(":"))
		if p:
			_pune(nume(ref), ("ref", p.group(1), p.group(2)))

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvFullHd: canalele de internet 4K pe receptoarele care redau cel mult 1080p (ZGEMMA H8.2H Plus, Vu+ Solo SE, Zero...).
# Trei bucati, fara nimic din enigma2 (probele de pe PC le folosesc ca atare):
# - placaFullHd(): receptorul reda cel mult 1080p. Semnul: modurile video ale driverului (/proc/stb/video/videomode_choices) au
#   1080 si n-au 2160. Vu+ Duo 4K Lite e scos: lista driverului lui e gresita (Components/HdsPlacaVuplus.py). Fara fisier (emulatorul,
#   o stare stricata): nu, deci purtarea ramane cea de pe receptoarele 4K.
# - filtreazaVariante(): lista HLS principala fara variantele mai mari de 1920x1080 (si fara cadrele I ale lor). Daca toate sunt mai
#   mari ramane cea mai mica; variantele fara RESOLUTION raman. Releul (Components/HdsIptvAdrese._listaHls) o cere numai pe placaFullHd.
# - perecheHd(): acelasi canal al furnizorului fara 4K in nume, din aceeasi grupa (WARNER BROS 1 4k -> WARNER BROS 1, MBC 2 4K ->
#   MBC 2 HD), cel mai bun dupa calitatea din nume: FHD/1080 inaintea lui HD/720, apoi fara semn; SD/576/480 niciodata. Numele cu alte
#   cuvinte (MBC 2 USA, Jawwy MBC 2 HD, MBC 2 -6 HOUR) nu sunt acelasi canal.
# - alegere(): ce face releul (Components/HdsIptvAdrese.inlocuireFullHd) cu un canal cerut pe un receptor Full HD: aduce perechea in locul
#   canalului 4K (referinta, lista si ghidul raman ale canalului ales; fereastra de pe ecran spune pe scurt ce s-a pornit), sau spune ca
#   un canal masurat 4K n-are pereche (mesajul vine repede, nu dupa 30 s de asteptare). Un canal masurat sub 4K („de fapt 1080p”) merge
#   asa cum e.

import os
import re
import unicodedata

LATIME_MAX = 1920
INALTIME_MAX = 1080
LATIME_4K = 3200         # ca in Components/HdsIptv4K.py: 3840x1600 (film lat) e tot 4K
FISIER_MODURI = "proc/stb/video/videomode_choices"
FISIERE_VUMODEL = ("proc/stb/info/vumodel",)
VU_LISTA_GRESITA = ("vuduo4klite", "duo4klite")

_4K = re.compile(r"(?<![a-z0-9])(?:4k|8k|uhd|ultra\s?hd|2160[pi]?|3840[pi]?)(?![a-z0-9])")
_FHD = re.compile(r"(?<![a-z0-9])(?:fhd|full\s?hd|1080[pi]?)(?![a-z0-9])")
_HD = re.compile(r"(?<![a-z0-9])(?:hd|720[pi]?)(?![a-z0-9])")
_SD = re.compile(r"(?<![a-z0-9])(?:sd|576[pi]?|480[pi]?)(?![a-z0-9])")
# semnele de calitate si de format scoase din nume ca sa ramana canalul insusi
_CALITATE = re.compile(r"(?<![a-z0-9])(?:4k|8k|uhd|ultra\s?hd|2160[pi]?|3840[pi]?|fhd|full\s?hd|hd|sd|1080[pi]?|720[pi]?|576[pi]?|"
	r"480[pi]?|hevc|h\.?26[45]|hdr(?:10)?\+?|dolby\s?vision|dv|\d{2,3}\s?fps)(?![a-z0-9])")
_SEMNE = re.compile(r"[^a-z0-9|+]+")      # + ramane: V Sport+ nu e V Sport, Channel 4 +1 nu e Channel 4

_cache = {}


def _cale(radacina, rel):
	return os.path.join(radacina or os.environ.get("HDS_PAZA_RADACINA") or "/", rel)


def _citeste(cale, maxim=4096):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("ascii", "replace").strip().lower()
	except (IOError, OSError, ValueError):
		return ""


def placaFullHd(radacina=None):
	"""True cand receptorul reda cel mult 1080p (vezi capul fisierului). Citit o data."""
	cheie = radacina or ""
	if cheie not in _cache:
		moduri = _citeste(_cale(radacina, FISIER_MODURI)).split()
		vu = " ".join(_citeste(_cale(radacina, f), 64) for f in FISIERE_VUMODEL)
		_cache[cheie] = bool(moduri) and any(m.startswith("1080") for m in moduri) and not any("2160" in m for m in moduri) \
			and vu.strip() not in VU_LISTA_GRESITA
	return _cache[cheie]


def uita():
	"""Uita valorile citite (numai pentru probele de pe PC)"""
	_cache.clear()


# ------------------------------------------------------------------ variantele HLS

_REZ = re.compile(r'RESOLUTION=(\d+)x(\d+)', re.I)


def _rezolutie(rand):
	m = _REZ.search(rand)
	return (int(m.group(1)), int(m.group(2))) if m else None


def _preaMare(rez, latime_max, inaltime_max):
	return rez is not None and (rez[0] > latime_max or rez[1] > inaltime_max)


def filtreazaVariante(text, latime_max=LATIME_MAX, inaltime_max=INALTIME_MAX):
	"""Lista HLS principala fara variantele mai mari de latime_max x inaltime_max (vezi capul fisierului). -> textul (acelasi cand nu e
	nimic de scos sau nu e o lista principala)."""
	if "#EXT-X-STREAM-INF" not in text:
		return text
	randuri = text.splitlines()
	# variantele: (indicele randului #EXT-X-STREAM-INF, indicele adresei, rezolutia)
	variante = []
	i = 0
	while i < len(randuri):
		if randuri[i].startswith("#EXT-X-STREAM-INF"):
			j = i + 1
			while j < len(randuri) and (not randuri[j].strip() or randuri[j].startswith("#")):
				j += 1
			variante.append((i, j if j < len(randuri) else None, _rezolutie(randuri[i])))
			i = j + 1
			continue
		i += 1
	mari = [v for v in variante if _preaMare(v[2], latime_max, inaltime_max)]
	if not mari:
		return text
	if len(mari) == len(variante):
		# toate sunt mai mari: ramane cea mai mica (mai bine ceva decat o lista goala)
		pastrata = min(mari, key=lambda v: v[2][0] * v[2][1])
		mari = [v for v in mari if v is not pastrata]
	scoase = set()
	for a, b, _r in mari:
		scoase.add(a)
		if b is not None:
			scoase.add(b)
	rez = []
	for k, rand in enumerate(randuri):
		if k in scoase:
			continue
		if rand.startswith("#EXT-X-I-FRAME-STREAM-INF") and _preaMare(_rezolutie(rand), latime_max, inaltime_max):
			continue
		rez.append(rand)
	return "\n".join(rez) + ("\n" if text.endswith("\n") else "")


# ------------------------------------------------------------------ acelasi canal in HD

def _ascii(text):
	t = (text or "")[:256]
	if not t.isascii():
		# NFKD face din semnele mici ale unor liste (ᴴᴰ, ᵁᴴᴰ, ⁴ᴷ) literele lor
		t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
	return t.casefold()


def este4K(nume):
	"""Numele spune 4K, UHD, 2160p..."""
	return bool(_4K.search(_ascii(nume)))


def cheieCanal(nume):
	"""Numele fara semnele de calitate si fara semne: "|AR| WARNER BROS 1 4k" si "|AR| WARNER BROS 1" dau aceeasi cheie."""
	t = _CALITATE.sub(" ", _ascii(nume))
	return _SEMNE.sub("", t)


def calitate(nume):
	"""3 FHD/1080, 2 HD/720, 1 fara semn, 0 SD/576/480, -1 4K"""
	t = _ascii(nume)
	if _4K.search(t):
		return -1
	if _FHD.search(t):
		return 3
	if _HD.search(t):
		return 2
	if _SD.search(t):
		return 0
	return 1


def perecheHd(nume, grupa, canale, masurate=None, numai_masurate=False):
	"""Cheia aceluiasi canal fara 4K din aceeasi grupa, sau None. canale: [(cheie, nume, grupa), ...] (in ordinea listei);
	masurate: {cheie: latime} din cautarea canalelor 4K (o pereche masurata 4K nu e buna); numai_masurate: numai o pereche masurata sub
	4K (numele nu ajunge: pe .129 |AR| WARNER BROS 1 trimite tot 3840x2160, ca |AR| WARNER BROS 1 4k)."""
	if not este4K(nume):
		return None
	baza = cheieCanal(nume)
	if not baza:
		return None
	cea_buna, rang = None, 0
	for c in canale:
		if len(c) < 3 or c[2] != grupa or not c[1]:
			continue
		r = calitate(c[1])
		if r <= rang or cheieCanal(c[1]) != baza:
			continue
		w = (masurate or {}).get(c[0]) or 0
		if w >= LATIME_4K or (numai_masurate and not w):
			continue
		cea_buna, rang = c[0], r
	return cea_buna


def alegere(nume, grupa, canale, latime=None, masurate=None):
	"""Ce aduce releul pentru un canal cerut pe un receptor Full HD. latime: cea masurata de cautarea canalelor 4K (Components/HdsIptv4K.py),
	sau None; masurate: {cheie: latime} ale canalelor si perechilor masurate. -> ("pereche", cheie) cand canalul e 4K (masurat, sau cu 4K in
	nume si nemasurat) si furnizorul are acelasi canal fara 4K in aceeasi grupa, MASURAT sub 4K; ("4k", None) cand e masurat 4K si n-are o
	astfel de pereche; (None, None) altfel (canalul cerut, ca inainte)."""
	if latime and latime < LATIME_4K:
		return None, None      # masurat: de fapt 1080p sau mai putin, merge asa cum e
	masurat_4k = bool(latime and latime >= LATIME_4K)
	if not masurat_4k and not este4K(nume):
		return None, None
	p = perecheHd(nume, grupa, canale, masurate, numai_masurate=True)
	if p:
		return "pereche", p
	return ("4k", None) if masurat_4k else (None, None)


def perechiDeMasurat(intrari):
	"""Pentru cautarea canalelor 4K pe un receptor Full HD: intrarile (cheie, nume, grupa, ...) fara 4K in nume care pot fi perechea unui
	canal cu 4K in nume din aceeasi grupa (aceeasi cheieCanal, nu SD). -> lista lor, in ordinea primita, fiecare o data."""
	baze = set((x[2], cheieCanal(x[1])) for x in intrari if len(x) > 2 and x[1] and este4K(x[1]))
	rez, vazute = [], set()
	for x in intrari:
		if len(x) < 3 or not x[1] or x[0] in vazute or calitate(x[1]) < 1:
			continue
		if (x[2], cheieCanal(x[1])) in baze:
			vazute.add(x[0])
			rez.append(x)
	return rez

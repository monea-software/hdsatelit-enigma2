# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPlatforma.py: pe ce placa ruleaza imaginea, pentru purtarea care difera intre primul Amiko Viper 4K (V10, masina
# viper4k) si Viper 4K V20, V30, V40 (masinile Dinobot u57 si u571). Singura sursa a intrebarii "e V10?" (0.6.3).
#
# De ce: V10 are alt pachet de drivere (Amiko, nu Dinobot), alt demon al platformei (libreader in loc de showiframe),
# alta asezare a partitiilor (nucleul in linuxkernel1, sistemul in subdosarul linuxrootfs1 al partitiei userdata),
# luminozitatea afisajului in /proc/stb/fp/oled_brightness si alta recuperare (arhiva producatorului). Ce se schimba
# pe V10: memoria decodorului (Components/HdsMemorieDriver.py)
# nu reporneste nimic, actualizarea din meniu accepta sistemul din subdosar, afisajul, VPN-ul, recuperarea si numele.
#
# Semnul: machinebuild=viper4k in regulile modelului (/etc/hdsatelit-model, scrise la construirea imaginii) sau
# "viper4k" in /proc/stb/info/boxtype (driverul hi-dvb.ko al lui V10; pe V20, V30, V40 firedtv.ko spune u57). Cand
# niciunul nu se poate citi (emulatorul de pe PC, o stare stricata) raspunsul e "nu e V10": Viper 4K V20 se poarta
# exact ca inainte. Nu se folosesc SystemInfo["machinebuild"] sau /etc/hostname: ele cad pe "viper4k" si pe V20.
#
# Valorile nu se schimba cat merge receptorul, deci se citesc o data (uita() e pentru probele de pe PC). Fisierul nu
# importa nimic din enigma2: probele de pe PC il folosesc direct, cu `radacina` (un receptor fals).

import os

MASINA_V10 = "viper4k"
# familia libreader (acelasi SDK HiSilicon al producatorului, demonul libreader, driverele hi_*): V10 si Octagon
MASINI_LIBREADER = ("viper4k", "sf8008", "sf8008m")
NUME_V10 = "Amiko Viper 4K V10"
FISIER_REGULI = "etc/hdsatelit-model"
FISIER_BOXTYPE = "proc/stb/info/boxtype"

_cache = {}


def _cale(radacina, rel):
	return os.path.join(radacina or os.environ.get("HDS_PAZA_RADACINA") or "/", rel)


def _primulRand(cale, maxim=16384):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError, ValueError):
		return ""


def masinaDinReguli(radacina=None):
	"""machinebuild= din regulile modelului ("viper4kv20", "viper4k"); "" fara fisier sau fara cheie"""
	for rand in _primulRand(_cale(radacina, FISIER_REGULI)).splitlines():
		rand = rand.strip()
		if rand.startswith("#") or "=" not in rand:
			continue
		k, _s, v = rand.partition("=")
		if k.strip() == "machinebuild":
			return v.strip()
	return ""


def tipPlaca(radacina=None):
	"""primul rand din /proc/stb/info/boxtype (u57, viper4k), sau """""
	text = _primulRand(_cale(radacina, FISIER_BOXTYPE), 256)
	return text.splitlines()[0].strip() if text.strip() else ""


def esteV10(radacina=None):
	"""True pe primul Amiko Viper 4K (V10): regulile imaginii sau driverul spun viper4k"""
	cheie = radacina or ""
	if cheie not in _cache:
		_cache[cheie] = masinaDinReguli(radacina) == MASINA_V10 or tipPlaca(radacina) == MASINA_V10
	return _cache[cheie]


def familiaLibreader(radacina=None):
	"""True pe placile familiei libreader (primul Amiko Viper 4K V10, Octagon SF8008 si SF8008 MINI): regulile
	imaginii (machinebuild=) sau driverul (/proc/stb/info/boxtype) spun una din MASINI_LIBREADER"""
	cheie = "libreader:" + (radacina or "")
	if cheie not in _cache:
		_cache[cheie] = masinaDinReguli(radacina) in MASINI_LIBREADER or tipPlaca(radacina) in MASINI_LIBREADER
	return _cache[cheie]


def cuMemorieEs(radacina=None):
	"""True cand demonul platformei e showiframe Dinobot, care mapeaza memoria de 34611200 o prin care driverul video
	primeste pozele si filmele (lib/dvb/hdspazavideo.h, Components/HdsMemorieDriver.py). Pe V10 nu exista: acolo
	memoria decodorului nu reporneste nimic (si enigma2 nu e construit cu paza, configure.ac)."""
	return not esteV10(radacina)


def uita():
	"""Uita valorile citite (numai pentru probele de pe PC)"""
	_cache.clear()

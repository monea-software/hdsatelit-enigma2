# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEpgDatLimbi.py: in ce limbi trimite fiecare canal ghidul, citit din epg.dat (numai citire), pentru asistenta.
#
# De ce: un om vedea ghidul unor canale numai in maghiara (asistenta 615583, 12.11.2026). Nucleul alege la fiecare citire,
# din descrierile tinute minte, limba ghidului, apoi engleza, apoi prima venita (lib/service/event.cpp), deci raspunsul
# e in cache: ce coduri ISO 639 au descrierile scurte (0x4D, titlul) si lungi (0x4E) ale fiecarei emisiuni. Fisierul e
# binar (7-50 MB): asistenta nu-l poate trimite ca text, deci op „citeste” pe /home/root/epg.dat da acest rezumat
# (Components/HdsAsistentaBroker.py, _citesteEpgDat), intr-un proces separat (python3 -c ..., cu termen), ca interfata
# sa nu astepte. Acelasi format ca unealta de pe PC unelte/stb/limbi_epg_dat.py.
#
# Formatul (lib/dvb/epgcache.cpp, eEPGCache::save, ENIGMA_EPG_V7, ordinea octetilor a receptorului, little endian pe ARM
# si mips el): 0x98765432, „ENIGMA_EPG_V7”, numarul de servicii; pentru fiecare: sid, onid, tsid (int), numarul de
# emisiuni; pentru fiecare emisiune: tip (1 octet), lungime (1 octet), datele (10 octeti antet EIT, apoi CRC-urile
# descrierilor, cate 4); apoi descrierile: numarul, si pentru fiecare: CRC (4), cate emisiuni o folosesc (4), descrierea
# (tag, lungime, continut).
#
# Iesirea nu are titluri de emisiuni, numai codurile limbilor si numerele. Fisierul se deschide numai pentru citire
# (mmap), nu se scrie nimic. Nu importa nimic din enigma2 (probele de pe PC il folosesc la fel).
#
# Memoria (12.11.2026: un fisier de 64 MB, cazul cel mai rau, tinea 490 MB cu emisiunile in memorie): trei treceri prin
# fisierul deschis cu mmap: (1) se sar emisiunile, ca sa se afle unde incep descrierile; (2) din descrieri se tine numai
# CRC -> limba (un numar mic); (3) emisiunile se numara pe loc, fara sa fie tinute. Procesul isi pune singur un plafon de
# memorie (PLAFON_MEMORIE, RLIMIT_AS) si se ruleaza cu prioritate mica, ca un fisier urias sa dea un mesaj, nu sa
# goleasca memoria receptorului.

import collections
import errno
import mmap
import os
import struct
import sys
import time

CALE = "/home/root/epg.dat"
MAGIC = 0x98765432
VERSIUNE = b"ENIGMA_EPG_V7"
MAX_CANALE = 4000          # randuri in raspuns (raspunsul asistentei are cel mult 1 MB)
PLAFON_MEMORIE = 320 * 1024 * 1024   # spatiul de adrese al procesului (cu fisierul mapat cu tot)

_SERVICIU = struct.Struct("<iiii")
_DESCRIERE = struct.Struct("<Ii")


class EpgDatStricat(Exception):
	pass


def numara(d):
	"""d: octetii (bytes sau mmap). -> (canale {(sid, onid, tsid): (emisiuni, Counter titlu, Counter descriere lunga)},
	numarul descrierilor cu limba). Cheile Counter-elor: limbile (ISO 639) ale unei emisiuni, unite cu spatiu, sau „-”.
	EpgDatStricat la un fisier care nu e epg.dat sau e taiat."""
	try:
		magic, = struct.unpack_from("<I", d, 0)
		if magic != MAGIC:
			raise EpgDatStricat("nu e un epg.dat (semnul %08x)" % magic)
		if bytes(d[4:17]) != VERSIUNE:
			raise EpgDatStricat("versiune necunoscuta a fisierului")
		marime = len(d)
		n, = struct.unpack_from("<i", d, 17)
		p = 21
		# (1) unde incepe fiecare canal si unde incep descrierile
		canale = []
		for _i in range(n):
			sid, onid, tsid, cate = _SERVICIU.unpack_from(d, p)
			p += 16
			canale.append(((sid & 0xFFFF, onid & 0xFFFF, tsid & 0xFFFF), p, cate))
			for _j in range(cate):
				p += 2 + d[p + 1]
		if p > marime:
			raise EpgDatStricat("fisier taiat")
		# (2) CRC -> cod: 2 * indexul limbii (+1 la descrierea lunga)
		n, = struct.unpack_from("<i", d, p)
		p += 4
		limbi = []
		index = {}
		coduri = {}
		for _i in range(n):
			crc, _folosiri = _DESCRIERE.unpack_from(d, p)
			p += 8
			tag = d[p]
			lung = d[p + 1] + 2
			if p + lung > marime:
				raise EpgDatStricat("fisier taiat")
			if lung >= 6 and tag in (0x4D, 0x4E):
				limba = bytes(d[p + 2:p + 5] if tag == 0x4D else d[p + 3:p + 6])
				i = index.get(limba)
				if i is None:
					i = index[limba] = len(limbi)
					limbi.append(limba.decode("latin-1"))
				coduri[crc] = 2 * i + (tag == 0x4E)
			p += lung
		# (3) emisiunile, numarate pe loc
		rezultat = {}
		for cheie, p, cate in canale:
			scurte = collections.Counter()
			lungi = collections.Counter()
			for _j in range(cate):
				lung = d[p + 1]
				k = (lung - 10) // 4
				fs = fl = 0
				if k > 0:
					for crc in struct.unpack_from("<%dI" % k, d, p + 12):
						c = coduri.get(crc)
						if c is not None:
							if c & 1:
								fl |= 1 << (c >> 1)
							else:
								fs |= 1 << (c >> 1)
				scurte[fs] += 1
				lungi[fl] += 1
				p += 2 + lung
			rezultat[cheie] = (cate, _cuNume(scurte, limbi), _cuNume(lungi, limbi))
		return rezultat, len(coduri)
	except (struct.error, IndexError):
		raise EpgDatStricat("fisier taiat sau stricat")


def _cuNume(numere, limbi):
	"""Counter {masca limbilor: emisiuni} -> Counter {„hun ron”: emisiuni}."""
	rez = collections.Counter()
	for masca, cate in numere.items():
		nume = " ".join(sorted(limbi[i] for i in range(len(limbi)) if masca >> i & 1)) or "-"
		rez[nume] += cate
	return rez


def rezumat(canale, descrieri, marime=None, scris_la=None):
	"""Textul pentru asistenta: un rand pe canal cu emisiuni (sid:tsid:onid in hex, ca in lamedb), limbile titlului si ale
	descrierii lungi cu numarul emisiunilor; canalele fara emisiuni numai numarate; apoi totalul."""
	randuri = []
	cap = "epg.dat: %d canale, %d descrieri cu limba" % (len(canale), descrieri)
	if marime is not None:
		cap += ", %d octeti" % marime
	if scris_la is not None:
		cap += ", scris la %s UTC" % time.strftime("%Y-%m-%d %H:%M", time.gmtime(scris_la))
	randuri.append(cap)
	randuri.append("(canalul: sid:tsid:onid in hex, ca in lamedb; fisierul se scrie la oprire si la salvarea ghidului, ce a venit de atunci e numai in memorie)")
	total_scurte = collections.Counter()
	total_lungi = collections.Counter()
	goale = sum(1 for v in canale.values() if not v[0])
	cu_emisiuni = sorted((k, v) for k, v in canale.items() if v[0])
	for numar, ((sid, onid, tsid), (cate, scurte, lungi)) in enumerate(cu_emisiuni):
		total_scurte.update(scurte)
		total_lungi.update(lungi)
		if numar < MAX_CANALE:
			randuri.append("%04x:%04x:%04x: %d emisiuni; titlul: %s; descrierea lunga: %s" % (sid, tsid, onid,
				cate, _numere(scurte), _numere(lungi)))
	if len(cu_emisiuni) > MAX_CANALE:
		randuri.append("... inca %d canale (se arata primele %d)" % (len(cu_emisiuni) - MAX_CANALE, MAX_CANALE))
	if goale:
		randuri.append("%d canale fara nicio emisiune (nu se arata)" % goale)
	randuri.append("toate canalele: titlul: %s; descrierea lunga: %s" % (_numere(total_scurte), _numere(total_lungi)))
	return "\n".join(randuri)


def _numere(c):
	return ", ".join("%s x%d" % kv for kv in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))) or "-"


def rezumatFisier(cale):
	"""Textul pentru o cale; fisierul gol, stricat sau prea mare pentru memorie da un rand care spune asta."""
	with open(cale, "rb") as f:
		st = os.fstat(f.fileno())
		if st.st_size == 0:
			return "epg.dat e gol (0 octeti)"
		try:
			harta = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
		except OSError as e:
			if e.errno == errno.ENOMEM:
				return "epg.dat e prea mare pentru memoria lasata acestei citiri (%d octeti)" % st.st_size
			raise
		with harta as d:
			try:
				canale, descrieri = numara(d)
			except EpgDatStricat as e:
				return "epg.dat nu se poate citi: %s (%d octeti)" % (e, st.st_size)
			except MemoryError:
				return "epg.dat e prea mare pentru memoria lasata acestei citiri (%d octeti)" % st.st_size
	return rezumat(canale, descrieri, st.st_size, st.st_mtime)


def _plafon():
	"""Pe receptor (Linux): spatiul de adrese al procesului plafonat; pe PC, fara."""
	try:
		import resource
		resource.setrlimit(resource.RLIMIT_AS, (PLAFON_MEMORIE, PLAFON_MEMORIE))
	except Exception:
		pass


def main(argv):
	cale = argv[0] if argv else CALE
	_plafon()
	try:
		sys.stdout.write(rezumatFisier(cale) + "\n")
	except OSError as e:
		sys.stdout.write("epg.dat nu se poate deschide: %s\n" % type(e).__name__)
		return 1
	except MemoryError:
		sys.stdout.write("epg.dat e prea mare pentru memoria lasata acestei citiri\n")
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))

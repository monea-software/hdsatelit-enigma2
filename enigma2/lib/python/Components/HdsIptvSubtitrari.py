# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvSubtitrari: pistele WebVTT dintr-un canal HLS. Demuxerul HLS din playerul de acum nu le deschide, deci le citeste un fir de aici,
# prin releu (Components/HdsIptvAdrese.py), numai pe cea aleasa de om, iar replicile merg in player ca la un fisier de subtitrari
# (setExternalSubtitles / setExternalSubtitleCues): apar in meniul normal de subtitrari si trec prin traducerea existenta.
#
# Timpul: o replica are timpul din fisierul ei, legat de ceasul imaginii prin X-TIMESTAMP-MAP; pozitia playerului incepe de la primul segment
# video, al carui prim PTS il afla releul.
#
# Partea de sus nu cere enigma2: se probeaza pe PC.

import re
import threading
import time

from Components import HdsIptvSurse as I

MAX_OCTETI_LISTA = 1024 * 1024
MAX_OCTETI_SEGMENT = 256 * 1024
MAX_REPLICI = 5000
INAINTE_MS = 60000       # cat se aduce inaintea imaginii, la un film
PE_TURA = 8              # segmente pe tura, ca firul sa nu tina releul ocupat
PTS_CERC = 1 << 33
TIP_WEBVTT = 7           # stWebVTT din lib/service/servicemp3.h

_ATRIBUT = re.compile(r'([A-Z0-9\-]+)=("[^"]*"|[^,]*)')
_HARTA = re.compile(r"X-TIMESTAMP-MAP=([^\r\n]+)")
_MPEGTS = re.compile(r"MPEGTS:(\d+)")
_LOCAL = re.compile(r"LOCAL:(\d+):(\d+):(\d+)[.,](\d+)")


def pisteDinLista(text):
	"""Pistele de subtitrare din lista principala HLS: [{"nume", "limba", "uri"}]."""
	rez = []
	for rand in text.splitlines():
		if not rand.startswith("#EXT-X-MEDIA:"):
			continue
		a = dict((m.group(1), m.group(2).strip('"')) for m in _ATRIBUT.finditer(rand[13:]))
		if a.get("TYPE") == "SUBTITLES" and a.get("URI"):
			rez.append({"nume": a.get("NAME") or a.get("LANGUAGE") or "", "limba": (a.get("LANGUAGE") or "und").lower(), "uri": a["URI"]})
	return rez


def citesteLista(text):
	"""Lista unei piste: (numarul primului segment, [(durata in secunde, adresa)], lista e intreaga)."""
	secventa, segmente, durata = 0, [], 0.0
	for rand in text.splitlines():
		rand = rand.strip()
		if rand.startswith("#EXT-X-MEDIA-SEQUENCE:"):
			try:
				secventa = int(rand[22:])
			except ValueError:
				pass
		elif rand.startswith("#EXTINF:"):
			try:
				durata = float(rand[8:].split(",", 1)[0])
			except ValueError:
				durata = 0.0
		elif rand and not rand.startswith("#"):
			segmente.append((durata, rand))
	return secventa, segmente, "#EXT-X-ENDLIST" in text


def decalajMs(text, pts0):
	"""Cat se aduna la timpul din fisier ca sa ajunga pe pozitia playerului. Fara harta sau fara PTS-ul imaginii: nimic."""
	m = _HARTA.search(text)
	if not m or pts0 is None:
		return 0
	ts = _MPEGTS.search(m.group(1))
	loc = _LOCAL.search(m.group(1))
	if not ts:
		return 0
	local = 0
	if loc:
		o, mn, s, ms = loc.groups()
		local = (int(o) * 3600 + int(mn) * 60 + int(s)) * 1000 + int(ms[:3].ljust(3, "0"))
	dif = (int(ts.group(1)) - pts0) % PTS_CERC
	if dif > PTS_CERC // 2:
		dif -= PTS_CERC
	return dif // 90 - local


def repliciSegment(text, pts0):
	"""Replicile unui segment, pe pozitia playerului: [(inceput_ms, sfarsit_ms, text, sus)]."""
	from Components import HdsSubtitrariFilm as F
	dec = decalajMs(text, pts0)
	rez = []
	for a, b, t, sus in F.pentruNucleu(F.citesteVtt(text)):
		if b + dec > 0:
			rez.append((max(0, a + dec), b + dec, t, sus))
	return rez


def _aduce(uri, maxim):
	"""Numai prin releu: adresa adevarata nu ajunge aici."""
	from urllib.request import ProxyHandler, Request, build_opener
	o = build_opener(ProxyHandler({}))
	with o.open(Request("http://127.0.0.1:%d%s" % (I.PORT, uri)), timeout=8) as f:
		return f.read(maxim).decode("utf-8", "replace")


class Pista(object):
	"""O pista: ce s-a adus din ea si replicile ei."""

	def __init__(self, uri, aduce=None):
		self.uri = uri
		self.aduce = aduce or _aduce
		self.vazute = set()
		self.replici = {}
		self.schimbat = False
		self.pas_s = 4.0

	def tura(self, pts0, pozitie_ms=None):
		"""Citeste lista si segmentele noi, cate PE_TURA. -> True daca mai sunt de adus acum."""
		secventa, segmente, intreaga = citesteLista(self.aduce(self.uri, MAX_OCTETI_LISTA))
		if segmente:
			self.pas_s = max(2.0, min(10.0, segmente[-1][0] or 4.0))
		adusi = 0
		timp = 0.0
		for i, (durata, adresa) in enumerate(segmente):
			nr = secventa + i
			inceput_ms = timp * 1000
			timp += durata
			if nr in self.vazute:
				continue
			# la un film se aduce numai ce urmeaza in curand; la un flux viu tot ce e in lista
			if intreaga and pozitie_ms is not None and inceput_ms > pozitie_ms + INAINTE_MS:
				break
			if adusi >= PE_TURA:
				return True
			adusi += 1
			self.vazute.add(nr)
			for r in repliciSegment(self.aduce(adresa, MAX_OCTETI_SEGMENT), pts0):
				self.replici[(r[0], r[2])] = r
				self.schimbat = True
		if len(self.replici) > MAX_REPLICI:
			for k in sorted(self.replici)[:len(self.replici) - MAX_REPLICI]:
				del self.replici[k]
		return False

	def lista(self):
		self.schimbat = False
		return [self.replici[k] for k in sorted(self.replici)]


class Urmaritor(threading.Thread):
	"""Firul care aduce pista aleasa. Ce scrie firul enigma2: ales (indexul pistei sau None), pts0, pozitie_ms. Replicile le ia tot el, cu noi()."""

	def __init__(self, piste, aduce=None):
		threading.Thread.__init__(self, name="HdsIptvSubtitrari")
		self.daemon = True
		self.piste = [Pista(p["uri"], aduce) for p in piste]
		self.ales = None
		self.pts0 = None
		self.pozitie_ms = None
		self.oprit = threading.Event()

	def opreste(self):
		self.oprit.set()

	def noi(self):
		"""(index, replici) cand pista aleasa are replici noi, altfel None."""
		i = self.ales
		if i is None or not 0 <= i < len(self.piste) or not self.piste[i].schimbat:
			return None
		return i, self.piste[i].lista()

	def run(self):
		while not self.oprit.is_set():
			i = self.ales
			asteapta = 1.0
			if i is not None and 0 <= i < len(self.piste):
				p = self.piste[i]
				try:
					if not p.tura(self.pts0, self.pozitie_ms):
						asteapta = p.pas_s
					else:
						asteapta = 0.2
				except Exception as e:
					# numai felul erorii
					print("[HdsIptvSubtitrari] %s" % type(e).__name__)
					asteapta = 5.0
			self.oprit.wait(asteapta)

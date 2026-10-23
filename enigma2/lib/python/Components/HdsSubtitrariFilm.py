# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSubtitrariFilm.py: subtitrarile din fisierele de langa film (srt, sub, ass/ssa, vtt, smi, txt, mpl).
#
# Ce face:
# - gaseste fisierele: in dosarul filmului si in subdosarele Subs, Subtitles, Subtitrari, tot ce incepe cu numele
#   filmului fara extensie (film.srt, film.ro.srt, film_en.forced.srt, Film.SRT); intr-un subdosar al unui dosar cu un
#   singur film, si fisierele cu alt nume (Subs/2_English.srt); cel mult MAX_FISIERE fisiere, MAX_OCTETI_TEXT pe fisier;
# - limba din nume (ultimul cuvant cu limba: ro, rum, ron, romanian, Romana; forced si sdh/hi/cc tinute separat), altfel
#   ghicita din text (ă ș ț = romana);
# - codarea: BOM (UTF-8, UTF-16, UTF-32), apoi UTF-8 valid, apoi „Codarea implicita” (Windows-1250 din oficiu: pentru
#   literele romanesti CP1250, ISO-8859-2 si ISO-8859-16 au aceiasi octeti), cu un detector pentru ghilimelele din
#   ISO-8859-16 („ si ” la 0xA5 si 0xB5); s si t cu sedila devin ș ț cu virgula la textul romanesc (setarea
#   hds_film_virgula); multe semne de inlocuire = codarea pare gresita;
# - formatele, recunoscute dupa continut (nu dupa extensie): SubRip, WebVTT, MicroDVD (in cadre: fps din film, din
#   primul rand {1}{1}23.976 sau ales de om), SubViewer 1 si 2, MPL2, TMPlayer, SAMI (fiecare limba din fisier apare
#   separat), SSA/ASS simplu (textul replicilor, fara stil; {\an7}-{\an9} si stilurile cu aliniere sus = replica sus);
# - replicile ajung in servicemp3 (iSubtitleOutput.setExternalSubtitles / setExternalSubtitleCues, lib/service/servicemp3.cpp)
#   si se arata de widgetul subtitrarilor cu „Aspectul subtitrărilor”; fisierele apar in lista de la tasta SUB dupa
#   pistele din container, cu numerele 100, 101, ...; schimbarea subtitrarii, a codarii sau a fps-ului nu atinge filmul;
# - tine minte pe film (dupa numele fisierului filmului si marimea lui, deci si dupa mutarea in alt dosar): subtitrarea
#   aleasa (sau „fara”), intarzierea, codarea, fps-ul si fisierele adaugate de mana, in CALE_MEMORIE (scris atomic,
#   stricat sau prea mare = ignorat, cel mult MAX_FILME filme, cele mai vechi pleaca), scris la cel mult o data in cateva
#   secunde (eMMC).
#
# FIRELE: cautarea si citirea fisierelor ruleaza pe un fir (un NAS poate raspunde greu); firul nu atinge serviciul. Pe
# firul enigma2, un eTimer ia rezultatele si le da serviciului, cate un fisier pe bataie. Alegerea automata a subtitrarii
# (Components/HdsPisteLimbi.py, aplicaSubtitrare) asteapta lista fisierelor cel mult TIMP_CAUTARE_S.
#
# PARTEA DE SUS A FISIERULUI E CURATA (nu cere enigma): citirea, codarea, gasirea si memoria se probeaza pe PC
# (test_subtitrari_film.py). Ce atinge serviciul, ecranele si setarile
# sta dupa linia „legatura cu enigma2”, cu importuri tarzii.

from __future__ import absolute_import

import codecs
import json
import os
import re
import threading
import time


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


# ------------------------------------------------------------------ tipurile, aceleasi numere ca subtype_t (servicemp3.h)
TIP_NECUNOSCUT, TIP_TEXT, TIP_SSA, TIP_ASS, TIP_SRT, TIP_VOB, TIP_PGS, TIP_VTT, TIP_MICRODVD, TIP_SUBVIEWER, \
	TIP_MPL2, TIP_TMPLAYER, TIP_SAMI = range(13)

# eticheta din lista: sursa, nu forma interna (textul din container e „Text”, un fisier are numele formatului)
ETICHETE = {
	TIP_TEXT: u"Text", TIP_SSA: u"SSA", TIP_ASS: u"ASS", TIP_SRT: u"SRT", TIP_VOB: u"VobSub", TIP_PGS: u"PGS",
	TIP_VTT: u"VTT", TIP_MICRODVD: u"SUB", TIP_SUBVIEWER: u"SUB", TIP_MPL2: u"MPL2", TIP_TMPLAYER: u"TMPlayer",
	TIP_SAMI: u"SAMI",
}
TIPURI_TEXT = (TIP_SRT, TIP_VTT, TIP_MICRODVD, TIP_SUBVIEWER, TIP_MPL2, TIP_TMPLAYER, TIP_SAMI, TIP_SSA, TIP_ASS)

INDEX_FISIER = 100          # numarul primului fisier in lista serviciului (pistele din container: 0, 1, 2, ...)
FLAG_FORCED = 1             # numai replicile in alta limba si inscriptiile
FLAG_SURZI = 2              # pentru surzi (sunete, nume)

EXTENSII = (".srt", ".sub", ".ass", ".ssa", ".vtt", ".smi", ".sami", ".txt", ".mpl", ".idx", ".sup")
TIPURI_IMAGINE = (TIP_VOB, TIP_PGS)
MAX_OCTETI_IDX = 2 * 1024 * 1024        # antetul si timpii unui .idx (text)
MAX_SETURI_PGS = 100000
EXTENSII_FILM = (".mkv", ".mp4", ".m4v", ".mov", ".avi", ".divx", ".mpg", ".mpeg", ".vob", ".dat")
SUBDOSARE = ("subs", "sub", "subtitles", "subtitle", "subtitrari", u"subtitrări")
SEPARATORI_NUME = (".", "_", "-", " [", " (")

MAX_FISIERE = 30
MAX_OCTETI_TEXT = 1536 * 1024       # ~20000 de replici; unul mai mare tine firul (si GIL-ul) secunde pe receptor
MAX_REPLICI = 200000
MAX_TEXT_REPLICA = 1000
OCTETI_PROBA = 64 * 1024     # cat se citeste pentru recunoasterea formatului, a codarii si a limbii
OCTETI_PREVIZUALIZARE = 16 * 1024   # inceputul tinut in memorie pentru previzualizarea codarii (fara disc pe firul enigma2)
TIMP_CAUTARE_S = 4.0         # cat asteapta alegerea automata lista fisierelor
INTARZIERE_MAX_MS = 600000   # +/- 10 minute
DURATA_FARA_SFARSIT_MS = 5000

CALE_MEMORIE = "/etc/enigma2/hdsatelit/subtitrari-filme.json"
MAX_FILME = 500
MAX_OCTETI_MEMORIE = 512 * 1024
MAX_ADAUGATE = 10
OPRIT = "oprit"

# ------------------------------------------------------------------ codarile

CODARE_AUTO = "auto"
# alegerile din tasta SUB si din web (codurile sunt nume de codecuri Python, toate in imagine: python3-codecs)
CODARI = (
	(CODARE_AUTO, N_("Automat")),
	("utf-8", "UTF-8"),
	("cp1250", N_("Europa Centrală (Windows-1250)")),
	("iso8859_16", N_("Europa de Sud-Est (ISO-8859-16)")),
	("iso8859_15", N_("Europa de Vest (ISO-8859-15)")),
	("cp1251", N_("Chirilic (Windows-1251)")),
	("cp1253", N_("Grec (Windows-1253)")),
	("cp1254", N_("Turc (Windows-1254)")),
)
# „Codarea implicită”: pentru fisierele care nu sunt UTF-8 si pentru pistele din MKV care nu sunt UTF-8 (acolo prin
# GST_SUBTITLE_ENCODING, pus de servicemp3 la pornirea filmului)
CODARI_IMPLICITE = (
	("cp1250", N_("Europa Centrală (Windows-1250)")),
	("iso8859_15", N_("Europa de Vest (ISO-8859-15)")),
	("cp1251", N_("Chirilic (Windows-1251)")),
	("cp1253", N_("Grec (Windows-1253)")),
	("cp1254", N_("Turc (Windows-1254)")),
)
_NUME_CODARE = dict(CODARI)
_NUME_CODARE["utf-16"] = "UTF-16"
_NUME_CODARE["utf-32"] = "UTF-32"
_NUME_CODARE["iso8859_2"] = N_("Europa Centrală (ISO-8859-2)")

FPS_ALEGERI = (("auto", N_("Automat (din film)")), ("23.976", "23,976"), ("24", "24"), ("25", "25"),
	("29.97", "29,97"), ("30", "30"))
FPS_IMPLICIT = 23.976

# s, t, S, T cu sedila (U+015F, U+0163, U+015E, U+0162) -> cu virgula (U+0219, U+021B, U+0218, U+021A)
_VIRGULA = {0x15F: u"\u0219", 0x163: u"\u021b", 0x15E: u"\u0218", 0x162: u"\u021a"}
_ROMANESTI = frozenset(u"ăĂșȘțȚ\u015f\u015e\u0163\u0162")


def numeCodare(cod):
	return _NUME_CODARE.get(cod, cod or u"")


def _pareIso885916(date):
	"""Ghilimelele romanesti din ISO-8859-16 („ la 0xA5, ” la 0xB5) fata de cele din CP1250 (0x84, 0x93, 0x94): in
	CP1250, 0xA5 si 0xB5 ar iesi „Ą” si „µ”."""
	n16 = date.count(b"\xa5") + date.count(b"\xb5")
	n1250 = date.count(b"\x84") + date.count(b"\x93") + date.count(b"\x94")
	return n16 >= 2 and n16 > 2 * n1250


def _pareUtf16FaraBom(date):
	proba = date[:4000]
	if len(proba) < 16:
		return None
	pare = proba[1::2].count(b"\x00")
	impare = proba[0::2].count(b"\x00")
	jumatate = len(proba) // 2
	if pare > jumatate * 0.3 and impare < jumatate * 0.05:
		return "utf-16-le"
	if impare > jumatate * 0.3 and pare < jumatate * 0.05:
		return "utf-16-be"
	return None


def decodeaza(date, codare=CODARE_AUTO, implicita="cp1250"):
	"""octetii unui fisier -> (textul, codarea folosita). codare: CODARE_AUTO sau un cod din CODARI; implicita: pentru
	textul care nu e UTF-8. Nu cade niciodata: ce nu se poate citi devine U+FFFD."""
	if codare in (None, u"", CODARE_AUTO):
		if date.startswith(codecs.BOM_UTF8):
			return date[3:].decode("utf-8", "replace"), "utf-8"
		if date.startswith(codecs.BOM_UTF32_LE) or date.startswith(codecs.BOM_UTF32_BE):
			return date.decode("utf-32", "replace"), "utf-32"
		if date.startswith(codecs.BOM_UTF16_LE) or date.startswith(codecs.BOM_UTF16_BE):
			return date.decode("utf-16", "replace"), "utf-16"
		fara_bom = _pareUtf16FaraBom(date)
		if fara_bom:
			return date.decode(fara_bom, "replace"), "utf-16"
		try:
			return date.decode("utf-8"), "utf-8"
		except UnicodeDecodeError:
			pass
		codare = implicita or "cp1250"
		if codare == "cp1250" and _pareIso885916(date):
			codare = "iso8859_16"
	elif codare == "utf-8" and date.startswith(codecs.BOM_UTF8):
		date = date[3:]
	try:
		return date.decode(codare, "replace"), codare
	except LookupError:
		return date.decode("cp1250", "replace"), "cp1250"


def pareRomana(text):
	"""Textul are litere romanesti (ă, ș, ț, si s t cu sedila, pe care turca nu le are pe amandoua cu ă)."""
	n = 0
	for c in text[:20000]:
		if c in _ROMANESTI:
			n += 1
			if n >= 3:
				return True
	return False


def cuVirgula(text):
	"""s t S T cu sedila -> ș ț Ș Ț cu virgula (scrierea corecta a limbii romane)."""
	return text.translate(_VIRGULA)


def pareCodareGresita(text):
	"""Multe semne de inlocuire (U+FFFD): codarea aleasa nu se potriveste fisierului."""
	if not text:
		return False
	return text.count(u"�") > max(3, len(text) // 200)


# ------------------------------------------------------------------ textul replicilor

_COD_ASS = re.compile(r"\{\\[^{}]*\}")
_ETICHETA = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)(?:\s[^<>]*)?>|<\d{1,2}:\d{2}(?::\d{2})?\.\d{1,3}>")
_ENTITATI_WEB = ((u"&nbsp;", u" "), (u"&lrm;", u""), (u"&rlm;", u""), (u"&#160;", u" "))


def _codariAss(text):
	"""Codurile {\\...}: (textul fara ele, sus, False). {\\an7}-{\\an9} si {\\a5}-{\\a7} (SSA) = sus. {\\i1} si {\\i0}
	devin <i> si </i> oriunde ar fi (si dupa {\\an8}), deci cursivul se socoteste pe rand, ca la etichetele HTML."""
	sus = [False]

	def inlocuieste(m):
		cod = m.group(0)
		if re.search(r"\\an[789]", cod) or re.search(r"\\a(?:5|6|7)(?![0-9])", cod):
			sus[0] = True
		cursiv = re.findall(r"\\i([01])(?![0-9])", cod)
		if cursiv:
			return u"<i>" if cursiv[-1] == "1" else u"</i>"
		return u""
	return _COD_ASS.sub(inlocuieste, text), sus[0], False


def _randuriHtml(text):
	"""Text cu etichete simple (<i>, <b>, <u>, <font>, <c.clasa>, <v Nume>, marcaje de timp) -> randuri [(text, italic)].
	Un rand e cursiv daca mai mult de jumatate din literele lui sunt intre <i> si </i>; <i> care tine peste mai multe
	randuri se socoteste pe fiecare."""
	randuri = []
	italic = 0
	for linie in text.split(u"\n"):
		bucati = []
		cursive = normale = 0
		poz = 0
		for m in _ETICHETA.finditer(linie):
			parte = linie[poz:m.start()]
			if parte:
				bucati.append(parte)
				if italic > 0:
					cursive += len(parte.strip())
				else:
					normale += len(parte.strip())
			nume = (m.group(2) or u"").lower()
			if nume == u"i":
				italic = max(0, italic - 1) if m.group(1) else italic + 1
			poz = m.end()
		parte = linie[poz:]
		if parte:
			bucati.append(parte)
			if italic > 0:
				cursive += len(parte.strip())
			else:
				normale += len(parte.strip())
		curat = u"".join(bucati)
		for a, b in _ENTITATI_WEB:
			curat = curat.replace(a, b)
		curat = curat.strip()
		if curat:
			randuri.append((curat, cursive > normale))
	return randuri


def textPentruNucleu(randuri):
	"""Randurile -> textul dat serviciului: randuri despartite de „\\n”, un rand cursiv intre <i> si </i> (widgetul
	subtitrarilor alege litera dupa eticheta de la inceputul randului)."""
	iesire = []
	for text, italic in randuri:
		text = text[:MAX_TEXT_REPLICA]
		iesire.append(u"<i>%s</i>" % text if italic else text)
	return u"\n".join(iesire)


class _Replici(object):
	"""Adunarea replicilor unui fisier: [(inceput_ms, sfarsit_ms, randuri, sus)]."""

	def __init__(self):
		self.lista = []

	def adauga(self, inceput, sfarsit, text, sus=False, italicTot=False):
		if len(self.lista) >= MAX_REPLICI or inceput is None or inceput < 0:
			return
		if sfarsit is None or sfarsit <= inceput:
			sfarsit = inceput + DURATA_FARA_SFARSIT_MS
		text = text.replace(u"\r", u"")
		text, susAss, italicAss = _codariAss(text)
		randuri = _randuriHtml(text)
		if not randuri:
			return
		if italicTot or italicAss:
			randuri = [(t, True) for t, i in randuri]
		self.lista.append((int(inceput), int(sfarsit), randuri, bool(sus or susAss)))

	def sortate(self):
		return sorted(self.lista, key=lambda r: (r[0], r[1]))


def _ms(ore, minute, secunde, fractie):
	"""hh, mm, ss si fractia de secunda scrisa cu 1-3 cifre (5 = 500 ms, 50 = 500 ms, 500 = 500 ms)."""
	f = (fractie or u"0")[:3]
	return ((int(ore or 0) * 60 + int(minute)) * 60 + int(secunde)) * 1000 + int(f.ljust(3, u"0"))


def _linii(text):
	return text.replace(u"\r\n", u"\n").replace(u"\r", u"\n").split(u"\n")


# ------------------------------------------------------------------ formatele

_SRT_TIMP = re.compile(r"(\d{1,3}):(\d{1,2}):(\d{1,2})[,.:](\d{1,3})\s*-+>\s*(\d{1,3}):(\d{1,2}):(\d{1,2})[,.:](\d{1,3})")
_VTT_TIMP = re.compile(r"^(?:(\d{1,3}):)?(\d{1,2}):(\d{1,2})\.(\d{1,3})\s+-->\s+(?:(\d{1,3}):)?(\d{1,2}):(\d{1,2})\.(\d{1,3})(.*)$")
_MDVD = re.compile(r"^\{(\d+)\}\{(\d*)\}(.*)$")
_MPL2 = re.compile(r"^\[(\d+)\]\[(\d*)\](.*)$")
_TMP = re.compile(r"^(\d{1,2}):(\d{1,2}):(\d{1,2})(?:,\d+)?[:=](.*)$")
_SUBVIEWER2 = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})\.(\d{1,3}),(\d{1,2}):(\d{2}):(\d{2})\.(\d{1,3})\s*$")
_SUBVIEWER1 = re.compile(r"^\[(\d{1,2}):(\d{2}):(\d{2})\]\s*$")


def recunoaste(text):
	"""Formatul unui fisier de subtitrare dupa continut (inceputul lui): unul din TIP_*, sau TIP_NECUNOSCUT."""
	cap = text[:OCTETI_PROBA].lstrip(u"﻿")
	inceput = cap.lstrip()
	if inceput[:6].upper() == u"WEBVTT":
		return TIP_VTT
	if re.search(r"(?i)<sami[\s>]", cap):
		return TIP_SAMI
	if re.search(r"(?im)^\s*\[script info\]", cap) or re.search(r"(?im)^\s*dialogue\s*:", cap):
		if re.search(r"(?im)^\s*\[v4\+ styles\]", cap) or re.search(r"(?im)^\s*scripttype\s*:\s*v4\.00\+", cap):
			return TIP_ASS
		return TIP_SSA
	if _SRT_TIMP.search(cap):
		return TIP_SRT
	for rand in _linii(cap)[:40]:
		r = rand.strip()
		if not r:
			continue
		if _MDVD.match(r):
			return TIP_MICRODVD
		if _MPL2.match(r):
			return TIP_MPL2
	if re.search(r"(?im)^\s*\[information\]", cap) or any(_SUBVIEWER2.match(r.strip()) for r in _linii(cap)[:60]):
		return TIP_SUBVIEWER
	if re.search(r"(?im)^\s*\*\*start script\*\*", cap) or \
			sum(1 for r in _linii(cap)[:60] if _SUBVIEWER1.match(r.strip())) >= 2:
		return TIP_SUBVIEWER
	if sum(1 for r in _linii(cap)[:60] if _TMP.match(r.strip())) >= 2:
		return TIP_TMPLAYER
	return TIP_NECUNOSCUT


def citesteSrt(text):
	linii = _linii(text)
	r = _Replici()
	i, n = 0, len(linii)
	while i < n:
		m = _SRT_TIMP.search(linii[i])
		if not m:
			i += 1
			continue
		inceput = _ms(*m.group(1, 2, 3, 4))
		sfarsit = _ms(*m.group(5, 6, 7, 8))
		i += 1
		bucati = []
		while i < n and linii[i].strip():
			if _SRT_TIMP.search(linii[i]):
				break
			if linii[i].strip().isdigit() and i + 1 < n and _SRT_TIMP.search(linii[i + 1]):
				break
			bucati.append(linii[i])
			i += 1
		r.adauga(inceput, sfarsit, u"\n".join(bucati))
	return r.sortate()


def citesteVtt(text):
	linii = _linii(text)
	r = _Replici()
	i, n = 0, len(linii)
	# antetul (WEBVTT si randurile lui) pana la primul rand gol
	while i < n and linii[i].strip():
		i += 1
	while i < n:
		while i < n and not linii[i].strip():
			i += 1
		if i >= n:
			break
		bloc = []
		while i < n and linii[i].strip():
			bloc.append(linii[i])
			i += 1
		cap = bloc[0].strip()
		if cap.startswith(u"NOTE") or cap.startswith(u"STYLE") or cap.startswith(u"REGION"):
			continue
		k = 0
		if not _VTT_TIMP.match(bloc[0].strip()) and len(bloc) > 1:
			k = 1     # identificatorul replicii
		m = _VTT_TIMP.match(bloc[k].strip())
		if not m:
			continue
		inceput = _ms(*m.group(1, 2, 3, 4))
		sfarsit = _ms(*m.group(5, 6, 7, 8))
		setari = m.group(9) or u""
		sus = False
		ml = re.search(r"line:\s*(-?\d+(?:\.\d+)?)(%?)", setari)
		if ml:
			try:
				v = float(ml.group(1))
				sus = (v < 50) if ml.group(2) else (v >= 0 and v < 4)
			except ValueError:
				sus = False
		r.adauga(inceput, sfarsit, u"\n".join(bloc[k + 1:]), sus)
	return r.sortate()


def citesteMicroDvd(text):
	"""-> (replici in CADRE [(cadru_inceput, cadru_sfarsit, text, sus)], fps scris in fisier sau None). Cadrele se trec
	in milisecunde cu cadreInMs, dupa fps-ul ales."""
	replici = []
	fps = None
	for rand in _linii(text):
		rand = rand.strip()
		m = _MDVD.match(rand)
		if not m:
			continue
		a = int(m.group(1))
		b = int(m.group(2)) if m.group(2) else None
		t = m.group(3)
		if a <= 1 and (b is None or b <= 1) and fps is None and not replici:
			try:
				v = float(t.strip().replace(u",", u"."))
				if 10.0 <= v <= 120.0:
					fps = v
					continue
			except ValueError:
				pass
		# {y:i} (randul acesta) si {Y:i} (toate randurile) = cursiv; celelalte coduri {x:...} se scot
		italicTot = bool(re.search(r"\{Y:[^}]*i", t))
		parti = []
		for p in t.split(u"|"):
			it = bool(re.search(r"\{y:[^}]*i", p)) or p.startswith(u"/")
			p = re.sub(r"\{[a-zA-Z]:[^}]*\}", u"", p)
			if p.startswith(u"/"):
				p = p[1:]
			parti.append(u"<i>%s</i>" % p if it else p)
		replici.append((a, b, u"\n".join(parti), italicTot))
		if len(replici) >= MAX_REPLICI:
			break
	return replici, fps


def cadreInMs(replici, fps):
	fps = fps if fps and fps > 0 else FPS_IMPLICIT
	r = _Replici()
	for i, (a, b, t, italicTot) in enumerate(replici):
		inceput = int(round(a * 1000.0 / fps))
		if b is None:
			urm = replici[i + 1][0] if i + 1 < len(replici) else None
			sfarsit = int(round(urm * 1000.0 / fps)) if urm is not None else None
			if sfarsit is None or sfarsit - inceput > DURATA_FARA_SFARSIT_MS:
				sfarsit = inceput + DURATA_FARA_SFARSIT_MS
		else:
			sfarsit = int(round(b * 1000.0 / fps))
		r.adauga(inceput, sfarsit, t, False, italicTot)
	return r.sortate()


def citesteMpl2(text):
	r = _Replici()
	for rand in _linii(text):
		m = _MPL2.match(rand.strip())
		if not m:
			continue
		a = int(m.group(1)) * 100
		b = int(m.group(2)) * 100 if m.group(2) else None
		parti = []
		for p in m.group(3).split(u"|"):
			if p.startswith(u"/"):
				parti.append(u"<i>%s</i>" % p[1:])
			else:
				parti.append(p)
		r.adauga(a, b, u"\n".join(parti))
	return r.sortate()


def citesteTmPlayer(text):
	gasite = []
	for rand in _linii(text):
		m = _TMP.match(rand.strip())
		if m:
			gasite.append((((int(m.group(1)) * 60 + int(m.group(2))) * 60 + int(m.group(3))) * 1000, m.group(4)))
	r = _Replici()
	for i, (inceput, t) in enumerate(gasite):
		sfarsit = inceput + DURATA_FARA_SFARSIT_MS
		if i + 1 < len(gasite) and gasite[i + 1][0] > inceput:
			sfarsit = min(sfarsit, gasite[i + 1][0])
		r.adauga(inceput, sfarsit, t.replace(u"|", u"\n"))
	return r.sortate()


def citesteSubViewer(text):
	linii = _linii(text)
	r = _Replici()
	i, n = 0, len(linii)
	v1 = []
	while i < n:
		rand = linii[i].strip()
		m = _SUBVIEWER2.match(rand)
		if m:
			inceput = _ms(*m.group(1, 2, 3, 4))
			sfarsit = _ms(*m.group(5, 6, 7, 8))
			i += 1
			bucati = []
			while i < n and linii[i].strip():
				bucati.append(linii[i])
				i += 1
			t = u"\n".join(bucati)
			t = re.sub(r"(?i)\[br\]", u"\n", t)
			r.adauga(inceput, sfarsit, t)
			continue
		m1 = _SUBVIEWER1.match(rand)
		if m1:
			v1.append((i, ((int(m1.group(1)) * 60 + int(m1.group(2))) * 60 + int(m1.group(3))) * 1000))
		i += 1
	# SubViewer 1: [hh:mm:ss] / text / [hh:mm:ss] (sfarsitul), un rand gol intre replici
	k = 0
	while k < len(v1):
		poz, inceput = v1[k]
		textul = []
		j = poz + 1
		while j < n and linii[j].strip() and not _SUBVIEWER1.match(linii[j].strip()):
			textul.append(linii[j])
			j += 1
		sfarsit = None
		if k + 1 < len(v1) and v1[k + 1][0] == j:
			sfarsit = v1[k + 1][1]
			k += 2
		else:
			k += 1
		if textul:
			r.adauga(inceput, sfarsit, re.sub(r"(?i)\[br\]", u"\n", u"\n".join(textul)).replace(u"|", u"\n"))
	return r.sortate()


def claseSami(text):
	"""Limbile unui fisier SAMI: [(clasa, limba din definitie sau None)], in ordinea din <STYLE>."""
	stil = re.search(r"(?is)<style[^>]*>(.*?)</style>", text[:OCTETI_PROBA])
	clase = []
	if stil:
		for m in re.finditer(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", stil.group(1)):
			corp = m.group(2)
			limba = re.search(r"(?i)lang\s*:\s*([A-Za-z]{2,3})", corp)
			nume = re.search(r"(?i)name\s*:\s*([^;]+)", corp)
			clase.append((m.group(1), (limba and limba.group(1)) or (nume and nume.group(1).strip()) or None))
	if not clase:
		gasite = []
		for m in re.finditer(r"(?i)<p\s+class\s*=\s*\"?([A-Za-z0-9_-]+)", text[:OCTETI_PROBA]):
			if m.group(1) not in gasite:
				gasite.append(m.group(1))
		clase = [(c, None) for c in gasite]
	return clase


def citesteSami(text, clasa=None):
	"""Replicile unei limbi (clasa) dintr-un fisier SAMI; fara clasa, prima din fisier."""
	if clasa is None:
		clase = claseSami(text)
		clasa = clase[0][0] if clase else None
	sincronizari = []
	for m in re.finditer(r"(?is)<sync\s+start\s*=\s*\"?(\d+)\"?[^>]*>(.*?)(?=<sync[\s>]|</body|$)", text):
		inceput = int(m.group(1))
		for p in re.finditer(r"(?is)<p(?:\s+[^>]*?class\s*=\s*\"?([A-Za-z0-9_-]+)\"?)?[^>]*>(.*?)(?=<p[\s>]|$)", m.group(2)):
			if clasa is not None and p.group(1) is not None and p.group(1).lower() != clasa.lower():
				continue
			corp = re.sub(r"(?i)<br\s*/?>", u"\n", p.group(2))
			corp = re.sub(r"(?is)</?(?!i\b|/i\b)[a-z][^>]*>", u"", corp)
			sincronizari.append((inceput, corp))
			break
	r = _Replici()
	for i, (inceput, corp) in enumerate(sincronizari):
		gol = not corp.replace(u"&nbsp;", u"").replace(u"&#160;", u"").strip()
		if gol:
			continue
		sfarsit = sincronizari[i + 1][0] if i + 1 < len(sincronizari) else None
		if sfarsit is not None and sfarsit - inceput > 3 * DURATA_FARA_SFARSIT_MS:
			sfarsit = inceput + DURATA_FARA_SFARSIT_MS
		r.adauga(inceput, sfarsit, corp)
	return r.sortate()


def _timpAss(t):
	m = re.match(r"\s*(\d+):(\d{1,2}):(\d{1,2})[.:](\d{1,3})", t)
	if not m:
		return None
	return _ms(*m.group(1, 2, 3, 4))


def citesteAss(text):
	"""SSA/ASS, varianta simpla: textul replicilor (dupa al 9-lea camp al Format-ului), fara stil; \\N = rand nou;
	replicile cu desene (\\p1) se sar; stilurile cu aliniere sus si {\\an7}-{\\an9} = replica sus."""
	sectiune = u""
	format_ev = [u"layer", u"start", u"end", u"style", u"name", u"marginl", u"marginr", u"marginv", u"effect", u"text"]
	format_stil = []
	stiluri_sus = set()
	r = _Replici()
	for rand in _linii(text):
		s = rand.strip()
		if s.startswith(u"[") and s.endswith(u"]"):
			sectiune = s.lower()
			continue
		if u":" not in s:
			continue
		cheie, rest = s.split(u":", 1)
		cheie = cheie.strip().lower()
		if sectiune in (u"[v4+ styles]", u"[v4 styles]"):
			if cheie == u"format":
				format_stil = [c.strip().lower() for c in rest.split(u",")]
			elif cheie == u"style" and format_stil:
				campuri = [c.strip() for c in rest.split(u",")]
				if u"alignment" in format_stil and u"name" in format_stil and len(campuri) == len(format_stil):
					try:
						a = int(campuri[format_stil.index(u"alignment")])
					except ValueError:
						a = 2
					sus = a in (7, 8, 9) if sectiune == u"[v4+ styles]" else a in (5, 6, 7)
					if sus:
						stiluri_sus.add(campuri[format_stil.index(u"name")].lower())
		elif sectiune == u"[events]":
			if cheie == u"format":
				format_ev = [c.strip().lower() for c in rest.split(u",")]
			elif cheie == u"dialogue":
				campuri = rest.split(u",", len(format_ev) - 1)
				if len(campuri) < len(format_ev) or u"text" not in format_ev:
					continue
				def camp(nume):
					return campuri[format_ev.index(nume)] if nume in format_ev else u""
				t = camp(u"text")
				if re.search(r"\{[^}]*\\p[1-9]", t):
					continue
				t = t.replace(u"\\N", u"\n").replace(u"\\n", u"\n").replace(u"\\h", u" ")
				sus = camp(u"style").strip().lower() in stiluri_sus
				r.adauga(_timpAss(camp(u"start")), _timpAss(camp(u"end")), t, sus)
	return r.sortate()


def replici(text, tip, fps=None, clasa=None):
	"""Textul unui fisier -> replicile [(inceput_ms, sfarsit_ms, randuri, sus)], dupa tipul lui."""
	if tip == TIP_SRT:
		return citesteSrt(text)
	if tip == TIP_VTT:
		return citesteVtt(text)
	if tip == TIP_MICRODVD:
		cadre, fps_fisier = citesteMicroDvd(text)
		return cadreInMs(cadre, fps or fps_fisier)
	if tip == TIP_MPL2:
		return citesteMpl2(text)
	if tip == TIP_TMPLAYER:
		return citesteTmPlayer(text)
	if tip == TIP_SUBVIEWER:
		return citesteSubViewer(text)
	if tip == TIP_SAMI:
		return citesteSami(text, clasa)
	if tip in (TIP_SSA, TIP_ASS):
		return citesteAss(text)
	return []


def pentruNucleu(lista):
	"""Replicile -> tuplurile pentru setExternalSubtitleCues: (inceput_ms, sfarsit_ms, text, sus)."""
	return [(a, b, textPentruNucleu(randuri), sus) for a, b, randuri, sus in lista]


# ------------------------------------------------------------------ gasirea fisierelor si limba din nume

def _limbi():
	"""Components/HdsPisteLimbi (tabelul limbilor), sau None."""
	try:
		from Components import HdsPisteLimbi as L
		return L
	except ImportError:
		try:
			import HdsPisteLimbi as L
			return L
		except ImportError:
			return None


_SEMNE_FORCED = frozenset(("forced", "fortat", u"forțat", "fortate", u"forțate", "forc"))
_SEMNE_SURZI = frozenset(("sdh", "cc", "hoh", "surzi", "hearing"))
_NU_LIMBA = frozenset(("sub", "subs", "subtitle", "subtitles", "subtitrare", "subtitrari", "srt", "track", "default",
	"full", "complet", "complete", "web", "bluray", "dvd", "hdtv", "x264", "x265", "h264", "hevc", "1080p", "720p"))


def limbaDinNume(rest):
	"""Partea numelui dintre numele filmului si extensie („.ro.forced”, „_English”, „.en.sdh”) -> (limba canonica sau
	None, forced, surzi). „hi” inseamna „pentru surzi” numai langa alt cuvant cu limba (altfel e hindi)."""
	cuvinte = [c for c in re.split(r"[\s._\-\[\](),]+", rest) if c]
	L = _limbi()
	limba = None
	forced = surzi = False
	are_hi = False
	for c in reversed(cuvinte):
		cl = c.lower()
		if cl in _SEMNE_FORCED:
			forced = True
			continue
		if cl in _SEMNE_SURZI:
			surzi = True
			continue
		if cl == "hi":
			are_hi = True
			continue
		if cl in _NU_LIMBA or cl.isdigit() or limba is not None or L is None:
			continue
		gasita = L.limbaCanonica(c)
		if gasita:
			limba = gasita
	if are_hi:
		if limba is not None:
			surzi = True
		elif L is not None:
			limba = L.limbaCanonica("hi")
	return limba, forced, surzi


def _potrivesteNumele(nume, baza):
	"""Fisierul `nume` tine de filmul cu numele fara extensie `baza` (fara sa conteze literele mari): „film.srt”,
	„film.ro.srt”, „film_en.srt”, „film [ro].srt”; nu si „film 2.srt” (alt film din acelasi dosar)."""
	n = nume.lower()
	b = baza.lower()
	if not n.startswith(b):
		return None
	rest = nume[len(baza):]
	if os.path.splitext(n)[0] == b:
		return u""
	for sep in SEPARATORI_NUME:
		if rest.startswith(sep):
			return os.path.splitext(rest)[0]
	return None


_CLASA_IN_NUME = re.compile(r"^(.*\S) \(([^()/]{1,40})\)$")


def numeAfisat(nume, film=u"", limbaCunoscuta=False, maxim=20):
	"""Numele unui fisier de langa film, scurt pentru o coloana ingusta: partea de dupa numele filmului
	(„Film.2024.x264-GRUP.ro.forced.srt” -> „ro.forced.srt”, „Subs/Film...ro.srt” -> „Subs/ro.srt”); un nume care nu
	incepe cu numele filmului (sau e chiar numele filmului) isi pastreaza sfarsitul („…x264-GRUP.srt”), partea care
	deosebeste fisierele. Clasa SAMI sau pista VobSub dintre paranteze („film.smi (ROMRO)”) se lasa deoparte cand limba e
	cunoscuta: coloana limbii o arata. Cheia memoriei ramane numele intreg; asta e numai pentru ecran."""
	nume = nume or u""
	m = _CLASA_IN_NUME.match(nume)
	if m and limbaCunoscuta:
		nume = m.group(1)
	dosar, fisier = os.path.split(nume)
	if dosar.startswith(u"/"):
		dosar = u""       # un fisier ales de om din alt loc: numai numele lui
	baza = os.path.splitext(os.path.basename(film or u""))[0]
	scurt = fisier
	if baza and fisier.lower().startswith(baza.lower()) and len(fisier) > len(baza):
		rest = fisier[len(baza):]
		if os.path.splitext(rest)[0].strip(u"._- []()"):
			scurt = rest.lstrip(u"._- ")
	if dosar:
		scurt = dosar + u"/" + scurt
	if maxim and len(scurt) > maxim:
		scurt = u"…" + scurt[-(maxim - 1):]
	return scurt


def gasesteFisiere(cale_film, subdosare=True, listeaza=None, esteDosar=None, marime=None):
	"""Fisierele de subtitrare ale filmului: [{"cale", "nume" (scurt, relativ la dosarul filmului), "ext", "rest"
	(partea dintre numele filmului si extensie, "" pentru film.srt), "marime"}], cel mult MAX_FISIERE, in ordinea:
	dosarul filmului, apoi subdosarele. Functiile de sistem se pot inlocui (probele)."""
	listeaza = listeaza or os.listdir
	esteDosar = esteDosar or os.path.isdir
	marime = marime or os.path.getsize
	dosar, nume_film = os.path.split(cale_film)
	baza = os.path.splitext(nume_film)[0]
	try:
		intrari = sorted(listeaza(dosar or u"."))
	except (OSError, IOError):
		return []
	filme = [n for n in intrari if os.path.splitext(n)[1].lower() in EXTENSII_FILM]
	gasite = []

	def ia(cale, scurt, rest, ext):
		if len(gasite) >= MAX_FISIERE:
			return
		try:
			m = marime(cale)
		except (OSError, IOError):
			return
		gasite.append({"cale": cale, "nume": scurt, "ext": ext, "rest": rest, "marime": m})

	idx = set(os.path.splitext(n)[0].lower() for n in intrari if n.lower().endswith(".idx"))
	for n in intrari:
		ext = os.path.splitext(n)[1].lower()
		if ext not in EXTENSII or n == nume_film:
			continue
		if ext == ".sub" and os.path.splitext(n)[0].lower() in idx:
			continue      # VobSub (.idx + .sub): poze, nu text
		rest = _potrivesteNumele(n, baza)
		if rest is None:
			continue
		ia(os.path.join(dosar, n), n, rest, ext)
	if subdosare:
		for d in intrari:
			if d.lower() not in SUBDOSARE:
				continue
			cale_d = os.path.join(dosar, d)
			if not esteDosar(cale_d):
				continue
			try:
				sub = sorted(listeaza(cale_d))
			except (OSError, IOError):
				continue
			idx_sub = set(os.path.splitext(n)[0].lower() for n in sub if n.lower().endswith(".idx"))
			for n in sub:
				ext = os.path.splitext(n)[1].lower()
				if ext not in EXTENSII:
					continue
				if ext == ".sub" and os.path.splitext(n)[0].lower() in idx_sub:
					continue
				rest = _potrivesteNumele(n, baza)
				if rest is None:
					if len(filme) != 1:
						continue
					rest = os.path.splitext(n)[0]   # singurul film din dosar: numele intreg poate spune limba
				ia(os.path.join(cale_d, n), d + u"/" + n, rest, ext)
	return gasite


def limbiIdx(text):
	"""Limbile unui .idx VobSub: [(indexul pistei, codul scris la „id:”)], in ordinea din fisier."""
	rez = []
	for m in re.finditer(r"(?m)^id:\s*([A-Za-z-]*)\s*,\s*index:\s*(\d+)", text):
		rez.append((int(m.group(2)), m.group(1)))
	return rez


def _cercetaImagine(intrare, date):
	"""Prima privire intr-un fisier de subtitrari-imagine: .idx (VobSub, cu .sub langa el) sau .sup (PGS)."""
	limba, forced, surzi = limbaDinNume(intrare.get("rest") or u"")
	L = _limbi()
	baza = {"forced": forced, "surzi": surzi, "codare_gasita": u"", "clasa": None, "fps_fisier": None}
	if intrare["ext"] == ".sup":
		if date[:2] != b"PG":
			return []
		e = dict(intrare)
		e.update(baza)
		e.update({"tip": TIP_PGS, "limba": limba or u"und", "limba_din": "nume" if limba else None})
		return [e]
	text = date.decode("latin-1")
	if not text.startswith("# VobSub index file"):
		return []
	sub = os.path.splitext(intrare["cale"])[0] + ".sub"
	if not os.path.isfile(sub):
		return []
	rezultat = []
	piste = limbiIdx(text) or [(0, u"")]
	for index, cod in piste:
		e = dict(intrare)
		e.update(baza)
		l = limba
		ld = "nume" if limba else None
		if not l and cod and L is not None:
			l = L.limbaCanonica(cod)
			ld = "fisier" if l else None
		e.update({"tip": TIP_VOB, "limba": l or u"und", "limba_din": ld, "clasa": index, "sub": sub})
		if len(piste) > 1:
			e["nume"] = u"%s (%s)" % (intrare["nume"], cod or index)
		rezultat.append(e)
	return rezultat


def cercetaFisier(intrare, date, codare=CODARE_AUTO, implicita="cp1250"):
	"""Prima privire intr-un fisier (inceputul lui, OCTETI_PROBA): formatul, codarea, limba (din nume, altfel din text),
	forced/surzi, clasele SAMI. Intoarce o lista de intrari (un fisier SAMI cu doua limbi da doua), fiecare o copie a
	lui `intrare` cu campurile noi; un fisier care nu e subtitrare da lista goala."""
	if intrare.get("ext") in (".idx", ".sup"):
		return _cercetaImagine(intrare, date)
	text, gasita = decodeaza(date, codare, implicita)
	tip = recunoaste(text)
	if tip == TIP_NECUNOSCUT:
		return []
	if intrare["ext"] == ".sub" and tip not in (TIP_MICRODVD, TIP_SUBVIEWER):
		return []
	limba, forced, surzi = limbaDinNume(intrare.get("rest") or u"")
	limba_din = "nume" if limba else None
	rezultat = []
	clase = claseSami(text) if tip == TIP_SAMI else [(None, None)]
	L = _limbi()
	for clasa, limba_clasa in clase or [(None, None)]:
		e = dict(intrare)
		l = limba
		ld = limba_din
		if clasa is not None and limba_clasa and L is not None:
			lc = L.limbaCanonica(limba_clasa) or L.limbaCanonica(clasa[:2])
			if lc:
				l, ld = lc, "fisier"
		if l is None and pareRomana(text):
			l, ld = "ron", "text"
		e.update({"tip": tip, "limba": l or u"und", "limba_din": ld, "forced": forced, "surzi": surzi,
			"codare_gasita": gasita, "clasa": clasa, "fps_fisier": None})
		if clasa is not None:
			e["nume"] = u"%s (%s)" % (intrare["nume"], clasa)
		if tip == TIP_MICRODVD:
			e["fps_fisier"] = citesteMicroDvd(text[:4000])[1]
		rezultat.append(e)
	return rezultat


def citesteIntreg(intrare, date, codare=CODARE_AUTO, implicita="cp1250", virgula=True, fps=None):
	"""Tot fisierul -> (replicile pentru nucleu, codarea folosita, codarea pare gresita)."""
	text, folosita = decodeaza(date, codare, implicita)
	if virgula and (intrare.get("limba") == "ron" or (intrare.get("limba") in (None, u"", u"und") and pareRomana(text))):
		text = cuVirgula(text)
	lista = replici(text, intrare.get("tip"), fps, intrare.get("clasa"))
	return pentruNucleu(lista), folosita, pareCodareGresita(text)


def _ms_idx(text):
	m = re.match(r"\s*(-?)(\d+):(\d+):(\d+)[:.,](\d+)", text)
	if not m:
		return None
	v = ((int(m.group(2)) * 60 + int(m.group(3))) * 60 + int(m.group(4))) * 1000 + int(m.group(5)[:3].ljust(3, "0"))
	return -v if m.group(1) else v


def pachetIdx(text, index=0):
	"""Antetul .idx (tot ce e inainte de prima pista: paleta, marimea) si pachetele pistei `index`:
	[(start_ms, pozitia in .sub, 0)]. „delay:” muta pachetele care urmeaza."""
	antet = []
	pachete = []
	pista = None
	intarziere = 0
	for rand in text.splitlines():
		r = rand.strip()
		m = re.match(r"id:\s*[A-Za-z-]*\s*,\s*index:\s*(\d+)", r)
		if m:
			pista = int(m.group(1))
			intarziere = 0
			continue
		if pista is None:
			if r and not r.startswith("#"):
				antet.append(r)
			continue
		if pista != index:
			continue
		if r.startswith("delay:"):
			v = _ms_idx(r[6:])
			if v is not None:
				intarziere += v
		elif r.startswith("timestamp:"):
			m = re.match(r"timestamp:\s*([-\d:.,]+)\s*,\s*filepos:\s*([0-9a-fA-F]+)", r)
			if m:
				t = _ms_idx(m.group(1))
				if t is not None and t + intarziere >= 0:
					pachete.append((t + intarziere, int(m.group(2), 16), 0))
	return u"\n".join(antet), pachete


def seturiSup(cale, limita=MAX_SETURI_PGS):
	"""Seturile de afisare ale unui .sup (PGS), din antetele segmentelor: [(start_ms, pozitia, lungimea)]; un set incepe la
	o compozitie (PCS) si se termina la END. Se citesc numai antetele (13 octeti) si se sare peste restul."""
	rez = []
	try:
		with open(cale, "rb") as f:
			inceput = None
			pts = 0
			poz = 0
			while len(rez) < limita:
				antet = f.read(13)
				if len(antet) < 13:
					break
				if antet[:2] != b"PG":
					break
				tip = antet[10]
				lungime = (antet[11] << 8) | antet[12]
				if tip == 0x16:
					inceput = poz
					pts = (antet[2] << 24) | (antet[3] << 16) | (antet[4] << 8) | antet[5]
				f.seek(lungime, 1)
				poz += 13 + lungime
				if tip == 0x80 and inceput is not None:
					rez.append((pts // 90, inceput, poz - inceput))
					inceput = None
	except (OSError, IOError):
		pass
	return rez


def citesteOcteti(cale, cat=None):
	"""Octetii unui fisier (cel mult `cat` sau MAX_OCTETI_TEXT); None daca nu se poate citi."""
	try:
		with open(cale, "rb") as f:
			return f.read(cat if cat is not None else MAX_OCTETI_TEXT)
	except (OSError, IOError):
		return None


def fpsDinNucleu(valoare):
	"""sFrameRate de la servicemp3 (dvbmediasink da cadre pe 1000 de secunde: 23976, 25000) -> fps, sau None."""
	try:
		v = int(valoare)
	except (TypeError, ValueError):
		return None
	if v <= 0:
		return None
	f = v / 1000.0 if v > 1000 else float(v)
	return f if 10.0 <= f <= 120.0 else None


def fpsAles(fps_om, fps_fisier, fps_film):
	"""fps-ul pentru MicroDVD: ales de om, apoi scris in fisier, apoi al filmului, apoi 23,976."""
	for v in (fps_om, fps_fisier, fps_film):
		try:
			f = float(v)
		except (TypeError, ValueError):
			continue
		if 10.0 <= f <= 120.0:
			return f
	return FPS_IMPLICIT


# ------------------------------------------------------------------ memoria pe film

def cheieFilm(cale_film, marime):
	"""Numele fisierului filmului si marimea lui: un film mutat in alt dosar isi pastreaza setarile."""
	return u"%s|%d" % (os.path.basename(cale_film)[:200], int(marime or 0))


def _curataIntrare(v):
	if not isinstance(v, dict):
		return None
	rez = {}
	s = v.get("s")
	if s == OPRIT:
		rez["s"] = OPRIT
	elif isinstance(s, dict) and s.get("fel") in ("fisier", "pista"):
		curat = {"fel": s["fel"]}
		if s["fel"] == "fisier" and isinstance(s.get("nume"), str):
			curat["nume"] = s["nume"][:300]
		elif s["fel"] == "pista":
			try:
				curat["index"] = int(s.get("index", 0))
				curat["tip"] = int(s.get("tip", 0))
			except (TypeError, ValueError):
				return None
			curat["limbi"] = [str(x)[:8] for x in (s.get("limbi") or [])[:4]]
		rez["s"] = curat
	try:
		d = int(v.get("d", 0))
		if d:
			rez["d"] = max(-INTARZIERE_MAX_MS, min(INTARZIERE_MAX_MS, d))
	except (TypeError, ValueError):
		pass
	c = v.get("c")
	if isinstance(c, dict):
		rez["c"] = dict((str(k)[:300], str(x)[:20]) for k, x in list(c.items())[:MAX_FISIERE] if str(x) in _NUME_CODARE)
	f = v.get("f")
	if isinstance(f, dict):
		curat = {}
		for k, x in list(f.items())[:MAX_FISIERE]:
			try:
				fx = float(x)
			except (TypeError, ValueError):
				continue
			if 10.0 <= fx <= 120.0:
				curat[str(k)[:300]] = fx
		rez["f"] = curat
	a = v.get("a")
	if isinstance(a, list):
		rez["a"] = [str(x)[:1024] for x in a[:MAX_ADAUGATE] if isinstance(x, str) and x.startswith("/")]
	try:
		rez["t"] = int(v.get("t", 0))
	except (TypeError, ValueError):
		rez["t"] = 0
	return rez


class MemorieFilme(object):
	"""Ce se tine minte pe fiecare film: {"s": sursa aleasa (OPRIT, {"fel": "fisier", "nume"} sau {"fel": "pista",
	"index", "tip", "limbi"}), "d": intarzierea in ms, "c": {nume fisier: codare}, "f": {nume fisier: fps}, "a": [cai
	adaugate de mana], "t": ora}. Scrierea e atomica (.nou + fsync + os.replace); un fisier stricat sau prea mare se
	ignora; peste maxFilme pleaca cele mai vechi."""

	def __init__(self, cale=CALE_MEMORIE, maxFilme=MAX_FILME, maxOcteti=MAX_OCTETI_MEMORIE, ceas=None):
		self.cale = cale
		self.maxFilme = maxFilme
		self.maxOcteti = maxOcteti
		self.ceas = ceas or time.time
		self._date = None
		self._murdar = False
		self._lacat = threading.Lock()

	def _citeste(self):
		if self._date is not None:
			return self._date
		date = {}
		try:
			if os.path.getsize(self.cale) <= self.maxOcteti:
				with open(self.cale, "rb") as f:
					brut = json.loads(f.read().decode("utf-8"))
				if isinstance(brut, dict):
					for k, v in list(brut.items())[:self.maxFilme * 2]:
						curat = _curataIntrare(v)
						if isinstance(k, str) and curat is not None:
							date[k[:260]] = curat
			else:
				print("[HdsSubtitrariFilm] memoria filmelor e prea mare, o ignor")
		except (OSError, IOError):
			pass
		except (ValueError, UnicodeDecodeError):
			print("[HdsSubtitrariFilm] memoria filmelor e stricata, o ignor")
		self._date = date
		return date

	def film(self, cheie):
		with self._lacat:
			return dict(self._citeste().get(cheie) or {})

	def noteaza(self, cheie, **campuri):
		"""Schimba campurile unui film (in memorie); salveaza() le scrie."""
		if not cheie:
			return False
		with self._lacat:
			date = self._citeste()
			v = dict(date.get(cheie) or {})
			for k, x in campuri.items():
				if x is None:
					v.pop(k, None)
				else:
					v[k] = x
			v["t"] = int(self.ceas())
			curat = _curataIntrare(v)
			if curat is None:
				return False
			date[cheie] = curat
			if len(date) > self.maxFilme:
				for k in sorted(date, key=lambda x: date[x].get("t", 0))[:len(date) - self.maxFilme]:
					del date[k]
			self._murdar = True
			return True

	def uita(self, cheie):
		with self._lacat:
			date = self._citeste()
			if cheie in date:
				del date[cheie]
				self._murdar = True
				return True
			return False

	def deSalvat(self):
		return self._murdar

	def _scrie(self, date):
		"""JSON-ul (taiat la maxOcteti, cele mai vechi filme pleaca) scris atomic: .nou + fsync + os.replace. `date` e o
		copie de sus a dictionarului: noteaza() si uita() inlocuiesc intrarile, nu le schimba pe loc."""
		text = json.dumps(date, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
		if len(text) > self.maxOcteti:
			date = dict(date)
			while date and len(text) > self.maxOcteti:
				for k in sorted(date, key=lambda x: date[x].get("t", 0))[:max(1, len(date) // 10)]:
					del date[k]
				text = json.dumps(date, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
		nou = self.cale + ".nou"
		try:
			d = os.path.dirname(self.cale)
			if d and not os.path.isdir(d):
				os.makedirs(d)
			fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
			try:
				rest = text
				while rest:
					rest = rest[os.write(fd, rest):]
				os.fsync(fd)
			finally:
				os.close(fd)
			os.replace(nou, self.cale)
			return True
		except (OSError, IOError) as e:
			print("[HdsSubtitrariFilm] memoria filmelor nu s-a scris: %s" % e)
			try:
				os.unlink(nou)
			except OSError:
				pass
			return False

	def salveaza(self):
		"""Scrie memoria pe loc, daca s-a schimbat; True daca e pe disc (probele; pe receptor salveazaPeFir)."""
		with self._lacat:
			if not self._murdar:
				return True
			if self._scrie(dict(self._citeste())):
				self._murdar = False
				return True
			return False

	def salveazaPeFir(self):
		"""Ca salveaza(), dar JSON-ul si fsync-ul pe un fir: pe firul enigma2 ramane numai copia de sus a dictionarului.
		Cel mult o scriere deodata; o schimbare venita cat se scrie se scrie la sfarsit, de acelasi fir."""
		with self._lacat:
			if not self._murdar:
				return
			self._murdar = False
			if getattr(self, "_inScriere", False):
				self._dinNou = True
				return
			self._inScriere = True
			self._dinNou = False
			copie = dict(self._citeste())

		def scrie(date):
			while True:
				reusit = self._scrie(date)
				with self._lacat:
					if not reusit:
						self._murdar = True
					if self._dinNou and reusit:
						self._dinNou = False
						date = dict(self._date or {})
						continue
					self._inScriere = False
					return
		fir = threading.Thread(target=scrie, args=(copie,), name="HdsSubtitrariFilm-memorie")
		fir.daemon = True
		fir.start()


def sursaDinTuplu(tuplu, L=None):
	"""Tuplul unei subtitrari din getSubtitleList (sau None = fara subtitrare) -> ce se tine minte pe film."""
	if not tuplu:
		return OPRIT
	try:
		index = int(tuplu[1])
		tip = int(tuplu[2])
	except (TypeError, ValueError, IndexError):
		return None
	if index >= INDEX_FISIER:
		if len(tuplu) > 6 and tuplu[6]:
			return {"fel": "fisier", "nume": u"%s" % tuplu[6]}
		return None
	limba = tuplu[4] if len(tuplu) > 4 else u""
	limbi = (L.limbiDinText(limba)[:4] if L is not None else []) if limba else []
	return {"fel": "pista", "index": index, "tip": tip, "limbi": limbi}


def potrivesteSursa(tupluri, sursa, L=None):
	"""Tuplul din lista de acum care e sursa tinuta minte, sau None. Un fisier dupa nume; o pista din container dupa
	numar si limba, apoi dupa limba si tip."""
	if not isinstance(sursa, dict):
		return None
	if sursa.get("fel") == "fisier":
		for t in tupluri:
			if len(t) > 6 and int(t[1]) >= INDEX_FISIER and u"%s" % t[6] == sursa.get("nume"):
				return t
		return None
	limbi = sursa.get("limbi") or []
	pista = [t for t in tupluri if int(t[1]) < INDEX_FISIER]

	def limbiT(t):
		return (L.limbiDinText(t[4])[:4] if L is not None else []) if len(t) > 4 and t[4] else []
	for t in pista:
		if int(t[1]) == sursa.get("index") and set(limbiT(t)) == set(limbi):
			return t
	for t in pista:
		if limbi and set(limbiT(t)) == set(limbi) and int(t[2]) == sursa.get("tip"):
			return t
	return None


def _limbaPreferinta(L, pref, limbaReceptor):
	"""O preferinta de subtitrare (HdsPisteLimbi: „receptor”, „nimic” sau un cod de limba) -> codul limbii, sau None."""
	if L is None or pref in (None, u"", getattr(L, "PREF_NIMIC", "nimic"), getattr(L, "PREF_CANAL", "canal")):
		return None
	if pref == getattr(L, "PREF_RECEPTOR", "receptor"):
		return L.limbaCanonica(limbaReceptor)
	return L.limbaCanonica(pref)


def alegeFilm(subtitrari, preferinte, limbaReceptor, niciodata=False, sursa=None, fisierIntai=True, forced=None,
		limbaSunet=None, L=None, rang=None):
	"""Alegerea automata a subtitrarii la un film (curata). subtitrari: forma comuna din HdsPisteLimbi (subtitrareDinTuplu,
	cu "tuplu"); sursa: ce se tine minte pe film; forced(s) spune daca o subtitrare e „forced”; limbaSunet: limba pistei
	audio care merge (codul canonic) sau None. -> (subtitrarea sau None, motiv), cu motivele din HdsPisteLimbi.
	La aceeasi limba, fisierul de langa film trece inaintea pistei din film (fisierIntai). O subtitrare forced (numai
	replicile in alta limba) se alege cand sunetul e chiar in limba dorita; altfel intai cea completa. rang(s): intre
	fisierele de aceeasi limba, cel cu numarul mai mic trece primul (rangFisier)."""
	if sursa == OPRIT:
		return (None, "memorat-oprit")
	if sursa:
		t = potrivesteSursa([s["tuplu"] for s in subtitrari], sursa, L)
		if t is not None:
			for s in subtitrari:
				if s["tuplu"] is t:
					return (s, "memorat")
	if niciodata:
		return (None, "niciodata")
	forced = forced or (lambda s: False)
	for nr, pref in enumerate(tuple(preferinte or ())[:3]):
		limba = _limbaPreferinta(L, pref, limbaReceptor)
		if not limba:
			continue
		candidati = [s for s in subtitrari if limba in s["limbi"]]
		if not candidati:
			continue

		def cheie(s):
			f = forced(s)
			if limbaSunet == limba:
				ordine_forced = 0 if f else 1
			else:
				ordine_forced = 1 if f else 0
			fisier = s["fel"] == "fisier" and s["pid"] >= INDEX_FISIER
			return (
				ordine_forced,
				1 if s["surzi"] else 0,
				0 if s["limbi"][0] == limba else 1,
				(0 if fisier else 1) if fisierIntai else (1 if fisier else 0),
				rang(s) if rang is not None else 0,
				s["index"],
			)
		return (sorted(candidati, key=cheie)[0], "preferinta-%d" % (nr + 1))
	return (None, "fara-potrivire")


def rangFisier(intrare):
	"""Intre fisierele in aceeasi limba: limba scrisa in nume (film.ro.srt) sau in fisier (SAMI) inaintea celei ghicite din
	text, iar SubRip inaintea celorlalte formate. Numar mai mic = mai bun."""
	din = intrare.get("limba_din")
	limba = 0 if din in ("nume", "fisier") else 2
	return limba + (0 if intrare.get("tip") == TIP_SRT else 1)


def eticheta(tuplu):
	"""Eticheta scurta a unei subtitrari de film pentru liste: „SRT”, „Text”, „VobSub”."""
	try:
		return ETICHETE.get(int(tuplu[2]), u"")
	except (TypeError, ValueError, IndexError):
		return u""


# ================================================================== legatura cu enigma2 (importuri tarzii)

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi (pe PC)."""
	if not text:
		return text or u""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def initConfig():
	"""config.subtitles.hds_film_*: codarea implicita (si pentru pistele din MKV care nu sunt UTF-8), s t cu sedila -> ș ț,
	fisierul de langa film inaintea pistei din film, cautarea in subdosare. Se poate chema de oricate ori."""
	from Components.config import config, ConfigSubsection, ConfigSelection, ConfigYesNo
	if "subtitles" not in config.content.items:     # hasattr nu merge: o subsectiune lipsa da KeyError
		config.subtitles = ConfigSubsection()
	s = config.subtitles
	if "hds_film_codare" in s.content.items:
		return s
	# numele codarilor raman netraduse: setarea se face la pornire, inainte ca limba sa fie activa, iar ConfigSelection
	# si pagina web le traduc la afisare
	s.hds_film_codare = ConfigSelection(choices=list(CODARI_IMPLICITE), default="cp1250")
	s.hds_film_virgula = ConfigYesNo(default=True)
	s.hds_film_fisier_intai = ConfigYesNo(default=True)
	s.hds_film_subdosare = ConfigYesNo(default=True)
	return s


def _setari():
	"""(codarea implicita, virgula, fisierul intai, subdosare), cu valorile implicite daca setarile lipsesc."""
	try:
		s = initConfig()
		return (s.hds_film_codare.value, bool(s.hds_film_virgula.value), bool(s.hds_film_fisier_intai.value),
			bool(s.hds_film_subdosare.value))
	except Exception as e:
		print("[HdsSubtitrariFilm] setarile: %s" % e)
		return ("cp1250", True, True, True)


_MEMORIE = [None]


def memorie():
	if _MEMORIE[0] is None:
		_MEMORIE[0] = MemorieFilme()
	return _MEMORIE[0]


# filmele din locurile de retea redate prin http (DLNA, puntea locala pentru FTP si WebDAV, Components/HdsStocareRetea):
# adresa -> {"cale": numele virtual al filmului intr-un dosar din /tmp, langa subtitrarile descarcate, "marime"}
_RETEA = {}


def inregistreazaRetea(adresa, cale_virtuala, marime=0):
	"""Un film din retea redat prin adresa: subtitrarile lui se cauta langa cale_virtuala (descarcate acolo)."""
	_RETEA.clear()
	_RETEA[adresa] = {"cale": cale_virtuala, "marime": int(marime or 0)}


def uitaRetea():
	_RETEA.clear()


def caleLocala(cale):
	"""Calea dupa care se cauta subtitrarile: cea virtuala pentru un film din retea redat prin adresa, altfel aceeasi."""
	r = _RETEA.get(cale)
	return r["cale"] if r else cale


def esteFilm(cale):
	"""Un fisier video redat de servicemp3 (nu o inregistrare .ts, nu un flux din retea; un film dintr-un loc din
	retea redat prin adresa da, dupa calea lui virtuala)."""
	try:
		cale = caleLocala(cale)
		return isinstance(cale, str) and cale.startswith("/") and os.path.splitext(cale)[1].lower() in EXTENSII_FILM
	except Exception:
		return False


def _textRef(ref):
	try:
		return ref.toString() if ref is not None else u""
	except Exception:
		return u""


def _caleRef(ref):
	try:
		return caleLocala(ref.getPath()) if ref is not None else u""
	except Exception:
		return u""


class _Film(object):
	"""Starea filmului care merge: fisierele gasite (in ordinea din serviciu), coada replicilor de dat serviciului."""

	def __init__(self, ref, cale, serviciu):
		self.ref = ref
		self.cale = cale
		self.serviciu = serviciu      # getPtrString(): acelasi film pornit din nou e alt serviciu
		self.marime = 0
		self.cheie = None
		self.fisiere = []
		self.lista_gata = False       # firul a terminat lista fisierelor
		self.gata = False             # lista data serviciului, sau timpul de asteptare a trecut
		self.inregistrat = False
		self.coada = []               # (index, replici pentru nucleu)
		self.pornit = time.time()
		self.oprit = False
		self.fire = 0
		self.lacat = threading.Lock()
		self.mesaj = u""
		self.nDat = 0                 # cate fisiere are lista data ultima data serviciului (replicile merg numai la ele)
		self.adaugari = []            # (cale, proba, gata): fisiere alese de om, cercetate pe fir, de pus in lista pe firul enigma2


_FILM = [None]
_CEAS = [None]
_CEAS_SALVARE = [None]
_SESIUNE = [None]


def _nav():
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def _serviciuSiRef():
	nav = _nav()
	if nav is None:
		return None, None
	try:
		return nav.getCurrentService(), nav.getCurrentlyPlayingServiceReference()
	except Exception:
		return None, None


def _ptr(service):
	try:
		return service.getPtrString()
	except Exception:
		return u"%s" % id(service)


def _subtitrari(service):
	try:
		return service and service.subtitle()
	except Exception:
		return None


def _fpsFilm(service):
	try:
		from enigma import iServiceInformation
		info = service and service.info()
		return fpsDinNucleu(info.getInfo(iServiceInformation.sFrameRate)) if info else None
	except Exception:
		return None


def _porneste(ceas, functie, ms, repetat):
	from enigma import eTimer
	if ceas[0] is None:
		ceas[0] = eTimer()
		ceas[0].callback.append(functie)
	ceas[0].start(ms, not repetat)


def _programeazaSalvarea():
	"""Memoria pe film se scrie la 3 s dupa ultima schimbare (o apasare repetata pe intarziere = o singura scriere)."""
	try:
		_porneste(_CEAS_SALVARE, _salveazaAcum, 3000, False)
	except Exception:
		memorie().salveazaPeFir()


def _salveazaAcum():
	memorie().salveazaPeFir()


def _filmCurent(service=None, ref=None):
	"""Filmul care merge acum, daca starea lui e a serviciului de acum; altfel None."""
	f = _FILM[0]
	if f is None:
		return None
	if service is None or ref is None:
		service, ref = _serviciuSiRef()
	if service is None or _textRef(ref) != f.ref or _ptr(service) != f.serviciu:
		return None
	return f


def pregatit(session):
	"""Chemat din Components/HdsPisteLimbi.py (aplicaSubtitrare) la fiecare evUpdatedInfo: la un film nou porneste
	cautarea fisierelor. True cand alegerea automata poate lucra (lista fisierelor e in serviciu, sau nu e un film, sau
	cautarea a trecut de TIMP_CAUTARE_S); False cat se cauta inca."""
	_SESIUNE[0] = session
	service, ref = _serviciuSiRef()
	cale = _caleRef(ref)
	if service is None or not esteFilm(cale):
		return True
	f = _filmCurent(service, ref)
	if f is None:
		_filmNou(service, ref, cale)
		return False
	return f.gata


def _filmNou(service, ref, cale):
	vechi = _FILM[0]
	if vechi is not None:
		vechi.oprit = True
		memorie().salveazaPeFir()
	f = _Film(_textRef(ref), cale, _ptr(service))
	_FILM[0] = f
	implicita, virgula, fisierIntai, subdosare = _setari()
	_pornesteFir(f, _cautaFisiere, (f, implicita, virgula, subdosare, _fpsFilm(service)))
	_porneste(_CEAS, _bate, 100, True)


def _pornesteFir(f, tinta, argumente):
	with f.lacat:
		f.fire += 1

	def lucreaza():
		try:
			tinta(*argumente)
		except Exception as e:          # nimic nu scapa dintr-un fir
			print("[HdsSubtitrariFilm] cautarea subtitrarilor: %s" % e)
			f.lista_gata = True
		finally:
			with f.lacat:
				f.fire -= 1
	fir = threading.Thread(target=lucreaza, name="HdsSubtitrariFilm")
	fir.daemon = True
	fir.start()


def _intrareAdaugata(f, cale):
	"""Intrarea (inainte de prima privire) pentru un fisier ales de om, oriunde ar fi."""
	n = os.path.basename(cale)
	baza = os.path.splitext(os.path.basename(f.cale))[0]
	rest = _potrivesteNumele(n, baza)
	try:
		marime = os.path.getsize(cale)
	except (OSError, IOError):
		marime = 0
	return {"cale": cale, "nume": n if os.path.dirname(cale) == os.path.dirname(f.cale) else cale,
		"ext": os.path.splitext(n)[1].lower(), "rest": rest if rest is not None else os.path.splitext(n)[0],
		"marime": marime, "adaugat": True}


def _cautaFisiere(f, implicita, virgula, subdosare, fps_film):
	"""Pe fir: marimea filmului (cheia memoriei), fisierele gasite si cele adaugate de mana, prima privire in fiecare,
	apoi citirea intreaga, fisier cu fisier, in coada."""
	try:
		f.marime = os.path.getsize(f.cale)
	except (OSError, IOError):
		# un film din retea redat prin adresa: marimea data de server
		f.marime = next((r["marime"] for r in list(_RETEA.values()) if r["cale"] == f.cale), 0)
	f.cheie = cheieFilm(f.cale, f.marime)
	mem = memorie().film(f.cheie)
	gasite = gasesteFisiere(f.cale, subdosare)
	stiute = set(g["cale"] for g in gasite)
	for cale in mem.get("a") or []:
		if cale in stiute or len(gasite) >= MAX_FISIERE or not os.path.isfile(cale):
			continue
		gasite.append(_intrareAdaugata(f, cale))
	codari = mem.get("c") or {}
	intrari = []
	for g in gasite:
		if f.oprit:
			return
		date = citesteOcteti(g["cale"], OCTETI_PROBA)
		if not date:
			continue
		for e in cercetaFisier(g, date, codari.get(g["nume"], CODARE_AUTO), implicita):
			e["codare"] = codari.get(e["nume"], CODARE_AUTO)
			e["proba"] = date[:OCTETI_PREVIZUALIZARE]
			intrari.append(e)
	with f.lacat:
		# fisierele alese de om cat mergea cautarea (adaugaFisier) raman pe locurile lor, primele: numarul lor in
		# lista serviciului (100 + i) e deja dat tastei SUB si web-ului
		alese = set(e["cale"] for e in f.fisiere)
		inceput = len(f.fisiere)
		noi = [e for e in intrari if e["cale"] not in alese][:max(0, MAX_FISIERE - inceput)]
		f.fisiere = f.fisiere + noi
		f.lista_gata = True
	fps_om = mem.get("f") or {}
	for k, e in enumerate(noi):
		if f.oprit:
			return
		_citesteInCoada(f, inceput + k, e, implicita, virgula, fps_om.get(e["nume"]), fps_film)


def _citesteImagini(f, i, e):
	"""Pe fir: indexul pachetelor unui fisier de subtitrari-imagine (fara pachetele insele: le citeste serviciul)."""
	if e["tip"] == TIP_VOB:
		date = citesteOcteti(e["cale"], MAX_OCTETI_IDX)
		if not date:
			e["eroare"] = "citire"
			return
		info, pachete = pachetIdx(date.decode("latin-1"), e.get("clasa") or 0)
		element = ("imagini", TIP_VOB, e.get("sub") or os.path.splitext(e["cale"])[0] + ".sub", info, pachete)
	else:
		pachete = seturiSup(e["cale"])
		element = ("imagini", TIP_PGS, e["cale"], u"", pachete)
	e["replici"] = len(pachete)
	with f.lacat:
		f.coada = [x for x in f.coada if x[0] != i]
		f.coada.append((i, element))


def _citesteInCoada(f, i, e, implicita, virgula, fps_om=None, fps_film=None):
	if e["tip"] in TIPURI_IMAGINE:
		_citesteImagini(f, i, e)
		return
	if e.get("marime", 0) > MAX_OCTETI_TEXT:
		e["eroare"] = "mare"
		print("[HdsSubtitrariFilm] %s are peste %d KB, nu il citesc" % (e["nume"], MAX_OCTETI_TEXT // 1024))
		return
	date = citesteOcteti(e["cale"])
	if date is None:
		e["eroare"] = "citire"
		return
	fps = fpsAles(fps_om, e.get("fps_fisier"), fps_film) if e["tip"] == TIP_MICRODVD else None
	lista, folosita, rea = citesteIntreg(e, date, e.get("codare", CODARE_AUTO), implicita, virgula, fps)
	e["codare_folosita"] = folosita
	e["codare_rea"] = rea
	e["replici"] = len(lista)
	e["fps"] = fps
	with f.lacat:
		f.coada = [x for x in f.coada if x[0] != i]
		f.coada.append((i, lista))


def _listaPentruNucleu(fisiere):
	return [(e["nume"], e["limba"], e["tip"], (FLAG_FORCED if e["forced"] else 0) | (FLAG_SURZI if e["surzi"] else 0))
		for e in fisiere]


def _daLista(f, sub):
	"""Da serviciului lista fisierelor de acum (pe firul enigma2). -> lista data."""
	with f.lacat:
		lista = _listaPentruNucleu(f.fisiere)
	try:
		sub.setExternalSubtitles(lista)
		with f.lacat:
			f.nDat = len(lista)
	except Exception as e:
		print("[HdsSubtitrariFilm] lista subtitrarilor: %s" % e)
	return lista


def _arataPeEcran(text):
	"""Un mesaj scurt peste film, o singura data (Notifications: nu opreste ecranul deschis acum)."""
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, 6, "HdsSubtitrariFilm")
	except Exception as e:
		print("[HdsSubtitrariFilm] mesajul: %s" % e)


def _bate():
	"""Pe firul enigma2, la 100 ms cat e ceva de facut: lista fisierelor, apoi replicile, un fisier pe bataie."""
	f = _FILM[0]
	service, ref = _serviciuSiRef()
	if f is None or service is None or _textRef(ref) != f.ref or _ptr(service) != f.serviciu:
		if f is not None:
			f.oprit = True
			_FILM[0] = None
			memorie().salveazaPeFir()
		if _CEAS[0] is not None:
			_CEAS[0].stop()
		return
	sub = _subtitrari(service)
	if sub is None:
		return
	with f.lacat:
		adaugare = f.adaugari.pop(0) if f.adaugari else None
	if adaugare is not None:
		cale, proba, gata = adaugare
		rezultat = _adauga(f, proba, sub)
		if gata is not None:
			try:
				gata(*rezultat)
			except Exception as e:
				print("[HdsSubtitrariFilm] fisierul ales: %s" % e)
		return
	if not f.inregistrat and f.lista_gata:
		f.gata = True
		f.inregistrat = True
		intarziere_ms = memorie().film(f.cheie).get("d", 0) if f.cheie else 0
		try:
			sub.setSubtitleDelay(int(intarziere_ms))
		except Exception as e:
			print("[HdsSubtitrariFilm] intarzierea: %s" % e)
		lista = _daLista(f, sub)      # evUpdatedInfo -> alegerea automata (HdsPisteLimbi)
		if lista:
			print("[HdsSubtitrariFilm] %d subtitrari langa film: %s" % (len(lista), u", ".join(x[0] for x in lista)[:300]))
		return
	if not f.gata and time.time() - f.pornit > TIMP_CAUTARE_S:
		# un NAS lent: alegerea nu mai asteapta; fisierele vin cand se termina cautarea (cele alese de om raman)
		f.gata = True
		print("[HdsSubtitrariFilm] cautarea subtitrarilor dureaza, alegerea merge fara ele deocamdata")
		_daLista(f, sub)
		return
	with f.lacat:
		# replicile merg numai la fisierele pe care serviciul le are deja in lista (nDat)
		element = None
		for k, x in enumerate(f.coada):
			if x[0] < f.nDat:
				element = f.coada.pop(k)
				break
	if element is not None:
		i, lista = element
		try:
			if isinstance(lista, tuple) and lista[0] == "imagini":
				sub.setExternalSubtitlePictures(i, lista[1], lista[2], lista[3], lista[4])
			else:
				sub.setExternalSubtitleCues(i, lista)
		except Exception as e:
			print("[HdsSubtitrariFilm] replicile: %s" % e)
		e = f.fisiere[i] if i < len(f.fisiere) else None
		if e is not None and e.get("codare_rea") and indexFisierActiv() == i:
			f.mesaj = _t("Codarea pare greșită; alege alta din tasta SUB.")
			if not e.get("mesaj_aratat"):
				e["mesaj_aratat"] = True
				_arataPeEcran(f.mesaj)
		return
	with f.lacat:
		lucru = f.fire > 0 or bool(f.coada) or bool(f.adaugari) or not f.inregistrat
	if not lucru and _CEAS[0] is not None:
		_CEAS[0].stop()


# ------------------------------------------------------------------ alegerea automata si memoria (din HdsPisteLimbi)

def _limbaSunetului(service, L):
	try:
		piste, curenta = L.pisteAudio(service)
		for p in piste:
			if p["index"] == curenta and p["limbi"]:
				return p["limbi"][0]
	except Exception:
		pass
	return None


def alege(lista, preferinte, limbaReceptor, niciodata, session=None):
	"""Alegerea automata la filmul care merge (HdsPisteLimbi.aplicaSubtitrare): memoria filmului, apoi preferintele."""
	L = _limbi()
	service, ref = _serviciuSiRef()
	f = _filmCurent(service, ref)
	sursa = memorie().film(f.cheie).get("s") if (f is not None and f.cheie) else None
	fisiere = f.fisiere if f is not None else []

	def forced(s):
		i = s["pid"] - INDEX_FISIER
		return s["fel"] == "fisier" and 0 <= i < len(fisiere) and bool(fisiere[i].get("forced"))
	def rang(s):
		i = s["pid"] - INDEX_FISIER
		return rangFisier(fisiere[i]) if s["fel"] == "fisier" and 0 <= i < len(fisiere) else 1
	fisierIntai = _setari()[2]
	return alegeFilm(lista, preferinte, limbaReceptor, niciodata, sursa, fisierIntai, forced,
		_limbaSunetului(service, L) if L is not None else None, L, rang)


def noteazaAlegere(session, tuplu):
	"""Omul a ales o subtitrare (tuplu) sau „Fără subtitrări” (None) la filmul care merge: se tine minte pe film."""
	f = _filmCurent()
	if f is None or not f.cheie:
		return False
	sursa = sursaDinTuplu(tuplu, _limbi())
	if sursa is None:
		return False
	memorie().noteaza(f.cheie, s=sursa)
	_programeazaSalvarea()
	return True


# ------------------------------------------------------------------ pentru tasta SUB si pentru web

def _tupluPornit(session=None):
	try:
		from Components import HdsPisteLimbi as L
		return L.subtitrare_pornita(L.infobarActiv(session))
	except Exception:
		return None


def indexFisierActiv(session=None):
	"""Numarul (in lista filmului) al fisierului pornit acum, sau None (o pista din film, sau nimic)."""
	t = _tupluPornit(session)
	try:
		if t and int(t[1]) >= INDEX_FISIER:
			return int(t[1]) - INDEX_FISIER
	except (TypeError, ValueError, IndexError):
		pass
	return None


def intarziere():
	"""Intarzierea subtitrarilor la filmul care merge, in ms (0 fara film)."""
	service, ref = _serviciuSiRef()
	sub = _subtitrari(service)
	try:
		return int(sub.getSubtitleDelay()) if sub else 0
	except Exception:
		return 0


def alegeIntarziere(ms=None, pas=None):
	"""Pune intarzierea (ms) sau o muta (pas, ms); o tine minte pe film. -> (reusit, intarzierea de acum)."""
	service, ref = _serviciuSiRef()
	f = _filmCurent(service, ref)
	sub = _subtitrari(service)
	if f is None or sub is None:
		return False, 0
	try:
		acum = int(sub.getSubtitleDelay())
	except Exception:
		acum = 0
	try:
		nou = int(ms) if ms is not None else acum + int(pas or 0)
	except (TypeError, ValueError):
		return False, acum
	nou = max(-INTARZIERE_MAX_MS, min(INTARZIERE_MAX_MS, nou))
	try:
		if sub.setSubtitleDelay(nou) < 0:
			return False, acum
	except Exception:
		return False, acum
	if f.cheie:
		memorie().noteaza(f.cheie, d=nou if nou else None)
		_programeazaSalvarea()
	return True, nou


def _reciteste(f, i):
	implicita, virgula, fisierIntai, subdosare = _setari()
	service, ref = _serviciuSiRef()
	e = f.fisiere[i]
	fps_om = (memorie().film(f.cheie).get("f") or {}).get(e["nume"]) if f.cheie else None
	_pornesteFir(f, _citesteInCoada, (f, i, e, implicita, virgula, fps_om, _fpsFilm(service)))
	_porneste(_CEAS, _bate, 100, True)


def alegeCodare(cod, index=None):
	"""Codarea unui fisier (implicit cel pornit): se reciteste pe fir si se arata pe loc; se tine minte pe film."""
	if cod not in dict(CODARI):
		return False
	f = _filmCurent()
	i = index if index is not None else indexFisierActiv()
	if f is None or i is None or not (0 <= i < len(f.fisiere)) or f.fisiere[i]["tip"] not in TIPURI_TEXT:
		return False
	e = f.fisiere[i]
	e["codare"] = cod
	if f.cheie:
		c = dict(memorie().film(f.cheie).get("c") or {})
		if cod == CODARE_AUTO:
			c.pop(e["nume"], None)
		else:
			c[e["nume"]] = cod
		memorie().noteaza(f.cheie, c=c)
		_programeazaSalvarea()
	f.mesaj = u""
	_reciteste(f, i)
	return True


def alegeFps(fps, index=None):
	"""fps-ul unui fisier MicroDVD (implicit cel pornit): „auto” sau un numar din FPS_ALEGERI."""
	if fps not in dict(FPS_ALEGERI):
		return False
	f = _filmCurent()
	i = index if index is not None else indexFisierActiv()
	if f is None or i is None or not (0 <= i < len(f.fisiere)) or f.fisiere[i]["tip"] != TIP_MICRODVD:
		return False
	e = f.fisiere[i]
	if f.cheie:
		fx = dict(memorie().film(f.cheie).get("f") or {})
		if fps == "auto":
			fx.pop(e["nume"], None)
		else:
			fx[e["nume"]] = float(fps)
		memorie().noteaza(f.cheie, f=fx)
		_programeazaSalvarea()
	_reciteste(f, i)
	return True


def fpsAlesPentru(index=None):
	"""„auto” sau fps-ul ales de om pentru fisierul MicroDVD (implicit cel pornit)."""
	f = _filmCurent()
	i = index if index is not None else indexFisierActiv()
	if f is None or i is None or not (0 <= i < len(f.fisiere)) or not f.cheie:
		return "auto"
	v = (memorie().film(f.cheie).get("f") or {}).get(f.fisiere[i]["nume"])
	for cod, text in FPS_ALEGERI:
		if cod != "auto" and v is not None and abs(float(cod) - float(v)) < 0.001:
			return cod
	return "auto"


def previzualizare(cod, index=None, cate=3):
	"""Primele `cate` replici ale unui fisier cu codarea `cod`, ca sa se vada pe loc daca ă ș ț ies bine. Din inceputul
	fisierului tinut in memorie la prima privire (fara disc pe firul enigma2); intai 4 KB, apoi 16 KB. -> lista de texte."""
	f = _filmCurent()
	i = index if index is not None else indexFisierActiv()
	if f is None or i is None or not (0 <= i < len(f.fisiere)):
		return []
	e = f.fisiere[i]
	proba = e.get("proba") or b""
	if not proba:
		return []
	implicita, virgula, fisierIntai, subdosare = _setari()
	lista = []
	for cat in (4096, OCTETI_PREVIZUALIZARE):
		lista, folosita, rea = citesteIntreg(e, proba[:cat], cod, implicita, virgula, e.get("fps") or FPS_IMPLICIT)
		if len(lista) >= cate or cat >= len(proba):
			break
	return [x[2].replace(u"<i>", u"").replace(u"</i>", u"") for x in lista[:cate]]


def _probaFisier(f, cale):
	"""Pe fir (sau in probe): verificarea si prima privire intr-un fisier ales de om. -> (reusit, mesaj, intrarile)."""
	ext = os.path.splitext(cale)[1].lower()
	if ext not in EXTENSII or not os.path.isfile(cale):
		return False, _t("Fișierul acesta nu este o subtitrare."), []
	if ext == ".sub":
		# un .sub DVD (VobSub) se citeste prin .idx-ul de langa el
		for idx in (os.path.splitext(cale)[0] + ".idx", os.path.splitext(cale)[0] + ".IDX"):
			if os.path.isfile(idx):
				cale, ext = idx, ".idx"
				break
	if not f.cheie:
		# marimea filmului (cheia memoriei) inca necitita de firul cautarii: aceeasi valoare, citita aici
		try:
			marime = os.path.getsize(f.cale)
		except (OSError, IOError):
			marime = 0
		f.cheie = f.cheie or cheieFilm(f.cale, marime)
	date = citesteOcteti(cale, OCTETI_PROBA)
	intrari = cercetaFisier(_intrareAdaugata(f, cale), date, CODARE_AUTO, _setari()[0]) if date else []
	if not intrari:
		return False, _t("Fișierul acesta nu este o subtitrare."), []
	for e in intrari:
		e["codare"] = CODARE_AUTO
		e["proba"] = date[:OCTETI_PREVIZUALIZARE]
	return True, u"", intrari


def _adauga(f, proba, sub=None):
	"""Pe firul enigma2: intrarea cercetata intra in lista filmului (sau se gaseste acolo), se tine minte pe film si
	se da serviciului pe loc, si cat merge inca cautarea. -> (reusit, mesaj, numarul in lista serviciului sau None)."""
	reusit, mesaj, intrari = proba
	if not reusit:
		return False, mesaj, None
	e = intrari[0]
	with f.lacat:
		for i, x in enumerate(f.fisiere):
			if x["cale"] == e["cale"]:
				return True, u"", INDEX_FISIER + i
		if len(f.fisiere) >= MAX_FISIERE:
			return False, _t("Filmul are deja prea multe subtitrări."), None
		f.fisiere.append(e)
		i = len(f.fisiere) - 1
	if f.cheie:
		a = list(memorie().film(f.cheie).get("a") or [])
		if e["cale"] not in a:
			memorie().noteaza(f.cheie, a=(a + [e["cale"]])[-MAX_ADAUGATE:])
			_programeazaSalvarea()
	if sub is None:
		service, ref = _serviciuSiRef()
		sub = _subtitrari(service)
	if sub is not None:
		_daLista(f, sub)
	_reciteste(f, i)
	return True, u"", INDEX_FISIER + i


def adaugaFisier(cale, gata=None):
	"""Un fisier ales de om („Alege alt fișier...” pe televizor sau in web): intra in lista filmului, se tine minte pe
	film si se poate porni pe loc, si cat merge inca cautarea fisierelor de langa film.
	Cu `gata(reusit, mesaj, numar)`: citirea si prima privire in fisier se fac pe un fir (un NAS lent nu opreste
	meniurile), iar adaugarea si `gata` pe firul enigma2, din _bate; intoarce (True, "", None) cand citirea a pornit.
	Fara `gata` (probele): totul pe loc. -> (reusit, mesaj, numarul lui in lista serviciului sau None)."""
	f = _filmCurent()
	if f is None:
		return False, _t("Nu rulează niciun film."), None
	if os.path.splitext(cale or u"")[1].lower() not in EXTENSII:
		return False, _t("Fișierul acesta nu este o subtitrare."), None
	if gata is None:
		return _adauga(f, _probaFisier(f, cale))

	def lucreaza():
		proba = _probaFisier(f, cale)
		with f.lacat:
			f.adaugari.append((cale, proba, gata))
	_pornesteFir(f, lucreaza, ())
	_porneste(_CEAS, _bate, 100, True)
	return True, u"", None


def tupluri():
	"""Lista subtitrarilor serviciului care merge (pistele din film, apoi fisierele), ca tupluri."""
	service, ref = _serviciuSiRef()
	sub = _subtitrari(service)
	try:
		return [tuple(t) for t in (sub.getSubtitleList() if sub else []) or []]
	except Exception:
		return []


def tupluPentru(numar):
	"""Tuplul din lista serviciului pentru numarul `numar` (100 + index la fisiere), sau None."""
	for t in tupluri():
		try:
			if int(t[1]) == int(numar):
				return t
		except (TypeError, ValueError, IndexError):
			continue
	return None


def stare(session=None):
	"""Ce stie modulul despre filmul care merge, pentru ecrane si web: {"film", "nume", "fisiere": [{index, nume,
	limba, format, codare, codare_gasita, forced, surzi, replici, eroare}], "activ" (numarul din lista sau None),
	"intarziere_ms", "codare", "codare_gasita", "fps", "e_text", "e_microdvd", "mesaj", "cautare_in_curs"}."""
	service, ref = _serviciuSiRef()
	f = _filmCurent(service, ref)
	rez = {"film": f is not None, "nume": os.path.basename(f.cale) if f is not None else u"", "fisiere": [],
		"activ": None, "intarziere_ms": 0, "codare": CODARE_AUTO, "codare_gasita": u"", "fps": "auto", "e_microdvd": False,
		"e_text": False, "mesaj": u"", "cautare_in_curs": False}
	if f is None:
		return rez
	rez["intarziere_ms"] = intarziere()
	rez["cautare_in_curs"] = not f.lista_gata
	rez["mesaj"] = f.mesaj
	activ = indexFisierActiv(session)
	with f.lacat:
		fisiere = list(f.fisiere)
	for i, e in enumerate(fisiere):
		rez["fisiere"].append({"index": INDEX_FISIER + i, "nume": e["nume"], "limba": e["limba"],
			"format": ETICHETE.get(e["tip"], u""), "codare": e.get("codare", CODARE_AUTO),
			"codare_gasita": e.get("codare_folosita") or e.get("codare_gasita") or u"", "forced": bool(e.get("forced")),
			"surzi": bool(e.get("surzi")), "replici": e.get("replici"), "eroare": e.get("eroare"),
			"adaugat": bool(e.get("adaugat"))})
	if activ is not None and 0 <= activ < len(fisiere):
		e = fisiere[activ]
		rez["activ"] = INDEX_FISIER + activ
		rez["codare"] = e.get("codare", CODARE_AUTO)
		rez["codare_gasita"] = e.get("codare_folosita") or e.get("codare_gasita") or u""
		rez["e_text"] = e["tip"] in TIPURI_TEXT
		rez["e_microdvd"] = e["tip"] == TIP_MICRODVD
		rez["fps"] = fpsAlesPentru(activ)
	return rez


def textIntarziere(ms):
	"""+1,5 s / −0,3 s / 0 s (virgula zecimala)."""
	try:
		ms = int(ms)
	except (TypeError, ValueError):
		ms = 0
	if ms == 0:
		return u"0 s"
	semn = u"+" if ms > 0 else u"−"
	a = abs(ms)
	if a % 1000 == 0:
		return u"%s%d s" % (semn, a // 1000)
	if a % 100 == 0:
		return u"%s%d,%d s" % (semn, a // 1000, (a % 1000) // 100)
	return u"%s%d,%03d s" % (semn, a // 1000, a % 1000)

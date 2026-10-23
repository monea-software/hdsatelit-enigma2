# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSemnaturaPornire.py: randul „HD Satelit <versiune> · moneasoftware.com & hdsatelit.com” scris peste poza de
# pornire, cat se incarca interfata. Poza (/usr/share/backdrop.mvi) o pune showiframe pe stratul video, fara niciun
# text in ea; randul se deseneaza pe OSD, deasupra ei, de lib/gdi/ecranpornire.cpp (deseneazaSemnaturaPornire): o
# capsula intunecata, pe jumatate stravezie, cu textul centrat, jos, in acelasi loc peste orice poza, si cu versiunea
# imaginii, ca omul sa vada dupa o actualizare ca s-a instalat cea noua.
#
# Cum il cheama mytest.py (trei locuri, fiecare in try/except: pornirea nu depinde de el):
#   1. arata() cat mai devreme, dupa profile("PYTHON_START"): OSD-ul are atunci 720x576, iar capsula se face la
#      masurile pentru 1920x1080 si se pune micsorata (placa video intinde OSD-ul pe tot ecranul);
#   2. arata() din nou dupa skin.loadSkinData(): skinul schimba rezolutia OSD-ului, iar gFBDC::setResolution sterge
#      tot ce era desenat, deci capsula se pune din nou, la rezolutia skinului;
#   3. ascundeLaPrimulDesen() tot atunci: la primul pas al buclei principale (cand se deschide primul ecran) cere
#      desktopului redesenarea locului capsulei. De obicei nici nu e nevoie (schimbarea rezolutiei face desktopul sa
#      redeseneze tot ecranul), dar un skin cu rezolutia de pornire nu ar sterge-o altfel.
#
# Textul nu se traduce: la primul pas limba interfetei nu e inca incarcata, iar „HD Satelit 0.1.6” se citeste la fel
# in orice limba. Fontul (HdsRegular din imagine) se inregistreaza aici sub numele HdsSemnatura, fiindca la primul pas
# skinul nu a inregistrat inca niciun font; addFont pe un fisier care nu e font opreste enigma2 (lib/gdi/font.cpp),
# deci fisierul se verifica inainte (marime si semnatura TrueType/OpenType).
# Modulul nu importa nimic din enigma la incarcare, ca sa poata fi incercat pe PC.

import os

SITURI = "moneasoftware.com & hdsatelit.com"
NUME_IMAGINE = "HD Satelit"
ALIAS_FONT = "HdsSemnatura"
FONTURI = (
	"/usr/share/fonts/HdsRegular.ttf",
	"/usr/share/enigma2/HDSatelit/fonts/HdsRegular.ttf",
)
IMAGE_VERSION = "/etc/image-version"
# un font adevarat are zeci de KB; sub atat fisierul e taiat
MARIME_MINIMA_FONT = 10 * 1024
SEMNATURI_FONT = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
LUNGIME_BUILD = 16
# o parte a versiunii cu doua cifre (0.3.10): fiecare parte pe doua cifre (Makefile.am, HdsJurnalVersiuni)
LUNGIME_BUILD_LUNG = 19

_font_pus = [False]
_ceasuri = []
_legaturi = []


def _jurnal(text):
	print("[HdsSemnaturaPornire] %s" % text)


def versiuneImagine(cale=IMAGE_VERSION):
	"""„0.1.6” din randul version= al /etc/image-version (16 cifre: felul, major, minor, revizia, data si ora
	constructiei; 19 cifre cand o parte are doua cifre, "0.3.10"). Sir gol daca fisierul lipseste sau randul are alta
	forma (alta imagine, emulatorul)."""
	try:
		with open(cale, "rb") as f:
			text = f.read(4096).decode("utf-8", "replace")
	except (OSError, IOError):
		return ""
	for rand in text.splitlines():
		cheie, _semn, valoare = rand.partition("=")
		if cheie.strip() != "version":
			continue
		valoare = valoare.strip()
		if len(valoare) == LUNGIME_BUILD and valoare.isdigit():
			return "%s.%s.%s" % (valoare[1], valoare[2], valoare[3])
		if len(valoare) == LUNGIME_BUILD_LUNG and valoare.isdigit() and valoare.isascii():
			return "%d.%d.%d" % (int(valoare[1:3]), int(valoare[3:5]), int(valoare[5:7]))
		return ""
	return ""


def textSemnatura(versiune=None):
	"""Randul scris peste poza: „HD Satelit 0.1.6 · moneasoftware.com & hdsatelit.com”; fara versiune cunoscuta,
	numai siturile."""
	if versiune is None:
		versiune = versiuneImagine()
	if versiune:
		return "%s %s  ·  %s" % (NUME_IMAGINE, versiune, SITURI)
	return SITURI


def fontBun(cale):
	"""Fisierul pare un font TrueType/OpenType intreg (marime si primii patru octeti)."""
	try:
		if os.path.getsize(cale) < MARIME_MINIMA_FONT:
			return False
		with open(cale, "rb") as f:
			return f.read(4) in SEMNATURI_FONT
	except (OSError, IOError):
		return False


def _puneFont():
	if _font_pus[0]:
		return True
	from enigma import addFont
	for cale in FONTURI:
		if fontBun(cale):
			addFont(cale, ALIAS_FONT, 100, False)
			_font_pus[0] = True
			return True
	_jurnal("niciun font HdsRegular bun; se incearca fontul skinului")
	return False


def arata():
	"""Deseneaza semnatura pe OSD, la rezolutia de acum. True daca s-a desenat. Nu arunca."""
	try:
		_puneFont()
		from enigma import deseneazaSemnaturaPornire
		cod = deseneazaSemnaturaPornire(textSemnatura())
		if cod:
			_jurnal("nedesenata (cod %d)" % cod)
		return cod == 0
	except Exception as eroare:
		_jurnal("nedesenata: %s" % eroare)
		return False


def _ascunde():
	try:
		from enigma import ascundeSemnaturaPornire
		ascundeSemnaturaPornire()
	except Exception as eroare:
		_jurnal("nu am putut cere redesenarea: %s" % eroare)
	del _ceasuri[:]
	del _legaturi[:]


def ascundeLaPrimulDesen():
	"""La primul pas al buclei principale, locul semnaturii se redeseneaza (vezi antetul). Nu arunca."""
	try:
		from enigma import eTimer
		ceas = eTimer()
		try:
			ceas.callback.append(_ascunde)
		except AttributeError:
			_legaturi.append(ceas.timeout.connect(_ascunde))
		_ceasuri.append(ceas)
		ceas.start(0, True)
		return True
	except Exception as eroare:
		_jurnal("ascunderea nu s-a putut programa: %s" % eroare)
		return False

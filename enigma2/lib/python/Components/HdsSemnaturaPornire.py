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
#
# 0.7.7 (OSD; e-mailul 6416, Vu+ Solo SE; TODO 15.11 14:22): in coltul din dreapta jos „Enigma2 pornește...”, ca omul sa
# stie ca interfata se incarca. Se pune din mytest.py dupa skin.loadSkinData (arataColt, inaintea lui arata()): o fereastra
# mica pe desktop, cu aceleasi culori si aceeasi inaltime ca semnatura, desenata pe loc (bucla principala nu merge inca);
# desenul poate sterge capsula, de aceea arata() vine dupa. Pleaca odata cu semnatura, la primul pas al buclei. Inainte de
# skin (primul arata()) nu exista fonturi si stil de ferestre, deci textul apare de la incarcarea skinului pana la primul
# ecran. Limba interfetei nu e inca activata: limba se citeste din setari (config.osd.language), traducerea din catalogul
# gettext al ei, incarcat separat (fara sa schimbe limba interfetei); fara traducere, engleza.

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


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce in textColt."""
	return text


# textul din colt: cheia (romana, ca toate textele imaginii) si rezerva engleza
# TRANSLATORS: la pornire, in coltul din dreapta jos, pana la primul ecran („Enigma2” ramane asa; in turca promis
# „Enigma2 başlatılıyor...”)
TEXT_COLT = N_("Enigma2 pornește...")
TEXT_COLT_EN = "Enigma2 is starting..."
CALE_SETARI = "/etc/enigma2/settings"
# masurile pe 1920x1080 (ca semnatura din lib/gdi/ecranpornire.cpp: font 30, inaltime 56, 40 de jos, culorile ei);
# 48 de la marginea din dreapta: zona sigura a ecranului (ca rotita din stanga sus, main/enigma.cpp)
COLT_FONT = 30
COLT_INALTIME = 56
COLT_MARGINE_TEXT = 32
COLT_JOS = 40
COLT_DREAPTA = 48
COLT_FUNDAL = (10, 14, 26, 255 - 184)   # gRGB: al patrulea = transparenta (0 plin)
COLT_TEXT = (240, 246, 252, 0)
COLT_Z = 100

_font_pus = [False]
_ceasuri = []
_legaturi = []
_colt = []      # [fereastra, eticheta] cat se vede textul din colt


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


def limbaSetari(cale=CALE_SETARI):
	"""config.osd.language din fisierul de setari („tr_TR”), sau "" (fisier lipsa, rand lipsa: limba din fabrica)."""
	try:
		with open(cale, "rb") as f:
			text = f.read(1024 * 1024).decode("utf-8", "replace")
	except (OSError, IOError):
		return ""
	for rand in text.splitlines():
		cheie, _semn, valoare = rand.partition("=")
		if cheie.strip() == "config.osd.language":
			return valoare.strip()
	return ""


def _dosarCataloage():
	try:
		from Tools.Directories import resolveFilename, SCOPE_LANGUAGE
		return resolveFilename(SCOPE_LANGUAGE, "")
	except Exception:
		return "/usr/share/enigma2/po/"


def textColt(limba=None, dosar=None):
	"""„Enigma2 pornește...” in limba data (implicit cea din setari, „ro_RO” din fabrica): din catalogul gettext al limbii,
	incarcat separat; o limba fara catalog sau fara traducere ia engleza (catalogul en, apoi TEXT_COLT_EN). Nu arunca."""
	if limba is None:
		limba = limbaSetari() or "ro_RO"
	if limba.split("_")[0].lower() == "ro":
		return TEXT_COLT
	if dosar is None:
		dosar = _dosarCataloage()
	import gettext
	for coduri in ([limba], ["en_EN"]):
		try:
			t = gettext.translation("enigma2", dosar, languages=coduri, fallback=True).gettext(TEXT_COLT)
		except Exception:
			t = TEXT_COLT
		if t and t != TEXT_COLT:
			return t
	return TEXT_COLT_EN


def arataColt(text=None):
	"""Dupa skin.loadSkinData: textul din coltul din dreapta jos (vezi antetul), desenat pe loc. True daca s-a pus. Nu
	arunca. Dupa el trebuie chemat arata() (desenul desktopului poate sterge capsula)."""
	try:
		from enigma import eWindow, eLabel, eSize, ePoint, gFont, gRGB, getDesktop
		if text is None:
			text = textColt()
		_puneFont()
		desktop = getDesktop(0)
		marime = desktop.size()
		lw, lh = marime.width(), marime.height()
		if lw < 64 or lh < 64:
			return False
		fx, fy = lw / 1920.0, lh / 1080.0
		inaltime = max(1, int(round(COLT_INALTIME * fy)))
		fereastra = eWindow(desktop, COLT_Z)
		fereastra.setFlag(eWindow.wfNoBorder)
		try:
			fereastra.setAnimationMode(0)
		except Exception:
			pass
		eticheta = eLabel(fereastra.child())
		# HdsRegular (aliasul semnaturii) cand s-a putut inregistra, altfel fontul obisnuit al skinului
		eticheta.setFont(gFont(ALIAS_FONT if _font_pus[0] else "Regular", max(8, int(round(COLT_FONT * fy)))))
		eticheta.setNoWrap(1)
		eticheta.resize(eSize(lw, inaltime))
		eticheta.setText(text)
		latimeText = eticheta.calculateSize().width()
		latime = min(lw - 2 * int(COLT_DREAPTA * fx), latimeText + 2 * int(round(COLT_MARGINE_TEXT * fx)))
		if latimeText <= 0 or latime <= 0:
			return False
		fereastra.resize(eSize(latime, inaltime))
		fereastra.move(ePoint(lw - latime - int(round(COLT_DREAPTA * fx)), lh - inaltime - int(round(COLT_JOS * fy))))
		fereastra.setBackgroundColor(gRGB(*COLT_FUNDAL))
		try:
			fereastra.setCornerRadius(inaltime // 2)
		except Exception:
			pass
		eticheta.move(ePoint(0, 0))
		eticheta.resize(eSize(latime, inaltime))
		eticheta.setHAlign(eLabel.alignCenter)
		eticheta.setVAlign(eLabel.alignCenter)
		eticheta.setForegroundColor(gRGB(*COLT_TEXT))
		eticheta.setBackgroundColor(gRGB(*COLT_FUNDAL))
		eticheta.setTransparent(1)
		fereastra.show()
		_colt[:] = [fereastra, eticheta]
		desktop.paint()
		_jurnal("textul din colt pus: %s" % text)
		return True
	except Exception as eroare:
		_jurnal("textul din colt nepus: %s" % eroare)
		return False


def ascundeColt():
	"""Fereastra din colt pleaca (locul ei se redeseneaza la urmatorul desen al desktopului). Nu arunca."""
	if not _colt:
		return
	try:
		_colt[0].hide()
	except Exception as eroare:
		_jurnal("textul din colt nu s-a ascuns: %s" % eroare)
	del _colt[1:]     # eticheta (copilul ferestrei) intai, apoi fereastra
	del _colt[:]


def _ascunde():
	try:
		from enigma import ascundeSemnaturaPornire
		ascundeSemnaturaPornire()
	except Exception as eroare:
		_jurnal("nu am putut cere redesenarea: %s" % eroare)
	ascundeColt()
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

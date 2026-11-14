# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsWidevine.py: modulul Widevine (protectia filmelor la Netflix si alte servicii cu cont) pe receptorul omului.
# Eduard, 13.11.2026 09:12: modulul se aduce de la Google pe receptorul omului NUMAI dupa ce omul vede textul licentei
# Google si ce inseamna (modulul vine de la Google, nu de la noi) si apasa „Accept”; fara accept, nimic.
#
# CALEA UNICA a modulului in imagine: /home/root/.local/share/widevine/libwidevinecdm.so (+ manifest.json alaturi, cu
# versiunea). Media Center (pluginul HdsMediaCenter) il leaga in dosarul cdm al profilului lui; HD Satelit Browser il ia
# cu --widevine-cdm-path. Modulul are ~10 MB (pe memoria receptorului). Arhiva de ~1,2 GB din care se scoate se sterge
# dupa; sta in memoria interna cand are LIBER_INTERN_KB liberi (fara stick, regula 1f, 13.11.2026), altfel pe stick/disc.
#
# Folosire:
#   instaleaza(session, gata=None)       ecranul: licenta, „Nu accept” / „Accept”, apoi descarcarea in fundal si un
#                                        mesaj la sfarsit; gata(True|False, text) la sfarsit (sau gata(False, ...) la refuz)
#   pornesteDescarcarea(accept, gata)    fara ecran (pagina web /aplicatii-tv, dupa ce omul a bifat acceptul acolo)
#   stare()                              {"faza": nimic|lucreaza|gata|eroare, "procent": n, "mesaj": text}, pentru web
#   instalat(), versiune(), textLicenta()
# Programul care descarca: Components/HdsWidevineGoogle.py (python3, in afara enigma2), pornit cu eConsoleAppContainer.
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC il folosesc direct).

import json
import os

DOSAR = "/home/root/.local/share/widevine"
MODUL = DOSAR + "/libwidevinecdm.so"
MANIFEST = DOSAR + "/manifest.json"
PROGRAM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HdsWidevineGoogle.py")
PYTHON = "/usr/bin/python3"
HDD = "/media/hdd"
MONTARI = "/proc/mounts"
LUCRU_INTERN = "/home/root/.cache"       # pe memoria interna: <LUCRU_INTERN>/hds-widevine, sters dupa
LIBER_INTERN_KB = 2560 * 1024            # arhiva (~1,24 GB) plus 1 GB ramas liber (HdsWidevineGoogle.LOC_PESTE_FLASH)


def N_(text):
	return text


# Textul licentei Google, cuvant cu cuvant (Chromium, third_party/widevine/LICENSE): netradus, e textul juridic.
LICENTA_GOOGLE = (
	'Google LLC and its affiliates ("Google") own all legal right, title and interest in and to the content decryption '
	'module software ("Software") and related documentation, including any intellectual property rights in the '
	'Software. You may not use, modify, sell, or otherwise distribute the Software without a separate license '
	'agreement with Google. The Software is not open source software.\n\n'
	'If you are interested in licensing the Software, please contact www.widevine.com')
TEXT_INAINTE = N_("Pentru Netflix și alte servicii cu cont, receptorul are nevoie de modulul Widevine. Modulul este "
	"al Google, nu al nostru: receptorul tău îl descarcă direct de pe serverele Google (aproximativ 1,2 GB pe un stick "
	"sau în memoria receptorului, șterși după, apoi rămân doar 10 MB). HD Satelit nu îl distribuie și nu îl modifică. "
	"Licența Google:")
TEXT_INTREBARE = N_("Accepți licența Google și descarci modulul?")
TEXT_FARA_STICK = N_("Descărcarea are nevoie de 2,5 GB liberi în memoria receptorului sau de un stick USB cu cel puțin "
	"1,5 GB liberi. Pune un stick și încearcă din nou.")
TEXT_INCEPE = N_("Modulul Widevine se descarcă de la Google. Durează câteva minute; poți folosi receptorul între timp.")
TEXT_GATA = N_("Modulul Widevine e instalat (versiunea %s).")
TEXT_EROARE = N_("Modulul Widevine nu s-a putut instala: %s")
TEXT_OCUPAT = N_("Modulul Widevine se descarcă deja.")
TEXT_TITLU = N_("Licența Google pentru modulul Widevine")
TEXT_ACCEPT = N_("Accept")
TEXT_NU_ACCEPT = N_("Nu accept")
MOTIVE = {
	2: N_("Google nu mai oferă imaginea din care se ia modulul."),
	6: N_("loc prea puțin pentru descărcare."),
	7: N_("modulul nu s-a găsit în imaginea Google."),
	8: N_("fișierul primit nu e pentru acest receptor."),
	9: N_("descărcarea s-a întrerupt. Verifică internetul și încearcă din nou."),
}

_stare = {"faza": "nimic", "procent": 0, "mesaj": ""}
_lucru = {"c": None, "rest": b"", "gata": None, "versiune": "", "eroare": None}


def instalat(modul=MODUL):
	return os.path.isfile(modul)


def versiune(manifest=MANIFEST):
	try:
		with open(manifest, "r") as f:
			return str(json.load(f).get("version") or "")
	except (IOError, OSError, ValueError, AttributeError):
		return ""


def textLicenta(traducere=None):
	t = traducere or (lambda s: s)
	return t(TEXT_INAINTE) + "\n\n" + LICENTA_GOOGLE + "\n\n" + t(TEXT_INTREBARE)


def liberKb(dosar):
	try:
		s = os.statvfs(dosar)
		return s.f_bavail * s.f_frsize // 1024
	except (OSError, AttributeError):
		return 0


def mediu(montari=MONTARI, hdd=HDD, intern=LUCRU_INTERN, liber=None):
	"""Locul arhivei: memoria interna cand are LIBER_INTERN_KB liberi, altfel hdd daca e montat, altfel primul stick
	USB (/media/usb...); None fara loc."""
	if liber is None:
		liber = liberKb(os.path.dirname(intern))
	if liber >= LIBER_INTERN_KB:
		try:
			if not os.path.isdir(intern):
				os.makedirs(intern)
			return intern
		except OSError:
			pass
	parinte = hdd.rsplit("/", 1)[0] + "/"
	alt = None
	try:
		with open(montari, "r") as f:
			randuri = f.read().splitlines()
	except (IOError, OSError):
		return None
	for r in randuri:
		c = r.split()
		if len(c) < 2:
			continue
		if c[1] == hdd and c[0].startswith("/dev/"):
			return hdd
		if alt is None and c[1].startswith(parinte + "usb") and "/" not in c[1][len(parinte):] and \
				(c[0].startswith("/dev/sd") or (c[0].startswith("/dev/mmcblk") and not c[0].startswith("/dev/mmcblk0"))):
			alt = c[1]
	return alt


def argumente(dosar, program=PROGRAM, python=PYTHON):
	"""Linia de comanda (pentru eConsoleAppContainer.execute: programul, apoi argv cu argv[0])."""
	return (python, "python3", program, "--instaleaza", "--accept-licenta", "--dosar", dosar, "--tinta", DOSAR)


def citesteRand(rand):
	"""Un rand al programului -> schimba _stare; intoarce ("gata", versiune), ("eroare", cod, text) sau None."""
	rand = rand.strip()
	if rand.startswith("PROCENT "):
		try:
			_stare["procent"] = max(0, min(100, int(rand[8:])))
		except ValueError:
			pass
	elif rand.startswith("STARE "):
		_stare["mesaj"] = rand[6:]
	elif rand.startswith("GATA"):
		return ("gata", rand[4:].strip())
	elif rand.startswith("EROARE "):
		p = rand[7:].split(" ", 1)
		try:
			cod = int(p[0])
		except ValueError:
			cod = 0
		return ("eroare", cod, p[1] if len(p) > 1 else "")
	return None


def _date(data):
	if isinstance(data, str):
		data = data.encode("utf-8", "replace")
	tot = _lucru["rest"] + data
	randuri = tot.split(b"\n")
	_lucru["rest"] = randuri.pop()
	for r in randuri:
		rez = citesteRand(r.decode("utf-8", "replace"))
		if rez and rez[0] == "gata":
			_lucru["versiune"] = rez[1]
		elif rez and rez[0] == "eroare":
			_lucru["eroare"] = rez


def textEroare(eroare, traducere=None):
	t = traducere or (lambda s: s)
	cod, detaliu = eroare[1], eroare[2]
	return t(TEXT_EROARE) % (t(MOTIVE[cod]) if cod in MOTIVE else detaliu)


def _sfarsit(cod):
	tr = _tr()
	gata = _lucru["gata"]
	_lucru["c"] = None
	if cod == 0 and instalat():
		_stare.update(faza="gata", procent=100, mesaj=tr(TEXT_GATA) % (_lucru["versiune"] or versiune() or "?"))
		ok = True
	else:
		e = _lucru["eroare"] or ("eroare", cod, "cod %s" % cod)
		_stare.update(faza="eroare", mesaj=textEroare(e, tr))
		ok = False
	if gata:
		try:
			gata(ok, _stare["mesaj"])
		except Exception as e:
			print("[HdsWidevine] gata: %r" % (e,))


def _tr():
	try:
		return _
	except NameError:
		return lambda s: s


def stare():
	return dict(_stare)


def pornesteDescarcarea(accept, gata=None, dosar=None):
	"""Fara ecran: porneste programul daca omul a acceptat licenta. Intoarce (True, "") sau (False, motivul)."""
	tr = _tr()
	if not accept:
		return False, ""
	if _lucru["c"] is not None:
		return False, tr(TEXT_OCUPAT)
	dosar = dosar or mediu()
	if not dosar:
		return False, tr(TEXT_FARA_STICK)
	from enigma import eConsoleAppContainer
	c = eConsoleAppContainer()
	_lucru.update(c=c, rest=b"", gata=gata, versiune="", eroare=None)
	_stare.update(faza="lucreaza", procent=0, mesaj=tr(TEXT_INCEPE))
	c.dataAvail.append(_date)
	c.appClosed.append(_sfarsit)
	if c.execute(*argumente(dosar)):
		_lucru["c"] = None
		_stare.update(faza="eroare", mesaj=tr(TEXT_EROARE) % "python3")
		return False, _stare["mesaj"]
	return True, ""


def instaleaza(session, gata=None):
	"""Ecranul: licenta Google si intrebarea (implicit „Nu accept”), apoi descarcarea in fundal si un mesaj la sfarsit."""
	from Screens.MessageBox import MessageBox
	tr = _tr()

	def laSfarsit(ok, text):
		try:
			from Tools import Notifications
			Notifications.AddNotification(MessageBox, text, type=MessageBox.TYPE_INFO if ok else MessageBox.TYPE_ERROR,
				timeout=15)
		except Exception as e:
			print("[HdsWidevine] mesajul de la sfarsit: %r" % (e,))
		if gata:
			gata(ok, text)

	def raspuns(da):
		if not da:
			if gata:
				gata(False, "")
			return
		ok, motiv = pornesteDescarcarea(True, laSfarsit)
		if ok:
			session.open(MessageBox, tr(TEXT_INCEPE), type=MessageBox.TYPE_INFO, timeout=8)
		else:
			session.open(MessageBox, motiv, type=MessageBox.TYPE_INFO, timeout=15)
			if gata:
				gata(False, motiv)

	# butoanele: „Nu accept” primul (ales cand se deschide), „Accept” al doilea; EXIT = nu accept
	session.openWithCallback(raspuns, MessageBox, textLicenta(tr), type=MessageBox.TYPE_YESNO,
		list=[(tr(TEXT_NU_ACCEPT), False), (tr(TEXT_ACCEPT), True)], title=tr(TEXT_TITLU))

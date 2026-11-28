# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsBaraPornire.py (0.8.x, BOOT1; Eduard 27.11.2026 16:35): bara de incarcare de pe ecranul de pornire. Pe poza de
# pornire, jos, deasupra randului cu versiunea: „Tema s-a încărcat” (pasul gata), „Se încarcă lista de canale” (pasul
# de acum), procentul si o bara orizontala care merge lin pana apare interfata, ca omul sa vada ca receptorul lucreaza
# si cat mai are.
#
# Cine deseneaza: un ajutor mic, acest fisier rulat ca program (python3 -I -S -B HdsBaraPornire.py porneste ...), cu
# prioritate mica, scrie de-a dreptul in /dev/fb0 (OSD-ul, peste poza pusa de showiframe pe stratul video). Bucla
# principala a interfetei nu merge in timpul pornirii (firul principal e ocupat cu importurile, uneori 9-12 s fara
# niciun pas), deci bara nu poate fi miscata din enigma2; ajutorul o misca dupa ceas, de cateva ori pe secunda.
#
# De unde vine procentul: din pornirea trecuta a aceluiasi receptor. Ajutorul tine minte cand a vazut fiecare pas
# (scripturile de pornire din /etc/rc?.d, pornirea enigma2, apoi fiecare profile() din Tools/Profile.py) si le scrie
# la sfarsit in /etc/enigma2/hds-bara-pornire.timpi. La pornirea urmatoare, pasul vazut acum spune unde suntem pe drumul
# masurat data trecuta; intre doi pasi bara inainteaza dupa ceas, dar nu trece de pasul urmator pana nu vine el. La prima
# pornire (fara fisier) se folosesc timpii masurati pe un ZGEMMA H8.2H Plus (TIMPI_IMPLICITI). Bara nu da inapoi.
#
# Doua feluri de pornire:
#   - „boot”: pornit din /etc/rcS.d (stratul, hds-bara-pornire), de la cateva secunde dupa nucleu; acopera montarile,
#     reteaua, softcam-ul si interfata. Procentul e din tot drumul (randurile B din fisierul de timpi).
#   - „interfata”: pornit din enigma2.sh cand nu ruleaza deja (repornirea interfetei); acopera numai enigma2 (randurile I).
#
# Cum se impart OSD-ul ajutorul si enigma2 (nimic nu se scrie in OSD cand enigma2 il schimba):
#   - fisierul pauza din /run/hds-bara-pornire: cat exista, ajutorul nu deseneaza; fiecare cadru se scrie tinand zavorul
#     lock, iar pauza se verifica sub zavor. Cine pune pauza ia apoi zavorul o data: dupa asta, ajutorul nu mai scrie.
#   - enigma2.sh pune pauza inainte de enigma2 (gFBDC schimba modul si sterge OSD-ul la pornire); Profile.py o scoate la
#     PYTHON_START. mytest.py o pune in jurul lui skin.loadSkinData (alt mod al OSD-ului) si o scoate dupa.
#   - la iesirea din pauza ajutorul redeschide /dev/fb0 si citeste din nou modul (alta latime, alt pas al randurilor).
#   - inainte de runReactor, opreste() trimite SIGTERM si asteapta: ajutorul pune la loc locul barei pe toate paginile si
#     iese; abia apoi bucla principala deseneaza primul ecran. Daca nu iese in 1 s, SIGKILL.
#
# Textele: ajutorul nu importa PIL (2,3 s de procesor la pornire pe un ARM lent). Le deseneaza o data, dupa pornire,
# un proces separat cu prioritate minima (pregateste), in limba receptorului (config.osd.language din setari, catalogul
# gettext al imaginii, apoi engleza), cu HdsRegular, pentru trei moduri ale OSD-ului (1920x1080, 1280x720, 720x576);
# le scrie comprimate in /etc/enigma2/hds-bara-pornire.texte. Pana atunci (prima pornire dupa scriere) se folosesc cele
# din imagine (/usr/share/enigma2/hds-bara-pornire/<ro|en>.texte, facute la constructie cu acelasi cod).
#
# Pe PC: HDS_BARA_FB (fisier obisnuit) + HDS_BARA_FB_MOD (ex. 1920x1080) deseneaza intr-un fisier in loc de /dev/fb0;
# HDS_BARA_RUN, HDS_BARA_PROC, HDS_BARA_TIMPI, HDS_BARA_TEXTE, HDS_BARA_SETARI, HDS_BARA_FONT, HDS_BARA_PO schimba
# caile. Vezi BOOT1/proba/proba_pc.py.
#
# Ca modul in enigma2 (pas, pauza, continua, opreste) nu importa nimic greu si nu arunca.

import os
import struct
import sys
import time

DIR = os.environ.get("HDS_BARA_RUN", "/run/hds-bara-pornire")
FB = os.environ.get("HDS_BARA_FB", "/dev/fb0")
FB_MOD = os.environ.get("HDS_BARA_FB_MOD", "")          # numai pe PC: „1920x1080” (fisier in loc de /dev/fb0)
PROC = os.environ.get("HDS_BARA_PROC", "/proc")
TIMPI = os.environ.get("HDS_BARA_TIMPI", "/etc/enigma2/hds-bara-pornire.timpi")
TEXTE = os.environ.get("HDS_BARA_TEXTE", "/etc/enigma2/hds-bara-pornire.texte")
TEXTE_IMAGINE = os.environ.get("HDS_BARA_TEXTE_IMAGINE", "/usr/share/enigma2/hds-bara-pornire")
SETARI = os.environ.get("HDS_BARA_SETARI", "/etc/enigma2/settings")
DOSAR_PO = os.environ.get("HDS_BARA_PO", "/usr/share/enigma2/po")
OPRITA = "/etc/enigma2/hds-bara-pornire.oprita"         # daca exista, enigma2.sh si scriptul de pornire nu o pornesc
FONTURI = tuple(p for p in (os.environ.get("HDS_BARA_FONT", ""), "/usr/share/fonts/HdsRegular.ttf",
	"/usr/share/enigma2/HDSatelit/fonts/HdsRegular.ttf") if p)

# schimbat cand se schimba textele, marimile sau asezarea lor: fisierul de texte se face din nou
VERSIUNE_TEXTE = 1
ANTET_TEXTE = b"HDSBARA1\n"


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce in pregateste()."""
	return text


# Pasii pe care ii vede omul: cheia, textul de acum, textul de dupa (romana = cheia gettext), apoi engleza (rezerva cand
# limba nu are inca traducere). Ordinea nu conteaza: pasul il alege ce se vede pe receptor.
# TRANSLATORS: textele barei de pe ecranul de pornire, pana apare interfata (scurte: incap pe un rand de ~40 de litere)
PASI = (
	("drivere", N_("Se încarcă driverele plăcii"), N_("Driverele s-au încărcat"), "Loading the board drivers", "Drivers loaded"),
	("discuri", N_("Se pregătesc memoria și discurile"), N_("Memoria și discurile sunt gata"), "Preparing the memory and disks", "Memory and disks ready"),
	("servicii", N_("Se pornesc serviciile sistemului"), N_("Serviciile sistemului au pornit"), "Starting the system services", "System services started"),
	("retea", N_("Se pornește rețeaua"), N_("Rețeaua a pornit"), "Starting the network", "Network started"),
	("softcam", N_("Se pornește softcam-ul"), N_("Softcam-ul a pornit"), "Starting the softcam", "Softcam started"),
	("interfata", N_("Se pornește interfața"), N_("Interfața a pornit"), "Starting the interface", "Interface started"),
	("limba", N_("Se încarcă limba"), N_("Limba s-a încărcat"), "Loading the language", "Language loaded"),
	("tema", N_("Se încarcă tema"), N_("Tema s-a încărcat"), "Loading the skin", "Skin loaded"),
	("tuner", N_("Se pornește tunerul"), N_("Tunerul a pornit"), "Starting the tuner", "Tuner started"),
	("canale", N_("Se încarcă lista de canale"), N_("Lista de canale s-a încărcat"), "Loading the channel list", "Channel list loaded"),
	("setari", N_("Se încarcă setările"), N_("Setările s-au încărcat"), "Loading the settings", "Settings loaded"),
	("web", N_("Se pornește interfața web"), N_("Interfața web a pornit"), "Starting the web interface", "Web interface started"),
	("module", N_("Se încarcă modulele interfeței"), N_("Modulele interfeței s-au încărcat"), "Loading the interface modules", "Interface modules loaded"),
	("ecran", N_("Se pregătește ecranul"), N_("Ecranul este gata"), "Preparing the screen", "Screen ready"),
	("telecomanda", N_("Se pregătește telecomanda"), N_("Telecomanda este gata"), "Preparing the remote control", "Remote control ready"),
	("video", N_("Se reglează ieșirea video"), N_("Ieșirea video este reglată"), "Setting up the video output", "Video output set up"),
	("dispozitive", N_("Se pregătesc dispozitivele"), N_("Dispozitivele sunt gata"), "Preparing the devices", "Devices ready"),
	("pluginuri", N_("Se pornesc pluginurile"), N_("Pluginurile au pornit"), "Starting the plugins", "Plugins started"),
	("sesiune", N_("Se deschide ecranul principal"), N_("Ecranul principal este gata"), "Opening the main screen", "Main screen ready"),
	("final", N_("Se pornesc funcțiile HD Satelit"), N_("Funcțiile HD Satelit au pornit"), "Starting the HD Satelit features", "HD Satelit features started"),
)
CHEI_PASI = tuple(p[0] for p in PASI)

# scripturile de pornire (/etc/rcS.d, /etc/rc3.d, /etc/rc5.d): o bucata din nume -> pasul
SCRIPTURI = (
	("modutils", "drivere"), ("modload", "drivere"), ("udev", "drivere"), ("hotplug", "drivere"),
	("alignment", "drivere"), ("sysfs", "drivere"), ("alsa", "drivere"),
	("mountall", "discuri"), ("checkroot", "discuri"), ("partitions", "discuri"), ("volatile", "discuri"),
	("read-only", "discuri"), ("hds-noduri", "discuri"), ("bootmisc", "discuri"), ("fuse", "discuri"),
	("networking", "retea"), ("netguard", "retea"), ("ipv6", "retea"), ("dropbear", "retea"), ("hds-ssh", "retea"),
	("avahi", "retea"), ("nume-local", "retea"), ("openvpn", "retea"), ("mountnfs", "retea"), ("vsftpd", "retea"),
	("softcam", "softcam"), ("cardserver", "softcam"),
)
SCRIPT_ALTUL = "servicii"

# profile() din enigma2 -> pasul (cele care nu sunt aici pastreaza pasul de dinainte)
PROFILE = {
	"PYTHON_START": "limba", "LANGUAGE": "module",
	"LOAD:InfoBar": "tema", "LOAD:GUISkin": "tema", "LOAD:ElementTree": "tema", "LOAD:enigma_skin": "tema",
	"LoadSkin": "tema", "LoadSkinDefault": "tema", "LoadSkinDefaultDone": "module", "LOAD:InfoBarGenerics": "module",
	"ChannelSelection.py 1": "canale", "ChannelSelection.py 2": "tuner", "ChannelSelection.py 2.1": "canale",
	"Bouquets": "canale", "ParentalControl": "setari", "LOAD:Navigation": "setari", "config.misc": "setari",
	"Twisted": "web", "LOAD:Plugin": "module", "Init:skin": "ecran", "InputDevice": "telecomanda",
	"AVSwitch": "video", "RecordingConfig": "setari", "Network": "retea", "LCD": "dispozitive",
	"readPluginList": "pluginuri", "Init:Session": "sesiune", "wizards": "final",
}
CAPAT = "RunReactor"

# masurat pe ZGEMMA H8.2H Plus (.129), 27.11.2026: pornirea placii 14:57 (scripturile) si repornirea interfetei 16:37
# (/etc/enigma2/profile); secunde de la pornirea nucleului
_PY = (("PYTHON_START", 0.0), ("LANGUAGE", 0.1), ("LOAD:InfoBar", 3.3), ("LoadSkin", 3.6), ("LoadSkinDefaultDone", 4.5),
	("ChannelSelection.py 1", 5.2), ("ChannelSelection.py 2", 6.0), ("ChannelSelection.py 2.1", 7.9), ("Bouquets", 8.5),
	("ParentalControl", 8.5), ("Twisted", 8.6), ("LOAD:Plugin", 12.6), ("Init:skin", 12.8), ("InputDevice", 13.1),
	("AVSwitch", 13.2), ("RecordingConfig", 13.7), ("Network", 14.5), ("LCD", 14.5), ("readPluginList", 16.2),
	("Init:Session", 17.7), ("wizards", 26.6), (CAPAT, 38.6))
TIMPI_IMPLICITI = {
	"B": [(9.0, "start"), (10.0, "rc:discuri"), (17.0, "rc:servicii"), (19.5, "rc:retea"), (41.0, "rc:softcam"),
		(44.0, "e2")] + [(44.7 + t, i) for i, t in _PY],
	# repornirea interfetei: enigma2.sh porneste ajutorul la inceput („sh”); pana la enigma2 („e2”) trec ~10 s
	# (oprirea celui vechi, sigla, paza modelului), masurat pe .129 la 17:09
	"I": [(0.0, "sh"), (10.5, "e2")] + [(11.2 + t, i) for i, t in _PY],
}

# asezarea, pe 1920x1080 (se micsoreaza la modul OSD-ului: latimea cu xres/1920, inaltimea cu yres/1080); semnatura
# (lib/gdi/ecranpornire.cpp) sta de la 984 la 1040, textul din colt tot acolo. Eduard 27.11 17:15: mai sus, nu lipit
# de randul cu versiunea si de cutia din dreapta jos: panoul se termina la 888, cu 96 de pixeli liberi pana la ele
PANOU = (500, 760, 920, 128)        # x, y, latime, inaltime
PANOU_RAZA = 20
PANOU_CULOARE = (10, 14, 26)        # ca semnatura
PANOU_OPAC = 176
MARGINE = 40
GATA_Y, GATA_FONT, GATA_H = 14, 22, 30
ACUM_Y, ACUM_FONT, ACUM_H = 44, 28, 38
BARA_Y, BARA_H = 96, 12
LATIME_PROCENT = 110                # locul procentului, la dreapta randului de acum
TEXT_ACUM = (240, 246, 252)
TEXT_GATA = (150, 196, 236)
BARA_FOND = (60, 72, 96)
BARA_PLIN = (80, 190, 255)          # albastru deschis, ca sigla
MODURI_TEXTE = ((1920, 1080), (1280, 720), (720, 576))

PERIOADA = 0.2                      # secunde intre doua cadre
TERMEN = 300.0                      # dupa atatea secunde ajutorul pleaca singur


def _jurnal(text):
	print("[HdsBaraPornire] %s" % text)


def ceas():
	"""Secunde de la pornirea nucleului (ca /proc/uptime), la fel in ajutor, in enigma2 si in enigma2.sh."""
	try:
		return time.clock_gettime(time.CLOCK_BOOTTIME)
	except (AttributeError, OSError):
		return time.monotonic()


# ---------------------------------------------------------------- in enigma2 (Tools/Profile.py, mytest.py)

def _scrie(nume, text, adauga=False):
	try:
		with open(os.path.join(DIR, nume), "a" if adauga else "w") as f:
			f.write(text)
		return True
	except (OSError, IOError):
		return False


def _sterge(nume):
	try:
		os.unlink(os.path.join(DIR, nume))
	except OSError:
		pass


def _generatie():
	"""Generatia OSD-ului: o scriu pauza() si enigma2.sh de fiecare data cand OSD-ul poate fi schimbat."""
	try:
		with open(os.path.join(DIR, "gen")) as f:
			return f.read()
	except (OSError, IOError):
		return ""


def _pidAjutor():
	try:
		with open(os.path.join(DIR, "pid")) as f:
			pid = int(f.read().strip() or 0)
	except (OSError, IOError, ValueError):
		return 0
	return pid if pid > 1 and os.path.exists("%s/%d" % (PROC, pid)) else 0


def pas(ident):
	"""Din Tools/Profile.profile(): pasul ajunge la ajutor. La PYTHON_START enigma2 a terminat cu modul OSD-ului de
	pornire, deci ajutorul poate desena din nou. Nu arunca; fara ajutor nu face nimic."""
	try:
		if not os.path.isdir(DIR):
			return
		_scrie("pasi", "%.2f %s\n" % (ceas(), ident.replace("\n", " ")), True)
		if ident == "PYTHON_START":
			_sterge("pauza")
	except Exception:
		pass


def _iaZavorul(termen=0.5):
	"""Pauza e pusa; asteapta cadrul inceput (zavorul lock). True daca dupa asta ajutorul nu mai scrie."""
	import fcntl
	try:
		fd = os.open(os.path.join(DIR, "lock"), os.O_CREAT | os.O_RDWR, 0o600)
	except OSError:
		return True
	try:
		sfarsit = time.monotonic() + termen
		while True:
			try:
				fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
				fcntl.flock(fd, fcntl.LOCK_UN)
				return True
			except (OSError, IOError):
				if time.monotonic() >= sfarsit:
					return False
				time.sleep(0.01)
	finally:
		os.close(fd)


def pauza():
	"""Inainte de skin.loadSkinData (alt mod al OSD-ului): ajutorul nu mai scrie pana la continua(). Nu arunca."""
	try:
		if not _pidAjutor():
			return
		_scrie("pauza", "")
		_scrie("gen", "%.3f\n" % ceas())
		if not _iaZavorul():
			_jurnal("zavorul nu s-a eliberat; ajutorul se opreste")
			_omoara()
	except Exception as eroare:
		_jurnal("pauza: %s" % eroare)


def continua():
	"""Dupa skin.loadSkinData: ajutorul redeschide OSD-ul, citeste modul nou si deseneaza din nou. Nu arunca."""
	try:
		_sterge("pauza")
	except Exception:
		pass


def _omoara():
	import signal
	pid = _pidAjutor()
	if pid:
		try:
			os.kill(pid, signal.SIGKILL)
		except OSError:
			pass


def opreste(termen=1.0):
	"""Inainte de runReactor: ajutorul pune la loc locul barei si iese, inainte ca bucla sa deseneze primul ecran.
	Asteapta cel mult termen secunde, apoi SIGKILL. Nu arunca."""
	import signal
	try:
		pid = _pidAjutor()
		if not pid:
			return
		os.kill(pid, signal.SIGTERM)
		sfarsit = time.monotonic() + termen
		while os.path.exists("%s/%d" % (PROC, pid)):
			try:
				with open("%s/%d/stat" % (PROC, pid)) as f:
					if f.read().rsplit(")", 1)[-1].split()[0] == "Z":
						break
			except (OSError, IOError, IndexError):
				break
			if time.monotonic() >= sfarsit:
				_jurnal("ajutorul nu a iesit in %.1f s: SIGKILL" % termen)
				os.kill(pid, signal.SIGKILL)
				break
			time.sleep(0.01)
	except Exception as eroare:
		_jurnal("oprire: %s" % eroare)


# ---------------------------------------------------------------- timpii

def citesteTimpi(cale=TIMPI):
	"""{"B": [(t, id)], "I": [(t, id)]} din fisierul de timpi; lipsa sau stricat: TIMPI_IMPLICITI."""
	rez = {"B": [], "I": []}
	try:
		with open(cale) as f:
			for rand in f:
				parti = rand.rstrip("\n").split(" ", 2)
				if len(parti) == 3 and parti[0] in rez:
					rez[parti[0]].append((float(parti[1]), parti[2]))
	except (OSError, IOError, ValueError):
		pass
	for fel in rez:
		lista = sorted(rez[fel])
		if not lista or lista[-1][1] != CAPAT or lista[-1][0] <= 0:
			lista = list(TIMPI_IMPLICITI[fel])
		rez[fel] = lista
	return rez


def scrieTimpi(vazute, fel, vechi, cale=TIMPI):
	"""vazute: [(t, id)] din pornirea asta, in ordinea venirii (t = ceas()). Se scrie numai o pornire intreaga (cu
	RunReactor). Felul boot scrie si randurile I (de la e2 incolo); felul interfata pastreaza randurile B vechi."""
	ids = [i for _t, i in vazute]
	if CAPAT not in ids or "e2" not in ids:
		return False
	prima = {}
	for t, i in vazute:
		prima.setdefault(i, t)
	# randurile I de la inceputul lui enigma2.sh („sh”, scris si la pornirea placii), altfel de la „e2”
	t_e2 = prima["sh"] if "sh" in prima and prima["sh"] <= prima["e2"] else prima["e2"]
	randuri_i = sorted((t - t_e2, i) for i, t in prima.items() if t >= t_e2)
	if fel == "boot":
		randuri_b = sorted((t, i) for i, t in prima.items())
	else:
		randuri_b = vechi["B"]
	text = "".join("B %.2f %s\n" % r for r in randuri_b) + "".join("I %.2f %s\n" % r for r in randuri_i)
	try:
		with open(cale + ".nou", "w") as f:
			f.write(text)
		os.rename(cale + ".nou", cale)
		return True
	except (OSError, IOError):
		return False


def _taraie(trecut, interval):
	"""Cat inainteaza bara intre doi pasi: dupa ceas pana la 97% din drumul masurat, apoi tot mai incet, fara sa
	ajunga la pasul urmator."""
	if interval <= 0:
		return 0.0
	prag = 0.97 * interval
	if trecut <= prag:
		return max(0.0, trecut)
	import math
	return prag + 0.025 * interval * (1.0 - math.exp(-(trecut - prag) / (interval + 1.0)))


class Progres(object):
	"""Unde suntem pe drumul masurat data trecuta (0..1) si ce pas vede omul."""

	def __init__(self, referinta, inceput, ident_inceput):
		self.ref = referinta                  # [(t, id)] sortat, ultimul = CAPAT
		self.loc = dict((i, t) for t, i in referinta)
		self.total = referinta[-1][0] or 1.0
		self.ancora = (self.loc.get(ident_inceput, 0.0), inceput)
		self.arata = 0.0
		self.gata = False

	def vazut(self, ident, t):
		if ident == CAPAT:
			self.gata = True
		r = self.loc.get(ident)
		if r is not None and r >= self.ancora[0]:
			self.ancora = (r, t)

	def fractie(self, acum):
		if self.gata:
			self.arata = 1.0
			return 1.0
		r_c, s_c = self.ancora
		urm = [t for t, _i in self.ref if t > r_c]
		interval = (urm[0] - r_c) if urm else 0.0
		est = r_c + _taraie(acum - s_c, interval)
		self.arata = max(self.arata, min(0.99, est / self.total))
		return self.arata


def pasulScriptului(nume):
	for bucata, cheie in SCRIPTURI:
		if bucata in nume:
			return cheie
	return SCRIPT_ALTUL


# ---------------------------------------------------------------- textele

def limbaSetari(cale=SETARI):
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


def textele(limba):
	"""{cheie: (acum, gata)} in limba data: romana = textele din PASI; altfel catalogul gettext al limbii, apoi engleza."""
	if (limba or "ro_RO").split("_")[0].lower() == "ro":
		return dict((p[0], (p[1], p[2])) for p in PASI)
	import gettext
	try:
		tr = gettext.translation("enigma2", DOSAR_PO, languages=[limba], fallback=True).gettext
	except Exception:
		tr = lambda t: t
	rez = {}
	for cheie, acum, gata, en_acum, en_gata in PASI:
		a, g = tr(acum), tr(gata)
		rez[cheie] = (a if a != acum else en_acum, g if g != gata else en_gata)
	return rez


def cheieTexte(limba, font):
	try:
		st = os.stat(font)
		semn = "%d-%d" % (st.st_size, int(st.st_mtime))
	except OSError:
		semn = "0"
	return "%d|%s|%s|%s" % (VERSIUNE_TEXTE, limba or "ro_RO", os.path.basename(font), semn)


def _fontBun():
	for cale in FONTURI:
		try:
			if os.path.getsize(cale) > 10 * 1024:
				return cale
		except OSError:
			pass
	return ""


def deseneazaTexte(limba, font, cale_iesire):
	"""Cu PIL: fiecare text (acum si gata) si cifrele procentului, ca masti de alfa (un octet pe pixel), pentru fiecare
	mod din MODURI_TEXTE. Textul prea lung se scrie cu litere mai mici pana incape."""
	import json
	import zlib
	from PIL import Image, ImageDraw, ImageFont
	tex = textele(limba)
	date = bytearray()
	seturi = {}
	cache_font = {}

	def fnt(marime):
		if marime not in cache_font:
			cache_font[marime] = ImageFont.truetype(font, marime)
		return cache_font[marime]

	def masca(text, marime, inaltime, latime_max, sx, sy):
		# se deseneaza la 1920x1080 si se micsoreaza la mod (pe 720x576 literele se strang pe orizontala ca OSD-ul)
		m = marime
		while True:
			f = fnt(m)
			latime = int(f.getlength(text)) + 2
			if latime <= latime_max or m <= 12:
				break
			m -= 1
		asc, desc = f.getmetrics()
		img = Image.new("L", (max(1, min(latime, latime_max)), inaltime), 0)
		ImageDraw.Draw(img).text((1, (inaltime - (asc + desc)) // 2), text, font=f, fill=255)
		w = max(1, int(round(img.size[0] * sx)))
		h = max(1, int(round(img.size[1] * sy)))
		if (w, h) != img.size:
			img = img.resize((w, h), Image.LANCZOS)
		return img.size, img.tobytes()

	def pune(blob):
		poz = len(date)
		date.extend(blob)
		return [poz, len(blob)]

	latime_text = PANOU[2] - 2 * MARGINE
	for mx, my in MODURI_TEXTE:
		sx, sy = mx / 1920.0, my / 1080.0
		s = {"texte": {}, "cifre": {}}
		for cheie, (acum, gata) in tex.items():
			(w, h), b = masca(acum, ACUM_FONT, ACUM_H, latime_text - LATIME_PROCENT, sx, sy)
			s["texte"][cheie + "/acum"] = [w, h] + pune(b)
			(w, h), b = masca(gata, GATA_FONT, GATA_H, latime_text, sx, sy)
			s["texte"][cheie + "/gata"] = [w, h] + pune(b)
		for c in "0123456789%":
			(w, h), b = masca(c, ACUM_FONT, ACUM_H, 200, sx, sy)
			s["cifre"][c] = [w, h] + pune(b)
		seturi["%dx%d" % (mx, my)] = s
	antet = {"cheie": cheieTexte(limba, font), "limba": limba, "seturi": seturi}
	tot = ANTET_TEXTE + json.dumps(antet, separators=(",", ":")).encode("ascii") + b"\n" + zlib.compress(bytes(date), 9)
	with open(cale_iesire + ".nou", "wb") as f:
		f.write(tot)
	os.rename(cale_iesire + ".nou", cale_iesire)
	return len(tot)


def citesteTexte(cale):
	"""(antet, date) din fisierul de texte, sau None."""
	import json
	import zlib
	try:
		with open(cale, "rb") as f:
			tot = f.read(8 * 1024 * 1024)
		if not tot.startswith(ANTET_TEXTE):
			return None
		rest = tot[len(ANTET_TEXTE):]
		capat = rest.index(b"\n")
		antet = json.loads(rest[:capat].decode("ascii"))
		return antet, zlib.decompress(rest[capat + 1:])
	except Exception:
		return None


def textePentruPornire(limba):
	"""Fisierul facut pe receptor; altfel cel din imagine, in romana sau engleza."""
	t = citesteTexte(TEXTE)
	if t:
		return t
	ro = (limba or "ro_RO").split("_")[0].lower() == "ro"
	for nume in (("ro", "en") if ro else ("en", "ro")):
		t = citesteTexte(os.path.join(TEXTE_IMAGINE, nume + ".texte"))
		if t:
			return t
	return None


# ---------------------------------------------------------------- desenul (in ajutor)

def _interclaseaza(masca, tb, tg, tr, ta):
	"""Masca de alfa -> pixeli ARGB8888 (B, G, R, A in memorie) prin patru tabele de 256 de octeti."""
	out = bytearray(4 * len(masca))
	out[0::4] = masca.translate(tb)
	out[1::4] = masca.translate(tg)
	out[2::4] = masca.translate(tr)
	out[3::4] = masca.translate(ta)
	return out


def _tabele(fond, fond_alfa, culoare, opac=255):
	"""Tabelele pentru o culoare peste fondul panoului (amestec ne-premultiplicat, cum scrie si enigma2 in OSD)."""
	tb, tg, tr, ta = bytearray(256), bytearray(256), bytearray(256), bytearray(256)
	for m in range(256):
		at = m * opac / 255.0 / 255.0
		ap = fond_alfa / 255.0
		ao = at + ap * (1.0 - at)
		if ao <= 0:
			c = fond
		else:
			c = tuple((culoare[k] * at + fond[k] * ap * (1.0 - at)) / ao for k in range(3))
		tr[m], tg[m], tb[m] = int(c[0] + 0.5), int(c[1] + 0.5), int(c[2] + 0.5)
		ta[m] = int(ao * 255 + 0.5)
	return bytes(tb), bytes(tg), bytes(tr), bytes(ta)


def _acoperire(x, y, w, h, r):
	"""Cat din pixel cade in dreptunghiul rotunjit (0..1), ca acoperire_capsula din ecranpornire.cpp."""
	cx = r if x < r else (w - r - 1 if x >= w - r else x)
	cy = r if y < r else (h - r - 1 if y >= h - r else y)
	if cx == x or cy == y:
		return 1.0
	dx, dy = x - cx, y - cy
	a = r - (dx * dx + dy * dy) ** 0.5 + 0.5
	return 0.0 if a <= 0 else (1.0 if a >= 1 else a)


def _mascaRotunjita(w, h, r):
	"""Masca de alfa 0..255 a unui dreptunghi rotunjit, rand cu rand (colturile calculate, mijlocul copiat)."""
	r = max(0, min(r, w // 2, h // 2))
	plin = b"\xff" * w
	out = bytearray()
	for y in range(h):
		if r <= y < h - r:
			out += plin
			continue
		stanga = bytes(int(255 * _acoperire(x, y, w, h, r) + 0.5) for x in range(r))
		dreapta = bytes(int(255 * _acoperire(x, y, w, h, r) + 0.5) for x in range(w - r, w))
		out += stanga + b"\xff" * (w - 2 * r) + dreapta
	return out


class Ecran(object):
	"""/dev/fb0 deschis, cu modul citit; desenul panoului pe pagina vazuta. Pe PC: un fisier si HDS_BARA_FB_MOD."""

	def __init__(self):
		import mmap
		self.fd = -1
		self.mm = None
		self.bun = False
		self.e_device = not FB_MOD
		self.blit_bun = False
		self.fd = os.open(FB, os.O_RDWR)
		if FB_MOD:
			mod = FB_MOD
			if mod.startswith("@"):                                  # proba: modul se schimba din fisier
				with open(mod[1:]) as f:
					mod = f.read().strip()
			x, y = (int(v) for v in mod.split("x")[:2])
			self.xres, self.yres, self.yoff = x, y, 0
			self.pas_rand = x * 4
			self.pagini = 1
			lungime = os.fstat(self.fd).st_size
			if lungime < self.pas_rand * y:
				os.ftruncate(self.fd, self.pas_rand * y)
				lungime = self.pas_rand * y
		else:
			import fcntl
			var = bytearray(160)
			fcntl.ioctl(self.fd, 0x4600, var, True)                  # FBIOGET_VSCREENINFO
			v = struct.unpack_from("=8I12I", var, 0)
			self.xres, self.yres, _xv, yv, _xo, self.yoff, bpp = v[:7]
			culori = v[8:20]
			fix = bytearray(80)
			fcntl.ioctl(self.fd, 0x4602, fix, True)                  # FBIOGET_FSCREENINFO
			lungime = struct.unpack_from("@LI", fix, 16)[1]
			# FBIO_BLIT (0x22) NU se mai da: pe HiSilicon (hifb) 0x22 e alta comanda a driverului; data de ajutor la
			# fiecare cadru, pe .129 sigla de pe stratul video a disparut (Eduard 27.11 17:15). Pe placile cu blit manual
			# (Broadcom, Dreambox) bara se vede la urmatorul blit al lui enigma2; de probat acolo inainte de a-l porni
			# pe numele driverului (fix.id).
			self.blit_bun = False
			self.pas_rand = struct.unpack_from("@I", fix, 44)[0]
			# numai ARGB8888 (rosu 16, verde 8, albastru 0, alfa 24): asa scrie si enigma2; altfel nu desenam
			if bpp != 32 or culori != (16, 8, 0, 8, 8, 0, 0, 8, 0, 24, 8, 0) or self.xres < 320 or self.yres < 240:
				return
			self.pagini = max(1, yv // self.yres)
			if self.pas_rand < self.xres * 4 or self.pas_rand * yv > lungime:
				return
		self.mm = mmap.mmap(self.fd, lungime, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
		self.lungime = lungime
		sx, sy = self.xres / 1920.0, self.yres / 1080.0
		self.sx, self.sy = sx, sy
		px, py, pw, ph = PANOU
		self.x, self.y = int(round(px * sx)), int(round(py * sy))
		self.w, self.h = max(8, int(round(pw * sx))), max(8, int(round(ph * sy)))
		if self.x + self.w > self.xres or self.y + self.h > self.yres:
			return
		self.salvat = None
		self.bun = True

	def inchide(self):
		try:
			if self.mm is not None:
				self.mm.close()
		except Exception:
			pass
		try:
			if self.fd >= 0:
				os.close(self.fd)
		except OSError:
			pass
		self.mm, self.fd, self.bun = None, -1, False

	def _pagina_vazuta(self):
		if not self.e_device:
			return 0
		try:
			import fcntl
			var = bytearray(160)
			fcntl.ioctl(self.fd, 0x4600, var, True)
			v = struct.unpack_from("=8I", var, 0)
			if (v[0], v[1]) != (self.xres, self.yres):
				return -1                                            # alt mod: cineva l-a schimbat
			return v[5] // self.yres
		except (OSError, IOError):
			return -1

	def _locuri(self, pagina):
		return [((pagina * self.yres + self.y + r) * self.pas_rand + self.x * 4) for r in range(self.h)]

	def scrie(self, randuri):
		"""randuri: bytearray w*h*4 pe pagina vazuta. False daca modul s-a schimbat (nu se scrie nimic)."""
		pagina = self._pagina_vazuta()
		if pagina < 0 or pagina >= self.pagini:
			return False
		if self.salvat is None:
			# ce era sub panou, pe toate paginile, ca sa se puna la loc la plecare
			self.salvat = [[self.mm[o:o + self.w * 4] for o in self._locuri(p)] for p in range(self.pagini)]
		lat = self.w * 4
		for r, o in enumerate(self._locuri(pagina)):
			self.mm[o:o + lat] = randuri[r * lat:(r + 1) * lat]
		return True

	def scrieParti(self, parti):
		"""Numai bucatile date [(rand, x, octeti)] (bara si procentul) pe pagina vazuta. False daca modul s-a schimbat."""
		pagina = self._pagina_vazuta()
		if pagina < 0 or pagina >= self.pagini or self.salvat is None:
			return False
		for rand, x, b in parti:
			o = (pagina * self.yres + self.y + rand) * self.pas_rand + (self.x + x) * 4
			self.mm[o:o + len(b)] = b
		return True

	def blit(self):
		if self.e_device and self.blit_bun:
			try:
				import fcntl
				fcntl.ioctl(self.fd, 0x22)                               # FBIO_BLIT, numai cand enigma2 a pornit
			except (OSError, IOError):
				pass

	def curata(self):
		"""Tot OSD-ul stravezii (alfa 0), pe toate paginile, numai cand nu ruleaza niciun enigma2 (BOOT2, 27.11.2026).
		La repornirea interfetei in OSD ramane fereastra opaca „Interfața repornește...” (Screens/Standby.py,
		QuitMainloopScreen, #000a0e1a pe tot ecranul): bara desenata peste ea tinea stratul OSD aratat si plin, iar
		sigla de pe stratul video nu se mai vedea („ecran inchis, doar bara”). La pornirea placii la fel, cu ce a lasat
		incarcatorul in OSD. True daca a gasit ceva nestravezii in afara panoului (pentru jurnal)."""
		if not self.bun:
			return False
		lat = self.xres * 4
		gasit = False
		for p in range(self.pagini):
			for r in range(0, self.yres, 8):
				if r >= self.y and r < self.y + self.h:
					continue
				o = (p * self.yres + r) * self.pas_rand
				if self.mm[o + 3:o + lat:4 * 16].strip(b"\0"):
					gasit = True
					break
			if gasit:
				break
		if not gasit:
			return False
		gol = bytes(lat)
		for p in range(self.pagini):
			for r in range(self.yres):
				o = (p * self.yres + r) * self.pas_rand
				self.mm[o:o + lat] = gol
		self.salvat = None
		return True

	def puneLaLoc(self):
		if self.salvat is None or self._pagina_vazuta() < 0:
			return
		lat = self.w * 4
		for p in range(self.pagini):
			for o, b in zip(self._locuri(p), self.salvat[p]):
				self.mm[o:o + lat] = b
		self.salvat = None


class Desen(object):
	"""Panoul pregatit pentru un mod: fondul rotunjit, bara goala si plina, textele si cifrele aduse la pixeli."""

	def __init__(self, ecran, texte):
		self.e = ecran
		sx, sy = ecran.sx, ecran.sy
		w, h = ecran.w, ecran.h
		self.w, self.h = w, h
		self.fond_alfa = PANOU_OPAC
		masca = _mascaRotunjita(w, h, int(round(PANOU_RAZA * min(sx, sy))))
		tb, tg, tr, ta = _tabele(PANOU_CULOARE, 0, PANOU_CULOARE, PANOU_OPAC)
		self.fond = _interclaseaza(masca, tb, tg, tr, ta)
		self.t_acum = _tabele(PANOU_CULOARE, PANOU_OPAC, TEXT_ACUM)
		self.t_gata = _tabele(PANOU_CULOARE, PANOU_OPAC, TEXT_GATA)
		self.mx = int(round(MARGINE * sx))
		self.bx, self.bw = self.mx, w - 2 * self.mx
		self.by, self.bh = int(round(BARA_Y * sy)), max(3, int(round(BARA_H * sy)))
		bara = _mascaRotunjita(self.bw, self.bh, self.bh // 2)
		self.bara_fond = _interclaseaza(bara, *_tabele(PANOU_CULOARE, PANOU_OPAC, BARA_FOND))
		self.bara_plin = _interclaseaza(bara, *_tabele(PANOU_CULOARE, PANOU_OPAC, BARA_PLIN))
		self.gata_y = int(round(GATA_Y * sy))
		self.acum_y = int(round(ACUM_Y * sy))
		self.set = None
		self.date = b""
		if texte:
			antet, self.date = texte
			seturi = antet.get("seturi", {})
			# setul cu modul cel mai apropiat (la acelasi mod, masurile se potrivesc exact)
			alese = sorted(seturi, key=lambda k: abs(int(k.split("x")[0]) - ecran.xres) + abs(int(k.split("x")[1]) - ecran.yres))
			if alese:
				self.set = seturi[alese[0]]
		self.cache = {}

	def _masca(self, intrare):
		w, h, poz, lung = intrare
		return w, h, self.date[poz:poz + lung]

	def _textPixeli(self, cheie, tabele):
		if cheie in self.cache:
			return self.cache[cheie]
		rez = None
		if self.set and cheie in self.set["texte"]:
			w, h, m = self._masca(self.set["texte"][cheie])
			rez = (w, h, _interclaseaza(m, *tabele))
		self.cache[cheie] = rez
		return rez

	def _lipeste(self, tinta, x, y, w, h, pixeli, latime_max=None):
		W = self.w
		w2 = min(w, W - x, latime_max if latime_max is not None else w)
		if w2 <= 0:
			return
		for r in range(h):
			yy = y + r
			if yy < 0 or yy >= self.h:
				continue
			d = (yy * W + x) * 4
			tinta[d:d + w2 * 4] = pixeli[r * w * 4:r * w * 4 + w2 * 4]

	def baza(self, pas_acum, pas_gata):
		"""Panoul cu textele, fara procent si cu bara goala (bytearray w*h*4). Se face din nou numai cand se schimba
		pasul; intre doi pasi se scriu doar bucatile din parti()."""
		c = bytearray(self.fond)
		self.lp = int(round(LATIME_PROCENT * self.e.sx))
		if pas_gata:
			t = self._textPixeli(pas_gata + "/gata", self.t_gata)
			if t:
				self._lipeste(c, self.mx, self.gata_y, t[0], t[1], t[2], self.w - 2 * self.mx)
		if pas_acum:
			t = self._textPixeli(pas_acum + "/acum", self.t_acum)
			if t:
				self._lipeste(c, self.mx, self.acum_y, t[0], t[1], t[2], self.w - 2 * self.mx - self.lp)
		self.c = c
		return c

	def parti(self, fractie):
		"""[(rand, x, octeti)] in panou: randurile barei si locul procentului, peste baza()."""
		c = self.c
		W = self.w
		rez = []
		# procentul, aliniat la dreapta, in locul lui (fondul luat din baza)
		if self.set:
			ah = max(1, int(round(ACUM_H * self.e.sy)))
			x0 = self.w - self.mx - self.lp
			loc = bytearray()
			for r in range(ah):
				d = ((self.acum_y + r) * W + x0) * 4
				loc += c[d:d + self.lp * 4]
			cifre = [self._masca(self.set["cifre"][ch]) for ch in "%d%%" % int(fractie * 100 + 1e-6) if ch in self.set["cifre"]]
			if cifre:
				h = min(ah, max(ci[1] for ci in cifre))
				lat = min(self.lp, sum(ci[0] for ci in cifre))
				rand = bytearray()
				for r in range(h):
					for w, hh, m in cifre:
						rand += m[r * w:(r + 1) * w] if r < hh else b"\x00" * w
				pix = _interclaseaza(bytes(rand), *self.t_acum)
				tot = sum(ci[0] for ci in cifre)
				for r in range(h):
					d = (r * self.lp + self.lp - lat) * 4
					loc[d:d + lat * 4] = pix[(r * tot + tot - lat) * 4:(r * tot + tot) * 4]
			for r in range(ah):
				rez.append((self.acum_y + r, x0, loc[r * self.lp * 4:(r + 1) * self.lp * 4]))
		# bara
		plin = int(round(self.bw * max(0.0, min(1.0, fractie))))
		lat = self.bw * 4
		for r in range(self.bh):
			rez.append((self.by + r, self.bx, self.bara_plin[r * lat:r * lat + plin * 4] + self.bara_fond[r * lat + plin * 4:(r + 1) * lat]))
		return rez

	def cadru(self, fractie, pas_acum, pas_gata):
		"""Panoul intreg (bytearray w*h*4), pentru probe."""
		c = bytearray(self.baza(pas_acum, pas_gata))
		for rand, x, b in self.parti(fractie):
			d = (rand * self.w + x) * 4
			c[d:d + len(b)] = b
		return c


class Ajutor(object):
	"""Bucla ajutorului: citeste pasii, deseneaza cadrele, iese la SIGTERM sau la termen."""

	def __init__(self, fel):
		self.fel = fel
		self.inceput = ceas()
		self.oprit = False
		self.vazute = []                       # [(t, id)] in ordinea venirii
		self.pid_vazute = set()
		self.e2_pid = 0
		self.e2_disparut = 0.0
		self.pasi_poz = 0
		self.pas_acum = None
		self.pas_gata = None
		self.ecran = None
		self.desen = None
		self.texte = None
		self.texte_citite = False
		self.limba = limbaSetari()
		self.timpi = citesteTimpi()
		ref = self.timpi["B" if fel == "boot" else "I"]
		self.progres = Progres(ref, self.inceput, "start" if fel == "boot" else "sh")
		self.ultim = None
		self.e2_pornit = fel != "boot"
		self.blit_voie = False
		if fel == "boot":
			self.vazute.append((self.inceput, "start"))
			self.pas_acum = "drivere"
		else:
			self.pas_acum = "interfata"

	def _vazut(self, ident, t):
		if ident in [i for _t, i in self.vazute]:
			self.progres.vazut(ident, t)
			return
		self.vazute.append((t, ident))
		self.progres.vazut(ident, t)
		cheie = None
		if ident.startswith("rc:"):
			cheie = ident[3:]
		elif ident in ("e2", "sh"):
			cheie = "interfata"
			self.e2_pornit = True
			if ident == "e2":
				self.blit_voie = True            # FBIO_BLIT numai dupa ce enigma2 ia OSD-ul
		else:
			cheie = PROFILE.get(ident)
		if cheie and cheie != self.pas_acum:
			if self.pas_acum:
				self.pas_gata = self.pas_acum
			self.pas_acum = cheie

	def _citestePasi(self):
		try:
			with open(os.path.join(DIR, "pasi")) as f:
				f.seek(self.pasi_poz)
				bucata = f.read()
		except (OSError, IOError):
			return
		capat = bucata.rfind("\n")
		if capat < 0:
			return
		self.pasi_poz += len(bucata[:capat + 1].encode("utf-8"))
		for rand in bucata[:capat].split("\n"):
			t, _s, ident = rand.partition(" ")
			try:
				self._vazut(ident.strip(), float(t))
			except ValueError:
				pass

	def _cautaProcese(self):
		"""Procesele noi: scripturile de pornire (felul boot) si enigma2 (cand iese, ajutorul pleaca)."""
		try:
			nume = [n for n in os.listdir(PROC) if n.isdigit()]
		except OSError:
			return
		for n in nume:
			if n in self.pid_vazute:
				continue
			self.pid_vazute.add(n)
			try:
				with open("%s/%s/cmdline" % (PROC, n), "rb") as f:
					cmd = f.read(512).replace(b"\0", b" ").decode("utf-8", "replace")
			except (OSError, IOError):
				continue
			if not self.e2_pornit:
				# rc porneste fiecare script ca „/etc/rc3.d/S10networking start” (scripturile .sh le citeste in
				# acelasi proces si nu se vad; pasul ramane cel de dinainte)
				for parte in cmd.split()[:3]:
					baza = parte.rsplit("/", 1)[-1]
					if ("/etc/rc" in parte and ".d/S" in parte) or ("/etc/init.d/" in parte and baza not in ("rc", "rcS")):
						self._vazut("rc:" + pasulScriptului(baza), ceas())
						break
			if cmd.startswith("/usr/bin/enigma2 ") or cmd.strip() == "/usr/bin/enigma2":
				self.e2_pid = int(n)
		if self.e2_pid and not os.path.exists("%s/%d" % (PROC, self.e2_pid)):
			if not self.e2_disparut:
				self.e2_disparut = ceas()

	def _textele(self):
		if not self.texte_citite:
			self.texte_citite = True
			self.texte = textePentruPornire(self.limba)

	def _deschide(self):
		self.gen_deschis = _generatie()
		try:
			self.ecran = Ecran()
		except (OSError, IOError, ValueError) as eroare:
			if not getattr(self, "spus", False):
				_jurnal("OSD-ul nu se deschide: %s" % eroare)
				self.spus = True
			self.ecran = None
			return
		if not self.ecran.bun:
			self.ecran.inchide()             # mod nepotrivit (sau OSD inca neinceput): se incearca la cadrul urmator
			self.ecran = None
			return
		# inainte de enigma2 (pasul „e2” nevazut si niciun enigma2 viu): OSD-ul ramas de la cel vechi sau de la incarcator
		# devine stravezii, ca sigla de pe stratul video sa se vada in spatele barei; dupa „e2” OSD-ul e al lui enigma2
		if "e2" not in [i for _t, i in self.vazute] and not _enigma2Viu():
			try:
				if self.ecran.curata():
					_jurnal("OSD-ul ramas (nestravezii) a fost facut stravezii inainte de bara")
			except (OSError, IOError, ValueError, IndexError):
				pass
		self.desen = Desen(self.ecran, self.texte)

	def _inchide(self, pune_la_loc):
		if self.ecran is not None:
			if pune_la_loc and self.ecran.bun:
				self.ecran.puneLaLoc()
				if self.blit_voie:
					self.ecran.blit()
			self.ecran.inchide()
		self.ecran = None
		self.desen = None
		self.ultim = None

	def bucla(self):
		import fcntl
		import signal

		def la_semnal(_s, _f):
			self.oprit = True
		signal.signal(signal.SIGTERM, la_semnal)
		signal.signal(signal.SIGINT, la_semnal)
		zavor = os.open(os.path.join(DIR, "lock"), os.O_CREAT | os.O_RDWR, 0o600)
		termen = self.inceput + TERMEN
		ultima_cautare = 0.0
		ultim_texte = False
		while not self.oprit:
			acum = ceas()
			if acum >= termen:
				break
			self._citestePasi()
			if acum - ultima_cautare >= (0.3 if not self.e2_pornit else 1.0):
				ultima_cautare = acum
				self._cautaProcese()
			if self.fel == "interfata" and "e2" not in [i for _t, i in self.vazute] and acum - self.inceput > 60.0:
				break                                    # enigma2.sh nu a ajuns la enigma2 (paza modelului, alt receptor)
			if self.e2_disparut and acum - self.e2_disparut > 2.0:
				break                                    # enigma2 a iesit; enigma2.sh porneste altul cu ajutorul lui
			fcntl.flock(zavor, fcntl.LOCK_EX)
			try:
				if os.path.exists(os.path.join(DIR, "pauza")):
					if self.ecran is not None:
						self._inchide(False)             # OSD-ul il schimba enigma2: nimic pus la loc, nimic scris
				else:
					# o pauza scurta poate trece intre doua cadre fara sa o vedem: generatia spune ca OSD-ul s-a schimbat
					if self.ecran is not None and _generatie() != self.gen_deschis:
						self._inchide(False)
					if self.ecran is None:
						self._deschide()
					if self.desen is not None:
						# textele dupa primul cadru: bara apare intai, textele o clipa mai tarziu
						if ultim_texte != self.texte_citite and self.texte_citite:
							self.desen = Desen(self.ecran, self.texte)
							self.ultim = None
						ultim_texte = self.texte_citite
						fr = self.progres.fractie(acum)
						semn = (int(fr * self.desen.bw), int(fr * 100 + 1e-6), self.pas_acum, self.pas_gata)
						if semn != self.ultim:
							# pas nou (sau OSD redeschis): tot panoul; altfel numai bara si procentul
							if self.ultim is None or self.ultim[2:] != semn[2:]:
								bun = self.ecran.scrie(self.desen.baza(self.pas_acum, self.pas_gata))
							else:
								bun = True
							if bun and self.ecran.scrieParti(self.desen.parti(fr)):
								self.ultim = semn
								if self.blit_voie:
									self.ecran.blit()
							else:
								self._inchide(False)     # alt mod decat cel citit: se redeschide la cadrul urmator
			finally:
				fcntl.flock(zavor, fcntl.LOCK_UN)
			if not self.texte_citite and self.desen is not None:
				self._textele()
			time.sleep(PERIOADA)
		fcntl.flock(zavor, fcntl.LOCK_EX)
		try:
			self._inchide(not os.path.exists(os.path.join(DIR, "pauza")))
		finally:
			fcntl.flock(zavor, fcntl.LOCK_UN)
		self._citestePasi()
		if CAPAT in [i for _t, i in self.vazute]:
			scrieTimpi(self.vazute, self.fel, self.timpi)
			self._pregatesteTextele()

	def _pregatesteTextele(self):
		"""Daca textele de pe receptor lipsesc sau sunt in alta limba, le face un proces separat, cu prioritate minima,
		peste un minut (dupa ce s-a linistit pornirea)."""
		font = _fontBun()
		if not font:
			return
		t = citesteTexte(TEXTE)
		if t and t[0].get("cheie") == cheieTexte(self.limba, font):
			return
		try:
			if os.fork():
				return
			os.setsid()
			if os.fork():
				os._exit(0)
			null = os.open(os.devnull, os.O_RDWR)
			for fd in (0, 1, 2):
				os.dup2(null, fd)
			os.execv(sys.executable, [sys.executable, "-I", "-B", os.path.abspath(__file__), "pregateste", "60"])
		except OSError:
			os._exit(0)


def _enigma2Viu():
	"""True daca ruleaza un proces enigma2 (dupa /proc/<pid>/comm)."""
	try:
		nume = [n for n in os.listdir(PROC) if n.isdigit()]
	except OSError:
		return False
	for n in nume:
		try:
			with open("%s/%s/comm" % (PROC, n)) as f:
				if f.read().strip() == "enigma2":
					return True
		except (OSError, IOError):
			pass
	return False


def _unic():
	"""Un singur ajutor: zavorul unic tinut toata viata. None daca altul ruleaza."""
	import fcntl
	try:
		os.makedirs(DIR, 0o755, exist_ok=True)
		fd = os.open(os.path.join(DIR, "unic"), os.O_CREAT | os.O_RDWR, 0o600)
		fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
		return fd
	except (OSError, IOError):
		return None


def main(argv):
	comanda = argv[1] if len(argv) > 1 else ""
	if comanda == "porneste":
		fel = argv[2] if len(argv) > 2 and argv[2] in ("boot", "interfata") else "interfata"
		if os.path.exists(OPRITA):
			return 0
		fd = _unic()
		if fd is None:
			return 0
		try:
			os.nice(10)
		except OSError:
			pass
		if fel == "boot":
			_scrie("pasi", "")                   # pornire noua: /run e gol oricum
		_scrie("pid", "%d\n" % os.getpid())
		try:
			Ajutor(fel).bucla()
		except Exception as eroare:
			_jurnal("ajutorul s-a oprit: %s" % eroare)
		_sterge("pid")
		return 0
	if comanda == "pregateste":
		# fisierul de texte in limba receptorului (dupa pornire, cu prioritate minima)
		try:
			os.nice(19)
		except OSError:
			pass
		if len(argv) > 2:
			time.sleep(float(argv[2]))
		font = _fontBun()
		if not font:
			return 1
		limba = limbaSetari()
		t = citesteTexte(TEXTE)
		if t and t[0].get("cheie") == cheieTexte(limba, font) and "--mereu" not in argv:
			return 0
		marime = deseneazaTexte(limba, font, TEXTE)
		_jurnal("texte %s: %d octeti" % (limba or "ro_RO", marime))
		return 0
	if comanda == "texte":
		# la constructie sau pe PC: texte <limba> <iesire>
		font = _fontBun()
		print(deseneazaTexte(argv[2], font, argv[3]))
		return 0
	print("folosire: %s porneste [boot|interfata] | pregateste [pauza] | texte <limba> <fisier>" % argv[0])
	return 2


if __name__ == "__main__":
	sys.exit(main(sys.argv))

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPluginExtern.py: o eroare intr-un plugin extern nu mai reporneste interfata; omul vede cauza pe ecran, iar echipa
# primeste raportul erorii (din 0.7.0).
#
# lib/python/python.cpp (ePython::call) cheama trateaza(tip, valoare, stiva, apel, jurnal) cand o functie Python chemata
# din C++ (un ceas, o tasta, iesirea unui program pornit cu eConsoleAppContainer) se termina cu o exceptie; apel e randul
# "(PyObject_CallObject(...) failed)" pe care C++ il scrie in jurnal, jurnal sfarsitul jurnalului de dinaintea erorii
# (inelul de 16 KiB al lui main/bsod.cpp). Daca stiva trece printr-un plugin care nu a venit cu imaginea (un dosar
# Plugins/Extensions/<Nume>/ sau Plugins/SystemPlugins/<Nume>/ care nu e in PLUGINURI_IMAGINE), trateaza() intoarce
# numele lui: C++ tipareste stiva in jurnal ca pana acum si merge mai departe, fara ecranul de cadere si fara repornire.
# Altfel intoarce None si totul ramane ca inainte (bsodFatal). Nu arunca.
#
# Pluginurile imaginii: o lista fixa (PLUGINURI_IMAGINE), cu dosarele din lib/python/Plugins ale sursei si pluginul
# pachetului skinului; proba test_eroare_plugin_extern_070.py o tine la zi cu dosarele din sursa. Orice alt dosar de
# plugin e extern, si cele din feedul nostru de pluginuri externe. Pluginul ales: cadrul extern cel mai adanc din stiva
# (cel mai aproape de locul erorii); calea se cauta oriunde in numele fisierului (un .pyc are calea masinii pe care a
# fost compilat).
#
# Raportul (specificatia comuna cu serverul): antetul
# cheie=valoare in ordinea ANTET_CHEI, un rand gol, apoi sectiunile [stiva], [jurnal], [fisiere], [pluginuri_externe],
# [surse_opkg], [jurnal_cadere]. Trimis anonim (fara inscriere, fara acordul de beta tester) pe ruta raport-plugin, cu
# acelasi client ca Components/HdsBetaTester.py (urllib). Raspunsul {"ok", "cod", "vreau_fisierele"}; cu
# vreau_fisierele, pachetul cu fisierele pluginului (tar.gz, filtrat: PachetFisiere) pe ruta raport-plugin-fisiere.
# Un raport netrimis (fara internet, 5xx, 404, 408, 429) sta in DOSAR_COADA si se reincearca la 15 minute, de cel mult
# 20 de ori; un alt 4xx il sterge.
#
# Cat se face, intr-o sesiune a interfetei, pentru un plugin:
#   - la fiecare eroare: decizia (numele), randul in jurnal si, daca ecranul curent a cazut cand pornea, inchiderea lui;
#   - o semnatura noua (pluginul, tipul exceptiei, ultimul cadru din plugin, mesajul fara cifre si cai): jurnalul de
#     cadere (enigma2_crash_<ora>.log, formatul text al ecranelor cazute din mytest.py, cu antetul ANTET si randul
#     "Plugin extern: <Nume>") si raportul;
#   - prima eroare a pluginului: mesajul mic pe ecran (Screens/HdsAnuntRetea): titlul, cauza (CAUZE), "Receptorul merge
#     mai departe." si fraza echipei, dupa raspunsul serverului sau dupa cel mult ASTEPTARE_RASPUNS_S secunde;
#   - peste ERORI_PE_MINUT erori ale pluginului intr-un minut: numai un rand in jurnal.
#
# Ecranul deschis pe jumatate: Session.open (mytest.py) prinde deja eroarea din __init__ si din skin. O eroare dupa ce
# ecranul a devenit cel curent (onExecBegin, onShown, show) iese din Session.open, care pune semnul hdsDeschidereEsuata;
# cu el tastele nu mai ajung nicaieri. Dupa o eroare de plugin extern ecranul acela se inchide (session.close), iar omul
# ramane in ecranul de dinainte. Ce a schimbat pluginul inainte de eroare nu se desface.
#
# FIRUL: trateaza() ruleaza pe firul enigma2, in mijlocul unui apel din C++: numai decizia si compunerea ieftina (stiva,
# cauza, semnatura, antetul stiut). Jurnalul de cadere, id-ul, versiunile, opkg, lista fisierelor cu sha256, trimiterea,
# pachetul si coada merg pe un fir (Lucru, LucruCoada); nicio cerere HTTP pe firul enigma2. Inchiderea ecranului si
# mesajul vin dintr-un eTimer. Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC); RADACINA pune un
# dosar in fata cailor de sistem, numai la probe.

import errno
import fnmatch
import gzip
import hashlib
import io
import json
import os
import platform
import re
import tarfile
import threading
import time
import traceback

RADACINA = ""
SERVER = "https://stb.hdsatelit.com/api/testeri/"
RUTA_RAPORT = "raport-plugin"
RUTA_FISIERE = "raport-plugin-fisiere"
DOSAR_JURNALE = "/home/root/logs"
DOSAR_REZERVA = "/tmp"
DOSAR_COADA = "/home/root/logs/rapoarte-pluginuri"
FISIER_ID = "/etc/enigma2/hds-raport-plugin.id"
PREFIX_PLUGINURI = "/usr/lib/enigma2/python/Plugins/"
OPKG_STATUS = "/var/lib/opkg/status"
OPKG_INFO = "/var/lib/opkg/info"
OPKG_LISTE = "/var/lib/opkg/lists"
OPKG_CONF = "/etc/opkg"
IMAGE_VERSION = "/etc/image-version"
ENIGMA_INFO = "/usr/lib/enigma.info"
MODEL_STB = "/proc/stb/info/model"

# acelasi inceput ca la ecranele cazute din mytest.py ("HD Satelit: raport de eroare, ecran protejat"), ca uneltele care
# citesc jurnalele sa-l stie; Components/HdsBetaTester.py si Components/HdsModSigur.py il deosebesc dupa el
ANTET = "HD Satelit: raport de eroare, plugin extern"

DURATA_MESAJ_MS = 15000
ASTEPTARE_RASPUNS_S = 8
PAS_CEAS_MS = 250
ERORI_PE_MINUT = 5
JURNAL_RANDURI = 300
MESAJ_MAX = 300
CORP_MAX = 1024 * 1024
FISIER_MAX = 5 * 1024 * 1024
FARA_EXTENSIE_MAX = 256 * 1024
PACHET_MAX = 20 * 1024 * 1024
COADA_MAX = 10
COADA_OCTETI = 5 * 1024 * 1024
COADA_INCERCARI = 20
COADA_PAS_MS = 15 * 60 * 1000
TIMP_CERERE_S = 30

ANTET_CHEI = ("format", "cheie", "receptor_anonim", "model", "imagine", "build", "enigma2", "python", "ora",
	"functionare_s", "plugin", "cale", "pachet", "pachet_versiune", "pachet_sursa", "plugin_versiune",
	"amprenta_fisiere", "semnatura", "cauza", "exceptie", "mesaj", "erori_sesiune")
SECTIUNI = ("stiva", "jurnal", "fisiere", "pluginuri_externe", "surse_opkg", "jurnal_cadere")

# dosarele Plugins/<fel>/<nume> ale imaginii: lib/python/Plugins din sursa si pachetul hdsatelit-skin (HdsSkinSetari)
PLUGINURI_IMAGINE = frozenset((
	"Extensions/HdsCutListEditor",
	"Extensions/HdsImportSetari",
	"Extensions/HdsNavigator",
	"Extensions/HdsSkinSetari",
	"Extensions/HdsWebControl",
	"Extensions/MediaPlayer",
	"Extensions/MediaScanner",
	"Extensions/PicturePlayer",
	"SystemPlugins/DiseqcTester",
	"SystemPlugins/HdsDvbI",
	"SystemPlugins/Hotplug",
	"SystemPlugins/SkinSelector",
))
FELURI = ("Extensions", "SystemPlugins")

# cauzele (specificatia, sectiunea 4), in ordinea in care se incearca; nicio cauza inventata: altfel "interna"
CAUZE = ("octeti-text", "python2", "modul-lipsa", "tema", "internet", "fisier", "interna")
_OCTETI_TEXT = re.compile(r"can't concat (?:str|bytes) to (?:bytes|str)|can only concatenate str \(not \"bytes\"\) to str"
	r"|'str' object has no attribute 'decode'|'bytes' object has no attribute 'encode'|a bytes-like object is required"
	r"|cannot use a (?:string|bytes) pattern on a (?:bytes|string)-like object")
_PYTHON2_NUME = re.compile(r"name '(?:unicode|basestring|xrange|raw_input|long|unichr|execfile|reload)' is not defined")
_INTERNET = frozenset(("URLError", "HTTPError", "timeout", "TimeoutError", "ConnectionError", "gaierror", "SSLError"))
_FISIER = frozenset(("FileNotFoundError", "PermissionError", "IsADirectoryError"))

_CADRU = re.compile(r"/Plugins/(Extensions|SystemPlugins)/([^/]+)/")

# pachetul de fisiere (specificatia, sectiunea 5)
EXTENSII = frozenset((".py", ".pyc", ".pyo", ".so", ".xml", ".json", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".po",
	".mo", ".txt", ".md", ".sh", ".conf", ".ini", ".cfg", ".html", ".css", ".js", ".ttf"))
NUME_SECRETE = ("*.key", "softcam*", "oscam*", "ncam*", "cccam*", "mgcamd*", "newcamd*", "gbox*", "wicardd*", "*.pem", "*.p12",
	"*.crt", "*.pfx", "settings", "id_rsa*", "id_ed25519*", "id_ecdsa*", ".env", "passw*", "credential*", "hds_iptv*")
# un rand cu o parola, un jeton sau o cheie cu valoare; cheia poate fi intre ghilimele (JSON)
_SECRET_RAND = re.compile(r"(?i)(?:pass|passwd|password|pwd|token|secret|apikey|api_key)[\"']?\s*[=:](.*)")

# masca datelor omului (ca tools/hds-raport.sh.in): adresele web intregi, IPv4 a.b.x.x, MAC cu producatorul, e-mail
_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MAC = re.compile(r"(?<![0-9A-Fa-f:])([0-9A-Fa-f]{2})[:-]([0-9A-Fa-f]{2})[:-]([0-9A-Fa-f]{2})(?:[:-][0-9A-Fa-f]{2}){3}"
	r"(?![0-9A-Fa-f:])")
_IP4 = re.compile(r"(?<![0-9.])([0-9]{1,3})\.([0-9]{1,3})\.[0-9]{1,3}\.[0-9]{1,3}(?![0-9.])")
_IP6 = re.compile(r"(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{1,4}:){5,7}[0-9A-Fa-f]{1,4}(?![0-9A-Za-z:])")
_PAROLA_IN_ADRESA = re.compile(r"(://)[^/@\s]*@")

_lacat = threading.Lock()
_pluginuri = {}             # nume -> {"ore": [], "erori": 0, "semnaturi": set(), "aratat": False}
_asteptari = []             # mesajele care asteapta raspunsul serverului si firele care mai lucreaza
_deInchis = [False]
_ceas = [None]
_ceasCoada = [None]
_firCoada = [None]
_opkg = {}                  # ce s-a citit o data din opkg (pe fir): "status", "dosare"
_PORNIRE_MODUL = time.monotonic()


def _jurnal(text):
	print("[HdsPluginExtern] %s" % text)


def _r(cale):
	return RADACINA + cale if RADACINA else cale


# ------------------------------------------------------------------ decizia

def pluginDinCale(cale):
	"""(fel, nume) al pluginului extern din calea unui fisier, sau None (al imaginii sau nu e intr-un dosar de plugin)."""
	m = None
	for m in _CADRU.finditer((cale or "").replace("\\", "/")):
		pass
	if m is None or "%s/%s" % (m.group(1), m.group(2)) in PLUGINURI_IMAGINE:
		return None
	return m.group(1), m.group(2)


def cadre(stiva):
	"""(fisier, rand) pentru fiecare cadru al stivei, de la apelul din C++ la locul erorii."""
	rez = []
	while stiva is not None:
		rez.append((stiva.tb_frame.f_code.co_filename, stiva.tb_lineno))
		stiva = stiva.tb_next
	return rez


def pluginDinStiva(stiva):
	"""Numele pluginului extern al cadrului extern cel mai adanc din stiva, sau None."""
	p = _pluginSiCadru(stiva)
	return p[1] if p else None


def _pluginSiCadru(stiva):
	"""(fel, nume, fisierul relativ la Plugins/, randul) pentru cadrul extern cel mai adanc, sau None."""
	gasit = None
	for cale, rand in cadre(stiva):
		p = pluginDinCale(cale)
		if p is not None:
			cale = cale.replace("\\", "/")
			gasit = (p[0], p[1], cale[cale.rindex("/Plugins/") + len("/Plugins/"):], rand)
	return gasit


def cauza(tip, valoare):
	"""Codul cauzei (CAUZE), dupa tipul exceptiei si mesaj."""
	clase = set(c.__name__ for c in getattr(tip, "__mro__", (tip,)))
	mesaj = _text(valoare)
	if clase & {"TypeError", "AttributeError"} and _OCTETI_TEXT.search(mesaj):
		return "octeti-text"
	if "SyntaxError" in clase and pluginDinCale(getattr(valoare, "filename", None) or ""):
		return "python2"
	if "NameError" in clase and _PYTHON2_NUME.search(mesaj):
		return "python2"
	if clase & {"ModuleNotFoundError", "ImportError"}:
		return "modul-lipsa"
	if "SkinError" in clase:
		return "tema"
	if clase & _INTERNET:
		return "internet"
	if clase & _FISIER or ("OSError" in clase and getattr(valoare, "errno", None) in (errno.ENOSPC, errno.EROFS)):
		return "fisier"
	return "interna"


def _text(valoare):
	try:
		return str(valoare)
	except Exception:
		return ""


def semnatura(nume, tip, cadru, mesaj):
	"""sha256 hex al: pluginul, tipul exceptiei, ultimul cadru din plugin (fisier relativ:rand), mesajul fara cai si cifre.
	Aceeasi eroare da aceeasi semnatura pe orice receptor."""
	curat = re.sub(r"\S*[/\\]\S*", "", mesaj or "")
	curat = " ".join(re.sub(r"[0-9]+", "", curat).split())
	text = "\n".join((nume, getattr(tip, "__name__", str(tip)), cadru, curat))
	return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def trateaza(tip, valoare, stiva, apel=None, jurnal=None):
	"""Chemata din C++ (ePython::call) cu exceptia luata. Numele pluginului extern (interfata merge mai departe) sau None
	(ca inainte: ecranul de cadere si repornirea). Nu arunca."""
	try:
		# iesirea ceruta (sys.exit) nu e o eroare: ramane ca inainte
		if tip is None or issubclass(tip, (SystemExit, KeyboardInterrupt)):
			return None
		p = _pluginSiCadru(stiva)
	except Exception as e:
		_jurnal("stiva nu se poate citi: %r" % (e,))
		return None
	if p is None:
		return None
	fel, nume, fisier, rand = p
	try:
		_dupaDecizie(fel, nume, "%s:%d" % (fisier, rand), tip, valoare, stiva, apel, jurnal)
	except Exception as e:
		# ce urmeaza dupa decizie (jurnalul, raportul, mesajul) nu are voie sa duca la repornire
		_jurnal("dupa eroarea pluginului %s: %r" % (nume, e))
	return nume


def _dupaDecizie(fel, nume, cadru, tip, valoare, stiva, apel, jurnal, acum=None, mono=None):
	acum = time.time() if acum is None else acum
	mono = time.monotonic() if mono is None else mono
	st = _pluginuri.setdefault(nume, {"ore": [], "erori": 0, "semnaturi": set(), "aratat": False})
	st["erori"] += 1
	st["ore"] = [t for t in st["ore"] if mono - t < 60] + [mono]
	_deInchis[0] = True
	if len(st["ore"]) > ERORI_PE_MINUT:
		_jurnal("peste %d erori intr-un minut in pluginul extern %s: interfata merge mai departe" % (ERORI_PE_MINUT, nume))
		_programeaza()
		return
	mesaj = _text(valoare)
	sem = semnatura(nume, tip, cadru, mesaj)
	if sem in st["semnaturi"]:
		_jurnal("eroare din nou in pluginul extern %s: interfata merge mai departe" % nume)
		_programeaza()
		return
	st["semnaturi"].add(sem)
	cod = cauza(tip, valoare)
	raport = compuneRaport(fel, nume, cod, sem, tip, valoare, stiva, apel, jurnal, st["erori"], acum, mono)
	_jurnal("eroare in pluginul extern %s (%s): interfata merge mai departe; jurnalul si raportul pe fir" % (nume, cod))
	lucru = Lucru(raport)
	lucru.start()
	arata = not st["aratat"]
	st["aratat"] = True
	_asteptari.append({"nume": nume, "cauza": cod, "lucru": lucru, "termen": mono + ASTEPTARE_RASPUNS_S,
		"arata": arata})
	_programeaza()


# ------------------------------------------------------------------ raportul: compunerea (firul enigma2, ieftina)

def unRand(text, maxim=None):
	"""Valoarea unui rand din antet: fara sfarsituri de rand, fara = la inceput."""
	text = " ".join((text or "").replace("\r", " ").replace("\n", " ").split())
	text = text.lstrip("=").strip()
	return text[:maxim] if maxim else text


def masca(text):
	"""Datele omului ascunse (ca tools/hds-raport.sh.in): adresele web, e-mailurile, MAC-ul (ramane producatorul),
	IPv4 (ramane a.b), IPv6."""
	text = _URL.sub("<adresa ascunsa>", text or "")
	text = _EMAIL.sub("<ascuns>", text)
	text = _MAC.sub(lambda m: "%s:%s:%s:xx:xx:xx" % m.groups(), text)
	text = _IP4.sub(lambda m: "%s.%s.x.x" % m.groups(), text)
	return _IP6.sub("<ascuns>", text)


def textJurnalCadere(nume, tip, valoare, stiva):
	"""Textul jurnalului de cadere (si al sectiunii [jurnal_cadere]): antetul, pluginul, stiva."""
	return "%s\nPlugin extern: %s\n%s" % (ANTET, nume, "".join(traceback.format_exception(tip, valoare, stiva)))


def compuneRaport(fel, nume, cod, sem, tip, valoare, stiva, apel, jurnal, erori, acum, mono):
	"""Ce se stie fara sa se citeasca nimic de pe disc; restul il pune firul (completeaza)."""
	antet = dict((k, "") for k in ANTET_CHEI)
	antet.update({"format": "1", "cheie": os.urandom(16).hex(), "python": platform.python_version(),
		"ora": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(acum)), "plugin": nume, "cale": "%s/%s" % (fel, nume),
		"semnatura": sem, "cauza": cod, "exceptie": getattr(tip, "__name__", str(tip)),
		"mesaj": unRand(masca(_text(valoare)), MESAJ_MAX), "erori_sesiune": str(erori)})
	stiva_text = "".join(traceback.format_exception(tip, valoare, stiva)).rstrip("\n")
	if apel:
		stiva_text += "\n" + apel
	cadere = textJurnalCadere(nume, tip, valoare, stiva)
	return {"antet": antet, "mono": mono, "acum": acum, "stiva": stiva_text, "jurnal_brut": jurnal or "",
		"jurnal_cadere": cadere}


# ------------------------------------------------------------------ raportul: ce citeste firul

def _citeste(cale, maxim=1024 * 1024):
	try:
		with open(_r(cale), "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return ""


def idAnonim():
	"""sha256 hex al jetonului facut o data pe instalare (FISIER_ID), nimic din aparat; jetonul se face la nevoie."""
	cale = _r(FISIER_ID)
	jeton = _citeste(FISIER_ID, 256).strip()
	if not re.match(r"\A[0-9a-f]{32}\Z", jeton):
		jeton = os.urandom(16).hex()
		try:
			with open(cale + ".nou", "w") as f:
				f.write(jeton + "\n")
			os.rename(cale + ".nou", cale)
		except (IOError, OSError) as e:
			_jurnal("jetonul raportului nu se poate scrie: %s" % e)
	return hashlib.sha256(jeton.encode("ascii")).hexdigest()


def _valoareInfo(text, cheie):
	m = re.search(r"(?m)^%s=(.*)$" % re.escape(cheie), text)
	return m.group(1).strip().strip("'\"") if m else ""


def model():
	m = _citeste(MODEL_STB, 256).strip().splitlines()
	if m and m[0].strip():
		return unRand(m[0], 40)
	info = _citeste(ENIGMA_INFO, 64 * 1024)
	return unRand(_valoareInfo(info, "model") or _valoareInfo(info, "machinebuild"), 40)


def buildSiVersiune():
	"""(build, versiune) din randul version= al lui /etc/image-version: 16 cifre = fel, x, y, z de o cifra + data; 19
	cifre = fel de o cifra, x, y, z de doua (ca Components/HdsJurnalVersiuni si tools/hds-raport.sh.in)."""
	build = re.sub(r"[^0-9]", "", _valoareInfo(_citeste(IMAGE_VERSION, 4096), "version"))
	versiune = ""
	if len(build) == 16 and build[0] == "0":
		versiune = "%d.%d.%d" % (int(build[1]), int(build[2]), int(build[3]))
	elif len(build) == 19 and build[0] == "0":
		versiune = "%d.%d.%d" % (int(build[1:3]), int(build[3:5]), int(build[5:7]))
	return build, versiune


def functionare(mono):
	"""Secundele de la pornirea procesului enigma2 pana la eroare (starttime din /proc/self/stat; ceasul monoton e cel
	de la pornirea sistemului)."""
	try:
		stat = _citeste("/proc/self/stat", 4096)
		campuri = stat[stat.rindex(")") + 2:].split()
		pornit = int(campuri[19]) / float(os.sysconf("SC_CLK_TCK"))
		if 0 <= mono - pornit < 10 * 365 * 86400:
			return str(int(mono - pornit))
	except (ValueError, IndexError, OSError, AttributeError):
		pass
	return str(int(max(0, mono - _PORNIRE_MODUL)))


def statusOpkg():
	"""{pachet: versiune} din /var/lib/opkg/status (o data pe proces)."""
	with _lacat:
		if "status" in _opkg:
			return _opkg["status"]
	rez = {}
	pachet = None
	for rand in _citeste(OPKG_STATUS, 16 * 1024 * 1024).splitlines():
		if rand.startswith("Package:"):
			pachet = rand[8:].strip()
		elif rand.startswith("Version:") and pachet:
			rez[pachet] = rand[8:].strip()
		elif not rand.strip():
			pachet = None
	with _lacat:
		_opkg["status"] = rez
	return rez


def dosarePachete():
	"""{"<fel>/<nume>": pachet} din listele opkg (o data pe proces)."""
	with _lacat:
		if "dosare" in _opkg:
			return _opkg["dosare"]
	rez = {}
	try:
		liste = sorted(n for n in os.listdir(_r(OPKG_INFO)) if n.endswith(".list"))
	except OSError:
		liste = []
	for n in liste:
		text = _citeste(os.path.join(OPKG_INFO, n), 4 * 1024 * 1024)
		if PREFIX_PLUGINURI not in text:
			continue
		for rand in text.splitlines():
			cale = rand.split("\t", 1)[0].strip()
			if cale.startswith(PREFIX_PLUGINURI):
				parti = cale[len(PREFIX_PLUGINURI):].split("/")
				if len(parti) >= 3 and parti[0] in FELURI and parti[1]:
					rez.setdefault(parti[0] + "/" + parti[1], n[:-5])
	with _lacat:
		_opkg["dosare"] = rez
	return rez


def sursaPachet(pachet):
	"""Numele sursei opkg (fisierul din /var/lib/opkg/lists) care are pachetul, sau ""."""
	if not pachet:
		return ""
	cauta = "Package: %s\n" % pachet
	try:
		liste = sorted(os.listdir(_r(OPKG_LISTE)))
	except OSError:
		return ""
	for n in liste:
		text = _citeste(os.path.join(OPKG_LISTE, n), 16 * 1024 * 1024)
		if text.startswith(cauta) or ("\n" + cauta) in text:
			return unRand(n, 60)
	return ""


_VERSIUNE_COD = re.compile(r"(?im)^[ \t]*(?:__version__|version|plugin_version|VERSION)[ \t]*=[ \t]*[\"']([^\"'\n]{1,40})[\"']")
_VERSIUNE_RAND = re.compile(r"(?im)^[ \t#]*version[ \t]*[:=][ \t]*[\"']?([0-9][0-9A-Za-z._+-]{0,39})")


def versiunePlugin(dosar):
	"""Versiunea scrisa de plugin: version.txt / VERSION, __version__ / VERSION in plugin.py, randul Version; sau ""."""
	for n in ("version.txt", "VERSION", "version", "Version.txt"):
		text = _citeste(os.path.join(dosar, n), 4096).strip()
		if text:
			return unRand(text.splitlines()[0], 40)
	for n in ("plugin.py", "__init__.py"):
		text = _citeste(os.path.join(dosar, n), 256 * 1024)
		m = _VERSIUNE_COD.search(text) or _VERSIUNE_RAND.search(text)
		if m:
			return unRand(m.group(1), 40)
	return ""


def motivOmis(nume, cale_disc, marime):
	"""De ce un fisier nu intra in pachet: "posibil secret", "prea mare", "alt fel"; None daca intra."""
	mic = nume.lower()
	if any(fnmatch.fnmatch(mic, t) for t in NUME_SECRETE):
		return "posibil secret"
	if marime > FISIER_MAX:
		return "prea mare"
	ext = os.path.splitext(mic)[1]
	if not ext:
		if marime >= FARA_EXTENSIE_MAX:
			return "prea mare"
	elif ext not in EXTENSII:
		return "alt fel"
	if areSecret(cale_disc):
		return "posibil secret"
	return None


def areSecret(cale_disc):
	"""Un fisier text cu un rand parola/jeton/cheie = valoare negoala (fisierele de configurare se citesc numai
	pentru asta)."""
	try:
		with open(cale_disc, "rb") as f:
			date = f.read(FISIER_MAX + 1)
	except (IOError, OSError):
		return False
	if b"\0" in date[:8192]:
		return False
	for rand in date.decode("utf-8", "replace").splitlines():
		m = _SECRET_RAND.search(rand)
		if m and _valoare(m.group(1)):
			return True
	return False


def _valoare(rest):
	"""Valoarea de dupa = sau : : sirul dintre ghilimele, altfel primul cuvant (pana la spatiu , ; } ] #)."""
	rest = rest.lstrip()
	if rest[:1] in ("\"", "'"):
		sfarsit = rest.find(rest[0], 1)
		return rest[1:sfarsit] if sfarsit > 0 else rest[1:]
	return re.split(r"[\s,;}\]#]", rest, 1)[0]


def sha256Fisier(cale_disc):
	h = hashlib.sha256()
	with open(cale_disc, "rb") as f:
		while True:
			b = f.read(65536)
			if not b:
				break
			h.update(b)
	return h.hexdigest()


def fisierePlugin(cale_plugin):
	"""[(cale relativa la Plugins/, marime, sha256 sau "omis: <motiv>", calea pe disc)] sortate; fara __pycache__ si fara
	legaturi."""
	baza = _r(PREFIX_PLUGINURI)
	dosar = os.path.join(baza, cale_plugin)
	rez = []
	for radacina, dosare, fisiere in os.walk(dosar, followlinks=False):
		dosare[:] = [d for d in dosare if d != "__pycache__"]
		for n in fisiere:
			disc = os.path.join(radacina, n)
			if os.path.islink(disc) or not os.path.isfile(disc):
				continue
			try:
				marime = os.path.getsize(disc)
			except OSError:
				continue
			rel = os.path.relpath(disc, baza).replace("\\", "/")
			motiv = motivOmis(n, disc, marime)
			try:
				semn = "omis: " + motiv if motiv else sha256Fisier(disc)
			except (IOError, OSError):
				semn = "omis: necitit"
			rez.append((rel, marime, semn, disc))
	rez.sort(key=lambda x: x[0])
	return rez


def amprenta(fisiere):
	"""sha256 hex al listei "cale marime sha256" (un rand pe fisier, sortata): aceeasi versiune = aceeasi amprenta."""
	return hashlib.sha256("".join("%s %d %s\n" % f[:3] for f in fisiere).encode("utf-8", "replace")).hexdigest()


def pluginuriExterne(fara, pachete, versiuni):
	"""Celelalte pluginuri externe instalate: "cale<TAB>pachet<TAB>versiune" (golurile de la sfarsit scoase)."""
	rez = []
	for fel in FELURI:
		try:
			nume = sorted(os.listdir(_r(PREFIX_PLUGINURI + fel)))
		except OSError:
			continue
		for n in nume:
			cheie = "%s/%s" % (fel, n)
			if cheie == fara or cheie in PLUGINURI_IMAGINE or n == "__pycache__":
				continue
			if not os.path.isdir(_r(PREFIX_PLUGINURI + cheie)):
				continue
			pachet = pachete.get(cheie, "")
			rez.append(("%s\t%s\t%s" % (cheie, pachet, versiuni.get(pachet, "") if pachet else "")).rstrip("\t"))
	return rez


def surseOpkg():
	"""Sursele din /etc/opkg/*.conf: "nume adresa", fara utilizator si parola in adresa."""
	rez = []
	try:
		nume = sorted(n for n in os.listdir(_r(OPKG_CONF)) if n.endswith(".conf"))
	except OSError:
		nume = []
	for n in nume:
		for rand in _citeste(os.path.join(OPKG_CONF, n), 64 * 1024).splitlines():
			m = re.match(r"\s*src(?:/gz)?\s+(\S+)\s+(\S+)", rand)
			if m:
				linie = "%s %s" % (m.group(1), _PAROLA_IN_ADRESA.sub(r"\1", m.group(2)))
				if linie not in rez:
					rez.append(linie)
	return rez


def jurnalCurat(brut):
	"""Ultimele JURNAL_RANDURI randuri ale jurnalului, fara randurile cu parole, chei si acces conditionat (regulile
	jurnalelor beta testerilor), cu datele omului ascunse."""
	randuri = (brut or "").replace("\r", "").split("\n")
	if len(brut or "") >= 16000 and len(randuri) > 1:
		randuri = randuri[1:]             # inelul plin: primul rand e taiat
	try:
		from Components import HdsBetaTester as B
		pastrat = [r for r in randuri if not (B.esteDeAcces(r) or B._SECRET.search(r))]
	except Exception:
		pastrat = [r for r in randuri if not re.search(r"(?i)pass|parol|token|secret|key|cheie|psk", r)]
	pastrat = [masca(r)[:1000] for r in pastrat if r.strip()]
	return pastrat[-JURNAL_RANDURI:]


def completeaza(raport):
	"""Pe fir: tot ce se citeste de pe disc (antetul, [fisiere], [pluginuri_externe], [surse_opkg], [jurnal])."""
	a = raport["antet"]
	a["receptor_anonim"] = idAnonim()
	a["model"] = model()
	a["build"], a["imagine"] = buildSiVersiune()
	versiuni = statusOpkg()
	a["enigma2"] = unRand(versiuni.get("enigma2-hdsatelit") or versiuni.get("enigma2", ""), 80)
	a["functionare_s"] = functionare(raport["mono"])
	pachete = dosarePachete()
	a["pachet"] = pachete.get(a["cale"], "")
	a["pachet_versiune"] = unRand(versiuni.get(a["pachet"], ""), 80) if a["pachet"] else ""
	a["pachet_sursa"] = sursaPachet(a["pachet"])
	a["plugin_versiune"] = versiunePlugin(PREFIX_PLUGINURI + a["cale"])
	fisiere = fisierePlugin(a["cale"])
	a["amprenta_fisiere"] = amprenta(fisiere)
	raport["fisiere"] = fisiere
	raport["sectiuni"] = {
		"stiva": masca(raport["stiva"]),
		"jurnal": "\n".join(jurnalCurat(raport["jurnal_brut"])),
		"fisiere": "\n".join("%s\t%d\t%s" % f[:3] for f in fisiere),
		"pluginuri_externe": "\n".join(pluginuriExterne(a["cale"], pachete, versiuni)),
		"surse_opkg": "\n".join(surseOpkg()),
		"jurnal_cadere": masca(raport["jurnal_cadere"]).rstrip("\n"),
	}
	return raport


def textRaport(antet, sectiuni):
	"""Antetul (ANTET_CHEI), un rand gol, apoi [sectiune] cu continutul ei, despartite de un rand gol."""
	randuri = ["%s=%s" % (k, unRand(antet.get(k, ""))) for k in ANTET_CHEI]
	corp = "\n\n".join("[%s]\n%s" % (s, sectiuni.get(s, "").strip("\n")) if sectiuni.get(s, "").strip("\n")
		else "[%s]" % s for s in SECTIUNI)
	return "\n".join(randuri) + "\n\n" + corp + "\n"


def construieste(raport):
	"""Textul raportului, cel mult CORP_MAX octeti: se taie intai [jurnal] (randurile vechi), apoi [fisiere]."""
	sectiuni = dict(raport["sectiuni"])
	text = textRaport(raport["antet"], sectiuni)
	for s in ("jurnal", "fisiere", "pluginuri_externe", "stiva"):
		while len(text.encode("utf-8")) > CORP_MAX and sectiuni.get(s):
			randuri = sectiuni[s].split("\n")
			sectiuni[s] = "\n".join(randuri[len(randuri) // 2 + 1:]) if len(randuri) > 1 else ""
			text = textRaport(raport["antet"], sectiuni)
	date = text.encode("utf-8")
	if len(date) > CORP_MAX:
		text = date[:CORP_MAX].decode("utf-8", "ignore")
	return text


def pachetFisiere(fisiere):
	"""tar.gz cu fisierele care intra (caile relative la Plugins/), sau None peste PACHET_MAX."""
	alese = [f for f in fisiere if not f[2].startswith("omis:")]
	if sum(f[1] for f in alese) > PACHET_MAX:
		return None
	b = io.BytesIO()
	with tarfile.open(fileobj=b, mode="w:gz") as tar:
		for rel, _marime, _semn, disc in alese:
			try:
				tar.add(disc, arcname=rel, recursive=False)
			except (IOError, OSError):
				pass
	date = b.getvalue()
	return date if len(date) <= PACHET_MAX else None


# ------------------------------------------------------------------ trimiterea (pe fir)

def _posteazaHttp(url, date, antete, timp=TIMP_CERERE_S):
	"""POST cu clientul raportului beta testerilor (urllib, certificatul verificat). (cod HTTP, raspunsul); cod 0 =
	fara legatura."""
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError
	h = {"User-Agent": "hdsatelit-receptor/1", "Accept": "application/json"}
	h.update(antete)
	try:
		r = urlopen(Request(url, data=date, method="POST", headers=h), timeout=timp)
		try:
			return r.getcode(), r.read(65536)
		finally:
			r.close()
	except HTTPError as e:
		try:
			corp = e.read(65536)
		except Exception:
			corp = b""
		return e.code, corp
	except Exception as e:
		_jurnal("trimiterea la %s: %s" % (url.rsplit("/", 1)[-1], e))
		return 0, b""


_posteaza = [_posteazaHttp]


def _json(octeti):
	try:
		o = json.loads(octeti.decode("utf-8"))
		return o if isinstance(o, dict) else {}
	except (ValueError, UnicodeDecodeError, AttributeError):
		return {}


TRIMIS, LASAT, MAI_TARZIU = "trimis", "lasat", "mai-tarziu"


def hotarare(cod, raspuns):
	"""TRIMIS (2xx cu ok), MAI_TARZIU (fara legatura, 5xx, 404, 408, 429: ramane in coada), LASAT (alt 4xx)."""
	if 200 <= cod < 300:
		return TRIMIS if raspuns.get("ok") is True else LASAT
	if cod == 0 or cod >= 500 or cod in (404, 408, 429):
		return MAI_TARZIU
	return LASAT


def trimiteText(text):
	"""(hotarare, raspunsul) pentru textul unui raport."""
	cod, octeti = _posteaza[0](SERVER + RUTA_RAPORT, gzip.compress(text.encode("utf-8")),
		{"Content-Type": "text/plain; charset=utf-8", "Content-Encoding": "gzip"})
	raspuns = _json(octeti)
	return hotarare(cod, raspuns), raspuns


def trimiteFisiere(cod_raport, cheie, fisiere):
	date = pachetFisiere(fisiere)
	if date is None:
		_jurnal("pachetul de fisiere trece de %d MB: se trimite numai raportul" % (PACHET_MAX // 1048576))
		return False
	cod, _octeti = _posteaza[0](SERVER + RUTA_FISIERE, date, {"Content-Type": "application/gzip",
		"X-HDS-Cod": str(cod_raport), "X-HDS-Cheie": cheie})
	return 200 <= cod < 300


def _valoareAntet(text, cheie):
	cap = text.split("\n\n", 1)[0]
	return _valoareInfo(cap, cheie)


def dupaRaspuns(text, ce, raspuns):
	"""Pachetul de fisiere, cand serverul il vrea (fisierele se iau de pe disc in clipa trimiterii)."""
	if ce == TRIMIS and raspuns.get("vreau_fisierele") is True:
		cale = _valoareAntet(text, "cale")
		if cale.split("/")[0] in FELURI and os.path.isdir(_r(PREFIX_PLUGINURI + cale)):
			trimiteFisiere(raspuns.get("cod", ""), _valoareAntet(text, "cheie"), fisierePlugin(cale))


class Lucru(object):
	"""Firul unui raport: jurnalul de cadere, completarea, trimiterea, pachetul, coada. .gata, .ok (True = serverul a
	raspuns ok), .in_coada."""

	def __init__(self, raport):
		self.raport = raport
		self.gata = False
		self.ok = None
		self.in_coada = False
		self.cale_jurnal = None
		self.text = ""
		self.fir = threading.Thread(target=self.run, name="hds-plugin-extern")
		self.fir.daemon = True

	def start(self):
		self.fir.start()

	def run(self):
		try:
			nume = self.raport["antet"]["plugin"]
			self.cale_jurnal = scrieJurnalText(self.raport["jurnal_cadere"], self.raport["acum"])
			_jurnal("jurnalul de cadere al pluginului %s: %s" % (nume, self.cale_jurnal or "nescris"))
			completeaza(self.raport)
			self.text = construieste(self.raport)
			ce, raspuns = trimiteText(self.text)
			_jurnal("raportul pluginului %s: %s%s" % (nume, ce, (", codul " + str(raspuns.get("cod"))) if ce == TRIMIS else ""))
			if ce == TRIMIS:
				self.ok = True
				dupaRaspuns(self.text, ce, raspuns)
			else:
				self.ok = False
				if ce == MAI_TARZIU:
					self.in_coada = puneInCoada(self.text, self.raport["antet"]["cheie"], self.raport["acum"])
		except Exception as e:
			_jurnal("raportul: %r" % (e,))
			self.ok = False
		finally:
			self.gata = True


# ------------------------------------------------------------------ jurnalul de cadere (pe fir)

def scrieJurnalText(text, acum=None, dosare=None):
	"""enigma2_crash_<ora>.log (ca bsod.cpp si mytest.py), in primul dosar care se poate scrie. Calea, sau None."""
	acum = time.time() if acum is None else acum
	for dosar in (dosare or (_r(DOSAR_JURNALE), _r(DOSAR_REZERVA))):
		try:
			if not os.path.isdir(dosar):
				os.makedirs(dosar)
			ora = int(acum)
			for _i in range(10):
				cale = os.path.join(dosar, "enigma2_crash_%d.log" % ora)
				try:
					# "x": nu scrie peste jurnalul altei caderi din aceeasi secunda
					with open(cale, "x", encoding="utf-8", errors="backslashreplace") as f:
						f.write(text)
					return cale
				except FileExistsError:
					ora += 1
		except (IOError, OSError) as e:
			_jurnal("jurnalul nu se poate scrie in %s: %s" % (dosar, e))
	return None


# ------------------------------------------------------------------ coada (pe fir)

_NUME_COADA = re.compile(r"\A(\d{10,})-([0-9a-f]{32})-(\d+)\.txt\.gz\Z")


def coada():
	"""[(nume, ora, cheie, incercari)] din DOSAR_COADA, cel mai vechi intai."""
	try:
		nume = os.listdir(_r(DOSAR_COADA))
	except OSError:
		return []
	rez = []
	for n in nume:
		m = _NUME_COADA.match(n)
		if m:
			rez.append((n, int(m.group(1)), m.group(2), int(m.group(3))))
	rez.sort(key=lambda x: (x[1], x[0]))
	return rez


def puneInCoada(text, cheie, acum=None):
	"""Raportul netrimis in coada; cele mai vechi ies peste COADA_MAX rapoarte sau COADA_OCTETI. True daca a ramas."""
	dosar = _r(DOSAR_COADA)
	nume = "%d-%s-0.txt.gz" % (int(time.time() if acum is None else acum), cheie)
	try:
		if not os.path.isdir(dosar):
			os.makedirs(dosar)
		with open(os.path.join(dosar, nume + ".nou"), "wb") as f:
			f.write(gzip.compress(text.encode("utf-8")))
		os.rename(os.path.join(dosar, nume + ".nou"), os.path.join(dosar, nume))
	except (IOError, OSError) as e:
		_jurnal("coada rapoartelor: %s" % e)
		return False
	stricteCoada()
	return os.path.exists(os.path.join(dosar, nume))


def stricteCoada():
	toate = coada()
	marimi = {}
	for n, _o, _c, _i in toate:
		try:
			marimi[n] = os.path.getsize(os.path.join(_r(DOSAR_COADA), n))
		except OSError:
			marimi[n] = 0
	while toate and (len(toate) > COADA_MAX or sum(marimi[x[0]] for x in toate) > COADA_OCTETI):
		_sterge(toate.pop(0)[0])


def _sterge(nume):
	try:
		os.remove(os.path.join(_r(DOSAR_COADA), nume))
	except OSError:
		pass


def trimiteCoada():
	"""O trecere prin coada: trimis sau refuzat -> sters; altfel o incercare in plus (dupa COADA_INCERCARI, sters).
	(trimise, ramase)."""
	trimise = 0
	for n, ora, cheie, incercari in coada():
		cale = os.path.join(_r(DOSAR_COADA), n)
		try:
			with open(cale, "rb") as f:
				text = gzip.decompress(f.read(COADA_OCTETI)).decode("utf-8", "replace")
		except (IOError, OSError, EOFError, ValueError):
			_sterge(n)
			continue
		ce, raspuns = trimiteText(text)
		if ce == MAI_TARZIU and incercari + 1 < COADA_INCERCARI:
			try:
				os.rename(cale, os.path.join(_r(DOSAR_COADA), "%d-%s-%d.txt.gz" % (ora, cheie, incercari + 1)))
			except OSError:
				pass
			continue
		_sterge(n)
		if ce == TRIMIS:
			trimise += 1
			dupaRaspuns(text, ce, raspuns)
	return trimise, len(coada())


def _lucruCoada():
	try:
		trimise, ramase = trimiteCoada()
		_jurnal("coada rapoartelor: %d trimise, %d raman" % (trimise, ramase))
	except Exception as e:
		_jurnal("coada rapoartelor: %r" % (e,))


def porneste():
	"""Din mytest.py, la pornirea interfetei: cu rapoarte ramase in coada, ceasul de COADA_PAS_MS. Nu arunca."""
	try:
		if coada():
			_pornesteCeasCoada()
	except Exception as e:
		_jurnal("pornirea cozii: %r" % (e,))


def _pornesteCeasCoada():
	if _ceasCoada[0] is None:
		from enigma import eTimer
		t = eTimer()
		t.callback.append(_ticCoada)
		_ceasCoada[0] = t
		t.start(COADA_PAS_MS, False)


def _ticCoada():
	if not coada():
		_ceasCoada[0].stop()
		_ceasCoada[0] = None
		return
	if _firCoada[0] is not None and _firCoada[0].is_alive():
		return
	fir = threading.Thread(target=_lucruCoada, name="hds-plugin-coada")
	fir.daemon = True
	_firCoada[0] = fir
	fir.start()


# ------------------------------------------------------------------ mesajul si ecranul ramas pe jumatate (firul enigma2)

def textCauza(cod):
	return {
		"octeti-text": _("Pluginul a fost scris pentru alt fel de imagine și nu înțelege încă un răspuns al receptorului."),
		"python2": _("Pluginul e făcut pentru imaginile vechi (Python 2) și nu poate rula așa pe această imagine."),
		"modul-lipsa": _("Pluginului îi lipsește o componentă de care are nevoie."),
		"tema": _("Pluginul cere un ecran pe care tema de acum nu îl are."),
		"internet": _("Pluginul nu a putut lua date de pe internet."),
		"fisier": _("Pluginul nu a găsit un fișier sau nu a putut scrie pe disc."),
	}.get(cod) or _("Pluginul a avut o eroare internă.")


def textMesaj(nume, cod, primit):
	"""Titlul, cauza, "Receptorul merge mai departe." si fraza echipei (primit: serverul a raspuns ok)."""
	echipa = _("Echipa HD Satelit a primit datele erorii și va încerca să o rezolve.") if primit else \
		_("Datele erorii ajung la echipa HD Satelit imediat ce receptorul are internet.")
	return "%s\n%s %s %s" % (_("Pluginul extern %s a avut o eroare.") % nume, textCauza(cod),
		_("Receptorul merge mai departe."), echipa)


def _sesiune():
	try:
		from Screens.InfoBar import InfoBar
		return InfoBar.instance.session if InfoBar.instance is not None else None
	except Exception:
		return None


def _programeaza():
	"""Dupa ce C++ termina apelul: ecranul ramas pe jumatate, apoi mesajele care asteapta raspunsul serverului."""
	if _ceas[0] is None:
		from enigma import eTimer
		t = eTimer()
		t.callback.append(dupaEroare)
		_ceas[0] = t
	_ceas[0].start(0, True)


def dupaEroare(sesiune=None, mono=None):
	"""Ceasul de pe firul enigma2. True daca mai are de asteptat (ceasul porneste din nou)."""
	sesiune = sesiune or _sesiune()
	if _deInchis[0]:
		_deInchis[0] = False
		if sesiune is not None:
			try:
				inchideEcranPeJumatate(sesiune)
			except Exception as e:
				_jurnal("ecranul ramas pe jumatate: %r" % (e,))
	mono = time.monotonic() if mono is None else mono
	for a in list(_asteptari):
		lucru = a["lucru"]
		if a["arata"] and (lucru.gata or mono >= a["termen"]):
			a["arata"] = False
			primit = lucru.gata and lucru.ok is True
			try:
				if sesiune is not None:
					from Screens import HdsAnuntRetea
					HdsAnuntRetea.arata(sesiune, textMesaj(a["nume"], a["cauza"], primit), "", DURATA_MESAJ_MS)
					_jurnal("mesajul pentru %s pe ecran (%s)" % (a["nume"], "raportul primit" if primit else
						"fara raspuns de la server"))
			except Exception as e:
				_jurnal("mesajul pentru %s: %r" % (a["nume"], e))
		if not a["arata"] and lucru.gata:
			_asteptari.remove(a)
			if lucru.in_coada:
				try:
					_pornesteCeasCoada()
				except Exception as e:
					_jurnal("coada rapoartelor: %r" % (e,))
	if _asteptari and _ceas[0] is not None:
		_ceas[0].start(PAS_CEAS_MS, True)
	return bool(_asteptari)


def inchideEcranPeJumatate(sesiune):
	"""Ecranul curent a cazut cand pornea (semnul pus de Session.open): se inchide, omul ramane in cel de dinainte.
	True daca s-a inchis."""
	ecran = getattr(sesiune, "current_dialog", None)
	if ecran is None or not getattr(ecran, "hdsDeschidereEsuata", False):
		return False
	ecran.hdsDeschidereEsuata = False
	if not getattr(sesiune, "in_exec", False):
		return False
	_jurnal("ecranul %s a cazut cand pornea: se inchide" % ecran.__class__.__name__)
	sesiune.close(ecran)
	return True

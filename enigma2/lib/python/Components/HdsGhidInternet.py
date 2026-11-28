# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsGhidInternet.py: ghidul TV din internet (EPGImport, din feedul extern) pentru tara omului, intr-un singur pas.
#
# De ce (TODO 14.11 22:14, INS): ca sa aiba ghidul din internet, omul trebuia sa instaleze EPG Import din Extensii, sa
# gaseasca printre ~80 de surse pe cele ale tarii lui, sa le bifeze, sa porneasca importul si sa-l programeze. Acum un
# singur rand ("Ghidul TV din internet", in Media, in meniul ghidului si in pagina web /ghid-internet) si un OK:
#   1. EPG Import si lista surselor (epgimport-sources) se instaleaza din feed, daca lipsesc (opkg update, apoi lucrarea
#      opkg obisnuita a Extensiilor, Components/HdsExtensiiLucru.Lucrare); pluginul intra in liste fara repornirea
#      interfetei (PluginComponent.activeazaAcum, ca la Components/HdsModuleLipsa.py);
#   2. se bifeaza NUMAI sursele tarii: /etc/enigma2/epgimport.conf (alegerea EPG Import: pickle {"sources": [descrieri]});
#      alegerea de dinainte se pastreaza o data in epgimport.conf.inainte-hds;
#   3. importul pornit o data acum si programat zilnic (config.plugins.epgimport.enabled; ora ramane a pluginului).
#
# Tara omului, in ordinea aceasta:
#   - raspunsul serverului nostru de la prima pornire (Components/HdsLimbaTara.py, numai in sesiunea aceea);
#   - fusul orar (config.timezone.val; Components/HdsFusTara.py il pune singur dupa internet) prin zone.tab: Europe/Vienna
#     da Austria, chiar cu meniul in germana;
#   - limba meniului (de_DE: Germania), numai cand nu se stie altceva.
#   Cand limba meniului e a altei tari decat cea aflata (un roman in Germania, fusul din fabrica Europe/Bucharest cu
#   meniul in germana), tara nu e sigura: ecranul si pagina intreaba intre cele doua. Regula 1f: cu tara sigura nu se
#   alege nimic, un OK.
#
# Sursele se iau din fisierele instalate (/etc/epgimport/*.sources.xml), dupa inceputul descrierii, cu spatiile
# stranse; in alegere se scrie descrierea EXACTA din fisier (EPG Import compara sirurile intregi, iar unele au doua
# spatii: "Deutschland - Basis  (xz)").
#
# Tarile fara sursa libera in lista OE-Alliance (Ungaria, tarile baltice, ...) primesc un mesaj clar.
#
# Rusia, Ucraina, Belarus, Kazahstan (GTR, TODO 15.11 07:51): russian.sources.xml are cate o sursa pentru fiecare satelit
# (AMOS 4.0W, Astra 19.2E, Express 80.0E...), nu pe tara. Pentru ele se bifeaza, tot intr-un singur pas si fara
# intrebari, sursele satelitilor de la tunerele omului (NimManager, ca in ecranul tunerelor; la motor numai satelitii
# pe care omul are canale, altfel ar intra toata lista). Pozitia sursei: din descriere (ultima, "Astra 2E/2F/2G 28.2E"
# = 28.2E) sau, cand descrierea n-o are ("Eutelsat 36B/36C", "Tricolor"), din adresa channels-360E.xml.gz.
#
# Fisierul nu importa nimic din enigma la incarcare: probele de pe PC folosesc direct partea fara efecte.

import os
import pickle
import re
import xml.etree.ElementTree as ET

DOSAR_SURSE = "/etc/epgimport"
FISIER_ALEGERE = "/etc/enigma2/epgimport.conf"
SUFIX_COPIE = ".inainte-hds"
FISIER_ZONE = "/usr/share/zoneinfo/zone.tab"
PACHET_PLUGIN = "enigma2-plugin-extensions-epgimport"
PACHET_SURSE = "epgimport-sources"
DOSAR_PLUGIN = "/usr/lib/enigma2/python/Plugins/Extensions/EPGImport"
MODUL_PLUGIN = "Plugins.Extensions.EPGImport.plugin"
MARIME_MAX_SURSE = 2 * 1024 * 1024


def N_(text):
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


# Tara (ISO 3166-1) -> inceputurile descrierilor surselor ei din epgimport-sources (OE-Alliance EPGImport-Sources,
# 4eaaa70: rytec, polandAzman, spainKoala, turkish). Se compara fara deosebire de litere si cu spatiile stranse.
_DACH = ("Deutschland/Osterreich/Switzerland - Gemeinsam", "Deutschland/Osterreich/Switzerland - Sports/Film")
_CZSK = ("Ceska/Slovensko - Rozdeleny", "Ceska/Slovensko - Sportove/Filmy")
SURSE_TARII = {
	"DE": ("Deutschland - Basis",) + _DACH,
	"AT": ("Osterreich - Basis",) + _DACH,
	"CH": ("Switzerland - Basis",) + _DACH,
	"LI": ("Switzerland - Basis",) + _DACH,
	"CZ": ("Ceska - Bazicky",) + _CZSK,
	"SK": ("Slovensko - Bazicky",) + _CZSK,
	"PL": ("Polska - Podstawowy", "Polska - Dodatkowy"),
	"RO": ("Romania - Baza", "Romania - Sport/Film"),
	"MD": ("Romania - Baza", "Romania - Sport/Film"),
	"NL": ("Nederland - Basis", "Vlaanderen/Nederland - Gemeenschappelijk", "Nederland - Sport/Movies"),
	"BE": ("Vlaanderen - Basis", "Vlaanderen/Nederland - Gemeenschappelijk", "Wallonie - Telesat Base",
		"France/Wallonie - Commun"),
	"FR": ("France - TNT", "France/Wallonie - Commun", "France - Mixte", "France - Sport/Cinema"),
	"MC": ("France - TNT", "France/Wallonie - Commun", "France - Mixte", "France - Sport/Cinema"),
	"BG": ("Bulgaria",),
	"DK": ("Danmark - ",),
	"NO": ("Norge - ",),
	"SE": ("Sverige - ",),
	"FI": ("Suomi - ",),
	"GR": ("Ellada - ",),
	"CY": ("Ellada - ",),
	"IT": ("Italia - ",),
	"SM": ("Italia - ",),
	"VA": ("Italia - ",),
	"PT": ("Portugal",),
	"HR": ("Hrvatska - ",),
	"BA": ("Hrvatska - ",),
	"RS": ("Srbija/Crna Gora - ",),
	"ME": ("Srbija/Crna Gora - ",),
	"SI": ("Slovenija - ",),
	"GB": ("UK/Ireland - ",),
	"IE": ("UK/Ireland - ",),
	"ES": ("Koala 7 dias",),
	"TR": ("Open-EPG - Turkey",),
}

NUME_TARA = {
	"DE": N_("Germania"), "AT": N_("Austria"), "CH": N_("Elveția"), "LI": N_("Liechtenstein"),
	"CZ": N_("Cehia"), "SK": N_("Slovacia"), "PL": N_("Polonia"), "RO": N_("România"), "MD": N_("Republica Moldova"),
	"NL": N_("Olanda"), "BE": N_("Belgia"), "FR": N_("Franța"), "MC": N_("Monaco"), "BG": N_("Bulgaria"),
	"DK": N_("Danemarca"), "NO": N_("Norvegia"), "SE": N_("Suedia"), "FI": N_("Finlanda"), "GR": N_("Grecia"),
	"CY": N_("Cipru"), "IT": N_("Italia"), "SM": N_("San Marino"), "VA": N_("Vatican"), "PT": N_("Portugalia"),
	"HR": N_("Croația"), "BA": N_("Bosnia și Herțegovina"), "RS": N_("Serbia"), "ME": N_("Muntenegru"),
	"SI": N_("Slovenia"), "GB": N_("Marea Britanie"), "IE": N_("Irlanda"), "ES": N_("Spania"), "TR": N_("Turcia"),
	"HU": N_("Ungaria"), "UA": N_("Ucraina"), "RU": N_("Rusia"), "EE": N_("Estonia"), "LT": N_("Lituania"),
	"LV": N_("Letonia"), "LU": N_("Luxemburg"), "BY": N_("Belarus"), "KZ": N_("Kazahstan"),
}

# Fisierele de surse pe satelit (nu pe tara) -> tarile lor. russian.sources.xml (categoria "Russian XMLTV", runigma):
# canalele in rusa si ucraineana de pe fiecare satelit, de la 4.0W (AMOS) pana la 96.5E (Express-AM33).
SURSE_SATELIT = {"russian.sources.xml": ("RU", "UA", "BY", "KZ")}

# Cat poate fi pozitia sursei departe de a satelitului de la tuner, in zecimi de grad: sursele scriu Thor 1.0W, Sirius
# 4.9E, ABS 74.9E, lista satelitilor 0.8W, 4.8E, 75.0E, iar banda C sta cu o zecime mai incolo (96.5E = 966). Sub 5:
# Astra 31.5E nu trebuie sa ia Turksat 31.0E, iar Belintersat 51.5E nu trebuie sa ia 52.0E.
TOLERANTA_POZITIE = 3

_POZ_DESCRIERE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d)?)\s*°?\s*([EW])(?![A-Za-z0-9])")
_POZ_ADRESA = re.compile(r"channels-(?:[a-z]+-)?(\d{3,4})([ew])\.xml", re.I)

# limba meniului -> tara, unde partea a doua a codului nu e tara (sr_YU, en_EN, fy_x-FY)
_TARA_LIMBII = {"YU": "RS", "EN": "", "X-FY": "NL"}

TEXT_FARA_SURSA = N_("Pentru %s nu avem încă o sursă liberă de ghid din internet. Poți alege altă țară.")
TEXT_NECUNOSCUTA = N_("Nu știu încă în ce țară ești. Alege țara ta.")
TEXT_NESIGURA = N_("Alege țara ghidului: %s sau %s.")
TEXT_FARA_SATELIT = N_("Pe sateliții de la tunerele tale nu avem încă surse de ghid din internet pentru %s.")
# EPG1 (0.8.0): locul ghidului importat se socoteste dupa memoria receptorului (lib/dvb/hdsepgloc.h); cand tot s-a umplut,
# omul afla cate n-au incaput si ce poate face (eEPGCache.getExternRefused, numaratoarea importului de acum sau a ultimului)
TEXT_PLIN = N_("Ghidul TV s-a umplut la ultimul import: %d emisiuni nu au mai încăput. Alege mai puține surse în EPG Import.")


def numeTara(cod):
	n = NUME_TARA.get((cod or "").upper())
	return _t(n) if n else (cod or "").upper()


def _strans(text):
	return " ".join((text or "").split()).lower()


# ---------------------------------------------------------------- sursele (fara efecte)

def citesteSurse(dosar=None):
	"""/etc/epgimport/*.sources.xml -> [{"descriere", "categorie", "fisier"}], in ordinea fisierelor si din fisier.
	"descriere" e textul exact (asa il pune EPG Import in alegere); sursele fara descriere se sar (EPG Import le da
	numele unei adrese alese la intamplare)."""
	dosar = dosar or DOSAR_SURSE
	try:
		fisiere = sorted(f for f in os.listdir(dosar) if f.endswith(".sources.xml"))
	except OSError:
		return []
	surse = []
	for f in fisiere:
		cale = os.path.join(dosar, f)
		try:
			if os.path.getsize(cale) > MARIME_MAX_SURSE:
				continue
			radacina = ET.parse(cale).getroot()
		except (OSError, ET.ParseError):
			continue
		for cat in [radacina] + list(radacina.iter("sourcecat")):
			nume_cat = cat.get("sourcecatname", "")
			copii = cat.findall("source") if cat is radacina else cat.iter("source")
			for s in copii:
				d = s.findtext("description")
				if d and d.strip():
					surse.append({"descriere": d, "categorie": nume_cat, "fisier": f,
						"channels": s.get("channels", "")})
	return surse


def pozitieSursa(descriere, channels=""):
	"""pozitia orbitala a unei surse pe satelit, ca in NimManager (0..3599, vestul 3600 - x): ultima pozitie din
	descriere ("Astra 2E/2F/2G 28.2E" = 282, "AMOS 4.0W" = 3560, "Express 80.0°E" = 800); altfel din adresa
	channels-360E.xml.gz (numai 3-4 cifre, in zecimi: "4W" si "49E" din aceeasi lista nu spun sigur zecimile). None
	pentru o sursa fara satelit ("IPTV")."""
	gasite = _POZ_DESCRIERE.findall(descriere or "")
	if gasite:
		zecimi, parte = int(round(float(gasite[-1][0]) * 10)), gasite[-1][1]
	else:
		m = _POZ_ADRESA.search(channels or "")
		if not m:
			return None
		zecimi, parte = int(m.group(1)), m.group(2).upper()
	if zecimi > 1800:
		return None
	return (3600 - zecimi) % 3600 if parte == "W" else zecimi


def textPozitie(poz):
	"""282 -> "28.2E", 3560 -> "4.0W" """
	poz = int(poz) % 3600
	if poz > 1800:
		return "%d.%dW" % divmod(3600 - poz, 10)
	return "%d.%dE" % divmod(poz, 10)


def _distanta(a, b):
	d = abs(int(a) - int(b)) % 3600
	return min(d, 3600 - d)


def fisiereSatelit(tara):
	"""fisierele de surse pe satelit ale tarii (gol pentru tarile cu surse pe tara)"""
	tara = (tara or "").upper()
	return tuple(f for f, tari in sorted(SURSE_SATELIT.items()) if tara in tari)


def peSatelit(tara):
	return bool(fisiereSatelit(tara))


def areSursa(tara):
	"""tara are surse in epgimport-sources: pe tara (SURSE_TARII) sau pe satelit (SURSE_SATELIT)"""
	return (tara or "").upper() in SURSE_TARII or peSatelit(tara)


def sursePentru(tara, surse, pozitii=None):
	"""descrierile exacte ale surselor tarii, fara dubluri, in ordinea din fisiere; [] pentru o tara fara sursa. Pentru
	tarile cu surse pe satelit: numai sursele satelitilor din `pozitii` (satelitii de la tunere, pozitiiTunere)."""
	fisiere = fisiereSatelit(tara)
	alese = []
	if fisiere:
		for s in surse:
			d = s["descriere"]
			if s.get("fisier") not in fisiere or d in alese:
				continue
			p = pozitieSursa(d, s.get("channels", ""))
			if p is not None and any(_distanta(p, q) <= TOLERANTA_POZITIE for q in pozitii or ()):
				alese.append(d)
		return alese
	inceputuri = [_strans(p) for p in SURSE_TARII.get((tara or "").upper(), ())]
	for s in surse:
		d = s["descriere"]
		if d not in alese and any(_strans(d).startswith(p) for p in inceputuri):
			alese.append(d)
	return alese


def _areSurseSatelit(tara, surse):
	fisiere = fisiereSatelit(tara)
	return any(s.get("fisier") in fisiere and pozitieSursa(s["descriere"], s.get("channels", "")) is not None
		for s in surse)


def tariCuSursa(surse=None):
	"""codurile tarilor care au surse (in lista instalata, daca e data), in ordinea numelor. Tarile cu surse pe satelit
	apar cand fisierul lor e instalat, oricare ar fi satelitii de la tunere (mesajul spune daca nu se potriveste
	niciunul)."""
	coduri = [c for c in SURSE_TARII if surse is None or sursePentru(c, surse)]
	for tari in SURSE_SATELIT.values():
		coduri += [c for c in tari if c not in coduri and (surse is None or _areSurseSatelit(c, surse))]
	return sorted(coduri, key=lambda c: _strans(numeTara(c)))


def pozitiiDinTunere(tunere, cu_canale=()):
	"""tunere: [(pozitiile satelitilor de la tuner, motor)] -> pozitiile de luat in seama. La motor NimManager da toata
	lista satelitilor; acolo numai pozitiile pe care omul are canale (cu_canale, din lamedb), in toleranta."""
	rez = set()
	for pozitii, motor in tunere:
		for p in pozitii:
			p = int(p)
			if p < 0 or p >= 3600:
				continue
			if not motor or any(_distanta(p, q) <= TOLERANTA_POZITIE for q in cu_canale):
				rez.add(p)
	return rez


# ---------------------------------------------------------------- alegerea EPG Import

def citesteAlegerea(cale=None):
	try:
		with open(cale or FISIER_ALEGERE, "rb") as f:
			d = pickle.load(f)
		s = d.get("sources") if isinstance(d, dict) else None
		return [x for x in s if isinstance(x, str)] if isinstance(s, (list, tuple, set)) else []
	except Exception:
		return []


def scrieAlegerea(descrieri, cale=None):
	"""scrie alegerea EPG Import (acelasi format ca EPGConfig.storeUserSettings), prin fisier temporar si mutare; prima
	data pastreaza alegerea de dinainte in <cale>.inainte-hds"""
	cale = cale or FISIER_ALEGERE
	copie = cale + SUFIX_COPIE
	if os.path.exists(cale) and not os.path.exists(copie):
		try:
			with open(cale, "rb") as a, open(copie, "wb") as b:
				b.write(a.read())
		except OSError as e:
			print("[HdsGhidInternet] copia alegerii de dinainte: %s" % e)
	tmp = cale + ".hds-tmp"
	with open(tmp, "wb") as f:
		pickle.dump({"sources": list(descrieri)}, f, pickle.HIGHEST_PROTOCOL)
		f.flush()
		try:
			os.fsync(f.fileno())
		except OSError:
			pass
	os.replace(tmp, cale)


# ---------------------------------------------------------------- tara omului (fara efecte)

def zoneTari(cale=None, text=None):
	"""zone.tab -> {fus: tara}; {} daca lipseste"""
	if text is None:
		try:
			with open(cale or FISIER_ZONE, "r", encoding="utf-8") as f:
				text = f.read(256 * 1024)
		except (IOError, OSError):
			return {}
	zone = {}
	for rand in text.splitlines():
		if not rand or rand.startswith("#"):
			continue
		c = rand.split("\t")
		if len(c) >= 3 and len(c[0]) == 2:
			zone[c[2].strip()] = c[0].upper()
	return zone


def fusDinNume(valoare, lista, legatura=""):
	"""config.timezone.val tine numele din ecran (/etc/timezone.xml, Components/Timezones.py: [(nume, fus)]), nu fusul:
	numele -> fusul ("Europe/Vienna"). Rezerva: tinta legaturii /etc/localtime (.../zoneinfo/Europe/Vienna); altfel
	valoarea, cand e deja un fus."""
	for nume, fus in lista or ():
		if nume == valoare and fus:
			return fus
	if legatura and "/zoneinfo/" in legatura:
		return legatura.split("/zoneinfo/", 1)[1]
	return valoare or ""


def taraDinLimba(limba):
	"""de_DE -> DE, cs_CZ -> CZ, sr_YU -> RS; "" pentru engleza si pentru ce nu e un cod de tara"""
	if not isinstance(limba, str) or "_" not in limba:
		return ""
	c = limba.split("_", 1)[1].upper()
	if c in _TARA_LIMBII:
		return _TARA_LIMBII[c]
	return c if len(c) == 2 and c.isalpha() else ""


def _limbaTarii(tara):
	try:
		from Components.HdsLimbaTara import limbaTarii
	except ImportError:
		try:
			from HdsLimbaTara import limbaTarii
		except ImportError:
			return ""
	return limbaTarii(tara)


def taraOmului(server="", fus="", limba="", zone=None):
	"""{"tara": codul sigur sau "", "candidati": [coduri], "sigur": bool}. server: tara aflata la prima pornire
	(HdsLimbaTara); fus: config.timezone.val; limba: config.osd.language."""
	t_fus = (zone or {}).get(fus or "", "")
	t_limba = taraDinLimba(limba)
	principala = (server or "").upper() or t_fus or t_limba
	candidati = []
	for c in (principala, t_limba):
		if c and c not in candidati:
			candidati.append(c)
	sigur = bool(principala) and (not t_limba or t_limba == principala or _limbaTarii(principala) == limba)
	return {"tara": principala if sigur else "", "candidati": candidati, "sigur": sigur}


# ---------------------------------------------------------------- pe receptor

_STARE = {"faza": "", "mesaj": "", "tara": "", "lucru": None}
_ASCULTATORI = []

GATA = "gata"
EROARE = "eroare"
LUCREAZA = ("actualizez", "instalez", "aplic")


def asculta(functie):
	if functie not in _ASCULTATORI:
		_ASCULTATORI.append(functie)


def lasa(functie):
	if functie in _ASCULTATORI:
		_ASCULTATORI.remove(functie)


def _pune(faza, mesaj, tara=None):
	_STARE["faza"] = faza
	_STARE["mesaj"] = mesaj
	if tara is not None:
		_STARE["tara"] = tara
	print("[HdsGhidInternet] %s: %s" % (faza, mesaj))
	for f in list(_ASCULTATORI):
		try:
			f()
		except Exception as e:
			print("[HdsGhidInternet] ascultator: %r" % (e,))


def inLucru():
	return _STARE["faza"] in LUCREAZA


def instalat(dosar_plugin=None, dosar_surse=None):
	try:
		return os.path.isdir(dosar_plugin or DOSAR_PLUGIN) and any(
			f.endswith(".sources.xml") for f in os.listdir(dosar_surse or DOSAR_SURSE))
	except OSError:
		return False


def _config():
	from Components.config import config
	return config


def taraAcum():
	"""taraOmului cu datele receptorului"""
	server = ""
	try:
		from Components import HdsLimbaTara
		s = HdsLimbaTara.stare()
		if s.get("stare") == HdsLimbaTara.GATA:
			server = s.get("tara") or ""
	except Exception:
		pass
	c = _config()
	fus = limba = ""
	try:
		lista = []
		try:
			from Components.Timezones import timezones
			lista = list(timezones.timezones)
		except Exception:
			pass
		legatura = os.path.realpath("/etc/localtime") if os.path.exists("/etc/localtime") else ""
		fus = fusDinNume(c.timezone.val.value, lista, legatura)
	except Exception:
		pass
	try:
		limba = c.osd.language.value
	except Exception:
		pass
	return taraOmului(server, fus, limba, zoneTari())


def pozitiiTunere():
	"""pozitiile satelitilor de la tunerele de satelit (configuratia tunerelor, NimManager.getSatListForNim); la motor
	numai cele cu canale in lamedb. Rezerva, cand NimManager nu raspunde: pozitiile salvate la tunere in settings si cele
	cu canale (Components/HdsSatelitiImagine, ca la unirea satelitilor)."""
	try:
		from Components.NimManager import nimmanager
		tunere = []
		for slot in range(len(nimmanager.nim_slots)):
			if not nimmanager.nim_slots[slot].isCompatible("DVB-S"):
				continue
			pozitii = [x[0] for x in nimmanager.getSatListForNim(slot)]
			if pozitii:
				tunere.append((pozitii, bool(nimmanager.getRotorSatListForNim(slot))))
		cu_canale = ()
		if any(motor for _p, motor in tunere):
			from Components.HdsSatelitiImagine import pozitii_lamedb
			cu_canale = pozitii_lamedb()
		return pozitiiDinTunere(tunere, cu_canale)
	except Exception as e:
		print("[HdsGhidInternet] satelitii de la tunere: %r" % (e,))
	try:
		from Components.HdsSatelitiImagine import pozitii_lamedb, pozitii_setari
		return set(pozitii_setari()) | set(pozitii_lamedb())
	except Exception as e:
		print("[HdsGhidInternet] satelitii din settings: %r" % (e,))
		return set()


def _programare():
	"""(programat, "HH:MM", ultimul import) din setarile EPG Import, cand pluginul e incarcat"""
	try:
		ep = _config().plugins.epgimport
		ora = "%02d:%02d" % tuple(ep.wakeup.value[:2])
		programat = bool(ep.enabled.value)
	except Exception:
		return False, "", ""
	ultimul = ""
	try:
		ultimul = _config().plugins.extra_epgimport.last_import.value
	except Exception:
		pass
	return programat, ora, ultimul


def emisiuniRefuzate():
	"""cate emisiuni n-au mai incaput in ghid la importul de acum sau la ultimul; 0 cand a intrat tot sau fara cache"""
	try:
		from enigma import eEPGCache
		e = eEPGCache.getInstance()
		return max(0, int(e.getExternRefused())) if e is not None and hasattr(e, "getExternRefused") else 0
	except Exception:
		return 0


def textPlin(n):
	"""textul pentru om cand ghidul s-a umplut, "" cand a intrat tot"""
	return _t(TEXT_PLIN) % n if n else ""


def stare():
	"""totul pentru ecran si pentru pagina web"""
	t = taraAcum()
	surse = citesteSurse() if instalat() else []
	programat, ora, ultimul = _programare()
	tara = _STARE["tara"] or t["tara"]
	lista = surse or None
	pe_satelit = peSatelit(tara)
	pozitii = pozitiiTunere() if pe_satelit else set()
	return {
		"tara": tara, "nume": numeTara(tara) if tara else "", "sigur": t["sigur"] or bool(_STARE["tara"]),
		"candidati": [{"cod": c, "nume": numeTara(c), "are": areSursa(c)} for c in t["candidati"]],
		"tari": [{"cod": c, "nume": numeTara(c)} for c in tariCuSursa(lista)],
		"are_sursa": areSursa(tara),
		"pe_satelit": pe_satelit, "sateliti": [textPozitie(p) for p in sorted(pozitii, key=lambda x: x - 3600 if x > 1800 else x)],
		"instalat": instalat(), "bifate": citesteAlegerea(),
		"surse_tarii": sursePentru(tara, surse, pozitii) if tara else [],
		"programat": programat, "ora": ora, "ultimul": ultimul,
		"faza": _STARE["faza"], "mesaj": _STARE["mesaj"], "in_lucru": inLucru(),
		"refuzate": emisiuniRefuzate(),
	}


def textStare(s=None):
	"""starea pe cateva randuri, pentru ecran"""
	s = s or stare()
	r = []
	if s["tara"]:
		r.append(_t("Țara: %s") % s["nume"])
		if not s["are_sursa"]:
			r.append(_t(TEXT_FARA_SURSA) % s["nume"])
	elif len(s["candidati"]) > 1:
		r.append(_t(TEXT_NESIGURA) % (s["candidati"][0]["nume"], s["candidati"][1]["nume"]))
	else:
		r.append(_t(TEXT_NECUNOSCUTA))
	if s.get("pe_satelit"):
		r.append(_t("Sateliții de la tunere: %s") % (", ".join(s.get("sateliti") or ()) or _t("niciunul")))
		if s["instalat"] and not s["surse_tarii"]:
			r.append(_t(TEXT_FARA_SATELIT) % s["nume"])
	if s["surse_tarii"]:
		r.append(_t("Sursele: %s") % ", ".join(" ".join(d.split()) for d in s["surse_tarii"]))
	if s["programat"] and s["bifate"]:
		r.append(_t("Importul se face zilnic la %s.") % s["ora"])
	if s["ultimul"]:
		r.append(_t("Ultimul import: %s") % s["ultimul"])
	if s.get("refuzate"):
		r.append(textPlin(s["refuzate"]))
	if s["mesaj"]:
		r.append(s["mesaj"])
	return "\n".join(r)


def porneste(tara, session=None):
	"""Un OK: instaleaza (daca lipseste), bifeaza sursele tarii, porneste importul si il programeaza zilnic. None daca a
	pornit (rezultatul vine prin asculta/stare), altfel textul pentru om."""
	tara = (tara or "").upper()
	if inLucru():
		return _t("Ghidul TV din internet se pregătește deja. Așteaptă puțin.")
	if not areSursa(tara):
		return _t(TEXT_FARA_SURSA) % numeTara(tara) if tara else _t(TEXT_NECUNOSCUTA)
	_STARE["tara"] = tara
	if instalat():
		_aplica(tara, session)
	else:
		_actualizeaza(tara, session)
	return None


def _opkgOcupat():
	try:
		from Components.HdsActualizari import opkg_ocupat
		return bool(opkg_ocupat("/"))
	except Exception as e:
		print("[HdsGhidInternet] zavorul opkg: %r" % (e,))
		return False


def _actualizeaza(tara, session):
	if _opkgOcupat():
		_pune(EROARE, _t("Alt program instalează acum pachete. Încearcă din nou peste un minut."))
		return
	from Components.Ipkg import IpkgComponent
	ipkg = IpkgComponent()
	_STARE["lucru"] = ipkg
	_pune("actualizez", _t("Se citește lista pachetelor..."), tara)

	def gata(eveniment, parametru):
		if eveniment in (IpkgComponent.EVENT_DONE, IpkgComponent.EVENT_ERROR):
			ipkg.removeCallback(gata)
			# o lista cazuta (fara internet) se vede la instalare, cu motivul opkg
			_instaleaza(tara, session)
	ipkg.addCallback(gata)
	ipkg.startCmd(IpkgComponent.CMD_UPDATE)


def planInstalare(argumente):
	"""planul lucrarii opkg (Components/HdsExtensiiLucru.Lucrare), ca la Components/HdsModuleLipsa.planModul"""
	titlu = "EPG Import"
	pachete = [PACHET_PLUGIN, PACHET_SURSE]
	return {"fel": "instaleaza", "titlu": titlu, "nume": titlu, "subtitlu": _t("Ghidul TV din internet"), "icoana": "altele",
		"randuri": [], "nota": "", "externe": [], "notaCuloare": "", "buton": N_("Instalează"), "argumente": argumente,
		"repornire": False, "pachete": pachete,
		"tinte": [{"nume": p, "titlu": p, "la": "", "de": "", "acces": False} for p in pachete], "automat": True}


def _instaleaza(tara, session):
	from Components import HdsExtensiiLucru as X
	from Components.Ipkg import opkgArguments
	argumente = opkgArguments("install", [PACHET_PLUGIN, PACHET_SURSE])
	if argumente is None:
		_pune(EROARE, _t("EPG Import nu se poate instala."))
		return
	l = X.Lucrare(planInstalare(argumente))
	_STARE["lucru"] = l
	_pune("instalez", _t("Se instalează EPG Import..."), tara)

	def ascultator(eveniment, *date):
		if eveniment != "gata":
			return
		l.lasa(ascultator)
		rez = getattr(l, "rezultat", None) or {}
		if not instalat():
			_pune(EROARE, _t("EPG Import nu s-a instalat: %s") % (rez.get("stare") or _t("Operațiunea nu a reușit.")))
			return
		_aplica(tara, session)
	l.asculta(ascultator)
	l.porneste()


def activeazaPlugin(session, plugins=None):
	"""EPG Import instalat acum intra in liste fara repornirea interfetei (pornirea lui de sesiune, autoStartTimer)"""
	try:
		if plugins is None:
			from Components.PluginComponent import plugins
		cai = [c for c in getattr(plugins, "amanateToate", {}) if (c or "").rstrip("/").endswith("/Extensions/EPGImport")]
		if cai and hasattr(plugins, "activeazaAcum"):
			return plugins.activeazaAcum(cai, session)
	except Exception as e:
		print("[HdsGhidInternet] pornirea pluginului: %r" % (e,))
	return []


def _aplica(tara, session):
	_pune("aplic", _t("Se bifează sursele..."), tara)
	pe_satelit = peSatelit(tara)
	alese = sursePentru(tara, citesteSurse(), pozitiiTunere() if pe_satelit else None)
	if not alese:
		if pe_satelit:
			_pune(EROARE, _t(TEXT_FARA_SATELIT) % numeTara(tara))
		else:
			_pune(EROARE, _t("Lista surselor EPG Import nu are încă surse pentru %s.") % numeTara(tara))
		return
	try:
		scrieAlegerea(alese)
	except OSError as e:
		_pune(EROARE, _t("Alegerea surselor nu s-a putut scrie: %s") % e)
		return
	# instalat acum, sau mai demult din Extensii fara repornirea interfetei: pluginul amanat porneste acum
	activeazaPlugin(session)
	try:
		import importlib
		P = importlib.import_module(MODUL_PLUGIN)
		from Components.config import configfile
		ep = _config().plugins.epgimport
		ep.enabled.value = True
		ep.enabled.save()
		configfile.save()
		if getattr(P, "autoStartTimer", None) is None and session is not None:
			P.autostart(0, session=session)
		temporizator = getattr(P, "autoStartTimer", None)
		if temporizator is None:
			_pune(EROARE, _t("Sursele sunt bifate; importul pornește după repornirea interfeței."))
			return
		temporizator.update()
		imp = getattr(P, "epgimport", None)
		if imp is not None and imp.isImportRunning():
			text = _t("Importul era deja în lucru.")
		else:
			temporizator.runImport()
			text = _t("Importul a început.")
	except Exception as e:
		print("[HdsGhidInternet] pornirea importului: %r" % (e,))
		_pune(EROARE, _t("Sursele sunt bifate, dar importul nu a pornit: %s") % e)
		return
	ora = _programare()[1]
	_pune(GATA, _t("Ghidul TV din internet pentru %s e pornit. %s Se repetă zilnic la %s.") % (numeTara(tara), text, ora))

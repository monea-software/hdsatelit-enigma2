# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLimbaTara.py: limba asistentului de la prima pornire, dupa tara aflata din adresa de internet.
#
# Regula: limba tarii in care e receptorul. Cand tara nu se stie (fara retea, serverul nu raspunde, adresa fara loc in
# baza) sau limba tarii nu e intre limbile imaginii, engleza. Romana numai pentru Romania si Moldova. De ce: cu romana
# din fabrica, un om din alta tara vedea la prima pornire o limba pe care nu o recunostea.
#
# Cum merge:
#   - laPornire(limba) din Components/SetupDevices.py, imediat dupa ce config.osd.language si-a luat valoarea din
#     settings: tine minte daca omul are deja o limba aleasa si, numai la prima pornire (config.misc.firstrun) fara
#     una, porneste cautarea tarii pe un fir. Cu asistentul terminat (firstrun False) nu se intreaba nimic.
#   - limba aleasa de om = randul config.osd.language din settings, diferit de valoarea din fabrica (setarile puse la
#     loc din copie, limba schimbata din pagina web). Un rand egal cu valoarea din fabrica il scrie si
#     HdsCopieSetari.fixeaza_setari (save_forced) la fiecare pornire, chiar cu asistentul neterminat, deci el nu
#     inseamna o alegere. Alegerea facuta aici NU se scrie in config.osd.language: o scrie asistentul la VERDE.
#   - firul: asteapta ruta implicita (HdsLoculInternet.retea, numai tabelele nucleului, nicio conexiune) cel mult
#     ASTEPTARE_RETEA_S, apoi un GET spre serverul nostru, aceeasi adresa ca locul antenei (HdsLoculInternet.ADRESA),
#     cu TIMP_CERERE_S. Din raspuns se ia numai codul tarii; orasul si coordonatele nu se pastreaza si nu se scriu.
#     La o eroare de retea se reincearca dupa PAUZA_S, pana la TERMEN_S de la pornirea firului: dupa flash ceasul
#     porneste de la ora salvata (fake-hwclock) si certificatul serverului poate parea inca nevalabil pana pune
#     Components/HdsCeas.py ora din NTP. Nimic nu asteapta firul: pornirea merge mai departe.
#   - asistentul (Screens/HdsStartWizard.py) cere limbaDeInceput(coduri) cand se deschide: limba omului, limba tarii
#     daca firul a terminat, altfel engleza. Cat firul lucreaza (inLucru), asistentul se uita din nou la INTERVAL_MS si
#     pune limbaDupaTara(coduri) numai daca omul nu a atins randul limbii si e inca pe prima pagina.
#   - un rand in jurnalul interfetei: ce limba si de ce (codul tarii, niciodata adresa, orasul sau coordonatele).
#
# Fisierul nu importa nimic din enigma la incarcare: probele de pe PC il folosesc direct (reteaua, cererea, ceasul si
# firul se pot inlocui).

import json
import threading
import time

ROMANA = "ro_RO"
ENGLEZA = "en_EN"

# cat asteapta firul ruta implicita (DHCP poate veni dupa pornirea interfetei)
ASTEPTARE_RETEA_S = 20.0
PAS_RETEA_S = 0.5
# timpul unei cereri (ca la Components/HdsLoculInternet.py, aflarea numelui DNS nu e marginita de el; termenul de mai
# jos opreste firul oricum)
TIMP_CERERE_S = 3.0
PAUZA_S = 2.0
# dupa atat timp de la pornirea firului tara nu se mai cauta, iar un raspuns venit mai tarziu nu se mai ia
TERMEN_S = 90.0
# cat de des se uita asistentul daca firul a terminat
INTERVAL_MS = 500

NIMIC = "nimic"
OM = "om"
LUCREAZA = "lucreaza"
GATA = "gata"

# de ce (in jurnal)
DIN_SERVER = "aflata de la serverul HD Satelit"
FARA_RETEA = "fara retea"
NEGASIT = "adresa fara loc in baza serverului"
STRICAT = "raspunsul serverului nu se poate folosi"
TERMEN = "serverul nu a raspuns la timp"

# Tara (ISO 3166-1, doua litere) -> limba din cele 33 ale imaginii (Components/Language.py, LIMBI_COMPLETE): limba
# oficiala sau a majoritatii. O tara care nu e aici primeste engleza. Frizona (fy_x-FY) nu are tara a ei.
LIMBA_TARII = {
	"RO": "ro_RO", "MD": "ro_RO",
	"DE": "de_DE", "AT": "de_DE", "CH": "de_DE", "LI": "de_DE", "LU": "de_DE",
	"FR": "fr_FR", "MC": "fr_FR",
	"ES": "es_ES", "MX": "es_ES", "AR": "es_ES", "CO": "es_ES", "CL": "es_ES", "PE": "es_ES", "VE": "es_ES",
	"EC": "es_ES", "GT": "es_ES", "CU": "es_ES", "BO": "es_ES", "DO": "es_ES", "HN": "es_ES", "PY": "es_ES",
	"SV": "es_ES", "NI": "es_ES", "CR": "es_ES", "PA": "es_ES", "UY": "es_ES", "PR": "es_ES", "GQ": "es_ES",
	"IT": "it_IT", "SM": "it_IT", "VA": "it_IT",
	"HU": "hu_HU",
	"CZ": "cs_CZ",
	"PL": "pl_PL",
	"PT": "pt_PT", "BR": "pt_PT", "AO": "pt_PT", "MZ": "pt_PT", "CV": "pt_PT", "GW": "pt_PT", "ST": "pt_PT",
	"TL": "pt_PT",
	"NL": "nl_NL", "BE": "nl_NL", "SR": "nl_NL", "AW": "nl_NL", "CW": "nl_NL", "SX": "nl_NL",
	"RU": "ru_RU", "BY": "ru_RU", "KZ": "ru_RU", "KG": "ru_RU",
	"TR": "tr_TR",
	"SK": "sk_SK",
	"HR": "hr_HR", "BA": "hr_HR",
	"RS": "sr_YU", "ME": "sr_YU",
	"SI": "sl_SI",
	"GR": "el_GR", "CY": "el_GR",
	"SE": "sv_SE", "AX": "sv_SE",
	"DK": "da_DK", "GL": "da_DK", "FO": "da_DK",
	"NO": "no_NO", "SJ": "no_NO",
	"FI": "fi_FI",
	"EE": "et_EE",
	"LT": "lt_LT",
	"LV": "lv_LV",
	"AD": "ca_AD",
	"IS": "is_IS",
	"UA": "uk_UA",
	"UZ": "uz_UZ",
	"AL": "sq_AL", "XK": "sq_AL",
	"BG": "bg_BG",
	"AE": "ar_AE", "SA": "ar_AE", "EG": "ar_AE", "IQ": "ar_AE", "JO": "ar_AE", "KW": "ar_AE", "LB": "ar_AE",
	"LY": "ar_AE", "OM": "ar_AE", "QA": "ar_AE", "SY": "ar_AE", "YE": "ar_AE", "BH": "ar_AE", "PS": "ar_AE",
	"SD": "ar_AE", "DZ": "ar_AE", "MA": "ar_AE", "TN": "ar_AE", "MR": "ar_AE",
}

# cod si corp: raspunsul serverului (HTTP 200 sau 404), pastrat pentru fusul orar (Components/HdsFusTara.py), ca la
# prima pornire sa plece o singura cerere pentru limba si fus
_STARE = {"stare": NIMIC, "tara": "", "motiv": "", "limba_om": "", "pornit": 0.0, "cod": None, "corp": b""}
_ZAVOR = threading.Lock()


def jurnal(text):
	print("[HdsLimbaTara] %s" % text)


def stare():
	"""copie a starii (pentru probe si pentru jurnalul de diagnostic)"""
	with _ZAVOR:
		return dict(_STARE)


def _pune(**valori):
	with _ZAVOR:
		_STARE.update(valori)


# ---------------------------------------------------------------- alegerea (fara efecte)

def limbaTarii(tara):
	"""codul tarii ("TR", "md") -> limba din imagine ("tr_TR", "ro_RO"); engleza cand tara nu se stie sau limba ei nu
	e in imagine"""
	if not isinstance(tara, str):
		return ENGLEZA
	return LIMBA_TARII.get(tara.strip().upper(), ENGLEZA)


def alege(tara, coduri=None):
	"""limba tarii, numai dintre `coduri` (limbile din lista asistentului; pe Vu+ Solo SE cu partea a doua numai cele
	cu catalog): altfel engleza, iar fara engleza in lista, prima limba din ea"""
	limba = limbaTarii(tara)
	if coduri:
		coduri = list(coduri)
		if limba not in coduri:
			limba = ENGLEZA if ENGLEZA in coduri else coduri[0]
	return limba


def aleasaDeOm(element):
	"""limba din settings aleasa de om ("" daca nu e): randul config.osd.language, diferit de valoarea din fabrica"""
	valoare = getattr(element, "saved_value", None)
	if not isinstance(valoare, str) or not valoare.strip():
		return ""
	if valoare == getattr(element, "default", None):
		return ""
	return valoare


def taraDinRaspuns(corp, marime_max=4096):
	"""corpul raspunsului (octeti) -> codul tarii ("RO"); ValueError daca nu se poate folosi. Numai campul "tara"."""
	if not isinstance(corp, (bytes, bytearray)) or len(corp) > marime_max:
		raise ValueError("raspuns lipsa sau prea mare")
	try:
		d = json.loads(bytes(corp).decode("utf-8"))
	except (UnicodeDecodeError, ValueError):
		raise ValueError("raspunsul nu e JSON")
	tara = d.get("tara") if isinstance(d, dict) else None
	if not isinstance(tara, str) or len(tara) != 2 or not all("A" <= c <= "Z" for c in tara.upper()):
		raise ValueError("codul tarii lipseste sau nu e bun")
	return tara.upper()


def _deCe(tara, motiv, limba):
	if tara and limba == limbaTarii(tara):
		return "tara %s, %s" % (tara, motiv)
	if tara:
		return "tara %s nu are limba ei intre limbile din lista, %s" % (tara, motiv)
	return "tara nu se stie (%s)" % motiv


# ---------------------------------------------------------------- cautarea tarii (pe fir)

def _locul():
	from Components import HdsLoculInternet
	return HdsLoculInternet


def cautaTara(retea_=None, citeste_url=None, ceas=None, dormi=None, adresa=None):
	"""Blocanta: numai pe fir. -> (tara, motiv); tara "" cand nu se stie. `retea_()`, `citeste_url(adresa, timp,
	limita)` -> (cod HTTP, corp), `ceas()` si `dormi(s)` se inlocuiesc in probe. Termenele se socotesc pe ceasul monoton:
	ora din NTP muta ceasul obisnuit cu zile inainte chiar in cazul pentru care se reincearca (certificatul)."""
	ceas = ceas or time.monotonic
	dormi = dormi or time.sleep
	if retea_ is None or citeste_url is None or adresa is None:
		L = _locul()
		retea_ = retea_ or L.retea
		citeste_url = citeste_url or L._citesteUrl
		adresa = adresa or L.ADRESA
	inceput = ceas()
	while not retea_():
		if ceas() - inceput >= ASTEPTARE_RETEA_S:
			return "", FARA_RETEA
		dormi(PAS_RETEA_S)
	while True:
		try:
			cod, corp = citeste_url(adresa, TIMP_CERERE_S, 4096)
		except Exception as e:
			# fara raspuns: ceasul in urma (certificat), DNS, serverul cazut; se reincearca pana la termen
			motiv = "eroare de retea %s" % type(e).__name__
			if ceas() - inceput + PAUZA_S >= TERMEN_S:
				return "", motiv
			dormi(PAUZA_S)
			continue
		if cod in (200, 404):
			_pune(cod=cod, corp=bytes(corp or b"")[:4096] if cod == 200 else b"")
		if ceas() - inceput > TERMEN_S:
			return "", TERMEN
		if cod == 404:
			return "", NEGASIT
		if cod != 200:
			return "", "serverul a raspuns HTTP %s" % cod
		try:
			return taraDinRaspuns(corp), DIN_SERVER
		except ValueError:
			return "", STRICAT


def _lucreaza(**k):
	try:
		tara, motiv = cautaTara(**k)
	except Exception as e:
		tara, motiv = "", "eroare %s" % type(e).__name__
	_pune(stare=GATA, tara=tara, motiv=motiv)
	jurnal("cautarea tarii s-a terminat: %s" % (("tara %s, %s" % (tara, motiv)) if tara else motiv))


def porneste(fir=None, **k):
	"""porneste cautarea pe un fir daemon (`fir(functie)` se inlocuieste in probe); nu asteapta"""
	_pune(stare=LUCREAZA, tara="", motiv="", pornit=time.monotonic())

	def functie():
		_lucreaza(**k)
	if fir is not None:
		fir(functie)
		return
	t = threading.Thread(target=functie, name="HdsLimbaTara")
	t.daemon = True
	t.start()


def _primaPornire():
	"""config.misc.firstrun (Screens/StartWizard.py); False daca nu exista"""
	try:
		from Components.config import config
		el = config.misc.content.items.get("firstrun")
		return bool(el is not None and el.value)
	except Exception:
		return False


def laPornire(element, prima=None, **k):
	"""Din Components/SetupDevices.py, dupa ce config.osd.language (`element`) si-a citit randul din settings. Nu arunca."""
	try:
		if prima is None:
			prima = _primaPornire()
		_pune(stare=NIMIC, tara="", motiv="", limba_om="", cod=None, corp=b"")
		if not prima:
			return
		om = aleasaDeOm(element)
		if om:
			_pune(stare=OM, limba_om=om)
			jurnal("prima pornire cu limba aleasa deja de om (%s, din setari): tara nu se cauta" % om)
			return
		porneste(**k)
	except Exception as e:
		jurnal("cautarea tarii nu a pornit: %r" % (e,))


# ---------------------------------------------------------------- ce cere asistentul

def inLucru():
	return stare()["stare"] == LUCREAZA


def limbaDeInceput(coduri):
	"""limba cu care se deschide asistentul, dintre `coduri`, cu un rand in jurnal"""
	s = stare()
	if s["stare"] == OM and s["limba_om"] in (coduri or ()):
		jurnal("limba de inceput %s: aleasa deja de om (setari)" % s["limba_om"])
		return s["limba_om"]
	if s["stare"] == GATA:
		limba = alege(s["tara"], coduri)
		jurnal("limba de inceput %s: %s" % (limba, _deCe(s["tara"], s["motiv"], limba)))
		return limba
	limba = alege("", coduri)
	if s["stare"] == LUCREAZA:
		jurnal("limba de inceput %s pana raspunde serverul (tara se cauta inca)" % limba)
	elif s["stare"] == OM:
		jurnal("limba de inceput %s: limba aleasa de om (%s) nu e in lista" % (limba, s["limba_om"]))
	else:
		jurnal("limba de inceput %s: tara nu s-a cautat" % limba)
	return limba


def limbaDupaTara(coduri):
	"""limba tarii dintre `coduri`, dupa ce firul a terminat (None cat inca lucreaza sau daca nu a pornit)"""
	s = stare()
	if s["stare"] != GATA:
		return None
	return alege(s["tara"], coduri)


def deCe(coduri):
	"""motivul alegerii, pentru randul din jurnal al asistentului ("" daca firul nu a terminat)"""
	s = stare()
	if s["stare"] != GATA:
		return ""
	return _deCe(s["tara"], s["motiv"], alege(s["tara"], coduri))

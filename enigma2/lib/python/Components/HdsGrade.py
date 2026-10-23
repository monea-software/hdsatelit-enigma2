# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsGrade.py - pozitia orbitala a satelitilor si coordonatele locului antenei, scrise in limba meniului.
#
# Pana la 0.2.5 fiecare ecran isi scria singur pozitiile: cu literele romanesti (E / V) si cu virgula in orice limba,
# altele cu W englezesc sau cu punct. Cine avea meniul in engleza vedea „26,11 V" langa „19,2°E" si „30,0°V". Acum
# ecranele, bara de informatii si paginile web iau textul de aici, deci aceeasi pozitie se scrie peste tot la fel:
#   - literele trec prin traduceri: pozitia orbitala prin tiparele „%s E" / „%s V" (traduse deja in cele 13 limbi,
#     aceleasi ca in listele DAB+ / DVB-T2: „%s°E", „%s°W", „%s°O"...), coordonatele locului prin cele patru tipare
#     TIPAR_NORD ... TIPAR_LON_VEST de mai jos;
#   - separatorul zecimal e al limbii meniului, din acelasi tabel ca bara de informatii
#     (Components/Converter/HdsLang.py, cheia _dec): punct in engleza, virgula in romana si in celelalte 11 limbi;
#   - un tipar netradus (limbile fara traducere) sau stricat (altceva decat un singur %s) nu ajunge pe ecran: in
#     romana ramane forma romaneasca („19,2°E", „5,0°V", „44,43 N, 26,11 E"), in celelalte limbi literele
#     internationale N, S, E, W;
#   - ce scrie omul (de pilda emisfera din pagina DAB+ / DVB-T2) se citeste cu emisfera(): E si V ca pana acum, plus W
#     si literele limbii meniului.
# Numai textul aratat se schimba: settings, lamedb, satellites.xml, fisierele listelor si comenzile motorului lucreaza
# cu numere, ca inainte.
#
# Limba: config.osd.language, citita din modulul deja incarcat (ca bara de informatii, Converter/HdsCommon.py); pe PC,
# fara setari, „ro" (implicitul imaginii, Components/SetupDevices.py). Traducerea: functia _ din builtins, cautata la
# fiecare apel (la schimbarea limbii Components/Language.py pune alta).
#
# Se compileaza pe Python 2.7 si 3.x (bara de informatii il cheama); nicio functie publica nu arunca exceptie.
import re
import sys

GRAD = u"°"


def N_(text):
	return text


# pozitia orbitala: aceleasi msgid ca in Hds/DabT2/tuner.py („19,2°E", „5,0°V"; in engleza „5.0°W")
TIPAR_EST = N_("%s E")
TIPAR_VEST = N_("%s V")
# coordonatele locului antenei („44,43 N, 26,11 E"); paranteza e numai pentru traducator: se traduce doar tiparul
TIPAR_NORD = N_("%s N (latitudine nordică)")
TIPAR_SUD = N_("%s S (latitudine sudică)")
TIPAR_LON_EST = N_("%s E (longitudine estică)")
TIPAR_LON_VEST = N_("%s V (longitudine vestică)")

# formele de rezerva, cand tiparul nu e tradus sau traducerea e stricata
ROMANA = {
	TIPAR_EST: u"%s°E", TIPAR_VEST: u"%s°V",
	TIPAR_NORD: u"%s N", TIPAR_SUD: u"%s S", TIPAR_LON_EST: u"%s E", TIPAR_LON_VEST: u"%s V",
}
INTERNATIONAL = {
	TIPAR_EST: u"%s°E", TIPAR_VEST: u"%s°W",
	TIPAR_NORD: u"%s N", TIPAR_SUD: u"%s S", TIPAR_LON_EST: u"%s E", TIPAR_LON_VEST: u"%s W",
}

LIMBA_IMPLICITA = "ro"

try:
	_text = unicode  # noqa: F821 (Python 2)
except NameError:
	_text = str

# separatorul zecimal pe codul limbii; tabelul limbii se incarca o singura data
_SEPARATOARE = {}


def _u(s):
	if isinstance(s, _text):
		return s
	if isinstance(s, bytes):
		return s.decode("utf-8", "replace")
	return _text(s)


# ---------------------------------------------------------------- limba

def _hdsLang():
	"""tabelele de limba ale barei de informatii (Components/Converter/HdsLang.py); None daca nu se pot incarca"""
	try:
		from Components.Converter import HdsLang
		return HdsLang
	except ImportError:
		pass
	try:
		from Converter import HdsLang  # pe PC, in teste, Components e chiar dosarul modulului
		return HdsLang
	except ImportError:
		return None


def codLimba(valoare):
	"""valoarea din config.osd.language („ro_RO", „en_EN", „pt_PT") -> codul din HdsLang („ro", „en", „pt")"""
	try:
		return _hdsLang().cod_limba(valoare)
	except Exception:
		try:
			s = str(valoare).strip().lower().replace("-", "_").split("_")[0]
			return s or LIMBA_IMPLICITA
		except Exception:
			return LIMBA_IMPLICITA


def limba():
	"""codul limbii meniului; „ro" cand setarile nu sunt incarcate (pe PC, in probe)"""
	try:
		valoare = sys.modules["Components.config"].config.osd.language.value
	except Exception:
		return LIMBA_IMPLICITA
	if not valoare:
		return LIMBA_IMPLICITA
	return codLimba(valoare)


def separator(cod=None):
	"""separatorul zecimal al limbii („," sau „."), acelasi ca in bara de informatii"""
	try:
		cod = cod or limba()
		sep = _SEPARATOARE.get(cod)
		if sep is None:
			sep = _separatorDinTabel(cod)
			if len(_SEPARATOARE) < 64:
				_SEPARATOARE[cod] = sep
		return sep
	except Exception:
		return u","


def _separatorDinTabel(cod):
	"""ca HdsCommon.tr("_dec"): tabelul limbii, iar pentru o limba pe care tabelele nu o au, cel englezesc. Cand
	tabelele nu se pot incarca: punct in engleza, virgula in rest."""
	try:
		HdsLang = _hdsLang()
		if cod == "en" or cod not in HdsLang.LANGS:
			sep = HdsLang.EN.get("_dec")
		else:
			sep = HdsLang.incarca(cod).get("_dec")
		if sep and len(sep) <= 2:
			return _u(sep)
	except Exception:
		pass
	return u"." if cod == "en" else u","


# ---------------------------------------------------------------- tiparele

def _tradu(msgid):
	try:
		try:
			import builtins
		except ImportError:
			import __builtin__ as builtins  # noqa: F401 (Python 2)
		f = getattr(builtins, "_", None)
		if f is None:
			return msgid
		return _u(f(msgid))
	except Exception:
		return msgid


def _bun(tipar):
	return isinstance(tipar, _text) and tipar.count(u"%s") == 1 and tipar.count(u"%") == 1


def tipar(msgid, cod=None):
	"""tiparul tradus („%s°E", „%s° в. д."...), sau cel de rezerva al limbii"""
	t = _tradu(msgid)
	if t != _u(msgid) and _bun(t):
		return t
	try:
		cod = cod or limba()
	except Exception:
		cod = LIMBA_IMPLICITA
	return (ROMANA if cod == LIMBA_IMPLICITA else INTERNATIONAL).get(msgid, u"%s")


def _pune(tipar_, numar_):
	return tipar_.replace(u"%s", numar_, 1)


# ---------------------------------------------------------------- numerele

def numar(x, zecimale=1, cod=None):
	"""x cu `zecimale` zecimale si separatorul limbii („185,7"; in engleza „185.7"); semnul ramane, fara „-0,0";
	u"" daca x nu e un numar"""
	try:
		x = float(x)
		if x != x or x in (float("inf"), float("-inf")):
			return u""
		text = u"%.*f" % (max(0, int(zecimale)), x)
		if text.startswith(u"-") and float(text) == 0:
			text = text[1:]
		return text.replace(u".", separator(cod))
	except Exception:
		return u""


def _grade(x):
	try:
		x = float(x)
	except Exception:
		return None
	if x != x or x in (float("inf"), float("-inf")):
		return None
	return x


# ---------------------------------------------------------------- pozitia orbitala

def pozitie(grade, zecimale=1, cod=None):
	"""grade semnate (est +, vest -) -> „19,2°E" / „5,0°V" (in engleza „5.0°W", in germana „19,2°O"); directia dupa
	semnul valorii primite (0 si mai mult = est), ca pana acum; u"" daca nu e un numar"""
	g = _grade(grade)
	if g is None:
		return u""
	return _pune(tipar(TIPAR_EST if g >= 0 else TIPAR_VEST, cod), numar(abs(g), zecimale, cod))


def pozitieOrbitala(orbital, cod=None):
	"""pozitia bruta a nucleului (zecimi de grad, 0..3599, vestul ca 3600 - x): 192 -> „19,2°E", 3550 -> „5,0°V",
	1800 -> „180,0°E"; cu cifre intregi, fara rotunjiri. u"" daca nu e o pozitie: fiecare ecran isi pune semnul lui
	(„?" sau gol)."""
	try:
		if isinstance(orbital, bool):
			return u""
		p = int(orbital)
		if p != orbital and not isinstance(orbital, (_text, bytes)):
			return u""
	except Exception:
		return u""
	if p < 0 or p > 3600:
		return u""
	p %= 3600
	vest = p > 1800
	z = 3600 - p if vest else p
	text = u"%d%s%d" % (z // 10, separator(cod), z % 10)
	return _pune(tipar(TIPAR_VEST if vest else TIPAR_EST, cod), text)


# ---------------------------------------------------------------- numele satelitilor

# pozitia de la inceputul numelui din lista satelitilor: '19.2E Astra 1N/1P', '0.8W Thor 5/6/7', '177.0W C-band NSS 9'
_POZITIE_LA_INCEPUT = re.compile(u"^\\s*(\\d{1,3})(?:[.,](\\d))?\\s*" + GRAD + u"?\\s*([EeWw])(?:\\s*[-:]?\\s+|\\s*$)")
# o pozitie in alta parte a numelui ('Astra 19.2E', 'Astra 1N (19.2E)')
_POZITIE_IN_NUME = re.compile(u"(?:^|[\\s(])\\d{1,3}[.,]\\d\\s*" + GRAD + u"?\\s*[EeWw](?:$|[\\s)])")


def pozitieDinNume(nume):
	"""(pozitia bruta 0..3599 de la inceputul numelui, restul numelui): '19.2E Astra 1N/1P' -> (192, 'Astra 1N/1P'),
	'0.8W Thor 5/6/7' -> (3592, 'Thor 5/6/7'); (None, numele) cand numele nu incepe cu o pozitie."""
	try:
		text = _u(nume or u"").strip()
		m = _POZITIE_LA_INCEPUT.match(text)
		if m is None:
			return None, text
		zecimi = int(m.group(1)) * 10 + int(m.group(2) or 0)
		if zecimi > 1800:
			return None, text
		vest = m.group(3) in u"Ww"
		return ((3600 - zecimi) % 3600 if vest else zecimi), text[m.end():].strip()
	except Exception:
		return None, u""


def numeSatelit(orbital, nume, cod=None):
	"""Numele unui satelit pentru om, cu pozitia in fata, scrisa ca peste tot: '19.2E Astra 1N/1P' -> '19,2°E Astra
	1N/1P'. Pozitia e cea din nume, cand numele incepe cu ea: lista satelitilor muta unii sateliti C-band si Ka-band cu o
	zecime, ca sa nu aiba aceeasi pozitie cu cei obisnuiti ('177.0W C-band NSS 9' are position -1771), iar omul ii stie
	dupa nume. Un nume care are pozitia in alta parte ('Astra 19.2E') ramane cum e; un nume fara pozitie primeste
	pozitia `orbital` (bruta, 0..3599); fara nume, numai pozitia. u"" cand nu e nici nume, nici pozitie."""
	try:
		p, rest = pozitieDinNume(nume)
		if p is None and rest and _POZITIE_IN_NUME.search(rest):
			return rest
		text = pozitieOrbitala(orbital if p is None else p, cod)
		return (u"%s %s" % (text, rest)).strip()
	except Exception:
		try:
			return _u(nume or u"").strip()
		except Exception:
			return u""


# ---------------------------------------------------------------- coordonatele locului

def latitudine(grade, zecimale=2, cod=None):
	"""44.43 -> „44,43 N"; -33.925 -> „33,925 S" (cu 3 zecimale); u"" daca nu e un numar"""
	g = _grade(grade)
	if g is None:
		return u""
	return _pune(tipar(TIPAR_NORD if g >= 0 else TIPAR_SUD, cod), numar(abs(g), zecimale, cod))


def longitudine(grade, zecimale=2, cod=None):
	"""26.11 -> „26,11 E"; -18.424 -> „18,42 V" (in engleza „18.42 W", in germana „26,11 O")"""
	g = _grade(grade)
	if g is None:
		return u""
	return _pune(tipar(TIPAR_LON_EST if g >= 0 else TIPAR_LON_VEST, cod), numar(abs(g), zecimale, cod))


def coordonate(lat, lon, zecimale=2, cod=None):
	"""„44,43 N, 26,11 E" (in engleza „44.43 N, 26.11 E"); u"" daca una lipseste"""
	a, b = latitudine(lat, zecimale, cod), longitudine(lon, zecimale, cod)
	if not a or not b:
		return u""
	return u"%s, %s" % (a, b)


# ---------------------------------------------------------------- literele (listele de alegere si ce scrie omul)

def _curata(text):
	try:
		text = _u(text)
	except Exception:
		return u""
	for semn in (u"%s", GRAD, u" ", u" ", u" ", u" ", u".", u"\t"):
		text = text.replace(semn, u"")
	return text.upper()


def litera(msgid, cod=None):
	"""litera (sau prescurtarea) din tipar: „%s°E" -> „E", „%s° в. д." -> „в. д.", fara grad si fara spatiile de margine"""
	t = tipar(msgid, cod).replace(u"%s", u"", 1).replace(GRAD, u"")
	return t.strip(u"    ") or u"?"


def litereEstVest(cod=None):
	"""(litera estului, litera vestului) a limbii meniului, pentru listele E / V din pagini"""
	return litera(TIPAR_EST, cod), litera(TIPAR_VEST, cod)


def emisfera(text, cod=None):
	"""„E" sau „V" (codurile care se salveaza) din ce trimite omul sau pagina: E si V ca pana acum, W pentru vest si
	literele limbii meniului (O = est in germana si olandeza, O = vest in franceza, spaniola, italiana si
	portugheza, Ny = vest in maghiara...). E si V isi pastreaza sensul vechi: o litera a limbii egala cu ele, dar cu
	alt sens (V = est in ceha), nu schimba nimic. None daca nu se intelege."""
	s = _curata(text)
	if not s:
		return None
	if s == u"E":
		return "E"
	if s in (u"V", u"W"):
		return "V"
	est, vest = litereEstVest(cod)
	if s == _curata(est):
		return "E"
	if s == _curata(vest):
		return "V"
	return None

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTemaExterna.py: ce ii trebuie unei teme scrise de altii, numai cat e aleasa una. Tema ramane a omului; daca nu merge,
# omul afla de ce pe ecran si revine singur tema HD Satelit, fara bucle de repornire. Modulul se incarca numai la alegerea
# unei teme externe sau cu una aleasa: cu tema HD Satelit (Clasic, Pro) nu se incarca deloc. Nu importa nimic din enigma2 la
# incarcare (probele de pe PC).
#
# INCLUDERILE (puneIncluderile): <include filename="..." conditional="..."/> de la radacina se inlocuieste, pe locul lui, cu
# copiii radacinii fisierului inclus. Fisierul se cauta langa cel care il include, apoi langa tema, apoi in dosarul temelor.
# O conditie falsa lasa includerea deoparte; un fisier lipsa, stricat sau inclus in cerc e o tema stricata (EroareTema).
# Primul ecran cu un nume castiga (ca in tot restul incarcarii).
#
# POZITIILE (rezolvaRelative): position="fill", "e-10", "c-624", "50%", "20*f" si orice expresie cu + - * / si paranteze,
# fata de parinte (televizorul pentru un <screen>, ecranul pentru elementele lui). Se socoteste pe arborele expresiei, fara
# eval; o forma necunoscuta ramane cum e si merge mai departe ca pana acum (un rand in jurnal).
#
# FONTURILE (fontBun, fontRezerva): un fisier care nu e font opreste enigma2 din cod nativ, deci se verifica antetul si tabela
# inainte de addFont. Un font lipsa sau stricat ia locul numelui lui cu un font al imaginii cu acelasi rol.
#
# VERIFICAREA (verifica): inainte de activare, fara sa ruleze nimic din tema: tot XML-ul, includerile, rezolutia, fonturile,
# componentele cerute. Ce nu tine de ecranele esentiale nu opreste tema, ci se spune.
#
# JURNALUL ACTIVARII (ACTIVARE): supravietuieste repornirii receptorului. Se scrie inainte de alegere si la fiecare pornire
# cu tema in proba; fara el scris, tema nu se activeaza. Peste MAX_INCERCARI porniri fara sfarsitul probei, tema se retrage.
#
# CADERILE ECRANELOR (stivaDinTema): trei erori de ecran in 30 de secunde retrag tema numai daca macar una trece prin fisierele
# temei (dosarul ei sau fisierele pachetului opkg care a pus-o: convertoare, randatoare, pluginul ei). Un plugin care cade singur
# (constructorul lui, oricare ar fi tema) reporneste interfata ca pana acum, dar tema omului ramane (Obsidian-FHD retrasa de
# OAWeatherOverview, 12.11.2026).
#
# NUMELE CERUTE (ImportComponente, puneNumeLipsa): convertoarele si randatoarele din HdsConvertoareStraine si HdsRandatoareStraine se vad la
# import cu numele din XML numai cand nu exista fisierul (un pachet de tema care il aduce ramane al lui si se instaleaza fara conflict).
#
# PANOURILE CU ASEZARE (panouFaraNume): <panel position=... size=...> fara nume e un cadru: copiii se muta fata de el; "left", "right", "top",
# "bottom", "fill" si marimile cu "*" impart locul ramas.
#
# RAPORTUL (trimiteRaport): pe canalul rapoartelor pluginurilor (Components/HdsPluginExtern.py), cu fisierele temei, numai pe
# fir. Fraza despre echipa se spune numai dupa raspunsul serverului.

import copy
import hashlib
import json
import os
import posixpath
import re
import time
import xml.etree.ElementTree as ET

ACTIVARE = "/etc/enigma2/hds-tema-activare.json"
MAX_INCERCARI = 3
MAX_ADANCIME = 8
# bara, lista canalelor, meniul, setarile, ferestrele: fara ele tema nu se poate folosi
ESENTIALE = ("InfoBar", "SecondInfoBar", "ChannelSelection", "Menu", "Setup", "MessageBox", "ChoiceBox", "EPGSelection",
	"EventView", "Volume", "VirtualKeyBoard")
DOSAR_FONTURI = "/usr/share/fonts"
DOSAR_PYTHON = "/usr/lib/enigma2/python"
FONTURI_REZERVA = ("HdsRegular.ttf", "HdsBold.ttf", "HdsCond.ttf")
# rezerva unui ecran: cate componente lipsa fata de elementele cu sursa inseamna ca ecranul temei nu se poate folosi
FRACTIE_LIPSA = 2
MAX_ANUNTATE = 40


# ce dau modulele noastre, cu numele din XML
CONVERTOARE_NOASTRE = frozenset(("ClientsStreaming", "CpuUsage", "CryptoInfo", "EventInfo", "ExtendedServiceInfo", "HddState", "LayoutInfo", "MovieReference",
	"PliExtraInfo", "RotorPosition", "ServiceName2", "ServiceOrbitalPosition", "StreamInfo", "TransponderInfo", "VAudioInfo", "VNetSpeedInfo", "VServiceInfo",
	"SCServicePosition", "AnalogClock", "ConfigEntryTestVisible", "ConverterRotator", "TextCase", "ReceiverInfo", "YWeather"))
# RunningText nu e aici: imaginea il are ca fisier (Components/Renderer/RunningText.py), cu optiunile lui
RANDATOARE_NOASTRE = frozenset(("ChannelNumber", "CiModuleControl", "NextEpgInfo", "NextEvents", "PiconBg", "Rectangle", "RegularLabel",
	"VRunningText", "VVolumeText", "VideoSize", "VolumeText", "Cover", "AudioIcon", "SingleEpgList", "AnalogClockLCD", "RatingIconLabel", "Bhclock"))
MODULE_NOASTRE = {"Converter": ("HdsConvertoareStraine", CONVERTOARE_NOASTRE), "Renderer": ("HdsRandatoareStraine", RANDATOARE_NOASTRE)}
# importuri scrise pentru Python 2 in fisierele aduse de teme ("from Poll import Poll")
IMPORTURI_VECHI = {"Poll": "Components.Converter.Poll", "Converter": "Components.Converter.Converter", "Renderer": "Components.Renderer.Renderer"}


def N_(text):
	return text


class EroareTema(Exception):
	"""O tema care nu se poate folosi; motiv = cuvantul din HdsSkinuri (TEXT_MOTIV)."""

	def __init__(self, motiv, detaliu=""):
		Exception.__init__(self, "%s: %s" % (motiv, detaliu))
		self.motiv = motiv
		self.detaliu = detaliu


MOTIV_XML = "xml"
MOTIV_INCLUDE = "include"
MOTIV_REZOLUTIE = "rezolutie"
MOTIV_SCRIERE = "scriere"
MOTIV_CADERE = "cadere"
MOTIV_ECRANE = "ecrane"
MOTIV_NU_E_SKIN = "nu_e_skin"


def _jurnal(text):
	print("[HdsTemaExterna] %s" % text)


def _t(text, traducere=None):
	if traducere is not None:
		try:
			return traducere(text)
		except Exception:
			return text
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


# ------------------------------------------------------------------ includerile

def _valoareConditie(nod, cutie):
	import ast
	if isinstance(nod, ast.Expression):
		return _valoareConditie(nod.body, cutie)
	if isinstance(nod, ast.BoolOp):
		valori = [_valoareConditie(v, cutie) for v in nod.values]
		return all(valori) if isinstance(nod.op, ast.And) else any(valori)
	if isinstance(nod, ast.UnaryOp) and isinstance(nod.op, ast.Not):
		return not _valoareConditie(nod.operand, cutie)
	if isinstance(nod, ast.Compare) and len(nod.ops) == 1:
		a, b = _valoareConditie(nod.left, cutie), _valoareConditie(nod.comparators[0], cutie)
		op = nod.ops[0]
		if isinstance(op, ast.Eq):
			return a == b
		if isinstance(op, ast.NotEq):
			return a != b
		if isinstance(op, (ast.In, ast.NotIn)) and isinstance(b, (tuple, list, str)):
			return (a in b) if isinstance(op, ast.In) else (a not in b)
		raise ValueError("comparatie nepermisa")
	if isinstance(nod, ast.Constant) and isinstance(nod.value, (str, int, float, bool, type(None))):
		return nod.value
	if isinstance(nod, (ast.Tuple, ast.List)):
		return tuple(_valoareConditie(e, cutie) for e in nod.elts)
	if isinstance(nod, ast.Call) and isinstance(nod.func, ast.Attribute) and isinstance(nod.func.value, ast.Name) \
			and (nod.func.value.id, nod.func.attr) in (("BoxInfo", "getItem"), ("SystemInfo", "get"), ("BoxInfo", "get")) \
			and not nod.keywords and 1 <= len(nod.args) <= 2:
		return cutie.getItem(*[_valoareConditie(x, cutie) for x in nod.args])
	# str(...), (...).startswith("7."): numai atat din apeluri; altceva nu se ruleaza
	if isinstance(nod, ast.Call) and isinstance(nod.func, ast.Name) and nod.func.id == "str" and len(nod.args) == 1 and not nod.keywords:
		return str(_valoareConditie(nod.args[0], cutie))
	if isinstance(nod, ast.Call) and isinstance(nod.func, ast.Attribute) and nod.func.attr in ("startswith", "endswith", "lower", "upper") and not nod.keywords:
		v = _valoareConditie(nod.func.value, cutie)
		if isinstance(v, str):
			return getattr(v, nod.func.attr)(*[_valoareConditie(x, cutie) for x in nod.args])
	raise ValueError("expresie nepermisa")


def conditieIncludere(expresie, cutie=None):
	"""True daca includerea se ia (expresia peste BoxInfo/SystemInfo e adevarata); False pentru o expresie falsa sau pe care
	nu o stim: fisierele facute anume pentru alte imagini raman deoparte."""
	try:
		import ast
		if cutie is None:
			from Components.SystemInfo import BoxInfo as cutie
		return bool(_valoareConditie(ast.parse(expresie.strip(), mode="eval"), cutie))
	except Exception as e:
		_jurnal("conditional=%r nu se evalueaza, includerea ramane deoparte (%s)" % (expresie, e))
		return False


def verificaRezolutia(radacina):
	"""EroareTema cand tema cere o rezolutie care nu se poate pune (zero sau negativa): ar opri afisarea."""
	for c in radacina.findall("output"):
		if str(c.attrib.get("id") or "0") != "0":
			continue
		for r in c.findall("resolution"):
			try:
				bun = int(r.attrib.get("xres") or 720) > 0 and int(r.attrib.get("yres") or 576) > 0
			except ValueError:
				bun = False
			if not bun:
				raise EroareTema(MOTIV_REZOLUTIE, "%s x %s" % (r.attrib.get("xres"), r.attrib.get("yres")))


def caleInclus(fisier, dosare, dosar_teme=None):
	"""Calea fisierului inclus sau None. `dosare`: langa cel care il include, apoi langa tema; apoi dosarul temelor."""
	if fisier.startswith("/"):
		return fisier if os.path.isfile(fisier) else None
	for d in list(dosare) + ([dosar_teme] if dosar_teme else []):
		if d:
			cale = os.path.join(d, fisier)
			if os.path.isfile(cale):
				return cale
	return None


def puneIncluderile(radacina, dosar_tema, fisier_tema, dosar_teme=None, cutie=None, _lant=None, _vazute=None, _dosar=None):
	"""Inlocuieste <include> cu copiii fisierelor incluse (si ale includerilor lor). EroareTema la un fisier lipsa, stricat,
	inclus in cerc sau prea adanc."""
	lant = _lant if _lant is not None else (os.path.realpath(fisier_tema),)
	vazute = _vazute if _vazute is not None else set(lant)
	for el in list(radacina.findall("include")):
		poz = list(radacina).index(el)
		radacina.remove(el)
		fisier = (el.get("filename") or "").strip()
		conditie = el.get("conditional")
		if not fisier or (conditie and not conditieIncludere(conditie, cutie)):
			continue
		cale = caleInclus(fisier, [_dosar, dosar_tema], dosar_teme)
		if cale is None:
			raise EroareTema(MOTIV_INCLUDE, fisier)
		real = os.path.realpath(cale)
		if real in lant:
			raise EroareTema(MOTIV_INCLUDE, "%s (se include pe sine)" % fisier)
		if real in vazute:
			continue
		if len(lant) > MAX_ADANCIME:
			raise EroareTema(MOTIV_INCLUDE, "%s (prea adanc)" % fisier)
		try:
			inclus = ET.parse(cale).getroot()
		except Exception as e:
			raise EroareTema(MOTIV_INCLUDE, "%s: %s" % (fisier, str(e)[:160]))
		vazute.add(real)
		if inclus.find("include") is not None:
			puneIncluderile(inclus, dosar_tema, fisier_tema, dosar_teme, cutie, lant + (real,), vazute, os.path.dirname(cale))
		for i, copil in enumerate(list(inclus)):
			radacina.insert(poz + i, copil)


# ------------------------------------------------------------------ pozitiile

_FACTOR = [None]


def factorSkin():
	"""Scara ecranului fata de 720 de randuri (1 la 720p, 1.5 la 1080p), f din temele scrise cu ea."""
	if _FACTOR[0] is None:
		try:
			from enigma import getDesktop
			inaltime = getDesktop(0).size().height()
			_FACTOR[0] = inaltime / 720.0 if inaltime > 0 else 1.0
		except Exception:
			return 1.0
	return _FACTOR[0]


def _socoteste(nod):
	import ast
	if isinstance(nod, ast.Expression):
		return _socoteste(nod.body)
	if isinstance(nod, ast.Constant) and type(nod.value) in (int, float):
		return nod.value
	if isinstance(nod, ast.UnaryOp) and isinstance(nod.op, (ast.USub, ast.UAdd)):
		v = _socoteste(nod.operand)
		return -v if isinstance(nod.op, ast.USub) else v
	if isinstance(nod, ast.BinOp):
		a, b = _socoteste(nod.left), _socoteste(nod.right)
		if isinstance(nod.op, ast.Add):
			return a + b
		if isinstance(nod.op, ast.Sub):
			return a - b
		if isinstance(nod.op, ast.Mult):
			return a * b
		if isinstance(nod.op, ast.Div):
			return a / b
		if isinstance(nod.op, ast.FloorDiv):
			return a // b
	raise ValueError("expresie nepermisa")


def calculeaza(text):
	"""O expresie numai cu numere, + - * / si paranteze -> numarul ei (intreg, trunchiat), sau None."""
	if not text or any(c not in "0123456789.+-*/() " for c in text) or "**" in text or len(text) > 80:
		return None
	import ast
	try:
		return int(_socoteste(ast.parse(text, mode="eval")))
	except (SyntaxError, ValueError, ArithmeticError, RecursionError):
		return None


def _cuvant(text, litera):
	"""True cand `litera` e in text ca nume de sine statator (nu in alt cuvant)."""
	i = text.find(litera)
	while i != -1:
		inainte = text[i - 1] if i else " "
		dupa = text[i + 1] if i + 1 < len(text) else " "
		if not (inainte.isalnum() or inainte == "_") and not (dupa.isalnum() or dupa == "_"):
			return True
		i = text.find(litera, i + 1)
	return False


def _inlocuieste(text, litera, valoare):
	rez = []
	i = 0
	while i < len(text):
		c = text[i]
		if c == litera and not (i and (text[i - 1].isalnum() or text[i - 1] == "_")) and \
				not (i + 1 < len(text) and (text[i + 1].isalnum() or text[i + 1] == "_")):
			rez.append(valoare)
		else:
			rez.append(c)
		i += 1
	return "".join(rez)


def _componentaRelativa(s):
	s = s.strip()
	if not s or s == "center":
		return False
	return s.endswith("%") or _cuvant(s, "e") or _cuvant(s, "c") or _areFactor(s)


def _areFactor(s):
	return _cuvant(s, "f") and any(o in s for o in "*/")


def coordonata(s, parinte, pozitiva=True):
	"""O componenta ("c-624", "e-10", "50%", "20*f", "e-130*f") -> numarul ei, ca text; altceva ramane cum e."""
	t = s.strip()
	if not _componentaRelativa(t):
		return s
	t = _inlocuieste(t, "e", "(%d)" % parinte)
	t = _inlocuieste(t, "c", "(%r)" % (parinte / 2.0))
	t = t.replace("%", "*%r" % (parinte / 100.0))
	t = _inlocuieste(t, "f", "(%r)" % float(factorSkin()))
	v = calculeaza(t)
	if v is None:
		return s
	return str(max(v, 0) if pozitiva else v)


def valoareCuFactor(v):
	"""Un atribut oarecare cu f ("45*f", "Regular;20*f", "30*f,20*f", "poza.png:3*f,0") -> cu numere."""
	if ";" in v:
		nume, sep, rest = v.partition(";")
		return nume + sep + valoareCuFactor(rest)
	if ":" in v:
		inainte, sep, rest = v.rpartition(":")
		return inainte + sep + valoareCuFactor(rest)
	return ",".join(coordonata(p, 0, False) if _areFactor(p) else p for p in v.split(","))


_CUVINTE_POZITIE = ("left", "right", "top", "bottom")


def _pozitieCuCuvinte(v, latime, inaltime, marime):
	"""position="right,9", "left,1", "10,bottom": lipit de marginea parintelui, cu marimea elementului. Altfel valoarea asa cum e."""
	parti = [p.strip() for p in v.split(",")]
	if len(parti) != 2 or not any(p in _CUVINTE_POZITIE for p in parti):
		return v
	w, h = marime
	x = {"left": "0", "right": str(max(0, latime - w))}.get(parti[0], parti[0])
	y = {"top": "0", "bottom": str(max(0, inaltime - h))}.get(parti[1], parti[1])
	return "%s,%s" % (x, y)


def _lipitDeMargine(atribute, latime, inaltime):
	"""position="bottom" size="*,246": lipit de o margine a parintelui, "*" = toata latura. Altfel lista primita."""
	p = next((v.strip() for a, v in atribute if a == "position" and isinstance(v, str)), "")
	if p not in _CUVINTE_POZITIE:
		return atribute
	marime = next((v for a, v in atribute if a == "size" and isinstance(v, str)), "")
	cadru = (0, 0, latime, inaltime)
	(x, y, w, h), _ramas = _pozitieCopil(ET.Element("widget", {"position": p, "size": marime}), cadru, cadru)
	rez = [(a, "%d,%d" % (x, y) if a == "position" else "%d,%d" % (w, h) if a == "size" else v) for a, v in atribute]
	if not marime:
		rez.append(("size", "%d,%d" % (w, h)))
	return rez


def rezolvaRelative(atribute, latime, inaltime):
	"""Lista (atribut, valoare) cu expresii -> aceeasi lista cu numere (pozitiile si marimile fata de un parinte latime x
	inaltime); fara nimic de calculat, chiar lista primita."""
	atribute = _lipitDeMargine(atribute, latime, inaltime)
	if any(a == "position" and isinstance(v, str) and any(c in v for c in _CUVINTE_POZITIE) for a, v in atribute):
		marime = marimeDinAtribute(rezolvaRelative([x for x in atribute if x[0] == "size"], latime, inaltime), (0, 0))
		atribute = [(a, _pozitieCuCuvinte(v, latime, inaltime, marime) if a == "position" and isinstance(v, str) else v) for a, v in atribute]

	def relativ(a, v):
		return a in ("position", "size") and isinstance(v, str) and (v.strip() == "fill" or
			any(_componentaRelativa(p) for p in v.split(",")))

	def cuFactor(a, v):
		return a not in ("text", "title") and isinstance(v, str) and "f" in v and _areFactor(v)
	if not any(relativ(a, v) or cuFactor(a, v) for a, v in atribute):
		return atribute
	umple = any(a == "position" and isinstance(v, str) and v.strip() == "fill" for a, v in atribute)
	rez = []
	for a, v in atribute:
		if umple and a == "size":
			continue
		if a == "position" and umple:
			rez.append(("position", "0,0"))
			rez.append(("size", "%d,%d" % (latime, inaltime)))
			continue
		if relativ(a, v):
			parti = v.split(",")
			if len(parti) == 2:
				v = ",".join(coordonata(p, m) for p, m in zip(parti, (latime, inaltime)))
		elif cuFactor(a, v):
			v = valoareCuFactor(v)
		rez.append((a, v))
	return rez


def marimeDinAtribute(atribute, implicit):
	"""Marimea (latime, inaltime) din atributul size, daca e numerica; altfel `implicit`."""
	for a, v in atribute:
		if a == "size" and isinstance(v, str):
			try:
				x, y = v.split(",")
				return int(x), int(y)
			except ValueError:
				pass
	return implicit


def primaCuloare(s):
	"""Un gradient ("#00718096,#00ffffff,horizontal", numele culorilor la fel) -> prima culoare; fara virgula, None."""
	if s and "," in s:
		return s.split(",")[0].strip()
	return None


# ------------------------------------------------------------------ panourile cu asezare

CUVINTE_ASEZARE = ("left", "right", "top", "bottom", "fill")


def _masura(s, parinte):
	"""O componenta de marime: "*" sau lipsa = None (tot ce a ramas), altfel numarul ei."""
	s = (s or "").strip()
	if not s or s == "*":
		return None
	v = coordonata(s, parinte, False)
	try:
		return int(v)
	except ValueError:
		return None


def cadruEcran(element, latime, inaltime):
	"""Locul in care se aseaza copiii unui ecran: (0, 0, latimea, inaltimea) ferestrei."""
	marime = (element.attrib.get("size") or "").split(",")
	if len(marime) == 2:
		w = _masura(marime[0], latime)
		h = _masura(marime[1], inaltime)
		return 0, 0, latime if w is None else w, inaltime if h is None else h
	return 0, 0, latime, inaltime


def panouFaraNume(panou, cale, cadru, cauta):
	"""Copiii unui panou fara nume, ca lista (element, cale), cu pozitiile si marimile in coordonatele ferestrei. Elementele sunt copii,
	originalele raman neatinse. `cauta(nume)`: (<screen>, cale) sau (None, None)."""
	loc = _pozitieCopil(panou, cadru, cadru)[0]
	return _aseaza(list(panou), cale, loc, cauta, panou.attrib.get("layout") == "stack", 0)


def _centru(s, parinte, marime):
	""""center", "center+20", "center-8" -> elementul centrat in parinte plus deplasarea, cel putin 0; None altfel"""
	if not s.startswith("center"):
		return None
	rest = s[6:].replace(" ", "")
	deplasare = calculeaza(rest) if rest else 0
	if deplasare is None or (rest and rest[0] not in "+-"):
		return None
	return max((parinte - marime) // 2 + deplasare, 0)


def _pozitieCopil(el, cadru, ramas):
	"""(x, y, latime, inaltime) ale copilului si locul ramas dupa el."""
	x0, y0, w0, h0 = cadru
	x, y, w, h = ramas
	p = (el.attrib.get("position") or ("fill" if el.tag == "panel" else "")).strip()
	marime = (el.attrib.get("size") or "").split(",")
	mw = _masura(marime[0], w) if len(marime) == 2 else None
	mh = _masura(marime[1], h) if len(marime) == 2 else None
	if p in CUVINTE_ASEZARE:
		if p == "left":
			mw = w if mw is None else mw
			return (x, y, mw, h), (x + mw, y, max(0, w - mw), h)
		if p == "right":
			mw = w if mw is None else mw
			return (x + w - mw, y, mw, h), (x, y, max(0, w - mw), h)
		if p == "top":
			mh = h if mh is None else mh
			return (x, y, w, mh), (x, y + mh, w, max(0, h - mh))
		if p == "bottom":
			mh = h if mh is None else mh
			return (x, y + h - mh, w, mh), (x, y, w, max(0, h - mh))
		return (x, y, w, h), ramas
	mw = w0 if mw is None else mw
	mh = h0 if mh is None else mh
	parti = [q.strip() for q in p.split(",")]
	if len(parti) == 2:
		px = _centru(parti[0], w0, mw)
		py = _centru(parti[1], h0, mh)
		if px is None:
			px = w0 - mw if parti[0] == "right" else _masura(parti[0], w0) or 0
		if py is None:
			py = h0 - mh if parti[1] == "bottom" else _masura(parti[1], h0) or 0
	else:
		px = py = 0
	return (x0 + px, y0 + py, mw, mh), ramas


def _aseaza(copii, cale, cadru, cauta, stiva, adancime):
	rez = []
	ramas = cadru
	if adancime > MAX_ADANCIME * 2:
		return rez
	for c in copii:
		if c.tag == "panel" and c.attrib.get("name"):
			p, pcale = cauta(c.attrib.get("name"))
			if p is not None:
				rez += _aseaza(list(p), pcale, ramas, cauta, False, adancime + 1)
			continue
		loc, dupa = _pozitieCopil(c, cadru, ramas)
		if c.tag == "panel":
			rez += _aseaza(list(c), cale, loc, cauta, c.attrib.get("layout") == "stack", adancime + 1)
		else:
			n = copy.copy(c)
			n.attrib = dict(c.attrib)
			n.attrib["position"] = "%d,%d" % (loc[0], loc[1])
			if c.attrib.get("size") or (c.attrib.get("position") or "").strip() in CUVINTE_ASEZARE:
				n.attrib["size"] = "%d,%d" % (loc[2], loc[3])
			rez.append((n, cale))
		if not stiva:
			ramas = dupa
	return rez


# ------------------------------------------------------------------ numele cerute

class ImportComponente(object):
	"""La sfarsitul lui sys.meta_path, cu o tema externa aleasa: ce nu se gaseste ca fisier si dau modulele noastre."""

	@classmethod
	def find_spec(cls, name, path=None, target=None):
		from importlib.machinery import ModuleSpec
		if name in IMPORTURI_VECHI:
			return ModuleSpec(name, cls)
		parti = name.split(".")
		if len(parti) == 3 and parti[0] == "Components" and parti[1] in MODULE_NOASTRE and parti[2] in MODULE_NOASTRE[parti[1]][1]:
			return ModuleSpec(name, cls)
		return None

	@classmethod
	def create_module(cls, spec):
		return None

	@classmethod
	def exec_module(cls, modul):
		import importlib
		import sys
		if modul.__name__ in IMPORTURI_VECHI:
			sys.modules[modul.__name__] = importlib.import_module(IMPORTURI_VECHI[modul.__name__])
			return
		_c, fel, nume = modul.__name__.split(".")
		sursa = importlib.import_module("Components.%s.%s" % (fel, MODULE_NOASTRE[fel][0]))
		setattr(modul, nume, getattr(sursa, nume))


def pornesteImportul():
	"""skin.py, cand tema externa s-a incarcat."""
	import sys
	if ImportComponente not in sys.meta_path:
		sys.meta_path.append(ImportComponente)


class _ControlImagine(object):
	"""Ce intreaba fisierele aduse de teme despre imaginea de acum, din /proc/stb/vmpeg (fara decodor, valorile date)."""
	_unic = None

	@classmethod
	def getInstance(cls):
		if cls._unic is None:
			cls._unic = cls()
		return cls._unic

	def _citeste(self, nume, baza, implicit):
		try:
			with open("/proc/stb/vmpeg/0/" + nume) as f:
				return int(f.read().strip(), baza)
		except (IOError, OSError, ValueError):
			return implicit

	def getResolutionX(self, implicit=0, *_a):
		return self._citeste("xres", 16, implicit)

	def getResolutionY(self, implicit=0, *_a):
		return self._citeste("yres", 16, implicit)

	def getFrameRate(self, implicit=0, *_a):
		return self._citeste("framerate", 10, implicit)

	def getProgressive(self, *_a):
		return self._citeste("progressive", 10, 0)

	def getAspect(self, implicit=0, *_a):
		return self._citeste("aspect", 16, implicit)


# ce cheama fisierele aduse de teme pe elementele imaginii si imaginea nu deseneaza inca (colturi, chenare, contur): primit, fara efect
_DECOR = {
	"eWidget": ("setCornerRadius", "setWidgetBorderColor", "setWidgetBorderWidth", "setPadding", "setBorderColor", "setBorderWidth"),
	"eLabel": ("setUnderline", "setTabWidth", "setAlphatest"),
	"ePixmap": ("setScale", "setScaleFlags"),
	"eListbox": ("setCornerRadius", "setItemCornerRadius", "setItemSpacing", "setMargin", "setScrollbarWidth", "setScrollbarRadius", "setScrollbarOffset",
		"setScrollbarBorderWidth", "setScrollbarForegroundColor", "setScrollbarBackgroundColor", "setScrollbarBorderColor", "setOrientation", "setItemWidth",
		"setTopIndex", "setPadding", "setSelectionZoom"),
}


# constantele pe care le folosesc sabloanele si fisierele aduse de teme; imaginea le primeste si nu le deseneaza (MultiContent)
_CONSTANTE = {"BT_ALPHATEST": 1, "BT_ALPHABLEND": 2, "BT_SCALE": 4, "BT_KEEP_ASPECT_RATIO": 8, "BT_FIXRATIO": 8, "BT_HALIGN_LEFT": 0, "BT_HALIGN_CENTER": 16,
	"BT_HALIGN_RIGHT": 32, "BT_VALIGN_TOP": 0, "BT_VALIGN_CENTER": 64, "BT_VALIGN_BOTTOM": 128, "BT_ALIGN_CENTER": 80, "RT_ELLIPSIS": 0, "RT_BLEND": 0}


def _puneDecor(enigma):
	def nimic(self, *a, **k):
		return None
	for n, v in _CONSTANTE.items():
		if not hasattr(enigma, n):
			setattr(enigma, n, v)
	# un dreptunghi plin e o eticheta fara text
	if not hasattr(enigma, "eRectangle") and hasattr(enigma, "eLabel"):
		enigma.eRectangle = enigma.eLabel
	for clasa, nume in _DECOR.items():
		c = getattr(enigma, clasa, None)
		if c is None:
			continue
		for n in nume:
			if not hasattr(c, n):
				setattr(c, n, nimic)
	l = getattr(enigma, "eListbox", None)
	if l is not None and not hasattr(l, "orVertical"):
		l.orVertical = 0
	if l is not None and not hasattr(l, "orHorizontal"):
		l.orHorizontal = 1
	if l is not None and not hasattr(l, "getOrientation"):
		l.getOrientation = lambda self: 0
	if l is not None and not hasattr(l, "getItemHeight"):
		l.getItemHeight = lambda self: 0


def _lipseste(sectiune, nume):
	"""config.<sectiune> da KeyError la un nume necunoscut, deci hasattr nu ajunge."""
	try:
		getattr(sectiune, nume)
		return False
	except (KeyError, AttributeError):
		return True


def puneNumeLipsa(skin_globale=None):
	"""skin.loadSkinData, inainte sa se incarce extensiile: numele pe care le importa fisierele aduse de teme si de extensiile lor, numai daca
	imaginea nu le are. Numai cu tema externa aleasa; nu schimba nimic din ce exista."""
	import sys
	import types
	if skin_globale is not None:
		skin_globale.setdefault("getSkinFactor", factorSkin)
		skin_globale.setdefault("applySkinFactor", aplicaFactor)
	try:
		import enigma
		if not hasattr(enigma, "eAVControl"):
			enigma.eAVControl = _ControlImagine
		_puneDecor(enigma)
	except Exception as e:
		_jurnal("eAVControl: %r" % (e,))
	try:
		from Tools import Directories as D
		for nou, vechi in (("SCOPE_GUISKIN", "SCOPE_CURRENT_SKIN"), ("SCOPE_ACTIVE_SKIN", "SCOPE_CURRENT_SKIN"), ("SCOPE_SKINS", "SCOPE_SKIN")):
			if not hasattr(D, nou):
				setattr(D, nou, getattr(D, vechi))
	except Exception as e:
		_jurnal("Directories: %r" % (e,))
	try:
		import ServiceReference as R
		if not hasattr(R, "resolveAlternate"):
			R.resolveAlternate = resolveAlternate
	except Exception as e:
		_jurnal("ServiceReference: %r" % (e,))
	try:
		from Tools import Transponder as P
		if not hasattr(P, "getChannelNumber"):
			P.getChannelNumber = lambda frecventa, nim: "0"
	except Exception as e:
		_jurnal("Transponder: %r" % (e,))
	try:
		from Components.Renderer import Picon as S
		if not hasattr(S, "getPiconName"):
			S.getPiconName = S.cauta_sigla
		if not hasattr(S, "searchPaths"):
			S.searchPaths = [c % "picon" for c in S.CAI_SIGLE]
		if not hasattr(S, "lastPiconPath"):
			S.lastPiconPath = None
	except Exception as e:
		_jurnal("Picon: %r" % (e,))
	try:
		from Components.config import config, ConfigYesNo, ConfigSelection
		u = config.usage
		for n, f in (("swap_snr_on_osd", lambda: ConfigYesNo(default=False)), ("swap_time_display_on_osd", lambda: ConfigSelection(default="0", choices=[("0", "0")])),
				("swap_media_time_display_on_osd", lambda: ConfigSelection(default="0", choices=[("0", "0")])),
				("swap_time_remaining_on_osd", lambda: ConfigSelection(default="0", choices=[("0", "0")])),
				("swap_time_display_on_vfd", lambda: ConfigSelection(default="0", choices=[("0", "0")]))):
			if _lipseste(u, n):
				setattr(u, n, f())
	except Exception as e:
		_jurnal("config: %r" % (e,))
	for nume, continut in (("Tools.GetEcmInfo", {"GetEcmInfo": GetEcmInfo}), ("Tools.TextBoundary", {"getTextBoundarySize": getTextBoundarySize}),
			("Tools.Alternatives", {"GetWithAlternative": GetWithAlternative, "ResolveCiAlternative": lambda ref, *a, **k: ref, "CompareWithAlternatives": lambda x, y: x == y})):
		try:
			__import__(nume)
		except ImportError:
			m = types.ModuleType(nume)
			m.__dict__.update(continut)
			sys.modules[nume] = m
			import Tools
			setattr(Tools, nume.split(".")[1], m)


class GetEcmInfo(object):
	"""Ce cer fisierele aduse de teme despre decodare, din /tmp/ecm.info, cand exista; altfel gol."""
	CALE = "/tmp/ecm.info"

	def __init__(self):
		self.date = {}

	def pollEcmData(self):
		self.date = {}
		try:
			with open(self.CALE, encoding="utf-8", errors="replace") as f:
				for r in f:
					k, sep, v = r.partition(":")
					if sep:
						self.date[k.strip().lower()] = v.strip()
		except (IOError, OSError):
			pass
		return self.date

	def getEcmData(self):
		self.pollEcmData()
		return (self.date.get("from", ""), self.date.get("caid", "0"), self.date.get("provid", "0"), self.date.get("pid", "0"))

	def getInfo(self, membru, gol=""):
		return self.pollEcmData().get(str(membru).lower(), gol)

	def getText(self):
		self.pollEcmData()
		return " ".join("%s: %s" % (k, v) for k, v in sorted(self.date.items())[:4])


def getTextBoundarySize(instance, font, targetSize, text, nowrap=False):
	"""Marimea pe care o ia un text cu fontul dat, intr-o caseta de targetSize, masurata de eLabel."""
	from enigma import eLabel
	eticheta = eLabel(instance)
	eticheta.setFont(font)
	if nowrap:
		eticheta.setNoWrap(1)
	eticheta.resize(targetSize)
	eticheta.setText(text)
	return eticheta.calculateSize()


def aplicaFactor(*valori):
	"""Valorile inmultite cu factorSkin: una -> un numar intreg, mai multe -> un tuplu; ce nu e numar ramane."""
	f = factorSkin()
	if len(valori) == 1:
		return int(valori[0] * f + 0.5) if isinstance(valori[0], (int, float)) else valori[0]
	return tuple(int(v * f + 0.5) if isinstance(v, (int, float)) else v for v in valori)


def GetWithAlternative(service):
	"""Pentru un grup de alternative (referinta "1:134:...") primul serviciu din grup, altfel referinta asa cum e."""
	if service.startswith("1:134:"):
		from enigma import eServiceCenter, eServiceReference
		lista = eServiceCenter.getInstance().list(eServiceReference(service))
		if lista:
			continut = lista.getContent("S")
			if continut:
				return continut[0]
	return service


def resolveAlternate(ref):
	from enigma import eServiceReference
	return eServiceReference(GetWithAlternative(ref.toString()))


# ------------------------------------------------------------------ fonturile

def fontBun(cale):
	"""True cand fisierul are antetul si tabela unui font TrueType/OpenType care incap in el."""
	try:
		marime = os.path.getsize(cale)
		with open(cale, "rb") as f:
			cap = f.read(12)
			if len(cap) < 12:
				return False
			if cap[:4] == b"ttcf":
				return marime > 16
			if cap[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
				return False
			tabele = int.from_bytes(cap[4:6], "big")
			if tabele < 1 or tabele > 256 or marime < 12 + 16 * tabele:
				return False
			for _i in range(tabele):
				t = f.read(16)
				if len(t) < 16:
					return False
				if int.from_bytes(t[8:12], "big") + int.from_bytes(t[12:16], "big") > marime:
					return False
		return True
	except (IOError, OSError):
		return False


def fontRezerva(nume, dosar=None):
	"""Calea fontului imaginii cu acelasi rol pentru un font al temei care lipseste sau e stricat, sau None."""
	dosar = dosar or DOSAR_FONTURI
	n = (nume or "").lower()
	fel = FONTURI_REZERVA[0]
	if "bold" in n or "semi" in n or "medium" in n or "heavy" in n:
		fel = FONTURI_REZERVA[1]
	elif "cond" in n or "narrow" in n or "fixed" in n or "lcd" in n or "console" in n or "mono" in n:
		fel = FONTURI_REZERVA[2]
	cale = os.path.join(dosar, fel)
	return cale if os.path.isfile(cale) else None


def fontDinImagine(nume, skinuri):
	"""True cand un alt fisier (HDSatelit, skin_default) a dat deja fontul cu numele acesta: ramane acela."""
	for (_p, radacina) in skinuri:
		for c in radacina.findall("fonts"):
			for font in c.findall("font"):
				if font.attrib.get("name", "Regular") == nume:
					return True
	return False


# ------------------------------------------------------------------ rezerva unui ecran

def strangeCopii(element, cautaPanou, copii, _vazute=None):
	"""Elementele unui ecran, cu panourile puse la loc, in `copii`. Intoarce numele primului panou care lipseste, sau None."""
	vazute = _vazute or frozenset()
	for copil in element:
		if copil.tag != "panel":
			copii.append(copil)
			continue
		nume = copil.attrib.get("name")
		if not nume:
			# cadru: se uita la copiii lui
			lipsa = strangeCopii(copil, cautaPanou, copii, vazute)
			if lipsa is not None:
				return lipsa
			continue
		if nume in vazute:
			continue
		panou = cautaPanou(nume)
		if panou is None:
			return nume
		lipsa = strangeCopii(panou, cautaPanou, copii, vazute | {nume})
		if lipsa is not None:
			return lipsa
	return None


_moduleVazute = {}


def modulExista(fel, nume, dosar=None):
	"""True cand Components/<fel>/<nume>.py (sau .pyc) exista sau il dau modulele noastre; nu importa nimic."""
	if not nume or "/" in nume or "." in nume:
		return False
	if fel in MODULE_NOASTRE and nume in MODULE_NOASTRE[fel][1]:
		return True
	# ecranele se verifica la fiecare deschidere: fisierele se cauta o singura data
	cheie = (fel, nume, dosar)
	if cheie not in _moduleVazute:
		baza = os.path.join(dosar or DOSAR_PYTHON, "Components", fel, nume)
		_moduleVazute[cheie] = os.path.isfile(baza + ".py") or os.path.isfile(baza + ".pyc")
	return _moduleVazute[cheie]


def componenteLipsa(widget, dosar=None):
	"""Numele convertoarelor si al randatoarelor cerute de un element care nu sunt pe receptor."""
	lipsa = []
	r = widget.attrib.get("render")
	if r and not modulExista("Renderer", r, dosar):
		lipsa.append(r)
	for c in widget.findall("convert"):
		t = c.get("type")
		if t and not modulExista("Converter", t, dosar):
			lipsa.append(t)
	return lipsa


def esteLista(cheie, componenta):
	"""True pentru o lista a ecranului, fara de care ecranul nu se poate folosi; elementele noastre (hds...) nu cer temei
	nimic."""
	if cheie.lower().startswith("hds"):
		return False
	try:
		from enigma import eListbox
		if getattr(componenta, "GUI_WIDGET", None) is eListbox:
			return True
	except ImportError:
		pass
	return componenta.__class__.__name__ == "List" and hasattr(componenta, "list")


def motivEcran(ecran, element, cautaPanou, dosar=None):
	"""De ce ecranul temei nu se poate folosi: ("panou", nume), ("lista", cheie), ("componente", [nume]) sau None. Fara sa se
	construiasca nimic, deci fara nimic de desfacut."""
	copii = []
	panou = strangeCopii(element, cautaPanou, copii)
	if panou is not None:
		return "panou", panou
	nume, surse = set(), set()
	lipsa = []
	cuSursa = 0
	for w in copii:
		if w.tag != "widget":
			continue
		n, s = w.attrib.get("name"), w.attrib.get("source")
		if n:
			nume.add(n)
		elif s:
			cuSursa += 1
			surse.add(s)
			l = componenteLipsa(w, dosar)
			if l:
				lipsa += l
				if w.attrib.get("render") == "Listbox":
					return "componente", sorted(set(l))
	for cheie in ecran:
		if cheie not in nume and cheie not in surse and esteLista(cheie, ecran[cheie]):
			return "lista", cheie
	if lipsa and cuSursa and len(lipsa) * FRACTIE_LIPSA >= cuSursa:
		return "componente", sorted(set(lipsa))
	return None


def textMotivEcran(motiv, traducere=None):
	"""Motivul de mai sus, pentru om."""
	fel, ce = motiv
	if fel == "cadere":
		return _t("ecranul temei nu s-a putut construi", traducere)
	if fel == "panou":
		return _t("lipsește o parte a temei", traducere)
	if fel == "lista":
		return _t("lista ecranului lipsește din temă", traducere)
	return _t("lipsesc componentele %s", traducere) % ", ".join(ce[:4])


# ------------------------------------------------------------------ verificarea dinainte de activare

def _unFont(filename, dosar_tema, dosar_fonturi):
	for d in (dosar_tema, dosar_fonturi):
		cale = os.path.join(d, filename)
		if os.path.isfile(cale):
			return cale
	return None


def verifica(cale, root=None, dosar_fonturi=None, dosar_python=None, cutie=None):
	"""{"bun", "motiv", "detaliu", "latime", "inaltime", "fonturi": [lipsa sau stricate], "componente": [lipsa pe ecranele
	esentiale], "ecrane": n}. Nu ruleaza nimic din tema. Numai ce face tema de nefolosit o refuza."""
	rez = {"bun": False, "motiv": "", "detaliu": "", "latime": 0, "inaltime": 0, "fonturi": [], "componente": [], "ecrane": 0}
	dosar = os.path.dirname(cale)
	try:
		radacina = ET.parse(cale).getroot()
	except Exception as e:
		rez["motiv"], rez["detaliu"] = MOTIV_XML, str(e)[:200]
		return rez
	if radacina.tag != "skin":
		rez["motiv"] = MOTIV_NU_E_SKIN
		return rez
	try:
		puneIncluderile(radacina, dosar, cale, root, cutie)
	except EroareTema as e:
		rez["motiv"], rez["detaliu"] = e.motiv, e.detaliu
		return rez
	try:
		verificaRezolutia(radacina)
	except EroareTema as e:
		rez["motiv"], rez["detaliu"] = e.motiv, e.detaliu
		return rez
	for c in radacina.findall("output"):
		if str(c.attrib.get("id") or "0") == "0":
			for r in c.findall("resolution"):
				rez["latime"], rez["inaltime"] = int(r.attrib.get("xres") or 720), int(r.attrib.get("yres") or 576)
	fonturi = dosar_fonturi or DOSAR_FONTURI
	for c in radacina.findall("fonts"):
		for font in c.findall("font"):
			f = font.attrib.get("filename", "")
			gasit = _unFont(f, dosar, fonturi) if f else None
			if gasit is None or not fontBun(gasit):
				rez["fonturi"].append(f)
	ecrane = dict((s.attrib.get("name", ""), s) for s in reversed(radacina.findall("screen")))
	rez["ecrane"] = len(ecrane)
	lipsa = set()
	for n in ESENTIALE:
		s = ecrane.get(n)
		if s is None:
			continue
		copii = []
		strangeCopii(s, lambda p: ecrane.get(p), copii)
		for w in copii:
			if w.tag == "widget":
				lipsa.update(componenteLipsa(w, dosar_python))
	rez["componente"] = sorted(lipsa)
	rez["bun"] = True
	return rez


def textAvertisment(v, traducere=None):
	"""Ce nu opreste tema, dar omul trebuie sa stie, sau ""."""
	if v.get("componente"):
		return _t("Tema nu e completă: lipsesc componentele %s. Ecranele care au nevoie de ele vin de la HD Satelit.",
			traducere) % ", ".join(v["componente"][:6])
	return ""


# ------------------------------------------------------------------ jurnalul activarii

def citesteActivare(cale=None):
	try:
		with open(cale or ACTIVARE, encoding="utf-8") as f:
			d = json.load(f)
		return d if isinstance(d, dict) else None
	except (IOError, OSError, ValueError):
		return None


def scrieActivare(date, cale=None):
	"""Scriere atomica, cu datele ajunse pe disc inainte de inlocuire. False cand nu se poate."""
	cale = cale or ACTIVARE
	temp = cale + ".nou"
	try:
		with open(temp, "w", encoding="utf-8") as f:
			json.dump(date, f, ensure_ascii=False)
			f.flush()
			os.fsync(f.fileno())
		os.replace(temp, cale)
		return True
	except (IOError, OSError) as e:
		_jurnal("%s: %s" % (cale, e))
		try:
			os.unlink(temp)
		except OSError:
			pass
		return False


def amprentaFisier(cale):
	try:
		h = hashlib.sha256()
		with open(cale, "rb") as f:
			while True:
				b = f.read(65536)
				if not b:
					break
				h.update(b)
		return h.hexdigest()
	except (IOError, OSError):
		return ""


def _areUndeScrie(cale):
	"""Pe PC (probele) dosarul setarilor nu exista: fara jurnal, fara refuz."""
	return os.path.isdir(os.path.dirname(cale))


def pregatesteActivarea(valoare, cale_skin, cale=None):
	"""La alegere, inainte sa se schimbe setarea. False: nu se poate tine minte, deci tema nu se activeaza."""
	cale = cale or ACTIVARE
	if not _areUndeScrie(cale):
		return True
	return scrieActivare({"skin": valoare, "stare": "proba", "incercari": 0, "amprenta": amprentaFisier(cale_skin),
		"ora": int(time.time())}, cale)


def laPornire(valoare, cale_skin, cale=None):
	"""Inainte sa se incarce tema: None = se incarca; altfel (motiv, detaliu). Fiecare pornire in proba se tine minte, ca o
	tema care opreste receptorul sa nu fie incarcata la nesfarsit."""
	cale = cale or ACTIVARE
	if not _areUndeScrie(cale):
		return None
	a = citesteActivare(cale) or {}
	amprenta = amprentaFisier(cale_skin)
	acelasi = a.get("skin") == valoare and a.get("amprenta") == amprenta
	if acelasi and a.get("stare") == "bun":
		return None
	if acelasi and a.get("stare") == "refuzat":
		return a.get("motiv") or MOTIV_CADERE, a.get("detaliu") or ""
	incercari = 1
	if acelasi and a.get("stare") == "proba":
		incercari = int(a.get("incercari") or 0) + 1
		if incercari > MAX_INCERCARI:
			return MOTIV_CADERE, ""
	nou = {"skin": valoare, "stare": "proba", "incercari": incercari, "amprenta": amprenta, "ora": int(time.time()),
		"anuntate": a.get("anuntate", []) if acelasi else []}
	if not scrieActivare(nou, cale):
		return MOTIV_SCRIERE, ""
	return None


def probaReusita(cale=None):
	"""Interfata a mers tot timpul probei cu tema: nu se mai numara pornirile."""
	cale = cale or ACTIVARE
	a = citesteActivare(cale)
	if a and a.get("stare") == "proba":
		a["stare"] = "bun"
		a["incercari"] = 0
		scrieActivare(a, cale)


def iesireCeruta(cale=None):
	"""Interfata s-a oprit la cerere (repornirea interfetei, oprirea receptorului): pornirea asta nu se numara."""
	cale = cale or ACTIVARE
	a = citesteActivare(cale)
	if a and a.get("stare") == "proba" and int(a.get("incercari") or 0) > 0:
		a["incercari"] = int(a["incercari"]) - 1
		scrieActivare(a, cale)


def marcheazaRefuz(valoare, motiv, detaliu="", cale=None):
	"""Refuzul tinut minte si dupa repornirea receptorului (fisierul din RAM se pierde)."""
	cale = cale or ACTIVARE
	if not _areUndeScrie(cale):
		return
	a = citesteActivare(cale) or {}
	amprenta = a.get("amprenta", "") if a.get("skin") == valoare else ""
	scrieActivare({"skin": valoare, "stare": "refuzat", "motiv": motiv, "detaliu": detaliu, "amprenta": amprenta,
		"ora": int(time.time())}, cale)


def caderiRecente(acum, caderi, fereastra=600):
	"""Cate opriri neasteptate in ultimele `fereastra` secunde (acelasi fisier ca modul sigur, scris de enigma2.sh)."""
	n = 0
	try:
		with open(caderi, encoding="utf-8", errors="replace") as f:
			for rand in f:
				p = rand.split()
				if p and p[0].isdigit() and int(p[0]) + fereastra >= acum and p[2:3] != ["oprire"]:
					n += 1
	except (IOError, OSError):
		pass
	return n


# ------------------------------------------------------------------ raportul si mesajul

def numeRaport(nume):
	"""Numele temei cum il primeste serverul (litere, cifre, _ . + -)."""
	return "".join(c if c.isalnum() and c.isascii() or c in "_.+-" else "_" for c in nume)[:80] or "tema"


def textRaport(nume, motiv, ecrane, avertismente):
	"""Sectiunea de jurnal a raportului."""
	randuri = ["Tema: %s" % nume, "Motivul: %s" % motiv]
	for e in sorted(ecrane):
		randuri.append("Ecranul %s: %r" % (e, ecrane[e]))
	randuri += avertismente
	return "\n".join(randuri)


def trimiteRaport(nume, motiv, ecrane=None, avertismente=None, acum=None, mono=None):
	"""Raportul temei, pe fir. Lucrul lui HdsPluginExtern (.gata, .ok), sau None cand acelasi raport a plecat deja."""
	from Components import HdsPluginExtern as P
	acum = time.time() if acum is None else acum
	mono = time.monotonic() if mono is None else mono
	n = numeRaport(nume)
	sem = P.semnatura(n, EroareTema, "tema:" + motiv, motiv)
	eroare = EroareTema(motiv)
	raport = P.compuneRaport(P.FEL_TEME, n, "tema", sem, EroareTema, eroare, None, None,
		textRaport(nume, motiv, ecrane or {}, avertismente or []), 1, acum, mono)
	lucru = P.Lucru(raport)
	lucru.start()
	return lucru


def dejaAnuntat(semn, cale=None):
	"""True cand mesajul si raportul pentru `semn` au plecat la versiunea asta a temei; altfel il tine minte."""
	cale = cale or ACTIVARE
	a = citesteActivare(cale)
	if a is None:
		return False
	anuntate = a.get("anuntate") or []
	if semn in anuntate:
		return True
	a["anuntate"] = (anuntate + [semn])[-MAX_ANUNTATE:]
	scrieActivare(a, cale)
	return False


def textEchipa(primit, traducere=None):
	return _t("Echipa HD Satelit a primit datele erorii și va încerca să o rezolve.", traducere) if primit else \
		_t("Datele erorii ajung la echipa HD Satelit imediat ce receptorul are internet.", traducere)


def textStare(nume, ecrane, traducere=None):
	"""Pentru selector si pagina web: ce nu merge din tema de pe ecran, sau ""."""
	if not ecrane:
		return ""
	rezerve = [e for e in ecrane if ecrane[e].get("rezerva")]
	lipsa = set()
	for e in ecrane.values():
		lipsa.update(e.get("lipsa", []))
	lipsa = componenteDinRaport(lipsa)
	bucati = []
	if rezerve:
		bucati.append(_t("Un ecran folosește aspectul HD Satelit", traducere) if len(rezerve) == 1 else _t("%d ecrane folosesc aspectul HD Satelit", traducere) % len(rezerve))
	if lipsa:
		bucati.append(_t("lipsesc: %s", traducere) % ", ".join(sorted(lipsa)[:6]))
	if not bucati:
		return ""
	return _t("Tema %s: %s.", traducere) % (nume, "; ".join(bucati))


def mesajEcran(nume, ecran, motiv_text, traducere=None):
	"""Mesajul de pe televizor cand un ecran al temei a fost inlocuit."""
	return _t("Tema %s nu are tot ce îi trebuie pentru ecranul %s: %s. Ecranul folosește aspectul HD Satelit. Receptorul merge "
		"mai departe.", traducere) % (nume, ecran, motiv_text)


class _Anunt(object):
	ceas = None
	lista = []


def _sesiune():
	try:
		from Screens.InfoBar import InfoBar
		return InfoBar.instance.session if InfoBar.instance is not None else None
	except Exception:
		return None


def _ticAnunt():
	"""Mesajul se arata dupa ce vine raspunsul serverului (sau dupa cel mult cat asteapta si pluginurile)."""
	from Components import HdsPluginExtern as P
	acum = time.monotonic()
	for a in list(_Anunt.lista):
		lucru = a["lucru"]
		if lucru is None or lucru.gata or acum >= a["termen"]:
			_Anunt.lista.remove(a)
			primit = lucru is not None and lucru.gata and lucru.ok is True
			if a.get("fereastra"):
				try:
					_mesajRefuz(a["text"] + ("\n\n" + textEchipa(primit) if lucru is not None else ""))
				except Exception as e:
					_jurnal("mesajul temei retrase: %r" % (e,))
				continue
			sesiune = _sesiune()
			if sesiune is None:
				continue
			try:
				from Screens import HdsAnuntRetea
				text = a["text"] + ("\n" + textEchipa(primit) if lucru is not None else "")
				HdsAnuntRetea.arata(sesiune, text, "", P.DURATA_MESAJ_MS)
			except Exception as e:
				_jurnal("mesajul temei: %r" % (e,))
	if _Anunt.lista and _Anunt.ceas is not None:
		_Anunt.ceas.start(250, True)


def anunta(text, lucru, fereastra=False):
	"""Mesajul pe televizor (firul enigma2): dupa raspunsul serverului la raportul `lucru`. `fereastra`: o fereastra cu OK, nu mesajul mic."""
	from enigma import eTimer
	from Components import HdsPluginExtern as P
	_Anunt.lista.append({"text": text, "lucru": lucru, "termen": time.monotonic() + P.ASTEPTARE_RASPUNS_S, "fereastra": fereastra})
	if _Anunt.ceas is None:
		_Anunt.ceas = eTimer()
		_Anunt.ceas.callback.append(_ticAnunt)
	_Anunt.ceas.start(250, True)


def rezervaFolosita(nume, ecran, motiv):
	"""skin.readSkin, pe firul enigma2: un ecran al temei a fost inlocuit. O singura data pe versiune de tema pentru fiecare
	ecran: mesajul pe televizor si raportul, dupa ce s-a terminat lucrul ecranului."""
	try:
		from enigma import eTimer
		_Ceasuri.lista.append((nume, ecran, motiv))
		if _Ceasuri.ceas is None:
			_Ceasuri.ceas = eTimer()
			_Ceasuri.ceas.callback.append(_dupaRezerva)
		_Ceasuri.ceas.start(1500, True)
	except Exception as e:
		_jurnal("rezerva ecranului %s: %r" % (ecran, e))


class _Ceasuri(object):
	ceas = None
	lista = []


def _dupaRezerva():
	lista, _Ceasuri.lista = _Ceasuri.lista, []
	for nume, ecran, motiv in lista:
		try:
			if dejaAnuntat("ecran:%s:%s" % (ecran, motiv[0])):
				continue
			text = textMotivEcran(motiv)
			lucru = trimiteRaport(nume, "ecranul %s: %s %r" % (ecran, motiv[0], motiv[1]))
			anunta(mesajEcran(nume, ecran, text), lucru)
		except Exception as e:
			_jurnal("rezerva ecranului %s: %r" % (ecran, e))


def dupaRefuz(refuz, text):
	"""La pornirea sesiunii, dupa ce o tema a fost retrasa: raportul, apoi un singur mesaj cu motivul si fraza despre echipa, dupa raspunsul
	serverului. Mesajul ajunge la om si fara raport. Nu arunca."""
	lucru = None
	try:
		nume = (refuz.get("skin") or "").split("/")[0] or "tema"
		lucru = trimiteRaport(nume, "refuzata: %s %s" % (refuz.get("motiv", ""), refuz.get("detaliu", "")))
	except Exception as e:
		_jurnal("raportul temei retrase: %r" % (e,))
	try:
		anunta(text, lucru, True)
	except Exception as e:
		_jurnal("mesajul temei retrase: %r" % (e,))
		_mesajRefuz(text)


def _mesajRefuz(text):
	from Screens.MessageBox import MessageBox
	from Tools import Notifications
	Notifications.AddPopup(text, MessageBox.TYPE_WARNING, 0, "hds_skin_refuz")


def dupaProba(nume, ecrane, avertismente):
	"""Dupa timpul probei, cu tema pe ecran: ce elemente nu s-au putut, o singura data pe versiune de tema. Ecranele inlocuite
	au mesajul lor (rezervaFolosita)."""
	lipsa = set()
	for e in ecrane.values():
		lipsa.update(e.get("lipsa", []))
	if not lipsa or dejaAnuntat("elemente:%d" % len(lipsa)):
		return
	lucru = trimiteRaport(nume, "elemente care nu se pot afisa", ecrane, avertismente)
	# un element pe care ecranul nostru nu il are nu se vede lipsind; omul afla numai cand lipseste o componenta a temei
	if componenteDinRaport(lipsa):
		anunta(_t("Tema %s are elemente pe care receptorul nu le poate afișa încă. Receptorul merge mai departe.") % nume, lucru)


def componenteDinRaport(lipsa):
	"""Numele componentelor care nu sunt pe receptor, din randurile raportului."""
	rez = set()
	for r in lipsa:
		if "No module named" in r:
			rez.add(r.split("No module named")[1].strip(" '\"").split(".")[-1])
	return rez


# ------------------------------------------------------------------ caderile ecranelor: din tema sau din altceva

DOSAR_OPKG_INFO = "/var/lib/opkg/info"
_FISIER_IN_STIVA = re.compile(r'File "([^"]+)"')


def _faraPyc(cale):
	"""Calea sursei pentru un .pyc (asa apare in stiva): /x/__pycache__/m.cpython-314.pyc si /x/m.pyc devin /x/m.py."""
	if not cale.endswith(".pyc"):
		return cale
	dosar, nume = posixpath.split(cale)
	if posixpath.basename(dosar) == "__pycache__":
		dosar = posixpath.dirname(dosar)
		nume = nume.split(".")[0] + ".pyc"
	return posixpath.join(dosar, nume[:-1])


def fisierePachetTema(dosar_tema, info=None):
	"""Fisierele pachetului opkg care a pus tema (cel care are <dosar_tema>/skin.xml), cu .pyc scris ca .py. Multime goala pentru
	o tema pusa de mana."""
	info = info or DOSAR_OPKG_INFO
	skin_xml = dosar_tema.rstrip("/") + "/skin.xml"
	try:
		liste = sorted(n for n in os.listdir(info) if n.endswith(".list"))
	except OSError:
		return frozenset()
	for n in liste:
		try:
			with open(os.path.join(info, n), encoding="utf-8", errors="replace") as f:
				randuri = [r.split("\t")[0].strip() for r in f]
		except (IOError, OSError):
			continue
		if skin_xml in randuri:
			return frozenset(_faraPyc(r) for r in randuri if r)
	return frozenset()


def stivaDinTema(stiva, dosar_tema, info=None):
	"""True cand stiva unei erori de ecran trece printr-un fisier al temei: sub dosarul ei sau din pachetul ei."""
	dosar = dosar_tema.rstrip("/") + "/"
	fisiere = _FISIER_IN_STIVA.findall(stiva or "")
	if any(f.startswith(dosar) for f in fisiere):
		return True
	pachet = None
	for f in fisiere:
		if pachet is None:
			pachet = fisierePachetTema(dosar, info)
			if not pachet:
				return False
		if _faraPyc(f) in pachet:
			return True
	return False

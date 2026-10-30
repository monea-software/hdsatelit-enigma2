# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaCatalog.py: catalogul fix al operatiilor pe care le poate cere Asistenta de la distanta (nivelul A:
# citiri si probe). E singura sursa a listei: ce se poate cere, ce i se arata omului in jurnal si pe pagina web vin
# toate de aici (data/asistenta/catalog.json), deci lista vazuta de om nu poate sa difere de ce se poate face.
#
# O operatie are: op (numele scurt, trimis in cererea semnata), grup si text (pentru om, traduse la afisare), fel
# („citire" sau „proba", pentru randul din jurnal) si args (zero sau mai multi, fiecare cu un tipar strict). Validarea
# unei cereri (valideaza) nu ruleaza nimic: verifica numai ca op e in catalog si ca argumentele se potrivesc tiparelor.
# Rularea insasi o face Components/HdsAsistentaBroker.py, care are cate o functie pentru fiecare op; o proba
# (test_asistenta_broker.py) cere ca orice op din catalog sa aiba o functie si invers, ca sa nu existe o operatie
# aratata omului fara rulare sau o rulare neanuntata.
#
# Catalogul se poate largi printr-o actualizare a pachetului (alt rand in catalog.json plus functia in broker), fara
# flash. Fisierul nu importa nimic din enigma2: probele de pe PC il incarca asa cum e.

import json
import os
import re

# calea catalogului in imagine (data/asistenta/catalog.json, pus de Makefile.am sub ${datadir}/enigma2/asistenta)
CALE_IMPLICITA = "/usr/share/enigma2/asistenta/catalog.json"
# pe PC, in teste, langa depozit
CALE_PC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "asistenta",
	"catalog.json")

FELURI = ("citire", "proba")
# un nume de op: litere mici, cifre si cratima; niciodata inceput cu cratima
_OP = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_NUME_ARG = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
# cel mult atatea argumente la o operatie si atatea semne intr-un argument (dincolo oricum nu trece niciun tipar); un
# argument poate cere in catalog o margine proprie ("max_semne"), dar niciodata peste MAX_SEMNE_ARG_LUNG (textul
# concluziilor echipei)
MAX_ARGUMENTE = 4
MAX_SEMNE_ARG = 256
MAX_SEMNE_ARG_LUNG = 2000


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele din catalog se traduc la afisare, nu la incarcare. TEXTE_CATALOG
	de mai jos tine aceleasi texte ca data/asistenta/catalog.json, ca xgettext sa le vada (sunt in JSON, nu in cod); o
	proba (test_asistenta.py) cere sa fie exact aceleasi."""
	return text


# aceleasi texte ca in catalog.json (grupuri si descrierea fiecarei operatii), ca sa fie traduse in cele 13 limbi
TEXTE_CATALOG = (
	N_("Informații"), N_("Semnal"), N_("Jurnale"), N_("Setări"), N_("Probe"),
	N_("starea receptorului (model, versiune, nucleu, memorie, disc, temperaturi)"),
	N_("placa: procesorul, linia de comandă a nucleului, partițiile, modulele încărcate"),
	N_("lista pachetelor instalate"),
	N_("rețeaua: cablu sau Wi-Fi, legat sau nu, ruta implicită, DNS (fără numele rețelei, MAC mascat)"),
	N_("tunerele și blocarea semnalului"),
	N_("starea decodorului (video, sunet, sincronizare)"),
	N_("memoria liberă și memoria decodorului"),
	N_("lista jurnalelor receptorului, cu mărimile"),
	N_("ultimele rânduri dintr-un jurnal"),
	N_("jurnalul nucleului"),
	N_("lista proceselor (numele, fără argumente)"),
	N_("copie filtrată a setărilor (audio, video, interfață, rețea; fără parole și chei)"),
	N_("o captură a ecranului (numai meniurile, fără imaginea canalului)"),
	N_("un mesaj scris pe ecranul televizorului"),
	N_("concluziile echipei (ce am găsit și ce am făcut), arătate pe receptor până apeși OK"),
)


def cale(cale_=None):
	if cale_:
		return cale_
	if os.path.exists(CALE_IMPLICITA):
		return CALE_IMPLICITA
	return os.path.normpath(CALE_PC)


_cache = {}


def incarca(cale_=None):
	"""Lista operatiilor din catalog.json, verificata. Pune in cache dupa calea fisierului. ValueError daca fisierul
	nu are forma buna (un catalog stricat nu trebuie sa lase sa treaca nimic)."""
	c = cale(cale_)
	cheie = os.path.abspath(c)
	if cheie in _cache:
		return _cache[cheie]
	with open(c, "rb") as f:
		octeti = f.read(256 * 1024)
	o = json.loads(octeti.decode("utf-8"))
	if not isinstance(o, dict) or o.get("fel") != "hds-asistenta-catalog" or not isinstance(o.get("operatii"), list):
		raise ValueError("catalog: antet")
	operatii = []
	vazute = set()
	for intrare in o["operatii"]:
		op = _verifica_intrare(intrare)
		if op["op"] in vazute:
			raise ValueError("catalog: op de doua ori: %s" % op["op"])
		vazute.add(op["op"])
		operatii.append(op)
	if not operatii:
		raise ValueError("catalog: gol")
	_cache[cheie] = operatii
	return operatii


def _verifica_intrare(intrare):
	if not isinstance(intrare, dict):
		raise ValueError("catalog: o intrare nu e obiect")
	op = intrare.get("op")
	if not isinstance(op, str) or not _OP.match(op):
		raise ValueError("catalog: op rau: %r" % (op,))
	fel = intrare.get("fel")
	if fel not in FELURI:
		raise ValueError("catalog: fel rau la %s: %r" % (op, fel))
	grup = intrare.get("grup")
	text = intrare.get("text")
	if not isinstance(grup, str) or not grup or not isinstance(text, str) or not text:
		raise ValueError("catalog: grup sau text lipsa la %s" % op)
	args = intrare.get("args", [])
	if not isinstance(args, list) or len(args) > MAX_ARGUMENTE:
		raise ValueError("catalog: args rau la %s" % op)
	arg_verif = []
	for a in args:
		arg_verif.append(_verifica_arg(op, a))
	return {"op": op, "grup": grup, "text": text, "fel": fel, "args": arg_verif}


def _verifica_arg(op, a):
	if not isinstance(a, dict):
		raise ValueError("catalog: argument rau la %s" % op)
	nume = a.get("nume")
	tipar = a.get("tipar")
	if not isinstance(nume, str) or not _NUME_ARG.match(nume) or not isinstance(tipar, str) or not tipar:
		raise ValueError("catalog: argument rau la %s" % op)
	try:
		rx = re.compile(tipar)
	except re.error as e:
		raise ValueError("catalog: tipar rau la %s/%s: %s" % (op, nume, e))
	max_semne = a.get("max_semne", MAX_SEMNE_ARG)
	if not isinstance(max_semne, int) or isinstance(max_semne, bool) or not 1 <= max_semne <= MAX_SEMNE_ARG_LUNG:
		raise ValueError("catalog: max_semne rau la %s/%s" % (op, nume))
	return {"nume": nume, "tipar": tipar, "rx": rx, "cerut": bool(a.get("cerut", False)), "max_semne": max_semne}


def gaseste(op, cale_=None):
	"""Intrarea unei operatii dupa nume, sau None."""
	for intrare in incarca(cale_):
		if intrare["op"] == op:
			return intrare
	return None


def valideaza(op, args, cale_=None):
	"""(bun, motiv): True daca op e in catalog si args (o lista de texte) se potrivesc tiparelor. Nu ruleaza nimic.
	motiv (pentru jurnal) cand nu e bun: op-necunoscut, prea-multe-argumente, lipseste-<nume>, argument-<nume>."""
	intrare = gaseste(op, cale_)
	if intrare is None:
		return False, "op-necunoscut"
	if not isinstance(args, list):
		return False, "argumente-rau"
	specs = intrare["args"]
	if len(args) > len(specs):
		return False, "prea-multe-argumente"
	for i, spec in enumerate(specs):
		if i >= len(args) or args[i] in (None, ""):
			if spec["cerut"]:
				return False, "lipseste-%s" % spec["nume"]
			continue
		v = args[i]
		if not isinstance(v, str) or len(v) > spec["max_semne"] or not spec["rx"].match(v):
			return False, "argument-%s" % spec["nume"]
	return True, ""


def pentru_afisare(cale_=None):
	"""Lista pentru pagina web si pentru om: [(op, grup, fel, text)], cu textul marcat pentru traducere."""
	return [(i["op"], i["grup"], i["fel"], i["text"]) for i in incarca(cale_)]

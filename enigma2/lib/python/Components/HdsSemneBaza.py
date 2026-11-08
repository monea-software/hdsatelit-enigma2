# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HDSatelit: semnul „$” din lista de canale ia si ce stie baza canalelor (Components/HdsBazaCanale.py, grupa „ca”,
# pozitia 0: 1 = criptat), umpluta de comutari si de „Scanare detaliata” (cererea din 02.11.2026: scanarile detaliate spun
# deja care canale sunt codate). Masurat pe receptorul de proba la 0.6.21: baza stia 4616 canale codate, lista arata „$” la 1094.
#
# La pornire (o singura trecere, la PORNIRE_S dupa sesiune, pe firul enigma2) se pune steagul dxIsScrambledPMT (1024,
# lib/dvb/idvb.h) pe serviciile din lamedb pe care baza le stie codate si care n-au inca nici steagul, nici CAID-uri
# (C:): listboxservice.cpp il deseneaza ca „$”, dupa setarea „Semnele din lista de canale”. Steagul ajunge in lamedb la
# urmatoarea salvare a listei (f:400), in forma citita si de alte imagini. Baza nu se schimba si niciun canal nu se scoate;
# un canal pe care baza il stie FTA nu pierde semnul pus de cautare sau de PMT.

from __future__ import absolute_import

import json
import re

try:
	from Components.HdsListeText import text_lista
except ImportError:
	from HdsListeText import text_lista

STEAG_CODAT = 1024
PORNIRE_S = 30
CALE_LAMEDB = "/etc/enigma2/lamedb"
_RE_STEAGURI = re.compile(r"(?:^|,)f:([0-9a-fA-F]+)")


def _cale_baza():
	from Components import HdsBazaCanale
	return HdsBazaCanale.CALE


def _cheie(parti):
	"""(sid, ns, tsid, onid) ca numere -> cheia bazei, „sid:ns:tsid:onid" hex fara zerouri in fata."""
	return "%x:%x:%x:%x" % tuple(parti)


def chei_codate(cale=None):
	"""Cheile canalelor pe care baza le stie codate (grupa ca, pozitia 0 = 1). Randurile stricate se sar."""
	rez = set()
	try:
		f = open(cale or _cale_baza(), "r")
	except (IOError, OSError):
		return rez
	with f:
		for rand in f:
			if '"ca"' not in rand or '"k"' not in rand:
				continue
			try:
				r = json.loads(rand)
			except ValueError:
				continue
			ca = r.get("ca")
			k = r.get("k")
			if not isinstance(k, str) or not isinstance(ca, list) or not ca:
				continue
			if ca[0] == 1:
				rez.add(k.lower())
	return rez


def servicii_lamedb(cale=CALE_LAMEDB):
	"""(sid, ns, tsid, onid, tip, semnat) pentru fiecare serviciu din lamedb (versiunea 4); semnat = are deja CAID-uri
	(C:) sau steagul 1024, deci „$" se vede si fara baza. In cheie primele patru campuri sunt hex, tipul e ZECIMAL
	(lib/dvb/db.cpp: "%x:%x:%x:%x:%d:%d"; 25 = H.264 HD, in referinta 19)."""
	try:
		f = open(cale, "rb")
	except (IOError, OSError):
		return
	with f:
		text = text_lista(f.read()).replace("\r\n", "\n").replace("\r", "\n")
		linii = text.split("\n")
	try:
		i = linii.index("services") + 1
	except ValueError:
		return
	while i + 2 < len(linii) and linii[i].strip() != "end":
		cheie, parametri = linii[i].strip(), linii[i + 2]
		i += 3
		parti = cheie.split(":")
		if len(parti) < 5:
			continue
		try:
			sid, ns, tsid, onid = [int(p, 16) for p in parti[:4]]
			tip = int(parti[4], 10)
		except ValueError:
			continue
		m = _RE_STEAGURI.search(parametri)
		semnat = "C:" in parametri or bool(m and int(m.group(1), 16) & STEAG_CODAT)
		yield sid, ns, tsid, onid, tip, semnat


def de_marcat(cale_baza=None, cale_lamedb=CALE_LAMEDB):
	"""Referintele serviciilor de marcat: codate in baza, fara „$" in lista."""
	codate = chei_codate(cale_baza)
	if not codate:
		return []
	rez = []
	for sid, ns, tsid, onid, tip, semnat in servicii_lamedb(cale_lamedb):
		if not semnat and _cheie((sid, ns, tsid, onid)) in codate:
			rez.append("1:0:%X:%X:%X:%X:%X:0:0:0:" % (tip, sid, tsid, onid, ns))
	return rez


def marcheaza(cale_baza=None, cale_lamedb=CALE_LAMEDB, refs=None):
	"""Pune steagul 1024 pe serviciile de marcat (refs, daca sunt date deja), in lista din memorie. -> cate."""
	from enigma import eDVBDB, eServiceReference
	db = eDVBDB.getInstance()
	n = 0
	for ref in (de_marcat(cale_baza, cale_lamedb) if refs is None else refs):
		if db.addFlag(eServiceReference(ref), STEAG_CODAT) == 0:
			n += 1
	return n


# Citirea bazei si a lamedb (~1,5 s pe V20 cu 9578 de canale) merge pe un fir separat, ca interfata sa nu stea; steagurile
# le pune firul enigma2 (eDVBDB nu se atinge din alt fir), cand rezultatul e gata (un ceas care se uita o data pe secunda).
_stare = {"refs": None, "eroare": None}
_timer = []


def _citeste():
	try:
		_stare["refs"] = de_marcat()
	except Exception as e:
		_stare["eroare"] = e
		_stare["refs"] = []


def _verifica():
	if _stare["refs"] is None:
		return
	_timer[-1].stop()
	if _stare["eroare"] is not None:
		_jurnal("citirea bazei canalelor: %s" % _stare["eroare"], eroare=True)
		return
	try:
		n = marcheaza(refs=_stare["refs"])
		_jurnal("canale codate marcate din baza canalelor: %d" % n)
	except Exception as e:
		_jurnal("marcarea din baza canalelor: %s" % e, eroare=True)


def _jurnal(mesaj, eroare=False):
	"""Pe consola si in /home/root/logs/hds-zap.log (Components/HdsJurnal.py), ca rezultatul sa se vada si de la
	distanta."""
	print("[HdsSemneBaza] %s" % mesaj)
	try:
		from Components import HdsJurnal
		(HdsJurnal.avert if eroare else HdsJurnal.info)("zap", "semne", mesaj)
	except Exception:
		pass


def _incepe():
	import threading
	from enigma import eTimer
	t = threading.Thread(target=_citeste, name="HdsSemneBaza")
	t.daemon = True
	t.start()
	v = eTimer()
	v.callback.append(_verifica)
	v.start(1000, False)
	# ceasul de pornire ramane in lista: el ruleaza chiar acum functia asta si nu se elibereaza din propriul apel
	_timer.append(v)


def porneste():
	"""Din mytest.py, dupa pornirea sesiunii: o singura trecere, la PORNIRE_S secunde."""
	from enigma import eTimer
	t = eTimer()
	t.callback.append(_incepe)
	t.start(PORNIRE_S * 1000, True)
	_timer[:] = [t]

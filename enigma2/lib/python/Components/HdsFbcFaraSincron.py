# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFbcFaraSincron.py - tunere FBC care, de la pornirea receptorului, vad semnalul antenei dar nu se sincronizeaza pe
# niciun transponder: receptorul spune omului, o singura data, ca ajuta o repornire completa si i-o ofera.
#
# De ce (UFB8, 22.11.2026; asistenta 046836, Vu+ Uno 4K, 8 x 45308X FBC, imaginea 0.7.7 pornita prima data de pe disc, prin pornire multipla):
# de la prima acordare de dupa instalare, toate acordarile pe tunerul A au dat purtatoare si viterbi, dar fara
# sincronizare (hds-tuner.log: „purtatoare=1 viterbi=1 sincronizare=0”, nivel 51-59 %), pe opt transpondere, la orice
# configurare. Legaturile FBC (fbc_connect/fbc_link, Components/HdsFbc.py) erau scrise la fiecare configurare, cu
# aceleasi valori ca dupa repornire; repornirea interfetei NU a ajutat, repornirea completa a receptorului da, cu exact
# aceleasi setari. Deci starea stricata e in driver/platforma, sub enigma2; cauza ei nu se vede in jurnale (dmesg-ul
# primei porniri s-a pierdut). Aceasta e o OCOLIRE: omul nu mai cauta o ora prin setari.
#
# Cand se arata (toate deodata, citite numai din hds-tuner.log al pornirii de acum a receptorului):
#  - inceputul pornirii: randul „[jurnal] pornit” al primei porniri a interfetei de dupa pornirea receptorului, tinut
#    in /tmp (tmpfs: se sterge la repornirea receptorului, ramane la repornirea interfetei); fara el, de la ultimul
#    rand „pornit”; nicio comparatie de timpi;
#  - de atunci niciun tuner n-a prins nimic (orice rand [acordare] cu „semnal in”, de orice fel de receptie);
#  - macar ACORDARI_MIN acordari cazute pe tunere FBC (numele din randurile [configurare] are „FBC”) cu purtatoare=1,
#    viterbi=1, sincronizare=0 si nivel >= NIVEL_MIN %, pe macar TRANSPONDERE_MIN transpondere diferite. ATENTIE: pe
#    driverul 45308X FBC si un tuner FARA cablu da purtatoare=1 viterbi=1 sincronizare=0 (AS107, tunerul B, nivel
#    24-25 %), deci bitii singuri nu deosebesc nimic; nivelul il desparte de mufa goala (A cu antena: 51-59 %). Un
#    DiSEqC sau un LNB gresit, cu antena in mufa, poate trece de prag: de aceea textul spune „daca setarile sunt cele
#    bune”, iar raspunsul implicit e Nu;
#  - Components/HdsFbcMutare.py nu mai are nicio pereche de judecat (cablul in mufa cealalta il rezolva ea, intai);
#  - semnul config.misc.hds_fbc_fara_sincron e gol: oferta se face o singura data (Da sau Nu, nu se mai intreaba).
# Fara FBC, dupa un singur semnal prins, sub prag sau fara purtatoare nu se arata nimic. Nu reporneste singur:
# Da = repornire completa, Nu (implicit) = nimic.
#
# Logica e in functii fara enigma (probe pe PC: teste/test_ufb8_fbc_fara_sincron.py).

import re

PRIMA_S = 60                  # dupa pornirea interfetei: macar cateva acordari
PAS_S = 30                    # citirea jurnalului, pana la hotarare
CITIRI_MAX = 40               # ~20 de minute; apoi abia la pornirea urmatoare
ACORDARI_MIN = 3
TRANSPONDERE_MIN = 2
NIVEL_MIN = 40                # % (AS107: mufa fara cablu 24-25 %, mufa cu antena 51-59 %)
SEMN_PORNIRE = "/tmp/hds-fbc-fara-sincron.pornire"

OFERTA, PRINS, ASTEAPTA = "oferta", "prins", "asteapta"

_RAND_PORNIT = re.compile(r"\[jurnal\] pornit: .*\bup=([0-9.]+)s")
_RAND_CONFIG = re.compile(r"\[configurare\] ([A-Z]) \"([^\"]*)\"")
_RAND_ACORD = re.compile(r"\[acordare\] ([A-Z]) \S+ \S+ ([0-9]+) ([HVLR]) ")
_FARA_SINCRON = "purtatoare=1 viterbi=1 sincronizare=0"
_NIVEL = re.compile(r"\bnivel ([0-9]+)%")

_sesiune = None
_ceas = None
_citiri = 0
_inceput = ""


def _jurnal(text):
	print("[HdsFbcFaraSincron] %s" % text)


def ultimul_pornit(randuri):
	"""Ultimul rand „[jurnal] pornit” (pornirea interfetei de acum), sau ""."""
	for rand in reversed(randuri):
		if _RAND_PORNIT.search(rand):
			return rand
	return ""


def pornirea_de_acum(randuri, inceput=""):
	"""Randurile de la randul `inceput` (prima pornire a interfetei de dupa pornirea receptorului, din SEMN_PORNIRE);
	fara el sau negasit (jurnal rotit): de la ultimul rand „pornit”; fara niciun rand „pornit”: toate."""
	if inceput:
		for i in range(len(randuri) - 1, -1, -1):
			if randuri[i] == inceput:
				return randuri[i:]
	for i in range(len(randuri) - 1, -1, -1):
		if _RAND_PORNIT.search(randuri[i]):
			return randuri[i:]
	return randuri


def judeca(randuri, inceput=""):
	"""OFERTA, PRINS (un tuner a prins de la pornire: gata pe pornirea asta) sau ASTEAPTA."""
	fbc, acordari, transpondere = set(), 0, set()
	for rand in pornirea_de_acum(randuri, inceput):
		m = _RAND_CONFIG.search(rand)
		if m:
			if re.search(r"\bFBC\b", m.group(2)):
				fbc.add(m.group(1))
			else:
				fbc.discard(m.group(1))
			continue
		if "[acordare]" in rand and "semnal in" in rand:
			return PRINS
		m = _RAND_ACORD.search(rand)
		if not m:
			continue
		n = _NIVEL.search(rand)
		if (m.group(1) in fbc and "fara semnal" in rand and _FARA_SINCRON in rand and n
				and int(n.group(1)) >= NIVEL_MIN):
			acordari += 1
			transpondere.add((m.group(2), m.group(3)))
	if acordari >= ACORDARI_MIN and len(transpondere) >= TRANSPONDERE_MIN:
		return OFERTA
	return ASTEAPTA


def text_oferta():
	return _("De la pornirea receptorului niciun canal nu prinde, deși tunerul vede semnal pe cablul antenei. La "
		"receptoarele cu tunere FBC, mai ales la prima pornire după instalare, asta se repară uneori numai cu o repornire "
		"completă a receptorului (repornirea interfeței nu ajunge). Dacă antena și setările tunerului sunt cele bune (de "
		"pildă au mers cu altă imagine), merită încercat; setările rămân aceleași.\n\nRepornesc receptorul acum?")


def _citeste_jurnal():
	try:
		from Components import HdsJurnal
		randuri = []
		for vechi in (1, 0):
			try:
				with open(HdsJurnal.cale("tuner", vechi), "r") as f:
					randuri.extend(f.read().splitlines())
			except (IOError, OSError):
				pass
		return randuri
	except Exception as e:
		_jurnal("jurnalul tunerului: %r" % (e,))
		return []


def _inceputul():
	"""Randul „pornit” al primei porniri a interfetei de dupa pornirea receptorului (SEMN_PORNIRE), scris acum daca
	lipseste (deci aceasta e prima pornire a interfetei de la pornirea receptorului)."""
	try:
		with open(SEMN_PORNIRE, "r") as f:
			return f.read().strip()
	except (IOError, OSError):
		pass
	rand = ultimul_pornit(_citeste_jurnal())
	try:
		with open(SEMN_PORNIRE, "w") as f:
			f.write(rand)
	except (IOError, OSError) as e:
		_jurnal("semnul pornirii: %r" % (e,))
	return rand


def _mutare_ocupata():
	"""HdsFbcMutare inca are o pereche de judecat (cablul in cealalta mufa): ea intai."""
	try:
		from Components import HdsFbcMutare
		return getattr(HdsFbcMutare, "_proba", None) is not None or bool(HdsFbcMutare.de_judecat(scrie=False))
	except Exception as e:
		_jurnal("HdsFbcMutare: %r" % (e,))
		return False


def _semn():
	from Components.config import config, ConfigText
	if "hds_fbc_fara_sincron" not in config.misc.content.items:
		config.misc.hds_fbc_fara_sincron = ConfigText(default="", fixed_size=False)
	return config.misc.hds_fbc_fara_sincron


def _scrie_semn(text):
	el = _semn()
	el.value = text
	el.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("settings: %r" % (e,))


def _raspuns(da):
	import time
	_scrie_semn("%s:%s" % ("da" if da else "nu", time.strftime("%Y-%m-%d %H:%M")))
	try:
		from Components import HdsJurnal
		HdsJurnal.info("tuner", "fbc", "fara sincronizare de la pornire: oferta de repornire, raspuns %s" % ("da" if da else "nu"))
	except Exception:
		pass
	if da and _sesiune is not None:
		from Screens.Standby import TryQuitMainloop
		_sesiune.open(TryQuitMainloop, 2)


def _bataie():
	global _citiri
	_citiri += 1
	if _semn().value:
		return
	stare = judeca(_citeste_jurnal(), _inceput)
	if stare == OFERTA and _mutare_ocupata():
		stare = ASTEAPTA
	if stare == OFERTA:
		_jurnal("FBC fara sincronizare de la pornire: oferta de repornire completa")
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddNotificationWithCallback(_raspuns, MessageBox, text_oferta(), MessageBox.TYPE_YESNO, default=False)
		return
	if stare == ASTEAPTA and _citiri < CITIRI_MAX and _ceas is not None:
		_ceas.start(PAS_S * 1000, True)


def porneste(session):
	"""Din mytest.py. Cu semnul pus (oferta facuta o data) nu face nimic."""
	global _sesiune, _ceas, _citiri, _inceput
	_sesiune = session
	_citiri = 0
	_inceput = _inceputul()
	if _semn().value:
		return
	from enigma import eTimer
	_ceas = eTimer()
	_ceas.callback.append(_bataie)
	_ceas.start(PRIMA_S * 1000, True)

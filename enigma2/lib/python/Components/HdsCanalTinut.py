# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCanalTinut.py: canalul la care se uita omul, tinut minte ca dupa orice repornire a interfetei receptorul sa
# porneasca pe el (InfoBarGenerics.startupService, alegerea "last": config.tv.lastservice).
#
# Lista de pe televizor (ChannelSelection.zap -> saveChannel) il tine minte singura. Canalele pornite pentru om pe alta
# cale il tin minte prin tine_minte(ref): zap-ul din web si din aplicatiile de telefon (HdsWebControl
# plugin.zapReferinta), temporizatorul de comutare si comutarea pentru o inregistrare (RecordTimer). Ca in lista:
#   - un canal TV: config.tv.lastservice;
#   - un post de radio: config.radio.lastservice (ultimul canal TV ramane; cu lista radio separata ca in lista,
#     postul nu devine "ultimul canal TV").
# Zap-urile facute de imagine pentru ea insasi (readucerea antenei, verificarea pe alte transpondere, scanarea,
# culegerea, cautarea semnalului, probele LNB) NU trec pe aici: canalul tinut minte ramane al omului.
#
# Pe disc: element.save() schimba numai memoria; /etc/enigma2/settings il scrie enigma2 la iesirea curata (mytest.py)
# si meniurile. Ca canalul sa ramana si dupa o oprire fara iesire curata (paznicul care reporneste o interfata blocata,
# repornirea receptorului, curentul), NU se rescrie tot settings, ci numai canalul, intr-un fisier mic al lui
# (CALE_CANAL), scris sigur (fisier .nou, fsync, rename):
#   - numai dupa ce canalul tinut minte a ramas SCRIERE_DUPA_S secunde (60) pe ecran: ceasul o ia de la capat la
#     fiecare schimbare (si din lista), deci un sir de zap-uri rapide da o singura scriere, si numai cand canalul e altul
#     decat cel scris deja; o oprire fara iesire curata mai devreme porneste pe canalul de dinainte;
#   - inainte de orice repornire ceruta (Screens/Standby.TryQuitMainloop: actualizarea, /api/accel-reporneste, meniul,
#     repornirea pentru memorie), pe loc, oricat a stat canalul pe ecran.
# Fisierul are canalul si calea lui in lista (buchetul), TV si radio, plus "baza": canalul din settings in clipa
# scrierii. La pornirea interfetei (la_pornire, din InfoBarGenerics, inainte ca lista de canale sa fie facuta si
# inainte de primul zap) fisierul mic castiga numai cand e mai nou decat settings: canalul lui e altul, iar settings
# are inca baza lui (deci n-a mai fost scris dupa el). Fara ceas: la pornire ora receptorului poate fi gresita.
# Fisierul nu importa nimic din enigma2 la incarcare, ca probele de pe PC sa-l foloseasca cu falsi.

import os
import sys

SCRIERE_DUPA_S = 60
TIPURI_RADIO = (2, 10)      # tipul serviciului DVB: radio, radio AAC
CALE_CANAL = "/etc/enigma2/hds-ultimul-canal"
CALE_SETARI = "/etc/enigma2/settings"
# cheia din fisierul mic -> elementul din config (sectiunea, numele) si randul din settings
CHEI = (
	("tv", ("tv", "lastservice")),
	("tv_cale", ("tv", "lastroot")),
	("radio", ("radio", "lastservice")),
	("radio_cale", ("radio", "lastroot")),
)
# perechile canal / cale si baza lor (canalul din settings la scriere)
PARTI = (("tv", "tv_cale", "baza_tv"), ("radio", "radio_cale", "baza_radio"))

_ceas = [None]
_scris = [None]             # ce e acum in fisierul mic (dict), aflat o data


def _jurnal(text):
	print("[HdsCanalTinut] %s" % text)


def _config():
	m = sys.modules.get("Components.config")
	if m is None:
		from Components import config as m
	return m


def _element(c, sectiune, nume):
	return getattr(getattr(c, sectiune), nume)


def e_radio(ref):
	"""Un post de radio DVB (tipul serviciului 2 sau 10); fluxurile si restul: nu."""
	try:
		return ref.type == 1 and ref.getData(0) in TIPURI_RADIO
	except Exception:
		return False


def tine_minte(ref):
	"""Canalul `ref` (eServiceReference) pornit pentru om in afara listei: ultimul canal, ca la zap-ul din lista
	(value + save(), in memorie), apoi scrierea fisierului mic programata. -> True cand s-a schimbat ceva."""
	try:
		if ref is None or not ref.valid():
			return False
		c = _config().config
		el = c.radio.lastservice if e_radio(ref) else c.tv.lastservice
		text = ref.toString()
		if el.value == text:
			return False
		el.value = text
		el.save()
		programeaza_scrierea()
		return True
	except Exception as e:
		_jurnal("tine minte: %s" % e)
		return False


# ---------------------------------------------------------------- fisierele

def _citeste_perechi(cale):
	"""Fisierul mic (cheie=valoare pe rand) -> dict; None cand lipseste sau nu se poate citi."""
	try:
		with open(cale, encoding="utf-8") as f:
			rez = {}
			for r in f:
				r = r.rstrip("\r\n")
				if "=" in r:
					k, v = r.split("=", 1)
					rez[k.strip()] = v.strip()
			return rez
	except (IOError, OSError, UnicodeDecodeError, ValueError):
		return None


def _din_setari():
	"""Canalele (si caile) din fisierul settings de pe disc; "" pentru ce lipseste (valoarea din fabrica)."""
	rez = dict((k, "") for k, _e in CHEI)
	nume = dict(("config.%s.%s=" % e, k) for k, e in CHEI)
	try:
		with open(CALE_SETARI, encoding="utf-8") as f:
			for r in f:
				for inceput, k in nume.items():
					if r.startswith(inceput):
						rez[k] = r[len(inceput):].rstrip("\r\n")
	except (IOError, OSError, UnicodeDecodeError):
		return None
	return rez


def _acum():
	"""Canalele si caile tinute minte acum (memoria)."""
	c = _config().config
	return dict((k, _element(c, *e).value or "") for k, e in CHEI)


def _scrie_sigur(cale, text):
	nou = cale + ".nou"
	with open(nou, "w", encoding="utf-8") as f:
		f.write(text)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)   # rename atomic, peste fisierul vechi
	try:
		d = os.open(os.path.dirname(cale) or ".", os.O_RDONLY)
		try:
			os.fsync(d)
		finally:
			os.close(d)
	except (OSError, AttributeError):
		pass


def scrie_daca_s_a_schimbat():
	"""Fisierul mic scris cand canalul (sau calea) tinut minte e altul decat cel din el. -> True la scriere."""
	try:
		acum = _acum()
		if _scris[0] is None:
			_scris[0] = _citeste_perechi(CALE_CANAL) or {}
			if not _scris[0]:
				# fara fisier mic: ce e in settings e la zi pana la prima schimbare
				_scris[0] = _din_setari() or {}
		if all(_scris[0].get(k, "") == v for k, v in acum.items()):
			return False
		baza = _din_setari() or {}
		rand = dict(acum)
		rand["baza_tv"] = baza.get("tv", "")
		rand["baza_radio"] = baza.get("radio", "")
		_scrie_sigur(CALE_CANAL, "".join("%s=%s\n" % (k, rand[k]) for k in
			("tv", "tv_cale", "radio", "radio_cale", "baza_tv", "baza_radio")))
		_scris[0] = rand
		return True
	except Exception as e:
		_jurnal("scrierea: %s" % e)
		return False


def programeaza_scrierea():
	"""Scrierea fisierului mic peste SCRIERE_DUPA_S secunde de la ultima schimbare (ceasul o ia de la capat la fiecare
	zap, deci canalul a ramas cel putin atat pe ecran)."""
	try:
		if _ceas[0] is None:
			from enigma import eTimer
			t = eTimer()
			t.callback.append(scrie_daca_s_a_schimbat)
			_ceas[0] = t
		_ceas[0].start(SCRIERE_DUPA_S * 1000, True)
	except Exception as e:
		_jurnal("scrierea programata: %s" % e)


def scrie_acum():
	"""Inainte de o repornire ceruta (TryQuitMainloop): fisierul mic la zi, pe loc (settings il scrie enigma2 la iesire)."""
	try:
		if _ceas[0] is not None:
			_ceas[0].stop()
	except Exception:
		pass
	return scrie_daca_s_a_schimbat()


def la_pornire():
	"""La pornirea interfetei, inainte ca lista de canale sa fie facuta si inainte de primul zap: canalul (si calea lui)
	din fisierul mic, cand e mai nou decat cel din settings. -> lista partilor luate din fisierul mic ("tv", "radio")."""
	luate = []
	try:
		mic = _citeste_perechi(CALE_CANAL)
		if not mic:
			return luate
		c = _config().config
		for canal, cale, baza in PARTI:
			el = _element(c, *dict(CHEI)[canal])
			din_setari = el.value or ""
			nou = mic.get(canal, "")
			if not nou or nou == din_setari or mic.get(baza, "") != din_setari:
				continue
			el.value = nou
			el.save()
			if mic.get(cale):
				ec = _element(c, *dict(CHEI)[cale])
				ec.value = mic[cale]
				ec.save()
			luate.append(canal)
			_jurnal("pornire: %s din %s (%s; in settings %s)" % (canal, CALE_CANAL, nou, din_setari or "-"))
		_scris[0] = mic
	except Exception as e:
		_jurnal("pornire: %s" % e)
	return luate

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbISurse: listele DVB-I (sursele) care nu raspund, ca jurnalul sa nu se umple si omul sa nu astepte degeaba.
#
# DVJ (15.11.2026, jurnalele testerilor 2090, 2093, 2102): o lista din registre (de pilda una germana care nu mai
# raspunde deloc, nici din Germania) dadea "timed out" dupa 15 s la fiecare pornire si la fiecare reincarcare din ora
# in ora, cu cate un rand in jurnal de fiecare data. Acum:
#   - o adresa care nu raspunde, in timp ce alte liste raspund (deci vina e a ei, nu a internetului), se pune in pauza
#     crescatoare: PAUZE_S dupa 1, 2, 3 ... caderi la rand, pana la o zi. Pauza se tine pe disc (CALE), deci o pornire
#     a receptorului nu o mai incearca inainte de vreme. Reincarcarea ceruta de om (ecranul DVB-I, pagina web) le
#     incearca pe toate;
#   - jurnalul: un rand la prima cadere, apoi cel mult unul pe zi cat tot nu raspunde, si un rand cand raspunde iar;
#   - cand nu raspunde NICIO lista incercata (receptorul pornit fara internet, routerul inca nepregatit, ceva din retea
#     care raspunde in locul serverelor: pe un receptor toate adresele HTTPS, si cele din afara DVB-I, au cazut in
#     acelasi minut cu "handshake failure"), sursele nu sunt de vina: pauzele lor nu cresc, iar reincarcarea se reia
#     curand (REINCERCARI_RETEA_S), nu peste o ora; tot un singur rand in jurnal.
# Fara enigma2: probele de pe PC il incarca direct (ceasul, jurnalul si calea se dau din afara).
from __future__ import absolute_import, print_function, unicode_literals

import json
import os
import time

CALE = "/etc/enigma2/hdsdvbi-surse.json"
PAUZE_S = (3600, 3 * 3600, 6 * 3600, 12 * 3600, 24 * 3600)   # dupa 1, 2, 3, 4, 5+ caderi la rand
REINCERCARI_RETEA_S = (60, 120, 300, 600)   # cand nu raspunde nicio lista: urmatoarele reincarcari, apoi intervalul
JURNAL_S = 24 * 3600          # acelasi rand despre aceeasi adresa cel mult o data in atat
CEAS_INAPOI_S = 300           # ceasul dat inapoi mai mult de atat (pornire cu ceasul vechi): pauza nu mai tine
MAX_ADRESE = 200
MAX_EROARE = 160


def _scurt(text):
	text = " ".join(("%s" % (text,)).split())
	return text[:MAX_EROARE]


def _durata(secunde):
	secunde = int(max(0, secunde))
	if secunde >= 3600:
		return "%d h" % (secunde // 3600)
	if secunde >= 60:
		return "%d min" % (secunde // 60)
	return "%d s" % secunde


class Surse(object):
	def __init__(self, cale=CALE, ceas=None, jurnal=None):
		self.cale = cale
		self.ceas = ceas or time.time
		self.jurnal = jurnal or (lambda text: print("[HdsDvbI] %s" % text))
		self.date = {}       # adresa -> {"caderi", "prima", "ultima", "urmatoarea", "eroare", "jurnal"}
		self.retea = None    # {"de_la", "jurnal", "pas"} cat nu raspunde nicio lista (numai in memorie)
		self._citit = False

	# ---- disc
	def _incarca(self):
		if self._citit:
			return
		self._citit = True
		if not self.cale:
			return
		try:
			with open(self.cale, "rb") as f:
				d = json.loads(f.read().decode("utf-8"))
		except (IOError, OSError, ValueError):
			return
		if not isinstance(d, dict):
			return
		for adresa, v in d.items():
			if not isinstance(v, dict):
				continue
			try:
				self.date[str(adresa)] = {"caderi": int(v.get("caderi", 0)), "prima": float(v.get("prima", 0)),
					"ultima": float(v.get("ultima", 0)), "urmatoarea": float(v.get("urmatoarea", 0)),
					"eroare": _scurt(v.get("eroare", "")), "jurnal": float(v.get("jurnal", 0))}
			except (TypeError, ValueError):
				continue

	def _scrie(self):
		if not self.cale:
			return
		while len(self.date) > MAX_ADRESE:
			del self.date[min(self.date, key=lambda a: self.date[a]["ultima"])]
		nou = self.cale + ".nou"
		try:
			with open(nou, "wb") as f:
				f.write(json.dumps(self.date, ensure_ascii=True, sort_keys=True).encode("ascii"))
			os.replace(nou, self.cale)
		except (IOError, OSError) as e:
			print("[HdsDvbI] nu pot scrie %s: %s" % (self.cale, e))
			try:
				os.unlink(nou)
			except OSError:
				pass

	# ---- intrebari
	def inPauza(self, adresa, acum=None):
		"""ora pana la care adresa nu se mai incearca (0 = se incearca acum)"""
		self._incarca()
		v = self.date.get(adresa)
		if not v:
			return 0
		acum = self.ceas() if acum is None else acum
		if acum < v["ultima"] - CEAS_INAPOI_S:
			return 0   # ceasul a fost dat inapoi: pauza socotita cu alt ceas nu mai tine
		return v["urmatoarea"] if acum < v["urmatoarea"] else 0

	def deIncercat(self, adrese, forteaza=False, acum=None):
		"""(de incercat, sarite: {adresa: pana la}); cu forteaza (reincarcarea ceruta de om) toate se incearca"""
		if forteaza:
			return list(adrese), {}
		acum = self.ceas() if acum is None else acum
		incercat, sarite = [], {}
		for a in adrese:
			p = self.inPauza(a, acum)
			if p:
				sarite[a] = p
			else:
				incercat.append(a)
		return incercat, sarite

	def eroare(self, adresa):
		self._incarca()
		v = self.date.get(adresa)
		return v["eroare"] if v else ""

	def faraRaspuns(self, adresa):
		"""DVK (15.11.2026): pentru ecranul DVB-I si pagina web, (de cand nu raspunde, urmatoarea incercare) sau None
		daca adresa raspunde (sau n-a fost incercata); numai citire"""
		self._incarca()
		v = self.date.get(adresa)
		if not v:
			return None
		return v["prima"], v["urmatoarea"]

	# ---- dupa o trecere
	def noteaza(self, rezultate, acum=None):
		"""rezultate: [(adresa, ok, eroare)] pentru adresele incercate acum. -> secundele pana la reincarcarea
		urmatoare cand nu a raspuns niciuna (reteaua, nu sursele), altfel None (intervalul obisnuit)"""
		self._incarca()
		acum = self.ceas() if acum is None else acum
		if not rezultate:
			return None
		if not any(ok for _a, ok, _e in rezultate):
			return self._faraRetea(rezultate, acum)
		if self.retea is not None:
			self.jurnal("listele DVB-I raspund din nou (nu raspundea niciuna de %s)"
				% _durata(acum - self.retea["de_la"]))
			self.retea = None
		schimbat = False
		for adresa, ok, eroare in rezultate:
			v = self.date.get(adresa)
			if ok:
				if v is not None:
					self.jurnal("lista %s raspunde din nou (dupa %d incercari fara raspuns)" % (adresa, v["caderi"]))
					del self.date[adresa]
					schimbat = True
				continue
			eroare = _scurt(eroare or "fara raspuns")
			if v is None:
				v = self.date[adresa] = {"caderi": 0, "prima": acum, "ultima": acum, "urmatoarea": 0, "eroare": "",
					"jurnal": 0}
			v["caderi"] += 1
			v["ultima"] = acum
			v["eroare"] = eroare
			pauza = PAUZE_S[min(v["caderi"], len(PAUZE_S)) - 1]
			v["urmatoarea"] = acum + pauza
			if v["caderi"] == 1:
				self.jurnal("lista %s nu raspunde (%s); o incerc din nou peste %s" % (adresa, eroare, _durata(pauza)))
				v["jurnal"] = acum
			elif acum - v["jurnal"] >= JURNAL_S or acum < v["jurnal"]:
				self.jurnal("lista %s tot nu raspunde (%s; %d incercari de %s); urmatoarea peste %s"
					% (adresa, eroare, v["caderi"], _durata(acum - v["prima"]), _durata(pauza)))
				v["jurnal"] = acum
			schimbat = True
		if schimbat:
			self._scrie()
		return None

	def _faraRetea(self, rezultate, acum):
		r = self.retea
		if r is None:
			r = self.retea = {"de_la": acum, "jurnal": acum, "pas": 0}
			self.jurnal("nicio lista DVB-I nu raspunde (%d incercate; %s: %s); internetul receptorului nu pare "
				"pregatit, reincerc peste %s" % (len(rezultate), rezultate[0][0], _scurt(rezultate[0][2] or
				"fara raspuns"), _durata(REINCERCARI_RETEA_S[0])))
		else:
			r["pas"] += 1
			if acum - r["jurnal"] >= JURNAL_S or acum < r["jurnal"]:
				r["jurnal"] = acum
				self.jurnal("tot nu raspunde nicio lista DVB-I (de %s)" % _durata(acum - r["de_la"]))
		if r["pas"] < len(REINCERCARI_RETEA_S):
			return REINCERCARI_RETEA_S[r["pas"]]
		return None


_SURSE = {}


def surse(cale=None):
	"""starea comuna a pluginului pentru fisierul `cale` (implicit CALE), citita de pe disc la prima folosire; pluginul
	da fisierul de langa starea lui, deci probele care o muta intr-un dosar temporar il muta si pe acesta"""
	cale = cale or CALE
	s = _SURSE.get(cale)
	if s is None:
		s = _SURSE[cale] = Surse(cale)
	return s

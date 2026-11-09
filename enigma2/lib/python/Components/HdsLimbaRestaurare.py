# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Pune la loc limba si ajutorul pierdute dupa restaurare sau actualizare."""

import os
import re

CALE = "etc/enigma2/hds-limba-restaurare.json"
PREFIX_PO = "enigma2-hdsatelit-po-"
AJUTOR = "hdsatelit-ajutor"
_LIMBA = re.compile(r"^[a-z]{2,3}(?:_[A-Za-z0-9-]{1,12})?\Z")
_PACHET = re.compile(
	r"^(?:enigma2-hdsatelit-po-|hdsatelit-ajutor-)[a-z]{2,3}"
	r"(?:-[a-z0-9]{2,8})?\Z")
REINCERCARE_MS = 5 * 60 * 1000


def _modul(nume):
	try:
		return __import__("Components." + nume, fromlist=[nume])
	except ImportError:
		return __import__(nume)


def _actualizari():
	return _modul("HdsActualizari")


def _r():
	return _modul("HdsReinstalare")


def _c(rad, rel):
	return os.path.join(rad or "/", *rel.split("/"))


def _cod(limba):
	return "pt-br" if limba == "pt_BR" else limba.split("_", 1)[0]


def verifica(date):
	if not isinstance(date, dict) or not isinstance(date.get("limba"), str) \
			or not _LIMBA.fullmatch(date["limba"]):
		raise ValueError("limba nu are un cod bun")
	pachete = date.get("pachete")
	if not isinstance(pachete, list) or len(pachete) > 120 or any(
			not isinstance(n, str) or (n != AJUTOR and not _PACHET.fullmatch(n))
			for n in pachete):
		raise ValueError("lista pachetelor limbii nu e buna")
	return {"limba": date["limba"], "pachete": sorted(set(pachete))}


def citeste(rad="/"):
	try:
		return verifica(_r()._citeste_json(_c(rad, CALE)))
	except ValueError:
		return None


def _limba(rad, text=None):
	if text is None:
		try:
			with open(_c(rad, "etc/enigma2/settings"), encoding="utf-8") as f:
				text = f.read(1024 * 1024)
		except OSError:
			text = ""
	for rand in reversed(text.splitlines()):
		cheie, egal, valoare = rand.partition("=")
		if egal and cheie == "config.osd.language" and _LIMBA.fullmatch(valoare):
			return valoare
	return "ro_RO"


def _instalate(rad):
	A = _actualizari()
	inst = set(A.instalate(rad))
	P = _modul("HdsParteaDoua")
	conf = P.citesteConf(rad)
	if conf and P.radacinaNand(rad) and P.esteMontat(rad, conf):
		cale = _c(rad, P.montare(conf).lstrip("/") + "/var/lib/opkg/status")
		inst.update(s["package"] for s in A.P.citeste_strofe(cale)
			if s.get("status", "").split()[-1:] == ["installed"])
	return inst


def stare(rad="/", text_setari=None):
	pachete = [n for n in _instalate(rad) if n == AJUTOR or _PACHET.fullmatch(n)]
	# O copie facuta fara retea pastreaza si cererile neindeplinite.
	pachete += (citeste(rad) or {}).get("pachete", [])
	return verifica({"limba": _limba(rad, text_setari), "pachete": pachete})


def pregateste(rad, date):
	date = verifica(date)
	if citeste(rad) != date:
		_r()._scrie_json(_c(rad, CALE), date)
	return date


def pastreaza(rad="/", limba=None):
	"""Inainte de actualizare: nu pierde cererile inca neindeplinite."""
	date = stare(rad)
	if limba is not None:
		date["limba"] = limba
	return pregateste(rad, date)


def lipsa(rad="/", limba=None):
	date = citeste(rad)
	limba = limba or _limba(rad)
	if not _LIMBA.fullmatch(limba):
		return []
	cod = _cod(limba)
	inst = _instalate(rad)
	po = PREFIX_PO + cod
	catalog = "pt_BR" if cod == "pt-br" else cod
	are_catalog = os.path.isfile(_c(rad,
		"usr/share/enigma2/po/%s/LC_MESSAGES/enigma2.mo" % catalog))
	rez = [po] if po not in inst and not are_catalog else []
	# Ajutorul pe limbi se cere numai daca omul il avea deja.
	for n in (date or {}).get("pachete", []):
		if n in (AJUTOR, AJUTOR + "-" + cod) and n not in inst:
			rez.append(n)
	return sorted(set(rez))


def _instaleaza(rad, pachete):
	"""Aceeasi semnatura si aceleasi fisiere verificate ca la actualizari."""
	A = _actualizari()
	P = _modul("HdsParteaDoua")
	pc = A.P.citeste_configurarea(rad)
	canal, surse, baza = A.canalul(rad, pc)
	if canal not in ("public", "proba") or not surse \
			or baza != A.baza_receptorului(rad):
		return []
	conf = P.citesteConf(rad)
	pe_stick = conf and P.radacinaNand(rad) and P.idLegat(rad)
	lacat = P.ocupaOperatia(rad)
	if lacat is None:
		return []
	dosar = _c(rad, "tmp/hds-limba-restaurare")
	try:
		limbi = [n for n in pachete if n.startswith(PREFIX_PO)]
		if pe_stick and limbi:
			# Nu dubleaza in memoria interna limbile destinate stickului.
			ok, _mesaj = P.actualizeazaContinut(rad, lacat=lacat, cerute=limbi)
			if not ok:
				return []
			pachete = [n for n in pachete if n not in limbi]
		if not pachete:
			return sorted(set(limbi) & _instalate(rad))
		adresa = A.adresa_stare(canal, baza).rsplit("/", 1)[0]
		credentiale = A.citeste_netrc(rad) if canal == "proba" else None
		server, eroare = A.descarca_stare(adresa + "/stare.json", credentiale)
		if eroare or server.get("baza") != baza or server.get("imagine_noua") \
				or server.get("canal", canal) != canal or \
				A.P.compara_versiuni(server.get("imagine_minima", ""), baza) > 0:
			return []
		plan = []
		for n in pachete:
			variante = [A.pachet_din_stare(server, n, arh) for arh in
				sorted(pc.arhitecturi, key=pc.arhitecturi.get, reverse=True)]
			p = next((p for p in variante if p), None)
			if p:
				plan.append({"nume": n, "la": p["versiune"],
					"arhitectura": p["arhitectura"]})
		if not plan:
			return []
		intrari, eroare = A.pachete_semnate({"stare": server},
			{"server": server, "pachete": plan})
		if eroare or A.pachete_straine(intrari, pc.arhitecturi):
			return []
		cai, eroare = A.descarca_pachete(intrari, adresa, credentiale, dosar)
		if eroare:
			return []
		comanda = _r()._opkg(rad, None)
		if comanda and not A.opkg_ocupat(rad) and not _actualizare_in_lucru(A):
			_r()._ruleaza(comanda + ["install"] + cai, 600)
		return sorted(set(pachete + limbi) & _instalate(rad))
	finally:
		A.goleste_dosarul(dosar)
		P.elibereazaOperatia(lacat)


def _actualizare_in_lucru(A):
	actualizare = getattr(A, "actualizari", None)
	return actualizare is not None and (
		actualizare.faza != "liber" or actualizare.repornire)


def lucreaza(rad="/", limba=None):
	cerute = lipsa(rad, limba)
	if not cerute:
		return {"stare": "gata", "puse": []}
	A = _actualizari()
	if A.fara_retea(rad) or A.opkg_ocupat(rad) or _actualizare_in_lucru(A):
		return {"stare": "amanat", "puse": []}
	puse = _instaleaza(rad, cerute)
	return {"stare": "amanat" if lipsa(rad, limba) else "gata", "puse": puse}


def _aleasa():
	from Components.config import config
	return config.osd.language.value


def _activeaza():
	from Components.Language import language
	aleasa = _aleasa()
	language.getLanguageList()
	if aleasa in language.lang and language.getActiveLanguage() != aleasa:
		language.activateLanguage(aleasa)


class _Ceas:
	def __init__(self):
		from enigma import eTimer
		self.lucrare = None
		self.ceas = eTimer()
		try:
			self.legatura = self.ceas.timeout.connect(self.verifica)
		except AttributeError:
			self.ceas.callback.append(self.verifica)
		self.ceas.start(60000, True)

	def verifica(self):
		from Components.HdsImportSurse import Lucrare
		if self.lucrare is not None:
			return
		aleasa = _aleasa()
		self.lucrare = Lucrare(lambda: lucreaza(limba=aleasa), self.gata)

	def gata(self, rez, eroare):
		self.lucrare = None
		if eroare:
			print("[HdsLimbaRestaurare] reincerc: %s" % type(eroare).__name__)
		# Callbackul este pe firul interfetei, dupa lucrul din fundal.
		try:
			_activeaza()
		finally:
			if eroare or not rez or rez.get("stare") == "amanat":
				self.ceas.start(REINCERCARE_MS, True)


_CEAS = []


def porneste(session=None, rezultat_copie=None):
	if rezultat_copie and rezultat_copie.get("repornire") == "ceruta":
		return
	pastreaza(limba=_aleasa())
	if not _CEAS:
		_CEAS.append(_Ceas())

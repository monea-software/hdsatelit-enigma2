# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAccesCanale - FTA sau criptat, tinut minte pe fiecare canal, pentru bara de jos, bara mare si afisajul detaliat.
#
# Pe ecran nu apare nimic cat starea canalului nu se stie; apoi FTA sau criptat, dupa analiza. O stare aflata la o
# vizionare anterioara se arata din prima.
#
# CAUZA: pana vine PMT-ul, nucleul raspunde sIsCrypted = -1 (lib/service/servicedvb.cpp, getInfo), iar convertorul
# socotea „nu e criptat” = FTA. Acum sunt trei stari: nu se stie (nimic pe ecran), „fta”, „criptat”. Ce afla analiza
# (sIsCrypted 0/1 sau CAID-urile din PMT) se arata pe loc si se tine minte aici; la zap, pana vine analiza, se arata
# starea tinuta minte, iar fara ea nimic. Starea de acum castiga mereu asupra celei tinute minte.
# Calculul starii de acum sta in Components/Converter/HdsCommon.py (Reader.acces), care merge si pe alte imagini: acolo,
# fara acest modul, nu se tine minte nimic, dar tot nu se mai arata FTA inainte de analiza.
#
# FISIERUL: /etc/enigma2/hds_acces_canale.json, {"v": 1, "c": {cheie: "f" | "c"}}, cheia din
# HdsIndexCanale.cheie_din_ref („sid:ns:tsid:onid”), cel mult MAX_CANALE (cele mai vechi pleaca primele). Scris atomic
# (temporar + fsync + os.replace), numai cand s-a schimbat ceva, cel mult o data la INTARZIERE_S (ca baza pistelor).
# Nu depinde de setarea „Citirea pistelor la vizionare”: e doar ce s-a vazut pe ecran.
# Un fisier care nu s-a putut citi nu e scris peste (Components/HdsFisierSigur.py): eroare de citire = numai citire
# pana la o citire buna (memoria se uneste atunci peste fisier); JSON stricat = pus deoparte ca .stricat-AAAALLZZ
# inaintea primei scrieri.
#
# BAZA UNICA: memorie() da acum adaptorul MemorieBaza peste Components/HdsBazaCanale.py (grupa ca); acolo se
# noteaza accesul numai de culegerea unita (Components/HdsCulegereCanale.py), dupa PMT. Clasa Memorie si fisierul de
# mai sus raman pentru migrare (citite fara scriere) si pentru cazul in care baza unica nu se incarca.
#
# PARTEA DE SUS E CURATA (fara enigma): probele pe PC in 
# test_acces_canale.py.

from __future__ import absolute_import

import json
import os

try:
	from Components import HdsIndexCanale as _X
	from Components import HdsFisierSigur as _S
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsIndexCanale as _X
	import HdsFisierSigur as _S

CALE = "/etc/enigma2/hds_acces_canale.json"
VERSIUNE = 1
MAX_CANALE = 20000
MAX_OCTETI = 2 * 1024 * 1024
INTARZIERE_S = 30

FTA = "fta"
CRIPTAT = "criptat"
STARI = (FTA, CRIPTAT)
_COD = {FTA: "f", CRIPTAT: "c"}
_STARE = {"f": FTA, "c": CRIPTAT}


def _jurnal(text):
	print("[HdsAccesCanale] %s" % text)


def cheie(ref_text):
	"""Cheia canalului DVB („sid:ns:tsid:onid”) sau None (inregistrari, fisiere, fluxuri din retea)."""
	try:
		k = _X.cheie_din_ref(ref_text)
	except Exception:
		return None
	return k if k and k.count(":") == 3 else None


def _programatorEnigma(functie, secunde):
	"""O singura chemare, dupa `secunde`, pe firul enigma2 (eTimer); pe PC nu exista, deci None."""
	try:
		from enigma import eTimer
	except ImportError:
		return None
	t = eTimer()
	t.callback.append(functie)
	t.start(int(secunde * 1000), True)
	return t


class Memorie(object):
	"""Starea tinuta minte a canalelor. `programeaza(functie, secunde)` pune scrierea pe mai tarziu (implicit eTimer);
	cand intoarce None, scrierea se face pe loc."""

	def __init__(self, cale=CALE, programeaza=None, monoton=None, ceas=None):
		self.cale = cale
		self._programeaza = programeaza or _programatorEnigma
		self._date = None
		self._murdar = False
		self._cronometru = None
		self.fisier = _S.FisierJson(cale, MAX_OCTETI, VERSIUNE, jurnal=_jurnal, monoton=monoton, ceas=ceas)

	def _citeste(self):
		"""-> {cheie: cod}; gol si la o citire nereusita (starea ei ramane in self.fisier)."""
		date = {}
		obiect = self.fisier.citeste()
		if obiect is None:
			return date
		canale = obiect.get("c")
		if not isinstance(canale, dict):
			self.fisier.stricat("\"c\" nu e un obiect")
			return date
		for k, v in canale.items():
			if isinstance(k, str) and 0 < len(k) <= 40 and v in _STARE:
				date[k] = v
		while len(date) > MAX_CANALE:
			del date[next(iter(date))]
		return date

	def _reciteste(self):
		"""O citire noua; numai daca reuseste, ce s-a aflat in memorie se uneste peste fisier."""
		disc = self._citeste()
		if self.fisier.stare == _S.CITIT:
			self._date = _S.uneste_peste(disc, self._date or {}, MAX_CANALE)

	def _toate(self):
		if self._date is None:
			self._date = self._citeste()
		elif self.fisier.la_timp():
			self._reciteste()
		return self._date

	def stare(self, cheie_canal):
		"""„fta”, „criptat” sau None (nu se stie)."""
		if not cheie_canal:
			return None
		return _STARE.get(self._toate().get(cheie_canal))

	def numar(self):
		return len(self._toate())

	def toate(self):
		"""{cheie: "fta" | "criptat"}, o copie (pentru migrarea in baza unica)."""
		return dict((k, _STARE[v]) for k, v in self._toate().items())

	def noteaza(self, cheie_canal, stare):
		"""Tine minte starea aflata acum. -> True daca s-a schimbat ceva."""
		if not cheie_canal or stare not in _COD:
			return False
		date = self._toate()
		cod = _COD[stare]
		if date.get(cheie_canal) == cod:
			return False
		date.pop(cheie_canal, None)
		date[cheie_canal] = cod           # la sfarsit: cele mai vechi pleaca primele cand lista e plina
		while len(date) > MAX_CANALE:
			del date[next(iter(date))]
		self._murdar = True
		self._programeazaScrierea()
		return True

	def _programeazaScrierea(self):
		if self._cronometru is not None:
			return
		try:
			self._cronometru = self._programeaza(self._laTimp, INTARZIERE_S)
		except Exception as eroare:
			_jurnal("nu pot programa scrierea: %s" % eroare)
			self._cronometru = None
		if self._cronometru is None:
			self.salveaza()

	def _laTimp(self):
		self._cronometru = None
		self.salveaza()

	def salveaza(self):
		"""Scrie fisierul, atomic, daca s-a schimbat ceva. -> True daca a scris."""
		if not self._murdar:
			return False
		if not self.fisier.poate_scrie(self._reciteste):
			return False
		text = json.dumps({"v": VERSIUNE, "c": self._toate()}, separators=(",", ":"), sort_keys=False)
		temporar = self.cale + ".nou"
		try:
			dosar = os.path.dirname(self.cale)
			if dosar and not os.path.isdir(dosar):
				os.makedirs(dosar)
			with open(temporar, "wb") as f:
				f.write(text.encode("utf-8"))
				f.flush()
				os.fsync(f.fileno())
			os.replace(temporar, self.cale)
			self.fisier.scris()
		except (IOError, OSError) as eroare:
			_jurnal("nu pot scrie %s: %s" % (self.cale, eroare))
			try:
				os.remove(temporar)
			except OSError:
				pass
			return False
		self._murdar = False
		return True


def _stare_din_rand(rec):
	ca = rec.get("ca") if rec else None
	if isinstance(ca, list) and ca and ca[0] in (0, 1) and not isinstance(ca[0], bool):
		return CRIPTAT if ca[0] == 1 else FTA
	return None


# cat merge culegerea unita (Components/HdsCulegereCanale.py), accesul il noteaza numai ea, dupa PMT; notarea din
# afisaj ar lua drept verificat si un CAID venit din lamedb inaintea PMT-ului
_NOTARE = {"din_afisaj": True}


def lasa_notarea_culegerii():
	"""Chemata de culegerea unita la pornire: de acum accesul se noteaza numai de ea."""
	_NOTARE["din_afisaj"] = False


class MemorieBaza(object):
	"""Adaptorul memoriei peste baza unica (Components/HdsBazaCanale.py, grupa ca), cu aceleasi metode ca Memorie:
	starea se citeste din baza, randul desfacut numai la cerere; noteaza scrie grupa ca numai cand culegerea unita nu
	merge. Scrierea pe disc e a bazei (pragul, standby, oprirea)."""

	def __init__(self, B, b=None):
		self._B = B
		self._b = b
		self._vedere = None

	def _baza(self):
		if self._b is None:
			self._b = self._B.baza()
		return self._b

	def _privire(self):
		if self._vedere is None:
			self._vedere = self._B.Vedere(self._baza(), _stare_din_rand, ("ca",), ("ca",))
		return self._vedere

	def stare(self, cheie_canal):
		"""„fta”, „criptat” sau None (nu se stie)."""
		if not cheie_canal:
			return None
		return self._privire().get(cheie_canal)

	def numar(self):
		return len(self._privire())

	def toate(self):
		return dict(self._privire().items())

	def noteaza(self, cheie_canal, stare):
		"""-> True daca baza s-a schimbat. Nimic cat culegerea unita merge (ea noteaza accesul dupa PMT)."""
		if not cheie_canal or stare not in _COD or not _NOTARE["din_afisaj"]:
			return False
		return self._baza().actualizeaza(cheie_canal, {"ca": [1 if stare == CRIPTAT else 0, []]}, "v")

	def salveaza(self):
		return self._baza().salveaza(self._B.PRAG)


_MEMORIE = []


def memorie():
	"""Memoria procesului: adaptorul peste baza unica; memoria veche (fisierul de dinainte) numai daca baza unica nu
	se incarca."""
	if not _MEMORIE:
		try:
			try:
				from Components import HdsBazaCanale as B
			except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
				import HdsBazaCanale as B
			_MEMORIE.append(MemorieBaza(B))
		except Exception as e:
			_jurnal("baza unica: %s; memoria de dinainte" % e)
			_MEMORIE.append(Memorie())
	return _MEMORIE[0]


def acces(ref_text, acum):
	"""Starea de aratat pentru canalul `ref_text`: `acum` („fta”/„criptat”, aflata din PMT), tinuta minte pe loc; iar
	cand `acum` e None (analiza n-a venit inca), starea tinuta minte sau None (nimic pe ecran)."""
	k = cheie(ref_text)
	m = memorie()
	if acum in STARI:
		if k:
			m.noteaza(k, acum)
		return acum
	return m.stare(k) if k else None

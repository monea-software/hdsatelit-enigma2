# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnaleSloturi.py: „Jurnalele celorlalte sloturi”, fara ecran. Il folosesc ecranul de pe receptor
# (Screens/HdsJurnaleSloturi.py) si pagina web /jurnale-sloturi (Plugins/Extensions/HdsWebControl/sloturi_web.py), deci
# amandoua vad acelasi lucru si fac acelasi lucru.
#
# Cand o imagine dintr-un alt slot nu porneste, pasii pornirilor ei, rapoartele porniri ratate si jurnalele de cadere
# raman in slotul ei. Aici: o singura lucrare odata, pe un fir, prin programul tools/hds-raport.sh (acelasi care scrie si
# trimite raportul pornirii ratate, independent de enigma2):
#   cauta()  sloturile gasite (hds-raport.sh sloturi cauta: dosarele multiboot linuxrootfsN, alte radacini pe discuri si pe
#            memoria interna, montate numai pentru citire);
#   pune()   un singur raport cu tot ce au lasat sloturile, pus pe stick si trimis (hds-raport.sh sloturi pune): o
#            singura apasare, fara alegeri; fara retea raportul ramane in receptor si pleaca singur la pornirea urmatoare.
# stare() spune ce se intampla si rezultatul, cu textele gata de aratat. Fisierul nu importa nimic din enigma2 la
# incarcare: probele de pe PC dau programul lor (PROGRAM).

import os
import subprocess
import threading
import time

PROGRAM = "/usr/bin/hds-raport.sh"
TERMEN_CAUTA_S = 120
TERMEN_PUNE_S = 300


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


TITLU = N_("Jurnalele celorlalte sloturi")
DESCRIERE = N_("Dacă o imagine dintr-un alt slot nu pornește, aici iei pașii pornirilor ei, rapoartele și jurnalele "
	"de cădere rămase acolo. O apăsare le pune pe stick și le trimite, ca să aflăm de ce nu pornește.")
BUTON = N_("Pune pe stick și trimite")
CAUT = N_("Caut celelalte sloturi...")
NICIUN_SLOT = N_("Nu am găsit alte sloturi pe acest receptor.")
RAND_SLOT = N_("%(nume)s, %(imagine)s: porniri %(porniri)d, rapoarte %(rapoarte)d, jurnale de cădere %(caderi)d")
LUCREZ = N_("Pun jurnalele pe stick și le trimit...")
PE_STICK = N_("Pus pe stick, în dosarul hds-raport.")
FARA_STICK = N_("Nu e niciun stick pus: raportul a rămas în receptor.")
TRIMIS = N_("Trimis. Codul raportului: %s.")
NETRIMIS = N_("Nu am putut trimite acum: raportul pleacă singur la pornirea următoare, când receptorul are rețea.")
EROARE = N_("Nu am putut face raportul.")
LIPSA_PROGRAM = N_("Lipsește programul raportului din această imagine.")
ETICHETA_SLOTURI = N_("Ce am găsit în celelalte sloturi")
ETICHETA_COD = N_("Codul raportului")


class Lucrare(object):
	"""O singura lucrare odata (cautare sau punere), pe un fir; starea se citeste oricand."""

	def __init__(self, program=None, ruleaza=None):
		self.program = program or PROGRAM
		self.ruleaza = ruleaza or self._ruleaza
		self.zavor = threading.Lock()
		self.fel = ""           # cauta / pune: lucrarea in curs sau ultima
		self.merge = False
		self.sloturi = None     # lista de dictionare, dupa ultima cautare
		self.rezultat = None    # dictionarul ultimei puneri (fisier, stick, cod, motiv)
		self.cand = 0

	def _ruleaza(self, argumente, termen):
		p = subprocess.run(["/bin/sh", self.program] + argumente, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
			timeout=termen)
		return p.stdout.decode("utf-8", "replace")

	def porneste(self, fel):
		"""Porneste cautarea sau punerea; False daca alta lucrare merge acum."""
		with self.zavor:
			if self.merge:
				return False
			self.merge = True
			self.fel = fel
		threading.Thread(target=self._fir, args=(fel,), name="hds-jurnale-sloturi", daemon=True).start()
		return True

	def _fir(self, fel):
		try:
			if not os.path.isfile(self.program):
				iesire = None
			elif fel == "cauta":
				iesire = self.ruleaza(["sloturi", "cauta"], TERMEN_CAUTA_S)
			else:
				iesire = self.ruleaza(["sloturi", "pune"], TERMEN_PUNE_S)
		except Exception:
			iesire = ""
		with self.zavor:
			if fel == "cauta":
				self.sloturi = citesteSloturi(iesire)
			else:
				self.rezultat = citesteRezultat(iesire)
				# dupa punere, lista ramane cea de dinainte (sloturile nu se schimba)
			self.cand = time.time()
			self.merge = False

	def stare(self):
		with self.zavor:
			return {"fel": self.fel, "merge": self.merge, "sloturi": self.sloturi, "rezultat": self.rezultat}


def citesteSloturi(iesire):
	"""Randurile „slot|nume|imagine|porniri|rapoarte|caderi” -> lista; None cand programul lipseste."""
	if iesire is None:
		return None
	lista = []
	for rand in iesire.splitlines():
		parti = rand.split("|")
		if len(parti) != 6 or parti[0] != "slot":
			continue
		try:
			numere = [int(x) for x in parti[3:]]
		except ValueError:
			continue
		nume = parti[1].rstrip("/")
		lista.append({"nume": os.path.basename(nume) or nume, "cale": nume, "imagine": parti[2].strip() or "?",
			"porniri": numere[0], "rapoarte": numere[1], "caderi": numere[2]})
	return lista


def citesteRezultat(iesire):
	"""Randurile cheie=valoare ale lui „sloturi pune” -> dictionar; {"motiv": "program"} cand programul lipseste."""
	if iesire is None:
		return {"motiv": "program"}
	d = {}
	for rand in iesire.splitlines():
		k, semn, v = rand.partition("=")
		if semn and k in ("fisier", "stick", "cod", "motiv") and k not in d:
			d[k] = v.strip()
	return d


def textSloturi(sloturi):
	"""Textul listei, gata de aratat."""
	if sloturi is None:
		return _(LIPSA_PROGRAM)
	if not sloturi:
		return _(NICIUN_SLOT)
	return "\n".join(_(RAND_SLOT) % s for s in sloturi)


def textRezultat(r):
	"""Textul rezultatului punerii: unde e raportul si daca a plecat."""
	if not r:
		return ""
	motiv = r.get("motiv", "")
	if motiv == "program":
		return _(LIPSA_PROGRAM)
	if motiv == "fara-sloturi":
		return _(NICIUN_SLOT)
	if not r.get("fisier"):
		return _(EROARE)
	randuri = [_(PE_STICK) if r.get("stick", "nu") not in ("", "nu") else _(FARA_STICK)]
	cod = r.get("cod", "nu")
	randuri.append(_(TRIMIS) % cod if cod.isdigit() else _(NETRIMIS))
	return "\n".join(randuri)


def codRezultat(r):
	"""Codul raportului trimis (6 cifre), sau "" cand nu a plecat."""
	cod = (r or {}).get("cod", "")
	return cod if cod.isdigit() else ""


_unic = [None]


def lucrare():
	if _unic[0] is None:
		_unic[0] = Lucrare()
	return _unic[0]

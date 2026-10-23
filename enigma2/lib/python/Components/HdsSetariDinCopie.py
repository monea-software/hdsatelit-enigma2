# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSetariDinCopie.py: setarile puse la loc cat enigma2 ruleaza (importul, mai tarziu ecranele de copie).
#
# Ele nu se scriu in /etc/enigma2/settings: la iesirea curata configfile.save() (mytest.py) scrie peste fisier arborele
# din memorie, deci o valoare pusa acolo se pierde la repornirea interfetei. Se scriu in settings.din-copie, numai
# cheile puse la loc, cate un rand „config.<nume>=valoare”. tools/enigma2.sh.in le uneste peste settings inainte de
# urmatoarea pornire a lui enigma2 (cheile din fisier castiga, celelalte raman), pastreaza settings de dinainte ca
# settings.inainte-de-copie si scrie semnul garzii (.hds-setari-din-copie, secundele din /proc/uptime).
# Garda (tot in enigma2.sh): 2 opriri neasteptate ale interfetei in 10 minute de la unire pun la loc settings de
# dinainte (sau niciunul: nu existau setari inainte de unire) si muta setarile unite in settings.din-copie-cazut, care
# ramane pana la o garda urmatoare; dupa 30 de minute fara asa ceva semnul si instantaneul se sterg (instantaneul are
# si jetonul web). O repornire a receptorului inchide fereastra (semnul are pe randul 2 id-ul pornirii). Unirea nu
# inlocuieste settings daca un pas nu se poate verifica (disc plin): fisierul in asteptare ramane pentru pornirea
# urmatoare.
# Aceleasi reguli pentru chei ca in enigma2.sh: numele potrivit cu TIPAR_CHEIE, niciodata jetonul interfetei web
# (e al receptorului, nu al copiei), valoarea fara sfarsit de rand. Fisierul nu importa nimic din enigma2.

import os
import re

DOSAR = "/etc/enigma2"
CALE = DOSAR + "/settings.din-copie"
CALE_CAZUT = DOSAR + "/settings.din-copie-cazut"
CALE_SEMN = DOSAR + "/.hds-setari-din-copie"
CHEIE_JETON = "config.plugins.hdswebcontrol.token"
TIPAR_CHEIE = re.compile(r"^config\.[A-Za-z0-9_.-]+$")
# aceeasi limita ca in enigma2.sh: un fisier mai mare se sterge acolo, fara unire
MARIME_MAXIMA = 1024 * 1024
# fereastra garzii, in secunde de la unire: aceeasi valoare ca HDS_SETARI_FEREASTRA din enigma2.sh
FEREASTRA = 1800


def cheieBuna(cheie):
	return bool(TIPAR_CHEIE.match(cheie or "")) and cheie != CHEIE_JETON


def _valoare(v):
	v = "" if v is None else str(v)
	return v.split("\n", 1)[0].split("\r", 1)[0].strip()


def _citesteStrict(cale):
	"""({cheie: valoare}, None); ({}, None) daca fisierul lipseste; (None, eroare) la orice alta eroare de citire,
	ca un fisier necitit sa nu fie scris peste."""
	chei = {}
	try:
		with open(cale, "r", encoding="utf-8", errors="surrogateescape") as f:
			for rand in f:
				cheie, egal, valoare = rand.rstrip("\r\n").partition("=")
				if egal and cheieBuna(cheie):
					chei[cheie] = valoare
	except FileNotFoundError:
		return {}, None
	except OSError as eroare:
		return None, eroare.strerror or str(eroare)
	return chei, None


def citeste(cale=None):
	"""{cheie: valoare} din fisierul in asteptare (ordinea din fisier); {} daca lipseste sau nu se poate citi."""
	chei, _eroare = _citesteStrict(cale or CALE)
	return chei or {}


def scrie(chei, cale=None):
	"""Adauga cheile la cele deja in asteptare (cele noi castiga) si scrie atomic (.nou, fsync, os.replace).
	Intoarce (numarul cheilor in asteptare, eroare sau None). Cheile rele si jetonul web nu intra; daca nu ramane
	nicio cheie buna, nu se scrie nimic."""
	cale = cale or CALE
	noi = {}
	for cheie, valoare in (chei or {}).items():
		cheie = (cheie or "").strip()
		if cheieBuna(cheie):
			noi[cheie] = _valoare(valoare)
	toate, eroare = _citesteStrict(cale)
	if toate is None:
		return 0, eroare
	if not noi:
		return len(toate), None
	toate.update(noi)
	text = "".join("%s=%s\n" % (k, v) for k, v in toate.items())
	try:
		date = text.encode("utf-8", "surrogateescape")
	except UnicodeEncodeError:
		date = text.encode("utf-8", "replace")
	if len(date) > MARIME_MAXIMA:
		return len(citeste(cale)), "prea multe setari (%d octeti)" % len(date)
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except OSError as eroare:
		try:
			os.remove(nou)
		except OSError:
			pass
		return len(citeste(cale)), eroare.strerror or str(eroare)
	return len(toate), None


def _uptime():
	"""Secundele de la pornirea receptorului (acelasi ceas ca enigma2.sh); None daca /proc/uptime nu se poate citi."""
	try:
		with open("/proc/uptime", "r") as f:
			return int(float(f.read().split()[0]))
	except (OSError, ValueError, IndexError):
		return None


def _gardaPornita(cale_semn, acum=None):
	"""Garda lucreaza numai in fereastra: semnul are numarul unirii si au trecut mai putin de FEREASTRA secunde de
	atunci. enigma2.sh inchide fereastra numai la o pornire sau o iesire a lui enigma2, deci un semn ramas dupa 30 de
	minute nu mai inseamna „in proba”. Fara ceas (probele de pe PC): semnul cu numar ajunge."""
	try:
		with open(cale_semn, "r") as f:
			rand = f.readline()
	except OSError:
		return False
	cifre = "".join(c for c in rand if c.isdigit())[:12].lstrip("0")
	if not cifre:
		return False
	if acum is None:
		acum = _uptime()
	if acum is None:
		return True
	return acum - int(cifre) < FEREASTRA


def stare(cale=None, cale_cazut=None, cale_semn=None, acum=None):
	"""Pentru ecranul importului si pentru interfata web: cheile in asteptare, garda pornita (unire in ultimele 30 de
	minute) si setarile scoase de garda. acum: secundele de la pornire (numai pentru probe)."""
	return {
		"asteapta": len(citeste(cale)),
		"garda": _gardaPornita(cale_semn or CALE_SEMN, acum),
		"cazut": os.path.exists(cale_cazut or CALE_CAZUT),
	}


def texteStare(st=None):
	"""Randurile de afisat pe televizor si in web (traduse pe receptor)."""
	st = stare() if st is None else st
	randuri = []
	if st.get("asteapta"):
		randuri.append(_t("Setări importate care așteaptă repornirea interfeței: %d.") % st["asteapta"])
	if st.get("garda"):
		randuri.append(_t("Setările importate sunt în probă: dacă interfața se oprește neașteptat de două ori în 10 "
			"minute, se pun la loc cele de dinainte."))
	if st.get("cazut"):
		randuri.append(_t("Setările importate data trecută au fost scoase după opriri neașteptate ale interfeței "
			"(păstrate în settings.din-copie-cazut)."))
	return randuri


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCuratenie.py: curatenia discului (Meniu > Setari > Sistem & Dispozitive > Cleanup & Reset Wizard), aceeasi pentru
# ecranul de pe televizor (Screens/CleanupWizard.py) si pentru pagina web /curatenie (HdsWebControl/resetare_web.py).
# Codul e cel al ecranului, mutat aici fara schimbari; ecranul il foloseste, deci se poarta la fel.
#
# Numai doua categorii, strict regenerabile: fisierele temporare din /tmp si pachetele descarcate de opkg
# (/var/cache/opkg). Niciodata setari, canale, inregistrari sau programari (resetarea completa e separata,
# Components/HdsResetareFabrica.py). In /tmp pot fi obiecte vii cat merge sistemul: socket-urile si FIFO-urile (de
# exemplu /tmp/mmi.socket, dialogul cu modulul din fanta CI, Components/Ci.py) si steagul hds-pornire-stick.ruleaza
# (porneste.sh, proba prin stick); ePastrat() le lasa pe loc.
#
# Marimile si golirea citesc tot dosarul: pe receptor pagina web le face pe un fir (meniu_comun_web.peFir).
# Fisierul nu importa nimic din enigma2 la incarcare; textele se traduc la folosire (N_ le marcheaza pentru xgettext).

import os
import stat

NUME_EXCLUSE_TMP = frozenset((
	"hds-pornire-stick.ruleaza",
))


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# (cheie, eticheta netradusa, dosarul, numele pastrate)
CATEGORII = (
	("tmp", N_("Fișiere temporare"), "/tmp", NUME_EXCLUSE_TMP),
	("opkg_cache", N_("Cache pachete descărcate (opkg)"), "/var/cache/opkg", frozenset()),
)


def categorii():
	"""CATEGORII cu etichetele traduse: [(cheie, eticheta, dosarul, numele pastrate)]."""
	return [(cheie, _t(eticheta), cale, excluse) for cheie, eticheta, cale, excluse in CATEGORII]


def categorie(cheie):
	"""(cheie, eticheta tradusa, dosarul, numele pastrate) sau None pentru o cheie necunoscuta."""
	for c in categorii():
		if c[0] == cheie:
			return c
	return None


def marimeFolder(cale):
	"""Suma octetilor tuturor fisierelor din `cale` (recursiv). Erorile de acces (fisiere in curs de scriere sau fara
	drept de citire) se sar, una cate una."""
	total = 0
	try:
		for radacina, _dirs, fisiere in os.walk(cale):
			for nume in fisiere:
				try:
					total += os.path.getsize(os.path.join(radacina, nume))
				except OSError:
					pass
	except OSError:
		pass
	return total


def ePastrat(cale_fisier, nume_excluse):
	"""True pentru ce nu se sterge cat merge sistemul: un nume din `nume_excluse` (steagul probei prin stick), un
	socket sau un FIFO (un proces care il tine deschis ar ramane cu legatura rupta)."""
	nume = os.path.basename(cale_fisier)
	if nume in nume_excluse:
		return True
	try:
		mod = os.stat(cale_fisier).st_mode
	except OSError:
		return False  # deja disparut sau inaccesibil: os.remove de mai jos cade oricum curat
	return stat.S_ISSOCK(mod) or stat.S_ISFIFO(mod)


def curataFolder(cale, nume_excluse=frozenset()):
	"""Sterge CONTINUTUL lui `cale` (fisierele si subdosarele golite); pastreaza dosarul insusi si tot ce pastreaza
	ePastrat(). Fiecare eroare (fisier folosit, drept lipsa) se sare, restul continua. Intoarce (fisiere_sterse,
	octeti_eliberati)."""
	sterse = 0
	eliberati = 0
	try:
		for radacina, dirs, fisiere in os.walk(cale, topdown=False):
			for nume in fisiere:
				fp = os.path.join(radacina, nume)
				if ePastrat(fp, nume_excluse):
					continue
				try:
					marime = os.path.getsize(fp)
					os.remove(fp)
					sterse += 1
					eliberati += marime
				except OSError:
					pass
			for nume in dirs:
				dp = os.path.join(radacina, nume)
				try:
					os.rmdir(dp)  # numai daca a ramas gol: un dosar cu un fisier pastrat inauntru ramane
				except OSError:
					pass
	except OSError:
		pass
	return sterse, eliberati


def formatMB(octeti):
	return "%.1f MB" % (octeti / (1024.0 * 1024.0))


def marimi():
	"""Pentru pagina web: [{cheie, eticheta, cale, exista, octeti, marime}], ca randurile ecranului."""
	rez = []
	for cheie, eticheta, cale, _excluse in categorii():
		exista = os.path.isdir(cale)
		octeti = marimeFolder(cale) if exista else 0
		rez.append({"cheie": cheie, "eticheta": eticheta, "cale": cale, "exista": exista, "octeti": octeti,
			"marime": formatMB(octeti)})
	return rez


def goleste(cheie):
	"""Ca Da in intrebarea ecranului: (exista, fisiere_sterse, octeti_eliberati); KeyError pentru o cheie necunoscuta."""
	c = categorie(cheie)
	if c is None:
		raise KeyError(cheie)
	_cheie, _eticheta, cale, excluse = c
	if not os.path.isdir(cale):
		return False, 0, 0
	sterse, eliberati = curataFolder(cale, excluse)
	return True, sterse, eliberati

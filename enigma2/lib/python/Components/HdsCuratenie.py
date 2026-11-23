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
import re
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


# 0.7.9 (BLD8, 23.11.2026; coordonatorul 14:20): opkg pastreaza in /var/cache/opkg pachetele descarcate dintr-un feed
# (opkg.conf n-are nicio optiune de cache), iar /var/cache e tmpfs, adica RAM, pe toate receptoarele: pe ZGEMMA H8.2H Plus
# (~335 MB vazuti de Linux) enigma2-hdsatelit de 37 MB a stat acolo pana la repornire. Dupa orice instalare, actualizare sau
# scoatere reala (nu --download-only si nu --noaction, unde pachetele descarcate se citesc dupa aceea) se sterg pachetele de
# acolo; numai cand niciun opkg nu mai ruleaza (o instalare cu mai multe pachete le deschide pe rand). Listele feedurilor
# (*_Packages.gz) si orice alt fisier raman. Fara nimic pentru om: nicio fereastra, niciun text nou.
DOSAR_CACHE_OPKG = "/var/cache/opkg"


def opkgRuleaza(proc="/proc"):
	"""True cand ruleaza un proces opkg (comm = opkg), altul decat acesta"""
	eu = str(os.getpid())
	try:
		intrari = os.listdir(proc)
	except OSError:
		return False
	for p in intrari:
		if not p.isdigit() or p == eu:
			continue
		try:
			with open(os.path.join(proc, p, "comm"), "rb") as f:
				if f.read().strip() == b"opkg":
					return True
		except OSError:
			pass
	return False


def schimbaPachete(argumente):
	"""True cand argumentele opkg (fara program) instaleaza, actualizeaza sau scot de-a binelea"""
	argumente = [a for a in (argumente or ()) if isinstance(a, str)]
	if argumente and argumente[0].endswith("opkg"):
		argumente = argumente[1:]
	comenzi = [a for a in argumente if not a.startswith("-")]
	return bool(comenzi) and comenzi[0] in ("install", "upgrade", "remove") and not any(
		a in argumente for a in ("--download-only", "--noaction"))


def ePachetInCache(nume):
	"""True pentru un pachet descarcat de opkg (<suma>_<pachet>.ipk); opkg taie numele lungi, deci si fara .ipk la coada
	(de pilda ..._streamlink_..._cortexa15hf-n). Listele feedurilor (<suma>_Packages.gz si semnaturile) raman."""
	return not re.search(r"_Packages(\.gz|\.sig|\.asc)?$", nume)


def golesteCacheOpkg(dosar=DOSAR_CACHE_OPKG, proc="/proc"):
	"""Sterge pachetele din cache-ul opkg dupa o instalare: (fisiere_sterse, octeti_eliberati); (0, 0) cat ruleaza un opkg"""
	try:
		nume = [n for n in os.listdir(dosar) if ePachetInCache(n) and os.path.isfile(os.path.join(dosar, n))]
	except OSError:
		return 0, 0
	if not nume or opkgRuleaza(proc):
		return 0, 0
	sterse = 0
	eliberati = 0
	for n in nume:
		cale = os.path.join(dosar, n)
		try:
			marime = os.path.getsize(cale)
			os.remove(cale)
			sterse += 1
			eliberati += marime
		except OSError:
			pass
	if sterse:
		print("[HdsCuratenie] cache-ul opkg: %d pachete sterse, %s" % (sterse, formatMB(eliberati)))
	return sterse, eliberati


def golesteCacheOpkgDupa(argumente):
	"""golesteCacheOpkg() numai dupa o comanda opkg care schimba pachete (schimbaPachete); orice eroare se inghite"""
	try:
		if schimbaPachete(argumente):
			return golesteCacheOpkg()
	except Exception as e:
		print("[HdsCuratenie] cache-ul opkg: %s" % e)
	return 0, 0


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

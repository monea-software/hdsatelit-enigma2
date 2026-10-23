# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsResetareFabrica.py: revenirea la setarile din fabrica (Meniu > Setari > Sistem & Dispozitive > Reset to Factory
# Defaults), aceeasi pentru televizor (codul intrarii factory_reset din data/menu.xml, dupa Da in
# Screens/FactoryReset.py) si pentru pagina web /resetare-fabrica (HdsWebControl/resetare_web.py).
#
# Pasii, in ordinea de dinainte, cand erau scrisi in menu.xml ca comenzi de shell:
#   1. scrierile bazei canalelor se opresc (Components.HdsCulegereCanale.Scrieri.opreste()); o eroare aici nu opreste
#      resetarea;
#   2. /etc/enigma2 se sterge (era rm -R; ce nu se poate sterge ramane, ca la rm);
#   3. /usr/share/enigma2/defaults se copiaza in /etc/enigma2 (era cp -R: legaturile raman legaturi, fisierele isi
#      pastreaza drepturile). Daca /etc/enigma2 n-a disparut de tot, cp -R ar fi pus copia in /etc/enigma2/defaults;
#      aici continutul ei se pune peste ce a ramas, deci rezultatul e acelasi cu al unei stergeri reusite;
#   4. iesirea pe loc, os._exit(0), fara salvarea setarilor din memorie (iesirea curata ar scrie /etc/enigma2/settings
#      la loc); enigma2.sh porneste apoi interfata din nou (codul 0 nu opreste si nu reporneste receptorul).
# Fara shell: os si shutil. Fisierul nu importa nimic din enigma2 la incarcare (probele de pe PC dau dosarele lor).

import os
import shutil

ETC = "/etc/enigma2"
IMPLICITE = "/usr/share/enigma2/defaults"


def _log(text):
	print("[HdsResetareFabrica] %s" % text)


def opresteScrierile():
	"""Pasul 1: scrierile bazei canalelor (HdsCulegereCanale) se opresc; o eroare se scrie in jurnal si atat."""
	try:
		from Components.HdsCulegereCanale import Scrieri
		Scrieri.opreste()
	except Exception as e:
		_log("baza canalelor: %s" % e)


def sterge(cale):
	"""Pasul 2, ca rm -R: dosarul cu tot ce e in el; o legatura sau un fisier se sterge singur; erorile nu opresc nimic."""
	if os.path.islink(cale) or os.path.isfile(cale):
		try:
			os.remove(cale)
		except OSError as e:
			_log("stergerea %s: %s" % (cale, e))
		return
	shutil.rmtree(cale, ignore_errors=True)


def _legatura(sursa, tinta):
	if os.path.lexists(tinta) and not os.path.isdir(tinta):
		os.remove(tinta)
	os.symlink(os.readlink(sursa), tinta)


def copiaza(sursa, tinta):
	"""Pasul 3, ca cp -R: dosarele, fisierele (continutul si drepturile) si legaturile (ca legaturi). False cand
	`sursa` nu e un dosar (atunci nu se copiaza nimic, ca la cp)."""
	if not os.path.isdir(sursa):
		_log("%s lipseste: nu se copiaza nimic" % sursa)
		return False
	for radacina, dosare, fisiere in os.walk(sursa):
		rel = os.path.relpath(radacina, sursa)
		dest = tinta if rel == os.curdir else os.path.join(tinta, rel)
		if not os.path.isdir(dest):
			try:
				os.makedirs(dest)
			except OSError as e:
				_log("dosarul %s: %s" % (dest, e))
				continue
		for nume in dosare + fisiere:
			s = os.path.join(radacina, nume)
			d = os.path.join(dest, nume)
			try:
				if os.path.islink(s):
					_legatura(s, d)
				elif os.path.isfile(s):
					shutil.copyfile(s, d)
					shutil.copymode(s, d)
			except (IOError, OSError) as e:
				_log("copia %s: %s" % (s, e))
	return True


def reseteaza(etc=None, implicite=None, iesire=None, scrieri=None):
	"""Toti pasii, in ordine. Implicit: ETC, IMPLICITE, os._exit (primeste 0) si opresteScrierile (pasul 1)."""
	etc = etc or ETC
	(scrieri or opresteScrierile)()
	sterge(etc)
	copiaza(implicite or IMPLICITE, etc)
	(iesire or os._exit)(0)


def implicitele(implicite=None):
	"""True cand dosarul cu valorile din fabrica exista (altfel, dupa resetare, interfata porneste fara setari)."""
	return os.path.isdir(implicite or IMPLICITE)

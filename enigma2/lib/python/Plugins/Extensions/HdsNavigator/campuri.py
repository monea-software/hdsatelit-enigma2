# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# campuri.py: textul scris in interfata web (telefon, calculator) ajunge in campul de text activ de pe televizor.
#
# Unde ajunge, in ordine:
#   1. o fereastra de text a enigma2 deschisa acum (tastatura VirtualKeyBoard, si cea cu parola a navigatorului;
#      caseta InputBox): textul ii inlocuieste continutul, omul confirma cu OK ca de obicei;
#   2. un ecran de setari cu o setare de text selectata (ConfigText): valoarea ei, fara salvare;
#   3. navigatorul web, cand e pe ecran si are un camp cu focalizare: textul intra la cursor;
#   4. altfel nimic, cu motivul.
# Textul nu se scrie in niciun jurnal; in jurnal ajunge numai lungimea si felul campului.

from . import lansator as L

TEXT_MAXIM = L.TEXT_MAXIM


def _fereastra(sesiune):
	try:
		return sesiune.current_dialog if sesiune is not None else None
	except Exception:
		return None


def _setareText(d):
	"""Setarea de text selectata intr-un ecran ConfigListScreen, sau None."""
	try:
		from Components.config import ConfigText
		lista = d["config"]
		rand = lista.getCurrent()
	except Exception:
		return None
	if rand and len(rand) > 1 and isinstance(rand[1], ConfigText):
		return rand
	return None


def tinta(sesiune):
	"""Unde ar ajunge textul acum: (fel, parola), fel in: tastatura, caseta, setare, navigator, None."""
	d = _fereastra(sesiune)
	try:
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		from Screens.InputBox import InputBox
	except Exception:
		VirtualKeyBoard = InputBox = None
	if d is not None and VirtualKeyBoard is not None and isinstance(d, VirtualKeyBoard):
		return "tastatura", d.__class__.__name__ == "TastaturaParola"
	if d is not None and InputBox is not None and isinstance(d, InputBox):
		return "caseta", False
	if d is not None and _setareText(d) is not None:
		return "setare", False
	n = L.activ()
	if n is not None and n.stare == L.ARATAT and n.camp != "niciunul":
		return "navigator", n.camp == "parola"
	return None, False


def trimite(sesiune, text):
	"""(True, fel) daca textul a ajuns undeva, altfel (False, motiv)."""
	text = (text or "")[:TEXT_MAXIM]
	if not text:
		return False, "gol"
	fel, _parola = tinta(sesiune)
	d = _fereastra(sesiune)
	try:
		if fel == "tastatura":
			d.text = text
			d["text"].setText(text)
		elif fel == "caseta":
			d["input"].setText(text)
		elif fel == "setare":
			rand = _setareText(d)
			rand[1].setValue(text)
			d["config"].invalidateCurrent()
		elif fel == "navigator":
			if not L.activ().textInCamp(text):
				return False, "navigator"
		else:
			return False, "fara-camp"
	except Exception as e:
		print("[HdsNavigator] text trimis: %s" % e.__class__.__name__)
		return False, "eroare"
	print("[HdsNavigator] text trimis: %d semne, spre %s" % (len(text), fel))
	return True, fel

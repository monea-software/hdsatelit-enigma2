# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAspectLista.py (0.7.5): „Aspectul listei de canale” (config.usage.hds_aspect_lista; Setări > Personalizare, langa
# „Rânduri pe pagină” si „Mărimea textului în lista de canale”; in web /setari?id=usage).
#   „Obișnuit” (din fabrica): ecranele de pana acum ale temei (HdsListaCanale, HdsListaCanaleRadio, HdsListaCanaleSimpla).
#   „Lista mare”: aceleasi ecrane cu „Mare” in nume (HdsListaCanaleMare...): pe tot ecranul, lista pe ~2/3 in stanga, imaginea
#   canalului si ghidul in dreapta, tastele colorate in dreapta jos. Daca tema nu are ecranul mare (o tema straina), skin.readSkin
#   trece la urmatorul nume din skinName, deci ramane lista obisnuita a temei.
# Listele radio si cea simpla se fac la fiecare deschidere, deci iau ecranul ales din skinName (ecrane()). Lista TV a barei se face
# o data, la pornire (InfoBarGenerics: InfoBar.servicelist); la schimbarea setarii ecranul ei se reface pe loc, fara repornire si
# fara sa se ruleze iar constructorul (ca rezerva temelor straine din mytest.py, ecranCuRezerva): numai cat lista nu se vede;
# schimbata din web cu lista deschisa pe televizor, se reface la prima inchidere a listei.

PREFIX = "HdsListaCanale"
SUFIX_MARE = "Mare"


def mare():
	try:
		from Components.config import config
		return getattr(getattr(config.usage, "hds_aspect_lista", None), "value", "obisnuit") == "mare"
	except Exception:
		return False


def numeMare(nume):
	"""HdsListaCanale -> HdsListaCanaleMare, HdsListaCanaleRadio -> HdsListaCanaleMareRadio"""
	if not nume.startswith(PREFIX) or nume.startswith(PREFIX + SUFIX_MARE):
		return None
	return PREFIX + SUFIX_MARE + nume[len(PREFIX):]


def ecrane(nume):
	"""skinName pentru o lista a imaginii: [ecranul mare] + nume cu „Lista mare”, altfel nume (o copie)."""
	nume = [n for n in nume if not n.startswith(PREFIX + SUFIX_MARE)]
	if mare():
		mari = [m for m in (numeMare(n) for n in nume) if m]
		# chiar inaintea primului ecran al listei: ce sta inaintea lui (stilul ales al unei teme straine) ramane primul
		i = next((k for k, n in enumerate(nume) if n.startswith(PREFIX)), 0)
		return nume[:i] + mari + nume[i:]
	return nume


def _listaTv():
	try:
		from Screens.InfoBar import InfoBar
		return getattr(InfoBar.instance, "servicelist", None) if InfoBar.instance is not None else None
	except Exception:
		return None


def reface(ecran):
	"""Ecranul (deja facut) primeste asezarea aleasa: skinName nou, tema citita din nou, aceleasi componente si surse.
	-> True daca s-a refacut acum, False daca nu era nevoie sau ramane pentru prima inchidere a listei."""
	if ecran is None or getattr(ecran, "instance", None) is None:
		return False
	dorit = ecrane(list(ecran.skinName) if isinstance(ecran.skinName, (list, tuple)) else [ecran.skinName])
	if list(dorit) == list(ecran.skinName if isinstance(ecran.skinName, (list, tuple)) else [ecran.skinName]):
		return False
	if getattr(ecran, "shown", False):
		# schimbata din web cu lista pe televizor: la prima inchidere
		ecran.hdsAspectAsteapta = True
		if not getattr(ecran, "hdsAspectLegat", False):
			ecran.hdsAspectLegat = True
			ecran.onHide.append(lambda: _dupaInchidere(ecran))
		return False
	from skin import readSkin
	desktop = ecran.desktop
	lista = getattr(ecran, "servicelist", None)
	curent = None
	try:
		curent = lista.getCurrent() if lista is not None and lista.instance is not None else None
	except Exception:
		curent = None
	for r in list(getattr(ecran, "renderer", [])):
		try:
			r.disconnectAll()
		except Exception as e:
			print("[HdsAspectLista] disconnectAll: %s" % e)
		try:
			if getattr(r, "instance", None) is not None:
				r.GUIdelete()
		except Exception as e:
			print("[HdsAspectLista] GUIdelete: %s" % e)
	ecran.deleteGUIScreen()
	ecran.instance = None
	ecran.onLayoutFinish[:] = [f for f in ecran.onLayoutFinish if callable(f)]
	ecran.skinName = dorit
	readSkin(ecran, None, ecran.skinName, desktop)
	ecran.setDesktop(desktop)
	ecran.applySkin()
	# lista noua (eListbox) porneste de la primul rand: cursorul inapoi pe canalul de dinainte
	try:
		if curent is not None and curent.valid() and lista is not None and lista.instance is not None:
			lista.setCurrent(curent)
	except Exception as e:
		print("[HdsAspectLista] cursorul: %s" % e)
	print("[HdsAspectLista] lista de canale refacuta: %s" % ecran.skinName[0])
	return True


def _dupaInchidere(ecran):
	if not getattr(ecran, "hdsAspectAsteapta", False):
		return
	ecran.hdsAspectAsteapta = False
	# dupa ascunderea de acum (onHide ruleaza in timpul hide()): cu un ceas de 0, ca ecranul sa fie deja ascuns
	try:
		from enigma import eTimer
		ceas = eTimer()

		def _acum():
			ecran.hdsAspectCeas = None
			reface(ecran)
		ceas.callback.append(_acum)
		ecran.hdsAspectCeas = ceas
		ceas.start(0, True)
	except Exception as e:
		print("[HdsAspectLista] dupa inchidere: %s" % e)


def laSchimbare(configElement=None):
	"""notifierul setarii (Components/UsageConfig.py): lista TV a barei se reface pe loc (sau la prima inchidere)"""
	try:
		reface(_listaTv())
	except Exception as e:
		import traceback
		print("[HdsAspectLista] refacerea listei: %s" % e)
		traceback.print_exc()

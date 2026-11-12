# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Paza barei canalului (0.7.4, OEA1): omul nu ramane niciodata fara bara din cauza unui plugin.

Unele pluginuri scrise pentru alte imagini schimba clasele barei la incarcare (InfoBarShowHide.__init__ inlocuit cu o functie a
lor, care pune elementul lor pe bara). Daca functia lor cade (de pilda cheama ceva ce imaginea nu are), bara canalului nu se mai
construieste deloc, iar dupa trei incercari interfata se reporneste fara folos.

Ce face: inainte sa se incarce pluginurile (mytest.py), instantaneu() tine minte metodele claselor barei (Screens.InfoBar.InfoBar si
toate clasele din care e facuta, plus clasele InfoBar* din Screens.InfoBarGenerics). Cand construirea barei cade cu un cadru de
plugin in stiva, repara() pune la loc numai ce au schimbat pluginurile (functiile din modulele Plugins.*), scrie in jurnal pluginul
vinovat si ce s-a pus la loc, si intoarce True: Session.open construieste bara inca o data, a noastra, fara elementul pluginului.
O singura data pe pornire; pentru alte ecrane si pentru caderile fara plugin in stiva nu face nimic (merge ca pana acum)."""

_originale = {}		# clasa -> {nume: valoarea de dinainte de pluginuri}
_reparat = []


def _clase():
	import Screens.InfoBar
	import Screens.InfoBarGenerics
	clase = []
	for c in Screens.InfoBar.InfoBar.__mro__:
		if c is not object:
			clase.append(c)
	for nume in dir(Screens.InfoBarGenerics):
		c = getattr(Screens.InfoBarGenerics, nume)
		if isinstance(c, type) and nume.startswith("InfoBar") and c not in clase:
			clase.append(c)
	return clase


def instantaneu():
	"""metodele claselor barei, inainte de pluginuri; o eroare aici lasa paza oprita (pornirea nu depinde de ea)"""
	try:
		for c in _clase():
			_originale[c] = dict(vars(c))
	except Exception as e:
		print("[HdsPazaBara] instantaneu:", e)


def _dinPlugin(v):
	f = getattr(v, "__func__", v)
	return (getattr(f, "__module__", None) or "").startswith("Plugins.")


def schimbate():
	"""[(clasa, nume, este_noua)] pentru ce au pus pluginurile peste clasele barei"""
	rez = []
	for c, vechi in _originale.items():
		for nume, v in list(vars(c).items()):
			if nume in vechi and vechi[nume] is v:
				continue
			if _dinPlugin(v):
				rez.append((c, nume, nume not in vechi))
	return rez


def repara(screen, error):
	"""True cand bara a cazut dintr-un plugin si s-au pus la loc metodele schimbate de pluginuri (bara se poate construi iar)"""
	try:
		import Screens.InfoBar
		if screen is not Screens.InfoBar.InfoBar or _reparat or not _originale:
			return False
		from Components import HdsPluginExtern
		vinovat = HdsPluginExtern._pluginSiCadru(getattr(error, "__traceback__", None))
		if vinovat is None:
			return False
		puse = []
		for c, nume, noua in schimbate():
			if noua:
				delattr(c, nume)
			else:
				setattr(c, nume, _originale[c][nume])
			puse.append("%s.%s" % (c.__name__, nume))
		_reparat.append(vinovat)
		if not puse:
			print("[HDS-SAFE] bara canalului a cazut din pluginul %s/%s, dar pluginul n-a schimbat clasele barei" % (vinovat[0], vinovat[1]))
			return False
		print("[HDS-SAFE] bara canalului a cazut din pluginul %s/%s (%s, randul %s): %s; se construieste bara fara schimbarile "
			"pluginurilor (puse la loc: %s)" % (vinovat[0], vinovat[1], vinovat[2], vinovat[3], error, ", ".join(puse) or "nimic"))
		return True
	except Exception as e:
		print("[HdsPazaBara] repara:", e)
		return False

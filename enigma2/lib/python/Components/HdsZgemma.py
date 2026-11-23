# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Tastele H8 din fotografiile proprietarului si codurile logice Linux.

Nu sunt coduri brute IR masurate. Evenimentele din fabrica se verifica
pe cele doua aparate inainte de validarea pe hardware.
"""

MODELE = ("zgemmah8se", "zgemmah82hplus")

try:
	_
except NameError:
	def _(text):
		return text

def disponibil(model):
	return model in MODELE

def taste(model):
	if not disponibil(model):
		return ()
	return ((_("VMODE"), 227), (_("PORTAL"), 150), (_("FILE LIST"), 393),
		(_("SLEEP"), 142), (_("TIMER"), 359), (_("HELP"), 138), (_("FAV"), 364))

def modelAcum():
	try:
		from Components.About import about
		return about.valoareDinReguli("machinebuild") or ""
	except (ImportError, AttributeError):
		return ""

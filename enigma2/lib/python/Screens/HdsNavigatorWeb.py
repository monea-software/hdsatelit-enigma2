# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsNavigatorWeb.py: intrarea „Navigator web” din meniu (data/menu.xml cere ecranele din Screens.<modul>). Ecranul
# adevarat e in pluginul Plugins/Extensions/HdsNavigator; aici numai numele pentru meniu si pentru „Deschide pe
# televizor” din interfata web (meniu_web.py), fara nimic incarcat pana la deschidere.

from Plugins.Extensions.HdsNavigator.ecrane import HdsNavigatorEcran, HdsNavigatorSetari


class HdsNavigatorWeb(HdsNavigatorEcran):
	"""Navigatorul obisnuit, cu pagina de pornire din setari."""

	def __init__(self, session, *argumente):
		HdsNavigatorEcran.__init__(self, session)
		self.skinName = "HdsNavigatorEcran"


class HdsNavigatorWebSetari(HdsNavigatorSetari):
	"""Setarile navigatorului, direct din meniu."""

	def __init__(self, session, *argumente):
		HdsNavigatorSetari.__init__(self, session)
		self.skinName = "HdsNavigatorSetari"

	def close(self, *rezultat):
		"""Din meniu ecranul se inchide fara rezultat: True (salvat) ar inchide toate meniurile (Screens/Menu.py,
		menuClosed). Navigatorul deschis, care primeste True, foloseste ecranul de baza."""
		HdsNavigatorSetari.close(self)

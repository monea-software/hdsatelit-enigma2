# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsNavigator: navigatorul web pe televizor (WPE WebKit, pachetul hds-navigator, care vine cu imaginea).
#
# Fisierul acesta se importa la pornirea receptorului, ca toate pluginurile, deci tine numai setarile
# (config.plugins.hdsnavigator, fara nimic pe disc) si functiile de deschidere. Ecranele si pornirea
# navigatorului (ecrane.py, lansator.py) se importa abia la prima chemare; procesul navigatorului nu exista pana
# atunci si se opreste de tot la inchidere.
#
# Navigatorul e o functie a imaginii: se deschide numai din meniu si din interfata web, nu din lista de extensii.
# Cine deschide:
#   - meniul: Media > „Navigator web” si Setari > Surse Internet > „Setări navigator web” (data/menu.xml, prin
#     Screens/HdsNavigatorWeb.py): deschideNavigator, deschideSetari;
#   - butonul din ecranul camului (Albastru): deschideInterfataCam;
#   - interfata web (HdsWebControl/navigator_web.py, /navigator): „Deschide pe televizor”.

from . import setari as S

S.initConfig()


def deschideNavigator(session, adresa=None, **kwargs):
	"""Navigatorul obisnuit: `adresa`, altfel pagina de pornire din setari."""
	from .ecrane import HdsNavigatorEcran
	from . import lansator as L
	return session.open(HdsNavigatorEcran, L.MOD_OBISNUIT, adresa)


def deschideInterfataCam(session, port=None, **kwargs):
	"""Interfata web a camului care ruleaza, gasita la rulare (fara nume, porturi sau parole scrise in imagine);
	`port` alege una dintre interfete cand sunt mai multe (butonul de pe cardul ei din interfata web)."""
	from .ecrane import HdsNavigatorEcran
	from . import lansator as L
	return session.open(HdsNavigatorEcran, L.MOD_CAM, None, port)


def deschideSetari(session, **kwargs):
	from .ecrane import HdsNavigatorSetari
	return session.open(HdsNavigatorSetari)


def Plugins(**kwargs):
	"""Fara descriptori: navigatorul nu apare in lista de extensii si nici la tasta albastra. Fisierul se incarca tot la
	pornire (setarile de mai sus), ca interfata web si Caută setări sa le gaseasca."""
	return []

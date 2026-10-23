# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ferestrele DAB+ si DVB-T2 din satelit, deschise din scaner (Screens/ScanerSatelit.py) sau din meniu.

Fereastra principala (Hds/DabT2/ecrane.py, EcranPrincipal) cere controlorul profilului, nu doar sesiunea. Aceste doua
clase il iau din Hds/DabT2/imagine.py (acelasi obiect pe tot procesul, cel pus in extensiile de zap), deci se deschid
cu session.open ca orice ecran. Numele claselor raman cele folosite de scaner, de Components/HdsLnbAplicare.py si de
probe.
"""
from Hds.DabT2.ecrane import EcranPrincipal


class HdsDabPrincipal(EcranPrincipal):
	def __init__(self, session):
		from Hds.DabT2 import imagine
		EcranPrincipal.__init__(self, session, imagine.controlor_dab())


class HdsT2miPrincipal(EcranPrincipal):
	def __init__(self, session):
		from Hds.DabT2 import imagine
		EcranPrincipal.__init__(self, session, imagine.controlor_t2())

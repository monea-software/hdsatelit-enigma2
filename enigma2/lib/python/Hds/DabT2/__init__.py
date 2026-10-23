# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""DAB+ si DVB-T2 din satelit, in codul imaginii.

Codul comun (tunerul, releele, listele, buchetele, lamedb, ferestrele, captura) e acelasi cu cel al pluginului pentru
alte imagini (acolo sta in Plugins/SystemPlugins/HdsComun); importurile dintre module sunt relative, deci pachetul
merge in ambele locuri. Numai imagine.py tine de imagine: pornirea din mytest.py, ferestrele din meniu.
  dab/motor, dab/date   releul DAB+ (proces separat) si lista de frecvente venita cu imaginea
  t2/motor, t2/date     releul DVB-T2 (proces separat), lista de frecvente; t2/bin: decapsulatorul T2-MI (C)
Aici nu se importa nimic: modulele se incarca la nevoie.
"""

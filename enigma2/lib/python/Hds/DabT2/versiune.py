# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Versiunea pachetului hdsatelit-comun. Facut de hdsatelit.com.

Aceeasi cu versiunea pachetului; construieste_ipk.py refuza construirea daca difera. Pluginurile cer cel putin
versiunea cu care au fost probate (VERSIUNE_MINIMA_COMUN in plugin.py)."""
VERSIUNE = '0.1.5'


def ca_tuplu(v):
    """'0.1.5' -> (0, 1, 5); partile nenumerice conteaza ca 0."""
    rez = []
    for parte in str(v).split('.'):
        cifre = ''
        for ch in parte:
            if not ch.isdigit():
                break
            cifre += ch
        rez.append(int(cifre) if cifre else 0)
    return tuple(rez)


def cel_putin(minima):
    return ca_tuplu(VERSIUNE) >= ca_tuplu(minima)

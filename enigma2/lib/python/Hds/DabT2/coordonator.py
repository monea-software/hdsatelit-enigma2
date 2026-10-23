# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Locul unde HdsDab si HdsT2mi se intalnesc cand sunt instalate amandoua. Facut de hdsatelit.com.

Codul comun poate exista in acelasi proces in mai multe copii (de exemplu o asezare veche, cu comunul copiat in
fiecare plugin). Doua copii inseamna doua seturi de variabile globale, care nu se vad intre ele. De aceea starea
comuna sta intr-un singur obiect pus in sys.modules sub un nume fix (NUME_MODUL): primul care il cere il creeaza,
ceilalti il gasesc. Tot dupa acest nume il gasesc si alte parti ale imaginii (Gasire semnal, rotirea antenei).

Ce tine:
  - cine tine tunerul unic de satelit (un singur detinator; cererea unui plugin il face pe celalalt sa cedeze
    intai, sincron, inainte de a aloca tunerul);
  - care plugin a inregistrat captura OSD (intrarea din Extensii si tasta), ca sa apara o singura data;
  - controlorii activi, ca captura sa afle ce post canta acum, indiferent de plugin.

Interfata e mica si nu se schimba intre versiuni; `protocol` creste doar la schimbari compatibile.
"""
import sys

NUME_MODUL = 'hdsatelit_hds_coordonator'
PROTOCOL = 1


class Coordonator(object):
    protocol = PROTOCOL

    def __init__(self):
        self.detinator = None          # controlorul care tine tunerul
        self.captura_la = None         # numele pluginului care a inregistrat captura
        self.tasta_legata = False
        self.controlori = {}           # nume plugin -> controlor
        self.captura = None            # obiectul de captura activ (unul singur)

    # ---- tunerul unic
    def cere_tuner(self, cine):
        """`cine` vrea tunerul. Daca il tine altcineva, acela cedeaza acum. Nu arunca."""
        vechi = self.detinator
        if vechi is not None and vechi is not cine:
            try:
                vechi.cedeaza('tunerul e cerut de %s' % getattr(cine, 'nume', '?'))
            except Exception:
                pass
        self.detinator = cine

    def elibereaza_tuner(self, cine):
        if self.detinator is cine:
            self.detinator = None

    # ---- inregistrari unice
    def inregistreaza_controlor(self, nume, controlor):
        self.controlori[nume] = controlor

    def ia_captura(self, nume):
        """True daca pluginul `nume` trebuie sa arate captura (primul care cere o primeste)."""
        if self.captura_la is None:
            self.captura_la = nume
        return self.captura_la == nume

    def controlor_activ(self):
        """Controlorul care canta acum un post al nostru, sau None."""
        for c in list(self.controlori.values()):
            try:
                if c.activ():
                    return c
            except Exception:
                pass
        return None


def obtine():
    """Coordonatorul comun al procesului. Il creeaza la primul apel."""
    m = sys.modules.get(NUME_MODUL)
    c = getattr(m, 'coordonator', None) if m is not None else None
    if c is None:
        import types
        m = types.ModuleType(NUME_MODUL)
        c = Coordonator()
        m.coordonator = c
        sys.modules[NUME_MODUL] = m
    return c


def uita():
    """Doar pentru probe: sterge coordonatorul comun."""
    sys.modules.pop(NUME_MODUL, None)

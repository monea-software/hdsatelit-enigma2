# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Procesul separat (releul) pornit si supravegheat din enigma2. Facut de hdsatelit.com.

Se foloseste eConsoleAppContainer: porneste procesul fara sa blocheze si anunta iesirea prin appClosed, in
bucla principala a enigma2. Iesirea standard nu se citeste (ar aduna memorie); erorile merg intr-un fisier din
/tmp care se goleste la fiecare pornire.

Supraveghere: daca procesul moare fara sa-l fi oprit noi, se reporneste de cel mult 3 ori intr-o fereastra de
10 minute; a patra cadere cheama `la_renuntare`. Oprirea voita nu se numara.
"""
import os

from . import compat, jurnal
from .limba import _

REPORNIRI_MAX = 3
FEREASTRA_S = 600
# fereastra caderilor pe ceasul monoton: nu sare cand ora se potriveste din retea
_monoton = compat.monoton


def _arunca(*date):
    """Citeste si arunca ce scrie procesul pe tevi (nu aduna memorie)."""
    return None


# Procese oprite de noi care trebuie culese: dupa kill(), enigma2 nu le culege mereu si raman zombie (Z) sub enigma2
# (vazut pe Viper 4K V20, releul DAB oprit la zap). Le culegem NEBLOCANT (WNOHANG), din firul principal.
_de_cules = {}          # pid -> incercari ramase
_timer_cules = [None, None]     # timerul si manierul legaturii lui (semnale-obiect: legatura tinuta cat traieste timerul)


def _culege():
    for pid in list(_de_cules):
        try:
            gata, _stare = os.waitpid(pid, os.WNOHANG)
        except OSError:
            gata = pid                      # ECHILD: l-a cules deja altcineva
        if gata == pid or _de_cules[pid] <= 1:
            _de_cules.pop(pid, None)
        else:
            _de_cules[pid] -= 1
    if not _de_cules and _timer_cules[0] is not None:
        _timer_cules[0].stop()


def _programeaza_culegerea(pid):
    if not pid or pid <= 0:
        return
    _de_cules[pid] = 15
    try:
        if _timer_cules[0] is None:
            from enigma import eTimer
            t = eTimer()
            _timer_cules[1] = compat.conecteaza_timer(t, _culege)
            _timer_cules[0] = t
        _timer_cules[0].start(1000, False)
    except Exception:
        _culege()


class Supraveghetor(object):

    def __init__(self, eticheta, la_repornire=None, la_renuntare=None):
        self.et = eticheta
        self.la_repornire = la_repornire   # la_repornire(numar) dupa o repornire reusita
        self.la_renuntare = la_renuntare   # la_renuntare(mesaj)
        self.comanda = None
        self._container = None
        self._conexiuni = []          # manierele semnalelor containerului (semnale-obiect: fara ele iesirea nu mai e anuntata)
        self._caderi = []
        self.porniri = 0
        self.opriri = 0

    def ruleaza(self):
        return self._container is not None

    def porneste(self, comanda):
        """Porneste comanda (sir pentru /bin/sh). Opreste intai ce rula. -> True daca a pornit."""
        self.opreste()
        self.comanda = comanda
        self._caderi = []
        return self._lanseaza()

    def _lanseaza(self):
        try:
            from enigma import eConsoleAppContainer
            c = eConsoleAppContainer()
            # manierele stau pe supraveghetor: cu semnale-obiect o legatura nepastrata nu mai anunta iesirea procesului
            self._conexiuni.append(compat.conecteaza(c.appClosed, self._inchis))
            # tevile raman deschise si golite (ce scrie procesul se arunca), altfel o teava plina opreste procesul
            for semnal in ('dataAvail', 'stderrAvail'):
                try:
                    self._conexiuni.append(compat.conecteaza(getattr(c, semnal), _arunca))
                except Exception:
                    pass
            self._container = c
            rez = c.execute(self.comanda)
            if rez:
                jurnal.noteaza(self.et, 'procesul nu a pornit (cod %s): %s' % (rez, self.comanda))
                self._curata()
                return False
            self.porniri += 1
            jurnal.noteaza(self.et, 'proces pornit: %s' % self.comanda)
            return True
        except Exception:
            jurnal.eroare(self.et, 'pornirea procesului')
            self._curata()
            return False

    def _curata(self):
        self._container = None
        compat.deconecteaza_toate(self._conexiuni)

    def opreste(self):
        """Oprire voita: nu se reporneste. Sincron."""
        c = self._container
        if c is None:
            return
        self._curata()
        try:
            if c.running():
                pid = 0
                try:
                    pid = c.getPID()
                except Exception:
                    pass
                c.kill()
                _programeaza_culegerea(pid)
        except Exception:
            jurnal.eroare(self.et, 'oprirea procesului')
        self.opriri += 1
        jurnal.noteaza(self.et, 'proces oprit')

    def _inchis(self, cod=None):
        try:
            if self._container is None:
                return
            self._curata()
            acum = _monoton()
            self._caderi = [t for t in self._caderi if acum - t < FEREASTRA_S] + [acum]
            jurnal.noteaza(self.et, 'procesul a iesit singur (cod %s), caderea %d' % (cod, len(self._caderi)))
            if len(self._caderi) > REPORNIRI_MAX:
                if self.la_renuntare:
                    self.la_renuntare(_('Releul s-a oprit de %d ori. Vezi /tmp/hdsdabt2.log.') % len(self._caderi))
                return
            if self._lanseaza() and self.la_repornire:
                self.la_repornire(len(self._caderi))
        except Exception:
            jurnal.eroare(self.et, 'supravegherea procesului')

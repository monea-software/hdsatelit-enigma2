# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Jurnalul pluginurilor HdsDab si HdsT2mi. Facut de hdsatelit.com.

Un singur fisier, /tmp/hdsdabt2.log, pentru amandoua pluginurile (fiecare linie are eticheta pluginului).
Se roteste la 200 KB: fisierul curent devine .1 (o singura generatie), deci pe /tmp nu stau niciodata mai mult
de 400 KB. Scrierea e protejata de un zavor, fiindca scriu si firele de lucru (descarcari, citiri HTTP).

`pazit` imbraca un callback: orice exceptie se prinde, se scrie in jurnal si se intoarce valoarea de rezerva.
O eroare a pluginului nu are voie sa ajunga in enigma2 (acolo ar da ecranul verde).
"""
import os
import threading
import time
import traceback

CALE = '/tmp/hdsdabt2.log'
MARIME_MAX = 200 * 1024

_zavor = threading.Lock()
_stare = {'cale': CALE, 'scrieri': 0}


def seteaza_cale(cale):
    """Doar pentru probe pe PC."""
    _stare['cale'] = cale


def cale():
    return _stare['cale']


def _roteste(c):
    try:
        if os.path.getsize(c) >= MARIME_MAX:
            vechi = c + '.1'
            try:
                os.remove(vechi)
            except OSError:
                pass
            os.rename(c, vechi)
    except OSError:
        pass


def noteaza(eticheta, mesaj):
    """Scrie o linie. Nu arunca niciodata."""
    try:
        linie = '%s [%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), eticheta, mesaj)
        with _zavor:
            c = _stare['cale']
            # verificarea marimii costa un stat; o facem la fiecare a 20-a scriere si la prima
            _stare['scrieri'] += 1
            if _stare['scrieri'] % 20 == 1:
                _roteste(c)
            with open(c, 'a') as f:
                f.write(linie)
    except Exception:
        pass


def eroare(eticheta, unde):
    """Scrie exceptia curenta, pe scurt (ultimele 12 linii din traceback)."""
    try:
        linii = traceback.format_exc().rstrip().splitlines()[-12:]
        noteaza(eticheta, 'EROARE in %s: %s' % (unde, ' | '.join(l.strip() for l in linii)))
    except Exception:
        pass


def pazit(eticheta, rezerva=None):
    """Decorator: functia nu arunca niciodata. La eroare scrie in jurnal si intoarce `rezerva`.

    Daca `rezerva` e o functie, se cheama cu aceleasi argumente (asa extensia de zap poate intoarce
    referinta primita, neatinsa)."""
    def decor(functie):
        nume = getattr(functie, '__name__', 'callback')

        def invelis(*a, **k):
            try:
                return functie(*a, **k)
            except Exception:
                eroare(eticheta, nume)
                if callable(rezerva):
                    try:
                        return rezerva(*a, **k)
                    except Exception:
                        return None
                return rezerva
        invelis.__name__ = nume
        invelis.__doc__ = functie.__doc__
        return invelis
    return decor

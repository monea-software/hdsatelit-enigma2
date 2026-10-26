# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Jurnalul pluginurilor HdsDab si HdsT2mi. Facut de hdsatelit.com.

Un singur fisier, /tmp/hdsdabt2.log, pentru amandoua pluginurile (fiecare linie are eticheta pluginului).
Se roteste la 200 KB: fisierul curent devine .1 (o singura generatie), deci pe /tmp nu stau niciodata mai mult
de 400 KB. Scrierea e protejata de un zavor, fiindca scriu si firele de lucru (descarcari, citiri HTTP).

Erorile (exceptiile scrise de `eroare`) merg si in CALE_ERORI, in dosarul jurnalelor de pe memoria interna: raman
dupa repornire (de acolo le trimit testerii) si le arata Jurnalele sistemului; cel mult MARIME_ERORI, apoi .1. Dosarul
nu se face de aici (pe receptor il face paznicul), deci probele de pe PC nu scriu acolo.

`pazit` imbraca un callback: orice exceptie se prinde, se scrie in jurnal si se intoarce valoarea de rezerva.
O eroare a pluginului nu are voie sa ajunga in enigma2 (acolo ar da ecranul verde).
"""
import os
import re
import threading
import time
import traceback

CALE = '/tmp/hdsdabt2.log'
MARIME_MAX = 200 * 1024
CALE_ERORI = '/home/root/logs/hds-dabt2-erori.log'
MARIME_ERORI = 64 * 1024
# numele si parola dintr-o adresa de flux (http://nume:parola@gazda/...) nu ajung in jurnalul de pe disc
_PAROLA_IN_ADRESA = re.compile(r'(?i)\b((?:https?|rtsp|udp|rtp)://)[^/\s@]+@')

_zavor = threading.Lock()
_stare = {'cale': CALE, 'erori': CALE_ERORI, 'scrieri': 0}


def seteaza_cale(cale, erori=None):
    """Doar pentru probe pe PC."""
    _stare['cale'] = cale
    if erori is not None:
        _stare['erori'] = erori


def _pastreaza_eroare(linie):
    """Linia unei erori, adaugata la jurnalul erorilor de pe memoria interna (rotit la MARIME_ERORI, o copie .1);
    numai cand dosarul exista, fara legaturi simbolice, fara numele si parola din adresele fluxurilor. Nu arunca."""
    c = _stare['erori']
    try:
        if not c or not os.path.isdir(os.path.dirname(c)) or os.path.islink(c):
            return
        date = _PAROLA_IN_ADRESA.sub(r'\1', linie).encode('utf-8', 'replace')[:MARIME_ERORI]
        if os.path.isfile(c) and os.path.getsize(c) + len(date) > MARIME_ERORI:
            os.replace(c, c + '.1')
        fd = os.open(c, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            os.write(fd, date)
            # erorile sunt rare: fsync, ca sa ramana si dupa o repornire dura a receptorului
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        pass


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
    """Scrie exceptia curenta, pe scurt (ultimele 12 linii din traceback), in jurnal si in jurnalul erorilor de pe
    memoria interna."""
    try:
        linii = traceback.format_exc().rstrip().splitlines()[-12:]
        mesaj = 'EROARE in %s: %s' % (unde, ' | '.join(l.strip() for l in linii))
        noteaza(eticheta, mesaj)
        with _zavor:
            _pastreaza_eroare('%s [%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), eticheta, mesaj))
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

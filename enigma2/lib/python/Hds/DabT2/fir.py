# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Munca pentru firul principal al enigma2, ceruta din orice fir, fara asteptare. Facut de hdsatelit.com.

enigma2 e facut pentru un singur fir: ferestrele, tunerul (eDVBResourceManager), eTimer, Navigation se ating DOAR
din bucla principala. Daca un alt plugin (sau o unealta) cheama Navigation.playService dintr-un fir al lui,
extensiile noastre de zap ruleaza in firul acela; asa s-a blocat enigma2 cand o unealta a chemat zap-ul dintr-un
fir twisted.

  in_principal()             True daca firul curent e cel al buclei enigma2
  programeaza(functie, *a)   pune functia in coada si trezeste bucla principala; se intoarce imediat
  goleste()                  ruleaza coada (doar in firul principal)

Trezirea: twisted `reactor.callFromThread` (scrie intr-un fd de trezire, sigur din orice fir; reactorul enigma2
ruleaza in bucla principala). Fara twisted: un eTimer creat si pornit in firul principal la pornirea sesiunii
(`porneste_plasa`), la 500 ms. Bataia paznicului (la 10 s) goleste si ea coada, ca ultima plasa.
Nimic de aici nu asteapta un alt fir.
"""
import collections
import threading

from . import compat, jurnal

PAS_PLASA_MS = 500
MAX_PE_GOLIRE = 64

_coada = collections.deque()
_stare = {'ident': None, 'timer': None, 'legatura': None, 'trezire': None}


def marcheaza_principal():
    """Chemat din firul principal (pornirea sesiunii): tine minte care e firul buclei enigma2."""
    _stare['ident'] = threading.current_thread().ident


def in_principal():
    ident = _stare['ident']
    fir = threading.current_thread()
    if ident is not None:
        return fir.ident == ident
    principal = getattr(threading, 'main_thread', None)
    if principal is not None:
        return fir is principal()
    return isinstance(fir, getattr(threading, '_MainThread', ()))


def _trezeste():
    f = _stare['trezire']
    if f is not None:
        f(goleste)
        return True
    try:
        from twisted.internet import reactor
        reactor.callFromThread(goleste)
        return True
    except Exception:
        return False


def programeaza(functie, *argumente):
    """Ruleaza functie(*argumente) in firul principal, cat de curand. Nu asteapta si nu arunca."""
    _coada.append((functie, argumente))
    try:
        _trezeste()
    except Exception:
        pass


def in_asteptare():
    return len(_coada)


def goleste():
    if not in_principal():
        return
    n = 0
    while _coada and n < MAX_PE_GOLIRE:
        try:
            functie, argumente = _coada.popleft()
        except IndexError:
            break
        n += 1
        try:
            functie(*argumente)
        except Exception:
            jurnal.eroare('fir', 'munca amanata')


def porneste_plasa():
    """Doar din firul principal. Daca twisted lipseste, un eTimer la 500 ms goleste coada."""
    try:
        from twisted.internet import reactor  # noqa: F401
        return False
    except Exception:
        pass
    try:
        if _stare['timer'] is None:
            from enigma import eTimer
            t = eTimer()
            _stare['legatura'] = compat.conecteaza_timer(t, goleste)   # semnale-obiect: legatura tinuta cat traieste timerul
            _stare['timer'] = t
        _stare['timer'].start(PAS_PLASA_MS, False)
        return True
    except Exception:
        jurnal.eroare('fir', 'plasa fara twisted')
        return False

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Protectia la pornire: un serviciu de-al nostru care a oprit enigma2 nu se mai porneste singur. Facut de hdsatelit.com.

La zap pe un serviciu al nostru se scrie pe disc (directorul pluginului din /etc/enigma2) marcajul
„pornesc <ref> <t>". Se sterge cand redarea a mers 20 s sau cand serviciul se opreste normal (zap, stop, standby,
iesirea din enigma2). Daca la pornirea unei sesiuni noi marcajul exista si e mai nou de 10 minute, enigma2 a murit
(blocaj, paznic, repornire de mana) in timpul pornirii serviciului: acel serviciu nu se mai porneste automat.

Pe disc, nu in /tmp: dupa un blocaj in driver receptorul se reporneste de mana, /tmp se goleste, iar enigma2 porneste
singur ultimul serviciu; exact bucla care trebuie oprita. Scrierea e mica si fara fsync (nu tine firul principal).
Varsta: in aceeasi pornire a receptorului (boot_id) dupa ceasul monoton; dupa o repornire dupa ceasul de perete.

Controlorul scrie si sterge marcajul in fundal (scrie_in_fundal, sterge_in_fundal): pe flash, la pornirea receptorului,
un singur open a tinut firul principal 4,8 s (pachetul 2186, FRD). Fiecare scriere sau stergere ia un numar de ordine pe
director; in fundal se face numai daca e inca ultima ceruta, deci o scriere intarziata nu readuce un marcaj sters dupa ea.
sterge() (iesirea enigma2, pornirea sesiunii) ramane pe loc si trece si ea la un numar nou.
"""
import json
import os
import threading

from . import compat

NUME = 'pornire.marcaj'
VALABIL_S = 600
REDARE_BUNA_S = 20


def cale(director):
    return os.path.join(director, NUME)


def boot_id():
    try:
        with open('/proc/sys/kernel/random/boot_id') as f:
            return f.read(64).strip() or None
    except (IOError, OSError):
        return None


_zavor = threading.Lock()       # numai pentru numere: nu se tine niciodata in timpul unei scrieri pe disc
_zavor_disc = threading.Lock()  # verificarea numarului si scrierea sau stergerea care urmeaza, una cate una
_ordine = {}                    # director -> numarul ultimei scrieri sau stergeri cerute


def _urmatorul(director):
    """Numarul de ordine al unei cereri noi pe director (firul principal nu asteapta niciun disc aici)."""
    with _zavor:
        n = _ordine.get(director, 0) + 1
        _ordine[director] = n
        return n


def _ultimul(director, n):
    with _zavor:
        return _ordine.get(director) == n


def _scrie_tmp(director, tmp, ref, inainte, acum, mono, boot):
    if not os.path.isdir(director):
        os.makedirs(director)
    with open(tmp, 'w') as f:
        f.write(json.dumps({'ref': ref, 'inainte': inainte, 't': acum, 'mono': mono, 'boot': boot}))


def scrie(director, ref, inainte, acum, mono, boot):
    """Fara fsync: pagina ajunge pe flash in cateva secunde si supravietuieste mortii enigma2."""
    c = cale(director)
    tmp = c + '.tmp'
    _scrie_tmp(director, tmp, ref, inainte, acum, mono, boot)
    with _zavor_disc:
        _urmatorul(director)
        compat.inlocuieste(tmp, c)


def _porneste_fir(tinta):
    """Firul de fundal, ca la fundal.Fundal (fara asteptarea pornirii lui). Probele il pot inlocui."""
    from . import fundal
    fundal._porneste_fir(tinta)


def scrie_in_fundal(director, ref, inainte, acum, mono, boot):
    """Ca scrie(), intr-un fir: firul principal nu atinge discul. Fisierul temporar are numarul cererii (doua scrieri
    din fire diferite nu impart acelasi fisier). Erorile se pierd: protectia e o plasa de siguranta, nu o functie."""
    n = _urmatorul(director)

    def lucru():
        c = cale(director)
        tmp = '%s.tmp%d' % (c, n)
        try:
            _scrie_tmp(director, tmp, ref, inainte, acum, mono, boot)
            with _zavor_disc:
                if _ultimul(director, n):
                    compat.inlocuieste(tmp, c)
                    return
            os.remove(tmp)      # dupa ea s-a cerut alta scriere sau o stergere: a ei ramane
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
    _porneste_fir(lucru)


def citeste(director):
    try:
        with open(cale(director)) as f:
            m = json.loads(f.read(8192))
        return m if isinstance(m, dict) and m.get('ref') else None
    except (IOError, OSError, ValueError):
        return None


def sterge(director):
    with _zavor_disc:
        _urmatorul(director)
        try:
            os.remove(cale(director))
            return True
        except OSError:
            return False


def sterge_in_fundal(director, la_gata=None):
    """Ca sterge(), intr-un fir; numai daca dupa ea nu s-a cerut o scriere noua. la_gata(sters) se cheama din fir."""
    n = _urmatorul(director)

    def lucru():
        sters = False
        with _zavor_disc:
            if _ultimul(director, n):
                try:
                    os.remove(cale(director))
                    sters = True
                except OSError:
                    pass
        if la_gata is not None:
            try:
                la_gata(sters)
            except Exception:
                pass
    _porneste_fir(lucru)


def recent(m, acum, mono, boot):
    """Marcajul e mai nou de 10 minute? Cu ceasul de perete gresit (in urma) se socoteste recent: mai bine un
    serviciu nepornit o data decat o bucla de blocaje."""
    if not m:
        return False
    if boot and m.get('boot') == boot and isinstance(m.get('mono'), (int, float)):
        return -1 <= mono - m['mono'] < VALABIL_S
    t = m.get('t')
    if not isinstance(t, (int, float)):
        return False
    return acum - t < VALABIL_S

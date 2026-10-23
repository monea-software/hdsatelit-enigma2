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
"""
import json
import os

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


def scrie(director, ref, inainte, acum, mono, boot):
    """Fara fsync: pagina ajunge pe flash in cateva secunde si supravietuieste mortii enigma2."""
    if not os.path.isdir(director):
        os.makedirs(director)
    c = cale(director)
    tmp = c + '.tmp'
    with open(tmp, 'w') as f:
        f.write(json.dumps({'ref': ref, 'inainte': inainte, 't': acum, 'mono': mono, 'boot': boot}))
    compat.inlocuieste(tmp, c)


def citeste(director):
    try:
        with open(cale(director)) as f:
            m = json.loads(f.read(8192))
        return m if isinstance(m, dict) and m.get('ref') else None
    except (IOError, OSError, ValueError):
        return None


def sterge(director):
    try:
        os.remove(cale(director))
        return True
    except OSError:
        return False


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

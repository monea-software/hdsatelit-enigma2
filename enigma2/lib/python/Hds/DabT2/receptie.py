# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Legatura cu skinul HDSatelit: /tmp/hdsatelit/receptie.json. Facut de hdsatelit.com.

Formatul e cel din conventia plugin -> skin (receptor\\skin\\cercetare\\tipuri-receptie-si-dab.md, sectiunea 8):
chei scurte, numerele purtatorului cu aceleasi enumuri si unitati ca dictionarul de transponder al enigma2
(frequency in kHz, polarization 0..3, fec_inner, modulation, system, is_id, pls_mode, pls_code). Skinul il
foloseste doar daca e mai nou de 15 s si `sref_redat` e serviciul redat.
Scriere atomica (fisier .tmp in acelasi director, apoi mutare), cel mult o data la 2 s, doar cat canta un serviciu
al nostru; la oprire fisierul se sterge. /tmp e in RAM. Fara dB (placa da o valoare relativa: calitate in procente).

Semnalul tunerului care tine purtatorul (serviciul redat e un flux local, fara tuner propriu: enigma2 da 0 pe tot):
in `purtator`, cand s-a citit, `semnal` si `calitate` in procente, `prins` (lock), `ber` si `tuner` (slotul, 0 = A).
Lipsesc cand citirea nu a venit inca; skinul spune atunci ca nu are date, nu „fara semnal”.
"""
import json
import os

from . import compat, tuner

CALE = '/tmp/hdsatelit/receptie.json'
PAS_S = 2.0
VERSIUNE = 1

TRANSPORT = {'edi': 'MPE/UDP/EDI', 'ts2na': 'ETI-NA in TS', 'ts2na12': 'ETI-NA in TS', 'tsniv2ni': 'ETI-NI in TS',
             't2mi': 'T2-MI'}


def _int(v):
    try:
        if compat.e_text(v) and v.lower().startswith('0x'):     # si unicode din JSON pe 2.7
            return int(v, 16)
        return int(v)
    except (TypeError, ValueError):
        return None


def _procent(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return max(0, min(100, int(v)))


def campuri_semnal(semnal, slot=None):
    """Citirea tunerului (tuner.citeste_semnal) -> campurile de semnal ale purtatorului. Numai ce s-a citit."""
    rez = {}
    semnal = semnal or {}
    for cheie, din in (('semnal', 'semnal_la_suta'), ('calitate', 'calitate_la_suta')):
        p = _procent(semnal.get(din))
        if p is not None:
            rez[cheie] = p
    if isinstance(semnal.get('lock'), bool):
        rez['prins'] = semnal['lock']
    ber = semnal.get('ber')
    if isinstance(ber, int) and not isinstance(ber, bool) and ber >= 0:
        rez['ber'] = ber
    if rez and isinstance(slot, int) and not isinstance(slot, bool) and 0 <= slot <= 25:
        rez['tuner'] = slot
    return rez


def compune(tip_plugin, sref, feed, tp, sid=None, post=None, releu=None, semnal=None, ref_purtator=None, acum=0,
            slot=None):
    """Dictionarul pentru skin. Functie pura. `slot`: tunerul care tine purtatorul (0 = A)."""
    feed = feed or {}
    releu = releu or {}
    p = tuner.parametri(tp or {})
    purtator = {
        'sref': ref_purtator,
        'orbital_position': p['orbital_position'],
        'frequency': p['frequency'],
        'polarization': p['polarisation'],
        'symbol_rate': p['symbol_rate'],
        'system': p['system'],
        'modulation': p['modulation'],
        'fec_inner': p['fec'],
        'is_id': p['is_id'],
        'pls_mode': p['pls_mode'],
        'pls_code': p['pls_code'],
        'pid': _int(feed.get('pid')),
    }
    purtator.update(campuri_semnal(semnal, slot))
    rez ={'v': VERSIUNE, 'sref_redat': sref, 'purtator': purtator, 'actualizat': int(acum)}
    fel = str(feed.get('fel') or '')
    if tip_plugin == 'dab':
        post = post or {}
        dabplus = str(post.get('fel') or 'dab+').lower() in ('dab+', 'dabplus')
        rez['tip'] = 'DAB+' if dabplus else 'DAB'
        rez['sursa'] = 'HDSatelit DAB'
        transport = TRANSPORT.get(fel, fel)
        if fel == 'edi' and feed.get('ip'):
            transport = '%s %s:%s' % (transport, feed.get('ip'), feed.get('port'))
        dab = {'ansamblu': releu.get('ansamblu') or feed.get('nume'), 'eid': feed.get('ansamblu'),
               'sid': '%04X' % sid if isinstance(sid, int) and sid > 0 else None, 'post': post.get('nume'),
               'codec': 'HE-AAC' if dabplus else 'MPEG Audio Layer II', 'kbit': _int(post.get('kbit')),
               'transport': transport}
        rez['dab'] = dict((k, v) for k, v in dab.items() if v not in (None, ''))
    else:
        rez['tip'] = 'T2-MI'
        rez['sursa'] = 'HDSatelit T2-MI'
        rez['t2'] = {'plp_id': _int(feed.get('plp')), 't2mi_pid': _int(feed.get('pid'))}
    return rez


def scrie(date, cale=None):
    cale = cale or CALE
    director = os.path.dirname(cale)
    if not os.path.isdir(director):
        os.makedirs(director)
    tmp = cale + '.tmp'
    with open(tmp, 'w') as f:
        f.write(json.dumps(date, sort_keys=True))
    compat.inlocuieste(tmp, cale)


def sterge(cale=None):
    try:
        os.remove(cale or CALE)
    except OSError:
        pass

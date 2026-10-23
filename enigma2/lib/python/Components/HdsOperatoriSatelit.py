# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Operatorii de satelit: scanarea dupa operator, DVB-T2 prin satelit si DAB+ prin satelit.

Datele stau in data/operatori-satelit.json (instalat in /usr/share/enigma2), cu sursa scrisa pe fiecare valoare.
Modulul le citeste, le pune in ordine (intai operatorii din tara
utilizatorului, apoi ceilalti, pe tari) si le da in cele doua forme de care e nevoie:
  - transponder_nucleu(op): campurile lui eDVBFrontendParametersSatellite (lib/dvb/frontendparms.h), pentru o
    scanare obisnuita (ServiceScan), aceleasi pe care le folosesc Screens/ScanerSatelit.py si probele lui;
  - transponder_hdscomun(op): formatul listelor HdsComun (HdsComun/liste.py, HdsComun/tuner.parametri), pentru
    DVB-T2 si DAB+ prin satelit, unde nu se face o scanare DVB, ci acord plus detectorul HdsComun.

Unitatile (antetul JSON-ului): frecventa e deja in kHz; rata e in kSymb/s si se inmulteste cu 1000 numai aici, o
singura data (inmultirea dubla a stricat deja de doua ori transpondere in acest depozit); pozitia e bruta,
0..3599, cu vestul ca 3600 - x (5,0 vest = 3550).

Motorul: pozitia NU se traduce in numere negative. lib/dvb/db.cpp (randurile 825-832) aduce deja position="-50"
din satellites.xml la 3550 cand il citeste, deci NimManager si SEC-ul lucreaza numai cu 0..3599, iar
lib/dvb/sec.cpp (randul 506) calculeaza unghiul USALS din abs(orbital_position) / 10: un -50 trimis nucleului
ar fi insemnat 5,0 grade EST si antena ar fi plecat in partea cealalta. Antena se duce singura pe pozitia
ceruta, la acord, din orbital_position.

Tara utilizatorului: nu exista o setare de tara; se ia din config.osd.language (implicit "ro_RO"), bucata de
dupa "_". Components/Language.py nu scrie peste tot coduri ISO: sarba e "YU" (in JSON "RS"), engleza "EN"
(aici "GB"). POTRIVIRI_TARA le aduce la codul din JSON.

Modulul nu importa nimic din enigma la incarcare: se poate proba pe PC (teste/test_scaner_satelit.py).
"""
from __future__ import absolute_import, unicode_literals

import io
import json
import os

NUME_FISIER = 'operatori-satelit.json'

# felul de scanare din meniu -> felul din JSON
FEL_JSON = {'operator': 'tv', 'dvbt2': 't2mi', 'dab': 'dab', 'tv': 'tv', 't2mi': 't2mi'}

# Components/Language.py -> codul de tara din JSON (ISO 3166, doua litere)
POTRIVIRI_TARA = {'YU': 'RS', 'EN': 'GB'}
TARA_IMPLICITA = 'RO'

# textele din JSON -> codurile lui eDVBFrontendParametersSatellite (lib/dvb/frontendparms.h)
POLARIZARE = {'H': 0, 'V': 1, 'L': 2, 'R': 3}
SISTEM = {'DVB-S': 0, 'DVB-S2': 1}
MODULATIE = {'QPSK': 1, '8PSK': 2, 'QAM16': 3}       # APSK nu exista in nucleu: -1, refuzat de motiv_refuz
FEC = {'1/2': 1, '2/3': 2, '3/4': 3, '5/6': 4, '7/8': 5, '8/9': 6, '3/5': 7, '4/5': 8, '9/10': 9}

_cache = {}


def N_(text):
    """Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la folosire, cu _text()."""
    return text


def _text(s):
    try:
        return _(s)          # noqa: F821  (functia de traducere a enigma2, pusa in builtins)
    except NameError:
        return s


def cai_posibile():
    """Unde poate sta fisierul: in imagine (/usr/share/enigma2) si, pe PC, in data/ din depozit."""
    cai = []
    try:
        from enigma import eEnv
        cai.append(eEnv.resolve('${datadir}/enigma2/' + NUME_FISIER))
    except Exception:
        pass
    cai.append('/usr/share/enigma2/' + NUME_FISIER)
    aici = os.path.dirname(os.path.abspath(__file__))
    cai.append(os.path.normpath(os.path.join(aici, '..', '..', '..', 'data', NUME_FISIER)))
    return cai


def cale_date():
    cai = cai_posibile()
    for c in cai:
        if os.path.isfile(c):
            return c
    return cai[0]


def incarca(cale=None):
    """Continutul JSON-ului ({"operatori": [...], ...}). Fisier lipsa sau stricat: {"operatori": [], "eroare": ...}.
    Se tine minte dupa cale si data modificarii, deci o actualizare a fisierului se vede fara repornire."""
    cale = cale or cale_date()
    try:
        semn = os.path.getmtime(cale)
    except OSError:
        return {'operatori': [], 'eroare': 'lipseste %s' % cale}
    vechi = _cache.get(cale)
    if vechi and vechi[0] == semn:
        return vechi[1]
    try:
        with io.open(cale, encoding='utf-8') as f:
            date = json.load(f)
        if not isinstance(date, dict) or not isinstance(date.get('operatori'), list):
            raise ValueError('fara lista "operatori"')
    except Exception as e:
        return {'operatori': [], 'eroare': 'nu se poate citi %s: %s' % (cale, e)}
    _cache[cale] = (semn, date)
    return date


def tara_din_limba(limba):
    """"ro_RO" -> "RO", "sr_YU" -> "RS", "en_EN" -> "GB". None daca nu are tara."""
    if not limba or '_' not in str(limba):
        return None
    tara = str(limba).split('_', 1)[1].strip().upper()
    if not tara:
        return None
    return POTRIVIRI_TARA.get(tara, tara)


def tara_utilizatorului():
    """Codul de tara (doua litere) din limba aleasa pentru meniuri; "RO" daca nu se poate afla."""
    try:
        from Components.config import config
        tara = tara_din_limba(config.osd.language.value)
    except Exception:
        tara = None
    return tara or TARA_IMPLICITA


def cere_multistream(op):
    """Transponderul operatorului are mai multe fluxuri (flux = is_id) sau cod PLS: se acordeaza numai cu un tuner
    care poate alege fluxul (NIM.isMultistream) si cu nucleul care are is_id, pls_mode si pls_code
    (lib/dvb/frontendparms.h, lib/dvb/hdsmultistream.h)."""
    t = op.get('transponder') or {}
    return t.get('pls') is not None or t.get('flux') is not None


# modul PLS din JSON -> pls_mode din nucleu (0 Root, 1 Gold, 2 Combo)
PLS_MOD = {'root': 0, 'gold': 1, 'combo': 2}


def campuri_multistream(op):
    """is_id, pls_mode si pls_code ale transponderului de pornire, in valorile nucleului. Fara flux si fara PLS: fara
    filtru (-1) si secventa implicita (Gold 0). Cu PLS si fara flux se trimite fluxul 0 (lib/dvb/hdsmultistream.h)."""
    t = op.get('transponder') or {}
    pls = t.get('pls') or None
    flux = t.get('flux')
    is_id = int(flux) if flux is not None and 0 <= int(flux) <= 255 else -1
    if pls:
        mod = PLS_MOD.get(str(pls.get('mod') or 'gold').lower(), 1)
        cod = int(pls.get('cod') or 0) & 0x3FFFF
    else:
        mod, cod = 1, 0
    return {'is_id': is_id, 'pls_mode': mod, 'pls_code': cod}


def _completat(op, tara):
    o = dict(op)
    o['din_tara'] = tara in (op.get('tari') or [])
    o['cere_multistream'] = cere_multistream(op)
    return o


def _prima_tara(op):
    return (op.get('tari') or ['?'])[0]


def operatori(fel, tara=None, cale=None):
    """Operatorii unui fel ("tv", "t2mi", "dab" sau felul de scanare "operator", "dvbt2", "dab"), in ordinea de
    afisat: intai cei din tara utilizatorului, in ordinea din JSON; apoi ceilalti, pe tari (prima tara a
    operatorului), tarile in ordinea in care apar in JSON. Fiecare e operatorul din JSON plus "din_tara" si
    "cere_multistream"."""
    fel = FEL_JSON.get(fel, fel)
    if tara is None:
        tara = tara_utilizatorului()
    toti = [o for o in incarca(cale).get('operatori', []) if isinstance(o, dict) and o.get('fel') == fel]
    ai_tarii = [o for o in toti if tara in (o.get('tari') or [])]
    tari = []
    for o in toti:
        if _prima_tara(o) not in tari:
            tari.append(_prima_tara(o))
    restul = []
    for t in tari:
        restul += [o for o in toti if o not in ai_tarii and _prima_tara(o) == t]
    return [_completat(o, tara) for o in ai_tarii + restul]


def grupe(fel, tara=None, cale=None):
    """Blocurile de afisat: [(titlu, [op, ...])]. Primul e mereu cel al tarii utilizatorului, chiar gol (pentru
    Romania, la DVB-T2 si DAB+ prin satelit, nu exista niciun operator, iar ecranul trebuie sa o spuna limpede);
    apoi cate un bloc pe tara, in ordinea din operatori()."""
    if tara is None:
        tara = tara_utilizatorului()
    lista = operatori(fel, tara, cale)
    rez = [(_text(N_('Din țara ta (%s)')) % nume_tara(tara), [o for o in lista if o['din_tara']])]
    ultima = None
    for o in lista:
        if o['din_tara']:
            continue
        if _prima_tara(o) != ultima:
            ultima = _prima_tara(o)
            rez.append((nume_tara(ultima), []))
        rez[-1][1].append(o)
    return rez


def operator(id_operator, tara=None, cale=None):
    """Operatorul cu id-ul dat (din JSON, completat cu din_tara si cere_multistream), sau None."""
    for o in incarca(cale).get('operatori', []):
        if isinstance(o, dict) and o.get('id') == id_operator:
            return _completat(o, tara_utilizatorului() if tara is None else tara)
    return None


def transponder_nucleu(op):
    """Transponderul de pornire, cu campurile si unitatile lui eDVBFrontendParametersSatellite: frecventa in kHz
    (asa e deja in JSON), rata in simboluri/s, pozitia bruta 0..3599. Inversare Auto (2), roll-off 0,35 (0) si
    pilot Auto (2), ca in HdsComun/tuner.parametri, cu care s-a acordat pe receptor. La un transponder multistream
    se adauga is_id, pls_mode si pls_code (campuri_multistream)."""
    t = op['transponder']
    sistem = SISTEM.get(t.get('sistem'), -1)
    tp = {
        'frequency': int(t['frecventa']),
        'symbol_rate': int(t['rata']) * 1000,
        'polarisation': POLARIZARE.get(t.get('pol'), -1),
        'fec': FEC.get(t.get('fec'), 0),
        'inversion': 2,
        'orbital_position': int(op['pozitie']),
        'system': sistem,
        'modulation': MODULATIE.get(t.get('modulatie'), -1) if sistem == 1 else 1,
        'rolloff': 0,
        'pilot': 2,
    }
    if cere_multistream(op):
        tp.update(campuri_multistream(op))
    return tp


def transponder_hdscomun(op):
    """Transponderul in formatul listelor HdsComun (frecvente.json): frecventa in kHz, sr in simboluri/s, pol,
    sistem, modulatie si FEC ca text, is_id din "flux", pls_mod/pls_cod din "pls". Il primesc
    HdsComun/tuner.Tuner.acordeaza si HdsComun/liste.adauga_scanat."""
    t = op['transponder']
    pls = t.get('pls') or None
    return {
        'id': 'op_%s' % op['id'],
        'pozitie': int(op['pozitie']),
        'frecventa': int(t['frecventa']),
        'pol': t.get('pol'),
        'sr': int(t['rata']) * 1000,
        'sistem': t.get('sistem'),
        'modulatie': t.get('modulatie'),
        'fec': t.get('fec'),
        'is_id': t.get('flux'),
        'pls_mod': pls.get('mod') if pls else None,
        'pls_cod': pls.get('cod') if pls else None,
        'feeduri': [],
    }


def nume_tara(cod):
    """Numele tarii, tradus; codul insusi daca nu e in tabel."""
    nume = NUME_TARI.get(cod)
    return _text(nume) if nume else str(cod)


# Tarile din JSON si cele din Components/Language.py (tara limbii de meniu), cu numele in romana (msgid).
NUME_TARI = {
    'RO': N_('România'), 'MD': N_('Republica Moldova'), 'CZ': N_('Cehia'), 'SK': N_('Slovacia'), 'HU': N_('Ungaria'),
    'PL': N_('Polonia'), 'RS': N_('Serbia'), 'HR': N_('Croația'), 'SI': N_('Slovenia'),
    'BA': N_('Bosnia și Herțegovina'), 'ME': N_('Muntenegru'), 'MK': N_('Macedonia de Nord'), 'GB': N_('Regatul Unit'),
    'IE': N_('Irlanda'), 'DE': N_('Germania'), 'AT': N_('Austria'), 'IT': N_('Italia'), 'FR': N_('Franța'),
    'ES': N_('Spania'), 'CY': N_('Cipru'), 'UA': N_('Ucraina'), 'RU': N_('Rusia'), 'GR': N_('Grecia'),
    'NL': N_('Țările de Jos'), 'DK': N_('Danemarca'), 'EE': N_('Estonia'), 'FI': N_('Finlanda'), 'LT': N_('Lituania'),
    'LV': N_('Letonia'), 'IS': N_('Islanda'), 'NO': N_('Norvegia'), 'PT': N_('Portugalia'), 'SE': N_('Suedia'),
    'TR': N_('Turcia'), 'AE': N_('Emiratele Arabe Unite'), 'AD': N_('Andorra'),
}

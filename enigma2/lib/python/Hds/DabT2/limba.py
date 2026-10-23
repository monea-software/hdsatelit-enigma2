# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Traducerile codului DAB+ si DVB-T2 din satelit. Facut de hdsatelit.com.

Textele din cod sunt in romana fara diacritice (msgid); romana cu diacritice vine tot din catalog (ro).
Doua feluri de lucru, dupa numele pachetului:
  - in imaginea HDSatelit (pachetul Hds.DabT2): textele stau in catalogul imaginii (domeniul enigma2, po/<limba>.po)
    si le traduce functia _ pusa de enigma2 in builtins; Components.Language o pune din nou la schimbarea limbii,
    deci se cauta la fiecare apel, nu o data la import;
  - ca plugin pe alte imagini (Plugins/SystemPlugins/HdsComun): catalogul propriu, domeniul HdsComun,
    locale/<limba>/LC_MESSAGES/HdsComun.mo langa modul (facut din .po cu unelte/po_in_mo.py); limba vine din
    Components.Language, iar in afara celor 13 limbi se foloseste engleza.
`seteaza()` ramane pentru pluginuri: leaga schimbarea limbii o singura data si nu schimba domeniul.
"""
import gettext
import os

LIMBI = ('ro', 'en', 'de', 'fr', 'es', 'it', 'pt', 'pl', 'nl', 'tr', 'cs', 'hu', 'ru')
IMPLICIT = 'en'
DOMENIU = 'HdsComun'
# In imagine pachetul e Hds.DabT2; ca plugin, Plugins.SystemPlugins.HdsComun (sau HdsComun in probe).
IN_IMAGINE = __name__.startswith('Hds.')

_stare = {'domeniu': DOMENIU, 'cale': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locale'),
          'limba': None, 'traducere': None, 'fortat': None, 'legat': False}


def seteaza(domeniu=None, cale_plugin=None):
    """Chemat din plugin.py. Argumentele sunt pastrate pentru pluginurile vechi; catalogul e al comunului."""
    _stare['limba'] = None
    if _stare['legat']:
        return
    try:
        from Components.Language import language
        language.addCallback(_limba_schimbata)
        _stare['legat'] = True
    except Exception:
        pass


def forteaza_limba(cod):
    """Pentru probe: limba data, fara Components.Language."""
    _stare['fortat'] = cod
    _stare['limba'] = None


def _limba_schimbata(*a):
    _stare['limba'] = None


def limba_enigma2():
    if _stare['fortat']:
        return _stare['fortat']
    try:
        from Components.Language import language
        return language.getLanguage() or ''
    except Exception:
        return ''


def cod_limba(text):
    cod = (text or '').replace('-', '_').split('_')[0].lower()
    return cod if cod in LIMBI else IMPLICIT


def _traducere():
    text_limba = limba_enigma2()
    # fara limba de la enigma2 (unelte, paznicul in afara interfetei): textul din cod, ca in 0.1.4
    cod = cod_limba(text_limba) if text_limba else ''
    if _stare['limba'] != cod:
        t = None
        if cod and _stare['domeniu'] and _stare['cale']:
            try:
                t = gettext.translation(_stare['domeniu'], _stare['cale'], languages=[cod], fallback=True)
            except Exception:
                t = None
        _stare['traducere'] = t
        _stare['limba'] = cod
    return _stare['traducere']


def N_(text):
    """Marcaj pentru xgettext (--keyword=N_): textul se traduce abia la afisare, cu _()."""
    return text


def _din_imagine(text):
    """Traducerea din catalogul imaginii (functia _ din builtins, pusa de Components.Language)."""
    try:
        import builtins
    except ImportError:               # Python 2.7
        import __builtin__ as builtins
    f = getattr(builtins, '_', None)
    if not callable(f):
        return text
    try:
        return f(text)
    except Exception:
        return text


def _plural_ro(unu, multe, n):
    """Regula romaneasca (msgid-urile sunt in romana), fara "de": 2 posturi, 20 posturi."""
    return unu if n == 1 else multe


def _forma(text, multe):
    """Forma aleasa, cu % care merge si cand forma pentru 1 n-are numarul (Components/HdsPlural.Forma, in imagine)."""
    try:
        from Components.HdsPlural import Forma
    except ImportError:
        return text
    return Forma(text, multe)


def ngettext(unu, multe, n):
    """Pluralul tradus. In imagine: catalogul imaginii, cu formele limbii alese (Components.HdsListeCabluTerestru);
    ca plugin: catalogul comun. Fara catalog, regula romaneasca."""
    if IN_IMAGINE and not _stare['fortat']:
        try:
            from Components.HdsListeCabluTerestru import ngettext as plural
            return plural(unu, multe, n)
        except Exception:
            return _plural_ro(unu, multe, n)
    try:
        t = _traducere()
        if t is not None:
            tradus = t.ngettext(unu, multe, n)
            if tradus not in (unu, multe):
                return _forma(tradus, multe)
    except Exception:
        pass
    return _plural_ro(unu, multe, n)


def _(text):
    if not text:
        return text   # gettext('') ar intoarce antetul catalogului
    if IN_IMAGINE and not _stare['fortat']:
        return _din_imagine(text)
    try:
        t = _traducere()
        return t.gettext(text) if t is not None else text
    except Exception:
        return text

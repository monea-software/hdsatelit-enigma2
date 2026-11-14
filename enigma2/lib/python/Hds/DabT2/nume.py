# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Numele aratate ale multiplexurilor din listele DAB+ si DVB-T2 din satelit, in limba receptorului. Facut de hdsatelit.com.

Listele (frecvente.json din imagine si cea de pe stb.hdsatelit.com) au numele scrise in romana: tara in paranteza la
capat („Dasto Semtel (Bosnia și Herțegovina)”, campul „tara” al feed-ului) si cateva nume cu cuvinte romanesti
(„KRRT Ucraina (criptat BISS)”). Numele aratat (marcajul „MUX DVB-T2: ...” din buchet, ecranele, pagina web):
  - un nume din FRAZE se traduce intreg;
  - altfel, tara din paranteza de la capat se inlocuieste cu numele ei tradus („Dasto Semtel (Bosna i Hercegovina)”);
    tara din mijlocul numelui nu se atinge („Oman TV” e numele postului);
  - restul ramane cum e scris (nume proprii: operatori, ansambluri).
Textele sunt msgid-uri ale catalogului imaginii (N_ aici, ca xgettext sa le vada). Un nume nou in lista de pe stb cu
cuvinte romanesti se adauga in FRAZE; o tara noua, in TARI (proba test_num_nume_limba_075 le cere pe toate).
"""
from .limba import N_, _

# numele tarilor din campul „tara” al listelor (romana, ca in HdsOperatoriSatelit.NUME_TARI si HdsLocuriDate)
TARI = (
    N_('Spania'), N_('Rusia'), N_('Ucraina'), N_('Cipru'), N_('Italia'), N_('Bosnia și Herțegovina'), N_('Oman'),
    N_('Germania'), N_('Grecia'), N_('Turcia'), N_('Polonia'), N_('Franța'), N_('Portugalia'), N_('Austria'),
    N_('Cehia'), N_('Slovacia'), N_('Ungaria'), N_('Serbia'), N_('Croația'), N_('Slovenia'), N_('Muntenegru'),
    N_('Macedonia de Nord'), N_('Albania'), N_('Bulgaria'), N_('România'), N_('Republica Moldova'),
    N_('Regatul Unit'), N_('Irlanda'), N_('Țările de Jos'), N_('Belgia'), N_('Danemarca'), N_('Norvegia'),
    N_('Suedia'), N_('Finlanda'), N_('Estonia'), N_('Letonia'), N_('Lituania'), N_('Georgia'),
    N_('Armenia'), N_('Azerbaidjan'), N_('Israel'), N_('Egipt'), N_('Maroc'), N_('Algeria'), N_('Tunisia'),
    N_('Arabia Saudită'), N_('Emiratele Arabe Unite'), N_('Irak'), N_('Liban'),
)

# numele intregi din liste care au cuvinte romanesti in afara tarii
FRAZE = (
    N_('MX-7 Ucraina (clar): doar DSNS Informed'),
    N_('KRRT Ucraina (criptat BISS)'),
    N_('RSCC Crimeea'),
)
_FRAZE = frozenset(FRAZE)


def _u(text):
    """Text unicode (pe 2.7 octetii UTF-8 ai traducerii devin unicode)."""
    if text is None:
        return u''
    if isinstance(text, bytes):
        return text.decode('utf-8', 'replace')
    return text if isinstance(text, type(u'')) else u'%s' % (text,)


def tara(text):
    """Numele tarii (romana, cum e in lista) in limba receptorului; textul insusi fara traducere."""
    t = _u(text).strip()
    return _u(_(t)) if t else t


def nume_feed(feed):
    """Numele aratat al unui feed din lista (dictul din frecvente.json), in limba receptorului."""
    nume = _u(feed.get('nume') or feed.get('id') or '').strip()
    if nume in _FRAZE:
        return _u(_(nume))
    t = _u(feed.get('tara') or '').strip()
    if t:
        sufix = u' (%s)' % t
        if nume.endswith(sufix):
            return u'%s (%s)' % (nume[:-len(sufix)], tara(t))
    return nume

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Textele din tabelele DVB (nume de serviciu si de furnizor din SDT). Facut de hdsatelit.com.

Un singur loc pentru detector.py si releul T2. Fara alte importuri: se incarca si ca modul simplu (releele si
detectorul pun comun/ in sys.path) si ca parte din pachetul pluginului.

EN 300 468 anexa A: primul octet alege tabela de caractere. Fara selector: tabela implicita (latin, aproximata
cu latin-1). 0x01-0x0B = ISO 8859-5..15; 0x10 + 2 octeti = ISO 8859-N; 0x11 = UCS-2; 0x15 = UTF-8.
Codurile de control 0x80-0x9F (de ex. 0x86/0x87, accentuare) se scot.

Etichetele DAB (FIG 1, numele ansamblului si al posturilor: EN 300 401, 16 octeti) au alt sistem: primii 4 biti ai
FIG-ului aleg setul de caractere (ETSI TS 101 756, tabelul 1): 0 = setul EBU Latin complet (TS 101 756, anexa C),
6 = UCS-2 big endian, 15 = UTF-8; un set necunoscut se citeste ca EBU Latin. In EBU Latin literele accentuate stau la
alte coduri decat in Latin-1 (0x82 = é, 0x91 = ä, 0x99 = ü, 0xD9 = Ü), iar 0x24 e ł, nu $ (dolarul e la 0xAB).
Codurile de control din eticheta (0x00 nul, 0x0A rand nou preferat, 0x0B sfarsitul titlului, 0x1F despartire de
cuvant preferata) se scot.
Merge pe Python 3 si pe Python 2.7 (acolo octetii se citesc prin bytearray, ca indexul sa dea numere).
"""

_PY2 = bytes is str
_TABELE_DVB = {0x01: 'iso8859_5', 0x02: 'iso8859_6', 0x03: 'iso8859_7', 0x04: 'iso8859_8', 0x05: 'iso8859_9',
               0x06: 'iso8859_10', 0x07: 'iso8859_11', 0x09: 'iso8859_13', 0x0A: 'iso8859_14', 0x0B: 'iso8859_15'}


def text_dvb(b):
    if not b:
        return ''
    if _PY2 and type(b) is not bytearray:
        b = bytearray(b)                  # pe 2.7 b[0] pe str ar fi un sir si comparatia cu 0x20 ar minti tacut
    cod = 'latin-1'
    x = b[0]
    if x < 0x20:
        if x in _TABELE_DVB:
            cod, b = _TABELE_DVB[x], b[1:]
        elif x == 0x10 and len(b) >= 3:
            n = (b[1] << 8) | b[2]
            cod, b = ('iso8859_%d' % n) if 1 <= n <= 15 and n != 12 else 'latin-1', b[3:]
        elif x == 0x11:
            cod, b = 'utf-16-be', b[1:]
        elif x == 0x15:
            cod, b = 'utf-8', b[1:]
        else:
            b = b[1:]
    try:
        t = bytes(b).decode(cod, 'replace')
    except LookupError:
        t = bytes(b).decode('latin-1', 'replace')
    return ''.join(ch for ch in t if not 0x80 <= ord(ch) <= 0x9F).strip()


# EBU Latin (ETSI TS 101 756, anexa C): codul Unicode al fiecarui octet care nu e acelasi ca in ASCII. Randurile
# 0x00-0x1F si 0x7B-0xFF sunt intregi; in 0x20-0x7A numai patru octeti difera de ASCII.
_EBU_RANDURI = {
    0x00: (0, 0x118, 0x12E, 0x172, 0x102, 0x116, 0x10E, 0x218, 0x21A, 0x10A, 0, 0, 0x120, 0x139, 0x17B, 0x143),
    0x10: (0x105, 0x119, 0x12F, 0x173, 0x103, 0x117, 0x10F, 0x219, 0x21B, 0x10B, 0x147, 0x11A, 0x121, 0x13A, 0x17C, 0),
    0x80: (0xE1, 0xE0, 0xE9, 0xE8, 0xED, 0xEC, 0xF3, 0xF2, 0xFA, 0xF9, 0xD1, 0xC7, 0x15E, 0xDF, 0xA1, 0x178),
    0x90: (0xE2, 0xE4, 0xEA, 0xEB, 0xEE, 0xEF, 0xF4, 0xF6, 0xFB, 0xFC, 0xF1, 0xE7, 0x15F, 0x11F, 0x131, 0xFF),
    0xA0: (0x136, 0x145, 0xA9, 0x122, 0x11E, 0x11B, 0x148, 0x151, 0x150, 0x20AC, 0xA3, 0x24, 0x100, 0x112, 0x12A, 0x16A),
    0xB0: (0x137, 0x146, 0x13B, 0x123, 0x13C, 0x130, 0x144, 0x171, 0x170, 0xBF, 0x13E, 0xB0, 0x101, 0x113, 0x12B, 0x16B),
    0xC0: (0xC1, 0xC0, 0xC9, 0xC8, 0xCD, 0xCC, 0xD3, 0xD2, 0xDA, 0xD9, 0x158, 0x10C, 0x160, 0x17D, 0xD0, 0x13F),
    0xD0: (0xC2, 0xC4, 0xCA, 0xCB, 0xCE, 0xCF, 0xD4, 0xD6, 0xDB, 0xDC, 0x159, 0x10D, 0x161, 0x17E, 0x111, 0x140),
    0xE0: (0xC3, 0xC5, 0xC6, 0x152, 0x177, 0xDD, 0xD5, 0xD8, 0xDE, 0x14A, 0x154, 0x106, 0x15A, 0x179, 0x164, 0xF0),
    0xF0: (0xE3, 0xE5, 0xE6, 0x153, 0x175, 0xFD, 0xF5, 0xF8, 0xFE, 0x14B, 0x155, 0x107, 0x15B, 0x17A, 0x165, 0x127),
}
_EBU_ALTE = {0x24: 0x142, 0x5C: 0x16E, 0x5E: 0x141, 0x60: 0x104, 0x7B: 0xAB, 0x7C: 0x16F, 0x7D: 0xBB, 0x7E: 0x13D,
             0x7F: 0x126}
_CONTROL_DAB = (0x00, 0x0A, 0x0B, 0x1F)


def _tabel_ebu():
    uchr = unichr if _PY2 else chr          # noqa: F821  (unichr exista numai pe 2.7)
    rez = []
    for x in range(256):
        rand = _EBU_RANDURI.get(x & 0xF0)
        if x in _CONTROL_DAB:
            rez.append(u'')
        elif rand is not None:
            rez.append(uchr(rand[x & 0x0F]))
        else:
            rez.append(uchr(_EBU_ALTE.get(x, x)))
    return tuple(rez)


_EBU = _tabel_ebu()
SET_EBU_LATIN, SET_UCS2, SET_UTF8 = 0, 6, 15


def eticheta_dab(b, set_caractere=SET_EBU_LATIN):
    """Eticheta unei FIG 1 (16 octeti) -> text, dupa setul de caractere din FIG (fig[0] >> 4). Fara spatiile si
    nulurile de umplutura de la capete."""
    if not b:
        return u''
    if _PY2 and type(b) is not bytearray:
        b = bytearray(b)
    if set_caractere in (SET_UTF8, SET_UCS2):
        t = bytes(b).decode('utf-8' if set_caractere == SET_UTF8 else 'utf-16-be', 'replace')
        return t.replace(u'\x00', u'').strip()
    return u''.join(_EBU[x] for x in b).strip()

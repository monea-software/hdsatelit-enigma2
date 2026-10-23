# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Decodor DAB/DAB+ din EDI (ETSI TS 102 693, TS 102 821, EN 300 401, TS 102 563). Facut de hdsatelit.com.
Varianta pentru receptor (ARM): fara bucle bit cu bit pe drumul fierbinte, CRC in C (binascii) sau pe tabela,
LOAS construit cu un singur int mare, reasamblare PF cu marime fixa. Iesirea e identica octet cu octet cu
varianta de pe calculator (receptor/dab/dab_edi.py); proba: probe/proba_dab_edi.py.

Interfata (fixa, din contract):
  cadre_eti(pachete_edi) -> iterator (fic: bytes, mst: {subcanal: bytes})
  Ansamblu().fib(fib32); .fic(fic); .nume, .eid, .posturi {sid: {'nume','subch','ascty'}}
  DABPlus().adauga(mst_subcanal) -> [cadre LOAS]

Linie de comanda (pe calculator, pentru verificari):
  python dab_edi.py lista   fisier.edi
  python dab_edi.py extrage fisier.edi SID iesire.aac|iesire.mp2
Fisierul .edi: pachete UDP cu lungimea pe 4 octeti in fata.
Merge pe Python 3 si pe Python 2.7 (imagini vechi). Pe Python 3 numele de mai jos sunt chiar functiile standard
(int.from_bytes, memoryview, b''.join), deci drumul datelor e acelasi; pe 2.7 octetii se tin in bytearray, ca indexul
sa dea numere (str[i] da un sir de 1 caracter si `p[0] == 0x50` ar fi fals tacut)."""
from __future__ import division

import collections
import operator
import struct
import sys

if sys.version_info[0] < 3:                      # Python 2.7
    import binascii as _binascii
    _PY2 = True
    _B = bytearray
    _GOL = bytearray()                           # b''.join nu primeste bytearray pe 2.7

    def _felie(x):
        return x                                 # memoryview pe 2.7 da siruri la index si bytes() pe el da text

    def _din_octeti(b, _ordine='big'):
        return int(_binascii.hexlify(b) or b'0', 16)

    def _in_octeti(v, n, _ordine='big'):
        return _binascii.unhexlify('%0*x' % (2 * n, v)) if n else b''

    def _functie(m):
        return getattr(m, '__func__', m)         # metodele nelegate de pe 2.7 sunt obiecte noi la fiecare acces
    # „cel mai vechi pleaca" (next(iter(dict))) cere ordinea inserarii: dict o are pe 3.7+, pe 2.7 doar OrderedDict
    _DictOrdonat = collections.OrderedDict
else:
    _PY2 = False
    _B = bytes
    _GOL = b''
    _felie = memoryview
    _din_octeti = int.from_bytes                 # _din_octeti(x, 'big') = int.from_bytes(x, 'big')
    _in_octeti = int.to_bytes                    # _in_octeti(v, n, 'big') = v.to_bytes(n, 'big')

    def _functie(m):
        return m
    _DictOrdonat = dict

# ---------------------------------------------------------------- CRC
_T1021 = []
for _i in range(256):
    _c = _i << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x1021) & 0xFFFF if _c & 0x8000 else (_c << 1) & 0xFFFF
    _T1021.append(_c)


def crc16_tabela(data, init=0xFFFF):
    """CRC-CCITT (x^16+x^12+x^5+1), pe tabela; rezerva cand binascii lipseste."""
    c = init
    t = _T1021
    for b in data:
        c = ((c << 8) & 0xFFFF) ^ t[(c >> 8) ^ b]
    return c


if _PY2:
    _crc16_tabela_3 = crc16_tabela

    def crc16_tabela(data, init=0xFFFF):         # noqa: F811
        return _crc16_tabela_3(data if type(data) is bytearray else bytearray(data), init)


try:
    from binascii import crc_hqx as _crc_hqx     # acelasi polinom, fara reflexie, calculat in C

    def crc16_ccitt(data, init=0xFFFF):
        return _crc_hqx(data, init)
    CRC_IN_C = True
except ImportError:                              # imagine fara binascii
    crc16_ccitt = crc16_tabela
    _crc_hqx = crc16_tabela
    CRC_IN_C = False

# CRC-ul calculat peste date + CRC-ul lor complementat (big endian) da mereu 0x1D0F, si numai atunci: se verifica
# dintr-un singur apel, fara felie separata si fara a citi cei doi octeti in Python
CRC_REST = 0x1D0F

_H = struct.Struct('>H')
_I = struct.Struct('>I')
_TAG = struct.Struct('>4sI')
_TAG_INT = struct.Struct('>II')                  # numele tagului ca intreg (fara obiect bytes nou pe tag)
_PF = struct.Struct('>2xHBHBHH')                 # pseq, findex(8+16), fcount(8+16), fec|addr|plen


def crc_ok_ccitt(data):
    """FIB, AU, AF: CRC-CCITT, init FFFF, complementat, pe ultimii 2 octeti."""
    n = len(data)
    if n <= 2:
        return False
    return _crc_hqx(data, 0xFFFF) == CRC_REST


_FIRE = []
for _i in range(256):
    _c = _i << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x782F) & 0xFFFF if _c & 0x8000 else (_c << 1) & 0xFFFF
    _FIRE.append(_c)


def firecode_ok(sf):
    """TS 102 563: G(x) = x^16+x^14+x^13+x^12+x^11+x^5+x^3+x^2+x+1, peste octetii 2..10."""
    if len(sf) < 11 or not any(sf[:11]):
        return False
    c = 0
    t = _FIRE
    for b in sf[2:11]:
        c = ((c << 8) & 0xFFFF) ^ t[(c >> 8) ^ b]
    return c == ((sf[0] << 8) | sf[1])


# ---------------------------------------------------------------- EDI: PF -> AF -> TAG
class PFT(object):
    """Reasamblarea fragmentelor PF (TS 102 821). Tine cel mult MAX pachete AF in lucru; cel mai vechi pleaca."""
    MAX = 8

    def __init__(self):
        self.buc = _DictOrdonat()     # pseq -> [fcount, gasite, parti], in ordinea sosirii
        self.rele = 0                 # PF respinse (antet, CRC, marimi)
        self.pierdute = 0             # AF incomplete aruncate

    def adauga(self, p):
        n = len(p)
        if n < 14 or p[0] != 0x50 or p[1] != 0x46:
            return None
        pseq, fi1, fi2, fc1, fc2, fl = _PF.unpack_from(p)
        findex = (fi1 << 16) | fi2
        fcount = (fc1 << 16) | fc2
        fec = fl >> 15
        plen = fl & 0x3FFF
        o = 12
        rsk = rsz = 0
        if fec:
            if n < 16:
                self.rele += 1
                return None
            rsk, rsz = p[12], p[13]
            o = 14
        if (fl >> 14) & 1:
            o += 4
        if n < o + 2 + plen or fcount == 0 or findex >= fcount:
            self.rele += 1
            return None
        if _crc_hqx(p[:o + 2], 0xFFFF) != CRC_REST:
            self.rele += 1
            return None
        o += 2
        buc = self.buc
        if fcount == 1 and not fec:
            # AF intr-un singur fragment: fara lista de parti; tabelul se atinge doar ca in drumul lung
            if pseq in buc:
                del buc[pseq]
            elif len(buc) >= self.MAX:
                del buc[next(iter(buc))]
                self.pierdute += 1
            return p[o:o + plen]
        f = buc.get(pseq)
        if f is None or f[0] != fcount:
            if f is None and len(buc) >= self.MAX:
                del buc[next(iter(buc))]
                self.pierdute += 1
            f = buc[pseq] = [fcount, 0, [None] * fcount]
        parti = f[2]
        if parti[findex] is None:
            f[1] += 1
        parti[findex] = p[o:o + plen]
        if f[1] < fcount:
            return None
        del buc[pseq]
        if fec and fcount > 1:
            # Cu RS, octetii pachetului protejat sunt imprastiati pe fragmente: octetul j sta in fragmentul j mod Fcount
            # (dovedit pe 7E 12567,8 V, NDR 239.229.96.x si 239.128.57/58.20: 893 de AF din 893 cu CRC bun; cu
            # fragmentele lipite la rand CRC-ul nu iesea niciodata).
            total = sum(len(x) for x in parti)
            imprastiat = bytearray(total)
            try:
                for i in range(fcount):
                    imprastiat[i::fcount] = parti[i]
            except ValueError:            # marimi de fragmente care nu se potrivesc impartirii
                self.rele += 1
                return None
            date = _B(imprastiat)
        else:
            date = parti[0] if fcount == 1 else _GOL.join(parti)
        if fec:                       # prin IP nu vin erori: se pastreaza doar octetii de date din fiecare bloc RS
            if rsk == 0:
                self.rele += 1
                return None
            pas = rsk + 48
            date = _GOL.join([date[i:i + rsk] for i in range(0, len(date), pas)])
            if rsz:
                date = date[:len(date) - rsz]
        return date


def af_taguri(af):
    """AF -> {nume_tag: valoare}; primul tag cu un nume castiga. Nu verifica CRC (ca varianta veche)."""
    n = len(af)
    if n < 10 or af[0] != 0x41 or af[1] != 0x46:
        return None
    lung = _I.unpack_from(af, 2)[0]
    capat = min(n, 10 + lung)
    mv = _felie(af)
    t = {}
    o = 10
    while o + 8 <= capat:
        nume, biti = _TAG.unpack_from(af, o)
        a = o + 8
        o = a + ((biti + 7) >> 3)
        if nume not in t:
            t[nume] = bytes(mv[a:min(o, capat)])
    return t


class DecodorEdi(object):
    """Pachete EDI (PF sau AF) -> (fic, {subch: mst}); contoare pentru /stare."""

    def __init__(self, verifica_crc_af=True):
        self.pft = PFT()
        self.verifica_crc_af = verifica_crc_af
        self.af_bune = 0
        self.af_rele = 0
        self._sablon = None

    def adauga(self, p):
        n = len(p)
        if n < 2:
            return None
        if p[0] == 0x50 and p[1] == 0x46:
            af = self.pft.adauga(p)
            if not af:
                return None
        elif p[0] == 0x41 and p[1] == 0x46:
            af = p
        else:
            return None
        return self.cadru(af)

    def cadru(self, af):
        n = len(af)
        if n < 10 or af[0] != 0x41 or af[1] != 0x46:
            self.af_rele += 1
            return None
        lung = _I.unpack_from(af, 2)[0]
        capat = 10 + lung
        if af[8] & 0x80 and self.verifica_crc_af:
            if n < capat + 2 or _crc_hqx(af if n == capat + 2 else memoryview(af)[:capat + 2], 0xFFFF) != CRC_REST:
                self.af_rele += 1
                return None
        if capat > n:
            capat = n
        sab = self._sablon
        if sab is not None and sab[0] == capat and sab[1](af) == sab[2]:
            # aceleasi antete de tag in aceleasi locuri ca la cadrul trecut: pozitiile se iau din sablon (in C)
            deti_a, deti_b, date, chei = sab[3], sab[4], sab[5], sab[6]
            if len(chei) > 1:
                mst = dict(zip(chei, date(af)))
            else:
                mst = {chei[0]: date(af)} if chei else {}
        else:
            deti_a, deti_b, mst = self._taguri(af, capat)
        if deti_a < 0 or deti_b - deti_a < 4:
            self.af_rele += 1
            return None
        d0 = af[deti_a]
        o = deti_a + 6 + (8 if d0 & 0x80 else 0)
        if d0 & 0x40:
            ficlen = 128 if (af[deti_a + 3] >> 6) == 3 else 96
            e = o + ficlen
            fic = af[o:e if e < deti_b else deti_b] if o < deti_b else b''
        else:
            fic = b''
        self.af_bune += 1
        return fic, mst

    def _taguri(self, af, capat):
        """Parcurge tagurile (TS 102 693) si tine minte sablonul: unde incep antetele de tag si, pentru 'estN', primul
        octet de date (SCID). Cadrul urmator cu exact aceiasi octeti in acele locuri are aceleasi pozitii."""
        o = 10
        deti_a = -1
        deti_b = 0
        mst = {}
        vazute = 0                                   # indicii 'estN' deja luati, ca biti intr-un intreg
        un_tag = _TAG_INT.unpack_from
        verif = [slice(0, 2), slice(8, 10)]          # 'AF', AR si PT (SEQ se schimba la fiecare cadru)
        felii = []
        chei = []
        while o + 8 <= capat:
            nume, biti = un_tag(af, o)
            a = o + 8
            t = o
            o = a + ((biti + 7) >> 3)
            if nume >> 8 == 0x657374:                # 'est' + index: primul tag cu un nume castiga
                verif.append(slice(t, a + 1))
                bit = 1 << (nume & 0xFF)
                if vazute & bit:
                    continue
                vazute |= bit
                b = o if o < capat else capat
                if b - a > 3:
                    mst[af[a] >> 2] = af[a + 3:b]
                    chei.append(af[a] >> 2)
                    felii.append(slice(a + 3, b))
            else:
                verif.append(slice(t, a))
                if nume == 0x64657469 and deti_a < 0:      # 'deti'
                    deti_a, deti_b = a, (o if o < capat else capat)
        if deti_a < 0 or len(verif) > 256:
            self._sablon = None
        else:
            g = operator.itemgetter(*verif)
            self._sablon = (capat, g, g(af), deti_a, deti_b, operator.itemgetter(*felii) if felii else None, tuple(chei))
        return deti_a, deti_b, mst


def cadre_eti(pachete, dec=None):
    """Din pachete EDI brute -> (fic, {subch: mst}) pentru fiecare cadru de 24 ms."""
    if dec is None:
        dec = DecodorEdi()
    if _functie(type(dec).adauga) is not _functie(DecodorEdi.adauga):     # decodor schimbat: se merge prin metoda lui
        ad = dec.adauga
        for p in pachete:
            r = ad(p)
            if r is not None:
                yield r
        return
    pf = dec.pft.adauga                                     # la fel ca DecodorEdi.adauga, fara un apel in plus
    cadru = dec.cadru
    for p in pachete:
        if len(p) < 2 or p[1] != 0x46:
            continue
        c = p[0]
        if c == 0x50:
            p = pf(p)
            if not p:
                continue
        elif c != 0x41:
            continue
        r = cadru(p)
        if r is not None:
            yield r


if _PY2:
    _cadre_eti_3 = cadre_eti

    def cadre_eti(pachete, dec=None):            # noqa: F811  (pachetele din surse sunt deja bytearray: fara copie)
        return _cadre_eti_3((p if type(p) is bytearray else bytearray(p) for p in pachete), dec)

    def _cu_bytearray(metoda):
        def f(self, p):
            return metoda(self, p if type(p) is bytearray else bytearray(p))
        f.__name__ = metoda.__name__
        return f

    # intrarile publice primesc si str (probe, apeluri directe); ce vine din cadre_eti e deja bytearray
    PFT.adauga = _cu_bytearray(PFT.__dict__['adauga'])
    DecodorEdi.cadru = _cu_bytearray(DecodorEdi.__dict__['cadru'])
    DecodorEdi.adauga = _cu_bytearray(DecodorEdi.__dict__['adauga'])
    _firecode_ok_3 = firecode_ok

    def firecode_ok(sf):                         # noqa: F811  (DABPlus da deja bytearray: fara copie)
        return _firecode_ok_3(sf if type(sf) is bytearray else bytearray(sf))


# ---------------------------------------------------------------- FIC
EBU = {0x8A: 'ș', 0x9A: 'š', 0xE0: 'à',
       # vazute in etichete reale (5W „M\x82tropolitain”; 7E „Allg\x91uDonauIller", „Oberbayern S\x99d"; 19.2E „S\xd9DWESTF", „W\xd9RZBURG")
       0x82: 'é', 0x91: 'ä', 0x99: 'ü', 0xD9: 'Ü'}


# pe 2.7 literalele de mai sus sunt octeti UTF-8, iar unicode.translate vrea unicode
_EBU_TABEL = dict((k, v.decode('utf-8') if isinstance(v, bytes) else v) for k, v in EBU.items())


def eticheta(b):
    # unele ansambluri (ERT, 39E) umplu cele 16 caractere cu 0x00 in loc de spatii: se taie si acestea.
    # latin-1 da exact chr(x) pentru fiecare octet; translate pune literele EBU; totul intr-un singur apel in C
    return bytes(b).decode('latin-1').translate(_EBU_TABEL).strip(' \x00')


class Ansamblu(object):
    """Starea ansamblului din FIG 0/2, 1/0, 1/1. FIB-urile deja aplicate fara efect se sar (tabel mic), iar un FIC
    intreg deja vazut fara nicio schimbare de atunci se sare dintr-o singura cautare (FIC-ul se repeta prin rotatia
    figurilor; cand ansamblul se schimba, ambele tabele se golesc si totul se decodeaza din nou)."""
    CACHE = 1024
    CACHE_FIC = 512

    def __init__(self):
        self.nume = ''
        self.eid = None
        self.posturi = {}          # sid -> {'nume', 'subch', 'ascty'}
        self.subcanale = {}        # subch -> kbit/s (din lungimea MST)
        self._stiute = set()
        self._fic_stiute = set()
        self.schimbari = 0         # creste la fiecare schimbare de stare (releul reface lista doar atunci)

    def fic(self, fic):
        if type(fic) is not bytes:
            fic = bytes(fic)
        st = self._fic_stiute
        if fic in st:
            return
        inainte = self.schimbari
        fib = self.fib
        for i in range(0, len(fic), 32):
            fib(fic[i:i + 32])
        if self.schimbari == inainte:            # la o schimbare fib() a golit deja tabelul
            if len(st) >= self.CACHE_FIC:
                st.clear()
            st.add(fic)

    def fib(self, fib):
        if type(fib) is not bytes:
            fib = bytes(fib)
        st = self._stiute
        if fib in st:
            return
        inainte = self.schimbari
        if crc_ok_ccitt(fib):
            self._aplica(fib)
        if self.schimbari != inainte:
            st.clear()
            self._fic_stiute.clear()
        elif len(st) >= self.CACHE:
            st.clear()
        st.add(fib)

    def _post(self, sid):
        p = self.posturi.get(sid)
        if p is None:
            p = self.posturi[sid] = {'nume': '', 'subch': None, 'ascty': None}
            self.schimbari += 1
        return p

    def _aplica(self, fib):
        d = _B(fib[:30])                         # pe 3 bytes(bytes) e acelasi obiect; pe 2.7 bytearray (index = numar)
        o = 0
        while o < 30 and d[o] != 0xFF:
            tip, lung = d[o] >> 5, d[o] & 0x1F
            fig = d[o + 1:o + 1 + lung]
            o += 1 + lung
            if not fig:
                continue
            if tip == 0:
                pd, ext = (fig[0] >> 5) & 1, fig[0] & 0x1F
                if ext == 2 and pd == 0:
                    i = 1
                    lf = len(fig)
                    while i + 3 <= lf:
                        sid = (fig[i] << 8) | fig[i + 1]
                        nsc = fig[i + 2] & 0x0F
                        i += 3
                        for _ in range(nsc):
                            if i + 2 > lf:
                                break
                            if fig[i] >> 6 == 0 and fig[i + 1] & 0x02:      # TMId 0, componenta primara
                                ascty = fig[i] & 0x3F
                                subch = fig[i + 1] >> 2
                                p = self._post(sid)
                                if p['subch'] != subch or p['ascty'] != ascty:
                                    p['subch'], p['ascty'] = subch, ascty
                                    self.schimbari += 1
                            i += 2
            elif tip == 1:
                ext = fig[0] & 0x07
                if ext == 0 and len(fig) >= 19:
                    eid = (fig[1] << 8) | fig[2]
                    nume = eticheta(fig[3:19])
                    if eid != self.eid or nume != self.nume:
                        self.eid, self.nume = eid, nume
                        self.schimbari += 1
                elif ext == 1 and len(fig) >= 19:
                    sid = (fig[1] << 8) | fig[2]
                    nume = eticheta(fig[3:19])
                    p = self._post(sid)
                    if p['nume'] != nume:
                        p['nume'] = nume
                        self.schimbari += 1

    def complet(self):
        return self.nume and self.posturi and all(p['nume'] and p['subch'] is not None for p in list(self.posturi.values()))


# ---------------------------------------------------------------- DAB+ superframe -> AU -> LOAS
FREC = {32000: 5, 16000: 8, 48000: 3, 24000: 6}


class Biti(object):
    """Scriere pe biti (folosita doar la antete mici, nu pe date)."""

    def __init__(self):
        self.v = 0
        self.n = 0
        self.o = bytearray()

    def pune(self, val, n):
        for i in range(n - 1, -1, -1):
            self.v = (self.v << 1) | ((val >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.o.append(self.v)
                self.v = 0
                self.n = 0

    def gata(self):
        if self.n:
            self.pune(0, 8 - self.n)
        return bytes(self.o)


def _antet_latm(rata_core, canale):
    """Primii 45 de biti ai AudioMuxElement (StreamMuxConfig inclus), ca intreg."""
    v = 0
    for val, n in ((0, 1), (0, 1), (1, 1), (0, 6), (0, 4), (0, 3),     # useSameStreamMux, audioMuxVersion,
                   (2, 5), (FREC[rata_core], 4), (canale, 4),          # allStreamsSameTimeFraming, subframes
                   (1, 1), (0, 1), (0, 1),                             # AAC-LC, 960 (frameLengthFlag=1)
                   (0, 3), (0xFF, 8),                                  # frameLengthType=0, bufferFullness
                   (0, 1), (0, 1)):                                    # otherDataPresent, crcCheckPresent
        v = (v << n) | (val & ((1 << n) - 1))
    return v


_ANTETE = {}


def loas(au, rata_core, canale):
    """AU AAC -> cadru LOAS (AudioSyncStream). Antetul LATM are 45 de biti, deci AU nu cade pe octet intreg:
    se lipeste o singura data printr-un int mare (shift), fara bucla pe octeti."""
    h = _ANTETE.get((rata_core, canale))
    if h is None:
        h = _ANTETE[(rata_core, canale)] = _antet_latm(rata_core, canale)
    n = len(au)
    k, r = divmod(n, 255)
    m = k + 1 + n                                   # PayloadLengthInfo + payload, in octeti
    lung = m + 6                                    # 45 + 8m biti, completat la octet (+3)
    lungime = (((1 << (8 * k)) - 1) << 8) | r       # k x 0xFF, apoi restul
    v = (((((0x56E0 | ((lung >> 8) & 0x1F)) << 8) | (lung & 0xFF)) << 45 | h) << (8 * (k + 1))) | lungime
    v = ((v << (8 * n)) | _din_octeti(au, 'big')) << 3
    return _in_octeti(v, lung + 3, 'big')


_NUM_AU = {(0, 0): 4, (0, 1): 2, (1, 0): 6, (1, 1): 3}
_START_AU = {2: 5, 3: 6, 4: 8, 6: 11}


class DABPlus(object):
    def __init__(self):
        self.cadre = collections.deque()
        self.aliniat = False
        self.au_bune = self.au_rele = 0
        self.info = None
        self._cheie_info = None
        self.superframes = 0             # superframe-uri gasite (firecode bun), si cu toate AU stricate
        self.indici = []                 # pozitiile in superframe ale AU din ultima iesire (pentru timpul lor)

    def adauga(self, mst):
        c = self.cadre
        c.append(mst)
        if len(c) < 5:
            return []
        sf = _GOL.join(c)
        if not firecode_ok(sf):
            c.popleft()                  # cauta inceputul superframe-ului, cadru cu cadru
            return []
        c.clear()
        self.superframes += 1
        s = len(sf) // 120
        capat = s * 110
        b2 = sf[2]
        dac, sbr, chm, ps = b2 >> 6 & 1, b2 >> 5 & 1, b2 >> 4 & 1, b2 >> 3 & 1
        num = _NUM_AU[(dac, sbr)]
        st = [_START_AU[num]]
        nb = (12 * (num - 1) + 7) // 8
        biti = _din_octeti(sf[3:3 + nb] or b'\0', 'big')
        tot = nb * 8
        for i in range(num - 1):
            st.append((biti >> (tot - 12 * (i + 1))) & 0xFFF)
        st.append(capat)                 # ultima AU se termina la capatul datelor (fara paritatea RS)
        rata = (48000 if dac else 32000) // (2 if sbr else 1)
        cheie = (dac, sbr, chm, ps, num)
        if cheie != self._cheie_info:
            self._cheie_info = cheie
            self.info = {'rata_iesire': 48000 if dac else 32000, 'sbr': sbr, 'ps': ps, 'stereo': chm or ps, 'au_pe_superframe': num}
        mv = memoryview(sf)
        canale = 2 if chm else 1
        iesire = []
        indici = self.indici = []
        for i in range(num):
            a, b = st[i], st[i + 1]
            au = mv[a:b]
            la = len(au)
            if b <= a or la <= 2 or _crc_hqx(au, 0xFFFF) != CRC_REST:
                self.au_rele += 1
                continue
            self.au_bune += 1
            indici.append(i)
            iesire.append(loas(au[:la - 2], rata, canale))
        return iesire


# ---------------------------------------------------------------- sunetul unui post intr-un TS (redare prin placa)
_T32 = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _T32.append(_c)


def crc32_mpeg(date):
    """CRC-32 MPEG-2 (polinom 0x04C11DB7, pornire 0xFFFFFFFF, fara inversare): sfarsitul sectiunilor PSI."""
    c = 0xFFFFFFFF
    for b in bytearray(date):
        c = ((c << 8) & 0xFFFFFFFF) ^ _T32[((c >> 24) ^ b) & 0xFF]
    return c


class TsAudio(object):
    """Cadrele de sunet ale unui post (LOAS la DAB+, MP2 la DAB) intr-un TS cu un singur program, pentru redarea prin
    demultiplexorul si decodorul placii (referinta tip 1 cu cale http, imaginea HDSatelit): PAT cu programul = SID-ul
    postului, PMT cu un singur flux (stream_type 0x11 = AAC in LATM/LOAS, 0x03 = MPEG audio), un PES pe cadru cu PTS,
    PCR pe PID-ul sunetului (PCR_INAINTE_90K inaintea PTS-ului). PAT si PMT se repeta la TABELE_90K; ultimul pachet
    al unui PES se completeaza cu umplutura in campul de adaptare. Contorii de continuitate sunt ai fluxului: un client
    care intra din mers vede un salt, ca la orice canal. pachete([(cadru, pts_90k), ...]) -> octetii TS."""
    PID_PMT = 0x100
    PID_SUNET = 0x101
    TABELE_90K = 22500                # 250 ms
    PCR_INAINTE_90K = 45000           # 0,5 s: cat tine decodorul in memorie inainte de redare
    PTS_START = 90000
    CIF_90K = 2160                    # 24 ms, un cadru CIF (DAB, MP2)
    MASCA_33 = (1 << 33) - 1

    def __init__(self, sid, aac=True, tsid=1):
        self.sid = (int(sid) & 0xFFFF) or 1
        self.tip = 0x11 if aac else 0x03
        self.cc = {0: 0, self.PID_PMT: 0, self.PID_SUNET: 0}
        self._tabele_la = None
        self._cif = 0
        self._pat = self._sectiune(0x00, tsid & 0xFFFF, bytearray(struct.pack('>HH', self.sid, 0xE000 | self.PID_PMT)))
        pmt = bytearray(struct.pack('>HH', 0xE000 | self.PID_SUNET, 0xF000))
        pmt += bytearray(struct.pack('>BHH', self.tip, 0xE000 | self.PID_SUNET, 0xF000))
        self._pmt = self._sectiune(0x02, self.sid, pmt)
        self.pes = 0

    @staticmethod
    def _sectiune(tid, ext, corp):
        lung = 5 + len(corp) + 4
        s = bytearray(struct.pack('>BHHBBB', tid, 0xB000 | lung, ext, 0xC1, 0, 0)) + corp
        return s + bytearray(struct.pack('>I', crc32_mpeg(s)))

    def _cc(self, pid):
        c = self.cc[pid]
        self.cc[pid] = (c + 1) & 15
        return c

    def _psi(self, pid, sectiune):
        p = bytearray([0x47, 0x40 | (pid >> 8), pid & 0xFF, 0x10 | self._cc(pid), 0]) + sectiune
        return p + bytearray(b'\xff' * (188 - len(p)))

    @staticmethod
    def _pts(v):
        return bytearray([0x21 | ((v >> 29) & 0x0E), (v >> 22) & 0xFF, ((v >> 14) & 0xFE) | 1, (v >> 7) & 0xFF,
                          ((v << 1) & 0xFE) | 1])

    def _pcr(self, v):
        v &= self.MASCA_33
        return bytearray([(v >> 25) & 0xFF, (v >> 17) & 0xFF, (v >> 9) & 0xFF, (v >> 1) & 0xFF,
                          ((v & 1) << 7) | 0x7E, 0])

    def _pes(self, cadru, pts):
        cadru = bytearray(cadru)
        lung = 8 + len(cadru)
        if lung > 0xFFFF:
            lung = 0
        date = bytearray([0, 0, 1, 0xC0, lung >> 8, lung & 0xFF, 0x80, 0x80, 5]) + self._pts(pts) + cadru
        pid = self.PID_SUNET
        iesire = bytearray()
        poz, primul = 0, True
        while poz < len(date):
            af = bytearray([7, 0x10]) + self._pcr(pts - self.PCR_INAINTE_90K) if primul else None
            loc = 184 - (len(af) if af is not None else 0)
            bucata = date[poz:poz + loc]
            lips = loc - len(bucata)
            if lips and af is None:
                af = bytearray([lips - 1]) + (bytearray([0]) + bytearray(b'\xff' * (lips - 2)) if lips > 1 else bytearray())
            elif lips:
                af = bytearray([af[0] + lips]) + af[1:] + bytearray(b'\xff' * lips)
            iesire += bytearray([0x47, (0x40 if primul else 0) | (pid >> 8), pid & 0xFF,
                                 (0x30 if af is not None else 0x10) | self._cc(pid)])
            if af is not None:
                iesire += af
            iesire += bucata
            poz += len(bucata)
            primul = False
        return iesire

    def pachete(self, cadre):
        iesire = bytearray()
        for cadru, pts in cadre:
            pts &= self.MASCA_33
            if self._tabele_la is None or (pts - self._tabele_la) & self.MASCA_33 >= self.TABELE_90K:
                self._tabele_la = pts
                iesire += self._psi(0, self._pat) + self._psi(self.PID_PMT, self._pmt)
            iesire += self._pes(cadru, pts)
            self.pes += 1
        return bytes(iesire)

    def cif(self, cadru):
        """DAB (MP2): un cadru CIF de 24 ms, cu PTS-ul lui (numarat de la primul cadru vazut de acest TS)."""
        pts = self.PTS_START + self._cif * self.CIF_90K
        self._cif += 1
        return self.pachete([(cadru, pts)])


def cadre_cu_pts(d, iesire):
    """DABPlus dupa adauga(): cadrele LOAS iesite, fiecare cu PTS-ul lui in 90 kHz. Un superframe tine 120 ms si se
    imparte egal la AU; PTS-ul vine din numarul superframe-ului si pozitia AU in el, deci un superframe sau o AU
    stricata (sarita) lasa gol in timp si nu muta ce urmeaza. -> [(cadru, pts)]"""
    if not iesire or not d.info:
        return []
    pas = 10800 // d.info['au_pe_superframe']
    baza = TsAudio.PTS_START + (d.superframes - 1) * 10800
    return [(cadru, baza + (d.indici[k] if k < len(d.indici) else k) * pas) for k, cadru in enumerate(iesire)]


# ---------------------------------------------------------------- unelte
def pachete_din_fisier(f):
    with open(f, 'rb') as fis:
        d = fis.read()
    o = 0
    while o + 4 <= len(d):
        n = _I.unpack_from(d, o)[0]
        yield d[o + 4:o + 4 + n]
        o += 4 + n


def citeste_ansamblul(sursa, max_cadre=2500):
    a = Ansamblu()
    lung = collections.defaultdict(list)
    n = 0
    for fic, mst in sursa:
        a.fic(fic)
        for k, v in mst.items():
            lung[k].append(len(v))
        n += 1
        if (a.complet() and n > 250) or n >= max_cadre:
            break
    a.subcanale = {k: round(sum(v) / len(v) * 8 / 24) for k, v in lung.items()}
    return a, n


def tipareste(a, n):
    print('Ansamblu: %s (EId %04X), %d cadre citite (%.1f s)' % (a.nume, a.eid or 0, n, n * 0.024))
    for sid, p in sorted(a.posturi.items(), key=lambda x: x[1]['nume']):
        fel = 'DAB+' if p['ascty'] == 63 else ('DAB (MP2)' if p['ascty'] == 0 else 'tip %s' % p['ascty'])
        print('  %04X  %-16s  %-9s subcanal %-3s %s kbit/s' % (sid, p['nume'], fel, p['subch'], a.subcanale.get(p['subch'], '?')))


if __name__ == '__main__':
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    ce = sys.argv[1] if len(sys.argv) > 1 else ''
    if ce == 'lista':
        tipareste(*citeste_ansamblul(cadre_eti(pachete_din_fisier(sys.argv[2]))))
    elif ce == 'extrage':
        f, sid, out = sys.argv[2], int(sys.argv[3], 16), sys.argv[4]
        a, _ = citeste_ansamblul(cadre_eti(pachete_din_fisier(f)))
        p = a.posturi[sid]
        dec = DABPlus() if p['ascty'] == 63 else None
        with open(out, 'wb') as g:
            for fic, mst in cadre_eti(pachete_din_fisier(f)):
                v = mst.get(p['subch'])
                if not v:
                    continue
                if dec:
                    for x in dec.adauga(v):
                        g.write(x)
                else:
                    g.write(v)
        print('%s -> %s; %s' % (p['nume'], out, dec and dict(dec.info or {}, au_bune=dec.au_bune, au_rele=dec.au_rele)))
    else:
        print(__doc__)

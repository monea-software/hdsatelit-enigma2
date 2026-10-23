# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ETI (ETS 300 799) din pachete TS de satelit -> cadre DAB de 24 ms. Facut de hdsatelit.com.

Iesirea are aceeasi forma ca dab_edi.cadre_eti: (fic: bytes, mst: {SCID: bytes}), un element la 24 ms,
ca sa mearga Ansamblu si DABPlus neschimbate.

  cadre_din_ts2na(sarcini_ts, umplutura)   ETI(NA, G.704) = flux E1 de 2048 kbit/s pus in sarcina TS
  cadre_din_tsniv2ni(sarcini_ts)           ETI(NI, V.11) sau ETI(NI, G.703) pus in sarcina TS; recunoaste singur si
                                           forma ETI(LI) pe unitati PUSI (vezi cadre_din_ts_li)
  cadre_din_ts_li(sarcini_ts)              ETI(LI) fara ERR/FSYNC, cate un cadru pe unitate TS (PUSI + pointer)
  cadre_din_eti_ni(cadre_6144)             ETI(NI) brut (cadre de 6144 octeti sau bucati oarecare)

Toate primesc fie blocuri de pachete TS de 188 octeti (se recunosc dupa 0x47 la fiecare 188), fie sarcini deja scoase.
Fiecare functie primeste optional `stare` (dict) in care pune contoare: cadre, erori CRC, RS, sincronizari.

Drumul fierbinte nu are bucle pe biti: contorul de bloc se verifica cu bytes.translate pe o felie din 256 in 256,
octetii LIDATA se scot cu operator.itemgetter pe indici calculati o data, CRC-ul se face cu binascii.crc_hqx (C),
STC se citeste cu struct. Reed-Solomon ruleaza doar cand CRC-urile ETI nu ies bune.
Detalii si surse: ETI-NOTE.md.
Merge pe Python 3 si pe Python 2.7. Pe Python 3 aliasurile de mai jos sunt chiar functiile standard (drumul datelor
neschimbat); pe 2.7 octetii se tin in bytearray, iar cele doua metode care folosesc memoryview cu pas au o varianta
proprie la sfarsitul fisierului.
"""
from __future__ import division

import binascii
import operator
import struct
import sys

if sys.version_info[0] < 3:                       # Python 2.7
    _PY2 = True
    _B = bytearray                                # bytes(tuplu) pe 2.7 e textul tuplului, str[i] e un sir
    _GOL = bytearray()                            # b''.join nu primeste bytearray pe 2.7
    _G = b'\x47'                                  # bytearray.count(int) nu exista pe 2.7
    _INDEXABIL = (bytearray,)

    def _O(x=b''):
        return bytes(bytearray(x))

    def _din_octeti(b, _ordine='big'):
        return int(binascii.hexlify(b) or b'0', 16)

    def _in_octeti(v, n, _ordine='big'):
        return binascii.unhexlify('%0*x' % (2 * n, v)) if n else b''
else:
    _PY2 = False
    _B = _O = bytes
    _GOL = b''
    _G = 0x47
    _INDEXABIL = (bytes, bytearray)
    _din_octeti = int.from_bytes                  # _din_octeti(x, 'big') = int.from_bytes(x, 'big')
    _in_octeti = int.to_bytes                     # _in_octeti(v, n, 'big') = v.to_bytes(n, 'big')

__all__ = ['cadre_din_ts2na', 'cadre_din_tsniv2ni', 'cadre_din_eti_ni', 'cadre_din_ts_li', 'UnitatiLI',
           'DeframerNA', 'DeframerNI', 'SarciniTS', 'citeste_li', 'RS']

NI_LUNG = 6144                    # octeti ETI(NI, G.703) la 24 ms; tot atat are si multicadrul E1
FSYNC0 = b'\x07\x3a\xb6'
FSYNC1 = b'\xf8\xc5\x49'

_crc = binascii.crc_hqx
_U16 = struct.Struct('>H')
_STC = {}                         # NST -> struct precompilat


if hasattr(int, 'bit_count'):                # Python 3.10+
    def _paritate(v):
        return v.bit_count() & 1
else:
    def _paritate(v):
        return bin(v).count('1') & 1


def _crc_bun(mv, o, n):
    """CRC ETI (anexa D) peste mv[o:o+n], comparat cu cei 2 octeti de dupa."""
    return (_crc(mv[o:o + n], 0xFFFF) ^ 0xFFFF) == ((mv[o + n] << 8) | mv[o + n + 1])


def _stare_noua(stare):
    s = stare if stare is not None else {}
    for k in ('cadre', 'cadre_nule', 'crc_antet', 'crc_mst', 'lungime_rea', 'sinc', 'sinc_pierduta',
              'octeti_aruncati', 'rs_randuri_corectate', 'rs_randuri_esuate', 'rs_octeti_corectati',
              'pachete_pierdute', 'pachete_rele', 'erori'):
        s.setdefault(k, 0)
    return s


# ---------------------------------------------------------------- ETI(LI)
def citeste_li(mv, o, cap, st):
    """Citeste un cadru ETI(LI) care incepe cu FC la mv[o], avand cel mult `cap` octeti disponibili.
    Intoarce (fic, mst, crc_mst_bun) sau None daca antetul e stricat / cadru nul."""
    if cap < 20:
        st['lungime_rea'] += 1
        return None
    fc1 = mv[o + 1]; fc2 = mv[o + 2]; fc3 = mv[o + 3]
    if mv[o] == 0xFF and fc1 == 0xFF and fc2 == 0xFF and fc3 == 0xFF:
        st['cadre_nule'] += 1
        return None
    nst = fc1 & 0x7F
    fl = ((fc2 & 7) << 8) | fc3
    h = 4 + 4 * nst                                   # FC + STC
    if nst > 64 or (fl + 3) * 4 > cap or fl < nst + 1:
        st['lungime_rea'] += 1
        return None
    if not _crc_bun(mv, o, h + 2):                    # CRCh peste FC, STC, MNSC
        st['crc_antet'] += 1
        return None
    if mv[o] > 249:                                   # FCT in afara standardului: se accepta, se numara
        st['fct_nestandard'] = st.get('fct_nestandard', 0) + 1
    mid = (fc2 >> 3) & 3
    ficl = ((128 if mid == 3 else 96) if fc1 & 0x80 else 0)
    m = o + h + 4                                     # inceputul MST
    n_mst = (fl - nst - 1) * 4
    s = _STC.get(nst)
    if s is None:
        s = _STC[nst] = struct.Struct('>%dI' % nst)
    cuv = s.unpack_from(mv, o + 4)
    total = ficl
    for w in cuv:
        total += (w & 0x3FF) * 8
    if total != n_mst:
        st['lungime_rea'] += 1
        return None
    crc_bun = _crc_bun(mv, m, n_mst)
    if not crc_bun:
        st['crc_mst'] += 1
    fic = bytes(mv[m:m + ficl])
    p = m + ficl
    mst = {}
    for w in cuv:
        n = (w & 0x3FF) * 8
        if n:
            mst[w >> 26] = bytes(mv[p:p + n])
        p += n
    return fic, mst, crc_bun


# ---------------------------------------------------------------- Reed-Solomon ETI(NA): GF(2^8), 0x187, radacini alfa^120..
class RS:
    """Cod RS scurtat la 240 de octeti, R octeti de paritate (5 sau 14), ETS 300 799 8.6.
    Conventie: primul octet al randului e coeficientul de grad maxim, paritatea la coada."""
    EXP = [0] * 512
    LOG = [0] * 256
    _x = 1
    for _i in range(255):
        EXP[_i] = _x
        LOG[_x] = _i
        _x <<= 1
        if _x & 0x100:
            _x ^= 0x187
    for _i in range(255, 512):
        EXP[_i] = EXP[_i - 255]
    del _x, _i
    PRIMA = 120

    def __init__(self, r):
        self.r = r
        self._cache_masti = {}
        e, l = self.EXP, self.LOG
        g = [1]
        for i in range(self.PRIMA, self.PRIMA + r):     # g(x) = prod (x - a^i)
            a = e[i]
            ng = g + [0]
            for k in range(len(g)):
                if g[k]:
                    ng[k + 1] ^= e[l[g[k]] + l[a]]
            g = ng
        self.gen = g                                      # g[0] = 1, grad r

    def mul(self, a, b):
        return self.EXP[self.LOG[a] + self.LOG[b]] if a and b else 0

    def codeaza(self, date):
        """Paritatea (r octeti) pentru date (240 - r octeti)."""
        e, l, g, r = self.EXP, self.LOG, self.gen, self.r
        reg = [0] * r
        for b in date:
            fb = b ^ reg[0]
            reg = reg[1:] + [0]
            if fb:
                lf = l[fb]
                for k in range(r):
                    if g[k + 1]:
                        reg[k] ^= e[lf + l[g[k + 1]]]
        return _O(reg)

    def sindroame_lent(self, cuv):
        """Horner octet cu octet; folosit doar in probe, ca martor pentru sindroame()."""
        e, l = self.EXP, self.LOG
        out = []
        for i in range(self.r):
            la = self.PRIMA + i
            s = 0
            for c in cuv:
                s = (e[l[s] + la] if s else 0) ^ c
            out.append(s)
        return out

    def _masti(self, n):
        """Sindromul e liniar peste GF(2): bitul b din S_k = paritatea (cuvant & masca[k][b]).
        Mastile se fac o data (la prima eroare), apoi un sindrom costa 8 x R operatii pe intregi mari (cod C)."""
        e, l = self.EXP, self.LOG
        masti = []
        for k in range(self.r):
            biti = [0] * 8
            for grad in range(n):
                la = ((self.PRIMA + k) * grad) % 255
                for t in range(8):
                    v = e[t + la]                      # (1 << t) * a^(la), cu log(1 << t) = t (0x187: a = 2, t < 8)
                    for b in range(8):
                        if v >> b & 1:
                            biti[b] |= 1 << (grad * 8 + t)
            masti.append(biti)
        return masti

    def sindroame(self, cuv):
        n = len(cuv)
        m = self._cache_masti.get(n)
        if m is None:
            m = self._cache_masti[n] = self._masti(n)
        v = _din_octeti(cuv, 'big')
        out = []
        for biti in m:
            s = 0
            for b in range(8):
                if _paritate(v & biti[b]):
                    s |= 1 << b
            out.append(s)
        return out

    def corecteaza(self, cuv):
        """Intoarce (cuvant_corectat, numar_octeti_corectati) sau (None, -1) daca nu se poate."""
        S = self.sindroame(cuv)
        if not any(S):
            return cuv, 0
        e, l, r, n = self.EXP, self.LOG, self.r, len(cuv)
        # Berlekamp-Massey
        lam = [1]; b = [1]; L = 0; m = 1; bb = 1
        for k in range(r):
            d = S[k]
            for i in range(1, L + 1):
                if i < len(lam) and lam[i] and S[k - i]:
                    d ^= e[l[lam[i]] + l[S[k - i]]]
            if d == 0:
                m += 1
                continue
            coef = e[l[d] + 255 - l[bb]]
            t = lam[:]
            need = len(b) + m
            if len(lam) < need:
                lam = lam + [0] * (need - len(lam))
            for i, bi in enumerate(b):
                if bi:
                    lam[i + m] ^= e[l[coef] + l[bi]]
            if 2 * L <= k:
                L = k + 1 - L
                b = t; bb = d; m = 1
            else:
                m += 1
        while len(lam) > 1 and lam[-1] == 0:
            lam.pop()
        if L != len(lam) - 1 or 2 * L > r:
            return None, -1
        # Chien: pozitia j are gradul n-1-j, X = a^(n-1-j); radacina la X^-1
        poz = []
        for j in range(n):
            xinv = (255 - (n - 1 - j)) % 255
            s = 0
            for i, c in enumerate(lam):
                if c:
                    s ^= e[l[c] + (xinv * i) % 255]
            if s == 0:
                poz.append(j)
        if len(poz) != L:
            return None, -1
        # Forney: Omega = S(x) Lambda(x) mod x^r ; e = X^(1-PRIMA) Omega(X^-1) / Lambda'(X^-1)
        om = [0] * r
        for i, si in enumerate(S):
            if si:
                for k, c in enumerate(lam):
                    if c and i + k < r:
                        om[i + k] ^= e[l[si] + l[c]]
        out = bytearray(cuv)
        for j in poz:
            lx = (n - 1 - j) % 255
            xinv = (255 - lx) % 255
            num = 0
            for i, c in enumerate(om):
                if c:
                    num ^= e[l[c] + (xinv * i) % 255]
            den = 0
            for i in range(1, len(lam), 2):             # derivata formala: termenii impari
                if lam[i]:
                    den ^= e[l[lam[i]] + (xinv * (i - 1)) % 255]
            if den == 0:
                return None, -1
            if num:
                val = e[(l[num] - l[den] + lx * (1 - self.PRIMA)) % 255]
                out[j] ^= val
        if any(self.sindroame(out)):
            return None, -1
        return _B(out), L


# ---------------------------------------------------------------- harta ETI(NA, G.704)
class _HartaNA:
    """Indici in multicadrul de 6144 octeti, calculati o data (ETS 300 799 8.4.2 / 8.4.3)."""

    def __init__(self, paritate):
        d = 240 - paritate                           # coloane de date: 235 sau 226
        pe_sb = 2 * (d - 8) + 6 * d                  # 1864 sau 1792 octeti LIDATA pe superbloc
        self.capacitate = 3 * pe_sb                  # 5592 sau 5376
        b = [0] * self.capacitate
        randuri = []
        for i in range(24):
            sb, r8 = divmod(i, 8)
            rand = []
            for j in range(240):
                p = 1920 * sb + 8 * j + r8
                q = p + p // 15 + 1
                rand.append(q)
                if j >= d or (r8 < 2 and j % 30 == 0):
                    continue
                if r8 < 2:
                    idx = sb * pe_sb + (i % 2) * (d - 8) - j // 30 + j - 1
                else:
                    idx = sb * pe_sb + r8 * d + j - 16
                b[idx] = q
            randuri.append(rand)
        self.date = operator.itemgetter(*b)
        self.randuri = [operator.itemgetter(*r) for r in randuri]
        self.indici_randuri = randuri
        self.indici_date = b
        self.rs = RS(paritate)


_HARTI = {}


def harta_na(paritate):
    h = _HARTI.get(paritate)
    if h is None:
        h = _HARTI[paritate] = _HartaNA(paritate)
    return h


# contorul din M: bloc in bitii 7..5, superbloc in 4..3; valoarea asteptata la blocul k al multicadrului
_M_MASCA = _B(v & 0xF8 for v in range(256))
_M_ASTEPTAT = _B(((k % 8) << 5) | ((k // 8) << 3) for k in range(24))
_M_INDEX = _B(((v >> 5) + 8 * ((v >> 3) & 3)) if ((v >> 3) & 3) < 3 else 0xFF for v in range(256))
_M_URM = _B(((v + 1) % 24) if v < 24 else 0xFE for v in range(256))     # 0xFF (invalid) nu se potriveste niciodata


# ---------------------------------------------------------------- transformari de biti (doar daca fluxul nu e aliniat)
_INVERS = _B(int('{:08b}'.format(i)[::-1], 2) for i in range(256))
_NEGAT = _B(255 - i for i in range(256))


class _Transformator(object):
    """Sare `bit_start` biti din flux, apoi regrupeaza in octeti; optional inverseaza ordinea bitilor in octet si/sau
    neaga toti bitii (flux E1 cu polaritatea logica inversata: dovedit pe 9E 12091,9 H, PID-urile 1062/1063/1065,
    unde golul liniei vine 0x00 in loc de 0xFF si FAS-ul G.704 apare ca 0x64).
    Cost: o conversie int <-> bytes pe bucata (cod C), nu bucla pe biti."""

    def __init__(self, invers, bit_start, negat=False):
        self.inv = invers
        self.neg = negat
        self.sari, self.k = divmod(bit_start, 8)
        self.rest = 0
        self.nrest = 0
        self.primul = True

    def __call__(self, d):
        if self.sari:
            if len(d) <= self.sari:
                self.sari -= len(d)
                return b''
            d = d[self.sari:]
            self.sari = 0
        if self.neg:
            d = bytes(d).translate(_NEGAT)
        if self.inv:
            d = bytes(d).translate(_INVERS)
        if not self.k:
            return d
        if not d:
            return b''
        bits = 8 * len(d)
        v = _din_octeti(d, 'big')
        if self.primul:
            bits -= self.k
            v &= (1 << bits) - 1
            self.primul = False
        v |= self.rest << bits
        bits += self.nrest
        r = bits & 7
        self.rest = v & ((1 << r) - 1)
        self.nrest = r
        return _in_octeti(v >> r, bits >> 3, 'big')


_VARIANTE = [(False, 0, False), (True, 0, False), (False, 0, True), (True, 0, True)] + \
    [(inv, k, neg) for neg in (False, True) for k in range(1, 8) for inv in (False, True)]


class _Deframer(object):
    """Partea comuna: fereastra de octeti, cautarea sincronizarii pe variante de aliniere, compactarea."""
    MIN_CAUTARE = 2 * 64 * 192 + 8           # doua cadre V.11 de lungime maxima (N = 64)

    def __init__(self, stare=None, variante=True):
        self.st = _stare_noua(stare)
        self.buf = bytearray()
        self.poz = 0
        self.sinc = False
        self.lant = []
        self.variante = _VARIANTE if variante else _VARIANTE[:1]
        self.st.setdefault('aliniere', None)

    def adauga(self, bucata):
        if not bucata:
            return []
        for t in self.lant:
            bucata = t(bucata)
        self.buf += bucata
        iesire = []
        try:
            self._lucreaza(iesire)
        except (IndexError, ValueError, struct.error):
            self.st['erori'] += 1
            self._pierde()
            self.poz = min(self.poz + 1, len(self.buf))
        if self.poz > 65536:
            del self.buf[:self.poz]
            self.poz = 0
        return iesire

    def pauza(self, n):
        """Lipsesc n octeti din flux (pachete pierdute): se pun zerouri ca sa ramana faza cadrului."""
        if n > 0 and self.sinc:
            self.adauga(_B(n))                   # n octeti zero (pe 2.7 bytes(n) ar fi textul numarului, tacut)

    def _pierde(self):
        self.sinc = False
        self.st['sinc_pierduta'] += 1

    def _lucreaza(self, iesire):
        while True:
            if not self.sinc:
                if not self._cauta():
                    return
            if not self._cadru(iesire):
                return

    def _cauta(self):
        disp = len(self.buf) - self.poz
        if disp < self.MIN_CAUTARE:
            return False
        w = _B(self.buf[self.poz:self.poz + 2 * self.MIN_CAUTARE])
        for inv, k, neg in self.variante:
            tw = w if not (inv or k or neg) else _B(_Transformator(inv, k, neg)(w))
            s = self._gaseste(tw)
            if s >= 0:
                if inv or k or neg:
                    if len(self.lant) >= 3:
                        self.lant = []
                    t = _Transformator(inv, k + 8 * s, neg)
                    rest = t(bytes(self.buf[self.poz:]))
                    self.lant.append(t)
                    self.buf = bytearray(rest)
                    self.poz = 0
                    self.st['aliniere'] = {'bit_invers': inv, 'bit_decalaj': k, 'negat': neg}
                else:
                    self.poz += s
                    self.st['octeti_aruncati'] += s
                    if self.st['aliniere'] is None:
                        self.st['aliniere'] = {'bit_invers': False, 'bit_decalaj': 0, 'negat': False}
                self.sinc = True
                self.rele = 0
                self.st['sinc'] += 1
                return True
        # nimic: se pastreaza doar coada, cat sa prinda un cadru care incepe acum
        pastrat = self.MIN_CAUTARE
        arunc = disp - pastrat
        if arunc > 0:
            self.poz += arunc
            self.st['octeti_aruncati'] += arunc
        return False


# ---------------------------------------------------------------- ETI(NA, G.704)
class DeframerNA(_Deframer):
    """Flux E1 (6144 octeti la 24 ms) -> cadre ETI(LI). Sincronizare pe contorul de bloc din octetul M."""
    MIN_CAUTARE = 2 * NI_LUNG + 260

    def __init__(self, stare=None, variante=True, rs=True):
        _Deframer.__init__(self, stare, variante)
        self.rs = rs
        self.rele = 0
        self.st.setdefault('varianta_na', None)

    @staticmethod
    def _gaseste(w):
        """Cauta 6 contoare de bloc consecutive corecte (30 de biti) la pasul de 256 octeti, pe toate cele 256 de faze.
        Fara bucla pe pozitii: idx[t+1] == idx[t]+1 se verifica prin XOR intre doi intregi mari si find pe octeti nuli."""
        n = len(w)
        for o in range(1, 257):
            idx = w[o::256].translate(_M_INDEX)
            k = len(idx) - 1
            if k < 5:
                break
            x = _in_octeti(_din_octeti(idx[1:], 'big') ^ _din_octeti(idx[:-1].translate(_M_URM), 'big'), k, 'big')
            t = x.find(b'\x00\x00\x00\x00\x00')
            while t != -1:
                a = idx[t]
                s = o - 1 + 256 * (t - a)
                while s < 0:
                    s += NI_LUNG
                if s + NI_LUNG <= n:
                    return s
                t = x.find(b'\x00\x00\x00\x00\x00', t + 1)
        return -1

    def _cadru(self, iesire):
        buf = self.buf
        p = self.poz
        if len(buf) - p < NI_LUNG:
            return False
        o = _B(buf[p:p + NI_LUNG])
        if o[1::256].translate(_M_MASCA) != _M_ASTEPTAT:
            m = o[1::256].translate(_M_MASCA)
            gresite = sum(1 for a, b in zip(m, _M_ASTEPTAT) if a != b)
            if gresite >= 3:
                self.rele += 1
                if self.rele >= 2 or gresite > 12:
                    self._pierde()
                    self.poz = p + 1
                    return True
        else:
            self.rele = 0
        self.poz = p + NI_LUNG
        rez = self._decodeaza(o)
        if rez is not None:
            self.st['cadre'] += 1
            iesire.append(rez)
        return True

    def _decodeaza(self, o):
        st = self.st
        semnal_5376 = o[257] & 0x02
        ordine = (14, 5) if semnal_5376 else (5, 14)
        for incercare, par in enumerate(ordine):
            h = harta_na(par)
            b = _B(h.date(o))
            r = citeste_li(b, 0, h.capacitate, st)
            if r is not None and r[2]:
                st['varianta_na'] = h.capacitate
                return r[0], r[1]
            if self.rs and incercare == 0:
                oc = self._rs(o, h)
                if oc is not None:
                    b = _B(h.date(oc))
                    r2 = citeste_li(b, 0, h.capacitate, st)
                    if r2 is not None:
                        st['varianta_na'] = h.capacitate
                        return r2[0], r2[1]
            if r is not None:                      # antet bun, MST cu CRC gresit: se da mai departe
                st['varianta_na'] = h.capacitate
                return r[0], r[1]
        return None

    def _rs(self, o, h):
        st = self.st
        oc = None
        esuate = 0
        for k, get in enumerate(h.randuri):
            cuv = _B(get(o))
            if not any(h.rs.sindroame(cuv)):
                continue
            bun, n = h.rs.corecteaza(cuv)
            if bun is None:
                st['rs_randuri_esuate'] += 1
                esuate += 1
                if esuate >= 6:                      # multicadru pierdut (pachete lipsa, gunoi): nu se mai arde timp
                    break
                continue
            if oc is None:
                oc = bytearray(o)
            for q, a, v in zip(h.indici_randuri[k], cuv, bun):
                if a != v:
                    oc[q] = v
            st['rs_randuri_corectate'] += 1
            st['rs_octeti_corectati'] += n
        return _B(oc) if oc is not None else None


# ---------------------------------------------------------------- ETI(NI)
class DeframerNI(_Deframer):
    """ETI(NI, G.703) sau ETI(NI, V.11): FSYNC alternant.
    Lungimea cadrului se afla singura: fixa N x 192 (6144 intai) sau variabila, cand FRPD lipseste si cadrul are doar
    SYNC + LIDATA = (FL + 3) x 4 + 4 octeti (atunci self.lung = 0 si lungimea se ia din FL-ul fiecarui cadru)."""

    def __init__(self, stare=None, variante=True, lungime=None):
        _Deframer.__init__(self, stare, variante)
        self.lung = lungime
        self.fixa = lungime is not None
        self.urm = None
        self.rele = 0

    @staticmethod
    def _lung_var(w, s):
        """Lungimea cadrului fara FRPD care incepe la w[s] (SYNC), din FL."""
        return (((w[s + 6] & 7) << 8 | w[s + 7]) + 3) * 4 + 4

    def _gaseste(self, w):
        n = len(w)
        if self.fixa:
            cand = [self.lung]
        else:
            cand = [NI_LUNG] + [k * 192 for k in range(1, 65) if k != 32] + [0]
        h0 = w.find(FSYNC0, 1)
        h1 = w.find(FSYNC1, 1)
        while h0 != -1 or h1 != -1:                  # cel mai devreme dintre cele doua tipare
            if h1 == -1 or (h0 != -1 and h0 < h1):
                h, pat, comp = h0, FSYNC0, FSYNC1
                h0 = w.find(FSYNC0, h0 + 1)
            else:
                h, pat, comp = h1, FSYNC1, FSYNC0
                h1 = w.find(FSYNC1, h1 + 1)
            s = h - 1
            if s + 12 > n:
                break
            for L in cand:
                if L:
                    if s + 2 * L + 4 > n or w[h + L:h + L + 3] != comp or w[h + 2 * L:h + 2 * L + 3] != pat:
                        continue
                    lim = L - 4
                else:                                # fara FRPD: cadrele se leaga prin FL
                    L1 = self._lung_var(w, s)
                    if s + L1 + 12 > n or w[h + L1:h + L1 + 3] != comp:
                        continue
                    L2 = self._lung_var(w, s + L1)
                    if s + L1 + L2 + 4 > n or w[h + L1 + L2:h + L1 + L2 + 3] != pat:
                        continue
                    lim = L1 - 4
                if citeste_li(w, s + 4, lim, _stare_noua({})) is not None:
                    self.lung = L
                    self.urm = pat
                    self.st['lungime_cadru_ni'] = L if L else 'variabila (fara FRPD)'
                    return s
        return -1

    def _cadru(self, iesire):
        buf = self.buf
        p = self.poz
        L = self.lung
        disp = len(buf) - p
        if L == 0:                                   # lungime variabila
            if disp < 12:
                return False
            L = self._lung_var(buf, p)
        if disp < L:
            return False
        f = _B(buf[p:p + L])
        if f[1:4] == self.urm:
            self.rele = 0
        else:
            self.rele += 1
            if self.rele >= 2 or self.lung == 0:     # la lungime variabila un FSYNC gresit inseamna FL de neincredere
                self._pierde()
                self.poz = p + 1
                if not self.fixa:
                    self.lung = None
                return True
        r = citeste_li(f, 4, L - 4, self.st)
        if r is None and self.lung == 0:
            self._pierde()                           # FL nu e garantat de CRCh: nu se sare pe o lungime gresita
            self.poz = p + 1
            self.lung = None
            return True
        self.urm = FSYNC1 if self.urm == FSYNC0 else FSYNC0
        self.poz = p + L
        if r is not None:
            self.st['cadre'] += 1
            iesire.append((r[0], r[1]))
        return True


# ---------------------------------------------------------------- TS -> sarcina
_CC_MASCA = _B(v & 0x3F for v in range(256))             # afc + cc, fara bitii de criptare
_CC_SIR = _B(0x10 | (i & 15) for i in range(16)) * 64


class SarciniTS(object):
    """Scoate sarcina unui PID din pachete TS de 188 octeti, sau lasa neatinse sarcinile deja scoase.

    `umplutura`: octeti sariti dupa antetul de 4 octeti al fiecarui pachet: 12 la ts2na12, 0 la ts2na.
    Valoare negativa: datele incep inainte de sfarsitul antetului (-3 = imediat dupa 0x47, fara antet TS real);
    atunci nu se citesc PID si contor.
    `pes`: 'auto' sare un antet PES (00 00 01) la pachetele cu PUSI; True il cere; False nu se uita.

    adauga() intoarce o lista in ordine de bucati de date (memoryview/bytes) si numere intregi;
    un intreg n inseamna „lipsesc n octeti aici" (pachete pierdute sau cu TEI)."""

    def __init__(self, umplutura=0, pid=None, stare=None, pes=False):
        self.u = umplutura
        self.pid = pid
        self.st = _stare_noua(stare)
        self.cc = None
        self.pes = pes
        self.lung_sarcina = 184 - max(umplutura, 0)
        self.rest = b''
        self.mod = None                       # None nehotarat, 'ts', 'sarcina'

    @staticmethod
    def _aliniat(d, n):
        return d[0:n:188].count(0x47) == n // 188

    def adauga(self, d):
        if self.mod == 'sarcina':
            return [d[self.u:]] if self.u > 0 else [d]
        if self.rest:
            d = self.rest + bytes(d)
            self.rest = b''
        if self.mod is None:
            if len(d) < 188 * 3:
                if d[:1] == b'\x47' or not d:
                    self.rest = bytes(d)
                    return []
                n = 0
            else:
                n = len(d) // 188 * 188
            if n and d[0] == 0x47 and self._aliniat(d, n):
                self.mod = 'ts'
            else:
                self.mod = 'sarcina'
                return self.adauga(d)
        n = len(d) // 188 * 188
        if not n:
            self.rest = bytes(d)
            return []
        if d[0] != 0x47 or not self._aliniat(d, n):
            return self._realiniaza(d)
        if n < len(d):
            self.rest = bytes(d[n:])
        mv = memoryview(d)
        u = self.u
        cnt = n // 188
        if u < 0:
            return [mv[i + 4 + u:i + 188] for i in range(0, n, 188)]
        # drumul rapid: acelasi PID, fara TEI, fara camp de adaptare, contor continuu, fara PES de sarit
        if self.cc is not None:
            h1 = mv[1:n:188].tobytes()
            h2 = mv[2:n:188].tobytes()
            start = (self.cc + 1) & 15
            if h1.count(h1[0]) == cnt and not (h1[0] & 0x80) and h2.count(h2[0]) == cnt and \
                    not (self.pes and h1[0] & 0x40) and \
                    (self.pid is None or ((h1[0] & 0x1F) << 8 | h2[0]) == self.pid) and \
                    mv[3:n:188].tobytes().translate(_CC_MASCA) == _CC_SIR[start:start + cnt]:
                self.cc = (start + cnt - 1) & 15
                return [mv[i + 4 + u:i + 188] for i in range(0, n, 188)]
        return self._pachet_cu_pachet(d, mv, n)

    def _realiniaza(self, d):
        """Octeti in plus sau lipsa in intrare: se cauta iar 0x47 la fiecare 188."""
        n = len(d)
        k = 0
        while k + 188 <= n and d[k] == 0x47:
            k += 188
        out = self.adauga(d[:k]) if k else []        # partea inca aliniata
        for i in range(k + 1, n):
            if d[i] == 0x47 and (i + 188 >= n or d[i + 188] == 0x47) and (i + 376 >= n or d[i + 376] == 0x47):
                self.st['octeti_aruncati'] += i - k
                self.cc = None
                return out + self.adauga(d[i:])
        self.st['octeti_aruncati'] += n - k
        return out

    def _pachet_cu_pachet(self, d, mv, n):
        out = []
        u = self.u
        pes = self.pes
        for i in range(0, n, 188):
            b1 = d[i + 1]
            pid = ((b1 & 0x1F) << 8) | d[i + 2]
            if pid == 0x1FFF or (self.pid is not None and pid != self.pid):
                continue
            if self.pid is None:
                self.pid = pid                        # primul PID vazut; un bloc de la surse are un singur PID
            b3 = d[i + 3]
            afc = (b3 >> 4) & 3
            cc = b3 & 15
            if b1 & 0x80:                             # TEI: pachet stricat, se socoteste lipsa
                self.st['pachete_rele'] += 1
                out.append(self.lung_sarcina)
                if afc & 1:
                    self.cc = cc
                continue
            if not afc & 1:
                continue
            if self.cc is not None:
                if cc == self.cc:                     # duplicat permis de ISO 13818-1
                    continue
                lipsa = (cc - self.cc - 1) & 15
                if lipsa:
                    self.st['pachete_pierdute'] += lipsa
                    out.append(lipsa * self.lung_sarcina)
            self.cc = cc
            o = i + 4
            if afc & 2:
                o += 1 + d[i + 4]
            if pes and (b1 & 0x40) and o + 9 <= i + 188 and d[o] == 0 and d[o + 1] == 0 and d[o + 2] == 1:
                o += 9 + d[o + 8]
            else:
                o += u
            if o < i + 188:
                out.append(mv[o:i + 188])
        return out


def _din_ts(sarcini_ts, deframer, umplutura, pid, pes=False):
    ts = SarciniTS(umplutura, pid, deframer.st, pes)
    adauga = deframer.adauga
    for bloc in sarcini_ts:
        if not bloc:
            continue
        try:
            bucati = ts.adauga(bloc)
        except (IndexError, ValueError):
            deframer.st['erori'] += 1
            continue
        date = []
        for b in bucati:
            if b.__class__ is int:
                if date:
                    for c in adauga(_GOL.join(date)):
                        yield c
                    date = []
                deframer.pauza(b)
            else:
                date.append(b)
        if date:
            for c in adauga(_GOL.join(date)):
                yield c


# ---------------------------------------------------------------- interfata din contract
def cadre_din_ts2na(sarcini_ts, umplutura, stare=None, pid=None, rs=True):
    """ETI(NA, G.704) in TS -> (fic, mst). umplutura: 12 (ts2na12), 0 (ts2na), -3 (doar 0x47 in fata)."""
    d = DeframerNA(stare, rs=rs)
    return _din_ts(sarcini_ts, d, umplutura, pid)


def cadre_din_tsniv2ni(sarcini_ts, stare=None, pid=None, umplutura=0, pes='auto'):
    """ETI(NI, V.11) in TS -> (fic, mst). Lungimea cadrului (N x 192) se afla singura.

    Unele fluxuri trecute in liste ca „NI in TS" poarta de fapt cadre ETI(LI) fara ERR/FSYNC, cate unul pe unitate
    PUSI (dovedit pe 39E 12241,5 H, PID 0x3F2). Primele pachete se incearca intai asa; daca ies cel putin 3 cadre
    cu CRC-ul antetului bun, fluxul merge pe UnitatiLI, altfel pe deframerul NI, cu aceleasi pachete de la inceput."""
    st = _stare_noua(stare)
    it = iter(sarcini_ts)
    primele = []
    proba = UnitatiLI(pid, {})
    n = 0
    cadre_li = 0
    for bloc in it:
        if not bloc:
            continue
        primele.append(bloc)
        n += len(bloc)
        try:
            cadre_li += len(proba.adauga(bloc))
        except (IndexError, ValueError, struct.error):
            cadre_li = 0
            break
        if cadre_li >= 3 or n >= _PROBA_LI_OCTETI or proba.mod == 'sarcina':
            break
    if cadre_li >= 3:
        st['forma'] = 'ETI(LI) pe unitati PUSI'
        u = UnitatiLI(pid, st)
        for bloc in primele:
            for c in u.adauga(bloc):
                yield c
        for bloc in it:
            if bloc:
                for c in u.adauga(bloc):
                    yield c
        return
    st['forma'] = 'ETI(NI)'

    def tot():
        for b in primele:
            yield b
        for b in it:
            yield b
    for c in _din_ts(tot(), DeframerNI(st), umplutura, pid, pes):
        yield c


_PROBA_LI_OCTETI = 188 * 400                 # ~1,5 s la debitul ERT (16 pachete pe cadru: 25 de cadre posibile)


class UnitatiLI(object):
    """Pachete TS -> cadre ETI(LI) (ETS 300 799: FC, STC, EOH, MST, EOF, TIST, fara ERR si FSYNC), cate unul pe
    unitate. Pachetul cu PUSI are pointer_field; cadrul incepe dupa el si tine pana la inceputul unitatii urmatoare,
    iar ce e dupa lungimea din FL e umplutura (0xFF). FL e crezut doar cu CRC-ul antetului bun (citeste_li).
    O unitate cu pachete lipsa (contor), TEI sau pointer imposibil se arunca intreaga. Fara bucle pe octeti:
    o iteratie pe pachet si felii."""
    MAX_UNITATE = 2 * NI_LUNG

    def __init__(self, pid=None, stare=None):
        self.pid = pid
        self.st = _stare_noua(stare)
        self.buf = None
        self.cc = None
        self.rest = b''
        self.mod = None                          # None, 'ts' sau 'sarcina' (intrarea nu e TS: forma nu se aplica)

    def adauga(self, d):
        out = []
        if self.mod == 'sarcina' or not d:
            return out
        if self.rest:
            d = self.rest + _B(d)
            self.rest = b''
        elif not isinstance(d, _INDEXABIL):
            d = _B(d)
        n = len(d)
        st = self.st
        i = 0
        if d[0] == 0x47 and self.pid is not None and n >= 188 and self._rapid(d, n, out):
            return out
        if d[0] != 0x47:
            i = _gaseste_188(d, 0)
            if i < 0:
                if self.mod is None and n >= 188 * 3:
                    self.mod = 'sarcina'
                else:
                    self.rest = bytes(d[-187:])
                return out
            st['octeti_aruncati'] += i
            self.buf = None
        while i + 188 <= n:
            if d[i] != 0x47:
                j = _gaseste_188(d, i + 1)
                if j < 0:
                    self.rest = bytes(d[max(i + 1, n - 187):])
                    st['octeti_aruncati'] += n - i - len(self.rest)
                    self.buf = None
                    return out
                st['octeti_aruncati'] += j - i
                self.buf = None
                self.cc = None
                i = j
                continue
            self.mod = 'ts'
            b1 = d[i + 1]
            pid = ((b1 & 0x1F) << 8) | d[i + 2]
            if pid == 0x1FFF or (self.pid is not None and pid != self.pid):
                i += 188
                continue
            if self.pid is None:
                if not b1 & 0x40:                # fara PID dat, se invata de pe primul pachet cu PUSI
                    i += 188
                    continue
                self.pid = pid
            b3 = d[i + 3]
            afc = (b3 >> 4) & 3
            cc = b3 & 15
            if b1 & 0x80:
                st['pachete_rele'] += 1
                self.buf = None
                self.cc = cc
                i += 188
                continue
            if not afc & 1:
                i += 188
                continue
            if self.cc is not None:
                if cc == self.cc:                # duplicat permis de ISO 13818-1
                    i += 188
                    continue
                lipsa = (cc - self.cc - 1) & 15
                if lipsa:
                    st['pachete_pierdute'] += lipsa
                    self.buf = None
            self.cc = cc
            o = i + 4
            if afc & 2:
                o += 1 + d[i + 4]
            capat = i + 188
            if o >= capat:
                i += 188
                continue
            if b1 & 0x40:
                inceput = o + 1 + d[o]
                if inceput > capat:
                    st['erori'] += 1
                    self.buf = None
                    i += 188
                    continue
                if self.buf is not None:
                    self.buf += d[o + 1:inceput]
                    self._termina(out)
                self.buf = bytearray(d[inceput:capat])
            elif self.buf is not None:
                self.buf += d[o:capat]
                if len(self.buf) > self.MAX_UNITATE:
                    st['lungime_rea'] += 1
                    self.buf = None
            i += 188
        if i < n:
            self.rest = bytes(d[i:])
        return out

    def _rapid(self, d, n, out):
        """Blocul intreg dintr-o data, fara bucla pe pachete, cand e curat: toate sincronizarile la loc, iar pachetele
        PID-ului au doar sarcina (fara camp de adaptare), fara TEI si cu contorul continuu. Pachetele altor PID-uri se
        scot din bloc (ca in bucla, unde se sar fara efect), sarcinile se lipesc prin stergeri din 188 in 188 (in C),
        iar pe pachet se lucreaza doar la inceputurile de unitate (PUSI). Orice altceva: False, fara nicio schimbare
        de stare, si blocul merge pe bucla obisnuita. Rezultatul e acelasi cu al buclei."""
        cnt = n // 188
        m = cnt * 188
        pid = self.pid
        if pid == 0x1FFF or cnt > 1000 or d[0:m:188].count(_G) != cnt:
            return False
        t1 = d[1:m:188].translate(_tabel_pid_sus(pid >> 8))
        t2 = d[2:m:188].translate(_tabel_egal(pid & 0xFF))
        masca = _in_octeti(_din_octeti(t1, 'big') & _din_octeti(t2, 'big'), cnt, 'big')
        if masca.find(b'\x00') < 0:
            T = d[:m]
        else:
            parti = []
            k = masca.find(b'\x01')
            while k >= 0:
                e = masca.find(b'\x00', k)
                if e < 0:
                    e = cnt
                parti.append(d[k * 188:e * 188])
                k = masca.find(b'\x01', e)
            T = _GOL.join(parti)
        tcnt = len(T) // 188
        if tcnt:
            h1 = T[1::188]
            h3 = T[3::188]
            if max(h1) & 0x80:                               # TEI
                return False
            start = (h3[0] if self.cc is None else self.cc + 1) & 15
            if h3.translate(_CC_MASCA) != _CC_SIR[start:start + tcnt]:
                return False
        self.mod = 'ts'
        if tcnt:
            st = self.st
            buf = self.buf
            pusi = h1.translate(_BIT_PUSI)
            k = 0
            p = pusi.find(b'\x01')
            while p >= 0:
                if p > k and buf is not None:
                    buf += _sarcini_188(T, k, p)
                    if len(buf) > self.MAX_UNITATE:
                        st['lungime_rea'] += 1
                        buf = None
                o = p * 188 + 4
                capat = o + 184
                inceput = o + 1 + T[o]
                if inceput > capat:
                    st['erori'] += 1
                    buf = None
                else:
                    if buf is not None:
                        buf += T[o + 1:inceput]
                        self.buf = buf
                        self._termina(out)
                    buf = bytearray(T[inceput:capat])
                k = p + 1
                p = pusi.find(b'\x01', k)
            if k < tcnt and buf is not None:
                buf += _sarcini_188(T, k, tcnt)
                if len(buf) > self.MAX_UNITATE:
                    st['lungime_rea'] += 1
                    buf = None
            self.buf = buf
            self.cc = h3[-1] & 15
        if m < n:
            self.rest = bytes(d[m:])
        return True

    def _termina(self, out):
        b = self.buf
        self.buf = None
        if len(b) < 20:
            return
        r = citeste_li(b, 0, len(b), self.st)
        if r is not None:
            self.st['cadre'] += 1
            out.append((r[0], r[1]))


_BIT_PUSI = _B(1 if v & 0x40 else 0 for v in range(256))
_TABELE_PID = {}


def _tabel_pid_sus(sus):
    """Octetul 1 al antetului: 1 daca bitii PID de sus sunt `sus` (TEI si PUSI nu conteaza aici), altfel 0."""
    t = _TABELE_PID.get(('s', sus))
    if t is None:
        t = _TABELE_PID[('s', sus)] = _B(1 if (v & 0x1F) == sus else 0 for v in range(256))
    return t


def _tabel_egal(jos):
    t = _TABELE_PID.get(('j', jos))
    if t is None:
        t = _TABELE_PID[('j', jos)] = _B(1 if v == jos else 0 for v in range(256))
    return t


def _sarcini_188(T, a, b):
    """Sarcinile pachetelor a..b-1 (fara camp de adaptare) lipite: se sterg cei 4 octeti de antet din fiecare pachet."""
    s = bytearray(memoryview(T)[a * 188:b * 188])
    del s[0::188]
    del s[0::187]
    del s[0::186]
    del s[0::185]
    return s


def _gaseste_188(d, de_la):
    """Primul 0x47 urmat de 0x47 la +188 si +376 (cat se vede din bucata)."""
    n = len(d)
    i = d.find(b'\x47', de_la)
    while i != -1 and i + 188 <= n:
        if d[i + 188 if i + 188 < n else i] == 0x47 and (i + 376 >= n or d[i + 376] == 0x47):
            return i
        i = d.find(b'\x47', i + 1)
    return -1


def cadre_din_ts_li(sarcini_ts, stare=None, pid=None):
    """ETI(LI) pe unitati PUSI in TS -> (fic, mst). Forma gasita pe ERT DAB (39E 12241,5 H, PID 0x3F2)."""
    u = UnitatiLI(pid, stare)
    for bloc in sarcini_ts:
        if bloc:
            for c in u.adauga(bloc):
                yield c


def cadre_din_eti_ni(cadre_6144, stare=None):
    """ETI(NI) brut (bucati oarecare, de obicei cadre de 6144 octeti) -> (fic, mst)."""
    d = DeframerNI(stare)
    for bloc in cadre_6144:
        if bloc:
            for c in d.adauga(bloc):
                yield c


# ---------------------------------------------------------------- Python 2.7
if _PY2:
    # memoryview cu pas nu exista pe 2.7 (NotImplementedError) si bytearray.count(int) nici atat: cele doua metode de
    # mai jos fac acelasi lucru ca pe Python 3, cu felii din bytearray (o copie pe antet, nu pe octet).
    def _aliniat_2(d, n):
        return d[0:n:188].count(b'\x47') == n // 188

    def _sarcini_adauga_2(self, d):
        if self.mod == 'sarcina':
            return [d[self.u:]] if self.u > 0 else [d]
        if self.rest:
            d = self.rest + bytearray(d)
            self.rest = b''
        elif type(d) is not bytearray:
            d = bytearray(d)
        if self.mod is None:
            if len(d) < 188 * 3:
                if d[:1] == b'\x47' or not d:
                    self.rest = bytes(d)
                    return []
                n = 0
            else:
                n = len(d) // 188 * 188
            if n and d[0] == 0x47 and self._aliniat(d, n):
                self.mod = 'ts'
            else:
                self.mod = 'sarcina'
                return self.adauga(d)
        n = len(d) // 188 * 188
        if not n:
            self.rest = bytes(d)
            return []
        if d[0] != 0x47 or not self._aliniat(d, n):
            return self._realiniaza(d)
        if n < len(d):
            self.rest = bytes(d[n:])
        u = self.u
        cnt = n // 188
        if u < 0:
            return [d[i + 4 + u:i + 188] for i in range(0, n, 188)]
        if self.cc is not None:
            h1 = d[1:n:188]
            h2 = d[2:n:188]
            start = (self.cc + 1) & 15
            if h1.count(h1[0:1]) == cnt and not (h1[0] & 0x80) and h2.count(h2[0:1]) == cnt and \
                    not (self.pes and h1[0] & 0x40) and \
                    (self.pid is None or ((h1[0] & 0x1F) << 8 | h2[0]) == self.pid) and \
                    d[3:n:188].translate(_CC_MASCA) == _CC_SIR[start:start + cnt]:
                self.cc = (start + cnt - 1) & 15
                return [d[i + 4 + u:i + 188] for i in range(0, n, 188)]
        return self._pachet_cu_pachet(d, d, n)

    SarciniTS._aliniat = staticmethod(_aliniat_2)
    SarciniTS.adauga = _sarcini_adauga_2

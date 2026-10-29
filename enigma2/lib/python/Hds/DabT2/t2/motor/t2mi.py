# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Decapsulator T2-MI de referinta (Python, doar biblioteca standard).

Scris din standarde:
  - ETSI TS 102 773 V1.4.1 (DVB BlueBook A136, ianuarie 2016): pachetele T2-MI si transportul lor in TS.
  - ETSI EN 302 755 (DVB BlueBook A182): antetul BB, NM/HEM, ISSY, stergerea pachetelor nule, L1.

Drumul rapid e in C (c/t2mi_decap.c). Modulul asta e referinta si sta la baza probelor.
Descrierea formatului si capcanele: T2MI-NOTE.md.

Folosire:
    d = Decapsulator(pid=4096, plp=None)       # plp None = primul PLP de date din L1-current
    iesire = d.adauga(bloc_ts)                 # bloc de pachete TS 188 (orice lungime, orice taietura)
    iesire = d.adauga_sarcina(octeti)          # flux de pachete T2-MI fara antete TS (se sincronizeaza singur)
    d.plp_uri, d.stare

Merge pe Python 3 si pe Python 2.7 (acolo pachetele se tin in bytearray, ca indexul sa dea numere).
"""
from __future__ import division

import sys
import zlib
from collections import deque

if sys.version_info[0] < 3:                   # Python 2.7: bytes e str (index = sir), memoryview da tot siruri
    import binascii
    _PY2 = True
    _B = bytearray

    def _felie(x):
        return x                              # felia dintr-un bytearray e o copie, dar indexul da numere

    def _din_octeti(b):
        return int(binascii.hexlify(b) or b'0', 16)
    _SEP47 = bytearray(b'\x47')               # b'\x47'.join nu primeste bytearray pe 2.7
    from collections import OrderedDict as _DictOrdonat     # ordinea din L1 (dict o pastreaza doar pe 3.7+)
else:
    _PY2 = False
    _B = bytes
    _felie = memoryview
    _SEP47 = b'\x47'
    _DictOrdonat = dict

    def _din_octeti(b):
        return int.from_bytes(b, 'big')

__all__ = ['Decapsulator', 'TsInPid', 'crc32_mpeg', 'crc8_dvb', 'PACHET_NUL', 'KBCH']

# ---------------------------------------------------------------------------
# CRC-uri
# ---------------------------------------------------------------------------

# Tabel de inversare a bitilor intr-un octet. CRC-32 din T2-MI (EN 302 755 anexa F, TS 102 773 anexa A) are
# polinomul 0x04C11DB7, registrul pornit cu unu, fara inversare si fara XOR la final. zlib.crc32 face acelasi
# polinom in forma oglindita (cu XOR la final). Daca oglindim fiecare octet la intrare, zlib da rezultatul oglindit.
_OGLINDA = _B(int('{:08b}'.format(i)[::-1], 2) for i in range(256))


def crc32_mpeg(date):
    """CRC-32 MPEG-2 (init 0xFFFFFFFF, fara oglindire, fara XOR final)."""
    r = zlib.crc32(bytes(date).translate(_OGLINDA)) ^ 0xFFFFFFFF
    return int('{:032b}'.format(r)[::-1], 2)


def _crc32_bun(pachet):
    """Adevarat daca CRC-32 al pachetului (date + CRC la coada) e corect.
    Pentru CRC fara XOR final, CRC-ul peste date+CRC da zero; in forma zlib asta inseamna 0xFFFFFFFF."""
    return zlib.crc32(bytes(pachet).translate(_OGLINDA)) == 0xFFFFFFFF


if _PY2:
    # zlib.crc32 da numar cu semn pe 2.7 (fara & 0xFFFFFFFF comparatia de mai sus ar fi mereu falsa, tacut),
    # iar bytes(memoryview) ar fi textul "<memory at ...>"
    # zlib.crc32 pe 2.7 primeste doar str (nu bytearray): bytes(...) e str acolo
    def crc32_mpeg(date):                     # noqa: F811
        r = (zlib.crc32(bytes(bytearray(date).translate(_OGLINDA))) & 0xFFFFFFFF) ^ 0xFFFFFFFF
        return int('{:032b}'.format(r)[::-1], 2)

    def _crc32_bun(pachet):                   # noqa: F811
        return zlib.crc32(bytes(bytearray(pachet).translate(_OGLINDA))) & 0xFFFFFFFF == 0xFFFFFFFF


def _tabel_crc8():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        t.append(c)
    return _B(t)                              # pe 2.7 bytes(lista) ar fi textul listei


_CRC8 = _tabel_crc8()   # G8(x) = x^8 + x^7 + x^6 + x^4 + x^2 + 1, registrul pornit cu zero


def crc8_dvb(date, c=0):
    t = _CRC8
    for b in date:
        c = t[c ^ b]
    return c


if _PY2:
    _crc8_dvb_3 = crc8_dvb

    def crc8_dvb(date, c=0):                  # noqa: F811  (pe 2.7 un str dat din afara s-ar itera pe caractere)
        return _crc8_dvb_3(date if type(date) is bytearray else bytearray(date), c)


# ---------------------------------------------------------------------------
# Constante din standard
# ---------------------------------------------------------------------------

PACHET_NUL = b'\x47\x1f\xff\x10' + b'\xff' * 184

# Kbch (biti) din EN 302 755 tabelele 7(a), 7(b) si I.1 (T2-Lite). Folosit doar la cautarea sincronizarii.
KBCH = frozenset((32208, 38688, 43040, 48408, 51648, 53840,
                  7032, 9552, 10632, 11712, 12432, 13152,
                  5232, 6312))

TIPURI_T2MI = {0x00: 'bb', 0x01: 'aux', 0x02: 'celule', 0x10: 'l1_curent', 0x11: 'l1_viitor',
               0x12: 'p2_bias', 0x20: 'timestamp', 0x21: 'adresare', 0x30: 'fef_nul', 0x31: 'fef_iq',
               0x32: 'fef_compus', 0x33: 'fef_subparte'}

TIP_PLP = {0: 'common', 1: 'data1', 2: 'data2'}

_MAX_PACHET_T2MI = 6 + 8192 + 4       # payload_len are 16 biti: cel mult 8192 octeti de sarcina
_MAX_ASTEPTARE_L1 = 512               # cadre BB tinute pana vine L1-current (plp=None)
_MAX_COADA_COMUN = 256                # pachete din PLP-ul comun tinute pentru pachetele nule (mod nule)
_MAX_BUF_SARCINA = 4 * _MAX_PACHET_T2MI


class _StarePlp(object):
    """Starea de reasamblare pentru un PLP: bucata de pachet rupta intre cadre BB."""
    __slots__ = ('rest', 'cheie', 'crc_ant', 'iesite', 'nule')

    def __init__(self):
        self.rest = None      # None = nesincronizat (asteapta SYNCD); bytearray = inceputul unitatii rupte
        self.cheie = None     # (mod, lungime unitate, npd, issy)
        self.crc_ant = None   # NM: CRC-8 al pachetului anterior (doar cu verifica_up)
        self.iesite = 0
        self.nule = 0


class TsInPid(object):
    """Un TS intreg purtat direct in payload-ul unui PID, fara T2-MI (felul abertis: fluxurile de distributie spaniole de
    pe 30W). Rezerva in Python a lui bin/t2mi_decap -A: payload-urile pachetelor PID-ului (dupa antet si campul de
    adaptare), puse cap la cap, sunt pachetele TS de 188 de octeti ale multiplexului; resincronizare pe 0x47 la fiecare
    188. Pachetele cu bitii de criptare pusi se numara si se arunca; o pierdere (CC, TEI) reia sincronizarea.
    Aceeasi interfata ca Decapsulator: adauga(bloc_ts) -> bytes, goleste(), stare, plp_uri."""

    def __init__(self, pid):
        self.pid = int(pid) & 0x1FFF
        self.plp_uri = {}
        self.stare = {'ts_pachete': 0, 'ts_pid': 0, 'ts_resincronizari': 0, 'ts_cc_erori': 0, 'ts_duplicate': 0,
                      'ts_tei': 0, 'ts_criptate': 0, 'ts_af_rele': 0, 'resinc_interior': 0, 'iesite': 0,
                      'exceptii_prinse': 0}
        self.goleste()

    def goleste(self):
        self._ts_rest = b''
        self._cc = -1
        self._ultim = None
        self._ab = bytearray()
        self._sinc = False

    def _pierdut(self):
        if self._sinc:
            self.stare['resinc_interior'] += 1
        self._ab = bytearray()
        self._sinc = False

    def adauga(self, bloc_ts):
        out = bytearray()
        try:
            self._adauga(bloc_ts, out)
        except Exception:
            self.stare['exceptii_prinse'] += 1
            self.goleste()
        return bytes(out)

    def _adauga(self, bloc, out):
        st = self.stare
        date = _B(self._ts_rest + _B(bloc)) if self._ts_rest else _B(bloc)
        n = len(date)
        i = 0
        while i + 188 <= n:
            if date[i] != 0x47:
                st['ts_resincronizari'] += 1
                self._cc = -1
                self._pierdut()
                j = date.find(b'\x47', i + 1)
                while j >= 0 and j + 188 < n and date[j + 188] != 0x47:
                    j = date.find(b'\x47', j + 1)
                if j < 0:
                    i = n
                    break
                i = j
                continue
            st['ts_pachete'] += 1
            if ((date[i + 1] & 0x1F) << 8 | date[i + 2]) == self.pid:
                st['ts_pid'] += 1
                self._pachet(date[i:i + 188], out)
            i += 188
        self._ts_rest = date[i:] if i < n else b''
        if len(self._ts_rest) >= 188:
            self._ts_rest = b''

    def _pachet(self, p, out):
        st = self.stare
        if p[1] & 0x80:
            st['ts_tei'] += 1
            self._cc = -1
            self._pierdut()
            return
        if p[3] & 0xC0:
            st['ts_criptate'] += 1
            self._cc = -1
            self._pierdut()
            return
        afc = (p[3] >> 4) & 3
        cc = p[3] & 0x0F
        off = 4
        disc = False
        if afc == 0:
            st['ts_af_rele'] += 1
            self._pierdut()
            return
        if afc & 2:
            afl = p[4]
            if (afc == 3 and afl > 182) or (afc == 2 and afl != 183):
                st['ts_af_rele'] += 1
                if afc == 3:
                    self._cc = -1
                    self._pierdut()
                return
            disc = afl > 0 and bool(p[5] & 0x80)
            off = 5 + afl
        if not afc & 1:
            return
        if self._cc >= 0 and not disc:
            if cc == self._cc:
                if self._ultim == p:
                    st['ts_duplicate'] += 1
                    return
                st['ts_cc_erori'] += 1
                self._pierdut()
            elif cc != (self._cc + 1) & 0x0F:
                st['ts_cc_erori'] += 1
                self._pierdut()
        self._cc = cc
        self._ultim = p
        self._ab += p[off:]
        self._interior(out)

    def _interior(self, out):
        ab = self._ab
        i = 0
        n = len(ab)
        while True:
            if self._sinc:
                if n - i < 188:
                    break
                if ab[i] == 0x47:
                    out += ab[i:i + 188]
                    self.stare['iesite'] += 1
                    i += 188
                    continue
                self._sinc = False
                self.stare['resinc_interior'] += 1
            j = ab.find(b'\x47', i)
            if j < 0:
                i = n
                break
            i = j
            if n - i < 189:
                break
            if ab[i + 188] == 0x47:
                self._sinc = True
                continue
            i += 1
        if i:
            del ab[:i]


class Decapsulator(object):
    """Decapsulator T2-MI -> TS 188.

    pid          PID-ul pe care vin pachetele T2-MI (pentru adauga()).
    plp          PLP_ID dorit; None = primul PLP de date (tip 1 sau 2) din L1-current.
    nule         True = pune la loc pachetele nule sterse (DNP), ca fluxul sa aiba debit constant.
    comun        True = amesteca in iesire pachetele PLP-ului comun din acelasi grup (tabele SI).
    verifica_up  True = verifica CRC-8 al fiecarui pachet in NM (lent, pentru probe). Nu arunca pachete,
                 doar numara in stare['up_crc_rele'].
    flux_t2mi    t2mi_stream_id acceptat; None = primul vazut.
    """

    def __init__(self, pid, plp=None, nule=False, comun=True, verifica_up=False, flux_t2mi=None):
        self.pid = int(pid) & 0x1FFF
        self.plp_cerut = plp
        self.nule = bool(nule)
        self.comun = bool(comun)
        self.verifica_up = bool(verifica_up)
        self.flux_t2mi = flux_t2mi
        self.plp_uri = {}
        self.l1 = {}
        self.stare = {
            'ts_pachete': 0, 'ts_pid': 0, 'ts_resincronizari': 0, 'ts_cc_erori': 0, 'ts_duplicate': 0,
            'ts_tei': 0, 'ts_criptate': 0, 'ts_af_rele': 0, 'ts_pointer_rele': 0,
            't2mi_bune': 0, 't2mi_crc_rele': 0, 't2mi_pierdute': 0, 't2mi_alt_flux': 0,
            't2mi_neterminate': 0, 't2mi_tipuri': {},
            'sarcina_resincronizari': 0, 'sarcina_octeti_aruncati': 0,
            'bb_cadre': 0, 'bb_cadre_plp': 0, 'bb_crc_rele': 0, 'bb_ne_ts': 0, 'bb_lungimi_rele': 0,
            'bb_syncd_rele': 0, 'bb_upl_rele': 0, 'bb_sync_rele': 0,
            'up_iesite': 0, 'nule_puse': 0, 'up_crc_rele': 0, 'comun_iesite': 0,
            'l1_bune': 0, 'l1_rele': 0, 'l1_asteptare_depasita': 0,
            'exceptii_prinse': 0,
            'mod': None, 'plp': plp, 'plp_comun': None,
        }
        # nivel TS
        self._ts_rest = b''
        self._cc = -1
        self._in_pachet = False      # suntem in mijlocul unui pachet T2-MI (dupa un PUSI bun)
        self._buf = bytearray()      # pachetul T2-MI in reasamblare
        self._ultim_ts = None        # ultimul pachet TS acceptat (pentru duplicate)
        # nivel sarcina fara antete TS
        self._sbuf = bytearray()
        self._s_sinc = False
        # nivel T2-MI
        self._ultim_count = None
        # nivel BB
        self._plp_stari = {}
        self._asteapta = []          # (plp_id, bytes cadru BB) pana vine L1 (plp=None)
        self._plp_ales = plp
        self._plp_comun = None
        self._coada_comun = deque()
        self._out = bytearray()

    # ------------------------------------------------------------------
    # Intrari publice
    # ------------------------------------------------------------------

    def adauga(self, bloc_ts):
        """Primeste un bloc de octeti TS (orice lungime). Intoarce pachetele TS 188 scoase (bytes)."""
        try:
            self._adauga_ts(bloc_ts)
        except Exception:
            self.stare['exceptii_prinse'] += 1
            self._pierdere_ts()
        return self._scoate()

    def adauga_sarcina(self, octeti):
        """Primeste un flux continuu de pachete T2-MI fara antete TS. Se sincronizeaza pe antet + CRC-32."""
        try:
            self._adauga_sarcina(octeti)
        except Exception:
            self.stare['exceptii_prinse'] += 1
            self._sbuf = bytearray()
            self._s_sinc = False
            self._pierdere_t2mi()
        return self._scoate()

    def goleste(self):
        """Arunca tot ce e pe jumatate (la zap). Pastreaza plp_uri."""
        self._ts_rest = b''
        self._cc = -1
        self._in_pachet = False
        self._buf = bytearray()
        self._sbuf = bytearray()
        self._s_sinc = False
        self._pierdere_t2mi()
        self._coada_comun = deque()
        self._out = bytearray()

    def _scoate(self):
        if not self._out:
            return b''
        r = bytes(self._out)
        self._out = bytearray()
        return r

    # ------------------------------------------------------------------
    # Nivelul TS
    # ------------------------------------------------------------------

    def _pierdere_ts(self):
        """Pierdere pe nivelul TS: pachetul T2-MI inceput nu mai e bun, se asteapta urmatorul PUSI."""
        if self._in_pachet and self._buf:
            self.stare['t2mi_neterminate'] += 1
        self._in_pachet = False
        self._buf = bytearray()

    def _adauga_ts(self, bloc):
        st = self.stare
        date = self._ts_rest + _B(bloc) if self._ts_rest else _B(bloc)
        n = len(date)
        i = 0
        pid_h = self.pid >> 8
        pid_l = self.pid & 0xFF
        while i + 188 <= n:
            if date[i] != 0x47:
                # cautam din nou sincronizarea: 0x47 urmat de 0x47 la 188 (sau sfarsitul datelor)
                st['ts_resincronizari'] += 1
                self._pierdere_ts()
                self._cc = -1
                j = date.find(b'\x47', i + 1)
                while j >= 0 and j + 188 < n and date[j + 188] != 0x47:
                    j = date.find(b'\x47', j + 1)
                if j < 0:
                    i = n
                    break
                i = j
                continue
            st['ts_pachete'] += 1
            b1 = date[i + 1]
            if (b1 & 0x1F) != pid_h or date[i + 2] != pid_l:
                i += 188
                continue
            st['ts_pid'] += 1
            self._pachet_ts(date, i, b1)
            i += 188
        self._ts_rest = date[i:] if i < n else b''
        if len(self._ts_rest) >= 188:   # nu se intampla, dar nu lasam sa creasca
            self._ts_rest = b''

    def _pachet_ts(self, date, i, b1):
        st = self.stare
        if b1 & 0x80:
            st['ts_tei'] += 1
            self._pierdere_ts()
            return
        b3 = date[i + 3]
        if b3 & 0xC0:
            st['ts_criptate'] += 1
            self._pierdere_ts()
            return
        afc = (b3 >> 4) & 3
        cc = b3 & 0x0F
        if afc == 0:
            st['ts_af_rele'] += 1
            self._pierdere_ts()
            return
        p = i + 4
        discontinuitate = False
        if afc & 2:
            afl = date[i + 4]
            if afc == 3 and afl > 182 or afc == 2 and afl != 183:
                st['ts_af_rele'] += 1
                self._pierdere_ts()
                return
            if afl > 0:
                discontinuitate = bool(date[i + 5] & 0x80)
            p = i + 5 + afl
        if not (afc & 1):
            return    # fara sarcina: contorul nu creste
        # contorul de continuitate
        if self._cc >= 0 and not discontinuitate:
            if cc == self._cc:
                # un duplicat e voie o data (ISO 13818-1); il ignoram
                if self._ultim_ts is not None and date[i:i + 188] == self._ultim_ts:
                    st['ts_duplicate'] += 1
                    return
                st['ts_cc_erori'] += 1
                self._pierdere_ts()
            elif cc != (self._cc + 1) & 0x0F:
                st['ts_cc_erori'] += 1
                self._pierdere_ts()
        self._cc = cc
        self._ultim_ts = date[i:i + 188]
        fin = i + 188
        if b1 & 0x40:
            ptr = date[p]
            p += 1
            if p + ptr >= fin:
                st['ts_pointer_rele'] += 1
                self._pierdere_ts()
                return
            if self._in_pachet:
                self._buf += date[p:p + ptr]
                self._extrage_din_ts(final_pusi=True)
            else:
                self._buf = bytearray()
            self._in_pachet = True
            self._buf = bytearray(date[p + ptr:fin])
            self._extrage_din_ts(final_pusi=False)
        elif self._in_pachet:
            self._buf += date[p:fin]
            self._extrage_din_ts(final_pusi=False)

    def _extrage_din_ts(self, final_pusi):
        """Scoate pachetele T2-MI complete din bufferul TS.
        final_pusi=True: octetii de dinaintea pointerului trebuie sa termine exact pachetele in curs."""
        buf = self._buf
        st = self.stare
        while True:
            n = len(buf)
            if n < 6:
                break
            total = 6 + ((buf[4] << 8 | buf[5]) + 7 >> 3) + 4
            if n < total:
                break
            if _crc32_bun(_felie(buf)[:total]):
                self._pachet_t2mi(_B(buf[:total]))
                del buf[:total]
            else:
                st['t2mi_crc_rele'] += 1
                self._pierdere_t2mi()
                self._in_pachet = False
                self._buf = bytearray()
                return
        if final_pusi and buf:
            # pachetul nu s-a terminat unde spunea pointerul: pachete TS pierdute sau date stricate
            st['t2mi_neterminate'] += 1
            self._pierdere_t2mi()
            self._buf = bytearray()

    # ------------------------------------------------------------------
    # Sarcina fara antete TS
    # ------------------------------------------------------------------

    @staticmethod
    def _antet_plauzibil(b, k):
        t = b[k]
        plen = b[k + 4] << 8 | b[k + 5]
        if b[k + 2] & 0x0F or b[k + 3] & 0xF8:     # rfu (9 biti) = 0
            return False
        if t == 0x00:
            return (plen - 24) in KBCH
        if t == 0x20:
            return plen == 88
        if t == 0x10:
            return 2 * 8 + 168 + 16 <= plen
        return False

    def _adauga_sarcina(self, octeti):
        st = self.stare
        self._sbuf += octeti
        buf = self._sbuf
        k = 0
        while True:
            n = len(buf)
            if not self._s_sinc:
                # cautam un antet plauzibil cu CRC-32 corect
                gasit = -1
                while k + 6 <= n:
                    if self._antet_plauzibil(buf, k):
                        total = 6 + ((buf[k + 4] << 8 | buf[k + 5]) + 7 >> 3) + 4
                        if k + total > n:
                            break            # asteptam restul
                        if _crc32_bun(_felie(buf)[k:k + total]):
                            gasit = k
                            break
                    k += 1
                if gasit < 0:
                    if k:
                        st['sarcina_octeti_aruncati'] += k
                        del buf[:k]
                    if len(buf) > _MAX_BUF_SARCINA:
                        st['sarcina_octeti_aruncati'] += len(buf) - 6
                        del buf[:len(buf) - 6]
                    return
                if k:
                    st['sarcina_octeti_aruncati'] += k
                self._s_sinc = True
                st['sarcina_resincronizari'] += 1
                self._pierdere_t2mi()
                del buf[:k]
                k = 0
                continue
            if n < 6:
                return
            total = 6 + ((buf[4] << 8 | buf[5]) + 7 >> 3) + 4
            if n < total:
                return
            if buf[0] in TIPURI_T2MI and _crc32_bun(_felie(buf)[:total]):
                self._pachet_t2mi(_B(buf[:total]))
                del buf[:total]
            else:
                st['t2mi_crc_rele'] += 1
                self._s_sinc = False
                self._pierdere_t2mi()
                k = 1

    # ------------------------------------------------------------------
    # Nivelul T2-MI
    # ------------------------------------------------------------------

    def _pierdere_t2mi(self):
        """Un pachet T2-MI poate lipsi: toate bucatile rupte intre cadre BB devin nesigure."""
        self._ultim_count = None
        for s in self._plp_stari.values():
            s.rest = None
            s.crc_ant = None

    def _pachet_t2mi(self, pk):
        st = self.stare
        tip = pk[0]
        flux = pk[3] & 0x07
        if self.flux_t2mi is None:
            self.flux_t2mi = flux
        elif flux != self.flux_t2mi:
            st['t2mi_alt_flux'] += 1
            return
        count = pk[1]
        if self._ultim_count is not None and count != (self._ultim_count + 1) & 0xFF:
            st['t2mi_pierdute'] += (count - self._ultim_count - 1) & 0xFF
            self._pierdere_t2mi()
        self._ultim_count = count
        st['t2mi_bune'] += 1
        tipuri = st['t2mi_tipuri']
        tipuri[tip] = tipuri.get(tip, 0) + 1
        plen = pk[4] << 8 | pk[5]
        try:
            if tip == 0x00:
                if plen >= 24 + 80 and 6 + (plen + 7 >> 3) + 4 <= len(pk):
                    self._cadru_bb(pk[7], _felie(pk)[9:6 + (plen >> 3)])
                else:
                    st['bb_lungimi_rele'] += 1
            elif tip == 0x10:
                self._l1_curent(pk, plen)
        except Exception:
            st['exceptii_prinse'] += 1
            self._pierdere_t2mi()

    # ------------------------------------------------------------------
    # L1-current
    # ------------------------------------------------------------------

    def _l1_curent(self, pk, plen):
        st = self.stare
        sarc = pk[6:6 + (plen + 7 >> 3)]
        # frame_idx(8) freq_source(2) rfu(6) L1PRE(168) L1CONF_LEN(16) L1CONF ...
        if len(sarc) < 2 + 21 + 2:
            st['l1_rele'] += 1
            return
        pre = _din_octeti(sarc[2:23])

        def camp_pre(poz, lat):
            return (pre >> (168 - poz - lat)) & ((1 << lat) - 1)

        s2 = camp_pre(12, 4)
        num_rf = camp_pre(152, 3)
        conf_len = sarc[23] << 8 | sarc[24]
        conf_oct = (conf_len + 7) >> 3
        if 25 + conf_oct > len(sarc):
            st['l1_rele'] += 1
            return
        conf = _din_octeti(sarc[25:25 + conf_oct])
        biti = conf_oct * 8

        def camp(poz, lat):
            if poz + lat > conf_len:
                raise ValueError('L1CONF prea scurt')
            return (conf >> (biti - poz - lat)) & ((1 << lat) - 1)

        try:
            num_plp = camp(15, 8)
            poz = 15 + 8 + 4 + 8 + num_rf * 35
            if s2 & 1:
                poz += 34
            plp_uri = _DictOrdonat()
            ordine = []
            for _ in range(num_plp):
                pid_ = camp(poz, 8)
                tip = camp(poz + 8, 3)
                plp_uri[pid_] = {
                    'plp_id': pid_,
                    'tip': TIP_PLP.get(tip, 'rezervat%d' % tip),
                    'tip_cod': tip,
                    'sarcina': camp(poz + 11, 5),     # PLP_PAYLOAD_TYPE: 3 = TS
                    'grup': camp(poz + 28, 8),
                }
                ordine.append(pid_)
                poz += 89
        except ValueError:
            st['l1_rele'] += 1
            return
        st['l1_bune'] += 1
        self.l1 = {'t2_system_id': camp_pre(112, 16), 'network_id': camp_pre(96, 16),
                   'cell_id': camp_pre(80, 16), 'num_t2_frames': camp_pre(128, 8), 'num_rf': num_rf,
                   's2': s2, 'num_plp': num_plp, 'ordine': ordine}
        self.plp_uri = plp_uri
        self._alege_plp()

    def _alege_plp(self):
        st = self.stare
        if self._plp_ales is None and self.plp_uri:
            ordine = self.l1.get('ordine') or sorted(self.plp_uri)
            date_ts = [p for p in ordine if self.plp_uri[p]['tip_cod'] in (1, 2) and self.plp_uri[p]['sarcina'] == 3]
            date_ = [p for p in ordine if self.plp_uri[p]['tip_cod'] in (1, 2)]
            ales = (date_ts or date_ or ordine)[0]
            self._plp_ales = ales
            st['plp'] = ales
        if self._plp_ales is not None and self.comun and self._plp_ales in self.plp_uri:
            grup = self.plp_uri[self._plp_ales]['grup']
            comun = None
            for p, inf in self.plp_uri.items():
                if inf['tip_cod'] == 0 and inf['grup'] == grup and p != self._plp_ales:
                    comun = p
                    break
            if comun != self._plp_comun:
                self._plp_comun = comun
                self._coada_comun = deque()
                st['plp_comun'] = comun
        if self._asteapta and self._plp_ales is not None:
            asteapta, self._asteapta = self._asteapta, []
            for plp_id, cadru in asteapta:
                self._cadru_bb(plp_id, _felie(cadru))

    # ------------------------------------------------------------------
    # Cadre BB
    # ------------------------------------------------------------------

    def _cadru_bb(self, plp_id, bb):
        st = self.stare
        st['bb_cadre'] += 1
        if self._plp_ales is None:
            # nu stim inca ce PLP vrem: tinem cadrele pana vine L1-current
            if len(self._asteapta) >= _MAX_ASTEPTARE_L1:
                st['l1_asteptare_depasita'] += 1
                self._plp_ales = self._asteapta[0][0]
                st['plp'] = self._plp_ales
                self._alege_plp()
            else:
                self._asteapta.append((plp_id, _B(bb)))
                return
        if plp_id == self._plp_ales:
            esteComun = False
        elif plp_id == self._plp_comun and plp_id is not None:
            esteComun = True
        else:
            return
        st['bb_cadre_plp'] += 1
        s = self._plp_stari.get(plp_id)
        if s is None:
            s = self._plp_stari[plp_id] = _StarePlp()

        m = crc8_dvb(bb[:9]) ^ bb[9]
        if m > 1:
            st['bb_crc_rele'] += 1
            s.rest = None
            s.crc_ant = None
            return
        ma1 = bb[0]
        if ma1 >> 6 != 3:
            st['bb_ne_ts'] += 1
            s.rest = None
            return
        issyi = (ma1 >> 3) & 1
        npd = (ma1 >> 2) & 1
        dfl = bb[4] << 8 | bb[5]
        syncd = bb[7] << 8 | bb[8]
        n = dfl >> 3
        if dfl & 7 or 10 + n > len(bb):
            st['bb_lungimi_rele'] += 1
            s.rest = None
            return
        if m == 0:
            if not esteComun:
                st['mod'] = 'NM'
            upl = bb[2] << 8 | bb[3]
            unit = upl >> 3
            issy = unit - 188 - npd
            if upl & 7 or (issy not in (2, 3) if issyi else issy != 0):
                st['bb_upl_rele'] += 1
                s.rest = None
                return
            if bb[6] != 0x47:
                st['bb_sync_rele'] += 1
            corp = 1
            cheie = (0, unit, npd, issy)
        else:
            if not esteComun:
                st['mod'] = 'HEM'
            unit = 187 + npd
            issy = 0
            corp = 0
            cheie = (1, unit, npd, 0)
        if s.cheie != cheie:
            s.cheie = cheie
            s.rest = None
            s.crc_ant = None

        data = bb[10:10 + n]
        rest = s.rest
        if syncd == 0xFFFF:
            if rest is not None:
                rest += data
                if len(rest) > unit:
                    st['bb_syncd_rele'] += 1
                    s.rest = None
                elif len(rest) == unit:
                    # unitatea s-a terminat exact la capatul cadrului; urmatorul cadru trebuie sa aiba SYNCD 0
                    out = self._out if not esteComun else bytearray()
                    self._emite(s, _felie(_B(rest)), 0, 1, unit, corp, npd, issy, out)
                    s.rest = bytearray()
                    if esteComun:
                        self._amesteca_comun(out)
            return
        if syncd & 7 or (syncd >> 3) > n:
            st['bb_syncd_rele'] += 1
            s.rest = None
            return
        k = syncd >> 3
        unitati = []
        if rest is not None:
            if len(rest) + k == unit:
                if k:
                    rest += data[:k]
                if unit:
                    unitati.append(_felie(_B(rest)))
            elif k or rest:
                st['bb_syncd_rele'] += 1
                s.crc_ant = None
        cate = (n - k) // unit
        sf = k + cate * unit
        s.rest = bytearray(data[sf:n])
        out = self._out if not esteComun else bytearray()
        if unitati:
            self._emite(s, unitati[0], 0, 1, unit, corp, npd, issy, out)
        if cate:
            self._emite(s, data, k, cate, unit, corp, npd, issy, out)
        if esteComun:
            self._amesteca_comun(out)

    def _emite(self, s, reg, start, cate, unit, corp, npd, issy, out):
        """Scrie in out `cate` unitati din reg incepand la start. Unitate NM: [CRC-8][187][ISSY][DNP];
        unitate HEM: [187][DNP]. Pachetul TS iese cu 0x47 pus la loc."""
        st = self.stare
        sf = start + cate * unit
        if self.verifica_up and corp == 1:
            for p in range(start, sf, unit):
                if s.crc_ant is not None and reg[p] != s.crc_ant:
                    st['up_crc_rele'] += 1
                s.crc_ant = crc8_dvb(reg[p + 1:p + unit])
        if npd and self.nule:
            off_dnp = corp + 187 + issy
            nul = PACHET_NUL
            # doar PLP-ul de date (care scrie direct in self._out) ia pachete din coada PLP-ului comun
            coada = self._coada_comun if (self._plp_comun is not None and out is self._out) else None
            for p in range(start, sf, unit):
                dnp = reg[p + off_dnp]
                if dnp:
                    s.nule += dnp
                    st['nule_puse'] += dnp
                    if coada:
                        while dnp and coada:
                            out += coada.popleft()
                            st['comun_iesite'] += 1
                            dnp -= 1
                    if dnp:
                        out += nul * dnp
                out += b'\x47'
                out += reg[p + corp:p + corp + 187]
        else:
            out += b'\x47'
            out += _SEP47.join([reg[p:p + 187] for p in range(start + corp, sf, unit)])
        s.iesite += cate
        st['up_iesite'] += cate

    def _amesteca_comun(self, pachete):
        """Pachetele PLP-ului comun (fara nulele lui) intra in iesire. Cu nule=True iau locul pachetelor nule
        puse la loc in PLP-ul de date; altfel intra imediat, in ordinea sosirii."""
        st = self.stare
        mv = _felie(pachete)
        coada = self._coada_comun
        for p in range(0, len(pachete), 188):
            if (mv[p + 1] & 0x1F) == 0x1F and mv[p + 2] == 0xFF:
                continue
            if self.nule:
                coada.append(bytes(mv[p:p + 188]))
            else:
                self._out += mv[p:p + 188]
                st['comun_iesite'] += 1
        while len(coada) > _MAX_COADA_COMUN:
            # PLP-ul de date nu are destule nule: nu tinem la infinit, cele mai vechi ies direct
            self._out += coada.popleft()
            st['comun_iesite'] += 1

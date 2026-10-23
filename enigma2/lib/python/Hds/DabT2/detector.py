# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Detector de fluxuri DAB+ si DVB-T2 pe un transponder deja acordat. Facut de hdsatelit.com.

Ruleaza in procesul separat (nu in enigma2). Citeste doar sectiuni (PAT, PMT, SDT, MPE) si, daca exista,
pachete TS brute, apoi intoarce un dictionar JSON cu feed-urile gasite in formatul listei de frecvente.

Sursele se dau ca functii, ca sa poata fi probat pe PC cu date sintetice:
    sectiuni(pid, timp_s)   -> iterabil de sectiuni intregi (bytes) sau None cand nu a venit nimic;
                               trebuie sa se termine singur dupa timp_s (sau sa dea None des, ca sa-l oprim).
    pachete_ts(pid, timp_s) -> iterabil de blocuri de pachete TS de 188 octeti (sau None); optional.
Iteratorul se inchide (close) dupa folosire, ca sa elibereze filtrul de demux.

Standarde: ISO/IEC 13818-1 (PAT, PMT), EN 300 468 (SDT, descriptori, T2MI_descriptor 6.4.14),
EN 301 192 (datagram_section MPE), TS 102 821 (EDI: PF, AF, TAG), TS 102 693 (deti), EN 300 401 (FIC),
TS 102 773 (T2-MI: antet 6 octeti + CRC32, pointer la PUSI), EN 300 799 (ETI, FSYNC), ITU-T G.704 (FAS).

Pe receptor:  python3 detector.py [dab|t2|toate] [timp_max_s]   (tunerul trebuie tinut acordat de altcineva)
Merge si cu Python 2.7 (imagini vechi): acolo datele se citesc prin bytearray, ca indexul sa dea numere.
"""
from __future__ import division

import json
import struct
import sys
import time

if sys.version_info[0] < 3:                           # Python 2.7: aceleasi nume ca pe Python 3
    try:
        from compat import monoton as _monoton, din_octeti as _din_octeti
    except ImportError:
        from .compat import monoton as _monoton, din_octeti as _din_octeti
    OSError = EnvironmentError                        # noqa: A001  (pe 2.7 IOError de la ioctl nu e OSError)
    _B = bytearray                                    # bytes(...) pe 2.7 e str: str[i] da un sir, nu un numar
    _GOL = bytearray()
    _chr = unichr                                     # noqa: F821
    from collections import OrderedDict as _DictOrdonat
else:
    _monoton = time.monotonic
    _B = bytes
    _GOL = b''
    _chr = chr
    _DictOrdonat = dict

    def _din_octeti(b):
        return int.from_bytes(b, 'big')

# ---------------------------------------------------------------- CRC pe tabele
_T32 = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _T32.append(_c)
_T16 = []
for _i in range(256):
    _c = _i << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x1021) & 0xFFFF if _c & 0x8000 else (_c << 1) & 0xFFFF
    _T16.append(_c)
del _i, _c


def crc32_mpeg(date):
    c = 0xFFFFFFFF
    t = _T32
    for b in date:
        c = ((c << 8) & 0xFFFFFFFF) ^ t[(c >> 24) ^ b]
    return c


def crc16_ccitt(date, c=0xFFFF):
    t = _T16
    for b in date:
        c = ((c << 8) & 0xFFFF) ^ t[(c >> 8) ^ b]
    return c


def crc16_ok(date):
    """CRC-CCITT complementat la coada (FIB, AF, HCRC la PF)."""
    return len(date) > 2 and (crc16_ccitt(date[:-2]) ^ 0xFFFF) == (date[-2] << 8 | date[-1])


# ---------------------------------------------------------------- constante
TID_PAT, TID_PMT, TID_SDT, TID_MPE = 0x00, 0x02, 0x42, 0x3E
PID_PAT, PID_SDT = 0x0000, 0x0011

TIP_VIDEO = {0x01, 0x02, 0x10, 0x1B, 0x20, 0x24, 0x42, 0x33}
TIP_AUDIO = {0x03, 0x04, 0x0F, 0x11, 0x1C, 0x81, 0x87}
TIP_DSMCC = {0x0A, 0x0B, 0x0C, 0x0D}
TIP_IGNORAT = {0x86}                    # SCTE-35
# descriptori care arata ca un stream_type 0x06 e sunet, subtitrare, teletext, AIT sau carusel
DESC_NU_E_AL_NOSTRU = {0x0A, 0x13, 0x14, 0x45, 0x46, 0x56, 0x59, 0x6A, 0x6F, 0x7A, 0x7B, 0x7C}
EXT_T2MI = 0x11
DBID_MPE = 0x0005
DBID_NU_E_MPE = {0x0006, 0x0007, 0x000A, 0x000B, 0x00F0, 0x00F1, 0x00F2}
TIPURI_T2MI = frozenset((0x00, 0x01, 0x02, 0x10, 0x11, 0x12, 0x20, 0x21, 0x30, 0x31, 0x32, 0x33))
# cat se citeste cel mult un PID cu EDI: cat sa vina din FIC lista posturilor fiecarui ansamblu (FIG 1/1 se repeta
# cam o data pe secunda); de obicei se termina mai devreme, cand toate ansamblurile de pe PID sunt complete
TIMP_PID_MPE_S = 9.0
SECTIUNI_PE_ANSAMBLU = 2000     # plafonul de sectiuni pe PID, pe fiecare ansamblu EDI gasit acolo (cel putin 10000)

FSYNC0, FSYNC1 = b'\x07\x3a\xb6', b'\xf8\xc5\x49'
_FAS_MSB = _B(1 if (b & 0x7F) == 0x1B else 0 for b in range(256))
_FAS_LSB = _B(1 if (b & 0xFE) == 0xD8 else 0 for b in range(256))
# flux E1 cu bitii negati (dovedit pe 9E 12091,9 H): FAS-ul apare ca 0x64 / 0x27
_FAS_MSB_NEG = _B(1 if ((255 - b) & 0x7F) == 0x1B else 0 for b in range(256))
_FAS_LSB_NEG = _B(1 if ((255 - b) & 0xFE) == 0xD8 else 0 for b in range(256))


# ---------------------------------------------------------------- sectiuni
def sectiune_valida(s):
    """Intoarce sectiunea taiata la lungimea ei, sau None daca e rea (lungime, CRC32)."""
    if s is None or len(s) < 3:
        return None
    lung = ((s[1] & 0x0F) << 8) | s[2]
    if lung + 3 > len(s) or lung < 1:
        return None
    s = _B(s[:lung + 3])
    if s[1] & 0x80:                       # section_syntax_indicator
        if lung < 9:
            return None
        if s[0] == TID_MPE:
            return s                      # MPE: CRC32 verificat separat (poate fi si suma de control)
        if crc32_mpeg(s) != 0:
            return None
    return s


def _pat(s):
    """-> {program_number: pmt_pid} (fara programul 0, NIT)."""
    o, sf = {}, len(s) - 4
    i = 8
    while i + 4 <= sf:
        prog = (s[i] << 8) | s[i + 1]
        pid = ((s[i + 2] & 0x1F) << 8) | s[i + 3]
        if prog:
            o[prog] = pid
        i += 4
    return o


def _descriptori(d):
    i, n = 0, len(d)
    while i + 2 <= n:
        tag, lung = d[i], d[i + 1]
        if i + 2 + lung > n:
            return
        yield tag, d[i + 2:i + 2 + lung]
        i += 2 + lung


def _pmt(s):
    """-> (program_number, [ {pid, stream_type, desc: {...}} ])."""
    prog = (s[3] << 8) | s[4]
    pil = ((s[10] & 0x0F) << 8) | s[11]
    i, sf = 12 + pil, len(s) - 4
    es = []
    while i + 5 <= sf:
        st = s[i]
        pid = ((s[i + 1] & 0x1F) << 8) | s[i + 2]
        eil = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
        d = s[i + 5:min(i + 5 + eil, sf)]
        i += 5 + eil
        info = {'pid': pid, 'stream_type': st, 'taguri': [], 'dbid': None, 'component_tag': None,
                't2mi': None, 'format_id': None}
        for tag, v in _descriptori(d):
            info['taguri'].append(tag)
            if tag in (0x66, 0x64) and len(v) >= 2:
                info['dbid'] = (v[0] << 8) | v[1]
            elif tag == 0x52 and len(v) >= 1:
                info['component_tag'] = v[0]
            elif tag == 0x05 and len(v) >= 4:
                info['format_id'] = v[:4].decode('latin-1')
            elif tag == 0x7F and len(v) >= 1:
                info['taguri'].append(0x7F00 | v[0])
                if v[0] == EXT_T2MI and len(v) >= 4:
                    info['t2mi'] = {'t2mi_stream_id': v[1] & 0x07, 'fluxuri': (v[2] & 0x07) + 1,
                                    'ceas_comun': bool(v[3] & 0x01)}
        es.append(info)
    return prog, es


try:                                       # in pachetul pluginului
    from .text_dvb import text_dvb as _text_dvb, eticheta_dab as _eticheta_dab
except (ImportError, ValueError):          # ca script (python3 comun/detector.py) sau cu comun/ in sys.path (2.7: ValueError)
    from text_dvb import text_dvb as _text_dvb, eticheta_dab as _eticheta_dab


def _sdt(s):
    """-> {service_id: {'nume', 'furnizor', 'tip'}}"""
    o = {}
    i, sf = 11, len(s) - 4
    while i + 5 <= sf:
        sid = (s[i] << 8) | s[i + 1]
        dll = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
        d = s[i + 5:min(i + 5 + dll, sf)]
        i += 5 + dll
        for tag, v in _descriptori(d):
            if tag == 0x48 and len(v) >= 2:
                lp = v[1]
                furn = v[2:2 + lp]
                j = 2 + lp
                ln = v[j] if j < len(v) else 0
                o[sid] = {'tip': v[0], 'furnizor': _text_dvb(furn), 'nume': _text_dvb(v[j + 1:j + 1 + ln])}
    return o


# ---------------------------------------------------------------- MPE -> IP -> UDP
def udp_din_sectiune_mpe(s, verifica_crc=False):
    """-> (ip_dest, port_dest, sarcina_udp, fragment) sau None. s e deja taiata la lungime.
    CRC32 (section_syntax_indicator 1) costa mult pe sectiuni de 4 KB; detectorul il verifica doar pe primele
    sectiuni ale fiecarui PID, iar EDI are oricum CRC-urile lui (HCRC, AF)."""
    if len(s) < 16 or s[0] != TID_MPE:
        return None
    if s[5] & 0x3C:                        # adresa sau sarcina criptata
        return None
    if verifica_crc and s[1] & 0x80 and crc32_mpeg(s) != 0:
        return None
    c = s[12 + (8 if s[5] & 0x02 else 0):len(s) - 4]
    if len(c) < 28:
        return None
    v = c[0] >> 4
    if v == 4:
        ihl = (c[0] & 0x0F) * 4
        if ihl < 20 or c[9] != 17 or len(c) < ihl + 8:
            return None
        frag = ((c[6] & 0x1F) << 8) | c[7]
        if frag:
            return None                    # doar primul fragment are antet UDP
        mf = bool(c[6] & 0x20)
        tot = (c[2] << 8) | c[3]
        ip = '%d.%d.%d.%d' % (c[16], c[17], c[18], c[19])
    elif v == 6:
        ihl = 40
        if len(c) < 48 or c[6] != 17:
            return None
        mf = False
        tot = 40 + ((c[4] << 8) | c[5])
        ip = ':'.join('%x' % ((c[24 + k] << 8) | c[25 + k]) for k in range(0, 16, 2))
    else:
        return None
    port = (c[ihl + 2] << 8) | c[ihl + 3]
    ulen = (c[ihl + 4] << 8) | c[ihl + 5]
    sf = min(len(c), tot if tot >= ihl + 8 else len(c), ihl + ulen if ulen >= 8 else len(c))
    return ip, port, c[ihl + 8:sf], mf


# ---------------------------------------------------------------- EDI
class GrupEDI:
    """Pentru un (ip, port): numara pachetele EDI valide si scoate din FIC ansamblul (FIG 0/0 si 1/0: EId, nume) si
    posturile lui (FIG 0/2: SId cu componenta primara audio, deci subcanalul si DAB sau DAB+; FIG 1/1: numele).

    gata()     ansamblul e cunoscut (EId si nume): feed-ul se poate pune in lista.
    complet()  in plus, fiecare post audio din FIG 0/2 are nume, iar de CADRE_LINISTE cadre nu a aparut nimic nou
               (lista posturilor se repeta in rotatia FIC, deci o fereastra linistita arata ca s-a vazut toata).
               Un ansamblu fara niciun post audio dupa de trei ori atatea cadre e si el complet (FIG 0/2 vine de
               zece ori pe secunda: daca nu a venit, nu mai vine).
    Dupa complet() pachetele grupului doar se numara: nicio refacere de fragmente, niciun CRC.
    pare_edi(): cel putin doua pachete EDI bune cu numere de secventa diferite. O sectiune MPE cu adresa IP stricata
    (CRC-ul MPE se verifica numai pe primele sectiuni) poate purta un pachet EDI bun; repetat, ar parea alt flux, dar
    are mereu aceeasi secventa."""
    __slots__ = ('pf', 'af', 'rele', 'fragmente', 'eid', 'nume', 'ptr', 'cadre', 'af_verificate', 'posturi',
                 'fib_vazute', 'ultima_noutate', '_complet', 'secvente')

    CADRE_LINISTE = 60          # cadre de 24 ms, cam 1,4 s
    FIB_MAX = 512               # FIB-uri deja vazute tinute minte (FIC-ul se repeta: CRC-ul doar pe cele noi)
    POSTURI_MAX = 128           # un ansamblu are cel mult 64 de subcanale

    def __init__(self):
        self.pf = self.af = self.rele = self.cadre = self.af_verificate = 0
        self.fragmente = _DictOrdonat()       # „cel mai vechi pleaca" cere ordinea inserarii (pe 2.7 doar OrderedDict)
        self.eid = None
        self.nume = None
        self.ptr = None
        self.posturi = {}                     # sid -> [nume sau None, ascty sau None, subcanal sau None]
        self.fib_vazute = set()
        self.ultima_noutate = 0
        self._complet = False
        self.secvente = set()                 # cateva numere de secventa PF / AF vazute (ajung doua)

    def gata(self):
        return self.eid is not None and self.nume is not None

    def pare_edi(self):
        return self.pf + self.af >= 2 and len(self.secvente) >= 2

    def complet(self):
        if self._complet:
            return True
        if not self.gata() or self.cadre - self.ultima_noutate < self.CADRE_LINISTE:
            return False
        audio = [p for p in self.posturi.values() if p[2] is not None]
        if audio and all(p[0] for p in audio):
            self._complet = True
        elif not audio and self.cadre - self.ultima_noutate >= 3 * self.CADRE_LINISTE:
            self._complet = True
        return self._complet

    def lista_posturi(self):
        """Posturile audio cu nume si subcanal, cu aceleasi campuri ca lista releului (/dab/<feed>/lista): sid,
        nume, fel (DAB+ pentru ASCTy 63, altfel DAB), subcanal; ordonate dupa nume."""
        rez = []
        for sid, (nume, ascty, subch) in self.posturi.items():
            if nume and subch is not None:
                rez.append({'sid': sid, 'nume': nume, 'fel': 'DAB+' if ascty == 63 else 'DAB', 'subcanal': subch})
        rez.sort(key=lambda x: (x['nume'].lower(), x['sid']))
        return rez

    def _post(self, sid):
        p = self.posturi.get(sid)
        if p is None:
            if len(self.posturi) >= self.POSTURI_MAX:
                return None
            p = self.posturi[sid] = [None, None, None]
        return p

    def adauga(self, p):
        if p[:2] == b'PF':
            af = self._pf(p)
            if af is not None:
                self._af(af)
        elif p[:2] == b'AF':
            self._af(p, True)

    def _pf(self, p):
        if len(p) < 14:
            self.rele += 1
            return None
        fl = (p[10] << 8) | p[11]
        fec, adr, plen = fl >> 15, (fl >> 14) & 1, fl & 0x3FFF
        o = 12 + (2 if fec else 0) + (4 if adr else 0)
        if len(p) < o + 2 or not crc16_ok(p[:o + 2]):
            self.rele += 1
            return None
        self.pf += 1
        pseq = (p[2] << 8) | p[3]
        if len(self.secvente) < 4:
            self.secvente.add(('pf', pseq))
        if self._complet:
            return None
        findex = _din_octeti(p[4:7])
        fcount = _din_octeti(p[7:10])
        if fcount == 0 or findex >= fcount or fcount > 2048:
            return None
        fr = self.fragmente.get(pseq)
        if fr is None:
            if len(self.fragmente) >= 6:
                self.fragmente.pop(next(iter(self.fragmente)))
            fr = self.fragmente[pseq] = {}
        fr[findex] = p[o + 2:o + 2 + plen]
        if len(fr) < fcount:
            return None
        del self.fragmente[pseq]
        if fec and fcount > 1:
            # cu RS octetul j al pachetului protejat sta in fragmentul j mod Fcount (dovedit pe 7E 12567,8 V)
            date = bytearray(sum(len(x) for x in fr.values()))
            try:
                for i in range(fcount):
                    date[i::fcount] = fr[i]
            except ValueError:
                self.rele += 1
                return None
            date = _B(date)
        else:
            date = _GOL.join(fr[i] for i in range(fcount))
        if fec:
            rsk, rsz = p[12], p[13]
            if rsk == 0:
                return None
            date = _GOL.join(date[i:i + rsk] for i in range(0, len(date), rsk + 48))
            if rsz:
                date = date[:-rsz]
        return date

    def _af(self, af, direct=False):
        if len(af) < 10 or af[:2] != b'AF' or af[9] != 0x54:     # PT = 'T'
            if direct:
                self.rele += 1
            return
        lung = _din_octeti(af[2:6])
        if 10 + lung > len(af) or lung > 1 << 20:
            if direct:
                self.rele += 1
            return
        if direct:
            self.af += 1
            if len(self.secvente) < 4:
                self.secvente.add(('af', (af[6] << 8) | af[7]))
        if self._complet:
            return
        if af[8] & 0x80 and self.af_verificate < 4:
            # CRC pe un AF intreg (pana la cativa KB) costa mult pe ARM: se verifica doar primele AF-uri ale
            # grupului; mai departe ajunge CRC-ul fiecarui FIB (EN 300 401), din care se citeste numele
            if 12 + lung > len(af) or not crc16_ok(af[:12 + lung]):
                self.rele += 1
                return
            self.af_verificate += 1
        corp = af[10:10 + lung]
        o, deti = 0, None
        while o + 8 <= len(corp):
            nume = corp[o:o + 4]
            n = (_din_octeti(corp[o + 4:o + 8]) + 7) // 8
            v = corp[o + 8:o + 8 + n]
            if nume == b'*ptr':
                self.ptr = v[:4].decode('latin-1', 'replace')
            elif nume == b'deti':
                deti = v
            o += 8 + n
        if deti is None or len(deti) < 6 or self._complet:
            return
        self.cadre += 1
        atstf, ficf = deti[0] >> 7, (deti[0] >> 6) & 1
        if not ficf:
            return
        mid = deti[3] >> 6
        o = 6 + (8 if atstf else 0)
        fic = deti[o:o + (128 if mid == 3 else 96)]
        for i in range(0, len(fic) - 31, 32):
            self._fib(fic[i:i + 32])

    def _fib(self, fib):
        # un FIB deja vazut (acelasi continut, deci aceleasi figuri) nu mai aduce nimic: fara CRC si fara citire
        cheie = bytes(fib)
        if cheie in self.fib_vazute:
            return
        if len(self.fib_vazute) >= self.FIB_MAX:
            self.fib_vazute.clear()
        self.fib_vazute.add(cheie)
        if not crc16_ok(fib):
            return
        o = 0
        while o < 30 and fib[o] != 0xFF:
            tip, lung = fib[o] >> 5, fib[o] & 0x1F
            fig = fib[o + 1:o + 1 + lung]
            o += 1 + lung
            if not fig or o > 30:
                break
            if tip == 0:
                ext = fig[0] & 0x1F
                if ext == 0 and len(fig) >= 3:
                    eid = (fig[1] << 8) | fig[2]
                    if eid != self.eid:
                        self.eid = eid
                        self.ultima_noutate = self.cadre
                elif ext == 2 and not (fig[0] >> 5) & 1:
                    self._fig0_2(fig)              # P/D = 0: programe audio, SId pe 16 biti
            elif tip == 1 and len(fig) >= 19:
                ext = fig[0] & 0x07
                if ext == 0:
                    eid, nume = (fig[1] << 8) | fig[2], eticheta_ebu(fig[3:19], fig[0] >> 4)
                    if (eid, nume) != (self.eid, self.nume):
                        self.eid, self.nume = eid, nume
                        self.ultima_noutate = self.cadre
                elif ext == 1 and not (fig[0] >> 3) & 1:
                    # OE = 0: numele unui post din acest ansamblu (OE = 1 ar fi un post din alt ansamblu)
                    nume = eticheta_ebu(fig[3:19], fig[0] >> 4)
                    p = self._post((fig[1] << 8) | fig[2])
                    if p is not None and nume and p[0] != nume:
                        p[0] = nume
                        self.ultima_noutate = self.cadre

    def _fig0_2(self, fig):
        """FIG 0/2 (EN 300 401 6.3.1): SId (16 biti), octetul cu numarul componentelor, apoi cate 2 octeti pe
        componenta: TMId (2 biti) + ASCTy (6), SubChId (6) + P/S + CA. Se tine numai componenta primara audio
        (TMId 0 = flux audio in MSC): subcanalul si felul (ASCTy 63 = DAB+)."""
        i, n = 1, len(fig)
        while i + 3 <= n:
            sid = (fig[i] << 8) | fig[i + 1]
            componente = fig[i + 2] & 0x0F
            i += 3
            for _k in range(componente):
                if i + 2 > n:
                    return
                if fig[i] >> 6 == 0 and fig[i + 1] & 0x02:
                    ascty, subch = fig[i] & 0x3F, fig[i + 1] >> 2
                    p = self._post(sid)
                    if p is not None and (p[1], p[2]) != (ascty, subch):
                        p[1], p[2] = ascty, subch
                        self.ultima_noutate = self.cadre
                i += 2


def eticheta_ebu(b, set_caractere=0):
    """Numele ansamblului sau al postului dintr-o FIG 1, dupa setul de caractere al FIG-ului (text_dvb.eticheta_dab:
    EBU Latin, UTF-8, UCS-2), fara umplutura (spatii sau 0x00) de la capete."""
    return _eticheta_dab(b, set_caractere)


# ---------------------------------------------------------------- TS: T2-MI si ETI
def _sarcini_ts(blocuri, pid, stat):
    """Din blocuri TS -> (pusi, sarcina) pentru pid; numara salturile de contor."""
    ultim = None
    for bloc in blocuri:
        if not bloc:
            continue
        for o in range(0, len(bloc) - 187, 188):
            if bloc[o] != 0x47:
                stat['sincron_pierdut'] += 1
                continue
            if ((bloc[o + 1] & 0x1F) << 8 | bloc[o + 2]) != pid:
                continue
            if bloc[o + 1] & 0x80:
                stat['erori_ts'] += 1
                continue
            b3 = bloc[o + 3]
            if b3 & 0xC0:
                stat['criptat'] += 1
            afc = (b3 >> 4) & 3
            if not afc & 1:
                continue
            cc = b3 & 0x0F
            if ultim is not None and cc != (ultim + 1) & 0x0F and cc != ultim:
                stat['salturi_cc'] += 1
                yield None, None
            ultim = cc
            i = o + 4
            if afc == 3:
                i += 1 + bloc[o + 4]
            if i >= o + 188:
                continue
            stat['pachete'] += 1
            yield bool(bloc[o + 1] & 0x40), bloc[i:o + 188]


def verifica_t2mi(blocuri, pid, max_pachete=4000):
    """Refac pachetele T2-MI si le verific CRC32. -> dict cu confirmarea."""
    stat = {'pachete': 0, 'salturi_cc': 0, 'sincron_pierdut': 0, 'erori_ts': 0, 'criptat': 0}
    buf = bytearray()
    sincron = False
    bune = rele = 0
    tipuri = set()
    plp = set()
    fluxuri = set()
    for pusi, sarcina in _sarcini_ts(blocuri, pid, stat):
        if sarcina is None:
            del buf[:]                    # bytearray.clear() lipseste pe 2.7
            sincron = False
            continue
        if pusi:
            ptr = sarcina[0]
            if not sincron:
                del buf[:]
                if 1 + ptr > len(sarcina):
                    continue
                buf += sarcina[1 + ptr:]
                sincron = True
            else:
                buf += sarcina[1:]
        elif sincron:
            buf += sarcina
        else:
            continue
        o = 0
        while len(buf) - o >= 6:
            pt = buf[o]
            n = 6 + (((buf[o + 4] << 8) | buf[o + 5]) + 7) // 8 + 4
            if pt not in TIPURI_T2MI or n > 65536:
                rele += 1
                sincron = False
                del buf[:]
                o = 0
                break
            if len(buf) - o < n:
                break
            if crc32_mpeg(buf[o:o + n]) == 0:
                bune += 1
                tipuri.add(pt)
                fluxuri.add(buf[o + 3] & 0x07)
                if pt == 0x00 and n > 12:
                    plp.add(buf[o + 7])
            else:
                rele += 1
            o += n
        if o:
            del buf[:o]
        if len(buf) > 70000:
            del buf[:]
            sincron = False
        if stat['pachete'] >= max_pachete:
            break
    return {'confirmat': bune >= 3 and bune > rele, 'pachete_t2mi_bune': bune, 'pachete_t2mi_rele': rele,
            'tipuri': sorted(tipuri), 'plp_uri': sorted(plp), 't2mi_stream_id': sorted(fluxuri), 'ts': stat}


def verifica_eti(blocuri, pid, max_octeti=400000):
    """ETI-NI (FSYNC alternant) sau ETI-NA (FAS G.704 la 64 de octeti), cu 0 sau 12 octeti de umplutura."""
    stat = {'pachete': 0, 'salturi_cc': 0, 'sincron_pierdut': 0, 'erori_ts': 0, 'criptat': 0}
    brut, taiat = bytearray(), bytearray()
    unitati, unitate = [], None
    for pusi, sarcina in _sarcini_ts(blocuri, pid, stat):
        if sarcina is None:
            unitate = None
            continue
        if pusi and len(sarcina) > 1:
            ptr = sarcina[0]
            if unitate is not None:
                unitate += sarcina[1:1 + ptr]
                if len(unitati) < 64:
                    unitati.append(_B(unitate))
            unitate = bytearray(sarcina[1 + ptr:])
        elif unitate is not None and len(unitate) < 16384:
            unitate += sarcina
        brut += sarcina
        if len(sarcina) > 12:
            taiat += sarcina[12:]
        if len(brut) >= max_octeti:
            break
    rez = {'confirmat': False, 'fel': None, 'ts': stat}
    brut, taiat = _B(brut), _B(taiat)
    n0, n1 = brut.count(FSYNC0), brut.count(FSYNC1)
    if n0 >= 2 and n1 >= 2 and abs(n0 - n1) <= max(2, (n0 + n1) // 4):
        rez.update(confirmat=True, fel='tsniv2ni', motiv='FSYNC ETI-NI alternant (%d/%d)' % (n0, n1))
        return rez
    n_li = sum(1 for u in unitati if _li_bun(u))
    if n_li >= 3 and n_li * 2 > len(unitati):
        # ERT (39E), DAB Italia si EuroDab (9E): ETI(LI) fara SYNC, un cadru pe unitate PUSI; eti.cadre_din_tsniv2ni
        # recunoaste singur forma, deci feed-ul ramane „tsniv2ni"
        rez.update(confirmat=True, fel='tsniv2ni', motiv='ETI(LI) pe unitati PUSI, CRC antet bun (%d/%d)'
                   % (n_li, len(unitati)))
        return rez
    for date, fel in ((taiat, 'ts2na12'), (brut, 'ts2na')):
        r = _aliniere_fas(date)
        if r:
            rez.update(confirmat=True, fel=fel, motiv='cuvant de aliniere G.704 la 64 de octeti (%s)' % r)
            return rez
    return rez


def _li_bun(u):
    """Unitatea incepe cu FC ETI(LI) cu CRC-ul antetului (FC + STC + MNSC) bun."""
    if len(u) < 12:
        return False
    nst = u[1] & 0x7F
    h = 4 + 4 * nst + 2
    if nst == 0 or len(u) < h + 2:
        return False
    return (crc16_ccitt(u[:h]) ^ 0xFFFF) == ((u[h] << 8) | u[h + 1])


def _aliniere_fas(date, cadre=160):
    lim = 64 * cadre
    if len(date) < lim + 64:
        return None
    for tab, ordine in ((_FAS_MSB, 'MSB'), (_FAS_LSB, 'LSB'), (_FAS_MSB_NEG, 'MSB negat'), (_FAS_LSB_NEG, 'LSB negat')):
        for off in range(64):
            if sum(tab[b] for b in date[off:off + lim:64]) >= cadre * 0.95:
                return '%s, decalaj %d' % (ordine, off)
    return None


# ---------------------------------------------------------------- consum cu termen
def _citeste(fn, pid, termen, ceas, pana_cand=None, erori=None):
    """Consuma sursa pana la termen; opreste cand pana_cand(sectiune) intoarce True."""
    rest = termen - ceas()
    if rest <= 0.05:
        return
    try:
        it = iter(fn(pid, rest))
    except Exception as e:                # sursa nu se poate deschide: se trece mai departe
        if erori is not None and len(erori) < 20:
            erori.append('%s pe PID %d' % (e.__class__.__name__, pid))
        return
    try:
        while True:
            try:
                x = next(it)
            except StopIteration:
                break
            except Exception as e:        # sursa a cazut in mijloc (flux oprit, demux inchis)
                if erori is not None and len(erori) < 20:
                    erori.append('%s pe PID %d' % (e.__class__.__name__, pid))
                break
            if x is not None:
                yield x
            if ceas() >= termen or (pana_cand is not None and pana_cand()):
                break
    finally:
        inchide = getattr(it, 'close', None)
        if inchide:
            try:
                inchide()
            except Exception:
                pass


# ---------------------------------------------------------------- detectorul
def _cheie_cunoscuta(f):
    return (f.get('pid'), f.get('ip'), f.get('port')) if f.get('fel') == 'edi' else (f.get('pid'),)


def detecteaza(sectiuni, pachete_ts=None, timp_max=15.0, cunoscute=None, ceas=_monoton,
               max_sectiuni_mpe=10000, tip=None, la_progres=None):
    """Cauta fluxurile noastre pe transponderul acordat. Nu arunca exceptii pentru date rele.
    tip: 'dab' (EDI, ETI-NA, ETI-NI), 't2' (T2-MI) sau None (amandoua). Fiecare plugin cere doar tipul lui.
    Un PID cu EDI se citeste pana cand fiecare ansamblu de pe el are lista posturilor completa (GrupEDI.complet),
    cel mult TIMP_PID_MPE_S. la_progres(dict), daca e dat, primeste fiecare ansamblu gasit imediat dupa PID-ul lui
    (nume, ansamblu, numarul posturilor), ca scanerul sa arate ce a gasit pana atunci."""
    if tip not in (None, 'dab', 't2'):
        raise ValueError('tip trebuie sa fie dab, t2 sau None')
    vrea_dab, vrea_t2 = tip != 't2', tip != 'dab'
    start = ceas()
    termen_total = start + max(1.0, float(timp_max))
    rez = {'versiune': 1, 'tip': tip, 'feeduri': [], 'candidati': [], 'alte_ip': [], 'programe': {},
           'stare': {'sectiuni_rele': 0, 'pmt_lipsa': [], 'terminat': 'gata'}}
    stare = rez['stare']
    erori = stare['erori_sursa'] = []

    def citeste(fn, pid, t, oprire=None):
        return _citeste(fn, pid, t, ceas, oprire, erori)
    cunoscute = [f for f in (cunoscute or []) if isinstance(f, dict) and (tip is None or f.get('tip') == tip)]
    dupa_cheie = {}
    for f in cunoscute:
        dupa_cheie.setdefault(_cheie_cunoscuta(f), f.get('id'))

    def termen(max_s, fractie=1.0):
        rest = termen_total - ceas()
        return ceas() + max(0.0, min(max_s, rest * fractie))

    # ---- PAT
    pat, vazute = {}, set()
    ultima = [None]

    def pat_complet():
        return ultima[0] is not None and len(vazute) > ultima[0]

    for s in citeste(sectiuni, PID_PAT, termen(2.5), pat_complet):
        s = sectiune_valida(s)
        if s is None or s[0] != TID_PAT or not s[1] & 0x80:
            stare['sectiuni_rele'] += 1
            continue
        if not s[5] & 0x01:
            continue
        ultima[0] = s[7]
        vazute.add(s[6])
        pat.update(_pat(s))
    stare['pat'] = bool(pat)

    # ---- PMT (cel mult jumatate din timpul ramas)
    pe_pid = {}
    for prog, pid in pat.items():
        pe_pid.setdefault(pid, set()).add(prog)
    es_toate = {}                     # pid es -> info (+ program)
    termen_pmt = termen(termen_total - ceas(), 0.5)
    for pmt_pid in sorted(pe_pid):
        ramase = set(pe_pid[pmt_pid])
        for s in citeste(sectiuni, pmt_pid, min(termen_pmt, ceas() + 1.5), lambda: not ramase):
            s = sectiune_valida(s)
            if s is None or s[0] != TID_PMT or not s[1] & 0x80:
                stare['sectiuni_rele'] += 1
                continue
            try:
                prog, es = _pmt(s)
            except IndexError:
                stare['sectiuni_rele'] += 1
                continue
            if prog not in ramase:
                continue
            ramase.discard(prog)
            rez['programe'][prog] = {'pmt_pid': pmt_pid, 'es': [[e['pid'], e['stream_type']] for e in es]}
            for e in es:
                e['program'] = prog
                es_toate.setdefault(e['pid'], e)
        stare['pmt_lipsa'].extend(sorted(ramase))
        if ceas() >= termen_pmt:
            break

    # ---- clasificare
    mpe, private, t2 = [], [], []
    for pid, e in sorted(es_toate.items()):
        st, tg = e['stream_type'], set(e['taguri'])
        if e['t2mi']:
            t2.append((pid, 'T2MI_descriptor in PMT (EN 300 468 6.4.14)'))
        elif st in TIP_VIDEO or st in TIP_AUDIO or st in TIP_IGNORAT:
            continue
        elif e['dbid'] == DBID_MPE:
            mpe.append((pid, 'data_broadcast_id 0x0005 (MPE)'))
        elif e['dbid'] in DBID_NU_E_MPE or tg & {0x13, 0x14, 0x6F}:
            continue
        elif st in TIP_DSMCC:
            mpe.append((pid, 'stream_type 0x%02X (DSM-CC)' % st))
        elif st == 0x05:
            mpe.append((pid, 'stream_type 0x05 (sectiuni private)'))
        elif st == 0x06 or st >= 0x80:
            if tg & DESC_NU_E_AL_NOSTRU:
                continue
            private.append((pid, 'stream_type 0x%02X fara descriptori de sunet sau subtitrare' % st))
    in_pmt = set(es_toate)
    for f in cunoscute:
        pid = f.get('pid')
        if isinstance(pid, int) and pid not in in_pmt:
            if f.get('fel') == 'edi':
                mpe.append((pid, 'din lista (nu apare in PMT)'))
            elif f.get('tip') == 't2':
                t2.append((pid, 'din lista (nu apare in PMT)'))
            else:
                private.append((pid, 'din lista (nu apare in PMT)'))
            in_pmt.add(pid)
    if not vrea_t2:
        t2 = []
    if not vrea_dab:
        mpe = []                       # PID-urile private se probeaza scurt ca sa fie scoase cele MPE

    def nume_program(pid):
        e = es_toate.get(pid)
        return e and e.get('program')

    # ---- MPE si PID-uri private: sectiuni 0x3E
    grupuri = {}                       # (pid, ip, port) -> [GrupEDI, pachete, octeti]
    fara_sectiuni = []
    de_probat = [(p, m, True) for p, m in mpe] + [(p, m, False) for p, m in private]
    for idx, (pid, motiv, e_mpe) in enumerate(de_probat):
        ramase_pid = len(de_probat) - idx
        buget = max(0.4, (termen_total - ceas() - 1.0) / ramase_pid)
        t_pid = termen(min(TIMP_PID_MPE_S, buget))
        pornit = ceas()
        n_mpe = [0]
        ale_pid = []

        def destul(e_mpe=e_mpe, pornit=pornit, n_mpe=n_mpe, ale_pid=ale_pid):
            edi = [g for g in ale_pid if g[0].pare_edi()]
            # plafonul de sectiuni creste cu ansamblurile de pe PID: 15 ansambluri pe acelasi PID (7E) dau de 15 ori
            # mai multe sectiuni pentru aceeasi lista de posturi; unul complet costa numai numaratoarea
            if n_mpe[0] >= max(max_sectiuni_mpe, SECTIUNI_PE_ANSAMBLU * len(edi)):
                return True
            trecut = ceas() - pornit
            if trecut < 1.0:
                return False
            if not edi:
                # fara EDI: un PID privat se lasa dupa o secunda, unul anuntat ca MPE dupa trei (ca inainte)
                return not e_mpe or trecut >= 3.0
            return all(g[0].complet() for g in edi)

        vazut_ceva = False
        for s in citeste(sectiuni, pid, t_pid, destul):
            s = sectiune_valida(s)
            if s is None:
                stare['sectiuni_rele'] += 1
                continue
            if s[0] != TID_MPE:
                continue
            n_mpe[0] += 1
            verif = n_mpe[0] <= 20 and bool(s[1] & 0x80)
            if verif and crc32_mpeg(s) != 0:
                stare['mpe_crc_rele'] = stare.get('mpe_crc_rele', 0) + 1
                continue
            try:
                u = udp_din_sectiune_mpe(s)
            except IndexError:
                u = None
            if u is None:
                continue
            # abia un datagram IP/UDP intreg arata MPE; gunoiul dat de filtru pe un PID de date brute
            # (T2-MI, ETI) poate incepe si el cu 0x3E
            vazut_ceva = True
            ip, port, sarcina, _mf = u
            k = (pid, ip, port)
            g = grupuri.get(k)
            if g is None:
                if len(grupuri) >= 256:
                    continue
                g = grupuri[k] = [GrupEDI(), 0, 0]
                ale_pid.append(g)
            g[1] += 1
            g[2] += len(sarcina)
            try:
                g[0].adauga(sarcina)
            except (IndexError, ValueError, KeyError):
                g[0].rele += 1
        if not vazut_ceva and not e_mpe:
            fara_sectiuni.append((pid, motiv))
        elif not vazut_ceva and e_mpe:
            rez['candidati'].append({'pid': pid, 'tip': 'dab', 'fel': 'edi', 'confirmat': False,
                                     'motiv': motiv + '; nu au venit sectiuni 0x3E in timpul dat'})
        if la_progres is not None and vrea_dab:
            for g in ale_pid:
                if g[0].gata() and g[0].pare_edi():
                    try:
                        la_progres({'nume': g[0].nume, 'ansamblu': '%04X' % g[0].eid,
                                    'posturi': len(g[0].lista_posturi())})
                    except Exception:
                        pass

    for (pid, ip, port), (g, pachete, octeti) in sorted(grupuri.items(), key=lambda x: x[0]):
        if not vrea_dab:
            continue
        if g.pare_edi() and g.pf + g.af > g.rele:
            posturi = g.lista_posturi()
            f = {'id': 'det_edi_%04x_%s_%d' % (pid, ip.replace('.', '_').replace(':', '_'), port),
                 'tip': 'dab', 'fel': 'edi', 'pid': pid, 'ip': ip, 'port': port,
                 'ansamblu': '%04X' % g.eid if g.eid is not None else None,
                 'nume': g.nume or 'EDI %s:%d' % (ip, port),
                 'confirmat': True,
                 'motiv': 'EDI prin MPE: %d PF, %d AF valide%s; %d posturi%s' % (
                     g.pf, g.af, (', *ptr ' + g.ptr) if g.ptr else '', len(posturi),
                     '' if g.complet() else ' (lista posturilor incompleta)'),
                 'program': nume_program(pid), 'cunoscut': dupa_cheie.get((pid, ip, port))}
            if posturi:
                f['posturi'] = posturi
            rez['feeduri'].append(f)
        else:
            rez['alte_ip'].append({'pid': pid, 'ip': ip, 'port': port, 'pachete': pachete, 'octeti': octeti})

    # ---- T2-MI si ETI: pe sectiuni nu se vad; confirmare doar din TS
    candidati_ts = [(p, m, 't2') for p, m in t2] + [(p, m, '?') for p, m in fara_sectiuni]
    for idx, (pid, motiv, tip_c) in enumerate(candidati_ts):
        if tip_c == '?':
            tip_c = 't2' if not vrea_dab else ('dab' if not vrea_t2 else 't2 sau dab')
        fel_c = {'t2': 't2mi', 'dab': 'eti', 't2 sau dab': 't2mi sau eti'}[tip_c]
        cand = {'pid': pid, 'tip': tip_c, 'fel': fel_c,
                'confirmat': False, 'motiv': motiv + '; nu e in sectiuni (data piping), trebuie TS',
                'program': nume_program(pid), 'cunoscut': dupa_cheie.get((pid,))}
        e = es_toate.get(pid)
        if e and e.get('t2mi'):
            cand.update(e['t2mi'])
        if pachete_ts is not None and termen_total - ceas() > 0.3:
            buget = max(0.3, (termen_total - ceas()) / (len(candidati_ts) - idx))
            t_pid = termen(min(2.0, buget))
            try:
                blocuri = list(citeste(pachete_ts, pid, t_pid))
                v = verifica_t2mi(blocuri, pid) if vrea_t2 else {'confirmat': False, 'pachete_t2mi_bune': 0,
                                                                 'ts': {'pachete': len(blocuri)}}
                if v['confirmat']:
                    f = {'id': 'det_t2_%04x' % pid, 'tip': 't2', 'fel': 't2mi', 'pid': pid,
                         'plp': v['plp_uri'][0] if v['plp_uri'] else None, 'plp_uri': v['plp_uri'],
                         'nume': 'DVB-T2 PID %d' % pid, 'confirmat': True,
                         'motiv': 'T2-MI: %d pachete cu CRC32 bun' % v['pachete_t2mi_bune'],
                         'program': cand['program'], 'cunoscut': cand['cunoscut']}
                    rez['feeduri'].append(f)
                    continue
                w = verifica_eti(blocuri, pid) if vrea_dab else {'confirmat': False}
                if w['confirmat']:
                    rez['feeduri'].append({'id': 'det_eti_%04x' % pid, 'tip': 'dab', 'fel': w['fel'], 'pid': pid,
                                           'nume': 'ETI PID %d' % pid, 'confirmat': True, 'motiv': w['motiv'],
                                           'program': cand['program'], 'cunoscut': cand['cunoscut']})
                    continue
                cand['motiv'] += '; TS citit, neconfirmat (%d pachete TS, %d T2-MI bune)' % (
                    v['ts']['pachete'], v['pachete_t2mi_bune'])
            except Exception as ex:       # sursa TS poate cadea; detectorul nu
                cand['motiv'] += '; TS indisponibil: %s' % ex.__class__.__name__
        rez['candidati'].append(cand)

    # ---- SDT pentru nume (doar daca a mai ramas timp)
    if termen_total - ceas() > 0.5 and (rez['feeduri'] or rez['candidati']):
        servicii = {}
        sec_sdt = set()
        ultima_sdt = [None]
        for s in citeste(sectiuni, PID_SDT, termen(2.2),
                          lambda: ultima_sdt[0] is not None and len(sec_sdt) > ultima_sdt[0]):
            s = sectiune_valida(s)
            if s is None or s[0] != TID_SDT or not s[1] & 0x80:
                continue
            try:
                servicii.update(_sdt(s))
            except IndexError:
                continue
            ultima_sdt[0] = s[7]
            sec_sdt.add(s[6])
        for f in rez['feeduri'] + rez['candidati']:
            srv = servicii.get(f.get('program'))
            if srv:
                f['serviciu'] = srv['nume']
                # numele din FIC ramane; numele generate (EDI ip:port, ETI PID, DVB-T2 PID) se inlocuiesc
                if srv['nume'] and 'nume' in f and f['nume'].startswith(('EDI ', 'ETI ', 'DVB-T2 ')):
                    f['nume'] = srv['nume']
        rez['servicii'] = {str(k): v for k, v in sorted(servicii.items())}

    durata = ceas() - start
    stare['durata_s'] = round(durata, 2)
    if ceas() >= termen_total:
        stare['terminat'] = 'timp_depasit'
    rez['programe'] = {str(k): v for k, v in sorted(rez['programe'].items())}
    return rez


# ---------------------------------------------------------------- sursa reala (Linux DVB), doar pe receptor
def sursa_demux(adapter=0, demux=0):
    """Filtru de sectiuni pe PID, fara masca (asa merge pe HiSilicon). Nu se foloseste pe PC."""
    import fcntl
    import os
    import select
    DMX_SET_FILTER, DMX_STOP, DMX_SET_BUFFER_SIZE = 0x403C6F2B, 0x6F2A, 0x6F2D
    cale = '/dev/dvb/adapter%d/demux%d' % (adapter, demux)

    def sectiuni(pid, timp_s):
        fd = os.open(cale, os.O_RDONLY | os.O_NONBLOCK)
        try:
            try:
                fcntl.ioctl(fd, DMX_SET_BUFFER_SIZE, 256 * 1024)
            except OSError:
                pass
            fcntl.ioctl(fd, DMX_SET_FILTER, struct.pack('=H2x16s16s16sII', pid, b'\0' * 16, b'\0' * 16,
                                                        b'\0' * 16, 0, 4))
            gata = _monoton() + timp_s
            while True:
                rest = gata - _monoton()
                if rest <= 0:
                    return
                r, _, _ = select.select([fd], [], [], min(rest, 0.25))
                if not r:
                    yield None
                    continue
                try:
                    yield os.read(fd, 4096)
                except OSError:
                    yield None
        finally:
            try:
                fcntl.ioctl(fd, DMX_STOP)
            except OSError:
                pass
            os.close(fd)
    return sectiuni


def _progres_pe_stderr(x):
    """Un ansamblu gasit, ca rand „HDS-GASIT {json}" pe stderr: scanare.Scanare il citeste cat detectorul lucreaza
    (iesirea standard ramane numai rezultatul JSON de la sfarsit)."""
    try:
        sys.stderr.write('HDS-GASIT %s\n' % json.dumps(x, ensure_ascii=True, sort_keys=True))
        sys.stderr.flush()
    except Exception:
        pass


def main(argv):
    # argumentele in orice ordine: scanare.py trimite „<timp> <tip>", documentatia spune „<tip> <timp>"
    tip, timp = None, 25.0
    for a in argv[1:3]:
        if a in ('dab', 't2', 'toate'):
            tip = a if a != 'toate' else None
        else:
            try:
                timp = float(a)
            except ValueError:
                pass
    try:
        __import__('os').nice(10)
    except (AttributeError, OSError):
        pass
    rez = detecteaza(sursa_demux(), None, timp, tip=tip, la_progres=_progres_pe_stderr)
    sys.stdout.write(text_iesire(rez))
    return 0


def text_iesire(rez):
    """Raspunsul pentru stdout, numai ASCII (literele din numele posturilor ca \\uXXXX). Enigma2 citeste teava cate
    2048 de octeti si decodeaza fiecare bucata separat (UTF-8 cu inlocuire): o litera de doi octeti taiata la granita
    s-ar strica. Pe Python 2.7 json.dumps cu ensure_ascii da tot str."""
    text = json.dumps(rez, ensure_ascii=True, indent=1) + '\n'
    if not isinstance(text, str):
        text = text.encode('ascii')
    return text


# ---------------------------------------------------------------- Python 2.7
if sys.version_info[0] < 3:
    # Pe 2.7 sursele dau str si str[i] e un sir de 1 caracter: `s[1] & 0x80` ar crapa, iar `bloc[o] != 0x47` ar fi
    # mereu adevarat, tacut. Datele se fac bytearray o singura data, cand intra in detector (sursa sau apelul direct);
    # ce e deja bytearray trece fara copie. Pe Python 3 nimic de aici nu exista.
    def _ba(x):
        return x if type(x) is bytearray else bytearray(x)

    def _cu_bytearray(fn):
        def f(date, *a, **k):
            return fn(_ba(date), *a, **k)
        f.__name__ = fn.__name__
        return f

    def _blocuri_bytearray(fn):
        def f(blocuri, *a, **k):
            return fn([_ba(b) for b in blocuri], *a, **k)
        f.__name__ = fn.__name__
        return f

    crc32_mpeg, crc16_ccitt, crc16_ok = _cu_bytearray(crc32_mpeg), _cu_bytearray(crc16_ccitt), _cu_bytearray(crc16_ok)
    eticheta_ebu, _li_bun = _cu_bytearray(eticheta_ebu), _cu_bytearray(_li_bun)
    _pat, _pmt, _sdt = _cu_bytearray(_pat), _cu_bytearray(_pmt), _cu_bytearray(_sdt)
    udp_din_sectiune_mpe = _cu_bytearray(udp_din_sectiune_mpe)
    verifica_t2mi, verifica_eti = _blocuri_bytearray(verifica_t2mi), _blocuri_bytearray(verifica_eti)
    _sectiune_valida_3 = sectiune_valida

    def sectiune_valida(s):
        return None if s is None else _sectiune_valida_3(_ba(s))

    _GrupEDI_adauga_3 = GrupEDI.adauga

    def _adauga_2(self, p):
        return _GrupEDI_adauga_3(self, _ba(p))
    GrupEDI.adauga = _adauga_2

    _citeste_3 = _citeste

    def _citeste(fn, pid, termen, ceas, pana_cand=None, erori=None):
        for x in _citeste_3(fn, pid, termen, ceas, pana_cand, erori):
            yield _ba(x)


if __name__ == '__main__':
    sys.exit(main(sys.argv))

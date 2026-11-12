# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Decodarea sunetului in software, pentru placile al caror decodor nu stie un fel de sunet din fluxurile noastre.
Facut de hdsatelit.com.

Primul folositor: releul DAB+ din satelit (dab/motor/releu_dab.py). AAC-ul DAB+ are cadre de 960 de esantioane
(HE-AAC v1/v2, SBR si PS semnalate implicit). Decodorul HiSilicon (facut pe FDK) le stie; decodoarele Broadcom (Vu+)
sunt facute pentru DVB (cadre de 1024) si, pe Vu+ Uno 4K SE, postul se aude sacadat (forumul 801 #1562). Aici:
  AU AAC (fara LOAS) -> faad2 (libfaad.so.2, GPL-2.0-only, stie cadrele de 960 cu SBR si PS) -> PCM 16 biti intercalat
  PCM -> MPEG-1 Layer II (libtwolame.so.0, LGPL-2.1) -> cadre MP2: ce reda orice placa, ca radioul DVB obisnuit.
Bibliotecile se incarca prin ctypes, numai cand e nevoie (functii cu argumente simple, fara structuri care se schimba de
la o versiune la alta). Fara ele, sau daca proba de pornire nu iese, releul ramane pe decodorul placii si spune de ce
in /stare. Nimic nu se face esantion cu esantion in Python.

Cine decodeaza (alege): setarea „automat” (implicita) = decodorul placii pe HiSilicon (exista dosarul /proc/hisi/msp
sau /proc/msp; nu se citeste nimic din el, pe SF8008 citirea poate opri nucleul), software pe toate celelalte (Broadcom,
adica Vu+, si orice placa noua, nestiuta); „placa” si „software” sunt fortate.

Refolosibil: Transcodor primeste (AU, PTS, durata in 90 kHz) si da (cadru MP2, PTS in 90 kHz) cu timpul continuu: o AU
lipsa sau stricata devine liniste de aceeasi durata, un salt mare in PTS reancoreaza. Alt flux cu sunet pe care placa nu-l
stie are nevoie numai de alt decodor cu aceeasi interfata ca DecodorAac (decodeaza(au) -> (pcm, rata, canale) sau None).
Probat pe Python 3 (3.12 pe PC, 3.14 al imaginii); scris fara nimic numai-Python-3, dar neprobat pe 2.7."""
from __future__ import division

import ctypes
import os
import time

SETARI = ('automat', 'placa', 'software')
SETARE_IMPLICITA = 'automat'
MOD_PLACA = 'placa'
MOD_SOFTWARE = 'software'

# numele bibliotecilor (soname); HDS_SUNET_LIB = un dosar cautat intai (probele de pe PC si de pe receptor, din /tmp)
LIB_FAAD = 'libfaad.so.2'
LIB_TWOLAME = 'libtwolame.so.0'
ENV_DOSAR = 'HDS_SUNET_LIB'

# HiSilicon: decodorul AAC al placii stie cadrele de 960 (proba D pe .122; lucru-sesiune/pilot-26-09/dab-2/dab-2-progres.md)
DOSARE_HISILICON = ('proc/hisi/msp', 'proc/msp')

FAAD_FMT_16BIT = 1
TWOLAME_JOINT_STEREO = 1
TWOLAME_MONO = 3
# debitul MP2 (kbit/s): fluxul nu iese din receptor (127.0.0.1), deci cat mai sus din ce folosesc posturile DVB obisnuite
# (320 kbit/s, ca radiourile ARD pe Astra; 384 e voie dupa norma, dar rar). Masurat pe SUNSHINE LIVE (HE-AAC 48 kHz),
# fata de decodarea de referinta, mediana pe ferestre de 5 s: 192 kbit/s 15,0 dB, 256 27,0 dB, 320 31,7 dB, 384 34,8 dB
# (teste/asculta_sunet_software.py). Mono: cel mult 192 dupa norma.
KBIT_STEREO = 320
KBIT_MONO = 160
# modelul psihoacustic al lui twolame (-1..4, implicit al lui 3): 0 e cel mai ieftin cu model; la debitul de mai sus
# diferenta fata de 3 nu se vede in masuratoare (26,1 dB cu 3, 27,0 cu 0, la 256 kbit/s), iar 3 costa de doua ori mai mult
PSY_IMPLICIT = 0
ESANTIOANE_MP2 = 1152            # MPEG-1/2 Layer II: un cadru = 1152 de esantioane pe canal
MASCA_33 = (1 << 33) - 1
SALT_MAX_90K = 2 * 90000         # gol in sursa peste atat (sau PTS inapoi): timpul se reancoreaza, fara liniste
BUFFER_MP2 = 32768               # loc pentru cadrele iesite dintr-un apel twolame
BUCATA_PCM = 8192                # esantioane pe canal intr-un apel: cel mult 8 cadre (<= 8 x 1728 octeti) in BUFFER_MP2

try:
    _ceas_fir = time.thread_time          # Python 3.7+: numai firul care decodeaza
except AttributeError:
    _ceas_fir = getattr(time, 'process_time', None) or time.clock     # noqa: Python 2.7


class Lipsa(Exception):
    """Decodarea software nu se poate face aici (biblioteca lipsa, functie lipsa, proba de pornire esuata)."""


# ---------------------------------------------------------------- cine decodeaza
def placa_hisilicon(radacina='/'):
    """True pe HiSilicon (dosarul driverului exista). Numai os.path.isdir, nicio citire."""
    for d in DOSARE_HISILICON:
        try:
            if os.path.isdir(os.path.join(radacina, d)):
                return True
        except Exception:
            pass
    return False


def alege(setare, radacina='/'):
    """Setarea omului -> (mod, motiv); mod = 'placa' sau 'software'. Disponibilitatea bibliotecilor nu se verifica aici
    (vezi disponibil)."""
    setare = setare if setare in SETARI else SETARE_IMPLICITA
    if setare == MOD_PLACA:
        return MOD_PLACA, 'setarea: placa'
    if setare == MOD_SOFTWARE:
        return MOD_SOFTWARE, 'setarea: software'
    if placa_hisilicon(radacina):
        return MOD_PLACA, 'automat: HiSilicon stie DAB+'
    return MOD_SOFTWARE, 'automat: placa nu e HiSilicon'


# ---------------------------------------------------------------- bibliotecile
_LIB = {}


def _incarca(nume):
    if nume in _LIB:
        lib = _LIB[nume]
        if isinstance(lib, Lipsa):
            raise lib
        return lib
    dosar = os.environ.get(ENV_DOSAR)
    incercari = ([os.path.join(dosar, nume)] if dosar else []) + [nume]
    ultima = None
    for cale in incercari:
        try:
            lib = ctypes.CDLL(cale)
            _LIB[nume] = lib
            return lib
        except OSError as e:
            ultima = e
    eroare = Lipsa('lipseste %s (%s)' % (nume, ultima))
    _LIB[nume] = eroare
    raise eroare


class _ConfFaad(ctypes.Structure):
    _fields_ = [('defObjectType', ctypes.c_ubyte), ('defSampleRate', ctypes.c_ulong),
                ('outputFormat', ctypes.c_ubyte), ('downMatrix', ctypes.c_ubyte),
                ('useOldADTSFormat', ctypes.c_ubyte), ('dontUpSampleImplicitSBR', ctypes.c_ubyte)]


class _InfoFaad(ctypes.Structure):
    _fields_ = [('bytesconsumed', ctypes.c_ulong), ('samples', ctypes.c_ulong), ('channels', ctypes.c_ubyte),
                ('error', ctypes.c_ubyte), ('samplerate', ctypes.c_ulong), ('sbr', ctypes.c_ubyte),
                ('object_type', ctypes.c_ubyte), ('header_type', ctypes.c_ubyte),
                ('num_front_channels', ctypes.c_ubyte), ('num_side_channels', ctypes.c_ubyte),
                ('num_back_channels', ctypes.c_ubyte), ('num_lfe_channels', ctypes.c_ubyte),
                ('channel_position', ctypes.c_ubyte * 64), ('ps', ctypes.c_ubyte)]


def _faad():
    lib = _incarca(LIB_FAAD)
    if getattr(lib, '_hds_gata', False):
        return lib
    try:
        lib.NeAACDecOpen.restype = ctypes.c_void_p
        lib.NeAACDecOpen.argtypes = []
        lib.NeAACDecGetCurrentConfiguration.restype = ctypes.POINTER(_ConfFaad)
        lib.NeAACDecGetCurrentConfiguration.argtypes = [ctypes.c_void_p]
        lib.NeAACDecSetConfiguration.restype = ctypes.c_ubyte
        lib.NeAACDecSetConfiguration.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ConfFaad)]
        lib.NeAACDecInit2.restype = ctypes.c_byte
        lib.NeAACDecInit2.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ulong,
                                      ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ubyte)]
        lib.NeAACDecDecode.restype = ctypes.c_void_p
        lib.NeAACDecDecode.argtypes = [ctypes.c_void_p, ctypes.POINTER(_InfoFaad), ctypes.c_char_p, ctypes.c_ulong]
        lib.NeAACDecClose.restype = None
        lib.NeAACDecClose.argtypes = [ctypes.c_void_p]
        lib.NeAACDecGetErrorMessage.restype = ctypes.c_char_p
        lib.NeAACDecGetErrorMessage.argtypes = [ctypes.c_ubyte]
    except AttributeError as e:
        raise Lipsa('%s fara functia %s' % (LIB_FAAD, e))
    lib._hds_gata = True
    return lib


def _twolame():
    lib = _incarca(LIB_TWOLAME)
    if getattr(lib, '_hds_gata', False):
        return lib
    try:
        lib.twolame_init.restype = ctypes.c_void_p
        lib.twolame_init.argtypes = []
        for f in ('twolame_set_in_samplerate', 'twolame_set_out_samplerate', 'twolame_set_num_channels',
                  'twolame_set_mode', 'twolame_set_bitrate', 'twolame_set_psymodel'):
            getattr(lib, f).restype = ctypes.c_int
            getattr(lib, f).argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.twolame_init_params.restype = ctypes.c_int
        lib.twolame_init_params.argtypes = [ctypes.c_void_p]
        lib.twolame_encode_buffer_interleaved.restype = ctypes.c_int
        lib.twolame_encode_buffer_interleaved.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                                          ctypes.c_void_p, ctypes.c_int]
        lib.twolame_close.restype = None
        lib.twolame_close.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    except AttributeError as e:
        raise Lipsa('%s fara functia %s' % (LIB_TWOLAME, e))
    lib._hds_gata = True
    return lib


def disponibil():
    """(True, '') cand ambele biblioteci se incarca si codorul MP2 face un cadru bun din liniste; altfel (False, motiv).
    Rezultatul se tine minte (proba se face o singura data pe proces)."""
    if 'proba' in _LIB:
        return _LIB['proba']
    try:
        _faad()
        c = CodorMp2(48000, 2)
        try:
            iesit = c.codeaza(b'\0' * (ESANTIOANE_MP2 * 4))
        finally:
            c.inchide()
        cadre, rest = cadre_mp2(iesit)
        if len(cadre) != 1 or rest or len(cadre[0]) != 144 * KBIT_STEREO * 1000 // 48000:
            raise Lipsa('proba twolame: %d cadre, %d octeti' % (len(cadre), len(iesit)))
        rez = (True, '')
    except Lipsa as e:
        rez = (False, str(e))
    except Exception as e:                      # orice altceva tot pe placa: releul nu are voie sa cada de aici
        rez = (False, '%s: %s' % (type(e).__name__, e))
    _LIB['proba'] = rez
    return rez


# ---------------------------------------------------------------- AAC DAB+ -> PCM
FREC_INDEX = {96000: 0, 88200: 1, 64000: 2, 48000: 3, 44100: 4, 32000: 5, 24000: 6, 22050: 7, 16000: 8,
              12000: 9, 11025: 10, 8000: 11}


def asc_dab(rata_baza, canale_baza):
    """AudioSpecificConfig pentru AAC-ul DAB+ (ETSI TS 102 563): AAC LC (AOT 2), rata si canalele nucleului, cadre de
    960 (frameLengthFlag=1). SBR si PS raman semnalate implicit: faad2 presupune SBR la nucleu <= 24 kHz si da stereo
    cand poate veni PS (asa face si dablin)."""
    i = FREC_INDEX[rata_baza]
    return bytes(bytearray([(2 << 3) | (i >> 1), ((i & 1) << 7) | ((canale_baza & 15) << 3) | 0b100]))


class DecodorAac(object):
    """faad2 pe AU-uri AAC brute (fara LOAS/ADTS), cu AudioSpecificConfig dat. decodeaza(au) -> (pcm, rata, canale):
    pcm = octeti S16 intercalati (pot fi 0 la primele AU); None cand AU e stricata (se numara in erori)."""

    def __init__(self, asc):
        self.lib = lib = _faad()
        self.h = lib.NeAACDecOpen()
        if not self.h:
            raise Lipsa('NeAACDecOpen')
        conf = lib.NeAACDecGetCurrentConfiguration(self.h)
        conf.contents.outputFormat = FAAD_FMT_16BIT
        conf.contents.dontUpSampleImplicitSBR = 0
        conf.contents.downMatrix = 0
        if lib.NeAACDecSetConfiguration(self.h, conf) != 1:
            self.inchide()
            raise Lipsa('NeAACDecSetConfiguration')
        rata, canale = ctypes.c_ulong(0), ctypes.c_ubyte(0)
        r = lib.NeAACDecInit2(self.h, asc, len(asc), ctypes.byref(rata), ctypes.byref(canale))
        if r != 0:
            self.inchide()
            raise Lipsa('NeAACDecInit2: %d' % r)
        self.rata_init, self.canale_init = rata.value, canale.value
        self.info = _InfoFaad()
        self.erori = 0
        self.ultima_eroare = ''

    def decodeaza(self, au):
        if not isinstance(au, bytes):
            au = bytes(au)
        info = self.info
        p = self.lib.NeAACDecDecode(self.h, ctypes.byref(info), au, len(au))
        if info.error:
            self.erori += 1
            m = self.lib.NeAACDecGetErrorMessage(info.error)
            self.ultima_eroare = m.decode('ascii', 'replace') if isinstance(m, bytes) else str(m)
            return None
        n = info.samples
        pcm = ctypes.string_at(p, n * 2) if p and n else b''
        return pcm, info.samplerate, info.channels or 1

    def inchide(self):
        h, self.h = getattr(self, 'h', None), None
        if h:
            self.lib.NeAACDecClose(h)

    def __del__(self):
        try:
            self.inchide()
        except Exception:
            pass


# ---------------------------------------------------------------- PCM -> MP2
_KBIT_L2 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384)            # MPEG-1 Layer II
_KBIT_L2_LSF = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)            # MPEG-2 LSF Layer II
_RATE = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000)}                             # dupa ID-ul versiunii


def lungime_cadru_mp2(antet):
    """Lungimea unui cadru Layer II din primii 4 octeti, sau 0 cand nu e un antet bun."""
    b = bytearray(antet[:4])
    if len(b) < 4 or b[0] != 0xFF or (b[1] & 0xE0) != 0xE0:
        return 0
    versiune = (b[1] >> 3) & 3
    strat = (b[1] >> 1) & 3
    ib = b[2] >> 4
    ir = (b[2] >> 2) & 3
    if strat != 2 or versiune not in _RATE or ib in (0, 15) or ir == 3:
        return 0
    kbit = (_KBIT_L2 if versiune == 3 else _KBIT_L2_LSF)[ib]
    return 144 * kbit * 1000 // _RATE[versiune][ir] + ((b[2] >> 1) & 1)


def cadre_mp2(date):
    """Octetii iesiti din codor -> ([cadru, ...], rest). Codorul da numai cadre intregi; restul ramane gol."""
    cadre = []
    o, n = 0, len(date)
    while o + 4 <= n:
        lung = lungime_cadru_mp2(date[o:o + 4])
        if not lung or o + lung > n:
            break
        cadre.append(date[o:o + lung])
        o += lung
    return cadre, date[o:]


class CodorMp2(object):
    """twolame: PCM S16 intercalat -> octetii cadrelor MP2 iesite (intregi)."""

    def __init__(self, rata, canale, kbit=None, psy=PSY_IMPLICIT):
        self.lib = lib = _twolame()
        self.rata, self.canale = int(rata), int(canale)
        if self.canale not in (1, 2):
            raise Lipsa('MP2 cu %d canale' % self.canale)
        self.kbit = int(kbit or (KBIT_STEREO if self.canale == 2 else KBIT_MONO))
        self.o = lib.twolame_init()
        if not self.o:
            raise Lipsa('twolame_init')
        rez = [lib.twolame_set_in_samplerate(self.o, self.rata), lib.twolame_set_out_samplerate(self.o, self.rata),
               lib.twolame_set_num_channels(self.o, self.canale),
               lib.twolame_set_mode(self.o, TWOLAME_JOINT_STEREO if self.canale == 2 else TWOLAME_MONO),
               lib.twolame_set_bitrate(self.o, self.kbit), lib.twolame_set_psymodel(self.o, int(psy))]
        if any(rez) or lib.twolame_init_params(self.o) != 0:
            self.inchide()
            raise Lipsa('twolame: parametri respinsi (%d Hz, %d canale, %d kbit/s)' % (self.rata, self.canale, self.kbit))
        self._buf = ctypes.create_string_buffer(BUFFER_MP2)

    def codeaza(self, pcm):
        if not pcm:
            return b''
        if not isinstance(pcm, bytes):
            pcm = bytes(pcm)
        # pe bucati de BUCATA_PCM esantioane: o liniste lunga (pana la SALT_MAX_90K) ar da mai multe cadre decat incap
        # in BUFFER_MP2 dintr-un singur apel
        pas = BUCATA_PCM * 2 * self.canale
        iesit = []
        for o in range(0, len(pcm), pas):
            bucata = pcm[o:o + pas] if o or len(pcm) > pas else pcm
            n = len(bucata) // (2 * self.canale)
            r = self.lib.twolame_encode_buffer_interleaved(self.o, bucata, n, self._buf, BUFFER_MP2)
            if r < 0:
                raise Lipsa('twolame_encode: %d' % r)
            if r:
                iesit.append(self._buf.raw[:r])
        return iesit[0] if len(iesit) == 1 else b''.join(iesit)

    def inchide(self):
        o, self.o = getattr(self, 'o', None), None
        if o:
            p = ctypes.c_void_p(o)
            self.lib.twolame_close(ctypes.byref(p))

    def __del__(self):
        try:
            self.inchide()
        except Exception:
            pass


# ---------------------------------------------------------------- timpul: (AU, PTS) -> (cadru MP2, PTS)
class Transcodor(object):
    """AU-uri cu PTS (90 kHz) -> cadre MP2 cu PTS. fabrica_decodor() da un decodor nou (DecodorAac(asc) la DAB+).

    Timpul: primul cadru iesit primeste PTS-ul primei AU, urmatoarele cate 1152 de esantioane mai tarziu (fara rest
    la 48 si 32 kHz: 2160 / 3240). Codorul are o intarziere fixa (filtrul), aceeasi pe tot fluxul, deci PTS-urile raman
    la pas egal. Cand PTS-ul AU-ului vine mai tarziu decat cel asteptat (AU sau superframe pierdut), golul se umple cu
    liniste; peste SALT_MAX_90K, sau inapoi, ori cand se schimba rata/canalele, se reancoreaza (decodor si codor noi).
    O AU stricata (faad2 da eroare) devine liniste de durata ei."""

    def __init__(self, fabrica_decodor, kbit=None, psy=PSY_IMPLICIT, fabrica_codor=None):
        self.fabrica = fabrica_decodor
        self.fabrica_codor = fabrica_codor or CodorMp2      # (rata, canale, kbit, psy) -> codeaza(pcm), inchide()
        self.kbit = kbit
        self.psy = psy
        self.dec = None
        self.cod = None
        self.format = None              # (rata, canale) al codorului
        self.ancora = None              # PTS-ul primului cadru MP2 al codorului de acum
        self.cadre = 0                  # cadre MP2 iesite de la ancora
        self.pts_urm = None             # PTS-ul asteptat al urmatoarei AU
        self._rest = b''
        self.au = self.au_rele = self.reancorari = 0
        self.liniste_esantioane = 0
        self.cpu_s = 0.0
        self.ultima_eroare = ''

    def _reancoreaza(self, pts):
        self._inchide_codor()
        if self.dec is not None:
            self.dec.inchide()
        self.dec = self.fabrica()
        self.ancora = pts & MASCA_33
        self.cadre = 0
        self.pts_urm = None
        self._rest = b''
        self.reancorari += 1

    def _inchide_codor(self):
        if self.cod is not None:
            self.cod.inchide()
        self.cod = None
        self.format = None

    def _liniste(self, esantioane):
        if self.cod is None or esantioane <= 0:
            return b''
        self.liniste_esantioane += esantioane
        return self.cod.codeaza(b'\0' * (esantioane * 2 * self.format[1]))

    def adauga(self, au, pts, durata_90k):
        """-> [(cadru_mp2, pts_90k), ...] (poate fi gol)"""
        t0 = _ceas_fir()
        try:
            return self._adauga(au, pts & MASCA_33, int(durata_90k))
        finally:
            self.cpu_s += _ceas_fir() - t0

    def _adauga(self, au, pts, durata):
        self.au += 1
        if self.dec is None:
            self._reancoreaza(pts)
        iesit = b''
        if self.pts_urm is not None:
            d = (pts - self.pts_urm) & MASCA_33
            if d >= 1 << 32:
                d -= 1 << 33
            if d > SALT_MAX_90K or d < -(durata // 2 + 1):
                self._reancoreaza(pts)
            elif d > durata // 2 and self.format:
                iesit += self._liniste(d * self.format[0] // 90000)
        self.pts_urm = (pts + durata) & MASCA_33
        r = self.dec.decodeaza(au)
        if r is None:
            self.au_rele += 1
            self.ultima_eroare = getattr(self.dec, 'ultima_eroare', '')
            if self.format:
                iesit += self._liniste(durata * self.format[0] // 90000)
        else:
            pcm, rata, canale = r
            if pcm:
                if self.format != (rata, canale):
                    if self.format is not None:
                        # alt format in mijlocul fluxului (postul s-a reconfigurat): codor nou si timp nou de la AU
                        # asta; decodorul, care a dat deja formatul nou, ramane
                        self._inchide_codor()
                        self.ancora = pts
                        self.cadre = 0
                        self._rest = b''
                        self.reancorari += 1
                        iesit = b''
                    self.cod = self.fabrica_codor(rata, canale, self.kbit, self.psy)
                    self.format = (rata, canale)
                iesit += self.cod.codeaza(pcm)
        if not iesit:
            return []
        cadre, self._rest = cadre_mp2(self._rest + iesit if self._rest else iesit)
        rata = self.format[0]
        rez = []
        for c in cadre:
            rez.append((c, (self.ancora + self.cadre * ESANTIOANE_MP2 * 90000 // rata) & MASCA_33))
            self.cadre += 1
        return rez

    def stare(self):
        return {'au': self.au, 'au_rele': self.au_rele, 'cadre_mp2': self.cadre, 'reancorari': self.reancorari,
                'liniste_ms': int(self.liniste_esantioane * 1000 // self.format[0]) if self.format else 0,
                'format': list(self.format) if self.format else None,
                'kbit': getattr(self.cod, 'kbit', None),
                'cpu_s': round(self.cpu_s, 3), 'ultima_eroare': self.ultima_eroare}

    def inchide(self):
        self._inchide_codor()
        if self.dec is not None:
            self.dec.inchide()
            self.dec = None

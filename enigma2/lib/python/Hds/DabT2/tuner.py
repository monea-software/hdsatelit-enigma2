# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Tine tunerul de satelit acordat pe transponderul unui feed. Facut de hdsatelit.com.

Cum lucreaza (lucruri dovedite pe Amiko Viper 4K V20, cu puntea de masurare):
  - canalul brut se ia cu eDVBResourceManager.allocateRawChannel(slot) si se acordeaza cu
    frontend.tune(eDVBFrontendParameters cu setDVBS). Acordul ramane in picioare doar cat tinem referinta
    la canal; cand o dam drumul (None), tunerul se elibereaza.
  - alocarea goleste singura canalul pastrat in cache de enigma2 (dvb.cpp, allocateRawChannel).
  - semnalul se citeste prin ioctl pe frontend (FE_READ_STATUS etc.), NU prin getFrontendStatus, care da zero.
    SNR-ul e o valoare relativa pe 16 biti; se da in procente, niciodata in dB.
  - cutia are si un tuner DVB-C/T2 care raporteaza lock permanent. Se citeste doar un frontend de satelit.
  - cu motor: cat timp antena se roteste, lock-ul poate veni de pe pozitia parasita. Nu il credem pana nu
    s-a oprit motorul (isRotorMoving) si nu a trecut timpul de asezare (4 s + jumatate de secunda pe grad).
  - cu motor si pozitia necunoscuta (dupa pornirea receptorului, pana o reda HdsMotorPozitie): sec.cpp trimite
    comanda motorului si tine „rotorul in miscare” pana vede lock-ul sau pana la MOTOR_RUNNING_TIMEOUT (360 s),
    deci isRotorMoving() poate ramane adevarat si cu antena deja pe satelit (vazut pe receptor: „nu vine semnal” dupa
    69 s, al doilea acord a prins imediat). Dupa asezare + REACORD_DUPA_S fara lock se da un acord din nou, o singura
    data: comanda motorului a plecat de atata timp, deci nucleul primeste pozitia tinta (hdsRestoreRotorPosition,
    cu comanda trimisa, cand nucleul spune ca miscarea era spre acelasi satelit), iar acordul nou nu mai roteste
    nimic si se uita direct dupa lock.

Nimic de aici nu blocheaza: asteptarea lock-ului e un eTimer la 500 ms, iar rezultatul vine prin callback.
Citirile de frontend (ioctl FE_GET_INFO / FE_READ_*) se fac intr-un fir de fundal: un driver care nu raspunde nu
opreste bucla principala. In firul principal raman doar apelurile enigma2 (alocarea canalului, tune, rotorul).
"""
import os
import struct

from . import compat, fundal, jurnal
from .limba import _

# duratele acordului (asezarea, termenul, alocarea) pe ceasul monoton: nu sare cand ora se potriveste din retea
_monoton = compat.monoton

ET = 'tuner'

FE_READ_STATUS = 0x80046F45
FE_READ_BER = 0x80046F46
FE_READ_SIGNAL_STRENGTH = 0x80026F47
FE_READ_SNR = 0x80026F48
FE_GET_INFO = 0x80A86F3D
FE_HAS_LOCK = 0x10
TIP_SATELIT = 0

POLARIZARE = {'H': 0, 'V': 1, 'L': 2, 'R': 3}
SISTEM = {'DVB-S': 0, 'DVB-S2': 1, 'DVB-S2X': 1}
MODULATIE = {'AUTO': 0, 'QPSK': 1, '8PSK': 2, 'QAM16': 3, '16APSK': 4, '32APSK': 5}
FEC = {'AUTO': 0, '1/2': 1, '2/3': 2, '3/4': 3, '5/6': 4, '7/8': 5, '8/9': 6, '3/5': 7, '4/5': 8, '9/10': 9}
PLS_MOD = {'ROOT': 0, 'GOLD': 1, 'COMBO': 2}

POZITIE_NECUNOSCUTA = 9999
PAS_MS = 500
ALOCARE_PAS_MS = 150        # tunerul refuzat (streamserverul inca il tine dupa 8001): reincercare la atat
ALOCARE_MAX_S = 3.0         # ... cel mult atat, apoi „tunerul de satelit e ocupat"
REACORD_DUPA_S = 6          # pozitia motorului necunoscuta: fara lock la asezare + atat, un acord din nou
TERMEN_REACORD_S = 45       # ... si dupa el se mai asteapta lock-ul cel mult atat


def _int(v, implicit=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return implicit


def parametri(tp):
    """Transponderul din lista (format frecvente.json) -> dictionar de intregi pentru enigma2.

    frecventa in kHz, sr in simboluri/s, pozitie in zecimi de grad (192 = 19,2E; vestul ca 3600 - x)."""
    poz = _int(tp.get('pozitie'))
    if poz < 0:
        poz += 3600
    pls = tp.get('pls_mod')
    is_id = _int(tp.get('is_id'), -1) if tp.get('is_id') is not None else -1
    are_pls = tp.get('pls_cod') is not None and _int(tp.get('pls_cod'), 0) > 0 or \
        str(pls).upper() in ('GOLD', 'COMBO', '1', '2')
    if is_id < 0 and are_pls:
        # Dovedit pe HiSilicon (39E 11760 H): PLS se aplica doar cu is_id >= 0. Cu -1 nu prinde nimic.
        is_id = 0
    return {
        'frequency': _int(tp.get('frecventa')),
        'symbol_rate': _int(tp.get('sr')),
        'polarisation': POLARIZARE.get(str(tp.get('pol', 'H')).upper()[:1], 0),
        'orbital_position': poz,
        'system': SISTEM.get(str(tp.get('sistem', 'DVB-S')).upper(), 0),
        'modulation': MODULATIE.get(str(tp.get('modulatie', 'QPSK')).upper(), 1),
        'fec': FEC.get(str(tp.get('fec', 'auto')).upper(), 0),
        'inversion': 2,
        'rolloff': 0,
        'pilot': 2,
        'is_id': is_id,
        'pls_mode': PLS_MOD.get(str(pls).upper(), _int(pls, 0)) if pls is not None else 0,
        'pls_code': _int(tp.get('pls_cod'), 0) if tp.get('pls_cod') is not None else 0,
    }


def arc_grade(de_la, la):
    """Arcul parcurs de motor intre doua pozitii enigma2 (zecimi de grad). Necunoscut -> 40 de grade."""
    if de_la is None or la is None or de_la == POZITIE_NECUNOSCUTA:
        return 40.0
    a = de_la if de_la <= 1800 else de_la - 3600
    b = la if la <= 1800 else la - 3600
    return abs(a - b) / 10.0


def secunde_asezare(arc):
    return int(4 + arc / 2.0) if arc else 0


def pozitie_motor_stiuta(slot):
    """Unde e motorul tunerului `slot` (zecimi de grad, ca orbital_position), sau None daca nu se stie.

    Intai pozitia tinuta de nucleu (eDVBSatelliteEquipmentControl.hdsKnownRotorPosition, in imaginea HD Satelit):
    e aceeasi dupa care SEC-ul hotaraste daca trimite comanda motorului, deci pe acelasi satelit nu se asteapta
    nimic; -1 = nestiuta (dupa pornire, pana o reda HdsMotorPozitie). Alte imagini: config.misc.lastrotorposition."""
    try:
        from enigma import eDVBSatelliteEquipmentControl
        v = int(eDVBSatelliteEquipmentControl.getInstance().hdsKnownRotorPosition(slot))
        if v >= 0:
            return v
    except Exception:
        pass
    try:
        from Components.config import config
        return config.misc.lastrotorposition.value
    except Exception:
        return None


def pozitie_necunoscuta(v):
    return v is None or v < 0 or v == POZITIE_NECUNOSCUTA


def pozitie_dupa_miscare(slot, poz):
    """Nucleul a notat o miscare a motorului tunerului `slot` spre `poz`: tine minte acea pozitie, cu comanda trimisa
    (hdsRestoreRotorPosition), ca un acord nou pe acelasi satelit sa nu mai roteasca nimic. -> True daca s-a pus.
    Alte imagini (fara aceste functii) sau o miscare spre alt satelit: False."""
    try:
        from enigma import eDVBSatelliteEquipmentControl
        sec = eDVBSatelliteEquipmentControl.getInstance()
        if int(sec.hdsRotorToOrbital(slot)) != poz:
            return False
        return bool(sec.hdsRestoreRotorPosition(slot, poz, int(sec.hdsRotorCmd(slot))))
    except Exception:
        return False


def cheie_transponder(tp):
    p = parametri(tp)
    return (p['orbital_position'], p['frequency'] // 1000, p['polarisation'], p['is_id'])


# ---------------------------------------------------------------- citirea frontend-ului, prin ioctl
def _deschide(cale):
    return os.open(cale, os.O_RDONLY | os.O_NONBLOCK)


def e_satelit(cale):
    try:
        import fcntl
        fd = _deschide(cale)
    except Exception:
        return False
    try:
        buf = bytearray(132)
        fcntl.ioctl(fd, FE_GET_INFO, buf, True)
        return struct.unpack('i', bytes(buf[128:132]))[0] == TIP_SATELIT
    except Exception:
        return False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def citeste_semnal(cale):
    """{'lock', 'semnal_la_suta', 'calitate_la_suta', 'ber'} sau {} daca nu se poate citi. Nu arunca."""
    rez = {}
    try:
        import fcntl
        fd = _deschide(cale)
    except Exception:
        return rez
    try:
        for cheie, cerere, fmt in (('stare', FE_READ_STATUS, 'I'), ('agc', FE_READ_SIGNAL_STRENGTH, 'H'),
                                   ('snr', FE_READ_SNR, 'H'), ('ber', FE_READ_BER, 'I')):
            try:
                rez[cheie] = struct.unpack(fmt, fcntl.ioctl(fd, cerere, struct.pack(fmt, 0)))[0]
            except Exception:
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if 'stare' in rez:
        rez['lock'] = bool(rez['stare'] & FE_HAS_LOCK)
    if 'agc' in rez:
        rez['semnal_la_suta'] = int(round(rez['agc'] * 100.0 / 65535.0))     # int si pe 2.7 (round da float)
    if 'snr' in rez:
        rez['calitate_la_suta'] = int(round(rez['snr'] * 100.0 / 65535.0))
    return rez


def cale_frontend(slot):
    """Frontend-ul de satelit pentru slot. Pe cutiile cu un adaptor, frontendN = slotul N."""
    cale = '/dev/dvb/adapter0/frontend%d' % slot
    if os.path.exists(cale) and e_satelit(cale):
        return cale
    for a in range(2):
        for f in range(8):
            c = '/dev/dvb/adapter%d/frontend%d' % (a, f)
            if os.path.exists(c) and e_satelit(c):
                return c
    return cale


def alege_slot(pozitie):
    """Primul tuner DVB-S care are pozitia in lista lui de sateliti; altfel primul DVB-S; altfel 0."""
    try:
        from Components.NimManager import nimmanager
    except Exception:
        return 0, False
    primul, rotor = None, False
    try:
        for nim in nimmanager.nim_slots:
            try:
                if not nim.isCompatible('DVB-S'):
                    continue
                if getattr(nim, 'config_mode', '') == 'nothing':
                    continue
            except Exception:
                continue
            if primul is None:
                primul = nim.slot
            try:
                sateliti = [s[0] for s in nimmanager.getSatListForNim(nim.slot)]
            except Exception:
                sateliti = []
            if pozitie in sateliti:
                try:
                    rotor = pozitie in [s[0] for s in nimmanager.getRotorSatListForNim(nim.slot)]
                except Exception:
                    rotor = False
                return nim.slot, rotor
    except Exception:
        jurnal.eroare(ET, 'alege_slot')
    return (primul if primul is not None else 0), False


def citire_frontend(slot, cale=None):
    """In firul de fundal: calea frontend-ului de satelit (daca nu e stiuta) si semnalul. -> (cale, semnal)."""
    if not cale:
        cale = cale_frontend(slot)
    return cale, citeste_semnal(cale)


class Tuner(object):
    """Un singur acord tinut. Stari: liber, acord, rotire, prins, esuat."""

    def __init__(self, eticheta='tuner'):
        self.et = eticheta
        self.stare = 'liber'
        self.canal = None
        self.frontend = None
        self.slot = 0
        self.cale = None
        self.tp = None
        self.cheie = None
        self._timer = None
        self._la_gata = None
        self._la_stare = None
        self._inceput = 0.0
        self._asezare = 0
        self._motor_la = None
        self._termen = 0
        self._rotor = False
        self._vazut_miscare = False
        self._oprit_la = None
        self._lock_la_rand = 0
        self.alocari = 0
        self.eliberari = 0
        self._timer_alocare = None
        self._conexiuni = []          # manierele legaturilor timerelor (semnale-obiect: tinute cat traiesc timerele)
        self._alocare_pana = 0.0
        self._p = self._poz = self._fp = self._tp_cerut = None
        self._necunoscuta = False     # acordul a pornit cu pozitia motorului necunoscuta
        self._reacordat = False
        self.reacorduri = 0
        self.fundal = fundal.Fundal(eticheta)
        self.ultimul_semnal = {}

    # ---- intrebari
    def tinut(self):
        return self.canal is not None

    def prins_pe(self, tp):
        return self.canal is not None and self.stare == 'prins' and self.cheie == cheie_transponder(tp)

    def semnal(self):
        """Ultimul semnal citit in fundal (fara ioctl in firul principal)."""
        return dict(self.ultimul_semnal) if self.canal is not None else {}

    def ramas_s(self):
        """Secundele ramase pana la termenul acordului de acum (bataia pentru paznic), pe ceasul acordului."""
        return max(0, int(self._termen - (_monoton() - self._inceput)))

    # ---- acordul
    def acordeaza(self, tp, la_gata, la_stare=None):
        """Porneste acordul. la_gata(ok, mesaj) se cheama o singura data. Intoarce False daca a cazut imediat."""
        self.elibereaza()
        self._la_gata, self._la_stare = la_gata, la_stare
        p = parametri(tp)
        if not p['frequency'] or not p['symbol_rate']:
            self._termina(False, _('transponder fara frecventa'))
            return False
        if multistream_neprins(tp):
            self._termina(False, text_multistream())
            return False
        poz = p['orbital_position']
        self.slot, self._rotor = alege_slot(poz)
        try:
            from enigma import (eDVBFrontendParameters, eDVBFrontendParametersSatellite,
                                eDVBResourceManager)
        except Exception:
            self._termina(False, _('eroare interna'))
            return False

        ultima = pozitie_motor_stiuta(self.slot) if self._rotor else None
        arc = arc_grade(ultima, poz) if self._rotor and ultima != poz else 0.0
        self._motor_la = ultima
        self._necunoscuta = self._rotor and pozitie_necunoscuta(ultima)
        self._reacordat = False
        self._asezare = secunde_asezare(arc)
        self._termen = min(self._asezare + 45, 180) if self._asezare else 20

        s = eDVBFrontendParametersSatellite()
        for camp in ('frequency', 'symbol_rate', 'polarisation', 'orbital_position', 'fec', 'inversion',
                     'system', 'modulation', 'rolloff', 'pilot', 'is_id', 'pls_mode', 'pls_code'):
            try:
                setattr(s, camp, p[camp])
            except Exception:
                pass   # imagini mai vechi nu au is_id / pls
        fp = eDVBFrontendParameters()
        fp.setDVBS(s, False)
        self._p, self._poz, self._fp, self._tp_cerut = p, poz, fp, tp
        self._alocare_pana = _monoton() + ALOCARE_MAX_S
        return self._aloca_si_acordeaza()

    def _aloca_si_acordeaza(self):
        """0.1.4: dupa un canal T2 (sau ETI) prin 8001, streamserverul enigma2 elibereaza tunerul abia cand bucla
        principala prelucreaza inchiderea sesiunii. O alocare refuzata se reincearca din eTimer la ALOCARE_PAS_MS, cel
        mult ALOCARE_MAX_S, fara asteptare in firul principal; abia apoi „tunerul de satelit e ocupat"."""
        from enigma import eDVBResourceManager
        p, poz, fp, tp = self._p, self._poz, self._fp, self._tp_cerut
        canal = eDVBResourceManager.getInstance().allocateRawChannel(self.slot)
        if isinstance(canal, (tuple, list)):
            canal = canal[-1]
        fe = None
        if canal:
            fe = canal.getFrontend()
            if isinstance(fe, (tuple, list)):
                fe = fe[-1]
            if not fe:
                canal = None
        if not canal:
            if _monoton() < self._alocare_pana:
                if self.stare != 'alocare':
                    jurnal.noteaza(self.et, 'tunerul inca ocupat; reincerc alocarea cel mult %.0f s' % ALOCARE_MAX_S)
                self.stare = 'alocare'
                if self._timer_alocare is None:
                    from enigma import eTimer
                    self._timer_alocare = eTimer()
                    self._conexiuni.append(compat.conecteaza_timer(self._timer_alocare, self._reincearca_alocarea))
                self._timer_alocare.start(ALOCARE_PAS_MS, True)
                return True
            self._termina(False, _('tunerul de satelit e ocupat'))
            return False
        self.canal, self.frontend = canal, fe
        self.alocari += 1
        self.tp = tp
        self.cheie = cheie_transponder(tp)
        self.cale = None                  # se afla in fundal, la prima citire
        self.ultimul_semnal = {}
        fe.tune(fp)
        self.stare = 'acord'
        self._inceput = _monoton()
        self._vazut_miscare = False
        self._oprit_la = None
        self._lock_la_rand = 0
        jurnal.noteaza(self.et, 'acord slot %d: %d kHz pol %d sr %d poz %d, asezare %d s (motorul la %s)'
                       % (self.slot, p['frequency'], p['polarisation'], p['symbol_rate'], poz, self._asezare,
                          getattr(self, '_motor_la', None) if self._rotor else 'fara motor'))
        if self._asezare and self._la_stare:
            self._la_stare(_('Se roteste antena spre %s') % text_pozitie(poz))
        self._porneste_timer()
        return True

    def _reincearca_alocarea(self):
        try:
            if self.stare != 'alocare' or self._la_gata is None:
                return
            self._aloca_si_acordeaza()
        except Exception:
            jurnal.eroare(self.et, 'reincercarea alocarii')
            self._termina(False, _('eroare interna'))

    def _porneste_timer(self):
        if self._timer is None:
            from enigma import eTimer
            self._timer = eTimer()
            self._conexiuni.append(compat.conecteaza_timer(self._timer, self._pas))
        self._timer.start(PAS_MS, False)

    def _rotorul_se_misca(self):
        try:
            from enigma import eDVBSatelliteEquipmentControl
            return bool(eDVBSatelliteEquipmentControl.getInstance().isRotorMoving())
        except Exception:
            return False

    def _pas(self):
        try:
            self._pas_nepazit()
        except Exception:
            jurnal.eroare(self.et, 'pasul de acord')
            self._termina(False, _('eroare interna'))

    def _pas_nepazit(self):
        if self.canal is None:
            self._opreste_timer()
            return
        acum = _monoton()
        trecut = acum - self._inceput
        misca = self._rotorul_se_misca()
        if misca:
            if not self._vazut_miscare and self._la_stare:
                self._la_stare(_('Se roteste antena'))
            self._vazut_miscare = True
            self._oprit_la = None
            self.stare = 'rotire'
            self._lock_la_rand = 0
        elif self._vazut_miscare and self._oprit_la is None:
            self._oprit_la = acum

        asezat = True
        if self._asezare:
            oprit_de_ajuns = self._oprit_la is not None and acum - self._oprit_la >= 1.5
            asezat = (not misca) and (oprit_de_ajuns or trecut >= self._asezare)
        if not asezat:
            self._lock_la_rand = 0
        elif self.fundal.in_curs() == 0:
            self.fundal.lanseaza(citire_frontend, self._semnal_venit, self.slot, self.cale)
        if self._necunoscuta and not self._reacordat and trecut >= self._asezare + REACORD_DUPA_S:
            self._acord_din_nou(trecut)
            return
        if trecut >= self._termen:
            self.stare = 'esuat'
            self._termina(False, _('nu vine semnal pe %s') % text_transponder(self.tp))

    def _acord_din_nou(self, trecut):
        """Pozitia motorului era necunoscuta la acord si lock-ul nu a venit: o singura data, pozitia tinta data
        nucleului (comanda motorului a plecat de la acord) si acordul din nou, pe acelasi canal brut."""
        self._reacordat = True
        self.reacorduri += 1
        pus = pozitie_dupa_miscare(self.slot, self._poz)
        jurnal.noteaza(self.et, 'fara lock la %.0f s, cu pozitia motorului necunoscuta la acord: acord din nou%s'
                       % (trecut, ' (pozitia %d data nucleului)' % self._poz if pus else ''))
        try:
            self.frontend.tune(self._fp)
        except Exception:
            jurnal.eroare(self.et, 'acordul din nou')
        self.stare = 'acord'
        self._vazut_miscare = False
        self._oprit_la = None
        self._lock_la_rand = 0
        # timpul de asezare a trecut: lock-ul se citeste imediat ce nucleul nu mai socoteste motorul in miscare
        self._termen = max(self._termen, trecut + TERMEN_REACORD_S)

    def _semnal_venit(self, ok, rez):
        """In firul principal, cu rezultatul citirii din fundal."""
        try:
            if self.canal is None or self.stare not in ('acord', 'rotire') or self._la_gata is None:
                return
            if not ok or not isinstance(rez, tuple):
                self._lock_la_rand = 0
                return
            cale, m = rez
            self.cale = cale or self.cale
            self.ultimul_semnal = m or {}
            self._lock_la_rand = self._lock_la_rand + 1 if self.ultimul_semnal.get('lock') else 0
            if self._lock_la_rand >= 2:
                self.stare = 'prins'
                self._salveaza_pozitia()
                self._termina(True, 'prins')
        except Exception:
            jurnal.eroare(self.et, 'semnalul din fundal')
            self._termina(False, _('eroare interna'))

    def reimprospateaza(self):
        """Dupa prindere, cat tinem tunerul: o citire noua de semnal in fundal (din paza, la 2 s).

        Fara ea ultimul_semnal ar ramane cel de la prindere. Nu asteapta nimic in firul principal.
        """
        if self.canal is None or self.stare != 'prins' or self.fundal.in_curs() != 0:
            return False
        self.fundal.lanseaza(citire_frontend, self._la_reimprospatare(self.canal), self.slot, self.cale)
        return True

    def _la_reimprospatare(self, canal):
        def venit(ok, rez):
            # doar pentru acelasi canal inca tinut (intre timp tunerul poate fi eliberat sau reacordat)
            try:
                if self.canal is not canal or self.stare != 'prins' or not ok or not isinstance(rez, tuple):
                    return
                cale, m = rez
                self.cale = cale or self.cale
                self.ultimul_semnal = m or {}
            except Exception:
                jurnal.eroare(self.et, 'reimprospatarea semnalului')
        return venit

    def _salveaza_pozitia(self):
        if not self._rotor:
            return
        try:
            from Components.config import config
            poz = parametri(self.tp)['orbital_position']
            if config.misc.lastrotorposition.value != poz:
                config.misc.lastrotorposition.value = poz
                config.misc.lastrotorposition.save()
        except Exception:
            pass

    def _opreste_timer(self):
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass

    def _termina(self, ok, mesaj):
        self._opreste_timer()
        cb, self._la_gata = self._la_gata, None
        if not ok:
            jurnal.noteaza(self.et, 'acord esuat: %s' % mesaj)
            self._da_drumul()
            self.stare = 'esuat'
        if cb is not None:
            try:
                cb(ok, mesaj)
            except Exception:
                jurnal.eroare(self.et, 'la_gata')

    def _da_drumul(self):
        if self.canal is not None:
            self.eliberari += 1
        self.frontend = None
        self.canal = None

    def elibereaza(self):
        """Da tunerul inapoi. Sincron: dupa intoarcere tunerul e liber pentru enigma2."""
        self._opreste_timer()
        if self._timer_alocare is not None:
            try:
                self._timer_alocare.stop()
            except Exception:
                pass
        self.fundal.opreste()
        self._la_gata = None
        self._la_stare = None
        if self.canal is not None:
            jurnal.noteaza(self.et, 'tuner eliberat')
        self._da_drumul()
        self.stare = 'liber'
        self.tp = None
        self.cheie = None


def text_pozitie(poz):
    """192 -> „19,2°E", 3550 -> „5,0°V" („5.0°W" in engleza): aceleasi tipare traduse „%s E" / „%s V" si separatorul
    zecimal al limbii meniului, prin Components/HdsGrade.py, ca pe restul ecranelor; „?" cand nu e o pozitie"""
    try:
        poz = int(poz)
    except (TypeError, ValueError):
        return '?'
    try:
        try:
            from Components.HdsGrade import pozitieOrbitala
        except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
            from HdsGrade import pozitieOrbitala
    except ImportError:
        # pachetul pornit fara imagine (pluginul de sine statator, probele cu enigma simulat): tiparele lui, cu virgula
        if poz > 1800:
            return _('%s V') % _zecimal((3600 - poz) / 10.0)
        return _('%s E') % _zecimal(poz / 10.0)
    return pozitieOrbitala(poz) or '?'


def _zecimal(x):
    return ('%.1f' % x).replace('.', ',')


def cere_multistream(tp):
    """Transponderul cere filtrul de flux (ISI) sau un cod PLS altul decat cel implicit (radacina 1)."""
    tp = tp or {}
    if tp.get('is_id') not in (None, -1):
        return True
    cod = tp.get('pls_cod')
    return cod not in (None, 0) and not (str(tp.get('pls_mod') or '').lower() == 'root' and cod == 1)


_nucleu_ms = []


def nucleu_multistream():
    """eDVBFrontendParametersSatellite are is_id / pls_mode / pls_code (citit o data). Fara enigma: False."""
    if not _nucleu_ms:
        try:
            from enigma import eDVBFrontendParametersSatellite
            s = eDVBFrontendParametersSatellite()
            _nucleu_ms.append(all(hasattr(s, c) for c in ('is_id', 'pls_mode', 'pls_code')))
        except Exception:
            return False
    return _nucleu_ms[0]


def multistream_neprins(tp):
    """Transponderul cere multistream, iar nucleul nu-l are: acordul ar prinde alt flux sau nimic."""
    return cere_multistream(tp) and not nucleu_multistream()


def text_multistream():
    return _('Multistream: imaginea nu-l poate receptiona inca.')


def text_transponder(tp):
    if not tp:
        return '?'
    p = parametri(tp)
    return '%s %d %s %d' % (text_pozitie(p['orbital_position']), p['frequency'] // 1000,
                            'HVLR'[p['polarisation']], p['symbol_rate'] // 1000)

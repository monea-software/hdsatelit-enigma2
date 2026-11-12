# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsOarbaVuplus.py: cautarea oarba pe Vu+ Solo SE (tunerul AVL6211), prin programul inchis al producatorului
vuplus_6211_blindscan (pachetul vuplus-blindscan-dvbs-utils din feedul de pluginuri, luat NEMODIFICAT, cu acordul Satco).

Scris de la zero. Fisierul se ruleaza ca program separat (python3 HdsOarbaVuplus.py ...), pornit de HdsCautareOarba in locul lui
hds-blindscan (care merge numai pe placile HiSilicon), cu ACELEASI argumente si scrie ACELASI protocol (PORNIT, TRECERE, TP,
PROGRES, GATA, OPRIT, EROARE), deci ecranul, pagina web si probele raman cele de acum.

Programul Vu+ cauta pe o singura banda si polarizare la o chemare, prin legatura i2c cu demodulatorul; tensiunea si tonul
LNB-ului le pune cine tine tunerul deschis (asa face si pluginul Blindscan din sursele GPL enigma2 (OE-Alliance), commitul 6b8de23:
acordeaza tunerul pe banda si polarizarea trecerii, apoi porneste programul). Aici: pentru fiecare trecere, frontend-ul DVB al
tunerului e tinut deschis, cu tensiunea (13 V vertical, 18 V orizontal) si tonul de 22 kHz ale trecerii (FE_SET_VOLTAGE,
FE_SET_TONE), apoi:
    vuplus_6211_blindscan <IF start MHz> <IF stop MHz> <rata min MSym/s> <rata max MSym/s> <pol 0=H 1=V> <ton 0|1> <slot> <i2c>
Randurile lui de gasit: „OK <POLARIZARE> <frecventa kHz> <rata Sym/s> <DVB-S|DVB-S2> <inversiune> <pilot> <FEC> <modulatie>
<rolloff> ...”, cu frecventa socotita pe un LNB universal (9750 / 10600 MHz). Ca nu misca antena si nu trimite DiSEqC, ca si
hds-blindscan: cauta pe unde stau antena si comutatorul.

Nimic din enigma2 nu se importa (programul ruleaza in afara interfetei); probele de pe PC dau programul Vu+ si frontend-ul fals."""
from __future__ import absolute_import, print_function

import os
import signal
import subprocess
import sys
import time

# ioctl-urile DVB (linux/dvb/frontend.h): _IO('o', 66) si _IO('o', 67). _IO pune bitii de directie „fara date”: 0 pe ARM si x86,
# dar 1 << 29 pe MIPS (asm/ioctl.h: _IOC_NONE 1, _IOC_DIRSHIFT 29); Solo SE e MIPS, deci numerele depind de procesor.
FE_SET_TONE_BAZA = 0x6f42
FE_SET_VOLTAGE_BAZA = 0x6f43


def ioctl_nr(baza, masina):
    """Numarul ioctl _IO pentru procesorul dat (os.uname().machine: 'mips', 'armv7l', 'x86_64' ...)."""
    return baza | (1 << 29) if (masina or '').startswith('mips') else baza


def _masina():
    try:
        return os.uname().machine
    except AttributeError:   # Windows (probele de pe PC)
        return ''


FE_SET_TONE = ioctl_nr(FE_SET_TONE_BAZA, _masina())
FE_SET_VOLTAGE = ioctl_nr(FE_SET_VOLTAGE_BAZA, _masina())
SEC_VOLTAGE_13, SEC_VOLTAGE_18 = 0, 1
SEC_TONE_ON, SEC_TONE_OFF = 0, 1

LO_UNIVERSAL_KHZ = (9750000, 10600000)        # banda joasa / inalta, cum socoteste programul Vu+ frecventa
RATA_MAX_MSYM = 45
ASTEPTARE_FRONTEND_S = 15                      # enigma2 inchide frontend-ul la ~3 s dupa oprirea canalului
PAUZA_LNB_S = 0.5                              # LNB-ul si comutatorul se aseaza dupa tensiune / ton
NIM_SOCKETS = '/proc/bus/nim_sockets'
# numele cipului din /proc/bus/nim_sockets -> programul Vu+ (ca _supportNimType al pluginului Blindscan OE-Alliance)
PROGRAME = {'AVL6211': 'vuplus_6211_blindscan', 'AVL6222': 'vuplus_6222_blindscan', 'AVL1208': 'vuplus_blindscan'}
# legatura i2c a slotului cand nim_sockets nu o spune (tabelul pluginului Blindscan pentru tunerele care nu sunt AVL6222)
I2C_IMPLICIT = {0: 2, 1: 3, 2: 1, 3: 0}

_OPRIRE = []


def _iesire(rand):
    sys.stdout.write(rand + '\n')
    sys.stdout.flush()


def tuner_din_nim_sockets(text, slot):
    """(cipul, i2c) al slotului din continutul lui /proc/bus/nim_sockets; i2c None cand nu e scris acolo."""
    cip, i2c, sno = '', None, None
    gasit = {}
    for rand in (text or '').splitlines():
        rand = rand.strip()
        if rand.startswith('NIM Socket'):
            try:
                sno = int(rand.split()[2].rstrip(':'))
            except (IndexError, ValueError):
                sno = None
            cip, i2c = '', None
        elif sno is not None and rand.startswith('Name:'):
            # „Name: Vuplus DVB-S NIM(AVL6211)” -> AVL6211
            if '(' in rand and rand.endswith(')'):
                cip = rand[rand.rindex('(') + 1:-1].strip()
            gasit[sno] = (cip, gasit.get(sno, ('', None))[1])
        elif sno is not None and rand.startswith('I2C_Device:'):
            try:
                i2c = int(rand.split()[1])
            except (IndexError, ValueError):
                i2c = None
            gasit[sno] = (gasit.get(sno, ('', None))[0], i2c)
    return gasit.get(int(slot), ('', None))


def program_pentru(slot, nim_sockets=NIM_SOCKETS, dosar='/usr/bin'):
    """{'program': cale, 'i2c': n, 'cip': nume} pentru tunerul din slot, sau None cand cipul nu are program Vu+."""
    try:
        with open(nim_sockets) as f:
            text = f.read()
    except (IOError, OSError):
        return None
    cip, i2c = tuner_din_nim_sockets(text, slot)
    nume = PROGRAME.get(cip)
    if not nume:
        return None
    if i2c is None:
        i2c = I2C_IMPLICIT.get(int(slot), -1)
    return {'program': os.path.join(dosar, nume), 'i2c': int(i2c), 'cip': cip}


def citeste_ok(rand):
    """Un rand „OK ...” al programului Vu+ -> (pol 'H'|'V'|'L'|'R', frecventa kHz, rata Sym/s, sistem 0|1), altfel None."""
    p = (rand or '').split()
    if len(p) < 6 or p[0] != 'OK':
        return None
    pol = {'HORIZONTAL': 'H', 'VERTICAL': 'V', 'CIRCULARLEFT': 'L', 'CIRCULARRIGHT': 'R'}.get(p[1])
    if pol is None:
        return None
    try:
        frecventa, rata = int(p[2]), int(p[3])
    except ValueError:
        return None
    if frecventa <= 0 or rata <= 0:
        return None
    return pol, frecventa, rata, (1 if p[4].startswith('DVB-S2') else 0)


def real_din_if(if_khz, lo_khz):
    """Frecventa pe satelit din frecventa intermediara (banda C: oscilatorul e deasupra; aceeasi socoteala ca HdsCautareOarba)."""
    return lo_khz - if_khz if lo_khz < 7500000 else lo_khz + if_khz


def tp_din_ok(ok, ton, lo_khz, if_start, if_stop):
    """Randul nostru „TP <frecventa reala kHz> <rata kSym/s> <sistem> <pol> <IF kHz> <calitate>” sau None in afara trecerii."""
    pol, frecventa, rata, sistem = ok
    if_khz = abs(frecventa - LO_UNIVERSAL_KHZ[1 if ton else 0])
    if not (if_start - 5000 <= if_khz <= if_stop + 5000):
        return None
    return 'TP %d %d %d %s %d 0' % (real_din_if(if_khz, lo_khz), rata // 1000, sistem, pol, if_khz)


def argumente(argv):
    a = {'tuner': 0, 'lo_jos': 9750, 'lo_sus': 10600, 'timp_max': 1500, 'treceri': [], 'program': '', 'i2c': -1,
         'rata_min': 1, 'frontend': None}
    i = 0
    while i < len(argv):
        k = argv[i]
        v = argv[i + 1] if i + 1 < len(argv) else ''
        if k == '--trecere':
            pol, ton, start, stop = v.split(',')
            a['treceri'].append((pol, int(ton), int(start), int(stop)))
        elif k in ('--tuner', '--lo-jos', '--lo-sus', '--timp-max', '--i2c', '--rata-min'):
            a[k[2:].replace('-', '_')] = int(v)
        elif k in ('--program', '--frontend'):
            a[k[2:]] = v
        else:
            raise ValueError(k)
        i += 2
    return a


def deschide_frontend(cale, termen_s=ASTEPTARE_FRONTEND_S, dormi=time.sleep):
    """Descriptorul frontend-ului, asteptand cat il elibereaza enigma2; None daca ramane ocupat."""
    sfarsit = time.time() + termen_s
    while True:
        try:
            return os.open(cale, os.O_RDWR | getattr(os, 'O_NONBLOCK', 0))
        except OSError:
            if time.time() >= sfarsit or _OPRIRE:
                return None
            dormi(0.5)


def lnb(fd, pol, ton):
    """Tensiunea si tonul trecerii. Pe frontend-ul fals al probelor (un fisier obisnuit) ioctl-ul cade: se trece mai departe."""
    try:
        import fcntl
        fcntl.ioctl(fd, FE_SET_VOLTAGE, SEC_VOLTAGE_13 if pol in ('V', 'R') else SEC_VOLTAGE_18)
        fcntl.ioctl(fd, FE_SET_TONE, SEC_TONE_ON if ton else SEC_TONE_OFF)
    except (IOError, OSError, ImportError) as e:
        _iesire('JURNAL lnb %s' % getattr(e, 'errno', ''))


def ruleaza(a, porneste=subprocess.Popen, ceas=time.time):
    """Toate trecerile. Intoarce codul de iesire: 0 gata sau oprit, 1 eroare, 3 timpul depasit."""
    t0 = ceas()
    if not a['program'] or not os.path.exists(a['program']):
        _iesire('EROARE 1 program-vuplus-lipsa')
        return 1
    cale = a['frontend'] or '/dev/dvb/adapter0/frontend%d' % a['tuner']
    fd = deschide_frontend(cale)
    if fd is None:
        _iesire('EROARE 1 frontend-ocupat')
        return 1
    gasite = set()
    n = len(a['treceri'])
    _iesire('PORNIT %d 0' % n)
    rata_min = max(1, int(a['rata_min']))
    try:
        for nr, (pol, ton, start, stop) in enumerate(a['treceri'], 1):
            if _OPRIRE:
                break
            _iesire('TRECERE %d %s %d %d %d' % (nr, pol, ton, start, stop))
            lnb(fd, pol, ton)
            time.sleep(PAUZA_LNB_S)
            lo = (a['lo_sus'] if ton else a['lo_jos']) * 1000
            cmd = [a['program'], str(start // 1000), str((stop + 999) // 1000), str(rata_min), str(RATA_MAX_MSYM),
                   '1' if pol in ('V', 'R') else '0', '1' if ton else '0', str(a['tuner']), str(a['i2c'])]
            _iesire('JURNAL program %s' % ' '.join(cmd[1:]))
            p = porneste(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for brut in iter(p.stdout.readline, b''):
                if _OPRIRE or ceas() - t0 > a['timp_max']:
                    p.terminate()
                    break
                ok = citeste_ok(brut.decode('utf-8', 'replace'))
                if ok is None:
                    continue
                rand = tp_din_ok(ok, ton, lo, start, stop)
                if rand and rand not in gasite:
                    gasite.add(rand)
                    _iesire(rand)
            p.stdout.close()
            p.wait()
            _iesire('PROGRES %d %d' % (nr * 100 // max(1, n), len(gasite)))
            if ceas() - t0 > a['timp_max']:
                _iesire('OPRIT %d %d' % (len(gasite), int((ceas() - t0) * 1000)))
                return 3
    finally:
        os.close(fd)
    _iesire('%s %d %d' % ('OPRIT' if _OPRIRE else 'GATA', len(gasite), int((ceas() - t0) * 1000)))
    return 0


def main(argv):
    signal.signal(signal.SIGINT, lambda *x: _OPRIRE.append(1))
    signal.signal(signal.SIGTERM, lambda *x: _OPRIRE.append(1))
    try:
        a = argumente(argv)
    except (ValueError, IndexError) as e:
        _iesire('EROARE 2 argumente %s' % e)
        return 2
    return ruleaza(a)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Limitele SR raportate de drivere, in simboluri/s, fara asteptare in interfata.

FE_GET_INFO se citeste o singura data pe frontend, numai in firul de fundal.
None inseamna margine necunoscuta sau zero raportat de driver, deci fara refuz.
Cititorii primesc o fotografie a rezultatelor; nu asteapta nici firul, nici ioctl.
"""
import glob
import os
import struct
import sys
import threading

FE_GET_INFO = 0x80A86F3D
MARIME_INFO = 168
_stare = {}
_fir = None
_pornire = threading.Lock()
_proba = False


def _margine(valoare):
    return valoare if valoare and valoare > 0 else None


def _jurnal(cale, limite):
    try:
        from Components.HdsJurnal import info
        minim, maxim = limite
        info('tuner', 'HdsLimiteTuner', '%s: SR min=%s max=%s simboluri/s; sursa=%s' % (
            cale, minim if minim is not None else 'necunoscut',
            maxim if maxim is not None else 'necunoscut',
            'tuner' if minim is not None or maxim is not None else 'necunoscut'))
    except Exception:
        pass


def _citeste():
    global _stare
    try:
        import fcntl
        cai = sorted(glob.glob('/dev/dvb/adapter*/frontend*'))
    except (ImportError, OSError):
        return
    # Pana la citirea tipului, orice dispozitiv poate fi un tuner satelit necitit.
    rezultate = dict((cale, (None, None)) for cale in cai)
    if not _proba:
        _stare = rezultate.copy()
    for cale in cai:
        fd = None
        satelit = True
        try:
            fd = os.open(cale, os.O_RDONLY | os.O_NONBLOCK)
            tampon = bytearray(MARIME_INFO)
            fcntl.ioctl(fd, FE_GET_INFO, tampon, True)
            satelit = struct.unpack_from('<I', tampon, 128)[0] == 0
            if satelit:
                minim, maxim = struct.unpack_from('<II', tampon, 148)
                rezultate[cale] = (_margine(minim), _margine(maxim))
            else:
                rezultate[cale] = None
        except (OSError, ValueError, struct.error):
            pass
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        if not _proba:
            _stare = rezultate.copy()
        if satelit:
            _jurnal(cale, rezultate[cale])


def porneste():
    """Porneste o singura citire; descoperirea dispozitivelor ramane in fundal."""
    global _fir
    with _pornire:
        if _fir is None:
            _fir = threading.Thread(target=_citeste, name='HdsLimiteTuner', daemon=True)
            _fir.start()


def _cale(nim):
    frontend = nim.frontend_id
    return '/dev/dvb/adapter0/frontend%d' % int(frontend) if frontend is not None else None


def _toate(stare):
    """Toate frontend-urile de satelit citite (cele de alt tip au None in stare)."""
    return [c for c, limite in stare.items() if limite is not None]


def _frontends(slot, pozitie, stare):
    # NimManager se foloseste doar daca este deja incarcat. Importul lui ar putea
    # descoperi hardware pe firul apelant; aici citim doar configuratia din memorie.
    # Cand slotul nu se poate lega de un frontend (NimManager lipsa, slot fara frontend_id), se iau toate tunerele de
    # satelit citite: pe un receptor cu un singur tuner de satelit e acelasi lucru, iar o limita stiuta nu se pierde.
    modul = sys.modules.get('Components.NimManager')
    nim = getattr(modul, 'nimmanager', None)
    if nim is None:
        return _toate(stare)
    try:
        satelit = [n for n in nim.nim_slots if n.isCompatible('DVB-S')]
        if slot is not None:
            ale_slotului = [_cale(n) for n in satelit if n.slot == int(slot)]
            if ale_slotului and all(c is not None and c in stare for c in ale_slotului):
                return [c for c in ale_slotului if stare.get(c) is not None]
            return _toate(stare)
        alese = satelit
        if pozitie is not None:
            try:
                alese = [n for n in satelit if any(int(s[0]) == int(pozitie)
                    for s in nim.getSatListForNim(n.slot))]
            except Exception:
                alese = satelit
        # Dispozitivele altor adaptoare, fara slot cunoscut, raman eligibile:
        # configuratia lor de antena nu ne permite sa le excludem.
        mapate = {_cale(n) for n in nim.nim_slots}
        cai = {_cale(n) for n in alese}
        cai.update(c for c in stare if c not in mapate)
        return [c for c in cai if stare.get(c, (None, None)) is not None]
    except (AttributeError, TypeError, ValueError):
        return _toate(stare)


def limite_sr(slot=None, pozitie=None):
    """(min, max) cunoscute, fiecare int sau None; pozitie restrange reuniunea.

    Cu slot folosim frontend_id, niciodata numarul slotului drept dispozitiv.
    O parte necunoscuta la oricare tuner eligibil lasa reuniunea libera acolo.
    """
    stare = _stare
    limite = [stare.get(cale, (None, None)) for cale in _frontends(slot, pozitie, stare)]
    if not limite:
        return None, None
    minime, maxime = zip(*limite)
    return (min(minime) if all(x is not None for x in minime) else None,
            max(maxime) if all(x is not None for x in maxime) else None)


def sursa_limitelor(slot=None, pozitie=None):
    """Sursa marginilor folosite acum, pentru jurnal."""
    return 'tuner' if any(x is not None for x in limite_sr(slot, pozitie)) else 'necunoscut'


def pune_limite_pentru_test(limite):
    """Inlocuieste citirea cu {cale_frontend: (min, max)}, numai in probele PC."""
    global _stare, _proba
    _proba = True
    _stare = dict((cale, tuple(_margine(x) for x in valori)) for cale, valori in limite.items())


def limite_camp_sr():
    """Marginile campului de cinci cifre, in kSymb/s; nu presupun capacitati."""
    minim, maxim = limite_sr()
    jos = min(99999, max(1, minim // 1000)) if minim is not None else 1
    sus = min(99999, max(1, maxim // 1000)) if maxim is not None else 99999
    return jos, sus


porneste()

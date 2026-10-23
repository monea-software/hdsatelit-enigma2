# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Sesiunile deschise de pluginuri pe portul 8001 si memoria vmalloc a driverului. Facut de hdsatelit.com.

DOVEDIT pe Amiko Viper 4K V20 (HiSilicon): fiecare sesiune pe portul 8001 lasa in driver o zona
vmalloc de 4 MB (in /proc/vmallocinfo, marimea 4194304; 4198400 = 4 MB + pagina de garda pe alte nuclee) care nu se mai elibereaza. Dupa ~45 de
sesiuni decodorul video si inregistrarea nu mai pornesc pana la repornirea completa a receptorului.

Contorul (fisier text in /tmp, deci se goleste la repornirea receptorului):
    /tmp/hds-8001-sesiuni   un rand pe sesiune: "<uptime_s> <epoch_s> <cine>\\n", adaugat cu O_APPEND
Il scriu releul DAB (ETI prin 8001, din Python) si t2mi_decap (C, optiunea -c), in acelasi format. Un rand cu uptime mai
mare decat uptime-ul de acum e de dinainte de o repornire si nu se numara.
    /tmp/hds-8001-baza      numarul de zone de 4 MB vazut inainte de prima sesiune a pluginurilor (JSON)

Cititorul vmalloc numara intrarile cu una din marimile MARIMI_ZONA (pe Viper 4K V20 zonele pierdute au 4194304 octeti, masurat 24 -> 29 dupa 5 sesiuni; 4198400 numara doar o zona fixa, care nu creste); daca /proc/vmallocinfo nu se poate citi ramane doar contorul.
Doar biblioteca standard; merge cu Python 2.7 si 3.x. Nu arunca exceptii."""
import json
import os
import time

CONTOR = '/tmp/hds-8001-sesiuni'
BAZA = '/tmp/hds-8001-baza'
VMALLOCINFO = '/proc/vmallocinfo'
MEMINFO = '/proc/meminfo'
UPTIME = '/proc/uptime'
MARIME_ZONA = 4194304             # 4 MB, zona pierduta la fiecare sesiune (masurat pe receptor)
MARIMI_ZONA = (MARIME_ZONA, MARIME_ZONA + 4096)   # si varianta cu pagina de garda, pe alte nuclee
CONTOR_MAX = 256 * 1024           # contorul nu creste la nesfarsit (256 KB = mii de sesiuni)
TOLERANTA_UPTIME_S = 5

PRAG_SESIUNI = 30                 # zone scurse (sau sesiuni numarate) de la care receptorul trebuie repornit
PRAG_LIBER_KB = 64 * 1024         # vmalloc liber sub atat: decodorul video cere ~17 MB dintr-o bucata


def uptime(cale=UPTIME):
    try:
        with open(cale, 'rb') as f:
            return float(f.read(64).split()[0])
    except (IOError, OSError, ValueError, IndexError):
        return None


def noteaza(cine, cale=CONTOR, cale_uptime=UPTIME, acum=None):
    """O sesiune noua pe 8001 (raspuns 200 fara eroare in corp). -> True daca s-a scris."""
    try:
        u = uptime(cale_uptime)
        if u is None:
            u = 0.0
        try:
            if os.path.getsize(cale) > CONTOR_MAX:
                return False
        except OSError:
            pass
        # un contor de dinainte de o repornire (uptime mai mic acum) se inlocuieste
        ultim = _ultimul_uptime(cale)
        if ultim is not None and ultim > u + TOLERANTA_UPTIME_S:
            try:
                os.remove(cale)
            except OSError:
                pass
            try:
                os.remove(BAZA if cale == CONTOR else cale + '.baza')
            except OSError:
                pass
        linie = ('%d %d %s\n' % (int(u), int(acum if acum is not None else time.time()),
                                 ''.join(c for c in str(cine) if c.isalnum() or c in '_-.')[:32] or '-')).encode('ascii')
        fd = os.open(cale, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, linie)
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def _ultimul_uptime(cale):
    try:
        with open(cale, 'rb') as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - 128))
            randuri = f.read().splitlines()
        for r in reversed(randuri):
            p = r.split()
            if p and p[0].isdigit():
                return int(p[0])
    except (IOError, OSError, ValueError):
        pass
    return None


def numar(cale=CONTOR, cale_uptime=UPTIME):
    """Sesiunile 8001 deschise de pluginuri de la pornirea receptorului."""
    u = uptime(cale_uptime)
    try:
        with open(cale, 'rb') as f:
            date = f.read(CONTOR_MAX + 4096)
    except (IOError, OSError):
        return 0
    n = 0
    for r in date.splitlines():
        p = r.split()
        if len(p) < 2 or not p[0].isdigit():
            continue
        if u is not None and int(p[0]) > u + TOLERANTA_UPTIME_S:
            continue
        n += 1
    return n


def citeste_vmalloc(cale=VMALLOCINFO, cale_meminfo=MEMINFO, marime=MARIMI_ZONA):
    """-> dict {'zone': n, 'folosit_kb', 'total_kb', 'liber_kb', 'gol_max_kb'} sau None daca nu se poate citi.
    zone = intrarile cu exact `marime` octeti (un numar sau o lista de marimi). gol_max_kb = cel mai mare spatiu intre zone (estimare)."""
    try:
        with open(cale, 'rb') as f:
            date = f.read(4 * 1024 * 1024)
    except (IOError, OSError):
        return None
    marimi = (marime,) if isinstance(marime, int) else tuple(marime)
    zone = 0
    folosit = 0
    intervale = []
    for r in date.splitlines():
        p = r.split()
        if len(p) < 2:
            continue
        try:
            m = int(p[1])
            a, b = p[0].split(b'-')
            intervale.append((int(a, 16), int(b, 16)))
        except (ValueError, TypeError):
            continue
        folosit += m
        if m in marimi:
            zone += 1
    if not intervale:
        return None
    total_kb = None
    try:
        with open(cale_meminfo, 'rb') as f:
            for r in f.read(16384).splitlines():
                if r.startswith(b'VmallocTotal:'):
                    total_kb = int(r.split()[1])
                    break
    except (IOError, OSError, ValueError, IndexError):
        pass
    intervale.sort()
    gol = 0
    for (a1, b1), (a2, b2) in zip(intervale, intervale[1:]):
        if a2 > b1:
            gol = max(gol, a2 - b1)
    rez = {'zone': zone, 'folosit_kb': folosit // 1024, 'total_kb': total_kb, 'gol_max_kb': gol // 1024}
    rez['liber_kb'] = (total_kb - folosit // 1024) if total_kb else None
    return rez


def baza(zone, sesiuni, cale=BAZA):
    """Zonele de 4 MB de dinaintea pluginurilor. Prima citire o fixeaza: daca pluginurile deschisesera deja sesiuni,
    se scad din zonele vazute."""
    try:
        with open(cale, 'rb') as f:
            d = json.loads(f.read(4096).decode('utf-8'))
        if isinstance(d, dict) and isinstance(d.get('zone'), int):
            return d['zone']
    except (IOError, OSError, ValueError):
        pass
    b = max(0, int(zone) - int(sesiuni))
    try:
        tmp = cale + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(json.dumps({'zone': b, 'sesiuni_la_citire': int(sesiuni), 't': int(time.time())}).encode('utf-8'))
        os.rename(tmp, cale)
    except (IOError, OSError):
        pass
    return b


PROC_TCP = ('/proc/net/tcp', '/proc/net/tcp6')
PORT_8001_HEX = '1F41'
STARE_ASCULTA = '0A'


def conexiuni_8001(cai=PROC_TCP, port_hex=PORT_8001_HEX):
    """Socketurile deschise ale serverului de stream enigma2 (port local 8001), in afara celui care asculta: cele
    stabilite si cele pe care enigma2 inca nu le-a inchis (CLOSE_WAIT). -> numar, sau None daca nu se poate citi.
    Folosit la plecarea de pe un canal 8001 (fisier mic, fara asteptare; 0.1.4)."""
    n = 0
    citit = False
    for cale in cai:
        try:
            with open(cale, 'rb') as f:
                date = f.read(256 * 1024)
        except (IOError, OSError):
            continue
        citit = True
        for r in date.splitlines()[1:]:
            p = r.split()
            if len(p) < 4:
                continue
            try:
                local = p[1].decode('ascii')
                stare_ = p[3].decode('ascii')
            except (UnicodeDecodeError, AttributeError):
                continue
            if local.rpartition(':')[2].upper() == port_hex and stare_.upper() != STARE_ASCULTA:
                n += 1
    return n if citit else None


def stare(cale=CONTOR, cale_vmalloc=VMALLOCINFO, cale_meminfo=MEMINFO, cale_baza=BAZA, cale_uptime=UPTIME,
          prag_sesiuni=PRAG_SESIUNI, prag_liber_kb=PRAG_LIBER_KB):
    """Tot ce trebuie paznicului. -> dict cu 'sesiuni', 'vmalloc' (sau None), 'scurse', 'trebuie_repornit', 'motiv'."""
    s = numar(cale, cale_uptime)
    v = citeste_vmalloc(cale_vmalloc, cale_meminfo)
    rez = {'sesiuni': s, 'vmalloc': v, 'scurse': s, 'trebuie_repornit': False, 'motiv': ''}
    if v is not None:
        b = baza(v['zone'], s, cale_baza)
        rez['baza'] = b
        rez['scurse'] = max(0, v['zone'] - b)
    if rez['scurse'] >= prag_sesiuni:
        rez['trebuie_repornit'] = True
        rez['motiv'] = '%d zone de 4 MB pierdute de driver (%d sesiuni 8001 ale pluginurilor)' % (rez['scurse'], s)
    elif v is not None and v.get('liber_kb') is not None and v['liber_kb'] < prag_liber_kb:
        rez['trebuie_repornit'] = True
        rez['motiv'] = 'vmalloc liber %d KB (prag %d KB), %d sesiuni 8001' % (v['liber_kb'], prag_liber_kb, s)
    return rez

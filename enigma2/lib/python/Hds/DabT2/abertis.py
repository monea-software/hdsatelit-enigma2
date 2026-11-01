# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Fluxurile de distributie de pe 30W (felul abertis: un multiplex terestru purtat intreg intr-un PID privat): ce face
imaginea singura ca un flux criptat sa poata fi decriptat de modulul de acces al omului, cu cheile puse de el. Facut
de hdsatelit.com.

1. Purtatorul din lamedb e serviciul ADEVARAT al fluxului (SID-ul, ns/tsid/onid de pe satelit), cu PMT-ul citit (CA
   PMT-ul lui pleaca spre modulul de acces) si cu PID-ul de date tinut minte (c:18, cDATAPID): serverul 8001 al
   imaginii pune in flux si PID-urile tinute minte (lib/service/servicedvbrecord.cpp, adaugaPidTinuteMinte). Scrierea
   o face lamedb.py (purtatori_reali); aici numai valorile.
2. Configurarea modulului de acces al omului nu se atinge: imaginea nu scrie in ea nici reguli, nici chei. Modulul
   primeste CA PMT-ul purtatorului ca la orice canal criptat (punctul 1) si decodeaza cu ce are pus de om; masurat pe
   un receptor de proba: 17 fluxuri decodate fara nicio regula scrisa de noi.
3. Automatizarile altora: desfacerea o face mereu imaginea, si cu un alt automat instalat. Unde s-ar dubla scrierile
   imaginea se da la o parte pe fluxurile de care se ocupa ei (/etc/astra/astra.conf cu blocurile lor, purtatorii lor
   din lamedb cu furnizorul ABERTIS): purtatorul lor ramane neatins (releul nostru cere chiar referinta lui). Adresele canalelor din listele lor (pid_din_adresa_straina) se redau prin desfacerea
   noastra (pornire.Controlor._extensie_zap); decapsulatorul lor nu e pornit de noi si, daca asculta deja, nu e oprit.
   Fara mesaje.

Toate functiile primesc radacina sistemului de fisiere (implicit „/”), ca probele sa lucreze pe o radacina falsa.
Merge pe Python 3 si pe Python 2.7.
"""
import io
import os
import re

CAID_BISS = 0x2600
# urmele automatelor altora pentru aceste fluxuri (numai citite; nimic nu se schimba la ei): fisierul de configurare al
# decapsulatorului lor si purtatorii lor din lamedb
ASTRA_CONF = 'etc/astra/astra.conf'
FURNIZOR_STRAIN = 'ABERTIS'
_PID_ASTRA = re.compile(r'(?:abertis\s+|abertis/pid|Abertis PID\s+)(\d{1,4})\b', re.I)
# adresele canalelor din listele altor automate: iesirea decapsulatorului lor (portul 9999) sau forma scrisa uneori cu
# 8001 (intrarea lor); 127.0.0.1 sau localhost
_ADRESA_STRAINA = re.compile(r'^https?://(?:127\.0\.0\.1|localhost)(?::(?:9999|8001))?/abertis/pid(\d{1,4})/?$', re.I)


def _cale(radacina, rel):
    return os.path.join(radacina or '/', rel)


def _citeste(cale):
    try:
        with io.open(cale, encoding='utf-8', errors='replace') as f:
            return f.read()
    except (IOError, OSError):
        return None


# ---------------------------------------------------------------- purtatorul adevarat
def sid_purtator(feed):
    """SID-ul serviciului purtator: din lista (feed['purtator']['sid'] sau feed['sid']), altfel PID + 1000 (asa sunt
    numerotati purtatorii pe 30W: PID 2050 -> SID 3050, PID 8002 -> SID 1002 e scris in lista)."""
    p = feed.get('purtator') or {}
    for v in (p.get('sid'), feed.get('sid')):
        try:
            if v is not None and 0 < int(v) < 0x10000:
                return int(v)
        except (TypeError, ValueError):
            pass
    return (int(feed.get('pid') or 0) + 1000) & 0xFFFF


# ---------------------------------------------------------------- automatele altora
def fluxuri_straine(radacina='/', lamedb_text=None):
    """-> (exista_automat, set de PID-uri de care se ocupa ei). PID-urile vin din astra.conf (blocurile lor) si din
    purtatorii lor din lamedb (furnizorul ABERTIS, numele „Abertis PID n”)."""
    exista = False
    pid_uri = set()
    text = _citeste(_cale(radacina, ASTRA_CONF))
    if text is not None:
        exista = True
        pid_uri.update(int(x) for x in _PID_ASTRA.findall(text) if 0 < int(x) < 0x1FFF)
    if lamedb_text is None:
        lamedb_text = _citeste(_cale(radacina, 'etc/enigma2/lamedb')) or ''
    randuri = lamedb_text.split('\n')
    for i in range(1, len(randuri) - 1):
        if randuri[i + 1].startswith('p:%s' % FURNIZOR_STRAIN):
            m = re.match(r'Abertis PID\s+(\d{1,4})', randuri[i].strip(), re.I)
            if m:
                exista = True
                pid_uri.add(int(m.group(1)))
    return exista, pid_uri


def e_strain(feed, straine):
    """Fluxul e al altui automat (nu ne atingem de el)."""
    _exista, pid_uri = straine
    try:
        return int(feed.get('pid') or -1) in pid_uri
    except (TypeError, ValueError):
        return False


def pid_din_adresa_straina(ref):
    """Referinta unui canal din lista altui automat pentru aceste fluxuri (1:0:<tip>:<SID>:<TSID>:<ONID>:...:
    http%3a//localhost%3a9999/abertis/pid<N>:<nume>) -> {'pid', 'sid', 'tsid', 'onid', 'tip', 'nume'} sau None.
    SID-ul, TSID-ul si ONID-ul sunt ale programului din multiplexul desfacut."""
    try:
        parti = str(ref or '').split(':')
        if len(parti) < 11:
            return None
        url = parti[10].replace('%3A', ':').replace('%3a', ':')
        m = _ADRESA_STRAINA.match(url)
        if not m:
            return None
        pid = int(m.group(1))
        if not 0 < pid < 0x1FFF:
            return None
        return {'pid': pid, 'sid': int(parti[3], 16), 'tsid': int(parti[4], 16), 'onid': int(parti[5], 16),
                'tip': int(parti[2], 16) or 1, 'nume': ':'.join(parti[11:])}
    except (ValueError, IndexError, TypeError):
        return None

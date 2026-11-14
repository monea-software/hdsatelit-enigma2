# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Canalele DAB+ si DVB-T2 prin satelit din listele facute in alte imagini (aduse prin FTP sau dintr-un editor de liste
pe PC): referintele lor duc la mecanismul imaginii de unde vin, deci la noi ar ramane mute sau negre. La zap, pornire.py
le recunoaste aici si le reda prin releul nostru (127.0.0.1:8898 DAB, 8889 T2), acelasi post; lista omului nu se
atinge. Facut de hdsatelit.com.

Formele recunoscute (din listele publice):
  DAB+ nativ (tipul 4115):  4115:0:<tip parinte>:<SID parinte>:<TSID>:<ONID>:<NS>:<PID>:<SID DAB>:<ansamblu>:
                            dab%3a//<ts2na|ts2na12|tsniv2ni|ip%3aport>:<nume>   (campurile in hex)
  DAB+ prin dabstreamer:    4097:0:2:...:http%3a//<gazda>%3a5237/<unealta>/<referinta parinte>/<pid>[/<offset>]
                            [/<ip>/<port>]/<SID DAB>:<nume>   (PID si offset zecimal, SID-ul 0x...)
  DVB-T2 prin decapsulator: 1:0:<tip>:<SID>:<TSID>:<ONID>:0:0:0:0:http%3a//<0.0.0.0|localhost|127.0.0.1>%3a9999/<cale>:<nume>
                            (in afara de /abertis/pidN, de care se ocupa abertis.py): programul se cauta dupa
                            SID/TSID/ONID in posturile invatate ale feed-urilor noastre.
Feed-ul DAB se alege dupa pozitie (NS >> 16), PID si fel (la EDI si adresa, portul); la mai multi, cel cu acelasi SID
parinte. Totul fara disc si fara enigma2: lista si posturile invatate le da apelantul. Merge pe Python 3 si 2.7.
"""
import re

PORT_DABSTREAMER = 5237
_GAZDE = r'(?:127\.0\.0\.1|localhost|0\.0\.0\.0)'
_DECAPSULATOR = re.compile(r'^https?://' + _GAZDE + r':9999/(.+)$', re.I)
_DABSTREAMER = re.compile(r'^https?://[^/:]+:%d/(.+)$' % PORT_DABSTREAMER, re.I)


def _int16(v):
    try:
        return int(v, 16)
    except (TypeError, ValueError):
        return None


def _fara_cod(text):
    return text.replace('%3A', ':').replace('%3a', ':').replace('%2F', '/').replace('%2f', '/')


# ---------------------------------------------------------------- DAB+
def _feed_dab(lista, poz, pid, fel, ip=None, port=None, sid_parinte=None):
    """-> feed-ul DAB din lista (pozitia, PID-ul, felul si, la EDI, adresa si portul), sau None."""
    gasite = []
    for tp in (lista or {}).get('transpondere', []):
        try:
            if int(tp.get('pozitie')) != poz:
                continue
        except (TypeError, ValueError):
            continue
        for f in tp.get('feeduri', []):
            if f.get('tip') != 'dab' or f.get('pid') != pid or str(f.get('fel') or '') != fel:
                continue
            if fel == 'edi' and (str(f.get('ip') or '') != ip or f.get('port') != port):
                continue
            gasite.append(f)
    if not gasite:
        return None
    if sid_parinte is not None:
        for f in gasite:
            if f.get('sid_parinte') == sid_parinte:
                return f
    return gasite[0]


def dab_din_ref(text, lista):
    """Referinta unui post DAB+ din alta imagine -> (feed, SID DAB) din lista noastra, sau None."""
    parti = str(text or '').split(':')
    if len(parti) < 11:
        return None
    if parti[0] == '4115':
        cale = _fara_cod(parti[10])
        if not cale.startswith('dab//') and not cale.startswith('dab://'):
            # campul URL e „dab%3a//...”: dupa decodare „dab://...”; „:” din adresa EDI s-a despartit in campuri
            return None
        tinta = cale.split('//', 1)[1]
        if len(parti) > 11 and re.match(r'^\d+$', parti[11] or '') and re.match(r'^[\d.]+$', tinta):
            tinta = tinta + ':' + parti[11]           # „dab%3a//239.1.2.3:2048” scris fara cod la port
        valori = [_int16(parti[k]) for k in range(2, 10)]
        if None in valori:
            return None
        _tip, sid_par, _tsid, _onid, ns, pid, sid, _ansamblu = valori
        poz = (ns >> 16) & 0xFFFF
        if tinta in ('ts2na', 'ts2na12', 'tsniv2ni'):
            feed = _feed_dab(lista, poz, pid, tinta, sid_parinte=sid_par)
        else:
            m = re.match(r'^([\d.]+):(\d+)$', tinta)
            if not m:
                return None
            feed = _feed_dab(lista, poz, pid, 'edi', m.group(1), int(m.group(2)), sid_par)
        return (feed, sid) if feed is not None and sid else None
    url = _fara_cod(':'.join(parti[10:]))
    m = _DABSTREAMER.match(url)
    if not m:
        return None
    # ref parinte cu „:” in ea: 1:0:1:1:FA:C8:DDE0000:0:0:0 (10 campuri), apoi parametrii despartiti prin „/”
    rest = m.group(1)
    unealta, _, rest = rest.partition('/')
    bucati = rest.split('/')
    sref = bucati[0].split(':') if bucati else []
    if len(sref) < 7:
        return None
    sid_par, ns = _int16(sref[3]), _int16(sref[6])
    if ns is None:
        return None
    poz = (ns >> 16) & 0xFFFF
    param = bucati[1:]
    # numele postului poate urma dupa ultimul parametru („0x5201:Rai Radio1”)
    if param:
        param[-1] = param[-1].split(':', 1)[0]
    try:
        if unealta == 'tsniv2ni' and len(param) == 2:
            pid, sid, fel = int(param[0]), int(param[1], 16), 'tsniv2ni'
            feed = _feed_dab(lista, poz, pid, fel, sid_parinte=sid_par)
        elif unealta in ('ts2na', 'ts2ni') and len(param) == 3:
            pid, offset, sid = int(param[0]), int(param[1]), int(param[2], 16)
            fel = 'ts2na12' if offset == 12 else 'ts2na'
            feed = _feed_dab(lista, poz, pid, fel, sid_parinte=sid_par)
        elif unealta == 'fedi2eti' and len(param) == 4:
            pid, sid = int(param[0]), int(param[3], 16)
            feed = _feed_dab(lista, poz, pid, 'edi', param[1], int(param[2]), sid_par)
        else:
            return None
    except ValueError:
        return None
    return (feed, sid) if feed is not None and sid else None


# ---------------------------------------------------------------- DVB-T2 prin decapsulator
def t2_din_ref(text, lista, servicii):
    """Referinta unui program DVB-T2 dintr-o lista facuta pentru un decapsulator (portul 9999, alta cale decat
    /abertis/) -> (feed, {'sid', 'tsid', 'onid', 'tip', 'nume'}), daca programul (SID, TSID, ONID) e intre posturile
    invatate ale unui feed T2 din lista. servicii: {id feed: [{'sid', 'tsid', 'onid', ...}]} (invatate pe receptor,
    apoi cele de pe stb). None altfel."""
    parti = str(text or '').split(':')
    if len(parti) < 11 or parti[0] not in ('1', '4097', '5001', '5002'):
        return None
    url = _fara_cod(parti[10])
    m = _DECAPSULATOR.match(url)
    if not m or m.group(1).lower().startswith('abertis/'):
        return None
    valori = [_int16(parti[k]) for k in range(2, 6)]
    if None in valori:
        return None
    tip, sid, tsid, onid = valori
    if not sid:
        return None
    from .buchete import _curata_id
    feeduri = {}
    for tp in (lista or {}).get('transpondere', []):
        for f in tp.get('feeduri', []):
            if f.get('tip') == 't2':
                feeduri[_curata_id(f.get('id'))] = f
    for feed_id, posturi in (servicii or {}).items():
        f = feeduri.get(_curata_id(feed_id))
        if isinstance(posturi, dict):
            posturi = posturi.get('servicii')
        if f is None or not isinstance(posturi, list):
            continue
        for s in posturi:
            try:
                if int(s.get('sid')) == sid and int(s.get('tsid')) == tsid and int(s.get('onid')) == onid:
                    return f, {'sid': sid, 'tsid': tsid, 'onid': onid, 'tip': tip or 1,
                               'nume': ':'.join(parti[11:])}
            except (TypeError, ValueError, AttributeError):
                continue
    return None


def pare_strain(text, tip):
    """Numai dupa forma textului (fara lista, fara disc; pentru zap-urile din alt fir): referinta poate fi un post al
    altei imagini pe care il recunoaste dab_din_ref (tip 'dab') sau t2_din_ref (tip 't2')."""
    parti = str(text or '').split(':')
    if len(parti) < 11:
        return False
    if tip == 'dab':
        if parti[0] == '4115':
            return _fara_cod(parti[10]).startswith('dab://')
        return _DABSTREAMER.match(_fara_cod(':'.join(parti[10:]))) is not None
    m = _DECAPSULATOR.match(_fara_cod(parti[10]))
    return m is not None and not m.group(1).lower().startswith('abertis/')

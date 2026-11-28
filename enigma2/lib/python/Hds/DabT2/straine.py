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
                            Lists without the real multiplex ids (TSID 0x3157 + ONID = T2-MI PID, or TSID = MHz +
                            ONID = orbital position) are matched by PID, frequency in the path, position and SID.
Feed-ul DAB se alege dupa pozitie (NS >> 16), PID si fel (la EDI si adresa, portul); la mai multi, cel cu acelasi SID
parinte. Totul fara disc si fara enigma2 (lista si posturile invatate le da apelantul), in afara de
driver_decapsuleaza_t2mi si tunerele T2-MI (tunere_t2mi, tunere_satelit, tunere_amestecate), care se uita o data in
/proc. Merge pe Python 3 si 2.7.
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
    apoi cele de pe stb). None altfel.
    Without an exact match, the forms that do not carry the real multiplex ids (TSID 0x3157 + ONID = T2-MI PID, or
    TSID = MHz + ONID = orbital position) are matched by PID / frequency / position and SID (_t2_dupa_forma)."""
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
    nume = ':'.join(parti[11:])
    feeduri = _feeduri_t2(lista, servicii)
    # 1. exact SID/TSID/ONID among the learned programs (receiver, then stb), then those shipped in the list
    for f, _tp, posturi in feeduri:
        for s in posturi:
            if _ids(s) == (sid, tsid, onid):
                return f, {'sid': sid, 'tsid': tsid, 'onid': onid, 'tip': tip or 1, 'nume': nume}
    # 2. lists built for other decapsulators do not carry the real TSID/ONID of the T2 multiplex:
    #    TSID 0x3157 + ONID = T2-MI PID (ciefp form), the frequency often in the path (krrt/12285krrt801);
    #    TSID = frequency in MHz + ONID = orbital position (krrt/12285krrt800 as 1:0:1:3:2FFD:EB:...).
    x = _t2_dupa_forma(feeduri, m.group(1), sid, tsid, onid, nume)
    if x is None:
        return None
    f, s = x
    return f, {'sid': sid, 'tsid': s[0], 'onid': s[1], 'tip': tip or s[2] or 1, 'nume': nume}


TSID_DECAPSULATOR = 0x3157
_MHZ_IN_CALE = re.compile(r'(?<!\d)(\d{4,5})(?!\d)')


def _ids(s):
    try:
        return int(s.get('sid')), int(s.get('tsid')), int(s.get('onid'))
    except (TypeError, ValueError, AttributeError):
        return None


def _feeduri_t2(lista, servicii):
    """[(feed, transponder, programs)] for every T2 feed of the list, in list order. programs: learned on the receiver
    or published on stb (servicii, keyed by feed id; a list or {'servicii': [...]}) if any, else the feed's own
    'programe'."""
    from .buchete import _curata_id
    invatate = {}
    for feed_id, posturi in (servicii or {}).items():
        if isinstance(posturi, dict):
            posturi = posturi.get('servicii')
        if isinstance(posturi, list) and posturi:
            invatate[_curata_id(feed_id)] = posturi
    rez = []
    for tp in (lista or {}).get('transpondere', []):
        for f in tp.get('feeduri', []):
            if f.get('tip') != 't2':
                continue
            posturi = invatate.get(_curata_id(f.get('id')))
            if posturi is None:
                posturi = f.get('programe') if isinstance(f.get('programe'), list) else []
            rez.append((f, tp, [s for s in posturi if isinstance(s, dict)]))
    return rez


def _cheie_nume(text):
    """Channel name reduced to lower-case letters and digits (unicode), for comparing names between lists."""
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'ignore')
    text = text.replace('%20', ' ')
    return u''.join(ch for ch in text.lower() if ch.isalnum())


def _mhz(tp):
    try:
        return int(tp.get('frecventa')) / 1000.0
    except (TypeError, ValueError):
        return None


def _aproape(tp, mhz):
    f = _mhz(tp)
    return f is not None and abs(f - mhz) <= 2


def _t2_dupa_forma(feeduri, cale, sid, tsid, onid, nume):
    """Second pass of t2_din_ref for the decapsulator forms without the real multiplex ids. -> (feed, (tsid, onid,
    tip)) or None.
    Candidates: T2-MI feeds with PID == ONID (TSID 0x3157) and, if the path holds a frequency (4-5 digits, MHz), on
    that frequency +-2 MHz; or, for TSID = MHz and ONID = position, the T2-MI feeds of that transponder.
    Then the SID: a feed whose known programs have the SID with the same name (or no name on one side) wins (first
    in list order); a feed that has the SID under another name is a different multiplex and drops out; otherwise a
    single remaining candidate is taken (programs not learned yet, e.g. an encrypted multiplex)."""
    t2mi = [(f, tp, p) for f, tp, p in feeduri if str(f.get('fel') or '') == 't2mi']
    pid_onid = tsid == TSID_DECAPSULATOR and 0 < onid < 0x1FFF
    # C band 3400-4200 and Ku band 10700-12750 MHz; a number equal to the PID (krrt_4097) is the PID, not a frequency
    frecventa = lambda v: (3398 <= v <= 4202 or 10698 <= v <= 12752) and not (pid_onid and v == onid)
    frecvente = [int(x) for x in _MHZ_IN_CALE.findall(cale) if frecventa(int(x))]
    cand = []
    if pid_onid:
        cand = [c for c in t2mi if c[0].get('pid') == onid]
        if frecvente:
            cand = [c for c in cand if any(_aproape(c[1], mhz) for mhz in frecvente)]
    elif 2000 <= tsid <= 13000 and 0 < onid < 3600:
        for c in t2mi:
            try:
                if int(c[1].get('pozitie')) == onid and _aproape(c[1], tsid):
                    cand.append(c)
            except (TypeError, ValueError):
                continue
    if not cand:
        return None
    cheie = _cheie_nume(nume)
    potrivite, fara_nume, ramase = [], [], []
    for f, tp, posturi in cand:
        cu_sid = [s for s in posturi if _ids(s) is not None and _ids(s)[0] == sid]
        if not cu_sid:
            ramase.append((f, posturi))
            continue
        s = cu_sid[0]
        al_lor = _cheie_nume(s.get('nume') or '')
        if cheie and al_lor and cheie != al_lor:
            continue
        if cheie and al_lor:
            potrivite.append((f, s))
        elif pid_onid:
            fara_nume.append((f, s))
        else:
            # MHz/position form: no PID, and two multiplexes of one transponder can share SIDs; without a name the
            # SID proves nothing
            ramase.append((f, posturi))
    for f, s in potrivite + fara_nume:
        return f, (int(s.get('tsid')), int(s.get('onid')), _int_sau(s.get('tip')))
    if len(ramase) != 1:
        if len(cand) != 1:
            return None
        # a single candidate that has the SID under another name (the list was written with an older name)
        f, _tp, posturi = cand[0]
        s = [x for x in posturi if _ids(x) is not None and _ids(x)[0] == sid][0]
        return f, (int(s.get('tsid')), int(s.get('onid')), _int_sau(s.get('tip')))
    f, posturi = ramase[0]
    # same multiplex: the TSID/ONID of its other programs; none known -> keep those of the reference (the stream is
    # played by SID, the ids only label the service)
    for s in posturi:
        if _ids(s) is not None:
            return f, (int(s.get('tsid')), int(s.get('onid')), None)
    return f, (tsid, onid, None)


def _int_sau(v):
    try:
        return int(v)
    except (TypeError, ValueError):
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


# ---------------------------------------------------------------- DVB-T2 prin satelit cu T2-MI pe transponder
# Driverele care decapsuleaza T2-MI in placa (HiSilicon: SF8008 si familia) au /proc/stb/frontend/N/t2mi; enigma2 le
# trimite PID-ul si PLP-ul la acordare (lib/dvb/frontend.cpp, DTV_ISDBT_SB_SEGMENT_IDX), deci acolo un canal cu T2-MI
# pe transponder merge direct. Pe celelalte (Broadcom: Vu+, ...) driverul ignora campul si ar ramane ecran negru: zap-ul
# trece prin releul nostru, iar daca feed-ul lipseste din lista noastra il face feed_din_t2mi din lamedb.
T2MI_DRIVER = 'proc/stb/frontend/*/t2mi'
_DRIVER_T2MI = {}
_FEC = {1: '1/2', 2: '2/3', 3: '3/4', 4: '5/6', 5: '7/8', 6: '8/9', 7: '3/5', 8: '4/5', 9: '9/10'}
_MODULATIE = {1: 'QPSK', 2: '8PSK', 3: 'QAM16', 4: '16APSK', 5: '32APSK'}
_ROLLOFF = {0: '0.35', 1: '0.25', 2: '0.20'}
_PLS_MOD = {0: 'root', 1: 'gold', 2: 'combo'}


def driver_decapsuleaza_t2mi(radacina='/'):
    """True daca un tuner al receptorului decapsuleaza T2-MI in driver (/proc/stb/frontend/N/t2mi exista; NimManager
    isT2MI in OE-Alliance). Citit o data si tinut minte (procfs nu se schimba cat merge enigma2), deci se poate chema si
    din alt fir dupa prima chemare."""
    if radacina not in _DRIVER_T2MI:
        import glob
        import os
        _DRIVER_T2MI[radacina] = bool(glob.glob(os.path.join(radacina or '/', T2MI_DRIVER)))
    return _DRIVER_T2MI[radacina]


# Receptoarele cu tunere amestecate (unul cu T2-MI in driver, altul fara: un tuner pe USB sau de alt fel langa cele
# HiSilicon): un canal cu T2-MI pe transponder merge direct numai pe tunerul cu T2-MI. lib/dvb/frontend.cpp
# (isCompatibleWith, lib/dvb/hdst2mi.h) nu da transponderul T2-MI tunerului fara T2-MI cand receptorul are si unul cu
# T2-MI, deci enigma2 il porneste direct numai daca tunerul cu T2-MI e liber si prinde satelitul; altfel pornire.py il
# duce prin releul nostru, care merge pe orice tuner. Indicele N din /proc/stb/frontend/N este frontend-ul DVB
# (Frontend_Device din /proc/bus/nim_sockets), ca in frontend.cpp (m_dvbid).
NIM_SOCKETS = 'proc/bus/nim_sockets'
_TUNERE_T2MI = {}
_TUNERE_SAT = {}


def tunere_t2mi(radacina='/'):
    """Frontend-urile al caror driver decapsuleaza T2-MI (/proc/stb/frontend/N/t2mi): frozenset de N. Citit o data si
    tinut minte, ca driver_decapsuleaza_t2mi (procfs, se poate chema si din alt fir)."""
    if radacina not in _TUNERE_T2MI:
        import glob
        import os
        rez = set()
        for cale in glob.glob(os.path.join(radacina or '/', T2MI_DRIVER)):
            n = os.path.basename(os.path.dirname(cale))
            if n.isdigit():
                rez.add(int(n))
        _TUNERE_T2MI[radacina] = frozenset(rez)
    return _TUNERE_T2MI[radacina]


def citeste_tunere_satelit(text):
    """Textul din /proc/bus/nim_sockets -> frozenset cu frontend-urile tunerelor de satelit (Type sau un Mode DVB-S*;
    frontend-ul din Frontend_Device, altfel numarul socketului). Functie pura."""
    socluri, curent = {}, None
    for rand in (text or '').splitlines():
        rand = rand.strip()
        if rand.startswith('NIM Socket'):
            try:
                curent = int(rand.split(' ')[2].rstrip(':'))
            except (IndexError, ValueError):
                curent = None
                continue
            socluri[curent] = {'fe': curent, 'sat': False}
        elif curent is None:
            continue
        elif rand.startswith('Frontend_Device:'):
            try:
                socluri[curent]['fe'] = int(rand[len('Frontend_Device:'):].strip())
            except ValueError:
                pass
        elif rand.startswith('Type:') or (rand.startswith('Mode') and ':' in rand):
            if rand.split(':', 1)[1].strip().upper().startswith('DVB-S'):
                socluri[curent]['sat'] = True
    return frozenset(s['fe'] for s in socluri.values() if s['sat'])


def tunere_satelit(radacina='/'):
    """Frontend-urile tunerelor de satelit, din /proc/bus/nim_sockets (tinut minte); fisierul lipsa: frozenset()."""
    if radacina not in _TUNERE_SAT:
        import os
        try:
            with open(os.path.join(radacina or '/', NIM_SOCKETS)) as f:
                text = f.read()
        except (IOError, OSError):
            text = ''
        _TUNERE_SAT[radacina] = citeste_tunere_satelit(text)
    return _TUNERE_SAT[radacina]


def tunere_amestecate(radacina='/'):
    """True daca receptorul are si tunere de satelit cu T2-MI in driver, si tunere de satelit fara. Fara
    /proc/bus/nim_sockets se socotesc tunerele din /proc/stb/frontend/N (cele fara fisierul t2mi = fara T2-MI)."""
    cu = tunere_t2mi(radacina)
    if not cu:
        return False
    sat = tunere_satelit(radacina)
    if not sat:
        import glob
        import os
        sat = frozenset(int(os.path.basename(c)) for c in glob.glob(os.path.join(radacina or '/', 'proc/stb/frontend/*'))
                        if os.path.basename(c).isdigit())
    return bool(sat - cu)


def _pozitie_text(poz):
    return '%d.%d%s' % ((poz // 10, poz % 10, 'E') if poz <= 1800 else ((3600 - poz) // 10, (3600 - poz) % 10, 'W'))


def feed_din_t2mi(t):
    """Transponderul cu T2-MI din lamedb (lamedb.transpondere_t2mi: poz, khz, pol, sr, fec, sistem, modulatie, rolloff,
    is_id, pls_cod, pls_mod, pid, plp) -> (transponder, feed) in formatul listei (ca feed-ul adaugat de mana), pentru un
    canal din lista altei imagini al carui feed nu e in lista noastra. Functie pura. None daca datele nu ajung."""
    try:
        poz, khz, pol, sr = int(t['poz']), int(t['khz']), 'HVLR'[int(t['pol']) & 3], int(t['sr'])
        pid, plp, is_id = int(t['pid']), int(t['plp']), int(t.get('is_id', -1))
        pls_cod, pls_mod = int(t.get('pls_cod') or 0), int(t.get('pls_mod') or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= poz < 3600 and khz > 0 and sr > 0 and 0 < pid < 0x1FFF and 0 <= plp <= 255):
        return None
    mis = 0 <= is_id <= 255
    tp = {'id': 'lista_%d_%d%s%s' % (poz, khz // 1000, pol.lower(), '_mis%d' % is_id if mis else ''),
          'pozitie': poz, 'frecventa': khz, 'pol': pol, 'sr': sr,
          'sistem': 'DVB-S2' if int(t.get('sistem') or 0) else 'DVB-S',
          'modulatie': _MODULATIE.get(int(t.get('modulatie') or 0), 'AUTO'),
          'fec': _FEC.get(int(t.get('fec') or 0), 'auto'),
          'rolloff': _ROLLOFF.get(int(t.get('rolloff') or 0), '0.35'),
          'is_id': is_id if mis else None,
          'pls_cod': pls_cod if mis or pls_cod else None,
          'pls_mod': _PLS_MOD.get(pls_mod, 'root') if mis or pls_cod else None}
    fid = '%s_%d_plp%d' % (tp['id'], pid, plp)
    feed = {'id': fid, 'tip': 't2', 'fel': 't2mi', 'pid': pid, 'plp': plp,
            'nume': '%s %d %s PID %d PLP %d' % (_pozitie_text(poz), khz // 1000, pol, pid, plp)}
    return tp, feed

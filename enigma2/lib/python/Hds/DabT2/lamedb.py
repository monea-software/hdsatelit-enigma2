# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Serviciile purtatoare T2-MI in lamedb, pentru HdsT2mi. Facut de hdsatelit.com.

Dovedit pe receptor: pachetele T2-MI ajung la noi doar prin portul 8001 al enigma2
(streamserver). Streamserver-ul poate da doar un serviciu pe care enigma2 il stie din lamedb, deci pentru fiecare
PID T2-MI de pe un transponder cu cel putin un feed ACTIV (invatat sau pornit de utilizator) scriem un SERVICIU
PURTATOR (feed nou: la prima pornire, inainte de releu; „Refa buchetele" ii scoate pe cei ramasi fara feed activ):
  - transponderul, cu MIS/PLS daca are (PLS doar cu is_id >= 0), FARA campurile T2-MI: cu ele enigma2 nu mai acordeaza;
  - serviciul tip 1, SID ales de noi (unic, stabil), numele „HDSatelit T2-MI <PID>";
  - a treia linie `p:HDSatelit T2-MI,c:00<PID hex, 4 cifre>,c:03<acelasi PID>,f:04`: PID-ul T2-MI pus ca PID video
    si ca PCR in cache, iar f:04 (dxNoDVB) spune enigma2 sa nu caute PMT si sa foloseasca PID-urile din cache. Fara PCR
    in cache, inregistrarea enigma2 din baza imaginii (servicedvbrecord.cpp doRecord) adauga PID-ul -1 (0xFFFF) primul in
    filtrul demux-ului (vazut pe receptor prin serverul local 8001: program [(0, pat), (4097, video), (-1, pcr)], tuner
    blocat, 0 octeti). Ca reloadServicelist sa ia linia noua, purtatorii se scot intai din memorie (reincarca_servicii).
Releul T2 cere http://127.0.0.1:8001/<referinta purtatorului>; canalele din buchet raman tip 1 cu URL spre releu.
Zap direct pe purtator nu se tine (dovedit); purtatorul nu intra in niciun buchet.

Formatele (citite in eDVBDB din enigma2 7.6):
  lamedb  (4): „eDVB services /4/", „transponders", blocuri de 3 randuri (cheie ns:tsid:onid, „\\ts ...", „/"),
               „end", „services", blocuri de 3 randuri (sid:ns:tsid:onid:tip:0:0, nume, p:...), „end".
               s frecventa:sr:pol:fec:pozitie(cu semn):inversiune:steaguri[:sistem:modulatie:rolloff:pilot[:is_id:pls_cod:pls_mod]]
  lamedb5 (5): „t:ns:tsid:onid,s:...[,MIS/PLS:is_id:cod:mod]" si „s:sid:ns:tsid:onid:tip:0:0,"nume",p:...,c:00pid,f:4".
7.6 citeste doar lamedb; lamedb5 se actualizeaza doar daca exista deja (imaginile care il folosesc il au).

Felul abertis (fluxurile de distributie de pe 30W) are purtatorul ADEVARAT, serviciul de pe satelit al fluxului (SID-ul
lui, transponderul scanat de receptor), cu furnizorul „Abertis 30°W” (FURNIZOR_ABERTIS) si numele fluxului, ca omul
sa-l recunoasca in lista (scanarea il lasa fara nume, „11222H SID 0xbd1”, la un furnizor „DVB-S2 8PSK 11222H ...”):
PMT-ul citit (f:01), PID-ul de date tinut minte (c:18), CAID-ul BISS tinut minte la fluxurile BISS. Se scrie pentru
feed-urile active si pentru orice flux din lista al carui serviciu scanat e deja in lamedb (il inlocuieste, cu acelasi
tip); un transponder nou se scrie numai pentru un feed activ.
0.7.7 (asistenta 213800, Vu+ Uno 4K SE): pe aceeasi cheie sid:ns:tsid:onid pot fi mai multe servicii cu tipuri
diferite (purtatorul altui automat "Abertis PID n", furnizorul ABERTIS, tip 1, PID-ul de date in c:15; serviciul scanat tip
100 sau 12, fara PID de date), iar enigma2 le tine separat, dupa referinta CU tipul. Imaginea scrie mereu purtatorul ei,
pe tipul serviciului scanat pe care il inlocuieste, si nu atinge randurile altor automate (furnizorul ABERTIS sau orice rand
care tine minte PID-ul de date). Purtatorul lor (tip 1) nu se mai foloseste: la noi c:15 e pista de sunet AAC
(eDVBService::setCachedAudio o sterge la redare), iar referinta lor luata cu tipul scanatului (ultimul din fisier) dadea
serviciul fara PID de date: 0 octeti, ecran negru. Numai un rand al lor scris chiar cu tipul 100, cu PID-ul de date si fara
nimic de inlocuit pe cheie, ramane purtatorul releului (_tip_purtator).

Editarea e sigura: fisierul se desparte in blocuri; ale noastre se recunosc dupa furnizorul „HDSatelit T2-MI" sau
„Abertis 30°W" (servicii) si dupa ONID-ul 4844 fara alte servicii pe el (transpondere). Tot restul ramane octet cu octet. Un fisier care nu
se intelege nu se atinge. Daca rezultatul e identic, nu se scrie nimic. Inainte de scriere se pastreaza o copie
(lamedb.hds-copie), apoi fisier temporar + os.replace.
"""
import os

from . import abertis, compat, jurnal, tuner

FURNIZOR = 'HDSatelit T2-MI'
# Si HdsDab scrie purtatori, pentru ETI in TS (ts2na, ts2na12, tsniv2ni) prin 8001. Fiecare plugin isi
# recunoaste doar serviciile lui dupa furnizor, deci unul nu le sterge pe ale celuilalt; un transponder ONID 4844
# ramane cat il foloseste oricare dintre ele.
FURNIZORI = {'t2': FURNIZOR, 'dab': 'HDSatelit ETI'}
FURNIZOR_ABERTIS = compat.text_nativ(u'Abertis 30\u00b0W')     # octeti UTF-8 pe 2.7, ca restul textului lamedb
TIP_DATE = 100                 # tipul unui serviciu de date (asa il scrie scanarea pe purtatorii fara SDT)
FELURI_ETI = ('ts2na', 'ts2na12', 'tsniv2ni')
ONID = 0x4844
CALE4 = '/etc/enigma2/lamedb'
CALE5 = '/etc/enigma2/lamedb5'


def _crc16(text):
    c = 0xFFFF
    for b in bytearray(text.encode('utf-8')):       # bytearray: intregi si pe Python 2.7
        c ^= b << 8
        for _i in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


# ---------------------------------------------------------------- purtatorii
def _curata_id(feed_id):
    """La fel ca buchete._curata_id (id-urile din servicii.json si din URL-uri)."""
    return ''.join(ch for ch in str(feed_id) if ch.isalnum() or ch in '_-.')[:64]


def _al_tipului(f, tip):
    if tip == 'dab':
        return f.get('tip') == 'dab' and str(f.get('fel') or '') in FELURI_ETI
    return f.get('tip') == 't2'


def _nume_purtator(f, pid):
    """„Abertis 2050 RGE Nac (BISS)”: numele fluxului din lista, fara „(Abertis ...)” de la capat."""
    import re
    nume = re.sub(r'\s*\(Abertis[^)]*\)\s*$', '', compat.text_nativ(f.get('nume') or '')).strip()
    nume = nume.replace('"', '').replace(',', ' ').strip()
    if not nume or nume.startswith('Abertis'):
        nume = ''
    biss = str(f.get('acces') or '').upper() == 'BISS'
    return ('Abertis %d %s%s' % (pid, nume, ' (BISS)' if biss else '')).replace('  ', ' ').strip()


def _ns_satelit(p):
    return (p['orbital_position'] << 16) | ((p['frequency'] // 1000) & 0x7FFF) | ((p['polarisation'] & 1) << 15)


# tipurile pe care le ia purtatorul nostru cand tipul serviciului scanat e ocupat de randul altui automat (12 = serviciu de
# date in DVB; 25 si 1 numai daca si acela e ocupat)
TIPURI_DE_REZERVA = (TIP_DATE, 12, 25, 1)


def _rand_strain(rand_p):
    """Randul "p:..." e al altui automat pentru fluxurile de pe 30W (furnizorul ABERTIS); merge si pe restul unei linii
    lamedb5 (campurile despartite prin virgula)."""
    return ('p:%s' % abertis.FURNIZOR_STRAIN) in str(rand_p or '').split(',')


def _rand_pastrat(rand_p, pid):
    """Un serviciu care nu e al nostru, de pe cheia unui purtator adevarat, ramane neatins: e al altui automat
    (furnizorul ABERTIS) sau tine minte PID-ul de date al fluxului (in orice camp c:). Restul (serviciul scanat, fara
    PID de date) il inlocuieste purtatorul nostru."""
    return _rand_strain(rand_p) or pid in _pid_uri_tinute_minte(rand_p)


def _tip_cheie(cheie):
    """Tipul serviciului dintr-o cheie sid:ns:tsid:onid:tip:... (lamedb si lamedb5); None daca nu se intelege."""
    try:
        return int(cheie.split(':')[4])
    except (ValueError, IndexError):
        return None


def _alege_tp(p, sid, tp_reali, identitate=None):
    """Transponderul purtatorului dintre cele din lamedb cu aceeasi pozitie, polarizare, frecventa (+-2 MHz) si is_id:
    intai cel pe care e deja purtatorul nostru pentru SID, apoi cel cu orice serviciu pe SID, apoi cel mai apropiat ca
    frecventa, cel cu namespace-ul frecventei si cel mai mic namespace. Ordinea din fisier nu conteaza (enigma2 rescrie
    lamedb in ordinea lui). identitate: campurile T2-MI invatate filtreaza candidatii.
    -> (ns, tsid, onid) sau None."""
    ns_sat = _ns_satelit(p)
    randuri = tp_reali.get('randuri') or {}
    alese = []
    for t in tp_reali.get('tp') or []:
        # Identitatea T2-MI invatata are prioritate fata de lamedb vechi.
        if identitate and any(k in identitate and identitate[k] != t[k] for k in ('tsid', 'onid')):
            continue
        if t['poz'] == p['orbital_position'] and t['pol'] == p['polarisation'] and \
                abs(t['khz'] - p['frequency']) <= 2000 and (t['is_id'] < 0 or p['is_id'] < 0 or t['is_id'] == p['is_id']):
            r = randuri.get((sid, t['ns'], t['tsid'], t['onid'])) or ()
            ordine = (0 if any(x[2] for x in r) else 1, 0 if r else 1, abs(t['khz'] - p['frequency']),
                      0 if t['ns'] == ns_sat else 1, t['ns'], t['tsid'], t['onid'])
            alese.append((ordine, t))
    if not alese:
        return None
    t = min(alese, key=lambda a: a[0])[1]
    return t['ns'], t['tsid'], t['onid']


def _tip_purtator(randuri, pid, dupa_pid=False):
    """Tipul purtatorului nostru pe cheia lui. randuri: [(tip, pid-uri, al_nostru, strain)] de pe cheie, in ordinea din
    fisier. Tipurile randurilor pastrate (_rand_pastrat) nu se iau niciodata. -> (tip, inlocuieste, strain):
    inlocuieste = pe cheie e deja purtatorul nostru sau un serviciu scanat pe care il inlocuim; strain = pe cheie nu e
    nimic de inlocuit, iar referinta de date (tipul 100) e chiar a altui automat si tine minte PID-ul de date: releul o
    foloseste pe aceea, nimic scris (listele lor scriu tipul 1, deci la ei nu se intampla; probele mai vechi o au)."""
    pastrate = set(r[0] for r in randuri if not r[2] and (r[3] or pid in r[1]))
    if dupa_pid:
        # A carrier owned by another PID has its own service reference.
        pastrate.update(r[0] for r in randuri if r[2] and pid not in r[1])
    proprii = sorted(set(r[0] for r in randuri if r[2]) - pastrate)
    if proprii:
        return proprii[0], True, False
    scanate = sorted(set(r[0] for r in randuri if not r[2]) - pastrate, key=lambda t: (t != TIP_DATE, t))
    if scanate:
        return scanate[0], True, False
    if any(r[0] == TIP_DATE and not r[2] and pid in r[1] for r in randuri):
        return TIP_DATE, False, True
    tipuri = TIPURI_DE_REZERVA
    if dupa_pid:
        tipuri += tuple(t for t in range(1, 256) if t not in tipuri)
    for t in tipuri:
        if t not in pastrate:
            return t, False, False
    return None, False, False


def _purtator_real(f, p, pid, cheie, tp_reali, doar_scanat=False):
    """Felul abertis: purtatorul e serviciul adevarat al fluxului (SID-ul lui, transponderul de pe satelit), cu PMT-ul
    citit si cu PID-ul de date tinut minte (abertis.py, punctul 1). Transponderul: _alege_tp (cheia lui: namespace,
    tsid, onid); altfel tsid/onid din lista (feed['purtator']) si namespace-ul cu frecventa. Tipul: _tip_purtator (al
    serviciului scanat cu aceeasi cheie, altfel 100, niciodata al unui rand pastrat). doar_scanat: None daca pe cheie nu
    e nici purtatorul nostru, nici un serviciu scanat (pentru feed-urile care nu sunt active). Fara tsid si onid: None
    (ramane purtatorul HDSatelit T2-MI)."""
    tp_reali = tp_reali or {}
    pt = f.get('purtator') or {}
    sid = abertis.sid_purtator(f)
    ales = _alege_tp(p, sid, tp_reali, identitate=pt if f.get('fel') == 't2mi' else None)
    if ales is None:
        ns = _ns_satelit(p)
        tsid, onid = pt.get('tsid'), pt.get('onid')
    else:
        ns, tsid, onid = ales
    try:
        tsid, onid = int(tsid) & 0xFFFF, int(onid) & 0xFFFF
    except (TypeError, ValueError):
        return None
    randuri = (tp_reali.get('randuri') or {}).get((sid, ns, tsid, onid)) or ()
    if f.get('fel') == 't2mi':
        # Keep every existing personal service; use a free reference type.
        randuri = [(t, pids, ours, True) for t, pids, ours, _s in randuri]
    tip, inlocuieste, strain = _tip_purtator(randuri, pid, dupa_pid=f.get('fel') == 't2mi')
    if tip is None or (doar_scanat and not inlocuieste and not strain):
        return None
    x = {'cheie': cheie, 'parametri': p, 'pid': pid, 'ns': ns, 'tsid': tsid, 'onid': onid, 'sid': sid, 'tip': tip,
         'nume': _nume_purtator(f, pid), 'furnizor': FURNIZOR_ABERTIS, 'real': True,
         'biss': str(f.get('acces') or '').upper() == 'BISS',
         'ref': '1:0:%X:%X:%X:%X:%X:0:0:0:' % (tip, sid, tsid, onid, ns)}
    if f.get('fel') == 't2mi':
        x.update(nume='%s %d' % (FURNIZOR, pid), furnizor=FURNIZOR, pastreaza=True)
    if strain:
        x.update(strain=True, real=False)       # referinta lor, nimic scris (compune4/compune5 il sar)
    return x


def tp_reali_din(text4):
    """Ce stie lamedb-ul receptorului despre satelit: {'tp': [{ns, tsid, onid, poz, khz, pol, is_id}] (fara ale
    noastre, ONID 4844), 'sv': {(sid, ns, tsid, onid): tip (al ultimului din fisier)}, 'randuri': {(sid, ns, tsid,
    onid): [(tip, PID-urile tinute minte, al_nostru, al_altui_automat)] in ordinea din fisier}}. Pe aceeasi cheie pot fi
    mai multe servicii cu tipuri diferite, pe care enigma2 le tine separat."""
    rez = {'tp': [], 'sv': {}, 'randuri': {}}
    try:
        _antet, tp, sv, _coada = desparte4(text4 or '')
    except Stricat:
        return rez
    for b in tp:
        try:
            ns, tsid, onid = [int(x, 16) for x in b[0].split(':')[:3]]
            if onid == ONID or not b[1].lstrip().startswith('s '):
                continue
            c = b[1].lstrip()[2:].split(':')
            poz = int(c[4])
            rez['tp'].append({'ns': ns, 'tsid': tsid, 'onid': onid, 'poz': poz + 3600 if poz < 0 else poz,
                              'khz': int(c[0]), 'pol': int(c[2]), 'is_id': int(c[11]) if len(c) > 11 else -1})
        except (ValueError, IndexError):
            continue
    for b in sv:
        try:
            parti = b[0].split(':')
            k = tuple(int(parti[k], 16) for k in range(4))
            tip = int(parti[4])
        except (ValueError, IndexError):
            continue
        rez['sv'][k] = tip
        rez['randuri'].setdefault(k, []).append((tip, _pid_uri_tinute_minte(b[2]),
                                                 _al_nostru_furnizor(b[2], (FURNIZOR_ABERTIS, FURNIZOR)), _rand_strain(b[2])))
    return rez


def _pid_uri_tinute_minte(rand_p):
    """PID-urile tinute minte de un serviciu („p:...,c:TTPPPP,...”; TT zecimal, PPPP hex), cum le pune inregistrarea in
    filtru (servicedvbrecord.cpp adaugaPidTinuteMinte): fara intrarile care nu sunt PID-uri (5-8: tipul video, canalul
    de sunet, intarzierile) si fara cele pe care enigma2 nu le tine (22 si mai mult); din subtitrare (9) numai PID-ul,
    bitii 16-31."""
    rez = set()
    for camp in str(rand_p or '').split(','):
        if not camp.startswith('c:') or len(camp) < 5:
            continue
        try:
            tip, pid = int(camp[2:4]), int(camp[4:], 16)
        except ValueError:
            continue
        if tip == 9:
            pid = (pid >> 16) & 0xFFFF
        if tip not in (5, 6, 7, 8) and tip < 22 and 0 < pid < 0x1FFF:
            rez.add(pid)
    return rez


def _t2mi_biss_real(f):
    # Never infer a T2-MI SID from the data PID.
    pt = f.get('purtator') or {}
    return (f.get('fel') == 't2mi' and f.get('acces') == 'BISS' and isinstance(pt, dict)
            and isinstance(pt.get('sid'), int) and not isinstance(pt['sid'], bool) and 0 < pt['sid'] < 65536
            and all(isinstance(pt[k], int) and not isinstance(pt[k], bool) and 0 <= pt[k] < 65536
                    for k in ('tsid', 'onid') if k in pt))


def purtatori(lista, active=None, tip='t2', tp_reali=None, straine=None):
    """Lista unita de feed-uri -> purtatorii necesari (unul pe transponder + PID T2-MI), in ordine stabila.

    active: multimea id-urilor de feed ACTIVE (invatate sau pornite de utilizator); doar pentru ele se scrie un
    purtator (lamedb-ul utilizatorului nu primeste cate o intrare pentru fiecare feed din
    lista). None = toate feed-urile T2 din lista (doar pentru probe si unelte).
    Felul abertis: purtatorul adevarat (_purtator_real) cand se stiu tsid/onid, si pentru feed-urile care nu sunt
    active, daca serviciul lor scanat e deja in lamedb (numele si furnizorul pe care omul le recunoaste). Si pentru
    fluxurile de care se ocupa alt automat se scrie purtatorul nostru, langa randurile lor, pe care nu le atinge (0.7.7;
    strain=True numai in cazul din _tip_purtator); `straine` ramane numai pentru cei care o dau inca."""
    rez, vazute = [], set()
    # Reserve references locally, without changing the caller's lamedb snapshot.
    tp_reali = dict(tp_reali or {})
    tp_reali['randuri'] = {k: list(v) for k, v in (tp_reali.get('randuri') or {}).items()}
    for tp in lista.get('transpondere', []):
        feeduri = [f for f in tp.get('feeduri', []) if _al_tipului(f, tip) and f.get('pid') is not None
                   and (active is None or _curata_id(f.get('id')) in active
                        or (tip == 't2' and (str(f.get('fel') or '') == 'abertis' or _t2mi_biss_real(f))))]
        if not feeduri:
            continue
        p = tuner.parametri(tp)
        if not p['frequency'] or not p['symbol_rate']:
            continue
        for f in feeduri:
            pid = int(f['pid']) & 0x1FFF
            cheie = '%d:%d:%d:%d:%d' % (p['orbital_position'], p['frequency'] // 1000, p['polarisation'],
                                        p['is_id'], pid)
            if cheie in vazute:
                continue
            vazute.add(cheie)
            if tip == 't2' and (str(f.get('fel') or '') == 'abertis' or _t2mi_biss_real(f)):
                activ = active is None or _curata_id(f.get('id')) in active
                t2mi = f.get('fel') == 't2mi'
                real = _purtator_real(f, p, pid, cheie, tp_reali, doar_scanat=not activ and not t2mi)
                if real is not None:
                    if t2mi:
                        k = (real['sid'], real['ns'], real['tsid'], real['onid'])
                        tp_reali['randuri'].setdefault(k, []).append((real['tip'], {pid}, True, False))
                    if activ or not t2mi:
                        rez.append(real)
                    continue
                if not activ:
                    continue
            ns = (p['orbital_position'] << 16) | ((p['frequency'] // 1000) & 0x7FFF) | ((p['polarisation'] & 1) << 15)
            tsid = _crc16('tp:' + cheie.rsplit(':', 1)[0]) or 1
            sid = (_crc16('sid:' + cheie) if tip == 't2' else _crc16('sid-eti:' + cheie)) or 1
            rez.append({'cheie': cheie, 'parametri': p, 'pid': pid, 'ns': ns, 'tsid': tsid, 'onid': ONID,
                        'sid': sid, 'nume': '%s %d' % (FURNIZORI[tip], pid), 'furnizor': FURNIZORI[tip],
                        'ref': '1:0:1:%X:%X:%X:%X:0:0:0:' % (sid, tsid, ONID, ns)})
    return rez


def purtator_pentru(lista, tp, feed, cale4=None, radacina_cam='/'):
    """Purtatorul feed-ului care porneste, acelasi pe care il scrie actualizeaza (la felul abertis: transponderul si
    tipul din lamedb-ul receptorului), ca releul sa ceara exact referinta din lamedb. radacina_cam ramane numai pentru
    cei care o dau inca (automatele altora nu mai schimba purtatorul, 0.7.7)."""
    p = tuner.parametri(tp)
    cheie = '%d:%d:%d:%d:%d' % (p['orbital_position'], p['frequency'] // 1000, p['polarisation'], p['is_id'],
                                int(feed.get('pid') or 0) & 0x1FFF)
    tip = 'dab' if feed.get('tip') == 'dab' else 't2'
    tp_reali = None
    if tip == 't2' and (str(feed.get('fel') or '') == 'abertis' or _t2mi_biss_real(feed)):
        tp_reali = tp_reali_din(_text_sau_gol(_citeste(cale4 or CALE4)))
    contexte = {'transpondere': [dict(tp, feeduri=[feed])]}
    if _t2mi_biss_real(feed):
        # Reserve siblings exactly as when saving, including inactive feeds.
        contexte = dict(lista, transpondere=list(lista.get('transpondere') or []) + contexte['transpondere'])
    for x in purtatori(contexte, tip=tip, tp_reali=tp_reali):
        if x['cheie'] == cheie:
            return x
    return None


def _fe_parti(p):
    """Partile comune ale parametrilor de satelit, fara T2-MI. -> (baza, s2, mis) ca siruri."""
    poz = p['orbital_position']
    poz = poz - 3600 if poz > 1800 else poz
    baza = '%d:%d:%d:%d:%d:%d:%d' % (p['frequency'], p['symbol_rate'], p['polarisation'], p['fec'], poz,
                                     p['inversion'], 0)
    are_mis = p['is_id'] >= 0 or p['pls_code'] > 0 or p['pls_mode'] not in (0, 1)
    sistem = 1 if (p['system'] == 1 or are_mis) else 0       # MIS/PLS exista doar in DVB-S2
    s2 = '%d:%d:%d:%d' % (sistem, p['modulation'], p['rolloff'], p['pilot']) if sistem == 1 else ''
    mis = ''
    if sistem == 1 and are_mis:
        mis = '%d:%d:%d' % (p['is_id'], p['pls_code'] & 0x3FFFF, p['pls_mode'] & 3)
    return baza, s2, mis


def bloc_transponder4(x):
    baza, s2, mis = _fe_parti(x['parametri'])
    linie = '\ts ' + baza + (':' + s2 if s2 else '') + (':' + mis if mis else '')
    return ['%08x:%04x:%04x' % (x['ns'], x['tsid'], x['onid']), linie, '/']


def _ca_biss(x):
    return ',C:%04x' % abertis.CAID_BISS if x.get('biss', True) else ''


def bloc_serviciu4(x):
    if x.get('real'):
        # PMT citit (f:01, numai fara SDT), PID-ul de date in c:18 (cDATAPID, pus in fluxul 8001 de
        # servicedvbrecord.cpp), CAID-ul BISS tinut minte la fluxurile BISS; tipul serviciului scanat
        return ['%04x:%08x:%04x:%04x:%d:0:0' % (x['sid'], x['ns'], x['tsid'], x['onid'], x.get('tip', TIP_DATE)),
                x['nume'], 'p:%s,c:18%04x%s,f:01' % (x.get('furnizor', FURNIZOR), x['pid'], _ca_biss(x))]
    return ['%04x:%08x:%04x:%04x:1:0:0' % (x['sid'], x['ns'], x['tsid'], x['onid']), x['nume'],
            'p:%s,c:00%04x,c:03%04x,f:04' % (x.get('furnizor', FURNIZOR), x['pid'], x['pid'])]


def linie_transponder5(x):
    baza, s2, mis = _fe_parti(x['parametri'])
    return 't:%08x:%04x:%04x,s:%s%s%s' % (x['ns'], x['tsid'], x['onid'], baza, (':' + s2) if s2 else '',
                                          (',MIS/PLS:' + mis) if mis else '')


def linie_serviciu5(x):
    if x.get('real'):
        return 's:%04x:%08x:%04x:%04x:%d:0:0,"%s",p:%s,c:18%04x%s,f:1' % (
            x['sid'], x['ns'], x['tsid'], x['onid'], x.get('tip', TIP_DATE), x['nume'], x.get('furnizor', FURNIZOR),
            x['pid'], _ca_biss(x))
    # c:TTPPPP: tipul pe 2 cifre, PID-ul pe 4 cifre hex (cu %x un PID sub 0x1000 iesea altfel decat il
    # scrie enigma2 si fisierul parea mereu schimbat)
    return 's:%04x:%08x:%04x:%04x:1:0:0,"%s",p:%s,c:00%04x,c:03%04x,f:4' % (
        x['sid'], x['ns'], x['tsid'], x['onid'], x['nume'], x.get('furnizor', FURNIZOR), x['pid'], x['pid'])


# ---------------------------------------------------------------- lamedb (4)
class Stricat(ValueError):
    pass


def desparte4(text):
    """-> (antet, transpondere[[3 randuri]], servicii[[3 randuri]], coada[randuri]). Ridica Stricat."""
    randuri = text.split('\n')
    if randuri and randuri[-1] == '':
        randuri.pop()
    if not randuri or randuri[0].strip() != 'eDVB services /4/':
        raise Stricat('antet necunoscut')
    i = 1
    if i >= len(randuri) or randuri[i] != 'transponders':
        raise Stricat('lipseste „transponders"')
    i += 1
    tp = []
    while i < len(randuri) and randuri[i] != 'end':
        if i + 2 >= len(randuri) or randuri[i + 2] != '/' or not randuri[i + 1].startswith('\t'):
            raise Stricat('bloc de transponder stricat la randul %d' % (i + 1))
        tp.append(randuri[i:i + 3])
        i += 3
    if i >= len(randuri):
        raise Stricat('lipseste „end" dupa transpondere')
    i += 1
    if i >= len(randuri) or randuri[i] != 'services':
        raise Stricat('lipseste „services"')
    i += 1
    sv = []
    while i < len(randuri) and randuri[i] != 'end':
        if i + 2 >= len(randuri):
            raise Stricat('bloc de serviciu taiat la randul %d' % (i + 1))
        if len(randuri[i].split(':')) < 6:
            raise Stricat('cheie de serviciu stricata la randul %d' % (i + 1))
        sv.append(randuri[i:i + 3])
        i += 3
    if i >= len(randuri):
        raise Stricat('lipseste „end" dupa servicii')
    return randuri[0], tp, sv, randuri[i + 1:]


def _cheie_sv(cheie):
    """(sid, ns, tsid, onid) dintr-o cheie de serviciu, oricare ar fi tipul si restul campurilor; None daca nu se
    intelege."""
    try:
        parti = cheie.split(':')
        return tuple(int(parti[k], 16) for k in range(4))
    except (ValueError, IndexError):
        return None


def _al_nostru_furnizor(rand_p, furnizori):
    return any(rand_p == 'p:%s' % f or rand_p.startswith('p:%s,' % f) for f in furnizori)


def _furnizorii(furnizor):
    return (furnizor, FURNIZOR_ABERTIS) if furnizor == FURNIZOR else (furnizor,)


def _cheie_tp_din_serviciu4(cheie):
    parti = cheie.split(':')
    return '%s:%s:%s' % (parti[1].lower(), parti[2].lower(), parti[3].lower())


def compune4(text, lista_purtatori, furnizor=FURNIZOR):
    antet, tp, sv, coada = desparte4(text)
    furnizori = _furnizorii(furnizor)
    lista_purtatori = [x for x in lista_purtatori if not x.get('strain')]
    # purtatorii adevarati (felul abertis) iau locul serviciului scanat cu aceeasi cheie (un serviciu de date fara
    # nume, „11222H SID 0xbd1”), oricare i-ar fi tipul; randurile altor automate de pe cheie raman (_rand_pastrat);
    # transponderul lor e al receptorului si ramane, sau se scrie daca lipseste
    reali = dict(((x['sid'], x['ns'], x['tsid'], x['onid']), x) for x in lista_purtatori if x.get('real'))

    def ramane(b):
        if _al_nostru_furnizor(b[2], furnizori):
            return False
        x = reali.get(_cheie_sv(b[0]))
        if x is None:
            return True
        if x.get('pastreaza'):
            return True
        # pe referinta noastra (acelasi tip) nu ramane nimic: enigma2 ar tine primul rand din fisier
        return _tip_cheie(b[0]) != x.get('tip', TIP_DATE) and _rand_pastrat(b[2], x['pid'])
    sv_straine = [b for b in sv if ramane(b)]
    folosite = set(_cheie_tp_din_serviciu4(b[0]) for b in sv_straine)
    tp_existente = set(b[0].lower() for b in tp)
    lista_purtatori = [x for x in lista_purtatori
                       if not (x.get('real') and bloc_transponder4(x)[0].lower() in tp_existente)] + \
        [dict(x, fara_tp=True) for x in lista_purtatori if x.get('real') and bloc_transponder4(x)[0].lower() in tp_existente]
    ale_noastre = set(bloc_transponder4(x)[0] for x in lista_purtatori if not x.get('real'))
    tp_pastrate = []
    for b in tp:
        k = b[0].lower()
        onid_nostru = k.endswith(':%04x' % ONID)
        if k in ale_noastre or (onid_nostru and k not in folosite):
            continue
        tp_pastrate.append(b)
    noi_tp, scrise_tp = [], set()
    for x in lista_purtatori:
        b = bloc_transponder4(x)
        if not x.get('fara_tp') and b[0] not in scrise_tp:
            scrise_tp.add(b[0])
            noi_tp.append(b)
    noi_sv = [bloc_serviciu4(x) for x in lista_purtatori]
    randuri = [antet, 'transponders']
    for b in tp_pastrate + noi_tp:
        randuri += b
    randuri += ['end', 'services']
    for b in sv_straine + noi_sv:
        randuri += b
    randuri += ['end'] + coada
    return '\n'.join(randuri) + '\n'


# ---------------------------------------------------------------- lamedb5
def compune5(text, lista_purtatori, furnizor=FURNIZOR):
    randuri = text.split('\n')
    if randuri and randuri[-1] == '':
        randuri.pop()
    if not randuri or not randuri[0].startswith('eDVB services /5/'):
        raise Stricat('antet lamedb5 necunoscut')
    furnizori = _furnizorii(furnizor)
    lista_purtatori = [x for x in lista_purtatori if not x.get('strain')]
    reali = dict(((x['sid'], x['ns'], x['tsid'], x['onid']), x) for x in lista_purtatori if x.get('real'))

    def al_nostru_s(r):
        """Randul s: e al nostru sau il inlocuieste un purtator adevarat (ca ramane() din compune4)."""
        if any((',p:%s,' % f) in r or r.endswith(',p:%s' % f) for f in furnizori):
            return True
        if not reali:
            return False
        parti = r[2:].split(',', 1)
        x = reali.get(_cheie_sv(parti[0]))
        if x is None:
            return False
        if x.get('pastreaza'):
            return False
        return _tip_cheie(parti[0]) == x.get('tip', TIP_DATE) or \
            not _rand_pastrat(parti[1] if len(parti) > 1 else '', x['pid'])
    pastrate_s, t_linii, altele = [], [], []
    for r in randuri[1:]:
        if r.startswith('s:'):
            if al_nostru_s(r):
                continue
            pastrate_s.append(r)
        elif r.startswith('t:'):
            t_linii.append(r)
        else:
            altele.append(r)
    folosite = set()
    for r in pastrate_s:
        parti = r[2:].split(',', 1)[0].split(':')
        if len(parti) >= 4:
            folosite.add('%s:%s:%s' % (parti[1].lower(), parti[2].lower(), parti[3].lower()))
    t_existente = set(r[2:].split(',', 1)[0].lower() for r in t_linii)
    # transponderul unui purtator adevarat e al receptorului: ramane; se scrie numai daca lipseste
    lista_t = [x for x in lista_purtatori if not (x.get('real') and
                                                  linie_transponder5(x).split(',', 1)[0][2:].lower() in t_existente)]
    ale_noastre = set(linie_transponder5(x).split(',', 1)[0][2:] for x in lista_t if not x.get('real'))
    t_pastrate = []
    for r in t_linii:
        k = r[2:].split(',', 1)[0].lower()
        if k in ale_noastre or (k.endswith(':%04x' % ONID) and k not in folosite):
            continue
        t_pastrate.append(r)
    # ordinea fisierului se pastreaza (comentariile raman unde le-a pus enigma2); ale noastre vin dupa ultima linie
    # de acelasi fel
    sterse_t = set(r for r in t_linii) - set(t_pastrate)
    noi_t, scrise_t = [], set()
    for x in lista_t:
        r = linie_transponder5(x)
        k = r.split(',', 1)[0]
        if k not in scrise_t:
            scrise_t.add(k)
            noi_t.append(r)
    noi_s = [linie_serviciu5(x) for x in lista_purtatori]
    rez = [randuri[0]]
    ultim_t = ultim_s = None
    for r in randuri[1:]:
        if r.startswith('s:') and al_nostru_s(r):
            continue
        if r.startswith('t:') and r in sterse_t:
            continue
        rez.append(r)
        if r.startswith('t:'):
            ultim_t = len(rez)
        elif r.startswith('s:'):
            ultim_s = len(rez)
    if ultim_s is None:
        ultim_s = len(rez)
    if ultim_t is None:
        # fara transpondere: inaintea primului serviciu (sau la sfarsit), dupa comentariul de transpondere daca e
        ultim_t = next((i for i, r in enumerate(rez) if r.startswith('s:')), len(rez))
        if ultim_t > 0 and rez[ultim_t - 1].startswith('#') and 'ervice' in rez[ultim_t - 1]:
            ultim_t -= 1
    rez[ultim_s:ultim_s] = noi_s
    rez[ultim_t:ultim_t] = noi_t
    return '\n'.join(rez) + '\n'


def _acelasi_continut5(vechi, nou):
    """Aceleasi linii, oricare ar fi ordinea (enigma2 isi scrie singur fisierul in ordinea lui)."""
    if vechi is None:
        return False
    return sorted(r for r in vechi.split('\n') if r) == sorted(r for r in nou.split('\n') if r)


def _acelasi_continut4(vechi, nou):
    """Acelasi antet, aceleasi blocuri de transpondere si servicii, aceeasi coada, oricare ar fi ordinea blocurilor."""
    if vechi is None:
        return False
    try:
        a, b = desparte4(vechi), desparte4(nou)
    except Stricat:
        return False
    return (a[0] == b[0] and a[3] == b[3] and sorted(map(tuple, a[1])) == sorted(map(tuple, b[1]))
            and sorted(map(tuple, a[2])) == sorted(map(tuple, b[2])))


# ---------------------------------------------------------------- scriere
_OCTETI_SUNT_TEXT = bytes is str     # Python 2.7: textul lamedb ramane octeti (nu exista 'surrogateescape')


def _din_octeti(date):
    if _OCTETI_SUNT_TEXT:
        return date
    return date.decode('utf-8', 'surrogateescape')


def _in_octeti(text):
    if isinstance(text, bytes):
        return text
    try:
        return text.encode('utf-8', 'surrogateescape')
    except LookupError:              # Python 2.7 cu un text unicode (nume din JSON)
        return text.encode('utf-8', 'replace')


def _citeste(cale):
    try:
        with open(cale, 'rb') as f:
            return _din_octeti(f.read())
    except (IOError, OSError):
        return None


def _citeste_transpondere(cale):
    """Numai partea de transpondere a lamedb, pana la "services": serviciile (~95% din fisier, 1,2 MB din 1,3 MB in lista
    din asistenta 213800) nu se mai decodeaza si nu se mai despart in randuri. transpondere_receptor ruleaza in firul
    interfetei la zap (pornire._t2mi_strain) dupa fiecare schimbare a fisierului. Fara "services" la inceput de rand:
    tot fisierul, ca inainte."""
    try:
        with open(cale, 'rb') as f:
            date = f.read()
    except (IOError, OSError):
        return None
    for capat in (b'\nservices\n', b'\nservices\r\n'):
        i = date.find(capat)
        if i >= 0:
            return _din_octeti(date[:i + 1])
    return _din_octeti(date)


def _fir_curent():
    try:
        import threading
        return threading.current_thread().ident or 0
    except Exception:
        return 0


def _scrie(cale, text_vechi, text_nou):
    date = _in_octeti(text_nou)
    if text_vechi is not None:
        copie = cale + '.hds-copie'
        with open(copie + '.tmp', 'wb') as f:
            f.write(_in_octeti(text_vechi))
        compat.inlocuieste(copie + '.tmp', copie)
    # nume pe proces si fir: doi scriitori (ex. scriptul de dezinstalare si enigma2) nu impart fisierul temporar
    tmp = '%s.hds-tmp.%d.%d' % (cale, os.getpid(), _fir_curent())
    try:
        with open(tmp, 'wb') as f:
            f.write(date)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        compat.inlocuieste(tmp, cale)
    except Exception:
        try:
            os.remove(tmp)        # disc plin sau alta eroare: nu lasam temporare in /etc/enigma2
        except OSError:
            pass
        raise


def _text_sau_gol(t):
    return t if isinstance(t, str) else ''


def actualizeaza(lista, cale4=None, cale5=None, reincarca=True, active=None, tip='t2', radacina_cam='/'):
    """Pune in lamedb (si lamedb5 daca exista) purtatorii feed-urilor active si ii scoate pe ai nostri care nu mai
    sunt necesari. -> {'schimbat', 'purtatori', 'eroare'}. Nu arunca. `active`: vezi purtatori(). Configurarea
    modulului de acces nu se atinge (abertis.py, punctul 2). Randurile altor automate nu se ating (_rand_pastrat).
    radacina_cam ramane numai pentru cei care o dau inca."""
    cale4 = cale4 or CALE4
    cale5 = cale5 or CALE5
    rez = {'schimbat': False, 'purtatori': 0, 'eroare': None}
    try:
        furnizor = FURNIZORI.get(tip, FURNIZOR)
        vechi4 = _citeste(cale4)
        p = purtatori(lista, active, tip if tip in FURNIZORI else 't2',
                      tp_reali_din(_text_sau_gol(vechi4)) if tip == 't2' else None)
        rez['purtatori'] = len([x for x in p if not x.get('strain')])
        baza4 = vechi4 if vechi4 is not None else 'eDVB services /4/\ntransponders\nend\nservices\nend\n'
        try:
            nou4 = compune4(baza4, p, furnizor)
        except Stricat as e:
            rez['eroare'] = 'lamedb nu se intelege (%s), nu il ating' % e
            jurnal.noteaza('lamedb', rez['eroare'])
            return rez
        if nou4 != vechi4 and not _acelasi_continut4(vechi4, nou4):
            _scrie(cale4, vechi4, nou4)
            rez['schimbat'] = True
        vechi5 = _citeste(cale5)
        if vechi5 is not None:
            try:
                nou5 = compune5(vechi5, p, furnizor)
                if nou5 != vechi5 and not _acelasi_continut5(vechi5, nou5):
                    _scrie(cale5, vechi5, nou5)
                    rez['schimbat'] = True
            except Stricat as e:
                jurnal.noteaza('lamedb', 'lamedb5 nu se intelege (%s), nu il ating' % e)
        if rez['schimbat']:
            _de_scos.update(refs_ale_noastre4(vechi4 or '', furnizor) |
                            set(x['ref'] for x in p if not x.get('strain')))
            # si serviciile scanate inlocuite de purtatorii adevarati pe cheia lor (alt tip decat al nostru): altfel raman
            # in memorie, enigma2 le scrie inapoi in lamedb la oprire si fisierul se rescrie la fiecare pornire
            if nou4 != vechi4 and vechi4 is not None:
                _de_scos.update(refs_ale_noastre4(vechi4, toate=True) - refs_ale_noastre4(nou4, toate=True))
            jurnal.noteaza('lamedb', '%d purtatori %s scrisi' % (len(p), furnizor))
            if reincarca:
                reincarca_servicii()
    except Exception:
        jurnal.eroare('lamedb', 'actualizare')
        rez['eroare'] = 'eroare interna'
    return rez


# Serviciile noastre (purtatorii scrisi sau scosi la ultima actualizare) care se scot din memoria enigma2 inainte de
# reincarcare: eDVBDB::addService (lib/dvb/db.cpp) nu inlocuieste un serviciu deja incarcat, deci linia noua din lamedb
# (de exemplu PCR-ul din cache) n-ar ajunge in memorie, iar la oprire enigma2 scrie lamedb din memorie peste ea.
# Actualizarea poate fi in fundal, reincarcarea in firul principal: multimea se goleste numai in reincarca_servicii.
_de_scos = set()


_PRINSE = {}


def transpondere_receptor(cale4=None):
    """Transponderele de satelit din lista de canale a receptorului (lamedb, sectiunea „transponders”), fara ale
    noastre (ONID 4844): set de (pozitie 0..3599, frecventa kHz, polarizare 0..3, is_id sau -1). Lista se citeste din
    nou numai cand fisierul s-a schimbat (marime, data), deci o refacere de buchet in firul principal nu o parcurge
    de fiecare data. Fisier lipsa sau stricat: set gol."""
    cale4 = cale4 or CALE4
    try:
        st = os.stat(cale4)
    except OSError:
        return set()
    semn = (cale4, st.st_size, getattr(st, 'st_mtime', 0))
    if _PRINSE.get('semn') == semn:
        return _PRINSE['tp']
    rez = set()
    t2mi = {}
    text = _citeste_transpondere(cale4)
    if text:
        randuri = text.replace('\r', '').split('\n')
        if randuri and randuri[0].strip() == 'eDVB services /4/' and len(randuri) > 1 and randuri[1] == 'transponders':
            i = 2
            while i + 1 < len(randuri) and randuri[i] != 'end':
                cheie, linie = randuri[i], randuri[i + 1]
                i += 3
                parti_cheie = cheie.split(':')
                if not linie.startswith('\ts ') or len(parti_cheie) < 3:
                    continue
                try:
                    if int(parti_cheie[2], 16) == ONID:
                        continue
                    c = linie[3:].split(':')
                    poz = int(c[4])
                    is_id = int(c[11]) if len(c) > 11 else -1
                    rez.add((poz + 3600 if poz < 0 else poz, int(c[0]), int(c[2]), is_id))
                    # T2-MI scris de alte imagini (dupa pls_mode: t2mi_plp_id:t2mi_pid, ca in hdsmultistream.h)
                    plp = int(c[14]) if len(c) > 14 else -1
                    if 0 <= plp <= 255:
                        pid_t2 = int(c[15]) if len(c) > 15 else 4096
                        t2mi[tuple(int(x, 16) for x in parti_cheie[:3])] = {
                            'poz': poz + 3600 if poz < 0 else poz, 'khz': int(c[0]), 'pol': int(c[2]), 'is_id': is_id,
                            'plp': plp, 'pid': pid_t2 if 0 < pid_t2 < 0x1FFF else 4096,
                            # restul acordului (straine.feed_din_t2mi face din ele un feed cand lista noastra nu-l are):
                            # sr:pol:fec:pozitie:inversare:steaguri:sistem:modulatie:rolloff:pilot:is_id:pls_code:pls_mode
                            'sr': int(c[1]), 'fec': int(c[3]) if len(c) > 3 else 0,
                            'sistem': int(c[7]) if len(c) > 7 else 0, 'modulatie': int(c[8]) if len(c) > 8 else 0,
                            'rolloff': int(c[9]) if len(c) > 9 else 0, 'pls_cod': int(c[12]) if len(c) > 12 else 0,
                            'pls_mod': int(c[13]) if len(c) > 13 else 0}
                except (ValueError, IndexError):
                    continue
    _PRINSE['semn'], _PRINSE['tp'], _PRINSE['t2mi'] = semn, rez, t2mi
    return rez


def transpondere_t2mi(cale4=None, doar_din_memorie=False):
    """Transponderele cu T2-MI scrise de listele altor imagini (campurile t2mi_plp_id:t2mi_pid din lamedb, pe care
    nucleul nostru nu le foloseste): {(ns, tsid, onid): {poz, khz, pol, is_id, plp, pid}}. Acelasi citit si aceeasi
    memorie ca transpondere_receptor (lamedb se reciteste numai cand s-a schimbat). doar_din_memorie: fara nicio
    citire de disc (din alt fir decat cel principal); {} daca nu s-a citit inca."""
    if not doar_din_memorie:
        transpondere_receptor(cale4)
    return _PRINSE.get('t2mi') or {}


def refs_ale_noastre4(text, furnizor=FURNIZOR, toate=False):
    """Referintele serviciilor noastre (dupa furnizor) dintr-un lamedb (4); toate=True: ale tuturor serviciilor. Un
    fisier care nu se intelege: multime goala."""
    try:
        _antet, _tp, sv, _coada = desparte4(text)
    except Stricat:
        return set()
    rez = set()
    furnizori = _furnizorii(furnizor)
    for b in sv:
        if not toate and not _al_nostru_furnizor(b[2], furnizori):
            continue
        parti = b[0].split(':')
        try:
            sid, ns, tsid, onid = (int(parti[k], 16) for k in range(4))
            tip = int(parti[4])
        except (ValueError, IndexError):
            continue
        rez.add('1:0:%X:%X:%X:%X:%X:0:0:0:' % (tip, sid, tsid, onid, ns))
    return rez


def reincarca_servicii():
    """enigma2 reciteste lamedb. Doar din firul principal (scrierea de mai sus poate fi in fundal). Purtatorii nostri se
    scot intai din memorie (_de_scos), ca reincarcarea sa-i ia asa cum sunt acum in fisier."""
    try:
        from enigma import eDVBDB, eServiceReference
        db = eDVBDB.getInstance()
        scoate = getattr(db, 'removeService', None)      # lipseste in simulatorul probelor
        while _de_scos:
            ref = _de_scos.pop()
            if scoate is None:
                continue
            try:
                scoate(eServiceReference(ref))
            except Exception:
                jurnal.eroare('lamedb', 'scoaterea din memorie a %s' % ref)
        db.reloadServicelist()
    except Exception:
        jurnal.eroare('lamedb', 'reloadServicelist')

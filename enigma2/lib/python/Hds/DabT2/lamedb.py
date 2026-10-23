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

Editarea e sigura: fisierul se desparte in blocuri; ale noastre se recunosc dupa furnizorul „HDSatelit T2-MI" (servicii)
si dupa ONID-ul 4844 fara alte servicii pe el (transpondere). Tot restul ramane octet cu octet. Un fisier care nu
se intelege nu se atinge. Daca rezultatul e identic, nu se scrie nimic. Inainte de scriere se pastreaza o copie
(lamedb.hds-copie), apoi fisier temporar + os.replace.
"""
import os

from . import compat, jurnal, tuner

FURNIZOR = 'HDSatelit T2-MI'
# Si HdsDab scrie purtatori, pentru ETI in TS (ts2na, ts2na12, tsniv2ni) prin 8001. Fiecare plugin isi
# recunoaste doar serviciile lui dupa furnizor, deci unul nu le sterge pe ale celuilalt; un transponder ONID 4844
# ramane cat il foloseste oricare dintre ele.
FURNIZORI = {'t2': FURNIZOR, 'dab': 'HDSatelit ETI'}
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


def purtatori(lista, active=None, tip='t2'):
    """Lista unita de feed-uri -> purtatorii necesari (unul pe transponder + PID T2-MI), in ordine stabila.

    active: multimea id-urilor de feed ACTIVE (invatate sau pornite de utilizator); doar pentru ele se scrie un
    purtator (lamedb-ul utilizatorului nu primeste cate o intrare pentru fiecare feed din
    lista). None = toate feed-urile T2 din lista (doar pentru probe si unelte)."""
    rez, vazute = [], set()
    for tp in lista.get('transpondere', []):
        feeduri = [f for f in tp.get('feeduri', []) if _al_tipului(f, tip) and f.get('pid') is not None
                   and (active is None or _curata_id(f.get('id')) in active)]
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
            ns = (p['orbital_position'] << 16) | ((p['frequency'] // 1000) & 0x7FFF) | ((p['polarisation'] & 1) << 15)
            tsid = _crc16('tp:' + cheie.rsplit(':', 1)[0]) or 1
            sid = (_crc16('sid:' + cheie) if tip == 't2' else _crc16('sid-eti:' + cheie)) or 1
            rez.append({'cheie': cheie, 'parametri': p, 'pid': pid, 'ns': ns, 'tsid': tsid, 'onid': ONID,
                        'sid': sid, 'nume': '%s %d' % (FURNIZORI[tip], pid), 'furnizor': FURNIZORI[tip],
                        'ref': '1:0:1:%X:%X:%X:%X:0:0:0:' % (sid, tsid, ONID, ns)})
    return rez


def purtator_pentru(lista, tp, feed):
    p = tuner.parametri(tp)
    cheie = '%d:%d:%d:%d:%d' % (p['orbital_position'], p['frequency'] // 1000, p['polarisation'], p['is_id'],
                                int(feed.get('pid') or 0) & 0x1FFF)
    tip = 'dab' if feed.get('tip') == 'dab' else 't2'
    for x in purtatori({'transpondere': [dict(tp, feeduri=[feed])]}, tip=tip):
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


def bloc_serviciu4(x):
    return ['%04x:%08x:%04x:%04x:1:0:0' % (x['sid'], x['ns'], x['tsid'], x['onid']), x['nume'],
            'p:%s,c:00%04x,c:03%04x,f:04' % (x.get('furnizor', FURNIZOR), x['pid'], x['pid'])]


def linie_transponder5(x):
    baza, s2, mis = _fe_parti(x['parametri'])
    return 't:%08x:%04x:%04x,s:%s%s%s' % (x['ns'], x['tsid'], x['onid'], baza, (':' + s2) if s2 else '',
                                          (',MIS/PLS:' + mis) if mis else '')


def linie_serviciu5(x):
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


def _cheie_tp_din_serviciu4(cheie):
    parti = cheie.split(':')
    return '%s:%s:%s' % (parti[1].lower(), parti[2].lower(), parti[3].lower())


def compune4(text, lista_purtatori, furnizor=FURNIZOR):
    antet, tp, sv, coada = desparte4(text)
    sv_straine = [b for b in sv if not (b[2] == 'p:%s' % furnizor or b[2].startswith('p:%s,' % furnizor))]
    folosite = set(_cheie_tp_din_serviciu4(b[0]) for b in sv_straine)
    ale_noastre = set(bloc_transponder4(x)[0] for x in lista_purtatori)
    tp_pastrate = []
    for b in tp:
        k = b[0].lower()
        onid_nostru = k.endswith(':%04x' % ONID)
        if k in ale_noastre or (onid_nostru and k not in folosite):
            continue
        tp_pastrate.append(b)
    noi_tp = [bloc_transponder4(x) for x in lista_purtatori]
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
    pastrate_s, t_linii, altele = [], [], []
    for r in randuri[1:]:
        if r.startswith('s:'):
            if (',p:%s,' % furnizor) in r or r.endswith(',p:%s' % furnizor):
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
    ale_noastre = set(linie_transponder5(x).split(',', 1)[0][2:] for x in lista_purtatori)
    t_pastrate = []
    for r in t_linii:
        k = r[2:].split(',', 1)[0].lower()
        if k in ale_noastre or (k.endswith(':%04x' % ONID) and k not in folosite):
            continue
        t_pastrate.append(r)
    # ordinea fisierului se pastreaza (comentariile raman unde le-a pus enigma2); ale noastre vin dupa ultima linie
    # de acelasi fel
    sterse_t = set(r for r in t_linii) - set(t_pastrate)
    noi_t = [linie_transponder5(x) for x in lista_purtatori]
    noi_s = [linie_serviciu5(x) for x in lista_purtatori]
    rez = [randuri[0]]
    ultim_t = ultim_s = None
    for r in randuri[1:]:
        if r.startswith('s:') and ((',p:%s,' % furnizor) in r or r.endswith(',p:%s' % furnizor)):
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


def actualizeaza(lista, cale4=None, cale5=None, reincarca=True, active=None, tip='t2'):
    """Pune in lamedb (si lamedb5 daca exista) purtatorii feed-urilor active si ii scoate pe ai nostri care nu mai
    sunt necesari. -> {'schimbat', 'purtatori', 'eroare'}. Nu arunca. `active`: vezi purtatori()."""
    cale4 = cale4 or CALE4
    cale5 = cale5 or CALE5
    rez = {'schimbat': False, 'purtatori': 0, 'eroare': None}
    try:
        furnizor = FURNIZORI.get(tip, FURNIZOR)
        p = purtatori(lista, active, tip if tip in FURNIZORI else 't2')
        rez['purtatori'] = len(p)
        vechi4 = _citeste(cale4)
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
            _de_scos.update(refs_ale_noastre4(vechi4 or '', furnizor) | set(x['ref'] for x in p))
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
    text = _citeste(cale4)
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
                except (ValueError, IndexError):
                    continue
    _PRINSE['semn'], _PRINSE['tp'] = semn, rez
    return rez


def refs_ale_noastre4(text, furnizor=FURNIZOR):
    """Referintele serviciilor noastre (dupa furnizor) dintr-un lamedb (4). Un fisier care nu se intelege: multime goala."""
    try:
        _antet, _tp, sv, _coada = desparte4(text)
    except Stricat:
        return set()
    rez = set()
    for b in sv:
        if not (b[2] == 'p:%s' % furnizor or b[2].startswith('p:%s,' % furnizor)):
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Buchetele „DAB+ din satelit" (radio) si „DVB-T2 din satelit" (TV). Facut de hdsatelit.com.

Liniile:
  DAB+   imagine: #SERVICE 1:0:2:SID:0:0:0:0:0:0:http%3a//127.0.0.1%3a8898/dab/<feed>/<SID zecimal>.ts:<nume>
         alte imagini: #SERVICE 4097:0:2:SID:0:0:0:0:0:0:http%3a//127.0.0.1%3a8898/dab/<feed>/<SID zecimal>:<nume>
         (8888 pana la 0.1.8; 4097 si in imagine pana la 0.2.0)
  DVB-T2 #SERVICE 1:0:<stype>:SID:TSID:ONID:NS:0:0:0:http%3a//127.0.0.1%3a8889/t2/<feed>/<plp>:<nume>

Forma sunetului DAB (profil.sunet_ts, pus de imagine.py): in imagine releul da „<SID>.ts”, un TS cu un singur program
(PAT/PMT, AAC-LATM cu stream_type 0x11 sau MP2 cu 0x03), redat de tipul 1 prin eHdsFluxHttp si decodorul placii.
4097 (servicemp3) nu poate suna in imagine: gstreamer nu are acolo tsdemux si nici decodor AAC, iar dvbaudiosink
refuza LOAS/LATM. Pluginul pentru alte imagini ramane pe 4097 cu LOAS. ref_curenta aduce orice referinta a unui post
la forma de acum (portul; in imagine si tipul 4097 -> 1 cu „.ts”). Invers nu se rescrie nimic: tipul 1 cu „.ts” se
reda in imagine oricare ar fi forma aleasa, deci o intoarcere a formei nu lasa referinte nefolositoare.

De ce aceste tipuri (citit in sursele enigma2):
  - tipul 1 cu cale http:// -> eDVBServicePlay cu m_is_stream. In imagine createTsSource da eHdsFluxHttp
    (lib/service/hdsfluxhttp.cpp: numai 127.0.0.1, conexiunea o face firul care citeste, cel de impingere spre dvr);
    pe alte imagini, sursa http a bazei lor. Serviciul nu cere tuner propriu (tunerul il tine sesiunea 8001 a
    releului). Demultiplexarea si decodarea sunt cele hardware, ca la un canal de satelit: teletext, subtitrari, piste
    audio, EPG din flux. Programul se alege dupa SID-ul din referinta, deci SID-ul trebuie sa fie cel din PAT-ul
    fluxului scos (niciodata 0: _servicii_curate sare peste el).
  - 4097 = servicemp3 (gstreamer, souphttpsrc cu timeout 60 s), numai in pluginul pentru alte imagini: primeste
    audio fara TS (LOAS pentru DAB+, MP2 pentru DAB). Campul 10 (0) = fara buffer.
  - 5001/5002 (gstplayer / exteplayer3) vin din pluginul ServiceApp, care nu e in enigma2 de baza; nu ne bazam
    pe el.

Referintele sunt stabile: aceleasi feed + SID dau exact aceeasi linie, deci preferintele utilizatorului legate
de referinta (pista audio, favorite, ordinea) raman la refacere. Ordinea existenta din buchet se pastreaza;
intrarile noi se pun dupa ultima intrare a aceluiasi feed; liniile adaugate de utilizator raman neatinse; un nume
schimbat de utilizator (#DESCRIPTION diferit de numele nostru) ramane.

Scrierea e atomica (fisier temporar in acelasi director, fsync, os.replace). Daca nimic nu s-a schimbat, nu se
scrie nimic si nu se reincarca nimic. Nu se atinge lamedb: serviciile cu URL nu au nevoie de el, deci ajunge
eDVBDB.reloadBouquets(), fara reloadServicelist.
"""
import json
import os
import threading
import time

from . import compat, jurnal
from . import profil as _profil

GAZDA = '127.0.0.1'
DIRECTOR_ENIGMA2 = '/etc/enigma2'
TIP_MARCAJ = 0x48440000       # „HD" in hex: marcajele noastre au al treilea camp 4844xxxx
NS_T2 = 0xEEEE0000            # spatiul de nume terestru, cu octetii de jos din feed


def _crc16(text):
    c = 0xFFFF
    for b in bytearray(text.encode('utf-8')):       # bytearray: intregi si pe Python 2.7 (octetii str dau caractere)
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def _text(v):
    """Nume pentru buchet ca text unicode si pe 2.7 (buchetul se citeste ca unicode si se scrie UTF-8 la sfarsit;
    octeti UTF-8 amestecati cu unicode dau UnicodeDecodeError). Fara str(u'...'), care cade pe litere ne-ASCII."""
    if isinstance(v, bytes):
        return v.decode('utf-8', 'replace')
    if compat.e_text(v):
        return v
    return '%s' % (v if v is not None else '')


def _sir_ref(ref):
    """Referinta (sir sau eServiceReference) ca sir nativ; pe 2.7 un unicode cu nume ne-ASCII devine octeti UTF-8."""
    return compat.text_nativ(ref) if compat.e_text(ref) else str(ref)


def _curata_nume(nume):
    nume = ' '.join(_text(nume or '').replace(':', ' ').split())
    return nume[:80] or 'fara nume'


def _curata_id(feed_id):
    return ''.join(ch for ch in str(feed_id) if ch.isalnum() or ch in '_-.')[:64]


def _int(v, implicit=0):
    try:
        if compat.e_text(v) and v.lower().startswith('0x'):     # si unicode din JSON pe 2.7
            return int(v, 16)
        return int(v)
    except (TypeError, ValueError):
        return implicit


def url_codat(profil, cale):
    return ('http://%s:%d%s' % (GAZDA, profil.port, cale)).replace(':', '%3a')


FORMA_TS = 'ts'          # TS cu un program, tipul 1 (imaginea)
FORMA_LOAS = 'loas'      # LOAS / MP2 brut, tipul 4097 (pluginul pentru alte imagini)
TIP_FORMA = {FORMA_TS: '1', FORMA_LOAS: '4097'}
SUFIX_TS = '.ts'


def forma_dab(profil):
    """Forma in care se cere sunetul unui post DAB: FORMA_TS in imagine (profil.sunet_ts), altfel FORMA_LOAS."""
    return FORMA_TS if getattr(profil, 'sunet_ts', False) else FORMA_LOAS


def ref_dab(profil, feed_id, sid):
    sid = _int(sid)
    cale = '%s%s/%d' % (profil.prefix_url, _curata_id(feed_id), sid)
    forma = forma_dab(profil)
    if forma == FORMA_TS:
        cale += SUFIX_TS
    return '%s:0:2:%X:0:0:0:0:0:0:%s' % (TIP_FORMA[forma], sid, url_codat(profil, cale))


def ref_t2(profil, feed, serviciu):
    sid = _int(serviciu.get('sid'))
    tsid = _int(serviciu.get('tsid'))
    onid = _int(serviciu.get('onid'))
    stype = _int(serviciu.get('tip'), 1) or 1
    fid = _curata_id(feed.get('id'))
    ns = NS_T2 | _crc16(fid)
    cale = '%s%s/%d' % (profil.prefix_url, fid, _int(feed.get('plp'), 0))
    return '1:0:%X:%X:%X:%X:%X:0:0:0:%s' % (stype, sid, tsid, onid, ns, url_codat(profil, cale))


def ref_marcaj(feed_id):
    return '1:64:%X:0:0:0:0:0:0:0::' % (TIP_MARCAJ | _crc16(_curata_id(feed_id)))


# numele marcajului fiecarui ansamblu (multiplex) din buchet: „MUX DAB+: DR Deutschland”, „MUX DVB-T2: Zeonbud mux 1”.
# Nu se traduce: e scris in fisierul buchetului, iar „MUX”, „DAB+” si „DVB-T2” sunt nume tehnice, aceleasi in orice limba
PREFIX_MARCAJ = {'dab': u'MUX DAB+: ', 't2': u'MUX DVB-T2: '}


def nume_marcaj(profil, nume_feed):
    """Numele marcajului unui ansamblu: prefixul felului si numele lui (fara prefix dublu: un nume care il are deja,
    citit dintr-un buchet, ramane la fel; _curata_nume scoate „:” din nume, deci prefixul se pune dupa)."""
    prefix = PREFIX_MARCAJ[profil.tip]
    text = _text(nume_feed or '').strip()
    if text.startswith(prefix):
        text = text[len(prefix):]
    return prefix + _curata_nume(text)


def nume_ansamblu(text_marcaj):
    """Numele ansamblului dintr-un marcaj al nostru (fara „MUX DAB+: ” / „MUX DVB-T2: ”); altfel textul intreg."""
    text = _text(text_marcaj or '').strip()
    for prefix in PREFIX_MARCAJ.values():
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _porturi(profil):
    """Portul curent al profilului si porturile vechi (referintele scrise de versiuni mai vechi in buchet)."""
    f = getattr(profil, 'porturi_ref', None)
    return f() if f else (profil.port,)


def _port_in(s, porturi, prefix):
    """Primul port din `porturi` cu care sirul contine 127.0.0.1:<port><prefix> (codat %3a sau nu), altfel None."""
    for port in porturi:
        if ('%s%%3a%d%s' % (GAZDA, port, prefix)) in s or ('%s:%d%s' % (GAZDA, port, prefix)) in s:
            return port
    return None


def al_nostru(profil, ref):
    """True daca referinta (sir sau eServiceReference.toString()) e un serviciu al acestui plugin."""
    if not ref:
        return False
    return _port_in(_sir_ref(ref), _porturi(profil), profil.prefix_url) is not None


def al_hds(ref):
    """True daca referinta e a oricarui plugin hdsatelit (DAB sau T2, cu porturile din profil.py), nu doar a unuia."""
    s = _sir_ref(ref or '').replace('%3A', '%3a')
    return any(_port_in(s, _porturi(p), p.prefix_url) is not None for p in (_profil.DAB, _profil.T2))


def cheie_ref(ref):
    """Referinta fara nume (primele 11 campuri), ca sa se compare doua referinte ale aceluiasi serviciu."""
    return ':'.join(_sir_ref(ref or '').replace('%3A', '%3a').split(':')[:11])


# schemele adreselor de flux care pot ajunge decodate in campul caii al unei referinte
SCHEME_FLUX = ('http', 'https', 'rtsp', 'rtmp', 'rtp', 'udp')


def repara_cale_decodata(ref):
    """O referinta cu adresa decodata o data in plus, de pilda un sRef cu „%3a” pus intr-o adresa web fara sa fie scris
    „%253a” (serverul web il primeste cu „:”): „...:0:0:0:http://127.0.0.1:8889/t2/f/0:Nume”. Citita asa, enigma2 ia
    calea „http” si numele „//127.0.0.1:8889/t2/f/0:Nume”, iar toString() o da ca „...:http://127.0.0.1%3a8889/t2/f/
    0%3aNume”; redarea cade, fiindca sursa e „http”. -> referinta cu calea codata ca la toString() (fiecare „:” din
    adresa scris „%3a”) si numele dupa ea, sau None daca referinta nu are aceasta forma. Adresa se termina la primul
    „:” de dupa gazda si port (un nume dat de enigma2 nu are „:” in el, iar caile noastre nu au)."""
    parti = _sir_ref(ref or '').split(':')
    if len(parti) < 12 or parti[10].lower() not in SCHEME_FLUX:
        return None
    rest = ':'.join(parti[11:]).replace('%3A', '%3a').replace('%3a', ':')
    if not rest.startswith('//'):
        return None
    gazda_sfarsit = len(rest)
    for ch in '/:':
        i = rest.find(ch, 2)
        if i >= 0:
            gazda_sfarsit = min(gazda_sfarsit, i)
    j = gazda_sfarsit
    if rest[j:j + 1] == ':':
        k = j + 1
        while k < len(rest) and rest[k].isdigit():
            k += 1
        if k > j + 1:
            j = k                               # portul face parte din adresa
    sfarsit = rest.find(':', j)
    adresa = rest if sfarsit < 0 else rest[:sfarsit]
    nume = '' if sfarsit < 0 else rest[sfarsit + 1:]
    cale = (parti[10] + ':' + adresa).replace(':', '%3a')
    return ':'.join(parti[:10]) + ':' + cale + (':' + nume if nume else '')


def desparte_ref(profil, ref):
    """-> (feed_id, al_doilea) din URL: al doilea e SID-ul (dab) sau PLP-ul (t2). None daca nu e al nostru."""
    if not al_nostru(profil, ref):
        return None
    s = _sir_ref(ref).replace('%3a', ':').replace('%3A', ':')
    port = _port_in(s, _porturi(profil), profil.prefix_url)
    if port is None:
        return None
    marker = '%s:%d%s' % (GAZDA, port, profil.prefix_url)
    rest = s.split(marker, 1)[1]
    bucati = rest.split(':', 1)[0].split('/')
    if len(bucati) < 2:
        return None
    # „<SID>.ts” (sunetul DAB in TS, redat prin placa) e acelasi post ca „<SID>”
    return bucati[0], _int(bucati[1].split('.', 1)[0], -1)


def _url_cu_portul_curent(profil, url):
    """Campul URL al unei referinte (http%3a//127.0.0.1%3a<port><prefix>..., cu %3a sau %3A) scris cu un port vechi
    al profilului -> acelasi URL cu portul curent; restul (calea, ce urmeaza dupa ea) ramane. Altfel None.
    Numai forma scrisa de plugin (127.0.0.1, url_codat): localhost sau adresa receptorului pe acelasi port nu sunt
    socotite ale noastre (pot fi un serviciu strain, de pilda un modul de acces pe 8888), deci nu se rescriu."""
    mic = url.replace('%3A', '%3a')
    for port in _porturi(profil)[1:]:
        vechi = 'http%%3a//%s%%3a%d%s' % (GAZDA, port, profil.prefix_url)
        if mic.startswith(vechi):
            return 'http%%3a//%s%%3a%d%s' % (GAZDA, profil.port, profil.prefix_url) + url[len(vechi):]
    return None


def _forma_dupa_cale(profil, parti):
    """In forma TS (imaginea): campurile unui post DAB al profilului scris pentru 4097 (portul deja cel curent) trec
    pe tipul 1 cu „<SID>.ts”. Numai URL-ul http%3a//127.0.0.1%3a<port>/dab/<feed>/<SID>, fara nimic dupa SID. Invers
    nu se rescrie nimic: tipul 1 cu „.ts” se reda oriunde exista o sursa TS prin http (imaginea, alte imagini),
    deci in forma LOAS o referinta TS ramane cum e. -> True daca s-a schimbat ceva."""
    if profil.tip != 'dab' or forma_dab(profil) != FORMA_TS or parti[0] not in ('1', '4097'):
        return False
    url = parti[10]
    inceput = 'http%%3a//%s%%3a%d%s' % (GAZDA, profil.port, profil.prefix_url)
    if not url.replace('%3A', '%3a').startswith(inceput):
        return False
    bucati = url[len(inceput):].split('/')
    if len(bucati) != 2 or not bucati[0]:
        return False
    sid = bucati[1][:-len(SUFIX_TS)] if bucati[1].endswith(SUFIX_TS) else bucati[1]
    if not sid.isdigit():
        return False
    tip = TIP_FORMA[FORMA_TS]
    capat = sid + SUFIX_TS
    if parti[0] == tip and bucati[1] == capat:
        return False
    parti[0] = tip
    parti[10] = '%s%s/%s' % (inceput, bucati[0], capat)
    return True


def _parti_curente(profil, parti):
    """Campurile (lista de cel putin 11 siruri) ale unui post al profilului aduse la forma de acum: portul curent in
    locul unui port vechi si, la DAB, tipul si capatul URL-ului dupa forma sunetului. -> True daca s-a schimbat ceva.
    Se uita numai la primul camp si la campul URL (al 11-lea), deci o adresa straina, alt port sau alta cale nu se
    ating."""
    schimbat = False
    nou = _url_cu_portul_curent(profil, parti[10])
    if nou is not None:
        parti[10] = nou
        schimbat = True
    if _forma_dupa_cale(profil, parti):
        schimbat = True
    return schimbat


def ref_curenta(profil, ref):
    """Referinta unui post al profilului scrisa cu un port vechi (profil.porturi_vechi) sau, in imagine, un post DAB
    scris pentru 4097 -> acelasi post in forma de acum; campurile din mijloc, SID-ul, feed-ul si numele raman. None
    daca nu e a profilului sau e deja in forma de acum."""
    parti = _sir_ref(ref or '').split(':')
    if len(parti) < 11:
        return None
    if not _parti_curente(profil, parti):
        return None
    return ':'.join(parti)


# numele de dinainte de forma sunetului (0.1.10 - 0.2.0): numai portul
ref_cu_portul_curent = ref_curenta


def are_referinte_de_rescris(profil):
    """Profilul poate avea in buchete referinte in alta forma decat cea de acum: porturi vechi, sau posturi DAB scrise
    pentru 4097 cand forma de acum e TS (imaginea)."""
    return bool(tuple(getattr(profil, 'porturi_vechi', ()))) or (profil.tip == 'dab' and forma_dab(profil) == FORMA_TS)


def rescrie_referinte_vechi(profil, director=None):
    """In buchetele utilizatorului (userbouquet.*.tv / .radio din director) referintele posturilor profilului scrise
    cu un port vechi primesc portul curent, iar la DAB tipul si capatul URL-ului dupa forma sunetului de acum
    (ref_curenta). Se schimba numai primul camp si campul URL al acelor randuri #SERVICE; restul fisierului
    (#DESCRIPTION, ordinea, randurile straine, alte adrese http, sfarsiturile de rand, numele in orice codare) ramane
    octet cu octet. Scriere atomica, numai pentru fisierele schimbate. Blocant: din fir, sub zavorul scrierilor.
    Un dosar care nu se poate lista, sau un buchet care nu se poate citi ori scrie, arunca eroarea (IOError /
    OSError) dupa ce celelalte buchete au trecut; apelantul nu pune atunci semnul trecerii, deci rescrierea se reia la
    pornirea urmatoare. -> numele fisierelor rescrise."""
    if not are_referinte_de_rescris(profil):
        return []
    director = director or DIRECTOR_ENIGMA2
    cauta = profil.prefix_url.encode('ascii')
    nume = sorted(os.listdir(director))
    rescrise = []
    cazute = []
    for n in nume:
        if not n.startswith('userbouquet.') or not n.endswith(('.tv', '.radio')):
            continue
        cale = os.path.join(director, n)
        try:
            with open(cale, 'rb') as f:
                date = f.read()
        except (IOError, OSError) as e:
            cazute.append((n, e))
            continue
        if cauta not in date:
            continue
        linii = date.split(b'\n')
        schimbat = False
        for i, linie in enumerate(linii):
            # „#SERVICE: ” (editoare vechi) e citita de enigma2 ca „#SERVICE ” (lib/dvb/db.cpp); prefixul ramane
            prefix = b'#SERVICE: ' if linie.startswith(b'#SERVICE: ') else b'#SERVICE '
            if not linie.startswith(prefix) or cauta not in linie:
                continue
            parti = linie[len(prefix):].split(b':')
            if len(parti) < 11:
                continue
            text = [p.decode('latin-1') for p in parti[:11]]
            if not _parti_curente(profil, text):
                continue
            parti[:11] = [p.encode('latin-1') for p in text]
            linii[i] = prefix + b':'.join(parti)
            schimbat = True
        if schimbat:
            try:
                # un buchet care e legatura simbolica (spre un disc) ramane legatura: se scrie tinta ei
                scrie_atomic(os.path.realpath(cale), b'\n'.join(linii))
            except (IOError, OSError) as e:
                cazute.append((n, e))
                continue
            rescrise.append(n)
    if rescrise:
        jurnal.noteaza(profil.eticheta, 'referinte vechi rescrise pe %d%s: %s'
                       % (profil.port, ' (%s)' % forma_dab(profil) if profil.tip == 'dab' else '', ', '.join(rescrise)))
    if cazute:
        jurnal.noteaza(profil.eticheta, 'buchete cu referinte vechi necitite sau nescrise: %s' % ', '.join(
            '%s (%s)' % (x, getattr(e, 'strerror', None) or e) for x, e in cazute))
        raise cazute[0][1]
    return rescrise


# numele de dinainte de forma sunetului (0.1.10 - 0.2.0): numai portul
rescrie_porturi_vechi = rescrie_referinte_vechi


def redenumeste_marcajele(profil, director=None):
    """Marcajele ansamblurilor din buchetul profilului scrise de versiunile vechi cu numele gol al ansamblului
    („DR Deutschland”) primesc numele de acum („MUX DAB+: DR Deutschland”, nume_marcaj), pe loc: aceeasi referinta,
    deci fara dubluri. #DESCRIPTION egal cu numele vechi se schimba si el; unul schimbat de om ramane. Numai
    marcajele noastre (1:64:4844xxxx) din buchetul nostru; restul fisierului ramane octet cu octet. Un marcaj care are
    deja prefixul nu se atinge, deci o trecere in plus nu schimba nimic. Scriere atomica. Blocant: din fir, sub
    zavorul scrierilor. Un buchet care exista dar nu se poate citi sau scrie arunca eroarea (IOError / OSError).
    -> True daca s-a scris ceva."""
    cale = os.path.join(director or DIRECTOR_ENIGMA2, profil.buchet)
    if not os.path.exists(cale):
        return False
    with open(cale, 'rb') as f:
        date = f.read()
    linii = date.split(b'\n')
    schimbate = 0
    for i, linie in enumerate(linii):
        if not linie.startswith(b'#SERVICE 1:64:'):
            continue
        cr = b'\r' if linie.endswith(b'\r') else b''
        parti = linie[len(b'#SERVICE '):len(linie) - len(cr)].split(b':')
        if len(parti) < 11 or not _e_marcaj_nostru(b':'.join(parti[:11]).decode('latin-1')):
            continue
        vechi = b':'.join(parti[11:]).decode('utf-8', 'replace').strip()
        nou = nume_marcaj(profil, vechi)
        if nou == vechi:
            continue
        nou_b = nou.encode('utf-8')
        linii[i] = b'#SERVICE ' + b':'.join(parti[:11]) + b':' + nou_b + cr
        if i + 1 < len(linii) and linii[i + 1].startswith(b'#DESCRIPTION '):
            urm = linii[i + 1]
            cr2 = b'\r' if urm.endswith(b'\r') else b''
            desc = urm[len(b'#DESCRIPTION '):len(urm) - len(cr2)].decode('utf-8', 'replace').strip()
            if desc == vechi:
                linii[i + 1] = b'#DESCRIPTION ' + nou_b + cr2
        schimbate += 1
    if not schimbate:
        return False
    scrie_atomic(cale, b'\n'.join(linii))
    jurnal.noteaza(profil.eticheta, 'marcaje redenumite in %s: %d' % (profil.buchet, schimbate))
    return True


# ---------------------------------------------------------------- serviciile invatate
def cale_servicii(profil, director=None):
    return os.path.join(director or profil.director, 'servicii.json')


def citeste_servicii(profil, director=None):
    try:
        with open(cale_servicii(profil, director), 'rb') as f:
            date = json.loads(f.read(2 * 1024 * 1024).decode('utf-8'))
        return date if isinstance(date, dict) else {}
    except Exception:
        return {}


def _servicii_curate(profil, lista):
    rez = []
    vazute = set()
    for s in lista or []:
        if not isinstance(s, dict):
            continue
        sid = _int(s.get('sid'), -1)
        if sid <= 0 or sid > 0xFFFF or sid in vazute:
            continue
        vazute.add(sid)
        x = {'sid': sid, 'nume': _curata_nume(s.get('nume'))}
        if profil.tip == 't2':
            x['tsid'] = _int(s.get('tsid'))
            x['onid'] = _int(s.get('onid'))
            x['tip'] = _int(s.get('tip'), 1) or 1
        else:
            for k in ('fel', 'kbit'):
                if s.get(k) is not None:
                    x[k] = s.get(k)
        rez.append(x)
    return rez


def salveaza_servicii(profil, feed_id, lista, director=None):
    """Tine minte posturile/serviciile unui feed. -> True daca s-a schimbat ceva."""
    toate = citeste_servicii(profil, director)
    noi = _servicii_curate(profil, lista)
    if not noi:
        return False
    vechi = (toate.get(feed_id) or {}).get('servicii')
    if vechi == noi:
        return False
    toate[feed_id] = {'actualizat': time.strftime('%Y-%m-%d %H:%M'), 'servicii': noi}
    scrie_atomic(cale_servicii(profil, director),
                 (json.dumps(toate, ensure_ascii=False, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return True


def servicii_feed(profil, feed, memorate, stb=None, tp=None, prinse=None):
    """Serviciile unui feed: cele invatate de receptor (servicii.json), altfel cele publicate pe stb.hdsatelit.com
    (servicii-stb.json, numai cand receptorul prinde transponderul feed-ului: `prinse`), altfel cele din lista
    (posturi / servicii)."""
    din_cache = (memorate.get(_curata_id(feed.get('id'))) or {}).get('servicii')
    if din_cache:
        return _servicii_curate(profil, din_cache)
    if stb and tp is not None and prins(tp, prinse):
        publicate = servicii_stb_pentru(profil, feed, tp, stb)
        if publicate:
            return publicate
    return _servicii_curate(profil, feed.get('posturi') or feed.get('servicii'))


# ---------------------------------------------------------------- posturile publicate pe stb.hdsatelit.com
# servicii.json de langa frecvente.json pe stb (liste.descarca_servicii) se tine separat de servicii.json al
# receptorului: acela e ce a invatat receptorul insusi si castiga mereu
FISIER_SERVICII_STB = 'servicii-stb.json'


def cale_servicii_stb(profil, director=None):
    return os.path.join(director or profil.director, FISIER_SERVICII_STB)


def citeste_servicii_stb(profil, director=None):
    """{id feed: {'servicii': [...], 'cheie': {...}}} din servicii-stb.json; {} daca lipseste sau e stricat."""
    try:
        with open(cale_servicii_stb(profil, director), 'rb') as f:
            date = json.loads(f.read(2 * 1024 * 1024).decode('utf-8'))
        feeduri = date.get('feeduri') if isinstance(date, dict) else None
        return feeduri if isinstance(feeduri, dict) else {}
    except Exception:
        return {}


def _cheie_potrivita(profil, cheie, feed, tp):
    """Cheia publicata a unui feed (pozitie, frecventa, pol, is_id, pid, fel, ip/port la EDI, plp la T2) e a feed-ului
    din lista, pe transponderul lui (toleranta de frecventa ca la unirea listelor)?"""
    if not isinstance(cheie, dict):
        return False
    from . import liste
    try:
        tp_c = {'pozitie': cheie.get('pozitie'), 'pol': cheie.get('pol'), 'is_id': cheie.get('is_id'),
                'frecventa': int(cheie.get('frecventa'))}
        f_c = {'tip': profil.tip, 'pid': cheie.get('pid'), 'fel': cheie.get('fel'), 'ip': cheie.get('ip'),
               'port': cheie.get('port'), 'plp': cheie.get('plp')}
        return liste._acelasi_transponder(tp_c, tp) and liste._cheie_feed(f_c) == liste._cheie_feed(feed)
    except (TypeError, ValueError, KeyError):
        return False


def servicii_stb_pentru(profil, feed, tp, stb):
    """Posturile publicate pentru un feed: intai dupa id (id-ul publicat = cel din lista incorporata), apoi dupa cheie
    (pe un receptor care a scanat, id-ul local al aceluiasi feed e altul, de pilda det_edi_...)."""
    d = stb.get(_curata_id(feed.get('id')))
    if not (isinstance(d, dict) and d.get('servicii')):
        d = None
        for x in stb.values():
            if isinstance(x, dict) and x.get('servicii') and _cheie_potrivita(profil, x.get('cheie'), feed, tp):
                d = x
                break
    return _servicii_curate(profil, d.get('servicii')) if d else []


def prins(tp, prinse):
    """Transponderul unui feed e prins de acest receptor? `prinse`: cheile din transpondere_prinse (None = nu se
    stie, deci nu)."""
    if not prinse:
        return False
    from . import tuner
    p = tuner.parametri(tp)
    for poz, khz, pol, is_id in prinse:
        if poz == p['orbital_position'] and pol == p['polarisation'] and abs(khz - p['frequency']) <= 2000                 and (is_id < 0 or p['is_id'] < 0 or is_id == p['is_id']):
            return True
    return False


def transpondere_prinse(profil, director_date=None, cale_lamedb=None):
    """Transponderele de satelit pe care acest receptor le-a prins el insusi: cele din lista lui de canale (lamedb, fara
    purtatorii nostri) si cele ale feed-urilor gasite de scanarea lui (scanate.json). -> set de (pozitie, kHz, pol,
    is_id). Un feed de pe alt transponder (alt fascicul, alt satelit) nu primeste posturi publicate in buchet."""
    from . import lamedb, liste, tuner
    rez = set(lamedb.transpondere_receptor(cale_lamedb))
    scanate = liste.citeste_json(os.path.join(director_date or profil.director, liste.FISIER['scanat']), profil.tip)
    for t in (scanate or {}).get('transpondere') or []:
        p = tuner.parametri(t)
        rez.add((p['orbital_position'], p['frequency'], p['polarisation'], p['is_id']))
    return rez


# ---------------------------------------------------------------- scriere
def scrie_atomic(cale, octeti):
    director = os.path.dirname(cale) or '.'
    if not os.path.isdir(director):
        os.makedirs(director)
    # pid + fir: scrierile din firele de fundal nu isi calca fisierul temporar
    tmp = '%s.tmp%d_%d' % (cale, os.getpid(), threading.current_thread().ident or 0)
    try:
        with open(tmp, 'wb') as f:
            f.write(octeti)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        compat.inlocuieste(tmp, cale)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _citeste_text(cale):
    try:
        with open(cale, 'rb') as f:
            return f.read().decode('utf-8', 'replace')
    except (IOError, OSError):
        return None


def _cheie(linie_service):
    """Cheia unei intrari: referinta fara nume. Pentru URL-uri, pana la sfarsitul URL-ului."""
    ref = linie_service[len('#SERVICE '):].strip()
    parti = ref.split(':')
    if len(parti) > 11:
        return ':'.join(parti[:11])
    return ref


def _nume_din(linie_service):
    ref = linie_service[len('#SERVICE '):].strip()
    parti = ref.split(':')
    return ':'.join(parti[11:]) if len(parti) > 11 else ''


def _intrari(text):
    """Textul unui userbouquet -> (nume, [[linie_service, linie_description_sau_None], ...])."""
    nume, intrari = None, []
    for linie in (text or '').splitlines():
        linie = linie.rstrip('\r')
        if linie.startswith('#NAME ') and nume is None:
            nume = linie[6:]
        elif linie.startswith('#SERVICE '):
            intrari.append([linie, None])
        elif linie.startswith('#DESCRIPTION ') and intrari and intrari[-1][1] is None:
            intrari[-1][1] = linie
    return nume, intrari


def _cheie_curenta(profil, cheie):
    """Cheia unei intrari scrise cu un port vechi sau, la DAB, in alta forma a sunetului -> cheia aceluiasi post in
    forma de acum (ref_curenta); altfel neschimbata."""
    nou = ref_curenta(profil, cheie.replace('%3A', '%3a'))
    return nou if nou is not None else cheie


def _e_marcaj_nostru(cheie):
    parti = cheie.split(':')
    return len(parti) > 2 and parti[0] == '1' and parti[1] == '64' and parti[2].upper().startswith('4844') \
        and len(parti[2]) == 8


def nume_afisate(servicii):
    """Numele de aratat ale serviciilor unui feed, in aceeasi ordine. Un nume purtat de mai multe servicii ale
    aceluiasi feed (un multiplex poate da in SDT acelasi nume tuturor programelor) primeste SID-ul dupa el, ca
    intrarile sa se poata deosebi in lista de canale."""
    numar = {}
    for s in servicii:
        numar[s['nume']] = numar.get(s['nume'], 0) + 1
    return ['%s (%d)' % (s['nume'], s['sid']) if numar[s['nume']] > 1 else s['nume'] for s in servicii]


def intrari_noi(profil, lista, memorate, stb=None, prinse=None):
    """Lista unita de feed-uri -> [(feed_id, cheie, linie_service, nume)] in ordinea listei."""
    rez = []
    for tp in lista.get('transpondere', []):
        for feed in tp.get('feeduri', []):
            if feed.get('tip') != profil.tip:
                continue
            servicii = servicii_feed(profil, feed, memorate, stb, tp, prinse)
            if not servicii:
                continue
            fid = _curata_id(feed.get('id'))
            nume_feed = nume_marcaj(profil, feed.get('nume') or fid)
            ref = ref_marcaj(fid)
            rez.append((fid, _cheie('#SERVICE ' + ref), '#SERVICE %s%s' % (ref, nume_feed), nume_feed))
            for s, nume in zip(servicii, nume_afisate(servicii)):
                if profil.tip == 'dab':
                    ref = ref_dab(profil, fid, s['sid'])
                else:
                    ref = ref_t2(profil, feed, s)
                linie = '#SERVICE %s:%s' % (ref, nume)
                rez.append((fid, _cheie(linie), linie, nume))
    return rez


def compune(profil, text_vechi, noi):
    """Textul nou al buchetului. Pastreaza ordinea si intrarile utilizatorului."""
    _, vechi = _intrari(text_vechi)
    dupa_cheie = dict((cheie, (fid, linie, nume)) for fid, cheie, linie, nume in noi)
    folosite = set()
    rez = []          # [(feed_id sau None, linie, descriere)]
    for linie, descriere in vechi:
        cheie = _cheie(linie)
        nostru = al_nostru(profil, cheie) or _e_marcaj_nostru(cheie)
        if not nostru:
            rez.append((None, linie, descriere))
            continue
        cheie = _cheie_curenta(profil, cheie)      # port vechi sau alta forma DAB: locul si numele raman
        if cheie not in dupa_cheie or cheie in folosite:
            continue   # feed-ul sau postul nu mai exista
        fid, linie_noua, nume = dupa_cheie[cheie]
        folosite.add(cheie)
        nume_vechi = _nume_din(linie)
        if descriere is not None and descriere[len('#DESCRIPTION '):] not in (nume_vechi, nume):
            desc = descriere                      # redenumit de utilizator: ramane
        else:
            desc = '#DESCRIPTION %s' % nume
        rez.append((fid, linie_noua, desc))
    for fid, cheie, linie, nume in noi:
        if cheie in folosite:
            continue
        folosite.add(cheie)
        loc = len(rez)
        for i in range(len(rez) - 1, -1, -1):
            if rez[i][0] == fid:
                loc = i + 1
                break
        rez.insert(loc, (fid, linie, '#DESCRIPTION %s' % nume))
    linii = ['#NAME %s' % profil.nume_buchet]
    for _, linie, desc in rez:
        linii.append(linie)
        if desc:
            linii.append(desc)
    return '\n'.join(linii) + '\n'


def linie_index(profil):
    return '#SERVICE 1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (profil.tip_index, profil.buchet)


def asigura_index(profil, director):
    """Adauga buchetul in bouquets.radio / bouquets.tv doar daca lipseste. -> True daca a scris."""
    cale = os.path.join(director, profil.index_buchete)
    text = _citeste_text(cale)
    if text is not None and ('"%s"' % profil.buchet) in text:
        return False
    if text is None:
        text = '#NAME %s\n' % ('Bouquets (Radio)' if profil.tip_index == 2 else 'Bouquets (TV)')
    if not text.endswith('\n'):
        text += '\n'
    text += linie_index(profil) + '\n'
    scrie_atomic(cale, text.encode('utf-8'))
    return True


def reface(profil, lista, director=None, director_date=None, reincarca=True):
    """Scrie buchetul si indexul. -> {'schimbat': bool, 'intrari': n, 'feeduri': n}. Nu arunca."""
    rez = {'schimbat': False, 'intrari': 0, 'feeduri': 0}
    director = director or DIRECTOR_ENIGMA2
    try:
        memorate = citeste_servicii(profil, director_date)
        stb = citeste_servicii_stb(profil, director_date)
        prinse = transpondere_prinse(profil, director_date) if stb else None
        noi = intrari_noi(profil, lista, memorate, stb, prinse)
        rez['feeduri'] = len(set(fid for fid, _, _, _ in noi))
        rez['intrari'] = len([1 for _, c, _, _ in noi if not _e_marcaj_nostru(c)])
        cale = os.path.join(director, profil.buchet)
        vechi = _citeste_text(cale)
        nou = compune(profil, vechi or '', noi)
        schimbat = False
        if nou != vechi:
            scrie_atomic(cale, nou.encode('utf-8'))
            schimbat = True
        if asigura_index(profil, director):
            schimbat = True
        rez['schimbat'] = schimbat
        if schimbat:
            jurnal.noteaza(profil.eticheta, 'buchet refacut: %d intrari din %d feed-uri'
                           % (rez['intrari'], rez['feeduri']))
            if reincarca:
                reincarca_buchete()
    except Exception:
        jurnal.eroare(profil.eticheta, 'refacerea buchetelor')
        rez['eroare'] = True
    return rez


def reincarca_buchete():
    try:
        from enigma import eDVBDB
        eDVBDB.getInstance().reloadBouquets()
    except Exception:
        jurnal.eroare('buchete', 'reloadBouquets')

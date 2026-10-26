# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ScanerSatelit.py: scanerul de satelit al imaginii HDSatelit.

Scris de la zero.

La tasta MENU, Scanare -> Satelit are sapte feluri de scanare, toate la acelasi nivel, in aceasta ordine:
  1 "transponder"  dupa transponder, ales din lista satelitului (satellites.xml);
  2 "satelit"      tot satelitul;
  3 "mai_multi"    mai multi sateliti: ecranul Screens/ScanerMaiMultiSateliti.py (mecanismul din ScanSetup);
  4 "operator"     dupa operator, din data/operatori-satelit.json (Components/HdsOperatoriSatelit.py): intai
                   operatorii din tara utilizatorului, apoi ceilalti, pe tari; un transponder de pornire, apoi
                   cautare in retea (NIT);
  5 "manual"       cu date introduse de mana (frecventa, polarizare, rata, FEC, sistem, modulatie si, la
                   multistream, fluxul si secventa PLS);
  6 "dvbt2"        DVB-T2 prin satelit: acord pe transponderul purtator si detectorul HdsComun (nu ServiceScan);
  7 "dab"          DAB+ prin satelit: la fel, cu profilul DAB.
Meniul trimite felul ca argument: <screen module="ScanerSatelit" screen="ScanerSatelit">"operator"</screen>
(Menu.py lipeste textul si il trece prin eval). Fara argument (fel=None) ecranul are randul „Fel de scanare",
deci merg si intrarea veche din meniu si Gasire semnal (Satfinder.py trimite 'tip': '1').

Tot ce se cere nucleului trece prin pregateste(fel, valori): aceeasi functie pentru ecran si pentru interfata
web, ca sa nu existe doua adevaruri. Pozitiile raman peste tot 0..3599 (5,0 vest = 3550): cu motor, antena se
duce singura pe pozitia ceruta, la acord, din orbital_position (lib/dvb/sec.cpp); o traducere in -50 ar trimite-o
spre 5,0 EST (vezi antetul din Components/HdsOperatoriSatelit.py). Cu antena fixa se cauta numai pe pozitiile pe
care le vede antena (NimManager.getSatListForNim), iar altfel se spune limpede de ce nu si ce se poate cauta.

Listele de alegere se deschid in AlegereDinLista (Screens/ScanerCablu.py), unde Verde alege randul luminat;
previzualizarea vine tot din pregateste, la fel ca la Verde; rata de simbol se verifica fata de limitele driverului;
o eroare dupa detectorul de fluxuri nu lasa ecranul agatat; la operatori antena se verifica inaintea multistream-ului;
randurile si sistemele pe care nucleul nu le foloseste nu se arata; pozitia se scrie peste tot la fel, „19,2°E".
Pachetele operatorilor DTH (Digi, Focus Sat) stau, cu sursa, in lista de operatori, iar felul „dupa operator" le ia
de acolo, cu aceleasi valori ca vechiul „Un pachet de canale" (proba: teste/test_pachete_dth.py).
"""
from __future__ import absolute_import, unicode_literals
import json
import os
import re
import time

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.HdsLatimeText import INDENT
from Components.HdsCursorLista import pune_randurile
from Components.HdsOperatoriSatelit import (FEL_JSON, NUME_TARI, grupe, nume_tara, operator as operator_dupa_id,
                                            operatori, tara_utilizatorului, transponder_hdscomun, transponder_nucleu)

# ---------------------------------------------------------------- constante
CALE_CONFIG = '/etc/enigma2/hdsscaner_satelit.conf'

# Felurile de scanare, in ordinea din meniu. Cheile sunt si argumentul din menu.xml.
FELURI = [
    ('transponder', _('După transponder')),
    ('satelit', _('După satelit')),
    ('mai_multi', _('Mai mulți sateliți')),
    ('operator', _('După operator')),
    ('manual', _('Cu date introduse manual')),
    ('dvbt2', _('DVB-T2 prin satelit')),
    ('dab', _('DAB+ prin satelit')),
]
CHEI_FELURI = [c for c, n in FELURI]
# Felul din titlul ferestrei, scurt: titlul incape si cu fonturile marite la 130 % (HdsBold 52 in 1000 px); numele
# intreg ramane in meniu si in randul felului.
TITLURI_SCURTE = {'manual': _('Manual')}

# Randul vechi „Ce se cauta" ('tip') -> felul de acum. Gasire semnal (Satfinder.py) trimite inca 'tip': '1', iar
# fisierul de configurare al cuiva poate avea inca 'tip = 2' (pachetul DTH, acum „dupa operator").
FEL_DIN_TIP = {'0': 'satelit', '1': 'manual', '2': 'operator'}

# Campul din configurare in care se tine operatorul ales, pe fiecare fel (fiecare fel isi tine alegerea lui).
CAMP_OPERATOR = {'operator': 'operator', 'dvbt2': 'operator_dvbt2', 'dab': 'operator_dab'}
PROFIL_FEL = {'dvbt2': 't2', 'dab': 'dab'}

DA_NU = [('0', _('Nu')), ('1', _('Da'))]

# Randurile de actiune de la sfarsitul listei ecranului (numai sagetile si OK): la felurile din PROFIL_FEL
# „Fluxuri și setări” (fereastra HdsComun a felului, ca Albastru), apoi „Caută acum” (ca Verde), mereu ultimul, deci
# SUS de pe primul rand ajunge pe el. Nu sunt campuri: nu intra in _CAMPURI, in configuratia salvata sau in ce
# citeste pagina web /scanare.
RAND_CAUTA = '_cauta'
RAND_FLUXURI = '_fluxuri'

# Campurile de tip lista care au mai mult de atatea valori se aleg dintr-o fereastra (OK), nu doar cu stanga/dreapta.
PRAG_ALEGERE = 6

# Sisteme DVB (cod enigma2 / lamedb). Numai cele doua pe care nucleul le acordeaza (DVB-S2X, TURBO FEC si ISDB-S
# s-ar refuza abia la Verde). transponder_manual raspunde limpede si la codurile 2-4, daca vin dintr-o configurare
# veche sau dintr-o cerere web facuta de mana.
SISTEME = [
    (0, _('DVB-S  (QPSK clasic)')),
    (1, _('DVB-S2 (8PSK / QPSK)')),
]

# Polarizari
POLARIZARI = [
    (0, _('H: orizontal (liniar)')),
    (1, _('V: vertical (liniar)')),
    (2, _('L: circular stânga (LHCP)')),
    (3, _('R: circular dreapta (RHCP)')),
]

# FEC (Inner FEC): coduri enigma2
FEC_VALORI = [
    (0,  _('Auto')),
    (1,  '1/2'), (2,  '2/3'), (3,  '3/4'),
    (4,  '5/6'), (5,  '7/8'), (6,  '8/9'),
    (7,  '3/5'), (8,  '4/5'), (9,  '9/10'),
    (10, '2/5'), (11, '6/7'), (12, '7/9'),
    (13, '77/90'),  # DVB-S2X
    (14, '32/45'),  # DVB-S2X
    (15, _('Niciuna')),
]

# Modulatii satelit
MODULATII = [
    (0, _('Auto')),
    (1, 'QPSK'),   (2, '8PSK'),   (3, 'QAM16'),
    (4, 'QAM64'),  (5, '32APSK'), (6, '16APSK'),
    (7, '64APSK'), (8, '128APSK'),(9, '256APSK'),  # S2X
]

# Factorul de rotunjire (roll-off): numai valorile din nucleu (0,15, 0,10 si 0,05 sunt DVB-S2X, pe care nu il are)
ROLLOFF = [
    (0, '0,35'),
    (1, '0,25'),
    (2, '0,20'),
]

# Pilot
PILOT = [
    (2, _('Auto')),
    (0, _('Oprit')),
    (1, _('Pornit')),
]

# Inversare spectru
INVERSARE = [(2, _('Auto')), (0, _('Normal')), (1, _('Inversat'))]

# Secventa PLS (Physical Layer Scrambling) a unui transponder multistream: codul pls_mode din nucleu
# (lib/dvb/frontendparms.h: 0 Root, 1 Gold, 2 Combo). Gold e primul: in forma aceasta o publica operatorii.
PLS_MODURI = [
    (1, 'Gold'),
    (0, 'Root'),
    (2, 'Combo'),
]

# ---------------------------------------------------------------- ce primeste nucleul imaginii
# DVB-S2 cu FEC 0 (Auto) sau modulatie 0 (Auto) nu se acordeaza: lib/dvb/frontend.cpp (prepare_sat, ramura DVB_S2)
# nu are caz pentru FEC_Auto ("no valid fec for DVB-S2 set.. abort", -EINVAL), iar lib/dvb/scan.cpp (nextChannel)
# sare atunci transponderul fara sa-l numere, deci cautarea arata 0 canale, fara motiv. Tot ce pleaca de aici spre
# ServiceScan trece prin valorile de mai jos, luate din lib/dvb/frontendparms.h (eDVBFrontendParametersSatellite) si
# din switch-urile din frontend.cpp.
SISTEM_DVB_S, SISTEM_DVB_S2 = 0, 1
FEC_DVBS = [0, 1, 2, 3, 4, 5, 15]        # Auto, 1/2, 2/3, 3/4, 5/6, 7/8, Niciuna (ramura DVB-S primeste Auto)
FEC_DVBS2 = [1, 7, 2, 3, 8, 4, 5, 6, 9]   # 1/2, 3/5, 2/3, 3/4, 4/5, 5/6, 7/8, 8/9, 9/10; fara Auto
MOD_DVBS = [0, 1]                        # Auto, QPSK (DVB-S e mereu QPSK)
MOD_DVBS2 = [1, 2]                       # QPSK, 8PSK (APSK nu exista in structura din nucleu)
ROLLOFF_VALIDE = [0, 1, 2]               # 0.35, 0.25, 0.20
# Perechile (modulatie, FEC) din standardul DVB-S2 (ETSI EN 302 307), oferite cand lipsesc si nu sunt in satellites.xml
COMBINATII_DVBS2 = [(2, f) for f in (7, 2, 3, 4, 6, 9)] + [(1, f) for f in (1, 7, 2, 3, 8, 4, 6, 9)]
TOLERANTA_KHZ = 3000                     # cat se poate abate frecventa introdusa de cea din satellites.xml
# Rata de simbol pe care o primeste driverul tunerului (dmesg: „symbol rate 990000 out of range
# (1000000..60000000)"). 66 de transpondere din satellites.xml ies din interval: fara verificare ar da 0 canale, fara
# niciun motiv.
SR_MIN, SR_MAX = 1000000, 60000000
# Multistream DVB-S2 (lib/dvb/hdsmultistream.h): fluxul (ISI) e un octet, codul PLS are 18 biti
ISI_MAX = 255
PLS_COD_MAX = 262143


def _int(v, implicit):
    try:
        return int(v)
    except (ValueError, TypeError):
        return implicit


def _da(v):
    return str(v).strip().lower() in ('1', 'true', 'da', 'yes')


def _nume_valoare(lista, cod):
    for c, desc in lista:
        if c == cod:
            return desc
    return str(cod)


def sistem_ales(valoare):
    """Randul „Sistem" are numai DVB-S (0) si DVB-S2 (1). Orice alt cod, scris de o versiune veche a ecranului
    (DVB-S2X, TURBO FEC, ISDB-S), trece pe DVB-S2."""
    return str(SISTEM_DVB_S) if _int(valoare, SISTEM_DVB_S2) == SISTEM_DVB_S else str(SISTEM_DVB_S2)


def _sistem_nucleu(c):
    """Sistemul din config asa cum il vede nucleul: DVB-S2X (2) se acordeaza ca DVB-S2."""
    s = _int(c.get('sistem'), SISTEM_DVB_S2)
    return SISTEM_DVB_S2 if s == 2 else s


def _coduri_permise(cheie, c, lista):
    """Valorile prin care trec OK, stanga si dreapta: doar cele pe care nucleul le primeste pentru sistemul ales."""
    s2 = _sistem_nucleu(c) == SISTEM_DVB_S2
    if cheie == 'fec':
        return FEC_DVBS2 if s2 else FEC_DVBS
    if cheie == 'mod':
        return MOD_DVBS2 if s2 else MOD_DVBS
    if cheie == 'rolloff':
        return ROLLOFF_VALIDE
    return [x[0] for x in lista]


def _descriere_tp(tp):
    """Ex.: 11739 V 27500 DVB-S 3/4 QPSK; multistream: 12564 V 35294 DVB-S2 2/3 8PSK flux 11 PLS Gold 131070"""
    pol = tp['polarisation']
    text = '%d %s %d %s %s %s' % (
        tp['frequency'] // 1000, 'HVLR'[pol] if 0 <= pol <= 3 else '?', tp['symbol_rate'] // 1000,
        'DVB-S2' if tp['system'] == SISTEM_DVB_S2 else 'DVB-S',
        _nume_valoare(FEC_VALORI, tp['fec']), _nume_valoare(MODULATII, tp['modulation']))
    ms = text_multistream(tp)
    return text + ' ' + ms if ms else text


def _pls_implicit(mod, cod):
    """Secventa PLS implicita in oricare scriere a ei: Gold 0, Combo 0, Root 1 si Root 0 (il scriu listele fara PLS)."""
    if mod == 0:
        return cod in (0, 1)
    return cod == 0


def are_multistream(tp):
    """Transponderul cere un flux (is_id 0..255) sau o secventa PLS alta decat cea implicita. Aceeasi regula ca in
    nucleu (lib/dvb/hdsmultistream.h, cereFlux): numai atunci primeste driverul DTV_STREAM_ID."""
    isi = _int(tp.get('is_id'), -1)
    if 0 <= isi <= ISI_MAX:
        return True
    return not _pls_implicit(_int(tp.get('pls_mode'), 1), _int(tp.get('pls_code'), 0))


def text_multistream(tp):
    """„flux 11 PLS Gold 131070", „flux 10", „PLS Root 8"; '' fara multistream."""
    if not are_multistream(tp):
        return ''
    parti = []
    isi = _int(tp.get('is_id'), -1)
    if 0 <= isi <= ISI_MAX:
        parti.append(_('flux %d') % isi)
    mod, cod = _int(tp.get('pls_mode'), 1), _int(tp.get('pls_code'), 0)
    if not _pls_implicit(mod, cod):
        parti.append('PLS %s %d' % (_nume_valoare(PLS_MODURI, mod), cod))
    return ' '.join(parti)


def nucleu_multistream():
    """Nucleul imaginii are fluxul si PLS-ul in eDVBFrontendParametersSatellite (lib/dvb/frontendparms.h)."""
    try:
        from enigma import eDVBFrontendParametersSatellite
        p = eDVBFrontendParametersSatellite()
        return all(hasattr(p, c) for c in ('is_id', 'pls_mode', 'pls_code'))
    except Exception:
        return False


def tuner_multistream(nim, slot):
    """Tunerul de satelit poate alege fluxul (NIM.isMultistream: „DVB-S2X" sau „Multistream: yes" in
    /proc/bus/nim_sockets) si nucleul are campurile. Fara una din ele transponderele multistream nu se pot cauta."""
    try:
        if not nim.nim_slots[slot].isMultistream():
            return False
    except Exception:
        return False
    return nucleu_multistream()


def text_pozitie(orbpos):
    """Pozitia bruta in text, in limba meniului (Components/HdsGrade.py): 192 -> 19,2°E, 3550 -> 5,0°V (vest; in
    engleza 5.0°W). „?" cand nu e o pozitie."""
    from Components.HdsGrade import pozitieOrbitala
    return pozitieOrbitala(_int(orbpos, None)) or '?'


def nume_satelit(orbpos, nume):
    """Numele satelitului cu pozitia scrisa ca in restul imaginii (Components/HdsGrade.numeSatelit): '19.2E Astra
    1N/1P" (satellites.xml) devine '19,2°E Astra 1N/1P"; pozitia e cea din nume, cand numele o are ('177.0W C-band
    NSS 9", cu position -1771 in satellites.xml, ramane '177,0°V", nu '177,1°V"); fara nume ramane pozitia."""
    from Components.HdsGrade import numeSatelit
    return numeSatelit(_int(orbpos, None), nume) or text_pozitie(orbpos)


def cheie_tp(tp):
    """Cheia unui transponder in lista satelitului: frecventa kHz, polarizare, SR (ex. 11739000:1:27500000). La un
    flux ales se adauga fluxul (12564000:1:35294000:11), ca fluxurile aceleiasi frecvente sa nu se confunde; cheile
    transponderelor obisnuite raman cum erau, deci configurarea salvata le gaseste."""
    cheie = '%d:%d:%d' % (tp['frequency'], tp['polarisation'], tp['symbol_rate'])
    isi = _int(tp.get('is_id'), -1)
    return cheie + (':%d' % isi if 0 <= isi <= ISI_MAX else '')


def _descriere_hdscomun(tp):
    """Ex.: 39,0°E 11760 H 16515; frecventa cu zecimala cand nu e un MHz intreg (19,2°E 12460,5 H 27500), cum o
    publica operatorii: rotunjita ar arata alt transponder."""
    khz = _int(tp.get('frecventa'), 0)
    frecventa = '%d' % (khz // 1000) if khz % 1000 == 0 else '%d,%d' % (khz // 1000, (khz % 1000) // 100)
    return '%s %s %s %d' % (text_pozitie(tp.get('pozitie')), frecventa, tp.get('pol') or '?',
                            _int(tp.get('sr'), 0) // 1000)


def motiv_refuz(tp):
    """De ce ar refuza nucleul transponderul (text), sau None daca il primeste. Aceleasi reguli ca prepare_sat
    si setFrontend din lib/dvb/frontend.cpp."""
    if tp['frequency'] <= 0 or tp['symbol_rate'] <= 0:
        return _('frecvența sau rata de simbol lipsește')
    if not SR_MIN <= tp['symbol_rate'] <= SR_MAX:
        return _rata_refuzata(tp['symbol_rate'])
    if tp['polarisation'] not in (0, 1, 2, 3):
        return _('polarizare necunoscută')
    if are_multistream(tp):
        if tp['system'] != SISTEM_DVB_S2:
            return _('multistream există numai în DVB-S2')
        if not 0 <= _int(tp.get('pls_code'), 0) <= PLS_COD_MAX:
            return _('codul PLS trebuie să fie între 0 și %d') % PLS_COD_MAX
    if tp['system'] == SISTEM_DVB_S:
        return None
    if tp['system'] != SISTEM_DVB_S2:
        return _('sistem pe care imaginea nu îl știe')
    if tp['fec'] not in FEC_DVBS2:
        return _('DVB-S2 fără FEC real, Auto nu e primit')
    if tp['modulation'] not in MOD_DVBS2:
        return _('modulație pe care imaginea nu o știe încă')
    return None


def _rata_refuzata(sr):
    """Motivul pentru o rata de simbol in afara limitelor driverului (sr in simboluri/s)."""
    return _('rata de simbol %d kSymb/s nu e primită de tuner (%d-%d kSymb/s)') % (
        sr // 1000, SR_MIN // 1000, SR_MAX // 1000)


def _multistream_din_xml(x):
    """{'is_id', 'pls_mode', 'pls_code'} dintr-un tuplu din satellites.xml, sau {} fara multistream."""
    if len(x) <= 14:
        return {}
    ms = {'is_id': x[12], 'pls_mode': x[13], 'pls_code': x[14]}
    return ms if are_multistream(ms) else {}


def transpondere_satelit(orbpos, transpondere_xml, multistream=True):
    """Toate transponderele satelitului din satellites.xml (nimmanager.getTransponders(orbpos)), ca in
    ScanSetup.getInitialTransponderList. Tuplul vine din lib/dvb/db.cpp (readSatellites): (0, frecventa kHz,
    SR simb/s, pol, fec, sistem, modulatie, inversare, rolloff, pilot, tsid, onid, is_id, pls_mode, pls_code,
    t2mi_plp_id, t2mi_pid). Frecventa e deja in kHz si SR in simboluri/s, deci aici NU se mai inmulteste cu 1000.
    Transponderele multistream primesc is_id, pls_mode si pls_code; cu multistream=False (tunerul nu poate alege
    fluxul) ele trec la sarite. Intoarce (bune, sarite), sarite = [(tp, motiv)]."""
    bune, sarite = [], []
    for x in transpondere_xml or []:
        if x[0] != 0:
            continue
        tp = {'frequency': x[1], 'symbol_rate': x[2], 'polarisation': x[3], 'fec': x[4],
              'inversion': x[7] if x[7] in (0, 1, 2) else 2, 'orbital_position': orbpos,
              'system': x[5], 'modulation': x[6],
              'rolloff': x[8] if x[8] in ROLLOFF_VALIDE else 0, 'pilot': x[9] if x[9] in (0, 1, 2) else 2}
        tp.update(_multistream_din_xml(x))
        motiv = motiv_refuz(tp)
        if not motiv and not multistream and are_multistream(tp):
            motiv = _('multistream, iar tunerul nu poate alege fluxul')
        if motiv:
            sarite.append((tp, motiv))
        else:
            bune.append(tp)
    return bune, sarite


def _cauta_in_xml(frecventa_khz, pol, transpondere_xml):
    """Transponderul din satellites.xml cu aceeasi polarizare si frecventa cea mai apropiata, sub TOLERANTA_KHZ."""
    gasit, dif_min = None, TOLERANTA_KHZ + 1
    for x in transpondere_xml or []:
        if x[0] == 0 and x[3] == pol:
            dif = abs(x[1] - frecventa_khz)
            if dif < dif_min:
                gasit, dif_min = x, dif
    return gasit


def _fluxuri_in_xml(frecventa_khz, pol, transpondere_xml):
    """Fluxurile multistream din satellites.xml de pe aceeasi frecventa (sub TOLERANTA_KHZ) si polarizare:
    [{'is_id', 'pls_mode', 'pls_code'}], fara repetari."""
    rez = []
    for x in transpondere_xml or []:
        if x[0] == 0 and x[3] == pol and abs(x[1] - frecventa_khz) <= TOLERANTA_KHZ:
            ms = _multistream_din_xml(x)
            if ms and ms not in rez:
                rez.append(ms)
    return rez


def transponder_manual(c, transpondere_xml):
    """Transponderul introdus de mana, adus la valori pe care nucleul le primeste.
    Intoarce (tp, note, eroare, de_ales):
      eroare  = text pentru utilizator cand nu se poate cauta deloc (tp e atunci None);
      de_ales = [(text, (modulatie, fec))] cand e DVB-S2 fara FEC sau modulatie reala si transponderul nu e
                in satellites.xml; utilizatorul alege, nu se mai trimite Auto."""
    note = []
    frecventa, sr = _int(c.get('frecventa'), 0), _int(c.get('sr'), 0)
    if frecventa <= 0 or sr <= 0:
        return None, note, _('Introdu frecvența (MHz) și rata de simbol (kSymb/s) ale transponderului.'), None
    if not SR_MIN <= sr * 1000 <= SR_MAX:
        # inainte de alegerea FEC-ului: altfel o rata gresita la DVB-S2 ar fi cerut FEC-ul, nu ar fi spus ce e gresit
        return None, note, _('Nu se poate căuta: %s.') % _rata_refuzata(sr * 1000), None
    sistem = _int(c.get('sistem'), SISTEM_DVB_S2)
    if sistem in (3, 4):
        return None, note, _('%s: tunerul acestui receptor nu are demodulator pentru acest sistem. '
                             'Alege DVB-S sau DVB-S2.') % ('TURBO FEC' if sistem == 3 else 'ISDB-S'), None
    if sistem == 2:
        sistem = SISTEM_DVB_S2
        note.append(_('DVB-S2X se caută ca DVB-S2.'))
    if sistem not in (SISTEM_DVB_S, SISTEM_DVB_S2):
        return None, note, _('Sistem necunoscut (%s). Alege DVB-S sau DVB-S2.') % c.get('sistem'), None
    pol = _int(c.get('pol'), 0)
    if pol not in (0, 1, 2, 3):
        return None, note, _('Polarizare necunoscută (%s).') % c.get('pol'), None
    tp = {'frequency': frecventa * 1000, 'symbol_rate': sr * 1000,     # MHz -> kHz, kSymb/s -> Symb/s
          'polarisation': pol, 'fec': _int(c.get('fec'), 0), 'inversion': _int(c.get('inversare'), 2),
          'orbital_position': _int(c.get('pozitie'), 192), 'system': sistem,
          'modulation': _int(c.get('mod'), 0), 'rolloff': _int(c.get('rolloff'), 0), 'pilot': _int(c.get('pilot'), 2)}
    if tp['inversion'] not in (0, 1, 2):
        tp['inversion'] = 2
    if tp['pilot'] not in (0, 1, 2):
        tp['pilot'] = 2
    if tp['rolloff'] not in ROLLOFF_VALIDE:
        tp['rolloff'] = 0
        note.append(_('Factorul de rotunjire ales nu e primit de tuner, s-a folosit 0,35.'))
    if _da(c.get('multistream')):
        text_isi = str(c.get('is_id') if c.get('is_id') is not None else '').strip()
        isi = _int(text_isi, -2) if text_isi else -1
        if not -1 <= isi <= ISI_MAX:
            return None, note, _('Fluxul (ISI) e un număr între 0 și %d. Lasă-l gol dacă știi numai codul PLS.') \
                % ISI_MAX, None
        mod = _int(c.get('pls_mod'), 1)
        if mod not in (0, 1, 2):
            mod = 1
        cod = _int(c.get('pls_cod'), 0)
        if not 0 <= cod <= PLS_COD_MAX:
            return None, note, _('Codul PLS e un număr între 0 și %d.') % PLS_COD_MAX, None
        tp.update(is_id=isi, pls_mode=mod, pls_code=cod)
        if not are_multistream(tp):
            note.append(_('Multistream fără flux și fără cod PLS: se caută ca un transponder obișnuit.'))
        elif sistem == SISTEM_DVB_S:
            sistem = tp['system'] = SISTEM_DVB_S2
            note.append(_('Multistream există numai în DVB-S2: se caută ca DVB-S2.'))
    if sistem == SISTEM_DVB_S:
        if tp['fec'] not in FEC_DVBS:
            tp['fec'] = 0
        if tp['modulation'] not in MOD_DVBS:
            tp['modulation'] = 1
    gasit = _cauta_in_xml(tp['frequency'], pol, transpondere_xml)
    fluxuri = _fluxuri_in_xml(tp['frequency'], pol, transpondere_xml)
    if fluxuri and not are_multistream(tp):
        if len(fluxuri) == 1:
            tp.update(fluxuri[0])
            if sistem == SISTEM_DVB_S:
                sistem = tp['system'] = SISTEM_DVB_S2
            note.append(_('Fluxul și secvența PLS sunt luate din lista receptorului: %s.') % text_multistream(tp))
        else:
            note.append(_('Pe %d MHz lista receptorului are mai multe fluxuri (%s); se caută fără să se aleagă unul. '
                          'Pentru unul anume pune „Multistream” pe Da și scrie fluxul.')
                        % (frecventa, ', '.join(text_multistream(f) for f in fluxuri)))
    lipsa = tp['fec'] == 0 or (sistem == SISTEM_DVB_S2 and motiv_refuz(tp) is not None)
    if gasit is None:
        note.append(_('%d MHz nu e în lista receptorului pentru acest satelit, se caută cu valorile introduse.')
                    % frecventa)
    elif lipsa:
        proba = dict(tp, system=gasit[5], fec=gasit[4], modulation=gasit[6],
                     rolloff=gasit[8] if gasit[8] in ROLLOFF_VALIDE else 0,
                     pilot=gasit[9] if gasit[9] in (0, 1, 2) else 2)
        if motiv_refuz(proba) is None:
            tp = proba
            note.append(_('Sistemul, FEC-ul și modulația sunt luate din lista receptorului: %s.') % _descriere_tp(tp))
    if tp['system'] == SISTEM_DVB_S2 and motiv_refuz(tp) is not None:
        potrivite = [(m, f) for m, f in COMBINATII_DVBS2
                     if (tp['modulation'] not in MOD_DVBS2 or m == tp['modulation'])
                     and (tp['fec'] not in FEC_DVBS2 or f == tp['fec'])] or list(COMBINATII_DVBS2)
        de_ales = [('%s %s' % (_nume_valoare(MODULATII, m), _nume_valoare(FEC_VALORI, f)), (m, f)) for m, f in potrivite]
        return tp, note, None, de_ales
    return tp, note, None, None


def text_manual(tp, nume, note):
    """Ce se cauta la „Cu date introduse manual": previzualizare si stare, inainte si dupa pornire (P11)."""
    text = _('Căutare pe transponderul %s, satelitul %s.') % (_descriere_tp(tp), nume) + ' ' + \
        _('Numai acest transponder.')
    if note:
        text += ' ' + ' '.join(note)
    return text


def in_parametri(clasa, tp):
    """dict -> eDVBFrontendParametersSatellite; clasa se primeste ca proba sa poata folosi una simulata."""
    parm = clasa()
    for camp, valoare in tp.items():
        setattr(parm, camp, valoare)
    return parm


# ---------------------------------------------------------------- tunerul si antena
def _nimmanager(nim=None):
    if nim is not None:
        return nim
    try:
        from Components.NimManager import nimmanager
        return nimmanager
    except Exception as e:
        print('[ScanerSatelit] NimManager nu se poate citi: %s' % e)
        return None


def slot_satelit(nim):
    """Primul tuner de satelit (pe Viper 4K V20 e unul singur), sau None."""
    for n in nim.nim_slots:
        if n.isCompatible('DVB-S'):
            return n.slot
    return None


def sateliti_tuner(nim, slot):
    """[(pozitie, nume)]: satelitii pe care ii vede antena acestui tuner. Cu motor sunt toti din satellites.xml."""
    try:
        return [(x[0], nume_satelit(x[0], x[1])) for x in nim.getSatListForNim(slot) or []]
    except Exception as e:
        print('[ScanerSatelit] eroare la citirea satelitilor configurati: %s' % e)
        return []


def are_motor(nim, slot):
    """Tunerul are motor (poziționer USALS sau DiSEqC 1.2): NimManager.getRotorSatListForNim nu e gol."""
    try:
        return bool(nim.getRotorSatListForNim(slot))
    except Exception:
        return False


def _text_motor(motor, orbpos):
    return (' ' + _('Antena se rotește singură spre %s.') % text_pozitie(orbpos)) if motor else ''


def _pozitie_nevazuta(orbpos, sateliti, motor, ce, fel_json=None, multistream=False):
    """Textul pentru utilizator cand pozitia ceruta nu e pe tuner, sau None cand se poate cauta de acolo.
    Cu antena fixa se spune ce vede antena si ce operatori de acelasi fel sunt acolo (cei multistream numai daca
    tunerul poate alege fluxul)."""
    pozitii = [p for p, n in sateliti]
    if orbpos in pozitii:
        if motor:
            # cu motorul USALS antena se roteste dupa locul antenei (Components/HdsLocul.py); nestabilit = refuz clar
            try:
                from Components import HdsLocul
                if HdsLocul.blocatDeLoc(orbpos):
                    return _(HdsLocul.MESAJ_FARA_LOC)
            except Exception as e:
                print('[ScanerSatelit] locul antenei nu se poate citi: %s' % e)
        return None
    if not pozitii:
        return _('Tunerul de satelit nu are niciun satelit configurat. Configurează antena în „Setări tuner”, '
                 'apoi revino aici.')
    if motor:
        return _('%s se află pe %s, dar poziția aceasta nu e în lista motorului. Adaug-o în „Setări tuner”.') % (
            ce, text_pozitie(orbpos))
    text = _('Antena ta e fixă și vede numai: %s. %s se află pe %s, deci de aici nu se poate căuta.') % (
        ', '.join(text_pozitie(p) for p in pozitii), ce, text_pozitie(orbpos))
    if fel_json:
        # numai cei care se pot cauta: cei cu multistream cer un tuner care alege fluxul (mesaj_multistream)
        acolo = [o['nume'] for o in operatori(fel_json) if o['pozitie'] in pozitii
                 and (multistream or not o['cere_multistream'])]
        if acolo:
            text += ' ' + _('Pe pozițiile antenei tale sunt: %s.') % ', '.join(acolo)
        else:
            text += ' ' + _('Pe pozițiile antenei tale nu e niciun operator de acest fel care să se '
                            'poată căuta acum.')
    return text


# felurile care pot purta in data/menu.xml semnul „(în lucru)”: pagina web a intrarii (cheia din stariWeb)
PAGINI_IN_LUCRU = {'dvbt2': '/scanare/satelit/dvbt2', 'dab': '/scanare/satelit/dab'}


def text_in_lucru(fel, cale_meniu=None):
    """Felurile care au in data/menu.xml semnul „(în lucru)” (stare="in-lucru") spun pe ecran si in web de ce. Textul
    se ia din starea intrarii, deci dispare singur cand semnul se scoate din menu.xml. Fara stare: ''."""
    pagina = PAGINI_IN_LUCRU.get(fel)
    if pagina is None:
        return ''
    try:
        from Components import HdsStareMeniu
        if cale_meniu is None:
            from Tools.Directories import resolveFilename, SCOPE_SKIN
            cale_meniu = resolveFilename(SCOPE_SKIN, 'menu.xml')
        if HdsStareMeniu.stariWeb(cale_meniu).get(pagina) != 'in-lucru':
            return ''
    except Exception as e:
        print('[ScanerSatelit] starea din menu.xml nu se poate citi: %s' % e)
    if fel == 'dab':
        # posturile se gasesc si se salveaza; redarea lor (servicemp3) nu are pe receptor decodor pentru sunetul DAB+
        return _('În lucru: scanarea salvează posturile DAB+ în lista de canale, dar ascultarea lor nu merge încă '
                 'pe acest receptor.')
    return _('În lucru: scanarea și ascultarea DVB-T2 prin satelit nu au fost încă probate pe receptor.')


def mesaj_multistream(nume):
    """Operatorii cu mai multe fluxuri pe transponder (is_id / PLS), cand tunerul de satelit nu poate alege fluxul
    (tuner_multistream). Se spune limpede, pe operator, nu se porneste o cautare care n-ar gasi nimic."""
    return _('%s: emisie în multistream (mai multe fluxuri pe același transponder), iar tunerul de satelit al acestui '
             'receptor nu poate alege fluxul. De aici nu se poate căuta; operatorii fără multistream din listă merg.') \
        % nume


def pregateste(fel, valori, nim=None):
    """Ce se cere nucleului pentru un fel de scanare, fara niciun ecran (il folosesc si ecranul, si web-ul).

    valori: "pozitie" (0..3599), "transponder" (cheie_tp), "retea" (da/nu), "pozitii" (lista, la mai_multi),
    "operator" (id din operatori-satelit.json) si, la manual, campurile ecranului (frecventa in MHz, sr in kSymb/s,
    pol, fec, mod, sistem, rolloff, pilot, inversare).
    Intoarce:
      scanare DVB:  {"fel", "slot", "motor", "transpondere": [dict tp], "flags", "text"}, pornita cu
                    ServiceScan, [{"transponders": [in_parametri(...)], "feid": slot, "flags": flags}];
      dvbt2 / dab:  {"fel", "slot", "motor", "hdscomun": tp in formatul HdsComun, "profil": "t2" / "dab", "text"};
      manual fara FEC sau modulatie la DVB-S2: {"fel", "slot", "motor", "de_ales", "transponder", "note", "text"};
      refuz:        {"eroare": text pentru utilizator}."""
    valori = valori or {}
    if fel not in CHEI_FELURI:
        return {'eroare': _('Fel de scanare necunoscut: %s.') % fel}
    nim = _nimmanager(nim)
    if nim is None:
        return {'eroare': _('Lista tunerelor nu se poate citi.')}
    slot = slot_satelit(nim)
    if slot is None:
        return {'eroare': _('Niciun tuner de satelit disponibil.')}
    sateliti = sateliti_tuner(nim, slot)
    motor = are_motor(nim, slot)
    ms = tuner_multistream(nim, slot)
    baza = {'fel': fel, 'slot': slot, 'motor': motor}
    try:
        from enigma import eComponentScan
        retea = eComponentScan.scanNetworkSearch
    except Exception:
        retea = 1                                  # lib/dvb/scan.h: scanNetworkSearch = 1

    if fel == 'mai_multi':
        # T4: aceeasi pozitie venita de mai multe ori (o cerere web facuta de mana) se cauta o singura data
        pozitii = []
        for p in valori.get('pozitii') or []:
            p = _int(p, None)
            if p not in pozitii:
                pozitii.append(p)
        if not pozitii:
            return {'eroare': _('Bifează cel puțin un satelit.')}
        tps, sarite = [], 0
        for p in pozitii:
            eroare = _pozitie_nevazuta(p, sateliti, motor, _('Satelitul ales'))
            if eroare:
                return {'eroare': eroare}
            bune, rele = transpondere_satelit(p, nim.getTransponders(p), ms)
            tps += bune
            sarite += len(rele)
        if not tps:
            return {'eroare': _('Sateliții aleși nu au în lista receptorului niciun transponder pe care tunerul '
                                'să-l primească.')}
        text = _('Căutare pe %d sateliți: %d transpondere din lista receptorului, plus cele anunțate în semnal.') % (
            len(pozitii), len(tps))
        if sarite:
            text += ' ' + _('Sărite %d, cu parametri pe care tunerul nu îi primește.') % sarite
        return dict(baza, transpondere=tps, flags=retea, text=text)

    if fel in ('transponder', 'satelit', 'manual'):
        orbpos = _int(valori.get('pozitie'), None)
        if orbpos is None:
            return {'eroare': _('Alege un satelit din listă.')}
        eroare = _pozitie_nevazuta(orbpos, sateliti, motor, _('Satelitul ales'))
        if eroare:
            return {'eroare': eroare}
        nume = dict(sateliti).get(orbpos) or text_pozitie(orbpos)
        transpondere_xml = nim.getTransponders(orbpos)
        if fel == 'satelit':
            bune, sarite = transpondere_satelit(orbpos, transpondere_xml, ms)
            if not bune:
                if sarite:
                    return {'eroare': _('Satelitul %s are %d transpondere în lista receptorului, dar niciunul cu '
                                        'parametri pe care tunerul îi primește (%s). Nu am ce căuta.')
                            % (nume, len(sarite), sarite[0][1])}
                return {'eroare': _('Satelitul %s nu are niciun transponder în lista receptorului, deci nu am ce '
                                    'căuta. Alege alt satelit sau caută cu date introduse manual.') % nume}
            text = _('Căutare pe tot satelitul %s: %d transpondere din lista receptorului, plus cele anunțate în '
                     'semnal.') % (nume, len(bune))
            if sarite:
                text += ' ' + _('Sărite %d, cu parametri pe care tunerul nu îi primește.') % len(sarite)
            return dict(baza, transpondere=bune, flags=retea, text=text + _text_motor(motor, orbpos))
        if fel == 'transponder':
            bune, sarite = transpondere_satelit(orbpos, transpondere_xml, ms)
            if not bune:
                return {'eroare': _('Satelitul %s nu are în lista receptorului niciun transponder pe care tunerul '
                                    'să-l primească. Caută cu date introduse manual.') % nume}
            tp = None
            for t in bune:
                if cheie_tp(t) == valori.get('transponder'):
                    tp = t
                    break
            if tp is None:
                return {'eroare': _('Alege un transponder din lista satelitului %s.') % nume}
            cu_retea = _da(valori.get('retea'))
            text = _('Căutare pe transponderul %s, satelitul %s.') % (_descriere_tp(tp), nume) + ' '
            text += _('Se adaugă și transponderele anunțate în semnal.') if cu_retea \
                else _('Numai acest transponder.')
            return dict(baza, transpondere=[tp], flags=retea if cu_retea else 0, text=text + _text_motor(motor, orbpos))
        tp, note, eroare, de_ales = transponder_manual(valori, transpondere_xml)
        if eroare:
            return {'eroare': eroare}
        if are_multistream(tp) and not ms:
            return {'eroare': _('Transponderul are multistream (%s), iar tunerul de satelit al acestui receptor nu '
                                'poate alege fluxul.') % text_multistream(tp)}
        if de_ales:
            text = _('%s: la DVB-S2 FEC-ul nu poate fi Auto, iar transponderul nu e în lista receptorului. Alege '
                     'modulația și FEC-ul.') % ('%d %s %d' % (tp['frequency'] // 1000, 'HVLR'[tp['polarisation']],
                                                           tp['symbol_rate'] // 1000))
            return dict(baza, de_ales=de_ales, transponder=tp, note=note, text=text)
        text = text_manual(tp, nume, note)
        return dict(baza, transpondere=[tp], flags=0, note=note, text=text + _text_motor(motor, orbpos))

    # operator, dvbt2, dab: un operator din data/operatori-satelit.json
    fel_json = FEL_JSON[fel]
    op = operator_dupa_id(valori.get('operator'))
    if op is None or op.get('fel') != fel_json:
        return {'eroare': _('Alege un operator din listă.')}
    # intai ce vede antena: cu antena fixa pe 19,2E, mesajul despre multistream (Cipru) n-ar spune de ce nu se
    # poate cauta
    eroare = _pozitie_nevazuta(op['pozitie'], sateliti, motor, op['nume'], fel_json, ms)
    if eroare:
        return {'eroare': eroare}
    if op['cere_multistream'] and not ms:
        return {'eroare': mesaj_multistream(op['nume'])}
    tp = transponder_nucleu(op)
    motiv = motiv_refuz(tp)
    if motiv:
        return {'eroare': _('Transponderul operatorului %s nu poate fi acordat: %s.') % (op['nume'], motiv)}
    baza['operator'] = op['id']
    if fel == 'operator':
        text = _('Căutare după operator: %s, pe %s. Se pornește de la transponderul %s, restul vin din ce anunță '
                 'operatorul în semnal.') % (op['nume'], text_pozitie(op['pozitie']), _descriere_tp(tp))
        return dict(baza, transpondere=[tp], flags=retea, text=text + _text_motor(motor, op['pozitie']))
    hds = transponder_hdscomun(op)
    if fel == 'dvbt2':
        text = _('DVB-T2 prin satelit: %s, pe %s. Se acordează transponderul %s și se caută fluxurile DVB-T2.')
    else:
        text = _('DAB+ prin satelit: %s, pe %s. Se acordează transponderul %s și se caută radiourile DAB+.')
    # numele fara felul din fata lui („DAB+ prin satelit - "): textul incepe deja cu felul
    text = text % (nume_fara_fel(op), text_pozitie(op['pozitie']), _descriere_hdscomun(hds))
    # unde se roteste antena (de pe ce pozitie, cat dureaza, daca ramane) spune planul (plan_fluxuri), pe ecranul
    # scanarii si in pagina: aici fara „Antena se rotește singură", care ar fi gresit cand antena e deja acolo
    return dict(baza, hdscomun=hds, profil=PROFIL_FEL[fel], text=text)


# ---------------------------------------------------------------- DVB-T2 si DAB+ prin satelit
def profil_hdscomun(tip):
    """(Profil, dosarul cu motor/ si date/) pentru DAB+ ('dab') sau DVB-T2, din Hds/DabT2 (codul imaginii)."""
    from Hds.DabT2 import imagine, profil
    if tip == 'dab':
        return profil.DAB, imagine.cale_pentru('dab')
    return profil.T2, imagine.cale_pentru('t2')


# Cat dureaza, spus pe ecran inainte de pornire (pasii masurati pe receptor: acordul dupa asezarea antenei,
# detectorul, releul)
TIMP_ACORD_S = 5            # prinderea semnalului dupa ce antena s-a oprit
TIMP_DETECTOR_T2_S = 10     # la DVB-T2 detectorul citeste numai PAT si PMT (pachetele T2-MI vin prin portul 8001)
TIMP_INVATARE_S = 45        # lista programelor prin releu: pornirea lui + Hds/DabT2/pornire.TERMEN_RELEU_S
INVATARI_MAX = 4            # cate feed-uri se invata prin releu la o scanare, pe rand (tunerul e unul)
ROTIRE_NECUNOSCUTA_S = 25   # tuner.secunde_asezare(40 de grade): cand nu se stie de unde pleaca antena


def ngettext(unu, multe, n):
    """Pluralul tradus (Components/HdsListeCabluTerestru.ngettext, cu formele limbii alese); fara el (pe PC), dupa
    regula romaneasca, fiindca msgid-urile sunt in romana."""
    try:
        from Components.HdsListeCabluTerestru import ngettext as plural
        return plural(unu, multe, n)
    except Exception:
        return unu if n == 1 else multe


def text_durata(secunde):
    """„30 de secunde", „un minut", „2 minute"; secundele rotunjite la 5."""
    if secunde < 55:
        n = max(5, int(round(secunde / 5.0)) * 5)
        return ngettext('%d secundă', '%d secunde', n) % n
    if secunde < 90:
        return _('un minut')
    m = int(round(secunde / 60.0))
    return ngettext('%d minut', '%d minute', m) % m


def text_scurs(secunde):
    """Timpul trecut de la pornire, exact: „12 secunde", „1 min 05 s"."""
    secunde = max(0, int(secunde))
    if secunde < 60:
        return ngettext('%d secundă', '%d secunde', secunde) % secunde
    return _('%d min %02d s') % (secunde // 60, secunde % 60)


def pozitie_curenta(sesiune):
    """De unde pleaca antena: pozitia transponderului serviciului care ruleaza, altfel ultima pozitie a motorului
    (config.misc.lastrotorposition), altfel None (nu se stie)."""
    try:
        from Hds.DabT2 import scanare as hds_scanare
        tp = hds_scanare.transponder_curent(sesiune)
        if tp:
            p = _int(tp.get('pozitie'), None)
            if p is not None:
                return p
    except Exception as e:
        print('[ScanerSatelit] pozitia serviciului curent: %s' % e)
    try:
        from Components.config import config
        p = _int(config.misc.lastrotorposition.value, None)
        if p is not None and 0 <= p < 3600:
            return p
    except Exception:
        pass
    return None


def nume_pozitie(orbpos):
    """„23,5°E Astra 3C" din satelitii tunerului de satelit; fara nume, numai pozitia."""
    nim = _nimmanager()
    if nim is not None:
        try:
            slot = slot_satelit(nim)
            if slot is not None:
                nume = dict(sateliti_tuner(nim, slot)).get(orbpos)
                if nume:
                    return nume
        except Exception as e:
            print('[ScanerSatelit] numele satelitului %s: %s' % (orbpos, e))
    return text_pozitie(orbpos)


def plan_fluxuri(rez, sesiune=None, de_la=None):
    """Ce se intampla la o scanare DVB-T2 / DAB+ prin satelit, spus inainte de pornire (ecranul si pagina web).
    rez = pregateste('dvbt2' / 'dab', ...); de_la = pozitia de pe care pleaca antena (implicit pozitie_curenta).
    -> {'la', 'de_la', 'motor', 'rotire_s' (0 = fara rotire), 'rotire_stiuta', 'scanare_s', 'are_canal',
        'randuri': [(eticheta, valoare)], 'text'}"""
    tp = rez.get('hdscomun') or {}
    la = _int(tp.get('pozitie'), None)
    motor = bool(rez.get('motor'))
    dab = rez.get('profil') == 'dab'
    if de_la is None and sesiune is not None:
        de_la = pozitie_curenta(sesiune)
    are_canal = False
    if sesiune is not None:
        try:
            are_canal = sesiune.nav.getCurrentlyPlayingServiceReference() is not None
        except Exception:
            are_canal = False
    rotire, stiuta = 0, True
    if motor:
        if de_la is None:
            rotire, stiuta = ROTIRE_NECUNOSCUTA_S, False
        elif de_la != la:
            from Hds.DabT2 import tuner as hds_tuner
            rotire = hds_tuner.secunde_asezare(hds_tuner.arc_grade(de_la, la))
    try:
        from Hds.DabT2 import scanare as hds_scanare
        detector = int(getattr(hds_scanare, 'TIMP_DETECTOR_S', 25))
    except Exception:
        detector = 25
    scanare_s = TIMP_ACORD_S + (detector if dab else TIMP_DETECTOR_T2_S + TIMP_INVATARE_S)
    poz_la = text_pozitie(la)
    if not motor:
        antena = _('fixă, fără rotire')
        text = _('Antena ta e fixă: tunerul trece pe %s, fără rotire.') % poz_la
    elif not stiuta:
        antena = _('se rotește spre %s, până la %s') % (poz_la, text_durata(rotire))
        text = _('Antena se rotește spre %s (până la %s).') % (poz_la, text_durata(rotire))
    elif rotire:
        antena = _('se rotește de pe %s, cam %s') % (text_pozitie(de_la), text_durata(rotire))
        text = _('Antena se rotește de pe %s pe %s (cam %s).') % (text_pozitie(de_la), poz_la, text_durata(rotire))
    else:
        antena = _('rămâne pe %s') % poz_la
        text = _('Antena e deja pe %s.') % poz_la
    text += ' ' + (_('Apoi caut radiourile DAB+ și le salvez (cam %s).') if dab else
                   _('Apoi caut programele DVB-T2 și le salvez (cam %s).')) % text_durata(scanare_s)
    if are_canal and motor and rotire and stiuta:
        text += ' ' + _('La sfârșit alegi: pornești ce am găsit (antena rămâne pe %s) sau te întorci la canalul '
                        'tău (antena revine pe %s).') % (poz_la, text_pozitie(de_la))
    elif are_canal:
        text += ' ' + _('La sfârșit alegi: pornești ce am găsit sau te întorci la canalul tău.')
    else:
        text += ' ' + _('La sfârșit alegi ce pornești din ce am găsit.')
    # unde raman, spus inainte: lista de canale, buchetul felului
    text += ' ' + (_('Ce găsesc rămâne în lista de canale, la Radio.') if dab else
                   _('Ce găsesc rămâne în lista de canale, la TV.'))
    randuri = []
    op = operator_dupa_id(rez.get('operator')) if rez.get('operator') else None
    if op is not None:
        randuri.append((_('Operator'), nume_fara_fel(op)))
    randuri += [(_('Satelitul'), nume_pozitie(la)),
                (_('Transponderul'), _descriere_hdscomun(tp)),
                (_('Antena'), antena),
                (_('Durează'), _('cam %s') % text_durata(scanare_s + rotire))]
    return {'la': la, 'de_la': de_la, 'motor': motor, 'rotire_s': rotire, 'rotire_stiuta': stiuta,
            'scanare_s': scanare_s, 'are_canal': are_canal, 'randuri': randuri, 'text': text}


def buchet_in_sateliti(buchet):
    """Buchetul DAB+ / DVB-T2 din satelit are dosar in lista „Sateliți” (exista si e trecut in bouquets.*)."""
    try:
        from Components import HdsIndexCanale as X
        lista = 'radio' if buchet.endswith('.radio') else 'tv'
        return any(f == buchet for _fel, f in X.buchete_fluxuri(lista))
    except Exception as e:
        print('[ScanerSatelit] buchetele din Sateliti: %s' % e)
        return False


def porneste_postul(sesiune, ref_text, buchet, radio):
    """Porneste un post gasit la scanare prin lista de canale, in buchetul lui („DAB+ din satelit" la Radio,
    „DVB-T2 din satelit" la TV), ca lista si CH+/CH- sa mearga de acolo mai departe. Cu radioul in lista lui
    separata (usage.e1like_radio_mode oprit) postul porneste direct, iar lista radio tine minte buchetul si postul
    (config.radio.lastroot / lastservice), deci tasta RADIO o deschide acolo. Orice piedica in lista (editare,
    buchet inca nereincarcat) lasa pornirea directa. -> (True, None) sau (False, motivul)."""
    from enigma import eServiceReference
    ref = eServiceReference(ref_text)
    if not ref.valid():
        return False, _('Postul nu are o referință bună.')
    tip_index = 2 if radio else 1
    bref_text = '1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (tip_index, buchet)
    sl, separat, multibuchet, config = None, bool(radio), False, None
    try:
        from Components.config import config
        separat = bool(radio) and not config.usage.e1like_radio_mode.value
        multibuchet = bool(config.usage.multibouquet.value)
        from Screens.InfoBar import InfoBar
        ib = InfoBar.instance
        sl = getattr(ib, 'servicelist', None) if ib is not None else None
    except Exception as e:
        print('[ScanerSatelit] lista de canale: %s' % e)
    if radio and config is not None:
        # locul din lista radio: postul si buchetul lui. Tine si pentru lista TV cu radioul in ea: setModeRadio()
        # porneste singur ultimul post de radio, deci trebuie sa fie acesta, nu unul de pe alt satelit
        try:
            config.radio.lastservice.value = ref_text
            config.radio.lastservice.save()
            radacina = None
            if multibuchet:
                radacina = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.radio" ORDER BY bouquet'
            elif buchet_in_sateliti(buchet):
                # „mai multe buchete” oprit: buchetul sta ca dosar in „Sateliți” (ChannelSelection.hdsAdaugaBucheteFluxuri)
                from Screens.ChannelSelection import service_types_radio
                radacina = '%s FROM SATELLITES ORDER BY satellitePosition' % service_types_radio
            if radacina is not None:
                config.radio.lastroot.value = '%s;%s;' % (radacina, bref_text)
                config.radio.lastroot.save()
        except Exception as e:
            print('[ScanerSatelit] locul din lista radio: %s' % e)
    if separat or sl is None:
        sesiune.nav.playService(ref)
        return True, None
    try:
        from Screens import ChannelSelection as CS
        if not sl.movemode and sl.bouquet_mark_edit == CS.OFF:
            if radio:
                if sl.mode != CS.MODE_RADIO:
                    sl.setModeRadio()
            elif sl.mode != CS.MODE_TV:
                sl.setModeTv()
            if multibuchet:
                sl.clearPath()
                sl.enterPath(sl.bouquet_root)
                sl.enterPath(eServiceReference(bref_text))
            elif buchet_in_sateliti(buchet):
                sl.hdsDeschideSateliti()
                intrare = sl.hdsIntrareSatelit(ref)
                if intrare is not None:
                    sl.enterPath(intrare)
            sl.setCurrentSelection(ref)
            ales = sl.getCurrentSelection()
            if ales is not None and ales.valid() and ales == ref:
                sl.zap()
                return True, None
    except Exception as e:
        print('[ScanerSatelit] pornirea prin lista de canale: %s' % e)
    sesiune.nav.playService(ref)
    return True, None


# codurile erorilor de sistem (errno) spuse pe intelesul oricui; restul, 'eroare neasteptata'
_ERRNO_PLIN = (28, 122)            # ENOSPC, EDQUOT
_ERRNO_NESCRIS = (1, 13, 30)       # EPERM, EACCES, EROFS


def motiv_eroare(eroare):
    """Motivul unei erori, pentru om, intr-o fraza scurta fara textul tehnic: dupa codul erorii de sistem, cand se
    stie (din exceptie sau din textul 'OSError: [Errno 28] ...' pe care il da firul de fundal, Hds/DabT2/fundal.py).
    Textul intreg al erorii il scrie apelantul in jurnal."""
    cod = getattr(eroare, 'errno', None)
    if not isinstance(cod, int):
        gasit = re.search('Errno ([0-9]+)', '%s' % (eroare,))
        cod = int(gasit.group(1)) if gasit else None
    if cod in _ERRNO_PLIN:
        return _('Memoria receptorului e plină.')
    if cod in _ERRNO_NESCRIS:
        return _('Memoria receptorului nu se poate scrie acum.')
    return _('Eroare neașteptată în receptor; detaliile sunt în jurnal.')


def _tuner_ocupat(mesaj):
    """Acordul a cazut pentru ca tunerul de satelit e folosit de altceva (motivul dat de Hds/DabT2/tuner.py)."""
    try:
        from Hds.DabT2.limba import _ as tradu
        return mesaj in ('tunerul de satelit e ocupat', tradu('tunerul de satelit e ocupat'))
    except Exception:
        return mesaj == 'tunerul de satelit e ocupat'


def _fara_semnal(mesaj):
    """Acordul a cazut pentru ca nu a venit semnal (motivul dat de Hds/DabT2/tuner.py: 'nu vine semnal pe ...')."""
    inceput = 'nu vine semnal'
    try:
        from Hds.DabT2.limba import _ as tradu
        tradus = tradu('nu vine semnal pe %s').split('%s')[0].strip()
    except Exception:
        tradus = inceput
    text = '%s' % (mesaj or '',)
    return text.startswith(inceput) or (bool(tradus) and text.startswith(tradus))


class CautareFluxuri(object):
    """Felurile 6 si 7. DVB-T2 si DAB+ prin satelit nu se gasesc cu o scanare DVB (ServiceScan): fluxurile stau in
    pachete T2-MI sau ETI/EDI pe un transponder purtator. Pasii (`faza`):
      acord      tunerul acordeaza purtatorul (canal brut; cu motor antena se roteste, Hds/DabT2/tuner.py);
      detector   detectorul citeste demux-ul (Hds/DabT2/scanare.py, detector.py): ansamblurile EDI cu posturile
                 din FIC; la DVB-T2 si la DAB ETI numai PAT si PMT (pachetele lor vin pe receptor doar prin 8001);
      salvare    in fundal, sub zavorul scrierilor: scanate.json, posturile in servicii.json, buchetul
                 (scanare.salveaza_rezultatul);
      invatare   feed-urile fara lista de posturi (T2-MI, ETI, EDI necomplet) trec pe rand prin releu
                 (Controlor.invata), care scrie singur serviciile, buchetul si purtatorul din lamedb;
      gata / nimic / esuat   rezultatul; apoi `ales` (asculta sau inapoi) sau oprit (renuntare).
    Serviciul care rula se opreste la pornire (tunerul de satelit e unul singur; cu un canal pornit pe el alocarea ar
    cadea dupa 3 s cu „tunerul de satelit e ocupat") si NU se reporneste singur la sfarsit: asculta(i) porneste
    postul ales (antena ramane pe satelitul scanat), inapoi() porneste serviciul de dinainte (antena se intoarce).
    opreste() (iesire inainte de alegere) il reporneste.
    TUNERUL LA SFARSIT: cu posturi gasite („gata") cautarea tine tunerul acordat pe purtator pana la alegere. Liber,
    tunerul l-ar lua orice cerere (o sesiune a serverului local 8001, de pilda), care ar roti antena inapoi cat omul
    inca alege. Tunerul se da: sincron la asculta(i), chiar inainte de pornirea postului (acelasi transponder, fara
    rotire), la inapoi() / opreste(), la orice zap venit din alta parte (din web, din lista) si la o inregistrare
    adevarata, prin extensiile din Navigation puse numai cat il tine. Invatarea prin releu (T2-MI, ETI) are nevoie de
    tuner: inainte de ea se da, dupa ea se ia din nou.
    la_stare(text) si la_gata(ok, text, numar_posturi) raman pentru apelantii vechi; ecranele se inscriu in
    `ascultatori` (functii fara argumente, chemate la fiecare schimbare) si citesc rezumat()."""

    IN_CURS = ('acord', 'detector', 'salvare', 'invatare')

    def __init__(self, sesiune, profil_tip, tp, la_stare=None, la_gata=None, ref_inainte=None,
                 pozitie_inainte=None):
        self.sesiune = sesiune
        self.profil_tip = profil_tip
        self.tp = tp
        self._la_stare = la_stare
        self._la_gata = la_gata
        self.ascultatori = []
        self.tuner = None
        self.scanare = None
        self.faza = 'nepornit'
        self.text = ''
        self.gasite = []           # [{'id', 'nume', 'posturi': [{'sid', 'nume', 'fel', 'ref'}], 'stare', 'numar'}]
        self.raspuns = None        # raspunsul detectorului, pentru textul brut
        self.note = []             # ce n-a mers la invatare, pentru textul brut
        self.detaliu = ''          # la esec: detaliul tehnic scurt (codul detectorului, termenul), sub fraza simpla
        self.ref_inainte = ref_inainte
        self._serviciu_oprit = ref_inainte is not None
        self.pozitie = _int(tp.get('pozitie'), None)
        self.pozitie_inainte = pozitie_inainte
        self.satelit = text_pozitie(self.pozitie)
        self.ales = None
        self.inceput = None
        self.sfarsit = None
        self._de_invatat = []
        self._invat = None
        self._disc = None
        self._extensii = False

    def _felul(self):
        return _('DAB+') if self.profil_tip == 'dab' else _('DVB-T2')

    # ---- starea, pentru ecran si web
    def _anunta(self):
        for f in list(self.ascultatori):
            try:
                f()
            except Exception as e:
                print('[ScanerSatelit] ascultatorul cautarii: %s' % e)

    def _faza(self, faza, text):
        self.faza = faza
        self._stare(text)

    def _stare(self, text):
        self.text = text
        if self._la_stare is not None:
            self._la_stare(text)
        self._anunta()

    def in_curs(self):
        return self.faza in self.IN_CURS

    def posturi(self):
        """Posturile gasite, pe rand, cu grupa lor (ansamblul DAB sau multiplexul T2)."""
        rez = []
        for g in self.gasite:
            for p in g.get('posturi') or []:
                x = dict(p)
                x['grup'] = g['nume']
                rez.append(x)
        return rez

    def rezumat(self):
        """Tot ce arata ecranul si pagina web: faza, textul, satelitul, grupele gasite si posturile."""
        grupe = [{'nume': g['nume'], 'numar': len(g.get('posturi') or []) or g.get('numar') or 0,
                  'stare': g.get('stare')} for g in self.gasite]
        return {'faza': self.faza, 'text': self.text, 'fel': self.profil_tip, 'felul': self._felul(),
                'satelit': self.satelit, 'pozitie': text_pozitie(self.pozitie),
                'transponder': _descriere_hdscomun(self.tp),
                'pozitie_inainte': text_pozitie(self.pozitie_inainte) if self.pozitie_inainte is not None else '',
                'are_canal': self.ref_inainte is not None, 'ales': self.ales, 'grupe': grupe,
                'detaliu': self.detaliu if self.faza == 'esuat' else '',
                'posturi': [{'nume': p['nume'], 'fel': p.get('fel') or '', 'grup': p['grup']} for p in self.posturi()],
                'secunde': int((self.sfarsit or time.time()) - self.inceput) if self.inceput else 0}

    def text_brut(self):
        """Raspunsul detectorului si ce n-a mers la invatare, ca text (tasta ALBASTRA „Text brut"). Fara raspuns (tasta
        e numai la sfarsit, deci detectorul nu mai lucreaza): detaliul opririi (codul de iesire, termenul), ultimele
        randuri de pe stderr ale detectorului si inceputul iesirii care nu s-a putut citi (Hds/DabT2/scanare.py)."""
        parti = []
        if self.raspuns is not None:
            parti.append(json.dumps(self.raspuns, ensure_ascii=False, indent=1, sort_keys=True))
        else:
            parti.append(_('Detectorul nu a dat niciun răspuns.'))
            scanare = getattr(self, 'scanare', None)
            detaliu = getattr(self, 'detaliu', '')
            if detaliu:
                parti.append(detaliu)
            erori = getattr(scanare, 'erori_detector', None)
            if erori:
                parti.append(_('Ultimele rânduri de eroare ale detectorului:') + '\n' + '\n'.join(erori))
            necitit = getattr(scanare, 'necitit', '')
            if necitit:
                parti.append(_('Începutul ieșirii care nu s-a putut citi:') + '\n' + necitit)
        if self.note:
            parti.append('\n'.join(self.note))
        return '\n\n'.join(parti)

    # ---- pasii
    def porneste(self):
        from Hds.DabT2 import tuner as hds_tuner
        self.inceput = time.time()
        if not self._serviciu_oprit:
            if self.pozitie_inainte is None:
                self.pozitie_inainte = pozitie_curenta(self.sesiune)
            self._opreste_serviciul()
        try:
            self.satelit = nume_pozitie(self.pozitie)
        except Exception:
            pass
        self._cere_tunerul()
        self.tuner = hds_tuner.Tuner('scaner')
        self._faza('acord', _('Se acordează transponderul %s...') % _descriere_hdscomun(self.tp))
        return self.tuner.acordeaza(self.tp, self._acordat, self._stare)

    def _cere_tunerul(self):
        """Controlorii DAB+ / DVB-T2 care canta, invata sau tin sesiunea dau tunerul inapoi sincron, inaintea
        alocarii canalului brut. nav.stopService() nu trece prin extensiile de zap: fara cedare, un post DAB EDI sau un
        program DVB-T2 ar tine tunerul pana la paza controlorului (~10 s), iar alocarea renunta dupa ALOCARE_MAX_S."""
        try:
            from Hds.DabT2 import intrare
            for tip in ('dab', 't2'):
                profil, cale = profil_hdscomun(tip)
                c = intrare.controlor(profil, cale)
                if getattr(c, 'stare', 'oprit') != 'oprit':
                    c.cedeaza('scanare')
        except Exception as e:
            print('[ScanerSatelit] tunerul pentru scanare: %s' % e)

    def _acordat(self, ok, mesaj):
        if self.faza != 'acord':
            return
        if not ok:
            # motivul tunerului (Hds/DabT2/tuner.py) e scris pentru jurnal: pe ecran fraza simpla; un motiv altul decat
            # lipsa semnalului sau tunerul ocupat ramane dedesubt, cu litere mici (detaliu)
            print('[ScanerSatelit] acordul pe %s: %s' % (_descriere_hdscomun(self.tp), mesaj))
            if _tuner_ocupat(mesaj):
                text = _('Tunerul de satelit e folosit acum de altceva, de exemplu de o înregistrare. Încearcă din '
                         'nou după ce se termină.')
            elif _fara_semnal(mesaj) or not mesaj:
                text = _('Nu am recepționat semnal pe %s. Verifică antena și încearcă din nou.') % _descriere_hdscomun(self.tp)
            else:
                self.detaliu = '%s' % (mesaj,)
                text = _('Nu am putut porni tunerul pe %s. Încearcă din nou.') % _descriere_hdscomun(self.tp)
            self._termina('esuat', text)
            return
        from Hds.DabT2 import scanare as hds_scanare
        profil, cale = profil_hdscomun(self.profil_tip)
        self.scanare = hds_scanare.Scanare(profil, cale)
        self.faza = 'detector'
        try:
            pornit = self.scanare.porneste(self._detectat, self._progres)
        except TypeError:
            pornit = self.scanare.porneste(self._detectat)
        if not pornit:
            self._termina('esuat', _('Detectorul de fluxuri nu a pornit. Detalii în jurnal.'))
            return
        secunde = int(getattr(hds_scanare, 'TIMP_DETECTOR_S', 25))
        if self.profil_tip == 'dab':
            text = _('Semnal recepționat pe %s. Caut ansamblurile DAB+ și citesc lista posturilor, cel mult %s...')
        else:
            text = _('Semnal recepționat pe %s. Caut multiplexurile DVB-T2, cel mult %s...')
        self._stare(text % (_descriere_hdscomun(self.tp), text_scurs(secunde)))

    def _progres(self, x):
        """Un ansamblu gasit de detector cat inca lucreaza: apare pe ecran inainte de sfarsit."""
        if self.faza != 'detector' or not isinstance(x, dict):
            return
        nume = str(x.get('nume') or '').strip()
        if not nume or any(g['nume'] == nume for g in self.gasite):
            return
        self.gasite.append({'id': None, 'nume': nume, 'posturi': [], 'stare': 'gasit',
                            'numar': _int(x.get('posturi'), 0)})
        self._anunta()

    def _detectat(self, ok, rez):
        """Raspunsul detectorului. scanare._inchis inghite orice exceptie de aici, deci fara try o eroare la salvare
        ar lasa ecranul pe „Caut...", serviciul oprit si web-ul „in curs". _termina ruleaza oricum, o singura data."""
        if self.faza != 'detector':
            return
        try:
            self._dupa_detector(ok, rez)
        except Exception as e:
            print('[ScanerSatelit] dupa detector: %s' % e)
            if self.faza in ('detector', 'salvare'):
                self._esec_salvare(e)

    def _dupa_detector(self, ok, rez):
        # tunerul ramane acordat pe purtator cat se salveaza (antena nu pleaca); il da _termina la esec, invatarea
        # inainte de releu sau alegerea de la sfarsit
        self.raspuns = getattr(self.scanare, 'raspuns', None)
        if not ok:
            self.detaliu = getattr(self.scanare, 'detaliu', '') or ''
            self._termina('esuat', rez)
            return
        from Hds.DabT2 import fundal, intrare, pornire
        from Hds.DabT2 import scanare as hds_scanare
        profil, cale = profil_hdscomun(self.profil_tip)
        ctrl = intrare.controlor(profil, cale)
        cu_nedecodabile = False
        try:
            cu_nedecodabile = bool(ctrl._arata_nedecodabile())
        except Exception:
            pass
        candidati = (self.raspuns or {}).get('candidati') if isinstance(self.raspuns, dict) else None
        incorporat = os.path.join(cale, 'date', 'frecvente.json')
        self._faza('salvare', _('Salvez ce am găsit...'))
        self._disc = fundal.Fundal('scaner-disc')
        self._disc.lanseaza(pornire._sub_zavor, self._salvat, hds_scanare.salveaza_rezultatul, profil, self.tp,
                            rez or [], candidati, None, incorporat, cu_nedecodabile, INVATARI_MAX)

    def _salvat(self, ok, r):
        if self.faza != 'salvare':
            # oprita in timpul salvarii: firul a scris totusi buchetul; enigma2 trebuie sa-l citeasca din nou, altfel
            # lista arata buchetul vechi si o editare a lui (eBouquet::flushChanges) l-ar scrie peste cel nou
            if ok and isinstance(r, dict) and (r.get('buchet') or {}).get('schimbat'):
                try:
                    from Hds.DabT2 import buchete
                    buchete.reincarca_buchete()
                except Exception as e:
                    print('[ScanerSatelit] buchetul dupa oprire: %s' % e)
            return
        if not ok or not isinstance(r, dict):
            print('[ScanerSatelit] salvarea: %s' % (r,))
            self._esec_salvare(r)
            return
        try:
            from Hds.DabT2 import buchete, intrare
            profil, cale = profil_hdscomun(self.profil_tip)
            if (r.get('buchet') or {}).get('schimbat'):
                buchete.reincarca_buchete()
            intrare.controlor(profil, cale).lista(forteaza=True)
            self.gasite = [self._grupa(profil, feed, posturi) for feed, _tp, posturi in r.get('gasite') or []]
            self._de_invatat = list(r.get('de_invatat') or [])
        except Exception as e:
            print('[ScanerSatelit] dupa salvare: %s' % e)
            self._esec_salvare(e)
            return
        self._invata_urmatorul()

    def _esec_salvare(self, eroare):
        """Salvarea a cazut: pe ecran fraza simpla, dedesubt motivul spus simplu (motiv_eroare); textul tehnic al
        erorii ramane in jurnal si la textul brut (ALBASTRU)."""
        self.detaliu = motiv_eroare(eroare)
        self.note.append('%s' % (eroare,))
        self._termina('esuat', _('Ce am găsit nu s-a putut salva. Încearcă din nou.'))

    def _grupa(self, profil, feed, posturi):
        from Hds.DabT2 import buchete
        fid = buchete._curata_id(feed.get('id'))
        lista = []
        for s in posturi or []:
            if not isinstance(s, dict) or _int(s.get('sid'), 0) <= 0:
                continue
            if profil.tip == 'dab':
                ref = buchete.ref_dab(profil, fid, s['sid'])
                fel = s.get('fel') or 'DAB+'
            else:
                ref = buchete.ref_t2(profil, feed, s)
                fel = _('Radio') if _int(s.get('tip'), 1) in (2, 10) else _('TV')
            nume = ' '.join(str(s.get('nume') or fid).replace(':', ' ').split())
            lista.append({'sid': _int(s.get('sid'), 0), 'nume': nume, 'fel': fel, 'ref': ref})
        lista.sort(key=lambda p: (p['nume'].lower(), p['sid']))
        # acelasi nume pe mai multe servicii: SID-ul dupa nume, ca in buchet (buchete.nume_afisate)
        for p, nume in zip(lista, buchete.nume_afisate(lista)):
            p['nume'] = nume
            # referinta cu numele la capat, ca linia din buchet: un serviciu cu URL isi ia numele numai de aici
            # (fara el, bara si ecranul radio ar arata SID-ul)
            p['ref'] = '%s:%s' % (p['ref'], nume)
        return {'id': fid, 'nume': str(feed.get('nume') or fid), 'posturi': lista, 'stare': 'gata', 'numar': len(lista)}

    def _invata_urmatorul(self):
        if self.faza not in ('salvare', 'invatare'):
            return
        if not self._de_invatat:
            self._gata()
            return
        from Hds.DabT2 import buchete, intrare
        feed, tp, adaugat = self._de_invatat.pop(0)
        profil, cale = profil_hdscomun(self.profil_tip)
        fid = buchete._curata_id(feed.get('id'))
        nume = str(feed.get('nume') or fid)
        self._invat = (feed, tp, adaugat, fid)
        self.gasite.append({'id': fid, 'nume': nume, 'posturi': [], 'stare': 'invat', 'numar': 0})
        if self.profil_tip == 'dab':
            text = _('Citesc lista posturilor din %s (până la %s)...')
        else:
            text = _('Citesc lista programelor din %s (până la %s)...')
        self._faza('invatare', text % (nume, text_durata(TIMP_INVATARE_S)))
        self._elibereaza_tunerul()           # releul invatarii cere tunerul (canal brut sau sesiunea 8001)
        intrare.controlor(profil, cale).invata(feed, tp, self._invatat)

    def _invatat(self, ok, rez):
        if self.faza != 'invatare' or self._invat is None:
            return
        feed, _tp, adaugat, fid = self._invat
        self._invat = None
        grupa = next((g for g in self.gasite if g['id'] == fid and g['stare'] == 'invat'), None)
        try:
            from Hds.DabT2 import intrare
            profil, cale = profil_hdscomun(self.profil_tip)
            servicii = intrare.controlor(profil, cale).servicii_invatate(fid) if ok else []
            if ok and servicii and grupa is not None:
                grupa.update(self._grupa(profil, feed, servicii))
            else:
                if grupa is not None:
                    self.gasite.remove(grupa)
                self.note.append('%s: %s' % (feed.get('nume') or fid, rez if not ok else _('nicio listă')))
                if adaugat and self._disc is not None:
                    # candidatul pus in scanate.json inaintea invatarii nu a dat nimic: iese din lista
                    from Hds.DabT2 import liste, pornire
                    self._disc.lanseaza(pornire._sub_zavor, None, liste.scoate_scanat, profil.tip, feed.get('id'),
                                        profil.director)
        except Exception as e:
            print('[ScanerSatelit] dupa invatare: %s' % e)
        self._invata_urmatorul()

    def _gata(self):
        self.gasite = [g for g in self.gasite if g.get('posturi')]
        n = len(self.posturi())
        profil, _cale = profil_hdscomun(self.profil_tip)
        nume_buchet = _(profil.nume_buchet)
        if not n:
            if self.profil_tip == 'dab':
                text = _('Pe %s nu am găsit niciun post DAB+.') % _descriere_hdscomun(self.tp)
            else:
                text = _('Pe %s nu am găsit niciun program DVB-T2.') % _descriere_hdscomun(self.tp)
            text += ' ' + _('Verifică antena și semnalul sau încearcă alt operator. Poți adăuga fluxuri de mână în '
                            '„Fluxuri și setări”.')
            self._termina('nimic', text)
            return
        if self.profil_tip == 'dab':
            text = ngettext('Am găsit %d post DAB+.', 'Am găsit %d posturi DAB+.', n) % n
            text += ' ' + _('Rămân salvate în lista de canale, la Radio, în „%s”.') % nume_buchet
        else:
            text = ngettext('Am găsit %d program DVB-T2.', 'Am găsit %d programe DVB-T2.', n) % n
            text += ' ' + _('Rămân salvate în lista de canale, la TV, în „%s”.') % nume_buchet
        self._termina('gata', text)

    def _termina(self, faza, text):
        self.faza = faza
        self.sfarsit = time.time()
        if faza == 'gata':
            self._tine_tunerul()             # antena ramane pe satelitul scanat pana la alegere
        else:
            self._elibereaza_tunerul()
        self._stare(text)
        cb, self._la_gata = self._la_gata, None
        if cb is not None:
            cb(faza != 'esuat', text, len(self.posturi()))

    def _elibereaza_tunerul(self):
        self._scoate_extensiile()
        if self.tuner is not None:
            try:
                self.tuner.elibereaza()
            except Exception as e:
                print('[ScanerSatelit] eliberarea tunerului: %s' % e)
            self.tuner = None

    # ---- tunerul tinut la sfarsit, pana la alegere
    def _tine_tunerul(self):
        """Faza „gata": tunerul ramane (sau se ia din nou, dupa invatare) acordat pe purtator, iar zap-urile si
        inregistrarile venite din alta parte il primesc inapoi prin extensiile din Navigation."""
        tinut = getattr(self.tuner, 'tinut', None)
        if self.tuner is None or (callable(tinut) and not tinut()):
            try:
                from Hds.DabT2 import tuner as hds_tuner
                self.tuner = hds_tuner.Tuner('scaner')
                self.tuner.acordeaza(self.tp, self._tinut_acordat)
            except Exception as e:
                print('[ScanerSatelit] tunerul la sfarsit: %s' % e)
                self.tuner = None
                return
        self._pune_extensiile()

    def _tinut_acordat(self, ok, mesaj):
        if not ok:
            print('[ScanerSatelit] tunerul nu s-a putut tine la sfarsit: %s' % mesaj)
            self._elibereaza_tunerul()

    @staticmethod
    def _navigation():
        try:
            from Navigation import Navigation
            return Navigation
        except Exception:
            return None

    def _extensiile(self):
        nav = self._navigation()
        if nav is None:
            return ()
        return ((getattr(nav, 'playServiceExtensions', None), self._la_zap),
                (getattr(nav, 'recordServiceExtensions', None), self._la_inregistrare))

    def _pune_extensiile(self):
        if self._extensii:
            return
        for lista, f in self._extensiile():
            if isinstance(lista, list) and f not in lista:
                lista.insert(0, f)           # inaintea controlorilor DAB / T2, care ar cere tunerul
        self._extensii = True

    def _scoate_extensiile(self):
        if not self._extensii:
            return
        self._extensii = False
        for lista, f in self._extensiile():
            while isinstance(lista, list) and f in lista:
                lista.remove(f)

    def _la_zap(self, nav, playref, *rest):
        """Navigation.playServiceExtensions: un zap cat cautarea tine tunerul (din web, din lista, postul ales) il
        primeste inapoi, sincron, inainte ca enigma2 sau controlorii sa-l aloce. Referinta ramane neschimbata."""
        if self.tuner is not None:
            print('[ScanerSatelit] zap: dau tunerul tinut la sfarsitul scanarii')
            self._elibereaza_tunerul()
        return playref

    def _la_inregistrare(self, nav, ref, *rest):
        """Navigation.recordServiceExtensions: o inregistrare adevarata primeste tunerul; verificarea unui timer
        (simulate, variabila locala a cadrului care cheama extensiile) nu ia nimic."""
        simulare = False
        try:
            import sys
            simulare = bool(sys._getframe(1).f_locals.get('simulate', False))
        except Exception:
            simulare = False
        if self.tuner is not None and not simulare:
            print('[ScanerSatelit] inregistrare: dau tunerul tinut la sfarsitul scanarii')
            self._elibereaza_tunerul()
        return ref

    def _opreste_serviciul(self):
        try:
            nav = self.sesiune.nav
            self.ref_inainte = nav.getCurrentlyPlayingServiceReference()
            nav.stopService()
            self._serviciu_oprit = True
        except Exception as e:
            print('[ScanerSatelit] oprirea serviciului: %s' % e)

    def _reporneste_serviciul(self):
        ref, self.ref_inainte = self.ref_inainte, None
        if ref is not None:
            try:
                self.sesiune.nav.playService(ref)
            except Exception as e:
                print('[ScanerSatelit] repornirea serviciului: %s' % e)

    # ---- alegerea de la sfarsit
    def asculta(self, index):
        """Porneste postul `index` din posturi(): antena ramane pe satelitul scanat. -> (True, None) / (False, motiv)."""
        posturi = self.posturi()
        if self.faza != 'gata' or not 0 <= _int(index, -1) < len(posturi):
            return False, _('Alege un post din listă.')
        profil, _cale = profil_hdscomun(self.profil_tip)
        post = posturi[_int(index, 0)]
        # tunerul tinut pana acum trece la controlorul postului: dat sincron, chiar inainte de pornire, pe acelasi
        # transponder (antena nu se misca, nicio cerere straina nu apuca sa-l ia)
        self._elibereaza_tunerul()
        ok, motiv = porneste_postul(self.sesiune, post['ref'], profil.buchet, self.profil_tip == 'dab')
        if not ok:
            self._tine_tunerul()
        if ok:
            self.ales = 'asculta'
            self.ref_inainte = None
            self.faza = 'ales'
            self._stare(_('Pornit: %s.') % post['nume'])
        return ok, motiv

    def inapoi(self):
        """Canalul de dinainte porneste din nou (antena se intoarce). Si la renuntarea in timpul cautarii."""
        self._opreste('inapoi')

    def opreste(self):
        """La inchiderea ecranului: detectorul si invatarea oprite, tunerul dat inapoi, iar daca nu s-a ales un
        post, canalul de dinainte porneste din nou. Fara niciun raspuns catre la_gata."""
        self._opreste('oprit')

    def _opreste(self, ales):
        self._la_gata = None
        self._la_stare = None
        if self.ales is not None:
            return
        in_curs = self.in_curs()
        avea_canal = self.ref_inainte is not None
        self.ales = ales
        faza, self.faza = self.faza, ('ales' if self.ales == 'inapoi' else 'oprit')
        if self.scanare is not None:
            try:
                self.scanare.opreste()
            except Exception as e:
                print('[ScanerSatelit] oprirea detectorului: %s' % e)
            self.scanare = None
        if faza == 'invatare' and self._invat is not None:
            self._invat = None
            try:
                from Hds.DabT2 import intrare
                profil, cale = profil_hdscomun(self.profil_tip)
                intrare.controlor(profil, cale).cedeaza('scanarea s-a oprit')
            except Exception as e:
                print('[ScanerSatelit] oprirea invatarii: %s' % e)
        self._elibereaza_tunerul()
        self._reporneste_serviciul()
        if not self.sfarsit:
            self.sfarsit = time.time()
        if in_curs:
            self.text = _('Scanarea s-a oprit. Canalul tău pornește din nou.') if avea_canal else \
                _('Scanarea s-a oprit.')
        elif ales == 'inapoi' and avea_canal:
            self.text = _('Canalul tău pornește din nou.')
        self._anunta()

# ---------------------------------------------------------------- numele operatorului sub titlul lui
# prefixele felului din numele operatorilor DVB-T2 si DAB+ (data/operatori-satelit.json): in lista de alegere randul
# sta deja sub titlul felului, deci prefixul doar lungeste randul
PREFIXE_FEL = ('DAB+ prin satelit - ', 'Multiplexuri DVB-T2 prin satelit - ', 'Multiplex DVB-T2 prin satelit - ',
               'Multiplexuri DVB-T2 prin satelit ', 'Multiplex DVB-T2 prin satelit ')
# alte nume ale tarii in numele operatorilor din JSON (titlul grupei foloseste NUME_TARI)
ALTE_NUME_TARA = {'GB': ('Marea Britanie',)}


def _fel_scurt(op):
    fel = op.get('fel')
    return _('Multiplexuri DVB-T2') if fel == 't2mi' else (_('Ansambluri DAB+') if fel == 'dab' else op['nume'])


def nume_fara_fel(op):
    """Numele operatorului fara prefixul felului (titlul ferestrei spune deja „DVB-T2 prin satelit” sau „DAB+ prin
    satelit”): „Bundesmux (Germania)”. Un nume care ar incepe cu tara (Cipru) primeste felul scurt in fata."""
    nume = op['nume']
    for prefix in PREFIXE_FEL:
        if nume.startswith(prefix):
            nume = nume[len(prefix):].strip()
            break
    if not nume or nume.startswith('('):
        nume = ('%s %s' % (_fel_scurt(op), nume)).strip()
    return nume


def nume_in_grupa(op):
    """Numele operatorului in lista de alegere, unde sta sub titlul tarii lui: fara prefixul felului si fara „(Țara)”
    de la sfarsit cand e chiar tara grupei. Un nume care ar ramane gol (Cipru: numai prefixul si tara) ramane cu
    felul scurt („Multiplexuri DVB-T2”)."""
    nume = nume_fara_fel(op)
    cod = (op.get('tari') or ['?'])[0]
    for tara in (nume_tara(cod), NUME_TARI.get(cod, '')) + ALTE_NUME_TARA.get(cod, ()):
        if tara and nume.endswith(' (%s)' % tara):
            nume = nume[:-len(' (%s)' % tara)]
            break
    return nume.strip() or _fel_scurt(op)


# ---------------------------------------------------------------- helper citire config
def _citeste_config():
    c = {
        'frecventa': '11727', 'sr': '27500', 'sistem': '1',
        'pol': '0', 'fec': '0', 'mod': '0',
        'rolloff': '0', 'pilot': '2', 'inversare': '2',
        'multistream': '0', 'is_id': '', 'pls_mod': '1', 'pls_cod': '0',
        'pozitie': '192',
        # felul de scanare (FELURI). Gol = se ia din randul vechi 'tip', daca exista, altfel "satelit".
        # Cheile trebuie sa existe aici, altfel filtrul "if k in c" de mai jos le arunca la citirea fisierului.
        'fel': '', 'tip': '',
        'transponder': '', 'retea': '0',
        'operator': '', 'operator_dvbt2': '', 'operator_dab': '',
    }
    if not os.path.exists(CALE_CONFIG):
        return c
    try:
        with open(CALE_CONFIG, 'r', encoding='utf-8', errors='replace') as f:
            for linie in f:
                linie = linie.strip()
                if not linie or linie.startswith('#'):
                    continue
                if '=' in linie:
                    k, v = linie.split('=', 1)
                    k = k.strip().lower()
                    if k in c:
                        c[k] = v.strip()
    except (IOError, OSError):
        pass
    c['sistem'] = sistem_ales(c['sistem'])
    return c


def _scrie_config(c):
    linii = ['# Scaner Satelit HDSatelit: ultimii parametri folositi']
    for k, v in c.items():
        linii.append('%s = %s' % (k, v))
    try:
        with open(CALE_CONFIG, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linii) + '\n')
    except (IOError, OSError):
        pass


# ---------------------------------------------------------------- ecran scaner
class ScanerSatelit(Screen):
    """Scanerul de satelit: cele sapte feluri (FELURI). fel=None: ecranul cu randul „Fel de scanare".
    Fereastra: ecranul ScanerSatelit din skinul HDSatelit (cadrul HdsCadru1240, ca scanerele de cablu si terestru);
    pe alte skinuri skin_rezerva din Screens/ScanerCablu.py, cu cotele de mai jos (douasprezece randuri de 47 px:
    felul „Cu date introduse manual” cu randul felului, zece campuri si „Caută acum” incap pe o pagina; sub ele
    previzualizarea de 160 px, patru randuri de HdsRegular 28, pasul de 38 px). Randurile listei sunt (eticheta,
    cheie, valoare, culoarea valorii)."""

    COTE = {'lista_h': 564, 'rand': 47, 'eticheta': 440, 'linie_y': 680, 'preview_y': 692, 'preview_h': 160,
            'stare_y': 856, 'stare_h': 64}

    # ---- Parametrii transponderului, la felul „Cu date introduse manual". La multistream (randul „Multistream” pe Da)
    # se adauga fluxul si secventa PLS (_CAMPURI_MULTISTREAM, campuri_manual); T2-MI nu e aici: driverul nu-l
    # foloseste, DVB-T2 prin satelit are felul lui.
    _CAMPURI_MANUAL = [
        ('frecventa',  _('Frecvența (MHz)'),                     'numeric',  None),
        ('sr',         _('Rata de simbol (kSymb/s)'),            'numeric',  None),
        ('sistem',     _('Sistem'),                              'lista',    SISTEME),
        ('pol',        _('Polarizare'),                          'lista',    POLARIZARI),
        ('fec',        _('FEC'),                                 'lista',    FEC_VALORI),
        ('mod',        _('Modulație'),                           'lista',    MODULATII),
        ('rolloff',    _('Factorul de rotunjire (roll-off)'),    'lista',    ROLLOFF),
        ('pilot',      _('Pilot'),                               'lista',    PILOT),
        ('inversare',  _('Inversare spectru'),                   'lista',    INVERSARE),
        ('multistream', _('Multistream'),                        'lista',    DA_NU),
    ]
    _CAMPURI_MULTISTREAM = [
        ('is_id',      _('Fluxul (ISI, 0-255)'),                 'numeric',  None),
        ('pls_mod',    _('Secvența PLS'),                        'lista',    PLS_MODURI),
        ('pls_cod',    _('Codul PLS'),                           'numeric',  None),
    ]

    @classmethod
    def campuri_manual(cls, c):
        """Randurile felului „Cu date introduse manual” pentru configurarea c: fluxul si PLS-ul numai cu
        „Multistream” pe Da. Aceleasi randuri le arata pagina web (scanare_web)."""
        campuri = list(cls._CAMPURI_MANUAL)
        if _da((c or {}).get('multistream')):
            campuri += cls._CAMPURI_MULTISTREAM
        return campuri

    def __init__(self, session, fel=None, config_initial=None):
        Screen.__init__(self, session)
        from Screens.ScanerCablu import skin_rezerva, culoare_valoare, fonturi_texte
        self.skin = skin_rezerva('ScanerSatelit', self.COTE)
        self._fonturi = fonturi_texte('ScanerSatelit')
        self._culoare_valorii = culoare_valoare()
        self._config = _citeste_config()

        # ecranul poate fi deschis cu un transponder deja cautat: Gasire semnal (Satfinder.py) ii trimite satelitul,
        # frecventa, SR-ul, polarizarea si FEC-ul de acolo, plus 'tip': '1'.
        # Valorile primite se pun peste cele salvate INAINTE de verificarea pozitiei de mai jos si de aici incolo
        # se poarta ca orice valoare schimbata in ecran (se scriu la Salveaza, la pornirea cautarii si la iesire).
        initial = dict(config_initial or {})
        for _cheie, _valoare in initial.items():
            if _cheie in self._config and _valoare is not None:
                self._config[_cheie] = str(_valoare)

        # Felul: din meniu (argumentul), altfel din randul vechi 'tip' (Gasire semnal, configurari vechi), altfel
        # cel salvat. 'tip' nu se mai scrie inapoi.
        self._fel_fix = fel if fel in CHEI_FELURI else None
        tip = str(self._config.pop('tip', '') or '').strip()
        if self._fel_fix:
            self._config['fel'] = self._fel_fix
        elif 'tip' in initial or self._config.get('fel') not in CHEI_FELURI:
            self._config['fel'] = FEL_DIN_TIP.get(tip, 'satelit')

        # campul 'pozitie' vine din satelitii configurati pe tunerul de satelit (getSatListForNim); din el se ia
        # orbital_position la cautare
        self._pozitii_antena, self._motor = self._citeste_antena()
        self._multistream = self._citeste_multistream()
        self._lista_sateliti = self._construieste_lista_sateliti()
        if str(self._config.get('pozitie', '')) not in [str(p) for p, _n in self._lista_sateliti]:
            self._config['pozitie'] = str(self._lista_sateliti[0][0])
        self._tp_in_asteptare = None
        self._camp_in_alegere = None
        self._camp_in_editare = None
        self._cache_tp = {}

        self._CAMPURI = []
        self._intrari = []
        self._normalizeaza()
        self._construieste_lista()

        self['lista']      = List(self._intrari, enableWrapAround=True)
        self['preview']    = Label(self._preview())
        self['stare']      = Label(self._ajutor())
        self['key_red']    = StaticText(_('Înapoi'))
        self['key_green']  = StaticText(_('Caută acum'))
        self['key_yellow'] = StaticText(self._text_galben())
        self['key_blue']   = StaticText(self._text_albastru())

        actiuni = {
            'red':    self.inchide,
            'green':  self.cauta,
            'yellow': self._galben,
            'blue':   self.albastru,
            'ok':     self.schimba_valoare,
            'cancel': self.inchide,
            'up':     self._sus,
            'down':   self._jos,
            'left':   self._stanga,
            'right':  self._dreapta,
            'upRepeated':    self._sus,
            'downRepeated':  self._jos,
            'leftRepeated':  self._stanga,
            'rightRepeated': self._dreapta,
        }
        # ridicarea tastelor (keymap.xml, DirectionActions) fara efect, ca jurnalul sa nu scrie „unknown action”
        actiuni.update((nume, lambda: None) for nume in ('upUp', 'downUp', 'leftUp', 'rightUp'))
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions', 'DirectionActions'], actiuni, -1)
        self.onLayoutFinish.append(self._potriveste_textele)
        self.setTitle(self._titlu())

    # ---- felul si campurile lui
    def _fel(self):
        fel = self._config.get('fel')
        return fel if fel in CHEI_FELURI else 'satelit'

    def _titlu(self):
        if self._fel_fix:
            return _('Scanare satelit: %s') % (TITLURI_SCURTE.get(self._fel_fix) or
                                               _nume_valoare(FELURI, self._fel_fix))
        return _('Scanare satelit')

    def _text_albastru(self):
        """La „Mai mulți sateliți” nu e nimic de salvat (bifele sunt in fereastra lui): tasta nu apare."""
        fel = self._fel()
        if fel in PROFIL_FEL:
            return _('Fluxuri și setări')
        return '' if fel == 'mai_multi' else _('Salvează')

    def _text_galben(self):
        return '' if self._fel() == 'mai_multi' else _('Schimbă')

    # ---- textele de sub lista (previzualizarea si starea) ----
    def _potriveste_textele(self):
        from Screens.ScanerCablu import potriveste_textul
        for nume in ('preview', 'stare'):
            potriveste_textul(self[nume], *self._fonturi[nume])

    def scrie_stare(self, text):
        from Screens.ScanerCablu import potriveste_textul
        self['stare'].setText(text)
        potriveste_textul(self['stare'], *self._fonturi['stare'])

    def _scrie_preview(self):
        from Screens.ScanerCablu import potriveste_textul
        self['preview'].setText(self._preview())
        potriveste_textul(self['preview'], *self._fonturi['preview'])

    def _citeste_antena(self):
        """(pozitiile pe care le vede antena, are motor) de pe tunerul de satelit; ([], False) fara tuner."""
        nim = _nimmanager()
        if nim is None:
            return [], False
        try:
            slot = slot_satelit(nim)
        except Exception as e:
            print('[ScanerSatelit] tunerele nu se pot citi: %s' % e)
            return [], False
        if slot is None:
            return [], False
        return [p for p, n in sateliti_tuner(nim, slot)], are_motor(nim, slot)

    def _citeste_multistream(self):
        """Tunerul de satelit poate alege fluxul (tuner_multistream); False fara tuner."""
        nim = _nimmanager()
        if nim is None:
            return False
        try:
            slot = slot_satelit(nim)
        except Exception as e:
            print('[ScanerSatelit] tunerele nu se pot citi: %s' % e)
            return False
        return slot is not None and tuner_multistream(nim, slot)

    def _construieste_lista_sateliti(self):
        """Satelitii CHIAR configurati pe tunerul de satelit detectat, pt campul 'pozitie'.
        Daca nimmanager nu are niciun satelit configurat pe acest slot (LNB neconfigurat inca)
        sau tunerul lipseste in emulator, cade pe un singur implicit (19.2E) ca sa nu crape.
        nimmgr.satList are intrari de 3 elemente (orbpos, nume, flags), deci se indexeaza direct (sateliti_tuner),
        cu jurnal la eroare."""
        nim = _nimmanager()
        if nim is not None:
            try:
                slot = slot_satelit(nim)
                if slot is not None:
                    lista = sateliti_tuner(nim, slot)
                    if lista:
                        return lista
            except Exception as e:
                print('[ScanerSatelit] eroare la citirea satelitilor configurati: %s' % e)
        from Components.HdsGrade import pozitieOrbitala
        return [(192, _('%s (implicit, niciun satelit configurat pe tuner)') % pozitieOrbitala(192))]

    def _lista_transpondere(self):
        """[(cheie_tp, descriere)]: transponderele bune ale satelitului ales, din satellites.xml."""
        orbpos = _int(self._config.get('pozitie'), None)
        if orbpos not in self._cache_tp:
            bune = []
            nim = _nimmanager()
            if nim is not None and orbpos is not None:
                try:
                    bune, _sarite = transpondere_satelit(orbpos, nim.getTransponders(orbpos), self._multistream)
                except Exception as e:
                    print('[ScanerSatelit] transponderele satelitului %s: %s' % (orbpos, e))
            self._cache_tp[orbpos] = [(cheie_tp(t), _descriere_tp(t)) for t in bune]
        return self._cache_tp[orbpos]

    def _vede(self, orbpos):
        return not self._pozitii_antena or orbpos in self._pozitii_antena

    def _text_operator(self, op, sub_titlu=False):
        """Operatorul, cu pozitia si nota. In lista de alegere (sub_titlu) randul sta sub titlul felului si al tarii,
        deci numele se scrie fara ele (nume_in_grupa); randul e intreg (cand nu incape deruleaza, lib/gui/elabel.h)."""
        nume = nume_in_grupa(op) if sub_titlu else nume_fara_fel(op)
        sufix = ', ' + text_pozitie(op['pozitie'])
        if op['cere_multistream'] and not self._multistream:
            sufix += ' ' + _('(tunerul nu alege fluxul)')
        elif not self._vede(op['pozitie']):
            sufix += ' ' + _('(antena nu vede satelitul)')
        return nume + sufix

    def _lista_operatori(self, fel):
        return [(o['id'], self._text_operator(o)) for o in operatori(fel)]

    def _campuri(self):
        fel = self._fel()
        campuri = []
        if not self._fel_fix:
            campuri.append(('fel', _('Felul scanării'), 'lista', FELURI))
        if fel in ('transponder', 'satelit', 'manual'):
            campuri.append(('pozitie', _('Satelit (poziție orbitală)'), 'lista', self._lista_sateliti))
        if fel == 'transponder':
            campuri.append(('transponder', _('Transponder'), 'lista', self._lista_transpondere()))
            campuri.append(('retea', _('Căutare în rețea'), 'lista', DA_NU))
        elif fel in CAMP_OPERATOR:
            campuri.append((CAMP_OPERATOR[fel], _('Operator'), 'lista', self._lista_operatori(fel)))
        elif fel == 'manual':
            campuri += self.campuri_manual(self._config)
        return campuri

    def _normalizeaza(self):
        """Valorile de tip lista care nu mai sunt in lista lor (satelit scos, transponder de pe alt satelit,
        operator necunoscut, sistem sau factor de rotunjire scos din lista) se aduc la prima valoare buna. La
        operatori: primul pe care antena il vede si care nu cere multistream, ca ecranul sa nu porneasca pe un
        refuz. La sistem: DVB-S2 (sistem_ales)."""
        for _pas in range(3):
            schimbat = False
            for c, _e, tip, lista in self._campuri():
                if tip != 'lista' or c not in ('fel', 'pozitie', 'transponder', 'retea', 'sistem', 'rolloff',
                                               'multistream', 'pls_mod') + tuple(CAMP_OPERATOR.values()):
                    continue
                coduri = [str(x[0]) for x in lista or []]
                if not coduri or str(self._config.get(c)) in coduri:
                    continue
                nou = coduri[0]
                if c == 'sistem':
                    nou = sistem_ales(self._config.get(c))     # un sistem scos din lista trece pe DVB-S2, nu pe DVB-S
                elif c in CAMP_OPERATOR.values():
                    for o in operatori(self._fel()):
                        if (self._multistream or not o['cere_multistream']) and self._vede(o['pozitie']):
                            nou = o['id']
                            break
                self._config[c] = nou
                schimbat = True
            if not schimbat:
                break
        self._CAMPURI = self._campuri()

    def _eticheta_valoare(self, cheie, tip, lista):
        val = self._config.get(cheie, '')
        if cheie in ('fec', 'mod') and _sistem_nucleu(self._config) == SISTEM_DVB_S2 \
                and _int(val, -1) not in (FEC_DVBS2 if cheie == 'fec' else MOD_DVBS2):
            # DVB-S2 nu primeste Auto: valoarea se alege (motivul e in previzualizare)
            return _('alege cu stânga sau dreapta')
        if tip == 'numeric':
            return val if val else '-'
        if lista:
            for c, desc in lista:
                if str(c) == str(val):
                    return desc
        return val if val else '-'

    def _scurt(self, text):
        """Valoarea din lista, intreaga (Screens/ScanerCablu.valoare_scurta): un rand care nu incape deruleaza."""
        from Screens.ScanerCablu import valoare_scurta
        return valoare_scurta(text, self.COTE)

    def _construieste_lista(self):
        self._intrari = []
        for cheie, eticheta, tip, lista in self._CAMPURI:
            val_afisaj = self._scurt(str(self._eticheta_valoare(cheie, tip, lista)))
            self._intrari.append((eticheta, cheie, val_afisaj, self._culoare_valorii))
        if self._fel() in PROFIL_FEL:
            self._intrari.append((_('Fluxuri și setări'), RAND_FLUXURI, '', self._culoare_valorii))
        self._intrari.append((_('Caută acum'), RAND_CAUTA, '', self._culoare_valorii))

    def _reactualizeaza(self):
        """Randurile din nou dupa o schimbare; cursorul ramane pe randul schimbat (dupa cheie, Components/HdsCursorLista):
        setList singur l-ar duce pe primul rand."""
        self._normalizeaza()
        self._construieste_lista()
        pune_randurile(self['lista'], self._intrari)
        self._scrie_preview()
        self['key_yellow'].setText(self._text_galben())
        self['key_blue'].setText(self._text_albastru())

    def _ajutor(self):
        """Randul de stare: ce fac tastele, pe un rand si cu fonturile marite la 130 %. La „Mai mulți sateliți”
        ecranul are numai „Caută acum”; cand tara nu are operatori de felul ales, asta."""
        fel = self._fel()
        if fel == 'mai_multi':
            return _('Apasă OK pe „Caută acum”: se deschide lista sateliților de bifat.')
        if fel in CAMP_OPERATOR:
            _titlu, din_tara = grupe(fel)[0]
            if not din_tara:
                return _('%s: niciun operator de acest fel. Alte țări: OK pe rândul „Operator”.') % nume_tara(
                    tara_utilizatorului())
        return _('Schimbă cu OK, stânga sau dreapta; caută cu OK pe „Caută acum”.')

    def _sus(self):
        self['lista'].selectPrevious()

    def _jos(self):
        self['lista'].selectNext()

    def _cicleaza(self, pas):
        """Trece campul de tip lista la valoarea urmatoare (pas 1) sau anterioara (pas -1), doar prin valorile
        pe care nucleul le primeste pentru sistemul ales (_coduri_permise): la DVB-S2, FEC fara Auto si modulatie
        QPSK sau 8PSK. Valorile se compara ca text: codurile sunt numere la unele campuri, siruri la altele."""
        selectat = self['lista'].getCurrent()
        if not selectat:
            return
        for c, _etich, tip, lista in self._CAMPURI:
            if c == selectat[1]:
                if tip == 'lista' and lista:
                    coduri = [str(x) for x in _coduri_permise(c, self._config, lista)]
                    cur = str(self._config.get(c))
                    idx = coduri.index(cur) if cur in coduri else (-1 if pas > 0 else 0)
                    self._config[c] = coduri[(idx + pas) % len(coduri)]
                    self._reactualizeaza()
                break

    def _stanga(self):
        self._cicleaza(-1)

    def _dreapta(self):
        self._cicleaza(1)

    def _valori(self):
        """Valorile pentru pregateste(): configurarea ecranului, cu operatorul felului curent sub "operator"."""
        v = dict(self._config)
        fel = self._fel()
        if fel in CAMP_OPERATOR:
            v['operator'] = self._config.get(CAMP_OPERATOR[fel], '')
        return v

    def _preview(self):
        """Ce se va cauta, sau de ce nu se poate: acelasi raspuns ca la Verde (pregateste), inainte de apasare."""
        fel = self._fel()
        if fel == 'mai_multi':
            return _('Apasă OK pe „Caută acum”: se deschide lista sateliților antenei, bifează-i pe cei de căutat.')
        # frecventa scrisa la „Cu date introduse manual" e cea din listele de transpondere si pleaca asa spre nucleu
        # (fara LOF adunat), deci previzualizarea vine tot din pregateste, ca la celelalte feluri
        try:
            rez = pregateste(fel, self._valori())
        except Exception as e:
            print('[ScanerSatelit] previzualizarea: %s' % e)
            return _('Nu pot arăta ce se va căuta. %s') % motiv_eroare(e)
        text = rez.get('eroare') or rez.get('text') or ''
        nota = text_in_lucru(fel)
        return text + '\n' + nota if (text and nota) else (text or nota)

    # ---- schimbarea valorilor
    def _galben(self):
        """Galben („Schimbă”) schimba numai valori; pe randurile de actiune si la „Mai mulți sateliți” (fara
        valori) nu face nimic."""
        selectat = self['lista'].getCurrent()
        if self._fel() == 'mai_multi' or (selectat and selectat[1] in (RAND_CAUTA, RAND_FLUXURI)):
            return
        self.schimba_valoare()

    def schimba_valoare(self):
        """OK: alegerile randului luminat; pe "Caută acum" porneste cautarea, pe "Fluxuri și setări" deschide
        fereastra fluxurilor (ca Albastru)."""
        selectat = self['lista'].getCurrent()
        if not selectat:
            return
        cheie = selectat[1]
        if cheie == RAND_CAUTA:
            self.cauta()
            return
        if cheie == RAND_FLUXURI:
            self.albastru()
            return
        for c, _etich, tip, lista in self._CAMPURI:
            if c == cheie:
                if tip == 'lista' and lista:
                    # OK deschide mereu alegerile randului (numai valorile permise pentru sistemul ales,
                    # intrari_alegere), ca in toate scanerele si in Scanare detaliata; stanga / dreapta le schimba pe loc
                    self._alege_din_lista(c, _etich, lista)
                elif tip == 'numeric':
                    # tastatura scanerelor (fereastra in stilul lor, oprita inaintea ferestrei PiP)
                    from Screens.ScanerCablu import tastatura
                    self._camp_in_editare = cheie
                    self._eticheta_in_editare = _etich
                    self.session.openWithCallback(self._dupaTastatura, tastatura(),
                        title=_etich, text=self._config.get(cheie, ''))
                break

    def intrari_alegere(self, camp, lista):
        """Randurile ferestrei de alegere: [(text, cod)]. La FEC, modulatie si factorul de rotunjire numai valorile pe
        care nucleul le primeste pentru sistemul ales (_coduri_permise), in ordinea in care le trec stanga si dreapta;
        la celelalte campuri toata lista. La operatori, pe blocuri: intai tara utilizatorului (chiar goala, spusa
        limpede), apoi cate o tara; titlurile au codul None si nu se pot alege."""
        if camp not in CAMP_OPERATOR.values():
            texte = dict((str(cod), desc) for cod, desc in lista)
            return [(texte[str(cod)], str(cod)) for cod in _coduri_permise(camp, self._config, lista)
                    if str(cod) in texte]
        rez = []
        for titlu, ops in grupe(self._fel()):
            rez.append(('%s:' % titlu, None))
            if not ops:
                rez.append((INDENT + _('niciun operator de acest fel'), None))
            for o in ops:
                rez.append((INDENT + self._text_operator(o, sub_titlu=True), o['id']))
        return rez

    def _alege_din_lista(self, camp, titlu, lista):
        intrari = self.intrari_alegere(camp, lista)
        curent = str(self._config.get(camp))
        alegere = 0
        for i, (text, cod) in enumerate(intrari):
            if cod is not None and str(cod) == curent:
                alegere = i
                break
        else:
            alegere = next((i for i, (text, cod) in enumerate(intrari) if cod is not None), 0)
        self._camp_in_alegere = camp
        # AlegereDinLista, nu ChoiceBox simplu: acela leaga cifrele si butoanele colorate de primele 14 randuri,
        # titlurile cu tot, deci Verde ar alege alt rand decat cel luminat
        from Screens.ScanerCablu import AlegereDinLista
        self.session.openWithCallback(self._dupaAlegereCamp, AlegereDinLista, title=titlu, list=intrari,
                                      selection=alegere)

    def _dupaAlegereCamp(self, rez=None):
        camp, self._camp_in_alegere = self._camp_in_alegere, None
        if camp is None or not rez or rez[1] is None:
            return                         # anulat, sau un titlu de bloc
        self._config[camp] = str(rez[1])
        self._reactualizeaza()

    def _dupaTastatura(self, text=None):
        cheie = self._camp_in_editare
        self._camp_in_editare = None
        if text is None or cheie is None:
            return  # anulat din tastatura virtuala
        text = text.strip()
        eticheta = getattr(self, '_eticheta_in_editare', None) or cheie
        if text and not text.lstrip('-').isdigit():
            self.scrie_stare(_('Valoare greșită pentru %s: trebuie să fie un număr.') % eticheta)
            return
        self._config[cheie] = text
        self.scrie_stare('%s: %s' % (eticheta, text or '-'))
        self._reactualizeaza()

    # ---- cautarea
    def cauta(self):
        """Porneste felul ales. Ce se cere nucleului vine din pregateste(), la fel ca in interfata web. Lista de
        scanare se construieste aici (acelasi tipar ca ScanSetup.addSatTransponder + keyGo) si se deschide
        Screens.ServiceScan.ServiceScan direct cu ea. Tot ce pleaca spre ServiceScan trece prin motiv_refuz, ca
        nucleul sa nu renunte tacut la transponder; cand nu e nimic de cautat, motivul apare intr-o fereastra, nu
        doar „0 canale”."""
        _scrie_config(self._config)
        fel = self._fel()
        if fel == 'mai_multi':
            from Screens.ScanerMaiMultiSateliti import ScanerMaiMultiSateliti
            self.session.open(ScanerMaiMultiSateliti)
            return
        try:
            rez = pregateste(fel, self._valori())
            if rez.get('eroare'):
                self._eroare(rez['eroare'])
                return
            if rez.get('de_ales'):
                # DVB-S2 fara FEC sau modulatie reala si transponderul nu e in satellites.xml: se alege, nu se trimite Auto
                self._tp_in_asteptare = (rez['transponder'], rez.get('note') or [], rez['slot'])
                from Screens.ScanerCablu import AlegereDinLista
                self.session.openWithCallback(self._dupaAlegere, AlegereDinLista, title=rez['text'],
                                              list=rez['de_ales'])
                return
            if 'hdscomun' in rez:
                self._porneste_fluxuri(rez)
                return
            if fel == 'manual':
                self._porneste_manual(rez['transpondere'][0], rez.get('note') or [], rez['slot'], rez['text'])
                return
            self._porneste(rez['transpondere'], rez['slot'], rez['flags'], rez['text'])
        except Exception as e:
            print('[ScanerSatelit] pornirea cautarii: %s' % e)
            self.scrie_stare(_('Căutarea nu a putut porni. %s') % motiv_eroare(e))

    def _eroare(self, text):
        self.scrie_stare(text)
        from Screens.MessageBox import MessageBox
        self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)

    def _dupaAlegere(self, rez=None):
        asteptare, self._tp_in_asteptare = self._tp_in_asteptare, None
        if not asteptare:
            return
        if rez is None:
            self.scrie_stare(_('Căutare oprită: nu s-a ales FEC-ul.'))
            return
        tp, note, slot_sat = asteptare
        tp['modulation'], tp['fec'] = rez[1]
        self._config['mod'], self._config['fec'] = str(tp['modulation']), str(tp['fec'])
        _scrie_config(self._config)
        self._reactualizeaza()
        self._porneste_manual(tp, note, slot_sat)

    def _porneste(self, lista_tp, slot_sat, flags, text):
        """Poarta finala: niciun transponder nu pleaca spre nucleu daca motiv_refuz gaseste ceva."""
        for tp in lista_tp:
            motiv = motiv_refuz(tp)
            if motiv:
                self._eroare(_('Transponderul %s nu poate fi căutat: %s.') % (_descriere_tp(tp), motiv))
                return
        from enigma import eDVBFrontendParametersSatellite
        from Screens.ServiceScan import ServiceScan
        parametri = [in_parametri(eDVBFrontendParametersSatellite, tp) for tp in lista_tp]
        self.scrie_stare(text)
        # hds_fel: felul scanarii in /api/scanare-ultima (Components/HdsScanareUltima.py)
        self.session.open(ServiceScan, [{"transponders": parametri, "feid": slot_sat, "flags": flags,
                                         "hds_fel": "satelit/%s" % self._fel()}])

    def _porneste_manual(self, tp, note, slot_sat, text=None):
        """Un singur transponder, fara cautare in retea. IS-ID, codul PLS si T2-MI PLP-ID nu se trimit: nu exista in
        eDVBFrontendParametersSatellite (lib/dvb/frontendparms.h)."""
        try:
            if text is None:
                orbpos = tp['orbital_position']
                nume = dict(self._lista_sateliti).get(orbpos) or text_pozitie(orbpos)
                text = text_manual(tp, nume, note) + _text_motor(self._motor, orbpos)
            self._porneste([tp], slot_sat, 0, text)
        except Exception as e:
            print('[ScanerSatelit] pornirea cautarii manuale: %s' % e)
            self.scrie_stare(_('Căutarea nu a putut porni. %s') % motiv_eroare(e))

    # ---- DVB-T2 si DAB+ prin satelit
    def _porneste_fluxuri(self, rez):
        """Ecranul scanarii (Screens/HdsScanareFluxuri.py): intai unde se muta antena si cat dureaza, cu confirmare;
        apoi pasii si ce s-a gasit; la sfarsit posturile, cu „Ascultă" si „Înapoi la canalul meu". Dupa „Ascultă"
        se inchide si scanerul, ca postul ales sa ramana singur pe ecran."""
        self.scrie_stare(rez['text'])
        from Screens.HdsScanareFluxuri import HdsScanareFluxuri
        self.session.openWithCallback(self._dupa_fluxuri, HdsScanareFluxuri, rez)

    def _dupa_fluxuri(self, rezultat=None):
        ales, text = rezultat if isinstance(rezultat, tuple) and len(rezultat) == 2 else (None, '')
        if ales == 'asculta':
            self.inchide()
            return
        if text:
            self.scrie_stare(text)

    def albastru(self):
        """La DVB-T2 si DAB+ prin satelit: fereastra HdsComun cu lista de fluxuri (ascultare, invatare, lista de
        pe hdsatelit.com, setari). Intrarile ei vechi din meniu au devenit aceste doua feluri de scanare, deci
        drumul spre ea e de aici. La celelalte feluri: salveaza configurarea."""
        fel = self._fel()
        if fel == 'mai_multi':
            return
        if fel not in PROFIL_FEL:
            self.salveaza()
            return
        from Screens.HdsComunPrincipal import HdsDabPrincipal, HdsT2miPrincipal
        self.session.open(HdsDabPrincipal if fel == 'dab' else HdsT2miPrincipal)

    def salveaza(self):
        _scrie_config(self._config)
        self.scrie_stare(_('Configurația a fost salvată.'))

    def inchide(self):
        _scrie_config(self._config)
        self.close()

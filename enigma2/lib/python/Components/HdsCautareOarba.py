# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsCautareOarba.py: creierul comun al cautarii oarbe pe satelit, folosit de ecran (Screens/ScanerOarba.py), de
interfata web (HdsWebControl/oarba_web.py) si de probele de pe PC (teste/test_cautare_oarba.py), ca sa nu existe doua
adevaruri.

Scris de la zero.

Cautarea o face CIPUL demodulator, prin programul nostru hds-blindscan (un proces separat, vezi antetul lui
hds-blindscan.c pentru protocol): el cauta singur purtatoarele pe banda data, la orice rata intre 1 si 50 MSym/s, si
scrie transponderele gasite cu frecventa reala pe satelit. Aici sunt:
  - benzile LNB-ului (din oscilatoarele lui, aceleasi ca Components/HdsLnb.oscilatoareKhz) si trecerile cerute
    (banda x polarizare), toate intr-o SINGURA chemare a programului (o singura pornire a cipului);
  - citirea randurilor programului;
  - transponderele cunoscute ale satelitului (satellites.xml): arata ce trebuie sa existe, iar la sfarsit a doua
    trecere cauta NUMAI in ferestre inguste in jurul celor cunoscute pe care prima nu le-a gasit (masurat pe Astra
    19,2E: 89 din 89 cunoscute + 4 noi in ~195 s); dublurile unite;
  - satelitul pe care sta antena, aflat din ce s-a gasit (programul nu misca motorul: cauta unde sta antena);
  - comutatorul DiSEqC / toneburst al satelitului aratat (comutare_din_lnb), dat programului: dupa oprirea canalului
    enigma2 inchide frontend-ul si taie tensiunea LNB-ului, iar comutatorul ramas fara curent porneste pe portul A
    (Wlad, Viper 4K V10, asistenta 499376, 14.11.2026: arata 13E pe B, cauta 4,8E pe A); programul trimite deci
    comanda portului inainte de fiecare trecere, ca enigma2 la acordare;
  - Cautare: o cautare (una singura pe receptor, pornita din ecran sau din web), cu programul pornit printr-un
    'pornitor' dat din afara (pe receptor eConsoleAppContainer, la probe un proces obisnuit);
  - partea de receptor (la sfarsitul fisierului, importurile enigma2 numai la folosire): antena, oprirea si repunerea
    canalului, semnul paznicului, oprirea curata (SIGINT, nu SIGKILL), ServiceScan-ul de la sfarsit.

Nimic din acest fisier nu importa enigma2 la incarcare.
"""
from __future__ import absolute_import, unicode_literals

import bisect
import codecs
import time


def _t(text):
    """Traducerea enigma2 (functia _ din builtins), sau textul insusi (probele de pe PC)."""
    try:
        import builtins
        return builtins._(text)
    except (AttributeError, ImportError, NameError):
        return text


def N_(text):
    """Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la afisare, cu _t."""
    return text


# ---------------------------------------------------------------- constante
PROGRAM = '/usr/bin/hds-blindscan'
# Vu+ Solo SE (AVL6211): programul inchis al producatorului, nemodificat, din feed (pachetul de mai jos), chemat prin
# Components/HdsOarbaVuplus.py, care vorbeste acelasi protocol ca hds-blindscan; se instaleaza singur la prima cautare
PYTHON = '/usr/bin/python3'
PACHET_VUPLUS = 'vuplus-blindscan-dvbs-utils'
MODELE_VUPLUS = ('solose', 'vusolose')
VUMODEL = '/proc/stb/info/vumodel'
TUNER_USED = '/proc/stb/parameters/tuner_used'

# semnul 'ocupat' al paznicului (Components/HdsPaznic): cuvant scurt, fara spatii
MOTIV_OARBA = 'oarba'
CHEIE_PAZNIC = 'cautare-oarba'
DURATA_OARBA_S = 30 * 60

IF_MIN_KHZ = 950000
IF_MAX_KHZ = 2150000
# benzile LNB-ului se suprapun cu atat de fiecare parte a pragului, ca un transponder de langa prag sa nu cada intre ele
MARGINE_PRAG_KHZ = 20000
# sub atat oscilatorul e de banda C (frecventa reala = LO - IF)
LO_BANDA_C_KHZ = 7500000
# (jos, sus, prag) in kHz: LNB-ul universal, cand setarile antenei nu dau altceva
LNB_UNIVERSAL = (9750000, 10600000, 11700000)

BENZI = ('toata', 'joasa', 'inalta')
POLARIZARI = ('H', 'V', 'L', 'R')         # pozitia = codul enigma2 (Polarisation_Horizontal = 0 ...)
# rata minima: numai filtru la afisare si la 'Scanează canalele' (cipul cauta oricum de la 1 MSym/s in sus si a gasit
# si 0,94 MSym/s pe un V20); 0 = oricare
RATE_MIN = (0, 1000, 2000, 5000)

TIMP_MAX_S = 1500                          # paznicul de timp al programului, pe o chemare (4 treceri: ~190 s masurat)
GRATIE_OPRIRE_S = 90                       # dupa EXIT programul termina felia in curs (cea mai lunga masurata: 42 s)
# estimarea de pe ecran, pe trecere (banda x polarizare), dupa treptele alese; masurat pe Astra 19,2E (4 treceri):
# treapta 1 ~195 s, cu golurile (2) ~430 s, cu golurile de doua ori (3) ~654 s
SECUNDE_PE_TREAPTA = {1: 50, 2: 110, 3: 165}
# cu "Si sub 1 MSym/s" (podeaua coborata, --rata-min sub RATA_MIC_KSYM): masurat pe un SF8008, 19,2E, 4 treceri (WLD, o
# rulare): treapta 1 ~1230 s, 2 ~2340 s, 3 2626 s, fata de ~158 / ~405 / 652 s fara (estimarea spunea "cam 11 minute"
# la amandoua)
SECUNDE_PE_TREAPTA_SUB1 = {1: 310, 2: 585, 3: 660}

# a doua trecere: fereastra in jurul unui transponder cunoscut negasit, ±max(6 MHz, 0,7 x rata)
FEREASTRA_MIN_KHZ = 6000
FEREASTRA_ZECIMI = 7                       # 0,7 x rata, socotit in numere intregi
# si GOLURILE: tot ce nu acopera nicio purtatoare gasita (rata x 1,35, rolloff 0,35) se cauta din nou, in ferestre de
# 40 MHz suprapuse pe jumatate (masurat pe un V20: ferestrele inguste au prins toate ratarile primei treceri); un gol mai
# ingust de 3 MHz nu poate ascunde o purtatoare (1 MSym/s ocupa 1,35 MHz). Daca o trecere a golurilor mai gaseste
# ceva, inca una, cu ferestrele decalate cu 10 MHz (alte margini); cel mult ETAPE_MAX in total.
GOL_MIN_KHZ = 3000
FEREASTRA_GOL_KHZ = 40000
PAS_GOL_KHZ = 20000
MARGINE_GOL_KHZ = 2000
ETAPE_MAX = 3
# programul primeste cel mult 64 de treceri pe chemare (MAX_TRECERI in hds-blindscan.c): ferestrele merg in grupe
TRECERI_PE_CHEMARE = 60
# doua transpondere pe aceeasi polarizare, mai apropiate de max(2 MHz, rata/4), sunt acelasi
TOLERANTA_MIN_KHZ = 2000
# satelitul ales se schimba cu cel aflat numai cand acela se potriveste clar mai bine
POTRIVITE_MIN = 3

# sistemul transponderului nu vine de la cip (masurat: frecventa, rata, polarizarea si calitatea, atat); pentru
# 'Scanează canalele' un transponder nou merge ca DVB-S cu FEC si modulatia Auto, singura forma primita de nucleu fara
# FEC stiut (ScanerSatelit.motiv_refuz); cele cunoscute merg cu datele lor din satellites.xml
SISTEM_DVB_S, SISTEM_DVB_S2 = 0, 1
FEC_AUTO, MODULATIE_QPSK = 0, 1

# fazele cautarii
NIMIC, CAUTA, A_DOUA, OPRESTE, GATA, OPRIT, EROARE = 'nimic', 'cauta', 'a_doua', 'opreste', 'gata', 'oprit', 'eroare'
# 0.7.7 (M30): la antena cu motor, rotirea spre satelitul ales, inaintea programului
ROTIRE = 'rotire'
IN_CURS = (ROTIRE, CAUTA, A_DOUA, OPRESTE)

# codurile scurte ale programului -> ce afla omul (fara amanunte interne pe televizor)
MESAJE_EROARE = {
    'frontend-ocupat': N_('Tunerul de satelit e folosit acum (o înregistrare sau alt ecran). Încearcă după ce se '
                          'eliberează.'),
    'alt-proces': N_('O căutare oarbă e deja în curs pe acest receptor.'),
    'placa-necunoscuta': N_('Căutarea oarbă nu merge încă pe tunerul acestui receptor.'),
    'proc-tuner-lipsa': N_('Căutarea oarbă nu merge încă pe tunerul acestui receptor.'),
    'biblioteca-lipsa': N_('Căutarea oarbă nu merge încă pe tunerul acestui receptor.'),
    'simboluri-lipsa': N_('Căutarea oarbă nu merge încă pe tunerul acestui receptor.'),
    'tuner-used-lipsa': N_('Căutarea oarbă nu merge încă pe tunerul acestui receptor.'),
    'blocat': N_('Tunerul nu a mai răspuns, așa că am oprit căutarea.'),
}
MESAJ_EROARE_ALTA = N_('Căutarea nu a putut porni.')
CALE_JURNAL = '/home/root/logs/hds-blindscan.log'


# ---------------------------------------------------------------- frecventa si benzile LNB-ului
def e_banda_c(lo_khz):
    return int(lo_khz) < LO_BANDA_C_KHZ


def real_din_if(if_khz, lo_khz):
    """Frecventa reala pe satelit (kHz): LO + IF in banda Ku, LO - IF in banda C."""
    return int(lo_khz) - int(if_khz) if e_banda_c(lo_khz) else int(lo_khz) + int(if_khz)


def if_din_real(real_khz, lo_khz):
    return int(lo_khz) - int(real_khz) if e_banda_c(lo_khz) else int(real_khz) - int(lo_khz)


def _banda(cheie, lo, ton, if_start, if_stop):
    a, b = real_din_if(if_start, lo), real_din_if(if_stop, lo)
    return {'cheie': cheie, 'lo': int(lo), 'ton': int(ton), 'if_start': int(if_start), 'if_stop': int(if_stop),
            'real_start': min(a, b), 'real_stop': max(a, b)}


def benzi_lnb(osc=None):
    """Benzile pe care le poate cauta LNB-ul, din oscilatoarele lui (jos, sus, prag) in kHz (None = universal).
    Doua oscilatoare: banda joasa (ton oprit) pana la prag + 20 MHz si banda inalta (ton pornit) de la prag - 20 MHz,
    fiecare taiata la ce primeste tunerul (IF 950-2150 MHz); universal: joasa IF 950-1970, inalta IF 1080-2150. Un
    oscilator (sau pragul peste banda): o singura banda, IF 950-2150."""
    jos, sus, prag = (int(x) for x in (osc or LNB_UNIVERSAL))
    if jos <= 0 or sus <= 0:
        return []
    if jos == sus or prag - jos >= IF_MAX_KHZ or prag <= 0:
        return [_banda('unica', jos, 0, IF_MIN_KHZ, IF_MAX_KHZ)]
    benzi = []
    a, b = IF_MIN_KHZ, min(IF_MAX_KHZ, prag - jos + MARGINE_PRAG_KHZ)
    if a < b:
        benzi.append(_banda('joasa', jos, 0, a, b))
    a, b = max(IF_MIN_KHZ, prag - sus - MARGINE_PRAG_KHZ), IF_MAX_KHZ
    if a < b:
        benzi.append(_banda('inalta', sus, 1, a, b))
    return benzi


def are_doua_benzi(osc=None):
    return len(benzi_lnb(osc)) > 1


def benzi_alese(benzi, banda):
    if banda == 'joasa':
        return [b for b in benzi if b['cheie'] in ('joasa', 'unica')]
    if banda == 'inalta':
        return [b for b in benzi if b['cheie'] in ('inalta', 'unica')]
    return list(benzi)


def _polarizari(cerute):
    if cerute is None:
        cerute = ['H', 'V']
    rez = []
    for p in cerute:
        if p in POLARIZARI and p not in rez:
            rez.append(p)
    return rez


# ---------------------------------------------------------------- trecerile si chemarea programului
def treceri(cerere, osc=None):
    """Trecerile cautarii din cerere, toate pentru O SINGURA chemare a programului.

    cerere: {"tuner": slot, "banda": 'toata'|'joasa'|'inalta', "polarizari": ['H', 'V']}. osc: (jos, sus, prag) kHz.
    Intoarce {"treceri": [...], "benzi": [...], "polarizari": [...], "argv": [...]} sau {"eroare": text}."""
    benzi = benzi_lnb(osc)
    if not benzi:
        return {'eroare': _t('Oscilatorul LNB-ului nu e cunoscut. Verifică LNB-ul în Configurare LNB.')}
    banda = cerere.get('banda') or 'toata'
    if banda not in BENZI:
        return {'eroare': _t('Bandă necunoscută.')}
    pol = _polarizari(cerere.get('polarizari'))
    if not pol:
        return {'eroare': _t('Alege cel puțin o polarizare.')}
    alese = benzi_alese(benzi, banda)
    lista = []
    for b in alese:
        for p in pol:
            lista.append({'pol': p, 'cod_pol': POLARIZARI.index(p), 'banda': b['cheie'], 'lo': b['lo'],
                          'ton': b['ton'], 'if_start': b['if_start'], 'if_stop': b['if_stop']})
    tuner = int(cerere.get('tuner') or 0)
    return {'treceri': lista, 'benzi': alese, 'polarizari': pol,
            'argv': argv_program(lista, osc, tuner, cerere.get('timp_max'), cerere.get('vuplus'),
                                 cerere.get('rata_min'), cerere.get('comutare'))}


# commitedDiseqcCommand (NimManager): AA, AB, BA, BB = porturile A..D ale unui comutator DiSEqC 1.0; '240'..'255' = octetul
# comenzii scris de om, trimis asa cum e
PORT_DISEQC = {'AA': 0, 'AB': 1, 'BA': 2, 'BB': 3}


def comutare_din_lnb(lnb):
    """Comutarea LNB-ului unui satelit (Components/HdsLnb: modul simplu si cel avansat dau acelasi dictionar) ->
    {'port': 0-3} sau {'octet': 0xF0-0xFF} si/sau {'toneburst': 'A'|'B'}; None cand nu e nimic de comutat (un singur
    LNB, motor, DiSEqC 1.1 necomandat sau Unicable: acolo programul nu trimite nimic, ca pana acum)."""
    if not lnb or lnb.get('diseqc') in (None, '', 'none', '1_2'):
        return None
    rez = {}
    comanda = str(lnb.get('comanda') or 'none')
    if comanda in PORT_DISEQC:
        rez['port'] = PORT_DISEQC[comanda]
    elif comanda.isdigit() and 0xF0 <= int(comanda) <= 0xFF:
        rez['octet'] = int(comanda)
    if lnb.get('toneburst') in ('A', 'B'):
        rez['toneburst'] = lnb['toneburst']
    return rez or None


def argv_comutare(comutare):
    """Argumentele comutarii pentru hds-blindscan (numai programul nostru, nu adaptorul Vu+)."""
    if not comutare:
        return []
    argv = []
    if comutare.get('port') in (0, 1, 2, 3):
        argv += ['--diseqc-port', str(int(comutare['port']))]
    elif isinstance(comutare.get('octet'), int) and 0xF0 <= comutare['octet'] <= 0xFF:
        argv += ['--diseqc-octet', str(int(comutare['octet']))]
    if comutare.get('toneburst') in ('A', 'B'):
        argv += ['--toneburst', comutare['toneburst']]
    return argv


# ---------------------------------------------------------------- satelitul ales in ecran (0.7.7, WLD)
def _lnb_fix(lnb):
    """LNB-ul la care programul ajunge fara sa miste antena: nu cel al motorului (DiSEqC 1.2 sau "toti satelitii") si nu
    Unicable (cautarea oarba nu merge prin el)."""
    return bool(lnb) and not lnb.get('toti') and lnb.get('diseqc') != '1_2' and lnb.get('tip') != 'unicable'


def alegeri_satelit(modele, slot_acum, poz_acum, cu_comanda=True):
    """Satelitii randului "Satelit" al cautarii oarbe -> [(pozitie, slot)], in ordinea tunerelor si a porturilor.

    De ce: Wlad (forum 948 #2339/#2359, Amiko Viper 4K V10, comutator DiSEqC A=4,8E, B=13E, C=19,2E, D=4W): pana in
    0.7.6 se cauta numai pe satelitul canalului pornit, iar pentru altul trebuia pornit intai un canal de pe el.
    modele: [(slot, modelul tunerului din Components/HdsLnb.citeste)], tunerul cautarii intai. Intra satelitii la care
    programul ajunge fara sa miste antena: serviti de un LNB fix (_lnb_fix), pe un tuner cu un singur LNB (nimic de
    comutat) sau cu comutarea stiuta (comutare_din_lnb: portul DiSEqC 1.0, octetul scris de om, toneburst), pe care
    hds-blindscan o trimite inainte de fiecare trecere; DiSEqC 1.1 numai pe un tuner cu un singur LNB (comanda necomisa
    nu e in model si programul nu o trimite). cu_comanda=False (adaptorul Vu+, care nu trimite DiSEqC): numai
    tunerele cu un singur LNB. Pozitia de acum (poz_acum pe slot_acum; None = nestiuta: motor sau mai multi sateliti
    fara canal de satelit pornit) e mereu in lista, cu tunerul cautarii, ca implicitul sa ramana cautarea de pana
    acum; cand nu e printre cei fixi (motorul), e prima."""
    rez, vazute = [], set()
    for slot, model in modele or []:
        model = model or {}
        if model.get('motiv'):
            continue
        lnburi = list(model.get('lnburi') or [])
        # satelitul e al primului LNB anume care il are (ca HdsLnb.lnbPentruSatelit); "toti satelitii" nu intra
        al_cui = {}
        for i, lnb in enumerate(lnburi):
            if not lnb.get('toti'):
                for p in lnb.get('sateliti') or []:
                    al_cui.setdefault(p, i)
        for i, lnb in enumerate(lnburi):
            if not _lnb_fix(lnb):
                continue
            # DiSEqC 1.1 poate cere si comanda necomisa, pe care programul nu o trimite: numai pe un tuner cu un singur LNB
            if len(lnburi) > 1 and (lnb.get('diseqc') == '1_1' or not (cu_comanda and comutare_din_lnb(lnb))):
                continue
            for p in lnb.get('sateliti') or []:
                if al_cui.get(p) == i and p not in vazute:
                    vazute.add(p)
                    rez.append((int(p), slot))
    if poz_acum in vazute:
        rez = [(p, slot_acum if p == poz_acum else s) for p, s in rez]
    else:
        rez.insert(0, (poz_acum, slot_acum))
    return rez


def argv_program(lista, osc=None, tuner=0, timp_max=None, vuplus=None, rata_min=0, comutare=None):
    """Chemarea programului pentru trecerile date: oscilatoarele in MHz, fiecare trecere 'POL,TON,START,STOP'.
    vuplus: {'adaptor', 'program', 'i2c'} pe Vu+ Solo SE (vezi vuplus_pentru): acelasi protocol, prin HdsOarbaVuplus.
    comutare: comutare_din_lnb() a satelitului aratat (portul DiSEqC / toneburst), trimisa de program inainte de
    fiecare trecere."""
    jos, sus, _prag = (int(x) for x in (osc or LNB_UNIVERSAL))
    if vuplus:
        argv = [PYTHON, vuplus['adaptor'], '--program', vuplus['program'], '--i2c', str(int(vuplus['i2c'])),
                '--rata-min', str(max(1, int(rata_min or 0) // 1000))]
    else:
        argv = [PROGRAM]
        # sub 1 MSym/s numai la cerere: programul coboara podeaua (implicit 1000 kSym/s) cel mult pana la minimul declarat
        # de driverul tunerului; alegerile de la 1 MSym/s in sus nu trimit nimic, ca pana acum
        if 0 < int(rata_min or 0) < RATA_MIC_KSYM:
            argv += ['--rata-min', str(int(rata_min))]
    argv += ['--tuner', str(int(tuner)), '--lo-jos', str(jos // 1000), '--lo-sus', str(sus // 1000),
             '--timp-max', str(int(timp_max or TIMP_MAX_S))]
    if not vuplus:
        argv += argv_comutare(comutare)
    for t in lista:
        argv += ['--trecere', '%s,%d,%d,%d' % (t['pol'], t['ton'], t['if_start'], t['if_stop'])]
    return argv


def estimare_s(nr_treceri, trepte=3, rata_min=0):
    """Cat dureaza cautarea, dupa treceri, trepte si rata minima aleasa (sub 1 MSym/s e de ~4 ori mai lunga)."""
    try:
        sub1 = 0 < int(rata_min or 0) < RATA_MIC_KSYM
    except (TypeError, ValueError):
        sub1 = False
    tabel = SECUNDE_PE_TREAPTA_SUB1 if sub1 else SECUNDE_PE_TREAPTA
    return int(nr_treceri) * tabel.get(int(trepte), tabel[3])


def text_rotire(secunde):
    """Cat poate dura rotirea antenei, ca la scanarile prin satelit ("30 de secunde", "un minut": ScanerSatelit)."""
    secunde = int(secunde or 0) or 60
    try:
        from Screens import ScanerSatelit as S
        return S.text_durata(secunde)
    except Exception:
        return text_durata(secunde)


def text_durata(secunde):
    """'cam un minut' / 'cam 4 minute' (la singular fara cifra)."""
    minute = max(1, (int(secunde) + 59) // 60)
    return _t('cam un minut') if minute == 1 else _t('cam %d minute') % minute


# ---------------------------------------------------------------- alegerile omului (aceleasi pe televizor si in web)
ALEGERI = {
    'banda': (('toata', N_('Toată banda (joasă și înaltă)')), ('joasa', N_('Numai banda joasă')),
              ('inalta', N_('Numai banda înaltă'))),
    'polarizari': (('ambele', N_('Orizontală și verticală')), ('H', N_('Numai orizontală')),
                   ('V', N_('Numai verticală'))),
    # '100': si ratele sub 1 MSym/s (Silviu, SF8008: 285 kSym/s pe 19,2E), numai pe tunerele care le declara; mai lent
    'rata_min': (('0', N_('Oricare')), ('100', N_('Și sub 1 MSym/s (mai lent)')), ('1000', N_('1 MSym/s')),
                 ('2000', N_('2 MSym/s')), ('5000', N_('5 MSym/s'))),
    # treptele: omul alege cat de amanuntit; implicit cea mai sigura
    'trepte': (('1', N_('1: toată banda o dată')), ('2', N_('2: și golurile benzii')),
               ('3', N_('3: golurile de două ori'))),
}
# ce face treapta aleasa, pe scurt, sub alegeri
TEXTE_TREPTE = {
    1: N_('Treapta 1: toată banda o dată, apoi numai unde lipsește un transponder cunoscut.'),
    2: N_('Treapta 2: și toate golurile benzii, căutate din nou în ferestre înguste.'),
    3: N_('Treapta 3: golurile încă o dată, cu alte margini. Cea mai sigură și cea mai lungă.'),
}
# sub aceasta rata (kSym/s) cautarea oarba cere programului podeaua coborata (--rata-min)
RATA_MIC_KSYM = 1000
# ultimele alegeri, cat merge interfata (ecranul si pagina web pornesc de la ele)
ULTIMELE = {'banda': 'toata', 'polarizari': 'ambele', 'rata_min': '0', 'trepte': '3'}


def alegeri_traduse(cheie):
    return [(c, _t(n)) for c, n in ALEGERI[cheie]]


def valoare_buna(cheie, valoare):
    return valoare in [c for c, _n in ALEGERI.get(cheie, ())]


def cerere_din(config):
    """Alegerile (ecranul sau pagina web) -> cererea cautarii (treceri). 0.7.7 (WLD): config['pozitie'] = satelitul ales
    in randul "Satelit" (pozitia_din), dus in cerere ca porneste_pe_receptor sa-l dea lui antena()."""
    pol = config.get('polarizari') or 'ambele'
    rez = {'banda': config.get('banda') or 'toata', 'polarizari': ['H', 'V'] if pol == 'ambele' else [pol],
           'rata_min': int(config.get('rata_min') or 0), 'trepte': trepte_din(config.get('trepte'))}
    poz = pozitie_din(config.get('pozitie'))
    if poz is not None:
        rez['pozitie'] = poz
    return rez


def pozitie_din(valoare):
    """Satelitul ales (pozitia orbitala in zecimi de grad, 0-3599) din ecran sau din pagina web; None = niciunul ales
    (gol, nestiut), adica satelitul de pana acum: cel pe care sta antena (al canalului pornit)."""
    try:
        poz = int(valoare)
    except (TypeError, ValueError):
        return None
    return poz if 0 <= poz < 3600 else None


def trepte_din(valoare):
    try:
        return max(1, min(3, int(valoare)))
    except (TypeError, ValueError):
        return 3


def text_satelit(antena):
    return antena.get('nume') or _t('cel pe care stă antena acum')


def text_previzualizare(antena, config):
    """Ce se va cauta si cat dureaza, sau de ce nu se poate (acelasi text pe televizor si in pagina)."""
    if antena.get('motiv'):
        return antena['motiv']
    pregatit = treceri(cerere_din(config), antena.get('osc'))
    if pregatit.get('eroare'):
        return pregatit['eroare']
    n = len(pregatit['treceri'])
    trepte = trepte_din(config.get('trepte'))
    text = _t('Treceri (bandă × polarizare): %d. Durata: %s.') % (
        n, text_durata(estimare_s(n, trepte, config.get('rata_min'))))
    text += ' ' + _t(TEXTE_TREPTE[trepte])
    # 0.7.7 (WLD): satelitii din spatele unui comutator se aleg in randul "Satelit"; nota ramane la motor (antena nu se
    # roteste) si cand niciun alt satelit nu se poate alege (comutare necunoscuta, adaptorul Vu+)
    # 0.7.7 (M30): la motor satelitul se alege si el in rand; antena se roteste inainte de cautare
    if antena.get('rotire'):
        text += ' ' + _t('Antena se rotește spre %s (până la %s).') % (antena.get('nume') or text_satelit({}),
                                                                       text_rotire(antena.get('secunde_rotire')))
    elif len(antena.get('sateliti') or []) > 1 and len(antena.get('alegeri') or []) < 2:
        text += ' ' + _t('Antena nu se mișcă: pentru alt satelit, pornește întâi un canal de pe el.')
    return text


# ---------------------------------------------------------------- transponderele: aceleasi, cunoscute, negasite
def toleranta_khz(a, b):
    rate = [int(x.get('symbol_rate') or 0) for x in (a, b) if int(x.get('symbol_rate') or 0) > 0]
    r = min(rate) if rate else 0
    return max(TOLERANTA_MIN_KHZ, r // 4000)


def la_fel(a, b):
    """Acelasi transponder: aceeasi polarizare si frecventa in toleranta (max(2 MHz, rata/4))."""
    return int(a['polarisation']) == int(b['polarisation']) and \
        abs(int(a['frequency']) - int(b['frequency'])) <= toleranta_khz(a, b)


class _Index(object):
    """Cautare rapida 'e in lista?' (pe receptor: ~100 de sateliti x ~100 de transpondere)."""

    def __init__(self, lista):
        self._pe_pol = {}
        for t in lista:
            self._pe_pol.setdefault(int(t['polarisation']), []).append(t)
        self._chei = {}
        for p, l in self._pe_pol.items():
            l.sort(key=lambda x: int(x['frequency']))
            self._chei[p] = [int(x['frequency']) for x in l]

    def gaseste(self, tp):
        p = int(tp['polarisation'])
        chei = self._chei.get(p)
        if not chei:
            return None
        f = int(tp['frequency'])
        i = bisect.bisect_left(chei, f - 13000)    # toleranta cea mai mare: 50 MSym/s / 4 = 12,5 MHz
        lista = self._pe_pol[p]
        cel_mai_bun, dif = None, None
        while i < len(chei) and chei[i] <= f + 13000:
            if la_fel(tp, lista[i]):
                d = abs(chei[i] - f)
                if dif is None or d < dif:
                    cel_mai_bun, dif = lista[i], d
            i += 1
        return cel_mai_bun


def in_benzi(tp, benzi, polarizari):
    """Transponderul cade in benzile si polarizarile cautate (la cel putin 2 MHz de margine)."""
    if POLARIZARI[int(tp['polarisation']) % 4] not in polarizari:
        return False
    f = int(tp['frequency'])
    return any(b['real_start'] + 2000 <= f <= b['real_stop'] - 2000 for b in benzi)


def cunoscute_in_cautare(cunoscute, benzi, polarizari):
    """Cunoscutele (dict-uri in forma scanerului) care cad in ce se cauta, fara dubluri, dupa frecventa."""
    rez = []
    for tp in sorted(cunoscute or [], key=lambda x: (int(x['frequency']), int(x['polarisation']))):
        if in_benzi(tp, benzi, polarizari) and not any(la_fel(tp, r) for r in rez[-4:]):
            rez.append(tp)
    return rez


def negasite(cunoscute, gasite):
    idx = _Index(gasite)
    return [c for c in cunoscute if idx.gaseste(c) is None]


def ferestre_a_doua(lipsa, benzi):
    """A doua trecere: fereastra ±max(6 MHz, 0,7 x rata) in jurul fiecarui cunoscut negasit, in IF-ul benzii lui,
    taiata la 950-2150; ferestrele care se ating (aceeasi polarizare, aceeasi banda) unite. Intoarce trecerile."""
    pe_cheie = {}
    for tp in lipsa:
        f = int(tp['frequency'])
        # banda in care transponderul sta cel mai departe de margini (in suprapunerea de la prag, oricare)
        potrivite = [b for b in benzi if b['real_start'] <= f <= b['real_stop']]
        if not potrivite:
            continue
        b = max(potrivite, key=lambda x: min(f - x['real_start'], x['real_stop'] - f))
        jumatate = max(FEREASTRA_MIN_KHZ, int(tp.get('symbol_rate') or 0) * FEREASTRA_ZECIMI // 10000)
        a1, a2 = if_din_real(f - jumatate, b['lo']), if_din_real(f + jumatate, b['lo'])
        a, c = max(IF_MIN_KHZ, min(a1, a2)), min(IF_MAX_KHZ, max(a1, a2))
        if a >= c:
            continue
        pol = POLARIZARI[int(tp['polarisation']) % 4]
        pe_cheie.setdefault((b['cheie'], pol), (b, []))[1].append((a, c))
    rez = []
    for (cheie, pol), (b, intervale) in sorted(pe_cheie.items()):
        unite = []
        for a, c in sorted(intervale):
            if unite and a <= unite[-1][1]:
                unite[-1] = (unite[-1][0], max(unite[-1][1], c))
            else:
                unite.append((a, c))
        for a, c in unite:
            rez.append({'pol': pol, 'cod_pol': POLARIZARI.index(pol), 'banda': cheie, 'lo': b['lo'], 'ton': b['ton'],
                        'if_start': a, 'if_stop': c})
    return rez


def jumatate_ocupata_khz(tp):
    """Jumatate din latimea ocupata de purtatoare: rata x 1,35 / 2 (rolloff 0,35), in kHz; cel putin 0,7 MHz."""
    return max(700, int(tp.get('symbol_rate') or 0) * 27 // 40000)


def goluri(gasite, benzi, polarizari):
    """Locurile din benzile si polarizarile cautate pe care nu le acopera nicio purtatoare gasita: [(banda, pol,
    real_start, real_stop)] in kHz, numai cele mai late de GOL_MIN_KHZ."""
    rez = []
    for b in benzi:
        for pol in polarizari:
            cod = POLARIZARI.index(pol)
            ocupat = sorted((int(t['frequency']) - jumatate_ocupata_khz(t), int(t['frequency']) + jumatate_ocupata_khz(t))
                            for t in gasite if int(t['polarisation']) == cod)
            cur = b['real_start']
            for a, c in ocupat:
                if c <= cur:
                    continue
                if a - cur >= GOL_MIN_KHZ and a > cur:
                    rez.append((b, pol, cur, min(a, b['real_stop'])))
                cur = max(cur, c)
                if cur >= b['real_stop']:
                    break
            if b['real_stop'] - cur >= GOL_MIN_KHZ:
                rez.append((b, pol, cur, b['real_stop']))
    return [g for g in rez if g[3] - g[2] >= GOL_MIN_KHZ]


def ferestre_goluri(lista_goluri, decalaj_khz=0):
    """Trecerile care acopera golurile: ferestre de FEREASTRA_GOL_KHZ, din PAS_GOL_KHZ in PAS_GOL_KHZ (fiecare loc vazut
    de doua ori, cu margini diferite), cu MARGINE_GOL_KHZ peste purtatoarele vecine, in IF-ul benzii, taiate la
    950-2150 MHz. decalaj_khz muta inceputul ferestrelor (a treia trecere)."""
    rez = []
    vazute = set()
    for b, pol, a, c in lista_goluri:
        a, c = a - MARGINE_GOL_KHZ, c + MARGINE_GOL_KHZ
        if c - a <= FEREASTRA_GOL_KHZ:
            bucati = [(a, c)]
        else:
            bucati = []
            x = a - (decalaj_khz % PAS_GOL_KHZ if decalaj_khz else 0)
            while x < c:
                bucati.append((max(a, x), min(c, x + FEREASTRA_GOL_KHZ)))
                if x + FEREASTRA_GOL_KHZ >= c:
                    break
                x += PAS_GOL_KHZ
        for r1, r2 in bucati:
            i1, i2 = if_din_real(r1, b['lo']), if_din_real(r2, b['lo'])
            s, e = max(IF_MIN_KHZ, b['if_start'], min(i1, i2)), min(IF_MAX_KHZ, b['if_stop'], max(i1, i2))
            if e - s < GOL_MIN_KHZ or (b['cheie'], pol, s, e) in vazute:
                continue
            vazute.add((b['cheie'], pol, s, e))
            rez.append({'pol': pol, 'cod_pol': POLARIZARI.index(pol), 'banda': b['cheie'], 'lo': b['lo'],
                        'ton': b['ton'], 'if_start': s, 'if_stop': e})
    return rez


def treceri_etapa(etapa, cunoscute, gasite, benzi, polarizari):
    """Trecerile etapei 2 (ferestrele cunoscutelor negasite + toate golurile) sau 3 (golurile ramase, cu ferestrele
    decalate), in ordinea benzii, a polarizarii si a frecventei (cat mai putine comutari ale LNB-ului)."""
    lista = []
    if etapa == 2:
        lista += ferestre_a_doua(negasite(cunoscute, gasite), benzi)
    lista += ferestre_goluri(goluri(gasite, benzi, polarizari), PAS_GOL_KHZ // 2 if etapa >= 3 else 0)
    ordine = dict((b['cheie'], i) for i, b in enumerate(benzi))
    lista.sort(key=lambda t: (ordine.get(t['banda'], 0), t['pol'], t['if_start']))
    return lista


def identifica_satelit(gasite, candidati, ales=None):
    """Satelitul pe care sta antena, din transponderele gasite: cel ale carui cunoscute se potrivesc cu cele mai multe.
    candidati: {pozitie: [cunoscute]}. Intoarce (pozitie, potrivite, clasament [(potrivite, pozitie)]). Satelitul ales
    ramane cand nu e altul clar mai bun (de doua ori mai multe potriviri si cel putin POTRIVITE_MIN)."""
    clasament = []
    for poz, lista in (candidati or {}).items():
        idx = _Index(lista)
        clasament.append((sum(1 for g in gasite if idx.gaseste(g) is not None), poz))
    clasament.sort(key=lambda x: (-x[0], x[1]))
    pe_poz = dict((p, n) for n, p in clasament)
    if not clasament:
        return ales, 0, clasament
    n_bun, poz_bun = clasament[0]
    n_ales = pe_poz.get(ales, 0) if ales is not None else 0
    if ales is not None and (n_bun < POTRIVITE_MIN or n_bun < 2 * max(1, n_ales)):
        return ales, n_ales, clasament
    if n_bun < POTRIVITE_MIN:
        return ales, n_ales, clasament
    return poz_bun, n_bun, clasament


# ---------------------------------------------------------------- citirea randurilor programului
def citeste_eveniment(linie):
    """Un rand al protocolului -> dict cu 'tip' si campurile lui, sau None cand randul nu e al nostru (biblioteca
    platformei scrie si ea pe aceeasi iesire). Tipuri: profil, pornit, trecere, progres, tp, jurnal, gata, oprit,
    eroare, sonda."""
    parti = (linie or '').split()
    if not parti:
        return None
    cap = parti[0]
    try:
        if cap == 'TP' and len(parti) >= 7:
            pol = parti[4]
            if pol not in POLARIZARI:
                return None
            return {'tip': 'tp', 'frecventa': int(parti[1]), 'rata_ksym': int(parti[2]), 'sistem': int(parti[3]),
                    'pol': pol, 'if_khz': int(parti[5]), 'calitate': int(parti[6])}
        if cap == 'PROGRES' and len(parti) >= 3:
            return {'tip': 'progres', 'procent': max(0, min(100, int(parti[1]))), 'gasite': int(parti[2])}
        if cap == 'TRECERE' and len(parti) >= 6:
            return {'tip': 'trecere', 'nr': int(parti[1]), 'pol': parti[2], 'ton': int(parti[3]),
                    'if_start': int(parti[4]), 'if_stop': int(parti[5])}
        if cap == 'PORNIT' and len(parti) >= 3:
            return {'tip': 'pornit', 'treceri': int(parti[1]), 'latime_khz': int(parti[2])}
        if cap == 'JURNAL' and len(parti) >= 2:
            return {'tip': 'jurnal', 'cuvant': parti[1], 'valori': parti[2:]}
        if cap in ('GATA', 'OPRIT') and len(parti) >= 3:
            return {'tip': cap.lower(), 'gasite': int(parti[1]), 'durata_ms': int(parti[2])}
        if cap == 'EROARE' and len(parti) >= 2:
            return {'tip': 'eroare', 'cod': parti[1], 'text': ' '.join(parti[2:])}
        if cap == 'SONDA' and len(parti) >= 2:
            return {'tip': 'sonda', 'cod': int(parti[1]), 'text': ' '.join(parti[2:])}
        if cap == 'PROFIL' and len(parti) >= 7:
            return {'tip': 'profil', 'port': int(parti[1]), 'i2c': int(parti[2]), 'adr_demod': parti[3],
                    'tuner': parti[4], 'adr_tuner': parti[5], 'gpio': parti[6]}
    except (ValueError, IndexError):
        return None
    return None


def transponder_gasit(ev, orbpos):
    """Un eveniment 'tp' -> transponderul gasit, in forma scanerului (frequency kHz, symbol_rate Sym/s, polarisation
    0..3), plus calitatea. Sistemul nu e stiut (vezi pentru_scanare)."""
    return {'frequency': int(ev['frecventa']), 'symbol_rate': int(ev['rata_ksym']) * 1000,
            'polarisation': POLARIZARI.index(ev['pol']), 'orbital_position': int(orbpos) if orbpos is not None else 0,
            'calitate': int(ev.get('calitate') or 0)}


def mesaj_eroare(cod):
    return _t(MESAJE_EROARE.get(cod, MESAJ_EROARE_ALTA))


# ---------------------------------------------------------------- lista de la sfarsit
CHEI_SCANARE = ('frequency', 'symbol_rate', 'polarisation', 'fec', 'inversion', 'orbital_position', 'system',
                'modulation', 'rolloff', 'pilot', 'is_id', 'pls_mode', 'pls_code', 't2mi_plp_id', 't2mi_pid')


def _curat(tp):
    return dict((k, tp[k]) for k in CHEI_SCANARE if k in tp)


def din_cautare(tp, orbpos):
    """Un transponder gasit orb, pentru nucleu: DVB-S cu FEC si modulatia Auto (sistemul nu vine de la cip)."""
    return {'frequency': int(tp['frequency']), 'symbol_rate': int(tp['symbol_rate']),
            'polarisation': int(tp['polarisation']), 'fec': FEC_AUTO, 'inversion': 2,
            'orbital_position': int(orbpos), 'system': SISTEM_DVB_S, 'modulation': MODULATIE_QPSK, 'rolloff': 0,
            'pilot': 2}


def randuri(cunoscute, gasite, rata_min=0, gata=False, oprita=False):
    """Lista de pe ecran si din pagina, dupa frecventa: [{"tp", "stare"}], stare = 'gasit' (cunoscut, gasit),
    'nou' (gasit, nu e in lista), 'cunoscut' (inca negasit), la sfarsit 'negasit', iar dupa o cautare oprita
    'neverificat' (poate nu s-a ajuns la el). Cele noi sub rata minima nu se arata."""
    idx = _Index(gasite)
    lipsa = 'neverificat' if oprita else ('negasit' if gata else 'cunoscut')
    rez = []
    for c in cunoscute:
        rez.append({'tp': c, 'stare': 'gasit' if idx.gaseste(c) is not None else lipsa})
    idx_c = _Index(cunoscute)
    for g in gasite:
        if idx_c.gaseste(g) is None and int(g['symbol_rate']) >= int(rata_min or 0) * 1000:
            rez.append({'tp': g, 'stare': 'nou'})
    rez.sort(key=lambda r: (int(r['tp']['frequency']), int(r['tp']['polarisation'])))
    return rez


def pentru_scanare(cunoscute, gasite, orbpos, rata_min=0):
    """Ce primeste 'Scanează canalele': TOATE cunoscutele (cu datele lor, deci nicio frecventa cunoscuta ratata) si
    cele noi, peste rata minima, ca DVB-S Auto. In forma scanerului (Screens/ScanerSatelit.in_parametri)."""
    rez = [_curat(c) for c in cunoscute]
    idx_c = _Index(cunoscute)
    for g in gasite:
        if idx_c.gaseste(g) is None and int(g['symbol_rate']) >= int(rata_min or 0) * 1000:
            rez.append(din_cautare(g, orbpos))
    for tp in rez:
        tp['orbital_position'] = int(orbpos)
    return rez


def text_tp(tp):
    return _t('%d MHz, %s, %d kSym/s') % (int(tp['frequency']) // 1000, POLARIZARI[int(tp['polarisation']) % 4],
                                         int(tp['symbol_rate']) // 1000)


TEXTE_STARE = {'gasit': N_('găsit'), 'nou': N_('nou'), 'cunoscut': N_('se caută'), 'negasit': N_('negăsit'),
               'neverificat': N_('neverificat')}


def text_stare(stare):
    return _t(TEXTE_STARE.get(stare, stare))


def casete(st):
    """DSG2 (14.11.2026): casetele cautarii, pe televizor (Screens/ScanerOarba) si in pagina /oarba:
    [(cheie, cifra, eticheta, randul mic)] din stare(): Transpondere (gasite, cu cele noi), Progres, Durata. [] cand nu
    s-a pornit nicio cautare sau la eroare (atunci ramane numai randul de stare, care spune de ce). Aceleasi numere ca
    randul de stare, care ramane intreg sub casete."""
    if not st or st.get('faza') in (None, NIMIC, EROARE):
        return []
    n = st.get('numere') or {}
    noi = int(n.get('noi') or 0)
    gasite = noi + int(n.get('gasite_cunoscute') or 0)
    return [('transp', '%d' % gasite, _t('Transpondere'), _t('new: %d') % noi),
            ('progres', '%d%%' % int(st.get('procent') or 0), _t(N_('Progres')), ''),
            ('durata', '%d s' % int(st.get('durata_s') or 0), _t('Durata'), '')]


# ---------------------------------------------------------------- cautarea
class Cautare(object):
    """O cautare oarba: prima chemare a programului (toate trecerile), apoi, numai daca trebuie, a doua (ferestrele
    inguste in jurul cunoscutelor negasite). Starea o citesc ecranul si pagina web (stare(), randuri_acum());
    ascultatorii (adauga_ascultator) sunt chemati la orice schimbare.

    pornitor(argv, la_rand, la_iesire) -> proces cu opreste() (cerere de oprire curata: SIGINT) si omoara();
    la_rand(linie) primeste fiecare rand, la_iesire(cod) iesirea. candidati: functie () -> {pozitie: [cunoscute]}
    pentru aflarea satelitului (chemata o data, la sfarsitul primei treceri)."""

    def __init__(self, pornitor, ceas=None):
        self._pornitor = pornitor
        self._ceas = ceas or time.time
        self._ascultatori = []
        self._proces = None
        self.faza = NIMIC
        self._goleste()

    def _goleste(self):
        self.etapa = 0
        self.trepte = 3
        self.cerere = {}
        self.osc = None
        self.orbpos = None
        self.orbpos_ales = None
        self.nume_satelit = ''
        self.benzi = []
        self.polarizari = []
        self.treceri1 = []
        self.treceri2 = []
        self.treceri_etapa = []
        self._lot = []
        self._facute = 0
        self.cunoscute_toate = []
        self.cunoscute = []
        self.gasite = []
        self.procent = 0
        self.trecere = None
        self.nr_trecere = 0
        self.jurnal = []
        self.cod_eroare = ''
        self.mesaj = ''
        self.t_inceput = 0.0
        self.t_sfarsit = 0.0
        self.t_oprire = 0.0
        self.durata_program_ms = 0
        self.satelit_schimbat = False
        self._candidati = None
        self._nume_pozitii = {}
        self.secunde_rotire = 0
        self.opreste_rotirea = None       # pus de partea de receptor in faza ROTIRE: da tunerul rotirii inapoi

    # ---- ascultatori
    def adauga_ascultator(self, f):
        if f not in self._ascultatori:
            self._ascultatori.append(f)

    def scoate_ascultator(self, f):
        if f in self._ascultatori:
            self._ascultatori.remove(f)

    def _anunta(self):
        for f in list(self._ascultatori):
            try:
                f(self)
            except Exception as e:
                print('[HdsCautareOarba] ascultatorul: %s' % e)

    # ---- pornire
    def in_curs(self):
        return self.faza in IN_CURS

    def porneste(self, cerere, osc=None, orbpos=None, cunoscute=None, nume_satelit='', candidati=None,
                 nume_pozitii=None):
        """Porneste cautarea. nume_pozitii: {pozitie: nume} pentru satelitul aflat. Intoarce None sau textul
        refuzului. Din faza ROTIRE (antena a ajuns pe satelitul ales) porneste ca de obicei."""
        if self.in_curs() and self.faza != ROTIRE:
            return _t('O căutare oarbă e deja în curs pe acest receptor.')
        pregatit = treceri(cerere, osc)
        if pregatit.get('eroare'):
            return pregatit['eroare']
        self._goleste()
        self.cerere = dict(cerere)
        self.trepte = trepte_din(cerere.get('trepte'))
        self.osc = osc
        self.orbpos = self.orbpos_ales = orbpos
        self.nume_satelit = nume_satelit or ''
        self.benzi = pregatit['benzi']
        self.polarizari = pregatit['polarizari']
        self.treceri1 = pregatit['treceri']
        self.cunoscute_toate = list(cunoscute or [])
        self.cunoscute = cunoscute_in_cautare(self.cunoscute_toate, self.benzi, self.polarizari)
        self._candidati = candidati
        self._nume_pozitii = dict(nume_pozitii or {})
        self.t_inceput = self._ceas()
        return self._porneste_etapa(1, self.treceri1)

    def roteste(self, orbpos, nume_satelit='', secunde=0):
        """0.7.7 (M30): antena cu motor se roteste intai spre satelitul ales (rotirea o face partea de receptor, prin
        acordul enigma2); ecranul si pagina arata faza ROTIRE, iar porneste() urmeaza cand antena a ajuns. Intoarce None
        sau textul refuzului."""
        if self.in_curs():
            return _t('O căutare oarbă e deja în curs pe acest receptor.')
        self._goleste()
        self.faza = ROTIRE
        self.orbpos = self.orbpos_ales = orbpos
        self.nume_satelit = nume_satelit or ''
        self.secunde_rotire = int(secunde or 0)
        self.t_inceput = self._ceas()
        self._anunta()
        return None

    def renunta(self, mesaj):
        """Cautarea nu mai porneste (rotirea n-a putut lua tunerul, programul a refuzat): EROARE cu mesajul dat."""
        self.opreste_rotirea = None
        self.faza = EROARE
        self.mesaj = mesaj or mesaj_eroare('')
        self.t_sfarsit = self._ceas()
        self._anunta()

    def _porneste_etapa(self, etapa, lista):
        """O etapa = o lista de treceri, data programului in grupe de cel mult TRECERI_PE_CHEMARE."""
        self.etapa = etapa
        self.faza = CAUTA if etapa == 1 else A_DOUA
        self.treceri_etapa = list(lista)
        if etapa >= 2:
            self.treceri2 += list(lista)
        self._facute = 0
        self.procent = 0
        return self._porneste_lot()

    def _porneste_lot(self):
        self._lot = self.treceri_etapa[self._facute:self._facute + TRECERI_PE_CHEMARE]
        self.trecere = None
        self.nr_trecere = 0
        argv = argv_program(self._lot, self.osc, self.cerere.get('tuner') or 0, self.cerere.get('timp_max'),
                            self.cerere.get('vuplus'), self.cerere.get('rata_min'), self.cerere.get('comutare'))
        try:
            self._proces = self._pornitor(argv, self._la_rand, self._la_iesire)
        except Exception as e:
            print('[HdsCautareOarba] pornirea programului: %s' % e)
            self._proces = None
        if self._proces is None:
            self._termina(EROARE, cod='pornire')
            return self.mesaj
        self._anunta()
        return None

    # ---- randurile programului
    def _la_rand(self, linie):
        ev = citeste_eveniment(linie)
        if not ev:
            return
        tip = ev['tip']
        if tip == 'tp':
            tp = transponder_gasit(ev, self.orbpos)
            if not any(la_fel(tp, g) for g in self.gasite):
                self.gasite.append(tp)
                self._anunta()
        elif tip == 'progres':
            # procentul programului e pe grupa lui; aici, pe toata etapa
            total = max(1, len(self.treceri_etapa))
            self.procent = min(99, int((self._facute + ev['procent'] / 100.0 * len(self._lot)) * 100 / total))
            self._anunta()
        elif tip == 'trecere':
            self.nr_trecere = self._facute + ev['nr']
            self.trecere = self._lot[ev['nr'] - 1] if 0 < ev['nr'] <= len(self._lot) else None
            self._anunta()
        elif tip == 'jurnal':
            if ev['cuvant'] not in ('tp-brut',) and len(self.jurnal) < 400:
                self.jurnal.append((self.etapa, ev['cuvant'], ' '.join(ev['valori'])))
        elif tip in ('gata', 'oprit'):
            self.durata_program_ms += ev['durata_ms']
        elif tip == 'eroare':
            # 'EROARE <cod> <cuvant>': cuvantul scurt spune ce s-a intamplat (frontend-ocupat, init, blocat...)
            self.cod_eroare = ev['text'].split()[0] if ev['text'] else ev['cod']
            self.jurnal.append((self.etapa, 'eroare', '%s %s' % (ev['cod'], ev['text'])))

    def _la_iesire(self, cod=0):
        self._proces = None
        if self.faza == OPRESTE:
            self._termina(OPRIT)
            return
        if self.faza not in (CAUTA, A_DOUA):
            return
        if self.cod_eroare:
            # o eroare dupa ce s-a gasit ceva (de pilda paznicul de timp) lasa ce s-a gasit; altfel cautarea a cazut
            self._termina(OPRIT if self.gasite else EROARE, cod=self.cod_eroare)
            return
        if cod == 3:
            self._termina(OPRIT, cod='timp')
            return
        self._facute += len(self._lot)
        if self._facute < len(self.treceri_etapa):
            self._porneste_lot()
            return
        if self.etapa == 1:
            self._afla_satelitul()
            if not self.gasite:
                # nimic pe toata banda: antena nu primeste nimic aici; golurile ar fi toata banda, fara folos
                self._termina(GATA)
                return
        urmatoarea = self._urmatoarea_etapa()
        if urmatoarea:
            self._porneste_etapa(self.etapa + 1, urmatoarea)
            return
        self._termina(GATA)

    def _urmatoarea_etapa(self):
        """Dupa treptele alese: la 1, numai ferestrele cunoscutelor negasite (cateva secunde); la 2 si golurile; la 3
        golurile inca o data, cu ferestrele decalate."""
        if self.etapa == 1 and self.trepte == 1:
            return ferestre_a_doua(negasite(self.cunoscute, self.gasite), self.benzi)
        if self.etapa < min(self.trepte, ETAPE_MAX):
            return treceri_etapa(self.etapa + 1, self.cunoscute, self.gasite, self.benzi, self.polarizari)
        return []

    def _afla_satelitul(self):
        """Dupa prima trecere: daca gasitele se potrivesc clar mai bine cu alt satelit al antenei, acela e."""
        if self._candidati is None or len(self.gasite) < POTRIVITE_MIN:
            return
        try:
            candidati = self._candidati()
        except Exception as e:
            print('[HdsCautareOarba] satelitii antenei: %s' % e)
            return
        poz, _n, _clasament = identifica_satelit(self.gasite, candidati, self.orbpos_ales)
        if poz is not None and poz != self.orbpos and poz in candidati:
            self.orbpos = poz
            self.nume_satelit = self._nume_pozitii.get(poz) or self.nume_satelit
            self.satelit_schimbat = True
            self.cunoscute_toate = list(candidati[poz])
            self.cunoscute = cunoscute_in_cautare(self.cunoscute_toate, self.benzi, self.polarizari)
            for g in self.gasite:
                g['orbital_position'] = int(poz)

    def _salveaza_jurnal(self):
        """Randurile programului de la ultima cautare, de citit dupa aceea: in memorie se pierd la repornirea interfetei."""
        try:
            with open(CALE_JURNAL, 'w') as f:
                for etapa, cuvant, valori in self.jurnal:
                    f.write('%s %s %s\n' % (etapa, cuvant, valori))
        except (IOError, OSError):
            pass

    def _termina(self, faza, cod=''):
        self.faza = faza
        self.t_sfarsit = self._ceas()
        self._salveaza_jurnal()
        if cod and not self.cod_eroare:
            self.cod_eroare = cod
        if faza == EROARE:
            self.mesaj = mesaj_eroare(self.cod_eroare)
        elif faza == OPRIT and self.cod_eroare == 'blocat':
            self.mesaj = mesaj_eroare('blocat')
        elif faza == OPRIT and self.cod_eroare == 'timp':
            self.mesaj = _t('Căutarea a durat prea mult și s-a oprit. Rămân transponderele găsite până atunci.')
        else:
            self.mesaj = ''
        if faza in (GATA, OPRIT):
            self.procent = 100 if faza == GATA else self.procent
        self._anunta()

    # ---- oprire
    def opreste(self):
        """Cere oprirea curata (programul termina felia in curs). True daca era ceva de oprit. In faza ROTIRE programul
        nu ruleaza inca: cautarea se socoteste oprita, iar rotirea, cand se termina, nu mai porneste nimic."""
        if self.faza == ROTIRE:
            f, self.opreste_rotirea = self.opreste_rotirea, None
            try:
                if f is not None:
                    f()
            except Exception as e:
                print('[HdsCautareOarba] oprirea rotirii: %s' % e)
            self._termina(OPRIT)
            return True
        if self.faza not in (CAUTA, A_DOUA):
            return False
        self.faza = OPRESTE
        self.t_oprire = self._ceas()
        try:
            if self._proces is not None:
                self._proces.opreste()
        except Exception as e:
            print('[HdsCautareOarba] oprirea: %s' % e)
        self._anunta()
        return True

    def verifica(self, acum=None):
        """Chemata din secunda in secunda de receptor: dupa gratie, un program care nu s-a oprit e omorat (iar partea
        de receptor pune tuner_used inapoi). True daca l-a omorat."""
        if self.faza != OPRESTE or self._proces is None:
            return False
        acum = self._ceas() if acum is None else acum
        if acum - self.t_oprire < GRATIE_OPRIRE_S:
            return False
        try:
            self._proces.omoara()
        except Exception as e:
            print('[HdsCautareOarba] omorarea: %s' % e)
        self._proces = None
        self.cod_eroare = 'blocat'
        self._termina(OPRIT, cod='blocat')
        return True

    # ---- ce se arata
    def durata_s(self):
        if not self.t_inceput:
            return 0
        return int((self.t_sfarsit or self._ceas()) - self.t_inceput)

    def rata_min(self):
        return int(self.cerere.get('rata_min') or 0)

    def randuri_acum(self):
        return randuri(self.cunoscute, self.gasite, self.rata_min(), gata=self.faza == GATA,
                       oprita=self.faza in (OPRIT, EROARE))

    def lista_scanare(self):
        """Cunoscutele din benzile si polarizarile cautate + cele noi (ca DVB-S Auto); [] fara satelit stiut."""
        if self.orbpos is None or not (self.gasite or self.cunoscute):
            return []
        return pentru_scanare(self.cunoscute, self.gasite, self.orbpos, self.rata_min())

    def numere(self):
        r = self.randuri_acum()
        return {'noi': sum(1 for x in r if x['stare'] == 'nou'),
                'gasite_cunoscute': sum(1 for x in r if x['stare'] == 'gasit'),
                'cunoscute': len(self.cunoscute),
                'negasite': sum(1 for x in r if x['stare'] in ('negasit', 'cunoscut', 'neverificat'))}

    def text_stare(self):
        """Randul de stare, acelasi pe televizor si in pagina."""
        n = self.numere()
        if self.faza == NIMIC:
            return ''
        if self.faza == ROTIRE:
            return _t('Antena se rotește spre %s (până la %s).') % (self.nume_satelit or text_satelit({}),
                                                                       text_rotire(self.secunde_rotire))
        if self.faza in (CAUTA, A_DOUA):
            return _t('Treapta %d din %d: %d%%. Găsite: %d, noi: %d.') % (
                min(self.etapa, self.trepte), self.trepte, self.procent, len(self.gasite), n['noi'])
        if self.faza == OPRESTE:
            return _t('Se oprește după bucata de bandă în curs...')
        if self.faza == EROARE:
            return self.mesaj
        text = _t('Gata în %d s. Găsite: %d din %d cunoscute, noi: %d.') % (
            self.durata_s(), n['gasite_cunoscute'], n['cunoscute'], n['noi'])
        if self.faza == OPRIT:
            text = (self.mesaj + ' ' if self.mesaj else _t('Oprită.') + ' ') + text
        return text

    def stare(self):
        """Starea, ca dict simplu (pentru pagina web)."""
        return {'faza': self.faza, 'in_curs': self.in_curs(), 'etapa': self.etapa, 'trepte': self.trepte,
                'procent': self.procent,
                'text': self.text_stare(), 'mesaj': self.mesaj, 'durata_s': self.durata_s(),
                'pozitie': self.orbpos, 'satelit': self.nume_satelit, 'satelit_schimbat': self.satelit_schimbat,
                'numere': self.numere(), 'poate_scana': self.faza in (GATA, OPRIT) and bool(self.lista_scanare()),
                'randuri': [{'mhz': int(r['tp']['frequency']) // 1000,
                             'pol': POLARIZARI[int(r['tp']['polarisation']) % 4],
                             'ksym': int(r['tp']['symbol_rate']) // 1000, 'stare': r['stare'],
                             'text_stare': text_stare(r['stare'])} for r in self.randuri_acum()]}


# ---------------------------------------------------------------- pe receptor (enigma2 importat la folosire)
_COMUNA = {'cautare': None, 'ceas': None, 'sesiune': None, 'repune': None, 'standby': False}


class _ProcesReceptor(object):
    """Programul pornit cu eConsoleAppContainer. Oprirea: sendCtrlC (SIGINT pe grup; programul termina felia si pune
    tuner_used inapoi). kill() al containerului e SIGKILL (lib/base/console.cpp), deci numai dupa gratie, cu
    tuner_used pus inapoi de aici."""

    def __init__(self, argv, la_rand, la_iesire):
        from enigma import eConsoleAppContainer
        self._la_rand = la_rand
        self._la_iesire = la_iesire
        self._rest = ''
        # eConsoleAppContainer da octeti: decodati pe masura ce vin (un caracter taiat intre doua citiri iese intreg)
        self._decodor = codecs.getincrementaldecoder('utf-8')('replace')
        self.c = eConsoleAppContainer()
        self.c.dataAvail.append(self._date)
        self.c.appClosed.append(self._inchis)
        if self.c.execute(argv[0], *argv):
            raise RuntimeError('execute')

    def _date(self, data):
        if isinstance(data, (bytes, bytearray)):
            data = self._decodor.decode(data)
        self._rest += data
        while '\n' in self._rest:
            linie, self._rest = self._rest.split('\n', 1)
            self._la_rand(linie)

    def _inchis(self, cod):
        self._rest += self._decodor.decode(b'', True)
        if self._rest:
            self._la_rand(self._rest)
            self._rest = ''
        try:
            del self.c.dataAvail[:]
            del self.c.appClosed[:]
        except Exception:
            pass
        self._la_iesire(cod)

    def opreste(self):
        self.c.sendCtrlC()

    def omoara(self):
        try:
            del self.c.dataAvail[:]
            del self.c.appClosed[:]
        except Exception:
            pass
        self.c.kill()
        tuner_used_inapoi()


def tuner_used_inapoi():
    try:
        with open(TUNER_USED, 'w') as f:
            f.write('0\n')
    except (IOError, OSError) as e:
        print('[HdsCautareOarba] tuner_used: %s' % e)


def cautare():
    """Cautarea comuna a receptorului (ecranul si pagina web vad aceeasi)."""
    if _COMUNA['cautare'] is None:
        c = Cautare(_ProcesReceptor)
        c.adauga_ascultator(_dupa_schimbare)
        _COMUNA['cautare'] = c
    return _COMUNA['cautare']


def _in_standby():
    try:
        from Screens import Standby
        return Standby.inStandby is not None
    except Exception:
        return False


def _porneste_ceasul():
    """Secunda de verificare (gratia opririi), cat ruleaza programul."""
    if _COMUNA['ceas'] is None:
        from enigma import eTimer
        t = eTimer()
        try:
            t.callback.append(lambda: cautare().verifica())
        except AttributeError:
            t.timeout.get().append(lambda: cautare().verifica())
        _COMUNA['ceas'] = t
    _COMUNA['ceas'].start(1000, False)


def _dupa_schimbare(c):
    if c.in_curs():
        return
    if _COMUNA['ceas'] is not None:
        _COMUNA['ceas'].stop()
    try:
        from Components import HdsPaznic
        HdsPaznic.liber(CHEIE_PAZNIC)
    except Exception as e:
        print('[HdsCautareOarba] paznicul: %s' % e)
    _repune_canalul()


def _serviciul_curent(sesiune):
    nav = sesiune.nav
    f = getattr(nav, 'getCurrentlyPlayingServiceOrGroup', None) or nav.getCurrentlyPlayingServiceReference
    return f()


def _repune_canalul():
    """Canalul de dinainte, pornit din nou la sfarsit (nu in standby si nu daca omul a pornit intre timp altul)."""
    sesiune, ref = _COMUNA['sesiune'], _COMUNA['repune']
    _COMUNA['repune'] = None
    if sesiune is None or ref is None or _in_standby() or _COMUNA['standby']:
        return
    try:
        if _serviciul_curent(sesiune) is None:
            sesiune.nav.playService(ref)
    except Exception as e:
        print('[HdsCautareOarba] repunerea canalului: %s' % e)


def tuner_cautare(S, nim, sesiune):
    """Tunerul cautarii oarbe (0.7.7, SCN; tfrc LinuxSat 164155: pana acum mereu primul tuner de satelit). Antena nu se
    misca, deci se cauta acolo unde sta antena canalului pornit: tunerul canalului de satelit pornit acum, cand e unul
    cu antena pusa (ScanerSatelit.slot_serviciu); altfel tunerul care are pozitia de acum (ultima pozitie a motorului,
    ScanerSatelit.pozitie_curenta), daca se stie; altfel primul (slot_satelit), ca pana acum. Cat merge o cautare
    (canalul e oprit) si cat ii stau rezultatele pe ecran fara alt canal pornit, tunerul ramane al ei (cerere["tuner"]),
    ca ecranul, pagina si "Scaneaza canalele" sa nu treaca pe alt tuner. ScanerSatelit = S."""
    sloturi = S.sloturi_satelit(nim)
    try:
        c = cautare()
        al_cautarii = (getattr(c, 'cerere', None) or {}).get('tuner')
        in_curs, ramasa = c.in_curs(), getattr(c, 'faza', NIMIC) != NIMIC
    except Exception as e:
        print('[HdsCautareOarba] tunerul cautarii: %s' % e)
        al_cautarii, in_curs, ramasa = None, False, False
    if al_cautarii not in sloturi:
        al_cautarii = None
    if al_cautarii is not None and in_curs:
        return al_cautarii
    slot, _pozitie = S.slot_serviciu(sesiune)
    if slot is not None and slot in sloturi:
        return slot
    if al_cautarii is not None and ramasa:
        return al_cautarii
    poz = S.pozitie_curenta(sesiune)
    slot = S.slot_pentru(nim, poz) if poz is not None else None
    return slot if slot is not None else S.slot_satelit(nim)


def _modele_tunere(S, nim, slot):
    """[(slot, modelul tunerului din Components/HdsLnb.citeste)]: tunerul cautarii intai, apoi celelalte tunere de
    satelit cu antena pusa (S.sloturi_satelit), fiecare citit o singura data."""
    try:
        from Components import HdsLnb
        sloturi = [slot] + [s for s in S.sloturi_satelit(nim) if s != slot]
    except Exception as e:
        print('[HdsCautareOarba] tunerele: %s' % e)
        return []
    rez = []
    for s in sloturi:
        try:
            rez.append((s, HdsLnb.citeste(s, nim)))
        except Exception as e:
            print('[HdsCautareOarba] setarile tunerului %s: %s' % (s, e))
    return rez


def alegeri_motor(S, nim, slot, sateliti, alegeri):
    """0.7.7 (M30): la tunerul cautarii cu motor (USALS sau DiSEqC 1.2) randul "Satelit" are si
    satelitii la care antena se poate roti: ai tunerului, in ordinea lui, fara cei spre care nucleul nu trimite comanda
    (locul antenei nestabilit, sub orizont: HdsLocul.refuzUsals) si fara cei deja in alegeri -> [(pozitie, slot)].
    Pana acum la motor ramanea numai pozitia de acum, cu nota "Antena nu se misca"."""
    try:
        if not S.are_motor(nim, slot):
            return []
    except Exception:
        return []
    try:
        from Components import HdsLocul
        refuz = HdsLocul.refuzUsals
    except Exception:
        refuz = None
    vazute = set(p for p, _s in alegeri or [])
    rez = []
    for p, _n in sateliti or []:
        if p is None or p in vazute:
            continue
        try:
            if refuz is not None and refuz(slot, p):
                continue
        except Exception:
            pass
        vazute.add(p)
        rez.append((int(p), slot))
    return rez


def secunde_rotire(de_la, la):
    """Cat poate dura cel mult rotirea antenei de pe de_la pe la: termenul acordului care o roteste
    (Hds/DabT2/tuner.Tuner: asezarea dupa arc + 45 s, cel mult 180 s); cu semnal la sosire se termina mai devreme."""
    try:
        from Hds.DabT2 import tuner as hds_tuner
        return min(int(hds_tuner.secunde_asezare(hds_tuner.arc_grade(de_la, la))) + 45, 180)
    except Exception:
        return 60


FEC_TEXT = {0: 'auto', 1: '1/2', 2: '2/3', 3: '3/4', 4: '5/6', 5: '7/8', 6: '8/9', 7: '3/5', 8: '4/5', 9: '9/10'}
MODULATIE_TEXT = {1: 'QPSK', 2: '8PSK', 3: 'QAM16', 4: '16APSK', 5: '32APSK'}
ROLLOFF_TEXT = {0: '0.35', 1: '0.25', 2: '0.20'}


def tp_rotire(poz, cunoscute):
    """Transponderul acordului care roteste antena (forma lui Hds/DabT2/tuner.parametri): cunoscutul cel mai lat al
    satelitului (rata de simbol cea mai mare: de obicei se prinde cel mai usor, iar cu semnal acordul se termina cand
    antena a ajuns; pe Octagonul de proba un 4000 kSym/s neprins a tinut rotirea 70 s in loc de ~20), cu FEC-ul,
    modulatia si roll-off-ul lui; fara cunoscute, unul oarecare pe pozitie: comanda motorului pleaca oricum."""
    bune = sorted(cunoscute or [], key=lambda t: (-int(t.get('symbol_rate') or 0),
                                                  int(t.get('system') or 0) != SISTEM_DVB_S))
    if bune:
        t = bune[0]
        s2 = int(t.get('system') or 0) == SISTEM_DVB_S2
        return {'frecventa': int(t.get('frequency') or 0), 'sr': int(t.get('symbol_rate') or 0),
                'pol': POLARIZARI[int(t.get('polarisation') or 0) % 4], 'pozitie': int(poz),
                'sistem': 'DVB-S2' if s2 else 'DVB-S',
                'modulatie': MODULATIE_TEXT.get(int(t.get('modulation') or 1), 'QPSK'),
                'fec': FEC_TEXT.get(int(t.get('fec') or 0), 'auto'),
                'rolloff': ROLLOFF_TEXT.get(int(t.get('rolloff') or 0), '0.35')}
    return {'frecventa': 11766000, 'sr': 27500000, 'pol': 'H', 'pozitie': int(poz), 'sistem': 'DVB-S',
            'modulatie': 'QPSK', 'fec': 'auto'}


def antena(sesiune, pozitie=None):
    """Ce stie receptorul despre antena tunerului de satelit: {"slot", "pozitie", "nume", "osc", "motor",
    "sateliti", "comutare", "alegeri", "motiv"}; motiv = de ce nu se poate cauta (text), altfel ''. comutare: portul
    DiSEqC / toneburst al satelitului aratat (comutare_din_lnb), numai cand satelitul e stiut.

    0.7.7 (WLD): alegeri = [(pozitie, nume, slot)], satelitii randului "Satelit" (alegeri_satelit; pozitia None =
    "cel pe care sta antena acum"); `pozitie` = satelitul ales acolo: cand e printre alegeri, tot ce intoarce (tunerul,
    oscilatoarele, comutarea, numele) e al lui; altfel ramane satelitul de pana acum (al canalului pornit)."""
    from Screens import ScanerSatelit as S
    rez = {'slot': None, 'pozitie': None, 'nume': '', 'osc': None, 'motor': False, 'sateliti': [], 'comutare': None,
           'alegeri': [], 'motiv': '', 'rotire': False, 'de_la': None, 'secunde_rotire': 0}
    nim = S._nimmanager()
    slot = tuner_cautare(S, nim, sesiune) if nim is not None else None
    if slot is None:
        rez['motiv'] = _t('Receptorul nu are tuner de satelit.')
        return rez
    sateliti = S.sateliti_tuner(nim, slot)
    poz = S.pozitie_curenta(sesiune) if sateliti else None
    pozitii = [p for p, _n in sateliti]
    if poz not in pozitii:
        poz = pozitii[0] if len(pozitii) == 1 else None
    poz_antena, slot_antena = poz, slot
    modele = _modele_tunere(S, nim, slot) if sateliti else []
    if sateliti:
        try:
            nume = dict(S.sateliti_receptor(nim))
        except Exception:
            nume = {}
        nume.update(sateliti)
        alegeri = alegeri_satelit(modele, slot, poz, cu_comanda=model_vuplus() is None)
        alegeri += alegeri_motor(S, nim, slot, sateliti, alegeri)
        rez['alegeri'] = [(p, (nume.get(p) or S.text_pozitie(p)) if p is not None else text_satelit({}), s)
                          for p, s in alegeri]
        ales = pozitie_din(pozitie)
        if ales is not None and ales != poz:
            for p, s in alegeri:
                if p == ales:
                    slot, poz = s, p
                    sateliti = S.sateliti_tuner(nim, slot)
                    pozitii = [x for x, _n in sateliti]
                    break
    rez['slot'] = slot
    rez['sateliti'] = sateliti
    rez['motor'] = bool(S.are_motor(nim, slot))
    # 0.7.7 (M30): satelitul ales nu e cel pe care sta antena cu motor: se roteste intai (porneste_pe_receptor)
    rez['de_la'] = poz_antena
    rez['rotire'] = bool(rez['motor'] and poz is not None and poz != poz_antena and slot == slot_antena)
    rez['secunde_rotire'] = secunde_rotire(poz_antena, poz) if rez['rotire'] else 0
    if not rez['sateliti']:
        rez['motiv'] = _t('Tunerul de satelit nu are niciun satelit configurat. Configurează antena în „Setări tuner”.')
        return rez
    rez['pozitie'] = poz
    if poz is not None:
        rez['nume'] = dict(rez['sateliti']).get(poz) or S.text_pozitie(poz)
    osc = None
    try:
        from Components import HdsLnb
        model = dict(modele).get(slot)
        lnb = HdsLnb.lnbPentruSatelit(slot, poz if poz is not None else pozitii[0], nim, model=model)
        if lnb is not None:
            osc = HdsLnb.oscilatoareKhz(lnb)
            if osc is None:
                rez['motiv'] = _t('Căutarea oarbă nu merge printr-un LNB Unicable.')
                return rez
            if poz is not None:
                rez['comutare'] = comutare_din_lnb(lnb)
    except Exception as e:
        print('[HdsCautareOarba] LNB-ul: %s' % e)
    rez['osc'] = osc
    return rez


def _cunoscute_satelit(poz):
    from Screens import ScanerSatelit as S
    nim = S._nimmanager()
    try:
        bune, _sarite = S.transpondere_satelit(poz, nim.getTransponders(poz))
    except Exception as e:
        print('[HdsCautareOarba] transponderele satelitului %s: %s' % (poz, e))
        return []
    return bune


def porneste_pe_receptor(sesiune, cerere):
    """Pornirea comuna (ecranul si pagina web): antena, cunoscutele, oprirea canalului, semnul paznicului, programul.
    Intoarce None sau textul refuzului."""
    c = cautare()
    if c.in_curs():
        return _t('O căutare oarbă e deja în curs pe acest receptor.')
    import os
    pe_vuplus = model_vuplus() is not None
    if not pe_vuplus and not os.path.exists(PROGRAM):
        return _t('Programul de căutare oarbă nu e instalat pe acest receptor. Îl aduce actualizarea software.')
    # 0.7.7 (WLD): satelitul ales in randul "Satelit" (cerere["pozitie"]); fara el, cel pe care sta antena
    a = antena(sesiune, cerere.get('pozitie'))
    if a['motiv']:
        return a['motiv']
    cerere_omului = cerere
    cerere = dict(cerere)
    cerere['tuner'] = a['slot']
    # satelitul aratat e si cel cautat: comutatorul lui se pune din nou (enigma2 a taiat tensiunea LNB-ului)
    cerere['comutare'] = a.get('comutare')
    if pe_vuplus:
        vu = vuplus_pentru(a['slot'])
        if vu is None:
            return mesaj_eroare('placa-necunoscuta')
        if not os.path.exists(vu['program']):
            return _instaleaza_vuplus(sesiune, cerere_omului, vu)
        cerere['vuplus'] = vu
    poz = a['pozitie']
    cunoscute = _cunoscute_satelit(poz) if poz is not None else []
    sateliti = [p for p, _n in a['sateliti']]

    def candidati():
        return dict((p, _cunoscute_satelit(p)) for p in sateliti)

    # canalul de pe tunerul de satelit se opreste (enigma2 inchide frontend-ul dupa ~3 s; programul asteapta 15 s)
    _COMUNA['sesiune'] = sesiune
    _COMUNA['standby'] = _in_standby()
    _COMUNA['repune'] = None
    try:
        if not _COMUNA['standby'] and sesiune is not None:
            ref = _serviciul_curent(sesiune)
            if ref is not None:
                _COMUNA['repune'] = ref
                sesiune.nav.stopService()
    except Exception as e:
        print('[HdsCautareOarba] oprirea canalului: %s' % e)
    try:
        from Components import HdsPaznic
        HdsPaznic.ocupat(CHEIE_PAZNIC, MOTIV_OARBA, DURATA_OARBA_S)
    except Exception as e:
        print('[HdsCautareOarba] paznicul: %s' % e)
    from Screens import ScanerSatelit as S
    # stopService nu trece prin extensiile de zap: un program DVB-T2 sau un post DAB+ prin satelit si-ar tine releul si
    # sesiunea 8001 (deci tunerul) pana la ~20 s, mai mult decat asteapta programul. Cedeaza acum, ca la ServiceScan,
    # impreuna cu o scanare DVB-T2 / DAB+ care tine inca purtatorul.
    try:
        from Hds.DabT2 import imagine as hds_imagine
        hds_imagine.inainte_de_scanare(_t('Tunerul a fost dat căutării oarbe.'))
        S.elibereaza_cautarile()
    except Exception as e:
        print('[HdsCautareOarba] tunerul pentru cautare (DAB+ / DVB-T2): %s' % e)
    nume = dict((p, n or S.text_pozitie(p)) for p, n in a['sateliti'])
    if a.get('rotire'):
        refuz = _roteste_apoi_cauta(c, a, cerere, poz, cunoscute, candidati if len(sateliti) > 1 else None, nume)
    else:
        refuz = c.porneste(cerere, a['osc'], poz, cunoscute, a['nume'], candidati if len(sateliti) > 1 else None, nume)
    if refuz:
        _dupa_schimbare(c)
        return refuz
    _porneste_ceasul()
    return None


def _roteste_apoi_cauta(c, a, cerere, poz, cunoscute, candidati, nume_pozitii):
    """0.7.7 (M30): antena cu motor, satelit ales altul decat cel pe care sta: acord enigma2 pe un transponder al
    satelitului ales (SEC trimite comanda motorului, Hds/DabT2/tuner.Tuner asteapta oprirea si semnalul, cel mult
    termenul lui), apoi tunerul dat inapoi si programul pornit ca de obicei. Faza ROTIRE pe ecran si in pagina; EXIT o
    opreste (tunerul rotirii se da inapoi imediat). Fara semnal la sosire cautarea porneste totusi: antena a ajuns cat a
    putut, iar programul isi afla singur satelitul dupa prima treapta."""
    try:
        from Hds.DabT2 import tuner as hds_tuner
        t = hds_tuner.Tuner('oarba')
    except Exception as e:
        print('[HdsCautareOarba] tunerul rotirii: %s' % e)
        return mesaj_eroare('')
    refuz = c.roteste(poz, a.get('nume'), a.get('secunde_rotire'))
    if refuz:
        return refuz
    c.opreste_rotirea = t.elibereaza

    def gata(ok, mesaj):
        alocat = bool(getattr(t, 'alocari', 0))
        try:
            t.elibereaza()
        except Exception as e:
            print('[HdsCautareOarba] eliberarea tunerului rotirii: %s' % e)
        if c.faza != ROTIRE:
            return                          # oprita in timpul rotirii
        c.opreste_rotirea = None
        if not alocat:
            # acordul n-a pornit (tunerul ocupat): antena nu s-a miscat, deci nu se cauta pe alt satelit
            c.renunta(mesaj)
            return
        print('[HdsCautareOarba] rotirea spre %s gata (%s): pornesc cautarea' % (poz, 'semnal' if ok else mesaj))
        refuz2 = c.porneste(cerere, a['osc'], poz, cunoscute, a['nume'], candidati, nume_pozitii)
        if refuz2:
            c.renunta(refuz2)
        else:
            _porneste_ceasul()

    t.acordeaza(tp_rotire(poz, cunoscute), gata)
    return None


# ---------------------------------------------------------------- Vu+ Solo SE: programul producatorului, adus la cerere
def model_vuplus(cale=VUMODEL):
    """Modelul Vu+ cu drum de cautare oarba (MODELE_VUPLUS), din /proc/stb/info/vumodel, sau None."""
    try:
        with open(cale) as f:
            model = f.read(64).strip().lower()
    except (IOError, OSError):
        return None
    return model if model in MODELE_VUPLUS else None


def vuplus_pentru(slot, **unde):
    """{'adaptor', 'program', 'i2c', 'cip'} pentru tunerul din slot (HdsOarbaVuplus.program_pentru), sau None."""
    from Components import HdsOarbaVuplus as V
    vu = V.program_pentru(slot, **unde)
    if vu is not None:
        vu['adaptor'] = V.__file__
    return vu


def _arata(text):
    """Un mesaj pe televizor dupa o lucrare in fundal (instalarea programului Vu+), cand ecranul cautarii e inchis."""
    try:
        from Tools import Notifications
        from Screens.MessageBox import MessageBox
        Notifications.AddPopup(text, MessageBox.TYPE_INFO, 15, 'HdsCautareOarba')
    except Exception as e:
        print('[HdsCautareOarba] %s (%s)' % (text, e))


class _CeasSecunda(object):
    """Bataia de o secunda a instalarii programului Vu+ (eTimer), una singura pentru toti pasii."""

    def __init__(self, f):
        from enigma import eTimer
        self._t = eTimer()
        try:
            self._t.callback.append(f)
        except AttributeError:
            self._t.timeout.get().append(f)

    def start(self):
        self._t.start(1000, False)

    def stop(self):
        self._t.stop()


def _pe_fir(lucru, gata):
    """lucru() pe un fir separat, gata(rezultat, eroare) pe firul interfetei."""
    import threading
    from twisted.internet import reactor

    def alearga():
        rez, err = None, None
        try:
            rez = lucru()
        except Exception as e:
            err = e
        reactor.callFromThread(gata, rez, err)
    threading.Thread(target=alearga, name='HdsCautareOarba', daemon=True).start()


# 0.7.7 (BSC, e-mailul 6525, Vu+ Solo SE 0.7.6): fiecare pas al aducerii programului Vu+ are o limita de timp; pana atunci
# ecranul putea ramane pe „se descarca” fara sfarsit, iar esecul aparea numai ca fereastra, abia dupa inchiderea ecranelor.
# Acum pasul curent, cu timpul scurs, si motivul esecului se vad pe ecranul cautarii oarbe si in pagina web.
LIMITE_S = {'citesc': 120, 'lista': 300, 'astept': 300, 'instalare': 300}
TEXTE_PAS = {
    'citesc': N_('Pregătesc căutarea oarbă: citesc lista de programe (%s).'),
    'lista': N_('Pregătesc căutarea oarbă: descarc lista de programe de pe internet (%s).'),
    'astept': N_('Pregătesc căutarea oarbă: aștept să se termine altă instalare (%s).'),
    'instalare': N_('Pregătesc căutarea oarbă: instalez programul Vu+ (%s). Căutarea pornește singură după aceea.'),
}
TEXTE_TERMEN = {
    'citesc': N_('Lista de programe nu s-a putut citi în %d minute. Încearcă din nou.'),
    'lista': N_('Lista de programe de pe internet nu s-a descărcat în %d minute. Verifică legătura la internet și '
                'încearcă din nou.'),
    'astept': N_('Altă instalare ține receptorul ocupat de %d minute. Încearcă din nou după ce se termină.'),
    'instalare': N_('Instalarea programului Vu+ pentru căutarea oarbă nu s-a terminat în %d minute. Verifică legătura '
                    'la internet și încearcă din nou.'),
}
# cat timp se mai arata un esec (ecranul cautarii, pagina web), daca omul nu incearca din nou
ESEC_ARATAT_S = 600


def _ceas_text(secunde):
    secunde = max(0, int(secunde))
    return '%d:%02d' % (secunde // 60, secunde % 60)


class InstalareVuplus(object):
    """Aduce o singura data programul Vu+ (PACHET_VUPLUS) din feed, pe drumul Extensiilor (catalogul; lista de pe
    internet reimprospatata daca pachetul nu e in ea; lucrarea opkg), apoi cheama dupa() (care intoarce None sau textul
    unui refuz). Numai pe firul interfetei. Faze: nimic, citesc, lista, astept (alta lucrare opkg), instalare, gata, eroare.
    text(): pasul curent cu timpul scurs sau, dupa un esec, ce a cazut; il arata ecranul cautarii (ascultatorii) si pagina
    web (stare()). Fara ascultator (ecranul inchis), esecul vine si ca fereastra. Fiecare pas are limita lui (LIMITE_S)."""

    def __init__(self, X=None, pe_fir=None, ceas=None, arata=None, timp=None):
        self._x = X
        self._pe_fir = pe_fir or _pe_fir
        self._fabrica_ceas = ceas or _CeasSecunda
        self._ceas = None
        self._arata = arata or _arata
        self._timp = timp or time.time
        self.faza = 'nimic'
        self.dupa = None
        self.lucrare = None
        self.eroare = ''
        self._cand_eroare = 0
        self._din = 0                 # cand a inceput pasul curent
        self._citire = 0              # numarul citirii: raspunsul unei citiri ramase dupa termen nu mai conteaza
        self._lista_ceruta = False    # descarcarea listei pornita de noi (abia dupa ea lipsa pachetului e un raspuns)
        self._descarcare_veche = None  # STARE['descarcare'] dinaintea descarcarii noastre (motivul nu se ia de acolo)
        self._ascultatori = []

    def X(self):
        if self._x is None:
            from Components import HdsExtensiiLucru
            self._x = HdsExtensiiLucru
        return self._x

    # ---------------------------------------------------------------- starea, pentru ecran si pagina
    def in_curs(self):
        return self.faza in ('citesc', 'lista', 'astept', 'instalare')

    def esec_recent(self):
        return self.faza == 'eroare' and self._timp() - self._cand_eroare < ESEC_ARATAT_S

    def text(self):
        if self.in_curs():
            return _t(TEXTE_PAS[self.faza]) % _ceas_text(self._timp() - self._din)
        if self.esec_recent():
            return self.eroare
        return ''

    def stare(self):
        return {'faza': self.faza, 'in_curs': self.in_curs(), 'eroare': self.esec_recent(), 'text': self.text()}

    def adauga_ascultator(self, f):
        if f not in self._ascultatori:
            self._ascultatori.append(f)

    def scoate_ascultator(self, f):
        if f in self._ascultatori:
            self._ascultatori.remove(f)

    def _anunta(self):
        for f in list(self._ascultatori):
            try:
                f(self)
            except Exception as e:
                print('[HdsCautareOarba] ascultatorul instalarii: %s' % e)

    # ---------------------------------------------------------------- pasii
    def porneste(self, dupa):
        self.dupa = dupa
        if self.in_curs():
            return
        self._lista_ceruta = False
        self.eroare = ''
        self._citeste()

    def _pas(self, faza):
        self.faza = faza
        self._din = self._timp()
        if self._ceas is None:
            self._ceas = self._fabrica_ceas(self._bataie)
        self._ceas.start()
        self._anunta()

    def _opreste_ceasul(self):
        if self._ceas is not None:
            self._ceas.stop()

    def _citeste(self):
        self._citire += 1
        n = self._citire
        self._pas('citesc')
        self._pe_fir(self.X().incarcaCatalog, lambda catalog, eroare: self._catalog(catalog, eroare, n))

    def _esec(self, text):
        self.faza = 'eroare'
        self.eroare = text
        self._cand_eroare = self._timp()
        self.dupa = None
        self._opreste_ceasul()
        print('[HdsCautareOarba] programul Vu+: %s' % text)
        if not self._ascultatori:
            self._arata(text)
        self._anunta()

    def _ocupat(self):
        """o descarcare a listei sau o alta lucrare opkg (televizor sau pagina) in curs, ori rezerva feedului programata"""
        X = self.X()
        return bool(X.descarcareInCurs() or X.lucrareInCurs() or X.rezervaAsteapta())

    def _stare_descarcare(self):
        return (getattr(self.X(), 'STARE', None) or {}).get('descarcare')

    def _motiv_lista(self):
        """motivul dat de opkg pentru descarcarea listei pornita de noi, cand a cazut, sau '' (nu al uneia mai vechi)"""
        d = self._stare_descarcare()
        if not d or d is self._descarcare_veche or d.get('cod') in (0, None):
            return ''
        return d.get('motiv') or ''

    def _descarca_lista(self):
        """opkg update, pornit de noi, numai cand receptorul e liber; altfel bataia il porneste cand se elibereaza"""
        if self._ocupat():
            return False
        self._descarcare_veche = self._stare_descarcare()
        self._lista_ceruta = True
        self.X().pornesteDescarcarea()
        return True

    def _catalog(self, catalog, eroare, n=None):
        if (n is not None and n != self._citire) or self.faza != 'citesc':
            return
        if eroare is not None or catalog is None:
            return self._esec(_t('Nu am putut citi lista de programe. Încearcă din nou.'))
        X = self.X()
        p = catalog._toate.get(PACHET_VUPLUS)
        if p is None:
            if self._lista_ceruta:
                motiv = self._motiv_lista()
                if motiv:
                    return self._esec(_t('Lista de programe de pe internet nu s-a descărcat: %s') % motiv)
                return self._esec(_t('Programul Vu+ pentru căutarea oarbă nu e în lista de pe internet. Verifică '
                                     'legătura la internet și încearcă din nou.'))
            self._descarca_lista()
            # lista se citeste din nou la prima bataie dupa sfarsitul descarcarii (sau o porneste bataia, daca acum
            # lucra alt opkg)
            self._pas('lista')
            return
        if self._ocupat():
            self._pas('astept')
            return
        ocupat = X.motivOcupat()
        if ocupat is not None:
            return self._esec(ocupat[0])
        plan, eroare_plan = X.planInstalare(catalog, p)
        if plan is None:
            return self._esec(eroare_plan[0])
        from Components.PluginComponent import plugins
        # un program, nu o extensie: fara „Reporneste interfata” in rezultatul lucrarii
        plan['repornire'] = False
        self._pas('instalare')
        self.lucrare = X.pornesteLucrarea(plan, plugins=plugins, din_web=False)
        self.lucrare.asculta(self._lucrare)

    def _bataie(self):
        """o data pe secunda, cat ruleaza un pas: sfarsitul asteptarii, limita de timp, textul cu secundele"""
        if not self.in_curs():
            self._opreste_ceasul()
            return
        if self._timp() - self._din >= LIMITE_S[self.faza]:
            return self._termen()
        if self.faza in ('lista', 'astept') and not self._ocupat():
            if self.faza == 'lista' and not self._lista_ceruta:
                self._descarca_lista()
            else:
                return self._citeste()
        self._anunta()

    def _termen(self):
        faza = self.faza
        l, self.lucrare = self.lucrare, None
        if faza == 'instalare' and l is not None:
            l.lasa(self._lucrare)
            # opkg tacut de un minut (retea blocata): oprit, ca la EXIT in Extensii; altfel isi termina treaba singur
            try:
                if l.poateOpri():
                    l.opreste()
            except Exception as e:
                print('[HdsCautareOarba] oprirea instalarii: %s' % e)
        self._esec(_t(TEXTE_TERMEN[faza]) % (LIMITE_S[faza] // 60))

    def _lucrare(self, fel, *date):
        if fel != 'gata' or self.faza != 'instalare':
            return
        l, self.lucrare = self.lucrare, None
        rez = getattr(l, 'rezultat', None) or {}
        if rez and not rez.get('reusit'):
            motiv = rez.get('stare') or ''
            if motiv:
                return self._esec(_t('Programul Vu+ pentru căutarea oarbă nu s-a instalat: %s') % motiv)
            return self._esec(_t('Programul Vu+ pentru căutarea oarbă nu s-a putut instala.'))
        self.faza = 'gata'
        self._opreste_ceasul()
        dupa, self.dupa = self.dupa, None
        refuz = dupa() if dupa is not None else None
        if refuz:
            return self._esec(refuz)
        self._anunta()


_INSTALARE = []


def instalare_vuplus():
    if not _INSTALARE:
        _INSTALARE.append(InstalareVuplus())
    return _INSTALARE[0]


def _instaleaza_vuplus(sesiune, cerere, vu, i=None):
    """Porneste aducerea programului Vu+ si, la sfarsit, cautarea ceruta (fara alt pas al omului). Intoarce textul de aratat
    (pasul curent sau esecul); ecranul cautarii si pagina web il urmaresc apoi prin instalare_vuplus()."""
    import os
    i = i or instalare_vuplus()

    def dupa():
        if not os.path.exists(vu['program']):
            return _t('Instalarea programului Vu+ pentru căutarea oarbă nu a reușit. Verifică legătura la internet '
                      'și încearcă din nou.')
        return porneste_pe_receptor(sesiune, cerere)
    i.porneste(dupa)
    return i.text() or _t('Programul Vu+ pentru căutarea oarbă se instalează. Căutarea pornește singură după instalare.')


def scaneaza_canalele(sesiune):
    """'Scanează canalele': ServiceScan obisnuit pe cunoscute + noi. Intoarce None sau textul refuzului."""
    c = cautare()
    lista = c.lista_scanare()
    if c.in_curs() or not lista:
        return _t('Nu e nimic de scanat încă.')
    try:
        from enigma import eDVBFrontendParametersSatellite
        from Screens.ServiceScan import ServiceScan
        from Screens import ScanerSatelit as S
        # pe tunerul pe care s-a cautat (0.7.7, SCN), nu pe cel al canalului pornit intre timp
        slot = (c.cerere or {}).get('tuner')
        if slot is None:
            slot = antena(sesiune)['slot']
        parametri = [S.in_parametri(eDVBFrontendParametersSatellite, tp) for tp in lista
                     if not S.motiv_refuz(tp)]
        sesiune.open(ServiceScan, [{"transponders": parametri, "feid": slot, "flags": 0,
                                    "hds_fel": "satelit/oarba"}])
    except Exception as e:
        print('[HdsCautareOarba] ServiceScan: %s' % e)
        return _t('Scanarea canalelor nu a putut porni.')
    return None

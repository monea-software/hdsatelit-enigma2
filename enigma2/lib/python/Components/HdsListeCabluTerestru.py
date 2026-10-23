# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsListeCabluTerestru.py: listele de frecvente pentru scanarea prin cablu si pentru scanarea terestra.

Scris de la zero.

Aici stau datele si regulile folosite de Screens/ScanerCablu.py, de Screens/ScanerTerestru.py si de interfata
web, ca sa existe un singur adevar:
  - cititorii pentru /etc/tuxbox/cables.xml si /etc/tuxbox/terrestrial.xml, cu tara fiecarei liste (atributul
    countrycode, pe care lib/dvb/db.cpp nu il citeste, deci NimManager nu il are);
  - emitatoarele romanesti ale retelei MUX1 (data/terestru-romania.json, sursa: lista oficiala Radiocom), pe judete;
  - operatorii de cablu romanesti (data/cablu-romania.json: frecventa de pornire, rata, modulatia si sursele lor),
    pusi inaintea listelor din cables.xml, care pentru Romania are numai lista „DIGI Bucharest”;
  - tabelul canalelor terestre (VHF III 5-12, UHF 21-69) si maturarile de banda;
  - tara utilizatorului si trecerea de la codul de 2 litere la cel de 3 litere din fisierele XML;
  - ce primeste nucleul imaginii (lib/dvb/frontendparms.h, lib/dvb/frontend.cpp) si ce nu.

Nu importa nimic din enigma la incarcare, ca sa poata fi incercat si pe PC
(test_scanare_cablu_terestru.py).

Unitatile, la granita cu nucleul (le schimba o singura data cine construieste transponderul, nimeni altcineva):
  cablu:    frequency in kHz (prepare_cable din frontend.cpp o inmulteste cu 1000), symbol_rate in simboluri/s;
  terestru: frequency in Hz (prepare_terrestrial o trimite neschimbata).
"""
from __future__ import absolute_import, unicode_literals
import io
import json
import os
import xml.etree.ElementTree as ET

from Components.HdsLatimeText import (FONT_RAND_ALEGERE, INDENT, LATIME_RAND_ALEGERE, latime as latime_text,
                                      text_incapator)

CALE_CABLURI = '/etc/tuxbox/cables.xml'
CALE_TERESTRU = '/etc/tuxbox/terrestrial.xml'
FISIER_ROMANIA = 'terestru-romania.json'
# operatorii de cablu romanesti cu parametri verificati (frecventa de pornire, rata, modulatia, sursele); None = se
# cauta langa datele imaginii (_cale_date); probele pun aici o cale anume
FISIER_CABLU_ROMANIA = 'cablu-romania.json'
CALE_CABLU_ROMANIA = None



def _forma_ro(unu, multe, n):
    """Fara Components/HdsPlural (modulul incarcat singur): pluralul din catalogul instalat de enigma2, daca e; altfel
    forma romaneasca (msgid-urile sunt in romana): unu pentru n == 1, altfel multe, fara "de" ("20 canale")."""
    try:
        import builtins
        f = getattr(getattr(builtins.__dict__.get("_"), "__self__", None), "ngettext", None)
        if f is not None:
            return f(unu, multe, n)
    except Exception:
        pass
    return unu if n == 1 else multe


def ngettext(unu, multe, n):
    """Pluralul tradus (Components/HdsPlural.ngettext: formele din Plural-Forms ale limbii, intors ca Forma, al carei %
    merge si cand forma pentru 1 n-are numarul, ca "un canal" din ro.po). Fara pachetul Components (probele de pe PC),
    forma romaneasca de mai sus. Numele e cel stiut de xgettext."""
    try:
        from Components.HdsPlural import ngettext as plural
    except ImportError:
        return _forma_ro(unu, multe, n)
    return plural(unu, multe, n)


# ---------------------------------------------------------------- ce are nucleul (lib/dvb/frontendparms.h)
# eDVBFrontendParametersCable, randurile 50-70
CAB_MOD_AUTO, CAB_QAM16, CAB_QAM32, CAB_QAM64, CAB_QAM128, CAB_QAM256 = 0, 1, 2, 3, 4, 5
CAB_MODULATII = (0, 1, 2, 3, 4, 5)
CAB_FEC_AUTO = 0
CAB_FEC = (0, 1, 2, 3, 4, 5, 6, 15)
INV_AUTO = 2
INVERSARI = (0, 1, 2)
# eDVBFrontendParametersTerrestrial, randurile 72-113
TER_BW_8, TER_BW_7, TER_BW_6, TER_BW_AUTO = 0, 1, 2, 3
TER_BENZI = (0, 1, 2, 3)
TER_MOD_AUTO = 3
TER_MODULATII = (0, 1, 2, 3)               # QPSK, 16QAM, 64QAM, Auto; 256QAM exista doar la DVB-T2
TER_FEC_AUTO, TER_TM_AUTO, TER_GI_AUTO, TER_IER_AUTO = 5, 2, 4, 4
# DVB-T2: structura din nucleu NU are campurile `system` si `plp_id`, iar frontend.cpp (switchDeliverySystem,
# randul 2740) trimite mereu SYS_DVBT. Codul de mai jos le pune numai daca structura le are (nucleul_stie_dvbt2),
# deci cu un nucleu care le adauga merg fara nicio schimbare aici.
SISTEM_DVBT, SISTEM_DVBT2 = 0, 1
CAMPURI_CABLU = ('frequency', 'symbol_rate', 'modulation', 'inversion', 'fec_inner')
CAMPURI_TERESTRU = ('frequency', 'bandwidth', 'code_rate_HP', 'code_rate_LP', 'modulation', 'transmission_mode',
                    'guard_interval', 'hierarchy', 'inversion')
CAMPURI_DVBT2 = ('system', 'plp_id')

# ---------------------------------------------------------------- limite
# Banda in care lucreaza tunerele de cablu si terestre din Europa: 47 MHz (VHF I) pana la 862 MHz (UHF 69).
FRECV_MIN_MHZ, FRECV_MAX_MHZ = 47, 862
# Rata de simbol la cablu: NimManager.py (scan_sr_ext1/2) primeste pentru maturare numai valori peste 450 si cel
# mult 7230 kSymb/s. Retelele europene folosesc aproape toate 6900 sau 6875 kSymb/s.
SR_CABLU_MIN, SR_CABLU_MAX = 450, 7230
SR_CABLU_OBISNUITE = (6900, 6875)
# Cat asteapta nucleul la o frecventa fara semnal inainte sa treaca la urmatoarea (frontend.cpp:442-445, cablu si
# terestru): 5 secunde. De aici vine durata cea mai lunga a unei maturari, aratata utilizatorului dinainte.
SECUNDE_ACORDARE = 5

# Maturarea de cablu: raster de 8 MHz de la 122 la 858 MHz, 93 de frecvente, acelasi ca lista de maturare cu pas
# de 8 MHz, SR 6875/6900 si QAM 64/256 din cables.xml. Se face aici, nu se ia din fisier, fiindca nu stim ce
# versiune a fisierului e pe fiecare receptor.
FRECVENTE_CABLU_MHZ = tuple(range(122, 859, 8))

# Canalele terestre din Europa (planul GE06 al ITU, la fel ca lista „Europe, Middle East, Africa" din
# terrestrial.xml): VHF III canalele 5-12 pe 7 MHz, de la 177,5 MHz; UHF canalele 21-69 pe 8 MHz, de la 474 MHz.
CANALE_VHF = tuple(range(5, 13))
CANALE_UHF = tuple(range(21, 70))


def _int(v, implicit):
    try:
        return int(v)
    except (ValueError, TypeError):
        return implicit


# ---------------------------------------------------------------- canale terestre
def frecventa_canal(canal):
    """Frecventa centrala a canalului, in Hz, sau None pentru un canal care nu e in tabel."""
    canal = _int(canal, 0)
    if canal in CANALE_UHF:
        return (474 + 8 * (canal - 21)) * 1000000
    if canal in CANALE_VHF:
        return 177500000 + 7000000 * (canal - 5)
    return None


def latime_canal(canal):
    """Latimea de banda a canalului, cu codul din nucleu: 8 MHz in UHF, 7 MHz in VHF III."""
    return TER_BW_7 if _int(canal, 0) in CANALE_VHF else TER_BW_8


def canal_din_frecventa(hz):
    """Canalul a carui frecventa centrala e la cel mult 1 MHz de cea data, sau None."""
    for canal in CANALE_VHF + CANALE_UHF:
        if abs(frecventa_canal(canal) - _int(hz, 0)) <= 1000000:
            return canal
    return None


def canale(cu_vhf=True):
    return list(CANALE_VHF + CANALE_UHF) if cu_vhf else list(CANALE_UHF)


def mhz(hz):
    """474000000 -> '474', 177500000 -> '177,5'"""
    hz = _int(hz, 0)
    if hz % 1000000 == 0:
        return '%d' % (hz // 1000000)
    return ('%.3f' % (hz / 1000000.0)).rstrip('0').rstrip('.').replace('.', ',')


def hz_din_mhz(text):
    """'474' -> 474000000, '177,5' sau '177.5' -> 177500000, orice altceva -> None."""
    try:
        valoare = float(str(text).strip().replace(',', '.'))
    except (ValueError, TypeError):
        return None
    if valoare <= 0:
        return None
    return int(round(valoare * 1000)) * 1000


# ---------------------------------------------------------------- transpondere (dict, in unitatile nucleului)
def tp_cablu(frecventa_khz, sr_simb, modulatie=CAB_MOD_AUTO, fec=CAB_FEC_AUTO, inversare=INV_AUTO):
    return {'frequency': _int(frecventa_khz, 0), 'symbol_rate': _int(sr_simb, 0), 'modulation': _int(modulatie, 0),
            'fec_inner': _int(fec, 0), 'inversion': _int(inversare, INV_AUTO)}


def tp_terestru(frecventa_hz, latime=TER_BW_AUTO, modulatie=TER_MOD_AUTO, inversare=INV_AUTO, sistem=None,
                plp=None, crh=TER_FEC_AUTO, crl=TER_FEC_AUTO, gi=TER_GI_AUTO, tm=TER_TM_AUTO, ierarhie=TER_IER_AUTO):
    """sistem: None (nestiut, de exemplu la maturare), SISTEM_DVBT sau SISTEM_DVBT2."""
    return {'frequency': _int(frecventa_hz, 0), 'bandwidth': _int(latime, TER_BW_AUTO),
            'code_rate_HP': crh, 'code_rate_LP': crl, 'modulation': _int(modulatie, TER_MOD_AUTO),
            'transmission_mode': tm, 'guard_interval': gi, 'hierarchy': ierarhie,
            'inversion': _int(inversare, INV_AUTO), 'system': sistem, 'plp_id': plp}


def tp_canal(canal, sistem=None):
    return tp_terestru(frecventa_canal(canal), latime_canal(canal), sistem=sistem)


def maturare_cablu(sr_uri=SR_CABLU_OBISNUITE, modulatii=(CAB_QAM256, CAB_QAM64), frecvente_mhz=FRECVENTE_CABLU_MHZ):
    """Toate combinatiile frecventa x rata x modulatie. Nucleul le pastreaza pe toate (lib/dvb/scan.cpp, start:
    la cablu, doua transpondere cu modulatie sau rata diferita nu sunt „acelasi canal")."""
    return [tp_cablu(f * 1000, sr * 1000, m) for f in frecvente_mhz for sr in sr_uri for m in modulatii]


def maturare_terestru(cu_vhf=True):
    return [tp_canal(c) for c in canale(cu_vhf)]


def minute_maxime(numar_transpondere):
    """Cat poate dura cel mult o scanare (fiecare frecventa fara semnal costa SECUNDE_ACORDARE), in minute."""
    return max(1, (numar_transpondere * SECUNDE_ACORDARE + 59) // 60)


# ---------------------------------------------------------------- ce primeste nucleul
def motiv_refuz_cablu(tp):
    """De ce nu are rost sa trimitem transponderul (text), sau None. prepare_cable nu refuza nimic: orice cod
    necunoscut devine Auto, iar o frecventa sau o rata gresita dau doar 0 canale, fara motiv."""
    f, sr = tp.get('frequency', 0), tp.get('symbol_rate', 0)
    if not FRECV_MIN_MHZ * 1000 <= f <= FRECV_MAX_MHZ * 1000:
        return _('frecvența %s MHz e în afara benzii de cablu (%d-%d MHz)') % (mhz(f * 1000), FRECV_MIN_MHZ, FRECV_MAX_MHZ)
    if not SR_CABLU_MIN * 1000 < sr <= SR_CABLU_MAX * 1000:
        return _('rata de simbol %d kSymb/s nu e primită de tuner (%d-%d kSymb/s; rețelele folosesc de obicei '
                 '6900 sau 6875)') % (sr // 1000, SR_CABLU_MIN, SR_CABLU_MAX)
    if tp.get('modulation') not in CAB_MODULATII:
        return _('modulație pe care imaginea nu o știe încă')
    return None


def motiv_refuz_terestru(tp):
    f = tp.get('frequency', 0)
    if not FRECV_MIN_MHZ * 1000000 <= f <= FRECV_MAX_MHZ * 1000000:
        return _('frecvența %s MHz e în afara benzii terestre (%d-%d MHz)') % (mhz(f), FRECV_MIN_MHZ, FRECV_MAX_MHZ)
    if tp.get('bandwidth') not in TER_BENZI:
        return _('lățime de bandă pe care imaginea nu o știe (numai 8, 7, 6 MHz și Auto)')
    if tp.get('modulation') not in TER_MODULATII:
        return _('modulație pe care imaginea nu o știe încă (256QAM e numai la DVB-T2)')
    return None


def nucleul_stie_dvbt2(clasa):
    """True numai daca structura eDVBFrontendParametersTerrestrial are campul `system`, adica cu un nucleu care
    stie DVB-T2. Se intreaba clasa, nu un obiect: la SWIG campurile structurii sunt proprietati ale clasei."""
    return hasattr(clasa, 'system')


def cere_dvbt2(transpondere):
    return any(tp.get('system') == SISTEM_DVBT2 for tp in transpondere)


def in_parametri(clasa, tp):
    """dict -> obiectul de nucleu (eDVBFrontendParametersCable sau ...Terrestrial); clasa se primeste ca proba sa
    poata folosi una simulata. Campurile DVB-T2 se pun numai daca structura le are. Intoarce (obiect, nepuse):
    nepuse = campurile cerute pe care nucleul nu le poate primi (DVB-T nu intra aici, e oricum ce trimite)."""
    parm = clasa()
    nepuse = []
    for camp, valoare in tp.items():
        if valoare is None:
            continue
        if camp in CAMPURI_DVBT2 and not hasattr(clasa, camp):
            if not (camp == 'system' and valoare == SISTEM_DVBT):
                nepuse.append(camp)
            continue
        setattr(parm, camp, valoare)
    return parm, nepuse


def tuner_pentru(nimmanager, tip):
    """(slot, None) pentru primul tuner care stie `tip` ('DVB-C' sau 'DVB-T') si nu e trecut pe „nimic conectat"
    in Setari tuner, sau (None, motiv). ScanSetup sare si el tunerele oprite; ServiceScan ar da pe ele doar o
    eroare fara explicatie. Pe Viper 4K V20 tunerul B e combinat, DVB-C si DVB-T pe acelasi slot."""
    oprit = None
    for nim in getattr(nimmanager, 'nim_slots', []):
        if not nim.isCompatible(tip):
            continue
        try:
            nimic = nim.config_mode == 'nothing'
        except Exception:
            nimic = False
        if not nimic:
            return nim.slot, None
        if oprit is None:
            oprit = nim.slot
    fel = _('de cablu') if tip == 'DVB-C' else _('terestru')
    if oprit is not None:
        return None, _('Tunerul %s (%s) e trecut pe „nimic conectat” în Setări tuner. Pornește-l acolo, apoi '
                       'revino aici.') % (fel, chr(ord('A') + oprit))
    return None, _('Receptorul nu are niciun tuner %s.') % fel


# ---------------------------------------------------------------- tara utilizatorului
# Codul de 2 litere (din config.osd.language, ca la operatorii de satelit) -> codul de 3 litere din cables.xml si
# terrestrial.xml. Components/Language.py scrie sarba „YU" (nu „RS"); engleza are „EN", care nu e o tara, deci
# pentru ea nu iese nicio potrivire si listele raman doar pe tari.
ALFA3 = {
    'RO': 'ROU', 'MD': 'MDA', 'HU': 'HUN', 'BG': 'BGR', 'RS': 'SRB', 'YU': 'SRB', 'UA': 'UKR', 'DE': 'DEU',
    'AT': 'AUT', 'CH': 'CHE', 'NL': 'NLD', 'BE': 'BEL', 'FR': 'FRA', 'GB': 'GBR', 'IE': 'IRL', 'ES': 'ESP',
    'PT': 'PRT', 'IT': 'ITA', 'GR': 'GRC', 'PL': 'POL', 'CZ': 'CZE', 'SK': 'SVK', 'SI': 'SVN', 'HR': 'HRV',
    'RU': 'RUS', 'EE': 'EST', 'LV': 'LVA', 'LT': 'LTU', 'FI': 'FIN', 'SE': 'SWE', 'NO': 'NOR', 'DK': 'DNK',
    'IS': 'ISL', 'TR': 'TUR', 'IL': 'ISR', 'AD': 'AND', 'AE': 'ARE', 'BR': 'BRA', 'AU': 'AUS', 'NZ': 'NZL',
    'CN': 'CHN', 'TH': 'THA', 'UZ': 'UZB',
}


def nume_tara(cod3):
    """Numele tarii in limba aleasa; codul, daca tara nu e in tabel."""
    nume = {
        'ROU': _('România'), 'MDA': _('Republica Moldova'), 'HUN': _('Ungaria'), 'BGR': _('Bulgaria'),
        'SRB': _('Serbia'), 'UKR': _('Ucraina'), 'DEU': _('Germania'), 'AUT': _('Austria'), 'CHE': _('Elveția'),
        'NLD': _('Țările de Jos'), 'BEL': _('Belgia'), 'FRA': _('Franța'), 'GBR': _('Regatul Unit'),
        'IRL': _('Irlanda'), 'ESP': _('Spania'), 'PRT': _('Portugalia'), 'ITA': _('Italia'), 'GRC': _('Grecia'),
        'POL': _('Polonia'), 'CZE': _('Cehia'), 'SVK': _('Slovacia'), 'SVN': _('Slovenia'), 'HRV': _('Croația'),
        'RUS': _('Rusia'), 'EST': _('Estonia'), 'LVA': _('Letonia'), 'LTU': _('Lituania'), 'FIN': _('Finlanda'),
        'SWE': _('Suedia'), 'NOR': _('Norvegia'), 'DNK': _('Danemarca'), 'ISL': _('Islanda'), 'TUR': _('Turcia'),
        'ISR': _('Israel'), 'AND': _('Andorra'), 'ARE': _('Emiratele Arabe Unite'), 'BRA': _('Brazilia'),
        'AUS': _('Australia'), 'NZL': _('Noua Zeelandă'), 'CHN': _('China'), 'THA': _('Thailanda'),
        'UZB': _('Uzbekistan'),
    }
    return nume.get(cod3, cod3 or _('fără țară'))


def tara_din_limba(limba):
    """'ro_RO' -> 'RO'; 'sr_YU' -> 'RS'; '' daca limba nu are bucata de tara."""
    if not limba or '_' not in limba:
        return ''
    tara = limba.split('_', 1)[1].upper()
    return 'RS' if tara == 'YU' else tara


_DIN_SATELIT = None      # functia din HdsOperatoriSatelit, cautata o singura data (False = lipseste)


def tara_utilizatorului():
    """Codul de 2 litere al tarii utilizatorului. Intai din Components/HdsOperatoriSatelit.py (acelasi raspuns ca
    la operatorii de satelit), apoi, daca modulul lipseste, din config.osd.language."""
    global _DIN_SATELIT
    if _DIN_SATELIT is None:
        try:
            from Components.HdsOperatoriSatelit import tara_utilizatorului as din_satelit
            _DIN_SATELIT = din_satelit
        except Exception:
            _DIN_SATELIT = False
    if _DIN_SATELIT:
        try:
            tara = (_DIN_SATELIT() or '').upper()
            return 'RS' if tara == 'YU' else tara
        except Exception:
            pass
    try:
        from Components.config import config
        return tara_din_limba(config.osd.language.value)
    except Exception:
        return ''


def tara_alfa3(tara2=None):
    if tara2 is None:
        tara2 = tara_utilizatorului()
    return ALFA3.get((tara2 or '').upper(), '')


# ---------------------------------------------------------------- cititorii de fisiere
def _chei_unice(liste):
    """Fiecare lista primeste o cheie unica, cea folosita in configuratie si in web: numele, iar la nume
    repetate (cables.xml are, de exemplu, doua liste „Numericable-Belgium") numele urmat de „ (2)"."""
    vazute = {}
    for lista in liste:
        n = vazute.get(lista['nume'], 0) + 1
        vazute[lista['nume']] = n
        lista['cheie'] = lista['nume'] if n == 1 else '%s (%d)' % (lista['nume'], n)
    return liste


def _radacina(cale):
    try:
        return ET.parse(cale).getroot()
    except Exception as e:
        print('[HdsListeCabluTerestru] nu pot citi %s: %s' % (cale, e))
        return None


def citeste_cabluri(cale=None):
    """Listele din cables.xml: [{'cheie', 'nume', 'tara', 'flags', 'transpondere': [tp_cablu], 'ajustate'}].
    Aceleasi reguli ca lib/dvb/db.cpp (readCables): frecventa taiata la 6 cifre (kHz), modulatia implicita QAM64,
    FEC-ul implicit Auto, transponderele fara frecventa sau fara rata sarite. In plus fata de db.cpp: tara listei,
    iar codurile pe care structura din nucleu nu le are (modulation 6 si fec_inner 9 din fisierele mai noi) trec pe
    Auto aici, la vedere (se numara in 'ajustate'), nu tacut in prepare_cable."""
    rad = _radacina(cale or CALE_CABLURI)
    if rad is None:
        return []
    liste = []
    for el in rad:
        if el.get('name') is None:
            continue
        lista = {'nume': el.get('name'), 'tara': (el.get('countrycode') or '').upper(),
                 'flags': _int(el.get('flags'), 0), 'transpondere': [], 'ajustate': 0}
        for t in el:
            f, sr = _int(t.get('frequency'), 0), _int(t.get('symbol_rate'), 0)
            if not f or not sr:
                continue
            while f > 999999:
                f //= 10
            tp = tp_cablu(f, sr, _int(t.get('modulation'), CAB_QAM64), _int(t.get('fec_inner'), CAB_FEC_AUTO))
            if tp['modulation'] not in CAB_MODULATII:
                tp['modulation'] = CAB_MOD_AUTO
                lista['ajustate'] += 1
            if tp['fec_inner'] not in CAB_FEC:
                tp['fec_inner'] = CAB_FEC_AUTO
                lista['ajustate'] += 1
            lista['transpondere'].append(tp)
        liste.append(lista)
    return _chei_unice(liste)


# campurile terestre: (camp, valorile din nucleu, valoarea Auto)
_VALIDE_TERESTRU = (('bandwidth', TER_BENZI, TER_BW_AUTO), ('modulation', TER_MODULATII, TER_MOD_AUTO),
                    ('guard_interval', (0, 1, 2, 3, 4), TER_GI_AUTO), ('transmission_mode', (0, 1, 2), TER_TM_AUTO),
                    ('hierarchy', (0, 1, 2, 3, 4), TER_IER_AUTO), ('inversion', INVERSARI, INV_AUTO))


def citeste_terestru(cale=None):
    """Listele din terrestrial.xml, la fel ca citeste_cabluri. Ca lib/dvb/db.cpp (readTerrestrials): frecventa
    centrala in Hz, valorile lipsa pe Auto, code_rate peste 5 taiat la 5. In plus: tara listei, atributele
    `system` (0 DVB-T, 1 DVB-T2) si `plp_id`, pe care db.cpp nu le citeste, iar codurile pe care structura din
    nucleu nu le are (latimile de 5, 1,712 si 10 MHz, 256QAM, intervalele de garda si modurile noi) trec pe Auto."""
    rad = _radacina(cale or CALE_TERESTRU)
    if rad is None:
        return []
    liste = []
    for el in rad:
        if el.get('name') is None:
            continue
        lista = {'nume': el.get('name'), 'tara': (el.get('countrycode') or '').upper(),
                 'flags': _int(el.get('flags'), 0), 'transpondere': [], 'ajustate': 0}
        for t in el:
            f = _int(t.get('centre_frequency'), 0)
            if not f:
                continue
            tp = tp_terestru(f, _int(t.get('bandwidth'), TER_BW_AUTO), _int(t.get('constellation'), TER_MOD_AUTO),
                             _int(t.get('inversion'), INV_AUTO),
                             sistem=_int(t.get('system'), None), plp=_int(t.get('plp_id'), None),
                             crh=min(_int(t.get('code_rate_hp'), TER_FEC_AUTO), TER_FEC_AUTO),
                             crl=min(_int(t.get('code_rate_lp'), TER_FEC_AUTO), TER_FEC_AUTO),
                             gi=_int(t.get('guard_interval'), TER_GI_AUTO),
                             tm=_int(t.get('transmission_mode'), TER_TM_AUTO),
                             ierarhie=_int(t.get('hierarchy_information'), TER_IER_AUTO))
            for camp, valide, auto in _VALIDE_TERESTRU:
                if tp[camp] not in valide:
                    tp[camp] = auto
                    lista['ajustate'] += 1
            if tp['system'] not in (None, SISTEM_DVBT, SISTEM_DVBT2):
                tp['system'] = None
            lista['transpondere'].append(tp)
        liste.append(lista)
    return _chei_unice(liste)


_CITITE = {}


def _din_memorie(cititor, cale):
    """Fisierele XML au sute de KB (cables.xml ~800 KB): se citesc o data si se recitesc numai cand se schimba."""
    try:
        semn = os.path.getmtime(cale)
    except OSError:
        semn = None
    cheie = (cititor.__name__, cale)
    if cheie not in _CITITE or _CITITE[cheie][0] != semn:
        _CITITE[cheie] = (semn, cititor(cale))
    return _CITITE[cheie][1]


def liste_cablu(cale=None, cale_romania=None):
    """Toate listele de cablu: intai operatorii din data/cablu-romania.json (cheile incep cu „ro:”, deci nu se pot
    ciocni cu numele din cables.xml), apoi listele din cables.xml."""
    return citeste_cablu_romania(cale_romania) + _din_memorie(citeste_cabluri, cale or CALE_CABLURI)


def liste_terestre(cale_xml=None, cale_romania=None):
    """Toate listele terestre: intai cele romanesti (din lista Radiocom), apoi cele din terrestrial.xml."""
    return regiuni_romania(cale_romania) + _din_memorie(citeste_terestru, cale_xml or CALE_TERESTRU)


_CAI_DATE = {}


def _cale_date(fisier):
    """Unde se cauta un fisier de date: intai langa celelalte date ale imaginii (/usr/share/enigma2), apoi in
    dosarul data/ al depozitului (PC si emulator). Acelasi tipar ca Components/HdsJurnalVersiuni.py. Calea gasita se
    tine minte: listele se cer la fiecare sageata din scanere, iar resolveFilename si cautarea pe disc costau de
    fiecare data (un fisier lipsa se cauta din nou data viitoare)."""
    if fisier in _CAI_DATE:
        return _CAI_DATE[fisier]
    cai = []
    try:
        from Tools.Directories import resolveFilename, SCOPE_SKIN
        cai.append(resolveFilename(SCOPE_SKIN, fisier))
    except Exception:
        cai.append(os.path.join('/usr/share/enigma2', fisier))
    aici = os.path.dirname(os.path.abspath(__file__))
    cai.append(os.path.normpath(os.path.join(aici, '..', '..', '..', 'data', fisier)))
    for c in cai:
        if c and os.path.exists(c):
            _CAI_DATE[fisier] = c
            return c
    return cai[0]


def _citeste_json_romania(cale):
    try:
        with io.open(cale, 'r', encoding='utf-8') as f:
            date = json.load(f)
        if isinstance(date.get('emitatoare'), list):
            return date
    except Exception as e:
        print('[HdsListeCabluTerestru] nu pot citi lista emitatoarelor romanesti: %s' % e)
    return None


def citeste_romania(cale=None):
    """data/terestru-romania.json, sau None daca lipseste ori e stricat."""
    return _din_memorie(_citeste_json_romania, cale or _cale_date(FISIER_ROMANIA))


# QAM din fisierul de date -> codul din nucleu (eDVBFrontendParametersCable)
_QAM_CABLU = {16: CAB_QAM16, 32: CAB_QAM32, 64: CAB_QAM64, 128: CAB_QAM128, 256: CAB_QAM256}


def _liste_din_json_cablu(cale):
    """data/cablu-romania.json -> liste in forma celor din citeste_cabluri, plus 'fel' ('pornire': frecventele sunt
    numai pornirea, restul vine din tabela de retea). Transponderele cu frecventa sau rata in afara limitelor se sar;
    o modulatie necunoscuta trece pe Auto si se numara in 'ajustate'. Fisier lipsa sau stricat: lista goala."""
    if not cale or not os.path.exists(cale):
        return []
    try:
        with io.open(cale, 'r', encoding='utf-8') as f:
            date = json.load(f)
        operatori = date.get('operatori')
        if not isinstance(operatori, list):
            raise ValueError('lipseste lista "operatori"')
    except Exception as e:
        print('[HdsListeCabluTerestru] nu pot citi lista operatorilor de cablu: %s' % e)
        return []
    liste = []
    for op in operatori:
        if not isinstance(op, dict) or not op.get('cheie') or not op.get('nume'):
            continue
        lista = {'cheie': op['cheie'], 'nume': op['nume'], 'tara': (op.get('tara') or '').upper(), 'flags': 9,
                 'fel': op.get('fel') or 'lista', 'transpondere': [], 'ajustate': 0}
        for t in op.get('transpondere') or []:
            if not isinstance(t, dict):
                continue
            mhz_tp, sr = _int(t.get('mhz'), 0), _int(t.get('sr'), 0)
            if not FRECV_MIN_MHZ <= mhz_tp <= FRECV_MAX_MHZ or not SR_CABLU_MIN < sr <= SR_CABLU_MAX:
                continue
            modulatie = _QAM_CABLU.get(_int(t.get('qam'), 0))
            if modulatie is None:
                modulatie = CAB_MOD_AUTO
                lista['ajustate'] += 1
            lista['transpondere'].append(tp_cablu(mhz_tp * 1000, sr * 1000, modulatie))
        if lista['transpondere']:
            liste.append(lista)
    return liste


def citeste_cablu_romania(cale=None):
    """Operatorii de cablu din data/cablu-romania.json, cititi o data si recititi numai cand fisierul se schimba."""
    cale = cale or CALE_CABLU_ROMANIA or _cale_date(FISIER_CABLU_ROMANIA)
    return _din_memorie(_liste_din_json_cablu, cale)


def este_nota(rand):
    """Un rand de lista de alegere fara cheie si cu text tras spre dreapta e o nota (un sfat), nu un titlu de grupa:
    titlurile incep din margine, randurile de sub ele (si notele) cu trei spatii."""
    return rand[1] is None and rand[0][:1] == ' '


def text_canale(lista_canale):
    if len(lista_canale) == 1:
        return _('canalul %d') % lista_canale[0]
    return _('canalele %s') % ', '.join('%d' % c for c in lista_canale)


def regiuni_romania(cale=None):
    """Listele romanesti, facute din emitatoarele retelei MUX1: intai toata tara, apoi cate una pe judet.
    Fiecare canal se cauta o singura data, pe 8 MHz, ca DVB-T2 (asa emite MUX1)."""
    date = citeste_romania(cale)
    if not date:
        return []
    pe_judete = {}
    for e in date['emitatoare']:
        canal = _int(e.get('canal'), 0)
        if frecventa_canal(canal) is None or not e.get('judet'):
            continue
        pe_judete.setdefault(e['judet'], set()).add(canal)
    if not pe_judete:
        return []
    toate = sorted(set().union(*pe_judete.values()))
    liste = [{'cheie': 'ro:toata', 'nume': _('România, toată rețeaua MUX1 Radiocom'), 'tara': 'ROU', 'flags': 0,
              'ajustate': 0, 'canale': toate, 'transpondere': [tp_canal(c, SISTEM_DVBT2) for c in toate]}]
    for judet in sorted(pe_judete, key=_cheie_alfabetica):
        lista_canale = sorted(pe_judete[judet])
        liste.append({'cheie': 'ro:%s' % judet, 'nume': judet, 'tara': 'ROU', 'flags': 0, 'ajustate': 0,
                      'canale': lista_canale, 'transpondere': [tp_canal(c, SISTEM_DVBT2) for c in lista_canale]})
    return liste


def canale_romania(cale=None):
    """{canal: numarul de emitatoare MUX1 pe el}, pentru semnul din lista de canale."""
    date = citeste_romania(cale) or {'emitatoare': []}
    rez = {}
    for e in date['emitatoare']:
        canal = _int(e.get('canal'), 0)
        if frecventa_canal(canal) is not None:
            rez[canal] = rez.get(canal, 0) + 1
    return rez


def judete_pe_canal(cale=None):
    """{canal: [judetele cu emitatoare MUX1 pe el, in ordine alfabetica]}. Reteaua MUX1 foloseste alt canal in fiecare
    zona (canalul 21 e MUX1 numai in unele judete), deci semnul din lista de canale spune unde."""
    date = citeste_romania(cale) or {'emitatoare': []}
    rez = {}
    for e in date['emitatoare']:
        canal = _int(e.get('canal'), 0)
        judet = e.get('judet')
        if frecventa_canal(canal) is not None and judet:
            rez.setdefault(canal, set()).add(judet)
    return dict((c, sorted(j, key=_cheie_alfabetica)) for c, j in rez.items())


def _cheie_alfabetica(text):
    """Ordinea alfabetica fara diacritice (Calarasi inainte de Cluj)."""
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFD', text) if not unicodedata.combining(ch)).lower()


def text_judete(judete, latime=None):
    """Judetele, toate; cu `latime` (pixeli, fontul randului ferestrei de alegere): cate incap, apoi cate mai sunt
    („Alba, Arad, Hunedoara și încă 4”). Lista intreaga ramane in previzualizarea canalului ales."""
    if latime is None:
        return ', '.join(judete)
    for k in range(len(judete), 0, -1):
        if k == len(judete):
            text = ', '.join(judete)
        else:
            text = _('%s și încă %d') % (', '.join(judete[:k]), len(judete) - k)
        if latime_text(text, *FONT_RAND_ALEGERE) <= latime or k == 1:
            return text
    return ''


# ---------------------------------------------------------------- ordinea: intai tara utilizatorului, apoi pe tari
def ordoneaza_pe_tari(liste, tara3, cu_generale=True):
    """(din_tara, pe_tari, generale):
      din_tara = listele din tara utilizatorului, in ordinea lor;
      pe_tari  = [(cod3, [liste])] pentru celelalte tari, ordonate dupa numele tarii;
      generale = listele fara tara (numai daca cu_generale)."""
    din_tara, tari, generale = [], {}, []
    for lista in liste:
        if not lista.get('tara'):
            if cu_generale:
                generale.append(lista)
        elif tara3 and lista['tara'] == tara3:
            din_tara.append(lista)
        else:
            tari.setdefault(lista['tara'], []).append(lista)
    pe_tari = sorted(tari.items(), key=lambda x: nume_tara(x[0]).lower())
    return din_tara, pe_tari, generale


def alegeri_pe_tari(liste, tara3, text_lista, cu_generale=True):
    """Randurile pentru o lista de alegere (ChoiceBox si web): [(text, cheie)], cu titluri de grupa care au
    cheia None. Blocul „Din tara ta" e mereu primul cand tara e cunoscuta; daca pentru ea nu avem
    nimic, blocul o spune limpede, apoi urmeaza celelalte tari."""
    din_tara, pe_tari, generale = ordoneaza_pe_tari(liste, tara3, cu_generale)
    randuri = []
    if tara3:
        randuri.append((_('Din țara ta (%s):') % nume_tara(tara3), None))
        if din_tara:
            randuri += [('   ' + text_lista(l), l['cheie']) for l in din_tara]
        else:
            randuri.append(('   ' + _('Nu avem nicio listă pentru %s. Alege din celelalte țări.') % nume_tara(tara3),
                            None))
    for cod3, grupa in pe_tari:
        randuri.append(('%s:' % nume_tara(cod3), None))
        randuri += [('   ' + text_lista(l), l['cheie']) for l in grupa]
    if generale:
        randuri.append((_('Liste generale, fără țară:'), None))
        randuri += [('   ' + text_lista(l), l['cheie']) for l in generale]
    return randuri


def gaseste(liste, cheie):
    for lista in liste:
        if lista.get('cheie') == cheie:
            return lista
    return None

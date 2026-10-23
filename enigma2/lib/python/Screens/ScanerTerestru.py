# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ScanerTerestru.py: scanerul terestru al imaginii HDSatelit.

Scris de la zero.
Deschis din meniu: Scanare -> Terestru -> unul din cele cinci feluri (data/menu.xml trimite felul ca argument):
  "canal"    un canal sau un multiplex ales din lista canalelor (VHF III 5-12, UHF 21-69)
  "banda"    maturarea intregii benzi terestre, plus retelele gasite in semnal
  "regiune"  multiplexurile unei regiuni: intai tara utilizatorului (Romania: emitatoarele MUX1 Radiocom, pe
             judete, din data/terestru-romania.json), apoi regiunile din terrestrial.xml, pe tari
  "manual"   frecventa, latimea de banda, sistemul, modulatia, inversarea si PLP-ul scrise de mana
  "automat"  un canal de pornire, apoi retelele citite din semnal (tabela NIT)
Fara fel (ScanerTerestru(session)) se deschide pe ultimul fel folosit, la inceput „manual", ca pana acum.

Sisteme: DVB-T/T2 (Europa, Australia, Africa, Asia); ISDB-T, DTMB si ATSC raman in lista ca sa primeasca un
raspuns limpede: tunerul acestui receptor (Viper 4K V20) e DVB-C/T/T2 si nu are demodulator pentru ele.

DVB-T2: nucleul imaginii acordeaza deocamdata numai DVB-T (lib/dvb/frontendparms.h nu are `system` si `plp_id`,
frontend.cpp trimite mereu SYS_DVBT). Televiziunea terestra din Romania e DVB-T2, deci cu un nucleu fara DVB-T2 orice
fel de scanare iese acolo cu 0 canale. Ecranul o spune INAINTE de pornire si cere confirmarea; cand structura din
nucleu va avea campurile, intrebarea dispare singura (HdsListeCabluTerestru.nucleul_stie_dvbt2) si sistemul si
PLP-ul pleaca spre nucleu fara alta schimbare aici.

Ce se cauta hotaraste functia de modul pregateste(fel, valori), fara ecran, folosita si de interfata web;
cerere_scanare(rezultat) face lista pentru ServiceScan; alegeri(camp) da randurile listelor de alegere.
Ecranul comun al scanerelor (EcranScaner) sta in Screens/ScanerCablu.py.
"""
from __future__ import absolute_import, unicode_literals

import Components.HdsListeCabluTerestru as liste
from Screens.ScanerCablu import EcranScaner, MINUTE_CU_INTREBARE

CALE_CONFIG = '/etc/enigma2/hdsscaner_terestru.conf'
FELURI = ('canal', 'banda', 'regiune', 'manual', 'automat')

SISTEME = [
    (0, _('DVB-T (Europa clasic)')),
    (1, _('DVB-T2 (Europa nou, Asia)')),
    (3, _('ISDB-T (Japonia, Brazilia, America de Sud)')),
    (4, _('DTMB (China, Hong Kong, Cuba)')),
    (8, _('ATSC 1.0 (SUA, Canada, Mexic, Coreea)')),
    (9, _('ATSC 3.0 (SUA, nouă generație)')),
]

# Numai ce are nucleul (lib/dvb/frontendparms.h, eDVBFrontendParametersTerrestrial: Bandwidth 8/7/6 MHz si Auto,
# Modulation QPSK/QAM16/QAM64/Auto). Latimile de 1,712, 5 si 10 MHz si 256QAM le-ar transforma prepare_terrestrial
# (lib/dvb/frontend.cpp) tacut in Auto, iar 256QAM exista doar la DVB-T2, pe care nucleul nu il acordeaza; se pun
# odata cu DVB-T2 in C++.
BENZI = [
    (0, _('8 MHz (Europa standard)')),
    (1, _('7 MHz (Australia, Caraibe)')),
    (2, _('6 MHz (America, Japonia, Caraibe)')),
    (3, _('Auto')),
]

MODULATII = [
    (0, 'QPSK'), (1, '16QAM'), (2, '64QAM'),
    (3, _('Auto')),
]

FEC_TERESTRU = [
    (0, '1/2'), (1, '2/3'), (2, '3/4'),
    (3, '5/6'), (4, '7/8'), (5, _('Auto')),
]

INVERSARE = [(2, _('Auto')), (0, _('Normal')), (1, _('Inversat'))]


def _int(v, implicit):
    try:
        return int(v)
    except (ValueError, TypeError):
        return implicit


def nume_feluri():
    return [('canal', _('După canal sau multiplex')), ('banda', _('Toată banda')),
            ('regiune', _('După regiune sau operator')), ('manual', _('Cu date introduse manual')),
            ('automat', _('Automat, din rețeaua semnalului'))]


def titluri_scurte():
    """Felul din titlul ferestrei, scurt: titlul incape si cu fonturile marite la 130 % (HdsBold 52 in 1000 px)."""
    return {'canal': _('După canal'), 'banda': _('Toată banda'), 'regiune': _('După regiune'), 'manual': _('Manual'),
            'automat': _('Automat')}


def info_sistem(cod):
    return {
        0: _('DVB-T: Europa, Africa, Australia, Asia de Sud-Est.\nBanda tipică: 8 MHz. Canale TV analog reconvertite.'),
        1: _('DVB-T2: standardul nou din Europa și Asia.\nPoate duce mai multe multiplexuri pe aceeași frecvență.\nBanda: 8 MHz (Europa), 7/6 MHz (alte regiuni).'),
        3: _('ISDB-T: Standard japonez adoptat în Brazilia, Argentina, Bolivia,\nChile, Colombia, Peru, Venezuela, Filipine, Botswana, Mozambic.\nBanda: 6 MHz. Suportă servicii mobile (One-Seg).'),
        4: _('DTMB (DMB-TH): Standard chinez. Folosit în China, Hong Kong,\nCuba, Macao, Pakistan. Banda: 8 MHz.'),
        8: _('ATSC 1.0: Standard american. SUA, Canada, Mexic, Coreea de Sud.\nBanda: 6 MHz. Modulație 8VSB (terestru) sau 64QAM (cablu).'),
        9: _('ATSC 3.0: standardul nou din SUA, folosit din 2020.\nUltra HD, HDR, sunet cu efect de spațiu.'),
    }.get(_int(cod, -1), _('Sistem necunoscut.'))


def config_implicit():
    return {'fel': 'manual', 'canal': '21', 'cu_vhf': 'da', 'regiune': '', 'frecventa': '474', 'sistem': '0',
            'banda': '0', 'mod': '3', 'inversare': '2', 'plp': ''}


def verifica_terestru(c, hz):
    """(eroare, nota) inainte de cautarea manuala. prepare_terrestrial nu refuza nimic, orice valoare necunoscuta
    devine Auto, deci fara verificarea asta utilizatorul vede doar 0 canale, fara motiv."""
    if not liste.FRECV_MIN_MHZ * 1000000 <= hz <= liste.FRECV_MAX_MHZ * 1000000:
        return _('Frecvența %s MHz e în afara benzii terestre (%d-%d MHz). Scrie-o în MHz, de exemplu 474.') % (
            liste.mhz(hz), liste.FRECV_MIN_MHZ, liste.FRECV_MAX_MHZ), ''
    banda = _int(c.get('banda'), 3)
    if banda not in [x[0] for x in BENZI]:
        return _('Lățimea de bandă aleasă nu e primită: imaginea știe numai 8, 7, 6 MHz și Auto. Alege alta.'), ''
    if _int(c.get('mod'), 3) not in [x[0] for x in MODULATII]:
        return _('Modulația aleasă (256QAM) e numai la DVB-T2, pe care imaginea nu îl recepționează încă. '
                 'Alege QPSK, 16QAM, 64QAM sau Auto.'), ''
    if banda == 3:
        return None, _('Lățimea de bandă Auto nu merge pe toate tunerele; dacă iese 0 canale, alege 8 MHz.')
    return None, ''


# ---------------------------------------------------------------- listele de alegere
def campuri(fel):
    """Randurile felului: [(cheie, eticheta, tip, optiuni)], ca in Screens/ScanerCablu.py (campuri)."""
    if fel == 'canal':
        return [('canal', _('Canalul'), 'alegere', None)]
    if fel == 'automat':
        return [('canal', _('Canalul de pornire'), 'alegere', None)]
    if fel == 'banda':
        return [('cu_vhf', _('Și banda VHF (canalele 5-12)'), 'lista',
                 [('da', _('Da')), ('nu', _('Nu, numai UHF 21-69'))])]
    if fel == 'regiune':
        return [('regiune', _('Regiunea sau operatorul'), 'alegere', None)]
    return [('sistem', _('Sistem'), 'lista', SISTEME),
            ('frecventa', _('Frecvența (MHz, ex. 474)'), 'numeric', None),
            ('banda', _('Lățime bandă'), 'lista', BENZI),
            ('mod', _('Modulație'), 'lista', MODULATII),
            ('inversare', _('Inversare spectru'), 'lista', INVERSARE),
            ('plp', _('PLP ID (numai DVB-T2)'), 'numeric', None)]

def _text_regiune(lista):
    """Randul regiunii in lista de alegere: numele si canalele sau numarul de frecvente, intregi (un rand care nu
    incape deruleaza, lib/gui/elabel.h)."""
    if 'canale' in lista:
        canale = lista['canale']
        if len(canale) > 6:
            # toata tara are 18 canale: primele patru, apoi ultimul
            sufix = ' (%s)' % (_('canalele %s') % (', '.join('%d' % c for c in canale[:4]) + ' … %d' % canale[-1]))
        else:
            sufix = ' (%s)' % liste.text_canale(canale)
        return lista['nume'] + sufix
    n = len(lista['transpondere'])
    return lista['nume'] + liste.ngettext(', %d frecvență', ', %d frecvențe', n) % n


def alegeri(camp, cale_xml=None, cale_romania=None):
    """Randurile listei de alegere a unui camp: [(text, cheie)]; titlurile de grupa au cheia None."""
    if camp == 'regiune':
        return liste.alegeri_pe_tari(liste.liste_terestre(cale_xml, cale_romania), liste.tara_alfa3(),
                                     _text_regiune)
    if camp == 'canal':
        # MUX1 are alt canal in fiecare zona: semnul spune judetele in care canalul e MUX1, nu „in Romania”
        mux1 = liste.judete_pe_canal(cale_romania) if liste.tara_utilizatorului() == 'RO' else {}
        randuri = [(_('VHF III, canale de 7 MHz:'), None)]
        for canal in liste.canale():
            if canal == liste.CANALE_UHF[0]:
                randuri.append((_('UHF, canale de 8 MHz:'), None))
            text = _('Canalul %d, %s MHz') % (canal, liste.mhz(liste.frecventa_canal(canal)))
            if canal in mux1:
                # cate judete incap pe rand; toate sunt in previzualizarea canalului ales
                sablon = ' ' + _('(MUX1 în %s)')
                loc = liste.LATIME_RAND_ALEGERE - liste.latime_text(liste.INDENT + text + sablon % '',
                                                                   *liste.FONT_RAND_ALEGERE)
                text += sablon % liste.text_judete(mux1[canal], loc)
            randuri.append((liste.INDENT + text, str(canal)))
        return randuri
    return []


# ---------------------------------------------------------------- ce se cauta (fara ecran: ecranul si web-ul)
def pregateste(fel, valori, nimmanager=None, clasa=None, cale_xml=None, cale_romania=None):
    """Ce se cauta pentru felul ales si valorile date (aceleasi chei ca in configuratia ecranului).
    Intoarce {'fel', 'transpondere': [dict in unitatile nucleului], 'slot', 'flags', 'text', 'intrebare'} sau
    {'eroare': text}. 'intrebare' nevida = se cere confirmarea utilizatorului inainte de pornire: DVB-T2 pe care
    nucleul nu il acordeaza inca, sau o scanare lunga."""
    valori = valori or {}
    if fel not in FELURI:
        return {'eroare': _('Felul de scanare „%s" nu există. Alege unul din listă.') % fel}
    if fel == 'manual':
        sis = _int(valori.get('sistem'), 0)
        if sis in (3, 4, 8, 9):
            return {'eroare': _('%s: tunerul terestru al acestui receptor e DVB-T/T2, nu are demodulator pentru '
                                'acest standard.') % {3: 'ISDB-T', 4: 'DTMB', 8: 'ATSC 1.0', 9: 'ATSC 3.0'}[sis]}
    if nimmanager is None:
        from Components.NimManager import nimmanager
    slot, eroare = liste.tuner_pentru(nimmanager, 'DVB-T')
    if eroare:
        return {'eroare': eroare}
    from enigma import eComponentScan
    if clasa is None:
        from enigma import eDVBFrontendParametersTerrestrial as clasa
    retea = eComponentScan.scanNetworkSearch
    flags, note = 0, []

    if fel in ('canal', 'automat'):
        canal = _int(valori.get('canal'), 0)
        if liste.frecventa_canal(canal) is None:
            return {'eroare': _('Alege canalul din listă (OK).')}
        tps = [liste.tp_canal(canal)]
        if fel == 'automat':
            flags = retea
            text = _('Pornire de pe canalul %d (%s MHz), apoi toate multiplexurile anunțate în semnal.') % (
                canal, liste.mhz(tps[0]['frequency']))
        else:
            text = _('Canalul %d, %s MHz.') % (canal, liste.mhz(tps[0]['frequency']))
        # MUX1 are alt canal in fiecare zona: toate judetele in care canalul ales e MUX1 (randul listei are loc
        # numai pentru cateva)
        judete = liste.judete_pe_canal(cale_romania).get(canal) if liste.tara_utilizatorului() == 'RO' else None
        if judete:
            note.append(_('Pe acest canal emite MUX1 în: %s.') % liste.text_judete(judete))
    elif fel == 'banda':
        cu_vhf = valori.get('cu_vhf', 'da') != 'nu'
        tps = liste.maturare_terestru(cu_vhf)
        flags = retea
        text = _('Toată banda terestră: %d canale (%s), cel mult %d minute, plus rețelele găsite în semnal.') % (
            len(tps), _('VHF 5-12 și UHF 21-69') if cu_vhf else _('UHF 21-69'), liste.minute_maxime(len(tps)))
    elif fel == 'regiune':
        lista = liste.gaseste(liste.liste_terestre(cale_xml, cale_romania), valori.get('regiune'))
        if lista is None:
            return {'eroare': _('Alege regiunea din listă (OK).')}
        tps = list(lista['transpondere'])
        if not tps:
            return {'eroare': _('Lista %s nu are nicio frecvență.') % lista['nume']}
        flags = retea if lista['flags'] & 1 else 0
        text = liste.ngettext('%s (%s): %d frecvență.', '%s (%s): %d frecvențe.', len(tps)) % (
            lista['nume'], liste.nume_tara(lista['tara']), len(tps))
        if lista['ajustate']:
            note.append(_('%d valori din listă pe care imaginea nu le știe au trecut pe Auto.') % lista['ajustate'])
    else:
        hz = liste.hz_din_mhz(valori.get('frecventa'))
        if not hz:
            return {'eroare': _('Introdu frecvența în MHz, de exemplu 474.')}
        eroare, nota = verifica_terestru(valori, hz)
        if eroare:
            return {'eroare': eroare}
        if nota:
            note.append(nota)
        sis = _int(valori.get('sistem'), 0)
        plp = str(valori.get('plp', '')).strip()
        if plp and not plp.isdigit():
            return {'eroare': _('PLP ID „%s" nu e un număr.') % plp}
        tps = [liste.tp_terestru(hz, _int(valori.get('banda'), liste.TER_BW_AUTO),
                                 _int(valori.get('mod'), liste.TER_MOD_AUTO), _int(valori.get('inversare'), liste.INV_AUTO),
                                 sistem=liste.SISTEM_DVBT2 if sis == 1 else liste.SISTEM_DVBT,
                                 plp=int(plp) if (sis == 1 and plp) else None)]
        text = _('Un singur multiplex: %s MHz, %s.') % (liste.mhz(hz), 'DVB-T2' if sis == 1 else 'DVB-T')

    for tp in tps:
        motiv = liste.motiv_refuz_terestru(tp)
        if motiv:
            return {'eroare': _('Nu se poate căuta: %s.') % motiv}

    intrebari = []
    if not liste.nucleul_stie_dvbt2(clasa):
        romania = liste.tara_utilizatorului() == 'RO' and fel != 'manual'
        if romania:
            intrebari.append(_('Televiziunea terestră din România (rețeaua MUX1) e DVB-T2, iar imaginea acordează '
                               'deocamdată numai DVB-T. Căutarea va găsi 0 canale până la o actualizare viitoare '
                               'a imaginii.'))
        elif liste.cere_dvbt2(tps):
            intrebari.append(_('Ai cerut multiplexuri DVB-T2, iar imaginea acordează deocamdată numai DVB-T. Ele '
                               'vor ieși cu 0 canale până la o actualizare viitoare a imaginii.'))
        else:
            note.append(_('Imaginea acordează deocamdată numai DVB-T: multiplexurile DVB-T2 nu vor da canale până '
                          'la o actualizare viitoare.'))
        if flags & retea:
            note.append(_('Rețelele DVB-T2 își anunță frecvențele într-un fel pe care imaginea nu îl citește încă.'))
    minute = liste.minute_maxime(len(tps))
    if minute > MINUTE_CU_INTREBARE:
        intrebari.append(_('Căutarea are %d încercări și poate dura până la %d minute.') % (len(tps), minute))
    intrebare = ''
    if intrebari:
        intrebare = ' '.join(intrebari) + ' ' + _('Cauți totuși?')
    if note:
        text += ' ' + ' '.join(note)
    return {'fel': fel, 'transpondere': tps, 'slot': slot, 'flags': flags, 'text': text, 'intrebare': intrebare}


def cerere_scanare(rez, clasa=None):
    """Rezultatul lui pregateste -> lista primita de Screens.ServiceScan.ServiceScan. Sistemul si PLP-ul DVB-T2
    se pun numai daca structura din nucleu le are (vezi antetul)."""
    if clasa is None:
        from enigma import eDVBFrontendParametersTerrestrial as clasa
    parametri = [liste.in_parametri(clasa, tp)[0] for tp in rez['transpondere']]
    # hds_fel: felul scanarii in /api/scanare-ultima (Components/HdsScanareUltima.py)
    return [{"transponders": parametri, "feid": rez['slot'], "flags": rez['flags'],
             "hds_fel": "terestru/%s" % rez.get('fel', '')}]


class ScanerTerestru(EcranScaner):
    """Scanerul terestru: cele cinci feluri din FELURI, pe primul tuner DVB-T pornit."""

    CALE_CONFIG = CALE_CONFIG
    ANTET_CONFIG = 'Scaner Terestru HDSatelit'
    FEL_IMPLICIT = 'manual'
    CAMPURI_MHZ = ('frecventa',)

    def __init__(self, session, fel=None, config_initial=None):
        EcranScaner.__init__(self, session, fel, config_initial)

    def feluri(self):
        return nume_feluri()

    def titlu_fel(self, fel):
        return '%s: %s' % (_('Scanare terestră'), titluri_scurte().get(fel, ''))

    def config_implicit(self):
        return config_implicit()

    def potriveste_config(self, c):
        """Configuratia scrisa de versiunile vechi ale ecranului: frecventa in Hz (474000000) si PLP 0 pentru
        „implicit”. Acum frecventa e in MHz si PLP gol inseamna implicit."""
        f = _int(c.get('frecventa'), 0)
        if f > 100000:
            c['frecventa'] = liste.mhz(f)
        if str(c.get('plp', '')).strip() == '0':
            c['plp'] = ''
        return c

    def campuri(self, fel):
        return campuri(fel)

    def _eticheta_valoare(self, cheie, tip, optiuni):
        # PLP gol inseamna PLP-ul implicit al multiplexului; in lista se scrie asa, nu „-”
        if cheie == 'plp' and not str(self._config.get('plp', '')).strip():
            return _('Implicit')
        return EcranScaner._eticheta_valoare(self, cheie, tip, optiuni)

    def alegeri(self, camp):
        return alegeri(camp)

    def pregateste(self, fel, valori):
        return pregateste(fel, valori)

    def cerere(self, rez):
        return cerere_scanare(rez)

    def preview(self, rez):
        text = rez.get('eroare') or rez.get('text', '')
        if self._config.get('fel') == 'manual':
            return info_sistem(self._config.get('sistem')) + '\n' + text
        return text

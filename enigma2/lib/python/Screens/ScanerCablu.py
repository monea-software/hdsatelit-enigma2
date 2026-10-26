# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ScanerCablu.py: scanerul de cablu (DVB-C) al imaginii HDSatelit.

Scris de la zero.
Deschis din meniu: Scanare -> Cablu -> unul din cele cinci feluri (data/menu.xml trimite felul ca argument):
  "frecventa"  o frecventa aleasa din lista; rata de simbol si modulatia le incearca receptorul singur
  "banda"      maturarea intregii benzi de cablu (122-858 MHz, pas de 8 MHz), plus retelele gasite in semnal
  "operator"   un operator: intai cei din tara utilizatorului (in Romania: Digi, Vodafone si Nextgen din
               data/cablu-romania.json, cu frecventa de pornire, apoi listele din cables.xml), apoi pe tari
  "manual"     frecventa, rata de simbol si modulatia scrise de mana, un singur transponder
  "automat"    o frecventa de pornire, apoi retelele citite din semnal (tabela NIT)
La "frecventa" si "manual" tabela retelei (NIT) se citeste numai pentru informatie (steagul hdsNitInformativ, cel
mult 12 s de asteptare pe transponder cand operatorul nu o trimite): numele retelei si numerele canalelor, fara alte
frecvente in scanare.

Tot ce hotaraste ce se cauta sta in functia de modul pregateste(fel, valori), fara ecran, folosita si de
interfata web; cerere_scanare(rezultat) face din rezultat lista pe care o primeste ServiceScan; alegeri(camp)
da randurile listelor de alegere. Datele si regulile nucleului stau in Components/HdsListeCabluTerestru.py.

Tot aici e EcranScaner, ecranul comun al scanerelor de cablu si terestru (Screens/ScanerTerestru.py il foloseste),
si AlegereDinLista, fereastra de alegere a tuturor scanerelor (si Screens/ScanerSatelit.py o foloseste).

Fereastra: in skinul HDSatelit, ecranele ScanerCablu, ScanerTerestru si HdsAlegereScaner (cadrul HdsCadru1240, la
72,40, 1240x1000, fara bara de titlu a stilului de fereastra; panoul se opreste la x 1312, deci nu intra sub
fereastra PiP de la 1344). Pe alte skinuri, skin_rezerva() face acelasi desen, scris pe 1920 si inmultit cu latimea
ecranului / 1920, numai cu fontul Regular si culori scrise ca numere. Randurile listei sunt (eticheta, cheie,
valoare, culoarea valorii), desenate pe doua coloane de sablonul TemplatedMultiContent: eticheta la stanga, valoarea
aliniata la dreapta; fiecare text e taiat la marginea coloanei lui (elistboxcontent.cpp, painter.clip), deci o
valoare lunga nu trece peste eticheta.
"""
from __future__ import absolute_import, unicode_literals
import os

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Screens.ChoiceBox import ChoiceBox
import Components.HdsListeCabluTerestru as liste
from Components.HdsCursorLista import pune_randurile

CALE_CONFIG = '/etc/enigma2/hdsscaner_cablu.conf'
FELURI = ('frecventa', 'banda', 'operator', 'manual', 'automat')
# minutele peste care o scanare lunga se confirma inainte de pornire
MINUTE_CU_INTREBARE = 10
# Rândul din lista de alegere care deschide alt fel de scanare, nu o valoare: cheia „fel:<felul>”. Orange nu își
# publică frecvențele, deci rândul lui deschide „Toată banda”.
PREFIX_FEL = 'fel:'


def _int(v, implicit):
    try:
        return int(v)
    except (ValueError, TypeError):
        return implicit


def nume_feluri():
    return [('frecventa', _('După frecvență')), ('banda', _('Toată banda')), ('operator', _('După operator')),
            ('manual', _('Cu date introduse manual')), ('automat', _('Automat, din rețeaua semnalului'))]


def titluri_scurte():
    """Felul din titlul ferestrei: scurt, ca titlul să încapă și cu fonturile mărite la 130 % (HdsBold 52 în 1000 px);
    numele întreg rămâne în rândul felului și în meniu."""
    return {'frecventa': _('După frecvență'), 'banda': _('Toată banda'), 'operator': _('După operator'),
            'manual': _('Manual'), 'automat': _('Automat')}


def modulatii():
    return [(0, _('Auto')), (1, 'QAM16'), (2, 'QAM32'), (3, 'QAM64'), (4, 'QAM128'), (5, 'QAM256')]


def optiuni_banda_sr():
    return [('ambele', _('6900 și 6875 kSymb/s')), ('6900', '6900 kSymb/s'), ('6875', '6875 kSymb/s')]


def optiuni_banda_mod():
    return [('ambele', _('QAM256 și QAM64')), ('256', 'QAM256'), ('64', 'QAM64'),
            ('auto', _('Auto (numai dacă tunerul o află singur)'))]


BANDA_SR = {'ambele': (6900, 6875), '6900': (6900,), '6875': (6875,)}
BANDA_MOD = {'ambele': (liste.CAB_QAM256, liste.CAB_QAM64), '256': (liste.CAB_QAM256,), '64': (liste.CAB_QAM64,),
             'auto': (liste.CAB_MOD_AUTO,)}


# ---------------------------------------------------------------- configuratia (ultimii parametri folositi)
def citeste_config(cale, implicit):
    c = dict(implicit)
    if not os.path.exists(cale):
        return c
    try:
        with open(cale, 'r', encoding='utf-8', errors='replace') as f:
            for linie in f:
                linie = linie.strip()
                if not linie or linie.startswith('#') or '=' not in linie:
                    continue
                k, v = linie.split('=', 1)
                k = k.strip().lower()
                if k in c:
                    c[k] = v.strip()
    except (IOError, OSError):
        pass
    return c


def scrie_config(cale, c, antet):
    linii = ['# %s' % antet] + ['%s = %s' % (k, v) for k, v in c.items()]
    try:
        with open(cale, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linii) + '\n')
    except (IOError, OSError):
        pass


def _din_tara(cale_xml=None):
    tara3 = liste.tara_alfa3()
    return [l for l in liste.liste_cablu(cale_xml) if tara3 and l['tara'] == tara3]


def config_implicit(cale_xml=None):
    """Frecventa de pornire implicita: primul transponder al primului operator din tara utilizatorului (in
    Romania: Digi, 306 MHz, 6900 kSymb/s, QAM64). Fara operator cunoscut, campul ramane gol si ecranul cere
    frecventa."""
    c = {'fel': 'manual', 'frecventa_lista': '', 'operator': '', 'frecventa': '', 'sr': '6900',
         'mod': str(liste.CAB_MOD_AUTO), 'banda_sr': 'ambele', 'banda_mod': 'ambele', 'operator_ales': ''}
    for lista in _din_tara(cale_xml):
        if lista['transpondere']:
            tp = lista['transpondere'][0]
            c.update(frecventa=liste.mhz(tp['frequency'] * 1000), sr=str(tp['symbol_rate'] // 1000),
                     mod=str(tp['modulation']), frecventa_lista=str(tp['frequency']), operator=lista['cheie'])
            break
    return c


# ---------------------------------------------------------------- ce se cauta (fara ecran: ecranul si web-ul)
def _frecvente_pornire(lista):
    """'306' sau '306, 314': frecventele de pornire ale unui operator, fiecare o data, in ordinea din fisier."""
    vazute = []
    for tp in lista['transpondere']:
        text = liste.mhz(tp['frequency'] * 1000)
        if text not in vazute:
            vazute.append(text)
    return ', '.join(vazute)


def nume_operator(lista):
    """Numele de arătat: pentru listele românești din cables.xml, numele în română (acolo sunt în engleză)."""
    if lista.get('tara') == 'ROU' and lista.get('nume') == 'DIGI Bucharest':
        return _('Digi București, lista veche')
    return lista['nume']


def _text_operator(lista):
    """Rândul operatorului în lista de alegere, întreg (un rând care nu încape derulează, lib/gui/elabel.h)."""
    if lista.get('fel') == 'pornire':
        sufix = _(': toată rețeaua, pornind de la %s MHz') % _frecvente_pornire(lista)
    else:
        n = len(lista['transpondere'])
        sufix = liste.ngettext(', %d frecvență', ', %d frecvențe', n) % n
    return nume_operator(lista) + sufix


def _si(parti):
    """['QAM64', 'QAM256'] -> 'QAM64 și QAM256'; trei sau mai multe, cu virgula intre primele."""
    if len(parti) < 2:
        return ''.join(parti)
    return _('%s și %s') % (', '.join(parti[:-1]), parti[-1])


def descriere_pornire(transpondere):
    """'306 MHz (6900 kSymb/s, QAM64 și QAM256)': transponderele de pornire, grupate pe frecventa si rata."""
    grupe = []
    for tp in transpondere:
        for g in grupe:
            if (g[0], g[1]) == (tp['frequency'], tp['symbol_rate']):
                if tp['modulation'] not in g[2]:
                    g[2].append(tp['modulation'])
                break
        else:
            grupe.append((tp['frequency'], tp['symbol_rate'], [tp['modulation']]))
    nume_mod = dict(modulatii())
    return ', '.join('%s MHz (%d kSymb/s, %s)' % (liste.mhz(f * 1000), sr // 1000,
                                                    _si([nume_mod.get(m, str(m)) for m in mods]))
                     for f, sr, mods in grupe)


def nota_operator(cheie):
    """Nota care se adauga la previzualizarea unui operator anume ('' daca nu are)."""
    if cheie == 'ro:nextgen':
        return _('Rețeaua Nextgen trece pe Orange. Dacă nu găsește nimic, alege „Toată banda”.')
    return ''


def note_tara(tara3):
    """Randurile puse sub operatorii unei tari in lista de alegere: [(text, cheie)]. Cheia None = nota (un sfat, nu
    se poate alege); cheia PREFIX_FEL + fel = randul deschide acel fel de scanare (Orange nu isi publica frecventele,
    deci OK pe el deschide „Toata banda”)."""
    if tara3 == 'ROU':
        return [(_('Orange: căutare pe toată banda (frecvențele nu sunt publice)'), PREFIX_FEL + 'banda'),
                (_('INES, Moldtelecom, StarNet: televiziune prin internet, nu prin cablu.'), None)]
    return []


def text_nota_web(cheie):
    """In pagina web /scanare randul care deschide alt fel nu se poate alege din lista: devine nota, cu drumul."""
    if cheie == PREFIX_FEL + 'banda':
        return _('Orange: frecvențele nu sunt publice; caută cu Cablu, „Toată banda”.')
    return ''


def _cu_note(randuri, toate):
    """Pune notele fiecarei tari (note_tara) dupa ultimul ei operator din lista de alegere. Randurile de nota au
    cheia None si textul tras spre dreapta (liste.este_nota), deci nu se pot alege."""
    tara_cheii = dict((l['cheie'], l['tara']) for l in toate)
    ultimul = {}
    for i, (_text, cheie) in enumerate(randuri):
        if cheie is not None and tara_cheii.get(cheie):
            ultimul[tara_cheii[cheie]] = i
    for tara3, i in sorted(ultimul.items(), key=lambda x: -x[1]):
        randuri[i + 1:i + 1] = [('   ' + text, cheie) for text, cheie in note_tara(tara3)]
    return randuri


def campuri(fel):
    """Randurile felului: [(cheie, eticheta, tip, optiuni)]. tip: 'lista' (optiuni = [(cod, text)]), 'alegere'
    (randurile vin din alegeri(cheie)) sau 'numeric'. Aceleasi randuri in ecran si in formularul din web."""
    if fel == 'frecventa':
        return [('frecventa_lista', _('Frecvența'), 'alegere', None)]
    if fel == 'banda':
        return [('banda_sr', _('Rata de simbol'), 'lista', optiuni_banda_sr()),
                ('banda_mod', _('Modulația'), 'lista', optiuni_banda_mod())]
    if fel == 'operator':
        return [('operator', _('Operatorul'), 'alegere', None)]
    eticheta = _('Frecvența de pornire (MHz)') if fel == 'automat' else _('Frecvența (MHz)')
    return [('frecventa', eticheta, 'numeric', None),
            ('sr', _('Rata de simbol (kSymb/s)'), 'numeric', None),
            ('mod', _('Modulația'), 'lista', modulatii())]


def alegeri(camp, cale_xml=None):
    """Randurile listei de alegere a unui camp: [(text, cheie)]; titlurile de grupa si notele au cheia None
    (notele se deosebesc prin textul tras spre dreapta, liste.este_nota)."""
    if camp == 'operator':
        # listele fara tara din cables.xml sunt maturari, nu operatori; maturarea are felul ei („Toata banda")
        toate = liste.liste_cablu(cale_xml)
        return _cu_note(liste.alegeri_pe_tari(toate, liste.tara_alfa3(), _text_operator, cu_generale=False), toate)
    if camp == 'frecventa_lista':
        stiute = {}
        for lista in _din_tara(cale_xml):
            for tp in lista['transpondere']:
                nume = stiute.setdefault(tp['frequency'], [])
                # o lista veche din cables.xml a aceluiasi operator („DIGI Bucharest” langa „Digi”) nu se mai scrie
                primul = lista['nume'].split()[0].lower() if lista['nume'].split() else ''
                if lista['nume'] not in nume and not any(n.split()[0].lower() == primul for n in nume if n.split()):
                    nume.append(lista['nume'])
        randuri = []
        for khz in sorted(set(f * 1000 for f in liste.FRECVENTE_CABLU_MHZ) | set(stiute)):
            text = '%s MHz' % liste.mhz(khz * 1000)
            if khz in stiute:
                text += ' (%s)' % ', '.join(stiute[khz])
            randuri.append((text, str(khz)))
        return randuri
    return []


def _fara_dubluri(transpondere):
    """Acelasi transponder (frecventa, rata, modulatie) venit de la mai multi operatori se cauta o singura data."""
    vazute, rez = set(), []
    for tp in transpondere:
        semn = (tp['frequency'], tp['symbol_rate'], tp['modulation'])
        if semn not in vazute:
            vazute.add(semn)
            rez.append(tp)
    return rez


def pregateste(fel, valori, nimmanager=None, cale_xml=None):
    """Ce se cauta pentru felul ales si valorile date (aceleasi chei ca in configuratia ecranului).
    Intoarce {'fel', 'transpondere': [dict in unitatile nucleului], 'slot', 'flags', 'text', 'intrebare'} sau
    {'eroare': text}. 'intrebare' nevida = se cere confirmarea utilizatorului inainte de pornire (scanare lunga)."""
    valori = valori or {}
    if fel not in FELURI:
        return {'eroare': _('Felul de scanare „%s" nu există. Alege unul din listă.') % fel}
    if nimmanager is None:
        from Components.NimManager import nimmanager
    slot, eroare = liste.tuner_pentru(nimmanager, 'DVB-C')
    if eroare:
        return {'eroare': eroare}
    from enigma import eComponentScan
    retea = eComponentScan.scanNetworkSearch
    # cablu fara cautare in retea: NIT-ul (numele retelei, numerele canalelor) citit numai pentru informatie, fara alte
    # frecvente in scanare (lib/dvb/scan.h); un nucleu fara steag da 0, ca inainte
    informativ = getattr(eComponentScan, 'hdsNitInformativ', 0)
    flags, note = 0, []

    if fel == 'frecventa':
        khz = _int(valori.get('frecventa_lista'), 0)
        if not khz:
            return {'eroare': _('Alege frecvența din listă (OK).')}
        flags = informativ
        # la 306 MHz, de exemplu, Digi (QAM64 si QAM256), Vodafone (QAM256) si lista DIGI Bucharest (QAM64) dau
        # impreuna doua transpondere diferite, nu patru
        stiute = _fara_dubluri([tp for l in _din_tara(cale_xml) for tp in l['transpondere'] if tp['frequency'] == khz])
        if stiute:
            tps = stiute
            text = _('Căutare pe %s MHz, cu rata și modulația cunoscute ale operatorului.') % liste.mhz(khz * 1000)
        else:
            tps = [liste.tp_cablu(khz, sr * 1000, m) for sr in liste.SR_CABLU_OBISNUITE
                   for m in BANDA_MOD['ambele']]
            text = _('Căutare pe %s MHz: %d încercări, cu 6900 și 6875 kSymb/s, QAM256 și QAM64.') % (
                liste.mhz(khz * 1000), len(tps))
    elif fel == 'banda':
        tps = liste.maturare_cablu(BANDA_SR.get(valori.get('banda_sr'), BANDA_SR['ambele']),
                                   BANDA_MOD.get(valori.get('banda_mod'), BANDA_MOD['ambele']))
        flags = retea
        text = _('Toată banda de cablu, %d-%d MHz din 8 în 8 MHz: %d încercări, cel mult %d minute, plus '
                 'rețelele găsite în semnal.') % (liste.FRECVENTE_CABLU_MHZ[0], liste.FRECVENTE_CABLU_MHZ[-1],
                                                  len(tps), liste.minute_maxime(len(tps)))
        if valori.get('banda_mod') == 'auto':
            note.append(_('Cu modulația Auto, dacă ies 0 canale, alege QAM256 și QAM64.'))
    elif fel == 'operator':
        lista = liste.gaseste(liste.liste_cablu(cale_xml), valori.get('operator'))
        if lista is None:
            return {'eroare': _('Alege operatorul din listă (OK).')}
        tps = list(lista['transpondere'])
        if not tps:
            return {'eroare': _('Lista operatorului %s nu are nicio frecvență.') % lista['nume']}
        # frecventele din fisier sunt pornirea; lista la zi a operatorului vine din tabela lui de retea (NIT)
        flags = retea
        if lista.get('fel') == 'pornire':
            text = _('Operatorul %s (%s): pornire pe %s, apoi toate frecvențele anunțate de rețea în semnal.') % (
                nume_operator(lista), liste.nume_tara(lista['tara']), descriere_pornire(tps))
        else:
            text = liste.ngettext('Operatorul %s (%s): %d frecvență cunoscută, plus cele anunțate în semnal.',
                                  'Operatorul %s (%s): %d frecvențe cunoscute, plus cele anunțate în semnal.',
                                  len(tps)) % (nume_operator(lista), liste.nume_tara(lista['tara']), len(tps))
        nota = nota_operator(lista['cheie'])
        if nota:
            note.append(nota)
        if lista['ajustate']:
            note.append(_('%d valori din listă pe care imaginea nu le știe au trecut pe Auto.') % lista['ajustate'])
    else:
        hz = liste.hz_din_mhz(valori.get('frecventa'))
        sr = _int(valori.get('sr'), 0)
        if not hz or sr <= 0:
            return {'eroare': _('Introdu frecvența (MHz) și rata de simbol (kSymb/s), de exemplu 306 și 6900.')}
        tps = [liste.tp_cablu(hz // 1000, sr * 1000, _int(valori.get('mod'), liste.CAB_MOD_AUTO))]
        if fel == 'automat':
            flags = retea
            text = _('Pornire de pe %s MHz, apoi toate frecvențele anunțate în semnal.') % liste.mhz(hz)
        else:
            flags = informativ
            text = _('Un singur transponder: %s MHz, %d kSymb/s.') % (liste.mhz(hz), sr)
        if tps[0]['modulation'] == liste.CAB_MOD_AUTO:
            note.append(_('Cu modulația Auto, dacă ies 0 canale, alege QAM256 sau QAM64.'))

    for tp in tps:
        motiv = liste.motiv_refuz_cablu(tp)
        if motiv:
            return {'eroare': _('Nu se poate căuta: %s.') % motiv}
    intrebare = ''
    minute = liste.minute_maxime(len(tps))
    if minute > MINUTE_CU_INTREBARE:
        intrebare = _('Căutarea are %d încercări și poate dura până la %d minute. Pornești?') % (len(tps), minute)
    if note:
        text += ' ' + ' '.join(note)
    return {'fel': fel, 'transpondere': tps, 'slot': slot, 'flags': flags, 'text': text, 'intrebare': intrebare}


def cerere_scanare(rez, clasa=None):
    """Rezultatul lui pregateste -> lista primita de Screens.ServiceScan.ServiceScan."""
    if clasa is None:
        from enigma import eDVBFrontendParametersCable as clasa
    parametri = [liste.in_parametri(clasa, tp)[0] for tp in rez['transpondere']]
    # hds_fel: felul scanarii in /api/scanare-ultima (Components/HdsScanareUltima.py)
    return [{"transponders": parametri, "feid": rez['slot'], "flags": rez['flags'],
             "hds_fel": "cablu/%s" % rez.get('fel', '')}]


# ---------------------------------------------------------------- fereastra
# Culorile ecranului pe skinurile care nu au numele hds* (aceleasi valori ca in paleta skinului HDSatelit)
CULORI_REZERVA = {'hdsPanelDialog': '#0D10162A', 'hdsLine': '#99FFFFFF', 'hdsDivider': '#D9FFFFFF',
                  'hdsText': '#00F2F4F8', 'hdsText2': '#00C9D2E3', 'hdsAmber': '#00F5B83D', 'hdsBrand': '#00374EA1',
                  'hdsBrandLight': '#009FB4FF', 'key_red': '#00E5484D', 'key_green': '#0046B06A',
                  'key_yellow': '#00E8B93A', 'key_blue': '#003D7BE0'}
# Cotele ferestrei, pe 1920 (aceleasi ca in skin.xml): lista (inaltimea, randul, lungimea coloanei etichetei),
# previzualizarea si randul de stare
COTE_SCANER = {'lista_h': 480, 'rand': 60, 'eticheta': 440, 'linie_y': 596, 'preview_y': 608, 'preview_h': 244,
               'stare_y': 856, 'stare_h': 64}


def factor_ecran():
    """Latimea ecranului / 1920 (1 pe 1920x1080, 2/3 pe 1280x720)."""
    try:
        from enigma import getDesktop
        latime = getDesktop(0).size().width()
        return latime / 1920.0 if latime > 0 else 1.0
    except Exception:
        return 1.0


def culoare_valoare():
    """Culoarea valorilor din lista: hdsBrandLight din paleta skinului activ, altfel aceeasi valoare ca numar."""
    c = _culoare_skin('hdsBrandLight')
    return 0x9FB4FF if c is None else c


def latime_valoare(cote=None):
    """Latimea coloanei valorii, pe 1920: lista de 1176 px minus marginile de 16 si coloana etichetei
    (sablon_randuri); 672 la scanere, 632 la import."""
    k = dict(COTE_SCANER)
    k.update(cote or {})
    return 1176 - 2 * 16 - (16 + k['eticheta'] + 16)


def valoare_scurta(text, cote=None):
    """Valoarea din coloana din dreapta, intreaga: un rand care nu incape deruleaza (lib/gui/elabel.h)."""
    return text


def _procent_fonturi():
    try:
        import skin
        return skin.getFontScalePercent()
    except Exception:
        return 100


def potriveste_textul(eticheta, font, marime, marja=4):
    """„Mărime fonturi OSD” peste 100 % (Screens/FontSetup.py) mareste literele cutiilor de text (skin.parseFont), nu
    si cutiile. Un text care nu mai incape in cutia lui se scrie cu litere mai mici, pana la mărimea de la 100 %
    (`marime`, cea din skin.xml), cautata prin injumatatire: cel mult patru asezari ale textului
    (eLabel.calculateSize, cu randurile rupte ca pe ecran). La 100 % nu face nimic. Se cheama dupa setText si dupa
    asezarea ferestrei (instance exista abia atunci)."""
    procent = _procent_fonturi()
    inst = getattr(eticheta, 'instance', None)
    if procent <= 100 or inst is None:
        return
    try:
        from enigma import gFont
        inaltime = inst.size().height() - marja
        mare = marime * procent // 100
        inst.setFont(gFont(font, mare))
        if inst.calculateSize().height() <= inaltime:
            return
        jos, sus = marime, mare - 1
        while jos < sus:
            m = (jos + sus + 1) // 2
            inst.setFont(gFont(font, m))
            if inst.calculateSize().height() <= inaltime:
                jos = m
            else:
                sus = m - 1
        inst.setFont(gFont(font, jos))
    except Exception as eroare:
        print('[ScanerCablu] potrivirea textului: %s' % eroare)


def fonturi_texte(nume_ecran):
    """(font, marime la 100 %) ale previzualizarii si ale starii: cele din skin.xml cand skinul are ecranul, altfel
    cele din skin_rezerva. Pentru potriveste_textul."""
    try:
        import skin
        din_skin = skin.lookupScreen(nume_ecran, 0)[0] is not None
    except Exception:
        din_skin = True
    if din_skin:
        return {'preview': ('HdsRegular', 28), 'stare': ('HdsCond', 26)}
    f = factor_ecran()
    return {'preview': ('Regular', max(15, int(round(28 * f)))), 'stare': ('Regular', max(15, int(round(26 * f))))}


_TASTATURA = []


def tastatura():
    """Tastatura scanerelor: VirtualKeyBoard in fereastra HdsTastaturaScaner din skinul HDSatelit (cadrul ecranelor
    noastre, fara bara de titlu a stilului de fereastra, oprita la x 1312 ca sa nu intre sub fereastra PiP de la
    1344); pe alte skinuri, VirtualKeyBoard-ul lor. Clasa se face la prima folosire (Screens.VirtualKeyBoard se
    incarca abia atunci)."""
    if not _TASTATURA:
        from Screens.VirtualKeyBoard import VirtualKeyBoard

        class TastaturaScaner(VirtualKeyBoard):
            def __init__(self, session, title='', text=''):
                VirtualKeyBoard.__init__(self, session, title=title, text=text)
                self.skinName = ['HdsTastaturaScaner', 'VirtualKeyBoard']
                self.setTitle(title)

        _TASTATURA.append(TastaturaScaner)
    return _TASTATURA[0]


def sablon_randuri(latime, rand, eticheta, font_eticheta, font_valoare, margine=16, nume_eticheta='Regular',
                   nume_valoare='Regular'):
    """Sablonul TemplatedMultiContent al listei: eticheta (coloana 0 a randului) la stanga, de la 16 px, lunga de
    `eticheta`; valoarea (coloana 2) aliniata la dreapta, de la eticheta + 32 pana la 32 px de marginea listei (bara
    de derulare incepe la latime - 27), in culoarea din coloana 3. Aceleasi cote in skin.xml (scrise acolo de mana)
    si in skin_rezerva."""
    x_valoare = margine + eticheta + margine
    return ('{"template": [MultiContentEntryText(pos=(%d, 0), size=(%d, %d), font=0, flags=RT_HALIGN_LEFT | '
            'RT_VALIGN_CENTER, text=0), MultiContentEntryText(pos=(%d, 0), size=(%d, %d), font=1, '
            'flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=2, color=MultiContentTemplateColor(3))], '
            '"fonts": [gFont("%s", %d), gFont("%s", %d)], "itemHeight": %d}'
            % (margine, eticheta, rand, x_valoare, latime - 2 * margine - x_valoare, rand, nume_eticheta, font_eticheta,
               nume_valoare, font_valoare, rand))


def skin_rezerva(nume, cote=None, factor=None):
    """Skinul ferestrei pentru skinurile care nu au ecranul `nume`: desenul din skin.xml (cadrul cu titlul si ceasul
    in placa, lista pe doua coloane, previzualizarea, starea, cele patru taste cu bara lor de culoare), scris pe 1920
    si inmultit cu factorul ecranului; numai fontul Regular (Bold nu e sigur pe orice skin), culori ca numere."""
    k = dict(COTE_SCANER)
    k.update(cote or {})
    f = factor_ecran() if factor is None else factor

    def s(v):
        return max(1, int(round(v * f)))

    def fnt(v):
        # literele nu coboara sub 15 px (1280x720) si nici sub 22 px pe 1920
        return max(15, int(round(v * f)))

    c = CULORI_REZERVA
    taste = ''
    for i, (tasta, culoare) in enumerate((('key_red', c['key_red']), ('key_green', c['key_green']),
                                          ('key_yellow', c['key_yellow']), ('key_blue', c['key_blue']))):
        x = 32 + 294 * i
        # bara de culoare se vede numai cand tasta are text (ca in HdsCadru1240): o tasta nefolosita nu lasa o bara goala
        taste += ('<widget source="%s" render="FixedLabel" position="%d,%d" size="%d,%d" backgroundColor="%s" '
                  'zPosition="1"><convert type="ConditionalShowHide" /></widget>'
                  '<widget source="%s" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" '
                  'foregroundColor="%s" backgroundColor="%s" transparent="1" valign="center" noWrap="1" '
                  'zPosition="1" />' % (tasta, s(x), s(944), s(6), s(32), culoare, tasta, s(x + 16), s(936), s(270),
                                        s(48), fnt(28), c['hdsText'], c['hdsPanelDialog']))
    lista = sablon_randuri(s(1176), s(k['rand']), s(k['eticheta']), fnt(32), fnt(30), s(16))
    return (
        '<screen name="%s" position="%d,%d" size="%d,%d" backgroundColor="%s" flags="wfNoBorder">'
        '<eLabel position="0,0" size="%d,%d" backgroundColor="%s" zPosition="1" />'
        '<widget source="Title" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="%s" '
        'backgroundColor="%s" transparent="1" valign="center" noWrap="1" zPosition="1" />'
        '<widget source="global.CurrentTime" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" '
        'foregroundColor="%s" backgroundColor="%s" transparent="1" halign="right" valign="center" zPosition="1">'
        '<convert type="ClockToText">Format:%%H:%%M</convert></widget>'
        '<eLabel position="%d,%d" size="%d,1" backgroundColor="%s" zPosition="1" />'
        '<widget source="lista" render="Listbox" position="%d,%d" size="%d,%d" foregroundColor="%s" '
        'backgroundColor="%s" foregroundColorSelected="#00FFFFFF" backgroundColorSelected="%s" transparent="1" '
        'scrollbarMode="showOnDemand" zPosition="2"><convert type="TemplatedMultiContent">%s</convert></widget>'
        '<eLabel position="%d,%d" size="%d,1" backgroundColor="%s" zPosition="1" />'
        '<widget name="preview" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="%s" '
        'backgroundColor="%s" transparent="1" zPosition="1" />'
        '<widget name="stare" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="%s" '
        'backgroundColor="%s" transparent="1" valign="center" zPosition="1" />'
        '<eLabel position="%d,%d" size="%d,1" backgroundColor="%s" zPosition="1" />'
        '%s</screen>' % (
            nume, s(72), s(40), s(1240), s(1000), c['hdsPanelDialog'],
            s(1240), s(2), c['hdsLine'],
            s(32), s(18), s(1000), s(56), fnt(40), c['hdsText'], c['hdsPanelDialog'],
            s(1048), s(18), s(160), s(56), fnt(40), c['hdsText'], c['hdsPanelDialog'],
            s(32), s(88), s(1176), c['hdsDivider'],
            s(32), s(104), s(1176), s(k['lista_h']), c['hdsText'], c['hdsPanelDialog'], c['hdsBrand'], lista,
            s(32), s(k['linie_y']), s(1176), c['hdsDivider'],
            s(32), s(k['preview_y']), s(1176), s(k['preview_h']), fnt(28), c['hdsText2'], c['hdsPanelDialog'],
            s(32), s(k['stare_y']), s(1176), s(k['stare_h']), fnt(26), c['hdsAmber'], c['hdsPanelDialog'],
            s(32), s(924), s(1176), c['hdsDivider'],
            taste))


def _rand_din_skin(nume):
    """(x, y, latime, inaltime) din <parameter name=nume value="x,y,latime,inaltime"> al skinului activ, cu
    inaltimea randului listei de alegere (aliasul ChoiceList, cu marimea literelor aleasa de om), sau None."""
    try:
        from skin import getParameterFromSkin, getListFont
        cote, din_skin = getParameterFromSkin(nume, (0, 0, 0, 0))
        if not din_skin:
            return None
        _font, inaltime = getListFont('ChoiceList', ('Regular', 20, 25))
        return (cote[0], cote[1], cote[2], inaltime or cote[3])
    except Exception:
        return None


class AlegereDinLista(ChoiceBox):
    """Fereastra de alegere a tuturor scanerelor (cablu, terestru, satelit): randuri multe, cu titluri de grupa pe
    tari si note. In fereastra asta niciun rand nu are tasta (keys=['']*n): Verde si OK aleg randul luminat, iar Rosu
    inseamna inapoi, ca in scanere. Sagetile sar peste randurile fara cheie (titluri si note), deci numai cu sagetile
    si OK se ajunge doar pe randuri care se pot alege.
    In skinul HDSatelit ecranul e HdsAlegereScaner (cadrul HdsCadru1240, cu titlul in placa si tastele jos); acolo,
    daca skinul da parametrul HdsAlegereScanerRand (x,y,latime,inaltime), randurile se deseneaza pe toata latimea
    listei, titlurile de grupa si notele in culori proprii. Pe alte skinuri ramane ChoiceBox-ul lor."""

    def __init__(self, session, title='', list=None, selection=0):
        randuri = list or []
        ChoiceBox.__init__(self, session, title=title, list=randuri, keys=[''] * len(randuri), selection=selection,
                           skin_name=['HdsAlegereScaner'])
        self.setTitle(title)
        self['key_red'] = StaticText(_('Înapoi'))
        self['key_green'] = StaticText(_('Alege'))
        cote = _rand_din_skin('HdsAlegereScanerRand')
        if cote:
            self.list = [self._rand(r, cote) for r in randuri]
            self['list'].setList(self.list)
            # continutul pus inainte ca lista sa aiba marimea: bara de derulare apare abia la prima tasta; o mutare pe
            # acelasi rand, dupa asezarea ferestrei, o desenaza de la inceput (lista pare altfel ca se termina)
            self.onLayoutFinish.append(self._arataBaraDeDerulare)
        # stanga / dreapta dau pagina (in lista lunga se ajunge repede oriunde numai cu sagetile); tinute apasat,
        # sagetile merg mai departe; ridicarea tastelor e legata fara efect, ca jurnalul sa nu scrie „unknown action”
        try:
            actiuni = getattr(self['actions'], 'actions', None)
        except KeyError:
            actiuni = None
        if isinstance(actiuni, dict):
            actiuni.update({'left': self.paginaSus, 'right': self.paginaJos, 'leftRepeated': self.paginaSus,
                            'rightRepeated': self.paginaJos, 'upRepeated': self.up, 'downRepeated': self.down})
            for nume in TASTE_RIDICATE:
                actiuni.setdefault(nume, _nimic)

    def _arataBaraDeDerulare(self):
        try:
            lista = self['list']
            lista.instance.moveSelectionTo(lista.l.getCurrentSelectionIndex())
        except Exception as eroare:
            print('[ScanerCablu] bara de derulare: %s' % eroare)

    @staticmethod
    def _rand(rand, cote):
        """Randul desenat de noi: textul pe toata latimea data de skin; titlul de grupa in hdsBrandLight, nota in
        hdsAmber, randul care se poate alege in culoarea listei. Textul e intreg: un rand care nu incape deruleaza
        (lib/gui/elabel.h)."""
        from enigma import eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_CENTER
        culoare = None
        if rand[1] is None:
            culoare = _culoare_skin('hdsAmber' if liste.este_nota(rand) else 'hdsBrandLight')
        x, y, w, h = cote
        return [rand, (eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER,
                       rand[0], culoare)]

    def _sari(self, sus):
        """Muta randul luminat pana la primul rand cu cheie in directia data; daca nu exista unul, ramane unde era."""
        lista = self['list']
        n = len(lista.list)
        if not n:
            return
        pas = lista.instance.moveUp if sus else lista.instance.moveDown
        inapoi = lista.instance.moveDown if sus else lista.instance.moveUp
        facuti = 0
        for _i in range(n):
            inainte = lista.l.getCurrentSelectionIndex()
            lista.instance.moveSelection(pas)
            if lista.l.getCurrentSelectionIndex() == inainte:
                break
            facuti += 1
            rand = lista.l.getCurrentSelection()[0]
            if rand[1] is not None:
                self.updateSummary(lista.l.getCurrentSelectionIndex())
                return
        for _i in range(facuti):
            lista.instance.moveSelection(inapoi)

    def up(self):
        self._sari(True)

    def down(self):
        self._sari(False)

    def _pagina(self, sus):
        """O pagina in sus sau in jos; daca pagina se opreste pe un titlu sau pe o nota, randul luminat trece pe
        primul rand cu cheie de sub el (sau de deasupra, la capatul listei)."""
        lista = self['list']
        if not lista.list:
            return
        lista.instance.moveSelection(lista.instance.pageUp if sus else lista.instance.pageDown)
        if lista.l.getCurrentSelection()[0][1] is None:
            inainte = lista.l.getCurrentSelectionIndex()
            self._sari(False)
            if lista.l.getCurrentSelectionIndex() == inainte:
                self._sari(True)
        self.updateSummary(lista.l.getCurrentSelectionIndex())

    def paginaSus(self):
        self._pagina(True)

    def paginaJos(self):
        self._pagina(False)

    def keyGreen(self):
        self.go()

    def keyRed(self):
        self.cancel()


def _nimic():
    pass


# ridicarea sagetilor (keymap.xml, DirectionActions, flags="b"): ajunge la orice harta legata de DirectionActions
TASTE_RIDICATE = ('upUp', 'downUp', 'leftUp', 'rightUp')

# Cheia randului de actiune de la sfarsitul listei scanerelor: OK pe el porneste cautarea (acelasi lucru ca Verde),
# ca ecranul sa se poata folosi numai cu sagetile si OK. Randul e numai in lista ecranului, nu in campuri(fel), pe
# care le citeste si pagina web /scanare; cheia nu ajunge niciodata in configuratia salvata.
RAND_CAUTA = '_cauta'


def _culoare_skin(nume):
    """Culoarea `nume` din skinul activ, ca numar pentru o lista desenata din Python, sau None. Alfa FF ar fi citit
    de lista ca trimitere la o coloana a randului (MultiContentTemplateColor), deci se scoate."""
    try:
        import skin
        c = skin.colorNames.get(nume)
        if c is not None:
            v = c.argb()
            return v & 0xFFFFFF if (v >> 24) == 0xFF else v
    except Exception:
        pass
    return None


class EcranScaner(Screen):
    """Randurile felului ales, schimbate cu OK, stanga si dreapta; cautarea porneste cu OK pe ultimul rand („Caută
    acum”, RAND_CAUTA) sau cu Verde. Deschis fara fel, primul rand e felul scanarii; deschis din meniu cu felul
    dat, randul lipseste (o singura cale spre fiecare fel).
    Subclasa da: CALE_CONFIG, ANTET_CONFIG, FEL_IMPLICIT, CAMPURI_MHZ si metodele feluri(),
    campuri(fel), alegeri(camp), config_implicit(), pregateste(fel, valori), cerere(rez), titlu_fel(fel),
    preview(rez).
    Tipurile de rand: 'lista' (stanga/dreapta prin valori), 'alegere' (OK deschide lista mare, cu titluri pe
    tari), 'numeric' (OK deschide tastatura).
    Tastele sunt StaticText (key_red..key_blue), desenate de cadrul HdsCadru1240 cu bara lor de culoare; ca surse,
    pe un skin care nu le are nu lasa „skin is missing element” in jurnal."""

    CALE_CONFIG = CALE_CONFIG
    ANTET_CONFIG = 'Scaner'
    FEL_IMPLICIT = 'manual'
    CAMPURI_MHZ = ('frecventa',)
    COTE = {}

    def __init__(self, session, fel=None, config_initial=None):
        Screen.__init__(self, session)
        self.skin = skin_rezerva(self.__class__.__name__, self.COTE)
        self._fonturi = fonturi_texte(self.__class__.__name__)
        # randurile listelor de alegere nu se schimba cat ecranul e deschis: se fac o data pe camp (o sageata pe
        # randul „Operatorul” le cerea de doua-trei ori, cu citirea listelor de fiecare data)
        self._cache_alegeri = {}
        self._config = self.potriveste_config(citeste_config(self.CALE_CONFIG, self.config_implicit()))
        for cheie, valoare in (config_initial or {}).items():
            if cheie in self._config and valoare is not None:
                self._config[cheie] = str(valoare)
        coduri = [f for f, _n in self.feluri()]
        self._fel_fix = fel if fel in coduri else None
        if fel in coduri:
            self._config['fel'] = fel
        elif self._config.get('fel') not in coduri:
            self._config['fel'] = self.FEL_IMPLICIT
        self._rez_in_asteptare = None
        self._camp_in_editare = None
        self._alegere_in_editare = None
        self._culoare_valorii = culoare_valoare()
        self._intrari = []
        self._construieste_lista()

        self['lista'] = List(self._intrari, enableWrapAround=True)
        self['preview'] = Label('')
        self['stare'] = Label(self.ajutor())
        self['key_red'] = StaticText(_('Înapoi'))
        self['key_green'] = StaticText(_('Caută acum'))
        self['key_yellow'] = StaticText(_('Schimbă'))
        self['key_blue'] = StaticText(_('Salvează'))
        actiuni = {
            'red': self.inchide,
            'green': self.cauta,
            'yellow': self._galben,
            'blue': self.salveaza,
            'ok': self.schimba_valoare,
            'cancel': self.inchide,
            'up': self._sus,
            'down': self._jos,
            'left': self._stanga,
            'right': self._dreapta,
            'upRepeated': self._sus,
            'downRepeated': self._jos,
            'leftRepeated': self._stanga,
            'rightRepeated': self._dreapta,
        }
        # ridicarea tastelor, fara efect, ca jurnalul sa nu scrie „unknown action”
        actiuni.update((nume, _nimic) for nume in TASTE_RIDICATE)
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions', 'DirectionActions'], actiuni, -1)
        self._actualizeaza_preview()
        self.setTitle(self.titlu_fel(self._config['fel']))
        self.onLayoutFinish.append(self._potriveste_textele)

    def potriveste_config(self, c):
        """Loc pentru subclasa: aduce la zi valorile scrise de o versiune mai veche a ecranului."""
        return c

    def ajutor(self):
        """Randul de stare cand nu e nimic de spus: ce fac tastele. Un singur rand si cu fonturile marite la 130 %
        (Verde, „Caută acum”, se vede in bara tastelor)."""
        return _('Schimbă cu OK, stânga sau dreapta; caută cu OK pe „Caută acum”.')

    # ---- textele de sub lista (previzualizarea si starea) ----
    def _potriveste_textele(self):
        for nume in ('preview', 'stare'):
            potriveste_textul(self[nume], *self._fonturi[nume])

    def scrie_stare(self, text):
        self['stare'].setText(text)
        potriveste_textul(self['stare'], *self._fonturi['stare'])

    def _alegeri(self, cheie):
        if cheie not in self._cache_alegeri:
            self._cache_alegeri[cheie] = self.alegeri(cheie)
        return self._cache_alegeri[cheie]

    def _la_schimbare(self, cheie):
        """O valoare aleasa de om: operatorul ales ramane al lui (potriveste_config nu il mai muta)."""
        if cheie == 'operator' and 'operator_ales' in self._config:
            self._config['operator_ales'] = '1'

    # ---- randurile ----
    def _campuri(self):
        campuri = list(self.campuri(self._config['fel']))
        if self._fel_fix:
            return campuri
        return [('fel', _('Felul scanării'), 'lista', self.feluri())] + campuri

    def _scurt(self, text):
        """Valoarea din lista, intreaga (valoare_scurta)."""
        return valoare_scurta(text, self.COTE)

    def _eticheta_valoare(self, cheie, tip, optiuni):
        val = self._config.get(cheie, '')
        if tip == 'numeric':
            return val if val else '-'
        if tip == 'alegere':
            for text, c in self._alegeri(cheie):
                if c is not None and c == val:
                    return self._scurt(text.strip())
            return _('(alege cu OK)')
        for c, text in optiuni or []:
            if str(c) == str(val):
                return self._scurt(text)
        return val

    def _construieste_lista(self):
        self._intrari = [(eticheta, cheie, self._eticheta_valoare(cheie, tip, optiuni), self._culoare_valorii)
                         for cheie, eticheta, tip, optiuni in self._campuri()]
        self._intrari.append((_('Caută acum'), RAND_CAUTA, '', self._culoare_valorii))

    def _actualizeaza_preview(self):
        try:
            rez = self.pregateste(self._config['fel'], self._config)
        except Exception as e:
            rez = {'eroare': _('Eroare: %s') % e}
        self['preview'].setText(self.preview(rez))
        potriveste_textul(self['preview'], *self._fonturi['preview'])

    def preview(self, rez):
        return rez.get('eroare') or rez.get('text', '')

    def _reactualizeaza(self):
        """Randurile din nou dupa o schimbare; cursorul ramane pe randul schimbat (dupa cheie, Components/HdsCursorLista):
        setList singur l-ar duce pe primul rand."""
        self._construieste_lista()
        pune_randurile(self['lista'], self._intrari)
        self._actualizeaza_preview()
        self.setTitle(self.titlu_fel(self._config['fel']))

    def _camp_curent(self):
        selectat = self['lista'].getCurrent()
        if not selectat:
            return None
        for camp in self._campuri():
            if camp[0] == selectat[1]:
                return camp
        return None

    # ---- tastele ----
    def _sus(self):
        self['lista'].selectPrevious()

    def _jos(self):
        self['lista'].selectNext()

    def _cicleaza(self, pas):
        camp = self._camp_curent()
        if not camp:
            return
        cheie, _eticheta, tip, optiuni = camp
        if tip == 'lista' and optiuni:
            coduri = [str(c) for c, _t in optiuni]
        elif tip == 'alegere':
            # randurile care deschid alt fel de scanare (PREFIX_FEL) nu sunt valori: stanga / dreapta le sar
            coduri = [c for _t, c in self._alegeri(cheie) if c is not None and not str(c).startswith(PREFIX_FEL)]
        else:
            return
        if not coduri:
            return
        val = str(self._config.get(cheie, ''))
        idx = coduri.index(val) if val in coduri else (-1 if pas > 0 else 0)
        self._config[cheie] = coduri[(idx + pas) % len(coduri)]
        self._la_schimbare(cheie)
        self._reactualizeaza()

    def _stanga(self):
        self._cicleaza(-1)

    def _dreapta(self):
        self._cicleaza(1)

    def _galben(self):
        """Galben („Schimbă”) schimba numai valori; pe randul „Caută acum” nu porneste cautarea."""
        selectat = self['lista'].getCurrent()
        if selectat and selectat[1] == RAND_CAUTA:
            return
        self.schimba_valoare()

    def schimba_valoare(self):
        """OK: alegerile randului luminat (fereastra de alegere; tastatura la numere); pe randul "Caută acum" porneste
        cautarea, ca Verde."""
        selectat = self['lista'].getCurrent()
        if selectat and selectat[1] == RAND_CAUTA:
            self.cauta()
            return
        camp = self._camp_curent()
        if not camp:
            return
        cheie, eticheta, tip, optiuni = camp
        if tip == 'lista':
            # aceeasi fereastra de alegere ca la randurile cu liste lungi (si ca in Scanare detaliata): OK arata
            # valorile, nu sare la urmatoarea; stanga / dreapta le schimba pe loc
            randuri = [(text, str(c)) for c, text in optiuni or []]
            if not randuri:
                return
            val = str(self._config.get(cheie, ''))
            poz = [i for i, r in enumerate(randuri) if r[1] == val]
            self._alegere_in_editare = cheie
            self.session.openWithCallback(self._dupaAlegere, AlegereDinLista, title=eticheta, list=randuri,
                                          selection=poz[0] if poz else 0)
        elif tip == 'alegere':
            randuri = self._alegeri(cheie)
            if not randuri:
                self.scrie_stare(_('Lista e goală: fișierul cu frecvențe lipsește de pe receptor.'))
                return
            val = self._config.get(cheie, '')
            poz = [i for i, r in enumerate(randuri) if r[1] is not None and r[1] == val]
            if not poz:
                poz = [i for i, r in enumerate(randuri) if r[1] is not None]
            self._alegere_in_editare = cheie
            self.session.openWithCallback(self._dupaAlegere, AlegereDinLista, title=eticheta, list=randuri,
                                          selection=poz[0] if poz else 0)
        elif tip == 'numeric':
            self._camp_in_editare = cheie
            self.session.openWithCallback(self._dupaTastatura, tastatura(), title=eticheta,
                                          text=self._config.get(cheie, ''))

    def deschide_fel(self, fel):
        """Randul din lista de alegere care duce la alt fel de scanare (PREFIX_FEL): fereastra acelui fel, deasupra
        acesteia (Inapoi se intoarce aici). Subclasa da clasa ei."""
        self.session.open(self.__class__, fel)

    def _dupaAlegere(self, rand=None):
        cheie, self._alegere_in_editare = self._alegere_in_editare, None
        if not rand or cheie is None:
            return
        if rand[1] is None:
            if liste.este_nota(rand):
                self.scrie_stare(_('Acel rând e o explicație și nu se poate alege.'))
            else:
                self.scrie_stare(_('Acela e un titlu de grupă. Alege un rând de sub el.'))
            return
        if str(rand[1]).startswith(PREFIX_FEL):
            # nu e o valoare a campului (configuratia ramane cum era): deschide felul acela
            self.deschide_fel(str(rand[1])[len(PREFIX_FEL):])
            return
        self._config[cheie] = rand[1]
        self._la_schimbare(cheie)
        self.scrie_stare(self.ajutor())
        self._reactualizeaza()

    def _dupaTastatura(self, text=None):
        cheie, self._camp_in_editare = self._camp_in_editare, None
        if text is None or cheie is None:
            return
        text = text.strip()
        if cheie in self.CAMPURI_MHZ:
            bun = not text or liste.hz_din_mhz(text) is not None
        else:
            bun = not text or text.isdigit()
        if not bun:
            self.scrie_stare(_('Valoare nevalidă: aici se scrie un număr.'))
            return
        self._config[cheie] = text
        self.scrie_stare(self.ajutor())
        self._reactualizeaza()

    # ---- cautarea ----
    def cauta(self):
        scrie_config(self.CALE_CONFIG, self._config, self.ANTET_CONFIG)
        try:
            rez = self.pregateste(self._config['fel'], self._config)
        except Exception as e:
            self.scrie_stare(_('Eroare: %s') % e)
            return
        if rez.get('eroare'):
            self._eroare(rez['eroare'])
            return
        if rez.get('intrebare'):
            self._rez_in_asteptare = rez
            from Screens.MessageBox import MessageBox
            self.session.openWithCallback(self._dupaIntrebare, MessageBox, rez['intrebare'], MessageBox.TYPE_YESNO)
            return
        self._porneste(rez)

    def _dupaIntrebare(self, da=False):
        rez, self._rez_in_asteptare = self._rez_in_asteptare, None
        if not rez:
            return
        if not da:
            self.scrie_stare(_('Căutarea nu a pornit.'))
            return
        self._porneste(rez)

    def _porneste(self, rez):
        try:
            cerere = self.cerere(rez)
        except Exception as e:
            self.scrie_stare(_('Eroare: %s') % e)
            return
        # ce se cauta ramane scris in previzualizare; la intoarcerea din cautare starea arata iar ajutorul
        self.scrie_stare(self.ajutor())
        from Screens.ServiceScan import ServiceScan
        self.session.open(ServiceScan, cerere)

    def _eroare(self, text):
        self.scrie_stare(text)
        from Screens.MessageBox import MessageBox
        self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)

    def salveaza(self):
        scrie_config(self.CALE_CONFIG, self._config, self.ANTET_CONFIG)
        self.scrie_stare(_('Salvat.'))

    def inchide(self):
        scrie_config(self.CALE_CONFIG, self._config, self.ANTET_CONFIG)
        self.close()


class ScanerCablu(EcranScaner):
    """Scanerul de cablu: cele cinci feluri din FELURI, pe primul tuner DVB-C pornit."""

    CALE_CONFIG = CALE_CONFIG
    ANTET_CONFIG = 'Scaner de cablu HDSatelit: ultimii parametri folositi'
    FEL_IMPLICIT = 'manual'
    CAMPURI_MHZ = ('frecventa',)

    def __init__(self, session, fel=None, config_initial=None):
        EcranScaner.__init__(self, session, fel, config_initial)

    def feluri(self):
        return nume_feluri()

    def titlu_fel(self, fel):
        return '%s: %s' % (_('Scanare prin cablu'), titluri_scurte().get(fel, ''))

    def config_implicit(self):
        return config_implicit()

    def potriveste_config(self, c):
        """Operatorul salvat de o versiune mai veche, cand ecranul tinea minte orice rand (operator_ales gol), si care
        nu e din tara omului (de exemplu Ziggo, primul rand al listei vechi) trece pe primul operator din tara lui.
        Dupa o alegere a omului (_la_schimbare), operatorul ramane oricare ar fi."""
        if c.get('operator_ales') == '1':
            return c
        tara3 = liste.tara_alfa3()
        lista = liste.gaseste(liste.liste_cablu(), c.get('operator'))
        if tara3 and (lista is None or lista.get('tara') != tara3):
            implicit = config_implicit()
            if implicit.get('operator'):
                c['operator'] = implicit['operator']
        return c

    def campuri(self, fel):
        return campuri(fel)

    def alegeri(self, camp):
        return alegeri(camp)

    def pregateste(self, fel, valori):
        return pregateste(fel, valori)

    def cerere(self, rez):
        return cerere_scanare(rez)

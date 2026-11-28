# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ScanerOarba.py: ecranul 'Căutare oarbă pe satelit' (Scanare > Satelit).

Scris de la zero.

Cipul tunerului cauta singur transponderele pe toata banda, fara frecvente stiute dinainte (programul nostru
hds-blindscan). Ecranul are doua fete: alegerile (satelitul, banda, polarizarile, rata minima; satelitul e implicit cel
pe care sta antena acum, iar din 0.7.7 se alege cu Stanga/Dreapta dintre cei la care se ajunge fara sa se miste antena:
comutatorul DiSEqC / toneburst il trimite programul; la antena cu motor si satelitii la care se poate roti, iar
antena se roteste intai) si cautarea (progresul si lista: fiecare
transponder cunoscut al satelitului cu 'găsit' / 'se caută', cele noi cu 'nou'), apoi 'Scanează canalele' = un
ServiceScan obisnuit pe cunoscute si noi.

Tot lucrul e in Components/HdsCautareOarba.py: o singura cautare pe receptor, aceeasi pe care o vede si o porneste
pagina web /oarba; ecranul doar o arata. EXIT in timpul cautarii o opreste curat (dupa bucata de banda in curs).

0.8.0 (AMR4, el bandido, LegitFTA post-110268): lista nu mai amesteca ce a gasit cautarea cu ce era in lista
satelitului. Cat merge cautarea: numai purtatoarele gasite pana acum, cea mai noua sus (frecventa, polarizarea, rata,
sistemul), iar caseta Durata e cronometrul (cat a trecut, cat mai tine treapta). La sfarsit, pe sectiuni cu numaratori:
Noi (fiecare „se păstrează” din fabrica; Albastru o lasa deoparte sau o pune la loc), Deja în listă, Căzute la acordare
(dupa „Scanează canalele”) si, jos, Din listă, negăsite. OK sau Verde: „Scanează canalele” cu cele pastrate, o tasta.
"""
from __future__ import absolute_import, unicode_literals

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components import HdsCautareOarba as O
from Components.HdsCursorLista import pune_randurile

RAND_CAUTA = '_cauta'
# 0.8.0 (AMR4): randurile de cap ale sectiunilor raportului si cele din lista satelitului negasite (chei proprii, ca
# HdsCursorLista sa tina cursorul pe acelasi rand cand lista se reface)
RAND_SECTIUNE = '_sectiune_'
RAND_LISTA = '_lista_'
# 0.7.7 (M30): la antena cu motor randul "Satelit" are zeci de sateliti; de la atatia alegeri, OK deschide lista lor
PRAG_LISTA_SATELITI = 8
# DSG2: casetele cautarii, in ordinea din skin (HdsCautareOarba.casete)
CASETE = ('transp', 'progres', 'durata')


def _vede(eticheta, da):
    """Arata sau ascunde o eticheta (casetele DSG2)."""
    f = getattr(eticheta, 'show' if da else 'hide', None)
    if f is not None:
        f()


def _nume_valoare(lista, cod):
    for c, n in lista:
        if c == cod:
            return n
    return str(cod)


class ScanerOarba(Screen):
    """Fereastra: <screen name="ScanerOarba"> din skinul HDSatelit; pe alt skin, skin_rezerva din
    Screens/ScanerCablu.py, cu aceleasi cote ca scanerul de satelit."""

    COTE = {'lista_h': 564, 'rand': 47, 'eticheta': 440, 'linie_y': 680, 'preview_y': 692, 'preview_h': 160,
            'stare_y': 856, 'stare_h': 64}

    def __init__(self, session, *_argumente):
        Screen.__init__(self, session)
        from Screens.ScanerCablu import skin_rezerva, culoare_valoare
        self.skin = skin_rezerva('ScanerOarba', self.COTE)
        self._culoare_valorii = culoare_valoare()
        self._c = O.cautare()
        try:
            self._antena = O.antena(session)
        except Exception as e:
            print('[ScanerOarba] antena: %s' % e)
            self._antena = {'motiv': _('Nu pot citi setările tunerului de satelit.'), 'osc': None, 'nume': '',
                            'motor': False, 'sateliti': [], 'pozitie': None, 'slot': None}
        self._doua_benzi = O.are_doua_benzi(self._antena.get('osc'))
        self._config = dict(O.ULTIMELE)
        # 0.7.7 (WLD, Wlad forum 948 #2359): satelitul ales in randul "Satelit" (None = cel pe care sta antena, al
        # canalului pornit); nu intra in ULTIMELE: fiecare deschidere porneste de la canalul pornit
        self._pozitie = None
        # fata cu lista: cand cautarea merge (pornita de aici sau din web) sau cand am pornit-o din acest ecran
        self._urmareste = self._c.in_curs()
        self._mesaj = ''
        # 0.8.0 (AMR4): randurile noi ale raportului aratat (cheie -> rand, pentru Albastru si eticheta lui); raportul s-a
        # aratat o data (cursorul pus pe prima noua); "Scanează canalele" pornita de aici (al doilea OK nu o reia)
        self._noi = {}
        self._raport_aratat = False
        self._scanat = False

        self['lista'] = List([], enableWrapAround=True)
        self['preview'] = Label('')
        self['stare'] = Label('')
        self['key_red'] = StaticText('')
        self['key_green'] = StaticText('')
        self['key_yellow'] = StaticText('')
        self['key_blue'] = StaticText('')
        # DSG2: casetele cautarii (skinul HDSatelit: blocul DSG2 din ecranul ScanerOarba); pe alt skin ramane preview
        for k in CASETE:
            for parte in ('box', 'lin', 'cap', 'num', 'sub'):
                self['oarba_%s_%s' % (parte, k)] = Label('')
                _vede(self['oarba_%s_%s' % (parte, k)], False)
        self['oarba_loc'] = Label('')
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions', 'DirectionActions'], {
            'red': self.inapoi, 'cancel': self.inapoi, 'green': self.verde, 'yellow': self.galben, 'ok': self.ok,
            'blue': self.albastru,
            'up': self._sus, 'down': self._jos, 'left': lambda: self._cicleaza(-1), 'right': lambda: self._cicleaza(1),
            'upRepeated': self._sus, 'downRepeated': self._jos,
        }, -1)
        self._c.adauga_ascultator(self._schimbare)
        # 0.8.0 (AMR4): cronometrul merge din secunda in secunda, si cand programul nu scrie nimic
        adauga_ceas = getattr(self._c, 'adauga_ascultator_ceas', None)
        if adauga_ceas is not None:
            adauga_ceas(self._la_ceas)
        # 0.7.7 (BSC): pe Vu+ Solo SE, aducerea programului Vu+ la prima cautare: pasul cu timpul scurs si esecul, aici
        self._i = O.instalare_vuplus()
        self._i.adauga_ascultator(self._la_instalare)
        self.onClose.append(self._la_inchidere)
        self.setTitle(_('Căutare oarbă pe satelit'))
        self._arata()
        # casetele se stiu numai dupa ce skinul s-a pus (hdsAreCasete)
        if hasattr(self, 'onLayoutFinish'):
            self.onLayoutFinish.append(self._arata)
        # 0.8.0 (AMR4): dupa „Scanează canalele” ecranul se arata din nou: cele cazute la acordare trec in sectiunea lor
        if hasattr(self, 'onShown'):
            self.onShown.append(self._la_aratare)

    # ---------------------------------------------------------------- ce se arata
    def _fata_lista(self):
        return self._urmareste or self._c.in_curs()

    def _arata(self):
        if self._fata_lista():
            self._arata_cautarea()
        else:
            self._arata_alegerile()

    def _campuri(self):
        rez = [('pozitie', _('Satelit'), None)]
        if self._doua_benzi:
            rez.append(('banda', _('Banda'), O.alegeri_traduse('banda')))
        rez += [('polarizari', _('Polarizările'), O.alegeri_traduse('polarizari')),
                ('trepte', _('Treptele căutării'), O.alegeri_traduse('trepte')),
                ('rata_min', _('Rata minimă'), O.alegeri_traduse('rata_min'))]
        return rez

    def _text_satelit(self):
        return O.text_satelit(self._antena)

    def _arata_alegerile(self):
        randuri = []
        for cheie, eticheta, lista in self._campuri():
            valoare = self._text_satelit() if cheie == 'pozitie' else _nume_valoare(lista, self._config.get(cheie))
            randuri.append((eticheta, cheie, valoare, self._culoare_valorii))
        randuri.append((_('Caută acum'), RAND_CAUTA, '', self._culoare_valorii))
        pune_randurile(self['lista'], randuri)
        self.hdsArataCasetele(None)
        self['preview'].setText(self._preview())
        self['stare'].setText(self._text_alegeri())
        self['key_red'].setText(_('Înapoi'))
        self['key_green'].setText(_('Caută acum') if not self._antena.get('motiv') else '')
        self['key_yellow'].setText(_('Schimbă'))
        self['key_blue'].setText('')

    def _text_alegeri(self):
        """Randul de stare de sub alegeri: aducerea programului Vu+ (pasul sau esecul), refuzul ultimei porniri sau ajutorul."""
        if self._i.in_curs():
            return self._i.text()
        return self._mesaj or self._i.text() or _('Sus/Jos alege rândul, Stânga/Dreapta sau OK schimbă, Verde '
                                                  'pornește, EXIT oprește.')

    def _la_instalare(self, _i):
        try:
            if not self._fata_lista():
                self['stare'].setText(self._text_alegeri())
        except Exception as e:
            print('[ScanerOarba] starea instalarii: %s' % e)

    def _preview(self):
        return O.text_previzualizare(self._antena, self._config)

    @staticmethod
    def _cu_sistem(sistem, text):
        """'DVB-S2, text' cand sistemul e stiut, altfel numai textul."""
        return ', '.join(x for x in (sistem, text) if x)

    def _randuri_raport(self, c):
        """0.8.0 (AMR4): randurile de la sfarsit, pe sectiuni (HdsCautareOarba.sectiuni): capul fiecareia cu numaratoarea
        (Noi si Deja în listă mereu, celelalte numai cand au ceva), apoi purtatoarele ei."""
        rez = []
        sect = c.sectiuni_acum()
        self._noi = dict((r['cheie'], r) for r in dict(sect).get('noi', []))
        for cheie, lista in sect:
            if not lista and cheie not in ('noi', 'in_lista'):
                continue
            rez.append((O.titlu_sectiune(cheie, len(lista), c.faza == O.OPRIT), RAND_SECTIUNE + cheie, '',
                        self._culoare_valorii))
            for r in lista:
                if cheie == 'negasite':
                    rez.append((O.text_tp(r['tp']), RAND_LISTA + r['cheie'], O.text_stare(r['stare']),
                                self._culoare_valorii))
                elif r.get('alege'):
                    rez.append((O.text_tp(r['tp']), r['cheie'],
                                self._cu_sistem(r['sistem'], O.text_pastrat(r['pastrat'])), self._culoare_valorii))
                else:
                    rez.append((O.text_tp(r['tp']), r['cheie'], r['sistem'], self._culoare_valorii))
        return rez

    def _index(self):
        f = getattr(self['lista'], 'getIndex', None)
        try:
            return f() if f is not None else None
        except Exception:
            return None

    def _arata_cautarea(self):
        c = self._c
        if c.gata_sau_oprita():
            randuri = self._randuri_raport(c)
            pune_randurile(self['lista'], randuri)
            if not self._raport_aratat:
                # prima aratare a raportului: cursorul pe prima purtatoare noua (Albastru se vede de la inceput)
                self._raport_aratat = True
                prima = [i for i, r in enumerate(randuri) if r[1] in self._noi]
                self['lista'].setIndex(prima[0] if prima else 0)
        else:
            # 0.8.0 (AMR4): cat merge cautarea, numai ce a gasit pana acum, cea mai noua sus (text scurt: in germana
            # sau maghiara randul lung nu incape)
            self._noi = {}
            self._raport_aratat = False
            # o cautare noua (si una pornita din pagina web): primul OK din raportul ei porneste iar scanarea
            self._scanat = False
            randuri = [(O.text_tp(r['tp']), r['cheie'], self._cu_sistem(r['sistem'], O.text_gasita(r['stare'])),
                        self._culoare_valorii) for r in c.gasite_acum()]
            if not randuri and c.in_curs():
                randuri = [(_('Se caută...'), '', '', self._culoare_valorii)]
            # cursorul sus ramane sus, pe cea mai noua (altfel pune_randurile il tine pe aceeasi purtatoare si fereastra
            # aluneca spre cele vechi); daca omul a coborat in lista, ramane unde era
            sus = self._index() in (0, None)
            pune_randurile(self['lista'], randuri)
            if sus and randuri:
                self['lista'].setIndex(0)
        self._arata_starea()
        if c.in_curs():
            self['key_red'].setText(_('Oprește') if c.faza != O.OPRESTE else '')
            self['key_green'].setText('')
            self['key_yellow'].setText('')
        else:
            self['key_red'].setText(_('Înapoi'))
            self['key_green'].setText(_('Scanează canalele') if c.stare()['poate_scana'] else '')
            self['key_yellow'].setText(_('Caută din nou'))
        self._eticheta_albastra()

    def _arata_starea(self):
        """Casetele (cu cronometrul), randul satelitului si randul de stare; chemat si din secunda in secunda."""
        c = self._c
        satelit = c.nume_satelit or self._text_satelit()
        if c.satelit_schimbat:
            loc = _('Transponderele găsite arată că antena stă pe %s.') % satelit
        else:
            loc = _('Satelit: %s') % satelit
        # cu casete, randul satelitului sta sub ele (oarba_loc), iar preview ramane gol; altfel, ca inainte
        self['preview'].setText('' if self.hdsArataCasetele(c.stare(), loc) else loc)
        self['stare'].setText(c.text_stare())

    def _rand_ales(self):
        """0.8.0 (AMR4): randul raportului de sub cursor cand e o purtatoare noua (se poate lasa deoparte), altfel None.
        Din randurile noi ale raportului aratat (_noi), fara sa se socoteasca din nou la fiecare Sus/Jos."""
        if not self._fata_lista() or not self._c.gata_sau_oprita():
            return None
        rand = self._rand()
        cheie = rand[1] if rand and len(rand) > 1 else None
        return self._noi.get(cheie) if cheie else None

    def _eticheta_albastra(self):
        r = self._rand_ales()
        self['key_blue'].setText('' if r is None else (_('Nu păstra') if r['pastrat'] else _('Păstrează')))

    def _la_ceas(self, _c):
        try:
            if self._fata_lista() and self._c.in_curs():
                self._arata_starea()
        except Exception as e:
            print('[ScanerOarba] cronometrul: %s' % e)

    def _la_aratare(self):
        try:
            if self._fata_lista():
                self._arata_cautarea()
        except Exception as e:
            print('[ScanerOarba] aratarea din nou: %s' % e)

    def hdsAreCasete(self):
        """True cand skinul are casetele (blocul DSG2 din ecranul ScanerOarba al skinului HDSatelit)."""
        return bool(getattr(self['oarba_num_transp'], 'skinAttributes', None))

    def hdsArataCasetele(self, st, loc=''):
        """DSG2: casetele cautarii din HdsCautareOarba.casete(st); st None (fata alegerilor) sau fara casete in skin: le
        ascunde. In tema Pro se vede fundalul casetei, in Clasic linia subtire de sus. True cand le-a aratat."""
        lista = O.casete(st) if st is not None and self.hdsAreCasete() else []
        pro = False
        if lista:
            try:
                from Components import HdsTemaTv
                pro = HdsTemaTv.activa() == 'pro'
            except Exception:
                pro = False
        texte = dict((k, (num, cap, sub)) for k, num, cap, sub in lista)
        for k in CASETE:
            t = texte.get(k)
            for parte, text in zip(('num', 'cap', 'sub'), t or ('', '', '')):
                self['oarba_%s_%s' % (parte, k)].setText(text)
            for parte in ('num', 'cap', 'sub'):
                _vede(self['oarba_%s_%s' % (parte, k)], t)
            _vede(self['oarba_box_%s' % k], t and pro)
            _vede(self['oarba_lin_%s' % k], t and not pro)
        self['oarba_loc'].setText(loc if lista else '')
        return bool(lista)

    def _schimbare(self, _c):
        try:
            # o cautare pornita din web cu ecranul deja deschis: ecranul o urmareste pana la capat (altfel, la sfarsit,
            # in_curs() e fals si ecranul ramanea pe ultimul progres, cu 'Oprește')
            if self._c.in_curs():
                self._urmareste = True
            if self._fata_lista():
                self._arata_cautarea()
        except Exception as e:
            print('[ScanerOarba] actualizarea ecranului: %s' % e)

    # ---------------------------------------------------------------- taste
    def _rand(self):
        return self['lista'].getCurrent()

    def _sus(self):
        self['lista'].selectPrevious()
        self._eticheta_albastra()

    def _jos(self):
        self['lista'].selectNext()
        self._eticheta_albastra()

    def _alegeri_satelit(self):
        """[(pozitie, nume, slot)] din randul "Satelit" (HdsCautareOarba.antena), cu doua sau mai multe: se alege."""
        return self._antena.get('alegeri') or []

    def _schimba_satelitul(self, pas):
        """Stanga/Dreapta/OK pe randul "Satelit": urmatorul satelit din alegeri (comutatorul DiSEqC / toneburst al lui
        il trimite programul; la motor antena se roteste inainte de cautare). Tunerul, LNB-ul (deci si randul Banda) si
        nota sunt ale lui."""
        alegeri = self._alegeri_satelit()
        if len(alegeri) < 2:
            return
        pozitii = [p for p, _n, _s in alegeri]
        cur = self._antena.get('pozitie')
        i = pozitii.index(cur) if cur in pozitii else 0
        self._pune_satelitul(pozitii[(i + pas) % len(pozitii)])

    def _pune_satelitul(self, noua):
        """Satelitul ales (din Stanga/Dreapta sau din lista): antena, tunerul, LNB-ul si randul Banda ale lui."""
        try:
            antena = O.antena(self.session, noua)
        except Exception as e:
            print('[ScanerOarba] satelitul ales: %s' % e)
            return
        self._antena = antena
        self._pozitie = noua
        self._doua_benzi = O.are_doua_benzi(antena.get('osc'))
        self._mesaj = ''
        self._arata_alegerile()

    def _cicleaza(self, pas):
        if self._fata_lista():
            return
        rand = self._rand()
        if rand and rand[1] == 'pozitie':
            self._schimba_satelitul(pas)
            return
        optiuni = O.ALEGERI.get(rand[1]) if rand else None
        if not optiuni:
            return
        chei = [c for c, _n in optiuni]
        cur = self._config.get(rand[1])
        self._config[rand[1]] = chei[(chei.index(cur) + pas) % len(chei)] if cur in chei else chei[0]
        O.ULTIMELE.update(self._config)
        self._mesaj = ''
        self._arata_alegerile()

    def ok(self):
        if self._fata_lista():
            # 0.8.0 (AMR4): la sfarsit OK = „Scanează canalele”, ca Verde (din fabrica toate cele noi se pastreaza); o
            # singura data: dupa intoarcerea din scanare un OK nu o mai porneste de la capat (Verde da)
            if not self._c.in_curs() and not self._scanat:
                self.verde()
            return
        rand = self._rand()
        if rand and rand[1] == RAND_CAUTA:
            self.cauta()
        elif rand and rand[1] == 'pozitie' and len(self._alegeri_satelit()) > PRAG_LISTA_SATELITI:
            self._lista_satelitilor()
        else:
            self._cicleaza(1)

    def _lista_satelitilor(self):
        """0.7.7 (M30): OK pe randul "Satelit" cu multe alegeri (antena cu motor): lista satelitilor, cursorul pe cel de
        acum; Stanga/Dreapta merg in continuare unul cate unul."""
        lista = [(n, p) for p, n, _s in self._alegeri_satelit()]
        cur = self._antena.get('pozitie')
        sel = 0
        for i, (_n, p) in enumerate(lista):
            if p == cur:
                sel = i
                break
        try:
            from Screens.ChoiceBox import ChoiceBox
            self.session.openWithCallback(self._satelit_din_lista, ChoiceBox, title=_('Satelit'), list=lista,
                                          selection=sel)
        except Exception as e:
            print('[ScanerOarba] lista satelitilor: %s' % e)
            self._schimba_satelitul(1)

    def _satelit_din_lista(self, ales):
        if ales and not self._fata_lista():
            self._pune_satelitul(ales[1])

    def verde(self):
        if not self._fata_lista():
            self.cauta()
        elif not self._c.in_curs() and self._c.stare()['poate_scana']:
            refuz = O.scaneaza_canalele(self.session)
            if refuz:
                self['stare'].setText(refuz)
            else:
                self._scanat = True

    def albastru(self):
        """0.8.0 (AMR4): pe o purtatoare noua din raport, o lasa deoparte sau o pune la loc (nu merge la „Scanează
        canalele”); alegerea e a cautarii, deci se vede si in pagina web."""
        r = self._rand_ales()
        if r is not None:
            self._c.pastreaza(r['cheie'])

    def galben(self):
        if not self._fata_lista():
            self._cicleaza(1)
        elif not self._c.in_curs():
            # 'Caută din nou': inapoi la alegeri
            self._urmareste = False
            self._arata_alegerile()

    def inapoi(self):
        if self._c.in_curs():
            # EXIT in timpul cautarii: o opreste curat si ramane pe lista gasite
            self._c.opreste()
            self._arata_cautarea()
            return
        self.close()

    # ---------------------------------------------------------------- cautarea
    def cauta(self):
        if self._antena.get('motiv'):
            self['stare'].setText(self._antena['motiv'])
            return
        refuz = O.porneste_pe_receptor(self.session, O.cerere_din(dict(self._config, pozitie=self._pozitie)))
        if refuz:
            # aducerea programului Vu+ isi scrie singura pasul si esecul (_text_alegeri); celelalte refuzuri raman aici
            dela_instalare = self._i.in_curs() or (self._i.esec_recent() and refuz == self._i.eroare)
            self._mesaj = '' if dela_instalare else refuz
            self._arata_alegerile()
            return
        self._mesaj = ''
        self._urmareste = True
        self._scanat = False
        self['lista'].setIndex(0)
        self._arata_cautarea()

    def _la_inchidere(self):
        # cautarea (daca mai merge) continua; o vede pagina web, iar la sfarsit canalul de dinainte porneste din nou
        self._c.scoate_ascultator(self._schimbare)
        scoate_ceas = getattr(self._c, 'scoate_ascultator_ceas', None)
        if scoate_ceas is not None:
            scoate_ceas(self._la_ceas)
        self._i.scoate_ascultator(self._la_instalare)

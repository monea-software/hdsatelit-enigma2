# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ScanerOarba.py: ecranul 'Căutare oarbă pe satelit' (Scanare > Satelit).

Scris de la zero.

Cipul tunerului cauta singur transponderele pe toata banda, fara frecvente stiute dinainte (programul nostru
hds-blindscan). Ecranul are doua fete: alegerile (banda, polarizarile, rata minima; satelitul e cel pe care sta antena
acum, programul nu o misca) si cautarea (progresul si lista: fiecare transponder cunoscut al satelitului cu 'găsit' /
'se caută', cele noi cu 'nou'), apoi 'Scanează canalele' = un ServiceScan obisnuit pe cunoscute si noi.

Tot lucrul e in Components/HdsCautareOarba.py: o singura cautare pe receptor, aceeasi pe care o vede si o porneste
pagina web /oarba; ecranul doar o arata. EXIT in timpul cautarii o opreste curat (dupa bucata de banda in curs).
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
        # fata cu lista: cand cautarea merge (pornita de aici sau din web) sau cand am pornit-o din acest ecran
        self._urmareste = self._c.in_curs()
        self._mesaj = ''

        self['lista'] = List([], enableWrapAround=True)
        self['preview'] = Label('')
        self['stare'] = Label('')
        self['key_red'] = StaticText('')
        self['key_green'] = StaticText('')
        self['key_yellow'] = StaticText('')
        self['key_blue'] = StaticText('')
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions', 'DirectionActions'], {
            'red': self.inapoi, 'cancel': self.inapoi, 'green': self.verde, 'yellow': self.galben, 'ok': self.ok,
            'up': self._sus, 'down': self._jos, 'left': lambda: self._cicleaza(-1), 'right': lambda: self._cicleaza(1),
            'upRepeated': self._sus, 'downRepeated': self._jos,
        }, -1)
        self._c.adauga_ascultator(self._schimbare)
        self.onClose.append(self._la_inchidere)
        self.setTitle(_('Căutare oarbă pe satelit'))
        self._arata()

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
        self['preview'].setText(self._preview())
        self['stare'].setText(self._mesaj or _('Sus/Jos alege rândul, Stânga/Dreapta sau OK schimbă, Verde pornește, '
                                               'EXIT oprește.'))
        self['key_red'].setText(_('Înapoi'))
        self['key_green'].setText(_('Caută acum') if not self._antena.get('motiv') else '')
        self['key_yellow'].setText(_('Schimbă'))

    def _preview(self):
        return O.text_previzualizare(self._antena, self._config)

    def _arata_cautarea(self):
        c = self._c
        randuri = [(O.text_tp(r['tp']), '', O.text_stare(r['stare']), self._culoare_valorii)
                   for r in c.randuri_acum()]
        if not randuri:
            randuri = [(_('Se caută...'), '', '', self._culoare_valorii)]
        pune_randurile(self['lista'], randuri)
        satelit = c.nume_satelit or self._text_satelit()
        if c.satelit_schimbat:
            self['preview'].setText(_('Transponderele găsite arată că antena stă pe %s.') % satelit)
        else:
            self['preview'].setText(_('Satelit: %s') % satelit)
        self['stare'].setText(c.text_stare())
        if c.in_curs():
            self['key_red'].setText(_('Oprește') if c.faza != O.OPRESTE else '')
            self['key_green'].setText('')
            self['key_yellow'].setText('')
        else:
            self['key_red'].setText(_('Înapoi'))
            self['key_green'].setText(_('Scanează canalele') if c.stare()['poate_scana'] else '')
            self['key_yellow'].setText(_('Caută din nou'))

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

    def _jos(self):
        self['lista'].selectNext()

    def _cicleaza(self, pas):
        if self._fata_lista():
            return
        rand = self._rand()
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
            return
        rand = self._rand()
        if rand and rand[1] == RAND_CAUTA:
            self.cauta()
        else:
            self._cicleaza(1)

    def verde(self):
        if not self._fata_lista():
            self.cauta()
        elif not self._c.in_curs() and self._c.stare()['poate_scana']:
            refuz = O.scaneaza_canalele(self.session)
            if refuz:
                self['stare'].setText(refuz)

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
        refuz = O.porneste_pe_receptor(self.session, O.cerere_din(self._config))
        if refuz:
            self._mesaj = refuz
            self._arata_alegerile()
            return
        self._mesaj = ''
        self._urmareste = True
        self['lista'].setIndex(0)
        self._arata_cautarea()

    def _la_inchidere(self):
        # cautarea (daca mai merge) continua; o vede pagina web, iar la sfarsit canalul de dinainte porneste din nou
        self._c.scoate_ascultator(self._schimbare)

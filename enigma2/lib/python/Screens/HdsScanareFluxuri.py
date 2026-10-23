# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsScanareFluxuri.py: ecranul scanarii „DAB+ prin satelit" si „DVB-T2 prin satelit" (felurile 6 si 7 din
# Screens/ScanerSatelit.py). Toata logica e in ScanerSatelit.CautareFluxuri si plan_fluxuri; aici numai cele trei
# fete ale ferestrei:
#   inainte   ce se va intampla: operatorul, satelitul, transponderul, unde se roteste antena si cat dureaza
#             (plan_fluxuri); randurile „Pornește scanarea" si „Renunță";
#   in curs   satelitul, pasul (acord si rotire, cautare, salvare, citirea listelor prin releu), grupele gasite pana
#             atunci (ansamblurile DAB+ vin din detector cat inca lucreaza) si „Oprește scanarea";
#   sfarsit   posturile gasite, pe ansambluri (DAB+) sau multiplexuri (DVB-T2): capul grupei cu numarul posturilor,
#             apoi posturile ei, fiecare cu „Ascultă" (OK = il pornesti, antena ramane pe satelitul scanat; cursorul
#             sare peste capete) si „Înapoi la canalul meu" (sau „Închide", cand inainte nu mergea nimic); fara
#             rezultat: „Caută din nou". Cat ecranul asteapta alegerea, cautarea tine tunerul pe purtator, deci antena
#             nu pleaca (ScanerSatelit.CautareFluxuri). Nimic nu se intoarce pe
#             canalul de dinainte fara sa se spuna: EXIT la sfarsit are acelasi nume ca tasta rosie. La esec raman
#             grupele vazute in timpul scanarii, fraza simpla sta in previzualizare, iar detaliul tehnic (codul
#             detectorului, termenul) in randul de stare, cu litere mai mici. DAB+ cu „(în lucru)” in data/menu.xml:
#             fara promisiunea sunetului, tasta verde „Pornește”.
# Numai sagetile si OK ajung la orice; tastele colorate sunt scurtaturi. ALBASTRU la sfarsit = „Text brut"
# (raspunsul detectorului si ce n-a mers la citirea listelor), ca la celelalte ecrane de informatii.
#
# Skinul: fereastra scanerului de satelit (skinName „ScanerSatelit" din skinul HDSatelit: cadrul, lista pe doua
# coloane, previzualizarea, starea, tastele). Pe alte skinuri, skin_rezerva din Screens/ScanerCablu.py, cu aceleasi
# cote.
#
# Interfata web (Plugins/Extensions/HdsWebControl/scanare_web.py) deschide acelasi ecran pe televizor, cu
# cautarea pornita, si citeste stare_web(); butoanele ei cheama asculta() si inapoi() de aici, deci televizorul si
# pagina arata mereu acelasi lucru.

from __future__ import absolute_import, unicode_literals

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText

import Screens.ScanerSatelit as S

RAND_INFO = '_info'
RAND_PORNESTE = '_porneste'
RAND_RENUNTA = '_renunta'
RAND_OPRESTE = '_opreste'
RAND_INAPOI = '_inapoi'
RAND_DIN_NOU = '_din_nou'
PREFIX_POST = 'post:'
PREFIX_GRUP = 'grup:'      # capul unei grupe (ansamblu DAB+, multiplex DVB-T2) la sfarsit: cursorul sare peste el

# fetele ferestrei
INAINTE, IN_CURS, SFARSIT, INCHIS = 'inainte', 'in_curs', 'sfarsit', 'inchis'

# fazele cautarii (ScanerSatelit.CautareFluxuri) dupa care fereastra trece la fata „sfarsit"
TERMINATE = ('gata', 'nimic', 'esuat', 'ales', 'oprit')

# pasul scurt din randul „Pasul", dupa faza cautarii
PASI = {'nepornit': 'acord', 'acord': 'acord', 'detector': 'detector', 'salvare': 'salvare', 'invatare': 'invatare'}


class HdsScanareFluxuri(Screen):
    """Scanarea DAB+ / DVB-T2 prin satelit. rez = ScanerSatelit.pregateste('dab' / 'dvbt2', ...). pornita=True (din
    web, dupa confirmarea din pagina): cautarea porneste la deschidere, fara fata „inainte". Se inchide cu
    (alegere, text): alegere = 'asculta', 'inapoi', 'oprit' sau 'renuntat'."""

    COTE = dict(S.ScanerSatelit.COTE)

    def __init__(self, session, rez, pornita=False):
        Screen.__init__(self, session)
        from Screens.ScanerCablu import skin_rezerva, culoare_valoare, fonturi_texte
        import Screens.ScanerCablu as SC
        self.skinName = ['HdsScanareFluxuri', 'ScanerSatelit']
        self.skin = skin_rezerva('HdsScanareFluxuri', self.COTE)
        self._fonturi = fonturi_texte('ScanerSatelit')
        self._culoare = culoare_valoare()
        c = getattr(SC, '_culoare_skin', lambda nume: None)('hdsAmber')    # capetele grupelor la sfarsit
        self._culoare_grup = 0xF5B83D if c is None else c
        self.rez = rez
        self.dab = rez.get('profil') == 'dab'
        self.felul = 'DAB+' if self.dab else 'DVB-T2'
        # DAB+ cu „(în lucru)” in data/menu.xml: posturile se salveaza, dar sunetul lor nu merge inca pe receptor, deci
        # fata de sfarsit nu promite ascultarea (S.text_in_lucru citeste menu.xml o data, tinut in memorie dupa data)
        self.fara_sunet = False
        if self.dab:
            try:
                self.fara_sunet = bool(S.text_in_lucru('dab'))
            except Exception as e:
                print('[HdsScanareFluxuri] starea DAB+ din meniu: %s' % e)
        self.plan = S.plan_fluxuri(rez, session)
        self.cautare = None
        self.fata = INAINTE
        self._pornita = pornita
        self._intrari = []
        self._ceas = None
        self._legatura_ceas = None
        self.rezultat = None

        self['lista'] = List([], enableWrapAround=True)
        self['preview'] = Label('')
        self['stare'] = Label('')
        self['key_red'] = StaticText('')
        self['key_green'] = StaticText('')
        self['key_yellow'] = StaticText('')
        self['key_blue'] = StaticText('')
        actiuni = {
            'ok': self.ok,
            'cancel': self.iesire,
            'red': self.rosu,
            'green': self.verde,
            'yellow': lambda: None,
            'blue': self.albastru,
            'up': self._sus,
            'down': self._jos,
            'left': self._pagina_sus,
            'right': self._pagina_jos,
            'upRepeated': self._sus,
            'downRepeated': self._jos,
            'leftRepeated': self._pagina_sus,
            'rightRepeated': self._pagina_jos,
        }
        # ridicarea tastelor (keymap.xml, DirectionActions) fara efect, ca jurnalul sa nu scrie „unknown action"
        actiuni.update((nume, lambda: None) for nume in ('upUp', 'downUp', 'leftUp', 'rightUp'))
        self['actiuni'] = ActionMap(['ColorActions', 'OkCancelActions', 'DirectionActions'], actiuni, -1)
        self.onClose.append(self._la_inchidere)
        self.onLayoutFinish.append(self._dupa_asezare)
        self._arata()

    # ---- fetele ferestrei
    def _dupa_asezare(self):
        # cursorul se pune abia acum: inainte de asezare lista nu are inca widget (List.setIndex nu face nimic)
        self._arata()
        if self._pornita:
            self._pornita = False
            self.porneste()

    def _potriveste(self):
        from Screens.ScanerCablu import potriveste_textul
        for nume in ('preview', 'stare'):
            potriveste_textul(self[nume], *self._fonturi[nume])

    def _titlu(self):
        if self.fata == INAINTE:
            return _('%s: înainte de scanare') % self.felul
        if self.fata == IN_CURS:
            return _('%s: scanare în curs') % self.felul
        c = self.cautare
        if c is not None and c.faza == 'esuat':
            return _('%s: scanarea nu a mers') % self.felul
        if c is not None and c.posturi():
            return _('%s: posturi găsite') % self.felul if self.dab else _('%s: programe găsite') % self.felul
        return _('%s: nimic găsit') % self.felul

    def _text_inapoi(self):
        c = self.cautare
        are_canal = c.ref_inainte is not None if c is not None else self.plan.get('are_canal')
        return _('Înapoi la canalul meu') if are_canal else _('Închide')

    def _rand(self, eticheta, cheie, valoare=''):
        # eticheta si valoarea intregi: un rand care nu incape deruleaza (lib/gui/elabel.h)
        from Screens.ScanerCablu import valoare_scurta
        return (eticheta, cheie, valoare_scurta(valoare, self.COTE) if valoare else '', self._culoare)

    def _randuri(self):
        """(randurile listei, cheia randului pe care sta cursorul)."""
        c = self.cautare
        if self.fata == INAINTE:
            randuri = [self._rand(e, RAND_INFO, v) for e, v in self.plan['randuri']]
            randuri += [self._rand(_('Pornește scanarea'), RAND_PORNESTE), self._rand(_('Renunță'), RAND_RENUNTA)]
            return randuri, RAND_PORNESTE
        if self.fata == IN_CURS:
            randuri = [self._rand(_('Satelitul'), RAND_INFO, c.satelit),
                       self._rand(_('Pasul'), RAND_INFO, self._pas())]
            for g in c.gasite:
                randuri.append(self._rand(g['nume'], RAND_INFO, self._text_grupa(g)))
            randuri.append(self._rand(_('Oprește scanarea'), RAND_OPRESTE))
            return randuri, RAND_OPRESTE
        randuri = []
        # pe grupe, in ordinea din posturi(): capul grupei, apoi posturile ei; numarul postului e cel din posturi()
        i = 0
        for gi, g in enumerate(c.gasite):
            lista = g.get('posturi') or []
            if not lista:
                continue
            randuri.append(self._rand_grup(gi, g))
            for p in lista:
                randuri.append(self._rand(p['nume'], '%s%d' % (PREFIX_POST, i), self._valoare_post(p)))
                i += 1
        prima = '%s0' % PREFIX_POST if i else RAND_INAPOI
        if not randuri:
            if c.faza == 'esuat':
                # ce a vazut detectorul inainte sa se opreasca ramane pe ecran (ca in timpul scanarii si ca in web);
                # fraza de deasupra spune ca nu s-a salvat nimic
                for g in c.gasite:
                    randuri.append(self._rand(g['nume'], RAND_INFO, self._text_grupa(g)))
            randuri.append(self._rand(_('Caută din nou'), RAND_DIN_NOU))
            prima = RAND_DIN_NOU
        randuri.append(self._rand(self._text_inapoi(), RAND_INAPOI,
                                  c.rezumat()['pozitie_inainte'] if c.ref_inainte is not None else ''))
        return randuri, prima

    def _rand_grup(self, gi, g):
        """Capul grupei la sfarsit: numele ansamblului (multiplexului) si cate posturi are, in alta culoare."""
        from Screens.ScanerCablu import valoare_scurta
        return (g['nume'], '%s%d' % (PREFIX_GRUP, gi), valoare_scurta(self._text_grupa(g), self.COTE), self._culoare_grup)

    def _valoare_post(self, p):
        """Valoarea randului unui post la sfarsit: ce face OK pe el (DAB+: „Ascultă”, sau „Pornește” cat ascultarea e
        „(în lucru)”); la DVB-T2 felul programului (TV, Radio)."""
        if self.dab:
            return _('Pornește') if self.fara_sunet else _('Ascultă')
        return p.get('fel') or self.felul

    def _pas(self):
        c = self.cautare
        pas = PASI.get(c.faza, '')
        if pas == 'acord':
            return _('acord și rotirea antenei')
        if pas == 'detector':
            return _('caut ansamblurile DAB+') if self.dab else _('caut multiplexurile DVB-T2')
        if pas == 'salvare':
            return _('salvez ce am găsit')
        if pas == 'invatare':
            return _('citesc lista posturilor') if self.dab else _('citesc lista programelor')
        return ''

    def _text_grupa(self, g):
        if g.get('stare') == 'invat':
            return _('citesc lista...')
        n = len(g.get('posturi') or []) or g.get('numar') or 0
        if self.dab:
            return S.ngettext('%d post', '%d posturi', n) % n
        return S.ngettext('%d program', '%d programe', n) % n

    def _preview(self):
        if self.fata == INAINTE:
            return self.plan['text']
        c = self.cautare
        text = c.text
        if self.fata == SFARSIT and c.posturi():
            if self.fara_sunet:
                text += ' ' + _('Ascultarea lor nu merge încă pe acest receptor (în lucru).')
            else:
                text += ' ' + (_('Apasă OK pe un post ca să-l asculți; antena rămâne pe %s.') if self.dab else
                               _('Apasă OK pe un program ca să-l vezi; antena rămâne pe %s.')) % c.rezumat()['pozitie']
        return text

    def _stare(self):
        if self.fata == INAINTE:
            return _('Alege cu săgețile și apasă OK.')
        c = self.cautare
        if self.fata == IN_CURS:
            secunde = c.rezumat()['secunde']
            return _('Au trecut %s. Ca să oprești, apasă OK pe „Oprește scanarea”.') % S.text_scurs(secunde)
        if c.faza == 'esuat' and getattr(c, 'detaliu', ''):
            # detaliul tehnic, cu litere mai mici decat fraza simpla de deasupra (randul de stare)
            return '%s %s' % (c.detaliu, _('ALBASTRU: textul brut al scanării.'))
        if c.faza == 'esuat' or not c.posturi():
            if c.ref_inainte is not None:
                return _('Poți căuta din nou sau te poți întoarce la canalul tău.')
            return _('Poți căuta din nou sau poți închide fereastra.')
        return _('ALBASTRU: textul brut al scanării.')

    def _taste(self):
        c = self.cautare
        if self.fata == INAINTE:
            return _('Renunță'), _('Pornește'), ''
        if self.fata == IN_CURS:
            return _('Oprește'), '', ''
        verde = (_('Ascultă') if self.dab and not self.fara_sunet else _('Pornește')) if c.posturi() else \
            _('Caută din nou')
        return self._text_inapoi(), verde, _('Text brut')

    def _arata(self):
        """Fata curenta, din starea cautarii: titlul, randurile (cursorul ramane pe acelasi rand cand se poate),
        previzualizarea, starea, tastele."""
        if self.fata == INCHIS:
            return
        if self.cautare is not None and self.fata == IN_CURS and self.cautare.faza in TERMINATE:
            self.fata = SFARSIT
            self._opreste_ceasul()
        curent = self['lista'].getCurrent()
        cheie_curenta = curent[1] if curent else None
        self._intrari, prima = self._randuri()
        self['lista'].setList(self._intrari)
        chei = [r[1] for r in self._intrari]
        tinta = cheie_curenta if (cheie_curenta in chei and cheie_curenta != RAND_INFO
                                  and not cheie_curenta.startswith(PREFIX_GRUP)) else prima
        if tinta in chei:
            self['lista'].setIndex(chei.index(tinta))
        self.setTitle(self._titlu())
        self['preview'].setText(self._preview())
        self['stare'].setText(self._stare())
        rosu, verde, albastru = self._taste()
        self['key_red'].setText(rosu)
        self['key_green'].setText(verde)
        self['key_blue'].setText(albastru)
        self._potriveste()

    # ---- ceasul care arata cat a trecut (o data pe secunda, numai randul de stare)
    def _porneste_ceasul(self):
        try:
            from enigma import eTimer
            if self._ceas is None:
                self._ceas = eTimer()
                try:
                    self._ceas.callback.append(self._tic)
                except AttributeError:
                    self._legatura_ceas = self._ceas.timeout.connect(self._tic)
            self._ceas.start(1000, False)
        except Exception as e:
            print('[HdsScanareFluxuri] ceasul: %s' % e)

    def _opreste_ceasul(self):
        if self._ceas is not None:
            try:
                self._ceas.stop()
            except Exception:
                pass

    def _tic(self):
        if self.fata == IN_CURS and self.cautare is not None:
            self['stare'].setText(self._stare())

    # ---- actiunile
    def porneste(self, ref_inainte=None, pozitie_inainte=None):
        """Cautarea: fata „in curs"; ecranul se reface la fiecare schimbare a cautarii."""
        tp = self.rez['hdscomun']
        self.cautare = S.CautareFluxuri(self.session, self.rez['profil'], tp, ref_inainte=ref_inainte,
                                        pozitie_inainte=pozitie_inainte)
        self.cautare.ascultatori.append(self._schimbare)
        self.fata = IN_CURS
        self._arata()
        self._porneste_ceasul()
        try:
            self.cautare.porneste()
        except Exception as e:
            print('[HdsScanareFluxuri] pornirea cautarii: %s' % e)
            # fraza simpla; motivul spus simplu dedesubt, textul tehnic numai in jurnal si la textul brut
            self.cautare.detaliu = S.motiv_eroare(e)
            self.cautare.note.append('%s' % (e,))
            self.cautare._termina('esuat', _('Scanarea nu a putut porni. Încearcă din nou.'))

    def _schimbare(self):
        try:
            self._arata()
        except Exception as e:
            print('[HdsScanareFluxuri] reafisarea: %s' % e)

    def ok(self):
        curent = self['lista'].getCurrent()
        if not curent:
            return
        cheie = curent[1]
        if cheie == RAND_PORNESTE:
            self.porneste()
        elif cheie == RAND_RENUNTA:
            self._inchide('renuntat', '')
        elif cheie == RAND_OPRESTE:
            self.opreste()
        elif cheie == RAND_INAPOI:
            self.inapoi()
        elif cheie == RAND_DIN_NOU:
            self.din_nou()
        elif cheie.startswith(PREFIX_POST):
            self.asculta(int(cheie[len(PREFIX_POST):]))
        elif cheie.startswith(PREFIX_GRUP):
            self._jos()                      # OK pe capul grupei: primul ei post

    def rosu(self):
        if self.fata == INAINTE:
            self._inchide('renuntat', '')
        elif self.fata == IN_CURS:
            self.opreste()
        elif self.fata == SFARSIT:
            self.inapoi()

    def verde(self):
        if self.fata == INAINTE:
            self.porneste()
        elif self.fata == SFARSIT:
            curent = self['lista'].getCurrent()
            if self.cautare.posturi():
                if curent and curent[1].startswith(PREFIX_POST):
                    self.asculta(int(curent[1][len(PREFIX_POST):]))
                else:
                    self.asculta(0)
            else:
                self.din_nou()

    def albastru(self):
        if self.fata != SFARSIT or self.cautare is None:
            return
        from Screens.TextBox import TextBox
        dlg = self.session.open(TextBox, self.cautare.text_brut())
        try:
            dlg.setTitle(_('%s: text brut') % self.felul)
        except Exception:
            pass

    def iesire(self):
        """EXIT: inainte = Renunță, in curs = Oprește, la sfarsit = aceeasi alegere ca tasta rosie (scrisa pe ea)."""
        self.rosu()

    def opreste(self):
        if self.cautare is not None:
            self.cautare.opreste()
            self._inchide('oprit', self.cautare.text)
        else:
            self._inchide('renuntat', '')

    def inapoi(self):
        c = self.cautare
        if c is None:
            self._inchide('renuntat', '')
            return
        c.inapoi()
        self._inchide('inapoi', c.text)

    def asculta(self, index):
        """-> (True, None) sau (False, motivul); la reusita fereastra se inchide."""
        if self.cautare is None or self.fata != SFARSIT:
            return False, _('Scanarea nu s-a terminat.')
        ok, motiv = self.cautare.asculta(index)
        if ok:
            self._inchide('asculta', self.cautare.text)
        else:
            self['stare'].setText(motiv or '')
        return ok, motiv

    def din_nou(self):
        """Aceeasi scanare inca o data; canalul de dinainte ramane cel tinut minte la prima pornire."""
        vechi = self.cautare
        ref, poz = None, None
        if vechi is not None:
            ref, poz = vechi.ref_inainte, vechi.pozitie_inainte
            vechi.ales = 'reluat'
            vechi.ref_inainte = None
            vechi._elibereaza_tunerul()      # tunerul tinut la sfarsit trece la cautarea noua
            if self._schimbare in vechi.ascultatori:
                vechi.ascultatori.remove(self._schimbare)
        self.porneste(ref_inainte=ref, pozitie_inainte=poz)

    def _inchide(self, alegere, text):
        if self.fata == INCHIS:
            return
        self.rezultat = (alegere, text)
        self.fata = INCHIS
        self._opreste_ceasul()
        self.close(self.rezultat)

    def _la_inchidere(self):
        self._opreste_ceasul()
        c = self.cautare
        if c is not None:
            if self._schimbare in c.ascultatori:
                c.ascultatori.remove(self._schimbare)
            if c.ales is None:
                c.opreste()          # inchisa din alta parte inainte de alegere: canalul de dinainte porneste

    # ---- navigarea
    def _pe_cap(self):
        curent = self['lista'].getCurrent()
        return bool(curent) and str(curent[1]).startswith(PREFIX_GRUP)

    def _peste_capete(self, pas, inapoi):
        """La sfarsit cursorul nu sta pe capul unei grupe: inca un pas in aceeasi directie; la marginea listei (fara
        invartire, sus pe primul cap) un pas inapoi, pe primul post."""
        if self.fata != SFARSIT:
            return
        for _i in range(len(self._intrari)):
            if not self._pe_cap():
                return
            pas()
        if self._pe_cap():
            inapoi()

    def _sus(self):
        lista = self['lista']
        lista.selectPrevious()
        self._peste_capete(lista.selectPrevious, lista.selectNext)

    def _jos(self):
        lista = self['lista']
        lista.selectNext()
        self._peste_capete(lista.selectNext, lista.selectPrevious)

    def _pagina_sus(self):
        lista = self['lista']
        for _i in range(5):
            lista.selectPrevious()
        self._peste_capete(lista.selectPrevious, lista.selectNext)

    def _pagina_jos(self):
        lista = self['lista']
        for _i in range(5):
            lista.selectNext()
        self._peste_capete(lista.selectNext, lista.selectPrevious)

    # ---- pentru interfata web (aceeasi stare ca pe televizor)
    def stare_web(self):
        st = {'fata': self.fata, 'titlu': self._titlu(), 'plan': {'randuri': [list(r) for r in self.plan['randuri']],
                                                                'text': self.plan['text']}}
        if self.cautare is not None:
            st.update(self.cautare.rezumat())
            st['text_inapoi'] = self._text_inapoi()
        # DAB+ „(în lucru)”: butonul postului din pagina spune „Pornește”, nu „Ascultă”, ca tasta verde
        st['fara_sunet'] = self.fara_sunet
        st['preview'] = self._preview() if self.fata != INCHIS else ''
        return st

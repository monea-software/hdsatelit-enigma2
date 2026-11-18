# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""ScanerMaiMultiSateliti.py: felul 3 al scanarii de satelit, „Mai multi sateliti".

E mecanismul multisatelit din Screens/ScanSetup.py (o bifa pe fiecare satelit al antenei, apoi toate
transponderele lor din satellites.xml, cu cautare in retea), stins acolo prin permiteMultisat = False. Ecranul de
aici il aprinde, fara nicio linie scrisa in ScanSetup.py:
  - permiteMultisat = True si tipul pus direct pe multisatelit: nu mai apare „Un singur transponder" sau
    „Un satelit", care au felurile lor in lista Satelit;
  - in randul „Tuner" raman numai tunerele de satelit (altfel alegerea tunerului de cablu sau terestru ar fi
    transformat ecranul intr-o a doua cale spre scanarea de cablu);
  - "toti bifati" si lista bifelor vin din ScanerSatelit.sateliti_de_bifat (Gpiupiu, forum 801 #2502): cu motorul
    DiSEqC 1.2 cu pozitii salvate (sau USALS pe satelit) lista are numai pozitiile puse in Setari tuner si se ofera;
    cu motorul peste tot satellites.xml (206) se ofera numai cu locul antenei stabilit: lista are satelitii deasupra
    orizontului, iar "toti bifati" bifeaza numai pe cei care au deja canale in lista (ScanerSatelit.sateliti_si_bife,
    hotararea DSP 14.11 20:49; createSetup de aici pune bifele, ScanSetup le-ar bifa pe toate); fara loc nu se ofera (o
    pornire ar plimba antena si pe pozitii pe care nu le vede). Satelitii ascunsi ies din lista prin Satexists,
    singurul loc unde il cheama ScanSetup (bucla bifelor din createSetup);
  - nu porneste spre un satelit spre care antena nu se roteste (motorul USALS cu locul nestabilit sau satelitul sub
    orizont, ScanerSatelit.refuz_pozitii): fereastra spune de ce, iar la locul nestabilit OK deschide alegerea locului
    (asistenta 289712: altfel o scanare de 1 h 40 min numai cu "fara semnal");
  - cu motor, cautarea merge pe rand: cate o trecere pe satelit (ScanerSatelit.treceri_pe_satelit), deci antena
    termina un satelit inainte sa se roteasca spre urmatorul;
  - inainte de pornire, fiecare transponder trece prin motiv_refuz (Screens/ScanerSatelit.py), aceeasi poarta ca
    la celelalte feluri: getInitialTransponderList din ScanSetup nu filtreaza nimic, iar un DVB-S2 cu FEC Auto
    sau o rata sub limita driverului („symbol rate 990000 out of range" in dmesg) ar fi fost aruncat tacut de
    nucleu;
  - tastele au aceleasi nume ca in celelalte scanere („Înapoi”, „Caută acum”), puse dupa ScanSetup.__init__.
"""
from Screens.ScanSetup import ScanSetup
from Screens.MessageBox import MessageBox
from Screens.ScanerSatelit import motiv_refuz, sateliti_si_bife, roteste, treceri_pe_satelit, refuz_pozitii
from Components.config import ConfigSelection
from Components.NimManager import nimmanager

# campurile lui eDVBFrontendParametersSatellite pe care le citeste motiv_refuz
CAMPURI_TP = ('frequency', 'symbol_rate', 'polarisation', 'fec', 'inversion', 'orbital_position', 'system',
              'modulation', 'rolloff', 'pilot')


def din_parametri(parm):
    """eDVBFrontendParametersSatellite -> dict cu aceleasi nume (ce primeste motiv_refuz)."""
    return dict((c, getattr(parm, c, 0)) for c in CAMPURI_TP)


def filtreaza(tlist):
    """(bune, sarite): sarite = [(parametri, motiv)], cele pe care nucleul nu le-ar primi."""
    bune, sarite = [], []
    for parm in tlist:
        motiv = motiv_refuz(din_parametri(parm))
        if motiv:
            sarite.append((parm, motiv))
        else:
            bune.append(parm)
    return bune, sarite


def tunere_satelit():
    """[(slot ca text, descriere)]: tunerele de satelit folosibile, dupa aceleasi reguli ca ScanSetup.createConfig
    (fara cele puse pe "nimic", fara cele avansate fara sateliti, fara cele legate de un tuner de acelasi fel). 0.7.7
    (SCN): regulile stau in ScanerSatelit.sloturi_satelit, ca randul "Tuner" din pagina web sa aiba aceleasi tunere."""
    from Screens.ScanerSatelit import sloturi_satelit, tunere_alegere
    return tunere_alegere(nimmanager, sloturi_satelit(nimmanager))


def are_motor(slot):
    try:
        return bool(nimmanager.getRotorSatListForNim(int(slot)))
    except Exception:
        return False


class ScanerMaiMultiSateliti(ScanSetup):
    permiteMultisat = True
    hdsFel = 'satelit/mai_multi'    # felul scanarii in /api/scanare-ultima (ScanSetup.startScan il pune in lista)

    def __init__(self, session):
        ScanSetup.__init__(self, session)
        # fara ecran propriu in piele: se ia cel al lui ScanSetup (acelasi tipar ca DefaultSatLists)
        self.skinName = ['ScanerMaiMultiSateliti', 'ScanSetup']
        self.setTitle(_('Mai mulți sateliți'))
        for tasta, text in (('key_red', _('Înapoi')), ('key_green', _('Caută acum'))):
            try:
                self[tasta].setText(text)
            except (KeyError, AttributeError):
                pass
        try:
            if self.scan_nims.value == '':
                text = _('Niciun tuner de satelit configurat. Configurează antena în „Setări tuner”.')
            elif self._roteste(self.scan_nims.value):
                text = _('Bifează sateliții de căutat cu stânga sau dreapta, apoi apasă OK. Antena se rotește pe '
                         'rând spre fiecare satelit bifat.')
                pozitii, bife = self._de_bifat(self.scan_nims.value)
                if bife and len(bife) < len(pozitii):
                    text += ' ' + _('Bifați din oficiu: numai sateliții care au deja canale în listă (%d din %d); '
                                    'pe ceilalți îi poți bifa tu.') % (len(bife), len(pozitii))
            else:
                text = _('Bifează sateliții de căutat cu stânga sau dreapta, apoi apasă OK.')
            self['introduction'].setText(text)
        except Exception:
            pass

    @staticmethod
    def _roteste(slot):
        try:
            return roteste(nimmanager, int(slot))
        except (ValueError, TypeError):
            return False

    def _de_bifat(self, slot):
        """(pozitiile din lista bifelor, pozitiile bifate de "toti bifati") pentru tunerul slot, tinute minte cat sta
        ecranul deschis; a doua multime goala = "toti bifati" nu se ofera."""
        slot = str(slot)
        if slot not in self._bife:
            sateliti, bife = sateliti_si_bife(nimmanager, int(slot))
            self._bife[slot] = (set(p for p, _n in sateliti), set(bife))
        return self._bife[slot]

    def createSetup(self):
        """ScanSetup.createSetup bifeaza la "toti bifati" fiecare satelit din lista; aici raman bifati numai cei din
        sateliti_si_bife (la motorul USALS peste tot: cei care au deja canale), ceilalti raman de bifat de om."""
        ScanSetup.createSetup(self)
        try:
            if not self.scan_type.value.endswith('_yes'):
                return
            _pozitii, bife = self._de_bifat(self.scan_nims.value)
        except (AttributeError, ValueError, TypeError):
            return
        schimbat = False
        for pozitie, bifa in getattr(self, 'multiscanlist', []):
            da = pozitie in bife
            if bool(bifa.value) != da:
                bifa.value = da
                schimbat = True
        if schimbat:
            try:
                self['config'].l.setList(self.list)
            except (KeyError, AttributeError, TypeError):
                pass

    def Satexists(self, tlist, pos):
        """ScanSetup.createSetup pune un satelit in lista bifelor numai cand Satexists da 0: aici se ascund si
        pozitiile pe care sateliti_de_bifat nu le da (sub orizont, oprite de locul nestabilit)."""
        if ScanSetup.Satexists(self, tlist, pos):
            return 1
        try:
            pozitii, _permis = self._de_bifat(self.scan_nims.value)
        except (ValueError, TypeError):
            return 0
        return 0 if pos in pozitii else 1

    def createConfig(self, frontendData):
        self._bife = {}     # inaintea lui ScanSetup.createConfig: Satexists il foloseste oricand e chemat
        rez = ScanSetup.createConfig(self, frontendData)
        tunere = tunere_satelit()
        self.scan_nims = ConfigSelection(choices=tunere)
        alegeri = [('multisat', _('Bifez eu sateliții'))]
        # "toti bifati" numai cand se poate pe fiecare tuner (alegerea e una singura pentru ecran)
        if tunere and all(self._de_bifat(slot)[1] for slot, _d in tunere):
            if any(self._roteste(slot) for slot, _d in tunere):
                alegeri.append(('multisat_yes', _('Toți sateliții motorului, bifați, pe rând')))
            else:
                alegeri.append(('multisat_yes', _('Toți sateliții antenei, bifați')))
        self.scan_type = ConfigSelection(default='multisat', choices=alegeri)
        return rez

    def startScan(self, tlist, flags, feid):
        if not tlist:
            self.session.open(MessageBox, _('Nu e bifat niciun satelit. Bifează cu stânga sau dreapta sateliții de '
                                            'căutat, apoi apasă OK.'), MessageBox.TYPE_ERROR)
            return
        pozitie, refuz = refuz_pozitii(getattr(parm, 'orbital_position', None) for parm in tlist)
        if refuz:
            self._refuza(refuz)
            return
        bune, sarite = filtreaza(tlist)
        if not bune:
            text = _('Sateliții bifați au %d transpondere în lista receptorului, dar niciunul cu parametri pe care '
                     'tunerul îi primește (%s).') % (len(tlist), sarite[0][1])
            self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)
            return
        if self._roteste(feid):
            lista = treceri_pe_satelit(bune, feid, flags, self.hdsFel)
            if len(lista) > 1:
                print('[ScanerMaiMultiSateliti] cu motor: %d treceri, cate una pe satelit' % len(lista))
                self._porneste_treceri(lista, sarite)
                return
        self._noteaza_sarite(sarite)
        ScanSetup.startScan(self, bune, flags, feid)

    def _refuza(self, text):
        """Fereastra cu motivul; la locul antenei nestabilit, OK deschide direct alegerea locului (regula 1f)."""
        try:
            from Components import HdsLocul
            fara_loc = not HdsLocul.stabilit()
        except Exception:
            fara_loc = False
        if fara_loc:
            self.session.openWithCallback(self._alegeLocul, MessageBox, text, MessageBox.TYPE_INFO)
        else:
            self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)

    def _alegeLocul(self, rezultat=True):
        if rezultat is False:
            return      # EXIT pe fereastra: omul nu vrea acum alegerea locului
        try:
            from Screens.HdsLocul import deschide
            deschide(self.session, self._locAles)
        except Exception as e:
            print('[ScanerMaiMultiSateliti] alegerea locului: %s' % e)

    def _locAles(self, schimbat):
        if schimbat:
            # lista bifelor depinde de loc (orizontul, satelitii USALS opriti): se socoteste din nou
            self._bife = {}
            self.createSetup()

    def _porneste_treceri(self, lista, sarite):
        """Ca ScanSetup.startScan, cu lista de treceri gata facuta."""
        self._noteaza_sarite(sarite)
        from Screens.ServiceScan import ServiceScan
        if self.finished_cb:
            self.session.openWithCallback(self.finished_cb, ServiceScan, lista)
        else:
            self.session.open(ServiceScan, lista)

    @staticmethod
    def _noteaza_sarite(sarite):
        if sarite:
            # motivul e un text tradus (cu ș, ț); ascii() il scrie cu coduri, ca randul de jurnal sa nu poata opri
            # pornirea cautarii pe o consola fara UTF-8 (UnicodeEncodeError)
            print('[ScanerMaiMultiSateliti] sarite %d transpondere pe care nucleul nu le primeste, primul: %s'
                  % (len(sarite), ascii(sarite[0][1])))

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
  - cu motor NU se ofera „toti bifati": lista motorului are toti satelitii din satellites.xml (206), iar o
    singura pornire pe toti ar plimba antena si pe pozitii pe care nu le vede (motivul pentru care mecanismul
    fusese stins);
  - inainte de pornire, fiecare transponder trece prin motiv_refuz (Screens/ScanerSatelit.py), aceeasi poarta ca
    la celelalte feluri: getInitialTransponderList din ScanSetup nu filtreaza nimic, iar un DVB-S2 cu FEC Auto
    sau o rata sub limita driverului („symbol rate 990000 out of range" in dmesg) ar fi fost aruncat tacut de
    nucleu;
  - tastele au aceleasi nume ca in celelalte scanere („Înapoi”, „Caută acum”), puse dupa ScanSetup.__init__.
"""
from Screens.ScanSetup import ScanSetup
from Screens.MessageBox import MessageBox
from Screens.ScanerSatelit import motiv_refuz
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
    (fara cele puse pe „nimic”, fara cele avansate fara sateliti, fara cele legate de un tuner de acelasi fel)."""
    rez = []
    for n in nimmanager.nim_slots:
        if not n.isCompatible('DVB-S'):
            continue
        if n.config_mode == 'nothing':
            continue
        if n.config_mode == 'advanced' and len(nimmanager.getSatListForNim(n.slot)) < 1:
            continue
        if n.config_mode in ('loopthrough', 'satposdepends'):
            radacina = nimmanager.sec.getRoot(n.slot_id, int(n.config.connectedTo.value))
            if n.type == nimmanager.nim_slots[radacina].type:
                continue
        rez.append((str(n.slot), n.friendly_full_description))
    return rez


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
            self['introduction'].setText(_('Bifează sateliții de căutat cu stânga sau dreapta, apoi apasă OK.')
                                         if self.scan_nims.value != '' else
                                         _('Niciun tuner de satelit configurat. Configurează antena în „Setări '
                                           'tuner”.'))
        except Exception:
            pass

    def createConfig(self, frontendData):
        rez = ScanSetup.createConfig(self, frontendData)
        self.scan_nims = ConfigSelection(choices=tunere_satelit())
        cu_motor = any(are_motor(slot) for slot, _d in tunere_satelit())
        alegeri = [('multisat', _('Bifez eu sateliții'))]
        if not cu_motor:
            alegeri.append(('multisat_yes', _('Toți sateliții antenei, bifați')))
        self.scan_type = ConfigSelection(default='multisat', choices=alegeri)
        return rez

    def startScan(self, tlist, flags, feid):
        if not tlist:
            self.session.open(MessageBox, _('Nu e bifat niciun satelit. Bifează cu stânga sau dreapta sateliții de '
                                            'căutat, apoi apasă OK.'), MessageBox.TYPE_ERROR)
            return
        bune, sarite = filtreaza(tlist)
        if not bune:
            text = _('Sateliții bifați au %d transpondere în lista receptorului, dar niciunul cu parametri pe care '
                     'tunerul îi primește (%s).') % (len(tlist), sarite[0][1])
            self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)
            return
        if sarite:
            # motivul e un text tradus (cu ș, ț); ascii() il scrie cu coduri, ca randul de jurnal sa nu poata opri
            # pornirea cautarii pe o consola fara UTF-8 (UnicodeEncodeError)
            print('[ScanerMaiMultiSateliti] sarite %d transpondere pe care nucleul nu le primeste, primul: %s'
                  % (len(sarite), ascii(sarite[0][1])))
        ScanSetup.startScan(self, bune, flags, feid)

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsDvbMABR.py — Ecran configurare DVB-MABR (IP Multicast ABR) in imaginea HDSatelit.

Scris de la zero.
Accesat din meniu: Settings → Internet Sources → DVB-MABR (IP Multicast).
"""
from __future__ import absolute_import, unicode_literals
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Button import Button

# Citirea si scrierea /etc/enigma2/hdsmabr.conf, verificarea unui grup nou si cautarea SAP stau in
# Components/HdsMabrSetari.py, aceleasi pentru acest ecran si pentru pagina web /mabr (HdsWebControl/internet_web.py).
from Components import HdsMabrSetari as S

CALE_CONFIG_MABR = S.CALE_CONFIG


def _citeste_config_mabr():
    return S.citeste()


def _scrie_config_mabr(config):
    S.scrie(config)


class HdsDvbMABRSetup(Screen):
    """Configurare DVB-MABR: grupuri multicast manuale + autodiscover SAP."""

    skin = """
        <screen name="HdsDvbMABRSetup" resolution="1920,1080" position="center,center" size="800,540" title="DVB-MABR: IP Multicast">
            <widget name="stare"          position="10,5"   size="780,30"  font="Regular;17" halign="left" />
            <widget name="lista"          position="10,40"  size="780,360" scrollbarMode="showOnDemand" />
            <widget name="sesiuni_label"  position="10,410" size="780,20"  font="Regular;15" foregroundColor="#aaaaaa" />
            <widget name="sesiuni"        position="10,432" size="780,50"  font="Regular;16" halign="left" />
            <widget name="buton_rosu"     position="10,495"  size="185,40" backgroundColor="#9f1313" font="Regular;16" halign="center" valign="center" />
            <widget name="buton_verde"    position="210,495" size="185,40" backgroundColor="#1f771f" font="Regular;16" halign="center" valign="center" />
            <widget name="buton_galben"   position="410,495" size="185,40" backgroundColor="#a08020" font="Regular;16" halign="center" valign="center" />
            <widget name="buton_albastru" position="610,495" size="180,40" backgroundColor="#18188b" font="Regular;16" halign="center" valign="center" />
        </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self._config     = _citeste_config_mabr()
        self._sesiuni_live = []   # descoperite prin SAP
        self._construieste_lista()

        self['stare']          = Label(self._text_stare())
        self['lista']          = MenuList(self._intrari)
        self['sesiuni_label']  = Label(_('Sesiuni descoperite live (SAP):'))
        self['sesiuni']        = Label(_('Apasă Caută pentru a descoperi sesiuni MABR în rețea.'))
        self['buton_rosu']     = Button(_('Înapoi'))
        self['buton_verde']    = Button(_('Salvează'))
        self['buton_galben']   = Button(_('Schimbă'))
        self['buton_albastru'] = Button(_('Caută SAP'))

        self['tastatura'] = ActionMap(
            ['ColorActions', 'OkCancelActions', 'DirectionActions'],
            {
                'red':    self.inchide,
                'green':  self.salveaza,
                'yellow': self.toggle_selectat,
                'blue':   self.cauta_sap,
                'ok':     self.toggle_selectat,
                'cancel': self.inchide,
            }, -1)
        self.setTitle(_('DVB-MABR: Configurare IP Multicast'))
        getattr(self, "onLayoutFinish", []).append(self._textMarit)

    def _textMarit(self):
        """Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): eticheta sesiunilor (caseta de 20 px)
        creste cat randul fontului, iar lista sesiunilor coboara (de la 110 % i se taiau cozile literelor). La 100 % nu se
        schimba nimic."""
        try:
            from Components import HdsMarireText as MT
            if not MT.marit():
                return
            a = MT.Asezare(self)
            eticheta, sesiuni = self['sesiuni_label'].instance, self['sesiuni'].instance
            buton = a.dinSkin(self['buton_rosu'].instance)
            if eticheta is None or sesiuni is None or buton is None:
                return
            MT.potrivesteStiva(a, [(eticheta, lambda: MT.marimeFont(eticheta) * 140 // 100),
                (sesiuni, lambda: MT.inaltimeText(sesiuni))], buton[1] - 4, (sesiuni,))
        except Exception as e:
            print('[HdsDvbMABR] textul marit: %s' % e)

    def _text_stare(self):
        return S.textStare(self._config)

    def _construieste_lista(self):
        self._intrari = []
        # Optiuni generale
        activ = S.pornit(self._config, 'activ')
        auto  = S.pornit(self._config, 'autodiscover')
        self._intrari.append((_('[%s] DVB-MABR activ') % (_('DA') if activ else _('NU')), ('toggle', 'activ')))
        self._intrari.append((_('[%s] Autodiscover SAP/SD&S') % (_('DA') if auto else _('NU')), ('toggle', 'autodiscover')))
        self._intrari.append((_('--- Grupuri multicast manuale ---'), None))
        for i, (adresa, port) in enumerate(self._config.get('grupuri', [])):
            self._intrari.append(('  udp://@%s:%d' % (adresa, port), ('grup', i)))
        self._intrari.append((_('+ Adaugă grup manual (239.x.x.x:port)'), ('adauga', None)))

    def _reactualizeaza(self):
        self._construieste_lista()
        self['lista'].setList(self._intrari)
        self['stare'].setText(self._text_stare())

    def toggle_selectat(self):
        selectat = self['lista'].getCurrent()
        if not selectat or not selectat[1]:
            return
        tip, valoare = selectat[1]
        if tip == 'toggle':
            if S.comuta(self._config, valoare):
                self._reactualizeaza()
        elif tip == 'grup':
            # Sterge grupul selectat, dupa o intrebare cu Nu ales dinainte (ca pagina web /mabr, stergerea in doi pasi)
            from Screens.MessageBox import MessageBox
            self.session.openWithCallback(lambda da, i=valoare: self._stergeGrup(i, da), MessageBox,
                _('Ștergi grupul multicast?') + '\n' + selectat[0].strip(), MessageBox.TYPE_YESNO, default=False)
        elif tip == 'adauga':
            self._deschide_adauga()

    def _stergeGrup(self, index, da):
        if da and S.stergeGrup(self._config, index) is not None:
            self._reactualizeaza()

    def _deschide_adauga(self):
        """HDSatelit: era doar un mesaj de stare, autorul
        insusi lasase comentariul 'Placeholder' -- niciun dialog real. Tastatura virtuala, acelasi
        tipar ca la ScanerSatelit/HdsDvbI."""
        from Screens.VirtualKeyBoard import VirtualKeyBoard
        self.session.openWithCallback(self._dupa_adauga, VirtualKeyBoard,
            title=_('Grup multicast (adresa:port), ex. 239.1.1.1:9000'), text='239.')

    def _dupa_adauga(self, text=None):
        if text is None:
            return   # anulat din tastatura virtuala
        reusit, mesaj = S.adaugaGrup(self._config, text)
        self['sesiuni'].setText(mesaj)
        if reusit:
            self._reactualizeaza()

    def cauta_sap(self):
        """Porneste descoperirea SAP pe un fir separat (Components/HdsMabrSetari.cauta) si afiseaza sesiunile gasite;
        rezultatul vine pe firul enigma2."""
        self['sesiuni'].setText(_('Se caută sesiuni MABR în rețea (5 secunde)...'))
        S.cauta(self._config.get('interfata', ''), la_gata=self._sesiuni_gasite)

    def _sesiuni_gasite(self, rezultat):
        sesiuni = rezultat.get('sesiuni') or []
        self._sesiuni_live = sesiuni
        if sesiuni:
            text = '\n'.join('udp://@%s:%d · %s' % (s['adresa'], s['port'], s['nume'] or _('fără nume'))
                             for s in sesiuni[:3])
            if len(sesiuni) > 3:
                text += _('\n... și %d mai multe') % (len(sesiuni) - 3)
        else:
            text = S.mesajCautare(rezultat)
        try:
            self['sesiuni'].setText(text)
        except Exception:
            pass   # ecranul s-a inchis intre timp

    def salveaza(self):
        _scrie_config_mabr(self._config)
        self['stare'].setText(_('Salvat. ') + self._text_stare())

    def inchide(self):
        _scrie_config_mabr(self._config)
        self.close()

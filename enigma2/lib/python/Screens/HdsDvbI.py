# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsDvbI: ecranele DVB-I (canale de pe internet) in imaginea HDSatelit.

Scris de la zero.
Accesat din meniu: Setari > Surse Internet > DVB-I.

Ecranele DVB-I (design din Stitch):
  HdsDvbISetup      "Canale de pe internet (DVB-I)": tara si regiunea alese din registrele DVB-I, listele tarii (cele
                    adevarate bifate singure, cele de proba de bifat de mana), trecerea singura pe internet, canalele
                    incercate din casa, adresele puse de mana (avansat). Verde reincarca, Galben incearca canalele,
                    Albastru adauga o adresa.
  HdsDvbIAlegeTara  lista tarilor din registre (raspunsul tinut minte; registrele se intreaba din nou cand lipseste).
  HdsDvbIAvansat    listele predefinite, adresele puse de mana si pornirea DVB-I (ce era inainte ecranul de setari).
  HdsDvbIOprit      mesajul pentru un canal oprit pentru tara omului, cu tasta spre setarea VPN.
  HdsDvbIReloadNow  reincarcarea acum (DVB-I Reload Now).
Toata logica e in Components/HdsDvbISetari.py (aceeasi in pagina web /dvb-i, HdsWebControl/internet_web.py).
"""
from __future__ import absolute_import, unicode_literals

import time

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Button import Button
from Components.Sources.StaticText import StaticText
from enigma import eTimer, eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_CENTER

# ---------------------------------------------------------------- setarile
# Citirea si scrierea /etc/enigma2/hdsdvbi.conf, listele predefinite (din pluginul DVB-I, o singura lista) si
# reincarcarea stau in Components/HdsDvbISetari.py, aceleasi pentru aceste ecrane si pentru pagina web /dvb-i
# (HdsWebControl/internet_web.py). Inainte, aici era o copie a citirii si scrierii, care pierdea interval_refresh.
from Components import HdsDvbISetari as S
from Components import HdsMarireText as MT

CALE_CONFIG = S.CALE_CONFIG
CITIRE_MS = 1500

# culorile sistemului HD Satelit Control (Stitch): fundal, linii, accent, textele, verde, chihlimbar, rosu
FUNDAL = "#0010162a"
LINIE = "#001c2440"
ALBASTRU = "#00374ea1"
TEXT = "#00f2f4f8"
TEXT2 = "#00c9d2e3"
TEXT3 = "#00aeb9cc"
VERDE = "#004fd18b"
GALBEN = "#00f1c40f"
ROSU = "#00ff6b5e"
CULORI_STARE = {"bun": VERDE, "chihlimbar": GALBEN, "rau": ROSU, "slab": TEXT3}


def _citeste_config():
    return S.citeste()


def _scrie_config(config):
    S.scrie(config)


def _taste(y, taste):
    """pastilele colorate si etichetele tastelor (fisa Stitch: pastila 28x16, eticheta 24 px, 44 px intre taste)"""
    culori = {"red": ROSU, "green": VERDE, "yellow": GALBEN, "blue": ALBASTRU}
    rez = []
    for nume, x, latime in taste:
        rez.append('<eLabel position="%d,%d" size="28,16" backgroundColor="%s" zPosition="2" />' % (x, y + 12, culori[nume]))
        rez.append('<widget source="key_%s" render="Label" position="%d,%d" size="%d,40" font="Regular;24" valign="center" '
            'foregroundColor="%s" backgroundColor="%s" transparent="1" zPosition="2" />' % (nume, x + 40, y, latime, TEXT, FUNDAL))
    return "\n".join(rez)


def _stari(x, y, latime, inaltime, font):
    return "\n".join('<widget source="stare_%s" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" valign="center" '
        'foregroundColor="%s" backgroundColor="%s" transparent="1" zPosition="1" />' % (k, x, y, latime, inaltime, font, c, FUNDAL)
        for k, c in sorted(CULORI_STARE.items()))


# ---------------------------------------------------------------- ecran principal DVB-I
class HdsDvbIReloadNow(Screen):
    """HDSatelit: "DVB-I Reload Now" din meniu deschidea exact
    acelasi ecran ca "DVB-I Setup", fara nicio actiune reala. Ecran nou, minimal: porneste
    efectiv reincarcarea listelor configurate (plugin.reincarca_acum(), fir separat, nu
    blocheaza interfata) si arata rezultatul cand se termina."""

    skin = """
        <screen name="HdsDvbIReloadNow" resolution="1920,1080" position="center,center" size="760,220" flags="wfNoBorder" backgroundColor="#0010162a" title="DVB-I: Reîncărcare">
            <eLabel position="0,0" size="760,1" backgroundColor="#00374ea1" zPosition="1" />
            <widget name="stare" position="40,30" size="680,120" font="Regular;26" halign="center" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" />
            <eLabel position="40,166" size="28,16" backgroundColor="#00ff6b5e" zPosition="2" />
            <widget name="buton_rosu" position="80,154" size="300,40" font="Regular;24" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" />
        </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self._inchis = False
        self['stare'] = Label(_('Se reîncarcă listele DVB-I configurate...'))
        self['buton_rosu'] = Button(_('Înapoi'))
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions'],
            {'red': self.close, 'cancel': self.close, 'ok': self.close}, -1)
        self.onLayoutFinish.append(self._porneste)

    def close(self, *args):
        ceas = getattr(self, '_ceas', None)
        if ceas is not None:
            ceas.stop()
        # HDSatelit (gasit prin testare reala, KeyError necaptat): reincarcarea
        # ruleaza pe fir separat; daca utilizatorul inchide ecranul INAINTE sa se termine,
        # callback-ul _gata() venea oricum mai tarziu si incerca sa scrie pe un widget al unui
        # ecran deja inchis ("self['stare']" -> KeyError: 'stare'). Steag simplu, verificat in
        # _gata() inainte de a atinge orice widget.
        self._inchis = True
        Screen.close(self, *args)

    def _porneste(self):
        # o reincarcare deja pornita (din web sau din ecranul de setari) isi spune rezultatul aici cand se termina
        if not S.reincarca(la_gata=self._gata):
            self._ceas = eTimer()
            self._ceas.callback.append(self._verifica)
            self._ceas.start(500, False)

    def _verifica(self):
        st = S.stareReincarcare()
        if st['in_curs']:
            return
        self._ceas.stop()
        self._gata(st['succes'], st['eroare'])

    def _gata(self, succes, eroare):
        if self._inchis:
            return
        if succes:
            self['stare'].setText(_('Reîncărcare terminată cu succes.\nApasă OK sau Roșu pentru a închide.'))
        else:
            self['stare'].setText(_('Reîncărcarea a eșuat: %s\nApasă OK sau Roșu pentru a închide.') % (eroare or '?'))


def _factor():
    try:
        import skin
        return skin.factorHds()
    except Exception:
        return 1.0, 1.0, 1.0


def _fontHds(nume):
    """fontul HD Satelit cu rolul `nume` sub un skin strain (skin.fontHds); cu HDSatelit ales, `nume`"""
    try:
        import skin
        return skin.fontHds(nume)
    except Exception:
        return nume


def _bifa(aleasa):
    """casuta listei (liste/bifa_on.png / bifa_off.png din skin, ca SelectionList), sau None"""
    try:
        from skin import getListPixmap
        return getListPixmap("SelectionListImage", "on" if aleasa else "off")
    except Exception:
        return None, False


class ListaRanduri(MenuList):
    """Randurile ecranului DVB-I desenate din Python: textul centrat pe rand si, la listele tarii, casuta bifata sau nu
    (fisa Stitch: randuri de 64 px, text 28 px, casuta inaintea numelui). Numerele sunt pe 1920 (skin.factorHds).
    Fontul e pus din cod, deci urmeaza Marimea textului (Components/HdsMarireText); cu textul marit randul creste odata
    cu el (la 100 % aceleasi numere)."""

    def __init__(self, inaltime=64, font=28):
        MenuList.__init__(self, [], content=eListboxPythonMultiContent)
        sx, sy, sf = _factor()
        self._sx, self._sy = sx, sy
        self._inaltime = MT.inaltimeCod(max(1, int(round(inaltime * sy))))
        self.l.setFont(0, MT.fontCod(_fontHds("Regular"), max(1, int(round(font * sf)))))
        self.l.setItemHeight(self._inaltime)

    def applySkin(self, desktop, parent):
        ret = MenuList.applySkin(self, desktop, parent)
        # itemHeight din skin (64) ar pune randul inapoi: cu textul marit ramane cel socotit aici
        MT.randuriCod(self, self._inaltime)
        return ret

    def intrare(self, text, bifa=None, latime=1304):
        sx, h = self._sx, self._inaltime
        rez = [text]
        x = int(round(20 * sx))
        if bifa is not None:
            png, din_skin = _bifa(bifa)
            if png is not None:
                m = int(round(32 * sx))
                rez.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND if din_skin else
                    eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, x, max(0, (h - m) // 2), m, m, png))
                x += m + int(round(16 * sx))
            else:
                text = ("[x] " if bifa else "[  ] ") + text
        rez.append((eListboxPythonMultiContent.TYPE_TEXT, x, 0, max(1, int(round(latime * sx)) - x), h, 0,
            RT_HALIGN_LEFT | RT_VALIGN_CENTER, text))
        return rez


def _plugin():
    try:
        from Plugins.SystemPlugins.HdsDvbI import plugin
        return plugin
    except Exception:
        return None


def _rezumatIncercari():
    try:
        from Components import HdsDvbIDate
        return HdsDvbIDate.rezumat()
    except Exception:
        return {}


def _stareIncercare():
    p = _plugin()
    try:
        return p.stareIncercare() if p is not None else {}
    except Exception:
        return {}


class HdsDvbISetup(Screen):
    """Canale de pe internet (DVB-I): tara, regiunea, listele tarii, trecerea pe internet, canalele incercate din casa.
    Fisa Stitch: dvbi-048/stitch/tv-dvbi-setari (fereastra de 1400 px, randuri de 64 px, explicatia in chihlimbar)."""

    skin = """
        <screen name="HdsDvbISetup" resolution="1920,1080" position="center,center" size="1400,920" flags="wfNoBorder" backgroundColor="#0010162a" title="DVB-I: Configurare">
            <eLabel position="0,0" size="1400,1" backgroundColor="#00374ea1" zPosition="1" />
            <widget source="titlu" render="Label" position="48,30" size="1304,56" font="Regular;40" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            %(stari)s
            <widget source="detalii" render="Label" position="48,140" size="1304,64" font="Regular;22" valign="top" foregroundColor="#00aeb9cc" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget name="list" position="48,210" size="1304,512" itemHeight="64" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
            <widget source="rand" render="Label" position="48,734" size="1304,60" font="Regular;24" valign="top" foregroundColor="#00f1c40f" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget source="mesaj" render="Label" position="48,796" size="1304,36" font="Regular;22" valign="top" foregroundColor="#00c9d2e3" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <eLabel position="48,846" size="1304,1" backgroundColor="#001c2440" zPosition="1" />
            %(taste)s
        </screen>""" % {"stari": _stari(48, 92, 1304, 44, 32), "taste": _taste(862, (("red", 48, 200), ("green", 300, 230),
        ("yellow", 590, 290), ("blue", 940, 320)))}

    def __init__(self, session):
        Screen.__init__(self, session)
        self._config = _citeste_config()
        self._randuri = []
        self._mesajPana = 0
        self._inchis = False
        titlu = _('Canale de pe internet (DVB-I)')
        self.setTitle(_('DVB-I: Configurare'))
        self['titlu'] = StaticText(titlu)
        for k in CULORI_STARE:
            self['stare_' + k] = StaticText('')
        self['detalii'] = StaticText('')
        self['list'] = ListaRanduri()
        self['rand'] = StaticText('')
        self['mesaj'] = StaticText('')
        self['key_red'] = StaticText(_('Închide'))
        self['key_green'] = StaticText(_('Reîncarcă'))
        self['key_yellow'] = StaticText(_('Încearcă canalele'))
        self['key_blue'] = StaticText(_('Adaugă adresă'))
        self['tastatura'] = ActionMap(
            ['ColorActions', 'OkCancelActions', 'DirectionActions'],
            {
                'red':    self.inchide,
                'green':  self.reincarca,
                'yellow': self.incearca,
                'blue':   self.adauga_url,
                'ok':     self.ok,
                'cancel': self.inchide,
                'up':     self.sus,
                'down':   self.jos,
                'left':   self.stanga,
                'right':  self.dreapta,
            }, -1)
        self['list'].onSelectionChanged.append(self._randAles)
        self._ceas = eTimer()
        self._ceas.callback.append(self._citeste)
        # o schimbare de tara sau regiune reincarca listele dupa 2 s de liniste (apasarile repetate nu pornesc cate o
        # reincarcare, iar ultima alegere chiar se descarca, si cand o reincarcare era deja in curs)
        self._ceasReincarcare = eTimer()
        self._ceasReincarcare.callback.append(self._reincarcaAcum)
        self.onLayoutFinish.append(self._porneste)
        self.onClose.append(self._laInchidere)

    def _laInchidere(self):
        self._inchis = True
        self._ceas.stop()

    # ------------------------------------------------------------------ citirea

    def _porneste(self):
        self._citeste()
        # registrele nu au fost intrebate niciodata (sau raspunsul e vechi): se intreaba acum, in fundal
        try:
            from Components import HdsDvbIRegistru as R
            if R.deIntrebat(R.incarca()):
                S.intreabaRegistrele(la_gata=self._registreGata)
        except Exception as eroare:
            print('[HdsDvbI] registrele: %r' % (eroare,))

    def _registreGata(self, raspuns):
        if not self._inchis:
            self._citeste()

    def _citeste(self):
        self._ceas.stop()
        culoare, text, detalii = S.rezumatEcran(self._config)
        for k in CULORI_STARE:
            self['stare_' + k].setText(text if k == culoare else '')
        self['detalii'].setText(detalii)
        self._puneRanduri(S.randuriSetari(self._config, rez=_rezumatIncercari(), incercare=_stareIncercare()))
        if self._mesajPana and self._mesajPana < time.time():
            self['mesaj'].setText('')
            self._mesajPana = 0
        self._ceas.start(CITIRE_MS, True)

    def _puneRanduri(self, noi):
        if [r[:3] + r[4:5] for r in noi] == [r[:3] + r[4:5] for r in self._randuri]:
            self._randuri = noi
            self._randAles()
            return
        ales = self._randAlesAcum()
        self._randuri = noi
        self['list'].setList([self['list'].intrare(r[0], r[4]) for r in noi])
        index = 0
        if ales is not None:
            for i, r in enumerate(noi):
                if r[1] == ales[1] and r[2] == ales[2]:
                    index = i
                    break
        self['list'].moveToIndex(index)
        self._randAles()

    def _randAlesAcum(self):
        index = self['list'].getSelectionIndex()
        if 0 <= index < len(self._randuri):
            return self._randuri[index]
        return None

    def _randAles(self):
        r = self._randAlesAcum()
        self['rand'].setText(r[3] if r is not None else '')

    def _mesaj(self, text):
        self['mesaj'].setText(text)
        self._mesajPana = time.time() + 15

    # ------------------------------------------------------------------ tastele

    def sus(self):
        self['list'].up()

    def jos(self):
        self['list'].down()

    def _salveaza(self, reincarca=False):
        _scrie_config(self._config)
        if reincarca:
            self._ceasReincarcare.start(2000, True)
        self._citeste()

    def _reincarcaAcum(self):
        if not S.reincarca():
            # o reincarcare e deja in curs (cu alegerea de dinainte): a noastra porneste dupa ea
            self._ceasReincarcare.start(2000, True)

    def stanga(self):
        self._sageata(-1)

    def dreapta(self):
        self._sageata(+1)

    def _sageata(self, pas):
        r = self._randAlesAcum()
        if r is None:
            return
        if r[1] == S.R_TARA:
            S.seteazaTara(self._config, S.tariVecine(self._config, pas))
            self._salveaza(reincarca=True)
            self._mesaj(_('Țara aleasă: %s. Listele ei se descarcă acum.') % S.numeTara(self._config.get('tara', '')))
        elif r[1] == S.R_REGIUNE:
            S.seteazaRegiune(self._config, S.regiuneVecina(self._config, pas))
            self._salveaza(reincarca=True)
        elif r[1] == S.R_REZERVA:
            self.ok()

    def ok(self):
        r = self._randAlesAcum()
        if r is None:
            return
        actiune, valoare = r[1], r[2]
        if actiune == S.R_TARA:
            self.session.openWithCallback(self._taraAleasa, HdsDvbIAlegeTara, self._config.get('tara', ''))
        elif actiune == S.R_REGIUNE:
            self._sageata(+1)
        elif actiune == S.R_LISTA:
            if S.comutaListaTarii(self._config, valoare):
                self._salveaza(reincarca=True)
        elif actiune == S.R_REZERVA:
            S.comutaRezerva(self._config)
            self._salveaza()
        elif actiune == S.R_INCERCARI:
            self.incearca()
        elif actiune == S.R_AVANSAT:
            self.session.openWithCallback(self._dupaAvansat, HdsDvbIAvansat)
        elif actiune == S.R_INCHIDE:
            self.inchide()

    def _taraAleasa(self, tara=None):
        if tara is None:
            return
        S.seteazaTara(self._config, tara)
        self._salveaza(reincarca=True)
        if tara:
            self._mesaj(_('Țara aleasă: %s. Listele ei se descarcă acum.') % S.numeTara(tara))

    def _dupaAvansat(self, *rezultat):
        self._config = _citeste_config()
        self._citeste()

    def incearca(self):
        p = _plugin()
        if p is not None and p.incearca_acum(forteaza=True):
            self._mesaj(_('Canalele se încearcă acum din casă, unul câte unul.'))
        else:
            self._mesaj(_('Canalele se încearcă deja.'))
        self._citeste()

    def adauga_url(self):
        self.session.openWithCallback(self._url_introdus, HdsDvbIAdaugaURL)

    def _url_introdus(self, url=None):
        if url:
            reusit, mesaj = S.adaugaUrl(self._config, url)
            if reusit:
                self._salveaza(reincarca=True)
                self._mesaj(_('Adresa a fost adăugată.'))
            else:
                self._mesaj(mesaj)

    def reincarca(self):
        """Reincarcarea acum, aceeasi ca DVB-I Reload Now si ca in pagina web (Components/HdsDvbISetari.py); fisierul
        se scrie inainte, ca listele bifate acum sa se si descarce."""
        try:
            _scrie_config(self._config)
            if S.reincarca():
                self._mesaj(_('Se reîncarcă listele DVB-I...'))
            else:
                self._mesaj(_('O reîncărcare e deja în curs.'))
        except Exception as e:
            self._mesaj(_('Eroare: %s') % e)
        self._citeste()

    def inchide(self):
        _scrie_config(self._config)
        if self._ceasReincarcare.isActive():
            # alegerea facuta chiar inainte de iesire se descarca oricum
            self._ceasReincarcare.stop()
            S.reincarca()
        self.close()


# ---------------------------------------------------------------- lista tarilor
class HdsDvbIAlegeTara(Screen):
    """Tarile care au liste DVB-I in registre (fisa Stitch tv-dvbi-tara): "Germania · liste: 26", ultimul rand "Nicio
    tara". Cand raspunsul tinut minte lipseste, registrele se intreaba acum; daca niciunul nu raspunde, ecranul spune
    ce s-a intrebat si ce a raspuns fiecare."""

    skin = """
        <screen name="HdsDvbIAlegeTara" resolution="1920,1080" position="center,center" size="760,840" flags="wfNoBorder" backgroundColor="#0010162a" title="Alege țara">
            <eLabel position="0,0" size="760,1" backgroundColor="#00374ea1" zPosition="1" />
            <widget source="titlu" render="Label" position="42,26" size="676,50" font="Regular;36" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget source="nota" render="Label" position="42,80" size="676,64" font="Regular;22" valign="top" foregroundColor="#00aeb9cc" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget name="list" position="42,150" size="676,560" itemHeight="56" font="Regular;28" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" textOffset="16,11" zPosition="2" />
            <eLabel position="42,738" size="676,1" backgroundColor="#001c2440" zPosition="1" />
            %(taste)s
        </screen>""" % {"taste": _taste(764, (("red", 42, 220), ("green", 330, 300)))}

    def __init__(self, session, tara=''):
        Screen.__init__(self, session)
        self._tara = tara or ''
        self._coduri = []
        self._inchis = False
        self.setTitle(_('Alege țara'))
        self['titlu'] = StaticText(_('Alege țara'))
        self['nota'] = StaticText('')
        self['list'] = MenuList([])
        self['key_red'] = StaticText(_('Înapoi'))
        self['key_green'] = StaticText(_('Alege'))
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions', 'DirectionActions'], {
            'ok': self.alege, 'green': self.alege, 'red': self.inapoi, 'cancel': self.inapoi,
            'up': lambda: self['list'].up(), 'down': lambda: self['list'].down(),
        }, -1)
        # cat se intreaba registrele (de aici sau din ecranul de setari), lista se umple cand vine raspunsul
        self._ceas = eTimer()
        self._ceas.callback.append(self._asteapta)
        self.onLayoutFinish.append(self._umple)
        self.onClose.append(self._laInchidere)

    def _laInchidere(self):
        self._inchis = True
        self._ceas.stop()

    def _asteapta(self):
        if S.stareRegistre()['in_curs']:
            self._ceas.start(1000, True)
        else:
            self._umple(intreaba=False)

    def _umple(self, intreaba=True):
        from Components import HdsDvbIRegistru as R
        registru = R.incarca()
        tari = S.tariOrdonate(registru)
        if tari:
            self['nota'].setText(_('Țările care au liste DVB-I în registre. Listele lor se iau singure.'))
        elif S.stareRegistre()['in_curs'] or (intreaba and S.intreabaRegistrele(la_gata=self._raspuns)):
            self['nota'].setText(_('Se întreabă registrele DVB-I...'))
            self._ceas.start(1000, True)
        randuri, self._coduri = [], []
        for cod, nume, n, reale in tari:
            if reale:
                randuri.append('%s · %s %d' % (nume, _('liste:'), reale))
            else:
                randuri.append('%s · %s' % (nume, _('numai liste de probă')))
            self._coduri.append(cod)
        randuri.append(_('Nicio țară (numai adresele puse de mână)'))
        self._coduri.append('')
        self['list'].setList(randuri)
        # fara tara aleasa cursorul sta pe prima tara (nu pe "Nicio tara", la capatul listei)
        if self._tara and self._tara in self._coduri:
            self['list'].moveToIndex(self._coduri.index(self._tara))

    def _raspuns(self, raspuns):
        if self._inchis:
            return
        if raspuns and raspuns.get('liste'):
            self._umple()
            return
        # niciun registru n-a raspuns cu liste: ce s-a intrebat si ce a raspuns fiecare
        self['nota'].setText(S.textFaraRegistre(raspuns))

    def alege(self):
        i = self['list'].getSelectionIndex()
        if 0 <= i < len(self._coduri):
            self.close(self._coduri[i])

    def inapoi(self):
        self.close(None)


# ---------------------------------------------------------------- avansat: liste predefinite si adrese de mana
class HdsDvbIAvansat(Screen):
    """Listele predefinite, adresele puse de mana si pornirea DVB-I (ce era inainte ecranul de setari)."""

    skin = """
        <screen name="HdsDvbIAvansat" resolution="1920,1080" position="center,center" size="1400,840" flags="wfNoBorder" backgroundColor="#0010162a" title="DVB-I: avansat">
            <eLabel position="0,0" size="1400,1" backgroundColor="#00374ea1" zPosition="1" />
            <widget source="titlu" render="Label" position="48,30" size="1304,56" font="Regular;40" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget source="stare" render="Label" position="48,92" size="1304,40" font="Regular;26" valign="center" foregroundColor="#00aeb9cc" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget name="lista" position="48,146" size="1304,576" itemHeight="64" font="Regular;28" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" textOffset="20,15" zPosition="2" />
            <eLabel position="48,746" size="1304,1" backgroundColor="#001c2440" zPosition="1" />
            %(taste)s
        </screen>""" % {"taste": _taste(772, (("red", 48, 200), ("green", 300, 230), ("yellow", 590, 290), ("blue", 940, 320)))}

    def __init__(self, session):
        Screen.__init__(self, session)
        self._config = _citeste_config()
        self._construieste_lista()
        self.setTitle(_('DVB-I: avansat'))
        self['titlu'] = StaticText(_('Adrese puse de mână și liste predefinite'))
        self['stare'] = StaticText(S.textStare(self._config))
        self['lista'] = MenuList(self._intrari)
        self['key_red'] = StaticText(_('Înapoi'))
        self['key_green'] = StaticText(_('Reîncarcă'))
        self['key_yellow'] = StaticText(_('Pornit/Oprit'))
        self['key_blue'] = StaticText(_('Adaugă adresă'))
        self['tastatura'] = ActionMap(
            ['ColorActions', 'OkCancelActions', 'DirectionActions'],
            {
                'red':    self.inchide,
                'green':  self.reincarca,
                'yellow': self.toggle_activ,
                'blue':   self.adauga_url,
                'ok':     self.toggle_selectat,
                'cancel': self.inchide,
                'up':     lambda: self['lista'].up(),
                'down':   lambda: self['lista'].down(),
            }, -1)

    def _construieste_lista(self):
        """Construieste lista de intrari afisate: predefinite + URL-uri proprii."""
        self._intrari = []
        predefinite_active = set(self._config.get('predefinite', []))

        self._intrari.append((_('--- Liste predefinite ---'), None))
        for cheie, descriere, _adresa, _tara in S.listePredefinite():
            marcaj = '[✓] ' if cheie in predefinite_active else '[  ] '
            self._intrari.append((marcaj + descriere, ('predefinit', cheie)))

        self._intrari.append((_('--- Adrese proprii ---'), None))
        for i, url in enumerate(self._config.get('url_uri', [])):
            # adresa intreaga: un rand care nu incape deruleaza (lib/gui/elabel.h)
            self._intrari.append(('  ' + url, ('url', i)))

    def _reactualizeaza(self):
        """Reconstruieste lista si actualizeaza starea."""
        self._construieste_lista()
        self['lista'].setList(self._intrari)
        self['stare'].setText(S.textStare(self._config))
        _scrie_config(self._config)

    def toggle_selectat(self):
        """OK pe o intrare predefinita o activeaza/dezactiveaza."""
        selectat = self['lista'].getCurrent()
        if not selectat or not selectat[1]:
            return
        tip, valoare = selectat[1]
        if tip == 'predefinit':
            if S.comutaPredefinita(self._config, valoare):
                self._reactualizeaza()
        elif tip == 'url':
            # OK pe o adresa proprie o sterge, dupa o intrebare cu Nu ales dinainte (ca pagina web /dvb-i)
            from Screens.MessageBox import MessageBox
            self.session.openWithCallback(lambda da, i=valoare: self._stergeUrl(i, da), MessageBox,
                _('Ștergi adresa din listele DVB-I?') + '\n' + selectat[0].strip(), MessageBox.TYPE_YESNO, default=False)

    def _stergeUrl(self, index, da):
        if da and S.stergeUrl(self._config, index) is not None:
            self._reactualizeaza()

    def toggle_activ(self):
        S.comutaActiv(self._config)
        self._reactualizeaza()

    def adauga_url(self):
        self.session.openWithCallback(self._url_introdus, HdsDvbIAdaugaURL)

    def _url_introdus(self, url=None):
        if url and S.adaugaUrl(self._config, url)[0]:
            self._reactualizeaza()

    def reincarca(self):
        try:
            _scrie_config(self._config)
            S.reincarca()
            self['stare'].setText(_('Se reîncarcă... Canalele apar în câteva secunde în buchetul Canale de pe '
                'internet (DVB-I).'))
        except Exception as e:
            self['stare'].setText(_('Eroare: %s') % e)

    def inchide(self):
        _scrie_config(self._config)
        self.close()


# ---------------------------------------------------------------- canalul oprit pentru tara omului
class HdsDvbIOprit(Screen):
    """Mesajul pentru un canal DVB-I oprit pentru tara omului (raspunsul televiziunii masurat din casa: 403/451/401),
    cu Verde spre setarea VPN (Screens/HdsVpn.py). Fisa Stitch: tv-dvbi-oprit. Dupa iesirea din setarea VPN, canalele
    oprite se incearca din nou singure (pluginul DVB-I vede schimbarea VPN-ului); close(True) cand s-a deschis VPN-ul."""

    skin = """
        <screen name="HdsDvbIOprit" resolution="1920,1080" position="center,center" size="1000,440" flags="wfNoBorder" backgroundColor="#0010162a" title="DVB-I">
            <eLabel position="0,0" size="1000,6" backgroundColor="#00f1c40f" zPosition="1" />
            <widget source="titlu" render="Label" position="48,40" size="904,52" font="Regular;36" valign="center" foregroundColor="#00f1c40f" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <widget source="text" render="Label" position="48,112" size="904,200" font="Regular;26" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" zPosition="1" />
            <eLabel position="48,336" size="904,1" backgroundColor="#001c2440" zPosition="1" />
            %(taste)s
        </screen>""" % {"taste": _taste(364, (("green", 48, 260), ("red", 360, 260)))}

    def __init__(self, session, text, titlu=None, cu_vpn=True):
        Screen.__init__(self, session)
        self._cu_vpn = cu_vpn
        self.setTitle(titlu or _('Canalul e oprit pentru țara ta'))
        self['titlu'] = StaticText(titlu or _('Canalul e oprit pentru țara ta'))
        self['text'] = StaticText(text)
        self['key_green'] = StaticText(_('Setări VPN') if cu_vpn else '')
        self['key_red'] = StaticText(_('Închide'))
        self['tastatura'] = ActionMap(['ColorActions', 'OkCancelActions'], {
            'green': self.vpn, 'ok': self.vpn if cu_vpn else self.inchide, 'red': self.inchide, 'cancel': self.inchide,
        }, -1)

    def vpn(self):
        if not self._cu_vpn:
            return
        try:
            from Components.SystemInfo import SystemInfo
            if SystemInfo.get('HdsVpn'):
                from Screens.HdsVpn import HdsVpn
                self.session.openWithCallback(self._dupaVpn, HdsVpn)
                return
        except Exception as eroare:
            print('[HdsDvbI] setarea VPN: %r' % (eroare,))
        self['text'].setText(_('Programele VPN nu sunt în această imagine. Setarea VPN e în Meniu > Setări > Rețea și internet > VPN.'))

    def _dupaVpn(self, *rezultat):
        self.close(True)

    def inchide(self):
        self.close(False)


# ---------------------------------------------------------------- dialog adauga URL
class HdsDvbIAdaugaURL(Screen):
    """Dialog simplu pentru introducerea unui URL DVB-I."""

    skin = """
        <screen name="HdsDvbIAdaugaURL" resolution="1920,1080" position="center,center" size="900,280" flags="wfNoBorder" backgroundColor="#0010162a" title="Adaugă URL DVB-I">
            <eLabel position="0,0" size="900,1" backgroundColor="#00374ea1" zPosition="1" />
            <widget name="eticheta" position="40,24"  size="820,36" font="Regular;24" halign="left" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" />
            <widget name="input"    position="40,70"  size="820,56" font="Regular;26" halign="left" foregroundColor="#00ffffff" backgroundColor="#00374ea1" />
            <widget name="eroare"   position="40,136" size="820,36" font="Regular;22" foregroundColor="#00ff6b5e" halign="left" backgroundColor="#0010162a" transparent="1" />
            <eLabel position="40,212" size="28,16" backgroundColor="#004fd18b" zPosition="2" />
            <widget name="buton_verde"  position="80,200"  size="300,40" font="Regular;24" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" />
            <eLabel position="420,212" size="28,16" backgroundColor="#00ff6b5e" zPosition="2" />
            <widget name="buton_rosu"   position="460,200" size="300,40" font="Regular;24" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#0010162a" transparent="1" />
        </screen>"""

    # Deschis cu openWithCallback (ecranul de setari): adresa pleaca prin close(url), None la anulare. Inainte,
    # __init__ cerea si un callback pe care openWithCallback nu-l da, deci Albastru (Adauga URL) cadea cu TypeError.
    # HDSatelit: inainte, 'input' era un simplu Label, iar self._url nu era
    # NICIODATA modificat de nicaieri -- nu exista niciun ascultator de taste, nicio tastatura
    # virtuala, nimic; Salveaza dadea mereu "URL invalid" pentru ca self._url ramanea "". Reparat
    # cu tastatura virtuala deja existenta in imagine (Screens/VirtualKeyBoard.py, folosita peste
    # tot unde nu exista un widget nativ de introducere text) -- tipar standard Dreambox, nu cod nou.

    def __init__(self, session):
        Screen.__init__(self, session)
        self._url      = ''

        self['eticheta']    = Label(_('Introdu URL-ul listei DVB-I (https://...):'))
        self['input']       = Label(self._url or _('(apasă OK sau Verde ca să scrii URL-ul)'))
        self['eroare']      = Label('')
        self['buton_verde'] = Button(_('Salvează'))
        self['buton_rosu']  = Button(_('Anulează'))

        self['tastatura'] = ActionMap(
            ['ColorActions', 'OkCancelActions'],
            {
                'green':  self._deschideTastatura,
                'ok':     self._deschideTastatura,
                'red':    self._anuleaza,
                'cancel': self._anuleaza,
            }, -1)
        self.setTitle(_('Adaugă URL DVB-I'))

    def _deschideTastatura(self):
        from Screens.VirtualKeyBoard import VirtualKeyBoard
        self.session.openWithCallback(self._dupaTastatura, VirtualKeyBoard,
            title=_('Introdu URL-ul listei DVB-I'), text=self._url)

    def _dupaTastatura(self, text=None):
        if text is None:
            return  # anulat din tastatura virtuala -- ramane la ce era, nu inchide dialogul
        self._url = text.strip()
        self['input'].setText(self._url or _('(apasă OK sau Verde ca să scrii URL-ul)'))
        self['eroare'].setText('')
        if self._url:
            self._salveaza()

    def _salveaza(self):
        url = self._url.strip()
        if not S.urlBun(url):
            self['eroare'].setText(_('URL invalid. Trebuie să înceapă cu http:// sau https://'))
            return
        self.close(url)

    def _anuleaza(self):
        self.close(None)

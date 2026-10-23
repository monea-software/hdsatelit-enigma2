# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Aspectul HDSatelit al ferestrelor: curat, usor, fara nicio imagine. Facut de hdsatelit.com.

Ferestrele se descriu o singura data, in unitati de 1280x720, si se scaleaza la rezolutia reala a interfetei
(getDesktop(0).size().width(): 1280 HD, 1920 FHD, 2560/3840 pe cutiile UHD care au interfata mare). Se
scaleaza position, size, font, itemHeight si borderWidth.

Aspect simplu, dupa cerinta: doar culori si text. Panoul e o culoare cu alfa, bara de titlu o culoare plina,
sub ea o linie de accent albastru, fara sigla si fara numele sitului. Asta costa zero memorie de imagine si arata la fel pe orice imagine.
Doar atribute pe care le au toate imaginile (verificat in skin.py al imaginilor Enigma2 raspandite): position, size, font,
foregroundColor, backgroundColor, transparent, zPosition, halign, valign, itemHeight, scrollbarMode,
backgroundColorSelected, foregroundColorSelected, flags. Font doar „Regular", care exista in orice skin.

Culorile enigma2 sunt #AARRGGBB, cu AA = 00 opac si FF transparent.
"""
import re

from .limba import IN_IMAGINE

CULORI = {
    'fond': '#1A0B1526',          # albastru foarte inchis, ~90% opac
    'titlu': '#000E2440',
    'accent': '#002E9BE0',        # albastrul hdsatelit
    'text': '#00F2F6FC',
    'text2': '#0099BAD6',
    'verde': '#00B2E0B4',
    'selectie': '#00245A8C',
    'rosu': '#00D0453A',
    'verde_buton': '#0033A457',
    'galben': '#00D9A21B',
    'albastru': '#002E86DE',
    'bara_fond': '#00182238',
}

_ATRIBUTE = re.compile(r'\b(position|size|itemHeight|borderWidth)="([0-9, ]+)"')
_FONT = re.compile(r'font="Regular;(\d+)"')


def factor():
    # HDSatelit: si in jos, nu numai in sus; sub 1280 de puncte (1024x576,
    # 720x576) ferestrele ramaneau de 1280 si ieseau din ecran. Pe 1280x720 ramane 1.0, pe 1920x1080 1.5, ca inainte.
    try:
        from enigma import getDesktop
        latime = getDesktop(0).size().width()
        if latime > 0:
            return latime / 1280.0
    except Exception:
        pass
    return 1.0


def scaleaza(xml, f=None):
    if f is None:
        f = factor()
    if f == 1.0:
        return _culori(xml)

    def numere(m):
        valori = [v.strip() for v in m.group(2).split(',')]
        return '%s="%s"' % (m.group(1), ','.join(str(int(round(int(v) * f))) if v.isdigit() else v
                                                  for v in valori))
    xml = _ATRIBUTE.sub(numere, xml)
    xml = _FONT.sub(lambda m: 'font="Regular;%d"' % int(round(int(m.group(1)) * f)), xml)
    return _culori(xml)


def _culori(xml):
    for nume, valoare in CULORI.items():
        xml = xml.replace('{%s}' % nume, valoare)
    return xml


def _cadru(latime, inaltime):
    """Fundalul comun: panou, bara de titlu, linia de accent si titlul (fara numele sitului pe ecran)."""
    return (
        '<eLabel position="0,0" size="{w},{h}" backgroundColor="{{fond}}" zPosition="-2" />'
        '<eLabel position="0,0" size="{w},52" backgroundColor="{{titlu}}" zPosition="-1" />'
        '<eLabel position="0,52" size="{w},3" backgroundColor="{{accent}}" zPosition="0" />'
        '<widget source="Title" render="Label" position="22,8" size="{tw},38" font="Regular;28" '
        'foregroundColor="{{text}}" backgroundColor="{{titlu}}" transparent="1" valign="center" noWrap="1" />'
    ).format(w=latime, h=inaltime, tw=latime - 44)


def _butoane(y, latime):
    """Patru butoane colorate jos: text + bara colorata de 4 px sub el."""
    pas = (latime - 40) // 4
    bucati = []
    for i, (nume, culoare) in enumerate((('key_red', 'rosu'), ('key_green', 'verde_buton'),
                                         ('key_yellow', 'galben'), ('key_blue', 'albastru'))):
        x = 20 + i * pas
        bucati.append('<widget source="%s" render="Label" position="%d,%d" size="%d,30" font="Regular;20" '
                      'halign="center" valign="center" foregroundColor="{text}" backgroundColor="{fond}" '
                      'transparent="1" />' % (nume, x, y, pas - 12))
        bucati.append('<eLabel position="%d,%d" size="%d,4" backgroundColor="{%s}" />'
                      % (x, y + 32, pas - 12, culoare))
    return ''.join(bucati)


def principal():
    # lata: un rand de feed are transponderul, numele, posturile invatate si starea verificarii
    w, h = 1180, 580
    return scaleaza(
        '<screen position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="{fond}">' % (w, h)
        + _cadru(w, h)
        + '<widget name="lista" position="20,68" size="1140,380" itemHeight="38" font="Regular;24" '
          'scrollbarMode="showOnDemand" foregroundColor="{text}" backgroundColor="{fond}" '
          'foregroundColorSelected="{text}" backgroundColorSelected="{selectie}" transparent="1" />'
        + '<eLabel position="20,458" size="1140,1" backgroundColor="{bara_fond}" />'
        + '<widget name="stare" position="20,466" size="1140,56" font="Regular;20" foregroundColor="{text2}" '
          'backgroundColor="{fond}" transparent="1" valign="top" />'
        + _butoane(528, w)
        + '</screen>')


def configurare():
    w, h = 900, 560
    # in imaginea HDSatelit lista de setari primeste si litera valorilor (secondfont, stiut de skin.py al imaginii);
    # pe alte imagini atributul poate lipsi din skin.py, deci ramane numai in imagine
    valori = ' secondfont="Regular;24"' if IN_IMAGINE else ''
    return scaleaza(
        '<screen position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="{fond}">' % (w, h)
        + _cadru(w, h)
        + ('<widget name="config" position="20,68" size="860,380" itemHeight="38" font="Regular;24"%s '
           'scrollbarMode="showOnDemand" foregroundColor="{text}" backgroundColor="{fond}" '
           'foregroundColorSelected="{text}" backgroundColorSelected="{selectie}" transparent="1" />' % valori)
        + '<widget name="ajutor" position="20,456" size="860,50" font="Regular;19" foregroundColor="{text2}" '
          'backgroundColor="{fond}" transparent="1" />'
        + _butoane(508, w)
        + '</screen>')


def despre():
    w, h = 760, 300
    return scaleaza(
        '<screen position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="{fond}">' % (w, h)
        + _cadru(w, h)
        + '<widget name="text" position="30,80" size="700,150" font="Regular;24" foregroundColor="{text}" '
          'backgroundColor="{fond}" transparent="1" valign="top" />'
        + '<widget name="versiune" position="30,240" size="700,30" font="Regular;18" foregroundColor="{text2}" '
          'backgroundColor="{fond}" transparent="1" />'
        + '</screen>')


def mesaj():
    """Mesajul de stare (acord, rotire, pornire): sus in dreapta, sub fereastra de volum, mic, fara taste. Nu sta in
    mijloc, unde ar acoperi titlul listei de canale deschise; textul are doua randuri, ca numele lungi ale fluxurilor
    sa nu fie taiate."""
    w, h = 400, 110
    return scaleaza(
        '<screen position="816,93" size="%d,%d" flags="wfNoBorder" backgroundColor="{fond}" zPosition="10">'
        % (w, h)
        + '<eLabel position="0,0" size="%d,%d" backgroundColor="{fond}" zPosition="-2" />' % (w, h)
        + '<eLabel position="0,0" size="5,%d" backgroundColor="{accent}" />' % h
        + '<widget name="titlu" position="20,8" size="366,28" font="Regular;21" foregroundColor="{text2}" '
          'backgroundColor="{fond}" transparent="1" noWrap="1" />'
        + '<widget name="text" position="20,38" size="366,66" font="Regular;23" foregroundColor="{text}" '
          'backgroundColor="{fond}" transparent="1" />'
        + '</screen>')


def notita():
    """HdsRecoveryNotice cand skinul nu il are: sus dreapta, sub fereastra de volum, doar culori.
    In skinul HDSatelit (1920): 1224,140 600x150; aici in unitati 1280, putin mai inalt pentru mesaje pe doua randuri."""
    w, h = 400, 120
    return scaleaza(
        '<screen position="816,93" size="%d,%d" flags="wfNoBorder" backgroundColor="{fond}" zPosition="15">' % (w, h)
        + '<eLabel position="0,0" size="%d,%d" backgroundColor="{fond}" zPosition="-2" />' % (w, h)
        + '<eLabel position="0,0" size="4,%d" backgroundColor="{accent}" />' % h
        + '<widget name="titlu" position="16,6" size="300,28" font="Regular;21" foregroundColor="{text}" '
          'backgroundColor="{fond}" transparent="1" noWrap="1" />'
        + '<widget name="ora" position="316,8" size="70,26" font="Regular;16" halign="right" foregroundColor="{text2}" '
          'backgroundColor="{fond}" transparent="1" />'
        + '<widget name="mesaj" position="16,38" size="372,76" font="Regular;18" foregroundColor="{text}" '
          'backgroundColor="{fond}" transparent="1" valign="top" />'
        + '</screen>')


def osd():
    """Banda de captura: jos, pe toata latimea. Doua bare (Semnal, Calitate) si campurile pe randuri."""
    w, h = 1220, 230
    return scaleaza(
        '<screen position="30,466" size="%d,%d" flags="wfNoBorder" backgroundColor="#80081022" zPosition="20">'
        % (w, h)
        + '<eLabel position="0,0" size="%d,%d" backgroundColor="#50081022" zPosition="-2" />' % (w, h)
        + '<eLabel position="0,%d" size="%d,1" backgroundColor="#6078A0D7" />' % (h - 1, w)
        + '<widget name="titlu" position="18,10" size="1184,32" font="Regular;24" foregroundColor="{text}" '
          'backgroundColor="#50081022" transparent="1" />'
        + '<widget name="et_semnal" position="18,50" size="90,24" font="Regular;18" foregroundColor="{text2}" '
          'backgroundColor="#50081022" transparent="1" />'
        + '<eLabel position="110,56" size="380,12" backgroundColor="{bara_fond}" />'
        + '<widget name="plin_semnal" position="110,56" size="380,12" backgroundColor="{verde_buton}" zPosition="1" />'
        + '<widget name="semnal" position="500,50" size="70,24" font="Regular;18" foregroundColor="{text}" '
          'backgroundColor="#50081022" transparent="1" />'
        + '<widget name="et_calitate" position="600,50" size="100,24" font="Regular;18" foregroundColor="{text2}" '
          'backgroundColor="#50081022" transparent="1" />'
        + '<eLabel position="702,56" size="380,12" backgroundColor="{bara_fond}" />'
        + '<widget name="plin_calitate" position="702,56" size="380,12" backgroundColor="{verde_buton}" zPosition="1" />'
        + '<widget name="calitate" position="1092,50" size="80,24" font="Regular;18" foregroundColor="{text}" '
          'backgroundColor="#50081022" transparent="1" />'
        + '<widget name="campuri" position="18,84" size="1184,138" font="Regular;19" foregroundColor="{text}" '
          'backgroundColor="#50081022" transparent="1" valign="top" />'
        + '</screen>')


def text():
    w, h = 1100, 620
    return scaleaza(
        '<screen position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="{fond}">' % (w, h)
        + _cadru(w, h)
        + '<widget name="text" position="20,68" size="1060,540" font="Regular;20" foregroundColor="{text}" '
          'backgroundColor="{fond}" transparent="1" />'
        + '</screen>')

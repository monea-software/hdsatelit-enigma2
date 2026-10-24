# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Legatura pluginului cu paznicul anti-blocaj (comun/paznic/paznic.py). Facut de hdsatelit.com.

  - un eTimer la 10 s scrie /tmp/hds-bataie (JSON mic, pe tmpfs): momentul, pid-ul enigma2 si daca motorul
    se roteste acum (cu cat timp mai are nevoie). Daca enigma2 se agata, bataia se opreste si paznicul vede.
  - steagul /etc/enigma2/hds-paznic.oprit spune paznicului sa stea (setarea „Paznic anti-blocaj" pe nu).
  - dupa o repornire facuta de paznic, la pornirea sesiunii se arata un mesaj (fisierul /tmp/hds-paznic.eveniment).
Un singur timer pe proces, tinut de coordonator, oricate pluginuri ar fi instalate.

In imaginea HD Satelit (IN_IMAGINE) nimic de aici nu arata vreo fereastra pe televizor (regula imaginii: fara mesaje
despre defecte interne): paznicul pluginului nu porneste in imagine (imagine.porneste nu cere bataia), imaginea are
paznicul ei (Components/HdsPaznic.py, hds-watchdog), iar memoria decodorului o reface singur
Components/HdsMemorieDriver.py (repornirea in standby, cu pazele ei; si la un film). Daca bataia ar fi pornita
totusi in imagine, mesajele "Receptorul trebuie repornit din meniu." si cele de dupa repornire nu se arata:
evenimentul ramane numai in jurnalul paznicului. In pluginul pentru alte imagini mesajele raman ca pana acum.
"""
import json
import os
import time

from . import compat, jurnal
from .limba import IN_IMAGINE, _

# duratele (imaginea lipsa de N s) pe ceasul monoton; `t` din fisierul bataii ramane ora de perete (paznicul il
# compara cu ora lui)
_monoton = compat.monoton

CALE_BATAIE = '/tmp/hds-bataie'
STEAG_OPRIT = '/etc/enigma2/hds-paznic.oprit'
EVENIMENT = '/tmp/hds-paznic.eveniment'
# evenimentele decodor/driver se scriu si pe disc: repornirea receptorului goleste /tmp (vezi paznic.EVENIMENT_DISC)
EVENIMENT_DISC = '/etc/enigma2/hds-paznic.eveniment'
JURNAL_DISC = '/etc/enigma2/hds-paznic.log'
PAS_MS = 10000
# memoria driverului pierduta de portul 8001 (paznic, punctul 6): mesajul se arata o data, semnul sta in /tmp
MEMORIE_ARATAT = '/tmp/hds-memorie-8001.aratat'


def _text_memorie():
    return _('Receptorul trebuie repornit din meniu pentru ca imaginea sa ramana stabila.')



def _scrie_semn(cale):
    try:
        with open(cale, 'w') as f:
            f.write('%d\n' % int(time.time()))
    except (IOError, OSError):
        pass


class Bataie(object):

    def __init__(self, coord):
        self.coord = coord
        self._timer = None
        self._legatura = None         # manierul legaturii timerului (cu semnale-obiect legatura traieste doar cat e tinut)
        self.scrieri = 0
        self.sesiune = None
        self._zero_de_la = None
        self._decodor_aratat = None

    def porneste(self):
        if self._timer is None:
            from enigma import eTimer
            self._timer = eTimer()
            self._legatura = compat.conecteaza_timer(self._timer, self.bate)
        self._timer.start(PAS_MS, False)
        self.bate()

    def stare_rotire(self):
        """(se_roteste, secunde_ramase) din controlorii care acordeaza acum."""
        for c in list(self.coord.controlori.values()):
            try:
                if getattr(c, 'rotire', False):
                    return True, 60
                t = c.tuner
                if t.stare in ('acord', 'rotire') and t.tinut():
                    ramas = t.ramas_s()
                    return t.stare == 'rotire' or bool(t._asezare), ramas
            except Exception:
                pass
        return False, 0

    def bate(self):
        try:
            rotire, ramas = self.stare_rotire()
            date = {'t': int(time.time()), 'pid': os.getpid(), 'rotire': rotire, 'rotire_ramas_s': ramas,
                    'activ': bool(self.coord.controlor_activ())}
            date.update(self.stare_video())
            tmp = CALE_BATAIE + '.tmp'
            with open(tmp, 'w') as f:
                f.write(json.dumps(date))
            compat.inlocuieste(tmp, CALE_BATAIE)
            self.scrieri += 1
            self.mesaj_decodor()
        except Exception:
            jurnal.eroare('bataie', 'scriere')


    def stare_video(self):
        """Pentru paznic: serviciul ar trebui sa aiba imagine, dar latimea e 0 de N secunde?"""
        if self.sesiune is None:
            return {}
        from . import captura
        asteptat = captura.video_asteptat(self.sesiune)
        latime = captura.latime_serviciu(self.sesiune) if asteptat else -1
        acum = _monoton()
        if asteptat and latime == 0:
            if self._zero_de_la is None:
                self._zero_de_la = acum
        else:
            self._zero_de_la = None
        return {'video_asteptat': asteptat, 'latime_video': latime,
                'latime_zero_s': int(acum - self._zero_de_la) if self._zero_de_la is not None else 0}

    def mesaj_decodor(self):
        """Paznicul a gasit decodorul fara memorie: mesaj o data pe eveniment. Nu repornim nimic singuri. In imagine
        niciun mesaj (vezi sus): ramane numai jurnalul paznicului."""
        if IN_IMAGINE:
            return
        try:
            if not os.path.exists(EVENIMENT):
                return
            with open(EVENIMENT) as f:
                date = json.loads(f.read(4096) or '{}')
            fel = date.get('fel')
            if fel not in ('decodor', 'driver', 'memorie') or date.get('t') == self._decodor_aratat:
                return
            self._decodor_aratat = date.get('t')
            if fel == 'memorie':
                # o singura data pe pornire a receptorului, si peste reporniri ale interfetei (semn in /tmp)
                if os.path.exists(MEMORIE_ARATAT):
                    return
                _scrie_semn(MEMORIE_ARATAT)
                text = _text_memorie()
            else:
                text = _('Receptorul trebuie repornit din meniu.')
            from Tools.Notifications import AddPopup
            from Screens.MessageBox import MessageBox
            AddPopup(text, MessageBox.TYPE_WARNING
                     if hasattr(MessageBox, 'TYPE_WARNING') else MessageBox.TYPE_INFO, 0, 'hdsdecodor')
        except Exception:
            jurnal.eroare('bataie', 'mesajul decodorului')


def obtine(coord):
    b = getattr(coord, 'bataie', None)
    if b is None:
        b = Bataie(coord)
        coord.bataie = b
        b.porneste()
    return b


def aplica_setarea(pornit):
    """Setarea din fereastra: pune sau scoate steagul de oprire al paznicului."""
    try:
        if pornit and os.path.exists(STEAG_OPRIT):
            os.remove(STEAG_OPRIT)
        elif not pornit and not os.path.exists(STEAG_OPRIT):
            with open(STEAG_OPRIT, 'w') as f:
                f.write('oprit din setari\n')
    except Exception:
        jurnal.eroare('bataie', 'steagul paznicului')


def mesaj_dupa_repornire():
    """Textul de aratat daca paznicul a repornit enigma2 (o singura data), altfel None."""
    return eveniment_dupa_repornire()[0]


def eveniment_dupa_repornire():
    """(text, momentul evenimentului) daca paznicul a lasat un eveniment (o singura data), altfel (None, None).

    Intai /tmp (enigma2 repornit, receptorul nu). Daca in /tmp nu e nimic, dar pe disc a ramas un eveniment
    decodor/driver, receptorul a fost repornit intre timp: mesajul spune asta. Ambele fisiere se sterg.
    """
    text, t = None, None
    if IN_IMAGINE:
        # in imagine fara mesaj pe televizor (vezi sus); fisierele se sterg ca la plugin, evenimentul ramane in jurnal
        for cale in (EVENIMENT, EVENIMENT_DISC):
            try:
                if os.path.exists(cale):
                    os.remove(cale)
            except Exception:
                jurnal.eroare('bataie', 'evenimentul paznicului')
        return None, None
    try:
        if os.path.exists(EVENIMENT):
            with open(EVENIMENT) as f:
                date = json.loads(f.read(4096) or '{}')
            os.remove(EVENIMENT)
            text, t = _text_eveniment(date), date.get('t')
    except Exception:
        jurnal.eroare('bataie', 'evenimentul paznicului')
    try:
        if os.path.exists(EVENIMENT_DISC):
            with open(EVENIMENT_DISC) as f:
                date = json.loads(f.read(4096) or '{}')
            os.remove(EVENIMENT_DISC)
            if text is None:
                text, t = _text_eveniment(date, dupa_repornire=True), date.get('t')
    except Exception:
        jurnal.eroare('bataie', 'evenimentul paznicului de pe disc')
    return text, t


def _text_eveniment(date, dupa_repornire=False):
    fel = date.get('fel') if isinstance(date, dict) else None
    if fel == 'memorie':
        if dupa_repornire or os.path.exists(MEMORIE_ARATAT):
            return None
        _scrie_semn(MEMORIE_ARATAT)
        return _text_memorie()
    if dupa_repornire and fel == 'decodor':
        return None     # mesajul a aparut in timpul functionarii (mesaj_decodor); repornirea l-a rezolvat
    if dupa_repornire and fel == 'driver':
        return _('Paznicul a gasit data trecuta enigma2 blocat in driver. Receptorul a fost repornit.')
    if fel in ('decodor', 'driver'):
        # driver: paznicul a gasit enigma2 blocat in driver (nu a iesit nici la SIGKILL)
        return _('Receptorul trebuie repornit din meniu.')
    if fel == 'repornire':
        return _('Paznicul a repornit interfata: enigma2 nu mai raspundea.')
    if fel == 'limita':
        return _('Paznicul a gasit enigma2 blocat de prea multe ori. Vezi jurnalul paznicului.')
    return None


def citeste_jurnal_disc(linii=200):
    try:
        with open(JURNAL_DISC, 'rb') as f:
            text = f.read(64 * 1024).decode('utf-8', 'replace')
        return '\n'.join(text.splitlines()[-linii:]) or _('Jurnalul e gol.')
    except (IOError, OSError):
        return _('Jurnalul e gol.')

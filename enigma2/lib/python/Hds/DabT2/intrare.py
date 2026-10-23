# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Intrarile unui plugin in enigma2 (Pluginuri, Extensii, pornirea sesiunii). Facut de hdsatelit.com.

Ca plugin pe alte imagini, plugin.py din HdsDab si HdsT2mi e doar: `Plugins = lambda **k:
intrare.descriptori(PROFIL, CALE)`. In imaginea HDSatelit nu exista descriptori: pornirea o face imagine.py.
La incarcarea enigma2 nu se importa nimic greu: ecranele se importa la deschidere, controlorul la sesiune.
"""
from . import coordonator, jurnal
from .limba import _

_controlori = {}


def arata_notita(mesaj, t=None):
    """Ecranul „HdsRecoveryNotice" (skinul HDSatelit il are; altfel aspectul nostru), pus in coada de notificari a
    enigma2: apare cand InfoBar-ul e gata, se inchide cu OK/EXIT sau singur dupa 15 s. Rezerva: MessageBox."""
    import time
    ora = time.strftime('%H:%M', time.localtime(t if isinstance(t, (int, float)) and t > 0 else time.time()))
    try:
        from Tools.Notifications import AddNotification
        from .ecrane import EcranNotita
        AddNotification(EcranNotita, _('Paznic anti-blocaj'), mesaj, ora)
        return True
    except Exception:
        jurnal.eroare('notita', 'HdsRecoveryNotice')
    try:
        from Tools.Notifications import AddPopup
        from Screens.MessageBox import MessageBox
        AddPopup(mesaj, MessageBox.TYPE_INFO, 15, 'hdspaznic')
    except Exception:
        jurnal.eroare('notita', 'mesajul de rezerva')
    return False


def controlor(profil, cale):
    c = _controlori.get(profil.nume)
    if c is None:
        from .pornire import Controlor
        c = Controlor(profil, cale)
        _controlori[profil.nume] = c
    return c


def descriptori(profil, cale):
    from Plugins.Plugin import PluginDescriptor
    coord = coordonator.obtine()

    def la_sesiune(reason, **kwargs):
        try:
            if reason != 0 or 'session' not in kwargs:
                return
            sesiune = kwargs['session']
            controlor(profil, cale).instaleaza(sesiune)
            if coord.ia_captura(profil.nume):
                # o singura data pe proces: descarcarea zilnica a listelor (numai daca setarea e pornita)
                from . import liste
                liste.zilnic().porneste()
                # lucrurile unice pe proces: captura, tasta, bataia pentru paznic, mesajul paznicului
                from . import bataie, captura
                cap = captura.obtine(coord)
                cap.sesiune = sesiune
                cap.leaga_tasta()
                bataie.aplica_setarea(captura.configureaza().paznic.value)
                bataie.obtine(coord).sesiune = sesiune
                mesaj, t = bataie.eveniment_dupa_repornire()
                if mesaj:
                    arata_notita(mesaj, t)
            jurnal.noteaza(profil.eticheta, 'sesiune pornita')
        except Exception:
            jurnal.eroare(profil.eticheta, 'pornirea sesiunii')

    def la_pornire(reason, **kwargs):
        try:
            if reason == 1:
                # iesirea curata a enigma2: marcajele protectiei la pornire (ambele feluri) se sterg primele, inaintea
                # opririlor lente (imagine.sterge_marcajele face la fel in imagine)
                from . import marcaj, profil as _p
                for p in (_p.DAB, _p.T2):
                    marcaj.sterge(p.director)
                c = _controlori.get(profil.nume)
                if c is not None:
                    c.opreste('enigma2 se opreste')
        except Exception:
            jurnal.eroare(profil.eticheta, 'oprirea enigma2')

    def deschide(session, **kwargs):
        try:
            from .ecrane import EcranPrincipal
            session.open(EcranPrincipal, controlor(profil, cale))
        except Exception:
            jurnal.eroare(profil.eticheta, 'deschiderea ferestrei')

    def captura_acum(session, **kwargs):
        try:
            from . import captura
            captura.obtine(coord).porneste(session)
        except Exception:
            jurnal.eroare(profil.eticheta, 'captura din Extensii')

    rez = [
        PluginDescriptor(name=_(profil.titlu), description=_('Facut de hdsatelit.com'),
                         where=PluginDescriptor.WHERE_PLUGINMENU, fnc=deschide),
        PluginDescriptor(name=_(profil.titlu), description=_('Facut de hdsatelit.com'),
                         where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=deschide),
        PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=la_sesiune),
        PluginDescriptor(where=PluginDescriptor.WHERE_AUTOSTART, fnc=la_pornire),
    ]
    if coord.ia_captura(profil.nume):
        rez.append(PluginDescriptor(name=_('Captura HDSatelit.com'), description=_('Captura ecranului cu banda de date'),
                                    where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=captura_acum))
    return rez

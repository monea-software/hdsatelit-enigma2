# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ferestrele pluginurilor HdsDab si HdsT2mi. Facut de hdsatelit.com.

Se importa doar cand utilizatorul deschide pluginul (sau cand trebuie aratat un mesaj), niciodata la pornirea
enigma2. Fiecare actiune din ferestre e imbracata in try/except: o eroare scrie in jurnal si arata un mesaj.
"""
import os

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from . import aspect, buchete, captura, compat, fundal, jurnal, tuner
from . import profil as profil_mod
from .limba import IN_IMAGINE, _, ngettext
from .versiune import VERSIUNE   # versiunea codului comun, aceeasi cu a pachetelor pentru alte imagini


def fascicul_departe(tp):
    """Numele fasciculului cand lista spune ca nu ajunge in Romania (campurile 'fascicul' si 'fascicul_fara_romania' ale
    transponderului, din harta fasciculului), altfel ''."""
    tp = tp or {}
    nume = tp.get('fascicul')
    if tp.get('fascicul_fara_romania') is True and compat.e_text(nume) and nume.strip():
        return compat.text_nativ(nume.strip())
    return ''


def text_stare(feed, scurt=False, tp=None):
    """Starea verificarii pe receptorul de probe ('' daca feed-ul nu are verificare). scurt=True: pentru randul din
    lista (textul intreg se arata jos, pentru randul ales). tp: transponderul feed-ului; cand fasciculul lui nu ajunge
    in Romania, lipsa semnalului la proba se spune ca "numai in zona lui" (altfel numai faptul masurat)."""
    stare = (feed or {}).get('stare_verificare')
    if stare == 'merge':
        return _('Verificat: merge')
    if stare == 'fara_semnal_in_zona_testata':
        fascicul = fascicul_departe(tp)
        if fascicul:
            if scurt:
                return _('Numai in zona lui')
            return _('Fasciculul %s nu ajunge in Romania (la proba, cu antena de 90 cm, nu era semnal): merge numai in '
                     'zona lui') % fascicul
        if scurt:
            return _('Fara semnal la proba')
        return _('In zona testata nu era semnal (antena 90 cm); poate merge in alte zone')
    if stare == 'nu_se_decodeaza':
        return _('Nu se decodeaza')
    return ''


def text_numar(profil, n):
    """„1 post”, „5 posturi”, „20 de posturi” (DAB) sau programe (DVB-T2)."""
    if profil.tip == 'dab':
        return ngettext('%d post', '%d posturi', n) % n
    return ngettext('%d program', '%d programe', n) % n


def text_cauta(profil):
    """Fapta care porneste fluxul o data si afla ce are (Controlor.invata): pe ecran, in web si in mesaje."""
    if profil.tip == 'dab':
        return _('Cauta posturile din flux')
    return _('Cauta programele din flux')


def text_ajutor_cauta(profil):
    """Randul de ajutor de langa fapta: ce face, in cuvinte simple."""
    if profil.tip == 'dab':
        return _('Citeste din flux numele posturilor si le pune in lista de canale.')
    return _('Citeste din flux numele programelor si le pune in lista de canale.')


def text_necautat(profil):
    """Feed fara posturi aflate inca, pe randul ales jos (pe televizor, cu tasta)."""
    if profil.tip == 'dab':
        return _('Posturile nu sunt cautate inca: apasa OK, apoi Cauta posturile din flux.')
    return _('Programele nu sunt cautate inca: apasa OK, apoi Cauta programele din flux.')


def text_caut(profil, nume):
    """Mesajul cat se cauta, cu numele feed-ului."""
    if profil.tip == 'dab':
        return _('Caut posturile din %s...') % nume
    return _('Caut programele din %s...') % nume


def text_gasite(profil, n):
    """Rezultatul cautarii: „Găsite: 14 posturi.”."""
    return _('Gasite: %s.') % text_numar(profil, n)


def text_cautare_oprita(profil):
    if profil.tip == 'dab':
        return _('Cautarea posturilor s-a oprit.')
    return _('Cautarea programelor s-a oprit.')


# numele unui feed pe randul listei: cat incape langa pozitie si numar; intregul se vede jos, pe randul ales
NUME_RAND_MAX = 30


def nume_scurt(nume, maxim=NUME_RAND_MAX):
    """Numele taiat cu „…” (numarat pe caractere, nu pe octeti; pe 2.7 intra si iese in forma nativa)."""
    text = nume.decode('utf-8', 'replace') if isinstance(nume, bytes) else nume
    if len(text) > maxim:
        text = text[:maxim - 1].rstrip() + u'\u2026'
    return compat.text_nativ(text)


def stari_rand(profil, tp, feed, n):
    """(text scurt pe rand, text lung jos) pentru un feed. Functie pura, probata pe PC."""
    if tuner.multistream_neprins(tp):
        return 'Multistream', tuner.text_multistream()
    verif = text_stare(feed, tp=tp)
    if n:
        return text_numar(profil, n), verif
    lung = text_necautat(profil)
    return text_stare(feed, scurt=True, tp=tp), ('%s. %s' % (verif, lung)) if verif else lung


def _pazit(functie):
    def invelis(self, *a, **k):
        try:
            return functie(self, *a, **k)
        except Exception:
            jurnal.eroare('ecran', functie.__name__)
            try:
                self.session.open(MessageBox, _('A aparut o eroare. Detalii in /tmp/hdsdabt2.log.'),
                                  MessageBox.TYPE_ERROR, timeout=8)
            except Exception:
                pass
    invelis.__name__ = functie.__name__
    return invelis


# ---------------------------------------------------------------- ferestre fara taste
class EcranMesaj(Screen):
    def __init__(self, session):
        self.skin = aspect.mesaj()
        Screen.__init__(self, session)
        self.skinName = 'HdsMesaj'
        self['titlu'] = Label('')
        self['text'] = Label('')

    def seteaza(self, titlu, text):
        self['titlu'].setText(titlu)
        self['text'].setText(text)


class EcranNotita(Screen):
    """„HdsRecoveryNotice": mesajul paznicului / al protectiei la pornire. Skinul HDSatelit are ecranul (sus dreapta,
    Label titlu / mesaj / ora); pe alt skin se foloseste aspectul nostru. OK sau EXIT il inchid; singur dupa 15 s."""
    AFISARE_MS = 15000

    def __init__(self, session, titlu='', mesaj='', ora=''):
        self.skin = aspect.notita()
        Screen.__init__(self, session)
        self.skinName = 'HdsRecoveryNotice'
        self['titlu'] = Label(titlu)
        self['mesaj'] = Label(mesaj)
        self['ora'] = Label(ora)
        self['actiuni'] = ActionMap(['OkCancelActions'], {'ok': self._inchide, 'cancel': self._inchide}, -1)
        self._timer = None
        self._legatura = None
        try:
            from enigma import eTimer
            self._timer = eTimer()
            self._legatura = compat.conecteaza_timer(self._timer, self._inchide)
            self._timer.start(self.AFISARE_MS, True)
        except Exception:
            jurnal.eroare('ecran', 'timerul notitei')

    def _inchide(self):
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer = None
            self._legatura = compat.deconecteaza(self._legatura)
            self.close()
        except Exception:
            jurnal.eroare('ecran', 'inchiderea notitei')


class EcranOsd(Screen):
    def __init__(self, session):
        self.skin = aspect.osd()
        Screen.__init__(self, session)
        self.skinName = 'HdsOsd'
        self['titlu'] = Label('')
        self['campuri'] = Label('')
        self['semnal'] = Label('')
        self['calitate'] = Label('')
        self['plin_semnal'] = Label('')
        self['plin_calitate'] = Label('')
        self['et_semnal'] = Label(_('Semnal'))
        self['et_calitate'] = Label(_('Calitate'))
        self._procente = (0, 0)
        self._latimi = None
        self.onLayoutFinish.append(self._masoara)

    def _masoara(self):
        try:
            self._latimi = (self['plin_semnal'].instance.size(), self['plin_calitate'].instance.size())
            self._bare()
        except Exception:
            jurnal.eroare('ecran', 'osd masurare')

    def seteaza(self, titlu, lista, semnal, calitate):
        self['titlu'].setText(titlu)
        self['campuri'].setText('  |  '.join(lista))
        self['semnal'].setText('%d%%' % semnal if isinstance(semnal, (int, float)) else '-')
        self['calitate'].setText('%d%%' % calitate if isinstance(calitate, (int, float)) else '-')
        self._procente = (semnal or 0, calitate or 0)
        self._bare()

    def _bare(self):
        if not self._latimi:
            return
        try:
            from enigma import eSize
            for nume, marime, procent in (('plin_semnal', self._latimi[0], self._procente[0]),
                                          ('plin_calitate', self._latimi[1], self._procente[1])):
                w = int(marime.width() * max(0, min(100, procent)) / 100.0)
                self[nume].instance.resize(eSize(max(w, 1), marime.height()))
        except Exception:
            jurnal.eroare('ecran', 'osd bare')


# ---------------------------------------------------------------- fereastra principala
class EcranPrincipal(Screen):

    def __init__(self, session, controlor):
        self.skin = aspect.principal()
        Screen.__init__(self, session)
        self.skinName = 'HdsPrincipal'
        self.ctrl = controlor
        self.profil = controlor.profil
        self.setTitle(_(self.profil.titlu))
        self.fundal = fundal.Fundal('ecran')
        self.scanare = None
        self._stari_feed = {}
        self._legat_selectia = False
        self['lista'] = MenuList([])
        self['stare'] = Label('')
        self['key_red'] = StaticText(_('Inchide'))
        self['key_green'] = StaticText(_('Scaneaza'))
        self['key_yellow'] = StaticText(_('Adauga manual'))
        self['key_blue'] = StaticText(_('Refa buchetele'))
        self['actiuni'] = ActionMap(['OkCancelActions', 'ColorActions', 'MenuActions'], {
            'ok': self.ok,
            'cancel': self.inchide,
            'red': self.inchide,
            'green': self.scaneaza,
            'yellow': self.manual,
            'blue': self.buchete,
            'menu': self.setari,
        }, -1)
        self.onLayoutFinish.append(self.umple)
        self.onClose.append(self._la_inchidere)

    def _la_inchidere(self):
        self.fundal.opreste()
        if self.scanare is not None:
            self.scanare.opreste()

    @_pazit
    def umple(self):
        actiuni = [
            (_('Actualizeaza lista de pe hdsatelit.com'), 'actualizeaza'),
            (_('Scaneaza transponderul curent'), 'scaneaza'),
            (_('Adauga manual'), 'manual'),
            (_('Refa buchetele'), 'buchete'),
            (_('Captura ecranului cu OSD'), 'captura'),
            (_('Setari'), 'setari'),
            (_('Jurnalul paznicului'), 'jurnal_paznic'),
            (_('Despre'), 'despre'),
        ]
        if IN_IMAGINE:
            # paznicul pluginului nu e in imagine (imaginea are paznicul ei): fara jurnalul lui
            actiuni = [a for a in actiuni if a[1] != 'jurnal_paznic']
        memorate = buchete.citeste_servicii(self.profil)
        # posturile publicate pe stb.hdsatelit.com se socotesc ca in buchet: numai pe transponderele prinse
        stb = buchete.citeste_servicii_stb(self.profil)
        prinse = buchete.transpondere_prinse(self.profil) if stb else None
        feeduri = []
        for tp in self.ctrl.lista().get('transpondere', []):
            for f in tp.get('feeduri', []):
                if f.get('tip') != self.profil.tip:
                    continue
                n = len(buchete.servicii_feed(self.profil, f, memorate, stb, tp, prinse))
                scurt, lung = stari_rand(self.profil, tp, f, n)
                # numele din JSON (unicode pe 2.7) langa textul tradus (octeti UTF-8 pe 2.7): aceeasi forma
                nume = compat.text_nativ(f.get('nume') or f.get('id'))
                # numele intreg: randul ales deruleaza cand nu incape (lib/gui/elabel.h)
                text = '   %s   %s' % (tuner.text_transponder(tp), nume)
                if scurt:
                    text = '%s   %s' % (text, scurt)
                feeduri.append((text, ('feed', f.get('id'))))
                # jos, pe randul ales: numele intreg si starea lunga
                self._stari_feed[f.get('id')] = ('%s. %s' % (nume, lung)) if lung else nume
        intrari = actiuni + [(_('Feed-uri in lista: %d') % len(feeduri), None)] + feeduri
        self['lista'].setList(intrari)
        if not self['stare'].getText():
            self._stare_curenta()
        if not self._legat_selectia:
            try:
                self['lista'].onSelectionChanged.append(self._selectie)
                self._legat_selectia = True
            except Exception:
                pass

    def _selectie(self):
        """Starea intreaga a verificarii (pe rand e cea scurta) se arata jos, pentru feed-ul ales. Pe randurile de
        actiuni textul de jos ramane (mesajul ultimei actiuni)."""
        try:
            cur = self['lista'].getCurrent()
            if cur and isinstance(cur[1], tuple):
                stare = self._stari_feed.get(cur[1][1])
                if stare:
                    self['stare'].setText(stare)
        except Exception:
            jurnal.eroare('ecran', 'selectia')

    def _stare_curenta(self):
        c = self.ctrl
        if c.stare == 'canta' and c.feed:
            self['stare'].setText(_('Canta acum: %s pe %s') % (c.feed.get('nume') or c.feed.get('id'),
                                                            tuner.text_transponder(c.tp)))
        elif c.stare == 'pregatire':
            self['stare'].setText(_('Se pregateste un post.'))
        else:
            self['stare'].setText(_('Tunerul porneste doar cand alegi un post din buchetul %s.')
                                  % _(self.profil.nume_buchet))

    @_pazit
    def ok(self):
        cur = self['lista'].getCurrent()
        if not cur or cur[1] is None:
            return
        cheie = cur[1]
        if isinstance(cheie, tuple):
            self.feed(cheie[1])
            return
        getattr(self, cheie)()

    def inchide(self):
        self.close()

    # ---- actiuni
    @_pazit
    def actualizeaza(self):
        if self.fundal.in_curs():
            return
        self['stare'].setText(_('Descarc lista de pe hdsatelit.com...'))
        from . import liste
        self.fundal.lanseaza(liste.actualizeaza, self._actualizat, self.profil.tip, self.profil.director)

    @_pazit
    def _actualizat(self, ok, rez):
        if ok and isinstance(rez, tuple):
            ok, mesaj = rez
        else:
            mesaj = rez
        jurnal.noteaza(self.profil.eticheta, 'actualizare: %s %s' % (ok, mesaj))
        if ok:
            self.ctrl.lista(forteaza=True)
            r = self.ctrl.reface_buchete()
            self['stare'].setText(_('Lista actualizata. Intrari in buchet: %d.') % r.get('intrari', 0))
        else:
            self['stare'].setText(text_actualizare_esuata())
        self.umple()

    @_pazit
    def scaneaza(self):
        from . import scanare
        tp = scanare.transponder_curent(self.session)
        if tp is None:
            self.session.open(MessageBox, _('Porneste intai un canal de pe transponderul de scanat.'),
                              MessageBox.TYPE_INFO, timeout=10)
            return
        if self.scanare is None:
            self.scanare = scanare.Scanare(self.profil, self.ctrl.cale_plugin)
        if self.scanare.ruleaza():
            return
        self._tp_scanat = tp
        if self.scanare.porneste(self._scanat):
            self['stare'].setText(_('Caut fluxuri pe %s (%d s)...')
                                  % (tuner.text_transponder(tp), scanare.TIMP_DETECTOR_S))
        else:
            self['stare'].setText(_('Detectorul nu a pornit.'))

    @_pazit
    def _scanat(self, ok, rez):
        if not ok:
            self['stare'].setText(rez)
            return
        if not rez:
            self['stare'].setText(_('Pe %s nu am gasit nimic.') % tuner.text_transponder(self._tp_scanat))
            return
        # scanate.json, posturile citite din FIC (servicii.json) si buchetul: in fundal, sub zavorul scrierilor
        from . import pornire, scanare
        incorporat = os.path.join(self.ctrl.cale_plugin, 'date', 'frecvente.json')
        self.fundal.lanseaza(lambda *a: pornire._sub_zavor(scanare.salveaza_rezultatul, *a),
                             lambda ok_s, r: self._scanare_salvata(ok_s, r, len(rez)),
                             self.profil, self._tp_scanat, rez, None, None, incorporat)

    @_pazit
    def _scanare_salvata(self, ok, r, gasite):
        if not ok or not isinstance(r, dict):
            self['stare'].setText(_('Eroare interna.'))
            return
        if (r.get('buchet') or {}).get('schimbat'):
            buchete.reincarca_buchete()
        self.ctrl.lista(forteaza=True)
        self['stare'].setText(_('Fluxuri gasite: %d, noi: %d. Apasa OK pe unul.') % (gasite, r.get('noi', 0)))
        self.umple()

    @_pazit
    def manual(self):
        self.session.openWithCallback(self._manual_gata, EcranManual, self.ctrl)

    @_pazit
    def _manual_gata(self, rez=None):
        if rez:
            self.ctrl.lista(forteaza=True)
            self['stare'].setText(_('Feed adaugat. Apasa OK pe el.'))
            self.umple()

    @_pazit
    def buchete(self):
        r = self.ctrl.reface_buchete()
        if r.get('eroare'):
            self['stare'].setText(_('Buchetul nu s-a putut scrie. Detalii in jurnal.'))
        else:
            self['stare'].setText((_('Buchet refacut. Intrari: %d, fluxuri: %d.') if r['schimbat'] else
                                   _('Buchetul era la zi. Intrari: %d, fluxuri: %d.'))
                                  % (r['intrari'], r['feeduri']))

    @_pazit
    def captura(self):
        cap = captura.obtine(self.ctrl.coord)
        self.close()
        cap.porneste(self.session)

    @_pazit
    def setari(self):
        self.session.openWithCallback(self._setari_gata, EcranSetari, self.ctrl)

    def _setari_gata(self, *rez):
        try:
            if not IN_IMAGINE:
                from . import bataie
                bataie.aplica_setarea(captura.configureaza().paznic.value)
            captura.obtine(self.ctrl.coord).leaga_tasta()
        except Exception:
            jurnal.eroare('ecran', 'setari')
        try:
            # setarea feed-urilor care nu se decodeaza schimba lista si buchetul
            inainte = self.ctrl._lista_semn
            self.ctrl.lista()
            if self.ctrl._lista_semn != inainte:
                self.ctrl.reface_buchete()
            self.umple()
        except Exception:
            jurnal.eroare('ecran', 'lista dupa setari')

    @_pazit
    def despre(self):
        self.session.open(EcranDespre, self.profil)

    @_pazit
    def jurnal_paznic(self):
        from . import bataie
        self.session.open(EcranText, _('Jurnalul paznicului'), bataie.citeste_jurnal_disc())

    # ---- un feed
    @_pazit
    def feed(self, feed_id):
        f, tp = self.ctrl.cauta_feed(buchete._curata_id(feed_id))
        if f is None:
            return
        if tuner.multistream_neprins(tp) and f.get('sursa') != 'manual':
            self['stare'].setText(tuner.text_multistream())
            return
        self._feed_ales = (f, tp)
        from Screens.ChoiceBox import ChoiceBox
        variante = [(text_cauta(self.profil), 'invata')]
        if f.get('sursa') == 'manual':
            variante.append((_('Sterge feed-ul'), 'sterge'))
        # textul de sus spune ce face cautarea (doua randuri incap in fereastra de alegere); numele fluxului sta in bara
        # de titlu a ferestrei, in locul lui „Alege”
        dlg = self.session.openWithCallback(self._feed_ales_cb, ChoiceBox, title=text_ajutor_cauta(self.profil),
                                            list=variante)
        try:
            dlg.setTitle(compat.text_nativ(f.get('nume') or f.get('id')))
        except Exception:
            pass                          # alte imagini: titlul general al ferestrei ramane

    @_pazit
    def _feed_ales_cb(self, alegere):
        if not alegere:
            return
        f, tp = self._feed_ales
        if alegere[1] == 'invata':
            if tuner.multistream_neprins(tp):
                self['stare'].setText(tuner.text_multistream())
                return
            self['stare'].setText(text_caut(self.profil, f.get('nume') or f.get('id')))
            self.ctrl.invata(f, tp, self._invatat)
        elif alegere[1] == 'sterge':
            sterge_manual(self.profil, f.get('id'))
            self.ctrl.lista(forteaza=True)
            self.umple()

    @_pazit
    def _invatat(self, ok, rez):
        if ok:
            self['stare'].setText(text_gasite(self.profil, rez))
        else:
            self['stare'].setText(str(rez))
        self.umple()


# ---------------------------------------------------------------- setari si adaugare manuala
try:
    from Components.ConfigList import ConfigListScreen
except Exception:     # imagini foarte vechi
    ConfigListScreen = object


class EcranSetari(Screen, ConfigListScreen):
    def __init__(self, session, controlor):
        self.skin = aspect.configurare()
        Screen.__init__(self, session)
        self.skinName = 'HdsSetari'
        self.setTitle(_('Setari'))
        self.ctrl = controlor
        cfg = captura.configureaza()
        self._ajutor_captura = _('Captura: .jpg cu banda, -brut.jpg fara banda, .json cu datele.')
        self['ajutor'] = Label(self._ajutor_captura)
        self['key_red'] = StaticText(_('Renunta'))
        self['key_green'] = StaticText(_('Salveaza'))
        self['key_yellow'] = StaticText('')
        self['key_blue'] = StaticText('')
        lista = [
            (_('Paznic anti-blocaj'), cfg.paznic),
            (_('Captura cu apasare lunga pe INFO'), cfg.tasta),
            (_('Dosarul capturilor'), cfg.dosar),
            (_('Latimea capturii'), cfg.latime),
            (_('Arata si feed-urile care nu se decodeaza'), cfg.nedecodabile),
            (_('Ia listele DAB+ si DVB-T2 de pe stb.hdsatelit.com in fiecare zi'), cfg.liste_zilnic),
            (_('Rezerva la pornirea postului'), cfg.rezerva),
        ]
        # textul de jos urmeaza randul ales (capturile au textul lor comun)
        self._ajutor = {
            id(cfg.nedecodabile): _('Feed-urile verificate ca nedecodabile apar si ele in lista si in buchet.'),
            id(cfg.liste_zilnic): _('O data pe zi, in fundal, receptorul ia de pe stb.hdsatelit.com frecventele si '
                                    'numele posturilor. Butonul Actualizeaza lista merge oricand.'),
            id(cfg.rezerva): _('La pornirea unui post, receptorul tine o rezerva din flux, ca intreruperile scurte '
                               'sa nu se vada si sa nu se auda. Postul porneste cu atat mai tarziu.'),
        }
        if IN_IMAGINE:
            lista = lista[1:]     # paznicul pluginului nu e in imagine
        else:
            # rezerva de pornire o citeste numai nucleul imaginii (eHdsFluxHttp): pe alte imagini nu face nimic
            lista = [x for x in lista if x[1] is not cfg.rezerva]
        ConfigListScreen.__init__(self, lista, session=session)
        try:
            self['config'].onSelectionChanged.append(self._ajutor_rand)
        except Exception:
            pass
        self['actiuni_hds'] = ActionMap(['SetupActions', 'ColorActions'], {
            'save': self.salveaza, 'ok': self.salveaza, 'green': self.salveaza,
            'cancel': self.renunta, 'red': self.renunta,
        }, -2)

    def _ajutor_rand(self):
        try:
            cur = self['config'].getCurrent()
            self['ajutor'].setText(self._ajutor.get(id(cur[1]), self._ajutor_captura) if cur else self._ajutor_captura)
        except Exception:
            pass

    def salveaza(self):
        try:
            for x in self['config'].list:
                x[1].save()
            from Components.config import configfile
            configfile.save()
        except Exception:
            jurnal.eroare('ecran', 'salvare setari')
        self.close(True)

    def renunta(self):
        try:
            for x in self['config'].list:
                x[1].cancel()
        except Exception:
            pass
        self.close(False)


class EcranManual(Screen, ConfigListScreen):
    def __init__(self, session, controlor):
        from Components.config import ConfigInteger, ConfigSelection, ConfigText, NoSave
        self.skin = aspect.configurare()
        Screen.__init__(self, session)
        self.skinName = 'HdsSetari'
        self.setTitle(_('Adauga manual'))
        self.ctrl = controlor
        self.profil = controlor.profil
        self['ajutor'] = Label(_('Pozitia in zecimi de grad: 192 = 19,2 E, 3592 = 0,8 V.'))
        self['key_red'] = StaticText(_('Renunta'))
        self['key_green'] = StaticText(_('Salveaza'))
        self['key_yellow'] = StaticText('')
        self['key_blue'] = StaticText('')
        c = self.c = {}
        c['nume'] = NoSave(ConfigText(default='', fixed_size=False))
        c['pozitie'] = NoSave(ConfigInteger(default=192, limits=(0, 3599)))
        c['frecventa'] = NoSave(ConfigInteger(default=12460, limits=(10700, 12750)))
        c['pol'] = NoSave(ConfigSelection(default='H', choices=[('H', _('Orizontala')), ('V', _('Verticala')),
                                                              ('L', _('Circulara stanga')),
                                                              ('R', _('Circulara dreapta'))]))
        c['sr'] = NoSave(ConfigInteger(default=27500, limits=(1000, 60000)))
        c['sistem'] = NoSave(ConfigSelection(default='DVB-S2', choices=[('DVB-S', 'DVB-S'), ('DVB-S2', 'DVB-S2')]))
        c['modulatie'] = NoSave(ConfigSelection(default='QPSK', choices=[(x, x) for x in
                                                                        ('QPSK', '8PSK', '16APSK', '32APSK')]))
        c['fec'] = NoSave(ConfigSelection(default='auto', choices=[(x, x) for x in
                                                                  ('auto', '1/2', '2/3', '3/4', '3/5', '4/5',
                                                                   '5/6', '7/8', '8/9', '9/10')]))
        c['is_id'] = NoSave(ConfigInteger(default=0, limits=(0, 255)))
        c['multistream'] = NoSave(ConfigSelection(default='nu', choices=[('nu', _('nu')), ('da', _('da'))]))
        c['pls_cod'] = NoSave(ConfigInteger(default=0, limits=(0, 262142)))
        c['pid'] = NoSave(ConfigInteger(default=4096, limits=(32, 8190)))
        lista = [(_('Nume'), c['nume']), (_('Pozitie orbitala'), c['pozitie']),
                 (_('Frecventa (MHz)'), c['frecventa']), (_('Polarizare'), c['pol']),
                 (_('Rata de simboluri (kS/s)'), c['sr']), (_('Sistem'), c['sistem']),
                 (_('Modulatie'), c['modulatie']), ('FEC', c['fec'])]
        if tuner.nucleu_multistream():
            lista += [('Multistream', c['multistream']), ('Multistream: ISI', c['is_id']),
                      (_('Multistream: cod PLS (Gold)'), c['pls_cod'])]
        lista += [('PID', c['pid'])]
        if self.profil.tip == 'dab':
            c['fel'] = NoSave(ConfigSelection(default='edi', choices=[('edi', _('EDI prin MPE')),
                                                                      ('ts2na', _('ETI-NA in TS')),
                                                                      ('ts2na12', _('ETI-NA in TS') + ' (12)'),
                                                                      ('tsniv2ni', _('ETI-NI in TS'))]))
            c['ip'] = NoSave(ConfigText(default='239.0.0.1', fixed_size=False))
            c['port'] = NoSave(ConfigInteger(default=50000, limits=(1, 65535)))
            lista += [(_('Fel'), c['fel']), (_('IP (doar EDI)'), c['ip']), (_('Port UDP (doar EDI)'), c['port'])]
        else:
            c['plp'] = NoSave(ConfigInteger(default=0, limits=(0, 255)))
            lista += [('PLP', c['plp'])]
        ConfigListScreen.__init__(self, lista, session=session)
        self['actiuni_hds'] = ActionMap(['SetupActions', 'ColorActions'], {
            'save': self.salveaza, 'green': self.salveaza, 'cancel': self.renunta, 'red': self.renunta,
        }, -2)
        # la deschidere pe „Pozitie orbitala”: pe „Nume” ajutorul tastaturii numerice ar iesi peste marginea ferestrei
        self.onLayoutFinish.append(self._primul_rand)

    def _primul_rand(self):
        try:
            self['config'].setCurrentIndex(1)
        except Exception:
            pass

    def renunta(self):
        self.close(False)

    @_pazit
    def salveaza(self):
        c = self.c
        tp, feed = feed_manual(self.profil, dict((k, v.value) for k, v in c.items()))
        ok, mesaj = adauga_manual(self.profil, tp, feed)
        if not ok:
            jurnal.noteaza(self.profil.eticheta, 'feed manual respins: %s' % mesaj)
            self.session.open(MessageBox, _('Datele feed-ului nu sunt valide.'), MessageBox.TYPE_ERROR, timeout=10)
            return
        self.close(True)


def feed_manual(profil, v):
    """Valorile din fereastra -> (transponder, feed) in formatul listei. Functie pura."""
    ms = v.get('multistream') == 'da'
    poz = int(v['pozitie'])
    fid = 'manual_%d_%d%s_%d' % (poz, int(v['frecventa']), str(v['pol']).lower(), int(v['pid']))
    tp = {'id': 'manual_%d_%d%s' % (poz, int(v['frecventa']), str(v['pol']).lower()),
          'pozitie': poz, 'frecventa': int(v['frecventa']) * 1000, 'pol': v['pol'], 'sr': int(v['sr']) * 1000,
          'sistem': v['sistem'], 'modulatie': v['modulatie'], 'fec': v['fec'],
          'is_id': int(v['is_id']) if ms else None, 'pls_cod': int(v['pls_cod']) if ms else None,
          'pls_mod': 'gold' if ms else None}
    feed = {'id': fid, 'tip': profil.tip, 'pid': int(v['pid']), 'nume': (v.get('nume') or '').strip() or fid}
    if profil.tip == 'dab':
        feed['fel'] = v['fel']
        if v['fel'] == 'edi':
            feed['ip'] = str(v['ip']).strip()
            feed['port'] = int(v['port'])
        feed['id'] += '_%s' % v['fel']
    else:
        feed['fel'] = 't2mi'
        feed['plp'] = int(v['plp'])
        feed['id'] += '_plp%d' % int(v['plp'])
    return tp, feed


def text_actualizare_esuata():
    """Textul unei actualizari cazute, pe televizor si in web (dabt2_web il cheama tot pe acesta). Din 0.2.5: cand
    certificatul a cazut din cauza ceasului receptorului, textul comun „ceasul e în urmă” (liste.ultima_eroare_ceas)."""
    try:
        from . import liste
        ceas = liste.ultima_eroare_ceas()
    except Exception:
        ceas = None
    if ceas:
        return ceas
    return _('Lista de pe hdsatelit.com nu e disponibila acum. Merge in continuare lista venita cu imaginea.')


def adauga_manual(profil, tp, feed, director=None):
    """Pune feed-ul in manual.json (unire, fara dubluri). -> (ok, mesaj)."""
    from . import liste
    director = director or profil.director
    cale = os.path.join(director, liste.FISIER['manual'])
    vechi = liste.citeste_json(cale, profil.tip) or {'versiune': 1, 'actualizat': '', 'transpondere': []}
    t = dict(tp)
    t['feeduri'] = [feed]
    nou, mesaj = liste.verifica_lista({'versiune': 1, 'transpondere': [t]}, profil.tip)
    if not nou or not nou['transpondere']:
        return False, mesaj or 'date incomplete'
    unit = liste.uneste([('manual', vechi), ('manual', nou)])
    for x in unit:
        x.pop('sursa', None)
        for f in x['feeduri']:
            f.pop('sursa', None)
    import time
    liste.salveaza_lista(cale, {'versiune': 1, 'actualizat': time.strftime('%Y-%m-%d'), 'transpondere': unit})
    return True, 'adaugat'


def sterge_manual(profil, feed_id, director=None):
    from . import liste
    director = director or profil.director
    cale = os.path.join(director, liste.FISIER['manual'])
    vechi = liste.citeste_json(cale, profil.tip)
    if not vechi:
        return False
    for t in vechi['transpondere']:
        t['feeduri'] = [f for f in t['feeduri'] if f.get('id') != feed_id]
    vechi['transpondere'] = [t for t in vechi['transpondere'] if t['feeduri']]
    liste.salveaza_lista(cale, vechi)
    return True


class EcranDespre(Screen):
    def __init__(self, session, profil):
        self.skin = aspect.despre()
        Screen.__init__(self, session)
        self.skinName = 'HdsDespre'
        self.setTitle(_('Despre'))
        self['text'] = Label(_(profil_mod.DESPRE))   # citit la deschidere: pluginul pentru alte imagini il schimba
        # in imagine versiunea e a imaginii (Informatii); versiunea codului comun are sens numai la plugin
        self['versiune'] = Label(_(profil.titlu) if IN_IMAGINE else
                                 _('%s, versiunea %s') % (_(profil.titlu), VERSIUNE))
        self['actiuni'] = ActionMap(['OkCancelActions'], {'ok': self.close, 'cancel': self.close}, -1)


class EcranText(Screen):
    """Text lung, doar citit (jurnalul paznicului). Sus/jos deruleaza."""
    def __init__(self, session, titlu, text):
        self.skin = aspect.text()
        Screen.__init__(self, session)
        self.skinName = 'HdsText'
        self.setTitle(titlu)
        from Components.ScrollLabel import ScrollLabel
        self['text'] = ScrollLabel(text)
        self['actiuni'] = ActionMap(['OkCancelActions', 'DirectionActions'], {
            'ok': self.close, 'cancel': self.close,
            'up': self['text'].pageUp, 'down': self['text'].pageDown,
            'left': self['text'].pageUp, 'right': self['text'].pageDown,
        }, -1)

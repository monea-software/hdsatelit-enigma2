# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Captura ecranului cu banda HDSatelit.com. Facut de hdsatelit.com.

Pe receptor nu exista PIL, deci banda nu se poate desena peste o poza ca pe calculator (unelte/fa_osd.py).
Ce e realist si ce facem:
  1. Afisam banda ca fereastra enigma2 (skin fara imagini, aspect.osd), apoi, dupa 400 ms, rulam `grab` fara -v
     si fara -o: grab lipeste singur planul video cu OSD-ul, deci iese poza COMPUSA direct pe cutie.
  2. Imediat dupa, `grab -v` ia cadrul BRUT (fara banda). Cadrul brut se priveste inainte de publicare
     (regula AdSense) si, la nevoie, banda se recompune pe PC din JSON.
  3. Langa ele se scrie un JSON cu toate datele (semnal, transponder, post, debit, momentul capturii in UTC).
`grab` e unealta obisnuita de captura a imaginilor Enigma2 (aio-grab); ruleaza in eConsoleAppContainer, fara
blocare.

Regulile benzii (aceleasi ca in fa_osd.py): scrie HDSatelit.com; locatia (judetul) NU apare; SNR-ul nu se
transforma in dB, fiindca placa da o valoare relativa: apare „Calitate" in procente.

Captura se inregistreaza o singura data cand sunt instalate ambele pluginuri: coordonatorul tine obiectul si
tasta; al doilea plugin il foloseste pe acelasi.
"""
import json
import os
import time

from . import buchete, compat, fundal, jurnal, tuner
from .limba import N_, _

TITLU = N_('Receptie realizata de HDSatelit.com in Romania')
KEY_INFO = 358
FLAG_LUNG = 3
ASTEPTARE_OSD_MS = 400
TERMEN_GRAB_S = 20
DOSARE = ('/media/hdd/hdsatelit', '/media/usb/hdsatelit', '/tmp/hdsatelit')

POL_TEXT = {'H': N_('Orizontala'), 'V': N_('Verticala'), 'L': N_('Circulara stanga'), 'R': N_('Circulara dreapta')}
TRANSPORT = {'edi': N_('EDI prin MPE'), 'ts2na': N_('ETI-NA in TS'), 'ts2na12': N_('ETI-NA in TS'),
             'tsniv2ni': N_('ETI-NI in TS'), 't2mi': 'T2-MI'}


def _are(sectiune, nume):
    """Subsectiunea de config are deja `nume`? hasattr nu e sigur: ConfigSubsection.__getattr__ poate arunca
    KeyError (nu AttributeError) pentru o cheie lipsa, iar hasattr din Python 3 prinde numai AttributeError. Se
    citeste dictionarul intern (content.items); unde nu exista, hasattr cu KeyError prins."""
    try:
        return nume in sectiune.content.items
    except (AttributeError, TypeError):
        pass
    try:
        return hasattr(sectiune, nume)
    except KeyError:
        return False


# rezerva de pornire (ms): „fara”, apoi secundele cu virgula
REZERVE_MS = ('0', '200', '400', '600', '800', '1000')


def variante_rezerva():
    return [(v, _('fara') if v == '0' else '%s s' % ('%g' % (int(v) / 1000.0)).replace('.', ',')) for v in REZERVE_MS]


def configureaza():
    """config.plugins.hdscomun, comun ambelor pluginuri (se defineste o singura data)."""
    from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection
    if not _are(config.plugins, 'hdscomun'):
        config.plugins.hdscomun = ConfigSubsection()
        config.plugins.hdscomun.paznic = ConfigYesNo(default=True)
        config.plugins.hdscomun.tasta = ConfigYesNo(default=False)
        config.plugins.hdscomun.dosar = ConfigSelection(default='auto', choices=[
            ('auto', _('automat'))] + [(d, d) for d in DOSARE])
        config.plugins.hdscomun.latime = ConfigSelection(default='1920', choices=[
            ('1920', '1920'), ('1280', '1280')])
    if not _are(config.plugins.hdscomun, 'nedecodabile'):
        # 0.1.3: feed-urile verificate „nu_se_decodeaza" sunt ascunse din liste si buchete, cat timp setarea e pe nu.
        # Definita separat: un plugin vechi incarcat primul a creat deja subsectiunea fara ea.
        config.plugins.hdscomun.nedecodabile = ConfigYesNo(default=False)
    if not _are(config.plugins.hdscomun, 'liste_zilnic'):
        # 0.2.2: descarcarea zilnica a listelor de pe stb.hdsatelit.com, numai daca omul o porneste (liste.Zilnic)
        config.plugins.hdscomun.liste_zilnic = ConfigYesNo(default=False)
    if not _are(config.plugins.hdscomun, 'rezerva'):
        # 0.2.2: rezerva de la pornirea unui post DAB+ sau DVB-T2 redat prin placa, in milisecunde (citita de
        # lib/service/servicedvb.cpp, createTsSource -> eHdsFluxHttp::setStartReserve)
        config.plugins.hdscomun.rezerva = ConfigSelection(default='400', choices=variante_rezerva())
    return config.plugins.hdscomun


def _zecimal(x, cifre=1):
    return ('%.*f' % (cifre, x)).replace('.', ',')


def campuri(date):
    """Datele adunate -> (lista de campuri text, semnal %, calitate %). Functie pura, probata pe PC."""
    c = []

    def pune(eticheta, valoare):
        if valoare not in (None, '', 'N/A'):
            # pe 2.7: eticheta tradusa e octeti UTF-8, numele din JSON unicode; totul in aceeasi forma
            c.append('%s: %s' % (compat.text_nativ(eticheta), compat.text_nativ(valoare)))

    ctx = date.get('context') or {}
    feed = ctx.get('feed') or {}
    tp = ctx.get('transponder') or date.get('transponder') or {}
    releu = ctx.get('releu') or {}
    semnal = ctx.get('semnal') or date.get('semnal') or {}

    pune(_('Post') if ctx.get('tip') == 'dab' else _('Serviciu'), date.get('serviciu'))
    if ctx.get('tip') == 'dab':
        pune(_('Ansamblu'), feed.get('nume'))
        pune('EId', feed.get('ansamblu'))
    elif ctx.get('tip') == 't2':
        pune(_('Multiplex DVB-T2'), feed.get('nume'))
    if tp:
        p = tuner.parametri(tp)
        satelit = tp.get('satelit')
        poz = tuner.text_pozitie(p['orbital_position'])
        pune(_('Satelit'), '%s (%s)' % (satelit, poz) if satelit else poz)
        if p['frequency']:
            pune(_('Frecventa'), '%s MHz' % _zecimal(p['frequency'] / 1000.0, 1 if p['frequency'] % 1000 else 0))
        pol = POL_TEXT.get(str(tp.get('pol', '')).upper()[:1])
        pune(_('Polarizare'), _(pol) if pol else None)
        if p['symbol_rate']:
            pune('SR', '%d kS/s' % (p['symbol_rate'] // 1000))
    if feed:
        t = TRANSPORT.get(feed.get('fel'), feed.get('fel') or '?')
        t = _(t) if feed.get('fel') in TRANSPORT and feed.get('fel') != 't2mi' else t
        if feed.get('pid') is not None:
            t = '%s, PID %s' % (t, feed.get('pid'))
        if ctx.get('tip') == 't2' and feed.get('plp') is not None:
            t = '%s, PLP %s' % (t, feed.get('plp'))
        pune(_('Transport'), t)
    debit = releu.get('debit_kbit') or releu.get('kbit') or releu.get('debit')
    if isinstance(debit, (int, float)) and debit > 0:
        pune(_('Debit masurat'), '%s kbit/s' % _zecimal(debit, 0) if debit < 10000
             else '%s Mbit/s' % _zecimal(debit / 1000.0, 2))
    if semnal.get('ber') is not None:
        pune('BER', semnal.get('ber'))
    pune(_('Moment'), time.strftime('%d.%m.%Y %H:%M UTC', time.gmtime(date.get('moment_utc') or time.time())))
    return c, semnal.get('semnal_la_suta'), semnal.get('calitate_la_suta')


def dosar_capturi(ales='auto'):
    if ales and ales != 'auto':
        candidati = [ales]
    else:
        candidati = list(DOSARE)
    for d in candidati:
        parinte = os.path.dirname(d)
        # /media/hdd poate fi o legatura spre /run/media/...: ismount pe legatura da False, deci calea reala
        if d.startswith('/tmp') or os.path.ismount(os.path.realpath(parinte)):
            try:
                if not os.path.isdir(d):
                    os.makedirs(d)
                if os.access(d, os.W_OK):
                    return d
            except OSError:
                continue
    return '/tmp'


class Captura(object):

    def __init__(self, coord):
        self.coord = coord
        self.sesiune = None
        self.fereastra = None
        self.fundal = fundal.Fundal('captura')
        self._container = None
        self._timer = None
        self._termen = None
        self._conexiuni = []          # manierele timerelor capturii (semnale-obiect: tinute aici)
        self._legatura_grab = None    # manierul appClosed al containerului grab
        self._legatura_tasta = None
        self._pasi = []
        self._date = None
        self._nume = None
        self.in_lucru = False
        self._legat = False

    # ---- tasta lunga INFO, doar daca e ceruta in Setari
    def leaga_tasta(self):
        try:
            cfg = configureaza()
            from enigma import eActionMap
            if cfg.tasta.value and not self._legat:
                eActionMap.getInstance().bindAction('', -0x7FFFFFFF, self._tasta)
                self._legat = True
            elif not cfg.tasta.value and self._legat:
                eActionMap.getInstance().unbindAction('', self._tasta)
                self._legat = False
        except Exception:
            jurnal.eroare('captura', 'legarea tastei')

    def _tasta(self, tasta, steag):
        try:
            if tasta == KEY_INFO and steag == FLAG_LUNG and not self.in_lucru:
                from enigma import eTimer
                self._timer_tasta = eTimer()
                self._legatura_tasta = compat.conecteaza_timer(self._timer_tasta, self.porneste)
                self._timer_tasta.start(0, True)
        except Exception:
            pass
        return 0

    # ---- captura
    def porneste(self, sesiune=None):
        try:
            self._porneste(sesiune)
        except Exception:
            jurnal.eroare('captura', 'pornire')
            self._termina(_('Captura nu a mers. Vezi /tmp/hdsdabt2.log.'))

    def _porneste(self, sesiune):
        if sesiune is not None:
            self.sesiune = sesiune
        if self.in_lucru or self.sesiune is None:
            return
        self.in_lucru = True
        ctrl = self.coord.controlor_activ()
        date = {'moment_utc': int(time.time()), 'serviciu': self._nume_serviciu()}
        url = slot = None
        if ctrl is not None:
            date['context'] = ctrl.context()
            url = ctrl.profil.url_releu('/stare')
            slot = date['context'].pop('frontend_slot', None)
        else:
            date['transponder'] = self._transponder_serviciu()
            date['latime_video'] = latime_serviciu(self.sesiune)
        # in fundal: /stare al releului, ioctl pe frontend, dosarul (poate trezi discul); nimic din enigma2
        self.fundal.lanseaza(_aduna_in_fundal, lambda ok, r: self._date_venite(date, ctrl, ok, r), url, slot,
                             ctrl is None, configureaza().dosar.value)

    def _date_venite(self, date, ctrl, ok, rez):
        rez = rez if ok and isinstance(rez, dict) else {}
        if ctrl is not None:
            if isinstance(rez.get('releu'), dict):
                date['context']['releu'] = rez['releu']
                ctrl.ultima_stare_releu = rez['releu']
            if rez.get('semnal') is not None:
                date['context']['semnal'] = rez['semnal']
        elif rez.get('semnal') is not None:
            date['semnal'] = rez['semnal']
        self._dosar = rez.get('dosar') or '/tmp'
        self._arata(date)

    def _nume_serviciu(self):
        try:
            s = self.sesiune.nav.getCurrentService()
            info = s and s.info()
            return info.getName() if info else None
        except Exception:
            return None

    def _transponder_serviciu(self):
        from . import scanare
        tp = scanare.transponder_curent(self.sesiune)
        if tp:
            tp.pop('feeduri', None)
            tp.pop('id', None)
        return tp

    @staticmethod
    def _semnal_serviciu():
        """In fundal: primul frontend de satelit prins."""
        for f in range(4):
            cale = '/dev/dvb/adapter0/frontend%d' % f
            if os.path.exists(cale) and tuner.e_satelit(cale):
                m = tuner.citeste_semnal(cale)
                if m.get('lock'):
                    return m
        return {}

    def _arata(self, date):
        self._date = date
        lista, semnal, calitate = campuri(date)
        if self.fereastra is None:
            from .ecrane import EcranOsd
            self.fereastra = self.sesiune.instantiateDialog(EcranOsd)
        self.fereastra.seteaza(_(TITLU), lista, semnal, calitate)
        self.fereastra.show()
        cfg = configureaza()
        dosar = getattr(self, '_dosar', None) or '/tmp'
        self._nume = os.path.join(dosar, 'hdsatelit-%s' % time.strftime('%Y%m%d-%H%M%S'))
        latime = cfg.latime.value
        self._pasi = [('grab -j 92 -r %s %s.jpg' % (latime, self._nume), True),
                      ('grab -v -j 92 -r %s %s-brut.jpg' % (latime, self._nume), False)]
        from enigma import eTimer
        compat.deconecteaza_toate(self._conexiuni)
        self._timer = eTimer()
        self._conexiuni.append(compat.conecteaza_timer(self._timer, self._urmatorul_pas))
        self._timer.start(ASTEPTARE_OSD_MS, True)
        self._termen = eTimer()
        self._conexiuni.append(compat.conecteaza_timer(self._termen,
                                                       lambda: self._termina(_('Programul grab nu a raspuns.'))))
        self._termen.start(TERMEN_GRAB_S * 1000, True)

    def _urmatorul_pas(self):
        try:
            if not self._pasi:
                self._scrie_json()
                self._termina(_('Captura salvata: %s') % (self._nume + '.jpg'))
                return
            comanda, cu_osd = self._pasi.pop(0)
            if not cu_osd and self.fereastra is not None:
                self.fereastra.hide()
            from enigma import eConsoleAppContainer
            c = eConsoleAppContainer()
            # manier separat de al timerelor: la sfarsitul unui pas se desface doar legatura containerului
            self._legatura_grab = compat.conecteaza(c.appClosed, self._pas_gata)
            self._container = c
            if c.execute(comanda):
                self._termina(_('Programul grab lipseste pe acest receptor.'))
        except Exception:
            jurnal.eroare('captura', 'pas')
            self._termina(_('Captura nu a mers. Vezi /tmp/hdsdabt2.log.'))

    def _pas_gata(self, cod=None):
        self._container = None
        self._legatura_grab = compat.deconecteaza(self._legatura_grab)
        self._urmatorul_pas()

    def _scrie_json(self):
        try:
            date = dict(self._date or {})
            date['camp_text'], date['semnal_la_suta'], date['calitate_la_suta'] = campuri(date)
            date['titlu'] = _(TITLU)
            # martorul imaginii e latimea din info-ul serviciului, nu poza: grab poate iesi negru pe HiSilicon
            latime = (date.get('context') or {}).get('latime_video', date.get('latime_video', -1))
            date['imagine_confirmata'] = isinstance(latime, int) and latime > 0
            if not date['imagine_confirmata']:
                jurnal.noteaza('captura', 'latimea video e %s: cadrul poate fi negru' % latime)
            buchete.scrie_atomic(self._nume + '.json', _json_utf8(date))
        except Exception:
            jurnal.eroare('captura', 'json')

    def _termina(self, mesaj):
        for t in (self._timer, self._termen):
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
        self._timer = self._termen = None
        compat.deconecteaza_toate(self._conexiuni)
        self._legatura_grab = compat.deconecteaza(self._legatura_grab)
        c, self._container = self._container, None
        if c is not None:
            try:
                if c.running():
                    c.kill()
            except Exception:
                pass
        try:
            if self.fereastra is not None:
                self.fereastra.hide()
        except Exception:
            pass
        self._pasi = []
        was = self.in_lucru
        self.in_lucru = False
        if was:
            jurnal.noteaza('captura', mesaj)
            try:
                from Tools.Notifications import AddPopup
                from Screens.MessageBox import MessageBox
                AddPopup(mesaj, MessageBox.TYPE_INFO, 6, 'hdscaptura')
            except Exception:
                pass


def _json_utf8(date):
    """dict -> octeti JSON in UTF-8, pe Python 3 si pe 2.7. Pe 2.7 textele traduse vin ca octeti UTF-8 si
    json.dumps(ensure_ascii=False) nu le poate amesteca cu unicode; atunci iese JSON cu \\u (tot valid)."""
    try:
        text = json.dumps(date, ensure_ascii=False, indent=1, default=str)
        return text if isinstance(text, bytes) else text.encode('utf-8')
    except UnicodeError:
        text = json.dumps(date, indent=1, default=str)
        return text if isinstance(text, bytes) else text.encode('ascii')


def _aduna_in_fundal(url, slot, fara_controlor, dosar_ales):
    """Firul de fundal al capturii: citiri de retea, ioctl si disc. -> dict. Nu atinge enigma2."""
    rez = {}
    if url:
        try:
            # fara conexiune tinuta: captura poate fi a celuilalt plugin, iar rezerva ei nu o inchide nimeni
            rez['releu'] = fundal.cere_json(url, tine=False)
        except Exception as e:
            rez['releu_eroare'] = '%s' % e
    try:
        if slot is not None:
            rez['semnal'] = tuner.citeste_semnal(tuner.cale_frontend(slot))
        elif fara_controlor:
            rez['semnal'] = Captura._semnal_serviciu()
    except Exception:
        pass
    rez['dosar'] = dosar_capturi(dosar_ales)
    return rez


def obtine(coord):
    """Obiectul de captura unic al procesului (tinut de coordonator)."""
    if coord.captura is None:
        coord.captura = Captura(coord)
    return coord.captura


def latime_serviciu(sesiune):
    """Latimea video a serviciului curent (martorul imaginii), -1 daca nu se stie."""
    try:
        from enigma import iServiceInformation
        s = sesiune.nav.getCurrentService()
        info = s and s.info()
        return int(info.getInfo(iServiceInformation.sVideoWidth)) if info else -1
    except Exception:
        return -1


def video_asteptat(sesiune):
    """True daca serviciul curent ar trebui sa aiba imagine (are PID video)."""
    try:
        from enigma import iServiceInformation
        s = sesiune.nav.getCurrentService()
        info = s and s.info()
        return bool(info) and int(info.getInfo(iServiceInformation.sVideoPID)) > 0
    except Exception:
        return False

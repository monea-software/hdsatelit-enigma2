# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Munca blocanta (retea, fisiere mari) mutata din firul principal al enigma2. Facut de hdsatelit.com.

Functia ruleaza intr-un fir separat; rezultatul se pune intr-o coada, iar un eTimer din firul principal il
scoate si cheama callback-ul acolo. Asa callback-ul poate atinge ecrane si enigma2 fara griji.
Timerul merge doar cat exista lucrari in curs (nu consuma nimic in rest).
Firul se porneste cu _thread.start_new_thread, care NU asteapta ca firul nou sa porneasca (threading.Thread.start
asteapta, iar daca alt fir tine GIL-ul blocat, firul principal ar sta si el).
"""
import collections
import json
import threading

try:
    import _thread as _fire_joase
except ImportError:                   # Python 2.7
    import thread as _fire_joase

from . import compat, jurnal

PAS_MS = 100
LIMITA_JSON = 512 * 1024
_THREAD_REAL = threading.Thread


def _porneste_fir(tinta):
    """Porneste tinta() intr-un fir nou, fara asteptare. Probele pot inlocui modulul threading (fir sincron)."""
    if getattr(threading, 'Thread', None) is not _THREAD_REAL:
        t = threading.Thread(target=tinta, name='hds-fundal')
        t.daemon = True
        t.start()
        return
    _fire_joase.start_new_thread(tinta, ())


class Fundal(object):

    def __init__(self, eticheta):
        self.et = eticheta
        self._coada = collections.deque()
        self._zavor = threading.Lock()
        self._in_curs = 0
        self._timer = None
        self._legatura = None         # manierul legaturii timerului (semnale-obiect: tinut cat traieste timerul)
        self._generatie = 0

    def in_curs(self):
        return self._in_curs

    def lanseaza(self, functie, la_gata, *args):
        """functie(*args) in fir; la_gata(ok, rezultat_sau_mesaj) in firul principal."""
        self._in_curs += 1
        gen = self._generatie

        def lucru():
            try:
                rez = (True, functie(*args))
            except Exception as e:
                rez = (False, '%s: %s' % (e.__class__.__name__, e))
            with self._zavor:
                self._coada.append((gen, la_gata, rez))

        try:
            _porneste_fir(lucru)
        except Exception:
            self._in_curs -= 1
            jurnal.eroare(self.et, 'pornirea firului')
            return False
        self._porneste_timer()
        return True

    def _porneste_timer(self):
        if self._timer is None:
            from enigma import eTimer
            self._timer = eTimer()
            self._legatura = compat.conecteaza_timer(self._timer, self._goleste)
        self._timer.start(PAS_MS, False)

    def _goleste(self):
        while True:
            with self._zavor:
                if not self._coada:
                    break
                gen, la_gata, (ok, rez) = self._coada.popleft()
            if gen != self._generatie:
                continue
            self._in_curs -= 1
            if la_gata is not None:
                try:
                    la_gata(ok, rez)
                except Exception:
                    jurnal.eroare(self.et, 'callback din fundal')
        if self._in_curs <= 0:
            self._in_curs = 0
            try:
                self._timer.stop()
            except Exception:
                pass

    def opreste(self):
        """Rezultatele care inca vin se arunca (callback-urile nu mai sunt chemate)."""
        with self._zavor:
            self._coada.clear()
            self._generatie += 1
            self._in_curs = 0
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass


# Conexiunile tinute spre releele locale. 0.1.4 (CLOSE_WAIT ramas in enigma2 spre 8890): o
# conexiune libera ramasa in rezerva dupa ce releul s-a oprit nu o mai inchidea nimeni. Acum:
#  - inchide_conexiunile(port) se cheama la oprirea releului, la tinere si la repornirea lui (pornire.Controlor);
#  - o cerere pornita inainte de inchidere nu isi mai pune conexiunea in rezerva (epoca);
#  - la refolosire, o conexiune pe care releul a inchis-o (socket citibil = sfarsit de flux) sau mai veche de
#    VARSTA_MAX_S se inchide si se face alta;
#  - cere_json(tine=False) cere Connection: close si inchide dupa raspuns (captura, rara, din alt plugin).
_CONEXIUNI = {}                       # (gazda, port) -> (conexiune HTTP tinuta, libera; momentul eliberarii)
_ZAVOR_CONEXIUNI = threading.Lock()
_EPOCA = [0]
CONEXIUNI_MAX = 4
VARSTA_MAX_S = 20.0                   # sub TERMEN_TINUT_S (30 s) al releului: nu refolosim ce e pe cale sa inchida


def _monoton():
    from . import compat
    return compat.monoton()


def _inchide(c):
    if c is None:
        return
    try:
        c.close()
    except Exception:
        pass


def _inchisa_de_celalalt(c):
    """Conexiunea libera are ceva de citit? Pe o conexiune tinuta, intre cereri, asta inseamna ca releul a inchis-o
    (sfarsit de flux) sau a trimis ceva nepotrivit: oricum nu se mai refoloseste. Nu asteapta (select cu 0)."""
    try:
        import select
        s = c.sock
        if s is None:
            return True
        r, _, _ = select.select([s], [], [], 0)
        return bool(r)
    except Exception:
        return True


def _conexiune_noua(gazda, port, timp):
    try:
        from http.client import HTTPConnection
    except ImportError:               # Python 2.7
        from httplib import HTTPConnection
    return HTTPConnection(gazda, port, timeout=timp)


def _desparte_url(url):
    if not url.startswith('http://'):
        raise ValueError('doar http://')
    rest = url[7:]
    gazda_port, _, cale = rest.partition('/')
    gazda, _, port = gazda_port.partition(':')
    return gazda, int(port or 80), '/' + cale


def _ia_din_rezerva(cheie):
    with _ZAVOR_CONEXIUNI:
        intrare = _CONEXIUNI.pop(cheie, None)
    if intrare is None:
        return None
    c, liber_la = intrare
    if _monoton() - liber_la > VARSTA_MAX_S or _inchisa_de_celalalt(c):
        _inchide(c)
        return None
    return c


def cere_json(url, timp=1.5, limita=LIMITA_JSON, tine=True):
    """GET blocant catre releul local. Doar din fir separat. Fara proxy (adresa e 127.0.0.1).
    tine=True: pe o conexiune tinuta (una libera pe gazda:port, refolosita de urmatoarea cerere); o conexiune
    inchisa de releu intre timp se reface o data. tine=False: Connection: close, socketul se inchide dupa raspuns.
    Cod diferit de 200 sau raspuns prea mare -> exceptie (ca inainte). Socketul se inchide pe orice drum in afara de
    cel in care intra, viu si curat, in rezerva."""
    gazda, port, cale = _desparte_url(url)
    cheie = (gazda, port)
    epoca = _EPOCA[0]
    c = _ia_din_rezerva(cheie) if tine else None
    antet = {'Connection': 'keep-alive' if tine else 'close', 'User-Agent': 'hdsatelit-plugin'}
    for incercare in (0, 1):
        refolosita = c is not None
        if c is None:
            c = _conexiune_noua(gazda, port, timp)
        else:
            try:
                if c.sock is not None:
                    c.sock.settimeout(timp)
            except Exception:
                pass
        try:
            c.request('GET', cale, headers=antet)
            r = c.getresponse()
            date = r.read(limita + 1)
            inchide = bool(getattr(r, 'will_close', True))
            cod = r.status
        except Exception:
            _inchide(c)
            c = None
            if refolosita and incercare == 0:
                continue                  # releul a inchis conexiunea tinuta intre timp: una noua
            raise
        try:
            if tine and not inchide and len(date) <= limita and cod == 200:
                with _ZAVOR_CONEXIUNI:
                    if (epoca == _EPOCA[0] and cheie not in _CONEXIUNI and len(_CONEXIUNI) < CONEXIUNI_MAX):
                        _CONEXIUNI[cheie] = (c, _monoton())
                        c = None
        finally:
            _inchide(c)
        if cod != 200:
            raise IOError('HTTP %d' % cod)
        if len(date) > limita:
            raise ValueError('raspuns prea mare')
        return json.loads(date.decode('utf-8'))
    raise IOError('fara raspuns')


def inchide_conexiunile(port=None):
    """Inchide conexiunile libere (toate, sau doar spre `port`). Cererile aflate in curs nu le mai pun inapoi in
    rezerva. Nu asteapta nimic (close pe un socket local), deci merge si din firul principal."""
    with _ZAVOR_CONEXIUNI:
        _EPOCA[0] += 1
        chei = [k for k in _CONEXIUNI if port is None or k[1] == port]
        vechi = [_CONEXIUNI.pop(k)[0] for k in chei]
    for c in vechi:
        _inchide(c)
    return len(vechi)


def conexiuni_libere():
    """Cate conexiuni stau in rezerva (probe, jurnal)."""
    with _ZAVOR_CONEXIUNI:
        return len(_CONEXIUNI)

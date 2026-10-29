# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Listele de frecvente pentru HdsDab (tip 'dab') si HdsT2mi (tip 't2'). Facut de hdsatelit.com.

Surse, in ordinea prioritatii (prima castiga la aceeasi cheie):
    manual     /etc/enigma2/<plugin>/manual.json      scris de utilizator
    scanat     /etc/enigma2/<plugin>/scanate.json     scris dupa detector
    descarcat  /etc/enigma2/<plugin>/frecvente.json   actualizat de pe stb.hdsatelit.com
    incorporat <plugin>/date/frecvente.json           venit cu pachetul
Alaturi de lista se descarca servicii.json (posturile invatate pe receptorul de proba, pe feed-uri), scris in
/etc/enigma2/<plugin>/servicii-stb.json: buchete.py il foloseste numai pentru feed-urile pe care receptorul le prinde
si numai unde receptorul n-a invatat el insusi posturile.

Adresele: https://stb.hdsatelit.com/receptor/{dab,t2mi}/ (URL_IMPLICIT); daca stb nu da o lista buna, adresa veche de
pe www.hdsatelit.com (URL_REZERVA), care trimite tot spre stb. Descarcarea zilnica (Zilnic) merge numai cu setarea
„Ia listele DAB+ si DVB-T2 de pe stb.hdsatelit.com in fiecare zi” pornita (config.plugins.hdscomun.liste_zilnic,
oprita din fabrica); butonul „Actualizeaza lista” descarca oricand, de mana.
Toate au acelasi format (versiune, actualizat, transpondere[feeduri]).

Cheia unui feed: pozitie + frecventa (toleranta 2 MHz) + pol + is_id + pid + ip + port (dab edi) sau plp (t2).
is_id intra in cheie: pe 5.0W acelasi 12564 V poarta doua fluxuri multistream diferite.

Descarcarea (descarca) e blocanta si trebuie chemata din fir separat sau din procesul motorului, niciodata din
firul principal enigma2. Nu arunca exceptii: intoarce (ok, mesaj).

Verificarea descarcarii:
  - HTTPS cu certificatul verificat (contextul implicit ssl), timeout 10 s, cel mult 1 MB, JSON valid,
    versiune de format cunoscuta, fiecare transponder si feed verificat; intrarile rele se sar, fisierul fara
    niciun feed bun se respinge; scriere atomica (fisier temporar + fsync + os.replace).
  - Suma sha256 publicata alaturi (<url>.sha256, 64 de caractere hex). Mod 'obligatoriu' (implicit: stb publica
    mereu suma): fara ea nu se primeste lista; 'daca_exista': daca fisierul .sha256 exista trebuie sa se potriveasca;
    'nu'.
    De ce doar sha256: prinde fisierele taiate, stricate pe drum sau o memorie tampon veche care da lista noua
    cu suma veche (sau invers). NU apara de cineva care controleaza serverul, fiindca ar schimba ambele fisiere.
    O semnatura adevarata (Ed25519) cere o biblioteca straina pe receptor, iar un HMAC cu cheie in plugin nu
    apara nimic (cheia e publica in pachet). HTTPS verificat acopera drumul; sha256 acopera integritatea.
"""
import errno
import hashlib
import json
import os
import sys
import tempfile

try:
    from . import compat                 # din pachetul comun (enigma2)
except (ImportError, ValueError):
    import compat                        # rulat ca modul de sine statator (detector, probe)

TIPURI = ('dab', 't2')
FORMAT_MAX = 1
MARIME_MAX = 1024 * 1024
TIMP_DESCARCARE = 10.0
TOLERANTA_KHZ = 2000

URL_IMPLICIT = {'dab': 'https://stb.hdsatelit.com/receptor/dab/frecvente.json',
                't2': 'https://stb.hdsatelit.com/receptor/t2mi/frecvente.json'}
# adresa de pana la 0.2.1; situl o trimite spre stb (301), deci ramane buna daca stb nu se poate atinge direct
URL_REZERVA = {'dab': 'https://www.hdsatelit.com/receptor/dab/frecvente.json',
               't2': 'https://www.hdsatelit.com/receptor/t2mi/frecvente.json'}
MARIME_SERVICII_MAX = 2 * 1024 * 1024
FISIER_SERVICII_STB = 'servicii-stb.json'          # acelasi nume ca buchete.FISIER_SERVICII_STB
DIR_IMPLICIT = {'dab': '/etc/enigma2/hdsdab', 't2': '/etc/enigma2/hdst2mi'}
# t2: t2mi (DVB-T2 prin T2-MI) si abertis (un TS terestru intreg in payload-ul unui PID privat, fara T2-MI: fluxurile
# de distributie spaniole de pe 30W; desfacut de t2mi_decap -A)
FEL = {'dab': ('edi', 'ts2na', 'ts2na12', 'tsniv2ni'), 't2': ('t2mi', 'abertis')}
PRIORITATE = ('manual', 'scanat', 'descarcat', 'incorporat')
FISIER = {'manual': 'manual.json', 'scanat': 'scanate.json', 'descarcat': 'frecvente.json'}
POLARIZARI = ('H', 'V', 'L', 'R')


def _jurnal(msg):
    try:
        with open('/tmp/hdsdabt2.log', 'a') as f:
            f.write('liste: %s\n' % msg)
    except Exception:
        pass


def _int(v, mn, mx):
    return isinstance(v, int) and not isinstance(v, bool) and mn <= v <= mx


def _nativ(x):
    """JSON adus la textul nativ al fiecarui Python (pe 2.7 json da unicode; enigma2 si gettext folosesc octeti UTF-8,
    iar amestecul da UnicodeDecodeError). Pe Python 3 nu schimba nimic."""
    if isinstance(x, dict):
        return dict((_nativ(k), _nativ(v)) for k, v in x.items())
    if isinstance(x, list):
        return [_nativ(v) for v in x]
    return compat.text_nativ(x)


def _ip_ok(ip):
    if not compat.e_text(ip) or len(ip) > 45:
        return False
    p = ip.split('.')
    if len(p) == 4:
        return all(x.isdigit() and len(x) <= 3 and int(x) <= 255 for x in p)
    return ':' in ip and all(c in '0123456789abcdefABCDEF:' for c in ip)


def _text(v, n=120):
    return compat.e_text(v) and len(v) <= n


# ---------------------------------------------------------------- verificare
def verifica_feed(f, tip=None):
    if not isinstance(f, dict):
        return None
    t = f.get('tip')
    if t not in TIPURI or (tip and t != tip):
        return None
    if f.get('fel') not in FEL[t] or not _int(f.get('pid'), 0, 8191):
        return None
    if not _text(f.get('id'), 80) or not f['id'] or not _text(f.get('nume', ''), 120):
        return None
    if f['fel'] == 'edi' and not (_ip_ok(f.get('ip')) and _int(f.get('port'), 1, 65535)):
        return None
    if t == 't2' and f.get('plp') is not None and not _int(f.get('plp'), 0, 255):
        return None
    return f


def verifica_transponder(t, tip=None):
    """-> transponder curatat (doar feed-urile bune de tipul cerut) sau None."""
    if not isinstance(t, dict):
        return None
    if not (_int(t.get('pozitie'), 0, 3599) and _int(t.get('frecventa'), 2000000, 40000000)
            and t.get('pol') in POLARIZARI and _int(t.get('sr'), 100000, 100000000)):
        return None
    if t.get('is_id') is not None and not _int(t.get('is_id'), 0, 255):
        return None
    if t.get('pls_cod') is not None and not _int(t.get('pls_cod'), 0, 262143):
        return None
    if t.get('pls_mod') not in (None, 'root', 'gold', 'combo'):
        return None
    if t.get('sistem', 'DVB-S') not in ('DVB-S', 'DVB-S2', 'DVB-S2X'):
        return None
    feeduri = t.get('feeduri')
    if not isinstance(feeduri, list):
        return None
    bune = [f for f in feeduri if verifica_feed(f, tip)]
    if not bune:
        return None
    c = dict(t)
    c['feeduri'] = bune
    return c


def verifica_lista(date, tip=None):
    """-> (lista curatata sau None, mesaj)."""
    if not isinstance(date, dict):
        return None, 'nu e obiect JSON'
    v = date.get('versiune')
    if not _int(v, 1, 1000000):
        return None, 'lipseste versiunea'
    if v > FORMAT_MAX:
        return None, 'format %d necunoscut (stiu pana la %d)' % (v, FORMAT_MAX)
    tp = date.get('transpondere')
    if not isinstance(tp, list):
        return None, 'lipsesc transponderele'
    bune = [x for x in (verifica_transponder(t, tip) for t in tp) if x]
    n_total = sum(len(t.get('feeduri') or []) for t in tp if isinstance(t, dict) and isinstance(t.get('feeduri'), list))
    n_bune = sum(len(t['feeduri']) for t in bune)
    act = date.get('actualizat') if _text(date.get('actualizat'), 32) else ''
    return ({'versiune': v, 'actualizat': act, 'transpondere': bune},
            '%d feed-uri bune din %d' % (n_bune, n_total))


# ---------------------------------------------------------------- fisiere
def citeste_json(cale, tip=None):
    """Citeste si verifica o lista locala; fisier lipsa sau stricat -> None (se scrie in jurnal)."""
    try:
        if os.path.getsize(cale) > MARIME_MAX:
            _jurnal('%s prea mare' % cale)
            return None
        with open(cale, 'rb') as f:
            date = _nativ(json.loads(f.read().decode('utf-8')))
    except (IOError, OSError) as e:           # FileNotFoundError nu exista pe Python 2.7
        if getattr(e, 'errno', None) != errno.ENOENT:
            _jurnal('%s stricat: %s' % (cale, e))
        return None
    except (ValueError, UnicodeDecodeError) as e:
        _jurnal('%s stricat: %s' % (cale, e))
        return None
    lista, msg = verifica_lista(date, tip)
    if lista is None:
        _jurnal('%s respins: %s' % (cale, msg))
    return lista


def scrie_atomic(cale, octeti):
    d = os.path.dirname(cale) or '.'
    if not os.path.isdir(d):                  # exist_ok nu exista pe Python 2.7
        try:
            os.makedirs(d)
        except OSError:
            if not os.path.isdir(d):
                raise
    fd, tmp = tempfile.mkstemp(prefix='.tmp_', dir=d)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(octeti)
            f.flush()
            os.fsync(f.fileno())
        compat.inlocuieste(tmp, cale)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def salveaza_lista(cale, lista):
    if sys.version_info[0] < 3:
        # pe 2.7 textele sunt octeti UTF-8: iesirea ASCII (cu \\u) evita amestecul octeti / unicode; JSON-ul e acelasi
        text = json.dumps(lista, ensure_ascii=True, indent=1) + '\n'
        scrie_atomic(cale, text if isinstance(text, bytes) else text.encode('utf-8'))
    else:
        scrie_atomic(cale, (json.dumps(lista, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))


def cale_incorporata(tip):
    """Lista venita cu codul. Ca plugin pe alte imagini: Extensions/<plugin>/date/frecvente.json (modulul comun sta
    in Plugins/SystemPlugins/HdsComun, deci la ../../Extensions/<plugin>/date). In imaginea HDSatelit: langa modul,
    in <tip>/date (Hds/DabT2/dab/date, Hds/DabT2/t2/date). Se cauta si langa modul si un nivel mai sus (asezarea
    veche, comun copiat in plugin sau in motor/), apoi in sursele de pe PC."""
    aici = os.path.dirname(os.path.abspath(__file__))
    nume = {'dab': 'HdsDab', 't2': 'HdsT2mi'}[tip]
    for c in (os.path.join(aici, '..', '..', 'Extensions', nume, 'date', 'frecvente.json'),
              os.path.join(aici, tip, 'date', 'frecvente.json'),
              os.path.join(aici, 'date', 'frecvente.json'), os.path.join(aici, '..', 'date', 'frecvente.json')):
        if os.path.isfile(c):
            return os.path.normpath(c)
    return os.path.normpath(os.path.join(aici, '..', 'plugin', nume, 'date', 'frecvente.json'))


# ---------------------------------------------------------------- descarcare
# 0.2.5: textul ultimei descarcari cazute din cauza ceasului receptorului (Components/HdsCeasHttps.py), pentru mesajul de
# pe televizor si din web (ecrane.text_actualizare_esuata); se goleste la fiecare actualizeaza()
_ULTIMA_EROARE_CEAS = [None]


def _mesaj_ceas(e):
    """Textul comun „ceasul e în urmă” cand certificatul cade din cauza ceasului, altfel None. In afara imaginii
    (pluginul pe alta imagine, detectorul) modulul lipseste: None, mesajul obisnuit."""
    try:
        from Components import HdsCeasHttps
    except ImportError:
        return None
    try:
        text = HdsCeasHttps.mesaj(e)
    except Exception:
        return None
    if text and _ULTIMA_EROARE_CEAS[0] is None:
        _ULTIMA_EROARE_CEAS[0] = text        # primul din actualizare (cu „Ora se sincronizează acum...”, cand e cazul)
    return text


def ultima_eroare_ceas():
    """Textul „ceasul e în urmă” al ultimei actualizari, sau None."""
    return _ULTIMA_EROARE_CEAS[0]


def _citeste_url(url, timp, limita):
    try:
        from urllib.request import Request, urlopen
    except ImportError:               # Python 2.7
        from urllib2 import Request, urlopen
    cerere = Request(url, headers={'User-Agent': 'hdsatelit-receptor/1', 'Accept-Encoding': 'identity'})
    r = urlopen(cerere, timeout=timp)
    try:                              # pe Python 2.7 raspunsul nu e manager de context: se inchide explicit
        antete = getattr(r, 'headers', None) or r.info()
        lung = antete.get('Content-Length')
        if lung and lung.isdigit() and int(lung) > limita:
            raise ValueError('prea mare (%s octeti)' % lung)
        date = r.read(limita + 1)
    finally:
        r.close()
    if len(date) > limita:
        raise ValueError('prea mare (peste %d octeti)' % limita)
    if lung and lung.isdigit() and int(lung) != len(date):
        raise ValueError('taiat pe drum (%d din %s octeti)' % (len(date), lung))
    return date


def _cu_suma(url, timp, limita, sha256, citeste_url):
    """Corpul de la url, verificat cu <url>.sha256 dupa modul sha256. -> (corp, None) sau (None, mesaj)."""
    try:
        corp = citeste_url(url, timp, limita)
    except Exception as e:
        ceas = _mesaj_ceas(e)
        if ceas:
            return None, ceas
        return None, 'descarcare esuata: %s' % (e.__class__.__name__ if not str(e) else e)
    if sha256 != 'nu':
        try:
            suma = citeste_url(url + '.sha256', timp, 512)
            suma = suma.decode('ascii', 'replace').strip().split()[0].lower() if suma.strip() else ''
        except Exception:
            suma = None
        if suma is None:
            if sha256 == 'obligatoriu':
                return None, 'lipseste suma sha256'
        elif len(suma) != 64 or any(c not in '0123456789abcdef' for c in suma):
            return None, 'suma sha256 publicata nu e valida'
        elif hashlib.sha256(corp).hexdigest() != suma:
            return None, 'suma sha256 nu se potriveste'
    return corp, None


def descarca(tip, url=None, director=None, timp=TIMP_DESCARCARE, sha256='obligatoriu', citeste_url=None):
    """Descarca lista si o scrie atomic in <director>/frecvente.json. -> (ok, mesaj). Blocant: fir separat.
    Fara url: intai stb.hdsatelit.com, apoi adresa veche de pe www (daca stb nu da o lista buna)."""
    if tip not in TIPURI:
        return False, 'tip necunoscut'
    if url is None:
        ok, mesaj = descarca(tip, URL_IMPLICIT[tip], director, timp, sha256, citeste_url)
        if ok:
            return ok, mesaj
        ok2, mesaj2 = descarca(tip, URL_REZERVA[tip], director, timp, sha256, citeste_url)
        return (ok2, mesaj2) if ok2 else (False, mesaj)
    director = director or DIR_IMPLICIT[tip]
    citeste_url = citeste_url or _citeste_url
    corp, eroare = _cu_suma(url, timp, MARIME_MAX, sha256, citeste_url)
    if corp is None:
        return False, eroare
    try:
        date = _nativ(json.loads(corp.decode('utf-8')))
    except (ValueError, UnicodeDecodeError):
        return False, 'JSON stricat'
    lista, msg = verifica_lista(date, tip)
    if lista is None:
        return False, 'lista respinsa: %s' % msg
    if not lista['transpondere']:
        return False, 'lista fara niciun feed bun (%s)' % msg
    try:
        salveaza_lista(os.path.join(director, FISIER['descarcat']), lista)
    except (IOError, OSError) as e:
        return False, 'scriere esuata: %s' % e
    return True, 'lista din %s: %s' % (lista['actualizat'] or '?', msg)


def url_servicii(url_frecvente):
    """servicii.json sta langa frecvente.json, in acelasi dosar de pe server."""
    return url_frecvente.rsplit('/', 1)[0] + '/servicii.json'


def verifica_servicii(date, tip):
    """servicii.json publicat -> (dictionarul feed-urilor curatat sau None, mesaj). Formatul: {versiune 1, tip,
    actualizat, feeduri: {id: {actualizat, servicii: [...], cheie: {...}}}}; feed-urile fara servicii se sar."""
    if not isinstance(date, dict) or not _int(date.get('versiune'), 1, FORMAT_MAX):
        return None, 'format necunoscut'
    if date.get('tip') != tip:
        return None, 'alt tip (%s)' % date.get('tip')
    feeduri = date.get('feeduri')
    if not isinstance(feeduri, dict):
        return None, 'lipsesc feed-urile'
    bune = {}
    for fid, d in feeduri.items():
        if not (_text(fid, 80) and fid and isinstance(d, dict) and isinstance(d.get('servicii'), list)
                and d['servicii'] and isinstance(d.get('cheie', {}), dict)):
            continue
        servicii = [s for s in d['servicii'] if isinstance(s, dict) and _int(s.get('sid'), 1, 0xFFFF)
                    and _text(s.get('nume', ''), 120)][:500]
        if servicii:
            bune[fid] = {'actualizat': d.get('actualizat') if _text(d.get('actualizat'), 32) else '',
                         'servicii': servicii, 'cheie': d.get('cheie') or {}}
    return bune, '%d feed-uri cu posturi din %d' % (len(bune), len(feeduri))


def descarca_servicii(tip, url_frecvente=None, director=None, timp=TIMP_DESCARCARE, sha256='obligatoriu',
                      citeste_url=None):
    """servicii.json de langa lista (posturile publicate), scris atomic in <director>/servicii-stb.json.
    -> (ok, mesaj). Blocant: fir separat. Fara url: stb, apoi adresa veche."""
    if tip not in TIPURI:
        return False, 'tip necunoscut'
    if url_frecvente is None:
        ok, mesaj = descarca_servicii(tip, URL_IMPLICIT[tip], director, timp, sha256, citeste_url)
        if ok:
            return ok, mesaj
        ok2, mesaj2 = descarca_servicii(tip, URL_REZERVA[tip], director, timp, sha256, citeste_url)
        return (ok2, mesaj2) if ok2 else (False, mesaj)
    director = director or DIR_IMPLICIT[tip]
    corp, eroare = _cu_suma(url_servicii(url_frecvente), timp, MARIME_SERVICII_MAX, sha256,
                            citeste_url or _citeste_url)
    if corp is None:
        return False, 'posturile: %s' % eroare
    try:
        date = _nativ(json.loads(corp.decode('utf-8')))
    except (ValueError, UnicodeDecodeError):
        return False, 'posturile: JSON stricat'
    feeduri, msg = verifica_servicii(date, tip)
    if feeduri is None:
        return False, 'posturile respinse: %s' % msg
    act = date.get('actualizat') if _text(date.get('actualizat'), 32) else ''
    try:
        salveaza_lista(os.path.join(director, FISIER_SERVICII_STB),
                       {'versiune': 1, 'tip': tip, 'actualizat': act, 'feeduri': feeduri})
    except (IOError, OSError) as e:
        return False, 'posturile: scriere esuata: %s' % e
    return True, 'posturile: %s' % msg


def actualizeaza(tip, director=None, citeste_url=None):
    """Lista si posturile publicate, cu sha256 obligatoriu. -> (ok, mesaj); ok = lista a venit (posturile pot lipsi,
    mesajul o spune). Blocant: fir separat."""
    _ULTIMA_EROARE_CEAS[0] = None
    ok, mesaj = descarca(tip, None, director, citeste_url=citeste_url)
    if not ok:
        return False, mesaj
    ok_s, mesaj_s = descarca_servicii(tip, None, director, citeste_url=citeste_url)
    return True, '%s; %s' % (mesaj, mesaj_s if ok_s else 'posturile nu au venit (%s)' % mesaj_s)


# ---------------------------------------------------------------- descarcarea zilnica
STARE_ZILNIC = '/etc/enigma2/hdsdab/liste-zilnic.json'
PRIMA_VERIFICARE_S = 300        # dupa pornire, prima privire la ceas (pornirea receptorului are destula treaba)
PAS_ZILNIC_S = 1800
INTERVAL_ZILNIC_S = 24 * 3600
REINCERCARE_ZILNIC_S = 3 * 3600  # dupa o descarcare cazuta (fara retea, stb oprit)


def zilnic_activ():
    """Setarea „Ia listele DAB+ si DVB-T2 de pe stb.hdsatelit.com in fiecare zi” (oprita din fabrica)."""
    try:
        from . import captura
        return bool(captura.configureaza().liste_zilnic.value)
    except Exception:
        return False


def citeste_stare_zilnic(cale=None):
    """{'la': secunde, 'ok': bool, 'mesaj': text} al ultimei descarcari zilnice, sau {}."""
    try:
        with open(cale or STARE_ZILNIC, 'rb') as f:
            d = json.loads(f.read(8192).decode('utf-8'))
        return d if isinstance(d, dict) and isinstance(d.get('la'), (int, float)) else {}
    except Exception:
        return {}


def e_timpul(stare, acum):
    """Descarcarea zilnica e de facut acum? Niciodata facuta; 24 de ore dupa una buna; 3 ore dupa una cazuta; sau
    ceasul a sarit inapoi fata de ultima descarcare (ora gresita de dinainte de NTP)."""
    la = stare.get('la') if stare else None
    if not isinstance(la, (int, float)):
        return True
    if acum < la:
        return True
    return acum - la >= (INTERVAL_ZILNIC_S if stare.get('ok') else REINCERCARE_ZILNIC_S)


def descarca_toate(directoare=None, citeste_url=None, cale_stare=None):
    """In fir: listele si posturile pentru DAB+ si DVB-T2, apoi starea scrisa. -> {tip: (ok, mesaj)}."""
    import time
    rez = {}
    for tip in TIPURI:
        try:
            rez[tip] = actualizeaza(tip, (directoare or {}).get(tip), citeste_url=citeste_url)
        except Exception as e:
            rez[tip] = (False, '%s: %s' % (e.__class__.__name__, e))
        _jurnal('zilnic %s: %s' % (tip, rez[tip][1]))
    ok = all(r[0] for r in rez.values())
    try:
        text = json.dumps({'la': int(time.time()), 'ok': ok, 'mesaj': '; '.join(
            '%s: %s' % (x, rez[x][1]) for x in TIPURI)[:900]}, ensure_ascii=True) + '\n'
        scrie_atomic(cale_stare or STARE_ZILNIC, text if isinstance(text, bytes) else text.encode('ascii'))
    except (IOError, OSError, ValueError):
        pass
    return rez


class Zilnic(object):
    """Descarcarea zilnica, o singura data pe proces (zilnic()). Un eTimer in firul principal se uita din PAS_ZILNIC_S
    in PAS_ZILNIC_S daca setarea e pornita si daca e timpul (e_timpul); descarcarea merge intr-un fir (fundal), iar
    listele noi ajung la controlori (lista citita din nou, buchetul refacut in fundal) in firul principal."""

    def __init__(self):
        self._timer = None
        self._legatura = None
        self._fundal = None
        self.descarcari = 0

    def porneste(self, prima_s=PRIMA_VERIFICARE_S):
        if self._timer is not None:
            return
        try:
            from enigma import eTimer
            self._timer = eTimer()
            self._legatura = compat.conecteaza_timer(self._timer, self._pas)
            self._timer.start(int(prima_s * 1000), True)
        except Exception:
            self._timer = None
            _jurnal('zilnic: timerul nu a pornit')

    def opreste(self):
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
        if self._fundal is not None:
            self._fundal.opreste()

    def _pas(self):
        try:
            self._timer.start(PAS_ZILNIC_S * 1000, True)
            if not zilnic_activ():
                return
            if self._fundal is None:
                from . import fundal
                self._fundal = fundal.Fundal('liste-zilnic')
            if self._fundal.in_curs():
                return
            import time
            if not e_timpul(citeste_stare_zilnic(), time.time()):
                return
            self.descarcari += 1
            self._fundal.lanseaza(descarca_toate, self._gata)
        except Exception:
            _jurnal('zilnic: pasul a cazut')

    def _gata(self, ok, rez):
        if not ok or not isinstance(rez, dict):
            _jurnal('zilnic: %s' % rez)
            return
        try:
            from . import intrare
            for c in list(intrare._controlori.values()):
                r = rez.get(c.profil.tip)
                if r and r[0]:
                    c.reface_in_fundal()
        except Exception:
            _jurnal('zilnic: refacerea buchetelor')


_zilnic = []


def zilnic():
    """Descarcarea zilnica a procesului (aceeasi pentru DAB+ si DVB-T2)."""
    if not _zilnic:
        _zilnic.append(Zilnic())
    return _zilnic[0]


# ---------------------------------------------------------------- unire
def _cheie_feed(f):
    if f['tip'] == 't2':
        return (f['tip'], f['pid'], f.get('plp'))
    if f['fel'] == 'edi':
        return (f['tip'], f['pid'], f['ip'], f['port'])
    return (f['tip'], f['pid'], f['fel'])


def _acelasi_transponder(a, b):
    return (a['pozitie'] == b['pozitie'] and a['pol'] == b['pol'] and a.get('is_id') == b.get('is_id')
            and abs(a['frecventa'] - b['frecventa']) <= TOLERANTA_KHZ)


def uneste(liste):
    """liste: [(sursa, lista)] in ordinea prioritatii. -> lista unita, fiecare feed cu campul 'sursa'."""
    rez = []
    ids = set()
    for sursa, lista in liste:
        if not lista:
            continue
        for t in lista['transpondere']:
            tinta = next((x for x in rez if _acelasi_transponder(x, t)), None)
            if tinta is None:
                tinta = {k: v for k, v in t.items() if k != 'feeduri'}
                tinta['sursa'] = sursa
                tinta['feeduri'] = []
                rez.append(tinta)
            else:
                # campurile pe care sursa mai buna nu le are (de pilda fasciculul, scris numai in lista din pachet) se
                # iau din sursa urmatoare; ce are deja ramane neschimbat
                for k, v in t.items():
                    if k != 'feeduri' and k not in tinta:
                        tinta[k] = v
            chei = {_cheie_feed(f) for f in tinta['feeduri']}
            for f in t['feeduri']:
                k = _cheie_feed(f)
                if k in chei:
                    continue
                chei.add(k)
                g = dict(f)
                g['sursa'] = sursa
                baza, n = g['id'], 2
                while g['id'] in ids:
                    g['id'] = '%s_%d' % (baza, n)
                    n += 1
                ids.add(g['id'])
                tinta['feeduri'].append(g)
    return rez


def incarca(tip, director=None, incorporat=None):
    """Lista unita pentru un plugin. Nu arunca exceptii pentru fisiere lipsa sau stricate."""
    if tip not in TIPURI:
        raise ValueError('tip trebuie sa fie dab sau t2')
    director = director or DIR_IMPLICIT[tip]
    inc = citeste_json(incorporat or cale_incorporata(tip), tip)
    desc = citeste_json(os.path.join(director, FISIER['descarcat']), tip)
    if desc and inc and desc.get('actualizat', '') < inc.get('actualizat', ''):
        _jurnal('lista descarcata (%s) mai veche decat cea din pachet (%s), nu se foloseste'
                % (desc.get('actualizat'), inc.get('actualizat')))
        desc = None
    surse = [('manual', citeste_json(os.path.join(director, FISIER['manual']), tip)),
             ('scanat', citeste_json(os.path.join(director, FISIER['scanat']), tip)),
             ('descarcat', desc), ('incorporat', inc)]
    return {'versiune': 1, 'tip': tip, 'transpondere': uneste(surse),
            'surse': {s: bool(l) for s, l in surse}}


STARE_NEDECODABIL = 'nu_se_decodeaza'


def fara_nedecodabile(lista):
    """Lista fara feed-urile verificate ca „nu_se_decodeaza" (ascunse implicit in plugin; setarea le arata).
    Transponderele ramase fara feed-uri ies si ele. Nu schimba lista primita."""
    if not isinstance(lista, dict):
        return lista
    rez = dict((k, v) for k, v in lista.items() if k != 'transpondere')
    tp = []
    for t in lista.get('transpondere') or []:
        feeduri = [f for f in t.get('feeduri') or [] if f.get('stare_verificare') != STARE_NEDECODABIL]
        if feeduri:
            c = dict(t)
            c['feeduri'] = feeduri
            tp.append(c)
    rez['transpondere'] = tp
    return rez


def adauga_scanat(tip, transponder, feeduri, director=None):
    """Pune feed-urile confirmate de detector in scanate.json (unire, fara dubluri). -> numarul adaugat."""
    director = director or DIR_IMPLICIT[tip]
    cale = os.path.join(director, FISIER['scanat'])
    vechi = citeste_json(cale, tip) or {'versiune': 1, 'actualizat': '', 'transpondere': []}
    t = dict(transponder)
    t['feeduri'] = [{k: v for k, v in f.items() if k not in ('confirmat', 'motiv', 'program', 'cunoscut', 'sursa')}
                    for f in feeduri if f.get('confirmat', True)]
    nou, _ = verifica_lista({'versiune': 1, 'transpondere': [t]}, tip)
    if not nou or not nou['transpondere']:
        return 0
    inainte = sum(len(x['feeduri']) for x in vechi['transpondere'])
    unit = uneste([('scanat', vechi), ('scanat', nou)])
    for x in unit:
        x.pop('sursa', None)
        for f in x['feeduri']:
            f.pop('sursa', None)
    import time
    salveaza_lista(cale, {'versiune': 1, 'actualizat': time.strftime('%Y-%m-%d'), 'transpondere': unit})
    return sum(len(x['feeduri']) for x in unit) - inainte


def scoate_scanat(tip, feed_id, director=None):
    """Scoate din scanate.json feed-ul cu id-ul dat (un candidat pus acolo inaintea invatarii, care n-a dat nimic);
    transponderele ramase fara feed-uri ies si ele. Nu scrie nimic daca feed-ul nu e acolo. -> True daca a scris."""
    director = director or DIR_IMPLICIT[tip]
    cale = os.path.join(director, FISIER['scanat'])
    vechi = citeste_json(cale, tip)
    if not vechi:
        return False
    tp, scos = [], False
    for t in vechi['transpondere']:
        feeduri = [f for f in t['feeduri'] if f.get('id') != feed_id]
        scos = scos or len(feeduri) != len(t['feeduri'])
        if feeduri:
            c = dict(t)
            c['feeduri'] = feeduri
            tp.append(c)
    if not scos:
        return False
    salveaza_lista(cale, {'versiune': 1, 'actualizat': vechi.get('actualizat') or '', 'transpondere': tp})
    return True

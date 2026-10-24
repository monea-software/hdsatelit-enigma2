# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsDvbI — suport DVB-I integrat in imaginea HDSatelit.

DVB-I (ETSI TS 103 669): canale TV liniare livrate prin internet (HLS/DASH/TS).
Scris de la zero.

DVB-I: listele tarii alese din registrele DVB-I (Components/HdsDvbIRegistru, HdsDvbISetari), un singur
buchet TV "Canale de pe internet (DVB-I)" in ordinea LCN a regiunii (Components/HdsDvbILegare), mereu in lista;
adresele cu ':' codificat (%3a) si buchetele reincarcate (reloadBouquets); starea pentru lista de canale, bara,
trecerea pe internet si web (Components/HdsDvbIDate); canalele incercate din casa (Components/HdsDvbIIncercare) la
6 ore, la cerere si dupa schimbarea VPN-ului; la pornirea sesiunii, trecerea pe internet (Components/HdsDvbIRezerva).

Integrare:
  - Autostart la pornire Enigma2 (PluginDescriptor.WHERE_AUTOSTART)
  - NU apare in Plugin Browser (fara WHERE_PLUGINMENU)
  - Meniu: HDSatelit → Surse → DVB-I
  - Config: /etc/enigma2/hdsdvbi.conf
  - Bouquet generat: /etc/enigma2/userbouquet.hdsdvbi.tv
                     /etc/enigma2/userbouquet.hdsdvbi.radio
"""
from __future__ import absolute_import, unicode_literals
import os
import threading
import time
import xml.etree.ElementTree as ET

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import Request, urlopen, URLError, HTTPError

from Plugins.Plugin import PluginDescriptor

# ---------------------------------------------------------------- constante
VERSIUNE             = '0.1.0'
CALE_CONFIG          = '/etc/enigma2/hdsdvbi.conf'
CALE_BOUQUET_TV      = '/etc/enigma2/userbouquet.hdsdvbi.tv'
CALE_BOUQUET_RADIO   = '/etc/enigma2/userbouquet.hdsdvbi.radio'
CALE_BOUQUETS_TV     = '/etc/enigma2/bouquets.tv'
CALE_BOUQUETS_RADIO  = '/etc/enigma2/bouquets.radio'
USER_AGENT           = 'HDSatelit/%s DVB-I/1.0 (hdsatelit.com)' % VERSIUNE
TIMP_FETCH           = 15.0
MAX_LISTA            = 4 * 1024 * 1024
INTERVAL_REFRESH_SEC = 3600   # 1 ora

# Namespace-uri DVB-I (ETSI TS 103 669)
_NS = [
    'urn:dvb:metadata:serviceDiscovery:2023',
    'urn:dvb:metadata:serviceDiscovery:2021',
    'urn:dvb:metadata:serviceDiscovery:2019',
]

# Liste DVB-I predefinite (activate optional din config).
# HDSatelit: cele 14 URL-uri vechi de aici NU rezolvau DNS deloc (verificat cu
# nslookup si socket.gethostbyname pe toate 14 -- pareau ghicite dupa un tipar plauzibil
# "dvb-i.<domeniu>/service-list", nu cercetate real). Inlocuite cu 7 adrese REALE, verificate
# una cate una (HTTP 200, continut XML DVB-I valid, descarcate si inspectate) din registrul
# oficial DVB-I (https://competition-csr.dvb-i.tv/api/query, endpoint recomandat chiar de DVB
# pentru dezvoltare/testare). Un registru se schimba in timp -- daca vreuna nu mai raspunde la
# o verificare ulterioara, se cere din nou lista curenta de la endpoint-ul de mai sus, nu se
# ghicesc adrese noi dupa tipar.
LISTE_PREDEFINITE = [
    ('babeleye',     'https://aws.onscreenpublisher.co.uk/dvb-i/api/serviceList/dvbUICompetition', 'DVB-I Competition (OnScreen Publishing)', 'INT'),
    ('ccma',         'https://dvbi-statics.3cat.cat/servicelist/pilot_dvbi_3cat.xml?version=1.0',  '3Cat / CCMA Catalonia',                    'ES'),
    ('sofia',        'https://apps-demo.dtv.fi/dvbi/public/Finnish-DVB-T-Demo/c9ffaaf1069677fc07a5ec61c2f8b6da/tagsofiadigitalcom2024finlanddttv.xml', 'Sofia Digital DVB-T Demo', 'FI'),
    ('freeview_nz',  'https://slr.switch.tv/static/servicelists/dvbi_service_list_uat.xml',        'Freeview New Zealand (UAT)',               'NZ'),
    ('saorview',     'https://dvbipoc.private.saorview.ie/dvb-i/api/serviceList/saorview',          'Saorview Irlanda',                         'IE'),
    ('getmeradio_uk','https://dvbi01-uk.getmeradio.com/unitedkingdom.xml',                          'Get Me Radio - Marea Britanie',            'GB'),
    ('getmeradio_us','https://dvbi01-uk.getmeradio.com/unitedstatesofamerica.xml',                  'Get Me Radio - SUA',                       'US'),
]


# ---------------------------------------------------------------- fetch + parse DVB-I
# 0.2.5: textul „ceasul e în urmă” (Components/HdsCeasHttps.py) cand o lista a cazut la reincarcare din cauza ceasului
# receptorului; reincarca_acum il da ecranului in locul lui „terminată cu succes”. Se goleste la fiecare reincarcare.
_ULTIMA_EROARE_CEAS = [None]
# 0.2.8: True cand la ultima reincarcare NICIO lista configurata nu s-a putut descarca. Atunci
# buchetele nu se rescriu (inainte deveneau goale si canalele DVB-I bune de dinainte se pierdeau pana la urmatoarea
# reincarcare reusita), lista de canale nu se reincarca, iar reincarca_acum spune ecranului T_NICIO_LISTA in locul lui
# "terminata cu succes". O lista descarcata, chiar fara niciun canal, se scrie ca pana acum (e raspunsul ei).
_TOATE_AU_CAZUT = [False]
# 0.6.2: True cand la ultima reincarcare nu era nicio lista de descarcat (fara tara, fara liste bifate, fara adrese
# proprii). Reincarcarea "reuseste" fara sa faca nimic; Components/HdsDvbISetari.reincarca il citeste dupa ea, ca
# ecranul DVB-I Reload Now si pagina web sa nu mai spuna "terminată cu succes".
_FARA_LISTE = [False]


def N_(text):
    """Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la folosire."""
    return text


T_NICIO_LISTA = N_("Nicio listă DVB-I nu s-a putut descărca. Canalele DVB-I de dinainte rămân.")


def _t(text):
    try:
        return _(text)
    except NameError:
        return text


def _mesaj_ceas(eroare):
    try:
        from Components import HdsCeasHttps
        return HdsCeasHttps.mesaj(eroare)
    except Exception:
        return None


def _fetch(url):
    """Descarca URL-ul listei DVB-I. -> bytes sau None la eroare."""
    try:
        req = Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept': 'application/xml, text/xml, */*',
        })
        r = urlopen(req, timeout=TIMP_FETCH)
        date = r.read(MAX_LISTA + 1)
        if len(date) > MAX_LISTA:
            print('[HdsDvbI] lista prea mare: %s' % url)
            return None
        return date
    except (HTTPError, URLError, Exception) as e:
        print('[HdsDvbI] eroare fetch %s: %s' % (url, e))
        ceas = _mesaj_ceas(e)
        if ceas:
            _ULTIMA_EROARE_CEAS[0] = ceas
        return None


def _text_element(el):
    return (el.text or '').strip()


def _itereaza(el, tag_local):
    """Itereaza toti descendentii cu tag-ul local dat (indiferent de namespace)."""
    for copil in el.iter():
        tl = copil.tag.split('}')[-1] if '}' in copil.tag else copil.tag
        if tl == tag_local:
            yield copil


def _url_din_service_instance(el_inst):
    """Cauta URL-ul de flux intr-un <ServiceInstance>, dupa formele reale gasite
    inspectand 6 liste DVB-I reale, in productie, descarcate din registrul oficial DVB-I
    (nu presupuse, nu ghicite dupa denumire): schema 2019-2023 (mai veche, folosita de codul
    initial) foloseste <Locator href="..."/>; schema curenta 2024-2025 foloseste alte forme:
      - <DASHDeliveryParameters><UriBasedLocation><...:URI>url</...:URI></UriBasedLocation></DASHDeliveryParameters>
      - <OtherDeliveryParameters extensionName="vnd.apple.mpegurl">
            <hls:UriBasedLocation><...:URI>url</...:URI></hls:UriBasedLocation>
        </OtherDeliveryParameters>   (fluxuri HLS/m3u8)
      - <IdentifierBasedDeliveryParameters contentType="audio/mpeg">url</IdentifierBasedDeliveryParameters>
        (text direct, folosit des la radio)
    <DVBTDeliveryParameters> (triplet DVB-T clasic, nu URL) se ignora intentionat -- nu e livrare IP."""
    # 1. schema veche: Locator cu href/src/uri sau text
    for el_loc in _itereaza(el_inst, 'Locator'):
        for attr in ('href', 'src', 'uri'):
            v = el_loc.get(attr, '').strip()
            if v.startswith(('http://', 'https://')):
                return v
        if _text_element(el_loc).startswith(('http://', 'https://')):
            return _text_element(el_loc)

    # 2. schema curenta: DASH/HLS ("Other") -- ambele au un <...:UriBasedLocation> cu un
    #    copil <...:URI> care contine textul URL-ului, indiferent de prefixul de namespace
    for el_uri_loc in _itereaza(el_inst, 'UriBasedLocation'):
        for el_uri in _itereaza(el_uri_loc, 'URI'):
            v = _text_element(el_uri)
            if v.startswith(('http://', 'https://')):
                return v

    # 3. schema curenta, radio simplu: IdentifierBasedDeliveryParameters cu URL ca text direct
    for el_id in _itereaza(el_inst, 'IdentifierBasedDeliveryParameters'):
        v = _text_element(el_id)
        if v.startswith(('http://', 'https://')):
            return v

    # 4. fallback generic pentru variante viitoare de schema: orice element cunoscut cu atribut URL
    for tag in ('ContentLocator', 'Availability', 'StreamSource'):
        for el_alt in _itereaza(el_inst, tag):
            for attr in ('href', 'src', 'uri'):
                v = el_alt.get(attr, '').strip()
                if v.startswith(('http://', 'https://')):
                    return v
    return ''


def _id_stabil_serviciu(nume, url_flux):
    """Id stabil (16 biti) derivat din URL, NU un contor secvential care se reseteaza la fiecare
    refresh -- inainte, doua rulari ale parserului puteau da acelasi serviciu la indexuri diferite
    daca ordinea din XML se schimba intre timp (servicii adaugate/scoase la sursa), ceea ce rupea
    referinta de canal salvata de enigma2 (ultimul canal vazut, timere). Acum acelasi URL da mereu
    acelasi id, indiferent de pozitia lui in document sau de refresh-urile ulterioare."""
    import binascii
    date = (url_flux or nume).encode('utf-8', 'replace')
    return (binascii.crc32(date) & 0xFFFF) or 1  # niciodata 0 (rezervat/gol in referintele enigma2)


def _areDoctypeSuspect(xml_bytes):
    """HDSatelit: xml.etree.
    ElementTree.fromstring() (stdlib) NU e protejat implicit impotriva bombelor de entitati XML
    ("billion laughs", documentat oficial de Python) -- un DOCTYPE de cativa KB poate defini
    entitati care se expandeaza la GB la parsare, mult peste plafonul MAX_LISTA (care limiteaza
    doar DESCARCAREA, nu si expandarea la PARSARE; un receptor cu ~244 MB memorie masurata ar
    putea bloca/crapa enigma2). Cere compromiterea unuia din serverele configurate (fetch e pe
    HTTPS peste tot, TLS blocheaza un man-in-the-middle simplu) -- dar cel putin unul e explicit
    endpoint de test/demo, mai plausibil compromis decat unul de productie.
    Schemele DVB-I reale (ETSI TS 103 669) nu folosesc niciodata DOCTYPE/ENTITY -- respingerea nu
    pierde nimic legitim. Verificare pe OCTETI BRUTI, inainte de orice parsare/decodare -- nu pe
    atribute interne ale modulului expat (nu exista o cale stabila, documentata, de a injecta un
    parser expat propriu in ET.XMLParser incepand cu Python 3.8, iar atributul intern folosit de
    `defusedxml` pentru asta s-a dovedit sa difere intre versiuni de Python la verificare directa
    -- de-aici alegerea sa NU adaugam `defusedxml` ca dependinta noua, ci sa respingem devreme,
    portabil, orice document care ar putea contine o definitie de entitate)."""
    prefix = (xml_bytes or b'')[:8192].lower()
    return b'<!doctype' in prefix or b'<!entity' in prefix


def _parseaza_servicii(xml_bytes, url_baza=''):
    """Parseaza XML DVB-I -> lista de (id_stabil, nume, url_flux, tip) unde tip: 'tv'/'radio'."""
    servicii = []
    if _areDoctypeSuspect(xml_bytes):
        print('[HdsDvbI] XML respins: contine DOCTYPE/ENTITY (posibila bomba de entitati)')
        return servicii
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print('[HdsDvbI] XML invalid: %s' % e)
        return servicii

    # Gaseste namespace-ul
    ns = ''
    for n in _NS:
        if root.tag == ('{%s}ServiceList' % n) or root.tag.endswith('}ServiceList'):
            ns = n
            break

    id_folosite = set()
    for el_svc in _itereaza(root, 'Service'):
        # Nume
        nume = ''
        for el_dn in _itereaza(el_svc, 'DisplayName'):
            if _text_element(el_dn):
                nume = _text_element(el_dn)
                break
        if not nume:
            for el_n in _itereaza(el_svc, 'Name'):
                if _text_element(el_n):
                    nume = _text_element(el_n)
                    break
        if not nume:
            for el_n in _itereaza(el_svc, 'ServiceName'):  # numele folosit de schema curenta (2024-2025)
                if _text_element(el_n):
                    nume = _text_element(el_n)
                    break
        if not nume:
            continue

        # Tip serviciu
        tip = 'tv'
        for el_tip in _itereaza(el_svc, 'ServiceType'):
            t = (el_tip.get('href', '') or _text_element(el_tip)).lower()
            if 'radio' in t or 'audio' in t:
                tip = 'radio'
                break

        # URL flux: HDSatelit -- inainte cauta o singura data pe tot Service-ul si se
        # oprea la primul Locator gasit oriunde in subarbore (nu neaparat cel mai bun); acum
        # parcurge fiecare <ServiceInstance> in ordinea de prioritate DVB-I (atribut "priority",
        # numar mai mic = preferat; cele fara atribut trec ultimele) si ia primul care chiar
        # produce un URL de flux valid -- daca prima sursa (ex. CDN principal) nu are URL utilizabil,
        # trece la urmatoarea in loc sa renunte la tot serviciul.
        instante = list(_itereaza(el_svc, 'ServiceInstance'))
        instante.sort(key=lambda el: int(el.get('priority') or 999999))
        url_flux = ''
        for el_inst in instante:
            url_flux = _url_din_service_instance(el_inst)
            if url_flux:
                break

        if not url_flux:
            continue  # ex. doar DVBTDeliveryParameters (triplet clasic, nu livrare IP) -- normal, se sare

        id_serviciu = _id_stabil_serviciu(nume, url_flux)
        while id_serviciu in id_folosite:  # coliziune rara de CRC32 pe 16 biti -- pastram unicitatea
            id_serviciu = (id_serviciu + 1) & 0xFFFF or 1
        id_folosite.add(id_serviciu)

        servicii.append((id_serviciu, nume, url_flux, tip))

    return servicii


def _url_codificat(url):
    """Codifica URL-ul pentru referinta enigma2: '%', spatiul si ':'. Referinta se imparte la ':'
    (lib/service/service.cpp), deci fara '%3a' adresa "https://..." devenea calea "https" si canalul nu pornea."""
    return url.replace('%', '%25').replace(' ', '%20').replace(':', '%3a')


# randul #SERVICE al buchetului se citeste in char line[256] (lib/dvb/db.cpp, loadBouquet): un rand mai lung se strica
LUNGIME_RAND_MAX = 255


def _linie_sigura(text):
    """HDSatelit: un <DisplayName>/URL de flux
    dintr-un XML DVB-I extern poate contine, legitim din punct de vedere XML, orice caracter in
    interiorul textului unui element -- inclusiv \\r/\\n. `_text_element()` (mai sus) face doar
    `.strip()`, care curata STRICT capetele, nu si newline-uri din mijloc; `_url_codificat()` nu
    atinge deloc \\r/\\n. Fara aceasta curatare, `_genereaza_bouquet()` scria `nume`/`url_flux`
    NESCHIMBATE direct in liniile fisierului bouquet -- o sursa DVB-I rea intentionata sau
    compromisa (unul din cele 7 endpoint-uri predefinite, sau un URL propriu al utilizatorului)
    putea injecta linii `#SERVICE`/`#DESCRIPTION` proprii, ARBITRARE, in bouquet-ul userului
    (canale false/spoofing), nedetectabile de deduplicarea de mai sus (care lucreaza pe tupluri
    structurate, nu pe textul final scris in fisier). CONFIRMAT cu o proba directa (XML crafted,
    linie `#SERVICE` falsa injectata cu succes inainte de aceasta reparatie) -- nu doar presupus.
    Nu modifica sensul textului legitim (fara CR/LF, un nume/URL normal ramane identic)."""
    return (text or '').replace('\r', ' ').replace('\n', ' ').strip()


def ref_serviciu(idx, url_flux, tip='tv'):
    """Referinta enigma2 a unui canal DVB-I (fara numele de la coada): aceeasi in buchet, in starea pentru lista de
    canale si in trecerea pe internet (Components/HdsDvbIRezerva)."""
    return '4097:0:%d:%X:0:0:0:0:0:0:%s' % (2 if tip == 'radio' else 1, idx + 1, _url_codificat(_linie_sigura(url_flux)))


# cate randuri au fost lasate afara la ultima scriere a buchetelor, fiind prea lungi pentru nucleu (LUNGIME_RAND_MAX)
_SARITE_LUNGI = [0]


def _genereaza_bouquet(servicii_tv, servicii_radio, nume_tv='DVB-I TV'):
    """Genereaza continutul fisierelor bouquet pentru enigma2. Randurile #SERVICE mai lungi decat LUNGIME_RAND_MAX
    nu intra (le-ar strica citirea nucleului); cate au ramas afara sta in _SARITE_LUNGI."""
    _SARITE_LUNGI[0] = 0

    def linii(nume_buchet, servicii, tip):
        rez = ['#NAME %s' % _linie_sigura(nume_buchet)]
        for idx, nume, url_flux, _tip in servicii:
            rand = '#SERVICE %s' % ref_serviciu(idx, url_flux, tip)
            if len(rand.encode('utf-8')) > LUNGIME_RAND_MAX:
                _SARITE_LUNGI[0] += 1
                continue
            rez.append(rand)
            rez.append('#DESCRIPTION %s' % _linie_sigura(nume))
        return '\n'.join(rez) + '\n'

    return linii(nume_tv, servicii_tv, 'tv'), linii('DVB-I Radio', servicii_radio, 'radio')


def _adauga_in_bouquets_master(cale_master, cale_bouquet_nou, nume_bouquet):
    """Adauga referinta la bouquet-ul DVB-I in bouquets.tv sau bouquets.radio daca nu exista deja."""
    referinta = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % os.path.basename(cale_bouquet_nou)
    try:
        if os.path.exists(cale_master):
            with open(cale_master, 'r', encoding='utf-8', errors='replace') as f:
                continut = f.read()
        else:
            continut = '#NAME Favourites\n'

        if os.path.basename(cale_bouquet_nou) not in continut:
            continut = continut.rstrip('\n') + '\n' + referinta + '\n'
            with open(cale_master, 'w', encoding='utf-8') as f:
                f.write(continut)
    except (IOError, OSError) as e:
        print('[HdsDvbI] eroare bouquets master: %s' % e)


# ---------------------------------------------------------------- citire/scriere config
def _citeste_config():
    """Citeste /etc/enigma2/hdsdvbi.conf -> dict. Creeaza implicit daca lipseste."""
    config = {
        'activ': 'da',
        'interval_refresh': str(INTERVAL_REFRESH_SEC),
        'url_uri': [],         # lista URL-uri adaugate de utilizator
        'predefinite': [],     # cheile din LISTE_PREDEFINITE activate (ex. 'bbc,ard')
    }
    if not os.path.exists(CALE_CONFIG):
        return config
    try:
        with open(CALE_CONFIG, 'r', encoding='utf-8', errors='replace') as f:
            for linie in f:
                linie = linie.strip()
                if not linie or linie.startswith('#'):
                    continue
                if '=' in linie:
                    cheie, val = linie.split('=', 1)
                    cheie = cheie.strip().lower()
                    val = val.strip()
                    if cheie == 'activ':
                        config['activ'] = val.lower()
                    elif cheie == 'interval_refresh':
                        config['interval_refresh'] = val
                    elif cheie == 'url':
                        if val:
                            config['url_uri'].append(val)
                    elif cheie == 'predefinite':
                        config['predefinite'] = [x.strip() for x in val.split(',') if x.strip()]
    except (IOError, OSError) as e:
        print('[HdsDvbI] eroare citire config: %s' % e)
    return config


def _scrie_config(config):
    """Scrie configuratia in /etc/enigma2/hdsdvbi.conf."""
    linii = [
        '# Configurare HdsDvbI — HDSatelit DVB-I over Internet',
        '# activ = da / nu',
        'activ = %s' % config.get('activ', 'da'),
        '# interval_refresh = secunde intre reincarcari automate (0 = dezactivat)',
        'interval_refresh = %s' % config.get('interval_refresh', str(INTERVAL_REFRESH_SEC)),
        '# predefinite = cheile listelor predefinite separate prin virgula',
        '# Cheile disponibile: %s' % ', '.join(k for k, _, _, _ in LISTE_PREDEFINITE),
        'predefinite = %s' % ', '.join(config.get('predefinite', [])),
        '# url = URL personal DVB-I (adauga cate o linie pentru fiecare URL)',
    ]
    for url in config.get('url_uri', []):
        linii.append('url = %s' % url)
    try:
        with open(CALE_CONFIG, 'w', encoding='utf-8') as f:
            f.write('\n'.join(linii) + '\n')
    except (IOError, OSError) as e:
        print('[HdsDvbI] eroare scriere config: %s' % e)


# ---------------------------------------------------------------- manager principal
class HdsDvbIManager(object):
    """Gestioneaza incarcarea si actualizarea canalelor DVB-I."""

    def __init__(self):
        self._config = _citeste_config()
        self._thread = None
        self._activ  = True
        # o singura reincarcare deodata (firul periodic si reincarcarea ceruta din ecran sau din web)
        self._lacat = threading.Lock()
        self._vpn = None

    @property
    def activ(self):
        return self._config.get('activ', 'da').lower() in ('da', 'yes', '1', 'true')

    def _are_liste_configurate(self):
        """Aceeasi verificare ca inceputul lui fetch_si_actualizeaza (predefinite activate + URL-uri proprii),
        dar fara sa descarce nimic -- doar ca sa stim daca are rost sa pornim firul de reincarcare periodica.
        HDSatelit (optimizare de pornire): pluginul e activ implicit pentru toata lumea, dar marea
        majoritate a instalarilor nu au atins niciodata ecranul DVB-I -- fara asta, firul de mai jos pornea
        oricum la fiecare boot si statea de veghe la nesfarsit (trezire la 60s) fara sa aiba vreodata ceva de
        facut. Nu schimba nimic pentru cine chiar are o lista configurata. Si tara aleasa
        inseamna liste (ale ei, din registre)."""
        if self._config.get('url_uri') or self._config.get('tara'):
            return True
        predefinite_active = set(self._config.get('predefinite', []))
        return any(cheie in predefinite_active for cheie, _url, _desc, _tara in LISTE_PREDEFINITE)

    def _adrese(self):
        """adresele de descarcat: listele alese ale tarii (raspunsul registrelor, intrebate din nou cand e vechi),
        cele predefinite bifate si adresele proprii (Components/HdsDvbISetari.adreseDeDescarcat)"""
        config = self._config
        S, R = _setari(), _registru()
        if S is None:
            url_uri = list(config.get('url_uri', []))
            predefinite_active = set(config.get('predefinite', []))
            for cheie, url, _desc, _tara in LISTE_PREDEFINITE:
                if cheie in predefinite_active:
                    url_uri.append(url)
            return url_uri
        registru = None
        if config.get('tara') and R is not None:
            registru = R.incarca()
            if R.deIntrebat(registru):
                nou = R.intreabaToate()
                if nou.get('liste'):
                    R.salveaza(nou)
                    registru = nou
        return S.adreseDeDescarcat(config, registru, plugin=_eu())

    def fetch_si_actualizeaza(self):
        """Descarca toate listele DVB-I configurate si actualizeaza bouquet-urile enigma2."""
        with self._lacat:
            self._fetch_si_actualizeaza()

    def _fetch_si_actualizeaza(self):
        config = self._config
        _ULTIMA_EROARE_CEAS[0] = None
        _TOATE_AU_CAZUT[0] = False
        _FARA_LISTE[0] = False

        url_uri = self._adrese()
        if not url_uri:
            print('[HdsDvbI] nicio lista configurata')
            _FARA_LISTE[0] = True
            return

        # HDSatelit: un singur buchet TV pentru toate listele, fiecare lista in ordinea numerelor ei
        # (tabelul LCN al regiunii alese), apoi listele una dupa alta. Id-ul vine din adresa fluxului (stabil intre
        # reincarcari si intre liste); aceeasi adresa din doua liste intra o singura data.
        L = _legare()
        regiune = config.get('regiune', '')
        tv_all, radio_all = [], []
        urluri_puse = {}
        id_folosite = set()
        liste_info, legaturi_brute = [], []
        descarcate = 0

        for index_lista, url in enumerate(url_uri):
            info = {'adresa': url, 'nume': '', 'ok': False, 'tv': 0, 'radio': 0, 'regiuni': []}
            liste_info.append(info)
            date = _fetch(url)
            if not date:
                continue
            descarcate += 1
            info['ok'] = True
            info['nume'] = _numeLista(date)
            servicii = _parseaza_servicii(date, url)
            lcn = {}
            if L is not None:
                try:
                    lcn = L.numerotare(date, regiune)
                    info['regiuni'] = L.regiuni(date)
                    legaturi_brute += [(index_lista, l) for l in L.legaturi(date) if l.get('url')]
                except Exception as e:
                    print('[HdsDvbI] numerotarea si legarea %s: %s' % (url, e))
            ordine = sorted(range(len(servicii)), key=lambda i: (lcn.get(servicii[i][1]) is None,
                lcn.get(servicii[i][1]) or 0, i))
            for i in ordine:
                id_stabil, nume, url_flux, tip = servicii[i]
                if url_flux in urluri_puse:
                    continue
                id_serviciu = id_stabil
                while id_serviciu in id_folosite:  # coliziune rara de CRC32 pe 16 biti -- pastram unicitatea
                    id_serviciu = (id_serviciu + 1) & 0xFFFF or 1
                id_folosite.add(id_serviciu)
                intrare = (id_serviciu, nume, url_flux, tip)
                urluri_puse[url_flux] = (index_lista, intrare, lcn.get(nume))
                if tip == 'radio':
                    radio_all.append(intrare)
                    info['radio'] += 1
                else:
                    tv_all.append(intrare)
                    info['tv'] += 1

        if not descarcate:
            # fara internet, server cazut, ceasul in urma: buchetele de dinainte raman cum erau (nescrise, fara
            # reincarcarea listei de canale)
            _TOATE_AU_CAZUT[0] = True
            print('[HdsDvbI] nicio lista nu s-a putut descarca (%d configurate); buchetele raman neschimbate'
                  % len(url_uri))
            _scrieStare(liste_info, None, None, pastreaza_canalele=True)
            return

        bouquet_tv, bouquet_radio = _genereaza_bouquet(tv_all, radio_all, _numeBuchet())

        # Scrie fisierele bouquet
        try:
            with open(CALE_BOUQUET_TV, 'w', encoding='utf-8') as f:
                f.write(bouquet_tv)
            with open(CALE_BOUQUET_RADIO, 'w', encoding='utf-8') as f:
                f.write(bouquet_radio)
        except (IOError, OSError) as e:
            print('[HdsDvbI] eroare scriere bouquet: %s' % e)
            return

        # Adauga in bouquets master
        _adauga_in_bouquets_master(CALE_BOUQUETS_TV, CALE_BOUQUET_TV, 'DVB-I TV')
        _adauga_in_bouquets_master(CALE_BOUQUETS_RADIO, CALE_BOUQUET_RADIO, 'DVB-I Radio')

        _scrieStare(liste_info, (tv_all, radio_all, urluri_puse), legaturi_brute)

        # HDSatelit: eDVBDB.getInstance().reloadServicelist() ruleaza aici pe firul
        # de fundal (threading.Thread din porneste_refresh_periodic, mai jos) -- un apel in
        # motorul C++ al enigma2 care nu e sigur de facut decat din firul principal, la fel ca
        # orice atingere a GUI-ului/bazei de date de servicii dintr-un fir separat. Mutat pe
        # firul principal prin reactor.callFromThread() (Twisted, deja instalat de mytest.py
        # peste bucla principala enigma2 -- exact mecanismul facut pentru asta, sigur de apelat
        # din orice fir, spre deosebire de eTimer, ale carui obiecte nu sunt sigure de creat
        # din alt fir decat cel principal).
        def _reincarca_pe_firul_principal():
            try:
                from enigma import eDVBDB
                db = eDVBDB.getInstance()
                db.reloadServicelist()
                # DVB-I: reloadServicelist citeste numai lamedb; buchetul scris acum intra in lista numai
                # cu reloadBouquets (inainte aparea abia dupa o repornire)
                db.reloadBouquets()
                print('[HdsDvbI] lista reincarcata: %d TV, %d Radio' % (len(tv_all), len(radio_all)))
            except Exception as e:
                print('[HdsDvbI] reloadServicelist: %s' % e)
            _anuntaSchimbarea()

        try:
            from twisted.internet import reactor
            reactor.callFromThread(_reincarca_pe_firul_principal)
        except Exception as e:
            print('[HdsDvbI] nu am putut programa reloadServicelist pe firul principal: %s' % e)

    def incearca_canalele(self, forteaza=False, numai=None):
        """Incearca din casa fluxurile canalelor (Components/HdsDvbIIncercare): numai pe cele neincercate sau
        incercate de mai mult de INCERCARE_S, ori toate cu forteaza; 'numai' = stari de incercat din nou (de pilda
        oprit_tara dupa pornirea VPN-ului). Pe firul celui care cheama; una deodata."""
        I, D = _incercare(), _date()
        if I is None or D is None:
            return
        if not _INCERCARE['lacat'].acquire(False):
            return
        try:
            acum = time.time()
            de_incercat = []
            for c in D.canale():
                st, _cod, ora = D.stareUrl(c.get('url', ''))
                if numai is not None:
                    if st in numai:
                        de_incercat.append(c)
                elif forteaza or not st or acum - ora > INCERCARE_S or acum < ora:
                    de_incercat.append(c)
            _INCERCARE.update(in_curs=True, facute=0, total=len(de_incercat), ora=acum)
            rezultate = {}
            for c in de_incercat:
                if not self._activ:
                    break
                rezultate[c['url']] = I.incearca(c['url'])
                _INCERCARE['facute'] += 1
                if len(rezultate) >= 10:
                    D.noteazaIncercari(rezultate)
                    rezultate = {}
            if rezultate:
                D.noteazaIncercari(rezultate)
        except Exception as e:
            print('[HdsDvbI] incercarea canalelor: %s' % e)
        finally:
            _INCERCARE.update(in_curs=False)
            _INCERCARE['lacat'].release()
        _anuntaSchimbarea()

    def _pazaVpn(self):
        """VPN-ul receptorului tocmai a pornit (sau s-a oprit): canalele oprite pentru tara se incearca din nou"""
        try:
            from Components import HdsVpn
            s = HdsVpn.stare()
            semn = (s.get('legatura') == 'conectat', (s.get('ip') or {}).get('tara') if isinstance(s.get('ip'), dict) else None)
        except Exception:
            return
        vechi, self._vpn = self._vpn, semn
        if vechi is not None and vechi != semn:
            print('[HdsDvbI] VPN-ul s-a schimbat (%s -> %s): canalele oprite pentru tara se incearca din nou' % (vechi, semn))
            self.incearca_canalele(numai=('oprit_tara', 'nu_raspunde') if semn[0] else ('merge',))

    def porneste_refresh_periodic(self):
        """Porneste un thread daemon care refresheaza listele la intervalul configurat."""
        try:
            interval = int(self._config.get('interval_refresh', INTERVAL_REFRESH_SEC))
        except (ValueError, TypeError):
            interval = INTERVAL_REFRESH_SEC

        if interval <= 0:
            return

        # HDSatelit (optimizare de pornire, vezi _are_liste_configurate): fara nicio lista
        # activata, firul nu are niciodata ce reincarca -- nu-l mai pornim deloc (thread + trezire la
        # 60s, pe toata durata functionarii, degeaba). Daca thread-ul e deja pornit (apelul de mai jos
        # se poate repeta, ex. dintr-o sesiune viitoare care activeaza ceva), nu pornim un al doilea.
        if self._thread is not None and self._thread.is_alive():
            return
        if not self._are_liste_configurate():
            print('[HdsDvbI] nicio lista configurata -- firul de reincarcare periodica nu porneste (pornește dupa alegerea unei tari sau a unei liste)')
            return

        def _bucla():
            # Prima incarcare dupa 10 secunde (enigma2 sa termine initializarea)
            time.sleep(10)
            urmatoarea = 0
            while self._activ:
                if time.time() >= urmatoarea:
                    self.fetch_si_actualizeaza()
                    self.incearca_canalele()
                    urmatoarea = time.time() + interval
                self._pazaVpn()
                time.sleep(60)

        self._thread = threading.Thread(target=_bucla, name='HdsDvbI-refresh', daemon=True)
        self._thread.start()

    def opreste(self):
        self._activ = False


# ---------------------------------------------------------------- ajutoarele DVB-I
# Componentele se incarca la folosire si pot lipsi (probele de pe PC dau pluginul fara ele): atunci pluginul merge ca
# inainte (adresele proprii si predefinite, fara stare, legare si incercari).
INCERCARE_S = 6 * 3600
_INCERCARE = {'in_curs': False, 'facute': 0, 'total': 0, 'ora': 0, 'lacat': threading.Lock()}
CALE_STARE = '/etc/enigma2/hdsdvbi-stare.json'


T_NUME_BUCHET = N_('Canale de pe internet (DVB-I)')


def _numeBuchet():
    return _t(T_NUME_BUCHET)


def _eu():
    import sys
    return sys.modules.get(__name__)


def _setari():
    try:
        from Components import HdsDvbISetari
        return HdsDvbISetari
    except Exception:
        return None


def _registru():
    try:
        from Components import HdsDvbIRegistru
        return HdsDvbIRegistru
    except Exception:
        return None


def _legare():
    try:
        from Components import HdsDvbILegare
        return HdsDvbILegare
    except Exception:
        return None


def _incercare():
    try:
        from Components import HdsDvbIIncercare
        return HdsDvbIIncercare
    except Exception:
        return None


def _date():
    try:
        from Components import HdsDvbIDate
        return HdsDvbIDate
    except Exception:
        return None


def stareIncercare():
    return dict((k, v) for k, v in _INCERCARE.items() if k != 'lacat')


def _numeLista(xml_bytes):
    """<Name> de la radacina listei (numele dat de cine a facut-o), sau ''"""
    if _areDoctypeSuspect(xml_bytes):
        return ''
    try:
        rad = ET.fromstring(xml_bytes)
    except Exception:
        return ''
    for c in list(rad):
        tl = c.tag.split('}')[-1]
        if tl == 'Name' and _text_element(c):
            return _linie_sigura(_text_element(c))[:120]
    return ''


def _scrieStare(liste_info, canale, legaturi_brute, pastreaza_canalele=False):
    """Starea pentru lista de canale, bara, trecerea pe internet si pagina web (Components/HdsDvbIDate)."""
    D = _date()
    if D is None:
        return
    vechi = D.stare(CALE_STARE) if pastreaza_canalele else {}
    stare = {'ora': int(time.time()), 'liste': liste_info, 'lungi': _SARITE_LUNGI[0],
             'canale': list(vechi.get('canale') or []), 'legaturi': dict(vechi.get('legaturi') or {})}
    if canale is not None:
        tv_all, radio_all, urluri_puse = canale
        L = _legare()
        lista_canale = []
        nr_tv = nr_radio = 0
        id_dupa_lista_nume = {}
        for idx, nume, url_flux, tip in tv_all + radio_all:
            index_lista, _intrare, lcn = urluri_puse[url_flux]
            if tip == 'radio':
                nr_radio += 1
                nr = nr_radio
            else:
                nr_tv += 1
                nr = nr_tv
            lista_canale.append({'id': idx, 'nume': nume, 'url': url_flux, 'tip': tip, 'lcn': lcn, 'nr': nr,
                                 'lista': liste_info[index_lista]['adresa'], 'sat': '',
                                 'ref': ref_serviciu(idx, url_flux, tip)})
            id_dupa_lista_nume.setdefault((index_lista, nume), lista_canale[-1])
        dupa_url = dict((c['url'], c) for c in lista_canale)
        legaturi = {}
        for index_lista, l in legaturi_brute or []:
            c = id_dupa_lista_nume.get((index_lista, l.get('nume', ''))) or dupa_url.get(l.get('url', ''))
            if c is None or L is None:
                continue
            cheie = L.cheie(l['sid'], l['tsid'], l['onid'], L.spatiuNume(l['zecimi']))
            if cheie in legaturi:
                continue
            legaturi[cheie] = {'nume': c['nume'], 'url': c['url'], 'id': c['id'], 'ref': c['ref']}
            if not c['sat']:
                c['sat'] = cheie
        stare['canale'] = lista_canale
        stare['legaturi'] = legaturi
    D.scrieJson(CALE_STARE, stare)


# cine vrea sa afle ca s-a schimbat ceva (lista de canale, bara): functii fara argumente, chemate pe firul enigma2
ASCULTATORI = []


def _anuntaSchimbarea():
    def _anunta():
        for f in list(ASCULTATORI):
            try:
                f()
            except Exception as e:
                print('[HdsDvbI] ascultator: %s' % e)
    try:
        from twisted.internet import reactor
        reactor.callFromThread(_anunta)
    except Exception:
        pass


def _asiguraBuchetul():
    """Buchetul "Canale de pe internet (DVB-I)" e mereu in lista de canale, si fara nicio lista aleasa: gol, cu
    explicatia din lista (Components/HdsIndexCanale, felul 'dvbi'). -> True daca s-a scris ceva acum."""
    scris = False
    try:
        if not os.path.exists(CALE_BOUQUET_TV):
            with open(CALE_BOUQUET_TV, 'w', encoding='utf-8') as f:
                f.write('#NAME %s\n' % _linie_sigura(_numeBuchet()))
            scris = True
        are = False
        if os.path.exists(CALE_BOUQUETS_TV):
            with open(CALE_BOUQUETS_TV, 'r', encoding='utf-8', errors='replace') as f:
                are = os.path.basename(CALE_BOUQUET_TV) in f.read()
        if not are:
            _adauga_in_bouquets_master(CALE_BOUQUETS_TV, CALE_BOUQUET_TV, 'DVB-I TV')
            scris = True
    except (IOError, OSError) as e:
        print('[HdsDvbI] buchetul DVB-I: %s' % e)
    return scris


def reincarca_acum(la_gata=None):
    """HDSatelit: "DVB-I Reload Now" din meniu deschidea exact
    acelasi ecran ca "DVB-I Setup", fara nicio actiune reala de reincarcare. Functia de fata
    porneste chiar reincarcarea (aceeasi metoda folosita de refresh-ul periodic), intr-un fir
    separat ca sa nu blocheze interfata; `la_gata()` (daca e data) se cheama pe firul principal
    dupa terminare, prin acelasi reactor.callFromThread folosit si de fetch_si_actualizeaza.
    Dupa raspuns, pe acelasi fir: incercarea din casa a canalelor noi si pornirea reincarcarii periodice (o tara
    aleasa acum nu astepta o repornire)."""
    if _manager is None:
        if la_gata:
            from twisted.internet import reactor
            reactor.callFromThread(la_gata, False, 'HdsDvbI nu e pornit inca (autostart nu a rulat)')
        return

    def _fir():
        eroare = None
        try:
            _manager.fetch_si_actualizeaza()
        except Exception as e:
            eroare = str(e)
        if eroare is None and _ULTIMA_EROARE_CEAS[0]:
            eroare = _ULTIMA_EROARE_CEAS[0]
        if eroare is None and _TOATE_AU_CAZUT[0]:
            eroare = _t(T_NICIO_LISTA)
        if la_gata:
            try:
                from twisted.internet import reactor
                reactor.callFromThread(la_gata, eroare is None, eroare)
            except Exception:
                pass
        if eroare is None:
            try:
                _manager.incearca_canalele()
                _manager.porneste_refresh_periodic()
            except Exception as e:
                print('[HdsDvbI] dupa reincarcare: %s' % e)

    threading.Thread(target=_fir, name='HdsDvbI-reload-manual', daemon=True).start()


def incearca_acum(forteaza=True, numai=None):
    """Incercarea din casa a canalelor, pe un fir (tasta galbena pe televizor, butonul din web). -> False daca o
    incercare e deja in curs sau pluginul nu e pornit."""
    if _manager is None or _INCERCARE['in_curs']:
        return False

    def _fir():
        _manager.incearca_canalele(forteaza=forteaza, numai=numai)

    threading.Thread(target=_fir, name='HdsDvbI-incercare', daemon=True).start()
    return True


# ---------------------------------------------------------------- instanta globala
_manager = None


def autostart(reason, **kwargs):
    """Apelata de enigma2 la pornire (reason=0) si oprire (reason=1)."""
    global _manager
    if reason == 0:   # pornire
        _manager = HdsDvbIManager()
        if _manager.activ:
            if _asiguraBuchetul():
                try:
                    from enigma import eDVBDB
                    eDVBDB.getInstance().reloadBouquets()
                except Exception as e:
                    print('[HdsDvbI] reloadBouquets la pornire: %s' % e)
            _manager.porneste_refresh_periodic()
    elif reason == 1 and _manager:  # oprire
        _manager.opreste()


def sessionstart(reason, session=None, **kwargs):
    """La pornirea sesiunii: trecerea singura pe internet cand satelitul nu se receptioneaza si mesajul
    pentru canalele oprite pe tara (Components/HdsDvbIRezerva.py; bataia ei pe firul enigma2)."""
    if reason != 0 or session is None:
        return
    try:
        from Components import HdsDvbIRezerva
        HdsDvbIRezerva.porneste(session)
    except Exception as e:
        print('[HdsDvbI] trecerea pe internet nu a pornit: %s' % e)


def Plugins(**kwargs):
    """Inregistrare plugin: autostart si pornirea sesiunii, NU apare in Plugin Browser."""
    return [
        PluginDescriptor(
            name='HdsDvbI',
            description=_('DVB-I over Internet'),
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=autostart,
        ),
        PluginDescriptor(
            name='HdsDvbI',
            description=_('DVB-I over Internet'),
            where=PluginDescriptor.WHERE_SESSIONSTART,
            fnc=sessionstart,
        ),
    ]

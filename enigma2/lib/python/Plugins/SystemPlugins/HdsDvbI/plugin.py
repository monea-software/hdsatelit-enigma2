# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsDvbI — suport DVB-I integrat in imaginea HDSatelit.

DVB-I (ETSI TS 103 669): canale TV liniare livrate prin internet (HLS/DASH/TS).
Scris de la zero.

DVB-I: listele tarii alese din registrele DVB-I (Components/HdsDvbIRegistru, HdsDvbISetari), un singur
buchet TV "Canale de pe internet (DVB-I)" in ordinea LCN a regiunii (Components/HdsDvbILegare), in lista din fabrica;
scos de om din lista de canale nu mai revine singur (semnul CALE_SCOASA, Components/HdsDvbISetari), pana il pune la loc
randul "Arată lista în lista de canale" (ecranul DVB-I, pagina web);
adresele cu ':' codificat (%3a) si buchetele reincarcate (reloadBouquets); starea pentru lista de canale, bara,
trecerea pe internet si web (Components/HdsDvbIDate); canalele incercate din casa (Components/HdsDvbIIncercare) la
6 ore, la cerere si dupa schimbarea VPN-ului; la pornirea sesiunii, trecerea pe internet (Components/HdsDvbIRezerva).

EPG2 (0.7.7, asistenta 058499, hotararea coordonatorului 16.11 02:45, varianta 2): in buchet intra numai canalele care pot
merge. Adresele care nu sunt canale (clipurile Vimeo cu lungime si imaginile de proba DASH-IF, HdsDvbIIncercare.felScos)
nu intra deloc si nu se incearca; canalele care n-au trecut incercarea din casa (oprite pentru tara, adrese moarte, fara
raspuns) stau ascunse pana la urmatoarea incercare reusita: raman in starea DVB-I (lista din web le arata, incercarea le
reia la fiecare reincarcare, INCERCARE_ASCUNSE_S), iar buchetul se rescrie fara descarcare cand se schimba ceva. Totul pe
firul de fundal, cu un termen pe canal (TERMEN_CANAL_S) si unul pe toata incercarea (TERMEN_INCERCARI_S); in jurnal un
singur rand pe buchet, cu cate s-au scos si cate s-au ascuns, si de ce.

DVI2 (0.8.0, Eduard 26.11.2026 17:32-17:34): listele din toate tarile vin si cu listele de proba
(Components/HdsDvbISetari); canalele oprite pentru tara nu se mai ascund (se pot porni cu VPN-ul), ci au eticheta, cu
tara listei lor ("tara" la lista si la canal in starea DVB-I) cand e alta decat tara aleasa. Listele de proba nu dau
trecerea singura satelit -> internet.

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
CALE_SCOASA          = '/etc/enigma2/hdsdvbi.scoasa'   # listele scoase de om din lista de canale (tv, radio)
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
# DVJ (15.11.2026): textul erorii ultimei descarcari nereusite (_fetch nu mai scrie el in jurnal: listele care nu
# raspund le noteaza Components/HdsDvbISurse, un rand la prima cadere si cel mult unul pe zi, cu pauza crescatoare)
_ULTIMA_EROARE_FETCH = [None]


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
    """Descarca URL-ul listei DVB-I. -> bytes sau None la eroare (textul ei in _ULTIMA_EROARE_FETCH)."""
    _ULTIMA_EROARE_FETCH[0] = None
    try:
        req = Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept': 'application/xml, text/xml, */*',
        })
        r = urlopen(req, timeout=TIMP_FETCH)
        date = r.read(MAX_LISTA + 1)
        if len(date) > MAX_LISTA:
            _ULTIMA_EROARE_FETCH[0] = 'lista prea mare'
            return None
        return date
    except (HTTPError, URLError, Exception) as e:
        _ULTIMA_EROARE_FETCH[0] = str(e) or e.__class__.__name__
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
            if _tip == 'marcaj':
                # TODO 1883: marcajul grupei unei tari (listele din toate tarile), cu numele tarii
                rez.append('#SERVICE 1:64:%d:0:0:0:0:0:0:0::%s' % (idx, _linie_sigura(nume)))
                rez.append('#DESCRIPTION %s' % _linie_sigura(nume))
                continue
            rand = '#SERVICE %s' % ref_serviciu(idx, url_flux, tip)
            if len(rand.encode('utf-8')) > LUNGIME_RAND_MAX:
                _SARITE_LUNGI[0] += 1
                continue
            rez.append(rand)
            rez.append('#DESCRIPTION %s' % _linie_sigura(nume))
        return '\n'.join(rez) + '\n'

    return linii(nume_tv, servicii_tv, 'tv'), linii('DVB-I Radio', servicii_radio, 'radio')


def _repara_tipul_radio(continut, fisier):
    """In bouquets.radio randul buchetului `fisier` scris cu tipul TV (#SERVICE 1:7:1:...) trece pe tipul radio
    (#SERVICE 1:7:2:...). Celelalte randuri si sfarsiturile de rand raman neatinse."""
    gresit, bun = '#SERVICE 1:7:1:', '#SERVICE 1:7:2:'
    cauta = 'FROM BOUQUET "%s"' % fisier
    randuri = continut.splitlines(True)
    for i, rand in enumerate(randuri):
        if rand.startswith(gresit) and cauta in rand:
            randuri[i] = bun + rand[len(gresit):]
    return ''.join(randuri)


def _adauga_in_bouquets_master(cale_master, cale_bouquet_nou, nume_bouquet):
    """Adauga referinta la bouquet-ul DVB-I in bouquets.tv sau bouquets.radio daca nu exista deja. In bouquets.radio
    referinta poarta tipul radio (1:7:2), ca favoritele si celelalte buchete radio ale imaginii. Pana in 0.7.4 se
    scria si acolo 1:7:1 (tipul TV): randul gresit deja scris (sau adus inapoi de o copie a setarilor ori de un import)
    se repara pe loc la fiecare chemare; dupa scriere vine reloadBouquets, deci il ia si lista din memorie."""
    fisier = os.path.basename(cale_bouquet_nou)
    tip = 2 if cale_master.endswith('.radio') or cale_master == CALE_BOUQUETS_RADIO else 1
    referinta = '#SERVICE 1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (tip, fisier)
    try:
        if os.path.exists(cale_master):
            # newline='': sfarsiturile de rand ale fisierului raman cum sunt (o reparatie nu rescrie tot fisierul)
            with open(cale_master, 'r', encoding='utf-8', errors='surrogateescape', newline='') as f:
                continut = f.read()
        else:
            continut = '#NAME Favourites\n'

        nou = continut
        if fisier not in continut:
            nou = continut.rstrip('\n') + '\n' + referinta + '\n'
        elif tip == 2:
            nou = _repara_tipul_radio(continut, fisier)
        if nou != continut:
            with open(cale_master, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
                f.write(nou)
    except (IOError, OSError) as e:
        print('[HdsDvbI] eroare bouquets master: %s' % e)


def _scoasa(fel):
    """Buchetul DVB-I de felul 'tv' / 'radio' scos de om din lista de canale (semnul CALE_SCOASA, pus de
    Components/HdsDvbISetari): nu se mai scrie si nu se mai leaga singur. Citit din fisier la fiecare scriere, nu din
    setarile tinute de manager."""
    try:
        with open(CALE_SCOASA, 'r', encoding='utf-8', errors='replace') as f:
            return fel in f.read().split()
    except (IOError, OSError):
        return False


def _scoate_din_bouquets_master(cale_master, cale_bouquet):
    """Scoate randul buchetului DVB-I din bouquets.tv / bouquets.radio; celelalte randuri si sfarsiturile lor raman.
    -> True daca s-a scris."""
    cauta = 'FROM BOUQUET "%s"' % os.path.basename(cale_bouquet)
    try:
        with open(cale_master, 'r', encoding='utf-8', errors='surrogateescape', newline='') as f:
            continut = f.read()
    except (IOError, OSError):
        return False
    randuri = continut.splitlines(True)
    ramase = [r for r in randuri if not (r.startswith('#SERVICE') and cauta in r)]
    if len(ramase) == len(randuri):
        return False
    try:
        with open(cale_master, 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
            f.write(''.join(ramase))
        return True
    except (IOError, OSError) as e:
        print('[HdsDvbI] scoaterea din %s: %s' % (cale_master, e))
        return False


# ---------------------------------------------------------------- citire/scriere config
def _citeste_config():
    """Citeste /etc/enigma2/hdsdvbi.conf -> dict, cu toate cheile (tara, regiunea, listele tarii scoase sau puse,
    rezerva; fara tara aleasa, tara receptorului) prin Components/HdsDvbISetari.citeste, aceeasi citire ca ecranul si
    pagina web. Citirea veche de mai jos (numai activ, interval, predefinite, url) pierdea tara: dupa o repornire
    reincarcarea din ora in ora nu mai pornea ("nicio lista configurata"), iar buchetul ramanea cel vechi.
    Fara modulul setarilor (probele de pe PC), citirea veche."""
    S = _setari()
    if S is not None:
        try:
            return S.citeste(CALE_CONFIG)
        except Exception as e:
            print('[HdsDvbI] setarile: %s' % e)
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
        self._grupe = {}
        self._proba = set()
        self._thread = None
        self._activ  = True
        # o singura reincarcare deodata (firul periodic si reincarcarea ceruta din ecran sau din web)
        self._lacat = threading.Lock()
        self._vpn = None
        # registrele au raspuns cu liste la ultima intrebare (_adrese): numai atunci "tara n-are liste" e sigur
        self._registru_raspuns = False
        # EPG2: ce a dat ultima descarcare (buchetul se rescrie din ea dupa o incercare, fara descarcare) si adresele
        # ascunse in buchetul scris
        self._ultim = None
        self._ascunse = None

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

    def _golesteFaraListe(self):
        """Nicio lista de descarcat pentru tara de acum (registrele raspunsesera si n-o au, sau nicio tara aleasa):
        buchetele DVB-I raman goale, nu cu canalele altei tari sau ale unei liste scoase, iar starea spune tara si ca
        nu are liste (textul listei goale, Components/HdsIndexCanale). Fara raspunsul registrelor (fara internet de la
        pornire) nu se sterge nimic: nu se stie."""
        tara = self._config.get('tara', '')
        if tara and not self._registru_raspuns:
            return
        gol_tv = '#NAME %s\n' % _linie_sigura(_numeBuchet())
        gol_radio = '#NAME %s\n' % _linie_sigura(_numeBuchet())
        schimbat = False
        for cale, gol, fel in ((CALE_BOUQUET_TV, gol_tv, 'tv'), (CALE_BOUQUET_RADIO, gol_radio, 'radio')):
            if _scoasa(fel):
                continue
            try:
                vechi = ''
                if os.path.exists(cale):
                    with open(cale, 'r', encoding='utf-8', errors='replace') as f:
                        vechi = f.read()
                if '#SERVICE' in vechi or not vechi:
                    with open(cale, 'w', encoding='utf-8') as f:
                        f.write(gol)
                    schimbat = True
            except (IOError, OSError) as e:
                print('[HdsDvbI] buchetul gol: %s' % e)
        _scrieStare([], ([], [], {}), [], in_plus={'fara_liste': True, 'tara': tara})
        if not schimbat:
            return

        def _reincarca_pe_firul_principal():
            try:
                from enigma import eDVBDB
                eDVBDB.getInstance().reloadBouquets()
            except Exception as e:
                print('[HdsDvbI] reloadBouquets: %s' % e)
            _anuntaSchimbarea()
        try:
            from twisted.internet import reactor
            reactor.callFromThread(_reincarca_pe_firul_principal)
        except Exception as e:
            print('[HdsDvbI] nu am putut programa reloadBouquets: %s' % e)

    def _adrese(self):
        """adresele de descarcat: listele alese ale tarii (raspunsul registrelor, intrebate din nou cand e vechi),
        cele predefinite bifate si adresele proprii (Components/HdsDvbISetari.adreseDeDescarcat)"""
        config = self._config
        S, R = _setari(), _registru()
        self._registru_raspuns = False
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
            self._registru_raspuns = bool((registru or {}).get('liste'))
        # DVI2: listele de proba ale registrelor (nu dau trecerea singura pe internet)
        self._proba = set(l.get('adresa') for l in (registru or {}).get('liste', []) if l.get('proba'))
        # TODO 1883: tara fiecarei adrese, pentru marcajele grupelor din buchet ({} cu toate_tarile oprit)
        try:
            self._grupe = S.grupeAdrese(config, registru) if hasattr(S, 'grupeAdrese') else {}
        except Exception as e:
            print('[HdsDvbI] grupele pe tari: %s' % e)
            self._grupe = {}
        return S.adreseDeDescarcat(config, registru, plugin=_eu())

    def fetch_si_actualizeaza(self, forteaza=False):
        """Descarca toate listele DVB-I configurate si actualizeaza bouquet-urile enigma2. forteaza (reincarcarea
        ceruta de om): si listele aflate in pauza pentru ca nu raspundeau (Components/HdsDvbISurse)."""
        with self._lacat:
            self._fetch_si_actualizeaza(forteaza)

    def _fetch_si_actualizeaza(self, forteaza=False):
        config = self._config
        self._reincearca_peste = None
        _ULTIMA_EROARE_CEAS[0] = None
        _TOATE_AU_CAZUT[0] = False
        _FARA_LISTE[0] = False

        self._grupe = {}
        url_uri = self._adrese()
        if not url_uri:
            print('[HdsDvbI] nicio lista configurata')
            _FARA_LISTE[0] = True
            # EPG2: o incercare de dupa asta nu mai rescrie buchetul listelor de dinainte
            self._ultim = None
            self._golesteFaraListe()
            return

        # HDSatelit: un singur buchet TV pentru toate listele, fiecare lista in ordinea numerelor ei
        # (tabelul LCN al regiunii alese), apoi listele una dupa alta. Id-ul vine din adresa fluxului (stabil intre
        # reincarcari si intre liste); aceeasi adresa din doua liste intra o singura data.
        L = _legare()
        regiune = config.get('regiune', '')
        tara_aleasa = (config.get('tara') or '').upper()
        tv_all, radio_all = [], []
        urluri_puse = {}
        id_folosite = set()
        # EPG2: clipurile si imaginile de proba (nu sunt canale), numarate o data pe adresa
        I = _incercare()
        felScos = getattr(I, 'felScos', None) if I is not None else None
        scoase, scoase_url = {}, set()
        liste_info, legaturi_brute = [], []
        descarcate = 0
        # DVJ: o lista care nu raspundea sta in pauza crescatoare (nu se mai asteapta 15 s la fiecare pornire)
        SU = _surse()
        sarite = SU.deIncercat(url_uri, forteaza)[1] if SU is not None else {}
        rezultate = []

        for index_lista, url in enumerate(url_uri):
            # DVI2: tara listei cand e alta decat tara aleasa (eticheta "merge doar în <țara>" a canalelor oprite)
            grupa = (self._grupe.get(url) or '').upper()
            info = {'adresa': url, 'nume': '', 'ok': False, 'tv': 0, 'radio': 0, 'regiuni': [],
                    'tara': grupa if grupa and grupa != tara_aleasa else ''}
            liste_info.append(info)
            if url in sarite:
                info['pauza_pana'] = int(sarite[url])
                info['eroare'] = SU.eroare(url)
                continue
            date = _fetch(url)
            rezultate.append((url, bool(date), _ULTIMA_EROARE_FETCH[0]))
            if not date:
                info['eroare'] = _ULTIMA_EROARE_FETCH[0] or ''
                if SU is None:
                    print('[HdsDvbI] eroare fetch %s: %s' % (url, info['eroare']))
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
                    # TODO 1883: trecerea singura satelit -> internet (HdsDvbIRezerva) ia legaturile numai din listele
                    # tarii alese (si din cele fara grupa: predefinite, puse de mana), ca inainte; listele celorlalte
                    # tari dau canale in buchet, dar un flux strain blocat pe tara ar da ecran negru la pierderea
                    # semnalului
                    # DVI2: nici listele de proba ale registrelor (un flux de test nu inlocuieste canalul de satelit)
                    if self._grupe.get(url, tara_aleasa) == tara_aleasa and url not in getattr(self, '_proba', ()):
                        legaturi_brute += [(index_lista, l) for l in L.legaturi(date) if l.get('url')]
                except Exception as e:
                    print('[HdsDvbI] numerotarea si legarea %s: %s' % (url, e))
            ordine = sorted(range(len(servicii)), key=lambda i: (lcn.get(servicii[i][1]) is None,
                lcn.get(servicii[i][1]) or 0, i))
            for i in ordine:
                id_stabil, nume, url_flux, tip = servicii[i]
                if url_flux in urluri_puse:
                    continue
                fel = felScos(url_flux) if felScos is not None else ''
                if fel:
                    if url_flux not in scoase_url:
                        scoase_url.add(url_flux)
                        scoase[fel] = scoase.get(fel, 0) + 1
                        info['scoase'] = info.get('scoase', 0) + 1
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

        if SU is not None:
            try:
                self._reincearca_peste = SU.noteaza(rezultate)
            except Exception as e:
                print('[HdsDvbI] sursele: %s' % e)

        if not descarcate and not rezultate:
            # toate listele sunt in pauza (nu raspundeau): nimic de descarcat acum, buchetele raman cum erau
            return

        if not descarcate:
            # fara internet, server cazut, ceasul in urma: buchetele de dinainte raman cum erau (nescrise, fara
            # reincarcarea listei de canale); randul din jurnal il scrie HdsDvbISurse (o data, nu la fiecare incercare)
            _TOATE_AU_CAZUT[0] = True
            if SU is None:
                print('[HdsDvbI] nicio lista nu s-a putut descarca (%d configurate); buchetele raman neschimbate'
                      % len(url_uri))
            _scrieStare(liste_info, None, None, pastreaza_canalele=True)
            return

        self._ultim = {'tv': tv_all, 'radio': radio_all, 'urluri_puse': urluri_puse, 'url_uri': url_uri,
                       'liste_info': liste_info, 'legaturi': legaturi_brute, 'grupe': dict(self._grupe),
                       'scoase': scoase}
        self._scrieBuchetele(self._ultim)

    def _scrieBuchetele(self, u, numai_buchetele=False):
        """Scrie buchetele DVB-I din ce a dat o descarcare (u = self._ultim), fara canalele ascunse (EPG2: n-au trecut
        incercarea din casa), apoi starea (cu toate canalele, si cele ascunse, ca incercarea sa le reia) si randul din
        jurnal; reincarcarea listei de canale merge pe firul principal. numai_buchetele: rescrierea de dupa o incercare
        (lamedb nu s-a schimbat, ajunge reloadBouquets). -> False daca fisierele nu s-au putut scrie."""
        ascunse = _ascunse(u['tv'] + u['radio'])
        # numarul de canale al fiecarei liste (ecranul si web: "canale: N") fara cele ascunse
        for info in u['liste_info']:
            info['ascunse'] = 0
        for url in ascunse:
            index_lista = u['urluri_puse'].get(url, (None,))[0]
            if index_lista is not None and index_lista < len(u['liste_info']):
                u['liste_info'][index_lista]['ascunse'] += 1
        tv_all = [x for x in u['tv'] if x[2] not in ascunse]
        radio_all = [x for x in u['radio'] if x[2] not in ascunse]
        urluri_puse, url_uri, grupe = u['urluri_puse'], u['url_uri'], u['grupe']
        bouquet_tv, bouquet_radio = _genereaza_bouquet(_cuMarcaje(tv_all, urluri_puse, url_uri, grupe),
            _cuMarcaje(radio_all, urluri_puse, url_uri, grupe), _numeBuchet())

        # Scrie fisierele bouquet si le leaga in bouquets.tv / bouquets.radio; cel scos de om din lista de canale nu
        # se mai scrie si nu se mai leaga (_scoasa)
        for cale, continut, master, nume, fel in (
                (CALE_BOUQUET_TV, bouquet_tv, CALE_BOUQUETS_TV, 'DVB-I TV', 'tv'),
                (CALE_BOUQUET_RADIO, bouquet_radio, CALE_BOUQUETS_RADIO, 'DVB-I Radio', 'radio')):
            if _scoasa(fel):
                continue
            try:
                with open(cale, 'w', encoding='utf-8') as f:
                    f.write(continut)
            except (IOError, OSError) as e:
                print('[HdsDvbI] eroare scriere bouquet: %s' % e)
                return False
            _adauga_in_bouquets_master(master, cale, nume)

        _scrieStare(u['liste_info'], (u['tv'], u['radio'], urluri_puse), u['legaturi'], ascunse=ascunse,
            in_plus={'scoase': dict(u.get('scoase') or {})})
        self._ascunse = set(ascunse)
        print(_textBuchet(len(tv_all), len(radio_all), u.get('scoase') or {}, ascunse))

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
                if not numai_buchetele:
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
        return True

    def _dupaIncercare(self):
        """EPG2: dupa o incercare din casa, buchetul se rescrie (fara descarcare) numai daca s-au schimbat canalele
        ascunse: unul a cazut sau unul ascuns merge din nou."""
        u = self._ultim
        if u is None:
            return
        if set(_ascunse(u['tv'] + u['radio'])) == (self._ascunse or set()):
            return
        with self._lacat:
            if self._ultim is u:
                self._scrieBuchetele(u, numai_buchetele=True)

    def incearca_canalele(self, forteaza=False, numai=None):
        """Incearca din casa fluxurile canalelor (Components/HdsDvbIIncercare): numai pe cele neincercate sau
        incercate de mai mult de INCERCARE_S, ori toate cu forteaza; 'numai' = stari de incercat din nou (de pilda
        oprit_tara dupa pornirea VPN-ului). Pe firul celui care cheama (mereu un fir de fundal); una deodata.
        EPG2: cele ascunse (n-au trecut incercarea) se reiau dupa INCERCARE_ASCUNSE_S; fiecare canal are TERMEN_CANAL_S,
        toata incercarea TERMEN_INCERCARI_S (cele ramase se iau la urmatoarea); la sfarsit buchetul se rescrie daca s-a
        schimbat ce e ascuns."""
        I, D = _incercare(), _date()
        if I is None or D is None:
            return
        if not _INCERCARE['lacat'].acquire(False):
            return
        try:
            acum = time.time()
            de_incercat = []
            ascunsa = getattr(I, 'ascunsa', lambda st: False)
            # DRM1: un "merge" notat de o imagine care nu se uita in manifest dupa DRM se reia acum, nu peste 6 ore
            veche = getattr(D, 'incercareVeche', lambda url: False)
            for c in D.canale():
                st, _cod, ora = D.stareUrl(c.get('url', ''))
                if numai is not None:
                    if st in numai:
                        de_incercat.append(c)
                elif forteaza or not st or acum - ora > (INCERCARE_ASCUNSE_S if ascunsa(st) else INCERCARE_S) \
                        or acum < ora or (st == 'merge' and veche(c.get('url', ''))):
                    de_incercat.append(c)
            _INCERCARE.update(in_curs=True, facute=0, total=len(de_incercat), ora=acum)
            rezultate = {}
            # EPG2: "nu raspunde" (cod 0) spune ceva despre canal numai daca reteaua mergea: pana la primul raspuns HTTP
            # (oricare, si 403 sau 404) nimic nu se scrie, iar o incercare fara niciun raspuns (reteaua cazuta, routerul
            # repornit, VPN-ul abia oprit) lasa starile cum erau, deci nu goleste buchetul
            raspuns_http = False
            for c in de_incercat:
                if not self._activ:
                    break
                if time.time() - acum > TERMEN_INCERCARI_S:
                    print('[HdsDvbI] incercarea canalelor: termenul de %d s s-a terminat dupa %d din %d; restul la '
                          'urmatoarea' % (TERMEN_INCERCARI_S, _INCERCARE['facute'], len(de_incercat)))
                    break
                rezultate[c['url']] = I.incearca(c['url'], termen=TERMEN_CANAL_S)
                raspuns_http = raspuns_http or bool(rezultate[c['url']][1])
                _INCERCARE['facute'] += 1
                if len(rezultate) >= 10 and raspuns_http:
                    D.noteazaIncercari(rezultate)
                    rezultate = {}
            if rezultate and raspuns_http:
                D.noteazaIncercari(rezultate)
            elif rezultate:
                print('[HdsDvbI] incercarea canalelor: niciuna din cele %d adrese n-a raspuns (reteaua?); starile raman '
                      'cum erau' % len(rezultate))
        except Exception as e:
            print('[HdsDvbI] incercarea canalelor: %s' % e)
        finally:
            _INCERCARE.update(in_curs=False)
            _INCERCARE['lacat'].release()
        try:
            self._dupaIncercare()
        except Exception as e:
            print('[HdsDvbI] buchetul dupa incercare: %s' % e)
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
                    # DVJ: cand nu a raspuns nicio lista (internetul inca nepregatit la pornire), din nou curand
                    # (60 s, 2, 5, 10 min: HdsDvbISurse.REINCERCARI_RETEA_S), nu peste o ora
                    peste = getattr(self, '_reincearca_peste', None)
                    urmatoarea = time.time() + (min(peste, interval) if peste else interval)
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
# EPG2: canalele ascunse (n-au trecut incercarea) se reiau la fiecare reincarcare (o ora), ca sa revina repede; termenul
# unui canal (manifestul cerut, cu redirectari) si al intregii incercari, pe firul de fundal
INCERCARE_ASCUNSE_S = 3000
TERMEN_CANAL_S = 8
TERMEN_INCERCARI_S = 300
_INCERCARE = {'in_curs': False, 'facute': 0, 'total': 0, 'ora': 0, 'lacat': threading.Lock()}
CALE_STARE = '/etc/enigma2/hdsdvbi-stare.json'


T_NUME_BUCHET = N_('Canale de pe internet (DVB-I)')


def _numeTara(cod):
    S = _setari()
    if S is not None and cod:
        try:
            return S.numeTara(cod)
        except Exception:
            pass
    return cod or _t(N_('Alte liste'))


def _cuMarcaje(servicii, urluri_puse, url_uri, grupe):
    """TODO 1883: serviciile buchetului cu un marcaj (numele tarii) la inceputul fiecarei grupe de tara, cand
    serviciile vin din mai mult de o grupa; altfel lista ca atare. Grupa unui serviciu = tara listei lui
    (grupe: {adresa listei: cod}); listele fara grupa (predefinite, adrese puse de mana) merg sub "Alte liste"."""
    if not grupe or not servicii:
        return servicii
    def grupa(intrare):
        index_lista = urluri_puse.get(intrare[2], (None,))[0]
        adresa = url_uri[index_lista] if index_lista is not None and index_lista < len(url_uri) else None
        return grupe.get(adresa, '')
    toate = [grupa(x) for x in servicii]
    if len(set(toate)) < 2:
        return servicii
    rez, ultima, n = [], None, 0
    for intrare, g in zip(servicii, toate):
        if g != ultima:
            n += 1
            rez.append((n, _numeTara(g), None, 'marcaj'))
            ultima = g
        rez.append(intrare)
    return rez


def _numeBuchet():
    return _t(T_NUME_BUCHET)


def _ascunse(servicii):
    """EPG2: {adresa: starea incercarii} pentru canalele care n-au trecut incercarea din casa (oprite pentru tara, adrese
    moarte, fara raspuns): nu intra in buchet pana la urmatoarea incercare reusita. Neincercatele intra. {} fara
    componente (probele de pe PC fara ele: ca inainte)."""
    I, D = _incercare(), _date()
    if I is None or D is None or not hasattr(I, 'ascunsa'):
        return {}
    rez = {}
    for s in servicii:
        st = D.stareUrl(s[2])[0]
        if I.ascunsa(st):
            rez[s[2]] = st
    return rez


def _textBuchet(tv, radio, scoase, ascunse):
    """Randul din jurnal la fiecare buchet scris: cate canale, cate adrese scoase (clipuri, imagini de proba) si cate
    canale ascunse pana merg din nou, pe stari."""
    parti = ['[HdsDvbI] buchetul: %d TV, %d radio' % (tv, radio)]
    n = sum(scoase.values())
    if n:
        parti.append('scoase %d (clipuri %d, imagini de proba %d)' % (n, scoase.get('clip', 0), scoase.get('proba', 0)))
    if ascunse:
        st = {}
        for v in ascunse.values():
            st[v] = st.get(v, 0) + 1
        parti.append('ascunse pana merg din nou %d (oprite pentru tara %d, adrese moarte %d, fara raspuns %d)' % (
            len(ascunse), st.get('oprit_tara', 0), st.get('adresa_moarta', 0), st.get('nu_raspunde', 0)))
        if st.get('drm'):
            # DRM1: criptate cu DRM (receptorul n-are decriptor)
            parti.append('din ele protejate DRM %d' % st['drm'])
    return '; '.join(parti)


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


def _surse():
    """starea listelor care nu raspund (Components/HdsDvbISurse), sau None (probele de pe PC fara el: ca inainte)"""
    try:
        from Components import HdsDvbISurse
        return HdsDvbISurse.surse(os.path.join(os.path.dirname(CALE_STARE), 'hdsdvbi-surse.json'))
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


def _scrieStare(liste_info, canale, legaturi_brute, pastreaza_canalele=False, in_plus=None, ascunse=None):
    """Starea pentru lista de canale, bara, trecerea pe internet si pagina web (Components/HdsDvbIDate). in_plus:
    chei in plus (fara_liste, tara: tara de acum nu are liste; scoase). ascunse (EPG2): {adresa: stare} pentru canalele
    care nu sunt in buchet; raman in stare cu "ascuns" si fara loc in buchet ("nr" None)."""
    ascunse = ascunse or {}
    D = _date()
    if D is None:
        return
    vechi = D.stare(CALE_STARE) if pastreaza_canalele else {}
    stare = {'ora': int(time.time()), 'liste': liste_info, 'lungi': _SARITE_LUNGI[0],
             'canale': list(vechi.get('canale') or []), 'legaturi': dict(vechi.get('legaturi') or {})}
    if pastreaza_canalele and isinstance(vechi.get('scoase'), dict):
        # EPG2: cand toate listele cad, canalele raman, deci si ce s-a scos din ele
        stare['scoase'] = dict(vechi['scoase'])
    stare.update(in_plus or {})
    if canale is not None:
        tv_all, radio_all, urluri_puse = canale
        L = _legare()
        lista_canale = []
        nr_tv = nr_radio = 0
        id_dupa_lista_nume = {}
        for idx, nume, url_flux, tip in tv_all + radio_all:
            index_lista, _intrare, lcn = urluri_puse[url_flux]
            if url_flux in ascunse:
                nr = None
            elif tip == 'radio':
                nr_radio += 1
                nr = nr_radio
            else:
                nr_tv += 1
                nr = nr_tv
            lista_canale.append({'id': idx, 'nume': nume, 'url': url_flux, 'tip': tip, 'lcn': lcn, 'nr': nr,
                                 'lista': liste_info[index_lista]['adresa'], 'sat': '',
                                 'ref': ref_serviciu(idx, url_flux, tip), 'ascuns': ascunse.get(url_flux, ''),
                                 'tara': liste_info[index_lista].get('tara', '')})
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
    """Buchetul "Canale de pe internet (DVB-I)" e in lista de canale din fabrica, si fara nicio lista aleasa: gol, cu
    explicatia din lista (Components/HdsIndexCanale, felul 'dvbi'). Scos de om din lista (_scoasa) nu se mai pune.
    -> True daca s-a scris ceva acum."""
    scris = False
    if _scoasa('tv'):
        return scris
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


def legaInLista(da):
    """Randul "Arată lista în lista de canale" (Components/HdsDvbISetari.puneInLista, semnul deja scris): cu da
    buchetele DVB-I se leaga la loc (TV si gol, radio daca are fisier), cu nu se scot din bouquets.tv / bouquets.radio
    si fisierele lor se sterg, ca la stergerea din lista de canale. Apoi lista din memorie se reincarca. Pe firul
    enigma2. -> True daca s-a schimbat ceva."""
    schimbat = False
    if da:
        schimbat = _asiguraBuchetul()
        if not _scoasa('radio') and os.path.exists(CALE_BOUQUET_RADIO):
            are = False
            try:
                with open(CALE_BOUQUETS_RADIO, 'r', encoding='utf-8', errors='replace') as f:
                    are = os.path.basename(CALE_BOUQUET_RADIO) in f.read()
            except (IOError, OSError):
                pass
            if not are:
                _adauga_in_bouquets_master(CALE_BOUQUETS_RADIO, CALE_BOUQUET_RADIO, 'DVB-I Radio')
                schimbat = True
    else:
        for master, cale in ((CALE_BOUQUETS_TV, CALE_BOUQUET_TV), (CALE_BOUQUETS_RADIO, CALE_BOUQUET_RADIO)):
            if _scoate_din_bouquets_master(master, cale):
                schimbat = True
            try:
                os.unlink(cale)
                schimbat = True
            except OSError:
                pass
    if schimbat:
        try:
            from enigma import eDVBDB
            eDVBDB.getInstance().reloadBouquets()
        except Exception as e:
            print('[HdsDvbI] reloadBouquets: %s' % e)
        _anuntaSchimbarea()
    return schimbat


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
            _manager.fetch_si_actualizeaza(forteaza=True)
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

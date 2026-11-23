# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Legatura DAB+ si DVB-T2 din satelit cu imaginea HDSatelit: pornirea, oprirea si ferestrele din meniu.

Numai acest modul tine de imagine; restul pachetului e codul comun, acelasi cu al pluginului pentru alte imagini.
In imagine nu exista descriptori de plugin si nici steag de dezactivare:
  porneste(sesiune)   chemat din mytest.py dupa Navigation si Session, in firul principal: fiecare controlor (DAB,
                      T2) se pune in Navigation.playServiceExtensions / recordServiceExtensions si in nav.event;
                      captura se leaga de tasta (numai daca setarea e pornita). Nimic greu: releele pornesc abia la
                      zap pe un post al nostru; curatarea releelor ramase, buchetele puse prima data si rescrierea o
                      singura data a referintelor vechi din buchete (port, forma sunetului DAB; SEMN_PORT) si a
                      marcajelor ansamblurilor („MUX DAB+: ...”; SEMN_MARCAJE) merg in fir de fundal; la fel
                      buchetele scrise in alta limba decat a interfetei (SEMN_LIMBA, retradu), si la fiecare
                      schimbare a limbii (Components.Language), si buchetele facute dupa alta lista din imagine
                      (SEMN_LISTA, reface_daca_lista_noua), o data dupa o actualizare.
  opreste()           chemat din mytest.py la iesirea enigma2: marcajele protectiei la pornire se sterg primele
                      (sterge_marcajele), apoi releele se opresc, tunerul se elibereaza.
  descarcarea zilnica a listelor (liste.Zilnic) porneste aici; merge numai cu setarea ei pornita.
  server8001          serverul local de flux pe 127.0.0.1:8001 (pornit aici): baza nu are streamserver, iar releele
                      cer fluxul serviciului purtator acolo.
  controlor_dab(), controlor_t2()   controlorii (acelasi obiect pe tot procesul), pentru ferestre si web.
  inainte_de_scanare(), cine_tine_tunerul()   o scanare de canale (Components/ServiceScan.py) primeste tunerul de
                      satelit inainte de start; daca tot nu-l primeste, ce il mai tine.
Paznicul pluginului (bataia din /tmp/hds-bataie) nu porneste in imagine: imaginea are paznicul ei
(Components/HdsPaznic.py si hds-watchdog). Caile de plugin ale controlorilor sunt dab/ si t2/ de langa modul
(motor/, date/, bin/).
"""
import os

from . import coordonator, jurnal
from . import profil as _profil
from .limba import _ as _tr

AICI = os.path.dirname(os.path.abspath(__file__))
CALE_DAB = os.path.join(AICI, 'dab')
CALE_T2 = os.path.join(AICI, 't2')
# fisierele pluginurilor din imaginile 0.1.0-0.1.6 (steagul de dezactivare si contorul de esecuri la incarcare):
# in imagine nu mai inseamna nimic, se sterg o data daca au ramas
FISIERE_VECHI = ('/etc/enigma2/hdsdab.dezactivat', '/etc/enigma2/hdst2mi.dezactivat',
                 '/etc/enigma2/hdsdab.esecuri', '/etc/enigma2/hdst2mi.esecuri')

# semnul (in dosarul de date al fiecarui fel) ca buchetul a fost pus o data in lista de canale: un buchet scos de om
# din lista nu revine la pornire; o scanare cu rezultat il pune iar (buchete.reface)
SEMN_BUCHET = 'buchet-pus'
# semnul (in dosarul de date al profilului) ca referintele scrise cu porturi vechi in buchetele utilizatorului au
# primit o data portul curent; numele poarta portul, deci o mutare viitoare pe alt port rescrie din nou
SEMN_PORT = 'port-%d'
# la DAB in forma TS semnul poarta si forma (buchete.forma_dab): trecerea pe TS rescrie o data posturile scrise
# pentru 4097, si cand portul era deja cel curent
SEMN_PORT_FORMA = 'port-%d-%s'

# semnul (in dosarul de date al profilului) ca marcajele ansamblurilor din buchetul nostru au primit o data numele de
# acum („MUX DAB+: <ansamblu>”, „MUX DVB-T2: <nume>”, buchete.redenumeste_marcajele)
SEMN_MARCAJE = 'marcaje-mux'

# semnul (in dosarul de date al profilului) cu limba in care s-a scris buchetul: numele lui si numele multiplexurilor
# („MUX DVB-T2: Dasto Semtel (Bosna i Hercegovina)”, nume.nume_feed) sunt scrise in fisier in limba receptorului. La
# pornire, daca limba e alta decat cea din semn (si la prima pornire a unei versiuni care scria numele in romana), si
# la fiecare schimbare a limbii (Components.Language), buchetul se reface in fundal: numele noastre trec in limba noua,
# referintele, ordinea si numele puse de om raman (buchete.compune)
SEMN_LIMBA = 'limba-buchet'

# semnul (in dosarul de date al profilului) cu amprenta listei din imagine (date/frecvente.json) dupa care s-a scris
# buchetul. O actualizare a imaginii poate aduce alta lista (programe noi intr-un flux, un canal mutat, un flux cu id
# nou): la prima pornire cu ea buchetul se reface o data, in fundal, ca schimbarea sa ajunga in lista de canale fara
# scanare si fara alt pas al omului; referintele, ordinea si numele puse de om raman (buchete.compune)
SEMN_LISTA = 'lista-buchet'

# DAB in imagine: sunetul ca TS cu un program pe tipul 1 (eHdsFluxHttp, decodorul placii: AAC-LATM si MP2). Pe
# receptor 4097 nu poate suna: gstreamer nu are tsdemux si nici decodor AAC, iar dvbaudiosink refuza LOAS/LATM
_profil.DAB.sunet_ts = True

_stare = {'sesiune': None, 'fundal': None, 'zilnic': None}


def profiluri():
    """(profil, calea pluginului) pentru DAB si T2, in ordinea pornirii."""
    return ((_profil.DAB, CALE_DAB), (_profil.T2, CALE_T2))


def cale_pentru(tip):
    """'dab' sau 't2' -> dosarul cu motor/ si date/ din imagine."""
    return CALE_DAB if tip == 'dab' else CALE_T2


def controlor_dab():
    from .intrare import controlor
    return controlor(_profil.DAB, CALE_DAB)


def controlor_t2():
    from .intrare import controlor
    return controlor(_profil.T2, CALE_T2)


def dupa_scanare(pozitii=None):
    """Dupa o scanare obisnuita (Components/ServiceScan.py, la sfarsit): daca lista DVB-T2 are fluxuri cu programele
    scrise in ea (felul abertis de pe 30W si fluxurile T2-MI invatate pe receptoarele noastre: Cipru, Ucraina, Rai) sau
    invatate de acest receptor (servicii.json) pe una din pozitiile scanate (`pozitii`, None = oricare), buchetul lor si
    purtatorii din lamedb se refac in fundal, ca transponderele prinse acum sa-si aiba canalele in lista fara alt pas.
    Nu arunca; nimic de facut = nicio scriere."""
    try:
        poz = set(int(p) % 3600 for p in pozitii) if pozitii is not None else None
        if poz is not None and not poz:
            return False                      # numai cablu sau terestru
        from . import buchete
        c = controlor_t2()
        invatate = set(k for k, v in buchete.citeste_servicii(c.profil).items() if (v or {}).get('servicii'))
        for tp in c.lista().get('transpondere', []):
            if (poz is None or int(tp.get('pozitie') or -1) in poz) and \
                    any(f.get('programe') or buchete._curata_id(f.get('id')) in invatate
                        for f in tp.get('feeduri', [])):
                c.reface_in_fundal()
                jurnal.noteaza('imagine', 'dupa scanare: buchetele si purtatorii DVB-T2 refacuti in fundal')
                return True
    except Exception:
        jurnal.eroare('imagine', 'refacerea dupa scanare')
    return False


def buchete_dupa_scanare(pozitii, lista=None, memorate=None, prinse=None):
    """Pentru rezumatul scanarii obisnuite (Screens/ServiceScan.hdsIndiciuT2): pe care din pozitiile scanate fluxurile
    DVB-T2 prin satelit intra singure in lista de canale (dupa_scanare): fluxuri cu programele stiute (scrise in lista
    sau invatate de receptor) pe un transponder pe care receptorul il prinde. -> {pozitie: {'buchete': [numele
    buchetelor, in limba meniului], 'tp': [(frecventa kHz, polarizare 'H'/'V'/'L'/'R')]}}; pozitiile fara asa ceva
    lipsesc. lista / memorate / prinse: pentru probe. Nu arunca."""
    rez = {}
    try:
        from . import buchete, liste
        poz = set(int(p) % 3600 for p in pozitii or () if isinstance(p, int))
        if not poz:
            return rez
        prof = _profil.T2
        if lista is None:
            lista = controlor_t2().lista()
        if memorate is None:
            memorate = buchete.citeste_servicii(prof)
        if prinse is None:
            prinse = buchete.transpondere_prinse(prof)
        for tp in lista.get('transpondere', []):
            p = int(tp.get('pozitie') or -1)
            if p not in poz or not buchete.prins(tp, prinse):
                continue
            for f in tp.get('feeduri', []):
                if f.get('tip') != 't2' or f.get('stare_verificare') == liste.STARE_NEDECODABIL:
                    continue
                if not (f.get('programe') or (memorate.get(buchete._curata_id(f.get('id'))) or {}).get('servicii')):
                    continue
                nume = buchete.NUME_BUCHET_ABERTIS if buchete.e_abertis(f) else _tr(prof.nume_buchet)
                x = rez.setdefault(p, {'buchete': [], 'tp': []})
                if nume not in x['buchete']:
                    x['buchete'].append(nume)
                cheie = (int(tp.get('frecventa') or 0), tp.get('pol'))
                if cheie not in x['tp']:
                    x['tp'].append(cheie)
    except Exception:
        jurnal.eroare('imagine', 'buchetele dupa scanare')
    return rez


def _tine_ceva(c):
    """Controlorul tine tunerul de satelit sau il poate lua: post pornit sau tinut, releu care ruleaza (cu sesiunea
    lui 8001), canal brut."""
    return c.stare != 'oprit' or c.tuner.tinut() or c.releu.ruleaza()


def inainte_de_scanare(motiv='Tunerul a fost dat căutării de canale.'):
    """Chemat de Components/ServiceScan.py chiar inainte de eComponentScan.start, care ia tunerul cu
    allocateRawChannel(feid) (lib/components/scan.cpp) si cade daca il tine altcineva. Ecranul ServiceScan opreste
    serviciul cu nav.stopService(), care nu trece prin extensiile de zap: un program DVB-T2 (sau un post DAB+) pornit
    inainte si-ar tine releul si sesiunea 8001 (o inregistrare pe purtator) pana il vede paza controlorului (10 s) si
    inca pana la TINERE_8001_S dupa, iar cautarea ar cadea pe loc cu „tunerul nu a putut fi folosit” (de pilda dupa
    „Ascultă” in „DVB-T2 prin satelit”, apoi „După satelit” din acelasi meniu). Aici controlorii care tin ceva cedeaza
    acum, sincron, ca la un zap pe alt transponder (releul, sesiunile 8001 oprite pe loc, canalul brut); o pornire
    amanata a altui canal (dupa eliberarea purtatorului) se anuleaza, fiindca tunerul il ia cautarea. `motiv` ajunge in
    jurnal si, la un post DAB+ ascultat in browser, in pagina (HdsTransmisie.textEroare).
    -> felurile ('dab', 't2') care au cedat. Nu arunca."""
    from . import intrare
    cedate = []
    for prof, _cale in profiluri():
        c = intrare._controlori.get(prof.nume)
        if c is None:
            continue
        try:
            c._anuleaza_eliberarea()
            if _tine_ceva(c):
                # ce tinea, scris inainte de cedare: proba de pe receptor arata ce anume a oprit cautarea
                ce = 'stare %s, mod %s, releu %s, canal brut %s, sesiuni 8001 %s' % (
                    c.stare, c.mod, 'pornit' if c.releu.ruleaza() else 'oprit', 'da' if c.tuner.tinut() else 'nu',
                    _sesiuni_8001(c._ref_purtator))
                c.cedeaza(motiv)
                cedate.append(prof.tip)
                jurnal.noteaza(prof.eticheta, 'tunerul dat scanarii de canale (%s)' % ce)
        except Exception:
            jurnal.eroare(prof.eticheta, 'tunerul pentru scanarea de canale')
    return cedate


def _sesiuni_8001(ref):
    """Sesiunile serverului local 8001 de pe purtatorul `ref` (toate, fara ref), sau '?' daca nu se poate afla."""
    try:
        from . import server8001
        n = server8001.sesiuni_deschise(ref or None)
        return '?' if n is None else n
    except Exception:
        return '?'


def cine_tine_tunerul():
    """Dupa o scanare de canale care n-a putut lua tunerul (Components/ServiceScan.py): ce tine inca imaginea pe el,
    din memorie. -> 't2' / 'dab' (un controlor tine inca ceva), '8001' (sesiuni ale serverului local de flux: Stream
    Relay, alt aparat din retea) sau None (nu stie). Nu arunca."""
    from . import intrare
    for prof, _cale in profiluri():
        c = intrare._controlori.get(prof.nume)
        try:
            if c is not None and _tine_ceva(c):
                return prof.tip
        except Exception:
            jurnal.eroare(prof.eticheta, 'cine tine tunerul')
    try:
        from . import server8001
        if server8001.sesiuni_deschise():
            return '8001'
    except Exception:
        jurnal.eroare('imagine', 'sesiunile 8001 dupa scanare')
    return None


def _sterge_fisierele_vechi():
    for cale in FISIERE_VECHI:
        try:
            if os.path.exists(cale):
                os.remove(cale)
                jurnal.noteaza('imagine', 'sters %s (ramas de la pluginul de dinainte)' % cale)
        except OSError:
            pass


def de_pus():
    """Profilurile al caror buchet n-a fost pus inca in lista de canale (cateva os.stat, pe firul principal)."""
    return [prof for prof, _cale in profiluri() if not os.path.exists(os.path.join(prof.director, SEMN_BUCHET))]


def pune_buchetele(profiluri_, director_enigma2=None):
    """In fir: pentru fiecare profil, o singura data, buchetul („#NAME DAB+ din satelit”, gol pana la prima scanare)
    si randul lui din bouquets.radio / bouquets.tv, ca lista de canale sa-l arate, cu explicatia, inainte de prima
    scanare. Un fisier care exista deja nu se rescrie. -> True daca s-a scris ceva (buchetele trebuie reincarcate)."""
    from . import buchete
    director = director_enigma2 or buchete.DIRECTOR_ENIGMA2
    scris = False
    for prof in profiluri_:
        cale = os.path.join(director, prof.buchet)
        if not os.path.exists(cale):
            buchete.scrie_atomic(cale, ('#NAME %s\n' % _tr(prof.nume_buchet)).encode('utf-8'))
            scris = True
        if buchete.asigura_index(prof, director):
            scris = True
        buchete.scrie_atomic(os.path.join(prof.director, SEMN_BUCHET), b'')
        jurnal.noteaza(prof.eticheta, 'buchetul pus in lista de canale')
    return scris


def semn_rescriere(prof):
    """Numele semnului trecerii prin rescriere: portul, iar la DAB in forma TS si forma (port-8898-ts)."""
    from . import buchete
    if prof.tip == 'dab' and buchete.forma_dab(prof) == buchete.FORMA_TS:
        return SEMN_PORT_FORMA % (prof.port, buchete.FORMA_TS)
    return SEMN_PORT % prof.port


def _buchete_dupa_semn(semn, director_enigma2=None):
    """True cand un buchet al utilizatorului (userbouquet.*.tv / .radio) e scris dupa semnul trecerii: o copie a
    setarilor pusa la loc de mana sau un editor de canale pe PC pot aduce referinte vechi dupa prima pornire. Numai
    os.stat (pe firul principal, la pornire); False cand semnul sau dosarul nu se pot citi."""
    from . import buchete
    director = director_enigma2 or buchete.DIRECTOR_ENIGMA2
    try:
        prag = os.stat(semn).st_mtime
        nume = os.listdir(director)
    except OSError:
        return False
    for n in nume:
        if n.startswith('userbouquet.') and n.endswith(('.tv', '.radio')):
            try:
                if os.stat(os.path.join(director, n)).st_mtime > prag:
                    return True
            except OSError:
                continue
    return False


def de_rescris_porturile(director_enigma2=None):
    """Profilurile cu referinte de adus la forma de acum (porturi vechi, forma DAB) ale caror buchete n-au trecut
    inca prin rescriere sau au fost scrise dupa ultima trecere (cate un os.stat). O trecere care nu gaseste nimic
    scrie semnul din nou, deci buchetele schimbate de om (favorite) dau cel mult o trecere ieftina, in fir."""
    from . import buchete
    rez = []
    for prof, _cale in profiluri():
        if not buchete.are_referinte_de_rescris(prof):
            continue
        semn = os.path.join(prof.director, semn_rescriere(prof))
        if not os.path.exists(semn) or _buchete_dupa_semn(semn, director_enigma2):
            rez.append(prof)
    return rez


def rescrie_porturile(profiluri_, director_enigma2=None):
    """In fir, sub zavorul scrierilor: referintele vechi din toate buchetele utilizatorului (favorite, buchetele lui,
    al nostru) trec in forma de acum: portul curent si, la DAB, tipul dupa forma sunetului
    (buchete.rescrie_referinte_vechi). Semnul se scrie numai dupa o trecere fara eroare, deci o scriere cazuta se
    reia la urmatoarea pornire. Profilul cu un buchet necitit sau nescris (randul e in jurnal, scris de buchete)
    ramane fara semn, celelalte profiluri merg mai departe, iar la sfarsit se arunca prima eroare (_porturi_rescrise
    reincarca totusi buchetele). -> True daca s-a rescris vreun buchet (buchetele trebuie reincarcate in firul
    principal)."""
    from . import buchete
    scris = False
    eroare = None
    for prof in profiluri_:
        try:
            if buchete.rescrie_referinte_vechi(prof, director_enigma2):
                scris = True
        except (IOError, OSError) as e:
            eroare = eroare or e
            continue
        buchete.scrie_atomic(os.path.join(prof.director, semn_rescriere(prof)), b'')
    if eroare is not None:
        raise eroare
    return scris


def de_redenumit_marcajele():
    """Profilurile al caror buchet exista si n-a trecut inca prin redenumirea marcajelor (cate doua os.stat)."""
    from . import buchete
    return [prof for prof, _cale in profiluri()
            if os.path.exists(os.path.join(buchete.DIRECTOR_ENIGMA2, prof.buchet))
            and not os.path.exists(os.path.join(prof.director, SEMN_MARCAJE))]


def redenumeste_marcajele(profiluri_, director_enigma2=None):
    """In fir, sub zavorul scrierilor: marcajele ansamblurilor din buchetul fiecarui profil primesc o data numele de
    acum (buchete.redenumeste_marcajele). Semnul se scrie numai dupa o trecere fara eroare (o scriere cazuta se reia la
    pornirea urmatoare); prima eroare se arunca la sfarsit, dupa celelalte profiluri. -> True daca s-a scris ceva."""
    from . import buchete
    scris = False
    eroare = None
    for prof in profiluri_:
        try:
            if buchete.redenumeste_marcajele(prof, director_enigma2):
                scris = True
        except (IOError, OSError) as e:
            eroare = eroare or e
            continue
        buchete.scrie_atomic(os.path.join(prof.director, SEMN_MARCAJE), b'')
    if eroare is not None:
        raise eroare
    return scris


def _marcaje_redenumite(ok, rez):
    if not ok:
        jurnal.noteaza('imagine', 'marcajele buchetelor nu s-au putut redenumi (se reia la pornirea urmatoare): %s'
                       % rez)
    if not ok or rez:
        from . import buchete
        buchete.reincarca_buchete()


def _porturi_rescrise(ok, rez):
    if not ok:
        # o parte poate fi rescrisa (alt buchet, alt profil): enigma2 citeste buchetele din nou oricum
        jurnal.noteaza('imagine', 'referintele cu port vechi nu s-au putut rescrie toate (se reia la pornirea '
                       'urmatoare): %s' % rez)
        from . import buchete
        buchete.reincarca_buchete()
    elif rez:
        from . import buchete
        buchete.reincarca_buchete()


def _buchete_puse(ok, rez):
    if not ok:
        jurnal.noteaza('imagine', 'buchetele nu s-au putut pune: %s' % rez)
    elif rez:
        from . import buchete
        buchete.reincarca_buchete()


def limba_acum():
    """Limba interfetei („it_IT”), sau „” fara Components.Language."""
    from . import limba
    return limba.limba_enigma2() or ''


def _limba_din_semn(prof):
    """Limba din semn, sau None fara semn (scrierile raman in buchete.py: imagine.py nu deschide fisiere)."""
    from . import buchete
    text = buchete._citeste_text(os.path.join(prof.director, SEMN_LIMBA))
    if text is None:
        return None
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'replace')
    return text.strip()


def de_tradus(limba_=None, director_enigma2=None):
    """Profilurile al caror buchet exista si a fost scris in alta limba decat cea de acum (fara semn: scris de o
    versiune care punea numele in romana). Cateva os.stat si un fisier mic, pe firul principal."""
    from . import buchete
    limba_ = limba_acum() if limba_ is None else limba_
    if not limba_:
        return []
    director = director_enigma2 or buchete.DIRECTOR_ENIGMA2
    rez = []
    for prof, _cale in profiluri():
        if not os.path.exists(os.path.join(director, prof.buchet)) or _limba_din_semn(prof) == limba_:
            continue
        # un buchet scos de om din lista (fisierul ramas, de pilda dupa un editor de canale pe PC) nu revine: refacerea
        # l-ar pune iar in bouquets.* (buchete.asigura_index), ca la pornire (SEMN_BUCHET)
        index = buchete._citeste_text(os.path.join(director, prof.index_buchete))
        if isinstance(index, bytes):
            index = index.decode('utf-8', 'replace')
        if index and ('"%s"' % prof.buchet) in index:
            rez.append(prof)
    return rez


def traduce_buchetele(lucrari, limba_, director_enigma2=None):
    """In fir, sub zavorul scrierilor: lucrari = [(profil, lista unita)]; fiecare buchet refacut in limba de acum
    (buchete.reface, fara reincarcare), apoi semnul limbii. Un profil cazut nu primeste semnul (se reia la pornirea
    urmatoare). -> True daca s-a schimbat vreun buchet."""
    from . import buchete
    schimbat = False
    for prof, lista in lucrari:
        rez = buchete.reface(prof, lista, director_enigma2, reincarca=False)
        if rez.get('eroare'):
            continue
        schimbat = schimbat or bool(rez.get('schimbat'))
        buchete.scrie_atomic(os.path.join(prof.director, SEMN_LIMBA), limba_.encode('utf-8'))
        jurnal.noteaza(prof.eticheta, 'buchetul scris in limba %s' % limba_)
    return schimbat


def _buchete_traduse(ok, rez):
    if not ok:
        jurnal.noteaza('imagine', 'buchetele nu s-au putut scrie in limba noua (se reia la pornirea urmatoare): %s' % rez)
    if not ok or rez:
        from . import buchete
        buchete.reincarca_buchete()


def retradu(*_a):
    """Pe firul principal (la pornire si din Components.Language la schimbarea limbii): buchetele scrise in alta limba
    se refac in fundal, cu lista unita a fiecarui controlor. Nimic de facut de om. Nu arunca."""
    try:
        from .intrare import _controlori
        limba_ = limba_acum()
        lucrari = []
        for prof in de_tradus(limba_):
            c = _controlori.get(prof.nume)
            if c is not None:
                lucrari.append((prof, c.lista(forteaza=True)))
        if lucrari:
            _sub_zavor_in_fundal(traduce_buchetele, _buchete_traduse, lucrari, limba_)
    except Exception:
        jurnal.eroare('imagine', 'buchetele in limba noua')


def amprenta_listei(cale):
    """sha1 al listei din imagine (cateva zeci de KB, citita in fir), sau None daca nu se poate citi. Citirea ramane
    in buchete.py (imagine.py nu deschide fisiere)."""
    import hashlib
    from . import buchete
    text = buchete._citeste_text(cale)
    if text is None:
        return None
    if not isinstance(text, bytes):
        text = text.encode('utf-8', 'surrogateescape')
    return hashlib.sha1(text).hexdigest()


def de_refacut_dupa_lista(director_enigma2=None):
    """[(profil, calea listei din imagine)] pentru profilurile cu cel putin un buchet al lor care exista si e in lista
    de canale: prof.buchet (DVB-T2 sau DAB+ din satelit), iar la T2 si BUCHET_ABERTIS (omul poate pastra numai unul).
    Cateva os.stat si indexul, pe firul principal; amprenta listei se socoteste in fir (reface_dupa_lista), iar
    refacerea nu pune in index un buchet scos de om."""
    from . import buchete
    director = director_enigma2 or buchete.DIRECTOR_ENIGMA2
    rez = []
    for prof, cale in profiluri():
        index = buchete._citeste_text(os.path.join(director, prof.index_buchete))
        if isinstance(index, bytes):
            index = index.decode('utf-8', 'replace')
        if not index:
            continue
        fisiere = [prof.buchet] + ([buchete.BUCHET_ABERTIS] if prof.tip == 't2' else [])
        if any(os.path.exists(os.path.join(director, f)) and ('"%s"' % f) in index for f in fisiere):
            rez.append((prof, os.path.join(cale, 'date', 'frecvente.json')))
    return rez


def reface_dupa_lista(lucrari, director_enigma2=None):
    """In fir, sub zavorul scrierilor: lucrari = [(profil, calea listei din imagine, arata_nedecodabile)]. Pentru
    fiecare profil a carui lista din imagine are alta amprenta decat cea din SEMN_LISTA (sau fara semn): lista unita
    citita din nou, buchetul refacut (buchete.reface, fara reincarcare), apoi semnul. Un profil cazut ramane fara semn
    (se reia la pornirea urmatoare). -> True daca s-a schimbat vreun buchet."""
    from . import buchete, liste
    schimbat = False
    for prof, incorporat, arata in lucrari:
        amprenta = amprenta_listei(incorporat)
        if amprenta is None:
            continue
        semn = os.path.join(prof.director, SEMN_LISTA)
        vechi = buchete._citeste_text(semn)
        if isinstance(vechi, bytes):
            vechi = vechi.decode('ascii', 'replace')
        if vechi is not None and vechi.strip() == amprenta:
            continue
        lista = liste.incarca(prof.tip, prof.director, incorporat)
        if not arata:
            lista = liste.fara_nedecodabile(lista)
        rez = buchete.reface(prof, lista, director_enigma2, reincarca=False, index=False)
        if rez.get('eroare'):
            continue
        schimbat = schimbat or bool(rez.get('schimbat'))
        buchete.scrie_atomic(semn, amprenta.encode('ascii'))
        jurnal.noteaza(prof.eticheta, 'buchetul refacut dupa lista din imagine (%s)' % amprenta[:12])
    return schimbat


def _buchete_dupa_lista(ok, rez):
    if not ok:
        jurnal.noteaza('imagine', 'buchetele nu s-au putut reface dupa lista din imagine (se reia la pornirea '
                       'urmatoare): %s' % rez)
    if not ok or rez:
        from . import buchete
        buchete.reincarca_buchete()


def reface_daca_lista_noua():
    """Pe firul principal, la pornire: buchetele facute dupa alta lista din imagine se refac o data, in fundal. Nimic
    de facut de om. Nu arunca."""
    try:
        from .intrare import _controlori
        lucrari = []
        for prof, incorporat in de_refacut_dupa_lista():
            c = _controlori.get(prof.nume)
            if c is None:
                continue
            try:
                arata = bool(c._arata_nedecodabile())
            except Exception:
                arata = False
            lucrari.append((prof, incorporat, arata))
        if lucrari:
            _sub_zavor_in_fundal(reface_dupa_lista, _buchete_dupa_lista, lucrari)
    except Exception:
        jurnal.eroare('imagine', 'buchetele dupa lista din imagine')


def _leaga_limba():
    """retradu() la fiecare schimbare a limbii interfetei (o singura legatura pe proces)."""
    if _stare.get('limba_legata'):
        return
    from Components.Language import language
    language.addCallback(retradu)
    _stare['limba_legata'] = True


def porneste(sesiune):
    """Extensiile de zap si de inregistrare pentru DAB si T2, apoi captura pe tasta. Nu arunca."""
    from .intrare import controlor
    _stare['sesiune'] = sesiune
    try:
        # setarile comune exista inaintea primului zap: rezerva de pornire o citeste nucleul la fiecare post
        from . import captura
        captura.configureaza()
    except Exception:
        jurnal.eroare('imagine', 'setarile comune')
    for prof, cale in profiluri():
        try:
            controlor(prof, cale).instaleaza(sesiune)
            jurnal.noteaza(prof.eticheta, 'sesiune pornita (imagine)')
        except Exception:
            jurnal.eroare(prof.eticheta, 'pornirea in imagine')
    try:
        coord = coordonator.obtine()
        if coord.ia_captura(_profil.DAB.nume):
            from . import captura
            cap = captura.obtine(coord)
            cap.sesiune = sesiune
            cap.leaga_tasta()
    except Exception:
        jurnal.eroare('imagine', 'captura pe tasta')
    _sterge_fisierele_vechi()
    try:
        # descarcarea zilnica a listelor (numai daca setarea e pornita; prima privire la 5 minute dupa pornire)
        from . import liste
        _stare['zilnic'] = liste.zilnic()
        _stare['zilnic'].porneste()
    except Exception:
        jurnal.eroare('imagine', 'descarcarea zilnica')
    try:
        # releele cer fluxul purtatorului la 127.0.0.1:8001; baza imaginii nu are streamserver (server8001.py)
        from . import server8001
        server8001.porneste()
    except Exception:
        jurnal.eroare('imagine', 'serverul local de flux')
    try:
        lipsa = de_pus()
        if lipsa:
            _sub_zavor_in_fundal(pune_buchetele, _buchete_puse, lipsa)
    except Exception:
        jurnal.eroare('imagine', 'buchetele in lista de canale')
    try:
        vechi = de_rescris_porturile()
        if vechi:
            _sub_zavor_in_fundal(rescrie_porturile, _porturi_rescrise, vechi)
    except Exception:
        jurnal.eroare('imagine', 'referintele cu port vechi')
    try:
        marcaje = de_redenumit_marcajele()
        if marcaje:
            _sub_zavor_in_fundal(redenumeste_marcajele, _marcaje_redenumite, marcaje)
    except Exception:
        jurnal.eroare('imagine', 'marcajele buchetelor')
    # numele buchetelor si ale multiplexurilor in limba receptorului (SEMN_LIMBA), acum si la schimbarea limbii
    retradu()
    # buchetele facute dupa lista de dinainte a imaginii (SEMN_LISTA): o data, dupa o actualizare care aduce alta lista
    reface_daca_lista_noua()
    try:
        _leaga_limba()
    except Exception:
        jurnal.eroare('imagine', 'legatura cu limba interfetei')


def _sub_zavor_in_fundal(functie, la_gata, *argumente):
    """functie(*argumente) intr-un fir, sub acelasi zavor ca celelalte scrieri ale buchetelor si ale lui bouquets.*
    (reface, scanarea); la_gata(ok, rezultat) in firul principal."""
    from . import fundal, pornire
    if _stare['fundal'] is None:
        _stare['fundal'] = fundal.Fundal('imagine')
    _stare['fundal'].lanseaza(lambda *a: pornire._sub_zavor(functie, *a), la_gata, *argumente)


def sterge_marcajele():
    """Iesirea curata a enigma2 (repornirea interfetei din meniu sau din web, TryQuitMainloop, SIGTERM la oprirea
    receptorului): marcajele protectiei la pornire (marcaj.py) ale ambelor feluri se sterg PRIMELE, inaintea oricarei
    opriri lente (releu, tuner, sesiuni 8001). Altfel, un proces omorat in timpul opririi (init trimite SIGKILL la
    scurt timp dupa SIGTERM) lasa marcajul unui post pornit de curand, iar pornirea urmatoare il ia drept o cadere a
    interfetei si nu mai porneste postul. Nu arunca."""
    from . import intrare, marcaj
    for prof, _cale in profiluri():
        try:
            c = intrare._controlori.get(prof.nume)
            if c is not None:
                c._marcaj_la = None
            if marcaj.sterge(prof.director):
                jurnal.noteaza(prof.eticheta, 'marcaj de pornire sters (iesirea enigma2)')
        except Exception:
            jurnal.eroare(prof.eticheta, 'marcajul la iesirea enigma2')


def opreste():
    """La iesirea enigma2: marcajele protectiei sterse, apoi releele oprite si tunerul dat inapoi. Nu arunca."""
    from . import intrare
    sterge_marcajele()
    try:
        _stare['zilnic'] and _stare['zilnic'].opreste()
    except Exception:
        jurnal.eroare('imagine', 'oprirea descarcarii zilnice')
    for prof, _cale in profiluri():
        c = intrare._controlori.get(prof.nume)
        if c is None:
            continue
        try:
            c.opreste('enigma2 se opreste')
        except Exception:
            jurnal.eroare(prof.eticheta, 'oprirea enigma2')
    try:
        from . import server8001
        server8001.opreste()
    except Exception:
        jurnal.eroare('imagine', 'oprirea serverului local de flux')
    _stare['sesiune'] = None

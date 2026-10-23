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
                      marcajelor ansamblurilor („MUX DAB+: ...”; SEMN_MARCAJE) merg in fir de fundal.
  opreste()           chemat din mytest.py la iesirea enigma2: marcajele protectiei la pornire se sterg primele
                      (sterge_marcajele), apoi releele se opresc, tunerul se elibereaza.
  descarcarea zilnica a listelor (liste.Zilnic) porneste aici; merge numai cu setarea ei pornita.
  server8001          serverul local de flux pe 127.0.0.1:8001 (pornit aici): baza nu are streamserver, iar releele
                      cer fluxul serviciului purtator acolo.
  controlor_dab(), controlor_t2()   controlorii (acelasi obiect pe tot procesul), pentru ferestre si web.
Paznicul pluginului (bataia din /tmp/hds-bataie) nu porneste in imagine: imaginea are paznicul ei
(Components/HdsPaznic.py si hds-watchdog). Caile de plugin ale controlorilor sunt dab/ si t2/ de langa modul
(motor/, date/, bin/).
"""
import os

from . import coordonator, jurnal
from . import profil as _profil

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
            buchete.scrie_atomic(cale, ('#NAME %s\n' % prof.nume_buchet).encode('utf-8'))
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

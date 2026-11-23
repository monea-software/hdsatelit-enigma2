# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Recuperarea indexurilor fara reimport; citirea si copiile merg pe fir."""
import builtins
import json
import os
import stat
import tempfile
import threading
import time
import weakref
from urllib.parse import unquote, quote_from_bytes

try:
    from Components import HdsBucheteOrfane as O
except ImportError:
    import HdsBucheteOrfane as O

_ZAVOR = threading.Lock()
_LUCRU = None
_ULTIM = None
_INCERCAT = 0.0
_CEAS = None
_CALLBACK = None
_IMPORT = None
_EROARE = ""
_MESAJ_ESEC = None
_NEVERIFICAT = object()
_LISTE = {}


def _(text):
    return getattr(builtins, "_", lambda s: s)(text)


def mesaj(rez=None):
    rez = _ULTIM if rez is None else rez
    if not rez:
        return ""
    nume = rez.get("puse", [])
    if nume:
        lista = ", ".join((O.forma_numelui(n) if any(0xDC80 <= ord(c) <= 0xDCFF for c in n) else n)[:100]
                          for n in nume[:5])
        if len(nume) > 5:
            lista += _(" și încă %d") % (len(nume) - 5)
        if len(nume) == 1:
            text = _("Am găsit un buchet care lipsea din listă și l-am pus la loc: %s") % lista
        else:
            text = _("Am găsit %d buchete care lipseau din listă și le-am pus la loc: %s") % (len(nume), lista)
        if rez.get("curatate"):
            text += " " + _("Am curățat și descrierile rămase fără buchet.")
        return text
    if rez.get("curatate"):
        return _("Am curățat descrierile rămase fără buchet în lista de canale.")
    return ""


def _semn(cale):
    try:
        s = os.lstat(cale)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(s.st_mode):
        raise OSError("fisierul nu este obisnuit")
    return s.st_mtime_ns, s.st_ctime_ns, s.st_size, s.st_ino


def _citeste(cale):
    with open(cale, "rb") as f:
        return f.read()


def _atomic(cale, date, mod=0o644, asteptat=_NEVERIFICAT):
    fd, nou = tempfile.mkstemp(prefix=".hds-buchete-", dir=os.path.dirname(cale))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(date)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(nou, mod)
        if asteptat is not _NEVERIFICAT and _semn(cale) != asteptat:
            raise OSError("index schimbat in timpul scrierii")
        os.replace(nou, cale)
    finally:
        if os.path.exists(nou):
            os.unlink(nou)


def repara(director=O.DIRECTOR, ocupat=None):
    """Aceeasi operatie pentru pornire, lista si asistenta; fara scrieri la gol."""
    if not _ZAVOR.acquire(False):
        raise OSError("reparatia lucreaza deja")
    try:
        return _repara(director, ocupat or (lambda: False))
    finally:
        _ZAVOR.release()


def _trimiteri(text):
    rez = []
    for nume in O.trimiteri(text):
        if "%" in nume:
            try:
                nume = unquote(nume, errors="surrogateescape")
            except UnicodeError:
                continue
        if _nume_disc_sigur(nume):
            rez.append(nume)
    return rez


def _nume_disc_sigur(nume):
    """Valideaza si octetii vechi de pe disc, fara a-i inlocui sau pierde."""
    try:
        return (O._nume_sigur(O.forma_numelui(nume))
                and len(nume.encode("utf-8", "surrogateescape")) <= O.MAX_OCTETI_NUME)
    except UnicodeError:
        return False


def _nume_ref(nume):
    try:
        nume.encode("utf-8")
        return nume
    except UnicodeError:
        # Nucleul decodeaza %xx in octetii originali ai caii.
        return quote_from_bytes(nume.encode("utf-8", "surrogateescape"), safe="._- ")


def _stare_refuzuri(text):
    d = json.loads(text or "{}")
    if not isinstance(d, dict) or not isinstance(d.get("scoase", []), list):
        raise OSError("starea alegerilor nu se poate citi")
    return d


def plan_refuzuri(baza, noi, director):
    """Alegerile editorului, calculate si scrise numai pe firul de disc."""
    def vizibile(buchete):
        vazute, coada = set(), list(O.INDEXURI)
        while coada:
            n = coada.pop()
            if n in vazute:
                continue
            vazute.add(n)
            b = buchete.get(n)
            if b is not None:
                coada.extend(i.fisier for i in b.intrari if i.fisier)
        return vazute
    vechi, acum = vizibile(baza), vizibile(noi)
    if vechi == acum:
        return None
    cale = os.path.join(director, O.FISIER_STARE)
    try:
        _semn(cale)
        text = _citeste(cale).decode("utf-8")
    except FileNotFoundError:
        text = ""
    d = _stare_refuzuri(text)
    scoase = set(d.get("scoase", []))
    rezultat = (scoase | {n for n in vechi - acum if _nume_disc_sigur(n)}) - acum
    if rezultat == scoase:
        return None
    d["scoase"] = sorted(rezultat)
    return json.dumps(d, ensure_ascii=True, sort_keys=True).encode("ascii")


def _generat(nume, locuri=None):
    return O.e_propriu(nume, locuri) and nume not in ("userbouquet.favourites.tv", "userbouquet.favourites.radio")


def _dezleaga(parinte, nume, director, sterge=False):
    """Dezlegarea nativa, cu aceleasi alegeri ca editorul; numai pe firul de disc."""
    if not _ZAVOR.acquire(False):
        raise OSError("lista este in lucru")
    try:
        semne, date = {}, {}
        def citeste(n):
            if n not in date:
                cale = os.path.join(director, n)
                semne[n] = _semn(cale)
                date[n] = _citeste(cale) if semne[n] is not None else b""
                if _semn(cale) != semne[n]:
                    raise OSError("lista s-a schimbat")
            return date[n].decode("utf-8", "surrogateescape")
        text = citeste(parinte)
        ramase, scos, descriere = [], False, False
        for rand in text.splitlines(True):
            if not scos and nume in _trimiteri(rand):
                scos, descriere = True, True
                continue
            if descriere and rand.startswith("#DESCRIPTION"):
                descriere = False
                continue
            descriere = False
            ramase.append(rand)
        if not scos:
            raise OSError("legatura nu mai exista")
        nou = "".join(ramase)
        def vizibile(inlocuire=None):
            vazute, coada = set(), list(O.INDEXURI)
            while coada:
                n = coada.pop()
                if n in vazute:
                    continue
                vazute.add(n)
                t = inlocuire if n == parinte and inlocuire is not None else citeste(n)
                coada.extend(_trimiteri(t))
            return vazute
        vechi, acum = vizibile(), vizibile(nou)
        # Un copil comun, ramas vizibil prin alta legatura, nu devine exclus.
        stare = _stare_refuzuri(citeste(O.FISIER_STARE))
        scoase = set(stare.get("scoase", []))
        stare["scoase"] = sorted((scoase | {n for n in vechi - acum if _nume_disc_sigur(n)}) - acum)
        schimbate = {}
        refuz = json.dumps(stare, ensure_ascii=True, sort_keys=True).encode("ascii")
        if refuz != date[O.FISIER_STARE]:
            schimbate[O.FISIER_STARE] = refuz
        schimbate[parinte] = nou.encode("utf-8", "surrogateescape")
        # Stergerea nativa a unui buchet are copie si nu rupe o alta legatura valida.
        if sterge and nume not in acum:
            citeste(nume)
            schimbate[nume] = None
        def verifica():
            if any(_semn(os.path.join(director, n)) != s for n, s in semne.items()):
                raise OSError("lista s-a schimbat")
        copie = _scrie_schimbari(schimbate, date, semne, verifica, director)
        return {"puse": [], "curatate": 0, "schimbate": list(schimbate), "copie": copie, "dezlegat": nume}
    finally:
        _ZAVOR.release()


def _scrie_schimbari(schimbate, date, semne, verifica, director):
    """Copii exacte, scriere atomica verificata si revenire fara a suprascrie alte schimbari."""
    verifica()
    copie = tempfile.mkdtemp(prefix="hds-backup-setari-" + time.strftime("%Y%m%d_%H%M%S") + "-buchete-", dir=director)
    for nume in schimbate:
        if semne[nume] is not None:
            with open(os.path.join(copie, nume), "xb") as f:
                f.write(date[nume])
                f.flush()
                os.fsync(f.fileno())
    verifica()
    scrise = []
    try:
        for nume, continut in schimbate.items():
            cale = os.path.join(director, nume)
            if _semn(cale) != semne[nume]:
                raise OSError("fisier schimbat in timpul scrierii")
            mod = stat.S_IMODE(os.stat(cale).st_mode) if semne[nume] is not None else 0o644
            if continut is None:
                if semne[nume] is not None:
                    os.unlink(cale)
            else:
                _atomic(cale, continut, mod, asteptat=semne[nume])
            semn_scris = _semn(cale)
            scrise.append((nume, mod, semn_scris))
            if (continut is None and semn_scris is not None) or (continut is not None and _citeste(cale) != continut):
                raise OSError("scrierea nu s-a confirmat")
    except Exception:
        for nume, mod, semn_scris in reversed(scrise):
            cale = os.path.join(director, nume)
            if _semn(cale) == semn_scris:
                if semne[nume] is not None:
                    _atomic(cale, date[nume], mod, asteptat=semn_scris)
                elif semn_scris is not None:
                    os.unlink(cale)
        raise
    return copie


def _repara(director, ocupat):
    if ocupat():
        raise OSError("lista este in lucru")
    semne, date, texte, noi = {}, {}, {}, {}
    def citeste(nume):
        if nume in date:
            return date[nume].decode("utf-8", "surrogateescape")
        cale = os.path.join(director, nume)
        semne[nume] = _semn(cale)
        date[nume] = _citeste(cale) if semne[nume] is not None else b""
        if semne[nume] != _semn(cale):
            raise OSError("lista s-a schimbat")
        return date[nume].decode("utf-8", "surrogateescape")
    curatate = 0
    nume_disc = sorted(os.listdir(director))
    pe_forma = {}
    for n in nume_disc:
        if _nume_disc_sigur(n) and not os.path.islink(os.path.join(director, n)):
            pe_forma.setdefault(O.forma_numelui(n), []).append(n)
    refuzuri = _stare_refuzuri(citeste(O.FISIER_STARE))
    excluse = {O.forma_numelui(n) for n in refuzuri.get("scoase", []) if isinstance(n, str)}
    texte = {index: citeste(index) for index in O.INDEXURI}
    referite = {n for text in texte.values() for n in _trimiteri(text)}
    impacate = []
    for index in O.INDEXURI:
        text = texte[index]
        ramase, serviciu, sari_descriere = [], False, False
        for rand in text.splitlines(True):
            if rand.startswith("#DESCRIPTION") and sari_descriere:
                sari_descriere = False
                curatate += 1
                continue
            sari_descriere = False
            brut = O._nume_rand(rand)
            n = next(iter(_trimiteri(rand)), None)
            if n and not _generat(n) and not os.path.exists(os.path.join(director, n)):
                candidati = pe_forma.get(O.forma_numelui(n), [])
                if len(candidati) == 1 and candidati[0] not in referite:
                    impacate.append(candidati[0])
                    referite.add(candidati[0])
                    rand = rand.replace('FROM BOUQUET "' + brut + '"', 'FROM BOUQUET "' + _nume_ref(candidati[0]) + '"', 1)
                elif not candidati and not O._NUME_VECHI.match(n):
                    sari_descriere = True
                    serviciu = False
                    curatate += 1
                    continue

            if rand.startswith("#DESCRIPTION"):
                if not serviciu:
                    curatate += 1
                    continue
                serviciu = False
            elif rand.startswith("#NAME"):
                serviciu = False
            elif rand.startswith("#SERVICE"):
                serviciu = True
            elif rand.strip() and not rand.startswith("#"):
                serviciu = False
            ramase.append(rand)
        noi[index] = "".join(ramase)
    # Descendentii deja vizibili nu se dubleaza in radacina.
    legate, coada = set(), [f for t in noi.values() for f in _trimiteri(t)]
    while coada:
        nume = coada.pop()
        if nume in legate or not _nume_disc_sigur(nume):
            continue
        legate.add(nume)
        coada.extend(_trimiteri(citeste(nume)))
    locuri = O._locuri_extensii(director)
    puse = []
    for n in impacate:
        titluri = [r[6:].strip() for r in date[n].decode("utf-8", "replace").splitlines() if r.startswith("#NAME ")]
        puse.append(titluri[0] if titluri and titluri[0] else O.forma_numelui(n))
    candidati, copii = {}, set()
    for nume in nume_disc:
        if (nume in legate or not _nume_disc_sigur(nume) or _generat(nume, locuri)
                or O.forma_numelui(nume) in excluse or refuzuri.get("refuzat")):
            continue
        cale = os.path.join(director, nume)
        if os.path.islink(cale):
            continue
        text = citeste(nume)
        copii.update(_trimiteri(text))
        canale, titlu = False, O.forma_numelui(nume)
        for rand in text.splitlines():
            if rand.startswith("#NAME "):
                titlu = rand[6:].strip().encode("utf-8", "replace").decode("utf-8") or O.forma_numelui(nume)
            if rand.startswith("#SERVICE "):
                parti = rand[9:].split(":", 2)
                try:
                    canale = canale or (len(parti) == 3 and not int(parti[1]) & (1 | 64))
                except ValueError:
                    pass
        if canale:
            candidati[nume] = titlu
    # Radacinile inaintea copiilor; a doua parte acopera si ciclurile.
    ordine = [n for n in candidati if n not in copii] + list(candidati)
    for nume in ordine:
        if nume in legate:
            continue
        titlu = candidati[nume]
        coada = [nume]
        while coada:
            n = coada.pop()
            if n in legate or not _nume_disc_sigur(n):
                continue
            legate.add(n)
            coada.extend(_trimiteri(citeste(n)))
        index = "bouquets." + nume.rsplit(".", 1)[1]
        if not noi[index]:
            noi[index] = "#NAME Bouquets (%s)\n" % ("TV" if index.endswith("tv") else "Radio")
        if not noi[index].endswith("\n"):
            noi[index] += "\n"
        noi[index] += '#SERVICE 1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet\n#DESCRIPTION %s\n' % (
            1 if index.endswith("tv") else 2, _nume_ref(nume), titlu)
        puse.append(titlu)
    schimbate = {n: t.encode("utf-8", "surrogateescape") for n, t in noi.items() if t != texte[n]}
    rezultat = {"puse": puse, "curatate": curatate, "copie": "", "schimbate": list(schimbate)}
    if not schimbate:
        return rezultat
    def verifica():
        if ocupat() or any(_semn(os.path.join(director, n)) != s for n, s in semne.items()):
            raise OSError("lista s-a schimbat; reparatia se reia la deschidere")
    rezultat["copie"] = _scrie_schimbari(schimbate, date, semne, verifica, director)
    return rezultat


def _ocupat():
    import sys
    imp = sys.modules.get("Components.HdsImportSurse")
    return bool((imp is not None and imp.ocupat()) or _editor_ocupat())


def _editor_ocupat():
    import sys
    ed = sys.modules.get("Components.HdsEditorCanale")
    return bool((ed is not None and ed._ZAVOR["s"] is not None) or _editare_tv())


def _lista_tv():
    import sys
    m = sys.modules.get("Screens.InfoBar")
    bara = getattr(getattr(m, "InfoBar", None), "instance", None)
    return getattr(bara, "servicelist", None)


def inregistreaza_lista(lista):
    """Liste native TV/radio; numai firul principal, fara a retine ecrane inchise."""
    ident = id(lista)
    def scoate(ref=None):
        if ref is None or _LISTE.get(ident) is ref:
            _LISTE.pop(ident, None)
    _LISTE[ident] = weakref.ref(lista, scoate)
    lista.onClose.append(scoate)


def _liste_native():
    liste = [ref() for ref in tuple(_LISTE.values())]
    tv = _lista_tv()
    if tv is not None and all(tv is not lista for lista in liste):
        liste.append(tv)
    return [lista for lista in liste if lista is not None]


def _editare_tv():
    return any(getattr(lista, "movemode", False) or getattr(lista, "bouquet_mark_edit", 0)
               or getattr(lista, "mutableList", None) is not None for lista in _liste_native())


def _reface_lista():
    import sys
    for nume in ("Components.HdsFavorite", "Plugins.Extensions.HdsWebControl.canale_web"):
        m = sys.modules.get(nume)
        if m is not None:
            m.uita()
    for lista in _liste_native():
        root, cur = lista.getRoot(), lista.getCurrentSelection()
        lista.bouquetNumOffsetCache = {}
        if root is not None and root.valid():
            lista.setRoot(root)
            if cur is not None and cur.valid():
                lista.servicelist.setCurrent(cur)


def cerere(director=O.DIRECTOR, la_gata=None):
    """Porneste fara asteptare; rezultatul se aplica numai pe firul Enigma2."""
    if la_gata is None and time.monotonic() - _INCERCAT < 2:
        return False
    return _porneste(lambda: repara(director), la_gata)


def dezleaga(parinte, nume, la_gata, sterge=False, director=O.DIRECTOR):
    """Primeste numai nume, nu obiecte Enigma2; rezervarea se ia pe firul principal."""
    if (parinte not in O.INDEXURI and not _nume_disc_sigur(parinte)) or not _nume_disc_sigur(nume) or parinte == nume:
        return False
    return _porneste(lambda: _dezleaga(parinte, nume, director, sterge), la_gata,
                     eroare=_("Nu am putut confirma schimbarea listei. Încearcă din nou."))


def _porneste(functie, la_gata, eroare=None):
    global _LUCRU, _INCERCAT, _CEAS, _CALLBACK, _IMPORT, _EROARE, _MESAJ_ESEC
    if _LUCRU is not None or _ocupat():
        return False
    from enigma import eTimer
    import _thread
    from Components import HdsImportSurse
    if not HdsImportSurse.ocupa():
        return False
    _IMPORT = HdsImportSurse
    _EROARE = ""
    _MESAJ_ESEC = eroare
    _CALLBACK = la_gata
    _INCERCAT = time.monotonic()
    _LUCRU = []
    cutie = _LUCRU
    def lucru():
        try:
            # Rezervarea importului si a editorului ramane pana la preia().
            # Obiectele Enigma2 se verifica exclusiv in cerere/preia, pe UI.
            cutie.append(functie())
        except Exception:
            cutie.append(None)
    _CEAS = None
    try:
        _CEAS = eTimer()
        _CEAS.callback.append(preia)
        _CEAS.start(100, False)
        _thread.start_new_thread(lucru, ())
    except Exception:
        if _CEAS is not None:
            _CEAS.stop()
        _LUCRU = None
        _IMPORT.elibereaza()
        _IMPORT = None
        _CALLBACK = None
        _CEAS = None
        _EROARE = eroare or _("Lista nu s-a putut repara. Nu am șters niciun buchet.")
        _MESAJ_ESEC = None
        raise
    return True


def preia():
    global _LUCRU, _ULTIM, _CALLBACK, _IMPORT, _EROARE, _MESAJ_ESEC
    if not _LUCRU or _editare_tv():
        return
    _CEAS.stop()
    rez, _LUCRU = _LUCRU[0], None
    if _IMPORT is not None:
        _IMPORT.elibereaza()
        _IMPORT = None
    callback, _CALLBACK = _CALLBACK, None
    _EROARE = (_MESAJ_ESEC or _("Lista nu s-a putut repara. Nu am șters niciun buchet.")) if rez is None else ""
    _MESAJ_ESEC = None
    if rez and rez["schimbate"]:
        _ULTIM = None if rez.get("dezlegat") else rez
        from enigma import eDVBDB
        try:
            eDVBDB.getInstance().reloadBouquets()
            _reface_lista()
        except Exception:
            _EROARE = (_("Lista s-a scris pe disc, dar nu s-a putut reîncărca. Repornește interfața.")
                       if rez.get("dezlegat") else _("Lista s-a reparat pe disc, dar nu s-a putut reîncărca. Repornește interfața."))
        try:
            from Tools.Notifications import AddNotification
            from Screens.MessageBox import MessageBox
            if not rez.get("dezlegat"):
                AddNotification(MessageBox, _EROARE or mesaj(rez),
                                type=MessageBox.TYPE_ERROR if _EROARE else MessageBox.TYPE_INFO, timeout=15)
        except Exception:
            pass
    if callback is not None:
        callback(None if _EROARE else rez)


def mesaj_web():
    return _EROARE or mesaj()


def stare_web():
    return {"result": not bool(_EROARE), "ocupat": _LUCRU is not None,
            "reparatie_buchete": mesaj_web()}

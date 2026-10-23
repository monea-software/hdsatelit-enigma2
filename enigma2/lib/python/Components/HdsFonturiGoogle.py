# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFonturiGoogle: creierul comun pentru descarcarea fonturilor Google direct
# de pe receptor. Folosit si de ecranul de pe televizor (Screens/HdsFonturi.py)
# si de interfata web (Plugins/Extensions/HdsWebControl/plugin.py). O singura
# sursa de adevar, ca la HdsDvbI.
#
# DE CE EXISTA: omul sa aleaga din receptor
# ce font vrea de pe Google Fonts, receptorul sa-l descarce singur, iar de atunci
# fontul sa se poata folosi in skin.
#
# ===================== PARTEA DE SIGURANTA, CEA MAI IMPORTANTA =====================
# `addFont` (lib/gdi/font.cpp:239) cheama fontRenderClass::AddFont (font.cpp:121),
# care pe un fisier care NU e font face:
#       if ((error=FT_New_Face(library, filename.c_str(), 0, &face)))
#               eFatal(" failed: %s", strerror(error));      <-- font.cpp:133
# adica OPRESTE enigma2. O pagina de eroare HTML salvata cu extensia .ttf, un fisier
# taiat la jumatate de o intrerupere de curent sau un font stricat de pe un mediu
# extern ar stinge televizorul la fiecare pornire.
# De aceea NICIUN fisier nu ajunge la addFont inainte sa treaca prin verificaFisierFont()
# de mai jos: semnatura sfnt, directorul de tabele intreg in interiorul fisierului,
# tabelele obligatorii prezente, numele familiei citit chiar din tabela `name`.
# `ctypes` lipseste din imagine, deci verificarea e Python curat, fara nicio biblioteca.
# ==================================================================================

from __future__ import absolute_import, print_function

import json
import os
import re
import shutil
import struct
import time

try:
    from urllib.request import Request, urlopen
    from urllib.parse import quote
    from urllib.error import URLError, HTTPError
except ImportError:  # Python 2, numai ca sa nu cada importul in uneltele vechi
    from urllib2 import Request, urlopen, URLError, HTTPError
    from urllib import quote

try:
    _
except NameError:
    def _(text):
        return text


# ---------------------------------------------------------------- adrese publice

# Lista intreaga a fontatelor Google, publica, FARA cheie de acces (verificat:
# HTTP 200, 2 702 081 octeti, 1946 de familii, JSON curat fara prefix XSSI).
URL_LISTA = "https://fonts.google.com/metadata/fonts"

# Foaia de stil care da adresa fisierului. Cu un User-Agent vechi (fara woff2)
# Google raspunde cu TTF, exact ce stie FreeType-ul din enigma2 sa citeasca.
URL_CSS = "https://fonts.googleapis.com/css?family=%s&subset=%s"
UA_VECHI = "Mozilla/4.0 (compatible; HDSatelit)"

# Depozitul liber, de unde se ia licenta. Directorul ESTE licenta.
URL_DEPOZIT = "https://raw.githubusercontent.com/google/fonts/main/%s/%s/%s"
LICENTE = (
    ("ofl", "OFL.txt", "SIL Open Font License 1.1"),
    ("apache", "LICENSE.txt", "Apache License 2.0"),
    ("ufl", "UFL.txt", "Ubuntu Font Licence 1.0"),
)

# Subseturile care intereseaza o interfata de receptor. Cerand numai pe astea,
# un font „chinezesc” de 17,7 MB ajunge 44 KB (masurat).
SUBSETURI_OSD = ("latin", "latin-ext", "cyrillic", "cyrillic-ext", "greek", "greek-ext", "vietnamese")

TIMP_RETEA = 20          # secunde pentru o cerere
BUCATA = 32768           # octeti pe pas la descarcare
ZILE_CACHE = 7

PRAG_AVERTISMENT = 4 * 1024 * 1024    # peste asta se cere confirmare
PRAG_REFUZ = 12 * 1024 * 1024         # peste asta nu se descarca deloc
REZERVA_DISC = 8 * 1024 * 1024        # cat spatiu liber ramane oricum


# ---------------------------------------------------------------- unde se tin fonturile

# ofgwrite rescrie radacina intreaga, iar copia de siguranta din HdsSoftwareUpdate.py ia numai
# canalele, setarile si datele din /etc/enigma2 (hds_*, hdsatelit/), nu fonturile. Deci un font pus
# pe radacina se pierde la actualizarea imaginii. Daca exista un mediu extern montat, acolo e locul lui.
DIR_RADACINA = "/usr/share/fonts/hdsatelit-google"
NUME_DIR_EXTERN = "hdsatelit-fonturi"


def _altaPartitie(punct):
    """True numai daca punctul de montare e pe ALT dispozitiv decat radacina.

    Gasit la proba: `getMountedPartitions()` intoarce si legaturi care stau
    tot pe radacina (in emulator, chiar directorul de jurnale montat in container), iar
    ecranul ar fi spus omului „rezista la actualizarea imaginii” despre un loc care NU
    rezista. Numai un dispozitiv diferit de cel al radacinii supravietuieste unui ofgwrite.
    Gasit la proba pe receptorul de proba: pe Viper 4K V20 `/media` ESTE un
    tmpfs de 64 KB (`tmpfs on /media type tmpfs (size=64k)`), deci `/media/hdd` are alt
    st_dev decat radacina si trecea de verificarea de mai sus. Ecranul i-ar fi spus omului
    „rezista la actualizarea imaginii” despre un RAM disc de 64 KB, care se pierde la prima
    repornire, iar descarcarea ar fi cazut pe lipsa de spatiu. De aceea nu mai e destul ca
    dispozitivul sa fie altul: locul trebuie sa fie pe un sistem de fisiere ADEVARAT.
    """
    try:
        if os.stat(punct).st_dev == os.stat("/").st_dev:
            return False
    except OSError:
        return False
    if _esteInMemorie(punct):
        return False
    try:
        s = os.statvfs(punct)
        return s.f_blocks * s.f_frsize >= MINIM_MEDIU_EXTERN
    except (OSError, AttributeError):
        return False


# Sub atat nu are rost sa numim ceva „mediu extern” (tmpfs-ul de /media are 64 KB).
MINIM_MEDIU_EXTERN = 64 * 1024 * 1024

# Sistemele de fisiere care stau in RAM: nu supravietuiesc nici macar unei reporniri.
FS_IN_MEMORIE = ("tmpfs", "ramfs", "devtmpfs", "overlay", "squashfs")


_OCTAL_MONTARE = re.compile(r"\\([0-7]{3})")


def _decodeazaMontare(cale):
    """Calea din /proc/mounts cu secventele \\ooo (spatiu, tab, rand nou, backslash) inlocuite, ca in
    Components/Harddisk.unescapeMountPath; altfel un stick cu spatiu in eticheta nu se potriveste cu nicio montare."""
    return _OCTAL_MONTARE.sub(lambda m: chr(int(m.group(1), 8)), cale)


def _esteInMemorie(punct):
    """True daca punctul de montare e servit de un sistem de fisiere care sta in RAM."""
    cale = os.path.realpath(punct)
    potrivit = None
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="surrogateescape") as f:
            for linie in f:
                parti = linie.split()
                if len(parti) < 3:
                    continue
                unde, fel = _decodeazaMontare(parti[1]), parti[2]
                if cale == unde or cale.startswith(unde.rstrip("/") + "/"):
                    if potrivit is None or len(unde) > len(potrivit[0]):
                        potrivit = (unde, fel)
    except (OSError, IOError):
        return False
    return bool(potrivit) and potrivit[1] in FS_IN_MEMORIE


def _mediiExterne():
    """Mediile montate pe care s-ar putea scrie, in ordinea in care le incercam."""
    gasite = []
    try:
        from Components.Harddisk import harddiskmanager
        for partitie in harddiskmanager.getMountedPartitions():
            punct = getattr(partitie, "mountpoint", None)
            if punct and punct not in ("/", "/boot") and os.path.isdir(punct) and _altaPartitie(punct):
                gasite.append(punct)
    except Exception:
        pass
    # Caile de rezerva, cand modulul e chemat fara enigma2 pornit. `/run/media/*` e locul
    # in care alte imagini monteaza stickurile pe Viper 4K V20 (de exemplu /run/media/<eticheta>-sda1).
    rezerve = ["/media/hdd", "/media/usb"]
    try:
        for nume in sorted(os.listdir("/run/media")):
            rezerve.append(os.path.join("/run/media", nume))
    except OSError:
        pass
    for punct in rezerve:
        if punct not in gasite and os.path.isdir(punct) and _altaPartitie(punct):
            gasite.append(punct)
    return gasite


def directoareFonturi():
    """Toate locurile in care pot sta fonturi descarcate, in ordinea de citire."""
    locuri = [os.path.join(punct, NUME_DIR_EXTERN) for punct in _mediiExterne()]
    locuri.append(DIR_RADACINA)
    return locuri


def directorScriere():
    """Unde se scrie un font nou: mediu extern daca exista, altfel radacina."""
    for punct in _mediiExterne():
        cale = os.path.join(punct, NUME_DIR_EXTERN)
        try:
            os.makedirs(cale, exist_ok=True)
            proba = os.path.join(cale, ".proba-scriere")
            with open(proba, "wb") as f:
                f.write(b"1")
            os.remove(proba)
            return cale
        except (OSError, IOError):
            continue
    try:
        os.makedirs(DIR_RADACINA, exist_ok=True)
    except (OSError, IOError):
        pass
    return DIR_RADACINA


def peMediuExtern():
    """True daca fonturile se scriu pe un mediu care supravietuieste actualizarii imaginii."""
    return directorScriere() != DIR_RADACINA


def spatiuLiber(cale):
    try:
        s = os.statvfs(cale)
        return s.f_bavail * s.f_frsize
    except (OSError, AttributeError):
        return 0


# ---------------------------------------------------------------- nume si aliasuri

def aliasFamilie(familie):
    """Numele sub care fontul se cheama in skin: familia fara spatii si fara semne.

    „Noto Sans SC” -> „NotoSansSC”, deci in skin: font="NotoSansSC;24".
    """
    return re.sub(r"[^0-9A-Za-z]", "", familie or "")


def _numeFisier(familie):
    return aliasFamilie(familie) + ".ttf"


def _numeDepozit(familie):
    """Numele directorului din github.com/google/fonts: familia mica, fara spatii."""
    return re.sub(r"[^0-9a-z]", "", (familie or "").lower())


# ---------------------------------------------------------------- retea

def _cere(url, metoda="GET", ua=None, timeout=TIMP_RETEA):
    cerere = Request(url)
    cerere.add_header("User-Agent", ua or "HDSatelit/1.0")
    if metoda != "GET":
        try:
            cerere.get_method = lambda: metoda
        except Exception:
            pass
    return urlopen(cerere, timeout=timeout)


def _citesteTot(url, ua=None, maxim=8 * 1024 * 1024, timeout=TIMP_RETEA):
    raspuns = _cere(url, "GET", ua, timeout)
    try:
        return raspuns.read(maxim)
    finally:
        try:
            raspuns.close()
        except Exception:
            pass


def _lungimeDeclarata(url):
    """Content-Length prin HEAD, ca mararimea aratata omului sa fie cea adevarata."""
    try:
        raspuns = _cere(url, "HEAD")
        try:
            lungime = raspuns.headers.get("Content-Length")
        finally:
            raspuns.close()
        return int(lungime) if lungime else 0
    except (URLError, HTTPError, ValueError, OSError):
        return 0


# ---------------------------------------------------------------- lista de familii

def _caleCache():
    return os.path.join(directorScriere(), "lista-google.json")


def _subliniaza(familie):
    """Ce pastram din metadate: destul pentru lista si filtre, nu 2,7 MB."""
    return {
        "familie": familie.get("family", ""),
        "categorie": familie.get("category", ""),
        "marime": int(familie.get("size") or 0),
        "subseturi": [s for s in (familie.get("subsets") or []) if s != "menu"],
        "greutati": sorted((familie.get("fonts") or {}).keys()),
        "variabil": bool(familie.get("axes")),
        "desenatori": familie.get("designers") or [],
        "popularitate": int(familie.get("popularity") or 99999),
    }


def _potrivitPentruReceptor(familie):
    """Ce NU intra in lista.

    - fonturile in culori (COLRv1/OTSVG): FreeType din enigma2 nu le deseneaza colorat,
      ar aparea ca niste pete negre; 21 de familii din 1946 (masurat);
    - familiile care nu au nici macar subsetul `latin`: n-au ce arata intr-o interfata
      in romana.
    Nota: `isOpenSource` e `true` la toate cele 1946 de familii din lista publica, deci
    nu exista in ea familii nelibere de scos. Licenta adevarata se confirma oricum
    inainte de descarcare, din depozitul google/fonts (vezi gasesteLicenta()).
    """
    if familie.get("colorCapabilities"):
        return False
    subseturi = familie.get("subsets") or []
    return "latin" in subseturi


def listaFamilii(reincarca=False):
    """Lista familiilor, din cache daca e proaspata, altfel de pe internet.

    Intoarce (lista, eroare_sau_None). Lista e sortata dupa popularitate.
    """
    cale = _caleCache()
    if not reincarca and os.path.isfile(cale):
        try:
            varsta = time.time() - os.path.getmtime(cale)
            if varsta < ZILE_CACHE * 86400:
                with open(cale, "r", encoding="utf-8") as f:
                    return json.load(f), None
        except (OSError, IOError, ValueError):
            pass
    try:
        brut = _citesteTot(URL_LISTA, maxim=16 * 1024 * 1024)
        date = json.loads(brut.decode("utf-8", "replace"))
    except (URLError, HTTPError, OSError, ValueError) as eroare:
        if os.path.isfile(cale):      # internetul e cazut, dar avem o lista veche
            try:
                with open(cale, "r", encoding="utf-8") as f:
                    return json.load(f), None
            except (OSError, IOError, ValueError):
                pass
        return [], _explicaEroareaDeRetea(eroare)
    lista = [_subliniaza(f) for f in date.get("familyMetadataList", []) if _potrivitPentruReceptor(f)]
    lista.sort(key=lambda f: f["popularitate"])
    try:
        cale_noua = cale + ".nou"
        with open(cale_noua, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False)
        os.replace(cale_noua, cale)
    except (OSError, IOError):
        pass
    return lista, None


def cauta(lista, text):
    """Cautare simpla dupa nume, fara diacritice si fara sa conteze literele mari."""
    text = (text or "").strip().lower()
    if not text:
        return lista
    return [f for f in lista if text in f["familie"].lower()]


# ---------------------------------------------------------------- verificatorul de font

SEMNATURI = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1")

_DIACRITICE_RO = {0x103: "ă", 0xE2: "â", 0xEE: "î", 0x219: "ș", 0x21B: "ț"}


def _decodeazaNume(date, platforma, codare):
    try:
        if platforma == 3 or (platforma == 0):
            return date.decode("utf-16-be", "replace")
        return date.decode("latin-1", "replace")
    except Exception:
        return ""


def _numeDinTabela(date):
    """Numele familiei din tabela `name`: nameID 16 (tipografic) daca exista, altfel 1."""
    if len(date) < 6:
        return ""
    formatul, numar, offset_siruri = struct.unpack(">HHH", date[:6])
    gasit = {}
    for i in range(numar):
        poz = 6 + i * 12
        if poz + 12 > len(date):
            break
        platforma, codare, limba, id_nume, lungime, offset = struct.unpack(">HHHHHH", date[poz:poz + 12])
        if id_nume not in (1, 16):
            continue
        start = offset_siruri + offset
        if start + lungime > len(date):
            continue
        text = _decodeazaNume(date[start:start + lungime], platforma, codare).strip()
        if text and id_nume not in gasit:
            gasit[id_nume] = text
    return gasit.get(16) or gasit.get(1) or ""


def _coduriDinCmap(date, cautate):
    """Care dintre codurile cerute exista in cmap. Formatele 4 si 12, destule pentru TTF-uri reale."""
    gasite = set()
    if len(date) < 4 or not cautate:
        return gasite
    cel_mai_mare = max(cautate)
    numar = struct.unpack(">H", date[2:4])[0]
    subtabele = []
    for i in range(numar):
        poz = 4 + i * 8
        if poz + 8 > len(date):
            break
        platforma, codare, offset = struct.unpack(">HHI", date[poz:poz + 8])
        if (platforma == 3 and codare in (1, 10)) or platforma == 0:
            subtabele.append(offset)
    for offset in subtabele:
        if len(gasite) == len(cautate):     # le-am gasit pe toate, nu mai citim degeaba
            return gasite
        if offset + 4 > len(date):
            continue
        formatul = struct.unpack(">H", date[offset:offset + 2])[0]
        if formatul == 4:
            if offset + 14 > len(date):
                continue
            segX2 = struct.unpack(">H", date[offset + 6:offset + 8])[0]
            seg = segX2 // 2
            p_sfarsit = offset + 14
            p_inceput = p_sfarsit + segX2 + 2
            if p_inceput + segX2 > len(date):
                continue
            for s in range(seg):
                sfarsit = struct.unpack(">H", date[p_sfarsit + s * 2:p_sfarsit + s * 2 + 2])[0]
                inceput = struct.unpack(">H", date[p_inceput + s * 2:p_inceput + s * 2 + 2])[0]
                for cod in cautate:
                    if inceput <= cod <= sfarsit and cod != 0xFFFF:
                        gasite.add(cod)
        elif formatul == 12:
            if offset + 16 > len(date):
                continue
            grupuri = struct.unpack(">I", date[offset + 12:offset + 16])[0]
            grupuri = min(grupuri, 100000)
            for g in range(grupuri):
                poz = offset + 16 + g * 12
                if poz + 12 > len(date):
                    break
                inceput, sfarsit, _glif = struct.unpack(">III", date[poz:poz + 12])
                if inceput > cel_mai_mare:   # grupurile sunt sortate crescator
                    break
                for cod in cautate:
                    if inceput <= cod <= sfarsit:
                        gasite.add(cod)
                if len(gasite) == len(cautate):
                    return gasite
    return gasite


def verificaFisierFont(cale, familie_asteptata=None):
    """Spune daca fisierul e CHIAR un font si se poate da lui addFont fara sa cada enigma2.

    Intoarce un dictionar: {"bun": bool, "motiv": str, "familie": str, "diacritice": [..],
    "tabele": [..], "octeti": int}. Nu arunca niciodata.

    Verifica, in ordine: fisierul exista si nu e gol; semnatura sfnt; numarul de tabele
    e rezonabil; directorul de tabele incape in fisier; FIECARE tabela are offset+lungime
    inauntrul fisierului (asta prinde fisierul taiat de o intrerupere, pe care FreeType
    l-ar putea deschide si apoi crapa la desenare); tabelele obligatorii exista; numele
    familiei citit din tabela `name` seamana cu ce s-a cerut.
    """
    raspuns = {"bun": False, "motiv": "", "familie": "", "diacritice": [], "tabele": [], "octeti": 0}
    try:
        if not os.path.isfile(cale):
            raspuns["motiv"] = _("fișierul nu există")
            return raspuns
        marime = os.path.getsize(cale)
        raspuns["octeti"] = marime
        if marime < 1024:
            raspuns["motiv"] = _("fișier prea mic pentru un font (%d octeți)") % marime
            return raspuns
        if marime > 64 * 1024 * 1024:
            raspuns["motiv"] = _("fișier absurd de mare pentru un font")
            return raspuns
        with open(cale, "rb") as f:
            date = f.read()
    except (OSError, IOError) as eroare:
        raspuns["motiv"] = str(eroare)
        return raspuns

    semnatura = date[:4]
    if semnatura == b"ttcf":
        raspuns["motiv"] = _("colecție de fonturi (ttcf), nu un font singur")
        return raspuns
    if semnatura not in SEMNATURI:
        vizibil = "".join(chr(o) if 32 <= o < 127 else "." for o in date[:4])
        raspuns["motiv"] = _("nu e font: începe cu „%s”, nu cu o semnătură de font") % vizibil
        return raspuns

    try:
        numar = struct.unpack(">H", date[4:6])[0]
    except struct.error:
        raspuns["motiv"] = _("antet rupt")
        return raspuns
    if not 1 <= numar <= 512:
        raspuns["motiv"] = _("număr imposibil de tabele: %d") % numar
        return raspuns
    if 12 + numar * 16 > len(date):
        raspuns["motiv"] = _("fișier tăiat: lista de tabele nu încape în el")
        return raspuns

    tabele = {}
    for i in range(numar):
        poz = 12 + i * 16
        eticheta, _suma, offset, lungime = struct.unpack(">4sIII", date[poz:poz + 16])
        if offset + lungime > len(date):
            raspuns["motiv"] = _("fișier tăiat: tabela „%s” trece de sfârșitul fișierului") % \
                eticheta.decode("latin-1", "replace").strip()
            return raspuns
        tabele[eticheta.decode("latin-1", "replace")] = (offset, lungime)
    raspuns["tabele"] = sorted(tabele.keys())

    for obligatorie in ("head", "name", "cmap"):
        if obligatorie not in tabele:
            raspuns["motiv"] = _("lipsește tabela obligatorie „%s”") % obligatorie
            return raspuns
    if "glyf" not in tabele and "CFF " not in tabele:
        raspuns["motiv"] = _("nu are nici contururi (glyf), nici CFF: nu are ce desena")
        return raspuns

    offset, lungime = tabele["name"]
    raspuns["familie"] = _numeDinTabela(date[offset:offset + lungime])
    if not raspuns["familie"]:
        raspuns["motiv"] = _("nu are nume de familie în tabela „name”")
        return raspuns
    if familie_asteptata:
        a = aliasFamilie(raspuns["familie"]).lower()
        b = aliasFamilie(familie_asteptata).lower()
        if a != b and not a.startswith(b) and not b.startswith(a):
            raspuns["motiv"] = _("fișierul se numește „%s”, nu „%s”") % (raspuns["familie"], familie_asteptata)
            return raspuns

    offset, lungime = tabele["cmap"]
    gasite = _coduriDinCmap(date[offset:offset + lungime], set(_DIACRITICE_RO.keys()))
    raspuns["diacritice"] = [_DIACRITICE_RO[c] for c in sorted(_DIACRITICE_RO) if c in gasite]

    raspuns["bun"] = True
    raspuns["motiv"] = _("în regulă")
    return raspuns


def areDiacriticeRomanesti(verificare):
    return len(verificare.get("diacritice") or []) == len(_DIACRITICE_RO)


# ---------------------------------------------------------------- licenta

ultimaEroareDeRetea = None
"""Ultima eroare de RETEA (nu 404) de la `gasesteLicenta`.

De ce exista: `gasesteLicenta` inghitea `URLError` cu `continue`, deci cu ceasul
receptorului in 1970 (certificat „not yet valid”) omul primea „nu se găsește în depozitul
liber google/fonts: licență neconfirmată” -- un mesaj fals, care il trimitea pe drumul
gresit. Acum descarcarea poate spune care a fost eroarea adevarata.
"""


def gasesteLicenta(familie):
    """Cauta familia in google/fonts. Directorul ESTE licenta: ofl, apache sau ufl.

    Intoarce (cheie_director, nume_fisier_licenta, nume_licenta) sau (None, None, None)
    daca familia nu e in depozitul liber -- caz in care NU se descarca nimic.
    Daca a cazut reteaua, lasa eroarea in `ultimaEroareDeRetea`.
    """
    global ultimaEroareDeRetea
    ultimaEroareDeRetea = None
    dosar = _numeDepozit(familie)
    if not dosar:
        return None, None, None
    for cheie, fisier, nume in LICENTE:
        url = URL_DEPOZIT % (cheie, dosar, "METADATA.pb")
        try:
            raspuns = _cere(url, "HEAD", timeout=10)
            cod = getattr(raspuns, "status", None) or raspuns.getcode()
            raspuns.close()
            if cod == 200:
                return cheie, fisier, nume
        except HTTPError:
            continue      # 404 curat: familia chiar nu e in dosarul asta
        except (URLError, OSError) as eroare:
            ultimaEroareDeRetea = eroare
            continue
    return None, None, None


# ---------------------------------------------------------------- adresa fisierului

_RE_URL = re.compile(r"url\((https://[^)]+?\.ttf)\)")
_RE_BUCATA = re.compile(r"@font-face\s*\{(.*?)\}", re.S)


def adresaFisier(familie, subseturi=None):
    """Adresa TTF-ului pentru varianta normala (400, fara cursiv) a familiei.

    Intoarce (url, eroare_sau_None). Cere numai subseturile care intereseaza OSD-ul,
    deci fisierul e mic (Roboto: 60 884 octeti pentru latin+latin-ext).
    """
    cerute = [s for s in SUBSETURI_OSD if not subseturi or s in subseturi]
    if not cerute:
        cerute = ["latin"]
    url = URL_CSS % (quote(familie), ",".join(cerute))
    try:
        css = _citesteTot(url, ua=UA_VECHI, maxim=256 * 1024, timeout=TIMP_RETEA).decode("utf-8", "replace")
    except (URLError, HTTPError, OSError) as eroare:
        return None, _explicaEroareaDeRetea(eroare)
    bucati = _RE_BUCATA.findall(css)
    normal = None
    oricare = None
    for bucata in bucati:
        gasit = _RE_URL.search(bucata)
        if not gasit:
            continue
        if oricare is None:
            oricare = gasit.group(1)
        if "italic" in bucata:
            continue
        if re.search(r"font-weight:\s*400", bucata) or "font-weight" not in bucata:
            normal = normal or gasit.group(1)
    adresa = normal or oricare
    if not adresa:
        return None, _("Google nu a dat niciun fișier TTF pentru „%s”") % familie
    return adresa, None


# ---------------------------------------------------------------- descarcarea

class Oprit(Exception):
    """Ridicata cand cel care a cerut descarcarea a apasat Anulează."""


def _explicaEroareaDeRetea(eroare):
    """Traduce erorile de retea in ceva ce ii spune omului ce sa faca.

    Cea mai importanta: certificatul. Probat pe receptorul de proba, certificatul
    lui fonts.gstatic.com e valabil din 10 septembrie 2026. Un receptor pornit dupa o pana
    de curent are ceasul in 1970 pana il potriveste din fluxul DVB sau din NTP, iar pana
    atunci `verify_mode` e CERT_REQUIRED (dovedit pe receptor cu badssl.com: certificatele
    expirate, nesemnate si cu alt nume sunt respinse). Fara linia asta, omul ar fi vazut
    doar „[SSL: CERTIFICATE_VERIFY_FAILED] certificate is not yet valid”, care nu-i spune
    nimic si nu seamana deloc cu „potriveste ceasul”.

    Din 0.2.5 textul ceasului e cel comun tuturor descarcarilor (Components/HdsCeasHttps.py) si apare numai cand
    ceasul chiar e de vina (ora vadit in urma sau inca nesigura); cu ceasul bun ramane mesajul certificatului.
    """
    ceas = _mesajCeas(eroare)
    if ceas:
        return ceas
    text = str(eroare)
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSLCertVerificationError" in text:
        return _("Certificatul serverului nu a putut fi verificat. Nu se descarcă nimic.\n(%s)") % text
    return _("Descărcarea a eșuat: %s") % text


def _mesajCeas(eroare):
    """Textul comun „ceasul e în urmă” (Components/HdsCeasHttps.py) cand certificatul cade din cauza ceasului
    receptorului, altfel None. Verificarea certificatelor ramane pornita; aici se alege numai textul."""
    try:
        from Components import HdsCeasHttps
        return HdsCeasHttps.mesaj(eroare)
    except Exception:
        return None


def descarca(familie, subseturi=None, progres=None, opreste=None, confirma_mare=False):
    """Descarca familia, o verifica si o pune la locul ei. Se cheama pe un FIR, nu pe
    firul enigma2 (blocheaza pana termina).

    progres(descarcat, total) se cheama la fiecare bucata; opreste() intoarce True ca sa
    se renunte. Intoarce (True, mesaj, cale) sau (False, mesaj, None). Nu arunca.

    Fisierul se scrie in `<nume>.ttf.parte` si se redenumeste NUMAI dupa ce trece
    verificarea, deci nu exista niciodata un font pe jumatate in folosinta.
    """
    def _oprit():
        return bool(opreste and opreste())

    director = directorScriere()
    cale_finala = os.path.join(director, _numeFisier(familie))
    cale_parte = cale_finala + ".parte"

    cheie, fisier_licenta, nume_licenta = gasesteLicenta(familie)
    if not cheie:
        if ultimaEroareDeRetea is not None:
            # Nu „familia nu exista”, ci „n-am putut intreba”. Cu ceasul receptorului in 1970
            # aici cade prima cerere HTTPS din tot lantul, deci aici trebuie spus adevarul.
            return False, _explicaEroareaDeRetea(ultimaEroareDeRetea), None
        return False, _("„%s” nu se găsește în depozitul liber google/fonts: licență neconfirmată, nu se descarcă.") % familie, None

    adresa, eroare = adresaFisier(familie, subseturi)
    if not adresa:
        return False, eroare, None

    total = _lungimeDeclarata(adresa)
    if total and total > PRAG_REFUZ:
        return False, _("Fontul are %s, prea mult pentru un receptor (limita %s).") % (
            marimeText(total), marimeText(PRAG_REFUZ)), None
    if total and total > PRAG_AVERTISMENT and not confirma_mare:
        return False, _("Fontul are %s. Confirmă descărcarea mare.") % marimeText(total), None
    liber = spatiuLiber(director)
    if total and liber and total + REZERVA_DISC > liber:
        return False, _("Nu e destul spațiu: fontul are %s, liber sunt %s.") % (
            marimeText(total), marimeText(liber)), None

    descarcat = 0
    try:
        raspuns = _cere(adresa, "GET", ua=UA_VECHI)
        try:
            with open(cale_parte, "wb") as f:
                while True:
                    if _oprit():
                        raise Oprit()
                    bucata = raspuns.read(BUCATA)
                    if not bucata:
                        break
                    f.write(bucata)
                    descarcat += len(bucata)
                    if descarcat > PRAG_REFUZ:
                        raise ValueError(_("serverul trimite mai mult decât limita"))
                    if progres:
                        try:
                            progres(descarcat, total)
                        except Exception:
                            pass
        finally:
            try:
                raspuns.close()
            except Exception:
                pass
    except Oprit:
        _sterge(cale_parte)
        return False, _("Descărcare anulată. Nu a rămas nimic pe disc."), None
    except (URLError, HTTPError, OSError, IOError, ValueError) as eroare:
        _sterge(cale_parte)
        return False, _explicaEroareaDeRetea(eroare), None

    verificare = verificaFisierFont(cale_parte, familie)
    if not verificare["bun"]:
        _sterge(cale_parte)
        return False, _("Fișierul descărcat nu e un font bun (%s). A fost șters, receptorul nu l-a atins.") % verificare["motiv"], None

    # licenta si provenienta, langa font
    try:
        text = _citesteTot(URL_DEPOZIT % (cheie, _numeDepozit(familie), fisier_licenta), maxim=256 * 1024, timeout=15)
        with open(os.path.join(director, aliasFamilie(familie) + "-" + fisier_licenta), "wb") as f:
            f.write(text)
    except (URLError, HTTPError, OSError, IOError):
        pass  # fontul e bun oricum; lipsa textului de licenta se vede in sursa.txt
    try:
        with open(os.path.join(director, aliasFamilie(familie) + "-sursa.txt"), "w", encoding="utf-8") as f:
            f.write("Familia: %s\n" % familie)
            f.write("Nume in skin: %s\n" % aliasFamilie(familie))
            f.write("Descarcat de pe: %s\n" % adresa)
            f.write("Lista: %s\n" % URL_LISTA)
            f.write("Licenta: %s (%s/%s in github.com/google/fonts)\n" % (nume_licenta, cheie, _numeDepozit(familie)))
            f.write("Data: %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write("Octeti: %d\n" % verificare["octeti"])
            f.write("Diacritice romanesti gasite: %s\n" % ("".join(verificare["diacritice"]) or "niciuna"))
    except (OSError, IOError):
        pass

    try:
        os.replace(cale_parte, cale_finala)
        _sterge(cale_finala + SUFIX_STERS)   # o re-descarcare anuleaza o stergere neterminata
    except OSError as eroare:
        _sterge(cale_parte)
        return False, _("Nu s-a putut pune fontul la loc: %s") % eroare, None

    # ATENTIE: aici NU se cheama addFont. Functia asta ruleaza pe un fir separat, iar
    # `fontRenderClass::getFaceID` (font.cpp:105) parcurge lista de fonturi FARA lacat,
    # in timp ce `AddFont` i-ar adauga in cap un element nou. Inregistrarea o face cel
    # care a cerut descarcarea, pe firul principal (ecranul in `_gataDescarcare`,
    # interfata web in `_peFirulPrincipal`).
    return True, _("„%s” descărcat (%s), licență %s, folosibil în skin ca %s.") % (
        familie, marimeText(verificare["octeti"]), nume_licenta, aliasFamilie(familie)), cale_finala


def _sterge(cale):
    try:
        os.remove(cale)
    except (OSError, IOError):
        pass


def marimeText(octeti):
    octeti = int(octeti or 0)
    if octeti >= 1024 * 1024:
        return "%.1f MB" % (octeti / 1048576.0)
    if octeti >= 1024:
        return "%d KB" % (octeti // 1024)
    return "%d B" % octeti


# ---------------------------------------------------------------- fonturile de pe disc

# Verificarea unui font ia pe procesorul receptorului 0,01-0,15 s (masurat pe receptor), iar
# lista se reface la fiecare reimprospatare a ecranului si a paginii web, pe firul enigma2: cu cateva
# fonturi mari ecranul ar ingheta peste o secunda. Rezultatul se tine minte pe (cale, marime, data
# modificarii); un fisier inlocuit sau schimbat are alta marime sau alta data, deci se verifica din nou.
_verificari_tinute = {}


def _verificareTinuta(cale):
    try:
        st = os.stat(cale)
        cheie = (cale, st.st_size, st.st_mtime_ns)
    except OSError:
        return verificaFisierFont(cale)
    rezultat = _verificari_tinute.get(cheie)
    if rezultat is None:
        rezultat = verificaFisierFont(cale)
        for veche in [c for c in _verificari_tinute if c[0] == cale]:
            _verificari_tinute.pop(veche, None)
        _verificari_tinute[cheie] = rezultat
    return rezultat


def fonturiDescarcate():
    """Fonturile deja descarcate, cu verificarea lor. Lista de dictionare."""
    gasite = []
    vazute = set()
    for director in directoareFonturi():
        if not os.path.isdir(director):
            continue
        try:
            nume_fisiere = sorted(os.listdir(director))
        except OSError:
            continue
        for nume in nume_fisiere:
            if not nume.lower().endswith(".ttf") or nume in vazute:
                continue
            cale = os.path.join(director, nume)
            if _esteSters(cale):     # scos din folosinta, se sterge la urmatoarea pornire
                continue
            vazute.add(nume)
            verificare = _verificareTinuta(cale)
            gasite.append({
                "alias": nume[:-4],
                "familie": verificare["familie"] or nume[:-4],
                "cale": cale,
                "octeti": verificare["octeti"],
                "bun": verificare["bun"],
                "motiv": verificare["motiv"],
                "diacritice": verificare["diacritice"],
                "extern": director != DIR_RADACINA,
            })
    return gasite


SUFIX_STERS = ".sters"


def stergeFont(alias):
    """Scoate fontul din folosinta. Intoarce (reusit, mesaj).

    NU sterge fisierul acum, si iata de ce (gasit la verificare, inainte
    sa apuce sa strice ceva): `addFont` nu are pereche care sa scoata un alias din
    `fontRenderClass`, iar cache-ul de fete al FreeType tine numai 8 fete deodata
    (`FTC_Manager_New(library, 8, 8, ...)`, font.cpp:169) -- skinul HDSatelit inregistreaza
    deja 9 aliasuri. Cand o fata e aruncata din cache si un widget cere din nou acel alias,
    `FTC_Face_Requester` face `FT_New_Face` pe FISIERUL DE PE DISC; daca fisierul nu mai e,
    `eTextPara::renderString` face `eFatal("no current_face")` (font.cpp:505) si opreste
    receptorul. Adica stergerea „pe loc” ar fi fost o bomba cu ceas.
    In schimb se pune un semn `<alias>.ttf.sters` langa font: fontul dispare imediat din
    liste si nu se mai inregistreaza, iar fisierul se sterge de-adevaratelea la urmatoarea
    pornire (inregistreazaLaPornire), cand niciun alias nu mai trimite spre el.
    """
    gasit = False
    for director in directoareFonturi():
        cale = os.path.join(director, alias + ".ttf")
        if os.path.isfile(cale):
            try:
                with open(cale + SUFIX_STERS, "w", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                gasit = True
            except (OSError, IOError) as eroare:
                return False, _("Nu s-a putut șterge: %s") % eroare
    if not gasit:
        return False, _("Fontul „%s” nu a fost găsit.") % alias
    return True, _("„%s” a fost scos din folosință. Fișierul se șterge la următoarea pornire.") % alias


def _esteSters(cale_ttf):
    return os.path.exists(cale_ttf + SUFIX_STERS)


def _stergeDeAdevaratelea():
    """La pornire, INAINTE de orice addFont: sterge fonturile insemnate la stergere.

    Aici e sigur: niciun alias nu e inca inregistrat spre ele in acest proces.
    """
    sterse = 0
    for director in directoareFonturi():
        if not os.path.isdir(director):
            continue
        try:
            nume_fisiere = list(os.listdir(director))
        except OSError:
            continue
        for nume in nume_fisiere:
            if not nume.endswith(".ttf" + SUFIX_STERS):
                continue
            alias = nume[:-(len(".ttf") + len(SUFIX_STERS))]
            _sterge(os.path.join(director, alias + ".ttf"))
            for alaturat in ("-sursa.txt", "-OFL.txt", "-LICENSE.txt", "-UFL.txt"):
                _sterge(os.path.join(director, alias + alaturat))
            _sterge(os.path.join(director, nume))
            sterse += 1
    return sterse


# ---------------------------------------------------------------- inregistrarea in enigma2

_inregistrate = set()


def inregistreazaUnFont(cale, familie=None):
    """Da fontul lui enigma2, DAR numai dupa ce trece verificatorul.

    Nicio alta cale din imagine nu are voie sa cheme addFont pe un fisier descarcat.
    """
    verificare = verificaFisierFont(cale, familie)
    if not verificare["bun"]:
        print("[HdsFonturiGoogle] REFUZAT (nu ajunge la addFont): %s -- %s" % (cale, verificare["motiv"]))
        return False, _("Fișierul nu e un font bun: %s") % verificare["motiv"]
    alias = aliasFamilie(familie or verificare["familie"]) or os.path.basename(cale)[:-4]
    try:
        from enigma import addFont
        addFont(cale, alias, 100, 0)
    except Exception as eroare:
        print("[HdsFonturiGoogle] addFont a esuat pentru %s: %s" % (cale, eroare))
        return False, str(eroare)
    _inregistrate.add(alias)
    print("[HdsFonturiGoogle] inregistrat %s din %s" % (alias, cale))
    return True, alias


def curataPartiale():
    """Sterge orice `*.parte` ramas dintr-o descarcare intrerupta."""
    sterse = 0
    for director in directoareFonturi():
        if not os.path.isdir(director):
            continue
        try:
            for nume in os.listdir(director):
                if nume.endswith(".parte"):
                    _sterge(os.path.join(director, nume))
                    sterse += 1
        except OSError:
            continue
    return sterse


def inregistreazaLaPornire():
    """Se cheama o data la pornire, din mytest.py, INAINTE de incarcarea skinului.

    Curata resturile de descarcari intrerupte, apoi da lui enigma2 numai fonturile care
    trec verificatorul. Un fisier stricat e sarit cu o linie in jurnal, NU oprit
    receptorul. Nu arunca niciodata.
    In modul sigur (HDS_MOD_SIGUR=1 de la enigma2.sh, Components/HdsModSigur.py) skinul e cel
    al imaginii, fara skin_user.xml, deci fonturile descarcate nu se dau lui enigma2 deloc.
    """
    if os.environ.get("HDS_MOD_SIGUR") == "1":
        print("[HdsFonturiGoogle] modul sigur: fonturile descarcate nu se inregistreaza")
        return
    try:
        scoase = _stergeDeAdevaratelea()
        if scoase:
            print("[HdsFonturiGoogle] sterse definitiv %d fonturi scoase din folosinta" % scoase)
        sterse = curataPartiale()
        if sterse:
            print("[HdsFonturiGoogle] sterse %d descarcari neterminate" % sterse)
        bune = 0
        for font in fonturiDescarcate():
            if not font["bun"]:
                print("[HdsFonturiGoogle] sarit %s: %s" % (font["cale"], font["motiv"]))
                continue
            if inregistreazaUnFont(font["cale"], font["familie"])[0]:
                bune += 1
        if bune:
            print("[HdsFonturiGoogle] %d fonturi Google gata de folosit in skin" % bune)
    except Exception as eroare:
        print("[HdsFonturiGoogle] pornire: %s" % eroare)


def aliasuriInregistrate():
    return sorted(_inregistrate)

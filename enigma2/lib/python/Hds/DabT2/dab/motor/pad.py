# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""PAD-ul posturilor DAB / DAB+: textul postului (DLS) si imaginile lui (MOT SlideShow). Facut de hdsatelit.com, scris de la zero.

Surse: ETSI EN 300 401 (7.4: PAD, F-PAD, X-PAD, lista CI, DLS), ETSI TS 102 563 (PAD in elementul DSE al AU-ului AAC),
ETSI EN 301 234 (MOT: grupuri de date, antet, corp, segmente), ETSI TS 101 499 (SlideShow), ETSI TS 101 756 (seturile de
caractere: EBU Latin, tabelul 1).

Unde sta PAD-ul:
  DAB (MP2)  la coada cadrului: F-PAD = ultimii 2 octeti; inaintea lui ScF-CRC (2 sau 4 octeti); inaintea lui X-PAD-ul,
             cu octetii in ordine inversa (primul octet logic e cel lipit de ScF-CRC). Lungimea X-PAD-ului nu e scrisa:
             o da lista CI.
  DAB+       in elementul DSE cu care incepe AU-ul (id 4): count (si esc_count la 255), apoi octetii PAD-ului, tot cu
             F-PAD-ul la coada si X-PAD-ul inversat, de lungime exacta.

Iesirea (pentru ecranul radio si pagina web): un dosar pe post, RADACINA/<feed>-<SID hex>/, cu `text` (UTF-8) si
`imagine.jpg` sau `imagine.png`, scrise numai cand se schimba, printr-un fisier .tmp si os.rename (cine citeste vede
mereu fisierul vechi intreg sau pe cel nou intreg). Pe receptoarele slabe: o singura trecere pe cadru, felii mici
(X-PAD-ul are cel mult 196 de octeti), nicio copie a cadrului de sunet; imaginea se lipeste o data, la sfarsit.

Merge pe Python 3 si pe Python 2.7 (octetii se citesc din bytearray, ca indexul sa dea numere)."""
from __future__ import division

import binascii
import os
import zlib

RADACINA = "/tmp/hds-dab"
# pus de setarea „Imaginile posturilor DAB” pe Nu (Components/HdsRadioSetari.py); releul nu mai strange atunci imaginile
FARA_IMAGINI = "/tmp/hds-dab-fara-imagini"

LUNG_CI = (4, 6, 8, 12, 16, 24, 32, 48)        # indexul de 3 biti al unui CI din X-PAD-ul variabil
X_PAD_MAX = 196                                 # cel mai lung X-PAD posibil: 4 CI + 4 x 48
APP_DGLI, APP_DLS, APP_DLS_CONT, APP_MOT, APP_MOT_CONT = 1, 2, 3, 12, 13
_CONTINUARE = {APP_DGLI: APP_DGLI, APP_DLS: APP_DLS_CONT, APP_DLS_CONT: APP_DLS_CONT,
               APP_MOT: APP_MOT_CONT, APP_MOT_CONT: APP_MOT_CONT}
GRUP_MAX = 16 * 1024                            # un grup de date MOT din X-PAD (segmentul are cel mult 8191 de octeti)
IMAGINE_MAX = 256 * 1024                        # SlideShow cere cel mult 50 KB; peste plafon obiectul se arunca
OBIECTE_MAX = 2                                 # obiecte MOT in lucru deodata (in mod obisnuit unul)

# MP2: kbit/s dupa indexul din antet (Layer II), MPEG-1 la 48 kHz si MPEG-2 la 24 kHz
_KBIT_MPEG1 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0)
_KBIT_MPEG2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)

try:
    _crc = binascii.crc_hqx

    def _crc_bun(d):
        """CRC-CCITT (pornire FFFF, complementat, la coada): peste date + CRC iese mereu 0x1D0F."""
        return len(d) > 2 and _crc(bytes(d), 0xFFFF) == 0x1D0F
except AttributeError:                          # pragma: no cover (binascii fara crc_hqx)
    def _crc_bun(d):
        c = 0xFFFF
        for b in bytearray(d[:-2]):
            c ^= b << 8
            for _ in range(8):
                c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        c ^= 0xFFFF
        return len(d) > 2 and c == ((d[-2] << 8) | d[-1])


# ---------------------------------------------------------------- seturile de caractere
# EBU Latin (TS 101 756, tabelul 1): codurile care nu sunt ASCII. 0x0A (sfarsit de rand preferat) si 0x0B (sfarsitul
# titlului) devin spatiu; 0x00 si 0x1F (despartire in silabe) dispar.
_EBU_DIFERIT = {
    0x00: u"", 0x01: u"Ę", 0x02: u"Į", 0x03: u"Ų", 0x04: u"Ă", 0x05: u"Ė", 0x06: u"Ď",
    0x07: u"Ș", 0x08: u"Ț", 0x09: u"Ċ", 0x0A: u" ", 0x0B: u" ", 0x0C: u"Ġ", 0x0D: u"Ĺ",
    0x0E: u"Ż", 0x0F: u"Ń", 0x10: u"ą", 0x11: u"ę", 0x12: u"į", 0x13: u"ų",
    0x14: u"ă", 0x15: u"ė", 0x16: u"ď", 0x17: u"ș", 0x18: u"ț", 0x19: u"ċ",
    0x1A: u"Ň", 0x1B: u"Ě", 0x1C: u"ġ", 0x1D: u"ĺ", 0x1E: u"ż", 0x1F: u"",
    0x24: u"ł", 0x5C: u"Ů", 0x5E: u"Ł", 0x60: u"Ą",
    0x7B: u"«", 0x7C: u"ů", 0x7D: u"»", 0x7E: u"Ľ", 0x7F: u"Ħ",
}
_EBU_80 = (  # 0x80 .. 0xFF
    u"áàéèíìóòúùÑÇŞß¡Ÿ"
    u"âäêëîïôöûüñçşğıÿ"
    u"ĶŅ©ĢĞěňőŐ€£$ĀĒĪŪ"
    u"ķņĻģļİńűŰ¿ľ°āēīū"
    u"ÁÀÉÈÍÌÓÒÚÙŘČŠŽÐĿ"
    u"ÂÄÊËÎÏÔÖÛÜřčšžđŀ"
    u"ÃÅÆŒŷÝÕØÞŊŔĆŚŹŤð"
    u"ãåæœŵýõøþŋŕćśźťħ")
EBU_LATIN = dict(_EBU_DIFERIT)
for _i, _c in enumerate(_EBU_80):
    EBU_LATIN[0x80 + _i] = _c
del _i, _c
# latin-1 da chr(x) pentru fiecare octet, apoi un singur translate pune literele EBU (in C)
_EBU_TABEL = dict((k, v) for k, v in EBU_LATIN.items())
_CONTROL = {0x00: None, 0x0A: u" ", 0x0B: u" ", 0x1F: None, 0x0D: u" ", 0x09: u" "}

SET_EBU, SET_LATIN1, SET_UCS2, SET_UTF8 = 0, 4, 6, 15


def decodeaza_text(octeti, setul):
    """Octetii unei etichete DAB -> text unicode pe un singur rand."""
    b = bytes(bytearray(octeti))
    if setul == SET_EBU:
        t = b.decode("latin-1").translate(_EBU_TABEL)
    elif setul == SET_UTF8:
        t = b.decode("utf-8", "replace")
    elif setul == SET_UCS2:
        t = b[:len(b) // 2 * 2].decode("utf-16-be", "replace")
    elif setul == SET_LATIN1:
        t = b.decode("latin-1")
    else:                                       # set nestandard: UTF-8 daca se potriveste, altfel Latin-1
        try:
            t = b.decode("utf-8")
        except UnicodeDecodeError:
            t = b.decode("latin-1")
    return u" ".join(t.translate(_CONTROL).split())


# ---------------------------------------------------------------- unde se scrie
def curata_id(feed_id):
    """La fel ca releu_dab.curata_id (si buchete._curata_id)."""
    return "".join(ch for ch in str(feed_id or "") if ch.isalnum() or ch in "_-.")[:64]


def dosar_post(feed_id, sid, radacina=None):
    return os.path.join(radacina or RADACINA, "%s-%04X" % (curata_id(feed_id), int(sid) & 0xFFFF))


def sid_din_text(text):
    """SID-ul din calea releului, ca releu_dab.sid_din_cale: zecimal (asa scrie buchetul), 0x... sau hex."""
    t = str(text).split(".", 1)[0].strip()
    if not t:
        raise ValueError("SID gol")
    if t[:2].lower() == "0x":
        v = int(t, 16)
    elif t.isdigit():
        v = int(t)
    else:
        v = int(t, 16)
    if not 0 < v <= 0xFFFF:
        raise ValueError("SID in afara intervalului")
    return v


def dosar_din_cale(cale, radacina=None):
    """Calea unei referinte de post DAB al releului din satelit (http://127.0.0.1:<port>/dab/<feed>/<SID>[.ts], cu
    sau fara %3a) -> dosarul postului, sau None pentru orice altceva (/dab/<feed>/lista, T2, stickul USB, alt flux)."""
    try:
        text = cale.decode("utf-8", "replace") if isinstance(cale, bytes) else u"%s" % cale
    except Exception:
        return None
    text = text.replace("%3a", ":").replace("%3A", ":")
    if not text.lower().startswith("http://"):
        return None
    gazda_port, _, drum = text[7:].partition("/")
    gazda = gazda_port.rpartition(":")[0] or gazda_port
    if gazda not in ("127.0.0.1", "localhost"):
        return None
    bucati = [b for b in drum.split("?")[0].split("/") if b]
    if len(bucati) != 3 or bucati[0] != "dab" or bucati[2] == "lista":
        return None
    try:
        sid = sid_din_text(bucati[2])
    except ValueError:
        return None
    return dosar_post(bucati[1], sid, radacina)


def imagine_din_dosar(dosar):
    """Calea imaginii postului (cea mai noua dintre imagine.jpg si imagine.png), sau "" cand nu e niciuna."""
    if not dosar:
        return ""
    alese = ("", -1.0)
    for ext in ("jpg", "png"):
        c = os.path.join(dosar, "imagine." + ext)
        try:
            t = os.stat(c).st_mtime
        except OSError:
            continue
        if t > alese[1]:
            alese = (c, t)
    return alese[0]


def text_din_dosar(dosar):
    try:
        with open(os.path.join(dosar, "text"), "rb") as f:
            return f.read(1024).decode("utf-8", "replace").strip()
    except (IOError, OSError, TypeError, AttributeError):
        return u""


def sterge_dosar(dosar):
    """Textul si imaginile unui post (sau ale tuturor, cu dosarul radacina), fara sa cada daca lipsesc."""
    if not dosar:
        return
    try:
        nume = os.listdir(dosar)
    except OSError:
        return
    for n in nume:
        c = os.path.join(dosar, n)
        if os.path.isdir(c):
            sterge_dosar(c)
            continue
        try:
            os.unlink(c)
        except OSError:
            pass
    try:
        os.rmdir(dosar)
    except OSError:
        pass


_inlocuieste = getattr(os, "replace", os.rename)


def scrie_atomic(cale, date):
    d = os.path.dirname(cale)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    tmp = cale + ".tmp"
    with open(tmp, "wb") as f:
        f.write(date)
    _inlocuieste(tmp, cale)


# ---------------------------------------------------------------- MP2: unde e PAD-ul in cadru
def lungime_mp2(antet):
    """Antetul MPEG audio Layer II (4 octeti, bytearray) -> (lungimea cadrului, lungimea ScF-CRC), sau None."""
    if antet[0] != 0xFF or (antet[1] & 0xE6) != 0xE4:          # sincronizare, Layer II
        return None
    mpeg1 = antet[1] & 0x08
    bi = antet[2] >> 4
    fi = (antet[2] >> 2) & 3
    kbit = (_KBIT_MPEG1 if mpeg1 else _KBIT_MPEG2)[bi]
    if not kbit or fi == 3:
        return None
    rata = ((44100, 48000, 32000) if mpeg1 else (22050, 24000, 16000))[fi]
    lung = 144000 * kbit // rata + ((antet[2] >> 1) & 1)
    mono = (antet[3] >> 6) == 3
    scf = 2 if mpeg1 and kbit < (56 if mono else 112) else 4
    return lung, scf


# ---------------------------------------------------------------- decodorul
class DecodorPad(object):
    """Un post: cadre MP2 (din_mp2) sau AU-uri DAB+ (din_au) -> text si imagine in `dosar`.
    imagini=False: MOT nu se mai reasambleaza deloc (setarea „Imaginile posturilor DAB” pe Nu); textul ramane."""

    def __init__(self, dosar=None, imagini=True):
        self.dosar = dosar
        self.imagini = imagini
        self.text = u""
        self.text_scris = None
        self.imagine_crc = None
        self.contoare = {"pad": 0, "dls": 0, "dls_rele": 0, "mot_grupuri": 0, "mot_rele": 0, "imagini": 0}
        self._cont = None                      # (aplicatia de continuare, lungimea) din X-PAD-ul de dinainte
        self._dls = None                       # grupul DLS in lucru (bytearray)
        self._dls_toggle = None
        self._dls_seg = {}                     # numar -> (octeti, ultimul)
        self._dls_set = SET_EBU
        self._mot = None                       # grupul MOT in lucru
        self._mot_lung = 0
        self._dgli = 0
        self._obiecte = {}                     # ID de transport -> obiect MOT in lucru
        self._refuzate = []                    # ID-uri de transport ale obiectelor care nu sunt imagini
        self._mp2 = None                       # cadru MP2 de 48 ms (24 kHz), strans din doua CIF-uri

    # ------------------------------------------------------------ intrarile
    def din_mp2(self, cif):
        """Un CIF al subcanalului MP2 (24 ms). La 48 kHz e chiar un cadru; la 24 kHz cadrul tine doua CIF-uri."""
        n = len(cif)
        if n < 8:
            return
        if self._mp2 is None:
            a = bytearray(cif[:4])
            r = lungime_mp2(a)
            if r is None:
                return
            lung, scf = r
            if lung == n:
                self._cadru_mp2(cif, n, scf)
                return
            if lung > n and lung <= 2 * n + 4:
                self._mp2 = (bytearray(cif), lung, scf)
            return
        buf, lung, scf = self._mp2
        buf += cif
        if len(buf) >= lung:
            self._mp2 = None
            self._cadru_mp2(buf, lung, scf)
            rest = buf[lung:]
            if len(rest) >= 4:
                self.din_mp2(bytes(rest))

    def _cadru_mp2(self, c, n, scf):
        f = bytearray(c[n - 2:n])
        if f[0] >> 6 or not (f[0] >> 4) & 3:
            self._cont = None                  # fara X-PAD: continuarea se pierde
            return
        capat = n - 2 - scf
        inceput = max(4, capat - X_PAD_MAX)
        if capat <= inceput:
            return
        x = bytearray(c[inceput:capat])
        x.reverse()
        self._x_pad(x, False, f[0], f[1])

    def din_au(self, au):
        """Un AU DAB+ bun (fara cei 2 octeti de CRC). PAD-ul e in elementul DSE cu care incepe AU-ul, cand exista."""
        if len(au) < 4:
            return
        b0 = au[0]
        if not isinstance(b0, int):            # Python 2.7, memoryview
            b0 = ord(b0)
        if b0 >> 5 != 4:
            self._cont = None
            return
        h = bytearray(au[1:3])
        count, o = h[0], 2
        if count == 255:
            count += h[1]
            o = 3
        if count < 2 or o + count > len(au):
            return
        p = bytearray(au[o:o + count])
        f0, f1 = p[-2], p[-1]
        if f0 >> 6 or not (f0 >> 4) & 3:
            self._cont = None
            return
        x = p[:-2]
        x.reverse()
        self._x_pad(x, True, f0, f1)

    # ------------------------------------------------------------ X-PAD
    def _x_pad(self, x, exact, f0, f1):
        self.contoare["pad"] += 1
        fel = (f0 >> 4) & 3
        ci = f1 & 0x02
        sub = []
        if fel == 1:                                         # X-PAD scurt: 4 octeti
            if len(x) < 4:
                return
            if ci:
                app = x[0] & 0x1F
                if app:
                    sub.append((app, x[1:4]))
                    self._cont = (_CONTINUARE.get(app, app), 4)
                else:
                    self._cont = None
            elif self._cont is not None:
                sub.append((self._cont[0], x[0:4]))
        elif fel == 2:                                       # X-PAD variabil
            if ci:
                lista = []
                o = 0
                while o < len(x) and len(lista) < 4:
                    c = x[o]
                    o += 1
                    if not c & 0x1F:
                        break
                    lista.append((c & 0x1F, LUNG_CI[c >> 5]))
                total = o + sum(l for _, l in lista)
                if not lista or total > len(x):
                    self._cont = None
                    return
                for app, l in lista:
                    sub.append((app, x[o:o + l]))
                    o += l
                self._cont = (_CONTINUARE.get(lista[-1][0], lista[-1][0]), total)
            elif self._cont is not None:
                app, l = self._cont
                sub.append((app, x if exact else x[:l]))
        else:
            self._cont = None
            return
        for app, d in sub:
            if app == APP_DGLI:
                if len(d) >= 4 and _crc_bun(d[:4]):
                    self._dgli = ((d[0] & 0x3F) << 8) | d[1]
            elif app == APP_DLS:
                self._dls = bytearray(d)
                self._dls_gata()
            elif app == APP_DLS_CONT:
                if self._dls is not None:
                    self._dls += d
                    self._dls_gata()
            elif app == APP_MOT:
                if self.imagini:
                    self._mot = bytearray(d)
                    self._mot_lung = self._dgli
                    self._dgli = 0
                    self._mot_gata()
            elif app == APP_MOT_CONT:
                if self._mot is not None:
                    self._mot += d
                    self._mot_gata()

    # ------------------------------------------------------------ DLS
    def _dls_gata(self):
        g = self._dls
        if len(g) < 2:
            return
        b0, b1 = g[0], g[1]
        if b0 & 0x10:                                        # comanda
            cmd = b0 & 0x0F
            nevoie = 2 + ((b1 & 0x0F) + 1 if cmd == 2 else 0) + 2
        else:
            nevoie = 2 + (b0 & 0x0F) + 1 + 2
        if len(g) < nevoie:
            return
        self._dls = None
        grup = g[:nevoie]
        if not _crc_bun(grup):
            self.contoare["dls_rele"] += 1
            return
        self.contoare["dls"] += 1
        toggle = b0 >> 7
        if toggle != self._dls_toggle:
            self._dls_toggle = toggle
            self._dls_seg = {}
        if b0 & 0x10:
            if b0 & 0x0F == 1:                               # sterge eticheta
                self._dls_seg = {}
                self._pune_text(u"")
            return                                           # 2 = DL Plus: numai etichetele piesei, nu se arata
        if b0 & 0x40:
            nr = 0
            self._dls_set = b1 >> 4
        else:
            nr = (b1 >> 4) & 7
        self._dls_seg[nr] = (bytes(grup[2:nevoie - 2]), bool(b0 & 0x20))
        parti = []
        k = 0
        while k in self._dls_seg:
            octeti, ultimul = self._dls_seg[k]
            parti.append(octeti)
            if ultimul:
                self._pune_text(decodeaza_text(b"".join(parti), self._dls_set & 0x0F))
                return
            k += 1

    def _pune_text(self, text):
        self.text = text
        if text == self.text_scris or not self.dosar:
            return
        try:
            scrie_atomic(os.path.join(self.dosar, "text"), text.encode("utf-8"))
            self.text_scris = text
        except (IOError, OSError):
            pass

    # ------------------------------------------------------------ MOT
    def _mot_gata(self):
        g = self._mot
        if len(g) > GRUP_MAX:
            self._mot = None
            return
        lung = self._mot_lung or _lungime_grup(g)
        if not lung or len(g) < lung:
            return
        self._mot = None
        self._grup_mot(g[:lung])

    def _grup_mot(self, d):
        self.contoare["mot_grupuri"] += 1
        n = len(d)
        if n < 9:
            return
        b0 = d[0]
        tip = b0 & 0x0F
        if not (b0 & 0x20 and b0 & 0x10) or tip not in (3, 4):
            return
        if b0 & 0x40:
            if not _crc_bun(d):
                self.contoare["mot_rele"] += 1
                return
            n -= 2
        o = 4 if b0 & 0x80 else 2
        ultimul = d[o] & 0x80
        nr = ((d[o] & 0x7F) << 8) | d[o + 1]
        ua = d[o + 2]
        o += 3
        li = ua & 0x0F
        if not ua & 0x10 or li < 2 or o + li + 2 > n:
            return
        tid = (d[o] << 8) | d[o + 1]
        o += li
        marime = ((d[o] & 0x1F) << 8) | d[o + 1]
        o += 2
        if o + marime > n:
            return
        if tid in self._refuzate:
            return
        ob = self._obiecte.get(tid)
        if ob is None:
            if len(self._obiecte) >= OBIECTE_MAX:
                del self._obiecte[min(self._obiecte, key=lambda k: self._obiecte[k]["varsta"])]
            ob = self._obiecte[tid] = {"varsta": self.contoare["mot_grupuri"], 3: {}, 4: {}, "ultim3": None,
                                       "ultim4": None, "octeti": 0}
        parti = ob[tip]
        if nr not in parti:
            if ob["octeti"] + marime > IMAGINE_MAX + 8192:
                del self._obiecte[tid]
                return
            parti[nr] = bytes(d[o:o + marime])
            ob["octeti"] += marime
        if ultimul:
            ob["ultim%d" % tip] = nr
        self._obiect_gata(tid, ob)

    def _obiect_gata(self, tid, ob):
        antet = _lipit(ob[3], ob["ultim3"])
        if antet is None:
            return
        if len(antet) < 7:
            del self._obiecte[tid]
            return
        h = bytearray(antet[:7])
        corp_marime = (h[0] << 20) | (h[1] << 12) | (h[2] << 4) | (h[3] >> 4)
        tip = (h[5] >> 1) & 0x3F
        subtip = ((h[5] & 1) << 8) | h[6]
        if tip != 2 or subtip not in (1, 3) or corp_marime > IMAGINE_MAX:
            del self._obiecte[tid]                           # nu e imagine JPEG / PNG (sau e prea mare): segmentele
            self._refuzate.append(tid)                       # lui care se repeta in carusel nu se mai strang
            del self._refuzate[:-8]
            return
        corp = _lipit(ob[4], ob["ultim4"])
        if corp is None:
            return
        del self._obiecte[tid]
        if len(corp) != corp_marime:
            self.contoare["mot_rele"] += 1
            return
        if corp[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif corp[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        else:
            self.contoare["mot_rele"] += 1
            return
        self._pune_imagine(corp, ext)

    def _pune_imagine(self, date, ext):
        crc = (zlib.crc32(date) & 0xFFFFFFFF, len(date))
        if crc == self.imagine_crc or not self.dosar:
            return
        try:
            scrie_atomic(os.path.join(self.dosar, "imagine." + ext), date)
            alta = os.path.join(self.dosar, "imagine." + ("png" if ext == "jpg" else "jpg"))
            if os.path.exists(alta):
                os.unlink(alta)
            self.imagine_crc = crc
            self.contoare["imagini"] += 1
        except (IOError, OSError):
            pass

    def stare(self):
        s = dict(self.contoare)
        s["text"] = self.text
        return s


def _lipit(parti, ultimul):
    """Segmentele 0..ultimul lipite, sau None cand lipseste vreunul (ori nu s-a vazut inca ultimul)."""
    if ultimul is None or len(parti) < ultimul + 1:
        return None
    try:
        return b"".join([parti[i] for i in range(ultimul + 1)])
    except KeyError:
        return None


def _lungime_grup(g):
    """Lungimea unui grup de date MOT din antetele lui (cand n-a venit indicatorul de lungime, AppTy 1), sau 0."""
    if len(g) < 2:
        return 0
    b0 = g[0]
    if not (b0 & 0x20 and b0 & 0x10):
        return 0
    o = 4 if b0 & 0x80 else 2
    if len(g) < o + 3:
        return 0
    li = g[o + 2] & 0x0F
    o += 3 + li
    if len(g) < o + 2:
        return 0
    return o + 2 + (((g[o] & 0x1F) << 8) | g[o + 1]) + (2 if b0 & 0x40 else 0)

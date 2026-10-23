# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Baza unica a valorilor tehnice pe canal si pe transponder (/etc/enigma2/hds_baza_canale.jsonl).

Modul curat: nu importa nimic din enigma, deci se probeaza in intregime pe PC. Ceasul, sistemul de fisiere, contorul
zilei, pornirea firului de scriere si jurnalul se primesc din afara (valori implicite pentru receptor).

FORMATUL (JSON pe randuri, numai ASCII, ensure_ascii):
  rand 1   antetul: {"fel":"hds-baza-canale","v":1,"scris":<s>,"imagine":"..","canale":N,"transpondere":M,
           "migrat":{fisier:[mtime,marime]},"pornire_md5":".."} (si, dupa unirea bazei de pornire,
           "pornire_stb_md5", "pornire_versiune": vezi CHEI_ANTET_PORNIRE)
  randuri  {"k":<cheie canal>,"vf":{grupa:[data,sursa(,fel)]},<grupe>} si {"tp":<cheie transponder>,...}
  ultimul  {"sfarsit":N}, N = numarul randurilor de date; fara el, sau cu alt N, fisierul e taiat.
  In memorie randurile stau ca text (dict cheie -> text) si se desfac numai la cerere; `cauta` intoarce o copie.

CHEI: canal = HdsIndexCanale.cheie_din_ref ("sid:ns:tsid:onid" hex fara zerouri in fata, sau cheia de flux);
transponder = "ns:tsid:onid" (hex, fara zerouri); cheia de rezerva "onid:tsid:sid@poz", poz = ns >> 16
(C = cablu 0xFFFF, T = terestru 0xEEEE), folosita numai la cerere (cauta(..., rezerva=True)) si numai cu un singur
alt rand candidat, care se uneste pe loc sub cheia noua.

GRUPE PE CANAL (pozitii; -1 sau "" = nu se stie):
  sv  [furnizor, tip serviciu, nume]
  pmt [PID PMT, PCR, video, stream_type video, teletext, AIT]; AIT 0 = PMT citit, fara AIT HbbTV
  ca  [0 FTA / 1 criptat, [[CAID, PID ECM], ...]]
  pi  campurile a [[limbi, fel, descriere audio 0/1, PID]], d [[limba, surzi 0/1, PID]],
      x [[limba, pagina, surzi 0/1]], tt 0/1 (o cheie lipsa = nu se stie, o lista goala = stiut: nimic)
  hb  HbbTV 0/1
  ap  AIT-ul HbbTV citit (Components/HdsHbbtv.grupa_ap): [aplicatii de pornit, autostart 0/1, transportul aplicatiei
      de la ROSU "h" / "c" / "hc", versiunea AIT, adresa de baza fara parametri, numele, lista]; [0, 0, "", -1, "", ""]
      = PMT fara AIT HbbTV. lista (pozitia 6, numai cand AIT-ul are aplicatii de pornit; fara ea = scrisa de un modul
      fara lista) = [[cod 1 AUTOSTART / 2 PRESENT, organisation_id, application_id, transport "h" / "c" / "hc",
      adresa completa de pornire (cu parametrii; "" fara HTTP), lungimea adresei cand e taiata la MAX_AP_URL
      (0 = intreaga), numele], ...], cea de la ROSU intai, cel mult MAX_AP_LISTA; mai putine elemente decat ap[0] =
      lista taiata (la numar, la marime sau de rand_canal). Dintr-o bucata: la unire nu ia campuri din cealalta valoare
      (doua versiuni ale AIT-ului nu se amesteca). Un rand cu ap, citit de un modul fara ap, o pastreaza neatinsa (cheie
      necunoscuta); un modul cu ap dar fara lista o scoate cand schimba randul.
  vd  [latime, inaltime, progresiv 1/0, cadre in miimi, gama 0-3, aspect "16:9"/"4:3", codec mpeg2/h264/h265/alt]
  br  [total, video, audio] kbit/s
  pc  [profil, format pixeli, esantionare culoare, gama culoare, GOP mediu, codec audio, esantionare audio,
      canale audio, format audio, [pachete stricate, pachete], durata masurarii s]
  sg  [nivel %, calitate %, SNR zecimi dB, BER, tuner]; nu murdareste niciodata baza (ultima valoare sta in memorie si
      pleaca pe disc cu o scriere care are loc oricum) si nu iese niciodata in exportul CSV sau in baza de pornire.
GRUPE PE TRANSPONDER: pr (f kHz, pol, sr kSym/s, poz; data in "vf"), dc (sis, fec, mod, ro, pil, inv, bw, crh, crl,
  gi, tm, hi, retea, nsv; data in "vfo" cand vin de la operator, altfel declarate cu data din "vf"), ms (mis, plsm,
  plsc, plp, t2mi; data in "vfj").

SURSE si ordinea la unire (uneste_grupa, o singura functie):
  intai felul: o valoare a receptorului (fel 0, 1, 3) bate mereu una din baza de pornire (fel 2), oricare ar fi data
  sau sursa, si ii ia locul la prima vizionare (fara a doua vizionare in vd); intre doua valori de acelasi fel:
  verificat cu data (v, p, j, m): cea mai noua data castiga; la data egala, cea exacta bate cea aproximativa (fel 1);
  > verificat fara data (c, sau o data in afara ferestrei) > declarat de operator (o) > declarat (l) > nu se stie.
  La egalitate deplina, sau cand o data lipseste, castiga valoarea locala. Un camp necunoscut al grupei castigatoare
  se ia din cealalta (in vd numai la aceeasi inaltime): o valoare stiuta nu se inlocuieste cu "nu se stie". O data in afara [01.01.2026, acum + 1 zi]
  e necunoscuta. fel: 0 normal, 1 data aproximativa, 2 baza de pornire, 3 import.

SCRIEREA (un singur drum): instantaneul (lista de referinte la randuri) se ia pe firul apelantului; firul de scriere,
sub un lacat, scrie .nou.<nr> (writelines, flush, fsync), face .bak prin os.link(viu, .bak.nou) + os.replace (numai
daca viul exista si a fost citit curat sau scris de noi; o eroare aici nu opreste scrierea), apoi os.replace pe viu si
fsync pe dosar. Nu face makedirs. "Murdar" = versiune != versiune_scrisa; versiunea scrisa e cea a instantaneului.
Stari: scrie, numai-citire (citire nereusita sau cazuta cu o exceptie, fisier stricat nepus deoparte, v mai mare,
peste 16 MiB, dosar lipsa), oprit (nicio scriere pana la repornirea interfetei; nicio alta stare nu o inlocuieste),
amanat (3 erori la rand; iese la standby). Un fisier stricat se pune deoparte ca .stricat-AAAALLZZ printr-o legatura
tare: fisierul viu ramane pe loc pana il inlocuieste prima scriere.
Pe disc: prag = max(300 s, marime * 86400 / 50 MiB) si cel mult 50 MiB pe zi (contorul zilei in /var/run); standby,
oprire, copie, actualizare si uitare nu asteapta pragul, dar se numara (uitarea cel mult o data la
MARGINE_UITARE_S). Continut egal nu murdareste baza (confirmarea
sta in memorie, cu felul datei ei, si intra in "vf" la urmatoarea scriere); o grupa verificata mai veche de 7 zile se
reimprospateaza. Latimea, cadrele pe secunda, aspectul, gama si progresivul vii diferite de baza se scriu dupa 2
vizionari la rand cu aceleasi valori (o valoare cu data aproximativa, din migrare, nu asteapta). In vd, o valoare cu
alta inaltime nu ia campurile necunoscute din cealalta (ar amesteca doua imagini).
LIMITE: scrierea tine fisierul sub 10 MiB (pleaca randul cu cea mai veche data a celei mai noi grupe) si randul sub
4 KiB (taie pc, apoi pistele peste 16, apoi textele peste 12, apoi lista aplicatiilor din ap); citirea primeste
16 MiB si randuri de 8 KiB (un rand mai lung nu se desface: se sare, se pastreaza neatins la scriere, iar valorile noi
pentru el nu se scriu).
Datele din fisier sau din afara nu arunca exceptii: JSON rau sau prea adanc, NaN, Infinity, forme neasteptate.
MIGRAREA (Migrare, pe bucati; migreaza, dintr-o bucata): fisierele de dinainte (hds_piste_canale.json,
hds_masuratori_canale.json, hds_acces_canale.json) se unesc in baza pe grupe, cu data lor sau, fara ea, cu data
fisierului (aproximativa); raman pe loc, neatinse, iar antetul "migrat" tine [mtime, marime] al fiecaruia (unul schimbat
de atunci se uneste din nou; o intrare fara data nu bate atunci o grupa aflata dupa migrarea de dinainte). Cu ceasul
receptorului nepotrivit (inainte de 2026, sau cu peste o zi in urma fata de data fisierului) fisierul asteapta.
PRIVIREA (Vedere): dictionarul numai de citit al adaptoarelor acelor cititori, desfacut la cerere (HdsPisteCanale,
HdsIndexCanale, HdsAccesCanale), cu versiunea grupelor lui (versiune_grupe: o schimbare a accesului nu reface pistele
indexului). Culegerea si ceasurile bazei: Components/HdsCulegereCanale.py.
"""

from __future__ import absolute_import

import calendar
import collections
import csv
import errno
import io
import json
import os
import re
import stat
import threading
import time

try:
	from Components import HdsIndexCanale as _X
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsIndexCanale as _X

CALE = "/etc/enigma2/hds_baza_canale.jsonl"
CALE_CONTOR = "/var/run/hds-baza-canale.buget"
FEL = "hds-baza-canale"
VERSIUNE = 1

MAX_SCRIS = 10 * 1024 * 1024
# cand bugetul e depasit, se scoate pana la 90%, ca urmatoarele scrieri sa nu refaca socoteala pe toata baza
TINTA_SCOATERE = 0.9
MAX_CITIT = 16 * 1024 * 1024
RAND_SCRIS = 4 * 1024
RAND_CITIT = 8 * 1024
MAX_PISTE_INTRARE = 32
MAX_PISTE = 16
MAX_TEXT_INTRARE = 32
MAX_TEXT = 12
MAX_TEXT_LUNG = 64
MAX_CA = 64
MAX_CA_TAIAT = 16
MAX_STRICATE = 2
MAX_AP_APLICATII = 64
MAX_AP_ADRESA = 120
MAX_AP_NUME = 32
MAX_AP_LISTA = 16
MAX_AP_URL = 500

PRAG_MIN_S = 300
BUGET_ZI = 50 * 1024 * 1024
PROASPAT_S = 7 * 86400
ZI_S = 86400
DATA_MIN = calendar.timegm((2026, 1, 1, 0, 0, 0))
ERORI_AMANARE = 3
REINCERCARE_S = 600
REINCERCARI_MAX = 3
ASTEPTARE_FIR_S = 3.0
# doua scrieri "uitare" la rand (de ex. din web, in bucla) nu rescriu tot fisierul mai des de atat
MARGINE_UITARE_S = 10
# o data in "vf" in afara acestui interval nu e o data (si nu trece prin time.localtime)
_DATA_MAX_ABS = 2 ** 53
# un rand cu mai multe paranteze nu e al modulului (vezi _loads)
_PARANTEZE_MAX = 512

# motivele unei scrieri
PRAG = "prag"
STANDBY = "standby"
OPRIRE = "oprire"
COPIE = "copie"
ACTUALIZARE = "actualizare"
UITARE = "uitare"
MOTIVE = (PRAG, STANDBY, OPRIRE, COPIE, ACTUALIZARE, UITARE)

# starile scrierii
SCRIE = "scrie"
NUMAI_CITIRE = "numai-citire"
OPRIT = "oprit"
AMANAT = "amanat"
# motivele starii numai-citire
NECITIT = "necitit"
DEGRADAT = "degradat"
V_MAI_MARE = "v-mai-mare"
PREA_MARE = "prea-mare"
DOSAR_LIPSA = "dosar-lipsa"

SURSE_CU_DATA = ("v", "p", "j", "m")
SURSE = ("l", "c", "o") + SURSE_CU_DATA
FEL_NORMAL = 0
FEL_APROXIMATIV = 1
FEL_PORNIRE = 2
FEL_IMPORT = 3

# antetul unirii bazei de pornire (Components/HdsBazaPornire.py): md5-ul fisierului din imagine si al celui luat de pe
# stb, unite deja, si versiunea celei mai noi baze de pornire unite; se uita fara .bak bun (unirea se reface)
CHEI_ANTET_PORNIRE = ("pornire_md5", "pornire_stb_md5", "pornire_versiune")
GRUPE_CANAL = ("sv", "pmt", "ca", "pi", "hb", "ap", "vd", "br", "pc", "sg")
GRUPE_TP = ("pr", "dc", "ms")
CAMPURI_PI = ("a", "d", "x", "tt")
# ordinea cheilor intr-un rand de canal; alte chei (de la o versiune mai noua) se pastreaza dupa ele
_ORDINE_CANAL = ("k", "vf", "sv", "pmt", "ca", "a", "d", "x", "tt", "hb", "ap", "vd", "br", "pc", "sg")
# in vd: latimea (1440 sau 1920 la aceeasi inaltime), progresivul, cadrele pe secunda, gama si aspectul se schimba de
# la o emisiune la alta; inaltimea si codecul nu
VD_VOLATILE = (0, 2, 3, 4, 5)

_NECUNOSCUTE = (-1, "", None)


def _(text):
	"""Traducerea imaginii (builtins._); pe PC, in teste, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


def _jurnal_implicit(text):
	print("[HdsBazaCanale] %s" % text)


def _loads(text):
	"""json.loads pe date din fisier sau din afara: None pentru un text care nu se desface si pentru unul cu peste
	_PARANTEZE_MAX paranteze. Pragul la care json.loads arunca RecursionError depinde de versiunea Python (~3000 de
	niveluri pe 3.12, ~4000 pe 3.14), iar o structura adanca desfacuta ar ajunge la functiile recursive (_stiut) si la
	apelanti; un rand scris de modul are cel mult ~200 de paranteze, deci numaratoarea da acelasi raspuns pe orice
	versiune, fara desfacere."""
	if text.count("[") + text.count("{") > _PARANTEZE_MAX:
		return None
	try:
		return json.loads(text)
	except (ValueError, RecursionError):
		return None


# ---------------------------------------------------------------- date si ceas

def data_valida(t, acum):
	"""O data e stiuta numai in [01.01.2026, acum + 1 zi]; altfel (ceas nereglat) e necunoscuta."""
	if isinstance(t, bool) or not isinstance(t, (int, float)):
		return False
	return DATA_MIN <= t <= acum + ZI_S


def _data_stocata(t, acum):
	return int(t) if data_valida(t, acum) else 0


def _zi(t):
	return time.strftime("%Y%m%d", time.localtime(t))


def _luna(t):
	"""Prima zi a lunii (UTC), pentru baza de pornire."""
	g = time.gmtime(t)
	return calendar.timegm((g.tm_year, g.tm_mon, 1, 0, 0, 0))


# ---------------------------------------------------------------- chei

_RE_DVB = re.compile(r"^[0-9a-fA-F]{1,8}(:[0-9a-fA-F]{1,8}){3}$")
_RE_TP = re.compile(r"^[0-9a-fA-F]{1,8}(:[0-9a-fA-F]{1,8}){2}$")
_RE_CHEIE_RAND = re.compile(r'^\{"(k|tp)":"([^"\\]{1,400})"[,}]')
_RE_COD = re.compile(r"^[A-Za-z0-9/.+-]{1,12}$")
# obiectul "vf" al unui rand-text (listele din el nu au acolade)
_RE_OBIECT_VF = re.compile(r'"vf":\{([^{}]*)\}')


def cheie(ref_sau_cheie):
	"""Referinta de serviciu sau cheie -> cheia canalului (forma lui cheie_din_ref) sau None."""
	if not isinstance(ref_sau_cheie, str) or not ref_sau_cheie:
		return None
	s = ref_sau_cheie.strip()
	if s.count(":") == 3 and _RE_DVB.match(s):
		p = [int(x, 16) for x in s.split(":")]
		return "%x:%x:%x:%x" % tuple(p)
	if s.count(":") < 9:
		return None
	try:
		return _X.cheie_din_ref(s)
	except Exception:
		return None


def cheie_tp(text):
	"""Cheia transponderului din "ns:tsid:onid" (si forma lamedb "%08x:%04x:%04x") -> "%x:%x:%x" sau None."""
	if not isinstance(text, str) or not _RE_TP.match(text.strip()):
		return None
	p = [int(x, 16) for x in text.strip().split(":")]
	return "%x:%x:%x" % tuple(p)


def cheie_tp_din_cheie(k):
	"""Transponderul unui canal DVB, din propria cheie ("sid:ns:tsid:onid" -> "ns:tsid:onid"); fluxuri: None."""
	if not isinstance(k, str) or k.count(":") != 3:
		return None
	p = k.split(":")
	return cheie_tp(":".join(p[1:]))


def poz_din_ns(ns):
	"""Pozitia orbitala din namespace (ns >> 16): intreg x10 (est +, vest -), "C" cablu, "T" terestru."""
	sus = (ns >> 16) & 0xFFFF
	if sus == 0xFFFF:
		return "C"
	if sus == 0xEEEE:
		return "T"
	return sus - 3600 if sus > 1800 else sus


def cheie_rezerva(k):
	"""Cheia de rezerva "onid:tsid:sid@poz" a unui canal DVB (fara bitii de frecventa din namespace), sau None."""
	if not isinstance(k, str) or k.count(":") != 3 or not _RE_DVB.match(k):
		return None
	sid, ns, tsid, onid = [int(x, 16) for x in k.split(":")]
	return "%x:%x:%x@%s" % (onid, tsid, sid, poz_din_ns(ns))


def cheie_din_cheie_limbi(k):
	"""Cheia fisierelor de alegeri ale pistelor ("sid:tsid:onid:ns") -> cheia bazei ("sid:ns:tsid:onid")."""
	if not isinstance(k, str) or not _RE_DVB.match(k.strip()):
		return None
	sid, tsid, onid, ns = [int(x, 16) for x in k.strip().split(":")]
	return "%x:%x:%x:%x" % (sid, ns, tsid, onid)


# ---------------------------------------------------------------- curatarea valorilor (strict, ca pentru date din afara)

def _intreg(v, mn, mx):
	if isinstance(v, bool) or not isinstance(v, int):
		return -1
	return v if mn <= v <= mx else -1


def _numar(v, mn, mx):
	if isinstance(v, bool) or not isinstance(v, (int, float)):
		return -1
	if v != v or not (mn <= v <= mx):
		return -1
	return v if isinstance(v, int) else round(float(v), 1)


def _text(v, mx):
	if isinstance(v, bool):
		return ""
	if isinstance(v, int):
		v = str(v)
	if not isinstance(v, str):
		return ""
	t = "".join(c for c in v.strip() if c.isprintable())
	return t[:mx]


def _cod_text(v):
	t = _text(v, MAX_TEXT)
	return t if _RE_COD.match(t) else ""


def _limba(v):
	t = _text(v, MAX_TEXT_INTRARE).lower()
	return t if all(c.isalpha() or c == "/" for c in t) else ""


def _enum(v, permise):
	return v if isinstance(v, str) and v in permise else ""


def _01(v):
	if isinstance(v, bool):
		return int(v)
	return v if v in (0, 1) and isinstance(v, int) else -1


def _pid(v):
	return _intreg(v, 0, 8191)


def _pereche(v):
	if isinstance(v, (list, tuple)) and len(v) == 2:
		a, b = _intreg(v[0], 0, 2 ** 53), _intreg(v[1], 0, 2 ** 53)
		if a >= 0 and b >= 0:
			return [a, b]
	return [-1, -1]


def _codec(v):
	if not isinstance(v, str) or not v.strip():
		return ""
	t = v.strip().lower()
	return t if t in ("mpeg2", "h264", "h265") else "alt"


def _inaltime(v):
	# 0 (canal criptat nedecodat) = nu se stie
	h = _intreg(v, 0, 16384)
	return h if h > 0 else -1


# fiecare pozitie: functia care o curata
_POZITII = {
	"sv": (lambda v: _text(v, MAX_TEXT_LUNG), lambda v: _intreg(v, 0, 255), lambda v: _text(v, MAX_TEXT_LUNG)),
	"pmt": (_pid, _pid, _pid, lambda v: _intreg(v, 0, 255), _pid, _pid),
	"vd": (lambda v: _intreg(v, 1, 16384), _inaltime, _01, lambda v: _intreg(v, 1, 1000000),
		lambda v: _intreg(v, 0, 3), lambda v: _enum(v, ("16:9", "4:3")), _codec),
	"br": (lambda v: _intreg(v, 0, 10 ** 7),) * 3,
	"pc": ((lambda v: _text(v, MAX_TEXT_LUNG),) * 4 + (lambda v: _numar(v, 0, 100000),) +
		(lambda v: _text(v, MAX_TEXT_LUNG), lambda v: _intreg(v, 1, 10 ** 6), lambda v: _text(v, MAX_TEXT_LUNG),
		lambda v: _text(v, MAX_TEXT_LUNG), _pereche, lambda v: _numar(v, 0, 10 ** 6))),
	"sg": (lambda v: _intreg(v, 0, 100), lambda v: _intreg(v, 0, 100), lambda v: _intreg(v, 0, 100000),
		lambda v: _intreg(v, 0, 2 ** 31 - 1), lambda v: _intreg(v, 0, 63)),
}

_TP_CAMPURI = {
	"pr": ("f", "pol", "sr", "poz"),
	"dc": ("sis", "fec", "mod", "ro", "pil", "inv", "bw", "crh", "crl", "gi", "tm", "hi", "retea", "nsv"),
	"ms": ("mis", "plsm", "plsc", "plp", "t2mi"),
}
_TP_VF = {"pr": "vf", "dc": "vfo", "ms": "vfj"}
_SURSE_TP = {"pr": ("l", "v", "j", "m"), "dc": ("l", "o"), "ms": ("j", "m", "v", "p")}
# campurile DVB-T si cele de operator se scriu numai cand se stiu
_TP_OPTIONALE = ("bw", "crh", "crl", "gi", "tm", "hi", "retea", "nsv")


def _poz(v):
	if v in ("C", "T"):
		return v
	i = _intreg(v, -1800, 1800)
	return i if i != -1 or v == -1 else ""


_TP_CURATA = {
	"f": lambda v: _intreg(v, 1, 10 ** 8), "pol": lambda v: _enum(v, ("H", "V", "L", "R")),
	"sr": lambda v: _intreg(v, 1, 10 ** 6), "poz": _poz,
	"sis": lambda v: _enum(v, ("S", "S2", "C", "T", "T2")), "fec": _cod_text, "mod": _cod_text, "ro": _cod_text,
	"pil": _cod_text, "inv": lambda v: _intreg(v, 0, 2), "bw": lambda v: _intreg(v, 0, 100000), "crh": _cod_text,
	"crl": _cod_text, "gi": _cod_text, "tm": _cod_text, "hi": _cod_text, "retea": lambda v: _text(v, MAX_TEXT_LUNG),
	"nsv": lambda v: _intreg(v, 0, 65535), "mis": lambda v: _intreg(v, 0, 255), "plsm": lambda v: _intreg(v, 0, 2),
	"plsc": lambda v: _intreg(v, 0, 262143), "plp": lambda v: _intreg(v, 0, 255), "t2mi": lambda v: _intreg(v, 0, 8191),
}


def _stiut(e):
	if isinstance(e, list):
		return any(_stiut(x) for x in e)
	return e not in _NECUNOSCUTE


def _pozitional(grupa, v):
	functii = _POZITII[grupa]
	if not isinstance(v, (list, tuple)):
		return None
	rez = [f(v[i]) if i < len(v) else f(None) for i, f in enumerate(functii)]
	return rez if any(_stiut(e) for e in rez) else None


def _piste(v):
	"""Grupa pi: dict cu a, d, x, tt; o cheie lipsa = nu se stie."""
	if not isinstance(v, dict):
		return None
	rez = {}
	if isinstance(v.get("a"), list):
		a = []
		for p in v["a"][:MAX_PISTE_INTRARE]:
			if isinstance(p, (list, tuple)) and len(p) >= 2:
				a.append([_limba(p[0]), _text(p[1], MAX_TEXT_INTRARE).upper(), max(_01(p[2] if len(p) > 2 else 0), 0),
					_pid(p[3] if len(p) > 3 else None)])
		rez["a"] = a
	if isinstance(v.get("d"), list):
		d = []
		for p in v["d"][:MAX_PISTE_INTRARE]:
			if isinstance(p, (list, tuple)) and len(p) >= 1:
				d.append([_limba(p[0]), max(_01(p[1] if len(p) > 1 else 0), 0), _pid(p[2] if len(p) > 2 else None)])
		rez["d"] = d
	if isinstance(v.get("x"), list):
		x = []
		for p in v["x"][:MAX_PISTE_INTRARE]:
			if isinstance(p, (list, tuple)) and len(p) >= 2:
				pagina = _text(p[1], 4)
				x.append([_limba(p[0]), pagina if pagina.isalnum() else "", max(_01(p[2] if len(p) > 2 else 0), 0)])
		rez["x"] = x
	tt = _01(v.get("tt"))
	if tt != -1:
		rez["tt"] = tt
	return rez or None


def _ca(v):
	if not isinstance(v, (list, tuple)) or len(v) < 1:
		return None
	acces = _01(v[0])
	if acces == -1:
		return None
	perechi = []
	for p in (v[1] if len(v) > 1 and isinstance(v[1], (list, tuple)) else ())[:MAX_CA]:
		if isinstance(p, (list, tuple)) and len(p) >= 1:
			caid = _intreg(p[0], 0, 0xFFFF)
			if caid >= 0:
				perechi.append([caid, _pid(p[1] if len(p) > 1 else None)])
	return [acces, perechi]


def _ap_aplicatie(e):
	"""Un element al listei din ap: [cod, organisation_id, application_id, transport, adresa, lungime, nume], sau None.
	O adresa mai lunga de MAX_AP_URL se taie si lungimea ei adevarata ramane scrisa (nu se taie pe tacute)."""
	if not isinstance(e, (list, tuple)) or not e:
		return None
	camp = lambda i: e[i] if i < len(e) else None  # noqa: E731
	cod = _intreg(camp(0), 1, 2)
	adresa = _text(camp(4), 65535)
	lungime = _intreg(camp(5), 0, 65535)
	if len(adresa) > MAX_AP_URL:
		lungime = max(lungime, len(adresa))
		adresa = adresa[:MAX_AP_URL]
	rez = [cod, _intreg(camp(1), 0, 2 ** 32 - 1), _intreg(camp(2), 0, 0xFFFF), _enum(camp(3), ("h", "c", "hc")),
		adresa.strip(), lungime, _text(camp(6), MAX_AP_NUME).strip()]
	return rez if any(_stiut(x) for x in rez) else None


def _ap(v):
	"""Grupa ap: [aplicatii, autostart, transport, versiune AIT, adresa, nume(, lista)]; None fara numarul aplicatiilor.
	Lista (pozitia 6) ramane numai cand vine ca lista: o valoare cu 6 pozitii iese tot cu 6."""
	if not isinstance(v, (list, tuple)) or not v:
		return None
	n = _intreg(v[0], 0, MAX_AP_APLICATII)
	if n < 0:
		return None
	camp = lambda i: v[i] if i < len(v) else None  # noqa: E731
	rez = [n, _01(camp(1)), _enum(camp(2), ("h", "c", "hc")), _intreg(camp(3), 0, 31), _text(camp(4), MAX_AP_ADRESA),
		_text(camp(5), MAX_AP_NUME)]
	if isinstance(camp(6), (list, tuple)):
		rez.append([x for x in (_ap_aplicatie(e) for e in camp(6)[:MAX_AP_LISTA]) if x is not None])
	return rez


def curata_grupa(grupa, valoare):
	"""Valoarea unei grupe de canal sau de transponder -> forma sigura, sau None daca nu spune nimic."""
	if grupa in _POZITII:
		return _pozitional(grupa, valoare)
	if grupa == "pi":
		return _piste(valoare)
	if grupa == "ca":
		return _ca(valoare)
	if grupa == "ap":
		return _ap(valoare)
	if grupa == "hb":
		h = _01(valoare)
		return None if h == -1 else h
	if grupa in _TP_CAMPURI:
		if not isinstance(valoare, dict):
			return None
		rez = dict((c, _TP_CURATA[c](valoare.get(c))) for c in _TP_CAMPURI[grupa])
		return rez if any(_stiut(e) for e in rez.values()) else None
	return None


def _necunoscut(grupa, v):
	if v is None:
		return True
	if grupa == "hb":
		return v not in (0, 1)
	if grupa == "pi":
		return not v
	if grupa == "ca":
		return not isinstance(v, list) or not v or v[0] not in (0, 1)
	if isinstance(v, dict):
		return not any(_stiut(e) for e in v.values())
	if isinstance(v, list):
		return not any(_stiut(e) for e in v)
	return False


def _completeaza(grupa, castig, pierd):
	"""Campurile necunoscute ale valorii castigatoare, luate din cealalta (o valoare stiuta nu se pierde)."""
	if _necunoscut(grupa, pierd) or castig is None:
		return castig
	if grupa == "ap":
		# un AIT citit intreg: campurile altei citiri (alta versiune) nu sunt ale lui
		return castig
	if grupa == "pi":
		rez = dict(castig)
		for c in CAMPURI_PI:
			if c not in rez and c in pierd:
				rez[c] = pierd[c]
		return rez
	if grupa == "ca":
		if castig[0] == pierd[0] and not castig[1] and pierd[1]:
			return [castig[0], pierd[1]]
		return castig
	if isinstance(castig, dict):
		rez = dict(castig)
		for c, e in rez.items():
			if not _stiut(e) and _stiut(pierd.get(c)):
				rez[c] = pierd[c]
		return rez
	if isinstance(castig, list) and isinstance(pierd, list):
		if grupa == "vd" and len(castig) > 1 and len(pierd) > 1 and _stiut(castig[1]) and _stiut(pierd[1]) and \
				castig[1] != pierd[1]:
			# alta inaltime = alta imagine: latimea, cadrele, aspectul si codecul celeilalte nu sunt ale acesteia
			return castig
		rez = list(castig)
		for i, e in enumerate(rez):
			if not _stiut(e) and i < len(pierd) and _stiut(pierd[i]):
				rez[i] = pierd[i]
		return rez
	return castig


# ---------------------------------------------------------------- unirea (ordinea surselor)

def vf_tuplu(vf):
	"""[data, sursa] sau [data, sursa, fel] -> (data, sursa, fel), sau None daca nu e valid."""
	if not isinstance(vf, (list, tuple)) or len(vf) < 2:
		return None
	d, s = vf[0], vf[1]
	if isinstance(d, bool) or not isinstance(d, (int, float)) or not isinstance(s, str) or s not in SURSE:
		return None
	# NaN, Infinity (json le primeste) si numerele uriase: int() ar arunca sau time.localtime ar cadea mai tarziu;
	# NaN nu trece nicio comparatie, Infinity trece de margine, deci aceeasi conditie le refuza pe toate
	if not -_DATA_MAX_ABS <= d <= _DATA_MAX_ABS:
		return None
	fel = vf[2] if len(vf) > 2 else FEL_NORMAL
	if fel not in (FEL_NORMAL, FEL_APROXIMATIV, FEL_PORNIRE, FEL_IMPORT) or isinstance(fel, bool):
		fel = FEL_NORMAL
	return (int(d), s, fel)


def _vf_lista(vf):
	d, s, fel = vf
	return [d, s, fel] if fel else [d, s]


def treapta(vf, acum):
	"""(treapta, data stiuta sau None, exacta 1/0): 4 verificat cu data, 3 verificat fara data (c, sau data in afara
	ferestrei), 2 declarat de operator (o), 1 declarat (l), 0 nu se stie."""
	vf = vf_tuplu(vf)
	if not vf:
		return (0, None, 0)
	d, s, fel = vf
	data = d if data_valida(d, acum) else None
	if s in SURSE_CU_DATA:
		t = 4 if data is not None else 3
	elif s == "c":
		t, data = 3, None
	elif s == "o":
		t = 2
	else:
		t = 1
	return (t, data, 0 if fel == FEL_APROXIMATIV else 1)


def de_pornire(vf):
	"""True daca valoarea vine din baza de pornire (fel 2: aflata pe alt receptor, venita cu imaginea sau de pe stb)."""
	vf = vf_tuplu(vf)
	return bool(vf) and vf[2] == FEL_PORNIRE


def castiga_nou(vf_vechi, vf_nou, acum):
	"""True daca valoarea noua bate valoarea locala, dupa ordinea surselor. Intai: o valoare a receptorului (orice fel
	in afara de 2) bate mereu una din baza de pornire, in ambele sensuri; intre doua valori de pornire, ordinea
	obisnuita (cea mai noua data castiga; la aceeasi luna, cea unita acum)."""
	pv, pn = de_pornire(vf_vechi), de_pornire(vf_nou)
	if pv != pn:
		return pv
	tv, dv, ev = treapta(vf_vechi, acum)
	tn, dn, en = treapta(vf_nou, acum)
	if tn != tv:
		return tn > tv
	if dv is None or dn is None:
		return False
	if dn != dv:
		return dn > dv
	if pv:
		# doua baze de pornire din aceeasi luna: cea unita acum e cea mai noua (HdsBazaPornire.Unire le uneste in ordinea
		# versiunilor si nu mai uneste una mai veche decat cea mai noua unita)
		return True
	return en > ev


def uneste_grupa(vechi, nou, acum=None, grupa=None):
	"""Unirea unei grupe: vechi (local) si nou sunt (valoare, vf) sau None; intoarce (valoare, vf) castigatoare, cu
	campurile necunoscute completate din cealalta. Folosita de actualizeaza, uneste, mutari si de apelanti (index)."""
	if acum is None:
		acum = time.time()
	vv = vechi[0] if vechi else None
	nv = nou[0] if nou else None
	if _necunoscut(grupa, nv):
		return (vv, vf_tuplu(vechi[1])) if vechi and not _necunoscut(grupa, vv) else None
	if _necunoscut(grupa, vv):
		return (nv, vf_tuplu(nou[1]))
	if castiga_nou(vechi[1], nou[1], acum):
		return (_completeaza(grupa, nv, vv), vf_tuplu(nou[1]))
	return (_completeaza(grupa, vv, nv), vf_tuplu(vechi[1]))


# ---------------------------------------------------------------- randurile (grupe <-> dict)

def valoare_grupa(rec, grupa):
	"""Valoarea unei grupe dintr-un rand desfacut (canal sau transponder), sau None."""
	if not rec:
		return None
	if grupa == "pi":
		rez = dict((c, rec[c]) for c in CAMPURI_PI if c in rec)
		return rez or None
	if grupa in _TP_CAMPURI:
		rez = {}
		for c in _TP_CAMPURI[grupa]:
			rez[c] = rec.get(c, "" if c in ("pol", "poz", "sis", "fec", "mod", "ro", "pil", "crh", "crl", "gi", "tm",
				"hi", "retea") else -1)
		return rez if any(_stiut(e) for e in rez.values()) else None
	return rec.get(grupa)


def vf_grupa(rec, grupa):
	"""(data, sursa, fel) al unei grupe dintr-un rand desfacut, sau None."""
	if not rec:
		return None
	if grupa in _TP_CAMPURI:
		vf = vf_tuplu(rec.get(_TP_VF[grupa]))
		if vf is None and grupa == "dc":
			baza = vf_tuplu(rec.get("vf"))
			if baza is not None and valoare_grupa(rec, "dc") is not None:
				return (baza[0], "l", baza[2])
		return vf
	vfs = rec.get("vf")
	return vf_tuplu(vfs.get(grupa)) if isinstance(vfs, dict) else None


def _pune_grupa(rec, grupa, valoare, vf):
	if grupa in _TP_CAMPURI:
		for c in _TP_CAMPURI[grupa]:
			if c in _TP_OPTIONALE and not _stiut(valoare.get(c)):
				rec.pop(c, None)
			else:
				rec[c] = valoare.get(c)
		if grupa == "dc" and vf[1] == "l":
			rec.pop("vfo", None)
			if "vf" not in rec:
				rec["vf"] = _vf_lista(vf)
		else:
			rec[_TP_VF[grupa]] = _vf_lista(vf)
		return
	if grupa == "pi":
		for c in CAMPURI_PI:
			if c in valoare:
				rec[c] = valoare[c]
			else:
				rec.pop(c, None)
	else:
		rec[grupa] = valoare
	vfs = rec.get("vf")
	if not isinstance(vfs, dict):
		vfs = {}
		rec["vf"] = vfs
	vfs[grupa] = _vf_lista(vf)


def _scoate_grupa(rec, grupa):
	if grupa == "pi":
		for c in CAMPURI_PI:
			rec.pop(c, None)
	else:
		rec.pop(grupa, None)
	if isinstance(rec.get("vf"), dict):
		rec["vf"].pop(grupa, None)


_CHEI_CANAL = frozenset(_ORDINE_CANAL)
_CHEI_TP = frozenset(("tp", "vf", "vfo", "vfj") + tuple(_TP_CURATA))


def curata_rand(rec, tp=False, straine=True):
	"""Un rand desfacut cu fiecare grupa trecuta prin curata_grupa: o grupa ramane numai cu valoare si "vf" valide.
	straine=True pastreaza neschimbate cheile necunoscute (si intrarile necunoscute din "vf"); straine=False le scoate.
	Pe un rand scris de modul rezultatul e acelasi text (ordinea din "vf" se pastreaza), deci nu murdareste baza."""
	if not isinstance(rec, dict):
		return None
	cheie_rand = "tp" if tp else "k"
	rez = {cheie_rand: rec.get(cheie_rand)}
	for grupa in (GRUPE_TP if tp else GRUPE_CANAL):
		vf = vf_grupa(rec, grupa)
		if vf is None:
			continue
		val = curata_grupa(grupa, valoare_grupa(rec, grupa))
		if val is not None:
			_pune_grupa(rez, grupa, val, vf)
	vechi = rec.get("vf")
	if not tp and isinstance(vechi, dict):
		nou = rez.get("vf") if isinstance(rez.get("vf"), dict) else {}
		ordonat = {}
		for g in vechi:
			if g in nou:
				ordonat[g] = nou[g]
			elif straine and g not in GRUPE_CANAL:
				ordonat[g] = vechi[g]
		for g in nou:
			ordonat.setdefault(g, nou[g])
		if ordonat:
			rez["vf"] = ordonat
	if straine:
		cunoscute = _CHEI_TP if tp else _CHEI_CANAL
		for c, v in rec.items():
			if c not in cunoscute and c not in rez:
				rez[c] = v
	return rez


def _json(obj):
	return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def _ordonat_canal(rec):
	rez = {}
	for c in _ORDINE_CANAL:
		if c in rec:
			rez[c] = rec[c]
	for c, v in rec.items():
		if c not in rez:
			rez[c] = v
	return rez


def rand_canal(rec, jurnal=None):
	"""Randul-text al unui canal, sub RAND_SCRIS: taie intai pc, apoi pistele peste MAX_PISTE, apoi textele peste
	MAX_TEXT, apoi CAID-urile peste MAX_CA_TAIAT; in ultima instanta scoate grupele cele mai mari. O cheie necunoscuta
	care nu se poate scrie (prea adanca) pleaca, cu grupele curatate."""
	try:
		text = _json(_ordonat_canal(rec))
	except (ValueError, TypeError, RecursionError):
		rec = curata_rand(rec, straine=False)
		text = _json(_ordonat_canal(rec))
		if jurnal:
			jurnal("rand %s: chei necunoscute scoase (nu se pot scrie)" % rec.get("k"))
	if len(text) <= RAND_SCRIS:
		return text
	r = json.loads(text)
	pasi = []
	_scoate_grupa(r, "pc")
	pasi.append("pc")
	text = _json(_ordonat_canal(r))
	if len(text) > RAND_SCRIS:
		for c in ("a", "d", "x"):
			if isinstance(r.get(c), list):
				r[c] = r[c][:MAX_PISTE]
		pasi.append("piste")
		text = _json(_ordonat_canal(r))
	if len(text) > RAND_SCRIS:
		for c in ("a", "d", "x"):
			for p in r.get(c) or ():
				for i, e in enumerate(p):
					if isinstance(e, str):
						p[i] = e[:MAX_TEXT]
		if isinstance(r.get("sv"), list):
			r["sv"] = [e[:MAX_TEXT] if isinstance(e, str) else e for e in r["sv"]]
		pasi.append("texte")
		text = _json(_ordonat_canal(r))
	if len(text) > RAND_SCRIS and isinstance(r.get("ca"), list) and len(r["ca"]) > 1:
		r["ca"] = [r["ca"][0], r["ca"][1][:MAX_CA_TAIAT]]
		pasi.append("ca")
		text = _json(_ordonat_canal(r))
	ap = r.get("ap")
	if len(text) > RAND_SCRIS and isinstance(ap, list) and len(ap) > 6 and isinstance(ap[6], list) and ap[6]:
		# lista aplicatiilor, de la coada (cea de la ROSU e prima), inaintea grupelor intregi: pozitiile 0-5 raman
		while len(text) > RAND_SCRIS and ap[6]:
			ap[6].pop()
			text = _json(_ordonat_canal(r))
		pasi.append("ap-lista")
	for g in ("sg", "ap", "x", "d", "a", "ca", "br", "vd", "pmt"):
		if len(text) <= RAND_SCRIS:
			break
		_scoate_grupa(r, "pi" if g in ("a", "d", "x") else g)
		pasi.append(g)
		text = _json(_ordonat_canal(r))
	if jurnal:
		jurnal("rand %s taiat la %d o: %s" % (rec.get("k"), len(text), ", ".join(pasi)))
	return text


_ORDINE_TP = ("tp", "vf", "sis", "f", "pol", "sr", "fec", "mod", "ro", "pil", "inv", "bw", "crh", "crl", "gi", "tm",
	"hi", "mis", "plsm", "plsc", "plp", "t2mi", "vfj", "poz", "vfo", "retea", "nsv")


def rand_tp(rec):
	"""Randul-text al unui transponder (o cheie necunoscuta care nu se poate scrie pleaca, ca la rand_canal)."""
	ordine = _ORDINE_TP
	rez = {}
	for c in ordine:
		if c in rec:
			rez[c] = rec[c]
	for c, v in rec.items():
		if c not in rez:
			rez[c] = v
	try:
		return _json(rez)
	except (ValueError, TypeError, RecursionError):
		return rand_tp(curata_rand(rec, tp=True, straine=False))


_RE_VF = re.compile(r'\[(\d{9,10}),"[lcvpjmo]"')


def data_max_text(text, acum):
	"""Ca data_max, direct din randul-text (datele din "vf", "vfo", "vfj"), fara desfacere; -1 pentru un rand prea
	lung."""
	if len(text) > RAND_CITIT:
		return -1
	date = [int(x) for x in _RE_VF.findall(text)]
	date = [d for d in date if data_valida(d, acum)]
	return max(date) if date else 0


def data_max(rec, acum):
	"""Data cea mai noua a grupelor unui rand (pentru ordinea de scoatere); 0 daca nu are nicio data stiuta."""
	if not isinstance(rec, dict):
		return 0
	date = []
	if "tp" in rec:
		surse = [rec.get(c) for c in ("vf", "vfo", "vfj")]
	else:
		vfs = rec.get("vf")
		surse = list(vfs.values()) if isinstance(vfs, dict) else []
	for vf in surse:
		t = vf_tuplu(vf)
		if t and data_valida(t[0], acum):
			date.append(t[0])
	return max(date) if date else 0


# ---------------------------------------------------------------- transponderul din lamedb

_POL = ("H", "V", "L", "R")
_FEC_S = ("auto", "1/2", "2/3", "3/4", "5/6", "7/8", "8/9", "3/5", "4/5", "9/10")
_MOD_S = ("auto", "QPSK", "8PSK", "QAM16", "16APSK", "32APSK")
_RO_S = ("0.35", "0.25", "0.20", "auto")
_PIL = ("off", "on", "auto")
# Bandwidth_8MHz, _7MHz, _6MHz, _Auto (frontendparms.h); "auto" nu e o latime, deci -1 (nu se stie)
_BW_T = (8000, 7000, 6000, -1)
_FEC_T = ("1/2", "2/3", "3/4", "5/6", "7/8", "auto", "6/7", "8/9", "3/5", "4/5")
_MOD_T = ("QPSK", "QAM16", "QAM64", "auto", "QAM256")
_TM_T = ("2k", "8k", "auto", "4k", "1k", "16k", "32k")
_GI_T = ("1/32", "1/16", "1/8", "1/4", "auto", "1/128", "19/128", "19/256")
_HI_T = ("none", "1", "2", "4", "auto")
_MOD_C = ("auto", "QAM16", "QAM32", "QAM64", "QAM128", "QAM256")


def _din(tabel, i):
	return tabel[i] if 0 <= i < len(tabel) else ""


def _latime_banda(bw):
	if bw >= 1000:
		return bw // 1000
	return _BW_T[bw] if 0 <= bw < len(_BW_T) else -1


def tp_din_lamedb(cheie_lamedb, linie):
	"""Blocul unui transponder din lamedb (cheia "%08x:%04x:%04x" si randul "s ...", "t ..." sau "c ...", forma din
	lib/dvb/db.cpp si forma cu campuri in plus, scrisa de alte imagini) -> (cheie_tp, valori), sau None. Valorile sunt declarate
	(sursa "l"): f in kHz (la terestru Hz / 1000), sr in kSym/s, enumurile din frontendparms.h ca text."""
	k = cheie_tp(cheie_lamedb or "")
	if k is None or not isinstance(linie, str):
		return None
	s = linie.strip()
	if len(s) < 3 or s[1] != " " or s[0] not in "stc":
		return None
	try:
		n = [int(x) for x in s[2:].split(",")[0].split(":")]
	except ValueError:
		return None
	camp = lambda i: n[i] if i < len(n) else -1  # noqa: E731
	v = {}
	if s[0] == "s" and len(n) >= 6:
		s2 = camp(7) == 1
		v.update(f=camp(0), sr=camp(1) // 1000 if camp(1) > 0 else -1, pol=_din(_POL, camp(2)),
			fec="none" if camp(3) == 15 else _din(_FEC_S, camp(3)), poz=camp(4), inv=camp(5), sis="S2" if s2 else "S")
		if len(n) >= 11:
			v.update(mod=_din(_MOD_S, camp(8)), ro=_din(_RO_S, camp(9)), pil=_din(_PIL, camp(10)))
		else:
			v.update(mod="QPSK", ro="0.35", pil="")
	elif s[0] == "t" and len(n) >= 9:
		bw = camp(1)
		v.update(f=camp(0) // 1000 if camp(0) > 0 else -1, bw=_latime_banda(bw),
			crh=_din(_FEC_T, camp(2)), crl=_din(_FEC_T, camp(3)), mod=_din(_MOD_T, camp(4)), tm=_din(_TM_T, camp(5)),
			gi=_din(_GI_T, camp(6)), hi=_din(_HI_T, camp(7)), inv=camp(8), poz="T",
			sis="T2" if len(n) >= 11 and camp(10) == 1 else "T")
	elif s[0] == "c" and len(n) >= 5:
		v.update(f=camp(0), sr=camp(1) // 1000 if camp(1) > 0 else -1, inv=camp(2), mod=_din(_MOD_C, camp(3)),
			fec="none" if camp(4) == 15 else _din(_FEC_S, camp(4)), poz="C", sis="C")
	else:
		return None
	rez = {}
	for c, val in v.items():
		rez[c] = _TP_CURATA[c](val)
	return k, rez


# ---------------------------------------------------------------- CSV

COLOANE_CSV = (
	"cheie", "nume", "furnizor", "tip", "poz", "sis", "f", "pol", "sr", "fec", "mod", "ro", "pil", "inv", "bw", "crh",
	"crl", "gi", "tm", "hi", "mis", "plsm", "plsc", "plp", "t2mi", "retea", "nsv", "tp_data", "tp_sursa", "pmt", "pcr",
	"vpid", "vtip", "ttxpid", "aitpid", "acces", "caid", "ecm", "ca_data", "ca_sursa", "sunet", "subdvb", "subttx", "tt",
	"hbbtv", "latime", "inaltime", "progresiv", "cadre", "gama", "aspect", "codec", "vd_data", "vd_sursa", "br_total",
	"br_video", "br_audio", "br_data", "pc_profil", "pc_pixeli", "pc_esantionare_culoare", "pc_gama_culoare", "pc_gop",
	"pc_audio", "pc_esantionare", "pc_canale", "pc_format_audio", "pc_integritate", "pc_durata", "pc_data")


def _csv_val(v):
	if v is None or v == -1 or v == "" or isinstance(v, bool):
		return ""
	return str(v)


def _csv_data(vf):
	if not vf or not vf[0]:
		return ""
	try:
		return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(vf[0]))
	except (ValueError, OverflowError, OSError):
		# time_t de 32 de biti pe ARM, ani in afara lui localtime
		return ""


def rand_csv(rec, tp=None):
	"""Randul CSV al unui canal (coloanele COLOANE_CSV; gol = nu se stie). `tp` = randul transponderului, sau None."""
	r = rec or {}
	tp = tp or {}

	def pad(v, implicit):
		v = list(v) if isinstance(v, (list, tuple)) else []
		return (v + implicit[len(v):])[:len(implicit)]
	sv = pad(r.get("sv"), ["", -1, ""])
	pmt = pad(r.get("pmt"), [-1] * 6)
	ca = r.get("ca") if isinstance(r.get("ca"), list) and len(r["ca"]) == 2 else None
	vd = pad(r.get("vd"), [-1, -1, -1, -1, -1, "", ""])
	br = pad(r.get("br"), [-1] * 3)
	pc = pad(r.get("pc"), ["", "", "", "", -1, "", -1, "", "", [-1, -1], -1])
	vf_tp = vf_grupa(tp, "pr") if tp else None
	poz = tp.get("poz") if tp else None
	if poz in (None, ""):
		ktp = cheie_tp_din_cheie(r.get("k"))
		poz = poz_din_ns(int(ktp.split(":")[0], 16)) if ktp else ""
	integ = pc[9] if isinstance(pc[9], list) and len(pc[9]) == 2 and pc[9][0] >= 0 else None
	val = {
		"cheie": r.get("k", ""), "nume": sv[2], "furnizor": sv[0], "tip": sv[1], "poz": poz,
		"tp_data": _csv_data(vf_tp), "tp_sursa": vf_tp[1] if vf_tp else "",
		"pmt": pmt[0], "pcr": pmt[1], "vpid": pmt[2], "vtip": pmt[3], "ttxpid": pmt[4], "aitpid": pmt[5],
		"acces": ("criptat" if ca[0] == 1 else "fta") if ca else "",
		"caid": ";".join("%04x" % p[0] for p in ca[1]) if ca else "",
		"ecm": ";".join(_csv_val(p[1]) for p in ca[1]) if ca else "",
		"ca_data": _csv_data(vf_grupa(r, "ca")), "ca_sursa": (vf_grupa(r, "ca") or ("", ""))[1],
		"sunet": ";".join("%s:%s:%s" % (p[0], p[1], _csv_val(p[3] if len(p) > 3 else -1)) for p in r.get("a") or ()),
		"subdvb": ";".join("%s:%s:%s" % (p[0], p[1], _csv_val(p[2] if len(p) > 2 else -1)) for p in r.get("d") or ()),
		"subttx": ";".join("%s:%s:%s" % (p[0], p[1], p[2]) for p in r.get("x") or ()),
		"tt": r.get("tt", ""), "hbbtv": r.get("hb", ""),
		"latime": vd[0], "inaltime": vd[1], "progresiv": vd[2], "cadre": vd[3], "gama": vd[4], "aspect": vd[5],
		"codec": vd[6], "vd_data": _csv_data(vf_grupa(r, "vd")), "vd_sursa": (vf_grupa(r, "vd") or ("", ""))[1],
		"br_total": br[0], "br_video": br[1], "br_audio": br[2], "br_data": _csv_data(vf_grupa(r, "br")),
		"pc_profil": pc[0], "pc_pixeli": pc[1], "pc_esantionare_culoare": pc[2], "pc_gama_culoare": pc[3],
		"pc_gop": pc[4], "pc_audio": pc[5], "pc_esantionare": pc[6], "pc_canale": pc[7], "pc_format_audio": pc[8],
		"pc_integritate": "%d/%d" % tuple(integ) if integ else "", "pc_durata": pc[10],
		"pc_data": _csv_data(vf_grupa(r, "pc")),
	}
	for c in ("sis", "f", "pol", "sr", "fec", "mod", "ro", "pil", "inv", "bw", "crh", "crl", "gi", "tm", "hi", "mis",
			"plsm", "plsc", "plp", "t2mi", "retea", "nsv"):
		val[c] = tp.get(c, "")
	return [_csv_val(val[c]) for c in COLOANE_CSV]


# ---------------------------------------------------------------- sistemul de fisiere, contorul zilei, firul

class SistemFisiere(object):
	"""Operatiile pe fisiere ale bazei, intr-un singur loc (probele le inlocuiesc ca sa noteze ordinea)."""

	def deschide_citire(self, cale):
		return open(cale, "rb")

	def marime_deschis(self, f):
		return os.fstat(f.fileno()).st_size

	def deschide_import(self, cale):
		"""Un fisier venit din afara (stick, web): numai fisier obisnuit. O_NONBLOCK: un FIFO nu blocheaza deschiderea;
		O_NOFOLLOW: o legatura simbolica nu se urmeaza. Altceva decat un fisier obisnuit = OSError(EINVAL)."""
		fl = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
		fd = os.open(cale, fl)
		try:
			if not stat.S_ISREG(os.fstat(fd).st_mode):
				raise OSError(errno.EINVAL, "nu e un fisier obisnuit", cale)
			f = os.fdopen(fd, "rb")
		except BaseException:
			os.close(fd)
			raise
		return f

	def deschide_scriere(self, cale):
		return open(cale, "w", encoding="utf-8", newline="\n")

	def fsync(self, f):
		f.flush()
		os.fsync(f.fileno())

	def link(self, sursa, tinta):
		os.link(sursa, tinta)

	def replace(self, sursa, tinta):
		os.replace(sursa, tinta)

	def rename(self, sursa, tinta):
		os.rename(sursa, tinta)

	def remove(self, cale):
		os.remove(cale)

	def exista(self, cale):
		return os.path.exists(cale)

	def isdir(self, cale):
		return os.path.isdir(cale)

	def listdir(self, dosar):
		return os.listdir(dosar)

	def fsync_dosar(self, dosar):
		"""Numele nou ajunge pe flash abia cu fsync pe dosar; unde nu se poate (Windows), nimic."""
		try:
			fd = os.open(dosar or ".", os.O_RDONLY)
		except (OSError, AttributeError):
			return False
		try:
			os.fsync(fd)
			return True
		except OSError:
			return False
		finally:
			os.close(fd)


class ContorZi(object):
	"""Scrierile bazei in ziua curenta: "AAAALLZZ scrieri octeti" intr-un fisier din RAM (trece peste repornirea
	interfetei); fara fisier (cale None sau eroare), numai in memorie."""

	def __init__(self, cale=CALE_CONTOR):
		self.cale = cale
		self._zi, self._scrieri, self._octeti = "", 0, 0
		# adauga ruleaza pe firul de scriere, citeste pe firul interfetei
		self._lacat = threading.Lock()

	def _din_fisier(self):
		if not self.cale:
			return
		try:
			with open(self.cale, "r") as f:
				parti = f.read(64).split()
			if len(parti) == 3 and len(parti[0]) == 8 and parti[0].isdigit():
				self._zi, self._scrieri, self._octeti = parti[0], int(parti[1]), int(parti[2])
		except (IOError, OSError, ValueError):
			pass

	def _citeste(self, zi):
		if self._zi != zi:
			self._din_fisier()
		if self._zi != zi:
			return 0, 0
		return self._scrieri, self._octeti

	def citeste(self, zi):
		"""-> (scrieri, octeti) in ziua `zi`."""
		with self._lacat:
			return self._citeste(zi)

	def adauga(self, zi, octeti):
		with self._lacat:
			scrieri, total = self._citeste(zi)
			self._zi, self._scrieri, self._octeti = zi, scrieri + 1, total + octeti
			if self.cale:
				try:
					with open(self.cale, "w") as f:
						f.write("%s %d %d\n" % (self._zi, self._scrieri, self._octeti))
				except (IOError, OSError):
					pass
			return self._scrieri, self._octeti


def _fir_implicit(functie):
	t = threading.Thread(target=functie, name="HdsBazaCanale")
	t.daemon = True
	t.start()
	return t


class _Citire(object):
	"""Rezultatul citirii unui fisier: stare "lipseste", "necitit", "mare" sau "citit"."""

	def __init__(self, stare, detaliu=None):
		self.stare = stare
		self.detaliu = detaliu
		self.antet = None
		self.c = {}
		self.t = {}
		self.altele = []
		self.rele = []
		self.date = 0
		self.sfarsit = None
		self.dupa_sfarsit = False

	@property
	def intreg(self):
		return self.stare == "citit" and self.antet is not None and self.sfarsit is not None and \
			not self.dupa_sfarsit and self.sfarsit == self.date


def _antet_valid(linie):
	if not linie.startswith("{") or len(linie) > RAND_CITIT:
		return None
	a = _loads(linie)
	if not isinstance(a, dict) or a.get("fel") != FEL:
		return None
	v = a.get("v")
	if isinstance(v, bool) or not isinstance(v, int):
		return None
	return a


def _linii_marginite(f, stare):
	"""Randurile unui fisier binar deschis, ca text: cel mult MAX_CITIT octeti in total (peste: stare["mare"] = True si
	gata) si cel mult RAND_CITIT + 2 octeti tinuti pentru un rand; dintr-un rand mai lung iese numai inceputul (care
	se respinge la unire, fiind peste RAND_CITIT), iar restul se sare."""
	citit = 0
	sare = False
	while True:
		b = f.readline(RAND_CITIT + 2)
		if not b:
			return
		citit += len(b)
		if citit > MAX_CITIT:
			stare["mare"] = True
			return
		intreg = b.endswith(b"\n")
		if sare:
			sare = not intreg
			continue
		if not intreg and len(b) >= RAND_CITIT + 2:
			sare = True
		yield b.decode("utf-8", "replace")


def _numar_sfarsit(linie):
	o = _loads(linie) if len(linie) <= RAND_CITIT else None
	n = o.get("sfarsit") if isinstance(o, dict) else None
	return n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else -1


# ---------------------------------------------------------------- baza

class BazaCanale(object):
	"""O baza pe proces (vezi baza()). Toate metodele se cheama de pe firul interfetei; numai scrierea pe disc ruleaza
	in firul de scriere, sub un lacat, pe un instantaneu luat inainte."""

	def __init__(self, cale=CALE, ceas=None, fs=None, contor=None, porneste_fir=None, jurnal=None, imagine=""):
		self.cale = cale
		self._ceas = ceas or time.time
		self._fs = fs or SistemFisiere()
		self._contor = contor if contor is not None else ContorZi()
		self._porneste_fir = porneste_fir or _fir_implicit
		self._jurnal = jurnal or _jurnal_implicit
		self._imagine = imagine
		self._lacat = threading.Lock()
		self._fir = None
		self._nr = 0
		self._incarcat = False
		self._goleste()
		self._stare, self._motiv = SCRIE, None
		self._erori = 0
		self._reincercari = 0
		self._ultima_incercare = 0
		self._viu_bun = False
		self._oprire = False
		self._ultima_scriere = 0
		self._incarcare_ms = 0.0
		self._ultima_scriere_reusita = 0

	def _goleste(self):
		self._c = {}
		self._t = {}
		self._altele = []
		self._octeti = 0
		self._antet = {}
		self._v_fisier = VERSIUNE
		self._sarite = set()
		self._rele_la_citire = 0
		self._vazut = {}
		self._vizionari = {}
		self._confirmat = {}
		self._sg = {}
		self._asteapta = {}
		self._chemari = 0
		self._schimbate = {}
		self._rezerva = None
		self._lungi_notate = set()
		self.versiune = 0
		self.versiune_scrisa = 0
		self._versiune_toate = 0
		self._versiune_grupa = {}
		self._date_max = {}

	# ------------------------------------------------ stare

	def stare_scriere(self):
		"""-> (stare, motiv): SCRIE, NUMAI_CITIRE (cu motivul), OPRIT, AMANAT."""
		return self._stare, self._motiv

	def murdar(self):
		return self.versiune != self.versiune_scrisa

	def descriere_stare(self):
		"""Textul starii scrierii, pentru ecran si web."""
		texte = {
			SCRIE: _("Baza canalelor: se scrie normal"),
			OPRIT: _("Baza canalelor: scrieri oprite până la repornirea interfeței"),
			AMANAT: _("Baza canalelor: scrieri amânate după erori, până la standby"),
		}
		motive = {
			NECITIT: _("Baza canalelor: numai citire (fișierul nu s-a putut citi)"),
			DEGRADAT: _("Baza canalelor: numai citire (fișier stricat, nu s-a putut pune deoparte)"),
			V_MAI_MARE: _("Baza canalelor: numai citire (scrisă de o versiune mai nouă a imaginii)"),
			PREA_MARE: _("Baza canalelor: numai citire (fișier prea mare)"),
			DOSAR_LIPSA: _("Baza canalelor: numai citire (dosarul lipsește)"),
		}
		if self._stare == NUMAI_CITIRE:
			return motive.get(self._motiv, motive[NECITIT])
		return texte.get(self._stare, texte[SCRIE])

	def _numai_citire(self, motiv, detaliu=""):
		"""Starea OPRIT nu se inlocuieste (nici din firul de scriere): numai repornirea interfetei iese din ea."""
		self._jurnal("numai citire: %s %s" % (motiv, detaliu))
		if self._stare != OPRIT:
			self._stare, self._motiv = NUMAI_CITIRE, motiv

	def opreste_scrierile(self):
		"""Nicio scriere pana la repornirea interfetei (inainte de resetare, flash, restaurare). Asteapta scrierea din
		fundal cel mult ASTEPTARE_FIR_S."""
		self._stare, self._motiv = OPRIT, None
		fir = self._fir
		if fir is not None and fir.is_alive():
			fir.join(ASTEPTARE_FIR_S)
		self._jurnal("scrieri oprite")

	# ------------------------------------------------ citirea

	def incarca(self):
		"""Citirea fisierului (o data; si singura la prima cerere): numai impartirea in randuri si cheile, fara desfacere."""
		if self._incarcat:
			return self._stare
		self._incarcat = True
		self._ultima_scriere = self._ceas()
		inceput = time.time()
		try:
			self._incarca_disc()
		except Exception as e:
			# MemoryError, RecursionError sau alta cadere neasteptata: memoria goala nu are voie sa ajunga peste
			# fisier, deci numai-citire, ca la o citire nereusita (se reincearca)
			self._goleste()
			self._numai_citire(NECITIT, "%s: %s" % (type(e).__name__, e))
			self._ultima_incercare = self._ceas()
		self._incarcare_ms = (time.time() - inceput) * 1000.0
		self._jurnal("baza: %d randuri in %.0f ms" % (len(self._c) + len(self._t) + len(self._altele),
			self._incarcare_ms))
		return self._stare

	def _asigura(self):
		if not self._incarcat:
			self.incarca()

	def _dosar(self):
		return os.path.dirname(self.cale) or "."

	def _citeste(self, cale):
		fs = self._fs
		try:
			f = fs.deschide_citire(cale)
		except (IOError, OSError) as e:
			if getattr(e, "errno", None) == errno.ENOENT:
				return _Citire("lipseste")
			return _Citire("necitit", str(e))
		r = _Citire("citit")
		try:
			try:
				marime = fs.marime_deschis(f)
			except (IOError, OSError, ValueError, AttributeError):
				marime = 0
			if marime > MAX_CITIT:
				return _Citire("mare", marime)
			prima = True
			citit = 0
			for b in f:
				citit += len(b)
				if citit > MAX_CITIT:
					return _Citire("mare", citit)
				linie = b.decode("utf-8", "replace").rstrip("\r\n")
				if prima:
					prima = False
					r.antet = _antet_valid(linie)
					if r.antet is not None:
						continue
				if not linie.strip():
					continue
				if linie.startswith('{"sfarsit":'):
					r.sfarsit = _numar_sfarsit(linie)
					continue
				if r.sfarsit is not None:
					r.dupa_sfarsit = True
				r.date += 1
				m = _RE_CHEIE_RAND.match(linie)
				if m:
					(r.c if m.group(1) == "k" else r.t)[m.group(2)] = linie
					continue
				if len(linie) > RAND_CITIT:
					# nedesfacut (json.loads pe un rand de MiB ar cere de zeci de ori marimea lui); pastrat la scriere
					r.altele.append(linie)
					continue
				o = _loads(linie)
				if isinstance(o, dict) and isinstance(o.get("k"), str) and o["k"]:
					r.c[o["k"]] = linie
				elif isinstance(o, dict) and isinstance(o.get("tp"), str) and o["tp"]:
					r.t[o["tp"]] = linie
				elif isinstance(o, dict):
					r.altele.append(linie)
				else:
					r.rele.append(linie)
		except (IOError, OSError) as e:
			return _Citire("necitit", str(e))
		finally:
			f.close()
		return r

	def _foloseste(self, r, din):
		"""Randurile citite devin memoria bazei; randurile care nu se desfac trec neatinse printre "altele"."""
		if r.rele:
			r.altele.extend(r.rele)
			r.rele = []
		self._c, self._t = r.c, r.t
		self._altele = list(r.altele)
		self._antet = dict(r.antet or {})
		self._rezerva = None
		v = self._antet.get("v", VERSIUNE)
		self._v_fisier = v if isinstance(v, int) and not isinstance(v, bool) else VERSIUNE
		self._octeti = sum(len(x) + 1 for x in self._c.values()) + sum(len(x) + 1 for x in self._t.values()) + \
			sum(len(x) + 1 for x in self._altele)
		if din:
			self._jurnal("folosesc %s" % din)

	def _pastreaza_bune(self, r):
		"""Fisier taiat: raman numai randurile care se desfac, sub RAND_CITIT (un rand lung nu se poate verifica fara
		desfacere, iar ultimul rand poate fi unul taiat); restul se numara."""
		rele = len(r.rele)
		for harta in (r.c, r.t):
			for k in list(harta):
				if len(harta[k]) > RAND_CITIT or not isinstance(_loads(harta[k]), dict):
					del harta[k]
					rele += 1
		altele = []
		for linie in r.altele:
			if len(linie) <= RAND_CITIT and isinstance(_loads(linie), dict):
				altele.append(linie)
			else:
				rele += 1
		r.altele = altele
		r.rele = []
		self._rele_la_citire += rele

	def _incarca_disc(self):
		fs = self._fs
		if not fs.isdir(self._dosar()):
			self._numai_citire(DOSAR_LIPSA, self._dosar())
			return
		bak = self.cale + ".bak"
		r = self._citeste(self.cale)
		if r.stare == "lipseste":
			rb = self._citeste(bak)
			if rb.intreg:
				self._foloseste(rb, ".bak (fisierul viu lipseste)")
				self._verifica_versiunea()
			self._viu_bun = False
		elif r.stare == "necitit":
			self._numai_citire(NECITIT, r.detaliu or "")
			self._ultima_incercare = self._ceas()
			return
		elif r.intreg:
			self._foloseste(r, None)
			self._viu_bun = True
			self._verifica_versiunea()
		else:
			self._jurnal("%s %s" % (self.cale, "prea mare" if r.stare == "mare" else "taiat sau fara antet"))
			rb = self._citeste(bak)
			if rb.intreg:
				self._foloseste(rb, ".bak")
				self._viu_bun = False
				if not self._pune_deoparte(self.cale):
					self._numai_citire(DEGRADAT, "nu pot pune deoparte %s" % self.cale)
					return
				self._verifica_versiunea()
			elif r.stare == "mare":
				self._numai_citire(PREA_MARE, str(r.detaliu))
				return
			else:
				self._pastreaza_bune(r)
				self._foloseste(r, "randurile bune din fisierul taiat")
				# fara .bak bun: migrarea din fisierele vechi si baza de pornire se refac (unirea completeaza numai ce
				# lipseste, valorile mai noi raman)
				self._antet.pop("migrat", None)
				for x in CHEI_ANTET_PORNIRE:
					self._antet.pop(x, None)
				self._viu_bun = False
				if not self._pune_deoparte(self.cale):
					self._numai_citire(DEGRADAT, "nu pot pune deoparte %s" % self.cale)
					return
				self._verifica_versiunea()
				if self._stare == SCRIE:
					self.versiune += 1
					self._versiune_toate = self.versiune
		if self._stare == SCRIE:
			self._curata_temporare()

	def _verifica_versiunea(self):
		if self._v_fisier > VERSIUNE:
			self._numai_citire(V_MAI_MARE, "v=%d" % self._v_fisier)

	def _curata_temporare(self):
		baza = os.path.basename(self.cale)
		try:
			nume = self._fs.listdir(self._dosar())
		except (IOError, OSError):
			return
		for n in nume:
			if n.startswith(baza + ".nou.") or n == baza + ".bak.nou":
				try:
					self._fs.remove(os.path.join(self._dosar(), n))
				except (IOError, OSError):
					pass

	def _pune_deoparte(self, cale):
		"""Fisierul rau devine si .stricat-AAAALLZZ (raman cel mult MAX_STRICATE), fara nicio scriere: intai o legatura
		tare, deci fisierul viu ramane pe loc pana il inlocuieste prima scriere (o cadere de curent inainte de ea gaseste
		la pornire tot fisierul rau, din care se iau din nou randurile bune); numai daca legatura nu se poate, o
		redenumire."""
		fs = self._fs
		nume = "%s.stricat-%s" % (cale, _zi(self._ceas()))
		tinta, n = nume, 1
		while fs.exista(tinta):
			n += 1
			tinta = "%s-%d" % (nume, n)
		try:
			fs.link(cale, tinta)
		except (IOError, OSError, AttributeError, NotImplementedError) as e:
			self._jurnal("fara legatura pentru %s: %s; redenumesc" % (cale, e))
			try:
				fs.rename(cale, tinta)
			except (IOError, OSError) as e2:
				self._jurnal("nu pot redenumi %s: %s" % (cale, e2))
				return False
		self._jurnal("%s pus deoparte ca %s" % (cale, os.path.basename(tinta)))
		baza = os.path.basename(cale) + ".stricat-"

		def ordine(x):
			parti = x[len(baza):].split("-")
			return (parti[0], int(parti[1]) if len(parti) > 1 and parti[1].isdigit() else 1)
		try:
			stricate = sorted((x for x in fs.listdir(os.path.dirname(cale) or ".") if x.startswith(baza)), key=ordine)
		except (IOError, OSError):
			stricate = []
		for x in stricate[:-MAX_STRICATE] if len(stricate) > MAX_STRICATE else ():
			try:
				fs.remove(os.path.join(os.path.dirname(cale) or ".", x))
			except (IOError, OSError):
				pass
		return True

	def reincearca(self, acum=None):
		"""Dupa o citire nereusita: o noua citire, cel mult REINCERCARI_MAX, la cel putin REINCERCARE_S. Ce s-a aflat
		intre timp in memorie se uneste peste fisier. -> True daca baza a iesit din numai-citire."""
		acum = self._ceas() if acum is None else acum
		if self._stare != NUMAI_CITIRE or self._motiv not in (NECITIT, DOSAR_LIPSA):
			return False
		if self._reincercari >= REINCERCARI_MAX or acum - self._ultima_incercare < REINCERCARE_S:
			return False
		self._reincercari += 1
		self._ultima_incercare = acum
		return self._citeste_din_nou()

	def _citeste_din_nou(self):
		"""O citire noua din numai-citire (necitit, dosar lipsa), cu memoria unita peste ea. Daca citirea pica iar (sau
		arunca), memoria si starea raman exact cum erau."""
		inainte = dict(self.__dict__)
		vechi_c, vechi_t, v0, vs0, schimbate0 = self._c, self._t, self.versiune, self.versiune_scrisa, self._schimbate
		pastrate = (self._vazut, self._vizionari, self._confirmat, self._sg)
		try:
			self._goleste()
			self._vazut, self._vizionari, self._confirmat, self._sg = pastrate
			self._stare, self._motiv = SCRIE, None
			self._incarca_disc()
			if self._stare == NUMAI_CITIRE and self._motiv in (NECITIT, DOSAR_LIPSA) and not self._c and not self._t:
				self.__dict__.clear()
				self.__dict__.update(inainte)
				return False
			degradat = self.versiune != 0
			self.versiune = v0 + 1
			self._versiune_toate = self.versiune
			self.versiune_scrisa = vs0 if degradat else self.versiune
			self._schimbate = dict(schimbate0)
			for k in self._c:
				self._schimbate[k] = self.versiune
			for k, text in vechi_c.items():
				self._uneste_text(k, text, False)
			for k, text in vechi_t.items():
				self._uneste_text(k, text, True)
		except Exception as e:
			self.__dict__.clear()
			self.__dict__.update(inainte)
			self._jurnal("citirea din nou a cazut: %s: %s" % (type(e).__name__, e))
			return False
		return self._stare != NUMAI_CITIRE

	def porneste_din_nou(self):
		"""Din numai-citire, la cererea omului. Dupa o citire nereusita (necitit, dosar lipsa) intai o citire noua, fara
		asteptare; numai daca pica iar (sau motivul e altul: v mai mare, prea mare, degradat) fisierul viu se pune
		deoparte ca .stricat, iar baza scrie din nou din memorie. -> True daca a iesit din numai-citire."""
		self._asigura()
		if self._stare != NUMAI_CITIRE:
			return self._stare == SCRIE
		if self._motiv in (NECITIT, DOSAR_LIPSA):
			if self._citeste_din_nou():
				return True
			if self._stare != NUMAI_CITIRE:
				return self._stare == SCRIE
		if not self._fs.isdir(self._dosar()):
			return False
		if self._fs.exista(self.cale) and not self._pune_deoparte(self.cale):
			return False
		self._stare, self._motiv = SCRIE, None
		self._v_fisier = VERSIUNE
		self._viu_bun = False
		self.versiune += 1
		self._versiune_toate = self.versiune
		return True

	# ------------------------------------------------ desfacerea

	def _desface(self, k, text, tot=True, tp=False):
		"""Randul-text -> dict, sau None (rand peste RAND_CITIT, rand care nu se desface, alta cheie: numarat ca sarit).
		tot=True (pentru o schimbare): grupele trec prin curata_rand, deci o valoare ciudata de pe disc nu ajunge la unire;
		tot=False (pentru citire): randul asa cum e, fara cheile necunoscute cand fisierul e de la o versiune mai noua."""
		if text is None:
			return None
		if len(text) > RAND_CITIT:
			self._sarite.add(k)
			return None
		rec = _loads(text)
		if not isinstance(rec, dict) or rec.get("tp" if tp else "k") != k:
			self._sarite.add(k)
			return None
		if tot:
			return curata_rand(rec, tp)
		if self._v_fisier > VERSIUNE:
			stiute = _CHEI_TP if tp else _CHEI_CANAL
			rec = dict((c, v) for c, v in rec.items() if c in stiute)
		return rec

	def _lung(self, harta, k):
		"""Randul lui k e peste RAND_CITIT: sarit la citire si pastrat neatins, deci nicio valoare noua nu-l inlocuieste
		(o linie in jurnal, o data pe cheie)."""
		text = harta.get(k)
		if text is None or len(text) <= RAND_CITIT:
			return False
		if k not in self._lungi_notate:
			self._lungi_notate.add(k)
			self._jurnal("rand %s de %d o, peste %d: pastrat neatins, valorile noi pentru el nu se scriu" % (k,
				len(text), RAND_CITIT))
		return True

	def cauta(self, ref_sau_cheie, rezerva=False):
		"""Randul desfacut al canalului (o copie), sau None.
		rezerva=True: in baza se cauta si alt rand cu aceeasi cheie de rezerva (onid:tsid:sid@poz); daca e unul singur
		(in afara lui k), e randul vechi al acestui canal, ramas sub alta cheie dupa o rescanare pe alta frecventa, si
		se uneste pe loc sub k (grupa mai noua castiga, ca la uneste_grupa), iar randul vechi pleaca; pe disc la
		urmatoarea scriere. Se face si cand k are deja rand. Contractul apelantului: rezerva=True numai cand lamedb are
		un singur canal pe cheia de rezerva a lui k (numarat de apelant pe tot lamedb-ul); altfel unirea ar strica randul
		unui canal adevarat. Harta cheilor de rezerva se face la primul apel cu rezerva=True, apoi se tine la zi."""
		k = cheie(ref_sau_cheie)
		if k is None:
			return None
		self._asigura()
		if rezerva:
			self._uneste_rezerva(k)
		text = self._c.get(k)
		return self._desface(k, text, tot=False) if text is not None else None

	def _uneste_rezerva(self, k):
		vechi = self._candidat_rezerva(k)
		if vechi is None or self._lung(self._c, vechi) or self._lung(self._c, k):
			return False
		strain = self._desface(vechi, self._c.get(vechi))
		if strain is None:
			return False
		strain["k"] = k
		local = self._desface(k, self._c.get(k)) if k in self._c else None
		rec, _schimbat = self._uneste_rec(local, strain, self._ceas())
		self._sterge(self._c, vechi)
		self._seteaza(self._c, k, rand_canal(rec, self._jurnal))
		self._schimba(k)
		self._schimbate[vechi] = self.versiune
		self._jurnal("cheie de rezerva: %s mutat la %s (unit)" % (vechi, k))
		return True

	def _harta_rezerva(self):
		if self._rezerva is None:
			self._rezerva = {}
			for x in self._c:
				self._rezerva_adauga(x)
		return self._rezerva

	def _rezerva_adauga(self, x):
		"""Harta: cheie de rezerva -> cheia canalului (text) sau, pentru mai multe canale, un tuplu de chei."""
		r = cheie_rezerva(x)
		if r is None:
			return
		e = self._rezerva.get(r)
		if e is None:
			self._rezerva[r] = x
		elif isinstance(e, str):
			if e != x:
				self._rezerva[r] = (e, x)
		elif x not in e:
			self._rezerva[r] = e + (x,)

	def _rezerva_scoate(self, x):
		r = cheie_rezerva(x)
		e = self._rezerva.get(r) if r is not None else None
		if e is None:
			return
		rest = tuple(y for y in ((e,) if isinstance(e, str) else e) if y != x)
		if not rest:
			del self._rezerva[r]
		else:
			self._rezerva[r] = rest[0] if len(rest) == 1 else rest

	def _candidat_rezerva(self, k):
		"""Singurul alt rand cu aceeasi cheie de rezerva ca k, sau None (niciunul sau mai multe: nu se ghiceste)."""
		r = cheie_rezerva(k)
		if r is None:
			return None
		e = self._harta_rezerva().get(r)
		if e is None:
			return None
		alte = [x for x in ((e,) if isinstance(e, str) else e) if x != k and x in self._c]
		return alte[0] if len(alte) == 1 else None

	def candidat_rezerva(self, ref_sau_cheie):
		"""Cheia singurului alt rand din baza cu aceeasi cheie de rezerva ca acest canal, sau None (niciunul sau mai
		multe). Nu schimba nimic; harta cheilor de rezerva se face la primul apel (ca la cauta cu rezerva=True)."""
		k = cheie(ref_sau_cheie)
		if k is None:
			return None
		self._asigura()
		return self._candidat_rezerva(k)

	def contine(self, ref_sau_cheie):
		"""Are canalul rand in baza? Fara desfacere."""
		k = cheie(ref_sau_cheie)
		if k is None:
			return False
		self._asigura()
		return k in self._c

	def chei_cu(self, campuri):
		"""Cheile canalelor al caror rand-text are unul din campurile date (de ex. ("vd",) sau ("a", "d", "x", "tt")),
		fara desfacere. E o alegere larga: "vf" are aceleasi nume de grupe, deci apelantul desface si verifica."""
		self._asigura()
		semne = tuple('"%s":' % c for c in campuri)
		return [k for k, text in list(self._c.items()) if any(s in text for s in semne)]

	def seteaza_imagine(self, imagine):
		"""Versiunea imaginii scrisa in antet la urmatoarea scriere."""
		if isinstance(imagine, str) and imagine:
			self._imagine = imagine[:32]

	def data_max_grupe(self, grupe):
		"""Data cea mai noua (secunde; 0 daca nu e niciuna valida) din "vf" al grupelor date, pe toate canalele, cautata in
		randurile-text fara desfacere; tinuta pana la urmatoarea schimbare a acelor grupe (versiune_grupe)."""
		self._asigura()
		grupe = tuple(grupe)
		v = self.versiune_grupe(grupe)
		tinut = self._date_max.get(grupe)
		if tinut is not None and tinut[0] == v:
			return tinut[1]
		acum = self._ceas()
		re_grupa = re.compile(r'"(?:%s)":\[(\d{1,16})[,\]]' % "|".join(re.escape(g) for g in grupe))
		m = 0
		for text in list(self._c.values()):
			vf = _RE_OBIECT_VF.search(text)
			for d in re_grupa.findall(vf.group(1)) if vf else ():
				d = int(d)
				if d > m and data_valida(d, acum):
					m = d
		self._date_max[grupe] = (v, m)
		return m

	def transponder(self, ref_sau_cheie_tp):
		"""Randul desfacut al transponderului (cheia "ns:tsid:onid" sau cheia unui canal), sau None."""
		k = cheie_tp(ref_sau_cheie_tp) if isinstance(ref_sau_cheie_tp, str) and \
			ref_sau_cheie_tp.count(":") == 2 else cheie_tp_din_cheie(cheie(ref_sau_cheie_tp))
		if k is None:
			return None
		self._asigura()
		return self._desface(k, self._t.get(k), tot=False, tp=True)

	def stare(self, rec, grupa):
		"""(data, sursa, fel) al unei grupe, cu data cea mai noua dintre "vf" si confirmarea din memorie; sau None."""
		vf = vf_grupa(rec, grupa)
		if vf is None:
			return None
		k = (rec or {}).get("k")
		conf = self._confirmat.get(k, {}).get(grupa) if k else None
		if conf and conf[0] > vf[0]:
			return conf
		return vf

	def toate(self):
		"""Iterator (cheie, rand desfacut) pe canale, rand cu rand (fara lista intermediara de randuri desfacute)."""
		self._asigura()
		for k in list(self._c):
			rec = self._desface(k, self._c.get(k), tot=False)
			if rec is not None:
				yield k, rec

	def toate_tp(self):
		self._asigura()
		for k in list(self._t):
			rec = self._desface(k, self._t.get(k), tot=False, tp=True)
			if rec is not None:
				yield k, rec

	def schimbate_din(self, versiune):
		"""Cheile canalelor schimbate dupa `versiune` (pentru refacerea indexului pe bucati)."""
		return set(k for k, v in self._schimbate.items() if v > versiune)

	def vazut(self, ref_sau_cheie, cand=None):
		"""Ultima vizionare, numai in memorie (nu murdareste baza)."""
		k = cheie(ref_sau_cheie)
		if k:
			self._vazut[k] = self._ceas() if cand is None else cand
			self._vizionari[k] = self._vizionari.get(k, 0) + 1

	def vazut_la(self, ref_sau_cheie):
		return self._vazut.get(cheie(ref_sau_cheie))

	def confirma(self, ref_sau_cheie, grupa, cand=None, sursa="v", fel=FEL_NORMAL):
		"""Valoarea vie e egala cu cea din baza: data noua numai in memorie; intra in "vf" la urmatoarea scriere, cu
		felul ei (o data aproximativa, de ex. a unui fisier de dinainte, ramane aproximativa)."""
		k = cheie(ref_sau_cheie)
		if not k or sursa not in SURSE_CU_DATA:
			return
		cand = self._ceas() if cand is None else cand
		if not data_valida(cand, self._ceas()):
			return
		if fel not in (FEL_NORMAL, FEL_APROXIMATIV, FEL_PORNIRE, FEL_IMPORT) or isinstance(fel, bool):
			fel = FEL_NORMAL
		c = self._confirmat.setdefault(k, {})
		nou = (int(cand), sursa, fel)
		vechi = c.get(grupa)
		# data mai noua castiga; la aceeasi data, cea exacta bate cea aproximativa
		if vechi is None or (nou[0], nou[2] != FEL_APROXIMATIV) > (vechi[0], vechi[2] != FEL_APROXIMATIV):
			c[grupa] = nou

	# ------------------------------------------------ schimbarea

	def _schimba(self, k=None, grupe=None):
		"""O schimbare de continut: versiunea creste. `grupe`: grupele de canal atinse (pentru versiune_grupe); None =
		oricare (randuri citite, unite, mutate, taiate sau scoase); () = niciuna (antetul, transponderele)."""
		self.versiune += 1
		if k is not None:
			self._schimbate[k] = self.versiune
		if grupe is None:
			self._versiune_toate = self.versiune
		else:
			for g in grupe:
				self._versiune_grupa[g] = self.versiune

	def versiune_grupe(self, grupe):
		"""Versiunea bazei la ultima schimbare care putea atinge una din grupele date: pentru privirile adaptoarelor si
		pentru indexul cautarii (o schimbare a accesului nu reface pistele tuturor canalelor). Nu scade si nu trece de
		versiune."""
		v = self._versiune_toate
		for g in grupe:
			v = max(v, self._versiune_grupa.get(g, 0))
		return v

	def _seteaza(self, harta, k, text):
		vechi = harta.get(k)
		if vechi is not None:
			self._octeti -= len(vechi) + 1
		elif harta is self._c and self._rezerva is not None:
			self._rezerva_adauga(k)
		harta[k] = text
		self._octeti += len(text) + 1
		self._sarite.discard(k)

	def _sterge(self, harta, k):
		text = harta.pop(k, None)
		if text is not None:
			self._octeti -= len(text) + 1
			if harta is self._c:
				if self._rezerva is not None:
					self._rezerva_scoate(k)
				self._vazut.pop(k, None)
				self._confirmat.pop(k, None)
				self._sg.pop(k, None)
		return text is not None

	def actualizeaza(self, ref_sau_cheie, grupe, sursa, cand=None, fel=FEL_NORMAL):
		"""Valorile aflate pentru un canal: {grupa: valoare}. Declaratul (sursa "l") se primeste numai pentru sv; "c" si
		"o" nu se scriu pe canal. `fel` = FEL_APROXIMATIV pentru o data aproximativa (de ex. data unui fisier).
		Un rand care nu se desface (JSON rau, sub RAND_CITIT) e inlocuit de valorile noi; un rand peste RAND_CITIT ramane
		neatins si valorile noi pentru el nu se scriu. Semnalul (sg) nu murdareste niciodata baza.
		-> True daca s-a schimbat continutul (baza murdara)."""
		k = cheie(ref_sau_cheie)
		if k is None or sursa not in SURSE or sursa in ("c", "o") or not isinstance(grupe, dict):
			return False
		if fel not in (FEL_NORMAL, FEL_APROXIMATIV, FEL_PORNIRE, FEL_IMPORT) or isinstance(fel, bool):
			return False
		self._asigura()
		if self._lung(self._c, k):
			return False
		acum = self._ceas()
		cand = acum if cand is None else cand
		vf_nou = (_data_stocata(cand, acum), sursa, fel)
		text = self._c.get(k)
		rec = self._desface(k, text) if text is not None else None
		if rec is None:
			rec = {"k": k}
		schimbate = []
		for grupa, valoare in grupe.items():
			if grupa not in GRUPE_CANAL or (sursa == "l" and grupa != "sv"):
				continue
			val = curata_grupa(grupa, valoare)
			if val is None:
				continue
			if grupa == "sg":
				self._sg_nou(k, rec, val, vf_nou)
				continue
			if self._grupa_noua(k, rec, grupa, val, vf_nou, acum):
				schimbate.append(grupa)
		if schimbate:
			taiat = []

			def jurnal(t):
				taiat.append(t)
				self._jurnal(t)
			nou = rand_canal(rec, jurnal)
			if nou == text:
				return False
			self._seteaza(self._c, k, nou)
			# un rand taiat sub RAND_SCRIS poate pierde si alte grupe decat cele schimbate
			self._schimba(k, None if taiat else schimbate)
		return bool(schimbate)

	def _vechime_depasita(self, vf, acum):
		t = treapta(vf, acum)
		return t[1] is None or acum - t[1] > PROASPAT_S

	def _merita_scris(self, vechi_vf, nou_vf, acum):
		"""Acelasi continut, alta data: se scrie numai cand se schimba treapta sau exactitatea datei, sau cand grupa
		verificata de pe disc e mai veche de PROASPAT_S; altfel e o confirmare (numai in memorie)."""
		if nou_vf == vechi_vf:
			return False
		# o valoare de pornire confirmata de receptor devine a lui: se scrie (o singura data pe grupa), ca o baza de
		# pornire mai noua sa nu o mai poata inlocui
		if de_pornire(vechi_vf) != de_pornire(nou_vf):
			return True
		t_vechi, t_nou = treapta(vechi_vf, acum), treapta(nou_vf, acum)
		if (t_vechi[0], t_vechi[2]) != (t_nou[0], t_nou[2]):
			return True
		return nou_vf[1] in SURSE_CU_DATA and self._vechime_depasita(vechi_vf, acum)

	def _grupa_noua(self, k, rec, grupa, val, vf_nou, acum):
		vechi_val = valoare_grupa(rec, grupa)
		vechi_vf = vf_grupa(rec, grupa)
		if _necunoscut(grupa, vechi_val) or vechi_vf is None:
			_pune_grupa(rec, grupa, val, vf_nou)
			self._asteapta.pop(k, None)
			return True
		rez_val, rez_vf = uneste_grupa((vechi_val, vechi_vf), (val, vf_nou), acum, grupa)
		if rez_val == vechi_val:
			if rez_vf == vechi_vf:
				if grupa == "vd":
					self._asteapta.pop(k, None)
				if vf_nou[1] in SURSE_CU_DATA and treapta(vf_nou, acum)[1] is not None and \
						_completeaza(grupa, val, vechi_val) == vechi_val:
					self.confirma(k, grupa, vf_nou[0], vf_nou[1], vf_nou[2])
				return False
			if self._merita_scris(vechi_vf, rez_vf, acum):
				_pune_grupa(rec, grupa, rez_val, rez_vf)
				if grupa == "vd":
					self._asteapta.pop(k, None)
				return True
			if grupa == "vd":
				self._asteapta.pop(k, None)
			self.confirma(k, grupa, rez_vf[0], rez_vf[1], rez_vf[2])
			return False
		# cele doua vizionari sunt ale culegerii la vizionare; o valoare cu alt fel de data (migrarea din fisierele de
		# dinainte, o singura citire) nu are a doua vizionare, deci s-ar pierde. Peste o valoare din baza de pornire
		# (aflata pe alt receptor) prima vizionare ajunge.
		if grupa == "vd" and rez_vf == vf_tuplu(vf_nou) and vf_nou[2] == FEL_NORMAL and \
				not de_pornire(vechi_vf) and self._numai_volatile(vechi_val, rez_val):
			if not self._a_doua_vizionare(k, rez_val):
				return False
		elif grupa == "vd":
			self._asteapta.pop(k, None)
		_pune_grupa(rec, grupa, rez_val, rez_vf)
		return True

	@staticmethod
	def _numai_volatile(vechi, nou):
		"""Diferentele sunt numai in campurile VD_VOLATILE (latime, progresiv, cadre, gama, aspect), iar valoarea veche a
		acelor campuri era stiuta."""
		dif = [i for i in range(len(nou)) if i >= len(vechi) or vechi[i] != nou[i]]
		return bool(dif) and all(i in VD_VOLATILE and i < len(vechi) and _stiut(vechi[i]) for i in dif)

	def _a_doua_vizionare(self, k, val):
		"""Valorile noi din VD_VOLATILE se scriu la a doua vizionare la rand cu aceleasi valori. O vizionare = o
		chemare vazut() a canalului; fara vazut(), fiecare chemare conteaza ca vizionare."""
		volatile = tuple(val[i] for i in VD_VOLATILE)
		viz = self._vizionari.get(k)
		if viz is None:
			self._chemari += 1
			viz = ("chemare", self._chemari)
		asteapta = self._asteapta.get(k)
		if asteapta is None or asteapta[0] != volatile:
			self._asteapta[k] = (volatile, viz)
			return False
		if asteapta[1] == viz:
			return False
		self._asteapta.pop(k, None)
		return True

	def _sg_nou(self, k, rec, val, vf_nou):
		"""Semnalul nu murdareste niciodata baza (nici cu grupa lipsa, nici cu ceasul nereglat): ultima valoare sta in
		memorie si intra in rand (facut atunci, daca lipseste) la urmatoarea scriere care are loc oricum."""
		vechi_vf = vf_grupa(rec, "sg")
		if val == rec.get("sg") and vechi_vf is not None and vf_nou[0] <= vechi_vf[0]:
			self._sg.pop(k, None)
			return
		self._sg[k] = (val, vf_nou)

	def actualizeaza_tp(self, ref_sau_cheie_tp, valori, sursa, cand=None):
		"""Valorile unui transponder (dict plat de campuri). "l": pr si dc; "v": numai pr (frecventa, polarizarea, SR-ul,
		pozitia cu care s-a prins semnalul); "o": dc; "j" si "m": ms. -> True daca s-a schimbat continutul."""
		if isinstance(ref_sau_cheie_tp, str) and ref_sau_cheie_tp.count(":") == 2:
			k = cheie_tp(ref_sau_cheie_tp)
		else:
			k = cheie_tp_din_cheie(cheie(ref_sau_cheie_tp))
		grupe = {"l": ("pr", "dc"), "v": ("pr",), "o": ("dc",), "j": ("ms",), "m": ("ms",)}.get(sursa)
		if k is None or grupe is None or not isinstance(valori, dict):
			return False
		self._asigura()
		if self._lung(self._t, k):
			return False
		acum = self._ceas()
		cand = acum if cand is None else cand
		vf_nou = (_data_stocata(cand, acum), sursa, FEL_NORMAL)
		text = self._t.get(k)
		rec = self._desface(k, text, tp=True) if text is not None else None
		if rec is None:
			rec = {"tp": k}
		schimbat = False
		for grupa in grupe:
			val = curata_grupa(grupa, valori)
			if val is None:
				continue
			vechi_val, vechi_vf = valoare_grupa(rec, grupa), vf_grupa(rec, grupa)
			if vechi_vf is None or _necunoscut(grupa, vechi_val):
				_pune_grupa(rec, grupa, val, vf_nou)
				schimbat = True
				continue
			rez_val, rez_vf = uneste_grupa((vechi_val, vechi_vf), (val, vf_nou), acum, grupa)
			if rez_val != vechi_val or self._merita_scris(vechi_vf, rez_vf, acum):
				_pune_grupa(rec, grupa, rez_val, rez_vf)
				schimbat = True
		if schimbat:
			nou = rand_tp(rec)
			if nou == text:
				return False
			self._seteaza(self._t, k, nou)
			self._schimba(grupe=())
		return schimbat

	def uita(self, ref_sau_cheie=None):
		"""Scoate un canal (sau, fara cheie, toata baza) din memorie; pe disc la urmatoarea scriere."""
		self._asigura()
		if ref_sau_cheie is None:
			if self._c or self._t or self._altele:
				chei = list(self._c)
				self._c, self._t, self._altele, self._octeti = {}, {}, [], 0
				self._rezerva = None
				self._vazut, self._confirmat, self._sg, self._asteapta = {}, {}, {}, {}
				self._schimba()
				for k in chei:
					self._schimbate[k] = self.versiune
				return True
			return False
		k = cheie(ref_sau_cheie)
		if k and self._sterge(self._c, k):
			self._schimba(k)
			return True
		return False

	# ------------------------------------------------ unirea din afara

	def _uneste_rec(self, local, strain, acum, tp=False):
		"""Unire pe grupe; -> (rand, schimbat)."""
		rec = dict(local) if local else {("tp" if tp else "k"): strain.get("tp" if tp else "k")}
		if isinstance(rec.get("vf"), dict):
			rec["vf"] = dict(rec["vf"])
		schimbat = local is None
		for grupa in (GRUPE_TP if tp else GRUPE_CANAL):
			nv, nvf = valoare_grupa(strain, grupa), vf_grupa(strain, grupa)
			if nvf is None or _necunoscut(grupa, nv):
				continue
			vv, vvf = valoare_grupa(rec, grupa), vf_grupa(rec, grupa)
			vechi = (vv, vvf) if vvf is not None and not _necunoscut(grupa, vv) else None
			rez = uneste_grupa(vechi, (nv, nvf), acum, grupa)
			if rez is not None and (vechi is None or rez[0] != vv or rez[1] != vvf):
				_pune_grupa(rec, grupa, rez[0], rez[1])
				schimbat = True
		return rec, schimbat

	def _uneste_text(self, k, text, tp):
		"""Un rand-text din memoria veche peste randul citit acum (dupa o reincercare reusita)."""
		acum = self._ceas()
		strain = self._desface(k, text, tp=tp)
		harta = self._t if tp else self._c
		if strain is None or self._lung(harta, k):
			return
		local = self._desface(k, harta.get(k), tp=tp) if k in harta else None
		rec, schimbat = self._uneste_rec(local, strain, acum, tp)
		if schimbat:
			self._seteaza(harta, k, rand_tp(rec) if tp else rand_canal(rec, self._jurnal))
			self._schimba(None if tp else k, () if tp else None)

	def _curata_strain(self, o, fel):
		"""Un rand venit din afara (import, restaurare, baza de pornire), verificat strict pe grupe -> rand sau None."""
		tp = "tp" in o
		k = cheie_tp(o.get("tp")) if tp else cheie(o.get("k"))
		if k is None:
			return None
		acum = self._ceas()
		rec = {("tp" if tp else "k"): k}
		for grupa in (GRUPE_TP if tp else GRUPE_CANAL):
			if grupa == "sg":
				continue
			vf = vf_grupa(o, grupa)
			val = curata_grupa(grupa, valoare_grupa(o, grupa))
			if vf is None or val is None:
				continue
			if tp and vf[1] not in _SURSE_TP[grupa]:
				continue
			if not tp and (vf[1] in ("c", "o") or (vf[1] == "l" and grupa != "sv")):
				continue
			# o valoare venita dintr-o baza de pornire ramane de pornire si la un import (copia altui receptor sau a
			# acestuia): altfel ar trece drept aflata de receptor si o baza de pornire mai noua nu ar mai inlocui-o
			vf = (_data_stocata(vf[0], acum), vf[1], FEL_PORNIRE if fel == FEL_IMPORT and vf[2] == FEL_PORNIRE else fel)
			_pune_grupa(rec, grupa, val, vf)
		if len(rec) == 1:
			return None
		return rec

	def _uneste_linii(self, linii, fel, chei_lamedb=None, tacut=False):
		self._asigura()
		acum = self._ceas()
		adaugate = schimbate = respinse = 0
		tp_permise = None
		if chei_lamedb is not None:
			tp_permise = set(cheie_tp_din_cheie(x) for x in chei_lamedb)
		for linie in linii:
			linie = linie.strip()
			if not linie:
				continue
			if len(linie) > RAND_CITIT or not linie.isascii():
				respinse += 1
				continue
			o = _loads(linie)
			if not isinstance(o, dict):
				respinse += 1
				continue
			if o.get("fel") == FEL or "sfarsit" in o:
				continue
			if "k" not in o and "tp" not in o:
				respinse += 1
				continue
			rec = self._curata_strain(o, fel)
			if rec is None:
				respinse += 1
				continue
			tp = "tp" in rec
			k = rec["tp" if tp else "k"]
			if chei_lamedb is not None and (k not in tp_permise if tp else k not in chei_lamedb):
				continue
			harta = self._t if tp else self._c
			if self._lung(harta, k):
				continue
			local = self._desface(k, harta.get(k), tp=tp) if k in harta else None
			nou, schimbat = self._uneste_rec(local, rec, acum, tp)
			if schimbat:
				self._seteaza(harta, k, rand_tp(nou) if tp else rand_canal(nou, self._jurnal))
				self._schimba(None if tp else k, () if tp else None)
				if local is None:
					adaugate += 1
				else:
					schimbate += 1
		self._potriveste_bugetul()
		if not tacut:
			self._jurnal("unire (fel %d): %d adaugate, %d schimbate, %d respinse" % (fel, adaugate, schimbate, respinse))
		return adaugate, schimbate, respinse

	def uneste(self, text_jsonl, fel=FEL_IMPORT, chei_lamedb=None):
		"""Unirea unei baze venite din afara (fel 2 baza de pornire, 3 import): pe canal si pe grupa, valoarea mai noua
		castiga, deci nu se suprascrie nimic local mai nou. Cu `chei_lamedb` intra numai aceste canale (si
		transponderele lor). -> (adaugate, schimbate, respinse)."""
		if not isinstance(text_jsonl, str) or len(text_jsonl) > MAX_CITIT:
			self._jurnal("unire refuzata: text prea mare sau gresit")
			return 0, 0, 1
		return self._uneste_linii(io.StringIO(text_jsonl), fel, chei_lamedb)

	def uneste_fisier(self, cale, fel=FEL_IMPORT, chei_lamedb=None):
		"""Ca uneste, citind fisierul rand cu rand: numai un fisier obisnuit (SistemFisiere.deschide_import), cel mult
		MAX_CITIT octeti numarati la citire (marimea din fstat nu ajunge: un fisier care creste, sau unul care nu e
		obisnuit, are alta marime decat ce se citeste) si randuri de cel mult RAND_CITIT (restul unui rand mai lung se
		sare fara sa fie tinut in memorie)."""
		try:
			f = self._fs.deschide_import(cale)
		except (IOError, OSError) as e:
			self._jurnal("unire: nu pot citi %s: %s" % (cale, e))
			return 0, 0, 0
		stare = {"mare": False}
		try:
			try:
				marime = self._fs.marime_deschis(f)
			except (IOError, OSError, ValueError, AttributeError):
				marime = 0
			if marime > MAX_CITIT:
				self._jurnal("unire refuzata: %s prea mare" % cale)
				return 0, 0, 1
			rez = self._uneste_linii(_linii_marginite(f, stare), fel, chei_lamedb)
		except (IOError, OSError) as e:
			self._jurnal("unire: citirea lui %s a cazut: %s" % (cale, e))
			return 0, 0, 0
		finally:
			f.close()
		if stare["mare"]:
			self._jurnal("unire: %s trece de %d octeti; restul nu s-a citit" % (cale, MAX_CITIT))
			return rez[0], rez[1], rez[2] + 1
		return rez

	# ------------------------------------------------ bugetul de octeti

	def _potriveste_bugetul(self):
		"""Fisierul sub MAX_SCRIS: pleaca randurile cu cea mai veche data a celei mai noi grupe (randurile fara data si
		cele de fel necunoscut primele), pana la TINTA_SCOATERE din buget."""
		if self._octeti + 1024 <= MAX_SCRIS:
			return 0
		acum = self._ceas()
		tinta = int(MAX_SCRIS * TINTA_SCOATERE)
		ordine = []
		for i, text in enumerate(self._altele):
			ordine.append((-1, 2, i))
		for k, text in self._t.items():
			ordine.append((data_max_text(text, acum), 1, k))
		for k, text in self._c.items():
			ordine.append((data_max_text(text, acum), 0, k))
		ordine.sort(key=lambda x: (x[0], x[1]))
		scoase = 0
		scoase_altele = set()
		for _d, fel, k in ordine:
			if self._octeti + 1024 <= tinta:
				break
			if fel == 2:
				self._octeti -= len(self._altele[k]) + 1
				scoase_altele.add(k)
			elif fel == 1:
				self._sterge(self._t, k)
			else:
				self._sterge(self._c, k)
				self._schimbate[k] = self.versiune + 1
			scoase += 1
		if scoase_altele:
			self._altele = [x for i, x in enumerate(self._altele) if i not in scoase_altele]
		if scoase:
			self._schimba()
			self._jurnal("buget: %d randuri scoase (cele mai vechi)" % scoase)
		return scoase

	# ------------------------------------------------ scrierea

	def prag_s(self):
		"""Pragul de timp intre doua scrieri "prag", crescut cu marimea fisierului (bugetul pe zi)."""
		return max(PRAG_MIN_S, self._octeti * float(ZI_S) / BUGET_ZI)

	def _pragul_permite(self, acum):
		if acum < self._ultima_scriere:
			self._ultima_scriere = acum
		if acum - self._ultima_scriere < self.prag_s():
			return False
		_scrieri, octeti = self._contor.citeste(_zi(acum))
		return octeti + self._octeti <= BUGET_ZI

	def _poate_scrie(self, motiv):
		if self._stare == AMANAT and motiv == STANDBY:
			self._stare, self._motiv, self._erori = SCRIE, None, 0
		return self._stare == SCRIE

	def trebuie_scris(self, motiv=PRAG):
		"""Ar scrie acum salveaza(motiv)?"""
		self._asigura()
		if self._stare != SCRIE and not (self._stare == AMANAT and motiv == STANDBY):
			return False
		if not self.murdar() or self._uitare_prea_deasa(motiv):
			return False
		return motiv != PRAG or self._pragul_permite(self._ceas())

	def _uitare_prea_deasa(self, motiv):
		"""O scriere "uitare" la mai putin de MARGINE_UITARE_S de scrierea reusita de dinainte se sare: baza ramane
		murdara si pleaca la prag, standby sau oprire."""
		if motiv != UITARE or not self._ultima_scriere_reusita:
			return False
		return 0 <= self._ceas() - self._ultima_scriere_reusita < MARGINE_UITARE_S

	def _aplica_confirmari(self):
		"""Confirmarile si semnalul din memorie intra in randuri, numai la o scriere care are loc oricum. Un canal care are
		numai semnal primeste acum randul lui; un rand peste RAND_CITIT sau care nu se desface ramane neatins."""
		chei = set(self._confirmat) | set(self._sg)
		for k in chei:
			text = self._c.get(k)
			if text is not None and len(text) > RAND_CITIT:
				continue
			# fara curata_rand: aici se schimba numai datele din "vf" si grupa sg, iar un rand prea adanc nu se desface
			# (_loads); randul ramane altfel acelasi text, iar instantaneul ruleaza pe firul interfetei
			rec = self._desface(k, text, tot=False) if text is not None else None
			if rec is None:
				if text is not None or k not in self._sg:
					continue
				rec = {"k": k}
			for grupa, (cand, sursa, fel) in self._confirmat.get(k, {}).items():
				vf = vf_grupa(rec, grupa)
				if vf is not None and cand > vf[0]:
					rec["vf"][grupa] = _vf_lista((cand, sursa, fel))
			if k in self._sg:
				val, vf = self._sg[k]
				_pune_grupa(rec, "sg", val, vf)
			nou = rand_canal(rec, self._jurnal)
			if nou != text:
				self._seteaza(self._c, k, nou)
		self._confirmat = {}
		self._sg = {}

	def _instantaneu(self):
		"""Pe firul apelantului: confirmari, buget, apoi lista de referinte la randuri."""
		self._aplica_confirmari()
		self._potriveste_bugetul()
		acum = self._ceas()
		antet = dict(self._antet)
		antet.update({"fel": FEL, "v": VERSIUNE, "scris": int(acum), "imagine": self._imagine or antet.get("imagine", ""),
			"canale": len(self._c), "transpondere": len(self._t)})
		antet.setdefault("migrat", {})
		antet.setdefault("pornire_md5", "")
		ordine = {"fel": 0, "v": 1, "scris": 2, "imagine": 3, "canale": 4, "transpondere": 5, "migrat": 6,
			"pornire_md5": 7}
		antet = dict(sorted(antet.items(), key=lambda x: (ordine.get(x[0], 99), x[0])))
		randuri = [_json(antet)]
		randuri.extend(self._t.values())
		randuri.extend(self._c.values())
		randuri.extend(self._altele)
		n = len(randuri) - 1
		randuri.append(_json({"sfarsit": n}))
		return {"versiune": self.versiune, "randuri": randuri, "acum": acum, "canale": len(self._c),
			"octeti": sum(len(r) + 1 for r in randuri)}

	def _eroare(self, e):
		self._erori += 1
		self._jurnal("nu pot scrie %s: %s (eroarea %d la rand)" % (self.cale, e, self._erori))
		if self._erori >= ERORI_AMANARE and self._stare == SCRIE:
			self._stare, self._motiv = AMANAT, None
			self._jurnal("scrieri amanate pana la standby")

	def _scrie(self, inst, fundal=False):
		"""Drumul unic de scriere, sub lacat: .nou.<nr>, fsync, .bak prin .bak.nou, replace, fsync pe dosar."""
		fs = self._fs
		with self._lacat:
			if fundal and self._oprire:
				return False
			if self._stare != SCRIE:
				return False
			dosar = self._dosar()
			if not fs.isdir(dosar):
				self._numai_citire(DOSAR_LIPSA, dosar)
				return False
			self._nr += 1
			nou = "%s.nou.%d" % (self.cale, self._nr)
			try:
				f = fs.deschide_scriere(nou)
				try:
					for r in inst["randuri"]:
						f.write(r)
						f.write("\n")
					fs.fsync(f)
				finally:
					f.close()
			except (IOError, OSError, ValueError) as e:
				self._sterge_temporar(nou)
				self._eroare(e)
				return False
			if self._viu_bun and fs.exista(self.cale):
				bak_nou = self.cale + ".bak.nou"
				try:
					if fs.exista(bak_nou):
						fs.remove(bak_nou)
					fs.link(self.cale, bak_nou)
					fs.replace(bak_nou, self.cale + ".bak")
				except (IOError, OSError) as e:
					self._jurnal("fara .bak nou: %s" % e)
					self._sterge_temporar(bak_nou)
			if self._stare != SCRIE:
				self._sterge_temporar(nou)
				return False
			try:
				fs.replace(nou, self.cale)
			except (IOError, OSError) as e:
				self._sterge_temporar(nou)
				self._eroare(e)
				return False
			fs.fsync_dosar(dosar)
			self.versiune_scrisa = inst["versiune"]
			self._ultima_scriere = inst["acum"]
			self._ultima_scriere_reusita = inst["acum"]
			self._erori = 0
			self._viu_bun = True
			scrieri, octeti = self._contor.adauga(_zi(inst["acum"]), inst["octeti"])
			self._jurnal("scris: %d canale, %d KiB, azi %d scrieri / %d KiB" % (inst["canale"],
				(inst["octeti"] + 1023) // 1024, scrieri, (octeti + 1023) // 1024))
			return True

	def _sterge_temporar(self, cale):
		try:
			if self._fs.exista(cale):
				self._fs.remove(cale)
		except (IOError, OSError):
			pass

	def salveaza(self, motiv=PRAG, sincron=False):
		"""Scrierea pe disc, numai daca baza e murdara. PRAG asteapta pragul si bugetul zilei; celelalte motive nu
		asteapta, dar se numara. Implicit in firul de scriere (unul singur; cat ruleaza, baza ramane murdara);
		sincron=True asteapta firul cel mult ASTEPTARE_FIR_S si scrie pe firul apelantului. -> True daca a scris sau a
		pornit scrierea."""
		self._asigura()
		if motiv not in MOTIVE or not self._poate_scrie(motiv) or not self.murdar():
			return False
		if motiv == PRAG and not self._pragul_permite(self._ceas()):
			return False
		if self._uitare_prea_deasa(motiv):
			self._jurnal("scrierea la uitare amanata (sub %d s de la cea de dinainte)" % MARGINE_UITARE_S)
			return False
		fir = self._fir
		if fir is not None and fir.is_alive():
			if not sincron:
				return False
			fir.join(ASTEPTARE_FIR_S)
			if fir.is_alive():
				self._jurnal("scrierea din fundal nu s-a terminat in %.0f s; sar scrierea" % ASTEPTARE_FIR_S)
				return False
			if not self.murdar():
				return False
		inst = self._instantaneu()
		if sincron:
			return self._scrie(inst)
		self._fir = self._porneste_fir(lambda: self._scrie(inst, fundal=True))
		return True

	def la_oprire(self, asteapta_s=ASTEPTARE_FIR_S):
		"""Oprirea sau repornirea interfetei: firul din fundal nu mai incepe o scriere; se asteapta cel mult
		`asteapta_s`, apoi, numai daca baza e murdara, o scriere sincrona (alt .nou.<nr>)."""
		self._oprire = True
		fir = self._fir
		if fir is not None and fir.is_alive():
			fir.join(asteapta_s)
			if fir.is_alive():
				self._jurnal("scrierea din fundal nu s-a terminat; scrierea de la oprire sarita")
				return False
		if not self._incarcat or not self.murdar() or not self._poate_scrie(OPRIRE):
			return False
		return self._scrie(self._instantaneu())

	# ------------------------------------------------ antetul (migrarea, baza de pornire)

	def migrat(self):
		"""{fisier vechi: [mtime, marime]} din antet."""
		self._asigura()
		m = self._antet.get("migrat")
		return dict(m) if isinstance(m, dict) else {}

	def noteaza_migrat(self, fisier, mtime, marime):
		self._asigura()
		m = self.migrat()
		m[fisier] = [int(mtime), int(marime)]
		self._antet["migrat"] = m
		self._schimba(grupe=())

	def pornire_md5(self):
		self._asigura()
		v = self._antet.get("pornire_md5")
		return v if isinstance(v, str) else ""

	def noteaza_pornire_md5(self, md5):
		self.noteaza_antet_pornire("pornire_md5", md5)

	def antet_pornire(self, cheie):
		"""O valoare a antetului bazei de pornire (CHEI_ANTET_PORNIRE), sau None."""
		self._asigura()
		return self._antet.get(cheie) if cheie in CHEI_ANTET_PORNIRE else None

	def noteaza_antet_pornire(self, cheie, valoare):
		"""Semnul unei uniri reusite (md5-ul fisierului unit, versiunea celei mai noi baze unite); pe disc cu urmatoarea
		scriere."""
		self._asigura()
		if cheie in CHEI_ANTET_PORNIRE and self._antet.get(cheie) != valoare:
			self._antet[cheie] = valoare
			self._schimba(grupe=())

	def uneste_linii_pornire(self, linii, chei_lamedb=None):
		"""O bucata dintr-o baza de pornire (randuri-text JSONL), fara randul de jurnal al unirii: apelantul (unirea pe
		bucati din Components/HdsBazaPornire.py) scrie unul singur la sfarsit. -> (adaugate, schimbate, respinse)."""
		return self._uneste_linii(linii, FEL_PORNIRE, chei_lamedb, tacut=True)

	# ------------------------------------------------ exportul

	def exporta_linii(self, fel="jsonl"):
		"""Exportul ca generator de linii-text (fiecare cu sfarsitul de rand), ca apelantul sa-l scrie pe bucati (de ex. cate cateva sute
		de linii pe o trecere a reactorului), fara sa tina firul interfetei pe toata baza si fara tot textul in memorie.
		Cheile se iau la inceput; un rand scos intre doua bucati se sare. Felurile:
		"jsonl": randurile asa cum sunt, cu antet si sfarsit;
		"csv": COLOANE_CSV (fara sg si vazut); un rand cu alta forma trece intai prin curata_rand, iar daca tot nu se
		poate scrie, se sare (o linie in jurnal);
		"pornire": JSONL pentru baza de pornire sau server: numai grupele verificate cu data (surse v, p, j, m), date
		rotunjite la prima zi a lunii, fel 2, fara sg, fara cheile necunoscute, randurile in ordinea cheilor; un rand
		fara nicio grupa verificata nu iese."""
		self._asigura()
		acum = self._ceas()
		if fel == "csv":
			return self._linii_csv()
		if fel == "pornire":
			return self._linii_pornire(acum)
		return self._linii_jsonl(acum)

	def _linii_jsonl(self, acum):
		tp, c = list(self._t.values()), list(self._c.values())
		yield _json({"fel": FEL, "v": VERSIUNE, "scris": int(acum), "canale": len(c), "transpondere": len(tp)}) + "\n"
		for text in tp:
			yield text + "\n"
		for text in c:
			yield text + "\n"
		yield _json({"sfarsit": len(tp) + len(c)}) + "\n"

	def _linii_csv(self):
		buf = io.StringIO()
		w = csv.writer(buf, lineterminator="\n")

		def linie(randul):
			buf.seek(0)
			buf.truncate()
			w.writerow(randul)
			return buf.getvalue()
		yield linie(COLOANE_CSV)
		tp_cache = {}
		sarite = 0
		for k in list(self._c):
			text = self._c.get(k)
			rec = self._desface(k, text, tot=False) if text is not None else None
			if rec is None:
				continue
			ktp = cheie_tp_din_cheie(k)
			if ktp not in tp_cache:
				if len(tp_cache) > 4096:
					tp_cache.clear()
				tp_cache[ktp] = self._desface(ktp, self._t.get(ktp), tot=False, tp=True) if ktp in self._t else None
			tpr = tp_cache[ktp]
			try:
				randul = rand_csv(rec, tpr)
			except Exception:
				try:
					randul = rand_csv(curata_rand(rec, straine=False),
						curata_rand(tpr, tp=True, straine=False) if tpr else None)
				except Exception as e:
					sarite += 1
					self._jurnal("export csv: rand %s sarit: %s: %s" % (k, type(e).__name__, e))
					continue
			yield linie(randul)
		if sarite:
			self._jurnal("export csv: %d randuri sarite" % sarite)

	def _linii_pornire(self, acum):
		def rotunjit(vf):
			return (_luna(vf[0]) if data_valida(vf[0], acum) else 0, vf[1], FEL_PORNIRE)

		yield _json({"fel": FEL, "v": VERSIUNE, "scris": _luna(acum)}) + "\n"
		n = 0
		for tp, harta in ((True, self._t), (False, self._c)):
			for k in sorted(harta):
				text = harta.get(k)
				rec = self._desface(k, text, tot=False, tp=tp) if text is not None else None
				if rec is None:
					continue
				out = {"tp" if tp else "k": k}
				for grupa in (GRUPE_TP if tp else GRUPE_CANAL):
					if grupa == "sg":
						continue
					vf = vf_grupa(rec, grupa)
					if vf is None or vf[1] not in SURSE_CU_DATA:
						continue
					val = curata_grupa(grupa, valoare_grupa(rec, grupa))
					if val is not None:
						_pune_grupa(out, grupa, val, rotunjit(vf))
				if len(out) == 1:
					continue
				yield (rand_tp(out) if tp else _json(_ordonat_canal(out))) + "\n"
				n += 1
		yield _json({"sfarsit": n}) + "\n"

	def exporta_in(self, f, fel="jsonl"):
		"""Exportul rand cu rand intr-un fisier text deschis (vezi exporta_linii). -> numarul randurilor de date."""
		n = 0
		for linie in self.exporta_linii(fel):
			f.write(linie)
			n += 1
		return max(0, n - (1 if fel == "csv" else 2))

	def exporta(self, fel="jsonl"):
		f = io.StringIO()
		self.exporta_in(f, fel)
		return f.getvalue()

	# ------------------------------------------------ jurnalul

	def jurnal(self):
		"""Starea bazei, pentru jurnal, ecran si web."""
		self._asigura()
		scrieri, octeti = self._contor.citeste(_zi(self._ceas()))
		return {
			"canale": len(self._c), "transpondere": len(self._t), "altele": len(self._altele),
			"marime": self._octeti, "ultima_scriere": self._ultima_scriere_reusita, "scrieri_azi": scrieri,
			"octeti_azi": octeti, "sarite": len(self._sarite) + self._rele_la_citire, "stare": self._stare,
			"motiv": self._motiv, "versiune": self.versiune, "versiune_scrisa": self.versiune_scrisa,
			"incarcare_ms": round(self._incarcare_ms, 1), "prag_s": int(self.prag_s()), "migrat": self.migrat(),
		}


_BAZA = []


def baza():
	"""Baza unica a procesului."""
	if not _BAZA:
		_BAZA.append(BazaCanale())
	return _BAZA[0]


def baza_existenta():
	"""Baza procesului, daca a fost facuta; altfel None (la oprire nu se face una noua)."""
	return _BAZA[0] if _BAZA else None


# ---------------------------------------------------------------- privirea adaptoarelor (fara toata baza in memorie)

MEMORIE_VEDERE = 64


class Vedere(object):
	"""Privire numai de citit peste canalele bazei, pentru adaptoarele cititorilor de dinainte (pistele, masuratorile,
	accesul): `functie(rand desfacut)` da valoarea de aratat sau None, `campuri` spun ce randuri pot avea o valoare
	(chei_cu). Un rand se desface numai la cerere; raman ultimele MEMORIE_VEDERE valori, golite la o schimbare a
	bazei. Se foloseste ca un dictionar: get, [], in, len, iteratie, keys, items, values. `grupe` (grupele bazei din
	care `functie` isi ia valoarea): `versiune` si golirea urmeaza numai schimbarile lor (versiune_grupe); fara ele,
	orice schimbare a bazei."""

	def __init__(self, b, functie, campuri, grupe=None):
		self._b = b
		self._functie = functie
		self._campuri = tuple(campuri)
		self._grupe = tuple(grupe) if grupe is not None else None
		self._memorie = collections.OrderedDict()
		self._versiune = None

	@property
	def versiune(self):
		return self._b.versiune if self._grupe is None else self._b.versiune_grupe(self._grupe)

	def _goleste_la_schimbare(self):
		v = self.versiune
		if self._versiune != v:
			self._memorie.clear()
			self._versiune = v

	def _valoare(self, k):
		self._goleste_la_schimbare()
		if k in self._memorie:
			self._memorie.move_to_end(k)
			return self._memorie[k]
		rec = self._b.cauta(k)
		if rec is None:
			# o cheie fara rand (cele mai multe canale din lista) nu ocupa memoria mica
			return None
		v = self._functie(rec)
		# prima cautare poate incarca baza (si schimba versiunea): valoarea ramane buna, memoria se goleste
		self._goleste_la_schimbare()
		self._memorie[k] = v
		while len(self._memorie) > MEMORIE_VEDERE:
			self._memorie.popitem(last=False)
		return v

	def get(self, k, implicit=None):
		v = self._valoare(k) if isinstance(k, str) and k else None
		return implicit if v is None else v

	def __getitem__(self, k):
		v = self.get(k)
		if v is None:
			raise KeyError(k)
		return v

	def __contains__(self, k):
		return self.get(k) is not None

	def items(self):
		for k in self._b.chei_cu(self._campuri):
			v = self._valoare(k)
			if v is not None:
				yield k, v

	def keys(self):
		return [k for k, _v in self.items()]

	def values(self):
		return [v for _k, v in self.items()]

	def __iter__(self):
		return iter(self.keys())

	def __len__(self):
		return sum(1 for _x in self.items())

	def __bool__(self):
		for _x in self.items():
			return True
		return False

	__nonzero__ = __bool__


# ---------------------------------------------------------------- migrarea din fisierele de dinainte

DOSAR_VECHI = "/etc/enigma2"
FISIER_PISTE = "hds_piste_canale.json"
FISIER_MASURATORI = "hds_masuratori_canale.json"
FISIER_ACCES = "hds_acces_canale.json"
FISIERE_VECHI = (FISIER_PISTE, FISIER_MASURATORI, FISIER_ACCES)


def amprenta_veche(cale):
	"""[mtime in secunde, marime] al unui fisier de dinainte; None daca lipseste; False la alta eroare."""
	try:
		st = os.stat(cale)
	except (IOError, OSError) as e:
		return None if getattr(e, "errno", None) in (errno.ENOENT, errno.ENOTDIR) else False
	return [int(st.st_mtime), int(st.st_size)]


def _module_vechi():
	"""(HdsPisteCanale, HdsAccesCanale, HdsFisierSigur), importate tarziu: ele folosesc acest modul."""
	try:
		from Components import HdsPisteCanale as P, HdsAccesCanale as A, HdsFisierSigur as S
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsPisteCanale as P
		import HdsAccesCanale as A
		import HdsFisierSigur as S
	return P, A, S


# o bucata de migrare pe firul interfetei; intre bucati, ceasul culegerii (Components/HdsCulegereCanale.py) lasa
# interfata sa lucreze
MIGRARE_BUCATA = 200
# starea unui fisier lasat pe mai tarziu pentru ca ceasul receptorului nu e potrivit (inainte de 2026 sau cu peste o
# zi in urma fata de data fisierului): datele lui ar iesi necunoscute, iar fisierul notat migrat nu s-ar mai uni
CEAS_NEPOTRIVIT = "ceas"
OPRITA = "oprit"


def _data_fara_data(b, k, grupe, mtime, anterior):
	"""Data unei intrari fara data proprie: a fisierului (mtime, aproximativa). La o unire din nou (fisierul scris iar
	de o imagine mai veche, dupa migrarea notata cu `anterior`), o intrare ramasa neschimbata de atunci ar lua data noua
	a fisierului si ar bate o valoare aflata intre timp; deci, cand baza are pentru canal o grupa mai noua decat
	`anterior`, intrarea ia data de atunci: valoarea bazei ramane (o intrare schimbata de imaginea veche se reinvata la
	urmatoarea vizionare)."""
	if not anterior:
		return mtime
	rec = b.cauta(k)
	if rec is None:
		return mtime
	for g in grupe:
		st = b.stare(rec, g)
		if st is not None and st[0] > anterior:
			return anterior
	return mtime


def _citeste_piste(cale, module):
	P, _A, S = module
	vechi = P.Baza(cale)
	date = vechi.toate()
	if vechi.fisier.stare != S.CITIT:
		return vechi.fisier.stare, vechi.fisier.detaliu, None
	return S.CITIT, "", list(date.items())


def _unu_piste(b, k, rec, mtime, anterior, acum, module):
	"""hds_piste_canale.json: a, d, x, tt in grupa pi, hb in grupa hb, cu [t, s] al intrarii (data exacta); fara t
	valid, data fisierului (aproximativa)."""
	grupe = {}
	pi = dict((c, rec[c]) for c in CAMPURI_PI if c in rec)
	if pi:
		grupe["pi"] = pi
	if "hb" in rec:
		grupe["hb"] = rec["hb"]
	if not grupe:
		return False
	t = rec.get("t")
	if data_valida(t, acum):
		cand, fel = t, FEL_NORMAL
	else:
		cand, fel = _data_fara_data(b, k, tuple(grupe), mtime, anterior), FEL_APROXIMATIV
	return b.actualizeaza(k, grupe, rec.get("s") if rec.get("s") in ("v", "p") else "v", cand, fel)


def _citeste_masuratori(cale, module):
	_P, _A, S = module
	vechi = _X.Masuratori(cale)
	date = vechi.toate()
	if vechi.fisier.stare != S.CITIT:
		return vechi.fisier.stare, vechi.fisier.detaliu, None
	return S.CITIT, "", list(date.items())


def _unu_masurare(b, k, v, mtime, anterior, acum, module):
	"""hds_masuratori_canale.json: [inaltime, progresiv, codec] in grupa vd, cu data fisierului (aproximativa);
	inaltimea 0 (canal criptat nedecodat) = nu se stie, iar o valoare fara nimic stiut nu face grupa."""
	if not isinstance(v, list) or len(v) != 3:
		return False
	cand = _data_fara_data(b, k, ("vd",), mtime, anterior)
	return b.actualizeaza(k, {"vd": [-1, v[0], v[1], -1, -1, "", v[2]]}, "v", cand, FEL_APROXIMATIV)


def _citeste_acces(cale, module):
	_P, A, S = module
	vechi = A.Memorie(cale, programeaza=lambda functie, secunde: None)
	date = vechi.toate()
	if vechi.fisier.stare != S.CITIT:
		return vechi.fisier.stare, vechi.fisier.detaliu, None
	return S.CITIT, "", list(date.items())


def _unu_acces(b, k, stare, mtime, anterior, acum, module):
	"""hds_acces_canale.json: "fta" / "criptat" in grupa ca, fara CAID-uri, cu data fisierului (aproximativa)."""
	_P, A, _S = module
	cand = _data_fara_data(b, k, ("ca",), mtime, anterior)
	return b.actualizeaza(k, {"ca": [1 if stare == A.CRIPTAT else 0, []]}, "v", cand, FEL_APROXIMATIV)


class Migrare(object):
	"""Unirea fisierelor de dinainte (pistele, masuratorile, accesul) in baza, pe grupe, pe bucati: fiecare pas() face
	o singura bucata (citirea intreaga a unui fisier, sau cel mult `bucata` intrari) si intoarce True cat mai e de
	lucru; `rez` = {fisier: "lipseste" | "la zi" | "migrat" | "schimbat" | "necitit" | CEAS_NEPOTRIVIT | OPRITA |
	starea citirii nereusite}. Valoarea mai noua castiga (uneste_grupa). Fisierele raman pe loc, neatinse: cititorii lor
	nu scriu nimic fara salveaza(). Un fisier se uneste cand lipseste din antetul "migrat" sau are alt [mtime, marime]
	decat cel notat acolo (scris din nou de o imagine mai veche). Se noteaza in "migrat" numai dupa o citire reusita,
	cu toate intrarile unite si cu acelasi [mtime, marime] inainte si dupa; pe disc ajunge cu urmatoarea scriere
	reusita a bazei. Nu se noteaza, deci se incearca din nou la urmatoarea migrare: un fisier necitit (eroare de
	citire, JSON stricat, alta forma, v mai mare, prea mare), unul schimbat in timpul lucrului, unul lasat pentru ceas
	(CEAS_NEPOTRIVIT) si unul la care scrierile bazei s-au oprit (OPRITA). Intre bucati pot veni valori vii
	(actualizeaza e intreaga pe fiecare chemare) sau o scriere la prag cu fisierul pe jumatate unit: el nu e notat,
	deci se uneste din nou, cu acelasi rezultat, la migrarea urmatoare."""

	def __init__(self, b, dosar=DOSAR_VECHI, bucata=MIGRARE_BUCATA):
		self.b = b
		self.dosar = dosar
		self.bucata = max(1, int(bucata))
		self.rez = {}
		self._ramase = [(FISIER_PISTE, _citeste_piste, _unu_piste),
			(FISIER_MASURATORI, _citeste_masuratori, _unu_masurare), (FISIER_ACCES, _citeste_acces, _unu_acces)]
		self._curent = None
		self._module = None
		self._facute = None
		self.gata = False

	def _sfarsit(self):
		self.gata = True
		self._curent = None
		return False

	def pas(self):
		b = self.b
		if self.gata:
			return False
		if b.stare_scriere()[0] == OPRIT:
			if self._curent is not None:
				self.rez[self._curent["fisier"]] = OPRITA
			return self._sfarsit()
		if self._module is None:
			try:
				self._module = _module_vechi()
			except Exception as e:
				b._jurnal("migrare: cititorii de dinainte nu se incarca: %s" % e)
				return self._sfarsit()
			self._facute = b.migrat()
		if self._curent is None:
			if not self._ramase:
				return self._sfarsit()
			self._incepe(*self._ramase.pop(0))
		else:
			self._uneste_bucata()
		if self._curent is None and not self._ramase:
			return self._sfarsit()
		return True

	def _incepe(self, fisier, citeste, unu):
		b = self.b
		cale = os.path.join(self.dosar, fisier)
		inainte = amprenta_veche(cale)
		if inainte is None:
			self.rez[fisier] = "lipseste"
			return
		if inainte is False:
			self.rez[fisier] = "necitit"
			b._jurnal("migrare: %s nu se poate citi; se incearca din nou" % fisier)
			return
		anterior = self._facute.get(fisier)
		if anterior == inainte:
			self.rez[fisier] = "la zi"
			return
		# un ceas vadit gresit (inainte de 2026) nu cere citirea; unul in urma fata de data fisierului se vede dupa ea,
		# ca un fisier stricat sa fie spus ca atare
		if b._ceas() < DATA_MIN:
			self._fara_ceas(fisier, inainte)
			return
		try:
			stare, detaliu, intrari = citeste(cale, self._module)
		except Exception as e:
			stare, detaliu, intrari = "eroare", "%s: %s" % (type(e).__name__, e), None
		if stare != "citit":
			self.rez[fisier] = stare
			b._jurnal("migrare: %s nemigrat (%s %s); se incearca din nou" % (fisier, stare, detaliu))
			return
		if inainte[0] > b._ceas() + ZI_S:
			self._fara_ceas(fisier, inainte)
			return
		vechi = anterior[0] if isinstance(anterior, list) and anterior and isinstance(anterior[0], int) else None
		self._curent = {"fisier": fisier, "cale": cale, "inainte": inainte, "unu": unu, "intrari": intrari, "i": 0,
			"n": 0, "erori": 0, "anterior": vechi}
		if not intrari:
			self._uneste_bucata()

	def _fara_ceas(self, fisier, inainte):
		self.rez[fisier] = CEAS_NEPOTRIVIT
		self.b._jurnal("migrare: %s lasat pe mai tarziu: ceasul receptorului (%d) nu se potriveste cu data fisierului "
			"(%d)" % (fisier, int(self.b._ceas()), inainte[0]))

	def _uneste_bucata(self):
		b, c = self.b, self._curent
		acum = b._ceas()
		intrari, i = c["intrari"], c["i"]
		for k, v in intrari[i:i + self.bucata]:
			try:
				if c["unu"](b, k, v, c["inainte"][0], c["anterior"], acum, self._module):
					c["n"] += 1
			except Exception as e:
				c["erori"] += 1
				b._jurnal("migrare: %s, intrarea %s: %s: %s" % (c["fisier"], k, type(e).__name__, e))
		c["i"] = i + self.bucata
		if c["i"] < len(intrari):
			return
		self._curent = None
		fisier = c["fisier"]
		if c["erori"]:
			self.rez[fisier] = "eroare"
			b._jurnal("migrare: %s nemigrat (%d intrari cazute); se incearca din nou" % (fisier, c["erori"]))
			return
		if amprenta_veche(c["cale"]) != c["inainte"]:
			self.rez[fisier] = "schimbat"
			b._jurnal("migrare: %s s-a schimbat in timpul citirii; se incearca din nou" % fisier)
			return
		b.noteaza_migrat(fisier, c["inainte"][0], c["inainte"][1])
		self.rez[fisier] = "migrat"
		b._jurnal("migrare: %s, %d intrari unite" % (fisier, c["n"]))


def migreaza(b, dosar=DOSAR_VECHI):
	"""Migrarea (Migrare) dintr-o bucata: pentru probe si pentru apelantii fara ceas; pe receptor, ceasurile bazei
	(Components/HdsCulegereCanale.Pornire) o fac pe bucati, cu interfata libera intre ele. -> Migrare.rez."""
	m = Migrare(b, dosar)
	while m.pas():
		pass
	return m.rez

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStocareRetea.py: locurile din reteaua de acasa (filme, muzica si inregistrari de pe un calculator cu Windows, un
# NAS, un server FTP, WebDAV sau DLNA). O singura logica pentru ecranele de pe televizor (Screens/HdsLocuriRetea.py),
# pentru pagina web /locuri-retea (Plugins/Extensions/HdsWebControl/locuri_retea_web.py), pentru playerul de filme si
# pentru locul inregistrarilor (Components/HdsLocInregistrari.py).
#
# FELURILE si cum ajung la om:
#   smb      Windows si NAS: montat de nucleu (cifs, SMB 3.0 -> 2.1 -> 2.0) in /media/net/<nume>; apare in playerul de
#            fisiere ca orice disc si, dupa proba de scriere si viteza, poate fi locul inregistrarilor.
#   nfs      NAS si Linux: montat de nucleu (NFS 3 fara blocari, apoi 4) in /media/net/<nume>; la fel ca smb.
#   ftp      FTP si FTPS (TLS explicit, datele criptate): rasfoit din Python (ftplib); filmul merge prin puntea locala
#   ftps     (Components/HdsReteaUnealta.py, numai pe 127.0.0.1), parola nu apare in adresa filmului.
#   webdav   WebDAV pe http sau https: PROPFIND; filmul prin puntea locala (Basic sau Digest).
#   webdavs
#   dlna     serverele media din casa (UPnP ContentDirectory): gasite cu SSDP, rasfoite cu Browse, filmul direct de la
#            server (fara parola); subtitrarile date de server se descarca langa film.
# Montarea si rasfoirea pornesc NUMAI la cererea omului: nimic nu se cauta si nimic nu se monteaza singur la pornire,
# afara de locurile la care omul a ales anume "Montat si dupa repornire" (atunci in fundal, la 30 s dupa pornire, pe
# un fir, cu termen).
#
# PAROLELE: in /etc/enigma2/hdsatelit/retea-parole.bin (0600), criptate cu acelasi plic ca cheile traducerii
# (Components/HdsTraducereSubtitrari.cripteaza, identitatea receptorului: adresa placii si CID-ul eMMC), cu o eticheta
# proprie; lista locurilor (fara parole) in retea-locuri.json (0600). Copia setarilor le ia pe amandoua; parolele se
# citesc numai pe acelasi receptor (pe altul omul le scrie din nou). O parola nu se arata niciodata: nici pe televizor,
# nici in pagina web, nici in jurnal; montarea o primeste pe intrarea standard a procesului copil.
#
# FIRELE: nimic din retea nu ruleaza pe firul enigma2. Montarea, demontarea si proba de viteza ruleaza intr-un proces
# copil (un mount(2) blocat de un server oprit nu tine enigma2), rasfoirea si cautarea in casa pe fire cu termene
# scurte; rezultatul il culege un eTimer pe firul enigma2 (tragere: reactor.callFromThread nu trezeste prompt bucla
# imaginii). Un loc montat al carui server nu mai raspunde (verificat la PAZA_S secunde, numai cat e montat ceva) e
# demontat lenes, ca un statvfs pe el sa nu blocheze ecranele.
#
# Partea de sus a fisierului nu cere enigma2: probele de pe PC (test_stocare_retea.py) o folosesc direct.

import errno
import json
import os
import re
import socket
import threading
import time

CALE_LOCURI = "/etc/enigma2/hdsatelit/retea-locuri.json"
CALE_PAROLE = "/etc/enigma2/hdsatelit/retea-parole.bin"
DOSAR_MONTARI = "/media/net"
DOSAR_SUBTITRARI = "/tmp/hds-retea"
PYTHON = "/usr/bin/python3"
DOSAR_PYTHON = "/usr/lib/enigma2/python"

FELURI = ("smb", "nfs", "ftp", "ftps", "webdav", "webdavs", "dlna")
FELURI_MONTATE = ("smb", "nfs")
FELURI_PUNTE = ("ftp", "ftps", "webdav", "webdavs")
PORT_IMPLICIT = {"smb": 445, "nfs": 2049, "ftp": 21, "ftps": 21, "webdav": 80, "webdavs": 443, "dlna": 0}

MAX_LOCURI = 50
MAX_TEXT = 200
MAX_PAROLA = 256
TERMEN_MONTARE_S = 45
TERMEN_DEMONTARE_S = 15
TERMEN_VITEZA_S = 90
TERMEN_RETEA_S = 12
PAZA_S = 60
INTARZIERE_PORNIRE_S = 30
VITEZA_MINIMA = 2.5      # MB/s la scriere: sub atat o inregistrare HD pierde bucati
VITEZA_BUNA = 6.0        # MB/s: si un canal UHD sau doua inregistrari deodata
MAX_SUBTITRARE = 4 * 1024 * 1024
MAX_FISIERE_SUBTITRARI = 12

EXTENSII_FILM = (".mkv", ".mp4", ".m4v", ".mov", ".avi", ".divx", ".mpg", ".mpeg", ".vob", ".ts", ".m2ts", ".mts",
	".webm", ".wmv", ".flv", ".ogv", ".3gp", ".iso", ".dat")
EXTENSII_MUZICA = (".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".ac3", ".dts", ".mka")
EXTENSII_SUBTITRARI = (".srt", ".ass", ".ssa", ".sub", ".idx", ".smi", ".sami", ".vtt", ".txt", ".mpl", ".sup")
SUBDOSARE_SUBTITRARI = ("subs", "sub", "subtitles", "subtitle", "subtitrari", u"subtitrări")

COD_ACCES = "acces"
COD_SERVER = "server"


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or u""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsStocareRetea] %s" % text)


# ------------------------------------------------------------------ textele

NUME_FEL = {
	"smb": N_("Calculator cu Windows sau NAS (SMB)"),
	"nfs": N_("NAS sau Linux (NFS)"),
	"ftp": N_("Server FTP"),
	"ftps": N_("Server FTP securizat (FTPS)"),
	"webdav": N_("WebDAV"),
	"webdavs": N_("WebDAV securizat (HTTPS)"),
	"dlna": N_("Server media din casă (DLNA)"),
}
NUME_SCURT = {"smb": u"SMB", "nfs": u"NFS", "ftp": u"FTP", "ftps": u"FTPS", "webdav": u"WebDAV",
	"webdavs": u"WebDAV HTTPS", "dlna": u"DLNA"}

ERORI = {
	"acces": N_("Numele de utilizator sau parola nu sunt bune, ori utilizatorul nu are voie în acest dosar."),
	"server": N_("Serverul nu răspunde. Verifică dacă este pornit și în aceeași rețea cu receptorul."),
	"nume": N_("Numele serverului nu se găsește în rețea. Scrie adresa lui, de pildă 192.168.1.20."),
	"dosar": N_("Dosarul nu există pe server. Verifică numele lui."),
	"nesuportat": N_("Acest fel de loc nu se poate monta pe receptor."),
	"dialect": N_("Serverul nu folosește nicio versiune pe care o cunoaște receptorul. La SMB, pornește pe server "
		"SMB 2 sau SMB 3."),
	"ocupat": N_("Locul este deja montat."),
	"plin": N_("Pe server nu mai este loc."),
	"citire": N_("Pe acest loc nu se poate scrie: este numai pentru citire."),
	"punct": N_("Receptorul nu poate face dosarul în care se montează locul."),
	"termen": N_("Serverul nu a răspuns la timp. Încearcă încă o dată."),
	"parola": N_("Parola acestui loc nu este salvată pe receptor. Scrie-o din nou la Editează."),
	"tls": N_("Legătura securizată cu serverul nu s-a putut face (certificatul nu este bun)."),
	"retea": N_("Receptorul nu este legat la rețea."),
	"lent": N_("Locul este prea lent pentru înregistrări."),
	"cerere": N_("Cererea nu este bună."),
	"lipsa": N_("Locul nu mai există. Poate a fost șters între timp."),
	"alta": N_("Locul nu s-a putut deschide. Încearcă încă o dată."),
}


def textFel(fel, scurt=False):
	if scurt:
		return NUME_SCURT.get(fel, fel or u"")
	return _t(NUME_FEL.get(fel, u"")) or (fel or u"")


def textEroare(cod):
	return _t(ERORI.get(cod) or ERORI["alta"])


def poateInregistrari(fel):
	return fel in FELURI_MONTATE


# ------------------------------------------------------------------ locurile (fara parole)

_NUME_RX = re.compile(u"^[^\x00-\x1f/\\\\]{1,60}$")
_GAZDA_RX = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-\.]{0,251}[A-Za-z0-9])?$")


def _scurt(text, n=MAX_TEXT):
	return (u"%s" % (text if text is not None else u"")).strip()[:n]


def gazdaBuna(gazda):
	"""Un nume de gazda sau o adresa IPv4 (fara schema, fara port, fara spatii)."""
	if not gazda or len(gazda) > 253:
		return False
	if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", gazda):
		return all(0 <= int(x) <= 255 for x in gazda.split("."))
	return bool(_GAZDA_RX.match(gazda))


def desparteGazda(text, fel):
	"""Ce scrie omul in campul serverului -> (gazda, port, dosar): '\\\\NAS\\Filme' (Windows), 'smb://nas/filme',
	'nas:/export' (NFS), 'ftp://server:2121/filme', 'https://server/dav/'."""
	t = (text or u"").strip()
	port = 0
	dosar = u""
	if t.startswith(u"\\\\"):
		parti = [p for p in t.strip(u"\\").split(u"\\") if p]
		return (parti[0] if parti else u""), 0, u"/".join(parti[1:])
	m = re.match(r"^([a-z]+)://([^/]+)(/.*)?$", t, re.I)
	if m:
		gazda = m.group(2)
		dosar = (m.group(3) or u"").strip(u"/")
		if "@" in gazda:
			gazda = gazda.rsplit("@", 1)[1]
		if re.match(r"^.+:\d+$", gazda):
			gazda, p = gazda.rsplit(":", 1)
			port = int(p)
		return gazda, port, dosar
	if fel == "nfs" and ":" in t:
		gazda, dosar = t.split(":", 1)
		return gazda, 0, dosar.strip(u"/")
	if "/" in t:
		gazda, dosar = t.split("/", 1)
		return gazda, 0, dosar.strip(u"/")
	return t, 0, u""


def curata(date, vechi=None):
	"""Datele unui loc venite din ecran sau din pagina -> (loc, cod eroare sau "", text eroare sau "").
	Campurile: nume, fel, gazda (si adresa intreaga a unui server DLNA), port, dosar, utilizator, pornire, citire,
	tls_oricare (un certificat facut acasa la FTPS sau WebDAV HTTPS)."""
	vechi = vechi or {}
	fel = _scurt(date.get("fel", vechi.get("fel", u"")), 10)
	if fel not in FELURI:
		return None, "fel", _t("Alege felul locului.")
	nume = _scurt(date.get("nume", vechi.get("nume", u"")), 60)
	gazda = _scurt(date.get("gazda", vechi.get("gazda", u"")), 300)
	dosar = _scurt(date.get("dosar", vechi.get("dosar", u"")), 400).replace(u"\\", u"/").strip(u"/")
	try:
		port = int(date.get("port", vechi.get("port", 0)) or 0)
	except (TypeError, ValueError):
		port = -1
	if fel == "dlna":
		from Components import HdsReteaProtocoale as P
		if not P.adresaHttpBuna(gazda):
			return None, "gazda", _t("Adresa serverului media nu este bună. Folosește Caută în casă.")
	else:
		g, p, d = desparteGazda(gazda, fel)
		gazda = g
		if p:
			port = p
		if d and not dosar:
			dosar = d
		if not gazdaBuna(gazda):
			return None, "gazda", _t("Scrie numele sau adresa serverului, de pildă 192.168.1.20 sau NAS.")
	if port < 0 or port > 65535:
		return None, "port", _t("Portul trebuie să fie un număr între 1 și 65535 (0 pentru cel obișnuit).")
	if fel == "smb" and not dosar:
		return None, "dosar", _t("Scrie numele dosarului partajat de pe server, de pildă Filme.")
	if fel == "nfs" and not dosar:
		return None, "dosar", _t("Scrie dosarul exportat de server, de pildă volume1/filme.")
	if u".." in dosar.split(u"/"):
		return None, "dosar", _t("Dosarul nu poate conține '..'.")
	utilizator = _scurt(date.get("utilizator", vechi.get("utilizator", u"")), 120)
	if any(c in utilizator for c in u"\x00\r\n,"):
		return None, "utilizator", _t("Numele de utilizator nu poate conține virgule sau rânduri noi.")
	if not nume:
		nume = (dosar.rsplit(u"/", 1)[-1] if dosar and fel != "dlna" else u"") or gazda
		if fel == "dlna":
			nume = vechi.get("nume") or _t("Server media")
	nume = re.sub(u"[\x00-\x1f/\\\\]", u" ", nume).strip()[:60] or textFel(fel, True)

	def bifa(cheie):
		v = date.get(cheie, vechi.get(cheie, False))
		return v in (True, 1, "1", "true", "on", "da")
	loc = {
		"id": vechi.get("id") or u"",
		"nume": nume,
		"fel": fel,
		"gazda": gazda,
		"port": port,
		"dosar": dosar if fel != "dlna" else (dosar or u"0"),
		"utilizator": utilizator if fel not in ("dlna", "nfs") else u"",
		"pornire": bifa("pornire") and fel in FELURI_MONTATE,
		"citire": bifa("citire") and fel in FELURI_MONTATE,
		"tls_oricare": bifa("tls_oricare") and fel in ("ftps", "webdavs"),
		"inregistrari": bool(vechi.get("inregistrari")) and fel in FELURI_MONTATE,
		"viteza": vechi.get("viteza") or 0,
		"control": vechi.get("control") or u"",
	}
	if fel == "dlna":
		# adresa ContentDirectory aflata la cautarea in casa: pastrata, daca e pe acelasi aparat ca descrierea
		from Components import HdsReteaProtocoale as P
		from urllib.parse import urlsplit
		control = _scurt(date.get("control") or u"", 300)
		if control and P.adresaHttpBuna(control, urlsplit(gazda).hostname):
			loc["control"] = control
	# un loc mutat pe alt server sau alt dosar trebuie verificat din nou pentru inregistrari
	if vechi and any(vechi.get(k) != loc[k] for k in ("fel", "gazda", "dosar", "port")):
		loc["inregistrari"] = False
		loc["viteza"] = 0
		loc["control"] = u""
	return loc, "", u""


def punctPentru(loc, alte=()):
	"""/media/net/<nume fara spatii si semne>, deosebit de punctele altor locuri."""
	baza = re.sub(r"[^A-Za-z0-9_\-]+", "-", _faraDiacritice(loc.get("nume") or u"")).strip("-")[:32] or "loc"
	punct = DOSAR_MONTARI + "/" + baza
	n = 2
	while punct in alte:
		punct = "%s/%s-%d" % (DOSAR_MONTARI, baza, n)
		n += 1
	return punct


def _faraDiacritice(text):
	import unicodedata
	text = text.replace(u"ș", u"s").replace(u"ş", u"s").replace(u"ț", u"t").replace(u"ţ", u"t") \
		.replace(u"Ș", u"S").replace(u"Ş", u"S").replace(u"Ț", u"T").replace(u"Ţ", u"T")
	return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _scrieAtomic(cale, octeti, mod=0o600):
	dosar = os.path.dirname(cale)
	if dosar and not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	nou = cale + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mod)
	try:
		os.write(fd, octeti)
		os.fsync(fd)
	finally:
		os.close(fd)
	os.chmod(nou, mod)
	os.replace(nou, cale)


class Locuri(object):
	"""Lista locurilor omului, in CALE_LOCURI (JSON, 0600, fara parole)."""

	def __init__(self, cale=CALE_LOCURI):
		self.cale = cale
		self._memorie = None

	def lista(self):
		try:
			st = os.stat(self.cale)
		except OSError:
			self._memorie = None
			return []
		semn = (st.st_size, int(st.st_mtime * 1000))
		if self._memorie is not None and self._memorie[0] == semn:
			return [dict(l) for l in self._memorie[1]]
		try:
			if st.st_size > 512 * 1024:
				raise ValueError("prea mare")
			with open(self.cale, "r", encoding="utf-8") as f:
				date = json.load(f)
			locuri = []
			for l in (date.get("locuri") or [])[:MAX_LOCURI]:
				loc, cod, _text = curata(l, l)
				if loc is not None and l.get("id"):
					loc["id"] = _scurt(l["id"], 16)
					locuri.append(loc)
		except (OSError, IOError, ValueError, AttributeError, TypeError) as e:
			_jurnal("lista locurilor nu se poate citi: %s" % e.__class__.__name__)
			locuri = []
		self._memorie = (semn, locuri)
		return [dict(l) for l in locuri]

	def scrie(self, locuri):
		text = json.dumps({"v": 1, "locuri": locuri}, ensure_ascii=False, sort_keys=True, indent=1)
		_scrieAtomic(self.cale, text.encode("utf-8"), 0o600)
		self._memorie = None

	def dupaId(self, ident):
		for l in self.lista():
			if l["id"] == ident:
				return l
		return None

	def pune(self, loc):
		"""Adauga (fara id) sau inlocuieste locul. -> locul cu id."""
		locuri = self.lista()
		if not loc.get("id"):
			if len(locuri) >= MAX_LOCURI:
				raise ValueError("prea multe")
			folosite = set(l["id"] for l in locuri)
			while True:
				ident = os.urandom(4).hex() if hasattr(bytes, "hex") else "%08x" % int(time.time())
				if ident not in folosite:
					break
			loc = dict(loc, id=ident)
			locuri.append(loc)
		else:
			locuri = [loc if l["id"] == loc["id"] else l for l in locuri]
		self.scrie(locuri)
		return loc

	def sterge(self, ident):
		locuri = self.lista()
		rest = [l for l in locuri if l["id"] != ident]
		if len(rest) != len(locuri):
			self.scrie(rest)
			return True
		return False


# ------------------------------------------------------------------ parolele (criptate cu identitatea receptorului)

ETICHETA_PAROLE = u"retea-locuri|"


class Parole(object):
	"""{id loc: parola} in CALE_PAROLE, cu plicul cheilor de traducere si o identitate proprie (eticheta + identitatea
	receptorului), deci o cheie de criptare deosebita de a cheilor. `identitate` se poate da (probele)."""

	def __init__(self, cale=CALE_PAROLE, identitate=None):
		self.cale = cale
		self._identitate = identitate

	def _modul(self):
		from Components import HdsTraducereSubtitrari as T
		return T

	def identitate(self):
		if self._identitate is not None:
			return self._identitate
		ident = self._modul().identitateAparat()
		return (ETICHETA_PAROLE + ident) if ident else u""

	def citeste(self):
		try:
			if os.stat(self.cale).st_size > 256 * 1024:
				return {}
			with open(self.cale, "rb") as f:
				octeti = f.read()
		except (OSError, IOError):
			return {}
		ident = self.identitate()
		if not ident:
			return {}
		date = self._modul().decripteaza(octeti, ident)
		if not isinstance(date, dict):
			_jurnal("parolele locurilor nu se pot citi pe acest receptor")
			return {}
		return dict((k, v) for k, v in date.items() if isinstance(k, str) and isinstance(v, str))

	def are(self, ident):
		return ident in self.citeste()

	def parola(self, ident):
		return self.citeste().get(ident)

	def pune(self, ident, parola):
		"""-> True daca s-a scris; False cand identitatea receptorului nu se poate citi."""
		ident_cripto = self.identitate()
		if not ident_cripto:
			return False
		date = self.citeste()
		if parola is None:
			date.pop(ident, None)
		else:
			date[ident] = parola[:MAX_PAROLA]
		_scrieAtomic(self.cale, self._modul().cripteaza(date, ident_cripto), 0o600)
		return True

	def pastreaza(self, idei):
		"""Sterge parolele locurilor care nu mai exista."""
		date = self.citeste()
		rest = dict((k, v) for k, v in date.items() if k in idei)
		if len(rest) != len(date) and self.identitate():
			_scrieAtomic(self.cale, self._modul().cripteaza(rest, self.identitate()), 0o600)


# ------------------------------------------------------------------ montarile (citite din /proc/mounts)

def _montari(cale="/proc/mounts"):
	"""{punct: (sursa, fel)} pentru montarile de sub DOSAR_MONTARI."""
	rez = {}
	try:
		with open(os.environ.get("HDS_PROBA_MOUNTS") or cale, "r", encoding="utf-8", errors="surrogateescape") as f:
			for rand in f:
				p = rand.split()
				if len(p) >= 3:
					punct = p[1].replace("\\040", " ").rstrip("/")
					if punct.startswith(DOSAR_MONTARI + "/"):
						rez[punct] = (p[0].replace("\\040", " "), p[2])
	except (OSError, IOError):
		pass
	return rez


def sursaAsteptata(loc):
	if loc["fel"] == "smb":
		parti = [p for p in loc.get("dosar", u"").split(u"/") if p]
		return u"//" + loc["gazda"] + u"/" + u"/".join(parti)
	if loc["fel"] == "nfs":
		return loc["gazda"] + u":/" + loc.get("dosar", u"").strip(u"/")
	return u""


# ------------------------------------------------------------------ starea (pe firul enigma2; firele scriu sub lacat)

class Stare(object):
	"""Starea in memorie: pentru fiecare loc {stare, cod, mesaj, vers, punct, timp}; lucrarile in curs."""
	NEMONTAT = "nemontat"
	MONTAT = "montat"
	LUCREAZA = "lucreaza"
	EROARE = "eroare"

	def __init__(self):
		self.lacat = threading.RLock()
		self.locuri = {}
		self.puncte = {}         # punct -> id, pentru montarile facute de noi
		self.cautare = {"in_lucru": False, "gasite": [], "timp": 0, "cod": ""}

	def pune(self, ident, **campuri):
		with self.lacat:
			s = self.locuri.setdefault(ident, {"stare": self.NEMONTAT, "cod": "", "mesaj": u"", "vers": u"",
				"punct": u"", "timp": 0, "lucrare": u""})
			s.update(campuri)
			s["timp"] = time.time()
			return dict(s)

	def a(self, ident):
		with self.lacat:
			return dict(self.locuri.get(ident) or {"stare": self.NEMONTAT, "cod": "", "mesaj": u"", "vers": u"",
				"punct": u"", "timp": 0, "lucrare": u""})


_STARE = Stare()
_LOCURI = [None]
_PAROLE = [None]


def locuri():
	if _LOCURI[0] is None:
		_LOCURI[0] = Locuri()
	return _LOCURI[0]


def parole():
	if _PAROLE[0] is None:
		_PAROLE[0] = Parole()
	return _PAROLE[0]


def stare():
	return _STARE


def punctLoc(loc, montari=None):
	"""Punctul de montare al locului: cel tinut minte, cel gasit in /proc/mounts dupa sursa, sau unul nou."""
	s = _STARE.a(loc["id"])
	if s.get("punct"):
		return s["punct"]
	montari = _montari() if montari is None else montari
	sursa = sursaAsteptata(loc)
	for punct, (src, fel) in montari.items():
		if src == sursa:
			return punct
	ocupate = set(montari) | set(_STARE.puncte)
	return punctPentru(loc, ocupate)


def esteMontat(loc, montari=None):
	"""(montat, punct) dupa /proc/mounts (numai text, fara atingerea serverului)."""
	if loc.get("fel") not in FELURI_MONTATE:
		return False, u""
	montari = _montari() if montari is None else montari
	punct = punctLoc(loc, montari)
	if punct in montari:
		return True, punct
	sursa = sursaAsteptata(loc)
	for p, (src, fel) in montari.items():
		if src == sursa:
			return True, p
	return False, punct


def descrie(loc, montari=None, cu_parola=None):
	"""Un loc pentru ecran si pagina: fara parola, cu starea si textele."""
	montat, punct = esteMontat(loc, montari)
	s = _STARE.a(loc["id"])
	if montat:
		st = Stare.MONTAT
	elif s["stare"] in (Stare.LUCREAZA, Stare.EROARE):
		st = s["stare"]
	else:
		st = Stare.NEMONTAT
	if cu_parola is None:
		cu_parola = parole().are(loc["id"]) if loc.get("utilizator") else False
	adresa = loc["gazda"] if loc["fel"] == "dlna" else _adresaAfisata(loc)
	return {
		"id": loc["id"],
		"nume": loc["nume"],
		"fel": loc["fel"],
		"fel_text": textFel(loc["fel"]),
		"fel_scurt": textFel(loc["fel"], True),
		"gazda": loc["gazda"],
		"port": loc.get("port") or 0,
		"dosar": loc.get("dosar") or u"",
		"adresa": adresa,
		"utilizator": loc.get("utilizator") or u"",
		"are_parola": bool(cu_parola),
		"pornire": bool(loc.get("pornire")),
		"citire": bool(loc.get("citire")),
		"tls_oricare": bool(loc.get("tls_oricare")),
		"montabil": loc["fel"] in FELURI_MONTATE,
		"montat": montat,
		"punct": punct if loc["fel"] in FELURI_MONTATE else u"",
		"stare": st,
		"lucrare": s.get("lucrare") or u"",
		"mesaj": s.get("mesaj") or u"",
		"cod": s.get("cod") or u"",
		"vers": s.get("vers") or u"",
		"inregistrari": bool(loc.get("inregistrari")),
		"viteza": loc.get("viteza") or 0,
		"stare_text": textStare(loc, st, s),
		# in randul listei de pe televizor: fara mesajul intreg al erorii (el sta in detalii)
		"stare_scurt": _t("Nu s-a deschis") if st == Stare.EROARE else textStare(loc, st, s),
	}


def _adresaAfisata(loc):
	fel = loc["fel"]
	port = loc.get("port") or 0
	gazda = loc["gazda"]
	if port and port != PORT_IMPLICIT.get(fel):
		gazda = u"%s:%d" % (gazda, port)
	dosar = loc.get("dosar") or u""
	if fel == "smb":
		return u"\\\\" + gazda + (u"\\" + dosar.replace(u"/", u"\\") if dosar else u"")
	if fel == "nfs":
		return gazda + u":/" + dosar
	schema = {"ftp": u"ftp", "ftps": u"ftps", "webdav": u"http", "webdavs": u"https"}.get(fel, fel)
	return u"%s://%s/%s" % (schema, gazda, dosar)


def textStare(loc, st, s):
	if st == Stare.MONTAT:
		if loc.get("inregistrari"):
			return _t("Montat, folosit și pentru înregistrări")
		return _t("Montat")
	if st == Stare.LUCREAZA:
		return {
			"monteaza": _t("Se montează..."),
			"demonteaza": _t("Se demontează..."),
			"viteza": _t("Se verifică scrierea și viteza..."),
		}.get(s.get("lucrare"), _t("Se lucrează..."))
	if st == Stare.EROARE:
		return s.get("mesaj") or textEroare(s.get("cod"))
	if loc["fel"] in FELURI_MONTATE:
		return _t("Nemontat")
	return _t("Gata de răsfoit")


# ------------------------------------------------------------------ lucrarile pe fire, culese pe firul enigma2

_rezultate = []
_lacat_rez = threading.Lock()
_ceas = [None]
SINCRON = [False]       # probele de pe PC: totul pe loc, fara fire


def _culege():
	with _lacat_rez:
		gata = list(_rezultate)
		del _rezultate[:]
	for functie, rez in gata:
		try:
			if functie is not None:
				functie(rez)
		except Exception as e:
			_jurnal("raspunsul unei lucrari: %s" % e)
	with _STARE.lacat:
		ramase = any(s.get("stare") == Stare.LUCREAZA for s in _STARE.locuri.values()) or _STARE.cautare["in_lucru"]
	with _lacat_rez:
		ramase = ramase or bool(_rezultate) or _FIRE[0] > 0
	if not ramase and _ceas[0] is not None:
		_ceas[0].stop()


_FIRE = [0]


def lucreaza(tinta, argumente=(), gata=None, nume="HdsStocareRetea"):
	"""Ruleaza tinta(*argumente) pe un fir; gata(rezultat) se cheama pe firul enigma2 (eTimer). In probe, pe loc."""
	if SINCRON[0]:
		try:
			rez = tinta(*argumente)
		except Exception as e:
			rez = {"ok": False, "cod": "alta", "detaliu": str(e)}
		if gata is not None:
			gata(rez)
		return

	def fir():
		try:
			rez = tinta(*argumente)
		except Exception as e:      # nimic nu scapa dintr-un fir
			_jurnal("%s: %s" % (nume, e))
			rez = {"ok": False, "cod": "alta"}
		with _lacat_rez:
			_rezultate.append((gata, rez))
			_FIRE[0] -= 1
	with _lacat_rez:
		_FIRE[0] += 1
	t = threading.Thread(target=fir, name=nume)
	t.daemon = True
	t.start()
	try:
		from enigma import eTimer
		if _ceas[0] is None:
			_ceas[0] = eTimer()
			_ceas[0].callback.append(_culege)
		_ceas[0].start(150, False)
	except ImportError:
		pass


def _proces(mod, cerere, termen):
	"""Ruleaza Components/HdsReteaUnealta.py intr-un proces copil, cererea (cu parola) pe intrarea standard."""
	import subprocess
	py = PYTHON if os.path.exists(PYTHON) else "python3"
	cod = ("import sys; sys.path.insert(0, %r); from Components import HdsReteaUnealta as U; "
		"sys.exit(U.main(sys.argv[1:]))" % DOSAR_PYTHON)
	try:
		p = subprocess.Popen([py, "-c", cod, mod], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL, close_fds=True)
	except OSError as e:
		_jurnal("procesul copil nu porneste: %s" % e.__class__.__name__)
		return {"ok": False, "cod": "alta"}
	try:
		iesire, _x = p.communicate((json.dumps(cerere) + "\n").encode("utf-8"), timeout=termen)
	except subprocess.TimeoutExpired:
		# un mount(2) blocat in nucleu de un server care tace nu se poate opri: copilul primeste semnalul, iar
		# asteptarea lui ramane pe un fir separat; locul trece pe "termen", nu ramane "se monteaza" la nesfarsit
		try:
			p.kill()
		except OSError:
			pass
		fir = threading.Thread(target=p.wait, name="HdsStocareRetea-copil")
		fir.daemon = True
		fir.start()
		return {"ok": False, "cod": "termen"}
	try:
		return json.loads(iesire.decode("utf-8", "replace").strip().splitlines()[-1])
	except (ValueError, IndexError):
		return {"ok": False, "cod": "alta"}


PROCES = [_proces]      # probele inlocuiesc procesul copil


def _cerereMontare(loc, parola, punct):
	utilizator = loc.get("utilizator") or u""
	domeniu = u""
	if u"\\" in utilizator:
		domeniu, utilizator = utilizator.split(u"\\", 1)
	extra = u""
	if loc.get("port") and loc["fel"] == "smb" and loc["port"] != 445:
		extra = u"port=%d" % loc["port"]
	elif loc.get("port") and loc["fel"] == "nfs" and loc["port"] != 2049:
		extra = u"port=%d" % loc["port"]
	return {"fel": loc["fel"], "gazda": loc["gazda"], "dosar": loc.get("dosar") or u"", "punct": punct,
		"utilizator": utilizator, "domeniu": domeniu, "parola": parola or u"", "citire": bool(loc.get("citire")),
		"port": int(loc.get("port") or 0), "extra": extra}


def _adaugaInListe(punct, nume):
	"""Locul montat apare in playerul de fisiere si in alegerea dosarelor ca orice disc (Components/Harddisk.py).
	Fara evenimentul "add": ascultatorii lui (cautarea fisierelor media) ar parcurge tot serverul."""
	try:
		from Components.Harddisk import harddiskmanager
		harddiskmanager.addMountedPartition(punct, nume)
	except Exception:
		pass


def _scoateDinListe(punct):
	try:
		from Components.Harddisk import harddiskmanager
		harddiskmanager.removeMountedPartition(punct)
	except Exception:
		pass


def monteaza(ident, gata=None):
	"""Monteaza locul (smb, nfs) pe un fir, prin procesul copil. gata(rezultat) pe firul enigma2:
	{ok, cod, mesaj, punct, vers}."""
	loc = locuri().dupaId(ident)
	if loc is None or loc["fel"] not in FELURI_MONTATE:
		rez = {"ok": False, "cod": "lipsa" if loc is None else "nesuportat"}
		rez["mesaj"] = textEroare(rez["cod"])
		if gata:
			gata(rez)
		return False
	montat, punct = esteMontat(loc)
	if montat:
		_STARE.pune(ident, stare=Stare.MONTAT, punct=punct, cod="", mesaj=u"")
		# montat inainte (de pilda inaintea unei reporniri a interfetei): din nou in Player media si sub paza
		_adaugaInListe(punct, loc["nume"])
		_pornestePaza()
		rez = {"ok": True, "punct": punct, "deja": True}
		if gata:
			gata(rez)
		return True
	parola = None
	if loc.get("utilizator"):
		parola = parole().parola(ident)
		if parola is None:
			_STARE.pune(ident, stare=Stare.EROARE, cod="parola", mesaj=textEroare("parola"))
			rez = {"ok": False, "cod": "parola", "mesaj": textEroare("parola")}
			if gata:
				gata(rez)
			return False
	with _STARE.lacat:
		if _STARE.a(ident).get("stare") == Stare.LUCREAZA:
			# o montare, demontare sau proba pornita inainte (din ecran sau din web): raspunsul ei vine la cine a pornit-o
			if gata:
				gata({"ok": False, "cod": "ocupat", "mesaj": _t("Se lucrează...")})
			return False
		_STARE.pune(ident, stare=Stare.LUCREAZA, lucrare="monteaza", punct=punct, cod="", mesaj=u"")
		_STARE.puncte[punct] = ident
	cerere = _cerereMontare(loc, parola, punct)

	def gataMontare(rez):
		if rez.get("ok"):
			_STARE.pune(ident, stare=Stare.MONTAT, lucrare=u"", vers=rez.get("vers") or u"", cod="", mesaj=u"")
			_adaugaInListe(punct, loc["nume"])
			_jurnal("montat %s (%s %s) in %s" % (ident, loc["fel"], rez.get("vers") or "", punct))
			_pornestePaza()
		else:
			cod = rez.get("cod") or "alta"
			_STARE.pune(ident, stare=Stare.EROARE, lucrare=u"", cod=cod, mesaj=textEroare(cod))
			with _STARE.lacat:
				_STARE.puncte.pop(punct, None)
			_jurnal("montarea %s (%s) nu a mers: %s, errno %s" % (ident, loc["fel"], cod, rez.get("errno")))
		rez = dict(rez, punct=punct, mesaj=u"" if rez.get("ok") else textEroare(rez.get("cod") or "alta"))
		if gata:
			gata(rez)
	lucreaza(lambda: PROCES[0]("monteaza", cerere, TERMEN_MONTARE_S), (), gataMontare, "HdsStocareRetea-monteaza")
	return True


def demonteaza(ident, gata=None):
	loc = locuri().dupaId(ident)
	if loc is None:
		if gata:
			gata({"ok": False, "cod": "lipsa", "mesaj": textEroare("lipsa")})
		return False
	montat, punct = esteMontat(loc)
	if not montat:
		_STARE.pune(ident, stare=Stare.NEMONTAT, cod="", mesaj=u"", lucrare=u"")
		if gata:
			gata({"ok": True, "deja": True})
		return True
	_STARE.pune(ident, stare=Stare.LUCREAZA, lucrare="demonteaza")

	def gataDemontare(rez):
		if rez.get("ok"):
			_STARE.pune(ident, stare=Stare.NEMONTAT, lucrare=u"", cod="", mesaj=u"", punct=u"")
			with _STARE.lacat:
				_STARE.puncte.pop(punct, None)
			_scoateDinListe(punct)
			_jurnal("demontat %s din %s" % (ident, punct))
		else:
			cod = rez.get("cod") or "alta"
			_STARE.pune(ident, stare=Stare.EROARE, lucrare=u"", cod=cod, mesaj=textEroare(cod))
		if gata:
			gata(dict(rez, mesaj=u"" if rez.get("ok") else textEroare(rez.get("cod") or "alta")))
	lucreaza(lambda: PROCES[0]("demonteaza", {"punct": punct}, TERMEN_DEMONTARE_S), (), gataDemontare,
		"HdsStocareRetea-demonteaza")
	return True


def verificaInregistrari(ident, gata=None):
	"""Proba de scriere si viteza pe locul montat (procesul copil). Bun = cel putin VITEZA_MINIMA MB/s la scriere:
	atunci locul intra in lista discurilor pentru inregistrari (HdsLocInregistrari.candidati)."""
	loc = locuri().dupaId(ident)
	if loc is None or loc["fel"] not in FELURI_MONTATE:
		if gata:
			gata({"ok": False, "cod": "nesuportat", "mesaj": _t("Înregistrările merg numai pe locurile SMB și NFS "
				"montate.")})
		return False
	montat, punct = esteMontat(loc)
	if not montat:
		if gata:
			gata({"ok": False, "cod": "nemontat", "mesaj": _t("Montează întâi locul.")})
		return False
	if loc.get("citire"):
		if gata:
			gata({"ok": False, "cod": "citire", "mesaj": textEroare("citire")})
		return False
	_STARE.pune(ident, stare=Stare.LUCREAZA, lucrare="viteza")

	def gataViteza(rez):
		_STARE.pune(ident, stare=Stare.MONTAT, lucrare=u"")
		l = locuri().dupaId(ident)
		if l is None:
			return
		if rez.get("ok"):
			v = float(rez.get("scriere") or 0)
			l["viteza"] = v
			l["inregistrari"] = v >= VITEZA_MINIMA
			locuri().pune(l)
			rez = dict(rez, mesaj=textViteza(v))
		else:
			l["inregistrari"] = False
			locuri().pune(l)
			rez = dict(rez, mesaj=textEroare(rez.get("cod") or "alta"))
		if gata:
			gata(rez)
	lucreaza(lambda: PROCES[0]("viteza", {"punct": punct}, TERMEN_VITEZA_S), (), gataViteza,
		"HdsStocareRetea-viteza")
	return True


def textViteza(v):
	"""Fraza dupa proba de viteza (MB/s la scriere)."""
	if v < VITEZA_MINIMA:
		return _t("Locul scrie cu %s MB/s: prea încet pentru înregistrări (trebuie cel puțin %s MB/s). Încearcă un "
			"cablu de rețea în locul Wi-Fi-ului sau alt server.") % (_numar(v), _numar(VITEZA_MINIMA))
	if v < VITEZA_BUNA:
		return _t("Locul scrie cu %s MB/s: ajunge pentru o înregistrare HD odată. Pentru canale 4K sau două "
			"înregistrări deodată e mai sigur un disc legat la receptor.") % _numar(v)
	return _t("Locul scrie cu %s MB/s: ajunge pentru înregistrări, și pentru canale 4K.") % _numar(v)


def _numar(v):
	return (u"%.1f" % v).replace(u".", u",")


numar = _numar


def marime(n):
	"""4,3 GB / 734 MB / 12 kB (cu virgula), sau "" pentru o marime necunoscuta."""
	if n is None:
		return u""
	n = float(n)
	for unitate in (u"B", u"kB", u"MB", u"GB"):
		if n < 1024:
			break
		n /= 1024.0
	else:
		unitate = u"TB"
	if unitate == u"B":
		return u"%d B" % n
	text = (u"%.1f" % n) if n < 10 else (u"%d" % round(n))
	return u"%s %s" % (text.replace(u".", u","), unitate)


def durata(secunde):
	"""1:45:03 sau 3:07."""
	try:
		s = int(secunde)
	except (TypeError, ValueError):
		return u""
	if s >= 3600:
		return u"%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)
	return u"%d:%02d" % (s // 60, s % 60)


def pentruInregistrari(punct):
	"""Pentru HdsLocInregistrari.candidati (numai text si memorie, pe firul enigma2): (id, nume, fel) daca punctul e un
	loc montat de noi si verificat pentru inregistrari, altfel None."""
	punct = (punct or u"").rstrip("/")
	if not punct.startswith(DOSAR_MONTARI + "/"):
		return None
	montari = _montari()
	if punct not in montari:
		return None
	for loc in locuri().lista():
		if loc["fel"] not in FELURI_MONTATE or not loc.get("inregistrari"):
			continue
		montat, p = esteMontat(loc, montari)
		if montat and p == punct:
			return loc["id"], loc["nume"], loc["fel"]
	return None


# ------------------------------------------------------------------ paza locurilor montate

_PAZA = [None]


def _pornestePaza():
	if SINCRON[0]:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _PAZA[0] is None:
		_PAZA[0] = eTimer()
		_PAZA[0].callback.append(_pazeste)
	if not _PAZA[0].isActive():
		_PAZA[0].start(PAZA_S * 1000, False)


_neraspuns = {}


def _pazeste():
	"""La PAZA_S secunde, cat e montat ceva: o legatura TCP scurta spre serverul fiecarui loc montat (pe un fir). Un
	server care nu raspunde de doua ori la rand: locul se demonteaza lenes, cu un mesaj."""
	montari = _montari()
	de_verificat = []
	for loc in locuri().lista():
		if loc["fel"] in FELURI_MONTATE:
			montat, punct = esteMontat(loc, montari)
			if montat:
				de_verificat.append(loc)
	if not de_verificat:
		if _PAZA[0] is not None:
			_PAZA[0].stop()
		return

	def verifica():
		rez = []
		for loc in de_verificat:
			port = loc.get("port") or PORT_IMPLICIT[loc["fel"]]
			rez.append((loc, _raspundeTcp(loc["gazda"], port, 4.0)))
		return rez

	def gataPaza(rez):
		if not isinstance(rez, list):
			return
		for loc, bun in rez:
			if bun:
				_neraspuns.pop(loc["id"], None)
				continue
			_neraspuns[loc["id"]] = _neraspuns.get(loc["id"], 0) + 1
			if _neraspuns[loc["id"]] >= 2:
				_neraspuns.pop(loc["id"], None)
				_jurnal("serverul locului %s nu raspunde: demontat" % loc["id"])
				demonteaza(loc["id"], lambda r, n=loc["nume"]: _anunta(_t("Serverul locului %s nu mai răspunde, așa "
					"că locul a fost demontat. Îl poți monta din nou din Locuri din rețea.") % n))
	lucreaza(verifica, (), gataPaza, "HdsStocareRetea-paza")


def _raspundeTcp(gazda, port, termen):
	try:
		s = socket.create_connection((gazda, int(port)), termen)
		s.close()
		return True
	except (OSError, ValueError):
		return False


def _anunta(text):
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddNotification(MessageBox, text, MessageBox.TYPE_INFO, timeout=15)
	except Exception:
		_jurnal(text)


def reiaMontarile(montari=None):
	"""Dupa o repornire a interfetei (nu a receptorului) montarile raman in nucleu, dar starea din memorie nu: locurile
	montate se pun din nou in Player media, cu starea si paza lor. Numai text (/proc/mounts), fara atingerea serverului.
	-> cate locuri montate."""
	montari = _montari() if montari is None else montari
	n = 0
	for l in locuri().lista():
		if l["fel"] not in FELURI_MONTATE:
			continue
		montat, punct = esteMontat(l, montari)
		if montat:
			_STARE.pune(l["id"], stare=Stare.MONTAT, punct=punct, cod="", mesaj=u"")
			with _STARE.lacat:
				_STARE.puncte[punct] = l["id"]
			_adaugaInListe(punct, l["nume"])
			n += 1
	if n:
		_pornestePaza()
	return n


def laPornire():
	"""Chemat o data la pornirea enigma2: locurile montate inainte (repornirea interfetei) se iau din nou in seama;
	locurile cu "Montat si dupa repornire" se monteaza in fundal, dupa INTARZIERE_PORNIRE_S, pe rand. Nimic altceva nu
	se monteaza si nu se cauta singur."""
	try:
		reiaMontarile()
	except Exception as e:
		_jurnal("montarile de dinainte: %s" % e)
	try:
		lista = [l for l in locuri().lista() if l.get("pornire") and l["fel"] in FELURI_MONTATE]
	except Exception:
		lista = []
	if not lista:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	ceas = eTimer()

	def porneste():
		for l in lista:
			monteaza(l["id"])
	ceas.callback.append(porneste)
	ceas.start(INTARZIERE_PORNIRE_S * 1000, True)
	_PORNIRE[0] = ceas


_PORNIRE = [None]


# ------------------------------------------------------------------ cautarea in casa (pe un fir, la cerere)

TERMEN_CAUTARE_S = 3.5


def cautaInCasa(gata=None):
	"""SSDP (serverele DLNA), NetBIOS (calculatoarele cu Windows si NAS-urile cu fisiere partajate) si mDNS (_smb,
	_nfs, _webdav, _ftp), numai in reteaua receptorului. Rezultatul: {ok, gasite: [{fel, nume, gazda, port}], cod}."""
	with _STARE.lacat:
		if _STARE.cautare["in_lucru"]:
			return False
		_STARE.cautare.update(in_lucru=True, cod="", timp=time.time())

	def gataCautare(rez):
		with _STARE.lacat:
			_STARE.cautare.update(in_lucru=False, gasite=rez.get("gasite") or [], cod=rez.get("cod") or "",
				timp=time.time())
		if gata:
			gata(rez)
	lucreaza(CAUTARE[0], (), gataCautare, "HdsStocareRetea-cautare")
	return True


def rezultatCautare():
	with _STARE.lacat:
		c = dict(_STARE.cautare)
	stiute = set((l["fel"], l["gazda"]) for l in locuri().lista())
	c["gasite"] = [dict(g, adaugat=(g["fel"], g["gazda"]) in stiute, fel_text=textFel(g["fel"]))
		for g in c.get("gasite") or []]
	return c


def _cautare():
	from Components import HdsAparateRetea as A
	from Components import HdsReteaProtocoale as P
	import select
	r = A.reteaua()
	if r is None:
		return {"ok": False, "cod": "retea", "gasite": []}
	adrese, _prefix = A.adrese_de_intrebat(r)
	socluri = []
	ssdp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	ssdp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
	try:
		ssdp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(r["ip"]))
	except OSError:
		pass
	ssdp.bind(("", 0))
	socluri.append(ssdp)
	nb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	nb.bind(("", 0))
	socluri.append(nb)
	md = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	md.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
	try:
		md.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(r["ip"]))
	except OSError:
		pass
	md.bind(("", 0))
	socluri.append(md)
	locatii = {}
	netbios = {}
	mdns = []
	try:
		for _k in range(2):
			ssdp.sendto(P.intrebareSsdp(), P.SSDP)
		md.sendto(P.intrebareMdns(), P.MDNS)
		ident = int(time.time()) & 0x7FFF
		for k, ip in enumerate(adrese):
			try:
				nb.sendto(A.intrebare_netbios(ident), (ip, A.PORT_NETBIOS))
			except OSError:
				pass
			if k % A.PACHETE_PE_RAND == A.PACHETE_PE_RAND - 1:
				time.sleep(A.PAUZA_S)
		sfarsit = time.time() + TERMEN_CAUTARE_S
		while True:
			ramas = sfarsit - time.time()
			if ramas <= 0:
				break
			gata, _w, _x = select.select(socluri, [], [], ramas)
			for s in gata:
				try:
					date, (ip, _port) = s.recvfrom(65535)
				except OSError:
					continue
				if not A.in_retea(ip, r["retea"], r["prefix"]):
					continue
				if s is ssdp:
					antete = P.raspunsSsdp(date)
					loc = antete.get("location") or u""
					if P.adresaHttpBuna(loc, ip) and "mediaserver" in (antete.get("st") or u"").lower():
						locatii[loc] = ip
				elif s is nb:
					nume, fisiere = P.numeNetbios(date)
					if fisiere:
						netbios[ip] = nume
				else:
					mdns.append((P.raspunsMdns(date), ip))
	finally:
		for s in socluri:
			s.close()
	gasite = []
	for loc, ip in sorted(locatii.items())[:20]:
		d = _descriere(loc)
		if d:
			gasite.append({"fel": "dlna", "nume": d["nume"], "gazda": loc, "port": 0, "ip": ip,
				"control": d["control"]})
	for ip, nume in sorted(netbios.items()):
		gasite.append({"fel": "smb", "nume": nume or ip, "gazda": ip, "port": 0, "ip": ip})
	for rasp, ip in mdns:
		for s in P.serviciiMdns([rasp], ip):
			if not A.in_retea(s["gazda"], r["retea"], r["prefix"]):
				continue
			if any(g["fel"] == s["fel"] and g.get("ip", g["gazda"]) == s["gazda"] for g in gasite):
				continue
			port = s["port"] if s["port"] != PORT_IMPLICIT.get(s["fel"]) else 0
			gasite.append({"fel": s["fel"], "nume": s["nume"], "gazda": s["gazda"], "port": port, "ip": s["gazda"]})
	return {"ok": True, "gasite": gasite}


CAUTARE = [_cautare]


def _descriere(locatie):
	from Components import HdsReteaProtocoale as P
	try:
		date, _antete = _http("GET", locatie, termen=3.0, maxim=512 * 1024)
	except Exception:
		return None
	return P.descriereAparat(date, locatie)


# ------------------------------------------------------------------ HTTP mic (descrierea UPnP, Browse, PROPFIND)

def _http(metoda, adresa, corp=None, antete=None, termen=TERMEN_RETEA_S, maxim=4 * 1024 * 1024, tls_oricare=False,
		stare_ok=(200, 207)):
	"""-> (corpul, antetele raspunsului); IOError cu .stare pentru un raspuns HTTP nereusit."""
	import http.client
	from urllib.parse import urlsplit
	p = urlsplit(adresa)
	cale = p.path or "/"
	if p.query:
		cale += "?" + p.query
	if p.scheme == "https":
		import ssl
		ctx = ssl.create_default_context()
		if tls_oricare:
			ctx.check_hostname = False
			ctx.verify_mode = ssl.CERT_NONE
		c = http.client.HTTPSConnection(p.hostname, p.port or 443, timeout=termen, context=ctx)
	else:
		c = http.client.HTTPConnection(p.hostname, p.port or 80, timeout=termen)
	try:
		a = {"User-Agent": "HDSatelit", "Connection": "close"}
		a.update(antete or {})
		c.request(metoda, cale, body=corp, headers=a)
		r = c.getresponse()
		date = r.read(maxim + 1)
		if len(date) > maxim:
			raise IOError("raspuns prea mare")
		if r.status not in stare_ok:
			e = IOError("HTTP %d" % r.status)
			e.stare = r.status
			e.antete = dict((k.lower(), v) for k, v in r.getheaders())
			raise e
		return date, dict((k.lower(), v) for k, v in r.getheaders())
	finally:
		c.close()


def _codDinExceptie(e):
	"""O exceptie de retea -> codul mesajului."""
	import ssl
	stare = getattr(e, "stare", None)
	if stare in (401, 403):
		return "acces"
	if stare == 404:
		return "dosar"
	if isinstance(e, ssl.SSLError) or "CERTIFICATE" in str(e).upper():
		return "tls"
	if isinstance(e, socket.timeout):
		return "termen"
	if isinstance(e, socket.gaierror):
		return "nume"
	if isinstance(e, (ConnectionRefusedError, ConnectionResetError)) or getattr(e, "errno", None) in (
			errno.EHOSTUNREACH, errno.ENETUNREACH, errno.EHOSTDOWN, errno.ECONNREFUSED):
		return "server"
	try:
		import ftplib
		if isinstance(e, ftplib.error_perm):
			t = str(e)
			if t.startswith("530"):
				return "acces"
			if t.startswith("550"):
				return "dosar"
	except ImportError:
		pass
	return "alta"


# ------------------------------------------------------------------ rasfoirea (pe un fir)

def felFisier(nume):
	ext = os.path.splitext(nume or u"")[1].lower()
	if ext in EXTENSII_FILM:
		return "film"
	if ext in EXTENSII_MUZICA:
		return "muzica"
	if ext in EXTENSII_SUBTITRARI:
		return "subtitrare"
	return "altul"


def felIntrare(i):
	"""film, muzica, subtitrare sau altul: dupa clasa si tipul date de serverul DLNA, altfel dupa extensie."""
	clasa = (i.get("clasa") or u"").lower()
	mime = (i.get("mime") or u"").lower()
	if clasa.startswith("object.item.videoitem") or mime.startswith("video/"):
		return "film"
	if clasa.startswith("object.item.audioitem") or mime.startswith("audio/"):
		return "muzica"
	return felFisier(i.get("nume"))


def _ordoneaza(intrari):
	"""Dosarele intai, apoi filmele si muzica, dupa nume (fara deosebire de litere mari); celelalte fisiere nu se
	arata (subtitrarile se iau singure langa film)."""
	# dosarele de subtitrari (Subs...) nu se arata: subtitrarile din ele se iau singure langa film
	dosare = sorted([i for i in intrari if i.get("dosar") and i["nume"].lower() not in SUBDOSARE_SUBTITRARI],
		key=lambda i: i["nume"].lower())
	fisiere = []
	for i in intrari:
		if not i.get("dosar"):
			i["fel"] = felIntrare(i)
			if i["fel"] in ("film", "muzica"):
				fisiere.append(i)
	return dosare + sorted(fisiere, key=lambda i: i["nume"].lower())


def caleBuna(cale):
	"""O cale din interiorul locului, venita din ecran sau din pagina: fara '..', fara inceput absolut iesit din loc."""
	return ".." not in [p for p in (cale or u"").replace(u"\\", u"/").split(u"/")]


def _listeazaLocal(punct, cale):
	baza = os.path.join(punct, cale.strip("/")) if cale.strip("/") else punct
	# o legatura simbolica de pe server (NFS) care duce in afara locului nu se urmeaza
	real = os.path.realpath(baza)
	if real != os.path.realpath(punct) and not real.startswith(os.path.realpath(punct).rstrip("/") + "/"):
		raise OSError(errno.ENOENT, "in afara locului")
	rez = []
	for n in os.listdir(baza):
		if n.startswith("."):
			continue
		c = os.path.join(baza, n)
		try:
			st = os.stat(c)
		except OSError:
			continue
		import stat as S
		dosar = S.S_ISDIR(st.st_mode)
		rez.append({"nume": n, "dosar": dosar, "marime": None if dosar else st.st_size, "data": int(st.st_mtime),
			"cale": (cale.rstrip("/") + "/" + n).lstrip("/")})
	return rez


def _ftp(loc, parola):
	import ftplib
	if loc["fel"] == "ftps":
		import ssl
		ctx = ssl.create_default_context()
		if loc.get("tls_oricare"):
			ctx.check_hostname = False
			ctx.verify_mode = ssl.CERT_NONE
		ftp = ftplib.FTP_TLS(timeout=TERMEN_RETEA_S, context=ctx)
	else:
		ftp = ftplib.FTP(timeout=TERMEN_RETEA_S)
	ftp.encoding = "latin-1"     # numele vin ca octeti; decodate de HdsReteaProtocoale.decodeazaNume
	ftp.connect(loc["gazda"], int(loc.get("port") or 21))
	ftp.login(loc.get("utilizator") or "anonymous", parola or "")
	if loc["fel"] == "ftps":
		ftp.prot_p()
	return ftp


def _caleFtp(loc, cale):
	"""Calea pe server, ca text latin-1 (octetii trimisi asa cum au venit): dosarul scris de om in UTF-8, numele
	primite de la server neschimbate."""
	dosar = (loc.get("dosar") or u"").encode("utf-8").decode("latin-1")
	parti = [p for p in dosar.split(u"/") + (cale or u"").split(u"/") if p]
	return u"/" + u"/".join(parti)


def _listeazaFtp(loc, parola, cale):
	from Components import HdsReteaProtocoale as P
	ftp = _ftp(loc, parola)
	try:
		drum = _caleFtp(loc, cale)
		rez = []
		try:
			for nume, fapte in ftp.mlsd(drum, ["type", "size", "modify"]):
				i = P.randMlsd(nume, fapte)
				if i:
					rez.append(i)
		except ftplib_erori():
			randuri = []
			ftp.cwd(drum)
			ftp.retrlines("LIST", randuri.append)
			rez = [i for i in (P.randLista(r) for r in randuri) if i]
		for i in rez:
			i["brut"] = i["nume"]
			i["nume"] = P.decodeazaNume(i["nume"].encode("latin-1", "replace"))
			i["cale"] = (cale.rstrip("/") + "/" + i["brut"]).lstrip("/")
		return rez
	finally:
		try:
			ftp.quit()
		except Exception:
			ftp.close()


def ftplib_erori():
	import ftplib
	return (ftplib.error_perm, ftplib.error_reply)


def _adresaWebdav(loc, cale=u"", nume=None):
	from Components import HdsReteaProtocoale as P
	schema = "https" if loc["fel"] == "webdavs" else "http"
	port = loc.get("port") or 0
	gazda = loc["gazda"] + (":%d" % port if port and port != PORT_IMPLICIT[loc["fel"]] else "")
	dosar = u"/".join(p for p in ((loc.get("dosar") or u"") + u"/" + (cale or u"")).split(u"/") if p)
	return "%s://%s%s" % (schema, gazda, P.caleWebdav(dosar, nume))


def _cerereAutentificata(loc, parola, metoda, adresa, corp=None, antete=None, maxim=4 * 1024 * 1024):
	"""O cerere WebDAV cu Basic (pe https, sau cand serverul nu cere altceva) sau Digest dupa provocarea serverului."""
	from Components import HdsReteaProtocoale as P
	from urllib.parse import urlsplit
	a = dict(antete or {})
	if loc.get("utilizator"):
		a["Authorization"] = P.antetBasic(loc["utilizator"], parola or u"")
	try:
		return _http(metoda, adresa, corp, a, tls_oricare=loc.get("tls_oricare"), maxim=maxim)
	except IOError as e:
		if getattr(e, "stare", None) != 401 or not loc.get("utilizator"):
			raise
		p = P.provocareDigest((getattr(e, "antete", None) or {}).get("www-authenticate", ""))
		if p is None:
			raise
		a["Authorization"] = P.antetDigest(p, metoda, urlsplit(adresa).path or "/", loc["utilizator"], parola or u"")
		return _http(metoda, adresa, corp, a, tls_oricare=loc.get("tls_oricare"), maxim=maxim)


def _listeazaWebdav(loc, parola, cale):
	from Components import HdsReteaProtocoale as P
	from urllib.parse import urlsplit
	adresa = _adresaWebdav(loc, cale)
	date, _a = _cerereAutentificata(loc, parola, "PROPFIND", adresa, P.CERERE_PROPFIND,
		{"Depth": "1", "Content-Type": "application/xml; charset=utf-8"})
	intrari = P.raspunsPropfind(date, urlsplit(adresa).path)
	if intrari is None:
		raise IOError("raspuns PROPFIND de neinteles")
	for i in intrari:
		i["cale"] = (cale.rstrip("/") + "/" + i["nume"]).lstrip("/")
	return intrari


def controlDlna(loc):
	"""Adresa ContentDirectory a serverului DLNA (din descrierea lui)."""
	d = _descriere(loc["gazda"])
	if not d:
		raise IOError("server media fara ContentDirectory")
	return d["control"]


def _listeazaDlna(loc, obiect):
	from Components import HdsReteaProtocoale as P
	from urllib.parse import urlsplit
	control = loc.get("control") or controlDlna(loc)
	if not P.adresaHttpBuna(control, urlsplit(loc["gazda"]).hostname):
		raise IOError("ContentDirectory pe alta gazda")
	rez = []
	start = 0
	while len(rez) < P.MAX_INTRARI:
		corp, actiune = P.cerereBrowse(obiect or loc.get("dosar") or "0", start, 200)
		date, _a = _http("POST", control, corp, {"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": actiune})
		r = P.raspunsBrowse(date)
		if r is None:
			raise IOError("raspuns Browse de neinteles")
		text, numar, total = r
		# adresele date de server (filmul, subtitrarile) numai spre acelasi aparat, nu spre receptor sau alta gazda
		gazda = urlsplit(loc["gazda"]).hostname
		bucata = []
		for i in P.didl(text, control):
			if i["adresa"] and not P.adresaHttpBuna(i["adresa"], gazda):
				continue
			i["subtitrari"] = [a for a in i["subtitrari"] if P.adresaHttpBuna(a, gazda)]
			bucata.append(i)
		rez += bucata
		start += numar
		if numar <= 0 or start >= total:
			break
	intrari = []
	for i in rez:
		intrari.append({"nume": i["titlu"], "dosar": i["fel"] == "dosar", "marime": i["marime"], "data": None,
			"cale": i["id"], "adresa": i["adresa"], "subtitrari": i["subtitrari"], "durata": i["durata"],
			"mime": i["mime"], "clasa": i["clasa"]})
	return intrari


def listeaza(ident, cale=u"", gata=None):
	"""Continutul unui dosar al locului, pe un fir. gata({ok, cod, mesaj, intrari: [{nume, dosar, marime, data, cale,
	adresa, subtitrari}], cale}). La smb si nfs locul se monteaza intai, daca nu e montat."""
	loc = locuri().dupaId(ident)
	if loc is None:
		if gata:
			gata({"ok": False, "cod": "lipsa", "mesaj": textEroare("lipsa"), "intrari": []})
		return False
	if loc["fel"] != "dlna" and not caleBuna(cale):
		if gata:
			gata({"ok": False, "cod": "cerere", "mesaj": textEroare("cerere"), "intrari": []})
		return False
	if loc["fel"] in FELURI_MONTATE:
		montat, punct = esteMontat(loc)
		if not montat:
			def dupaMontare(r):
				if r.get("ok"):
					listeaza(ident, cale, gata)
				elif gata:
					gata(dict(r, intrari=[]))
			return monteaza(ident, dupaMontare)
	parola = parole().parola(ident) if loc.get("utilizator") else None
	if loc.get("utilizator") and parola is None and loc["fel"] not in FELURI_MONTATE:
		if gata:
			gata({"ok": False, "cod": "parola", "mesaj": textEroare("parola"), "intrari": []})
		return False

	def lucru():
		try:
			if loc["fel"] in FELURI_MONTATE:
				intrari = _listeazaLocal(esteMontat(loc)[1], cale)
			elif loc["fel"] in ("ftp", "ftps"):
				intrari = _listeazaFtp(loc, parola, cale)
			elif loc["fel"] in ("webdav", "webdavs"):
				intrari = _listeazaWebdav(loc, parola, cale)
			else:
				intrari = _listeazaDlna(loc, cale)
		except Exception as e:
			cod = _codDinExceptie(e)
			if loc["fel"] in FELURI_MONTATE and isinstance(e, OSError) and e.errno == errno.ENOENT:
				cod = "dosar"
			_jurnal("rasfoirea locului %s: %s (%s)" % (ident, cod, e.__class__.__name__))
			return {"ok": False, "cod": cod, "mesaj": textEroare(cod), "intrari": [], "cale": cale}
		return {"ok": True, "intrari": _ordoneaza(intrari), "toate": intrari, "cale": cale}
	lucreaza(lucru, (), gata, "HdsStocareRetea-listeaza")
	return True


# ------------------------------------------------------------------ exporturile NFS (pentru alegerea dosarului)

def exporturiNfs(gazda, termen=5.0):
	"""Dosarele exportate de un server NFS (RPC MOUNT EXPORT pe TCP) -> [dosar]."""
	from Components import HdsReteaProtocoale as P

	def apel(port, cerere, xid):
		s = socket.create_connection((gazda, port), termen)
		try:
			s.settimeout(termen)
			s.sendall(cerere)
			date = P.fragmenteRpc(s.recv)
		finally:
			s.close()
		return P.corpRaspunsRpc(date or b"", xid)
	xid = int(time.time() * 1000) & 0x7FFFFFFF
	corp = apel(P.PORT_PORTMAP, P.cerereGetport(xid, P.PROG_MOUNT, 3), xid)
	port = P.raspunsGetport(corp) if corp is not None else None
	if not port:
		raise IOError("serverul nu are serviciul de montare NFS 3")
	corp = apel(port, P.cerereExport(xid + 1), xid + 1)
	if corp is None:
		raise IOError("lista exporturilor nu a venit")
	return [d for d, _g in P.raspunsExport(corp)]


def dosareServer(fel, gazda, utilizator=u"", ident=None, parola=None, gata=None):
	"""Dosarele pe care le da un server (exporturile NFS; partajarile SMB prin Components/HdsReteaSmb, daca exista),
	pe un fir. gata({ok, cod, mesaj, dosare})."""
	if parola is None and ident:
		parola = parole().parola(ident)

	def lucru():
		try:
			if fel == "nfs":
				return {"ok": True, "dosare": exporturiNfs(gazda)}
			if fel == "smb":
				from Components import HdsReteaSmb
				return {"ok": True, "dosare": HdsReteaSmb.partajari(gazda, utilizator, parola or u"")}
		except ImportError:
			return {"ok": False, "cod": "nesuportat", "mesaj": textEroare("nesuportat"), "dosare": []}
		except Exception as e:
			cod = getattr(e, "cod", None) or _codDinExceptie(e)
			return {"ok": False, "cod": cod, "mesaj": textEroare(cod), "dosare": []}
		return {"ok": False, "cod": "nesuportat", "mesaj": textEroare("nesuportat"), "dosare": []}
	lucreaza(lucru, (), gata, "HdsStocareRetea-dosare")
	return True


# ------------------------------------------------------------------ redarea (filmul si subtitrarile de langa el)

def _cheieFilm(text):
	import hashlib
	return hashlib.sha1(text.encode("utf-8", "surrogateescape")).hexdigest()[:12]


def subtitrariLangaFilm(nume_film, intrari):
	"""Din intrarile dosarului: fisierele de subtitrare cu acelasi inceput de nume ca filmul (film.srt, film.ro.srt,
	film_en.srt) si dosarele de subtitrari (Subs, Subtitles...). -> (fisiere, dosare)."""
	baza = os.path.splitext(nume_film)[0].lower()
	fisiere = []
	dosare = []
	for i in intrari:
		n = i["nume"]
		if i.get("dosar"):
			if n.lower() in SUBDOSARE_SUBTITRARI:
				dosare.append(i)
			continue
		if felFisier(n) != "subtitrare":
			continue
		if n.lower().startswith(baza) and len(fisiere) < MAX_FISIERE_SUBTITRARI:
			fisiere.append(i)
	return fisiere, dosare


def _descarca(loc, parola, intrare, tinta):
	"""Un fisier mic (subtitrare) in `tinta`, cel mult MAX_SUBTITRARE octeti."""
	if loc["fel"] == "dlna" or intrare.get("adresa"):
		date, _a = _http("GET", intrare["adresa"], maxim=MAX_SUBTITRARE)
	elif loc["fel"] in ("webdav", "webdavs"):
		date, _a = _cerereAutentificata(loc, parola, "GET", _adresaWebdav(loc, os.path.dirname(intrare["cale"]),
			os.path.basename(intrare["cale"])), maxim=MAX_SUBTITRARE)
	else:
		import io
		ftp = _ftp(loc, parola)
		try:
			buf = io.BytesIO()

			def scrie(b):
				if buf.tell() + len(b) > MAX_SUBTITRARE:
					raise IOError("subtitrare prea mare")
				buf.write(b)
			ftp.retrbinary("RETR " + _caleFtp(loc, intrare["cale"]), scrie)
			date = buf.getvalue()
		finally:
			try:
				ftp.quit()
			except Exception:
				ftp.close()
	dosar = os.path.dirname(tinta)
	if not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	with open(tinta, "wb") as f:
		f.write(date)


def pregatesteSubtitrari(loc, parola, film, intrari, cale_dosar):
	"""Pe fir: subtitrarile filmului (de langa el, din Subs, date de serverul DLNA) descarcate in
	DOSAR_SUBTITRARI/<cheie>/, langa un nume virtual al filmului; HdsSubtitrariFilm le gaseste acolo ca pe cele de langa
	un film de pe stick. -> calea virtuala a filmului."""
	cheie = _cheieFilm(loc["id"] + u"|" + (film.get("cale") or film.get("adresa") or film["nume"]))
	dosar = os.path.join(DOSAR_SUBTITRARI, cheie)
	nume_film = re.sub(r"[/\x00]", "_", film["nume"])
	if loc["fel"] == "dlna" and felFisier(nume_film) != "film" and felIntrare(film) == "film":
		nume_film += _extensieDlna(film)
	virtual = os.path.join(dosar, nume_film)
	if not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	baza = os.path.splitext(nume_film)[0]
	puse = 0
	if loc["fel"] == "dlna":
		for k, adresa in enumerate((film.get("subtitrari") or [])[:MAX_FISIERE_SUBTITRARI]):
			ext = os.path.splitext(adresa.split("?")[0])[1].lower()
			if ext not in EXTENSII_SUBTITRARI:
				ext = ".srt"
			try:
				_descarca(loc, parola, {"adresa": adresa}, os.path.join(dosar, "%s.%d%s" % (baza, k + 1, ext)))
				puse += 1
			except Exception as e:
				_jurnal("subtitrarea DLNA nu s-a descarcat: %s" % e.__class__.__name__)
		return virtual
	fisiere, dosare = subtitrariLangaFilm(film["nume"], intrari)
	for i in fisiere:
		try:
			_descarca(loc, parola, i, os.path.join(dosar, i["nume"]))
			puse += 1
		except Exception as e:
			_jurnal("o subtitrare nu s-a descarcat: %s" % e.__class__.__name__)
	for d in dosare[:2]:
		try:
			if loc["fel"] in ("ftp", "ftps"):
				sub = _listeazaFtp(loc, parola, d["cale"])
			else:
				sub = _listeazaWebdav(loc, parola, d["cale"])
		except Exception:
			continue
		for i in [x for x in sub if not x.get("dosar") and felFisier(x["nume"]) == "subtitrare"][:MAX_FISIERE_SUBTITRARI]:
			try:
				_descarca(loc, parola, i, os.path.join(dosar, d["nume"], i["nume"]))
				puse += 1
			except Exception:
				pass
	return virtual


def _extensieDlna(film):
	mime = (film.get("mime") or u"").lower()
	for m, e in (("matroska", ".mkv"), ("mp4", ".mp4"), ("avi", ".avi"), ("mpeg2", ".mpg"), ("mp2t", ".ts"),
			("mpeg", ".mpg"), ("quicktime", ".mov"), ("webm", ".webm"), ("wmv", ".wmv"), ("x-ms-asf", ".wmv")):
		if m in mime:
			return e
	return ".mkv"


class Punte(object):
	"""Puntea locala (procesul copil HdsReteaUnealta punte) pentru filmul de acum; una singura deodata."""

	def __init__(self):
		self.proces = None
		self.port = 0
		self.jeton = u""
		self.lacat = threading.Lock()

	def porneste(self, tinte):
		"""Pe fir: porneste puntea pentru tinte (cu parola) si da (port, jeton) sau ridica IOError."""
		import subprocess
		self.opreste()
		jeton = os.urandom(12).hex()
		py = PYTHON if os.path.exists(PYTHON) else "python3"
		cod = ("import sys; sys.path.insert(0, %r); from Components import HdsReteaUnealta as U; "
			"sys.exit(U.main(sys.argv[1:]))" % DOSAR_PYTHON)
		p = subprocess.Popen([py, "-c", cod, "punte"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL, close_fds=True)
		p.stdin.write((json.dumps({"jeton": jeton, "tinte": tinte}) + "\n").encode("utf-8"))
		p.stdin.flush()
		# primul rand (portul), cu termen: citit pe un fir, ca un copil care nu raspunde sa nu tina firul acesta
		rand = []
		citit = threading.Event()

		def citeste():
			try:
				rand.append(p.stdout.readline())
			finally:
				citit.set()
		threading.Thread(target=citeste, name="HdsStocareRetea-punte").start()
		if not citit.wait(15) or not rand:
			p.kill()
			raise IOError("puntea nu a pornit")
		try:
			rasp = json.loads(rand[0].decode("utf-8", "replace"))
		except ValueError:
			rasp = {}
		if not rasp.get("ok"):
			p.kill()
			raise IOError("puntea nu a pornit")
		with self.lacat:
			self.proces, self.port, self.jeton = p, int(rasp["port"]), jeton
		return self.port, jeton

	def opreste(self):
		with self.lacat:
			p, self.proces = self.proces, None
		if p is not None:
			try:
				p.stdin.close()
			except Exception:
				pass
			try:
				p.terminate()
				p.wait(3)
			except Exception:
				try:
					p.kill()
				except Exception:
					pass


PUNTE = Punte()


def adresaPunte(port, jeton, index, nume):
	from urllib.parse import quote
	return "http://127.0.0.1:%d/%s/%d/%s" % (port, jeton, index, quote(nume.encode("utf-8"), safe=""))


def _tintaPunte(loc, parola, intrare):
	if loc["fel"] in ("ftp", "ftps"):
		return {"fel": loc["fel"], "gazda": loc["gazda"], "port": loc.get("port") or 21, "utilizator":
			loc.get("utilizator") or u"", "parola": parola or u"", "tls": loc["fel"] == "ftps",
			"cale": _caleFtp(loc, intrare["cale"]), "fara_verificare": bool(loc.get("tls_oricare"))}
	from urllib.parse import urlsplit
	adresa = _adresaWebdav(loc, os.path.dirname(intrare["cale"]), os.path.basename(intrare["cale"]))
	p = urlsplit(adresa)
	return {"fel": loc["fel"], "gazda": p.hostname, "port": p.port or (443 if p.scheme == "https" else 80),
		"tls": p.scheme == "https", "utilizator": loc.get("utilizator") or u"", "parola": parola or u"",
		"cale": p.path, "fara_verificare": bool(loc.get("tls_oricare"))}


def pregatesteRedarea(ident, intrare, intrari, gata):
	"""Pe un fir: adresa de redare a fisierului si subtitrarile de langa el. gata({ok, cod, mesaj, adresa, nume,
	virtual, marime}). smb/nfs: calea din locul montat (subtitrarile le gaseste playerul singur)."""
	loc = locuri().dupaId(ident)
	if loc is None:
		gata({"ok": False, "cod": "lipsa", "mesaj": textEroare("lipsa")})
		return
	parola = parole().parola(ident) if loc.get("utilizator") else None

	def lucru():
		try:
			if loc["fel"] in FELURI_MONTATE:
				montat, punct = esteMontat(loc)
				if not montat:
					return {"ok": False, "cod": "nemontat", "mesaj": _t("Locul nu mai este montat.")}
				return {"ok": True, "adresa": os.path.join(punct, intrare["cale"]), "nume": intrare["nume"],
					"virtual": u"", "marime": intrare.get("marime")}
			virtual = u""
			if felIntrare(intrare) == "film":
				try:
					virtual = pregatesteSubtitrari(loc, parola, intrare, intrari or [], u"")
				except Exception as e:
					_jurnal("subtitrarile de langa film: %s" % e.__class__.__name__)
			if loc["fel"] == "dlna":
				return {"ok": True, "adresa": intrare["adresa"], "nume": intrare["nume"], "virtual": virtual,
					"marime": intrare.get("marime")}
			port, jeton = PUNTE.porneste([_tintaPunte(loc, parola, intrare)])
			return {"ok": True, "adresa": adresaPunte(port, jeton, 0, intrare["nume"]), "nume": intrare["nume"],
				"virtual": virtual, "marime": intrare.get("marime")}
		except Exception as e:
			cod = _codDinExceptie(e)
			_jurnal("pregatirea redarii pe locul %s: %s" % (ident, e.__class__.__name__))
			return {"ok": False, "cod": cod, "mesaj": textEroare(cod)}
	lucreaza(lucru, (), gata, "HdsStocareRetea-reda")


def referinta(rez):
	"""eServiceReference pentru filmul pregatit (inregistrarile .ts dintr-un loc montat ca inregistrari)."""
	from enigma import eServiceReference
	adresa = rez["adresa"]
	if adresa.startswith("/") and adresa.lower().endswith(".ts"):
		ref = eServiceReference("1:0:0:0:0:0:0:0:0:0:" + adresa)
	else:
		ref = eServiceReference(4097, 0, adresa)
	ref.setName(rez.get("nume") or os.path.basename(adresa))
	if rez.get("virtual"):
		try:
			from Components import HdsSubtitrariFilm
			HdsSubtitrariFilm.inregistreazaRetea(adresa, rez["virtual"], rez.get("marime") or 0)
		except Exception as e:
			_jurnal("subtitrarile filmului din retea nu se pot lega: %s" % e)
	return ref


def deschidePeTv(sesiune, rez):
	"""Pornit din pagina web: filmul pregatit (pregatesteRedarea) in playerul de filme de pe televizor. In playerul
	deschis se schimba filmul; peste bara principala sau peste ecranele Locuri din retea se deschide playerul; peste
	alt ecran nu (omul ar pierde ce face acolo). -> (reusit, text)."""
	if sesiune is None:
		return False, _t("Receptorul nu este pregătit. Încearcă peste câteva secunde.")
	try:
		from Screens.InfoBar import InfoBar, MoviePlayer
		ref = referinta(rez)
		dialog = sesiune.current_dialog
		if isinstance(dialog, MoviePlayer):
			dialog.movieSelected(ref)
		elif isinstance(dialog, InfoBar) or dialog.__class__.__name__.startswith("HdsLocRetea") or \
				dialog.__class__.__name__ == "HdsLocuriRetea":
			sesiune.openWithCallback(lambda *a: dupaRedare(), MoviePlayer, ref)
		else:
			PUNTE.opreste()
			return False, _t("Pe televizor e deschis alt ecran. Închide-l, apoi pornește din nou filmul.")
	except Exception as e:
		_jurnal("filmul nu a pornit pe televizor: %s" % e)
		PUNTE.opreste()
		return False, _t("Filmul nu a pornit pe televizor.")
	return True, _t("Filmul pornește pe televizor.")


def dupaRedare():
	"""Filmul s-a oprit: puntea se inchide, subtitrarile descarcate se sterg."""
	PUNTE.opreste()
	try:
		from Components import HdsSubtitrariFilm
		HdsSubtitrariFilm.uitaRetea()
	except Exception:
		pass
	lucreaza(_curataSubtitrari, (), None, "HdsStocareRetea-curata")


def _curataSubtitrari():
	import shutil
	if os.path.isdir(DOSAR_SUBTITRARI):
		shutil.rmtree(DOSAR_SUBTITRARI, ignore_errors=True)
	return {"ok": True}


# ------------------------------------------------------------------ adaugarea, schimbarea, stergerea

def salveaza(date, parola=None, ident=None):
	"""Adauga (ident None) sau schimba un loc. parola: None = neschimbata, "" = stearsa, text = noua.
	-> (loc descris sau None, text eroare)."""
	L = locuri()
	vechi = L.dupaId(ident) if ident else None
	if ident and vechi is None:
		return None, textEroare("lipsa")
	loc, cod, text = curata(date, vechi)
	if loc is None:
		return None, text
	if vechi:
		montat, _p = esteMontat(vechi)
		if montat and any(vechi.get(k) != loc.get(k) for k in ("fel", "gazda", "dosar", "port", "utilizator",
				"citire")):
			return None, _t("Demontează întâi locul, apoi schimbă-l.")
	try:
		loc = L.pune(loc)
	except ValueError:
		return None, _t("Sunt prea multe locuri. Șterge unul pe care nu îl mai folosești.")
	except (OSError, IOError) as e:
		_jurnal("locul nu se poate scrie: %s" % e.__class__.__name__)
		return None, _t("Locul nu s-a putut salva pe receptor.")
	if parola is not None and loc.get("utilizator"):
		if not parole().pune(loc["id"], parola if parola else None):
			return descrie(loc), _t("Locul s-a salvat, dar parola nu se poate păstra pe acest receptor.")
	elif not loc.get("utilizator") and parole().are(loc["id"]):
		parole().pune(loc["id"], None)
	return descrie(loc), u""


def sterge(ident, gata=None):
	"""Demonteaza (daca e montat) si sterge locul si parola lui."""
	loc = locuri().dupaId(ident)
	if loc is None:
		if gata:
			gata({"ok": False, "cod": "lipsa", "mesaj": textEroare("lipsa")})
		return False

	def dupa(r):
		if not r.get("ok") and not r.get("deja"):
			if gata:
				gata(r)
			return
		locuri().sterge(ident)
		try:
			parole().pune(ident, None)
		except Exception:
			pass
		with _STARE.lacat:
			_STARE.locuri.pop(ident, None)
		if gata:
			gata({"ok": True})
	if loc["fel"] in FELURI_MONTATE and esteMontat(loc)[0]:
		return demonteaza(ident, dupa)
	dupa({"ok": True, "deja": True})
	return True


def toate():
	"""Locurile descrise, pentru ecran si pagina."""
	montari = _montari()
	try:
		cu_parola = parole().citeste()
	except Exception:
		cu_parola = {}
	return [descrie(l, montari, l["id"] in cu_parola) for l in locuri().lista()]


def dinCautare(g):
	"""Datele unui loc nou din ce a gasit cautarea in casa (pentru ecranul de adaugare)."""
	return {"fel": g.get("fel"), "nume": g.get("nume") or u"", "gazda": g.get("gazda") or u"",
		"port": g.get("port") or 0, "dosar": u"0" if g.get("fel") == "dlna" else u"", "control": g.get("control") or u""}

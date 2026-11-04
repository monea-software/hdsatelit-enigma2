# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvSurse: sursele de televiziune prin internet ale omului (playlist M3U, cont Xtream, portal Stalker, lista demo),
# canalele lor si buchetele din care lista de canale le arata. Aceeasi logica pentru ecranul de pe televizor
# (Screens/IptvSetup.py) si pentru pagina web /iptv (HdsWebControl/internet_web.py). Imaginea e numai un client: omul isi
# pune contul lui, de la furnizorul lui; aici nu exista nicio lista de furnizori, de portaluri sau de conturi.
#
# UNDE STAU DATELE
#   /etc/enigma2/hds_iptv/            dosar 0700
#     surse.json                      0600: sursele, cu adresele si parolele lor (numai aici, nu in settings)
#     canale-<sursa>.json             0600: canalele sursei, [cheie, nume, grupa, adresa]; adresa poate avea parola in ea
#   /etc/enigma2/userbouquet.hdsiptv.tv         radacina 'IPTV' (legata din bouquets.tv, ca nucleul sa o incarce)
#   /etc/enigma2/subbouquet.hdsiptv_*.tv        cate o grupa a furnizorului
# Numele cu 'iptv' e cu scop: Components/HdsAsistentaBroker.LOCURI_OPRITE il inchide pentru Asistenta. Copia setarilor ia
# dosarul cu tot etc/enigma2, cu drepturile lui, si il pune si pe alt receptor: abonamentul e al
# omului, nu al aparatului.
#
# BUCHETELE NU AU PAROLE. Un canal din buchet arata asa:
#   4097:0:1:SID:TSID:ONID:NS:0:0:0:http%3a//127.0.0.1%3a8897/tv/<sursa>/<cheie>:
# Fluxul il aduce la pornire Components/HdsIptvAdrese.py, numai pe 127.0.0.1, cu antetele cerute. Asa parola nu
# ajunge in buchete, in lastservice, in istoric, in eServiceMP3::playbin uri sau in copiile trimise, iar un canal pus de om
# in Favorite ramane valabil cand furnizorul isi reface lista: <sursa> nu se schimba cu parola, iar <cheie> e identificatorul
# furnizorului (Xtream stream_id, Stalker id, M3U tvg-id si numele). SID, TSID, ONID si NS vin din aceleasi doua valori,
# deci sunt la fel la orice refacere si pot purta EPG fara sa se schimbe favoritele.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc ca atare.

import hashlib
import json
import os
import re
import threading
import time
import zlib

try:
	from urllib.parse import urlsplit, parse_qs, unquote
except ImportError:  # Python 2
	from urlparse import urlsplit, parse_qs

DIRECTOR = "/etc/enigma2"
DOSAR = "/etc/enigma2/hds_iptv"
PORT = 8897
MARCAJ_CALE = "127.0.0.1:%d/tv/" % PORT      # o bucata din calea oricarui canal de aici (eticheta IPTV, cautarea)
BUCHET_RADACINA = "userbouquet.hdsiptv.tv"
PREFIX_GRUPA = "subbouquet.hdsiptv_"
NUME_RADACINA = "IPTV"

MAX_SURSE = 20
MAX_CANALE = 30000       # pe sursa: un buchet mai mare ar tine prea mult reincarcarea buchetelor
MAX_GRUPE = 1000
MAX_NUME = 100
MAX_TEXT = 512
MAX_ADRESA = 2048
LUNGIME_RAND = 250       # octeti pe rand de buchet: nucleul citeste cu un tampon de 256

FELURI = ("m3u", "xtream", "stalker", "demo")
SCHEME_SURSA = ("http", "https")
SCHEME_FLUX = ("http", "https", "rtsp", "rtmp", "mms", "udp")
SCHEME_REDIRECT = ("http", "https")           # numai de aici se poate urma o redirectionare HTTP
RADACINI_STICK = ("/media/", "/mnt/", "/autofs/", "/hdd/")
EXTENSII_LISTA = (".m3u", ".m3u8", ".tv")   # .tv: o lista Enigma2 de la furnizor

_MAC = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")
_GAZDA = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-.]{0,251}[A-Za-z0-9])?$")
_CHEIE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_ID_SURSA = re.compile(r"^[0-9a-f]{8}$")

_LACAT = threading.RLock()


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


NUME_FEL = {"m3u": N_("Playlist"), "xtream": N_("Cont"), "stalker": N_("Portal"), "demo": N_("Listă demo")}
T_FARA_HTTPS = N_("Legătura cu acest server nu este criptată, fiindcă furnizorul nu are HTTPS.")


def numeSursa(s):
	"""Numele aratat al unei surse: cel scris de om, altfel numele felului, tradus (in buchet ramane cum era la scriere)."""
	nume = numeCurat(s.get("nume"))
	if nume:
		return nume
	text = NUME_FEL.get(s.get("fel"), NUME_RADACINA)
	try:
		return _(text)
	except NameError:  # probele de pe PC
		return text


# ------------------------------------------------------------------ fisierele

def _cale(nume):
	return os.path.join(DOSAR, nume)


def _caleSurse():
	return _cale("surse.json")


def _caleCanale(sursa_id):
	return _cale("canale-%s.json" % sursa_id)


def _scrie(cale, octeti, mod):
	"""Dintr-o miscare: .nou (copia setarilor il sare), fsync, drepturile, redenumirea. Drepturile se pun inainte de scriere:
	nici o clipa fisierul cu parola nu se poate citi de altii."""
	nou = cale + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mod)
	try:
		with os.fdopen(fd, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.chmod(nou, mod)
		os.replace(nou, cale)
	except Exception:
		try:
			os.unlink(nou)
		except OSError:
			pass
		raise


def _asiguraDosar():
	if not os.path.isdir(DOSAR):
		os.makedirs(DOSAR, 0o700)
	os.chmod(DOSAR, 0o700)


def reparaDrepturi():
	"""Dupa o punere la loc din copie dosarul poate veni 0755, iar pe un stick FAT drepturile nu se pastreaza: 0700 si 0600, la pornire."""
	_asiguraDosar()
	for nume in os.listdir(DOSAR):
		cale = os.path.join(DOSAR, nume)
		if os.path.isfile(cale) and (os.stat(cale).st_mode & 0o777) != 0o600:
			os.chmod(cale, 0o600)


def citesteSurse():
	"""Lista surselor (dict-uri cu tot ce e in fisier, parole incluse: nu se dau mai departe, vezi publica). Un fisier care nu
	se poate citi da o lista goala."""
	try:
		with open(_caleSurse(), encoding="utf-8") as f:
			date = json.load(f)
		rez = date.get("surse") if isinstance(date, dict) else None
		if not isinstance(rez, list):
			return []
		return [s for s in rez if isinstance(s, dict) and s.get("fel") in FELURI and _ID_SURSA.match(str(s.get("id", "")))]
	except (IOError, OSError, ValueError):
		return []


def scrieSurse(surse):
	with _LACAT:
		_asiguraDosar()
		_scrie(_caleSurse(), json.dumps({"surse": surse}, ensure_ascii=False).encode("utf-8"), 0o600)


def areSurse():
	"""Un os.stat: cost mic la umplerea listei de canale."""
	return os.path.isfile(_caleSurse())


def sursa(sursa_id, surse=None):
	for s in (surse if surse is not None else citesteSurse()):
		if s.get("id") == sursa_id:
			return s
	return None


def citesteCanale(sursa_id):
	"""[[cheie, nume, grupa, adresa], ...], [] fara fisier."""
	try:
		with open(_caleCanale(sursa_id), encoding="utf-8") as f:
			date = json.load(f)
		return date if isinstance(date, list) else []
	except (IOError, OSError, ValueError):
		return []


def scrieCanale(sursa_id, canale):
	with _LACAT:
		_asiguraDosar()
		_scrie(_caleCanale(sursa_id), json.dumps(canale, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 0o600)


# ------------------------------------------------------------------ verificarea a ce scrie omul

def textBun(text, maxim=MAX_TEXT):
	"""Fara caractere de control, cel mult `maxim`."""
	return isinstance(text, str) and len(text) <= maxim and not any(ord(c) < 32 or ord(c) == 127 for c in text)


def _fara_spatii(text):
	return not any(c.isspace() for c in text)


def macBun(text):
	return bool(_MAC.match(text or ""))


def portBun(text):
	text = str(text)
	return text.isdigit() and len(text) <= 5 and 0 < int(text) <= 65535


def desparteServer(text):
	"""Ce a scris omul la server: 'gazda', 'gazda:port' sau 'http(s)://gazda[:port][/cale]'. -> (schema sau "", gazda, port sau
	"", cale) sau None daca nu e bun. Fara utilizator si parola in adresa."""
	text = (text or "").strip()
	if not text or not textBun(text) or not _fara_spatii(text):
		return None
	schema = ""
	if "://" in text:
		schema, text = text.split("://", 1)
		schema = schema.lower()
		if schema not in SCHEME_SURSA:
			return None
	gazda, _sep, cale = text.partition("/")
	if "@" in gazda:
		return None
	port = ""
	if ":" in gazda:
		gazda, port = gazda.rsplit(":", 1)
		if not portBun(port):
			return None
	if not _GAZDA.match(gazda):
		return None
	return schema, gazda, port, ("/" + cale.rstrip("/")) if cale.rstrip("/") else ""


def adresaListaBuna(text):
	"""Adresa sau calea unui playlist: numai http, https sau un fisier .m3u / .m3u8 de pe un stick sau disc. -> textul curat sau
	None."""
	text = (text or "").strip()
	if not text or not textBun(text, MAX_ADRESA) or not _fara_spatii(text.replace(" ", "")):
		return None
	if text.startswith("/"):
		if ".." in text.split("/") or not text.lower().endswith(EXTENSII_LISTA):
			return None
		if not text.startswith(RADACINI_STICK):
			return None
		return text
	if not _fara_spatii(text):
		return None
	p = _desparteAdresa(text)
	if p is None or p.scheme not in SCHEME_SURSA or not p.hostname:
		return None
	return text


def _desparteAdresa(text):
	try:
		p = urlsplit(text)
		p.port  # arunca ValueError la un port gresit
		return p
	except ValueError:
		return None


def fluxBun(adresa):
	"""O adresa de flux dintr-o lista (date neincredere): numai schemele permise, fara cale de fisier, fara spatii si caractere
	de control, cu margine la lungime. -> adresa sau None."""
	adresa = (adresa or "").strip()
	if not adresa or len(adresa) > MAX_ADRESA or not textBun(adresa, MAX_ADRESA) or not _fara_spatii(adresa):
		return None
	p = _desparteAdresa(adresa)
	if p is None or p.scheme.lower() not in SCHEME_FLUX or not p.hostname:
		return None
	return adresa


def numeCurat(text, implicit=""):
	"""Un nume dintr-o lista (date neincredere): fara caractere de control, fara semne de marcaj HTML, scurtat dupa octeti. Se
	arata ca text obisnuit, pe televizor si in pagina web."""
	text = "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in str(text or ""))
	text = text.replace("<", " ").replace(">", " ")
	text = " ".join(text.split())
	octeti = text.encode("utf-8")[:MAX_NUME]
	text = octeti.decode("utf-8", "ignore").strip()
	return text or implicit


def gazdaAdresei(adresa):
	"""Ce se poate arata dintr-o adresa: numai gazda, fara cale si parametri (acolo poate fi parola)."""
	if (adresa or "").startswith("/"):
		return adresa
	p = _desparteAdresa(adresa or "")
	return p.hostname if p is not None and p.hostname else ""


def fluxCriptat(adresa):
	return (adresa or "").lower().startswith("https://")


# ------------------------------------------------------------------ identificatorii si referintele

def identitatePlaylist(adresa):
	p = _desparteAdresa(adresa or "")
	if p is None:
		return adresa or "", ""
	q = parse_qs(p.query)
	u = (q.get("username") or q.get("user") or [p.username or ""])[0]
	cale = p.path
	parti = cale.strip("/").split("/")
	if not u and len(parti) >= 3 and parti[0].lower() in ("playlist", "get", "m3u", "live", "movie", "series"):
		u = unquote(parti[1])
		cale = "/" + parti[0]
	# Cu utilizator cunoscut, parola si calea nu definesc abonamentul.
	return ((p.hostname or "").lower() + (":%d" % p.port if p.port else "") + ("" if u else cale), u)


def _amprentaPlaylist(adresa):
	return hashlib.sha256(repr(identitatePlaylist(adresa)).encode("utf-8")).hexdigest()


def _identitatiPlaylist():
	try:
		with open(_cale("identitati.json"), "rb") as f:
			date = json.loads(f.read(128 * 1024))
		return {k: v for k, v in date.items() if re.fullmatch(r"[0-9a-f]{64}", k) and _ID_SURSA.fullmatch(str(v))} if isinstance(date, dict) else {}
	except (OSError, ValueError, TypeError):
		return {}


def _tineIdentitate(s):
	if s.get("fel") != "m3u":
		return
	date = _identitatiPlaylist()
	k = _amprentaPlaylist(s.get("adresa") or "")
	if date.get(k) == s["id"]:
		return
	date.pop(k, None)
	date[k] = s["id"]
	while len(date) > 1024:
		del date[next(iter(date))]
	_asiguraDosar()
	_scrie(_cale("identitati.json"), json.dumps(date).encode("utf-8"), 0o600)


def idSursa(fel, adresa, utilizator=""):
	"""Identificatorul stabil al sursei: acelasi cont are acelasi id si dupa stergere si adaugare din nou sau dupa o parola
	schimbata, deci canalele din Favorite raman. Intr-un playlist parola din adresa nu intra in calcul."""
	baza = adresa or ""
	if fel == "m3u" and not baza.startswith("/"):
		baza, utilizator = identitatePlaylist(baza)
	elif fel in ("xtream", "stalker"):
		d = desparteServer(baza)
		if d is not None:
			baza = "%s:%s%s" % (d[1].lower(), d[2], d[3])
	text = "%s|%s|%s" % (fel, baza, utilizator)
	return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def cheieDinNume(tvg_id, nume, vazute):
	"""Cheia unui canal fara identificator numeric (M3U): din tvg-id si nume, nu din adresa (adresa are parola si se poate
	schimba). Acelasi nume de mai multe ori primeste -2, -3 in ordinea din lista."""
	baza = hashlib.sha1(("%s|%s" % (tvg_id or "", (nume or "").lower())).encode("utf-8")).hexdigest()[:12]
	n = vazute.get(baza, 0) + 1
	vazute[baza] = n
	return baza if n == 1 else "%s-%d" % (baza, n)


def cheieBuna(cheie):
	return bool(_CHEIE.match(cheie or "")) and ".." not in cheie


def caleCanal(sursa_id, cheie):
	return "http://%s%s/%s" % (MARCAJ_CALE, sursa_id, cheie)


def e_cale_iptv(cale):
	"""Calea sau referinta (ca text, si codata) a unui canal de aici."""
	if not cale:
		return False
	return MARCAJ_CALE in cale.replace("%3a", ":").replace("%3A", ":")


_CALE_CANAL = re.compile(r"127\.0\.0\.1:%d/tv/([0-9a-f]{8})/([A-Za-z0-9_.\-]{1,64})" % PORT)


def desparteCale(cale):
	"""(sursa, cheie) din calea sau referinta unui canal de aici, altfel (None, None)."""
	m = _CALE_CANAL.search((cale or "").replace("%3a", ":").replace("%3A", ":"))
	return m.groups() if m else (None, None)


def _codeaza(text):
	rez = []
	for c in text:
		if c == ":" or c == "%" or ord(c) < 32:
			rez.append("%%%02x" % ord(c))
		else:
			rez.append(c)
	return "".join(rez)


def numereCanal(sursa_id, cheie):
	"""(SID, TSID, ONID, NS): din sursa si cheie, la fel la orice refacere. NS are in partea de sus 0xFFFE, locul 'IPTV' din
	lista pe sateliti (Screens/ChannelSelection.HDS_POZ_IPTV)."""
	h = zlib.crc32(("%s/%s" % (sursa_id, cheie)).encode("utf-8")) & 0xFFFFFFFF
	s = int(sursa_id[:8], 16)
	return (h & 0xFFFF) or 1, (h >> 16) or 1, (s & 0xFFFF) or 1, 0xFFFE0000 | ((s >> 16) & 0xFFFF)


def refCanal(sursa_id, cheie, adresa_directa=None):
	"""Referinta canalului, fara nume (numele sta in #DESCRIPTION). adresa_directa: numai pentru un flux care nu se poate
	redirectiona (rtsp, rtmp, mms, udp) si nu are parola in el (adresaDirecta)."""
	sid, tsid, onid, ns = numereCanal(sursa_id, cheie)
	return "4097:0:1:%X:%X:%X:%X:0:0:0:%s:" % (sid, tsid, onid, ns, _codeaza(adresa_directa or caleCanal(sursa_id, cheie)))


def adresaDirecta(adresa):
	"""Adresa unui flux care nu trece prin redirectionare: alta schema decat http(s), fara utilizator si fara parametri. Ce are
	date de acces in ea nu intra in buchet. -> (adresa sau None, fluxul se poate folosi)."""
	p = _desparteAdresa(adresa)
	if p is None:
		return None, False
	if p.scheme.lower() in SCHEME_REDIRECT:
		return None, True
	if p.username or p.password or p.query:
		return None, False
	return adresa, True


def _rand(ref, nume):
	return "#SERVICE %s\r\n#DESCRIPTION %s\r\n" % (ref, nume)


def _refGrupa(fisier):
	return '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % fisier


def refRadacina():
	"""Dosarul 'IPTV' din lista pe sateliti, acelasi ca randul din bouquets.tv."""
	return _refGrupa(BUCHET_RADACINA)


def _refMarcaj(n):
	return "1:64:%X:0:0:0:0:0:0:0::" % n


def _fisierGrupa(sursa_id, grupa):
	return "%s%s_%08x.tv" % (PREFIX_GRUPA, sursa_id, zlib.crc32(grupa.encode("utf-8")) & 0xFFFFFFFF)


# ------------------------------------------------------------------ ce grupe se vad
# s["ascunse"]: numele grupelor ascunse si "tara:<PREFIX>" pentru o tara intreaga (cuprinde si grupele ei noi). Lista tuturor grupelor,
# inclusiv ascunse si taiate la plafon, sta intr-un fisier mic separat (grupe-<sursa>.json): omul are din ce alege.

MAX_CATALOG = 5000
PREFIX_TARA = "tara:"
T_GRUPE_GHID = N_("Bifă = se vede în lista de canale. Canalele puse în Favorite merg în continuare.")
T_GRUPE_TAIATE = N_("Se văd %(vazute)d din %(toate)d de canale. Ascunde ce nu vrei, ca să încapă restul.")
T_GRUPE_N = N_("%d grupe")
T_GRUPE_PARTE = N_("o parte ascunse")
_PREFIX_GRUPA = re.compile(r"^[^0-9A-Za-z]*(?:([A-Za-z]{2,3})\s*[|:\-\u2013\u2014\]\)\u258e\u2503\u2502#/]+|([A-Za-z]{4,6})\s*[|\u258e\u2503\u2502]+)\s*\S")
_DESPARTIRE = re.compile(r"^\s*[#=*~_\-]{3,}")  # #### CHANNELS 4K ####: la furnizori e un rand de titlu, nu un canal


def prefixGrupa(nume):
	"""RO din 'RO| Sport', 'RO: Sport', '[RO] Sport', 'RO - Sport', ASIA din 'ASIA| India'; "" cand numele nu incepe asa."""
	m = _PREFIX_GRUPA.match(nume or "")
	return (m.group(1) or m.group(2)).upper() if m else ""


def eAscunsa(ascunse, nume):
	return bool(ascunse) and (nume in ascunse or (PREFIX_TARA + prefixGrupa(nume)) in ascunse)


def cheiInBuchete(sursa_id):
	"""Cheile canalelor acestei surse puse de om in buchetele lui (Favorite si celelalte): raman in lista sursei si cand grupa lor e
	ascunsa sau cand nu mai incap sub plafon, altfel nu mai pornesc."""
	semn = re.compile(r"8897/tv/%s/([A-Za-z0-9_.\-]{1,64})" % re.escape(sursa_id))
	chei = set()
	try:
		fisiere = os.listdir(DIRECTOR)
	except OSError:
		return chei
	for nume in fisiere:
		if nume.startswith(PREFIX_GRUPA) or nume == BUCHET_RADACINA or not nume.endswith((".tv", ".radio")):
			continue
		try:
			with open(os.path.join(DIRECTOR, nume), encoding="utf-8", errors="replace") as f:
				chei.update(semn.findall(f.read()))
		except (IOError, OSError):
			pass
	return chei


def pastreazaDinBuchete(sursa_id, canale):
	"""Canalele din buchetele omului care nu mai sunt in lista noua raman: o lista scurtata de server nu-i strica Favoritele, iar un canal scos
	de furnizor spune singur, la pornire, ca nu mai e acolo."""
	lipsa = cheiInBuchete(sursa_id) - set(c[0] for c in canale)
	if not lipsa:
		return canale
	return canale + [c for c in citesteCanale(sursa_id) if isinstance(c, list) and c and c[0] in lipsa]


class Filtru(object):
	"""Ce intra din lista unei surse, cat timp se citeste: tine minte toate grupele, lasa afara ce e ascuns si ce nu mai incape sub plafon,
	dar nu si canalele din buchetele omului."""

	def __init__(self, s=None):
		s = s or {}
		self.ascunse = frozenset(s.get("ascunse") or ())
		self.favorite = cheiInBuchete(s["id"]) if s.get("id") else frozenset()
		self.implicit = numeSursa(s) if s else ""
		self.grupe = {}
		self.taiate = 0

	def primeste(self, grupa, cheie, plin):
		"""-> True daca, la plafonul de acum (plin), canalul intra in lista."""
		g = grupa or self.implicit
		n = self.grupe.get(g)
		if n is not None or len(self.grupe) < MAX_CATALOG:
			self.grupe[g] = (n or 0) + 1
		if cheie in self.favorite:
			return True
		if eAscunsa(self.ascunse, g):
			return False
		if plin:
			self.taiate += 1
			return False
		return True

	def catalog(self):
		return [[g, n] for g, n in self.grupe.items()]


def _caleCatalog(sursa_id):
	return _cale("grupe-%s.json" % sursa_id)


def scrieCatalog(sursa_id, catalog):
	with _LACAT:
		_asiguraDosar()
		_scrie(_caleCatalog(sursa_id), json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 0o600)


def citesteCatalog(s):
	"""[[numele grupei, cate canale]], toate; pentru o lista adusa inainte sa existe fisierul, grupele vizibile."""
	try:
		with open(_caleCatalog(s["id"]), encoding="utf-8") as f:
			date = json.load(f)
		if isinstance(date, list):
			return [g for g in date if isinstance(g, list) and len(g) == 2]
	except (IOError, OSError, ValueError):
		pass
	return [[g[1], g[2]] for g in s.get("grupe_lista") or () if len(g) >= 3]


def randuriGrupe(s):
	"""Pentru ecranul Grupele si pagina web, sus tarile (un prefix pe macar doua grupe), dedesubt grupele:
	[{"cheie", "nume", "canale", "grupe" (la tara), "vizibil", "partial" (o tara cu o parte din grupe ascunse)}]."""
	catalog = citesteCatalog(s)
	ascunse = set(s.get("ascunse") or ())
	tari = {}
	for nume, n in catalog:
		pre = prefixGrupa(nume)
		if pre:
			t = tari.setdefault(pre, [0, 0, 0])
			t[0] += 1
			t[1] += n
			t[2] += 1 if eAscunsa(ascunse, nume) else 0
	rez = []
	for pre, (grupe, canale, ascunse_n) in tari.items():
		if grupe >= 2:
			rez.append({"cheie": PREFIX_TARA + pre, "nume": pre, "canale": canale, "grupe": grupe, "vizibil": ascunse_n < grupe,
				"partial": 0 < ascunse_n < grupe})
	for nume, n in catalog:
		rez.append({"cheie": nume, "nume": nume, "canale": n, "grupe": 0, "vizibil": not eAscunsa(ascunse, nume), "partial": False})
	return rez


def comutaGrupa(ascunse, catalog, cheie):
	"""Multimea noua de ascunse, dupa ce omul a schimbat bifa randului `cheie` din randuriGrupe."""
	ascunse = set(ascunse or ())
	nume = [g[0] for g in catalog]
	if cheie.startswith(PREFIX_TARA):
		pre = cheie[len(PREFIX_TARA):]
		ale_ei = [n for n in nume if prefixGrupa(n) == pre]
		vizibila = any(not eAscunsa(ascunse, n) for n in ale_ei)
		ascunse.difference_update(ale_ei)
		ascunse.discard(cheie)
		if vizibila:
			ascunse.add(cheie)
		return ascunse
	pre = prefixGrupa(cheie)
	if PREFIX_TARA + pre in ascunse:
		# o grupa dintr-o tara ascunsa: tara nu mai e ascunsa intreaga, celelalte grupe ale ei raman ascunse
		ascunse.discard(PREFIX_TARA + pre)
		ascunse.update(n for n in nume if prefixGrupa(n) == pre and n != cheie)
	elif cheie in ascunse:
		ascunse.discard(cheie)
	else:
		ascunse.add(cheie)
	return ascunse


def ascundeTot(catalog):
	return set(g[0] for g in catalog)


# ------------------------------------------------------------------ buchetele

def _randuriGrupa(s, canale):
	"""Randurile unui buchet si cate canale au intrat (un rand mai lung decat tamponul nucleului nu se poate citi). La Stalker a
	patra coloana e comanda canalului, nu o adresa."""
	sursa_id = s["id"]
	cu_adrese = s.get("fel") in ("m3u", "demo")
	text = []
	n = 0
	titluri = 0
	for c in canale:
		cheie, nume, _grupa, adresa = c[:4]
		if _DESPARTIRE.match(nume):
			titluri += 1
			text.append(_rand(_refMarcaj(titluri), nume))
			continue
		directa = adresaDirecta(adresa)[0] if cu_adrese and adresa else None
		r = _rand(refCanal(sursa_id, cheie, directa), nume)
		if max(len(x.encode("utf-8")) for x in r.split("\r\n")) > LUNGIME_RAND:
			continue
		text.append(r)
		n += 1
	return "".join(text), n


def _impartePeGrupe(s, canale):
	"""[(numele grupei, [canale])] in ordinea listei. Canalele fara grupa primesc numele sursei."""
	grupe = {}
	ordine = []
	for c in canale:
		g = c[2] or numeSursa(s)
		if g not in grupe:
			if len(grupe) >= MAX_GRUPE:
				g = ordine[-1]
			else:
				grupe[g] = []
				ordine.append(g)
		grupe[g].append(c)
	return [(g, grupe[g]) for g in ordine]


def _scrieDacaAltceva(cale, text):
	"""-> True daca s-a scris. Un buchet neschimbat nu se atinge, deci nu cere reincarcare."""
	octeti = text.encode("utf-8")
	try:
		with open(cale, "rb") as f:
			if f.read() == octeti:
				return False
	except (IOError, OSError):
		pass
	_scrie(cale, octeti, 0o644)
	return True


def scrieBuchete():
	"""Radacina si grupele, din canalele tuturor surselor. Scrie numai ce s-a schimbat si sterge grupele care nu mai sunt.
	Nu leaga si nu reincarca nimic: asta o face firul enigma2 (leagaIndex, HdsIptvLucru). -> True daca s-a schimbat ceva. Pune in
	fiecare sursa grupele ei (fisier, nume, canale), citite de lista de canale."""
	with _LACAT:
		surse = citesteSurse()
		schimbat = False
		pastrate = set()
		corp = []
		nr_marcaj = 1
		for s in surse:
			canale = citesteCanale(s["id"])
			ascunse = frozenset(s.get("ascunse") or ())
			grupe = [g for g in _impartePeGrupe(s, canale) if not eAscunsa(ascunse, g[0])]
			o_lista = len(surse) == 1 and len(grupe) == 1
			if len(surse) > 1 and grupe:
				corp.append(_rand(_refMarcaj(nr_marcaj), numeSursa(s)))
				nr_marcaj += 1
			s["grupe_lista"] = []
			s["canale"] = 0
			for nume, lista in grupe:
				text, n = _randuriGrupa(s, lista)
				if not n:
					continue
				fisier = _fisierGrupa(s["id"], nume)
				s["grupe_lista"].append([fisier, nume, n])
				s["canale"] += n
				if o_lista:
					corp.append(text)
					continue
				pastrate.add(fisier)
				corp.append(_rand(_refGrupa(fisier), nume))
				if _scrieDacaAltceva(os.path.join(DIRECTOR, fisier), "#NAME %s\r\n%s" % (nume, text)):
					schimbat = True
			del canale, grupe
		radacina = os.path.join(DIRECTOR, BUCHET_RADACINA)
		if surse:
			if _scrieDacaAltceva(radacina, "#NAME %s\r\n%s" % (NUME_RADACINA, "".join(corp))):
				schimbat = True
		elif os.path.isfile(radacina):
			os.unlink(radacina)
			schimbat = True
		try:
			pe_disc = os.listdir(DIRECTOR)
		except OSError:
			pe_disc = []
		for nume in pe_disc:
			if nume.startswith(PREFIX_GRUPA) and nume not in pastrate:
				try:
					os.unlink(os.path.join(DIRECTOR, nume))
					schimbat = True
				except OSError:
					pass
		if surse:
			scrieSurse(surse)
		return schimbat


def leagaIndex():
	"""Randul radacinii in bouquets.tv, la sfarsit (numerele canalelor omului nu se muta), numai cat sunt surse; altfel scos.
	Nucleul incarca un buchet numai prin index. Pe firul enigma2, chiar inainte de reincarcare. -> True daca s-a schimbat."""
	cale = os.path.join(DIRECTOR, "bouquets.tv")
	rand = "#SERVICE %s\r\n" % refRadacina()
	semn = 'FROM BOUQUET "%s"' % BUCHET_RADACINA
	are = areSurse() and bool(citesteSurse())
	try:
		with open(cale, encoding="utf-8", newline="") as f:
			text = f.read()
	except (IOError, OSError):
		if not are:
			return False
		text = "#NAME Bouquets (TV)\r\n"
	if are == (semn in text):
		return False
	if are:
		if text and not text.endswith("\n"):
			text += "\r\n"
		text += rand
	else:
		randuri = text.splitlines(True)
		rez = []
		sari = False
		for r in randuri:
			if semn in r:
				sari = True
				continue
			if sari and r.startswith("#DESCRIPTION"):
				sari = False
				continue
			sari = False
			rez.append(r)
		text = "".join(rez)
	_scrie(cale, text.encode("utf-8"), 0o644)
	return True


def numarCanale(surse=None):
	"""Cate canale are 'IPTV', pentru antetul din lista pe sateliti."""
	return sum(int(s.get("canale") or 0) for s in (surse if surse is not None else citesteSurse()))


def numarDupaFisier(surse=None):
	"""{fisierul grupei: cate canale}, pentru randurile de sub antet."""
	rez = {}
	for s in (surse if surse is not None else citesteSurse()):
		for g in s.get("grupe_lista") or ():
			try:
				rez[g[0]] = int(g[2])
			except (IndexError, TypeError, ValueError):
				pass
	return rez


def semnaturaRadacina():
	"""Se schimba cand se schimba 'IPTV': lista pe sateliti se reface atunci."""
	try:
		st = os.stat(os.path.join(DIRECTOR, BUCHET_RADACINA))
		return (st.st_mtime, st.st_size)
	except OSError:
		return None


def fisiereGrupe(director=None):
	"""Fisierele grupelor legate din radacina, in ordine (pentru cautare)."""
	cale = os.path.join(director or DIRECTOR, BUCHET_RADACINA)
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			text = f.read()
	except (IOError, OSError):
		return []
	rez = []
	for rand in text.splitlines():
		if rand.startswith("#SERVICE") and 'FROM BOUQUET "' in rand:
			nume = rand.split('FROM BOUQUET "', 1)[1].split('"', 1)[0]
			if nume.startswith(PREFIX_GRUPA) and "/" not in nume and nume not in rez:
				rez.append(nume)
	return rez


def grupaCanalului(cale):
	"""Fisierul grupei in care sta canalul, sau None. Cauta in fisiere: grupele se incarca in nucleu numai cand se deschid, deci o
	cautare prin lista de canale le-ar incarca pe toate."""
	sid = desparteCale(cale)[0]
	semn = (":%s:" % _codeaza(cale)).encode("utf-8")
	inceput = "%s%s_" % (PREFIX_GRUPA, sid) if sid else PREFIX_GRUPA
	for fisier in fisiereGrupe():
		if fisier.startswith(inceput):
			try:
				with open(os.path.join(DIRECTOR, fisier), "rb") as f:
					if semn in f.read():
						return fisier
			except (IOError, OSError):
				pass
	return None


# ------------------------------------------------------------------ sursele

def adaugaSursa(s):
	"""Sursa noua sau aceeasi din nou (acelasi id: datele noi peste cele vechi, de pilda o parola schimbata). -> sursa, sau None
	cand lista e plina."""
	with _LACAT:
		surse = citesteSurse()
		if s.get("fel") == "m3u":
			for v in surse:
				if v.get("fel") == "m3u" and identitatePlaylist(v.get("adresa")) == identitatePlaylist(s.get("adresa")):
					s = dict(s, id=v["id"])
					break
		_tineIdentitate(s)
		for i, v in enumerate(surse):
			if v.get("id") == s["id"]:
				surse[i] = dict(v, **s)
				scrieSurse(surse)
				return surse[i]
		if len(surse) >= MAX_SURSE:
			return None
		surse.append(s)
		scrieSurse(surse)
		return s


def actualizeazaSursa(sursa_id, **campuri):
	with _LACAT:
		surse = citesteSurse()
		for s in surse:
			if s.get("id") == sursa_id:
				s.update(campuri)
				scrieSurse(surse)
				return s
	return None


def stergeSursa(sursa_id):
	"""Sursa si canalele ei. Randurile puse de om in buchetele lui raman (nu se atinge nimic al lui). Daca adauga din nou acelasi
	cont, merg din nou. -> True daca era."""
	with _LACAT:
		surse = citesteSurse()
		noi = [s for s in surse if s.get("id") != sursa_id]
		if len(noi) == len(surse):
			return False
		for s in surse:
			if s.get("id") == sursa_id:
				_tineIdentitate(s)
		try:
			os.unlink(_caleCanale(sursa_id))
		except OSError:
			pass
		if noi:
			scrieSurse(noi)
		else:
			try:
				os.unlink(_caleSurse())
			except OSError:
				pass
		return True


def sursaNouaM3U(adresa, nume=""):
	sid = _identitatiPlaylist().get(_amprentaPlaylist(adresa)) or idSursa("m3u", adresa)
	for s in citesteSurse():
		if s.get("fel") == "m3u" and identitatePlaylist(s.get("adresa")) == identitatePlaylist(adresa):
			sid = s["id"]
			break
	return {"id": sid, "fel": "m3u", "adresa": adresa,
		"nume": numeCurat(nume) or numeCurat(os.path.basename(adresa)) if adresa.startswith("/") else numeCurat(nume) or gazdaAdresei(adresa)}


def sursaNouaXtream(server, utilizator, parola, nume=""):
	d = desparteServer(server)
	return {"id": idSursa("xtream", server, utilizator), "fel": "xtream", "server": server, "utilizator": utilizator,
		"parola": parola, "nume": numeCurat(nume) or (d[1] if d else server)}


def sursaNouaStalker(portal, mac, nume=""):
	d = desparteServer(portal)
	return {"id": idSursa("stalker", portal, mac.upper()), "fel": "stalker", "portal": portal, "mac": mac.upper(),
		"nume": numeCurat(nume) or (d[1] if d else portal)}


def sursaDemo():
	"""Lista demo: fara nume scris (se arata numele felului, tradus), un singur id."""
	return {"id": idSursa("demo", "lista-demo"), "fel": "demo", "nume": ""}


# campurile care se pot arata; parola si adresa cu parola nu ies de aici
def publica(s):
	"""Ce se poate arata despre o sursa, pe televizor si in pagina web: fara parola si fara adresa cu parola."""
	fel = s.get("fel")
	rez = {
		"id": s.get("id"), "fel": fel, "nume": s.get("nume") or "", "canale": int(s.get("canale") or 0),
		"grupe": len(s.get("grupe_lista") or ()), "ascunse": len(s.get("ascunse") or ()), "ora": int(s.get("ora") or 0), "eroare": s.get("eroare") or "",
		"taiate": int(s.get("taiate") or 0), "sarite": int(s.get("sarite") or 0), "fara_https": bool(s.get("fara_https")),
		"expira": int(s.get("expira") or 0),
		"epg_stare": s.get("epg_stare") or "", "epg_evenimente": int(s.get("epg_evenimente") or 0),
		"epg_mesaj": s.get("epg_mesaj") or "",
	}
	if fel == "m3u":
		rez["gazda"] = gazdaAdresei(s.get("adresa"))
	elif fel == "xtream":
		rez["gazda"] = gazdaAdresei(s.get("baza") or s.get("server")) or (desparteServer(s.get("server")) or ("", ""))[1]
		rez["utilizator"] = s.get("utilizator") or ""
	elif fel == "stalker":
		rez["gazda"] = gazdaAdresei(s.get("baza") or s.get("portal")) or (desparteServer(s.get("portal")) or ("", ""))[1]
		rez["mac"] = s.get("mac") or ""
	return rez


def citesteSursePublic():
	return [publica(s) for s in citesteSurse()]


def acum():
	return int(time.time())


# ------------------------------------------------------------------ canalele care n-au pornit ultima data
# Un fisier mic, separat de buchete si de lista canalelor: {"<sursa>/<cheie>": ora}. Lista de canale il citeste cand se schimba (un os.stat).

MAX_NEFUNCTIONALE = 5000
_nefunctionale = (None, {})


def _caleNefunctionale():
	return _cale("nefunctionale.json")


def nefunctionale():
	"""{"<sursa>/<cheie>": ora} ale canalelor care n-au pornit ultima data."""
	global _nefunctionale
	try:
		st = os.stat(_caleNefunctionale())
		semn = (st.st_mtime, st.st_size)
	except OSError:
		return {}
	if _nefunctionale[0] == semn:
		return _nefunctionale[1]
	try:
		with open(_caleNefunctionale(), encoding="utf-8") as f:
			date = json.load(f)
		date = date if isinstance(date, dict) else {}
	except (IOError, OSError, ValueError):
		date = {}
	_nefunctionale = (semn, date)
	return date


def eNefunctional(cale):
	semne = nefunctionale()
	if not semne:
		return False
	sid, cheie = desparteCale(cale)
	return sid is not None and ("%s/%s" % (sid, cheie)) in semne


def _scrieNefunctionale(date):
	global _nefunctionale
	with _LACAT:
		_asiguraDosar()
		_scrie(_caleNefunctionale(), json.dumps(date, separators=(",", ":")).encode("utf-8"), 0o600)
		_nefunctionale = (None, {})


def noteazaNefunctional(sid, cheie):
	date = dict(nefunctionale())
	date["%s/%s" % (sid, cheie)] = acum()
	if len(date) > MAX_NEFUNCTIONALE:
		for k in sorted(date, key=date.get)[:len(date) - MAX_NEFUNCTIONALE]:
			del date[k]
	_scrieNefunctionale(date)


def stergeNefunctional(sid, cheie):
	date = nefunctionale()
	k = "%s/%s" % (sid, cheie)
	if k in date:
		date = dict(date)
		del date[k]
		_scrieNefunctionale(date)


# ------------------------------------------------------------------ setarile vechi

def scoateSetarileVechi(config=None):
	"""Pana la 0.7.0 datele de acces stateau in config.hds_iptv.* (in settings, care nu e 0600). O singura data: un cont Xtream
	sau un portal gasit acolo trece in surse, iar randurile dispar din settings. Lista veche hds_iptv_surse.conf la fel."""
	mutate = False
	vechi = os.path.join(DIRECTOR, "hds_iptv_surse.conf")
	try:
		with open(vechi, encoding="utf-8") as f:
			for rand in f:
				parti = rand.rstrip("\r\n").split("|", 2)
				if len(parti) == 3 and parti[0] == "m3u":
					adresa = adresaListaBuna(parti[2])
					if adresa:
						adaugaSursa(sursaNouaM3U(adresa, parti[1]))
						mutate = True
		os.unlink(vechi)
	except (IOError, OSError):
		pass
	try:
		with open(os.path.join(DIRECTOR, "settings"), encoding="utf-8", errors="replace") as f:
			if "config.hds_iptv." not in f.read():
				return mutate
	except (IOError, OSError):
		return mutate
	try:
		if config is None:
			from Components.config import config
		from Components.config import ConfigSubsection, ConfigText
	except ImportError:
		return mutate
	if "hds_iptv" in config.content.items:
		return mutate
	config.hds_iptv = ConfigSubsection()
	cheile = ("tip_sursa", "m3u_cale", "stalker_portal", "stalker_mac", "xtream_server", "xtream_port", "xtream_user", "xtream_parola")
	valori = {}
	for k in cheile:
		setattr(config.hds_iptv, k, ConfigText(default="", fixed_size=False))
		valori[k] = getattr(config.hds_iptv, k).value
	server, port = valori["xtream_server"], valori["xtream_port"]
	if server and valori["xtream_user"] and valori["xtream_parola"]:
		adresa = server if not port or desparteServer(server) is None or desparteServer(server)[2] else "%s:%s" % (server, port)
		if desparteServer(adresa):
			adaugaSursa(sursaNouaXtream(adresa, valori["xtream_user"], valori["xtream_parola"]))
			mutate = True
	if valori["stalker_portal"] and macBun(valori["stalker_mac"]) and desparteServer(valori["stalker_portal"]):
		adaugaSursa(sursaNouaStalker(valori["stalker_portal"], valori["stalker_mac"]))
		mutate = True
	if valori["m3u_cale"] and adresaListaBuna(valori["m3u_cale"]):
		adaugaSursa(sursaNouaM3U(adresaListaBuna(valori["m3u_cale"])))
		mutate = True
	schimbat = False
	for k in cheile:
		el = getattr(config.hds_iptv, k)
		if el.value:
			schimbat = True
		el.value = ""
		el.save()
	if schimbat:
		try:
			from Components.config import configfile
			configfile.save()
		except ImportError:
			pass
	return mutate

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

MAX_SURSE = 300          # DX15: masurat pe PC cu 20, 100 si 300
MAX_CANALE = 30000       # pe sursa: un buchet mai mare ar tine prea mult reincarcarea buchetelor
MAX_GRUPE = 1000
MAX_NUME = 100
MAX_TEXT = 512
MAX_ADRESA = 2048
LUNGIME_RAND = 250       # octeti pe rand de buchet: nucleul citeste cu un tampon de 256

FELURI = ("m3u", "xtream", "stalker", "demo")
# 0.7.7 (FLM; Eduard 16.11 09:28 si 11:01): felurile ale caror filme (si seriale) nu stau in lista de canale, ci in aplicatia IPTV,
# sub sursa lor (Screens/IptvSetup.IptvCont), si in 'Filme și seriale' (Components/HdsVod._CLASE, aceleasi chei): contul Xtream
# (citite de la furnizor la cerere) si playlistul (filme-<sursa>.json, scris la citirea listei).
FELURI_CATALOG = ("xtream", "m3u")

SCHEME_SURSA = ("http", "https")
SCHEME_FLUX = ("http", "https", "rtsp", "rtmp", "mms", "udp")
SCHEME_REDIRECT = ("http", "https")           # numai de aici se poate urma o redirectionare HTTP
RADACINI_STICK = ("/media/", "/mnt/", "/autofs/", "/hdd/")
EXTENSII_LISTA = (".m3u", ".m3u8", ".tv")   # .tv: o lista Enigma2 de la furnizor
# Listele de canale puse prin FTP (Components/HdsIptvFisier, CRF, forum 1274): numai fisiere .m3u / .m3u8 asezate direct in aceste
# dosare (fara .tv: in /etc/enigma2 stau buchetele receptorului) si in dosarul copiilor, DOSAR/liste/ (copiile din /tmp si din web).
LOCURI_LISTE_FTP = ("/etc/enigma2/",)
SUBDOSAR_LISTE = "liste"
EXTENSII_PLAYLIST = (".m3u", ".m3u8")

_MAC = re.compile(r"[0-9A-Fa-f]{12}\Z")
_GAZDA = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-.]{0,251}[A-Za-z0-9])?$")
_CHEIE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_ID_SURSA = re.compile(r"^[0-9a-f]{8}$")
_CHEIE_FILM = re.compile(r"^[ve][0-9]{1,12}\.[A-Za-z0-9]{1,5}$")   # filmele si episoadele Xtream (HdsIptvClient.xtreamAdresa)

_LACAT = threading.RLock()
_stare_piconuri = {}
_versiune_piconuri = 0

# Separat de _LACAT: o scriere lenta nu tine ticul interfetei pe loc.
_lacat_prezenta_surse = threading.Lock()
_prezenta_surse = (None, False)
_versiune_prezenta_surse = 0
_verificare_surse = None


def _incepePrezentaSurse():
	global _versiune_prezenta_surse
	with _lacat_prezenta_surse:
		_versiune_prezenta_surse += 1
		return (_caleSurse(), _versiune_prezenta_surse)


def _retinePrezentaSurse(cerere, exista):
	global _prezenta_surse
	with _lacat_prezenta_surse:
		if cerere == (_caleSurse(), _versiune_prezenta_surse):
			_prezenta_surse = (cerere[0], exista)


def _actualizeazaPrezentaSurse(exista):
	# Apelat sub lacatul scrierii; invalideaza orice citire inceputa inainte.
	global _versiune_prezenta_surse, _prezenta_surse
	with _lacat_prezenta_surse:
		_versiune_prezenta_surse += 1
		_prezenta_surse = (_caleSurse(), exista)


def verificaSurseFundal():
	"""Un singur stat in fundal, cerut de ceasul rar, niciodata de ticul IPTV."""
	global _verificare_surse, _versiune_prezenta_surse
	with _lacat_prezenta_surse:
		if _verificare_surse is not None:
			return
		_versiune_prezenta_surse += 1
		cerere = (_caleSurse(), _versiune_prezenta_surse)
		_verificare_surse = cerere

	def verifica():
		global _verificare_surse
		try:
			exista = os.path.isfile(cerere[0])
			_retinePrezentaSurse(cerere, exista)
		finally:
			with _lacat_prezenta_surse:
				_verificare_surse = None

	try:
		fir = threading.Thread(target=verifica, name="HdsIptvPrezenta")
		fir.daemon = True
		fir.start()
	except Exception:
		with _lacat_prezenta_surse:
			_verificare_surse = None


def _starePiconuri(surse):
	# Numai permisiuni, fara adrese sau datele conturilor.
	return {s["id"]: (s.get("piconuri") is True, playerSursa(s), tuple(s.get("ascunse") or ()))
		for s in surse if s.get("id")}


def incarcaStarePiconuri():
	"""La pornirea firului: discul se citeste fara lacatul setarilor.
	O salvare concurenta are prioritate fata de instantaneul citit de pe disc."""
	global _stare_piconuri
	with _LACAT:
		versiune = _versiune_piconuri
	stare = _starePiconuri(citesteSurse())
	with _LACAT:
		if versiune == _versiune_piconuri:
			_stare_piconuri = stare


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


NUME_FEL = {"m3u": N_("Playlist"), "xtream": N_("Cont"), "stalker": N_("Portal"), "demo": N_("Listă demo")}
T_FARA_HTTPS = N_("Legătura cu acest server nu este criptată, fiindcă furnizorul nu are HTTPS.")
T_SURSE_PLINE = N_("Ai %d surse din %d posibile. Șterge una ca să poți adăuga alta.")
T_NECONECTATA = N_("Neconectată")


def textSursePline(traduce=lambda x: x):
	return traduce(T_SURSE_PLINE) % (len(citesteSurse()), MAX_SURSE)


def areCatalog(p):
	"""Sursa (sau randul ei public) isi are filmele si serialele in 'Filme și seriale'."""
	return (p or {}).get("fel") in FELURI_CATALOG


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
	if cale == _caleSurse():
		_actualizeazaPrezentaSurse(True)


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


def _sursaAcceptata(s):
	return isinstance(s, dict) and s.get("fel") in FELURI and _ID_SURSA.match(str(s.get("id", "")))


def citesteSurse():
	"""Lista surselor (dict-uri cu tot ce e in fisier, parole incluse: nu se dau mai departe, vezi publica). Un fisier care nu
	se poate citi da o lista goala."""
	cerere = _incepePrezentaSurse()
	try:
		with open(cerere[0], encoding="utf-8") as f:
			date = json.load(f)
		rez = date.get("surse") if isinstance(date, dict) else None
		if not isinstance(rez, list):
			return []
		return [s for s in rez if _sursaAcceptata(s)]
	except (IOError, OSError, ValueError):
		return []
	finally:
		_retinePrezentaSurse(cerere, os.path.isfile(cerere[0]))


def scrieSurse(surse):
	global _stare_piconuri, _versiune_piconuri
	with _LACAT:
		try:
			try:
				with open(_caleSurse(), encoding="utf-8") as f:
					vechi = json.load(f)
			except (IOError, OSError, ValueError):
				vechi = None
			date = dict(vechi) if isinstance(vechi, dict) else {}
			noi = list(surse)
			if isinstance(date.get("surse"), list):
				# Keep rows that the reader does not understand, in their original order.
				for n, s in enumerate(date["surse"]):
					if not _sursaAcceptata(s):
						noi.insert(n, s)
			date["surse"] = noi
			# Compare JSON types too: True and 1 are different settings.
			if json.dumps(vechi, sort_keys=True) != json.dumps(date, sort_keys=True):
				_asiguraDosar()
				try:
					continut = json.dumps(date, ensure_ascii=False).encode("utf-8")
				except UnicodeEncodeError:
					# A lone surrogate in a kept unknown field: the ASCII form escapes it
					# and reads back to exactly the same document.
					continut = json.dumps(date).encode("ascii")
				_scrie(_caleSurse(), continut, 0o600)
			else:
				_actualizeazaPrezentaSurse(True)
		except Exception:
			_actualizeazaPrezentaSurse(os.path.isfile(_caleSurse()))
			raise
		_stare_piconuri = _starePiconuri(surse)
		_versiune_piconuri += 1


def areSurse(verifica=False):
	"""Prezenta din memorie; verifica=True pastreaza verificarea de la pornire."""
	# La pornire pastram verificarea sincrona existenta inaintea redarii.
	if verifica:
		cerere = _incepePrezentaSurse()
		exista = os.path.isfile(cerere[0])
		_retinePrezentaSurse(cerere, exista)
		return exista
	cale, exista = _prezenta_surse
	return cale == _caleSurse() and exista


def sursa(sursa_id, surse=None):
	for s in (surse if surse is not None else citesteSurse()):
		if s.get("id") == sursa_id:
			return s
	return None


def citesteCanale(sursa_id):
	"""[[cheie, nume, grupa, adresa], ...], [] fara fisier."""
	return canaleDinOcteti(octetiCanale(sursa_id))


def octetiCanale(sursa_id):
	"""Fisierul canalelor sursei, asa cum e pe disc (octetii), sau None fara fisier. 0.7.7 (EPG3): ghidul TV (HdsIptvEpg) ia
	semnatura listei din aceiasi octeti din care o citeste, ca sa-si pastreze harta canalelor cat lista nu se schimba."""
	try:
		with open(_caleCanale(sursa_id), "rb") as f:
			return f.read()
	except (IOError, OSError):
		return None


def canaleDinOcteti(octeti):
	"""citesteCanale din octetii lui octetiCanale: lista, sau [] (fara fisier, fisier stricat sau altceva decat o lista)."""
	if octeti is None:
		return []
	try:
		date = json.loads(octeti.decode("utf-8"))
		return date if isinstance(date, list) else []
	except ValueError:
		return []


def scrieCanale(sursa_id, canale):
	with _LACAT:
		_asiguraDosar()
		_scrie(_caleCanale(sursa_id), json.dumps(canale, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 0o600)


# ------------------------------------------------------------------ filmele unui playlist (0.7.7, FLM2)
# Eduard 16.11 11:01: filmele unui playlist nu mai stau in lista de canale; se rasfoiesc in aplicatia IPTV, sub sursa lor
# (Screens/IptvSetup.IptvCont), si in Filme si seriale (Components/HdsVod.SursaM3U). Fisierul lor, filme-<sursa>.json, 0600
# (adresele pot avea parola), un film pe rand: [cheie, nume, grupa, adresa, meta]; se scrie din mers, la citirea listei
# (HdsIptvClient), fara sa tina toate filmele in memorie. grupe-filme-<sursa>.json: [[grupa, cate filme]], in ordinea listei.
MAX_FILME_SURSA = 50000      # ~5,5 MB pe flash; peste plafon cartela spune cat a intrat (HdsIptvClient.textTaiate)
EXT_FILM = (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm")


def eAdresaFilm(adresa):
	"""Un film dintr-un playlist care le amesteca: dupa sfarsitul adresei, fara parametri."""
	return isinstance(adresa, str) and adresa.split("?", 1)[0].lower().endswith(EXT_FILM)


def _caleFilme(sursa_id):
	return _cale("filme-%s.json" % sursa_id)


def _caleGrupeFilme(sursa_id):
	return _cale("grupe-filme-%s.json" % sursa_id)


class ScriitorFilme(object):
	"""Filmele unei surse, scrise din mers in filme-<sursa>.json.nou; gata() le pune in locul celor vechi, renunta() le arunca.
	Fara sursa (probele de pe PC care citesc numai lista) nu scrie nimic, doar numara."""

	def __init__(self, sursa_id=None, maxim=None):
		self.sursa_id = sursa_id
		self.maxim = MAX_FILME_SURSA if maxim is None else maxim
		self.scrise = 0
		self.taiate = 0
		self.grupe = []
		self._n = {}
		self._f = None
		if sursa_id:
			with _LACAT:
				_asiguraDosar()
			self._nou = _caleFilme(sursa_id) + ".nou"
			self._f = os.fdopen(os.open(self._nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8")

	def scrie(self, rand):
		"""rand = [cheie, nume, grupa, adresa, meta]. -> False cand nu mai incape."""
		if self.scrise >= self.maxim:
			self.taiate += 1
			return False
		g = rand[2]
		if g not in self._n:
			self._n[g] = 0
			self.grupe.append(g)
		self._n[g] += 1
		if self._f is not None:
			self._f.write(json.dumps(rand, ensure_ascii=False, separators=(",", ":")) + "\n")
		self.scrise += 1
		return True

	def gata(self):
		if self._f is None:
			return
		self._f.flush()
		os.fsync(self._f.fileno())
		self._f.close()
		self._f = None
		cale = _caleFilme(self.sursa_id)
		if self.scrise:
			os.chmod(self._nou, 0o600)
			os.replace(self._nou, cale)
			_scrie(_caleGrupeFilme(self.sursa_id), json.dumps([[g, self._n[g]] for g in self.grupe], ensure_ascii=False,
				separators=(",", ":")).encode("utf-8"), 0o600)
		else:
			# o lista fara filme: nu ramane nimic vechi in urma
			for c in (self._nou, cale, _caleGrupeFilme(self.sursa_id)):
				try:
					os.unlink(c)
				except OSError:
					pass

	def renunta(self):
		if self._f is not None:
			self._f.close()
			self._f = None
			try:
				os.unlink(self._nou)
			except OSError:
				pass


def grupeFilme(sursa_id):
	"""[[grupa, cate filme]] ale unui playlist, [] fara filme."""
	try:
		with open(_caleGrupeFilme(sursa_id), encoding="utf-8") as f:
			date = json.load(f)
		return [g for g in date if isinstance(g, list) and len(g) == 2] if isinstance(date, list) else []
	except (IOError, OSError, ValueError):
		return []


def filmeSursa(sursa_id, grupa=None, maxim=None):
	"""Filmele playlistului, din mers (generator), [cheie, nume, grupa, adresa, meta]; numai cele din `grupa`, daca e data."""
	try:
		f = open(_caleFilme(sursa_id), encoding="utf-8")
	except (IOError, OSError):
		return
	n = 0
	with f:
		for rand in f:
			try:
				r = json.loads(rand)
			except ValueError:
				continue
			if not isinstance(r, list) or len(r) < 4 or (grupa is not None and r[2] != grupa):
				continue
			yield r
			n += 1
			if maxim and n >= maxim:
				return


_filmGasit = {}


def filmDupaCheie(sursa_id, cheie):
	"""Randul unui film al playlistului (releul, la pornire; pagina filmului), sau None. Tinut minte dupa fisier."""
	try:
		st = os.stat(_caleFilme(sursa_id))
	except OSError:
		return None
	semn = (sursa_id, cheie, st.st_mtime_ns, st.st_size)
	if semn in _filmGasit:
		return _filmGasit[semn]
	inceput = '["%s",' % cheie
	rez = None
	try:
		with open(_caleFilme(sursa_id), encoding="utf-8") as f:
			for rand in f:
				if rand.startswith(inceput):
					try:
						rez = json.loads(rand)
					except ValueError:
						rez = None
					break
	except (IOError, OSError):
		return None
	if len(_filmGasit) > 64:
		_filmGasit.clear()
	_filmGasit[semn] = rez
	return rez


def areFilme(s):
	"""Un playlist cu filme (un os.stat): randul Filme in aplicatia IPTV si sursa in Filme si seriale."""
	return s.get("fel") == "m3u" and os.path.isfile(_caleFilme(s.get("id") or ""))


# ------------------------------------------------------------------ aplicatia IPTV: canalele unei surse, pe grupe (FLM2)

def grupeCanale(s):
	"""Grupele de canale ale sursei cum le arata lista de canale (fara grupele ascunse, fara filmele unei surse cu Filme si
	seriale, fara randurile de titlu): [(grupa, [(cheie, nume, adresa directa sau None)])]. Citeste canale-<sursa>.json: pe fir."""
	canale = citesteCanale(s["id"])
	if filmeAfaraDinLista(s):
		canale = [c for c in canale if not _eFilmSursei(c)]
	ascunse = frozenset(s.get("ascunse") or ())
	cu_adrese = s.get("fel") in ("m3u", "demo")
	rez = []
	for nume, lista in _impartePeGrupe(s, canale):
		if eAscunsa(ascunse, nume):
			continue
		randuri = []
		for c in lista:
			if len(c) < 4 or _DESPARTIRE.match(c[1] or ""):
				continue
			directa = adresaDirecta(c[3])[0] if cu_adrese and c[3] else None
			randuri.append((c[0], c[1], directa))
		if randuri:
			rez.append((nume, randuri))
	return rez


def filmeAfaraDinLista(s):
	"""Filmele sursei nu se arata in lista de canale: la un cont Xtream niciodata, la un playlist numai cand are fisierul filmelor.
	Un playlist adus de 0.7.6 sau de FLM (cu filmele in canale-<sursa>.json, fara fisier) le pastreaza in lista pana la aducerea
	lui de dupa actualizare: altfel ar disparea si din lista, si din aplicatia IPTV."""
	return s.get("fel") == "xtream" or areFilme(s)


def numarFilme(s):
	"""Cate filme are playlistul in fisierul lor (din grupe-filme-<sursa>.json, mic), 0 fara fisier."""
	if not areFilme(s):
		return 0
	return sum(int(n) for _g, n in grupeFilme(s["id"]) if isinstance(n, int))


def _eFilmSursei(c):
	"""Un film (Xtream v/e sau, la un playlist, dupa adresa) ramas in canalele sursei pentru Favorite (pastreazaDinBuchete)."""
	return bool(c) and isinstance(c[0], str) and (bool(_CHEIE_FILM.match(c[0])) or (len(c) > 3 and eAdresaFilm(c[3])))


# ------------------------------------------------------------------ verificarea a ce scrie omul

def textBun(text, maxim=MAX_TEXT):
	"""Fara caractere de control, cel mult `maxim`."""
	return isinstance(text, str) and len(text) <= maxim and not any(ord(c) < 32 or ord(c) == 127 for c in text)


def _fara_spatii(text):
	return not any(c.isspace() for c in text)


def macBun(text):
	return macCurat(text) is not None


def macNouaStalker():
	"""O adresa noua pentru formular; fara salvare sau conectare la portal."""
	import secrets
	return "00:1A:79:" + ":".join("%02X" % b for b in secrets.token_bytes(3))


def macReceptor(retea="/sys/class/net"):
	"""Valoare initiala a formularului nou; nu se foloseste in cererile portalului."""
	try:
		placi = sorted(os.listdir(retea))
	except OSError:
		return ""
	for placa in ["eth0"] + [p for p in placi if p not in ("eth0", "lo")]:
		try:
			with open(os.path.join(retea, placa, "address"), encoding="ascii") as f:
				mac = macCurat(f.read(64).strip())
			if mac and mac not in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
				return mac
		except (OSError, UnicodeError):
			pass
	return ""


def macCurat(text):
	"""Numai cele 12 cifre scrise de om; forma comuna pentru salvare si protocol."""
	if not isinstance(text, str) or len(text) > 64:
		return None
	text = text.strip().replace(":", "").replace("-", "").replace(".", "")
	if not _MAC.fullmatch(text):
		return None
	return ":".join(text[i:i + 2] for i in range(0, 12, 2)).upper()


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
		if text.startswith(RADACINI_STICK):
			return text
		if text.lower().endswith(EXTENSII_PLAYLIST) and os.path.dirname(text) + "/" in locuriListeLocale():
			return text
		return None
	if not _fara_spatii(text):
		return None
	p = _desparteAdresa(text)
	if p is None or p.scheme not in SCHEME_SURSA or not p.hostname:
		return None
	return text


def dosarListe():
	"""Unde stau copiile listelor de canale venite din /tmp sau din pagina web (CRF, forum 1274)."""
	return DOSAR.rstrip("/") + "/" + SUBDOSAR_LISTE


def locuriListeLocale():
	"""Dosarele din memoria receptorului din care se poate citi o lista de canale (fiecare cu / la sfarsit)."""
	return tuple(LOCURI_LISTE_FTP) + (dosarListe().rstrip("/") + "/",)


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
	if s.get("fel") not in ("m3u", "stalker"):
		return
	date = _identitatiPlaylist()
	k = _amprentaStalker(s.get("portal"), s.get("mac")) if s.get("fel") == "stalker" else _amprentaPlaylist(s.get("adresa") or "")
	if date.get(k) == s["id"]:
		return
	date.pop(k, None)
	date[k] = s["id"]
	while len(date) > 1024:
		del date[next(iter(date))]
	_asiguraDosar()
	_scrie(_cale("identitati.json"), json.dumps(date).encode("utf-8"), 0o600)


def identitatePortal(portal):
	d = desparteServer(portal)
	if not d:
		return None
	schema = d[0] or "http"
	return schema, d[1].lower(), d[2] or ("443" if schema == "https" else "80"), d[3]


def _amprentaStalker(portal, mac):
	return hashlib.sha256(repr(("stalker", identitatePortal(portal), macCurat(mac))).encode("utf-8")).hexdigest()


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


# ':' '%' si caracterele de control (sub 32) ca %xx, restul la fel. 0.7.7 (EPG3): cu str.translate in loc de o bucla Python pe
# fiecare litera: refCanal e chemat o data pe fiecare canal la harta ghidului TV (HdsIptvEpg) si la scrierea buchetelor; pe un
# Viper 4K harta a 29.000 de canale scade de la 5,7 s la 4,2 s de procesor. Acelasi text, litera cu litera.
_CODARE = dict((i, "%%%02x" % i) for i in range(32))
_CODARE[ord(":")] = "%3a"
_CODARE[ord("%")] = "%25"


def _codeaza(text):
	return text.translate(_CODARE)


def numereCanal(sursa_id, cheie):
	"""(SID, TSID, ONID, NS): din sursa si cheie, la fel la orice refacere. NS are in partea de sus 0xFFFE, locul 'IPTV' din
	lista pe sateliti (Screens/ChannelSelection.HDS_POZ_IPTV)."""
	h = zlib.crc32(("%s/%s" % (sursa_id, cheie)).encode("utf-8")) & 0xFFFFFFFF
	s = int(sursa_id[:8], 16)
	return (h & 0xFFFF) or 1, (h >> 16) or 1, (s & 0xFFFF) or 1, 0xFFFE0000 | ((s >> 16) & 0xFFFF)


PLAYERE = ("4097", "5001", "5002")


def playerSursa(s):
	player = str((s or {}).get("player", "4097"))
	return player if player in PLAYERE else "4097"


def refCanal(sursa_id, cheie, adresa_directa=None, player="4097"):
	"""Referinta canalului, fara nume (numele sta in #DESCRIPTION). adresa_directa: numai pentru un flux care nu se poate
	redirectiona (rtsp, rtmp, mms, udp) si nu are parola in el (adresaDirecta)."""
	sid, tsid, onid, ns = numereCanal(sursa_id, cheie)
	return "%s:0:1:%X:%X:%X:%X:0:0:0:%s:" % (playerSursa({"player": player}), sid, tsid, onid, ns, _codeaza(adresa_directa or caleCanal(sursa_id, cheie)))


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
	if lipsa and os.path.isfile(_caleFilme(sursa_id)):
		# 0.7.7 (FLM2): un film al playlistului din Favorite e in fisierul filmelor (adresa de acum), nu se tine copia veche
		lipsa -= set(r[0] for r in filmeSursa(sursa_id) if r[0] in lipsa)
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
		# 0.7.7 (BQT, Ozgur e-mailul 6514): din cele taiate, cate sunt filme (restul sunt canale TV), pentru textul cartelei
		self.taiate_filme = 0

	def primeste(self, grupa, cheie, plin, film=False):
		"""-> True daca, la plafonul de acum (plin), canalul (sau filmul, `film`) intra in lista."""
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
			if film:
				self.taiate_filme += 1
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
		r = _rand(refCanal(sursa_id, cheie, directa, player=playerSursa(s)), nume)
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
		o_singura = False
		for s in surse:
			canale = citesteCanale(s["id"])
			if filmeAfaraDinLista(s):
				# 0.7.7 (FLM): un film pastrat pentru Favorite (pastreazaDinBuchete) ramane in canalele sursei, dar nu mai face o grupa
				# de un rand sub 'IPTV' (filmele stau in aplicatia IPTV, sub sursa lor, si in Filme si seriale)
				canale = [c for c in canale if not _eFilmSursei(c)]
			ascunse = frozenset(s.get("ascunse") or ())
			grupe = [g for g in _impartePeGrupe(s, canale) if not eAscunsa(ascunse, g[0])]
			o_lista = len(surse) == 1 and len(grupe) == 1
			o_singura = o_singura or o_lista
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
		# grupele "4K adevărat" si "HDR" (Components/HdsIptv4K.py), in capul radacinii, cand cautarea a gasit canale
		if corp and not o_singura:      # o singura grupa: canalele stau direct in radacina, fara dosare
			try:
				from Components import HdsIptv4K
				grupe_4k = HdsIptv4K.grupe()
			except Exception as e:
				print("[HdsIptvSurse] grupele 4K: %s" % type(e).__name__)
				grupe_4k = []
			sus = []
			for fisier, nume, randuri in grupe_4k:
				pastrate.add(fisier)
				sus.append(_rand(_refGrupa(fisier), nume))
				text = "".join(_rand(ref, n) for ref, n in randuri)
				if _scrieDacaAltceva(os.path.join(DIRECTOR, fisier), "#NAME %s\r\n%s" % (nume, text)):
					schimbat = True
			corp = sus + corp
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
	are = bool(citesteSurse())
	try:
		with open(cale, encoding="utf-8", errors="surrogateescape", newline="") as f:
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
	_scrie(cale, text.encode("utf-8", "surrogateescape"), 0o644)
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


def grupeLista(surse=None):
	"""Numai identitatea si numele deja afisate, fara conturi sau adrese. Pe firul de citire al indexului.
	Se refoloseste grupe_lista, inclusiv lista unica tinuta direct in radacina."""
	surse = surse if surse is not None else citesteSurse()
	rez = []
	for s in surse:
		grupe = s.get("grupe_lista") or ()
		for g in grupe:
			if not isinstance(g, (list, tuple)) or len(g) < 3 or not isinstance(g[0], str):
				continue
			if not g[0].startswith(PREFIX_GRUPA) or "/" in g[0] or "\\" in g[0]:
				continue
			fisier = BUCHET_RADACINA if len(surse) == 1 and len(grupe) == 1 else g[0]
			rez.append((fisier, s["id"], numeSursa(s), numeCurat(g[1])))
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
				inainte = json.dumps(dict(s, eroare=""), sort_keys=True)
				s.update(campuri)
				_tineIdentitate(s)
				# Clearing a transient playback error alone does not change the saved source.
				if campuri.get("eroare") != "" or inainte != json.dumps(dict(s, eroare=""), sort_keys=True):
					scrieSurse(surse)
				return s
	return None


def stergeSursa(sursa_id):
	"""Sursa si canalele ei. Randurile puse de om in buchetele lui raman (nu se atinge nimic al lui). Daca adauga din nou acelasi
	cont, merg din nou. -> True daca era."""
	global _stare_piconuri, _versiune_piconuri
	with _LACAT:
		surse = citesteSurse()
		noi = [s for s in surse if s.get("id") != sursa_id]
		if len(noi) == len(surse):
			return False
		for s in surse:
			if s.get("id") == sursa_id:
				_tineIdentitate(s)
		# 0.7.7 (FLM2): si filmele playlistului (au adrese, poate cu parola)
		for cale in (_caleCanale(sursa_id), _caleFilme(sursa_id), _caleGrupeFilme(sursa_id)):
			try:
				os.unlink(cale)
			except OSError:
				pass
		if noi:
			scrieSurse(noi)
		else:
			try:
				os.unlink(_caleSurse())
			except OSError:
				_actualizeazaPrezentaSurse(os.path.isfile(_caleSurse()))
			else:
				_actualizeazaPrezentaSurse(False)
		_stare_piconuri = _starePiconuri(noi)
		_versiune_piconuri += 1
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
	mac = macCurat(mac)
	with _LACAT:
		surse = citesteSurse()
		sid = next((s["id"] for s in surse if s.get("fel") == "stalker" and identitatePortal(s.get("portal")) == identitatePortal(portal) and macCurat(s.get("mac")) == mac), None)
		if sid is None:
			sid = _identitatiPlaylist().get(_amprentaStalker(portal, mac)) or idSursa("stalker", portal, mac or "")
			ocupate = {s["id"] for s in surse}
			n = 0
			while sid in ocupate:
				n += 1
				sid = idSursa("stalker", portal, "%s:%d" % (mac or "", n))
	return {"id": sid, "fel": "stalker", "portal": portal, "mac": mac or "",
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
		"player": playerSursa(s), "piconuri": s.get("piconuri") is True,
		"epg_stare": s.get("epg_stare") or "", "epg_evenimente": int(s.get("epg_evenimente") or 0),
		"epg_mesaj": s.get("epg_mesaj") or "",
	}
	rez.update({k: s.get(k) or "" for k in ("adresa", "server", "portal", "utilizator", "parola", "user_agent", "referer", "x_user_agent", "stb_type")})
	if "neconectata" in s:
		rez["neconectata"] = bool(s["neconectata"])
	# 0.7.7 (BQT): cate canale TV si filme au intrat si cate filme s-au taiat (HdsIptvClient.textTaiate); o sursa adusa de
	# o versiune veche nu le are, iar textul cartelei ramane atunci cel general
	if "taiate_filme" in s:
		rez.update(vii=int(s.get("vii") or 0), filme=int(s.get("filme") or 0), taiate_filme=int(s.get("taiate_filme") or 0))
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


# ------------------------------------------------------------------ functiile cu Da/Nu (setup.xml hds_iptv_functii)

def optiune(nume, implicit=True):
	"""config.usage.hds_iptv_<nume> (ghid_pornire, semn, timp_pornire, 4k). Fara config (probele de pe PC): implicit."""
	try:
		from Components.config import config
		return bool(getattr(config.usage, "hds_iptv_" + nume).value)
	except Exception:
		return implicit


# ------------------------------------------------------------------ canalele care n-au pornit ultima data
# Un fisier mic, separat de buchete si de lista canalelor: {"<sursa>/<cheie>": ora} sau, cu motivul, {"<sursa>/<cheie>": [ora, motiv]}
# (MOTIVE). Lista de canale il citeste cand se schimba (un os.stat). Se scrie numai la o cadere si la prima pornire dupa ea.

# motivul pe scurt, din ce stiu releul si playerul (Components/HdsIptvRedare._motiv); textul il traduce lista la afisare
MOTIVE = {
	"server": N_("serverul nu răspunde"),
	"adresa": N_("adresa canalului nu mai există"),
	"refuz": N_("serverul a refuzat canalul (contul sau țara)"),
	"conexiuni": N_("contul a atins limita de conexiuni"),
	"format": N_("receptorul nu poate reda formatul"),
	"gol": N_("de la server nu vine nimic"),
	"retea": N_("fără internet"),
}

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


def numeDinBuchete(cale, director=None):
	"""Numele canalului de internet din grupele lui (#DESCRIPTION), sau "". Pentru zap-urile venite fara nume (/api/zap al
	aplicatiilor, canalul tinut minte): fara el, bara si /api/statusinfo aratau un nume gol."""
	import glob
	sid, cheie = desparteCale(cale)
	if sid is None:
		return ""
	semn = "%s/%s" % (sid, cheie)
	for f in glob.glob(os.path.join(director or DIRECTOR, PREFIX_GRUPA + "*.tv")):
		try:
			with open(f, encoding="utf-8", errors="replace") as fis:
				gasit = False
				for r in fis:
					if not r.strip():
						continue
					if gasit and r.startswith("#DESCRIPTION "):
						return r[13:].strip()
					gasit = r.startswith("#SERVICE ") and semn in r.replace("%3a", ":").replace("%3A", ":")
		except (IOError, OSError):
			continue
	return ""


def motivNefunctional(cale):
	"""(cod din MOTIVE sau "", textul codecului sau "") al canalului care n-a pornit; ("", "") daca a pornit sau nu se stie."""
	sid, cheie = desparteCale(cale)
	v = nefunctionale().get("%s/%s" % (sid, cheie)) if sid is not None else None
	if isinstance(v, list) and len(v) > 1 and v[1] in MOTIVE:
		return v[1], (v[2] if len(v) > 2 and isinstance(v[2], str) else "")
	return "", ""


def _scrieNefunctionale(date):
	global _nefunctionale
	with _LACAT:
		_asiguraDosar()
		_scrie(_caleNefunctionale(), json.dumps(date, separators=(",", ":")).encode("utf-8"), 0o600)
		_nefunctionale = (None, {})


def noteazaNefunctional(sid, cheie, motiv="", codec=""):
	if not optiune("semn"):
		return
	date = dict(nefunctionale())
	date["%s/%s" % (sid, cheie)] = [acum(), motiv, codec[:40]] if motiv in MOTIVE else acum()
	if len(date) > MAX_NEFUNCTIONALE:
		# valorile sunt ora (fisierele vechi) sau [ora, motiv, codec]: in Python 3 int si list nu se compara
		for k in sorted(date, key=lambda x: date[x][0] if isinstance(date[x], list) else date[x])[:len(date) - MAX_NEFUNCTIONALE]:
			del date[k]
	_scrieNefunctionale(date)


def stergeNefunctional(sid, cheie):
	date = nefunctionale()
	k = "%s/%s" % (sid, cheie)
	if k in date:
		date = dict(date)
		del date[k]
		_scrieNefunctionale(date)


# ------------------------------------------------------------------ timpul de pornire al canalelor care merg
# {"<sursa>/<cheie>": [zecimi de secunda, ...]} (ultimele PORNIRI_TINUTE), tinut in memorie; pe disc (porniri.json) cel mult o data
# la SCRIERE_PORNIRI_S si numai daca s-a schimbat ceva, deci nu la fiecare zap.

PORNIRI_TINUTE = 5
MAX_PORNIRI = 5000
SCRIERE_PORNIRI_S = 600
_porniri = None
_porniri_schimbate = False
_porniri_scrise = 0.0


def _caleaPorniri():
	return _cale("porniri.json")


def porniri():
	global _porniri
	if _porniri is None:
		try:
			with open(_caleaPorniri(), encoding="utf-8") as f:
				d = json.load(f)
			_porniri = dict((k, [int(x) for x in v][-PORNIRI_TINUTE:]) for k, v in d.items()
				if isinstance(k, str) and isinstance(v, list)) if isinstance(d, dict) else {}
		except (IOError, OSError, ValueError, TypeError):
			_porniri = {}
	return _porniri


def notaPornire(sid, cheie, secunde, ceas=time.monotonic):
	"""Canalul a pornit in `secunde`. In memorie; pe disc rar (scriePorniri)."""
	global _porniri_schimbate
	if not optiune("timp_pornire") or secunde is None or not 0 <= secunde < 600:
		return
	d = porniri()
	k = "%s/%s" % (sid, cheie)
	lista = d.pop(k, [])[-(PORNIRI_TINUTE - 1):] + [int(round(secunde * 10))]
	d[k] = lista               # la capat: cel mai nou; la plin se scot cele mai vechi
	while len(d) > MAX_PORNIRI:
		del d[next(iter(d))]
	_porniri_schimbate = True
	scriePorniri(ceas=ceas)


def scriePorniri(tot=False, ceas=time.monotonic):
	"""Pe disc daca s-a schimbat ceva si a trecut SCRIERE_PORNIRI_S de la ultima scriere (tot=True: acum, la iesire)."""
	global _porniri_schimbate, _porniri_scrise
	if not _porniri_schimbate or _porniri is None:
		return False
	acum_ = ceas()
	if not tot and _porniri_scrise and acum_ - _porniri_scrise < SCRIERE_PORNIRI_S:
		return False
	try:
		with _LACAT:
			_asiguraDosar()
			_scrie(_caleaPorniri(), json.dumps(_porniri, separators=(",", ":")).encode("utf-8"), 0o600)
	except (IOError, OSError) as e:
		print("[HdsIptvSurse] porniri: %s" % type(e).__name__)
		return False
	_porniri_schimbate = False
	_porniri_scrise = acum_
	return True


def timpPornire(cale):
	"""Media ultimelor porniri, in secunde (o zecimala), sau None."""
	if not optiune("timp_pornire"):
		return None
	sid, cheie = desparteCale(cale)
	v = porniri().get("%s/%s" % (sid, cheie)) if sid is not None else None
	return round(sum(v) / 10.0 / len(v), 1) if v else None


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


# ------------------------------------------------------------------ fluxul de internet in direct (0.7.5, IPV)
# Stanga/dreapta la privit cu setarea "volum" (Screens/InfoBarGenerics._hdsVolumPrivit): pe un flux de internet care se poate derula
# (IPTV 4097/5001/5002 din liste sau din buchetele omului) tastele raman la volum cat fluxul e in direct. Filmele, serialele,
# emisiunile din arhiva si fisierele raman la derulare (Ozgur, Vu+ Solo SE, e-mail 6318).

REF_DVB = 1
EXTENSII_FILM = (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg", ".webm", ".divx", ".vob", ".3gp")
SEMNE_NE_DIRECT = ("/movie/", "/series/", "/timeshift/", "/vod/", "catchup", "utc=", "lutc=", "archive=", "timeshift=")


_PREFIXE_FLUX = tuple(s + "://" for s in SCHEME_FLUX)


def _schemaFlux(cale):
	c = (cale or "").lower()
	return c.startswith(_PREFIXE_FLUX)


def fluxInDirect(tip_ref, cale):
	"""-> True cand referinta (tipul si calea decodata) e un flux de internet in direct: nu DVB, adresa de flux, fara semnele unui film, al
	unui serial sau al unei emisiuni din arhiva (cheile v/e/a ale releului nostru, /movie/, /series/, /timeshift/, catchup, extensiile de
	film). Lungimea fluxului o verifica cel care cheama (un film are lungime, un flux in direct nu)."""
	c = (cale or "").replace("%3a", ":").replace("%3A", ":")
	if tip_ref == REF_DVB or not _schemaFlux(c):
		return False
	sid, cheie = desparteCale(c)
	if cheie:
		if cheie[0] in ("v", "e") and "." in cheie:
			return False
		try:
			from Components.HdsIptvClient import eArhiva
			if eArhiva(cheie):
				return False
		except Exception:
			if re.match(r"^a\d{1,12}-\d{12}-\d{1,4}$", cheie):
				return False
		return True
	jos = c.lower()
	if any(s in jos for s in SEMNE_NE_DIRECT):
		return False
	drum = jos.split("?", 1)[0].split("#", 1)[0]
	return not drum.endswith(EXTENSII_FILM)


# ------------------------------------------------------------------ buchetele IP ale omului sub "IPTV" (0.7.5, IPV)
# Intrarea "IPTV" din fila Sateliti arata si buchetele facute de om (editoare de pe PC, Bouquet Maker) care au numai canale de internet
# (4097/5001/5002 si celelalte playere, adrese http/https/rtsp...), ca grupe cu numele buchetului (Gpiupiu, forum 801 #2537). Fara dubluri:
# buchetele noastre (radacina, grupele) si cele care au numai canale din sursele de aici nu intra; un buchet trecut de doua ori in index
# apare o data. Un buchet amestecat (si canale de satelit) ramane numai in Buchete: nucleul nu poate arata numai o parte dintr-un buchet.
# Nimic nu se scrie: randurile sunt dosarele buchetelor omului, deja incarcate prin bouquets.tv.

_MEMORIE_OM = {}       # fisier -> (semnul fisierului, rezultatul citirii)
_MEMORII_OM = {}       # director -> vedere pregatita numai pe firul de lucru
_LACAT_MEMORII_OM = threading.Lock()
_GAZDE_LOCALE = ("127.0.0.1", "localhost", "[::1]")


def _semnFisierOm(cale, erori=False):
	try:
		st = os.stat(cale)
		return st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino
	except (FileNotFoundError, NotADirectoryError):
		return None
	except OSError:
		if erori:
			raise
		return None


class _MemorieBucheteOm:
	"""O vedere completa, publicata dintr-o bucata; cititorii nu asteapta firul."""
	def __init__(self, director, interval):
		self.director = director
		self.interval = interval
		self.vedere = ((), (), {})
		self.semn = None
		self.index_semn = None
		self.fisiere = []
		self.stop = threading.Event()
		self.fir = threading.Thread(target=self._bucla, name="HdsBucheteOm", daemon=True)

	def opreste(self):
		self.stop.set()
		self.fir.join(10)

	def _bucla(self):
		while not self.stop.is_set():
			try:
				self._citeste()
			except Exception as e:
				# Nici numele fisierului, nici continutul nu intra in jurnal.
				print("[HdsIptvSurse] memoria buchetelor: %s" % type(e).__name__)
			self.stop.wait(self.interval)

	def _citeste(self):
		index = os.path.join(self.director, "bouquets.tv")
		index_semn = _semnFisierOm(index, erori=True)
		if self.semn is None or index_semn != self.index_semn:
			fisiere = [f for f in _fisiereIndex(self.director, erori=True) if _buchetOmEligibil(f)] if index_semn is not None else []
			if index_semn != _semnFisierOm(index, erori=True):
				return
			self.fisiere, self.index_semn = fisiere, index_semn
		semne = tuple((f, _semnFisierOm(os.path.join(self.director, f), erori=True)) for f in self.fisiere)
		semn = (index_semn, semne)
		if self.semn == semn:
			return
		randuri, harta = [], {}
		for fisier, asteptat in semne:
			if self.stop.is_set():
				return
			citit_semn, citit = _citireOm(self.director, fisier, erori=True)
			if citit_semn != asteptat:
				return
			if citit is None:
				continue
			nume, cai, amestecat = citit
			if amestecat or not cai:
				continue
			nume = nume or fisier
			randuri.append((fisier, nume, len(cai)))
			for c in cai:
				harta.setdefault(c, (fisier, nume))
		# Un import poate inlocui indexul sau un buchet in timpul citirii.
		if index_semn != _semnFisierOm(index, erori=True) or any(
			s != _semnFisierOm(os.path.join(self.director, f), erori=True) for f, s in semne):
			return
		self.vedere = (tuple(randuri), semn, harta)
		self.semn = semn
		pastrate = {os.path.join(self.director, f) for f in self.fisiere}
		for cale in list(_MEMORIE_OM):
			if os.path.dirname(cale) == self.director and cale not in pastrate:
				_MEMORIE_OM.pop(cale, None)


def pornesteMemoriaOm(director=None, interval=2.0):
	"""La pornire, inclusiv fara surse: analiza si urmarirea buchetelor pe fundal."""
	director = os.path.abspath(director or DIRECTOR)
	with _LACAT_MEMORII_OM:
		memorie = _MEMORII_OM.get(director)
		if memorie is None:
			memorie = _MemorieBucheteOm(director, interval)
			_MEMORII_OM[director] = memorie
			try:
				memorie.fir.start()
			except Exception:
				_MEMORII_OM.pop(director, None)
				raise
		return memorie


def _vedereOm(director):
	memorie = _MEMORII_OM.get(os.path.abspath(director or DIRECTOR))
	if memorie is None and director is None:
		memorie = pornesteMemoriaOm()
	return memorie.vedere if memorie is not None else None


def _buchetOmEligibil(fisier):
	return fisier != BUCHET_RADACINA and not fisier.startswith(PREFIX_GRUPA) and fisier.endswith(".tv")


def _fisiereIndex(director=None, erori=False):
	"""Buchetele din bouquets.tv, in ordine, fara repetari: [nume fisier]."""
	cale = os.path.join(director or DIRECTOR, "bouquets.tv")
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			text = f.read()
	except (IOError, OSError):
		if erori:
			raise
		return []
	rez = []
	for rand in text.splitlines():
		if rand.startswith("#SERVICE") and 'FROM BOUQUET "' in rand:
			nume = rand.split('FROM BOUQUET "', 1)[1].split('"', 1)[0]
			if nume and "/" not in nume and "\\" not in nume and nume not in rez:
				rez.append(nume)
	return rez


def _caleDinRand(rest):
	"""(tip, steaguri, cale decodata) din textul de dupa "#SERVICE ", sau None."""
	parti = rest.strip().split(":", 10)
	if len(parti) < 10:
		return None
	try:
		tip = int(parti[0])
		steaguri = int(parti[1])
	except ValueError:
		return None
	cale = parti[10].split(":", 1)[0] if len(parti) > 10 else ""
	if "%" in cale:
		# Cazul obisnuit are numai separatorul schemei codat.
		decodata = cale.replace("%3a", ":").replace("%3A", ":")
		try:
			cale = unquote(cale) if "%" in decodata else decodata
		except Exception:
			pass
	return tip, steaguri, cale


def _gazdaLocala(cale):
	try:
		gazda = (urlsplit(cale).netloc or "").rsplit("@", 1)[-1].lower()
	except Exception:
		return False
	gazda = gazda.rsplit(":", 1)[0] if not gazda.startswith("[") else gazda.split("]", 1)[0] + "]"
	return gazda in _GAZDE_LOCALE or gazda.startswith("127.")


def citesteBuchetOm(cale, erori=False):
	"""-> (numele buchetului, [caile canalelor de internet din afara], amestecat) dintr-un buchet al omului. amestecat: are si alte
	servicii (satelit, cablu, terestru, fisiere, releele locale, dosare); canalele din sursele de aici (releul 8897) nu se numara, dar nici
	nu fac buchetul amestecat."""
	nume = ""
	cai = []
	amestecat = False
	fundal = threading.current_thread() is not threading.main_thread()
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			for nr, rand in enumerate(f):
				if fundal and nr and not nr % 256:
					time.sleep(.001)     # lasa loc tastelor si pe procesoarele mici
				if rand.startswith("#NAME"):
					nume = rand[5:].strip()
					continue
				if not rand.startswith("#SERVICE"):
					continue
				d = _caleDinRand(rand[8:])
				if d is None:
					continue
				tip, steaguri, c = d
				if steaguri & 64:      # marcaj
					continue
				if steaguri & 1 or tip == REF_DVB or not _schemaFlux(c) or _gazdaLocala(c):
					if not e_cale_iptv(c):
						amestecat = True
					continue
				cai.append(c)
	except (IOError, OSError):
		if erori:
			raise
		return nume, [], True
	return nume, cai, amestecat


def _citireOm(director, fisier, erori=False):
	cale = os.path.join(director, fisier)
	semn = _semnFisierOm(cale, erori=erori)
	if semn is None:
		_MEMORIE_OM.pop(cale, None)
		return None, None
	vechi = _MEMORIE_OM.get(cale)
	if vechi is not None and vechi[0] == semn:
		return semn, vechi[1]
	rez = citesteBuchetOm(cale, erori=True) if erori else citesteBuchetOm(cale)
	if semn != _semnFisierOm(cale, erori=erori):
		return None, None
	_MEMORIE_OM[cale] = (semn, rez)
	return semn, rez


def bucheteOm(director=None):
	"""Buchetele omului sub IPTV; dupa pornire, numai vederea pregatita pe fundal."""
	vedere = _vedereOm(director)
	if vedere is not None:
		return list(vedere[0])
	director = director or DIRECTOR
	rez = []
	for fisier in _fisiereIndex(director):
		if not _buchetOmEligibil(fisier):
			continue
		semn, citit = _citireOm(director, fisier)
		if citit is None:
			continue
		nume, cai, amestecat = citit
		if amestecat or not cai:
			continue
		rez.append((fisier, nume or fisier, len(cai)))
	return rez


def refBuchetOm(fisier):
	return _refGrupa(fisier)


def numarCanaleOm(director=None):
	return sum(n for _f, _nume, n in bucheteOm(director))


def semnaturaOm(director=None):
	"""Se schimba cand se schimba bouquets.tv sau un buchet aratat sub "IPTV": lista pe sateliti se reface atunci."""
	vedere = _vedereOm(director)
	if vedere is not None:
		return vedere[1]
	director = director or DIRECTOR
	semne = []
	for fisier in ["bouquets.tv"] + [b[0] for b in bucheteOm(director)]:
		try:
			st = os.stat(os.path.join(director, fisier))
			semne.append((fisier, st.st_mtime, st.st_size))
		except OSError:
			semne.append((fisier, None, None))
	return tuple(semne)


def harteOm(director=None):
	"""{calea decodata a canalului: (fisier, numele buchetului)} pentru canalele din buchetele omului aratate sub "IPTV"; un canal din mai
	multe buchete ramane la primul (fara dubluri). Pentru pagina web a listei (grupele dupa buchet); se cheama o data pe lista."""
	vedere = _vedereOm(director)
	if vedere is not None:
		return vedere[2]
	director = director or DIRECTOR
	rez = {}
	for fisier, nume, _n in bucheteOm(director):
		citit = _MEMORIE_OM.get(os.path.join(director, fisier))
		if citit is None:
			continue
		for c in citit[1][1]:
			rez.setdefault(c, (fisier, nume))
	return rez

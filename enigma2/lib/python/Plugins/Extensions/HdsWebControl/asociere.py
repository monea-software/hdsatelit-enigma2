# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# asociere.py: browserele intrate pe receptor (sesiunea cu cookie) si jetonul din codul QR de pe televizor.
#
# Codul de 6 cifre aratat pe televizor si scris in browser s-a scos de tot. In casa interfata web merge fara nimic de
# scris. Numai cand omul si-a pus parola din reteaua de acasa (Components/HdsParolaLocala.py) si a bifat interfata web,
# browserul scrie o data parola (plugin.py, POST /intra) si primeste aici un secret aleator (cookie HttpOnly,
# SameSite=Strict, valabil un an, adaugaSesiune); pe disc sta DOAR amprenta lui (sha256).
#
# Modulul nu importa nimic din enigma2 sau Twisted, ca sa poata fi testat pe PC. Toate apelurile vin de pe firul
# reactorului (acelasi cu bucla enigma2) sau din ecranul de setari (acelasi fir); lacatul de mai jos e doar o plasa de
# siguranta, nu o cerinta.
#
# Ce ramane din paza de dinainte (apara de o pagina de pe internet deschisa in browserul omului, nu de om):
# - secretul sesiunii nu se scrie niciodata pe disc, doar sha256(secret); fisierul are drepturi 0600 si se scrie
#   atomic (fisier nou + os.replace);
# - tokenul CSRF al panoului se deriva din secret cu HMAC, deci nu trebuie pastrat nicaieri;
# - antetul Host trebuie sa fie adresa receptorului (gazdaPermisa): altfel o pagina de pe internet care isi re-leaga
#   numele la IP-ul receptorului (DNS rebinding) trimite Origin egal cu Host si trece de verificarea Origin.
#
# O SINGURA lista pentru toate aparatele: fiecare intrare are campul `tip` ("browser" sau "aplicatie"; intrarile
# de tip aplicatie sunt de dinainte si raman numai ca sa nu se piarda fisierul).
#
# JETONUL DIN CODUL QR (cereJeton / verificaJeton): un ecran de pe televizor (de ex. „Configurează de pe telefon” din
# traducerea subtitrarilor) arata un cod QR cu adresa http://<IP receptor>/t/<jeton>; telefonul care il scaneaza ajunge
# direct la pagina ceruta de ecran (si devine browser intrat, chiar cand omul are parola pusa). Omul nu scrie nimic:
# jetonul are 256 de biti, o singura folosire, JETON_S secunde pe ceasul monoton, un singur jeton activ, se anuleaza cand
# ecranul se inchide; in memorie se tine doar amprenta lui. Destinatia e o cale din DESTINATII_JETON, niciodata o adresa
# primita.

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

try:
	from urllib.parse import urlsplit
except ImportError:  # Python 2, doar ca modulul sa nu cada la import pe unelte vechi
	from urlparse import urlsplit

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

NUME_COOKIE = "hds_sesiune"
ANTET_CSRF = "X-HDS-CSRF"
CALE_IMPLICITA = "/etc/enigma2/hdswebcontrol-browsere.json"

DURATA_SESIUNE_S = 365 * 24 * 3600
MAX_BROWSERE = 20
INTERVAL_SALVARE_FOLOSIRE_S = 24 * 3600
# jetonul din codul QR: cinci minute (omul scaneaza cu telefonul din fata televizorului; ecranul face altul la expirare)
JETON_S = 300
# paginile spre care poate duce un jeton (ecranul alege una; nimic primit din retea)
DESTINATII_JETON = ("/", "/traducere-configurare", "/traducere-subtitrari")
# sub aceasta data (01.01.2020) ceasul receptorului nu era inca potrivit cand s-a creat sesiunea
# (receptorul porneste uneori cu ora din 1970 pana la sincronizare)
CEAS_MINIM_PLAUZIBIL = 1577836800

_CARACTERE_SECRET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

TIP_BROWSER = "browser"
TIP_APLICATIE = "aplicatie"
TIPURI = (TIP_BROWSER, TIP_APLICATIE)
LUNGIME_MAXIMA_NUME = 40


def numeAparat(text):
	"""Numele trimis de aplicatie (de ex. modelul telefonului), curatat: litere, cifre, spatiu si . - _ ( ) +,
	maxim 40 de caractere. Apare pe televizor si in ecranul de setari; nimic altceva nu trece."""
	if not text:
		return ""
	curat = "".join(c for c in str(text) if c.isalnum() or c in " .-_()+")
	curat = " ".join(curat.split())[:LUNGIME_MAXIMA_NUME].strip()
	return curat


def formatSecretValid(secret):
	"""Secretul din cookie are forma lui secrets.token_urlsafe(32): 43 de caractere base64url."""
	if not secret or not isinstance(secret, str):
		return False
	if len(secret) < 32 or len(secret) > 100:
		return False
	return all(c in _CARACTERE_SECRET for c in secret)


def amprenta(secret):
	return hashlib.sha256(secret.encode("ascii")).hexdigest()


def csrfPentru(secret):
	"""Tokenul CSRF al panoului, derivat din secretul sesiunii. O pagina straina nu il poate afla: nu poate
	citi cookie-ul (HttpOnly) si nici pagina panoului (fara CORS pe ea, iar SameSite=Strict nu trimite
	cookie-ul din alt sit)."""
	return hmac.new(secret.encode("ascii"), b"hds-csrf-v1", hashlib.sha256).hexdigest()


def _gazdaSiPort(schema, netloc):
	"""('http', '10.0.0.20:8080') -> ('10.0.0.20', 8080). Intoarce None la orice forma ciudata."""
	try:
		bucati = urlsplit("//" + netloc)
		gazda = bucati.hostname
		port = bucati.port
	except ValueError:
		return None
	if not gazda:
		return None
	if bucati.username is not None or bucati.password is not None:
		return None
	if port is None:
		port = 443 if schema == "https" else 80
	return (gazda.lower(), port)


def acelasiOrigin(antet_host, origin, referer):
	"""True doar daca cererea vine dintr-o pagina servita chiar de receptor (aceeasi gazda si acelasi port
	ca antetul Host). Se uita intai la Origin (trimis de browsere la orice POST); daca lipseste, la Referer.
	Fara niciunul, raspunsul e False: mai bine o cerere legitima refuzata decat una straina primita."""
	if not antet_host:
		return False
	asteptat = _gazdaSiPort("http", antet_host.strip())
	if asteptat is None:
		return False
	sursa = None
	if origin:
		origin = origin.strip()
		if origin.lower() == "null":
			return False
		sursa = origin
	elif referer:
		sursa = referer.strip()
	if not sursa:
		return False
	try:
		bucati = urlsplit(sursa)
	except ValueError:
		return False
	if bucati.scheme.lower() != "http":
		return False
	primit = _gazdaSiPort("http", bucati.netloc)
	return primit is not None and primit == asteptat


def _esteIPv4Scris(gazda):
	"""'10.0.0.20' da, '0x7f.1', '1.2.3', '10.0.0.20.nip.io' nu: patru numere 0-255, doar cifre."""
	parti = gazda.split(".")
	if len(parti) != 4:
		return False
	for parte in parti:
		if not parte or len(parte) > 3 or any(c not in "0123456789" for c in parte):
			return False
		if int(parte) > 255:
			return False
	return True


def gazdaPermisa(antet_host, nume_proprii=()):
	"""True daca antetul Host numeste chiar receptorul: o adresa IPv4 scrisa cu cifre, 'localhost' sau unul din
	`nume_proprii` (numele receptorului in retea, de ex. 'viper4kv20' si 'viper4kv20.local'), cu orice port.
	De ce (DNS rebinding): o pagina de pe internet, deschisa intr-un browser din casa, isi poate
	re-lega numele (evil.example) la IP-ul receptorului; browserul trimite atunci Host: evil.example si Origin:
	http://evil.example, egale, deci verificarea Origin singura nu ajunge. O adresa scrisa cu cifre nu poate fi
	re-legata, iar numele receptorului nu e al atacatorului. Fara Host (niciun browser nu trimite asa ceva), sau
	cu orice alt nume: False. Numele se compara exact, niciodata ca sufix."""
	if not antet_host:
		return False
	gazda_port = _gazdaSiPort("http", antet_host.strip())
	if gazda_port is None:
		return False
	gazda = gazda_port[0]
	if gazda.endswith("."):
		gazda = gazda[:-1]  # 'localhost.' e acelasi nume ca 'localhost'
	if _esteIPv4Scris(gazda) or gazda == "localhost":
		return True
	for nume in nume_proprii:
		if nume and gazda == nume.strip().lower().rstrip("."):
			return True
	return False


def numeBrowser(user_agent):
	"""Un nume scurt si citibil, dintr-un vocabular fix (niciodata text copiat din antet, deci nimic de
	scapat la afisare): 'Chrome pe Windows', 'Safari pe iPhone', 'Browser'."""
	ua = user_agent or ""
	if "Edg/" in ua or "EdgA/" in ua or "EdgiOS/" in ua:
		browser = "Edge"
	elif "OPR/" in ua or "Opera" in ua:
		browser = "Opera"
	elif "SamsungBrowser/" in ua:
		browser = "Samsung Internet"
	elif "Firefox/" in ua or "FxiOS/" in ua:
		browser = "Firefox"
	elif "Chrome/" in ua or "CriOS/" in ua or "Chromium/" in ua:
		browser = "Chrome"
	elif "Safari/" in ua:
		browser = "Safari"
	elif ua.startswith("curl/"):
		browser = "curl"
	else:
		browser = _t("Browser")
	if "iPhone" in ua:
		sistem = "iPhone"
	elif "iPad" in ua:
		sistem = "iPad"
	elif "Android" in ua:
		sistem = "Android"
	elif "Tizen" in ua or "Web0S" in ua or "SMART-TV" in ua or "SmartTV" in ua:
		sistem = "televizor"
	elif "Windows" in ua:
		sistem = "Windows"
	elif "CrOS" in ua:
		sistem = "ChromeOS"
	elif "Macintosh" in ua or "Mac OS X" in ua:
		sistem = "Mac"
	elif "Linux" in ua:
		sistem = "Linux"
	else:
		sistem = ""
	return "%s pe %s" % (browser, sistem) if sistem else browser


def _adresaCurata(adresa):
	"""Adresa IP a clientului, doar cifre, puncte si doua puncte (IPv6), maxim 45 de caractere."""
	if not adresa:
		return ""
	adresa = str(adresa)[:45]
	return adresa if all(c in "0123456789abcdefABCDEF.:" for c in adresa) else ""


class Asociere(object):
	"""Browserele intrate (pe disc, doar amprente) si jetonul codului QR (in memorie)."""

	def __init__(self, cale=CALE_IMPLICITA, ceas=time.time, ceas_monoton=time.monotonic, jurnal=None):
		self._cale = cale
		self._ceas = ceas
		self._monoton = ceas_monoton
		self._jurnal = jurnal or (lambda text: None)
		self._lacat = threading.RLock()
		self._browsere = None  # lista de dictionare, incarcata la prima folosire
		self._jeton = None  # {"hash", "id", "destinatie", "expira"}: jetonul activ al codului QR (numai amprenta)
		self._jeton_folosit = None  # {"id", "nume", "adresa"}: ultimul jeton folosit, pentru ecranul de pe televizor

	# ------------------------------------------------------------------ fisierul
	def _incarca(self):
		if self._browsere is not None:
			return
		self._browsere = []
		try:
			with open(self._cale, "r") as f:
				date = json.load(f)
		except (IOError, OSError):
			return  # nu exista inca: niciun browser asociat
		except ValueError:
			self._jurnal("fisierul browserelor e stricat, pornesc cu lista goala")
			return
		intrari = date.get("browsere", []) if isinstance(date, dict) else []
		for intrare in intrari if isinstance(intrari, list) else []:
			if self._intrareValida(intrare):
				self._browsere.append(intrare)

	@staticmethod
	def _intrareValida(intrare):
		if not isinstance(intrare, dict):
			return False
		h = intrare.get("hash")
		if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
			return False
		if not isinstance(intrare.get("id"), str) or not intrare["id"]:
			return False
		for camp in ("creat", "folosit"):
			if not isinstance(intrare.get(camp), (int, float)):
				return False
		if not isinstance(intrare.get("nume"), str):
			intrare["nume"] = _t("Browser")
		if not isinstance(intrare.get("adresa"), str):
			intrare["adresa"] = ""
		if intrare.get("tip") not in TIPURI:
			intrare["tip"] = TIP_BROWSER  # intrarile scrise inainte de campul `tip` erau toate browsere
		return True

	def _salveaza(self):
		date = {"versiune": 1, "browsere": self._browsere}
		nou = self._cale + ".nou"
		try:
			fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
			with os.fdopen(fd, "w") as f:
				json.dump(date, f, indent=1, sort_keys=True)
				f.flush()
				try:
					os.fsync(f.fileno())
				except OSError:
					pass
			try:
				os.chmod(nou, 0o600)
			except OSError:
				pass
			os.replace(nou, self._cale)
			return True
		except (IOError, OSError) as eroare:
			self._jurnal("nu am putut salva lista browserelor: %s" % eroare)
			try:
				os.remove(nou)
			except OSError:
				pass
			return False

	# ------------------------------------------------------------------ intrarea cu parola din reteaua de acasa
	def adaugaSesiune(self, user_agent="", adresa=""):
		"""Un browser a scris parola buna (plugin.py, POST /intra): (secret, intrarea fara amprenta). Secretul exista in
		clar numai acum, pentru cookie."""
		with self._lacat:
			secret = secrets.token_urlsafe(32)
			intrare = self._adaugaBrowser(secret, numeBrowser(user_agent), _adresaCurata(adresa), TIP_BROWSER)
			return secret, self._faraAmprenta(intrare)

	# ------------------------------------------------------------------ jetonul din codul QR (vezi nota de sus)
	def cereJeton(self, destinatie="/"):
		"""Un jeton nou pentru codul QR al unui ecran de pe televizor (cel vechi nu mai e bun). Intoarce
		{"jeton": textul pus in cod, "id": id-ul lui (pentru stareJeton/anuleazaJeton), "ramas": secunde}. Jetonul in
		clar nu se pastreaza aici si nu se scrie nicaieri: il are numai ecranul, cat il deseneaza."""
		if destinatie not in DESTINATII_JETON:
			destinatie = "/"
		jeton = secrets.token_urlsafe(32)
		with self._lacat:
			self._jeton = {"hash": amprenta(jeton), "id": secrets.token_hex(8), "destinatie": destinatie,
				"expira": self._monoton() + JETON_S}
			return {"jeton": jeton, "id": self._jeton["id"], "ramas": JETON_S}

	def _jetonCurent(self, acum):
		if self._jeton is not None and self._jeton["expira"] <= acum:
			self._jeton = None
		return self._jeton

	def anuleazaJeton(self, id_jeton=None):
		"""Ecranul s-a inchis: jetonul lui nu mai e bun (fara id: oricare). True daca a anulat."""
		with self._lacat:
			if self._jeton is None:
				return False
			if id_jeton is not None and not secrets.compare_digest(str(id_jeton).encode("utf-8"),
					self._jeton["id"].encode("ascii")):
				return False
			self._jeton = None
			return True

	def stareJeton(self, id_jeton):
		"""Pentru ecranul de pe televizor: ("activ", secunde ramase) | ("folosit", {"nume", "adresa"}) | ("expirat", None)."""
		with self._lacat:
			acum = self._monoton()
			curent = self._jetonCurent(acum)
			if curent is not None and curent["id"] == id_jeton:
				return "activ", int(curent["expira"] - acum + 0.999)
			f = self._jeton_folosit
			if f is not None and f["id"] == id_jeton:
				return "folosit", {"nume": f["nume"], "adresa": f["adresa"]}
			return "expirat", None

	def verificaJeton(self, jeton, user_agent="", adresa="", secret_existent=None):
		"""Jetonul primit de la telefon. Intoarce un dictionar:
		  stare: 'ok' | 'format' | 'expirat'
		  secret: la 'ok', secretul nou al browserului (pentru cookie), sau None daca browserul era deja asociat
		          (`secret_existent` = secretul din cookie-ul lui, bun): atunci nu se face a doua intrare
		  browser: la 'ok', intrarea (fara amprenta); nou: True daca intrarea e noua
		  destinatie: la 'ok', pagina spre care merge telefonul
		Jetonul se consuma la prima folosire buna; unul gresit nu schimba nimic (nicio blocare, vezi nota de sus)."""
		if not formatSecretValid(jeton):
			return {"stare": "format"}
		with self._lacat:
			acum = self._monoton()
			curent = self._jetonCurent(acum)
			if curent is None or not secrets.compare_digest(amprenta(jeton), curent["hash"]):
				return {"stare": "expirat"}
			self._jeton = None
			destinatie = curent["destinatie"]
			if secret_existent is not None:
				existenta = self.sesiune(secret_existent, tip=TIP_BROWSER)
				if existenta is not None:
					self._jeton_folosit = {"id": curent["id"], "nume": existenta.get("nume", ""),
						"adresa": _adresaCurata(adresa)}
					return {"stare": "ok", "secret": None, "browser": existenta, "nou": False, "destinatie": destinatie}
			secret = secrets.token_urlsafe(32)
			intrare = self._adaugaBrowser(secret, numeBrowser(user_agent), _adresaCurata(adresa), TIP_BROWSER)
			self._jeton_folosit = {"id": curent["id"], "nume": intrare["nume"], "adresa": intrare["adresa"]}
			return {"stare": "ok", "secret": secret, "browser": self._faraAmprenta(intrare), "nou": True,
				"destinatie": destinatie}

	# ------------------------------------------------------------------ aparatele asociate (browsere si aplicatii)
	def _adaugaBrowser(self, secret, nume, adresa, tip=TIP_BROWSER):
		self._incarca()
		acum = self._ceas()
		self._scoateExpirate(acum)
		while len(self._browsere) >= MAX_BROWSERE:
			cel_mai_vechi = min(self._browsere, key=lambda b: b.get("folosit", 0))
			self._browsere.remove(cel_mai_vechi)
		intrare = {
			"id": secrets.token_hex(4),
			"hash": amprenta(secret),
			"tip": tip,
			"nume": nume,
			"adresa": adresa,
			"creat": int(acum),
			"folosit": int(acum),
		}
		self._browsere.append(intrare)
		self._salveaza()
		return intrare

	@staticmethod
	def _expirat(intrare, acum):
		creat = intrare["creat"]
		if acum < creat:
			return False  # ceasul receptorului e in urma fata de momentul crearii: nu expiram pe nedrept
		if creat < CEAS_MINIM_PLAUZIBIL:
			return False  # creat cand ceasul era inca in 1970; anul incepe la prima ora corecta (_potrivesteCeasul)
		return acum - creat > DURATA_SESIUNE_S

	def _potrivesteCeasul(self, acum):
		"""Sesiunile facute cand ceasul receptorului era inca in 1970 primesc data de acum, de indata ce
		ceasul e corect, ca anul de valabilitate sa curga de la o data reala. Intoarce True daca a schimbat ceva."""
		if acum < CEAS_MINIM_PLAUZIBIL:
			return False
		schimbat = False
		for intrare in self._browsere:
			if intrare["creat"] < CEAS_MINIM_PLAUZIBIL:
				intrare["creat"] = int(acum)
				schimbat = True
			if intrare["folosit"] < CEAS_MINIM_PLAUZIBIL:
				intrare["folosit"] = int(acum)
				schimbat = True
		return schimbat

	def _scoateExpirate(self, acum):
		"""Potriveste datele facute cu ceasul gresit si scoate sesiunile expirate. True daca s-a schimbat ceva."""
		schimbat = self._potrivesteCeasul(acum)
		inainte = len(self._browsere)
		self._browsere = [b for b in self._browsere if not self._expirat(b, acum)]
		return schimbat or inainte != len(self._browsere)

	def _cauta(self, secret):
		if not formatSecretValid(secret):
			return None
		h = amprenta(secret)
		gasit = None
		for intrare in self._browsere:
			# fara iesire la prima potrivire: timpul nu spune pe a cata pozitie e browserul
			if secrets.compare_digest(h, intrare["hash"]):
				gasit = intrare
		return gasit

	def sesiune(self, secret, tip=None):
		"""Intrarea aparatului (fara amprenta) daca secretul e bun si neexpirat, altfel None. Cu `tip`, doar un
		aparat de acel fel trece (cookie-ul primeste doar browsere: secretul unei aplicatii nu devine cookie)."""
		with self._lacat:
			self._incarca()
			intrare = self._cauta(secret)
			if intrare is None:
				return None
			if tip is not None and intrare.get("tip", TIP_BROWSER) != tip:
				return None
			acum = self._ceas()
			schimbat = self._potrivesteCeasul(acum)
			if self._expirat(intrare, acum):
				self._browsere.remove(intrare)
				self._salveaza()
				return None
			if acum - intrare["folosit"] >= INTERVAL_SALVARE_FOLOSIRE_S or acum < intrare["folosit"]:
				# ultima folosire se scrie pe disc cel mult o data pe zi (memoria flash a receptorului)
				intrare["folosit"] = int(acum)
				schimbat = True
			if schimbat:
				self._salveaza()
			return self._faraAmprenta(intrare)

	def csrfValid(self, secret, primit):
		if not primit or not formatSecretValid(secret):
			return False
		return hmac.compare_digest(csrfPentru(secret).encode("ascii"), primit.strip().encode("utf-8", "replace"))

	def deconecteaza(self, secret):
		"""Scoate browserul cu acest secret (butonul 'Deconecteaza acest browser' din panou)."""
		with self._lacat:
			self._incarca()
			intrare = self._cauta(secret)
			if intrare is None:
				return False
			self._browsere.remove(intrare)
			self._salveaza()
			return True

	def deconecteazaToate(self, pastreaza=None):
		"""Scoate toate aparatele (browsere si aplicatii) si jetonul codului QR. `pastreaza`:
		secretul unui browser care ramane (cel care a cerut din web cheia noua pentru panou). Intoarce cate au fost
		scoase."""
		with self._lacat:
			self._incarca()
			ramas = self._cauta(pastreaza) if pastreaza else None
			if ramas is not None and ramas.get("tip", TIP_BROWSER) != TIP_BROWSER:
				ramas = None
			numar = len(self._browsere) - (1 if ramas is not None else 0)
			self._browsere = [ramas] if ramas is not None else []
			self._jeton = None
			self._salveaza()
			return numar

	def listaBrowsere(self):
		"""Copii fara amprenta, cele folosite recent primele (pentru ecranul de setari)."""
		with self._lacat:
			self._incarca()
			if self._scoateExpirate(self._ceas()):
				self._salveaza()
			lista = [self._faraAmprenta(b) for b in self._browsere]
		lista.sort(key=lambda b: b["folosit"], reverse=True)
		return lista

	@staticmethod
	def _faraAmprenta(intrare):
		return dict((k, v) for k, v in intrare.items() if k != "hash")

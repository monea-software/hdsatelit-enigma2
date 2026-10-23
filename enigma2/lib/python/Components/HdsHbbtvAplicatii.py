# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Aplicatiile HbbTV din lista imaginii si motivul pentru care o aplicatie nu porneste, se inchide sau nu se arata.

FISIERUL DE DATE (data/hbbtv-aplicatii.json, pe receptor /usr/share/enigma2/hbbtv-aplicatii.json; completarile in
/etc/enigma2/hbbtv-aplicatii.json, cu aceeasi forma: listele se adauga, profilul il inlocuieste pe cel din imagine).
O intrare dintr-o lista: {"adresa": "gazda/inceputul caii", "contine": "text" (daca e)}; se potriveste cu adresa din AIT
fara schema, cu gazda in litere mici (adresa_scurta, gaseste). Listele: compatibilitate, audienta, albastru,
consimtamant. Fara fisier sau cu el stricat: DATE_IMPLICITE.

COMPATIBILITATEA (alege_agent, config_cu_profil): compatibilitate cu aplicatiile din lista "compatibilitate".

MOTIVUL (motiv): din faptele stiute cand aplicatia nu a pornit, s-a inchis singura sau nu s-a aratat in timp:
  fara-internet       receptorul nu ajunge pe internet (adresa nu se afla si nici serverele DNS publice nu raspund);
  adresa-inexistenta  numele gazdei nu mai exista (NXDOMAIN sau fara adresa), cu internetul bun;
  ceas                certificatul paginii refuzat din cauza ceasului receptorului (ajutorul comun
                      Components/HdsCeasHttps; textul lui, tradus, e mesajul);
  pagina-mutata       pagina din AIT, sau cea spre care o muta pagina, raspunde 404 sau 410;
  pagina-goala        pagina raspunde 200 fara niciun octet (sau numai spatii);
  numai-televizoare   adresa e in lista "compatibilitate" si aplicatia nu s-a aratat;
  audienta            adresa e in audienta, sau titlul paginii spune "Telemetry", si aplicatia nu s-a aratat;
  albastru            adresa e in albastru (sau are blueButton=true) si aplicatia nu s-a aratat;
  consimtamant        adresa e in consimtamant si aplicatia nu s-a aratat;
  criptat             canalul e criptat si nu se vede (verdictul ecranului negru, Components/HdsEcranNegru.py), cand
                      nu s-a aflat altceva.
Faptele de pe internet le aduce Cercetare, pe un fir separat (niciodata pe firul enigma2): numele gazdei (DNS), pagina
din AIT cu acelasi User-Agent (urllib urmeaza redirectarile HTTP), mutarile scrise in pagina (meta refresh,
location = "..." in pagina sau in cel mult MAX_SCRIPTURI scripturi ale ei) si raspunsul paginii spre care muta. Se
citesc cel mult MAX_OCTETI pe cerere; nimic nu se ruleaza din ce vine.

Partea de sus nu importa enigma2: se probeaza pe PC."""

from __future__ import absolute_import

import json
import os
import re
import socket
import threading
import time

try:
	from urllib.parse import urljoin, urlsplit
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError
except ImportError:  # Python 2 (numai la probe vechi)
	from urlparse import urljoin, urlsplit  # noqa: F401
	from urllib2 import Request, urlopen, HTTPError  # noqa: F401

CALE_DATE = "/usr/share/enigma2/hbbtv-aplicatii.json"
CALE_OM = "/etc/enigma2/hbbtv-aplicatii.json"
LISTE = ("compatibilitate", "audienta", "albastru", "consimtamant")
MAX_INTRARI = 500
MAX_FISIER = 256 * 1024

PROFIL_IMPLICIT = {"producator": "LGE", "model": "55UR78003LK", "versiune": "WEBOS23 03.40.80", "placa": "W23_K24N",
	"familie": "LaTivu_2.0_2023"}
DATE_IMPLICITE = {
	"profil": PROFIL_IMPLICIT,
	"compatibilitate": [{"adresa": "hbbtv.mediaset.net/app/"}, {"adresa": "hbbtv.prosiebensat1puls4.com/extern/redorbit/"},
		{"adresa": "hbbtv.redbutton.de/extern/redorbit/"}],
	"audienta": [{"adresa": "hbbtv-ikosystem.ikomg.com/"}],
	"albastru": [{"adresa": "france24.tv.dotscreen.com/", "contine": "bluebutton=true"}],
	"consimtamant": [{"adresa": "r9.hbbtv.media/"}],
}

# motivele (cheile textelor din Components/HdsHbbtvPornire.TEXTE: "motiv-" + cod)
FARA_INTERNET = "fara-internet"
INEXISTENTA = "adresa-inexistenta"
MUTATA = "pagina-mutata"
GOALA = "pagina-goala"
TELEVIZOARE = "numai-televizoare"
AUDIENTA = "audienta"
ALBASTRU = "albastru"
CONSIMTAMANT = "consimtamant"
CRIPTAT = "criptat"
MOTIVE = (FARA_INTERNET, INEXISTENTA, MUTATA, GOALA, TELEVIZOARE, AUDIENTA, ALBASTRU, CONSIMTAMANT, CRIPTAT)
# certificatul refuzat din cauza ceasului receptorului: textul il da Components/HdsCeasHttps (cercetare["ceas"])
CEAS = "ceas"

# cum s-a terminat aplicatia (fel), din Components/HdsHbbtvPornire
NU_A_PORNIT, INCHISA_SINGURA, NEARATATA = "nu-a-pornit", "s-a-inchis-singura", "nu-s-a-aratat"

# prefixul User-Agent-ului navigatorului (WPE WebKit); cercetarea il pune in fata partii HbbTV, ca serverul sa vada
# aceeasi cerere ca de la navigator
PREFIX_WEBKIT = "Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/60.5 Safari/605.1.15"
TIMP_CERERE_S = 5.0
TIMP_TOTAL_S = 15.0
MAX_OCTETI = 256 * 1024
MAX_SCRIPT = 128 * 1024
MAX_SCRIPTURI = 3
MAX_MUTARI = 2
INTERNET_TINTE = (("1.1.1.1", 53), ("8.8.8.8", 53))
COD_MUTATA = (404, 410)
SEMNE_AUDIENTA = ("telemetry",)
_CAMP = re.compile(r"[^A-Za-z0-9 ._+-]")


def _jurnal(text):
	print("[HdsHbbtvAplicatii] %s" % text)


# ---------------------------------------------------------------- fisierul de date

def _intrare(x):
	"""O intrare buna dintr-o lista, sau None: adresa (gazda/cale, fara schema, fara spatii), contine scurt."""
	if isinstance(x, str):
		x = {"adresa": x}
	if not isinstance(x, dict):
		return None
	a = str(x.get("adresa") or "").strip().lower()
	a = re.sub(r"^[a-z]+://", "", a)
	if not a or len(a) > 200 or any(c in a for c in " \t\r\n") or "/" not in a and "." not in a:
		return None
	rez = {"adresa": a}
	c = str(x.get("contine") or "").strip().lower()
	if c:
		rez["contine"] = c[:100]
	return rez


def _profil(x):
	"""Profilul curatat (aceleasi semne ca in HdsHbbtv.agent_hbbtv), sau None daca lipseste ceva."""
	if not isinstance(x, dict):
		return None
	rez = {}
	for cheie in ("producator", "model", "versiune", "placa", "familie"):
		v = " ".join(_CAMP.sub("", str(x.get(cheie) or "")).split())[:40]
		rez[cheie] = v
	if not (rez["producator"] and rez["model"] and rez["familie"]):
		return None
	return rez


def date_curate(brut, peste=None):
	"""Datele din fisierul imaginii (`brut`) si completarile omului (`peste`), curatate: liste de intrari bune, cel mult
	MAX_INTRARI fiecare, profilul bun (al completarilor, daca e bun, altfel al imaginii, altfel PROFIL_IMPLICIT)."""
	rez = {"profil": dict(PROFIL_IMPLICIT)}
	for nume in LISTE:
		rez[nume] = []
	for sursa in (brut, peste):
		if not isinstance(sursa, dict):
			continue
		p = _profil(sursa.get("profil"))
		if p:
			rez["profil"] = p
		for nume in LISTE:
			lista = sursa.get(nume)
			if not isinstance(lista, list):
				continue
			for x in lista:
				i = _intrare(x)
				if i and i not in rez[nume] and len(rez[nume]) < MAX_INTRARI:
					rez[nume].append(i)
	return rez


def _citeste_json(cale):
	try:
		if os.path.getsize(cale) > MAX_FISIER:
			_jurnal("%s prea mare" % cale)
			return None
		with open(cale, "rb") as f:
			return json.loads(f.read().decode("utf-8"))
	except (IOError, OSError):
		return None
	except ValueError as e:
		_jurnal("%s stricat: %s" % (cale, e.__class__.__name__))
		return None


_CACHE = {"cheie": None, "date": None}


def citeste_date(cale=CALE_DATE, cale_om=CALE_OM):
	"""Datele, citite din nou numai cand fisierele s-au schimbat (marimea si ora). Fisierul imaginii lipsa sau stricat:
	DATE_IMPLICITE (plus completarile omului)."""
	cheie = []
	for c in (cale, cale_om):
		try:
			s = os.stat(c)
			cheie.append((c, s.st_size, s.st_mtime))
		except OSError:
			cheie.append((c, None, None))
	cheie = tuple(cheie)
	if _CACHE["cheie"] == cheie and _CACHE["date"] is not None:
		return _CACHE["date"]
	brut = _citeste_json(cale)
	if not isinstance(brut, dict):
		brut = DATE_IMPLICITE
	date = date_curate(brut, _citeste_json(cale_om))
	_CACHE["cheie"], _CACHE["date"] = cheie, date
	return date


# ---------------------------------------------------------------- adrese

def adresa_scurta(url):
	"""Adresa fara schema, cu gazda in litere mici si fara portul obisnuit: "gazda/cale?interogare" (cu calea "/" cand
	lipseste). Pentru orice nu e http(s): ""."""
	try:
		p = urlsplit((url or "").strip())
	except ValueError:
		return ""
	if p.scheme.lower() not in ("http", "https") or not p.hostname:
		return ""
	gazda = p.hostname.lower()
	try:
		port = p.port
	except ValueError:
		return ""
	if port and not (p.scheme.lower() == "http" and port == 80 or p.scheme.lower() == "https" and port == 443):
		gazda += ":%d" % port
	rez = gazda + (p.path or "/")
	if p.query:
		rez += "?" + p.query
	return rez


def gaseste(url, lista):
	"""Prima intrare din `lista` care se potriveste cu adresa (inceputul si, daca e, textul cerut), sau None."""
	a = adresa_scurta(url)
	if not a:
		return None
	mic = a.lower()
	for x in lista or ():
		if mic.startswith(x["adresa"]) and (not x.get("contine") or x["contine"] in mic):
			return x
	return None


def gazda(url):
	try:
		return (urlsplit(url or "").hostname or "").lower()
	except ValueError:
		return ""


# ---------------------------------------------------------------- compatibilitatea

def _agent_hbbtv():
	try:
		from Components import HdsHbbtv as H
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsHbbtv as H
	return H.agent_hbbtv


def agent_profil(profil):
	"""Partea HbbTV a User-Agent-ului pentru profil (fara capabilitati)."""
	p = _profil(profil) or dict(PROFIL_IMPLICIT)
	return _agent_hbbtv()(p["producator"], p["model"], p["versiune"], placa=p["placa"], familie=p["familie"])


def alege_agent(url, agent_receptor, date):
	"""(partea HbbTV a User-Agent-ului, profilul sau None) pentru aplicatia de la `url`: compatibilitate cu aplicatiile
	din lista."""
	if gaseste(url, (date or {}).get("compatibilitate")) is None:
		return agent_receptor, None
	p = _profil(date.get("profil")) or dict(PROFIL_IMPLICIT)
	return agent_profil(p), p


def config_cu_profil(config, profil):
	"""Configuration/LocalSystem (Components/HdsHbbtvPornire.config_hbbtv) cu valorile profilului."""
	c = dict(config or {})
	if profil:
		c.update({"vendorName": profil.get("producator", ""), "modelName": profil.get("model", ""),
			"familyName": profil.get("familie", ""), "softwareVersion": profil.get("versiune", ""),
			"hardwareVersion": profil.get("placa", "")})
	return c


# ---------------------------------------------------------------- motivul (partea curata)

def _pagina_rea(cercetare):
	"""MUTATA / GOALA din raspunsurile paginii si ale mutarilor ei, sau None."""
	for p in (cercetare or {}).get("pagini") or ():
		cod = p.get("cod")
		if cod in COD_MUTATA:
			return MUTATA
		if cod == 200 and p.get("gol"):
			return GOALA
	return None


def motiv(fel, url, cercetare=None, date=None, criptat=False):
	"""Motivul (unul din MOTIVE) sau None. fel: NU_A_PORNIT (prima pagina nu a venit), INCHISA_SINGURA (s-a inchis
	singura inainte sa se arate), NEARATATA (pornita, dar fara show() in timp). cercetare: rezultatul Cercetare (None
	cat nu s-a terminat); date: citeste_date(); criptat: canalul e criptat si nu se vede."""
	c = cercetare or {}
	date = date or {}
	if c.get("internet") is False:
		return FARA_INTERNET
	if c.get("dns") == "inexistent":
		return INEXISTENTA
	if c.get("ceas"):
		return CEAS
	rea = _pagina_rea(c)
	if rea:
		return rea
	if fel == NEARATATA:
		if gaseste(url, date.get("compatibilitate")):
			return TELEVIZOARE
		titlu = (c.get("titlu") or "").lower()
		if gaseste(url, date.get("audienta")) or any(s in titlu for s in SEMNE_AUDIENTA):
			return AUDIENTA
		if gaseste(url, date.get("albastru")) or "bluebutton=true" in adresa_scurta(url).lower():
			return ALBASTRU
		if gaseste(url, date.get("consimtamant")):
			return CONSIMTAMANT
	if criptat:
		return CRIPTAT
	return None


# ---------------------------------------------------------------- cercetarea (pe firul ei)

def _text(date):
	for cod in ("utf-8", "latin-1"):
		try:
			return date.decode(cod)
		except UnicodeError:
			continue
	return ""


def _fara_comentarii(text):
	return "\n".join(r for r in text.splitlines() if not r.strip().startswith("//"))


def mutari_in_pagina(html, baza):
	"""Adresele spre care o muta pagina, scrise direct: meta refresh, apoi location = / location.href = /
	location.replace("...") in afara randurilor de comentariu. Cel mult MAX_MUTARI, numai http(s)."""
	rez = []
	m = re.search(r"<meta[^>]*http-equiv\s*=\s*['\"]refresh['\"][^>]*content\s*=\s*['\"][^'\"]*url\s*=\s*([^'\"]+)['\"]",
		html, re.I)
	if m:
		rez.append(urljoin(baza, m.group(1).strip()))
	for m in re.finditer(r"location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]|location\.(?:replace|assign)\(\s*['\"]([^'\"]+)['\"]",
			_fara_comentarii(html)):
		u = (m.group(1) or m.group(2) or "").strip()
		if u and not u.startswith(("#", "javascript:")):
			rez.append(urljoin(baza, u))
	bune = []
	for u in rez:
		if u.lower().startswith(("http://", "https://")) and u not in bune:
			bune.append(u)
	return bune[:MAX_MUTARI]


def scripturi_in_pagina(html, baza):
	rez = []
	for m in re.finditer(r"<script[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", html, re.I):
		u = urljoin(baza, m.group(1).replace("&amp;", "&"))
		if u.lower().startswith(("http://", "https://")) and u not in rez:
			rez.append(u)
	return rez[:MAX_SCRIPTURI]


def _baza(html, final):
	m = re.search(r"<base[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"]", html, re.I)
	return urljoin(final, m.group(1)) if m else final


def _titlu(html):
	m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
	return " ".join(m.group(1).split())[:80] if m else ""


def proba_internet(tinte=INTERNET_TINTE, limita=2.0):
	"""True daca macar o conectare TCP spre serverele DNS publice reuseste (ca Components/HdsStareRetea)."""
	for g, port in tinte:
		try:
			s = socket.create_connection((g, port), limita)
			s.close()
			return True
		except Exception:
			continue
	return False


class Cercetare(object):
	"""Faptele de pe internet pentru adresa aplicatiei, adunate pe un fir separat. gata() spune daca s-a terminat,
	rezultat() da dictionarul: {"dns": "ok" | "inexistent" | "eroare", "internet": True | False | None,
	"pagini": [{"url", "cod", "octeti", "gol"}], "titlu"}. Functiile de retea se pot da (probele de pe PC)."""

	def __init__(self, url, agent, rezolva=None, deschide=None, internet=None, porneste=True, ceas=None):
		self.url, self.agent = url, agent
		self._rezolva = rezolva or socket.getaddrinfo
		self._deschide = deschide or self._deschide_urllib
		self._internet = internet or proba_internet
		self._ceas = ceas or time.time
		self._rez = {"dns": None, "internet": None, "pagini": [], "titlu": ""}
		self._gata = threading.Event()
		if porneste:
			fir = threading.Thread(target=self.ruleaza, name="HdsHbbtvMotiv")
			fir.daemon = True
			fir.start()

	def gata(self):
		return self._gata.is_set()

	def rezultat(self):
		return self._rez if self._gata.is_set() else None

	def _deschide_urllib(self, url, maxim):
		"""(cod, octeti cititi, adresa finala); cod = codul HTTP sau numele erorii."""
		cerere = Request(url, headers={"User-Agent": self.agent, "Accept": "*/*"})
		try:
			import ssl
			ctx = ssl.create_default_context()
		except Exception:
			ctx = None
		try:
			r = urlopen(cerere, timeout=TIMP_CERERE_S, context=ctx) if ctx is not None else urlopen(cerere, timeout=TIMP_CERERE_S)
			try:
				return getattr(r, "status", None) or r.getcode(), r.read(maxim), r.geturl()
			finally:
				r.close()
		except HTTPError as e:
			return e.code, b"", url
		except Exception as e:
			self._ceasul(e)
			return e.__class__.__name__, b"", url

	def _ceasul(self, eroare):
		"""Certificatul refuzat din cauza ceasului receptorului (ajutorul comun Components/HdsCeasHttps): textul lui, deja
		tradus, ramane in rezultat ("ceas") si devine motivul."""
		if self._rez.get("ceas"):
			return
		try:
			try:
				from Components import HdsCeasHttps
			except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
				import HdsCeasHttps
			text = HdsCeasHttps.mesaj(eroare)
		except Exception:
			text = None
		if text:
			self._rez["ceas"] = text

	def _dns(self, gazda_):
		try:
			if not self._rezolva(gazda_, None):
				return "inexistent"
			return "ok"
		except socket.gaierror as e:
			nr = e.args[0] if e.args else None
			if nr in (getattr(socket, "EAI_NONAME", -2), getattr(socket, "EAI_NODATA", -5), 11001, 11004):
				return "inexistent"
			return "eroare"
		except Exception:
			return "eroare"

	def _pagina(self, url, maxim=MAX_OCTETI):
		cod, date, final = self._deschide(url, maxim)
		p = {"url": url, "cod": cod, "octeti": len(date), "gol": cod == 200 and not date.strip()}
		self._rez["pagini"].append(p)
		return p, date, final

	def ruleaza(self):
		try:
			self._ruleaza()
		except Exception as e:
			_jurnal("cercetarea: %s" % e.__class__.__name__)
		finally:
			self._gata.set()

	def _ruleaza(self):
		inceput = self._ceas()
		g = gazda(self.url)
		if not g:
			return
		self._rez["dns"] = self._dns(g)
		if self._rez["dns"] != "ok":
			self._rez["internet"] = bool(self._internet())
			if self._rez["internet"] is False:
				self._rez["dns"] = "eroare"     # fara internet nu se stie daca numele exista
			return
		p, date, final = self._pagina(self.url)
		if not isinstance(p["cod"], int):
			self._rez["internet"] = bool(self._internet())
			return
		self._rez["internet"] = True
		if p["cod"] != 200 or p["gol"]:
			return
		html = _text(date)
		self._rez["titlu"] = _titlu(html)
		baza = _baza(html, final)
		tinte = mutari_in_pagina(html, baza)
		if not tinte:
			for s in scripturi_in_pagina(html, baza):
				if self._ceas() - inceput > TIMP_TOTAL_S:
					return
				cod, js, _f = self._deschide(s, MAX_SCRIPT)
				if cod == 200 and js:
					tinte = mutari_in_pagina(_text(js), baza)
					if tinte:
						break
		for u in tinte:
			if self._ceas() - inceput > TIMP_TOTAL_S:
				return
			if adresa_scurta(u) == adresa_scurta(final):
				continue
			self._pagina(u)


def rand_jurnal(fel, url, cod, cercetare=None):
	"""Un rand pentru jurnalul erorilor navigatorului: felul, motivul, gazda si codurile HTTP (fara calea paginii)."""
	c = cercetare or {}
	coduri = ",".join(str(p.get("cod")) + ("/gol" if p.get("gol") else "") for p in c.get("pagini") or ())
	return "%s hbbtv fel=%s motiv=%s gazda=%s dns=%s internet=%s pagini=%s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
		fel, cod or "-", gazda(url) or "-", c.get("dns") or "-", c.get("internet"), coduri or "-")

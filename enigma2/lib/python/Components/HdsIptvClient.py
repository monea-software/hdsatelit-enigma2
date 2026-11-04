# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvClient: vorbeste cu serverul furnizorului omului si citeste listele: playlist M3U / M3U8, cont Xtream, portal Stalker.
# Numai un client: datele de acces le scrie omul, de la furnizorul lui. Nu se cauta portaluri, conturi sau adrese MAC si nu se
# ocoleste nicio protectie.
#
# Tot ce vine de la server sau dintr-o lista e neincredere: margine la marime si la timp, numai http si https pentru surse,
# numai schemele permise pentru fluxuri (HdsIptvSurse.fluxBun), numele curatate (numeCurat), fara shell, fara cai de fisier.
# Analiza M3U e liniara: niciun regex pe partile lungi ale unui rand (un rand ostil nu poate tine firul).
#
# Mesajele de eroare spun ce s-a intamplat si ce are omul de facut. Niciun text de aici nu cuprinde adresa cu parola: la
# jurnal merge numai gazda. Ruleaza pe un fir al lui (Components/HdsIptvLucru.py), niciodata pe firul enigma2.
#
# Fisierul nu importa nimic din enigma2: probele de pe PC il folosesc ca atare, cu un server propriu pe 127.0.0.1.

import json
import os
import socket
import ssl
import subprocess
import time

try:
	from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, HTTPHandler, build_opener
	from urllib.error import HTTPError, URLError
	from urllib.parse import quote, urlencode, parse_qsl, urljoin
except ImportError:  # Python 2
	from urllib2 import Request, HTTPRedirectHandler, HTTPSHandler, HTTPHandler, build_opener, HTTPError, URLError
	from urllib import quote, urlencode

from Components import HdsIptvSurse as I
from Components.HdsIptvSurse import N_

MAX_LISTA = 64 * 1024 * 1024         # un playlist sau un raspuns de server
MAX_RAND = 8192                      # un rand de playlist mai lung e sarit
MAX_STICK = MAX_LISTA
TERMEN_S = 20                        # o cerere la server
TERMEN_TOTAL_S = 180                 # descarcarea unei liste, cu tot cu server incet
TERMEN_ADRESA_S = 8                  # adresa unui canal la pornire: omul asteapta in fata televizorului
AGENT = "VLC/3.0.21 LibVLC/3.0.21"
MAX_FILME = 2000

# ce vede omul
E_REFUZ = N_("Serverul a refuzat utilizatorul sau parola. Verifică-le și încearcă din nou.")
E_EXPIRAT = N_("Abonamentul a expirat sau este oprit. Vorbește cu furnizorul tău.")
E_EXPIRAT_DATA = N_("Abonamentul a expirat la %s. Vorbește cu furnizorul tău.")
E_NU_RASPUNDE = N_("Serverul nu răspunde. Verifică adresa și internetul, apoi încearcă din nou.")
E_NU_E_LISTA = N_("La această adresă nu este o listă de canale. Verifică adresa dată de furnizor.")
E_FARA_CANALE = N_("Lista nu are niciun canal pe care receptorul să-l poată porni.")
E_PREA_MARE = N_("Lista este prea mare pentru receptor.")
E_NU_E_CONT = N_("La această adresă nu răspunde un server de tip Xtream. Verifică serverul și portul.")
E_NU_E_PORTAL = N_("La această adresă nu răspunde un portal. Verifică adresa dată de furnizor.")
E_MAC = N_("Portalul a refuzat adresa MAC. Verifică adresa MAC dată de furnizor.")
E_FISIER = N_("Fișierul nu se poate citi. Verifică stickul și încearcă din nou.")
E_ADRESA = N_("Adresa nu este bună. Scrie adresa dată de furnizor, cu http sau https.")
E_CERTIFICAT = N_("Serverul are un certificat de securitate nevalid, așa că legătura s-a oprit.")
E_NUME = N_("Numele nu este bun. Scrie un nume mai scurt, fără semne speciale.")
E_UTILIZATOR = N_("Scrie utilizatorul primit de la furnizor.")
E_PAROLA = N_("Scrie parola primită de la furnizor.")
E_FORMA_MAC = N_("Adresa MAC nu este bună. Se scrie așa: 00:1A:79:12:34:56.")
E_PREA_MULTE = N_("Ai ajuns la numărul cel mai mare de surse. Șterge una ca să poți adăuga alta.")
E_DEMO = N_("Lista demo nu s-a putut descărca. Verifică internetul și încearcă din nou.")
E_CONEXIUNI = N_("Sunt prea multe conexiuni deschise pe acest abonament. Oprește redarea pe celălalt aparat și încearcă din nou.")
E_CANAL_LIPSA = N_("Canalul nu mai este la această adresă. Furnizorul l-a scos sau l-a mutat.")
E_PREA_MULTE_CERERI = N_("S-au făcut prea multe cereri către server. Mai încearcă peste puțin.")
E_REFUZ_REDARE = N_("Furnizorul a refuzat redarea acestui canal (cod %d). Dacă abonamentul permite o singură redare, oprește-o pe celălalt aparat.")
E_SERVER_CAZUT = N_("Serverul furnizorului are o problemă acum (cod %d). Mai încearcă peste puțin.")
E_ANTETE = N_("User-Agent sau Referer nu este bun. Folosește valorile primite de la furnizor, fără rânduri noi.")


# ce raspund serverele cand contul are deja o conexiune deschisa
COD_CONEXIUNI = (429, 453, 456, 458, 509, 512, 513)
COD_TEMPORAR = (500, 502, 503, 504)


class EroareIptv(Exception):
	"""mesaj = unul dintre textele E_*; se traduce la afisare."""

	def __init__(self, mesaj, expira=0, cod=0, dupa=0):
		Exception.__init__(self, mesaj)
		self.mesaj = mesaj
		self.expira = expira
		self.cod = cod      # codul HTTP, cand a venit unul
		self.dupa = dupa    # Retry-After, in secunde, cand serverul l-a spus

	def pentruOm(self):
		if self.mesaj == E_EXPIRAT and 0 < self.expira <= time.time():
			try:
				return _tradus(E_EXPIRAT_DATA) % time.strftime("%d.%m.%Y", time.localtime(self.expira))
			except (ValueError, OverflowError, OSError):
				pass
		return self.mesaj


def _jurnal(text):
	print("[HdsIptv] %s" % text)


# ------------------------------------------------------------------ descarcarea

class _Redirectionari(HTTPRedirectHandler):
	"""Numai spre http si https: un server nu poate trimite clientul spre un fisier sau alta schema."""
	max_redirections = 5

	def redirect_request(self, req, fp, code, msg, headers, newurl):
		if not newurl.lower().startswith(("http://", "https://")):
			raise EroareIptv(E_NU_E_LISTA)
		return HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def _context():
	ctx = ssl.create_default_context()
	return ctx


def anteteCurate(date):
	rez = {}
	for k, v in (date.items() if isinstance(date, dict) else ()):
		nume = {"user-agent": "User-Agent", "referer": "Referer", "referrer": "Referer"}.get(str(k).lower())
		if nume and isinstance(v, str) and v and I.textBun(v, 2048):
			rez[nume] = v
	return rez


def anteteSursa(s):
	a = {"User-Agent": s.get("user_agent") or (_AGENT_PORTAL if s.get("fel") == "stalker" else AGENT)}
	if s.get("referer"):
		a["Referer"] = s["referer"]
	return anteteCurate(a)


def _dupa(antete):
	"""Retry-After in secunde; forma cu data nu se foloseste la un zap."""
	try:
		return max(0, int((antete.get("Retry-After") or "0").strip()))
	except (AttributeError, TypeError, ValueError):
		return 0


def deschide(adresa, antete=None, termen=TERMEN_S, metoda=None):
	if I.adresaListaBuna(adresa) is None or adresa.startswith("/"):
		raise EroareIptv(E_ADRESA)
	try:
		req = Request(adresa, headers=dict({"User-Agent": AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}, **(antete or {})), method=metoda)
		return build_opener(_Redirectionari(), HTTPHandler(), HTTPSHandler(context=_context())).open(req, timeout=termen)
	except HTTPError as e:
		cod = e.code
		dupa = _dupa(e.headers)
		e.close()
		raise EroareIptv(E_CONEXIUNI if cod in COD_CONEXIUNI else E_REFUZ if cod in (401, 403) else E_NU_RASPUNDE, cod=cod, dupa=dupa)
	except (URLError, OSError, ValueError) as e:
		motiv = getattr(e, "reason", e)
		raise EroareIptv(E_CERTIFICAT if isinstance(motiv, ssl.SSLError) else E_NU_RASPUNDE)


def descarca(adresa, antete=None, maxim=MAX_LISTA, termen=TERMEN_S, total=TERMEN_TOTAL_S):
	"""GET cu margine la marime si la timp. -> octetii. Arunca EroareIptv; textul nu cuprinde adresa."""
	if not adresa.lower().startswith(("http://", "https://")):
		raise EroareIptv(E_ADRESA)
	cerere = Request(adresa, headers=dict({"User-Agent": AGENT, "Accept": "*/*"}, **(antete or {})))
	deschizator = build_opener(_Redirectionari(), HTTPHandler(), HTTPSHandler(context=_context()))
	inceput = time.time()
	try:
		raspuns = deschizator.open(cerere, timeout=termen)
		try:
			bucati = []
			n = 0
			while True:
				b = raspuns.read1(65536)
				if not b:
					break
				n += len(b)
				if n > maxim:
					raise EroareIptv(E_PREA_MARE)
				if time.time() - inceput > total:
					raise EroareIptv(E_NU_RASPUNDE)
				bucati.append(b)
			return b"".join(bucati)
		finally:
			raspuns.close()
	except EroareIptv:
		raise
	except HTTPError as e:
		if e.code in (429, 453):
			e.close()
			raise EroareIptv(E_CONEXIUNI)
		if e.code in (401, 403):
			e.close()
			raise EroareIptv(E_REFUZ)
		_jurnal("raspuns %d de la %s" % (e.code, I.gazdaAdresei(adresa)))
		raise EroareIptv(E_NU_E_LISTA if e.code == 404 else E_NU_RASPUNDE)
	except URLError as e:
		motiv = getattr(e, "reason", None)
		if isinstance(motiv, ssl.SSLError):
			_jurnal("certificat sau TLS la %s: %s" % (I.gazdaAdresei(adresa), type(motiv).__name__))
			raise EroareIptv(E_CERTIFICAT)
		_jurnal("legatura la %s: %s" % (I.gazdaAdresei(adresa), type(motiv).__name__))
		raise EroareIptv(E_NU_RASPUNDE)
	except (socket.timeout, socket.error, ssl.SSLError, ValueError, OSError) as e:
		_jurnal("legatura la %s: %s" % (I.gazdaAdresei(adresa), type(e).__name__))
		raise EroareIptv(E_NU_RASPUNDE)


def _text(octeti):
	if octeti[:3] == b"\xef\xbb\xbf":
		octeti = octeti[3:]
	try:
		return octeti.decode("utf-8")
	except UnicodeDecodeError:
		return octeti.decode("latin-1")


def _json(octeti, eroare):
	try:
		return json.loads(_text(octeti))
	except ValueError:
		raise EroareIptv(eroare)


# ------------------------------------------------------------------ M3U

def _atributeExtinf(text):
	"""Atributele cheie="valoare" dintr-un rand #EXTINF. Analiza manuala, liniara: fiecare pas avanseaza indexul, niciodata nu se
	intoarce peste ce a citit (un regex cu grupuri pe un rand ostil lua secunde)."""
	rezultat = {}
	i, n = 0, len(text)
	while i < n:
		while i < n and text[i] in " \t":
			i += 1
		start = i
		while i < n and (text[i].isalnum() or text[i] in "_-"):
			i += 1
		if i == start:
			i += 1
			continue
		cheie = text[start:i]
		if i + 1 >= n or text[i] != "=" or text[i + 1] != '"':
			continue
		i += 2
		start = i
		while i < n and text[i] != '"':
			i += 1
		if i >= n:
			break
		rezultat[cheie.lower()] = text[start:i]
		i += 1
	return rezultat


def _desparteExtinf(rand):
	"""Rand #EXTINF:-1 a="b",Nume -> (atribute, nume). Virgula numelui e prima din afara ghilimelelor; valorile pot avea virgule."""
	rest = rand[8:] if rand[:8].upper() == "#EXTINF:" else ""
	in_ghilimele = False
	for i, c in enumerate(rest):
		if c == '"':
			in_ghilimele = not in_ghilimele
		elif c == "," and not in_ghilimele:
			return _atributeExtinf(rest[:i]), rest[i + 1:].strip()
	return _atributeExtinf(rest), ""


def _m3u(flux, info):
	from Components.HdsIptvCitire import randuri
	atribute, nume, grupa, antete = {}, "", "", {}
	for octeti in randuri(flux):
		rand = _text(octeti).strip().lstrip("\ufeff")
		if not rand:
			continue
		mare = rand.upper()
		if mare.startswith("#EXTM3U"):
			info["antet"] = True
			a = _atributeExtinf(rand)
			url = (a.get("url-tvg") or a.get("x-tvg-url") or "").split(",", 1)[0].strip()
			if I.adresaListaBuna(url):
				info["epg_url"] = url
		elif mare.startswith("#EXTINF:"):
			info["antet"] = True
			atribute, nume = _desparteExtinf(rand)
			antete = {}
		elif mare.startswith("#EXTGRP:"):
			grupa = rand[8:].strip()
		elif mare.startswith("#EXTVLCOPT:"):
			k, _, v = rand[11:].partition("=")
			k = {"http-user-agent": "User-Agent", "http-referrer": "Referer", "http-referer": "Referer"}.get(k.lower())
			if k:
				antete.update(anteteCurate({k: v}))
		elif mare.startswith("#EXTHTTP:"):
			try:
				antete.update(anteteCurate(json.loads(rand[9:])))
			except ValueError:
				pass
		elif rand.startswith("#"):
			continue
		else:
			url, _, coada = rand.partition("|")
			antete.update(anteteCurate(dict(parse_qsl(coada, keep_blank_values=True))))
			adresa = I.fluxBun(url)
			if adresa:
				yield {"nume": nume or atribute.get("tvg-name") or "", "grupa": atribute.get("group-title") or grupa,
					"tvg_id": atribute.get("tvg-id") or "", "logo": atribute.get("tvg-logo") or "", "antete": antete, "adresa": adresa}
			else:
				info["sarite"] = info.get("sarite", 0) + 1
			atribute, nume, grupa, antete = {}, "", "", {}


def citesteM3U(text):
	import io
	info = {}
	rez = list(_m3u(io.BytesIO(text.encode("utf-8")), info))
	return rez, info.get("sarite", 0), info.get("antet", False)


_EXT_FILM = (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm")


def _eFilm(adresa):
	"""Un film dintr-un playlist care le amesteca (dupa sfarsitul adresei, fara parametri): la plafon canalele raman intai."""
	return adresa.split("?", 1)[0].lower().endswith(_EXT_FILM)


def _decodeazaRef(text):
	"""Inversul lui eServiceReference::encode, pentru calea si numele dintr-un rand de buchet."""
	rez = []
	i, n = 0, len(text)
	while i < n:
		c = text[i]
		if c == "%" and i + 2 < n + 0 and text[i + 1:i + 3].isalnum():
			try:
				rez.append(chr(int(text[i + 1:i + 3], 16)))
				i += 3
				continue
			except ValueError:
				pass
		rez.append(c)
		i += 1
	return "".join(rez)


def citesteBuchet(text):
	"""O lista Enigma2 de la furnizor (un fisier de buchet): randuri #SERVICE cu flux, #DESCRIPTION cu numele, marcajele sunt grupele.
	Aceeasi forma ca citesteM3U. Canalele DVB fara adresa nu au ce cauta aici si se sar."""
	canale = []
	sarite = 0
	grupa = ""
	inceput = 0
	lungime = len(text)
	ultimul = None
	while inceput < lungime:
		sfarsit = text.find("\n", inceput)
		if sfarsit < 0:
			sfarsit = lungime
		rand = text[inceput:sfarsit].strip()
		inceput = sfarsit + 1
		if len(rand) > MAX_RAND:
			continue
		if rand.startswith("#SERVICE "):
			ultimul = None
			parti = rand[9:].split(":")
			if len(parti) < 11:
				sarite += 1
				continue
			if parti[1] == "64":
				grupa = _decodeazaRef(":".join(parti[11:])).strip()
				ultimul = "marcaj"
				continue
			adresa = I.fluxBun(_decodeazaRef(parti[10]))
			if adresa is None:
				sarite += 1
				continue
			ultimul = {"nume": _decodeazaRef(":".join(parti[11:])).strip(), "grupa": grupa, "tvg_id": "", "adresa": adresa}
			canale.append(ultimul)
		elif rand.startswith("#DESCRIPTION "):
			if ultimul == "marcaj":
				grupa = rand[13:].strip()
			elif ultimul is not None:
				ultimul["nume"] = rand[13:].strip()
			ultimul = None
	return canale, sarite, True


def canaleDinM3U(octeti, filtru=None):
	"""Un playlist M3U sau o lista Enigma2. -> (canale pentru HdsIptvSurse.scrieCanale, cate s-au taiat la plafon, cate s-au sarit).
	Arunca EroareIptv daca nu e lista."""
	text = _text(octeti)
	inceput = text[:256].lstrip()
	if inceput.startswith("<"):
		raise EroareIptv(E_NU_E_LISTA)
	if inceput.startswith("#NAME") or inceput.startswith("#SERVICE"):
		lista, sarite, are_antet = citesteBuchet(text)
	else:
		import io
		rez, info = _playlistFlux(io.BytesIO(octeti), filtru)
		return rez, info["taiate"], info["sarite"]
	if not lista:
		raise EroareIptv(E_FARA_CANALE if are_antet else E_NU_E_LISTA)
	# la plafon raman intai canalele, apoi filmele
	vii = [c for c in lista if not _eFilm(c["adresa"])]
	filme = [c for c in lista if _eFilm(c["adresa"])]
	ordonate = vii + filme
	filtru = filtru or I.Filtru()
	vazute = {}
	rez = []
	for c in ordonate:
		_directa, bun = I.adresaDirecta(c["adresa"])
		if not bun:
			sarite += 1
			continue
		nume = I.numeCurat(c["nume"]) or I.numeCurat(c["adresa"].rsplit("/", 1)[-1]) or I.gazdaAdresei(c["adresa"])
		# cheia, inaintea filtrului: numara duplicatele in ordinea listei, deci canalul o pastreaza orice s-ar ascunde
		cheie = I.cheieDinNume(c["tvg_id"], nume, vazute)
		grupa = I.numeCurat(c["grupa"])
		if filtru.primeste(grupa, cheie, len(rez) >= I.MAX_CANALE):
			rez.append([cheie, nume, grupa, c["adresa"]])
	if not rez and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE)
	return rez, filtru.taiate, sarite


def _playlistFlux(flux, filtru=None):
	info, vii, filme, vazute = {}, [], [], {}
	sarite = 0
	filtru = filtru or I.Filtru()
	for c in _m3u(flux, info):
		lista = filme if _eFilm(c["adresa"]) else vii
		plafon = MAX_FILME if lista is filme else I.MAX_CANALE
		if not I.adresaDirecta(c["adresa"])[1]:
			sarite += 1
			continue
		nume = I.numeCurat(c["nume"]) or I.numeCurat(c["adresa"].rsplit("/", 1)[-1]) or I.gazdaAdresei(c["adresa"])
		# cheia, inaintea filtrului: numara duplicatele in ordinea listei, deci canalul o pastreaza orice s-ar ascunde
		cheie = I.cheieDinNume(c["tvg_id"], nume, vazute)
		grupa = I.numeCurat(c["grupa"])
		if not filtru.primeste(grupa, cheie, len(lista) >= plafon):
			continue
		meta = {"tvg_id": c["tvg_id"][:256], "logo": c["logo"][:I.MAX_ADRESA], "antete": c["antete"]}
		lista.append([cheie, nume, grupa, c["adresa"], meta])
	loc_filme = max(0, I.MAX_CANALE - len(vii))
	rez = vii + filme[:loc_filme]
	if not rez and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE if info.get("antet") else E_NU_E_LISTA)
	return rez, {"taiate": filtru.taiate + max(0, len(filme) - loc_filme), "sarite": sarite + info.get("sarite", 0), "epg_url": info.get("epg_url", "")}


def aducePlaylist(s):
	from Components.HdsIptvCitire import CuInceput
	adresa = s.get("adresa") or ""
	if I.adresaListaBuna(adresa) is None:
		raise EroareIptv(E_ADRESA)
	filtru = I.Filtru(s)
	try:
		with open(adresa, "rb") if adresa.startswith("/") else deschide(adresa, anteteSursa(s)) as f:
			prima, inceput = b"", time.monotonic()
			while len(prima) < 512 and b"\n" not in prima:
				if time.monotonic() - inceput > TERMEN_S:
					raise EroareIptv(E_NU_RASPUNDE)
				b = getattr(f, "read1", f.read)(512 - len(prima))
				if not b:
					break
				prima += b
			flux = CuInceput(prima, f)
			if prima.lstrip(b"\xef\xbb\xbf \t\r\n").startswith((b"#NAME", b"#SERVICE")):
				b = flux.read(MAX_LISTA + 1)
				if len(b) > MAX_LISTA:
					raise EroareIptv(E_PREA_MARE)
				canale, taiate, sarite = canaleDinM3U(b, filtru)
				info = {"taiate": taiate, "sarite": sarite}
			else:
				canale, info = _playlistFlux(flux, filtru)
	except OSError:
		raise EroareIptv(E_FISIER if adresa.startswith("/") else E_NU_RASPUNDE)
	except ValueError as e:
		raise EroareIptv(E_NU_RASPUNDE if str(e) == "termen" else E_PREA_MARE)
	info["fara_https"] = not adresa.startswith("/") and not I.fluxCriptat(adresa)
	info["catalog"] = filtru.catalog()
	return canale, info


# ------------------------------------------------------------------ Xtream

def _baze(server):
	"""Adresele de incercat, HTTPS intai cand omul n-a ales schema."""
	d = I.desparteServer(server)
	if d is None:
		raise EroareIptv(E_ADRESA)
	schema, gazda, port, cale = d
	loc = gazda + (":" + port if port else "")
	if schema:
		return ["%s://%s%s" % (schema, loc, cale)]
	return ["https://%s%s" % (loc, cale), "http://%s%s" % (loc, cale)]


def _apiXtream(baza, utilizator, parola, actiune=None, maxim=MAX_LISTA, termen=TERMEN_S, antete=None):
	parametri = {"username": utilizator, "password": parola}
	if actiune:
		parametri["action"] = actiune
	return descarca("%s/player_api.php?%s" % (baza, urlencode(parametri)), antete=antete, maxim=maxim, termen=termen)


def _urlXtream(s, actiune=None, parametri=None):
	baza = s.get("baza") or _baze(s.get("server") or "")[0]
	q = {"username": s.get("utilizator") or "", "password": s.get("parola") or ""}
	if actiune:
		q["action"] = actiune
	q.update(parametri or {})
	return "%s/player_api.php?%s" % (baza, urlencode(q))


def listaXtream(s, actiune, parametri=None):
	from Components.HdsIptvCitire import listaJson
	try:
		with deschide(_urlXtream(s, actiune, parametri), anteteSursa(s)) as f:
			for obj in listaJson(f):
				yield obj
	except ValueError:
		raise EroareIptv(E_NU_E_CONT)


def dateXtream(s, actiune, parametri=None):
	return _json(descarca(_urlXtream(s, actiune, parametri), anteteSursa(s), maxim=2 * 1024 * 1024), E_NU_E_CONT)


def _stareCont(s):
	"""Ce spune contul Xtream cand un canal nu porneste: textul potrivit sau None, cand contul e bun sau nu se poate afla."""
	if s.get("fel") != "xtream":
		return None
	try:
		date = _json(_apiXtream(s.get("baza") or "", s.get("utilizator") or "", s.get("parola") or "",
			maxim=65536, termen=TERMEN_ADRESA_S, antete=anteteSursa(s)), E_NU_E_CONT)
		info, _srv = _verificaLogare(date)
		if int(info.get("max_connections") or 0) > 0 and int(info.get("active_cons") or 0) >= int(info["max_connections"]):
			return E_CONEXIUNI
	except EroareIptv as e:
		if e.mesaj in (E_REFUZ, E_EXPIRAT):
			return e.pentruOm()
	except (TypeError, ValueError):
		pass
	return None


def mesajRedare(s, mesaj):
	if mesaj not in (E_REFUZ, E_NU_RASPUNDE):
		return mesaj
	return _stareCont(s) or mesaj


def mesajEroareRedare(s, e):
	"""Un canal n-a pornit: -> (ce i se spune omului, e o problema a sursei si nu a canalului). Sensul unui cod se ia cat se poate din
	raspunsul contului: 403 singur nu inseamna parola gresita, iar 509 nu e un cod standard."""
	cod = e.cod
	if e.mesaj == E_CANAL_LIPSA or cod in (404, 410):
		return E_CANAL_LIPSA, False
	if cod == 429:
		return E_PREA_MULTE_CERERI, True
	if cod in COD_TEMPORAR:
		return _tradus(E_SERVER_CAZUT) % cod, True
	if cod in (403, 509):
		return _stareCont(s) or _tradus(E_REFUZ_REDARE) % cod, True
	return mesajRedare(s, e.pentruOm()), True


def _verificaLogare(date):
	if not isinstance(date, dict) or not isinstance(date.get("user_info"), dict):
		raise EroareIptv(E_NU_E_CONT)
	info = date["user_info"]
	if str(info.get("auth", "")) != "1":
		raise EroareIptv(E_REFUZ)
	try:
		expira = max(0, int(info.get("exp_date") or 0))
	except (ValueError, TypeError):
		expira = 0
	stare = str(info.get("status") or "Active").lower()
	if stare not in ("active", "activ"):
		raise EroareIptv(E_EXPIRAT, expira)
	if 0 < expira <= time.time():
		raise EroareIptv(E_EXPIRAT, expira)
	return info, date.get("server_info") if isinstance(date.get("server_info"), dict) else {}


def xtreamConecteaza(s):
	"""Logarea. Incearca HTTPS, apoi HTTP; dupa HTTP, portul HTTPS spus de server. -> (baza, user_info, server_info)."""
	server, utilizator, parola = s.get("server") or "", s.get("utilizator") or "", s.get("parola") or ""
	eroare = None
	for baza in _baze(server):
		try:
			date = _json(_apiXtream(baza, utilizator, parola, maxim=2 * 1024 * 1024, antete=anteteSursa(s)), E_NU_E_CONT)
			info, srv = _verificaLogare(date)
		except EroareIptv as e:
			if e.mesaj in (E_REFUZ, E_EXPIRAT):
				raise
			eroare = e
			continue
		if baza.startswith("http://"):
			https = str(srv.get("https_port") or "")
			d = I.desparteServer(baza)
			if I.portBun(https) and https != "0" and d is not None:
				sigura = "https://%s:%s%s" % (d[1], https, d[3])
				try:
					date2 = _json(_apiXtream(sigura, utilizator, parola, termen=6, antete=anteteSursa(s)), E_NU_E_CONT)
					info, srv = _verificaLogare(date2)
					baza = sigura
				except EroareIptv as e:
					if e.mesaj == E_REFUZ:
						raise
		return baza, info, srv
	raise eroare or EroareIptv(E_NU_RASPUNDE)


def _extensieVie(info):
	formate = info.get("allowed_output_formats")
	if isinstance(formate, list) and formate and "ts" not in formate and "m3u8" in formate:
		return "m3u8"
	return "ts"


def _categorii(date):
	rez = {}
	for c in date:
		if isinstance(c, dict):
			rez[str(c.get("category_id"))] = I.numeCurat(c.get("category_name"))
		if len(rez) >= I.MAX_GRUPE:
			break
	return rez


def _categoriiXtream(s, actiune):
	try:
		return _categorii(listaXtream(s, actiune))
	except (EroareIptv, OSError, ValueError):
		return {}


def _idNumeric(v):
	v = str(v if v is not None else "").strip()
	return v if v.isdigit() and len(v) <= 12 else None


def _conexiuni(info):
	"""Cate conexiuni permite contul (max_connections); 1 cand nu spune."""
	try:
		return max(1, int(info.get("max_connections") or 1))
	except (TypeError, ValueError):
		return 1


def aduceXtream(s):
	"""Canalele vii ale contului. -> (canale, informatii de pus in sursa)."""
	baza, info, _srv = xtreamConecteaza(s)
	utilizator, parola = s.get("utilizator") or "", s.get("parola") or ""
	cont = dict(s, baza=baza)
	categorii = _categoriiXtream(cont, "get_live_categories")
	fluxuri = listaXtream(cont, "get_live_streams")
	canale = []
	sarite = 0
	filtru = I.Filtru(s)
	for f in fluxuri:
		if not isinstance(f, dict):
			continue
		sid = _idNumeric(f.get("stream_id"))
		nume = I.numeCurat(f.get("name"))
		if sid is None or not nume:
			sarite += 1
			continue
		grupa = categorii.get(str(f.get("category_id")), "")
		if not filtru.primeste(grupa, "l" + sid, len(canale) >= I.MAX_CANALE):
			continue
		canale.append(["l" + sid, nume, grupa, "",
			{"tvg_id": str(f.get("epg_channel_id") or "")[:256], "logo": str(f.get("stream_icon") or "")[:I.MAX_ADRESA]}])
	if not canale and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE)
	del fluxuri
	_filmeXtream(baza, utilizator, parola, canale, cont, filtru)
	try:
		expira = int(info.get("exp_date") or 0)
	except (TypeError, ValueError):
		expira = 0
	return canale, {"taiate": filtru.taiate, "sarite": sarite, "catalog": filtru.catalog(), "baza": baza, "format": _extensieVie(info),
		"fara_https": not I.fluxCriptat(baza), "expira": expira, "conexiuni": _conexiuni(info),
		"epg_url": "%s/xmltv.php?%s" % (baza, urlencode({"username": utilizator, "password": parola}))}


def _filmeXtream(baza, utilizator, parola, canale, s=None, filtru=None):
	try:
		return _filmeXtreamLucru(baza, utilizator, parola, canale, s, filtru)
	except (EroareIptv, OSError, ValueError):
		return 0


def _filmeXtreamLucru(baza, utilizator, parola, canale, s=None, filtru=None):
	"""Filmele contului, dupa canale, cat incap sub plafon, in grupe cu numele categoriei. Cine nu da filme nu strica lista: canalele
	raman. Serialele cer o cerere pentru fiecare serial, deci nu intra aici. -> cate s-au taiat."""
	try:
		s = s or {"baza": baza, "utilizator": utilizator, "parola": parola}
		categorii = _categoriiXtream(s, "get_vod_categories")
		filme = listaXtream(s, "get_vod_streams")
	except EroareIptv as e:
		_jurnal("filmele: %s" % type(e).__name__)
		return 0
	filtru = filtru or I.Filtru()
	inainte = filtru.taiate
	loc = min(MAX_FILME, I.MAX_CANALE - len(canale))
	for f in filme:
		if not isinstance(f, dict):
			continue
		sid = _idNumeric(f.get("stream_id"))
		ext = str(f.get("container_extension") or "mp4").lower()
		nume = I.numeCurat(f.get("name"))
		if sid is None or not nume or not ext.isalnum() or len(ext) > 5:
			continue
		cat = categorii.get(str(f.get("category_id")), "")
		film = _tradus(T_FILME)
		grupa = I.numeCurat("%s: %s" % (film, cat)) if cat else film
		cheie = "v%s.%s" % (sid, ext)
		if not filtru.primeste(grupa, cheie, loc <= 0):
			continue
		loc -= 1
		canale.append([cheie, nume, grupa, "", {"logo": str(f.get("stream_icon") or "")[:I.MAX_ADRESA]}])
	return filtru.taiate - inainte


T_FILME = N_("Film")


def _tradus(text):
	try:
		return _(text)
	except NameError:  # probele de pe PC
		return text


def xtreamAdresa(s, cheie):
	"""Adresa unui canal sau film: <baza>/live/<utilizator>/<parola>/<id>.<format>, <baza>/movie/.../<id>.<extensie>. Cheia: l<id>,
	v<id>.<extensie> (cheile le-a facut aduceXtream)."""
	baza = s.get("baza")
	if not baza or not cheie:
		return None
	cont = "%s/%s" % (quote(s.get("utilizator") or "", safe=""), quote(s.get("parola") or "", safe=""))
	if cheie[0] == "l" and _idNumeric(cheie[1:]) is not None:
		return "%s/live/%s/%s.%s" % (baza, cont, cheie[1:], s.get("format") or "ts")
	if cheie[0] in ("v", "e"):
		sid, _punct, ext = cheie[1:].partition(".")
		if _idNumeric(sid) is not None and ext.isalnum() and len(ext) <= 5:
			return "%s/%s/%s/%s.%s" % (baza, "series" if cheie[0] == "e" else "movie", cont, sid, ext)
	return None


# ------------------------------------------------------------------ Stalker

# Portalul raspunde numai unui client care se prezinta ca decodor: atat cere protocolul lui obisnuit, cu adresa MAC data de furnizor.
_AGENT_PORTAL = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
_CAI_API = ("/portal.php", "/server/load.php", "/stalker_portal/server/load.php")


def _antetePortal(s, baza, jeton=None):
	mac = s.get("mac") or ""
	antete = {
		"User-Agent": s.get("user_agent") or _AGENT_PORTAL, "X-User-Agent": "Model: MAG250; Link: WiFi", "Referer": s.get("referer") or baza + "/",
		"Cookie": "mac=%s; stb_lang=en; timezone=Europe/Bucharest" % quote(mac, safe=":"),
	}
	if jeton:
		antete["Authorization"] = "Bearer %s" % jeton
	return antete


def _bazePortal(portal):
	"""Portalul scris de om ('.../c/', '.../stalker_portal/c/', sau numai gazda) -> radacinile de incercat."""
	rez = []
	for baza in _baze(portal):
		for sfarsit in ("/c", "/stalker_portal/c", "/stalker_portal"):
			if baza.endswith(sfarsit):
				baza = baza[:-len(sfarsit)]
				break
		if baza not in rez:
			rez.append(baza)
	return rez


def _cerePortal(s, api, baza, parametri, jeton=None, maxim=MAX_LISTA, termen=TERMEN_S):
	date = dict(parametri, JsHttpRequest="1-xml")
	octeti = descarca("%s?%s" % (api, urlencode(date)), antete=_antetePortal(s, baza, jeton), maxim=maxim, termen=termen)
	r = _json(octeti, E_NU_E_PORTAL)
	if not isinstance(r, dict) or "js" not in r:
		raise EroareIptv(E_NU_E_PORTAL)
	return r["js"]


def stalkerConecteaza(s, termen=TERMEN_S):
	"""Strangerea de mana: gaseste calea API a portalului si cere jetonul, apoi profilul. -> (baza, api, jeton)."""
	if not I.macBun(s.get("mac") or ""):
		raise EroareIptv(E_MAC)
	eroare = None
	for baza in _bazePortal(s.get("portal") or ""):
		for cale in _CAI_API:
			api = baza + cale
			try:
				js = _cerePortal(s, api, baza, {"type": "stb", "action": "handshake", "token": ""}, termen=termen)
				jeton = js.get("token") if isinstance(js, dict) else None
				if not jeton:
					raise EroareIptv(E_MAC)
				profil = _cerePortal(s, api, baza, {"type": "stb", "action": "get_profile", "hd": "1"}, jeton, termen=termen)
				if isinstance(profil, dict) and str(profil.get("status", "0")) not in ("0", ""):
					raise EroareIptv(E_MAC)
				return baza, api, jeton
			except EroareIptv as e:
				if e.mesaj == E_MAC:
					raise
				eroare = e
	raise eroare or EroareIptv(E_NU_E_PORTAL)


def aduceStalker(s):
	"""Canalele portalului. Cheia: c<id>; a patra coloana e comanda canalului, ceruta la pornire de create_link. -> (canale, informatii)."""
	baza, api, jeton = stalkerConecteaza(s)
	grupe = {}
	js = _cerePortal(s, api, baza, {"type": "itv", "action": "get_genres"}, jeton)
	if isinstance(js, list):
		for g in js:
			if isinstance(g, dict):
				grupe[str(g.get("id"))] = I.numeCurat(g.get("title"))
	js = _cerePortal(s, api, baza, {"type": "itv", "action": "get_all_channels"}, jeton)
	lista = js.get("data") if isinstance(js, dict) else js
	if not isinstance(lista, list):
		raise EroareIptv(E_NU_E_PORTAL)
	canale = []
	sarite = 0
	filtru = I.Filtru(s)
	for c in lista:
		if not isinstance(c, dict):
			continue
		cid = _idNumeric(c.get("id"))
		nume = I.numeCurat(c.get("name"))
		comanda = c.get("cmd")
		if cid is None or not nume or not isinstance(comanda, str) or not comanda or len(comanda) > I.MAX_ADRESA:
			sarite += 1
			continue
		grupa = grupe.get(str(c.get("tv_genre_id")), "")
		if not filtru.primeste(grupa, "c" + cid, len(canale) >= I.MAX_CANALE):
			continue
		canale.append(["c" + cid, nume, grupa, comanda])
	if not canale and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE)
	return canale, {"taiate": filtru.taiate, "sarite": sarite, "catalog": filtru.catalog(), "baza": baza, "fara_https": not I.fluxCriptat(baza)}


def _adresaDinComanda(text):
	"""Raspunsul create_link: 'ffmpeg http://...' sau numai adresa. -> adresa buna sau None."""
	text = (text or "").strip()
	if " " in text:
		text = text.rsplit(" ", 1)[-1]
	return I.fluxBun(text)


_SESIUNI = {}


def stalkerAdresa(s, comanda):
	"""Adresa unui canal la pornire (create_link): se schimba de fiecare data, deci nu se tine nicaieri. Jetonul se tine in memorie
	si se cere din nou o data, cand portalul nu-l mai primeste. Termen scurt: omul asteapta in fata televizorului."""
	cheie = s.get("id")
	for incercare in (1, 2):
		sesiune = _SESIUNI.get(cheie)
		if sesiune is None:
			baza, api, jeton = stalkerConecteaza(s, termen=TERMEN_ADRESA_S)
			sesiune = _SESIUNI[cheie] = (baza, api, jeton)
		baza, api, jeton = sesiune
		try:
			js = _cerePortal(s, api, baza, {"type": "itv", "action": "create_link", "cmd": comanda, "series": "",
				"forced_storage": "0", "disable_ad": "0", "download": "0"}, jeton, maxim=256 * 1024, termen=TERMEN_ADRESA_S)
			adresa = _adresaDinComanda(js.get("cmd") if isinstance(js, dict) else None)
			if adresa:
				return adresa
		except EroareIptv:
			if incercare == 2:
				raise
		_SESIUNI.pop(cheie, None)
	raise EroareIptv(E_NU_RASPUNDE)


# ------------------------------------------------------------------ ce a scris omul

def verificaDate(fel, date):
	s, eroare = _verificaDate(fel, date)
	if eroare:
		return s, eroare
	if fel == "m3u":
		for v in I.citesteSurse():
			if v.get("fel") == "m3u" and I.identitatePlaylist(v.get("adresa")) == I.identitatePlaylist(s.get("adresa")):
				s["id"] = v["id"]
				break
	veche = I.sursa(s["id"]) or {}
	for cheie in ("user_agent", "referer"):
		v = date.get(cheie, veche.get(cheie, ""))
		if not isinstance(v, str) or not I.textBun(v, 2048):
			return None, E_ANTETE
		s[cheie] = v.strip()
	return s, None


def _verificaDate(fel, date):
	"""Datele scrise de om, verificate la fel pe televizor si in web. La o sursa care exista deja, o parola goala ramane cea veche.
	-> (sursa, None) sau (None, textul erorii, de tradus la afisare)."""
	nume = date.get("nume") or ""
	if not I.textBun(nume, I.MAX_NUME * 2):
		return None, E_NUME
	if fel == "m3u":
		adresa = I.adresaListaBuna(date.get("adresa"))
		if adresa is None:
			return None, E_ADRESA
		return I.sursaNouaM3U(adresa, nume), None
	if fel == "xtream":
		server = (date.get("server") or "").strip()
		utilizator = (date.get("utilizator") or "").strip()
		parola = date.get("parola") or ""
		if I.desparteServer(server) is None:
			return None, E_ADRESA
		if not utilizator or not I.textBun(utilizator):
			return None, E_UTILIZATOR
		if not parola:
			veche = I.sursa(I.idSursa("xtream", server, utilizator))
			parola = (veche or {}).get("parola") or ""
		if not parola or not I.textBun(parola):
			return None, E_PAROLA
		return I.sursaNouaXtream(server, utilizator, parola, nume), None
	if fel == "stalker":
		portal = (date.get("portal") or "").strip()
		mac = (date.get("mac") or "").strip()
		if I.desparteServer(portal) is None:
			return None, E_ADRESA
		if not I.macBun(mac):
			return None, E_FORMA_MAC
		return I.sursaNouaStalker(portal, mac, nume), None
	return None, E_ADRESA


# ------------------------------------------------------------------ o sursa, oricare ar fi

# lista demo: un pachet din feedul imaginii, nu sta in imagine; se ia si se actualizeaza de acolo, fara shell
CALE_DEMO = "/usr/share/enigma2/hds-lista-demo/lista.json"
PACHET_DEMO = "enigma2-plugin-extensions-hds-lista-demo"
TERMEN_OPKG_S = 180


def instaleazaDemo():
	"""opkg update si install: pune pachetul sau il aduce la zi. O eroare lasa lista veche, daca e."""
	for argumente in (["opkg", "update"], ["opkg", "install", PACHET_DEMO]):
		try:
			with open(os.devnull, "wb") as nimic:
				subprocess.call(argumente, stdout=nimic, stderr=nimic, timeout=TERMEN_OPKG_S)
		except (OSError, subprocess.SubprocessError) as e:
			_jurnal("lista demo: %s" % type(e).__name__)


def citesteDemo(cale=None):
	"""Lista demo din pachetul din feed: {"grupe": [{"nume", "canale": [{"nume", "adresa", "pagina", "citat", "atribuire"}]}]}."""
	try:
		with open(cale or CALE_DEMO, encoding="utf-8") as f:
			date = json.load(f)
		return date if isinstance(date, dict) and isinstance(date.get("grupe"), list) else None
	except (IOError, OSError, ValueError):
		return None


def aduceDemo(s, cale=None):
	if cale is None:
		instaleazaDemo()
	date = citesteDemo(cale)
	if date is None:
		raise EroareIptv(E_DEMO)
	canale = []
	vazute = {}
	for g in date["grupe"]:
		if not isinstance(g, dict):
			continue
		grupa = I.numeCurat(g.get("nume"))
		for c in g.get("canale") or ():
			adresa = I.fluxBun(c.get("adresa")) if isinstance(c, dict) else None
			nume = I.numeCurat(c.get("nume")) if isinstance(c, dict) else ""
			if adresa and nume:
				canale.append([I.cheieDinNume(c.get("id") or "", nume, vazute), nume, grupa, adresa])
	if not canale:
		raise EroareIptv(E_FARA_CANALE)
	return canale, {"taiate": 0, "sarite": 0, "fara_https": False}


def aduce(s):
	"""Canalele sursei de la server sau din fisier. -> (canale, informatii de pus in sursa). Arunca EroareIptv."""
	fel = s.get("fel")
	if fel == "m3u":
		return aducePlaylist(s)
	if fel == "xtream":
		return aduceXtream(s)
	if fel == "stalker":
		return aduceStalker(s)
	if fel == "demo":
		return aduceDemo(s)
	raise EroareIptv(E_ADRESA)

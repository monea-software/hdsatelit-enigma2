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

import base64
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import time
import threading
import math
from email.utils import parsedate_to_datetime

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
# 0.7.7 (FLM, FLM2): fara plafonul de 2000 de filme (pus pe 04.11 fara masura). Filmele nu mai stau in lista de canale: ale unui cont
# Xtream se citesc de la furnizor la cerere (aplicatia IPTV, Filme si seriale), ale unui playlist merg din mers in fisierul lor
# (HdsIptvSurse.ScriitorFilme, plafonul I.MAX_FILME_SURSA) si se rasfoiesc la fel. Lista de canale pastreaza plafonul sursei,
# I.MAX_CANALE (masurat pe Octagon SF8008: grupele IPTV se citesc in nucleu numai la deschidere, lib/dvb/db.cpp
# isLazyBouquet, deci reincarcarea buchetelor ramane 2-6 ms si cu 30000 de intrari).

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
E_FORMA_MAC = N_("Adresa MAC trebuie să aibă 12 cifre hexazecimale (0-9, A-F). Exemplu: 00:1A:79:12:34:56. Poți folosi și liniuțe, puncte sau nicio despărțire.")
E_PREA_MULTE = N_("Ai ajuns la numărul cel mai mare de surse. Șterge una ca să poți adăuga alta.")
E_DEMO = N_("Lista demo nu s-a putut descărca. Verifică internetul și încearcă din nou.")
E_DEMO_LIPSA = N_("Lista demo nu este încă în feedul imaginii. Încearcă din nou mai târziu.")
# 0.7.7 (IPX; LinuxSat 164155 #970837, e-mailul 6520): ce inseamna, cine poate tine conexiunile (si un plugin IPTV de pe acelasi receptor,
# cu acelasi cont; o redare abia oprita mai e socotita cateva secunde) si ce face omul; fara cauza data ca sigura
E_CONEXIUNI = N_("Abonamentul IPTV are toate conexiunile ocupate și nu mai permite încă o redare. Le poate folosi alt aparat (telefon, "
	"televizor, alt receptor) sau alt program de pe acest receptor, cu același cont, iar o redare abia oprită mai contează câteva "
	"secunde. Oprește redarea acolo, așteaptă puțin și încearcă din nou.")
E_CANAL_LIPSA = N_("Canalul nu mai este la această adresă. Furnizorul l-a scos sau l-a mutat.")
E_PREA_MULTE_CERERI = N_("S-au făcut prea multe cereri către server. Mai încearcă peste puțin.")
E_REFUZ_REDARE = N_("Furnizorul a refuzat redarea acestui canal (cod %d). Dacă folosești același cont pe alt aparat sau în alt program de "
	"pe acest receptor, oprește redarea acolo, așteaptă câteva secunde și încearcă din nou.")
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
	"""Retry-After: cel mult 300 s; data HTTP cere un ceas deja pus."""
	try:
		valoare = (antete.get("Retry-After") or "0").strip()
		if valoare.isdigit():
			cifre = valoare.lstrip("0") or "0"
			return 300 if len(cifre) > 3 else min(300, int(cifre))
		acum = time.time()
		if time.gmtime(acum).tm_year < 2025:
			return 60
		diferenta = parsedate_to_datetime(valoare).timestamp() - acum
		return int(math.ceil(diferenta)) if 0 <= diferenta <= 300 else 60
	except (AttributeError, TypeError, ValueError, OverflowError, OSError):
		return 60


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
		cod = e.code
		dupa = _dupa(e.headers)
		e.close()
		if cod in (429, 453):
			raise EroareIptv(E_CONEXIUNI, cod=cod, dupa=dupa)
		if cod in (401, 403):
			raise EroareIptv(E_REFUZ, cod=cod, dupa=dupa)
		_jurnal("raspuns %d de la %s" % (cod, I.gazdaAdresei(adresa)))
		raise EroareIptv(E_NU_E_LISTA if cod == 404 else E_NU_RASPUNDE, cod=cod, dupa=dupa)
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


def _eFilm(adresa):
	"""Un film dintr-un playlist care le amesteca (dupa sfarsitul adresei, fara parametri; I.EXT_FILM)."""
	return I.eAdresaFilm(adresa)


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


def canaleDinM3U(octeti, filtru=None, filme=None):
	"""Un playlist M3U sau o lista Enigma2. -> (canale pentru HdsIptvSurse.scrieCanale, cate s-au taiat la plafon, cate s-au sarit).
	Filmele (dupa adresa) nu intra in canale: merg in `filme` (HdsIptvSurse.ScriitorFilme; 0.7.7, FLM2). Arunca EroareIptv daca nu
	e lista."""
	text = _text(octeti)
	inceput = text[:256].lstrip()
	if inceput.startswith("<"):
		raise EroareIptv(E_NU_E_LISTA)
	filme = filme if filme is not None else I.ScriitorFilme()
	if inceput.startswith("#NAME") or inceput.startswith("#SERVICE"):
		lista, sarite, are_antet = citesteBuchet(text)
	else:
		import io
		rez, info = _playlistFlux(io.BytesIO(octeti), filtru, filme)
		return rez, info["taiate"], info["sarite"]
	if not lista:
		raise EroareIptv(E_FARA_CANALE if are_antet else E_NU_E_LISTA)
	filtru = filtru or I.Filtru()
	vazute = {}
	rez = []
	for c in lista:
		_directa, bun = I.adresaDirecta(c["adresa"])
		if not bun:
			sarite += 1
			continue
		nume = I.numeCurat(c["nume"]) or I.numeCurat(c["adresa"].rsplit("/", 1)[-1]) or I.gazdaAdresei(c["adresa"])
		# cheia, inaintea filtrului: numara duplicatele in ordinea listei, deci canalul o pastreaza orice s-ar ascunde
		cheie = I.cheieDinNume(c["tvg_id"], nume, vazute)
		grupa = I.numeCurat(c["grupa"])
		if _eFilm(c["adresa"]):
			# grupele ascunse de om (Grupele) raman ascunse si la filme; grupa lor sta in catalog, ca sa se poata arata iar
			if filtru.primeste(grupa, cheie, False, film=True):
				filme.scrie([cheie, nume, grupa, c["adresa"], {}])
		elif filtru.primeste(grupa, cheie, len(rez) >= I.MAX_CANALE):
			rez.append([cheie, nume, grupa, c["adresa"]])
	if not rez and not filme.scrise and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE)
	return rez, filtru.taiate + filme.taiate, sarite


def _playlistFlux(flux, filtru=None, filme=None):
	"""Playlistul citit pe bucati. 0.7.7 (FLM2, Eduard 16.11 11:01): filmele (dupa adresa) nu mai intra in lista de canale; merg
	din mers in `filme` (HdsIptvSurse.ScriitorFilme, fisierul lor, plafonul lor) si se rasfoiesc in aplicatia IPTV, sub sursa
	lor, si in Filme si seriale. Cheile canalelor si ale filmelor se fac impreuna (aceleasi duplicate), deci nu se calca."""
	info, vii, vazute = {}, [], {}
	sarite = 0
	filtru = filtru or I.Filtru()
	filme = filme if filme is not None else I.ScriitorFilme()
	for c in _m3u(flux, info):
		if not I.adresaDirecta(c["adresa"])[1]:
			sarite += 1
			continue
		nume = I.numeCurat(c["nume"]) or I.numeCurat(c["adresa"].rsplit("/", 1)[-1]) or I.gazdaAdresei(c["adresa"])
		# cheia, inaintea filtrului: numara duplicatele in ordinea listei, deci canalul o pastreaza orice s-ar ascunde
		cheie = I.cheieDinNume(c["tvg_id"], nume, vazute)
		grupa = I.numeCurat(c["grupa"])
		meta = {"tvg_id": c["tvg_id"][:256], "logo": c["logo"][:I.MAX_ADRESA], "antete": c["antete"]}
		if _eFilm(c["adresa"]):
			# grupele ascunse de om (Grupele, de pilda una pentru adulti) raman ascunse si la filme: nici in aplicatia IPTV, nici in
			# Filme si seriale; grupa lor sta in catalogul grupelor, ca sa se poata arata iar
			if filtru.primeste(grupa, cheie, False, film=True):
				filme.scrie([cheie, nume, grupa, c["adresa"], meta])
			continue
		if not filtru.primeste(grupa, cheie, len(vii) >= I.MAX_CANALE):
			continue
		vii.append([cheie, nume, grupa, c["adresa"], meta])
	if not vii and not filme.scrise and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE if info.get("antet") else E_NU_E_LISTA)
	return vii, {"taiate": filtru.taiate + filme.taiate, "sarite": sarite + info.get("sarite", 0), "epg_url": info.get("epg_url", ""),
		"vii": len(vii), "filme": filme.scrise, "taiate_filme": filme.taiate}


def aducePlaylist(s):
	from Components.HdsIptvCitire import CuInceput
	adresa = s.get("adresa") or ""
	if I.adresaListaBuna(adresa) is None:
		raise EroareIptv(E_ADRESA)
	filtru = I.Filtru(s)
	# 0.7.7 (FLM2): filmele listei, in fisierul lor; puse in locul celor vechi numai dupa o citire buna
	filme = I.ScriitorFilme(s.get("id"))
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
				canale, taiate, sarite = canaleDinM3U(b, filtru, filme)
				info = {"taiate": taiate, "sarite": sarite, "vii": len(canale), "filme": filme.scrise, "taiate_filme": filme.taiate}
			else:
				canale, info = _playlistFlux(flux, filtru, filme)
	except OSError:
		filme.renunta()
		raise EroareIptv(E_FISIER if adresa.startswith("/") else E_NU_RASPUNDE)
	except ValueError as e:
		filme.renunta()
		raise EroareIptv(E_NU_RASPUNDE if str(e) == "termen" else E_PREA_MARE)
	except BaseException:
		filme.renunta()
		raise
	filme.gata()
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


# 0.7.5 (IPI): starea contului Xtream aratata omului (Screens/IptvSetup.py, web /api/iptv-cont). Se cere NUMAI cand omul deschide IPTV
# pe televizor sau in web (config.usage.hds_iptv_cont), niciodata in fundal; raspunsul se tine minte un minut pe sursa.
T_CONT_ACTIV = N_("Contul e activ până la %s (%s).")
T_CONT_ACTIV_FARA_DATA = N_("Contul e activ, fără dată de expirare.")
T_CONT_EXPIRAT = N_("Contul a expirat la %s.")
T_CONT_OPRIT = N_("Contul e oprit la furnizor (%s).")
T_CONT_REFUZAT = N_("Serverul nu mai primește utilizatorul și parola.")
T_CONT_ZILE = N_("încă %d zile")
T_CONT_ZILE_DE = N_("încă %d de zile")
T_CONT_O_ZI_INTREAGA = N_("încă o zi")
T_CONT_O_ZI = N_("mai puțin de o zi")
T_CONT_CONEXIUNI = N_("Conexiuni: %d folosite acum din %d.")
T_CONT_PROBA = N_("Cont de probă.")
PASTRARE_CONT_S = 60
_conturi = {}


def stareContDinInfo(info, acum=None):
	"""user_info (player_api.php) -> {"stare": activ|expirat|oprit|refuzat, "expira", "active", "maxim", "proba"}. Fara date de acces."""
	acum = time.time() if acum is None else acum
	if not isinstance(info, dict):
		return {"stare": "necunoscut"}

	def _int(cheie):
		try:
			return max(0, int(info.get(cheie) or 0))
		except (TypeError, ValueError):
			return 0
	rez = {"expira": _int("exp_date"), "active": _int("active_cons"), "maxim": _int("max_connections"),
		"proba": str(info.get("is_trial", "0")).strip() in ("1", "true", "True")}
	stare = str(info.get("status") or "Active").strip().lower()
	if str(info.get("auth", "1")) != "1":
		rez["stare"] = "refuzat"
	elif 0 < rez["expira"] <= acum or stare == "expired":
		rez["stare"] = "expirat"
	elif stare not in ("active", "activ"):
		rez["stare"] = "oprit"
		rez["stare_server"] = stare[:20]
	else:
		rez["stare"] = "activ"
	return rez


def textStareCont(d, acum=None):
	"""Propozitia pentru om (o singura linie), din stareContDinInfo; "" cand nu se stie nimic."""
	acum = time.time() if acum is None else acum
	stare = (d or {}).get("stare")
	data = time.strftime("%d.%m.%Y %H:%M", time.localtime(d["expira"])) if (d or {}).get("expira") else ""
	if stare == "refuzat":
		return _tradus(T_CONT_REFUZAT)
	if stare == "expirat":
		return _tradus(T_CONT_EXPIRAT) % (data or "?")
	if stare == "oprit":
		parti = [_tradus(T_CONT_OPRIT) % d.get("stare_server", "")]
	elif stare == "activ":
		if data:
			zile = int((d["expira"] - acum) // 86400)
			if zile < 1:
				rest = _tradus(T_CONT_O_ZI)
			elif zile == 1:
				rest = _tradus(T_CONT_O_ZI_INTREAGA)
			else:
				# romana: 2-19 zile, 20 de zile, 101 zile, 120 de zile
				rest = _tradus(T_CONT_ZILE_DE if zile % 100 >= 20 or (zile >= 100 and zile % 100 == 0) else T_CONT_ZILE) % zile
			parti = [_tradus(T_CONT_ACTIV) % (data, rest)]
		else:
			parti = [_tradus(T_CONT_ACTIV_FARA_DATA)]
	else:
		return ""
	if d.get("maxim"):
		parti.append(_tradus(T_CONT_CONEXIUNI) % (d.get("active") or 0, d["maxim"]))
	if d.get("proba"):
		parti.append(_tradus(T_CONT_PROBA))
	return " ".join(parti)


def stareContXtream(s, proaspat=False):
	"""Intreaba serverul (o cerere mica, 64 KB, termenul unei adrese de canal). -> dict de mai sus sau None (nu e Xtream, oprita,
	serverul nu raspunde). Ruleaza pe un fir al apelantului, nu pe firul TV."""
	if not isinstance(s, dict) or s.get("fel") != "xtream":
		return None
	try:
		from Components.config import config
		if not config.usage.hds_iptv_cont.value:
			return None
	except (AttributeError, KeyError, ImportError):
		pass
	sid = str(s.get("id") or "")
	vechi = _conturi.get(sid)
	if vechi and not proaspat and time.time() - vechi[0] < PASTRARE_CONT_S:
		return vechi[1]
	try:
		date = _json(_apiXtream(s.get("baza") or _baze(s.get("server") or "")[0], s.get("utilizator") or "", s.get("parola") or "",
			maxim=65536, termen=TERMEN_ADRESA_S, antete=anteteSursa(s)), E_NU_E_CONT)
	except EroareIptv as e:
		if e.mesaj == E_REFUZ:
			rez = {"stare": "refuzat"}
		else:
			return None
	except (OSError, ValueError, TypeError):
		return None
	else:
		rez = stareContDinInfo(date.get("user_info") if isinstance(date, dict) else None)
		if rez.get("stare") == "necunoscut":
			return None
	_conturi[sid] = (time.time(), rez)
	if len(_conturi) > 32:
		_conturi.pop(next(iter(_conturi)))
	return rez


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
	"""Canalele vii ale contului. -> (canale, informatii de pus in sursa). Filmele si serialele nu intra in lista de canale: stau
	toate in 'Filme și seriale' (Components/HdsVod.SursaXtream, citite la cerere, pe categorii). Pana in 0.7.6 intrau aici cel
	mult 2000 de filme, primele din lista furnizorului, iar cartela spunea 'Filmele: au intrat 2000 din 9000' (Eduard 16.11
	09:28: 'de ce nu intra toate?'). Un film pus de om in Favorite merge mai departe: adresa lui se face din cheie
	(xtreamAdresa), iar randul lui ramane in canalele sursei (HdsIptvSurse.pastreazaDinBuchete)."""
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
		meta = {"tvg_id": str(f.get("epg_channel_id") or "")[:256], "logo": str(f.get("stream_icon") or "")[:I.MAX_ADRESA]}
		zile = zileArhiva(f)
		if zile:
			meta["arhiva"] = zile  # 0.7.5 (IPI): emisiunile trecute (Screens/HdsIptvArhiva.py)
		canale.append(["l" + sid, nume, grupa, "", meta])
	if not canale and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE)
	del fluxuri
	try:
		expira = int(info.get("exp_date") or 0)
	except (TypeError, ValueError):
		expira = 0
	return canale, {"taiate": filtru.taiate, "sarite": sarite, "catalog": filtru.catalog(), "baza": baza, "format": _extensieVie(info),
		"vii": len(canale), "filme": 0, "taiate_filme": 0,
		"fara_https": not I.fluxCriptat(baza), "expira": expira, "conexiuni": _conexiuni(info),
		"epg_url": "%s/xmltv.php?%s" % (baza, urlencode({"username": utilizator, "password": parola}))}


# 0.7.7 (BQT, Ozgur e-mailul 6514, Vu+ Solo SE): cartela unei liste taiate spune exact ce a intrat, canalele TV si filmele
# separat; pana in 0.7.6 spunea „au intrat primele 30000” si cand se taiasera numai filmele peste 2000, iar omul credea ca
# e o greseala. Pe televizor (Screens/IptvSetup.mesajSursa) si in pagina web (internet_web.stareIptv, taiate_text).
T_TAIATE_CANALE = N_("Canalele TV: au intrat %(intrate)d din %(toate)d.")
T_TAIATE_FILME = N_("Filmele: au intrat %(intrate)d din %(toate)d.")


def textTaiate(p, tr=None):
	"""Propozitiile despre ce n-a incaput din lista sursei `p` (HdsIptvSurse.publica), "" cand nu s-a taiat nimic. O lista
	adusa de o versiune veche (fara campurile vii / filme / taiate_filme) primeste textul general al grupelor."""
	tr = tr or _tradus
	taiate = int(p.get("taiate") or 0)
	if taiate <= 0:
		return ""
	# 0.7.7 (FLM): filmele unui cont Xtream nu se taie (le citeste Filme si seriale de la furnizor), deci nu se socotesc taiate; o
	# sursa Xtream adusa de 0.7.6 (fara campuri, sau cu filmele de atunci) nu mai spune nimic de filme pana la aducerea zilnica
	catalog = p.get("fel") == "xtream"
	if p.get("taiate_filme") is None:
		if catalog:
			return ""
		canale = int(p.get("canale") or 0)
		return tr(I.T_GRUPE_TAIATE) % {"vazute": canale, "toate": canale + taiate}
	filme_taiate = max(0, min(taiate, int(p.get("taiate_filme") or 0)))
	vii, filme = int(p.get("vii") or 0), int(p.get("filme") or 0)
	if catalog:
		taiate -= filme_taiate
		filme = filme_taiate = 0
		if taiate <= 0:
			return ""
	parti = []
	if vii or taiate > filme_taiate:   # o lista numai cu filme nu spune „Canalele TV: 0 din 0”
		parti.append(tr(T_TAIATE_CANALE) % {"intrate": vii, "toate": vii + taiate - filme_taiate})
	if filme or filme_taiate:
		parti.append(tr(T_TAIATE_FILME) % {"intrate": filme, "toate": filme + filme_taiate})
	return " ".join(parti)


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
	arhiva = desparteArhiva(cheie)
	if arhiva is not None:
		# <baza>/timeshift/<utilizator>/<parola>/<minute>/<AAAA-LL-ZZ:HH-MM>/<id>.<format>; ora e cea scrisa de server (ora lui)
		flux, (an, luna, zi, ora, minut), minute = arhiva
		return "%s/timeshift/%s/%d/%s-%s-%s:%s-%s/%s.%s" % (baza, cont, minute, an, luna, zi, ora, minut, flux, s.get("format") or "ts")
	if cheie[0] in ("v", "e"):
		sid, _punct, ext = cheie[1:].partition(".")
		if _idNumeric(sid) is not None and ext.isalnum() and len(ext) <= 5:
			return "%s/%s/%s/%s.%s" % (baza, "series" if cheie[0] == "e" else "movie", cont, sid, ext)
	return None


# ------------------------------------------------------------------ arhiva (0.7.5, IPI): emisiunile trecute ale canalelor Xtream
# Furnizorul tine o arhiva pe canalele cu tv_archive=1 (tv_archive_duration zile). Lista emisiunilor din arhiva se cere NUMAI cand omul
# deschide „Emisiunile trecute” (Screens/HdsIptvArhiva.py, web /api/iptv-arhiva), pe un fir: get_simple_data_table da emisiunile cu
# has_archive=1. O emisiune se reda prin releu (Components/HdsIptvAdrese.py) cu cheia a<id>-<AAAALLZZHHMM>-<minute>; adresa adevarata
# (/timeshift/...) o face xtreamAdresa, cu ora de inceput SCRISA DE SERVER (campul „start”, ora lui), nu socotita pe receptor: altfel o
# zona orara diferita muta emisiunea. Parola nu intra in referinta. Optional: config.usage.hds_iptv_arhiva (Da din fabrica).
_CHEIE_ARHIVA = re.compile(r"^a(\d{1,12})-(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})-(\d{1,4})$")
_START_SERVER = re.compile(r"^\s*(\d{4})-\s?(\d{1,2})-(\d{1,2})[ T:\-](\d{1,2})[:\-](\d{1,2})")
MAX_MINUTE_ARHIVA = 1440
MAX_PROGRAME_ARHIVA = 400


def zileArhiva(f):
	"""Zilele de arhiva ale unui canal din get_live_streams (tv_archive=1 si tv_archive_duration > 0), altfel 0."""
	if not isinstance(f, dict) or str(f.get("tv_archive") or "0").strip() != "1":
		return 0
	try:
		return max(0, min(int(str(f.get("tv_archive_duration") or "0").strip() or 0), 60))
	except (TypeError, ValueError):
		return 0


def cheieArhiva(flux, start_server, minute):
	"""Cheia unei emisiuni din arhiva. flux: id-ul canalului (fara „l”); start_server: campul „start” al serverului
	(„2026-11-13 19:00:00”); minute: cat tine. -> cheia sau None."""
	m = _START_SERVER.match(str(start_server or ""))
	if _idNumeric(flux) is None or m is None:
		return None
	an, luna, zi, ora, minut = (int(x) for x in m.groups())
	if not (1 <= luna <= 12 and 1 <= zi <= 31 and 0 <= ora <= 23 and 0 <= minut <= 59):
		return None
	try:
		minute = max(1, min(int(minute), MAX_MINUTE_ARHIVA))
	except (TypeError, ValueError):
		return None
	return "a%s-%04d%02d%02d%02d%02d-%d" % (flux, an, luna, zi, ora, minut, minute)


def desparteArhiva(cheie):
	"""cheia a... -> (id, (an, luna, zi, ora, minut) ca text, minute) sau None."""
	m = _CHEIE_ARHIVA.match(cheie or "")
	if m is None:
		return None
	minute = int(m.group(7))
	if not 1 <= minute <= MAX_MINUTE_ARHIVA:
		return None
	return m.group(1), m.group(2, 3, 4, 5, 6), minute


def eArhiva(cheie):
	return desparteArhiva(cheie) is not None


def _text64(v):
	"""Titlurile si descrierile din get_simple_data_table vin in base64; unele servere le dau direct."""
	v = str(v or "").strip()
	if not v:
		return ""
	try:
		t = base64.b64decode(v, validate=True).decode("utf-8")
		if t and "\x00" not in t:
			v = t
	except (ValueError, TypeError, UnicodeDecodeError):
		pass
	v = "".join(c if ord(c) >= 32 and ord(c) != 127 else " " for c in v)
	return " ".join(v.split())[:600]


def _ts(v):
	try:
		v = int(str(v or "").strip())
		return v if v > 0 else None
	except (TypeError, ValueError):
		return None


def programeDinTabel(date, flux, acum=None):
	"""Raspunsul get_simple_data_table -> emisiunile din arhiva, cea mai noua intai: [{"inceput", "sfarsit" (secunde UTC), "titlu",
	"descriere", "cheie", "acum" (emisiunea de acum, de la inceput)}]. Numai cele cu has_archive=1, inceput in trecut."""
	acum = time.time() if acum is None else acum
	lista = date.get("epg_listings") if isinstance(date, dict) else None
	rez = []
	for p in lista if isinstance(lista, list) else ():
		if not isinstance(p, dict) or str(p.get("has_archive") or "0").strip() != "1":
			continue
		inceput, sfarsit = _ts(p.get("start_timestamp")), _ts(p.get("stop_timestamp"))
		if inceput is None or sfarsit is None or sfarsit <= inceput or inceput >= acum:
			continue
		cheie = cheieArhiva(flux, p.get("start"), (sfarsit - inceput + 59) // 60)
		if cheie is None:
			continue
		rez.append({"inceput": inceput, "sfarsit": sfarsit, "titlu": _text64(p.get("title")), "descriere": _text64(p.get("description")),
			"cheie": cheie, "acum": sfarsit > acum})
	rez.sort(key=lambda p: -p["inceput"])
	return rez[:MAX_PROGRAME_ARHIVA]


def arhivaActiva():
	try:
		from Components.config import config
		return bool(config.usage.hds_iptv_arhiva.value)
	except (AttributeError, KeyError, ImportError):
		return True


def programeArhiva(s, cheie_canal):
	"""Emisiunile din arhiva ale unui canal Xtream (cheia l<id>). Cere serverul: numai pe un fir, numai cand omul a deschis lista.
	-> lista de mai sus. Arunca EroareIptv (serverul nu raspunde, contul)."""
	if not isinstance(s, dict) or s.get("fel") != "xtream" or not cheie_canal or cheie_canal[0] != "l":
		return []
	flux = _idNumeric(cheie_canal[1:])
	if flux is None:
		return []
	date = dateXtream(dict(s, baza=s.get("baza") or _baze(s.get("server") or "")[0]), "get_simple_data_table", {"stream_id": flux})
	return programeDinTabel(date, flux)


# ------------------------------------------------------------------ Stalker

# Portalul raspunde numai unui client care se prezinta ca decodor: atat cere protocolul lui obisnuit, cu adresa MAC data de furnizor.
_AGENT_PORTAL = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
_CAI_API = ("/portal.php", "/server/load.php", "/stalker_portal/server/load.php")


def _antetePortal(s, baza, jeton=None):
	mac = I.macCurat(s.get("mac")) or ""
	antete = {
		"User-Agent": s.get("user_agent") or _AGENT_PORTAL,
		"X-User-Agent": s.get("x_user_agent") or "Model: %s; Link: WiFi" % (s.get("stb_type") or "MAG250"),
		"Referer": s.get("referer") or baza + "/",
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


def _cerePortal(s, api, baza, parametri, jeton=None, maxim=MAX_LISTA, termen=TERMEN_S, activa=None):
	stare = _starePortal(s)
	with stare["lacat"]:
		_verificaPornirePortal(activa)
		_verificaPauzaPortal(stare)
		date = dict(parametri, JsHttpRequest="1-xml")
		try:
			octeti = descarca("%s?%s" % (api, urlencode(date)), antete=_antetePortal(s, baza, jeton), maxim=maxim, termen=termen)
		except EroareIptv as e:
			if e.dupa:
				stare["pauza"] = (time.monotonic(), min(300, e.dupa), e.mesaj, e.cod)
			raise
	r = _json(octeti, E_NU_E_PORTAL)
	if not isinstance(r, dict) or "js" not in r:
		raise EroareIptv(E_NU_E_PORTAL)
	return r["js"]


def stalkerConecteaza(s, termen=TERMEN_S):
	"""Strangerea de mana: gaseste calea API a portalului si cere jetonul, apoi profilul. -> (baza, api, jeton)."""
	stare = _starePortal(s)
	with stare["lacat"]:
		if stare.pop("reia", False):
			stare["pauza"] = None
		_verificaPauzaPortal(stare)
		stare["sesiune"] = None
		stare["stream"] = True
		sesiune = _conecteazaPortal(s, termen)
		stare["sesiune"] = sesiune
		return sesiune


def _conecteazaPortal(s, termen, activa=None):
	if not I.macBun(s.get("mac") or ""):
		raise EroareIptv(E_MAC)
	eroare = None
	for baza in _bazePortal(s.get("portal") or ""):
		for cale in _CAI_API:
			api = baza + cale
			try:
				js = _cerePortal(s, api, baza, {"type": "stb", "action": "handshake", "token": ""}, termen=termen, activa=activa)
				jeton = js.get("token") if isinstance(js, dict) else None
				if not jeton:
					raise EroareIptv(E_MAC)
				parametri = {"type": "stb", "action": "get_profile", "hd": "1"}
				if s.get("stb_type"):
					parametri["stb_type"] = s["stb_type"]
				profil = _cerePortal(s, api, baza, parametri, jeton, termen=termen, activa=activa)
				# Reparatia lui kreidlerboy, LinuxSat #971520: 0 si 1 pot insemna amandoua un cont activ.
				if _profilPortalRefuzat(profil):
					raise EroareIptv(E_MAC)
				return baza, api, jeton
			except EroareIptv as e:
				_verificaPornirePortal(activa)
				if e.mesaj == E_MAC or e.cod in (401, 403, 429) or e.dupa:
					raise
				eroare = e
	raise eroare or EroareIptv(E_NU_E_PORTAL)


def _profilPortalRefuzat(profil):
	"""Numarul din status singur nu deosebeste un cont refuzat pe toate portalurile."""
	if not isinstance(profil, dict):
		if profil is None or profil is False:
			return True
		raise EroareIptv(E_NU_E_PORTAL)
	if str(profil.get("error") or "").strip().lower() not in ("", "0", "false"):
		return True
	for cheie in ("blocked", "is_blocked"):
		if str(profil.get(cheie, "")).strip().lower() in ("1", "true", "yes"):
			return True
	if "auth" in profil and str(profil["auth"]).strip().lower() in ("0", "false"):
		return True
	return str(profil.get("status", "")).strip().lower() in ("blocked", "disabled", "expired", "rejected", "error")


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
		logo = c.get("logo")
		meta = {}
		if isinstance(logo, str) and logo and len(logo) <= I.MAX_ADRESA:
			logo = urljoin(baza.rstrip("/") + "/", logo)
			if I.fluxBun(logo) and logo.lower().startswith(("http://", "https://")):
				meta["logo"] = logo
		canale.append(["c" + cid, nume, grupa, comanda] + ([meta] if meta else []))
	if not canale and not filtru.grupe:
		raise EroareIptv(E_FARA_CANALE)
	return canale, {"taiate": filtru.taiate, "sarite": sarite, "catalog": filtru.catalog(), "baza": baza, "fara_https": not I.fluxCriptat(baza)}


def _adresaDinComanda(text):
	"""Raspunsul create_link: 'ffmpeg http://...' sau numai adresa. -> adresa buna sau None."""
	if not isinstance(text, str):
		return None
	text = (text or "").strip()
	if " " in text:
		text = text.rsplit(" ", 1)[-1]
	return I.fluxBun(text)


_SESIUNI = {}
_LACAT_SESIUNI = threading.Lock()


def _starePortal(s):
	"""Memorie numai in RAM, pe sursa; schimbarea datelor uita jetonul si forma cererii."""
	date = tuple(s.get(k) or "" for k in ("portal", "mac", "user_agent", "referer", "x_user_agent", "stb_type"))
	cheie = s.get("id") or date
	with _LACAT_SESIUNI:
		stare = _SESIUNI.get(cheie)
		if stare is None or stare["date"] != date:
			stare = {"date": date, "sesiune": None, "stream": True, "pauza": None, "lacat": threading.RLock()}
			_SESIUNI[cheie] = stare
		return stare


def _verificaPauzaPortal(stare):
	pauza = stare["pauza"]
	if pauza:
		ramas = pauza[1] - int(math.floor(time.monotonic() - pauza[0]))
		if ramas > 0:
			raise EroareIptv(pauza[2], cod=pauza[3], dupa=ramas)
		stare["pauza"] = None


def reiaPortal(s):
	"""Formularul TV/web cere explicit o noua incercare, fara pauza veche."""
	if s.get("fel") == "stalker":
		stare = _starePortal(s)
		stare["pauza"] = None
		# Si cererea deja in mers poate aduce o pauza pana ajunge formularul in coada.
		stare["reia"] = True


def _verificaPornirePortal(activa):
	if activa is not None and not activa():
		raise EroareIptv(E_NU_RASPUNDE)


def _streamDinComanda(comanda):
	"""Ia valoarea stream din comanda, decodata o data, inainte de urlencode al cererii API."""
	# Reparatia lui kreidlerboy, LinuxSat #971520.
	m = re.search(r"[?&]stream=([^&#\s]+)", comanda or "")
	return parse_qsl("stream=" + m.group(1))[0][1] if m else ""


def _legaturaPortal(s, api, baza, jeton, comanda, stare, buget, activa=None):
	parametri = {"type": "itv", "action": "create_link", "cmd": comanda, "series": "",
		"forced_storage": "0", "disable_ad": "0", "download": "0"}
	stream = _streamDinComanda(comanda)
	forme = (stare["stream"], not stare["stream"]) if stream else (False,)
	for separat in forme:
		if buget[0] <= 0:
			break
		buget[0] -= 1
		try:
			js = _cerePortal(s, api, baza, dict(parametri, stream=stream) if separat else parametri,
				jeton, maxim=256 * 1024, termen=TERMEN_ADRESA_S, activa=activa)
			_verificaPornirePortal(activa)
			if _adresaDinComanda(js.get("cmd") if isinstance(js, dict) else None):
				if stream:
					stare["stream"] = separat
				return js
		except EroareIptv as e:
			_verificaPornirePortal(activa)
			# Rezerva numai pentru forma incompatibila; niciun refuz de acces sau Retry-After nu se repeta aici.
			if e.dupa or e.cod == 429 or (e.cod not in (400, 405, 422) and e.mesaj != E_NU_E_PORTAL):
				raise
			if buget[0] <= 0:
				raise
	raise EroareIptv(E_NU_E_PORTAL)


def stalkerAdresa(s, comanda, activa=None):
	"""Adresa unui canal la pornire (create_link): se schimba de fiecare data, deci nu se tine nicaieri. Jetonul se tine in memorie
	si se cere din nou o data, cand portalul nu-l mai primeste. Termen scurt: omul asteapta in fata televizorului."""
	stare = _starePortal(s)
	if not stare["lacat"].acquire(timeout=10):
		raise EroareIptv(E_NU_RASPUNDE)
	try:
		_verificaPornirePortal(activa)
		_verificaPauzaPortal(stare)
		# Cel mult doua create_link cu jetonul vechi si unul singur dupa reinnoire.
		buget = [2]
		for incercare in (1, 2):
			if stare["sesiune"] is None:
				stare["sesiune"] = _conecteazaPortal(s, TERMEN_ADRESA_S, activa=activa)
			baza, api, jeton = stare["sesiune"]
			try:
				js = _legaturaPortal(s, api, baza, jeton, comanda, stare, buget, activa=activa)
				return _adresaDinComanda(js["cmd"])
			except EroareIptv as e:
				_verificaPornirePortal(activa)
				jeton_refuzat = e.cod in (401, 403) or (not e.cod and e.mesaj == E_NU_E_PORTAL)
				if jeton_refuzat:
					stare["sesiune"] = None
				if e.dupa or not jeton_refuzat or incercare == 2:
					raise
				buget = [1]
		raise EroareIptv(E_NU_RASPUNDE)
	finally:
		stare["lacat"].release()


# ------------------------------------------------------------------ ce a scris omul

def verificaDate(fel, date, sursa_id=None):
	s, eroare = _verificaDate(fel, date)
	if eroare:
		return s, eroare
	# Editarea MAC-ului pastreaza referintele canalelor si setarile sursei.
	if fel == "stalker" and sursa_id:
		veche = I.sursa(sursa_id)
		if veche and veche.get("fel") == fel and I.identitatePortal(veche.get("portal")) == I.identitatePortal(s["portal"]):
			s["id"] = sursa_id
	if fel == "m3u":
		for v in I.citesteSurse():
			if v.get("fel") == "m3u" and I.identitatePlaylist(v.get("adresa")) == I.identitatePlaylist(s.get("adresa")):
				s["id"] = v["id"]
				break
	veche = I.sursa(s["id"]) or {}
	optiuni, eroare = verificaOptiuni(date, veche)
	if eroare:
		return None, eroare
	s.update(optiuni)
	for cheie in ("user_agent", "referer", "x_user_agent", "stb_type"):
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
		mac = I.macCurat(date.get("mac"))
		if I.desparteServer(portal) is None:
			return None, E_ADRESA
		if mac is None:
			return None, E_FORMA_MAC
		return I.sursaNouaStalker(portal, mac, nume), None
	return None, E_ADRESA


# ------------------------------------------------------------------ o sursa, oricare ar fi

# lista demo: un pachet din feedul imaginii, nu sta in imagine; se ia si se actualizeaza de acolo, fara shell
CALE_DEMO = "/usr/share/enigma2/hds-lista-demo/lista.json"
PACHET_DEMO = "enigma2-plugin-extensions-hds-lista-demo"
TERMEN_OPKG_S = 180


# Grupele listei demo sunt tarile (si „Uniunea Europeană”), scrise in romana in pachet; aici sunt marcate pentru po, ca imaginea sa le
# arate in limba receptorului (tarile au deja traducerea din HdsOperatoriSatelit.NUME_TARI). O grupa noua in lista = un rand aici.
GRUPE_DEMO = (N_("Uniunea Europeană"),)
TARI_DEMO = (N_("Spania"), N_("Danemarca"), N_("Islanda"), N_("Suedia"), N_("Finlanda"), N_("Letonia"), N_("Cehia"), N_("Croația"),
	N_("Bulgaria"), N_("Luxemburg"), N_("Franța"), N_("Italia"), N_("Germania"), N_("Austria"), N_("Belgia"), N_("Țările de Jos"),
	N_("Polonia"), N_("Ungaria"), N_("Grecia"), N_("Portugalia"), N_("Irlanda"), N_("România"))


def _tradus(text):
	try:
		return _(text)  # noqa: F821 (gettext-ul pus de enigma2 in builtins)
	except NameError:
		return text


def instaleazaDemo():
	"""opkg update si install: pune pachetul sau il aduce la zi. O eroare lasa lista veche, daca e.
	-> None (instalat sau la zi), "lipsa" (opkg update a mers, dar pachetul nu e in feed) sau "internet" (celelalte)."""
	coduri = []
	for argumente in (["opkg", "update"], ["opkg", "install", PACHET_DEMO]):
		try:
			with open(os.devnull, "wb") as nimic:
				coduri.append(subprocess.call(argumente, stdout=nimic, stderr=nimic, timeout=TERMEN_OPKG_S))
		except (OSError, subprocess.SubprocessError) as e:
			_jurnal("lista demo: %s" % type(e).__name__)
			coduri.append(None)
	# 0.7.9 (BLD8): pachetele descarcate de opkg stau in /var/cache/opkg, in RAM; dupa instalare se sterg
	try:
		from Components import HdsCuratenie
		HdsCuratenie.golesteCacheOpkgDupa(["opkg", "install", PACHET_DEMO])
	except Exception:
		pass
	if coduri[-1] == 0:
		return None
	try:
		with open(os.devnull, "wb") as nimic:
			in_liste = bool(subprocess.check_output(["opkg", "list", PACHET_DEMO], stderr=nimic, timeout=60).strip())
	except (OSError, subprocess.SubprocessError, ValueError):
		in_liste = True
	motiv = "lipsa" if coduri[0] == 0 and not in_liste else "internet"
	_jurnal("lista demo: opkg update %s, install %s, %s" % (coduri[0], coduri[-1], motiv))
	return motiv


def _citesteFisierDemo(cale=None):
	try:
		with open(cale or CALE_DEMO, encoding="utf-8") as f:
			date = json.load(f)
		return date if isinstance(date, dict) and isinstance(date.get("grupe"), list) else None
	except (IOError, OSError, ValueError):
		return None


def citesteDemo(cale=None):
	"""Lista demo din pachetul din feed, gata de aratat si de pus in buchete: {"versiune", "grupe": [{"nume" (tradus), "canale": [{"nume",
	"adresa", "pagina", "citat", "atribuire", "antete"?}]}]}. In pachet: "grupe" (le citesc toate imaginile) si "grupe_cu_antete"
	(canale care cer antetele lor, de pilda User-Agent; numai 0.7.5+), unite aici dupa numele grupei. -> dict sau None."""
	date = _citesteFisierDemo(cale)
	if date is None:
		return None
	grupe = {}  # ordinea punerii (Python 3.7+)
	for cheie in ("grupe", "grupe_cu_antete"):
		for g in date.get(cheie) if isinstance(date.get(cheie), list) else ():
			if not isinstance(g, dict) or not isinstance(g.get("canale"), list):
				continue
			nume = I.numeCurat(g.get("nume"))
			grupe.setdefault(nume, []).extend(c for c in g["canale"] if isinstance(c, dict))
	# un nume gol nu se traduce: gettext ar intoarce antetul catalogului
	return {"versiune": str(date.get("versiune") or ""), "grupe": [{"nume": I.numeCurat(_tradus(n)) if n else "", "canale": c}
		for n, c in grupe.items()]}


def aduceDemo(s, cale=None):
	motiv = instaleazaDemo() if cale is None else None
	date = citesteDemo(cale)
	if date is None:
		raise EroareIptv(E_DEMO_LIPSA if motiv == "lipsa" else E_DEMO)
	canale = []
	vazute = {}
	for g in date["grupe"]:
		grupa = g["nume"]
		for c in g["canale"]:
			adresa = I.fluxBun(c.get("adresa"))
			nume = I.numeCurat(c.get("nume"))
			if adresa and nume:
				rand = [I.cheieDinNume(c.get("id") or "", nume, vazute), nume, grupa, adresa]
				antete = anteteCurate(c.get("antete"))
				if antete:
					rand.append({"antete": antete})
				canale.append(rand)
	if not canale:
		raise EroareIptv(E_FARA_CANALE)
	return canale, {"taiate": 0, "sarite": 0, "fara_https": False}


def aduce(s):
	"""Canalele sursei de la server sau din fisier. -> (canale, informatii de pus in sursa). Arunca EroareIptv."""
	fel = s.get("fel")
	if fel == "m3u":
		canale, info = aducePlaylist(s)
	elif fel == "xtream":
		canale, info = aduceXtream(s)
	elif fel == "stalker":
		canale, info = aduceStalker(s)
	elif fel == "demo":
		canale, info = aduceDemo(s)
	else:
		raise EroareIptv(E_ADRESA)
	# 0.7.7 (BQT): campurile textului taiatelor (textTaiate) se scriu la fiecare aducere, si cu 0, fiindca sursa se
	# actualizeaza peste cea veche (HdsIptvSurse.actualizeazaSursa): o taiere de ieri nu ramane in cartela
	info.setdefault("taiate_filme", 0)
	info.setdefault("filme", 0)
	info.setdefault("vii", len(canale) - info["filme"])
	return canale, info


# Optiunile apartin sursei; datele de acces nu trebuie rescrise pentru a le schimba.
E_OPTIUNI = N_("Alege un player din listă și Da sau Nu pentru piconuri.")


def verificaOptiuni(date, veche=None):
	veche = veche or {}
	player = str(date.get("player", I.playerSursa(veche)))
	piconuri = date.get("piconuri", veche.get("piconuri") is True)
	if player not in I.PLAYERE or str(piconuri).lower() not in ("true", "false", "1", "0"):
		return None, E_OPTIUNI
	return {"player": player, "piconuri": str(piconuri).lower() in ("true", "1")}, None


def salveazaOptiuni(sursa_id, date):
	s = I.sursa(sursa_id)
	if not s:
		return N_("Sursa aleasă nu mai e în listă. Pagina se încarcă din nou.")
	optiuni, eroare = verificaOptiuni(date, s)
	if eroare:
		return eroare
	s = I.actualizeazaSursa(sursa_id, **optiuni)
	from Components import HdsIptvLucru as L
	L.cere(L._REFACERE, din_nou=True)
	cerePiconuri(s)
	return None


# Un singur fir, independent de aducerea listelor si de firul televizorului.
# PNG standard, maximum 64 MiB pentru IPTV propriu. Siglele valide se pastreaza.
MAX_PICONURI_OCTETI = 64 * 1024 * 1024
MAX_PERECHI_PICONURI = 2048
MAX_PERECHI_OCTETI = 1024 * 1024
MAX_REGISTRU_PICONURI = 8192
_PICON_PROPRIU = re.compile(r"^(4097|5001|5002)_0_1_[0-9A-F]+_[0-9A-F]+_[0-9A-F]+_FFFE[0-9A-F]{4}_0_0_0[.]png$")
_picon_lacat = threading.Lock()
_picon_coada = {}
_picon_fir = None
_picon_stop = threading.Event()
_picon_iesire_legata = False


def _dosarPiconuri():
	for cale in ("/media/hdd/picon", "/media/usb/picon", "/usr/share/enigma2/picon"):
		if os.path.isdir(cale) and os.access(cale, os.W_OK):
			return cale
	return "/usr/share/enigma2/picon"


def _perechiPiconuri(s, canale):
	"""O singura sursa, referinta, logo si antete, cel mult 1 MiB de text.
	Lista completa este eliberata inaintea primei cereri de retea."""
	ascunse = frozenset(s.get("ascunse") or ())
	perechi, octeti = [], 0
	for c in canale:
		if _picon_stop.is_set():
			break
		if len(c) < 5 or not isinstance(c[4], dict) or I._eFilmSursei(c) or I._DESPARTIRE.match(c[1] or ""):
			continue
		if I.eAscunsa(ascunse, c[2] or I.numeSursa(s)):
			continue
		logo = c[4].get("logo")
		if not isinstance(logo, str) or len(logo) > I.MAX_ADRESA or not logo.lower().startswith(("http://", "https://")):
			continue
		ref = I.refCanal(s["id"], c[0], player=I.playerSursa(s))
		antete = anteteCurate(c[4].get("antete"))
		cost = (len(ref.encode("utf-8")) + len(logo.encode("utf-8")) +
			len(json.dumps(antete, ensure_ascii=False, sort_keys=True).encode("utf-8")))
		if len(perechi) >= MAX_PERECHI_PICONURI or octeti + cost > MAX_PERECHI_OCTETI:
			break
		perechi.append((ref, logo, antete))
		octeti += cost
	return perechi


def _canalePiconuri(sid):
	"""Citire din mers a listei JSON proprii: un rand, tampon de maximum 64 KiB.
	O lista incompleta sau un rand prea mare opreste numai aceasta incercare."""
	decodor = json.JSONDecoder()
	try:
		with open(I._caleCanale(sid), encoding="utf-8") as f:
			tampon = f.read(16384).lstrip()
			if not tampon.startswith("["):
				return
			tampon = tampon[1:]
			for n in range(I.MAX_CANALE):
				while True:
					tampon = tampon.lstrip()
					if tampon.startswith("]") or _picon_stop.is_set():
						return
					try:
						canal, capat = decodor.raw_decode(tampon)
						break
					except ValueError:
						if len(tampon) >= 49152:
							return
						bucata = f.read(16384)
						if not bucata:
							return
						tampon += bucata
				if isinstance(canal, list) and len(canal) >= 4:
					yield canal
				tampon = tampon[capat:].lstrip()
				while not tampon:
					tampon = f.read(16384).lstrip()
					if not tampon:
						return
				if not tampon.startswith(","):
					return
				tampon = tampon[1:]
	except (OSError, UnicodeError):
		return


def _piconValid(cale):
	from PIL import Image
	try:
		if os.path.islink(cale):
			return False
		with Image.open(cale) as im:
			if im.format != "PNG":
				return False
			im.verify()
		return True
	except Image.DecompressionBombError:
		# Nu interpretam o imagine enorma drept permisiune de a o sterge.
		return True
	except (OSError, ValueError, SyntaxError):
		return False


def _caleRegistruPiconuri(dosar):
	# Cate un registru pentru fiecare destinatie, numai in dosarul privat IPTV.
	semn = hashlib.sha256(os.path.abspath(dosar).encode("utf-8")).hexdigest()[:16]
	return os.path.join(I.DOSAR, "piconuri-%s.json" % semn)


def _registruPiconuri(dosar):
	try:
		with open(_caleRegistruPiconuri(dosar), "rb") as f:
			date = f.read(4 * 1024 * 1024 + 1)
		if len(date) > 4 * 1024 * 1024:
			return {}
		date = json.loads(date)
		if not isinstance(date, dict) or len(date) > MAX_REGISTRU_PICONURI:
			return {}
		return {n: v for n, v in date.items() if _PICON_PROPRIU.fullmatch(n) and
			isinstance(v, list) and len(v) == 4 and all(type(x) is int for x in v[:3]) and
			isinstance(v[3], str) and re.fullmatch(r"[0-9a-f]{64}", v[3])}
	except (OSError, ValueError, TypeError):
		return {}


def _poateScriePicon(cale, nota):
	if not os.path.lexists(cale):
		return True
	return bool(nota and _identitatePicon(cale) == nota and not _piconValid(cale))


def _identitatePicon(cale):
	"""Dovada completa, inclusiv marime si suma; nu adoptam un fisier modificat."""
	import stat
	try:
		st = os.lstat(cale)
		if not stat.S_ISREG(st.st_mode) or not st.st_ino or st.st_size > 256 * 1024:
			return None
		with open(cale, "rb") as f:
			citit = os.fstat(f.fileno())
			date = f.read(256 * 1024 + 1)
		if (st.st_dev, st.st_ino, st.st_size) != (citit.st_dev, citit.st_ino, len(date)):
			return None
		return [st.st_dev, st.st_ino, len(date), hashlib.sha256(date).hexdigest()]
	except OSError:
		return None


def _permitePicon(s):
	# Sub lacatul comun se consulta EXCLUSIV memoria, nici callback-uri cu disc.
	with I._LACAT:
		return not _picon_stop.is_set() and I._stare_piconuri.get(s["id"]) == (
			True, I.playerSursa(s), tuple(s.get("ascunse") or ()))


def _curataTemporarePiconuri(dosar):
	import stat
	try:
		with os.scandir(dosar) as intrari:
			for intrare in intrari:
				if intrare.name.startswith(".hds-picon-"):
					try:
						st = intrare.stat(follow_symlinks=False)
						if stat.S_ISREG(st.st_mode) and st.st_mtime < time.time() - 600:
							os.unlink(intrare.path)
					except OSError:
						pass
	except OSError:
		pass


def _octetiTemporarePiconuri(dosar):
	# Inclusiv temporarele proaspete ramase de la o iesire brusca.
	total = 0
	with os.scandir(dosar) as intrari:
		for i in intrari:
			try:
				if i.name.startswith(".hds-picon-") and i.is_file(follow_symlinks=False):
					total += i.stat(follow_symlinks=False).st_size
			except FileNotFoundError:
				pass  # un alt proces tocmai a strans un temporar
	return total


def _publicaPicon(nou, cale):
	"""Exclusiv: o destinatie aparuta intre verificari ramane neatinsa.
	Dovada vine din descriptorul nostru, niciodata din destinatia redeschisa."""
	with open(nou, "rb") as f:
		date = f.read(256 * 1024 + 1)
		st = os.fstat(f.fileno())
	if len(date) > 256 * 1024:
		return None
	suma = hashlib.sha256(date).hexdigest()
	try:
		os.link(nou, cale)
		return [st.st_dev, st.st_ino, len(date), suma]
	except FileExistsError:
		return None
	except OSError:
		# FAT si sisteme fara hardlink: O_EXCL arbitreaza cursa, fara rename.
		try:
			fd = os.open(cale, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
		except FileExistsError:
			return None
		with os.fdopen(fd, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
			st = os.fstat(f.fileno())
		return [st.st_dev, st.st_ino, len(date), suma]


def descarcaPiconuri(s, canale, dosar=None, continua=None, perechi=None):
	"""Numai pe fir de lucru. Sursa da logo-ul, numele vine din referinta buchetului.
	PNG/JPEG mici verificate, convertite la PNG; nicio adresa in nume sau jurnal.
	Optiunea oprita nu creeaza dosare si nu foloseste reteaua."""
	rez = {"scrise": 0}
	if not s or s.get("piconuri") is not True:
		return rez
	from Components import HdsIptvSigle as S
	from PIL import Image
	import io
	import shutil
	import tempfile
	dosar = dosar or _dosarPiconuri()
	os.makedirs(dosar, exist_ok=True)
	registru = {n: v for n, v in _registruPiconuri(dosar).items()
		if os.path.lexists(os.path.join(dosar, n))}
	# Numai fisierele proprii, neschimbate: o colectie a omului nu consuma plafonul.
	total = _octetiTemporarePiconuri(dosar)
	for n, nota in registru.items():
		cale = os.path.join(dosar, n)
		if _identitatePicon(cale) == nota:
			total += nota[2]
	if perechi is None:
		perechi = _perechiPiconuri(s, canale)
	for ref, adresa, antete in perechi:
		if _picon_stop.is_set() or (continua and not continua()) or not _permitePicon(s):
			break
		if total >= MAX_PICONURI_OCTETI:
			break
		nume = S.nume(ref)
		if not nume:
			continue
		cale = os.path.join(dosar, nume + ".png")
		if not _poateScriePicon(cale, registru.get(nume + ".png")):
			continue
		nou = None
		try:
			if shutil.disk_usage(dosar).free < 16 * 1024 * 1024:
				break
			date = S.descarcaSigla(s, adresa, antete)
			S.verifica(date)
			with Image.open(io.BytesIO(date)) as im:
				im.load()
				im = im.convert("RGBA")
				im.thumbnail((220, 132))
				out = io.BytesIO()
				im.save(out, "PNG")
			date = out.getvalue()
			if total + len(date) > MAX_PICONURI_OCTETI:
				break
			with tempfile.NamedTemporaryFile(dir=dosar, prefix=".hds-picon-", delete=False) as f:
				nou = f.name
				f.write(date)
				f.flush()
				os.fsync(f.fileno())
				st_propriu = os.fstat(f.fileno())
			os.chmod(nou, 0o644)
			nota = registru.get(nume + ".png")
			if not _poateScriePicon(cale, nota):
				continue
			if nume + ".png" not in registru and len(registru) >= MAX_REGISTRU_PICONURI:
				break
			if (continua and not continua()) or not _permitePicon(s):
				break
			# Dupa acest control poate ramane cel mult un picon suplimentar.
			if nota and not _piconValid(cale) and _identitatePicon(cale) == nota:
				# Numai refacerea unui fisier propriu cu toate dovezile neschimbate.
				# Verificarea completa este IMEDIAT inainte de replace, fara unlink.
				os.replace(nou, cale)
				dovada = [st_propriu.st_dev, st_propriu.st_ino, len(date), hashlib.sha256(date).hexdigest()]
			else:
				dovada = _publicaPicon(nou, cale)
			if dovada:
				registru[nume + ".png"] = dovada
				I._asiguraDosar()
				I._scrie(_caleRegistruPiconuri(dosar), json.dumps(registru, sort_keys=True).encode("utf-8"), 0o600)
				total += len(date)
				rez["scrise"] += 1
		except Exception:
			# O sigla lipsa sau gresita nu impiedica urmatorul canal.
			pass
		finally:
			if nou and os.path.exists(nou):
				os.unlink(nou)
	if rez["scrise"]:
		try:
			from Tools.PiconResolver import resetPiconPath
			resetPiconPath()
		except ImportError:
			pass
	return rez


def _piconBucla():
	global _picon_fir
	try:
		os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
	except (AttributeError, OSError):
		pass
	# O singura curatare pe rularea firului, fara niciun lacat comun tinut.
	I.incarcaStarePiconuri()
	_curataTemporarePiconuri(_dosarPiconuri())
	while True:
		with _picon_lacat:
			if _picon_stop.is_set() or not _picon_coada:
				if _picon_stop.is_set():
					_picon_coada.clear()
				_picon_fir = None
				return
			sid = next(iter(_picon_coada))
			_picon_coada.pop(sid)
		try:
			# Setarile cele mai noi, inclusiv oprirea facuta cat astepta in coada.
			s = I.sursa(sid)
			if s and s.get("piconuri") is True:
				perechi = _perechiPiconuri(s, _canalePiconuri(sid))
				descarcaPiconuri(s, None, perechi=perechi)
				del perechi
		except Exception as e:
			_jurnal("piconuri: %s" % type(e).__name__)


def cerePiconuri(s, canale=None):
	"""Coada are numai identificatori. Lista de pe disc este deja salvata de apelant.
	Parametrul vechi canale este acceptat, dar nu se retine in memorie."""
	global _picon_fir
	if not s or s.get("piconuri") is not True:
		return
	with _picon_lacat:
		if s["id"] not in _picon_coada and len(_picon_coada) >= I.MAX_SURSE:
			_picon_coada.pop(next(iter(_picon_coada)))
		if _picon_stop.is_set():
			return
		_picon_coada[s["id"]] = None
		if _picon_fir is None:
			_picon_fir = threading.Thread(target=_piconBucla, name="HdsIptvPiconuri", daemon=True)
			_picon_fir.start()


def oprestePiconuri():
	# Numai semnal: nici lacat, nici disc, nici join pe calea de iesire.
	# Firul daemon verifica semnalul sub I._LACAT inaintea publicarii.
	_picon_stop.set()


def pornestePiconuri():
	"""Legat o data pe firul principal, si cand nu exista inca surse."""
	global _picon_iesire_legata
	if _picon_iesire_legata:
		return
	import atexit
	atexit.register(oprestePiconuri)
	try:
		from twisted.internet import reactor
		reactor.addSystemEventTrigger("before", "shutdown", oprestePiconuri)
	except ImportError:
		pass
	_picon_iesire_legata = True

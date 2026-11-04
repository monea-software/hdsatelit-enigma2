# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvAdrese: adresa locala a canalelor de internet. Un canal din buchet are calea http://127.0.0.1:8897/tv/<sursa>/<cheie>
# (Components/HdsIptvSurse.py). Releul trimite fluxul cu antetele sursei. Parola nu intra in referinta.
# Listele HLS trimit si segmentele prin releu; portalul poate da alta adresa la fiecare pornire.
#
# Releul urmeaza el redirectionarile furnizorului, oricate sunt (urllib, HdsIptvClient._Redirectionari), iar playerul nu primeste
# niciodata un 302: GStreamer cadea cu eroarea "Found" la al doilea salt.
#
# CONEXIUNEA: un abonament are de obicei o singura conexiune. Un canal nou al aceleiasi surse inchide pe loc legatura veche (limita o da
# contul, s["conexiuni"]), iar daca serverul inca o mai socoteste, se incearca din nou de cateva ori. Altfel comutarea rapida intre canale
# se termina cu "prea multe conexiuni".
#
# TAMPONUL: la un flux viu (fara lungime) un fir citeste de la server intr-un tampon, iar firul cererii il da playerului. Inainte de primul
# octet se strange putin (PREUMPLERE_*), ca pornirea sa nu ramana in sacadari. Cand serverul inchide sau tace, firul se reconecteaza singur,
# iar playerul nu vede decat o pauza. Filmele (cu lungime si Range) si segmentele HLS merg direct, fara tampon.
#
# MASURATORILE: stareFlux() da viteza, timpul de raspuns al serverului si cat e in tampon, pentru bara si lista de canale.
#
# NUMAI pe 127.0.0.1, pe un fir al lui, fiecare cerere pe firul ei, ca un portal incet sa nu tina enigma2 (termen in
# HdsIptvClient.TERMEN_ADRESA_S). Nu scrie adresa in jurnal, nici la eroare. O cerere cu alta gazda (Host) decat 127.0.0.1 se
# refuza: o pagina deschisa in navigatorul de pe receptor nu poate ajunge la adresa printr-un nume care duce aici. Porneste
# numai cand exista surse (mytest.py si HdsIptvLucru): fara surse nu costa nimic.
#
# Fisierul nu importa nimic din enigma2: probele de pe PC il folosesc ca atare.

import collections
import hashlib
import os
import re
import socket
import threading
import time
from collections import OrderedDict
from urllib.parse import urljoin

try:
	from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except ImportError:  # Python 2: fara acest modul nu porneste nimic, fluxurile raman fara adresa locala
	BaseHTTPRequestHandler = object
	ThreadingHTTPServer = None

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C

_CALE = re.compile(r"^/tv/([0-9a-f]{8})/([A-Za-z0-9_.\-]{1,64})$")
_GAZDE = ("127.0.0.1:%d" % I.PORT, "localhost:%d" % I.PORT)

ASCULTARE_S = 5       # cat asteapta bucla intre doua cereri: o cerere o trezeste pe loc, deci nu intarzie nimic
TAMPON_MAX = 16 * 1024 * 1024       # octeti tinuti cel mult pentru un flux viu: cititorul asteapta peste atat
PREUMPLERE_OCTETI = 1500 * 1024     # inainte de primul octet catre player: atat, sau
PREUMPLERE_S = 1.5                  # atat timp, ce vine intai (la inceput serverele trimit de obicei mai repede decat se reda)
TERMEN_CITIRE_S = 10                # server care tace: legatura se reface
REINCERCARI_CONEXIUNE = 4           # serverul mai socoteste conexiunea veche: mai incercam, la PAUZA_CONEXIUNE_S
PAUZA_CONEXIUNE_S = 0.8
RECONECTARI_MAX = 6                 # consecutive, fara date intre ele
SANATOS_S = 30                      # dupa atatea secunde cu date, numaratoarea reconectarilor o ia de la capat
FEREASTRA_VITEZA_S = 2.0
TERMEN_SCRIERE_S = 120              # player care nu mai citeste deloc

_lacat = threading.Lock()
_canale = {}          # sursa -> (semnul fisierului, {cheie: a patra coloana})
_surse = (None, [])   # (semnul fisierului, sursele)
_server = None
_fir = None
_hls = OrderedDict()
_HLS = re.compile(r'^/hls/([0-9a-f]{8})/([A-Za-z0-9_.\-]{1,64})/([0-9a-f]{24})$')


def _semn(cale):
	try:
		st = os.stat(cale)
		return (st.st_mtime, st.st_size, st.st_ino)
	except OSError:
		return None


def _sursele():
	global _surse
	semn = _semn(os.path.join(I.DOSAR, "surse.json"))
	with _lacat:
		if _surse[0] == semn and semn is not None:
			return _surse[1]
	surse = I.citesteSurse() if semn is not None else []
	with _lacat:
		_surse = (semn, surse)
	return surse


def _coloane(sursa_id):
	"""{cheie: adresa sau comanda} ale sursei, tinute minte dupa fisier: o lista mare se citeste o singura data."""
	semn = _semn(os.path.join(I.DOSAR, "canale-%s.json" % sursa_id))
	with _lacat:
		v = _canale.get(sursa_id)
		if v is not None and v[0] == semn:
			return v[1]
	harta = dict((c[0], c) for c in I.citesteCanale(sursa_id) if isinstance(c, list) and len(c) >= 4)
	with _lacat:
		_canale.clear()  # o singura sursa mare in memorie
		_canale[sursa_id] = (semn, harta)
	return harta


def numeCanal(cale, nume):
	"""Numele adevarat, cand `nume` e chiar cheia canalului (a pornit fara nume). Numai din ce e deja citit: firul enigma2 nu citeste aici lista."""
	sid, cheie = I.desparteCale(cale)
	if sid is None or nume != cheie:
		return nume
	with _lacat:
		v = _canale.get(sid)
	c = v[1].get(cheie) if v else None
	return c[1] if c and len(c) > 1 and c[1] else nume


def adresa(sursa_id, cheie):
	"""Adresa adevarata a canalului, sau None. Rezultatul nu se scrie nicaieri."""
	s = I.sursa(sursa_id, _sursele())
	if s is None or not I.cheieBuna(cheie):
		return None
	fel = s.get("fel")
	if fel == "xtream":
		return C.xtreamAdresa(s, cheie)
	c = _coloane(sursa_id).get(cheie)
	if not c:
		return None
	valoare = c[3]
	if fel == "stalker":
		# un portal care nu da adresa nu inseamna un canal scos din lista
		rez = C.stalkerAdresa(s, valoare)
		if not rez:
			raise C.EroareIptv(C.E_NU_RASPUNDE)
		return rez
	return I.fluxBun(valoare)


def antete(sursa_id, cheie):
	s = I.sursa(sursa_id, _sursele()) or {}
	a = C.anteteSursa(s)
	if s.get("fel") == "stalker":
		a.update(C._antetePortal(s, s.get("baza") or ""))
	c = _coloane(sursa_id).get(cheie)
	if c and len(c) > 4 and isinstance(c[4], dict):
		a.update(C.anteteCurate(c[4].get("antete")))
	return a


class _Masura(object):
	"""Ce se stie despre fluxul de acum. Scrie firul fluxului; citeste firul enigma2 (valori simple, fara lacat)."""

	def __init__(self, sid, cheie):
		self.sid, self.cheie = sid, cheie
		self.inceput = time.monotonic()
		self.raspuns_ms = None
		self.octeti = 0
		self.viteza = 0
		self._ferestra = (self.inceput, 0)
		self.ultim = self.inceput
		self.reconectari = 0
		self.tampon = None
		self.preumplere = 0
		self.trimis = False
		self.hls = False
		self.eroare_sursa = False
		self.piste_hls = []
		self.pts0 = None

	def adauga(self, n):
		self.octeti += n
		acum = time.monotonic()
		self.ultim = acum
		t0, o0 = self._ferestra
		if acum - t0 >= FEREASTRA_VITEZA_S:
			self.viteza = int((self.octeti - o0) * 8 / (acum - t0))
			self._ferestra = (acum, self.octeti)


_masura = None
PAUZA_HLS_S = 30
ASTEPTARE_MAX_S = 8


def stareFlux(sid=None, cheie=None):
	"""Fluxul de acum: {"viteza": biti/s, "raspuns_ms", "tampon_s", "preumplere": procent, "reconectari", "trimis"}, sau None. Cu sid si cheie,
	numai daca e chiar acel canal."""
	m = _masura
	if m is None or (sid is not None and (m.sid != sid or m.cheie != cheie)):
		return None
	acum = time.monotonic()
	# HLS vine in rafale, cate un segment la cateva secunde: viteza ramane intre ele
	viteza = m.viteza if acum - m.ultim < (PAUZA_HLS_S if m.hls else 2 * FEREASTRA_VITEZA_S) else 0
	# tampon numai pe fluxul viu: un film sau HLS merg direct, fara tampon in releu
	tampon = m.tampon
	tampon_s = round(tampon.octeti * 8.0 / viteza, 1) if tampon is not None and viteza > 0 and m.trimis else None
	return {"viteza": viteza, "raspuns_ms": m.raspuns_ms, "tampon_s": tampon_s, "hls": m.hls, "eroare_sursa": m.eroare_sursa,
		"preumplere": m.preumplere, "reconectari": m.reconectari, "trimis": m.trimis, "octeti": m.octeti}


def primulPts(b):
	"""PTS-ul primului pachet PES dintr-un segment TS, sau None."""
	for i in range(0, min(len(b), 188 * 400) - 188 + 1, 188):
		if b[i] != 0x47:
			return None
		if not b[i + 1] & 0x40:
			continue
		adaptare = (b[i + 3] >> 4) & 3
		if adaptare == 2:
			continue
		p = i + 4 + (1 + b[i + 4] if adaptare == 3 else 0)
		if p + 14 > i + 188 or b[p:p + 3] != b"\x00\x00\x01" or b[p + 3] & 0xE0 not in (0xE0, 0xC0) or not b[p + 7] & 0x80:
			continue
		h = b[p + 9:p + 14]
		return ((h[0] & 0x0E) << 29) | (h[1] << 22) | ((h[2] & 0xFE) << 14) | (h[3] << 7) | (h[4] >> 1)
	return None


def pisteHls(sid, cheie):
	"""(pistele de subtitrare din lista principala a canalului de acum, PTS-ul primului segment)"""
	m = _masura
	if m is None or m.sid != sid or m.cheie != cheie:
		return [], None
	return m.piste_hls, m.pts0


def stareCale(cale):
	"""Fluxul de acum, daca e canalul cu aceasta cale; pentru convertoare. {} pentru un canal de-al nostru care n-a pornit inca; None pentru
	orice alt serviciu."""
	sid, cheie = I.desparteCale(cale)
	if sid is None:
		return None
	return stareFlux(sid, cheie) or {}


class _Legatura(object):
	"""Un flux deschis spre server. inchide() il opreste de pe alt fir: soclul se inchide, deci si o citire blocata se termina."""

	def __init__(self):
		self.inchisa = False
		self.raspuns = None
		self._lacat = threading.Lock()

	def pune(self, raspuns):
		with self._lacat:
			self.raspuns = raspuns
			if self.inchisa:
				_inchideRaspuns(raspuns)

	def inchide(self):
		with self._lacat:
			self.inchisa = True
			r = self.raspuns
		if r is not None:
			_inchideRaspuns(r)


def _inchideRaspuns(r):
	try:
		s = r.fp.raw._sock
		s.shutdown(socket.SHUT_RDWR)
	except (AttributeError, OSError):
		pass
	try:
		r.close()
	except Exception:
		pass


_legaturi = {}        # sursa -> [_Legatura]; cea mai noua la sfarsit


def _ocupa(s, sid):
	"""O legatura noua pentru sursa: cele vechi peste limita contului se inchid acum. -> (legatura, s-a inchis vreuna)."""
	try:
		limita = max(1, int(s.get("conexiuni") or 1))
	except (TypeError, ValueError):
		limita = 1
	noua = _Legatura()
	with _lacat:
		lista = _legaturi.setdefault(sid, [])
		de_inchis = lista[:max(0, len(lista) - limita + 1)]
		del lista[:len(de_inchis)]
		lista.append(noua)
	for v in de_inchis:
		v.inchide()
	return noua, bool(de_inchis)


def _elibereaza(sid, legatura):
	with _lacat:
		lista = _legaturi.get(sid)
		if lista and legatura in lista:
			lista.remove(legatura)


class _Tampon(object):
	"""Coada de bucati dintre firul care citeste de la server si firul care scrie spre player, cu margine in octeti."""

	def __init__(self, maxim=None):
		self.maxim = maxim or TAMPON_MAX
		self.bucati = collections.deque()
		self.octeti = 0
		self.sfarsit = False
		self.semnal = threading.Condition()

	def pune(self, b):
		"""-> False cand s-a inchis (nimeni nu mai citeste)."""
		with self.semnal:
			while self.octeti >= self.maxim and not self.sfarsit:
				self.semnal.wait(1)
			if self.sfarsit:
				return False
			self.bucati.append(b)
			self.octeti += len(b)
			self.semnal.notify_all()
			return True

	def ia(self, termen=None):
		"""O bucata, sau None la sfarsit sau cand trece termenul."""
		with self.semnal:
			limita = None if termen is None else time.monotonic() + termen
			while not self.bucati and not self.sfarsit:
				ramas = None if limita is None else limita - time.monotonic()
				if ramas is not None and ramas <= 0:
					return None
				self.semnal.wait(ramas if ramas is not None else 1)
			if not self.bucati:
				return None
			b = self.bucati.popleft()
			self.octeti -= len(b)
			self.semnal.notify_all()
			return b

	def inchide(self):
		with self.semnal:
			self.sfarsit = True
			self.semnal.notify_all()

	def asteapta(self, octeti, secunde, oprit):
		"""Pana sunt `octeti` in tampon, trec `secunde`, sau fluxul s-a terminat."""
		limita = time.monotonic() + secunde
		with self.semnal:
			while self.octeti < octeti and not self.sfarsit and not oprit():
				ramas = limita - time.monotonic()
				if ramas <= 0:
					return
				self.semnal.wait(min(ramas, 0.2))


def _deschideCuAsteptare(tinta_fn, a, legatura, metoda=None, a_inchis=False):
	"""Legatura spre server. Daca serverul spune ca are prea multe conexiuni (de obicei a noastra, abia inchisa) mai incearca de cateva ori.
	-> raspunsul. Arunca EroareIptv."""
	incercari = REINCERCARI_CONEXIUNE
	retea = 1
	while True:
		try:
			tinta = tinta_fn()
			if not tinta:
				raise C.EroareIptv(C.E_CANAL_LIPSA)
			return C.deschide(tinta, a, TERMEN_CITIRE_S, metoda)
		except C.EroareIptv as e:
			# un 403 dupa ce tocmai am inchis o legatura e tot conexiunea veche; altfel e un refuz adevarat si nu mai asteptam. Un server cazut
			# o clipa se mai incearca, iar reteaua numai o data; Retry-After se respecta, dar un zap nu asteapta oricat.
			repeta = e.cod in C.COD_CONEXIUNI or e.cod in C.COD_TEMPORAR or (a_inchis and e.cod == 403)
			if not repeta and not e.cod and e.mesaj == C.E_NU_RASPUNDE and retea > 0:
				retea -= 1
				repeta = True
			if not repeta or incercari <= 0 or legatura.inchisa or e.dupa > ASTEPTARE_MAX_S:
				raise
			incercari -= 1
			time.sleep(max(PAUZA_CONEXIUNE_S, e.dupa))


def _citesteViu(raspuns, tampon, legatura, tinta_fn, a, m, plecat):
	"""Firul cititor al unui flux viu: bucati in tampon; la sfarsit sau la tacere, legatura se reface. Se termina cand s-a inchis legatura,
	playerul a plecat sau nu se mai poate reface."""
	esecuri = 0
	ultima_buna = time.monotonic()
	try:
		while not legatura.inchisa and not plecat():
			try:
				b = raspuns.read1(65536)
			except (OSError, ValueError, AttributeError):
				b = b""
			if b:
				m.adauga(len(b))
				if not tampon.pune(b):
					return
				if esecuri and time.monotonic() - ultima_buna > SANATOS_S:
					esecuri = 0
				if not esecuri:
					ultima_buna = time.monotonic()
				continue
			# serverul a inchis sau tace: refacem legatura; playerul vede numai o pauza
			_inchideRaspuns(raspuns)
			while True:
				if legatura.inchisa or plecat():
					return
				esecuri += 1
				if esecuri > RECONECTARI_MAX:
					print("[HdsIptvAdrese] %s/%s: legatura nu s-a putut reface" % (m.sid, m.cheie))
					return
				time.sleep(min(0.5 * (2 ** (esecuri - 1)), 4.0))
				try:
					raspuns = _deschideCuAsteptare(tinta_fn, a, legatura)
				except C.EroareIptv:
					continue
				legatura.pune(raspuns)
				m.reconectari += 1
				ultima_buna = time.monotonic()
				break
	finally:
		_inchideRaspuns(raspuns)
		tampon.inchide()


def _locHls(sid, cheie, url):
	if not I.fluxBun(url) or not url.lower().startswith(("http://", "https://")):
		raise C.EroareIptv(C.E_ADRESA)
	jeton = hashlib.sha256((sid + "/" + cheie + "|" + url).encode("utf-8")).hexdigest()[:24]
	with _lacat:
		_hls[jeton] = (sid, cheie, url, time.monotonic())
		_hls.move_to_end(jeton)
		while len(_hls) > 8192:
			_hls.popitem(last=False)
	return "/hls/%s/%s/%s" % (sid, cheie, jeton)


def _listaHls(text, baza, sid, cheie):
	rez = []
	for rand in text.splitlines():
		if rand.startswith("#"):
			rand = re.sub(r'URI="([^"\r\n]+)"', lambda m: 'URI="%s"' % _locHls(sid, cheie, urljoin(baza, m.group(1))), rand)
		elif rand.strip():
			rand = _locHls(sid, cheie, urljoin(baza, rand.strip()))
		rez.append(rand)
	return ("\n".join(rez) + "\n").encode("utf-8")


class _Cerere(BaseHTTPRequestHandler):
	protocol_version = "HTTP/1.1"
	timeout = 15
	server_version = "HDSatelit"
	sys_version = ""

	def log_message(self, format, *args):  # noqa: A002 (numele cerut de BaseHTTPRequestHandler)
		pass  # calea are sursa si cheia, nu parola; adresa adevarata nu trece prin jurnal

	def _raspunde(self, cod, locatie=None):
		self.send_response(cod)
		if locatie:
			self.send_header("Location", locatie)
		self.send_header("Content-Length", "0")
		self.send_header("Cache-Control", "no-store")
		self.send_header("Connection", "close")
		self.end_headers()
		self.close_connection = True

	def _cere(self):
		global _masura
		if self.headers.get("Host", "") not in _GAZDE:
			self._raspunde(403)
			return
		cale = self.path.split("?", 1)[0]
		m = _CALE.match(cale)
		h = _HLS.match(cale)
		if h:
			with _lacat:
				v = _hls.get(h.group(3))
			if not v or v[:2] != h.group(1, 2) or time.monotonic() - v[3] > 24 * 3600:
				self._raspunde(404)
				return
			return self._direct(v[2], v[0], v[1])
		if m is None:
			self._raspunde(404)
			return
		self._canal(m.group(1), m.group(2))

	def _anunta(self, sid, e):
		s = I.sursa(sid, _sursele()) or {}
		mesaj, al_sursei = C.mesajEroareRedare(s, e) if isinstance(e, C.EroareIptv) else (C.mesajRedare(s, C.E_NU_RASPUNDE), True)
		m = _masura
		if al_sursei and m is not None and m.sid == sid:
			m.eroare_sursa = True
		from Components import HdsIptvLucru as L
		L.eroareRedare(sid, mesaj, al_sursei)

	def _canal(self, sid, cheie):
		"""Cererea unui canal: legatura noua, cea veche a sursei se inchide, apoi flux viu prin tampon sau direct (film, lista HLS)."""
		global _masura
		s = I.sursa(sid, _sursele())
		if s is None or not I.cheieBuna(cheie):
			self._raspunde(404)
			return
		cap = self.command == "HEAD"
		if cap:
			legatura, a_inchis = _Legatura(), False
		else:
			legatura, a_inchis = _ocupa(s, sid)
			m = _Masura(sid, cheie)
			_masura = m
		raspuns = None
		try:
			a = antete(sid, cheie)
			if self.headers.get("Range"):
				a["Range"] = self.headers["Range"][:128]

			def tinta_fn():
				return adresa(sid, cheie)
			inceput = time.monotonic()
			raspuns = _deschideCuAsteptare(tinta_fn, a, legatura, "HEAD" if cap else None, a_inchis)
			legatura.pune(raspuns)
			if not cap:
				m.raspuns_ms = int((time.monotonic() - inceput) * 1000)
			self._trimite(raspuns, sid, cheie, a, tinta_fn, legatura, None if cap else m)
		except (ConnectionError, socket.timeout):
			pass
		except C.EroareIptv as e:
			self._anunta(sid, e)
			self._raspunde(503)
		except Exception as e:
			# numai felul erorii: textul ei ar putea cuprinde adresa
			print("[HdsIptvAdrese] %s/%s: %s" % (sid, cheie, type(e).__name__))
			self._anunta(sid, e)
			if not self._trimis:
				self._raspunde(503)
		finally:
			if not cap:
				legatura.inchide()
				_elibereaza(sid, legatura)
			self.close_connection = True

	def _trimite(self, f, sid, cheie, a, tinta_fn, legatura, m):
		"""Raspunsul serverului spre player: lista HLS rescrisa, film cu lungime direct, flux viu prin tampon."""
		tip = f.headers.get("Content-Type", "application/octet-stream")
		lista = "mpegurl" in tip.lower() or f.geturl().split("?", 1)[0].lower().endswith(".m3u8")
		if lista and self.command != "HEAD":
			corp = self._listaDin(f, sid, cheie)
			self._antete(f.status, tip, {"Content-Length": str(len(corp))})
			self.wfile.write(corp)
			if m is not None:
				m.hls = True
				m.preumplere = 100
				m.trimis = True
				from Components.HdsIptvSubtitrari import pisteDinLista
				m.piste_hls = pisteDinLista(corp.decode("utf-8", "replace"))
			return
		viu = m is not None and not f.headers.get("Content-Length") and f.status == 200
		self._antete(f.status, tip, dict((k, f.headers[k]) for k in ("Content-Length", "Content-Range", "Accept-Ranges") if f.headers.get(k)))
		if self.command == "HEAD":
			return
		self.connection.settimeout(TERMEN_SCRIERE_S)
		if not viu:
			if m is not None:
				m.preumplere = 100
				m.trimis = True
			self._copiaza(f, m)
			return
		tampon = _Tampon()
		m.tampon = tampon
		plecat = threading.Event()
		fir = threading.Thread(target=_citesteViu, args=(f, tampon, legatura, tinta_fn, a, m, plecat.is_set), name="HdsIptvCitire")
		fir.daemon = True
		fir.start()
		try:
			inceput = time.monotonic()

			def oprit():
				m.preumplere = min(100, max(int(tampon.octeti * 100 / PREUMPLERE_OCTETI), int((time.monotonic() - inceput) * 100 / PREUMPLERE_S)))
				return legatura.inchisa
			tampon.asteapta(PREUMPLERE_OCTETI, PREUMPLERE_S, oprit)
			m.preumplere = 100
			m.trimis = True
			while not legatura.inchisa:
				b = tampon.ia(1.0)
				if b is None:
					if tampon.sfarsit and not tampon.octeti:
						break
					continue
				self.wfile.write(b)
		finally:
			plecat.set()
			tampon.inchide()
			legatura.inchide()

	_trimis = False

	def _antete(self, cod, tip, altele):
		self.send_response(cod)
		self.send_header("Content-Type", tip)
		self.send_header("Cache-Control", "no-store")
		self.send_header("Connection", "close")
		for k, v in altele.items():
			self.send_header(k, v)
		self.end_headers()
		self._trimis = True

	def _listaDin(self, f, sid, cheie):
		from Components.HdsIptvCitire import Limitat
		citire = Limitat(f, 2 * 1024 * 1024, C.TERMEN_ADRESA_S)
		bucati = []
		while True:
			b = citire.read(65536)
			if not b:
				break
			bucati.append(b)
		return _listaHls(b"".join(bucati).decode("utf-8-sig"), f.geturl(), sid, cheie)

	def _copiaza(self, f, m):
		masura = m
		while True:
			b = f.read1(65536)
			if not b:
				break
			if masura is not None:
				masura.adauga(len(b))
				if masura.hls and masura.pts0 is None:
					masura.pts0 = primulPts(b)
			self.wfile.write(b)

	def _direct(self, tinta, sid, cheie):
		"""O cerere dintr-o lista HLS (lista secundara, segment, cheie): direct, fara tampon; socotita la fluxul canalului."""
		try:
			a = antete(sid, cheie)
			if self.headers.get("Range"):
				a["Range"] = self.headers["Range"][:128]
			with C.deschide(tinta, a, TERMEN_CITIRE_S, "HEAD" if self.command == "HEAD" else None) as f:
				tip = f.headers.get("Content-Type", "application/octet-stream")
				lista = "mpegurl" in tip.lower() or f.geturl().split("?", 1)[0].lower().endswith(".m3u8")
				if lista and self.command != "HEAD":
					corp = self._listaDin(f, sid, cheie)
					self._antete(f.status, tip, {"Content-Length": str(len(corp))})
					self.wfile.write(corp)
					return
				self._antete(f.status, tip, dict((k, f.headers[k]) for k in ("Content-Length", "Content-Range", "Accept-Ranges") if f.headers.get(k)))
				if self.command == "HEAD":
					return
				self.connection.settimeout(TERMEN_SCRIERE_S)
				m = _masura
				self._copiaza(f, m if m is not None and m.sid == sid and m.cheie == cheie else None)
		except (ConnectionError, socket.timeout):
			pass
		except C.EroareIptv as e:
			# un segment care lipseste la un flux viu e ceva obisnuit: playerul trece peste el, omul nu primeste o fereastra
			if not self._trimis:
				self._raspunde(e.cod if e.cod in (403, 404, 410) else 503)
		except Exception as e:
			print("[HdsIptvAdrese] %s/%s: %s" % (sid, cheie, type(e).__name__))
			if not self._trimis:
				self._raspunde(503)
		finally:
			self.close_connection = True

	def do_GET(self):
		self._cere()

	def do_HEAD(self):
		self._cere()


class _Server(ThreadingHTTPServer or object):
	daemon_threads = True
	allow_reuse_address = True


def porneste():
	"""Serverul local, o singura data. -> True daca asculta. Un port ocupat lasa canalele fara adresa, nu opreste nimic."""
	global _server, _fir
	if _server is not None:
		return True
	if ThreadingHTTPServer is None:
		return False
	try:
		_server = _Server(("127.0.0.1", I.PORT), _Cerere)
	except (OSError, ValueError) as e:
		print("[HdsIptvAdrese] portul %d: %s" % (I.PORT, e))
		_server = None
		return False
	_fir = threading.Thread(target=_server.serve_forever, kwargs={"poll_interval": ASCULTARE_S}, name="HdsIptvAdrese")
	_fir.daemon = True
	_fir.start()
	return True


def opreste():
	"""Numai pentru probe."""
	global _server, _fir
	if _server is not None:
		_server.shutdown()
		_server.server_close()
	_server = None
	_fir = None
	_canale.clear()
	_hls.clear()
	with _lacat:
		toate = [x for lista in _legaturi.values() for x in lista]
		_legaturi.clear()
	for x in toate:
		x.inchide()
	global _masura
	_masura = None

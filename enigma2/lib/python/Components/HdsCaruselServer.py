# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCaruselServer.py: aplicatia HbbTV care vine numai prin caruselul DSM-CC al canalului, data navigatorului printr-un
# server HTTP mic al receptorului. Navigatorul nu cunoaste schema dvb:, deci adresa aplicatiei
# dvb://<onid>.<tsid>.<sid>.<component_tag>/<cale> (ETSI TS 102 851, ETSI TS 102 796 cap. 9.2) devine
# http://127.0.0.1:<port>/<cale>: radacina serverului e radacina caruselului, deci adresele relative ale paginii si cele
# care incep cu "/" merg ca in carusel. Adresele dvb:// intregi ramase in pagina le rescrie scriptul HbbTV din pagina
# (Plugins/Extensions/HdsNavigator/hds-hbbtv.js), dupa "carusel" din configurarea data paginii (info()).
#
# SESIUNEA (SesiuneCarusel): cititorul caruselului (Components/HdsCaruselDemux.CititorCarusel, pe firul lui: PMT-ul,
# apoi pistele caruselului; arborele scris in DOSAR_CARUSEL/<onid>.<tsid>.<sid>.<tag> si tinut la zi cat ruleaza:
# module noi, fisiere noi) si serverul, peste acelasi dosar. opreste() le opreste pe amandoua si sterge dosarul; la
# pornirea enigma2 curata() sterge ce a ramas. Limitele de marime sunt cele din HdsCarusel.
#
# SERVERUL (ServerCarusel): numai pe 127.0.0.1, numai GET (orice alta metoda: 405); antetul Host trebuie sa fie
# 127.0.0.1:<port> sau localhost:<port> (o pagina de pe internet nu ajunge aici printr-un nume care arata spre
# 127.0.0.1). Calea ceruta se decodeaza, fiecare bucata trece prin HdsCarusel.nume_sigur (fara bucati goale, ".",
# "..", "/" sau "\" codate, caractere de control, nume prea lungi), calea reala (fara legaturi simbolice pe drum) trebuie
# sa ramana in dosar, iar fisierul se deschide cu O_NOFOLLOW si se trimite numai daca e un fisier obisnuit. Un dosar
# da numele din el despartite prin virgula (ETSI TS 102 796 V1.2.1, Tabelul 10). Tipul MIME: content_type_descriptor-ul
# fisierului din carusel (manifestul, dosar + ".json"), altfel dupa extensie (TIPURI); o pagina .html sau .htm fara
# descriptor e XHTML (application/vnd.hbbtv.xhtml+xml, ca aplicatiile de pe internet) numai cand se declara asa (antetul
# <?xml sau spatiul de nume XHTML), altfel text/html. Fiecare raspuns are Cache-Control: no-store (caruselul se schimba
# cat ruleaza aplicatia) si X-Content-Type-Options: nosniff. Un fisier care inca nu a venit se asteapta cel mult
# ASTEPTARE_FISIER_S, numai cat caruselul nu e complet. Cel mult MAX_CERERI cereri deodata, fiecare cu termen.
#
# PORTUL: PORT_BAZA + crc32(identitatea caruselului) % PORT_PLAJA, deci acelasi carusel are mereu aceeasi origine
# (datele aplicatiei din navigator raman de la o pornire la alta), iar doua carusele au origini diferite, ca adresele
# dvb:// la televizoare; ocupat: urmatoarele PORT_INCERCARI porturi, apoi unul dat de sistem.
#
# Partea de sus (identitate, port_pentru, imparte_cale, adresa_in_baza, din_dvb, adresa_aplicatie, cale_pe_disc,
# tip_fisier) si ServerCarusel nu importa enigma2; SesiuneCarusel primeste sursa si ceasul in probe.

from __future__ import absolute_import

import json
import os
import re
import shutil
import socket
import socketserver
import stat
import sys
import threading
import time
import zlib

from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import quote, unquote, urlsplit

try:
	from Components import HdsCarusel as C
	from Components import HdsCaruselDemux as D
except ImportError:  # pe PC: dosarul modulelor e in sys.path
	import HdsCarusel as C
	import HdsCaruselDemux as D

GAZDA = "127.0.0.1"
DOSAR_CARUSEL = "/tmp/hds-carusel"
PORT_BAZA, PORT_PLAJA, PORT_INCERCARI = 18100, 800, 8
ASTEPTARE_FISIER_S = 8.0      # cererea unui fisier care inca nu a venit, cat caruselul nu e complet
PAS_ASTEPTARE_S = 0.2
TERMEN_CERERE_S = 15          # o legatura care nu trimite nimic in atat se inchide
MAX_CERERI = 16
MAX_CALE = 2048
BUCATA = 64 * 1024
OPRIRE_FIR_S = 2.0

TIP_XHTML = "application/vnd.hbbtv.xhtml+xml"
TIPURI = {
	".html": "text/html", ".htm": "text/html", ".xhtml": TIP_XHTML, ".cehtml": TIP_XHTML,
	".js": "application/javascript", ".css": "text/css", ".json": "application/json", ".xml": "application/xml",
	".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
	".bmp": "image/bmp", ".ico": "image/x-icon", ".webp": "image/webp", ".txt": "text/plain",
	".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2",
	".mp3": "audio/mpeg", ".aac": "audio/aac", ".mp4": "video/mp4",
}
TIP_NECUNOSCUT = "application/octet-stream"
_TIP_BUN = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,40}/[a-z0-9][a-z0-9.+-]{0,80}$")
_HEX = re.compile(r"^[0-9a-fA-F]{1,8}$")
# ce ramane necodat dintr-o cale din AIT (caracterele permise intr-o cale URL si "%" deja pus)
_SIGURE = "/%:@!$&'()*+,;=-._~"


def _jurnal(text):
	print("[HdsCaruselServer] %s" % text)


# ---------------------------------------------------------------- adresele (curat)

def identitate(onid, tsid, sid, tag):
	"""Originea caruselului in forma din ETSI TS 102 796 V1.4.1 cap. 6.3.2 (hex, litere mici): "onid.tsid.sid.tag"."""
	return "%x.%x.%x.%x" % (onid, tsid, sid, tag)


def port_pentru(ident):
	"""Portul preferat al caruselului (vezi antetul): acelasi pentru aceeasi identitate."""
	return PORT_BAZA + (zlib.crc32(ident.encode("ascii", "replace")) & 0xFFFFFFFF) % PORT_PLAJA


def imparte_cale(cale):
	"""Calea initiala din AIT (simple_application_location, de pilda "index.html?x=1#y", poate incepe cu "/") ->
	(calea fisierului fara "/" la inceput, restul "?...#..." cum e)."""
	cale = (cale or u"").strip()
	m = re.match(r"^([^?#]*)(.*)$", cale, re.S)
	return m.group(1).lstrip(u"/"), m.group(2)


def _cod(text, sigure):
	"""Caracterele de control si spatiile codate, restul cum e (o adresa deja codata ramane la fel)."""
	return quote(re.sub(r"[\x00-\x1f\x7f]", u"", text), safe=sigure)


def adresa_in_baza(baza, cale):
	"""Calea initiala din AIT pusa peste baza serverului (http://127.0.0.1:<port>/)."""
	fisier, rest = imparte_cale(cale)
	return baza + _cod(fisier, _SIGURE) + _cod(rest, _SIGURE + "?#")


def fisier_pornire(cale):
	"""Calea pe disc (in carusel, decodata) a fisierului de pornire din calea initiala din AIT."""
	return unquote(imparte_cale(cale)[0])


def din_dvb(url, carusel):
	"""O adresa dvb:// intreaga a caruselului servit (ETSI TS 102 851 Tabelul 1: dvb://<onid>.[<tsid>].<sid>.<tag>
	[$<carousel_id>]<cale>, numerele in hex, tsid poate lipsi) -> adresa locala (baza + cale), sau None pentru orice
	altceva: alt carusel, alt serviciu, dvb://current.ait/..., un canal fara component_tag. carusel = info() al
	sesiunii: {"baza", "onid", "tsid", "sid", "tag"}."""
	if not carusel or not isinstance(url, str):
		return None
	m = re.match(r"^\s*dvb://([^/?#]*)([/?#].*)?$", url, re.I | re.S)
	if not m:
		return None
	parti = m.group(1).split("$", 1)[0].split(".")
	if len(parti) != 4:
		return None
	for i, (p, cheie) in enumerate(zip(parti, ("onid", "tsid", "sid", "tag"))):
		if p == u"" and i == 1:
			continue
		if not _HEX.match(p) or int(p, 16) != carusel.get(cheie):
			return None
	rest = m.group(2) or u"/"
	return carusel["baza"] + (rest.lstrip(u"/") if rest.startswith(u"/") else rest)


def adresa_aplicatie(aplicatie, carusel):
	"""createApplication(dvb://current.ait/<org>.<app>) spre o aplicatie a aceluiasi carusel -> adresa locala (baza +
	calea ei initiala), sau None cand aplicatia nu vine prin caruselul servit (alt component_tag, alt serviciu)."""
	t = C.transport_carusel(aplicatie)
	if not carusel or t is None or t.get("la_distanta") or t.get("tag") != carusel.get("tag"):
		return None
	return adresa_in_baza(carusel["baza"], (aplicatie or {}).get("cale") or u"")


# ---------------------------------------------------------------- caile si tipurile (curat)

def cale_pe_disc(radacina, cale_url):
	"""Partea de cale a cererii (cu %xx) -> (calea reala in radacina, numele din carusel ca tuplu) sau None cand nu e
	voie: bucati goale (afara de "/" de la capat), ".", "..", "/" sau "\\" codate, caractere de control, nume prea lungi,
	o legatura simbolica pe drum, o cale care iese din radacina."""
	if not isinstance(cale_url, str) or not cale_url.startswith(u"/") or len(cale_url) > MAX_CALE:
		return None
	try:
		text = unquote(cale_url, errors="strict")
	except (UnicodeDecodeError, ValueError):
		return None
	parti = text[1:].split(u"/")
	if parti and parti[-1] == u"":
		parti.pop()
	nume = []
	for p in parti:
		n = C.nume_sigur(p.encode("utf-8"))
		if n is None or n != p:
			return None
		nume.append(n)
	baza = os.path.realpath(radacina)
	p = os.path.join(baza, *[C._pe_disc(x) for x in nume]) if nume else baza
	real = os.path.realpath(p)
	if os.path.normcase(real) != os.path.normcase(os.path.normpath(p)):
		return None
	if real != baza and not os.path.normcase(real).startswith(os.path.normcase(baza) + os.sep):
		return None
	return real, tuple(nume)


def _declarat_xhtml(inceput):
	cap = bytes(inceput or b"")[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
	return cap.startswith(b"<?xml") or b"http://www.w3.org/1999/xhtml" in cap


def tip_fisier(nume, descriptor=None, inceput=b""):
	"""Tipul MIME al unui fisier din carusel: content_type_descriptor-ul lui, cand are o forma buna; altfel dupa
	extensie (TIPURI, necunoscut: TIP_NECUNOSCUT); o pagina .html sau .htm fara descriptor e XHTML numai cand primii ei
	octeti (inceput) o declara asa."""
	d = (descriptor or u"").strip().lower() if isinstance(descriptor, str) else u""
	if d and _TIP_BUN.match(d):
		return d
	t = TIPURI.get(os.path.splitext(nume or u"")[1].lower(), TIP_NECUNOSCUT)
	if t == "text/html" and _declarat_xhtml(inceput):
		return TIP_XHTML
	return t


# ---------------------------------------------------------------- serverul

class _Server(ThreadingMixIn, HTTPServer):
	daemon_threads = True
	allow_reuse_address = os.name != "nt"     # pe Windows ar lasa doua servere pe acelasi port
	request_queue_size = 32                   # navigatorul deschide mai multe legaturi deodata (5 din clasa de baza)

	def __init__(self, adresa, cereri, carusel):
		self.carusel = carusel
		self._active = 0
		self._zavor_active = threading.Lock()
		HTTPServer.__init__(self, adresa, cereri)

	def server_bind(self):
		# fara getfqdn() din HTTPServer.server_bind (o cautare de nume la pornire)
		socketserver.TCPServer.server_bind(self)
		self.server_name, self.server_port = GAZDA, self.server_address[1]

	def handle_error(self, cerere, adresa):
		# o legatura rupta de navigator (pagina schimbata, aplicatia inchisa): un rand scurt, fara urma intreaga
		e = sys.exc_info()[1]
		if not isinstance(e, (BrokenPipeError, ConnectionResetError, socket.timeout)):
			_jurnal("cererea: %s" % e.__class__.__name__)

	def process_request(self, cerere, adresa):
		with self._zavor_active:
			if self._active >= MAX_CERERI:
				self.shutdown_request(cerere)
				return
			self._active += 1
		try:
			ThreadingMixIn.process_request(self, cerere, adresa)
		except Exception:
			with self._zavor_active:
				self._active -= 1
			self.shutdown_request(cerere)

	def process_request_thread(self, cerere, adresa):
		try:
			ThreadingMixIn.process_request_thread(self, cerere, adresa)
		finally:
			with self._zavor_active:
				self._active -= 1


class _Cereri(BaseHTTPRequestHandler):
	server_version = "HdsCarusel"
	sys_version = ""
	protocol_version = "HTTP/1.0"
	timeout = TERMEN_CERERE_S

	def log_message(self, *argumente):
		pass

	def _antete(self, cod, tip, lungime, antete=()):
		self.send_response(cod)
		self.send_header("Content-Type", tip)
		self.send_header("Content-Length", str(lungime))
		self.send_header("Cache-Control", "no-store")
		self.send_header("X-Content-Type-Options", "nosniff")
		for k, v in antete:
			self.send_header(k, v)
		self.end_headers()

	def _scurt(self, cod, corp=b"", antete=()):
		self._antete(cod, "text/plain; charset=utf-8", len(corp), antete)
		self.wfile.write(corp)

	def _refuza(self):
		self._scurt(405, b"", (("Allow", "GET"),))

	do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = _refuza

	def do_GET(self):
		srv = self.server.carusel
		if not srv.gazda_buna(self.headers.get("Host")):
			self._scurt(403)
			return
		try:
			cale = urlsplit(self.path).path
		except ValueError:
			cale = None
		gasit = srv.gaseste(cale)
		if gasit is None:
			self._scurt(404)
			return
		real, nume = gasit
		if os.path.isdir(real):
			try:
				corp = u",".join(sorted(os.listdir(real))).encode("utf-8")
			except OSError:
				self._scurt(404)
				return
			self._scurt(200, corp)
			return
		try:
			fd = os.open(real, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
		except OSError:
			self._scurt(404)
			return
		with os.fdopen(fd, "rb") as f:
			st = os.fstat(f.fileno())
			if not stat.S_ISREG(st.st_mode):
				self._scurt(404)
				return
			inceput = f.read(4096)
			self._antete(200, srv.tip(nume, inceput), st.st_size)
			self.wfile.write(inceput)
			while True:
				b = f.read(BUCATA)
				if not b:
					break
				self.wfile.write(b)


class ServerCarusel(object):
	"""Serverul local peste dosarul caruselului (vezi antetul). porturi: cele incercate intai (apoi unul dat de sistem);
	complet: functie fara argumente, True cand caruselul e intreg (atunci un fisier lipsa e 404 pe loc)."""

	def __init__(self, dosar, porturi=(), complet=None, asteptare_s=ASTEPTARE_FISIER_S):
		self.dosar = dosar
		self.porturi = [p for p in porturi if isinstance(p, int) and 0 < p < 65536]
		self.complet = complet
		self.asteptare_s = asteptare_s
		self.port = None
		self._srv = None
		self._fir = None
		self._oprit = threading.Event()
		self._zavor = threading.Lock()
		self._tipuri = (None, {})

	def porneste(self):
		"""Porneste ascultarea pe 127.0.0.1. -> portul."""
		if self._srv is not None:
			return self.port
		srv, eroare = None, None
		for port in self.porturi + [0]:
			try:
				srv = _Server((GAZDA, port), _Cereri, self)
				break
			except (OSError, socket.error) as e:
				eroare = e
		if srv is None:
			raise eroare or OSError("niciun port")
		self._srv = srv
		self.port = srv.server_address[1]
		self._oprit.clear()
		self._fir = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1}, name="HdsCaruselServer")
		self._fir.daemon = True
		self._fir.start()
		_jurnal("asculta pe %s:%d" % (GAZDA, self.port))
		return self.port

	def opreste(self):
		"""Opreste ascultarea; cererile care asteapta un fisier se termina cu 404."""
		self._oprit.set()
		srv, self._srv = self._srv, None
		if srv is None:
			return
		try:
			srv.shutdown()
		finally:
			srv.server_close()
		if self._fir is not None:
			self._fir.join(OPRIRE_FIR_S)
		_jurnal("oprit")

	def baza(self):
		return "http://%s:%d/" % (GAZDA, self.port) if self.port else None

	def gazda_buna(self, gazda):
		if not self.port or not isinstance(gazda, str):
			return False
		return gazda.strip().lower() in ("%s:%d" % (GAZDA, self.port), "localhost:%d" % self.port)

	def _complet(self):
		try:
			return bool(self.complet()) if self.complet is not None else False
		except Exception:
			return False

	def gaseste(self, cale):
		"""Calea ceruta -> (calea reala, numele) a unui fisier sau dosar care exista, sau None (refuzata ori lipsa). Un
		fisier lipsa se asteapta cel mult asteptare_s cat caruselul nu e complet."""
		capat = time.time() + self.asteptare_s
		while True:
			r = cale_pe_disc(self.dosar, cale)
			if r is None:
				return None
			if os.path.isfile(r[0]) or os.path.isdir(r[0]):
				return r
			if self._oprit.is_set() or self._complet() or time.time() >= capat:
				return None
			self._oprit.wait(PAS_ASTEPTARE_S)

	def _descriptori(self):
		"""{cale din carusel: content_type_descriptor} din manifest (citit din nou numai cand s-a schimbat)."""
		cale = self.dosar + ".json"
		try:
			cand = os.stat(cale).st_mtime
		except OSError:
			return {}
		with self._zavor:
			if self._tipuri[0] == cand:
				return self._tipuri[1]
		try:
			with open(cale, encoding="utf-8") as f:
				m = json.load(f)
			tipuri = {x.get("cale"): x.get("tip") for x in m.get("fisiere") or () if isinstance(x, dict) and x.get("tip")}
		except (OSError, ValueError, AttributeError):
			tipuri = {}
		with self._zavor:
			self._tipuri = (cand, tipuri)
		return tipuri

	def tip(self, nume, inceput=b""):
		return tip_fisier(nume[-1] if nume else u"", self._descriptori().get(u"/".join(nume)), inceput)


# ---------------------------------------------------------------- sesiunea

def _sterge(cale):
	try:
		if os.path.islink(cale) or os.path.isfile(cale):
			os.remove(cale)
		elif os.path.isdir(cale):
			shutil.rmtree(cale, ignore_errors=True)
	except OSError as e:
		_jurnal("stergerea %s: %s" % (cale, e))


def curata(radacina=DOSAR_CARUSEL):
	"""La pornirea enigma2: ce a ramas de la o sesiune de dinainte (o cadere a interfetei) se sterge."""
	if os.path.lexists(radacina):
		_sterge(radacina)


class SesiuneCarusel(object):
	"""Caruselul aplicatiei alese pe canalul redat: cititorul (pe firul lui) si serverul, peste acelasi dosar.

	demux, pid_pmt: ale canalului redat (HdsAnalizaFlux.parametri); onid, tsid, sid: din referinta lui; aplicatie: din
	AIT (forma HdsAnalizaFlux.citeste_ait), cu transportul prin carusel pe acest serviciu. sursa, ceas, porturi: in probe.
	ValueError cand aplicatia nu are carusel pe acest serviciu sau demux-ul ori PMT-ul nu se stiu."""

	def __init__(self, demux, pid_pmt, onid, tsid, sid, aplicatie, radacina=DOSAR_CARUSEL, sursa=None, ceas=None,
			porturi=None, asteptare_s=ASTEPTARE_FISIER_S):
		t = C.transport_carusel(aplicatie)
		if t is None or t.get("la_distanta") or not isinstance(t.get("tag"), int) or t["tag"] < 0:
			raise ValueError("aplicatia nu are carusel pe acest serviciu")
		if not isinstance(demux, int) or demux < 0 or not isinstance(pid_pmt, int) or not 0 < pid_pmt < 0x1FFF:
			raise ValueError("demux-ul sau PMT-ul canalului nu se stiu")
		self.onid, self.tsid, self.sid, self.tag = onid, tsid, sid, t["tag"]
		self.ident = identitate(onid, tsid, sid, self.tag)
		self.radacina = radacina
		self.dosar = os.path.join(radacina, self.ident)
		self.cale = (aplicatie or {}).get("cale") or u""
		self.fisier = fisier_pornire(self.cale)
		self.cititor = D.CititorCarusel(demux, None, self.dosar, sursa=sursa, ceas=ceas, pmt=(pid_pmt, sid, aplicatie))
		p = port_pentru(self.ident)
		self.server = ServerCarusel(self.dosar, range(p, p + PORT_INCERCARI) if porturi is None else porturi,
			complet=lambda: self.cititor.stare().get("complet"), asteptare_s=asteptare_s)
		self.pornita = False

	def _curata(self):
		for x in (self.dosar, self.dosar + ".json", self.dosar + ".json.nou", self.dosar + ".nou", self.dosar + ".vechi"):
			if os.path.lexists(x):
				_sterge(x)

	def porneste(self):
		"""Dosarul gol, serverul, apoi cititorul. O exceptie (portul, firul) lasa totul oprit."""
		try:
			if not os.path.isdir(self.radacina):
				os.makedirs(self.radacina, 0o700)
			self._curata()
			self.server.porneste()
			self.cititor.porneste()
			self.pornita = True
		except Exception:
			self.opreste()
			raise
		_jurnal("caruselul %s pornit (pornirea: %s)" % (self.ident, self.fisier or "-"))
		return True

	def baza(self):
		return self.server.baza()

	def adresa(self):
		"""Adresa de pornire pentru navigator (calea initiala din AIT peste serverul local)."""
		return adresa_in_baza(self.baza(), self.cale)

	def info(self):
		"""Ce primeste pagina in configurare ("carusel", pentru hds-hbbtv.js)."""
		return {"baza": self.baza(), "onid": self.onid, "tsid": self.tsid, "sid": self.sid, "tag": self.tag}

	def are_pornirea(self):
		if not self.fisier:
			return False
		parti = self.fisier.split(u"/")
		if any(C.nume_sigur(x.encode("utf-8")) != x for x in parti):
			return False
		return os.path.isfile(os.path.join(self.dosar, *[C._pe_disc(x) for x in parti]))

	def stare(self):
		"""Starea cititorului (HdsCaruselDemux.CititorCarusel.stare) plus "pornire" (fisierul de pornire e pe disc) si
		"port"."""
		st = self.cititor.stare()
		st["pornire"] = self.are_pornirea()
		st["port"] = self.server.port
		return st

	def opreste(self):
		"""Serverul si cititorul se opresc (filtrele se inchid pe firul lui), dosarul se sterge."""
		try:
			self.server.opreste()
		except Exception as e:
			_jurnal("oprirea serverului: %s" % e)
		self.cititor.opreste(asteapta_s=OPRIRE_FIR_S)
		self._curata()
		if self.pornita:
			_jurnal("caruselul %s oprit" % self.ident)
		self.pornita = False

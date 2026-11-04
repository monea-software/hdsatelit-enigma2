# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""EPG XMLTV propriu: retea, gzip, analiza si import pe un singur fir separat.

Nu pastreaza documentul XML sau programele unei surse in RAM. SAX tine doar canalul/programul curent;
textele, dictionarele, grupurile si cache-ul C++ au limite. Nu scrie fisiere si nu jurnalizeaza URL-uri.
Canalele pastreaza cele patru coloane istorice, urmate optional de {'tvg_id', 'logo', 'antete'}.
"""

import calendar
import datetime
import re
import threading
import time
import zlib
from collections import OrderedDict
from urllib.parse import urlencode
from xml.parsers import expat

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C
from Components.HdsIptvSurse import N_

MAX_COMPRIMAT = 64 * 1024 * 1024
MAX_XML = 128 * 1024 * 1024
MAX_EVENIMENTE = 20000             # pe sursa si incercare, inclusiv copiile pentru acelasi tvg-id
MAX_PE_CANAL = 128
MAX_CANALE_XML = 60000
MAX_TEXTE = 2048
MAX_ADANCIME = 32
ZILE = 7
TERMEN_TOTAL_S = 180
BUCATA = 65536
LOT = 16
MAX_LOTURI = 32                    # cel mult 512 evenimente in asteptarea importului C++
MAX_SNAPSHOTURI = 2               # numai chei/nume/tvg-id, fara adrese de flux, logo sau antete

E_NUCLEU = N_("Ghidul TV pentru canalele de internet cere actualizarea imaginii. Actualizează imaginea și încearcă din nou.")
E_ESUAT = N_("Ghidul TV nu s-a putut descărca. Verifică internetul și încearcă din nou.")
E_GATA = N_("Ghidul TV este actualizat.")
E_GOL = N_("Furnizorul nu a trimis programe pentru canalele din listă.")

_DATA = re.compile(r"^(\d{14})(?:\s*(Z|[+-]\d{4}))?$")
_lacat = threading.Lock()
_coada = OrderedDict()
_ultimele = OrderedDict()
_fir = None
_in_lucru = None
_de_notificat = False


class EroareEpg(Exception):
	def __init__(self, mesaj):
		Exception.__init__(self, mesaj)
		self.mesaj = mesaj


def adresaEpg(s):
	"""url-tvg al playlistului sau xmltv.php al contului. Numai http(s), fara fisiere locale."""
	adresa = s.get("epg_url") or ""
	if not adresa and s.get("fel") == "xtream":
		baza = s.get("baza") or C._baze(s.get("server") or "")[0]
		adresa = "%s/xmltv.php?%s" % (baza.rstrip("/"), urlencode({
			"username": s.get("utilizator") or "", "password": s.get("parola") or ""}))
	if isinstance(adresa, str) and adresa.lower().startswith(("http://", "https://")):
		return I.adresaListaBuna(adresa)
	return None


def _ora(text):
	m = _DATA.match((text or "").strip())
	if m is None:
		return None
	try:
		d = datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
		secunde = calendar.timegm(d.timetuple())
		zona = m.group(2)
		if zona and zona != "Z":
			ore, minute = int(zona[1:3]), int(zona[3:5])
			if ore > 23 or minute > 59:
				return None
			secunde -= (ore * 3600 + minute * 60) * (1 if zona[0] == "+" else -1)
		return secunde
	except (ValueError, OverflowError):
		return None


def _nume(text):
	return " ".join((text or "").casefold().split())[:256]


def _bucati(f, inceput):
	"""Gzip cu iesire limitata la o bucata chiar si pentru o arhiva foarte comprimata."""
	n = total = 0
	dec = None
	prima = True
	prefix = b""
	citeste = getattr(f, "read1", f.read)  # un singur recv: un server care picura octeti nu ascunde termenul total
	while True:
		if time.monotonic() - inceput > TERMEN_TOTAL_S:
			raise EroareEpg("termen")
		b = citeste(BUCATA)
		if not b:
			break
		n += len(b)
		if n > MAX_COMPRIMAT:
			raise EroareEpg("intrare")
		if prima:
			b = prefix + b
			if len(b) < 2:
				prefix = b
				continue
			# Nu facem presupuneri despre extensia URL-ului; primii doi octeti pot veni separat.
			prima = False
			if b.startswith(b"\x1f\x8b"):
				dec = zlib.decompressobj(31)
		if dec is None:
			total += len(b)
			if total > MAX_XML:
				raise EroareEpg("xml")
			yield b
		else:
			while b:
				if time.monotonic() - inceput > TERMEN_TOTAL_S:
					raise EroareEpg("termen")
				if dec.eof:
					dec = zlib.decompressobj(31)  # membri gzip concatenati
				x = dec.decompress(b, BUCATA)
				b = dec.unused_data if dec.eof else dec.unconsumed_tail
				total += len(x)
				if total > MAX_XML:
					raise EroareEpg("xml")
				if x:
					yield x
	if dec is not None and not dec.eof:
		raise EroareEpg("gzip")
	if prima and prefix:
		yield prefix


class _Xmltv:
	def __init__(self, s, canale, cache, acum):
		self.sid, self.cache, self.acum = s["id"], cache, acum
		self.iduri, self.nume, self.legate = {}, {}, {}
		self.numar, self.loturi = {}, OrderedDict()
		self.total = self.importate = self.canale_xml = 0
		self.octeti = 0
		self.stiva, self.canal, self.program, self.camp, self.text = [], None, None, None, ""
		for c in canale[:I.MAX_CANALE]:
			if not isinstance(c, (list, tuple)) or len(c) < 4 or not I.cheieBuna(c[0]):
				continue
			ref = I.refCanal(self.sid, c[0])
			meta = c[4] if len(c) > 4 and isinstance(c[4], dict) else {}
			tvg = meta.get("tvg_id")
			if isinstance(tvg, str) and tvg.strip():
				chei = self.iduri.setdefault(tvg.strip()[:256], [])
				if len(chei) < 8 and ref not in chei:
					chei.append(ref)
			nume = _nume(c[1])
			if nume:
				# Numele ambiguu nu alege arbitrar alt canal; identificatorul explicit are prioritate.
				self.nume[nume] = ref if nume not in self.nume else None
		self.parser = expat.ParserCreate()
		self.parser.StartElementHandler = self._incepe
		self.parser.EndElementHandler = self._termina
		self.parser.CharacterDataHandler = self._text
		self.parser.StartDoctypeDeclHandler = self._dtd
		self.parser.ExternalEntityRefHandler = self._dtd


	def citeste(self, b, gata=False):
		self.octeti += len(b)
		self.parser.Parse(b, gata)
		# Expat asteapta sfarsitul unui atribut/comentariu/token inaintea callback-ului. Nu lasam
		# un singur token ostil sa adune intregul document in tamponul sau intern.
		if self.octeti - self.parser.CurrentByteIndex > BUCATA:
			raise EroareEpg("jeton")


	def _dtd(self, *args):
		raise EroareEpg("DTD")


	def _incepe(self, tag, attr):
		self.stiva.append(tag)
		if len(self.stiva) > MAX_ADANCIME:
			raise EroareEpg("adancime")
		if len(self.stiva) == 1 and tag != "tv":
			raise EroareEpg("radacina")
		if len(attr) > 32 or any(len(k) > 128 or len(v) > 4096 for k, v in attr.items()):
			raise EroareEpg("atribute")
		if len(self.stiva) == 2:
			if tag == "channel":
				self.canale_xml += 1
				if self.canale_xml > MAX_CANALE_XML:
					raise EroareEpg("canale")
				self.canal = {"id": attr.get("id", "")[:256], "ref": None}
			elif tag == "programme":
				self.program = {"id": attr.get("channel", "")[:256], "start": attr.get("start", "")[:40],
					"stop": attr.get("stop", "")[:40]}
		if len(self.stiva) == 3 and ((self.canal is not None and tag == "display-name") or
				(self.program is not None and tag in ("title", "sub-title", "desc"))):
			self.camp, self.text = tag, ""


	def _text(self, text):
		if self.camp is not None and len(self.text) < MAX_TEXTE:
			self.text += text[:MAX_TEXTE - len(self.text)]


	def _termina(self, tag):
		if len(self.stiva) == 3 and self.camp == tag:
			if self.canal is not None:
				ref = self.nume.get(_nume(self.text))
				if ref and self.canal["ref"] is None:
					self.canal["ref"] = ref
			elif self.program is not None and tag not in self.program:
				self.program[tag] = self.text.strip()
			self.camp, self.text = None, ""
		if len(self.stiva) == 2:
			if tag == "channel" and self.canal is not None:
				cid = self.canal["id"]
				if cid and cid not in self.iduri and self.canal["ref"]:
					self.legate[cid] = [self.canal["ref"]]
				self.canal = None
			elif tag == "programme" and self.program is not None:
				self._eveniment(self.program)
				self.program = None
		self.stiva.pop()


	def _eveniment(self, p):
		if self.total >= MAX_EVENIMENTE:
			return
		cid = p["id"]
		refs = self.iduri.get(cid) or self.legate.get(cid)
		if not refs:
			ref = self.nume.get(_nume(cid))
			refs = [ref] if ref else ()
		start, stop = _ora(p["start"]), _ora(p["stop"])
		if not refs or start is None or stop is None or stop <= start or stop - start > 24 * 3600:
			return
		if stop <= self.acum or start > self.acum + ZILE * 86400 or not p.get("title"):
			return
		eid = zlib.crc32((cid + "/" + str(start)).encode("utf-8")) & 65535 or 1
		eveniment = (start, stop - start, p["title"][:240], p.get("sub-title", "")[:240], p.get("desc", "")[:1800], eid)
		for ref in refs:
			if self.total >= MAX_EVENIMENTE or self.numar.get(ref, 0) >= MAX_PE_CANAL:
				continue
			self.total += 1
			self.numar[ref] = self.numar.get(ref, 0) + 1
			if ref not in self.loturi and len(self.loturi) >= MAX_LOTURI:
				cheie, lot = self.loturi.popitem(last=False)
				self.importate += self.cache.importEvents(cheie, lot)
			lot = self.loturi.setdefault(ref, [])
			lot.append(eveniment)
			if len(lot) >= LOT:
				self.importate += self.cache.importEvents(ref, self.loturi.pop(ref))


	def gata(self):
		for ref, lot in self.loturi.items():
			self.importate += self.cache.importEvents(ref, lot)
		self.loturi.clear()
		return self.importate


def lucreaza(s, canale, cache=None):
	"""O sursa pe firul EPG. Rezultat: numarul evenimentelor importate; erorile raman fara URL."""
	adresa = adresaEpg(s)
	if adresa is None:
		return 0
	if cache is None:
		try:
			from enigma import eEPGCache
			cache = eEPGCache.getInstance()
		except ImportError:
			raise EroareEpg(E_NUCLEU)
	if cache is None or not hasattr(cache, "importEvents"):
		raise EroareEpg(E_NUCLEU)
	if canale is None:
		canale = I.citesteCanale(s["id"])
	if not canale:
		return 0
	inceput = time.monotonic()
	xml = _Xmltv(s, canale, cache, time.time())
	canale = None  # dupa mapare eliberam lista citita din JSON, inclusiv toate adresele de flux
	with C.deschide(adresa, C.anteteSursa(s)) as f:
		for b in _bucati(f, inceput):
			xml.citeste(b)
		xml.citeste(b"", True)
	return xml.gata()


def _stare(sid, stare, n=0, mesaj=""):
	try:
		I.actualizeazaSursa(sid, epg_stare=stare, epg_evenimente=n, epg_mesaj=mesaj, epg_ora=int(time.time()))
	except Exception as e:
		print("[HdsIptvEpg] salvarea starii: %s" % type(e).__name__)


def _bucla():
	global _fir, _in_lucru, _de_notificat
	while True:
		with _lacat:
			if not _coada:
				_fir, _in_lucru = None, None
				return
			_in_lucru, (s, canale) = _coada.popitem(last=False)
		_stare(_in_lucru, "lucreaza")
		try:
			n = lucreaza(s, canale)
			mesaj = ""
			_stare(_in_lucru, "gata", n, E_GATA if n else E_GOL)
		except Exception as e:
			n, mesaj = 0, E_NUCLEU if isinstance(e, EroareEpg) and e.mesaj == E_NUCLEU else E_ESUAT
			print("[HdsIptvEpg] sursa %s: %s" % (_in_lucru, type(e).__name__))
			_stare(_in_lucru, "eroare", n, mesaj)
		canale = None  # nu pastram lista sursei terminate cat timp incepe urmatoarea
		with _lacat:
			_ultimele[_in_lucru] = (n, mesaj)
			if n:
				_de_notificat = True
			_ultimele.move_to_end(_in_lucru)
			while len(_ultimele) > I.MAX_SURSE:
				_ultimele.popitem(last=False)


def cere(s, canale=None):
	"""Pune sursa in coada proprie si revine imediat. Reteaua/analiza/importul nu tin firul listelor sau UI."""
	global _fir
	if not isinstance(s, dict) or not I._ID_SURSA.match(s.get("id", "")):
		return False
	try:
		if adresaEpg(s) is None:
			return False
	except Exception:
		return False
	with _lacat:
		if s["id"] not in _coada and len(_coada) >= I.MAX_SURSE:
			return False
		# Apelul obisnuit da None: lista se citeste abia in worker, o singura sursa mare in RAM.
		# Compatibilitatea cu apelantii care dau lista tine cel mult doua copii compacte, fara URL-uri.
		meta = None
		if canale is not None and sum(1 for _s, cs in _coada.values() if cs is not None) < MAX_SNAPSHOTURI:
			meta = []
			for c in canale[:I.MAX_CANALE]:
				if not isinstance(c, (list, tuple)) or len(c) < 4:
					continue
				tvg = c[4].get("tvg_id", "") if len(c) > 4 and isinstance(c[4], dict) else ""
				meta.append((c[0], c[1], "", "", {"tvg_id": tvg[:256] if isinstance(tvg, str) else ""}))
		_coada[s["id"]] = (dict(s), meta)
		if _fir is None:
			_fir = threading.Thread(target=_bucla, name="HdsIptvEpg")
			_fir.daemon = True
			_fir.start()
	return True


def ultimul(sid):
	"""(evenimente importate, mesaj de tradus sau '') al ultimei incercari terminate."""
	with _lacat:
		return _ultimele.get(sid, (0, ""))


def notifica():
	"""Pe firul UI, din HdsIptvLucru._laTic: reface acum/urmeaza dupa un import nou."""
	global _de_notificat
	with _lacat:
		if not _de_notificat:
			return False
		_de_notificat = False
	try:
		from Screens.InfoBar import InfoBar
		bara = InfoBar.instance
		if bara is None:
			with _lacat:
				_de_notificat = True
			return False
		for cheie in ("Event_Now", "Event_Next"):
			sursa = bara.session.screen.get(cheie)
			if sursa is not None:
				sursa.changed((sursa.CHANGED_ALL,))
		lista = getattr(getattr(bara, "servicelist", None), "servicelist", None)
		instanta = getattr(lista, "instance", None)
		if instanta is not None:
			instanta.invalidate()
		return True
	except Exception as e:
		print("[HdsIptvEpg] afisarea ghidului: %s" % type(e).__name__)
		return False

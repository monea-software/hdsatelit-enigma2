# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""EPG XMLTV propriu: retea, gzip si analiza pe un singur fir separat.

Nu pastreaza documentul XML sau programele unei surse in RAM. SAX tine doar canalul/programul curent;
textele, dictionarele, grupurile si cache-ul C++ au limite. Nu scrie fisiere si nu jurnalizeaza URL-uri.
Canalele pastreaza cele patru coloane istorice, urmate optional de {'tvg_id', 'logo', 'antete'}.

Firul nu tine GIL-ul interfetei minute in sir. Pe un Viper 4K (0.7.6, Python 3.14) ghidul unui abonament mare (64 MB, 178.000
de emisiuni) tinea un nucleu 130 s dupa fiecare pornire a interfetei (125 s de procesor), iar ecranele si paginile web care cer
GIL-ul mergeau de cateva ori mai incet. Analiza citea 356.000 de ore cu datetime.strptime (care cere si locale-ul la fiecare
apel) si aduna textele tuturor emisiunilor, si ale celor fara canal in lista, din zilele trecute sau prea departe. Acum: orele
se citesc direct din cifre si se memoreaza (se repeta de la un canal la altul), iar emisiunile care nu pot intra (canal fara
pereche, canal plin, terminate, peste ZILE zile, ore rele) se sar de la <programme>, fara texte: de 2,5 ori mai putin lucru (50 s
de procesor la ceasul intreg pentru acelasi fisier). Dupa fiecare ~0,25 s de lucru firul doarme tot atat (_Ritm; pauzele nu intra
in TERMEN_TOTAL_S). Cu pauzele ceasul procesorului coboara: firul ia ~90 s de procesor in ~210 s (in loc de 125 s in ~130 s), iar
interfata raspunde mult mai repede cat merge (pagina principala web 455 ms in loc de 1514; 320 in repaus).
Ce ajunge in cache-ul C++ ramane acelasi, emisiune cu emisiune.
"""

import calendar
import datetime
import re
import queue
import threading
import time
import zlib
from collections import OrderedDict
from urllib.parse import urlencode
from xml.parsers import expat

from Components import HdsIptvSurse as I
from Components import HdsIptvClient as C
from Components import HdsEpgSalvare as S
from Components.HdsIptvSurse import N_

MAX_COMPRIMAT = 192 * 1024 * 1024  # intrarea se analizeaza din mers (SAX), deci marimea costa timp, nu memorie; termenul o margineste
MAX_XML = 384 * 1024 * 1024
# Cache-ul C++ primeste cel mult 40.000 de emisiuni IPTV si ~32 MB socotiti (eEPGCache::importIptvRows): pe un Viper 4K V20 au intrat 34.699.
# Un abonament mare trimite ~110.000 de emisiuni pe ~5.500 de canale (~20 pe canal, o zi): fara impartire, primele ~1.700 de canale
# aveau ghidul pe o zi, iar restul nimic. Plafonul se imparte pe canalele legate, ca fiecare sa aiba emisiunea de acum si urmatoarele.
MAX_EVENIMENTE = 32000             # pe sursa si incercare, inclusiv copiile pentru acelasi tvg-id
MAX_PE_CANAL = 128
MIN_PE_CANAL = 4                   # acum si urmatoarele trei, si cand sunt foarte multe canale
PE_CANAL_ALES = 48                 # canalele de internet puse de om in buchetele lui (Favorite si altele): ghid pe ~2 zile
MAX_ALESE = 300                    # cel mult atatea canale alese primesc partea mare (restul raman in impartirea obisnuita)


def canaleAlese(director=None):
	"""Referintele echivalente 4097 ale canalelor din releul local, din buchetele omului (userbouquet.*, in afara de cele IPTV ale
	imaginii): ele primesc ghidul intai, PE_CANAL_ALES emisiuni, iar restul isi imparte ce ramane din MAX_EVENIMENTE."""
	import glob
	import os
	rez = set()
	for f in glob.glob(os.path.join(director or I.DIRECTOR, "userbouquet.*.tv")):
		if os.path.basename(f) == I.BUCHET_RADACINA:
			continue
		try:
			with open(f, encoding="utf-8", errors="replace") as fis:
				for r in fis:
					if r.startswith(("#SERVICE 4097:", "#SERVICE 5001:", "#SERVICE 5002:")) and "8897" in r:
						sid, cheie = I.desparteCale(r)
						if sid is not None:
							rez.add(I.refCanal(sid, cheie))
							if len(rez) >= MAX_ALESE:
								return rez
		except (IOError, OSError):
			continue
	return rez
MAX_CANALE_XML = 60000
MAX_TEXTE = 2048
MAX_ADANCIME = 32
ZILE = 7
TERMEN_TOTAL_S = 300               # ghidul unui abonament mare: 52-110 s masurat pe receptor, server lent inclus
TERMEN_CITIRE_S = 45               # serverul tace in mijlocul fisierului (il genereaza din mers)
INCERCARI = 3                      # caderile de retea (termen, legatura rupta, 5xx) se reiau; un fisier stricat nu
PAUZA_INCERCARE_S = 20
BUCATA = 65536
LOT = 16
MAX_LOTURI = 32                    # cel mult 512 evenimente in asteptarea importului C++
MAX_SNAPSHOTURI = 2               # numai chei/nume/tvg-id, fara adrese de flux, logo sau antete
PAS_LUCRU_S = 0.25                # firul lucreaza cam atat (bucati de 64 KB adunate), apoi doarme
PAUZA_RAPORT = 1.0                # somnul = atata din lucrul adunat: GIL-ul ramane liber interfetei jumatate din timp
PAUZA_MAX_S = 0.5                 # o pauza nu trece de atat (o bucata lunga, de pilda cand interfata a tinut GIL-ul)
PAS_CANALE = 512                  # harta canalelor din lista (pana la I.MAX_CANALE) se face in bucati de atatea, cu pauze
MAX_ORE = 4096                    # orele XMLTV deja citite (se repeta de la un canal la altul); peste atatea se ia de la capat
MAX_CID = 8192                    # canalele din <programme> deja cautate dupa nume (rezultatul, si cand e gol)

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
_cereri_cache = queue.Queue(MAX_LOTURI)
_lot_ocupat = None
_stare_de_refacut = None
_lacat_trezire = threading.Lock()
_trezire_cache = False


class _Oprit(Exception):
	pass


def _verificaOprire():
	if S.inchis():
		raise _Oprit()


class _CachePrincipal:
	"""Lucratorul trimite loturi limitate; numai notifica() atinge cache-ul C++."""
	def __init__(self):
		self.total = 0
		self.eroare = None
		self.pauze = 0.0

	def _executa(self, ref, lot, gata):
		try:
			_verificaOprire()
			if self.eroare is not None:
				raise self.eroare
			cache = S._cache()
			_verificaOprire()
			incearca = getattr(cache, "tryImportEvents", None)
			if not callable(incearca):
				raise EroareEpg(E_NUCLEU)
			if ref is not None:
				n = incearca(ref, lot)
				if n == -1:
					return False
				self.total += n
		except Exception as e:
			self.eroare = e
		gata.set()
		return True

	def _trimite(self, ref=None, lot=None, asteapta=False):
		_verificaOprire()
		if self.eroare is not None:
			raise self.eroare
		gata = threading.Event()
		if threading.current_thread() is threading.main_thread():
			if not self._executa(ref, lot, gata):
				# Calea normala este lucratorul; un apel sincron nu poate astepta UI-ul.
				raise EroareEpg(E_NUCLEU)
		else:
			t = time.monotonic()
			while True:
				_verificaOprire()
				try:
					_cereri_cache.put((self, ref, lot, gata), timeout=0.1)
					break
				except queue.Full:
					pass
			self.pauze += time.monotonic() - t
			_trezesteCache()
		if asteapta:
			t = time.monotonic()
			while not gata.wait(0.1):
				_verificaOprire()
			self.pauze += time.monotonic() - t
		_verificaOprire()
		if self.eroare is not None:
			raise self.eroare

	def importEvents(self, ref, lot):
		self._trimite(ref, lot)
		return 0

	def gata(self):
		self._trimite(asteapta=True)
		return self.total


def _importaPePrincipal():
	global _lot_ocupat
	if threading.current_thread() is not threading.main_thread():
		return
	inceput = time.monotonic()
	for _i in range(MAX_LOTURI):
		if _lot_ocupat is None:
			try:
				_lot_ocupat = _cereri_cache.get_nowait()
			except queue.Empty:
				break
		cache, ref, lot, gata = _lot_ocupat
		if not cache._executa(ref, lot, gata):
			break
		_lot_ocupat = None
		if time.monotonic() - inceput >= 0.01:
			break


def _trezesteCache():
	global _trezire_cache
	with _lacat_trezire:
		if _trezire_cache or S.inchis():
			return
		_trezire_cache = True
	try:
		from twisted.internet import reactor
		reactor.callFromThread(_ticCache)
	except (ImportError, AttributeError):
		with _lacat_trezire:
			_trezire_cache = False


def _ticCache():
	"""Un singur apel programat, loturi marginite, fara dependenta de ceasul listelor."""
	global _trezire_cache
	_importaPePrincipal()
	with _lacat_trezire:
		if (_cereri_cache.empty() and _lot_ocupat is None) or S.inchis():
			_trezire_cache = False
			return
	try:
		from twisted.internet import reactor
		repeta = getattr(reactor, "callLater", None)
		if repeta is not None:
			repeta(0.05 if _lot_ocupat is not None else 0.001, _ticCache)
		else:
			reactor.callFromThread(_ticCache)
	except (ImportError, AttributeError):
		with _lacat_trezire:
			_trezire_cache = False


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


def decalaj():
	"""Secundele adaugate la orele ghidului TV de internet (config.usage.hds_iptv_decalaj_epg, 0.7.5, IPI): pentru furnizorii care scriu
	ora gresit in XMLTV (zona lipsa sau alta). 0 = fara decalaj (din fabrica); intre -12 si +12 ore."""
	import sys
	cfg = sys.modules.get("Components.config")    # pe receptor e mereu incarcat; aici nu se importa nimic (memoria firului EPG)
	try:
		ore = float(cfg.config.usage.hds_iptv_decalaj_epg.value)
	except (AttributeError, KeyError, TypeError, ValueError):
		return 0
	return int(max(-12.0, min(12.0, ore)) * 3600)


def _ora(text):
	m = _DATA.match((text or "").strip())
	if m is None:
		return None
	t = m.group(1)
	try:
		if t.isascii():
			# cifrele direct, fara strptime (pe receptor era jumatate din timpul firului); datetime refuza aceleasi date ca
			# strptime pe 14 cifre: luna 0 sau 13, ziua 31 in noiembrie, ora 24, minutul 60, secunda 60 sau 61, anul 0000
			d = datetime.datetime(int(t[:4]), int(t[4:6]), int(t[6:8]), int(t[8:10]), int(t[10:12]), int(t[12:]))
		else:
			d = datetime.datetime.strptime(t, "%Y%m%d%H%M%S")  # alte cifre Unicode: ca inainte
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


# 0.7.5 (IPI): potrivirea larga dupa nume, pentru canalele fara tvg-id (config.usage.hds_iptv_epg_larg): fara semnele de calitate
# (HD, FHD, 4K, HEVC...), fara diacritice si semne, fara prefixul tarii. Doua tari diferite sub acelasi nume (RO: Sport 1, HU: Sport 1)
# nu se potrivesc deloc; variantele de calitate ale aceluiasi canal (RO: PRO TV HD, RO: PRO TV FHD) primesc acelasi ghid (cel mult 8).
_CALITATE = re.compile(r"(?<![a-z0-9])(?:u?hd|fhd|sd|4k|8k|uhd|hevc|h\.?26[45]|hdr(?:10)?|raw|backup|multi(?:sub|audio)?|\d{2,3}\s?fps|1080[pi]?|720[pi]?|2160p?)(?![a-z0-9])")
_PREFIX = re.compile(r"^\s*(?:[\[(|]\s*)?([a-z]{2,3})\s*(?:[\])|:]|\s-\s|\s\|)\s*")
_SEMNE_NUME = re.compile(r"[^a-z0-9]+")
MAX_LARG = 8


def potrivireLarga():
	import sys
	cfg = sys.modules.get("Components.config")
	try:
		return bool(cfg.config.usage.hds_iptv_epg_larg.value)
	except (AttributeError, KeyError):
		return True


def _numeLarg(text):
	"""-> (prefixul tarii sau "", cheia larga) ; cheia "" cand nu ramane nimic."""
	t = (text or "")[:256]
	if not t.isascii():
		import unicodedata
		t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
	t = t.casefold()
	if t.isalnum():
		# Dupa conversia ASCII, limitele unui cuvant sunt numai capetele lui.
		return "", "" if _CALITATE.fullmatch(t) else t
	m = _PREFIX.match(t)
	prefix = ""
	if m:
		prefix, t = m.group(1), t[m.end():]
	t = _CALITATE.sub(" ", t)
	return prefix, _SEMNE_NUME.sub("", t)


def _nume(text):
	return " ".join((text or "").casefold().split())[:256]


def _dormi(secunde):
	time.sleep(secunde)


class _Ritm:
	"""Pauzele firului EPG. GIL-ul il ia firul interfetei numai cand firul EPG il lasa: la o asteptare in retea sau intr-un somn
	adevarat. Fara pauze, analiza il tinea aproape tot timpul, iar firul interfetei astepta GIL-ul dupa fiecare apel care il
	elibereaza (un fisier citit, un poll), de cate ori trebuia. dupa(t) aduna timpul lucrat de la t; cand trece de PAS_LUCRU_S,
	doarme PAUZA_RAPORT din el (cel mult PAUZA_MAX_S). Guvernatorul de frecventa vede o sarcina de ~50% si coboara ceasul (Viper
	4K: mai mult 400-600 decat 1200 MHz), deci lucrul tine mai mult decat la ceasul intreg; cu o pauza dupa fiecare bucata de
	64 KB era si mai rau (numai 400 MHz, ~300 s); cu bucatile de 0,25 s si cu emisiunile trecute sarite, ~210 s (efectul bucatilor
	singure nu s-a masurat separat). pauze = somnul adunat, scos din termenul total al descarcarii."""

	def __init__(self, dormi=None):
		self.dormi = _dormi if dormi is None else dormi
		self.pauze = 0.0
		self.lucru = 0.0

	def dupa(self, t):
		self.lucru += time.monotonic() - t
		if self.lucru < PAS_LUCRU_S:
			return
		p = min(PAUZA_MAX_S, self.lucru * PAUZA_RAPORT)
		self.lucru = 0.0
		if p > 0:
			self.dormi(p)
			self.pauze += p


def _bucati(f, inceput, ritm=None):
	"""Gzip cu iesire limitata la o bucata chiar si pentru o arhiva foarte comprimata."""
	n = total = 0
	dec = None
	prima = True
	prefix = b""
	citeste = getattr(f, "read1", f.read)  # un singur recv: un server care picura octeti nu ascunde termenul total
	while True:
		_verificaOprire()
		if time.monotonic() - inceput - (ritm.pauze if ritm else 0) > TERMEN_TOTAL_S:
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
				if time.monotonic() - inceput - (ritm.pauze if ritm else 0) > TERMEN_TOTAL_S:
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
	def __init__(self, s, canale, cache, acum, ritm=None, harta=None):
		"""harta: (iduri, nume, larg) facute de un _Xmltv de dinainte pentru aceeasi lista (_hartaPastrata); atunci canale nu
		se mai citeste. Harta nu se schimba dupa ce e facuta (numai se citeste), deci se poate folosi la mai multe importuri."""
		self.sid, self.cache, self.acum = s["id"], cache, acum
		self.iduri, self.nume, self.legate = {}, {}, {}
		self.numar, self.loturi = {}, OrderedDict()
		self.cu_canal = set()      # canalele din lista care au un <channel> in fisier (XMLTV le scrie inaintea emisiunilor)
		self.pe_canal = None       # partea fiecarui canal din MAX_EVENIMENTE, socotita la prima emisiune
		self.ore, self.dupa_nume = {}, {}   # memoria lui _ora si a cautarii dupa nume a canalului din <programme>
		try:
			self.alese = canaleAlese()
		except Exception:
			self.alese = set()
		self.total = self.importate = self.canale_xml = 0
		self.octeti = 0
		self.decalaj = decalaj()
		self.stiva, self.canal, self.program, self.camp, self.text = [], None, None, None, ""
		if harta is not None:
			self.iduri, self.nume, self.larg = harta
		else:
			self._harta(canale, ritm)
		self.parser = expat.ParserCreate()
		self.parser.StartElementHandler = self._incepe
		self.parser.EndElementHandler = self._termina
		# textul se cere numai cat e deschis un camp pastrat (_incepe/_termina): fara un apel inapoi pentru fiecare spatiu dintre
		# elemente si pentru textele care nu se pastreaza (categorii, actori, poze)
		self.parser.CharacterDataHandler = None
		self.parser.StartDoctypeDeclHandler = self._doctype
		self.parser.EntityDeclHandler = self._dtd
		self.parser.ExternalEntityRefHandler = self._dtd

	def harta(self):
		"""(iduri, nume, larg), pentru _hartaPastrata."""
		return self.iduri, self.nume, self.larg

	def _harta(self, canale, ritm):
		"""Harta listei: tvg-id, numele exact si cheia larga -> referintele canalelor din lista."""
		self.larg = {} if potrivireLarga() else None   # cheia larga -> (prefixele tarilor, canalele fara tvg-id)
		t = time.monotonic()
		for i, c in enumerate(canale[:I.MAX_CANALE]):
			_verificaOprire()
			if ritm is not None and i and not i % PAS_CANALE:
				ritm.dupa(t)
				t = time.monotonic()
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
			if self.larg is not None and not (isinstance(tvg, str) and tvg.strip()):
				prefix, cheie = _numeLarg(c[1])
				if cheie:
					tari, refs = self.larg.setdefault(cheie, (set(), []))
					tari.add(prefix)
					if len(refs) < MAX_LARG:
						refs.append(ref)


	def _largi(self, text):
		"""Canalele fara tvg-id cu aceeasi cheie larga, numai dintr-o singura tara. -> lista (poate goala)."""
		if not self.larg:
			return []
		exact = _nume(text)
		if exact in self.nume and self.nume[exact] is None:
			return []           # acelasi nume scris exact la doua canale: regula veche, niciun ghid ghicit
		prefix, cheie = _numeLarg(text)
		tari, refs = self.larg.get(cheie, (None, None)) if cheie else (None, None)
		if not refs or len(tari) > 1 or (prefix and prefix not in tari and "" not in tari):
			return []
		return list(refs)

	def citeste(self, b, gata=False):
		self.octeti += len(b)
		self.parser.Parse(b, gata)
		# Expat asteapta sfarsitul unui atribut/comentariu/token inaintea callback-ului. Nu lasam
		# un singur token ostil sa adune intregul document in tamponul sau intern.
		if self.octeti - self.parser.CurrentByteIndex > BUCATA:
			raise EroareEpg("jeton")


	def _doctype(self, nume, sistem, public, are_subset):
		# <!DOCTYPE tv SYSTEM "xmltv.dtd"> e capul obisnuit al fisierelor XMLTV (DTD-ul extern nu se citeste); un subset intern,
		# locul entitatilor care se umfla, ramane refuzat, ca si orice entitate declarata
		if are_subset:
			raise EroareEpg("DTD")

	def _dtd(self, *args):
		raise EroareEpg("DTD")


	def _incepe(self, tag, attr):
		stiva = self.stiva
		stiva.append(tag)
		n = len(stiva)
		if n > MAX_ADANCIME:
			raise EroareEpg("adancime")
		if n == 1 and tag != "tv":
			raise EroareEpg("radacina")
		if attr and (len(attr) > 32 or max(map(len, attr)) > 128 or max(map(len, attr.values())) > 4096):
			raise EroareEpg("atribute")
		if n == 2:
			if tag == "channel":
				self.canale_xml += 1
				if self.canale_xml > MAX_CANALE_XML:
					raise EroareEpg("canale")
				self.canal = {"id": attr.get("id", "")[:256], "ref": None}
			elif tag == "programme":
				if self.pe_canal is None:
					self._imparte()      # la prima emisiune, legata sau nu, ca inainte
				cid = attr.get("channel", "")[:256]
				refs = self._refs(cid)
				# fara canal legat, cu toate canalele lui pline, terminata deja, peste ZILE zile sau cu ore rele: nimic de importat,
				# deci nici texte de adunat (abonamentele trimit si zilele trecute: pe receptor 160.000 de emisiuni pentru 17.600)
				if refs and self.total < MAX_EVENIMENTE and any(
						self.numar.get(ref, 0) < (PE_CANAL_ALES if ref in self.alese else self.pe_canal) for ref in refs):
					start, stop = attr.get("start", "")[:40], attr.get("stop", "")[:40]
					if self._fereastra(start, stop) is not None:
						self.program = {"id": cid, "start": start, "stop": stop, "refs": refs}
		elif n == 3 and ((self.canal is not None and tag == "display-name") or
				(self.program is not None and tag in ("title", "sub-title", "desc"))):
			self.camp, self.text = tag, ""
			self.parser.CharacterDataHandler = self._text


	def _text(self, text):
		if self.camp is not None and len(self.text) < MAX_TEXTE:
			self.text += text[:MAX_TEXTE - len(self.text)]


	def _termina(self, tag):
		n = len(self.stiva)
		if n == 3 and self.camp == tag:
			if self.canal is not None:
				ref = self.nume.get(_nume(self.text))
				if ref and self.canal["ref"] is None:
					self.canal["ref"] = ref
				elif self.canal["ref"] is None and self.canal.get("larg") is None:
					self.canal["larg"] = self._largi(self.text)
			elif self.program is not None and tag not in self.program:
				self.program[tag] = self.text.strip()
			self.camp, self.text = None, ""
			self.parser.CharacterDataHandler = None
		elif n == 2:
			if tag == "channel" and self.canal is not None:
				cid = self.canal["id"]
				if cid and cid not in self.iduri and self.canal["ref"]:
					self.legate[cid] = [self.canal["ref"]]
				elif cid and cid not in self.iduri and self.canal.get("larg"):
					self.legate[cid] = self.canal["larg"]
				if self.cu_canal is not None and len(self.cu_canal) < I.MAX_CANALE:
					self.cu_canal.update(self.iduri.get(cid) or self.legate.get(cid) or ())
				self.canal = None
			elif tag == "programme" and self.program is not None:
				self._eveniment(self.program)
				self.program = None
		self.stiva.pop()


	def _imparte(self):
		"""Partea fiecarui canal din MAX_EVENIMENTE, la prima emisiune din fisier (canalele vazute pana atunci in <channel>)."""
		alese = len(self.alese & self.cu_canal) if self.cu_canal else 0
		rest = max(0, MAX_EVENIMENTE - alese * PE_CANAL_ALES)
		altele = len(self.cu_canal) - alese if self.cu_canal else 0
		self.pe_canal = max(MIN_PE_CANAL, min(MAX_PE_CANAL, rest // altele)) if altele > 0 else MAX_PE_CANAL
		self.cu_canal = None


	def _refs(self, cid):
		"""Canalele din lista legate de channel="cid": tvg-id, apoi <channel> cu nume potrivit, apoi chiar cid ca nume (exact sau
		larg). Cautarea dupa nume nu depinde de fisier, deci se memoreaza; legate creste cu fiecare <channel>, deci se citeste mereu."""
		refs = self.iduri.get(cid) or self.legate.get(cid)
		if refs:
			return refs
		try:
			return self.dupa_nume[cid]
		except KeyError:
			pass
		ref = self.nume.get(_nume(cid))
		refs = [ref] if ref else (self._largi(cid) or ())   # () comun pentru cele fara pereche, de obicei cele mai multe
		if len(self.dupa_nume) >= MAX_CID:
			self.dupa_nume.clear()
		self.dupa_nume[cid] = refs
		return refs


	def _ora(self, text):
		try:
			return self.ore[text]
		except KeyError:
			pass
		if len(self.ore) >= MAX_ORE:
			self.ore.clear()
		r = self.ore[text] = _ora(text)
		return r


	def _fereastra(self, start, stop):
		"""(inceput, sfarsit) in secunde, cu decalajul, sau None cand emisiunea nu intra: ore rele, durata zero, negativa sau peste
		o zi, terminata deja ori care incepe dupa ZILE zile."""
		start, stop = self._ora(start), self._ora(stop)
		if start is None or stop is None:
			return None
		if self.decalaj:
			start, stop = start + self.decalaj, stop + self.decalaj
		if stop <= start or stop - start > 24 * 3600 or stop <= self.acum or start > self.acum + ZILE * 86400:
			return None
		return start, stop


	def _eveniment(self, p):
		if self.total >= MAX_EVENIMENTE:
			return
		if self.pe_canal is None:
			self._imparte()
		cid = p["id"]
		refs = p.get("refs")
		if refs is None:
			refs = self._refs(cid)
		ore = self._fereastra(p["start"], p["stop"])
		if not refs or ore is None or not p.get("title"):
			return
		start, stop = ore
		eid = zlib.crc32((cid + "/" + str(start)).encode("utf-8")) & 65535 or 1
		eveniment = (start, stop - start, p["title"][:240], p.get("sub-title", "")[:240], p.get("desc", "")[:1800], eid)
		for ref in refs:
			if self.total >= MAX_EVENIMENTE or self.numar.get(ref, 0) >= (PE_CANAL_ALES if ref in self.alese else self.pe_canal):
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


# 0.7.7 (EPG3): harta listei (_Xmltv._harta: tvg-id, numele exacte si cheile largi ale celor ~29.000 de canale ale unui abonament
# mare) costa ~6,6 s de procesor pe un Viper 4K la fiecare import, si cand lista e aceeasi: la fiecare incercare reluata dupa o
# cadere de retea (_cuIncercari) si la improspatarea zilnica a unei liste neschimbate. Se pastreaza harta ultimului import (una
# singura: ~8 MB pe receptor la 29.000 de canale), cu cheia (sursa, potrivirea larga, semnatura octetilor fisierului listei);
# alta lista sau alta sursa o inlocuieste. Importul de dupa o repornire a interfetei o face din nou (memoria se pierde); acolo
# ajuta numai lucrul mai putin (HdsIptvSurse._codeaza: 5,7 s -> 4,2 s pe receptor la 29.000 de canale).
_HARTA = [None]                    # (cheie, (iduri, nume, larg)) sau None; numai firul EPG (_bucla) o atinge


def _cheieHarta(sid, octeti, larg):
	if octeti is None:
		return None
	import hashlib
	return (sid, bool(larg), hashlib.blake2b(octeti, digest_size=20).digest())


def _hartaPastrata(cheie):
	"""Harta pastrata pentru cheie, sau None; la o cheie noua cea veche se uita inainte sa se faca alta (memoria)."""
	p = _HARTA[0]
	if p is not None and cheie is not None and p[0] == cheie:
		return p[1]
	_HARTA[0] = None
	return None


def _pastreazaHarta(cheie, harta):
	_HARTA[0] = (cheie, harta)


def lucreaza(s, canale, cache=None):
	"""O sursa pe firul EPG. Rezultat: numarul evenimentelor importate; erorile raman fara URL."""
	_verificaOprire()
	adresa = adresaEpg(s)
	if adresa is None:
		return 0
	if cache is None:
		cache = _CachePrincipal()
		cache._trimite(asteapta=True)
	if cache is None or not hasattr(cache, "importEvents"):
		raise EroareEpg(E_NUCLEU)
	harta = cheie = None
	if canale is None:
		# harta de la importul de dinainte, daca fisierul listei are aceiasi octeti (atunci lista nici nu se mai citeste)
		octeti = I.octetiCanale(s["id"])
		cheie = _cheieHarta(s["id"], octeti, potrivireLarga())
		harta = _hartaPastrata(cheie)
		if harta is None:
			# fara fisier, lista (goala) vine ca inainte, din citesteCanale
			canale = I.canaleDinOcteti(octeti) if octeti is not None else I.citesteCanale(s["id"])
		octeti = None
		if harta is None and not canale:
			return 0
	elif not canale:
		return 0
	inceput = time.monotonic()
	ritm = _Ritm()
	xml = _Xmltv(s, canale, cache, time.time(), ritm, harta)
	canale = None  # dupa mapare eliberam lista citita din JSON, inclusiv toate adresele de flux
	if cheie is not None and harta is None:
		_pastreazaHarta((cheie[0], xml.larg is not None, cheie[2]), xml.harta())
	try:
		with C.deschide(adresa, C.anteteSursa(s), termen=TERMEN_CITIRE_S) as f:
			for b in _bucati(f, inceput, ritm):
				_verificaOprire()
				t = time.monotonic()
				pauze = cache.pauze if isinstance(cache, _CachePrincipal) else 0
				xml.citeste(b)
				asteptare = cache.pauze - pauze if isinstance(cache, _CachePrincipal) else 0
				# Coada nu este retea sau analiza si nu cere inca o pauza de procesor.
				ritm.pauze += asteptare
				ritm.dupa(t + asteptare)
			xml.citeste(b"", True)
		n = xml.gata()
		return cache.gata() if isinstance(cache, _CachePrincipal) else n
	finally:
		# Un document intrerupt nu lasa loturi pentru un import terminat deja.
		if isinstance(cache, _CachePrincipal):
			cache.eroare = _Oprit()


def _deReluat(e):
	"""Caderile de retea se reiau: legatura rupta, serverul care tace TERMEN_CITIRE_S, nu raspunde sau da 5xx. Nu: un fisier stricat
	sau prea lent in total (EroareEpg), contul refuzat (401/403), certificatul, prea multe conexiuni."""
	if isinstance(e, EroareEpg):
		return False
	if isinstance(e, C.EroareIptv):
		cod = getattr(e, "cod", 0) or 0
		return e.mesaj == C.E_NU_RASPUNDE and (cod == 0 or (cod >= 500 and cod not in C.COD_CONEXIUNI))
	import http.client
	return isinstance(e, (OSError, http.client.HTTPException))


def _cuIncercari(s, canale, asteapta=time.sleep):
	"""lucreaza() de cel mult INCERCARI ori. Emisiunile importate inainte de cadere raman; a doua trecere le scrie peste ele."""
	for i in range(INCERCARI):
		_verificaOprire()
		try:
			return lucreaza(s, canale)
		except Exception as e:
			_verificaOprire()
			if i + 1 >= INCERCARI or not _deReluat(e):
				raise
			print("[HdsIptvEpg] sursa %s: %s, din nou peste %d s" % (s.get("id"), type(e).__name__, PAUZA_INCERCARE_S))
			if asteapta is time.sleep:
				S._oprire.wait(PAUZA_INCERCARE_S)
			else:
				asteapta(PAUZA_INCERCARE_S)


def _stare(sid, stare, n=0, mesaj=""):
	try:
		return I.actualizeazaSursa(sid, epg_stare=stare, epg_evenimente=n, epg_mesaj=mesaj, epg_ora=int(time.time()))
	except Exception as e:
		print("[HdsIptvEpg] salvarea starii: %s" % type(e).__name__)


_CAMPURI_STARE = ("epg_stare", "epg_evenimente", "epg_mesaj", "epg_ora")


def _revine(sid, inainte, scris):
	try:
		_refaceStarea(sid, inainte, scris)
	except Exception as e:
		print("[HdsIptvEpg] refacerea starii: %s" % type(e).__name__)


def _refaceLaIesire():
	# Reteaua poate ramane blocata. Refacerea nu depinde de revenirea ei.
	incercare = _stare_de_refacut
	if incercare is not None:
		threading.Thread(target=_revine, args=incercare, name="HdsEpgStare", daemon=True).start()


S._la_oprire.append(_refaceLaIesire)


def _refaceStarea(sid, inainte, scris):
	"""Reface numai starea proprie intrerupta, fara a rescrie modificarile altcuiva."""
	if inainte is None or scris is None:
		return
	with I._LACAT:
		surse = I.citesteSurse()
		for s in surse:
			if s.get("id") != sid:
				continue
			if any(s.get(k) != scris.get(k) for k in _CAMPURI_STARE):
				return
			for k in _CAMPURI_STARE:
				if k in inainte:
					s[k] = inainte[k]
				else:
					s.pop(k, None)
			I.scrieSurse(surse)
			return


def _bucla():
	global _fir, _in_lucru
	try:
		_lucreazaCoada()
	finally:
		with _lacat:
			if _fir is threading.current_thread():
				_fir, _in_lucru = None, None


def _lucreazaCoada():
	global _fir, _in_lucru, _de_notificat, _stare_de_refacut
	while True:
		with _lacat:
			if S.inchis():
				_coada.clear()
				_de_notificat = False
			if not _coada:
				_fir, _in_lucru = None, None
				return
			_in_lucru, (s, canale) = _coada.popitem(last=False)
		with I._LACAT:
			if S.inchis():
				continue
			inainte = I.sursa(_in_lucru)
			scris = _stare(_in_lucru, "lucreaza")
			_stare_de_refacut = (_in_lucru, inainte, scris)
		try:
			_verificaOprire()
			n = _cuIncercari(s, canale)
			_verificaOprire()
			mesaj = ""
			with I._LACAT:
				_verificaOprire()
				scris = _stare(_in_lucru, "gata", n, E_GATA if n else E_GOL)
				_stare_de_refacut = (_in_lucru, inainte, scris)
				_verificaOprire()
		except _Oprit:
			_revine(_in_lucru, inainte, scris)
			continue
		except Exception as e:
			if S.inchis():
				_revine(_in_lucru, inainte, scris)
				continue
			n, mesaj = 0, E_NUCLEU if isinstance(e, EroareEpg) and e.mesaj == E_NUCLEU else E_ESUAT
			print("[HdsIptvEpg] sursa %s: %s %s" % (_in_lucru, type(e).__name__, e.mesaj if isinstance(e, EroareEpg) else ""))
			with I._LACAT:
				if S.inchis():
					_revine(_in_lucru, inainte, scris)
					continue
				scris = _stare(_in_lucru, "eroare", n, mesaj)
				_stare_de_refacut = (_in_lucru, inainte, scris)
				if S.inchis():
					_revine(_in_lucru, inainte, scris)
					continue
		finally:
			_stare_de_refacut = None
		canale = None  # nu pastram lista sursei terminate cat timp incepe urmatoarea
		with _lacat:
			if S.inchis():
				continue
			_ultimele[_in_lucru] = (n, mesaj)
			if n:
				_de_notificat = True
			_ultimele.move_to_end(_in_lucru)
			while len(_ultimele) > I.MAX_SURSE:
				_ultimele.popitem(last=False)


def cere(s, canale=None):
	"""Pune sursa in coada si revine imediat. Reteaua si analiza nu tin firul UI."""
	global _fir
	if not isinstance(s, dict) or not I._ID_SURSA.match(s.get("id", "")):
		return False
	try:
		if adresaEpg(s) is None:
			return False
	except Exception:
		return False
	with _lacat:
		if S.inchis():
			return False
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
	if threading.current_thread() is not threading.main_thread():
		return False
	_importaPePrincipal()
	if _de_notificat:
		S._cache()
	if S.inchis():
		with _lacat:
			_de_notificat = False
		return False
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

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Baza de pornire a canalelor: valorile tehnice ale canalelor (rezolutia, codarea, pistele, PID-urile, accesul, HbbTV)
aflate de Scanarea detaliata pe un receptor de proba, curatate de orice data personala si unite in baza unica a
receptorului (Components/HdsBazaCanale.py).

FISIERELE (acelasi format: JSONL in gzip; antetul {"fel":"hds-baza-canale","v":1,"scris":<prima zi a lunii>,
"pornire":"AAAA.LL.N","canale":N,"transpondere":M,"rezerve_duble":[...]}, randurile cu fel 2, apoi {"sfarsit":N}):
  imagine  ${datadir}/enigma2/hds-baza-pornire.jsonl.gz      venit cu imaginea (data/, dist_pkgdata_DATA)
  stb      /etc/enigma2/hds_baza_pornire_stb.jsonl.gz       luat de pe stb.hdsatelit.com, numai cu setarea "Ia baza
           de canale de pe stb.hdsatelit.com" pornita (config.usage.hds_baza_stb, oprita din fabrica)

UNIREA (Unire, pe bucati: fiecare pas() face cel mult `bucata` randuri; ceasurile bazei din Components/
HdsCulegereCanale.py o pornesc dupa migrare, numai dupa o pornire curata si in afara unei inregistrari):
  - un fisier se uneste cand md5-ul lui difera de cel notat in antetul bazei (pornire_md5 / pornire_stb_md5): deci la
    prima pornire, dupa o actualizare care aduce alta baza si dupa o descarcare noua; altfel nu se citeste;
  - fisierele se unesc in ordinea versiunilor; unul mai vechi decat cea mai noua baza unita (pornire_versiune) se sare,
    iar cel de pe stb se sare si cand e mai vechi decat cel din imagine;
  - NUMAI unde receptorul nu stie nimic: o valoare a receptorului bate mereu una de pornire (HdsBazaCanale.castiga_nou),
    deci ce culege receptorul singur ramane; intre doua baze de pornire castiga cea mai noua;
  - cheia de rezerva: un rand al carui canal lipseste din lamedb, dar are in lamedb un singur serviciu pe aceeasi cheie
    de rezerva (onid:tsid:sid@poz), se uneste sub cheia din lamedb (alt namespace, de pilda alta frecventa); cheile din
    "rezerve_duble" ale fisierului nu se potrivesc asa (nu se ghiceste);
  - la sfarsit, pentru fiecare serviciu din lamedb, singurul alt rand al bazei de pe aceeasi cheie de rezerva se muta
    sub cheia lui si se uneste cu randul ei, daca are deja unul (BazaCanale.cauta(..., rezerva=True), numai cu un
    singur serviciu in lamedb pe ea): asa se potrivesc si randurile vechi ale receptorului dupa o scanare pe alte
    frecvente, iar valorile lor bat pe cele de pornire;
  - asteapta ceasul (inainte de 2026, sau in urma lunii bazei, datele ar iesi necunoscute) si o baza care se scrie
    (numai-citire sau scrieri oprite: nimic, se incearca la pornirea urmatoare);
  - md5-ul se noteaza numai dupa un fisier unit pana la capat (randul de sfarsit cu numarul bun); pe disc ajunge cu
    urmatoarea scriere a bazei (o singura scriere la prag, nu una pe bucata).
MEMORIA: fisierul se citeste rand cu rand din gzip (nimic intreg in memorie), cel mult HdsBazaCanale.MAX_CITIT octeti
desfacuti si randuri de cel mult RAND_CITIT; lamedb-ul se citeste tot rand cu rand (cheile si o harta de intregi).
FIRUL (din ceasurile bazei, Unire(fir=fir_unire)): lamedb-ul se citeste si se desface pe un fir (citeste_lamedb_pe_fir,
cu paza scrierii pe loc a nucleului), iar harta cheilor de rezerva a bazei se face tot pe fir, dintr-o copie a cheilor
(HdsBazaCanale.BazaCanale.pregateste_rezerva): pe 0.7.6 amandoua stateau intr-un singur pas pe firul interfetei, la
fiecare pornire si dupa fiecare schimbare a lamedb-ului (3 s cu 23 920 de servicii pe Octagon, 9,4 s pe un u57).

DESCARCAREA (descarca, blocanta, intr-un fir; Zilnic o porneste din ticul bazei): intai suma publicata (<url>.sha256);
daca e aceeasi cu a fisierului stb de pe receptor, nu se mai ia nimic si nu se scrie nimic (eMMC). Altfel fisierul
(HTTPS cu certificatul verificat, cel mult MARIME_GZ_MAX), suma lui, gzip-ul desfacut si verificat in memorie
(antetul, randurile ASCII sub RAND_CITIT, sfarsitul), apoi scriere atomica (.nou + fsync + replace + fsync pe dosar).
Zilnic: prima privire la PRIMA_S dupa pornirea ceasurilor, apoi o data la 24 de ore (3 ore dupa o incercare cazuta);
starea sta numai in memorie, deci dupa o repornire se ia din nou doar suma (64 de octeti).

Partea de sus e curata (fara enigma): probele pe PC in 
test_baza_pornire_*.py.
"""

from __future__ import absolute_import

import gzip
import hashlib
import io
import json
import os
import sys
import threading
import time
import zlib

try:
	from Components import HdsBazaCanale as B
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsBazaCanale as B

NUME_IMAGINE = "hds-baza-pornire.jsonl.gz"
CALE_IMAGINE_IMPLICITA = "/usr/share/enigma2/" + NUME_IMAGINE
CALE_STB = "/etc/enigma2/hds_baza_pornire_stb.jsonl.gz"
CALE_LAMEDB = "/etc/enigma2/lamedb"
URL = "https://stb.hdsatelit.com/receptor/canale/baza.jsonl.gz"
MARIME_GZ_MAX = 4 * 1024 * 1024
MARIME_LAMEDB_MAX = 32 * 1024 * 1024
TIMP_DESCARCARE = 20.0
BUCATA = 200
BUCATA_REZERVE = 500
# unirea taiata dupa timp (Unire cu felie_s, din ceasurile bazei): randurile citite se unesc cate MINI_UNIRE, iar pasul se
# opreste cand trece felia. Pe procesorul unui receptor un rand unit peste unul existent tine ~2-3 ms (200 de randuri: 0,5 s;
# in enigma2, cu lacatul Python impartit, 1,5-3 s). Pe timp, nu pe numar: cand alt fir Python (de pilda EPG-ul IPTV) tine
# lacatul, o bucata pe numar se lungeste (masurat pe un u57: 20 de randuri = pana la 632 ms), o felie de timp nu
MINI_UNIRE = 5
# citirea lamedb-ului pe un fir (Unire cu fir, din ceasurile bazei): o pauza de CEDEAZA_S la CEDEAZA_LA servicii, ca firul
# interfetei sa ia lacatul Python repede; o citire prinsa de o scriere a lamedb-ului se reia de cel mult INCERCARI_LAMEDB
# ori, la PAUZA_LAMEDB_S una de alta, iar la predare (firul interfetei) o semnatura schimbata de atunci o reia de cel mult
# RECITIRI_LAMEDB ori
CEDEAZA_LA = 256
CEDEAZA_S = 0.001
INCERCARI_LAMEDB = 3
PAUZA_LAMEDB_S = 1.0
RECITIRI_LAMEDB = 2

PRIMA_S = 300
INTERVAL_S = 24 * 3600
REINCERCARE_S = 3 * 3600

# rezultatele unui fisier (Unire.rez)
LIPSESTE = "lipseste"
LA_ZI = "la zi"
UNIT = "unit"
SARIT = "sarit"
RESPINS = "respins"
STRICAT = "stricat"
CEAS = "ceas"
NESCRIS = "nescris"
# rezultatele descarcarii
NOU = "nou"
EROARE = "eroare"

SURSE = (("imagine", "pornire_md5"), ("stb", "pornire_stb_md5"))


def _jurnal(text):
	print("[HdsBazaPornire] %s" % text)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele date lui tr() in texte_despre se traduc la folosire."""
	return text


def cale_imagine():
	"""Fisierul venit cu imaginea: ${datadir}/enigma2/hds-baza-pornire.jsonl.gz."""
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/" + NUME_IMAGINE)
	except Exception:
		return CALE_IMAGINE_IMPLICITA


# ---------------------------------------------------------------- fisierele

def md5_fisier(cale):
	"""md5 (hex) al unui fisier, citit pe bucati; None daca lipseste sau nu se poate citi."""
	h = hashlib.md5()
	try:
		with open(cale, "rb") as f:
			for bucata in iter(lambda: f.read(65536), b""):
				h.update(bucata)
	except (IOError, OSError):
		return None
	return h.hexdigest()


def sha256_fisier(cale):
	h = hashlib.sha256()
	try:
		with open(cale, "rb") as f:
			for bucata in iter(lambda: f.read(65536), b""):
				h.update(bucata)
	except (IOError, OSError):
		return None
	return h.hexdigest()


def antet_valid(o):
	"""Antetul unei baze de pornire: obiect cu fel, v cunoscut, scris intreg, versiunea text."""
	return isinstance(o, dict) and o.get("fel") == B.FEL and isinstance(o.get("v"), int) and \
		not isinstance(o.get("v"), bool) and 1 <= o["v"] <= B.VERSIUNE and isinstance(o.get("scris"), int) and \
		not isinstance(o.get("scris"), bool) and isinstance(o.get("pornire"), str) and 0 < len(o["pornire"]) <= 32


def antet(cale):
	"""Antetul (primul rand) unei baze de pornire in gzip, sau None (lipsa, stricat, alt fel)."""
	try:
		with gzip.open(cale, "rb") as f:
			linie = f.readline(B.RAND_CITIT + 1)
	except (IOError, OSError, EOFError, zlib.error):
		return None
	if not linie.endswith(b"\n"):
		return None
	try:
		o = json.loads(linie.decode("ascii"))
	except (ValueError, UnicodeDecodeError):
		return None
	return o if antet_valid(o) else None


def cheie_versiune(a):
	"""Ordinea versiunilor ("AAAA.LL.N"), apoi luna; un text care nu e asa vine inaintea tuturor."""
	if not a:
		return ((), 0)
	try:
		v = tuple(int(x) for x in a.get("pornire", "").split("."))
	except ValueError:
		v = ()
	return (v, a.get("scris", 0))


def amprenta(cale):
	"""[mtime, marime] al unui fisier (lamedb), sau None."""
	try:
		st = os.stat(cale)
	except (IOError, OSError):
		return None
	return [int(st.st_mtime), int(st.st_size)]


def _semnatura(st):
	return (getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)), st.st_size, st.st_ino)


def semnatura_lamedb(cale):
	"""(mtime_ns, marime, inode) al fisierului, sau None: nucleul scrie lamedb pe loc (lib/dvb/db.cpp, fopen "w"), deci
	o scriere schimba data si, de cele mai multe ori, marimea, iar inode-ul ramane."""
	try:
		return _semnatura(os.stat(cale))
	except (IOError, OSError):
		return None


class Lamedb(object):
	"""Serviciile din lamedb, citit rand cu rand: cheile (forma cheii bazei) si, pe fiecare cheie de rezerva,
	namespace-ul singurului serviciu (>= 0) sau minus numarul serviciilor (mai multe). complet: randul "end" al
	serviciilor citit; semn: semnatura fisierului deschis (fstat), aceeasi inainte si dupa citire, altfel None.
	cedeaza=True (citirea pe fir): o pauza de CEDEAZA_S la CEDEAZA_LA servicii."""

	def __init__(self, cale=CALE_LAMEDB, cedeaza=False):
		self.chei = []
		self.multime = set()
		self.harta = {}
		self.citit = False
		self.complet = False
		self.semn = None
		self._cedeaza = cedeaza
		self._unice = None
		if cale is None:
			return
		try:
			if os.path.getsize(cale) > MARIME_LAMEDB_MAX:
				_jurnal("lamedb prea mare; fara potrivirea pe cheia de rezerva")
				return
			with io.open(cale, "r", encoding="utf-8", errors="replace") as f:
				inainte = _semnatura(os.fstat(f.fileno()))
				self._citeste(f)
				if inainte == _semnatura(os.fstat(f.fileno())):
					self.semn = inainte
			self.citit = True
		except (IOError, OSError):
			pass

	@classmethod
	def gol(cls):
		"""Un lamedb fara servicii (ca unul lipsa): fara potrivirea pe cheia de rezerva."""
		return cls(None)

	def _citeste(self, f):
		for linie in f:
			if linie.strip() == "services":
				break
		i = 0
		cedeaza = self._cedeaza
		for linie in f:
			s = linie.strip()
			if s == "end":
				self.complet = True
				break
			if i % 3 == 0:
				parti = s.split(":")
				if len(parti) >= 4:
					try:
						sid, ns, tsid, onid = [int(x, 16) for x in parti[:4]]
					except ValueError:
						sid = None
					if sid is not None:
						self._adauga("%x:%x:%x:%x" % (sid, ns, tsid, onid), ns)
				if cedeaza and i % (3 * CEDEAZA_LA) == 0:
					time.sleep(CEDEAZA_S)
			i += 1

	def _adauga(self, k, ns):
		if k in self.multime:
			return
		self.multime.add(k)
		self.chei.append(k)
		r = B.cheie_rezerva(k)
		if r is None:
			return
		e = self.harta.get(r)
		self.harta[r] = ns if e is None else (-2 if e >= 0 else e - 1)

	def unice(self):
		"""[(cheie, cheie de rezerva)] ale serviciilor singure pe cheia lor de rezerva, in ordinea din lamedb: cele pe care
		unirea le cauta in baza la sfarsit. Facuta o data (pe firul care a citit lamedb-ul, cand e citit pe fir)."""
		u = self._unice
		if u is None:
			u = []
			n = 0
			for k in self.chei:
				r = B.cheie_rezerva(k)
				if r is not None and self.harta.get(r, -1) >= 0:
					u.append((k, r))
				n += 1
				if self._cedeaza and n % CEDEAZA_LA == 0:
					time.sleep(CEDEAZA_S)
			self._unice = u
		return u

	def singurul(self, rezerva):
		"""Cheia singurului serviciu din lamedb pe cheia de rezerva, sau None."""
		e = self.harta.get(rezerva)
		if e is None or e < 0:
			return None
		parti, _poz = rezerva.split("@", 1)
		onid, tsid, sid = [int(x, 16) for x in parti.split(":")]
		return "%x:%x:%x:%x" % (sid, e, tsid, onid)


def cheie_potrivita(k, lamedb, duble):
	"""Cheia sub care se uneste randul k pe acest receptor: k insusi, sau cheia din lamedb a singurului serviciu cu
	aceeasi cheie de rezerva (cand k lipseste din lamedb si cheia de rezerva nu e dubla in fisier)."""
	if lamedb is None or not lamedb.chei or k in lamedb.multime:
		return k
	r = B.cheie_rezerva(k)
	if r is None or r in duble:
		return k
	return lamedb.singurul(r) or k


def citeste_lamedb_pe_fir(cale, incercari=INCERCARI_LAMEDB, pauza=PAUZA_LAMEDB_S, dormi=None):
	"""Lamedb-ul citit de pe un fir (Unire cu fir). Nucleul scrie lamedb pe loc, deci o citire de pe alt fir decat al
	interfetei poate prinde fisierul pe jumatate; se primeste numai o citire cu aceeasi semnatura (mtime_ns, marime,
	inode) pe descriptor inainte si dupa si pe cale dupa, si cu randul "end" al serviciilor (fara el numai la ultima
	incercare, cum l-ar fi citit si firul interfetei: un fisier stricat, dar care nu se mai schimba); altfel se citeste din
	nou dupa `pauza`. Lipsa sau prea mare: ca pe firul interfetei. -> Lamedb, sau Lamedb.gol() cand fisierul s-a schimbat
	la fiecare incercare (unirea merge fara potrivirea pe cheia de rezerva, iar ceasurile bazei o reiau la tic: amprenta
	lamedb-ului s-a schimbat)."""
	dormi = dormi or time.sleep
	for i in range(incercari):
		l = Lamedb(cale, cedeaza=True)
		if not l.citit:
			return l
		if l.semn is not None and l.semn == semnatura_lamedb(cale) and (l.complet or i == incercari - 1):
			l.unice()
			return l
		if i < incercari - 1:
			dormi(pauza)
	_jurnal("lamedb s-a schimbat in timpul fiecarei citiri; unirea merge fara potrivirea pe cheia de rezerva")
	return Lamedb.gol()


# ---------------------------------------------------------------- unirea pe bucati

class Unire(object):
	"""Unirea bazelor de pornire in baza `b`, pe bucati (vezi antetul modulului). pas() -> True cat mai e de lucru;
	rez = {"imagine": stare, "stb": stare, "rezerve": numarul randurilor mutate}; numere = {sursa: (adaugate,
	schimbate, respinse)}.
	fir: functie(lucru) -> firul pornit (cu is_alive), pentru munca grea care nu atinge baza: citirea lamedb-ului
	(citeste_lamedb_pe_fir, pornita la primul pas) si harta cheilor de rezerva a bazei (BazaCanale.pregateste_rezerva,
	din copia cheilor). Cat firul lucreaza, pas() nu face nimic, intoarce True si pune asteapta = True (apelantul revine
	mai tarziu, fara sa se invarta); pe firul apelantului raman numai bucatile care ating baza. fir None: totul pe loc,
	ca inainte (uneste(), probele).
	felie_s: un pas se opreste dupa atatea secunde (randurile unei bucati se unesc cate MINI_UNIRE, cheile de rezerva
	una cate una), iar restul ramane pentru pasul urmator; bugetul bazei se potriveste tot o data la `bucata` randuri.
	felie_s None: pasii pe numar, ca inainte. Rezultatul e acelasi cu si fara fir si felie."""

	def __init__(self, b, cale_imagine_=None, cale_stb=CALE_STB, cale_lamedb=CALE_LAMEDB, bucata=BUCATA, fir=None,
			felie_s=None):
		self.b = b
		self.cai = {"imagine": cale_imagine_ or cale_imagine(), "stb": cale_stb}
		self.cale_lamedb = cale_lamedb
		self.bucata = max(1, int(bucata))
		self.rez = {}
		self.numere = {}
		self.gata = False
		self.asteapta = False
		self._fir = fir
		self.felie_s = felie_s
		self._cron = getattr(time, "monotonic", time.time)
		self._citire = None
		self._recitiri = 0
		# harta cheilor de rezerva a bazei inaintea cheilor de rezerva: pe fir (cu fir) sau pe loc (fara fir), dar mereu
		# intai: fara harta, candidat_rezerva cauta cheie cu cheie peste toata baza (bun pentru o nota, nu pentru mii de chei)
		self._rezerva_gata = False
		self._ramase = None
		self._curent = None
		self._lamedb = None
		self._rezerve = None

	# -------------------------------------------- pasii

	def pas(self):
		self.asteapta = False
		if self.gata:
			return False
		try:
			return self._pas()
		except Exception as e:
			_jurnal("unirea: %s: %s" % (type(e).__name__, e))
			self._inchide()
			return self._sfarsit()

	def _pas(self):
		b = self.b
		if b.stare_scriere()[0] != B.SCRIE:
			for sursa, _cheie in SURSE:
				self.rez.setdefault(sursa, NESCRIS)
			self._inchide()
			return self._sfarsit()
		if self._ramase is None:
			self._ramase = self._alege()
			if self._fir is not None:
				self._porneste_citirea()
			return True
		if self._curent is not None:
			self._bucata()
			return True
		if self._ramase:
			if self._lamedb_gata() is None:
				return self._asteapta()
			self._incepe(self._ramase.pop(0))
			return True
		return self._pas_rezerve()

	def _sfarsit(self):
		self.gata = True
		return False

	def _asteapta(self):
		self.asteapta = True
		return True

	def _lamedb_citit(self):
		if self._lamedb is None:
			self._lamedb = Lamedb(self.cale_lamedb)
		return self._lamedb

	def _porneste_citirea(self):
		c = {}

		def lucreaza():
			try:
				c["lamedb"] = citeste_lamedb_pe_fir(self.cale_lamedb)
			except BaseException as e:
				c["eroare"] = e
		self._citire = c
		try:
			c["fir"] = self._fir(lucreaza)
		except Exception as e:
			# fara fir (de pilda prea multe fire): restul unirii pe loc, ca inainte
			_jurnal("unirea: firul nu a pornit (%s); citesc pe loc" % e)
			self._fir = None
			self._citire = None

	def _lamedb_gata(self):
		"""Lamedb-ul pentru pasul de acum, sau None cat firul il citeste. Fara fir: citit pe loc, ca inainte. La predare
		(pe firul apelantului) semnatura fisierului se verifica inca o data: un lamedb scris dupa citire se citeste din
		nou (de cel mult RECITIRI_LAMEDB ori, apoi unirea merge fara potrivirea pe cheia de rezerva)."""
		if self._lamedb is not None:
			return self._lamedb
		if self._fir is None:
			return self._lamedb_citit()
		c = self._citire
		if c is None:
			self._porneste_citirea()
			return None
		fir = c.get("fir")
		if fir is not None and fir.is_alive():
			return None
		self._citire = None
		if "eroare" in c:
			raise c["eroare"]
		l = c.get("lamedb")
		if l is None:
			raise RuntimeError("citirea lamedb pe fir nu a dat nimic")
		if l.citit and l.semn != semnatura_lamedb(self.cale_lamedb):
			if self._recitiri < RECITIRI_LAMEDB:
				self._recitiri += 1
				self._porneste_citirea()
				return None
			_jurnal("lamedb s-a schimbat dupa fiecare citire; unirea merge fara potrivirea pe cheia de rezerva")
			l = Lamedb.gol()
		self._lamedb = l
		return l

	def _lamedb_neschimbat(self):
		"""Cu fir (unirea tine minute pe o lista mare): inaintea fiecarei bucati noi si a cheilor de rezerva, un lamedb scris
		intre timp (o scanare, editorul de canale) se citeste din nou, ca potrivirea pe cheia de rezerva sa nu ia o cheie
		"singura" dintr-o lista veche (de cel mult RECITIRI_LAMEDB ori in toata unirea). -> True = se poate merge mai
		departe cu lamedb-ul tinut; False = citirea din nou a pornit (pasul asteapta). Fara fir: True, ca inainte."""
		l = self._lamedb
		if self._fir is None or l is None or not l.citit or self._recitiri >= RECITIRI_LAMEDB:
			return True
		if l.semn == semnatura_lamedb(self.cale_lamedb):
			return True
		self._recitiri += 1
		self._lamedb = None
		self._porneste_citirea()
		return False

	def _alege(self):
		"""Fisierele de unit acum, in ordinea versiunilor."""
		b = self.b
		acum = b._ceas()
		alese = []
		antete = {}
		for sursa, cheie_md5 in SURSE:
			cale = self.cai[sursa]
			md5 = md5_fisier(cale)
			if md5 is None:
				self.rez[sursa] = LIPSESTE
				continue
			a = antet(cale)
			if a is None:
				self.rez[sursa] = RESPINS
				_jurnal("%s: antetul nu e al unei baze de pornire (%s)" % (sursa, cale))
				continue
			antete[sursa] = a
			if b.antet_pornire(cheie_md5) == md5:
				self.rez[sursa] = LA_ZI
				continue
			if acum < B.DATA_MIN or a["scris"] > acum + B.ZI_S:
				self.rez[sursa] = CEAS
				_jurnal("%s asteapta ceasul receptorului (%d, baza din %d)" % (sursa, int(acum), a["scris"]))
				continue
			alese.append((cheie_versiune(a), sursa, cale, md5, a))
		if "stb" in antete and "imagine" in antete and cheie_versiune(antete["stb"]) < cheie_versiune(antete["imagine"]):
			alese = [x for x in alese if x[1] != "stb"]
			if self.rez.get("stb") is None:
				self.rez["stb"] = SARIT
				_jurnal("baza de pe stb (%s) e mai veche decat cea din imagine (%s); nu se uneste" % (
					antete["stb"]["pornire"], antete["imagine"]["pornire"]))
		unita = b.antet_pornire("pornire_versiune")
		if isinstance(unita, str) and unita:
			prag = cheie_versiune({"pornire": unita, "scris": 0})[0]
			for x in list(alese):
				if x[0][0] < prag:
					alese.remove(x)
					self.rez[x[1]] = SARIT
					_jurnal("%s: baza %s e mai veche decat cea unita (%s); nu se uneste" % (x[1], x[4]["pornire"], unita))
		alese.sort(key=lambda x: x[0])
		return [x[1:] for x in alese]

	def _incepe(self, ales):
		sursa, cale, md5, a = ales
		try:
			f = gzip.open(cale, "rb")
		except (IOError, OSError) as e:
			self.rez[sursa] = STRICAT
			_jurnal("%s: nu pot deschide %s: %s" % (sursa, cale, e))
			return
		stare = {"mare": False}
		linii = B._linii_marginite(f, stare)
		self._curent = {"sursa": sursa, "md5": md5, "antet": a, "f": f, "linii": linii, "stare": stare, "n": 0,
			"sfarsit": None, "numere": [0, 0, 0], "antet_citit": False,
			"duble": frozenset(x for x in a.get("rezerve_duble", ()) if isinstance(x, str))}
		self._lamedb_citit()

	def _inchide(self):
		c = self._curent
		self._curent = None
		if c is not None:
			try:
				c["f"].close()
			except Exception:
				pass

	def _bucata(self):
		"""Cel mult `bucata` randuri din fisierul curent, unite intr-o singura chemare a bazei; la capatul fisierului,
		verificarea sfarsitului si nota in antet. Cu felie_s, randurile citite raman in c["bune"] si se unesc pe mai multi
		pasi (_uneste_bune), inainte de a citi altele."""
		c = self._curent
		if c.get("bune"):
			self._uneste_bune(c)
			return
		if not self._lamedb_neschimbat() or self._lamedb_gata() is None:
			self.asteapta = True
			return
		lamedb = self._lamedb
		bune = []
		citite = 0
		terminat = False
		try:
			for linie in c["linii"]:
				citite += 1
				if not c["antet_citit"]:
					c["antet_citit"] = True
				else:
					s = self._rand(c, linie, lamedb)
					if s is not None:
						bune.append(s)
				if citite >= self.bucata:
					break
			else:
				terminat = True
		except (IOError, OSError, EOFError, zlib.error) as e:
			self.rez[c["sursa"]] = STRICAT
			_jurnal("%s: gzip stricat: %s" % (c["sursa"], e))
			self._inchide()
			return
		c["bune"] = bune
		c["terminat"] = terminat
		self._uneste_bune(c)

	def _uneste_bune(self, c):
		"""Randurile citite ale bucatii: toate deodata (fara felie, ca inainte) sau cate MINI_UNIRE pana trece felia; bugetul
		bazei se potriveste numai dupa ultimele randuri ale bucatii, ca la unirea dintr-o chemare (acelasi rezultat)."""
		bune = c["bune"]
		limita = None if self.felie_s is None else self._cron() + self.felie_s
		while bune:
			if limita is None:
				parte, bune = bune, []
			else:
				parte, bune = bune[:MINI_UNIRE], bune[MINI_UNIRE:]
			c["bune"] = bune
			n = self.b.uneste_linii_pornire(parte, buget=not bune)
			for i in range(3):
				c["numere"][i] += n[i]
			if bune and self._cron() >= limita:
				return
		if c["terminat"]:
			self._gata_fisier(c)

	@staticmethod
	def _rand(c, linie, lamedb):
		"""Un rand de date -> textul de unit (cu cheia potrivita pe lamedb), sau None (gol, sfarsitul)."""
		s = linie.strip()
		if not s:
			return None
		if s.startswith('{"sfarsit":'):
			try:
				c["sfarsit"] = json.loads(s).get("sfarsit")
			except (ValueError, AttributeError):
				c["sfarsit"] = -1
			return None
		c["n"] += 1
		m = B._RE_CHEIE_RAND.match(s)
		if m and m.group(1) == "k":
			k = m.group(2)
			nou = cheie_potrivita(k, lamedb, c["duble"])
			if nou != k:
				s = '{"k":"%s"%s' % (nou, s[m.end(2) + 1:])
		return s

	def _gata_fisier(self, c):
		self._inchide()
		sursa = c["sursa"]
		self.numere[sursa] = tuple(c["numere"])
		if c["stare"]["mare"]:
			self.rez[sursa] = RESPINS
			_jurnal("%s: peste %d octeti desfacuti; nu se noteaza" % (sursa, B.MAX_CITIT))
			return
		if c["sfarsit"] != c["n"]:
			self.rez[sursa] = STRICAT
			_jurnal("%s: taiat (sfarsit %r, %d randuri); nu se noteaza" % (sursa, c["sfarsit"], c["n"]))
			return
		cheie_md5 = dict(SURSE)[sursa]
		self.b.noteaza_antet_pornire(cheie_md5, c["md5"])
		unita = self.b.antet_pornire("pornire_versiune")
		if not isinstance(unita, str) or cheie_versiune(c["antet"]) >= cheie_versiune({"pornire": unita, "scris": 0}):
			self.b.noteaza_antet_pornire("pornire_versiune", c["antet"]["pornire"])
		self.rez[sursa] = UNIT
		a, s, r = c["numere"]
		_jurnal("%s %s unita: %d canale adaugate, %d completate, %d respinse" % (sursa, c["antet"]["pornire"], a, s, r))

	def _pas_rezerve(self):
		"""Randurile ramase sub o cheie veche dupa o scanare: mutate sub cheia din lamedb si unite cu randul ei (o bucata
		pe pas). Cu fir: intai lamedb-ul si harta cheilor de rezerva a bazei, facute pe fir."""
		lamedb = self._lamedb_gata()
		if lamedb is None or (self._rezerve is None and not self._lamedb_neschimbat()):
			return self._asteapta()
		unice = lamedb.unice()
		if not self._rezerva_gata and unice:
			if not self.b.pregateste_rezerva(self._fir):
				return self._asteapta()
			self._rezerva_gata = True
		if self._rezerve is None:
			self._rezerve = {"i": 0, "mutate": 0}
		r = self._rezerve
		b = self.b
		i = r["i"]
		capat = min(len(unice), i + BUCATA_REZERVE)
		limita = None if self.felie_s is None else self._cron() + self.felie_s
		while i < capat:
			# numai serviciile singure pe cheia lor de rezerva in lamedb (unice), in ordinea din lamedb; si cand k are
			# deja rand (de pilda din baza de pornire): randul vechi al receptorului se uneste in el, cu regula obisnuita
			# (ce stie receptorul castiga)
			k, rez = unice[i]
			i += 1
			if b.candidat_rezerva_cunoscut(k, rez) is not None:
				b.cauta(k, rezerva=True)
				r["mutate"] += 1
			if limita is not None and self._cron() >= limita:
				break
		r["i"] = i
		if i < len(unice):
			return True
		self.rez["rezerve"] = r["mutate"]
		if r["mutate"]:
			_jurnal("cheia de rezerva: %d randuri mutate sub cheia din lamedb" % r["mutate"])
		return self._sfarsit()


def uneste(b, **arg):
	"""Unirea dintr-o bucata (probe, apelanti fara ceas). -> Unire.rez."""
	u = Unire(b, **arg)
	while u.pas():
		pass
	return u.rez


# ---------------------------------------------------------------- verificarea si descarcarea

def verifica_gz(octeti, limita=None):
	"""Un fisier de baza de pornire (octetii gzip) verificat in memorie: antetul, randurile ASCII sub RAND_CITIT, cel
	mult MAX_CITIT octeti desfacuti, sfarsitul cu numarul bun. -> (antetul, numarul randurilor) sau ValueError."""
	limita = min(B.MAX_CITIT, B.MAX_CITIT if limita is None else limita)
	stare = {"mare": False}
	n = 0
	desfacuti = 0
	sfarsit = None
	a = None
	try:
		with gzip.GzipFile(fileobj=io.BytesIO(octeti), mode="rb") as f:
			for linie in B._linii_marginite(f, stare):
				desfacuti += len(linie)
				if desfacuti > limita:
					stare["mare"] = True
					break
				if not linie.endswith("\n") or len(linie) > B.RAND_CITIT + 1 or not linie.isascii():
					raise ValueError("rand prea lung sau care nu e ASCII")
				if a is None:
					a = json.loads(linie)
					if not antet_valid(a):
						raise ValueError("antetul nu e al unei baze de pornire")
					continue
				if sfarsit is not None:
					raise ValueError("randuri dupa sfarsit")
				o = json.loads(linie)
				if not isinstance(o, dict):
					raise ValueError("rand care nu e obiect")
				if "sfarsit" in o:
					sfarsit = o["sfarsit"]
					continue
				if "k" not in o and "tp" not in o:
					raise ValueError("rand fara cheie")
				n += 1
	except (IOError, OSError, EOFError, zlib.error) as e:
		raise ValueError("gzip stricat: %s" % e)
	if stare["mare"]:
		raise ValueError("peste %d octeti desfacuti" % limita)
	if a is None or sfarsit != n:
		raise ValueError("taiat (sfarsit %r, %d randuri)" % (sfarsit, n))
	return a, n


def _citeste_url(url, timp, limita):
	from urllib.request import Request, urlopen
	cerere = Request(url, headers={"User-Agent": "hdsatelit-receptor/1", "Accept-Encoding": "identity"})
	r = urlopen(cerere, timeout=timp)
	try:
		lung = r.headers.get("Content-Length")
		if lung and lung.isdigit() and int(lung) > limita:
			raise ValueError("prea mare (%s octeti)" % lung)
		date = r.read(limita + 1)
	finally:
		r.close()
	if len(date) > limita:
		raise ValueError("prea mare (peste %d octeti)" % limita)
	if lung and lung.isdigit() and int(lung) != len(date):
		raise ValueError("taiat pe drum (%d din %s octeti)" % (len(date), lung))
	return date


def _mesaj_eroare(e):
	"""Textul "ceasul e in urma" cand certificatul cade din cauza ceasului (Components/HdsCeasHttps.py), altfel
	numele erorii."""
	try:
		from Components import HdsCeasHttps
		text = HdsCeasHttps.mesaj(e)
		if text:
			return text
	except Exception:
		pass
	return "%s: %s" % (type(e).__name__, e)


def scrie_atomic(cale, octeti):
	"""Fisier temporar langa cel bun, fsync, os.replace, fsync pe dosar."""
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except BaseException:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise
	try:
		fd = os.open(os.path.dirname(cale) or ".", os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except (OSError, AttributeError):
		pass


def descarca(url=URL, cale=CALE_STB, timp=TIMP_DESCARCARE, citeste_url=None, cale_imagine_=None):
	"""Baza de pe stb, verificata, scrisa numai daca s-a schimbat. Blocanta: fir separat. -> (stare, mesaj); stare
	NOU (scrisa), LA_ZI (aceeasi suma, nimic scris), SARIT (mai veche decat cea din imagine) sau EROARE."""
	citeste_url = citeste_url or _citeste_url
	try:
		suma = citeste_url(url + ".sha256", timp, 512).decode("ascii", "replace").strip().split()
	except Exception as e:
		return EROARE, "suma: %s" % _mesaj_eroare(e)
	suma = suma[0].lower() if suma else ""
	if len(suma) != 64 or any(c not in "0123456789abcdef" for c in suma):
		return EROARE, "suma publicata nu e valida"
	if sha256_fisier(cale) == suma:
		return LA_ZI, "aceeasi baza ca pe receptor"
	try:
		corp = citeste_url(url, timp, MARIME_GZ_MAX)
	except Exception as e:
		return EROARE, "baza: %s" % _mesaj_eroare(e)
	if hashlib.sha256(corp).hexdigest() != suma:
		return EROARE, "suma nu se potriveste"
	try:
		a, n = verifica_gz(corp)
	except ValueError as e:
		return EROARE, "baza respinsa: %s" % e
	din_imagine = antet(cale_imagine_ or cale_imagine())
	if din_imagine and cheie_versiune(a) < cheie_versiune(din_imagine):
		return SARIT, "baza %s e mai veche decat cea din imagine (%s)" % (a["pornire"], din_imagine["pornire"])
	try:
		scrie_atomic(cale, corp)
	except (IOError, OSError) as e:
		return EROARE, "scriere: %s" % e
	return NOU, "baza %s, %d canale" % (a["pornire"], n)


class Zilnic(object):
	"""Descarcarea zilnica, cu setarea pornita: pas(acum, activ) din ticul bazei (o data pe minut), in firul interfetei;
	descarcarea merge intr-un fir. pas intoarce NOU o singura data dupa o descarcare noua (apelantul reface unirea)."""

	def __init__(self, descarca_=None, fir=None, ceas=None):
		self._descarca = descarca_ or descarca
		self._fir = fir or _fir_daemon
		self._ceas = ceas or time.time
		self.inceput = self._ceas()
		self.ultima = None          # (cand, stare, mesaj)
		self._lucru = None
		self._rezultat = None
		self.descarcari = 0

	def e_timpul(self, acum):
		if acum - self.inceput < PRIMA_S and acum >= self.inceput:
			return False
		if self.ultima is None:
			return True
		la, stare = self.ultima[0], self.ultima[1]
		if acum < la:
			return True
		return acum - la >= (REINCERCARE_S if stare == EROARE else INTERVAL_S)

	def in_curs(self):
		return self._lucru is not None and self._lucru.is_alive()

	def pas(self, activ):
		acum = self._ceas()
		rez = self._rezultat
		if rez is not None and not self.in_curs():
			self._rezultat = None
			self._lucru = None
			self.ultima = (acum, rez[0], rez[1])
			_jurnal("stb: %s (%s)" % (rez[0], rez[1]))
			if rez[0] == NOU:
				return NOU
		if not activ or self.in_curs() or not self.e_timpul(acum):
			return None
		self.descarcari += 1
		self._lucru = self._fir(self._lucreaza)
		return None

	def _lucreaza(self):
		try:
			self._rezultat = self._descarca()
		except Exception as e:
			self._rezultat = (EROARE, "%s: %s" % (type(e).__name__, e))


def _fir_daemon(functie, nume="hds-baza-stb"):
	t = threading.Thread(target=functie, name=nume)
	t.daemon = True
	t.start()
	return t


def fir_unire(functie):
	"""Firul unirii (Unire(fir=...), din ceasurile bazei): citirea lamedb-ului si harta cheilor de rezerva."""
	return _fir_daemon(functie, "hds-baza-unire")


# ---------------------------------------------------------------- setarea si textele

def initConfig():
	"""config.usage.hds_baza_stb: "Ia baza de canale de pe stb.hdsatelit.com", oprita din fabrica (o descarcare
	zilnica numai daca o vrea omul). Chemata din Components/UsageConfig.py, ca randul din setup.xml sa o gaseasca."""
	from Components.config import config, ConfigYesNo
	u = config.usage
	if "hds_baza_stb" not in u.content.items:
		u.hds_baza_stb = ConfigYesNo(default=False)
	return u.hds_baza_stb


def stb_activ():
	"""Setarea pornita? Orice citire nereusita inseamna oprita. Se cheama la fiecare tic: modulul setarilor se ia din
	sys.modules (pe receptor e incarcat de la pornire), fara un import care, nereusit, s-ar cauta din nou de fiecare data."""
	try:
		m = sys.modules.get("Components.config")
		return m is not None and m.config.usage.hds_baza_stb.value is True
	except Exception:
		return False


def texte_despre(traducere=None, cale_imagine_=None, cale_stb=CALE_STB):
	"""Randurile pentru "Despre imagine" (si pagina web /informatii/despre, care ia textul ecranului)."""
	tr = traducere or _t
	rez = []
	a = antet(cale_imagine_ or cale_imagine())
	if a:
		rez.append(tr(N_("Baza de canale din imagine: %s (canale: %d)")) % (a["pornire"], a.get("canale", 0)))
	s = antet(cale_stb)
	if s and (not a or cheie_versiune(s) > cheie_versiune(a)):
		rez.append(tr(N_("Baza de canale de pe stb.hdsatelit.com: %s (canale: %d)")) % (s["pornire"], s.get("canale", 0)))
	return rez

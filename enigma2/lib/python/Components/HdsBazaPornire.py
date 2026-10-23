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


class Lamedb(object):
	"""Serviciile din lamedb, citit rand cu rand: cheile (forma cheii bazei) si, pe fiecare cheie de rezerva,
	namespace-ul singurului serviciu (>= 0) sau minus numarul serviciilor (mai multe)."""

	def __init__(self, cale=CALE_LAMEDB):
		self.chei = []
		self.multime = set()
		self.harta = {}
		self.citit = False
		try:
			if os.path.getsize(cale) > MARIME_LAMEDB_MAX:
				_jurnal("lamedb prea mare; fara potrivirea pe cheia de rezerva")
				return
			with io.open(cale, "r", encoding="utf-8", errors="replace") as f:
				self._citeste(f)
			self.citit = True
		except (IOError, OSError):
			pass

	def _citeste(self, f):
		for linie in f:
			if linie.strip() == "services":
				break
		i = 0
		for linie in f:
			s = linie.strip()
			if s == "end":
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


# ---------------------------------------------------------------- unirea pe bucati

class Unire(object):
	"""Unirea bazelor de pornire in baza `b`, pe bucati (vezi antetul modulului). pas() -> True cat mai e de lucru;
	rez = {"imagine": stare, "stb": stare, "rezerve": numarul randurilor mutate}; numere = {sursa: (adaugate,
	schimbate, respinse)}."""

	def __init__(self, b, cale_imagine_=None, cale_stb=CALE_STB, cale_lamedb=CALE_LAMEDB, bucata=BUCATA):
		self.b = b
		self.cai = {"imagine": cale_imagine_ or cale_imagine(), "stb": cale_stb}
		self.cale_lamedb = cale_lamedb
		self.bucata = max(1, int(bucata))
		self.rez = {}
		self.numere = {}
		self.gata = False
		self._ramase = None
		self._curent = None
		self._lamedb = None
		self._rezerve = None

	# -------------------------------------------- pasii

	def pas(self):
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
			return True
		if self._curent is not None:
			self._bucata()
			return True
		if self._ramase:
			self._incepe(self._ramase.pop(0))
			return True
		return self._pas_rezerve()

	def _sfarsit(self):
		self.gata = True
		return False

	def _lamedb_citit(self):
		if self._lamedb is None:
			self._lamedb = Lamedb(self.cale_lamedb)
		return self._lamedb

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
		verificarea sfarsitului si nota in antet."""
		c = self._curent
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
		if bune:
			n = self.b.uneste_linii_pornire(bune)
			for i in range(3):
				c["numere"][i] += n[i]
		if terminat:
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
		pe pas)."""
		lamedb = self._lamedb_citit()
		if self._rezerve is None:
			self._rezerve = {"i": 0, "mutate": 0}
		r = self._rezerve
		chei = lamedb.chei
		b = self.b
		for k in chei[r["i"]:r["i"] + BUCATA_REZERVE]:
			# si cand k are deja rand (de pilda din baza de pornire): randul vechi al receptorului se uneste in el, cu
			# regula obisnuita (ce stie receptorul castiga)
			rez = B.cheie_rezerva(k)
			if rez is None or lamedb.harta.get(rez, -1) < 0:
				continue
			if b.candidat_rezerva(k) is None:
				continue
			b.cauta(k, rezerva=True)
			r["mutate"] += 1
		r["i"] += BUCATA_REZERVE
		if r["i"] < len(chei):
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


def _fir_daemon(functie):
	t = threading.Thread(target=functie, name="hds-baza-stb")
	t.daemon = True
	t.start()
	return t


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

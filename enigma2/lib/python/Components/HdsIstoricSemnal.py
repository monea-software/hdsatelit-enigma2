# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Istoricul semnalului pe pozitii si transpondere: pentru fiecare pozitie de satelit si fiecare transponder, data
primului si a ultimului semnal prins de acest receptor, in cate zile s-a prins si cea mai buna calitate.

Folosit de "Actualizeaza pistele" (Components/HdsPisteCanale.py: intrebarea pentru pozitiile pe care receptorul nu a
prins niciodata semnal), de ecranul motorului (Screens/HdsDishMotor.py: ultimul semnal pe pozitia tinta), de lista
satelitilor si de pagina web (/api/istoric-semnal, HdsWebControl/istoric_semnal_web.py).

FISIERUL: /etc/enigma2/hds_istoric_semnal.json, numai ASCII:
  {"fel": "hds-istoric-semnal", "v": 1, "scris": <secunde>,
   "tp": {"ns:tsid:onid": [prima, ultima, zile, calitate, snr]},
   "poz": {"192": [prima, ultima, zile, calitate, snr]}}
  prima / ultima: secundele primului si ale ultimului semnal; zile: in cate zile calendaristice s-a prins (o data pe
  zi, nu la fiecare schimbare de canal, deci fisierul nu creste cu anii); calitate: cea mai buna, in procente (-1 = nu
  se stie); snr: cel mai bun raport semnal / zgomot, in zecimi de dB (-1 = nu se stie). Cheia transponderului e cea din
  Components/HdsBazaCanale.py ("ns:tsid:onid", hexa, fara zerouri in fata); pozitia e in zecimi de grad (ns >> 16, 192 =
  19,2 grade Est), numai pentru satelit (cablul si terestrul au numai transpondere).
  Marimea: ~45 de octeti pe transponder; plafonul MAX_TP transpondere si MAX_OCTETI (pleaca transponderul cu ultimul
  semnal cel mai vechi).

SCRIEREA (rar, ca stickul si memoria flash sa nu se uzeze): atomic (.nou, fsync, os.replace), pe un fir separat
(instantaneul se ia pe firul apelantului, fara serializare acolo). Prima prindere a unui transponder sau a unei pozitii
se scrie in cel mult SCRIERE_NOU_S (o scanare sau o trecere intreaga = o scriere); restul (ultima zi, zilele, calitatea
mai buna) cel mult o data pe zi calendaristica; la oprirea interfetei si inaintea copiei de siguranta numai ce e
nescris. Un ceas nepus (inainte de 2026) nu noteaza nimic.

CITIREA: o data, la prima folosire. Fisier lipsa = istoric gol; JSON stricat = pus deoparte ca .stricat-AAAALLZZ, apoi
istoric gol; eroare de citire, v mai mare sau fisier prea mare = numai citire (nu se scrie peste).

PARTEA DE SUS E CURATA (fara enigma): se probeaza pe PC (teste/test_istoric_semnal.py). Ascultatorul de pe navigatie
(Urmaritor) primeste evenimentele, ceasul si serviciul din afara."""

from __future__ import absolute_import

import errno
import json
import os
import threading
import time

CALE = "/etc/enigma2/hds_istoric_semnal.json"
FEL = "hds-istoric-semnal"
VERSIUNE = 1
MAX_TP = 20000
MAX_POZ = 3600
MAX_OCTETI = 2 * 1024 * 1024
DATA_MIN = 1767225600            # inceputul anului 2026 (UTC): un ceas mai vechi nu e pus
SCRIERE_NOU_S = 120              # prima prindere: scrisa in cel mult atat
ESECURI_MAX = 3                  # scrieri cazute la rand dupa care istoricul ramane numai in memorie
VERIFICARE_MS = 2000             # dupa evTunedIn, starea tunerului citita o data
POZ_CABLU = 0xFFFF
POZ_TERESTRU = 0xEEEE


def _(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext); pe PC, forma romaneasca (singularul cu litere vine din ro.po)."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		try:
			from HdsPlural import ngettext as plural
		except ImportError:
			plural = None
	if plural is not None:
		try:
			return plural(unu, multe, n)
		except Exception:
			pass
	return unu if n == 1 else multe


def _jurnal(text):
	try:
		print("[HdsIstoricSemnal] %s" % text)
	except Exception:
		pass


# ------------------------------------------------------------------ chei si valori

def cheie_tp(ns, tsid, onid):
	"""-> "ns:tsid:onid" (hexa, litere mici, fara zerouri in fata), ca in baza canalelor."""
	return "%x:%x:%x" % (ns & 0xFFFFFFFF, tsid & 0xFFFF, onid & 0xFFFF)


def pozitie_din_ns(ns):
	"""Namespace-ul DVB -> pozitia de satelit in zecimi (0-3599), sau None (cablu, terestru, altceva)."""
	try:
		p = (int(ns) >> 16) & 0xFFFF
	except (TypeError, ValueError):
		return None
	return p if 0 <= p < 3600 else None


def din_ref(ref):
	"""Referinta de serviciu (text) -> (ns, tsid, onid) sau None (flux, referinta goala sau stricata)."""
	if not ref:
		return None
	parti = str(ref).split(":")
	if len(parti) < 10 or (len(parti) > 10 and parti[10]):
		return None
	try:
		if int(parti[0]) != 1:
			return None
		tsid, onid, ns = int(parti[4], 16), int(parti[5], 16), int(parti[6], 16)
	except ValueError:
		return None
	if not ns and not tsid and not onid:
		return None
	return ns, tsid, onid


def _intreg(v, mic, mare):
	if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
		return None
	v = int(v)
	return v if mic <= v <= mare else None


def curata_intrare(v, acum=None):
	"""O intrare din fisier -> [prima, ultima, zile, calitate, snr] sau None (forma rea, date in afara ferestrei)."""
	if not isinstance(v, list) or len(v) != 5:
		return None
	acum = int(acum if acum is not None else time.time())
	# ceasul inca nepus (pornire fara retea): nicio margine de sus, altfel s-ar lepada tot istoricul
	sus = acum + 86400 if acum >= DATA_MIN else 2 ** 31
	prima, ultima = _intreg(v[0], DATA_MIN, sus), _intreg(v[1], DATA_MIN, sus)
	zile = _intreg(v[2], 1, 10 ** 6)
	cal, snr = _intreg(v[3], -1, 100), _intreg(v[4], -1, 10000)
	if None in (prima, ultima, zile, cal, snr) or ultima < prima:
		return None
	return [prima, ultima, zile, cal, snr]


def _zi(t):
	"""Ziua calendaristica locala a unei clipe (AAAALLZZ, numar)."""
	z = time.localtime(t)
	return z.tm_year * 10000 + z.tm_mon * 100 + z.tm_mday


def calitate_din_stare(d):
	"""Dictionarul getFrontendStatus() -> (prins, calitate %, snr zecimi dB); calitatea si snr -1 cand nu se stiu."""
	if not isinstance(d, dict) or not d:
		return False, -1, -1
	stare = str(d.get("tuner_state") or "").upper()
	if stare:
		prins = stare == "LOCKED"
	else:
		prins = bool(d.get("tuner_locked"))
	cal = d.get("tuner_signal_quality")
	# acelasi procent ca bara de pe televizor si pagina antenei (HdsWebControl/scanare_web.py, procent)
	cal = -1 if _intreg(cal, 0, 65535) is None else max(0, min(100, int(cal) * 100 // 65536))
	snr = d.get("tuner_signal_quality_db")
	# nucleul da sutimi de dB (0x12345678 = nu se stie)
	snr = -1 if _intreg(snr, 0, 100000) is None else int(round(int(snr) / 10.0))
	return prins, cal, min(snr, 10000)


def _uneste(vechi, acum, cal, snr):
	"""Intrarea dupa o prindere noua -> (intrarea, schimbare: None / "nou" / "zi" / "mai_bun")."""
	if vechi is None:
		return [acum, acum, 1, cal, snr], "nou"
	prima, ultima, zile, c0, s0 = vechi
	schimbare = None
	if _zi(acum) != _zi(ultima) and acum > ultima:
		ultima, zile = acum, zile + 1
		schimbare = "zi"
	if acum < prima:
		prima = acum
		schimbare = schimbare or "zi"
	if cal > c0 or snr > s0:
		c0, s0 = max(c0, cal), max(s0, snr)
		schimbare = schimbare or "mai_bun"
	if schimbare is None:
		return vechi, None
	return [prima, ultima, zile, c0, s0], schimbare


# ------------------------------------------------------------------ istoricul

class Istoric(object):
	"""Istoricul in memorie, cu scrierea rara pe disc. ceas: secundele de acum (time.time); fir: functie(lucru) care
	porneste scrierea (implicit un fir nou; in probe, pe loc)."""

	def __init__(self, cale=CALE, ceas=None, fir=None):
		self.cale = cale
		self.ceas = ceas or time.time
		self.fir = fir
		self.tp = {}
		self.poz = {}
		self.numai_citire = False
		self.oprit = False
		self.incarcat = False
		self.versiune = 0            # creste la fiecare schimbare din memorie
		self.versiune_scrisa = 0
		self.nou = False             # o prima prindere nescrisa
		self.zi_scrisa = None        # ziua ultimei scrieri
		self.termen_nou = None       # cand trebuie scrisa prima prindere
		self._lacat = threading.Lock()
		self._lacatCitire = threading.Lock()
		self.scrieri = 0
		self.esecuri = 0             # scrieri cazute la rand (ESECURI_MAX = numai citire)

	# ---- citirea

	def incarca(self):
		"""Citirea fisierului, o singura data (si cand o porneste incarca_in_fundal: cine vine intre timp asteapta)."""
		if self.incarcat:
			return
		with self._lacatCitire:
			if self.incarcat:
				return
			try:
				self._incarca()
			finally:
				self.incarcat = True

	def incarca_in_fundal(self):
		"""La pornire: citirea pe un fir (un istoric mare, de mii de transpondere, cere cateva zecimi de secunda pe
		receptor), ca prima notare de pe firul interfetei sa-l gaseasca gata."""
		if self.incarcat:
			return
		t = threading.Thread(target=self.incarca, name="hds-istoric-semnal-citire")
		t.daemon = True
		t.start()

	def _incarca(self):
		try:
			with open(self.cale, "rb") as f:
				date = f.read(MAX_OCTETI + 1)
		except (IOError, OSError) as e:
			if getattr(e, "errno", None) != errno.ENOENT:
				_jurnal("citire: %s; numai citire" % e)
				self.numai_citire = True
			return
		if len(date) > MAX_OCTETI:
			_jurnal("fisier prea mare; numai citire")
			self.numai_citire = True
			return
		try:
			d = json.loads(date.decode("utf-8"))
		except (ValueError, UnicodeDecodeError, RecursionError):
			self._deoparte()
			return
		if not isinstance(d, dict) or d.get("fel") != FEL:
			self._deoparte()
			return
		v = d.get("v")
		if not isinstance(v, int) or v > VERSIUNE:
			_jurnal("versiune %r; numai citire" % (v,))
			self.numai_citire = True
			return
		acum = self.ceas()
		for nume, tinta, maxim in (("tp", self.tp, MAX_TP), ("poz", self.poz, MAX_POZ)):
			sursa = d.get(nume)
			if not isinstance(sursa, dict):
				continue
			for k, val in sursa.items():
				if len(tinta) >= maxim:
					break
				if not isinstance(k, str) or len(k) > 32:
					continue
				if nume == "poz":
					p = _intreg(int(k) if k.isdigit() else None, 0, 3599)
					if p is None:
						continue
					k = p
				c = curata_intrare(val, acum)
				if c is not None:
					tinta[k] = c
		scris = d.get("scris")
		if _intreg(scris, DATA_MIN, int(acum) + 86400) is not None:
			self.zi_scrisa = _zi(scris)

	def _deoparte(self):
		"""JSON stricat: pus deoparte (legatura tare, fisierul ramane pe loc pana la prima scriere), istoric gol."""
		tinta = "%s.stricat-%s" % (self.cale, time.strftime("%Y%m%d"))
		try:
			if not os.path.exists(tinta):
				os.link(self.cale, tinta)
			_jurnal("fisier stricat, pus deoparte: %s" % tinta)
		except OSError as e:
			_jurnal("fisier stricat, nu s-a putut pune deoparte (%s); numai citire" % e)
			self.numai_citire = True

	# ---- notarea

	def noteaza(self, ns, tsid, onid, calitate=-1, snr=-1, acum=None):
		"""Un semnal prins pe transponder. -> True daca s-a schimbat ceva in memorie. Nu arunca."""
		try:
			self.incarca()
			acum = int(self.ceas() if acum is None else acum)
			if acum < DATA_MIN:
				return False
			cal = _intreg(calitate, -1, 100)
			cal = -1 if cal is None else cal
			s = _intreg(snr, -1, 10000)
			s = -1 if s is None else s
			k = cheie_tp(ns, tsid, onid)
			schimbat = False
			for tinta, cheie, maxim in ((self.tp, k, MAX_TP), (self.poz, pozitie_din_ns(ns), MAX_POZ)):
				if cheie is None:
					continue
				vechi = tinta.get(cheie)
				if vechi is None and len(tinta) >= maxim:
					self._scoateCelMaiVechi(tinta)
				nou, schimbare = _uneste(vechi, acum, cal, s)
				if schimbare is None:
					continue
				tinta[cheie] = nou
				schimbat = True
				if schimbare == "nou":
					self.nou = True
			if schimbat:
				self.versiune += 1
				if self.nou and self.termen_nou is None:
					self.termen_nou = acum + SCRIERE_NOU_S
			return schimbat
		except Exception as e:
			_jurnal("noteaza: %s" % e)
			return False

	def noteaza_ref(self, ref, calitate=-1, snr=-1, acum=None):
		t = din_ref(ref)
		if t is None:
			return False
		return self.noteaza(t[0], t[1], t[2], calitate, snr, acum)

	@staticmethod
	def _scoateCelMaiVechi(tinta):
		k = min(tinta, key=lambda c: tinta[c][1])
		del tinta[k]

	# ---- scrierea

	def murdar(self):
		return self.versiune != self.versiune_scrisa

	def trebuie_scris(self, acum=None):
		"""Prima prindere dupa SCRIERE_NOU_S; restul numai intr-o alta zi decat ultima scriere."""
		if not self.murdar() or self.numai_citire or self.oprit:
			return False
		acum = self.ceas() if acum is None else acum
		if self.nou and self.termen_nou is not None and acum >= self.termen_nou:
			return True
		return not self.nou and self.zi_scrisa != _zi(acum)

	def poate(self, acum=None):
		"""Chemat dupa fiecare notare si la ceasul urmaritorului: scrie numai cand trebuie. -> True daca a pornit."""
		if self.trebuie_scris(acum):
			return self.salveaza()
		return False

	def salveaza(self, sincron=False):
		"""Scrierea ce e nescris (oprirea interfetei, copia, sau poate()). -> True daca a pornit (sau s-a facut)."""
		if not self.murdar() or self.numai_citire or self.oprit:
			return False
		acum = int(self.ceas())
		d = {"fel": FEL, "v": VERSIUNE, "scris": acum, "tp": dict(self.tp),
			"poz": dict((str(p), v) for p, v in self.poz.items())}
		versiune = self.versiune
		self.nou = False
		self.termen_nou = None
		self.zi_scrisa = _zi(acum)
		self.versiune_scrisa = versiune

		def lucru():
			if self._scrie(d):
				self.esecuri = 0
				return
			self.esecuri += 1
			if self.esecuri >= ESECURI_MAX:
				# disc plin sau numai citire: nicio incercare la fiecare zap; istoricul ramane in memorie pana la repornire
				self.numai_citire = True
				_jurnal("%d scrieri cazute la rand; numai citire pana la repornirea interfetei" % self.esecuri)
			elif self.versiune_scrisa == versiune:
				# ramane de scris la urmatorul prilej, nimic pierdut pe tacute
				self.versiune_scrisa = -1
				self.zi_scrisa = None
		if sincron:
			lucru()
		elif self.fir is not None:
			self.fir(lucru)
		else:
			t = threading.Thread(target=lucru, name="hds-istoric-semnal")
			t.daemon = True
			t.start()
		return True

	def _scrie(self, d):
		nou = self.cale + ".nou"
		with self._lacat:
			try:
				date = json.dumps(d, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
				if len(date) > MAX_OCTETI:
					date = self._taie(d)
				with open(nou, "wb") as f:
					f.write(date)
					f.flush()
					os.fsync(f.fileno())
				os.replace(nou, self.cale)
				self.scrieri += 1
				return True
			except Exception as e:
				_jurnal("scriere: %s" % e)
				try:
					os.remove(nou)
				except OSError:
					pass
				return False

	@staticmethod
	def _taie(d):
		"""Peste MAX_OCTETI: pleaca transponderele cu ultimul semnal cel mai vechi, pana incape."""
		tp = d["tp"]
		chei = sorted(tp, key=lambda k: tp[k][1])
		while chei:
			chei = chei[len(chei) // 10 + 1:]
			d2 = dict(d, tp=dict((k, tp[k]) for k in chei))
			date = json.dumps(d2, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
			if len(date) <= MAX_OCTETI:
				return date
		return json.dumps(dict(d, tp={}), ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")

	def opreste_scrierile(self):
		"""Inaintea resetarii din fabrica si a flash-ului: nicio scriere pana la repornirea interfetei."""
		self.oprit = True

	def uita(self):
		"""Istoricul sters (din pagina web, de exemplu dupa mutarea setarilor pe alt receptor). -> True."""
		self.incarca()
		if self.numai_citire:
			return False
		self.tp, self.poz = {}, {}
		self.versiune += 1
		self.salveaza()
		return True

	# ---- intrebarile

	def stiut(self):
		"""Istoricul are cel putin o pozitie de satelit (altfel nu se poate spune ca o pozitie n-a prins niciodata)."""
		self.incarca()
		return bool(self.poz)

	def pozitie(self, poz):
		self.incarca()
		return self.poz.get(poz)

	def transponder(self, ns, tsid, onid):
		self.incarca()
		return self.tp.get(cheie_tp(ns, tsid, onid))

	def prinsa(self, poz):
		"""True = pozitia a avut semnal pe acest receptor; False = niciodata (si istoricul stie alte pozitii); None =
		nu se stie (istoric gol, sau nu e pozitie de satelit)."""
		if not isinstance(poz, int) or not 0 <= poz < 3600:
			return None
		self.incarca()
		if not self.poz:
			return None
		return poz in self.poz

	def transpondere_pe_pozitie(self, poz):
		self.incarca()
		return sorted((k, v) for k, v in self.tp.items() if pozitie_din_ns(int(k.split(":")[0], 16)) == poz)

	def rezumat(self):
		"""Pentru pagina web: pozitiile, de la est la vest, cu numarul transponderelor prinse."""
		self.incarca()
		pe_poz = {}
		for k in self.tp:
			try:
				p = pozitie_din_ns(int(k.split(":")[0], 16))
			except ValueError:
				p = None
			if p is not None:
				pe_poz[p] = pe_poz.get(p, 0) + 1
		rez = []
		for p in sorted(self.poz, key=lambda x: -(x if x <= 1800 else x - 3600)):
			prima, ultima, zile, cal, snr = self.poz[p]
			rez.append({"pozitie": p, "pozitie_text": text_pozitie(p), "prima": prima, "ultima": ultima, "zile": zile,
				"calitate": cal, "snr": snr, "transpondere": pe_poz.get(p, 0), "text": text_istoric(self.poz[p]),
				"transpondere_text": text_transpondere(pe_poz.get(p, 0))})
		return rez


# ------------------------------------------------------------------ textele

def text_pozitie(poz):
	try:
		from Components import HdsIndexCanale as X
	except ImportError:
		try:
			import HdsIndexCanale as X
		except ImportError:
			X = None
	if X is not None:
		try:
			return X.text_pozitie(poz)
		except Exception:
			pass
	if not isinstance(poz, int):
		return u""
	return u"%.1f%s" % ((poz if poz <= 1800 else 3600 - poz) / 10.0, u"E" if poz <= 1800 else u"W")


def text_data(t):
	return time.strftime("%d.%m.%Y", time.localtime(t))


def text_istoric(intrare):
	"""Intrarea unei pozitii sau a unui transponder -> textul scurt pentru om."""
	if intrare is None:
		return _("Niciun semnal prins până acum pe acest receptor")
	prima, ultima, zile, cal, snr = intrare
	text = _("Ultimul semnal: %s") % text_data(ultima) + u" · " + (_("prins într-o zi") if zile == 1 else
		ngettext("prins în %d zi", "prins în %d zile", zile) % zile)
	if cal >= 0:
		text += u" · " + _("calitatea cea mai bună %d %%") % cal
	return text


def text_transpondere(n):
	"""Cate transpondere prinse are o pozitie: "un transponder", "12 transpondere" (pluralul din traducere)."""
	return ngettext("%d transponder", "%d transpondere", n) % n


def text_neprinse(pozitii):
	"""Intrebarea dinaintea lui "Actualizeaza pistele" cand unele pozitii n-au prins niciodata semnal."""
	n = len(pozitii)
	lista = u", ".join(text_pozitie(p) for p in pozitii[:8]) + (u", …" if n > 8 else u"")
	return (_("Acest receptor nu a prins niciodată semnal pe o poziție: %s.") % lista if n == 1 else
		ngettext("Acest receptor nu a prins niciodată semnal pe %d poziție: %s.",
			"Acest receptor nu a prins niciodată semnal pe %d poziții: %s.", n) % (n, lista))


# ------------------------------------------------------------------ istoricul receptorului

_ISTORIC = {"i": None}


def istoric():
	if _ISTORIC["i"] is None:
		_ISTORIC["i"] = Istoric()
	return _ISTORIC["i"]


def la_oprire():
	"""Oprirea interfetei: ce e nescris, pe loc."""
	i = _ISTORIC["i"]
	return i.salveaza(sincron=True) if i is not None else False


def inainte_de_copie():
	i = _ISTORIC["i"]
	return i.salveaza(sincron=True) if i is not None else False


def opreste_scrierile():
	istoric().opreste_scrierile()


class Urmaritor(object):
	"""Ascultatorul de pe navigatie: la evTunedIn, dupa VERIFICARE_MS, starea tunerului citita o data; semnal prins =
	notat. Fara nicio citire la fiecare secunda; o exceptie nu scapa niciodata spre C++."""

	def __init__(self, nav, ist=None, fabrica_ceas=None, evenimente=None, pe_nav=True):
		if evenimente is None:
			from enigma import iPlayableService as evenimente
		if fabrica_ceas is None:
			from enigma import eTimer as fabrica_ceas
		self.nav = nav
		self.ev = evenimente
		self.ist = ist if ist is not None else istoric()
		self.ceas = fabrica_ceas()
		self.ceas.callback.append(self._verifica)
		# prima prindere se scrie la SCRIERE_NOU_S chiar daca nu mai urmeaza niciun zap
		self.ceasScriere = fabrica_ceas()
		self.ceasScriere.callback.append(self._scrie)
		# pe_nav=False: evenimentele vin de la culegere (Components/HdsCulegereCanale.Culegere._eveniment), ca pe
		# navigatie sa ramana un singur ascultator
		self.pe_nav = pe_nav
		if pe_nav:
			self.nav.event.append(self._eveniment)

	def eveniment(self, ev):
		self._eveniment(ev)

	def _eveniment(self, ev):
		try:
			if ev == getattr(self.ev, "evTunedIn", None):
				self.ceas.start(VERIFICARE_MS, True)
			elif ev == getattr(self.ev, "evEnd", None) or ev == getattr(self.ev, "evTuneFailed", None):
				self.ceas.stop()
		except Exception as e:
			_jurnal("eveniment: %s" % e)

	def _verifica(self):
		try:
			ref = self.nav.getCurrentlyPlayingServiceReference()
			service = self.nav.getCurrentService()
			fe = service.frontendInfo() if service is not None else None
			d = fe.getFrontendStatus() if fe is not None else None
			prins, cal, snr = calitate_din_stare(d)
			if prins and ref is not None:
				self.ist.noteaza_ref(ref.toString(), cal, snr)
			if not self.ist.poate() and self.ist.termen_nou is not None:
				ramas = max(1.0, self.ist.termen_nou - self.ist.ceas())
				self.ceasScriere.start(int(ramas * 1000) + 500, True)
		except Exception as e:
			_jurnal("verificare: %s" % e)

	def _scrie(self):
		try:
			self.ist.poate()
		except Exception as e:
			_jurnal("scriere: %s" % e)

	def opreste(self):
		self.ceas.stop()
		self.ceasScriere.stop()
		if self.pe_nav:
			try:
				self.nav.event.remove(self._eveniment)
			except ValueError:
				pass


_URMARITOR = {"u": None}


def porneste(nav, pe_nav=True):
	"""O singura data (din Components/HdsCulegereCanale.porneste, cu pe_nav=False: evenimentele le da culegerea).
	Nu arunca."""
	if _URMARITOR["u"] is None:
		try:
			_URMARITOR["u"] = Urmaritor(nav, pe_nav=pe_nav)
			istoric().incarca_in_fundal()
		except Exception as e:
			_jurnal("pornire: %s" % e)
	return _URMARITOR["u"]

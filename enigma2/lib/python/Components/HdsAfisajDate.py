# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAfisajDate.py: ce poate arata afisajul din fata (Components/HdsAfisaj.py): grupele, datele, formatele fiecarei
# date, de unde se citeste fiecare pe receptor, cat costa citirea si desenul ei pe cele 4 cifre.
#
# O data are un id stabil „grupa.nume”, o eticheta (tradusa la afisare), costul citirii, perioada de reimprospatare
# (cat timp afisajul chiar o arata; 0 = numai cand alegerea ajunge pe afisaj) si formatele ei. O alegere e
# „grupa.nume:format” (de ex. „ceas.ora:24”); ecranul, pagina web si afisajul folosesc aceleasi id-uri.
#
# Costul unei citiri (pe receptor, ARM A53, Python de 10-20 de ori mai incet decat pe PC):
#   GRATIS     in memorie: ceasul, o setare, o valoare tinuta de alt modul
#   PROC       o citire mica din /proc sau /sys (sub 1 ms)
#   TUNER      starea tunerului (I2C, cateva ms), prin HdsCommon.frontend_status (tinuta minte 0,5 s)
#   GHID       evenimentul din ghid (EIT, in memorie)
#   FIR        disc: citeste() intoarce un Lucru, pe care afisajul il da firului lui (niciodata pe firul enigma2)
#   EVENIMENT  informatiile serviciului, schimbate la zap; tinute minte in Context pana la zap sau la evUpdatedInfo
#
# citeste(ctx) intoarce valoarea sau None (nimic de aratat acum: afisajul sare alegerea). Formatul face din valoare
# ce se deseneaza, ca pereche (fel, continut):
#   ("fix", text)       aliniat la stanga, taiat la 4 pozitii
#   ("dreapta", text)   aliniat la dreapta (numere)
#   ("derulat", text)   derulat cand nu incape
#   ("punct", text)     numar cu punct zecimal (punctul numai pe pozitiile 1-2); altfel fara punct, la dreapta
#   ("bara", fractie)   bara de nivel, 0..1
#   ("inel", None)      segmentul care inconjoara afisajul
#   ("sageti", "est" | "vest")  sageata care trece peste afisaj in directia data
#   ("alternat", [texte])       pe rand, cate ALTERNAT_MS
#   ("secventa", [(fel, continut, ms), ...])  bucatile una dupa alta (ms 0 = cat tine derularea)
# deseneaza() face din pereche cadrele de masti (Components/HdsAfisajLitere.py) si duratele lor.
#
# Nicio functie publica nu arunca: o citire cazuta da None. Fisierul nu importa nimic din enigma2 la incarcare.

import bisect
import os
import struct
import time

try:
	from Components import HdsAfisajLitere as L
except ImportError:     # probele de pe PC incarca modulul singur
	import HdsAfisajLitere as L

GRATIS = "gratis"
PROC = "proc"
TUNER = "tuner"
GHID = "ghid"
FIR = "fir"
EVENIMENT = "eveniment"

# duratele desenelor, in milisecunde
PRIMUL_CADRU_MS = 1500      # inceputul unui text derulat sta mai mult, ca sa fie prins
ULTIMUL_CADRU_MS = 1000
ALTERNAT_MS = 2000
VITEZA_IMPLICITA_MS = 300

CAPETE_TEMPERATURA = (30.0, 95.0)       # capetele barei de temperatura, in °C
VITEZA_BARA_MBIT = 100.0
GB_PE_ORA = 4.0                         # o ora de inregistrare HD, cam atat
MAX_FILME_NUMARATE = 20000


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la afisare."""
	return text


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsAfisajDate] %s" % text)


# ---------------------------------------------------------------- catalogul

GRUPE = [
	("ceas", N_("Ora și data")),
	("receptor", N_("Receptorul")),
	("stocare", N_("Discul și memoria USB")),
	("retea", N_("Rețeaua")),
	("canal", N_("Canalul")),
	("semnal", N_("Transponderul și semnalul")),
	("imagine", N_("Imaginea")),
	("sunet", N_("Sunetul și subtitrările")),
	("emisiune", N_("Emisiunea")),
	("radio", N_("Radio")),
	("inregistrari", N_("Înregistrări și programări")),
	("redare", N_("Filme și redare")),
	("acces", N_("Accesul condiționat")),
	("texte", N_("Texte, semne și animații")),
	("evenimente", N_("Mesaje scurte")),
	("asteptare", N_("În așteptare")),
]

GRUPA_EVENIMENTE = "evenimente"
GRUPA_ASTEPTARE = "asteptare"


class Format(object):
	__slots__ = ("id", "eticheta", "fa")

	def __init__(self, id_, eticheta, fa):
		self.id = id_
		self.eticheta = eticheta
		self.fa = fa


class Data(object):
	__slots__ = ("id", "grupa", "eticheta", "cost", "perioada", "formate", "nota", "citeste", "exemplu")

	def __init__(self, id_, eticheta, cost, perioada, citeste, exemplu, formate, nota=""):
		self.id = id_
		self.grupa = id_.split(".")[0]
		self.eticheta = eticheta
		self.cost = cost
		self.perioada = perioada
		self.citeste = citeste
		self.exemplu = exemplu
		self.formate = [Format(f[0], f[1], f[2]) for f in formate]
		self.nota = nota

	def format(self, id_format):
		for f in self.formate:
			if f.id == id_format:
				return f
		return None


class Lucru(object):
	"""O citire de facut pe firul afisajului (disc): `functie` nu atinge nimic din enigma2; `transforma` face din
	rezultat valoarea (pe firul enigma2). `cheie` spune ce se citeste: doua date cu aceeasi cheie impart citirea."""
	__slots__ = ("cheie", "functie", "transforma")

	def __init__(self, cheie, functie, transforma=None):
		self.cheie = cheie
		self.functie = functie
		self.transforma = transforma or (lambda x: x)


# ---------------------------------------------------------------- contextul citirilor

def curatNume(text):
	"""Un nume de serviciu sau de emisiune fara semnele de evidentiere DVB (0x80-0x9F) si fara spatii la capete."""
	if text is None:
		return u""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	return u"".join(c for c in u"%s" % text if not (u"\x80" <= c <= u"\x9f")).strip()


class Context(object):
	"""Ce au nevoie citirile: sesiunea, serviciul redat si informatiile lui, tinute minte pana la urmatorul zap sau
	pana la urmatoarea schimbare a informatiilor (laZap, laInfo). Numarul canalului il pune afisajul (numararea trece
	prin buchet, deci se face numai cand trebuie)."""

	def __init__(self, session=None, ceas=None):
		self.session = session
		self.ceas = ceas or time.time
		self.numar = None           # numarul canalului redat
		self.cate = None            # cate canale are buchetul listei
		self.numarAflat = False
		self._memo = {}
		self.stariProc = {}         # starea citirilor care fac diferente (procesorul, reteaua)

	def acum(self):
		return self.ceas()

	def laZap(self):
		self._memo.clear()
		self.numar = None
		self.cate = None
		self.numarAflat = False

	def laInfo(self):
		self._memo.clear()

	def _m(self, cheie, f):
		if cheie in self._memo:
			return self._memo[cheie]
		try:
			v = f()
		except Exception as e:
			_jurnal("%s: %r" % (cheie, e))
			v = None
		self._memo[cheie] = v
		return v

	def serviciu(self):
		nav = getattr(self.session, "nav", None)
		if nav is None:
			return None
		try:
			return nav.getCurrentService()
		except Exception:
			return None

	def ref(self):
		def f():
			nav = getattr(self.session, "nav", None)
			citeste = getattr(nav, "getCurrentlyPlayingServiceOrGroup", None) or getattr(nav,
				"getCurrentlyPlayingServiceReference", None)
			return citeste() if citeste is not None else None
		return self._m("ref", f)

	def info(self):
		def f():
			s = self.serviciu()
			return s.info() if s is not None else None
		return self._m("info", f)

	def getInfo(self, nume):
		"""iServiceInformation.<nume> ca numar; None cand lipseste sau nu se stie (-1, -2)."""
		def f():
			from enigma import iServiceInformation
			i = self.info()
			c = getattr(iServiceInformation, nume, None)
			if i is None or c is None:
				return None
			v = i.getInfo(c)
			return None if v is None or v < 0 else int(v)
		return self._m("i." + nume, f)

	def getInfoString(self, nume):
		def f():
			from enigma import iServiceInformation
			i = self.info()
			c = getattr(iServiceInformation, nume, None)
			if i is None or c is None:
				return u""
			return curatNume(i.getInfoString(c))
		return self._m("s." + nume, f)

	def numeServiciu(self):
		def f():
			ref = self.ref()
			if ref is None:
				return u""
			from ServiceReference import ServiceReference
			return curatNume(ServiceReference(ref).getServiceName())
		return self._m("nume", f)

	def caleServiciu(self):
		def f():
			ref = self.ref()
			return (ref.getPath() or "") if ref is not None else ""
		return self._m("cale", f) or ""

	def tp(self):
		"""Datele transponderului (dict) sau {}."""
		def f():
			from enigma import iServiceInformation
			d = None
			i = self.info()
			c = getattr(iServiceInformation, "sTransponderData", None)
			if i is not None and c is not None:
				try:
					d = i.getInfoObject(c)
				except Exception:
					d = None
			if not isinstance(d, dict) or not d:
				d = None
				s = self.serviciu()
				fe = s.frontendInfo() if s is not None else None
				if fe:
					for nume in ("getTransponderData", "getAll"):
						try:
							d = getattr(fe, nume)(True)
						except Exception:
							d = None
						if isinstance(d, dict) and d:
							break
			return d if isinstance(d, dict) else {}
		return self._m("tp", f) or {}

	def fe(self):
		"""Starea tunerului {'power','quality','ber','lock','number'} (HdsCommon, tinuta minte 0,5 s)."""
		try:
			from Components.Converter import HdsCommon as C
			ref = self.ref()
			return C.frontend_status(self.serviciu(), ref.toString() if ref is not None else "") or {}
		except Exception as e:
			_jurnal("tunerul: %r" % (e,))
			return {}

	def feDict(self):
		"""Starea completa a tunerului (getFrontendStatus), pentru raportul semnal/zgomot."""
		try:
			s = self.serviciu()
			fe = s.frontendInfo() if s is not None else None
			d = fe.getFrontendStatus() if fe else None
			return d if isinstance(d, dict) else {}
		except Exception:
			return {}

	def eveniment(self, i):
		def f():
			info = self.info()
			return info.getEvent(i) if info is not None else None
		return self._m("ev%d" % i, f)

	def radio(self):
		"""Serviciul redat e un post de radio (tipul din referinta: 2, 10) sau DAB."""
		def f():
			ref = self.ref()
			if ref is None:
				return False
			parti = ref.toString().split(":")
			tip = int(parti[2], 16) if len(parti) > 2 and parti[2] else 0
			return tip in (2, 10) or "dab" in (ref.getPath() or "").lower()
		return bool(self._m("radio", f))

	def fisier(self):
		"""Se reda un fisier (film, inregistrare), nu un canal."""
		return self.caleServiciu().startswith("/")

	def seek(self):
		s = self.serviciu()
		try:
			return s.seek() if s is not None else None
		except Exception:
			return None

	def infobar(self):
		try:
			from Screens.InfoBar import InfoBar
			return InfoBar.instance
		except Exception:
			return None


# ---------------------------------------------------------------- textele de timp

def _hm(t):
	return "%02d%02d" % (t.tm_hour, t.tm_min)


def _ora12(t):
	return "%d%02d" % (t.tm_hour % 12 or 12, t.tm_min)


ZILE = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"), N_("Sunday"))
ZILE_SCURT = (N_("Mon"), N_("Tue"), N_("Wed"), N_("Thu"), N_("Fri"), N_("Sat"), N_("Sun"))
LUNI = (N_("ianuarie"), N_("februarie"), N_("martie"), N_("aprilie"), N_("mai"), N_("iunie"), N_("iulie"),
	N_("august"), N_("septembrie"), N_("octombrie"), N_("noiembrie"), N_("decembrie"))


def _ziua(t, scurt=False):
	return _((ZILE_SCURT if scurt else ZILE)[t.tm_wday])


def _luna(t):
	return _(LUNI[t.tm_mon - 1])


def _minute(secunde):
	"""Minutele intregi dintr-un numar de secunde (in jos), niciodata negative."""
	return max(0, int(secunde) // 60)


def _hMin(secunde):
	"""„1H05” (ore si minute), „36H” de la 10 ore, zile („45d”) de la 1000 de ore."""
	h, m = divmod(_minute(secunde), 60)
	if h < 10:
		return ("fix", "%dH%02d" % (h, m))
	if h < 1000:
		return ("dreapta", "%dH" % h)
	return ("dreapta", "%dd" % (h // 24))


def _minSec(secunde):
	m, s = divmod(max(0, int(secunde)), 60)
	return ("fix", "%02d%02d" % (m % 100, s))


def _minus(minute):
	return ("dreapta", "-%d" % minute if minute < 1000 else "-%dH" % min(99, minute // 60))


def _txtOra(ts):
	return _hm(time.localtime(ts))


# ---------------------------------------------------------------- citirile: ceasul

def _ceas(ctx):
	return time.localtime(ctx.acum())


def _utc(ctx):
	return time.gmtime(ctx.acum())


def _oprire(ctx):
	"""Minutele pana la oprirea programata (SleepTimer), None cand nu e pusa."""
	nav = getattr(ctx.session, "nav", None)
	st = getattr(nav, "SleepTimer", None)
	if st is None or not st.isActive():
		return None
	lista = getattr(st, "timer_list", None) or []
	if not lista:
		return None
	return _minute(max(0, lista[0].begin - ctx.acum()) + 59)


# ---------------------------------------------------------------- ora din alt oras (fusurile din /usr/share/zoneinfo)

ZONEINFO = "/usr/share/zoneinfo"
MAX_TZIF = 256 * 1024
_FUSURI = {}


def _desparteDecalaj(text, i):
	"""[+-]hh[:mm[:ss]] de la pozitia i -> (secunde, pozitia de dupa) sau (None, i)."""
	semn = 1
	if i < len(text) and text[i] in "+-":
		semn = -1 if text[i] == "-" else 1
		i += 1
	parti, curent = [], ""
	while i < len(text) and (text[i].isdigit() or text[i] == ":"):
		if text[i] == ":":
			parti.append(curent)
			curent = ""
		else:
			curent += text[i]
		i += 1
	parti.append(curent)
	if not parti[0]:
		return None, i
	try:
		v = [int(p or 0) for p in parti[:3]] + [0, 0]
	except ValueError:
		return None, i
	return semn * (v[0] * 3600 + v[1] * 60 + v[2]), i


def _numeFus(text, i):
	if i < len(text) and text[i] == "<":
		j = text.find(">", i)
		return len(text) if j < 0 else j + 1
	while i < len(text) and text[i].isalpha():
		i += 1
	return i


def regulaPosix(text):
	"""Regula din coada unui fisier TZif („EET-2EEST,M3.5.0/3,M10.5.0/4”) -> (decalajul iernii, al verii, inceputul,
	sfarsitul) in secunde fata de UTC; fara ora de vara: (decalaj, None, None, None). Inceputul si sfarsitul:
	(luna, saptamana, ziua, ora locala in secunde), numai forma „M”. None pentru o regula necunoscuta."""
	try:
		i = _numeFus(text, 0)
		dec, i = _desparteDecalaj(text, i)
		if dec is None:
			return None
		iarna = -dec                      # in POSIX decalajul are semnul intors
		if i >= len(text):
			return (iarna, None, None, None)
		j = _numeFus(text, i)
		if j == i:
			return None
		i = j
		vara = iarna + 3600
		if i < len(text) and text[i] != ",":
			d2, i = _desparteDecalaj(text, i)
			if d2 is not None:
				vara = -d2
		if i >= len(text) or text[i] != ",":
			return (iarna, None, None, None)
		schimbari = []
		for bucata in text[i + 1:].split(",")[:2]:
			ziua, _sep, ora = bucata.partition("/")
			if not ziua.startswith("M"):
				return (iarna, None, None, None)
			luna, sapt, zi = [int(x) for x in ziua[1:].split(".")]
			secunde = _desparteDecalaj(ora, 0)[0] if ora else 7200
			schimbari.append((luna, sapt, zi, 7200 if secunde is None else secunde))
		if len(schimbari) != 2:
			return (iarna, None, None, None)
		return (iarna, vara, schimbari[0], schimbari[1])
	except (ValueError, IndexError):
		return None


def _ziuaRegulii(an, luna, sapt, zi):
	"""Ziua lunii pentru „a `sapt`-a zi `zi` (0 = duminica) din luna”; saptamana 5 = ultima."""
	import calendar
	prima = (calendar.weekday(an, luna, 1) + 1) % 7    # 0 = duminica
	d = 1 + (zi - prima) % 7 + (sapt - 1) * 7
	zile = calendar.monthrange(an, luna)[1]
	while d > zile:
		d -= 7
	return d


def _decalajRegula(regula, t):
	iarna, vara, inceput, sfarsit = regula
	if vara is None:
		return iarna
	import calendar
	an = time.gmtime(t + iarna).tm_year

	def moment(r, decalaj):
		luna, sapt, zi, secunde = r
		return calendar.timegm((an, luna, _ziuaRegulii(an, luna, sapt, zi), 0, 0, 0, 0, 0, 0)) + secunde - decalaj
	a, b = moment(inceput, iarna), moment(sfarsit, vara)
	if a < b:
		return vara if a <= t < b else iarna
	return iarna if b <= t < a else vara           # emisfera sudica: vara trece peste anul nou


def citesteTzif(date):
	"""Octetii unui fisier TZif -> (tranzitiile, tipul dupa fiecare, decalajele tipurilor, primul tip de iarna,
	regula din coada) sau None."""
	if len(date) < 44 or date[:4] != b"TZif":
		return None
	versiune = date[4:5]

	def antet(o):
		return struct.unpack(">6l", date[o + 20:o + 44])
	isut, isstd, salturi, n, tipuri, caractere = antet(0)
	o = 44
	lung_v1 = n * 5 + tipuri * 6 + caractere + salturi * 8 + isstd + isut
	marime, salt = 4, 8
	if versiune >= b"2" and len(date) >= 44 + lung_v1 + 44 and date[44 + lung_v1:48 + lung_v1] == b"TZif":
		o = 44 + lung_v1
		isut, isstd, salturi, n, tipuri, caractere = antet(o)
		o += 44
		marime, salt = 8, 12
	tranzitii = list(struct.unpack(">%d%s" % (n, "q" if marime == 8 else "l"), date[o:o + n * marime]))
	o += n * marime
	indici = list(bytearray(date[o:o + n]))
	o += n
	decalaje, iarna = [], None
	for k in range(tipuri):
		dec, vara, _ab = struct.unpack(">lBB", date[o:o + 6])
		o += 6
		decalaje.append(dec)
		if iarna is None and not vara:
			iarna = k
	o += caractere + salturi * salt + isstd + isut
	regula = None
	if marime == 8:
		coada = date[o:].split(b"\n")
		if len(coada) >= 2 and coada[1]:
			regula = regulaPosix(coada[1].decode("ascii", "replace"))
	if not decalaje or any(i >= len(decalaje) for i in indici):
		return None
	return tranzitii, indici, decalaje, (iarna if iarna is not None else 0), regula


def decalajFus(fus, t, citeste=None):
	"""Secundele fata de UTC ale fusului `fus` (de ex. „Asia/Tokyo”) la momentul t, sau None. Fisierul se citeste o
	singura data."""
	if not fus or ".." in fus or fus.startswith("/"):
		return None
	if fus not in _FUSURI:
		try:
			if citeste is not None:
				date = citeste(fus)
			else:
				with open(os.path.join(ZONEINFO, fus), "rb") as f:
					date = f.read(MAX_TZIF)
			_FUSURI[fus] = citesteTzif(date)
		except (IOError, OSError, struct.error, ValueError) as e:
			_jurnal("fusul %s: %r" % (fus, e))
			_FUSURI[fus] = None
	z = _FUSURI[fus]
	if z is None:
		return None
	tranzitii, indici, decalaje, iarna, regula = z
	if not tranzitii or t < tranzitii[0]:
		return decalaje[iarna] if regula is None or tranzitii else _decalajRegula(regula, t)
	if t >= tranzitii[-1] and regula is not None:
		return _decalajRegula(regula, t)
	return decalaje[indici[bisect.bisect_right(tranzitii, t) - 1]]


def fusurile():
	"""[(fus, numele)] din lista imaginii (Components/Timezones.py, /etc/timezone.xml), fiecare fus o data."""
	try:
		from Components.Timezones import timezones
		lista = timezones.timezones
	except Exception:
		return []
	rez, vazute = [], set()
	for nume, fus in lista:
		if fus and fus not in vazute and fus != "UTC":
			vazute.add(fus)
			rez.append((fus, nume))
	return rez


def orasDinNume(nume):
	"""„(GMT+09:00) Osaka, Sapporo, Tokyo” -> „Osaka, Sapporo, Tokyo”; „(GMT-10:00) French Polynesia: Tahiti” ->
	„Tahiti”."""
	t = (nume or u"").split(u")", 1)[-1].strip()
	return t.split(u": ")[-1].strip() or t


def _fusAles():
	try:
		from Components.config import config
		return config.hds_afisaj.oras.value or ""
	except Exception:
		return ""


def _altFus(ctx):
	fus = _fusAles()
	if not fus:
		return None
	acum = ctx.acum()
	dec = decalajFus(fus, acum)
	if dec is None:
		return None
	nume = dict(fusurile()).get(fus) or fus.split("/")[-1].replace("_", " ")
	return {"ora": time.gmtime(acum + dec), "oras": orasDinNume(nume)}


# ---------------------------------------------------------------- minutarul si cronometrul (in memorie, fara disc)

_CEASURI = {"minutar_pana": None, "cronometru_de_la": None, "cronometru_s": 0.0}
MINUTAR_ZERO_S = 60          # dupa ce ajunge la zero, minutarul clipeste atat, apoi dispare


def pornesteMinutar(minute, acum=None):
	"""Minutarul numara invers de la `minute` (0 = oprit)."""
	acum = time.time() if acum is None else acum
	_CEASURI["minutar_pana"] = (acum + 60 * int(minute)) if int(minute) > 0 else None


def cronometru(ce, acum=None):
	"""„porneste”, „opreste” sau „zero”."""
	acum = time.time() if acum is None else acum
	if ce == "porneste" and _CEASURI["cronometru_de_la"] is None:
		_CEASURI["cronometru_de_la"] = acum
	elif ce == "opreste" and _CEASURI["cronometru_de_la"] is not None:
		_CEASURI["cronometru_s"] += max(0.0, acum - _CEASURI["cronometru_de_la"])
		_CEASURI["cronometru_de_la"] = None
	elif ce == "zero":
		_CEASURI["cronometru_s"] = 0.0
		if _CEASURI["cronometru_de_la"] is not None:
			_CEASURI["cronometru_de_la"] = acum


def minutarRamas(acum):
	"""Secundele ramase (0 cat clipeste la sfarsit), sau None cand minutarul e oprit."""
	pana = _CEASURI["minutar_pana"]
	if pana is None:
		return None
	if acum >= pana + MINUTAR_ZERO_S:
		_CEASURI["minutar_pana"] = None
		return None
	return max(0, int(pana - acum + 0.999))


def cronometruScurs(acum):
	"""(secundele, merge) sau None cand cronometrul e la zero si oprit."""
	s = _CEASURI["cronometru_s"]
	merge = _CEASURI["cronometru_de_la"] is not None
	if merge:
		s += max(0.0, acum - _CEASURI["cronometru_de_la"])
	if not merge and s <= 0:
		return None
	return int(s), merge


def _minutar(ctx):
	return minutarRamas(ctx.acum())


def _cronometru(ctx):
	v = cronometruScurs(ctx.acum())
	return v[0] if v is not None else None


# ---------------------------------------------------------------- ora sigura (Components/HdsCeas.py)

# codurile din HdsCeas.stareOra: NECUNOSCUTA, SALVATA, PROVIZORIE, SIGURA_INTERNET, SIGURA_TRANSPONDERE, SIGURA_RTC
SURSE_ORA = {2: "PROV", 3: "NTP", 4: "SAT", 5: "RTC"}


def _sincronizat(ctx):
	try:
		from Components import HdsCeas as H
		cod = H.stareOra(H._handler())
	except Exception:
		return None
	return cod if cod is not None and cod >= 0 else None


# ---------------------------------------------------------------- citirile: receptorul

def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def _citesteMic_direct(cale, maxim=4096):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def _citesteMic(cale, maxim=4096):
	"""Ca _citesteMic_direct; fisierele driverului (/proc/msp, /proc/hisi) le citeste pe firul de fundal."""
	return _procFundal(_citesteMic_direct, cale, maxim)


def _procesor():
	try:
		from Components import HdsProcesor
		return HdsProcesor
	except Exception:
		return None


def _temperatura(ctx):
	"""Temperatura tinuta de paza procesorului (citita oricum la 5 s); fara paza, o citire din pm_cpu."""
	P = _procesor()
	if P is None:
		return None
	t = getattr(P.procesor(), "temperatura", None)
	if t is None:
		try:
			t = P.citesteTemperatura()[0]
		except Exception:
			t = None
	try:
		return int(round(float(t))) if t is not None else None
	except (TypeError, ValueError):
		return None


def _pmCpu():
	P = _procesor()
	if P is None:
		return {}
	try:
		return P.citestePmCpu() or {}
	except Exception:
		return {}


def _frecventa(ctx):
	try:
		khz = int(_pmCpu().get("frecventa_khz") or 0)
	except (TypeError, ValueError):
		return None
	return khz // 1000 if khz > 0 else None


def _tensiune(ctx):
	try:
		mv = int(_pmCpu().get("tensiune_mv") or 0)
	except (TypeError, ValueError):
		return None
	return mv if mv > 0 else None


MODURI_SCURT = {"automat": "AUTO", "normal": "NOR", "racoros": "RAC", "performanta": "PERF"}


def _modProcesor(ctx):
	try:
		from Components.config import config
		return MODURI_SCURT.get(config.hds_procesor.mod.value)
	except Exception:
		return None


def _incarcare(ctx):
	"""Procentul folosit al procesorului intre doua citiri ale /proc/stat; prima citire nu are inca diferenta."""
	text = _citesteMic("/proc/stat", 512)
	if not text:
		return None
	rand = text.split("\n", 1)[0].split()
	if len(rand) < 5 or rand[0] != "cpu":
		return None
	try:
		valori = [int(x) for x in rand[1:]]
	except ValueError:
		return None
	total = sum(valori)
	liber = valori[3] + (valori[4] if len(valori) > 4 else 0)
	inainte = ctx.stariProc.get("stat")
	ctx.stariProc["stat"] = (total, liber)
	if inainte is None or total <= inainte[0]:
		return None
	return max(0, min(100, int(round(100.0 * (1.0 - float(liber - inainte[1]) / (total - inainte[0]))))))


def _incarcareMedie(ctx):
	text = _citesteMic("/proc/loadavg", 128)
	try:
		return float(text.split()[0])
	except (AttributeError, IndexError, ValueError):
		return None


def _memorie(ctx):
	text = _citesteMic("/proc/meminfo", 2048)
	if not text:
		return None
	d = {}
	for rand in text.splitlines():
		parti = rand.split()
		if len(parti) >= 2 and parti[0] in ("MemTotal:", "MemAvailable:", "MemFree:"):
			try:
				d[parti[0][:-1]] = int(parti[1])
			except ValueError:
				pass
	total = d.get("MemTotal")
	liber = d.get("MemAvailable", d.get("MemFree"))
	if not total or liber is None:
		return None
	return {"liber_mb": liber // 1024, "folosit": 1.0 - float(liber) / total}


def _pornitDe(ctx):
	text = _citesteMic("/proc/uptime", 128)
	try:
		return float(text.split()[0])
	except (AttributeError, IndexError, ValueError):
		return None


_VERSIUNE = [None]


def _versiune(ctx):
	"""Cifrele versiunii care ruleaza (din jurnalul versiunilor, dupa build), citite o singura data."""
	if _VERSIUNE[0] is None:
		try:
			from Components import HdsJurnalVersiuni as J
			v = (J.versiunea_care_ruleaza() or {}).get("versiune") or ""
		except Exception:
			v = ""
		_VERSIUNE[0] = tuple(p for p in v.split(".") if p.isdigit())
	return _VERSIUNE[0] or None


def _numeReceptor(ctx):
	return (_citesteMic("/etc/hostname", 256) or "").strip() or None


def _caldura(ctx):
	P = _procesor()
	if P is None:
		return None
	return True if getattr(P.procesor(), "in_caldura", False) else None


# ---------------------------------------------------------------- citirile: discul

def _locInregistrari():
	try:
		from Components.config import config
		return config.usage.default_path.value or "/media/hdd/movie/"
	except Exception:
		return "/media/hdd/movie/"


def _statvfs(cale):
	st = os.statvfs(cale)
	return (st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize)


def _spatiu(r):
	total, liber = r
	if total <= 0:
		return None
	return {"liber_gb": liber / 1e9, "folosit": 1.0 - float(liber) / total}


def _discLiber(ctx):
	cale = _locInregistrari()
	return Lucru("statvfs:" + cale, lambda: _statvfs(cale), _spatiu)


def _numarFilme(cale):
	n = 0
	for i, nume in enumerate(os.listdir(cale)):
		if i >= MAX_FILME_NUMARATE:
			break
		if nume.endswith(".ts"):
			n += 1
	return n


def _inregistrari(ctx):
	cale = _locInregistrari()
	return Lucru("filme:" + cale, lambda: _numarFilme(cale))


def _usb(ctx):
	"""Un dispozitiv legat din mers (memorie USB) e montat."""
	try:
		from Components.Harddisk import harddiskmanager
		return True if harddiskmanager.getMountedPartitions(True) else None
	except Exception:
		return None


# ---------------------------------------------------------------- citirile: reteaua

def _adaptor():
	try:
		from Components.Network import iNetwork
		for nume in iNetwork.getAdapterList():
			if iNetwork.getAdapterAttribute(nume, "up"):
				return iNetwork, nume
	except Exception:
		pass
	return None, None


def _ip(ctx):
	retea, nume = _adaptor()
	if retea is None:
		return None
	ip = retea.getAdapterAttribute(nume, "ip")
	if not ip or len(ip) != 4 or not any(ip):
		return None
	return [int(x) for x in ip]


def _legatura(ctx):
	retea, nume = _adaptor()
	if retea is None:
		return None
	return "WIFI" if nume.startswith(("wlan", "wl", "ra")) else "LAN"


def _internet(ctx):
	"""HdsStareRetea: raspunsul tinut minte; proba (pe firul ei) porneste cel mult o data pe minut."""
	try:
		from Components import HdsStareRetea
		return HdsStareRetea.internet()
	except Exception:
		return None


def _vitezaRetea(ctx):
	"""Mbit/s primiti pe toate placile (fara lo), din diferenta octetilor intre doua citiri ale /proc/net/dev."""
	text = _citesteMic("/proc/net/dev", 8192)
	if not text:
		return None
	total = 0
	for rand in text.splitlines()[2:]:
		nume, _sep, rest = rand.partition(":")
		if nume.strip() in ("", "lo"):
			continue
		try:
			total += int(rest.split()[0])
		except (IndexError, ValueError):
			pass
	acum = ctx.acum()
	inainte = ctx.stariProc.get("net")
	ctx.stariProc["net"] = (acum, total)
	if inainte is None or acum - inainte[0] < 0.5 or total < inainte[1]:
		return None
	return (total - inainte[1]) * 8.0 / 1e6 / (acum - inainte[0])


def _wifi(ctx):
	text = _citesteMic("/proc/net/wireless", 2048)
	if not text:
		return None
	for rand in text.splitlines()[2:]:
		parti = rand.split()
		if len(parti) >= 3:
			try:
				calitate = float(parti[2].rstrip("."))
			except ValueError:
				continue
			return max(0, min(100, int(round(calitate * 100.0 / 70.0))))
	return None


def _clienti(ctx):
	try:
		from enigma import eStreamServer
		return len(eStreamServer.getInstance().getConnectedClients())
	except Exception:
		return None


# ---------------------------------------------------------------- citirile: canalul

def _numarCanal(ctx):
	return ctx.numar


def _numeCanal(ctx):
	return ctx.numeServiciu() or None


def _numarNume(ctx):
	nume = ctx.numeServiciu()
	if ctx.numar is None:
		return nume or None
	return (u"%d %s" % (ctx.numar, nume)).strip()


def _furnizor(ctx):
	return ctx.getInfoString("sProvider") or None


def _lista(ctx):
	ib = ctx.infobar()
	sl = getattr(ib, "servicelist", None) if ib is not None else None
	if sl is None:
		return None
	try:
		from ServiceReference import ServiceReference
		return curatNume(ServiceReference(sl.getRoot()).getServiceName()) or None
	except Exception:
		return None


def _cate(ctx):
	return ctx.cate


def _felCanal(ctx):
	cale = ctx.caleServiciu()
	# posturile DAB+ / DVB-T2 din satelit vin tot prin http (releele locale), dar nu sunt IPTV: DAB, iar un program
	# DVB-T2 e TV sau RAD, ca un canal de satelit
	try:
		from Components.HdsCapLista import fel_flux
		fel = fel_flux(cale)
	except ImportError:
		fel = None
	if fel == "dab":
		return "DAB"
	if fel == "t2":
		return "RAD" if ctx.radio() else "TV"
	if "://" in cale:
		return "IPTV"
	if "dab" in cale.lower():
		return "DAB"
	if ctx.fisier() or ctx.ref() is None:
		return None
	return "RAD" if ctx.radio() else "TV"


def _calitate(ctx):
	h = ctx.getInfo("sVideoHeight")
	if not h:
		return None
	if h >= 2160:
		return "UHD"
	if h >= 1080:
		return "FHD"
	if h >= 720:
		return "HD"
	return "SD"


def _codat(ctx):
	v = ctx.getInfo("sIsCrypted")
	if v is None:
		return None
	return "COD" if v else "LIB"


def _info(nume):
	def f(ctx):
		return ctx.getInfo(nume) or None
	return f


# ---------------------------------------------------------------- citirile: transponderul si semnalul

def _C():
	from Components.Converter import HdsCommon
	return HdsCommon


def _tpFel(ctx):
	tp = ctx.tp()
	if not tp:
		return None, ""
	return tp, _C().tp_kind(tp)


def _frecventaTp(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None:
		return None
	C = _C()
	mhz = C.to_mhz(tp.get("frequency"))
	if mhz is None:
		return None
	return {"mhz": int(round(mhz)), "pol": C.SAT_POL.get(C.ival(tp, "polarization"), u"") if fel == "s" else u""}


def _polarizare(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None or fel != "s":
		return None
	return _C().SAT_POL.get(_C().ival(tp, "polarization")) or None


def _rata(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None:
		return None
	return _C().symbol_rate(tp) or None


def _fec(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None:
		return None
	t = _C().fec_text(tp, fel)
	return t if t and t[0].isdigit() else None


def _sistem(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None:
		return None
	C = _C()
	if fel == "s":
		return "S2" if C.sat_system(tp) == u"DVB-S2" else "S"
	if fel == "t":
		return "T2" if C.ter_is_t2(tp) else "T"
	if fel == "c":
		return "C"
	return None


MODULATII_SCURT = {u"QPSK": "QPSK", u"8PSK": "8PSK", u"16APSK": "16AP", u"32APSK": "32AP", u"QAM16": "Q16",
	u"QAM32": "Q32", u"QAM64": "Q64", u"QAM128": "Q128", u"QAM256": "Q256"}


def _modulatie(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None:
		return None
	return MODULATII_SCURT.get(_C().modulation_text(tp, fel))


def _pozitieOrbitala(ctx):
	tp, fel = _tpFel(ctx)
	if tp is None or fel != "s":
		return None
	pos = _C().ival(tp, "orbital_position")
	return pos if 0 <= pos <= 3600 else None


def textPozitie(zecimi):
	"""Pozitia in zecimi de grad: 192 -> „192E”, 3592 -> „08W” (fara punct: pe pozitia a treia nu se aprinde)."""
	if zecimi > 1800:
		return "%02dW" % (3600 - zecimi)
	return "%02dE" % zecimi


def _numeSatelit(ctx):
	pos = _pozitieOrbitala(ctx)
	if pos is None:
		return None
	try:
		return curatNume(_C().sat_name(pos)) or None
	except Exception:
		return None


def _banda(ctx):
	v = _frecventaTp(ctx)
	if v is None or not v["pol"]:
		return None
	return "HI" if v["mhz"] >= 11700 else "LO"


def _tuner(ctx):
	n = ctx.fe().get("number")
	if n is None or not 0 <= n <= 25:
		return None
	return chr(65 + n)


def _procentTuner(cheie):
	def f(ctx):
		try:
			return _C().percent16(ctx.fe().get(cheie))
		except Exception:
			return None
	return f


def _snr(ctx):
	try:
		v = int(ctx.feDict().get("tuner_signal_quality_db"))
	except (TypeError, ValueError):
		return None
	if v < 0 or v >= 0x12345:
		return None
	return v / 100.0


def _ber(ctx):
	v = ctx.fe().get("ber")
	return v if v is not None and v >= 0 else None


def _faraSemnal(ctx):
	if ctx.fisier():
		return None
	fe = ctx.fe()
	return True if fe and fe.get("lock") == 0 else None


def stareMotor():
	"""Antena cu motor: {'misca', 'directie', 'grade'} din Components/HdsMotorStare.py (o intrebare in nucleu), sau None
	cand nu se misca si nici n-a ajuns de curand. `grade`: pozitia estimata cat merge, tinta la sosire (est pozitiv)."""
	try:
		from Components import HdsMotorStare as M
		s = M.stareMotor()
	except Exception:
		return None
	if not s or not s.get("activ"):
		return None
	misca = bool(s.get("se_misca")) and not s.get("a_ajuns")
	grade = s.get("pozitie_grade")
	if not misca and s.get("la_grade") is not None:
		grade = s.get("la_grade")
	return {"misca": misca, "directie": s.get("directie") or "", "grade": grade}


def _motor(ctx):
	s = stareMotor()
	if s is None or not s["misca"]:
		return None
	return {"directie": s["directie"], "grade": s["grade"]}


# ---------------------------------------------------------------- citirile: imaginea si sunetul

def _cadre(ctx):
	v = ctx.getInfo("sFrameRate")
	if not v:
		return None
	return {"fps": int(round(v / 1000.0)), "progresiv": ctx.getInfo("sProgressive")}


CODEC_VIDEO = {0: "MPG2", 1: "H264", 3: "VC1", 4: "MPG4", 5: "VC1", 6: "MPG1", 7: "H265", 8: "VP8", 9: "VP9",
	16: "AVS", 40: "AVS2"}


def _codecVideo(ctx):
	v = ctx.getInfo("sVideoType")
	return CODEC_VIDEO.get(v) if v is not None else None


def _aspect(ctx):
	v = ctx.getInfo("sAspect")
	if v is None:
		return None
	C = _C()
	if v in C.ASPECT_WIDE:
		return "16-9"
	if v in C.ASPECT_43:
		return "4-3"
	return None


GAMMA_SCURT = {0: "SDR", 1: "HDR", 2: "HDR", 3: "HLG"}


def _hdr(ctx):
	v = ctx.getInfo("sGamma")
	return GAMMA_SCURT.get(v) if v is not None else None


def _iesire(ctx):
	"""Modul trimis la televizor (/proc/stb/video/videomode, de ex. „1080p50”, „2160p60”) -> {'linii', 'hz'}."""
	text = (_citesteMic("/proc/stb/video/videomode", 64) or "").strip().lower()
	if not text:
		return None
	linii, sep, hz = "", "", ""
	for i, c in enumerate(text):
		if c.isdigit():
			linii += c
		else:
			sep = c
			hz = "".join(x for x in text[i + 1:] if x.isdigit())
			break
	if sep not in ("p", "i") and not text.startswith("4k"):
		return None
	if text.startswith("4k"):
		linii = "2160"
	return {"linii": int(linii) if linii else None, "hz": int(hz) if hz else None}


def _volumControl():
	from enigma import eDVBVolumecontrol
	return eDVBVolumecontrol.getInstance()


def _volum(ctx):
	try:
		v = _volumControl()
		return 0 if v.isMuted() else int(v.getVolume())
	except Exception:
		return None


def _mut(ctx):
	try:
		return True if _volumControl().isMuted() else None
	except Exception:
		return None


def _pista(ctx):
	"""(indicele pistei alese, cate piste, descrierea, limba) sau None."""
	def f():
		s = ctx.serviciu()
		at = s.audioTracks() if s is not None else None
		if not at:
			return None
		n = at.getNumberOfTracks()
		if not n:
			return None
		i = at.getCurrentTrack()
		info = at.getTrackInfo(i)
		return (i, n, curatNume(info.getDescription()), curatNume(info.getLanguage()))
	return ctx._m("pista", f)


def _codecSunet(ctx):
	p = _pista(ctx)
	if p is None:
		return None
	try:
		t = _C().audio_codec(p[2])
	except Exception:
		t = p[2]
	t = (t or u"").replace("-", "").replace("+", "").replace(" ", "").upper()
	return t[:4] or None


def _canaleSunet(ctx):
	p = _pista(ctx)
	if p is None:
		return None
	for c in ("7.1", "5.1", "2.0", "1.0"):
		if c in p[2]:
			return c
	return None


def _limbaSunet(ctx):
	p = _pista(ctx)
	if p is None or not p[3]:
		return None
	return p[3][:3]


def _pistaDin(ctx):
	p = _pista(ctx)
	if p is None or p[1] < 2:
		return None
	return "%d/%d" % (p[0] + 1, p[1])


def _subtitrare(ctx):
	"""Subtitrarile pornite: {'limba'} (limba pistei, cand o are), sau None."""
	ib = ctx.infobar()
	s = getattr(ib, "selected_subtitle", None) if ib is not None else None
	if not s:
		return None
	limba = u""
	# subtitrarea din InfoBar: (felul, pid, pagina, magazia, limba); limba e al cincilea camp, codul ISO 639
	if isinstance(s, (tuple, list)) and len(s) > 4 and isinstance(s[4], str):
		limba = curatNume(s[4])
	return {"limba": limba}


def _teletext(ctx):
	return True if ctx.getInfo("sTXTPID") else None


# ---------------------------------------------------------------- citirile: emisiunea

def _ev(ctx, i=0):
	e = ctx.eveniment(i)
	if e is None:
		return None
	try:
		inceput = e.getBeginTime()
		durata = e.getDuration()
		titlu = curatNume(e.getEventName())
		descriere = curatNume(e.getShortDescription())
	except Exception:
		return None
	if not inceput or not durata:
		return None
	return {"titlu": titlu, "inceput": inceput, "durata": durata, "descriere": descriere}


def _emisiune(ctx):
	return _ev(ctx, 0)


def _urmatoarea(ctx):
	return _ev(ctx, 1)


def _emisiuneAcum(ctx):
	v = _ev(ctx, 0)
	if v is None:
		return None
	v["acum"] = ctx.acum()
	return v


def _varsta(ctx):
	e = ctx.eveniment(0)
	if e is None:
		return None
	try:
		d = e.getParentalData()
		r = d.getRating() if d else 0
	except Exception:
		return None
	return r + 3 if 0 < r < 0x10 else None


# ---------------------------------------------------------------- citirile: radio

def _post(ctx):
	return (ctx.numeServiciu() or None) if ctx.radio() else None


def despartePiesa(text):
	"""Piesa din RT+ asa cum o da nucleul, „titlu (artist)” (lib/dvb/radiotext.cpp) -> (titlu, artist); fara artist
	(text, "")."""
	t = (text or u"").strip()
	if t.endswith(u")") and u" (" in t:
		i = t.rfind(u" (")
		return t[:i].strip(), t[i + 2:-1].strip()
	return t, u""


def _rds(fel):
	def f(ctx):
		if not ctx.radio():
			return None
		try:
			from Components import HdsRdsText as R
			s = ctx.serviciu()
			decodor = s.rdsDecoder() if s is not None else None
			text = R.text_decodor(decodor, R.TEXT if fel == "text" else R.PIESA)
		except Exception:
			return None
		if not text or fel == "text":
			return text or None
		titlu, artist = despartePiesa(text)
		if fel == "artist":
			return artist or None
		if fel == "artist_piesa":
			return (u"%s - %s" % (artist, titlu)) if artist and titlu else (titlu or None)
		return titlu or None
	return f


def _dab(ctx):
	"""Datele postului DAB+ ascultat (ansamblul, kbit/s), din /tmp/hdsatelit/receptie.json scris de HdsDab
	(HdsCommon.receptie: cel mult un os.stat la 2 s, fisierul in RAM), sau None pentru alt serviciu."""
	ref = ctx.ref()
	if ref is None or "/dab/" not in ctx.caleServiciu().replace("%3A", "%3a"):
		return None
	try:
		C = _C()
		return C.rj_dict(C.receptie(ref.toString()), "dab") or None
	except Exception:
		return None


def _ansamblu(ctx):
	return curatNume((_dab(ctx) or {}).get("ansamblu")) or None


# ---------------------------------------------------------------- citirile: inregistrarile

def _rt(ctx):
	return getattr(getattr(ctx.session, "nav", None), "RecordTimer", None)


def _rec(ctx):
	nav = getattr(ctx.session, "nav", None)
	try:
		n = len(nav.getRecordings()) if nav is not None else 0
	except Exception:
		n = 0
	return n if n > 0 else None


def _timereCareMerg(ctx):
	rt = _rt(ctx)
	if rt is None:
		return []
	try:
		return [t for t in rt.timer_list if t.state == t.StateRunning and not getattr(t, "justplay", False)]
	except Exception:
		return []


def _durataRec(ctx):
	t = _timereCareMerg(ctx)
	if not t:
		return None
	return max(0, ctx.acum() - min(x.begin for x in t))


def _numeRec(ctx):
	t = _timereCareMerg(ctx)
	if not t:
		return None
	return curatNume(getattr(t[0], "name", "")) or None


def _urmatoareaInregistrare(ctx):
	"""{'inceput', 'nume', 'acum'} pentru urmatoarea inregistrare programata, sau None."""
	rt = _rt(ctx)
	if rt is None:
		return None
	acum = ctx.acum()
	try:
		viitoare = [t for t in rt.timer_list if t.begin > acum and not getattr(t, "disabled", False)
			and not getattr(t, "justplay", False)]
	except Exception:
		return None
	if not viitoare:
		return None
	t = min(viitoare, key=lambda x: x.begin)
	return {"inceput": t.begin, "nume": curatNume(getattr(t, "name", "")), "acum": acum}


def _programari(ctx):
	rt = _rt(ctx)
	if rt is None:
		return None
	try:
		return len([t for t in rt.timer_list if not getattr(t, "disabled", False)])
	except Exception:
		return None


def _timeshift(ctx):
	"""Pauza in direct merge: {'urma'} = cate secunde e imaginea in urma emisiei (None cand nu se afla), sau None."""
	ib = ctx.infobar()
	if ib is None or not getattr(ib, "timeshift_enabled", 0):
		return None
	urma = None
	s = ctx.seek()
	try:
		lung, poz = s.getLength(), s.getPlayPosition()
		if not lung[0] and not poz[0] and lung[1] >= poz[1]:
			urma = (lung[1] - poz[1]) / 90000.0
	except Exception:
		urma = None
	return {"urma": urma}


# ---------------------------------------------------------------- citirile: redarea

def _redare(ctx):
	"""{'poz', 'lung'} in secunde pentru un fisier redat, sau None."""
	if not ctx.fisier():
		return None
	s = ctx.seek()
	if s is None:
		return None
	try:
		lung = s.getLength()
		poz = s.getPlayPosition()
	except Exception:
		return None
	if not lung or lung[0] or not poz or poz[0] or lung[1] <= 0:
		return None
	return {"poz": poz[1] / 90000.0, "lung": lung[1] / 90000.0}


def _stareRedare(ctx):
	if not ctx.fisier():
		return None
	ib = ctx.infobar()
	st = getattr(ib, "seekstate", None) if ib is not None else None
	try:
		pauza, ff = st[0], st[1]
	except (IndexError, TypeError):
		return "PLAY"
	if pauza:
		return "PAUS"
	if ff > 1:
		return ">>%d" % ff if ff < 100 else ">>"
	if ff < 0:
		return "<<%d" % -ff if -ff < 100 else "<<"
	return "PLAY"


def _numeFilm(ctx):
	return (ctx.numeServiciu() or None) if ctx.fisier() else None


# ---------------------------------------------------------------- citirile: accesul conditionat

def _ecm(ctx):
	"""Randurile ECM ale modulului de acces (HdsEcm: numai numere, fara nume sau adrese), citite cel mult o data pe
	secunda."""
	try:
		from Components import HdsEcm
		d = HdsEcm.stare(acum=ctx.acum())
	except Exception:
		return None
	if not d or not d.get("caid"):
		return None
	return d


def _numeSistem(ctx):
	d = _ecm(ctx)
	if d is None:
		return None
	try:
		return curatNume(_C().caid_name(d["caid"])) or None
	except Exception:
		return None


# ---------------------------------------------------------------- citirile: debitul, HDMI, sunetul radio, genul, CI

def _flux():
	try:
		from Components import HdsAnalizaFlux
		return HdsAnalizaFlux
	except Exception:
		return None


def _demuxServiciu(ctx):
	"""Demultiplexorul serviciului redat (getStreamingData), 0 cand nu se afla."""
	def f():
		s = ctx.serviciu()
		st = s.stream() if s is not None else None
		d = st.getStreamingData() if st is not None else None
		n = d.get("demux") if isinstance(d, dict) else None
		return n if isinstance(n, int) and 0 <= n < 16 else 0
	v = ctx._m("demux", f)
	return v if v is not None else 0


def _debitFrecventa(ctx):
	"""Mbit/s ai intregii frecvente: pachetele portului tunerului (/proc/hisi/msp/demux_main si demux_port, numai
	HiSilicon, doua citiri mici din /proc), intre doua citiri; prima nu are inca diferenta."""
	if ctx.fisier():
		return None
	F = _flux()
	if F is None:
		return None
	m = F.port_din_main(_citesteMic(F.HISI_MAIN, 2048), _demuxServiciu(ctx))
	if m is None:
		return None
	p = F.pachete_din_port(_citesteMic(F.HISI_PORT, 8192), m[0])
	if p is None:
		return None
	acum = ctx.acum()
	inainte = ctx.stariProc.get("debit")
	ctx.stariProc["debit"] = (acum, p[0], m[0])
	if inainte is None or inainte[2] != m[0] or acum - inainte[0] < 0.5:
		return None
	return F.diferenta32(inainte[1], p[0]) * 188.0 * 8.0 / 1e6 / (acum - inainte[0])


def _debitVideo(ctx):
	"""Mbit/s ai pistei video din analiza fluxului (Components/HdsAnalizaFlux.py), numai cand s-a facut una pentru
	canalul acesta (la cerere, din mesajul de ecran negru sau din web); altfel None."""
	ref = ctx.ref()
	F = _flux()
	if ref is None or F is None:
		return None
	try:
		rez = (F.stare(ref.toString()) or {}).get("rezultat") or {}
	except Exception:
		return None
	for p in rez.get("piste") or []:
		if F.STREAM_TYPES.get(p.get("stream_type"), ("", ""))[1] == "video" and p.get("debit"):
			return p["debit"] / 1e6
	return None


HDMI0 = "/proc/msp/hdmi0"


def _hdmi(ctx):
	"""Televizorul legat (HotPlug) si protectia HDCP pornita, din starea driverului HDMI (Components/HdsHdmiDate.py)."""
	try:
		from Components import HdsHdmiDate as H
	except Exception:
		return None
	t = _citesteMic(HDMI0, 16384)
	if not t:
		return None
	try:
		p = H.Perechi(t)
		return {"legat": H._da(p.val("HotPlug", "HWStatus")), "hdcp": H._da(p.val("HDCPAuthStatus", "SWStatus"))}
	except Exception:
		return None


def _analizaRadio(ctx):
	"""Datele sunetului postului de radio (ecranul radio, Screens/HdsEcranRadio.py: analiza()), sau None."""
	ib = ctx.infobar()
	leg = getattr(ib, "hdsRadio", None) if ib is not None else None
	fn = getattr(leg, "analiza", None)
	try:
		d = fn() if fn is not None else None
	except Exception:
		return None
	return d if isinstance(d, dict) else None


def _esantionare(ctx):
	d = _analizaRadio(ctx)
	try:
		hz = int(d.get("esantionare") or 0) if d else 0
	except (TypeError, ValueError):
		return None
	return hz if hz > 0 else None


def _debitSunet(ctx):
	"""kbit/s: masurat de analizorul ecranului radio cand merge, altfel cel anuntat de postul DAB+."""
	d = _analizaRadio(ctx) or {}
	try:
		v = int(d.get("debit_masurat") or d.get("debit") or 0)
		if not v:
			v = int((_dab(ctx) or {}).get("kbit") or 0)
	except (TypeError, ValueError):
		return None
	return v if 0 < v < 10000 else None


def _gen(ctx):
	"""Genul emisiunii (primul nivel din descriptorul DVB, cu numele din HdsCommon), sau None."""
	e = ctx.eveniment(0)
	if e is None:
		return None
	try:
		C = _C()
		return C.genre_text(C._genre_level1(e)) or None
	except Exception:
		return None


def _ci(ctx):
	"""Un modul CI gata intr-un slot: numele lui (dat de modul), sau None (API-ul CI al enigma2, prin HdsCommon)."""
	try:
		C = _C()
		n = C.cam_slots()
		ui = C._ci_ui()
		if n <= 0 or ui is None:
			return None
		for slot in range(n):
			if C._ci_state(ui, slot) == 2:
				return curatNume(C.ci_module_name(slot)) or u"CI"
	except Exception:
		return None
	return None


# ---------------------------------------------------------------- citirile: textele

def _textTau(ctx):
	try:
		from Components.config import config
		return config.hds_afisaj.text.value or None
	except Exception:
		return None


def _mereu(ctx):
	return True


# ---------------------------------------------------------------- formatele

def _txt(fel, sablon="%s"):
	def f(v):
		return (fel, sablon % (v,))
	return f


def _numar(fel="dreapta"):
	def f(v):
		return (fel, "%d" % v)
	return f


def _bara(minim=0.0, maxim=100.0):
	def f(v):
		return ("bara", (float(v) - minim) / (maxim - minim))
	return f


def _procent(v):
	return ("fix", "%d%%" % v if v < 100 else "100")


def _cuPunct(v, zecimale=1, sufix=""):
	"""Un numar cu punct („0.45”, „1.6G”) daca punctul cade pe pozitiile 1-2 si totul incape; altfel intreg, la
	dreapta."""
	for z in range(zecimale, 0, -1):
		t = ("%." + str(z) + "f") % v + sufix
		if L.potrivitCuPunct(t) is not None:
			return ("punct", t)
	return ("dreapta", "%d%s" % (int(round(v)), sufix))


def _dataDerulat(t):
	return ("derulat", u"%s %d %s %d" % (_ziua(t), t.tm_mday, _luna(t), t.tm_year))


def _ziuaCuData(t):
	return ("fix", u"%s%02d" % (L.transcrie(_ziua(t, True))[:2], t.tm_mday))


def _scurt3(text):
	return ("fix", L.transcrie(text)[:3])


def _tempGC(v):
	return ("fix", u"%d°C" % v if v < 100 else u"%d°" % v)


def _mbit(v):
	return ("dreapta", "%d" % min(9999, int(round(v))))


def _liberGB(v):
	gb = v["liber_gb"]
	if gb < 1000:
		return ("dreapta", "%dG" % int(gb))
	return _cuPunct(gb / 1000.0, 1, "T")


def _frecventaDerulat(v):
	return ("derulat", ("%d %s" % (v["mhz"], v["pol"])).strip())


def _frecventaMhz(v):
	return ("dreapta", "%d" % v["mhz"]) if v["mhz"] < 10000 else None


def _pornitZile(s):
	return ("fix", "%d d" % (int(s) // 86400))


def _pornitDerulat(s):
	s = int(s)
	return ("derulat", "%dd %02dH %02dm" % (s // 86400, (s % 86400) // 3600, (s % 3600) // 60))


def _ipDerulat(v):
	return ("derulat", " ".join("%d" % x for x in v))


def _hex(v):
	return ("fix", "%04X" % (v & 0xFFFF))


def _motorGrade(v):
	g = v.get("grade")
	if g is None:
		return ("fix", "ROT")
	zecimi = int(round(abs(g) * 10))
	return ("fix", textPozitie(zecimi) if g >= 0 else "%02dW" % zecimi)


def _motorMesaj(fel):
	"""Mesajul antenei: cat merge, sagetile (sau pozitia, sau inelul); la sosire, pozitia (sau nimic)."""
	def f(v):
		if v.get("misca"):
			if fel in ("sageti", "sageti_grade"):
				return ("sageti", "vest" if v.get("directie") == "vest" else "est")
			if fel == "inel":
				return ("inel", None)
			return _motorGrade(v) if v.get("grade") is not None else None
		if fel in ("grade", "sageti_grade") and v.get("grade") is not None:
			return _motorGrade(v)
		return None
	return f


def _cadrePI(v):
	return ("fix", "%d%s" % (v["fps"], "P" if v.get("progresiv") else "I"))


def _emisiuneRamas(fel):
	def f(v):
		m = _minute(max(0, v["inceput"] + v["durata"] - v["acum"]) + 59)
		return _minus(m) if fel == "minus" else ("dreapta", "%d" % m)
	return f


def _emisiuneProcent(fel):
	def f(v):
		p = max(0.0, min(1.0, float(v["acum"] - v["inceput"]) / v["durata"]))
		return ("bara", p) if fel == "bara" else _procent(int(round(p * 100)))
	return f


def _redareProcent(fel):
	def f(v):
		p = max(0.0, min(1.0, v["poz"] / v["lung"]))
		return ("bara", p) if fel == "bara" else _procent(int(round(p * 100)))
	return f


def _ecmMs(v):
	ms = v.get("ms")
	return ("dreapta", "%d" % ms) if ms is not None and 0 <= ms < 10000 else None


def _ecmE(v):
	ms = v.get("ms")
	return ("fix", "E%d" % ms) if ms is not None and 0 <= ms < 1000 else None


def _ecmLoc(v):
	if "local" not in v:
		return None
	return ("fix", "LOC" if v["local"] else "NET")


def _cifreTastate(v):
	return ("fix", (u"%s" % v + u"____")[:4])


def _zapNumarNume(v):
	numar, nume = v
	parti = []
	if numar is not None:
		parti.append(("dreapta", "%d" % numar, 2000))
	if nume:
		parti.append(("derulat", nume, 0))
	return ("secventa", parti) if parti else None


def _alternatOraData(t):
	return ("alternat", [_hm(t), "%02d%02d" % (t.tm_mday, t.tm_mon)])


def _recAlternat(v):
	return ("alternat", ["REC", _txtOra(v["inceput"])])


def _fixText(text):
	def f(v):
		return ("fix", text)
	return f


def _ora12ap(t):
	return ("alternat", ["%2d%02d" % (t.tm_hour % 12 or 12, t.tm_min), "AM" if t.tm_hour < 12 else "PM"])


def _minutarMs(s):
	if s <= 0:
		return ("alternat", ["0000", ""])        # la zero clipeste
	return _hMin(s) if s >= 6000 else _minSec(s)


def _cronometruMs(s):
	return _hMin(s) if s >= 6000 else _minSec(s)


def _debitMbit(v):
	return _cuPunct(v, 1) if v < 100 else _mbit(v)


def _khz(hz):
	if hz % 1000:
		return _cuPunct(hz / 1000.0, 1)
	return ("dreapta", "%d" % (hz // 1000))


def _hdmiTv(v):
	if v.get("legat") is None:
		return None
	return ("fix", "TV" if v["legat"] else "----")


def _urma(v):
	s = v.get("urma")
	if s is None:
		return None
	m, sec = divmod(int(s), 60)
	if m < 10:
		return ("fix", "-%d%02d" % (m, sec))
	return _minus(m)


_ORA = [
	("24", N_("24 de ore"), lambda t: ("fix", _hm(t))),
	("12", N_("12 ore"), lambda t: ("dreapta", _ora12(t))),
	("12ap", N_("12 ore, cu AM sau PM pe rând"), _ora12ap),
	("ore", N_("numai ora"), lambda t: ("fix", "%d H" % t.tm_hour)),
]

# ---------------------------------------------------------------- lista datelor

D = Data

CATALOG = [
	# ------------------------------------------------------------ ceas
	D("ceas.ora", N_("Ora"), GRATIS, 60, _ceas, None, _ORA,
		N_("Fără cele două puncte: afișajul nu le are între cifre. 2105 înseamnă 21:05.")),
	D("ceas.secunde", N_("Minutele și secundele"), GRATIS, 1, _ceas, None, [
		("ms", N_("minute și secunde"), lambda t: ("fix", "%02d%02d" % (t.tm_min, t.tm_sec))),
		("s", N_("numai secundele"), lambda t: ("dreapta", "%d" % t.tm_sec)),
	]),
	D("ceas.data", N_("Data"), GRATIS, 60, _ceas, None, [
		("zl", N_("ziua și luna"), lambda t: ("fix", "%02d%02d" % (t.tm_mday, t.tm_mon))),
		("lz", N_("luna și ziua"), lambda t: ("fix", "%02d%02d" % (t.tm_mon, t.tm_mday))),
		("z", N_("numai ziua"), lambda t: ("dreapta", "%d" % t.tm_mday)),
		("derulat", N_("data întreagă, derulată"), _dataDerulat),
	]),
	D("ceas.ziua", N_("Ziua săptămânii"), GRATIS, 60, _ceas, None, [
		("scurt", N_("trei litere"), lambda t: _scurt3(_ziua(t, True))),
		("cu_data", N_("două litere și ziua"), _ziuaCuData),
		("intreg", N_("numele întreg, derulat"), lambda t: ("derulat", _ziua(t))),
	]),
	D("ceas.luna", N_("Luna"), GRATIS, 3600, _ceas, None, [
		("scurt", N_("trei litere"), lambda t: _scurt3(_luna(t))),
		("numar", N_("numărul lunii"), lambda t: ("dreapta", "%d" % t.tm_mon)),
	]),
	D("ceas.anul", N_("Anul"), GRATIS, 3600, _ceas, None, [
		("an", N_("anul"), lambda t: ("fix", "%04d" % t.tm_year)),
	]),
	D("ceas.ziua_anului", N_("Ziua din an"), GRATIS, 3600, _ceas, None, [
		("n", N_("numărul zilei"), lambda t: ("dreapta", "%d" % t.tm_yday)),
	]),
	D("ceas.saptamana", N_("Săptămâna din an"), GRATIS, 3600, _ceas, None, [
		("n", N_("numărul săptămânii"), lambda t: ("dreapta", "%d" % int(time.strftime("%V", t)))),
	]),
	D("ceas.utc", N_("Ora universală (UTC)"), GRATIS, 60, _utc, None, [
		("24", N_("24 de ore"), lambda t: ("fix", _hm(t))),
	]),
	D("ceas.oprire", N_("Timpul până la oprirea programată"), GRATIS, 60, _oprire, 45, [
		("m", N_("în minute"), _numar()),
		("cu_text", N_("cu OFF înainte, derulat"), lambda v: ("derulat", "OFF %d" % v)),
	], N_("Se arată numai cât oprirea programată e pusă.")),
	D("ceas.alt_fus", N_("Ora din alt oraș"), GRATIS, 60, _altFus, None, [
		("24", N_("24 de ore"), lambda v: ("fix", _hm(v["ora"]))),
		("cu_oras", N_("orașul și ora, derulat"), lambda v: ("derulat", u"%s %s" % (v["oras"], _hm(v["ora"])))),
	], N_("Orașul îl alegi în Setări, la „Ora din alt oraș”.")),
	D("ceas.minutar", N_("Minutarul (numărătoare inversă)"), GRATIS, 1, _minutar, 12 * 60 + 5, [
		("ms", N_("minute și secunde"), _minutarMs),
		("m", N_("numai minutele"), lambda s: ("dreapta", "%d" % ((s + 59) // 60))),
	], N_("Îl pornești în Setări, la „Minutarul”. La zero clipește un minut.")),
	D("ceas.cronometru", N_("Cronometrul"), GRATIS, 1, _cronometru, 3 * 60 + 12, [
		("ms", N_("minute și secunde"), _cronometruMs),
	], N_("Îl pornești și îl oprești în Setări, la „Cronometrul”.")),
	D("ceas.sincronizat", N_("De unde vine ora"), GRATIS, 60, _sincronizat, 3, [
		("sursa", N_("NTP, SAT, RTC sau PROV"), lambda c: ("fix", SURSE_ORA.get(c, "----"))),
	], N_("NTP: prin Internet; SAT: de la două transpondere; RTC: ceasul receptorului; PROV: provizorie.")),
	# ------------------------------------------------------------ receptor
	D("receptor.temperatura", N_("Temperatura procesorului"), GRATIS, 5, _temperatura, 45, [
		("gc", N_("grade Celsius"), _tempGC),
		("g", N_("cu semnul de grad"), lambda v: ("fix", u"%d°" % v)),
		("t", N_("cu t înainte"), lambda v: ("fix", "t%3d" % v)),
		("n", N_("numai cifrele"), _numar()),
		("bara", N_("ca bară (30-95 °C)"), _bara(*CAPETE_TEMPERATURA)),
	]),
	D("receptor.frecventa", N_("Frecvența procesorului"), PROC, 5, _frecventa, 1600, [
		("mhz", N_("MHz"), _numar()),
		("ghz", N_("GHz cu punct"), lambda v: _cuPunct(v / 1000.0, 1, "G")),
	]),
	D("receptor.mod", N_("Modul procesorului"), GRATIS, 0, _modProcesor, "AUTO", [
		("scurt", N_("scurt"), _txt("fix")),
	], N_("Automat AUTO, Normal NOR, Răcoros RAC, Performanță PERF.")),
	D("receptor.incarcare", N_("Cât lucrează procesorul, în procente"), PROC, 2, _incarcare, 37, [
		("n", N_("procent"), _numar()),
		("pr", N_("cu semnul de procent"), _procent),
		("cpu", N_("cu CPU înainte, derulat"), lambda v: ("derulat", "CPU %d%%" % v)),
		("bara", N_("ca bară"), _bara()),
	]),
	D("receptor.incarcare_medie", N_("Încărcarea medie (un minut)"), PROC, 5, _incarcareMedie, 0.45, [
		("punct", N_("cu punct"), lambda v: _cuPunct(v, 2)),
	]),
	D("receptor.tensiune", N_("Tensiunea procesorului"), PROC, 5, _tensiune, 1050, [
		("mv", N_("milivolți"), _numar()),
	]),
	D("receptor.memorie", N_("Memoria liberă"), PROC, 5, _memorie, {"liber_mb": 312, "folosit": 0.61}, [
		("mb", N_("MB"), lambda v: ("dreapta", "%d" % min(9999, v["liber_mb"]))),
		("pr", N_("procent folosit"), lambda v: _procent(int(round(v["folosit"] * 100)))),
		("bara", N_("ca bară (folosită)"), lambda v: ("bara", v["folosit"])),
	]),
	D("receptor.pornit_de", N_("Timpul de la pornire"), PROC, 60, _pornitDe, 3 * 86400 + 4 * 3600 + 12 * 60, [
		("hm", N_("ore și minute"), _hMin),
		("zile", N_("zile"), _pornitZile),
		("derulat", N_("întreg, derulat"), _pornitDerulat),
	]),
	D("receptor.versiune", N_("Versiunea imaginii"), GRATIS, 0, _versiune, ("0", "1", "6"), [
		("scurt", N_("scurt"), lambda v: ("dreapta", "".join(v)[:4])),
		("derulat", N_("cu numele, derulat"), lambda v: ("derulat", "HDSATELIT " + " ".join(v))),
	]),
	D("receptor.nume", N_("Numele receptorului"), GRATIS, 0, _numeReceptor, "viper4k", [
		("derulat", N_("derulat"), _txt("derulat")),
		("fix", N_("primele patru litere"), _txt("fix")),
	]),
	D("receptor.caldura", N_("Semnul de încălzire"), GRATIS, 5, _caldura, True, [
		("hot", N_("HOT cât e cald"), _fixText("HOT")),
	], N_("Se arată numai cât procesorul merge încet din cauza căldurii.")),
	# ------------------------------------------------------------ stocare
	D("stocare.liber", N_("Spațiul liber pe disc"), FIR, 60, _discLiber, {"liber_gb": 512.0, "folosit": 0.37}, [
		("gb", N_("GB (TB cu punct de la 1000)"), _liberGB),
		("tb", N_("TB cu punct"), lambda v: _cuPunct(v["liber_gb"] / 1000.0, 2, "T")),
		("pr", N_("procent folosit"), lambda v: _procent(int(round(v["folosit"] * 100)))),
		("bara", N_("ca bară (folosit)"), lambda v: ("bara", v["folosit"])),
	], N_("Locul înregistrărilor, citit pe un fir separat, cel mult o dată pe minut.")),
	D("stocare.ore", N_("Ore de înregistrare rămase"), FIR, 60, _discLiber, {"liber_gb": 480.0, "folosit": 0.4}, [
		("h", N_("ore (cam 4 GB pe oră)"), lambda v: ("dreapta", "%dH" % min(999, int(v["liber_gb"] / GB_PE_ORA)))),
	]),
	D("stocare.inregistrari", N_("Câte înregistrări ai"), FIR, 300, _inregistrari, 24, [
		("n", N_("numărul"), _numar()),
	]),
	D("stocare.usb", N_("Memoria USB e legată"), PROC, 10, _usb, True, [
		("usb", N_("USB cât e legată"), _fixText("USB")),
	]),
	# ------------------------------------------------------------ retea
	D("retea.ip", N_("Adresa IP"), GRATIS, 60, _ip, [192, 168, 1, 122], [
		("derulat", N_("întreagă, derulată"), _ipDerulat),
		("ultim", N_("ultimul număr, cu punct"), lambda v: ("punct", ".%d" % v[3])),
	]),
	D("retea.legatura", N_("Legătura la rețea"), GRATIS, 10, _legatura, "LAN", [
		("fel", N_("LAN sau WiFi"), _txt("fix")),
	]),
	D("retea.internet", N_("Internetul merge"), GRATIS, 60, _internet, True, [
		("onoff", N_("ON sau OFF"), lambda v: ("fix", "ON" if v else "OFF")),
	]),
	D("retea.viteza", N_("Viteza de descărcare"), PROC, 2, _vitezaRetea, 85.0, [
		("mbit", N_("Mbit/s"), _mbit),
		("bara", N_("ca bară (față de 100 Mbit/s)"), lambda v: ("bara", v / VITEZA_BARA_MBIT)),
	]),
	D("retea.wifi", N_("Semnalul Wi-Fi"), PROC, 5, _wifi, 70, [
		("pr", N_("procent"), _procent),
		("bara", N_("ca bară"), _bara()),
	]),
	D("retea.clienti", N_("Câți privesc prin rețea"), GRATIS, 10, _clienti, 2, [
		("n", N_("numărul"), _numar()),
	]),
	# ------------------------------------------------------------ canal
	D("canal.numar", N_("Numărul canalului"), EVENIMENT, 0, _numarCanal, 12, [
		("dreapta", N_("aliniat la dreapta"), _numar()),
		("stanga", N_("aliniat la stânga"), _numar("fix")),
	], N_("Numărul din lista de canale, cel la care duc cifrele telecomenzii.")),
	D("canal.nume", N_("Numele canalului"), EVENIMENT, 0, _numeCanal, u"Digi Sport 1", [
		("derulat", N_("derulat"), _txt("derulat")),
		("fix", N_("primele patru litere"), _txt("fix")),
	]),
	D("canal.numar_nume", N_("Numărul și numele"), EVENIMENT, 0, _numarNume, u"12 Pro TV", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("canal.furnizor", N_("Furnizorul canalului"), EVENIMENT, 0, _furnizor, u"Focus Sat", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("canal.lista", N_("Lista de canale (buchetul)"), EVENIMENT, 0, _lista, u"Favorite", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("canal.cate", N_("Câte canale are lista"), EVENIMENT, 0, _cate, 245, [
		("n", N_("numărul"), _numar()),
	]),
	D("canal.fel", N_("Felul canalului"), EVENIMENT, 0, _felCanal, "TV", [
		("scurt", N_("TV, RAD, IPTV sau DAB"), _txt("fix")),
	]),
	D("canal.calitate", N_("HD, UHD sau SD"), EVENIMENT, 0, _calitate, "UHD", [
		("scurt", N_("scurt"), _txt("fix")),
	]),
	D("canal.codat", N_("Codat sau liber"), EVENIMENT, 0, _codat, "COD", [
		("scurt", N_("COD sau LIB"), _txt("fix")),
	]),
	D("canal.sid", N_("SID (numărul serviciului)"), EVENIMENT, 0, _info("sSID"), 1234, [
		("hex", N_("hexazecimal"), _hex),
		("dec", N_("zecimal"), _numar()),
	], N_("Pentru pasionați.")),
	D("canal.tsid", N_("Numărul transponderului (TSID)"), EVENIMENT, 0, _info("sTSID"), 1107,
		[("hex", N_("hexazecimal"), _hex)], N_("Pentru pasionați.")),
	D("canal.onid", N_("Numărul rețelei (ONID)"), EVENIMENT, 0, _info("sONID"), 1, [("hex", N_("hexazecimal"), _hex)],
		N_("Pentru pasionați.")),
	D("canal.pid_video", N_("PID-ul video"), EVENIMENT, 0, _info("sVideoPID"), 101, [("dec", N_("zecimal"), _numar())],
		N_("Pentru pasionați.")),
	D("canal.pid_audio", N_("PID-ul audio"), EVENIMENT, 0, _info("sAudioPID"), 102, [("dec", N_("zecimal"), _numar())],
		N_("Pentru pasionați.")),
	# ------------------------------------------------------------ semnal
	D("semnal.frecventa", N_("Frecvența transponderului"), EVENIMENT, 0, _frecventaTp, {"mhz": 11052, "pol": "H"}, [
		("derulat", N_("cu polarizarea, derulat"), _frecventaDerulat),
		("mhz", N_("MHz (cablu, terestru)"), _frecventaMhz),
	], N_("La satelit are 5 cifre, deci se derulează.")),
	D("semnal.polarizare", N_("Polarizarea"), EVENIMENT, 0, _polarizare, "H", [
		("litera", N_("o literă"), _txt("dreapta")),
	]),
	D("semnal.rata", N_("Rata de simbol"), EVENIMENT, 0, _rata, "27500", [
		("derulat", N_("cu SR înainte, derulat"), _txt("derulat", "SR %s")),
	]),
	D("semnal.fec", N_("Corecția erorilor (FEC)"), EVENIMENT, 0, _fec, "3/4", [
		("fix", N_("fracția"), _txt("fix")),
	]),
	D("semnal.sistem", N_("Sistemul (DVB-S2, T2, C)"), EVENIMENT, 0, _sistem, "S2", [
		("scurt", N_("scurt"), _txt("fix")),
	], N_("S seamănă cu 5: în context se citește.")),
	D("semnal.modulatie", N_("Modulația"), EVENIMENT, 0, _modulatie, "8PSK", [
		("scurt", N_("scurt"), _txt("fix")),
	]),
	D("semnal.satelit", N_("Poziția satelitului"), EVENIMENT, 0, _pozitieOrbitala, 192, [
		("pozitie", N_("poziția, fără punct"), lambda v: ("fix", textPozitie(v))),
		("punct", N_("cu punct (19.2E)"), lambda v: _cuPunct((3600 - v if v > 1800 else v) / 10.0, 1,
			"W" if v > 1800 else "E")),
	], N_("Fără punct: 192E pentru 19.2E. Cu punct: fără zecimală peste 100 de grade.")),
	D("semnal.satelit_nume", N_("Numele satelitului"), EVENIMENT, 0, _numeSatelit, u"Astra 19.2E", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("semnal.banda", N_("Banda LNB (joasă sau înaltă)"), EVENIMENT, 0, _banda, "HI", [
		("scurt", N_("HI sau LO"), _txt("fix")),
	]),
	D("semnal.tuner", N_("Tunerul folosit"), EVENIMENT, 0, _tuner, "A", [
		("litera", N_("litera tunerului"), _txt("fix", "T %s")),
	]),
	D("semnal.calitate", N_("Calitatea semnalului"), TUNER, 2, _procentTuner("quality"), 92, [
		("pr", N_("procent"), _numar()),
		("q", N_("cu q înainte"), lambda v: ("fix", "Q%3d" % min(99, v))),
		("bara", N_("ca bară"), _bara()),
	]),
	D("semnal.nivel", N_("Puterea semnalului"), TUNER, 2, _procentTuner("power"), 78, [
		("pr", N_("procent"), _numar()),
		("bara", N_("ca bară"), _bara()),
	]),
	D("semnal.snr", N_("Raportul semnal/zgomot"), TUNER, 2, _snr, 12.4, [
		("db", N_("dB"), lambda v: ("fix", "%dDB" % min(99, int(round(v))))),
	]),
	D("semnal.ber", N_("Erori (BER)"), TUNER, 2, _ber, 0, [
		("n", N_("numărul"), lambda v: ("dreapta", "%d" % min(9999, v))),
		("cu_text", N_("cu BER înainte, derulat"), lambda v: ("derulat", "BER %d" % v)),
	]),
	D("semnal.blocat", N_("Fără semnal"), TUNER, 2, _faraSemnal, True, [
		("liniute", N_("patru liniuțe cât lipsește semnalul"), _fixText("----")),
	]),
	D("semnal.debit", N_("Debitul frecvenței"), PROC, 2, _debitFrecventa, 38.5, [
		("mbit", N_("Mbit/s cu punct"), _debitMbit),
		("n", N_("Mbit/s"), _mbit),
	], N_("Toată frecvența, măsurată pe receptor.")),
	D("semnal.motor", N_("Antena cu motor"), GRATIS, 1, _motor, {"directie": "est", "grade": 19.2}, [
		("rot", N_("ROT cât se rotește"), _fixText("ROT")),
		("sageti", N_("săgeata în direcția rotirii"), lambda v: ("sageti", "vest" if v["directie"] == "vest" else "est")),
		("grade", N_("poziția antenei"), _motorGrade),
		("inel", N_("segmentul care se rotește"), lambda v: ("inel", None)),
	], N_("Se arată numai cât antena se rotește.")),
	# ------------------------------------------------------------ imagine
	D("imagine.rezolutie", N_("Rezoluția canalului"), EVENIMENT, 0, _info("sVideoHeight"), 1080, [
		("linii", N_("liniile"), _numar()),
	]),
	D("imagine.latime", N_("Lățimea imaginii"), EVENIMENT, 0, _info("sVideoWidth"), 1920, [
		("n", N_("pixeli"), _numar()),
	]),
	D("imagine.cadre", N_("Cadre pe secundă"), EVENIMENT, 0, _cadre, {"fps": 50, "progresiv": 1}, [
		("n", N_("numărul"), lambda v: ("dreapta", "%d" % v["fps"])),
		("pi", N_("cu P sau I"), _cadrePI),
	]),
	D("imagine.codec", N_("Codecul video"), EVENIMENT, 0, _codecVideo, "H265", [
		("scurt", N_("scurt"), _txt("fix")),
	]),
	D("imagine.aspect", N_("Formatul imaginii"), EVENIMENT, 0, _aspect, "16-9", [
		("raport", N_("raportul"), _txt("fix")),
	]),
	D("imagine.hdr", N_("HDR"), EVENIMENT, 0, _hdr, "HDR", [
		("scurt", N_("HDR, HLG sau SDR"), _txt("fix")),
	]),
	D("imagine.debit", N_("Debitul video"), GRATIS, 10, _debitVideo, 8.5, [
		("mbit", N_("Mbit/s cu punct"), _debitMbit),
		("n", N_("Mbit/s"), _mbit),
	], N_("Numai după o analiză a fluxului canalului (din mesajul de ecran negru sau din web).")),
	D("imagine.hdmi", N_("Televizorul legat (HDMI)"), PROC, 10, _hdmi, {"legat": True, "hdcp": True}, [
		("tv", N_("TV cât e legat, liniuțe când nu"), _hdmiTv),
		("hdcp", N_("HDCP cât protecția e pornită"), lambda v: ("fix", "HDCP") if v.get("hdcp") else None),
	]),
	D("imagine.iesire", N_("Rezoluția trimisă la televizor"), PROC, 60, _iesire, {"linii": 2160, "hz": 50}, [
		("linii", N_("liniile"), lambda v: ("dreapta", "%d" % v["linii"]) if v.get("linii") else None),
		("hz", N_("frecvența (Hz)"), lambda v: ("dreapta", "%d" % v["hz"]) if v.get("hz") else None),
	]),
	# ------------------------------------------------------------ sunet
	D("sunet.volum", N_("Volumul"), EVENIMENT, 5, _volum, 45, [
		("n", N_("numărul"), _numar()),
		("bara", N_("ca bară"), _bara()),
	]),
	D("sunet.mut", N_("Sunetul oprit (mut)"), EVENIMENT, 5, _mut, True, [
		("mut", N_("MUT cât e oprit"), _fixText("MUT")),
	]),
	D("sunet.codec", N_("Formatul sunetului"), EVENIMENT, 0, _codecSunet, "EAC3", [
		("scurt", N_("scurt"), _txt("fix")),
	]),
	D("sunet.canale", N_("Canalele de sunet"), EVENIMENT, 0, _canaleSunet, "5.1", [
		("punct", N_("cu punct"), _txt("punct")),
	]),
	D("sunet.limba", N_("Limba sunetului"), EVENIMENT, 0, _limbaSunet, "ron", [
		("iso", N_("trei litere"), _txt("fix")),
	]),
	D("sunet.pista", N_("Pista de sunet"), EVENIMENT, 0, _pistaDin, "2/3", [
		("din", N_("a câta din câte"), _txt("fix")),
	]),
	D("sunet.subtitrari", N_("Subtitrările"), EVENIMENT, 5, _subtitrare, {"limba": u"ron"}, [
		("are", N_("SUB cât sunt pornite"), _fixText("SUB")),
		("limba", N_("limba subtitrării"), lambda v: ("fix", L.transcrie(v["limba"])[:3].upper() if v.get("limba")
			else "SUB")),
	]),
	D("sunet.esantionare", N_("Eșantionarea sunetului"), GRATIS, 5, _esantionare, 48000, [
		("khz", N_("kHz"), _khz),
	], N_("Numai la radio, cât se analizează sunetul postului.")),
	D("sunet.debit", N_("Debitul sunetului"), GRATIS, 2, _debitSunet, 192, [
		("kbit", N_("kbit/s"), lambda v: ("dreapta", "%d" % min(9999, v))),
	], N_("La radio, măsurat cât se analizează sunetul; la DAB+, cel anunțat de post.")),
	D("sunet.teletext", N_("Teletextul"), EVENIMENT, 0, _teletext, True, [
		("tt", N_("TT cât canalul are teletext"), _fixText("TT")),
	]),
	# ------------------------------------------------------------ emisiune
	D("emisiune.titlu", N_("Titlul emisiunii"), GHID, 30, _emisiune, None, [
		("derulat", N_("derulat"), lambda v: ("derulat", v["titlu"]) if v["titlu"] else None),
	]),
	D("emisiune.inceput", N_("Ora de început"), GHID, 30, _emisiune, None, [
		("24", N_("ora"), lambda v: ("fix", _txtOra(v["inceput"]))),
	]),
	D("emisiune.sfarsit", N_("Ora de sfârșit"), GHID, 30, _emisiune, None, [
		("24", N_("ora"), lambda v: ("fix", _txtOra(v["inceput"] + v["durata"]))),
	]),
	D("emisiune.interval", N_("Începutul și sfârșitul"), GHID, 30, _emisiune, None, [
		("alternat", N_("pe rând"), lambda v: ("alternat", [_txtOra(v["inceput"]), _txtOra(v["inceput"] + v["durata"])])),
	]),
	D("emisiune.durata", N_("Durata"), GHID, 30, _emisiune, None, [
		("hm", N_("ore și minute"), lambda v: _hMin(v["durata"])),
		("m", N_("în minute"), lambda v: ("dreapta", "%d" % _minute(v["durata"]))),
	]),
	D("emisiune.ramas", N_("Timpul rămas"), GHID, 60, _emisiuneAcum, None, [
		("minus", N_("minute, cu minus"), _emisiuneRamas("minus")),
		("m", N_("în minute"), _emisiuneRamas("m")),
	]),
	D("emisiune.trecut", N_("Timpul trecut"), GHID, 60, _emisiuneAcum, None, [
		("m", N_("în minute"), lambda v: ("dreapta", "%d" % _minute(max(0, v["acum"] - v["inceput"])))),
	]),
	D("emisiune.procent", N_("Cât a trecut din emisiune"), GHID, 60, _emisiuneAcum, None, [
		("pr", N_("procent"), _emisiuneProcent("pr")),
		("bara", N_("ca bară"), _emisiuneProcent("bara")),
	]),
	D("emisiune.urmatoarea", N_("Emisiunea următoare"), GHID, 60, _urmatoarea, None, [
		("derulat", N_("titlul, derulat"), lambda v: ("derulat", v["titlu"]) if v["titlu"] else None),
		("ora", N_("ora de început"), lambda v: ("fix", _txtOra(v["inceput"]))),
		("ora_titlu", N_("ora și titlul, derulat"), lambda v: ("derulat", u"%s %s" % (_txtOra(v["inceput"]), v["titlu"]))),
	]),
	D("emisiune.varsta", N_("Vârsta recomandată"), GHID, 60, _varsta, 12, [
		("n", N_("anii"), _numar()),
	]),
	D("emisiune.gen", N_("Genul emisiunii"), GHID, 60, _gen, u"Sport", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("emisiune.descriere", N_("Descrierea scurtă"), GHID, 60, _emisiune, None, [
		("derulat", N_("derulat"), lambda v: ("derulat", v["descriere"]) if v["descriere"] else None),
	]),
	# ------------------------------------------------------------ radio
	D("radio.post", N_("Numele postului de radio"), EVENIMENT, 0, _post, u"Radio România Actualități", [
		("derulat", N_("derulat"), _txt("derulat")),
		("fix", N_("primele patru litere"), _txt("fix")),
	], N_("Se arată numai când asculți radio.")),
	D("radio.text", N_("Textul radio (RDS)"), EVENIMENT, 10, _rds("text"), u"Asculți Kiss FM", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("radio.piesa", N_("Piesa (RT+)"), EVENIMENT, 10, _rds("piesa"), u"Bohemian Rhapsody", [
		("derulat", N_("derulat"), _txt("derulat")),
	], N_("Titlul piesei, când postul îl trimite.")),
	D("radio.artist", N_("Artistul (RT+)"), EVENIMENT, 10, _rds("artist"), u"Queen", [
		("derulat", N_("derulat"), _txt("derulat")),
	], N_("Când postul îl trimite.")),
	D("radio.artist_piesa", N_("Artistul și piesa (RT+)"), EVENIMENT, 10, _rds("artist_piesa"),
		u"Queen - Bohemian Rhapsody", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("radio.dab", N_("Ansamblul DAB+"), EVENIMENT, 5, _ansamblu, u"DAB Italia", [
		("derulat", N_("derulat"), _txt("derulat")),
	], N_("Numai la posturile DAB+ din satelit.")),
	# ------------------------------------------------------------ inregistrari
	D("inregistrari.rec", N_("Se înregistrează"), EVENIMENT, 10, _rec, 1, [
		("rec", N_("REC"), _fixText("REC")),
		("rec_n", N_("REC și câte"), lambda v: ("fix", "REC%d" % v if v < 10 else "REC")),
	], N_("Se arată numai cât merge o înregistrare.")),
	D("inregistrari.durata", N_("Cât s-a înregistrat"), GRATIS, 60, _durataRec, 83 * 60, [
		("hm", N_("ore și minute"), _hMin),
	]),
	D("inregistrari.nume", N_("Ce se înregistrează"), EVENIMENT, 0, _numeRec, u"Filmul de seară", [
		("derulat", N_("derulat"), lambda v: ("derulat", u"REC " + v)),
	]),
	D("inregistrari.urmatoarea_ora", N_("Ora următoarei înregistrări"), EVENIMENT, 60, _urmatoareaInregistrare,
		None, [
		("24", N_("ora"), lambda v: ("fix", _txtOra(v["inceput"]))),
	]),
	D("inregistrari.pana_la", N_("Timpul până la următoarea înregistrare"), GRATIS, 60, _urmatoareaInregistrare, None, [
		("minus", N_("minute, cu minus"), lambda v: _minus(_minute(max(0, v["inceput"] - v["acum"]) + 59))),
	]),
	D("inregistrari.urmatoarea", N_("Următoarea înregistrare"), EVENIMENT, 60, _urmatoareaInregistrare, None, [
		("derulat", N_("ora și numele, derulat"), lambda v: ("derulat", u"%s %s" % (_txtOra(v["inceput"]), v["nume"]))),
	]),
	D("inregistrari.programari", N_("Câte programări ai"), EVENIMENT, 60, _programari, 5, [
		("n", N_("numărul"), _numar()),
		("cu_text", N_("cu PROG înainte, derulat"), lambda v: ("derulat", "PROG %d" % v)),
	]),
	D("inregistrari.timeshift", N_("Pauză în direct (timeshift)"), EVENIMENT, 1, _timeshift, {"urma": 312}, [
		("ts", N_("TS cât merge"), _fixText("TS")),
		("urma", N_("cât ești în urmă"), _urma),
	]),
	# ------------------------------------------------------------ redare
	D("redare.pozitie", N_("Poziția în film"), GRATIS, 1, _redare, {"poz": 83 * 60.0, "lung": 7200.0}, [
		("hm", N_("ore și minute"), lambda v: _hMin(v["poz"])),
		("ms", N_("minute și secunde"), lambda v: _minSec(v["poz"])),
	], N_("Se arată numai când se redă un film sau o înregistrare.")),
	D("redare.ramas", N_("Cât mai e din film"), GRATIS, 1, _redare, {"poz": 83 * 60.0, "lung": 7200.0}, [
		("minus", N_("minute, cu minus"), lambda v: _minus(_minute(max(0.0, v["lung"] - v["poz"])))),
	]),
	D("redare.procent", N_("Cât a trecut din film"), GRATIS, 5, _redare, {"poz": 2880.0, "lung": 7200.0}, [
		("bara", N_("ca bară"), _redareProcent("bara")),
		("pr", N_("procent"), _redareProcent("pr")),
	]),
	D("redare.stare", N_("Starea redării"), EVENIMENT, 1, _stareRedare, "PLAY", [
		("scurt", N_("PLAY, pauză, derulare"), _txt("fix")),
	]),
	D("redare.nume", N_("Numele filmului"), EVENIMENT, 0, _numeFilm, u"Vacanța la mare", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	# ------------------------------------------------------------ acces
	D("acces.ecm_timp", N_("Timpul ECM"), PROC, 5, _ecm, {"ms": 120, "local": True, "caid": 0x0B00}, [
		("ms", N_("milisecunde"), _ecmMs),
		("e", N_("cu E înainte"), _ecmE),
	], N_("Numai timpul, fără nume sau adrese.")),
	D("acces.caid", N_("Codul sistemului de acces (CAID)"), PROC, 5, _ecm, {"ms": 120, "local": True,
		"caid": 0x0B00}, [
		("hex", N_("hexazecimal"), lambda v: _hex(v["caid"])),
	], N_("Pentru pasionați.")),
	D("acces.sistem", N_("Sistemul de acces"), PROC, 5, _numeSistem, u"Conax", [
		("derulat", N_("derulat"), _txt("derulat")),
	]),
	D("acces.loc", N_("Răspunsul vine local sau prin rețea"), PROC, 5, _ecm, {"ms": 120, "local": True,
		"caid": 0x0B00}, [
		("scurt", N_("LOC sau NET"), _ecmLoc),
	]),
	D("acces.ci", N_("Modulul CI"), GRATIS, 10, _ci, u"CI+ CAM", [
		("ci", N_("CI cât e gata"), _fixText("CI")),
		("nume", N_("numele modulului, derulat"), _txt("derulat")),
	], N_("Numai cât un modul CI e în slot și gata.")),
	# ------------------------------------------------------------ texte
	D("texte.liber", N_("Textul tău"), GRATIS, 0, _textTau, u"Bună seara", [
		("derulat", N_("derulat"), _txt("derulat")),
		("fix", N_("fix, primele patru"), _txt("fix")),
	], N_("Îl scrii în Setări, la „Textul tău”.")),
	D("texte.sigla", N_("Sigla"), GRATIS, 0, _mereu, True, [
		("scurt", N_("scurt"), _fixText("HDS")),
		("derulat", N_("derulat"), lambda v: ("derulat", "HDSATELIT")),
	]),
	D("texte.inel", N_("Segmentul care se rotește"), GRATIS, 0, _mereu, True, [
		("inel", N_("în jurul afișajului"), lambda v: ("inel", None)),
	]),
	D("texte.liniute", N_("Liniuțe"), GRATIS, 0, _mereu, True, [
		("liniute", N_("patru liniuțe"), _fixText("----")),
	]),
	D("texte.nimic", N_("Nimic (afișaj stins)"), GRATIS, 0, _mereu, True, [
		("gol", N_("gol"), _fixText("")),
	]),
	# ------------------------------------------------------------ evenimente (mesajele scurte; valoarea o da afisajul)
	D("evenimente.volum", N_("Volumul, la schimbare"), EVENIMENT, 0, None, 45, [
		("n", N_("numărul, 3 s"), _numar()),
		("bara", N_("bara, 3 s"), _bara()),
	]),
	D("evenimente.mut", N_("MUT, la oprirea sunetului"), EVENIMENT, 0, None, True, [
		("mut", N_("MUT, 3 s"), _fixText("MUT")),
	]),
	D("evenimente.cifre", N_("Cifrele tastate pe telecomandă"), EVENIMENT, 0, None, "12", [
		("cifre", N_("cu locuri goale"), _cifreTastate),
	]),
	D("evenimente.zap", N_("Canalul nou, la schimbare"), EVENIMENT, 0, None, (12, u"Pro TV"), [
		("numar_nume", N_("numărul 2 s, apoi numele derulat"), _zapNumarNume),
		("numar", N_("numărul, 3 s"), lambda v: ("dreapta", "%d" % v[0]) if v[0] is not None else None),
		("nume", N_("numele derulat"), lambda v: ("derulat", v[1]) if v[1] else None),
	]),
	D("evenimente.motor", N_("Antena cu motor se rotește"), EVENIMENT, 0, None,
		{"misca": True, "directie": "est", "grade": 19.2}, [
		("sageti_grade", N_("săgețile cât se rotește, apoi poziția, 3 s"), _motorMesaj("sageti_grade")),
		("sageti", N_("săgețile cât se rotește"), _motorMesaj("sageti")),
		("grade", N_("poziția antenei"), _motorMesaj("grade")),
		("inel", N_("segmentul care se rotește"), _motorMesaj("inel")),
	], N_("După schimbarea canalului, cât antena se rotește spre alt satelit.")),
	D("evenimente.cautare", N_("Căutarea canalelor"), EVENIMENT, 0, None, 45, [
		("pr", N_("procentul, cât merge"), _procent),
		("bara", N_("bara, cât merge"), lambda v: ("bara", v / 100.0)),
	]),
	D("evenimente.actualizare", N_("Actualizarea imaginii"), EVENIMENT, 0, None, 60, [
		("upd", N_("U și procentul, cât merge"), lambda v: ("fix", "U%3d" % v if v is not True else "UPD")),
	]),
	D("evenimente.eroare", N_("Un mesaj de eroare"), EVENIMENT, 0, None, True, [
		("err", N_("ERR, 3 s"), _fixText("ERR")),
	]),
	D("evenimente.pornire", N_("La pornirea interfeței"), EVENIMENT, 0, None, True, [
		("boot", N_("BOOT, 3 s"), _fixText("BOOT")),
		("inel", N_("segmentul care se rotește, 3 s"), lambda v: ("inel", None)),
	]),
	D("evenimente.usb", N_("Memoria USB legată"), EVENIMENT, 0, None, True, [
		("usb", N_("USB, 3 s"), _fixText("USB")),
	]),
	D("evenimente.rec", N_("Înregistrarea pornește"), EVENIMENT, 0, None, True, [
		("rec", N_("REC, 3 s"), _fixText("REC")),
	]),
	D("evenimente.fara_semnal", N_("Semnalul s-a pierdut"), EVENIMENT, 0, None, True, [
		("liniute", N_("patru liniuțe, 3 s"), _fixText("----")),
	]),
	# ------------------------------------------------------------ asteptare (o singura alegere)
	D("asteptare.ora", N_("Ora"), GRATIS, 60, _ceas, None, [
		("24", N_("24 de ore"), lambda t: ("fix", _hm(t))),
	]),
	D("asteptare.ora_data", N_("Ora și data, pe rând"), GRATIS, 60, _ceas, None, [
		("alternat", N_("pe rând, câte 2 s"), _alternatOraData),
	]),
	D("asteptare.rec", N_("Ora și următoarea înregistrare"), GRATIS, 60, _urmatoareaInregistrare, None, [
		("alternat", N_("REC și ora ei, pe rând"), _recAlternat),
	], N_("Fără o înregistrare programată arată ora.")),
	D("asteptare.stins", N_("Nimic (afișaj stins)"), GRATIS, 0, _mereu, True, [
		("gol", N_("gol"), _fixText("")),
	]),
]

DUPA_ID = dict((d.id, d) for d in CATALOG)

# Etichetele scurte (cel mult 4 pozitii) care pot trece inainte de valoare in lista de rotire („+e”), ca sa se stie ce
# inseamna un numar. Numai prescurtari tehnice, la fel in orice limba.
SCURT = {
	"ceas.secunde": "SEC",
	"ceas.ziua_anului": "DAY",
	"ceas.saptamana": "WK",
	"ceas.utc": "UTC",
	"ceas.oprire": "OFF",
	"receptor.temperatura": "TMP",
	"receptor.frecventa": "MHZ",
	"receptor.incarcare": "CPU",
	"receptor.incarcare_medie": "LOAD",
	"receptor.tensiune": "MV",
	"receptor.memorie": "RAM",
	"receptor.pornit_de": "UP",
	"stocare.liber": "HDD",
	"stocare.ore": "HDD",
	"stocare.inregistrari": "REC",
	"retea.ip": "IP",
	"retea.viteza": "NET",
	"retea.wifi": "WIFI",
	"retea.clienti": "STR",
	"canal.numar": "CH",
	"canal.cate": "CH",
	"canal.sid": "SID",
	"canal.tsid": "TSID",
	"canal.onid": "ONID",
	"canal.pid_video": "VPID",
	"canal.pid_audio": "APID",
	"semnal.fec": "FEC",
	"semnal.satelit": "SAT",
	"semnal.calitate": "QUAL",
	"semnal.nivel": "PWR",
	"semnal.snr": "SNR",
	"semnal.ber": "BER",
	"imagine.rezolutie": "RES",
	"imagine.latime": "RES",
	"imagine.cadre": "FPS",
	"imagine.iesire": "OUT",
	"sunet.volum": "VOL",
	"sunet.codec": "AUD",
	"sunet.limba": "AUD",
	"sunet.pista": "AUD",
	"emisiune.inceput": "STRT",
	"emisiune.sfarsit": "END",
	"emisiune.durata": "DUR",
	"emisiune.ramas": "END",
	"emisiune.trecut": "PROG",
	"emisiune.procent": "PROG",
	"emisiune.varsta": "AGE",
	"inregistrari.durata": "REC",
	"inregistrari.urmatoarea_ora": "REC",
	"inregistrari.pana_la": "REC",
	"inregistrari.programari": "PROG",
	"redare.pozitie": "POS",
	"redare.ramas": "END",
	"redare.procent": "POS",
	"acces.ecm_timp": "ECM",
	"acces.caid": "CAID",
}

# momentul exemplelor (ora, emisiunea): ziua de azi la 21:05:33, ca previzualizarea sa nu depinda de ceas
MOMENT_EXEMPLU = time.mktime(tuple(time.localtime()[:3]) + (21, 5, 33, 0, 0, -1))


# exemplele unui singur format, cand exemplul datei nu i se potriveste (frecventa de satelit nu are loc pe 4 cifre)
EXEMPLE_FORMAT = {
	"semnal.frecventa:mhz": {"mhz": 474, "pol": u""},
}


def exemplu(d, f=None):
	"""Valoarea de exemplu a unei date (previzualizarea cand valoarea de acum lipseste), pentru formatul `f`."""
	if f is not None:
		v = EXEMPLE_FORMAT.get(idAlegere(d, f))
		if v is not None:
			return v
	if d.exemplu is not None:
		return d.exemplu
	if d.citeste is _ceas:
		return time.localtime(MOMENT_EXEMPLU)
	if d.citeste is _utc:
		return time.gmtime(MOMENT_EXEMPLU)
	if d.citeste in (_emisiune, _emisiuneAcum, _urmatoarea):
		return {"titlu": u"Știrile Pro TV", "inceput": MOMENT_EXEMPLU - 2220, "durata": 3600,
			"descriere": u"Meci din Liga 1", "acum": MOMENT_EXEMPLU}
	if d.citeste is _urmatoareaInregistrare:
		return {"inceput": MOMENT_EXEMPLU + 2700, "nume": u"Meci", "acum": MOMENT_EXEMPLU}
	if d.citeste is _altFus:
		return {"ora": time.localtime(MOMENT_EXEMPLU + 7 * 3600), "oras": u"Tokyo"}
	return None


# ---------------------------------------------------------------- alegerile

SEP_ALEGERE = ":"


def alegere(id_alegere):
	"""„grupa.nume:format” -> (Data, Format) sau (None, None). Fara format: primul format al datei."""
	id_data, _sep, id_format = (id_alegere or "").partition(SEP_ALEGERE)
	d = DUPA_ID.get(id_data.strip())
	if d is None:
		return None, None
	f = d.format(id_format.strip()) if id_format.strip() else d.formate[0]
	if f is None:
		return None, None
	return d, f


def idAlegere(d, f):
	return d.id + SEP_ALEGERE + f.id


def alegeriGrupa(grupa):
	"""Toate alegerile unei grupe, in ordinea catalogului: [(Data, Format)]."""
	return [(d, f) for d in CATALOG if d.grupa == grupa for f in d.formate]


def toateAlegerile():
	return [(d, f) for d in CATALOG for f in d.formate]


def numeGrupa(grupa):
	for g, nume in GRUPE:
		if g == grupa:
			return _(nume)
	return grupa


def textAlegere(d, f):
	"""„Temperatura procesorului: grade Celsius” (tradus); datele cu un singur format au numai numele."""
	if len(d.formate) == 1:
		return _(d.eticheta)
	return u"%s: %s" % (_(d.eticheta), _(f.eticheta))


def _pentruCautare(text):
	"""Textul fara diacritice, cu litere mici (aceeasi transcriere ca afisajul: „Ș” si „S” se potrivesc)."""
	return L.transcrie(text).lower()


def cauta(text, alegeri=None):
	"""Alegerile al caror nume (data, format sau grupa) contine toate cuvintele din `text`, fara diacritice."""
	cuvinte = _pentruCautare(text).split()
	if not cuvinte:
		return []
	grupe = dict((g, _(n)) for g, n in GRUPE)
	rez = []
	for d, f in (alegeri if alegeri is not None else toateAlegerile()):
		unde = _pentruCautare(u"%s %s %s" % (_(d.eticheta), _(f.eticheta), grupe.get(d.grupa, u"")))
		if all(c in unde for c in cuvinte):
			rez.append((d, f))
	return rez


# ---------------------------------------------------------------- desenul

class Desen(object):
	"""Cadrele (fiecare o lista de LATIME masti) si durata fiecaruia in ms. Un singur cadru = desen fix.
	`derulat`: textul trece o data (durata „cat tine derularea”); `bucla`: cadrele se reiau oricat (inel, alternat)."""
	__slots__ = ("cadre", "durate", "derulat", "bucla")

	def __init__(self, cadre, durate=None, derulat=False, bucla=False):
		self.cadre = [list(c) for c in cadre] or [[L.GOL] * L.LATIME]
		self.durate = list(durate) if durate else [0] * len(self.cadre)
		self.derulat = derulat
		self.bucla = bucla

	def fix(self):
		return len(self.cadre) == 1

	def durataTotala(self):
		return sum(self.durate)

	def __eq__(self, alt):
		return isinstance(alt, Desen) and self.cadre == alt.cadre and self.durate == alt.durate

	def __ne__(self, alt):
		return not self.__eq__(alt)

	__hash__ = None


def _desenDerulat(text, viteza, pana_iese):
	cadre = L.cadre(text, pana_iese=pana_iese)
	if len(cadre) == 1:
		return Desen(cadre)
	durate = [viteza] * len(cadre)
	durate[0] = max(viteza, PRIMUL_CADRU_MS)
	if not pana_iese:
		durate[-1] = max(viteza, ULTIMUL_CADRU_MS)
	return Desen(cadre, durate, derulat=True)


def _sageti(directie, viteza):
	"""Sageata („>” spre est, „<” spre vest) care trece peste cele 4 pozitii in directia rotirii."""
	semn = L.masca("efg") if directie == "est" else L.masca("bcg")
	pozitii = range(L.LATIME) if directie == "est" else range(L.LATIME - 1, -1, -1)
	cadre = []
	for i in pozitii:
		c = [L.GOL] * L.LATIME
		c[i] = semn
		cadre.append(c)
	return Desen(cadre, [max(150, viteza)] * len(cadre), bucla=True)


def deseneaza(pereche, viteza=VITEZA_IMPLICITA_MS, singur=False):
	"""(fel, continut) -> Desen, sau None cand nu e nimic de desenat. `singur`: alegerea e singura pe afisaj, deci
	textul derulat trece de tot, pana la afisajul gol, si reia de la capat."""
	if not pereche:
		return None
	try:
		fel, continut = pereche
	except (TypeError, ValueError):
		return None
	try:
		viteza = max(100, int(viteza or VITEZA_IMPLICITA_MS))
	except (TypeError, ValueError):
		viteza = VITEZA_IMPLICITA_MS
	if fel == "fix":
		return Desen([L.potrivit(continut)])
	if fel == "dreapta":
		return Desen([L.potrivit(continut, dreapta=True)])
	if fel == "derulat":
		return _desenDerulat(continut, viteza, singur)
	if fel == "punct":
		m = L.potrivitCuPunct(continut)
		if m is None:
			return Desen([L.potrivit(u"".join(c for c in u"%s" % continut if c != "."), dreapta=True)])
		return Desen([m])
	if fel == "bara":
		return Desen([L.bara(continut)])
	if fel == "inel":
		cadre = L.inel()
		return Desen(cadre, [max(100, viteza // 2)] * len(cadre), bucla=True)
	if fel == "sageti":
		return _sageti(continut, viteza)
	if fel == "alternat":
		cadre = [L.potrivit(t) for t in continut or []]
		if not cadre:
			return None
		if len(cadre) == 1:
			return Desen(cadre)
		return Desen(cadre, [ALTERNAT_MS] * len(cadre), bucla=True)
	if fel == "secventa":
		cadre, durate = [], []
		for sub_fel, sub_continut, ms in continut or []:
			d = deseneaza((sub_fel, sub_continut), viteza, False)
			if d is None:
				continue
			if d.fix():
				cadre.append(d.cadre[0])
				durate.append(ms or ALTERNAT_MS)
			else:
				cadre.extend(d.cadre)
				durate.extend(d.durate)
		if not cadre:
			return None
		return Desen(cadre, durate, derulat=len(cadre) > 1)
	return None


def pereche(d, f, valoare):
	"""Formatul `f` al datei `d` aplicat valorii: (fel, continut) sau None. Nu arunca."""
	if valoare is None:
		return None
	try:
		return f.fa(valoare)
	except Exception as e:
		_jurnal("%s:%s: %r" % (d.id, f.id, e))
		return None


def desenExemplu(d, f, viteza=VITEZA_IMPLICITA_MS, singur=False):
	"""Desenul valorii de exemplu (previzualizarea cand valoarea de acum lipseste)."""
	return deseneaza(pereche(d, f, exemplu(d, f)), viteza, singur)


def notaCost(d):
	"""Cat costa citirea datei, pe intelesul omului (nota de pe televizor si din pagina web), sau ""."""
	if d.cost == TUNER:
		return _("Citită din tuner la %d s, numai cât se vede pe afișaj.") % d.perioada
	if d.cost == FIR:
		return _("Citită separat, fără să încetinească receptorul.")
	return u""


def areEticheta(d, f):
	"""Formatul poate primi eticheta scurta inainte („+e”): data are una, iar formatul nu o scrie deja (de ex. „CPU 37%”
	are CPU in el)."""
	scurt = SCURT.get(d.id)
	if not scurt:
		return False
	p = pereche(d, f, exemplu(d, f))
	if p and p[0] in ("fix", "dreapta", "derulat") and L.transcrie(u"%s" % (p[1],)).strip().upper().startswith(scurt):
		return False
	return True


def citeste(d, ctx):
	"""Valoarea de acum a unei date (sau un Lucru pentru firul afisajului); None cand nu e nimic de aratat."""
	if d.citeste is None:
		return None
	try:
		return d.citeste(ctx)
	except Exception as e:
		_jurnal("%s: %r" % (d.id, e))
		return None

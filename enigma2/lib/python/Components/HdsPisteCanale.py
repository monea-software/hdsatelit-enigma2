# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPisteCanale - baza pistelor fiecarui canal (limbile, formatul si canalele sunetului, subtitrarile DVB si
# teletext, teletextul, HbbTV), pentru cautarea de canale (Screens/HdsCautareCanale.py, pagina web /cautare).
# Cautarea poate cere canalele cu teletext, subtitrari DVB, o limba a sunetului sau a subtitrarii, HbbTV, un format
# de sunet (MPEG, AAC, AC3, AC3+, DTS), sunet mono, stereo sau pe mai multe canale si numarul pistelor de sunet.
#
# DE UNDE SE IAU PISTELE
#   1. canalul care ruleaza, prin nucleu: audioTracks() (limba, felul), subtitle().getSubtitleList() (DVB si pagini de
#      teletext), info sTXTPID (teletext) - exact ce da eDVBServicePMTHandler::getProgramInfo (lib/dvb/pmt.cpp); HbbTV
#      din AIT-ul citit de nucleu (sAITPID, sHBBTVAit; Components/HdsHbbtv.hb_din_stare): 1 numai cu o aplicatie de
#      pornit in AIT, 0 numai cand PMT-ul nu are AIT HbbTV, altfel nimic (ramane ce stia baza);
#   2. PMT-ul brut, citit din Python direct din demux (filtru de sectiune, ca eDVBSectionReader din lib/dvb/demux.cpp):
#      PAT-ul transponderului, apoi PMT-ul fiecarui serviciu de pe el. Asa se afla HbbTV-ul anuntat in PMT (ES cu
#      stream_type 0x05 si descriptorul 0x6F, application_signalling) si PID-ul AIT (grupa pmt a bazei, cu PID-ul PMT
#      si PCR-ul) pentru canalele neprivite, si pistele tuturor canalelor de pe transponder, fara nicio schimbare de
#      canal;
#   3. lamedb: c:02 (cTPID) = canalul are teletext (se foloseste in Components/HdsIndexCanale.py).
#
# BAZA: /etc/enigma2/hds_piste_canale.json, scrisa atomic (temporar + fsync + os.replace), cel mult o data la 30 s si
# numai daca s-a schimbat ceva. {"v": 1, "actualizat": <secunde>, "c": {cheie: inregistrare}}; cheia e cea din
# HdsIndexCanale.cheie_din_ref („sid:ns:tsid:onid”). Inregistrarea:
#   "t": data culegerii, "s": "v" (prin nucleu) sau "p" (PMT brut),
#   "a": [[limbile, felul, descriere audio 0/1]], "d": [[limba, surzi 0/1]], "x": [[limba, pagina, surzi 0/1]],
#   "tt": teletext 1/0, "hb": HbbTV 1/0. O cheie lipsa = nu se stie.
#   Felul e formatul pistei („MPEG”, „AC3”, „AC3+”, „AAC”, „AAC-HE”, „DTS”...), urmat, cand PMT-ul sau EIT-ul il spun, de
#   asezarea canalelor dupa un spatiu: „AC3 5.1”, „MPEG 2.0”; vezi ASEZARI. La vizionare asezarea vine si din EIT
#   (component_descriptor-ii emisiunii de acum, asezarea_din_eit), fara nicio citire din demux. Baza unica tine pista pe patru campuri (limba, fel,
#   descriere, PID), deci asezarea sta in fel; nucleul nu o stie, iar din_serviciu o pastreaza din baza (fara ea,
#   fiecare vizionare ar sterge-o si fiecare citire a PMT-ului ar pune-o la loc: doua scrieri pe disc fara rost).
# Un fisier care nu s-a putut citi nu e scris peste (Components/HdsFisierSigur.py): eroare de citire = numai citire
# pana la o citire buna (memoria se uneste atunci peste fisier); JSON stricat = pus deoparte ca .stricat-AAAALLZZ
# inaintea primei scrieri; v mai mare sau fisier prea mare = numai citire.
# BAZA UNICA: baza() da acum adaptorul BazaUnica peste Components/HdsBazaCanale.py (grupele pi si hb, un rand pe
# canal, desfacut la cerere); clasa Baza si fisierul de mai sus raman pentru migrare (citite fara scriere) si pentru
# cazul in care baza unica nu se incarca. Culegerea la vizionare o face Components/HdsCulegereCanale.py (subclasa a
# lui Culegator de mai jos, cu aceeasi citire bruta a transponderului).
#
# PARTEA DE SUS E CURATA (fara enigma): baza, analiza PAT/PMT, unirea si cautarea se probeaza pe PC
# (test_piste_canale.py). Ce atinge nucleul (demuxul, navigatia,
# ceasurile) sta in clase care primesc aceste lucruri din afara, cu importuri tarzii.

from __future__ import absolute_import

import errno
import json
import os
import struct
import time

try:
	from Components import HdsIndexCanale as _X
	from Components import HdsFisierSigur as _S
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsIndexCanale as _X
	import HdsFisierSigur as _S

CALE = "/etc/enigma2/hds_piste_canale.json"
VERSIUNE = 1
MAX_CANALE = 20000
MAX_OCTETI = 8 * 1024 * 1024
MAX_PISTE = 16            # piste audio sau subtitrari tinute pe un canal
MAX_TEXT = 12             # limbile unei piste („deu/eng”) si felul („AAC-HE”)
PROASPAT_S = 7 * 86400    # o culegere la fel ca cea tinuta nu mai scrie nimic pe disc, daca nu e mai veche de atat

ADAPTOR = 0               # /dev/dvb/adapter0 (demux.cpp 84)


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


def _jurnal(text):
	print("[HdsPisteCanale] %s" % text)


# ------------------------------------------------------------------ limbile (codurile din HdsPisteLimbi)

_LIMBI = []


def _modulLimbi():
	if not _LIMBI:
		try:
			from Components import HdsPisteLimbi as L
		except ImportError:
			try:
				import HdsPisteLimbi as L
			except ImportError:
				L = None
		_LIMBI.append(L)
	return _LIMBI[0]


def _text(valoare):
	if valoare is None:
		return u""
	if isinstance(valoare, bytes):
		try:
			return valoare.decode("utf-8")
		except UnicodeDecodeError:
			return valoare.decode("latin-1")
	return u"%s" % (valoare,)


def limbi_din_text(text):
	"""„rum”, „ron”, „deu/eng”, „Deutsch”, „Română”, „und” -> ["ron"], ["deu", "eng"], [] (coduri ISO 639-2/T canonice,
	cum le recunoaste HdsPisteLimbi.limbiDinText, deci „rum”, „ro” si „Română” dau toate „ron”)."""
	L = _modulLimbi()
	if L is not None:
		try:
			return list(L.limbiDinText(text))[:4]
		except Exception:
			pass
	t = _text(text).strip().lower()
	return [t] if len(t) == 3 and t.isalpha() and t not in ("und", "mul", "zxx", "qaa") else []


def cod_limba(text):
	"""Textul limbii unei piste -> „ron”, „deu/eng” sau „” (nu se stie)."""
	return "/".join(limbi_din_text(text))[:MAX_TEXT]


def este_descriere_audio(text):
	L = _modulLimbi()
	if L is not None:
		try:
			return bool(L.esteDescriereAudio(text))
		except Exception:
			pass
	return False


def nume_limba(cod):
	"""„ron” -> „Română” (numele traduse din HdsPisteLimbi.numeLimba); pe PC, fara traduceri, numele englezesc."""
	L = _modulLimbi()
	if L is not None:
		try:
			return L.numeLimba(cod)
		except Exception:
			pass
		for c, nume in getattr(L, "LIMBI_MENIU", ()):
			if c == cod:
				return nume
	return (cod or u"").upper()


def limba_in_filtre(cod):
	"""Limba intra in filtrele cautarii (HdsPisteLimbi.limbaInFiltre: nu cele disparute, inventate, jargoanele si
	grupele de limbi, care apar pe sateliti numai din greseala); fara tabel, toate."""
	L = _modulLimbi()
	f = getattr(L, "limbaInFiltre", None) if L is not None else None
	return f(cod) if f is not None else bool(cod)


def limba_receptor():
	L = _modulLimbi()
	if L is not None:
		try:
			return L.limbaReceptor()
		except Exception:
			pass
	return None


# ------------------------------------------------------------------ inregistrarea unui canal (curata)

FELURI_AUDIO = ("MPEG", "AC3", "AC3+", "AAC", "AAC-HE", "DTS", "DTS-HD", "LPCM", "AC4")
MAX_FEL = 20              # felul cu asezarea canalelor („AAC-HE 1+1”); baza unica tine 32 de caractere

# asezarea canalelor unei piste, scrisa numai cand PMT-ul o spune sigur: „1.0” mono, „1+1” doua programe mono,
# „2.0” stereo, „MC” mai mult de doua canale fara numarul exact (AC-3 / E-AC-3 „multichannel”, AAC „surround”),
# „<canale>.<LFE>” numarul exact (DTS: „5.1” = cinci canale plus LFE)
ASEZARI = frozenset(["1.0", "1+1", "2.0", "MC"] + ["%d.%d" % (n, l) for n in range(3, 9) for l in (0, 1)])

# formatele sunetului pentru cautare (Components/HdsIndexCanale.py, randul „Format sunet”), dupa felul pistei
FORMATE_SUNET = ("mpeg", "aac", "ac3", "eac3", "dts", "alt")


def desparte_fel(fel):
	"""„AC3 5.1” -> („AC3”, „5.1”); „AC3” -> („AC3”, „”); un ultim cuvant care nu e o asezare ramane in format
	(„MPEG-4 AAC” -> („MPEG-4 AAC”, „”))."""
	t = _text(fel).strip()
	if u" " in t:
		cod, rest = t.rsplit(u" ", 1)
		if rest.upper() in ASEZARI:
			return cod.strip(), rest.upper()
	return t, u""


def fel_cu_asezare(cod, asezare):
	return (u"%s %s" % (cod, asezare)) if asezare else cod


def format_sunet(fel):
	"""Felul pistei (numele din nucleu, din PMT sau din GStreamer) -> una din FORMATE_SUNET, sau None (nu se stie)."""
	t = desparte_fel(fel)[0].upper().replace(u"-", u"").replace(u" ", u"")
	if not t or t == u"???":
		return None
	if u"AC3+" in t or u"EAC3" in t or u"DDP" in t or u"DOLBYDIGITALPLUS" in t:
		return "eac3"
	if u"AC3" in t:
		return "ac3"
	if u"DTS" in t:
		return "dts"
	if u"AAC" in t:
		return "aac"
	if u"MPEG" in t or u"MP2" in t or u"MP3" in t:
		return "mpeg"
	return "alt"


def mod_sunet(asezare):
	"""Asezarea canalelor -> „mono”, „stereo”, „multi” (mai mult de doua canale) sau None (nu se stie)."""
	if asezare in ("1.0", "1+1"):
		return "mono"
	if asezare == "2.0":
		return "stereo"
	if asezare in ASEZARI:
		return "multi"
	return None


def _intreg01(v):
	return 1 if v in (1, True, "1") else 0


def _cod(v):
	t = _text(v).strip().lower()[:MAX_TEXT]
	return t if all(c.isalpha() or c == "/" for c in t) else u""


def curata(rec):
	"""O inregistrare venita din fisier sau din culegere -> forma sigura (numai campurile cunoscute, taiate), sau
	None daca nu spune nimic."""
	if not isinstance(rec, dict):
		return None
	rez = {}
	try:
		t = int(rec.get("t") or 0)
	except (TypeError, ValueError):
		t = 0
	if t > 0:
		rez["t"] = t
	if rec.get("s") in ("v", "p"):
		rez["s"] = rec["s"]
	if isinstance(rec.get("a"), list):
		a = []
		for p in rec["a"][:MAX_PISTE]:
			if isinstance(p, (list, tuple)) and len(p) >= 2:
				fel = _text(p[1]).strip().upper()[:MAX_FEL]
				a.append([_cod(p[0]), fel, _intreg01(p[2] if len(p) > 2 else 0)])
		rez["a"] = a
	if isinstance(rec.get("d"), list):
		d = []
		for p in rec["d"][:MAX_PISTE]:
			if isinstance(p, (list, tuple)) and len(p) >= 1:
				d.append([_cod(p[0]), _intreg01(p[1] if len(p) > 1 else 0)])
		rez["d"] = d
	if isinstance(rec.get("x"), list):
		x = []
		for p in rec["x"][:MAX_PISTE]:
			if isinstance(p, (list, tuple)) and len(p) >= 2:
				pagina = _text(p[1]).strip()[:4]
				if not pagina.isalnum():
					pagina = u""
				x.append([_cod(p[0]), pagina, _intreg01(p[2] if len(p) > 2 else 0)])
		rez["x"] = x
	for k in ("tt", "hb"):
		if rec.get(k) in (0, 1, True, False):
			rez[k] = int(bool(rec[k]))
	if not any(k in rez for k in ("a", "d", "x", "tt", "hb")):
		return None
	return rez


_CONTINUT = ("a", "d", "x", "tt", "hb")


def acelasi_continut(a, b):
	"""Aceleasi piste (fara data si sursa)?"""
	if not a or not b:
		return False
	return all(a.get(k) == b.get(k) for k in _CONTINUT)


def uneste(vechi, nou):
	"""Culegerea noua peste ce era: campurile aduse de cea noua le inlocuiesc pe cele vechi, cele pe care cea noua nu le
	stie raman (de ex. HbbTV citit ieri din PMT ramane cand azi s-a putut citi numai prin nucleu)."""
	if not vechi:
		return dict(nou)
	rez = dict(vechi)
	for k, v in nou.items():
		rez[k] = v
	return rez


def are_teletext(rec):
	return bool(rec) and (rec.get("tt") == 1 or bool(rec.get("x")))


def are_sub_dvb(rec):
	return bool(rec) and bool(rec.get("d"))


def are_sub_ttx(rec):
	return bool(rec) and bool(rec.get("x"))


def are_hbbtv(rec):
	return bool(rec) and rec.get("hb") == 1


def _limbiLista(lista):
	rez = []
	for p in lista or ():
		for l in (p[0] or u"").split("/"):
			if l and l not in rez:
				rez.append(l)
	return rez


def limbi_sunet(rec):
	return _limbiLista((rec or {}).get("a"))


def limbi_subtitrare(rec, feluri=("dvb", "ttx")):
	rez = []
	if "dvb" in feluri:
		rez.extend(_limbiLista((rec or {}).get("d")))
	if "ttx" in feluri:
		for l in _limbiLista((rec or {}).get("x")):
			if l not in rez:
				rez.append(l)
	return rez


def sunet_piste(rec):
	"""(formatele sunetului, felurile mono / stereo / multi, numarul pistelor de sunet sau None cand pistele de sunet nu
	se stiu). Formatele si felurile numai din ce se stie: o pista fara asezare nu da niciun fel."""
	a = (rec or {}).get("a")
	if not isinstance(a, list):
		return frozenset(), frozenset(), None
	formate, moduri = set(), set()
	for p in a:
		cod, asezare = desparte_fel(p[1] if len(p) > 1 else u"")
		f = format_sunet(cod)
		if f:
			formate.add(f)
		m = mod_sunet(asezare)
		if m:
			moduri.add(m)
	return frozenset(formate), frozenset(moduri), len(a)


def trasaturi(rec):
	"""Ce foloseste indexul cautarii (HdsIndexCanale.Index.aplica_piste): (optiunile randului „Are”, teletextul e stiut,
	limbile sunetului, limbile subtitrarilor DVB, limbile paginilor de subtitrare teletext, sunet_piste(rec))."""
	are = set()
	if are_teletext(rec):
		are.add("ttx")
	if are_sub_dvb(rec):
		are.add("subdvb")
	if are_sub_ttx(rec):
		are.add("subttx")
	if are_hbbtv(rec):
		are.add("hbbtv")
	return (frozenset(are), "tt" in rec or bool(rec.get("x")), tuple(l for l in limbi_sunet(rec) if limba_in_filtre(l)),
		tuple(l for l in limbi_subtitrare(rec, ("dvb",)) if limba_in_filtre(l)),
		tuple(l for l in limbi_subtitrare(rec, ("ttx",)) if limba_in_filtre(l)), sunet_piste(rec))


def _limbaIn(dorite, limbi):
	if dorite is None:
		return True
	if isinstance(dorite, str):
		dorite = (dorite,)
	return any(l in limbi for l in dorite)


def potriveste(rec, teletext=None, sub_dvb=None, sub_ttx=None, hbbtv=None, sunet=None, subtitrare=None, fel_sub=None):
	"""Cautarea pe o inregistrare. Conditiile date se aduna (SI); None = nu conteaza. sunet / subtitrare: un cod sau o
	lista de coduri (SAU). fel_sub: „dvb”, „ttx” sau None (limba subtitrarii cautata in oricare fel)."""
	if not rec:
		return False
	for cerut, are in ((teletext, are_teletext), (sub_dvb, are_sub_dvb), (sub_ttx, are_sub_ttx), (hbbtv, are_hbbtv)):
		if cerut is not None and bool(cerut) != are(rec):
			return False
	if sunet is not None and not _limbaIn(sunet, limbi_sunet(rec)):
		return False
	if subtitrare is not None:
		feluri = (fel_sub,) if fel_sub in ("dvb", "ttx") else ("dvb", "ttx")
		if not _limbaIn(subtitrare, limbi_subtitrare(rec, feluri)):
			return False
	return True


def _numeLimbi(text):
	coduri = [c for c in (text or u"").split("/") if c]
	return u"/".join(nume_limba(c) for c in coduri) if coduri else _("limbă necunoscută")


def text_asezare(asezare):
	"""Asezarea canalelor pentru om: „mono”, „stereo”, „multicanal”, „5.1”; „” cand nu se stie."""
	if asezare == "1.0":
		return _("mono")
	if asezare == "1+1":
		return _("mono dublu")
	if asezare == "2.0":
		return _("stereo")
	if asezare == "MC":
		return _("multicanal")
	return asezare or u""


def text_fel(fel):
	"""„AC3 5.1” -> „AC3 5.1”, „MPEG 2.0” -> „MPEG stereo”, „AAC MC” -> „AAC multicanal”."""
	cod, asezare = desparte_fel(fel)
	return (cod + u" " + text_asezare(asezare)).strip() if asezare else cod


def rezumat(rec):
	"""Pentru om (pagina web, ecranul): {"sunet": ["Română MPEG", ...], "dvb": [...], "teletext": bool, "ttx": [...],
	"hbbtv": True/False/None, "data": secunde}."""
	rec = rec or {}
	sunet = []
	for limbi, fel, descriere in rec.get("a") or ():
		t = _numeLimbi(limbi)
		if fel:
			t += u" " + text_fel(fel)
		if descriere:
			t += u" (" + _("descriere audio") + u")"
		sunet.append(t)
	dvb = [_numeLimbi(l) + (u" (" + _("pentru surzi") + u")" if s else u"") for l, s in rec.get("d") or ()]
	ttx = [_numeLimbi(l) + (u" " + p if p else u"") + (u" (" + _("pentru surzi") + u")" if s else u"")
		for l, p, s in rec.get("x") or ()]
	return {
		"sunet": sunet, "dvb": dvb, "ttx": ttx,
		"teletext": are_teletext(rec) if ("tt" in rec or rec.get("x")) else None,
		"hbbtv": (rec.get("hb") == 1) if "hb" in rec else None,
		"data": rec.get("t") or 0,
	}


# ------------------------------------------------------------------ baza (fisierul)

class Baza(object):
	"""{cheie: inregistrare}; fisierul se citeste o singura data (din nou numai dupa o citire nereusita) si se scrie
	atomic, numai cand s-a schimbat ceva. `versiune` creste la fiecare schimbare (indexul cautarii stie asa cand trebuie
	sa refaca filtrele)."""

	def __init__(self, cale=CALE, monoton=None, ceas=None):
		self.cale = cale
		self.date = None
		self.murdar = False
		self.versiune = 0
		self.actualizat = 0
		self._trasaturi = (None, None)
		self._uitate = set()        # cheile uitate de la ultima scriere, ca unirea cu discul sa nu le aduca inapoi
		self._uitat_tot = False
		self.fisier = _S.FisierJson(cale, MAX_OCTETI, VERSIUNE, jurnal=_jurnal, monoton=monoton, ceas=ceas)

	def toate(self):
		if self.date is None:
			self.date = self._citeste()
		elif self.fisier.la_timp():
			self._reciteste()
		return self.date

	def _citeste(self):
		"""-> {cheie: inregistrare}; gol si la o citire nereusita (starea ei ramane in self.fisier)."""
		j = self.fisier.citeste()
		if j is None:
			return {}
		if not isinstance(j.get("c"), dict):
			self.fisier.stricat("\"c\" nu e un obiect")
			return {}
		try:
			self.actualizat = int(j.get("actualizat") or 0)
		except (TypeError, ValueError):
			self.actualizat = 0
		rez = {}
		for k, v in list(j["c"].items())[-MAX_CANALE:]:
			if not isinstance(k, str) or not k or len(k) > 300:
				continue
			r = curata(v)
			if r is not None:
				rez[k] = r
		return rez

	def _reciteste(self):
		"""O citire noua; numai daca reuseste, culegerile din memorie se unesc peste fisier (campurile lor castiga,
		cele pe care nu le stiu raman de pe disc)."""
		actualizat = self.actualizat
		disc = self._citeste()
		if self.fisier.stare != _S.CITIT:
			self.actualizat = actualizat
			return
		if self._uitat_tot:
			disc = {}
		for k in self._uitate:
			disc.pop(k, None)
		self.date = _S.uneste_peste(disc, self.date or {}, MAX_CANALE, uneste)
		self.actualizat = max(actualizat, self.actualizat)
		self.versiune += 1

	def inregistrare(self, cheie):
		return self.toate().get(cheie)

	def numar(self):
		return len(self.toate())

	def noteaza(self, cheie, rec, cand=None, sursa=None):
		"""O culegere noua pentru un canal. -> True daca baza s-a schimbat (atunci trebuie scrisa)."""
		if not cheie:
			return False
		nou = curata(rec)
		if nou is None:
			return False
		cand = int(cand if cand is not None else time.time())
		date = self.toate()
		vechi = date.get(cheie)
		unit = uneste(vechi, nou)
		unit.pop("t", None)
		if sursa in ("v", "p"):
			unit["s"] = sursa
		if vechi is not None and acelasi_continut(vechi, unit) and cand - (vechi.get("t") or 0) < PROASPAT_S:
			return False
		unit["t"] = cand
		if vechi is not None:
			del date[cheie]          # la sfarsit: cele vazute de curand raman cand lista se taie
		date[cheie] = unit
		while len(date) > MAX_CANALE:
			del date[next(iter(date))]
		self.murdar = True
		self.versiune += 1
		self.actualizat = cand
		return True

	def uita(self, cheie=None):
		date = self.toate()
		# fisierul inca necitit (sau de pus deoparte): ce e pe disc nu e in memorie, deci uitarea se tine minte
		nevazut = self.fisier.stare not in _S.SE_SCRIE
		if cheie is None:
			if not date and not nevazut:
				return False
			date.clear()
			self._uitat_tot = True
			self._uitate.clear()
		else:
			if date.pop(cheie, None) is None and not nevazut:
				return False
			self._uitate.add(cheie)
		self.murdar = True
		self.versiune += 1
		return True

	def salveaza(self):
		if not self.murdar or self.date is None:
			return False
		if not self.fisier.poate_scrie(self._reciteste):
			return False
		director = os.path.dirname(self.cale) or "."
		tmp = "%s.tmp%d" % (self.cale, os.getpid())
		try:
			if not os.path.isdir(director):
				os.makedirs(director)
			corp = json.dumps({"v": VERSIUNE, "actualizat": self.actualizat, "c": self.date}, separators=(",", ":"),
				ensure_ascii=True)
			with open(tmp, "wb") as f:
				f.write(corp.encode("utf-8"))
				f.flush()
				try:
					os.fsync(f.fileno())
				except OSError:
					pass
			os.replace(tmp, self.cale)
			self.fisier.scris()
		except (IOError, OSError) as e:
			_jurnal("nu am putut scrie %s: %s" % (self.cale, e))
			try:
				os.remove(tmp)
			except OSError:
				pass
			return False
		self.murdar = False
		self._uitate.clear()
		self._uitat_tot = False
		return True

	def trasaturi(self):
		"""{cheie: trasaturi(rec)}, refacut numai cand baza s-a schimbat."""
		versiune, rez = self._trasaturi
		if versiune != self.versiune or rez is None:
			rez = dict((k, trasaturi(r)) for k, r in self.toate().items())
			self._trasaturi = (self.versiune, rez)
		return rez

	def cauta(self, **conditii):
		"""Cheile canalelor care indeplinesc conditiile (vezi potriveste)."""
		return [k for k, r in self.toate().items() if potriveste(r, **conditii)]

	def agregat(self):
		"""Cate canale au fiecare lucru: {"canale", "teletext", "sub_dvb", "sub_ttx", "hbbtv", "hbbtv_stiut",
		"sunet": {limba: n}, "subtitrare": {limba: n}}."""
		rez = {"canale": 0, "teletext": 0, "sub_dvb": 0, "sub_ttx": 0, "hbbtv": 0, "hbbtv_stiut": 0,
			"sunet": {}, "subtitrare": {}}
		for r in self.toate().values():
			rez["canale"] += 1
			rez["teletext"] += are_teletext(r)
			rez["sub_dvb"] += are_sub_dvb(r)
			rez["sub_ttx"] += are_sub_ttx(r)
			rez["hbbtv"] += are_hbbtv(r)
			rez["hbbtv_stiut"] += "hb" in r
			for l in limbi_sunet(r):
				rez["sunet"][l] = rez["sunet"].get(l, 0) + 1
			for l in limbi_subtitrare(r):
				rez["subtitrare"][l] = rez["subtitrare"].get(l, 0) + 1
		return rez


def inregistrare_din_rand(rec):
	"""Un rand din baza unica (Components/HdsBazaCanale.py) -> inregistrarea de aici (forma lui curata): a, d, x fara
	PID-ul pistei, tt si hb, "t" = data cea mai noua a grupelor pi si hb, "s" = sursa ei ("v" sau "p"); sau None."""
	if not rec:
		return None
	nou = {}
	if isinstance(rec.get("a"), list):
		nou["a"] = [p[:3] for p in rec["a"] if isinstance(p, list)]
	if isinstance(rec.get("d"), list):
		nou["d"] = [p[:2] for p in rec["d"] if isinstance(p, list)]
	if isinstance(rec.get("x"), list):
		nou["x"] = [p[:3] for p in rec["x"] if isinstance(p, list)]
	for k in ("tt", "hb"):
		if k in rec:
			nou[k] = rec[k]
	t, s = 0, None
	vf = rec.get("vf") if isinstance(rec.get("vf"), dict) else {}
	for grupa in ("pi", "hb"):
		v = vf.get(grupa)
		if isinstance(v, list) and len(v) >= 2 and isinstance(v[0], int) and not isinstance(v[0], bool) and v[0] >= t:
			t, s = v[0], v[1]
	nou["t"] = t
	if s in ("v", "p"):
		nou["s"] = s
	return curata(nou)


# grupele bazei unice din care vin inregistrarile de aici
_GRUPE_BAZA = ("pi", "hb")


def _trasaturi_din_rand(rec):
	r = inregistrare_din_rand(rec)
	return trasaturi(r) if r is not None else None


class BazaUnica(object):
	"""Adaptorul bazei pistelor peste baza unica (Components/HdsBazaCanale.py, grupele pi si hb), cu metodele pe care
	le folosesc apelantii clasei Baza (afisajul, cautarea, pagina web, culegerea, „Actualizeaza”). Nu tine baza in
	memorie: toate() si trasaturi() sunt priviri care desfac randul cerut. `versiune` se schimba numai cu pistele si
	HbbTV (versiune_grupe), ca indexul cautarii sa nu refaca pistele la o schimbare a accesului sau a imaginii.
	Scrierea pe disc e a bazei: salveaza() o cere la prag (pragul si bugetul zilei); numai sfarsitul unei treceri
	„Actualizeaza” cere, prin salveaza_actualizare(), scrierea care nu asteapta pragul."""

	def __init__(self, B, b=None):
		self._B = B
		self._b = b
		self._inregistrari = None
		self._trasaturi = None

	def _baza(self):
		if self._b is None:
			self._b = self._B.baza()
		return self._b

	@property
	def versiune(self):
		return self._baza().versiune_grupe(_GRUPE_BAZA)

	@property
	def murdar(self):
		return self._baza().murdar()

	@property
	def actualizat(self):
		"""Data cea mai noua a pistelor si a HbbTV din baza (0 daca nu se stie), ca la clasa Baza."""
		return self._baza().data_max_grupe(_GRUPE_BAZA)

	def toate(self):
		"""{cheie: inregistrare}, ca privire (randul desfacut la cerere)."""
		if self._inregistrari is None:
			self._inregistrari = self._B.Vedere(self._baza(), inregistrare_din_rand, _CONTINUT, _GRUPE_BAZA)
		return self._inregistrari

	def inregistrare(self, cheie):
		return self.toate().get(cheie) if cheie else None

	def numar(self):
		return len(self.toate())

	def noteaza(self, cheie, rec, cand=None, sursa=None):
		"""O culegere noua pentru un canal. -> True daca baza s-a schimbat."""
		if not cheie:
			return False
		nou = curata(rec)
		if nou is None:
			return False
		grupe = {}
		pi = dict((k, nou[k]) for k in ("a", "d", "x", "tt") if k in nou)
		if pi:
			grupe["pi"] = pi
		if "hb" in nou:
			grupe["hb"] = nou["hb"]
		pmt = _pmt_brut(rec)
		if pmt is not None:
			grupe["pmt"] = pmt
		if not grupe:
			return False
		if sursa not in ("v", "p"):
			sursa = nou.get("s") or "v"
		return self._baza().actualizeaza(cheie, grupe, sursa, cand)

	def salveaza(self, motiv=None):
		"""Scrierea la prag (culegerea de dinainte, cand cea unita nu porneste): pragul si bugetul zilei."""
		return self._baza().salveaza(motiv or self._B.PRAG)

	def salveaza_actualizare(self):
		"""Sfarsitul unei treceri „Actualizeaza”: scrierea nu asteapta pragul (se numara in bugetul zilei)."""
		return self._baza().salveaza(self._B.ACTUALIZARE)

	def trasaturi(self):
		"""{cheie: trasaturi(inregistrare)}, ca privire; `versiune` e a bazei."""
		if self._trasaturi is None:
			self._trasaturi = self._B.Vedere(self._baza(), _trasaturi_din_rand, _CONTINUT, _GRUPE_BAZA)
		return self._trasaturi

	def cauta(self, **conditii):
		return [k for k, r in self.toate().items() if potriveste(r, **conditii)]

	def agregat(self):
		rez = {"canale": 0, "teletext": 0, "sub_dvb": 0, "sub_ttx": 0, "hbbtv": 0, "hbbtv_stiut": 0,
			"sunet": {}, "subtitrare": {}}
		for _k, r in self.toate().items():
			rez["canale"] += 1
			rez["teletext"] += are_teletext(r)
			rez["sub_dvb"] += are_sub_dvb(r)
			rez["sub_ttx"] += are_sub_ttx(r)
			rez["hbbtv"] += are_hbbtv(r)
			rez["hbbtv_stiut"] += "hb" in r
			for l in limbi_sunet(r):
				rez["sunet"][l] = rez["sunet"].get(l, 0) + 1
			for l in limbi_subtitrare(r):
				rez["subtitrare"][l] = rez["subtitrare"].get(l, 0) + 1
		return rez


def _pmt_brut(rec):
	"""Grupa pmt adusa de citirea bruta a PMT-ului (CititorTransponder: [PID PMT, PCR, -1, -1, -1, AIT]), verificata,
	sau None. Clasa Baza (fisierul de dinainte) nu o tine: curata() o scoate."""
	v = rec.get("pmt") if isinstance(rec, dict) else None
	if not isinstance(v, (list, tuple)) or len(v) != 6:
		return None
	numar = lambda x: isinstance(x, int) and not isinstance(x, bool)  # noqa: E731
	if not numar(v[0]) or not 0 < v[0] < 0x1FFF:
		return None
	rez = [x if numar(x) and 0 < x < 0x1FFF else -1 for x in v[:5]]
	return rez + [v[5] if numar(v[5]) and 0 <= v[5] < 0x1FFF else -1]


_BAZA = []


def baza():
	"""Baza comuna a imaginii (ecranul, culegatorul, pagina web): adaptorul peste baza unica; clasa Baza (fisierul
	de dinainte) numai daca baza unica nu se incarca."""
	if not _BAZA:
		try:
			try:
				from Components import HdsBazaCanale as B
			except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
				import HdsBazaCanale as B
			_BAZA.append(BazaUnica(B))
		except Exception as e:
			_jurnal("baza unica: %s; baza pistelor de dinainte" % e)
			_BAZA.append(Baza())
	return _BAZA[0]


# ------------------------------------------------------------------ PAT si PMT (curat)

def _tabelCrc():
	tabel = []
	for i in range(256):
		c = i << 24
		for _k in range(8):
			c = ((c << 1) ^ 0x04C11DB7) if c & 0x80000000 else (c << 1)
		tabel.append(c & 0xFFFFFFFF)
	return tabel


_CRC = _tabelCrc()


def crc32_mpeg(date):
	"""CRC-32/MPEG-2 (polinomul 0x04C11DB7, pornit din 0xFFFFFFFF). Peste o sectiune intreaga, cu CRC-ul ei, da 0."""
	c = 0xFFFFFFFF
	for b in bytearray(date):
		c = ((c << 8) & 0xFFFFFFFF) ^ _CRC[((c >> 24) ^ b) & 0xFF]
	return c


def sectiune(date):
	"""Octetii cititi din demux -> sectiunea intreaga (cu CRC bun), sau None."""
	b = bytes(date or b"")
	if len(b) < 12:
		return None
	lungime = ((b[1] & 0x0F) << 8) | b[2]
	if lungime < 9 or 3 + lungime > len(b):
		return None
	s = b[:3 + lungime]
	if not (b[1] & 0x80) or crc32_mpeg(s) != 0:
		return None
	return s


def antet_sectiune(s):
	"""(table_id, table_id_extension, section_number, last_section_number)"""
	return s[0], (s[3] << 8) | s[4], s[6], s[7]


def citeste_pat(s):
	"""Sectiunea PAT -> {"tsid", "programe": {numarul programului: PID-ul PMT}} (programul 0 = NIT, scos), sau None."""
	s = sectiune(s)
	if s is None or s[0] != 0x00:
		return None
	programe = {}
	i, sfarsit = 8, len(s) - 4
	while i + 4 <= sfarsit:
		program = (s[i] << 8) | s[i + 1]
		pid = ((s[i + 2] & 0x1F) << 8) | s[i + 3]
		if program:
			programe[program] = pid
		i += 4
	return {"tsid": (s[3] << 8) | s[4], "programe": programe}


def _descriptori(b, i, sfarsit):
	"""(tag, octetii) pentru fiecare descriptor dintre i si sfarsit."""
	rez = []
	while i + 2 <= sfarsit:
		tag, lung = b[i], b[i + 1]
		if i + 2 + lung > sfarsit:
			break
		rez.append((tag, b[i + 2:i + 2 + lung]))
		i += 2 + lung
	return rez


def _limbaIso(octeti):
	try:
		return cod_limba(bytes(octeti[:3]).decode("latin-1"))
	except Exception:
		return u""


# felul sunetului, pe numele pe care le da si nucleul (servicedvb.cpp 1807-1822)
_AUDIO_TIP_FLUX = {0x03: "MPEG", 0x04: "MPEG", 0x0F: "AAC", 0x11: "AAC-HE", 0x81: "AC3", 0x87: "AC3+"}
_AUDIO_DESCRIPTOR = {0x6A: "AC3", 0x7A: "AC3+", 0x7B: "DTS", 0x7C: "AAC-HE"}
_VIDEO_TIP_FLUX = frozenset((0x01, 0x02, 0x10, 0x1B, 0x24, 0x27, 0x42, 0xEA))

# EN 300 468, tabelul D.5: bitii b2-b0 din component_type (AC-3 0x6A si E-AC-3 0x7A); 6 = mai multe programe in
# substreamuri independente, 7 = rezervat: nu spun asezarea
_ASEZARE_AC3 = {0: "1.0", 1: "1+1", 2: "2.0", 3: "2.0", 4: "MC", 5: "MC"}
# tabelul G.4: surround_mode (AMODE) -> numarul canalelor principale; 1 si 10-63 nu au o asezare stiuta in DVB
_CANALE_DTS = {0: 1, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4, 9: 5}
# tabelul 26 (stream_content 0x06), folosit de AAC_type: 0x01 mono, 0x03 stereo, 0x05 surround, 0x43 HE-AAC v2 stereo
_ASEZARE_AAC = {0x01: "1.0", 0x03: "2.0", 0x05: "MC", 0x43: "2.0"}


def asezare_din_descriptori(desc):
	"""Asezarea canalelor unei piste de sunet din descriptorii ei din PMT, sau „” cand nu o spun.
	AC-3 / E-AC-3 (anexa D): primul octet are component_type_flag in bitul 7, urmat de component_type; DTS (anexa G):
	sample_rate_code 4, bit_rate_code 6, nblks 7, fsize 14, surround_mode 6, lfe_flag 1, extended_surround_flag 2 biti;
	AAC (anexa H): profile_and_level, apoi AAC_type_flag in bitul 7 si AAC_type."""
	for t, d in desc:
		if t in (0x6A, 0x7A):
			if len(d) >= 2 and d[0] & 0x80:
				return _ASEZARE_AC3.get(d[1] & 0x07, u"")
		elif t == 0x7B:
			if len(d) >= 5:
				v = 0
				for b in bytearray(d[:5]):
					v = (v << 8) | b
				n = _CANALE_DTS.get((v >> 3) & 0x3F)
				lfe = (v >> 2) & 1
				if n == 1:
					return "1.0"
				if n == 2:
					return "2.0"
				if n:
					return "%d.%d" % (n, lfe)
		elif t == 0x7C:
			if len(d) >= 3 and d[1] & 0x80:
				return _ASEZARE_AAC.get(d[2], u"")
	return u""


# EN 300 468, tabelul 26: component_descriptor din EIT pentru sunet. stream_content 0x2 = MPEG-1 Layer 2 (component_type
# 0x01 mono, 0x02 dual mono, 0x03 stereo, 0x05 surround; 0x04 = mai multe limbi pe mai multe canale, nu o asezare);
# 0x4 = AC-3 / E-AC-3 (component_type ca in descriptorul AC-3, anexa D: b7 E-AC-3, b2-b0 canalele); 0x6 = HE-AAC
_ASEZARE_EIT_MPEG = {0x01: "1.0", 0x02: "1+1", 0x03: "2.0", 0x05: "MC"}
# ordinea asezarilor la unirea cu ce stie baza: o asezare stiuta nu scade (vezi asezarea_din_eit)
_TREAPTA_ASEZARE = {"1.0": 1, "1+1": 1, "2.0": 2}


def asezare_din_eit(stream_content, component_type):
	"""Un component_descriptor al EIT -> (formatul, ca in FORMATE_SUNET, asezarea canalelor), sau (None, „”) pentru o
	componenta care nu e sunet sau nu spune asezarea."""
	flux = stream_content & 0x0F
	if flux == 0x02:
		return "mpeg", _ASEZARE_EIT_MPEG.get(component_type, u"")
	if flux == 0x04:
		return ("eac3" if component_type & 0x80 else "ac3"), _ASEZARE_AC3.get(component_type & 0x07, u"")
	if flux == 0x06:
		return "aac", _ASEZARE_AAC.get(component_type, u"")
	return None, u""


def _treapta(asezare):
	if not asezare:
		return 0
	return _TREAPTA_ASEZARE.get(asezare, 3)


def asezarea_din_eit(audio, componente):
	"""Pistele de sunet ale canalului pornit primesc asezarea canalelor din component_descriptor-ii EIT ai emisiunii de
	acum (eServiceEvent.getComponentData(): (tag, component_type, stream_content, limba, text)), numai cand potrivirea
	e sigura: printre componentele cu acelasi format si aceeasi limba (sau fara limba, de o parte sau de alta) e un
	singur fel de asezare. O asezare stiuta nu scade: un canal cu 5.1 la un film ramane la 5.1 si cand emisiunea de acum
	e stereo (altfel baza s-ar rescrie la fiecare schimbare de emisiune). -> lista noua (audio nu se schimba)."""
	if not audio or not componente:
		return audio
	dupa = {}
	for comp in componente:
		try:
			tip, flux, limba = int(comp[1]), int(comp[2]), comp[3]
		except (TypeError, ValueError, IndexError):
			continue
		fmt, asezare = asezare_din_eit(flux, tip)
		if fmt and asezare:
			dupa.setdefault((fmt, cod_limba(limba).split("/")[0] if limba else u""), set()).add(asezare)
	if not dupa:
		return audio
	rez = []
	for p in audio:
		cod, asezare = desparte_fel(p[1])
		fmt = format_sunet(cod)
		limba = (p[0] or u"").split("/")[0]
		potrivite = set()
		for (f, l), asezari in dupa.items():
			if f == fmt and (not l or not limba or l == limba):
				potrivite |= asezari
		if len(potrivite) == 1:
			nou = next(iter(potrivite))
			if _treapta(nou) > _treapta(asezare):
				p = [p[0], fel_cu_asezare(cod, nou)] + list(p[2:])
		rez.append(p)
	return rez


def componente_eit(info, info_const):
	"""Component_descriptor-ii EIT ai emisiunii de acum a serviciului care ruleaza, sau []. Numai memorie: emisiunea de
	acum din serviciu (getEvent(0)), altfel din ghidul programelor (eEPGCache.lookupEventTime cu ora de acum)."""
	ev = None
	try:
		ev = info.getEvent(0)
	except Exception:
		ev = None
	if ev is None:
		try:
			ref = _text(info.getInfoString(info_const.sServiceref))
			if ref:
				from enigma import eEPGCache, eServiceReference
				ev = eEPGCache.getInstance().lookupEventTime(eServiceReference(ref), -1)
		except Exception:
			ev = None
	if ev is None:
		return []
	try:
		return list(ev.getComponentData() or [])
	except Exception:
		return []


def citeste_pmt(s):
	"""Sectiunea PMT -> {"program", "pcr", "piste": inregistrarea (a, d, x, tt, hb, s="p")}, sau None.
	stream_type 0x03/0x04/0x0F/0x11 = sunet; 0x06 cu 0x6A/0x7A/0x7B/0x7C = sunet AC3/E-AC3/DTS/AAC, cu asezarea
	canalelor cand descriptorul o are (asezare_din_descriptori); 0x0A = limba (tipul
	3 = descriere audio); 0x59 = subtitrari DVB (tipurile 0x20-0x25 = pentru surzi); 0x56 si 0x46 = teletext, cu
	intrarile de tip 2 (subtitrare) si 5 (subtitrare pentru surzi); stream_type 0x05 cu 0x6F = AIT, HbbTV cand tipul
	aplicatiei e 0x0010 sau descriptorul nu are nicio intrare. "ait" = PID-ul AIT ales ca in nucleu (lib/dvb/pmt.cpp):
	pista 0x05 cu tipul 0x0010, altfel pista 0x05 fara niciun tip in 0x6F (sau fara 0x6F); 0 fara asa ceva."""
	s = sectiune(s)
	if s is None or s[0] != 0x02:
		return None
	program = (s[3] << 8) | s[4]
	pcr = ((s[8] & 0x1F) << 8) | s[9]
	info = ((s[10] & 0x0F) << 8) | s[11]
	i = 12 + info
	sfarsit = len(s) - 4
	if i > sfarsit:
		return None
	audio, dvb, ttx = [], [], []
	teletext = hbbtv = 0
	ait, ait_fel = 0, 0
	while i + 5 <= sfarsit:
		tip = s[i]
		pid = ((s[i + 1] & 0x1F) << 8) | s[i + 2]
		lung = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
		inceput, capat = i + 5, min(i + 5 + lung, sfarsit)
		i = i + 5 + lung
		desc = _descriptori(s, inceput, capat)
		taguri = [t for t, _d in desc]
		fel = None
		if tip in _AUDIO_TIP_FLUX:
			fel = _AUDIO_TIP_FLUX[tip]
		elif tip == 0x06:
			for t in taguri:
				if t in _AUDIO_DESCRIPTOR:
					fel = _AUDIO_DESCRIPTOR[t]
					break
		if tip == 0x05:
			fel_ait = 1
			for t, d in desc:
				if t == 0x6F:
					if not d:
						hbbtv = 1
					for k in range(0, len(d) - 2, 3):
						if ((d[k] << 8 | d[k + 1]) & 0x7FFF) == 0x0010:
							hbbtv = 1
							fel_ait = 2
						elif fel_ait == 1:
							fel_ait = 0
			if fel_ait > ait_fel:
				ait, ait_fel = pid, fel_ait
			continue
		if tip in _VIDEO_TIP_FLUX:
			continue
		if tip == 0x06:
			for t, d in desc:
				if t == 0x59:
					for k in range(0, len(d) - 7, 8):
						tip_sub = d[k + 3]
						dvb.append([_limbaIso(d[k:k + 3]), 1 if 0x20 <= tip_sub <= 0x25 else 0])
				elif t in (0x56, 0x46):
					teletext = 1
					for k in range(0, len(d) - 4, 5):
						fel_ttx = d[k + 3] >> 3
						if fel_ttx in (2, 5):
							magazin = d[k + 3] & 7
							ttx.append([_limbaIso(d[k:k + 3]), "%d%02x" % (magazin or 8, d[k + 4]), 1 if fel_ttx == 5 else 0])
		if fel is not None:
			fel = fel_cu_asezare(fel, asezare_din_descriptori(desc))
			limba, descriere = u"", 0
			for t, d in desc:
				if t == 0x0A:
					coduri = []
					for k in range(0, len(d) - 3, 4):
						c = _limbaIso(d[k:k + 3])
						if c and c not in coduri:
							coduri.append(c)
						if d[k + 3] == 3:
							descriere = 1
					limba = "/".join(coduri)[:MAX_TEXT]
			audio.append([limba, fel, descriere])
	rec = {"a": audio[:MAX_PISTE], "d": dvb[:MAX_PISTE], "x": ttx[:MAX_PISTE], "tt": teletext, "hb": hbbtv, "s": "p"}
	return {"program": program, "pcr": pcr, "piste": rec, "ait": ait}


# ------------------------------------------------------------------ pistele din nucleu (canalul care ruleaza)

def pastreaza_asezarea(audio, vechi):
	"""Pistele citite prin nucleu (felul fara asezarea canalelor) primesc asezarea tinuta in baza pentru aceeasi pista:
	aceeasi limba si acelasi format, a k-a pista de acest fel cu a k-a din baza. O pista care are deja asezare, sau fara
	pereche in baza, ramane cum e. -> lista noua (audio nu se schimba)."""
	if not audio or not vechi:
		return audio
	stiute = {}
	for p in vechi:
		if isinstance(p, (list, tuple)) and len(p) >= 2:
			cod, asezare = desparte_fel(p[1])
			stiute.setdefault((p[0], cod.upper()), []).append(asezare)
	rez, vazute = [], {}
	for p in audio:
		cod, asezare = desparte_fel(p[1])
		k = (p[0], cod.upper())
		i = vazute.get(k, 0)
		vazute[k] = i + 1
		lista = stiute.get(k, ())
		if not asezare and i < len(lista) and lista[i]:
			p = [p[0], fel_cu_asezare(cod, lista[i])] + list(p[2:])
		rez.append(p)
	return rez


def _pisteAudioStiute(info, info_const):
	"""Pistele de sunet tinute in baza pentru serviciul care ruleaza (dupa sServiceref), sau None. Numai memorie: baza
	e deja incarcata cand culegerea scrie in ea, iar privirea desface un singur rand."""
	if info is None:
		return None
	try:
		ref = _text(info.getInfoString(info_const.sServiceref))
	except Exception:
		return None
	k = _X.cheie_din_ref(ref) if ref else None
	if not k:
		return None
	try:
		rec = baza().inregistrare(k)
	except Exception as e:
		_jurnal("asezarea din baza: %s" % e)
		return None
	return (rec or {}).get("a")


def din_serviciu(service, info_const=None):
	"""Serviciul care ruleaza -> inregistrarea (prin nucleu), sau None. Nu citeste nimic de pe disc sau din demux:
	numai ce are deja nucleul in memorie (getProgramInfo, emisiunea de acum), deci cateva apeluri, sub o milisecunda.
	Asezarea canalelor (pe care nucleul nu o da) se ia din baza, pentru aceleasi piste (pastreaza_asezarea), si din
	EIT-ul emisiunii de acum (asezarea_din_eit, care numai o urca)."""
	if service is None:
		return None
	if info_const is None:
		from enigma import iServiceInformation as info_const
	rec = {"s": "v"}
	program_stiut = False
	txt = -1
	info = None
	try:
		info = service.info()
		if info is not None:
			program_stiut = int(info.getInfo(info_const.sPMTPID)) > 0
			txt = int(info.getInfo(info_const.sTXTPID))
	except Exception:
		program_stiut = False
	audio = []
	try:
		piste = service.audioTracks()
		n = int(piste.getNumberOfTracks() or 0) if piste else 0
		for i in range(min(n, MAX_PISTE)):
			ti = piste.getTrackInfo(i)
			if ti is None:
				continue
			limba = ti.getLanguage()
			fel = _text(ti.getDescription()).strip().upper()[:MAX_TEXT]
			audio.append([cod_limba(limba), fel if fel != "???" else u"", 1 if este_descriere_audio(limba) else 0])
	except Exception as e:
		_jurnal("piste audio: %s" % e)
	dvb, ttx = [], []
	try:
		sub = service.subtitle()
		lista = (sub and sub.getSubtitleList()) or []
		for t in list(lista)[:2 * MAX_PISTE]:
			if not isinstance(t, (list, tuple)) or len(t) < 4:
				continue
			limba = t[4] if len(t) > 4 else u""
			surzi = 1 if len(t) > 5 and t[5] else 0
			if t[0] == 0:
				dvb.append([cod_limba(limba), surzi])
			elif t[0] == 1:
				ttx.append([cod_limba(limba), "%d%02x" % ((int(t[3]) & 7) or 8, int(t[2]) & 0xFF), surzi])
	except Exception as e:
		_jurnal("subtitrari: %s" % e)
	if audio:
		audio = pastreaza_asezarea(audio, _pisteAudioStiute(info, info_const))
		if info is not None:
			audio = asezarea_din_eit(audio, componente_eit(info, info_const))
	if program_stiut:
		rec.update({"a": audio, "d": dvb, "x": ttx, "tt": 1 if txt > 0 else 0})
		hb = _hb_din_nucleu(info, info_const)
		if hb is not None:
			rec["hb"] = hb
	else:
		# flux (gstreamer) sau PMT inca necitit: numai ce exista sigur
		if audio:
			rec["a"] = audio
		if dvb:
			rec["d"] = dvb
		if ttx:
			rec["x"] = ttx
	return curata(rec)


def _hb_din_nucleu(info, info_const):
	"""HbbTV din AIT-ul citit de nucleu (Components/HdsHbbtv.hb_din_stare): 1, 0 sau None (nu se stie: nu se scrie)."""
	try:
		try:
			from Components import HdsHbbtv as H
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			import HdsHbbtv as H
		return H.hb_din_stare(H.din_info(info, info_const))
	except Exception as e:
		_jurnal("HbbTV: %s" % e)
		return None


def demux_din_serviciu(service):
	"""Numarul demuxului de date al serviciului care ruleaza (getStreamingData, servicedvb.cpp 3125-3143), sau None."""
	try:
		s = service.stream()
		d = s and s.getStreamingData()
	except Exception:
		return None
	if isinstance(d, dict):
		n = d.get("demux")
		if isinstance(n, int) and 0 <= n < 16:
			return n
	return None


def transponder_din_ref(ref):
	"""Referinta unui canal DVB (fara cale) -> (sid, ns, tsid, onid), sau None."""
	parti = _text(ref).split(":")
	if len(parti) < 10 or (len(parti) > 10 and parti[10]):
		return None
	try:
		if int(parti[0]) != 1:
			return None
		sid, tsid, onid, ns = [int(p or "0", 16) for p in parti[3:7]]
	except ValueError:
		return None
	if not (sid and (tsid or onid or ns)):
		return None
	return sid, ns, tsid, onid


def cheie_program(program, ns, tsid, onid):
	"""Cheia bazei pentru un serviciu gasit in PAT (aceeasi ca HdsIndexCanale.cheie_din_ref)."""
	return "%x:%x:%x:%x" % (program, ns, tsid, onid)


# ------------------------------------------------------------------ demuxul, citit din Python

DMX_STOP = 0x6F2A                 # _IO('o', 42)
DMX_SET_FILTER = 0x403C6F2B       # _IOW('o', 43, struct dmx_sct_filter_params), 60 de octeti
DMX_SET_BUFFER_SIZE = 0x6F2D      # _IO('o', 45)
DMX_CHECK_CRC = 1
DMX_IMMEDIATE_START = 4


def structura_filtru(pid, tid, ext=None, timeout=0, flags=DMX_IMMEDIATE_START | DMX_CHECK_CRC):
	"""struct dmx_sct_filter_params (linux/dvb/dmx.h): pid, filter/mask/mode cate 16 octeti, timeout, flags. Octetul 0 =
	table_id, 1-2 = table_id_extension (ca eDVBTableSpec in lib/dvb/esection.cpp 81-100)."""
	filtru, masca = bytearray(16), bytearray(16)
	filtru[0], masca[0] = tid & 0xFF, 0xFF
	if ext is not None:
		filtru[1], filtru[2] = (ext >> 8) & 0xFF, ext & 0xFF
		masca[1] = masca[2] = 0xFF
	return struct.pack("@H16s16s16sII", pid & 0x1FFF, bytes(filtru), bytes(masca), bytes(16), timeout, flags)


class DemuxLinux(object):
	"""/dev/dvb/adapterN/demuxM: un filtru de sectiune al nostru, deschis fara blocare, pe langa filtrele nucleului."""

	def __init__(self, adaptor=ADAPTOR):
		self.adaptor = adaptor

	def cale(self, demux):
		return "/dev/dvb/adapter%d/demux%d" % (self.adaptor, demux)

	def deschide(self, demux, pid, tid, ext=None):
		import fcntl
		fd = os.open(self.cale(demux), os.O_RDONLY | os.O_NONBLOCK)
		try:
			try:
				fcntl.ioctl(fd, DMX_SET_BUFFER_SIZE, 64 * 1024)
			except (IOError, OSError):
				pass
			fcntl.ioctl(fd, DMX_SET_FILTER, structura_filtru(pid, tid, ext))
		except Exception:
			os.close(fd)
			raise
		return fd

	def citeste(self, fd):
		"""Octetii unei sectiuni; None cand nu e nimic de citit; b"" dupa o umplere a memoriei (se citeste din nou)."""
		try:
			return os.read(fd, 4096)
		except (IOError, OSError) as e:
			if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
				return None
			if e.errno == errno.EOVERFLOW:
				return b""
			raise

	def inchide(self, fd):
		try:
			import fcntl
			fcntl.ioctl(fd, DMX_STOP)
		except Exception:
			pass
		try:
			os.close(fd)
		except OSError:
			pass


def _ceasEnigma():
	from enigma import eTimer
	return eTimer()


def _notificatorEnigma(fd):
	"""eSocketNotifier din Python (eBaseImpl, lib/base/ebase.cpp 610-760), sau None: atunci se citeste cu un ceas."""
	try:
		from enigma import eSocketNotifier
		return eSocketNotifier(fd, 1)       # 1 = POLLIN
	except Exception:
		return None


class CititorTabel(object):
	"""Un tabel (toate sectiunile lui) de pe un PID, citit fara sa blocheze: eSocketNotifier, altfel un ceas de 50 ms;
	cel mult `timp_ms`. Rezultatul (lista sectiunilor sau None) vine prin la_gata, pe firul enigma2. Un singur filtru
	deschis odata; opreste() il inchide pe loc (la orice schimbare de canal)."""
	SONDAJ_MS = 50

	def __init__(self, io=None, fabrica_ceas=None, fabrica_notificator=None):
		self.io = io or DemuxLinux()
		self.fabrica_ceas = fabrica_ceas or _ceasEnigma
		self.fabrica_notificator = fabrica_notificator if fabrica_notificator is not None else _notificatorEnigma
		self.fd = None
		self.notificator = None
		self.ceasSondaj = None
		self.ceasLimita = None
		self.la_gata = None

	def activ(self):
		return self.fd is not None

	def porneste(self, demux, pid, tid, ext, la_gata, timp_ms=2000):
		"""-> True daca filtrul s-a deschis (rezultatul vine mai tarziu), False daca demuxul nu se poate folosi (atunci
		la_gata nu se cheama)."""
		self.opreste()
		try:
			self.fd = self.io.deschide(demux, pid, tid, ext)
		except Exception as e:
			_jurnal("demux%s PID %d: %s" % (demux, pid, e))
			self.fd = None
			return False
		self.tid, self.ext, self.la_gata = tid, ext, la_gata
		self.sectiuni = {}
		self.notificator = self.fabrica_notificator(self.fd) if self.fabrica_notificator else None
		if self.notificator is not None:
			self.notificator.callback.append(self._date)
		else:
			self.ceasSondaj = self.fabrica_ceas()
			self.ceasSondaj.callback.append(self._date)
			self.ceasSondaj.start(self.SONDAJ_MS, False)
		self.ceasLimita = self.fabrica_ceas()
		self.ceasLimita.callback.append(self._expirat)
		self.ceasLimita.start(timp_ms, True)
		return True

	def _date(self, *argumente):
		if self.fd is None:
			return
		for _k in range(32):
			try:
				buf = self.io.citeste(self.fd)
			except Exception as e:
				_jurnal("citire: %s" % e)
				self._gata(None)
				return
			if buf is None:
				return
			s = sectiune(buf)
			if s is None:
				continue
			tid, ext, nr, ultim = antet_sectiune(s)
			if tid != self.tid or (self.ext is not None and ext != self.ext):
				continue
			self.sectiuni[nr] = s
			if all(k in self.sectiuni for k in range(ultim + 1)):
				self._gata([self.sectiuni[k] for k in range(ultim + 1)])
				return

	def _expirat(self):
		self._gata(None)

	def _gata(self, rezultat):
		cb = self.la_gata
		self._inchide()
		if cb is not None:
			cb(rezultat)

	def _inchide(self):
		self.la_gata = None
		# notificatorul se opreste INAINTE sa se inchida descriptorul (altfel bucla enigma2 ar urmari un fd inchis)
		if self.notificator is not None:
			try:
				self.notificator.stop()
			except Exception:
				pass
			try:
				self.notificator.callback.remove(self._date)
			except Exception:
				pass
			self.notificator = None
		for ceas in (self.ceasSondaj, self.ceasLimita):
			if ceas is not None:
				try:
					ceas.stop()
				except Exception:
					pass
		self.ceasSondaj = self.ceasLimita = None
		if self.fd is not None:
			fd, self.fd = self.fd, None
			self.io.inchide(fd)

	def opreste(self):
		self._inchide()


class CititorTransponder(object):
	"""PAT-ul transponderului, apoi PMT-ul fiecarui serviciu, pe rand (un filtru deschis odata). Rezultatul:
	{numarul programului: inregistrarea}, sau None daca PAT-ul nu s-a putut citi."""
	MAX_PROGRAME = 64
	PAT_MS = 3000
	PMT_MS = 2000

	def __init__(self, cititor=None):
		self.cititor = cititor or CititorTabel()
		self.la_gata = None
		self.coada = []

	def activ(self):
		return self.la_gata is not None

	def porneste(self, demux, la_gata, dorite=None):
		"""dorite: numerele de program citite primele (de ex. canalele cerute la „Actualizeaza”).
		-> True daca PAT-ul se citeste (rezultatul vine mai tarziu prin la_gata), False daca demuxul nu se poate folosi:
		atunci la_gata NU se cheama (ca la CititorTabel.porneste); altfel „Actualizeaza” ar trece de doua ori mai departe
		si ar sari un canal necitit."""
		self.opreste()
		self.demux, self.rezultat, self.dorite = demux, {}, set(dorite or ())
		self.la_gata = la_gata
		if not self.cititor.porneste(demux, 0x0000, 0x00, None, self._laPat, self.PAT_MS):
			self.la_gata = None
			return False
		return True

	def _laPat(self, sectiuni):
		if not sectiuni:
			self._gata(None)
			return
		programe = {}
		for s in sectiuni:
			pat = citeste_pat(s)
			if pat:
				programe.update(pat["programe"])
		ordine = sorted(programe.items(), key=lambda p: (p[0] not in self.dorite, p[0]))
		self.coada = ordine[:self.MAX_PROGRAME]
		self._urmatorul()

	def _urmatorul(self):
		if self.la_gata is None:
			return
		if not self.coada:
			self._gata(self.rezultat)
			return
		self.program, pid = self.coada.pop(0)
		self.pid_pmt = pid
		if not self.cititor.porneste(self.demux, pid, 0x02, self.program, self._laPmt, self.PMT_MS):
			self._gata(self.rezultat or None)

	def _laPmt(self, sectiuni):
		if sectiuni:
			pmt = citeste_pmt(sectiuni[0])
			if pmt and pmt["program"] == self.program:
				rec = dict(pmt["piste"])
				# grupa pmt a bazei (BazaUnica.noteaza): PID-ul PMT, PCR-ul si PID-ul AIT; restul il stie vizionarea
				rec["pmt"] = [self.pid_pmt, pmt["pcr"], -1, -1, -1, pmt["ait"]]
				self.rezultat[self.program] = rec
		self._urmatorul()

	def _gata(self, rezultat):
		cb, self.la_gata = self.la_gata, None
		self.coada = []
		if cb is not None:
			cb(rezultat)

	def opreste(self):
		self.la_gata = None
		self.coada = []
		self.cititor.opreste()


# ------------------------------------------------------------------ comutatorul culegerii (setarea)
# Culegerea putea porni singura la fiecare pornire si citi PMT-ul brut al transponderului din Python, fara nicio
# oprire. De aceea e o setare, pe televizor
# (Meniu > Setari > Personalizare, data/setup.xml) si in web (/cautare), cu trei trepte:
#   „oprita”       nimic nu se citeste singur; „Actualizeaza pistele” (MENU in cautare) merge in continuare;
#   „canal”        numai canalul privit, prin nucleu (ce stie deja enigma2 din PMT: limbile, subtitrarile, teletextul);
#   „transponder”  si PMT-ul brut al tuturor canalelor de pe transponder, citit din Python direct din demux (asa se
#                  afla si HbbTV); „(netestat)”: n-a rulat niciodata pe HiSilicon, iar paznicul receptorului pomeneste
#                  o blocare a nucleului in dvb_demux_release la scanare. De aceea implicitul e „canal”; dupa proba pe
#                  receptor se poate trece pe „transponder”.
CULEGERE_OPRITA, CULEGERE_CANAL, CULEGERE_TRANSPONDER = "oprita", "canal", "transponder"
CULEGERI = (CULEGERE_OPRITA, CULEGERE_CANAL, CULEGERE_TRANSPONDER)
CULEGERE_IMPLICITA = CULEGERE_CANAL


def textCulegeri():
	"""Alegerile setarii, [(valoare, text tradus acum)], pentru pagina web; pe televizor aceleasi texte vin din
	alegeriCulegere(), traduse de ConfigSelection la afisare."""
	return [(CULEGERE_OPRITA, _("Oprită")), (CULEGERE_CANAL, _("Numai canalul privit")),
		(CULEGERE_TRANSPONDER, _("Tot transponderul"))]


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect."""
	return text


def alegeriCulegere():
	"""Alegerile setarii ca msgid-uri netraduse: setarea se face din InitUsageConfig, inaintea limbii alese, iar
	ConfigSelection traduce descrierile la afisare (getText, getMulti). Aceleasi texte romanesti ca textCulegeri(),
	fara semne de stare (Components/HdsStareMeniu.py: starea nu se arata)."""
	return [(CULEGERE_OPRITA, N_("Oprită")), (CULEGERE_CANAL, N_("Numai canalul privit")),
		(CULEGERE_TRANSPONDER, N_("Tot transponderul"))]


def initConfig():
	"""config.usage.hds_culegere_piste (din UsageConfig, ca randul din setup.xml sa o gaseasca); se poate chema de
	oricate ori."""
	from Components.config import config, ConfigSelection, ConfigSubsection
	if "usage" not in config.content.items:
		config.usage = ConfigSubsection()
	u = config.usage
	if "hds_culegere_piste" not in u.content.items:
		u.hds_culegere_piste = ConfigSelection(choices=alegeriCulegere(), default=CULEGERE_IMPLICITA)
	return u.hds_culegere_piste


def culegere():
	"""Treapta de acum; la orice necaz (fara config, valoare necunoscuta) cea implicita."""
	try:
		valoare = initConfig().value
	except Exception:
		return CULEGERE_IMPLICITA
	return valoare if valoare in CULEGERI else CULEGERE_IMPLICITA


def seteaza_culegere(valoare):
	"""Din web: pune si salveaza treapta. Intoarce False (fara nicio schimbare) pentru o valoare necunoscuta."""
	if valoare not in CULEGERI:
		return False
	element = initConfig()
	element.value = valoare
	element.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("salvarea setarii culegerii: %s" % e)
	return True


# ------------------------------------------------------------------ culegerea la vizionare

class Culegator(object):
	"""Pornit o data (Screens/HdsCautareCanale.porneste_masuratori). La zap nu face nimic in afara de oprirea unei
	citiri in curs: pistele se citesc la 2,5 s dupa ultimul evUpdatedInfo (vine de cateva ori la un zap), apoi, pe
	fundal, PMT-ul brut al transponderului (o data la 12 ore pe transponder). Scrierea pe disc: cel mult o data la
	30 s. Ce se citeste hotaraste setarea (culegere(); `mod` o inlocuieste in probe): nimic, numai canalul privit sau
	si transponderul."""
	LINISTE_MS = 2500
	SCRIERE_MS = 30000
	TRANSPONDER_S = 12 * 3600

	def __init__(self, nav, baza_=None, fabrica_ceas=None, cititor=None, evenimente=None, info_const=None, ceasornic=None,
			mod=None):
		if evenimente is None:
			from enigma import iPlayableService as evenimente
		self.ev = evenimente
		self.info_const = info_const
		self.nav = nav
		self.baza = baza_ if baza_ is not None else baza()
		fabrica = fabrica_ceas or _ceasEnigma
		self.ceas = fabrica()
		self.ceas.callback.append(self._citeste)
		self.ceasScriere = fabrica()
		self.ceasScriere.callback.append(self._scrie)
		self.cititor = cititor if cititor is not None else CititorTransponder()
		self.ceasornic = ceasornic or time.time
		self.tp_citite = {}
		self.pauza = False
		self.citiri = 0
		self.mod = mod or culegere
		nav.event.append(self._eveniment)
		if mod is None:
			try:
				initConfig().addNotifier(self.laSchimbareSetare, initial_call=False)
			except Exception as e:
				_jurnal("setarea culegerii: %s" % e)

	def laSchimbareSetare(self, *argumente):
		"""Setarea schimbata cat merge interfata: o citire bruta in curs se opreste daca nu mai e voie."""
		mod = self.mod()
		if mod != CULEGERE_TRANSPONDER:
			self.cititor.opreste()
		if mod == CULEGERE_OPRITA:
			self.ceas.stop()

	def _eveniment(self, ev):
		if ev in (self.ev.evStart, self.ev.evEnd):
			self.ceas.stop()
			self.cititor.opreste()
		elif ev == self.ev.evUpdatedInfo and not self.pauza and self.mod() != CULEGERE_OPRITA:
			self.ceas.start(self.LINISTE_MS, True)

	def _citeste(self):
		if self.pauza:
			return
		mod = self.mod()
		if mod == CULEGERE_OPRITA:
			return
		try:
			ref = self.nav.getCurrentlyPlayingServiceReference()
			service = self.nav.getCurrentService()
			text = ref.toString() if ref is not None else ""
			cheie = _X.cheie_din_ref(text)
			if not cheie or service is None:
				return
			self.citiri += 1
			rec = din_serviciu(service, self.info_const)
			if rec is not None and self.baza.noteaza(cheie, rec, self.ceasornic(), "v"):
				self._programeazaScrierea()
			if mod != CULEGERE_TRANSPONDER:
				return                      # „numai canalul privit”: fara citirea bruta din demux
			self._citesteTransponder(text, service)
		except Exception as e:
			_jurnal("culegere: %s" % e)

	def _citesteTransponder(self, text, service):
		"""PMT-ul brut al transponderului canalului `text`, pe fundal, cel mult o data la TRANSPONDER_S (treapta
		„transponder”; folosita si de culegerea unita, Components/HdsCulegereCanale.py)."""
		tp = transponder_din_ref(text)
		if tp is None:
			return
		sid, ns, tsid, onid = tp
		acum = self.ceasornic()
		if self.cititor.activ() or acum - self.tp_citite.get((ns, tsid, onid), 0) < self.TRANSPONDER_S:
			return
		demux = demux_din_serviciu(service)
		if demux is None:
			return
		if not self.cititor.porneste(demux, lambda r: self._laTransponder((ns, tsid, onid), sid, r), (sid,)):
			# demuxul nu se deschide (driverul refuza filtrul): din nou abia peste TRANSPONDER_S, nu la fiecare zap
			self.tp_citite[(ns, tsid, onid)] = acum

	def _laTransponder(self, tp, sid, rezultat):
		if rezultat is None:
			return
		ns, tsid, onid = tp
		self.tp_citite[tp] = self.ceasornic()
		schimbat = False
		for program, rec in rezultat.items():
			schimbat |= self.baza.noteaza(cheie_program(program, ns, tsid, onid), rec, self.ceasornic(), "p")
		_jurnal("transponderul %x:%x:%x: %d servicii citite" % (ns, tsid, onid, len(rezultat)))
		if schimbat:
			self._programeazaScrierea()

	def _programeazaScrierea(self):
		if not self.ceasScriere.isActive():
			self.ceasScriere.start(self.SCRIERE_MS, True)

	def _scrie(self):
		try:
			self.baza.salveaza()
		except Exception as e:
			_jurnal("scriere: %s" % e)

	def opreste_pentru(self, pauza):
		"""„Actualizeaza” are cititorul ei: culegatorul sta cat merge ea."""
		self.pauza = bool(pauza)
		if self.pauza:
			self.ceas.stop()
			self.cititor.opreste()


# ------------------------------------------------------------------ „Actualizeaza”: trecerea prin canale

def are_motor(nm=None):
	"""Un tuner de satelit cu motor (lista de sateliti a rotorului nu e goala, ca in Screens/ScanerSatelit.py are_motor)."""
	try:
		if nm is None:
			from Components.NimManager import nimmanager as nm
		for slot in range(len(nm.nim_slots)):
			try:
				if nm.getRotorSatListForNim(slot):
					return True
			except Exception:
				continue
	except Exception:
		return False
	return False


class Grup(object):
	"""Canalele cerute de pe un transponder."""
	__slots__ = ("tp", "poz", "canale")

	def __init__(self, tp, poz):
		self.tp, self.poz, self.canale = tp, poz, []


def _ordinePoz(poz):
	if isinstance(poz, int):
		return (0, -(poz if poz <= 1800 else poz - 3600))
	return (1, str(poz))


def transpondere_din_canale(canale):
	"""Canalele (obiecte cu .ref, .poz) -> grupurile pe transpondere, de la est la vest, ca motorul sa se miste putin.
	Fluxurile (referinte cu cale) nu intra: nu au PMT de citit."""
	grupuri = {}
	for c in canale:
		tp = transponder_din_ref(getattr(c, "ref", ""))
		if tp is None:
			continue
		cheie = tp[1:]
		g = grupuri.get(cheie)
		if g is None:
			g = grupuri[cheie] = Grup(cheie, getattr(c, "poz", None))
		g.canale.append(c)
	return sorted(grupuri.values(), key=lambda g: (_ordinePoz(g.poz), g.tp))


# pluralele traduse (ngettext luat din traducerea instalata de enigma2, cu regula romaneasca pentru textele netraduse);
# numele scurt, ca xgettext sa gaseasca apelurile (cuvantul-cheie ngettext)
ngettext = _X.ngettext


SECUNDE_PE_TRANSPONDER = 6
SECUNDE_PE_POZITIE_MOTOR = 40


# Estimarea dupa timpul real (0.3.0; inainte, 6 s pe transponder si 40 s pe pozitie, oricat ar fi durat): fiecare
# trecere masoara cat a durat un transponder pe aceeasi pozitie (de la pornirea primului canal pana la trecerea mai
# departe, cu PMT-urile, asteptarile si transponderele fara semnal) si cat a durat primul transponder dupa o mutare a
# antenei. Sumele si numarul lor stau in starea reluarii (cheia "masurat"), adunate peste treceri; peste MASURAT_MAX_N
# masuratori ale unui fel, sumele se micsoreaza la fel, ca masuratorile vechi sa cantareasca tot mai putin (alta antena,
# alt motor). Fara masuratori raman valorile de mai sus.
MASURAT_MAX_N = 300
_CHEI_MASURAT = ("tp_s", "tp_n", "poz_s", "poz_n")


def masurat_din_stare(stare):
	"""Masuratorile din starea reluarii: {"tp_s", "tp_n", "poz_s", "poz_n"} (secunde, numar), sau None."""
	m = stare.get("masurat") if isinstance(stare, dict) else None
	if not isinstance(m, dict):
		return None
	rez = {}
	for k in _CHEI_MASURAT:
		v = m.get(k, 0)
		if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v < 1e9:
			return None
		rez[k] = float(v) if k.endswith("_s") else int(v)
	return rez


def aduna_masurat(a, b):
	"""Doua seturi de masuratori adunate, cu plafonul MASURAT_MAX_N pe fiecare fel."""
	rez = {}
	for fel in ("tp", "poz"):
		s = float((a or {}).get(fel + "_s", 0)) + float((b or {}).get(fel + "_s", 0))
		n = int((a or {}).get(fel + "_n", 0)) + int((b or {}).get(fel + "_n", 0))
		if n > MASURAT_MAX_N:
			s, n = s * MASURAT_MAX_N / n, MASURAT_MAX_N
		rez[fel + "_s"], rez[fel + "_n"] = round(s, 1), n
	return rez


def timpi_masurati(masurat=None, citeste=True):
	"""-> (secunde pe transponder, secunde in plus pe pozitie noua a antenei). Din masuratori unde exista (din starea
	reluarii de pe disc, daca nu sunt date si citeste=True), altfel valorile implicite."""
	if masurat is None and citeste:
		masurat = masurat_din_stare(citeste_stare())
	m = masurat or {}
	s_tp = float(SECUNDE_PE_TRANSPONDER)
	if m.get("tp_n", 0) > 0:
		s_tp = max(1.0, m["tp_s"] / m["tp_n"])
	s_poz = float(SECUNDE_PE_POZITIE_MOTOR)
	if m.get("poz_n", 0) > 0:
		s_poz = max(0.0, m["poz_s"] / m["poz_n"] - s_tp)
	return s_tp, s_poz


def mutari(grupuri, de_la=None):
	"""De cate ori se muta antena trecand prin grupuri, in ordine, plecand de la pozitia de_la (None = nestiuta)."""
	n, poz = 0, de_la
	for g in grupuri:
		if g.poz != poz:
			n += 1
			poz = g.poz
	return n


def secunde_rotiri(grupuri, de_la=None, s_poz=None, masurat_poz=False):
	"""Secundele in plus pe primul transponder de dupa fiecare mutare a antenei, trecand prin grupuri in ordine de la
	pozitia de_la (None = nestiuta). Cu masuratori (masurat_poz): media masurata, pe fiecare pozitie, ca pana acum. Fara
	masuratori: pe fiecare mutare, timpul dupa viteza invatata a motorului (Components/HdsTimpCautare.secundeMutare, din
	Components/HdsMotorViteza.py) si SECUNDE_PE_POZITIE_MOTOR numai cand plecarea nu se stie sau nu se poate calcula."""
	if masurat_poz:
		return float(s_poz) * len(set(g.poz for g in grupuri if isinstance(g.poz, int)))
	try:
		from Components import HdsTimpCautare
	except ImportError:
		try:
			import HdsTimpCautare
		except ImportError:
			HdsTimpCautare = None
	total, poz = 0.0, de_la
	# modelul motorului luat o data (HdsTimpCautare il tine si el cateva zeci de secunde: stare() se cere des)
	model = HdsTimpCautare.modelMotor() if HdsTimpCautare is not None else None
	for g in grupuri:
		# cablul si terestrul nu misca antena: nici timp de rotire, nici alta pozitie de plecare
		if g.poz == poz or not isinstance(g.poz, int):
			continue
		s = None
		if model is not None and isinstance(poz, int) and isinstance(g.poz, int):
			s = HdsTimpCautare.secundeMutare(poz, g.poz, model)
		total += s if s is not None else float(SECUNDE_PE_POZITIE_MOTOR)
		poz = g.poz
	return total


def durata_estimata(grupuri, motor=False, masurat=None, de_la=None):
	if masurat is None:
		masurat = masurat_din_stare(citeste_stare())
	s_tp, s_poz = timpi_masurati(masurat, citeste=False)
	secunde = s_tp * len(grupuri)
	if motor:
		secunde += secunde_rotiri(grupuri, de_la, s_poz, (masurat or {}).get("poz_n", 0) > 0)
	return int(round(secunde))


def pozitii_de_mutat(grupuri, de_la=None):
	"""Pozitiile spre care trecerea prin grupuri, in ordine, trimite comanda de mutare a antenei, plecand de la de_la
	(pozitia stiuta de receptor; None = nestiuta, deci si prima pozitie primeste comanda); fiecare o data."""
	rez, poz = [], de_la
	for g in grupuri:
		if not isinstance(g.poz, int):
			continue           # cablul si terestrul: nicio comanda de mutare a antenei
		if g.poz != poz:
			if g.poz not in rez:
				rez.append(g.poz)
			poz = g.poz
	return rez


def _pozitiaAntenei():
	"""Pozitia antenei tinuta de nucleu (zecimi), sau None (nestiuta; pe PC, fara enigma, mereu None)."""
	try:
		return MotorReceptor().pozitie()
	except Exception:
		return None


_NESTIUT = object()


def text_confirmare(grupuri, motor=False, de_la=_NESTIUT):
	"""Intrebarea dinainte de "Actualizeaza" (ecranul si pagina web). Cu motor, numai ce e sigur: spre ce pozitii se
	trimite comanda de mutare (nu "se va roti" spre pozitia pe care receptorul stie ca sta antena), sau ca nu se trimite
	niciuna. de_la: pozitia antenei (implicit cea tinuta de nucleu)."""
	canale = sum(len(g.canale) for g in grupuri)
	if motor:
		de_la = _pozitiaAntenei() if de_la is _NESTIUT else de_la
	minute = max(1, (durata_estimata(grupuri, motor, de_la=None if de_la is _NESTIUT else de_la) + 59) // 60)
	text = _("Se trece prin %s (%s); durează cam %s. Imaginea se schimbă pe rând, apoi revine la canalul de acum.") % (
		ngettext("%d transponder", "%d transpondere", len(grupuri)) % len(grupuri), _X.text_numar(canale),
		ngettext("%d minut", "%d minute", minute) % minute)
	if motor:
		pozitii = pozitii_de_mutat(grupuri, de_la)
		if pozitii:
			text += u" " + _("Antena are motor și va primi pe rând comanda de mutare spre %s: %s.") % (
				ngettext("%d poziție", "%d poziții", len(pozitii)) % len(pozitii),
				u", ".join(_X.text_pozitie(p) for p in pozitii[:8]) + (u", …" if len(pozitii) > 8 else u""))
		else:
			text += u" " + _("Nu se trimite nicio comandă de mutare a antenei.")
	return text + u" " + _("Continui?")


def _istoricSemnal():
	try:
		from Components import HdsIstoricSemnal as I
	except ImportError:
		try:
			import HdsIstoricSemnal as I
		except ImportError:
			return None
	return I


def pozitii_neprinse(grupuri, ist=None, org=None):
	"""Pozitiile de satelit din grupuri aduse din alta lista (importul, listele implicite) pe care acest receptor nu a
	receptionat niciodata semnal (Components/HdsIstoricSemnal.aduse_fara_semnal), in ordinea grupurilor. Lista goala
	cand nu se stie nimic: pozitiile scanate aici sau cu originea nestiuta nu sunt intrebate."""
	I = _istoricSemnal()
	if I is None:
		return []
	pozitii = []
	for g in grupuri:
		if isinstance(g.poz, int) and not isinstance(g.poz, bool) and g.poz not in pozitii:
			pozitii.append(g.poz)
	try:
		aduse = I.aduse_fara_semnal(pozitii, ist, org)
	except Exception:
		return []
	return [p for p in pozitii if p in aduse]


def fara_pozitii(grupuri, pozitii):
	"""Grupurile fara cele de pe pozitiile date."""
	pozitii = set(pozitii or ())
	return [g for g in grupuri if g.poz not in pozitii]


def text_intrebare_neprinse(neprinse):
	"""Intrebarea de pe televizor, inaintea celei obisnuite: se incearca si pozitiile fara semnal niciodata?"""
	I = _istoricSemnal()
	inceput = I.text_neprinse(neprinse) + u" " if I is not None else u""
	return inceput + _("Le încerc și pe ele?")


def text_neprinse(neprinse, fara, motor=False):
	"""Intrebarea dinainte de Actualizeaza cand unele pozitii n-au prins niciodata semnal (ecranul si pagina web):
	pozitiile, apoi planul fara ele (durata, comenzile de mutare)."""
	I = _istoricSemnal()
	inceput = I.text_neprinse(neprinse) + u" " if I is not None else u""
	return inceput + _("Fără ele:") + u" " + text_confirmare(fara, motor)


def _monoton():
	return getattr(time, "monotonic", time.time)()


def text_frecventa(tp):
	"""Transponderul canalului, cum il da lamedb (Canal.tp: '11538 H' la satelit, '346 MHz' la cablu si terestru) ->
	'11,538 GHz' (separatorul zecimal al limbii meniului, Components/HdsGrade.py) sau '346 MHz'; u"" cand nu se stie."""
	parti = (tp or u"").split()
	if not parti or not parti[0].isdigit() or int(parti[0]) <= 0:
		return u""
	if len(parti) > 1 and parti[1] == u"MHz":
		return u"%s MHz" % parti[0]
	try:
		try:
			from Components.HdsGrade import numar
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			from HdsGrade import numar
		text = numar(int(parti[0]) / 1000.0, 3)
	except Exception:
		text = u""
	return u"%s GHz" % (text or u"%.3f" % (int(parti[0]) / 1000.0))


def text_asteptare_semnal(stare):
	"""Dupa rotirea antenei, cat tunerul inca nu a prins semnal: 'Aștept semnal pe 11,538 GHz (încă 23 s)'; secundele
	sunt cele ramase pana se trece la transponderul urmator. u"" cand nu se asteapta semnal."""
	if not stare.get("astept_semnal"):
		return u""
	ramas = max(0, int(stare.get("semnal_ramas_s") or 0))
	frecventa = stare.get("frecventa") or u""
	if frecventa:
		return _("Aștept semnal pe %s (încă %d s)") % (frecventa, ramas)
	return _("Aștept semnal (încă %d s)") % ramas


# ------------------------------------------------------------------ „Actualizeaza”: starea pentru reluare
# Transponderele terminate se tin intr-un fisier mic, scris atomic la 10 minute (numai cu ceva nou), la oprire si la
# sfarsit, DUPA baza pistelor; in el intra numai transponderele ale caror piste sunt deja pe disc. O trecere oprita
# sau intrerupta (cadere, repornire) in ultimele 24 de ore se poate continua: transponderele ei se sar.

CALE_STARE = "/etc/enigma2/hds-actualizare-piste.json"
FEL_STARE = "hds-actualizare-piste"
MAX_STARE = 256 * 1024
MAX_FACUTE = 20000
RELUARE_MAX_S = 24 * 3600
GATA = "gata"
OPRIT = "oprit"


def cheie_tp(tp):
	"""Grup.tp (namespace, tsid, onid) -> „ns:tsid:onid” in hexa, cheia transponderului in starea reluarii."""
	return "%x:%x:%x" % tuple(tp)


def citeste_stare(cale=None):
	"""Starea ultimei treceri, sau None (lipsa, stricata, prea mare, alt fel)."""
	cale = cale or CALE_STARE
	try:
		with open(cale, "rb") as f:
			date = f.read(MAX_STARE + 1)
	except (IOError, OSError):
		return None
	if len(date) > MAX_STARE:
		return None
	try:
		d = json.loads(date.decode("utf-8"))
	except (ValueError, UnicodeDecodeError, RecursionError):
		return None
	if not isinstance(d, dict) or d.get("fel") != FEL_STARE or d.get("v") != 1:
		return None
	return d


def scrie_stare(d, cale=None):
	"""Atomic: .nou, fsync, os.replace; numai ASCII (pe receptor Python-ul ruleaza cu locale ASCII). Nu arunca;
	-> True daca s-a scris."""
	cale = cale or CALE_STARE
	nou = cale + ".nou"
	try:
		date = json.dumps(d, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
		return True
	except Exception as e:
		_jurnal("starea actualizarii nu s-a putut scrie: %s" % e)
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def reluare(grupuri, stare, acum=None):
	"""Trecerea din `stare`, oprita sau intrerupta in ultimele RELUARE_MAX_S, se poate continua peste `grupuri`:
	-> (grupurile ramase, cate din `grupuri` sunt facute, cheile facute) sau None (nimic de reluat: fara stare,
	terminata, prea veche, niciun transponder comun sau toate facute)."""
	if not isinstance(stare, dict) or stare.get("motiv") == GATA:
		return None
	try:
		actualizat = float(stare.get("actualizat") or 0)
	except (TypeError, ValueError):
		return None
	acum = time.time() if acum is None else acum
	if not 0 <= acum - actualizat <= RELUARE_MAX_S:
		return None
	lista = stare.get("facute")
	facute = set(k for k in lista if isinstance(k, str)) if isinstance(lista, list) else set()
	ramase = [g for g in grupuri if cheie_tp(g.tp) not in facute]
	n = len(grupuri) - len(ramase)
	if not n or not ramase:
		return None
	return ramase, n, facute


def text_reluare(facute, total):
	"""Intrebarea dinaintea unei noi „Actualizeaza” cand cea de dinainte nu s-a terminat (ecranul si pagina web)."""
	return _("Ultima actualizare a pistelor s-a oprit la transponderul %d din %d. Continui de unde a rămas?") % (
		min(facute + 1, total), total)


class MotorReceptor(object):
	"""Ce spune receptorul despre antena cu motor, pentru „Actualizeaza” (importuri tarzii; pe PC, fara enigma, totul e
	None si ramane prezicerea): pozitia tinuta de nucleu, mutarea in mers sau oprita (sec.cpp: hdsRotorMovingSlot,
	hdsRotorStoppedMs) si cat ar lua o mutare (modelul vitezei din Components/HdsCulegereTotala.py si HdsMotorViteza)."""

	def __init__(self):
		self.slot = None

	def _nucleu(self):
		try:
			from Components import HdsMotorTuner as T
			return T.controlSec(), T
		except Exception:
			return None, None

	def _sloturi(self, T):
		try:
			return [slot for slot, _nume in T.tunereCuMotor()]
		except Exception:
			return []

	def pozitie(self):
		"""Pozitia antenei tinuta de nucleu (zecimi, ca Grup.poz), sau None."""
		sec, T = self._nucleu()
		if sec is None:
			return None
		for slot in self._sloturi(T):
			try:
				p = int(sec.hdsKnownRotorPosition(slot))
			except Exception:
				continue
			if 0 <= p < 3600:
				return p
		return None

	def stare(self):
		"""{"merge": True / False / None, "oprit_de_s": secundele de la oprirea ultimei mutari (None = in mers sau nu se
		stie)}."""
		rez = {"merge": None, "oprit_de_s": None}
		sec, T = self._nucleu()
		if sec is None:
			return rez
		try:
			slot = int(sec.hdsRotorMovingSlot())
		except Exception:
			return rez
		rez["merge"] = slot >= 0
		if slot >= 0:
			self.slot = slot
			return rez
		sloturi = [self.slot] if self.slot is not None else self._sloturi(T)[:1]
		for s in sloturi:
			try:
				ms = int(sec.hdsRotorStoppedMs(s))
			except Exception:
				continue
			if ms >= 0:
				rez["oprit_de_s"] = ms / 1000.0
		return rez

	def secunde(self, de_la, la):
		"""Cat ar lua mutarea antenei intre doua pozitii (zecimi), dupa modelul invatat al motorului; None = nu se stie."""
		if de_la is None or la is None:
			return None
		try:
			try:
				from Components import HdsCulegereTotala as C
			except ImportError:
				import HdsCulegereTotala as C
			return float(C.secunde_mutare(de_la, la, C.Receptor(None).model_motor()))
		except Exception as e:
			_jurnal("durata mutarii: %s" % e)
			return None


def _paznic(lucru, da):
	"""HDSatelit: cat merge „Actualizeaza pistele” (transponder cu transponder, poate cu motorul),
	paznicul receptorului nu reporneste interfata (semnul „ocupat” din Components/HdsPaznic.py). Nu arunca niciodata;
	probele de pe PC, fara modulul HdsPaznic, trec mai departe."""
	try:
		from Components import HdsPaznic
	except ImportError:
		return
	cheie = "piste-%d" % id(lucru)
	if da:
		HdsPaznic.ocupat(cheie, HdsPaznic.MOTIV_PISTE, HdsPaznic.DURATA_PISTE_S)
	else:
		HdsPaznic.liber(cheie)


def _paznicDinNou(lucru):
	"""Semnul „ocupat” al trecerii luat inca o data de la capat: HdsPaznic scoate un semn mai vechi de 6 ore chiar
	daca e reinnoit cu aceeasi cheie (incepe pastreaza inceputul), iar o trecere cu motorul prin multe pozitii poate
	tine mai mult."""
	_paznic(lucru, False)
	_paznic(lucru, True)


class Actualizare(object):
	"""Trecerea prin transpondere: pe fiecare se porneste UN canal (neprotejat), apoi se citesc PMT-urile tuturor
	(CititorTransponder). Fara demux cunoscut, se trece pe rand prin canalele cerute si se ia ce da nucleul. La sfarsit
	(sau la opreste()) se revine la canalul de dinainte si baza se scrie pe loc, apoi starea reluarii.

	nav: session.nav (playService, getCurrentService, getCurrentlyPlayingServiceReference, event);
	fa_ref: text -> eServiceReference; protejat: ref (text) -> True daca e sub controlul parental;
	la_pas(stare) si la_sfarsit(stare): stare = self.stare();
	motor_info: MotorReceptor (sau unul fals in probe); monoton: ceasul termenelor (secunde);
	facute: cheile transponderelor terminate intr-o trecere reluata (raman in stare); inainte: cate transpondere din
	planul intreg s-au facut atunci (numaratoarea „Transponderul N din M” continua); cale_stare: fisierul reluarii.

	Asteptarea pe un transponder: PMT-ul venit (evUpdatedInfo, apoi LINISTE_MS) trece mai departe pe loc. Pe aceeasi
	pozitie termenul e ASTEPTARE_MS. Dupa o mutare a antenei (nu 2 minute fixe, orb): termenul e sfarsitul mutarii
	(spus de nucleu; fara el, prezis din grade si viteza) plus SEMNAL_DUPA_MOTOR_MS pentru semnal; cat nucleul spune
	ca motorul merge, termenul se muta; un acord prins dupa mutare il scurteaza la ASTEPTARE_MS pentru PMT; plafonul
	e MOTOR_MAX_MS plus semnalul.

	In stare(), "rotire" e adevarat numai cand nucleul spune ca motorul merge (dovada); prezicerea din grade si viteza
	tine numai termenul. Fara dovada se spune ce se stie sigur: asteptarea semnalului, cu secundele ramase.

	O pozitie de satelit care nu da niciun acord in aceasta trecere: dupa PRAG_FARA_SEMNAL transpondere ale ei la rand
	fara acord (masurat la termen, nu presupus), restul transponderelor ei se lasa; canalele lor se numara aparte
	(sarite_fara_semnal) si pozitia se spune la sfarsit (text_rezultat)."""
	LINISTE_MS = 1000
	ASTEPTARE_MS = 10000
	SEMNAL_DUPA_MOTOR_MS = 30000
	TIC_MS = 1000
	MOTOR_MAX_MS = 360000           # cea mai lunga mutare (motorul cel mai incet presupus de nucleu, HdsPaznic.DURATA_MOTOR_S)
	MOTOR_NECUNOSCUT_MS = 60000     # pozitia de plecare nu se stie: jumatate dintr-un drum de la un capat la altul
	SCRIERE_MS = 600000             # baza si starea reluarii pe drum: la 10 minute, numai cu ceva nou
	PAZNIC_REINNOIRE_MS = 3600000
	# o pozitie de satelit care nu a dat niciun acord in trecerea de acum: dupa atatea transpondere la rand fara acord,
	# restul ei se lasa (o lista adusa de altundeva poate avea pozitii pe care antena nu le prinde; fiecare transponder
	# al lor ar astepta degeaba)
	PRAG_FARA_SEMNAL = 5
	# o pozitie pe care receptorul n-a prins niciodata semnal (Components/HdsIstoricSemnal.py), incercata la cererea
	# omului: lasata mai repede
	PRAG_NEPRINSA = 2

	def __init__(self, nav, grupuri, baza_=None, cititor=None, fabrica_ceas=None, fa_ref=None, protejat=None,
			motor=False, evenimente=None, info_const=None, la_pas=None, la_sfarsit=None, ceasornic=None,
			motor_info=None, monoton=None, facute=None, inainte=0, cale_stare=None, neprinse=None, lasate=None):
		if evenimente is None:
			from enigma import iPlayableService as evenimente
		if fa_ref is None:
			from enigma import eServiceReference as fa_ref
		self.ev = evenimente
		self.info_const = info_const
		self.nav = nav
		self.grupuri = list(grupuri)
		self.baza = baza_ if baza_ is not None else baza()
		self.cititor = cititor if cititor is not None else CititorTransponder()
		fabrica = fabrica_ceas or _ceasEnigma
		self.ceasLimita = fabrica()
		self.ceasLimita.callback.append(self._limita)
		self.ceasLiniste = fabrica()
		self.ceasLiniste.callback.append(self._peCanal)
		self.fa_ref = fa_ref
		self.protejat = protejat or (lambda ref: False)
		self.motor = motor
		self.motor_info = motor_info if motor_info is not None else (MotorReceptor() if motor else None)
		self.monoton = monoton or _monoton
		self.la_pas = la_pas
		self.la_sfarsit = la_sfarsit
		self.ceasornic = ceasornic or time.time
		self.cale_stare = cale_stare
		self.i = -1
		self.canal = None
		self.pozAnterioara = None
		self.asteptare = False
		self.gata = False
		self.oprit = False
		self.original = None
		self.citite = set()
		self.fara_semnal = 0
		self.sarite = 0
		self.pe_canale = []          # canalele de citit pe rand (cand PMT-ul brut nu merge)
		self._peRand = None          # grupul (indexul) care se citeste pe rand
		# asteptarea pe canalul pornit (ceasul monoton)
		self.t0 = 0.0
		self.termen = 0.0
		self.mutare = False          # canalul pornit e pe alta pozitie: antena se muta
		self.rotire = False          # antena inca se roteste (nucleul o spune, sau prezicerea fara nucleu)
		self.rotire_vazuta = False   # la ultimul pas nucleul a spus ca motorul merge: singura dovada pentru "se roteste"
		self.sfarsit_prezis = 0.0
		self.t_semnal = None         # cand s-a vazut acordul prins dupa mutare
		self.asteptare_aratata = False   # ultima stare anuntata era 'astept semnal'
		# reluarea
		self.inainte = max(0, int(inainte or 0))
		self.facute = set(facute or ())
		self.facute_scrise = set(self.facute)
		self.inceput = int(time.time())
		self.ultima_scriere = 0.0
		self.paznic_la = 0.0
		# timpul real (estimarea): masuratorile trecerilor de dinainte, din starea de pe disc, si ale acesteia
		self.masurat_vechi = masurat_din_stare(citeste_stare(cale_stare))
		self.masurat = {"tp_s": 0.0, "tp_n": 0, "poz_s": 0.0, "poz_n": 0}
		self.t_grup = None           # cand s-a pornit primul canal al grupului de acum (ceasul monoton)
		self.grup_mutat = False      # pentru grupul de acum antena s-a mutat
		# tasta „Sari peste satelitul acesta”
		self.sarite_pozitie = 0      # canalele lasate la cererea omului
		self.pozitii_sarite = []     # pozitiile lasate (textul lor)
		self._sarit = False          # grupul de acum s-a terminat prin sarire (nu se masoara)
		# pozitiile fara semnal (PRAG_FARA_SEMNAL): pozitia numarata, transponderele ei la rand fara acord, daca a dat
		# vreun acord in trecerea de acum; canalele si pozitiile lasate asa
		self.poz_numarata = None
		self.fara_acord_la_rand = 0
		self.acord_pe_pozitie = False
		self.sarite_fara_semnal = 0
		self.pozitii_fara_semnal = []
		# istoricul semnalului: pozitiile neprinse niciodata incercate (prag mai mic) si cele lasate inainte de pornire
		self.neprinse = set(neprinse or ())
		self.pozitii_neprinse_goale = []
		self.pozitii_lasate = [_X.text_pozitie(p) or u"?" for p in (lasate or ())]

	def stare(self):
		total = len(self.grupuri)
		g = self.grupuri[self.i] if 0 <= self.i < total else None
		return {
			"activ": not self.gata,
			"oprit": self.oprit,
			"pas": self.inainte + max(0, min(self.i + 1, total)),
			"total": self.inainte + total,
			"canal": getattr(self.canal, "nume", u"") if self.canal is not None else u"",
			"pozitie": _X.text_pozitie(g.poz) if g is not None else u"",
			"citite": len(self.citite),
			"fara_semnal": self.fara_semnal,
			"sarite": self.sarite,
			# "Antena se roteste" numai cu dovada: nucleul a spus la ultimul pas ca motorul merge
			"rotire": bool(self.rotire_vazuta and self.asteptare and not self.gata),
			"sarite_pozitie": self.sarite_pozitie,
			"pozitii_sarite": list(self.pozitii_sarite),
			"sarite_fara_semnal": self.sarite_fara_semnal,
			"pozitii_fara_semnal": list(self.pozitii_fara_semnal),
			"pozitii_neprinse_goale": list(self.pozitii_neprinse_goale),
			"pozitii_lasate": list(self.pozitii_lasate),
			"poate_sari": bool(g is not None and not self.gata and not self.oprit),
			"satelit": bool(g is not None and isinstance(g.poz, int)),
			"ramas_s": self.ramas_s(),
			# dupa rotire, cat se asteapta semnalul (text_asteptare_semnal): frecventa si secundele ramase
			"astept_semnal": self.astept_semnal(),
			"semnal_ramas_s": self.semnal_ramas_s(),
			"frecventa": text_frecventa(getattr(self.canal, "tp", u"")) if self.canal is not None else u"",
		}

	def astept_semnal(self):
		"""Dupa comanda de mutare a antenei, cat nucleul nu spune ca motorul merge, iar tunerul inca nu a prins semnal:
		se asteapta pana la termen (in el intra si mutarea prezisa, cand nucleul nu spune nimic), apoi transponderul trece
		la 'fara semnal'."""
		return bool(self.asteptare and self.mutare and not self.rotire_vazuta and self.t_semnal is None and not self.gata
			and not self.oprit)

	def semnal_ramas_s(self):
		"""Secundele ramase din asteptarea semnalului (rotunjite in sus), sau None cand nu se asteapta semnal."""
		if not self.astept_semnal():
			return None
		return int(max(0.0, self.termen - self.monoton()) + 0.999)

	def masurat_total(self):
		"""Masuratorile trecerilor de dinainte adunate cu ale acesteia (ce se scrie in stare)."""
		return aduna_masurat(self.masurat_vechi, self.masurat)

	def ramas_s(self):
		"""Cat mai dureaza, in secunde, dupa timpii masurati (si ai acestei treceri): grupurile ramase, mutarile antenei
		intre ele si ce a mai ramas din grupul de acum."""
		total = len(self.grupuri)
		if self.gata or not 0 <= self.i < total:
			return 0
		masurat = self.masurat_total()
		s_tp, s_poz = timpi_masurati(masurat, citeste=False)
		g = self.grupuri[self.i]
		rest = self.grupuri[self.i + 1:]
		secunde = s_tp * (len(rest) + 1)
		if self.motor:
			if masurat.get("poz_n", 0) > 0:
				secunde += s_poz * mutari(rest, g.poz)
			else:
				# fara masuratori: fiecare mutare dupa viteza invatata a motorului (grade / viteza)
				secunde += secunde_rotiri(rest, g.poz)
			if self.grup_mutat and self.asteptare and self.rotire:
				secunde += max(0.0, self.sfarsit_prezis - self.monoton())
		if self.t_grup is not None:
			secunde -= min(s_tp, max(0.0, self.monoton() - self.t_grup))
		return max(0, int(round(secunde)))

	def sari_pozitia(self):
		"""Tasta „Sari peste satelitul acesta”: transponderele ramase de pe pozitia de acum se lasa (canalele lor se
		numara la „sarite la cererea ta” si trec la facute, ca o reluare sa nu le ia din nou), iar trecerea merge la
		pozitia urmatoare (la sfarsit, daca nu mai e alta). -> textul pozitiei lasate, sau None (nimic in lucru)."""
		total = len(self.grupuri)
		if self.gata or self.oprit or not 0 <= self.i < total:
			return None
		g = self.grupuri[self.i]
		n = len([c for c in g.canale if c.cheie_mas not in self.citite]) + self._lasaRestulPozitiei()
		self.sarite_pozitie += n
		text = _X.text_pozitie(g.poz) or u"?"
		if text not in self.pozitii_sarite:
			self.pozitii_sarite.append(text)
		_jurnal("actualizarea pistelor: sarita pozitia %s (%d canale)" % (g.poz, n))
		self._urmatorul()
		return text

	def _lasaRestulPozitiei(self):
		"""Transponderele de dupa cel de acum, de pe aceeasi pozitie, se lasa (trec la facute, ca o reluare sa nu le ia
		din nou); _urmatorul merge apoi la pozitia urmatoare. -> canalele lor."""
		total = len(self.grupuri)
		g = self.grupuri[self.i]
		self.ceasLimita.stop()
		self.ceasLiniste.stop()
		self.cititor.opreste()
		self.asteptare = False
		self.rotire = False
		self.rotire_vazuta = False
		self.pe_canale = []
		self._peRand = None
		n = 0
		j = self.i + 1
		# grupurile sunt pe pozitii (transpondere_din_canale), deci cele de pe aceeasi pozitie sunt la rand
		while j < total and self.grupuri[j].poz == g.poz:
			n += len(self.grupuri[j].canale)
			j += 1
		for k in range(self.i, j - 1):
			self.facute.add(cheie_tp(self.grupuri[k].tp))
		self.i = j - 1
		self._sarit = True
		return n

	def _maiSuntPePozitie(self):
		"""Dupa transponderul de acum mai urmeaza unul de pe aceeasi pozitie."""
		j = self.i + 1
		return 0 <= self.i and j < len(self.grupuri) and self.grupuri[j].poz == self.grupuri[self.i].poz

	def _numaraAcord(self, acord):
		"""Acordul la sfarsitul asteptarii unui transponder (sau PMT-ul venit, care il dovedeste). -> True cand pozitia
		de satelit de acum nu a dat niciun acord in trecerea de acum, iar ultimele PRAG_FARA_SEMNAL transpondere ale ei
		au ramas fara acord. Cablul si terestrul nu se numara: o frecventa goala nu spune nimic despre celelalte."""
		if not 0 <= self.i < len(self.grupuri):
			return False
		poz = self.grupuri[self.i].poz
		if not isinstance(poz, int):
			return False
		if poz != self.poz_numarata:
			self.poz_numarata = poz
			self.fara_acord_la_rand = 0
			self.acord_pe_pozitie = False
		if acord:
			self.acord_pe_pozitie = True
			self.fara_acord_la_rand = 0
			return False
		self.fara_acord_la_rand += 1
		prag = self.PRAG_NEPRINSA if poz in self.neprinse else self.PRAG_FARA_SEMNAL
		return not self.acord_pe_pozitie and self.fara_acord_la_rand >= prag

	def _lasaPozitiaFaraSemnal(self):
		"""Pozitia nu a dat acord pe PRAG_FARA_SEMNAL transpondere la rand: restul ei se lasa; canalele se numara
		aparte si pozitia se spune la sfarsit (text_rezultat), niciodata pe tacute."""
		g = self.grupuri[self.i]
		la_rand = self.fara_acord_la_rand
		n = self._lasaRestulPozitiei()
		self.sarite_fara_semnal += n
		text = _X.text_pozitie(g.poz) or u"?"
		lista = self.pozitii_neprinse_goale if g.poz in self.neprinse else self.pozitii_fara_semnal
		if text not in lista:
			lista.append(text)
		_jurnal("actualizarea pistelor: pozitia %s lasata dupa %d transpondere la rand fara acord (%d canale)" % (
			g.poz, la_rand, n))
		self._urmatorul()

	def porneste(self):
		_paznic(self, True)
		acum = self.monoton()
		self.paznic_la = acum
		self.ultima_scriere = acum
		try:
			self.original = self.nav.getCurrentlyPlayingServiceReference()
		except Exception:
			self.original = None
		if self.motor and self.motor_info is not None:
			try:
				self.pozAnterioara = self.motor_info.pozitie()
			except Exception:
				self.pozAnterioara = None
		# starea pe disc de la inceput (cu transponderele trecerii reluate): o cadere inainte de prima scriere la 10
		# minute nu lasa o stare veche, a altei treceri
		self._scrieStare(None)
		self.nav.event.append(self._eveniment)
		self._urmatorul()

	def _anunta(self):
		if self.la_pas is not None:
			try:
				self.la_pas(self.stare())
			except Exception as e:
				_jurnal("progres: %s" % e)

	def _urmatorul(self):
		self.ceasLimita.stop()
		self.ceasLiniste.stop()
		if self.oprit or self.gata:
			return
		if self.pe_canale:
			self.canal = self.pe_canale.pop(0)
			self._porneste(self.canal)
			return
		# transponderele cu toate canalele protejate se sar pe loc (bucla, nu recursie: pot fi multe)
		while True:
			if 0 <= self.i < len(self.grupuri):
				self._terminat(self.grupuri[self.i])
			self.i += 1
			self.t_grup = None
			self.grup_mutat = False
			if self.i >= len(self.grupuri):
				self._termina()
				return
			g = self.grupuri[self.i]
			self.canal = None
			for c in g.canale:
				if not self.protejat(c.ref):
					self.canal = c
					break
			if self.canal is not None:
				break
			self.sarite += len(g.canale)
			self._anunta()
		self._porneste(self.canal)

	def _porneste(self, canal):
		g = self.grupuri[self.i]
		de_la = self.pozAnterioara
		# numai o pozitie orbitala misca antena; cat se citeste cablul sau terestrul ea ramane unde era
		muta = bool(self.motor and isinstance(g.poz, int) and g.poz != de_la)
		if isinstance(g.poz, int):
			self.pozAnterioara = g.poz
		self.asteptare = True
		self.mutare = muta
		self.rotire = muta
		self.rotire_vazuta = False
		self.t_semnal = None
		self.t0 = self.monoton()
		if self.t_grup is None:
			self.t_grup = self.t0
			self.grup_mutat = muta
		if muta:
			secunde = None
			if de_la is not None and self.motor_info is not None:
				try:
					secunde = self.motor_info.secunde(de_la, g.poz)
				except Exception:
					secunde = None
			if secunde is None:
				secunde = self.MOTOR_NECUNOSCUT_MS / 1000.0
			secunde = max(0.0, min(float(secunde), self.MOTOR_MAX_MS / 1000.0))
			self.sfarsit_prezis = self.t0 + secunde
			self.termen = self.sfarsit_prezis + self.SEMNAL_DUPA_MOTOR_MS / 1000.0
		self._anunta()
		try:
			self.nav.playService(self.fa_ref(canal.ref), checkParentalControl=False)
		except TypeError:
			self.nav.playService(self.fa_ref(canal.ref))
		except Exception as e:
			_jurnal("pornire %s: %s" % (canal.ref, e))
		if muta:
			self.ceasLimita.start(self.TIC_MS, True)
		else:
			self.ceasLimita.start(self.ASTEPTARE_MS, True)

	def _eveniment(self, ev):
		if self.asteptare and ev == self.ev.evUpdatedInfo:
			self.ceasLiniste.start(self.LINISTE_MS, True)

	def _semnal(self):
		"""Starea tunerului canalului pornit: True = acordat (LOCKED), False = FAILED / LOSTLOCK, None = nu se stie."""
		try:
			service = self.nav.getCurrentService()
			fe = service.frontendInfo() if service is not None else None
			d = fe.getFrontendStatus() if fe is not None else None
		except Exception:
			return None
		if not isinstance(d, dict) or not d:
			return None
		stare = str(d.get("tuner_state") or "").upper()
		if stare == "LOCKED":
			return True
		if stare in ("FAILED", "LOSTLOCK"):
			return False
		prins = d.get("tuner_locked")
		return None if prins is None else bool(prins)

	def _limita(self):
		"""Ceasul canalului pornit. Pe aceeasi pozitie: termenul a trecut. Dupa o mutare: un pas de TIC_MS, in care
		termenul se socoteste din nou dupa motor si acord."""
		if not self.asteptare or self.oprit or self.gata:
			return
		if not self.mutare:
			self._expirat()
			return
		acum = self.monoton()
		semnal_s = self.SEMNAL_DUPA_MOTOR_MS / 1000.0
		st = None
		if self.motor_info is not None:
			try:
				st = self.motor_info.stare()
			except Exception as e:
				_jurnal("starea motorului: %s" % e)
		st = st if isinstance(st, dict) else {}
		merge = st.get("merge")
		oprit_de = st.get("oprit_de_s")
		termen = self.termen
		rotire = self.rotire
		if merge:
			# nucleul spune ca antena merge: semnalul se asteapta dupa ce se opreste
			rotire = True
			self.t_semnal = None
			termen = max(termen, acum + semnal_s)
		else:
			if oprit_de is not None and acum - oprit_de >= self.t0:
				# mutarea acestui canal s-a oprit (nu o oprire mai veche): semnalul are SEMNAL_DUPA_MOTOR_MS de atunci
				rotire = False
				termen = acum - oprit_de + semnal_s
			elif merge is None:
				# fara nucleu: prezicerea
				rotire = acum < self.sfarsit_prezis
			if self._semnal():
				if self.t_semnal is None:
					self.t_semnal = acum
				rotire = False
				termen = min(termen, self.t_semnal + self.ASTEPTARE_MS / 1000.0)
		termen = min(termen, self.t0 + (self.MOTOR_MAX_MS + self.SEMNAL_DUPA_MOTOR_MS) / 1000.0)
		self.termen = termen
		# pe ecran "se roteste" numai cand nucleul spune ca motorul merge; prezicerea tine numai termenul
		vazuta = bool(merge)
		if rotire != self.rotire or vazuta != self.rotire_vazuta:
			self.rotire = rotire
			self.rotire_vazuta = vazuta
			self._anunta()
		elif acum < termen and (self.astept_semnal() or self.asteptare_aratata):
			# dupa rotire, cat se asteapta semnalul, secundele ramase se schimba la fiecare pas; inca o data cand vine
			# semnalul, ca randul 'astept semnal' sa nu ramana pe ecran
			self._anunta()
		self.asteptare_aratata = self.astept_semnal()
		if acum >= termen:
			self._expirat()
			return
		self.ceasLimita.start(int(max(1, min(self.TIC_MS, (termen - acum) * 1000.0))), True)

	def _expirat(self):
		if not self.asteptare:
			return
		# acordul prins dupa o mutare, sau starea tunerului acum, la termen
		acord = self.t_semnal is not None or self._semnal() is True
		self.asteptare = False
		self.rotire = False
		self.rotire_vazuta = False
		if self._peRand != self.i:
			# pe rand (PMT-ul brut nu merge) transponderul are semnal: primul canal s-a citit; un canal tacut nu e
			# „transponder fara semnal”
			self.fara_semnal += 1
			if self._numaraAcord(acord) and self._maiSuntPePozitie():
				self._lasaPozitiaFaraSemnal()
				return
		self._urmatorul()

	def _peCanal(self):
		if not self.asteptare or self.oprit:
			return
		self.asteptare = False
		self.rotire = False
		self.rotire_vazuta = False
		self.ceasLimita.stop()
		self._numaraAcord(True)
		service = self.nav.getCurrentService()
		canal = self.canal
		rec = din_serviciu(service, self.info_const)
		if rec is not None and canal is not None and canal.cheie_mas:
			self.baza.noteaza(canal.cheie_mas, rec, self.ceasornic(), "v")
			self.citite.add(canal.cheie_mas)
		g = self.grupuri[self.i]
		if self._peRand == self.i:
			# grupul se citeste pe rand (PMT-ul brut n-a mers): canalul urmator din el
			self._urmatorul()
			return
		demux = demux_din_serviciu(service)
		tp = transponder_din_ref(canal.ref) if canal is not None else None
		if demux is None or tp is None:
			self._peRandDinGrup(g)
			return
		dorite = set()
		for c in g.canale:
			t = transponder_din_ref(c.ref)
			if t is not None:
				dorite.add(t[0])
		if not self.cititor.porneste(demux, lambda r: self._laTransponder(g, tp, r), dorite):
			self._peRandDinGrup(g)

	def _peRandDinGrup(self, g):
		"""PMT-ul brut nu merge: celelalte canale cerute din grup se pornesc pe rand (o singura data pe grup)."""
		if self._peRand != self.i:
			self._peRand = self.i
			self.pe_canale = [c for c in g.canale if c is not self.canal and c.cheie_mas not in self.citite
				and not self.protejat(c.ref)]
		self._anunta()
		self._urmatorul()

	def _laTransponder(self, g, tp, rezultat):
		if self.oprit:
			return
		if rezultat is None:
			self._peRandDinGrup(g)
			return
		_sid, ns, tsid, onid = tp
		acum = self.ceasornic()
		for program, rec in rezultat.items():
			cheie = cheie_program(program, ns, tsid, onid)
			self.baza.noteaza(cheie, rec, acum, "p")
		dorite = set(c.cheie_mas for c in g.canale if c.cheie_mas)
		gasite = set(cheie_program(p, ns, tsid, onid) for p in rezultat)
		self.citite |= dorite & gasite
		self._anunta()
		self._urmatorul()

	# ---- reluarea: transponderele terminate, baza si starea pe disc

	def _terminat(self, g):
		"""Transponderul g s-a terminat (citit, fara semnal sau sarit). La SCRIERE_MS de la ultima scriere, daca e ceva
		nou: baza, apoi starea; semnul „ocupat” al paznicului se ia din nou la PAZNIC_REINNOIRE_MS."""
		self.facute.add(cheie_tp(g.tp))
		acum = self.monoton()
		if self.t_grup is not None and not self._sarit:
			fel = "poz" if self.grup_mutat else "tp"
			self.masurat[fel + "_s"] += max(0.0, acum - self.t_grup)
			self.masurat[fel + "_n"] += 1
		self.t_grup = None
		self._sarit = False
		if acum - self.paznic_la >= self.PAZNIC_REINNOIRE_MS / 1000.0:
			self.paznic_la = acum
			_paznicDinNou(self)
		if acum - self.ultima_scriere >= self.SCRIERE_MS / 1000.0:
			if self.facute != self.facute_scrise or self._murdara():
				self.ultima_scriere = acum
				self._punct(None)

	def _murdara(self):
		try:
			return bool(getattr(self.baza, "murdar", False))
		except Exception:
			return False

	def _scrieBaza(self):
		"""Scrierea bazei care nu asteapta pragul (baza unica: salveaza_actualizare; clasa Baza: salveaza). -> True cand
		pistele citite pana acum sunt pe disc sau pe drum spre el (scrierea a pornit, ori nimic nescris)."""
		try:
			if getattr(self.baza, "salveaza_actualizare", self.baza.salveaza)():
				return True
		except Exception as e:
			_jurnal("scriere: %s" % e)
			return False
		return not self._murdara()

	def _punct(self, motiv):
		"""Baza intai, apoi starea reluarii. In stare intra ca facute numai transponderele de dinaintea unei scrieri
		reusite a bazei; o trecere terminata cu baza nescrisa ramane de reluat (motivul OPRIT, nu GATA)."""
		ok = self._scrieBaza()
		if ok:
			self.facute_scrise = set(self.facute)
		elif motiv == GATA:
			motiv = OPRIT
		self._scrieStare(motiv)

	def _scrieStare(self, motiv):
		scrie_stare({"fel": FEL_STARE, "v": 1, "inceput": self.inceput, "actualizat": int(time.time()), "motiv": motiv,
			"facute": sorted(self.facute_scrise)[-MAX_FACUTE:], "total": self.inainte + len(self.grupuri),
			"citite": len(self.citite), "fara_semnal": self.fara_semnal, "sarite": self.sarite,
			"masurat": self.masurat_total()}, self.cale_stare)

	def opreste(self):
		if self.gata:
			return
		self.oprit = True
		self.cititor.opreste()
		self._termina()

	def _termina(self):
		if self.gata:
			return
		self.gata = True
		_paznic(self, False)
		self.asteptare = False
		self.rotire = False
		self.rotire_vazuta = False
		self.ceasLimita.stop()
		self.ceasLiniste.stop()
		self.cititor.opreste()
		try:
			self.nav.event.remove(self._eveniment)
		except ValueError:
			pass
		if self.original is not None:
			try:
				self.nav.playService(self.original, checkParentalControl=False)
			except TypeError:
				self.nav.playService(self.original)
			except Exception as e:
				_jurnal("revenire: %s" % e)
		# baza unica: scrierea fara prag a sfarsitului de trecere (clasa Baza: salveaza()), apoi starea reluarii
		self._punct(OPRIT if self.oprit else GATA)
		if self.la_sfarsit is not None:
			self.la_sfarsit(self.stare())


def text_rezultat(stare):
	"""Ce s-a facut, pentru om, la sfarsitul unei „Actualizari”."""
	citite = stare.get("citite", 0)
	# la zero alta fraza: text_numar(0) e „Niciun canal”, facut pentru inceput de rand
	text = (_("Oprit.") + u" " if stare.get("oprit") else u"") + (_("Pistele citite la %s.") % _X.text_numar(citite)
		if citite > 0 else _("Nicio pistă citită."))
	if stare.get("fara_semnal"):
		n = stare["fara_semnal"]
		text += u" " + _("Fără semnal: %s.") % (ngettext("%d transponder", "%d transpondere", n) % n)
	if stare.get("sarite"):
		text += u" " + _("Sărite (control parental): %s.") % _X.text_numar(stare["sarite"])
	if stare.get("pozitii_sarite"):
		text += u" " + _("Sărite la cererea ta: %s.") % u", ".join(stare["pozitii_sarite"])
	if stare.get("pozitii_fara_semnal"):
		text += u" " + _("Fără semnal pe %d transpondere la rând, restul lăsat: %s.") % (Actualizare.PRAG_FARA_SEMNAL,
			u", ".join(stare["pozitii_fara_semnal"]))
	if stare.get("pozitii_neprinse_goale"):
		text += u" " + _("Tot fără semnal, ca până acum: %s.") % u", ".join(stare["pozitii_neprinse_goale"])
	if stare.get("pozitii_lasate"):
		text += u" " + _("Lăsate, fără semnal niciodată pe acest receptor: %s.") % u", ".join(stare["pozitii_lasate"])
	return text

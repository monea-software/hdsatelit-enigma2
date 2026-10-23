# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HbbTV pe canalul redat: aplicatiile anuntate de AIT-ul citit de nucleu (lib/dvb/pmt.cpp cu lib/dvb/hdsait.cpp) si
aplicatia care se porneste la tasta ROSIE. Nimic pe ecran aici: semnul rosu din bara il deseneaza skinul
(Components/Converter/HdsCommon.hbbtv_rosu -> arata_semn), iar pornirea la ROSU e in Components/HdsHbbtvPornire.py.

SETAREA SEMNULUI (semn_rosu_pornit): config.plugins.hdsnavigator.hbbtv_semn, „Semnul roșu HbbTV în bară” in Setari >
Surse Internet > Setari navigator web (HbbTV ruleaza in acelasi navigator), pornita din fabrica. Deasupra ei setarea
principala „HbbTV” (hbbtv_pornit, 0.2.8): oprita, nu se arata niciun semn si nu porneste nimic.

DE UNDE (iServiceInformation, numai pe canalul redat, nu la inregistrari si la redarea fisierelor):
  sAITPID        PID-ul AIT din PMT: -1 PMT necitit (sau program din cache), 0 fara AIT HbbTV, altfel PID-ul;
  sHBBTVAit      getInfoObject -> {"pid", "versiune", "aplicatii": [...]}: AIT-ul citit pe acel PID (versiunea -1 cat
                 nu s-a citit), cu textele ca octeti (numele cu prefixul de codare DVB);
  evHBBTVInfo    eveniment la un AIT nou, schimbat (alta versiune) sau disparut (PID-ul AIT scos din PMT).
Aceleasi aplicatii, din sectiuni brute: Components/HdsAnalizaFlux.citeste_ait (aceleasi reguli de citire, acelasi
dictionar dupa ait_text), deci restul modulului are o singura forma de aplicatie: "org", "id", "cod", "nume", "limba",
"adresa", "cale", "prioritate", "vizibilitate", "legat", "profile", "etichete", "transporturi", "utilizare",
"limite", "varste".

ALEGEREA LA ROSU (aplicatie_rosu): aplicatia AUTOSTART cu prioritatea cea mai mare, altfel cea PRESENT cu prioritatea
cea mai mare; la egalitate, prima din AIT. KILL, DISABLED si celelalte coduri nu se aleg. Profilul si versiunea ceruta
nu opresc alegerea aici: rezumat() le spune (versiune_ceruta, sustinuta), iar pornirea hotaraste.

ADRESA (url_complet): prima adresa a primului transport HTTP + calea din simple_application_location; o cale care e
deja o adresa intreaga ramane cum e. Adresa se citeste ca in navigator (normalizeaza_adresa): HGTV pe 19,2E are in AIT
"http:/de.container.enhanced.live/hgtv/" (o singura bara), pe care navigatorul o deschide ca "http://...".
numai_carusel: aplicatia are numai transport prin carusel (DSM-CC), fara HTTP.

BAZA CANALELOR (grupa_ap, hb_din_stare; le noteaza Components/HdsCulegereCanale.py): grupa "ap" = [aplicatii de pornit,
autostart 0/1, transportul aplicatiei de la ROSU "h" / "c" / "hc", versiunea AIT, adresa de baza fara parametri,
numele, lista]; "hb" = 1 numai cand AIT-ul citit are o aplicatie de pornit, 0 numai cand PMT-ul nu are AIT HbbTV.
Lista (lista_baza, numai cand AIT-ul are aplicatii de pornit) = fiecare aplicatie AUTOSTART sau PRESENT, cea de la ROSU
intai, apoi in ordinea din AIT: [cod, organisation_id, application_id, transportul ei, adresa completa de pornire
(url_complet, cu parametrii), lungimea adresei cand e taiata la MAX_URL_BAZA (0 = intreaga), numele]; cel mult
MAX_APLICATII_BAZA si cel mult MAX_LISTA_BAZA octeti in forma scrisa in baza (ensure_ascii), taiata de la coada.
Lista are mai putine elemente decat primul camp al grupei = taiata.

STAREA CANALULUI (Urmaritor): evenimentele canalului redat (de la culegerea unita, Components/HdsCulegereCanale.py,
care e singurul ascultator pe nav.event; sau direct din nav.event, cu pe_nav=True) tin stare() la zi, iar ascultatorii
(asculta) se cheama la fiecare schimbare. Partea de sus e curata (fara enigma), deci se probeaza pe PC
(test_hbbtv_ait.py)."""

from __future__ import absolute_import

import json
import re

COD_AUTOSTART, COD_PRESENT, COD_DESTROY, COD_KILL, COD_DISABLED = 0x01, 0x02, 0x03, 0x04, 0x07
PROTOCOL_CARUSEL, PROTOCOL_HTTP = 0x0001, 0x0003
TIP_HBBTV = 0x0010
# HbbTV 1.5 (ETSI TS 102 796 V1.2.1): versiunea pe care o declara navigatorul pana la HTML5 cu video
VERSIUNE_SUSTINUTA = (1, 2, 1)
# partea HbbTV a antetului User-Agent: HbbTV/<versiunea specificatiei> (<capabilitati>; <producator>; <model>;
# <versiunea soft>; <versiunea placii>; <rezervat>) (ETSI TS 102 796 V1.2.1, cap. 7.3.2.4); HbbTV 1.5 = V1.2.1
AGENT_SABLON = "HbbTV/%d.%d.%d (%s; %s; %s; %s; ; )"
# forma cu familia (ETSI TS 102 796 V1.4.1, cap. 7.3.2.4): ... <versiunea placii>; <familia>; <rezervat>)
AGENT_SABLON_FAMILIE = "HbbTV/%d.%d.%d (%s; %s; %s; %s; %s; %s;)"
MAX_ADRESA_BAZA = 120
MAX_NUME_BAZA = 32
# lista aplicatiilor din grupa ap: cate aplicatii, cat de lunga o adresa (cat tine si situl), cati octeti toata lista
MAX_APLICATII_BAZA = 16
MAX_URL_BAZA = 500
MAX_LISTA_BAZA = 2048
CITIRE_MS = 300

_ADRESA_INTREAGA = ("http://", "https://", "dvb://")
# "http:" sau "https:" urmat de oricate "/" sau "\" (si zero), apoi gazda: forma pe care navigatorul o indreapta
_SCHEMA_WEB = re.compile(r"^(https?):[/\\]*(?=[^/\\\s])", re.I)


def _jurnal(text):
	print("[HdsHbbtv] %s" % text)


def hbbtv_pornit(config=None):
	"""Setarea principala „HbbTV” (config.plugins.hdsnavigator.hbbtv, 0.2.8: omul poate opri HbbTV de tot, daca
	i se pare ca ingreuneaza receptorul), OPRITA din fabrica. Oprita: fara semnul rosu, ROSU
	si Portal nu pornesc nimic, pornirea automata nu se face, iar nucleul nu mai citeste AIT-ul (lib/service/servicedvb.cpp
	nu mai cere filtrul). Cat setarea nu exista sau nu se poate citi: oprit."""
	try:
		if config is None:
			from Components.config import config
		return bool(config.plugins.hdsnavigator.hbbtv.value)
	except Exception:
		return False


def semn_rosu_pornit(config=None):
	"""Setarea semnului rosu din bara (config.plugins.hdsnavigator.hbbtv_semn, facuta de
	Plugins/Extensions/HdsNavigator/setari.py la pornire). Cat setarea nu exista: pornit, ca din fabrica."""
	try:
		if config is None:
			from Components.config import config
		return bool(config.plugins.hdsnavigator.hbbtv_semn.value)
	except Exception:
		return True


def _flux():
	"""Components/HdsAnalizaFlux (textele DVB si dictionarul aplicatiei), importat la nevoie."""
	try:
		from Components import HdsAnalizaFlux as A
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsAnalizaFlux as A
	return A


def _int(v, implicit=-1):
	return v if isinstance(v, int) and not isinstance(v, bool) else implicit


def _octeti(v):
	if isinstance(v, (bytes, bytearray)):
		return bytes(v)
	if isinstance(v, str):
		return v.encode("latin-1", "replace")
	return b""


# ---------------------------------------------------------------- aplicatiile din nucleu

def _transport_nucleu(t):
	if not isinstance(t, dict):
		return None
	return {"protocol": _int(t.get("protocol"), 0), "eticheta": _int(t.get("eticheta"), 0),
		"la_distanta": _int(t.get("la_distanta"), 0), "onid": _int(t.get("onid"), 0), "tsid": _int(t.get("tsid"), 0),
		"sid": _int(t.get("sid"), 0), "tag": _int(t.get("tag")),
		"adrese": [_octeti(x) for x in (t.get("adrese") or ())][:8],
		"extensii": [_octeti(x) for x in (t.get("extensii") or ())][:8]}


def _aplicatie_nucleu(a):
	if not isinstance(a, dict):
		return None
	rez = {"org": _int(a.get("org"), 0), "id": _int(a.get("id"), 0), "cod": _int(a.get("cod"), 0),
		"prioritate": _int(a.get("prioritate")), "vizibilitate": _int(a.get("vizibilitate")),
		"legat": _int(a.get("legat")), "utilizare": _int(a.get("utilizare")),
		"nume": _octeti(a.get("nume")), "limba": _octeti(a.get("limba")), "cale": _octeti(a.get("cale")),
		"profile": [list(p)[:4] for p in (a.get("profile") or ()) if isinstance(p, (list, tuple)) and len(p) >= 4],
		"etichete": [x for x in (a.get("etichete") or ()) if _int(x) >= 0],
		"limite": [_octeti(x) for x in (a.get("limite") or ())],
		"varste": [[_octeti(v[0]), _int(v[1], 0)] for v in (a.get("varste") or ()) if isinstance(v, (list, tuple))
			and len(v) >= 2],
		"transporturi": [x for x in (_transport_nucleu(t) for t in (a.get("transporturi") or ())) if x is not None]}
	return _flux().ait_text(rez)


def din_nucleu(d):
	"""Dictionarul nucleului (getInfoObject(sHBBTVAit)) -> {"pid", "versiune", "aplicatii": [aplicatia ca la
	HdsAnalizaFlux.citeste_ait]}; orice forma neasteptata da o lista goala, nu o exceptie."""
	rez = {"pid": -1, "versiune": -1, "aplicatii": []}
	if not isinstance(d, dict):
		return rez
	rez["pid"] = _int(d.get("pid"))
	rez["versiune"] = _int(d.get("versiune"))
	aplicatii = d.get("aplicatii")
	for a in aplicatii if isinstance(aplicatii, (list, tuple)) else ():
		try:
			x = _aplicatie_nucleu(a)
		except Exception as e:
			_jurnal("aplicatia din nucleu: %s" % e)
			x = None
		if x is not None:
			rez["aplicatii"].append(x)
	return rez


def din_sectiuni(sectiuni):
	"""Sectiuni AIT brute (de exemplu dintr-o captura) -> aceeasi forma ca din_nucleu: numai sectiunile HbbTV fara
	test_application_flag, de aceeasi versiune cu prima citita, aplicatiile in ordinea sectiunilor (fara dubluri)."""
	A = _flux()
	rez = {"pid": -1, "versiune": -1, "aplicatii": []}
	vazute = set()
	for s in sectiuni or ():
		t = A.citeste_ait(s)
		if not t or t["tip"] != TIP_HBBTV or t["test"]:
			continue
		if rez["versiune"] < 0:
			rez["versiune"] = t["versiune"]
		elif t["versiune"] != rez["versiune"]:
			continue
		for a in t["aplicatii"]:
			if (a["org"], a["id"]) not in vazute:
				vazute.add((a["org"], a["id"]))
				rez["aplicatii"].append(a)
	return rez


def din_info(info, info_const):
	"""iServiceInformation al canalului redat -> starea AIT: {"pid": sAITPID, "versiune", "aplicatii"}. AIT-ul citit se
	ia numai cand e pe PID-ul din PMT-ul de acum (in timeshift PMT-ul e al fisierului, AIT-ul al canalului viu)."""
	rez = {"pid": -1, "versiune": -1, "aplicatii": []}
	if info is None or info_const is None:
		return rez
	w = getattr(info_const, "sAITPID", None)
	if w is None:
		return rez
	try:
		pid = info.getInfo(w)
	except Exception:
		return rez
	rez["pid"] = _int(pid)
	if rez["pid"] <= 0:
		return rez
	w = getattr(info_const, "sHBBTVAit", None)
	try:
		d = info.getInfoObject(w) if w is not None else None
	except Exception:
		d = None
	ait = din_nucleu(d)
	if ait["pid"] == rez["pid"]:
		rez["versiune"], rez["aplicatii"] = ait["versiune"], ait["aplicatii"]
	return rez


# ---------------------------------------------------------------- alegerea si adresa

def transporturi(a, protocol):
	return [t for t in (a or {}).get("transporturi") or () if t.get("protocol") == protocol]


def numai_carusel(a):
	return bool(transporturi(a, PROTOCOL_CARUSEL)) and not transporturi(a, PROTOCOL_HTTP)


def normalizeaza_adresa(adresa):
	"""O adresa din AIT citita ca de un navigator (WHATWG URL, schemele http si https): spatiile si caracterele de
	control de la capete scoase, tab, CR si LF scoase de oriunde, iar dupa "http:" sau "https:" orice sir de "/" sau
	"\\" devine "//" (unele posturi scriu "http:/gazda/..." cu o singura bara, iar navigatorul o deschide). Schema se
	scrie cu litere mici. Altceva (dvb://, o cale relativa) ramane cum e."""
	if not isinstance(adresa, str) or not adresa:
		return adresa
	u = re.sub(r"[\t\r\n]", u"", adresa).strip(u"".join(chr(i) for i in range(0x21)))
	m = _SCHEMA_WEB.match(u)
	if m is None:
		return u
	return m.group(1).lower() + u"://" + u[m.end():]


def adresa_baza(a):
	"""Prima adresa a primului transport HTTP (in ordinea etichetelor), normalizata ca de navigator, sau ""."""
	for t in transporturi(a, PROTOCOL_HTTP):
		if t.get("adrese"):
			return normalizeaza_adresa(t["adrese"][0])
	return u""


def url_complet(a):
	"""Adresa de pornire a unei aplicatii prin HTTP: URL_base urmat de calea initiala, lipite asa cum sunt (ETSI TS 102
	809 cap. 5.3.6), sau "" fara transport HTTP. O cale care e deja o adresa intreaga ramane cum e. Baza (si o cale
	intreaga) se citesc ca in navigator (normalizeaza_adresa): "http:/gazda/" e "http://gazda/"."""
	baza = adresa_baza(a)
	if not baza:
		return u""
	cale = (a or {}).get("cale") or u""
	if _SCHEMA_WEB.match(cale.lstrip()):
		cale = normalizeaza_adresa(cale)
	if cale.lower().startswith(_ADRESA_INTREAGA):
		return cale
	return baza + cale


def versiune_ceruta(a):
	"""Cea mai mare versiune (major, minor, micro) din profilele aplicatiei, sau None fara application_descriptor."""
	v = [tuple(p[1:4]) for p in (a or {}).get("profile") or () if len(p) >= 4]
	return max(v) if v else None


def de_pornit(aplicatii):
	return [a for a in aplicatii or () if a.get("cod") in (COD_AUTOSTART, COD_PRESENT)]


def aplicatie_rosu(aplicatii):
	"""Aplicatia care porneste la ROSU: AUTOSTART cu prioritatea cea mai mare, altfel PRESENT cu prioritatea cea mai
	mare; la egalitate, prima din AIT. None cand nu e niciuna."""
	for cod in (COD_AUTOSTART, COD_PRESENT):
		alese = [a for a in aplicatii or () if a.get("cod") == cod]
		if alese:
			cea_mai_mare = max(_int(a.get("prioritate")) for a in alese)
			return next(a for a in alese if _int(a.get("prioritate")) == cea_mai_mare)
	return None


def rezumat(stare, versiune_maxima=VERSIUNE_SUSTINUTA):
	"""Starea AIT a canalului -> {"are_hbbtv": True / False / None, "pid", "versiune", "aplicatii", "aleasa",
	"autostart", "url", "numai_carusel", "versiune_ceruta", "sustinuta"}."""
	st = stare or {}
	pid, versiune = _int(st.get("pid")), _int(st.get("versiune"))
	aplicatii = st.get("aplicatii") or []
	a = aplicatie_rosu(aplicatii)
	ceruta = versiune_ceruta(a) if a else None
	if pid == 0:
		are = False
	elif versiune >= 0:
		are = bool(de_pornit(aplicatii))
	else:
		are = None
	return {"are_hbbtv": are, "pid": pid, "versiune": versiune, "aplicatii": len(de_pornit(aplicatii)), "aleasa": a,
		"autostart": bool(a and a.get("cod") == COD_AUTOSTART), "url": url_complet(a) if a else u"",
		"numai_carusel": numai_carusel(a) if a else False, "versiune_ceruta": ceruta,
		"sustinuta": None if ceruta is None else ceruta <= tuple(versiune_maxima)}


def agent_hbbtv(producator, model, versiune, capabilitati="", placa="", familie=""):
	"""Partea HbbTV adaugata la User-Agent-ul navigatorului: versiunea declarata e VERSIUNE_SUSTINUTA (HbbTV 1.5),
	fara capabilitati (+DRM, +PVR, +DL nu sunt in imagine), versiunea placii si campul rezervat goale. Campurile
	pastreaza numai litere, cifre, spatiu si . _ + - (fara ; si paranteze, care ar strica antetul).
	Cu `familie`, forma cu familia (AGENT_SABLON_FAMILIE)."""
	def curat(text, implicit):
		t = re.sub(r"[^A-Za-z0-9 ._+-]", "", str(text or ""))
		return " ".join(t.split())[:40] or implicit
	campuri = tuple(VERSIUNE_SUSTINUTA) + (curat(capabilitati, ""), curat(producator, "HD Satelit"),
		curat(model, "receptor"), curat(versiune, "0"))
	fam = curat(familie, "")
	if fam:
		return AGENT_SABLON_FAMILIE % (campuri + (curat(placa, ""), fam))
	return AGENT_SABLON % campuri


def arata_semn(info, info_const, config=None):
	"""Semnul rosu din bara (HdsInfo HbbtvRosu): AIT-ul citit pe canalul redat are o aplicatie de pornit la ROSU
	(si numai prin carusel: ROSU spune atunci ca nu merge inca) si setarea semnului e pornita."""
	if not hbbtv_pornit(config) or not semn_rosu_pornit(config):
		return False
	return rezumat(din_info(info, info_const))["are_hbbtv"] is True


# ---------------------------------------------------------------- baza canalelor

def hb_din_stare(stare):
	"""1 cand AIT-ul citit are o aplicatie de pornit, 0 cand PMT-ul nu are AIT HbbTV, altfel None (nu se scrie)."""
	st = stare or {}
	pid, versiune = _int(st.get("pid")), _int(st.get("versiune"))
	if pid == 0:
		return 0
	if pid > 0 and versiune >= 0 and de_pornit(st.get("aplicatii")):
		return 1
	return None


def _transport(a):
	return ("h" if transporturi(a, PROTOCOL_HTTP) else "") + ("c" if transporturi(a, PROTOCOL_CARUSEL) else "")


def _json(valoare):
	# forma in care o scrie baza (HdsBazaCanale._json): marimea listei se masoara asa
	return json.dumps(valoare, separators=(",", ":"), ensure_ascii=True)


def aplicatie_baza(a):
	"""O aplicatie din lista grupei ap: [cod, organisation_id, application_id, transport, adresa completa de pornire,
	lungimea ei cand e taiata la MAX_URL_BAZA (0 = intreaga), numele]. Adresa e url_complet ("" fara transport HTTP)."""
	adresa = url_complet(a)
	lungime = 0
	if len(adresa) > MAX_URL_BAZA:
		adresa, lungime = adresa[:MAX_URL_BAZA], len(adresa)
	return [_int(a.get("cod"), 0), _int(a.get("org"), 0), _int(a.get("id"), 0), _transport(a), adresa, lungime,
		(a.get("nume") or u"")[:MAX_NUME_BAZA]]


def lista_baza(aplicatii):
	"""Aplicatiile de pornit (AUTOSTART si PRESENT) pentru grupa ap: cea de la ROSU intai, apoi celelalte in ordinea din
	AIT; cel mult MAX_APLICATII_BAZA, iar lista scrisa (_json) cel mult MAX_LISTA_BAZA octeti, taiata de la coada. Prima
	intra mereu (o aplicatie are cel mult ~700 de octeti)."""
	rosu = aplicatie_rosu(aplicatii)
	if rosu is None:
		return []
	lista = []
	for a in ([rosu] + [x for x in de_pornit(aplicatii) if x is not rosu])[:MAX_APLICATII_BAZA]:
		e = aplicatie_baza(a)
		if lista and len(_json(lista + [e])) > MAX_LISTA_BAZA:
			break
		lista.append(e)
	return lista


def grupa_ap(stare):
	"""Grupa "ap" a bazei (Components/HdsBazaCanale.py), sau None cat AIT-ul nu s-a citit. Cu aplicatii de pornit are
	si lista aplicatiilor (lista_baza) pe pozitia 6; pozitiile 0-5 raman ca inainte."""
	st = stare or {}
	pid, versiune = _int(st.get("pid")), _int(st.get("versiune"))
	if pid == 0:
		return [0, 0, "", -1, "", ""]
	if pid < 0 or versiune < 0:
		return None
	aplicatii = st.get("aplicatii") or []
	a = aplicatie_rosu(aplicatii)
	transport = _transport(a) if a is not None else ""
	adresa = adresa_baza(a).split("?", 1)[0].split("#", 1)[0][:MAX_ADRESA_BAZA] if a else ""
	nume = (a.get("nume") or "")[:MAX_NUME_BAZA] if a else ""
	rez = [len(de_pornit(aplicatii)), 1 if any(x.get("cod") == COD_AUTOSTART for x in aplicatii) else 0, transport,
		versiune, adresa, nume]
	lista = lista_baza(aplicatii)
	if lista:
		rez.append(lista)
	return rez


def grupe_baza(stare):
	"""{"hb": .., "ap": ..} numai cu ce se stie (pentru HdsBazaCanale.actualizeaza)."""
	grupe = {}
	hb = hb_din_stare(stare)
	if hb is not None:
		grupe["hb"] = hb
	ap = grupa_ap(stare)
	if ap is not None:
		grupe["ap"] = ap
	return grupe


# ---------------------------------------------------------------- canalul redat

class Urmaritor(object):
	"""Starea AIT a canalului redat, tinuta la zi din evenimentele lui (eveniment(ev)): evStart / evEnd o golesc,
	evUpdatedInfo si evHBBTVInfo o recitesc (dupa CITIRE_MS, o singura data pentru mai multe evenimente apropiate).
	pe_nav=True: se pune singur in nav.event. asculta(f): f(stare) la fiecare schimbare, pe firul enigma2."""

	def __init__(self, nav, evenimente=None, info_const=None, fabrica_ceas=None, pe_nav=True):
		if evenimente is None:
			from enigma import iPlayableService as evenimente
		if info_const is None:
			from enigma import iServiceInformation as info_const
		self.nav = nav
		self.ev = evenimente
		self.info_const = info_const
		self._ev_citire = tuple(x for x in (getattr(evenimente, n, None) for n in ("evUpdatedInfo", "evHBBTVInfo"))
			if x is not None)
		self._ev_gol = tuple(x for x in (getattr(evenimente, n, None) for n in ("evStart", "evEnd")) if x is not None)
		self._ascultatori = []
		self._stare = self._gol()
		self.citiri = 0
		if fabrica_ceas is None:
			from enigma import eTimer as fabrica_ceas
		self.ceas = fabrica_ceas()
		self.ceas.callback.append(self._citeste)
		self.pe_nav = pe_nav
		if pe_nav:
			nav.event.append(self.eveniment)

	@staticmethod
	def _gol(ref=""):
		return {"ref": ref, "pid": -1, "versiune": -1, "aplicatii": []}

	def eveniment(self, ev):
		# chemat din C++ (Navigation.dispatchEvent, fara try) sau din ascultatorul culegerii: nicio exceptie nu iese
		try:
			if ev in self._ev_gol:
				self.ceas.stop()
				self._pune(self._gol())
			elif ev in self._ev_citire:
				self.ceas.start(CITIRE_MS, True)
		except Exception as e:
			_jurnal("eveniment %s: %s" % (ev, e))

	def _citeste(self):
		try:
			self.citiri += 1
			ref = self.nav.getCurrentlyPlayingServiceReference()
			service = self.nav.getCurrentService()
			text = ref.toString() if ref is not None else ""
			st = din_info(service.info() if service is not None else None, self.info_const)
			st["ref"] = text
			self._pune(st)
		except Exception as e:
			_jurnal("citirea AIT: %s" % e)

	@staticmethod
	def _semn(st):
		return (st.get("ref"), st.get("pid"), st.get("versiune"),
			tuple((a.get("org"), a.get("id"), a.get("cod"), url_complet(a)) for a in st.get("aplicatii") or ()))

	def _pune(self, st):
		if self._semn(st) == self._semn(self._stare):
			return
		self._stare = st
		r = rezumat(st)
		if r["aleasa"] is not None:
			_jurnal("AIT v%d pe PID %d: %d aplicatii de pornit, la ROSU %s (%s)" % (r["versiune"], r["pid"],
				r["aplicatii"], r["url"] or (u"carusel" if r["numai_carusel"] else u"fara adresa"), r["aleasa"]["nume"]))
		for f in list(self._ascultatori):
			try:
				f(dict(st))
			except Exception as e:
				_jurnal("ascultatorul starii: %s" % e)

	def stare(self):
		return dict(self._stare)

	def rezumat(self):
		return rezumat(self._stare)

	def asculta(self, functie):
		if functie not in self._ascultatori:
			self._ascultatori.append(functie)

	def nu_mai_asculta(self, functie):
		while functie in self._ascultatori:
			self._ascultatori.remove(functie)

	def opreste(self):
		self.ceas.stop()
		if self.pe_nav:
			try:
				self.nav.event.remove(self.eveniment)
			except ValueError:
				pass


_URMARITOR = []


def porneste(session, pe_nav=True):
	"""O singura data: urmaritorul canalului redat (Components/HdsCulegereCanale.porneste il cere cu pe_nav=False si
	ii da evenimentele). -> urmaritorul."""
	if not _URMARITOR:
		_URMARITOR.append(Urmaritor(session.nav, pe_nav=pe_nav))
	return _URMARITOR[0]


def urmaritor():
	"""Urmaritorul pornit, sau None."""
	return _URMARITOR[0] if _URMARITOR else None

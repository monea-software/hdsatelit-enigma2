# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ghid_web.py: „Ghidul canalului” in interfata web (HdsWebControl), perechea primei pagini a celei de-a doua bare.
#
# Pe televizor: OK de doua ori pe un canal; prima pagina a barei e ghidul canalului (lista emisiunilor, emisiunea
# aleasa cu descrierea, temporizatorul si inregistrarea). Aici: aceeasi lista, aceleasi detalii, acelasi
# temporizator, pentru canalul de pe televizor sau pentru orice canal dat prin referinta (pagina Canale).
#
# O SINGURA LOGICA: randurile vin din cache-ul EPG al imaginii prin aceleasi functii ca bara
# (Components/Converter/HdsCommon.py: _epg_read, epg_lookup_id, event_line, epg_timer_for), temporizatoarele prin
# Components/HdsTemporizare.py (fara nicio fereastra pe televizor). Dupa o schimbare, bara de pe televizor (daca e
# deschisa pe ghid) primeste randul scurt din banda si se redeseneaza; nu se deschide niciun ecran.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/ghid?ref=&de_la=&cate=                 emisiunile de la `de_la` (implicit acum), cel mult 50, 7 zile
#   GET  /api/ghid-emisiune?ref=&id=                 o emisiune, cu descrierile
#   POST /api/ghid-temporizator?ref=&id=&fel=inregistrare|comutare|scoate
#                                                    pune sau scoate temporizatorul; 409 la suprapunere, cu lista
#   GET  /ghid[?ref=]                                pagina
# Fara `ref` se foloseste canalul de pe televizor. Pornirea canalului din pagina foloseste ruta existenta
# POST /api/zap?sRef= (ZapResource din plugin.py).
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; o cerere citeste cel mult cateva bucati de 24 de ore din
# cache (C++), fara disc si fara retea. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau
# modulele lor (C = HdsCommon, T = HdsTemporizare, E = HdsTraducereEpg) si navigatia lor.
#
# TRADUCEREA GHIDULUI („Tradu EPG”, Components/HdsTraducereEpg.py, aceeasi memorie ca pe televizor): titlurile din lista
# si titlul si descrierile emisiunii alese vin traduse cand traducerea e in memorie; altfel originalul, iar textul
# pleaca la traducere (raspunsul spune cate sunt in lucru, „in_lucru”, si pagina cere din nou dupa putin). Originalul
# ramane in raspuns („titlu_original”, „scurta_original”, „lunga_original”) pentru butonul „Textul original”.

import re
import time

MAX_CATE = 50
IMPLICIT_CATE = 30
ZILE = 7
BUCATA_MIN = 1440
MAX_REF = 600
MAX_TEXT = 2400

_REF = re.compile(r"^\d{1,4}:\d{1,5}(:[0-9A-Fa-f]{1,8}){8}:")
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f\ud800-\udfff]")
FELURI = ("inregistrare", "comutare", "scoate")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _c(C=None):
	if C is not None:
		return C
	from Components.Converter import HdsCommon
	return HdsCommon


def _epg(E=None):
	if E is not None:
		return E
	try:
		from Components import HdsTraducereEpg
		return HdsTraducereEpg
	except Exception:
		return None


def _tradus(E, fel, text):
	"""(textul de aratat, tradus, in_lucru) prin traducerea ghidului; fara ea, originalul"""
	if E is None or not text:
		return text, False, False
	try:
		t, stare = E.traducere(fel, text, None, False)
	except Exception:
		return text, False, False
	return t, stare == "tradus", stare == "lucru"


def _tm(T=None):
	if T is not None:
		return T
	from Components import HdsTemporizare
	return HdsTemporizare


def _nav(nav=None):
	if nav is not None:
		return nav
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def curat(text, n=MAX_TEXT):
	"""Text venit din satelit, pentru JSON: fara caractere de control, taiat; pagina il pune numai ca text."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return ""
	return _CONTROL.sub(u" ", t)[:n].strip()


def _curat_randuri(text, n=MAX_TEXT):
	"""Ca `curat`, dar randurile raman (textul scurt mutat la descriere, 0.7.5 EPI)."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return ""
	randuri = [_CONTROL.sub(u" ", x).strip() for x in t.replace(u"\r", u"\n").split(u"\n")]
	return u"\n".join(x for x in randuri if x)[:n].strip()


def _ref_valid(ref):
	return bool(ref) and len(ref) <= MAX_REF and bool(_REF.match(ref))


def _ref_acum(nav):
	"""(referinta, nume) a canalului de pe televizor, sau ("", "")."""
	nav = _nav(nav)
	try:
		r = nav.getCurrentlyPlayingServiceReference()
		if r is None:
			return "", ""
		ref = r.toString()
		nume = ""
		try:
			s = nav.getCurrentService()
			i = s and s.info()
			nume = i.getName() if i else ""
		except Exception:
			nume = ""
		return ref, curat(nume, 128)
	except Exception:
		return "", ""


def _nume_serviciu(ref):
	try:
		from enigma import eServiceCenter, eServiceReference
		i = eServiceCenter.getInstance().info(eServiceReference(ref))
		return curat(i.getName(eServiceReference(ref)) if i else "", 128)
	except Exception:
		return ""


def _eit(C, nav, ref):
	"""Acum si urmeaza din serviciul de pe televizor (cand cache-ul nu are nimic), ca dictionare ev_dict."""
	nav = _nav(nav)
	try:
		cur = nav.getCurrentlyPlayingServiceReference()
		if cur is None or C.norm_ref(cur.toString()) != C.norm_ref(ref):
			return []
		i = nav.getCurrentService().info()
		out = []
		for n in (0, 1):
			ev = C.ev_dict(i.getEvent(n))
			if ev and ev["begin"] > 0:
				out.append(ev)
		return out
	except Exception:
		return []


def _zi(C, t, acum):
	"""„Azi”, „Mâine” sau numele zilei, dupa ceasul receptorului (aceleasi texte ca bara)."""
	try:
		a = time.localtime(acum)
		b = time.localtime(t)
		import datetime
		d = (datetime.date(b.tm_year, b.tm_mon, b.tm_mday) - datetime.date(a.tm_year, a.tm_mon, a.tm_mday)).days
		if d == 0:
			return C.tr("epg_today")
		if d == 1:
			return C.tr("epg_tomorrow")
		return C.tr("day_long_%d" % b.tm_wday)
	except Exception:
		return ""


def _fel_temporizator(C, ref, eid, begin, dur, timers):
	t = C.epg_timer_for(ref, eid, begin, dur, timers)
	if t is None:
		return ""
	return "comutare" if getattr(t, "justplay", False) else "inregistrare"


def _intreg(v, implicit):
	try:
		return int(str(v).strip())
	except Exception:
		return implicit


def lista(argumente_, C=None, nav=None, acum=None, E=None):
	"""GET /api/ghid -> (cod, corp)."""
	C = _c(C)
	E = _epg(E)
	acum = int(time.time() if acum is None else acum)
	ref = argumente_.get("ref") or ""
	nume = ""
	if not ref:
		ref, nume = _ref_acum(nav)
		if not ref:
			return 409, {"result": False, "message": _t("Nu rulează niciun canal pe televizor.")}
	if not _ref_valid(ref):
		return 400, {"result": False, "message": _t("Canalul nu are o referință bună."), "camp": "ref"}
	cate = max(1, min(MAX_CATE, _intreg(argumente_.get("cate"), IMPLICIT_CATE)))
	de_la = _intreg(argumente_.get("de_la"), 0)
	sfarsit_permis = acum + ZILE * 86400
	if de_la > sfarsit_permis:
		return 400, {"result": False, "message": _t("Ghidul are cel mult 7 zile."), "camp": "de_la"}
	start = max(de_la, acum)
	randuri = []
	vazute = set()
	pas = start
	while len(randuri) < cate and pas < sfarsit_permis:
		bucata = C._epg_read(ref, pas if pas > acum else -1, BUCATA_MIN)
		noi = [x for x in bucata if x[0] not in vazute and x[1] + max(x[2], 1) > start]
		for x in noi:
			vazute.add(x[0])
			randuri.append(x)
		if not bucata:
			pas += BUCATA_MIN * 60
			continue
		ultim = bucata[-1]
		urm = ultim[1] + max(ultim[2], 60)
		if urm <= pas:
			break
		pas = urm
	randuri.sort(key=lambda x: x[1])
	if not randuri and not de_la:
		randuri = [(e["id"], e["begin"], e["dur"], e["name"]) for e in _eit(C, nav, ref)]
	mai_sunt = len(randuri) > cate
	randuri = randuri[:cate]
	timers = C._timer_list()
	emisiuni = []
	in_lucru = 0
	for eid, begin, dur, titlu in randuri:
		original = curat(titlu, 200)
		arata, tradus, lucru = _tradus(E, "titlu", original)
		in_lucru += 1 if lucru else 0
		emisiuni.append({
			"id": eid,
			"inceput": begin,
			"durata": dur,
			"titlu": curat(arata, 200),
			"titlu_original": original if tradus else "",
			"ora": C.hhmm(begin),
			"zi": _zi(C, begin, acum),
			"acum": begin <= acum < begin + max(dur, 1),
			"temporizator": _fel_temporizator(C, ref, eid, begin, dur, timers),
		})
	urmatorul = 0
	if emisiuni and (mai_sunt or len(emisiuni) == cate):
		u = randuri[-1]
		urmatorul = u[1] + max(u[2], 60)
		if urmatorul > sfarsit_permis:
			urmatorul = 0
	return 200, {"result": True, "ref": ref, "nume": nume or _nume_serviciu(ref), "acum": acum,
		"emisiuni": emisiuni, "urmatorul": urmatorul, "in_lucru": in_lucru}


def _emisiunea(C, nav, ref, eid):
	ev = C.epg_lookup_id(ref, eid)
	if ev:
		return ev
	for e in _eit(C, nav, ref):
		if e["id"] == eid:
			return e
	return None


def _scurta(C, ev):
	"""Textul scurt ca pe televizor: un rand, fara titlul repetat, randurile din EIT unite cu „ · ”."""
	if ev["short"] == ev["name"]:
		return ""
	fn = getattr(C, "epg_short_line", None)
	return curat(fn(ev) if fn is not None else ev["short"])


def emisiune(argumente_, C=None, nav=None, E=None):
	"""GET /api/ghid-emisiune -> (cod, corp)."""
	C = _c(C)
	E = _epg(E)
	ref = argumente_.get("ref") or _ref_acum(nav)[0]
	if not _ref_valid(ref):
		return 400, {"result": False, "message": _t("Canalul nu are o referință bună."), "camp": "ref"}
	eid = _intreg(argumente_.get("id"), -1)
	if eid < 0:
		return 400, {"result": False, "message": _t("Nu s-a cerut nicio emisiune."), "camp": "id"}
	ev = _emisiunea(C, nav, ref, eid)
	if not ev:
		return 404, {"result": False, "message": _t("Emisiunea nu mai e în ghid.")}
	fn = getattr(C, "epg_descrieri", None)
	if fn is not None:
		# aceeasi decizie ca pe televizor (0.7.5, EPI): textul scurt care nu incape pe randul lui trece la descriere cand
		# descrierea lunga lipseste; randurile lui din EIT raman (pagina le arata cu pre-wrap)
		scurta, lunga = fn(ev)
		din_scurt = bool(lunga) and lunga != ev["ext"]
		texte = {"titlu": curat(ev["name"], 200), "scurta": curat(scurta),
			"lunga": _curat_randuri(lunga) if din_scurt else curat(lunga)}
	else:
		din_scurt = False
		texte = {"titlu": curat(ev["name"], 200), "scurta": _scurta(C, ev),
			"lunga": curat(ev["ext"]) if ev["ext"] not in (ev["short"], ev["name"]) else ""}
	traduse = {}
	in_lucru = 0
	for camp, fel in (("titlu", "titlu"), ("scurta", "scurta"), ("lunga", "lunga")):
		arata, tradus, lucru = _tradus(E, fel, texte[camp])
		if camp == "lunga" and din_scurt:
			traduse[camp] = _curat_randuri(arata)
		else:
			traduse[camp] = curat(arata, 200 if camp == "titlu" else MAX_TEXT)
		traduse[camp + "_original"] = texte[camp] if tradus else ""
		in_lucru += 1 if lucru else 0
	return 200, {"result": True, "ref": ref, "in_lucru": in_lucru, "emisiune": {
		"id": ev["id"],
		"titlu": traduse["titlu"],
		"titlu_original": traduse["titlu_original"],
		"scurta": traduse["scurta"],
		"scurta_original": traduse["scurta_original"],
		"lunga": traduse["lunga"],
		"lunga_original": traduse["lunga_original"],
		"inceput": ev["begin"],
		"durata": ev["dur"],
		"linie": C.event_line(ev),
		"temporizator": _fel_temporizator(C, ref, ev["id"], ev["begin"], ev["dur"], C._timer_list()),
	}}


def _anunta(C, text):
	"""Randul scurt din banda barei de pe televizor, daca e deschisa pe ghid; nicio fereastra."""
	try:
		C.epg_note_set(text)
		C.page_refresh(C.EPG_PAGE)
	except Exception:
		pass


def _locInregistrarii():
	"""Unde se va salva o inregistrare tocmai programata (Components/HdsInregistrariProgramate.textLocProgramare: aceeasi
	logica si aceleasi texte ca ecranul „Locul înregistrărilor” si pagina /stocare), sau „” fara el."""
	try:
		from Components import HdsInregistrariProgramate
		return HdsInregistrariProgramate.textLocProgramare()
	except Exception:
		return ""


def temporizator(argumente_, C=None, T=None, nav=None, rt=None, fabrica=None):
	"""POST /api/ghid-temporizator -> (cod, corp). Nu deschide nimic pe televizor."""
	C = _c(C)
	T = _tm(T)
	ref = argumente_.get("ref") or _ref_acum(nav)[0]
	if not _ref_valid(ref):
		return 400, {"result": False, "message": _t("Canalul nu are o referință bună."), "camp": "ref"}
	fel = argumente_.get("fel") or ""
	if fel not in FELURI:
		return 400, {"result": False, "message": _t("Felul temporizatorului nu e cunoscut."), "camp": "fel"}
	eid = _intreg(argumente_.get("id"), -1)
	ev = _emisiunea(C, nav, ref, eid) if eid >= 0 else None
	if not ev:
		return 404, {"result": False, "message": _t("Emisiunea nu mai e în ghid.")}
	existent = T.cauta(ref, ev, rt)
	if fel == "scoate":
		if existent is None:
			return 404, {"result": False, "message": _t("Emisiunea nu are temporizator.")}
		if not T.scoate(existent, rt, anunta=True):
			return 500, {"result": False, "message": _t("Temporizatorul nu s-a putut scoate.")}
		_anunta(C, C.tr("epg_timer_removed").replace(u"{0}", curat(ev["name"], 80)))
		return 200, {"result": True, "message": _t("Temporizatorul a fost scos.")}
	if existent is not None:
		return 409, {"result": False, "message": _t("Emisiunea are deja un temporizator."), "suprapuse": []}
	rez, x = T.inregistreaza(ref, ev, justplay=(fel == "comutare"), rt=rt, fabrica=fabrica)
	if rez == T.REZULTAT_PUS:
		cheie = "epg_timer_set" if fel == "comutare" else "epg_rec_set"
		_anunta(C, C.tr(cheie).replace(u"{0}", curat(ev["name"], 80)))
		# unde se va salva (sau ce e de facut fara disc): cine programeaza de pe telefon nu vede televizorul
		loc = "" if fel == "comutare" else _locInregistrarii()
		return 200, {"result": True, "message": " ".join(x for x in (_t("Temporizatorul a fost pus."), loc) if x),
			"loc": loc}
	if rez == T.REZULTAT_SUPRAPUS:
		lista_s = []
		for t in (x or [])[:10]:
			try:
				lista_s.append({"nume": curat(getattr(t, "name", ""), 120), "inceput": int(t.begin), "sfarsit": int(t.end)})
			except Exception:
				continue
		return 409, {"result": False, "message": _t("Se suprapune cu alte temporizatoare. Nu s-a pus nimic."),
			"suprapuse": lista_s}
	return 500, {"result": False, "message": _t("Temporizatorul nu s-a putut pune.")}


# ---------------------------------------------------------------- ghidul grafic (grila canale x ore, RW2 26.11.2026)
# Perechea ecranului Screens/HdsGhidGrafic.py, cu aceeasi logica (Components/HdsGhidGrila.py): un singur apel la cache
# pentru canalele cerute si fereastra de ore. GET /api/ghid-grila?buchet=&de_la=&ore=&de=&cate=
#   buchet: referinta buchetului (implicit cel din lista de pe televizor, altfel primul); de_la: inceputul ferestrei
#   (aliniat la jumatate de ora, nu inainte de acum); ore: 1-6 (implicit 3); de, cate: randurile (cel mult 40 odata).
GRILA_MAX_CANALE = 40
GRILA_IMPLICIT_CANALE = 20
GRILA_MAX_ORE = 6
GRILA_IMPLICIT_ORE = 3
_BUCHETE_TV = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet'
_VIATA_CANALE = 60


class SursaCanale(object):
	"""Buchetele si canalele lor din lista de pe receptor (eServiceCenter); canalele unui buchet tinute 60 s."""

	def __init__(self):
		self._canale = {}

	def _lista(self, ref):
		from enigma import eServiceCenter, eServiceReference
		lista = eServiceCenter.getInstance().list(eServiceReference(ref))
		rez = []
		if lista is None:
			return rez
		while True:
			s = lista.getNext()
			if not s.valid():
				break
			rez.append(s)
		return rez

	def buchete(self):
		from enigma import eServiceCenter, eServiceReference
		rez = []
		try:
			for s in self._lista(_BUCHETE_TV):
				if s.flags & eServiceReference.isDirectory:
					i = eServiceCenter.getInstance().info(s)
					rez.append((s.toString(), curat(i.getName(s) if i else "", 128)))
		except Exception as e:
			print("[HdsWebControl] ghid grila buchete: %s" % e)
		return rez

	def buchetulTv(self):
		"""buchetul listei de pe televizor (radacina listei de canale), sau ''"""
		try:
			from Screens.InfoBar import InfoBar
			r = InfoBar.instance.servicelist.getRoot()
			return r.toString() if r is not None else ""
		except Exception:
			return ""

	def canale(self, buchet):
		"""[(ref pentru cache, ref intreaga, numele)] fara dosare si semne"""
		acum = time.time()
		e = self._canale.get(buchet)
		if e is not None and 0 <= acum - e[0] < _VIATA_CANALE:
			return e[1]
		from enigma import eServiceCenter, eServiceReference
		rez = []
		centru = eServiceCenter.getInstance()
		for s in self._lista(buchet):
			if s.flags & (eServiceReference.isDirectory | eServiceReference.isMarker):
				continue
			i = centru.info(s)
			rez.append((s.toCompareString(), s.toString(), i.getName(s) if i else ""))
		if len(self._canale) > 8:
			self._canale.clear()
		self._canale[buchet] = (acum, rez)
		return rez


_SURSA = [None]


def _sursa(S=None):
	if S is not None:
		return S
	if _SURSA[0] is None:
		_SURSA[0] = SursaCanale()
	return _SURSA[0]


def _grila_logica():
	from Components import HdsGhidGrila
	return HdsGhidGrila


def _cache_epg(C):
	f = getattr(C, "epg_cache", None)
	if f is not None:
		return f()
	from enigma import eEPGCache
	return eEPGCache.getInstance()


def grila(argumente_, C=None, S=None, epg=None, acum=None, E=None, GL=None):
	"""GET /api/ghid-grila -> (cod, corp)."""
	C = _c(C)
	E = _epg(E)
	S = _sursa(S)
	GL = GL or _grila_logica()
	acum = int(time.time() if acum is None else acum)
	buchete = S.buchete()
	buchet = argumente_.get("buchet") or ""
	if buchet and buchet not in [b[0] for b in buchete]:
		return 400, {"result": False, "message": _t("Buchetul nu e în lista receptorului."), "camp": "buchet"}
	if not buchet:
		tv = S.buchetulTv()
		buchet = tv if tv in [b[0] for b in buchete] else (buchete[0][0] if buchete else "")
	if not buchet:
		return 409, {"result": False, "message": _t("Receptorul nu are niciun buchet de canale.")}
	ore = max(1, min(GRILA_MAX_ORE, _intreg(argumente_.get("ore"), GRILA_IMPLICIT_ORE)))
	minim = GL.aliniaza(acum)
	de_la = _intreg(argumente_.get("de_la"), 0)
	if de_la > acum + ZILE * 86400:
		return 400, {"result": False, "message": _t("Ghidul are cel mult 7 zile."), "camp": "de_la"}
	t0 = max(minim, GL.aliniaza(de_la)) if de_la else minim
	t1 = t0 + ore * 3600
	de = max(0, _intreg(argumente_.get("de"), 0))
	cate = max(1, min(GRILA_MAX_CANALE, _intreg(argumente_.get("cate"), GRILA_IMPLICIT_CANALE)))
	toate = S.canale(buchet)
	felie = toate[de:de + cate]
	date = GL.citeste(epg if epg is not None else _cache_epg(C), [c[0] for c in felie], t0, t1)
	timers = C._timer_list()
	marcaje = GL.marcajeTemporizatoare(timers)
	canale = []
	in_lucru = 0
	for n, (cheie, ref, nume) in enumerate(felie):
		emisiuni = []
		for e in GL.vizibile(date.get(cheie, []), t0, t1):
			original = curat(e[3], 200)
			arata, tradus, lucru = _tradus(E, "titlu", original)
			in_lucru += 1 if lucru else 0
			emisiuni.append({
				"id": e[0], "inceput": e[1], "durata": e[2], "titlu": curat(arata, 200),
				"titlu_original": original if tradus else "", "ora": C.hhmm(e[1]),
				"acum": e[1] <= acum < GL.sfarsitul(e), "temporizator": GL.felTemporizator(marcaje, cheie, e),
			})
		canale.append({"ref": ref, "numar": de + n + 1, "nume": curat(nume, 128), "emisiuni": emisiuni})
	return 200, {"result": True, "acum": acum, "t0": t0, "t1": t1, "ore": ore, "minim": minim,
		"zi": _zi(C, t0, acum), "marcaje": [{"t": t, "text": text} for t, text in GL.ore(t0, t1)],
		"buchet": buchet, "buchete": [{"ref": r, "nume": nm} for r, nm in buchete],
		"nume_buchet": next((nm for r, nm in buchete if r == buchet), ""), "de": de, "total": len(toate),
		"canale": canale, "in_lucru": in_lucru}


def argumente(request):
	"""Argumentele cererii ca text: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = ("ref", "de_la", "cate", "id", "fel", "buchet", "ore", "de")
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v).strip()
	return rez


def rute(baza, resource, C=None, T=None, nav=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class _Citire(baza):
		lucru = None

		def render_GET(self, request):
			try:
				cod, corp = type(self).lucru(argumente(request), C=C, nav=nav)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] ghid: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class GhidResource(_Citire):
		lucru = staticmethod(lista)

	class EmisiuneResource(_Citire):
		lucru = staticmethod(emisiune)

	class TemporizatorResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				cod, corp = temporizator(argumente(request), C=C, T=T, nav=nav)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] ghid temporizator: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class GrilaResource(_Citire):
		lucru = staticmethod(grila)

	class PaginaResource(resource.Resource):
		"""GET /ghid: pagina „Ghidul canalului”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	class PaginaGraficResource(resource.Resource):
		"""GET /ghid-grafic: pagina 'Ghid grafic' (grila canale x ore)."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request, grafic=True)

	global PAGINA_GRAFIC_RESURSA
	PAGINA_GRAFIC_RESURSA = PaginaGraficResource()
	api = {
		b"ghid": GhidResource(),
		b"ghid-emisiune": EmisiuneResource(),
		b"ghid-temporizator": TemporizatorResource(),
		b"ghid-grila": GrilaResource(),
	}
	return api, PaginaResource()


PAGINA_GRAFIC_RESURSA = None


def pagina(request, grafic=False):
	"""Aceeasi poarta ca /limbi si /paznic."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina, grafic).encode("utf-8", "replace")


def pagina_text(stil, config_pagina, grafic=False):
	text = _traducePagina(PAGINA_GRAFIC) if grafic else _traducePagina(PAGINA)
	return text.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghidul canalului</title>
<style>__STIL_COMUN__
  main{max-width:980px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 6px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:0 0 12px;}
  .doua{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;}
  .rand{display:flex;gap:10px;align-items:center;padding:9px 8px;border-bottom:1px solid var(--bordura);cursor:pointer;min-height:44px;border-radius:6px;}
  .rand:last-child{border-bottom:0;}
  .rand.ales{background:#1c3a5c;}
  .rand .ora{min-width:92px;color:var(--text-slab);font-variant-numeric:tabular-nums;}
  .rand .titlu{flex:1;word-break:break-word;}
  .rand.acum .ora{color:#ffc34d;font-weight:bold;}
  .semn{width:12px;height:12px;border-radius:2px;flex:none;}
  .semn.inregistrare{background:#e0453a;}
  .semn.comutare{background:#ffc34d;}
  .zi{color:var(--text-slab);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;padding:10px 8px 4px;}
  .cand{color:var(--text-slab);font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px;}
  .titlu-mare{font-size:1.2rem;font-weight:bold;margin:0 0 6px;word-break:break-word;}
  .linie{color:#ffc34d;margin:0 0 10px;}
  .text{white-space:pre-wrap;line-height:1.45;margin:0 0 10px;word-break:break-word;}
  .descriere{max-height:20rem;overflow:auto;overscroll-behavior:contain;}
  .slab{color:var(--text-slab);}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.rosu{background:#b3322a;border-color:#b3322a;color:#fff;}
  button.verde{background:#1f7a44;border-color:#1f7a44;color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .tradus{color:var(--text-slab);font-size:.85rem;margin:0 0 8px;}
  @media (max-width:720px){ .doua{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1 id="canal">Ghidul canalului</h1>
<p class="slab" id="incarcare">Se citește ghidul...</p>
<div class="butoane ascuns" id="bara-traducere"><button type="button" id="original">Textul original</button><span class="tradus" id="nota-traducere">Tradus automat.</span></div>
<div id="continut" class="doua ascuns">
  <section class="card" aria-live="polite">
    <p class="cand" id="cand"></p>
    <p class="titlu-mare" id="titlu"></p>
    <p class="linie" id="linie"></p>
    <div class="descriere" id="descriere" tabindex="0" aria-labelledby="titlu">
      <p class="text" id="scurta"></p>
      <p class="text slab" id="lunga"></p>
    </div>
    <div class="butoane">
      <button type="button" class="rosu" id="inregistreaza">Înregistrează</button>
      <button type="button" id="comuta">Doar comutare la ora ei</button>
      <button type="button" id="scoate" class="ascuns">Scoate temporizatorul</button>
      <button type="button" class="verde" id="porneste">Pornește canalul pe televizor</button>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card">
    <div id="lista"></div>
    <div class="butoane"><button type="button" id="mai">Mai departe</button></div>
  </section>
</div>
<p class="slab">Pe televizor: apasă OK de două ori pe un canal; prima pagină a barei este ghidul canalului.</p>
<p class="slab"><a href="/ghid-grafic">Ghid grafic: toate canalele buchetului, pe ore</a></p>
</main>
<script>
var CFG = __CONFIG__;
var REF = new URLSearchParams(location.search).get("ref") || "";
var DATE = null, ALES = null, EMISIUNI = [], URMATORUL = 0;
var ORIGINAL = false, DETALII = null, INCERCARI_LISTA = 0, INCERCARI_EMISIUNE = 0, ASTEAPTA_MS = 1500, MAX_INCERCARI = 8;
// Derularea descrierii: un singur ceas, numai cand textul nu incape.
var CEAS_DESCRIERE = 0, DESCRIERE_PAUSA = false, DESCRIERE_TEXT = "";
function opresteDescriere(){
  if(CEAS_DESCRIERE){ clearTimeout(CEAS_DESCRIERE); CEAS_DESCRIERE = 0; }
}
function descriereSeMisca(){
  var d = $("descriere");
  return !document.hidden && !DESCRIERE_PAUSA &&
    !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) &&
    d.scrollHeight > d.clientHeight + 1;
}
function pasDescriere(){
  CEAS_DESCRIERE = 0;
  if(!descriereSeMisca()){ return; }
  var d = $("descriere"), capat = d.scrollHeight - d.clientHeight;
  if(d.scrollTop >= capat){
    d.scrollTop = 0;
    CEAS_DESCRIERE = setTimeout(pasDescriere, 5000);
  } else {
    d.scrollTop = Math.min(capat, d.scrollTop + 1);
    CEAS_DESCRIERE = setTimeout(pasDescriere, d.scrollTop >= capat ? 5000 : 80);
  }
}
function pornesteDescriere(reia){
  opresteDescriere();
  if(reia){ $("descriere").scrollTop = 0; }
  if(descriereSeMisca()){ CEAS_DESCRIERE = setTimeout(pasDescriere, 5000); }
}
// Sfarsitul derularii.
function text(e, camp){ return (ORIGINAL && e[camp + "_original"]) ? e[camp + "_original"] : (e[camp] || ""); }
function areTraducere(){
  var da = EMISIUNI.some(function(e){ return !!e.titlu_original; });
  if(DETALII){ da = da || !!(DETALII.titlu_original || DETALII.scurta_original || DETALII.lunga_original); }
  $("bara-traducere").classList.toggle("ascuns", !da);
  $("original").textContent = ORIGINAL ? "Textul tradus" : "Textul original";
  $("nota-traducere").textContent = ORIGINAL ? "Textul original, netradus." : "Tradus automat.";
}
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded"; optiuni.body = date.toString(); }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function q(obj){ var p = new URLSearchParams(); Object.keys(obj).forEach(function(k){ if(obj[k] !== "" && obj[k] !== null){ p.set(k, obj[k]); } }); return p; }
function deseneazaLista(){
  var c = $("lista"); c.textContent = ""; var ziVeche = null;
  EMISIUNI.forEach(function(e){
    if(e.zi !== ziVeche){ var z = document.createElement("div"); z.className = "zi"; z.textContent = e.zi; c.appendChild(z); ziVeche = e.zi; }
    var r = document.createElement("div"); r.className = "rand" + (e.acum ? " acum" : "") + (ALES && ALES.id === e.id ? " ales" : "");
    r.setAttribute("role", "button"); r.tabIndex = 0;
    var o = document.createElement("span"); o.className = "ora"; o.textContent = e.ora;
    var t = document.createElement("span"); t.className = "titlu"; t.textContent = text(e, "titlu");
    r.appendChild(o); r.appendChild(t);
    if(e.temporizator){ var s = document.createElement("span"); s.className = "semn " + e.temporizator; s.title = e.temporizator === "comutare" ? "Doar comutare" : "Înregistrare"; r.appendChild(s); }
    r.addEventListener("click", function(){ alege(e); });
    r.addEventListener("keydown", function(ev){ if(ev.key === "Enter"){ alege(e); } });
    c.appendChild(r);
  });
  $("mai").classList.toggle("ascuns", !URMATORUL);
  areTraducere();
}
function puneDetalii(){
  if(!DETALII){ return; }
  $("titlu").textContent = text(DETALII, "titlu"); $("linie").textContent = DETALII.linie;
  $("scurta").textContent = text(DETALII, "scurta"); $("lunga").textContent = text(DETALII, "lunga");
  var continut = $("descriere").textContent;
  if(continut !== DESCRIERE_TEXT){
    DESCRIERE_TEXT = continut; pornesteDescriere(true);
  }
  areTraducere();
}
function ceraDinNouLista(){
  // titlurile care se traduceau: aceeasi fereastra a ghidului, citita din nou dupa putin; numai titlurile se schimba
  if(INCERCARI_LISTA >= MAX_INCERCARI){ return; }
  INCERCARI_LISTA++;
  setTimeout(function(){
    if(!DATE){ return; }
    cerere("/api/ghid?" + q({ref: DATE.ref, cate: Math.min(50, Math.max(EMISIUNI.length, 1))})).then(function(d){
      if(!d.result){ return; }
      var noi = {}; d.emisiuni.forEach(function(e){ noi[e.id] = e; });
      EMISIUNI.forEach(function(e){ var n = noi[e.id]; if(n){ e.titlu = n.titlu; e.titlu_original = n.titlu_original; } });
      deseneazaLista();
      if(d.in_lucru){ ceraDinNouLista(); }
    }).catch(function(){});
  }, ASTEAPTA_MS);
}
function alege(e, dinNou){
  if(!dinNou){
    INCERCARI_EMISIUNE = 0; DETALII = null;
    DESCRIERE_TEXT = ""; opresteDescriere();
    var d = $("descriere");
    DESCRIERE_PAUSA = d.matches(":hover") || d.contains(document.activeElement);
  }
  ALES = e; deseneazaLista(); mesaj("");
  $("cand").textContent = e.acum ? "Acum" : (e.zi + " " + e.ora);
  if(!dinNou){ $("titlu").textContent = text(e, "titlu"); $("linie").textContent = ""; $("scurta").textContent = ""; $("lunga").textContent = ""; }
  butoane(e.temporizator);
  cerere("/api/ghid-emisiune?" + q({ref: DATE.ref, id: e.id})).then(function(d){
    if(!d.result || !ALES || ALES.id !== e.id){ return; }
    DETALII = d.emisiune; puneDetalii();
    butoane(d.emisiune.temporizator);
    if(d.in_lucru && INCERCARI_EMISIUNE < MAX_INCERCARI){
      INCERCARI_EMISIUNE++;
      setTimeout(function(){ if(ALES && ALES.id === e.id){ alege(e, true); } }, ASTEAPTA_MS);
    }
  });
}
function butoane(fel){
  $("inregistreaza").classList.toggle("ascuns", !!fel); $("comuta").classList.toggle("ascuns", !!fel);
  $("scoate").classList.toggle("ascuns", !fel);
}
function citeste(maiDeparte){
  var p = {ref: REF, cate: 30};
  if(maiDeparte && URMATORUL){ p.de_la = URMATORUL; }
  return cerere("/api/ghid?" + q(p)).then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi ghidul."; return; }
    DATE = d; REF = REF || d.ref; URMATORUL = d.urmatorul || 0;
    $("canal").textContent = d.nume ? ("Ghidul canalului: " + d.nume) : "Ghidul canalului";
    EMISIUNI = maiDeparte ? EMISIUNI.concat(d.emisiuni) : d.emisiuni;
    if(!EMISIUNI.length){ $("incarcare").textContent = "Canalul nu are program în ghid."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    if(!maiDeparte){ alege(EMISIUNI[0]); } else { deseneazaLista(); }
    INCERCARI_LISTA = 0;
    if(d.in_lucru){ ceraDinNouLista(); }
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(fel){
  if(!ALES){ return; }
  if(fel === "scoate" && !confirm("Scoți temporizatorul pentru „" + ALES.titlu + "”?")){ return; }
  mesaj("Se trimite...");
  cerere("/api/ghid-temporizator", "POST", q({ref: DATE.ref, id: ALES.id, fel: fel})).then(function(d){
    var t = d.message || "";
    if(d.suprapuse && d.suprapuse.length){ t += " " + d.suprapuse.map(function(s){ return s.nume; }).join(", "); }
    mesaj(t, !d.result);
    var id = ALES.id;
    // lista se reciteste (semnele de temporizator); alegerea emisiunii sterge mesajul, deci se scrie din nou dupa ea
    citeste(false).then(function(){ var e = EMISIUNI.filter(function(x){ return x.id === id; })[0]; if(e){ alege(e); } mesaj(t, !d.result); });
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("inregistreaza").addEventListener("click", function(){ trimite("inregistrare"); });
$("comuta").addEventListener("click", function(){ trimite("comutare"); });
$("scoate").addEventListener("click", function(){ trimite("scoate"); });
$("mai").addEventListener("click", function(){ citeste(true); });
$("original").addEventListener("click", function(){ ORIGINAL = !ORIGINAL; deseneazaLista(); puneDetalii(); });
var descriere = $("descriere");
descriere.addEventListener("mouseenter", function(){
  DESCRIERE_PAUSA = true; opresteDescriere();
});
descriere.addEventListener("mouseleave", function(){
  DESCRIERE_PAUSA = descriere.contains(document.activeElement);
  pornesteDescriere(false);
});
descriere.addEventListener("focusin", function(){
  DESCRIERE_PAUSA = true; opresteDescriere();
});
descriere.addEventListener("focusout", function(e){
  DESCRIERE_PAUSA = descriere.matches(":hover") || descriere.contains(e.relatedTarget);
  pornesteDescriere(false);
});
descriere.addEventListener("touchstart", function(){
  DESCRIERE_PAUSA = true; opresteDescriere();
}, {passive:true});
document.addEventListener("visibilitychange", function(){ pornesteDescriere(false); });
window.addEventListener("resize", function(){ pornesteDescriere(false); });
window.addEventListener("pagehide", opresteDescriere);
window.addEventListener("pageshow", function(){ pornesteDescriere(false); });
if(document.fonts && document.fonts.ready){
  document.fonts.ready.then(function(){ pornesteDescriere(false); });
}
$("porneste").addEventListener("click", function(){
  if(!DATE){ return; }
  mesaj("Se trimite...");
  cerere("/api/zap", "POST", q({sRef: DATE.ref})).then(function(d){ mesaj(d.result ? "Canalul pornește pe televizor." : (d.message || "Canalul nu a pornit."), !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
citeste(false);
</script>
</body>
</html>
"""


PAGINA_GRAFIC = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ghid grafic</title>
<style>__STIL_COMUN__
  main{max-width:1400px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 8px;}
  .bara{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 10px;}
  .bara select{min-height:44px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;padding:0 10px;max-width:100%;}
  .zi{color:#ffc34d;font-weight:bold;margin-left:4px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.rosu{background:#b3322a;border-color:#b3322a;color:#fff;}
  button.verde{background:#1f7a44;border-color:#1f7a44;color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .grila{position:relative;overflow-x:auto;border:1px solid var(--bordura);border-radius:10px;background:#10162a;}
  .interior{position:relative;}
  .rigla,.rand{position:relative;height:52px;border-bottom:1px solid #1c2440;}
  .rigla{height:34px;}
  .canal{position:sticky;left:0;z-index:3;width:170px;height:100%;background:#10162a;display:flex;align-items:center;gap:8px;padding:0 10px;box-sizing:border-box;border-right:1px solid #2a3350;}
  .canal .nr{color:var(--text-slab);font-size:.8rem;min-width:24px;text-align:right;font-variant-numeric:tabular-nums;}
  .canal .nm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:bold;}
  .ora{position:absolute;top:0;height:34px;line-height:34px;padding-left:8px;border-left:2px solid #2a3350;color:var(--text-slab);font-size:.85rem;white-space:nowrap;}
  .bloc{position:absolute;top:2px;height:48px;box-sizing:border-box;padding:0 10px;background:#282d3f;border-radius:4px;display:flex;align-items:center;gap:6px;cursor:pointer;overflow:hidden;white-space:nowrap;}
  .bloc span{overflow:hidden;text-overflow:ellipsis;}
  .bloc.acum{background:#404555;}
  .bloc.ales{background:#374ea1;outline:2px solid #9fb4ff;color:#fff;}
  .bloc .semn{flex:none;width:10px;height:10px;border-radius:50%;}
  .semn.inregistrare{background:#e5484d;}
  .semn.comutare{background:#f5b83d;}
  .gol{position:absolute;top:2px;height:48px;line-height:48px;padding-left:12px;color:var(--text-slab);background:#1a2034;border-radius:4px;}
  .linie{position:absolute;top:0;bottom:0;width:3px;background:#f5b83d;z-index:2;pointer-events:none;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:12px 0;}
  .titlu-mare{font-size:1.15rem;font-weight:bold;margin:0 0 4px;word-break:break-word;}
  .orele{color:#ffc34d;margin:0 0 8px;}
  .text{white-space:pre-wrap;line-height:1.45;margin:0 0 8px;word-break:break-word;max-height:12rem;overflow:auto;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .slab{color:var(--text-slab);}
</style>
</head>
<body>
<main>
<h1>Ghid grafic</h1>
<div class="bara">
  <select id="buchet" aria-label="Buchetul"></select>
  <button type="button" id="ziInapoi">Ziua anterioară</button>
  <button type="button" id="inapoi">◄ Mai devreme</button>
  <button type="button" id="acum">Acum</button>
  <button type="button" id="inainte">Mai târziu ►</button>
  <button type="button" id="ziInainte">Ziua următoare</button>
  <span class="zi" id="zi"></span>
</div>
<p class="slab" id="incarcare">Se citește ghidul...</p>
<div class="grila ascuns" id="grila"><div class="interior" id="interior"></div></div>
<div class="butoane"><button type="button" id="mai" class="ascuns">Mai multe canale</button></div>
<section class="card ascuns" id="detalii" aria-live="polite">
  <p class="titlu-mare" id="titlu"></p>
  <p class="orele" id="orele"></p>
  <p class="text" id="descriere"></p>
  <div class="butoane">
    <button type="button" class="rosu" id="inregistreaza">Înregistrează</button>
    <button type="button" id="aminteste">Amintește-mi</button>
    <button type="button" id="scoate" class="ascuns">Scoate temporizatorul</button>
    <button type="button" class="verde" id="porneste">Pornește canalul pe televizor</button>
  </div>
  <p class="mesaj" id="mesaj"></p>
</section>
<p class="slab">Pe televizor: tasta EPG, apoi MENU, Ghid grafic; sau setarea Ghidul TV ca grilă.</p>
<p class="slab"><a href="/ghid">Ghidul canalului de pe televizor</a></p>
</main>
<script>
var CFG = __CONFIG__;
var PX_MIN = 6, LATIME_CANAL = 170;
var STARE = {buchet: "", de_la: 0, ore: 3, canale: [], total: 0, date: null, ales: null}, CERERE = 0;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded"; optiuni.body = date.toString(); }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function q(obj){ var p = new URLSearchParams(); Object.keys(obj).forEach(function(k){ if(obj[k] !== "" && obj[k] !== null){ p.set(k, obj[k]); } }); return p; }
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function x(t){ var d = STARE.date; return LATIME_CANAL + Math.round((Math.max(t, d.t0) - d.t0) / 60 * PX_MIN); }
function deseneaza(){
  var d = STARE.date, c = $("interior"); c.textContent = "";
  var latime = LATIME_CANAL + Math.round((d.t1 - d.t0) / 60 * PX_MIN);
  c.style.width = latime + "px";
  var rigla = document.createElement("div"); rigla.className = "rigla";
  var cap = document.createElement("div"); cap.className = "canal"; rigla.appendChild(cap);
  d.marcaje.forEach(function(m){ var o = document.createElement("div"); o.className = "ora"; o.style.left = x(m.t) + "px"; o.textContent = m.text; rigla.appendChild(o); });
  c.appendChild(rigla);
  STARE.canale.forEach(function(ch){
    var r = document.createElement("div"); r.className = "rand";
    var cn = document.createElement("div"); cn.className = "canal";
    var nr = document.createElement("span"); nr.className = "nr"; nr.textContent = ch.numar;
    var nm = document.createElement("span"); nm.className = "nm"; nm.textContent = ch.nume; nm.title = ch.nume;
    cn.appendChild(nr); cn.appendChild(nm); r.appendChild(cn);
    if(!ch.emisiuni.length){
      var g = document.createElement("div"); g.className = "gol"; g.style.left = LATIME_CANAL + "px"; g.style.width = (latime - LATIME_CANAL) + "px";
      g.textContent = "Fără program în ghid"; r.appendChild(g);
    }
    ch.emisiuni.forEach(function(e){
      var a = x(e.inceput), b = x(Math.min(e.inceput + Math.max(e.durata, 60), d.t1));
      var bl = document.createElement("div"); bl.className = "bloc" + (e.acum ? " acum" : "") + (STARE.ales && STARE.ales.e.id === e.id && STARE.ales.ch.ref === ch.ref ? " ales" : "");
      bl.style.left = a + "px"; bl.style.width = Math.max(3, b - a - 2) + "px"; bl.tabIndex = 0; bl.setAttribute("role", "button");
      var t = document.createElement("span"); t.textContent = e.titlu; bl.title = e.ora + " " + e.titlu; bl.appendChild(t);
      if(e.temporizator){ var s = document.createElement("i"); s.className = "semn " + e.temporizator; bl.appendChild(s); }
      bl.addEventListener("click", function(){ alege(ch, e); });
      bl.addEventListener("keydown", function(ev){ if(ev.key === "Enter"){ alege(ch, e); } });
      r.appendChild(bl);
    });
    c.appendChild(r);
  });
  if(d.acum >= d.t0 && d.acum < d.t1){ var l = document.createElement("div"); l.className = "linie"; l.style.left = x(d.acum) + "px"; c.appendChild(l); }
  $("zi").textContent = d.zi;
  $("mai").classList.toggle("ascuns", STARE.canale.length >= STARE.total);
  $("inapoi").disabled = d.t0 <= d.minim; $("ziInapoi").disabled = d.t0 <= d.minim;
}
function citeste(maiMulte){
  var p = {buchet: STARE.buchet, de_la: STARE.de_la || "", ore: STARE.ore, de: maiMulte ? STARE.canale.length : 0, cate: 20};
  var nr = ++CERERE;
  return cerere("/api/ghid-grila?" + q(p)).then(function(d){
    if(nr !== CERERE){ return; }
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi ghidul."; return; }
    STARE.date = d; STARE.buchet = d.buchet; STARE.de_la = d.t0; STARE.total = d.total;
    STARE.canale = maiMulte ? STARE.canale.concat(d.canale) : d.canale;
    var s = $("buchet");
    if(!s.options.length){ d.buchete.forEach(function(b){ var o = document.createElement("option"); o.value = b.ref; o.textContent = b.nume; s.appendChild(o); }); }
    s.value = d.buchet;
    $("incarcare").classList.add("ascuns"); $("grila").classList.remove("ascuns");
    if(!STARE.canale.length){ $("incarcare").textContent = "Buchetul nu are canale."; $("incarcare").classList.remove("ascuns"); }
    deseneaza();
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function muta(secunde){ STARE.de_la = Math.max(STARE.date.minim, STARE.date.t0 + secunde); citeste(false); }
function butoane(fel){
  $("inregistreaza").classList.toggle("ascuns", !!fel); $("aminteste").classList.toggle("ascuns", !!fel);
  $("scoate").classList.toggle("ascuns", !fel);
}
function alege(ch, e){
  STARE.ales = {ch: ch, e: e}; deseneaza(); mesaj("");
  $("detalii").classList.remove("ascuns");
  $("titlu").textContent = ch.nume + ": " + e.titlu; $("orele").textContent = e.ora; $("descriere").textContent = "";
  butoane(e.temporizator);
  cerere("/api/ghid-emisiune?" + q({ref: ch.ref, id: e.id})).then(function(d){
    if(!d.result || !STARE.ales || STARE.ales.e.id !== e.id){ return; }
    $("orele").textContent = d.emisiune.linie;
    $("descriere").textContent = [d.emisiune.scurta, d.emisiune.lunga].filter(function(t){ return t; }).join("\\n");
    butoane(d.emisiune.temporizator);
  });
}
function trimite(fel){
  var a = STARE.ales; if(!a){ return; }
  mesaj("Se trimite...");
  cerere("/api/ghid-temporizator", "POST", q({ref: a.ch.ref, id: a.e.id, fel: fel})).then(function(d){
    var t = d.message || "";
    if(d.suprapuse && d.suprapuse.length){ t += " " + d.suprapuse.map(function(s){ return s.nume; }).join(", "); }
    citeste(false).then(function(){ mesaj(t, !d.result); });
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("buchet").addEventListener("change", function(){ STARE.buchet = this.value; STARE.ales = null; citeste(false); });
$("inapoi").addEventListener("click", function(){ muta(-STARE.ore * 1800); });
$("inainte").addEventListener("click", function(){ muta(STARE.ore * 1800); });
$("ziInapoi").addEventListener("click", function(){ muta(-86400); });
$("ziInainte").addEventListener("click", function(){ muta(86400); });
$("acum").addEventListener("click", function(){ STARE.de_la = 0; citeste(false); });
$("mai").addEventListener("click", function(){ citeste(true); });
$("inregistreaza").addEventListener("click", function(){ trimite("inregistrare"); });
$("aminteste").addEventListener("click", function(){ trimite("comutare"); });
$("scoate").addEventListener("click", function(){ trimite("scoate"); });
$("porneste").addEventListener("click", function(){
  var a = STARE.ales; if(!a){ return; }
  mesaj("Se trimite...");
  cerere("/api/zap", "POST", q({sRef: a.ch.ref})).then(function(d){ mesaj(d.result ? "Canalul pornește pe televizor." : (d.message || "Canalul nu a pornit."), !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
if(window.innerWidth < 720){ STARE.ore = 2; }
citeste(false);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Ghidul canalului"),
		N_("Se citește ghidul..."),
		N_("Textul original"),
		N_("Tradus automat."),
		N_("Înregistrează"),
		N_("Doar comutare la ora ei"),
		N_("Scoate temporizatorul"),
		N_("Pornește canalul pe televizor"),
		N_("Mai departe"),
		N_("Pe televizor: apasă OK de două ori pe un canal; prima pagină a barei este ghidul canalului."),

		# ghidul grafic (/ghid-grafic, RW2)
		N_("Ghid grafic: toate canalele buchetului, pe ore"),
		N_("Ghid grafic"),
		N_("Buchetul"),
		N_("Ziua anterioară"),
		N_("◄ Mai devreme"),
		N_("Acum"),
		N_("Mai târziu ►"),
		N_("Ziua următoare"),
		N_("Mai multe canale"),
		N_("Amintește-mi"),
		N_("Pe televizor: tasta EPG, apoi MENU, Ghid grafic; sau setarea Ghidul TV ca grilă."),
		N_("Ghidul canalului de pe televizor"),
	),
	"js": (
		N_("Textul tradus"),
		N_("Textul original"),
		N_("Textul original, netradus."),
		N_("Tradus automat."),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Doar comutare"),
		N_("Înregistrare"),
		N_("Acum"),
		N_("Receptorul nu a putut citi ghidul."),
		N_("Ghidul canalului:"),
		N_("Ghidul canalului"),
		N_("Canalul nu are program în ghid."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Scoți temporizatorul pentru „"),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Canalul pornește pe televizor."),
		N_("Canalul nu a pornit."),
		N_("Fără program în ghid"),
		N_("Buchetul nu are canale."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor

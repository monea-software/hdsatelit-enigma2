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
	texte = {"titlu": curat(ev["name"], 200), "scurta": _scurta(C, ev),
		"lunga": curat(ev["ext"]) if ev["ext"] not in (ev["short"], ev["name"]) else ""}
	traduse = {}
	in_lucru = 0
	for camp, fel in (("titlu", "titlu"), ("scurta", "scurta"), ("lunga", "lunga")):
		arata, tradus, lucru = _tradus(E, fel, texte[camp])
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


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = ("ref", "de_la", "cate", "id", "fel")
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_REF].strip()
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

	class PaginaResource(resource.Resource):
		"""GET /ghid: pagina „Ghidul canalului”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"ghid": GhidResource(),
		b"ghid-emisiune": EmisiuneResource(),
		b"ghid-temporizator": TemporizatorResource(),
	}
	return api, PaginaResource()


def pagina(request):
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
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


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
    <p class="text" id="scurta"></p>
    <p class="text slab" id="lunga"></p>
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
</main>
<script>
var CFG = __CONFIG__;
var REF = new URLSearchParams(location.search).get("ref") || "";
var DATE = null, ALES = null, EMISIUNI = [], URMATORUL = 0;
var ORIGINAL = false, DETALII = null, INCERCARI_LISTA = 0, INCERCARI_EMISIUNE = 0, ASTEAPTA_MS = 1500, MAX_INCERCARI = 8;
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
  if(!dinNou){ INCERCARI_EMISIUNE = 0; DETALII = null; }
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

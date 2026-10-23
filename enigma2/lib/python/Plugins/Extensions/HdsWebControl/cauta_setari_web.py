# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# cauta_setari_web.py: „Caută setări” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Screens/HdsCautaSetari.py: MENU > Setări > Caută setări, sau tasta TEXT in orice meniu).
#
# Acelasi index si aceleasi reguli ca pe televizor (Components/HdsCautaSetari.py): meniurile, intrarile si randurile de
# setari pe care le arata acum meniul receptorului (level=, requires=, conditional=), cautate in limba meniului si in
# romana, fara diacritice si fara majuscule. La fiecare rezultat: drumul din meniu, valoarea de acum (numai la setarile
# simple: Da / Nu, alegeri, numere), descrierea, si
# - pagina web potrivita: un rand din setup.xml duce la pagina generica /setari?id=<cheie>&setare=<setarea> (pagina il
#   alege si il arata); o intrare, la pagina ei (web= din menu.xml) sau la /setari?id=<cheie> pentru un <setup>; un
#   rand al ecranelor noastre, la pagina ecranului (web=); un meniu fara pagina, la /meniu;
# - „Deschide pe televizor”: ecranul se deschide pe televizor cu cursorul pe rand (Components/HdsCautaSetari.deschide).
#   Cererea trimite numai cheia rezultatului din index; modulul, ecranul si setarea vin din index, adica din fisierele
#   imaginii, nu din retea. Nu se deschid din web intrarile <code>, oprirea si repornirea receptorului si extensiile
#   (ca la /meniu); pentru ele ramane telecomanda.
# Campul „Caută setări” e si in capul panoului, al paginii /meniu si al paginii /setari (trimite la pagina aceasta).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/cauta-setari?q=<text>                 rezultatele (cel mult 60, cele mai potrivite intai)
#   POST /api/cauta-setari-televizor?cheie=<cheie>  deschide rezultatul pe televizor
#   GET  /cauta-setari                              pagina (?q=<text> cauta pe loc)
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; indexul se face o data si se reface numai cand se schimba
# ceva din ce il face (limba, nivelul, fisierele, SystemInfo).

MAX_TEXT = 60
MAX_CHEIE = 200


def _t(text):
	"""Traducerea enigma2; un text gol ramane gol (gettext ar da antetul fisierului .po)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] cauta setari: %s" % text)


def _C():
	from Components import HdsCautaSetari
	return HdsCautaSetari


def _sw():
	from . import scanare_web
	return scanare_web


def _paginaWeb(i):
	"""Pagina web a rezultatului (vezi capul fisierului), sau "" cand ecranul n-are pereche decat pe televizor."""
	from urllib.parse import quote
	if i.fel == "rand" and i.setup:
		return "/setari?id=%s&setare=%s" % (quote(i.setup, safe=""), quote(i.setare, safe=""))
	if i.web:
		return i.web
	if i.fel == "intrare" and i.setup:
		return "/setari?id=%s" % quote(i.setup, safe="")
	if i.fel == "grup":
		return "/meniu"
	return ""


def rezultat(i, C, config=None):
	merge, _fel = C.poateDeschide(i)
	web = _paginaWeb(i)
	return {
		"cheie": i.cheie,
		"fel": i.fel,
		"titlu": i.titlu,
		"drum": i.drumText(_t),
		"valoare": C.valoare(i, config),
		"ajutor": i.ajutor,
		"web": web,
		"televizor": merge,
		# o intrare cu pagina web (de exemplu resetarea sau oprirea, cu confirmare in pagina) nu are motiv
		"motiv": "" if merge or web else _t("Se deschide numai din telecomandă."),
	}


def cauta(text, config=None, SystemInfo=None):
	"""GET /api/cauta-setari?q=: {"result", "text", "numar", "rezultate"}."""
	C = _C()
	text = (text or "")[:MAX_TEXT]
	idx = C.index(config=config, SystemInfo=SystemInfo)
	rez = [rezultat(i, C, config) for i in idx.cauta(text)]
	return {"result": True, "text": text, "numar": len(rez), "rezultate": rez}


def deschide(cheie, sesiune=None, config=None, SystemInfo=None):
	"""POST /api/cauta-setari-televizor?cheie=: deschide pe televizor un rezultat din indexul de acum."""
	C = _C()
	idx = C.index(config=config, SystemInfo=SystemInfo)
	i = idx.dupaCheie((cheie or "")[:MAX_CHEIE])
	if i is None:
		return {"result": False, "message": _t("Rezultatul nu mai e în meniu. Caută din nou.")}
	merge, _fel = C.poateDeschide(i)
	if not merge:
		return {"result": False, "message": _t("Se deschide numai din telecomandă.")}
	W = _sw()
	if sesiune is None:
		sesiune = W._sesiune()
	refuz = W._ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	try:
		dlg = C.deschide(sesiune, i, config=config)
	except Exception as eroare:
		_jurnal("deschiderea %s pe televizor: %s" % (i.cheie, eroare))
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor (%s).") % eroare}
	if dlg is None:
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor. Detalii în jurnalul receptorului.")}
	return {"result": True, "message": _t("S-a deschis pe televizor: %s.") % i.nume}


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:6]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ("q", "cheie"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT if cheie == "q" else MAX_CHEIE].strip()
	return rez


def rute(baza, resource):
	class CautaResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, cauta(argumente(request).get("q", "")))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class TelevizorResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, deschide(argumente(request).get("cheie", "")))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {b"cauta-setari": CautaResource(), b"cauta-setari-televizor": TelevizorResource()}
	return api, PaginaResource()


def pagina(request):
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
<title>Caută setări</title>
<style>__STIL_COMUN__
  main{max-width:880px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  form.cauta{display:flex;gap:8px;margin:0 0 6px;}
  form.cauta input{flex:1;min-height:48px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;font-size:1.05rem;}
  .stare{display:flex;justify-content:space-between;gap:12px;color:var(--text-slab);font-size:.85rem;min-height:1.3em;margin:4px 0 10px;}
  .rezultat{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:10px 14px;margin:0 0 8px;}
  .rezultat .cap{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;align-items:baseline;}
  .rezultat .titlu{font-size:1rem;}
  .rezultat .valoare{color:#9fb4ff;font-size:.9rem;}
  .rezultat .drum{color:var(--text-slab);font-size:.82rem;margin:2px 0 0;}
  .rezultat .ajutor{color:var(--text-slab);font-size:.82rem;line-height:1.4;margin:6px 0 0;}
  .rezultat .actiuni{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin:8px 0 0;}
  .rezultat .motiv{color:var(--text-slab);font-size:.8rem;}
  button{min-height:40px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;font-size:.85rem;cursor:pointer;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:10px 0 0;line-height:1.45;}
  .mesaj{margin:8px 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
</style>
</head>
<body>
<main>
<h1>Caută setări</h1>
<form class="cauta" id="forma" action="/cauta-setari" method="get" role="search">
  <input type="search" id="text" name="q" maxlength="60" placeholder="Scrie un cuvânt, de exemplu subtitrări" aria-label="Caută setări" autocomplete="off" autofocus>
</form>
<div class="stare"><span id="numar"></span><a id="meniu" href="/meniu">Tot meniul receptorului</a></div>
<p class="mesaj" id="mesaj">Scrie câteva litere din numele setării.</p>
<div id="rezultate"></div>
<p class="nota">Aceleași rezultate ca pe televizor, în Meniu, „Setări”, „Caută setări” (sau tasta TEXT în orice meniu): meniurile și setările pe care le arată acum receptorul. Literele mari și diacriticele nu contează. La fiecare rezultat: pagina lui din interfața web, dacă are, sau „Deschide pe televizor”, cu rândul găsit deja ales.</p>
</main>
<script>
var CFG = __CONFIG__;
var ceas = null, numarCerere = 0;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function element(tag, clasa, text){ var e = document.createElement(tag); if(clasa){ e.className = clasa; } if(text){ e.textContent = text; } return e; }
function deschide(cheie){
  var q = new URLSearchParams(); q.set("cheie", cheie);
  mesaj("Se deschide pe televizor...");
  cerere("/api/cauta-setari-televizor", "POST", q).then(function(d){ mesaj(d.message, !d.result); }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function rezultat(r){
  var div = element("div", "rezultat");
  var cap = element("div", "cap");
  cap.appendChild(element("span", "titlu", r.titlu));
  if(r.valoare){ cap.appendChild(element("span", "valoare", r.valoare)); }
  div.appendChild(cap);
  div.appendChild(element("div", "drum", r.drum));
  if(r.ajutor){ div.appendChild(element("p", "ajutor", r.ajutor)); }
  var a = element("div", "actiuni");
  if(r.web){ var l = element("a", "", "Pagina web"); l.href = adresa(r.web); a.appendChild(l); }
  if(r.televizor){ var b = element("button", "", "Deschide pe televizor"); b.type = "button"; b.addEventListener("click", function(){ deschide(r.cheie); }); a.appendChild(b); }
  else if(r.motiv){ a.appendChild(element("span", "motiv", r.motiv)); }
  div.appendChild(a);
  return div;
}
function arata(d){
  var c = $("rezultate"); c.textContent = "";
  $("numar").textContent = "Rezultate: " + d.numar;
  mesaj(d.numar ? "" : "Nicio setare nu se potrivește. Încearcă un alt cuvânt sau mai puține litere.");
  d.rezultate.forEach(function(r){ c.appendChild(rezultat(r)); });
}
function cauta(){
  var text = $("text").value.trim();
  var nr = ++numarCerere;
  try { history.replaceState(null, "", adresa(location.pathname + (text ? "?q=" + encodeURIComponent(text) : ""))); } catch(e) {}
  if(!text){ $("rezultate").textContent = ""; $("numar").textContent = ""; mesaj("Scrie câteva litere din numele setării."); return; }
  cerere("/api/cauta-setari?q=" + encodeURIComponent(text)).then(function(d){
    if(nr !== numarCerere){ return; }
    if(!d.result){ mesaj(d.message, true); return; }
    arata(d);
  }).catch(function(){ if(nr === numarCerere){ mesaj("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); } });
}
$("text").addEventListener("input", function(){ clearTimeout(ceas); ceas = setTimeout(cauta, 200); });
$("forma").addEventListener("submit", function(ev){ ev.preventDefault(); clearTimeout(ceas); cauta(); });
$("meniu").href = adresa("/meniu");
var inceput = new URLSearchParams(location.search).get("q") || "";
if(inceput){ $("text").value = inceput.slice(0, 60); cauta(); }
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
		N_("Caută setări"),
		N_("Tot meniul receptorului"),
		N_("Scrie câteva litere din numele setării."),
		N_("Aceleași rezultate ca pe televizor, în Meniu, „Setări”, „Caută setări” (sau tasta TEXT în orice "
			"meniu): meniurile și setările pe care le arată acum receptorul. Literele mari și diacriticele "
			"nu contează. La fiecare rezultat: pagina lui din interfața web, dacă are, sau „Deschide pe "
			"televizor”, cu rândul găsit deja ales."),
		N_("Scrie un cuvânt, de exemplu subtitrări"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se deschide pe televizor..."),
		N_("Receptorul nu răspunde."),
		N_("Pagina web"),
		N_("Deschide pe televizor"),
		N_("Rezultate:"),
		N_("Nicio setare nu se potrivește. Încearcă un alt cuvânt sau mai puține litere."),
		N_("Scrie câteva litere din numele setării."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
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

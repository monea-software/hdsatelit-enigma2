# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ajutor_web.py: „Ajutor” in interfata web (HdsWebControl), din 0.6.8.
#
# Pe televizor: Meniu > Ajutor si tasta HELP pe orice ecran (Screens/HdsAjutor.py). Aici, aceleasi pagini, din aceleasi
# date (Components/HdsAjutor.py, pachetul hdsatelit-ajutor): capitolele, paginile cu partile lor, cautarea, legaturile
# intre pagini, adresa paginii cu poze de pe site si paginile web ale ecranului. In plus fata de televizor: butonul
# „Pagina ecranului de pe televizor” (pagina ecranului deschis acum pe televizor, cu aceleasi reguli ca tasta HELP).
# Textele din jurul paginilor vin din datele ajutorului, in limba interfetei (13 limbi); sablonul paginii nu are niciun
# text de ecran al lui (numai semnele __T_...__ si textele primite de la /api/ajutor), deci TEXTE_PAGINA e gol.
#
# Rute (poarta comuna a HdsJsonResource):
#   GET /api/ajutor                    capitolele cu paginile lor, textele din jur, versiunea, limba paginilor
#   GET /api/ajutor-pagina?p=<cheie>   o pagina („capitol/pagina”, ca adresa de pe site), cu titlurile paginilor legate
#   GET /api/ajutor-cauta?q=<text>     paginile gasite (cel mult HdsAjutor.CAUTARE_MAXIM)
#   GET /api/ajutor-ecran              cheia paginii ecranului de pe televizor ("" cand nu are)
#   GET /ajutor                        pagina (adresa din menu.xml); #p=<cheie> deschide o pagina, #q=<text> cauta
#
# FIRUL: render_GET ruleaza pe firul enigma2; o cerere citeste cel mult o pagina (cateva KB) sau textul de cautare al
# unei limbi (~90 KB comprimat), fara nimic tinut in memorie. Fisierul nu importa nimic din enigma2 la incarcare:
# probele de pe PC dau modulul lor (A).

import json
import re

try:
	from html import escape as _escape
except ImportError:  # Python 2
	from cgi import escape as _escape

MAX_CAUTARE = 100
MAX_CHEIE = 160
CHEIE = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")
# textele din jur de care are nevoie scriptul paginii (din datele ajutorului)
CHEI_TEXTE = ("ajutor", "cuprins", "capitol", "pagini_n", "cauta_titlu", "cauta_rezultate", "gasite_n", "nimic_gasit",
	"in_engleza", "online", "versiune", "inapoi_cuprins", "se_citeste", "nu_raspunde", "pagina_lipsa", "ecran_tv",
	"web_pereche", "fara_pagina", "valori", "din_fabrica", "cand", "la_ce_foloseste", "cum_ajungi", "ce_vezi",
	"randuri", "taste", "pas_cu_pas", "probleme", "legat_de", "diferente_receptoare", "lipsa")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAjutor
	return HdsAjutor


def _limba(A=None):
	try:
		return _a(A).limba_interfetei()
	except Exception:
		return "ro"


def texte(A=None, limba=None):
	A = _a(A)
	limba = limba or _limba(A)
	return dict((k, A.text(k, limba)) for k in CHEI_TEXTE)


def stare(A=None):
	"""GET /api/ajutor"""
	A = _a(A)
	lb = _limba(A)
	if not A.instalat():
		return {"result": True, "instalat": False, "texte": texte(A, lb), "capitole": []}
	capitole = []
	for c in A.capitole(lb):
		capitole.append({"i": c["i"], "cod": c["cod"], "titlu": c["titlu"],
			"pagini": [{"i": i, "c": A.cheie_pagina(i), "t": A.titlu_pagina(i, lb)} for i in c["pagini"]]})
	return {"result": True, "instalat": True, "limba": A.limba_text(lb), "in_engleza": A.in_engleza(lb),
		"versiune": A.versiune(), "texte": texte(A, lb), "capitole": capitole}


def _index(A, cheie):
	cheie = (cheie or "").strip().strip("/")
	if cheie.isdigit():
		i = int(cheie)
		return i if A.cheie_pagina(i) else None
	if not CHEIE.match(cheie):
		return None
	return A.index_cheie(cheie)


def pagina_api(cheie, A=None):
	"""GET /api/ajutor-pagina?p=<cheie>: ({...}, cod)"""
	A = _a(A)
	lb = _limba(A)
	if not A.instalat():
		return {"result": False, "message": A.text("lipsa", lb)}, 404
	i = _index(A, cheie)
	pg = A.pagina(i, lb) if i is not None else None
	if pg is None:
		return {"result": False, "message": A.text("pagina_lipsa", lb)}, 404
	cap = A.capitol_pagina(i)
	capitole = A.capitole(lb)
	capitol = capitole[cap] if cap is not None and 0 <= cap < len(capitole) else None
	legate = {}
	for j in A.legaturi(pg):
		if A.cheie_pagina(j):
			legate["%d" % j] = {"c": A.cheie_pagina(j), "t": A.titlu_pagina(j, lb)}
	return {"result": True, "i": i, "c": A.cheie_pagina(i), "titlu": pg.get("t") or A.titlu_pagina(i, lb),
		"capitol": {"cod": capitol["cod"], "titlu": capitol["titlu"]} if capitol else None,
		"parti": pg.get("p") or [], "legate": legate, "online": A.adresa_online(i, lb), "web": A.cai_web(i)}, 200


def cauta_api(text, A=None):
	"""GET /api/ajutor-cauta?q=<text>"""
	A = _a(A)
	lb = _limba(A)
	text = (text or "")[:MAX_CAUTARE]
	capitole = A.capitole(lb)
	rez = []
	for i in A.cauta(text, lb):
		cap = A.capitol_pagina(i)
		rez.append({"i": i, "c": A.cheie_pagina(i), "t": A.titlu_pagina(i, lb),
			"cap": capitole[cap]["titlu"] if cap is not None and 0 <= cap < len(capitole) else ""})
	return {"result": True, "q": text, "pagini": rez}


def ecran_api(sesiune=None, A=None):
	"""GET /api/ajutor-ecran: pagina ecranului de sus de pe televizor (aceleasi reguli ca tasta HELP)"""
	A = _a(A)
	s = sesiune() if callable(sesiune) else sesiune
	d = getattr(s, "current_dialog", None) if s is not None else None
	if d is None or not A.instalat():
		return {"result": True, "c": ""}
	dedesubt = [x[0] for x in reversed(getattr(s, "dialog_stack", None) or [])]
	i = A.pagina_ecranului(d, dedesubt)
	return {"result": True, "c": A.cheie_pagina(i) if i is not None else ""}


def _argument(request, nume, lungime):
	valori = (getattr(request, "args", None) or {}).get(nume)
	if not valori:
		return ""
	return valori[0].decode("utf-8", "replace")[:lungime]


def rute(baza, resource, sesiune=None, A=None):
	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaApiResource(baza):
		def render_GET(self, request):
			try:
				corp, cod = pagina_api(_argument(request, b"p", MAX_CHEIE), A)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CautaResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, cauta_api(_argument(request, b"q", MAX_CAUTARE), A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class EcranResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, ecran_api(sesiune, A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"ajutor": StareResource(), b"ajutor-pagina": PaginaApiResource(), b"ajutor-cauta": CautaResource(),
		b"ajutor-ecran": EcranResource()}, PaginaResource()


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
		config_pagina = P._configPanou("", "", browser.get("nume", ""))   # numai citire: fara tokenul CSRF
	return pagina_text(P._STIL_COMUN, config_pagina, _limba()).encode("utf-8", "replace")


def _e(text):
	return _escape(u"%s" % (text or ""), True)


def pagina_text(stil, config_pagina, limba="ro", A=None):
	A = _a(A)
	# titlul trece prin traducerea receptorului (msgid-ul „Ajutor” e in toate cele 13 limbi); celelalte texte le pune
	# scriptul, din /api/ajutor (datele ajutorului, in limba interfetei)
	valori = {
		"__STIL_COMUN__": stil,
		"__LIMBA__": _e(limba or "ro"),
		"__CONFIG__": config_pagina,
		"__T_TITLU__": _e(_t("Ajutor")),
	}
	# o singura trecere: un text venit din browser (in __CONFIG__) nu poate fi luat drept semn __X__
	return re.sub(r"__[A-Z_]+__", lambda m: valori.get(m.group(0), m.group(0)), _traducePagina(PAGINA))


PAGINA = u"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:1040px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1.05rem;margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--bordura);}
  h3{font-size:1rem;margin:12px 0 6px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .cauta{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;}
  .cauta input{flex:1;min-width:200px;min-height:44px;padding:6px 10px;border-radius:8px;border:1px solid var(--bordura);background:#1c2129;color:var(--text);font:inherit;}
  .cauta button,.inapoi{min-height:44px;padding:6px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .nota{color:var(--text-slab);font-size:.9rem;margin:6px 0 10px;line-height:1.45;}
  details.capitol{border-bottom:1px solid var(--bordura);}
  details.capitol summary{display:flex;gap:10px;align-items:baseline;min-height:44px;padding:10px 4px;cursor:pointer;}
  details.capitol summary .cod{color:var(--text-slab);font-variant-numeric:tabular-nums;}
  details.capitol summary .nr{margin-left:auto;color:var(--text-slab);font-size:.875rem;white-space:nowrap;}
  ul.pagini{list-style:none;margin:0 0 8px;padding:0 0 0 34px;}
  ul.pagini li a,ul.rezultate li a{display:block;padding:9px 4px;color:var(--text);text-decoration:none;border-radius:6px;}
  ul.pagini li a:hover,ul.pagini li a:focus,ul.rezultate li a:hover,ul.rezultate li a:focus{background:#242a33;}
  ul.rezultate{list-style:none;margin:0;padding:0;}
  ul.rezultate .cap{display:block;color:var(--text-slab);font-size:.85rem;}
  #pagina p{margin:0 0 8px;line-height:1.5;}
  #pagina a{color:var(--albastru-deschis,#9fb4ff);}
  .tabel-cadru{overflow-x:auto;}
  table.tabel{border-collapse:collapse;width:100%;font-size:.95rem;}
  table.tabel th,table.tabel td{border-bottom:1px solid var(--bordura);padding:7px 6px;text-align:left;vertical-align:top;line-height:1.45;}
  table.tabel th{color:var(--text-slab);font-weight:600;}
  .tasta{display:inline-block;padding:1px 8px;border-radius:6px;border:1px solid var(--bordura);background:#242a33;white-space:nowrap;font-weight:600;}
  .mic{display:block;color:var(--text-slab);font-size:.85rem;margin-top:3px;}
  details.problema{border-bottom:1px solid var(--bordura);}
  details.problema summary{padding:9px 4px;cursor:pointer;font-weight:600;line-height:1.45;}
  details.problema p{padding:0 4px 6px;}
  ol.pasi{margin:0 0 8px;padding-left:24px;line-height:1.5;}
  ul.conexe{margin:0;padding-left:20px;line-height:1.6;}
  .josul{margin-top:16px;color:var(--text-slab);font-size:.9rem;line-height:1.5;word-break:break-word;}
  [hidden]{display:none;}
</style>
</head>
<body>
<main>
<h1 id="titlu">__T_TITLU__</h1>
<div class="cauta"><input id="cauta" type="search"><button id="ecranTv" type="button" hidden></button></div>
<p class="nota" id="nota"></p>
<section class="card" id="cuprins" hidden></section>
<section class="card" id="rezultate" hidden></section>
<article class="card" id="pagina" hidden></article>
</main>
<script>
var CFG = __CONFIG__;
var T = {};
var DATE = null;
var amanare = null;
function $(id){ return document.getElementById(id); }
function f(text){ var a = Array.prototype.slice.call(arguments, 1); var i = 0; return String(text).replace(/%d|%s/g, function(){ return a[i++]; }); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale){
  return fetch(adresa(cale), {cache: "no-store", credentials: "same-origin"}).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("401"); }
    return r.json();
  });
}
function el(nume, clasa, text){
  var e = document.createElement(nume);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = text; }
  return e;
}
function legatura(cheie, text){
  var a = el("a", "", text); a.href = "#p=" + cheie; return a;
}
function arata(id){
  ["cuprins", "rezultate", "pagina"].forEach(function(x){ $(x).hidden = (x !== id); });
}
function nota(text){ $("nota").textContent = text || ""; $("nota").hidden = !text; }
function cuprins(){
  var s = $("cuprins"); s.textContent = "";
  (DATE.capitole || []).forEach(function(c){
    var d = el("details", "capitol");
    var sm = el("summary");
    sm.appendChild(el("span", "cod", c.cod));
    sm.appendChild(el("span", "", c.titlu));
    sm.appendChild(el("span", "nr", f(T.pagini_n, c.pagini.length)));
    d.appendChild(sm);
    var ul = el("ul", "pagini");
    c.pagini.forEach(function(p){ var li = el("li"); li.appendChild(legatura(p.c, p.t)); ul.appendChild(li); });
    d.appendChild(ul);
    s.appendChild(d);
  });
  $("titlu").textContent = T.ajutor;
  document.title = T.ajutor;
  nota(DATE.in_engleza ? T.in_engleza : (DATE.versiune ? f(T.versiune, DATE.versiune) : ""));
  arata("cuprins");
}
function inapoi(s){
  var b = el("button", "inapoi", T.inapoi_cuprins); b.type = "button";
  b.addEventListener("click", function(){ location.hash = ""; });
  s.appendChild(b);
}
function rezultate(q, d){
  var s = $("rezultate"); s.textContent = "";
  $("titlu").textContent = f(T.cauta_rezultate, q);
  nota(d.pagini.length ? f(T.gasite_n, d.pagini.length) : T.nimic_gasit);
  var ul = el("ul", "rezultate");
  d.pagini.forEach(function(p){
    var li = el("li"); var a = legatura(p.c, p.t); a.appendChild(el("span", "cap", p.cap)); li.appendChild(a); ul.appendChild(li);
  });
  s.appendChild(ul);
  inapoi(s);
  arata("rezultate");
}
function legat(d, e){
  var k = e[e.length - 1];
  return (k >= 0 && d.legate[String(k)]) ? d.legate[String(k)] : null;
}
function adaugaLegatura(parinte, d, e){
  var l = legat(d, e);
  if(l){ parinte.appendChild(document.createTextNode(" ")); parinte.appendChild(legatura(l.c, "\\u203a " + l.t)); }
}
function parte(s, d, cheie, elemente){
  s.appendChild(el("h2", "", T[cheie] || cheie));
  if(cheie === "randuri"){
    var cad = el("div", "tabel-cadru"); var tb = el("table", "tabel"); var cap = el("tr");
    [T.randuri, T.valori, T.din_fabrica, ""].forEach(function(x){ cap.appendChild(el("th", "", x)); });
    var th = el("thead"); th.appendChild(cap); tb.appendChild(th);
    var corp = el("tbody");
    elemente.forEach(function(e){
      var tr = el("tr");
      tr.appendChild(el("td", "", e[0])); tr.appendChild(el("td", "", e[1])); tr.appendChild(el("td", "", e[2]));
      var td = el("td", "", e[3]);
      if(e[4]){ td.appendChild(el("span", "mic", T.cand + ": " + e[4])); }
      adaugaLegatura(td, d, e);
      tr.appendChild(td); corp.appendChild(tr);
    });
    tb.appendChild(corp); cad.appendChild(tb); s.appendChild(cad);
  } else if(cheie === "taste"){
    var cad2 = el("div", "tabel-cadru"); var tb2 = el("table", "tabel"); var corp2 = el("tbody");
    elemente.forEach(function(e){
      var tr = el("tr"); var td1 = el("td"); td1.appendChild(el("span", "tasta", e[0])); tr.appendChild(td1);
      var td2 = el("td", "", e[1]); adaugaLegatura(td2, d, e); tr.appendChild(td2); corp2.appendChild(tr);
    });
    tb2.appendChild(corp2); cad2.appendChild(tb2); s.appendChild(cad2);
  } else if(cheie === "pas_cu_pas"){
    elemente.forEach(function(e){
      if(e[0]){ s.appendChild(el("h3", "", e[0])); }
      var ol = el("ol", "pasi"); (e[1] || []).forEach(function(p){ ol.appendChild(el("li", "", p)); }); s.appendChild(ol);
      var p2 = el("p"); adaugaLegatura(p2, d, e); if(p2.childNodes.length){ s.appendChild(p2); }
    });
  } else if(cheie === "probleme"){
    elemente.forEach(function(e){
      var det = el("details", "problema"); det.appendChild(el("summary", "", e[0]));
      var p = el("p", "", e[1]); adaugaLegatura(p, d, e); det.appendChild(p); s.appendChild(det);
    });
  } else if(cheie === "legat_de"){
    var ul = el("ul", "conexe");
    elemente.forEach(function(e){
      var li = el("li"); var l = legat(d, e);
      if(l){ li.appendChild(legatura(l.c, e[0])); } else { li.textContent = e[0]; }
      ul.appendChild(li);
    });
    s.appendChild(ul);
  } else {
    elemente.forEach(function(e){ var p = el("p", "", e[0]); adaugaLegatura(p, d, e); s.appendChild(p); });
  }
}
function pagina(d){
  var s = $("pagina"); s.textContent = "";
  $("titlu").textContent = d.titlu;
  document.title = d.titlu;
  nota(d.capitol ? f(T.capitol, d.capitol.cod) + " \\u00b7 " + d.capitol.titlu : "");
  (d.parti || []).forEach(function(x){ parte(s, d, x[0], x[1]); });
  var jos = el("div", "josul");
  if(DATE && DATE.in_engleza){ jos.appendChild(el("p", "", T.in_engleza)); }
  if(d.online){
    var p = el("p"); var i = T.online.indexOf("%s");
    var a = el("a", "", d.online); a.href = d.online; a.rel = "noopener"; a.target = "_blank";
    p.appendChild(document.createTextNode(i >= 0 ? T.online.slice(0, i) : T.online + " "));
    p.appendChild(a);
    if(i >= 0){ p.appendChild(document.createTextNode(T.online.slice(i + 2))); }
    jos.appendChild(p);
  }
  (d.web || []).forEach(function(w){
    var p = el("p"); var i = T.web_pereche.indexOf("%s");
    var a = el("a", "", w); a.href = w;
    p.appendChild(document.createTextNode(i >= 0 ? T.web_pereche.slice(0, i) : T.web_pereche + " "));
    p.appendChild(a);
    if(i >= 0){ p.appendChild(document.createTextNode(T.web_pereche.slice(i + 2))); }
    jos.appendChild(p);
  });
  s.appendChild(jos);
  inapoi(s);
  arata("pagina");
  window.scrollTo(0, 0);
}
function urmeaza(){
  if(!DATE){ return; }
  var h = decodeURIComponent((location.hash || "").slice(1));
  if(h.indexOf("p=") === 0){
    cerere("/api/ajutor-pagina?p=" + encodeURIComponent(h.slice(2))).then(function(d){
      if(!d.result){ nota(d.message || T.pagina_lipsa); arata(""); return; }
      pagina(d);
    }).catch(function(){ nota(T.nu_raspunde); });
  } else if(h.indexOf("q=") === 0 && h.length > 2){
    var q = h.slice(2);
    if($("cauta").value !== q){ $("cauta").value = q; }
    cerere("/api/ajutor-cauta?q=" + encodeURIComponent(q)).then(function(d){ rezultate(q, d); })
      .catch(function(){ nota(T.nu_raspunde); });
  } else {
    cuprins();
  }
}
function porneste(){
  cerere("/api/ajutor").then(function(d){
    T = d.texte || {};
    DATE = d;
    // fara pachetul ajutorului: numai mesajul (nimic de cautat; textele din jur nu sunt instalate)
    if(!d.instalat){ nota(T.lipsa); $("cauta").hidden = true; return; }
    $("cauta").placeholder = T.cauta_titlu || "";
    $("cauta").setAttribute("aria-label", T.cauta_titlu || "");
    $("ecranTv").textContent = T.ecran_tv; $("ecranTv").hidden = false;
    urmeaza();
  }).catch(function(){ nota(T.nu_raspunde || ""); });
}
$("cauta").addEventListener("input", function(){
  clearTimeout(amanare);
  var q = $("cauta").value.trim();
  amanare = setTimeout(function(){ location.hash = q ? "q=" + encodeURIComponent(q) : ""; }, 300);
});
$("ecranTv").addEventListener("click", function(){
  cerere("/api/ajutor-ecran").then(function(d){
    if(d.c){ location.hash = "p=" + d.c; } else { location.hash = ""; nota(T.fara_pagina); }
  }).catch(function(){ nota(T.nu_raspunde); });
});
window.addEventListener("hashchange", urmeaza);
porneste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Sablonul nu are niciun text de ecran al lui: toate vin din datele ajutorului (/api/ajutor, in limba interfetei).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
	),
	"js": (
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

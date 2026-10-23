# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# licente_web.py: „Licențe” in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Informații sistem > Licențe (Screens/HdsLicente.py). Aici, aceleasi randuri si aceleasi texte,
# din acelasi modul (Components/HdsLicente.py): starea listei, al cui e imaginea, adresa codului sursa al versiunii,
# programele din imagine cu licentele lor, componentele din pachetele fabricantului, fonturile, listele de canale si
# pachetele instalate dupa construire; textul unei licente se citeste la cerere. Numai citire. Textele paginii trec
# prin traducerea receptorului (_t), in limba interfetei, ca si randurile.
#
# Rute (poarta comuna a HdsJsonResource):
#   GET /api/licente                 starea, textele de sus si randurile (fara textele licentelor)
#   GET /api/licente-text?id=<id>    textul unei licente (id = 16 cifre hexa, din randuri)
#   GET /licente                     pagina (adresa din menu.xml)
#
# FIRUL: render_GET ruleaza pe firul enigma2. lista.json si starea pachetelor se citesc pe firul modulului (cereStare
# nu asteapta, listaTinuta face numai un stat); pana atunci raspunsul spune „se_citeste” si pagina intreaba din nou.
# Raspunsul /api/licente se tine in memorie cat timp lista, starea si limba sunt aceleasi (randurile nu se refac la
# fiecare cerere). Un text are cel mult HdsLicente.MAX_TEXT. Fisierul nu importa nimic din enigma2 la incarcare:
# probele de pe PC dau modulul lor (L).

import json
import re

try:
	from html import escape as _escape
except ImportError:  # Python 2
	from cgi import escape as _escape


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _l(L=None):
	if L is not None:
		return L
	from Components import HdsLicente
	return HdsLicente


def _limba():
	"""Codul limbii interfetei pentru <html lang>, „ro” daca nu se poate afla"""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	cod = "".join(ch for ch in cod if "a" <= ch <= "z")[:3]
	return cod or "ro"


# ultimul raspuns /api/licente: obiectele din care s-a facut (lista, starea, limba) si raspunsul
_tinut = {"lista": None, "stare": None, "limba": None, "se_citeste": None, "raspuns": None}


def _randWeb(L, r):
	return {
		"id": r["id"], "fel": r["fel"], "nume": r["nume"], "versiune": r["versiune"], "licenta": r["licenta"],
		"licenta_om": r.get("licenta_om") or r["licenta"], "clasa": r["clasa"],
		"clasa_nume": _t(L.NUME_CLASA.get(r["clasa"], "")) if r["clasa"] else "",
		"detaliu": r["detaliu"], "texte": [{"nume": n, "id": i} for n, i in L.textePentru(r)],
		"explicatie": "" if r["texte"] else L.explicatieFaraText(r),
	}


def licente(L=None):
	"""GET /api/licente"""
	L = _l(L)
	lista, eroare, gata = L.listaTinuta()
	st, se_citeste = L.cereStare(din_nou=not gata)
	if not gata:
		text, detaliu = L.texteSus(None, {"stare": L.STARE_CITESTE})
		return {"result": True, "stare": L.STARE_CITESTE, "se_citeste": True, "text": text, "detaliu": detaliu,
			"autor": L.textAutor(), "sursa": L.SURSA_IMPLICITA, "versiune": "", "build": "", "randuri": []}
	lb = L.limba()
	t = _tinut
	if (t["raspuns"] is not None and t["lista"] is lista and t["stare"] is st and t["limba"] == lb
			and t["se_citeste"] == bool(se_citeste)):
		return t["raspuns"]
	text, detaliu = L.texteSus(lista, st if lista is not None else {"stare": eroare}, lb)
	raspuns = {
		"result": True,
		"stare": (st or {}).get("stare") if lista is not None else (eroare or L.STARE_LIPSA),
		"se_citeste": bool(se_citeste),
		"text": text,
		"detaliu": detaliu,
		"autor": L.textAutor(),
		"fara_lista": L.randFaraLista() if lista is None else "",
		"sursa": (lista or {}).get("sursa") or L.SURSA_IMPLICITA,
		"versiune": (lista or {}).get("versiune") or "",
		"build": (lista or {}).get("build") or "",
		"randuri": [_randWeb(L, r) for r in L.randuri(lista, (st or {}).get("pachete_noi"), lb)],
	}
	t.update(lista=lista, stare=st, limba=lb, se_citeste=bool(se_citeste), raspuns=raspuns)
	return raspuns


def textLicenta(id_text, L=None):
	"""GET /api/licente-text?id=<id>"""
	L = _l(L)
	if not isinstance(id_text, str) or not L.ID_TEXT.match(id_text):
		return {"result": False, "message": _t("Adresa textului nu e bună.")}, 400
	text = L.citesteText(id_text)
	if text is None:
		return {"result": False, "message": _t("Textul acestei licențe lipsește din imagine.")}, 404
	return {"result": True, "id": id_text, "text": text}, 200


def _argument(request, nume, lungime):
	valori = (getattr(request, "args", None) or {}).get(nume)
	if not valori:
		return ""
	return valori[0].decode("ascii", "replace")[:lungime]


def rute(baza, resource, L=None):
	class LicenteResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, licente(L))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class TextResource(baza):
		def render_GET(self, request):
			try:
				corp, cod = textLicenta(_argument(request, b"id", 32), L)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"licente": LicenteResource(), b"licente-text": TextResource()}, PaginaResource()


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


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def _e(text):
	return _escape(u"%s" % (text or ""), True)


def texte():
	"""Textele scrise de scriptul paginii, traduse pe receptor"""
	return {
		"citeste": _t("Se citește lista licențelor..."),
		"citesteText": _t("Se citește textul..."),
		"textRau": _t("Textul nu se poate citi."),
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		"eroare": _t("Receptorul nu a putut citi lista licențelor."),
		"font": _t("Font:"),
		"lista": _t("Listă:"),
		"nou": _t("instalat după construire"),
		"randuri": _t("Rânduri: %d."),
		"dinRanduri": _t("Rânduri: %d din %d."),
		"nimic": _t("Niciun program nu se potrivește cu căutarea."),
		"textul": _t("Textul %d"),
	}


def pagina_text(stil, config_pagina, limba="ro"):
	drum = _drumMeniu("hds_licente")
	valori = {
		"__STIL_COMUN__": stil,
		"__LIMBA__": _e(limba or "ro"),
		"__CONFIG__": config_pagina,
		"__TEXTE__": json.dumps(texte(), ensure_ascii=False).replace("</", "<\\/"),
		"__T_TITLU__": _e(_t("Licențe")),
		"__T_CAUTA__": _e(_t("Caută un program sau o licență")),
		"__T_CITESTE__": _e(_t("Se citește lista licențelor...")),
		# drumul din meniu e HTML gata facut; textul din jurul lui se scapa
		"__T_ACELASI__": _e(_t("Același ecran e pe televizor, în %s.")).replace("%s", drum),
	}
	# o singura trecere: un nume venit din browser (in __CONFIG__) nu poate fi luat drept semn __X__
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
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .sus p{margin:0 0 8px;line-height:1.45;}
  .sus .autor{color:var(--text-slab);}
  .sus .adresa{color:var(--text-slab);font-size:.95rem;word-break:break-word;}
  .sus .adresa a{color:var(--text);display:inline-block;padding:11px 0;}
  .veche{color:#f5b83d;}
  .cauta{display:flex;gap:8px;margin:0 0 12px;}
  .cauta input{flex:1;min-height:44px;padding:6px 10px;border-radius:8px;border:1px solid var(--bordura);background:#1c2129;color:var(--text);font:inherit;}
  ul.lista{list-style:none;margin:0;padding:0;}
  ul.lista li{border-bottom:1px solid var(--bordura);}
  ul.lista button.rand{display:flex;flex-wrap:wrap;gap:4px 12px;justify-content:space-between;width:100%;min-height:44px;padding:8px 4px;background:none;border:0;color:var(--text);font:inherit;text-align:left;cursor:pointer;}
  ul.lista button.rand:hover,ul.lista button.rand:focus{background:#242a33;}
  .nume{font-weight:600;word-break:break-word;}
  .lic{color:var(--text-slab);font-size:.9rem;word-break:break-word;}
  .clasa{align-self:flex-start;font-size:.875rem;line-height:1.6;padding:0 8px;border-radius:10px;border:1px solid var(--bordura);color:var(--text-slab);white-space:nowrap;}
  .deschis{padding:4px 4px 12px;}
  .deschis p{margin:4px 0 8px;font-size:.95rem;line-height:1.45;color:var(--text-slab);}
  .file{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px;}
  .file button{min-height:44px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;font-size:.9rem;cursor:pointer;}
  .file button.ales{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  pre.text{font-family:monospace;font-size:.9rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;margin:0;max-height:60vh;overflow:auto;background:#161a20;border-radius:8px;padding:10px;}
  pre.explicatie{font-family:inherit;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.95rem;min-height:1.3em;}
  .nota{color:var(--text-slab);font-size:.9rem;margin:6px 0 0;line-height:1.45;}
  [hidden]{display:none;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<section class="card sus" id="sus"><p class="mesaj" id="mesaj">__T_CITESTE__</p></section>
<div class="cauta" id="cautare" hidden><input id="cauta" type="search" placeholder="__T_CAUTA__" aria-label="__T_CAUTA__"></div>
<section class="card" id="cardLista" hidden><ul class="lista" id="lista"></ul><p class="nota" id="numar"></p></section>
<p class="nota">__T_ACELASI__</p>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
var RANDURI = [];
var PAMPRENTA = "";
var DESCHISE = {};
function $(id){ return document.getElementById(id); }
function f(text){ var a = Array.prototype.slice.call(arguments, 1); var i = 0; return text.replace(/%d|%s/g, function(){ return a[i++]; }); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale){
  return fetch(adresa(cale), {cache: "no-store", credentials: "same-origin"}).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json();
  });
}
function mesaj(text){
  var s = $("sus"); s.textContent = "";
  var p = document.createElement("p"); p.className = "mesaj"; p.textContent = text; s.appendChild(p);
}
function sus(d){
  var s = $("sus"); s.textContent = "";
  var p = document.createElement("p"); p.textContent = d.text; if(d.stare === "veche" || d.stare === "lipsa" || d.stare === "stricata"){ p.className = "veche"; }
  s.appendChild(p);
  if(d.autor){ var au = document.createElement("p"); au.className = "autor"; au.textContent = d.autor; s.appendChild(au); }
  if(!d.detaliu){ return; }
  var a = document.createElement("p"); a.className = "adresa";
  var i = d.detaliu.indexOf(d.sursa);
  if(d.sursa && i !== -1 && /^https:\\/\\//.test(d.sursa)){
    a.appendChild(document.createTextNode(d.detaliu.slice(0, i)));
    var l = document.createElement("a"); l.href = d.sursa; l.rel = "noopener"; l.target = "_blank"; l.textContent = d.sursa; a.appendChild(l);
    a.appendChild(document.createTextNode(d.detaliu.slice(i + d.sursa.length)));
  } else { a.textContent = d.detaliu; }
  s.appendChild(a);
  if(d.fara_lista){ var fl = document.createElement("p"); fl.className = "nota"; fl.textContent = d.fara_lista; s.appendChild(fl); }
}
function deschide(li, r, idText){
  var div = document.createElement("div"); div.className = "deschis";
  var pre = document.createElement("pre"); pre.className = "text";
  if(!r.texte.length){
    // fara texte: numai explicatia (are deja ce spune randul de sub nume)
    pre.className = "text explicatie"; pre.textContent = r.explicatie;
    div.appendChild(pre); li.appendChild(div); DESCHISE[r.id] = ""; return;
  }
  var p = document.createElement("p"); p.textContent = r.detaliu; div.appendChild(p);
  var file = document.createElement("div"); file.className = "file";
  var ales = null;
  r.texte.forEach(function(t, k){
    var b = document.createElement("button"); b.type = "button"; b.textContent = t.nume || f(T.textul, k + 1);
    b.addEventListener("click", function(){ arataText(file, b, pre, r.id, t.id); });
    file.appendChild(b);
    if(t.id === idText){ ales = b; }
  });
  if(r.texte.length > 1){ div.appendChild(file); }
  div.appendChild(pre); li.appendChild(div);
  arataText(file, ales || file.firstChild, pre, r.id, ales ? idText : r.texte[0].id);
}
function comuta(li, r){
  var vechi = li.querySelector(".deschis");
  if(vechi){ li.removeChild(vechi); delete DESCHISE[r.id]; return; }
  deschide(li, r, "");
}
function arataText(file, b, pre, idRand, id){
  Array.prototype.forEach.call(file.children, function(x){ x.className = (x === b) ? "ales" : ""; });
  DESCHISE[idRand] = id;
  pre.textContent = T.citesteText;
  cerere("/api/licente-text?id=" + encodeURIComponent(id)).then(function(d){
    pre.textContent = d.result ? d.text : (d.message || T.textRau);
  }).catch(function(){ pre.textContent = T.nuRaspunde; });
}
function lista(){
  var q = $("cauta").value.trim().toLowerCase();
  var ul = $("lista"); ul.textContent = "";
  var n = 0;
  RANDURI.forEach(function(r){
    if(q && (r.nume + " " + r.versiune + " " + r.licenta + " " + r.licenta_om + " " + r.clasa_nume).toLowerCase().indexOf(q) === -1){ return; }
    n += 1;
    var li = document.createElement("li");
    var b = document.createElement("button"); b.type = "button"; b.className = "rand";
    var st = document.createElement("span");
    var inainte = r.fel === "font" ? T.font + " " : (r.fel === "lista" ? T.lista + " " : "");
    var nm = document.createElement("span"); nm.className = "nume"; nm.textContent = inainte + r.nume + (r.versiune ? " " + r.versiune : "");
    st.appendChild(nm);
    var lc = document.createElement("div"); lc.className = "lic"; lc.textContent = r.licenta_om || "-"; st.appendChild(lc);
    b.appendChild(st);
    if(r.clasa_nume && r.clasa_nume !== r.licenta_om){ var c = document.createElement("span"); c.className = "clasa"; c.textContent = r.clasa_nume; b.appendChild(c); }
    if(r.fel === "pachet"){ var c2 = document.createElement("span"); c2.className = "clasa veche"; c2.textContent = T.nou; b.appendChild(c2); }
    b.addEventListener("click", function(){ comuta(li, r); });
    li.appendChild(b); ul.appendChild(li);
    if(DESCHISE.hasOwnProperty(r.id)){ deschide(li, r, DESCHISE[r.id]); }
  });
  if(!n && RANDURI.length){ var gol = document.createElement("li"); gol.className = "nota"; gol.style.padding = "12px 4px"; gol.textContent = T.nimic; ul.appendChild(gol); }
  $("numar").textContent = n === RANDURI.length ? f(T.randuri, n) : f(T.dinRanduri, n, RANDURI.length);
}
function citeste(){
  cerere("/api/licente").then(function(d){
    if(!d.result){ mesaj(d.message || T.eroare); return; }
    sus(d);
    var areLista = d.stare !== "se_citeste" && d.randuri.length > 0;
    $("cautare").hidden = !areLista;
    $("cardLista").hidden = !areLista;
    // lista se face din nou numai cand s-a schimbat (randurile deschise raman deschise)
    var amprenta = JSON.stringify(d.randuri || []);
    if(amprenta !== PAMPRENTA){ PAMPRENTA = amprenta; RANDURI = d.randuri || []; lista(); }
    if(d.se_citeste){ setTimeout(citeste, d.stare === "se_citeste" ? 300 : 1500); }
  }).catch(function(){ mesaj(T.nuRaspunde); });
}
$("cauta").addEventListener("input", lista);
citeste();
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
	),
	"js": (
		N_("browser deconectat"),
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

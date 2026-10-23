# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# informatii_tabel_web.py: "Informatii despre sistem" in interfata web, ca tabele, ca pe televizor.
#
# Pe televizor: Meniu > Informatii despre sistem (Screens/Information.py, tabel pe doua coloane si textul brut pe
# ALBASTRU; Screens/HdsHdmiInfo.py). Aici: acelasi text din acelasi populate() (informatii_web._textEcran), impartit in
# sectiuni de acelasi modul ca pe televizor (Components/HdsInformatiiTabel.py), si butonul "Text brut". Informatii HDMI
# ca in informatii_web (coloanele din Components/HdsHdmiDate.py). Rutele inlocuiesc /api/informatii si /informatii din
# informatii_web.py (aspect_web.py le leaga dupa ele); raspunsul API pastreaza campurile de pana acum ("text", "coloane",
# "pagini") si adauga "sectiuni".
#
# Rute (poarta comuna a HdsJsonResource; numai citire):
#   GET /api/informatii?pagina=despre|receptor|tunere|memorie|stocare|retea|hdmi
#   GET /informatii/<pagina>
#
# FIRUL: render_GET ruleaza pe firul enigma2, ca ecranele de pe televizor (care citesc la fel, la deschidere).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _tabel():
	try:
		from Components import HdsInformatiiTabel as T
	except ImportError:
		import HdsInformatiiTabel as T
	return T


def _vechi():
	try:
		from . import informatii_web as V
	except ImportError:
		import informatii_web as V
	return V


def informatii(pagina, Information=None, D=None, T=None, V=None):
	"""GET /api/informatii: ce da informatii_web.informatii, plus sectiunile tabelului."""
	rez = (V or _vechi()).informatii(pagina, Information=Information, D=D)
	if rez.get("result") and rez.get("text") is not None:
		rez["sectiuni"] = (T or _tabel()).sectiuni(rez["text"])
	return rez


def rute(baza, resource):
	class InformatiiResource(baza):
		def render_GET(self, request):
			pagina = ""
			valori = (getattr(request, "args", None) or {}).get(b"pagina")
			if valori:
				pagina = valori[0].decode("ascii", "replace")[:20]
			try:
				return self._raspunde(request, informatii(pagina))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"informatii": InformatiiResource()}, {b"informatii": PaginaResource()}


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
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("info_screen"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informații despre receptor</title>
<style>__STIL_COMUN__
  main{max-width:1100px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  nav.file{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;}
  nav.file button,.unelte button{min-height:40px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;font-size:.88rem;cursor:pointer;}
  nav.file button.ales{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .unelte{display:flex;justify-content:flex-end;margin:0 0 8px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .coloane{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:4px 28px;}
  .sect{break-inside:avoid;margin:0 0 10px;}
  .sect h3{font-size:.95rem;margin:8px 0 4px;color:#9fb4ff;border-bottom:2px solid #2a3350;padding-bottom:4px;}
  .sect h4{font-size:.88rem;margin:8px 0 2px;}
  .r{display:grid;grid-template-columns:minmax(0,44%) minmax(0,1fr);gap:10px;padding:4px 0;border-bottom:1px solid var(--bordura);font-size:.88rem;}
  .r .e{color:var(--text-slab);overflow-wrap:anywhere;}
  .r .v{word-break:break-word;overflow-wrap:anywhere;}
  .r.lat{grid-template-columns:minmax(0,1fr);}
  .bara{grid-column:2;height:8px;border-radius:4px;background:#2a3350;overflow:hidden;margin:2px 0 4px;}
  .bara i{display:block;height:100%;background:#9fb4ff;}
  pre.text{font-family:monospace;font-size:.85rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;margin:0;}
  .bun{color:#7fdc9a;} .atentie{color:#f5b83d;} .rau{color:#ff8a80;} .stins{color:var(--text-slab);}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
</style>
</head>
<body>
<main>
<h1 id="titlu">Informații despre receptor</h1>
<nav class="file" id="file"></nav>
<div class="unelte"><button type="button" id="brut">Text brut</button></div>
<section class="card" id="continut"><p class="mesaj">Se citesc informațiile...</p></section>
<p class="nota">Aceleași ecrane sunt pe televizor, în __DRUM_MENIU__; tasta albastră arată acolo textul brut.</p>
</main>
<script>
var CFG = __CONFIG__;
var ALES = (location.pathname.split("/")[2] || new URLSearchParams(location.search).get("pagina") || "despre");
var BRUT = false, ULTIM = null;
function $(id){ return document.getElementById(id); }
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
function el(tag, clasa, text){ var e = document.createElement(tag); if(clasa){ e.className = clasa; } if(text !== undefined){ e.textContent = text; } return e; }
function file(d){
  var n = $("file"); n.textContent = "";
  (d.pagini || []).forEach(function(p){
    var b = el("button", p.id === ALES ? "ales" : "", p.titlu); b.type = "button";
    b.addEventListener("click", function(){ ALES = p.id; history.replaceState(null, "", "/informatii/" + p.id); citeste(); });
    n.appendChild(b);
  });
}
function tabel(sectiuni){
  var g = el("div", "coloane");
  sectiuni.forEach(function(s){
    var d = el("div", "sect");
    if(s.titlu){ d.appendChild(el("h3", "", s.titlu)); }
    s.randuri.forEach(function(r){
      if(r.subtitlu !== undefined){ d.appendChild(el("h4", "", r.subtitlu)); return; }
      var rd = el("div", "r" + (r.valoare ? "" : " lat"));
      rd.appendChild(el("span", r.valoare ? "e" : "v", r.eticheta));
      if(r.valoare){ rd.appendChild(el("span", "v", r.valoare)); }
      if(r.bara !== null && r.bara !== undefined){ var b = el("div", "bara"); var i = el("i"); i.style.width = Math.max(0, Math.min(100, r.bara)) + "%"; b.appendChild(i); rd.appendChild(b); }
      d.appendChild(rd);
    });
    g.appendChild(d);
  });
  return g;
}
function hdmi(coloane){
  var g = el("div", "coloane");
  (coloane || []).forEach(function(col){
    var div = el("div", "sect");
    col.forEach(function(r){
      if(r.titlu !== undefined){ div.appendChild(el("h3", "", r.titlu)); return; }
      var rd = el("div", "r"); rd.appendChild(el("span", "e", r.eticheta)); rd.appendChild(el("span", "v " + (r.ton || ""), r.valoare));
      div.appendChild(rd);
    });
    g.appendChild(div);
  });
  return g;
}
function arata(){
  var d = ULTIM, c = $("continut"); c.textContent = "";
  if(!d){ return; }
  $("titlu").textContent = d.titlu;
  $("brut").style.visibility = d.text !== undefined ? "visible" : "hidden";
  $("brut").textContent = BRUT ? "Tabel" : "Text brut";
  if(d.text !== undefined && (BRUT || !d.sectiuni)){ c.appendChild(el("pre", "text", d.text)); return; }
  c.appendChild(d.sectiuni ? tabel(d.sectiuni) : hdmi(d.coloane));
}
function citeste(){
  cerere("/api/informatii?pagina=" + encodeURIComponent(ALES)).then(function(d){
    file(d);
    if(!d.result){ $("continut").textContent = d.message || "Receptorul nu a putut citi informațiile."; return; }
    ULTIM = d; arata();
  }).catch(function(){ $("continut").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("brut").addEventListener("click", function(){ BRUT = !BRUT; arata(); });
citeste();
setInterval(function(){ if(ALES === "hdmi" || ALES === "memorie"){ citeste(); } }, 5000);
setInterval(function(){ if(ALES === "receptor" && document.visibilityState === "visible"){ citeste(); } }, 2000);
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
		N_("Informații despre receptor"),
		N_("Text brut"),
		N_("Se citesc informațiile..."),
		N_("Aceleași ecrane sunt pe televizor, în __DRUM_MENIU__; tasta albastră arată acolo textul brut."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Tabel"),
		N_("Text brut"),
		N_("Receptorul nu a putut citi informațiile."),
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

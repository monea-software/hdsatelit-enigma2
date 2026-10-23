# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# jurnal_web.py: „Ce e nou” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Screens/HdsJurnalVersiuni.py). Aceleasi doua parti, din acelasi modul (Components/HdsJurnalVersiuni.sectiuni):
# sus ce e nou (versiunile nevazute inca, sau versiunea care ruleaza), dedesubt „Versiunile de dinainte”, fara dubluri.
# Felurile au culorile de pe televizor (nou verde, reparat galben, imbunatatit albastru deschis); versiunile de
# dinainte stau stranse (<details>), fiecare se deschide la atingere, ca pagina sa nu aiba metri de derulat pe telefon.
#
# Din web jurnalul se DOAR citeste: „ultima versiune vazuta” o retine ecranul de pe receptor. Daca ar bifa-o si
# telefonul, ecranul care se arata singur la prima pornire dupa o actualizare nu s-ar mai arata.
#
# Rute (prin poarta comuna a HdsJsonResource):
#   GET /api/jurnal     {"versiune", "data", "build", "vazut", "titlu_sus", "sus": [versiuni], "jos": [versiuni],
#                        "noutati": [intrari nevazute, cu versiunea], "versiuni": [toate versiunile instalate]}
#   GET /jurnal         pagina
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau un modul fals.


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _J():
	from Components import HdsJurnalVersiuni
	return HdsJurnalVersiuni


def date(J=None):
	"""Corpul lui GET /api/jurnal. Un fisier lipsa sau stricat inseamna liste goale, nu eroare."""
	J = J or _J()
	lista = J.versiuni()
	curent = J.build_curent()
	vazut = J.ultima_vazuta()
	ruleaza = J.versiunea_care_ruleaza(lista, curent)
	sus, jos = J.sectiuni(lista, vazut, curent)

	def intrare(x):
		return {"fel": x["fel"], "eticheta": J.eticheta(x["fel"]), "text": J.text(x)}

	def versiune(v):
		return {
			"versiune": v["versiune"],
			"build": v["build"],
			"data": v["data"],
			"instalata": ruleaza is not None and v["build"] == ruleaza["build"],
			"intrari": [intrare(x) for x in v["intrari"]],
		}

	noutati = []
	for v, x in J.intrari_noi(lista, vazut, curent):
		rand = intrare(x)
		rand["versiune"] = v["versiune"]
		rand["data"] = v["data"]
		noutati.append(rand)
	if len(sus) == 1:
		titlu = _t("Ce e nou în versiunea %s") % sus[0]["versiune"]
	elif sus:
		titlu = _t("Ce e nou de la ultima actualizare")
	else:
		titlu = ""
	return {
		"result": True,
		"build": curent,
		"versiune": ruleaza["versiune"] if ruleaza else "",
		"data": ruleaza["data"] if ruleaza else "",
		"vazut": vazut,
		"titlu_sus": titlu,
		"sus": [versiune(v) for v in sus],
		"jos": [versiune(v) for v in jos],
		"noutati": noutati,
		"versiuni": [versiune(v) for v in sus + jos],
	}


def rute(baza, resource, J=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii /jurnal). `baza` e HdsJsonResource din plugin.py."""

	class JurnalResource(baza):
		"""GET /api/jurnal: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, date(J))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /jurnal: pagina „Ce e nou”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"jurnal": JurnalResource()}, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca panoul (reteaua locala, apoi ?token= sau cookie-ul browserului asociat); un browser neconectat
	primeste pagina de asociere. Pagina nu schimba nimic, deci nu primeste tokenul CSRF."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		_secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou("", "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ce e nou</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 4px;}
  .subtitlu{color:var(--text-slab);font-size:.85rem;margin:0 0 16px;min-height:1.2em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin-bottom:16px;}
  .card h2{font-size:.95rem;margin:0 0 12px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .versiune{margin-bottom:20px;}
  .versiune:last-child{margin-bottom:0;}
  .versiune h3{font-size:1rem;margin:0 0 2px;}
  .cand{color:var(--text-slab);font-size:.85rem;margin:0 0 8px;}
  details.versiune{margin-bottom:8px;border-bottom:1px solid var(--bordura);}
  details.versiune summary{cursor:pointer;min-height:44px;display:flex;align-items:center;gap:10px;font-size:1rem;font-weight:600;}
  details.versiune summary .cand{margin:0;font-weight:400;}
  details.versiune[open] summary{margin-bottom:6px;}
  ul{list-style:none;margin:0;padding:0;}
  li{display:flex;gap:10px;align-items:flex-start;padding:7px 0;border-bottom:1px solid var(--bordura);font-size:.92rem;line-height:1.45;}
  li:last-child{border-bottom:none;}
  .fel{flex:0 0 auto;min-width:110px;font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;padding:3px 8px;border-radius:999px;text-align:center;color:#10162a;font-weight:600;}
  .f-nou{background:#4fd18b;} .f-reparat{background:#f5b83d;} .f-imbunatatit{background:#9fb4ff;}
  .gol{color:var(--text-slab);font-size:.9rem;margin:0;}
  footer{color:var(--text-slab);font-size:.8rem;display:flex;flex-wrap:wrap;gap:8px 18px;}
  /* pe telefon eticheta sta deasupra textului, altfel randul ar ramane cu doua degete latime */
  @media(max-width:520px){
    li{flex-direction:column;gap:4px;}
    .fel{min-width:0;align-self:flex-start;}
  }
</style>
</head>
<body>
<main>
<h1>Ce e nou</h1>
<p class="subtitlu" id="subtitlu"></p>
<div class="card">
  <h2 id="titluSus">Ce e nou</h2>
  <div id="sus"><p class="gol">Se încarcă...</p></div>
</div>
<div class="card" id="cardJos">
  <h2>Versiunile de dinainte</h2>
  <div id="jos"><p class="gol">Se încarcă...</p></div>
</div>
<footer><a href="/meniu">Tot meniul receptorului</a></footer>
</main>
<script>
var CFG = __CONFIG__;
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function gol(text){
  var p = document.createElement("p");
  p.className = "gol";
  p.textContent = text;
  return p;
}
function randIntrare(x){
  // textele jurnalului intra in pagina NUMAI prin textContent, niciodata ca bucata de HTML
  var li = document.createElement("li");
  var fel = document.createElement("span");
  fel.className = "fel f-" + (x.fel || "");
  fel.textContent = x.eticheta || "";
  var text = document.createElement("span");
  text.textContent = x.text || "";
  li.appendChild(fel);
  li.appendChild(text);
  return li;
}
function listaIntrari(v){
  var ul = document.createElement("ul");
  (v.intrari || []).forEach(function(x){ ul.appendChild(randIntrare(x)); });
  return ul;
}
function numeVersiune(v){
  return "Versiunea " + v.versiune + (v.instalata ? " (instalată acum)" : "");
}
// versiunile de sus: deschise, cu titlu
function listaVersiuni(cutie, versiuni){
  for(var i = 0; i < versiuni.length; i++){
    var v = versiuni[i];
    var sectiune = document.createElement("div");
    sectiune.className = "versiune";
    var titlu = document.createElement("h3");
    titlu.textContent = numeVersiune(v);
    sectiune.appendChild(titlu);
    if(v.data){
      var cand = document.createElement("p");
      cand.className = "cand";
      cand.textContent = "din " + v.data;
      sectiune.appendChild(cand);
    }
    sectiune.appendChild(listaIntrari(v));
    cutie.appendChild(sectiune);
  }
}
// versiunile de dinainte: stranse, fiecare se deschide la atingere
function listaStransa(cutie, versiuni){
  for(var i = 0; i < versiuni.length; i++){
    var v = versiuni[i];
    var d = document.createElement("details");
    d.className = "versiune";
    var s = document.createElement("summary");
    var nume = document.createElement("span");
    nume.textContent = numeVersiune(v);
    s.appendChild(nume);
    var cand = document.createElement("span");
    cand.className = "cand";
    cand.textContent = (v.data ? "din " + v.data + " · " : "") + (v.intrari || []).length + " schimbări";
    s.appendChild(cand);
    d.appendChild(s);
    d.appendChild(listaIntrari(v));
    cutie.appendChild(d);
  }
}
function arata(d){
  var sus = document.getElementById("sus");
  var jos = document.getElementById("jos");
  sus.textContent = "";
  jos.textContent = "";
  if(d.versiune){
    document.getElementById("subtitlu").textContent =
      "Versiunea instalată acum: " + d.versiune + (d.data ? (", din " + d.data) : "") + ".";
  }
  if(!d.sus || !d.sus.length){
    document.getElementById("titluSus").textContent = "Ce e nou";
    sus.appendChild(gol("Jurnalul versiunilor nu este disponibil pe acest receptor."));
    document.getElementById("cardJos").style.display = "none";
    return;
  }
  document.getElementById("titluSus").textContent = d.titlu_sus || "Ce e nou";
  listaVersiuni(sus, d.sus);
  if(d.jos && d.jos.length){
    listaStransa(jos, d.jos);
  } else {
    document.getElementById("cardJos").style.display = "none";
  }
}
fetch(adresa("/api/jurnal"), {cache: "no-store", credentials: "same-origin"}).then(function(r){
  if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
  if(!r.ok){ throw new Error("HTTP " + r.status); }
  return r.json();
}).then(arata).catch(function(e){
  document.getElementById("sus").textContent = "";
  document.getElementById("sus").appendChild(gol("Receptorul nu a răspuns (" + e.message + ")."));
  document.getElementById("jos").textContent = "";
});
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
		N_("Ce e nou"),
		N_("Se încarcă..."),
		N_("Versiunile de dinainte"),
		N_("Tot meniul receptorului"),
	),
	"js": (
		N_("Versiunea"),
		N_("(instalată acum)"),
		N_("din"),
		N_("schimbări"),
		N_("Versiunea instalată acum:"),
		N_(", din"),
		N_("Ce e nou"),
		N_("Jurnalul versiunilor nu este disponibil pe acest receptor."),
		N_("browser deconectat"),
		N_("Receptorul nu a răspuns ("),
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

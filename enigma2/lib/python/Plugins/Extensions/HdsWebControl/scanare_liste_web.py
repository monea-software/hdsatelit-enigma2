# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# scanare_liste_web.py: „Liste implicite de canale” în interfața web (HdsWebControl).
#
# Orice ecran de pe receptor are pereche în interfața web. Pe televizor: Meniu > Scanare > Liste implicite de canale
# (Screens/HdsListeImplicite.py, modul avansat). Aici: același text și aceleași rânduri, din aceleași funcții
# (HdsListeImplicite.actiuni, are_liste), fiecare cu pagina ei din web: scanarea pe satelit, prin cablu, terestru
# (numai pentru tunerele receptorului) și importul (/import). Asistentul vechi al pachetelor de liste nu are pagină web;
# când imaginea are pachete, rândul lui spune că se deschide de pe televizor.
#
# Rute (poarta comuna a HdsJsonResource):
#   GET  /api/liste-implicite      textul, rândurile (cheia, textul, explicația, pagina web)
#   GET  /liste-implicite          pagina
#
# FIRUL: render_GET rulează pe firul enigma2; citește cel mult câteva fișiere .info mici. Fișierul nu importă nimic din
# enigma2 la încărcare: probele de pe PC dau modulul lor (M).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Screens import HdsListeImplicite
	return HdsListeImplicite


def stare(M=None):
	"""GET /api/liste-implicite."""
	M = _m(M)
	cu_liste = M.are_liste()
	return {
		"result": True,
		"titlu": M._t("Liste implicite de canale"),
		"are_liste": cu_liste,
		"text": M.text_intro(cu_liste),
		"actiuni": M.actiuni(M.are_tuner, cu_liste),
	}


def rute(baza, resource, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/liste-implicite: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /liste-implicite: pagina."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"liste-implicite": StareResource()}, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /setari-din-copie: reteaua locala, apoi ?token= sau cookie-ul browserului asociat."""
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
<title>Liste implicite de canale</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1rem;line-height:1.45;margin:0 0 8px;}
  a.actiune{display:block;padding:12px 14px;margin:8px 0 0;border-radius:8px;border:1px solid var(--bordura);color:inherit;text-decoration:none;min-height:44px;}
  a.actiune:hover{background:rgba(255,255,255,.04);}
  .titlu{font-weight:600;display:block;}
  .desc{display:block;color:var(--text-slab);font-size:.85rem;line-height:1.4;margin-top:2px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;}
  .eroare{color:#ffb4a8;}
</style>
</head>
<body>
<main>
<h1 id="titlu">Liste implicite de canale</h1>
<section class="card">
  <p class="acum" id="text">Se citește...</p>
  <div id="actiuni"></div>
</section>
<p class="mesaj" id="mesaj"></p>
</main>
<script>
var CFG = __CONFIG__;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
fetch(adresa("/api/liste-implicite"), {cache: "no-store", credentials: "same-origin"}).then(function(r){
  if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
  return r.json();
}).then(function(d){
  if(!d.result){ $("text").textContent = d.message || "Receptorul nu a putut citi listele."; return; }
  $("titlu").textContent = d.titlu || "Liste implicite de canale";
  $("text").textContent = d.text;
  var c = $("actiuni"); c.textContent = "";
  (d.actiuni || []).forEach(function(a){
    var l = document.createElement(a.web ? "a" : "div"); l.className = "actiune";
    if(a.web){ l.href = adresa(a.web); }
    var t = document.createElement("span"); t.className = "titlu"; t.textContent = a.text;
    var e = document.createElement("span"); e.className = "desc";
    e.textContent = a.web ? a.explicatie : a.explicatie + " Se deschide de pe televizor.";
    l.appendChild(t); l.appendChild(e); c.appendChild(l);
  });
}).catch(function(){ $("mesaj").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; $("mesaj").className = "mesaj eroare"; });
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
		N_("Liste implicite de canale"),
		N_("Se citește..."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul nu a putut citi listele."),
		N_("Liste implicite de canale"),
		N_("Se deschide de pe televizor."),
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

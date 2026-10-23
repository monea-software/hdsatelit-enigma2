# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# setari_copie_web.py: starea setarilor puse la loc din copie in interfata web (HdsWebControl).
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor: ecranul „Import Canale si Setari”
# (Plugins/Extensions/HdsImportSetari) arata in descriere setarile care asteapta repornirea interfetei, proba lor si
# setarile scoase de garda de caderi. Aici: aceeasi stare, din aceeasi logica (Components/HdsSetariDinCopie.py), si
# repornirea interfetei, dupa care tools/enigma2.sh le uneste peste settings.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/setari-din-copie              starea (numere si texte; niciodata cheile sau valorile)
#   POST /api/setari-din-copie-reporneste   reporneste interfata (TryQuitMainloop 3, ca din meniu)
#   GET  /setari-din-copie                  pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; citirea e scurta (un fisier mic si doua stat). Fisierul nu
# importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (M).


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
	from Components import HdsSetariDinCopie
	return HdsSetariDinCopie


def stare(M=None):
	"""Pentru GET /api/setari-din-copie."""
	M = _m(M)
	st = M.stare()
	return {
		"result": True,
		"asteapta": int(st.get("asteapta") or 0),
		"garda": bool(st.get("garda")),
		"cazut": bool(st.get("cazut")),
		"texte": M.texteStare(st),
	}


def reporneste(sesiune):
	"""POST /api/setari-din-copie-reporneste: aceeasi repornire ca /api/accel-reporneste."""
	from .accel_web import reporneste as _reporneste
	return _reporneste(sesiune)


def rute(baza, resource, M=None, sesiune=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py;
	`sesiune` e o functie care intoarce sesiunea enigma2 (plugin._sesiune se pune abia la pornirea sesiunii)."""

	class StareResource(baza):
		"""GET /api/setari-din-copie: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ReporniresResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, reporneste(sesiune() if sesiune else None))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /setari-din-copie: pagina „Setările importate”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"setari-din-copie": StareResource(),
		b"setari-din-copie-reporneste": ReporniresResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic si /accel."""
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
<title>Setările importate</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1rem;line-height:1.45;margin:0 0 8px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#1f771f;color:#fff;font:inherit;cursor:pointer;}
  button:disabled{opacity:.5;cursor:default;}
</style>
</head>
<body>
<main>
<h1>Setările importate</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <div id="stare"></div>
    <button type="button" id="reporneste" disabled>Repornește interfața acum</button>
  </section>
  <p class="nota">Setările aduse cu „Import canale și setări” nu se scriu cât interfața rulează: la oprire ea ar scrie
  peste ele setările din memorie. Așteaptă până la următoarea pornire a interfeței, când se unesc cu setările
  receptorului. Dacă în primele 30 de minute după aceea interfața se oprește neașteptat de două ori în 10 minute, se
  pun la loc setările de dinainte; o repornire a receptorului încheie proba. Dacă setările nu se pot uni (de exemplu,
  memoria receptorului e plină), ele rămân în așteptare și setările receptorului nu se schimbă. Pe televizor, aceeași
  stare apare în ecranul „Import canale și setări”, iar repornirea din meniu, la „Standby și repornire”.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function arata(d){
  var s = $("stare"); s.textContent = "";
  var texte = d.texte || [];
  if(!texte.length){ texte = ["Nicio setare importată nu așteaptă și nicio probă nu este în curs."]; }
  texte.forEach(function(t){ var p = document.createElement("p"); p.className = "acum"; p.textContent = t; s.appendChild(p); });
  $("reporneste").disabled = !d.asteapta;
}
function citeste(){
  return cerere("/api/setari-din-copie").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("reporneste").addEventListener("click", function(){
  $("reporneste").disabled = true;
  mesaj("Se repornește interfața...");
  cerere("/api/setari-din-copie-reporneste", "POST").then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ setTimeout(function(){ location.reload(); }, 15000); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
citeste();
setInterval(citeste, 10000);
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
		N_("Setările importate"),
		N_("Se citește starea..."),
		N_("Repornește interfața acum"),
		N_("Setările aduse cu „Import canale și setări” nu se scriu cât interfața rulează: la oprire ea ar "
			"scrie peste ele setările din memorie. Așteaptă până la următoarea pornire a interfeței, când se "
			"unesc cu setările receptorului. Dacă în primele 30 de minute după aceea interfața se oprește "
			"neașteptat de două ori în 10 minute, se pun la loc setările de dinainte; o repornire a "
			"receptorului încheie proba. Dacă setările nu se pot uni (de exemplu, memoria receptorului e "
			"plină), ele rămân în așteptare și setările receptorului nu se schimbă. Pe televizor, aceeași "
			"stare apare în ecranul „Import canale și setări”, iar repornirea din meniu, la „Standby și "
			"repornire”."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nicio setare importată nu așteaptă și nicio probă nu este în curs."),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se repornește interfața..."),
		N_("Receptorul nu răspunde."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# marime_text_web.py: "Marimea textului" in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Interfata si aspect > Marimea textului (Screens/FontSetup.py). Aici: acelasi procent, aceleasi
# limite si trepte, aceeasi proba, din aceeasi logica (Components/HdsMarimeText.py). Proba din pagina se schimba pe loc
# in browser; pe televizor noua marime se vede in ecranele deschise dupa salvare.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/marime-text                       procentul salvat, limitele si proba
#   POST /api/marime-text-seteaza?procent=80..130   salveaza si aplica
#   GET  /marime-text                           pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (o setare si un fisier mic). Modulul nu importa nimic din
# enigma2 la incarcare: probele de pe PC dau modulul lor (M), setarile lor (config) si skinul lor.


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsMarimeText
	return HdsMarimeText


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def stare(M=None, config=None):
	"""GET /api/marime-text."""
	M = _m(M)
	rez = M.stare(config, traducere=_t)
	rez["result"] = True
	return rez


def seteaza(argumente, M=None, config=None, skin_modul=None, configfile=None):
	"""POST /api/marime-text-seteaza: o valoare straina nu schimba nimic."""
	M = _m(M)
	procent = argumente.get("procent")
	if procent is None:
		rez = stare(M, config)
		rez.update({"result": False, "message": _t("Se alege cu procent=80..130.")})
		return rez
	bun, rezultat = M.seteaza(procent, config=config, skin_modul=skin_modul, configfile=configfile)
	rez = stare(M, config)
	if bun:
		rez.update({"result": True,
			"message": _t("Salvat: %s. Pe televizor se vede în ecranele deschise de acum.") % M.text(rezultat)})
	else:
		rez.update({"result": False, "message": _t(rezultat)})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:12].strip()
	return rez


def rute(baza, resource, M=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return ({b"marime-text": StareResource(), b"marime-text-seteaza": SeteazaResource()},
		{b"marime-text": PaginaResource()})


def pagina(request):
	"""Aceeasi poarta ca /paznic: numai din casa, cu browserul asociat sau ?token=."""
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


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); fara pachet (probele de pe PC) ramane "Meniu"."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_font_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mărimea textului</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .reglaj{display:grid;grid-template-columns:minmax(0,1fr) minmax(140px,2fr) 4.5em;gap:14px;align-items:center;}
  .reglaj label{font-size:1rem;}
  .reglaj input[type=range]{width:100%;min-height:44px;accent-color:#9fb4ff;}
  .procent{font-weight:700;font-size:1.15rem;text-align:right;color:#9fb4ff;}
  .capete{display:flex;justify-content:space-between;color:var(--text-slab);font-size:.82rem;grid-column:2;margin-top:-10px;}
  .proba{background:#10162a;border-radius:8px;padding:12px 14px;overflow:hidden;}
  .proba div{white-space:nowrap;overflow:hidden;line-height:1.5;}
  .proba .ales{background:#374ea1;color:#fff;border-radius:4px;padding:0 10px;margin:4px 0;}
  .proba .setare{display:flex;justify-content:space-between;gap:12px;}
  .proba .setare span:last-child{font-weight:700;color:#9fb4ff;}
  .proba .mic{color:#c9d2e3;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;}
  .butoane button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .butoane button.principal{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .reglaj{grid-template-columns:1fr 4.5em;} .reglaj label{grid-column:1 / span 2;} .capete{grid-column:1;} }
</style>
</head>
<body>
<main>
<h1>Mărimea textului</h1>
<p class="mesaj" id="incarcare">Se citește setarea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <div class="reglaj">
      <label for="procent">Mărimea tuturor textelor</label>
      <input type="range" id="procent" min="80" max="130" step="5" value="100" aria-describedby="valoare">
      <span class="procent" id="valoare">100%</span>
      <div class="capete"><span id="minim">80%</span><span id="maxim">130%</span></div>
    </div>
    <p class="nota">Proba, cu mărimea aleasă:</p>
    <div class="proba" id="proba"></div>
    <div class="butoane">
      <button type="button" class="principal" id="salveaza">Salvează</button>
      <button type="button" id="implicit">Înapoi la 100%</button>
      <button type="button" id="renunta">Renunță</button>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <p class="nota" id="salvat"></p>
  <p class="nota">Procentul se aplică la toate textele de pe televizor, în ecranele pe care le deschizi după salvare. Același reglaj e pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var STARE = null;
// marimile skinului HDSatelit la 1920 se arata aici la jumatate (titlul de 40 devine 20 px la 100%)
var SCARA = 0.5;
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
function familie(f){ return f === "Bold" ? "700" : "400"; }
function proba(){
  var p = parseInt($("procent").value, 10);
  $("valoare").textContent = p + "%";
  var c = $("proba"); c.textContent = "";
  var r = {};
  (STARE.proba || []).forEach(function(x){ r[x.cheie] = x; });
  function rand(x, clasa){
    // randul probei care nu incape se deruleaza (hds-derulant, cadru_web.py)
    var d = document.createElement("div"); d.className = "hds-derulant" + (clasa ? " " + clasa : "");
    d.textContent = x.text; d.style.fontSize = (x.baza * p / 100 * SCARA).toFixed(1) + "px"; d.style.fontWeight = familie(x.familie);
    if(x.familie === "Fixed"){ d.style.fontStretch = "condensed"; }
    return d;
  }
  if(r.proba_titlu){ c.appendChild(rand(r.proba_titlu)); }
  if(r.proba_rand){ c.appendChild(rand(r.proba_rand)); }
  if(r.proba_ales){ c.appendChild(rand(r.proba_ales, "ales")); }
  if(r.proba_setare && r.proba_valoare){
    var s = document.createElement("div"); s.className = "setare";
    var a = rand(r.proba_setare), b = rand(r.proba_valoare);
    var sa = document.createElement("span"), sb = document.createElement("span");
    sa.textContent = a.textContent; sa.style.cssText = a.style.cssText; sb.textContent = b.textContent; sb.style.cssText = b.style.cssText;
    s.appendChild(sa); s.appendChild(sb); c.appendChild(s);
  }
  if(r.proba_mic){ c.appendChild(rand(r.proba_mic, "mic")); }
  mesaj(p === STARE.procent ? "" : "Nesalvat: " + p + "%. Salvat acum: " + STARE.text + ".");
}
function arata(d){
  STARE = d;
  var i = $("procent"); i.min = d.minim; i.max = d.maxim; i.step = d.pas; i.value = d.procent;
  $("minim").textContent = d.minim + "%"; $("maxim").textContent = d.maxim + "%";
  $("salvat").textContent = "Salvat acum: " + d.text + ". Din fabrică: " + d.implicit + "%.";
  proba();
}
function citeste(){
  return cerere("/api/marime-text").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setarea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("procent").addEventListener("input", proba);
$("implicit").addEventListener("click", function(){ $("procent").value = STARE.implicit; proba(); });
$("renunta").addEventListener("click", function(){ $("procent").value = STARE.procent; proba(); });
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("procent", $("procent").value);
  mesaj("Se salvează...");
  cerere("/api/marime-text-seteaza", "POST", q).then(function(d){
    if(d.procent !== undefined){ arata(d); }
    mesaj(d.message, !d.result);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
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
		N_("Mărimea textului"),
		N_("Se citește setarea..."),
		N_("Mărimea tuturor textelor"),
		N_("Proba, cu mărimea aleasă:"),
		N_("Salvează"),
		N_("Înapoi la 100%"),
		N_("Renunță"),
		N_("Procentul se aplică la toate textele de pe televizor, în ecranele pe care le deschizi după "
			"salvare. Același reglaj e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nesalvat:"),
		N_("%. Salvat acum:"),
		N_("Salvat acum:"),
		N_(". Din fabrică:"),
		N_("Receptorul nu a putut citi setarea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează..."),
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

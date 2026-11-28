# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ventilator_web.py: pagina „Ventilatorul” din interfata web (HdsWebControl), perechea ecranului Screens/TempFanControl.py
# (0.8.0, RW1). Cod propriu, scris de la zero.
#
#   GET  /api/ventilator                 temperatura, turatia, ce are driverul, alegerile si alegerea de acum (numai citire)
#   POST /api/ventilator-seteaza?mod=..  alegerea (auto / maxim / pornit, cele pe care le are receptorul), salvata si
#                                        scrisa pe loc (Components/HdsVentilator.seteaza)
#   GET  /ventilator                     pagina; valorile se citesc din nou la 5 secunde
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (V) si setarile lor.


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _c():
	from . import meniu_comun_web
	return meniu_comun_web


def _v(V=None):
	if V is not None:
		return V
	from Components import HdsVentilator
	return HdsVentilator


def stare(V=None):
	"""Pentru GET /api/ventilator."""
	V = _v(V)
	V.initConfig()
	s = V.stare()
	rez = {"result": True, "are": s["are"], "familie": s["familie"], "mod": s["mod"],
		"alegeri": [[a, b] for a, b in s["alegeri"]], "turatie": s["turatie"],
		"temperaturi": [[n, g] for n, g in s["temperaturi"]], "driver": s.get("driver") or {}}
	if s.get("vu"):
		rez["vu"] = s["vu"]
	return rez


def seteaza(argumente, V=None, configfile=None):
	"""POST /api/ventilator-seteaza: mod=<una din alegerile receptorului>."""
	V = _v(V)
	V.initConfig()
	if not V.areVentilator():
		rez = {"result": False, "message": _t("Niciun ventilator detectat pe acest receptor.")}
	elif V.seteaza(argumente.get("mod", ""), configfile=configfile):
		rez = {"result": True, "message": _t("Salvat.")}
	else:
		rez = {"result": False, "message": _t("Alegerea trimisă nu e una a acestui receptor.")}
	rez["stare"] = stare(V)
	return rez


def rute(baza, resource, V=None, configfile=None):
	"""({nume: resursa de sub /api}, {nume: resursa pagina}); `baza` e HdsJsonResource din plugin.py."""

	class Stare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(V))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class Seteaza(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(_c().argumente(request, ("mod",), 16), V, configfile))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return _c().pagina(request, pagina)

	return {b"ventilator": Stare(), b"ventilator-seteaza": Seteaza()}, {b"ventilator": Pagina()}


def pagina(stil, config_pagina):
	C = _c()
	return C.sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": C.drumHtml("hds_fan_control")})


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ventilatorul</title>
<style>__STIL_COMUN__ __STIL_PAGINI__</style>
</head>
<body>
<main>
<h1>Ventilatorul</h1>
<p class="mesaj" id="incarcare">Se citește ventilatorul...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Temperatura</h2>
    <div id="temperaturi"></div>
    <p class="nota ascuns" id="faraTemperatura">Temperatura nu se poate citi pe acest receptor.</p>
    <div class="status-linie ascuns" id="randTuratie"><span>Turația</span><span id="turatie"></span></div>
  </section>
  <section class="card" id="cardReglaj">
    <h2>Cum merge ventilatorul</h2>
    <div class="rand">
      <label for="mod">Ventilatorul</label>
      <select id="mod"></select>
    </div>
    <p class="nota">Automat (din fabrică): receptorul îl reglează singur după temperatură, și în standby, și după repornire; nu se scrie nimic. Turație maximă și Pornit mereu se păstrează după standby și după repornire; la întoarcerea pe Automat se pun la loc valorile de dinainte.</p>
  </section>
  <p class="nota ascuns" id="faraVentilator">Niciun ventilator detectat pe acest receptor.</p>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
function rand(stanga, dreapta){
  var l = document.createElement("div"); l.className = "status-linie";
  var a = document.createElement("span"); a.textContent = stanga;
  var b = document.createElement("span"); b.textContent = dreapta;
  l.appendChild(a); l.appendChild(b); return l;
}
function arata(d){
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  $("faraVentilator").classList.toggle("ascuns", !!d.are);
  var t = $("temperaturi"); t.textContent = "";
  if(d.are){
    var acum = d.mod; (d.alegeri || []).forEach(function(a){ if(a[0] === d.mod){ acum = a[1]; } });
    t.appendChild(rand("Ventilatorul", acum));
  }
  (d.temperaturi || []).forEach(function(x){ t.appendChild(rand(x[0], x[1] + " °C")); });
  $("faraTemperatura").classList.toggle("ascuns", (d.temperaturi || []).length > 0 || !d.are);
  $("randTuratie").classList.toggle("ascuns", d.turatie === null || d.turatie === undefined);
  $("turatie").textContent = (d.turatie === null || d.turatie === undefined) ? "" : d.turatie + " RPM";
  var sel = $("mod");
  $("cardReglaj").classList.toggle("ascuns", !d.are || (d.alegeri || []).length < 2);
  if(document.activeElement !== sel){
    sel.textContent = "";
    (d.alegeri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
    sel.value = d.mod;
  }
}
function citeste(){
  return cerere("/api/ventilator").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi ventilatorul."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("mod").addEventListener("change", function(){
  mesaj("Se salvează...");
  var q = new URLSearchParams(); q.set("mod", $("mod").value);
  cerere("/api/ventilator-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.stare){ $("mod").blur(); arata(d.stare); }
  }).catch(nimicNuRaspunde);
});
citeste();
setInterval(citeste, 5000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginii

def N_(text):
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Ventilatorul"),
		N_("Se citește ventilatorul..."),
		N_("Temperatura"),
		N_("Temperatura nu se poate citi pe acest receptor."),
		N_("Turația"),
		N_("Cum merge ventilatorul"),
		N_("Automat (din fabrică): receptorul îl reglează singur după temperatură, și în standby, și după repornire; "
			"nu se scrie nimic. Turație maximă și Pornit mereu se păstrează după standby și după repornire; la "
			"întoarcerea pe Automat se pun la loc valorile de dinainte."),
		N_("Niciun ventilator detectat pe acest receptor."),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Ventilatorul"),
		N_("Receptorul nu a putut citi ventilatorul."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează..."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

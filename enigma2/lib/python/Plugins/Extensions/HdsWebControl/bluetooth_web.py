# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""TV Bluetooth pairing exposed through the authenticated web gateway."""
from . import meniu_comun_web as MC


def N_(text):
	return text


def rute(baza, resource):
	from Components.HdsBluetooth import manager

	class Stare(baza):
		def render_GET(self, request):
			return self._raspunde(request, manager.stare())

	class Comanda(baza):
		schimbaCeva = True

		def render_POST(self, request):
			args = MC.argumente(request, ("actiune", "id"), lung=40)
			return self._raspunde(request, manager.porneste(args.get("actiune", ""), args.get("id", "")))

	# the film and IPTV sound in a headset, the same object as the row of the TV screen (Components/HdsBluetoothSunet.py)
	class StareSunet(baza):
		def render_GET(self, request):
			from Components import HdsBluetoothSunet as S
			S.sunet.porneste()
			s = S.sunet.stare()
			s.update(poate=S.poate(), nod=S.areNod(), eticheta=S.sunet.eticheta())
			return self._raspunde(request, s)

	class ComandaSunet(baza):
		schimbaCeva = True

		def render_POST(self, request):
			from Components import HdsBluetoothSunet as S
			args = MC.argumente(request, ("actiune", "adresa", "intarziere"))
			actiune = args.get("actiune", "")
			if actiune == "citeste":
				return self._raspunde(request, S.sunet.citeste())
			if actiune == "intarziere":
				try:
					return self._raspunde(request, S.sunet.intarziere(int(args.get("intarziere", "0"))))
				except ValueError:
					return self._raspunde(request, {"result": False, "message": ""})
			return self._raspunde(request, S.sunet.alege(args.get("adresa", "")))

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from . import plugin as P
			if not P._esteAdresaLocala(P._adresaClient(request)):
				request.setResponseCode(403)
				return b""
			P._anteteHtml(request)
			secret, browser = P._sesiuneDinCerere(request)
			if browser is None:
				return P._PAGINA_ASOCIERE.encode("utf-8")
			cfg = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
			from .traducere_pagini import traduce
			return MC.sablon(traduce(PAGINA, TEXTE_PAGINA), P._STIL_COMUN, cfg).encode("utf-8")

	return {b"bluetooth": Stare(), b"bluetooth-comanda": Comanda(), b"bluetooth-sunet": StareSunet(),
		b"bluetooth-sunet-comanda": ComandaSunet()}, Pagina()


PAGINA = """<!DOCTYPE html><html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Telecomandă Bluetooth</title>
<style>__STIL_COMUN__ __STIL_PAGINI__</style></head><body><main>
<h1>Telecomandă Bluetooth</h1><p>Pune telecomanda în modul de asociere, apoi apasă Caută.</p>
<button type="button" id="cauta">Caută</button><p id="mesaj" role="status"></p><div id="lista"></div>
<section id="sunet" hidden><h2>Sunetul receptorului în cască Bluetooth</h2>
<p><select id="casca" aria-label="Sunetul receptorului în cască Bluetooth"></select></p><p><label>Întârzierea sunetului în cască (ms) <input type="number" id="intarziere" min="-300" max="300" step="20" value="0"></label></p><p id="mesajSunet" role="status"></p></section>
<p><a href="/dispozitive-intrare">Repetarea tastelor</a> <a href="/telecomenzi">Asocierea tastelor</a></p>
</main><script>__SCRIPT_COMUN__
function comanda(actiune, id){
  var q = new URLSearchParams(); q.set("actiune", actiune); if(id){q.set("id", id);}
  return cerere("/api/bluetooth-comanda", "POST", q).then(function(d){
    if(!d.result){$("mesaj").textContent = d.message || "";} citeste();
  }).catch(nimicNuRaspunde);
}
var ceas = null, citire = 0, eraOcupat = false;
function citeste(){
  var nr = ++citire;
  if(ceas){clearTimeout(ceas); ceas = null;}
  cerere("/api/bluetooth").then(function(s){
    if(nr !== citire){return;}
    if(!s.result){$("mesaj").textContent = s.message || ""; return;}
    $("mesaj").textContent = s.message || ""; $("cauta").disabled = s.ocupat;
    if(eraOcupat && !s.ocupat){reciteSunet();} eraOcupat = s.ocupat;
    $("lista").textContent = "";
    s.dispozitive.forEach(function(r){
      var p = document.createElement("p"), b = document.createElement("button"); b.type = "button";
      b.textContent = r.nume + " - " + (r.conectata ? "legătură Bluetooth activă" : r.asociata ? "asociată" : "nouă");
      b.disabled = s.ocupat; b.addEventListener("click", function(){comanda("asociaza", r.id);});
      p.appendChild(b); $("lista").appendChild(p);
    });
    ceas = setTimeout(citeste, s.ocupat ? 700 : 3000);
  }).catch(nimicNuRaspunde);
}
var ceasSunet = null, alegeSunet = false;
function citesteSunet(){
  if(ceasSunet){clearTimeout(ceasSunet); ceasSunet = null;}
  cerere("/api/bluetooth-sunet").then(function(s){
    if(!s.result || !s.poate){return;}
    $("sunet").hidden = false; $("mesajSunet").textContent = s.message || "";
    var sel = $("casca");
    if(!alegeSunet){
      sel.textContent = "";
      var nu = document.createElement("option"); nu.value = ""; nu.textContent = "Nu"; sel.appendChild(nu);
      var gasit = !s.adresa;
      s.dispozitive.forEach(function(r){
        var o = document.createElement("option"); o.value = r.id; o.textContent = r.nume; sel.appendChild(o);
        if(r.id === s.adresa){gasit = true;}
      });
      if(!gasit){var a = document.createElement("option"); a.value = s.adresa; a.textContent = s.nume || s.adresa; sel.appendChild(a);}
      sel.value = s.adresa || "";
    }
    sel.disabled = s.ocupat;
    if(document.activeElement !== $("intarziere")){$("intarziere").value = s.intarziere || 0;}
    ceasSunet = setTimeout(citesteSunet, s.ocupat ? 700 : 3000);
  }).catch(nimicNuRaspunde);
}
$("casca").addEventListener("focus", function(){alegeSunet = true;});
$("casca").addEventListener("blur", function(){alegeSunet = false;});
$("casca").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("adresa", this.value); alegeSunet = false;
  cerere("/api/bluetooth-sunet-comanda", "POST", q).then(function(d){
    if(!d.result){$("mesajSunet").textContent = d.message || "";} citesteSunet();
  }).catch(nimicNuRaspunde);
});
$("intarziere").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("actiune", "intarziere"); q.set("intarziere", this.value);
  cerere("/api/bluetooth-sunet-comanda", "POST", q).then(citesteSunet).catch(nimicNuRaspunde);
});
$("cauta").addEventListener("click", function(){comanda("cauta");});
comanda("citeste");
function reciteSunet(){
  cerere("/api/bluetooth-sunet-comanda", "POST", new URLSearchParams("actiune=citeste")).then(citesteSunet, citesteSunet);
}
reciteSunet();
</script></body></html>"""

TEXTE_PAGINA = {
	"html": (N_("Telecomandă Bluetooth"), N_("Pune telecomanda în modul de asociere, apoi apasă Caută."),
		N_("Caută"), N_("Repetarea tastelor"), N_("Asocierea tastelor"),
		N_("Sunetul receptorului în cască Bluetooth"), N_("Întârzierea sunetului în cască (ms)")),
	"js": (N_("legătură Bluetooth activă"), N_("asociată"), N_("nouă"), N_("Nu")),
}

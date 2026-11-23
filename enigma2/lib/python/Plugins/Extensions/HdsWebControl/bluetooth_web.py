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

	return {b"bluetooth": Stare(), b"bluetooth-comanda": Comanda()}, Pagina()


PAGINA = """<!DOCTYPE html><html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Telecomandă Bluetooth</title>
<style>__STIL_COMUN__ __STIL_PAGINI__</style></head><body><main>
<h1>Telecomandă Bluetooth</h1><p>Pune telecomanda în modul de asociere, apoi apasă Caută.</p>
<button type="button" id="cauta">Caută</button><p id="mesaj" role="status"></p><div id="lista"></div>
<p><a href="/dispozitive-intrare">Repetarea tastelor</a> <a href="/telecomenzi">Asocierea tastelor</a></p>
</main><script>__SCRIPT_COMUN__
function comanda(actiune, id){
  var q = new URLSearchParams(); q.set("actiune", actiune); if(id){q.set("id", id);}
  return cerere("/api/bluetooth-comanda", "POST", q).then(function(d){
    if(!d.result){$("mesaj").textContent = d.message || "";} citeste();
  }).catch(nimicNuRaspunde);
}
var ceas = null, citire = 0;
function citeste(){
  var nr = ++citire;
  if(ceas){clearTimeout(ceas); ceas = null;}
  cerere("/api/bluetooth").then(function(s){
    if(nr !== citire){return;}
    if(!s.result){$("mesaj").textContent = s.message || ""; return;}
    $("mesaj").textContent = s.message || ""; $("cauta").disabled = s.ocupat;
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
$("cauta").addEventListener("click", function(){comanda("cauta");});
comanda("citeste");
</script></body></html>"""

TEXTE_PAGINA = {
	"html": (N_("Telecomandă Bluetooth"), N_("Pune telecomanda în modul de asociere, apoi apasă Caută."),
		N_("Caută"), N_("Repetarea tastelor"), N_("Asocierea tastelor")),
	"js": (N_("legătură Bluetooth activă"), N_("asociată"), N_("nouă")),
}

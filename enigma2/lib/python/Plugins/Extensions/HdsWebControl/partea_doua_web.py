# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Aceeasi lucrare ca pe televizor. Poarta JSON comuna cere POST si CSRF.
def N_(text):
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _motor():
	from Components import HdsParteaDoua
	return HdsParteaDoua


def rute(baza, resource, P=None):
	P = P or _motor()
	class Stare(baza):
		def render_GET(self, request):
			return self._raspunde(request, dict(P.starePublica(), result=True))

	class Porneste(baza):
		schimbaCeva = True
		def render_POST(self, request):
			punct = (request.args.get(b"punct") or [b""])[0].decode("utf-8", "replace")
			d = P.starePublica()
			if d.get("montat"):
				punct = None
			elif not d.get("descris") or punct not in [x["punct"] for x in d.get("candidati", [])]:
				return self._raspunde(request, {"result": False, "message": _t("Alege un stick disponibil.")})
			ok = P.lucrare.porneste(punct)
			return self._raspunde(request, dict(P.starePublica(), result=ok,
				message=_t("Operatia a pornit.") if ok else _t("Alta operatie este in lucru sau interfata trebuie repornita.")))

	class Pagina(resource.Resource):
		isLeaf = True
		def render_GET(self, request):
			from .meniu_comun_web import pagina
			return pagina(request, pagina_text)
	return {b"partea-doua": Stare(), b"partea-doua-porneste": Porneste()}, Pagina()


def pagina_text(stil, configurare):
	from .meniu_comun_web import SCRIPT_COMUN, STIL_PAGINI
	from .traducere_pagini import traduce
	text = traduce(PAGINA, TEXTE_PAGINA)
	return text.replace("__STIL__", stil + STIL_PAGINI).replace("__SCRIPT__", SCRIPT_COMUN).replace("__CONFIG__", configurare)


PAGINA = """<!doctype html>
<html lang="ro"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Partea a doua pe stick</title><style>__STIL__</style></head><body><main>
<h1>Partea a doua pe stick</h1>
<section class="card"><p id="stare">Se citeste starea...</p><p id="limita"></p>
<label for="stick" id="eticheta">Stick USB</label><select id="stick"></select>
<p id="spatiu"></p><button id="porneste">Instaleaza / actualizeaza</button></section>
<p id="mesaj" role="status" aria-live="polite"></p></main>
<script>__SCRIPT__
var ultima = null;
function arata(d){
  ultima=d;
  $("stare").textContent=d.mesaj || (d.montat ? "Stick montat" : "Niciun stick legat");
  $("limita").textContent=d.limita || "";
  var select=$("stick"), ales=select.value;
  select.textContent="";
  (d.candidati || []).forEach(function(c){
    var o=document.createElement("option");o.value=c.punct;
    o.textContent=c.punct+" ("+c.liber_mib+" MiB liberi)";select.appendChild(o);
  });
  if(Array.from(select.options).some(function(o){return o.value===ales;})){select.value=ales;}
  select.hidden=!!d.legat || !d.descris;$("eticheta").hidden=select.hidden;
  $("spatiu").hidden=!!d.legat || !d.descris;$("porneste").hidden=!d.descris;
  $("spatiu").textContent="Se folosesc "+(d.marime_mib || 1024)+" MiB pe stick, fara stergerea fisierelor existente.";
  $("porneste").disabled=!!d.ocupat || !d.descris || (!d.montat && !(d.candidati || []).length);
  $("porneste").textContent=d.ocupat ? "Asteapta..." : (d.montat ? "Actualizeaza partea a doua" : "Instaleaza pe stick");
}
function citeste(){cerere("/api/partea-doua").then(arata).catch(nimicNuRaspunde);}
$("porneste").addEventListener("click",function(){
  if(!ultima || (!ultima.montat && !window.confirm("Folosesc spatiu pe acest stick pentru limbile suplimentare? Fisierele existente raman."))){return;}
  var q=new URLSearchParams();if(!ultima.montat){q.set("punct",$("stick").value);}
  $("porneste").disabled=true;
  cerere("/api/partea-doua-porneste","POST",q).then(function(d){mesaj(d.message,!d.result);citeste();}).catch(nimicNuRaspunde);
});
citeste();setInterval(citeste,3000);
</script></body></html>"""


TEXTE_PAGINA = {
	"html": (
		N_("Partea a doua pe stick"), N_("Se citeste starea..."), N_("Stick USB"),
		N_("Instaleaza / actualizeaza"),
	),
	"js": (
		N_("Stick montat"), N_("Niciun stick legat"), N_("MiB liberi"),
		N_("Se folosesc"), N_("MiB pe stick, fara stergerea fisierelor existente."),
		N_("Asteapta..."), N_("Actualizeaza partea a doua"), N_("Instaleaza pe stick"),
		N_("Folosesc spatiu pe acest stick pentru limbile suplimentare? Fisierele existente raman."),
	),
}

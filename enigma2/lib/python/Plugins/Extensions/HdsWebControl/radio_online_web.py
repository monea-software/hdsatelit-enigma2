# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Intrarea permanenta Radio online: confirmare, instalatorul comun si pagina pluginului.

GET citeste numai starea locala. Numai Da porneste verificarea feedului si instalarea,
prin acelasi singleton ca pe televizor. Pagina reala a pluginului este montata sub
/radio-online/lista/, pastrand originea si protocolul panoului, inclusiv HTTPS.
"""
import json


def _(text):
	from .meniu_comun_web import _t
	return _t(text)


def _D(D=None):
	if D is not None:
		return D
	from Components import HdsRadioOnline
	return HdsRadioOnline


def stare(D=None):
	D = _D(D)
	p = D.pregatire().stare()
	# Fisierele pot aparea inainte ca opkg sa termine configurarea pachetului.
	instalat = D.plugin_instalat() and p["faza"] == "gata"
	return {"result": True, "instalat": bool(instalat), "pregatire": p,
		"pagina": "/radio-online/lista/" if instalat else ""}


def instaleaza(arg, D=None, M=None):
	if M is None:
		from . import meniu_comun_web as M
	D = _D(D)
	actiune = "radio-online-instaleaza"
	pas = arg.get("pas", "")
	if pas == "renunta":
		M.uita(actiune)
		return {"result": True, "message": ""}
	if pas == "intreaba":
		return M.raspunsIntrebare(actiune, "", D.text_confirmare(), _("Da"))
	if not M.verifica(actiune, "", arg.get("cod", "")):
		return M.codGresit()
	D.pregatire().verifica(True)
	return stare(D)


def _plugin_web(sesiune):
	if sesiune is None:
		raise RuntimeError("sesiune indisponibila")
	from Plugins.Extensions.RadioOnline import web
	web.porneste(sesiune)
	return web._Radacina(panou_aici=True)


def rute(baza, resource, D=None, M=None, sesiune=None, plugin_web=None):
	if M is None:
		from . import meniu_comun_web as M

	def _eroare():
		return _("Radio online nu se poate deschide acum. Încearcă din nou.")

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(D))
			except Exception as e:
				print("[HdsWebControl] radio online: %s" % type(e).__name__)
				return self._eroare(request, _eroare(), 503)

	class InstaleazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = M.numaiBrowser(request)
			if refuz:
				return self._eroare(request, refuz, 403)
			try:
				arg = M.argumente(request, ("pas", "cod"), 40)
				return self._raspunde(request, instaleaza(arg, D, M))
			except Exception as e:
				print("[HdsWebControl] instalare radio online: %s" % type(e).__name__)
				return self._eroare(request, _eroare(), 503)

		def render_GET(self, request):
			return self._eroare(request, _("Instalarea se confirmă din pagina Radio online."), 405)

	class IndisponibilResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			request.setResponseCode(503)
			return M.pagina(request, lambda stil, config: pagina_text(stil, config, _eroare()))

	class ListaResource(resource.Resource):
		def getChild(self, name, request):
			# Pagina si API-urile pluginului isi verifica singure accesul. Poarta de aici
			# preceda inclusiv importul si pornirea pluginului nou instalat.
			from . import plugin as P
			if P._verificaAcces(request, False)[1] is not None:
				return IndisponibilResource()
			try:
				if not stare(D)["instalat"]:
					return PaginaResource()
				ses = sesiune() if sesiune is not None else M.sesiune()
				return (plugin_web or _plugin_web)(ses).getChildWithDefault(name, request)
			except Exception as e:
				print("[HdsWebControl] pagina radio online: %s" % type(e).__name__)
				return IndisponibilResource()

		def render_GET(self, request):
			request.setResponseCode(302)
			request.setHeader(b"location", b"/radio-online/lista/")
			return b""

	class PaginaResource(resource.Resource):
		def getChild(self, name, request):
			if name == b"lista":
				return ListaResource()
			if name == b"":
				return self
			return resource.Resource.getChild(self, name, request)

		def render_GET(self, request):
			return M.pagina(request, pagina_text)

	return {b"radio-online": StareResource(), b"radio-online-instaleaza": InstaleazaResource()}, {b"radio-online": PaginaResource()}


def texte():
	return {"neasteptat": _("Receptorul a răspuns neașteptat."),
		"nuRaspunde": _("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"citeste": _("Se citește starea..."), "incearca": _("Încearcă din nou"),
		"deschide": _("Deschide Radio online"), "deschidere": _("Se deschide Radio online...")}


def pagina_text(stil, config_pagina, eroare=""):
	from html import escape
	from .meniu_comun_web import STIL_PAGINI
	text = PAGINA.replace("__STIL_COMUN__", stil).replace("__STIL_PAGINI__", STIL_PAGINI)
	for cheie, valoare in {"__TITLU__": _("Radio online"), "__DA__": _("Da"), "__NU__": _("Nu"),
			"__INCEARCA__": _("Deschide Radio online"), "__EROARE__": eroare}.items():
		text = text.replace(cheie, escape(valoare, quote=True))
	text = text.replace("__CONFIG__", config_pagina)
	text = text.replace("__TEXTE__", json.dumps(texte(), ensure_ascii=True).replace("</", "<\\/"))
	return text.replace("__BLOCAT__", "true" if eroare else "false")


PAGINA = """<!doctype html>
<html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLU__</title><style>__STIL_COMUN__ __STIL_PAGINI__
progress{width:100%;height:18px} .butoane a{align-self:center}
</style></head><body><main><h1>__TITLU__</h1>
<section class="card"><p id="stare" role="status" aria-live="polite">__EROARE__</p><p id="pas" class="nota"></p>
<progress id="progres" hidden></progress>
<div class="butoane"><button id="incearca" type="button" hidden>__INCEARCA__</button></div></section>
<section id="confirmare" class="card" hidden><p id="intrebare"></p><div class="butoane">
<button id="da" type="button" class="principal">__DA__</button><button id="nu" type="button">__NU__</button></div></section>
<p id="mesaj" class="mesaj" role="status" aria-live="polite"></p>
</main><script>
"use strict";
var CFG=__CONFIG__, T=__TEXTE__, blocat=__BLOCAT__;
var cod="", ocupat=false, citire=false, intrebat=false, pleaca=false;
function $(id){return document.getElementById(id)}
function cerere(cale,metoda,date){
 var opt={method:metoda||"GET",cache:"no-store",credentials:"same-origin",headers:{}};
 if(CFG.csrf)opt.headers["X-HDS-CSRF"]=CFG.csrf;
 if(date){opt.headers["Content-Type"]="application/x-www-form-urlencoded";opt.body=date.toString()}
 if(CFG.jeton)cale+=(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton);
 return fetch(cale,opt).then(function(r){
  if(r.status===401&&!CFG.jeton){location.replace("/");throw new Error()}
  return r.json().catch(function(){return {result:false,message:T.neasteptat}})
 })
}
function mesaj(t){$("mesaj").textContent=t||""}
function butoane(da){$("da").disabled=!da;$("nu").disabled=!da;$("incearca").disabled=!da}
function intreaba(){
 if(ocupat||pleaca)return;
 intrebat=true;ocupat=true;butoane(false);mesaj("");
 var q=new URLSearchParams();q.set("pas","intreaba");
 return cerere("/api/radio-online-instaleaza","POST",q).then(function(d){
  if(!d.result||!d.confirmare){mesaj(d.message||T.neasteptat);$("incearca").hidden=false;return}
  cod=d.confirmare.cod;$("intrebare").textContent=d.confirmare.intrebare;$("confirmare").hidden=false;$("incearca").hidden=true;$("nu").focus()
 }).catch(function(){mesaj(T.nuRaspunde);$("incearca").hidden=false}).finally(function(){ocupat=false;butoane(true)})
}
function confirma(){
 if(ocupat||!cod)return;
 var q=new URLSearchParams();q.set("cod",cod);cod="";ocupat=true;butoane(false);$("confirmare").hidden=true;
 return cerere("/api/radio-online-instaleaza","POST",q).then(function(d){
  if(!d.result){mesaj(d.message||T.neasteptat);$("incearca").hidden=false;return}
  return citeste()
 }).catch(function(){mesaj(T.nuRaspunde);$("incearca").hidden=false}).finally(function(){ocupat=false;butoane(true)})
}
function renunta(){
 if(ocupat)return;
 cod="";intrebat=true;$("confirmare").hidden=true;$("incearca").hidden=false;mesaj("");
 var q=new URLSearchParams();q.set("pas","renunta");
 return cerere("/api/radio-online-instaleaza","POST",q).catch(function(){})
}
function citeste(){
 if(citire||pleaca||blocat)return Promise.resolve();citire=true;
 return cerere("/api/radio-online").then(function(d){
  if(!d.result){mesaj(d.message||T.neasteptat);$("incearca").hidden=false;return}
  var p=d.pregatire;
  if(d.instalat){pleaca=true;$("confirmare").hidden=true;$("stare").textContent=T.deschidere;location.replace("/radio-online/lista/");return}
  $("stare").textContent=p.text||T.citeste;$("pas").textContent=p.pas||"";
  var lucru=["citesc","lista","instalare"].indexOf(p.faza)>=0;
  $("progres").hidden=!lucru;$("progres").max=100;
  if(typeof p.progres==="number")$("progres").value=p.progres;else $("progres").removeAttribute("value");
  if(lucru){$("confirmare").hidden=true;cod="";intrebat=true;$("incearca").hidden=true}
  else if(p.faza==="eroare"||p.faza==="lipsa"){$("incearca").textContent=T.incearca;$("incearca").hidden=false}
  else if(!intrebat&&!ocupat){intreaba()}
 }).catch(function(){mesaj(T.nuRaspunde);$("incearca").hidden=false}).finally(function(){citire=false})
}
$("da").addEventListener("click",confirma);$("nu").addEventListener("click",renunta);
$("incearca").addEventListener("click",intreaba);
if(!blocat){citeste();setInterval(function(){if(!ocupat&&!document.hidden)citeste()},700)}
</script></body></html>
"""

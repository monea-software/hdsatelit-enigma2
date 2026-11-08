# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
#
# Aceeasi galerie si aceleasi comenzi ca pe televizor.
# Cererile lente folosesc firul si ceasul deja folosite la ecrane.

import base64

from .ecran_pornire_web import porneste_pe_fir


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _modul():
	from Components import HdsGalerieSigle
	return HdsGalerieSigle


def rezolutie(modul):
	try:
		from enigma import getDesktop
		d = getDesktop(0).size()
		return modul.resolution(d.width(), d.height())
	except Exception:
		return modul.resolution()


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace")


def _corp(date):
	date = dict(date)
	date["result"] = bool(date.get("ok"))
	return date


def date(modul=None, rez=None):
	M = modul or _modul()
	corp = _corp(M.catalog())
	corp["resolution"] = rez or rezolutie(M)
	corp["available_roles"] = M.status().get("available_roles", ["backdrop", "radio"])
	return corp


def poza(ident, modul=None):
	"""Poza verificata trece prin receptor, fara adrese alese de client."""
	M = modul or _modul()
	r = M.preview(ident)
	if not r.get("ok"):
		return _corp(r), 404
	with open(r["path"], "rb") as f:
		octeti = f.read(2 * 1024 * 1024 + 1)
	if len(octeti) > 2 * 1024 * 1024:
		return {"result": False, "message": _t("Previzualizarea este prea mare.")}, 400
	if octeti.startswith(b"\x89PNG\r\n\x1a\n"):
		tip = "image/png"
	elif octeti.startswith(b"\xff\xd8\xff"):
		tip = "image/jpeg"
	else:
		return {"result": False, "message": _t("Previzualizarea nu poate fi citită.")}, 400
	return {"result": True, "mime": tip,
		"data": base64.b64encode(octeti).decode("ascii")}


class _Stare(object):
	punere = [False]


def rute(baza, resource, modul=None, fabrica_ceas=None):
	def m():
		return modul or _modul()

	class ListaResource(baza):
		def render_GET(self, request):
			M = m()
			rez = rezolutie(M)
			return porneste_pe_fir(request, lambda: date(M, rez), [False], 60, fabrica_ceas)

	class PozaResource(baza):
		def render_GET(self, request):
			ident, M = _arg(request, b"id"), m()
			return porneste_pe_fir(request, lambda: poza(ident, M), [False], 60, fabrica_ceas)

	class PuneResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			if _Stare.punere[0]:
				return self._eroare(request, _t("Se pune deja o siglă. Așteaptă câteva clipe."), 503)
			ident = _arg(request, b"id")
			rol = _arg(request, b"rol", b"backdrop")
			M, rez = m(), rezolutie(m())
			return porneste_pe_fir(request, lambda: _corp(M.install(ident, rol, rez)),
				_Stare.punere, 180, fabrica_ceas)

	class InapoiResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			if _Stare.punere[0]:
				return self._eroare(request, _t("Se pune deja o siglă. Așteaptă câteva clipe."), 503)
			rol, M = _arg(request, b"rol", b"backdrop"), m()
			return porneste_pe_fir(request, lambda: _corp(M.restore(rol)),
				_Stare.punere, 180, fabrica_ceas)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"sigle-pornire": ListaResource(), b"sigle-poza": PozaResource(),
		b"sigle-pune": PuneResource(), b"sigle-inapoi": InapoiResource()}, PaginaResource()


def pagina(request):
	from .meniu_comun_web import pagina as pagina_comuna
	return pagina_comuna(request, pagina_text)


def pagina_text(stil, config):
	from .traducere_pagini import traduce
	return traduce(PAGINA, TEXTE_PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sigle de pornire</title>
<style>__STIL_COMUN__
#galerieSigle{width:100%;max-width:1100px;min-width:0;box-sizing:border-box;
 margin:0 auto;padding-bottom:24px;}
#galerieSigle *{box-sizing:border-box;min-width:0;}
#galerieSigle p,#galerieSigle button,#galerieSigle .stare{
 max-width:100%;white-space:normal;overflow-wrap:anywhere;}
h1{font-size:1.6rem;margin:0 0 8px;}
.introducere{color:var(--text-slab);margin:0 0 24px;line-height:1.5;max-width:760px;}
.locuri{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px;}
.locuri button,.secundar{font:inherit;color:var(--text);background:var(--panou);
 border:1px solid var(--bordura);border-radius:8px;padding:10px 16px;min-height:44px;cursor:pointer;}
.locuri button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff;}
.gs-unelte{display:flex;gap:12px;justify-content:space-between;align-items:center;flex-wrap:wrap;width:100%;}
.mic{color:var(--text-slab);font-size:.87rem;line-height:1.5;margin:6px 0;}
.stare{padding:14px 16px;border:1px solid var(--bordura);border-radius:8px;
 background:var(--panou);margin:16px 0;line-height:1.5;min-height:24px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
.stare.bun{color:#9ce3b4;}
.grila{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:18px;margin:20px 0 24px;}
.sigla{display:block;width:100%;padding:0;border:1px solid var(--bordura);border-radius:10px;
 overflow:hidden;background:var(--panou);color:var(--text);font:inherit;text-align:left;cursor:pointer;}
.sigla:hover{border-color:var(--accent);}
.sigla:focus-visible,.secundar:focus-visible,.locuri button:focus-visible{
 outline:3px solid var(--accent);outline-offset:3px;}
.sigla.aleasa{border:2px solid var(--accent);}
.poza{display:flex;align-items:center;justify-content:center;aspect-ratio:16/9;
 background:#080c16;color:#bfc9dd;font-size:.85rem;text-align:center;}
.poza img{display:block;width:100%;height:100%;object-fit:contain;}
.titlu{display:block;font-weight:600;font-size:1rem;margin:13px 15px 4px;overflow-wrap:anywhere;}
.autor{display:block;color:var(--text-slab);font-size:.85rem;margin:0 15px 15px;overflow-wrap:anywhere;}
.gol{color:var(--text-slab);padding:28px 0;line-height:1.6;}
.inapoi{border-top:1px solid var(--bordura);padding-top:22px;}
button[disabled]{opacity:.55;cursor:wait;}
[hidden]{display:none!important;}
@media(max-width:559px){.grila{grid-template-columns:minmax(0,1fr);gap:16px;}
 .locuri button{flex:1 1 135px;}.gs-unelte{align-items:flex-start;}}
</style>
</head>
<body>
<main id="galerieSigle">
<h1>Sigle de pornire</h1>
<p class="introducere">Sigle create de comunitatea HD Satelit.
Alege unde apare, apoi apasă poza ca să o pui pe receptor.</p>
<div class="locuri" role="group" aria-label="Unde apare sigla">
 <button type="button" data-rol="backdrop" aria-pressed="true">Imaginea de pornire</button>
 <button type="button" data-rol="radio" aria-pressed="false">Radio</button>
 <button type="button" data-rol="bootlogo" aria-pressed="false" hidden>Sigla timpurie a receptorului</button>
</div>
<div class="gs-unelte">
 <p class="mic" id="rezolutie">Rezoluția este aleasă automat pentru receptor.</p>
 <button type="button" class="secundar" id="reincarca">Reîncarcă galeria</button>
</div>
<div class="stare" id="stare" role="status" aria-live="polite">Se încarcă galeria de pe internet...</div>
<p class="gol" id="gol" hidden>Nu sunt încă sigle pentru locul ales.
Revino mai târziu sau pune înapoi sigla HD Satelit.</p>
<div class="grila" id="grila" aria-label="Siglele comunității"></div>
<div class="inapoi">
 <button type="button" class="secundar" id="inapoi">Pune înapoi sigla HD Satelit</button>
 <p class="mic">Pentru locul ales mai sus. Funcționează și fără internet.</p>
</div>
</main>
<script>
var CFG=__CONFIG__;
var DATE=null, ROL="backdrop", OCUPAT=false, GENERATIE=0, ALEASA={};
function adresa(cale){
 return CFG.jeton?cale+(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton):cale;
}
function mesaj(text,clasa){
 var s=document.getElementById("stare");s.textContent=text;s.className="stare "+(clasa||"");
}
function ocupat(da){
 OCUPAT=da;document.getElementById("grila").setAttribute("aria-busy",da?"true":"false");
 document.querySelectorAll("button").forEach(function(b){b.disabled=da;});
}
async function cere(cale,post){
 var opt={credentials:"same-origin",cache:"no-store",headers:{}};
 if(post){opt.method="POST";if(CFG.csrf){opt.headers["X-HDS-CSRF"]=CFG.csrf;}}
 var control=new AbortController();opt.signal=control.signal;
 var ceas=setTimeout(function(){control.abort();},185000);
 try{
  var r=await fetch(adresa(cale),opt),d=await r.json();
  if(!r.ok||!d.result){throw new Error(d.message||"Nu am putut termina. Încearcă din nou.");}
  return d;
 }finally{clearTimeout(ceas);}
}
function eroare(e){
 return e&&e.message&&e.name!=="TypeError"&&e.name!=="AbortError"?e.message:
  "Receptorul nu răspunde. Verifică legătura și încearcă din nou.";
}
async function reincarca(){
 if(OCUPAT){return;}ocupat(true);mesaj("Se încarcă galeria de pe internet...");
 try{DATE=await cere("/api/sigle-pornire");
  var roluri=DATE.available_roles||["backdrop","radio"];
  if(roluri.indexOf(ROL)<0){ROL=roluri[0]||"backdrop";}
  document.querySelectorAll("[data-rol]").forEach(function(b){
   b.hidden=roluri.indexOf(b.dataset.rol)<0;b.setAttribute("aria-pressed",b.dataset.rol===ROL?"true":"false");
  });deseneaza();
  mesaj(DATE.message||"Apasă poza pentru a pune sigla. Se vede la următoarea pornire.");
 }catch(e){mesaj(eroare(e),"rau");}finally{ocupat(false);}
}
function deseneaza(){
 var g=document.getElementById("grila");g.replaceChildren();
 var generatie=++GENERATIE, lista=(DATE&&DATE.items||[]).filter(function(i){
  return i.variants&&i.variants[DATE.resolution]&&i.variants[DATE.resolution][ROL];
 });
 document.getElementById("gol").hidden=lista.length!==0;
 document.getElementById("rezolutie").textContent=DATE?"Rezoluție aleasă automat: "+DATE.resolution+".":"";
 var coada=[];
 lista.forEach(function(i){
  var b=document.createElement("button");b.type="button";b.className="sigla";
  b.disabled=OCUPAT;b.setAttribute("aria-label",i.title+" - Pune sigla");
  if(ALEASA[ROL]===i.id){b.classList.add("aleasa");}
  var p=document.createElement("span");p.className="poza";p.textContent="Se încarcă previzualizarea...";
  var t=document.createElement("span");t.className="titlu";t.textContent=i.title;
  var a=document.createElement("span");a.className="autor";a.textContent="Autor: "+i.author;
  b.append(p,t,a);b.addEventListener("click",function(){pune(i);});g.appendChild(b);
  coada.push({item:i,element:p});
 });
 async function urmatoarea(){
  while(coada.length&&generatie===GENERATIE){
   var v=coada.shift();
   try{
    var d=await cere("/api/sigle-poza?id="+encodeURIComponent(v.item.id));
    if(generatie!==GENERATIE){return;}
    var img=document.createElement("img");img.alt=v.item.title;
    img.src="data:"+d.mime+";base64,"+d.data;
    img.onerror=function(){this.replaceWith(document.createTextNode("Previzualizarea nu poate fi citită."));};
    v.element.replaceChildren(img);
   }catch(e){v.element.textContent="Previzualizarea nu este disponibilă.";}
  }
 }
 urmatoarea();urmatoarea();
}
async function pune(item){
 if(OCUPAT){return;}ocupat(true);var rol=ROL;
 mesaj("Se descarcă și se pune sigla. Așteaptă câteva clipe...");
 try{
  var d=await cere("/api/sigle-pune?id="+encodeURIComponent(item.id)+"&rol="+encodeURIComponent(rol),true);
  ALEASA[rol]=item.id;deseneaza();mesaj(d.message||"Sigla a fost pusă. Se vede la următoarea pornire.","bun");
 }catch(e){mesaj(eroare(e),"rau");}finally{ocupat(false);}
}
async function inapoi(){
 if(OCUPAT){return;}ocupat(true);mesaj("Se pune înapoi sigla HD Satelit...");
 try{
  var d=await cere("/api/sigle-inapoi?rol="+encodeURIComponent(ROL),true);
  delete ALEASA[ROL];if(DATE){deseneaza();}mesaj(d.message||"Sigla HD Satelit a fost pusă înapoi.","bun");
 }catch(e){mesaj(eroare(e),"rau");}finally{ocupat(false);}
}
document.querySelectorAll("[data-rol]").forEach(function(b){b.addEventListener("click",function(){
 if(OCUPAT){return;}ROL=b.dataset.rol;
 document.querySelectorAll("[data-rol]").forEach(function(t){
  t.setAttribute("aria-pressed",t===b?"true":"false");
 });
 if(DATE){deseneaza();}mesaj("Apasă poza pentru a pune sigla. Se vede la următoarea pornire.");
});});
document.getElementById("reincarca").addEventListener("click",reincarca);
document.getElementById("inapoi").addEventListener("click",inapoi);
reincarca();
</script>
</body>
</html>"""


def N_(text):
	return text


TEXTE_PAGINA = {"html": (
	N_("Sigle de pornire"),
	N_("Sigle create de comunitatea HD Satelit. Alege unde apare, apoi apasă poza ca să o pui pe receptor."),
	N_("Unde apare sigla"), N_("Imaginea de pornire"), N_("Sigla timpurie a receptorului"), N_("Radio"),
	N_("Rezoluția este aleasă automat pentru receptor."), N_("Reîncarcă galeria"),
	N_("Se încarcă galeria de pe internet..."),
	N_("Nu sunt încă sigle pentru locul ales. Revino mai târziu sau pune înapoi sigla HD Satelit."),
	N_("Siglele comunității"), N_("Pune înapoi sigla HD Satelit"),
	N_("Pentru locul ales mai sus. Funcționează și fără internet."),
	), "js": (
	N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Apasă poza pentru a pune sigla. Se vede la următoarea pornire."),
	N_("Rezoluție aleasă automat: "), N_(" - Pune sigla"), N_("Se încarcă previzualizarea..."),
	N_("Autor: "), N_("Previzualizarea nu poate fi citită."),
	N_("Previzualizarea nu este disponibilă."),
	N_("Se descarcă și se pune sigla. Așteaptă câteva clipe..."),
	N_("Sigla a fost pusă. Se vede la următoarea pornire."),
	N_("Se pune înapoi sigla HD Satelit..."), N_("Sigla HD Satelit a fost pusă înapoi."),
	N_("Se încarcă galeria de pe internet..."),
)}

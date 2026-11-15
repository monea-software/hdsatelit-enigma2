# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pagina web "Sport azi", http://hdsatelit.local/sport-azi: perechea ecranului Screens/HdsSportAzi.py (regula din
# 24.09.2026). Aceeasi lista (meciurile, cursele si galele de azi din ghid, cu ora si canalul), acelasi filtru "numai
# in direct"; butonul "Pe televizor" la ce a inceput. Datele: Components/HdsSportAzi.py, fara internet.
#
#   GET  /api/sport-azi            randurile de sport de acum pana la sfarsitul zilei
#   POST /api/sport-azi-zap?ref=   canalul pe televizor (numai un canal din listele omului)


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _S():
	from Components import HdsSportAzi
	return HdsSportAzi


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace").strip()


def date(randuri, S=None):
	"""Randurile pentru pagina: ora scrisa, fara textul lung."""
	S = S or _S()
	return {"result": True, "randuri": [{"ref": r["ref"], "ora": S.ora(r["inceput"]), "sfarsit": S.ora(r["inceput"] + r["durata"]),
		"titlu": r["titlu"], "canal": r["canal"], "acum": r["acum"], "direct": r["direct"], "alte": r["alte"][:6]}
		for r in randuri]}


def rute(baza, resource):
	class DateResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, date(_S().sportAzi()))
			except Exception as e:
				print("[HdsWebControl] sport-azi: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class ZapResource(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Se trimite cu POST."), 405)

		def render_POST(self, request):
			try:
				ref = _arg(request, b"ref")
				if ref not in [r for r, n in _S().canaleTv()]:
					return self._eroare(request, _t("Canalul nu e în listele tale."), 400)
				from enigma import eServiceReference
				from Screens.InfoBar import InfoBar
				InfoBar.instance.session.nav.playService(eServiceReference(ref))
				return self._raspunde(request, {"result": True})
			except Exception as e:
				print("[HdsWebControl] sport-azi: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"sport-azi": DateResource(), b"sport-azi-zap": ZapResource()}, PaginaResource()


def pagina(request):
	from .meniu_comun_web import pagina as pagina_comuna
	return pagina_comuna(request, pagina_text)


def pagina_text(stil, config):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sport azi</title>
<style>__STIL_COMUN__
#sport{width:100%;max-width:1100px;margin:0 auto;padding-bottom:24px;box-sizing:border-box;}
#sport *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 6px;}
.intro{color:var(--text-slab);margin:0 0 14px;line-height:1.5;}
.bara{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px;}
button{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
 padding:10px 16px;min-height:44px;cursor:pointer;}
button.ales{background:var(--accent);border-color:var(--accent);color:#fff;}
button:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
.stare{padding:10px 14px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:0 0 14px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px;}
li{display:grid;grid-template-columns:90px 1fr auto;gap:12px;align-items:center;background:var(--panou);border:1px solid var(--bordura);
 border-radius:10px;padding:10px 14px;}
li .ora{font-weight:700;font-size:1.1rem;}
li .ora.acum{color:#3ddc84;}
li .titlu{font-size:1.05rem;}
li .canal{color:var(--text-slab);font-size:.92rem;}
.direct{background:#a8201a;color:#fff;border-radius:6px;padding:1px 8px;font-size:.8rem;margin-left:6px;}
@media (max-width:640px){li{grid-template-columns:70px 1fr;}li button{grid-column:1 / -1;}}
[hidden]{display:none!important;}
</style>
</head>
<body>
<main id="sport">
<h1>Sport azi</h1>
<p class="intro">Meciurile, cursele și galele de azi din ghidul canalelor tale, cu ora și canalul.</p>
<div class="bara"><button type="button" id="toate" class="ales">Toate</button><button type="button" id="direct">Numai în direct</button></div>
<div class="stare" id="stare" role="status" aria-live="polite" hidden></div>
<ol id="lista"></ol>
</main>
<script>
var CFG=__CONFIG__;
var R=[], DIRECT=false;
function adresa(cale){return CFG.jeton?cale+(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton):cale;}
function el(id){return document.getElementById(id);}
function mesaj(t,rau){var s=el("stare");s.hidden=!t;s.textContent=t||"";s.className="stare"+(rau?" rau":"");}
async function cere(cale,post){
 var opt={credentials:"same-origin",cache:"no-store",headers:{}};
 if(post){opt.method="POST";if(CFG.csrf){opt.headers["X-HDS-CSRF"]=CFG.csrf;}}
 var r=await fetch(adresa(cale),opt),d;
 try{d=await r.json();}catch(e){throw new Error("Receptorul a răspuns neașteptat.");}
 if(!r.ok||!d.result){throw new Error(d.message||"Nu am putut termina. Încearcă din nou.");}
 return d;
}
function eroare(e){return e&&e.message&&e.name!=="TypeError"?e.message:"Receptorul nu răspunde. Verifică legătura și încearcă din nou.";}
function deseneaza(){
 var l=el("lista");l.textContent="";
 el("toate").className=DIRECT?"":"ales";el("direct").className=DIRECT?"ales":"";
 var arata=R.filter(function(r){return r.direct||!DIRECT;});
 mesaj(arata.length?"":"Ghidul nu are sport azi pe canalele din listele tale.",false);
 arata.forEach(function(r){
  var li=document.createElement("li");
  var o=document.createElement("div");o.className="ora"+(r.acum?" acum":"");o.textContent=r.acum?"ACUM":r.ora;
  var m=document.createElement("div");
  var t=document.createElement("div");t.className="titlu";t.textContent=r.titlu;
  if(r.direct){var d=document.createElement("span");d.className="direct";d.textContent="în direct";t.appendChild(d);}
  var c=document.createElement("div");c.className="canal";c.textContent=r.ora+" - "+r.sfarsit+"  ·  "+r.canal+(r.alte.length?"  ·  "+"Și pe: "+r.alte.join(", "):"");
  m.appendChild(t);m.appendChild(c);li.appendChild(o);li.appendChild(m);
  if(r.acum){var b=document.createElement("button");b.type="button";b.textContent="Pe televizor";
   b.addEventListener("click",async function(){try{await cere("/api/sport-azi-zap?ref="+encodeURIComponent(r.ref),true);mesaj("Canalul e pe televizor.",false);}catch(e){mesaj(eroare(e),true);}});
   li.appendChild(b);}
  l.appendChild(li);
 });
}
async function citeste(){try{R=(await cere("/api/sport-azi")).randuri;deseneaza();}catch(e){mesaj(eroare(e),true);}}
el("toate").addEventListener("click",function(){DIRECT=false;deseneaza();});
el("direct").addEventListener("click",function(){DIRECT=true;deseneaza();});
citeste();
setInterval(citeste,120000);
</script>
</body>
</html>"""


def N_(text):
	return text


TEXTE_PAGINA = {"html": (
	N_("Sport azi"),
	N_("Meciurile, cursele și galele de azi din ghidul canalelor tale, cu ora și canalul."),
	N_("Toate"), N_("Numai în direct"),
	), "js": (
	N_("Receptorul a răspuns neașteptat."), N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Ghidul nu are sport azi pe canalele din listele tale."), N_("ACUM"), N_("în direct"), N_("Și pe: "),
	N_("Pe televizor"), N_("Canalul e pe televizor."),
)}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

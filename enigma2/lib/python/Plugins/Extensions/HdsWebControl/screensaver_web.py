# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# screensaver_web.py: „Screensaver” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Screens/HdsScreensaver.py, HdsScreensaverAlegere). Aceleasi date si aceleasi comenzi, din Components/HdsScreensavere.py.
# Pagina: cartele cu poza mica a fiecarui screensaver, numele si descrierea; apasarea cartelei il alege pe loc (fara
# „Salveaza”), „Probeaza pe televizor” il deschide pe televizor (prima tasta il inchide), iar „Porneste dupa” schimba
# timpul mecanismului (Screens/ScreenSaver.py, cand exista setarea lui).
#
# Rute (prin poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST + CSRF):
#   GET  /api/screensaver                    lista, cel ales, timpul de pornire (valoarea si alegerile)
#   GET  /api/screensaver-poza?id=..         poza mica (PNG), base64
#   POST /api/screensaver-alege?id=..        il alege
#   POST /api/screensaver-proba?id=..        il deschide pe televizor
#   POST /api/screensaver-dupa?valoare=..    timpul de pornire
#   GET  /screensaver                        pagina
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau furnizori falsi.

import base64


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _modul():
	from Components import HdsScreensavere
	return HdsScreensavere


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace")


def _timp():
	try:
		from Screens.HdsScreensaver import _configTimp
		return _configTimp()
	except Exception:
		return None


def _alegeri(c):
	"""[(cheie, text)] din alegerile unei setari ConfigSelection (perechi sau simple siruri)."""
	rez = []
	for x in getattr(getattr(c, "choices", None), "choices", None) or []:
		k, v = x if isinstance(x, (tuple, list)) else (x, x)
		rez.append((k, v))
	return rez


def date(modul=None, timp=None):
	M = modul or _modul()
	c = timp if timp is not None else _timp()
	corp = {"result": True, "ales": M.ales(), "lista": [
		{"id": i, "nume": M.nume(i), "descriere": M.descriere(i),
		"poza": bool(M.previzualizare(M.automat() if i == "automat" else i))} for i in M.IDURI]}
	if c is not None and _alegeri(c):
		corp["dupa"] = {"valoare": str(c.value), "alegeri": [[str(k), str(v)] for k, v in _alegeri(c)]}
	return corp


def poza(ident, modul=None):
	M = modul or _modul()
	if ident not in M.IDURI:
		return {"result": False, "message": _t("Nu există acest screensaver.")}, 404
	cale = M.previzualizare(M.automat() if ident == "automat" else ident)
	if not cale:
		return {"result": False, "message": _t("Previzualizarea nu este disponibilă.")}, 404
	with open(cale, "rb") as f:
		octeti = f.read(1024 * 1024 + 1)
	if len(octeti) > 1024 * 1024 or not octeti.startswith(b"\x89PNG\r\n\x1a\n"):
		return {"result": False, "message": _t("Previzualizarea nu poate fi citită.")}, 400
	return {"result": True, "mime": "image/png", "data": base64.b64encode(octeti).decode("ascii")}


def alege(ident, modul=None):
	M = modul or _modul()
	if not M.alege(ident):
		return {"result": False, "message": _t("Nu există acest screensaver.")}, 400
	return {"result": True, "ales": ident, "message": _t("Ales: %s") % M.nume(ident)}


def proba(ident, sesiune, modul=None, deschide=None):
	M = modul or _modul()
	if ident not in M.IDURI:
		return {"result": False, "message": _t("Nu există acest screensaver.")}, 400
	if sesiune is None:
		return {"result": False, "message": _t("Televizorul nu e gata. Încearcă din nou peste câteva clipe.")}, 503
	if deschide is None:
		from Screens.HdsScreensaver import deschide
	deschide(sesiune, ident)
	return {"result": True, "message": _t("Se vede pe televizor. Orice tastă de pe telecomandă îl închide.")}


def dupa(valoare, timp=None):
	c = timp if timp is not None else _timp()
	if c is None or not _alegeri(c):
		return {"result": False, "message": _t("Timpul de pornire nu se poate schimba pe acest receptor.")}, 400
	if valoare not in [str(k) for k, _v in _alegeri(c)]:
		return {"result": False, "message": _t("Valoare necunoscută.")}, 400
	for k, _v in _alegeri(c):
		if str(k) == valoare:
			c.value = k
	c.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return {"result": True, "message": _t("Pornește după: %s") % c.getText()}


def rute(baza, resource, modul=None, sesiune=None):
	def s():
		if sesiune is not None:
			return sesiune
		try:
			from . import plugin
			return plugin._sesiune
		except Exception:
			return None

	def raspunde(self, request, rez):
		corp, cod = (rez if isinstance(rez, tuple) else (rez, 200))
		return self._raspunde(request, corp, cod)

	class ListaResource(baza):
		def render_GET(self, request):
			return raspunde(self, request, date(modul))

	class PozaResource(baza):
		def render_GET(self, request):
			return raspunde(self, request, poza(_arg(request, b"id"), modul))

	class AlegeResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return raspunde(self, request, alege(_arg(request, b"id"), modul))

	class ProbaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return raspunde(self, request, proba(_arg(request, b"id"), s(), modul))

	class DupaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return raspunde(self, request, dupa(_arg(request, b"valoare")))

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"screensaver": ListaResource(), b"screensaver-poza": PozaResource(), b"screensaver-alege": AlegeResource(),
		b"screensaver-proba": ProbaResource(), b"screensaver-dupa": DupaResource()}, PaginaResource()


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
<title>Screensaver</title>
<style>__STIL_COMUN__
#ssv{width:100%;max-width:1100px;min-width:0;box-sizing:border-box;margin:0 auto;padding-bottom:24px;}
#ssv *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 8px;}
.introducere{color:var(--text-slab);margin:0 0 20px;line-height:1.5;max-width:760px;}
.unelte{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:0 0 8px;}
.unelte select,.secundar{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);
 border-radius:8px;padding:10px 14px;min-height:44px;}
.secundar{cursor:pointer;}
.stare{padding:14px 16px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:16px 0;
 line-height:1.5;min-height:24px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
.stare.bun{color:#9ce3b4;}
.grila{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:18px;margin:20px 0 24px;}
.cartela{border:1px solid var(--bordura);border-radius:10px;overflow:hidden;background:var(--panou);display:flex;
 flex-direction:column;}
.cartela.aleasa{border:2px solid var(--accent);}
.cartela button.alege{display:block;width:100%;padding:0;border:0;background:none;color:var(--text);font:inherit;
 text-align:left;cursor:pointer;}
.cartela button:focus-visible,.secundar:focus-visible{outline:3px solid var(--accent);outline-offset:3px;}
.poza{display:flex;align-items:center;justify-content:center;aspect-ratio:16/9;background:#080c16;color:#bfc9dd;
 font-size:.85rem;text-align:center;}
.poza img{display:block;width:100%;height:100%;object-fit:cover;}
.titlu{display:flex;gap:8px;align-items:center;font-weight:600;font-size:1rem;margin:12px 14px 4px;}
.eticheta{font-size:.75rem;font-weight:700;background:var(--accent);color:#fff;border-radius:6px;padding:2px 8px;}
.descriere{display:block;color:var(--text-slab);font-size:.87rem;line-height:1.45;margin:0 14px 12px;}
.cartela .secundar{margin:auto 14px 14px;}
button[disabled]{opacity:.55;cursor:wait;}
[hidden]{display:none!important;}
@media(max-width:559px){.grila{grid-template-columns:minmax(0,1fr);}}
</style>
</head>
<body>
<main id="ssv">
<h1>Screensaver</h1>
<p class="introducere">Ce se vede pe televizor când nu atingi telecomanda. Apasă o cartelă ca să o alegi.
Totul se mișcă încet pe ecran, ca televizorul să nu rămână cu aceeași imagine.</p>
<div class="unelte" id="randDupa" hidden>
 <label for="dupa">Pornește după</label>
 <select id="dupa"></select>
</div>
<div class="stare" id="stare" role="status" aria-live="polite">Se încarcă...</div>
<div class="grila" id="grila" aria-label="Screensaverele"></div>
</main>
<script>
var CFG=__CONFIG__;
var DATE=null, OCUPAT=false;
function adresa(cale){
 return CFG.jeton?cale+(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton):cale;
}
function mesaj(text,clasa){
 var s=document.getElementById("stare");s.textContent=text;s.className="stare "+(clasa||"");
}
async function cere(cale,post){
 var opt={credentials:"same-origin",cache:"no-store",headers:{}};
 if(post){opt.method="POST";if(CFG.csrf){opt.headers["X-HDS-CSRF"]=CFG.csrf;}}
 var r=await fetch(adresa(cale),opt),d=await r.json();
 if(!r.ok||!d.result){throw new Error(d.message||"Nu am putut termina. Încearcă din nou.");}
 return d;
}
function eroare(e){
 return e&&e.message&&e.name!=="TypeError"?e.message:"Receptorul nu răspunde. Verifică legătura și încearcă din nou.";
}
function deseneaza(){
 var g=document.getElementById("grila");g.replaceChildren();var coada=[];
 DATE.lista.forEach(function(i){
  var c=document.createElement("div");c.className="cartela"+(i.id===DATE.ales?" aleasa":"");
  var b=document.createElement("button");b.type="button";b.className="alege";
  var p=document.createElement("span");p.className="poza";p.textContent=i.nume;
  var t=document.createElement("span");t.className="titlu";t.textContent=i.nume;
  if(i.id===DATE.ales){var e=document.createElement("span");e.className="eticheta";e.textContent="Ales";t.appendChild(e);}
  var d=document.createElement("span");d.className="descriere";d.textContent=i.descriere;
  b.append(p,t,d);b.addEventListener("click",function(){alege(i);});
  var pr=document.createElement("button");pr.type="button";pr.className="secundar";pr.textContent="Probează pe televizor";
  pr.addEventListener("click",function(){proba(i);});
  c.append(b,pr);g.appendChild(c);
  if(i.poza){coada.push({item:i,element:p});}
 });
 (async function(){
  while(coada.length){var v=coada.shift();
   try{var r=await cere("/api/screensaver-poza?id="+encodeURIComponent(v.item.id));
    var img=document.createElement("img");img.alt=v.item.nume;img.src="data:"+r.mime+";base64,"+r.data;
    v.element.replaceChildren(img);}catch(e){}
  }
 })();
}
function deseneazaDupa(){
 var rand=document.getElementById("randDupa"),s=document.getElementById("dupa");
 if(!DATE.dupa){rand.hidden=true;return;}
 s.replaceChildren();DATE.dupa.alegeri.forEach(function(a){
  var o=document.createElement("option");o.value=a[0];o.textContent=a[1];o.selected=a[0]===DATE.dupa.valoare;s.appendChild(o);
 });rand.hidden=false;
}
async function incarca(){
 try{DATE=await cere("/api/screensaver");deseneaza();deseneazaDupa();
  mesaj("Apasă o cartelă ca să alegi screensaverul. Se păstrează singur.");
 }catch(e){mesaj(eroare(e),"rau");}
}
async function alege(i){
 if(OCUPAT){return;}OCUPAT=true;
 try{var d=await cere("/api/screensaver-alege?id="+encodeURIComponent(i.id),true);DATE.ales=i.id;deseneaza();mesaj(d.message,"bun");}
 catch(e){mesaj(eroare(e),"rau");}finally{OCUPAT=false;}
}
async function proba(i){
 try{var d=await cere("/api/screensaver-proba?id="+encodeURIComponent(i.id),true);mesaj(d.message,"bun");}
 catch(e){mesaj(eroare(e),"rau");}
}
document.getElementById("dupa").addEventListener("change",async function(){
 try{var d=await cere("/api/screensaver-dupa?valoare="+encodeURIComponent(this.value),true);DATE.dupa.valoare=this.value;mesaj(d.message,"bun");}
 catch(e){mesaj(eroare(e),"rau");}
});
incarca();
</script>
</body>
</html>"""


def N_(text):
	return text


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)


TEXTE_PAGINA = {"html": (
	N_("Screensaver"),
	N_("Ce se vede pe televizor când nu atingi telecomanda. Apasă o cartelă ca să o alegi. Totul se mișcă încet pe ecran, ca televizorul să nu rămână cu aceeași imagine."),
	N_("Pornește după"), N_("Se încarcă..."), N_("Screensaverele"),
	), "js": (
	N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Ales"), N_("Probează pe televizor"),
	N_("Apasă o cartelă ca să alegi screensaverul. Se păstrează singur."),
)}

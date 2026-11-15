# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pagina web "Mozaic", http://hdsatelit.local/mozaic: perechea ecranului Screens/HdsMozaic.py (regula din 24.09.2026).
# Aceeasi grila: toate canalele TV ale transponderului canalului de pe televizor, pe 2, 4 sau 9 celule, cu pagini; in
# fiecare celula ultima poza a canalului (dosarul comun cu HdsUltimaImagine), numele si emisiunea de acum, reimprospatate
# singure. Clic pe o celula = canalul pe televizor. Asezarea aleasa e aceeasi cu a televizorului (tinuta minte).
# "Deschide pe televizor" porneste ecranul mozaicului, care face pozele noi (a doua fereastra video sau runda).
#
#   GET  /api/mozaic                  canalele transponderului, asezarea, canalul de pe televizor
#   GET  /api/mozaic-poza?ref=        poza unui canal (numai din dosarul pozelor, dupa cheia referintei)
#   POST /api/mozaic-zap?ref=         canalul pe televizor (numai un canal de pe acelasi transponder)
#   POST /api/mozaic-asezare?a=2|4|9  asezarea, tinuta minte
#   POST /api/mozaic-deschide         ecranul mozaicului pe televizor

import os


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _M():
	from Components import HdsMozaic
	return HdsMozaic


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace")


def _refTv():
	try:
		from Screens.InfoBar import InfoBar
		r = InfoBar.instance.session.nav.getCurrentlyPlayingServiceReference()
		return r.toString() if r else ""
	except Exception:
		return ""


def date(ref_tv=None, M=None, canale=None, emisiune=None, poza=None, asezare=None):
	"""{"result", "canale": [{"i", "ref", "nume", "program", "poza", "v"}], "ales", "asezare", "pe_pagina"}"""
	M = M or _M()
	ref_tv = _refTv() if ref_tv is None else ref_tv
	canale = M.canaleTransponder(ref_tv) if canale is None else canale
	emisiune = emisiune or M.emisiuneaDeAcum
	poza = poza or _versiunePoza
	aleasa = M.asezareAleasa() if asezare is None else asezare
	curat = M.curata(ref_tv)
	rez, ales = [], 0
	for i, (ref, nume) in enumerate(canale):
		v = poza(ref)
		rez.append({"i": i, "ref": ref, "nume": nume, "program": emisiune(ref), "poza": v > 0, "v": v})
		if ref == curat:
			ales = i
	return {"result": True, "canale": rez, "ales": ales, "asezare": aleasa,
		"pe_pagina": M.asezareEfectiva(aleasa, len(canale)),
		"mesaj": "" if canale else _t("Canalul de pe televizor nu e pe un transponder din listă (fișier, IPTV sau niciun canal).")}


def _versiunePoza(ref):
	"""mtime-ul pozei (intreg) sau 0 cand nu e; pagina il pune in adresa ca poza noua sa nu vina din memoria browserului"""
	M = _M()
	cale = M.calePoza(ref)
	try:
		return int(os.path.getmtime(cale)) if cale and os.path.getsize(cale) >= M.MIN_OCTETI else 0
	except OSError:
		return 0


def permisZap(ref, ref_tv, M=None):
	"""numai un canal TV de pe transponderul televizorului (pagina nu poate porni altceva)"""
	M = M or _M()
	if not ref or not M.eTv(ref):
		return False
	return M.campuriTransponder(ref) is not None and M.campuriTransponder(ref) == M.campuriTransponder(ref_tv)


def rute(baza, resource):
	class _Post(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Se trimite cu POST."), 405)

		def render_POST(self, request):
			try:
				r = self.fa(request)
				if isinstance(r, tuple):
					return self._eroare(request, r[0], r[1])
				return self._raspunde(request, r)
			except Exception as e:
				print("[HdsWebControl] mozaic: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class DateResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, date())
			except Exception as e:
				print("[HdsWebControl] mozaic: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class PozaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			M = _M()
			cale = M.calePoza(_arg(request, b"ref"))
			try:
				with open(cale, "rb") as f:
					corp = f.read()
			except (OSError, TypeError):
				request.setResponseCode(404)
				return b""
			request.setHeader(b"Content-Type", b"image/jpeg")
			request.setHeader(b"Cache-Control", b"no-store")
			return corp

	class ZapResource(_Post):
		def fa(self, request):
			from enigma import eServiceReference
			from Screens.InfoBar import InfoBar
			ref = _M().curata(_arg(request, b"ref"))
			if not permisZap(ref, _refTv()):
				return _t("Canalul nu e pe transponderul de pe televizor."), 400
			InfoBar.instance.session.nav.playService(eServiceReference(ref))
			return {"result": True}

	class AsezareResource(_Post):
		def fa(self, request):
			M = _M()
			try:
				a = int(_arg(request, b"a"))
			except ValueError:
				a = 0
			if a not in M.ALEGERI:
				return _t("Așezarea poate fi 2, 4 sau 9."), 400
			M.tineMinteAsezarea(a)
			return {"result": True, "asezare": a}

	class DeschideResource(_Post):
		def fa(self, request):
			from Screens.InfoBar import InfoBar
			from Screens.HdsMozaic import HdsMozaic
			ib = InfoBar.instance
			ib.session.open(HdsMozaic, ib)
			return {"result": True}

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"mozaic": DateResource(), b"mozaic-poza": PozaResource(), b"mozaic-zap": ZapResource(),
		b"mozaic-asezare": AsezareResource(), b"mozaic-deschide": DeschideResource()}, PaginaResource()


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
<title>Mozaic</title>
<style>__STIL_COMUN__
#mozaic{width:100%;max-width:1280px;margin:0 auto;padding-bottom:24px;box-sizing:border-box;}
#mozaic *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 6px;}
.intro{color:var(--text-slab);margin:0 0 14px;line-height:1.5;}
.bara{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 14px;}
.bara .loc{flex:1 1 auto;color:var(--text-slab);text-align:right;}
button{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
 padding:10px 16px;min-height:44px;cursor:pointer;}
button.ales{background:var(--accent);border-color:var(--accent);color:#fff;}
button:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
.grila{display:grid;gap:16px;}
.grila.c1{grid-template-columns:1fr;}
.grila.c2{grid-template-columns:repeat(2,1fr);}
.grila.c3{grid-template-columns:repeat(3,1fr);}
.celula{background:#16233a;border:3px solid transparent;border-radius:10px;overflow:hidden;cursor:pointer;text-align:left;
 padding:0;display:block;width:100%;}
.celula.tv{border-color:#2e8bff;}
.celula .img{aspect-ratio:16/9;background:#0b1422;display:flex;align-items:center;justify-content:center;color:var(--text-slab);
 font-size:.9rem;}
.celula img{width:100%;height:100%;object-fit:cover;display:block;}
.celula .nume{padding:8px 12px 0;font-size:1.05rem;color:#f2f5fa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.celula .prog{padding:2px 12px 10px;font-size:.9rem;color:#9fb0c8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.stare{padding:10px 14px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:0 0 14px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
@media (max-width:700px){.grila.c3{grid-template-columns:repeat(2,1fr);}}
[hidden]{display:none!important;}
</style>
</head>
<body>
<main id="mozaic">
<h1>Mozaic</h1>
<p class="intro">Toate canalele de pe transponderul canalului de pe televizor. Apasă pe un canal ca să-l pornești pe televizor.</p>
<div class="stare" id="stare" role="status" aria-live="polite" hidden></div>
<div class="bara">
 <button type="button" data-a="2">2</button><button type="button" data-a="4">4</button><button type="button" data-a="9">9</button>
 <button type="button" id="inapoi" aria-label="Pagina anterioară">‹</button>
 <button type="button" id="inainte" aria-label="Pagina următoare">›</button>
 <span class="loc" id="loc"></span>
 <button type="button" id="deschide">Deschide pe televizor</button>
</div>
<div class="grila" id="grila"></div>
</main>
<script>
var CFG=__CONFIG__;
var D=null, PAG=0, PRIMA=true;
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
function coloane(pe){return pe===2?2:(pe===4?2:3);}
function deseneaza(){
 var g=el("grila"),pe=D.pe_pagina,n=D.canale.length,pagini=Math.max(1,Math.ceil(n/pe));
 if(PAG>=pagini){PAG=pagini-1;}
 document.querySelectorAll("[data-a]").forEach(function(b){b.className=(+b.dataset.a===D.asezare)?"ales":"";});
 el("loc").textContent=n?("Pagina "+(PAG+1)+" din "+pagini+" · "+n+" canale"):"";
 g.className="grila c"+coloane(pe);
 g.textContent="";
 D.canale.slice(PAG*pe,PAG*pe+pe).forEach(function(c){
  var b=document.createElement("button");b.type="button";b.className="celula"+(c.i===D.ales?" tv":"");
  var im=document.createElement("div");im.className="img";
  if(c.poza){var i=document.createElement("img");i.alt="";i.src=adresa("/api/mozaic-poza?ref="+encodeURIComponent(c.ref)+"&v="+c.v);im.appendChild(i);}
  else{im.textContent="Imaginea apare după ce deschizi mozaicul pe televizor.";}
  var nm=document.createElement("div");nm.className="nume";nm.textContent=(c.i+1)+"  "+c.nume;
  var pr=document.createElement("div");pr.className="prog";pr.textContent=c.program||"";
  b.appendChild(im);b.appendChild(nm);b.appendChild(pr);
  b.addEventListener("click",function(){zap(c);});
  g.appendChild(b);
 });
}
async function citeste(){
 try{D=await cere("/api/mozaic");mesaj(D.mesaj||"",false);
  if(PRIMA){PAG=Math.floor(D.ales/D.pe_pagina);PRIMA=false;}deseneaza();}
 catch(e){mesaj(eroare(e),true);}
}
async function zap(c){try{await cere("/api/mozaic-zap?ref="+encodeURIComponent(c.ref),true);D.ales=c.i;deseneaza();}catch(e){mesaj(eroare(e),true);}}
document.querySelectorAll("[data-a]").forEach(function(b){b.addEventListener("click",async function(){
 try{await cere("/api/mozaic-asezare?a="+b.dataset.a,true);PRIMA=true;await citeste();}catch(e){mesaj(eroare(e),true);}
});});
el("inapoi").addEventListener("click",function(){if(!D){return;}var p=Math.max(1,Math.ceil(D.canale.length/D.pe_pagina));PAG=(PAG-1+p)%p;deseneaza();});
el("inainte").addEventListener("click",function(){if(!D){return;}var p=Math.max(1,Math.ceil(D.canale.length/D.pe_pagina));PAG=(PAG+1)%p;deseneaza();});
el("deschide").addEventListener("click",async function(){try{await cere("/api/mozaic-deschide",true);mesaj("Mozaicul e deschis pe televizor.",false);}catch(e){mesaj(eroare(e),true);}});
citeste();
setInterval(citeste,4000);
</script>
</body>
</html>"""


def N_(text):
	return text


TEXTE_PAGINA = {"html": (
	N_("Mozaic"),
	N_("Toate canalele de pe transponderul canalului de pe televizor. Apasă pe un canal ca să-l pornești pe televizor."),
	N_("Pagina anterioară"), N_("Pagina următoare"), N_("Deschide pe televizor"),
	), "js": (
	N_("Receptorul a răspuns neașteptat."), N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Pagina"), N_("din"), N_("canale"),
	N_("Imaginea apare după ce deschizi mozaicul pe televizor."), N_("Mozaicul e deschis pe televizor."),
)}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

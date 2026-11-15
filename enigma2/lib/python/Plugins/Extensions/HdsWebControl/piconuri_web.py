# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pagina web "Sigle canale (piconuri)", http://hdsatelit.local/piconuri: perechea ecranului Screens/HdsPiconuri.py, cu
# aceleasi functii (Components/HdsPiconInstalare.py) si acelasi lucru pe fir (o singura instalare odata, vazuta si pe
# televizor). Omul scrie adresa unei arhive sau trimite o arhiva din calculator; locul si bifa "Numai canalele din lista
# mea" ca pe televizor; actualizarea si dezinstalarea. Imaginea nu propune nicio sursa.
#
#   GET  /api/piconuri                                    locurile, locul ales singur, starea lucrului
#   GET  /api/piconuri-stare                              numai starea lucrului (cererea de la o secunda)
#   POST /api/piconuri-adresa?adresa=&loc=&numai=1        porneste instalarea de la adresa
#   POST /api/piconuri-urca?id=&pozitie=&total=&nume=&loc=&numai=1   o bucata a arhivei, octeti bruti in corp
#                                                         (cel mult HdsPiconInstalare.MAX_BUCATA; limita corpului o pune
#                                                         _CerereHds din plugin.py, CALE_URCARE_PICON); ultima porneste
#   POST /api/piconuri-actualizeaza?loc=                  aceeasi sursa, acelasi loc
#   POST /api/piconuri-dezinstaleaza?loc=                 numai siglele puse de noi
#   POST /api/piconuri-opreste                            opreste instalarea
#   POST /api/piconuri-pornite?da=1|0                     setarea Da/Nu Siglele canalelor (config.usage.hds_piconuri),
#                                                         primul rand si in ecranul de pe televizor (0.7.5, LCF, dorinelu 795)
# Locul vine numai din lista locurilor (loc_permis): pagina nu poate scrie in alta cale.

from .ecran_pornire_web import porneste_pe_fir


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _modul():
	from Components import HdsPiconInstalare
	return HdsPiconInstalare


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace")


def date(P=None):
	P = P or _modul()
	lista = P.locuri()
	for l in lista:
		l["liber_text"] = P.marime_text(l["liber"])
	return {"result": True, "locuri": lista, "loc": P.loc_implicit(lista), "stare": P.Lucru.stare(), "pornite": _pornite()}


def _pornite():
	"""Setarea Siglele canalelor (config.usage.hds_piconuri); fara ea (probele de pe PC), pornita."""
	try:
		from Components.config import config
		return bool(config.usage.hds_piconuri.value)
	except Exception:
		return True


def pune_pornite(da):
	"""Da/Nu pe setarea Siglele canalelor, ca primul rand al ecranului Sigle canale; se aplica pe loc (HdsPiconBare)."""
	from Components.config import config, configfile
	el = config.usage.hds_piconuri
	el.value = bool(da)
	el.save()
	configfile.save()
	return bool(el.value)


class _Stare(object):
	scrie = [False]


def rute(baza, resource, modul=None, fabrica_ceas=None):
	def m():
		return modul or _modul()

	class _Post(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Se trimite cu POST."), 405)

		def render_POST(self, request):
			P = m()
			try:
				return self._raspunde(request, self.fa(P, request))
			except P.Eroare as e:
				return self._eroare(request, str(e), 400)
			except Exception as e:
				return self._eroare(request, _t("Eroare pe receptor: %s") % e, 500)

	class DateResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, date(m()))
			except Exception as e:
				return self._eroare(request, _t("Eroare pe receptor: %s") % e, 500)

	class StareResource(baza):
		"""Numai starea lucrului, fara parcurgerea dosarelor: pagina o cere la o secunda cat merge instalarea."""

		def render_GET(self, request):
			return self._raspunde(request, {"result": True, "stare": m().Lucru.stare()})

	class AdresaResource(_Post):
		def fa(self, P, request):
			loc = P.loc_permis(_arg(request, b"loc"))
			adresa = P._adresa_buna(_arg(request, b"adresa"))
			if not P.Lucru.porneste(P.instaleaza_din_adresa, adresa, loc, _arg(request, b"numai", b"1") == "1"):
				raise P.Eroare(_t("Se instalează deja. Așteaptă să se termine."))
			return {"result": True, "stare": P.Lucru.stare()}

	class ActualizeazaResource(_Post):
		def fa(self, P, request):
			loc = P.loc_permis(_arg(request, b"loc"))
			if not P.citeste_jurnal(loc):
				raise P.Eroare(_t("Aici nu sunt sigle puse din acest ecran. Instalează întâi un set."))
			if not P.Lucru.porneste(P.actualizeaza, loc):
				raise P.Eroare(_t("Se instalează deja. Așteaptă să se termine."))
			return {"result": True, "stare": P.Lucru.stare()}

	class DezinstaleazaResource(_Post):
		def fa(self, P, request):
			if P.Lucru.ocupat:
				raise P.Eroare(_t("Se instalează deja. Așteaptă să se termine."))
			n = P.dezinstaleaza(P.loc_permis(_arg(request, b"loc")))
			return {"result": True, "message": _t("Am șters %d sigle.") % n}

	class PorniteResource(_Post):
		def fa(self, P, request):
			return {"result": True, "pornite": pune_pornite(_arg(request, b"da", b"1") == "1")}

	class OpresteResource(_Post):
		def fa(self, P, request):
			P.Lucru.opreste()
			return {"result": True}

	class UrcaResource(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Se trimite cu POST."), 405)

		def render_POST(self, request):
			P = m()
			if _Stare.scrie[0]:
				return self._eroare(request, _t("Se scrie încă bucata de dinainte. Încearcă din nou."), 503)
			try:
				request.content.seek(0)
				octeti = request.content.read(P.MAX_BUCATA + 1)
				loc = P.loc_permis(_arg(request, b"loc"))
				ident = _arg(request, b"id")
				pozitie, total = int(_arg(request, b"pozitie", b"0")), int(_arg(request, b"total", b"0"))
				nume, numai = _arg(request, b"nume"), _arg(request, b"numai", b"1") == "1"
			except P.Eroare as e:
				return self._eroare(request, str(e), 400)
			except Exception as e:
				return self._eroare(request, _t("Nu am putut citi bucata: %s") % e, 400)
			if len(octeti) > P.MAX_BUCATA:
				return self._eroare(request, _t("Receptorul nu primește bucăți atât de mari."), 413)

			def lucru():
				try:
					gata = P.scrie_bucata(ident, pozitie, total, octeti, loc, nume, numai)
				except P.Eroare as e:
					return {"result": False, "message": str(e)}, 400
				return {"result": True, "gata": gata, "stare": P.Lucru.stare()}
			_Stare.scrie[0] = True
			return porneste_pe_fir(request, lucru, _Stare.scrie, 120, fabrica_ceas)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"piconuri": DateResource(), b"piconuri-stare": StareResource(), b"piconuri-adresa": AdresaResource(), b"piconuri-urca": UrcaResource(),
		b"piconuri-actualizeaza": ActualizeazaResource(), b"piconuri-dezinstaleaza": DezinstaleazaResource(),
		b"piconuri-opreste": OpresteResource(), b"piconuri-pornite": PorniteResource()}, PaginaResource()


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
<title>Sigle canale (piconuri)</title>
<style>__STIL_COMUN__
#piconuri{width:100%;max-width:860px;margin:0 auto;padding-bottom:24px;box-sizing:border-box;}
#piconuri *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 6px;}
.intro{color:var(--text-slab);margin:0 0 18px;line-height:1.5;}
.card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 14px;}
.card h2{font-size:1.05rem;margin:0 0 10px;}
label{display:block;margin:0 0 6px;color:var(--text-slab);font-size:.9rem;}
select,input[type=url],input[type=file]{width:100%;font:inherit;color:var(--text);background:var(--fundal,#0b1020);
 border:1px solid var(--bordura);border-radius:8px;padding:10px 12px;min-height:44px;}
.rand{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px;}
.rand>input{flex:1 1 320px;}
.bifa{display:flex;gap:10px;align-items:center;margin-top:12px;color:var(--text);}
.bifa input{width:22px;height:22px;}
button{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
 padding:10px 16px;min-height:44px;cursor:pointer;}
button.principal{background:var(--accent);border-color:var(--accent);color:#fff;}
button.rau{border-color:#a84d47;color:#ffb4ab;}
button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
button[disabled]{opacity:.55;cursor:wait;}
.stare{padding:12px 14px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:0 0 14px;
 line-height:1.5;min-height:24px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
.stare.bun{color:#9ce3b4;}
.mic{color:var(--text-slab);font-size:.87rem;line-height:1.5;margin:8px 0 0;}
[hidden]{display:none!important;}
</style>
</head>
<body>
<main id="piconuri">
<h1>Sigle canale (piconuri)</h1>
<p class="intro">Pune pe receptor un set de sigle ales de tine, fără FTP. Imaginea nu are seturi proprii.</p>
<div class="stare" id="stare" role="status" aria-live="polite">Se citește receptorul...</div>
<div class="card">
 <label class="bifa"><input type="checkbox" id="pornite" checked> Siglele canalelor (piconuri)</label>
 <p class="mic">Se văd pe bare, în lista de canale și în ghid. Aceeași setare e în Setări generale.</p>
</div>
<div class="card">
 <label for="loc">Unde se pun siglele</label>
 <select id="loc"></select>
 <label class="bifa"><input type="checkbox" id="numai" checked> Numai canalele din lista mea</label>
 <p class="mic" id="detalii"></p>
</div>
<div class="card">
 <h2>De la o adresă</h2>
 <label for="adresa">Adresa arhivei (zip, tar.gz, tar.xz, ipk)</label>
 <div class="rand"><input type="url" id="adresa" inputmode="url" autocomplete="off" spellcheck="false">
 <button type="button" class="principal" id="instaleaza">Instalează</button></div>
</div>
<div class="card">
 <h2>Din calculator</h2>
 <label for="fisier">Arhiva cu sigle</label>
 <div class="rand"><input type="file" id="fisier" accept=".zip,.tar,.tgz,.gz,.xz,.txz,.bz2,.ipk">
 <button type="button" class="principal" id="trimite">Trimite și instalează</button></div>
</div>
<div class="rand">
 <button type="button" id="actualizeaza" hidden>Actualizează siglele (aceeași sursă)</button>
 <button type="button" class="rau" id="dezinstaleaza" hidden>Dezinstalează siglele puse aici</button>
 <button type="button" id="opreste" hidden>Oprește</button>
</div>
</main>
<script>
var CFG=__CONFIG__;
var DATE=null, OCUPAT=false, CEAS=null;
function adresa(cale){
 return CFG.jeton?cale+(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton):cale;
}
function mesaj(text,clasa){var s=document.getElementById("stare");s.textContent=text;s.className="stare "+(clasa||"");}
function el(id){return document.getElementById(id);}
async function cere(cale,post,corp){
 var opt={credentials:"same-origin",cache:"no-store",headers:{}};
 if(post){opt.method="POST";if(CFG.csrf){opt.headers["X-HDS-CSRF"]=CFG.csrf;}
  if(corp){opt.body=corp;opt.headers["Content-Type"]="application/octet-stream";}}
 var r=await fetch(adresa(cale),opt),d;
 if(r.status===413){throw new Error("Receptorul nu primește bucăți atât de mari.");}
 try{d=await r.json();}catch(e){throw new Error("Receptorul a răspuns neașteptat.");}
 if(!r.ok||!d.result){throw new Error(d.message||"Nu am putut termina. Încearcă din nou.");}
 return d;
}
function eroare(e){return e&&e.message&&e.name!=="TypeError"?e.message:"Receptorul nu răspunde. Verifică legătura și încearcă din nou.";}
function loc(){return el("loc").value;}
function numai(){return el("numai").checked?"1":"0";}
function locAles(){return (DATE&&DATE.locuri||[]).filter(function(l){return l.cale===loc();})[0];}
function blocheaza(da){
 OCUPAT=da;["instaleaza","trimite","actualizeaza","dezinstaleaza","loc"].forEach(function(i){el(i).disabled=da;});
 el("opreste").hidden=!da;
}
function arata(){
 var l=locAles();el("actualizeaza").hidden=!(l&&l.ale_noastre);el("dezinstaleaza").hidden=!(l&&l.ale_noastre);
 var p=l?["Sigle aici:",l.sigle,"|","Liberi:",l.liber_text]:[];
 if(l&&l.ale_noastre){p=p.concat(["|","Puse de aici:",l.ale_noastre,"de la",l.sursa]);}
 el("detalii").textContent=p.join(" ");
}
async function citeste(pastreaza){
 try{
  DATE=await cere("/api/piconuri");var ales=pastreaza&&loc()?loc():DATE.loc,s=el("loc");s.replaceChildren();
  DATE.locuri.forEach(function(l){var o=document.createElement("option");o.value=l.cale;
   o.textContent=l.nume+" ("+l.liber_text+" "+"liberi"+")";s.appendChild(o);});
  s.value=ales;if(!s.value&&DATE.locuri.length){s.value=DATE.loc;}el("pornite").checked=DATE.pornite!==false;arata();
  urmareste(DATE.stare,!pastreaza);
 }catch(e){mesaj(eroare(e),"rau");}
}
function urmareste(st,prima){
 if(st.ocupat){blocheaza(true);mesaj(st.text);clearTimeout(CEAS);CEAS=setTimeout(async function(){
   try{var d=await cere("/api/piconuri-stare");urmareste(d.stare,false);}catch(e){CEAS=setTimeout(function(){urmareste(st,false);},2000);}
  },1000);return;}
 var era=OCUPAT;blocheaza(false);
 if(era&&!prima){mesaj(st.text,st.eroare?"rau":"bun");citeste(true);}
 else if(prima){mesaj("Scrie adresa unei arhive sau trimite una din calculator. Se scriu numai siglele canalelor tale.");}
}
el("loc").addEventListener("change",arata);
el("instaleaza").addEventListener("click",async function(){
 var a=el("adresa").value.trim();if(!a){mesaj("Scrie întâi adresa arhivei.","rau");return;}
 try{var d=await cere("/api/piconuri-adresa?adresa="+encodeURIComponent(a)+"&loc="+encodeURIComponent(loc())+"&numai="+numai(),true);
  OCUPAT=true;urmareste(d.stare,false);}catch(e){mesaj(eroare(e),"rau");}
});
el("trimite").addEventListener("click",async function(){
 var f=el("fisier").files[0];if(!f){mesaj("Alege întâi arhiva.","rau");return;}
 var id=Date.now().toString(36)+Math.random().toString(36).slice(2,8),b=4*1024*1024,p=0,d=null;
 blocheaza(true);
 try{
  while(p<f.size){
   var sf=Math.min(f.size,p+b);mesaj("Se trimite arhiva:"+" "+Math.round(p*100/f.size)+"%");
   d=await cere("/api/piconuri-urca?id="+id+"&pozitie="+p+"&total="+f.size+"&nume="+encodeURIComponent(f.name)+
    "&loc="+encodeURIComponent(loc())+"&numai="+numai(),true,f.slice(p,sf));p=sf;
  }
  OCUPAT=true;urmareste(d.stare,false);
 }catch(e){blocheaza(false);mesaj(eroare(e),"rau");}
});
el("actualizeaza").addEventListener("click",async function(){
 try{var d=await cere("/api/piconuri-actualizeaza?loc="+encodeURIComponent(loc()),true);OCUPAT=true;urmareste(d.stare,false);}
 catch(e){mesaj(eroare(e),"rau");}
});
el("dezinstaleaza").addEventListener("click",async function(){
 if(!confirm("Ștergi siglele puse de aici? Siglele tale de dinainte rămân.")){return;}
 try{var d=await cere("/api/piconuri-dezinstaleaza?loc="+encodeURIComponent(loc()),true);mesaj(d.message,"bun");citeste(true);}
 catch(e){mesaj(eroare(e),"rau");}
});
el("pornite").addEventListener("change",async function(){
 var c=el("pornite");
 try{var d=await cere("/api/piconuri-pornite?da="+(c.checked?"1":"0"),true);c.checked=!!d.pornite;}
 catch(e){c.checked=!c.checked;mesaj(eroare(e),"rau");}
});
el("opreste").addEventListener("click",async function(){try{await cere("/api/piconuri-opreste",true);}catch(e){}});
citeste(false);
</script>
</body>
</html>"""


def N_(text):
	return text


TEXTE_PAGINA = {"html": (
	N_("Sigle canale (piconuri)"),
	N_("Pune pe receptor un set de sigle ales de tine, fără FTP. Imaginea nu are seturi proprii."),
	N_("Se citește receptorul..."), N_("Unde se pun siglele"), N_("Numai canalele din lista mea"),
	N_("Siglele canalelor (piconuri)"), N_("Se văd pe bare, în lista de canale și în ghid. Aceeași setare e în Setări generale."),
	N_("De la o adresă"), N_("Adresa arhivei (zip, tar.gz, tar.xz, ipk)"), N_("Instalează"),
	N_("Din calculator"), N_("Arhiva cu sigle"), N_("Trimite și instalează"),
	N_("Actualizează siglele (aceeași sursă)"), N_("Dezinstalează siglele puse aici"), N_("Oprește"),
	), "js": (
	N_("Receptorul nu primește bucăți atât de mari."), N_("Receptorul a răspuns neașteptat."),
	N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Sigle aici:"), N_("Liberi:"), N_("Puse de aici:"), N_("de la"), N_("liberi"),
	N_("Scrie adresa unei arhive sau trimite una din calculator. Se scriu numai siglele canalelor tale."),
	N_("Scrie întâi adresa arhivei."), N_("Alege întâi arhiva."), N_("Se trimite arhiva:"),
	N_("Ștergi siglele puse de aici? Siglele tale de dinainte rămân."),
)}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

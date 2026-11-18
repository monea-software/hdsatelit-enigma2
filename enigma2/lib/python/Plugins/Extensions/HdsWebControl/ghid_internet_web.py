# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pagina web "Ghidul TV din internet", http://hdsatelit.local/ghid-internet: perechea ecranului Screens/HdsGhidInternet.py
# (regula din 24.09.2026). Aceeasi tara, aceleasi surse, acelasi buton: EPG Import instalat daca lipseste, sursele tarii
# bifate, importul pornit acum si zilnic. Logica: Components/HdsGhidInternet.py.
#
#   GET  /api/ghid-internet                  starea (tara, sursele, programarea, ce se lucreaza)
#   POST /api/ghid-internet-porneste?tara=   un pas (tara: codul din lista tarilor cu surse)
#
# Rusia, Ucraina, Belarus, Kazahstan (GTR): sursele dupa satelitii de la tunere; pagina arata satelitii (pe_satelit,
# sateliti), ca ecranul.


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _G():
	from Components import HdsGhidInternet
	return HdsGhidInternet


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace").strip()


def date(s):
	"""starea pentru pagina, fara nimic din afara ei"""
	return {"result": True, "tara": s["tara"], "nume": s["nume"], "sigur": s["sigur"], "are_sursa": s["are_sursa"],
		"candidati": s["candidati"], "tari": s["tari"], "instalat": s["instalat"],
		"surse": [" ".join(d.split()) for d in s["surse_tarii"]], "bifate": len(s["bifate"]),
		"pe_satelit": s.get("pe_satelit", False), "sateliti": s.get("sateliti", []),
		"programat": s["programat"], "ora": s["ora"], "ultimul": s["ultimul"], "faza": s["faza"], "mesaj": s["mesaj"],
		"in_lucru": s["in_lucru"]}


def rute(baza, resource):
	class DateResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, date(_G().stare()))
			except Exception as e:
				print("[HdsWebControl] ghid-internet: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class PornesteResource(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Se trimite cu POST."), 405)

		def render_POST(self, request):
			try:
				G = _G()
				tara = _arg(request, b"tara").upper()
				if not G.areSursa(tara):
					return self._eroare(request, _t(G.TEXT_FARA_SURSA) % G.numeTara(tara) if tara else _t(G.TEXT_NECUNOSCUTA), 400)
				from Screens.InfoBar import InfoBar
				sesiune = InfoBar.instance.session if InfoBar.instance else None
				text = G.porneste(tara, sesiune)
				if text:
					return self._eroare(request, text, 409)
				return self._raspunde(request, {"result": True})
			except Exception as e:
				print("[HdsWebControl] ghid-internet: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"ghid-internet": DateResource(), b"ghid-internet-porneste": PornesteResource()}, PaginaResource()


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
<title>Ghidul TV din internet</title>
<style>__STIL_COMUN__
#ghid{width:100%;max-width:900px;margin:0 auto;padding-bottom:24px;box-sizing:border-box;}
#ghid *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 6px;}
.intro{color:var(--text-slab);margin:0 0 14px;line-height:1.5;}
.panou{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 14px;line-height:1.6;}
.bara{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 14px;}
button,select{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
 padding:10px 16px;min-height:44px;}
button{cursor:pointer;}
button.principal{background:var(--accent);border-color:var(--accent);color:#fff;}
button:disabled{opacity:.6;cursor:default;}
button:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
.stare{padding:10px 14px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:0 0 14px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
.slab{color:var(--text-slab);}
[hidden]{display:none!important;}
</style>
</head>
<body>
<main id="ghid">
<h1>Ghidul TV din internet</h1>
<p class="intro">Programul canalelor din internet, pentru țara ta, cu un singur buton: EPG Import se instalează dacă lipsește, se bifează sursele țării, iar importul pornește acum și apoi zilnic.</p>
<div class="panou" id="info"></div>
<div class="bara">
 <label for="tara" class="slab">Țara</label>
 <select id="tara"></select>
 <button type="button" id="porneste" class="principal">Pornește</button>
</div>
<div class="stare" id="stare" role="status" aria-live="polite" hidden></div>
</main>
<script>
var CFG=__CONFIG__;
var S=null, ALES="";
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
function rand(p,t,slab){var d=document.createElement("div");if(slab){d.className="slab";}d.textContent=t;p.appendChild(d);}
function deseneaza(){
 var i=el("info");i.textContent="";
 if(S.tara){rand(i,"Țara: "+S.nume);if(!S.are_sursa){rand(i,"Pentru această țară nu avem încă o sursă liberă de ghid din internet. Poți alege altă țară.",true);}}
 else if(S.candidati.length>1){rand(i,"Alege țara ghidului: "+S.candidati[0].nume+" sau "+S.candidati[1].nume+".");}
 else{rand(i,"Nu știu încă în ce țară ești. Alege țara ta.");}
 if(S.pe_satelit){rand(i,"Sateliții de la tunere: "+(S.sateliti.length?S.sateliti.join(", "):"niciunul"),true);
  if(S.instalat&&!S.surse.length){rand(i,"Pe sateliții de la tunerele tale nu avem încă surse de ghid din internet pentru această țară.",true);}}
 if(S.surse.length){rand(i,"Sursele: "+S.surse.join(", "),true);}
 rand(i,S.instalat?"EPG Import este instalat.":"EPG Import se instalează la pornire.",true);
 if(S.programat&&S.bifate){rand(i,"Importul se face zilnic la "+S.ora+".",true);}
 if(S.ultimul){rand(i,"Ultimul import: "+S.ultimul,true);}
 var sel=el("tara");
 if(!sel.options.length){
  var primele=S.candidati.filter(function(c){return c.are;}).map(function(c){return c.cod;});
  var lista=S.candidati.filter(function(c){return c.are;}).concat(S.tari.filter(function(t){return primele.indexOf(t.cod)<0;}));
  lista.forEach(function(t){var o=document.createElement("option");o.value=t.cod;o.textContent=t.nume;sel.appendChild(o);});
  ALES=S.tara&&S.are_sursa?S.tara:(primele[0]||"");
  if(ALES){sel.value=ALES;}
 }
 el("porneste").disabled=S.in_lucru;
 el("porneste").textContent=S.programat&&S.bifate?"Pornește din nou":"Pornește";
 if(S.mesaj){mesaj(S.mesaj,S.faza==="eroare");}
}
async function citeste(){try{S=await cere("/api/ghid-internet");deseneaza();}catch(e){mesaj(eroare(e),true);}}
el("porneste").addEventListener("click",async function(){
 var t=el("tara").value;if(!t){mesaj("Alege țara ta.",true);return;}
 el("porneste").disabled=true;mesaj("Se pornește...",false);
 try{await cere("/api/ghid-internet-porneste?tara="+encodeURIComponent(t),true);}catch(e){mesaj(eroare(e),true);}
 citeste();
});
citeste();
setInterval(function(){if(S&&S.in_lucru){citeste();}},3000);
setInterval(citeste,60000);
</script>
</body>
</html>"""


def N_(text):
	return text


TEXTE_PAGINA = {"html": (
	N_("Ghidul TV din internet"),
	N_("Programul canalelor din internet, pentru țara ta, cu un singur buton: EPG Import se instalează dacă lipsește, se bifează sursele țării, iar importul pornește acum și apoi zilnic."),
	N_("Țara"), N_("Pornește"),
	), "js": (
	N_("Receptorul a răspuns neașteptat."), N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Țara: "), N_("Pentru această țară nu avem încă o sursă liberă de ghid din internet. Poți alege altă țară."),
	N_("Alege țara ghidului: "), N_(" sau "), N_("Nu știu încă în ce țară ești. Alege țara ta."), N_("Sursele: "),
	N_("Sateliții de la tunere: "), N_("niciunul"),
	N_("Pe sateliții de la tunerele tale nu avem încă surse de ghid din internet pentru această țară."),
	N_("EPG Import este instalat."), N_("EPG Import se instalează la pornire."), N_("Importul se face zilnic la "),
	N_("Ultimul import: "), N_("Pornește"), N_("Pornește din nou"), N_("Alege țara ta."), N_("Se pornește..."),
)}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pagina web "Despre film", http://hdsatelit.local/despre-film: perechea ecranului Screens/HdsDespreFilm.py (regula din
# 24.09.2026). Aceeasi fisa (afisul, titlul, anul, genul, durata, notele, descrierea, regia, actorii), pentru emisiunea de
# pe televizor sau pentru un titlu scris de om. Datele: Components/HdsDespreFilm.py (Wikidata si Wikipedia, fara cheie).
#
#   GET /api/despre-film-acum                      fisa emisiunii de acum de pe canalul de pe televizor
#   GET /api/despre-film?titlu=&an=                fisa unui titlu scris (anul ajuta cand sunt mai multe filme)
#   GET /api/despre-film-alege?qid=&titlu=&an=     fisa filmului ales din lista (cand nu e sigur care e)
#   GET /api/despre-film-afis?f=<nume>.jpg         afisul, numai din dosarul afiselor (CSP-ul paginilor: img-src 'self')
#   GET /api/despre-film-alege?tmdb=&titlu=&an=    la fel, pentru un film gasit numai in TMDB (cu cheia omului)
#   GET  /api/despre-film-cheie                    cheia TMDB a omului: daca e pusa si ultimele 4 semne, niciodata cheia
#   POST /api/despre-film-cheie  (corp: cheie=)    pune cheia (verificata la TMDB; o cheie refuzata nu se scrie); goala = sterge
# TMDB (INB, 15.11.2026): a doua sursa, numai cu cheia omului (Components/HdsDespreFilm.py, partea TMDB).

import os
import re

_NUME_AFIS = re.compile(r"^[0-9a-f]{24}\.jpg$")


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _D():
	from Components import HdsDespreFilm
	return HdsDespreFilm


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace").strip()[:200]


def evenimentAcum():
	"""(titlu, scurt, lung, inceput, durata) ale emisiunii de acum de pe televizor, sau None."""
	try:
		from enigma import eEPGCache
		from Screens.InfoBar import InfoBar
		ref = InfoBar.instance.session.nav.getCurrentlyPlayingServiceReference()
		if ref is None:
			return None
		ev = eEPGCache.getInstance().lookupEventTime(ref, -1)
		if ev is None:
			return None
		return (ev.getEventName() or "", ev.getShortDescription() or "", ev.getExtendedDescription() or "",
			ev.getBeginTime() or 0, ev.getDuration() or 0)
	except Exception:
		return None


def pentruPagina(rez, D=None):
	"""Rezultatul din HdsDespreFilm (pe fir) -> JSON-ul paginii: afisul adus si dat ca nume, fara adrese sau cai."""
	D = D or _D()
	out = {"result": True, "stare": rez.get("stare"), "mesaj": rez.get("mesaj") or ""}
	if rez.get("stare") == "alege":
		out["candidati"] = [{"qid": c.get("qid") or "", "tmdb": c.get("tmdb") or 0, "titlu": c.get("titlu") or "",
			"an": c.get("an"), "text": D.textCandidat(c)} for c in rez.get("candidati") or []]
	f = rez.get("fisa")
	if f:
		afis = ""
		if f.get("afis_adresa"):
			cale = D.aduAfis(f["afis_adresa"])
			afis = os.path.basename(cale) if cale else ""
		out["fisa"] = {"titlu": f.get("titlu") or "", "detalii": D.randDetalii(f), "note": f.get("note") or [],
			"descriere": f.get("rezumat") or f.get("descriere_scurta") or "", "regie": f.get("regie") or [],
			"actori": f.get("actori") or [], "surse": f.get("surse") or [], "afis": afis,
			"atribuire": D.atribuireTmdb() if "TMDB" in (f.get("surse") or []) else ""}
	return out


def rute(baza, resource):
	from twisted.web.server import NOT_DONE_YET

	class _Fisa(baza):
		"""GET: cautarea merge pe fir (retea, cateva secunde); raspunsul se scrie cand e gata."""

		def render_GET(self, request):
			try:
				lucru = self.lucru(request)
			except Exception as e:
				print("[HdsWebControl] despre-film: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)
			if isinstance(lucru, tuple) and len(lucru) == 2 and isinstance(lucru[1], int):
				return self._eroare(request, lucru[0], lucru[1])
			stare = {"inchis": False}
			request.notifyFinish().addErrback(lambda _e: stare.__setitem__("inchis", True))
			D = _D()

			def gata(rez):
				if stare["inchis"]:
					return
				try:
					corp = self._raspunde(request, rez)
				except Exception as e:
					print("[HdsWebControl] despre-film: %s" % e)
					corp = self._raspunde(request, {"result": False, "message": _t("Eroare pe receptor.")}, 500)
				request.write(corp)
				request.finish()

			functie, arg = lucru
			D.Cautare(gata).porneste(lambda: pentruPagina(functie(*arg), D))
			return NOT_DONE_YET

	class AcumResource(_Fisa):
		def lucru(self, request):
			ev = evenimentAcum()
			if not ev or not ev[0]:
				return _t("Canalul de pe televizor nu are acum o emisiune în ghid."), 404
			D = _D()
			return D.cauta, (D.dinText(*ev), D.limbaMeniului())

	class TitluResource(_Fisa):
		def lucru(self, request):
			titlu = _arg(request, b"titlu")
			if not titlu:
				return _t("Scrie titlul filmului."), 400
			an = _arg(request, b"an")
			D = _D()
			info = D.dinText(titlu, an if re.match(r"^(19|20)\d\d$", an or "") else "")
			return D.cauta, (info, D.limbaMeniului())

	class AlegeResource(_Fisa):
		def lucru(self, request):
			qid = _arg(request, b"qid")
			tmdb = _arg(request, b"tmdb")
			an = _arg(request, b"an")
			if re.match(r"^Q\d{1,12}$", qid):
				c = {"qid": qid, "titlu": _arg(request, b"titlu"), "an": int(an) if an.isdigit() else None}
			elif re.match(r"^[1-9]\d{0,9}$", tmdb):
				c = {"tmdb": int(tmdb), "titlu": _arg(request, b"titlu"), "an": int(an) if an.isdigit() else None}
			else:
				return _t("Filmul ales nu e bun."), 400
			D = _D()
			return D.deschide, (c, D.limbaMeniului())

	class AfisResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			nume = _arg(request, b"f")
			if not _NUME_AFIS.match(nume):
				request.setResponseCode(404)
				return b""
			try:
				with open(os.path.join(_D().DOSAR, nume), "rb") as fd:
					corp = fd.read()
			except OSError:
				request.setResponseCode(404)
				return b""
			request.setHeader(b"Content-Type", b"image/jpeg")
			request.setHeader(b"Cache-Control", b"max-age=3600")
			return corp

	class CheieResource(baza):
		"""Cheia TMDB a omului. GET: starea (pusa, ultimele 4 semne, textul). POST: o pune sau o sterge; verificarea la TMDB
		merge pe fir. Cheia vine in corpul cererii (nu in adresa, care poate ajunge in jurnale) si nu se intoarce niciodata."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, dict(_D().stareCheieTmdb(), result=True))
			except Exception as e:
				print("[HdsWebControl] despre-film-cheie: %s" % e.__class__.__name__)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

		def render_POST(self, request):
			try:
				valoare = request.args.get(b"cheie", [b""])[0].decode("utf-8", "replace")[:2048]
			except Exception:
				valoare = ""
			stare = {"inchis": False}
			request.notifyFinish().addErrback(lambda _e: stare.__setitem__("inchis", True))
			D = _D()

			def gata(rez):
				if stare["inchis"]:
					return
				try:
					ok, mesaj = rez
					corp = self._raspunde(request, dict(D.stareCheieTmdb(), result=bool(ok), message=mesaj), 200 if ok else 400)
				except Exception as e:
					print("[HdsWebControl] despre-film-cheie: %s" % e.__class__.__name__)
					corp = self._raspunde(request, {"result": False, "message": _t("Eroare pe receptor.")}, 500)
				request.write(corp)
				request.finish()

			D.Cautare(gata).porneste(D.pastreazaCheieTmdb, valoare)
			return NOT_DONE_YET

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"despre-film-acum": AcumResource(), b"despre-film": TitluResource(), b"despre-film-alege": AlegeResource(),
		b"despre-film-afis": AfisResource(), b"despre-film-cheie": CheieResource()}, PaginaResource()


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
<title>Despre film</title>
<style>__STIL_COMUN__
#film{width:100%;max-width:1100px;margin:0 auto;padding-bottom:24px;box-sizing:border-box;}
#film *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 6px;}
.intro{color:var(--text-slab);margin:0 0 14px;line-height:1.5;}
form{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px;}
input{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;padding:10px 12px;min-height:44px;}
#titlu{flex:1 1 260px;}
#an{width:110px;}
button{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
 padding:10px 16px;min-height:44px;cursor:pointer;}
button.principal{background:var(--accent);border-color:var(--accent);color:#fff;}
button:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
.stare{padding:10px 14px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:0 0 14px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
.lista{display:flex;flex-direction:column;gap:8px;margin:0 0 14px;}
.lista button{text-align:left;}
.fisa{display:grid;grid-template-columns:220px 1fr;gap:20px;background:var(--panou);border:1px solid var(--bordura);border-radius:12px;padding:18px;}
.fisa img{width:100%;border-radius:8px;display:block;}
.fisa h2{margin:0 0 6px;font-size:1.5rem;}
.detalii{color:var(--text-slab);margin:0 0 8px;}
.note{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px;}
.note span{background:#2a2410;color:#f5c518;border-radius:6px;padding:4px 10px;font-weight:600;}
.descriere{line-height:1.6;margin:0 0 12px;}
.mic{color:var(--text-slab);font-size:.9rem;}
details.cheie{margin:18px 0 0;background:var(--panou);border:1px solid var(--bordura);border-radius:12px;padding:12px 16px;}
details.cheie summary{cursor:pointer;font-weight:600;min-height:28px;}
#cheie-form{margin:10px 0 0;}
#cheie{flex:1 1 300px;}
@media (max-width:640px){.fisa{grid-template-columns:1fr;}.fisa img{max-width:220px;}}
[hidden]{display:none!important;}
</style>
</head>
<body>
<main id="film">
<h1>Despre film</h1>
<p class="intro">Afișul, descrierea, notele și actorii filmului de pe televizor sau ai unui titlu scris de tine. Datele vin din Wikidata și Wikipedia.</p>
<form id="cauta">
 <button type="button" class="principal" id="acum">Filmul de acum de pe televizor</button>
 <input id="titlu" type="search" placeholder="Titlul filmului" aria-label="Titlul filmului">
 <input id="an" type="number" min="1920" max="2049" placeholder="Anul" aria-label="Anul">
 <button type="submit">Caută</button>
</form>
<div class="stare" id="stare" role="status" aria-live="polite" hidden></div>
<div class="lista" id="lista" hidden></div>
<div class="fisa" id="fisa" hidden>
 <div><img id="afis" alt="" hidden></div>
 <div>
  <h2 id="f-titlu"></h2>
  <p class="detalii" id="f-detalii"></p>
  <div class="note" id="f-note"></div>
  <p class="descriere" id="f-descriere"></p>
  <p id="f-regie"></p>
  <p id="f-actori"></p>
  <p class="mic" id="f-surse"></p>
  <p class="mic" id="f-atribuire" hidden></p>
 </div>
</div>
<details class="cheie" id="cheie-sectiune">
 <summary>Cheia ta TMDB (opțional)</summary>
 <p class="mic" id="cheie-stare"></p>
 <form id="cheie-form" autocomplete="off">
  <input id="cheie" type="password" placeholder="Cheia API sau tokenul de citire de pe themoviedb.org" aria-label="Cheia TMDB">
  <button type="submit">Salvează</button>
  <button type="button" id="cheie-sterge" hidden>Șterge cheia</button>
 </form>
 <p class="mic">Cu cheia ta gratuită, afișul, descrierea și notele care lipsesc din Wikidata vin din TMDB. Fără cheie nu se trimite nimic la TMDB.</p>
</details>
</main>
<script>
var CFG=__CONFIG__;
function adresa(cale){return CFG.jeton?cale+(cale.indexOf("?")<0?"?":"&")+"token="+encodeURIComponent(CFG.jeton):cale;}
function el(id){return document.getElementById(id);}
function mesaj(t,rau){var s=el("stare");s.hidden=!t;s.textContent=t||"";s.className="stare"+(rau?" rau":"");}
async function cere(cale,corp){
 var opt={credentials:"same-origin",cache:"no-store",headers:{}};
 if(corp!==undefined){opt.method="POST";opt.body=corp;if(CFG.csrf){opt.headers["X-HDS-CSRF"]=CFG.csrf;}}
 var r=await fetch(adresa(cale),opt),d;
 try{d=await r.json();}catch(e){throw new Error("Receptorul a răspuns neașteptat.");}
 if(!r.ok||!d.result){throw new Error(d.message||"Nu am putut termina. Încearcă din nou.");}
 return d;
}
function eroare(e){return e&&e.message&&e.name!=="TypeError"?e.message:"Receptorul nu răspunde. Verifică legătura și încearcă din nou.";}
function arata(d){
 el("lista").hidden=true;el("fisa").hidden=true;
 if(d.stare==="alege"){
  mesaj("Nu e sigur care film este. Alege din listă.",false);
  var l=el("lista");l.textContent="";
  d.candidati.forEach(function(c){var b=document.createElement("button");b.type="button";b.textContent=c.text;
   var ales=c.qid?("qid="+encodeURIComponent(c.qid)):("tmdb="+encodeURIComponent(c.tmdb));
   b.addEventListener("click",function(){porneste("/api/despre-film-alege?"+ales+"&titlu="+encodeURIComponent(c.titlu)+"&an="+(c.an||""));});
   l.appendChild(b);});
  l.hidden=false;return;
 }
 if(d.stare!=="gata"||!d.fisa){mesaj(d.mesaj||"Filmul nu s-a găsit.",true);return;}
 mesaj("",false);
 var f=d.fisa;
 el("f-titlu").textContent=f.titlu;el("f-detalii").textContent=f.detalii;
 var n=el("f-note");n.textContent="";f.note.forEach(function(x){var s=document.createElement("span");s.textContent=x[0]+" "+x[1];n.appendChild(s);});
 el("f-descriere").textContent=f.descriere||"Wikipedia nu are încă o descriere pentru acest film.";
 el("f-regie").textContent=f.regie.length?("Regia: "+f.regie.join(", ")):"";
 el("f-actori").textContent=f.actori.length?("Cu: "+f.actori.join(", ")):"";
 el("f-surse").textContent="Sursa: "+f.surse.join(", ");
 var at=el("f-atribuire");at.textContent=f.atribuire||"";at.hidden=!f.atribuire;
 var a=el("afis");if(f.afis){a.src=adresa("/api/despre-film-afis?f="+encodeURIComponent(f.afis));a.hidden=false;}else{a.hidden=true;}
 el("fisa").hidden=false;
}
async function porneste(cale){
 mesaj("Caut filmul în Wikidata și Wikipedia...",false);
 try{arata(await cere(cale));}catch(e){mesaj(eroare(e),true);}
}
el("acum").addEventListener("click",function(){porneste("/api/despre-film-acum");});
el("cauta").addEventListener("submit",function(ev){ev.preventDefault();var t=el("titlu").value.trim();
 if(!t){mesaj("Scrie titlul filmului.",true);return;}
 porneste("/api/despre-film?titlu="+encodeURIComponent(t)+"&an="+encodeURIComponent(el("an").value.trim()));});
function stareCheie(d){
 el("cheie-stare").textContent=d.text||"";el("cheie-sterge").hidden=!d.pusa;
}
async function trimiteCheie(valoare){
 var corp=new URLSearchParams();corp.set("cheie",valoare);
 try{var d=await cere("/api/despre-film-cheie",corp);stareCheie(d);el("cheie").value="";mesaj(d.message||"",false);
  porneste("/api/despre-film-acum");}
 catch(e){mesaj(eroare(e),true);}
}
el("cheie-form").addEventListener("submit",function(ev){ev.preventDefault();var v=el("cheie").value.trim();
 if(!v){mesaj("Scrie cheia sau apasă Șterge cheia.",true);return;}trimiteCheie(v);});
el("cheie-sterge").addEventListener("click",function(){trimiteCheie("");});
cere("/api/despre-film-cheie").then(stareCheie).catch(function(){});
porneste("/api/despre-film-acum");
</script>
</body>
</html>"""


def N_(text):
	return text


TEXTE_PAGINA = {"html": (
	N_("Despre film"),
	N_("Afișul, descrierea, notele și actorii filmului de pe televizor sau ai unui titlu scris de tine. Datele vin din Wikidata și Wikipedia."),
	N_("Filmul de acum de pe televizor"), N_("Titlul filmului"), N_("Anul"), N_("Caută"),
	N_("Cheia ta TMDB (opțional)"), N_("Cheia API sau tokenul de citire de pe themoviedb.org"), N_("Cheia TMDB"),
	N_("Salvează"), N_("Șterge cheia"),
	N_("Cu cheia ta gratuită, afișul, descrierea și notele care lipsesc din Wikidata vin din TMDB. Fără cheie nu se trimite nimic la TMDB."),
	), "js": (
	N_("Receptorul a răspuns neașteptat."), N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("Nu e sigur care film este. Alege din listă."), N_("Filmul nu s-a găsit."),
	N_("Wikipedia nu are încă o descriere pentru acest film."), N_("Regia: "), N_("Cu: "), N_("Sursa: "),
	N_("Caut filmul în Wikidata și Wikipedia..."), N_("Scrie titlul filmului."),
	N_("Scrie cheia sau apasă Șterge cheia."),
)}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

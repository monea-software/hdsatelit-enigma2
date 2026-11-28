# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Web page "YouTube", http://hdsatelit.local/youtube (0.8.0, YTN1): the pair of the native screen
# Screens/HdsYouTube.py. The same lists (Home, Search, Live, Watched, a channel, a playlist), the same data
# (Components/HdsYouTube.py, no account), and "On the TV": the film plays on the receiver (only the film id is sent:
# /web/zap cuts long references at 600 characters).
#
#   GET  /api/youtube?fel=acasa|cauta|live|vazute|canal|lista|inrudite&q=&id=&cont=&capat=
#   POST /api/youtube-reda?id=<11-character film id>
#   GET  /api/youtube-setari                       the two settings of the TV screen's MENU, with their choices
#   POST /api/youtube-setari?calitate=&deschide=   the same, saved
# The network work runs on a thread (deferToThread), never on the main loop.
# YTN3 (0.8.x): tiles like the TV screen's: the 320x180 picture with the length (or "live") on it, the title on two
# lines, the channel and the views under it; a click on the picture plays the film on the TV (opens a channel/playlist).
import re


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def N_(text):
	return text


_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ID_LISTA = re.compile(r"^[A-Za-z0-9_-]{2,64}$")


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("utf-8", "replace").strip()


def _yt():
	from Components import HdsYouTube as Y
	from Screens.HdsYouTube import limba
	return Y, Y.YouTube(limba())


RUBRICI_WEB = {"jocuri": "FEtopics_gaming", "stiri": "FEtopics_news", "sport": "FEtopics_sports",
	"podcast": "FEtopics_podcasts", "live": "FEtopics_live"}


def _tara():
	"""the country of the charts, as on the TV (MENU > Țara); "" outside the receiver (PC tests)"""
	try:
		from Screens.HdsYouTube import taraTopuri
		return taraTopuri() or ""
	except Exception:
		return ""


def liste(fel, q="", id_="", cont="", capat="browse", Y=None, yt=None):
	"""the list for the page: {"result", "elemente", "cont", "capat"}"""
	if Y is None:
		Y, yt = _yt()
	tara = _tara()
	if tara:
		yt.gl = tara
	if cont:
		bun = capat in ("browse", "search", "next") or re.match(r"^tv:([A-Z]{2})?$", capat or "") is not None
		e, c = yt.continua(capat if bun else "browse", cont)
	elif fel == "acasa":
		e, c, capat = yt.acasa() + ("browse",)
	elif fel == "muzica":
		e, c = yt.muzica(tara)
		capat = "tv:" + (tara or "")
	elif fel in RUBRICI_WEB and not (fel == "live" and q):
		# the topic pages of the TV screen (YTN2); "live" with a word typed is still a search of live streams
		e, c = yt.rubrica(RUBRICI_WEB[fel])
		capat = "tv:"
	elif fel in ("cauta", "live"):
		if not q:
			return {"result": True, "elemente": [], "cont": None, "capat": "search", "cautari": yt.stare.cautari()}
		if fel == "cauta":
			yt.stare.adauga_cautare(q)
		e, c = yt.cauta(q, "live" if fel == "live" else "film")
		capat = "search"
	elif fel == "vazute":
		e, c, capat = yt.stare.vazute(), None, "browse"
	elif fel == "canal" and _ID_LISTA.match(id_):
		e, c, capat = yt.canal(id_) + ("browse",)
	elif fel == "lista" and _ID_LISTA.match(id_):
		e, c, capat = yt.lista(id_) + ("browse",)
	elif fel == "inrudite" and _ID.match(id_):
		e, c, capat = yt.inrudite(id_) + ("next",)
	else:
		return {"result": False, "message": _t(N_("Cererea nu e bună."))}
	return {"result": True, "elemente": e, "cont": c, "capat": capat, "cautari": yt.stare.cautari()}


def setari(argumente=None):
	"""the TV screen's MENU settings (config.plugins.hdsyoutube): quality and how YouTube opens from Applications"""
	from Components.config import config
	import Screens.HdsYouTube  # noqa: F401  (defines config.plugins.hdsyoutube)
	c = config.plugins.hdsyoutube
	schimbat = False
	for cheie in ("calitate", "deschide", "aspect", "date_bara", "redare_auto", "urmeaza"):
		v = (argumente or {}).get(cheie)
		element = getattr(c, cheie)
		if v and v in [x for x, _n in element.choices.choices] and v != element.value:
			element.value = v
			element.save()
			schimbat = True
	# the country of the charts (YTN2): Automat or any country the screen offers
	from Screens.HdsYouTube import tari, taraAutomata, numeTara
	tariBune = tari()
	v = ((argumente or {}).get("tara") or "").strip()
	if v and (v == "auto" or v in [x for x, _n in tariBune]) and v != c.tara.value:
		c.tara.value = v
		c.tara.save()
		schimbat = True
	if schimbat:
		c.save()
		config.save()
	rez = dict((k, {"valoare": getattr(c, k).value,
		"alegeri": [[x, _t(n)] for x, n in getattr(c, k).choices.choices]}) for k in ("calitate", "deschide", "aspect", "date_bara", "redare_auto", "urmeaza"))
	rez["tara"] = {"valoare": c.tara.value if c.tara.value != "AUTO" else "auto",
		"alegeri": [["auto", u"%s (%s)" % (_t("Automat"), numeTara(taraAutomata()))]] + [[x, n] for x, n in tariBune]}
	return {"result": True, "setari": rez}


def rute(baza, resource):
	class ListeResource(baza):
		def render_GET(self, request):
			from twisted.internet.threads import deferToThread
			from twisted.web.server import NOT_DONE_YET
			argumente = dict((k, _arg(request, k.encode())) for k in ("fel", "q", "id", "cont", "capat"))
			inchisa = [False]

			def deconectata(_motiv):
				inchisa[0] = True

			def gata(rez):
				if not inchisa[0] and not getattr(request, "finished", False):
					request.write(self._raspunde(request, rez))
					request.finish()

			def esec(motiv):
				print("[HdsWebControl] youtube: %s" % motiv.getErrorMessage())
				gata({"result": False, "message": _t(N_("YouTube nu răspunde acum. Verifică internetul și încearcă din nou."))})

			request.notifyFinish().addErrback(deconectata)
			deferToThread(liste, argumente["fel"] or "acasa", argumente["q"][:200], argumente["id"], argumente["cont"],
				argumente["capat"] or "browse").addCallbacks(gata, esec)
			return NOT_DONE_YET

	class RedaResource(baza):
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t(N_("Se trimite cu POST.")), 405)

		def render_POST(self, request):
			vid = _arg(request, b"id")
			if not _ID.match(vid):
				return self._eroare(request, _t(N_("Filmul nu e bun.")), 400)
			try:
				from Screens.InfoBar import InfoBar
				from Screens.HdsYouTube import redaId
				redaId(InfoBar.instance.session, vid)
				return self._raspunde(request, {"result": True, "message": _t(N_("Filmul pornește pe televizor."))})
			except Exception as e:
				print("[HdsWebControl] youtube-reda: %s" % e)
				return self._eroare(request, _t(N_("Eroare pe receptor.")), 500)

	class SetariResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, setari())
			except Exception as e:
				print("[HdsWebControl] youtube-setari: %s" % e)
				return self._eroare(request, _t(N_("Eroare pe receptor.")), 500)

		def render_POST(self, request):
			try:
				return self._raspunde(request, setari(dict((k, _arg(request, k.encode())) for k in ("calitate", "deschide", "tara", "aspect", "date_bara", "redare_auto", "urmeaza"))))
			except Exception as e:
				print("[HdsWebControl] youtube-setari: %s" % e)
				return self._eroare(request, _t(N_("Eroare pe receptor.")), 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina as pagina_comuna
			return pagina_comuna(request, pagina_text)

	return {b"youtube": ListeResource(), b"youtube-reda": RedaResource(), b"youtube-setari": SetariResource()}, PaginaResource()


def pagina_text(stil, config):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube</title>
<style>__STIL_COMUN__
#yt{width:100%;max-width:1200px;margin:0 auto;padding-bottom:24px;box-sizing:border-box;}
#yt *{box-sizing:border-box;min-width:0;}
h1{font-size:1.6rem;margin:0 0 6px;}
.intro{color:var(--text-slab);margin:0 0 14px;line-height:1.5;}
.bara{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px;}
button{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;
 padding:8px 14px;min-height:44px;cursor:pointer;}
button.ales{background:#c4302b;border-color:#c4302b;color:#fff;}
button:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px;}
form{display:flex;gap:8px;margin:0 0 12px;}
input[type=search]{flex:1;font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;padding:8px 12px;min-height:44px;}
.stare{padding:10px 14px;border:1px solid var(--bordura);border-radius:8px;background:var(--panou);margin:0 0 12px;}
.stare.rau{color:#ffb4ab;border-color:#a84d47;}
.raft{grid-column:1/-1;margin:14px 0 0;font-size:1rem;}
.cautari{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px;}
.cautari button{min-height:36px;padding:4px 10px;font-size:.9rem;}
#titlu{font-size:1.15rem;margin:0 0 10px;}
#lista{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px 12px;}
.card{background:transparent;border:0;display:flex;flex-direction:column;}
.card .poza{position:relative;display:block;width:100%;aspect-ratio:16/9;background:#141b30;border-radius:8px;overflow:hidden;
 padding:0;min-height:0;border:0;cursor:pointer;}
.card .poza:focus-visible{outline:4px solid #fff;outline-offset:2px;}
.card img{width:100%;height:100%;object-fit:cover;display:block;}
.card .canal-poza img{object-fit:contain;}
.durata{position:absolute;right:6px;bottom:6px;background:rgba(10,10,10,.85);color:#fff;border-radius:4px;padding:1px 6px;
 font-size:.8rem;font-weight:600;}
.durata.direct{background:#c4302b;text-transform:uppercase;}
.card .corp{padding:8px 2px 0;display:flex;flex-direction:column;gap:3px;flex:1;}
.card .nume{font-weight:600;line-height:1.3;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.card .mic{color:var(--text-slab);font-size:.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.card .butoane{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto;padding-top:6px;}
#mai{margin:14px auto 0;display:block;}
.setari{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0 0;padding-top:12px;border-top:1px solid var(--bordura);}
.setari label{display:flex;flex-direction:column;gap:4px;color:var(--text-slab);font-size:.9rem;}
.setari select{font:inherit;color:var(--text);background:var(--panou);border:1px solid var(--bordura);border-radius:8px;padding:8px;min-height:44px;}
[hidden]{display:none!important;}
</style>
</head>
<body>
<main id="yt">
<h1>YouTube</h1>
<p class="intro">Cauți aici și pornești filmul pe televizor. Fără cont.</p>
<div class="bara">
<button type="button" data-fel="acasa" class="ales">Acasă</button>
<button type="button" data-fel="muzica">Muzică</button>
<button type="button" data-fel="jocuri">Jocuri</button>
<button type="button" data-fel="stiri">Știri</button>
<button type="button" data-fel="sport">Sport</button>
<button type="button" data-fel="podcast">Podcasturi</button>
<button type="button" data-fel="live">În direct</button>
<button type="button" data-fel="cauta">Caută</button>
<button type="button" data-fel="vazute">Văzute</button>
</div>
<form id="forma" hidden><input type="search" id="q" placeholder="Ce cauți pe YouTube?" aria-label="Ce cauți pe YouTube?"><button type="submit">Caută</button></form>
<div class="cautari" id="cautari"></div>
<div class="stare" id="stare" role="status" aria-live="polite" hidden></div>
<h2 id="titlu"></h2>
<div id="lista"></div>
<button type="button" id="mai" hidden>Mai multe</button>
<div class="setari"><label>Calitatea<select id="calitate"></select></label><label>YouTube din Aplicații<select id="deschide"></select></label><label>Țara<select id="tara"></select></label><label>Aspect<select id="aspect"></select></label><label>Datele detaliate în bara de redare<select id="date_bara"></select></label><label>Redare automată<select id="redare_auto"></select></label><label>Anunțul clipului următor<select id="urmeaza"></select></label></div>
</main>
<script>
var CFG=__CONFIG__;
var FEL="acasa", CONT=null, CAPAT="browse", STIVA=[];
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
function buton(text,f){var b=document.createElement("button");b.type="button";b.textContent=text;b.addEventListener("click",f);return b;}
function card(e){
 if(e.fel==="raft"){var h=document.createElement("h3");h.className="raft";h.textContent=e.titlu;return h;}
 var c=document.createElement("div");c.className="card";
 var p=document.createElement("button");p.type="button";p.className="poza"+(e.fel==="canal"?" canal-poza":"");p.title=e.titlu;
 var src=e.fel==="film"&&e.id?"https://i.ytimg.com/vi/"+encodeURIComponent(e.id)+"/mqdefault.jpg":e.poza;
 if(src){var i=document.createElement("img");i.loading="lazy";i.alt="";i.src=src;p.appendChild(i);}
 if(e.live||((e.fel==="film"||e.fel==="lista")&&e.durata)){var d=document.createElement("span");d.className="durata"+(e.live?" direct":"");d.textContent=e.live?"în direct":e.durata;p.appendChild(d);}
 p.addEventListener("click",function(){if(e.fel==="film"){pePoza(e);}else if(e.fel==="canal"||e.fel==="lista"){deschide(e.fel,"",e.id,e.titlu);}});
 c.appendChild(p);
 var corp=document.createElement("div");corp.className="corp";
 var n=document.createElement("div");n.className="nume";n.title=e.titlu;
 n.appendChild(document.createTextNode((e.fel==="canal"?"Canal: ":e.fel==="lista"?"Listă: ":"")+e.titlu));
 corp.appendChild(n);
 var a=document.createElement("div");a.className="mic";a.textContent=e.autor||"";if(e.autor){corp.appendChild(a);}
 var m=document.createElement("div");m.className="mic";m.textContent=[e.vizionari,e.data].filter(Boolean).join("  ·  ");if(m.textContent){corp.appendChild(m);}
 var bs=document.createElement("div");bs.className="butoane";
 if(e.fel==="film"){
  bs.appendChild(buton("Pe televizor",function(){pePoza(e);}));
  bs.appendChild(buton("Asemănătoare",function(){deschide("inrudite","",e.id,"Asemănătoare: "+e.titlu);}));
 }
 if(e.fel==="canal"){bs.appendChild(buton("Deschide",function(){deschide("canal","",e.id,e.titlu);}));}
 if(e.fel==="lista"){bs.appendChild(buton("Deschide",function(){deschide("lista","",e.id,e.titlu);}));}
 if(e.fel==="film"&&e.autor_id){bs.appendChild(buton("Canalul",function(){deschide("canal","",e.autor_id,e.autor);}));}
 corp.appendChild(bs);c.appendChild(corp);return c;
}
async function pePoza(e){mesaj("Pornesc filmul pe televizor...",false);try{var d=await cere("/api/youtube-reda?id="+encodeURIComponent(e.id),true);mesaj(d.message||"Filmul pornește pe televizor.",false);}catch(x){mesaj(eroare(x),true);}}
function arata(d,titlu,adauga){
 var l=el("lista");if(!adauga){l.textContent="";}
 el("titlu").textContent=titlu||"";
 (d.elemente||[]).forEach(function(e){l.appendChild(card(e));});
 CONT=d.cont||null;CAPAT=d.capat||"browse";el("mai").hidden=!CONT;
 if(!adauga){mesaj((d.elemente||[]).length?"":(FEL==="cauta"||FEL==="live")&&!el("q").value?"":"Nu am găsit nimic aici.",false);}
 var cs=el("cautari");cs.textContent="";
 if(FEL==="cauta"){(d.cautari||[]).forEach(function(t){cs.appendChild(buton(t,function(){el("q").value=t;incarca("cauta",t);}));});}
}
async function incarca(fel,q,id,titlu){
 mesaj("Se încarcă...",false);
 try{var d=await cere("/api/youtube?fel="+fel+"&q="+encodeURIComponent(q||"")+"&id="+encodeURIComponent(id||""));arata(d,titlu||(q?"Caută: "+q:""));}
 catch(e){mesaj(eroare(e),true);}
}
function deschide(fel,q,id,titlu){incarca(fel,q,id,titlu);}
document.querySelectorAll(".bara button").forEach(function(b){b.addEventListener("click",function(){
 FEL=b.getAttribute("data-fel");
 document.querySelectorAll(".bara button").forEach(function(x){x.className=x===b?"ales":"";});
 el("forma").hidden=!(FEL==="cauta"||FEL==="live");
 if(FEL!=="cauta"&&FEL!=="live"){el("q").value="";}
 el("lista").textContent="";el("titlu").textContent="";el("mai").hidden=true;
 if(FEL==="cauta"||FEL==="live"){el("q").focus();}
 incarca(FEL,el("q").value,"",b.textContent);
});});
el("forma").addEventListener("submit",function(ev){ev.preventDefault();var q=el("q").value.trim();if(q){incarca(FEL,q);}});
el("mai").addEventListener("click",async function(){
 if(!CONT){return;}
 try{var d=await cere("/api/youtube?cont="+encodeURIComponent(CONT)+"&capat="+CAPAT);arata(d,el("titlu").textContent,true);}catch(e){mesaj(eroare(e),true);}
});
function setari(d){["calitate","deschide","tara","aspect","date_bara","redare_auto","urmeaza"].forEach(function(k){if(!d.setari[k]){return;}var s=el(k);s.textContent="";d.setari[k].alegeri.forEach(function(a){var o=document.createElement("option");o.value=a[0];o.textContent=a[1];o.selected=a[0]===d.setari[k].valoare;s.appendChild(o);});});}
["calitate","deschide","tara","aspect","date_bara","redare_auto","urmeaza"].forEach(function(k){el(k).addEventListener("change",async function(){try{setari(await cere("/api/youtube-setari?"+k+"="+encodeURIComponent(el(k).value),true));mesaj("Setarea s-a salvat.",false);}catch(e){mesaj(eroare(e),true);}});});
cere("/api/youtube-setari").then(setari).catch(function(){});
incarca("acasa","","","Acasă");
</script>
</body>
</html>"""


TEXTE_PAGINA = {"html": (
	N_("YouTube"),
	N_("Cauți aici și pornești filmul pe televizor. Fără cont."),
	N_("Acasă"), N_("Caută"), N_("În direct"), N_("Văzute"), N_("Ce cauți pe YouTube?"), N_("Mai multe"),
	N_("Calitatea"), N_("YouTube din Aplicații"), N_("Muzică"), N_("Jocuri"), N_("Știri"), N_("Sport"),
	N_("Podcasturi"), N_("Țara"), N_("Aspect"), N_("Datele detaliate în bara de redare"), N_("Redare automată"), N_("Anunțul clipului următor"),
	), "js": (
	N_("Receptorul a răspuns neașteptat."), N_("Nu am putut termina. Încearcă din nou."),
	N_("Receptorul nu răspunde. Verifică legătura și încearcă din nou."),
	N_("în direct"), N_("Canal: "), N_("Listă: "), N_("Pe televizor"), N_("Pornesc filmul pe televizor..."),
	N_("Filmul pornește pe televizor."), N_("Asemănătoare"), N_("Asemănătoare: "), N_("Deschide"), N_("Canalul"),
	N_("Nu am găsit nimic aici."), N_("Se încarcă..."), N_("Caută: "),N_("Setarea s-a salvat."),
)}


def _traducePagina(sablon, fel="pagina"):
	"""the template in the receiver's language; without the HdsWebControl package (PC tests), as it is"""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

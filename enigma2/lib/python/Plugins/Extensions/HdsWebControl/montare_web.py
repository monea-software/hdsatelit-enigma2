# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
#
# montare_web.py: pagina /montare-discuri, perechea ecranului „Montarea discurilor” de pe televizor
# (Screens/HdsMontareDiscuri.py). Aceeasi logica (Components/HdsMontareDiscuri.py): locul fiecarui disc in /media (hdd,
# usb, usb2.., mmc, eticheta; ramane si dupa repornire), demontarea ca sa-l scoti in siguranta si montarea la loc.
#   GET  /api/montare-discuri                                           discurile si lucrarea de acum
#   POST /api/montare-discuri-lucru?disc=<sdb1>&fel=loc&nume=<usb|gol>  locul ales, aplicat pe loc
#   POST /api/montare-discuri-lucru?disc=<sdb1>&fel=demontare|montare
# Fara confirmare (nimic nu se pierde); refuzul (o inregistrare sau timeshift-ul scrie pe disc, swap pornit pe el) vine
# cu motivul, ca pe televizor. Citirea discurilor merge pe un fir, cu termen (HdsStocareDisc.cere); pagina intreaba din
# nou cat asteapta. Fisierul nu importa nimic din enigma2 la incarcare (probele de pe PC dau modulul M).
# 0.7.8 (MDP): discul de pe care porneste imaginea vine fara alegeri si fara butoane, cu nota lui (M.notaRand): de ce ramane
# montat si unde se salveaza inregistrarile; locul si demontarea lui se refuza in M.porneste, ca pe televizor.

TERMEN_CITIRE_S = 3
MAX_DISC = 40
MAX_NUME = 40


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def N_(text):
	return text


def _c():
	from . import meniu_comun_web
	return meniu_comun_web


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsMontareDiscuri
	return HdsMontareDiscuri


def _lucru(M):
	l = M.stareLucru()
	if l is None:
		return None
	return {"fel": l["fel"], "disc": l["dispozitiv"], "stare": l["stare"], "text": l["mesaj"]}


CHEIE_CITIRE = ("montare-discuri-web",)


def stare(M=None, cere=None, citireTerminata=None):
	"""GET /api/montare-discuri: {"result", "discuri": [...], "asteapta", "lucru"}."""
	M = _m(M)
	if cere is None:
		from Components.HdsStocareDisc import cere, stare as citireTerminata
	elif citireTerminata is None:
		citireTerminata = lambda cheie: None
	# 0.7.7 (DRG, darog69, Vu+ Duo4K, forum 789 #2619): rezultatul citirii se tine 1 s, iar pagina intreaba din nou dupa
	# 0,7 s; pe un receptor ocupat a doua intrebare venea dupa ce rezultatul expirase, pornea o citire noua si pagina ramanea
	# la "Se citesc discurile...". Citirea terminata intre doua intrebari se ia acum inainte sa porneasca alta.
	terminata = citireTerminata(CHEIE_CITIRE)
	rez = cere(CHEIE_CITIRE, M.lista, termen=TERMEN_CITIRE_S, varsta=1)
	if rez["stare"] == "asteapta" and terminata is not None and terminata.get("stare") == "gata":
		rez = terminata
	date = {"result": True, "discuri": [], "asteapta": False, "lucru": _lucru(M)}
	if rez["stare"] == "asteapta":
		date["asteapta"] = True
	elif rez["stare"] != "gata":
		date.update(result=False, message=_t("Discul nu răspunde la timp. Încearcă din nou."))
	else:
		repara = getattr(M, "reparaNecunoscute", None)
		if repara is not None:
			# discurile montate pe care managerul nu le stie intra din nou in lista lui (pe firul interfetei)
			repara(rez["valoare"] or [])
		nota = getattr(M, "notaRand", None)
		for r in rez["valoare"] or []:
			date["discuri"].append(dict(r, text_stare=M.textStare(r), nota=nota(r) if nota is not None else ""))
	return date


def lucru(argumente, M=None):
	"""POST /api/montare-discuri-lucru: aceeasi lucrare ca pe televizor."""
	M = _m(M)
	fel = argumente.get("fel", "")
	disc = argumente.get("disc", "")
	nume = argumente.get("nume") if fel == M.LOC else None
	if fel == M.LOC and nume is None:
		return {"result": False, "message": _t("Alege un nume din listă."), "lucru": _lucru(M)}
	bun, mesaj = M.porneste(fel, disc, nume)
	return {"result": bool(bun), "message": mesaj, "lucru": _lucru(M)}


def argumente(request):
	C = _c()
	rez = C.argumente(request, ("disc", "fel"), MAX_DISC)
	rez.update(C.argumente(request, ("nume",), MAX_NUME))
	return rez


def rute(baza, resource, M=None):
	"""({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class Stare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class Lucru(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, lucru(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return _c().pagina(request, pagina)

	api = {
		b"montare-discuri": Stare(),
		b"montare-discuri-lucru": Lucru(),
	}
	return api, Pagina()


def pagina(stil, config_pagina):
	C = _c()
	return C.sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": C.drumHtml("hds_montare_discuri")})


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Montarea discurilor</title>
<style>__STIL_COMUN__ __STIL_PAGINI__
  main{max-width:820px;margin:0 auto;}
  .disc{border-bottom:1px solid var(--bordura);padding:10px 0;}
  .disc:last-child{border-bottom:0;}
  .disc .nume{font-weight:600;overflow-wrap:anywhere;}
  .disc .mic{color:var(--text-slab);font-size:.85rem;overflow-wrap:anywhere;}
  .disc .camp{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}
  .disc select{flex:1 1 180px;min-width:0;min-height:44px;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Montarea discurilor</h1>
<p class="mesaj" id="incarcare">Se citesc discurile...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Stick-urile, hard diskurile și cardurile</h2>
    <p class="nota" id="gol">Niciun hard disk și niciun stick USB găsit.</p>
    <div id="discuri"></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Locul ales se aplică pe loc și rămâne și după repornire. Dosarele înregistrărilor și locul ghidului TV merg după disc. Un disc demontat se poate scoate în siguranță; dacă nu-l scoți, rămâne demontat până la „Montează la loc” sau până la repornire.</p>
  <p class="nota">Același ecran este pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var CEAS = null, SEMN = null;
function programeaza(f, ms){ if(CEAS){ clearTimeout(CEAS); } CEAS = setTimeout(f, ms); }
function trimite(k, fel, nume){
  var q = new URLSearchParams(); q.set("disc", k.dispozitiv); q.set("fel", fel);
  if(nume !== null){ q.set("nume", nume); }
  mesaj("Se lucrează...");
  cerere("/api/montare-discuri-lucru", "POST", q).then(function(d){ mesaj(d.message, !d.result); SEMN = null; citeste(); }).catch(nimicNuRaspunde);
}
function buton(text, apasat){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text; b.addEventListener("click", apasat); return b;
}
function disc(k, ocupat){
  var div = document.createElement("div"); div.className = "disc";
  var n = document.createElement("div"); n.className = "nume"; n.textContent = k.nume + (k.marime ? "  " + k.marime : ""); div.appendChild(n);
  var m = document.createElement("div"); m.className = "mic"; m.textContent = (k.loc && k.loc_afisat ? k.text_stare.replace(k.loc, k.loc_afisat) : k.text_stare) + (k.sistem ? " (" + k.sistem + ")" : ""); div.appendChild(m);
  if(k.nota){ var o = document.createElement("div"); o.className = "mic"; o.textContent = k.nota; div.appendChild(o); }
  var camp = document.createElement("div"); camp.className = "camp";
  if(k.alegeri.length){
    var s = document.createElement("select"); s.setAttribute("aria-label", "Locul de montare");
    k.alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[0] ? a[1] : "Automat (primul nume liber)"; s.appendChild(o); });
    s.value = k.ales; s.disabled = ocupat;
    s.addEventListener("change", function(){ trimite(k, "loc", s.value); });
    camp.appendChild(s);
  }
  if(k.poate_demonta){ var b = buton("Demontează", function(){ trimite(k, "demontare", null); }); b.disabled = ocupat; camp.appendChild(b); }
  if(k.poate_monta){ var c = buton("Montează la loc", function(){ trimite(k, "montare", null); }); c.disabled = ocupat; camp.appendChild(c); }
  div.appendChild(camp);
  return div;
}
function arata(d){
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var ocupat = !!(d.lucru && d.lucru.stare === "in_lucru");
  if(ocupat){ mesaj(d.lucru.text); }
  var semn = JSON.stringify([d.discuri, ocupat]);
  if(semn !== SEMN){
    SEMN = semn;
    var c = $("discuri"); c.textContent = "";
    d.discuri.forEach(function(k){ c.appendChild(disc(k, ocupat)); });
    $("gol").classList.toggle("ascuns", d.discuri.length > 0);
  }
  if(!ocupat && d.lucru && SEMN_LUCRU !== d.lucru.text){ SEMN_LUCRU = d.lucru.text; mesaj(d.lucru.text, d.lucru.stare === "eroare"); }
  programeaza(citeste, ocupat ? 1000 : 4000);
}
var SEMN_LUCRU = null;
function citeste(){
  if(document.hidden){ programeaza(citeste, 4000); return; }
  cerere("/api/montare-discuri").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi discurile."; programeaza(citeste, 5000); return; }
    if(d.asteapta){ programeaza(citeste, 700); return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; programeaza(citeste, 10000); });
}
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginii
TEXTE_PAGINA = {
	"html": (
		N_("Montarea discurilor"),
		N_("Se citesc discurile..."),
		N_("Stick-urile, hard diskurile și cardurile"),
		N_("Niciun hard disk și niciun stick USB găsit."),
		N_("Locul ales se aplică pe loc și rămâne și după repornire. Dosarele înregistrărilor și locul ghidului TV merg "
			"după disc. Un disc demontat se poate scoate în siguranță; dacă nu-l scoți, rămâne demontat până la „Montează "
			"la loc” sau până la repornire."),
		N_("Același ecran este pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Se lucrează..."),
		N_("Locul de montare"),
		N_("Automat (primul nume liber)"),
		N_("Demontează"),
		N_("Montează la loc"),
		N_("Receptorul nu a putut citi discurile."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

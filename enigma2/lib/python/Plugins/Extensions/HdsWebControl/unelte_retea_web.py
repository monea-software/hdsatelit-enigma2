# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# unelte_retea_web.py: perechea web a utilitarelor de retea de pe televizor (din 0.4.4), Meniu > Setari > Retea si
# Internet:
#   /wifi-canale     "Cat de aglomerat e Wi-Fi-ul" (Components/HdsWifiCanale.py; pe televizor HdsWifiCanaleScreen)
#   /aparate-retea   "Ce aparate sunt in retea" (Components/HdsAparateRetea.py; pe televizor HdsAparateReteaScreen)
# plus starea trecerii singure pe alta retea (Components/HdsComutareRetea.py), pentru cardul din /retea. Setarile
# trecerii se schimba prin pagina generica a setarilor (/setari?id=hds_retea_comutare), ca pe televizor.
# O SINGURA LOGICA: aceleasi module ca pe televizor; ultimul rezultat se vede si aici si pe televizor.
#
# Rute (poarta comuna a HdsJsonResource; cautarile pornesc numai cu POST, cookie, aceeasi origine si antetul CSRF,
# fiindca trimit pachete in retea):
#   GET  /api/wifi-canale                    placile Wi-Fi, cautarea in curs, ultimul rezultat (canalele 1-13, retelele,
#                                            canalul recomandat si explicatia)
#   POST /api/wifi-canale-cauta?placa=       porneste o cautare
#   GET  /api/aparate-retea                  cautarea in curs sau ultimul rezultat (aparatele, reteaua)
#   POST /api/aparate-retea-cauta            porneste o cautare (cel mult una la 10 s)
#   GET  /api/comutare-retea                 trecerea pe alta retea: pornita, caile in ordine, pe ce cale e acum
#   GET  /wifi-canale, GET /aparate-retea    paginile
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC pun in DEP modulele lor.

DEP = {}
_STARE = {"wifi": None}


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def _t(text):
	return _mc()._t(text)


def _dep(nume):
	if nume in DEP:
		return DEP[nume]
	if nume == "HdsWifiCanale":
		from Components import HdsWifiCanale
		return HdsWifiCanale
	if nume == "HdsAparateRetea":
		from Components import HdsAparateRetea
		return HdsAparateRetea
	if nume == "HdsComutareRetea":
		from Components import HdsComutareRetea
		return HdsComutareRetea
	raise KeyError(nume)


# ------------------------------------------------------------------ Wi-Fi

def stareWifi(request=None):
	W = _dep("HdsWifiCanale")
	x = _STARE["wifi"]
	return {"result": True, "placi": W.placi_wifi(), "lucreaza": bool(x and x["lucreaza"]),
		"mesaj": (x or {}).get("mesaj", ""), "rezultat": W.ultima()}


def cautaWifi(request):
	W = _dep("HdsWifiCanale")
	placi = W.placi_wifi()
	if not placi:
		return {"result": False, "message": _t("Receptorul nu are o placă Wi-Fi. Pune una în portul USB.")}
	placa = _mc().argumente(request, ("placa",), 20).get("placa") or placi[0]
	if placa not in placi:
		return {"result": False, "message": _t("Placa %s nu e o placă Wi-Fi.") % placa[:20]}
	vechi = _STARE["wifi"]
	if vechi is not None and vechi["lucreaza"]:
		return {"result": False, "message": _t("O căutare e deja în curs.")}
	x = {"lucreaza": True, "mesaj": _t("Se caută rețelele Wi-Fi...")}
	_STARE["wifi"] = x

	def gata(rez):
		x["lucreaza"] = False
		x["mesaj"] = "" if rez.get("stare") == "gata" else rez.get("mesaj", "")
	c = W.Cautare(placa, gata)
	x["obiect"] = c
	c.porneste()
	return {"result": True, "message": x["mesaj"]}


# ------------------------------------------------------------------ aparatele

def stareAparate(request=None):
	A = _dep("HdsAparateRetea")
	st = A.rezultat()
	for a in st.get("aparate", []):
		a["eticheta_text"] = A.text_eticheta(a.get("eticheta", ""))
	st["result"] = True
	return st


def cautaAparate(request):
	A = _dep("HdsAparateRetea")
	ok, motiv = A.porneste()
	return {"result": bool(ok), "message": motiv or _t("Se caută aparatele din rețea...")}


# ------------------------------------------------------------------ trecerea pe alta retea

def stareComutare(request=None):
	try:
		st = _dep("HdsComutareRetea").stare()
	except Exception as eroare:
		_mc().jurnal("comutare: %r" % eroare)
		st = {"pornita": False, "cai": [], "mod": "normal", "fara_alternative": True}
	st["result"] = True
	return st


# ------------------------------------------------------------------ rutele si paginile

def rute(baza, resource):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	def _eroare(self, request, eroare):
		_mc().jurnal("unelte retea: %r" % eroare)
		return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def _citire(functie):
		class Citire(baza):
			def render_GET(self, request):
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					return _eroare(self, request, eroare)
		return Citire()

	def _scriere(functie):
		class Scriere(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					return _eroare(self, request, eroare)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Scriere()

	def _pagina(text):
		class Pagina(resource.Resource):
			isLeaf = True

			def render_GET(self, request):
				return _mc().pagina(request, text)
		return Pagina()

	api = {
		b"wifi-canale": _citire(stareWifi),
		b"wifi-canale-cauta": _scriere(cautaWifi),
		b"aparate-retea": _citire(stareAparate),
		b"aparate-retea-cauta": _scriere(cautaAparate),
		b"comutare-retea": _citire(stareComutare),
	}
	return api, {b"wifi-canale": _pagina(pagina_wifi), b"aparate-retea": _pagina(pagina_aparate)}


def pagina_wifi(stil, config_pagina):
	mc = _mc()
	return mc.sablon(_traducePagina(PAGINA_WIFI), stil, config_pagina,
		{"__DRUM_MENIU__": mc.drumHtml("hds_wifi_canale")})


def pagina_aparate(stil, config_pagina):
	mc = _mc()
	return mc.sablon(_traducePagina(PAGINA_APARATE), stil, config_pagina,
		{"__DRUM_MENIU__": mc.drumHtml("hds_aparate_retea")})


PAGINA_WIFI = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cât de aglomerat e Wi-Fi-ul</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .grafic{display:grid;grid-template-columns:repeat(13,minmax(0,1fr));gap:6px;align-items:end;margin:6px 0 4px;}
  .coloana{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0;}
  .eticheta-sus{font-size:.7rem;min-height:1.1em;color:var(--accent);text-align:center;white-space:nowrap;}
  .pista{position:relative;width:100%;max-width:42px;height:200px;background:var(--bordura);border-radius:4px;overflow:hidden;}
  .umplere{position:absolute;left:0;right:0;bottom:0;border-radius:4px;}
  .liber{background:#4FD18B;} .aglomerat{background:#F1C40F;} .foarte_aglomerat{background:#FF6B5E;}
  .coloana.recomandat .pista{outline:3px solid #4FD18B;outline-offset:2px;}
  .coloana.recomandat .eticheta-sus,.coloana.recomandat .nr{color:#4FD18B;font-weight:600;}
  .nr{font-weight:600;font-size:1.05rem;} .cate{font-size:.8rem;color:var(--text-slab);}
  .legenda{display:flex;flex-wrap:wrap;gap:14px;font-size:.85rem;color:var(--text-slab);margin-top:8px;}
  .legenda span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;}
  .legenda .l1::before{background:#4FD18B;} .legenda .l2::before{background:#F1C40F;} .legenda .l3::before{background:#FF6B5E;}
  .canal-mare{font-size:2.2rem;font-weight:700;color:#4FD18B;margin:4px 0 8px;}
  .fraze p{margin:0 0 8px;line-height:1.45;}
  .retele td:last-child{white-space:nowrap;}
  @media (max-width:560px){ .grafic{gap:3px;} .pista{height:150px;} .eticheta-sus{font-size:.6rem;} .nr{font-size:.85rem;} }
</style>
</head>
<body>
<main>
<h1>Cât de aglomerat e Wi-Fi-ul</h1>
<p class="nota" id="sub">Se citește...</p>
<section class="card">
  <h2>Canalele de 2,4 GHz</h2>
  <div class="rand ascuns" id="randPlaca"><label for="placa">Placa Wi-Fi</label><select id="placa"></select></div>
  <div class="grafic" id="grafic"></div>
  <div class="legenda"><span class="l1">liber</span><span class="l2">aglomerat</span><span class="l3">foarte aglomerat</span></div>
  <p class="nota">Sub fiecare canal: câte rețele sunt chiar pe el. Înălțimea barei arată cât e de încărcat, cu rețelele de pe canalele vecine (un canal se suprapune cu câte 4 de fiecare parte) și cu cât de tare e semnalul lor. Rețeaua ta nu intră în socoteală.</p>
  <div class="butoane"><button type="button" class="principal" id="cauta">Caută din nou</button></div>
</section>
<section class="card ascuns" id="cardRecomandare">
  <h2>Recomandare</h2>
  <div class="canal-mare" id="canalMare"></div>
  <div class="fraze" id="fraze"></div>
</section>
<section class="card ascuns" id="cardRetele">
  <h2>Rețelele găsite</h2>
  <table class="retele"><thead><tr><th>Rețeaua</th><th>Canalul</th><th>Semnalul</th></tr></thead><tbody id="retele"></tbody></table>
</section>
<p class="mesaj" id="mesaj"></p>
<p class="nota">Același utilitar e pe televizor, în __DRUM_MENIU__. Placa Wi-Fi a receptorului recepționează numai rețelele de 2,4 GHz. Căutarea e aceeași ca la lista rețelelor Wi-Fi: nu trimite nimic altceva.</p>
</main>
<script>
__SCRIPT_COMUN__
var D = null, PLACA = null;
function scrie(el, t){ el.textContent = (t === null || t === undefined) ? "" : String(t); }
function el(tag, clasa, text){ var e = document.createElement(tag); if(clasa){ e.className = clasa; } if(text !== undefined){ scrie(e, text); } return e; }
function arata(){
  var r = D.rezultat;
  var s = $("placa");
  if(D.placi.length > 1 && !s.options.length){ D.placi.forEach(function(p){ var o = el("option", "", p); o.value = p; s.appendChild(o); }); }
  $("randPlaca").classList.toggle("ascuns", D.placi.length < 2);
  if(!D.placi.length){ scrie($("sub"), "Receptorul nu are o placă Wi-Fi. Pune una în portul USB."); $("cauta").disabled = true; return; }
  $("cauta").disabled = D.lucreaza;
  scrie($("cauta"), D.lucreaza ? "Se caută..." : "Caută din nou");
  if(!r){ scrie($("sub"), D.lucreaza ? "Se caută rețelele Wi-Fi..." : (D.mesaj || "Nicio căutare încă.")); return; }
  scrie($("sub"), "Rețele găsite pe 2,4 GHz: " + r.numar + (D.lucreaza ? " · se caută din nou..." : "") + (D.mesaj ? " · " + D.mesaj : ""));
  var g = $("grafic"); g.textContent = "";
  r.canale.forEach(function(c){
    var k = el("div", "coloana" + (c.recomandat ? " recomandat" : ""));
    k.appendChild(el("div", "eticheta-sus", c.recomandat ? "recomandat" : (c.al_meu ? "routerul tău" : "")));
    var p = el("div", "pista"); p.title = "Canalul " + c.canal + ": " + c.nivel_text + ", " + c.retele + " rețele pe el";
    var u = el("div", "umplere " + c.nivel); u.style.height = Math.max(2, c.procent) + "%"; p.appendChild(u); k.appendChild(p);
    k.appendChild(el("div", "nr", c.canal)); k.appendChild(el("div", "cate", c.retele));
    g.appendChild(k);
  });
  $("cardRecomandare").classList.remove("ascuns");
  scrie($("canalMare"), "Canalul " + r.recomandat);
  var f = $("fraze"); f.textContent = ""; r.explicatie.forEach(function(t){ f.appendChild(el("p", "", t)); });
  var tb = $("retele"); tb.textContent = "";
  r.retele.forEach(function(n){
    var tr = el("tr");
    tr.appendChild(el("td", "", n.nume + (n.a_mea ? " (a ta)" : "")));
    tr.appendChild(el("td", "", n.canal ? n.canal : (n.banda ? n.banda + " GHz" : "")));
    tr.appendChild(el("td", "", n.semnal + (n.dbm !== null ? " (" + n.dbm + " dBm)" : "")));
    tb.appendChild(tr);
  });
  $("cardRetele").classList.toggle("ascuns", !r.retele.length);
}
function citeste(){
  return cerere("/api/wifi-canale").then(function(d){ if(!d.result){ mesaj(d.message, true); return; } D = d; arata(); }).catch(nimicNuRaspunde);
}
function cauta(){
  var q = new URLSearchParams(); if($("placa").value){ q.set("placa", $("placa").value); }
  cerere("/api/wifi-canale-cauta", "POST", q).then(function(d){ if(!d.result){ mesaj(d.message, true); } citeste(); }).catch(nimicNuRaspunde);
}
$("cauta").addEventListener("click", cauta);
citeste().then(function(){ if(D && D.placi.length && !D.lucreaza){ cauta(); } });
setInterval(function(){ if(!document.hidden && D && D.lucreaza){ citeste(); } }, 2000);
</script>
</body>
</html>
"""


PAGINA_APARATE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ce aparate sunt în rețea</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .aparate td,.aparate th{overflow-wrap:anywhere;}
  .aparate .mic{display:block;font-size:.8rem;color:var(--text-slab);}
  .aparate .eticheta{display:inline-block;font-size:.72rem;padding:1px 8px;border-radius:999px;border:1px solid var(--accent);color:var(--accent);margin-left:6px;}
  @media (max-width:560px){
    .aparate thead{display:none;}
    .aparate tr{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:8px 0;border-bottom:1px solid var(--bordura);}
    main .card table.aparate tr td{border:0;padding:2px 0;}
    .aparate td:nth-child(1),.aparate td:nth-child(3){grid-column:1;}
    .aparate td:nth-child(2){grid-column:2;grid-row:1;}
    .aparate td:nth-child(3){color:var(--text-slab);font-size:.85rem;}
  }
</style>
</head>
<body>
<main>
<h1>Ce aparate sunt în rețea</h1>
<p class="nota" id="sub">Se citește...</p>
<section class="card">
  <div class="butoane">
    <button type="button" class="principal" id="cauta">Caută din nou</button>
    <button type="button" id="ordine">Ordinea: după nume</button>
  </div>
  <table class="aparate ascuns" id="tabel"><thead><tr><th>Numele</th><th>Adresa IP</th><th>Producătorul și adresa MAC</th></tr></thead><tbody id="aparate"></tbody></table>
</section>
<section class="card">
  <h2>Cum se află</h2>
  <p class="nota">Din tabela de vecini a receptorului și o întrebare scurtă trimisă fiecărei adrese din rețeaua ta (fără căutări de porturi). Numele vin din răspunsurile aparatelor (mDNS, NetBIOS) și de la router, producătorul din lista publică a adreselor MAC (lista Wireshark, licența GPL-2.0-or-later, în Licențe). Nimic nu pleacă în afara rețelei tale. Telefoanele adormite pot lipsi: caută din nou peste un minut. Adresa aleatoare e adresa privată pe care și-o aleg singure telefoanele și tabletele noi.</p>
</section>
<p class="mesaj" id="mesaj"></p>
<p class="nota">Același utilitar e pe televizor, în __DRUM_MENIU__.</p>
</main>
<script>
__SCRIPT_COMUN__
var D = null, DUPA_NUME = false;
function scrie(el, t){ el.textContent = (t === null || t === undefined) ? "" : String(t); }
function el(tag, clasa, text){ var e = document.createElement(tag); if(clasa){ e.className = clasa; } if(text !== undefined){ scrie(e, text); } return e; }
function numar(ip){ return ip.split(".").reduce(function(a, b){ return a * 256 + Number(b); }, 0); }
function arata(){
  $("cauta").disabled = D.stare === "lucreaza";
  scrie($("cauta"), D.stare === "lucreaza" ? "Se caută..." : "Caută din nou");
  if(D.stare === "lucreaza"){ scrie($("sub"), D.faza || "Se caută aparatele din rețea..."); return; }
  if(D.stare === "eroare"){ scrie($("sub"), D.mesaj); return; }
  if(D.stare !== "gata"){ scrie($("sub"), "Nicio căutare încă."); return; }
  scrie($("sub"), D.mesaj ? D.mesaj : ("Rețeaua " + D.retea + " · " + D.aparate.length + " aparate găsite · nimic nu pleacă în afara rețelei tale"));
  var ap = D.aparate.slice();
  if(DUPA_NUME){ ap.sort(function(a, b){ return (a.nume || "~").toLowerCase().localeCompare((b.nume || "~").toLowerCase()) || numar(a.ip) - numar(b.ip); }); }
  var tb = $("aparate"); tb.textContent = "";
  ap.forEach(function(a){
    var tr = el("tr");
    var t1 = el("td"); t1.appendChild(el("span", "", a.nume || "fără nume")); if(a.eticheta_text){ t1.appendChild(el("span", "eticheta", a.eticheta_text)); } tr.appendChild(t1);
    tr.appendChild(el("td", "", a.ip));
    var t3 = el("td"); t3.appendChild(el("span", "", a.producator)); t3.appendChild(el("span", "mic", (a.mac || "").toUpperCase())); tr.appendChild(t3);
    tb.appendChild(tr);
  });
  $("tabel").classList.toggle("ascuns", !ap.length);
}
function citeste(){
  return cerere("/api/aparate-retea").then(function(d){ if(!d.result){ mesaj(d.message, true); return; } D = d; arata(); }).catch(nimicNuRaspunde);
}
function cauta(){
  cerere("/api/aparate-retea-cauta", "POST", new URLSearchParams()).then(function(d){ if(!d.result){ mesaj(d.message, true); } citeste(); }).catch(nimicNuRaspunde);
}
$("cauta").addEventListener("click", cauta);
$("ordine").addEventListener("click", function(){ DUPA_NUME = !DUPA_NUME; scrie($("ordine"), DUPA_NUME ? "Ordinea: după adresă" : "Ordinea: după nume"); if(D){ arata(); } });
citeste().then(function(){ if(D && D.stare !== "lucreaza" && D.stare !== "gata"){ cauta(); } });
setInterval(function(){ if(!document.hidden && D && D.stare === "lucreaza"){ citeste(); } }, 1000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Cât de aglomerat e Wi-Fi-ul"),
		N_("Se citește..."),
		N_("Canalele de 2,4 GHz"),
		N_("Placa Wi-Fi"),
		N_("liber"),
		N_("aglomerat"),
		N_("foarte aglomerat"),
		N_("Sub fiecare canal: câte rețele sunt chiar pe el. Înălțimea barei arată cât e de încărcat, cu "
			"rețelele de pe canalele vecine (un canal se suprapune cu câte 4 de fiecare parte) și cu cât de "
			"tare e semnalul lor. Rețeaua ta nu intră în socoteală."),
		N_("Caută din nou"),
		N_("Recomandare"),
		N_("Rețelele găsite"),
		N_("Rețeaua"),
		N_("Canalul"),
		N_("Semnalul"),
		N_("Același utilitar e pe televizor, în __DRUM_MENIU__. Placa Wi-Fi a receptorului recepționează "
			"numai rețelele de 2,4 GHz. Căutarea e aceeași ca la lista rețelelor Wi-Fi: nu trimite nimic "
			"altceva."),
		N_("Ce aparate sunt în rețea"),
		N_("Ordinea: după nume"),
		N_("Numele"),
		N_("Adresa IP"),
		N_("Producătorul și adresa MAC"),
		N_("Cum se află"),
		N_("Din tabela de vecini a receptorului și o întrebare scurtă trimisă fiecărei adrese din rețeaua "
			"ta (fără căutări de porturi). Numele vin din răspunsurile aparatelor (mDNS, NetBIOS) și de la "
			"router, producătorul din lista publică a adreselor MAC (lista Wireshark, licența "
			"GPL-2.0-or-later, în Licențe). Nimic nu pleacă în afara rețelei tale. Telefoanele adormite pot "
			"lipsi: caută din nou peste un minut. Adresa aleatoare e adresa privată pe care și-o aleg "
			"singure telefoanele și tabletele noi."),
		N_("Același utilitar e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Receptorul nu are o placă Wi-Fi. Pune una în portul USB."),
		N_("Se caută..."),
		N_("Caută din nou"),
		N_("Se caută rețelele Wi-Fi..."),
		N_("Nicio căutare încă."),
		N_("Rețele găsite pe 2,4 GHz:"),
		N_("· se caută din nou..."),
		N_("routerul tău"),
		N_("Canalul"),
		N_("rețele pe el"),
		N_("(a ta)"),
		N_("Se caută aparatele din rețea..."),
		N_("Rețeaua"),
		N_("aparate găsite · nimic nu pleacă în afara rețelei tale"),
		N_("fără nume"),
		N_("Ordinea: după adresă"),
		N_("Ordinea: după nume"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor

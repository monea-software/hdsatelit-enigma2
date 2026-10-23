# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# stocare_web.py: „Locul înregistrărilor” in interfata web (HdsWebControl).
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor: ecranul Screens/HdsLocInregistrari.py
# (din meniu si de la tasta rosie, cand nu e unde sa se inregistreze). Aici: locul de acum al inregistrarilor, spatiul
# liber, discurile conectate (cu starea fiecaruia), cele pe care receptorul nu le poate citi si butonul „Folosește
# pentru înregistrări” pentru fiecare disc bun. Ca pe televizor, cand locul nu e bun: discul pe care receptorul il va
# alege singur la prima inregistrare („automat”) sau intrebarea, cand sunt mai multe discuri si niciunul tinut minte
# (Components/HdsLocInregistrari.decizie). Alegerea facuta aici se tine minte la fel.
#
# O SINGURA LOGICA: discurile, citirea lor pe un fir, pregatirea discului ales (dosarul movie, fara formatare) si
# setarile sunt in Components/HdsLocInregistrari.py; textele sunt aceleasi ca pe televizor (texte(), textLucru()).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/stocare                         locul inregistrarilor, discurile, citirea si pregatirea in curs
#   POST /api/stocare-foloseste?punct=/media/usb   foloseste discul pentru inregistrari (numai un disc din lista)
#   GET  /stocare                             pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; aici se citesc numai /proc/mounts si /sys, spatiul liber
# se citeste pe un fir (Components/HdsLocInregistrari.cereStare), iar pagina intreaba din nou cat timp citirea sau
# pregatirea e in curs. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (L).

import time

MAX_PUNCT = 120
# cat timp (secunde de la pornire) se arata in pagina rezultatul ultimei pregatiri
VARSTA_LUCRU = 300


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _l(L=None):
	if L is not None:
		return L
	from Components import HdsLocInregistrari
	return HdsLocInregistrari


def _disc(L, d, automat=None):
	"""Un disc pentru pagina, cu marimile scrise ca pe televizor. `automat`: discul pe care receptorul il alege singur
	la prima inregistrare."""
	bun = d.get("bun")
	if bun is False:
		stare = L.textMotivDisc(d.get("motiv"))
	elif d.get("folosit"):
		stare = _t("aici se salvează înregistrările")
	elif automat and d["punct"] == automat:
		stare = _t("aici se vor salva")
	elif bun is None:
		stare = _t("se citește")
	else:
		stare = _t("se poate folosi")
	return {
		"punct": d["punct"],
		"nume": d["nume"],
		"dispozitiv": d.get("dispozitiv") or "",
		"fel": d.get("fel") or "",
		"bun": bun,
		"folosit": bool(d.get("folosit")),
		"automat": bool(automat) and d["punct"] == automat,
		"are_movie": d.get("are_movie"),
		"liber": d.get("liber"),
		"total": d.get("total"),
		"liber_text": L.marime(d.get("liber")),
		"total_text": L.marime(d.get("total")),
		"stare": stare,
	}


def stare(L=None, acum=None):
	"""Pentru GET /api/stocare. Culege intai o pregatire terminata (setarile se pun pe firul acesta); rezultatul ei se
	da cel mult VARSTA_LUCRU secunde de la pornire (pagina il arata numai daca ea a cerut-o; lucrul in curs il arata
	oricum). `detaliu` are numai explicatiile despre loc: starea fiecarui disc e in tabelul paginii."""
	L = _l(L)
	acum = time.time() if acum is None else acum
	lucru = L.culege()
	cand = L.candidati()
	necit = L.necitite()
	cale = L.locInregistrari()
	citire, se_citeste = L.cereStare(cand, cale)
	t = L.texte(citire, cand, necit, L.SCOP_MENIU, cale, None, se_citeste)
	if citire is not None:
		discuri = citire.get("discuri") or []
	else:
		discuri = [dict(c, bun=None, motiv="", liber=None, total=None, are_movie=None, folosit=False) for c in cand]
	rez = {
		"result": True,
		"titlu": t["titlu"],
		"text": t["text"],
		"detaliu": t.get("detaliu_loc", t["detaliu"]),
		"bun": t["bun"],
		"automat": t.get("automat"),
		"intrebare": bool(t.get("intrebare")),
		"loc": cale,
		"timeshift": L.locTimeshift(),
		"se_citeste": bool(se_citeste),
		"discuri": [_disc(L, d, t.get("automat")) for d in discuri],
		# `disc`: discul intreg (sda), pentru legatura 'Formatează' spre pagina Discurile
		"necitite": [{"dispozitiv": n["dispozitiv"], "nume": n["nume"], "fel": n.get("fel") or "",
			"disc": L.discul(n["dispozitiv"]) if hasattr(L, "discul") else ""} for n in necit],
		"lucru": None,
	}
	if lucru is not None and (lucru["stare"] == L.LUCRU_IN_LUCRU or acum - (lucru.get("timp") or 0) < VARSTA_LUCRU):
		text, detaliu = L.textLucru(lucru)
		# `timp` (ceasul receptorului, la pornirea pregatirii): pagina deosebeste o pregatire pornita dupa cererea ei de una
		# mai veche pe acelasi disc
		rez["lucru"] = {"stare": lucru["stare"], "aplicat": bool(lucru.get("aplicat")), "punct": lucru.get("punct"),
			"text": text, "detaliu": detaliu, "timp": lucru.get("timp") or 0}
	return rez


def foloseste(argumente, L=None):
	"""POST /api/stocare-foloseste?punct=...: numai un disc din lista de acum (candidati), niciodata o cale oarecare
	din cerere; pregatirea merge pe un fir, pagina urmareste /api/stocare."""
	L = _l(L)
	punct = argumente.get("punct", "")
	cand = L.candidati()
	if not punct or punct not in [c["punct"] for c in cand]:
		rez = stare(L)
		rez.update({"result": False, "message": _t("Discul ales nu mai este conectat. Alege din nou.")})
		return rez
	pornit, mesaj = L.foloseste(punct, cand, L.SCOP_MENIU)
	rez = stare(L)
	if pornit:
		text, _detaliu = L.textLucru(L.stareLucru())
		rez.update({"result": True, "message": text})
	else:
		rez.update({"result": False, "message": mesaj})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = set(("punct",))
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_PUNCT].strip()
	return rez


def rute(baza, resource, L=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/stocare: citeste; culege o pregatire terminata."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(L))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class FolosesteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, foloseste(argumente(request), L=L))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /stocare: pagina „Locul înregistrărilor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"stocare": StareResource(),
		b"stocare-foloseste": FolosesteResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi si /paznic."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_loc_inregistrari"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Locul înregistrărilor</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .loc{font-size:1.05rem;line-height:1.45;margin:0;}
  .loc.rau{color:#ffb4a8;}
  .loc.intrebare{color:var(--text);font-weight:600;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  table{width:100%;border-collapse:collapse;font-size:.92rem;}
  td,th{padding:8px 6px;border-bottom:1px solid var(--bordura);text-align:left;vertical-align:middle;}
  th{color:var(--text-slab);font-weight:normal;}
  td.actiune{text-align:right;width:1%;white-space:nowrap;}
  td.nume{overflow-wrap:break-word;}
  tr.discul.cu-raspuns td{border-bottom:0;}
  tr.raspuns td{padding-top:0;}
  .mic{color:var(--text-slab);font-size:.85rem;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;}
  tr.raspuns .mesaj{margin:0;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){
    #tabel thead{display:none;}
    #tabel, #tabel tbody, #tabel tr, #tabel td{display:block;width:auto;}
    #tabel tr{padding:10px 0;border-bottom:1px solid var(--bordura);}
    #tabel tr.discul.cu-raspuns{border-bottom:0;padding-bottom:4px;}
    #tabel tr.raspuns{padding:0 0 10px;}
    #tabel td{border:0;padding:3px 0;text-align:left;}
    #tabel td.liber, #tabel td.stare{display:inline;}
    #tabel td.liber:not(:empty)::before{content:"Liber: ";color:var(--text-slab);}
    #tabel td.liber:not(:empty) + td.stare::before{content:" · ";color:var(--text-slab);}
    #tabel td.actiune{white-space:normal;padding-top:8px;}
    #tabel td.actiune button{width:100%;}
  }
</style>
</head>
<body>
<main>
<h1>Locul înregistrărilor</h1>
<p class="mesaj" id="incarcare">Se citesc discurile...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Unde se salvează</h2>
    <p class="loc" id="text"></p>
    <p class="nota" id="detaliu"></p>
  </section>
  <section class="card">
    <h2>Discurile conectate</h2>
    <p class="nota ascuns" id="alege">Alege discul pe care se salvează înregistrările.</p>
    <p class="nota" id="fara">Nu este conectat niciun stick USB sau hard disk.</p>
    <table id="tabel"><thead><tr><th>Discul</th><th>Liber</th><th>Starea</th><th></th></tr></thead><tbody id="discuri"></tbody></table>
    <div id="mesaj" class="ascuns"></div>
    <p class="nota ascuns" id="notaFoloseste">„Folosește pentru înregistrări” face pe disc dosarul movie, dacă lipsește. Nu se șterge și nu se formatează nimic.</p>
  </section>
  <section class="card">
    <h2>Cum alege receptorul</h2>
    <p class="nota">La prima înregistrare (tasta roșie, pauză, o emisiune programată din ghid sau de aici), receptorul caută singur stick-urile și hard diskurile. Dacă e unul singur, îl folosește și face pe el dosarul movie. Dacă sunt mai multe, te întreabă o dată pe care și ține minte alegerea; dacă nu răspunzi până pornește o înregistrare programată, ia singur discul cu cel mai mult loc liber. Memoria internă a receptorului nu se folosește niciodată: e prea mică.</p>
  </section>
  <section class="card ascuns" id="cardNecitite">
    <h2>Discuri pe care receptorul nu le poate citi</h2>
    <ul id="necitite"></ul>
    <p class="nota">Receptorul nu le poate citi sistemul de fișiere. Se pot folosi după formatare: cu „Formatează”, care deschide pagina Discurile (receptorul întreabă înainte), sau pe un calculator, ca FAT32. Formatarea șterge tot de pe ele.</p>
  </section>
  <p class="nota">Locul fiecărui fel de înregistrare (programate, imediate, timeshift) se alege în <a data-cale="/locuri-inregistrari" href="/locuri-inregistrari" style="color:inherit">Locurile înregistrărilor</a>; formatarea și verificarea discurilor în <a data-cale="/discuri" href="/discuri" style="color:inherit">Discurile</a>.</p>
  <p class="nota">Același ecran este pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var CEAS = null;
// discul pentru care pagina aceasta a apasat „Folosește”: numai rezultatul lui se arata (lucrul in curs, oricum)
var CERUT = null;
// raspunsul imediat al cererii (trimisa, refuzata, receptorul nu raspunde): {punct, text, detaliu, eroare}
var RASPUNS = null;
// `timp` al pregatirii stiute cand s-a apasat „Folosește”: numai o pregatire pornita dupa cerere (alt timp) ii tine locul
var LUCRU_LA_CERERE = null;
var ULTIMA = null;
var ULTIMUL_MESAJ = "";
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function inLucru(d){ return d.lucru && (d.lucru.stare === "in_lucru" || (d.lucru.stare === "gata" && !d.lucru.aplicat)); }
function lucruNou(l){ return !!l && l.timp !== LUCRU_LA_CERERE; }
function lucruNouPe(d, punct){ return !!d.lucru && d.lucru.punct === punct && lucruNou(d.lucru); }
function dinLucru(l){ return {text: l.text, detaliu: l.detaliu, eroare: l.stare === "eroare"}; }
// fraza simpla, apoi explicatia mai mica, separat
function raspunsHtml(loc, r){
  loc.textContent = "";
  var p = document.createElement("p"); p.className = "mesaj" + (r.eroare ? " eroare" : ""); p.textContent = r.text || "";
  loc.appendChild(p);
  if(r.detaliu){ var n = document.createElement("p"); n.className = "nota"; n.textContent = r.detaliu; loc.appendChild(n); }
}
// ce se arata langa un disc: raspunsul cererii de acum (trimisa, refuzata), apoi lucrul pe el pornit dupa cerere sau in
// curs (pornit de oriunde); o pregatire mai veche pe acelasi disc nu acopera refuzul
function raspunsPentru(d, punct){
  if(CERUT === punct && lucruNouPe(d, punct)){ return dinLucru(d.lucru); }
  if(RASPUNS && RASPUNS.punct === punct){ return RASPUNS; }
  if(d.lucru && d.lucru.punct === punct && (inLucru(d) || CERUT === punct)){ return dinLucru(d.lucru); }
  return null;
}
function arata(d){
  ULTIMA = d;
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  $("text").textContent = d.text || "";
  $("text").classList.toggle("rau", !d.bun && !d.se_citeste && !d.intrebare);
  $("text").classList.toggle("intrebare", !!d.intrebare);
  $("alege").classList.toggle("ascuns", !d.intrebare);
  $("detaliu").textContent = d.detaliu || "";
  var corp = $("discuri"); corp.textContent = "";
  var ocupat = inLucru(d);
  var aratat = false;
  var butoane = 0;
  (d.discuri || []).forEach(function(k){
    var tr = document.createElement("tr"); tr.className = "discul";
    var n = document.createElement("td"); n.className = "nume"; n.textContent = k.nume;
    var mic = document.createElement("div"); mic.className = "mic"; mic.textContent = k.punct + (k.fel ? " (" + k.fel + ")" : "");
    n.appendChild(mic);
    var l = document.createElement("td"); l.className = "liber"; l.textContent = k.liber_text ? (k.liber_text + " din " + k.total_text) : "";
    var s = document.createElement("td"); s.className = "stare"; s.textContent = k.stare;
    var a = document.createElement("td"); a.className = "actiune";
    if(k.bun !== false && !k.folosit){
      var b = document.createElement("button"); b.type = "button"; b.className = "verde";
      b.textContent = (ocupat && d.lucru.punct === k.punct) ? "Se pregătește..." : "Folosește pentru înregistrări";
      b.disabled = ocupat;
      b.addEventListener("click", function(){ foloseste(k); });
      a.appendChild(b);
      butoane++;
    }
    tr.appendChild(n); tr.appendChild(l); tr.appendChild(s); tr.appendChild(a); corp.appendChild(tr);
    var r = raspunsPentru(d, k.punct);
    if(r){
      aratat = true;
      tr.classList.add("cu-raspuns");
      var rr = document.createElement("tr"); rr.className = "raspuns";
      var td = document.createElement("td"); td.colSpan = 4; raspunsHtml(td, r);
      rr.appendChild(td); corp.appendChild(rr);
    }
  });
  var are = (d.discuri || []).length > 0;
  $("tabel").classList.toggle("ascuns", !are);
  $("fara").classList.toggle("ascuns", are);
  $("notaFoloseste").classList.toggle("ascuns", !butoane);
  var nc = $("necitite"); nc.textContent = "";
  (d.necitite || []).forEach(function(k){
    var li = document.createElement("li"); li.textContent = k.nume;
    if(k.disc){
      // formatarea se face in pagina Discurile, cu intrebarea ei; aici numai drumul spre ea
      var a = document.createElement("a"); a.href = adresa("/discuri?f=formatare"); a.textContent = "Formatează";
      a.style.color = "inherit"; a.style.marginLeft = "12px";
      li.appendChild(a);
    }
    nc.appendChild(li);
  });
  $("cardNecitite").classList.toggle("ascuns", !(d.necitite || []).length);
  // discul apasat nu mai e in lista (scos intre timp): raspunsul sub discuri, adus in fata ochilor
  var sus = null;
  if(!aratat && CERUT !== null){
    // refuzul cererii de acum inaintea unei pregatiri mai vechi pe acelasi disc; numai o pregatire pornita dupa cerere il
    // inlocuieste
    if(RASPUNS && !lucruNouPe(d, CERUT)){ sus = RASPUNS; }
    else if(d.lucru && d.lucru.punct === CERUT && (lucruNou(d.lucru) || !RASPUNS)){ sus = dinLucru(d.lucru); }
  }
  var m = $("mesaj");
  m.classList.toggle("ascuns", !sus);
  if(sus){
    raspunsHtml(m, sus);
    if(sus.text !== ULTIMUL_MESAJ && m.scrollIntoView){ m.scrollIntoView({block: "nearest"}); }
  }
  ULTIMUL_MESAJ = sus ? sus.text : "";
  programeaza(d.se_citeste || ocupat ? 1000 : 10000);
}
function programeaza(ms){ if(CEAS){ clearTimeout(CEAS); } CEAS = setTimeout(citeste, ms); }
function citeste(){
  return cerere("/api/stocare").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi discurile."; programeaza(10000); return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."; programeaza(10000); });
}
function foloseste(k){
  if(!confirm("Înregistrările se vor salva pe „" + k.nume + "”. Dacă pe el nu există dosarul movie, receptorul îl face. Nu se șterge nimic. Continui?")){ return; }
  var q = new URLSearchParams(); q.set("punct", k.punct);
  CERUT = k.punct;
  LUCRU_LA_CERERE = (ULTIMA && ULTIMA.lucru) ? ULTIMA.lucru.timp : null;
  RASPUNS = {punct: k.punct, text: "Se trimite...", detaliu: "", eroare: false};
  if(ULTIMA){ arata(ULTIMA); }
  cerere("/api/stocare-foloseste", "POST", q).then(function(d){
    RASPUNS = d.result ? null : {punct: k.punct, text: d.message || "Receptorul nu a putut porni pregătirea.", detaliu: "", eroare: true};
    if(d.discuri){ arata(d); } else { citeste(); }
  }).catch(function(){
    RASPUNS = {punct: k.punct, text: "Receptorul nu răspunde.", detaliu: "", eroare: true};
    if(ULTIMA){ arata(ULTIMA); }
  });
}
// legaturile spre paginile vecine pastreaza cheia din adresa (modul ?token=)
Array.prototype.forEach.call(document.querySelectorAll("a[data-cale]"), function(a){ a.href = adresa(a.getAttribute("data-cale")); });
citeste();
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
		N_("Locul înregistrărilor"),
		N_("Se citesc discurile..."),
		N_("Unde se salvează"),
		N_("Discurile conectate"),
		N_("Alege discul pe care se salvează înregistrările."),
		N_("Nu este conectat niciun stick USB sau hard disk."),
		N_("Discul"),
		N_("Liber"),
		N_("Starea"),
		N_("„Folosește pentru înregistrări” face pe disc dosarul movie, dacă lipsește. Nu se șterge și nu "
			"se formatează nimic."),
		N_("Cum alege receptorul"),
		N_("La prima înregistrare (tasta roșie, pauză, o emisiune programată din ghid sau de aici), "
			"receptorul caută singur stick-urile și hard diskurile. Dacă e unul singur, îl folosește și face "
			"pe el dosarul movie. Dacă sunt mai multe, te întreabă o dată pe care și ține minte alegerea; "
			"dacă nu răspunzi până pornește o înregistrare programată, ia singur discul cu cel mai mult loc "
			"liber. Memoria internă a receptorului nu se folosește niciodată: e prea mică."),
		N_("Discuri pe care receptorul nu le poate citi"),
		N_("Receptorul nu le poate citi sistemul de fișiere. Se pot folosi după formatare: cu „Formatează”, "
			"care deschide pagina Discurile (receptorul întreabă înainte), sau pe un calculator, ca FAT32. "
			"Formatarea șterge tot de pe ele."),
		N_("Locul fiecărui fel de înregistrare (programate, imediate, timeshift) se alege în <a "
			"data-cale=\"/locuri-inregistrari\" href=\"/locuri-inregistrari\" style=\"color:inherit\">Locurile "
			"înregistrărilor</a>; formatarea și verificarea discurilor în <a data-cale=\"/discuri\" "
			"href=\"/discuri\" style=\"color:inherit\">Discurile</a>."),
		N_("Același ecran este pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("din"),
		N_("Se pregătește..."),
		N_("Folosește pentru înregistrări"),
		N_("Formatează"),
		N_("Receptorul nu a putut citi discurile."),
		N_("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		N_("Înregistrările se vor salva pe „"),
		N_("”. Dacă pe el nu există dosarul movie, receptorul îl face. Nu se șterge nimic. Continui?"),
		N_("Se trimite..."),
		N_("Receptorul nu a putut porni pregătirea."),
		N_("Receptorul nu răspunde."),
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

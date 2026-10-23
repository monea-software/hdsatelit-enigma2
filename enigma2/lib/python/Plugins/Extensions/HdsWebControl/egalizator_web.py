# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# egalizator_web.py: „Egalizator” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Meniu > Audio & Sound Tracks > Egalizator, Screens/HdsEgalizator.py).
#
# O SINGURA LOGICA: setarile, presetarile, memoria pe post, textele starii si motorul sunt in
# Components/HdsEgalizator.py; aici numai citirea argumentelor, verificarea lor si pagina.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/egalizator             setarile (si cele obisnuite, „globale”), presetarile, postul de acum, starea in
#                                    cuvinte, datele tehnice pe randuri („tehnic”), starea motorului (bruta, pentru
#                                    „Text brut”)
#   POST /api/egalizator-seteaza     pornit=0|1, presetare=<cheie>, benzi=b0,...,b9, noapte=0|1, nivel=-12..12,
#                                    pe_post=0|1, volum=auto|aici|placa, placa=<nume ALSA>, tv=0|1 (si la canalele TV),
#                                    potrivire_tv=-300..300 (ms, din 10 in 10: sunetul fata de imagine la TV); cu
#                                    incearca=1 valorile
#                                    se aud pe loc fara sa se salveze (glisoarele, cat le misti); renunta=1 pune inapoi
#                                    ce e salvat. O singura valoare gresita nu schimba nimic. pe_post=0 fara alte
#                                    valori: postul uita reglajele lui, cele obisnuite raman cum erau.
#   GET  /egalizator                 pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte (motorul noteaza setarile si raspunde
# din memorie). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (E).

MAX_TEXT = 80
CHEI = ("pornit", "presetare", "benzi", "noapte", "nivel", "pe_post", "volum", "placa", "incearca", "renunta", "tv",
	"potrivire_tv")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _e(E=None):
	if E is not None:
		return E
	from Components import HdsEgalizator
	return HdsEgalizator


def stare(E=None):
	"""Pentru GET /api/egalizator."""
	E = _e(E)
	s = E.stareCompleta()
	s["result"] = True
	s["presetari"] = [{"cheie": p[0], "nume": _t(p[1]), "benzi": list(p[2]), "noapte": bool(p[3])} for p in E.PRESETARI]
	s["nume_manual"] = _t(E.NUME_MANUAL)
	s["etichete"] = list(E.ETICHETE)
	s["limite"] = {"db_min": E.DB_MIN, "db_max": E.DB_MAX, "nivel_min": E.NIVEL_MIN, "nivel_max": E.NIVEL_MAX}
	s["volum_alegeri"] = [["auto", _t("Automat")], ["aici", _t("În egalizator")], ["placa", _t("Pe placa de sunet")]]
	s["potrivire_tv_alegeri"] = [[v, t] for v, t in E.alegeriPotrivireTv()]
	return s


def _intreg(text, jos, sus):
	try:
		v = int(text)
	except (TypeError, ValueError):
		return None
	return v if jos <= v <= sus else None


def _citeste(argumente, E):
	"""Argumentele -> (valorile bune, None) sau (None, mesajul de eroare)."""
	v = {}
	for cheie in ("pornit", "noapte", "pe_post", "incearca", "renunta", "tv"):
		if cheie in argumente:
			if argumente[cheie] not in ("0", "1"):
				return None, _t("„%s” se alege cu 1 (da) sau 0 (nu).") % cheie
			v[cheie] = argumente[cheie] == "1"
	if "presetare" in argumente:
		if argumente["presetare"] not in E.CHEI_PRESETARI:
			return None, _t("Presetarea „%s” nu există.") % argumente["presetare"][:40]
		v["presetare"] = argumente["presetare"]
	if "benzi" in argumente:
		parti = argumente["benzi"].split(",")
		benzi = [_intreg(x.strip(), E.DB_MIN, E.DB_MAX) for x in parti]
		if len(benzi) != E.BENZI or None in benzi:
			return None, _t("Benzile se dau ca %d numere între %d și %d, cu virgulă între ele.") % (E.BENZI, E.DB_MIN, E.DB_MAX)
		v["benzi"] = benzi
	if "nivel" in argumente:
		n = _intreg(argumente["nivel"], E.NIVEL_MIN, E.NIVEL_MAX)
		if n is None:
			return None, _t("Nivelul se dă ca număr între %d și %d.") % (E.NIVEL_MIN, E.NIVEL_MAX)
		v["nivel"] = n
	if "volum" in argumente:
		if argumente["volum"] not in E.VOLUM_ALEGERI:
			return None, _t("Volumul se alege cu auto, aici sau placa.")
		v["volum"] = argumente["volum"]
	if "placa" in argumente:
		p = argumente["placa"]
		if not p or not all(ch.isalnum() or ch in ":,_-." for ch in p):
			return None, _t("Numele plăcii de sunet are numai litere, cifre și : , _ - .")
		v["placa"] = p
	if "potrivire_tv" in argumente:
		n = _intreg(argumente["potrivire_tv"], E.POTRIVIRE_TV_MIN, E.POTRIVIRE_TV_MAX)
		if n is None or n % E.POTRIVIRE_TV_PAS:
			return None, _t("Potrivirea cu imaginea se dă în milisecunde, din 10 în 10, între %d și %d.") % (
				E.POTRIVIRE_TV_MIN, E.POTRIVIRE_TV_MAX)
		v["potrivire_tv"] = n
	return v, None


def seteaza(argumente, E=None):
	"""POST /api/egalizator-seteaza."""
	E = _e(E)
	v, eroare = _citeste(argumente, E)
	if eroare:
		rez = stare(E)
		rez.update({"result": False, "message": eroare})
		return rez
	if v.get("renunta"):
		E.aplica()
		rez = stare(E)
		rez.update({"result": True, "message": _t("Am pus înapoi reglajele păstrate.")})
		return rez
	if v.get("incearca"):
		E.incearca(benzi=v.get("benzi"), noapte=v.get("noapte"), nivel=v.get("nivel"), presetare_=v.get("presetare"),
			pornit=v.get("pornit"))
		rez = stare(E)
		rez.update({"result": True, "message": _t("Se aude acum. Apasă „Păstrează” ca să rămână.")})
		return rez
	valori = dict((k, v[k]) for k in ("pornit", "benzi", "noapte", "nivel", "volum", "placa", "tv") if k in v)
	if "potrivire_tv" in v:
		valori["potrivireTv"] = v["potrivire_tv"]
	if "presetare" in v:
		valori["presetare_"] = v["presetare"]
	if "pe_post" in v:
		valori["pePost"] = v["pe_post"]
	if not valori:
		rez = stare(E)
		rez.update({"result": False, "message": _t("Nu s-a trimis nicio setare.")})
		return rez
	E.seteaza(**valori)
	rez = stare(E)
	rez.update({"result": True, "message": _t("Păstrat. Se aude și pe televizor.")})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:20]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in CHEI:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, E=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/egalizator: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), E=E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /egalizator: pagina „Egalizator”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"egalizator": StareResource(),
		b"egalizator-seteaza": SeteazaResource(),
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur (probele de pe PC) da „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_egalizator"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Egalizator</title>
<style>__STIL_COMUN__
  main{max-width:980px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1.02rem;line-height:1.45;margin:0 0 6px;}
  .acum.bine{color:#7ee0a8;} .acum.rau{color:#ffd24d;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .rand{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.ales{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .eticheta-aleasa{display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--albastru);background:var(--albastru);color:#fff;}
  select,input[type=text]{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .comutator{display:flex;align-items:center;gap:10px;min-height:44px;font-size:1rem;}
  .comutator input{width:22px;height:22px;}
  .benzi{position:relative;display:grid;grid-template-columns:repeat(11,minmax(0,1fr));gap:4px;align-items:end;margin-top:6px;}
  .banda{display:flex;flex-direction:column;align-items:center;gap:6px;position:relative;z-index:1;}
  .banda .val{font-weight:bold;font-size:.9rem;min-height:1.2em;white-space:nowrap;}
  .banda .et{color:var(--text-slab);font-size:.8rem;white-space:nowrap;}
  .scurt{display:none;}
  .banda input[type=range]{writing-mode:vertical-lr;direction:rtl;height:220px;width:36px;margin:0;accent-color:#9fb4ff;}
  .banda.nivel{border-left:1px solid var(--bordura);}
  #spectru{position:absolute;left:0;top:0;width:100%;height:100%;z-index:0;pointer-events:none;}
  .stins .banda input[type=range]{filter:grayscale(1);opacity:.45;}
  table{width:100%;border-collapse:collapse;font-size:.9rem;}
  td{padding:6px 4px;border-bottom:1px solid var(--bordura);vertical-align:top;}
  td.e{color:var(--text-slab);width:45%;}
  pre{white-space:pre-wrap;word-break:break-word;font-size:.8rem;background:#0f1216;padding:10px;border-radius:8px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  details summary{cursor:pointer;min-height:32px;}
  @media (max-width:640px){ .benzi{gap:2px;} .banda input[type=range]{height:170px;width:26px;} .banda .et{font-size:.75rem;min-height:1.3em;} .banda .val{font-size:.75rem;} .lung{display:none;} .scurt{display:inline;} }
</style>
</head>
<body>
<main>
<h1>Egalizator</h1>
<p class="mesaj" id="incarcare">Se citesc reglajele...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Acum</h2>
    <p class="acum" id="acum"></p>
    <p class="nota" id="detaliu"></p>
  </section>
  <section class="card" id="reglaje">
    <h2>Reglaje</h2>
    <div class="rand">
      <label class="comutator"><input type="checkbox" id="pornit"> Egalizator pornit</label>
      <label class="comutator"><input type="checkbox" id="noapte"> Mod de noapte</label>
      <label class="comutator" id="rand_post"><input type="checkbox" id="pe_post"> <span id="text_post">Pentru acest post</span></label>
    </div>
    <div class="rand" id="presetari"></div>
    <div class="benzi" id="benzi"><canvas id="spectru"></canvas></div>
    <p class="nota">Barele din spate arată cât de tare se aude fiecare bandă acum. Sus: mai mult, jos: mai puțin, câte 1 dB (valorile sunt în dB, frecvențele în Hz).</p>
    <div class="rand" style="margin-top:12px">
      <button type="button" class="verde" id="pastreaza">Păstrează</button>
      <button type="button" id="renunta">Renunță</button>
      <span class="nota" id="nepastrat"></span>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card">
    <details id="avansat">
      <summary>Pentru probe și potriviri</summary>
      <table>
        <tr><td class="e">Volumul telecomenzii</td><td><select id="volum"></select></td></tr>
        <tr><td class="e">Placa de sunet (ALSA)</td><td><input type="text" id="placa" maxlength="64"> <button type="button" id="pune_placa">Pune</button></td></tr>
        <tr><td class="e">La canalele TV</td><td><select id="tv"><option value="1">Da</option><option value="0">Nu</option></select></td></tr>
        <tr><td class="e">Potrivirea cu imaginea la TV</td><td><select id="potrivire_tv"></select></td></tr>
      </table>
      <p class="nota">Automat: receptorul vede singur dacă volumul telecomenzii se aplică și sunetului cu egalizator. Placa de sunet rămâne „default”, afară de probe.</p>
      <p class="nota">La canalele TV cu sunet MPEG egalizatorul ține sunetul după imagine. Dacă buzele se mișcă după sunet, alege un număr cu +; dacă sunetul vine după buze, unul cu −.</p>
      <h2 style="margin-top:14px">Sunetul cu egalizator</h2>
      <table id="tehnic"></table>
      <p><button type="button" id="brut">Text brut</button></p>
      <pre id="text_brut" class="ascuns"></pre>
    </details>
  </section>
  <p class="nota">Aceleași reglaje sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var D = null, SCHIMBAT = false, CEAS_INCERCARE = null;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var o = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ o.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ o.headers["Content-Type"] = "application/x-www-form-urlencoded"; o.body = date.toString(); }
  return fetch(adresa(cale), o).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(t, e){ var m = $("mesaj"); m.textContent = t || ""; m.classList.toggle("eroare", !!e); }
function numar(v){ v = parseInt(v, 10); return (v > 0 ? "+" : (v < 0 ? "\\u2212" : "")) + Math.abs(v); }
function db(v){ return numar(v) + " dB"; }
function valoare(el, v){
  el.textContent = "";
  var a = document.createElement("span"); a.className = "lung"; a.textContent = db(v);
  var b = document.createElement("span"); b.className = "scurt"; b.textContent = numar(v);
  el.appendChild(a); el.appendChild(b);
}
function scurt(et){ return et.replace(" kHz", "k").replace(" Hz", ""); }
function benziAcum(){ var b = []; for(var i = 0; i < 10; i++){ b.push(parseInt($("b" + i).value, 10)); } return b; }
function construieste(d){
  var c = $("benzi");
  d.etichete.concat(["Nivel"]).forEach(function(et, i){
    var col = document.createElement("div"); col.className = "banda" + (i === 10 ? " nivel" : "");
    var v = document.createElement("div"); v.className = "val"; v.id = "v" + i;
    var r = document.createElement("input"); r.type = "range"; r.id = i === 10 ? "nivel" : "b" + i; r.step = 1;
    r.min = i === 10 ? d.limite.nivel_min : d.limite.db_min; r.max = i === 10 ? d.limite.nivel_max : d.limite.db_max;
    r.setAttribute("aria-label", et);
    r.addEventListener("input", function(){ valoare($("v" + i), r.value); if(i < 10){ potrivestePresetarea(); } schimbare(); deseneaza(); });
    var e = document.createElement("div"); e.className = "et";
    var el = document.createElement("span"); el.className = "lung"; el.textContent = et;
    var es = document.createElement("span"); es.className = "scurt"; es.textContent = scurt(et);
    e.appendChild(el); e.appendChild(es);
    col.appendChild(v); col.appendChild(r); col.appendChild(e); c.appendChild(col);
  });
  d.volum_alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; $("volum").appendChild(o); });
  (d.potrivire_tv_alegeri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; $("potrivire_tv").appendChild(o); });
}
function presetari(d){
  var c = $("presetari"); c.textContent = "";
  d.presetari.forEach(function(p){
    var b = document.createElement("button"); b.type = "button"; b.textContent = p.nume;
    b.classList.toggle("ales", p.cheie === d.presetare);
    b.addEventListener("click", function(){ aplicaPresetare(p); });
    c.appendChild(b);
  });
  if(d.presetare === "manual"){
    // benzile reglate de mana nu sunt o presetare de apasat: o eticheta aleasa, nu un buton stins
    var s = document.createElement("span"); s.className = "eticheta-aleasa"; s.textContent = d.nume_manual; c.appendChild(s);
  }
}
function aplicaPresetare(p){
  for(var i = 0; i < 10; i++){ $("b" + i).value = p.benzi[i]; valoare($("v" + i), p.benzi[i]); }
  $("noapte").checked = p.noapte;
  D.presetare = p.cheie; presetari(D); schimbare(); deseneaza();
}
function arataReglaje(d){
  $("pornit").checked = d.pornit; $("noapte").checked = d.noapte;
  for(var i = 0; i < 10; i++){ $("b" + i).value = d.benzi[i]; valoare($("v" + i), d.benzi[i]); }
  $("nivel").value = d.nivel; valoare($("v10"), d.nivel);
  $("pe_post").checked = d.pe_post; $("pe_post").disabled = !d.post.cheie;
  $("text_post").textContent = d.post.cheie ? ("Numai pentru " + (d.post.nume || "acest post")) : "Pentru acest post (nu merge niciun post)";
  $("volum").value = d.volum; $("placa").value = d.placa;
  $("tv").value = d.tv ? "1" : "0"; $("potrivire_tv").value = String(d.potrivire_tv);
  presetari(d); SCHIMBAT = false; $("nepastrat").textContent = "";
}
function arataStarea(d){
  var a = $("acum"); a.textContent = d.text || "";
  a.classList.toggle("bine", d.bine === true); a.classList.toggle("rau", d.bine === false);
  $("detaliu").textContent = d.detaliu || "";
  $("reglaje").classList.toggle("stins", !$("pornit").checked);
  var m = d.motor || {}, t = $("tehnic"); t.textContent = "";
  // datele pe randuri, in cuvinte (Components/HdsEgalizator.randuriTehnice); cele brute numai in „Text brut”
  (d.tehnic || []).forEach(function(x){ if(!x[1]){ return; } var tr = document.createElement("tr");
    var a1 = document.createElement("td"); a1.className = "e"; a1.textContent = x[0];
    var a2 = document.createElement("td"); a2.textContent = x[1]; tr.appendChild(a1); tr.appendChild(a2); t.appendChild(tr); });
  $("text_brut").textContent = JSON.stringify(m, null, 1);
  deseneaza();
}
// drumul butonului fiecarui glisor, masurat pe pagina (pe telefon randurile de text au alta inaltime decat pe ecran lat):
// x la mijlocul glisorului, sus / jos unde ajunge centrul butonului la +12 / -12 (jumatatea butonului scazuta la capete)
var BUTON_JUMATATE = 8;
function drumGlisor(i, baza){
  var r = $("b" + i).getBoundingClientRect();
  return {x: r.left + r.width / 2 - baza.left, sus: r.top - baza.top + BUTON_JUMATATE, jos: r.bottom - baza.top - BUTON_JUMATATE};
}
function deseneaza(){
  var cv = $("spectru"), c = $("benzi"); if(!cv || !D || !$("b0")){ return; }
  cv.width = c.clientWidth; cv.height = c.clientHeight;
  var x = cv.getContext("2d"); x.clearRect(0, 0, cv.width, cv.height);
  var sp = (D.motor && D.motor.spectru && (D.motor.stare === "merge" || D.motor.stare === "fara-date")) ? D.motor.spectru : null;
  var baza = c.getBoundingClientRect(), g = [];
  for(var i = 0; i < 10; i++){ g.push(drumGlisor(i, baza)); }
  var w = g.length > 1 ? g[1].x - g[0].x : cv.width / 11;
  x.fillStyle = $("pornit").checked ? "rgba(90,110,180,.35)" : "rgba(100,110,130,.2)";
  if(sp){ for(var k = 0; k < 10; k++){ var n = Math.max(-60, Math.min(0, sp[k])); var hh = (n + 60) / 60 * (g[k].jos - g[k].sus); x.fillRect(g[k].x - w * .3, g[k].jos - hh, w * .6, hh); } }
  var zero = (g[0].sus + g[0].jos) / 2;
  x.strokeStyle = "rgba(102,112,133,.8)"; x.lineWidth = 1; x.beginPath(); x.moveTo(g[0].x - w / 2, zero); x.lineTo(g[9].x + w / 2, zero); x.stroke();
  x.strokeStyle = $("pornit").checked ? "#9fb4ff" : "#667085"; x.lineWidth = 3; x.beginPath();
  benziAcum().forEach(function(v, i){ var z = (g[i].sus + g[i].jos) / 2, py = z - v / 12 * (g[i].jos - g[i].sus) / 2; if(i){ x.lineTo(g[i].x, py); } else { x.moveTo(g[i].x, py); } });
  x.stroke();
}
function trimite(valori){
  var q = new URLSearchParams(); Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  return cerere("/api/egalizator-seteaza", "POST", q).then(function(d){
    if(!d.result){ mesaj(d.message, true); return d; }
    D = d; arataStarea(d); return d;
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function valori(){
  return {pornit: $("pornit").checked ? "1" : "0", benzi: benziAcum().join(","), noapte: $("noapte").checked ? "1" : "0", nivel: $("nivel").value};
}
function schimbare(){
  mesaj("");
  SCHIMBAT = true; $("nepastrat").textContent = "Ai schimbări nepăstrate: se aud acum, dar rămân numai după „Păstrează”.";
  $("reglaje").classList.toggle("stins", !$("pornit").checked);
  clearTimeout(CEAS_INCERCARE);
  CEAS_INCERCARE = setTimeout(function(){ var v = valori(); v.incearca = "1"; trimite(v); }, 150);
}
function citeste(cuReglaje){
  return cerere("/api/egalizator").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi reglajele."; return; }
    var prima = !D; D = d;
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    if(prima){ construieste(d); }
    if(prima || cuReglaje || !SCHIMBAT){ arataReglaje(d); }
    arataStarea(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică să fie pornit și în aceeași rețea."; });
}
function potrivestePresetarea(){
  var b = benziAcum().join(","), n = $("noapte").checked, gasit = "manual";
  D.presetari.forEach(function(p){ if(p.benzi.join(",") === b && p.noapte === n){ gasit = p.cheie; } });
  if(gasit !== D.presetare){ D.presetare = gasit; presetari(D); }
}
$("pornit").addEventListener("change", schimbare);
// „Numai pentru acest post” debifat: se vad (si se aud) reglajele obisnuite, ale tuturor posturilor; bifat: cele de acum
// raman si devin ale postului la „Păstrează”
$("pe_post").addEventListener("change", function(){
  if(!$("pe_post").checked && D && D.globale){
    var g = D.globale;
    for(var i = 0; i < 10; i++){ $("b" + i).value = g.benzi[i]; valoare($("v" + i), g.benzi[i]); }
    $("noapte").checked = g.noapte; $("nivel").value = g.nivel; valoare($("v10"), g.nivel);
    D.presetare = g.presetare; presetari(D);
  }
  schimbare(); deseneaza();
});
$("noapte").addEventListener("change", function(){ potrivestePresetarea(); schimbare(); });
$("pastreaza").addEventListener("click", function(){
  var v = valori(); if(!$("pe_post").disabled){ v.pe_post = $("pe_post").checked ? "1" : "0"; }
  trimite(v).then(function(d){ if(d && d.result){ mesaj(d.message); arataReglaje(d); } });
});
$("renunta").addEventListener("click", function(){
  trimite({renunta: "1"}).then(function(d){ if(d && d.result){ mesaj(d.message); arataReglaje(d); } });
});
$("volum").addEventListener("change", function(){ trimite({volum: $("volum").value}).then(function(d){ if(d && d.result){ mesaj(d.message); } }); });
$("pune_placa").addEventListener("click", function(){ trimite({placa: $("placa").value}).then(function(d){ if(d && d.result){ mesaj(d.message); } }); });
$("tv").addEventListener("change", function(){ trimite({tv: $("tv").value}).then(function(d){ if(d && d.result){ mesaj(d.message); } }); });
$("potrivire_tv").addEventListener("change", function(){ trimite({potrivire_tv: $("potrivire_tv").value}).then(function(d){ if(d && d.result){ mesaj(d.message); } }); });
$("brut").addEventListener("click", function(){ $("text_brut").classList.toggle("ascuns"); });
window.addEventListener("resize", deseneaza);
citeste(true);
setInterval(function(){ if(!document.hidden){ citeste(false); } }, 1000);
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
		N_("Egalizator"),
		N_("Se citesc reglajele..."),
		N_("Acum"),
		N_("Reglaje"),
		N_("Egalizator pornit"),
		N_("Mod de noapte"),
		N_("Pentru acest post"),
		N_("Barele din spate arată cât de tare se aude fiecare bandă acum. Sus: mai mult, jos: mai puțin, "
			"câte 1 dB (valorile sunt în dB, frecvențele în Hz)."),
		N_("Păstrează"),
		N_("Renunță"),
		N_("Pentru probe și potriviri"),
		N_("Volumul telecomenzii"),
		N_("Placa de sunet (ALSA)"),
		N_("Pune"),
		N_("La canalele TV"),
		N_("Da"),
		N_("Nu"),
		N_("Potrivirea cu imaginea la TV"),
		N_("Automat: receptorul vede singur dacă volumul telecomenzii se aplică și sunetului cu egalizator. "
			"Placa de sunet rămâne „default”, afară de probe."),
		N_("La canalele TV cu sunet MPEG egalizatorul ține sunetul după imagine. Dacă buzele se mișcă după "
			"sunet, alege un număr cu +; dacă sunetul vine după buze, unul cu −."),
		N_("Sunetul cu egalizator"),
		N_("Text brut"),
		N_("Aceleași reglaje sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nivel"),
		N_("Numai pentru"),
		N_("Pentru acest post (nu merge niciun post)"),
		N_("Receptorul nu răspunde."),
		N_("Ai schimbări nepăstrate: se aud acum, dar rămân numai după „Păstrează”."),
		N_("Receptorul nu a putut citi reglajele."),
		N_("Receptorul nu răspunde. Verifică să fie pornit și în aceeași rețea."),
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

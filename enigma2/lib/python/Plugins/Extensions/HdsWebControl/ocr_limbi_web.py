# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ocr_limbi_web.py: „Limbile recunoașterii textului” in interfata web (HdsWebControl), perechea ecranului de pe
# televizor (Screens/HdsOcrLimbi.py, din „Aspectul subtitrărilor”, randul „Limbile recunoașterii”).
#
# Lista tuturor limbilor pentru care receptorul poate citi ca text subtitrarile DVB, grupate: in imagine (nume si
# marime, strans, fara butoane), descarcate, de descarcat (si cele care se descarca, in locul lor, cu bara si butonul
# „Oprește” pe locul butonului apasat); fiecare cu marimea modelului si starea in
# cuvinte, cu butonul potrivit (Descarcă, Oprește, Șterge; pentru un model al carui stick lipseste, Descarcă din nou si
# Scoate din listă) si o cautare dupa nume, si fara diacritice. Sub un rand se scrie ceva numai cand spune ce s-a
# intamplat (descarcarea nereusita si de ce, stickul scos). Sus: cate sunt, unde merg modelele noi si cat loc e acolo;
# cand subtitrarea DVB de acum are o limba fara model, limba ei; limbile pentru care omul a spus „Nu mai întreba”, cu
# butonul care il face sa fie intrebat din nou. Cand singurul loc e memoria interna, pagina pune aceeasi intrebare ca
# televizorul (cu locul liber), iar descarcarea porneste numai dupa „da”.
#
# O SINGURA LOGICA: randurile, textele, locul, descarcarea, oprirea si stergerea vin din Components/HdsOcrModele.py
# (depozit()), exact ce foloseste ecranul. Descarcarea merge pe firul modulului; pagina intreaba starea din nou la
# PAS_DESCARCARE_MS cat merge o descarcare si la PAS_MS altfel (numai cat se vede fila). Randurile se schimba pe loc
# (textul starii, bara, butoanele), fara sa fie facute din nou: un buton cu focus sau apasat ramane acelasi.
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/ocr-limbi                          randurile, textul de sus, locul, descarcarile, limba pistei de acum,
#                                                limbile fara intrebare
#   POST /api/ocr-limbi-descarca?model=slk[&intern=1]   porneste descarcarea; fara intern=1, cand locul ar fi memoria
#                                                interna, intoarce intrebarea (cere_intern) si nu porneste nimic
#   POST /api/ocr-limbi-opreste?model=slk        opreste descarcarea
#   POST /api/ocr-limbi-sterge?model=slk         sterge un model descarcat (cele din imagine nu), sau il scoate din
#                                                lista cand stickul lui nu e pus
#   POST /api/ocr-limbi-intreaba                 receptorul intreaba din nou pentru limbile cu „Nu mai întreba”
#   GET  /ocr-limbi                              pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (reactorul e bucla enigma2) si fac numai lucruri scurte
# (depozitul citeste pe fir tot ce atinge un stick). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe
# PC dau depozitul lor (D).

import re

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

PAS_MS = 5000
PAS_DESCARCARE_MS = 1000
MODEL = re.compile(r"^[a-z]{3}(_[a-z]{4})?$")


def _om(D=None):
	"""Components.HdsOcrModele si depozitul (cel dat de probe, sau al receptorului)"""
	from Components import HdsOcrModele
	return HdsOcrModele, (D if D is not None else HdsOcrModele.depozit())


def _ocrAles():
	try:
		from Components import HdsSubtitrariAspect
		return HdsSubtitrariAspect.stare().get("marire_dvb") == "ocr"
	except Exception:
		return False


def _pista(randuri):
	"""limba subtitrarii DVB de acum, cand modelul ei lipseste de pe receptor (altfel None), din clientul OCR, fara
	sa-l porneasca. Numai o pista DVB (teletextul si fisierele sunt deja text), numai cat subtitrarea e pornita, si
	numai cand modelul necesar nu e in imagine si nici descarcat (randurile listei)."""
	try:
		from Components import HdsOcrSubtitrari as O
		s = O.contor()
		if not s or not s.get("limba") or s.get("model"):
			return None
		if s.get("fel", 0) != 0:
			return None
		necesar = O.modelNecesar(s.get("limba"))
		if not necesar:
			return None
		for r in randuri:
			if r.get("model") == necesar and r.get("stare") in ("imagine", "descarcat"):
				return None
		return {"limba": s.get("limba"), "model": None, "necesar": necesar}
	except Exception:
		return None


def _faraIntrebare(OM):
	try:
		return [OM.numeModel(m) for m in OM.faraIntrebare()]
	except Exception:
		return []


def stare(D=None):
	"""GET /api/ocr-limbi"""
	OM, dep = _om(D)
	inst, se_citeste = dep.cereStare()
	randuri = dep.randuri(inst)
	p = dep.plan(0, inst)
	loc = None
	if p is not None:
		loc = {"fel": p["fel"], "text": p["text"], "liber": OM.marimeText(p["liber"]), "medii": p.get("medii", 0)}
		try:
			loc["sus"] = OM.textLocSus(p)
		except Exception:
			pass
	pista = _pista(randuri)
	if pista:
		pista["nume"] = OM.numeModel(pista["necesar"])
	return {
		"result": True, "se_citeste": bool(se_citeste and inst is None), "scurt": dep.textScurt(),
		"ocr_ales": _ocrAles(), "loc": loc, "pista": pista, "in_lucru": dep.inLucru(),
		"fara_intrebare": _faraIntrebare(OM),
		"modele": [dict((k, r.get(k)) for k in ("model", "nume", "marime", "marime_text", "stare", "stare_text", "loc",
			"procent", "descarcabil", "detaliu", "mesaj")) for r in randuri],
	}


def _model(a):
	m = (a.get("model") or "").strip()
	return m if MODEL.match(m) else None


def _cuStare(D, rez):
	d = stare(D)
	d.update(dict((k, v) for k, v in rez.items() if k != "result"))
	d["result"] = bool(rez.get("result"))
	return d


def descarca(a, D=None):
	OM, dep = _om(D)
	m = _model(a)
	if m is None:
		return {"result": False, "message": _t("Limbă necunoscută.")}
	return _cuStare(D, dep.descarca(m, intern=a.get("intern") == "1"))


def opreste(a, D=None):
	OM, dep = _om(D)
	m = _model(a)
	if m is None:
		return {"result": False, "message": _t("Limbă necunoscută.")}
	return _cuStare(D, dep.opreste(m))


def sterge(a, D=None):
	OM, dep = _om(D)
	m = _model(a)
	if m is None:
		return {"result": False, "message": _t("Limbă necunoscută.")}
	return _cuStare(D, dep.sterge(m))


def intreaba(a, D=None):
	OM, dep = _om(D)
	return _cuStare(D, OM.intreabaDinNou())


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:20].strip()
	return rez


def rute(baza, resource, D=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; D e depozitul
	dat de probe (implicit Components.HdsOcrModele.depozit())."""

	class StareResource(baza):
		"""GET /api/ocr-limbi: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(D))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class DescarcaResource(_Schimba):
		def fa(self, a):
			return descarca(a, D)

	class OpresteResource(_Schimba):
		def fa(self, a):
			return opreste(a, D)

	class StergeResource(_Schimba):
		def fa(self, a):
			return sterge(a, D)

	class IntreabaResource(_Schimba):
		def fa(self, a):
			return intreaba(a, D)

	class PaginaResource(resource.Resource):
		"""GET /ocr-limbi: pagina „Limbile recunoașterii textului”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"ocr-limbi": StareResource(),
		b"ocr-limbi-descarca": DescarcaResource(),
		b"ocr-limbi-opreste": OpresteResource(),
		b"ocr-limbi-sterge": StergeResource(),
		b"ocr-limbi-intreaba": IntreabaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /subtitrari: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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


def _drumMeniu():
	"""Drumul de pe televizor spre ecran, scris ca meniu_web.drumText („Meniu, „Setări”, ...”); modulul incarcat
	singur (probele de pe PC) nu are meniul, deci incepe cu „Meniu”."""
	try:
		from .meniu_web import drumHtml
		drum = drumHtml("hds_subtitrari_aspect")
	except ImportError:
		drum = "Meniu"
	import html
	return drum + html.escape(_t(", „Limbile recunoașterii”"), quote=False)


def pagina_text(stil, config_pagina):
	return (_traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)
		.replace("__DRUM_MENIU__", _drumMeniu()).replace("__PAS_MS__", str(PAS_MS))
		.replace("__PAS_DESCARCARE_MS__", str(PAS_DESCARCARE_MS)))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Limbile recunoașterii textului</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 12px;overflow-wrap:anywhere;}
  h2{font-size:1rem;margin:0 0 6px;color:var(--text-slab);font-weight:600;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 12px;}
  .sus{line-height:1.5;margin:0;}
  .pista{margin:8px 0 0;line-height:1.45;color:#f5c95c;}
  .fara{margin:10px 0 0;line-height:1.45;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;}
  .fara button{min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  #cauta{width:100%;box-sizing:border-box;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .limba{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--bordura);}
  .limba:last-child{border-bottom:0;}
  .limba .nume{font-weight:600;overflow-wrap:anywhere;}
  .limba .marime{color:var(--text-slab);font-weight:normal;margin-left:6px;white-space:nowrap;}
  .limba .stare{grid-column:1;color:var(--text-slab);font-size:.9rem;}
  .limba .stare.imagine{color:#8fd19e;} .limba .stare.descarcat{color:#8fd19e;} .limba .stare.eroare{color:#ffb4a8;}
  .limba .stare.lipseste{color:#f0c674;}
  .limba .buton{grid-column:2;grid-row:1 / span 2;display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}
  .limba button{min-height:44px;min-width:112px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .limba button.descarca{background:#1f771f;border-color:#1f771f;color:#fff;}
  .limba button.sterge{background:#5a1a1a;border-color:#7a2a2a;color:#fff;}
  .limba button:disabled{background:#2a2f36;border-color:var(--bordura);color:var(--text-slab);cursor:not-allowed;}
  .limba .detaliu{grid-column:1 / -1;color:var(--text-slab);font-size:.85rem;line-height:1.4;}
  .limba .detaliu:empty{display:none;}
  .cipuri{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 0;}
  .cip{padding:6px 12px;border:1px solid var(--bordura);border-radius:16px;font-size:.92rem;background:#0f1216;}
  .cip small{color:var(--text-slab);margin-left:6px;font-size:.85rem;white-space:nowrap;}
  .bara{grid-column:1 / -1;height:8px;border-radius:4px;background:#0f1216;border:1px solid var(--bordura);overflow:hidden;}
  .bara span{display:block;height:100%;background:#f5b83d;width:0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:8px 0 0;line-height:1.45;font-size:.92rem;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  a.inapoi{color:var(--text-slab);font-size:.9rem;margin-right:14px;display:inline-flex;align-items:center;min-height:44px;}
  @media (max-width:520px){ .limba{grid-template-columns:1fr;} .limba .buton{grid-column:1;grid-row:auto;order:2;justify-content:stretch;}
    .limba .stare{order:1;} .limba .bara{order:3;} .limba .detaliu{order:4;} .limba button{flex:1 1 100%;} }
</style>
</head>
<body>
<main>
<p><a class="inapoi" href="/subtitrari">Aspectul subtitrărilor</a></p>
<h1>Limbile recunoașterii textului</h1>
<section class="card">
  <p class="sus" id="sus">Se citește lista limbilor...</p>
  <p class="pista ascuns" id="pista"></p>
  <p class="fara ascuns" id="fara-intrebare"><span id="fara-intrebare-text"></span><button type="button" id="intreaba">Întreabă din nou</button></p>
  <p class="mesaj ascuns" id="mesaj"></p>
</section>
<section class="card">
  <input id="cauta" type="search" maxlength="30" placeholder="Caută o limbă" autocomplete="off" aria-label="Caută o limbă">
  <p class="nota ascuns" id="nimic">Nicio limbă nu se potrivește.</p>
</section>
<section class="card" id="grupa-imagine"><h2>În imagine</h2><div class="cipuri" id="lista-imagine"></div><p class="nota">Merg fără descărcare și nu se șterg.</p></section>
<section class="card" id="grupa-descarcate"><h2>Descărcate</h2><div id="lista-descarcate"></div></section>
<section class="card" id="grupa-de-descarcat"><h2>Se pot descărca</h2><div id="lista-de-descarcat"></div></section>
<p class="nota">Modelele sunt tessdata_fast (licența Apache-2.0), luate de la aceeași versiune fixă a depozitului lor; fiecare fișier descărcat e verificat cu sha256 din lista din imagine. Aceeași listă e pe televizor, în __DRUM_MENIU__.</p>
</main>
<script>
var CFG = __CONFIG__;
var ultim = null, ultimJson = null, ceas = null, elemente = {}, ordine = {};
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
function nb(s){ return String(s || "").replace(/(\\d) (GB|MB|KB)/g, "$1\\u00a0$2"); }
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = nb(text); m.classList.toggle("eroare", !!eroare); m.classList.toggle("ascuns", !text); }
function sterge(el){ while(el.firstChild){ el.removeChild(el.firstChild); } }
function grupa(r){
  if(r.stare === "imagine"){ return "imagine"; }
  if(r.stare === "de_descarcat" || r.stare === "eroare" || r.stare === "se_descarca" || r.stare === "asteapta"){ return "de-descarcat"; }
  return "descarcate";
}
function butoane(r){
  if(r.stare === "se_descarca" || r.stare === "asteapta"){ return [["Oprește", "", "opreste"]]; }
  if(r.stare === "descarcat"){ return [["Șterge", "sterge", "sterge"]]; }
  if(r.stare === "lipseste"){ return r.descarcabil ? [["Descarcă din nou", "descarca", "descarca"], ["Scoate din listă", "", "scoate"]] : [["Scoate din listă", "", "scoate"]]; }
  if(r.descarcabil && (r.stare === "de_descarcat" || r.stare === "eroare")){ return [["Descarcă", "descarca", "descarca"]]; }
  return [];
}
function apasa(inf, fel){
  var r = inf.r;
  if(fel === "opreste"){ actiune("/api/ocr-limbi-opreste", r); return; }
  if(fel === "scoate"){ actiune("/api/ocr-limbi-sterge", r); return; }
  if(fel === "sterge"){
    if(confirm(r.nume + ": ștergi modelul (" + r.marime_text + ")? Subtitrările în limba asta rămân imagine până îl descarci din nou.")){ actiune("/api/ocr-limbi-sterge", r); }
    return;
  }
  actiune("/api/ocr-limbi-descarca", r);
}
function faraLoc(){ return !!(ultim && ultim.loc && ultim.loc.fel === "fara_loc"); }
function puneButoane(inf, r){
  var dorite = butoane(r), cheie = dorite.map(function(b){ return b[2]; }).join(",");
  if(cheie !== inf.cheie){
    inf.cheie = cheie;
    if(!dorite.length){ if(inf.buton){ inf.el.removeChild(inf.buton); inf.buton = null; } }
    else {
      if(!inf.buton){ inf.buton = document.createElement("div"); inf.buton.className = "buton"; inf.el.appendChild(inf.buton); }
      sterge(inf.buton);
      dorite.forEach(function(d){
        var b = document.createElement("button"); b.type = "button";
        b.onclick = function(){ apasa(inf, d[2]); };
        inf.buton.appendChild(b);
      });
    }
  }
  if(inf.buton){
    dorite.forEach(function(d, i){
      var b = inf.buton.children[i];
      if(b.textContent !== d[0]){ b.textContent = d[0]; }
      if(b.className !== d[1]){ b.className = d[1]; }
      b.disabled = d[2] === "descarca" && faraLoc();
    });
  }
}
function faceRand(r){
  var d = document.createElement("div"); d.className = "limba";
  var n = document.createElement("div"); n.className = "nume"; n.textContent = r.nume;
  var m = document.createElement("span"); m.className = "marime"; n.appendChild(m);
  d.appendChild(n);
  var s = document.createElement("div"); d.appendChild(s);
  var bara = document.createElement("div"); bara.className = "bara ascuns"; var p = document.createElement("span"); bara.appendChild(p); d.appendChild(bara);
  var t = document.createElement("div"); t.className = "detaliu"; d.appendChild(t);
  return {el: d, marime: m, stare: s, bara: bara, procent: p, detaliu: t, buton: null, cheie: null, r: r};
}
function puneRand(inf, r){
  inf.r = r;
  var mt = r.marime_text || "";
  if(inf.marime.textContent !== mt){ inf.marime.textContent = mt; }
  var st = r.stare_text || "", cls = "stare " + r.stare;
  if(inf.stare.textContent !== st){ inf.stare.textContent = st; }
  if(inf.stare.className !== cls){ inf.stare.className = cls; }
  inf.bara.classList.toggle("ascuns", r.stare !== "se_descarca");
  inf.procent.style.width = (r.procent || 0) + "%";
  var det = r.stare === "eroare" ? (r.mesaj || "") : (r.stare === "lipseste" ? "Pune stickul la loc, descarcă modelul din nou sau scoate-l din listă." : "");
  det = nb(det);
  if(inf.detaliu.textContent !== det){ inf.detaliu.textContent = det; }
  puneButoane(inf, r);
}
function faceCip(r){
  var s = document.createElement("span"); s.className = "cip"; s.textContent = r.nume;
  var m = document.createElement("small"); s.appendChild(m);
  return {el: s, marime: m, r: r};
}
function cuvant(s){ return String(s || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase(); }
function pune(d){
  var j = JSON.stringify([d.scurt, d.loc, d.pista, d.ocr_ales, d.se_citeste, d.fara_intrebare, d.modele]);
  ultim = d;
  if(j === ultimJson){ planifica(); return; }
  ultimJson = j;
  var sus = "Limbile pentru care receptorul citește ca text subtitrările DVB: " + (d.scurt || "") + ".";
  if(d.loc){ sus += " " + (d.loc.sus || d.loc.text || ""); }
  else if(d.se_citeste){ sus += " Se caută stickurile și discurile..."; }
  if(!d.ocr_ales){ sus += " Recunoașterea textului nu e aleasă acum în Aspectul subtitrărilor: modelele se folosesc după ce o alegi."; }
  $("sus").textContent = nb(sus);
  var p = $("pista");
  if(d.pista && d.pista.nume){ p.textContent = "Limba subtitrării DVB de acum: " + d.pista.nume + ". Receptorul nu are modelul ei; îl poți descărca mai jos."; p.classList.remove("ascuns"); }
  else { p.classList.add("ascuns"); }
  var f = $("fara-intrebare");
  if(f){
    var fi = d.fara_intrebare || [];
    f.classList.toggle("ascuns", !fi.length);
    $("fara-intrebare-text").textContent = fi.length ? "Pentru aceste limbi ai ales să nu te mai întreb când apare o subtitrare fără model: " + fi.join(", ") + "." : "";
  }
  var dorite = {"imagine": [], "descarcate": [], "de-descarcat": []}, vazute = {};
  (d.modele || []).forEach(function(r){
    var g = grupa(r), k = (g === "imagine" ? "c:" : "r:") + r.model, inf = elemente[k];
    if(!inf){
      inf = elemente[k] = g === "imagine" ? faceCip(r) : faceRand(r);
      inf.el.setAttribute("data-nume", cuvant(r.nume));
    }
    if(g === "imagine"){ inf.r = r; inf.marime.textContent = r.marime_text || ""; } else { puneRand(inf, r); }
    dorite[g].push(k); vazute[k] = true;
  });
  Object.keys(elemente).forEach(function(k){ if(!vazute[k]){ delete elemente[k]; } });
  var schimbate = ["imagine", "descarcate", "de-descarcat"].filter(function(g){ return (ordine[g] || []).join("|") !== dorite[g].join("|"); });
  schimbate.forEach(function(g){ sterge($("lista-" + g)); });
  schimbate.forEach(function(g){ dorite[g].forEach(function(k){ $("lista-" + g).appendChild(elemente[k].el); }); ordine[g] = dorite[g]; });
  filtreaza();
  planifica();
}
function filtreaza(){
  var q = $("cauta").value.trim().normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase(), toate = 0;
  ["imagine", "descarcate", "de-descarcat"].forEach(function(g){
    var lista = $("lista-" + g), vizibile = 0;
    for(var i = 0; i < lista.children.length; i++){
      var el = lista.children[i], da = !q || el.getAttribute("data-nume").indexOf(q) !== -1;
      el.classList.toggle("ascuns", !da); if(da){ vizibile++; }
    }
    $("grupa-" + g).classList.toggle("ascuns", vizibile === 0);
    toate += vizibile;
  });
  var n = $("nimic"); if(n){ n.classList.toggle("ascuns", !q || toate > 0); }
}
function planifica(){
  if(ceas){ clearTimeout(ceas); }
  ceas = setTimeout(citeste, ultim && ultim.in_lucru ? __PAS_DESCARCARE_MS__ : (ultim && ultim.se_citeste ? 500 : __PAS_MS__));
}
function citeste(){
  if(document.hidden){ planifica(); return; }
  cerere("/api/ocr-limbi").then(function(d){
    if(!d.result){ $("sus").textContent = d.message || "Receptorul nu a putut citi lista."; ultimJson = null; planifica(); return; }
    pune(d);
  }).catch(function(){ $("sus").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; ultimJson = null; planifica(); });
}
function actiune(cale, r, intern){
  var q = new URLSearchParams(); if(r){ q.set("model", r.model); } if(intern){ q.set("intern", "1"); }
  mesaj("Se trimite...");
  cerere(cale, "POST", q).then(function(d){
    if(d.cere_intern){
      mesaj("");
      if(confirm(d.intrebare)){ actiune(cale, r, true); }
      return;
    }
    mesaj(d.message, !d.result);
    if(d.modele){ pune(d); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("cauta").addEventListener("input", filtreaza);
if($("intreaba")){ $("intreaba").addEventListener("click", function(){ actiune("/api/ocr-limbi-intreaba", null); }); }
document.addEventListener("visibilitychange", function(){ if(!document.hidden){ citeste(); } });
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
		N_("Limbile recunoașterii textului"),
		N_("Aspectul subtitrărilor"),
		N_("Se citește lista limbilor..."),
		N_("Întreabă din nou"),
		N_("Nicio limbă nu se potrivește."),
		N_("În imagine"),
		N_("Merg fără descărcare și nu se șterg."),
		N_("Descărcate"),
		N_("Se pot descărca"),
		N_("Modelele sunt tessdata_fast (licența Apache-2.0), luate de la aceeași versiune fixă a "
			"depozitului lor; fiecare fișier descărcat e verificat cu sha256 din lista din imagine. Aceeași "
			"listă e pe televizor, în __DRUM_MENIU__."),
		N_("Caută o limbă"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Oprește"),
		N_("Șterge"),
		N_("Descarcă din nou"),
		N_("Scoate din listă"),
		N_("Descarcă"),
		N_(": ștergi modelul ("),
		N_(")? Subtitrările în limba asta rămân imagine până îl descarci din nou."),
		N_("Pune stickul la loc, descarcă modelul din nou sau scoate-l din listă."),
		N_("Limbile pentru care receptorul citește ca text subtitrările DVB:"),
		N_("Se caută stickurile și discurile..."),
		N_("Recunoașterea textului nu e aleasă acum în Aspectul subtitrărilor: modelele se folosesc după ce "
			"o alegi."),
		N_("Limba subtitrării DVB de acum:"),
		N_(". Receptorul nu are modelul ei; îl poți descărca mai jos."),
		N_("Pentru aceste limbi ai ales să nu te mai întreb când apare o subtitrare fără model:"),
		N_("Receptorul nu a putut citi lista."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
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

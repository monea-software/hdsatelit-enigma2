# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# reglaje_imagine_web.py (PQ2, 0.8.0): „Calitatea imaginii” in interfata web pe placile fara /proc/msp/pq, perechea
# ecranului Screens/HdsCalitateImagine.HdsReglajeImagine (luminozitate, contrast, culori, claritate, zgomot prin
# /proc/stb/vmpeg/0/pep_*). Pagina sta tot la /calitate-imagine: calitate_imagine_web.pagina o da pe aceasta cand
# placa nu are blocul HiSilicon si are reglajele pep_*. Rutele le adauga calitate_imagine_web.rute (plugin.py neatins).
#
# O SINGURA LOGICA: Components/HdsReglajeImagine.py; aici numai argumentele, verificarea lor si pagina.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST si antetul CSRF al panoului):
#   GET  /api/reglaje-imagine             reglajele placii: cheia, numele, descrierea, valoarea salvata, cea din
#                                         fabrica, pozitiile cu textul lor
#   POST /api/reglaje-imagine-seteaza     <cheie>=<pozitie> pentru unul sau mai multe reglaje; incearca=1: se vad pe loc
#                                         fara sa se salveze; renunta=1: inapoi la cele salvate. O valoare gresita nu
#                                         schimba nimic.
#   POST /api/reglaje-imagine-implicite   toate reglajele la valorile din fabrica, salvate
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (R).

ECRAN_TV = "HdsReglajeImagine"


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _r(R=None):
	if R is not None:
		return R
	from Components import HdsReglajeImagine
	return HdsReglajeImagine


def oferit(R=None):
	try:
		return bool(_r(R).disponibil())
	except Exception:
		return False


def stare(R=None):
	"""Pentru GET /api/reglaje-imagine."""
	R = _r(R)
	r = R.reglaje()
	rez = {"result": True, "oferit": bool(r.oferit), "reglaje": [], "eroare": r.eroare or ""}
	if not r.oferit:
		return rez
	R.initConfig()
	salvate = R.valori(salvate=True)
	for cheie in r.chei():
		d = R.REGLAJ[cheie]
		rez["reglaje"].append({"cheie": cheie, "nume": _t(d[4]), "descriere": _t(d[5]), "valoare": salvate[cheie],
			"fabrica": r.pozitieFabrica(cheie), "fabrica_text": R.textPozitie(cheie, r.pozitieFabrica(cheie)),
			"alegeri": [[p, R.textPozitie(cheie, p)] for p in R.pozitii(cheie)]})
	return rez


def _cuMesaj(rez, reusit, mesaj):
	rez["result"] = reusit
	rez["message"] = mesaj
	return rez


def seteaza(argumente, R=None):
	"""POST /api/reglaje-imagine-seteaza."""
	R = _r(R)
	r = R.reglaje()
	if not r.oferit:
		return _cuMesaj(stare(R), False, _t("Receptorul acesta nu are reglaje pentru imagine."))
	R.initConfig()
	if argumente.get("renunta") == "1":
		R.anuleaza()
		return _cuMesaj(stare(R), True, _t("Am pus înapoi reglajele păstrate."))
	valori = {}
	for cheie in r.chei():
		if cheie not in argumente:
			continue
		try:
			p = int(argumente[cheie])
		except (TypeError, ValueError):
			p = None
		if p not in R.pozitii(cheie):
			return _cuMesaj(stare(R), False, _t("Valoare în afara gamei: %s.") % cheie)
		valori[cheie] = p
	if not valori:
		return _cuMesaj(stare(R), False, _t("Nu s-a trimis nicio setare."))
	for cheie, p in valori.items():
		R.element(cheie).value = str(p)
	if argumente.get("incearca") == "1":
		bine = R.incearca()
		if not bine:
			return _cuMesaj(stare(R), False, r.eroare or _t("Placa nu a primit această valoare."))
		return _cuMesaj(stare(R), True, _t("Se vede acum pe televizor. Apasă „Păstrează” ca să rămână."))
	bine = R.salveaza()
	if not bine:
		return _cuMesaj(stare(R), False, r.eroare or _t("Placa nu a primit această valoare."))
	return _cuMesaj(stare(R), True, _t("Păstrat. Se vede și pe televizor."))


def implicite(argumente, R=None):
	"""POST /api/reglaje-imagine-implicite."""
	R = _r(R)
	if not R.reglaje().oferit:
		return _cuMesaj(stare(R), False, _t("Receptorul acesta nu are reglaje pentru imagine."))
	R.initConfig()
	R.implicite(salveaza_acum=True)
	return _cuMesaj(stare(R), True, _t("Reglajele au acum valorile din fabrică."))


def argumente(request, R=None):
	"""Argumentele cererii ca text, numai cheile cunoscute (reglajele, incearca, renunta)."""
	try:
		chei = set(_r(R).CHEI) | set(("incearca", "renunta"))
	except Exception:
		chei = set(("incearca", "renunta"))
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in chei:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v).strip()
	return rez


def rute(baza, R=None):
	"""{nume: resursa de sub /api}. `baza` e HdsJsonResource din plugin.py."""

	def _raspunsSigur(self, request, functie):
		try:
			return self._raspunde(request, functie())
		except Exception as eroare:
			return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class StareResource(baza):
		def render_GET(self, request):
			return _raspunsSigur(self, request, lambda: stare(R))

	class _Schimba(baza):
		schimbaCeva = True
		functie = None

		def render_POST(self, request):
			return _raspunsSigur(self, request, lambda: self.functie(argumente(request, R)))

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(_Schimba):
		def functie(self, a):
			return seteaza(a, R=R)

	class ImpliciteResource(_Schimba):
		def functie(self, a):
			return implicite(a, R=R)

	return {
		b"reglaje-imagine": StareResource(),
		b"reglaje-imagine-seteaza": SeteazaResource(),
		b"reglaje-imagine-implicite": ImpliciteResource(),
	}


# etichetele fixe ale paginii: __T_<CHEIE>__ in PAGINA, traduse si scapate pentru HTML
ETICHETE = {
	"TITLU": N_("Calitatea imaginii"),
	"INCARCARE": N_("Se citesc reglajele..."),
	"REGLAJE": N_("Reglaje"),
	"PASTREAZA": N_("Păstrează"),
	"RENUNTA": N_("Renunță"),
	"IMPLICITE": N_("Înapoi la implicite"),
}

NOTA_JOS = N_("Aceleași reglaje sunt pe televizor, în %s. Ce se vede cu adevărat se judecă pe televizor: capturile de ecran nu arată prelucrarea plăcii.")

TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi reglajele."),
	"lipsa": N_("Receptorul acesta nu are reglaje pentru imagine."),
	"nu_raspunde_retea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"fabrica": N_("Din fabrică: %s."),
	"pe_loc": N_("Ce schimbi se vede pe loc pe televizor."),
	"nepastrat": N_("Ai schimbări nepăstrate: rămân numai după „Păstrează”."),
	"confirma": N_("Pui înapoi valorile din fabrică?"),
}


def _json(obiect):
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


def pagina_text(stil, config_pagina, drum="Meniu", limba="ro"):
	"""Pagina cu etichetele traduse si scapate pentru HTML; drum = HTML-ul drumului din meniul televizorului."""
	import html
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA_JOS), quote=True)
	nota = nota.replace("%s", drum, 1) if "%s" in nota else nota
	return (text.replace("__LIMBA__", limba).replace("__NOTA_JOS__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
		.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina))


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:980px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .rand{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 12px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  .reglaj{display:grid;grid-template-columns:minmax(150px,230px) 1fr 72px;gap:4px 12px;align-items:center;padding:6px 0;border-bottom:1px solid var(--bordura);}
  .reglaj .nume{font-weight:bold;}
  .reglaj .val{text-align:right;font-variant-numeric:tabular-nums;}
  .reglaj input[type=range]{width:100%;min-height:36px;accent-color:#9fb4ff;}
  .reglaj .desc{grid-column:1 / -1;color:var(--text-slab);font-size:.82rem;line-height:1.4;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:640px){ .reglaj{grid-template-columns:1fr 64px;} .reglaj input[type=range]{grid-column:1 / -1;grid-row:2;} }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>__T_REGLAJE__</h2>
    <p class="nota" id="pe_loc"></p>
    <div id="lista"></div>
    <div class="rand" style="margin-top:12px">
      <button type="button" class="verde" id="pastreaza">__T_PASTREAZA__</button>
      <button type="button" id="renunta">__T_RENUNTA__</button>
      <button type="button" id="implicite">__T_IMPLICITE__</button>
    </div>
    <p class="nota" id="nepastrat"></p>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <p class="nota">__NOTA_JOS__</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var TXT = __TEXTE_JS__;
var D = null, SCHIMBAT = false, CEAS = null, NODURI = {};
function $(id){ return document.getElementById(id); }
function fmt(t){ var a = Array.prototype.slice.call(arguments, 1); return String(t).replace(/%s/g, function(){ return a.length ? String(a.shift()) : ""; }); }
function adresa(cale){ if(!CFG.jeton){ return cale; } return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton); }
function cerere(cale, metoda, date){
  var o = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ o.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ o.headers["Content-Type"] = "application/x-www-form-urlencoded"; o.body = date.toString(); }
  return fetch(adresa(cale), o).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: fmt(TXT.neasteptat, r.status)}; });
  });
}
function mesaj(t, e){ var m = $("mesaj"); m.textContent = t || ""; m.classList.toggle("eroare", !!e); }
function textPoz(r, p){ var t = String(p); r.alegeri.forEach(function(a){ if(a[0] === p){ t = a[1]; } }); return t; }
function construieste(d){
  var l = $("lista"); l.textContent = ""; NODURI = {};
  d.reglaje.forEach(function(r){
    var rand = document.createElement("div"); rand.className = "reglaj";
    var n = document.createElement("label"); n.className = "nume"; n.textContent = r.nume; n.htmlFor = "r_" + r.cheie;
    var poz = r.alegeri.map(function(a){ return a[0]; });
    var g = document.createElement("input"); g.type = "range"; g.id = "r_" + r.cheie;
    g.min = poz[0]; g.max = poz[poz.length - 1]; g.step = poz.length > 1 ? poz[1] - poz[0] : 1; g.value = r.valoare;
    var v = document.createElement("span"); v.className = "val"; v.textContent = textPoz(r, r.valoare);
    var e = document.createElement("div"); e.className = "desc"; e.textContent = r.descriere + " " + fmt(TXT.fabrica, r.fabrica_text);
    g.addEventListener("input", function(){ v.textContent = textPoz(r, parseInt(g.value, 10)); schimbare(); });
    rand.appendChild(n); rand.appendChild(g); rand.appendChild(v); rand.appendChild(e); l.appendChild(rand);
    NODURI[r.cheie] = g;
  });
  SCHIMBAT = false; $("nepastrat").textContent = ""; $("pe_loc").textContent = TXT.pe_loc;
}
function valori(){ var q = {}; Object.keys(NODURI).forEach(function(k){ q[k] = NODURI[k].value; }); return q; }
function trimite(cale, v){
  var q = new URLSearchParams(); Object.keys(v).forEach(function(k){ q.set(k, v[k]); });
  return cerere(cale, "POST", q).then(function(d){ if(d.result){ D = d; } return d; })
    .catch(function(){ return {result: false, message: TXT.nu_raspunde}; });
}
function schimbare(){
  mesaj(""); SCHIMBAT = true; $("nepastrat").textContent = TXT.nepastrat;
  clearTimeout(CEAS);
  CEAS = setTimeout(function(){ var v = valori(); v.incearca = "1"; trimite("/api/reglaje-imagine-seteaza", v).then(function(d){ if(!d.result){ mesaj(d.message, true); } }); }, 200);
}
function dupa(d){ mesaj(d.message, !d.result); if(d.result){ construieste(d); } }
$("pastreaza").addEventListener("click", function(){ trimite("/api/reglaje-imagine-seteaza", valori()).then(dupa); });
$("renunta").addEventListener("click", function(){ trimite("/api/reglaje-imagine-seteaza", {renunta: "1"}).then(dupa); });
$("implicite").addEventListener("click", function(){ if(!confirm(TXT.confirma)){ return; } trimite("/api/reglaje-imagine-implicite", {}).then(dupa); });
cerere("/api/reglaje-imagine").then(function(d){
  if(!d.result){ $("incarcare").textContent = d.message || TXT.necitit; return; }
  if(!d.oferit){ $("incarcare").textContent = TXT.lipsa; return; }
  D = d; $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns"); construieste(d);
}).catch(function(){ $("incarcare").textContent = TXT.nu_raspunde_retea; });
</script>
</body>
</html>
"""


# Textele sabloanului de mai sus traduse la cerere (traducere_pagini.py); un text nou in sablon se scrie si aici.
TEXTE_PAGINA = {
	"html": (
	),
	"js": (
		N_("browser deconectat"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

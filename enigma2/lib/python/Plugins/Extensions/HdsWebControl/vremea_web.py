# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Vremea din acelasi serviciu si aceleasi setari ca pe televizor.

Citirea starii foloseste numai memoria. Cautarea oraselor lucreaza pe un fir
separat. Salvarea trece prin poarta comuna pentru POST si CSRF.
"""


def _v(V=None):
	if V is not None:
		return V
	from Components import HdsVremea
	return HdsVremea


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	return text


def stare(V=None):
	V = _v(V)
	V.initConfig()
	setari = dict(V.setari())
	date = dict(V.date() or {})
	if date.get("stare"):
		date["stare"] = _t(date["stare"])
	unitate = setari.get("unitate", "C")
	texte = {}
	for cheie in ("temperatura", "azi_min", "azi_max", "maine_min", "maine_max"):
		valoare = date.get(cheie)
		texte[cheie] = V.textTemperatura(valoare, unitate) if valoare is not None else ""
	return {"result": True, "setari": setari, "date": date, "texte": texte}


def seteaza(argumente, V=None):
	V = _v(V)
	V.initConfig()
	alegeri = {k: v for k, v in argumente.items() if k in ("unitate", "oras", "tema")}
	bun, mesaj = V.seteaza(alegeri)
	rez = stare(V)
	rez.update(result=bool(bun), message=_t(mesaj))
	return rez


def cauta(nume, V=None):
	"""Se cheama numai pe fir separat, niciodata direct din render_GET."""
	V = _v(V)
	rezultat = V.cautaOraseRezultat(nume)
	rez = []
	for oras in rezultat["orase"][:20]:
		cod = V.codOras(oras)
		if cod:
			rez.append({"nume": oras["nume"], "cod": cod})
	rezultat["orase"] = rez
	return rezultat


def argumente(request):
	limite = {"unitate": 8, "oras": 1024, "tema": 16, "q": 80}
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in limite:
			continue
		valoare = (valori or [b""])[0]
		if isinstance(valoare, bytes):
			valoare = valoare.decode("utf-8", "replace")
		rez[cheie] = str(valoare)[:limite[cheie]].strip()
	return rez


def rute(baza, resource, V=None, pe_fir=None, neterminat=None):
	"""Rutele paginii si ale API, cu aceeasi poarta ca restul setarilor."""
	def eroare(resursa, request, text, cod=503):
		return resursa._eroare(request, _t(text), cod)

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(V))
			except Exception as e:
				print("[HdsWebControl] vremea: %s" % type(e).__name__)
				return eroare(self, request, "Setările vremii nu se pot citi acum.")

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), V))
			except Exception as e:
				print("[HdsWebControl] salvare vremea: %s" % type(e).__name__)
				return eroare(self, request, "Setările vremii nu se pot salva acum.")

		def render_GET(self, request):
			return self.render_POST(request)

	class OraseResource(baza):
		def render_GET(self, request):
			nume = argumente(request).get("q", "")
			if len(nume) < 2:
				return eroare(self, request, "Scrie cel puțin două litere din numele orașului.", 400)
			try:
				W = _v(V)
				W.initConfig()
				if pe_fir is None:
					from twisted.internet.threads import deferToThread
				else:
					deferToThread = pe_fir
				if neterminat is None:
					from twisted.web.server import NOT_DONE_YET
				else:
					NOT_DONE_YET = neterminat
				inchisa = [False]

				def deconectata(motiv):
					inchisa[0] = True
					return None

				def gata(rezultat):
					if not inchisa[0] and not getattr(request, "finished", False):
						request.write(self._raspunde(request, rezultat))
						request.finish()
					return None

				def esec(motiv):
					return gata({"result": False, "orase": [], "message":
						W.mesajCautare("serviciu"), "motiv": "serviciu"})

				request.notifyFinish().addErrback(deconectata)
				deferToThread(cauta, nume, W).addCallbacks(gata, esec)
				return NOT_DONE_YET
			except Exception as e:
				print("[HdsWebControl] cautare oras: %s" % type(e).__name__)
				return eroare(self, request, _v(V).mesajCautare("serviciu"))

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina
			return pagina(request, pagina_text)

	return ({b"vremea": StareResource(), b"vremea-seteaza": SeteazaResource(),
		b"vremea-orase": OraseResource()}, {b"vremea": PaginaResource()})


def pagina_text(stil, config_pagina):
	from .meniu_comun_web import sablon
	return sablon(_traducePagina(PAGINA), stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vremea</title>
<style>__STIL_COMUN__ __STIL_PAGINI__
  .cautare{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
  .cautare input{flex:1;min-width:160px;}
  .legaturi{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0;}
  #oras{width:100%;}
  #orasAcum{font:inherit;text-align:left;}
</style>
</head>
<body>
<main>
<h1>Vremea</h1>
<p class="nota">Aceleași setări pentru afișajul din față și pentru televizor.</p>
<p class="mesaj" id="mesaj" role="status" aria-live="polite">Se citesc setările...</p>
<form id="setari" class="card ascuns">
  <div class="rand">
    <label for="unitate">Unitatea temperaturii</label>
    <select id="unitate">
      <option value="C">Celsius (°C)</option>
      <option value="F">Fahrenheit (°F)</option>
      <option value="K">Kelvin (K)</option>
    </select>
  </div>
  <div class="rand">
    <label for="oras">Orașul</label>
    <select id="oras"><option value="">Automat după fusul orar sau țară</option></select>
  </div>
  <div class="cautare">
    <input id="nume" type="search" maxlength="80" autocomplete="off"
      placeholder="Caută un oraș după nume" aria-label="Caută un oraș după nume">
    <button type="button" id="cauta">Caută</button>
  </div>
  <p class="nota" id="rezultate" role="status" aria-live="polite"></p>
  <div class="rand">
    <label for="tema">Vremea pe televizor</label>
    <select id="tema">
      <option value="nu">Nu se afișează</option>
      <option value="bara">În bara de informații</option>
      <option value="principal">Pe ecranul principal</option>
      <option value="ambele">În ambele locuri</option>
    </select>
  </div>
  <div class="butoane"><button type="submit" id="salveaza" class="principal">Salvează</button></div>
  <p class="nota">Pe afișajul din față, alege vremea din lista de rotire.</p>
</form>
<p class="nota"><button type="button" id="orasAcum" class="ascuns" aria-controls="nume"
  title="Caută un oraș după nume"></button> <span id="acum"></span></p>
<nav class="legaturi">
  <a id="temaLegatura" href="/tema-tv">Tema interfeței</a>
  <a id="afisajLegatura" href="/afisaj">Afișajul din față</a>
</nav>
</main>
<script>
__SCRIPT_COMUN__
var salvate = null;
var cautareInitiala = (new URLSearchParams(window.location.search).get("q") || "").slice(0, 80);
function optiune(valoare, nume){
  var o = document.createElement("option"); o.value = valoare; o.textContent = nume;
  return o;
}
function arata(d){
  salvate = d.setari;
  $("unitate").value = salvate.unitate;
  $("tema").value = salvate.tema;
  var s = $("oras");
  while(s.options.length > 1){ s.remove(1); }
  if(salvate.oras){ s.appendChild(optiune(salvate.oras, salvate.oras_nume)); }
  s.value = salvate.oras || "";
  var v = d.date || {}, t = d.texte || {};
  $("orasAcum").textContent = v.oras || salvate.oras_nume || s.options[0].textContent;
  $("orasAcum").classList.remove("ascuns");
  $("acum").textContent = t.temperatura ?
    [t.temperatura, v.stare].filter(Boolean).join(", ") : "";
  $("setari").classList.remove("ascuns");
}
$("orasAcum").addEventListener("click", function(){
  $("nume").focus(); $("nume").select();
});
function cauta(){
  var nume = $("nume").value.trim();
  if(nume.length < 2){
    $("rezultate").textContent = "Scrie cel puțin două litere din numele orașului."; return;
  }
  $("cauta").disabled = true; $("salveaza").disabled = true;
  $("rezultate").textContent = "Se caută orașele...";
  cerere("/api/vremea-orase?q=" + encodeURIComponent(nume)).then(function(d){
    if(!d.result){
      $("rezultate").textContent = d.message || "Receptorul nu răspunde."; return;
    }
    var s = $("oras"), ales = s.value;
    var numeAles = s.selectedIndex >= 0 ? s.options[s.selectedIndex].textContent : "";
    while(s.options.length > 1){ s.remove(1); }
    if(ales){ s.appendChild(optiune(ales, numeAles)); }
    (d.orase || []).forEach(function(o){
      if(!Array.from(s.options).some(function(x){ return x.value === o.cod; })){
        s.appendChild(optiune(o.cod, o.nume));
      }
    });
    s.value = Array.from(s.options).some(function(o){ return o.value === ales; }) ? ales : "";
    $("rezultate").textContent = d.orase && d.orase.length ?
      "Alege orașul din listă, apoi salvează." : d.message;
    if(d.orase && d.orase.length){ s.focus(); }
  }).catch(function(){ $("rezultate").textContent = "Receptorul nu răspunde."; })
    .finally(function(){ $("cauta").disabled = false; $("salveaza").disabled = false; });
}
$("cauta").addEventListener("click", cauta);
$("nume").addEventListener("keydown", function(e){
  if(e.key === "Enter"){ e.preventDefault(); if(!$("cauta").disabled){ cauta(); } }
});
$("setari").addEventListener("submit", function(e){
  e.preventDefault();
  var q = new URLSearchParams();
  ["unitate", "oras", "tema"].forEach(function(k){ q.set(k, $(k).value); });
  $("salveaza").disabled = true; $("cauta").disabled = true;
  mesaj("Se salvează...");
  cerere("/api/vremea-seteaza", "POST", q).then(function(d){
    if(d.result){ arata(d); $("rezultate").textContent = ""; }
    mesaj(d.message || (d.result ? "Setările au fost salvate." : "Setările nu au fost salvate."), !d.result);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); })
    .finally(function(){ $("salveaza").disabled = false; $("cauta").disabled = false; });
});
$("temaLegatura").href = adresa("/tema-tv");
$("afisajLegatura").href = adresa("/afisaj");
cerere("/api/vremea").then(function(d){
  if(d.result){
    arata(d); mesaj("");
    if(cautareInitiala){
      $("nume").value = cautareInitiala; cautareInitiala = ""; cauta();
    }
  }
  else { mesaj(d.message || "Setările vremii nu se pot citi acum.", true); }
}).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
</script>
</body>
</html>
"""


TEXTE_PAGINA = {
	"html": (
		N_("Vremea"),
		N_("Aceleași setări pentru afișajul din față și pentru televizor."),
		N_("Se citesc setările..."),
		N_("Unitatea temperaturii"),
		N_("Celsius (°C)"),
		N_("Fahrenheit (°F)"),
		N_("Kelvin (K)"),
		N_("Orașul"),
		N_("Automat după fusul orar sau țară"),
		N_("Caută un oraș după nume"),
		N_("Caută"),
		N_("Vremea pe televizor"),
		N_("Nu se afișează"),
		N_("În bara de informații"),
		N_("Pe ecranul principal"),
		N_("În ambele locuri"),
		N_("Salvează"),
		N_("Pe afișajul din față, alege vremea din lista de rotire."),
		N_("Tema interfeței"),
		N_("Afișajul din față"),
	),
	"js": (
		N_("Scrie cel puțin două litere din numele orașului."),
		N_("Se caută orașele..."),
		N_("Alege orașul din listă, apoi salvează."),
		N_("Se salvează..."),
		N_("Setările au fost salvate."),
		N_("Setările nu au fost salvate."),
		N_("Receptorul nu răspunde."),
		N_("Setările vremii nu se pot citi acum."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

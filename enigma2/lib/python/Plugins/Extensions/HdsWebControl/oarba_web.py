# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# oarba_web.py: 'Căutare oarbă pe satelit' in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Meniu > Scanare > Satelit > Căutare oarbă, Screens/ScanerOarba.py).
#
# Aceeasi cautare ca pe televizor, din acelasi cod (Components/HdsCautareOarba.py): o singura cautare pe receptor,
# pornita de aici sau din telecomanda, cu aceleasi alegeri (banda, polarizarile, rata minima), acelasi progres si
# aceeasi lista (fiecare transponder cunoscut al satelitului cu 'găsit' / 'se caută', cele noi cu 'nou'), apoi
# 'Scanează canalele' (ServiceScan pe televizor, ca la celelalte scanari).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/oarba                                       alegerile, previzualizarea si starea cautarii
#   POST /api/oarba-porneste?banda=&polarizari=&trepte=&rata_min=  porneste cautarea (pe televizor si ecranul ei)
#   POST /api/oarba-opreste                               o opreste curat (dupa bucata de banda in curs)
#   POST /api/oarba-scaneaza                              'Scanează canalele' pe televizor
#   POST /api/oarba-televizor                             deschide ecranul pe televizor
#   GET  /oarba                                           pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2, ca si programul (eConsoleAppContainer); citirea starii e
# mica. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau creierul (O) si sesiunea lor.


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


CHEI_CERERE = ("banda", "polarizari", "trepte", "rata_min")


def _o(O=None):
	if O is not None:
		return O
	from Components import HdsCautareOarba
	return HdsCautareOarba


def _jurnal(text):
	print("[HdsWebControl] oarba: %s" % text)


def _in_standby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


def _antena(O, sesiune):
	try:
		return O.antena(sesiune)
	except Exception as eroare:
		_jurnal("antena: %s" % eroare)
		return {"motiv": _t("Nu pot citi setările tunerului de satelit."), "osc": None, "nume": "", "motor": False,
			"sateliti": [], "pozitie": None, "slot": None}


def stare(sesiune=None, O=None, argumente=None):
	"""Ce arata pagina: alegerile (valorile ultimei folosiri, peste care vin cele bune din cerere, numai pentru
	previzualizare: nimic nu se salveaza), previzualizarea si starea cautarii."""
	O = _o(O)
	a = _antena(O, sesiune)
	valori = dict(O.ULTIMELE)
	for cheie, v in (argumente or {}).items():
		if cheie in CHEI_CERERE and O.valoare_buna(cheie, v):
			valori[cheie] = v
	doua = O.are_doua_benzi(a.get("osc"))
	campuri = []
	if doua:
		campuri.append({"cheie": "banda", "eticheta": _t("Banda"), "optiuni": O.alegeri_traduse("banda")})
	campuri.append({"cheie": "polarizari", "eticheta": _t("Polarizările"), "optiuni": O.alegeri_traduse("polarizari")})
	campuri.append({"cheie": "trepte", "eticheta": _t("Treptele căutării"), "optiuni": O.alegeri_traduse("trepte")})
	campuri.append({"cheie": "rata_min", "eticheta": _t("Rata minimă"), "optiuni": O.alegeri_traduse("rata_min")})
	c = O.cautare()
	return {"result": True, "satelit": O.text_satelit(a), "motiv": a.get("motiv") or "", "motor": bool(a.get("motor")),
		"campuri": campuri, "valori": valori, "previzualizare": O.text_previzualizare(a, valori),
		"standby": _in_standby(), "cautare": c.stare()}


def _alta_scanare(sesiune):
	"""Textul refuzului cand pe televizor e deschisa alta scanare (ServiceScan sau DVB-T2 / DAB+), altfel None."""
	try:
		from . import scanare_web as W
	except ImportError:
		return None
	try:
		if W._dialogScanare(sesiune)[0] is not None or W._dialogFluxuri(sesiune)[0] is not None:
			return _t("O altă scanare e deschisă pe televizor. Așteaptă să se termine sau închide-o, apoi încearcă din "
				"nou.")
	except Exception as eroare:
		_jurnal("ferestrele de scanare: %s" % eroare)
	return None


def _deschide_ecranul(sesiune):
	"""Ecranul cautarii pe televizor (daca nu e deja in fata); nu in standby."""
	if sesiune is None or _in_standby():
		return False
	try:
		from Screens.ScanerOarba import ScanerOarba
		if isinstance(getattr(sesiune, "current_dialog", None), ScanerOarba):
			return True
		return sesiune.open(ScanerOarba) is not None
	except Exception as eroare:
		_jurnal("ecranul pe televizor: %s" % eroare)
		return False


def porneste(argumente, sesiune=None, O=None):
	O = _o(O)
	config = dict(O.ULTIMELE)
	for cheie in CHEI_CERERE:
		v = argumente.get(cheie)
		if v is None or v == "":
			continue
		if not O.valoare_buna(cheie, v):
			return {"result": False, "message": _t("Valoare necunoscută pentru %s.") % cheie}
		config[cheie] = v
	if sesiune is None:
		return {"result": False, "message": _t("Interfața web nu are încă legătura cu ecranul receptorului. Așteaptă "
			"pornirea completă a receptorului sau repornește-l, apoi încearcă din nou.")}
	refuz = _alta_scanare(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	O.ULTIMELE.update(config)
	refuz = O.porneste_pe_receptor(sesiune, O.cerere_din(config))
	if refuz:
		return {"result": False, "message": refuz, "stare": stare(sesiune, O)}
	pe_tv = _deschide_ecranul(sesiune)
	_jurnal("cautare oarba pornita din web (%s)" % ", ".join("%s=%s" % x for x in sorted(config.items())))
	text = _t("Căutarea a pornit.")
	if not pe_tv:
		text += " " + _t("Televizorul nu o arată acum (receptorul e în standby sau ecranul nu s-a deschis), dar merge.")
	return {"result": True, "message": text, "stare": stare(sesiune, O)}


def opreste(sesiune=None, O=None):
	O = _o(O)
	if not O.cautare().opreste():
		return {"result": False, "message": _t("Nicio căutare oarbă în curs."), "stare": stare(sesiune, O)}
	return {"result": True, "message": _t("Căutarea se oprește după bucata de bandă în curs."),
		"stare": stare(sesiune, O)}


def scaneaza(sesiune=None, O=None):
	O = _o(O)
	if sesiune is None:
		return {"result": False, "message": _t("Interfața web nu are încă legătura cu ecranul receptorului.")}
	if _in_standby():
		return {"result": False, "message": _t("Receptorul este în standby. Pornește-l din telecomandă, apoi încearcă "
			"din nou.")}
	refuz = _alta_scanare(sesiune) or O.scaneaza_canalele(sesiune)
	if refuz:
		return {"result": False, "message": refuz, "stare": stare(sesiune, O)}
	return {"result": True, "message": _t("Scanarea canalelor a pornit pe televizor. Rezultatul se vede pe pagina "
		"Scanare și antenă."), "stare": stare(sesiune, O)}


def televizor(sesiune=None, O=None):
	O = _o(O)
	if _in_standby():
		return {"result": False, "message": _t("Receptorul este în standby. Pornește-l din telecomandă, apoi încearcă "
			"din nou.")}
	if not _deschide_ecranul(sesiune):
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor. Detalii în jurnalul receptorului.")}
	return {"result": True, "message": _t("S-a deschis pe televizor: %s.") % _t("Căutare oarbă pe satelit")}


def argumente(request):
	"""Argumentele cunoscute ale cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:20]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in CHEI_CERERE:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:16].strip()
	return rez


def rute(baza, resource, sesiune=None, O=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	intoarce sesiunea enigma2 tinuta de plugin.py."""

	def _sesiune():
		try:
			return sesiune() if callable(sesiune) else sesiune
		except Exception:
			return None

	def _cu_eroare(self, request, f):
		try:
			return self._raspunde(request, f())
		except Exception as eroare:
			_jurnal("cererea: %s" % eroare)
			return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class StareResource(baza):
		"""GET /api/oarba: numai citire."""

		def render_GET(self, request):
			return _cu_eroare(self, request, lambda: stare(_sesiune(), O, argumente(request)))

	class PornesteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _cu_eroare(self, request, lambda: porneste(argumente(request), _sesiune(), O))

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class OpresteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _cu_eroare(self, request, lambda: opreste(_sesiune(), O))

		def render_GET(self, request):
			return self.render_POST(request)

	class ScaneazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _cu_eroare(self, request, lambda: scaneaza(_sesiune(), O))

		def render_GET(self, request):
			return self.render_POST(request)

	class TelevizorResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _cu_eroare(self, request, lambda: televizor(_sesiune(), O))

		def render_GET(self, request):
			return self.render_POST(request)

	class PaginaResource(resource.Resource):
		"""GET /oarba: pagina."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"oarba": StareResource(),
		b"oarba-porneste": PornesteResource(),
		b"oarba-opreste": OpresteResource(),
		b"oarba-scaneaza": ScaneazaResource(),
		b"oarba-televizor": TelevizorResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic si /dabt2."""
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); fara pachet (probele de pe PC) ramane 'Meniu'."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return (_traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)
		.replace("__DRUM__", _drumMeniu("hds_satelit_oarba")))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Căutare oarbă pe satelit</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0;}
  button{background:#242a33;color:var(--text);border:1px solid var(--bordura);border-radius:8px;padding:10px 14px;min-height:44px;font:inherit;cursor:pointer;}
  button.principal{background:var(--accent);border-color:var(--accent);}
  button:disabled{opacity:.5;cursor:default;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,280px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  .bara{height:10px;border-radius:5px;background:#0f1216;border:1px solid var(--bordura);overflow:hidden;margin:10px 0 0;}
  .bara div{height:100%;width:0;background:var(--accent);transition:width .4s;}
  table{width:100%;border-collapse:collapse;margin:10px 0 0;font-size:.92rem;}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bordura);}
  th{color:var(--text-slab);font-weight:600;}
  td.numar{text-align:right;font-variant-numeric:tabular-nums;}
  .gasit{color:var(--text);}
  .nou{color:var(--galben);font-weight:600;}
  .cunoscut,.negasit,.neverificat{color:var(--text-slab);}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Căutare oarbă pe satelit</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="acum">Satelit: <b id="satelit"></b></p>
    <div id="campuri"></div>
    <p class="nota" id="previzualizare"></p>
    <div class="butoane">
      <button type="button" class="principal" id="cauta">Caută acum</button>
      <button type="button" id="opreste">Oprește căutarea</button>
      <button type="button" id="scaneaza">Scanează canalele</button>
      <button type="button" id="televizor">Deschide pe televizor</button>
    </div>
    <p class="nota">Pe televizor: <span>__DRUM__</span>.</p>
  </section>
  <section class="card">
    <p class="acum" id="stare" role="status"></p>
    <div class="bara"><div id="progres"></div></div>
    <table id="tabel" class="ascuns">
      <thead><tr><th>Frecvența (MHz)</th><th>Polarizarea</th><th>Rata (kSym/s)</th><th>Starea</th></tr></thead>
      <tbody id="randuri"></tbody>
    </table>
  </section>
  <p class="mesaj" id="mesaj" role="status"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var S = {semn: "", urmarire: null, valori: {}};
function $(id){ return document.getElementById(id); }
function el(tag, cls, text){ var e = document.createElement(tag); if(cls){ e.className = cls; } if(text !== undefined){ e.textContent = text; } return e; }
function arata(e, da){ e.classList.toggle("ascuns", !da); }
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
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function deseneazaCampurile(d){
  var cutie = $("campuri");
  var semn = JSON.stringify(d.campuri);
  if(cutie.dataset.semn === semn){
    d.campuri.forEach(function(c){ var s = $("c_" + c.cheie); if(s && document.activeElement !== s){ s.value = d.valori[c.cheie]; } });
    return;
  }
  cutie.dataset.semn = semn;
  cutie.textContent = "";
  d.campuri.forEach(function(c){
    var r = el("div", "rand"), l = el("label", "", c.eticheta), s = el("select");
    s.id = "c_" + c.cheie; l.htmlFor = s.id;
    c.optiuni.forEach(function(o){ var x = el("option", "", o[1]); x.value = o[0]; s.appendChild(x); });
    s.value = d.valori[c.cheie];
    r.appendChild(l); r.appendChild(s); cutie.appendChild(r);
  });
}
function deseneaza(d){
  $("satelit").textContent = d.cautare.satelit || d.satelit;
  deseneazaCampurile(d);
  $("previzualizare").textContent = d.previzualizare;
  var c = d.cautare;
  $("stare").textContent = c.text || "";
  $("progres").style.width = (c.faza === "nimic" ? 0 : c.procent) + "%";
  $("cauta").disabled = c.in_curs || !!d.motiv;
  $("opreste").disabled = !c.in_curs || c.faza === "opreste";
  $("scaneaza").disabled = !c.poate_scana || d.standby;
  $("televizor").disabled = d.standby;
  Array.prototype.forEach.call(document.querySelectorAll("#campuri select"), function(s){ s.disabled = c.in_curs; });
  var semn = JSON.stringify(c.randuri);
  if(semn !== S.semn){
    S.semn = semn;
    var corp = $("randuri"); corp.textContent = "";
    c.randuri.forEach(function(r){
      var tr = el("tr", r.stare);
      tr.appendChild(el("td", "numar", String(r.mhz)));
      tr.appendChild(el("td", "", r.pol));
      tr.appendChild(el("td", "numar", String(r.ksym)));
      tr.appendChild(el("td", "", r.text_stare));
      corp.appendChild(tr);
    });
    arata($("tabel"), c.randuri.length > 0);
  }
  if(c.in_curs && !S.urmarire){ S.urmarire = setTimeout(function(){ S.urmarire = null; citeste(); }, 1500); }
}
function alese(){
  var q = new URLSearchParams();
  Array.prototype.forEach.call(document.querySelectorAll("#campuri select"), function(s){ q.set(s.id.slice(2), s.value); });
  return q;
}
function citeste(){
  return cerere("/api/oarba?" + alese().toString()).then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    deseneaza(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, q, text){
  mesaj(text || "Se trimite...");
  return cerere(cale, "POST", q || new URLSearchParams()).then(function(d){
    mesaj(d.message, !d.result);
    if(d.stare){ deseneaza(d.stare); }
    return d;
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("cauta").addEventListener("click", function(){ trimite("/api/oarba-porneste", alese(), "Se pornește căutarea..."); });
$("opreste").addEventListener("click", function(){ trimite("/api/oarba-opreste", null, "Se oprește..."); });
$("scaneaza").addEventListener("click", function(){ trimite("/api/oarba-scaneaza", null, "Se pornește scanarea canalelor..."); });
$("televizor").addEventListener("click", function(){ trimite("/api/oarba-televizor", null, "Se deschide pe televizor..."); });
// o alegere schimbata: numai previzualizarea (cat dureaza, cate treceri); se salveaza abia la 'Caută acum'
document.addEventListener("change", function(e){
  if(e.target && e.target.id && e.target.id.indexOf("c_") === 0){ citeste(); }
});
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginii
# Textele sablonului de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text nou sau
# schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Căutare oarbă pe satelit"),
		N_("Se citește starea..."),
		N_("Satelit: <b id=\"satelit\"></b>"),
		N_("Caută acum"),
		N_("Oprește căutarea"),
		N_("Scanează canalele"),
		N_("Deschide pe televizor"),
		N_("Pe televizor: <span>__DRUM__</span>."),
		N_("Frecvența (MHz)"),
		N_("Polarizarea"),
		N_("Rata (kSym/s)"),
		N_("Starea"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Se pornește căutarea..."),
		N_("Se oprește..."),
		N_("Se pornește scanarea canalelor..."),
		N_("Se deschide pe televizor..."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)

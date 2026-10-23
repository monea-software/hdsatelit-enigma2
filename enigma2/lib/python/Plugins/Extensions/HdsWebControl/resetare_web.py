# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# resetare_web.py: doua intrari din Meniu > Setari > Sistem & Dispozitive in interfata web (HdsWebControl):
# - /resetare-fabrica: Revenire la setarile din fabrica (factory_reset; pe televizor codul din data/menu.xml, cu
#   intrebarea din Screens/FactoryReset.py). Aici: ce se pierde si ce ramane, o bifa obligatorie (Inteleg ca se pierd
#   toate setarile, verificata si aici, nu numai in pagina), confirmarea in doi pasi, apoi aceiasi pasi ca pe televizor
#   (Components/HdsResetareFabrica.reseteaza), pornit dupa 1,5 s ca raspunsul sa plece inainte de iesirea interfetei.
# - /curatenie: Curatenia discului (hds_cleanup_wizard, Screens/CleanupWizard.py): aceleasi doua categorii, cu dosarul si
#   marimea, golirea uneia cu confirmare in doi pasi si rezultatul (fisiere sterse, spatiu eliberat), din aceeasi logica
#   (Components/HdsCuratenie.py).
# Ambele actiuni se fac numai din browserul conectat (nu cu ?token=).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/resetare-fabrica                              daca exista valorile din fabrica, inregistrarile in curs
#   POST /api/resetare-fabrica-fa?inteleg=1&pas=intreaba    intrebarea si codul
#   POST /api/resetare-fabrica-fa?inteleg=1&cod=<cod>       resetarea (peste 1,5 s; interfata iese si porneste din nou)
#   POST /api/resetare-fabrica-fa?pas=renunta               codul nu mai e bun
#   GET  /api/curatenie                                     categoriile cu marimile (pe un fir)
#   POST /api/curatenie-goleste?categorie=tmp|opkg_cache&pas=intreaba|renunta, sau &cod=<cod> (golirea, pe un fir)
#   GET  /resetare-fabrica, GET /curatenie                  paginile
#
# FIRUL: marimile si golirea citesc dosare intregi, deci merg pe un fir (meniu_comun_web.peFir), cate una odata;
# raspunsul pleaca din firul enigma2. Resetarea ruleaza pe firul enigma2, ca pe televizor (ea opreste interfata).
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulele lor (R, Cu, A) si dosarele.

CONFIRMARE_RESETARE = "resetare-fabrica"
CONFIRMARE_CURATENIE = "curatenie"
DUPA_MS = 1500
TIMP_FIR_S = 300
CHEI_RESETARE = ("inteleg", "pas", "cod")
CHEI_CURATENIE = ("categorie", "pas", "cod")

# cate o singura lucrare pe disc odata, in tot procesul (marimile sau golirea)
_FIR = {"marimi": [False], "golire": [False]}


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def _t(text):
	return _mc()._t(text)


def _r(R=None):
	if R is not None:
		return R
	from Components import HdsResetareFabrica
	return HdsResetareFabrica


def _cu(Cu=None):
	if Cu is not None:
		return Cu
	from Components import HdsCuratenie
	return HdsCuratenie


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAlimentare
	return HdsAlimentare


def _inregistrari(sesiune):
	try:
		return len(sesiune.nav.getRecordings() or [])
	except Exception:
		return 0


# ------------------------------------------------------------------ revenirea la setarile din fabrica

def stareResetare(R=None, sesiune=None):
	"""Pentru GET /api/resetare-fabrica."""
	return {"result": True, "implicite": bool(_r(R).implicitele()), "inregistrari": _inregistrari(sesiune)}


def _detaliiResetare(R, sesiune):
	d = [_t("Se pierd toate setările: listele de canale și favoritele, canalele găsite la scanare, setările antenei și "
		"ale tunerelor, programările înregistrărilor, setările interfeței web și browserele conectate la ea."),
		_t("Înregistrările de pe disc sau stick rămân."),
		_t("Interfața iese și pornește din nou singură. Browserul se conectează apoi din nou, cu codul de pe televizor.")]
	if _inregistrari(sesiune):
		d.append(_t("Înregistrările în curs se opresc."))
	if not R.implicitele():
		d.append(_t("Dosarul cu valorile din fabrică lipsește pe acest receptor: după revenire interfața pornește fără "
			"setări și fără liste de canale."))
	return d


def reseteaza(argumente, R=None, A=None, sesiune=None, fabrica_ceas=None, iesire=None):
	"""POST /api/resetare-fabrica-fa, in doi pasi si numai cu bifa (inteleg=1). Refuzul pentru ?token= il da resursa."""
	R = _r(R)
	MC = _mc()
	pas = argumente.get("pas", "")
	if pas == "renunta":
		MC.uita(CONFIRMARE_RESETARE)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if argumente.get("inteleg") != "1":
		return {"result": False, "message": _t("Bifează întâi că înțelegi că se pierd toate setările.")}
	if pas == "intreaba":
		return MC.raspunsIntrebare(CONFIRMARE_RESETARE, "", _t("Sigur revii la setările din fabrică?"),
			_t("Da, revino la setările din fabrică"), _detaliiResetare(R, sesiune))
	if not MC.verifica(CONFIRMARE_RESETARE, "", argumente.get("cod", "")):
		return MC.codGresit()
	MC.jurnal("revenirea la setarile din fabrica, ceruta din web")

	def acum():
		R.reseteaza(iesire=iesire)

	_a(A).programeaza(acum, DUPA_MS, fabrica_ceas, nume="resetare")
	return {"result": True, "reseteaza": True, "message": _t("Revenirea la setările din fabrică a început. Interfața "
		"pornește din nou; pagina se reîncarcă singură când receptorul răspunde și cere conectarea browserului.")}


# ------------------------------------------------------------------ curatenia discului

def marimi(Cu=None):
	"""Pentru GET /api/curatenie (pe un fir: citeste dosare intregi)."""
	return {"result": True, "categorii": _cu(Cu).marimi()}


def _ocupatDisc():
	return {"result": False, "ocupat": True, "message": _t("Se lucrează deja pe disc. Încearcă din nou peste câteva "
		"secunde.")}


def golesteIntrebare(argumente, Cu=None):
	"""Pasii fara fir ai lui POST /api/curatenie-goleste: cheia, renuntarea, intrebarea, codul. -> (raspuns, None) sau
	(None, cheia) cand codul e bun si golirea poate porni."""
	Cu = _cu(Cu)
	MC = _mc()
	cheie = argumente.get("categorie", "")
	c = Cu.categorie(cheie)
	if c is None:
		return {"result": False, "message": _t("Categorie necunoscută.")}, None
	_cheie, eticheta, cale, _excluse = c
	pas = argumente.get("pas", "")
	if pas == "renunta":
		MC.uita(CONFIRMARE_CURATENIE, cheie)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}, None
	if pas == "intreaba":
		return MC.raspunsIntrebare(CONFIRMARE_CURATENIE, cheie, _t("Ștergi conținutul: %s?") % eticheta,
			_t("Da, golește"), [_t("Calea: %s") % cale, _t("Acțiunea nu poate fi anulată."),
			_t("Fișierele active (socket-uri, de exemplu dialogul cu modulul CAM) și steagul probei prin stick se "
			"păstrează singure.")]), None
	if _FIR["golire"][0] or _FIR["marimi"][0]:
		return _ocupatDisc(), None
	if not MC.verifica(CONFIRMARE_CURATENIE, cheie, argumente.get("cod", "")):
		return MC.codGresit(), None
	return None, cheie


def goleste(cheie, Cu=None):
	"""Golirea propriu-zisa (pe un fir), ca Da pe ecran: rezultatul si marimile noi."""
	Cu = _cu(Cu)
	_cheie, eticheta, cale, _excluse = Cu.categorie(cheie)
	exista, sterse, eliberati = Cu.goleste(cheie)
	if not exista:
		rez = {"result": False, "message": _t("Dosarul %s nu există pe acest receptor.") % cale}
	else:
		rez = {"result": True, "sterse": sterse, "eliberati": eliberati,
			"message": _t("%s: %d fișiere șterse, %s eliberați.") % (eticheta, sterse, Cu.formatMB(eliberati))}
	rez["categorii"] = Cu.marimi()
	return rez


def _sigur(lucru):
	"""lucru() pe fir; o exceptie devine raspuns de eroare (nu textul comun al firului)."""
	def f():
		try:
			return lucru()
		except Exception as eroare:
			return {"result": False, "message": _t("Eroare pe receptor: %s") % eroare}, 500
	return f


# ------------------------------------------------------------------ rutele

def rute(baza, resource, R=None, Cu=None, A=None, sesiune=None, fabrica_ceas=None, iesire=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py; `sesiune` e o
	functie care intoarce sesiunea enigma2 (implicit cea tinuta de plugin.py)."""
	MC = _mc()

	def _ses():
		try:
			return sesiune() if sesiune is not None else MC.sesiune()
		except Exception:
			return None

	class StareResetareResource(baza):
		"""GET /api/resetare-fabrica: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stareResetare(R, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ReseteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = MC.numaiBrowser(request)
			if refuz:
				return self._eroare(request, refuz, 403)
			try:
				arg = MC.argumente(request, CHEI_RESETARE, 40)
				return self._raspunde(request, reseteaza(arg, R, A, _ses(), fabrica_ceas, iesire))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # cu ?token= refuzat; din browser poarta cere POST

	class CuratenieResource(baza):
		"""GET /api/curatenie: numai citire, pe un fir."""

		def render_GET(self, request):
			if _FIR["marimi"][0] or _FIR["golire"][0]:
				return self._raspunde(request, _ocupatDisc())
			return MC.peFir(request, _sigur(lambda: marimi(Cu)), _FIR["marimi"], TIMP_FIR_S, fabrica_ceas)

	class GolesteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = MC.numaiBrowser(request)
			if refuz:
				return self._eroare(request, refuz, 403)
			try:
				raspuns, cheie = golesteIntrebare(MC.argumente(request, CHEI_CURATENIE, 40), Cu)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			if raspuns is not None:
				return self._raspunde(request, raspuns)
			MC.jurnal("curatenia discului din web: %s" % cheie)
			return MC.peFir(request, _sigur(lambda: goleste(cheie, Cu)), _FIR["golire"], TIMP_FIR_S, fabrica_ceas)

		def render_GET(self, request):
			return self.render_POST(request)   # cu ?token= refuzat; din browser poarta cere POST

	class PaginaResetare(resource.Resource):
		"""GET /resetare-fabrica."""
		isLeaf = True

		def render_GET(self, request):
			return MC.pagina(request, pagina_resetare)

	class PaginaCuratenie(resource.Resource):
		"""GET /curatenie."""
		isLeaf = True

		def render_GET(self, request):
			return MC.pagina(request, pagina_curatenie)

	api = {
		b"resetare-fabrica": StareResetareResource(),
		b"resetare-fabrica-fa": ReseteazaResource(),
		b"curatenie": CuratenieResource(),
		b"curatenie-goleste": GolesteResource(),
	}
	return api, {b"resetare-fabrica": PaginaResetare(), b"curatenie": PaginaCuratenie()}


def pagina_resetare(stil, config_pagina):
	MC = _mc()
	return MC.sablon(_traducePagina(PAGINA_RESETARE), stil, config_pagina,
		{"__DRUM_MENIU__": MC.drumHtml("factory_reset")})


def pagina_curatenie(stil, config_pagina):
	MC = _mc()
	return MC.sablon(_traducePagina(PAGINA_CURATENIE), stil, config_pagina,
		{"__DRUM_MENIU__": MC.drumHtml("hds_cleanup_wizard")})


PAGINA_RESETARE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revenire la setările din fabrică</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .bifa{display:flex;align-items:center;gap:10px;min-height:44px;margin:12px 0 0;cursor:pointer;}
  .legatura{display:inline-flex;align-items:center;min-height:44px;}
</style>
</head>
<body>
<main>
<h1>Revenire la setările din fabrică</h1>
<section class="card">
  <h2>Ce se pierde</h2>
  <p class="intrebare">La revenirea la setările din fabrică se pierd TOATE setările receptorului.</p>
  <p class="nota">Se pierd: listele de canale și favoritele, canalele găsite la scanare, setările antenei și ale tunerelor (inclusiv datele sateliților), programările înregistrărilor, setările interfeței web și browserele conectate la ea.</p>
  <p class="nota">Rămân: înregistrările de pe disc sau stick.</p>
  <p class="nota">După revenire interfața pornește din nou singură. Browserul se conectează apoi din nou, cu codul de pe televizor. Dacă ai schimbat portul interfeței web, ea răspunde din nou pe portul 80.</p>
  <p class="nota eroare ascuns" id="faraImplicite">Dosarul cu valorile din fabrică lipsește pe acest receptor: după revenire interfața pornește fără setări și fără liste de canale.</p>
  <p class="nota ascuns" id="cuInregistrari">O înregistrare e în curs: se oprește la revenire.</p>
  <label class="bifa" for="inteleg"><input type="checkbox" id="inteleg"> Înțeleg că se pierd toate setările</label>
  <div class="butoane"><button type="button" class="rosu" id="reseteaza" disabled>Revenire la setările din fabrică</button></div>
</section>
<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
<p class="nota">Pentru a face loc pe disc fără să pierzi setările, folosește curățenia discului. Același ecran e pe televizor, în __DRUM_MENIU__.</p>
<div class="butoane"><a class="legatura" href="/curatenie">Curățenia discului</a></div>
</main>
<script>__SCRIPT_COMUN__
var asteapta = false;
function citeste(){
  cerere("/api/resetare-fabrica").then(function(d){
    if(!d.result){ mesaj(d.message, true); return; }
    $("faraImplicite").classList.toggle("ascuns", !!d.implicite);
    $("cuInregistrari").classList.toggle("ascuns", !d.inregistrari);
  }).catch(function(){ if(!asteapta){ nimicNuRaspunde(); } });
}
function asteaptaRevenirea(){
  // interfata iese la 1,5 s dupa raspuns; dupa ce nu mai raspunde si raspunde iar, se deschide pagina de conectare
  asteapta = true;
  var cazut = false, pornit = Date.now();
  function incearca(){
    fetch("/", {cache: "no-store", credentials: "same-origin"}).then(function(){
      if(cazut || Date.now() - pornit > 180000){ location.replace("/"); return; }
      setTimeout(incearca, 3000);
    }).catch(function(){ cazut = true; setTimeout(incearca, 3000); });
  }
  setTimeout(incearca, 4000);
}
$("inteleg").addEventListener("change", function(){ $("reseteaza").disabled = !$("inteleg").checked; });
$("reseteaza").addEventListener("click", function(){
  if(!$("inteleg").checked){ return; }
  var q = new URLSearchParams(); q.set("inteleg", "1");
  cuConfirmare("/api/resetare-fabrica-fa", q, function(d){
    if(d.result && d.reseteaza){ $("reseteaza").disabled = true; $("inteleg").disabled = true; asteaptaRevenirea(); }
  });
});
citeste();
</script>
</body>
</html>
"""


PAGINA_CURATENIE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curățenia discului</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .rand .dreapta{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap;}
  .rand .marime{font-variant-numeric:tabular-nums;}
  .legatura{display:inline-flex;align-items:center;min-height:44px;}
</style>
</head>
<body>
<main>
<h1>Curățenia discului</h1>
<section class="card">
  <h2>Ce se poate goli</h2>
  <p class="mesaj" id="incarcare">Se calculează mărimile...</p>
  <div id="randuri"></div>
  <div class="butoane"><button type="button" id="din_nou">Calculează din nou</button></div>
  <p class="nota">Șterge doar fișiere temporare și pachete descărcate; nu atinge niciodată canale, înregistrări, programări sau setări. Fișierele active (socket-uri, de exemplu dialogul cu modulul CAM) și steagul probei prin stick rămân.</p>
  <div class="butoane"><a class="legatura" href="/resetare-fabrica">Resetarea completă: Revenire la setările din fabrică</a></div>
</section>
<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
<p class="nota">Același ecran e pe televizor, în __DRUM_MENIU__.</p>
</main>
<script>__SCRIPT_COMUN__
var lucreaza = false;
function arata(categorii){
  var r = $("randuri"); r.textContent = "";
  categorii.forEach(function(c){
    var rand = document.createElement("div"); rand.className = "rand";
    var st = document.createElement("div");
    var l = document.createElement("label"); l.textContent = c.eticheta; st.appendChild(l);
    var p = document.createElement("p"); p.className = "nota"; p.textContent = c.exista ? c.cale : c.cale + " (nu există pe acest receptor)"; st.appendChild(p);
    var dr = document.createElement("div"); dr.className = "dreapta";
    var m = document.createElement("span"); m.className = "marime"; m.textContent = c.marime; dr.appendChild(m);
    var b = document.createElement("button"); b.type = "button"; b.className = "rosu"; b.textContent = "Golește";
    b.disabled = !c.exista || lucreaza;
    b.addEventListener("click", function(){ goleste(c.cheie); });
    dr.appendChild(b);
    rand.appendChild(st); rand.appendChild(dr); r.appendChild(rand);
  });
}
function citeste(){
  $("incarcare").classList.remove("ascuns"); $("incarcare").textContent = "Se calculează mărimile...";
  return cerere("/api/curatenie").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi mărimile."; return; }
    $("incarcare").classList.add("ascuns");
    arata(d.categorii || []);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function goleste(cheie){
  var q = new URLSearchParams(); q.set("categorie", cheie);
  cuConfirmare("/api/curatenie-goleste", q, function(d){
    if(d.categorii){ arata(d.categorii); }
  });
}
$("din_nou").addEventListener("click", function(){ mesaj(""); citeste(); });
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
		N_("Revenire la setările din fabrică"),
		N_("Ce se pierde"),
		N_("La revenirea la setările din fabrică se pierd TOATE setările receptorului."),
		N_("Se pierd: listele de canale și favoritele, canalele găsite la scanare, setările antenei și ale "
			"tunerelor (inclusiv datele sateliților), programările înregistrărilor, setările interfeței web "
			"și browserele conectate la ea."),
		N_("Rămân: înregistrările de pe disc sau stick."),
		N_("După revenire interfața pornește din nou singură. Browserul se conectează apoi din nou, cu "
			"codul de pe televizor. Dacă ai schimbat portul interfeței web, ea răspunde din nou pe portul 80."),
		N_("Dosarul cu valorile din fabrică lipsește pe acest receptor: după revenire interfața pornește "
			"fără setări și fără liste de canale."),
		N_("O înregistrare e în curs: se oprește la revenire."),
		N_("Înțeleg că se pierd toate setările"),
		N_("Pentru a face loc pe disc fără să pierzi setările, folosește curățenia discului. Același ecran "
			"e pe televizor, în __DRUM_MENIU__."),
		N_("Curățenia discului"),
		N_("Ce se poate goli"),
		N_("Se calculează mărimile..."),
		N_("Calculează din nou"),
		N_("Șterge doar fișiere temporare și pachete descărcate; nu atinge niciodată canale, înregistrări, "
			"programări sau setări. Fișierele active (socket-uri, de exemplu dialogul cu modulul CAM) și "
			"steagul probei prin stick rămân."),
		N_("Resetarea completă: Revenire la setările din fabrică"),
		N_("Același ecran e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("(nu există pe acest receptor)"),
		N_("Golește"),
		N_("Se calculează mărimile..."),
		N_("Receptorul nu a putut citi mărimile."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
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

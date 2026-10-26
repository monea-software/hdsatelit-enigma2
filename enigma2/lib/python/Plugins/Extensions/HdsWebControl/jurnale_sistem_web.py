# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# jurnale_sistem_web.py: "Jurnalele sistemului" si "Jurnalele de cadere" in interfata web (HdsWebControl).
#
# Orice ecran sau setare de pe receptor are pereche in interfata web.
# Pe televizor:
#   - Meniu > Setari > Sistem & Dispozitive > System Log Viewer (entryID hds_log_manager, Screens/LogManager.py,
#     HdsLogManager): lista jurnalelor din /home/root/logs, Verde/OK deschide unul (cel mult 512 KB de la sfarsit),
#     Galben il sterge dupa o intrebare, Albastru arata "Informatii" (dosarul, cate fisiere, spatiul, cate jurnale de
#     depanare se pastreaza si dupa cate zile se sterg; config.logmanager nu se schimba din niciun ecran);
#   - ... > Crash Log Viewer (entryID hds_crashlog_autosubmit, Screens/HdsCrashlogAutoSubmit.py): jurnalele
#     enigma2_crash_*.log din /home/root/logs, /tmp si dosarele de sub /media, /run/media, /home/root; deschiderea,
#     stergerea dupa o intrebare si, la Albastru, cele doua setari citite de main/bsod.cpp
#     (config.plugins.crashlogautosubmit.sendAnonCrashlog si addNetwork).
# Aici, aceleasi liste, aceeasi citire, aceeasi stergere (cu confirmare in doi pasi) si aceleasi setari. Textul unui
# jurnal se arata fara randurile cu jetonul web, cu parole sau chei (aceeasi regula ca textul brut din /mod-sigur,
# Components/HdsModSigur._faraSecrete): pagina pleaca prin retea. Pagina /mod-sigur (mod_sigur_web.py) arata deja
# opririle interfetei, pe scurt: aici numai o legatura spre ea.
#
# O SINGURA LOGICA: lista, citirea, stergerea, caile si setarile sunt in Components/HdsJurnale.py (folosit si de cele
# doua ecrane). Un fisier se alege numai din lista de acum (numele, respectiv calea din lista), niciodata o cale
# oarecare din cerere; legaturile simbolice nu se deschid si nu se sterg.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/jurnale-sistem                       lista, informatiile si setarile config.logmanager (numai citire)
#   GET  /api/jurnale-sistem-citeste?nume=<fisier>  textul jurnalului (pe un fir)
#   POST /api/jurnale-sistem-sterge?nume=<fisier>&pas=intreaba | &cod=<cod> | &pas=renunta   stergerea, in doi pasi
#   GET  /api/jurnale-cadere                       jurnalele de cadere (pe un fir), dosarele cautate si setarile
#   GET  /api/jurnale-cadere-citeste?cale=<cale>   textul unui jurnal de cadere (pe un fir)
#   POST /api/jurnale-cadere-sterge?cale=<cale>&pas=intreaba | &cod=<cod> | &pas=renunta   stergerea, in doi pasi
#   POST /api/jurnale-cadere-seteaza?anonim=0|1&retea=0|1   setarile citite de bsod.cpp (oricare dintre ele)
#   GET  /jurnale-sistem, /jurnale-cadere          paginile
# Stergerile nu se fac cu ?token= (numai din browserul conectat).
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Lista din /home/root/logs (memoria interna) se citeste pe
# loc; cautarea jurnalelor de cadere (dosarele de sub /media pot fi partajari de retea) si citirea unui jurnal (pana la
# 512 KB) merg pe un fir (meniu_comun_web.peFir), iar raspunsul pleaca dupa (NOT_DONE_YET). Fisierul nu importa nimic
# din enigma2 la incarcare: probele de pe PC dau modulul lor (J), setarile lor si firul lor.

import os

MAX_NUME = 200
MAX_CALE = 400
TIMP_FIR_S = 30


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _c():
	from . import meniu_comun_web
	return meniu_comun_web


def _j(J=None):
	if J is not None:
		return J
	from Components import HdsJurnale
	return HdsJurnale


def _config(J, config=None):
	if config is None:
		J.initConfig()
		J.initConfigCadere()
		from Components.config import config
	return config


def _kb(marime):
	return "%.0f KB" % (marime / 1024.0)


# ------------------------------------------------------------------ jurnalele sistemului

def stareSistem(J=None, config=None):
	"""Pentru GET /api/jurnale-sistem."""
	J = _j(J)
	jurnale = J.listaJurnale()
	dosar, numar, total_mb, pastrate, zile = J.informatii(jurnale, _config(J, config))
	return {
		"result": True,
		"dosar": dosar,
		"jurnale": [{"nume": n, "marime": int(s), "marime_text": _kb(s), "data": J.textData(m)} for m, n, s in jurnale],
		"informatii": {"dosar": dosar, "numar": numar, "total_mb": round(total_mb, 1), "pastrate": pastrate,
			"zile": zile, "randuri": [[a, b] for a, b in _randuriInPlus(J)]},
	}


def _randuriInPlus(J):
	"""jurnalul sistemului si serviciile de sistem (aceleasi randuri ca "Informatii jurnale" pe televizor)"""
	try:
		return J.randuriInformatii()
	except Exception:
		return []


def _text(J, text):
	"""Textul fara secrete si cate randuri s-au scos."""
	curat = J.faraSecrete(text)
	return curat, max(0, text.count("\n") - curat.count("\n"))


def citesteSistem(argumente, J=None):
	"""GET /api/jurnale-sistem-citeste?nume=...: numai un jurnal din lista de acum."""
	J = _j(J)
	nume = argumente.get("nume", "")
	cale = J.caleJurnal(nume)
	if cale is None:
		return {"result": False, "message": _t("Jurnalul nu mai este în listă. Alege din nou.")}
	text, ascunse = _text(J, J.citesteJurnal(cale))
	return {"result": True, "nume": nume, "text": text, "ascunse": ascunse}


def stergeSistem(argumente, J=None, config=None):
	"""POST /api/jurnale-sistem-sterge: pas=intreaba -> intrebarea si codul; cod=... -> stergerea; pas=renunta."""
	J = _j(J)
	C = _c()
	nume = argumente.get("nume", "")
	pas = argumente.get("pas", "")
	if pas == "renunta":
		C.uita("jurnal-sistem", nume)
		return {"result": True, "message": _t("Nu s-a șters nimic.")}
	jurnale = J.listaJurnale()
	cale = J.caleJurnal(nume, jurnale=jurnale)
	if cale is None:
		rez = stareSistem(J, config)
		rez.update({"result": False, "message": _t("Jurnalul nu mai este în listă. Alege din nou.")})
		return rez
	if pas == "intreaba":
		detalii = [x for m, n, s in jurnale if n == nume for x in (_t("Mărimea: %s") % _kb(s),
			_t("Data: %s") % J.textData(m))]
		return C.raspunsIntrebare("jurnal-sistem", nume, _t("Ștergi jurnalul %s?") % nume, _t("Da, șterge"), detalii)
	if not C.verifica("jurnal-sistem", nume, argumente.get("cod", "")):
		rez = stareSistem(J, config)
		rez.update(C.codGresit())
		return rez
	sters = J.stergeFisier(cale)
	rez = stareSistem(J, config)
	rez.update({"result": bool(sters), "message": _t("Jurnalul a fost șters.") if sters else
		_t("Jurnalul nu s-a putut șterge.")})
	return rez


# ------------------------------------------------------------------ jurnalele de cadere

def _alegeriDaNu(element):
	d = getattr(element, "descriptions", None) or {False: "no", True: "yes"}
	return [["1", _t(d[True]) if d[True] else "1"], ["0", _t(d[False]) if d[False] else "0"]]


def setariCadere(J=None, config=None):
	J = _j(J)
	c = _config(J, config).plugins.crashlogautosubmit
	return {
		"anonim": bool(c.sendAnonCrashlog.value),
		"retea": bool(c.addNetwork.value),
		"alegeri_anonim": _alegeriDaNu(c.sendAnonCrashlog),
		"alegeri_retea": _alegeriDaNu(c.addNetwork),
	}


def stareCadere(J=None, config=None):
	"""Pentru GET /api/jurnale-cadere (pe un fir: dosarele de sub /media pot fi partajari de retea). Face dosarul
	principal daca lipseste, ca ecranul la deschidere."""
	J = _j(J)
	J.asiguraDirectorPrincipal()
	gasite = J.cautaJurnaleCadere()
	rez = {
		"result": True,
		"principal": J.CALE_PRINCIPALA,
		"jurnale": [{"cale": c, "nume": n, "dosar": os.path.dirname(c), "marime": int(s),
			"marime_text": _kb(s), "data": J.textData(m)} for c, n, s, m in gasite],
	}
	rez.update(setariCadere(J, config))
	return rez


def citesteCadere(argumente, J=None):
	"""GET /api/jurnale-cadere-citeste?cale=...: numai un jurnal din lista de acum."""
	J = _j(J)
	cale = J.caleCadere(argumente.get("cale", ""))
	if cale is None:
		return {"result": False, "message": _t("Jurnalul nu mai este în listă. Alege din nou.")}
	text, ascunse = _text(J, J.citesteJurnal(cale))
	return {"result": True, "cale": cale, "text": text, "ascunse": ascunse}


def stergeCadere(argumente, J=None, config=None):
	"""POST /api/jurnale-cadere-sterge: in doi pasi, ca stergeSistem."""
	J = _j(J)
	C = _c()
	cale_ceruta = argumente.get("cale", "")
	pas = argumente.get("pas", "")
	if pas == "renunta":
		C.uita("jurnal-cadere", cale_ceruta)
		return {"result": True, "message": _t("Nu s-a șters nimic.")}
	gasite = J.cautaJurnaleCadere()
	cale = J.caleCadere(cale_ceruta, gasite)
	if cale is None:
		rez = stareCadere(J, config)
		rez.update({"result": False, "message": _t("Jurnalul nu mai este în listă. Alege din nou.")})
		return rez
	if pas == "intreaba":
		detalii = [x for c, n, s, m in gasite if c == cale for x in (_t("Dosarul: %s") % os.path.dirname(c),
			_t("Mărimea: %s") % _kb(s), _t("Data: %s") % J.textData(m))]
		nume = os.path.basename(cale)
		return C.raspunsIntrebare("jurnal-cadere", cale, _t("Ștergi jurnalul %s?") % nume, _t("Da, șterge"), detalii)
	if not C.verifica("jurnal-cadere", cale, argumente.get("cod", "")):
		rez = stareCadere(J, config)
		rez.update(C.codGresit())
		return rez
	sters = J.stergeFisier(cale)
	rez = stareCadere(J, config)
	rez.update({"result": bool(sters), "message": _t("Jurnalul a fost șters.") if sters else
		_t("Jurnalul nu s-a putut șterge.")})
	return rez


def seteazaCadere(argumente, J=None, config=None, configfile=None):
	"""POST /api/jurnale-cadere-seteaza: anonim=0|1, retea=0|1. O valoare straina nu schimba nimic. Ca la Verde pe
	televizor (save()), apoi configfile.save(): bsod.cpp citeste direct /etc/enigma2/settings."""
	J = _j(J)
	config = _config(J, config)
	c = config.plugins.crashlogautosubmit
	noi = []
	for cheie, element in (("anonim", c.sendAnonCrashlog), ("retea", c.addNetwork)):
		if cheie not in argumente:
			continue
		if argumente[cheie] not in ("0", "1"):
			rez = setariCadere(J, config)
			rez.update({"result": False, "message": _t("Valoarea trimisă nu e bună. Se alege Da sau Nu.")})
			return rez
		noi.append((element, argumente[cheie] == "1"))
	if not noi:
		rez = setariCadere(J, config)
		rez.update({"result": False, "message": _t("Nu s-a trimis nicio setare.")})
		return rez
	for element, valoare in noi:
		if element.value != valoare:
			element.value = valoare
		element.save()
	if configfile is not None:
		configfile.save()
	else:
		_c().salveazaSetari()
	rez = setariCadere(J, config)
	rez.update({"result": True, "message": _t("Salvat.")})
	return rez


# ------------------------------------------------------------------ cererile

def argumente(request):
	"""Argumentele cererii ca text scurt, numai cheile stiute, fara token."""
	rez = _c().argumente(request, ("nume", "pas", "cod"), MAX_NUME)
	rez.update(_c().argumente(request, ("cale",), MAX_CALE))
	rez.update(_c().argumente(request, ("anonim", "retea"), 4))
	return rez


class _Steaguri(object):
	cadere = [False]
	citire = [False]


def _peFirImplicit(request, lucru, steag):
	return _c().peFir(request, lucru, steag, TIMP_FIR_S)


def rute(baza, resource, J=None, config=None, configfile=None, fir=None):
	"""({nume: resursa de sub /api}, {nume: resursa pagina}). `baza` e HdsJsonResource din plugin.py; `fir(request,
	lucru, steag)` porneste lucru() pe un fir si intoarce NOT_DONE_YET (probele dau unul care raspunde pe loc)."""
	pe_fir = fir or _peFirImplicit

	def _ocupat(obiect, request):
		return obiect._eroare(request, _t("Receptorul citește deja jurnalele. Încearcă din nou peste câteva secunde."),
			503)

	class StareSistem(baza):
		"""GET /api/jurnale-sistem: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stareSistem(J, config))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CitesteSistem(baza):
		"""GET /api/jurnale-sistem-citeste: numai citire, pe un fir."""

		def render_GET(self, request):
			if _Steaguri.citire[0]:
				return _ocupat(self, request)
			arg = argumente(request)
			return pe_fir(request, lambda: citesteSistem(arg, J), _Steaguri.citire)

	class StergeSistem(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = _c().numaiBrowser(request)
			if refuz:
				return self._eroare(request, refuz, 403)
			try:
				return self._raspunde(request, stergeSistem(argumente(request), J, config))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token=, deci refuzat

	class StareCadere(baza):
		"""GET /api/jurnale-cadere: numai citire, pe un fir."""

		def render_GET(self, request):
			if _Steaguri.cadere[0]:
				return _ocupat(self, request)
			return pe_fir(request, lambda: stareCadere(J, config), _Steaguri.cadere)

	class CitesteCadere(baza):
		"""GET /api/jurnale-cadere-citeste: numai citire, pe un fir."""

		def render_GET(self, request):
			if _Steaguri.citire[0]:
				return _ocupat(self, request)
			arg = argumente(request)
			return pe_fir(request, lambda: citesteCadere(arg, J), _Steaguri.citire)

	class StergeCadere(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = _c().numaiBrowser(request)
			if refuz:
				return self._eroare(request, refuz, 403)
			if _Steaguri.cadere[0]:
				return _ocupat(self, request)
			arg = argumente(request)
			return pe_fir(request, lambda: stergeCadere(arg, J, config), _Steaguri.cadere)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token=, deci refuzat

	class SeteazaCadere(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteazaCadere(argumente(request), J, config, configfile))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaSistem(resource.Resource):
		"""GET /jurnale-sistem."""
		isLeaf = True

		def render_GET(self, request):
			return _c().pagina(request, pagina_sistem)

	class PaginaCadere(resource.Resource):
		"""GET /jurnale-cadere."""
		isLeaf = True

		def render_GET(self, request):
			return _c().pagina(request, pagina_cadere)

	api = {
		b"jurnale-sistem": StareSistem(),
		b"jurnale-sistem-citeste": CitesteSistem(),
		b"jurnale-sistem-sterge": StergeSistem(),
		b"jurnale-cadere": StareCadere(),
		b"jurnale-cadere-citeste": CitesteCadere(),
		b"jurnale-cadere-sterge": StergeCadere(),
		b"jurnale-cadere-seteaza": SeteazaCadere(),
	}
	pagini = {
		b"jurnale-sistem": PaginaSistem(),
		b"jurnale-cadere": PaginaCadere(),
	}
	return api, pagini


# ------------------------------------------------------------------ paginile

def pagina_sistem(stil, config_pagina):
	C = _c()
	return C.sablon(_traducePagina(PAGINA_SISTEM), stil, config_pagina,
		{"__DRUM_MENIU__": C.drumHtml("hds_log_manager"),
		"__SCRIPT_VIZUALIZARE__": _traducePagina(SCRIPT_VIZUALIZARE, "js")})


def pagina_cadere(stil, config_pagina):
	C = _c()
	return C.sablon(_traducePagina(PAGINA_CADERE), stil, config_pagina,
		{"__DRUM_MENIU__": C.drumHtml("hds_crashlog_autosubmit"),
		"__SCRIPT_VIZUALIZARE__": _traducePagina(SCRIPT_VIZUALIZARE, "js")})


# stilul propriu al celor doua pagini: tabelul jurnalelor se asaza pe randuri pe telefon
STIL_JURNALE = """
  .tabel th{overflow-wrap:normal;word-break:normal;white-space:nowrap;}
  .tabel td.actiuni{white-space:nowrap;text-align:right;}
  .tabel td.actiuni button{margin:2px 0 2px 6px;}
  .tabel .mic{color:var(--text-slab);font-size:.8rem;overflow-wrap:anywhere;}
  .legaturi a{color:inherit;}
  @media (max-width:560px){
    .tabel thead{display:none;}
    .tabel, .tabel tbody, .tabel tr, .tabel td{display:block;width:auto;}
    .tabel tr{padding:8px 0;border-bottom:1px solid var(--bordura);}
    .tabel td{border:0;padding:2px 0;}
    .tabel td.actiuni{text-align:left;white-space:normal;padding-top:6px;}
    .tabel td.actiuni button{margin:4px 8px 0 0;}
  }
"""

# scriptul comun al celor doua pagini: deschiderea unui jurnal in cartea "Jurnalul deschis", legaturile cu ?token=
SCRIPT_VIZUALIZARE = r"""
function legaturi(){
  Array.prototype.forEach.call(document.querySelectorAll("a[data-cale]"), function(a){ a.href = adresa(a.getAttribute("data-cale")); });
}
function arataJurnal(titlu, d){
  var c = $("cardText");
  $("titluText").textContent = titlu;
  $("text").textContent = d.result ? d.text : (d.message || "");
  $("notaText").textContent = d.result && d.ascunse ? ("Rânduri ascunse aici (cu parole, coduri sau chei): " + d.ascunse + ".") : "";
  c.classList.remove("ascuns");
  c.scrollIntoView({block: "start"});
}
function inchideJurnal(){ $("cardText").classList.add("ascuns"); }
function buton(text, clasa, apasat){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  if(clasa){ b.className = clasa; }
  b.addEventListener("click", apasat);
  return b;
}
function celula(tr, text, clasa){
  var td = document.createElement("td"); td.textContent = text || ""; if(clasa){ td.className = clasa; }
  tr.appendChild(td); return td;
}
"""

PAGINA_SISTEM = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jurnalele sistemului</title>
<style>__STIL_COMUN__ __STIL_PAGINI__""" + STIL_JURNALE + """</style>
</head>
<body>
<main>
<h1>Jurnalele sistemului</h1>
<p class="mesaj" id="incarcare">Se citesc jurnalele...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Jurnalele</h2>
    <p class="nota" id="gol">Niciun fișier de jurnal găsit.</p>
    <table class="tabel" id="tabel"><thead><tr><th>Fișierul</th><th>Mărimea</th><th>Data</th><th></th></tr></thead><tbody id="jurnale"></tbody></table>
    <p class="nota">Deschide arată cel mult ultimii 512 KB din jurnal, ca pe televizor.</p>
  </section>
  <section class="card ascuns" id="cardText">
    <h2 id="titluText"></h2>
    <p class="nota" id="notaText"></p>
    <pre class="text" id="text"></pre>
    <div class="butoane"><button type="button" id="inchide">Închide</button></div>
  </section>
  <section class="card">
    <h2>Informații</h2>
    <div class="status-linie"><span>Dosarul jurnalelor</span><span id="infoDosar"></span></div>
    <div class="status-linie"><span>Număr de fișiere</span><span id="infoNumar"></span></div>
    <div class="status-linie"><span>Spațiu ocupat</span><span id="infoSpatiu"></span></div>
    <div class="status-linie"><span>Jurnale de depanare păstrate</span><span id="infoPastrate"></span></div>
    <div class="status-linie"><span>Se șterg jurnalele mai vechi de</span><span id="infoZile"></span></div>
    <div id="infoInPlus"></div>
    <p class="nota">Curățarea automată rulează numai dacă AutoLogManager e pornit din codul principal. Aceste două valori nu se schimbă din meniu, nici pe televizor, nici aici.</p>
  </section>
  <p class="nota legaturi">Opririle neașteptate ale interfeței, pe scurt, sunt în <a data-cale="/mod-sigur" href="/mod-sigur">Mod sigur</a>; jurnalele scrise la o cădere sunt în <a data-cale="/jurnale-cadere" href="/jurnale-cadere">Jurnalele de cădere</a>.</p>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
__SCRIPT_VIZUALIZARE__
function arata(d){
  if(!d.jurnale){ return; }
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var corp = $("jurnale"); corp.textContent = "";
  d.jurnale.forEach(function(j){
    var tr = document.createElement("tr");
    celula(tr, j.nume); celula(tr, j.marime_text); celula(tr, j.data);
    var a = celula(tr, "", "actiuni");
    a.appendChild(buton("Deschide", "principal", function(){ deschide(j.nume); }));
    a.appendChild(buton("Șterge", "rosu", function(){ sterge(j.nume); }));
    corp.appendChild(tr);
  });
  var are = d.jurnale.length > 0;
  $("tabel").classList.toggle("ascuns", !are); $("gol").classList.toggle("ascuns", are);
  var i = d.informatii || {};
  $("infoDosar").textContent = i.dosar || "";
  $("infoNumar").textContent = String(i.numar || 0);
  $("infoSpatiu").textContent = (i.total_mb || 0).toFixed(1) + " MB";
  $("infoPastrate").textContent = "cel mult " + i.pastrate;
  $("infoZile").textContent = i.zile + " zile";
  var p = $("infoInPlus"); p.textContent = "";
  (i.randuri || []).forEach(function(r){ var l = document.createElement("div"); l.className = "status-linie";
    var a = document.createElement("span"); a.textContent = r[0]; var b = document.createElement("span"); b.textContent = r[1];
    l.appendChild(a); l.appendChild(b); p.appendChild(l); });
}
function citeste(){
  return cerere("/api/jurnale-sistem").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi jurnalele."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function deschide(nume){
  mesaj("Se citește jurnalul...");
  cerere("/api/jurnale-sistem-citeste?nume=" + encodeURIComponent(nume)).then(function(d){
    mesaj(d.result ? "" : d.message, !d.result);
    if(d.result){ arataJurnal("Jurnal: " + nume, d); } else { citeste(); }
  }).catch(nimicNuRaspunde);
}
function sterge(nume){
  var q = new URLSearchParams(); q.set("nume", nume);
  cuConfirmare("/api/jurnale-sistem-sterge", q, function(d){ if(d.jurnale){ arata(d); inchideJurnal(); } else { citeste(); } });
}
$("inchide").addEventListener("click", inchideJurnal);
legaturi();
citeste();
setInterval(function(){ if(document.visibilityState === "visible"){ citeste(); } }, 30000);
</script>
</body>
</html>
"""

PAGINA_CADERE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jurnalele de cădere</title>
<style>__STIL_COMUN__ __STIL_PAGINI__""" + STIL_JURNALE + """</style>
</head>
<body>
<main>
<h1>Jurnalele de cădere</h1>
<p class="mesaj" id="incarcare">Se caută jurnalele...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Jurnalele găsite</h2>
    <p class="nota" id="numar"></p>
    <p class="nota" id="gol">Niciun jurnal de cădere găsit.</p>
    <table class="tabel" id="tabel"><thead><tr><th>Fișierul</th><th>Mărimea</th><th>Data</th><th></th></tr></thead><tbody id="jurnale"></tbody></table>
    <p class="nota">Trimiterea rămâne manuală: un jurnal găsit aici se poate trimite prin formularul de contact de pe hdsatelit.com; nu există încă o trimitere automată prin rețea. Se caută în <span id="principal"></span>, în /tmp și în orice alt dosar montat sub /media, /run/media, /home/root.</p>
  </section>
  <section class="card ascuns" id="cardText">
    <h2 id="titluText"></h2>
    <p class="nota" id="notaText"></p>
    <pre class="text" id="text"></pre>
    <div class="butoane"><button type="button" id="inchide">Închide</button></div>
  </section>
  <section class="card">
    <h2>Setări</h2>
    <div class="rand">
      <label for="anonim">Păstrează jurnalul anonim (fără cartelă CA, fără setările contului)</label>
      <select id="anonim"></select>
    </div>
    <div class="rand">
      <label for="retea">Include informații de rețea în jurnal (interfețe, DNS, ruta implicită)</label>
      <select id="retea"></select>
    </div>
    <p class="nota">Aceste două opțiuni sunt citite direct de codul care scrie jurnalul de cădere (bsod.cpp), chiar și la o prăbușire completă. Parola Wi-Fi nu intră niciodată în jurnal, oricare ar fi setările.</p>
    <p class="nota">Anonim, Da (din fabrică): jurnalul nu identifică receptorul sau contul. Anonim, Nu: jurnalul are și cartela CA și setările (fără parole); alege asta numai dacă trimiți jurnalul cuiva care chiar are nevoie de acele detalii.</p>
    <p class="nota">Informații de rețea, Nu (din fabrică): jurnalul nu are nimic despre rețea. Da: jurnalul are interfețele, DNS și ruta implicită (util la probleme de rețea, dar arată adrese interne).</p>
  </section>
  <p class="nota legaturi">Opririle neașteptate ale interfeței, pe scurt, cu ultima eroare, sunt în <a data-cale="/mod-sigur" href="/mod-sigur">Mod sigur</a>; celelalte jurnale ale receptorului sunt în <a data-cale="/jurnale-sistem" href="/jurnale-sistem">Jurnalele sistemului</a>.</p>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
__SCRIPT_VIZUALIZARE__
function alegeri(sel, lista, valoare){
  if(document.activeElement === sel){ return; }
  sel.textContent = "";
  (lista || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
  sel.value = valoare ? "1" : "0";
}
function arataSetari(d){
  if(d.alegeri_anonim){ alegeri($("anonim"), d.alegeri_anonim, d.anonim); }
  if(d.alegeri_retea){ alegeri($("retea"), d.alegeri_retea, d.retea); }
}
function arata(d){
  arataSetari(d);
  if(!d.jurnale){ return; }
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  $("principal").textContent = d.principal || "";
  $("numar").textContent = "Găsite: " + d.jurnale.length + ".";
  var corp = $("jurnale"); corp.textContent = "";
  d.jurnale.forEach(function(j){
    var tr = document.createElement("tr");
    var n = celula(tr, j.nume);
    var mic = document.createElement("div"); mic.className = "mic"; mic.textContent = j.dosar; n.appendChild(mic);
    celula(tr, j.marime_text); celula(tr, j.data);
    var a = celula(tr, "", "actiuni");
    a.appendChild(buton("Deschide", "principal", function(){ deschide(j); }));
    a.appendChild(buton("Șterge", "rosu", function(){ sterge(j.cale); }));
    corp.appendChild(tr);
  });
  var are = d.jurnale.length > 0;
  $("tabel").classList.toggle("ascuns", !are); $("gol").classList.toggle("ascuns", are);
}
function citeste(){
  return cerere("/api/jurnale-cadere").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut căuta jurnalele."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function deschide(j){
  mesaj("Se citește jurnalul...");
  cerere("/api/jurnale-cadere-citeste?cale=" + encodeURIComponent(j.cale)).then(function(d){
    mesaj(d.result ? "" : d.message, !d.result);
    if(d.result){ arataJurnal("Jurnal: " + j.nume, d); } else { citeste(); }
  }).catch(nimicNuRaspunde);
}
function sterge(cale){
  var q = new URLSearchParams(); q.set("cale", cale);
  cuConfirmare("/api/jurnale-cadere-sterge", q, function(d){ if(d.jurnale){ arata(d); inchideJurnal(); } else { citeste(); } });
}
function seteaza(cheie, valoare){
  var q = new URLSearchParams(); q.set(cheie, valoare);
  mesaj("Se salvează...");
  cerere("/api/jurnale-cadere-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); arataSetari(d); }).catch(nimicNuRaspunde);
}
$("anonim").addEventListener("change", function(){ seteaza("anonim", $("anonim").value); });
$("retea").addEventListener("change", function(){ seteaza("retea", $("retea").value); });
$("inchide").addEventListener("click", inchideJurnal);
legaturi();
citeste();
setInterval(function(){ if(document.visibilityState === "visible"){ citeste(); } }, 30000);
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
		N_("Jurnalele sistemului"),
		N_("Se citesc jurnalele..."),
		N_("Jurnalele"),
		N_("Niciun fișier de jurnal găsit."),
		N_("Fișierul"),
		N_("Mărimea"),
		N_("Data"),
		N_("Deschide arată cel mult ultimii 512 KB din jurnal, ca pe televizor."),
		N_("Închide"),
		N_("Informații"),
		N_("Dosarul jurnalelor"),
		N_("Număr de fișiere"),
		N_("Spațiu ocupat"),
		N_("Jurnale de depanare păstrate"),
		N_("Se șterg jurnalele mai vechi de"),
		N_("Curățarea automată rulează numai dacă AutoLogManager e pornit din codul principal. Aceste două "
			"valori nu se schimbă din meniu, nici pe televizor, nici aici."),
		N_("Opririle neașteptate ale interfeței, pe scurt, sunt în <a data-cale=\"/mod-sigur\" "
			"href=\"/mod-sigur\">Mod sigur</a>; jurnalele scrise la o cădere sunt în <a "
			"data-cale=\"/jurnale-cadere\" href=\"/jurnale-cadere\">Jurnalele de cădere</a>."),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("Jurnalele de cădere"),
		N_("Se caută jurnalele..."),
		N_("Jurnalele găsite"),
		N_("Niciun jurnal de cădere găsit."),
		N_("Trimiterea rămâne manuală: un jurnal găsit aici se poate trimite prin formularul de contact de "
			"pe hdsatelit.com; nu există încă o trimitere automată prin rețea. Se caută în <span "
			"id=\"principal\"></span>, în /tmp și în orice alt dosar montat sub /media, /run/media, /home/root."),
		N_("Setări"),
		N_("Păstrează jurnalul anonim (fără cartelă CA, fără setările contului)"),
		N_("Include informații de rețea în jurnal (interfețe, DNS, ruta implicită)"),
		N_("Aceste două opțiuni sunt citite direct de codul care scrie jurnalul de cădere (bsod.cpp), chiar "
			"și la o prăbușire completă. Parola Wi-Fi nu intră niciodată în jurnal, oricare ar fi setările."),
		N_("Anonim, Da (din fabrică): jurnalul nu identifică receptorul sau contul. Anonim, Nu: jurnalul "
			"are și cartela CA și setările (fără parole); alege asta numai dacă trimiți jurnalul cuiva care "
			"chiar are nevoie de acele detalii."),
		N_("Informații de rețea, Nu (din fabrică): jurnalul nu are nimic despre rețea. Da: jurnalul are "
			"interfețele, DNS și ruta implicită (util la probleme de rețea, dar arată adrese interne)."),
		N_("Opririle neașteptate ale interfeței, pe scurt, cu ultima eroare, sunt în <a "
			"data-cale=\"/mod-sigur\" href=\"/mod-sigur\">Mod sigur</a>; celelalte jurnale ale receptorului sunt "
			"în <a data-cale=\"/jurnale-sistem\" href=\"/jurnale-sistem\">Jurnalele sistemului</a>."),
	),
	"js": (
		N_("Rânduri ascunse aici (cu parole, coduri sau chei):"),
		N_("Deschide"),
		N_("Șterge"),
		N_("cel mult"),
		N_("Receptorul nu a putut citi jurnalele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se citește jurnalul..."),
		N_("Jurnal:"),
		N_("Găsite:"),
		N_("Receptorul nu a putut căuta jurnalele."),
		N_("Se salvează..."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ceas_web.py: „Data și ora” in interfata web (HdsWebControl).
#
# Orice setare de pe receptor are pereche in interfata web.
# Pe televizor: Setari > Sistem si dispozitive > Data si ora (Screens/Time.py): fusul orar, sursa orei (Internet,
# apoi transponder / numai Internet / numai transponder), serverul NTP, „Sincronizeaza acum” si starea. Aici: aceleasi
# setari, aceeasi stare si acelasi buton, din aceeasi logica (Components/HdsCeas.py).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/ceas                                    ora receptorului, setarile cu alegerile lor si starea
#   POST /api/ceas-seteaza?sursa=..&server=..&fus=..  schimba si salveaza (oricare dintre ele)
#   POST /api/ceas-sincronizeaza                      o sincronizare prin Internet acum
#   GET  /ceas                                        pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte (NTP porneste un proces separat si
# nu se asteapta dupa el). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (C).

import time

def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _c(C=None):
	if C is not None:
		return C
	from Components import HdsCeas
	return HdsCeas


def stare(C=None, acum=None):
	"""Pentru GET /api/ceas."""
	C = _c(C)
	acum = time.time() if acum is None else acum
	s = C.stare()
	return {
		"result": True,
		"ora": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(acum)),
		"ora_utc": int(acum),
		"fus": C.fusCurent(),
		"fusuri": C.fusuri(),
		"sursa": s["mod"],
		"surse": [[m, C.textMod(m)] for m in C.MODURI],
		"server": s["server"],
		"servere": [[v, t] for (v, t) in C.SERVERE],
		"in_curs": s["in_curs"],
		"confirmata": s["confirmata"],
		# starea orei, ca pe ecranul „Data si ora” (provizorie, salvata, sigura si de unde)
		"stare_ceas": s.get("stare_ceas", ""),
		"sigura": s.get("confirmata"),
		"transponder_pornit": s["transponder_pornit"],
		"sursa_text": s["sursa_text"],
		"ultima_text": s["ultima_text"],
		"ultima": s["ultima"],
	}


def seteaza(argumente, C=None):
	"""POST /api/ceas-seteaza: o valoare straina nu schimba nimic (nici celelalte trimise odata cu ea)."""
	C = _c(C)
	sursa = argumente.get("sursa")
	server = argumente.get("server")
	fus = argumente.get("fus")
	if sursa is None and server is None and fus is None:
		rez = stare(C)
		rez.update({"result": False, "message": _t("Nu s-a trimis nimic de schimbat (sursa, server sau fus).")})
		return rez
	reusit, mesaj = C.seteaza(mod=sursa, server=server, fus=fus)
	rez = stare(C)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def sincronizeaza(C=None):
	"""POST /api/ceas-sincronizeaza."""
	C = _c(C)
	pornit, mesaj = C.sincronizeazaAcum()
	rez = stare(C)
	rez.update({"result": bool(pornit), "message": mesaj})
	return rez


def argumente(request):
	"""Argumentele cererii ca text: {cheie: text}, fara token. Fusul orar are nume lungi, deci pana la 120 de caractere."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:120].strip()
	return rez


def rute(baza, resource, C=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/ceas: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(C))
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

	class SeteazaResource(_Schimba):
		def fa(self, a):
			return seteaza(a, C)

	class SincronizeazaResource(_Schimba):
		def fa(self, a):
			return sincronizeaza(C)

	class PaginaResource(resource.Resource):
		"""GET /ceas: pagina „Data și ora”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"ceas": StareResource(),
		b"ceas-seteaza": SeteazaResource(),
		b"ceas-sincronizeaza": SincronizeazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /accel: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser neconectat
	primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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
		_drumMeniu("time_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data și ora</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .ora{font-size:1.6rem;font-variant-numeric:tabular-nums;margin:0 0 6px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,300px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;max-width:100%;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0;}
  .butoane button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .acum{font-size:1rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .nesigura{color:#ffd28a;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Data și ora</h1>
<p class="mesaj" id="incarcare">Se citește ora receptorului...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="ora" id="ora"></p>
    <p class="acum" id="sursaText"></p>
    <p class="nota" id="ultimaText"></p>
  </section>
  <section class="card">
    <div class="rand">
      <label for="fus">Fus orar</label>
      <select id="fus"></select>
    </div>
    <div class="rand">
      <label for="sursa">Sursa orei</label>
      <select id="sursa"></select>
    </div>
    <div class="rand" id="randServer">
      <label for="server">Server NTP</label>
      <select id="server"></select>
    </div>
  </section>
  <div class="butoane"><button type="button" id="sincronizeaza">Sincronizează acum</button></div>
  <p class="nota">Receptorul nu are ceas propriu cu baterie: la pornire ora vine din ultima oră salvată, apoi se ia din Internet (NTP) și, până reușește, din transponderul canalului. Ora de la un singur transponder rămâne provizorie până o confirmă Internetul sau un al doilea transponder; numai ora sigură se salvează. Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
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
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function umple(sel, alegeri, ales){
  sel.textContent = "";
  alegeri.forEach(function(a){
    var o = document.createElement("option");
    o.value = Array.isArray(a) ? a[0] : a;
    o.textContent = Array.isArray(a) ? a[1] : a;
    sel.appendChild(o);
  });
  sel.value = ales;
}
function arata(d){
  if(document.activeElement !== $("fus")){ umple($("fus"), d.fusuri || [], d.fus); }
  if(document.activeElement !== $("sursa")){ umple($("sursa"), d.surse || [], d.sursa); }
  if(document.activeElement !== $("server")){ umple($("server"), d.servere || [], d.server); }
  $("randServer").classList.toggle("ascuns", d.sursa === "dvb");
  $("sincronizeaza").disabled = d.sursa === "dvb" || d.in_curs;
  $("sursaText").textContent = d.sursa_text || "";
  $("sursaText").classList.toggle("nesigura", d.sigura === false);
  $("ultimaText").textContent = (d.ultima_text || "") + (d.in_curs ? " Se sincronizează acum." : "");
  $("ora").textContent = d.ora;
}
function citeste(){
  return cerere("/api/ceas").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi ora."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cheie, valoare){
  var q = new URLSearchParams(); q.set(cheie, valoare);
  mesaj("Se salvează...");
  cerere("/api/ceas-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.fusuri){ arata(d); } })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("fus").addEventListener("change", function(){ trimite("fus", $("fus").value); });
$("sursa").addEventListener("change", function(){ trimite("sursa", $("sursa").value); });
$("server").addEventListener("change", function(){ trimite("server", $("server").value); });
$("sincronizeaza").addEventListener("click", function(){
  mesaj("Se sincronizează...");
  cerere("/api/ceas-sincronizeaza", "POST", new URLSearchParams()).then(function(d){
    mesaj(d.message, !d.result); if(d.fusuri){ arata(d); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
citeste();
setInterval(citeste, 5000);
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
		N_("Data și ora"),
		N_("Se citește ora receptorului..."),
		N_("Fus orar"),
		N_("Sursa orei"),
		N_("Server NTP"),
		N_("Sincronizează acum"),
		N_("Receptorul nu are ceas propriu cu baterie: la pornire ora vine din ultima oră salvată, apoi se "
			"ia din Internet (NTP) și, până reușește, din transponderul canalului. Ora de la un singur "
			"transponder rămâne provizorie până o confirmă Internetul sau un al doilea transponder; numai "
			"ora sigură se salvează. Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se sincronizează acum."),
		N_("Receptorul nu a putut citi ora."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează..."),
		N_("Receptorul nu răspunde."),
		N_("Se sincronizează..."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# paznic_web.py: „Paznicul receptorului” in interfata web (HdsWebControl).
#
# Orice setare de pe receptor are pereche in interfata web.
# Pe televizor: Meniu > Sistem & Dispozitive > Paznicul receptorului (Screens/HdsPaznic.py). Aici: aceleasi doua
# setari (repornirea interfetei cand nu mai raspunde, asteptarea), aceeasi stare si ultimele randuri din jurnalul
# paznicului, din aceeasi logica (Components/HdsPaznic.py). Deasupra starii, cat paznicul o spune, informatia despre
# memoria pozelor si a filmelor (stare.avertisment, cand lipseste); sub stare, memoria decodorului masurata
# (stare.memorie_driver, Components/HdsMemorieDriver.py). Numai informatie, fara alarma. Perechea setarii
# "Elibereaza memoria decodorului in standby" (config.hds_paznic.repornire_noapte).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/paznic                                      setarile, alegerile, starea si jurnalul
#   POST /api/paznic-seteaza?interfata=0|1&asteptare=60|120|300&noapte=0|1   schimba si salveaza (oricare dintre ele)
#   GET  /paznic                                          pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte (citesc doua fisiere mici). Fisierul
# nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (P) si setarile lor (config).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _p(P=None):
	if P is not None:
		return P
	from Components import HdsPaznic
	return HdsPaznic


def _setari(P, config=None):
	if config is None:
		P.initConfig()
		from Components.config import config
	return bool(config.hds_paznic.interfata.value), int(config.hds_paznic.asteptare.value)


def _noapte(config=None):
	"""config.hds_paznic.repornire_noapte (Components/HdsMemorieDriver.py); lipsa sau necitita = Da, ca din fabrica."""
	try:
		if config is None:
			from Components import HdsMemorieDriver
			HdsMemorieDriver.initConfig()
			from Components.config import config
		v = getattr(config.hds_paznic, "repornire_noapte", None)
		return True if v is None else bool(v.value)
	except Exception:
		return True


def stare(P=None, config=None):
	"""Pentru GET /api/paznic."""
	P = _p(P)
	interfata, asteptare = _setari(P, config)
	return {
		"result": True,
		"interfata": interfata,
		"asteptare": asteptare,
		"noapte": _noapte(config),
		"asteptari": [[s, P.textDurata(s)] for s in P.ASTEPTARI_PERMISE_S],
		"stare": P.stare(),
		"jurnal": P.ultimeleRanduriJurnal(randuri=8),
	}


def seteaza(argumente, P=None, config=None):
	"""POST /api/paznic-seteaza: o valoare straina nu schimba nimic."""
	P = _p(P)
	interfata = argumente.get("interfata")
	asteptare = argumente.get("asteptare")
	noapte = argumente.get("noapte")
	if noapte is not None and noapte not in ("0", "1"):
		rez = stare(P, config)
		rez.update({"result": False, "message": _t("Se alege cu noapte=1 sau noapte=0.")})
		return rez
	if interfata is None and asteptare is None and noapte is None:
		rez = stare(P, config)
		rez.update({"result": False, "message": _t("Se alege cu interfata=0|1 sau asteptare=60|120|300.")})
		return rez
	if interfata is not None and interfata not in ("0", "1"):
		rez = stare(P, config)
		rez.update({"result": False, "message": _t("Se alege cu interfata=1 sau interfata=0.")})
		return rez
	schimbari = {"interfata": None if interfata is None else interfata == "1", "asteptare": asteptare}
	if noapte is not None:
		schimbari["noapte"] = noapte == "1"
	reusit, mesaj = P.seteaza(**schimbari)
	rez = stare(P, config)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:6]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:8].strip()
	return rez


def rute(baza, resource, P=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/paznic: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(P))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), P))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /paznic: pagina „Paznicul receptorului”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"paznic": StareResource(),
		b"paznic-seteaza": SeteazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /accel si /ceas."""
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
		_drumMeniu("hds_paznic"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paznicul receptorului</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,220px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .acum{font-size:1rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .jurnal{font-family:monospace;font-size:.78rem;line-height:1.4;white-space:pre-wrap;word-break:break-word;color:var(--text-slab);margin:0;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .info{margin:0 0 10px;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Paznicul receptorului</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="acum info ascuns" id="avertisment"></p>
    <p class="acum" id="stare"></p>
    <p class="nota" id="memorie"></p>
    <p class="nota" id="reporniri"></p>
  </section>
  <section class="card">
    <div class="rand">
      <label for="interfata">Repornește interfața când nu mai răspunde</label>
      <select id="interfata"><option value="1">Da</option><option value="0">Nu</option></select>
    </div>
    <div class="rand" id="randAsteptare">
      <label for="asteptare">Așteaptă înainte de repornire</label>
      <select id="asteptare"></select>
    </div>
    <div class="rand">
      <label for="noapte">Eliberează memoria decodorului în standby</label>
      <select id="noapte"><option value="1">Da</option><option value="0">Nu</option></select>
    </div>
  </section>
  <p class="nota">Paznicul repornește interfața numai când nu mai dă semn de viață și nici interfața web nu răspunde. În timpul unei scanări, al citirii pistelor sau al unei rotiri de antenă așteaptă. Paznicul plăcii rămâne mereu pornit. Când memoria decodorului nu mai ajunge, receptorul o eliberează singur după câteva minute de standby, fără înregistrări în curs sau în următoarele 30 de minute: se repornește fără să aprindă televizorul și rămâne în standby. Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
  <section class="card">
    <p class="nota">Jurnalul paznicului, ultimele rânduri</p>
    <pre class="jurnal" id="jurnal"></pre>
  </section>
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
function arata(d){
  if(document.activeElement !== $("interfata")){ $("interfata").value = d.interfata ? "1" : "0"; }
  if(document.activeElement !== $("noapte")){ $("noapte").value = d.noapte === false ? "0" : "1"; }
  if(document.activeElement !== $("asteptare")){
    var s = $("asteptare"); s.textContent = "";
    (d.asteptari || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    s.value = String(d.asteptare);
  }
  $("randAsteptare").classList.toggle("ascuns", !d.interfata);
  var st = d.stare || {};
  $("avertisment").textContent = st.avertisment || "";
  $("avertisment").classList.toggle("ascuns", !st.avertisment);
  $("stare").textContent = st.text || "";
  $("memorie").textContent = (st.memorie_driver || {}).text || "";
  var r = [];
  if(st.reporniri){ r.push("Reporniri ale interfeței de la pornirea receptorului: " + st.reporniri + "."); }
  if(st.ultima_actiune_ora){ r.push("Ultima: " + new Date(st.ultima_actiune_ora * 1000).toLocaleString("ro-RO") + "."); }
  $("reporniri").textContent = r.join(" ");
  $("jurnal").textContent = (d.jurnal || []).join("\\n") || "Jurnalul este gol.";
}
function citeste(){
  return cerere("/api/paznic").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cheie, valoare){
  var q = new URLSearchParams(); q.set(cheie, valoare);
  mesaj("Se salvează...");
  cerere("/api/paznic-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.asteptari){ arata(d); } })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("interfata").addEventListener("change", function(){ trimite("interfata", $("interfata").value); });
$("asteptare").addEventListener("change", function(){ trimite("asteptare", $("asteptare").value); });
$("noapte").addEventListener("change", function(){ trimite("noapte", $("noapte").value); });
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
		N_("Paznicul receptorului"),
		N_("Se citește starea..."),
		N_("Repornește interfața când nu mai răspunde"),
		N_("Da"),
		N_("Nu"),
		N_("Așteaptă înainte de repornire"),
		N_("Eliberează memoria decodorului în standby"),
		N_("Paznicul repornește interfața numai când nu mai dă semn de viață și nici interfața web nu "
			"răspunde. În timpul unei scanări, al citirii pistelor sau al unei rotiri de antenă așteaptă. "
			"Paznicul plăcii rămâne mereu pornit. Când memoria decodorului nu mai ajunge, receptorul o "
			"eliberează singur după câteva minute de standby, fără înregistrări în curs sau în următoarele 30 "
			"de minute: se repornește fără să aprindă televizorul și rămâne în standby. Aceleași setări sunt "
			"pe televizor, în __DRUM_MENIU__."),
		N_("Jurnalul paznicului, ultimele rânduri"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Reporniri ale interfeței de la pornirea receptorului:"),
		N_("Ultima:"),
		N_("Jurnalul este gol."),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează..."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# volum_intarziere_web.py: „Volum și întârziere” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Meniu > Audio & Sound Tracks > Volum și întârziere, data/setup.xml hds_setari_sunet) si a randului „Întârzierea pistei
# pe acest canal” din ecranul AUDIO.
#
# Aceleasi setari ca pe televizor (Components/HdsSetariSunet.py, RANDURI: aceleasi texte, deci aceleasi traduceri):
# pasul volumului, volumul tinut minte pe canal, volumul egal intre canale (AVC-ul placii), intarzierea pe HDMI si pe
# optic. In plus, ce nu incape pe televizor intr-un rand: volumul de acum, ce arata placa (intarzierea fiecarei iesiri),
# canalul si pista de acum cu intarzierea ei, cate canale au volumul tinut minte, cu „Uită volumele ținute minte”.
# O SINGURA LOGICA: totul trece prin Components/HdsSetariSunet.py; setarile sunt config.hds_setari_sunet.*, cu
# notificatorii lor (intarzierea si AVC-ul se scriu in placa de acolo).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/volum-intarziere                       setarile, placa, canalul si pista de acum
#   POST /api/volum-intarziere-seteaza?pas=1..10&afisare=1..10&canal=da|nu&egal=oprit|usor|puternic&hdmi=0..500&optic=0..500
#                                 &pista=-250..250&uita=volume
#                                                oricare dintre ele; toate verificate inainte de orice schimbare
#   GET  /volum-intarziere                           pagina
# Nu se schimba nimic cat e deschis pe televizor ecranul „Volum și întârziere” sau ecranul AUDIO.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; citirile sunt un fisier mic din /proc, scrierile cel mult
# cateva comenzi in /proc/msp/sound0. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul
# lor (S = Components.HdsSetariSunet), config-ul, SystemInfo, sesiunea si fisierul de setari.

ARGUMENTE = ("pas", "afisare", "canal", "egal", "hdmi", "optic", "pista", "uita")
MAX_VALOARE = 12
ECRANE_OCUPATE = ("AudioSelection",)
SETUP_OCUPAT = "hds_setari_sunet"
DA_NU = (("da", "Yes"), ("nu", "No"))


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _s(S=None):
	if S is not None:
		return S
	from Components import HdsSetariSunet
	return HdsSetariSunet


def _cfg(cfg=None):
	if cfg is not None:
		return cfg
	from Components.config import config
	return config


def _sistem(si=None):
	if si is not None:
		return si
	from Components.SystemInfo import SystemInfo
	return SystemInfo


def _fisierSetari(configfile=None):
	if configfile is not None:
		return configfile
	from Components.config import configfile as fisier
	return fisier


def _jurnal(text):
	print("[HdsWebControl] volum-intarziere: %s" % text)


def _dialoguri(sesiune):
	deschise = []
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None:
		deschise.append(curent)
	for x in getattr(sesiune, "dialog_stack", None) or []:
		deschise.append(x[0] if isinstance(x, tuple) else x)
	return deschise


def ocupat(sesiune):
	"""Textul refuzului cand pe televizor e deschis un ecran cu aceleasi setari (ar ramane cu valori vechi), altfel None."""
	if sesiune is None:
		return None
	for d in _dialoguri(sesiune):
		nume = type(d).__name__
		if nume in ECRANE_OCUPATE or (nume == "Setup" and getattr(d, "setup", None) == SETUP_OCUPAT):
			return _t("Pe televizor e deschis un ecran cu setările sunetului. Închide-l, apoi încearcă din nou.")
	return None


def _element(cfg, atribut):
	try:
		return getattr(cfg.hds_setari_sunet, atribut)
	except Exception:
		return None


def _vizibil(si, cere):
	return not cere or bool(si.get(cere))


def _rand(cheie, element, eticheta, descriere):
	if cheie == "canal":
		valoare = "da" if element.value else "nu"
		alegeri = [[v, _t(t)] for v, t in DA_NU]
	else:
		valoare = str(element.value)
		alegeri = [[str(v), _t(element.description[v])] for v in element.choices]
	return {"nume": cheie, "eticheta": _t(eticheta), "descriere": _t(descriere), "valoare": valoare, "alegeri": alegeri}


def stare(S=None, cfg=None, sesiune=None, si=None):
	"""Pentru GET /api/volum-intarziere."""
	S = _s(S)
	cfg = _cfg(cfg)
	si = _sistem(si)
	if "hds_setari_sunet" not in cfg.content.items:
		return {"result": False, "message": _t("Setările sunetului nu sunt încă gata. Încearcă din nou peste câteva secunde.")}
	randuri = []
	for cheie, atribut, eticheta, descriere, cere in S.RANDURI:
		el = _element(cfg, atribut)
		if el is not None and _vizibil(si, cere):
			randuri.append(_rand(cheie, el, eticheta, descriere))
	acum = S.stare()
	pista = acum.get("pista") if si.get("HdsSunetIntarziere") else None
	return {
		"result": True,
		"randuri": randuri,
		"placa": acum.get("placa"),
		"volum": acum.get("volum"),
		"pista": None if not pista else {
			"canal": pista.get("canal") or "", "pista": pista.get("pista") or "", "ms": pista.get("ms", 0),
			"eticheta": _t(S.ETICHETA_PISTA), "descriere": _t(S.AJUTOR_PISTA),
			"alegeri": [[v, t] for v, t in S.alegeriPista()]},
		"volume_tinute": acum.get("volume_tinute", 0),
		"pe_canal": bool(getattr(_element(cfg, "volum_pe_canal"), "value", False)),
		"ocupat": ocupat(sesiune),
	}


def _cuMesaj(rez, reusit, mesaj):
	rez = dict(rez)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def _valoareNoua(cheie, el, text, S):
	"""Textul primit -> valoarea setarii, sau None cand nu e una din alegerile ei."""
	if cheie == "canal":
		return {"da": True, "nu": False}.get(text)
	return text if text in [str(v) for v in el.choices] else None


def seteaza(argumente, S=None, cfg=None, sesiune=None, configfile=None, si=None):
	"""POST /api/volum-intarziere-seteaza. Toate valorile primite trebuie sa fie bune, altfel nu se schimba nimic."""
	S = _s(S)
	cfg = _cfg(cfg)
	si = _sistem(si)
	baza = stare(S, cfg, sesiune, si)
	if not baza["result"]:
		return baza
	if not any(k in argumente for k in ARGUMENTE):
		return _cuMesaj(baza, False, _t("Nu s-a trimis nicio setare."))
	refuz = ocupat(sesiune)
	if refuz:
		return _cuMesaj(baza, False, refuz)
	noi = []
	for cheie, atribut, eticheta, descriere, cere in S.RANDURI:
		if cheie not in argumente:
			continue
		el = _element(cfg, atribut)
		text = argumente[cheie]
		valoare = None if el is None or not _vizibil(si, cere) else _valoareNoua(cheie, el, text, S)
		if valoare is None:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (text[:MAX_VALOARE], _t(eticheta)))
		noi.append((cheie, el, valoare))
	pista = None
	if "pista" in argumente:
		p = baza.get("pista")
		text = argumente["pista"]
		if p is None:
			return _cuMesaj(baza, False, _t("Nu merge acum un canal cu o pistă de sunet."))
		if text not in [v for v, t in S.alegeriPista()]:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (text[:MAX_VALOARE],
				_t(S.ETICHETA_PISTA)))
		pista = int(text)
	uita = argumente.get("uita")
	if uita is not None and uita != "volume":
		return _cuMesaj(baza, False, _t("Nu s-a trimis nicio setare."))
	schimbat = []
	for cheie, el, valoare in noi:
		if el.value != valoare:
			el.value = valoare          # notificatorii scriu in placa (intarzierea, AVC-ul)
			el.save()
			schimbat.append("%s=%s" % (cheie, argumente[cheie]))
	if schimbat:
		_fisierSetari(configfile).save()
	if pista is not None and pista != baza["pista"]["ms"]:
		S.seteazaIntarzierePista(pista)
		schimbat.append("pista=%d" % pista)
	if uita == "volume":
		n = S.uitaVolume()
		schimbat.append("uitate=%d" % n)
	if not schimbat:
		return _cuMesaj(stare(S, cfg, sesiune, si), True, _t("Setarea era deja aceasta."))
	_jurnal(", ".join(schimbat))
	return _cuMesaj(stare(S, cfg, sesiune, si), True, _t("Salvat."))


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, numai cheile stiute, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ARGUMENTE:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_VALOARE].strip()
	return rez


def rute(baza, resource, sesiune=None, S=None, cfg=None, configfile=None, si=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/volum-intarziere: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(S, cfg, _ses(), si))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), S, cfg, _ses(), configfile, si))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /volum-intarziere: pagina „Volum și întârziere”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"volum-intarziere": StareResource(),
		b"volum-intarziere-seteaza": SeteazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /sunet, /limbi si /video."""
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
		_drumMeniu("hds_setari_sunet"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Volum și întârziere</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 8px;color:var(--text-slab);font-weight:normal;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,300px);gap:10px;align-items:center;padding:8px 0 2px;}
  .rand label{font-size:.98rem;}
  .bloc{border-bottom:1px solid var(--bordura);padding:0 0 8px;}
  .bloc:last-of-type{border-bottom:0;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0;}
  .acum{font-size:1.05rem;line-height:1.45;margin:0;overflow-wrap:anywhere;}
  .nota{color:var(--text-slab);font-size:.875rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Volum și întârziere</h1>
<p class="mesaj" id="incarcare">Se citesc setările sunetului...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Acum</h2>
    <p class="acum" id="volum"></p>
    <p class="nota" id="placa"></p>
  </section>
  <section class="card" id="cardPista">
    <h2>Pista de acum</h2>
    <p class="acum" id="pistaText"></p>
    <div class="rand"><label for="r_pista" id="pistaEticheta"></label><select id="r_pista"></select></div>
    <p class="nota" id="pistaAjutor"></p>
  </section>
  <section class="card">
    <div id="randuri"></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button></div>
  </section>
  <section class="card">
    <h2>Volumele ținute minte</h2>
    <p class="acum" id="tinute"></p>
    <div class="butoane"><button type="button" id="uita">Uită volumele ținute minte</button></div>
  </section>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Întârzierea pistei e și în ecranul tastei AUDIO.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var D = null;
var schimbat = false;
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
function valoare(nume){ var s = $("r_" + nume); return s ? s.value : null; }
function optiuni(s, alegeri, v){
  s.textContent = "";
  alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
  s.value = v;
}
function randuri(lista){
  var loc = $("randuri"); loc.textContent = "";
  lista.forEach(function(r){
    var bloc = document.createElement("div"); bloc.className = "bloc";
    var div = document.createElement("div"); div.className = "rand";
    var l = document.createElement("label"); l.htmlFor = "r_" + r.nume; l.textContent = r.eticheta;
    var s = document.createElement("select"); s.id = "r_" + r.nume;
    optiuni(s, r.alegeri, r.valoare);
    s.addEventListener("change", function(){ schimbat = true; });
    var p = document.createElement("p"); p.className = "nota"; p.textContent = r.descriere;
    div.appendChild(l); div.appendChild(s); bloc.appendChild(div); bloc.appendChild(p); loc.appendChild(bloc);
  });
}
function arata(d){
  D = d;
  var v = d.volum;
  $("volum").textContent = v ? ("Volumul: " + v.valoare + (v.mut ? " (fără sunet, mut)" : "")) : "Volumul nu se poate citi acum.";
  var pl = d.placa;
  $("placa").textContent = pl ? ("Placa de sunet întârzie acum: HDMI " + (pl.HDMI0 === null || pl.HDMI0 === undefined ? "?" : pl.HDMI0) + " ms, optic " + (pl.SPDIF0 === null || pl.SPDIF0 === undefined ? "?" : pl.SPDIF0) + " ms.") : "";
  var p = d.pista;
  $("cardPista").classList.toggle("ascuns", !p);
  if(p){
    $("pistaText").textContent = (p.canal || "Canalul de acum") + (p.pista ? ", " + p.pista : "");
    $("pistaEticheta").textContent = p.eticheta;
    $("pistaAjutor").textContent = p.descriere;
    if(document.activeElement !== $("r_pista")){ optiuni($("r_pista"), p.alegeri, String(p.ms)); }
  }
  $("tinute").textContent = d.volume_tinute === 1 ? "Un canal are volumul lui." : (d.volume_tinute + " canale au volumul lor.");
  $("uita").disabled = !d.volume_tinute || !!d.ocupat;
  if(!schimbat){ randuri(d.randuri || []); }
  var blocat = !!d.ocupat;
  $("salveaza").disabled = blocat;
  $("r_pista").disabled = blocat;
  Array.prototype.forEach.call(document.querySelectorAll("#randuri select"), function(s){ s.disabled = blocat; });
  if(d.ocupat){ mesaj(d.ocupat, true); }
}
function citeste(){
  return cerere("/api/volum-intarziere").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările sunetului."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(q){
  mesaj("Se trimite...");
  return cerere("/api/volum-intarziere-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.randuri){ schimbat = false; arata(d); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  ["pas", "afisare", "canal", "egal", "hdmi", "optic"].forEach(function(n){ if(valoare(n) !== null){ q.set(n, valoare(n)); } });
  trimite(q);
});
$("r_pista").addEventListener("change", function(){ var q = new URLSearchParams(); q.set("pista", $("r_pista").value); trimite(q); });
$("uita").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("uita", "volume"); trimite(q); });
function bucla(){ citeste().then(function(){ setTimeout(bucla, 5000); }); }
bucla();
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
		N_("Volum și întârziere"),
		N_("Se citesc setările sunetului..."),
		N_("Acum"),
		N_("Pista de acum"),
		N_("Salvează"),
		N_("Volumele ținute minte"),
		N_("Uită volumele ținute minte"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Întârzierea pistei e și în ecranul tastei "
			"AUDIO."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Volumul:"),
		N_("(fără sunet, mut)"),
		N_("Volumul nu se poate citi acum."),
		N_("Placa de sunet întârzie acum: HDMI"),
		N_("ms, optic"),
		N_("ms."),
		N_("Canalul de acum"),
		N_("Un canal are volumul lui."),
		N_("canale au volumul lor."),
		N_("Receptorul nu a putut citi setările sunetului."),
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

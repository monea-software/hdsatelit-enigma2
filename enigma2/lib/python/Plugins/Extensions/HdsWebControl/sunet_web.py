# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# sunet_web.py: „Ieșirea sunetului” in interfata web (HdsWebControl), perechea randurilor de sunet din Setari A/V
# (data/setup.xml, avsetup; pe televizor: Meniu > Audio & Sound Tracks > Sound Output & Downmix).
#
# Aceleasi setari ca pe televizor: „Ieșirea sunetului” (Automat / Manual), „AC3 downmix” si „DTS downmix” (numai pe
# Manual, ca sa nu para ca schimba ceva pe Automat), „Alege singur pista AC3”. In plus, ce nu incape pe televizor
# intr-un rand: ce primeste televizorul (EDID), ce se trimite acum pentru pista care merge si de ce, si ce arata
# driverul ca pleaca pe HDMI si pe optic (/proc/msp/sound0). O SINGURA LOGICA: citirea, decizia si scrierea sunt in
# Components/HdsSunet.py; setarile sunt chiar config.av.* ale receptorului, cu notificatorii lor (AVSwitch, HdsSunet).
# Randul "DTS recodat in AC3" (config.av.hds_dts_ac3) exista numai cu elementul hdsdtsac3 in imagine, ca pe
# televizor, si merge si pe Automat.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/sunet                                      setarile, televizorul, ce se trimite acum si de ce
#   POST /api/sunet-seteaza?iesire=auto|manual&ac3=da|nu&dts=da|nu&pista=da|nu&dts_ac3=da|nu
#                                                        oricare dintre ele; toate verificate inainte de orice schimbare
#   GET  /sunet                                          pagina
# ac3 / dts sunt setarile pentru Manual („da” = downmix, stereo). Trimise cand iesirea e pe Automat si fara iesire=,
# trec iesirea pe Manual, ca schimbarea lor de pe televizor; cu iesire= in aceeasi cerere se tin minte fara sa atinga
# driverul (HdsSunet.pastreaza), apoi iesirea pune comutatoarele o singura data. „pista” exista numai cand
# HdsPisteLimbi o foloseste (HdsSunet.pistaLegata), ca pe televizor. Nu se schimba nimic cat e deschis pe televizor
# ecranul cu aceste randuri (Setari A/V) sau ecranul AUDIO.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; citirile sunt cateva fisiere mici din /proc, scrierile
# cel mult doua fisiere din /proc/stb/audio. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau
# modulul lor (H = Components.HdsSunet), config-ul, sesiunea si fisierul de setari.

ARGUMENTE = ("iesire", "ac3", "dts", "pista", "dts_ac3")
ORDINE = ("ac3", "dts", "pista", "dts_ac3", "iesire")     # ordinea in care se pun valorile primite (iesirea la urma)
MAX_VALOARE = 20
ECRANE_OCUPATE = ("AudioSelection",)
SETUP_OCUPAT = "avsetup"


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# randurile, in ordinea si cu textele din data/setup.xml (aceleasi msgid, deci aceleasi traduceri)
RANDURI = (
	("iesire", "hds_sunet_iesire", N_("Ieșirea sunetului"),
		N_("Micșorează întâi volumul televizorului. Automat: AC3 și DTS pleacă neschimbate (5.1) numai spre un televizor care le primește. Manual: după rândurile de mai jos.")),
	("pista", "hds_sunet_pista51", N_("Alege singur pista AC3"),
		N_("Da: când AC3 pleacă neschimbat, receptorul pornește pista AC3 (de obicei 5.1) în aceeași limbă. O pistă aleasă de mână nu se schimbă.")),
	("ac3", "downmix_ac3", "AC3 downmix",
		"Yes: the receiver turns AC3 sound into stereo. No: AC3 sound goes unchanged to the TV or sound system (5.1 sound), which must know AC3, otherwise there is no sound."),
	("dts", "downmix_dts", "DTS downmix",
		"Yes: the receiver turns DTS sound into stereo. No: DTS sound goes unchanged to the TV or sound system; if it does not know DTS, there is no sound. Many TVs do not know DTS."),
	("dts_ac3", "hds_dts_ac3", N_("DTS recodat în AC3"),
		N_("Da: receptorul recodează în AC3 (5.1) sunetul DTS al filmelor, pentru un amplificator sau televizor care primește AC3, dar nu DTS. AC3 trebuie să plece neschimbat (Ieșirea sunetului pe Automat sau Downmix AC3 pe Nu). Se aplică de la următorul film pornit.")),
)
DA_NU = (("da", "Yes"), ("nu", "No"))


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsSunet
	return HdsSunet


def _cfg(cfg=None):
	if cfg is not None:
		return cfg
	from Components.config import config
	return config


def _fisierSetari(configfile=None):
	if configfile is not None:
		return configfile
	from Components.config import configfile as fisier
	return fisier


def _jurnal(text):
	print("[HdsWebControl] sunet: %s" % text)


def _dialoguri(sesiune):
	deschise = []
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None:
		deschise.append(curent)
	for x in getattr(sesiune, "dialog_stack", None) or []:
		deschise.append(x[0] if isinstance(x, tuple) else x)
	return deschise


def ocupat(sesiune):
	"""Textul refuzului cand pe televizor e deschis un ecran cu aceleasi setari (ar ramane cu valori vechi), altfel None.
	Fara sesiune (interfata abia pornita) nu e nimic deschis."""
	if sesiune is None:
		return None
	for d in _dialoguri(sesiune):
		nume = type(d).__name__
		if nume in ECRANE_OCUPATE or (nume == "Setup" and getattr(d, "setup", None) == SETUP_OCUPAT):
			return _t("Pe televizor e deschis un ecran cu setările sunetului. Închide-l, apoi încearcă din nou.")
	return None


def _element(cfg, atribut):
	try:
		return getattr(cfg.av, atribut)
	except Exception:
		return None


def _elementVizibil(H, cfg, cheie, atribut):
	"""setarea randului, sau None cand randul nu se arata nici pe televizor (pista fara HdsPisteLimbi legat, DTS recodat
	in AC3 fara elementul hdsdtsac3 in imagine)"""
	if cheie == "pista" and not getattr(H, "pistaLegata", lambda: True)():
		return None
	if cheie == "dts_ac3" and not getattr(H, "areDtsAc3", lambda: False)():
		return None
	return _element(cfg, atribut)


def _serviciu(sesiune):
	try:
		return sesiune.nav.getCurrentService()
	except Exception:
		return None


def _rand(cheie, element, eticheta, descriere):
	if cheie == "iesire":
		valoare = element.value
		alegeri = [[str(v), _t(element.description[v])] for v in element.choices]
	else:
		valoare = "da" if element.value else "nu"
		alegeri = [[v, _t(t)] for v, t in DA_NU]
	return {"nume": cheie, "eticheta": _t(eticheta), "descriere": _t(descriere), "valoare": valoare, "alegeri": alegeri}


def stare(H=None, cfg=None, sesiune=None):
	"""Pentru GET /api/sunet."""
	H = _h(H)
	cfg = _cfg(cfg)
	if _element(cfg, "hds_sunet_iesire") is None or not H.areComutatoare():
		return {"result": False, "message": _t("Receptorul nu are comutatoare pentru sunetul AC3 și DTS.")}
	randuri = []
	for cheie, atribut, eticheta, descriere in RANDURI:
		el = _elementVizibil(H, cfg, cheie, atribut)
		if el is not None:
			randuri.append(_rand(cheie, el, eticheta, descriere))
	acum = H.stare(service=_serviciu(sesiune), cuDriver=True) if sesiune is not None else H.stare(cuDriver=True)
	tv = acum.get("tv")
	return {
		"result": True,
		"iesire": acum["iesire"],
		"randuri": randuri,
		"tv": None if tv is None else {"formate": [[k, tv[k]] for k in sorted(tv)], "text": acum.get("tv_text") or ""},
		"comutatoare": acum.get("comutatoare") or {},
		"acum": None if sesiune is None or not acum.get("fel") else {
			"text": acum.get("text") or "", "motiv": acum.get("motiv") or "", "volum": acum.get("volum") or "",
			"format": acum.get("format"), "trimis": acum.get("trimis")},
		"driver": acum.get("driver") or {},
		"ocupat": ocupat(sesiune),
	}


def _cuMesaj(rez, reusit, mesaj):
	rez = dict(rez)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def seteaza(argumente, H=None, cfg=None, sesiune=None, configfile=None):
	"""POST /api/sunet-seteaza. Toate valorile primite trebuie sa existe, altfel nu se schimba nimic. Ordinea:
	randurile AC3 / DTS (setarile pentru Manual), pista, apoi iesirea."""
	H = _h(H)
	cfg = _cfg(cfg)
	baza = stare(H, cfg, sesiune)
	if not baza["result"]:
		return baza
	if not any(k in argumente for k in ARGUMENTE):
		return _cuMesaj(baza, False, _t("Nu s-a trimis nicio setare."))
	refuz = ocupat(sesiune)
	if refuz:
		return _cuMesaj(baza, False, refuz)
	noi = []
	for cheie, atribut, eticheta, descriere in RANDURI:
		if cheie not in argumente:
			continue
		el = _elementVizibil(H, cfg, cheie, atribut)
		text = argumente[cheie]
		if el is None:
			valoare = None
		elif cheie == "iesire":
			valoare = text if text in [str(v) for v in el.choices] else None
		else:
			valoare = {"da": True, "nu": False}.get(text)
		if valoare is None:
			return _cuMesaj(baza, False, _t("Alegerea „%s” nu există pentru „%s”.") % (text[:MAX_VALOARE], _t(eticheta)))
		noi.append((cheie, el, valoare))
	noi.sort(key=lambda x: ORDINE.index(x[0]))
	schimbat = False
	cuIesire = any(c == "iesire" for c, e, v in noi)
	if cuIesire:
		# randurile pentru Manual se tin minte fara sa atinga driverul; iesirea (la urma) pune comutatoarele o data:
		# notificatorul ei cand se schimba, altfel aplica
		with H.pastreaza():
			for cheie, el, valoare in noi[:-1]:
				if el.value != valoare:
					el.value = valoare
					schimbat = True
				el.save()
		cheie, el, valoare = noi[-1]
		if el.value != valoare:
			el.value = valoare
			schimbat = True
		elif schimbat:
			H.aplica(fortat=True)
		el.save()
	else:
		for cheie, el, valoare in noi:
			if el.value != valoare:
				el.value = valoare        # notificatorii scriu in driver (AVSwitch pe Manual, HdsSunet pe Automat)
				schimbat = True
			el.save()
	if not schimbat:
		return _cuMesaj(stare(H, cfg, sesiune), True, _t("Setarea era deja aceasta."))
	# iesirea poate trece singura pe Manual (o schimbare a randurilor AC3 / DTS pe Automat): se salveaza si ea
	iesire = _element(cfg, "hds_sunet_iesire")
	if iesire is not None:
		iesire.save()
	_fisierSetari(configfile).save()
	_jurnal("setari: %s" % ", ".join("%s=%s" % (c, v) for c, e, v in noi))
	return _cuMesaj(stare(H, cfg, sesiune), True, _t("Salvat."))


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


def rute(baza, resource, sesiune=None, H=None, cfg=None, configfile=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/sunet: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(H, cfg, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), H, cfg, _ses(), configfile))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /sunet: pagina „Ieșirea sunetului”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"sunet": StareResource(),
		b"sunet-seteaza": SeteazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /ceas, /limbi si /video."""
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
		_drumMeniu("audio_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ieșirea sunetului</title>
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
  .acum{font-size:1.05rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.875rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .atentie{color:#ffd28a;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Ieșirea sunetului</h1>
<p class="mesaj" id="incarcare">Se citesc setările sunetului...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Acum</h2>
    <p class="acum" id="acum"></p>
    <p class="nota" id="motiv"></p>
    <p class="nota atentie" id="volum"></p>
    <p class="nota" id="driver"></p>
  </section>
  <section class="card">
    <h2>Televizorul primește</h2>
    <p class="acum" id="tv"></p>
    <p class="nota">Citit din ce anunță televizorul prin HDMI. O bară de sunet legată la televizor se vede aici numai prin ce anunță televizorul.</p>
  </section>
  <section class="card">
    <div id="randuri"></div>
    <p class="nota atentie ascuns" id="avertisment">Micșorează întâi volumul televizorului: când sunetul pleacă neschimbat, volumul receptorului nu mai lucrează, iar sunetul poate fi mai tare.</p>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button></div>
    <p class="nota">Pentru o bară de sunet legată la ieșirea optică a receptorului alege Manual și pune Downmix AC3 pe Nu. Schimbarea se aude sigur de la următorul canal.</p>
  </section>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
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
function vizibile(){
  // pe Automat randurile AC3 / DTS nu se folosesc, deci nu se arata (ca sa nu para ca schimba ceva)
  var auto = valoare("iesire") === "auto";
  ["ac3", "dts"].forEach(function(n){ var b = $("b_" + n); if(b){ b.classList.toggle("ascuns", auto); } });
  $("avertisment").classList.toggle("ascuns", !(auto && D && D.iesire !== "auto"));
}
function randuri(lista){
  var loc = $("randuri"); loc.textContent = "";
  lista.forEach(function(r){
    var bloc = document.createElement("div"); bloc.className = "bloc"; bloc.id = "b_" + r.nume;
    var div = document.createElement("div"); div.className = "rand";
    var l = document.createElement("label"); l.htmlFor = "r_" + r.nume; l.textContent = r.eticheta;
    var s = document.createElement("select"); s.id = "r_" + r.nume;
    r.alegeri.forEach(function(a){
      var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o);
    });
    s.value = r.valoare;
    s.addEventListener("change", function(){ schimbat = true; vizibile(); });
    var p = document.createElement("p"); p.className = "nota"; p.textContent = r.descriere;
    div.appendChild(l); div.appendChild(s); bloc.appendChild(div); bloc.appendChild(p); loc.appendChild(bloc);
  });
}
function arata(d){
  D = d;
  if(d.acum){
    $("acum").textContent = d.acum.text;
    $("motiv").textContent = d.acum.motiv || "";
    $("volum").textContent = d.acum.volum || "";
  } else {
    $("acum").textContent = "Nu merge acum niciun sunet (sau interfața nu are încă legătura cu receptorul).";
    $("motiv").textContent = ""; $("volum").textContent = "";
  }
  var dr = d.driver || {};
  $("driver").textContent = (dr.hdmi || dr.optic) ? ("Driverul arată că pleacă acum: HDMI " + (dr.hdmi || "?") + ", optic " + (dr.optic || "?") + ".") : "";
  $("tv").textContent = d.tv ? (d.tv.text || "numai sunet obișnuit") : "Nu se știe: televizorul nu a spus ce sunet primește (poate e stins sau cablul HDMI nu e legat).";
  if(!schimbat){ randuri(d.randuri || []); }
  vizibile();
  var blocat = !!d.ocupat;
  $("salveaza").disabled = blocat;
  Array.prototype.forEach.call(document.querySelectorAll("#randuri select"), function(s){ s.disabled = blocat; });
  if(d.ocupat){ mesaj(d.ocupat, true); }
}
function citeste(){
  return cerere("/api/sunet").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările sunetului."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  var auto = valoare("iesire") === "auto";
  // pe Automat randurile AC3 / DTS nu se trimit: raman cum erau, pentru Manual
  ["ac3", "dts", "pista", "dts_ac3", "iesire"].forEach(function(n){
    if(valoare(n) === null || (auto && (n === "ac3" || n === "dts"))){ return; }
    q.set(n, valoare(n));
  });
  mesaj("Se trimite...");
  cerere("/api/sunet-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.randuri){ schimbat = false; arata(d); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
function bucla(){ citeste().then(function(){ setTimeout(bucla, 5000); }); }
bucla();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Ieșirea sunetului"),
		N_("Se citesc setările sunetului..."),
		N_("Acum"),
		N_("Televizorul primește"),
		N_("Citit din ce anunță televizorul prin HDMI. O bară de sunet legată la televizor se vede aici "
			"numai prin ce anunță televizorul."),
		N_("Micșorează întâi volumul televizorului: când sunetul pleacă neschimbat, volumul receptorului nu "
			"mai lucrează, iar sunetul poate fi mai tare."),
		N_("Salvează"),
		N_("Pentru o bară de sunet legată la ieșirea optică a receptorului alege Manual și pune Downmix AC3 "
			"pe Nu. Schimbarea se aude sigur de la următorul canal."),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nu merge acum niciun sunet (sau interfața nu are încă legătura cu receptorul)."),
		N_("Driverul arată că pleacă acum: HDMI"),
		N_(", optic"),
		N_("numai sunet obișnuit"),
		N_("Nu se știe: televizorul nu a spus ce sunet primește (poate e stins sau cablul HDMI nu e legat)."),
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

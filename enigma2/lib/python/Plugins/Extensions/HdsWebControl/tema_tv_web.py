# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# tema_tv_web.py: "Tema interfeței" de pe televizor (Clasic / Pro) in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Interfata si aspect > Tema interfetei (Screens/HdsTemaInterfata.py). Aici: aceleasi doua teme,
# aceeasi setare (config.skin.tema_tv), aceeasi logica (Components/HdsTemaTv.py) si aceeasi repornire a interfetei pe
# calea sigura (TryQuitMainloop 3). Tema de aici e numai a televizorului: tema paginilor web (Setari > Aspectul
# interfetei web, cookie-ul hds_tema si config.plugins.hdswebcontrol.tema_web) nu se citeste si nu se schimba.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/tema-tv                        temele, tema aleasa, tema de pe ecran acum, daca trebuie repornit
#   POST /api/tema-tv-seteaza?tema=clasic|pro   alege tema (se vede pe televizor dupa repornirea interfetei)
#   POST /api/tema-tv-reporneste             reporneste interfata (TryQuitMainloop 3)
#   GET  /api/tema-tv-poza?id=clasic|pro     previzualizarea temei (JPEG din pachetul skinului)
#   GET  /tema-tv                            pagina
#
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC dau config si caile).

MAXIM_POZA = 512 * 1024


def _tema(T=None):
	if T is not None:
		return T
	from Components import HdsTemaTv
	return HdsTemaTv


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def stare(T=None, **cai):
	"""GET /api/tema-tv."""
	T = _tema(T)
	rez = T.stare(traducere=_t, **cai)
	rez["result"] = True
	return rez


def seteaza(argumente, T=None, config=None, configfile=None, **cai):
	"""POST /api/tema-tv-seteaza."""
	T = _tema(T)
	bun, mesaj, schimbata = T.seteaza(argumente.get("tema", ""), config=config, configfile=configfile,
		dosar=cai.get("dosar"), exista=cai.get("exista"), traducere=_t, dom_skins=cai.get("dom_skins"))
	rez = stare(T, config=config, **cai)
	if bun and schimbata:
		mesaj = mesaj + " " + _t("Se vede pe televizor după repornirea interfeței.")
	rez.update({"result": bun, "message": mesaj})
	return rez


_CEAS = {}


def reporneste(sesiune, dupa_ms=1500):
	"""POST /api/tema-tv-reporneste: aceeasi cale ca "Repornește interfața" din meniu (TryQuitMainloop 3), dupa
	`dupa_ms`, ca raspunsul cererii sa plece inainte ca interfata sa se opreasca (in emulator, fara asteptare, cererea
	ramanea fara raspuns)."""
	if sesiune is None:
		return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}

	def acum():
		from Screens.Standby import TryQuitMainloop
		sesiune.open(TryQuitMainloop, 3)
	if dupa_ms <= 0:
		acum()
	else:
		from enigma import eTimer
		t = eTimer()
		try:
			_CEAS["legatura"] = t.timeout.connect(acum)
		except AttributeError:
			t.callback.append(acum)
		t.start(dupa_ms, True)
		_CEAS["ceas"] = t
	return {"result": True, "message": _t("Interfața se repornește. Pagina se reîncarcă singură în câteva secunde.")}


def poza(argumente, T=None, dosar=None):
	"""(octetii JPEG, None) sau (None, motivul). Numai cele doua previzualizari din pachetul skinului."""
	T = _tema(T)
	cale = T.cale_poza(argumente.get("id", ""), dosar)
	if cale is None:
		return None, _t("Se cere id=clasic sau id=pro.")
	try:
		with open(cale, "rb") as f:
			date = f.read(MAXIM_POZA + 1)
	except (IOError, OSError):
		return None, _t("Previzualizarea lipsește.")
	if len(date) > MAXIM_POZA or date[:3] != b"\xff\xd8\xff":
		return None, _t("Previzualizarea nu e bună.")
	return date, None


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:6]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ("tema", "id"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:12].strip()
	return rez


def _sesiune():
	try:
		from . import plugin as W
		return W._sesiune
	except Exception:
		return None


def rute(baza, resource, T=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(T))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def _scrie(functie):
		class ScrieResource(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(argumente(request)))
				except Exception as eroare:
					return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return ScrieResource()

	class PozaResource(baza):
		def render_GET(self, request):
			try:
				date, motiv = poza(argumente(request), T)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			if date is None:
				return self._eroare(request, motiv, 404)
			request.setHeader(b"content-type", b"image/jpeg")
			request.setHeader(b"cache-control", b"private, max-age=86400")
			return date

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return ({b"tema-tv": StareResource(), b"tema-tv-seteaza": _scrie(lambda a: seteaza(a, T)),
		b"tema-tv-reporneste": _scrie(lambda a: reporneste(_sesiune())), b"tema-tv-poza": PozaResource()},
		{b"tema-tv": PaginaResource()})


def pagina(request):
	"""Aceeasi poarta ca /paznic: numai din casa, cu browserul asociat sau ?token=."""
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
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_tema_interfata"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tema interfeței de pe televizor</title>
<style>__STIL_COMUN__
  main{max-width:1040px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 6px;}
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
  .teme{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:8px;}
  .card.aleasa{border-color:var(--albastru);box-shadow:0 0 0 1px var(--albastru);}
  .cap{display:flex;justify-content:space-between;align-items:baseline;gap:10px;}
  .cap h2{font-size:1.1rem;margin:0;}
  .eticheta{font-size:.78rem;color:var(--text-slab);white-space:nowrap;}
  .eticheta.acum{color:#4fd18b;}
  .eticheta.dupa{color:#f5b83d;}
  .poza{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;background:#10162a;display:block;}
  .scurt{font-weight:600;margin:0;font-size:.95rem;}
  .descriere{font-size:.9rem;line-height:1.45;margin:0;}
  .card button,.repornire button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:var(--albastru);color:#fff;font:inherit;cursor:pointer;align-self:flex-start;}
  .card button:disabled{opacity:.5;cursor:default;}
  .card button[disabled]{background:#242a33;color:var(--text-slab);cursor:default;}
  .repornire{margin:14px 0 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:12px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Tema interfeței de pe televizor</h1>
<p class="sub">Cum arată meniurile, lista de canale, ghidul și barele de informații pe televizor. Tema paginilor web e o altă setare și rămâne cum e.</p>
<p class="mesaj" id="incarcare">Se citește tema...</p>
<div id="continut" class="ascuns">
  <p class="mesaj eroare ascuns" id="altSkin"></p>
  <div class="teme" id="teme"></div>
  <div class="repornire ascuns" id="repornire">
    <span id="repornire_text"></span>
    <button type="button" id="reporneste">Repornește interfața acum</button>
  </div>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Tema se vede pe televizor după repornirea interfeței: câteva secunde, receptorul nu se oprește și canalul pornește din nou. Culorile rămân cele alese la Setări skin. Același ecran e pe televizor, în __DRUM_MENIU__.</p>
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
  var c = $("teme"); c.textContent = "";
  d.teme.forEach(function(t){
    var card = document.createElement("section"); card.className = "card" + (t.aleasa ? " aleasa" : "");
    var cap = document.createElement("div"); cap.className = "cap";
    var h = document.createElement("h2"); h.textContent = t.nume + " · " + t.eticheta; cap.appendChild(h);
    var e = document.createElement("span"); e.className = "eticheta";
    if(!t.disponibila){ e.textContent = "lipsește din skin"; }
    else if(t.aleasa && t.activa){ e.textContent = "tema de acum"; e.classList.add("acum"); }
    else if(t.aleasa){ e.textContent = "aleasă, după repornire"; e.classList.add("dupa"); }
    else if(t.activa){ e.textContent = "pe ecran până la repornire"; }
    cap.appendChild(e); card.appendChild(cap);
    var img = document.createElement("img"); img.className = "poza"; img.alt = "Previzualizarea temei " + t.nume;
    img.src = adresa("/api/tema-tv-poza?id=" + encodeURIComponent(t.id));
    img.addEventListener("error", function(){ img.classList.add("ascuns"); });
    card.appendChild(img);
    var s = document.createElement("p"); s.className = "scurt"; s.textContent = t.scurt; card.appendChild(s);
    var de = document.createElement("p"); de.className = "descriere"; de.textContent = t.descriere; card.appendChild(de);
    var b = document.createElement("button"); b.type = "button";
    b.textContent = t.aleasa ? "Aleasă" : "Alege tema " + t.nume;
    b.disabled = t.aleasa || !t.disponibila || d.skin_imaginii === false;
    b.addEventListener("click", function(){ alege(t.id); });
    card.appendChild(b);
    c.appendChild(card);
  });
  $("altSkin").textContent = d.nota_skin || "";
  $("altSkin").classList.toggle("ascuns", !d.nota_skin);
  $("repornire").classList.toggle("ascuns", !d.repornire);
  if(d.repornire){
    var ales = d.teme.filter(function(t){ return t.aleasa; })[0];
    $("repornire_text").textContent = "Tema " + (ales ? ales.nume : "") + " se vede pe televizor după repornirea interfeței.";
  }
}
function citeste(){
  return cerere("/api/tema-tv").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi tema."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function alege(id){
  var q = new URLSearchParams(); q.set("tema", id);
  mesaj("Se salvează tema...");
  cerere("/api/tema-tv-seteaza", "POST", q).then(function(d){ if(d.teme){ arata(d); } mesaj(d.message, !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("reporneste").addEventListener("click", function(){
  mesaj("Se repornește interfața...");
  cerere("/api/tema-tv-reporneste", "POST", new URLSearchParams()).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ setTimeout(function(){ location.reload(); }, 15000); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
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
		N_("Tema interfeței de pe televizor"),
		N_("Cum arată meniurile, lista de canale, ghidul și barele de informații pe televizor. Tema "
			"paginilor web e o altă setare și rămâne cum e."),
		N_("Se citește tema..."),
		N_("Repornește interfața acum"),
		N_("Tema se vede pe televizor după repornirea interfeței: câteva secunde, receptorul nu se oprește "
			"și canalul pornește din nou. Culorile rămân cele alese la Setări skin. Același ecran e pe "
			"televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("lipsește din skin"),
		N_("tema de acum"),
		N_("aleasă, după repornire"),
		N_("pe ecran până la repornire"),
		N_("Previzualizarea temei"),
		N_("Aleasă"),
		N_("Alege tema"),
		N_("Tema"),
		N_("se vede pe televizor după repornirea interfeței."),
		N_("Receptorul nu a putut citi tema."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează tema..."),
		N_("Receptorul nu răspunde."),
		N_("Se repornește interfața..."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# limba_interfata_web.py: „Limba meniurilor” in interfata web (HdsWebControl).
#
# Pe televizor: intrarea language_setup din menu.xml (Screens/LanguageSelection.py). Aici: aceeasi lista de limbi
# (Components/Language.py, getLanguageList), cu aceleasi nume ca pe televizor (Components/language_cache.py, in limba
# aleasa acum), si aceeasi schimbare ca OK pe televizor (LanguageSelection.run):
# config.osd.language, activateLanguage, config.misc.languageselected = 0, apoi salvarea setarilor. Ca pe televizor,
# interfata nu se reporneste: ce se deschide de acum e in limba noua, ecranele deschise deja raman pana la inchidere.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/limba-interfata                        limba de acum si lista limbilor (codul, numele de pe televizor)
#   POST /api/limba-interfata-seteaza?limba=ro_RO     schimba limba meniurilor si o salveaza
#   GET  /limba-interfata                            pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (activateLanguage cheama notificarile limbii, care
# schimba textele din memorie). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau limba lor (Lg),
# setarile lor (cfg) si numele lor (nume).

MAX_COD = 16


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _limba(Lg=None):
	if Lg is not None:
		return Lg
	from Components.Language import language
	return language


def _config(cfg=None):
	if cfg is not None:
		return cfg
	from Components.config import config
	return config


def _nume(nume=None):
	"""{limba activa: {cod: numele limbii}} al ecranului de pe televizor (Components/language_cache.LANG_TEXT)."""
	if nume is not None:
		return nume
	try:
		from Components.language_cache import LANG_TEXT
		return LANG_TEXT
	except ImportError:
		return {}


def _salveazaFisierul(configfile=None):
	if configfile is None:
		from Components.config import configfile
	configfile.save()


def _limbi(Lg, cfg, nume):
	"""[[cod, nume]] in ordinea de pe televizor; numele ca in LanguageSelection.updateList (in limba aleasa acum),
	altfel numele din lista limbilor."""
	activa = cfg.osd.language.value
	lista = Lg.getLanguageList()
	if activa not in [c for c, d in lista]:
		# limba salvata e ascunsa (Components/Language.py, LIMBI_COMPLETE): numele in limba in care sunt meniurile
		activa = Lg.getActiveLanguage() or activa
	texte = nume.get(activa, {})
	rez = []
	for cod, date in lista:
		# date = (nume, limba, tara); cheia numelui e limba_tara, ca pe televizor
		cheie = "%s_%s" % (date[1], date[2]) if len(date) > 2 else cod
		rez.append([cod, texte.get(cheie) or (date[0] if date else cod)])
	return rez


def stare(Lg=None, cfg=None, nume=None):
	"""Pentru GET /api/limba-interfata."""
	Lg, cfg, nume = _limba(Lg), _config(cfg), _nume(nume)
	return {"result": True, "activa": Lg.getActiveLanguage() or cfg.osd.language.value,
		"limbi": _limbi(Lg, cfg, nume)}


def seteaza(argumente, Lg=None, cfg=None, nume=None, configfile=None):
	"""POST /api/limba-interfata-seteaza?limba=<cod>: numai un cod din lista; aceeasi schimbare ca OK pe televizor."""
	Lg, cfg, nume = _limba(Lg), _config(cfg), _nume(nume)
	cod = argumente.get("limba", "")
	coduri = [c for c, n in Lg.getLanguageList()]
	if not cod:
		rez = stare(Lg, cfg, nume)
		rez.update({"result": False, "message": _t("Nu s-a trimis nicio limbă.")})
		return rez
	if cod not in coduri:
		rez = stare(Lg, cfg, nume)
		rez.update({"result": False, "message": _t("Limba „%s” nu există pe receptor.") % cod[:MAX_COD]})
		return rez
	cfg.osd.language.value = cod
	cfg.osd.language.save()
	Lg.activateLanguage(cod)
	cfg.misc.languageselected.value = 0
	cfg.misc.languageselected.save()
	_salveazaFisierul(configfile)
	print("[HdsWebControl] limba meniurilor: %s (din web)" % cod)
	rez = stare(Lg, cfg, nume)
	ales = dict((c, n) for c, n in rez["limbi"]).get(cod, cod)
	rez.update({"result": True, "message": _t("Limba meniurilor este acum: %s. Ecranele deschise deja pe televizor "
		"se schimbă la următoarea deschidere.") % ales})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie != "limba":
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_COD].strip()
	return rez


def rute(baza, resource, Lg=None, cfg=None, nume=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/limba-interfata: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(Lg, cfg, nume))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), Lg, cfg, nume))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /limba-interfata: pagina „Limba meniurilor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"limba-interfata": StareResource(),
		b"limba-interfata-seteaza": SeteazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi si /ceas."""
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
		_drumMeniu("language_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Limba meniurilor</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(160px,320px);gap:10px;align-items:center;padding:8px 0;}
  .rand label{font-size:.98rem;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .acum{font-size:.98rem;line-height:1.45;margin:0 0 8px;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Limba meniurilor</h1>
<p class="mesaj" id="incarcare">Se citește limba de acum...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Limba de pe televizor</h2>
    <p class="acum" id="acum"></p>
    <div class="rand"><label for="limba">Limba meniurilor</label><select id="limba"></select></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button></div>
    <p class="nota">Limba se schimbă pe loc, fără repornire. Ce se deschide pe televizor de acum apare în limba nouă; ecranele deschise deja se schimbă la următoarea deschidere. Paginile interfeței web se schimbă la următoarea încărcare.</p>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceeași alegere este pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
var SCHIMBAT = false;
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
function numeActiv(d){
  var n = d.activa;
  (d.limbi || []).forEach(function(a){ if(a[0] === d.activa){ n = a[1]; } });
  return n;
}
function arata(d, cuAlegere){
  DATE = d;
  $("acum").textContent = "Acum: " + numeActiv(d) + ".";
  if(cuAlegere || !SCHIMBAT){
    var sel = $("limba"); sel.textContent = "";
    (d.limbi || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
    sel.value = d.activa;
    SCHIMBAT = false;
  }
}
function citeste(cuAlegere){
  return cerere("/api/limba-interfata").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi limba."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d, cuAlegere);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("limba").addEventListener("change", function(){ SCHIMBAT = true; });
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  q.set("limba", $("limba").value);
  mesaj("Se trimite...");
  cerere("/api/limba-interfata-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.limbi){ arata(d, true); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
citeste(true);
setInterval(function(){ citeste(false); }, 15000);
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
		N_("Limba meniurilor"),
		N_("Se citește limba de acum..."),
		N_("Limba de pe televizor"),
		N_("Salvează"),
		N_("Limba se schimbă pe loc, fără repornire. Ce se deschide pe televizor de acum apare în limba "
			"nouă; ecranele deschise deja se schimbă la următoarea deschidere. Paginile interfeței web se "
			"schimbă la următoarea încărcare."),
		N_("Aceeași alegere este pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Acum:"),
		N_("Receptorul nu a putut citi limba."),
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

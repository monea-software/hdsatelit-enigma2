# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# margini_web.py: "Marginile ecranului" (overscan) in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Interfata si aspect > Marginile ecranului (Screens/OSDCalibration.py). Aici: aceleasi patru
# margini, aceleasi limite (0 - 5% din latura), aceeasi scriere in driver, din aceeasi logica (Components/HdsMargini.py);
# un desen al ecranului cu marginile alese si butonul care deschide cadrul de proba pe televizor (/api/meniu-televizor,
# meniu_web.py).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/margini-ecran                                       marginile, limitele, daca receptorul are driverul
#   POST /api/margini-ecran-seteaza?sus=&dreapta=&jos=&stanga=     salveaza si aplica (o latura lipsa ramane cum e)
#   GET  /margini-ecran                                           pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (setari si cinci fisiere mici din /proc). Modulul nu importa
# nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (M) si setarile lor (config).


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsMargini
	return HdsMargini


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def stare(M=None, config=None, latime=None, inaltime=None, cale=None):
	"""GET /api/margini-ecran."""
	M = _m(M)
	rez = M.stare(config, latime, inaltime, cale or M.CALE_FB, traducere=_t)
	rez["result"] = True
	return rez


def seteaza(argumente, M=None, config=None, latime=None, inaltime=None, cale=None, configfile=None):
	"""POST /api/margini-ecran-seteaza."""
	M = _m(M)
	if not any(argumente.get(l) not in (None, "") for l in M.LATURI):
		rez = stare(M, config, latime, inaltime, cale)
		rez.update({"result": False,
			"message": _t("Se dă cel puțin una dintre sus, dreapta, jos, stanga (în pixeli).")})
		return rez
	bun, rezultat = M.seteaza(argumente, config, latime, inaltime, cale or M.CALE_FB, configfile)
	rez = stare(M, config, latime, inaltime, cale)
	if bun:
		rez.update({"result": True, "message": "Salvat: %s." % rez["text"]})
	else:
		rez.update({"result": False, "message": _t(rezultat)})
	return rez


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ("sus", "dreapta", "jos", "stanga"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:6].strip()
	return rez


def rute(baza, resource, M=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return ({b"margini-ecran": StareResource(), b"margini-ecran-seteaza": SeteazaResource()},
		{b"margini-ecran": PaginaResource()})


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
		_drumMeniu("hds_osd_calibration"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Marginile ecranului</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .desen{position:relative;width:100%;aspect-ratio:16/9;background:#0b0f1d;border-radius:6px;overflow:hidden;}
  .desen .cadru{position:absolute;border:3px solid #f5b83d;box-sizing:border-box;}
  .desen .zona{position:absolute;left:3.75%;top:3.7%;width:92.5%;height:92.6%;border:1px solid #9fb4ff;box-sizing:border-box;}
  .desen .eticheta{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);color:#c9d2e3;font-size:.85rem;text-align:center;}
  .laturi{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 18px;margin-top:14px;}
  .latura{display:grid;grid-template-columns:5.5em 44px minmax(3.5em,1fr) 44px;gap:6px;align-items:center;}
  .latura label{font-size:.98rem;}
  .latura input{min-height:44px;width:100%;box-sizing:border-box;padding:6px 8px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;text-align:center;}
  .latura button,.butoane button{min-height:44px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;}
  .butoane button{padding:8px 16px;}
  .butoane button.principal{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:8px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .laturi{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Marginile ecranului</h1>
<p class="mesaj" id="incarcare">Se citesc marginile...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <div class="desen" aria-hidden="true"><div class="zona"></div><div class="cadru" id="cadru"></div><div class="eticheta" id="eticheta"></div></div>
    <div class="laturi" id="laturi"></div>
    <div class="butoane">
      <button type="button" class="principal" id="salveaza">Salvează</button>
      <button type="button" id="implicite">Înapoi la implicite</button>
      <button type="button" id="televizor">Arată cadrul pe televizor</button>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <p class="nota" id="nota"></p>
  <p class="nota">Cadrul galben e marginea imaginii, linia albastră e zona în care stau ferestrele meniului. Mărește o margine până când, pe televizor, cadrul se vede întreg. Același reglaj e pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var STARE = null;
var LATURI = [["sus", "Sus"], ["dreapta", "Dreapta"], ["jos", "Jos"], ["stanga", "Stânga"]];
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
function valori(){ var v = {}; LATURI.forEach(function(l){ v[l[0]] = parseInt($("m_" + l[0]).value, 10) || 0; }); return v; }
function desen(){
  if(!STARE){ return; }
  var v = valori(), W = STARE.latime, H = STARE.inaltime, c = $("cadru");
  c.style.left = (v.stanga * 100 / W) + "%"; c.style.top = (v.sus * 100 / H) + "%";
  c.style.width = ((W - v.stanga - v.dreapta) * 100 / W) + "%"; c.style.height = ((H - v.sus - v.jos) * 100 / H) + "%";
  // numele laturilor din LATURI (traduse), in aceeasi ordine: sus, dreapta, jos, stanga
  $("eticheta").textContent = LATURI.map(function(l){ return l[1] + " " + v[l[0]] + " px"; }).join(" · ");
}
function pune(nume, v){
  var i = $("m_" + nume), max = STARE.maxim[nume];
  i.value = Math.max(0, Math.min(max, v)); desen();
}
function construieste(){
  var c = $("laturi"); c.textContent = "";
  LATURI.forEach(function(l){
    var d = document.createElement("div"); d.className = "latura";
    var e = document.createElement("label"); e.htmlFor = "m_" + l[0]; e.textContent = l[1];
    var minus = document.createElement("button"); minus.type = "button"; minus.textContent = "−"; minus.setAttribute("aria-label", l[1] + ": mai mică");
    var i = document.createElement("input"); i.type = "number"; i.id = "m_" + l[0]; i.min = 0; i.step = STARE.pas; i.max = STARE.maxim[l[0]]; i.inputMode = "numeric";
    var plus = document.createElement("button"); plus.type = "button"; plus.textContent = "+"; plus.setAttribute("aria-label", l[1] + ": mai mare");
    minus.addEventListener("click", function(){ pune(l[0], (parseInt(i.value, 10) || 0) - STARE.pas); });
    plus.addEventListener("click", function(){ pune(l[0], (parseInt(i.value, 10) || 0) + STARE.pas); });
    i.addEventListener("input", desen);
    d.appendChild(e); d.appendChild(minus); d.appendChild(i); d.appendChild(plus); c.appendChild(d);
  });
}
function arata(d){
  var prima = !STARE; STARE = d;
  if(prima){ construieste(); }
  LATURI.forEach(function(l){ var i = $("m_" + l[0]); i.max = d.maxim[l[0]]; i.value = d.margini[l[0]]; });
  $("nota").textContent = d.nota + " " + "Cel mult 5 la sută din latură: %s stânga și dreapta, %s sus și jos."
    .replace("%s", d.maxim.stanga + " px").replace("%s", d.maxim.sus + " px");
  desen();
}
function citeste(){
  return cerere("/api/margini-ecran").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi marginile."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(v){
  var q = new URLSearchParams(); Object.keys(v).forEach(function(k){ q.set(k, v[k]); });
  mesaj("Se salvează...");
  cerere("/api/margini-ecran-seteaza", "POST", q).then(function(d){ if(d.margini){ arata(d); } mesaj(d.message, !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("salveaza").addEventListener("click", function(){ trimite(valori()); });
$("implicite").addEventListener("click", function(){ trimite({sus: 0, dreapta: 0, jos: 0, stanga: 0}); });
$("televizor").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("id", "hds_osd_calibration");
  cerere("/api/meniu-televizor", "POST", q).then(function(d){ mesaj(d.message, !d.result); }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
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
		N_("Marginile ecranului"),
		N_("Se citesc marginile..."),
		N_("Salvează"),
		N_("Înapoi la implicite"),
		N_("Arată cadrul pe televizor"),
		N_("Cadrul galben e marginea imaginii, linia albastră e zona în care stau ferestrele meniului. "
			"Mărește o margine până când, pe televizor, cadrul se vede întreg. Același reglaj e pe "
			"televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Sus"),
		N_("Dreapta"),
		N_("Jos"),
		N_("Stânga"),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_(": mai mică"),
		N_("Cel mult 5 la sută din latură: %s stânga și dreapta, %s sus și jos."),
		N_("Receptorul nu a putut citi marginile."),
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

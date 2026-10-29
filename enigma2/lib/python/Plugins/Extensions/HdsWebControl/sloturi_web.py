# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# sloturi_web.py: „Jurnalele celorlalte sloturi” in interfata web (HdsWebControl).
#
# Orice ecran de pe receptor are pereche in interfata web. Pe receptor: Meniu > Sistem & Dispozitive > Jurnalele
# celorlalte sloturi (Screens/HdsJurnaleSloturi.py). Aici: aceeasi cautare a sloturilor si acelasi buton, din aceeasi
# logica (Components/HdsJurnaleSloturi.py): o apasare pune pe stick si trimite tot ce au lasat celelalte sloturi.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/jurnale-sloturi          starea: sloturile gasite (cauta o data, la prima cerere) si rezultatul punerii
#   POST /api/jurnale-sloturi-pune     porneste punerea pe stick si trimiterea (pe un fir; starea o spune GET)
#   POST /api/jurnale-sloturi-cauta    cauta din nou (un stick pus intre timp)
#   GET  /jurnale-sloturi              pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; lucrarea merge pe firul ei (Components/HdsJurnaleSloturi).
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (J).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _j(J=None):
	if J is not None:
		return J
	from Components import HdsJurnaleSloturi
	return HdsJurnaleSloturi


def stare(J=None):
	"""Ce arata pagina: sloturile (cu textul lor), rezultatul punerii, daca lucreaza; prima cerere porneste cautarea."""
	J = _j(J)
	l = J.lucrare()
	s = l.stare()
	if s["sloturi"] is None and not s["merge"] and s["fel"] == "":
		l.porneste("cauta")
		s = l.stare()
	return {
		"result": True,
		"merge": s["merge"],
		"fel": s["fel"],
		"sloturi": s["sloturi"] or [],
		"text_sloturi": J.textSloturi(s["sloturi"]) if (s["sloturi"] is not None or s["fel"] == "cauta") and not
			(s["merge"] and s["fel"] == "cauta") else _t(J.CAUT),
		"text_rezultat": (_t(J.LUCREZ) if s["merge"] and s["fel"] == "pune" else J.textRezultat(s["rezultat"])),
		"poate_pune": bool(s["sloturi"]) and not s["merge"],
	}


def pune(J=None):
	J = _j(J)
	l = J.lucrare()
	s = l.stare()
	if not s["sloturi"]:
		return {"result": False, "message": _t(J.NICIUN_SLOT)}
	if not l.porneste("pune"):
		return {"result": False, "message": _t(J.LUCREZ)}
	return {"result": True, "message": _t(J.LUCREZ)}


def cauta(J=None):
	J = _j(J)
	if not J.lucrare().porneste("cauta"):
		return {"result": False, "message": _t(J.LUCREZ)}
	return {"result": True, "message": _t(J.CAUT)}


def rute(baza, resource, J=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/jurnale-sloturi."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(J))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PuneResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, pune(J))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CautaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, cauta(J))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /jurnale-sloturi: pagina „Jurnalele celorlalte sloturi”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"jurnale-sloturi": StareResource(),
		b"jurnale-sloturi-pune": PuneResource(),
		b"jurnale-sloturi-cauta": CautaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic."""
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
	"""Drumul de pe receptor spre ecran (meniu_web.drumHtml); fara pachet (probele de pe PC) ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__", _drumMeniu("hds_jurnale_sloturi"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jurnalele celorlalte sloturi</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1rem;line-height:1.5;margin:0;white-space:pre-line;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .buton{min-height:48px;padding:10px 18px;border-radius:10px;border:0;background:#1f9d55;color:#fff;font:inherit;font-weight:600;cursor:pointer;width:100%;}
  .buton:disabled{opacity:.45;cursor:default;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.95rem;min-height:1.3em;white-space:pre-line;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Jurnalele celorlalte sloturi</h1>
<section class="card">
  <p class="acum" id="sloturi">Caut celelalte sloturi...</p>
</section>
<section class="card">
  <button class="buton" id="pune" disabled>Pune pe stick și trimite</button>
  <p class="mesaj" id="rezultat"></p>
</section>
<p class="nota">Dacă o imagine dintr-un alt slot nu pornește, aici iei pașii pornirilor ei, rapoartele și jurnalele de cădere rămase acolo. O apăsare le pune pe stick și le trimite, ca să aflăm de ce nu pornește. Același ecran e pe receptor, în __DRUM_MENIU__.</p>
</main>
<script>
var CFG = __CONFIG__;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
var ceas = null;
function arata(d){
  $("sloturi").textContent = d.text_sloturi || "";
  $("rezultat").textContent = d.text_rezultat || "";
  $("pune").disabled = !d.poate_pune;
  if(d.merge && !ceas){ ceas = setInterval(citeste, 1500); }
  if(!d.merge && ceas){ clearInterval(ceas); ceas = null; }
}
function citeste(){
  return cerere("/api/jurnale-sloturi").then(function(d){
    if(!d.result){ $("sloturi").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    arata(d);
  }).catch(function(){ $("sloturi").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("pune").addEventListener("click", function(){
  $("pune").disabled = true;
  cerere("/api/jurnale-sloturi-pune", "POST").then(function(d){
    $("rezultat").textContent = d.message || "";
    $("rezultat").classList.toggle("eroare", !d.result);
    if(!ceas){ ceas = setInterval(citeste, 1500); }
  }).catch(function(){ $("rezultat").textContent = "Receptorul nu răspunde."; });
});
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sablonului de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text nou sau schimbat
# in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Jurnalele celorlalte sloturi"),
		N_("Caut celelalte sloturi..."),
		N_("Pune pe stick și trimite"),
		N_("Dacă o imagine dintr-un alt slot nu pornește, aici iei pașii pornirilor ei, rapoartele și jurnalele de "
			"cădere rămase acolo. O apăsare le pune pe stick și le trimite, ca să aflăm de ce nu pornește. Același "
			"ecran e pe receptor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
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

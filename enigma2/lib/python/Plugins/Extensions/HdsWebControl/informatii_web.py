# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# informatii_web.py: „System Information” in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > System Information > Despre imagine, Device & Hardware, Tuner Overview, Memory Status,
# Storage & Disks, Network Status (Screens/Information.py) si Informații HDMI (Screens/HdsHdmiInfo.py). Aici, aceleasi
# texte din acelasi cod: textul fiecarui ecran se ia chiar din functia lui populate() (scrie in self["text"]), iar
# Informații HDMI din Components/HdsHdmiDate.py (citeste + coloane), ca pe televizor. Numai citire.
#
# Rute (poarta comuna a HdsJsonResource):
#   GET /api/informatii?pagina=despre|receptor|tunere|memorie|stocare|retea|hdmi
#   GET /informatii/<pagina>                 pagina (adresa din menu.xml; fara <pagina>, „Despre imagine”)
#
# FIRUL: render_GET ruleaza pe firul enigma2, ca ecranele de pe televizor (care citesc la fel, la deschidere).


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# (cheia paginii, clasa din Screens/Information.py, titlul ecranului de pe televizor)
PAGINI = (
	("despre", "HdsAbout", N_("Despre imagine")),
	("receptor", "HdsReceiverInfo", N_("Receptor și procesor")),
	("tunere", "HdsTunerInfo", N_("Tunere")),
	("memorie", "HdsMemoryInfo", N_("Memorie")),
	("stocare", "HdsStorageInfo", N_("Discuri și stocare")),
	("retea", "HdsNetworkInfo", N_("Rețea")),
)
RADACINA_HDMI = "/"        # probele pun aici un dosar cu /proc/msp falsi


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


class _Text(object):
	def __init__(self):
		self.text = ""

	def setText(self, text):
		self.text = text


class _Ecran(dict):
	"""Ce foloseste populate() din ecran: self["text"].setText(...)."""


def _textEcran(clasa, Information=None):
	if Information is None:
		from Screens import Information
	cls = getattr(Information, clasa)
	e = _Ecran()
	e["text"] = _Text()
	cls.populate(e)
	return e["text"].text


def _hdmi(D=None):
	if D is None:
		from Components import HdsHdmiDate as D
	ales = None
	try:
		from Components.config import config
		el = config.av.content.items.get("hds_videomode")
		ales = el.value if el is not None else None
	except Exception:
		ales = None
	s = D.citeste(RADACINA_HDMI)
	coloane = []
	for col in D.coloane(s, ales):
		randuri = []
		for r in col:
			if r[0] == "titlu":
				randuri.append({"titlu": r[1]})
			else:
				randuri.append({"eticheta": r[1], "valoare": r[2], "ton": r[3]})
		coloane.append(randuri)
	return {"result": True, "pagina": "hdmi", "titlu": _t(D.TITLU), "coloane": coloane}


def informatii(pagina, Information=None, D=None):
	"""GET /api/informatii?pagina=..."""
	lista = [{"id": p, "titlu": _t(titlu)} for p, _c, titlu in PAGINI] + [{"id": "hdmi", "titlu": _t("Informații HDMI")}]
	if pagina == "hdmi":
		rez = _hdmi(D)
	else:
		gasit = [x for x in PAGINI if x[0] == (pagina or "despre")]
		if not gasit:
			return {"result": False, "message": _t("Pagina „%s” nu există.") % (pagina or "")[:20], "pagini": lista}
		cheie, clasa, titlu = gasit[0]
		rez = {"result": True, "pagina": cheie, "titlu": _t(titlu), "text": _textEcran(clasa, Information)}
	rez["pagini"] = lista
	return rez


def rute(baza, resource):
	class InformatiiResource(baza):
		def render_GET(self, request):
			pagina = ""
			valori = (getattr(request, "args", None) or {}).get(b"pagina")
			if valori:
				pagina = valori[0].decode("ascii", "replace")[:20]
			try:
				return self._raspunde(request, informatii(pagina))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {b"informatii": InformatiiResource()}, PaginaResource()


def pagina(request):
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
		config_pagina = P._configPanou("", "", browser.get("nume", ""))   # numai citire: fara tokenul CSRF
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
		_drumMeniu("info_screen"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informații despre receptor</title>
<style>__STIL_COMUN__
  main{max-width:1040px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  nav.file{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;}
  nav.file button{min-height:40px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;font-size:.88rem;cursor:pointer;}
  nav.file button.ales{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  pre.text{font-family:monospace;font-size:.85rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;margin:0;}
  .coloane{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;}
  .coloane h3{font-size:.95rem;margin:10px 0 6px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .coloane .r{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px solid var(--bordura);font-size:.88rem;}
  .coloane .r span:last-child{text-align:right;word-break:break-word;}
  .bun{color:#7fdc9a;} .atentie{color:#f5b83d;} .rau{color:#ff8a80;} .stins{color:var(--text-slab);}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
</style>
</head>
<body>
<main>
<h1 id="titlu">Informații despre receptor</h1>
<nav class="file" id="file"></nav>
<section class="card" id="continut"><p class="mesaj" id="mesaj">Se citesc informațiile...</p></section>
<p class="nota">Aceleași ecrane sunt pe televizor, în __DRUM_MENIU__.</p>
</main>
<script>
var CFG = __CONFIG__;
// pagina aleasa: /informatii/<pagina> (adresa din menu.xml, web=) sau /informatii?pagina=<pagina>
var ALES = (location.pathname.split("/")[2] || new URLSearchParams(location.search).get("pagina") || "despre");
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale){
  return fetch(adresa(cale), {cache: "no-store", credentials: "same-origin"}).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json();
  });
}
function file(d){
  var n = $("file"); n.textContent = "";
  (d.pagini || []).forEach(function(p){
    var b = document.createElement("button"); b.type = "button"; b.textContent = p.titlu; if(p.id === ALES){ b.className = "ales"; }
    b.addEventListener("click", function(){ ALES = p.id; history.replaceState(null, "", "/informatii/" + p.id); citeste(); });
    n.appendChild(b);
  });
}
function arata(d){
  var c = $("continut"); c.textContent = "";
  $("titlu").textContent = d.titlu;
  if(d.text !== undefined){ var pre = document.createElement("pre"); pre.className = "text"; pre.textContent = d.text; c.appendChild(pre); return; }
  var g = document.createElement("div"); g.className = "coloane";
  (d.coloane || []).forEach(function(col){
    var div = document.createElement("div");
    col.forEach(function(r){
      if(r.titlu !== undefined){ var h = document.createElement("h3"); h.textContent = r.titlu; div.appendChild(h); return; }
      var rd = document.createElement("div"); rd.className = "r";
      var e = document.createElement("span"); e.textContent = r.eticheta; var v = document.createElement("span"); v.textContent = r.valoare; v.className = r.ton || "";
      rd.appendChild(e); rd.appendChild(v); div.appendChild(rd);
    });
    g.appendChild(div);
  });
  c.appendChild(g);
}
function citeste(){
  cerere("/api/informatii?pagina=" + encodeURIComponent(ALES)).then(function(d){
    file(d);
    if(!d.result){ $("continut").textContent = d.message || "Receptorul nu a putut citi informațiile."; return; }
    arata(d);
  }).catch(function(){ $("continut").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
citeste();
setInterval(function(){ if(ALES === "hdmi" || ALES === "memorie"){ citeste(); } }, 5000);
setInterval(function(){ if(ALES === "receptor" && document.visibilityState === "visible"){ citeste(); } }, 2000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Informații despre receptor"),
		N_("Se citesc informațiile..."),
		N_("Aceleași ecrane sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul nu a putut citi informațiile."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# liste_internet_web.py: "Liste de canale de pe internet" in interfata web (HdsWebControl).
#
# Pereche a ecranului de pe televizor (Screens/HdsListeInternet.py: Meniu > Scanare > Liste implicite de canale,
# randul "Descarcă o listă de canale de pe internet"). Aceleasi liste, aceeasi ordine dupa antena, aceeasi instalare
# si aceeasi punere la loc, din acelasi modul (Components/HdsListeInternet.py), deci un singur import odata pentru
# televizor si web (zavorul importului de canale).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/liste-internet[?citeste=1]       listele (citite de la autori daca nu sunt tinute minte), antena, starea
#   POST /api/liste-internet-instaleaza?id=<id> descarca si instaleaza lista (copia de siguranta intai)
#   POST /api/liste-internet-pune-la-loc        pune la loc lista de dinainte de ultima instalare
#   GET  /liste-internet                        pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 si raspund pe loc (citirea, descarcarea si importul merg
# pe firul lor; pagina intreaba din nou). Fisierul nu importa nimic din enigma2 la incarcare: probele dau modulul (M).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsListeInternet
	return HdsListeInternet


def argumente(request):
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token":
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v).strip()
	return rez


def stare(a, M=None):
	"""GET /api/liste-internet."""
	M = _m(M)
	M.porneste_citirea(fortat=a.get("citeste") == "1")
	ant = M.antena()
	rez = M.stare_publica(ant)
	rez.update({
		"result": True,
		"titlu": _t("Liste de canale de pe internet"),
		"intro": M.text_intro(),
		"antena": [M.text_pozitie(p) for p in ant.get("pozitii") or []],
		"texte": {
			"instaleaza": _t("Instalează"),
			"gol": M.text_gol(),
			"citeste": _t("Se citesc listele de la autori..."),
			"toti": M.text_autor(""),
		},
	})
	return rez


def instaleaza(a, M=None):
	"""POST /api/liste-internet-instaleaza."""
	M = _m(M)
	if "automat" in a:
		if a.get("automat") not in ("da", "nu") or a.get("id"):
			return {"result": False, "message": _t("Alege Da sau Nu pentru actualizarea automată.")}
		fel, _l = M.porneste_setare_automat(a["automat"] == "da")
		return {"result": fel == "pornit", "message": _t("Se salvează alegerea...") if fel == "pornit" else
			_t("Un import e deja în curs. Așteaptă să se termine.")}
	fel, _l = M.porneste_instalarea(a.get("id", ""))
	if fel == "necunoscuta":
		M.porneste_citirea(fortat=True)
		return {"result": False, "message": M.text_schimbata()}
	if fel == "ocupat":
		return {"result": False, "message": _t("Un import e deja în curs. Așteaptă să se termine.")}
	l = M.lista_dupa_id(a.get("id", "")) or {"autor_nume": "", "nume": ""}
	return {"result": True, "message": _t("Se descarcă și se instalează %s...") % ("%s: %s" % (l["autor_nume"],
		l["nume"]))}


def pune_la_loc(a, M=None):
	"""POST /api/liste-internet-pune-la-loc."""
	M = _m(M)
	fel, _l = M.porneste_punerea_la_loc()
	if fel == "nimic":
		return {"result": False, "message": _t("Nu este nicio listă de pus la loc.")}
	if fel == "ocupat":
		return {"result": False, "message": _t("Un import e deja în curs. Așteaptă să se termine.")}
	return {"result": True, "message": _t("Se pune la loc lista de dinainte...")}


def rute(baza, resource, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	_m(M).demareaza_automat()

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class InstaleazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, instaleaza(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PuneLaLocResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, pune_la_loc(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /liste-internet: pagina."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return {
		b"liste-internet": StareResource(),
		b"liste-internet-instaleaza": InstaleazaResource(),
		b"liste-internet-pune-la-loc": PuneLaLocResource(),
	}, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /liste-implicite: reteaua locala, apoi ?token= sau cookie-ul browserului asociat."""
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


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Liste de canale de pe internet</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:0 0 12px;}
  .intro{font-size:.92rem;line-height:1.45;margin:0 0 10px;color:var(--text-slab);}
  .filtre{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 6px;}
  .filtre label{font-size:.9rem;}
  .filtre select{min-height:40px;}
  .rand{display:flex;align-items:center;gap:10px;padding:10px 12px;margin:6px 0 0;border-radius:8px;border:1px solid var(--bordura);}
  .rand .nume{flex:1;min-width:0;}
  .rand .titlu{font-weight:600;display:block;}
  .rand .desc{display:block;color:var(--text-slab);font-size:.82rem;line-height:1.35;white-space:pre-line;}
  .rand .antena{color:#5fd47d;}
  .rand button{min-height:40px;}
  .bara{display:flex;flex-wrap:wrap;gap:10px;align-items:center;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;}
  .eroare{color:#ffb4a8;}
</style>
</head>
<body>
<main>
<h1 id="titlu">Liste de canale de pe internet</h1>
<section class="card">
  <p class="intro" id="intro"></p>
  <div class="filtre">
    <label>Sateliți <select id="fel"></select></label>
    <label>Autor <select id="autor"></select></label>
  </div>
  <div class="bara">
    <span id="instalata"></span>
    <button id="pune" type="button" hidden>Pune la loc lista de dinainte</button>
  </div>
  <p><label>Actualizare automată <select id="automat"><option value="nu">Nu</option><option value="da">Da</option></select></label></p>
  <div id="liste"></div>
</section>
<p class="mesaj" id="mesaj"></p>
</main>
<script>
var CFG = __CONFIG__;
var date = null, felAles = null, autorAles = "", asteapta = null;
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
    return r.json();
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function optiuni(sel, lista, ales){
  sel.textContent = "";
  lista.forEach(function(o){ var e = document.createElement("option"); e.value = o.cheie; e.textContent = o.nume; e.selected = o.cheie === ales; sel.appendChild(e); });
}
function deseneaza(){
  var c = $("liste"); c.textContent = "";
  var n = 0;
  (date.liste || []).forEach(function(l){
    if(felAles !== "toate" && l.fel !== felAles){ return; }
    if(autorAles && l.autor !== autorAles){ return; }
    n++;
    var r = document.createElement("div"); r.className = "rand";
    var s = document.createElement("span"); s.className = "nume";
    var t = document.createElement("span"); t.className = "titlu" + (l.potrivita ? " antena" : ""); t.textContent = l.autor_nume + ": " + l.nume;
    var d = document.createElement("span"); d.className = "desc"; d.textContent = l.descriere;
    s.appendChild(t); s.appendChild(d); r.appendChild(s);
    var b = document.createElement("button"); b.type = "button"; b.textContent = date.texte.instaleaza; b.disabled = !!date.lucreaza;
    b.onclick = function(){ instaleaza(l.id); };
    r.appendChild(b); c.appendChild(r);
  });
  if(!n && !date.citeste){ var g = document.createElement("p"); g.className = "intro"; g.textContent = date.texte.gol; c.appendChild(g); }
}
function arata(d){
  date = d;
  $("titlu").textContent = d.titlu || $("titlu").textContent;
  $("intro").textContent = d.intro || "";
  if(felAles === null){ felAles = d.fel_implicit || "toate"; }
  optiuni($("fel"), d.feluri || [], felAles);
  optiuni($("autor"), [{cheie: "", nume: d.texte.toti}].concat(d.autori || []), autorAles);
  $("instalata").textContent = d.instalata_text || "";
  $("pune").hidden = !d.poate_pune_la_loc;
  $("pune").disabled = !!d.lucreaza;
  $("automat").value = d.automat ? "da" : "nu";
  $("automat").disabled = !!d.lucreaza || !d.automat_incarcat;
  deseneaza();
  var m = [];
  if(d.citeste){ m.push(d.texte.citeste); }
  (d.erori || []).forEach(function(e){ m.push(e); });
  if(!d.lucreaza && d.ultimul && d.ultimul.mesaje){ m = m.concat(d.ultimul.mesaje.slice(0, 2)); }
  if(m.length || !d.lucreaza){ mesaj(m.join(" "), d.ultimul && !d.ultimul.ok && !d.lucreaza); }
  clearTimeout(asteapta);
  if(d.citeste || d.lucreaza || !d.automat_incarcat){ asteapta = setTimeout(citeste, 1500); }
}
function citeste(forta){
  cerere("/api/liste-internet" + (forta ? "?citeste=1" : "")).then(function(d){
    if(!d.result){ mesaj(d.message || "", true); return; }
    arata(d);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function porneste(cale){
  cerere(cale, "POST").then(function(d){
    mesaj(d.message || "", !d.result);
    if(!d.result){ clearTimeout(asteapta); asteapta = setTimeout(citeste, 1500); }
    if(d.result){ date.lucreaza = "da"; deseneaza(); $("pune").disabled = true; clearTimeout(asteapta); asteapta = setTimeout(citeste, 1500); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function instaleaza(id){ porneste("/api/liste-internet-instaleaza?id=" + encodeURIComponent(id)); }
$("fel").onchange = function(){ felAles = this.value; deseneaza(); };
$("autor").onchange = function(){ autorAles = this.value; deseneaza(); };
$("pune").onclick = function(){ porneste("/api/liste-internet-pune-la-loc"); };
$("automat").onchange = function(){ this.disabled = true; porneste("/api/liste-internet-instaleaza?automat=" + this.value); };
citeste(false);
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
		N_("Liste de canale de pe internet"),
		N_("Sateliți"),
		N_("Autor"),
		N_("Pune la loc lista de dinainte"),
		N_("Actualizare automată"),
		N_("Da"),
		N_("Nu"),
	),
	"js": (
		N_("browser deconectat"),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# culegere_canale_web.py: „Scanare detaliată” in interfata web (HdsWebControl), perechea ecranului de pe
# televizor (Meniu > Scanare, Screens/HdsCulegereTotala.py).
#
# O SINGURA LOGICA: planul, estimarea, reluarea, judecata, oprirea si toate textele vin din
# Components/HdsCulegereTotala.py; pornirea deschide ecranul de progres pe televizor (Screens/HdsCulegereTotala.
# porneste_pe_televizor), ca si cum omul ar fi apasat Verde acolo, deci orice tasta de pe telecomanda o opreste la fel.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/culegere-canale?pozitie=toti|192&fta=0|1&necunoscute=0|1     alegerile, planul (cate canale, cat dureaza,
#        reluarea) si trecerea in curs sau ultima; cu doar_stare=1 numai trecerea (pagina o cere la 3 s cat merge si
#        la 15 s altfel; planul, care citeste baza, numai la o schimbare a alegerilor si la sfarsitul unei treceri)
#   POST /api/culegere-canale-porneste?pozitie=..&fta=..&necunoscute=..&de_la_capat=0|1   porneste pe televizor
#   POST /api/culegere-canale-opreste                                       opreste; canalul de dinainte revine
#   GET  /scanare-detaliata si /culegere-canale (adresa veche)               pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Planul citeste lamedb numai cand s-a schimbat (tinut in
# memorie de modul) si randurile bazei care au grupele cerute; cat merge trecerea pagina cere numai starea. Fisierul nu
# importa nimic din enigma2 la incarcare: probele de pe PC dau furnizorul lor (M).

TOTI = "toti"


class _Furnizor(object):
	"""Modulele adevarate ale imaginii, importate abia la prima cerere."""

	@property
	def C(self):
		from Components import HdsCulegereTotala
		return HdsCulegereTotala

	@property
	def S(self):
		from Screens import HdsCulegereTotala
		return HdsCulegereTotala

	def sesiune(self):
		from . import plugin
		return getattr(plugin, "_sesiune", None)


def _m(M=None):
	return M if M is not None else _Furnizor()


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:12]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:12].strip()
	return rez


def optiuni(argumente_, C):
	"""Alegerile din cerere; fara ele, cele ale ultimei treceri (ca reluarea sa se vada), altfel cele implicite."""
	if not any(k in argumente_ for k in ("pozitie", "fta", "necunoscute")):
		vechi = C.citeste_stare() or {}
		o = vechi.get("optiuni")
		if isinstance(o, dict):
			return C.optiuni_din(o.get("pozitie"), o.get("fta"), o.get("necunoscute", True))
		return C.optiuni_implicite()
	return C.optiuni_din(argumente_.get("pozitie") or None, argumente_.get("fta") == "1",
		argumente_.get("necunoscute", "1") != "0")


def rulare(C):
	"""Trecerea in curs sau ultima, cu randurile de pe televizor; None daca n-a fost niciuna de la pornire."""
	s = C.stare_rulare()
	if not s:
		return None
	rez = dict(s)
	if s.get("activ"):
		rez["linie"], rez["detalii"] = C.texte_mers(s)
	else:
		rez["text"] = s.get("text") or C.text_rezultat(s)
	return rez


def stare(argumente_, M=None):
	"""GET /api/culegere-canale."""
	M = _m(M)
	C = M.C
	rez = {"result": True, "titlu": _t(C.TITLU), "rulare": rulare(C), "indiciu": _t(C.T_INDICIU)}
	if argumente_.get("doar_stare") == "1":
		return rez
	sesiune = M.sesiune()
	receptor = C.Receptor(sesiune.nav) if sesiune is not None else None
	o = optiuni(argumente_, C)
	info = C.plan_receptor(o, receptor=receptor)
	rez.update({
		"descriere": _t(C.DESCRIERE),
		"optiuni": {"pozitie": TOTI if o["pozitie"] is None else str(o["pozitie"]), "fta": o["fta"],
			"necunoscute": o["necunoscute"]},
		"alegeri": {
			"sateliti": [[TOTI if p is None else str(p), t] for p, t in C.alegeri_pozitii(info["servicii"])],
			"canale": [["0", _t(C.T_TOATE)], ["1", _t(C.T_NUMAI_FTA)]],
			"care": [["1", _t(C.T_NECUNOSCUTE)], ["0", _t(C.T_DIN_NOU)]],
		},
		"etichete": {"sateliti": _t(C.T_SATELITI), "canale": _t(C.T_CANALE), "care": _t(C.T_CARE),
			"porneste": _t(C.T_PORNESTE), "continua": _t(C.T_CONTINUA), "de_la_capat": _t(C.T_DE_LA_CAPAT),
			"opreste": _t(C.T_OPRESTE)},
		"plan": {"canale": len(info["rest"]), "secunde": int(info["secunde"]), "text": info["text"],
			"reluare": bool(info["relua"]), "text_reluare": info["text_reluare"], "pas": info["i0"] + 1,
			"total": info["total"]},
		"lista": info["semn"] is not None,
	})
	return rez


def porneste(argumente_, M=None):
	"""POST /api/culegere-canale-porneste: ecranul de progres pe televizor, cu alegerile din cerere."""
	M = _m(M)
	C = M.C
	sesiune = M.sesiune()
	if sesiune is None:
		return {"result": False, "message": _t("Receptorul nu e gata.")}
	o = optiuni(argumente_, C)
	eroare = M.S.porneste_pe_televizor(sesiune, o, argumente_.get("de_la_capat") == "1")
	if eroare:
		return {"result": False, "message": eroare, "rulare": rulare(C)}
	return {"result": True, "message": _t(C.T_PORNITA), "rulare": rulare(C)}


def opreste(M=None):
	"""POST /api/culegere-canale-opreste."""
	M = _m(M)
	C = M.C
	if M.S.opreste_de_oriunde():
		return {"result": True, "message": _t(C.T_OPRIT_WEB), "rulare": rulare(C)}
	return {"result": False, "message": _t(C.T_NIMIC_NU_MERGE), "rulare": rulare(C)}


def rute(baza, resource, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(argumente(request), M))
			except Exception as eroare:
				print("[HdsWebControl] culegere canale: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] culegere canale: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PornesteResource(_Schimba):
		def fa(self, a):
			return porneste(a, M)

	class OpresteResource(_Schimba):
		def fa(self, a):
			return opreste(M)

	class PaginaResource(resource.Resource):
		"""GET /scanare-detaliata si adresa veche /culegere-canale: pagina."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"culegere-canale": StareResource(),
		b"culegere-canale-porneste": PornesteResource(),
		b"culegere-canale-opreste": OpresteResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser neconectat
	primeste pagina de asociere. Pagina porneste si opreste trecerea, deci cu cookie primeste tokenul CSRF."""
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); fara pachet (probele de pe PC) ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_culegere_canale"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scanare detaliată</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(170px,260px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-of-type{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  .plan{color:#f5b83d;font-size:1rem;line-height:1.45;margin:12px 0 0;}
  .nota{color:var(--text-slab);font-size:.88rem;margin:8px 0 0;line-height:1.5;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 0;}
  .butoane button{min-height:44px;padding:10px 18px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .butoane button.principal{background:#23744a;border-color:#23744a;color:#fff;}
  .butoane button.oprire{background:var(--rosu);border-color:var(--rosu);color:#fff;}
  .butoane button:disabled{opacity:.5;cursor:default;}
  .bara{height:10px;background:#0f1216;border:1px solid var(--bordura);border-radius:6px;overflow:hidden;margin:10px 0 6px;}
  .bara div{height:100%;width:0;background:var(--verde);transition:width .4s;}
  .linie{font-size:1rem;line-height:1.45;margin:0;color:#f5b83d;word-break:break-word;}
  .detalii{font-size:.92rem;line-height:1.45;margin:6px 0 0;color:var(--text);white-space:pre-line;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} .butoane button{flex:1 1 100%;} }
</style>
</head>
<body>
<main>
<h1 id="titlu">Scanare detaliată</h1>
<p class="mesaj" id="incarcare">Se citește lista de canale...</p>
<div id="continut" class="ascuns">
  <section class="card ascuns" id="mers">
    <p class="linie" id="linie"></p>
    <div class="bara"><div id="bara"></div></div>
    <p class="detalii" id="detalii"></p>
    <p class="nota" id="indiciu"></p>
    <div class="butoane"><button type="button" class="oprire" id="opreste">Oprește</button></div>
  </section>
  <section class="card" id="alegeri">
    <div class="rand"><label for="sateliti" id="eSateliti">Sateliți</label><select id="sateliti"></select></div>
    <div class="rand"><label for="canale" id="eCanale">Canale</label><select id="canale"></select></div>
    <div class="rand"><label for="care" id="eCare">Care canale</label><select id="care"></select></div>
    <p class="plan" id="plan"></p>
    <p class="nota" id="reluare"></p>
    <div class="butoane">
      <button type="button" class="principal" id="porneste">Pornește</button>
      <button type="button" class="ascuns" id="capat">De la capăt</button>
    </div>
  </section>
  <section class="card ascuns" id="ultima"><p class="detalii" id="ultimaText"></p></section>
  <p class="nota" id="descriere"></p>
  <p class="nota">Același ecran e pe televizor, în __DRUM_MENIU__.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var ultimaCerere = 0, ceas = null, mergea = false;
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
function umple(sel, alegeri, valoare){
  if(document.activeElement === sel){ return; }
  sel.textContent = "";
  (alegeri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
  sel.value = valoare;
}
function alese(){
  var q = new URLSearchParams();
  q.set("pozitie", $("sateliti").value || "toti");
  q.set("fta", $("canale").value || "0");
  q.set("necunoscute", $("care").value || "1");
  return q;
}
function arataRulare(r){
  var merge = !!(r && r.activ);
  $("mers").classList.toggle("ascuns", !merge);
  $("alegeri").classList.toggle("ascuns", merge);
  if(merge){
    $("linie").textContent = r.linie || "";
    $("detalii").textContent = r.detalii || "";
    $("bara").style.width = (r.total ? Math.min(100, Math.round(100 * (r.pas - 1) / r.total)) : 0) + "%";
  }
  $("ultima").classList.toggle("ascuns", merge || !(r && r.text));
  if(r && r.text){ $("ultimaText").textContent = r.text; }
  mergea = merge;
  if(ceas){ clearTimeout(ceas); }
  // numai starea (fara planul, care citeste baza pe firul receptorului): la 3 s cat merge, la 15 s altfel
  ceas = setTimeout(citesteStarea, merge ? 3000 : 15000);
}
function arata(d){
  $("titlu").textContent = d.titlu || $("titlu").textContent;
  document.title = d.titlu || document.title;
  if(d.etichete){
    $("eSateliti").textContent = d.etichete.sateliti; $("eCanale").textContent = d.etichete.canale;
    $("eCare").textContent = d.etichete.care; $("opreste").textContent = d.etichete.opreste;
    $("capat").textContent = d.etichete.de_la_capat;
  }
  if(d.alegeri){
    umple($("sateliti"), d.alegeri.sateliti, d.optiuni.pozitie);
    umple($("canale"), d.alegeri.canale, d.optiuni.fta ? "1" : "0");
    umple($("care"), d.alegeri.care, d.optiuni.necunoscute ? "1" : "0");
  }
  if(d.plan){
    $("plan").textContent = d.plan.text || "";
    $("reluare").textContent = d.plan.text_reluare || "";
    $("porneste").textContent = d.plan.reluare ? d.etichete.continua : d.etichete.porneste;
    $("porneste").disabled = !d.plan.canale;
    $("capat").classList.toggle("ascuns", !d.plan.reluare);
  }
  if(d.descriere){ $("descriere").textContent = d.descriere; }
  $("indiciu").textContent = d.indiciu || "";
  arataRulare(d.rulare);
}
function citeste(cuAlegeri){
  var n = ++ultimaCerere;
  return cerere("/api/culegere-canale" + (cuAlegeri ? "?" + alese().toString() : "")).then(function(d){
    if(n !== ultimaCerere){ return; }
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi lista de canale."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function citesteStarea(){
  return cerere("/api/culegere-canale?doar_stare=1").then(function(d){
    if(!d.result){ return; }
    $("indiciu").textContent = d.indiciu || "";
    // planul se cere din nou numai cand o trecere tocmai s-a terminat (reluarea si numarul canalelor s-au schimbat)
    if(!(d.rulare && d.rulare.activ) && mergea){ citeste(true); } else { arataRulare(d.rulare); }
  }).catch(function(){ ceas = setTimeout(citesteStarea, 5000); });
}
function porneste(deLaCapat){
  var q = alese(); q.set("de_la_capat", deLaCapat ? "1" : "0");
  mesaj("Se pornește pe televizor...");
  cerere("/api/culegere-canale-porneste", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.rulare){ arataRulare(d.rulare); }
    setTimeout(citesteStarea, 1500);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
["sateliti", "canale", "care"].forEach(function(id){ $(id).addEventListener("change", function(){ citeste(true); }); });
$("porneste").addEventListener("click", function(){ porneste(false); });
$("capat").addEventListener("click", function(){ porneste(true); });
$("opreste").addEventListener("click", function(){
  mesaj("Se oprește...");
  cerere("/api/culegere-canale-opreste", "POST", new URLSearchParams()).then(function(d){
    mesaj(d.message, !d.result); setTimeout(function(){ citeste(true); }, 1000);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
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
		N_("Scanare detaliată"),
		N_("Se citește lista de canale..."),
		N_("Oprește"),
		N_("Sateliți"),
		N_("Canale"),
		N_("Care canale"),
		N_("Pornește"),
		N_("De la capăt"),
		N_("Același ecran e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Receptorul nu a putut citi lista de canale."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se pornește pe televizor..."),
		N_("Receptorul nu răspunde."),
		N_("Se oprește..."),
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

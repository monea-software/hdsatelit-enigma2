# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# culori_web.py: "Culori pe roluri" ale skinului HDSatelit in interfata web (HdsWebControl).
#
# Pe televizor: Setari skin > Culori pe roluri > un rol (pluginul skinului, Plugins/Extensions/HdsSkinSetari: ecrane.py,
# ecrane_culoare.py). Aici: aceleasi roluri, aceeasi paleta si aceleasi fisiere (/etc/enigma2/hdsatelit-culori.conf si
# blocul <colors> din skin.xml), din aceeasi logica (paleta.py, grila.py ale pluginului); culoarea se alege cu
# selectorul browserului si transparenta pe aceleasi trepte ca pe televizor; o previzualizare in pagina se schimba pe
# loc. Culorile noi se vad pe televizor dupa repornirea interfetei (butonul din pagina, ca la Salveaza pe televizor).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/culori-skin                                         rolurile, culorile, paleta
#   POST /api/culori-skin-seteaza?rol=<rol>&culoare=%23RRGGBB[&alfa=0..90]   culoarea unui rol, salvata
#   POST /api/culori-skin-paleta?rol=<rol>|toate                  inapoi la culoarea din paleta
#   POST /api/culori-skin-reporneste                              reporneste interfata (TryQuitMainloop 3)
#   GET  /culori-skin                                             pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (un fisier mic de setari si primii 64 KB din skin.xml).
# Fara pluginul skinului (alt skin, pachetul lipsa), pagina spune asta si nu scrie nimic.


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _module(P=None, G=None, T=None):
	if P is None:
		from Plugins.Extensions.HdsSkinSetari import paleta as P
	if G is None:
		from Plugins.Extensions.HdsSkinSetari import grila as G
	if T is None:
		try:
			from Plugins.Extensions.HdsSkinSetari.texte import tr as T
		except ImportError:
			T = None
	return P, G, (T or (lambda cheie: cheie))


def _baza(P, c, palete):
	p = P.paleta_dupa_id(c["paleta"], palete, c["alfa"])
	return p if p is not None else P.implicita(c["alfa"])


def stare(P=None, G=None, T=None, conf=None, skin_xml=None):
	"""GET /api/culori-skin."""
	try:
		P, G, T = _module(P, G, T)
	except ImportError:
		return {"result": False, "message": _t("Pluginul skinului HDSatelit nu e instalat: culorile pe roluri nu se "
			"pot alege.")}
	c = P.citeste_conf(conf)
	palete = P.citeste_palete()
	baza = _baza(P, c, palete)
	pal = P.paleta_din_conf(c, palete)
	roluri = []
	for rol in P.EDITABILE:
		v = pal[rol]
		roluri.append({"rol": rol, "nume": T("role_" + rol), "culoare": P.hexa(v), "rgb": G.hex6(v).lower(),
			"alfa": G.procent_din_alfa((v >> 24) & 255) if G.are_alfa(rol) else 0, "are_alfa": G.are_alfa(rol),
			"modificat": rol in c["roluri"], "paleta": P.hexa(baza[rol])})
	return {"result": True, "paleta": c["paleta"], "roluri": roluri, "alfe": list(G.ALFE),
		"banda": [G.hex6(x).lower() for x in G.banda("", c, pal, pal.get("hdsBrand", 0))],
		"previzualizare": dict((r, G.hex6(pal[r]).lower()) for r in G.ROLURI_BANDA + ("hdsPanel", "hdsSelText", "hdsDisabled") if r in pal)}


def _salveaza(P, c, conf=None, skin_xml=None):
	import os
	P.scrie_conf(c, conf)
	cale = skin_xml or P.SKIN_XML
	if os.path.isfile(cale):
		P.scrie_skin(P.paleta_din_conf(c, P.citeste_palete()), c["paleta"], cale)


def seteaza(argumente, P=None, G=None, T=None, conf=None, skin_xml=None):
	"""POST /api/culori-skin-seteaza."""
	try:
		P, G, T = _module(P, G, T)
	except ImportError:
		return stare(P, G, T, conf, skin_xml)
	rol = argumente.get("rol", "")
	if rol not in P.EDITABILE:
		rez = stare(P, G, T, conf, skin_xml)
		rez.update({"result": False, "message": _t("Rolul acesta nu există.")})
		return rez
	v = P.citeste_culoare(argumente.get("culoare", ""))
	if v is None or len(argumente.get("culoare", "").lstrip("#")) != 6:
		rez = stare(P, G, T, conf, skin_xml)
		rez.update({"result": False, "message": _t("Culoarea se dă ca #RRGGBB.")})
		return rez
	a = 0
	if G.are_alfa(rol):
		try:
			procent = int(argumente.get("alfa", "0") or 0)
		except ValueError:
			procent = -1
		if procent < 0 or procent > 100:
			rez = stare(P, G, T, conf, skin_xml)
			rez.update({"result": False, "message": _t("Transparența e un procent între 0 și 100.")})
			return rez
		a = G.alfa_din_procent(procent)
	c = P.citeste_conf(conf)
	nou = G.compune(v, a)
	c["roluri"].pop(rol, None)
	if nou != _baza(P, c, P.citeste_palete())[rol]:
		c["roluri"][rol] = nou
	_salveaza(P, c, conf, skin_xml)
	rez = stare(P, G, T, conf, skin_xml)
	rez.update({"result": True,
		"message": _t("Salvat. Culoarea nouă se vede pe televizor după repornirea interfeței.")})
	return rez


def din_paleta(argumente, P=None, G=None, T=None, conf=None, skin_xml=None):
	"""POST /api/culori-skin-paleta?rol=<rol>|toate."""
	try:
		P, G, T = _module(P, G, T)
	except ImportError:
		return stare(P, G, T, conf, skin_xml)
	rol = argumente.get("rol", "")
	c = P.citeste_conf(conf)
	if rol == "toate":
		c["roluri"] = {}
	elif rol in P.EDITABILE:
		c["roluri"].pop(rol, None)
	else:
		rez = stare(P, G, T, conf, skin_xml)
		rez.update({"result": False, "message": _t("Rolul acesta nu există.")})
		return rez
	_salveaza(P, c, conf, skin_xml)
	rez = stare(P, G, T, conf, skin_xml)
	rez.update({"result": True, "message": _t("Înapoi la culorile din paletă. Se văd pe televizor după repornirea "
		"interfeței.")})
	return rez


def reporneste(sesiune):
	if sesiune is None:
		return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
	from Screens.Standby import TryQuitMainloop
	sesiune.open(TryQuitMainloop, 3)
	return {"result": True, "message": _t("Interfața se repornește. Pagina se reîncarcă singură în câteva secunde.")}


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ("rol", "culoare", "alfa"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:24].strip()
	return rez


def _sesiune():
	try:
		from . import plugin as W
		return W._sesiune
	except Exception:
		return None


def rute(baza, resource):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare())
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

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return ({b"culori-skin": StareResource(), b"culori-skin-seteaza": _scrie(seteaza),
		b"culori-skin-paleta": _scrie(din_paleta), b"culori-skin-reporneste": _scrie(lambda a: reporneste(_sesiune()))},
		{b"culori-skin": PaginaResource()})


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
		_drumMeniu("hds_skin_setari"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Culori pe roluri</title>
<style>__STIL_COMUN__
  main{max-width:1040px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .sus{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:start;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:0 0 12px;}
  .prev{border-radius:8px;padding:12px;font-size:.95rem;}
  .prev .cap{display:flex;justify-content:space-between;font-weight:700;font-size:1.15rem;}
  .prev .sina{height:8px;border-radius:4px;margin:8px 0;display:flex;overflow:hidden;}
  .prev .ales{padding:6px 10px;border-radius:4px;margin:8px 0;}
  .prev .taste{display:flex;gap:10px;font-size:.8rem;margin-top:8px;}
  .prev .taste span{display:flex;align-items:center;gap:5px;}
  .prev .taste i{display:inline-block;width:5px;height:16px;border-radius:2px;}
  .rand{display:grid;grid-template-columns:minmax(0,1fr) 52px 84px auto;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand .nume{font-size:.92rem;}
  .rand .nume small{display:block;color:var(--text-slab);font-size:.75rem;}
  .rand input[type=color]{width:52px;height:40px;border:1px solid var(--bordura);border-radius:6px;background:none;padding:2px;}
  .rand select{min-height:40px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;padding:4px 6px;}
  .rand button,.butoane button{min-height:40px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .rand button[disabled]{opacity:.45;cursor:default;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;}
  .butoane button.principal{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:700px){ .sus{grid-template-columns:1fr;} .rand{grid-template-columns:minmax(0,1fr) 52px 84px;} .rand button{grid-column:1 / span 3;justify-self:start;} }
</style>
</head>
<body>
<main>
<h1>Culori pe roluri</h1>
<p class="mesaj" id="incarcare">Se citesc culorile...</p>
<div id="continut" class="ascuns">
  <div class="sus">
    <section class="card">
      <div class="prev" id="prev">
        <div class="cap"><span id="pv_canal">101  Canal</span><span id="pv_ora">20:15</span></div>
        <div id="pv_acum">Știrile de seară</div>
        <div class="sina" id="pv_sina"><span id="pv_bun" style="width:55%"></span><span id="pv_slab" style="width:20%"></span><span id="pv_rau" style="width:10%"></span></div>
        <div class="ales" id="pv_ales">Rând selectat</div>
        <div id="pv_eticheta">Etichetă · <b id="pv_evid">Evidențiere</b></div>
        <div class="taste"><span><i id="k0"></i>OK</span><span><i id="k1"></i>OK</span><span><i id="k2"></i>OK</span><span><i id="k3"></i>OK</span></div>
      </div>
    </section>
    <section class="card">
      <div class="butoane">
        <button type="button" class="principal" id="reporneste">Repornește interfața</button>
        <button type="button" id="implicite">Înapoi la implicite</button>
      </div>
      <p class="nota">Fiecare culoare se salvează când o alegi. Pe televizor culorile noi apar după repornirea interfeței; receptorul nu se oprește și antena nu se mișcă.</p>
      <p class="mesaj" id="mesaj"></p>
    </section>
  </div>
  <section class="card" id="roluri"></section>
  <p class="nota">Aceleași culori sunt pe televizor, în __DRUM_MENIU__ › Culori pe roluri, unde le alegi pe o grilă. Paleta, opacitatea panourilor și pagina tehnică se aleg tot acolo.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var STARE = null;
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
function c(rol){ var i = $("c_" + rol); return i ? i.value : ((STARE.previzualizare || {})[rol] || "#888888"); }
function previzualizare(){
  var p = $("prev");
  p.style.background = c("hdsPanelSolid"); p.style.color = c("hdsText");
  $("pv_ora").style.color = c("hdsAmber"); $("pv_acum").style.color = c("hdsText2");
  $("pv_sina").style.background = c("hdsTrack"); $("pv_bun").style.background = c("hdsGood");
  $("pv_slab").style.background = c("hdsWarn"); $("pv_rau").style.background = c("hdsBad");
  $("pv_ales").style.background = c("hdsBrand"); $("pv_ales").style.color = c("hdsSelText");
  $("pv_ales").style.boxShadow = "inset 5px 0 0 " + c("hdsBrandLight");
  $("pv_eticheta").style.color = c("hdsLabel"); $("pv_evid").style.color = c("hdsBrandLight");
  ["key_red", "key_green", "key_yellow", "key_blue"].forEach(function(r, i){ $("k" + i).style.background = c(r); });
}
function trimite(cale, q){
  mesaj("Se salvează...");
  return cerere(cale, "POST", q).then(function(d){ if(d.roluri){ arata(d); } mesaj(d.message, !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function arata(d){
  STARE = d;
  var s = $("roluri"); s.textContent = "";
  d.roluri.forEach(function(r){
    var rd = document.createElement("div"); rd.className = "rand";
    var n = document.createElement("label"); n.className = "nume"; n.htmlFor = "c_" + r.rol; n.textContent = r.nume;
    var sm = document.createElement("small"); sm.textContent = r.culoare + (r.modificat ? " · aleasă de tine" : " · din paletă"); n.appendChild(sm);
    var i = document.createElement("input"); i.type = "color"; i.id = "c_" + r.rol; i.value = r.rgb;
    var a = document.createElement("select"); a.id = "a_" + r.rol; a.setAttribute("aria-label", r.nume + ": transparență"); a.title = "transparență";
    if(r.are_alfa){
      var trepte = d.alfe.slice(); if(trepte.indexOf(r.alfa) < 0){ trepte.push(r.alfa); trepte.sort(function(x, y){ return x - y; }); }
      trepte.forEach(function(p){ var o = document.createElement("option"); o.value = p; o.textContent = p + "%"; a.appendChild(o); }); a.value = String(r.alfa);
    }
    else { a.style.visibility = "hidden"; }
    var b = document.createElement("button"); b.type = "button"; b.textContent = "Din paletă"; b.disabled = !r.modificat;
    function salveaza(){ var q = new URLSearchParams(); q.set("rol", r.rol); q.set("culoare", i.value); if(r.are_alfa){ q.set("alfa", a.value); } trimite("/api/culori-skin-seteaza", q); }
    i.addEventListener("input", previzualizare);
    i.addEventListener("change", salveaza);
    a.addEventListener("change", salveaza);
    b.addEventListener("click", function(){ var q = new URLSearchParams(); q.set("rol", r.rol); trimite("/api/culori-skin-paleta", q); });
    rd.appendChild(n); rd.appendChild(i); rd.appendChild(a); rd.appendChild(b); s.appendChild(rd);
  });
  previzualizare();
}
function citeste(){
  return cerere("/api/culori-skin").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi culorile."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("implicite").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("rol", "toate"); trimite("/api/culori-skin-paleta", q); });
$("reporneste").addEventListener("click", function(){
  cerere("/api/culori-skin-reporneste", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); if(d.result){ setTimeout(function(){ location.reload(); }, 15000); } })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
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
		N_("Culori pe roluri"),
		N_("Se citesc culorile..."),
		N_("101 Canal"),
		N_("Știrile de seară"),
		N_("Rând selectat"),
		N_("Etichetă · <b id=\"pv_evid\">Evidențiere</b>"),
		N_("Repornește interfața"),
		N_("Înapoi la implicite"),
		N_("Fiecare culoare se salvează când o alegi. Pe televizor culorile noi apar după repornirea "
			"interfeței; receptorul nu se oprește și antena nu se mișcă."),
		N_("Aceleași culori sunt pe televizor, în __DRUM_MENIU__ › Culori pe roluri, unde le alegi pe o "
			"grilă. Paleta, opacitatea panourilor și pagina tehnică se aleg tot acolo."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se salvează..."),
		N_("Receptorul nu răspunde."),
		N_("· aleasă de tine"),
		N_("· din paletă"),
		N_(": transparență"),
		N_("transparență"),
		N_("Din paletă"),
		N_("Receptorul nu a putut citi culorile."),
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

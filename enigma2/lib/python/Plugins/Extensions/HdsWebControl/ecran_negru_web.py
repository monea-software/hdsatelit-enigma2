# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ecran_negru_web.py: de ce e negru ecranul canalului, in interfata web (HdsWebControl), perechea mesajului de pe
# mijlocul ecranului (Screens/HdsEcranNegru.py). Acelasi verdict si aceleasi texte, luate din
# Components/HdsEcranNegru.py (ultima_stare, fapta_web), deci nicio a doua logica.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/ecran-negru                          {result, activ, vizibil, pornit, cod, canal, titlu, text,
#                                                   etichete, semnal, calitate, detaliu, fapta: {id, text} | null}
#   POST /api/ecran-negru-fapta?fapta=<id>|ascunde  fapta mesajului de acum, pe televizor (cautarea din nou,
#                                                   ecranul de cautare, inregistrarile, codul pentru parinti, setarile
#                                                   tunerului), sau ascunderea mesajului (ca EXIT); „analiza” porneste
#                                                   analiza fluxului fara sa deschida ecranul ei pe televizor
#   GET  /api/ecran-negru-flux                     analiza fluxului serviciului din mesaj (Components/HdsAnalizaFlux):
#                                                   {result, stare: nimic|citeste|gata|eroare|oprita, stare_text,
#                                                   canal, sectiuni: [{titlu, randuri}]}, aceleasi texte ca ecranul ei
# Panoul principal („Acum pe receptor”): in_panou(pagina) pune caseta sub randul „Standby”, stilul ei si citirea la
# 3 secunde (la 1 secunda cat merge analiza); fara ancorele panoului pagina ramane neschimbata. Sectiunile analizei
# fluxului stau intr-un card separat, pe toata latimea, la capatul grilei panoului (caseta ramane mica, iar telecomanda
# ramane unde e); in caseta, un singur rand de stare. Tot aici se leaga randul „Acces” (acces_web.in_panou).
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; o cerere face o singura fotografie a starii (cateva citiri
# din serviciul redat si din placa, fara disc si fara retea); analiza fluxului ruleaza pe firul ei, aici se citeste
# numai starea tinuta in memorie. Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulele lor
# (E, A).

import re

MAX_TEXT = 600
MAX_RAND = 400
_CONTROL = re.compile(u"[\u0000-\u0008\u000b-\u001f\u007f-\u009f\ud800-\udfff]")
FAPTE_WEB = ("cauta_tp", "cauta", "inregistrari", "cod", "tuner", "analiza", "loc", "ascunde")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _e(E=None):
	if E is not None:
		return E
	from Components import HdsEcranNegru
	return HdsEcranNegru


def curat(text, n=MAX_TEXT):
	"""Text pentru JSON: fara caractere de control (randurile noi raman), taiat; pagina il pune numai ca text."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return ""
	return _CONTROL.sub(u" ", t)[:n].strip()


def _procent(v):
	try:
		v = int(v)
	except (TypeError, ValueError):
		return None
	return max(0, min(100, v)) if v >= 0 else None


def stare(E=None):
	"""GET /api/ecran-negru -> (cod, corp)."""
	E = _e(E)
	s = E.ultima_stare()
	v = s.get("verdict")
	corp = {"result": True, "activ": bool(v), "vizibil": bool(s.get("vizibil")), "pornit": bool(s.get("pornit")),
		"urmarit": bool(s.get("urmarit"))}
	if not v:
		return 200, corp
	f = v.get("fapta")
	corp.update({
		"cod": curat(v.get("cod"), 32),
		"canal": curat(v.get("canal"), 128),
		"titlu": curat(v.get("titlu"), 200),
		"text": curat(v.get("text")),
		"etichete": [curat(x, 40) for x in (v.get("etichete") or [])][:8],
		"semnal": _procent(v.get("semnal")),
		"calitate": _procent(v.get("calitate")),
		"detaliu": curat(v.get("detaliu")),
		"fapta": {"id": curat(f.get("id"), 32), "text": curat(f.get("text"), 120)} if f else None,
	})
	return 200, corp


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAnalizaFlux
	return HdsAnalizaFlux


def flux(E=None, A=None):
	"""GET /api/ecran-negru-flux -> (cod, corp): analiza fluxului pentru serviciul mesajului de acum."""
	E = _e(E)
	A = _a(A)
	v = E.ultima_stare().get("verdict") or {}
	ref = v.get("ref")
	if not ref:
		return 200, {"result": True, "stare": "nimic", "stare_text": u"", "canal": u"", "sectiuni": []}
	s = A.stare(ref)
	corp = {"result": True, "stare": curat(s.get("stare"), 16), "stare_text": u"", "canal": curat(v.get("canal"), 128),
		"sectiuni": []}
	if s.get("stare") == "citeste":
		facute, stiute = s.get("progres") or (0, 0)
		corp["stare_text"] = curat(_t(A.T_CITESTE) % (facute, stiute), 120)
	elif s.get("stare") == "nimic":
		corp["stare_text"] = curat(_t(A.T_NICIO_ANALIZA), 200)
	else:
		for sect in A.sectiuni_text(s.get("rezultat"))[:12]:
			corp["sectiuni"].append({"titlu": curat(sect.get("titlu"), 80),
				"randuri": [curat(r, MAX_RAND) for r in (sect.get("randuri") or [])][:60]})
	return 200, corp


def fapta(argumente_, E=None):
	"""POST /api/ecran-negru-fapta -> (cod, corp). Fapta se face pe televizor numai daca e a mesajului de acum."""
	E = _e(E)
	f = argumente_.get("fapta") or ""
	if f not in FAPTE_WEB:
		return 400, {"result": False, "message": _t("Fapta nu e cunoscută."), "camp": "fapta"}
	cod, mesaj = E.fapta_web(f)
	return cod, {"result": cod == 200, "message": mesaj}


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie != "fapta":
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:32].strip()
	return rez


def rute(baza, resource=None, E=None, A=None):
	"""Resursele de sub /api: {nume: resursa}. `baza` e HdsJsonResource din plugin.py."""

	class FluxResource(baza):
		def render_GET(self, request):
			try:
				cod, corp = flux(E=E, A=A)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] analiza fluxului: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class StareResource(baza):
		def render_GET(self, request):
			try:
				cod, corp = stare(E=E)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] ecran negru: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

	class FaptaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				cod, corp = fapta(argumente(request), E=E)
				return self._raspunde(request, corp, cod)
			except Exception as eroare:
				print("[HdsWebControl] ecran negru fapta: %s" % eroare)
				return self._eroare(request, _t("Eroare pe receptor."), 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	return {b"ecran-negru": StareResource(), b"ecran-negru-fapta": FaptaResource(), b"ecran-negru-flux": FluxResource()}


# ---------------------------------------------------------------- caseta din panoul principal

# sfarsitul randului "Standby" al panoului, fara textul lui (panoul se traduce in limba receptorului)
ANCORA_HTML = u'<span id="stStandby">-</span></div>'
ANCORA_CSS = u"</style>"
ANCORA_JS = u"</script>"

PANOU_HTML = u"""
      <div class="ecran-negru ascuns" id="ecranNegru" role="status" aria-live="polite">
        <div class="en-canal" id="enCanal"></div>
        <div class="en-titlu" id="enTitlu"></div>
        <div class="en-text" id="enText"></div>
        <div class="en-etichete" id="enEtichete"></div>
        <div class="en-bara ascuns" id="enBaraSemnal"><span>Semnal</span><span class="en-cursa"><span id="enSemnal"></span></span><span id="enSemnalVal"></span></div>
        <div class="en-bara ascuns" id="enBaraCalitate"><span>Calitate</span><span class="en-cursa"><span class="bun" id="enCalitate"></span></span><span id="enCalitateVal"></span></div>
        <div class="en-detaliu" id="enDetaliu"></div>
        <div class="en-butoane"><button type="button" class="en-fapta ascuns" id="enFapta"></button><button type="button" id="enAscunde">Ascunde mesajul pe televizor</button></div>
        <div class="en-mesaj" id="enMesaj"></div>
        <div class="en-flux ascuns" id="enFlux"><div class="en-flux-stare" id="enFluxStare"></div></div>
      </div>"""

PANOU_CSS = u"""  .ecran-negru{margin-top:12px;padding:12px 14px;border-left:4px solid #f5b83d;background:#10162a;border-radius:8px;}
  .ecran-negru.ascuns,.ecran-negru .ascuns{display:none;}
  .en-canal{color:var(--text-slab);font-size:.9rem;}
  .en-titlu{font-weight:bold;font-size:1.05rem;margin:2px 0 6px;}
  .en-text{line-height:1.45;white-space:pre-line;word-break:break-word;}
  .en-etichete{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0;}
  .en-etichete span{border:2px solid #f5b83d;border-radius:4px;padding:2px 8px;font-size:.9rem;font-weight:bold;}
  .en-bara{display:grid;grid-template-columns:5.5em 1fr 3.5em;gap:8px;align-items:center;margin-top:8px;font-size:.9rem;}
  .en-cursa{display:block;height:8px;background:#2a3350;border-radius:4px;overflow:hidden;}
  .en-cursa span{display:block;height:100%;width:0;background:#9fb4ff;}
  .en-cursa span.bun{background:#4fd18b;}
  .en-detaliu{color:var(--text-slab);font-size:.9rem;margin-top:8px;word-break:break-word;}
  .en-butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}
  .en-butoane button{min-height:40px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .en-butoane button.en-fapta{background:#374ea1;border-color:#374ea1;color:#fff;}
  .en-butoane button:disabled{opacity:.55;cursor:default;}
  .en-mesaj{font-size:.9rem;margin-top:6px;min-height:1em;color:var(--text-slab);}
  .en-flux{margin-top:10px;border-top:1px solid var(--bordura);padding-top:8px;}
  .en-flux.ascuns,.en-flux-card.ascuns{display:none;}
  .en-flux-stare{font-size:.9rem;color:#f5b83d;}
  .en-flux-card{grid-column:1/-1;}
  .en-flux-canal{color:var(--text-slab);font-size:.9rem;margin:-6px 0 6px;}
  .en-flux-card h3{margin:14px 0 4px;font-size:.95rem;letter-spacing:.04em;text-transform:uppercase;color:#9fb4ff;}
  .en-flux-card ul{margin:0;padding-left:1.1em;}
  .en-flux-card li{font-size:.95rem;line-height:1.45;word-break:break-word;margin:2px 0;}
  @media(max-width:600px){.ecran-negru,.en-flux-card{font-size:15px;}
    .en-canal,.en-detaliu,.en-mesaj,.en-flux-stare,.en-flux-canal,.en-etichete span,.en-bara,.en-flux-card li{font-size:15px;}}
"""

PANOU_JS = u"""var enUltimaCheie = null;
function ecranNegruDeseneaza(d){
  var c = document.getElementById("ecranNegru");
  // raspunsul ultimei fapte ramane numai cat ramane acelasi mesaj pe acelasi canal
  var cheie = (d && d.result && d.activ) ? (d.cod || "") + "|" + (d.canal || "") : "";
  if(cheie !== enUltimaCheie){ document.getElementById("enMesaj").textContent = ""; enUltimaCheie = cheie; }
  if(!d || !d.result || !d.activ){ c.classList.add("ascuns"); return; }
  c.classList.remove("ascuns");
  document.getElementById("enCanal").textContent = d.canal || "";
  document.getElementById("enTitlu").textContent = d.titlu || "";
  document.getElementById("enText").textContent = d.text || "";
  document.getElementById("enDetaliu").textContent = d.detaliu || "";
  var et = document.getElementById("enEtichete"); et.textContent = "";
  (d.etichete || []).forEach(function(x){ var s = document.createElement("span"); s.textContent = x; et.appendChild(s); });
  [["Semnal", d.semnal], ["Calitate", d.calitate]].forEach(function(p){
    var rand = document.getElementById("enBara" + p[0]);
    rand.classList.toggle("ascuns", p[1] === null || p[1] === undefined);
    document.getElementById("en" + p[0]).style.width = (p[1] || 0) + "%";
    document.getElementById("en" + p[0] + "Val").textContent = (p[1] === null || p[1] === undefined) ? "" : p[1] + " %";
  });
  var b = document.getElementById("enFapta");
  b.classList.toggle("ascuns", !d.fapta);
  if(d.fapta){ b.textContent = d.fapta.text; b.dataset.fapta = d.fapta.id; }
  document.getElementById("enAscunde").classList.toggle("ascuns", !d.vizibil);
  // analiza fluxului se arata numai la mesajele care o au (serviciu de date, format necunoscut)
  if(d.fapta && d.fapta.id === "analiza"){ ecranNegruFlux(); }
  else { document.getElementById("enFlux").classList.add("ascuns"); enFluxCard().classList.add("ascuns"); enFluxUltim = null; b.disabled = false; }
}
function enFluxCard(){
  // cardul rezultatului, pe toata latimea, la capatul grilei panoului (facut o singura data)
  var c = document.getElementById("enFluxCard");
  if(c){ return c; }
  c = document.createElement("div"); c.className = "card en-flux-card ascuns"; c.id = "enFluxCard";
  var h = document.createElement("h2"); h.textContent = "Analiza fluxului"; c.appendChild(h);
  var k = document.createElement("div"); k.className = "en-flux-canal"; k.id = "enFluxCanal"; c.appendChild(k);
  var s = document.createElement("div"); s.id = "enFluxSectiuni"; c.appendChild(s);
  (document.querySelector(".grid") || document.body).appendChild(c);
  return c;
}
var enFluxCeas = null, enFluxUltim = null, enFluxPornit = false;
function ecranNegruFlux(){
  cerere("/api/ecran-negru-flux").then(function(d){
    var c = document.getElementById("enFlux"), card = enFluxCard(), b = document.getElementById("enFapta");
    clearTimeout(enFluxCeas);
    if(!d || !d.result || d.stare === "nimic"){ c.classList.add("ascuns"); card.classList.add("ascuns"); enFluxUltim = null; b.disabled = false; return; }
    var citeste = d.stare === "citeste";
    // cat merge analiza: un singur rand de stare (progresul), iar butonul nu o porneste a doua oara
    b.disabled = citeste;
    if(citeste){ enFluxCeas = setTimeout(ecranNegruFlux, 1000); document.getElementById("enMesaj").textContent = ""; }
    else if(enFluxPornit){ enFluxPornit = false; document.getElementById("enMesaj").textContent = ""; }
    var cheie = JSON.stringify(d);
    if(cheie === enFluxUltim){ return; }
    enFluxUltim = cheie;
    var sectiuni = d.sectiuni || [];
    c.classList.toggle("ascuns", !citeste && !sectiuni.length);
    document.getElementById("enFluxStare").textContent = citeste ? (d.stare_text || "") : (sectiuni.length ? "Rezultatul analizei este mai jos, în cardul „Analiza fluxului”." : "");
    card.classList.toggle("ascuns", !sectiuni.length);
    document.getElementById("enFluxCanal").textContent = d.canal || "";
    var s = document.getElementById("enFluxSectiuni"); s.textContent = "";
    sectiuni.forEach(function(x){
      var h = document.createElement("h3"); h.textContent = x.titlu || ""; s.appendChild(h);
      var ul = document.createElement("ul");
      (x.randuri || []).forEach(function(r){ var li = document.createElement("li"); li.textContent = r; ul.appendChild(li); });
      s.appendChild(ul);
    });
  }).catch(function(){});
}
function ecranNegruFapta(f){
  // ca cerere() din panou, dar si raspunsurile 409 au un mesaj de aratat
  var m = document.getElementById("enMesaj");
  var optiuni = {method: "POST", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  m.textContent = "Se trimite...";
  fetch(adresa("/api/ecran-negru-fapta?fapta=" + encodeURIComponent(f)), optiuni).then(function(r){
    return r.json().catch(function(){ return {message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  }).then(function(d){
    m.textContent = d.message || "";
    actualizeazaEcranNegru(true);
    if(f === "analiza"){ enFluxPornit = true; ecranNegruFlux(); }
  }).catch(function(){ m.textContent = "Receptorul nu a primit cererea."; });
}
function actualizeazaEcranNegru(oData){
  cerere("/api/ecran-negru").then(ecranNegruDeseneaza).catch(function(){}).then(function(){
    if(!oData){ setTimeout(actualizeazaEcranNegru, 3000); }
  });
}
document.getElementById("enFapta").addEventListener("click", function(){
  // rezultatul analizei e deja in pagina: butonul duce la el, fara o cerere noua
  var card = document.getElementById("enFluxCard");
  if(this.dataset.fapta === "analiza" && card && !card.classList.contains("ascuns")){ card.scrollIntoView({behavior: "smooth"}); return; }
  ecranNegruFapta(this.dataset.fapta || "");
});
document.getElementById("enAscunde").addEventListener("click", function(){ ecranNegruFapta("ascunde"); });
actualizeazaEcranNegru();
"""


def in_panou(pagina):
	"""Panoul principal cu caseta ecranului negru: HTML-ul sub randul „Standby”, stilul inainte de primul </style>,
	scriptul inainte de ultimul </script>. Fara oricare ancora (alta pagina, panou schimbat) pagina ramane cum e."""
	try:
		if ANCORA_HTML not in pagina or ANCORA_CSS not in pagina or ANCORA_JS not in pagina or "ecranNegru" in pagina:
			return pagina
		pagina = pagina.replace(ANCORA_HTML, ANCORA_HTML + _traducePagina(PANOU_HTML), 1)
		pagina = pagina.replace(ANCORA_CSS, PANOU_CSS + ANCORA_CSS, 1)
		i = pagina.rindex(ANCORA_JS)
		pagina = pagina[:i] + _traducePagina(PANOU_JS, "js") + pagina[i:]
	except Exception as eroare:
		print("[HdsWebControl] caseta ecranului negru: %s" % eroare)
		return pagina
	return _cu_acces(pagina)


def _cu_acces(pagina):
	"""Randul „Acces” (sistemul prin care se decripteaza acum) din acces_web.py, sub randul „Canal”."""
	try:
		from . import acces_web
	except Exception:
		try:
			import acces_web
		except Exception:
			return pagina
	return acces_web.in_panou(pagina)


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Semnal"),
		N_("Calitate"),
		N_("Ascunde mesajul pe televizor"),
	),
	"js": (
		N_("Semnal"),
		N_("Calitate"),
		N_("Val"),
		N_("Analiza fluxului"),
		N_("Rezultatul analizei este mai jos, în cardul „Analiza fluxului”."),
		N_("Se trimite..."),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Receptorul nu a primit cererea."),
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

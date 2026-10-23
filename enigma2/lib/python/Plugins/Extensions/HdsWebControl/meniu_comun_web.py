# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# meniu_comun_web.py: ajutoarele comune ale paginilor web facute pentru intrarile de meniu care se deschideau numai pe
# televizor (lista in meniu_pagini_web.MODULE). Nu e o pagina.
#
# - pagina(request, sablon): poarta paginilor (reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un
#   browser neconectat primeste pagina de asociere), ca paznic_web.pagina; `sablon(stil, config)` da textul paginii.
# - numaiBrowser(request): refuzul pentru actiunile periculoase cerute cu ?token= (o cheie in adresa nu e un om in fata
#   unei pagini); actiunile periculoase merg numai din browserul conectat, cu POST si antetul CSRF (poarta comuna).
# - Confirmarile (cere / verifica): o actiune periculoasa (oprire, repornire, resetare, formatare, stergere) se face in
#   doi pasi. Pasul 1 (POST ...?pas=intreaba) intoarce intrebarea si un cod de unica folosinta, valabil DURATA_COD_S
#   secunde, legat de actiune si de tinta ei; pasul 2 (POST ...?cod=<cod>) face actiunea numai cu acel cod. Un cod
#   folosit, expirat sau al altei actiuni nu face nimic. Pagina arata intrebarea si butoanele "Da, ..." / "Renunță".
# - argumente(request, chei, lung): argumentele cererii ca text scurt, numai cheile stiute, fara token.
# - drumHtml(entryID): drumul de pe televizor spre ecran (meniu_web.drumHtml), pentru nota "Aceleași setări sunt pe
#   televizor, în ...".
# - sesiune(), ocupat(sesiune): sesiunea enigma2 tinuta de plugin.py si refuzul cand televizorul e ocupat
#   (scanare_web._ocupat).
# - salveazaSetari(): configfile.save(), ca la inchiderea unui meniu cu flushConfigOnClose.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il incarca fara receptor.

import os
import time

DURATA_COD_S = 120
MAX_CODURI = 32

_CODURI = {}


def _t(text):
	"""Traducerea enigma2; un text gol ramane gol (gettext ar da antetul fisierului .po)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def jurnal(text):
	print("[HdsWebControl] %s" % text)


def _acum():
	return time.monotonic()


def _curata(acum):
	for cheie in [k for k, v in _CODURI.items() if v[1] < acum]:
		_CODURI.pop(cheie, None)
	while len(_CODURI) >= MAX_CODURI:
		cea_mai_veche = min(_CODURI.items(), key=lambda kv: kv[1][1])[0]
		_CODURI.pop(cea_mai_veche, None)


def cere(actiune, tinta=""):
	"""Pasul 1: un cod nou pentru (actiune, tinta); unul cerut inainte pentru aceeasi pereche nu mai e bun."""
	import binascii
	acum = _acum()
	_curata(acum)
	cod = binascii.hexlify(os.urandom(6)).decode("ascii")
	_CODURI[(actiune, tinta or "")] = (cod, acum + DURATA_COD_S)
	return cod


def verifica(actiune, tinta, cod):
	"""Pasul 2: True numai pentru codul cerut pentru aceeasi (actiune, tinta), inca valabil; codul se foloseste o data."""
	import hmac
	acum = _acum()
	_curata(acum)
	if not cod:
		return False
	x = _CODURI.get((actiune, tinta or ""))
	if x is None:
		return False
	if not hmac.compare_digest(x[0].encode("ascii"), str(cod).encode("ascii", "replace")):
		return False
	_CODURI.pop((actiune, tinta or ""), None)
	return x[1] >= acum


def uita(actiune, tinta=""):
	""""Renunță": codul cerut nu mai e bun."""
	_CODURI.pop((actiune, tinta or ""), None)


def raspunsIntrebare(actiune, tinta, intrebare, buton, detalii=None):
	"""Corpul raspunsului la pasul 1: {"result": True, "confirmare": {...}} cu codul nou."""
	return {"result": True, "confirmare": {"actiune": actiune, "tinta": tinta or "", "intrebare": intrebare,
		"buton": buton, "cod": cere(actiune, tinta), "valabil_s": DURATA_COD_S, "detalii": detalii or []}}


def codGresit():
	return {"result": False, "message": _t("Confirmarea a expirat sau nu e pentru această acțiune. Încearcă din nou.")}


def argumente(request, chei, lung=200):
	"""{cheie: text} pentru cheile din `chei` (fara token), cel mult `lung` caractere fiecare."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:24]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in chei:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:lung].strip()
	return rez


def numaiBrowser(request):
	"""Textul refuzului cand o actiune periculoasa vine cu ?token=, altfel None."""
	try:
		from . import plugin as P
		jeton = P.PARAM_JETON
	except Exception:
		jeton = b"token"
	if jeton in (getattr(request, "args", None) or {}):
		return _t("Această acțiune se face numai din browserul conectat, nu cu cheia din adresă.")
	return None


def drumHtml(id_intrare):
	"""Drumul de pe televizor spre ecran; fara meniu (probele de pe PC care incarca modulul singur) ramane "Meniu"."""
	try:
		from .meniu_web import drumHtml as d
	except ImportError:
		return "Meniu"
	try:
		return d(id_intrare)
	except Exception:
		return "Meniu"


def sesiune():
	try:
		from .scanare_web import _sesiune
	except ImportError:
		return None
	return _sesiune()


def ocupat(s):
	try:
		from .scanare_web import _ocupat
	except ImportError:
		return None
	return _ocupat(s)


def salveazaSetari(config_fisier=None):
	"""configfile.save(), ca la inchiderea unui meniu cu flushConfigOnClose."""
	try:
		if config_fisier is None:
			from Components.config import configfile as config_fisier
		config_fisier.save()
		return True
	except Exception as eroare:
		jurnal("salvarea setarilor: %s" % eroare)
		return False


def peFir(request, lucru, steag, timeout_s, fabrica_ceas=None):
	"""`lucru` pe un fir separat, raspunsul pe firul enigma2 (ecran_pornire_web.porneste_pe_fir); intoarce
	NOT_DONE_YET. `steag` = [bool], o singura lucrare de felul ei odata."""
	from .ecran_pornire_web import porneste_pe_fir
	return porneste_pe_fir(request, lucru, steag, timeout_s, fabrica_ceas)


def pagina(request, sablon, cu_csrf=True):
	"""Poarta paginilor, ca paznic_web.pagina. `sablon(stil, config_pagina)` -> textul paginii. `cu_csrf`=False la
	paginile numai de citire (fara tokenul CSRF in pagina)."""
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
		config_pagina = P._configPanou(P.csrfPentru(secret) if cu_csrf else "", "", browser.get("nume", ""))
	return sablon(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


# Scriptul comun al paginilor (cererile, mesajul, confirmarea in doi pasi), lipit in fiecare pagina in locul lui
# __SCRIPT_COMUN__. Pagina are un element #mesaj si, pentru confirmari, un <div id="confirmare" class="card ascuns">.
SCRIPT_COMUN = r"""
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
function mesaj(text, eroare){ var m = $("mesaj"); if(!m){ return; } m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function nimicNuRaspunde(){ mesaj("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); }
// confirmarea in doi pasi: cale = ruta actiunii; date = URLSearchParams; dupa = functia chemata cu raspunsul final
function cuConfirmare(cale, date, dupa){
  var q = new URLSearchParams(date ? date.toString() : ""); q.set("pas", "intreaba");
  mesaj("");
  cerere(cale, "POST", q).then(function(d){
    if(!d.result || !d.confirmare){ mesaj(d.message, !d.result); if(dupa){ dupa(d); } return; }
    arataConfirmarea(cale, date, d.confirmare, dupa);
  }).catch(nimicNuRaspunde);
}
function arataConfirmarea(cale, date, c, dupa){
  var cutie = $("confirmare"); if(!cutie){ return; }
  cutie.textContent = "";
  var h = document.createElement("h2"); h.textContent = "Confirmare"; cutie.appendChild(h);
  var p = document.createElement("p"); p.className = "intrebare"; p.textContent = c.intrebare; cutie.appendChild(p);
  (c.detalii || []).forEach(function(x){ var n = document.createElement("p"); n.className = "nota"; n.textContent = x; cutie.appendChild(n); });
  var b = document.createElement("div"); b.className = "butoane";
  var da = document.createElement("button"); da.type = "button"; da.className = "rosu"; da.textContent = c.buton;
  var nu = document.createElement("button"); nu.type = "button"; nu.textContent = "Renunță";
  da.addEventListener("click", function(){
    var q = new URLSearchParams(date ? date.toString() : ""); q.set("cod", c.cod);
    cutie.classList.add("ascuns"); mesaj("Se trimite...");
    cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); if(dupa){ dupa(d); } }).catch(nimicNuRaspunde);
  });
  nu.addEventListener("click", function(){
    var q = new URLSearchParams(date ? date.toString() : ""); q.set("pas", "renunta");
    cutie.classList.add("ascuns"); mesaj("Nu s-a făcut nimic.");
    cerere(cale, "POST", q).catch(function(){});
  });
  b.appendChild(da); b.appendChild(nu); cutie.appendChild(b);
  cutie.classList.remove("ascuns");
  cutie.scrollIntoView({block: "center"});
  nu.focus();
}
"""

# Stilul comun al paginilor (geometria; culorile si aspectul le pun temele din cadru_web.py), lipit in locul lui
# __STIL_PAGINI__ dupa __STIL_COMUN__. Tintele de atins au cel putin 44 px.
STIL_PAGINI = """
  main{max-width:880px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card h2{font-size:1rem;margin:0 0 10px;}
  .rand{display:grid;grid-template-columns:1fr minmax(160px,260px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand .ajutor{grid-column:1 / -1;font-size:.8rem;line-height:1.4;margin:0;}
  select,input,textarea{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;max-width:100%;}
  input[type=checkbox],input[type=radio]{min-height:0;width:22px;height:22px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button:disabled{opacity:.5;cursor:default;}
  button.principal{background:var(--accent);border-color:var(--accent);color:#fff;}
  button.rosu{background:var(--rosu);border-color:var(--rosu);color:#fff;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0;}
  .status-linie{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--bordura);font-size:.92rem;}
  .status-linie:last-child{border-bottom:0;}
  .status-linie>span:last-child{text-align:right;overflow-wrap:anywhere;}
  table{width:100%;border-collapse:collapse;font-size:.9rem;}
  th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--bordura);vertical-align:top;overflow-wrap:anywhere;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .intrebare{font-size:1rem;line-height:1.45;margin:0 0 6px;}
  .ascuns{display:none;}
  pre.text{font-family:monospace;font-size:.78rem;line-height:1.4;white-space:pre-wrap;word-break:break-word;margin:0;max-height:60vh;overflow:auto;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
"""


def sablon(text, stil, config_pagina, inlocuiri=None):
	"""Textul unei pagini: __STIL_COMUN__, __STIL_PAGINI__, __SCRIPT_COMUN__ (cu __CONFIG__ in el) si inlocuirile
	paginii ({"__DRUM_MENIU__": ...})."""
	rez = text.replace("__STIL_COMUN__", stil).replace("__STIL_PAGINI__", STIL_PAGINI)
	rez = rez.replace("__SCRIPT_COMUN__", _traducePagina(SCRIPT_COMUN, "js").replace("__CONFIG__", config_pagina))
	for cheie, valoare in (inlocuiri or {}).items():
		rez = rez.replace(cheie, valoare)
	return rez


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Confirmare"),
		N_("Renunță"),
		N_("Se trimite..."),
		N_("Nu s-a făcut nimic."),
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

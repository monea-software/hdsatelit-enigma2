# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# meniu_web.py: tot meniul receptorului (tasta MENU) in interfata web (HdsWebControl).
#
# Fiecare intrare de meniu are pereche in interfata web, intr-una din trei forme: pagina proprie, motorul generic de
# meniuri, „deschide pe TV”. Pagina /meniu e motorul generic: tot data/menu.xml, cu aceleasi
# reguli ca televizorul (Screens/Menu.py: level= fata de nivelul utilizatorului, requires= din SystemInfo, ordinea dupa
# weight, semnul „(în lucru)” / „(netestat)”), iar la fiecare intrare:
# - pagina ei proprie, cand are una (atributul web= din menu.xml);
# - pagina generica de setari /setari?id=..., la intrarile <setup id="..."/> (setari_web.py);
# - „Deschide pe televizor”: ecranul adevarat se deschide pe televizor, deci valorile si regulile sunt chiar ale lui.
# Nu se deschid pe televizor din aceasta pagina: intrarile <code> (nu se ruleaza cod din menu.xml la o cerere din retea)
# si oprirea sau repornirea receptorului (Standby, TryQuitMainloop): un clic in browser nu opreste receptorul sub cel
# care se uita. Fiecare dintre ele are pagina ei (web=): oprirea, repornirea si standby-ul
# sunt in /alimentare, resetarea in /resetare-fabrica, proba DiSEqC in /proba-diseqc, fiecare actiune cu confirmare in
# doi pasi (meniu_comun_web.py), ca orice
# ecran sa aiba pereche in web; butonul de aici ramane fara ele, deci nimic nu se opreste fara confirmare.
# Extensiile puse de om care se agata de un meniu prin cod (WHERE_MENU) nu sunt in menu.xml si nu apar aici; ale
# imaginii au intrarea lor in menu.xml din 0.2.6 (de exemplu importul de canale, Media, setarile skinului).
#
# Motorul de meniu e cel din scanare_web.py (acelasi fisier citit, aceleasi reguli de vizibilitate); acolo se deschid
# pe televizor numai intrarile din sectiunile Scanare si Antena, aici oricare dintre cele de mai sus.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/meniu                        arborele meniului, cum il vede televizorul acum
#   POST /api/meniu-televizor?id=<entryID> deschide intrarea pe televizor
#   GET  /meniu                            pagina
#
# Fiecare intrare are in pagina ancora i-<entryID>: meniul de sus al paginilor (cadru_web.py) duce acolo la intrarile care
# se deschid numai pe televizor; grupa ei se deschide si randul e ales.

# ecranele care opresc sau repornesc receptorul (Screens/Standby.py): nu se deschid din web
NEDESCHISE = frozenset((("Standby", "Standby"), ("Standby", "TryQuitMainloop")))
MAX_ADANCIME = 6


def _sw():
	from . import scanare_web
	return scanare_web


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] meniu: %s" % text)


def _seDeschide(tinta):
	"""(se deschide pe televizor?, motivul daca nu)."""
	W = _sw()
	if tinta is None:
		return False, "gol"
	if tinta["fel"] == "setup":
		return bool(tinta.get("id")), "" if tinta.get("id") else "gol"
	if tinta["fel"] == "cod":
		return False, "cod"
	if (tinta["modul"], tinta["ecran"]) in NEDESCHISE:
		return False, "oprire"
	if not W._seDeschidePeTelevizor(tinta):
		return False, "cod"
	return True, ""


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


_MOTIVE = {
	"cod": N_("Se deschide numai din telecomandă."),
	"oprire": N_("Oprirea și repornirea se dau numai din telecomandă."),
	"gol": "",
}


def _intrare(nod):
	W = _sw()
	tinta = W._tinta(nod)
	merge, motiv = _seDeschide(tinta)
	motiv = _MOTIVE.get(motiv, "")
	return {
		"tip": "intrare",
		"id": nod.get("entryID") or "",
		"text": W._cuSemn(nod),
		"web": nod.get("web") or "",
		"setup": tinta["id"] if tinta is not None and tinta["fel"] == "setup" else "",
		"televizor": merge,
		# un text gol nu trece prin _(): gettext ar da antetul fisierului .po; o intrare cu pagina web nu are motiv (pagina
		# ei e calea din browser)
		"motiv": _t(motiv) if motiv and not merge and not nod.get("web") else "",
	}


def _grup(nod, nivel, adancime):
	W = _sw()
	copii = []
	if adancime < MAX_ADANCIME:
		for x in W._copiiVizibili(nod, nivel):
			if x.tag == "item":
				copii.append(_intrare(x))
			elif x.tag == "menu":
				copii.append(_grup(x, nivel, adancime + 1))
	return {"tip": "grup", "id": nod.get("entryID") or nod.get("key") or "", "text": W._cuSemn(nod),
		"web": nod.get("web") or "", "copii": copii}


def arbore():
	"""GET /api/meniu: {"result", "meniu": grupul principal}."""
	W = _sw()
	radacina = W._radacinaMeniu()
	if radacina is None:
		return {"result": False, "message": _t("Meniul receptorului nu se poate citi.")}
	principal = radacina.find("menu")
	if principal is None:
		return {"result": False, "message": _t("Meniul receptorului nu se poate citi.")}
	g = _grup(principal, W._nivelUtilizator(), 0)
	g["text"] = _t("Meniu principal")
	return {"result": True, "meniu": g}


def _cauta(nod, id_intrare, nivel, parinti, adancime=0):
	"""(nodul vizibil cu entryID-ul dat, lista parintilor lui) sau (None, None)."""
	W = _sw()
	if adancime > MAX_ADANCIME:
		return None, None
	for x in W._copiiVizibili(nod, nivel):
		if x.tag == "item" and x.get("entryID") == id_intrare:
			return x, parinti + [nod]
		if x.tag == "menu":
			gasit, lant = _cauta(x, id_intrare, nivel, parinti + [nod], adancime + 1)
			if gasit is not None:
				return gasit, lant
	return None, None


# nivelul la care se cauta drumul spre o intrare: peste orice level= din menu.xml, ca drumul sa se poata arata si cand
# intrarea e ascunsa la nivelul ales acum pe receptor (requires= ramane: ce nu exista pe receptor nu are drum)
_NIVEL_ORICARE = 99


def _cautaDrum(nod, id_intrare, parinti, adancime=0):
	"""Lista nodurilor de la primul nivel pana la intrarea (<item>) sau grupul (<menu>) cu entryID-ul sau key-ul dat,
	sau None."""
	W = _sw()
	if adancime > MAX_ADANCIME:
		return None
	for x in W._copiiVizibili(nod, _NIVEL_ORICARE):
		if x.get("entryID") == id_intrare or (x.tag == "menu" and x.get("key") == id_intrare):
			return parinti + [x]
		if x.tag == "menu":
			gasit = _cautaDrum(x, id_intrare, parinti + [x], adancime + 1)
			if gasit is not None:
				return gasit
	return None


def drum(id_intrare):
	"""Numele de pe televizor, traduse ca acolo si fara semnele de stare, de la primul nivel al meniului pana la
	intrare: ["Setări", "Sunet și subtitrări", "Limba sunetului și a subtitrărilor"]; [] daca nu e in meniu."""
	W = _sw()
	radacina = W._radacinaMeniu()
	principal = radacina.find("menu") if radacina is not None else None
	if principal is None or not id_intrare:
		return []
	noduri = _cautaDrum(principal, id_intrare, []) or []
	return [_t(x.get("text") or "") for x in noduri]


def drumText(id_intrare):
	"""„Meniu, „Setări”, „Sunet și subtitrări”, „Limba sunetului și a subtitrărilor”” (text simplu, pentru mesaje);
	numai „Meniu” daca intrarea nu e in meniu."""
	# cuvantul Meniu si ghilimelele sunt ale limbii meniurilor: drumul intra in pagini dupa traducerea lor
	# (__DRUM_MENIU__), deci _traducePagina nu il vede
	ghilimele = _t("„%s”")
	if ghilimele.count("%s") != 1:
		ghilimele = u"\u201e%s\u201d"
	return ", ".join([_t("Meniu")] + [ghilimele % n for n in drum(id_intrare)])


def drumHtml(id_intrare):
	"""drumText scapat pentru HTML (numele au „&”)."""
	import html
	return html.escape(drumText(id_intrare), quote=False)


def cheiSetup():
	"""[(cheia din setup.xml, textul intrarii)] pentru intrarile <setup> vizibile acum (ce poate deschide si
	televizorul), fara dubluri, in ordinea din meniu. Pentru setari_web.py."""
	rez = []
	vazute = set()

	def _umbla(g):
		for c in g.get("copii", []):
			if c["tip"] == "grup":
				_umbla(c)
			elif c.get("setup") and c["setup"] not in vazute:
				vazute.add(c["setup"])
				rez.append((c["setup"], c["text"]))
	a = arbore()
	if a.get("result"):
		_umbla(a["meniu"])
	return rez


def deschide(id_intrare, sesiune=None):
	"""POST /api/meniu-televizor?id=: deschide pe televizor o intrare vizibila, dupa entryID. Modulul, ecranul si
	argumentele vin din menu.xml, nu din cerere."""
	W = _sw()
	radacina = W._radacinaMeniu()
	principal = radacina.find("menu") if radacina is not None else None
	if principal is None or not id_intrare:
		return {"result": False, "message": _t("Intrarea nu e în meniu.")}
	nod, parinti = _cauta(principal, id_intrare, W._nivelUtilizator(), [])
	if nod is None:
		return {"result": False, "message": _t("Intrarea „%s” nu e în meniu.") % id_intrare[:40]}
	tinta = W._tinta(nod)
	merge, motiv = _seDeschide(tinta)
	if not merge:
		return {"result": False, "message": _t(_MOTIVE.get(motiv) or "Se deschide numai din telecomandă.")}
	if sesiune is None:
		sesiune = W._sesiune()
	refuz = W._ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	# ca meniul de pe televizor: un nod parinte cu flushConfigOnClose salveaza setarile la inchidere
	salveaza = any(p.get("flushConfigOnClose") for p in parinti)

	def _laIesire(*_rezultat):
		if salveaza:
			try:
				from Components.config import configfile
				configfile.save()
			except Exception as eroare:
				_jurnal("salvarea setarilor dupa %s: %s" % (id_intrare, eroare))

	try:
		if tinta["fel"] == "setup":
			from Screens.Setup import Setup
			dlg = sesiune.openWithCallback(_laIesire, Setup, tinta["id"])
		else:
			import importlib
			modul = importlib.import_module("Screens." + tinta["modul"])
			ecran = getattr(modul, tinta["ecran"])
			dlg = sesiune.openWithCallback(_laIesire, ecran, *tinta["argumente"])
	except Exception as eroare:
		_jurnal("deschiderea %s pe televizor: %s" % (id_intrare, eroare))
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor (%s).") % eroare}
	if dlg is None:
		return {"result": False, "message": _t("Ecranul nu s-a deschis pe televizor. Detalii în jurnalul receptorului.")}
	return {"result": True, "message": _t("S-a deschis pe televizor: %s.") % _t(nod.get("text") or "")}


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:4]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie != "id":
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:64].strip()
	return rez


def rute(baza, resource):
	class ArboreResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, arbore())
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class TelevizorResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, deschide(argumente(request).get("id", "")))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {b"meniu": ArboreResource(), b"meniu-televizor": TelevizorResource()}
	return api, PaginaResource()


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
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meniul receptorului</title>
<style>__STIL_COMUN__
  main{max-width:880px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  details{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;margin:0 0 10px;}
  details details{margin:8px 0 8px 0;background:#181c23;}
  summary{cursor:pointer;padding:12px 14px;font-size:1rem;min-height:44px;display:flex;align-items:center;gap:10px;}
  summary a{font-size:.85rem;}
  .copii{padding:0 12px 8px;}
  .intrare{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px 12px;padding:8px 2px;border-top:1px solid var(--bordura);}
  .intrare .nume{font-size:.95rem;}
  .intrare .actiuni{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}
  .intrare .motiv{color:var(--text-slab);font-size:.8rem;}
  .unic{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;margin:0 0 10px;padding:4px 14px;}
  .unic .intrare{border-top:0;}
  .unic .nume{font-size:1rem;}
  button{min-height:44px;padding:6px 12px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;font-size:.85rem;cursor:pointer;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .intrare.ales{background:#22304a;border-radius:8px;padding-left:8px;padding-right:8px;}
  form.cauta-setari{display:flex;gap:8px;margin:0 0 14px;}
  form.cauta-setari input{flex:1;min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  form.cauta-setari button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
</style>
</head>
<body>
<main>
<h1>Meniul receptorului</h1>
<form class="cauta-setari" action="/cauta-setari" method="get" role="search"><input type="search" name="q" maxlength="60" placeholder="Caută setări" aria-label="Caută setări" autocomplete="off"><button type="submit">Caută</button></form>
<p class="nota">Același meniu ca la tasta MENU, cu aceleași intrări pentru nivelul ales pe receptor. La fiecare intrare: pagina ei din interfața web, dacă are, pagina de setări sau „Deschide pe televizor”.</p>
<p class="mesaj" id="mesaj">Se citește meniul...</p>
<div id="meniu"></div>
<p class="nota">Extensiile care se agață singure de meniu nu sunt în listă. Oprirea, repornirea și standby-ul receptorului se dau din pagina Alimentare și repornire, cu confirmare, sau din telecomandă.</p>
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
function legatura(href, text){ var a = document.createElement("a"); a.href = adresa(href); a.textContent = text; return a; }
function deschide(id){
  var q = new URLSearchParams(); q.set("id", id);
  mesaj("Se deschide pe televizor...");
  cerere("/api/meniu-televizor", "POST", q).then(function(d){ mesaj(d.message, !d.result); }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function intrare(c){
  var div = document.createElement("div"); div.className = "intrare";
  if(c.id){ div.id = "i-" + c.id; }
  var n = document.createElement("span"); n.className = "nume"; n.textContent = c.text; div.appendChild(n);
  var a = document.createElement("span"); a.className = "actiuni";
  if(c.web){ a.appendChild(legatura(c.web, "Pagina web")); }
  if(c.setup){ a.appendChild(legatura("/setari?id=" + encodeURIComponent(c.setup), "Setări în web")); }
  if(c.televizor){ var b = document.createElement("button"); b.type = "button"; b.textContent = "Deschide pe televizor"; b.addEventListener("click", function(){ deschide(c.id); }); a.appendChild(b); }
  else if(c.motiv){ var m = document.createElement("span"); m.className = "motiv"; m.textContent = c.motiv; a.appendChild(m); }
  div.appendChild(a);
  return div;
}
function grup(g, deschis){
  var d = document.createElement("details"); if(deschis){ d.open = true; }
  var s = document.createElement("summary"); s.appendChild(document.createTextNode(g.text));
  if(g.web){ s.appendChild(legatura(g.web, "Pagina web")); }
  d.appendChild(s);
  var c = document.createElement("div"); c.className = "copii";
  g.copii.forEach(function(x){ c.appendChild(x.tip === "grup" ? grup(x, false) : intrare(x)); });
  d.appendChild(c);
  return d;
}
// /meniu#i-<entryID> (din meniul de sus, la intrarile care se deschid numai pe televizor): grupa intrarii se
// deschide, iar randul ei e ales si adus in fata
function arataDinAdresa(){
  var vechi = document.querySelector(".intrare.ales"); if(vechi){ vechi.classList.remove("ales"); }
  var h = location.hash.slice(1);
  if(!/^i-[A-Za-z0-9_.-]{1,64}$/.test(h)){ return; }
  var x = $(h); if(!x){ return; }
  for(var p = x.parentNode; p; p = p.parentNode){ if(p.tagName === "DETAILS"){ p.open = true; } }
  x.classList.add("ales");
  x.scrollIntoView({block: "center"});
}
window.addEventListener("hashchange", arataDinAdresa);
cerere("/api/meniu").then(function(d){
  if(!d.result){ mesaj(d.message, true); return; }
  mesaj("");
  var m = $("meniu");
  d.meniu.copii.forEach(function(x){
    if(x.tip === "grup"){ m.appendChild(grup(x, false)); return; }
    var u = document.createElement("div"); u.className = "unic"; u.appendChild(intrare(x)); m.appendChild(u);
  });
  arataDinAdresa();
}).catch(function(){ mesaj("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); });
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Meniul receptorului"),
		N_("Caută"),
		N_("Același meniu ca la tasta MENU, cu aceleași intrări pentru nivelul ales pe receptor. La fiecare "
			"intrare: pagina ei din interfața web, dacă are, pagina de setări sau „Deschide pe televizor”."),
		N_("Se citește meniul..."),
		N_("Extensiile care se agață singure de meniu nu sunt în listă. Oprirea, repornirea și standby-ul "
			"receptorului se dau din pagina Alimentare și repornire, cu confirmare, sau din telecomandă."),
		N_("Caută setări"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se deschide pe televizor..."),
		N_("Receptorul nu răspunde."),
		N_("Pagina web"),
		N_("Setări în web"),
		N_("Deschide pe televizor"),
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

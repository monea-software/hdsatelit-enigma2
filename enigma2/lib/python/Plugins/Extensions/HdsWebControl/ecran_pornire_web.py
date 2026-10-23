# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ecran_pornire_web.py: „Ecranul de pornire” in interfata web (HdsWebControl), perechea ecranului de pe televizor
# (Screens/HdsEcranPornire.py). Aceleasi date si aceleasi comenzi, din acelasi modul, Components/HdsEcranePornire.py.
#
# Pagina are aceeasi asezare ca ecranul de pe televizor: sus grupele („Toate”, „Logo”, „Natură”, ..., „Pozele mele”
# cand exista), dedesubt ecranele in randuri si coloane (chenarele se aseaza singure pe cate incap, si pe telefon),
# cu semnul „pus acum” pe cel pus si „șterge” pe cele care se pot sterge (nu ecranul din fabrica, nici cel pus acum),
# apoi „Pune la loc ecranele șterse” cand omul a sters vreunul. Jos, bara cu ecranul ales, „Pune pe receptor” si
# „Ecranul din fabrică” (tasta albastra de pe televizor); mai jos, trimiterea unei poze proprii, cu limita de poze.
# Pozele nu au niciun text: randul cu siturile si versiunea il scrie receptorul peste poza, la pornire. Pagina e in
# romana, deci si numele grupelor si ale ecranelor vin romanesti (lista("ro")).
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/ecrane                                  grupele, ecranele, pozele proprii, ecranul pus acum
#   GET  /api/ecran-poza?sursa=galerie|propriu&id=..  poza mica a unui ecran (JPG, 480x270)
#   POST /api/ecran-alege?sursa=..&id=..              pune ecranul (fir separat)
#   POST /api/ecran-sterge?sursa=galerie|propriu&id=..  sterge un ecran din galerie sau o poza proprie (fara sursa:
#                                                     poza proprie cu acel id, altfel ecranul din galerie)
#   POST /api/ecran-la-loc                            „Pune la loc ecranele șterse”
#   POST /api/ecran-urca?nume=..                      poza ca octeti bruti in corp (application/octet-stream; limita
#                                                     de marime o pune _CerereHds din plugin.py dupa cale)
#   GET  /ecrane                                      pagina
#
# FIRUL: punerea si conversia unei poze scriu pe flash si pot tine secunde bune, deci NU se fac pe firul enigma2 (ar
# ingheta televizorul): fir separat + dictionar simplu + eTimer care trimite raspunsul (callLater nu trezeste bucla
# reactorului imaginii). Steagul unei lucrari cade abia cand firul s-a terminat, nu la raspunsul „a durat prea mult”:
# altfel o a doua cerere ar porni a doua conversie langa prima. Fisierul nu importa nimic din enigma2 la incarcare:
# probele de pe PC dau furnizori falsi.

import json
import threading
import time

try:
	from twisted.web.server import NOT_DONE_YET
except ImportError:          # pe PC, fara Twisted
	NOT_DONE_YET = 1


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _ep():
	from Components import HdsEcranePornire
	return HdsEcranePornire


def _jurnal(text):
	try:
		from . import plugin
		plugin._jurnal(text)
	except Exception:
		print("[HdsWebControl] %s" % text)


def _adresa(request):
	try:
		from . import plugin
		return plugin._adresaClient(request)
	except Exception:
		return "?"


def _arg(request, cheie, implicit=b""):
	return request.args.get(cheie, [implicit])[0].decode("ascii", "replace")


def date(limba="ro", ep=None):
	"""Corpul lui GET /api/ecrane: exact ce foloseste si ecranul de pe televizor."""
	ep = ep or _ep()
	d = ep.lista(limba)
	d["result"] = True
	return d


class _Stare(object):
	"""Cate o singura lucrare de fiecare fel, in tot procesul: o conversie de poza, o punere de ecran."""
	conversie = [False]
	punere = [False]
	ceasuri = []
	legaturi = []


def porneste_pe_fir(request, lucru, steag, timeout_s, fabrica_ceas=None):
	"""`lucru` (fara parametri, pregatit pe firul reactorului) ruleaza pe un fir separat; raspunsul il trimite un
	eTimer pe firul enigma2. `lucru` intoarce corpul raspunsului sau (corp, cod_http). `steag` e [bool], pus pe True
	cat merge firul. Intoarce NOT_DONE_YET."""
	if fabrica_ceas is None:
		from enigma import eTimer as fabrica_ceas
	rezultat = {}
	pornit = time.time()

	def fir():
		try:
			rezultat["gata"] = lucru()
		except Exception as eroare:
			rezultat["eroare"] = str(eroare)
		finally:
			steag[0] = False        # lucrarea s-a terminat de-adevaratelea

	def trimite(corp, cod=200):
		try:
			request.setResponseCode(cod)
			request.setHeader(b"content-type", b"application/json; charset=utf-8")
			request.setHeader(b"cache-control", b"no-store")
			request.write(json.dumps(corp, ensure_ascii=False).encode("utf-8", "replace"))
			request.finish()
		except Exception as eroare:
			_jurnal("ecran de pornire: nu am putut trimite raspunsul (client plecat?): %s" % eroare)

	ceas = fabrica_ceas()
	_Stare.ceasuri.append(ceas)

	def opreste():
		try:
			ceas.stop()
		except Exception:
			pass
		try:
			_Stare.ceasuri.remove(ceas)
		except ValueError:
			pass

	def verifica():
		if "gata" in rezultat:
			opreste()
			gata = rezultat["gata"]
			if isinstance(gata, tuple):
				trimite(gata[0], gata[1])
			else:
				trimite(gata)
		elif "eroare" in rezultat:
			opreste()
			_jurnal("ecran de pornire: eroare in firul separat: %s" % rezultat["eroare"])
			trimite({"result": False, "message": _t("Eroare pe receptor la ecranul de pornire.")}, 500)
		elif time.time() - pornit > timeout_s:
			opreste()
			trimite({"result": False, "message": _t("A durat prea mult.")}, 504)

	try:
		ceas.callback.append(verifica)
	except AttributeError:
		_Stare.legaturi.append(ceas.timeout.connect(verifica))
	steag[0] = True
	t = threading.Thread(target=fir)
	t.daemon = True
	t.start()
	ceas.start(150, False)
	return NOT_DONE_YET


def rute(baza, resource, ep=None, fabrica_ceas=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii /ecrane). `baza` e HdsJsonResource din plugin.py."""

	def m():
		return ep or _ep()

	class EcraneResource(baza):
		"""GET /api/ecrane: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, date(ep=m()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PozaResource(baza):
		"""GET /api/ecran-poza: calea o face MODULUL, din identificator, verificata cu realpath; nimic din ce vine
		prin retea nu ajunge intr-o cale asa cum a venit. Numai citire."""

		def render_GET(self, request):
			M = m()
			cale = M.caleMic(_arg(request, b"sursa", b"galerie"), _arg(request, b"id"))
			if cale is None:
				return self._eroare(request, _t("Previzualizarea cerută nu există."), 404)
			tip = M.tipulPozei(cale)
			if tip is None:
				return self._eroare(request, _t("Previzualizarea cerută nu este o poză."), 404)
			try:
				with open(cale, "rb") as f:
					octeti = f.read()
			except OSError as eroare:
				return self._eroare(request, "nu am putut citi previzualizarea: %s" % eroare, 500)
			request.setResponseCode(200)
			request.setHeader(b"content-type", tip.encode("ascii"))
			# se schimba doar cand omul urca alta poza: 5 minute de cache scutesc receptorul de zeci de citiri
			request.setHeader(b"cache-control", b"private, max-age=300")
			request.setHeader(b"x-content-type-options", b"nosniff")
			return octeti

	class AlegeResource(baza):
		"""POST /api/ecran-alege: pune ecranul pe un fir separat (HdsEcranePornire.aplica). Nu reporneste interfata si
		nu atinge showiframe; ecranul se vede la urmatoarea pornire. Acelasi drum ca OK pe televizor."""
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			if _Stare.punere[0]:
				return self._eroare(request, _t("Receptorul pune deja un ecran. Încearcă din nou peste câteva clipe."), 503)
			sursa = _arg(request, b"sursa", b"galerie")
			id_ecran = _arg(request, b"id")
			client = _adresa(request)
			M = m()

			def lucru():
				bun, mesaj = M.aplica(sursa, id_ecran)
				if not bun:
					return {"result": False, "message": mesaj}, 400
				_jurnal("ecran de pornire schimbat in %s/%s, de la %s" % (sursa, id_ecran, client))
				return {"result": True, "message": mesaj, "sursa": sursa, "id": id_ecran}

			return porneste_pe_fir(request, lucru, _Stare.punere, 60, fabrica_ceas)

	class StergeResource(baza):
		"""POST /api/ecran-sterge: sterge un ecran din galerie sau o poza proprie (nu ecranul din fabrica, nici cel
		pus sau ales acum; regulile sunt ale modulului). Numai fisiere mici si o lista, deci pe loc."""
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			id_ecran = _arg(request, b"id")
			sursa = _arg(request, b"sursa") or None
			bun, mesaj = m().sterge(id_ecran, sursa)
			if bun:
				_jurnal("ecran de pornire sters: %s/%s, de la %s" % (sursa or "?", id_ecran, _adresa(request)))
			return self._raspunde(request, {"result": bool(bun), "message": mesaj, "id": id_ecran}, 200 if bun else 400)

	class LaLocResource(baza):
		"""POST /api/ecran-la-loc: „Pune la loc ecranele șterse” (uita lista ecranelor sterse din galerie)."""
		schimbaCeva = True

		def render_POST(self, request):
			return self.render_GET(request)

		def render_GET(self, request):
			bun, mesaj = m().laLoc()
			return self._raspunde(request, {"result": bool(bun), "message": mesaj}, 200 if bun else 400)

	class UrcaResource(baza):
		"""POST /api/ecran-urca?nume=<numele fisierului>, cu POZA CA OCTETI BRUTI in corp: Twisted nu parseaza nimic pe
		firul enigma2 si nu scrie nimic in /tmp. Poza se verifica DUPA CONTINUT si NU se scrie niciodata peste ecranul
		activ: se salveaza in dosarul pozelor proprii, se converteste acolo si abia fisierul .mvi rezultat se pune."""
		schimbaCeva = True

		def render_GET(self, request):
			return self._eroare(request, _t("Poza se trimite cu POST."), 405)

		def render_POST(self, request):
			M = m()
			if _Stare.conversie[0]:
				return self._eroare(request, _t("Receptorul pregătește deja o poză. Încearcă din nou peste câteva clipe."), 503)
			try:
				request.content.seek(0)
				octeti = request.content.read(M.MAX_POZA + 1)
			except Exception as eroare:
				return self._eroare(request, "nu am putut citi poza: %s" % eroare)
			nume = request.args.get(b"nume", [b""])[0].decode("utf-8", "replace")
			# verificarile ieftine se fac aici, pe firul reactorului: un refuz nu porneste niciun fir
			fel, _latime, _inaltime, eroare = M.verificaPoza(octeti)
			if fel is None:
				return self._raspunde(request, {"result": False, "message": eroare}, 400)
			_jurnal("poza de ecran de pornire primita (%d octeti, %s) de la %s" % (len(octeti), fel, _adresa(request)))

			def lucru():
				return M.primestePoza(octeti, nume)

			return porneste_pe_fir(request, lucru, _Stare.conversie, 180, fabrica_ceas)

	class PaginaResource(resource.Resource):
		"""GET /ecrane: pagina „Ecranul de pornire”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"ecrane": EcraneResource(),
		b"ecran-poza": PozaResource(),
		b"ecran-alege": AlegeResource(),
		b"ecran-sterge": StergeResource(),
		b"ecran-la-loc": LaLocResource(),
		b"ecran-urca": UrcaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca panoul: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser neconectat
	primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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
	# subsolul scurt: lista „Toate paginile” (fostul subsol al panoului) e in meniul cadrului (cadru_web.py)
	text = pagina_text(P._STIL_COMUN, config_pagina)
	legaturi = getattr(P, "_legaturiDisponibile", None)
	if legaturi is not None:
		text = legaturi(text)
	return text.encode("utf-8", "replace")


SUBSOL_SCURT = """<footer>
  <a href="/jurnal">Ce e nou</a>
  <a href="/meniu">Tot meniul receptorului</a>
</footer>"""


def _subsolTradus(subsol):
	"""Numele legaturilor din subsol in limba meniurilor (subsolul intra dupa traducerea paginii; numele sunt in
	registrul paginilor din plugin.py, marcate acolo pentru po)."""
	import re

	def tradus(m):
		t = _t(m.group(2)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
		return m.group(1) + t + m.group(3)
	return re.sub(r'(<a href="[^"]*">)([^<]+)(</a>)', tradus, subsol)


def pagina_text(stil, config_pagina, subsol=SUBSOL_SCURT):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__SUBSOL__", _subsolTradus(subsol))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ecranul de pornire</title>
<style>__STIL_COMUN__
  body{padding-bottom:110px;}
  main{max-width:1100px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 6px;}
  .sub{margin:0 0 14px;color:var(--text-slab);font-size:.85rem;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px;margin:16px 0;}
  .card h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .grupe{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px;}
  .grupe button{background:#242a33;color:var(--text);border:1px solid var(--bordura);border-radius:999px;padding:8px 16px;font-size:.9rem;cursor:pointer;min-height:44px;}
  .grupe button.activ{background:var(--accent);border-color:var(--accent);color:#fff;}
  .ecrane{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;}
  .ecran{position:relative;background:#0d1014;border:2px solid var(--bordura);border-radius:10px;overflow:hidden;display:flex;flex-direction:column;}
  .ecran.ales{border-color:var(--accent);}
  .ecran .alege{background:none;border:none;padding:0;margin:0;text-align:left;color:var(--text);font:inherit;cursor:pointer;display:block;width:100%;}
  .ecran .alege:focus-visible{outline:3px solid #7fb8ff;outline-offset:-3px;}
  .ecran .poza{aspect-ratio:16/9;background:#000;display:flex;align-items:center;justify-content:center;}
  .ecran .poza img{width:100%;height:100%;object-fit:cover;display:block;}
  .ecran .gol{color:var(--text-slab);font-size:.8rem;padding:8px;text-align:center;}
  .ecran .nume{display:block;padding:10px;font-size:.9rem;min-height:44px;box-sizing:border-box;}
  .ecran .semn{position:absolute;left:8px;top:8px;font-size:.8rem;color:#10162a;background:#4fd18b;border-radius:999px;padding:3px 10px;white-space:nowrap;pointer-events:none;}
  .ecran .sterge{background:none;border:none;border-top:1px solid var(--bordura);color:var(--text-slab);font:inherit;font-size:.85rem;cursor:pointer;text-decoration:underline;min-height:44px;padding:0 10px;text-align:left;}
  .ecran .sterge:focus-visible{outline:3px solid #7fb8ff;outline-offset:-3px;}
  .la-loc{margin:12px 0 0;display:none;align-items:center;gap:10px;flex-wrap:wrap;}
  .urcare{display:flex;flex-wrap:wrap;gap:10px;align-items:center;}
  .urcare input[type=file]{color:var(--text-slab);font:inherit;max-width:100%;min-height:44px;}
  .buton{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:11px 18px;font-size:.95rem;cursor:pointer;min-height:44px;}
  .buton.al-doilea{background:#242a33;color:var(--text);border:1px solid var(--bordura);}
  .buton[disabled]{background:#3a424e;color:#8891a0;cursor:default;}
  .bara{position:fixed;left:var(--cadru-stanga,0px);right:0;bottom:var(--cadru-jos,0px);background:var(--panou);border-top:1px solid var(--bordura);padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;}
  .bara .ce{font-size:.9rem;color:var(--text-slab);overflow-wrap:anywhere;flex:1 1 200px;}
  .bara .butoane{display:flex;gap:10px;flex-wrap:wrap;}
  .stare{font-size:.85rem;color:var(--text-slab);margin-top:10px;min-height:1.2em;}
  .rau{color:#ff9a8f;}
  .bun{color:#8fe0b0;}
  footer{color:var(--text-slab);font-size:.8rem;display:flex;flex-wrap:wrap;gap:8px 18px;}
</style>
</head>
<body>
<main>
<h1>Ecranul de pornire</h1>
<p class="sub">Alege poza pe care o arată receptorul când pornește. Se vede de la următoarea pornire.</p>
<div class="grupe" id="grupe"></div>
<div class="ecrane" id="ecrane"></div>
<div class="stare" id="stareGrila"></div>
<div class="la-loc" id="laLoc">
  <button class="buton al-doilea" id="punelaloc" type="button">Pune la loc ecranele șterse</button>
</div>

<div class="card">
  <h2>Poza mea</h2>
  <p class="sub" id="explicatieUrcare">Poți pune o poză a ta, JPG sau PNG.</p>
  <div class="urcare">
    <input type="file" id="fisier" accept="image/jpeg,image/png">
    <button class="buton" id="trimite" disabled>Trimite poza</button>
  </div>
  <div class="stare" id="stareUrcare"></div>
</div>

__SUBSOL__
</main>

<div class="bara">
  <span class="ce" id="ce">Se încarcă lista...</span>
  <span class="butoane">
    <button class="buton al-doilea" id="fabrica" type="button" disabled>Ecranul din fabrică</button>
    <button class="buton" id="pune" type="button" disabled>Pune pe receptor</button>
  </span>
</div>

<script>
var CFG = __CONFIG__;
var DATE = null;
var ALES = null;
var GRUP = "toate";

function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function anteteCerere(){
  var a = {};
  if(CFG.csrf){ a["X-HDS-CSRF"] = CFG.csrf; }
  return a;
}
function cerere(cale, metoda){
  return fetch(adresa(cale), {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: anteteCerere()})
    .then(function(r){
      if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
      return r.json().then(function(d){ d._cod = r.status; return d; });
    });
}
function pozaUrl(sursa, id){
  return adresa("/api/ecran-poza?sursa=" + encodeURIComponent(sursa) + "&id=" + encodeURIComponent(id));
}
function spune(unde, text, fel){
  var e = document.getElementById(unde);
  e.textContent = text;
  e.className = "stare" + (fel ? " " + fel : "");
}
function toateEcranele(){
  if(!DATE){ return []; }
  return (DATE.ecrane || []).concat(DATE.proprii || []);
}
function esteActiv(x){
  return DATE && DATE.activ && DATE.activ.sursa === x.sursa && DATE.activ.id === x.id;
}
function numeImplicit(){
  var gasit = ((DATE && DATE.ecrane) || []).filter(function(x){ return x.id === DATE.implicit; })[0];
  return gasit ? gasit.nume : "";
}

// aceleasi grupe ca pe televizor: „Toate”, apoi cele din lista (numai cele cu ecrane), „Pozele mele” la urma
function deseneazaGrupe(){
  var cutie = document.getElementById("grupe");
  cutie.textContent = "";
  var grupe = [{id: "toate", nume: "Toate"}].concat(DATE.grupe || []);
  grupe.forEach(function(g){
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = g.nume;
    if(g.id === GRUP){ b.className = "activ"; }
    b.onclick = function(){ GRUP = g.id; deseneazaGrupe(); deseneazaEcrane(); };
    cutie.appendChild(b);
  });
}

// fiecare ecran: un cartonas cu doua butoane, „alege” (poza si numele) si, unde se poate, „șterge”
function deseneazaEcrane(){
  var cutie = document.getElementById("ecrane");
  cutie.textContent = "";
  toateEcranele().forEach(function(x){
    if(GRUP !== "toate" && x.grup !== GRUP){ return; }
    var carte = document.createElement("div");
    carte.className = "ecran" + (ALES && ALES.sursa === x.sursa && ALES.id === x.id ? " ales" : "");
    var b = document.createElement("button");
    b.type = "button";
    b.className = "alege";
    b.onclick = function(){ ALES = {sursa: x.sursa, id: x.id, nume: x.nume}; deseneazaEcrane(); potrivesteBara(); };

    var poza = document.createElement("span");
    poza.className = "poza";
    if(x.are_poza){
      var img = document.createElement("img");
      img.loading = "lazy";
      img.alt = x.nume;
      img.src = pozaUrl(x.sursa, x.id);
      poza.appendChild(img);
    } else {
      var gol = document.createElement("span");
      gol.className = "gol";
      gol.textContent = "fără previzualizare";
      poza.appendChild(gol);
    }
    b.appendChild(poza);
    var nume = document.createElement("span");
    nume.className = "nume";
    nume.textContent = x.nume;
    b.appendChild(nume);
    carte.appendChild(b);
    if(esteActiv(x)){
      var semn = document.createElement("span");
      semn.className = "semn";
      semn.textContent = "pus acum";
      carte.appendChild(semn);
    }
    if(x.se_sterge){
      var st = document.createElement("button");
      st.className = "sterge";
      st.type = "button";
      st.textContent = x.sursa === "propriu" ? "șterge poza" : "șterge din galerie";
      st.onclick = function(){ stergeEcran(x); };
      carte.appendChild(st);
    }
    cutie.appendChild(carte);
  });
  if(!cutie.children.length){
    var p = document.createElement("p");
    p.className = "sub";
    p.textContent = "Nu este niciun ecran în această grupă.";
    cutie.appendChild(p);
  }
}

function potrivesteBara(){
  document.getElementById("pune").disabled = !ALES;
  document.getElementById("fabrica").disabled = !(DATE && DATE.implicit);
  document.getElementById("ce").textContent = ALES ? ("Ales: " + ALES.nume) : "Atinge un ecran ca să îl alegi.";
}

function incarca(){
  return cerere("/api/ecrane").then(function(d){
    if(!d.result){ throw new Error(d.message || "nu am putut citi lista"); }
    DATE = d;
    var exista = [{id: "toate"}].concat(d.grupe || []).some(function(g){ return g.id === GRUP; });
    if(!exista){ GRUP = "toate"; }
    var mb = Math.round((d.max_octeti || 0) / 1048576);
    var cate = d.max_proprii || 6;
    var ai = (d.proprii || []).length;
    var text = "Poți pune o poză a ta, JPG sau PNG, de cel mult " + mb + " MB. Receptorul o aduce la 1920x1080, fără deformare. " +
      "Poți avea cel mult " + cate + " poze proprii; acum ai " + ai + ".";
    if(ai >= cate){ text += " Șterge una înainte de a trimite alta."; }
    if(!d.poate_converti){ text += " Acest receptor nu are încă unealta care face ecranul dintr-o poză."; }
    document.getElementById("explicatieUrcare").textContent = text;
    document.getElementById("fisier").disabled = !d.poate_converti || ai >= cate;
    document.getElementById("laLoc").style.display = d.sterse ? "flex" : "none";
    document.getElementById("punelaloc").textContent = "Pune la loc ecranele șterse (" + (d.sterse || 0) + ")";
    deseneazaGrupe();
    deseneazaEcrane();
    potrivesteBara();
  }).catch(function(e){
    document.getElementById("ce").textContent = "Eroare: " + e.message;
  });
}

document.getElementById("pune").onclick = function(){
  if(!ALES){ return; }
  puneEcranul(ALES.sursa, ALES.id, this);
};

// tasta albastra de pe televizor: ecranul pus de imagine (grila)
document.getElementById("fabrica").onclick = function(){
  if(!DATE || !DATE.implicit){ return; }
  ALES = {sursa: "galerie", id: DATE.implicit, nume: numeImplicit() || DATE.implicit};
  deseneazaEcrane();
  puneEcranul("galerie", DATE.implicit, this);
};

function puneEcranul(sursa, id, buton){
  buton.disabled = true;
  document.getElementById("ce").textContent = "Se pune...";
  return cerere("/api/ecran-alege?sursa=" + encodeURIComponent(sursa) + "&id=" + encodeURIComponent(id), "POST")
    .then(function(d){
      var mesaj = d.message || (d.result ? "Gata." : "Nu s-a putut.");
      document.getElementById("ce").textContent = mesaj;
      return incarca().then(function(){ document.getElementById("ce").textContent = mesaj; });
    })
    .catch(function(e){ document.getElementById("ce").textContent = "Eroare: " + e.message; })
    .then(function(){
      document.getElementById("pune").disabled = !ALES;
      document.getElementById("fabrica").disabled = !(DATE && DATE.implicit);
    });
}

function stergeEcran(x){
  var intrebare = x.sursa === "propriu" ? ("Ștergi poza „" + x.nume + "”?") :
    ("Ștergi „" + x.nume + "” din galerie? Îl aduci înapoi cu „Pune la loc ecranele șterse”.");
  if(!window.confirm(intrebare)){ return; }
  cerere("/api/ecran-sterge?sursa=" + encodeURIComponent(x.sursa) + "&id=" + encodeURIComponent(x.id), "POST").then(function(d){
    if(ALES && ALES.sursa === x.sursa && ALES.id === x.id){ ALES = null; }
    return incarca().then(function(){ spune("stareGrila", d.message || "", d.result ? "bun" : "rau"); });
  }).catch(function(e){ spune("stareGrila", "Eroare: " + e.message, "rau"); });
}

document.getElementById("punelaloc").onclick = function(){
  cerere("/api/ecran-la-loc", "POST").then(function(d){
    return incarca().then(function(){ spune("stareGrila", d.message || "", d.result ? "bun" : "rau"); });
  }).catch(function(e){ spune("stareGrila", "Eroare: " + e.message, "rau"); });
};

document.getElementById("fisier").onchange = function(){
  var f = this.files && this.files[0];
  document.getElementById("trimite").disabled = !f;
  if(!f){ spune("stareUrcare", ""); return; }
  var mare = DATE && DATE.max_octeti ? DATE.max_octeti : 8388608;
  if(f.size > mare){
    var are = (Math.round(f.size / 104857.6) / 10).toString().replace(".", ",");
    spune("stareUrcare", "Poza are " + are + " MB, peste limita de " + Math.round(mare / 1048576) + " MB.", "rau");
    document.getElementById("trimite").disabled = true;
    return;
  }
  spune("stareUrcare", "Gata de trimis: " + f.name);
};

document.getElementById("trimite").onclick = function(){
  var camp = document.getElementById("fisier");
  var f = camp.files && camp.files[0];
  if(!f){ return; }
  var buton = this;
  buton.disabled = true;
  spune("stareUrcare", "Se trimite poza...");
  var antete = anteteCerere();
  antete["Content-Type"] = "application/octet-stream";
  fetch(adresa("/api/ecran-urca?nume=" + encodeURIComponent(f.name)), {
    method: "POST", body: f, cache: "no-store", credentials: "same-origin", headers: antete
  }).then(function(r){
    if(r.status === 413){ throw new Error("poza este prea mare pentru receptor"); }
    return r.json();
  }).then(function(d){
    spune("stareUrcare", d.message || (d.result ? "Gata." : "Nu s-a putut."), d.result ? "bun" : "rau");
    if(d.result){ camp.value = ""; ALES = null; GRUP = "proprii"; }
    return incarca();
  }).catch(function(e){
    spune("stareUrcare", "Eroare: " + e.message, "rau");
  }).then(function(){
    buton.disabled = !(camp.files && camp.files[0]);
  });
};

incarca();
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
		N_("Ecranul de pornire"),
		N_("Alege poza pe care o arată receptorul când pornește. Se vede de la următoarea pornire."),
		N_("Pune la loc ecranele șterse"),
		N_("Poza mea"),
		N_("Poți pune o poză a ta, JPG sau PNG."),
		N_("Trimite poza"),
		N_("Se încarcă lista..."),
		N_("Ecranul din fabrică"),
		N_("Pune pe receptor"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Toate"),
		N_("fără previzualizare"),
		N_("pus acum"),
		N_("șterge poza"),
		N_("șterge din galerie"),
		N_("Nu este niciun ecran în această grupă."),
		N_("Ales:"),
		N_("Atinge un ecran ca să îl alegi."),
		N_("nu am putut citi lista"),
		N_("Poți pune o poză a ta, JPG sau PNG, de cel mult"),
		N_("MB. Receptorul o aduce la 1920x1080, fără deformare."),
		N_("Poți avea cel mult"),
		N_("Șterge una înainte de a trimite alta."),
		N_("Acest receptor nu are încă unealta care face ecranul dintr-o poză."),
		N_("Pune la loc ecranele șterse ("),
		N_("Eroare:"),
		N_("Se pune..."),
		N_("Gata."),
		N_("Nu s-a putut."),
		N_("Ștergi poza „"),
		N_("Ștergi „"),
		N_("” din galerie? Îl aduci înapoi cu „Pune la loc ecranele șterse”."),
		N_("Poza are"),
		N_("MB, peste limita de"),
		N_("Gata de trimis:"),
		N_("Se trimite poza..."),
		N_("poza este prea mare pentru receptor"),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# aplicatii_tv_web.py: „Aplicații” in interfata web (HdsWebControl), perechea meniului de pe televizor (Meniu >
# Aplicații, Screens/HdsAplicatii.py). Numele „aplicatii_web.py” e al rutelor pentru aplicatiile de telefon, deci
# aici e /aplicatii-tv.
# Aceleasi lucruri ca pe televizor, din aceeasi logica (Components/HdsAplicatii.py, setarile config.plugins.hdsaplicatii):
#   - cardurile in ordinea omului, cu cele ascunse (marcate), descrierea si nota despre video;
#   - „Deschide pe televizor” (navigatorul imaginii, modul aplicatie, Plugins/Extensions/HdsNavigator.deschideAplicatie);
#   - mutarea la stanga / la dreapta, ascunderea si aratarea din nou.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/aplicatii-tv              lista (toate, cu „ascunsa”), daca navigatorul exista, daca are video
#   POST /api/aplicatii-tv-deschide     id=...: aplicatia pe televizor
#   POST /api/aplicatii-tv-muta         id=..., pas=-1|1: un loc la stanga sau la dreapta intre cele vazute
#   POST /api/aplicatii-tv-ascunde      id=..., da=1|0: ascunde sau arata din nou
#   GET  /api/aplicatii-tv-poza         id=...: poza cardului (aceeasi ca pe televizor)
# Magazinul (runda 2): instalarea, actualizarea si stergerea unei aplicatii din feed folosesc rutele Extensiilor
# (/api/extensii-instaleaza|actualizeaza|sterge?pachet=<nume>, cu confirmarea in doi pasi a paginilor), deci aceeasi
# lucrare opkg, aceleasi mesaje si aceeasi paza „o lucrare odata” ca pe televizor si in /extensii; starea lucrarii vine in
# GET /api/aplicatii-tv („lucrare”), iar pagina o urmareste pana se termina.
#   GET  /aplicatii-tv                  pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; nimic nu asteapta.


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


class Legaturi(object):
	"""Logica aplicatiilor si deschiderea pe televizor; probele de pe PC dau altele."""

	def __init__(self):
		from Components import HdsAplicatii
		self.A = HdsAplicatii

	def porneste(self, sesiune, aplicatie):
		"""None daca a pornit, altfel textul pentru om (HdsAplicatii.porneste)."""
		return self.A.porneste(sesiune, aplicatie)

	def navigatorDeschis(self):
		try:
			from Plugins.Extensions.HdsNavigator import lansator
		except ImportError:
			return False
		nav = lansator.activ()
		return nav is not None and nav.mod != lansator.MOD_HBBTV

	def instalat(self):
		return bool(self.A.browsereDisponibile())

	def catalog(self):
		return self.A.catalogAcum()

	def widevine(self):
		"""Descarcarea modulului Widevine (Components/HdsWidevine.stare: faza, procent, mesaj), sau None."""
		try:
			from Components import HdsWidevine
		except ImportError:
			return None
		return HdsWidevine.stare()

	def lucrare(self):
		"""Lucrarea opkg de acum (instalarea pornita din pagina sau de pe televizor), pe scurt, sau None."""
		try:
			from Components import HdsExtensiiLucru as L
		except ImportError:
			return None
		l = L.STARE.get("lucrare")
		if l is None:
			return None
		r = l.rezultat or {}
		return {"nume": l.plan.get("nume", ""), "faza": l.faza, "pas": l.pas, "titlu": r.get("titlu", "")}


_legaturi = [None]


def _n(N=None):
	if N is not None:
		return N
	if _legaturi[0] is None:
		_legaturi[0] = Legaturi()
	return _legaturi[0]


def _titlu(a):
	return _t(a["titlu"]) if a.get("titlu_tradus") else a["titlu"]


def stare(N=None, sesiune=None):
	"""GET /api/aplicatii-tv: toate cardurile (si cele ascunse, marcate), cu starea din magazin si actiunile lor."""
	N = _n(N)
	A = N.A
	video = A.areVideo()
	catalog = N.catalog()
	vazute = [a["id"] for a in A.listaPentruOm(catalog=catalog)]
	lista = []
	for a in A.listaPentruOm(cu_ascunse=True, catalog=catalog):
		s = a.get("stare")
		if A.fel(a) == A.FEL_SCURTATURA and s != A.CERE_WIDEVINE:
			nota = A.stare(a, video)
			text_stare = _t(nota) if nota else _t(N_("Instalat"))
		else:
			text_stare = _t(A.TEXTE_STARE.get(s, ""))
			p = A.pachetDinCatalog(a, catalog)
			if s == A.CERE_NAVIGATOR:
				trebuie, _liber = A.locNavigator()
				if trebuie:
					text_stare += " · ~%d MB" % (trebuie // 1048576)
			if s == A.DISPONIBIL and p is not None and p.marime:
				try:
					from Components.HdsPachete import marime_text
					text_stare += " · " + marime_text(p.marime)
				except ImportError:
					pass
		descriere = A.descriereIntreaga(a, _t, video)
		lista.append({
			"id": a["id"], "titlu": _titlu(a), "culoare": a["culoare"],
			"descriere": descriere,
			"stare": text_stare,
			"fel_stare": s or "",
			"actiuni": A.actiuni(a, s),
			"pachet": a.get("pachet", "") if A.fel(a) == A.FEL_PACHET else "",
			# 0.7.8 (CR3): aplicatiile din imagine (Filme si seriale) pornesc si fara navigator
			"imagine": A.fel(a) == A.FEL_IMAGINE,
			"poza": bool(A.pozaPentru(a)),
			"ascunsa": a["id"] not in vazute,
			"browser": A.preferintaBrowser(a["id"]),
			"browsere": A.alegeriBrowser(True, a["id"], _t)
				if A.fel(a) == A.FEL_SCURTATURA and not A.motorObligatoriu(a) else [],
		})
	# NVM: pe receptoarele unde navigatorul se poate instala din cardul lui, nota rosie „lipseste din imagine” nu se arata
	de_instalat = any(x["fel_stare"] in (A.CERE_NAVIGATOR, A.NU_INCAPE) for x in lista)
	return {"result": True, "aplicatii": lista, "vazute": vazute, "instalat": N.instalat() or de_instalat,
		"video": bool(video),
		"catalog_gata": catalog is not None, "lucrare": N.lucrare(), "widevine": N.widevine(),
		"browser": A.browserGeneral(),
		"browsere": [(m, _t(t)) for m, t in A.alegeriBrowser()] if len(A.browsereDisponibile()) == 2 else []}


def browser(argumente, N=None, sesiune=None):
	"""POST: aceeasi alegere si salvare imediata ca in meniul TV."""
	N = _n(N)
	id_ = argumente.get("id")
	ok = "motor" in argumente and N.A.salveazaBrowser(argumente["motor"], id_)
	return _cuStare({"result": ok, "message": _t(N_("Browserul s-a salvat.")) if ok else
		_t(N_("Browserul nu se poate alege pentru această aplicație sau nu mai este instalat."))}, N, sesiune)


def _cuStare(rez, N, sesiune):
	rez.update(dict((k, v) for k, v in stare(N, sesiune).items() if k != "result"))
	return rez


def deschide(argumente, N=None, sesiune=None):
	"""POST /api/aplicatii-tv-deschide: aplicatia porneste pe televizor (scurtatura in navigator, pluginul ei)."""
	N = _n(N)
	A = N.A
	a = A.gaseste(argumente.get("id", ""))
	if a is None:
		return _cuStare({"result": False, "message": _t("Aplicația nu există pe acest receptor.")}, N, sesiune)
	if A.stareMagazin(a, N.catalog()) in (A.CERE_NAVIGATOR, A.NU_INCAPE):
		# NVM: navigatorul lipseste (Vu+ Solo SE si celelalte MIPS): butonul Instaleaza al cardului, ca OK pe televizor
		text = A.instaleazaNavigator(sesiune)
		return _cuStare({"result": text is None, "message": _t(A.TEXT_NAVIGATOR_PORNIT) if text is None else text},
			N, sesiune)
	if sesiune is None:
		return _cuStare({"result": False, "message": _t("Interfața web nu are încă legătura cu televizorul. Încearcă peste câteva secunde.")}, N, sesiune)
	if A.fel(a) == A.FEL_SCURTATURA and not N.instalat():
		return _cuStare({"result": False, "message": _t("Navigatorul lipsește din imaginea acestui receptor, deci nu se poate deschide pe televizor.")}, N, sesiune)
	if A.stareMagazin(a, N.catalog()) == A.CERE_WIDEVINE:
		# licenta Google se arata si se accepta pe televizor (instalatorul modulului)
		eroare = A.instaleazaWidevine(sesiune)
		if eroare:
			return _cuStare({"result": False, "message": _t(eroare)}, N, sesiune)
		return _cuStare({"result": True, "message": _t("Pe televizor s-a deschis instalarea modulului Widevine. Citește licența și acceptă-o acolo.")}, N, sesiune)
	if A.stareMagazin(a, N.catalog()) not in (A.INSTALAT, A.ACTUALIZARE):
		return _cuStare({"result": False, "message": _t("Aplicația nu e instalată.")}, N, sesiune)
	if N.navigatorDeschis():
		return _cuStare({"result": False, "message": _t("Pe televizor e deschis navigatorul sau altă aplicație. Închide-l întâi (EXIT).")}, N, sesiune)
	eroare = N.porneste(sesiune, a)
	if eroare:
		return _cuStare({"result": False, "message": _t(eroare)}, N, sesiune)
	return _cuStare({"result": True, "message": _t("Aplicația se deschide pe televizor.")}, N, sesiune)


def muta(argumente, N=None, sesiune=None):
	"""POST /api/aplicatii-tv-muta: un loc intre cele vazute, ca MENU pe televizor (schimbul cu vecinul vazut)."""
	N = _n(N)
	A = N.A
	id_ = argumente.get("id", "")
	vazute = [a["id"] for a in A.listaPentruOm(catalog=N.catalog())]
	try:
		pas = 1 if int(argumente.get("pas", "0")) > 0 else -1
	except ValueError:
		pas = 0
	if id_ not in vazute or not pas:
		return _cuStare({"result": False, "message": _t("Aplicația nu se poate muta.")}, N, sesiune)
	j = vazute.index(id_) + pas
	if j < 0 or j >= len(vazute):
		return _cuStare({"result": True, "message": ""}, N, sesiune)
	A.schimbaSiSalveaza(id_, vazute[j])
	return _cuStare({"result": True, "message": _t("Ordinea s-a salvat. Pe televizor e la fel.")}, N, sesiune)


def poza(id_, N=None):
	"""GET /api/aplicatii-tv-poza?id=...: poza cardului (numai calea data de HdsAplicatii.pozaPentru), sau None."""
	N = _n(N)
	a = N.A.gaseste(id_)
	cale = N.A.pozaPentru(a) if a is not None else None
	if not cale:
		return None
	try:
		with open(cale, "rb") as f:
			return f.read(4 * 1024 * 1024)
	except (IOError, OSError):
		return None


def ascunde(argumente, N=None, sesiune=None):
	"""POST /api/aplicatii-tv-ascunde."""
	N = _n(N)
	id_ = argumente.get("id", "")
	if N.A.gaseste(id_) is None:
		return _cuStare({"result": False, "message": _t("Aplicația nu există pe acest receptor.")}, N, sesiune)
	da = argumente.get("da", "1") != "0"
	N.A.ascundeSiSalveaza(id_, da)
	return _cuStare({"result": True, "message": _t("Aplicația e ascunsă din meniul de pe televizor.") if da else
		_t("Aplicația apare din nou în meniul de pe televizor.")}, N, sesiune)


def argumente(request, permise=("id", "pas", "da", "motor"), maxim=64):
	"""Argumentele cererii (adresa sau corpul formularului), fara token; numai cheile cunoscute."""
	rez = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v).strip()
	return rez


def rute(baza, resource, sesiune=None, N=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(N, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), N=N, sesiune=_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class DeschideResource(_Schimba):
		lucru = staticmethod(deschide)

	class MutaResource(_Schimba):
		lucru = staticmethod(muta)

	class AscundeResource(_Schimba):
		lucru = staticmethod(ascunde)

	class BrowserResource(_Schimba):
		lucru = staticmethod(browser)

	class PozaResource(baza):
		"""GET /api/aplicatii-tv-poza?id=...: poza cardului (PNG sau JPEG), dupa aceeasi poarta."""

		def render_GET(self, request):
			id_ = (request.args.get(b"id") or [b""])[0].decode("utf-8", "replace")[:40]
			date = poza(id_, N)
			if date is None:
				return self._eroare(request, _t("Aplicația nu are poză."), 404)
			request.setHeader(b"content-type", b"image/jpeg" if date[:3] == b"\xff\xd8\xff" else b"image/png")
			request.setHeader(b"cache-control", b"max-age=300")
			return date

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"aplicatii-tv": StareResource(),
		b"aplicatii-tv-deschide": DeschideResource(),
		b"aplicatii-tv-muta": MutaResource(),
		b"aplicatii-tv-ascunde": AscundeResource(),
		b"aplicatii-tv-browser": BrowserResource(),
		b"aplicatii-tv-poza": PozaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /navigator."""
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


def _limba():
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


ETICHETE = {
	"BROWSER": N_("Browserul aplicațiilor"),
	"TITLU": N_("Aplicații"),
	"INCARCARE": N_("Se citește lista..."),
	"NOTA": N_("Aplicațiile se deschid pe tot ecranul televizorului. Pe televizor: OK deschide, MENU arată mai multe, EXIT te întoarce în meniu."),
	"NEINSTALAT": N_("Navigatorul lipsește din imaginea acestui receptor, deci nu se poate deschide pe televizor."),
	"FARA": N_("Nicio aplicație instalată."),
}

NOTA_MENIU = N_("Aceeași listă e pe televizor, în %s.")

TEXTE_JS = {
	"browser": N_("Deschide cu..."),
	"deschide": N_("Deschide pe televizor"),
	"instaleaza": N_("Instalează"),
	"actualizeaza": N_("Actualizează"),
	"dezinstaleaza": N_("Dezinstalează"),
	"stanga": N_("Mută la stânga"),
	"dreapta": N_("Mută la dreapta"),
	"ascunde": N_("Ascunde"),
	"arata": N_("Arată din nou"),
	"ascunsa": N_("Ascunsă pe televizor"),
	"lucru": N_("Se lucrează: %s"),
	"catalog": N_("Se citește lista extensiilor..."),
	"widevine": N_("Instalează modulul Widevine pe televizor"),
	"navigator": N_("Instalează navigatorul web"),
}


def _json(obiect):
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


def pagina_text(stil, config_pagina):
	"""Pagina, cu stilul si scriptul comun al paginilor (meniu_comun_web.sablon: cererile, mesajul, confirmarea in doi
	pasi folosita de Instaleaza / Actualizeaza / Dezinstaleaza)."""
	import html
	try:
		from .meniu_comun_web import sablon
	except ImportError:   # probele de pe PC incarca modulul singur: fara stilul si scriptul comun
		def sablon(text, stil, config_pagina):
			return (text.replace("__STIL_COMUN__", stil).replace("__STIL_PAGINI__", "")
				.replace("__SCRIPT_COMUN__", "var CFG = " + config_pagina + ";"))
	text = PAGINA
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=False))
	nota = html.escape(_t(NOTA_MENIU), quote=False)
	nota = nota.replace("%s", _drumMeniu("hds_aplicatii"), 1) if "%s" in nota else nota
	text = (text.replace("__LIMBA__", _limba()).replace("__NOTA_MENIU__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items()))))
	return sablon(text, stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN____STIL_PAGINI__
  main{max-width:1100px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 6px;}
  .grila{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;}
  .app{background:var(--panou);border:1px solid var(--bordura);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;}
  .app.ascunsa{opacity:.55;}
  .poster{position:relative;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;
    font-size:1.5rem;letter-spacing:.04em;text-transform:uppercase;text-align:center;padding:8px;background-size:cover;background-position:center;}
  .poster .nume{position:absolute;left:0;right:0;bottom:0;padding:6px;background:rgba(0,0,0,.55);font-size:1.05rem;text-transform:none;letter-spacing:0;}
  .detalii{padding:10px 12px;display:flex;flex-direction:column;gap:6px;flex:1;}
  .stare{color:var(--text-slab);font-size:.82rem;}
  .stare.actualizare{color:#f5b83d;}
  .stare.disponibil{color:#4fd18b;}
  .descriere{font-size:.88rem;line-height:1.4;}
  .app .butoane{margin-top:auto;padding-top:6px;}
  button.albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="nota">__T_NOTA__</p>
<p id="browserGeneral" class="ascuns"><label>__T_BROWSER__ <select id="browserAles"></select></label></p>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<p class="mesaj ascuns eroare" id="neinstalat">__T_NEINSTALAT__</p>
<p class="mesaj" id="mesaj"></p>
<div class="butoane ascuns" id="imagineBara"><button type="button" id="imagine" class="principal"></button></div>
<p class="nota ascuns" id="lucrare"></p>
<div id="confirmare" class="card ascuns"></div>
<div class="grila" id="grila"></div>
<p class="nota ascuns" id="fara">__T_FARA__</p>
<p class="nota">__NOTA_MENIU__</p>
</main>
<script>
__SCRIPT_COMUN__
var TXT = __TEXTE_JS__;
var urmarire = null;
function trimite(cale, campuri){
  var q = new URLSearchParams();
  Object.keys(campuri).forEach(function(k){ q.set(k, campuri[k]); });
  cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); arata(d); }).catch(nimicNuRaspunde);
}
function citeste(){ cerere("/api/aplicatii-tv").then(arata).catch(nimicNuRaspunde); }
// instalarea, actualizarea si stergerea: rutele Extensiilor, cu confirmarea comuna; apoi lucrarea se urmareste aici
// 0.7.6 (EX2): cand aplicatia cere o versiune mai noua a imaginii, refuzul are "imagine" (legatura si textul butonului,
// ca in /extensii): sub mesaj apare butonul spre Actualizare software
var IMAGINE = "";
function arataImagine(x){ IMAGINE = x && x.legatura ? x.legatura : ""; $("imagineBara").classList.toggle("ascuns", !IMAGINE); if(IMAGINE){ $("imagine").textContent = x.text; } }
function opkg(ruta, pachet){
  var q = new URLSearchParams(); q.set("pachet", pachet);
  arataImagine(null);
  cuConfirmare(ruta, q, function(d){ arataImagine(d && d.imagine); citeste(); });
}
$("imagine").addEventListener("click", function(){ if(IMAGINE){ location.href = IMAGINE; } });
function buton(text, clasa, cand){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  if(clasa){ b.className = clasa; }
  b.addEventListener("click", cand); return b;
}
function alegeBrowser(select, alegeri, ales, id){
  select.textContent = "";
  alegeri.forEach(function(a){
    var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; select.appendChild(o);
  });
  select.value = alegeri.some(function(a){ return a[0] === ales; }) ? ales : (alegeri.length ? alegeri[0][0] : "");
  select.onchange = function(){
    var campuri = {motor: select.value}; if(id){ campuri.id = id; }
    trimite("/api/aplicatii-tv-browser", campuri);
  };
}
function arata(d){
  if(!d || !d.aplicatii){ return; }
  var alegeri = d.browsere || [];
  $("browserGeneral").classList.toggle("ascuns", !alegeri.length);
  alegeBrowser($("browserAles"), alegeri, d.browser || "");
  $("incarcare").classList.add("ascuns");
  $("neinstalat").classList.toggle("ascuns", d.instalat !== false);
  var l = d.lucrare, pl = $("lucrare");
  var w = d.widevine, wvLucru = !!(w && w.faza === "lucreaza");
  var inLucru = !!(l && l.faza === "lucru");
  pl.classList.toggle("ascuns", !inLucru && !wvLucru && d.catalog_gata !== false);
  pl.textContent = inLucru ? TXT.lucru.replace("%s", l.nume + (l.pas ? " (" + l.pas + ")" : "")) :
    wvLucru ? (w.mesaj || "") + (w.procent ? " " + w.procent + "%" : "") : (d.catalog_gata === false ? TXT.catalog : "");
  if(urmarire){ clearTimeout(urmarire); urmarire = null; }
  if(inLucru || wvLucru || d.catalog_gata === false){ urmarire = setTimeout(citeste, 2000); }
  var g = $("grila"); g.textContent = "";
  $("fara").classList.toggle("ascuns", d.aplicatii.length > 0);
  var vazute = d.vazute || [];
  d.aplicatii.forEach(function(a){
    var c = document.createElement("section"); c.className = "app" + (a.ascunsa ? " ascunsa" : "");
    var p = document.createElement("div"); p.className = "poster"; p.style.backgroundColor = a.culoare;
    if(a.poza){
      p.style.backgroundImage = "url('" + adresa("/api/aplicatii-tv-poza?id=" + encodeURIComponent(a.id)) + "')";
      var n = document.createElement("span"); n.className = "nume"; n.textContent = a.titlu; p.appendChild(n);
    } else { p.textContent = a.titlu; }
    var x = document.createElement("div"); x.className = "detalii";
    var s = document.createElement("div"); s.className = "stare " + (a.fel_stare || ""); s.textContent = a.ascunsa ? TXT.ascunsa : a.stare;
    var t = document.createElement("div"); t.className = "descriere"; t.textContent = a.descriere;
    if(a.browsere && a.browsere.length){
      var et = document.createElement("label"); et.textContent = TXT.browser + " ";
      var sel = document.createElement("select"); alegeBrowser(sel, a.browsere, a.browser || "", a.id);
      et.appendChild(sel); x.appendChild(et);
    }
    var b = document.createElement("div"); b.className = "butoane";
    (a.actiuni || []).forEach(function(act){
      var bt;
      if(act === "porneste"){ bt = buton(TXT.deschide, "albastru", function(){ trimite("/api/aplicatii-tv-deschide", {id: a.id}); }); }
      else if(act === "instaleaza"){ bt = buton(TXT.instaleaza, "verde", function(){ opkg("/api/extensii-instaleaza", a.pachet); }); }
      else if(act === "actualizeaza"){ bt = buton(TXT.actualizeaza, "verde", function(){ opkg("/api/extensii-actualizeaza", a.pachet); }); }
      else if(act === "instaleaza-navigator"){ bt = buton(TXT.navigator, "verde", function(){ trimite("/api/aplicatii-tv-deschide", {id: a.id}); }); }
      else if(act === "instaleaza-widevine"){ bt = buton(TXT.widevine, "verde", function(){ trimite("/api/aplicatii-tv-deschide", {id: a.id}); }); }
      else if(act === "dezinstaleaza"){ bt = buton(TXT.dezinstaleaza, "", function(){ opkg("/api/extensii-sterge", a.pachet); }); }
      if(bt){ bt.disabled = inLucru || (act === "porneste" && d.instalat === false && !a.pachet && !a.imagine); b.appendChild(bt); }
    });
    var i = vazute.indexOf(a.id);
    if(!a.ascunsa){
      var st = buton("\\u2190", "", function(){ trimite("/api/aplicatii-tv-muta", {id: a.id, pas: "-1"}); });
      st.title = TXT.stanga; st.setAttribute("aria-label", TXT.stanga); st.disabled = i <= 0;
      var dr = buton("\\u2192", "", function(){ trimite("/api/aplicatii-tv-muta", {id: a.id, pas: "1"}); });
      dr.title = TXT.dreapta; dr.setAttribute("aria-label", TXT.dreapta); dr.disabled = i < 0 || i >= vazute.length - 1;
      b.appendChild(st); b.appendChild(dr);
    }
    b.appendChild(buton(a.ascunsa ? TXT.arata : TXT.ascunde, "", function(){
      trimite("/api/aplicatii-tv-ascunde", {id: a.id, da: a.ascunsa ? "0" : "1"});
    }));
    x.appendChild(s); x.appendChild(t); x.appendChild(b);
    c.appendChild(p); c.appendChild(x); g.appendChild(c);
  });
}
citeste();
</script>
</body>
</html>
"""

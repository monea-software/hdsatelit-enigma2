# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# subtitrari_film_web.py: „Subtitrările filmului” in interfata web (HdsWebControl), perechea tastei SUB la un film
# redat din fisier (MKV, MP4, AVI).
#
# Pe televizor: tasta SUB in timpul filmului (Screens/AudioSelection.py, pagina subtitrarilor): pistele din film si
# fisierele de langa film, „Fără subtitrări”, intarzierea, codarea fisierului text si cadrele pe secunda (MicroDVD).
# Aici: aceleasi alegeri, din acelasi modul (Components/HdsSubtitrariFilm.py), cu tinerea minte pe film; la codare,
# primele trei replici cu codarea aleasa, ca sa se vada pe loc daca ă ș ț ies bine. Setarile implicite (codarea
# implicita, s t cu sedila -> ș ț, fisierul inaintea pistei, subdosarele) sunt in setup.xml (hds_subtitrari_filme), deci
# in pagina generala a setarilor.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/subtitrari-film                              filmul, subtitrarile, intarzierea, codarea, fps-ul
#   POST /api/subtitrari-film-alege?id=<fel-numar-tip-0>   o subtitrare (acelasi id ca in /piste), sau ?id=oprit
#   POST /api/subtitrari-film-intarziere?ms=N              intarzierea in ms (-600000..600000), sau ?pas=+/-N
#   POST /api/subtitrari-film-codare?cod=...[&numar=100]   codarea unui fisier text (implicit cel pornit)
#   POST /api/subtitrari-film-fps?fps=...[&numar=100]      cadrele pe secunda ale unui fisier MicroDVD
#   GET  /subtitrari-film                                  pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 si sunt scurte; recitirea unui fisier cu alta codare se face
# pe firul modulului, previzualizarea citeste numai inceputul fisierului (16 KB). Fisierul nu importa nimic din enigma2
# la incarcare: probele de pe PC dau modulele lor (F, L) si sesiunea lor.

MAX_TEXT = 60
INTARZIERE_MAX_MS = 600000
PRIMUL_FISIER = 100


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsSubtitrariFilm
	return HdsSubtitrariFilm


def _l(L=None):
	if L is not None:
		return L
	from Components import HdsPisteLimbi
	return HdsPisteLimbi


def id_subtitrare(t):
	"""Id-ul unei subtitrari in adresa: fel-numar-tip-0 (primele patru campuri ale tuplului, ca in /piste)."""
	try:
		return "-".join(["%d" % int(x) for x in t[:4]])
	except Exception:
		return ""


def _numeLimba(L, cod):
	try:
		c = L.limbaCanonica(cod)
		if c:
			return L.numeLimba(c)
	except Exception:
		pass
	return "" if cod in (None, "", "und") else cod


def stare(F=None, L=None, sesiune=None):
	"""GET /api/subtitrari-film: numai citire."""
	F = _f(F)
	L = _l(L)
	st = F.stare(sesiune)
	pornita = L.subtitrare_pornita(L.infobarActiv(sesiune))
	rez = {"result": True, "film": bool(st["film"]), "nume": st["nume"], "cautare_in_curs": bool(st["cautare_in_curs"]),
		"intarziere_ms": st["intarziere_ms"], "intarziere_text": F.textIntarziere(st["intarziere_ms"]), "subtitrari": [],
		"fara_subtitrari": pornita is None, "activ": st["activ"], "codare": st["codare"],
		"codare_gasita": _t(F.numeCodare(st["codare_gasita"])) if st["codare_gasita"] else "", "e_text": bool(st["e_text"]),
		"e_microdvd": bool(st["e_microdvd"]), "fps": st["fps"], "mesaj": st["mesaj"],
		"codari": [[c, _t(t)] for c, t in F.CODARI], "fps_alegeri": [[c, _t(t)] for c, t in F.FPS_ALEGERI]}
	if not st["film"]:
		return rez
	fisiere = dict((x["index"], x) for x in st["fisiere"])
	for t in F.tupluri():
		try:
			numar = int(t[1])
		except (TypeError, ValueError, IndexError):
			continue
		e = {"id": id_subtitrare(t), "numar": numar, "fisier": numar >= PRIMUL_FISIER, "format": F.eticheta(t),
			"limba": _numeLimba(L, t[4] if len(t) > 4 else ""), "nume": t[6] if len(t) > 6 else "",
			"surzi": bool(len(t) > 5 and t[5]), "forced": False, "pornita": L.aceeasiSubtitrare(t, pornita)}
		x = fisiere.get(numar)
		if x is not None:
			e["forced"] = x["forced"]
			e["replici"] = x["replici"]
			e["eroare"] = x["eroare"]
		rez["subtitrari"].append(e)
	return rez


def _cuMesaj(F, L, sesiune, reusit, mesaj):
	rez = stare(F, L, sesiune)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def _faraFilm(F, L, sesiune):
	return _cuMesaj(F, L, sesiune, False, _t("Acum nu rulează un film din fișier."))


def alege(argumente, F=None, L=None, sesiune=None):
	"""POST /api/subtitrari-film-alege?id=...: o subtitrare din lista de acum, sau „oprit” (fara subtitrari); se tine
	minte pe film, ca alegerea din tasta SUB."""
	F = _f(F)
	L = _l(L)
	if not F.stare(sesiune)["film"]:
		return _faraFilm(F, L, sesiune)
	id_ales = argumente.get("id", "")
	if id_ales == "oprit":
		reusit = L.alegeSubtitrareDeMana(sesiune, None)
		return _cuMesaj(F, L, sesiune, reusit, _t("Subtitrările sunt oprite la filmul acesta.") if reusit else
			_t("Subtitrarea nu s-a putut opri."))
	for t in F.tupluri():
		if id_subtitrare(t) == id_ales:
			reusit = L.alegeSubtitrareDeMana(sesiune, t)
			return _cuMesaj(F, L, sesiune, reusit, _t("Subtitrarea s-a schimbat.") if reusit else
				_t("Subtitrarea nu s-a putut alege."))
	return _cuMesaj(F, L, sesiune, False, _t("Subtitrarea nu există (poate s-a schimbat filmul)."))


def _intreg(text):
	try:
		return int(str(text).strip().replace("+", ""))
	except (TypeError, ValueError):
		return None


def intarziere(argumente, F=None, L=None, sesiune=None):
	"""POST /api/subtitrari-film-intarziere?ms=N sau ?pas=N: se aplica pe loc si se tine minte pe film."""
	F = _f(F)
	L = _l(L)
	if not F.stare(sesiune)["film"]:
		return _faraFilm(F, L, sesiune)
	if "ms" in argumente:
		ms = _intreg(argumente["ms"])
		if ms is None or abs(ms) > INTARZIERE_MAX_MS:
			return _cuMesaj(F, L, sesiune, False, _t("Întârzierea se scrie în milisecunde, între -600000 și 600000."))
		reusit, acum = F.alegeIntarziere(ms=ms)
	elif "pas" in argumente:
		pas = _intreg(argumente["pas"])
		if pas is None or abs(pas) > INTARZIERE_MAX_MS:
			return _cuMesaj(F, L, sesiune, False, _t("Pasul se scrie în milisecunde."))
		reusit, acum = F.alegeIntarziere(pas=pas)
	else:
		return _cuMesaj(F, L, sesiune, False, _t("Nu s-a trimis întârzierea."))
	if not reusit:
		return _cuMesaj(F, L, sesiune, False, _t("Întârzierea nu s-a putut schimba."))
	return _cuMesaj(F, L, sesiune, True, _t("Întârzierea este acum %s.") % F.textIntarziere(acum))


def _index(argumente, st):
	"""Fisierul la care se refera cererea: ?numar=100+i, altfel cel pornit. -> index (0, 1, ...) sau None."""
	if "numar" in argumente:
		n = _intreg(argumente["numar"])
		if n is None or n < PRIMUL_FISIER:
			return None
		return n - PRIMUL_FISIER
	if st["activ"] is None:
		return None
	return st["activ"] - PRIMUL_FISIER


def codare(argumente, F=None, L=None, sesiune=None):
	"""POST /api/subtitrari-film-codare?cod=...: recitirea fisierului text cu alta codare, plus primele trei replici."""
	F = _f(F)
	L = _l(L)
	st = F.stare(sesiune)
	if not st["film"]:
		return _faraFilm(F, L, sesiune)
	cod = argumente.get("cod", "")
	if cod not in dict(F.CODARI):
		return _cuMesaj(F, L, sesiune, False, _t("Codarea aceasta nu există."))
	i = _index(argumente, st)
	if i is None:
		return _cuMesaj(F, L, sesiune, False, _t("Codarea se alege numai la un fișier de subtitrare text de lângă film."))
	reusit = F.alegeCodare(cod, i)
	rez = _cuMesaj(F, L, sesiune, reusit, _t("Codarea s-a schimbat. Replicile se citesc din nou.") if reusit else
		_t("Codarea se alege numai la un fișier de subtitrare text de lângă film."))
	rez["previzualizare"] = F.previzualizare(cod, i) if reusit else []
	return rez


def fps(argumente, F=None, L=None, sesiune=None):
	"""POST /api/subtitrari-film-fps?fps=...: cadrele pe secunda ale unui fisier MicroDVD."""
	F = _f(F)
	L = _l(L)
	st = F.stare(sesiune)
	if not st["film"]:
		return _faraFilm(F, L, sesiune)
	valoare = argumente.get("fps", "")
	if valoare not in dict(F.FPS_ALEGERI):
		return _cuMesaj(F, L, sesiune, False, _t("Valoarea aceasta nu există."))
	i = _index(argumente, st)
	reusit = i is not None and F.alegeFps(valoare, i)
	return _cuMesaj(F, L, sesiune, reusit, _t("Cadrele pe secundă s-au schimbat.") if reusit else
		_t("Cadrele pe secundă se aleg numai la un fișier MicroDVD (.sub)."))


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = ("id", "ms", "pas", "cod", "numar", "fps")
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:12]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, sesiune=None, F=None, L=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2 (ecranul care are subtitrarile)."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/subtitrari-film: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(F, L, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), F=F, L=L, sesiune=_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class AlegeResource(_Schimba):
		lucru = staticmethod(alege)

	class IntarziereResource(_Schimba):
		lucru = staticmethod(intarziere)

	class CodareResource(_Schimba):
		lucru = staticmethod(codare)

	class FpsResource(_Schimba):
		lucru = staticmethod(fps)

	class PaginaResource(resource.Resource):
		"""GET /subtitrari-film: pagina „Subtitrările filmului”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"subtitrari-film": StareResource(),
		b"subtitrari-film-alege": AlegeResource(),
		b"subtitrari-film-intarziere": IntarziereResource(),
		b"subtitrari-film-codare": CodareResource(),
		b"subtitrari-film-fps": FpsResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /limbi si /piste."""
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
		_drumMeniu("hds_subtitrari_filme"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Subtitrările filmului</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .titlu{font-size:.98rem;word-break:break-word;}
  .detalii{color:var(--text-slab);font-size:.85rem;margin-top:2px;}
  .pornita{color:var(--verde);font-weight:bold;}
  select,input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  select{width:100%;}
  input{width:120px;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center;}
  .valoare{font-size:1.4rem;font-weight:bold;margin:0 0 6px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  ul.replici{margin:8px 0 0;padding-left:18px;line-height:1.5;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1>Subtitrările filmului</h1>
<p class="mesaj" id="incarcare">Se citește filmul de acum...</p>
<div id="faraFilm" class="ascuns">
  <section class="card">
    <p>Acum nu rulează un film din fișier (MKV, MP4, AVI). Subtitrările canalelor se aleg în pagina <a href="/piste">Sunet și subtitrări</a>.</p>
  </section>
</div>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Filmul de acum</h2>
    <p class="titlu" id="nume"></p>
    <p class="nota" id="cautare"></p>
  </section>
  <section class="card">
    <h2>Subtitrarea</h2>
    <div id="lista"></div>
    <div class="butoane"><button type="button" id="oprit">Fără subtitrări</button></div>
  </section>
  <section class="card">
    <h2>Întârzierea</h2>
    <p class="valoare" id="intarziere"></p>
    <div class="butoane">
      <button type="button" data-pas="-1000">&minus;1 s</button>
      <button type="button" data-pas="-100">&minus;0,1 s</button>
      <button type="button" data-ms="0">0</button>
      <button type="button" data-pas="100">+0,1 s</button>
      <button type="button" data-pas="1000">+1 s</button>
    </div>
    <div class="butoane">
      <label for="secunde">Secunde:</label>
      <input type="number" id="secunde" step="0.1" min="-600" max="600" inputmode="decimal">
      <button type="button" class="verde" id="pune">Pune</button>
    </div>
    <p class="nota">Pozitiv: subtitrarea apare mai târziu. Negativ: mai devreme. Se ține minte la filmul acesta. La textul din film, subtitrarea poate veni mai devreme numai cu puțin.</p>
  </section>
  <section class="card ascuns" id="cardCodare">
    <h2>Codarea fișierului</h2>
    <select id="codare"></select>
    <p class="nota" id="codareGasita"></p>
    <ul class="replici" id="previzualizare"></ul>
  </section>
  <section class="card ascuns" id="cardFps">
    <h2>Cadre pe secundă</h2>
    <select id="fps"></select>
    <p class="nota">Numai la fișierele MicroDVD (.sub cu cadre în loc de timp). Automat: din film sau din fișier.</p>
  </section>
  <section class="card ascuns" id="cardInternet">
    <h2>Subtitrări de pe internet</h2>
    <p><a id="spreInternet" href="/descarcare-subtitrari">Caută subtitrări pe internet</a> pentru filmul acesta.</p>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Pe televizor: tasta SUB în timpul filmului. Setările implicite sunt în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
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
function optiuni(sel, lista, valoare){
  sel.textContent = "";
  (lista || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
  sel.value = valoare;
}
function arata(d){
  DATE = d;
  $("incarcare").classList.add("ascuns");
  $("faraFilm").classList.toggle("ascuns", !!d.film);
  $("continut").classList.toggle("ascuns", !d.film);
  if(!d.film){ return; }
  $("nume").textContent = d.nume;
  $("cautare").textContent = d.cautare_in_curs ? "Se caută încă fișierele de subtitrare de lângă film..." : "";
  var l = $("lista"); l.textContent = "";
  if(!(d.subtitrari || []).length){
    var p = document.createElement("p"); p.className = "nota"; p.textContent = "Filmul nu are subtitrări, nici în film, nici în fișiere de lângă el."; l.appendChild(p);
  }
  (d.subtitrari || []).forEach(function(s){
    var r = document.createElement("div"); r.className = "rand";
    var st = document.createElement("div");
    var t = document.createElement("div"); t.className = "titlu";
    t.textContent = s.format + (s.nume ? "  " + s.nume : " din film, pista " + (s.numar + 1));
    var det = document.createElement("div"); det.className = "detalii";
    var parti = [];
    if(s.limba){ parti.push(s.limba); }
    if(s.surzi){ parti.push("pentru surzi"); }
    if(s.forced){ parti.push("numai replicile în altă limbă"); }
    if(s.eroare === "mare"){ parti.push("fișierul e prea mare"); }
    det.textContent = parti.join(", ");
    st.appendChild(t); st.appendChild(det);
    var b = document.createElement("button"); b.type = "button";
    if(s.pornita){ b.textContent = "Pornită"; b.disabled = true; b.className = "pornita"; }
    else { b.textContent = "Alege"; b.addEventListener("click", function(){ trimite("/api/subtitrari-film-alege", {id: s.id}); }); }
    r.appendChild(st); r.appendChild(b); l.appendChild(r);
  });
  $("oprit").disabled = !!d.fara_subtitrari;
  $("intarziere").textContent = d.intarziere_text;
  if(document.activeElement !== $("secunde")){ $("secunde").value = (d.intarziere_ms / 1000).toString(); }
  $("cardCodare").classList.toggle("ascuns", !d.e_text);
  if(d.e_text && document.activeElement !== $("codare")){
    optiuni($("codare"), d.codari, d.codare);
    $("codareGasita").textContent = d.codare_gasita ? ("Codarea citită acum: " + d.codare_gasita + "." + (d.mesaj ? " " + d.mesaj : "")) : "";
  }
  $("cardFps").classList.toggle("ascuns", !d.e_microdvd);
  if(d.e_microdvd && document.activeElement !== $("fps")){ optiuni($("fps"), d.fps_alegeri, d.fps); }
}
function citeste(){
  return cerere("/api/subtitrari-film").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi filmul."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, valori){
  var q = new URLSearchParams();
  Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  mesaj("Se trimite...");
  return cerere(cale, "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.film !== undefined){ arata(d); }
    var pv = $("previzualizare"); pv.textContent = "";
    (d.previzualizare || []).forEach(function(t){ var li = document.createElement("li"); li.textContent = t; pv.appendChild(li); });
    return d;
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
Array.prototype.forEach.call(document.querySelectorAll("button[data-pas]"), function(b){
  b.addEventListener("click", function(){ trimite("/api/subtitrari-film-intarziere", {pas: b.getAttribute("data-pas")}); });
});
Array.prototype.forEach.call(document.querySelectorAll("button[data-ms]"), function(b){
  b.addEventListener("click", function(){ trimite("/api/subtitrari-film-intarziere", {ms: b.getAttribute("data-ms")}); });
});
$("pune").addEventListener("click", function(){
  var v = parseFloat(($("secunde").value || "0").replace(",", "."));
  if(isNaN(v) || Math.abs(v) > 600){ mesaj("Scrie un număr de secunde între -600 și 600.", true); return; }
  trimite("/api/subtitrari-film-intarziere", {ms: Math.round(v * 1000)});
});
$("oprit").addEventListener("click", function(){ trimite("/api/subtitrari-film-alege", {id: "oprit"}); });
$("codare").addEventListener("change", function(){ trimite("/api/subtitrari-film-codare", {cod: $("codare").value}); });
$("fps").addEventListener("change", function(){ trimite("/api/subtitrari-film-fps", {fps: $("fps").value}); });
// pagina cautarii pe internet exista numai cu pachetul ei instalat: cardul apare doar cand ruta ei raspunde
cerere("/api/descarcare-subtitrari").then(function(d){
  if(d && d.result){
    $("spreInternet").href = adresa("/descarcare-subtitrari");
    $("cardInternet").classList.remove("ascuns");
  }
}).catch(function(){});
citeste();
setInterval(citeste, 5000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Subtitrările filmului"),
		N_("Se citește filmul de acum..."),
		N_("Acum nu rulează un film din fișier (MKV, MP4, AVI). Subtitrările canalelor se aleg în pagina <a "
			"href=\"/piste\">Sunet și subtitrări</a>."),
		N_("Filmul de acum"),
		N_("Subtitrarea"),
		N_("Fără subtitrări"),
		N_("Întârzierea"),
		N_("Secunde:"),
		N_("Pune"),
		N_("Pozitiv: subtitrarea apare mai târziu. Negativ: mai devreme. Se ține minte la filmul acesta. La "
			"textul din film, subtitrarea poate veni mai devreme numai cu puțin."),
		N_("Codarea fișierului"),
		N_("Cadre pe secundă"),
		N_("Numai la fișierele MicroDVD (.sub cu cadre în loc de timp). Automat: din film sau din fișier."),
		N_("Subtitrări de pe internet"),
		N_("<a id=\"spreInternet\" href=\"/descarcare-subtitrari\">Caută subtitrări pe internet</a> pentru "
			"filmul acesta."),
		N_("Pe televizor: tasta SUB în timpul filmului. Setările implicite sunt în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se caută încă fișierele de subtitrare de lângă film..."),
		N_("Filmul nu are subtitrări, nici în film, nici în fișiere de lângă el."),
		N_("din film, pista"),
		N_("pentru surzi"),
		N_("numai replicile în altă limbă"),
		N_("fișierul e prea mare"),
		N_("Pornită"),
		N_("Alege"),
		N_("Codarea citită acum:"),
		N_("Receptorul nu a putut citi filmul."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Scrie un număr de secunde între -600 și 600."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# intrari_web.py: trei ecrane de pe televizor in interfata web (HdsWebControl), paginile /dispozitive-intrare,
# /taste-rapide si /skin.
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor:
# - Meniu > Setari > Sistem & Dispozitive > Remote Control Setup (Screens/InputDeviceSetup.py): dispozitivele de intrare
#   (/dev/input/event*) si, pentru fiecare, "Change repeat and delay settings?", intervalul dintre taste la repetare si
#   intarzierea pana incepe repetarea (config.inputDevices.<dispozitiv>.*), cu intrebarea "Use this input device
#   settings?" la Verde. config.misc.rcused nu e un rand al ecranului (alege numai iconita), deci nu e nici aici. Ecranul
#   Telecomenzi (HdsTelecomenzi, /telecomenzi) e altul: pagina pune legatura spre el;
# - ... > Butoane colorate si taste rapide (Screens/ButtonSetup.py, HdsButtonSetup): VERDE apasat scurt si cele patru
#   butoane colorate (apasare lunga), aceleasi actiuni de ales (config.hds_buttons.*), salvate la fel; bara le
#   foloseste pe loc (Screens/InfoBar.py), fara semnul "in lucru";
# - Meniu > Setari > Interfata & Aspect > Aspectul ecranelor (Plugins/SystemPlugins/SkinSelector): skinurile instalate cu
#   previzualizarea lor (prev.png, servit numai pentru dosarele din lista), alegerea (config.skin.primary_skin, verificata
#   ca pe televizor: fisierul trebuie sa fie un skin; ecranele HD Satelit se scaleaza la rezolutia lui, iar la un skin
#   mai ingust de 1024 de puncte se spune ca literele lor sunt mici: HdsSkinuri.avertismentRezolutie) si intrebarea de
#   repornire a interfetei, apoi TryQuitMainloop 3, si aspectul meniului (tasta galbena, config.skin.layout_meniu);
#   skinul cu care merge interfata acum si, daca skinul ales nu a pornit, motivul intoarcerii pe HDSatelit
#   (Components/HdsSkinuri.py, pornirea sigura); legaturi spre /tema-tv si /culori-skin.
#
# O SINGURA LOGICA: Components/HdsDispozitiveIntrare.py, Components/HdsTasteRapide.py, Components/HdsSkinuri.py,
# folosite si de ecranele de pe televizor; repornirea interfetei: Components/HdsAlimentare.deschide (aceeasi cale ca
# intrarea "Restart Interface" din meniu, dupa 1,5 s, ca raspunsul sa plece inainte).
#
# Setarile unui dispozitiv de intrare si repornirea interfetei se fac in doi pasi (meniu_comun_web: intrebarea, apoi un
# cod de unica folosinta), numai din browserul conectat (nu cu ?token=), ca intrebarile de pe televizor.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/dispozitive-intrare                    dispozitivele si setarile lor, limitele din config
#   POST /api/dispozitive-intrare-seteaza?dispozitiv=eventN&activ=0|1&repetare=<ms>&intarziere=<ms>   (+ pas / cod)
#   GET  /api/taste-rapide                           butoanele (apasarea lunga), scurtele (VERDE scurt), actiunea
#                                                    fiecaruia, actiunile de ales
#   POST /api/taste-rapide-seteaza?red=&green=&yellow=&blue=&green_short=   o valoare straina nu schimba nimic
#   GET  /api/skin                                   skinurile (cautarea prin ${datadir}/enigma2 pe un fir), alegerea,
#                                                    aspectul meniului
#   GET  /api/skin-poza?nume=<skin>                  previzualizarea (PNG sau JPEG, cel mult 2 MiB)
#   POST /api/skin-alege?nume=<skin>                 ca OK pe ecran (se vede dupa repornirea interfetei)
#   POST /api/skin-aspect?aspect=lista|dale          ca tasta galbena
#   POST /api/skin-reporneste                        (+ pas / cod) repornirea interfetei
#   GET  /dispozitive-intrare, /taste-rapide, /skin  paginile
#
# FIRUL: totul pe firul enigma2 si scurt, afara de cautarea skinurilor (os.walk prin tot dosarul, pe un fir:
# meniu_comun_web.peFir). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC pun in DEP modulele,
# config, configfile, iInputDevices, radacina skinurilor, sesiunea si peFir.

MAX_POZA = 2 * 1024 * 1024
CHEI_DISPOZITIV = ("dispozitiv", "activ", "repetare", "intarziere", "pas", "cod")
TIPURI = ("remote", "keyboard", "mouse")

# ce dau probele de pe PC: "HdsDispozitiveIntrare", "HdsTasteRapide", "HdsSkinuri", "HdsAlimentare", "dispozitive"
# (iInputDevices), "config", "configfile", "radacina", "poza_lipsa", "sesiune", "peFir", "skinPornit" (functia care da
# skinul cu care a pornit interfata), "refuz" (fisierul refuzului din RAM)
DEP = {}

_STEAG_SKIN = [False]


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def _t(text):
	return _mc()._t(text)


def _dep(nume):
	if nume in DEP:
		return DEP[nume]
	if nume in ("HdsDispozitiveIntrare", "HdsTasteRapide", "HdsSkinuri", "HdsAlimentare"):
		return __import__("Components." + nume, fromlist=[nume])
	if nume == "dispozitive":
		from Components.InputDevice import iInputDevices
		return iInputDevices
	if nume == "config":
		from Components.config import config
		return config
	if nume == "configfile":
		from Components.config import configfile
		return configfile
	if nume == "radacina":
		return _dep("HdsSkinuri").radacina()
	if nume == "poza_lipsa":
		from Tools.Directories import resolveFilename, SCOPE_PLUGINS
		return resolveFilename(SCOPE_PLUGINS, _dep("HdsSkinuri").POZA_LIPSA)
	if nume == "sesiune":
		return _mc().sesiune()
	if nume == "peFir":
		return _mc().peFir
	if nume == "skinPornit":
		return _dep("HdsSkinuri").skinPornit
	if nume == "refuz":
		return None      # fisierul din RAM al lui HdsSkinuri (REFUZ)
	raise KeyError(nume)


def _alegeri(el):
	"""[[valoare, text]] dintr-o setare ConfigSelection (aceleasi alegeri ca pe televizor, traduse acolo)."""
	alegeri = el.choices.choices
	if not isinstance(alegeri, list):
		alegeri = list(alegeri.items())
	rez = []
	for x in alegeri:
		if isinstance(x, tuple):
			rez.append([str(x[0]), str(x[1]) if x[1] else str(x[0])])
		else:
			rez.append([str(x), str(x)])
	return rez


def _doiPasi(request, argumente, actiune, tinta, intrebare, buton, detalii, fapta):
	mc = _mc()
	refuz = mc.numaiBrowser(request)
	if refuz:
		return {"result": False, "message": refuz}
	if argumente.get("pas") == "renunta":
		mc.uita(actiune, tinta)
		return {"result": True, "message": _t("Nu s-a schimbat nimic.")}
	cod = argumente.get("cod")
	if cod:
		if not mc.verifica(actiune, tinta, cod):
			return mc.codGresit()
		return fapta()
	return mc.raspunsIntrebare(actiune, tinta, intrebare, buton, detalii)


# ------------------------------------------------------------------ dispozitivele de intrare

def _glisor(el):
	return [int(el.min), int(el.max), int(el.increment or 1)]


def stareDispozitive():
	"""Pentru GET /api/dispozitive-intrare."""
	HD = _dep("HdsDispozitiveIntrare")
	D = _dep("dispozitive")
	config = _dep("config")
	rez = []
	for x, nume, tip in HD.lista(D, config):
		s = HD.sectiune(x, config)
		rez.append({"dispozitiv": x, "nume": nume, "tip": tip if tip in TIPURI else "",
			"activ": bool(s.enabled.value), "repetare": int(s.repeat.value), "intarziere": int(s.delay.value),
			"repetare_limite": _glisor(s.repeat), "intarziere_limite": _glisor(s.delay)})
	return {"result": True, "dispozitive": rez}


def _ms(text, el):
	"""Numarul de milisecunde, daca e unul din pasii glisorului de pe televizor, altfel None."""
	if text is None or not text.isdigit() or len(text) > 6:
		return None
	n = int(text)
	minim, maxim, pas = _glisor(el)
	if n < minim or n > maxim or (n - minim) % pas:
		return None
	return n


def seteazaDispozitiv(request):
	"""POST /api/dispozitive-intrare-seteaza: ca Verde si Da pe ecranul dispozitivului."""
	HD = _dep("HdsDispozitiveIntrare")
	D = _dep("dispozitive")
	config = _dep("config")
	a = _mc().argumente(request, CHEI_DISPOZITIV, 20)
	x = a.get("dispozitiv", "")
	s = HD.sectiune(x, config)
	if s is None or x not in [d for d, _n, _t2 in HD.lista(D, config)]:
		return {"result": False, "message": _t("Dispozitivul %s nu există pe receptor.") % x[:20]}
	if a.get("activ") not in ("0", "1"):
		return {"result": False, "message": _t("Se alege cu activ=1 sau activ=0.")}
	activ = a["activ"] == "1"
	repetare = intarziere = None
	if activ:
		for cheie, el in (("repetare", s.repeat), ("intarziere", s.delay)):
			if cheie in a:
				n = _ms(a[cheie], el)
				if n is None:
					minim, maxim, pas = _glisor(el)
					return {"result": False, "message": _t("Valoarea %s ms nu e bună: se alege între %d și %d ms, din %d în %d.")
						% (a[cheie][:8], minim, maxim, pas, pas)}
				if cheie == "repetare":
					repetare = n
				else:
					intarziere = n
	tinta = "%s|%d|%s|%s" % (x, activ, repetare, intarziere)
	nume = D.getDeviceName(x)

	def fapta():
		HD.aplica(x, activ, repetare, intarziere, D, config, _dep("configfile"))
		rez = stareDispozitive()
		rez.update(result=True, message=_t("Salvat."))
		return rez

	return _doiPasi(request, a, "dispozitive-intrare", tinta, _t("Use this input device settings?"), _t("Da, folosește-le"),
		[_t("Dispozitivul: %s") % nume], fapta)


# ------------------------------------------------------------------ butoanele colorate

def stareTaste():
	"""Pentru GET /api/taste-rapide: "butoane" = apasarea lunga a celor patru, "scurte" = VERDE apasat scurt; aceleasi
	actiuni de ales pentru toate."""
	TR = _dep("HdsTasteRapide")
	b = TR.initConfigButtonSetup(_dep("config"))
	butoane = [{"cheie": k, "text": text, "valoare": getattr(b, k).value} for k, text in TR.BUTOANE]
	scurte = [{"cheie": k, "text": text, "valoare": getattr(b, k).value} for k, text in TR.SCURTE]
	return {"result": True, "butoane": butoane, "scurte": scurte, "actiuni": _alegeri(getattr(b, TR.BUTOANE[0][0]))}


def seteazaTaste(request):
	"""POST /api/taste-rapide-seteaza: ca Verde pe ecran. Toate valorile trimise trebuie sa fie bune."""
	TR = _dep("HdsTasteRapide")
	config = _dep("config")
	b = TR.initConfigButtonSetup(config)
	chei = [k for k, _text in TR.BUTOANE + TR.SCURTE]
	a = _mc().argumente(request, chei, 20)
	if not a:
		rez = stareTaste()
		rez.update(result=False, message=_t("Nu s-a trimis nicio setare."))
		return rez
	noi = []
	for k in chei:
		if k in a:
			el = getattr(b, k)
			if a[k] not in [x[0] for x in _alegeri(el)]:
				rez = stareTaste()
				rez.update(result=False, message=_t("Acțiunea %s nu există.") % a[k][:20])
				return rez
			noi.append((el, a[k]))
	for el, v in noi:
		el.value = v
	TR.salveaza(config)
	_dep("configfile").save()
	rez = stareTaste()
	rez.update(result=True, message=_t("Salvat."))
	return rez


# ------------------------------------------------------------------ skinul

def stareSkin(skinuri, ales, aspect, aspecte, activ=None, refuz=None):
	"""Corpul raspunsului GET /api/skin, din lista citita pe fir si din setarile citite pe firul enigma2."""
	S = _dep("HdsSkinuri")
	activ = activ or S.DOSAR_IMAGINE
	return {"result": True,
		"skinuri": [{"nume": x, "eticheta": _t("Skinul implicit") if x == S.IMPLICIT else x,
			"ales": x == ales or (ales is None and x == S.IMPLICIT), "activ": x == activ,
			"imaginii": x == S.DOSAR_IMAGINE} for x in skinuri],
		"aspect": aspect, "aspecte": aspecte, "activ": activ, "refuz": refuz or ""}


def _aspecte(config):
	text = {"lista": _t("Listă"), "dale": _t("Dale")}
	return [[v, text.get(v, t)] for v, t in _alegeri(config.skin.layout_meniu)]


def cereSkin(request):
	"""GET /api/skin: setarile pe firul enigma2, cautarea skinurilor pe un fir."""
	S = _dep("HdsSkinuri")
	config = _dep("config")
	if _STEAG_SKIN[0]:
		return {"result": False, "message": _t("Lista skinurilor se citește deja. Încearcă din nou peste câteva secunde.")}
	ales = S.curent(config)
	aspect = S.aspect(config)
	aspecte = _aspecte(config)
	radacina = _dep("radacina")
	activ = S.numeDinValoare(_dep("skinPornit")()) or S.DOSAR_IMAGINE
	refuz = S.textRefuz(S.citesteRefuz(_dep("refuz")), _t)
	return _dep("peFir")(request, lambda: stareSkin(S.lista(radacina), ales, aspect, aspecte, activ, refuz), _STEAG_SKIN,
		20)


def _numeSkin(a):
	S = _dep("HdsSkinuri")
	nume = a.get("nume", "")
	if S.caleSkin(_dep("radacina"), nume) is None:
		return None
	return nume


def pozaSkin(a):
	"""(octetii, felul) sau (None, motivul)."""
	S = _dep("HdsSkinuri")
	nume = _numeSkin(a)
	if nume is None:
		return None, _t("Skinul nu există.")
	cale = S.previzualizare(_dep("radacina"), nume, _dep("poza_lipsa"))
	try:
		with open(cale, "rb") as f:
			date = f.read(MAX_POZA + 1)
	except (IOError, OSError):
		return None, _t("Previzualizarea lipsește.")
	if len(date) > MAX_POZA:
		return None, _t("Previzualizarea nu e bună.")
	if date[:8] == b"\x89PNG\r\n\x1a\n":
		return date, b"image/png"
	if date[:3] == b"\xff\xd8\xff":
		return date, b"image/jpeg"
	return None, _t("Previzualizarea nu e bună.")


def alegeSkin(request):
	"""POST /api/skin-alege: ca OK pe ecran (aceeasi verificare a fisierului, acelasi avertisment de rezolutie)."""
	S = _dep("HdsSkinuri")
	a = _mc().argumente(request, ("nume",), 120)
	nume = _numeSkin(a)
	if nume is None:
		return {"result": False, "message": _t("Skinul nu există.")}
	bun, mesaj, avertisment = S.alege(nume, _dep("config"), _dep("radacina"), _t, _dep("refuz"))
	if not bun:
		return {"result": False, "message": mesaj}
	_dep("configfile").save()
	return {"result": True, "message": (avertisment + " " + mesaj) if avertisment else mesaj, "avertisment": avertisment,
		"reporneste": True}


def aspectMeniu(request):
	"""POST /api/skin-aspect: ca tasta galbena (aspectul meniului)."""
	S = _dep("HdsSkinuri")
	config = _dep("config")
	a = _mc().argumente(request, ("aspect",), 12)
	v = a.get("aspect", "")
	if v not in [x[0] for x in _alegeri(config.skin.layout_meniu)]:
		return {"result": False, "message": _t("Se alege aspect=lista sau aspect=dale.")}
	S.seteazaAspect(v, config)
	_dep("configfile").save()
	return {"result": True, "message": _t("Salvat."), "aspect": S.aspect(config)}


def reporneste(request):
	"""POST /api/skin-reporneste: Da pe intrebarea de pe televizor (TryQuitMainloop 3), cu codul."""
	A = _dep("HdsAlimentare")
	sesiune = _dep("sesiune")
	a = _mc().argumente(request, ("pas", "cod"), 40)
	detalii = []
	try:
		if A.vaIntreba(sesiune):
			detalii.append(_t("Pe televizor se cere o confirmare: o înregistrare e în curs sau începe curând. Repornirea "
				"se face numai dacă răspunzi Da acolo."))
	except Exception as eroare:
		_mc().jurnal("skin: %r" % eroare)

	def fapta():
		if not A.deschide(sesiune, "interfata", dupa_ms=1500):
			return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
		return {"result": True, "reporneste": True,
			"message": _t("Interfața se repornește. Pagina se reîncarcă singură în câteva secunde.")}

	return _doiPasi(request, a, "skin-reporneste", "", _t("GUI needs a restart to apply a new skin\nDo you want to Restart "
		"the GUI now?"), _t("Da, repornește interfața"), detalii, fapta)


# ------------------------------------------------------------------ rutele si paginile

def rute(baza, resource):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	def _eroare(self, request, eroare):
		_mc().jurnal("intrari: %r" % eroare)
		return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def _citire(functie):
		class Citire(baza):
			def render_GET(self, request):
				try:
					rez = functie(request)
				except Exception as eroare:
					return _eroare(self, request, eroare)
				if not isinstance(rez, dict):
					return rez          # NOT_DONE_YET: raspunsul pleaca de pe fir
				return self._raspunde(request, rez)
		return Citire()

	def _scriere(functie):
		class Scriere(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					return _eroare(self, request, eroare)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Scriere()

	class Poza(baza):
		def render_GET(self, request):
			try:
				date, fel = pozaSkin(_mc().argumente(request, ("nume",), 120))
			except Exception as eroare:
				return _eroare(self, request, eroare)
			if date is None:
				return self._eroare(request, fel, 404)
			request.setHeader(b"content-type", fel)
			request.setHeader(b"cache-control", b"private, max-age=3600")
			return date

	def _pagina(text):
		class Pagina(resource.Resource):
			isLeaf = True

			def render_GET(self, request):
				return _mc().pagina(request, text)
		return Pagina()

	api = {
		b"dispozitive-intrare": _citire(lambda r: stareDispozitive()),
		b"dispozitive-intrare-seteaza": _scriere(seteazaDispozitiv),
		b"taste-rapide": _citire(lambda r: stareTaste()),
		b"taste-rapide-seteaza": _scriere(seteazaTaste),
		b"skin": _citire(cereSkin),
		b"skin-poza": Poza(),
		b"skin-alege": _scriere(alegeSkin),
		b"skin-aspect": _scriere(aspectMeniu),
		b"skin-reporneste": _scriere(reporneste),
	}
	pagini = {
		b"dispozitive-intrare": _pagina(pagina_dispozitive),
		b"taste-rapide": _pagina(pagina_taste),
		b"skin": _pagina(pagina_skin),
	}
	return api, pagini


def _sablon(text, stil, config_pagina, intrare):
	mc = _mc()
	return mc.sablon(text, stil, config_pagina, {"__DRUM_MENIU__": mc.drumHtml(intrare)})


def pagina_dispozitive(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_DISPOZITIVE), stil, config_pagina, "input_device_setup")


def pagina_taste(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_TASTE), stil, config_pagina, "hds_button_setup")


def pagina_skin(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_SKIN), stil, config_pagina, "skin_setup")


PAGINA_DISPOZITIVE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dispozitive de intrare</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
  .glisor{display:flex;align-items:center;gap:10px;}
  .glisor input{flex:1;min-width:0;}
  .glisor output{min-width:72px;text-align:right;}
</style>
</head>
<body>
<main>
<h1>Dispozitive de intrare</h1>
<p class="sub">Telecomenzile, tastaturile și mouse-urile găsite de receptor la pornire. Pentru fiecare se poate schimba cât de repede se repetă o tastă ținută apăsat.</p>
<p class="mesaj" id="incarcare">Se citesc dispozitivele...</p>
<div id="continut" class="ascuns">
  <div id="lista"></div>
  <p class="nota ascuns" id="gol">Receptorul n-a găsit niciun dispozitiv de intrare la pornire.</p>
  <section class="card">
    <h2>Telecomenzi</h2>
    <p class="nota">Codurile tastelor, proba tastelor și folosirea altei telecomenzi au pagina lor.</p>
    <div class="butoane"><button type="button" id="spreTelecomenzi">Deschide Telecomenzi</button></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var TIP = {remote: "telecomandă", keyboard: "tastatură", mouse: "mouse"};
function rand(cutie, eticheta, control, id){
  var r = document.createElement("div"); r.className = "rand";
  var l = document.createElement("label"); l.textContent = eticheta; l.htmlFor = id; r.appendChild(l);
  r.appendChild(control); cutie.appendChild(r); return r;
}
function glisor(id, valoare, limite){
  var d = document.createElement("div"); d.className = "glisor";
  var i = document.createElement("input"); i.type = "range"; i.id = id;
  i.min = limite[0]; i.max = limite[1]; i.step = limite[2]; i.value = valoare;
  var o = document.createElement("output"); o.textContent = valoare + " ms";
  i.addEventListener("input", function(){ o.textContent = i.value + " ms"; });
  d.appendChild(i); d.appendChild(o); return d;
}
function card(x){
  var c = document.createElement("section"); c.className = "card";
  var h = document.createElement("h2"); h.textContent = x.nume; c.appendChild(h);
  var n = document.createElement("p"); n.className = "nota"; n.textContent = (TIP[x.tip] || "alt dispozitiv") + " · " + x.dispozitiv; c.appendChild(n);
  var s = document.createElement("select"); s.id = "activ-" + x.dispozitiv;
  [["1", "Da"], ["0", "Nu"]].forEach(function(v){ var o = document.createElement("option"); o.value = v[0]; o.textContent = v[1]; s.appendChild(o); });
  s.value = x.activ ? "1" : "0";
  rand(c, "Schimbi intervalul și întârzierea repetării?", s, s.id);
  var r1 = rand(c, "Intervalul dintre taste la repetare", glisor("repetare-" + x.dispozitiv, x.repetare, x.repetare_limite), "repetare-" + x.dispozitiv);
  var r2 = rand(c, "Întârzierea până începe repetarea", glisor("intarziere-" + x.dispozitiv, x.intarziere, x.intarziere_limite), "intarziere-" + x.dispozitiv);
  function vizibile(){ var da = s.value === "1"; r1.classList.toggle("ascuns", !da); r2.classList.toggle("ascuns", !da); }
  s.addEventListener("change", vizibile); vizibile();
  var b = document.createElement("div"); b.className = "butoane";
  var salv = document.createElement("button"); salv.type = "button"; salv.className = "principal"; salv.textContent = "Salvează";
  salv.addEventListener("click", function(){
    var q = new URLSearchParams(); q.set("dispozitiv", x.dispozitiv); q.set("activ", s.value);
    if(s.value === "1"){ q.set("repetare", $("repetare-" + x.dispozitiv).value); q.set("intarziere", $("intarziere-" + x.dispozitiv).value); }
    cuConfirmare("/api/dispozitive-intrare-seteaza", q, function(d){ if(d.result && d.dispozitive){ arata(d); } });
  });
  var inapoi = document.createElement("button"); inapoi.type = "button"; inapoi.textContent = "Pune înapoi valorile salvate";
  inapoi.addEventListener("click", function(){ mesaj(""); citeste(); });
  b.appendChild(salv); b.appendChild(inapoi); c.appendChild(b);
  var a = document.createElement("p"); a.className = "nota";
  a.textContent = "Cu Nu, intervalul și întârzierea se întorc la valorile din fabrică.";
  c.appendChild(a);
  return c;
}
function arata(d){
  var l = $("lista"); l.textContent = "";
  (d.dispozitive || []).forEach(function(x){ l.appendChild(card(x)); });
  $("gol").classList.toggle("ascuns", (d.dispozitive || []).length > 0);
}
function citeste(){
  return cerere("/api/dispozitive-intrare").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi dispozitivele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("spreTelecomenzi").addEventListener("click", function(){ location.href = adresa("/telecomenzi"); });
citeste();
</script>
</body>
</html>
"""


PAGINA_TASTE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Butoane colorate și taste rapide</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
</style>
</head>
<body>
<main>
<h1>Butoane colorate și taste rapide</h1>
<p class="sub">Alege ce face VERDE apăsat scurt și ce se deschide la apăsarea lungă a fiecărui buton colorat, cât te uiți la televizor.</p>
<p class="mesaj" id="incarcare">Se citesc butoanele...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Apăsarea scurtă</h2>
    <div id="scurte"></div>
    <p class="nota">Pe un canal cu subcanale, VERDE scurt arată întâi lista lor.</p>
  </section>
  <section class="card">
    <h2>Apăsarea lungă</h2>
    <div id="butoane"></div>
  </section>
  <div class="butoane">
    <button type="button" class="principal" id="salveaza">Salvează</button>
    <button type="button" id="renunta">Renunță</button>
  </div>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var D = null;
function randuri(c, lista, actiuni){
  c.textContent = "";
  lista.forEach(function(b){
    var r = document.createElement("div"); r.className = "rand";
    var l = document.createElement("label"); l.htmlFor = "b-" + b.cheie; l.textContent = b.text; r.appendChild(l);
    var s = document.createElement("select"); s.id = "b-" + b.cheie;
    actiuni.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    s.value = b.valoare; r.appendChild(s); c.appendChild(r);
  });
}
function toate(){ return D.butoane.concat(D.scurte || []); }
function arata(d){
  D = d;
  randuri($("scurte"), d.scurte || [], d.actiuni);
  randuri($("butoane"), d.butoane, d.actiuni);
}
function citeste(){
  return cerere("/api/taste-rapide").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi butoanele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("salveaza").addEventListener("click", function(){
  var q = new URLSearchParams();
  toate().forEach(function(b){ q.set(b.cheie, $("b-" + b.cheie).value); });
  mesaj("Se salvează...");
  cerere("/api/taste-rapide-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.butoane){ arata(d); } }).catch(nimicNuRaspunde);
});
$("renunta").addEventListener("click", function(){ mesaj("Nu s-a schimbat nimic."); citeste(); });
citeste();
</script>
</body>
</html>
"""


PAGINA_SKIN = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aspectul ecranelor</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .sub{color:var(--text-slab);margin:0 0 14px;font-size:.92rem;line-height:1.45;}
  .skinuri{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:0 0 12px;}
  .skinuri .card{margin:0;display:flex;flex-direction:column;gap:8px;}
  .skinuri .card.ales{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
  .cap{display:flex;justify-content:space-between;align-items:baseline;gap:10px;}
  .cap h2{margin:0;}
  .eticheta{font-size:.78rem;color:var(--text-slab);white-space:nowrap;}
  .poza{width:100%;aspect-ratio:16/9;object-fit:contain;border-radius:8px;display:block;}
</style>
</head>
<body>
<main>
<h1>Aspectul ecranelor</h1>
<p class="sub">Skinurile instalate pe receptor. Skinul ales se vede pe televizor după repornirea interfeței.</p>
<p class="mesaj" id="incarcare">Se caută skinurile...</p>
<div id="continut" class="ascuns">
  <p class="mesaj eroare ascuns" id="refuz"></p>
  <div class="skinuri" id="skinuri"></div>
  <section class="card">
    <h2>Aspectul meniului</h2>
    <div class="rand">
      <label for="aspect">Meniul ca</label>
      <select id="aspect"></select>
    </div>
  </section>
  <section class="card">
    <h2>Tema și culorile</h2>
    <p class="nota">Tema skinului HD Satelit (Clasic sau Pro) și culorile lui au paginile lor.</p>
    <div class="butoane">
      <button type="button" id="spreTema">Tema interfeței</button>
      <button type="button" id="spreCulori">Culorile skinului</button>
    </div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Skinul ales se încarcă la pornirea interfeței. Ecranele pe care skinul ales nu le are (cele ale receptorului HD Satelit) vin din skinul HD Satelit, potrivite la rezoluția skinului ales, deci încap întregi, cu culorile și literele lor; pe un skin mai îngust de 1024 de puncte (720x576) literele lor sunt mici. Dacă skinul ales nu pornește (lipsește, e stricat sau interfața se oprește cu el), receptorul revine singur la skinul HD Satelit și spune de ce, aici și pe televizor. Tema Clasic sau Pro e numai a skinului HD Satelit. Meniul rămâne deocamdată listă. Același ecran e pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
function arata(d){
  var c = $("skinuri"); c.textContent = "";
  d.skinuri.forEach(function(x){
    var card = document.createElement("section"); card.className = "card" + (x.ales ? " ales" : "");
    var cap = document.createElement("div"); cap.className = "cap";
    var h = document.createElement("h2"); h.textContent = x.eticheta; cap.appendChild(h);
    var e = document.createElement("span"); e.className = "eticheta";
    e.textContent = x.ales && x.activ ? "ales, pe ecran acum" : (x.ales ? "ales, după repornire" : (x.activ ? "pe ecran până la repornire" : ""));
    cap.appendChild(e);
    card.appendChild(cap);
    var img = document.createElement("img"); img.className = "poza"; img.alt = "Previzualizarea skinului " + x.eticheta;
    img.src = adresa("/api/skin-poza?nume=" + encodeURIComponent(x.nume));
    img.addEventListener("error", function(){ img.classList.add("ascuns"); });
    card.appendChild(img);
    var b = document.createElement("button"); b.type = "button"; b.className = x.ales ? "" : "principal";
    b.textContent = x.ales ? "Alege din nou" : "Alege acest skin";
    b.addEventListener("click", function(){ alege(x.nume); });
    var bs = document.createElement("div"); bs.className = "butoane"; bs.appendChild(b); card.appendChild(bs);
    c.appendChild(card);
  });
  $("refuz").textContent = d.refuz || "";
  $("refuz").classList.toggle("ascuns", !d.refuz);
  var s = $("aspect");
  if(document.activeElement !== s){
    s.textContent = "";
    (d.aspecte || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
    s.value = d.aspect;
  }
}
function citeste(){
  return cerere("/api/skin").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi skinurile."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function alege(nume){
  var q = new URLSearchParams(); q.set("nume", nume);
  mesaj("Se salvează...");
  cerere("/api/skin-alege", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(!d.result){ return; }
    citeste();
    cuConfirmare("/api/skin-reporneste", new URLSearchParams(), function(r){
      if(r.result && r.reporneste){ setTimeout(function(){ location.reload(); }, 15000); }
    });
    // cuConfirmare goleste mesajul: avertismentul (literele mici) si "se vede dupa repornire" raman scrise
    mesaj(d.message, false);
  }).catch(nimicNuRaspunde);
}
$("aspect").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("aspect", $("aspect").value);
  mesaj("Se salvează...");
  cerere("/api/skin-aspect", "POST", q).then(function(d){ mesaj(d.message, !d.result); }).catch(nimicNuRaspunde);
});
$("spreTema").addEventListener("click", function(){ location.href = adresa("/tema-tv"); });
$("spreCulori").addEventListener("click", function(){ location.href = adresa("/culori-skin"); });
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
		N_("Dispozitive de intrare"),
		N_("Telecomenzile, tastaturile și mouse-urile găsite de receptor la pornire. Pentru fiecare se "
			"poate schimba cât de repede se repetă o tastă ținută apăsat."),
		N_("Se citesc dispozitivele..."),
		N_("Receptorul n-a găsit niciun dispozitiv de intrare la pornire."),
		N_("Telecomenzi"),
		N_("Codurile tastelor, proba tastelor și folosirea altei telecomenzi au pagina lor."),
		N_("Deschide Telecomenzi"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("Butoane colorate și taste rapide"),
		N_("Alege ce face VERDE apăsat scurt și ce se deschide la apăsarea lungă a fiecărui buton colorat, cât te "
			"uiți la televizor."),
		N_("Se citesc butoanele..."),
		N_("Apăsarea scurtă"),
		N_("Pe un canal cu subcanale, VERDE scurt arată întâi lista lor."),
		N_("Apăsarea lungă"),
		N_("Salvează"),
		N_("Renunță"),
		N_("Aspectul ecranelor"),
		N_("Skinurile instalate pe receptor. Skinul ales se vede pe televizor după repornirea interfeței."),
		N_("Se caută skinurile..."),
		N_("Aspectul meniului"),
		N_("Meniul ca"),
		N_("Tema și culorile"),
		N_("Tema skinului HD Satelit (Clasic sau Pro) și culorile lui au paginile lor."),
		N_("Tema interfeței"),
		N_("Culorile skinului"),
		N_("Skinul ales se încarcă la pornirea interfeței. Ecranele pe care skinul ales nu le are (cele ale "
			"receptorului HD Satelit) vin din skinul HD Satelit, potrivite la rezoluția skinului ales, deci "
			"încap întregi, cu culorile și literele lor; pe un skin mai îngust de 1024 de puncte (720x576) "
			"literele lor sunt mici. Dacă skinul ales nu pornește (lipsește, e stricat sau interfața se "
			"oprește cu el), receptorul revine singur la skinul HD Satelit și spune de ce, aici și pe "
			"televizor. Tema Clasic sau Pro e numai a skinului HD Satelit. Meniul rămâne deocamdată listă. "
			"Același ecran e pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("telecomandă"),
		N_("tastatură"),
		N_("alt dispozitiv"),
		N_("Da"),
		N_("Nu"),
		N_("Schimbi intervalul și întârzierea repetării?"),
		N_("Intervalul dintre taste la repetare"),
		N_("Întârzierea până începe repetarea"),
		N_("Salvează"),
		N_("Pune înapoi valorile salvate"),
		N_("Cu Nu, intervalul și întârzierea se întorc la valorile din fabrică."),
		N_("Receptorul nu a putut citi dispozitivele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Receptorul nu a putut citi butoanele."),
		N_("Se salvează..."),
		N_("Nu s-a schimbat nimic."),
		N_("ales, pe ecran acum"),
		N_("ales, după repornire"),
		N_("pe ecran până la repornire"),
		N_("Previzualizarea skinului"),
		N_("Alege din nou"),
		N_("Alege acest skin"),
		N_("Receptorul nu a putut citi skinurile."),
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

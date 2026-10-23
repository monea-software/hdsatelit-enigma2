# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# piste.py: „Sunet și subtitrări” in interfata web (HdsWebControl).
#
# Orice ecran sau alegere facuta pe receptor are pereche in
# interfata web. Afisajul detaliat (a doua bara, pagina 3) lasa acum alegerea pistei audio, a subtitrarii, a canalului
# audio si a downmix-ului; aici sunt aceleasi liste si aceleasi alegeri, din browser.
#
# O SINGURA LOGICA: listele si alegerile vin din Components/Converter/HdsCommon.py, exact ce foloseste afisajul de pe
# televizor: aceleasi liste (Reader.track_list / sub_list, deci acelasi numar de pista), aceleasi functii de alegere
# (piste_alege_audio, piste_alege_subtitrare, piste_alege_canal), care cheama modulul imaginii Components/HdsPisteLimbi.py
# (tine minte alegerea facuta de mana pe canal). Dupa o alegere, daca afisajul e deschis pe televizor, se redeseneaza
# (HdsCommon.page_refresh), ca semnul sa se mute si acolo.
#
# Rute (toate prin poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat;
# ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/piste                          listele si starea
#   POST /api/pista-audio?index=N
#   POST /api/subtitrare?id=<fel-pid-pagina-magazin> sau ?id=oprit
#   POST /api/canal-audio?n=0|1|2            stanga, stereo, dreapta
#   POST /api/downmix?tip=ac3|dts&pornit=0|1
#   GET  /piste                              pagina
# Teletextul si HbbTV nu se deschid din web (sunt ecrane pe televizor); pagina spune doar daca exista.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 (reactorul e bucla enigma2), apelurile sunt scurte si
# directe, fara fire. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau un HdsCommon fals.


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


MAX_TEXT = 40


def _hc(C=None):
	if C is not None:
		return C
	from Components.Converter import HdsCommon
	return HdsCommon


def _serviciu():
	"""(serviciul redat, proprietarul subtitrarilor: bara InfoBar sau MoviePlayer). Oricare poate fi None."""
	service = prop = None
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		service = nav.getCurrentService() if nav is not None else None
	except Exception:
		service = None
	try:
		# la o inregistrare, ecranul din fata e MoviePlayer, cu subtitrarile lui (InfoBarSubtitleSupport)
		from Screens.InfoBar import InfoBar
		prop = InfoBar.instance
		fata = prop.session.current_dialog if prop is not None else None
		if fata is not None and fata is not prop and hasattr(fata, "subtitle_window") and hasattr(fata, "secondInfoBarScreen"):
			prop = fata
	except Exception:
		prop = None
	return service, prop


class _Sursa(object):
	__slots__ = ("service",)

	def __init__(self, service):
		self.service = service


def id_subtitrare(e):
	"""Id-ul unei subtitrari in adresa: fel-pid-pagina-magazin (primele patru campuri ale tuplului)."""
	try:
		return "-".join(["%d" % int(x) for x in e[:4]])
	except Exception:
		return ""


def stare(C=None, service=None, prop=None, cu_serviciu=True):
	"""Listele si starea, pentru GET /api/piste."""
	C = _hc(C)
	if cu_serviciu:
		service, prop = _serviciu()
	rez = {"result": True, "activ": service is not None, "audio": [], "subtitrari": [], "fara_subtitrari": True,
		"canal_audio": None, "downmix_ac3": None, "downmix_dts": None, "hbbtv_semnalat": False, "teletext": False}
	if service is None:
		return rez
	r = C.Reader(_Sursa(service), None)
	rows, cur = r.track_list()
	for i, (codec, limba, pid) in enumerate(rows):
		rez["audio"].append({"index": i, "codec": codec, "limba": limba, "pid": pid, "pornita": i == cur})
	subs, scur = r.sub_list()
	for e in subs:
		pornita = C.same_sub(e, scur)
		try:
			fel = int(e[0])
		except Exception:
			fel = -1
		rez["subtitrari"].append({"id": id_subtitrare(e), "tip": fel, "text": C.sub_text(e),
			"limba": C.language_name(e[4]) if len(e) > 4 else "", "pornita": pornita})
	rez["fara_subtitrari"] = scur is None
	rez["canal_audio"] = C.piste_canal(service)
	ex = C.sel_extras(r)
	for tip in ("ac3", "dts"):
		c = C._cfg_downmix(tip) if tip in ex else None
		rez["downmix_" + tip] = bool(c.value) if c is not None else None
	# HbbTV: aceeasi sursa ca afisajul de pe televizor (HdsCommon.hbbtv_semnalat: nucleul cu sHBBTVUrl, altfel baza
	# pistelor, Components/HdsPisteCanale.py); None = nu se stie. Inainte: mereu „nu”
	# pe imaginea HDSatelit, al carei nucleu nu citeste AIT-ul.
	semnalat = getattr(C, "hbbtv_semnalat", None)
	rez["hbbtv_semnalat"] = semnalat(r) if semnalat is not None else bool(r.gets("sHBBTVUrl"))
	rez["teletext"] = r.geti("sTXTPID") > 0
	return rez


def _dupa(C, ok, mesaj_ok, mesaj_rau):
	if ok:
		try:
			C.page_refresh()
		except Exception:
			pass
	return {"result": bool(ok), "message": mesaj_ok if ok else mesaj_rau}


def alege_audio(index, C=None, service=None, cu_serviciu=True):
	C = _hc(C)
	if cu_serviciu:
		service = _serviciu()[0]
	try:
		index = int(index)
	except Exception:
		return {"result": False, "message": _t("Pista audio nu e un număr.")}
	if service is None:
		return {"result": False, "message": _t("Nu rulează niciun canal.")}
	rows = C.Reader(_Sursa(service), None).track_list()[0]
	if not 0 <= index < len(rows):
		return {"result": False, "message": _t("Pista audio nu există (poate s-a schimbat canalul).")}
	return _dupa(C, C.piste_alege_audio(service, index), _t("Pista audio aleasă."), _t("Pista audio nu s-a putut "
		"alege."))


def alege_subtitrare(id_ales, C=None, service=None, prop=None, cu_serviciu=True):
	C = _hc(C)
	if cu_serviciu:
		service, prop = _serviciu()
	if service is None:
		return {"result": False, "message": _t("Nu rulează niciun canal.")}
	if id_ales == "oprit":
		t = None
	else:
		subs = C.Reader(_Sursa(service), None).sub_list()[0]
		t = None
		for e in subs:
			if id_subtitrare(e) == id_ales:
				t = e
				break
		if t is None:
			return {"result": False, "message": _t("Subtitrarea nu există (poate s-a schimbat canalul).")}
	return _dupa(C, C.piste_alege_subtitrare(prop, t), _t("Subtitrările s-au schimbat."), _t("Subtitrarea nu s-a putut "
		"alege."))


def alege_canal(n, C=None, service=None, cu_serviciu=True):
	C = _hc(C)
	if cu_serviciu:
		service = _serviciu()[0]
	try:
		n = int(n)
	except Exception:
		n = -1
	if n not in (0, 1, 2):
		return {"result": False, "message": _t("Canalul audio e 0 (stânga), 1 (stereo) sau 2 (dreapta).")}
	if service is None or C.piste_canal(service) is None:
		return {"result": False, "message": _t("Canalul audio nu se poate alege aici.")}
	return _dupa(C, C.piste_alege_canal(service, n), _t("Canalul audio s-a schimbat."), _t("Canalul audio nu s-a putut "
		"schimba."))


def alege_downmix(tip, pornit, C=None, service=None, cu_serviciu=True):
	C = _hc(C)
	if cu_serviciu:
		service = _serviciu()[0]
	if tip not in ("ac3", "dts"):
		return {"result": False, "message": _t("Downmix-ul e ac3 sau dts.")}
	if pornit not in ("0", "1"):
		return {"result": False, "message": _t("pornit trebuie să fie 0 sau 1.")}
	c = C._cfg_downmix(tip)
	if service is None or c is None or tip not in C.sel_extras(C.Reader(_Sursa(service), None)):
		return {"result": False, "message": _t("Receptorul nu are această alegere.")}
	if bool(c.value) == (pornit == "1"):
		return {"result": True, "message": _t("Era deja așa.")}
	return _dupa(C, C.alege_extra(service, tip), "Downmix-ul s-a schimbat.", _t("Downmix-ul nu s-a putut schimba."))


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, C=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class PisteResource(baza):
		"""GET /api/piste: listele si starea. Numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(C))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True

		def fa(self, a):
			raise NotImplementedError

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.fa(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PistaAudioResource(_Schimba):
		def fa(self, a):
			return alege_audio(a.get("index", ""), C)

	class SubtitrareResource(_Schimba):
		def fa(self, a):
			return alege_subtitrare(a.get("id", ""), C)

	class CanalAudioResource(_Schimba):
		def fa(self, a):
			return alege_canal(a.get("n", ""), C)

	class DownmixResource(_Schimba):
		def fa(self, a):
			return alege_downmix(a.get("tip", ""), a.get("pornit", ""), C)

	class PaginaResource(resource.Resource):
		"""GET /piste: pagina „Sunet și subtitrări”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"piste": PisteResource(),
		b"pista-audio": PistaAudioResource(),
		b"subtitrare": SubtitrareResource(),
		b"canal-audio": CanalAudioResource(),
		b"downmix": DownmixResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /scanare: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Pagina schimba ceva pe receptor, deci cu cookie primeste tokenul CSRF."""
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
<title>Sunet și subtitrări</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card h2{font-size:1rem;margin:0 0 10px;}
  .lista{display:grid;grid-template-columns:1fr;gap:8px;}
  .lista button{min-height:44px;padding:10px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;text-align:left;cursor:pointer;}
  .lista button[aria-pressed="true"]{border-color:var(--accent);box-shadow:inset 6px 0 0 var(--accent);}
  .lista button[disabled]{opacity:.5;cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Sunet și subtitrări</h1>
<p class="mesaj" id="incarcare">Se citește canalul...</p>
<div id="continut" class="ascuns">
  <section class="card"><h2>Sunet</h2><div class="lista" id="audio"></div></section>
  <section class="card"><h2>Subtitrări</h2><div class="lista" id="subtitrari"></div></section>
  <section class="card" id="card-alte"><h2>Alte alegeri</h2><div class="lista" id="alte"></div>
    <p class="nota" id="info"></p></section>
  <p class="nota ascuns" id="film">Acum rulează un film din fișier: fișierele de subtitrare de lângă el, întârzierea și codarea sunt în pagina <a id="spreFilm" href="/subtitrari-film">Subtitrările filmului</a>.</p>
  <p class="nota">Alegerea făcută aici e aceeași cu cea din afișajul detaliat de pe televizor (tasta OK de două ori, apoi pagina „Video, audio”) și rămâne ținută minte pentru canalul acesta.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
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
function goleste(e){ while(e.firstChild){ e.removeChild(e.firstChild); } }
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function buton(parinte, text, pornit, actiune){
  var b = document.createElement("button");
  b.type = "button";
  b.textContent = text;
  b.setAttribute("aria-pressed", pornit ? "true" : "false");
  b.addEventListener("click", actiune);
  parinte.appendChild(b);
  return b;
}
function trimite(cale, p){
  mesaj("Se schimbă...");
  cerere(cale, "POST", p).then(function(d){ mesaj(d.message, !d.result); citeste(); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
var CANALE = ["Stânga", "Stereo", "Dreapta"];
function deseneaza(d){
  var a = $("audio"), s = $("subtitrari"), x = $("alte");
  goleste(a); goleste(s); goleste(x);
  if(!d.activ){ $("incarcare").textContent = "Nu rulează niciun canal."; $("incarcare").classList.remove("ascuns"); $("continut").classList.add("ascuns"); return; }
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  if(!d.audio.length){ var n = document.createElement("p"); n.className = "nota"; n.textContent = "Nicio pistă audio."; a.appendChild(n); }
  d.audio.forEach(function(p){
    var t = [p.codec, p.limba, p.pid > 0 ? "PID " + p.pid : ""].filter(Boolean).join(" · ");
    buton(a, t || ("Pista " + (p.index + 1)), p.pornita, function(){
      var q = new URLSearchParams(); q.set("index", p.index); trimite("/api/pista-audio", q);
    });
  });
  buton(s, "Fără subtitrări", d.fara_subtitrari, function(){
    var q = new URLSearchParams(); q.set("id", "oprit"); trimite("/api/subtitrare", q);
  });
  d.subtitrari.forEach(function(p){
    buton(s, p.text || p.id, p.pornita, function(){
      var q = new URLSearchParams(); q.set("id", p.pornita ? "oprit" : p.id); trimite("/api/subtitrare", q);
    });
  });
  var alte = 0;
  if(d.canal_audio !== null){
    alte++;
    CANALE.forEach(function(nume, i){
      buton(x, "Canal audio: " + nume, d.canal_audio === i, function(){
        var q = new URLSearchParams(); q.set("n", i); trimite("/api/canal-audio", q);
      });
    });
  }
  ["ac3", "dts"].forEach(function(tip){
    if(d["downmix_" + tip] === null){ return; }
    alte++;
    var pornit = d["downmix_" + tip];
    buton(x, "Downmix " + tip.toUpperCase() + ": " + (pornit ? "pornit" : "oprit"), pornit, function(){
      var q = new URLSearchParams(); q.set("tip", tip); q.set("pornit", pornit ? "0" : "1"); trimite("/api/downmix", q);
    });
  });
  var hb = d.hbbtv_semnalat === true ? "da" : (d.hbbtv_semnalat === false ? "nu" : "nu se știe");
  $("info").textContent = "HbbTV semnalat: " + hb + " · Teletext: " + (d.teletext ? "da" : "nu");
}
function citeste(){
  cerere("/api/piste").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi canalul."; return; }
    deseneaza(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
  // cat merge un film din fisier, legatura spre pagina lui (subtitrari_film_web.py)
  cerere("/api/subtitrari-film").then(function(d){
    $("film").classList.toggle("ascuns", !(d && d.film));
  }).catch(function(){});
}
$("spreFilm").href = adresa("/subtitrari-film");
citeste();
setInterval(function(){ if(!document.hidden){ citeste(); } }, 5000);
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
		N_("Sunet și subtitrări"),
		N_("Se citește canalul..."),
		N_("Sunet"),
		N_("Subtitrări"),
		N_("Alte alegeri"),
		N_("Acum rulează un film din fișier: fișierele de subtitrare de lângă el, întârzierea și codarea "
			"sunt în pagina <a id=\"spreFilm\" href=\"/subtitrari-film\">Subtitrările filmului</a>."),
		N_("Alegerea făcută aici e aceeași cu cea din afișajul detaliat de pe televizor (tasta OK de două "
			"ori, apoi pagina „Video, audio”) și rămâne ținută minte pentru canalul acesta."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se schimbă..."),
		N_("Receptorul nu răspunde."),
		N_("Stânga"),
		N_("Stereo"),
		N_("Dreapta"),
		N_("Nu rulează niciun canal."),
		N_("Nicio pistă audio."),
		N_("Pista"),
		N_("Fără subtitrări"),
		N_("Canal audio:"),
		N_("Downmix"),
		N_("nu se știe"),
		N_("HbbTV semnalat:"),
		N_("· Teletext:"),
		N_("Receptorul nu a putut citi canalul."),
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

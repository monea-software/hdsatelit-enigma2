# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# accel_web.py: „Accelerare 2D pe placa video” in interfata web (HdsWebControl).
#
# Pereche web a setarii de pe televizor: Meniu > Setari > Interfata si aspect > Setari generale
# (setup.xml „usage”, config.usage.hds_accel_2d). Aici: aceeasi setare, plus ce a hotarat interfata la pornire (starea
# reala scrisa de lib/gdi/accel.cpp in /tmp/hds-accel.stare) si repornirea interfetei, ca schimbarea sa se vada.
# Pagina web e si drumul de scapare cand accelerarea strica imaginea de pe televizor: se opreste de aici, fara
# meniurile de pe ecran.
#
# O SINGURA LOGICA: Components/HdsAccel2D.py (fisierul de oprire /etc/enigma2/hds-fara-accel, starea, textele). Ca pe
# televizor: implicit pornita; pe un receptor fara accelerarea 2D (disponibila() fals) setarea nu se poate schimba,
# pagina spune ca nu exista, iar legatura spre /accel nu apare in panou si in /ecrane (faraLegaturaDacaLipseste,
# chemata din plugin.py).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/accel                         setarea (pentru urmatoarea pornire) si starea reala de acum
#   POST /api/accel-seteaza?pornita=0|1     schimba si salveaza setarea (se aplica la urmatoarea pornire a interfetei)
#   POST /api/accel-reporneste              reporneste interfata (enigma2), ca la Meniu > Standby si repornire
#   GET  /accel                             pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte. Fisierul nu importa nimic din
# enigma2 la incarcare: probele de pe PC dau modulul lor (M).


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsAccel2D
	return HdsAccel2D


def stare(M=None):
	"""Pentru GET /api/accel."""
	M = _m(M)
	return {
		"result": True,
		"disponibila": M.disponibila(),
		"pornita_in_setari": M.pornita_in_setari(),
		"acum": M.stare(),
	}


def seteaza(argumente, M=None):
	"""POST /api/accel-seteaza?pornita=0|1: pune setarea din enigma2 (daca exista) si fisierul, salvate."""
	M = _m(M)
	valoare = argumente.get("pornita")
	if valoare not in ("0", "1"):
		rez = stare(M)
		rez.update({"result": False, "message": _t("Se alege cu pornita=1 sau pornita=0.")})
		return rez
	if not M.disponibila():
		# ca pe televizor, unde randul nu se arata: nimic de schimbat pe un receptor fara accelerarea 2D
		rez = stare(M)
		rez.update({"result": False, "message": _t("Accelerarea 2D nu există pe acest receptor.")})
		return rez
	pornita = valoare == "1"
	element = None
	try:
		from Components.config import config
		element = getattr(config.usage, "hds_accel_2d", None)
	except Exception:
		element = None
	if element is not None:
		# notificarea setarii pune sau scoate fisierul; salvarea o face si pe disc
		element.value = pornita
		element.save()
		try:
			from Components.config import configfile
			configfile.save()
		except Exception:
			pass
	reusit = M.seteaza(pornita)
	rez = stare(M)
	if not reusit or M.pornita_in_setari() != pornita:
		rez.update({"result": False, "message": _t("Setarea nu s-a putut salva pe receptor.")})
		return rez
	rez.update({"result": True, "message": _t("Salvat. Se aplică la următoarea pornire a interfeței.")})
	return rez


LEGATURA = '<a href="/accel">Accelerare 2D pe placa video</a>'


def faraLegaturaDacaLipseste(pagina, M=None):
	"""Panoul si /ecrane: legatura spre /accel ramane numai pe un receptor cu accelerarea 2D (regula:
	meniul si web-ul arata doar ce exista); aceeasi hotarare ca randul din setup.xml (requires)."""
	try:
		if _m(M).disponibila():
			return pagina
	except Exception as eroare:
		print("[accel_web] disponibila: %s" % eroare)
	# dupa adresa, nu dupa text: pagina e tradusa in limba receptorului
	import re
	legatura = r'<a href="%s">[^<]*</a>' % re.escape(re.search(r'href="([^"]+)"', LEGATURA).group(1))
	return re.sub(legatura, "", re.sub("  " + legatura + "\n", "", pagina))


def reporneste(sesiune):
	"""POST /api/accel-reporneste: TryQuitMainloop(3), ca din meniul de oprire (pe televizor poate intreba ceva
	daca o inregistrare e in curs)."""
	if sesiune is None:
		return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
	from Screens.Standby import TryQuitMainloop
	sesiune.open(TryQuitMainloop, 3)
	return {"result": True, "message": _t("Interfața se repornește. Pagina se reîncarcă singură în câteva secunde.")}


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:6]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:8].strip()
	return rez


def rute(baza, resource, M=None, sesiune=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py;
	`sesiune` e o functie care intoarce sesiunea enigma2 (plugin._sesiune se pune abia la pornirea sesiunii)."""

	class StareResource(baza):
		"""GET /api/accel: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
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

	class SeteazaResource(_Schimba):
		def fa(self, a):
			return seteaza(a, M)

	class ReporniresResource(_Schimba):
		def fa(self, a):
			return reporneste(sesiune() if sesiune else None)

	class PaginaResource(resource.Resource):
		"""GET /accel: pagina „Accelerare 2D pe placa video”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"accel": StareResource(),
		b"accel-seteaza": SeteazaResource(),
		b"accel-reporneste": ReporniresResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /subtitrari: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
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
	return cuSemn(pagina_text(P._STIL_COMUN, config_pagina), P._caleSetup()).encode("utf-8", "replace")


TITLU = "Accelerare 2D pe placa video"


def cuSemn(text, cale_setup):
	"""titlul paginii poarta semnul randului din setup.xml (stare=, „(netestat)” pana la proba
	pe receptor), ca pe televizor (Screens/Setup.py si Components/HdsStareMeniu.py)."""
	try:
		from Components import HdsStareMeniu
		s = HdsStareMeniu.stareSetare(cale_setup, "config.usage.hds_accel_2d")
	except Exception as eroare:
		print("[accel_web] semnul: %s" % eroare)
		return text
	if not s:
		return text
	# pagina e deja tradusa (TITLU e unul din TEXTE_PAGINA): titlul si semnul in limba ei
	titlu = _t(TITLU)
	semn = HdsStareMeniu.cuSemn(titlu, s, _t)
	return text.replace("<h1>%s</h1>" % titlu, "<h1>%s</h1>" % semn).replace("<title>%s</title>" % titlu,
		"<title>%s</title>" % semn)


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("usage_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accelerare 2D pe placa video</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,220px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 0;}
  .butoane button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .acum{font-size:1rem;line-height:1.45;margin:0;}
  .detalii{color:var(--text-slab);font-size:.82rem;margin:8px 0 0;line-height:1.45;word-break:break-word;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Accelerare 2D pe placa video</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="acum" id="acum"></p>
    <p class="detalii" id="detalii"></p>
  </section>
  <div id="alegere">
  <section class="card">
    <div class="rand">
      <label for="alege">La următoarea pornire a interfeței</label>
      <select id="alege"><option value="1">Pornită</option><option value="0">Oprită</option></select>
    </div>
  </section>
  <div class="butoane"><button type="button" id="reporneste">Repornește interfața acum</button></div>
  <p class="nota">Pornită implicit: umplerile mari de pe ecran se fac pe placa video, restul desenului rămâne pe procesor. Dacă apar probleme, receptorul trece singur pe desenul fără accelerare. Dacă imaginea de pe televizor arată totuși greșit, alege „Oprită” și repornește interfața. Aceeași setare este pe televizor, în __DRUM_MENIU__.</p>
  </div>
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
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function arata(d){
  $("alegere").classList.toggle("ascuns", !d.disponibila);
  $("alege").value = d.pornita_in_setari ? "1" : "0";
  $("acum").textContent = "Acum: " + (d.acum && d.acum.text ? d.acum.text : "necunoscut");
  $("detalii").textContent = d.acum && d.acum.detalii ? d.acum.detalii : "";
}
function citeste(){
  return cerere("/api/accel").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("alege").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("pornita", $("alege").value);
  mesaj("Se salvează...");
  cerere("/api/accel-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.acum){ arata(d); } })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
$("reporneste").addEventListener("click", function(){
  if(!window.confirm("Repornești interfața receptorului acum? Imaginea se oprește câteva secunde.")){ return; }
  mesaj("Se repornește...");
  cerere("/api/accel-reporneste", "POST", new URLSearchParams()).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ setTimeout(function(){ location.reload(); }, 25000); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
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
		N_("Accelerare 2D pe placa video"),
		N_("Se citește starea..."),
		N_("La următoarea pornire a interfeței"),
		N_("Pornită"),
		N_("Oprită"),
		N_("Repornește interfața acum"),
		N_("Pornită implicit: umplerile mari de pe ecran se fac pe placa video, restul desenului rămâne pe "
			"procesor. Dacă apar probleme, receptorul trece singur pe desenul fără accelerare. Dacă imaginea "
			"de pe televizor arată totuși greșit, alege „Oprită” și repornește interfața. Aceeași setare "
			"este pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Acum:"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează..."),
		N_("Receptorul nu răspunde."),
		N_("Repornești interfața receptorului acum? Imaginea se oprește câteva secunde."),
		N_("Se repornește..."),
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

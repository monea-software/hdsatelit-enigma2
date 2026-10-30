# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# asistenta_web.py: Asistenta de la distanta in interfata web (HdsWebControl), perechea ecranului de pe receptor
# (Screens/HdsAsistenta.py), pentru oricine. Aceeasi stare, aceleasi texte si acelasi jurnal, din
# Components/HdsAsistenta.py; in meniul web e randul /asistenta din Setari (data/menu.xml).
# Pagina de pornire are numai randul scurt (A.TEXT_SCURT), randul bifat dinainte "Accept termenii și condițiile" (in
# fraza, chiar cuvintele "termenii și condițiile" sunt legatura care deschide textul intreg, A.textTermeni, intr-o
# fereastra peste pagina) si butonul Start. Pornita, pagina arata numai pana cand e pornita, butonul Oprește si
# jurnalul. Codul sesiunii nu se trimite browserului: ramane intern, intre receptor, server si echipa. Cand echipa a
# trimis concluzii (op "concluzii"), pagina le arata sub jurnal, si dupa oprire: "Ce am găsit și ce am făcut", textul
# si multumirile (A.stareConcluzii).
# Start dintr-un browser conectat cu codul de pe receptor (acelasi nivel asociat ca la Acces SSH) porneste pe loc
# (Screens/HdsAsistentaSemn.pornesteWeb). Dintr-un browser fara cod (orice aparat din reteaua locala) deschide pe
# receptor aceeasi pagina de pornire si porneste numai Start apasat acolo (HdsAsistentaSemn.cerereWeb): altfel orice
# aparat din casa ar putea da acces la receptor fara stirea omului. Oprirea merge din orice browser din reteaua
# locala (a opri nu primejduieste pe nimeni). Cat asistenta e activa, paginile web au sus o banda (bandaWeb, pusa de
# meniu_comun_web.pagina).
#
# Rute (poarta comuna meniu_comun_web; ce schimba ceva cere, cu cookie, POST si antetul CSRF):
#   GET  /api/asistenta            starea, pana cand e pornita, ultimele randuri din jurnal (fara cod), ultimele
#                                  concluzii ale echipei
#   GET  /api/asistenta-catalog    lista operatiilor in limba receptorului
#   POST /api/asistenta-cere?accept=1   Start (accept=1: randul "Accept termenii și condițiile" bifat)
#   POST /api/asistenta-opreste    opreste
#   GET  /asistenta                pagina
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (A).

def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAsistenta
	return HdsAsistenta


def _asociat(request):
	"""True daca cererea vine dintr-un browser conectat cu codul de pe receptor (Start porneste atunci pe loc)."""
	try:
		from . import acces_ssh_web
		return acces_ssh_web.nivel(request) == "asociat"
	except Exception:
		return False


def stare(request=None, A=None, B=None):
	"""Starea pentru pagina (si pentru banda): fara codul sesiunii, care ramane intern."""
	A = _a(A)
	s = A.stare()
	return {"result": True, "stare": s.get("stare"), "disponibil": s.get("disponibil"),
		"ramas_s": s.get("ramas_s", 0), "jurnal": s.get("jurnal", []), "nivel": s.get("nivel"),
		"durata_implicita": s.get("durata_implicita"),
		# pana cand e pornita, tradus ("Pornită până la ZZ.LL, HH:MM." / "Pornită, fără sfârșit; ...")
		"permanent": bool(s.get("permanent")), "pana_text": s.get("pana_text") or "",
		"concluzii": _concluzii(A)}


def _concluzii(A):
	"""Ultimele concluzii ale echipei ({"text", "ora_text"}) sau None; un modul vechi fara ele da None."""
	try:
		return A.stareConcluzii()
	except Exception:
		return None


def catalog(A=None):
	A = _a(A)
	try:
		from Components import HdsAsistentaCatalog as C
		return {"result": True, "operatii": [{"op": op, "grup": _t(grup), "fel": fel, "text": _t(text)}
			for (op, grup, fel, text) in C.pentru_afisare()]}
	except Exception as e:
		return {"result": False, "message": _t("Nu pot citi catalogul: %s") % e}


def cere(argumente, A=None, B=None, de_incredere=False):
	"""Start din pagina: numai cu randul bifat (accept=1). Browser de incredere: porneste pe loc; altfel deschide
	pagina de pornire pe receptor."""
	A = _a(A)
	if str(argumente.get("accept", "")) != "1":
		rez = stare(None, A)
		rez.update({"result": False, "message": _t(A.TEXT_FARA_BIFA)})
		return rez
	try:
		from Screens import HdsAsistentaSemn as Semn
		from .meniu_comun_web import sesiune
		if de_incredere:
			reusit, mesaj = Semn.pornesteWeb(sesiune())
		else:
			reusit, mesaj = Semn.cerereWeb(sesiune())
	except Exception as e:
		reusit, mesaj = False, _t("Eroare pe receptor: %s") % e
	rez = stare(None, A)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def opreste(A=None):
	A = _a(A)
	reusit, mesaj = A.opreste("de om (web)")
	rez = stare(None, A)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


# butonul "Oprește" al benzii web: opreste direct (POST /api/asistenta-opreste, cu tokenul CSRF al paginii, din CFG,
# pus de scriptul fiecarei pagini); o pagina fara CFG duce la /asistenta, unde e butonul de oprire
_OPRESTE_BANDA = ("var c=window.CFG||{};if(!c.csrf&&!c.jeton){location.href='/asistenta';return false;}"
	"var h={};if(c.csrf){h['X-HDS-CSRF']=c.csrf;}"
	"fetch('/api/asistenta-opreste'+(c.jeton?'?token='+encodeURIComponent(c.jeton):''),"
	"{method:'POST',credentials:'same-origin',cache:'no-store',headers:h})"
	".then(function(){location.reload();},function(){location.href='/asistenta';});return false;")


def bandaWeb(A=None):
	"""Banda pusa sus pe paginile web cat asistenta e activa (HTML gata, tradus), sau "" cand nu e: ca e pornita si pana
	cand ("până la ZZ.LL, HH:MM" / "fără sfârșit") si butonul care o opreste pe loc."""
	import html as _html
	try:
		A = _a(A)
		ses = A.sesiune()
		if ses is None or not ses.activa():
			return ""
		text = A.textPana(ses, banda=True)
	except Exception:
		return ""
	return ('<div role="status" style="background:#c0392b;color:#fff;padding:8px 14px;text-align:center;'
		'font:600 .95rem system-ui,sans-serif;">%s · <a href="/asistenta" onclick="%s" style="color:#fff;">%s</a>'
		'</div>' % (_html.escape(text), _html.escape(_OPRESTE_BANDA, quote=True), _html.escape(_t("Oprește"))))


def _argumente(request):
	"""Argumentele lui Start: numai accept (randul bifat), taiat la o marime sigura."""
	args = getattr(request, "args", None) or {}
	rez = {}
	valori = args.get(b"accept")
	if valori:
		v = valori[0]
		if isinstance(v, bytes):
			v = v[:8].decode("utf-8", "replace")
		rez["accept"] = v[:2]
	return rez


def rute(baza, resource, A=None):
	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(request, A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CatalogResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, catalog(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class CereResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				# pentru oricine; browserul conectat cu codul porneste pe loc, altul deschide pagina pe receptor
				return self._raspunde(request, cere(_argumente(request), A, de_incredere=_asociat(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class OpresteResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, opreste(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina as poarta
			return poarta(request, pagina_text)

	api = {
		b"asistenta": StareResource(),
		b"asistenta-catalog": CatalogResource(),
		b"asistenta-cere": CereResource(),
		b"asistenta-opreste": OpresteResource(),
	}
	return api, {b"asistenta": PaginaResource()}


def _drumMeniu(A=None):
	try:
		return _a(A).drumMeniu()
	except Exception:
		return "Meniu > Setări > Asistență de la distanță"


def _termeni(A=None):
	"""Termenii si conditiile intregi (A.textTermeni), ca paragrafe HTML pentru fereastra de peste pagina."""
	import html as _html
	try:
		text = _a(A).textTermeni()
	except Exception:
		return ""
	return "".join("<p>%s</p>" % _html.escape(p) for p in text.split("\n\n") if p.strip())


def pagina_text(stil, config_pagina, A=None):
	return (_traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)
		.replace("__TERMENI__", _termeni(A)))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Asistență de la distanță</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .scurt{line-height:1.5;margin:0 0 14px;}
  .bifa{display:flex;gap:10px;align-items:center;margin:0 0 16px;cursor:pointer;line-height:1.4;}
  .bifa input{width:22px;height:22px;margin:0;flex:none;accent-color:#46B06A;}
  .bifa a{color:inherit;text-decoration:underline;}
  .jurnal{font-family:monospace;font-size:.82rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;color:var(--text-slab);margin:0;max-height:360px;overflow:auto;}
  button{min-height:44px;padding:8px 22px;border-radius:8px;border:0;color:#fff;font:inherit;font-weight:600;cursor:pointer;}
  .verde{background:#2e8b4e;}
  .rosu{background:#c0392b;}
  .gri{background:#3a4255;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.2em;}
  .eroare{color:#ffb4a8;}
  .nota{color:var(--text-slab);font-size:.85rem;line-height:1.45;}
  .pana{font-weight:600;margin:0 0 12px;}
  .fereastra{position:fixed;inset:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:16px;z-index:50;}
  .fereastra .card{max-width:760px;width:100%;max-height:86vh;display:flex;flex-direction:column;margin:0;}
  .fereastra h2{font-size:1.1rem;margin:0 0 10px;}
  .fereastra .termeni{overflow:auto;flex:1;margin:0 0 12px;}
  .fereastra .termeni p{font-size:.9rem;line-height:1.5;margin:0 0 8px;}
  .concluzii h2{font-size:1.1rem;margin:0 0 6px;}
  .concluzii .text{white-space:pre-wrap;word-break:break-word;line-height:1.5;margin:0 0 10px;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Asistență de la distanță</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<section class="card ascuns" id="indisponibil">
  <p>Funcția nu e disponibilă pe această imagine.</p>
</section>
<section class="card ascuns" id="pornire">
  <p class="scurt">Echipa HD Satelit vede prin internet starea receptorului tău, ca să te ajute, fără să schimbe nimic. O oprești oricând.</p>
  <label class="bifa"><input type="checkbox" id="accept" checked><span>Accept <a href="#" id="termeni">termenii și condițiile</a></span></label>
  <button class="verde" id="porneste">Start</button>
  <p class="mesaj" id="mesaj"></p>
</section>
<section class="card ascuns" id="pornita">
  <p class="pana" id="stare"></p>
  <button class="rosu" id="opreste">Oprește</button>
  <p class="mesaj" id="mesajOprire"></p>
  <p class="nota ascuns" id="asteptare">Te anunțăm când intrăm. Poți folosi receptorul între timp.</p>
  <p class="nota">Jurnalul asistenței</p>
  <pre class="jurnal" id="jurnal"></pre>
</section>
<section class="card concluzii ascuns" id="concluzii">
  <h2>Ce am găsit și ce am făcut</h2>
  <p class="nota" id="concluziiOra"></p>
  <p class="text" id="concluziiText"></p>
  <p class="nota">Mulțumim că ne-ai lăsat să te ajutăm.</p>
</section>
</main>
<div class="fereastra ascuns" id="fereastra" role="dialog" aria-modal="true" aria-labelledby="titluTermeni">
  <div class="card">
    <h2 id="titluTermeni">Termenii și condițiile</h2>
    <div class="termeni">__TERMENI__</div>
    <div><button class="gri" id="inchide">Închide</button></div>
  </div>
</div>
<script>
var CFG = __CONFIG__;
function $(id){ return document.getElementById(id); }
function adresa(cale){ if(!CFG.jeton){ return cale; } return cale + (cale.indexOf("?")===-1?"?":"&") + "token=" + encodeURIComponent(CFG.jeton); }
function cerere(cale, metoda, date){
  var o = {method: metoda||"GET", cache:"no-store", credentials:"same-origin", headers:{}};
  if(CFG.csrf){ o.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){ o.headers["Content-Type"]="application/x-www-form-urlencoded"; o.body = date.toString(); }
  return fetch(adresa(cale), o).then(function(r){ return r.json().catch(function(){ return {result:false, message:"HTTP "+r.status}; }); });
}
function mesaj(id,t,e){ var m=$(id); m.textContent=t||""; m.classList.toggle("eroare",!!e); }
function nuRaspunde(){ return "Receptorul nu răspunde."; }
function arata(d){
  var activa = !!d.stare && d.stare!=="oprit";
  $("indisponibil").classList.toggle("ascuns", !!d.disponibil || activa);
  $("pornire").classList.toggle("ascuns", activa || !d.disponibil);
  $("pornita").classList.toggle("ascuns", !activa);
  $("stare").textContent = d.pana_text || "";
  $("asteptare").classList.toggle("ascuns", d.stare!=="asteapta");
  $("jurnal").textContent = (d.jurnal||[]).join("\\n") || "Jurnalul e gol.";
  var c = d.concluzii;
  $("concluzii").classList.toggle("ascuns", !(c && c.text));
  if(c && c.text){ $("concluziiText").textContent = c.text; $("concluziiOra").textContent = c.ora_text || ""; }
}
function citeste(){
  return cerere("/api/asistenta").then(function(d){
    if(d.result===false){ $("incarcare").textContent = d.message||nuRaspunde(); return; }
    $("incarcare").classList.add("ascuns"); arata(d);
  }).catch(function(){ $("incarcare").textContent=nuRaspunde(); });
}
$("termeni").addEventListener("click", function(e){ e.preventDefault(); e.stopPropagation(); $("fereastra").classList.remove("ascuns"); $("inchide").focus(); });
$("inchide").addEventListener("click", function(){ $("fereastra").classList.add("ascuns"); });
$("fereastra").addEventListener("click", function(e){ if(e.target===$("fereastra")){ $("fereastra").classList.add("ascuns"); } });
document.addEventListener("keydown", function(e){ if(e.key==="Escape"){ $("fereastra").classList.add("ascuns"); } });
$("accept").addEventListener("change", function(){ if($("accept").checked){ mesaj("mesaj",""); } });
$("porneste").addEventListener("click", function(){
  if(!$("accept").checked){ mesaj("mesaj", "Fără bifă, asistența nu pornește.", true); return; }
  var q=new URLSearchParams(); q.set("accept","1");
  mesaj("mesaj", "Se pornește...");
  cerere("/api/asistenta-cere","POST",q).then(function(d){ var activa=!!d.stare && d.stare!=="oprit"; mesaj("mesaj", activa ? "" : d.message, !d.result); arata(d); }).catch(function(){ mesaj("mesaj", nuRaspunde(), true); }); });
$("opreste").addEventListener("click", function(){ mesaj("mesajOprire", "Se oprește...");
  cerere("/api/asistenta-opreste","POST", new URLSearchParams()).then(function(d){ mesaj("mesajOprire", d.result ? "" : d.message, !d.result); if(d.result){ mesaj("mesaj", d.message); } arata(d); }).catch(function(){ mesaj("mesajOprire", nuRaspunde(), true); }); });
citeste(); setInterval(citeste, 3000);
</script>
</body>
</html>
"""


# textele de ecran ale paginii (sablonul si scriptul), ca liste scrise direct: le citesc xgettext si probele
TEXTE_PAGINA = {
	"html": (
		N_("Asistență de la distanță"),
		N_("Se citește starea..."),
		N_("Funcția nu e disponibilă pe această imagine."),
		N_("Echipa HD Satelit vede prin internet starea receptorului tău, ca să te ajute, fără să schimbe nimic. O "
			"oprești oricând."),
		N_("Accept <a href=\"#\" id=\"termeni\">termenii și condițiile</a>"),
		N_("Start"),
		N_("Oprește"),
		N_("Te anunțăm când intrăm. Poți folosi receptorul între timp."),
		N_("Jurnalul asistenței"),
		N_("Termenii și condițiile"),
		N_("Închide"),
		N_("Ce am găsit și ce am făcut"),
		N_("Mulțumim că ne-ai lăsat să te ajutăm."),
	),
	"js": (
		N_("Receptorul nu răspunde."),
		N_("Jurnalul e gol."),
		N_("Fără bifă, asistența nu pornește."),
		N_("Se pornește..."),
		N_("Se oprește..."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon.replace("__DRUM_MENIU__", _drumMeniu())
	return traduce(sablon, TEXTE_PAGINA, fel).replace("__DRUM_MENIU__", _drumMeniu())

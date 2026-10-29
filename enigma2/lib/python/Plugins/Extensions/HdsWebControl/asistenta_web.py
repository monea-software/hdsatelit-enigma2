# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# asistenta_web.py: Ajutor de la distanta in interfata web (HdsWebControl), perechea ecranului de pe receptor
# (Screens/HdsAsistenta.py). Aceeasi stare, acelasi text de informare si acelasi jurnal, din Components/HdsAsistenta.py.
# Numai pentru beta testeri (numai ei pot da acces la receptor): pagina e legata numai din /beta-tester; cine nu e
# inscris vede fraza Asistenta de la distanta e pentru beta testeri. si legatura spre /beta-tester, iar cererea de
# pornire e refuzata. Oprirea merge oricand (si dupa iesirea din program cu o sesiune pornita).
# Pornirea din web NU porneste nimic: deschide pe televizor ecranul Asistentei cu informarea si durata aleasa
# (Screens/HdsAsistentaSemn.cerereWeb); omul porneste de acolo. Oprirea merge din orice browser din reteaua locala (a
# opri nu primejduieste pe nimeni). Codul de 6 cifre se arata numai unui browser conectat cu codul de pe televizor
# (acelasi nivel asociat ca la Acces SSH). Cat asistenta e activa, paginile web au sus o banda (bandaWeb, pusa de
# meniu_comun_web.pagina). Omul nu trebuie sa ne spuna codul: serverul ni-l trimite singur pe e-mail; codul ramane pe
# pagina numai ca sa vada ca e cererea lui. "Cu ce te ajutăm?" (optional, ca pe receptor): o alegere din lista
# A.NEVOI si un rand de text; merg cu cererea spre ecranul de pornire de pe receptor, unde apar deja alese.
#
# Rute (poarta comuna meniu_comun_web; ce schimba ceva cere, cu cookie, POST si antetul CSRF):
#   GET  /api/asistenta            starea, timpul ramas, ultimele randuri din jurnal, codul (numai asociat)
#   GET  /api/asistenta-catalog    lista operatiilor in limba receptorului
#   POST /api/asistenta-cere?minute=120[&nevoie=wifi&detalii=...]   cere pornirea (ecranul cu informarea pe receptor);
#        minute: 120, 720, 1440, 10080, 43200 sau 0 (permanent), ca A.DURATE_MIN
#   POST /api/asistenta-opreste    opreste
#   GET  /asistenta                pagina
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (A).

def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


TEXT_NUMAI_TESTERI = N_("Asistența de la distanță e pentru beta testeri.")


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


def tester(B=None):
	"""Omul e beta tester? (Components.HdsBetaTester; fara el, nimeni nu e.)"""
	try:
		if B is None:
			from Components import HdsBetaTester as B
		return bool(B.inscris())
	except Exception:
		return False


def _asociat(request):
	"""True daca cererea vine dintr-un browser conectat cu codul de pe televizor (codul se arata numai lui)."""
	try:
		from . import acces_ssh_web
		return acces_ssh_web.nivel(request) == "asociat"
	except Exception:
		return False


def stare(request=None, A=None, B=None):
	A = _a(A)
	s = A.stare()
	rez = {"result": True, "stare": s.get("stare"), "disponibil": s.get("disponibil"), "tester": tester(B),
		"ramas_s": s.get("ramas_s", 0), "jurnal": s.get("jurnal", []), "nivel": s.get("nivel"),
		"durate": s.get("durate", []), "durata_implicita": s.get("durata_implicita"),
		# pana cand e pornita, tradus ("Pornită până la ZZ.LL, HH:MM." / "Pornită, fără sfârșit; ...")
		"permanent": bool(s.get("permanent")), "pana_text": s.get("pana_text") or ""}
	try:
		rez["durate_text"] = [[m, A.textDurata(m)] for m in rez["durate"]]
	except Exception:
		rez["durate_text"] = [[m, str(m)] for m in rez["durate"]]
	# "Cu ce te ajutăm?": aceeasi lista ca pe ecranul de pornire, tradusa (prima, "", e implicita)
	try:
		rez["nevoi_text"] = [[cheie, text] for cheie, text in A.alegeriNevoie()]
		rez["detalii_max"] = A.DETALII_MAX
	except Exception:
		rez["nevoi_text"] = []
	# codul numai pentru un browser asociat
	if s.get("cod") and (request is None or _asociat(request)):
		rez["cod"] = s["cod"]
	return rez


def catalog(A=None):
	A = _a(A)
	try:
		from Components import HdsAsistentaCatalog as C
		return {"result": True, "operatii": [{"op": op, "grup": _t(grup), "fel": fel, "text": _t(text)}
			for (op, grup, fel, text) in C.pentru_afisare()]}
	except Exception as e:
		return {"result": False, "message": _t("Nu pot citi catalogul: %s") % e}


def cere(argumente, A=None, B=None):
	A = _a(A)
	if not tester(B):
		rez = stare(None, A, B)
		rez.update({"result": False, "message": _t(TEXT_NUMAI_TESTERI), "beta": "/beta-tester"})
		return rez
	try:
		minute = int(argumente.get("minute", A.DURATA_IMPLICITA_MIN))
	except (TypeError, ValueError):
		minute = A.DURATA_IMPLICITA_MIN
	if minute not in A.DURATE_MIN:
		minute = A.DURATA_IMPLICITA_MIN
	curata = getattr(A, "curataNevoie", None)
	nevoie, detalii = curata(argumente.get("nevoie", ""), argumente.get("detalii", "")) if curata else ("", "")
	try:
		from Screens import HdsAsistentaSemn as Semn
		from .meniu_comun_web import sesiune
		reusit, mesaj = Semn.cerereWeb(sesiune(), nivel="A", durata_min=minute, nevoie=nevoie, detalii=detalii)
	except Exception as e:
		reusit, mesaj = False, _t("Nu pot cere confirmarea pe televizor: %s") % e
	rez = stare(None, A, B)
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
	"""Argumentele cererii de pornire: minutele si, optional, "Cu ce te ajutăm?" (cheia si textul, in UTF-8; taiate
	aici la o marime sigura, curatate apoi de A.curataNevoie)."""
	args = getattr(request, "args", None) or {}
	rez = {}
	for nume, marime in ((b"minute", 6), (b"nevoie", 16), (b"detalii", 800)):
		valori = args.get(nume)
		if not valori:
			continue
		v = valori[0]
		if isinstance(v, bytes):
			v = v[:marime * 4].decode("utf-8", "replace")
		rez[nume.decode("ascii")] = v[:marime]
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
				# numai beta testerii pot da acces la receptor: altfel fraza si legatura spre /beta-tester
				if not tester():
					return self._raspunde(request, cere(_argumente(request), A))
				# pornirea (chiar daca o confirma televizorul) o cere numai un browser conectat cu codul: altfel orice
				# aparat din casa ar putea deschide ecranul de pornire pe televizor
				if not _asociat(request):
					return self._raspunde(request, {"result": False, "trebuie_cod": True,
						"message": _t("Pornirea se cere numai dintr-un browser conectat cu codul de pe televizor.")}, 403)
				return self._raspunde(request, cere(_argumente(request), A))
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
		return "Meniu > Setări > Beta tester > Cere ajutor de la distanță"


def _informare(A=None):
	import html as _html
	try:
		text = _a(A).textInformare()
	except Exception:
		return ""
	return "".join("<p>%s</p>" % _html.escape(p) for p in text.split("\n\n") if p.strip())


def pagina_text(stil, config_pagina, A=None):
	return (_traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)
		.replace("__INFORMARE__", _informare(A)))


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
  .cod{font-size:2rem;letter-spacing:.25em;text-align:center;margin:6px 0;}
  .jurnal{font-family:monospace;font-size:.82rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;color:var(--text-slab);margin:0;max-height:360px;overflow:auto;}
  .rand{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
  select,button,input{min-height:44px;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  #randPornire .rand{margin:0 0 10px;}
  #detalii{flex:1;min-width:0;}
  button{cursor:pointer;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.2em;}
  .eroare{color:#ffb4a8;}
  .nota{color:var(--text-slab);font-size:.85rem;line-height:1.45;}
  .informare p{font-size:.9rem;line-height:1.5;margin:0 0 8px;}
  a.buton{display:inline-flex;align-items:center;min-height:44px;padding:8px 18px;border-radius:8px;background:var(--accent);color:#fff;text-decoration:none;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Asistență de la distanță</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<section class="card ascuns" id="numaiTesteri">
  <p class="acum">Asistența de la distanță e pentru beta testeri.</p>
  <div class="rand"><a class="buton" href="/beta-tester">Devino beta tester</a></div>
</section>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="acum" id="stare"></p>
    <p class="cod ascuns" id="cod"></p>
    <p class="nota ascuns" id="asteptare">Te anunțăm când intrăm. Poți folosi receptorul între timp.</p>
    <div id="randPornire">
      <div class="rand">
        <label for="minute">Cât timp</label>
        <select id="minute"></select>
      </div>
      <div class="rand">
        <label for="nevoie">Cu ce te ajutăm?</label>
        <select id="nevoie"></select>
      </div>
      <div class="rand">
        <input id="detalii" type="text" maxlength="200" autocomplete="off" placeholder="Scrie pe scurt (opțional)">
      </div>
      <div class="rand"><button id="porneste">Pornește</button></div>
    </div>
    <div class="rand ascuns" id="randOprire">
      <button id="opreste">Oprește</button>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card informare" id="informare">__INFORMARE__</section>
  <section class="card">
    <p class="nota">Jurnalul asistenței</p>
    <pre class="jurnal" id="jurnal"></pre>
  </section>
  <p class="nota">Pornirea cere confirmare pe televizor. Oprirea merge din orice browser din rețeaua locală. Aceleași lucruri sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
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
function hms(s){ s=Math.max(0,s|0); return (s/3600|0)+":"+("0"+((s%3600)/60|0)).slice(-2)+":"+("0"+(s%60)).slice(-2); }
function mesaj(t,e){ var m=$("mesaj"); m.textContent=t||""; m.classList.toggle("eroare",!!e); }
function nuRaspunde(){ return "Receptorul nu răspunde."; }
function arata(d){
  var activa = d.stare && d.stare!=="oprit";
  var poarta = !d.tester && !activa;
  $("numaiTesteri").classList.toggle("ascuns", !poarta);
  $("continut").classList.toggle("ascuns", poarta);
  if(poarta){ return; }
  $("randPornire").classList.toggle("ascuns", activa || !d.disponibil);
  $("randOprire").classList.toggle("ascuns", !activa);
  $("informare").classList.toggle("ascuns", activa);
  if(!$("minute").options.length){ (d.durate_text||[]).forEach(function(x){ var o=document.createElement("option"); o.value=x[0]; o.textContent=x[1]; if(x[0]===d.durata_implicita){o.selected=true;} $("minute").appendChild(o); }); }
  if(!$("nevoie").options.length){ (d.nevoi_text||[]).forEach(function(x){ var o=document.createElement("option"); o.value=x[0]; o.textContent=x[1]; $("nevoie").appendChild(o); }); }
  var t = "";
  if(!d.disponibil){ t = "Funcția nu e disponibilă pe această imagine."; }
  else if(!activa){ t = "Oprită. O pornești tu, dacă vrei să ne ajuți."; }
  else if(d.stare==="asteapta"){ t = "Am primit cererea ta, cu codul de mai jos. Nu trebuie să faci nimic." + " " + (d.pana_text||""); }
  else if(d.stare==="conectat"){ t = "Conectat." + " " + (d.pana_text||""); }
  else { t = "Se pregătește..."; }
  $("stare").textContent = t;
  $("asteptare").classList.toggle("ascuns", d.stare!=="asteapta");
  if(d.cod){ $("cod").textContent = String(d.cod).replace(/(\\d\\d)(\\d\\d)(\\d\\d)/, "$1 $2 $3"); $("cod").classList.remove("ascuns"); }
  else { $("cod").classList.add("ascuns"); }
  $("jurnal").textContent = (d.jurnal||[]).join("\\n") || "Jurnalul e gol.";
}
function citeste(){
  return cerere("/api/asistenta").then(function(d){
    if(d.result===false){ $("incarcare").textContent = d.message||nuRaspunde(); return; }
    $("incarcare").classList.add("ascuns"); arata(d);
  }).catch(function(){ $("incarcare").textContent=nuRaspunde(); });
}
$("porneste").addEventListener("click", function(){ var q=new URLSearchParams(); q.set("minute", $("minute").value);
  if($("nevoie").value){ q.set("nevoie", $("nevoie").value); } if($("detalii").value.trim()){ q.set("detalii", $("detalii").value.trim()); }
  mesaj("Se deschide pe televizor...");
  cerere("/api/asistenta-cere","POST",q).then(function(d){ mesaj(d.message, !d.result); arata(d); }).catch(function(){ mesaj(nuRaspunde(),true); }); });
$("opreste").addEventListener("click", function(){ mesaj("Se oprește...");
  cerere("/api/asistenta-opreste","POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); arata(d); }).catch(function(){ mesaj(nuRaspunde(),true); }); });
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
		N_("Asistența de la distanță e pentru beta testeri."),
		N_("Devino beta tester"),
		N_("Te anunțăm când intrăm. Poți folosi receptorul între timp."),
		N_("Cât timp"),
		N_("Cu ce te ajutăm?"),
		N_("Scrie pe scurt (opțional)"),
		N_("Pornește"),
		N_("Oprește"),
		N_("Jurnalul asistenței"),
		N_("Pornirea cere confirmare pe televizor. Oprirea merge din orice browser din rețeaua locală. Aceleași "
			"lucruri sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Receptorul nu răspunde."),
		N_("Funcția nu e disponibilă pe această imagine."),
		N_("Oprită. O pornești tu, dacă vrei să ne ajuți."),
		N_("Am primit cererea ta, cu codul de mai jos. Nu trebuie să faci nimic."),
		N_("Conectat."),
		N_("Se pregătește..."),
		N_("Jurnalul e gol."),
		N_("Se deschide pe televizor..."),
		N_("Se oprește..."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon.replace("__DRUM_MENIU__", _drumMeniu())
	return traduce(sablon, TEXTE_PAGINA, fel).replace("__DRUM_MENIU__", _drumMeniu())

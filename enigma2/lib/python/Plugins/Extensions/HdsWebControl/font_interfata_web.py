# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# font_interfata_web.py: "Fontul interfetei" in interfata web (HdsWebControl).
#
# Pe televizor: Meniu > Interfata si aspect > Fontul interfetei (Screens/HdsFontInterfata.py). Aici: aceleasi familii,
# aceeasi alegere, aceeasi verificare a literelor limbii meniului, din aceeasi logica (Components/HdsFontInterfata.py).
# Proba din pagina e scrisa chiar cu fisierele fontului de pe receptor (@font-face din /api/font-interfata-fisier), deci
# arata ce se va vedea pe televizor.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/font-interfata                          familiile, alegerea de acum, limba meniului
#   POST /api/font-interfata-seteaza?id=<familie>     foloseste familia (pe loc si la pornire)
#   GET  /api/font-interfata-fisier?id=<familie>&rol=regular|bold|cond   fisierul TTF (numai cele din tabel)
#   GET  /font-interfata                              pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; addFont trebuie chemat chiar pe el (lista fonturilor din
# lib/gdi/font.cpp nu are lacat pentru cititori). Fisierul de font se citeste o data (cel mult 600 KB). Modulul nu
# importa nimic din enigma2 la incarcare.

MAXIM_FISIER = 1024 * 1024


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsFontInterfata
	return HdsFontInterfata


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def stare(F=None, config=None, limba=None, **cai):
	"""GET /api/font-interfata."""
	F = _f(F)
	rez = F.stare(config, traducere=_t, limba=limba, **cai)
	rez["result"] = True
	return rez


def seteaza(argumente, F=None, config=None, addFont=None, verifica=None, configfile=None, limba=None, **cai):
	"""POST /api/font-interfata-seteaza."""
	F = _f(F)
	fid = argumente.get("id", "")
	bun, rezultat = F.seteaza(fid, config=config, addFont=addFont, verifica=verifica, configfile=configfile, limba=limba, **cai)
	rez = stare(F, config, limba, **cai)
	if bun:
		rez.update({"result": True, "message": _t("Fontul interfeței e acum %s. Pe televizor îl folosesc ecranele pe "
			"care le deschizi de acum.") % rezultat})
	else:
		rez.update({"result": False, "message": _t(rezultat)})
	return rez


def fisier(argumente, F=None, **cai):
	"""(octetii fontului, None) sau (None, motivul). Numai fisierele din tabelul familiilor."""
	F = _f(F)
	fid, rol = argumente.get("id", ""), argumente.get("rol", "")
	if F.familie(fid) is None or rol not in F.ROLURI:
		return None, _t("Se cere id=<familie> si rol=regular|bold|cond.")
	cale = F.cale(fid, rol, **cai) or F.cale(F.IMPLICIT, rol, **cai)
	try:
		with open(cale, "rb") as f:
			date = f.read(MAXIM_FISIER + 1)
	except (IOError, OSError, TypeError):
		return None, _t("Fișierul fontului lipsește.")
	if len(date) > MAXIM_FISIER or date[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
		return None, _t("Fișierul fontului nu e bun.")
	return date, None


def argumente(request):
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:6]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ("id", "rol"):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:20].strip()
	return rez


def rute(baza, resource, F=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(F))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), F))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class FisierResource(baza):
		def render_GET(self, request):
			try:
				date, motiv = fisier(argumente(request), F)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			if date is None:
				return self._eroare(request, motiv, 404)
			request.setHeader(b"content-type", b"font/ttf")
			request.setHeader(b"cache-control", b"private, max-age=86400")
			return date

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	return ({b"font-interfata": StareResource(), b"font-interfata-seteaza": SeteazaResource(),
		b"font-interfata-fisier": FisierResource()}, {b"font-interfata": PaginaResource()})


def pagina(request):
	"""Aceeasi poarta ca /paznic: numai din casa, cu browserul asociat sau ?token=."""
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


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_font_interfata"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fontul interfeței</title>
<style>__STIL_COMUN__
  main{max-width:1040px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .familii{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:8px;}
  .card.ales{border-color:#f5b83d;}
  .cap{display:flex;justify-content:space-between;align-items:baseline;gap:10px;}
  .cap h2{font-size:1.05rem;margin:0;}
  .eticheta{font-size:.78rem;color:#f5b83d;white-space:nowrap;}
  .eticheta.stins{color:var(--text-slab);}
  .proba{background:#10162a;border-radius:8px;padding:10px 12px;overflow:hidden;}
  .proba div{white-space:nowrap;overflow:hidden;line-height:1.45;}
  .proba .t{font-size:1.35rem;font-weight:700;}
  .proba .r{font-size:1.05rem;}
  .proba .m{font-size:.85rem;color:#c9d2e3;}
  .descriere{font-size:.9rem;line-height:1.45;margin:0;}
  .detalii{font-size:.8rem;color:var(--text-slab);margin:0;line-height:1.4;}
  .card button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:var(--albastru);color:#fff;font:inherit;cursor:pointer;align-self:flex-start;}
  .card button[disabled]{background:#242a33;color:var(--text-slab);cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:10px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>Fontul interfeței</h1>
<p class="mesaj" id="incarcare">Se citesc fonturile...</p>
<div id="continut" class="ascuns">
  <div class="familii" id="familii"></div>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Proba fiecărui font e scrisă cu fișierele lui de pe receptor. Toate fonturile sunt libere (SIL Open Font License 1.1); licențele sunt și în pagina Licențe. Același ecran e pe televizor, în __DRUM_MENIU__.</p>
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
var INCARCATE = {};
function font(id, rol){
  var nume = "hds-" + id + "-" + rol;
  if(!INCARCATE[nume] && window.FontFace){
    INCARCATE[nume] = true;
    var f = new FontFace(nume, "url(" + adresa("/api/font-interfata-fisier?id=" + encodeURIComponent(id) + "&rol=" + rol) + ")");
    // dupa incarcare textul are alta latime: derularea (cadru_web.py) masoara din nou
    f.load().then(function(x){ document.fonts.add(x); if(window.HDS_DERULANT){ window.HDS_DERULANT.verifica(); } }).catch(function(){});
  }
  return "'" + nume + "', system-ui, sans-serif";
}
// randul probei care nu incape se deruleaza (hds-derulant, cadru_web.py): la fontul folosit, cu mouse-ul sau cu focusul
function linie(clasa, text, id, rol){ var d = document.createElement("div"); d.className = clasa + " hds-derulant"; d.textContent = text; d.style.fontFamily = font(id, rol); return d; }
function arata(d){
  var c = $("familii"); c.textContent = "";
  d.familii.forEach(function(f){
    var card = document.createElement("section"); card.className = "card hds-derulant-rand" + (f.ales ? " ales" : "");
    var cap = document.createElement("div"); cap.className = "cap";
    var h = document.createElement("h2"); h.textContent = f.nume; cap.appendChild(h);
    var e = document.createElement("span"); e.className = "eticheta";
    if(f.ales){ e.textContent = "folosit acum"; } else if(!f.potrivit){ e.textContent = "fără literele limbii"; e.classList.add("stins"); }
    cap.appendChild(e); card.appendChild(cap);
    var p = document.createElement("div"); p.className = "proba";
    p.appendChild(linie("t", "Știri de seară, la ora 20:00", f.id, "bold"));
    p.appendChild(linie("r", "Rândul obișnuit al unei liste: emisiunea de acum", f.id, "regular"));
    p.appendChild(linie("r", "0123456789 · 20:15 · 87%", f.id, "regular"));
    p.appendChild(linie("m", "Text mic: ăâîșț ĂÂÎȘȚ 0123456789", f.id, "cond"));
    card.appendChild(p);
    var de = document.createElement("p"); de.className = "descriere"; de.textContent = f.descriere; card.appendChild(de);
    var dt = document.createElement("p"); dt.className = "detalii";
    dt.textContent = "Litere: " + f.litere + " · Pe disc: " + f.marime + " · De la: " + f.autor + " · " + f.licenta + (f.ingust ? "" : " · textele mici rămân cu Open Sans îngust");
    card.appendChild(dt);
    var b = document.createElement("button"); b.type = "button";
    b.textContent = f.ales ? "Folosit acum" : "Folosește fontul";
    b.disabled = f.ales || !f.potrivit;
    b.addEventListener("click", function(){ alege(f.id); });
    card.appendChild(b);
    c.appendChild(card);
  });
}
function citeste(){
  return cerere("/api/font-interfata").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi fonturile."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function alege(id){
  var q = new URLSearchParams(); q.set("id", id);
  mesaj("Se schimbă fontul...");
  cerere("/api/font-interfata-seteaza", "POST", q).then(function(d){ if(d.familii){ arata(d); } mesaj(d.message, !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
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
		N_("Fontul interfeței"),
		N_("Se citesc fonturile..."),
		N_("Proba fiecărui font e scrisă cu fișierele lui de pe receptor. Toate fonturile sunt libere (SIL "
			"Open Font License 1.1); licențele sunt și în pagina Licențe. Același ecran e pe televizor, în "
			"__DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("fără literele limbii"),
		N_("Știri de seară, la ora 20:00"),
		N_("Rândul obișnuit al unei liste: emisiunea de acum"),
		N_("Text mic: ăâîșț ĂÂÎȘȚ 0123456789"),
		N_("Litere:"),
		N_("· Pe disc:"),
		N_("· De la:"),
		N_("· textele mici rămân cu Open Sans îngust"),
		N_("Folosit acum"),
		N_("Folosește fontul"),
		N_("Receptorul nu a putut citi fonturile."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se schimbă fontul..."),
		N_("Receptorul nu răspunde."),
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

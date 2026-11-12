# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# copie_imagine_web.py: „Copia completă a imaginii” in interfata web (HdsWebControl).
#
# Perechea ecranului de pe televizor: Meniu > Setari > Software & Firmware > Copia completa a imaginii
# (Screens/HdsCopieImagine.py). Aceleasi locuri (stickurile si discurile USB), aceeasi copie pe firul ei, acelasi pas cu
# procent si timp ramas, aceeasi oprire, din acelasi modul (Components/HdsCopieImagine.py). Raspunsurile au numai nume
# de locuri, texte si numere.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/copie-imagine                   locurile, lucrul in curs (pasul, textul), rezultatul ultimei copii
#   POST /api/copie-imagine-fa?mediu=<id>     porneste copia pe locul ales (pe firul ei)
#   POST /api/copie-imagine-opreste           opreste copia; fisierul inceput se sterge
#   GET  /copie-imagine                       pagina
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (M).


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsCopieImagine
	return HdsCopieImagine


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:8]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:600].strip()
	return rez


def stare(M=None):
	"""GET /api/copie-imagine"""
	M = _m(M)
	ok, motiv = M.suport()
	st = M.stare()
	medii = M.medii() if ok and not st["lucreaza"] else []
	implicit = M.mediuImplicit(medii)
	r = st["rezultat"]
	return {
		"result": True,
		"suport": bool(ok),
		"text_suport": "" if ok else M.textSuport(motiv),
		"despre": M.textDespre(),
		"parole": M.textParole(),
		"lucreaza": bool(st["lucreaza"]),
		"oprit": bool(st["oprit"]),
		"pas": st["pas"],
		"pasi": st["pasi"],
		"text": st["text"],
		"medii": [{"id": m["id"], "nume": m["nume"]} for m in medii],
		"implicit": implicit["id"] if implicit else "",
		"rezultat": {"ok": bool(r["ok"]), "mesaj": r["mesaj"]} if r else None,
	}


def salveazaSetarile():
	"""Setarile de acum intra in copie (ca pe televizor, inainte de pornire)."""
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as eroare:
		print("[copie_imagine_web] setarile: %r" % (eroare,))


def fa(a, M=None):
	M = _m(M)
	if M is not None and not M.ocupat():
		salveazaSetarile()
	pornit, mesaj = M.porneste(a.get("mediu", ""))
	return {"result": bool(pornit), "message": mesaj}


def opreste(M=None):
	M = _m(M)
	if M.opreste():
		return {"result": True, "message": _t("Copia se oprește…")}
	return {"result": False, "message": _t("Nu se face nicio copie acum.")}


def rute(baza, resource, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/copie-imagine: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def resursa(functie):
		class Resursa(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(argumente(request)))
				except Exception as eroare:
					return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Resursa()

	class PaginaResource(resource.Resource):
		"""GET /copie-imagine: pagina „Copia completă a imaginii”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"copie-imagine": StareResource(),
		b"copie-imagine-fa": resursa(lambda a: fa(a, M)),
		b"copie-imagine-opreste": resursa(lambda a: opreste(M)),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /copie-setari: reteaua locala, apoi ?token= sau cookie-ul browserului asociat."""
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
<title>Copia completă a imaginii</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  label.alegere{display:flex;gap:10px;align-items:center;min-height:44px;cursor:pointer;overflow-wrap:anywhere;}
  label.alegere input{min-width:20px;min-height:20px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;white-space:pre-line;}
  .mesaj:empty{display:none;}
  .eroare{color:#ffb4a8;}
  .bara{height:10px;border-radius:5px;background:#2a3140;overflow:hidden;margin:10px 0 0;}
  .bara div{height:100%;width:0;background:#1f771f;transition:width .5s;}
  .ascuns{display:none;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#2a3140;color:#fff;font:inherit;cursor:pointer;}
  button.verde{background:#1f771f;}
  button.galben{background:#7a5a10;}
  button:disabled{opacity:.5;cursor:default;}
</style>
</head>
<body>
<main>
<h1>Copia completă a imaginii</h1>
<section class="card">
  <p class="nota" id="despre"></p>
  <p class="nota" id="parole"></p>
  <div id="medii"><p class="mesaj">Se caută stickurile și discurile...</p></div>
  <div class="butoane"><button type="button" class="verde" id="fa" disabled>Fă copia acum</button>
  <button type="button" class="galben ascuns" id="opreste">Oprește copia</button>
  <button type="button" id="cauta">Caută din nou</button></div>
  <div class="bara ascuns" id="bara"><div id="umplut"></div></div>
  <p class="mesaj" id="mesaj"></p>
</section>
<p class="nota">Copia se pune înapoi din Meniu, Setări, Software &amp; Firmware, Imagine nouă de pe stick.</p>
<p class="nota">Pe televizor: Meniu, Setări, Software &amp; Firmware, Copia completă a imaginii.</p>
</main>
<script>
var CFG = __CONFIG__;
var ales = null, ceas = null, semn = null, pornita = false;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function el(tip, clasa, text){ var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text !== undefined){ e.textContent = text; } return e; }
function desenMedii(d){
  var c = $("medii"); c.textContent = "";
  if(!d.suport){ c.appendChild(el("p", "mesaj eroare", d.text_suport)); ales = null; return; }
  if(d.lucreaza){ return; }
  var lista = d.medii || [];
  if(!lista.length){
    c.appendChild(el("p", "mesaj", "Bagă un stick sau un disc USB în receptor. Lista se reface singură."));
    ales = null; return;
  }
  if(!lista.some(function(m){ return m.id === ales; })){ ales = d.implicit || lista[0].id; }
  lista.forEach(function(m){
    var l = el("label", "alegere"); var i = el("input"); i.type = "radio"; i.name = "mediu"; i.checked = m.id === ales;
    i.addEventListener("change", function(){ ales = m.id; });
    l.appendChild(i); l.appendChild(document.createTextNode(m.nume)); c.appendChild(l);
  });
}
function procent(text){ var m = /(\\d+) %/.exec(text || ""); return m ? parseInt(m[1], 10) : 0; }
function citeste(){
  if(ceas){ clearTimeout(ceas); ceas = null; }
  if(document.hidden){ ceas = setTimeout(citeste, 3000); return; }
  cerere("/api/copie-imagine").then(function(d){
    if(!d.result){ mesaj(d.message || "Receptorul nu a putut citi starea.", true); ceas = setTimeout(citeste, 3000); return; }
    $("despre").textContent = d.despre || "";
    $("parole").textContent = d.parole || "";
    var nou = JSON.stringify([d.suport, d.lucreaza, d.medii]);
    if(semn !== nou){ desenMedii(d); semn = nou; }
    $("fa").disabled = !d.suport || d.lucreaza || !ales;
    $("opreste").classList.toggle("ascuns", !d.lucreaza);
    $("bara").classList.toggle("ascuns", !d.lucreaza);
    if(d.lucreaza){
      pornita = true;
      var pas = d.pas || 1, p = procent(d.text);
      $("umplut").style.width = Math.min(100, ((pas - 1) * 100 + p) / (d.pasi || 3)) + "%";
      mesaj(d.oprit ? "Copia se oprește…" : d.text + "\\n" + "Nu scoate stickul până nu scrie „Copia e gata”.");
    } else if(pornita && d.rezultat){
      pornita = false; mesaj(d.rezultat.mesaj, !d.rezultat.ok);
    }
    ceas = setTimeout(citeste, d.lucreaza ? 1000 : 4000);
  }).catch(function(){
    mesaj("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true);
    ceas = setTimeout(citeste, 3000);
  });
}
$("fa").addEventListener("click", function(){
  $("fa").disabled = true; mesaj("Copia pornește...");
  cerere("/api/copie-imagine-fa?mediu=" + encodeURIComponent(ales || ""), "POST").then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ pornita = true; } else { $("fa").disabled = false; }
    setTimeout(citeste, 800);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); $("fa").disabled = false; });
});
$("opreste").addEventListener("click", function(){
  cerere("/api/copie-imagine-opreste", "POST").then(function(d){ mesaj(d.message, !d.result); setTimeout(citeste, 800); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
$("cauta").addEventListener("click", function(){ semn = null; mesaj(""); citeste(); });
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
		N_("Copia completă a imaginii"),
		N_("Se caută stickurile și discurile..."),
		N_("Fă copia acum"),
		N_("Oprește copia"),
		N_("Caută din nou"),
		N_("Copia se pune înapoi din Meniu, Setări, Software &amp; Firmware, Imagine nouă de pe stick."),
		N_("Pe televizor: Meniu, Setări, Software &amp; Firmware, Copia completă a imaginii."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Bagă un stick sau un disc USB în receptor. Lista se reface singură."),
		N_("Receptorul nu a putut citi starea."),
		N_("Copia se oprește…"),
		N_("Nu scoate stickul până nu scrie „Copia e gata”."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Copia pornește..."),
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

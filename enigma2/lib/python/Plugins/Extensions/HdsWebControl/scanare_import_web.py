# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# scanare_import_web.py: „Import canale și setări” în interfața web (HdsWebControl).
#
# Orice ecran de pe receptor are pereche în interfața web. Pe televizor: Meniu > Scanare > Import canale și setări
# (Plugins/Extensions/HdsImportSetari/plugin.py). Aici: aceleași surse (stick-urile întâi), aceleași patru alegeri,
# același import, din același modul (Components/HdsImportSurse.py): căutarea, dezarhivarea, copia de siguranță și
# scrierea fișierelor pe firul importului, reîncărcarea listei de canale pe firul enigma2, un singur import odată
# pentru televizor și web. Setările merg în settings.din-copie și intră la următoarea pornire a interfeței (pagina
# /setari-din-copie arată starea lor și o repornește).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/import-surse[?cauta=1]      sursele găsite (fără căutare nouă, afară de prima cerere și de cauta=1),
#                                          starea căutării și a importului, rezultatul ultimului import
#   POST /api/import?sursa=<id>&canale=1&tunere=1&temporizatoare=0&retea=0&picon=1&generale=1&pachete=1
#                                          pornește importul (pluginurile: numai oferta, instalate apoi prin
#                                          /api/extensii-instaleaza, ca la Extensii și aplicații)
#   POST /api/import-alta-imagine?raspuns=da|nu|ascunde   răspunsul la întrebarea primei porniri (copia altei imagini,
#                                          Components/HdsImportAltaImagine.py) sau ascunderea rezumatului ei
#   GET  /import                           pagina
#
# Întrebarea primei porniri (Components/HdsImportAltaImagine.py): pe televizor e o casetă Da/Nu; aici aceeași
# întrebare, cu sursa, în cartea de sus a paginii, cât timp e deschisă, apoi rezumatul (ce s-a adus și ce nu) și
# repornirea interfeței (/api/setari-din-copie-reporneste) când setările antenei o așteaptă. Starea vine în
# /api/import-surse ("alta_imagine"); răspunsul dat într-o parte închide întrebarea din cealaltă.
#
# FIRUL: render_GET / render_POST rulează pe firul enigma2; răspund pe loc (căutarea și dezarhivarea merg pe firul
# lor, iar pagina întreabă din nou). Fișierul nu importă nimic din enigma2 la încărcare: probele de pe PC dau
# modulul lor (M).

_LUCRARI = []    # lucrările în curs (eTimer-ul unei Lucrări neținute în viață e cules și rezultatul nu mai vine)


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsImportSurse
	return HdsImportSurse


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsImportAltaImagine
	return HdsImportAltaImagine


def _texte_setari():
	try:
		from Components import HdsSetariDinCopie
		return HdsSetariDinCopie.texteStare()
	except Exception:
		return []


def banda_panou(A=None):
	"""Textul benzii de pe prima pagină a interfeței (plugin.py, /api/statusinfo) cât timp întrebarea primei porniri e
	deschisă, altfel "". Nu aruncă."""
	try:
		return _a(A).banda_panou()
	except Exception:
		return ""


def stare_alta_imagine(A=None):
	"""Starea întrebării primei porniri pentru pagină; {} când nu se poate citi."""
	try:
		return _a(A).stare_publica()
	except Exception:
		return {}


def alta_imagine(a, A=None):
	"""POST /api/import-alta-imagine?raspuns=da|nu|ascunde: răspunsul la întrebarea primei porniri (același ca pe
	televizor) sau ascunderea rezumatului din pagină."""
	A = _a(A)
	raspuns = a.get("raspuns", "")
	if raspuns == "ascunde":
		A.ascunde_rezumatul_web()
		return {"result": True, "message": "", "alta_imagine": A.stare_publica()}
	if raspuns not in ("da", "nu"):
		return {"result": False, "message": _t("Răspuns necunoscut.")}
	ok, mesaj = A.raspunde(raspuns == "da", "web")
	return {"result": bool(ok), "message": mesaj, "alta_imagine": A.stare_publica()}


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 20:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:600].strip()
	return rez


def sursa_publica(M, s):
	"""Ce vede pagina dintr-o sursă (fără cheile interne)."""
	return {
		"id": s["id"],
		"text": M.text_sursa(s),
		"descriere": M.descriere_sursa(s),
		"mediu": s["mediu"],
		"mediu_nume": s["mediu_nume"],
		"data": M.data_text(s.get("timp")),
		"canale": bool(s.get("canale")),
		"setari": bool(s.get("setari")),
		"temporizatoare": bool(s.get("temporizatoare")),
		"buchete": int(s.get("buchete") or 0),
		"retea": bool(s.get("retea")),
		"picon": bool(s.get("picon")),
		"pachete": bool(s.get("pachete")),
	}


def surse(a, M=None, texte_setari=None, A=None):
	"""GET /api/import-surse: prima cerere (sau cauta=1) pornește căutarea; celelalte citesc starea comună."""
	M = _m(M)
	st = M.stare()
	if a.get("cauta") == "1" or (st["surse"] is None and not st["cauta"]):
		try:
			M.porneste_cautarea()
		except Exception as eroare:
			return {"result": False, "message": _t("Căutarea nu a pornit: %s.") % eroare}
	st = M.stare()
	lista = [sursa_publica(M, s) for s in (st["surse"] or [])]
	return {
		"result": True,
		"cauta": bool(st["cauta"]),
		"cautat": bool(st["cand"]),
		"surse": lista,
		"fara": M.text_fara_surse() if not lista and not st["cauta"] else "",
		"alegeri": [c for c, _camp in M.ALEGERI],
		"campuri": dict(M.ALEGERI),
		"etichete": dict((c, M.eticheta_alegere(c)) for c, _camp in M.ALEGERI),
		"ajutor": dict((c, M.ajutor_alegere(c)) for c, _camp in M.ALEGERI),
		"implicite": dict(M.ALEGERI_IMPLICITE),
		"ocupat": M.ocupat(),
		"ultimul": st["ultimul"],
		"setari": texte_setari() if texte_setari else _texte_setari(),
		"alta_imagine": stare_alta_imagine(A),
	}


def porneste(a, M=None):
	"""POST /api/import: pregătirea sursei, copia de siguranță și importul pe firul lor (M.porneste_importul), apoi
	reîncărcarea listei de canale pe firul enigma2; răspunde pe loc."""
	M = _m(M)
	s = M.sursa_dupa_id(a.get("sursa", ""))
	if s is None:
		return {"result": False, "message": _t("Copia aleasă nu mai este în listă. Caută din nou.")}
	alegeri = M.alegeri_efective(dict((c, a.get(c) == "1") for c, _camp in M.ALEGERI), s)
	if not any(alegeri.values()):
		return {"result": False, "message": _t("Alege cel puțin un lucru de importat.")}
	lucrare = []
	terminat = []

	def _gata(rezultat):
		terminat.append(True)
		for l in lucrare:
			if l in _LUCRARI:
				_LUCRARI.remove(l)

	try:
		l = M.porneste_importul(s, alegeri, _gata)
	except Exception as eroare:
		return {"result": False, "message": str(eroare)}
	if l is None:
		return {"result": False, "message": _t("Un import e deja în curs. Așteaptă să se termine.")}
	if not terminat:
		lucrare.append(l)
		_LUCRARI.append(l)
	return {"result": True, "message": _t("Importul a pornit.")}


def rute(baza, resource, M=None, A=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class SurseResource(baza):
		"""GET /api/import-surse: numai citire (căutarea citește discurile, nu scrie nimic)."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, surse(argumente(request), M, A=A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class AltaImagineResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, alta_imagine(argumente(request), A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class ImportResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, porneste(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /import: pagina „Import canale și setări”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"import-surse": SurseResource(),
		b"import": ImportResource(),
		b"import-alta-imagine": AltaImagineResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /setari-din-copie: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
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
<title>Import canale și setări</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .mediu{font-weight:600;margin:12px 0 6px;color:var(--text-slab);}
  .mediu:first-child{margin-top:0;}
  label.sursa{display:flex;gap:10px;align-items:flex-start;padding:8px 6px;border-radius:8px;cursor:pointer;}
  label.sursa:hover{background:rgba(255,255,255,.04);}
  label.sursa input{margin-top:4px;min-width:20px;min-height:20px;}
  label.sursa > span{min-width:0;overflow-wrap:anywhere;}
  .desc{display:block;color:var(--text-slab);font-size:.85rem;line-height:1.4;overflow-wrap:anywhere;white-space:pre-line;}
  label.alegere{display:flex;gap:10px;align-items:center;min-height:44px;cursor:pointer;}
  label.alegere input{min-width:20px;min-height:20px;}
  label.alegere.stins{opacity:.5;cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;white-space:pre-line;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#2a3140;color:#fff;font:inherit;cursor:pointer;}
  button.verde{background:#1f771f;}
  button:disabled{opacity:.5;cursor:default;}
  .card.alta{border-color:#f5b83d;}
  .intrebare{font-size:1.02rem;line-height:1.45;margin:0 0 8px;}
  ul.lista{margin:4px 0 8px 20px;padding:0;line-height:1.55;}
  h3{font-size:.95rem;margin:10px 0 2px;}
</style>
</head>
<body>
<main>
<h1>Import canale și setări</h1>
<section class="card alta ascuns" id="card-alta" aria-live="polite">
  <h2>Canalele din altă imagine</h2>
  <div id="alta-intrebare-bloc">
    <p class="intrebare" id="alta-intrebare"></p>
    <p class="desc" id="alta-sursa"></p>
    <p class="nota" id="alta-ce"></p>
    <div class="butoane"><button type="button" class="verde" id="alta-da">Da, adu-le</button><button type="button" id="alta-nu">Nu</button></div>
  </div>
  <p class="mesaj ascuns" id="alta-lucreaza">Se aduc canalele și setările...</p>
  <div class="ascuns" id="alta-rezumat">
    <div id="alta-rez-bun">
      <h3>Am adus</h3><ul class="lista" id="alta-adus"></ul>
      <h3>Nu am adus</h3><ul class="lista" id="alta-neadus"></ul>
    </div>
    <p class="mesaj ascuns" id="alta-rez-text"></p>
    <div class="butoane"><button type="button" class="verde ascuns" id="alta-reporneste">Repornește interfața acum</button><button type="button" id="alta-ascunde">Am înțeles</button></div>
  </div>
  <p class="mesaj" id="alta-mesaj"></p>
</section>
<section class="card">
  <h2>Copia din care se importă</h2>
  <div id="surse"><p class="mesaj">Se caută copiile...</p></div>
  <div class="butoane"><button type="button" id="cauta">Caută din nou</button></div>
</section>
<section class="card">
  <h2>Ce se importă</h2>
  <div id="alegeri"></div>
  <div class="butoane"><button type="button" class="verde" id="importa" disabled>Importă</button></div>
  <p class="mesaj" id="mesaj"></p>
</section>
<section class="card ascuns" id="card-pluginuri" aria-live="polite">
  <h2>Pluginurile din copie</h2>
  <p class="nota">Sunt în sursele receptorului și nu sunt instalate. Fiecare are întrebarea lui, ca la Extensii și aplicații.</p>
  <div id="pluginuri"></div>
  <p class="mesaj" id="mesaj-pluginuri"></p>
</section>
<section class="card ascuns" id="card-setari">
  <h2>Setările importate</h2>
  <div id="setari"></div>
  <p class="nota"><a href="/setari-din-copie">Setările importate</a>: starea lor și repornirea interfeței.</p>
</section>
<p class="nota">Înainte de import, receptorul păstrează canalele și setările de acum într-o copie de siguranță, care
apare apoi în lista de mai sus („Copiile de siguranță de pe receptor”; se păstrează ultimele cinci): cu ea importul se
poate întoarce. Setările
alese intră la următoarea pornire a interfeței. Pe televizor: Meniu, Scanare, Import canale și setări.</p>
</main>
<script>
var CFG = __CONFIG__;
var ETICHETE = {}, AJUTOR = {}, CAMP = {}, ORDINE = [];
var ales = null, surseAcum = [], alegeri = null, asteapta = null, ultimulVazut = null;
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
function sursaAleasa(){ for(var i = 0; i < surseAcum.length; i++){ if(surseAcum[i].id === ales){ return surseAcum[i]; } } return null; }
function desenAlegeri(){
  var s = sursaAleasa(), c = $("alegeri"); c.textContent = "";
  ORDINE.forEach(function(k){
    var are = !s || s[CAMP[k]];
    var l = document.createElement("label"); l.className = "alegere" + (are ? "" : " stins");
    var i = document.createElement("input"); i.type = "checkbox"; i.id = "a-" + k;
    i.checked = are && !!alegeri[k]; i.disabled = !are;
    i.addEventListener("change", function(){ alegeri[k] = i.checked; });
    var t = document.createElement("span"); t.textContent = ETICHETE[k] + (are ? "" : " (lipsește din copie)");
    if(AJUTOR[k]){ var d = document.createElement("span"); d.className = "desc"; d.textContent = AJUTOR[k]; t.appendChild(d); }
    l.appendChild(i); l.appendChild(t);
    c.appendChild(l);
  });
  $("importa").disabled = !s || asteapta === "import";
}
function desenSurse(d){
  var c = $("surse"); c.textContent = "";
  surseAcum = d.surse || [];
  if(!surseAcum.length){
    var p = document.createElement("p"); p.className = "mesaj";
    p.textContent = d.cauta ? "Se caută copiile pe stick-uri, discuri și în memoria receptorului..." : (d.fara || "");
    c.appendChild(p); ales = null; desenAlegeri(); return;
  }
  if(!sursaAleasa()){ ales = surseAcum[0].id; }
  var ultim = null;
  surseAcum.forEach(function(s){
    if(s.mediu_nume !== ultim){
      ultim = s.mediu_nume;
      var h = document.createElement("div"); h.className = "mediu"; h.textContent = s.mediu_nume; c.appendChild(h);
    }
    var l = document.createElement("label"); l.className = "sursa";
    var i = document.createElement("input"); i.type = "radio"; i.name = "sursa"; i.checked = s.id === ales;
    i.addEventListener("change", function(){ ales = s.id; desenAlegeri(); });
    var t = document.createElement("span"); t.textContent = s.text;
    var ds = document.createElement("span"); ds.className = "desc"; ds.textContent = s.descriere;
    t.appendChild(ds); l.appendChild(i); l.appendChild(t); c.appendChild(l);
  });
  desenAlegeri();
}
function desenSetari(texte){
  $("card-setari").classList.toggle("ascuns", !(texte && texte.length));
  var c = $("setari"); c.textContent = "";
  (texte || []).forEach(function(t){ var p = document.createElement("p"); p.className = "nota"; p.textContent = t; c.appendChild(p); });
}
var ceasCiteste = null;
function programeaza(ms){
  if(ceasCiteste){ clearTimeout(ceasCiteste); }
  ceasCiteste = setTimeout(function(){ ceasCiteste = null; citeste(false); }, ms);
}
function lista(ul, texte){
  ul.textContent = "";
  (texte || []).forEach(function(t){ var li = document.createElement("li"); li.textContent = t; ul.appendChild(li); });
}
function mesajAlta(text, eroare){ var m = $("alta-mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
// intrebarea primei porniri (copia altei imagini): aceeasi stare ca pe televizor
function desenAlta(a){
  a = a || {};
  var deschisa = a.stare === "intrebare", lucreaza = a.stare === "da", rez = a.stare === "gata" && a.rezumat;
  $("card-alta").classList.toggle("ascuns", !(deschisa || lucreaza || rez));
  $("alta-intrebare-bloc").classList.toggle("ascuns", !deschisa);
  $("alta-lucreaza").classList.toggle("ascuns", !lucreaza);
  $("alta-rezumat").classList.toggle("ascuns", !rez);
  if(deschisa){
    var s = a.sursa || {};
    $("alta-intrebare").textContent = a.intrebare || "";
    $("alta-sursa").textContent = (s.mediu_nume ? s.mediu_nume + ": " : "") + (s.text || "");
    $("alta-ce").textContent = a.ce_se_aduce || "";
  }
  if(rez){
    var r = a.rezumat;
    $("alta-rez-bun").classList.toggle("ascuns", !r.ok);
    $("alta-rez-text").classList.toggle("ascuns", !!r.ok);
    $("alta-rez-text").textContent = r.ok ? "" : (r.text || "");
    lista($("alta-adus"), r.adus); lista($("alta-neadus"), r.neadus);
    if(r.ok && r.pachete && r.pachete.oferite && r.pachete.oferite.length && !pluginuriVazute){
      pluginuriVazute = true; desenPluginuri(r.pachete.oferite);
    }
    $("alta-reporneste").classList.toggle("ascuns", !(r.ok && r.repornire));
  }
}
// oferta pluginurilor din copie: aceeasi intrebare ca la Extensii si aplicatii (/api/extensii-instaleaza, doi pasi)
var pluginuriVazute = false;
function mesajPluginuri(text, eroare){ var m = $("mesaj-pluginuri"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function desenPluginuri(oferite){
  var c = $("pluginuri"); c.textContent = "";
  $("card-pluginuri").classList.toggle("ascuns", !(oferite && oferite.length));
  (oferite || []).forEach(function(p){
    var r = document.createElement("div"); r.className = "butoane";
    var t = document.createElement("span"); t.textContent = p[1] || p[0]; t.style.flex = "1"; t.style.alignSelf = "center";
    var b = document.createElement("button"); b.type = "button"; b.textContent = "Instalează";
    b.addEventListener("click", function(){ instaleazaPlugin(p[0], b); });
    r.appendChild(t); r.appendChild(b); c.appendChild(r);
  });
}
function instaleazaPlugin(nume, b){
  var q = "/api/extensii-instaleaza?pachet=" + encodeURIComponent(nume);
  b.disabled = true;
  cerere(q + "&pas=intreaba", "POST").then(function(d){
    if(!d.result || !d.confirmare){ mesajPluginuri(d.message, true); b.disabled = false; return; }
    var cf = d.confirmare;
    if(!confirm(cf.intrebare + ((cf.detalii && cf.detalii.length) ? "\\n\\n" + cf.detalii.join("\\n") : ""))){
      cerere(q + "&pas=renunta", "POST").catch(function(){}); b.disabled = false; return;
    }
    return cerere(q + "&cod=" + encodeURIComponent(cf.cod), "POST").then(function(r){
      mesajPluginuri(r.message, !r.result); if(!r.result){ b.disabled = false; }
    });
  }).catch(function(){ mesajPluginuri("Receptorul nu răspunde.", true); b.disabled = false; });
}
function raspundeAlta(r){
  $("alta-da").disabled = true; $("alta-nu").disabled = true;
  cerere("/api/import-alta-imagine?raspuns=" + r, "POST").then(function(d){
    mesajAlta(d.message, !d.result);
    if(d.alta_imagine){ desenAlta(d.alta_imagine); }
    programeaza(800);
  }).catch(function(){ mesajAlta("Receptorul nu răspunde.", true); }).then(function(){
    $("alta-da").disabled = false; $("alta-nu").disabled = false;
  });
}
function citeste(cauta){
  return cerere("/api/import-surse" + (cauta ? "?cauta=1" : "")).then(function(d){
    if(!d.result){ mesaj(d.message || "Receptorul nu a putut citi sursele.", true); return d; }
    if(!alegeri){ alegeri = d.implicite || {canale: true, tunere: true}; }
    if(d.alegeri){ ORDINE = d.alegeri; ETICHETE = d.etichete || {}; AJUTOR = d.ajutor || {}; CAMP = d.campuri || {}; }
    desenSurse(d); desenSetari(d.setari); desenAlta(d.alta_imagine);
    if(asteapta === "import" && !d.ocupat){
      asteapta = null;
      var u = d.ultimul || {mesaje: []};
      mesaj((u.mesaje || []).join("\\n"), !u.ok);
      desenPluginuri((u.pachete || {}).oferite);
      desenAlegeri();
    }
    if(asteapta === "cauta" && !d.cauta){ asteapta = null; }
    var alta = d.alta_imagine || {};
    if(d.cauta || (asteapta === "import") || alta.stare === "da"){ programeaza(1000); }
    else if(alta.stare === "intrebare"){ programeaza(3000); }
    return d;
  }).catch(function(){ mesaj("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); });
}
$("alta-da").addEventListener("click", function(){ raspundeAlta("da"); });
$("alta-nu").addEventListener("click", function(){ raspundeAlta("nu"); });
$("alta-ascunde").addEventListener("click", function(){
  cerere("/api/import-alta-imagine?raspuns=ascunde", "POST").then(function(d){ mesajAlta(""); desenAlta(d.alta_imagine); }).catch(function(){});
});
$("alta-reporneste").addEventListener("click", function(){
  if(!confirm("Interfața repornește acum, ca să intre setările antenei. Continui?")){ return; }
  cerere("/api/setari-din-copie-reporneste", "POST").then(function(d){ mesajAlta(d.message || "", !d.result); }).catch(function(){ mesajAlta("Interfața repornește..."); });
});
$("cauta").addEventListener("click", function(){ asteapta = "cauta"; mesaj(""); $("surse").textContent = "Se caută..."; citeste(true); });
$("importa").addEventListener("click", function(){
  var s = sursaAleasa(); if(!s){ return; }
  var q = [];
  ORDINE.forEach(function(k){ q.push(k + "=" + (($("a-" + k) || {}).checked ? "1" : "0")); });
  var retea = ($("a-retea") || {}).checked ? "\\n\\n" + "Rețeaua se schimbă: legătura poate cădea câteva secunde." : "";
  if(!confirm("Canalele și setările alese se înlocuiesc cu cele din:" + "\\n" + s.text + "\\n\\n" +
    "Cele de acum se păstrează într-o copie de siguranță pe receptor. Continui?" + retea)){ return; }
  $("importa").disabled = true; mesaj("Se pregătește copia...");
  cerere("/api/import?sursa=" + encodeURIComponent(s.id) + "&" + q.join("&"), "POST").then(function(d){
    if(!d.result){ mesaj(d.message, true); desenAlegeri(); return; }
    asteapta = "import"; mesaj(d.message); programeaza(800);
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); desenAlegeri(); });
});
citeste(false);
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
		N_("Import canale și setări"),
		N_("Canalele din altă imagine"),
		N_("Da, adu-le"),
		N_("Nu"),
		N_("Se aduc canalele și setările..."),
		N_("Am adus"),
		N_("Nu am adus"),
		N_("Repornește interfața acum"),
		N_("Am înțeles"),
		N_("Copia din care se importă"),
		N_("Se caută copiile..."),
		N_("Caută din nou"),
		N_("Ce se importă"),
		N_("Importă"),
		N_("Setările importate"),
		N_("Pluginurile din copie"),
		N_("Sunt în sursele receptorului și nu sunt instalate. Fiecare are întrebarea lui, ca la Extensii și aplicații."),
		N_("<a href=\"/setari-din-copie\">Setările importate</a>: starea lor și repornirea interfeței."),
		N_("Înainte de import, receptorul păstrează canalele și setările de acum într-o copie de siguranță, "
			"care apare apoi în lista de mai sus („Copiile de siguranță de pe receptor”; se păstrează "
			"ultimele cinci): cu ea importul se poate întoarce. Setările alese intră la următoarea pornire a "
			"interfeței. Pe televizor: Meniu, Scanare, Import canale și setări."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Instalează"),
		N_("Rețeaua se schimbă: legătura poate cădea câteva secunde."),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("(lipsește din copie)"),
		N_("Se caută copiile pe stick-uri, discuri și în memoria receptorului..."),
		N_("Receptorul nu răspunde."),
		N_("Receptorul nu a putut citi sursele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Interfața repornește acum, ca să intre setările antenei. Continui?"),
		N_("Interfața repornește..."),
		N_("Se caută..."),
		N_("Canalele și setările alese se înlocuiesc cu cele din:"),
		N_("Cele de acum se păstrează într-o copie de siguranță pe receptor. Continui?"),
		N_("Se pregătește copia..."),
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

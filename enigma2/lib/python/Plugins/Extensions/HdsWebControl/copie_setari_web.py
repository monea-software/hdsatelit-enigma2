# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# copie_setari_web.py: „Copia setărilor” in interfata web (HdsWebControl).
#
# Orice ecran de pe receptor are pereche in interfata web. Pe televizor: Meniu > Setari > Software & Firmware > Copia
# setarilor (Screens/HdsCopieSetari.py). Aici: aceleasi medii (stickul de actualizare ales intai), aceleasi copii,
# aceeasi copie automata, aceeasi punere la loc si stergere, din acelasi modul (Components/HdsCopieSetari.py): copia si
# cautarea pe firul lor, punerea la loc la repornirea interfetei (enigma2.sh), niciodata cat interfata ruleaza.
# Raspunsurile au numai nume, date si numere: niciun continut din copie (parolele Wi-Fi, setarile modulelor, jetonul).
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/copie-setari[?cauta=1]                 mediile, copiile, copia automata, lucrul in curs, ultimul rezultat
#   POST /api/copie-setari-fa?mediu=<id>             face copia acum (pe firul ei)
#   POST /api/copie-setari-pune?copie=<id>           cere punerea la loc si reporneste interfata
#   POST /api/copie-setari-sterge?copie=<id>         sterge copia
#   POST /api/copie-setari-automat?automat=oprita|zilnic&pastrate=<1-10>
#   GET  /copie-setari                               pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 si raspund pe loc; copia si cautarea merg pe firul lor, iar
# pagina intreaba din nou. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (M).


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsCopieSetari
	return HdsCopieSetari


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


def copie_publica(M, c):
	return {
		"id": c["id"],
		"titlu": _t("Copia din %s") % c["data_text"],
		"data": c["data_text"],
		"versiune": c["versiune"] or "?",
		"acest": bool(c["acest"]),
		"receptor": _t("acest receptor") if c["acest"] else _t("alt receptor"),
		"automata": c["fel"] == "automata",
		"mediu_nume": c["mediu_nume"],
		"descriere": M.descriere_copie(c),
		"marime_kb": int((c.get("marime") or 0) + 1023) // 1024,
		"intrebare_pune": M.text_intrebare_punere(c),
		"intrebare_sterge": M.text_intrebare_stergere(c),
	}


def stare(a, M=None):
	"""GET /api/copie-setari: prima cerere (sau cauta=1) porneste cautarea; celelalte citesc starea comuna."""
	M = _m(M)
	st = M.stare()
	if a.get("cauta") == "1" or (not st["cand"] and not st["cauta"]):
		try:
			M.porneste_cautarea()
		except Exception as eroare:
			return {"result": False, "message": _t("Căutarea nu a pornit: %s.") % eroare.__class__.__name__}
	st = M.stare()
	c = M.config_copie()
	implicit = M.mediu_implicit(st["medii"] or [])
	rez = M.citeste_rezultat()
	return {
		"result": True,
		"cauta": bool(st["cauta"]),
		"lucreaza": bool(st["lucreaza"]),
		"medii": [{"id": m["id"], "nume": m["nume"], "actualizare": bool(m.get("actualizare"))} for m in st["medii"] or []],
		"implicit": implicit["id"] if implicit else "",
		"copii": [copie_publica(M, x) for x in st["copii"] or []],
		"automat": c.automat.value,
		"pastrate": int(c.pastrate.value),
		"pastrate_maxim": M.PASTRATE_MAXIM,
		"text_automat": M.text_automat(),
		"avertisment": M.text_avertisment(),
		"ultimul": st["ultimul"],
		"cerere": bool(M.cerere_in_asteptare()),
		"punere": M.mesaj_rezultat(rez) if rez else "",
	}


def fa(a, M=None):
	M = _m(M)
	pornit, mesaj = M.porneste_copia(a.get("mediu", ""))
	return {"result": bool(pornit), "message": mesaj}


def pune(a, sesiune, M=None):
	"""POST /api/copie-setari-pune: cererea scrisa, apoi repornirea interfetei (ca din meniu); copia se pune la loc
	de enigma2.sh, inainte de pornirea interfetei."""
	M = _m(M)
	if sesiune is None:
		return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}
	ok, mesaj = M.cere_punerea(a.get("copie", ""), M.stare()["copii"] or None)
	if not ok:
		return {"result": False, "message": mesaj}
	from Screens.Standby import TryQuitMainloop
	sesiune.open(TryQuitMainloop, 3)
	return {"result": True, "message": _t("Interfața repornește și pune la loc copia. Pagina se reîncarcă singură.")}


def sterge(a, M=None):
	M = _m(M)
	ok, mesaj = M.sterge_copia(a.get("copie", ""), M.stare()["copii"] or None)
	if ok:
		M.porneste_cautarea()
	return {"result": bool(ok), "message": mesaj}


def automat(a, M=None):
	M = _m(M)
	ok, mesaj = M.seteaza_automat(a.get("automat") or None, a.get("pastrate") or None)
	return {"result": bool(ok), "message": mesaj}


def anuleaza(a, M=None):
	M = _m(M)
	M.anuleaza_cererea()
	return {"result": True, "message": _t("Copia nu se mai pune la loc.")}


def rute(baza, resource, M=None, sesiune=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care intoarce sesiunea enigma2 (plugin._sesiune se pune abia la pornirea sesiunii)."""

	class StareResource(baza):
		"""GET /api/copie-setari: numai citire (cautarea citeste mediile, nu scrie nimic)."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(argumente(request), M))
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
		"""GET /copie-setari: pagina „Copia setărilor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"copie-setari": StareResource(),
		b"copie-setari-fa": resursa(lambda a: fa(a, M)),
		b"copie-setari-pune": resursa(lambda a: pune(a, sesiune() if sesiune else None, M)),
		b"copie-setari-sterge": resursa(lambda a: sterge(a, M)),
		b"copie-setari-automat": resursa(lambda a: automat(a, M)),
		b"copie-setari-anuleaza": resursa(lambda a: anuleaza(a, M)),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /import: reteaua locala, apoi ?token= sau cookie-ul browserului asociat."""
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
<title>Copia setărilor</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  label.alegere{display:flex;gap:10px;align-items:center;min-height:44px;cursor:pointer;overflow-wrap:anywhere;}
  label.alegere input{min-width:20px;min-height:20px;}
  select{min-height:44px;padding:6px 10px;border-radius:8px;border:1px solid var(--bordura);background:#1b2130;color:#fff;font:inherit;max-width:100%;}
  .rand{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0;}
  .rand span{min-width:12em;}
  .copie{border-top:1px solid var(--bordura);padding:12px 0;}
  .copie:first-child{border-top:none;padding-top:0;}
  .titlu{font-weight:600;}
  .eticheta{display:inline-block;font-size:.8rem;padding:2px 8px;border-radius:10px;background:#2a3140;margin-left:6px;}
  .eticheta.acest{background:#1f5f1f;}
  .desc{color:var(--text-slab);font-size:.85rem;line-height:1.45;white-space:pre-line;overflow-wrap:anywhere;margin:4px 0 0;}
  .avertisment{color:#ffd28a;font-size:.9rem;line-height:1.45;margin:8px 0 0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;white-space:pre-line;}
  .mesaj:empty{display:none;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .butoane{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;}
  .intrebare{background:#1b2130;border:1px solid var(--bordura);border-radius:8px;padding:10px;margin-top:10px;line-height:1.45;}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#2a3140;color:#fff;font:inherit;cursor:pointer;}
  button.verde{background:#1f771f;}
  button.galben{background:#7a5a10;}
  button.rosu{background:#7a2420;}
  button:disabled{opacity:.5;cursor:default;}
</style>
</head>
<body>
<main>
<h1>Copia setărilor</h1>
<section class="card">
  <h2>Fă copia acum</h2>
  <div id="medii"><p class="mesaj">Se caută stickurile și discurile...</p></div>
  <p class="nota">Copia are canalele, buchetele, listele DAB+ și DVB-T2, setările, rețeaua și Wi-Fi, cheile SSH și
  modulele de acces condiționat. După o actualizare, imaginea nouă o pune singură la loc la prima pornire, dacă
  stickul e băgat.</p>
  <p class="avertisment" id="avertisment"></p>
  <div class="butoane"><button type="button" class="verde" id="fa" disabled>Fă copia acum</button>
  <button type="button" id="cauta">Caută din nou</button></div>
  <p class="mesaj" id="mesaj-copie"></p>
</section>
<section class="card">
  <h2>Copie automată</h2>
  <div class="rand"><span>Copie automată</span><select id="automat"><option value="oprita">Oprită</option><option value="zilnic">Zilnic</option></select></div>
  <div class="rand"><span>Copii automate păstrate</span><select id="pastrate"></select></div>
  <p class="nota" id="text-automat"></p>
  <p class="nota">Copia automată merge pe stickul de actualizare, dacă e băgat, altfel pe primul stick sau disc găsit.
  Copiile făcute de mână nu se șterg singure.</p>
  <p class="mesaj" id="mesaj-automat"></p>
</section>
<section class="card">
  <h2>Copiile găsite</h2>
  <div id="cerere" class="intrebare ascuns">O copie așteaptă să fie pusă la loc la repornirea interfeței.
    <div class="butoane"><button type="button" id="anuleaza">Renunță la punerea la loc</button></div></div>
  <div id="copii"><p class="mesaj">Se caută copiile...</p></div>
  <p class="mesaj" id="mesaj-copii"></p>
</section>
<section class="card ascuns" id="card-punere">
  <h2>Ultima punere la loc</h2>
  <p class="desc" id="punere"></p>
</section>
<p class="nota">Pe televizor: Meniu, Setări, Software &amp; Firmware, Copia setărilor.</p>
</main>
<script>
var CFG = __CONFIG__;
var ales = null, asteapta = null, ultimaStare = null;
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
function mesaj(id, text, eroare){ var m = $(id); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function el(tip, clasa, text){ var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text !== undefined){ e.textContent = text; } return e; }
function desenMedii(d){
  var c = $("medii"); c.textContent = "";
  var lista = d.medii || [];
  if(!lista.length){
    c.appendChild(el("p", "mesaj", d.cauta ? "Se caută stickurile și discurile..." : "Bagă un stick USB sau un disc în receptor, apoi alege „Caută din nou”."));
    ales = null;
  } else {
    if(!lista.some(function(m){ return m.id === ales; })){ ales = d.implicit || lista[0].id; }
    lista.forEach(function(m){
      var l = el("label", "alegere"); var i = el("input"); i.type = "radio"; i.name = "mediu"; i.checked = m.id === ales;
      i.addEventListener("change", function(){ ales = m.id; });
      l.appendChild(i); l.appendChild(document.createTextNode(m.nume)); c.appendChild(l);
    });
  }
  $("fa").disabled = !ales || d.lucreaza || asteapta === "copie";
}
function intrebare(loc, text, da, cand){
  var vechi = loc.querySelector(".intrebare"); if(vechi){ vechi.remove(); }
  var q = el("div", "intrebare", text);
  var b = el("div", "butoane");
  var nu = el("button", "", "Nu"); var dab = el("button", "rosu", da);
  nu.type = "button"; dab.type = "button";
  nu.addEventListener("click", function(){ q.remove(); });
  dab.addEventListener("click", function(){ q.remove(); cand(); });
  b.appendChild(nu); b.appendChild(dab); q.appendChild(b); loc.appendChild(q); nu.focus();
}
function desenCopii(d){
  var c = $("copii"); c.textContent = "";
  var lista = d.copii || [];
  if(!lista.length){ c.appendChild(el("p", "mesaj", d.cauta ? "Se caută copiile..." : "Nicio copie găsită pe stickurile și discurile băgate.")); return; }
  lista.forEach(function(x){
    var r = el("div", "copie");
    var t = el("div", "titlu", x.titlu);
    t.appendChild(el("span", "eticheta" + (x.acest ? " acest" : ""), x.receptor));
    t.appendChild(el("span", "eticheta", "imaginea " + x.versiune));
    if(x.automata){ t.appendChild(el("span", "eticheta", "automată")); }
    r.appendChild(t);
    r.appendChild(el("p", "desc", x.descriere));
    var b = el("div", "butoane");
    var pune = el("button", "galben", "Pune la loc"); pune.type = "button";
    var sterge = el("button", "", "Șterge"); sterge.type = "button";
    pune.addEventListener("click", function(){
      intrebare(r, x.intrebare_pune,
        "Da, pune la loc", function(){
          mesaj("mesaj-copii", "Se cere punerea la loc...");
          cerere("/api/copie-setari-pune?copie=" + encodeURIComponent(x.id), "POST").then(function(d){
            mesaj("mesaj-copii", d.message, !d.result);
            if(d.result){ setTimeout(function(){ location.reload(); }, 20000); }
          }).catch(function(){ mesaj("mesaj-copii", "Receptorul nu răspunde.", true); });
        });
    });
    sterge.addEventListener("click", function(){
      intrebare(r, x.intrebare_sterge, "Da, șterge", function(){
        cerere("/api/copie-setari-sterge?copie=" + encodeURIComponent(x.id), "POST").then(function(d){
          mesaj("mesaj-copii", d.message, !d.result); setTimeout(citeste, 600);
        }).catch(function(){ mesaj("mesaj-copii", "Receptorul nu răspunde.", true); });
      });
    });
    b.appendChild(pune); b.appendChild(sterge); r.appendChild(b); c.appendChild(r);
  });
}
function desenAutomat(d){
  var s = $("pastrate");
  if(!s.options.length){ for(var i = 1; i <= (d.pastrate_maxim || 10); i++){ var o = el("option", "", String(i)); o.value = String(i); s.appendChild(o); } }
  if(document.activeElement !== $("automat")){ $("automat").value = d.automat; }
  if(document.activeElement !== s){ s.value = String(d.pastrate); }
  s.disabled = d.automat !== "zilnic";
  $("text-automat").textContent = d.text_automat || "";
}
function citeste(cauta){
  return cerere("/api/copie-setari" + (cauta ? "?cauta=1" : "")).then(function(d){
    if(!d.result){ mesaj("mesaj-copie", d.message || "Receptorul nu a putut citi starea.", true); return; }
    ultimaStare = d;
    $("avertisment").textContent = d.avertisment || "";
    desenMedii(d); desenCopii(d); desenAutomat(d);
    $("cerere").classList.toggle("ascuns", !d.cerere);
    $("card-punere").classList.toggle("ascuns", !d.punere); $("punere").textContent = d.punere || "";
    if(asteapta === "copie" && !d.lucreaza){
      asteapta = null;
      var u = d.ultimul || {mesaje: []};
      mesaj("mesaj-copie", (u.mesaje || []).join("\\n"), !u.ok);
      desenMedii(d);
    }
    if(d.cauta || d.lucreaza || asteapta){ setTimeout(citeste, 1000); }
  }).catch(function(){ mesaj("mesaj-copie", "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.", true); });
}
$("fa").addEventListener("click", function(){
  if(!ales){ return; }
  $("fa").disabled = true; mesaj("mesaj-copie", "Se face copia. Nu scoate stickul până nu scrie „Copia e gata”.");
  cerere("/api/copie-setari-fa?mediu=" + encodeURIComponent(ales), "POST").then(function(d){
    if(!d.result){ mesaj("mesaj-copie", d.message, true); $("fa").disabled = false; return; }
    asteapta = "copie"; setTimeout(citeste, 800);
  }).catch(function(){ mesaj("mesaj-copie", "Receptorul nu răspunde.", true); $("fa").disabled = false; });
});
$("cauta").addEventListener("click", function(){ mesaj("mesaj-copie", ""); citeste(true); });
function salveazaAutomat(){
  cerere("/api/copie-setari-automat?automat=" + $("automat").value + "&pastrate=" + $("pastrate").value, "POST").then(function(d){
    mesaj("mesaj-automat", d.message, !d.result); citeste();
  }).catch(function(){ mesaj("mesaj-automat", "Receptorul nu răspunde.", true); });
}
$("automat").addEventListener("change", salveazaAutomat);
$("pastrate").addEventListener("change", salveazaAutomat);
$("anuleaza").addEventListener("click", function(){
  cerere("/api/copie-setari-anuleaza", "POST").then(function(d){ mesaj("mesaj-copii", d.message, !d.result); citeste(); });
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
		N_("Copia setărilor"),
		N_("Fă copia acum"),
		N_("Se caută stickurile și discurile..."),
		N_("Copia are canalele, buchetele, listele DAB+ și DVB-T2, setările, rețeaua și Wi-Fi, cheile SSH "
			"și modulele de acces condiționat. După o actualizare, imaginea nouă o pune singură la loc la "
			"prima pornire, dacă stickul e băgat."),
		N_("Caută din nou"),
		N_("Copie automată"),
		N_("Oprită"),
		N_("Zilnic"),
		N_("Copii automate păstrate"),
		N_("Copia automată merge pe stickul de actualizare, dacă e băgat, altfel pe primul stick sau disc "
			"găsit. Copiile făcute de mână nu se șterg singure."),
		N_("Copiile găsite"),
		N_("O copie așteaptă să fie pusă la loc la repornirea interfeței."),
		N_("Renunță la punerea la loc"),
		N_("Se caută copiile..."),
		N_("Ultima punere la loc"),
		N_("Pe televizor: Meniu, Setări, Software &amp; Firmware, Copia setărilor."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se caută stickurile și discurile..."),
		N_("Bagă un stick USB sau un disc în receptor, apoi alege „Caută din nou”."),
		N_("Nu"),
		N_("Se caută copiile..."),
		N_("Nicio copie găsită pe stickurile și discurile băgate."),
		N_("imaginea"),
		N_("automată"),
		N_("Pune la loc"),
		N_("Șterge"),
		N_("Da, pune la loc"),
		N_("Se cere punerea la loc..."),
		N_("Receptorul nu răspunde."),
		N_("Da, șterge"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se face copia. Nu scoate stickul până nu scrie „Copia e gata”."),
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

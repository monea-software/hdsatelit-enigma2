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
# si multumirile (A.stareConcluzii). Cat exista copia setarilor facuta cand a intrat echipa (A.stareCopie, si dupa
# oprire), pagina arata ziua si ora ei si butonul "Pune înapoi cum era", perechea tastei Albastre de pe receptor: o
# intrebare in pagina (aceeasi ca la "Copia setărilor", cu Nu / Da, pune la loc; fara fereastra browserului, ca restul
# paginii), apoi cererea si repornirea interfetei, ca la /api/copie-setari-pune; sesiunea nu se opreste.
# Start porneste pe loc din orice browser acceptat de poarta locala, cu termenii bifati.
# Nu cere asocierea cu codul de pe televizor. HdsAsistentaSemn.pornesteWeb anunta pe receptor
# ca a pornit din web, fara sa ceara o apasare acolo. Exteriorul ramane respins de poarta comuna.
# Oprirea merge din orice browser acceptat. Cat asistenta e activa, paginile web au sus
# o banda (bandaWeb, pusa de meniu_comun_web.pagina).
#
# Rute (poarta comuna meniu_comun_web; ce schimba ceva cere, cu cookie, POST si antetul CSRF):
#   GET  /api/asistenta            starea, pana cand e pornita, ultimele randuri din jurnal (fara cod), ultimele
#                                  concluzii ale echipei
#   GET  /api/asistenta-catalog    lista operatiilor in limba receptorului
#   POST /api/asistenta-cere?accept=1   Start (accept=1: randul "Accept termenii și condițiile" bifat); asistenta
#                                       pornita e mereu completa (nivelul B)
#   POST /api/asistenta-opreste    opreste
#   POST /api/asistenta-pune-inapoi     "Pune înapoi cum era": cere punerea la loc a copiei de asistenta si reporneste
#                                       interfata (A.cerePunereaInapoi)
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


def stare(request=None, A=None, B=None):
	"""Starea pentru pagina (si pentru banda): fara codul sesiunii, care ramane intern."""
	A = _a(A)
	s = A.stare()
	return {"result": True, "stare": s.get("stare"), "disponibil": s.get("disponibil"),
		"eroare_pornire": s.get("eroare_pornire") or "",
		"setari_internet": "/retea" if s.get("eroare_pornire") else "",
		"ramas_s": s.get("ramas_s", 0), "jurnal": s.get("jurnal", []), "nivel": s.get("nivel"),
		"durata_implicita": s.get("durata_implicita"),
		# pana cand e pornita, tradus ("Pornită până la ZZ.LL, HH:MM." / "Pornită, fără sfârșit; ...")
		"permanent": bool(s.get("permanent")), "pana_text": s.get("pana_text") or "",
		"concluzii": _concluzii(A),
		# copia pentru "Pune înapoi cum era" ({"data_text", "text", "intrebare"}) sau None
		"copie": s.get("copie")}


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
	rez.update({"result": bool(reusit) and not bool(rez["eroare_pornire"]),
		"message": rez["eroare_pornire"] or mesaj})
	return rez


def opreste(A=None):
	A = _a(A)
	reusit, mesaj = A.opreste("de om (web)")
	rez = stare(None, A)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def scriereSecret(C=None):
	"""Numai permisiunea de scriere, fara valoarea campului si fara jurnalul asistentei."""
	if C is None:
		from Components import HdsAsistentaControl as C
	try:
		activa = C.asistentaActiva()
	except Exception:
		return {"result": False, "permisa": False,
			"message": _t("Nu pot verifica asistența. Încearcă din nou înainte să scrii parola sau cheia.")}
	return {"result": True, "permisa": not activa,
		"message": _t(C.TEXT_OPRESTE_SECRET) if activa else ""}


def protejeazaScrierea(text):
	"""Acelasi paznic pentru toate campurile web, inclusiv pagina de intrare."""
	if "</body>" not in text or 'id="hds-scriere-secret"' in text:
		return text
	import json
	config = {"eroare": _t("Nu pot verifica asistența. Încearcă din nou înainte să scrii parola sau cheia."),
		"inchide": _t("Închide"), "opreste": _t("Oprește asistența"),
		"pe_tv": _t("Oprește asistența de pe televizor, apoi revino aici.")}
	script = SCRIPT_SCRIERE_SECRET.replace("__TEXTE_SECRET__", json.dumps(config, ensure_ascii=True))
	return text.replace("</body>", script + "</body>", 1)


SCRIPT_SCRIERE_SECRET = r'''
<script id="hds-scriere-secret">
(function(){
  "use strict";
  var texte = __TEXTE_SECRET__, anterior = new WeakMap(), lipite = new WeakMap();
  var inserare = new WeakSet(), coada = Promise.resolve(), inCurs = 0, avertisment = null;
  function secret(c){
    if(!c || !/^(INPUT|TEXTAREA)$/.test(c.tagName)){ return false; }
    if(c.dataset.hdsSecret === "1" || c.type === "password"){ return true; }
    var nume = [c.id || "", c.name || "", c.autocomplete || ""].join(" ");
    if(/parol|passw|secret|token|(^|[ _-])pin|cheie|api[_-]?key/i.test(nume)){ return true; }
    return c.classList.contains("pin");
  }
  function anunta(text){
    if(avertisment){ avertisment.querySelector("p").textContent = text; return; }
    var d = document.createElement("dialog"), p = document.createElement("p");
    p.textContent = text; d.appendChild(p);
    var cfg = window.CFG || {};
    if(cfg.csrf || cfg.jeton){
      var a = document.createElement("button"); a.type = "button"; a.textContent = texte.opreste;
      a.onclick = function(){
        a.disabled = true;
        var h = {}; if(cfg.csrf){ h["X-HDS-CSRF"] = cfg.csrf; }
        var url = "/api/asistenta-opreste" + (cfg.jeton ? "?token=" + encodeURIComponent(cfg.jeton) : "");
        fetch(url, {method:"POST", credentials:"same-origin", cache:"no-store", headers:h})
          .then(function(r){ return r.json(); }).then(function(r){
            if(!r.result){ p.textContent = r.message || texte.eroare; a.disabled = false; return; }
            d.close(); d.remove(); avertisment = null;
          }).catch(function(){ p.textContent = texte.eroare; a.disabled = false; });
      };
      d.appendChild(a);
    } else {
      var nota = document.createElement("p"); nota.textContent = texte.pe_tv; d.appendChild(nota);
    }
    var b = document.createElement("button"); b.type = "button"; b.textContent = texte.inchide;
    b.style.marginLeft = "1em";
    b.onclick = function(){ d.close(); d.remove(); avertisment = null; };
    d.addEventListener("cancel", function(){ d.remove(); avertisment = null; });
    d.appendChild(b); document.body.appendChild(d); avertisment = d; d.showModal(); b.focus();
  }
  function verifica(){
    // Cererea nu contine textul scris, nici macar numele campului.
    return fetch("/scriere-secret", {credentials:"same-origin", cache:"no-store"})
      .then(function(r){ if(!r.ok){ throw new Error("stare"); } return r.json(); });
  }
  function insereaza(c, text){
    var inceput = c.selectionStart, sfarsit = c.selectionEnd;
    if(inceput === null || sfarsit === null){ return; }
    if(c.maxLength >= 0){ text = text.slice(0, Math.max(0, c.maxLength - c.value.length + sfarsit - inceput)); }
    c.setRangeText(text, inceput, sfarsit, "end");
    anterior.set(c, c.value); inserare.add(c);
    c.dispatchEvent(new Event("input", {bubbles:true}));
    inserare.delete(c);
  }
  function puneInCoada(c, lucru, verificaStarea){
    inCurs++;
    coada = coada.then(function(){
      if(!verificaStarea){ if(c.isConnected){ lucru(); } return; }
      return verifica().then(function(d){
        if(!d.result || !d.permisa){ anunta(d.message || texte.eroare); return; }
        if(c.isConnected){ lucru(); }
      }).catch(function(){ anunta(texte.eroare); });
    }).then(function(){ inCurs--; }, function(){ inCurs--; anunta(texte.eroare); });
  }
  document.addEventListener("focusin", function(e){
    if(secret(e.target)){ anterior.set(e.target, e.target.value); }
  }, true);
  document.addEventListener("paste", function(e){
    if(secret(e.target) && e.clipboardData){ lipite.set(e.target, e.clipboardData.getData("text/plain")); }
  }, true);
  document.addEventListener("beforeinput", function(e){
    var c = e.target;
    if(!secret(c) || c.readOnly || c.disabled || !/^(insert|delete)/.test(e.inputType || "")){ return; }
    anterior.set(c, c.value);
    if(!e.cancelable){ return; }
    e.preventDefault(); e.stopImmediatePropagation();
    if(/^delete/.test(e.inputType)){
      var fel = e.inputType;
      puneInCoada(c, function(){
        var a = c.selectionStart, b = c.selectionEnd;
        if(a === null || b === null){ return; }
        if(a === b){
          if(/Backward$/.test(fel)){
            a = /Word/.test(fel) ? c.value.slice(0, a).replace(/\S+\s*$/, "").length : Math.max(0, a - 1);
            if(a > 0 && /[\uDC00-\uDFFF]/.test(c.value.charAt(a))){ a--; }
          } else if(/Forward$/.test(fel)){
            b = /Word/.test(fel) ? a + (c.value.slice(a).match(/^\s*\S+/) || [""])[0].length : Math.min(c.value.length, b + 1);
            if(b < c.value.length && /[\uD800-\uDBFF]/.test(c.value.charAt(b - 1))){ b++; }
          }
        }
        c.setRangeText("", a, b, "end"); anterior.set(c, c.value); inserare.add(c);
        c.dispatchEvent(new Event("input", {bubbles:true})); inserare.delete(c);
      }, false);
      return;
    }
    var text = e.data;
    if(text === null && e.dataTransfer){ text = e.dataTransfer.getData("text/plain"); }
    if(text === null){ text = lipite.get(c) || ""; } lipite.delete(c);
    if(!text){ return; }
    puneInCoada(c, function(){ insereaza(c, text); }, true);
  }, true);
  // Acopera si completarea automata ori compunerea pentru care beforeinput nu se poate opri.
  document.addEventListener("input", function(e){
    var c = e.target;
    if(!secret(c) || inserare.has(c)){ return; }
    e.stopImmediatePropagation();
    var nou = c.value; c.value = anterior.get(c) || "";
    puneInCoada(c, function(){
      c.value = nou; anterior.set(c, nou); inserare.add(c);
      c.dispatchEvent(new Event("input", {bubbles:true})); inserare.delete(c);
    }, true);
  }, true);
  // Salvarea asteapta verificarea ultimului caracter; nu trimite o valoare incompleta.
  document.addEventListener("click", function(e){
    if(avertisment && avertisment.contains(e.target)){ return; }
    if(!inCurs || !e.target.closest("button,input[type=submit]")){ return; }
    e.preventDefault(); e.stopImmediatePropagation();
    var tinta = e.target;
    coada.then(function(){ if(tinta.isConnected && !avertisment){ tinta.click(); } });
  }, true);
  document.addEventListener("submit", function(e){
    if(!inCurs){ return; } e.preventDefault(); e.stopImmediatePropagation();
    var f = e.target, b = e.submitter;
    coada.then(function(){ if(f.isConnected && !avertisment){ f.requestSubmit(b || undefined); } });
  }, true);
})();
</script>
'''


def _sesiuneEnigma():
	try:
		from .meniu_comun_web import sesiune
		return sesiune()
	except Exception:
		return None


def puneInapoi(A=None, sesiune=None):
	"""POST /api/asistenta-pune-inapoi ("Pune înapoi cum era"): cererea de punere la loc a copiei facute cand a intrat
	echipa (A.cerePunereaInapoi), apoi repornirea interfetei, ca /api/copie-setari-pune; enigma2.sh pune copia la loc
	inainte de pornirea interfetei. Sesiunea de asistenta nu se opreste. sesiune: sesiunea enigma2 (probele dau una)."""
	A = _a(A)
	if sesiune is None:
		sesiune = _sesiuneEnigma()
	if sesiune is None:
		rez = stare(None, A)
		rez.update({"result": False, "message": _t("Interfața nu este gata pentru repornire.")})
		return rez
	ok, mesaj = A.cerePunereaInapoi()
	rez = stare(None, A)
	if not ok:
		rez.update({"result": False, "message": mesaj})
		return rez
	from Screens.Standby import TryQuitMainloop
	sesiune.open(TryQuitMainloop, 3)
	rez.update({"result": True,
		"message": _t("Interfața repornește și pune la loc copia. Pagina se reîncarcă singură.")})
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
	for nume in ("accept",):
		valori = args.get(nume.encode("ascii"))
		if valori:
			v = valori[0]
			if isinstance(v, bytes):
				v = v[:8].decode("utf-8", "replace")
			rez[nume] = v[:2]
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
				# Poarta comuna a verificat reteaua locala si cererea; Start nu mai cere codul TV.
				return self._raspunde(request, cere(_argumente(request), A, de_incredere=True))
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

	class PuneInapoiResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, puneInapoi(A))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

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
		b"asistenta-pune-inapoi": PuneInapoiResource(),
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
  .intrebare{background:#1b2130;border:1px solid var(--bordura);border-radius:8px;padding:10px;margin-top:10px;line-height:1.45;}
  .intrebare p{margin:0 0 10px;}
  .intrebare button{margin:0 8px 0 0;}
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
  <p class="scurt">Echipa HD Satelit vede ecranele, setările și imaginea canalului și poate controla receptorul prin toate meniurile. Numele de utilizator, parolele, PIN-urile și cheile nu ajung la echipă. Oprește asistența cât scrii o parolă sau o cheie, până o salvezi. Poți opri oricând.</p>
  <label class="bifa"><input type="checkbox" id="accept" checked><span>Accept <a href="#" id="termeni">termenii și condițiile</a></span></label>
  <button class="verde" id="porneste">Start</button>
  <p class="mesaj" id="mesaj"></p>
  <p class="ascuns" id="internet"><a id="setariInternet" href="/retea">Setările de internet</a></p>
</section>
<section class="card ascuns" id="pornita">
  <p class="pana" id="stare"></p>
  <button class="rosu" id="opreste">Oprește</button>
  <p class="mesaj" id="mesajOprire"></p>
  <p class="nota ascuns" id="asteptare">Te anunțăm când intrăm. Poți folosi receptorul între timp.</p>
  <p class="nota ascuns" id="asteptareNuOpri">Dacă nu intrăm imediat, las-o pornită măcar 30 de minute: poate ajutăm pe altcineva chiar acum.</p>
  <p class="nota">Jurnalul asistenței</p>
  <pre class="jurnal" id="jurnal"></pre>
</section>
<section class="card ascuns" id="copie">
  <p class="pana" id="copieText"></p>
  <p class="nota">Copia se face singură când intră echipa, înainte de orice schimbare. Butonul pune la loc canalele, setările și rețeaua de atunci; interfața repornește.</p>
  <button class="gri" id="puneInapoi">Pune înapoi cum era</button>
  <div class="intrebare ascuns" id="intrebareCopie"><p id="intrebareText"></p>
    <button class="gri" id="copieNu">Nu</button>
    <button class="rosu" id="copieDa">Da, pune la loc</button>
  </div>
  <p class="mesaj" id="mesajCopie"></p>
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
var copiaInapoi = null;
var eroarePornireVazuta = "";
var startCuFocus = false;
function arata(d){
  var activa = !!d.stare && d.stare!=="oprit";
  $("indisponibil").classList.toggle("ascuns", !!d.disponibil || activa);
  $("pornire").classList.toggle("ascuns", activa || !d.disponibil);
  // randul 170 (perechea OK-ului de pe receptor): prima data cand se vede pagina de pornire, Start primeste focusul,
  // deci Enter (sau OK din telecomanda navigatorului) porneste asistenta dintr-un pas; nu fura focusul altui camp
  if(!activa && d.disponibil && !startCuFocus){ startCuFocus = true;
    if(!document.activeElement || document.activeElement===document.body){ $("porneste").focus(); } }
  $("pornita").classList.toggle("ascuns", !activa);
  if(d.eroare_pornire){ mesaj("mesaj", d.eroare_pornire, true); }
  else if(eroarePornireVazuta){ mesaj("mesaj", ""); }
  eroarePornireVazuta = d.eroare_pornire || "";
  $("internet").classList.toggle("ascuns", !d.eroare_pornire);
  $("setariInternet").href = adresa("/retea");
  $("stare").textContent = d.pana_text || "";
  $("asteptare").classList.toggle("ascuns", d.stare!=="asteapta");
  $("asteptareNuOpri").classList.toggle("ascuns", d.stare!=="asteapta");
  $("jurnal").textContent = (d.jurnal||[]).join("\\n") || "Jurnalul e gol.";
  var c = d.concluzii;
  $("concluzii").classList.toggle("ascuns", !(c && c.text));
  if(c && c.text){ $("concluziiText").textContent = c.text; $("concluziiOra").textContent = c.ora_text || ""; }
  copiaInapoi = d.copie || null;
  $("copie").classList.toggle("ascuns", !copiaInapoi);
  $("copieText").textContent = copiaInapoi ? (copiaInapoi.text || "") : "";
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
$("puneInapoi").addEventListener("click", function(){
  if(!copiaInapoi){ return; }
  $("intrebareText").textContent = copiaInapoi.intrebare || "";
  $("intrebareCopie").classList.remove("ascuns"); $("copieNu").focus(); });
$("copieNu").addEventListener("click", function(){ $("intrebareCopie").classList.add("ascuns"); });
$("copieDa").addEventListener("click", function(){
  $("intrebareCopie").classList.add("ascuns");
  mesaj("mesajCopie", "Se cere punerea la loc...");
  cerere("/api/asistenta-pune-inapoi","POST", new URLSearchParams()).then(function(d){ mesaj("mesajCopie", d.message, !d.result); if(d.result){ setTimeout(function(){ location.reload(); }, 20000); } }).catch(function(){ mesaj("mesajCopie", nuRaspunde(), true); }); });
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
		N_("Echipa HD Satelit vede ecranele, setările și imaginea canalului și poate controla receptorul prin toate "
			"meniurile. Numele de utilizator, parolele, PIN-urile și cheile nu ajung la echipă. Oprește asistența cât "
			"scrii o parolă sau o cheie, până o salvezi. Poți opri oricând."),
		N_("Accept <a href=\"#\" id=\"termeni\">termenii și condițiile</a>"),
		N_("Start"),
		N_("Setările de internet"),
		N_("Oprește"),
		N_("Te anunțăm când intrăm. Poți folosi receptorul între timp."),
		N_("Dacă nu intrăm imediat, las-o pornită măcar 30 de minute: poate ajutăm pe altcineva chiar acum."),
		N_("Jurnalul asistenței"),
		N_("Termenii și condițiile"),
		N_("Închide"),
		N_("Copia se face singură când intră echipa, înainte de orice schimbare. Butonul pune la loc canalele, "
			"setările și rețeaua de atunci; interfața repornește."),
		N_("Pune înapoi cum era"),
		N_("Nu"),
		N_("Da, pune la loc"),
		N_("Ce am găsit și ce am făcut"),
		N_("Mulțumim că ne-ai lăsat să te ajutăm."),
	),
	"js": (
		N_("Receptorul nu răspunde."),
		N_("Jurnalul e gol."),
		N_("Fără bifă, asistența nu pornește."),
		N_("Se pornește..."),
		N_("Se oprește..."),
		N_("Se cere punerea la loc..."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon.replace("__DRUM_MENIU__", _drumMeniu())
	return traduce(sablon, TEXTE_PAGINA, fel).replace("__DRUM_MENIU__", _drumMeniu())

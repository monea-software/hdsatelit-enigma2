# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# mod_sigur_web.py: „Mod sigur” in interfata web (HdsWebControl).
#
# Orice ecran de pe receptor are pereche in interfata web. Pe televizor: mesajul modului sigur, primul ecran dupa 5
# opriri neasteptate ale interfetei in 10 minute, si ecranul „Ce s-a întâmplat” (Screens/HdsModSigur.py). Aici: acelasi
# mesaj, aceleasi alegeri (numai cand interfata chiar ruleaza in modul sigur, ca pe televizor), aceleasi randuri pe
# grupe si, ca optiune, textul brut al fisierelor (jurnalul opririlor, rapoartele de eroare, numaratoarea), fara
# randurile cu jetonul web sau cu parole. In afara modului sigur pagina arata opririle si ultima eroare.
#
# O SINGURA LOGICA: starea, alegerile si textele sunt in Components/HdsModSigur.py.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/mod-sigur                              starea, textele, alegerile, randurile, lista fisierelor brute
#   POST /api/mod-sigur-alege?alegere=normal|setari  cererea pentru enigma2.sh, apoi repornirea interfetei peste 1,5 s
#                                                    (TryQuitMainloop 3; pe televizor poate cere o confirmare)
#   GET  /api/mod-sigur-brut?pagina=<n>              textul brut al unui fisier (titlul scurt, calea separat)
#   GET  /mod-sigur                                  pagina (starea se citeste din nou la 60 s)
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Starea si textul brut citesc fisiere de zeci de KiB, deci
# pe receptor se citesc pe un fir (Components/HdsModSigur.peFir), iar raspunsul pleaca dupa (NOT_DONE_YET); fara
# Twisted (probele de pe PC) pe loc. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul
# lor (M).

import json

try:
	from twisted.web.server import NOT_DONE_YET
except ImportError:          # pe PC, fara Twisted: raspunsurile pleaca pe loc
	NOT_DONE_YET = None

try:
	from html import escape as _escape
except ImportError:  # Python 2 (probele vechi)
	from cgi import escape as _escape


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsModSigur
	return HdsModSigur


def stare(M=None):
	"""Pentru GET /api/mod-sigur."""
	M = _m(M)
	s = M.stare()
	if s.get("activ"):
		mesaj, explicatie = M.textMesaj(), M.textExplicatie(s)
		alegeri = [{"cheie": c, "titlu": t, "descriere": d, "se_poate": bool(p)} for c, t, d, p in M.alegeri(s)
			if c != "detalii"]
	else:
		mesaj = _t("Receptorul merge normal.")
		explicatie = _t("Modul sigur pornește singur după %d opriri neașteptate ale interfeței în 10 minute: atunci "
			"pornesc numai extensiile venite cu imaginea, iar aici și pe televizor poți alege cum continui.") % M.PRAG
		alegeri = []
	return {
		"result": True,
		"activ": bool(s.get("activ")),
		"titlu": M.titlu(),
		"mesaj": mesaj,
		"explicatie": explicatie,
		"alegeri": alegeri,
		"randuri": [list(r) for r in M.randuri(s)],
		"pagini": [{"titlu": t, "cale": c} for t, c, _x in M.paginiBrute(cu_text=False)],
	}


def bandaPanou(M=None):
	"""Textul benzii din panou (/api/statusinfo, cheia „mod_sigur”): "" in afara modului sigur. Ieftin: numai mediul."""
	try:
		return _m(M).textPanou()
	except Exception:
		return ""


def textFonturi(M=None):
	"""Fraza pentru /api/fonturi (cheia „mod_sigur”): "" in afara modului sigur."""
	try:
		return _m(M).textPentruFonturi()
	except Exception:
		return ""


def alege(argumente, M=None, sesiune=None):
	"""POST /api/mod-sigur-alege: „normal” sau „setari”, numai in modul sigur; apoi repornirea interfetei."""
	M = _m(M)
	alegere = (argumente.get("alegere") or "").strip()
	if alegere not in ("normal", "setari"):
		return {"result": False, "message": _t("Alegere necunoscută.")}
	if not M.activ():
		return {"result": False, "message": _t("Receptorul nu este în modul sigur.")}
	ok, text = M.pornesteNormal() if alegere == "normal" else M.punInapoiSetarile()
	if not ok:
		return {"result": False, "message": text}
	# TryQuitMainloop intreaba pe televizor cand o inregistrare e in curs sau aproape: raspunsul de aici nu poate sti
	# ce se alege acolo, deci o spune (la „Nu” cererea se sterge si modul sigur continua)
	intreaba = sesiune is not None and M.repornireCuIntrebare(sesiune)
	if not M.reporneste(sesiune, dupa_ms=1500):
		return {"result": True, "message": text + " " + _t("Alegerea se aplică la următoarea repornire a interfeței.")}
	if intreaba:
		return {"result": True, "message": text + " " + _t("Pe televizor se cere o confirmare: o înregistrare e în curs "
			"sau începe curând. Alegerea se face numai dacă răspunzi Da acolo.")}
	return {"result": True, "message": text + " " + _t("Interfața se repornește. Pagina se reîncarcă singură în "
		"câteva secunde.")}


def brut(argumente, M=None):
	"""GET /api/mod-sigur-brut?pagina=<n>: textul brut al unui fisier, fara secrete."""
	M = _m(M)
	pagini = M.paginiBrute()
	try:
		n = int(argumente.get("pagina") or 0)
	except ValueError:
		n = 0
	if not pagini:
		return {"result": False, "message": _t("Nu există niciun fișier de arătat.")}
	n %= len(pagini)
	titlu, cale, text = pagini[n]
	return {"result": True, "pagina": n, "numar": len(pagini), "titlu": titlu, "cale": cale, "text": text}


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
		rez[cheie] = str(v)[:12].strip()
	return rez


def rute(baza, resource, M=None, sesiune=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py;
	`sesiune` e o functie care intoarce sesiunea enigma2 (plugin._sesiune se pune abia la pornirea sesiunii)."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	def _peFir(obiect, request, lucru):
		"""lucru() pe un fir (Components/HdsModSigur.peFir), raspunsul trimis din firul enigma2; fara Twisted pe loc."""
		if NOT_DONE_YET is None:
			return obiect._raspunde(request, lucru())

		def gata(rez, eroare):
			try:
				if eroare is not None:
					request.write(obiect._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500))
				else:
					request.write(obiect._raspunde(request, rez))
				request.finish()
			except Exception as e:
				print("[HdsWebControl] mod sigur: raspunsul nu a plecat (browserul a plecat?): %s" % e)
		_m(M).peFir(lucru, gata)
		return NOT_DONE_YET

	class StareResource(baza):
		"""GET /api/mod-sigur: numai citire."""

		def render_GET(self, request):
			try:
				return _peFir(self, request, lambda: stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class AlegeResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, alege(argumente(request), M, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class BrutResource(baza):
		"""GET /api/mod-sigur-brut: numai citire."""

		def render_GET(self, request):
			try:
				arg = argumente(request)
				return _peFir(self, request, lambda: brut(arg, M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /mod-sigur: pagina „Mod sigur”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"mod-sigur": StareResource(),
		b"mod-sigur-alege": AlegeResource(),
		b"mod-sigur-brut": BrutResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /setari-din-copie si /accel."""
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
	return pagina_text(P._STIL_COMUN, config_pagina, _limba()).encode("utf-8", "replace")


def _limba():
	"""Codul limbii interfetei pentru <html lang> („ro”, „de” ...), „ro” daca nu se poate afla"""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	cod = "".join(ch for ch in cod if "a" <= ch <= "z")[:3]
	return cod or "ro"


def _e(text):
	return _escape(text or "", quote=True)


def texteScript():
	"""Textele folosite de scriptul paginii, traduse, ca JSON (scriptul nu are textele lui)."""
	return json.dumps({
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"neasteptat": _t("Receptorul a răspuns neașteptat."),
		"seAplica": _t("Se aplică alegerea..."),
		"textBrut": _t("Text brut"),
		"peScurt": _t("Pe scurt"),
	}, ensure_ascii=True).replace("</", "<\\/")


def pagina_text(stil, config_pagina, limba="ro"):
	inlocuiri = {
		"__STIL_COMUN__": stil,
		"__CONFIG__": config_pagina,
		"__TEXTE__": texteScript(),
		"__LIMBA__": _e(limba),
		"__TITLU__": _e(_t("Mod sigur")),
		"__SE_CITESTE__": _e(_t("Se citește starea...")),
		"__ALEGERI__": _e(_t("Ce poți face")),
		"__CE_S_A_INTAMPLAT__": _e(_t("Ce s-a întâmplat")),
		"__TEXT_BRUT__": _e(_t("Text brut")),
		"__NOTA_BRUT__": _e(_t("Fișierele așa cum sunt pe receptor, fără rândurile cu parole sau cu cheia interfeței web.")),
		"__FISIERUL__": _e(_t("Fișierul:")),
		"__NOTA_TV__": _e(_t("Pe televizor, același mesaj apare singur la pornire, în modul sigur, și din Meniu > "
			"Informații despre sistem > Mod sigur.")),
	}
	text = PAGINA
	for cheie, valoare in inlocuiri.items():
		text = text.replace(cheie, valoare)
	return text


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card.avertizare{border-color:#f5b83d;}
  .mare{font-size:1.1rem;line-height:1.45;margin:0 0 8px;font-weight:bold;}
  .acum{font-size:.98rem;line-height:1.45;margin:0;}
  .alegere{padding:10px 0;border-bottom:1px solid var(--bordura);}
  .alegere:last-child{border-bottom:0;}
  .alegere p{margin:6px 0 0;color:var(--text-slab);font-size:.9rem;line-height:1.45;}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.principal{background:#f5b83d;border-color:#f5b83d;color:#101828;}
  button:disabled{opacity:.5;cursor:default;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;max-width:100%;}
  table{width:100%;border-collapse:collapse;font-size:.92rem;}
  td{padding:7px 6px;border-bottom:1px solid var(--bordura);text-align:left;vertical-align:top;word-break:break-word;}
  td.eticheta{color:var(--text-slab);width:34%;}
  tr.grupa td{color:#9fb4ff;font-weight:bold;padding-top:14px;border-bottom:1px solid #2a3350;}
  tr.linie td{padding-top:3px;padding-bottom:3px;}
  tr.nota td{color:var(--text-slab);font-size:.82rem;padding-top:2px;}
  .bun{color:#4fd18b;} .atentie{color:#f5b83d;} .rau{color:#ff6b5e;} .stins{color:#8a94a6;}
  pre{white-space:pre-wrap;word-break:break-word;background:#0f1216;border:1px solid var(--bordura);border-radius:8px;padding:10px;font-size:.8rem;max-height:60vh;overflow:auto;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;align-items:center;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  #caleBrut{overflow-wrap:anywhere;word-break:break-all;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ td.eticheta{width:40%;} }
</style>
</head>
<body>
<main>
<h1>__TITLU__</h1>
<p class="mesaj" id="incarcare">__SE_CITESTE__</p>
<div id="continut" class="ascuns">
  <section class="card" id="cardStare"><p class="mare" id="mesajMare"></p><p class="acum" id="explicatie"></p></section>
  <section class="card ascuns" id="cardAlegeri"><h2>__ALEGERI__</h2><div id="alegeri"></div></section>
  <section class="card"><h2>__CE_S_A_INTAMPLAT__</h2><table><tbody id="randuri"></tbody></table></section>
  <section class="card"><h2>__TEXT_BRUT__</h2>
    <div class="butoane"><button type="button" id="comutaBrut">__TEXT_BRUT__</button><select id="fisier" class="ascuns"></select></div>
    <p class="nota">__NOTA_BRUT__</p>
    <p class="nota ascuns" id="caleBrut">__FISIERUL__ <code id="cale"></code></p>
    <pre id="brut" class="ascuns"></pre>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">__NOTA_TV__</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
var brutVizibil = false, ocupat = false;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("deconectat"); }
    return r.json().catch(function(){ return {result: false, message: T.neasteptat + " (HTTP " + r.status + ")"}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function celula(rand, text, clasa){ var td = document.createElement("td"); td.textContent = text; if(clasa){ td.className = clasa; } rand.appendChild(td); return td; }
function arataRanduri(randuri){
  var corp = $("randuri"); corp.textContent = "";
  randuri.forEach(function(r){
    var tr = document.createElement("tr");
    if(r[0] === "titlu"){ tr.className = "grupa"; celula(tr, r[1]).colSpan = 2; }
    else if(r[0] === "linie" || r[0] === "nota"){ tr.className = r[0]; celula(tr, "", "eticheta"); celula(tr, r[1]); }
    else { celula(tr, r[1], "eticheta"); celula(tr, r[2], r[3] === "normal" ? "" : r[3]); }
    corp.appendChild(tr);
  });
}
function arataAlegeri(alegeri){
  var d = $("alegeri"); d.textContent = "";
  $("cardAlegeri").classList.toggle("ascuns", !alegeri.length);
  alegeri.forEach(function(a, i){
    var div = document.createElement("div"); div.className = "alegere";
    var b = document.createElement("button"); b.type = "button"; b.textContent = a.titlu;
    if(i === 0){ b.className = "principal"; }
    b.disabled = !a.se_poate || ocupat;
    b.addEventListener("click", function(){ alege(a.cheie); });
    var p = document.createElement("p"); p.textContent = a.descriere;
    div.appendChild(b); div.appendChild(p); d.appendChild(div);
  });
}
function arataFisiere(pagini){
  var s = $("fisier"), ales = s.value; s.textContent = "";
  pagini.forEach(function(p, i){ var o = document.createElement("option"); o.value = i; o.textContent = p.titlu; s.appendChild(o); });
  if(ales && ales < pagini.length){ s.value = ales; }
}
function citeste(){
  return cerere("/api/mod-sigur").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || T.neasteptat; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    $("mesajMare").textContent = d.mesaj; $("explicatie").textContent = d.explicatie;
    $("cardStare").classList.toggle("avertizare", !!d.activ);
    arataAlegeri(d.alegeri || []); arataRanduri(d.randuri || []); arataFisiere(d.pagini || []);
  }).catch(function(){ $("incarcare").textContent = T.nuRaspunde; });
}
function citesteBrut(){
  cerere("/api/mod-sigur-brut?pagina=" + encodeURIComponent($("fisier").value || "0")).then(function(d){
    $("brut").textContent = d.result ? d.text : (d.message || T.neasteptat);
    $("cale").textContent = d.result ? d.cale : ""; $("caleBrut").classList.toggle("ascuns", !d.result);
  }).catch(function(){ $("brut").textContent = T.nuRaspunde; });
}
function alege(cheie){
  if(ocupat){ return; }
  ocupat = true;
  Array.prototype.forEach.call(document.querySelectorAll("#alegeri button"), function(b){ b.disabled = true; });
  mesaj(T.seAplica);
  cerere("/api/mod-sigur-alege?alegere=" + encodeURIComponent(cheie), "POST").then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ setTimeout(function(){ location.reload(); }, 20000); } else { ocupat = false; citeste(); }
  }).catch(function(){ mesaj(T.nuRaspunde, true); ocupat = false; });
}
$("comutaBrut").addEventListener("click", function(){
  brutVizibil = !brutVizibil;
  $("brut").classList.toggle("ascuns", !brutVizibil); $("fisier").classList.toggle("ascuns", !brutVizibil);
  if(!brutVizibil){ $("caleBrut").classList.add("ascuns"); }
  $("comutaBrut").textContent = brutVizibil ? T.peScurt : T.textBrut;
  if(brutVizibil){ citesteBrut(); }
});
$("fisier").addEventListener("change", citesteBrut);
citeste();
setInterval(function(){ if(!ocupat){ citeste(); } }, 60000);
</script>
</body>
</html>
"""

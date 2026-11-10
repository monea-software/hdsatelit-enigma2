# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# dab_usb_web.py: „Radio DAB+ prin USB” in interfata web (HdsWebControl), perechea ecranului de pe televizor (Screens/HdsDabUsb.py si
# ecranul pluginului DabTerestru). Pagina exista si fara plugin: arata starea stickului si instaleaza programul de receptie din acelasi loc.
# Cu pluginul instalat, totul trece prin motorul lui (DabTerestru/motor.py), acelasi cu al telecomenzii: aceeasi cautare, aceleasi
# verificari, un singur stick. Nicio a doua logica aici.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba ceva cere, cu cookie,
# POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/dab-terestru                 {result, instalat, stick, pregatire, cautare, redare, posturi, setari, ajutor}
#   POST /api/dab-terestru-fa?actiune=pregateste|cauta|opreste|asculta|opreste_radio|favorit|seteaza[&id=][&cheie=&valoare=]
#   GET  /api/dab-terestru-imagine         imaginea trimisa acum de post (MOT), cand exista
#   GET  /dab-terestru                     pagina (starea se citeste din nou la 2 secunde)
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. O cerere citeste numai memoria motorului si sysfs. Nu se expune nimic din
# fluxul IQ sau din program catre retea. Numele posturilor vin din aer: ajung in pagina numai prin textContent.
# Fara enigma2 la incarcare: probele de pe PC dau modulele lor (D, M).
import json
import os

try:
	from html import escape as _escape
except ImportError:  # Python 2 (probele vechi)
	from cgi import escape as _escape

ACTIUNI = ("pregateste", "cauta", "opreste", "asculta", "opreste_radio", "favorit", "seteaza")
MAX_IMAGINE = 1024 * 1024


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _d(D=None):
	if D is not None:
		return D
	from Components import HdsDabUsb
	return HdsDabUsb


def _m(M=None, sesiune=None, D=None):
	"""Motorul pluginului, sau None cand pluginul lipseste ori nu se incarca."""
	if M is not None:
		return M
	if not _d(D).plugin_instalat():
		return None
	try:
		from Plugins.Extensions.DabTerestru.motor import motor
		m = motor()
		if m.nav is None and sesiune is not None:
			m.nav = sesiune.nav
		return m
	except Exception as e:
		print("[HdsWebControl] DAB+ prin USB: %s: %s" % (type(e).__name__, e))
		return None


def _text_ajutor():
	try:
		from Plugins.Extensions.DabTerestru.ecran import text_ajutor
		return text_ajutor()
	except Exception:
		return ""


def stare(D=None, M=None, sesiune=None, ajutor=_text_ajutor):
	"""Fotografia pentru pagina, aceleasi texte ca pe televizor."""
	D = _d(D)
	m = _m(M, sesiune, D)
	if m is None:
		fel, stick = D.fel_stare(D.inventar())
		p = D.pregatire()
		if p.faza == "nimic":
			p.verifica()
		return {"result": True, "instalat": False, "stick": D.text_stare(fel, stick), "pregatire": p.stare(), "cautare": None, "redare": None,
			"posturi": [], "setari": [], "ajutor": ""}
	d = dict(m.stare())
	d.update(result=True, instalat=True, pregatire=None, ajutor=ajutor())
	d["redare"] = dict(d["redare"], imagine=bool(d["redare"].get("imagine")))
	return d


def fa(arg, D=None, M=None, sesiune=None):
	"""Comanda din pagina. Aceleasi verificari ca telecomanda: le face motorul."""
	actiune = arg.get("actiune") or ""
	if actiune not in ACTIUNI:
		return {"result": False, "message": _t("Comanda nu este cunoscută.")}
	if actiune == "pregateste":
		D = _d(D)
		p = D.pregatire()
		if p.stare()["faza"] == "de_instalat":
			p.instaleaza()
		else:
			p.verifica(True)
		return {"result": True, "message": ""}
	m = _m(M, sesiune, D)
	if m is None:
		return {"result": False, "message": _t("Programul de recepție nu e încă pe receptor.")}
	if actiune == "favorit":
		return _favorit(m, arg.get("id") or "")
	return m.fa(actiune, arg)


def _favorit(m, id_):
	"""Pune sau scoate postul din Favorite, cu aceleasi functii ca lista de canale (Components/HdsFavorite.py)."""
	p = m.date.post(id_)
	if p is None:
		return {"result": False, "message": _t("Nu am găsit postul.")}
	from Components import HdsFavorite
	from Plugins.Extensions.DabTerestru.date import ref_post
	r = HdsFavorite.comuta(ref_post(p["id"]) + p["nume"], tip=HdsFavorite.RADIO, nume=p["nume"])
	return {"result": bool(r.ok), "message": r.mesaj()}


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
		rez[cheie] = v[:80]
	return rez


def rute(baza, resource, D=None, M=None, sesiune=None):
	"""({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(D, M, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class FaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, fa(argumente(request), D, M, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class ImagineResource(baza):
		"""Imaginea trimisa de post; numai din dosarul programului de receptie, cu numele dat de el."""

		def render_GET(self, request):
			m = _m(M, _ses())
			cale = m.stare_redare().get("imagine") if m is not None else ""
			if not cale or not os.path.isfile(cale) or os.path.getsize(cale) > MAX_IMAGINE:
				return self._eroare(request, _t("Postul nu a trimis nicio imagine."), 404)
			with open(cale, "rb") as f:
				date = f.read()
			request.setHeader(b"content-type", b"image/png" if cale.endswith(".png") else b"image/jpeg")
			request.setHeader(b"cache-control", b"no-store")
			return date

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {b"dab-terestru": StareResource(), b"dab-terestru-fa": FaResource(), b"dab-terestru-imagine": ImagineResource()}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /mod-sigur si /accel."""
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
	"""Textele scriptului paginii, traduse, ca JSON."""
	return json.dumps({
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"neasteptat": _t("Receptorul a răspuns neașteptat."),
		"cauta": _t("Caută posturi"),
		"opreste": _t("Oprește căutarea"),
		"asculta": _t("Ascultă pe receptor"),
		"seAsculta": _t("Se ascultă"),
		"opresteRadio": _t("Oprește radioul"),
		"favorit": _t("Favorite"),
		"pregateste": _t("Pregătește recepția DAB+"),
		"incearca": _t("Încearcă din nou"),
		"niciunPost": _t("Nu sunt posturi încă. Pune stickul și apasă Caută posturi."),
		"marime": _t("Se instalează o singură dată. Mărime: %s."),
	}, ensure_ascii=True).replace("</", "<\\/")


def pagina_text(stil, config_pagina, limba="ro"):
	inlocuiri = {
		"__STIL_COMUN__": stil,
		"__CONFIG__": config_pagina,
		"__TEXTE__": texteScript(),
		"__LIMBA__": _e(limba),
		"__TITLU__": _e(_t("Radio DAB+ prin USB")),
		"__SE_CITESTE__": _e(_t("Se citește starea...")),
		"__CAUTAREA__": _e(_t("Caută posturi")),
		"__POSTURI__": _e(_t("Posturi")),
		"__OPTIUNI__": _e(_t("Opțiuni")),
		"__AJUTOR__": _e(_t("Ajutor")),
		"__NOTA_TV__": _e(_t("Aceeași pagină e pe televizor, la Meniu > Scanare > Radio DAB+ prin USB. Posturile găsite apar în lista de radio, la DAB+ terestru (USB).")),
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
  .stick{border-left:6px solid #667085;}
  .stick.bun{border-left-color:#4fd18b;} .stick.galben{border-left-color:#f1c40f;} .stick.rau{border-left-color:#ff6b5e;}
  .mare{font-size:1.1rem;line-height:1.45;margin:0 0 6px;font-weight:bold;}
  .acum{font-size:.95rem;line-height:1.45;margin:0;color:var(--text-slab);}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.principal{background:#f5b83d;border-color:#f5b83d;color:#101828;}
  button:disabled{opacity:.5;cursor:default;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;max-width:100%;}
  .bara{height:10px;background:#2a3350;border-radius:5px;overflow:hidden;margin:10px 0 0;}
  .bara i{display:block;height:100%;background:#4fd18b;width:0;}
  .ansamblu{color:#9fb4ff;font-weight:bold;padding:12px 0 6px;}
  .post{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .post .nume{flex:1 1 200px;min-width:0;overflow-wrap:anywhere;font-weight:bold;}
  .post .format{color:var(--text-slab);font-size:.88rem;}
  .post.merge .nume{color:#4fd18b;}
  .rand{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0 0;}
  pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.5;margin:0;}
  img{max-width:100%;border-radius:8px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
</style>
</head>
<body>
<main>
<h1>__TITLU__</h1>
<p class="mesaj" id="incarcare">__SE_CITESTE__</p>
<div id="continut" class="ascuns">
  <section class="card stick" id="cardStick"><p class="mare" id="stickTitlu"></p><p class="acum" id="stickRand"></p></section>
  <section class="card ascuns" id="cardPregatire"><p class="mare" id="pregTitlu"></p><p class="acum" id="pregText"></p>
    <div class="butoane"><button type="button" class="principal" id="pregButon"></button></div></section>
  <section class="card ascuns" id="cardRedare"><p class="mare" id="redareNume"></p><p class="acum" id="redareText"></p><p class="acum" id="redareSemnal"></p>
    <img id="redareImg" class="ascuns" alt=""><div class="butoane"><button type="button" id="opresteRadio"></button></div></section>
  <section class="card ascuns" id="cardCautare"><h2>__CAUTAREA__</h2><p class="acum" id="cautareText"></p><div class="bara ascuns" id="baraFond"><i id="bara"></i></div>
    <div class="butoane"><button type="button" class="principal" id="cauta"></button></div></section>
  <section class="card ascuns" id="cardPosturi"><h2>__POSTURI__</h2><div id="posturi"></div></section>
  <section class="card ascuns" id="cardOptiuni"><h2>__OPTIUNI__</h2><div id="optiuni"></div></section>
  <section class="card ascuns" id="cardAjutor"><h2>__AJUTOR__</h2><pre id="ajutor"></pre></section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">__NOTA_TV__</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
var semnPosturi = "", semnOptiuni = "", ocupat = false;
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
function arata(id, da){ $(id).classList.toggle("ascuns", !da); }
function comanda(parametri){
  if(ocupat){ return; }
  ocupat = true;
  cerere("/api/dab-terestru-fa?" + parametri, "POST").then(function(d){
    mesaj(d.message, !d.result); ocupat = false; citeste();
  }).catch(function(){ mesaj(T.nuRaspunde, true); ocupat = false; });
}
function buton(text, clasa, fapta){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  if(clasa){ b.className = clasa; }
  b.addEventListener("click", fapta); return b;
}
function aratePosturi(d){
  var semn = JSON.stringify(d.posturi);
  if(semn === semnPosturi){ return; }
  semnPosturi = semn;
  var c = $("posturi"), ultim = null; c.textContent = "";
  if(!d.posturi.length){ var g = document.createElement("p"); g.className = "acum"; g.textContent = T.niciunPost; c.appendChild(g); return; }
  d.posturi.forEach(function(p){
    var a = p.ansamblu + " · " + p.bloc;
    if(a !== ultim){ ultim = a; var h = document.createElement("div"); h.className = "ansamblu"; h.textContent = a; c.appendChild(h); }
    var r = document.createElement("div"); r.className = "post" + (p.merge ? " merge" : "");
    var n = document.createElement("span"); n.className = "nume"; n.textContent = p.nume; r.appendChild(n);
    var f = document.createElement("span"); f.className = "format"; f.textContent = p.format; r.appendChild(f);
    r.appendChild(buton(p.merge ? T.seAsculta : T.asculta, p.merge ? "" : "principal", function(){ comanda("actiune=asculta&id=" + encodeURIComponent(p.id)); }));
    r.appendChild(buton(T.favorit, "", function(){ comanda("actiune=favorit&id=" + encodeURIComponent(p.id)); }));
    c.appendChild(r);
  });
}
function arateOptiuni(d){
  var semn = JSON.stringify(d.setari);
  if(semn === semnOptiuni){ return; }
  semnOptiuni = semn;
  var c = $("optiuni"); c.textContent = "";
  d.setari.forEach(function(s){
    var r = document.createElement("div"); r.className = "rand";
    var t = document.createElement("span"); t.textContent = s.titlu; r.appendChild(t);
    var sel = document.createElement("select");
    s.valori.forEach(function(v){ var o = document.createElement("option"); o.value = v.valoare; o.textContent = v.text; sel.appendChild(o); });
    sel.value = s.acum;
    sel.addEventListener("change", function(){ comanda("actiune=seteaza&cheie=" + encodeURIComponent(s.cheie) + "&valoare=" + encodeURIComponent(sel.value)); });
    r.appendChild(sel); c.appendChild(r);
  });
}
function citeste(){
  return cerere("/api/dab-terestru").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || T.neasteptat; return; }
    arata("incarcare", false); arata("continut", true);
    $("stickTitlu").textContent = d.stick.titlu; $("stickRand").textContent = d.stick.rand;
    $("cardStick").className = "card stick " + d.stick.culoare;
    arata("cardPregatire", !d.instalat);
    if(!d.instalat){
      var p = d.pregatire, poate = p.faza === "de_instalat" || p.faza === "lipsa" || p.faza === "eroare";
      $("pregTitlu").textContent = T.pregateste;
      $("pregText").textContent = p.text + (p.faza === "de_instalat" && p.marime ? " " + T.marime.replace("%s", Math.round(p.marime / 1024) + " KB") : "") + (p.pas ? " " + p.pas : "");
      $("pregButon").textContent = p.faza === "de_instalat" ? T.pregateste : T.incearca;
      $("pregButon").disabled = !poate;
    }
    arata("cardCautare", d.instalat); arata("cardPosturi", d.instalat); arata("cardOptiuni", d.instalat);
    arata("cardAjutor", d.instalat && !!d.ajutor);
    arata("cardRedare", !!(d.instalat && d.redare.merge));
    if(!d.instalat){ return; }
    $("cautareText").textContent = d.cautare.text;
    $("cauta").textContent = d.cautare.merge ? T.opreste : T.cauta;
    arata("baraFond", d.cautare.merge); $("bara").style.width = d.cautare.procent + "%";
    if(d.redare.merge){
      $("redareNume").textContent = d.redare.nume; $("redareText").textContent = d.redare.text; $("redareSemnal").textContent = d.redare.semnal;
      $("opresteRadio").textContent = T.opresteRadio;
      arata("redareImg", d.redare.imagine);
      if(d.redare.imagine){ $("redareImg").src = adresa("/api/dab-terestru-imagine") + (CFG.jeton ? "&" : "?") + "t=" + Date.now(); }
    }
    aratePosturi(d); arateOptiuni(d);
    if(d.ajutor && !$("ajutor").textContent){ $("ajutor").textContent = d.ajutor; }
  }).catch(function(){ $("incarcare").textContent = T.nuRaspunde; arata("incarcare", true); });
}
$("pregButon").addEventListener("click", function(){ comanda("actiune=pregateste"); });
$("opresteRadio").addEventListener("click", function(){ comanda("actiune=opreste_radio"); });
$("cauta").addEventListener("click", function(){ comanda($("cauta").textContent === T.opreste ? "actiune=opreste" : "actiune=cauta"); });
citeste();
setInterval(function(){ if(!ocupat && !document.hidden){ citeste(); } }, 2000);
</script>
</body>
</html>
"""

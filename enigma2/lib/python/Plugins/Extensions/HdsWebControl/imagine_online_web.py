# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# imagine_online_web.py: „Imagine nouă de pe internet” in interfata web (HdsWebControl), perechea ferestrei
# Screens/HdsImagineOnline.py. Aceeasi stare si aceleasi actiuni, din Components/HdsImagineOnline.py (o singura lucrare
# odata: ce porneste pagina se vede si pe televizor, si invers).
#
# Rute (poarta comuna a HdsJsonResource; cele care schimba ceva cer POST + antetul CSRF al panoului, sau ?token=):
#   GET  /api/imagine-online            starea: oferta (versiunile cu datele lor), faza, pasul, progresul, mesajul, setarea
#   POST /api/imagine-online-cauta      citeste lista semnata
#   POST /api/imagine-online-porneste   versiune=<x.y.z>&oferta=<amprenta>, cele aratate in pagina: un singur „Da”
#   POST /api/imagine-online-opreste    opreste lucrarea inainte de scriere; fisierul inceput ramane pe stick
#   POST /api/imagine-online-standby    valoare=amandoua|majore|minore|oprita
#   POST /api/imagine-online-straina    id=<id>&confirmat=1: o imagine a altei echipe, data de un plugin, dupa avertismentul din pagina
#   GET  /imagine-online                pagina (aceeasi poarta ca /paznic)
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul lor (IO).

import json
import re

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


def _io(IO=None):
	if IO is not None:
		return IO
	from Components import HdsImagineOnline
	return HdsImagineOnline


def _text_rezultat(IO):
	i = IO.imagine_online
	return _t({IO.LA_ZI: IO.T_LA_ZI, IO.FARA_RETEA: IO.T_FARA_RETEA, IO.FARA_RASPUNS: IO.T_FARA_SERVER,
		IO.NESEMNATA: IO.T_NESEMNATA, IO.EROARE: IO.T_FARA_SERVER}.get(i.rezultat, ""))


def stare(IO=None):
	IO = _io(IO)
	rez = IO.imagine_online.stare_publica()
	loc_bun = True
	if rez.get("fel") == "imagine":
		loc_bun = bool(IO.citeste_tinta().get("bun"))
	rez.update({"result": True, "text_rezultat": _text_rezultat(IO), "loc_bun": loc_bun,
		"text_loc": "" if loc_bun else _t(IO.T_LOC_STRAIN),
		"valori_standby": [[v, _t(t)] for v, t in IO.VALORI_STANDBY]})
	return rez


def cauta(IO=None):
	IO = _io(IO)
	pornit = IO.imagine_online.cauta()
	rez = stare(IO)
	rez.update({"result": bool(pornit), "message": "" if pornit else (IO.imagine_online.pas or IO.imagine_online.mesaj)})
	return rez


def porneste(arg, IO=None):
	IO = _io(IO)
	i = IO.imagine_online
	pornit = i.porneste(versiune=arg.get("versiune") or "", oferta=arg.get("oferta") or "")
	rez = stare(IO)
	rez.update({"result": bool(pornit), "message": "" if pornit else i.mesaj})
	return rez


def opreste(IO=None):
	IO = _io(IO)
	pornit = IO.imagine_online.opreste()
	rez = stare(IO)
	rez["result"] = bool(pornit)
	return rez


def porneste_straina(arg, IO=None):
	"""Imaginea altei echipe: numai cu confirmat=1, adica dupa avertismentul din pagina."""
	IO = _io(IO)
	i = IO.imagine_online
	pornit = i.porneste_straina(arg.get("id") or "", confirmat=arg.get("confirmat") == "1")
	rez = stare(IO)
	rez.update({"result": bool(pornit), "message": "" if pornit else i.mesaj})
	return rez


def seteaza_standby(arg, IO=None):
	IO = _io(IO)
	bun = IO.seteaza_standby(arg.get("valoare") or "")
	rez = stare(IO)
	rez["result"] = bool(bun)
	return rez


def argumente(request):
	"""Campurile cererii ca texte; un nume sau o valoare ciudata nu ajunge mai departe."""
	rez = {}
	for k, v in (getattr(request, "args", None) or {}).items():
		try:
			cheie = k.decode("ascii") if isinstance(k, bytes) else k
			valoare = v[0].decode("utf-8") if isinstance(v[0], bytes) else v[0]
		except (UnicodeDecodeError, IndexError, AttributeError):
			continue
		rez[cheie] = valoare
	return rez


def rute(baza, resource, IO=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(IO))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ActiuneResource(baza):
		schimbaCeva = True
		functie = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.functie(argumente(request)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	def actiune(f):
		r = ActiuneResource()
		r.functie = f
		return r

	class PaginaResource(resource.Resource):
		"""GET /imagine-online: pagina."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"imagine-online": StareResource(),
		b"imagine-online-cauta": actiune(lambda arg: cauta(IO)),
		b"imagine-online-porneste": actiune(lambda arg: porneste(arg, IO)),
		b"imagine-online-opreste": actiune(lambda arg: opreste(IO)),
		b"imagine-online-standby": actiune(lambda arg: seteaza_standby(arg, IO)),
		b"imagine-online-straina": actiune(lambda arg: porneste_straina(arg, IO)),
	}
	return api, PaginaResource()


def _limba():
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	cod = "".join(ch for ch in cod if "a" <= ch <= "z")[:3]
	return cod or "ro"


def pagina(request):
	"""Aceeasi poarta ca /paznic."""
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


def _e(text):
	return _escape(u"%s" % (text or ""), True)


def texte(IO=None):
	"""Textele scrise de scriptul paginii, traduse pe receptor"""
	IO = _io(IO)
	return {
		"nuRaspunde": _t("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		"caut": _t(IO.P_CAUT),
		"instaleaza": _t(IO.T_INSTALEAZA),
		"daStrain": _t(IO.T_STRAINA_DA),
		"nu": _t("No"),
	}


def pagina_text(stil, config_pagina, limba="ro", IO=None):
	IO = _io(IO)
	valori = {
		"__STIL_COMUN__": stil,
		"__LIMBA__": _e(limba or "ro"),
		"__CONFIG__": config_pagina,
		"__TEXTE__": json.dumps(texte(IO), ensure_ascii=False).replace("</", "<\\/"),
		"__T_TITLU__": _e(_t("Imagine nouă de pe internet")),
		"__T_DA__": _e(_t(IO.T_DA)),
		"__T_OPRESTE__": _e(_t("Oprește")),
		"__T_STANDBY__": _e(_t(IO.T_STANDBY)),
	}
	# o singura trecere: un nume venit din browser (in __CONFIG__) nu poate fi luat drept semn __X__
	return re.sub(r"__[A-Z_]+__", lambda m: valori.get(m.group(0), m.group(0)), PAGINA)


PAGINA = u"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.3rem;margin:0 0 12px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:14px 16px;margin:0 0 10px;}
  .text{line-height:1.5;margin:0 0 10px;}
  .pas{color:var(--text-slab);margin:0 0 10px;min-height:1.4em;line-height:1.45;}
  button{min-height:44px;padding:8px 16px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  main button.da{background:#1f771f;border-color:#1f771f;color:#fff;}
  button[hidden]{display:none;}
  select{min-height:40px;font:inherit;background:#0f1216;color:var(--text);border:1px solid var(--bordura);border-radius:8px;padding:4px 8px;}
  label{display:block;margin:0 0 6px;}
  h2{font-size:1.05rem;margin:0 0 10px;}
  .rand{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--bordura);}
  .eticheta{display:inline-block;padding:2px 8px;border-radius:6px;border:1px solid #f5b83d;color:#f5b83d;font-size:.8rem;margin-right:8px;}
  .avertisment{width:100%;line-height:1.45;white-space:pre-line;margin:6px 0;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<section class="card">
<p class="text" id="text"></p>
<p class="pas" id="pas"></p>
<button id="da" class="da" type="button" hidden>__T_DA__</button>
<button id="opreste" type="button" hidden>__T_OPRESTE__</button>
</section>
<div id="straine"></div>
<section class="card">
<label for="standby">__T_STANDBY__</label>
<select id="standby"></select>
</section>
</main>
<script>
var CFG = __CONFIG__;
var T = __TEXTE__;
var versiune = "";
var oferta = "";
var stranieVazute = null;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser"); }
    return r.json();
  });
}
function arata(d){
  versiune = d.versiune || "";
  oferta = d.oferta || "";
  var lucrez = d.faza === "lucrez" || d.faza === "astept";
  var liber = d.faza === "liber";
  var text = d.text || d.text_rezultat || "";
  if(d.faza === "caut" || d.faza === "scriu"){ text = d.pas; }
  if(!d.loc_bun){ text = d.text_loc; }
  $("text").textContent = text;
  $("pas").textContent = lucrez ? d.pas : (d.message || d.mesaj || "");
  $("da").hidden = !(liber && d.versiune && d.loc_bun);
  $("opreste").hidden = !lucrez;
  var s = $("standby");
  if(!s.options.length){
    d.valori_standby.forEach(function(v){ var o = document.createElement("option"); o.value = v[0]; o.textContent = v[1]; s.appendChild(o); });
  }
  s.value = d.standby;
  arataStraine(d.straine || [], liber);
}
function arataStraine(lista, liber){
  var cheie = JSON.stringify(lista) + liber;
  if(cheie === stranieVazute){ return; }
  stranieVazute = cheie;
  var loc = $("straine"); loc.textContent = "";
  var sectiune = null, card = null;
  lista.forEach(function(x){
    if(x.sectiune !== sectiune){
      sectiune = x.sectiune;
      card = document.createElement("section"); card.className = "card";
      var h = document.createElement("h2"); h.textContent = sectiune; card.appendChild(h);
      loc.appendChild(card);
    }
    var r = document.createElement("div"); r.className = "rand";
    var t = document.createElement("span");
    var e = document.createElement("span"); e.className = "eticheta"; e.textContent = x.stare;
    t.appendChild(e); t.appendChild(document.createTextNode(x.nume)); r.appendChild(t);
    if(liber){
      var b = document.createElement("button"); b.type = "button"; b.textContent = T.instaleaza;
      b.addEventListener("click", function(){ avertisment(r, x, b); });
      r.appendChild(b);
    }
    card.appendChild(r);
  });
}
function avertisment(r, x, b){
  b.hidden = true;
  var p = document.createElement("p"); p.className = "avertisment"; p.textContent = x.avertisment; r.appendChild(p);
  var nu = document.createElement("button"); nu.type = "button"; nu.textContent = T.nu;
  var da = document.createElement("button"); da.type = "button"; da.textContent = T.daStrain;
  function inchide(){ p.remove(); nu.remove(); da.remove(); b.hidden = false; }
  nu.addEventListener("click", inchide);
  da.addEventListener("click", function(){
    inchide();
    cerere("/api/imagine-online-straina?confirmat=1&id=" + encodeURIComponent(x.id), "POST").then(arata);
  });
  r.appendChild(nu); r.appendChild(da);
  nu.focus();
}
function citeste(){
  cerere("/api/imagine-online").then(arata).catch(function(){ $("pas").textContent = T.nuRaspunde; });
}
$("da").addEventListener("click", function(){
  cerere("/api/imagine-online-porneste?versiune=" + encodeURIComponent(versiune) + "&oferta=" + encodeURIComponent(oferta), "POST").then(arata);
});
$("opreste").addEventListener("click", function(){ cerere("/api/imagine-online-opreste", "POST").then(arata); });
$("standby").addEventListener("change", function(){
  cerere("/api/imagine-online-standby?valoare=" + encodeURIComponent(this.value), "POST").then(arata);
});
$("text").textContent = T.caut;
cerere("/api/imagine-online-cauta", "POST").then(arata).catch(citeste);
setInterval(citeste, 2000);
</script>
</body>
</html>
"""

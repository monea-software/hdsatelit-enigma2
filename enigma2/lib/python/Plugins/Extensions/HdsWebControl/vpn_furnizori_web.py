# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# vpn_furnizori_web.py: "Furnizorul VPN, fără fișiere" in interfata web (HdsWebControl), perechea ecranului de pe
# televizor (Screens/HdsVpnFurnizor.py, deschis din ecranul VPN). Aceeasi logica, din Components/HdsVpnFurnizori.py:
# alegi furnizorul, scrii contul (numele si parola de serviciu ori numarul contului Mullvad; scrise aici, niciodata
# aratate inapoi; campurile sunt text obisnuit, fara stelute), alegi tara, iar receptorul pune serverele si porneste
# VPN-ul. Pentru furnizorii fara cale oficiala pagina arata de unde iei fisierele si trimite la pagina /vpn. Legat din
# meniu_pagini_web.MODULE. Numai cu programele VPN in imagine (SystemInfo["HdsVpn"], ca pagina /vpn).
#
# Cine are voie: ca la /vpn. Starea (GET) o vede oricine trece de poarta: nu are secrete. Orice schimbare (POST) cere
# un browser (cel din casa), nu cheia pentru scripturi.
#   GET  /api/vpn-furnizor?furnizor=..          starea (fara nume, parola, numar sau chei)
#   POST /api/vpn-furnizor-tari                 furnizor=, din_nou=0|1: citeste lista tarilor (lucrare)
#   POST /api/vpn-furnizor-configureaza         corp: furnizor=, tara=, nume=, parola=, numar= (contul numai in corp)
#   POST /api/vpn-furnizor-sterge               furnizor=, confirmat=1: sterge contul acestui furnizor de pe receptor
#   GET  /vpn-furnizor                          pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2 si nu fac cereri pe internet: listele si configurarea merg
# pe firul lucrarilor din Components/HdsVpn.py. Fisierul nu importa nimic din enigma2 la incarcare.


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la afisare cu _t()."""
	return text


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _f(F=None):
	if F is not None:
		return F
	from Components import HdsVpnFurnizori
	return HdsVpnFurnizori


def disponibil(F=None):
	"""Ca pagina /vpn: numai cu programele VPN in imagine (SystemInfo["HdsVpn"]; cu modulul dat, V.disponibil())."""
	if F is not None:
		return bool(F._hv().disponibil())
	try:
		from Components.SystemInfo import SystemInfo
	except Exception as eroare:
		print("[HdsWebControl] vpn-furnizor: %r" % (eroare,))
		return False
	return bool(SystemInfo.get("HdsVpn"))


def _arg(request, nume, maxim=200):
	valori = (getattr(request, "args", None) or {}).get(nume.encode("ascii")) or []
	if not valori:
		return ""
	v = valori[0]
	if isinstance(v, bytes):
		v = v.decode("utf-8", "replace")
	return str(v)[:maxim]


def _cheiDinAdresa(request):
	"""Numele argumentelor scrise in adresa (request.args le amesteca cu cele din corp)."""
	uri = getattr(request, "uri", b"") or b""
	if isinstance(uri, bytes):
		uri = uri.decode("utf-8", "replace")
	from urllib.parse import urlsplit, parse_qsl
	return set(k for k, _v in parse_qsl(urlsplit(uri).query, keep_blank_values=True))


def nivel(request, sesiune_cerere=None):
	""""jeton" (?token=, numai citire) sau "asociat" (orice browser care a trecut poarta)."""
	if b"token" in (getattr(request, "args", None) or {}):
		return "jeton"
	if sesiune_cerere is None:
		from . import plugin as P
		sesiune_cerere = P._sesiuneDinCerere
	_secret, browser = sesiune_cerere(request)
	return "asociat" if browser is not None else "liber"


NEASOCIAT = N_("VPN-ul se schimbă numai din pagina VPN, dintr-un browser (nu cu cheia pentru scripturi).")


def stare(request, F=None, nivel_cerere="asociat"):
	F = _f(F)
	fid = _arg(request, "furnizor", 20)
	if fid not in F.ORDINE and fid not in F.CU_FISIERE:
		acum = F._hv().setari()["furnizor"]
		fid = acum if acum in F.ORDINE else F.ORDINE[0]
	s = F.stare(fid)
	return dict(s, result=True, nivel=nivel_cerere, asociat=nivel_cerere == "asociat",
		text_vpn=F._hv().textLegatura(F._hv().stare()))


def _pornit(numar, mesaj):
	if numar is None:
		return {"result": False, "message": _t("Așteaptă să se termine ce ai pornit înainte (pe televizor sau aici).")}
	return {"result": True, "lucrare": numar, "message": mesaj}


def tari(request, F=None):
	F = _f(F)
	fid = _arg(request, "furnizor", 20)
	if fid not in F.ORDINE:
		return {"result": False, "message": _t("Alege întâi furnizorul.")}
	if F.indisponibil(fid):
		return {"result": False, "message": F.indisponibil(fid)}
	numar = F.pornesteTarile(fid, _arg(request, "din_nou") == "1")
	if numar == 0:
		return {"result": True, "message": ""}
	return _pornit(numar, F.textLucrare(F.LUCRARE_TARI))


def configureaza(request, F=None):
	F = _f(F)
	if {"nume", "parola", "numar"}.intersection(_cheiDinAdresa(request)):
		return {"result": False, "message": _t("Datele contului se trimit numai în corpul cererii.")}
	fid = _arg(request, "furnizor", 20)
	if fid not in F.ORDINE:
		return {"result": False, "message": _t("Alege întâi furnizorul.")}
	if F.indisponibil(fid):
		return {"result": False, "message": F.indisponibil(fid)}
	cod = _arg(request, "tara", 4)
	if not any(t["cod"] == cod for t in (F.listaTarilor(fid) or [])):
		return {"result": False, "message": _t("Alege întâi țara.")}
	maxim = F._hv().MAX_CAMP_CONT + 1
	bun, mesaj, cont = F.verificaCont(fid, _arg(request, "nume", maxim), _arg(request, "parola", maxim),
		_arg(request, "numar", 40))
	if not bun:
		return {"result": False, "message": mesaj}
	return _pornit(F.configureaza(fid, cod, cont), F.textLucrare(F.LUCRARE_CONFIGURARE))


def sterge(request, F=None):
	F = _f(F)
	if _arg(request, "confirmat") != "1":
		return {"result": False, "message": _t("Confirmă ștergerea.")}
	reusit, mesaj = F.stergeDatele(_arg(request, "furnizor", 20))
	return {"result": reusit, "message": mesaj}


def rute(baza, resource, F=None, sesiune_cerere=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}); fara programele VPN in imagine: ({}, {})."""
	if not disponibil(F):
		return {}, {}

	def neasociat(request):
		if nivel(request, sesiune_cerere) == "asociat":
			return None
		return {"result": False, "trebuie_cod": True, "message": _t(NEASOCIAT)}

	class StareResource(baza):
		"""GET /api/vpn-furnizor: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(request, F, nivel(request, sesiune_cerere)))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Comanda(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			refuz = neasociat(request)
			if refuz is not None:
				return self._raspunde(request, refuz, 403)
			try:
				return self._raspunde(request, type(self).lucru(request, F))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # poarta cere POST din browser; cu ?token= raspunsul e refuzul

	def comanda(functie):
		return type("Comanda", (_Comanda,), {"lucru": staticmethod(functie)})()

	class PaginaResource(resource.Resource):
		"""GET /vpn-furnizor: pagina."""
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina as poarta
			return poarta(request, pagina_text)

	api = {
		b"vpn-furnizor": StareResource(),
		b"vpn-furnizor-tari": comanda(tari),
		b"vpn-furnizor-configureaza": comanda(configureaza),
		b"vpn-furnizor-sterge": comanda(sterge),
	}
	return api, {b"vpn-furnizor": PaginaResource()}


def _limba():
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	return cod if (2 <= len(cod) <= 3 and cod.isalpha()) else "ro"


def _json(obiect):
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


ETICHETE = {
	"TITLU": N_("Furnizorul VPN, fără fișiere"),
	"INCARCARE": N_("Se citește starea..."),
	"FURNIZOR": N_("Furnizorul"),
	"CONT": N_("Contul"),
	"NUME": N_("Numele"),
	"PAROLA": N_("Parola"),
	"NUMAR": N_("Numărul contului"),
	"TARA": N_("Țara"),
	"PUNE": N_("Pune VPN-ul pe receptor"),
	"DIN_NOU": N_("Citește din nou lista țărilor"),
	"STERGE": N_("Șterge contul acestui furnizor de pe receptor"),
	"INAPOI": N_("Înapoi la pagina VPN"),
	"VPN": N_("VPN-ul acum"),
}

NOTA_TV = N_("Aceleași lucruri sunt pe televizor, în %s, rândul Alege furnizorul (fără fișiere).")

TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi starea."),
	"nuRaspunde": N_("Receptorul nu răspunde."),
	"seTrimite": N_("Se trimite..."),
	"salvate": N_("salvate"),
	"lipsesc": N_("lipsesc"),
	"scrieAlta": N_("Scrie alta ca s-o schimbi"),
	"seCitesc": N_("Se citește lista țărilor..."),
	"alegeTara": N_("Alege țara"),
	"faraTara": N_("Alege întâi țara."),
	"scrieContul": N_("Scrie întâi contul."),
	"intrebareSterge": N_("Ștergi de pe receptor contul acestui furnizor?"),
	"numaiStarea": N_("Cu cheia pentru scripturi pagina arată numai starea."),
}


def pagina_text(stil, config_pagina):
	import html
	from . import meniu_comun_web as MC
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA_TV), quote=False)
	nota = nota.replace("%s", MC.drumHtml("hds_vpn"), 1) if "%s" in nota else nota
	text = text.replace("__LIMBA__", _limba()).replace("__NOTA_TV__", nota).replace("__TEXTE_JS__",
		_json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
	return MC.sablon(text, stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .rand > *{min-width:0;}
  .rand select, .rand input[type=text]{width:100%;box-sizing:border-box;}
  .vpn{font-weight:600;}
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <section class="card">
    <div class="rand"><label for="furnizor">__T_FURNIZOR__</label><select id="furnizor"></select></div>
    <p class="nota" id="ajutor"></p>
    <p class="nota" id="indisponibil"></p>
  </section>
  <section class="card" id="cardCont">
    <h2><span id="titluCont">__T_CONT__</span> <span class="nota" id="contStare"></span></h2>
    <div id="randuriNume">
      <div class="rand"><label for="nume">__T_NUME__</label><input type="text" id="nume" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="128"></div>
      <div class="rand"><label for="parola">__T_PAROLA__</label><input type="text" id="parola" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="128"></div>
    </div>
    <div class="rand" id="randNumar"><label for="numar">__T_NUMAR__</label><input type="text" id="numar" inputmode="numeric" autocomplete="off" spellcheck="false" maxlength="24"></div>
    <p class="nota" id="contNota"></p>
    <div class="rand"><label for="tara">__T_TARA__</label><select id="tara"></select></div>
    <div class="butoane">
      <button type="button" class="principal" id="pune">__T_PUNE__</button>
      <button type="button" id="dinNou">__T_DIN_NOU__</button>
      <button type="button" class="rosu" id="sterge">__T_STERGE__</button>
    </div>
    <p class="mesaj" id="mesaj"></p>
  </section>
  <section class="card">
    <p><span>__T_VPN__:</span> <span class="vpn" id="vpn"></span></p>
    <p><a href="/vpn">__T_INAPOI__</a></p>
  </section>
  <p class="nota">__NOTA_TV__</p>
</div>
</main>
<script>__SCRIPT_COMUN__
var TXT = __TEXTE_JS__;
var D = null, ALES = null, ASTEPT = null, VAZUTA = null, CERUTE = {}, APLICA = "";
function pune(id, text){ $(id).textContent = text || ""; }
function optiuni(sel, lista, ales){
  if(document.activeElement === sel){ return; }
  var vechi = Array.prototype.map.call(sel.options, function(o){ return o.value + "|" + o.textContent; }).join("\\n");
  var nou = lista.map(function(x){ return x[0] + "|" + x[1]; }).join("\\n");
  if(vechi !== nou){
    sel.textContent = "";
    lista.forEach(function(x){ var o = document.createElement("option"); o.value = x[0]; o.textContent = x[1]; sel.appendChild(o); });
  }
  if(ales !== null){ sel.value = ales; }
}
function arata(d){
  D = d; ALES = d.furnizor;
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  optiuni($("furnizor"), d.furnizori, d.furnizor);
  pune("ajutor", d.ajutor); pune("indisponibil", d.indisponibil); pune("vpn", d.text_vpn);
  var cuCont = (d.cu_cont || []).indexOf(d.furnizor) !== -1 && !d.indisponibil;
  $("cardCont").classList.toggle("ascuns", !cuCont);
  if(cuCont){
    pune("titluCont", d.eticheta_cont); pune("contNota", d.nota_cont);
    pune("contStare", "(" + (d.cont ? TXT.salvate : TXT.lipsesc) + ")");
    $("randuriNume").classList.toggle("ascuns", d.fel_cont !== "nume_parola");
    $("randNumar").classList.toggle("ascuns", d.fel_cont !== "numar");
    $("parola").placeholder = d.cont ? TXT.scrieAlta : ""; $("numar").placeholder = d.cont ? TXT.scrieAlta : "";
    $("sterge").disabled = !d.cont;
    var tari = (d.tari || []).map(function(t){ return [t.cod, t.titlu]; });
    var alesTara = $("tara").value;
    tari.unshift(["", d.tari ? TXT.alegeTara : TXT.seCitesc]);
    optiuni($("tara"), tari, tari.some(function(t){ return t[0] === alesTara; }) ? alesTara : "");
    if(!d.tari && !d.lucreaza && !CERUTE[d.furnizor] && d.asociat){ CERUTE[d.furnizor] = 1; trimite("/api/vpn-furnizor-tari", {furnizor: d.furnizor}); }
  }
  if(d.nivel === "jeton"){ mesaj(TXT.numaiStarea); }
  if(!d.asociat){
    Array.prototype.forEach.call(document.querySelectorAll("#continut button, #continut select, #continut input"), function(e){ e.disabled = true; });
  }
  if(d.lucreaza){ mesaj(d.text_lucreaza); }
  if(d.ultima && d.ultima.id !== VAZUTA){
    var noua = VAZUTA !== null || ASTEPT !== null;
    VAZUTA = d.ultima.id;
    if(noua && (ASTEPT === null || d.ultima.id >= ASTEPT)){ mesaj(d.ultima.mesaj, !d.ultima.reusit); ASTEPT = null; }
  }
  if(d.aplica && d.aplica !== APLICA){ APLICA = d.aplica; mesaj(d.aplica, true); }
}
function citeste(){
  return cerere("/api/vpn-furnizor?furnizor=" + encodeURIComponent(ALES || "")).then(function(d){
    if(d && d.result){ arata(d); } else { mesaj((d && d.message) || TXT.necitit, true); }
  }).catch(function(){ mesaj(TXT.nuRaspunde, true); });
}
function trimite(cale, campuri){
  var q = new URLSearchParams(); Object.keys(campuri || {}).forEach(function(k){ q.append(k, campuri[k]); });
  mesaj(TXT.seTrimite);
  return cerere(cale, "POST", q).then(function(r){
    if(r.message){ mesaj(r.message, !r.result); }
    if(r.lucrare){ ASTEPT = r.lucrare; }
    return citeste().then(function(){ return r; });
  }).catch(function(){ mesaj(TXT.nuRaspunde, true); });
}
$("furnizor").addEventListener("change", function(){ ALES = this.value; $("tara").value = ""; mesaj(""); citeste(); });
$("dinNou").addEventListener("click", function(){ if(ALES){ trimite("/api/vpn-furnizor-tari", {furnizor: ALES, din_nou: "1"}); } });
$("pune").addEventListener("click", function(){
  if(!D){ return; }
  var tara = $("tara").value;
  if(!tara){ mesaj(TXT.faraTara, true); return; }
  var c = {furnizor: D.furnizor, tara: tara};
  if(D.fel_cont === "numar"){ c.numar = $("numar").value.trim(); }
  else { c.nume = $("nume").value.trim(); c.parola = $("parola").value; }
  if(!D.cont && !(c.numar || (c.nume && c.parola))){ mesaj(TXT.scrieContul, true); return; }
  trimite("/api/vpn-furnizor-configureaza", c).then(function(r){
    if(r && r.result){ $("nume").value = ""; $("parola").value = ""; $("numar").value = ""; }
  });
});
$("sterge").addEventListener("click", function(){
  if(D && confirm(TXT.intrebareSterge)){ trimite("/api/vpn-furnizor-sterge", {furnizor: D.furnizor, confirmat: "1"}); }
});
function planifica(){ setTimeout(function(){ citeste().then(planifica, planifica); }, (ASTEPT !== null || (D && D.lucreaza)) ? 800 : 2500); }
citeste().then(planifica, planifica);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
	),
	"js": (
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

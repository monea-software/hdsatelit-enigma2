# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# limbi_web.py: „Limba sunetului și a subtitrărilor” in interfata web (HdsWebControl).
#
# Orice ecran sau setare de pe receptor are pereche in interfata web.
# Pe televizor: Meniu > Setari > Audio & Sound Tracks > Limba sunetului si a subtitrarilor (Screens/HdsPisteLimbi.py).
# Aici: aceleasi 8 setari (cate 3 preferinte pentru sunet si subtitrare, „Fără subtitrări niciodată”, „Tradu automat din
# orice subtitrare disponibilă”, care conteaza cu traducerea subtitrarilor pornita), cu aceleasi
# alegeri (luate chiar din setarile config.hds_piste, nu scrise a doua oara), randurile subtitrarii ascunse la
# „niciodata” ca pe televizor, ce se tine minte pe canalul care merge, lista canalelor cu alegeri de mana si „Uită”.
# Dupa salvare preferintele se aplica pe loc pe canalul care merge (reaplicaAcum), ca la Verde pe televizor.
#
# O SINGURA LOGICA: preferintele, memoria alegerilor si aplicarea lor sunt in Components/HdsPisteLimbi.py.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/limbi                                   setarile, alegerile, canalul care merge, canalele tinute minte
#   POST /api/limbi-seteaza?audio1=..&sub1=..&fara_subtitrari=0|1&tradu_orice=0|1   schimba si salveaza (oricare)
#   POST /api/limbi-uita?cheie=<cheia canalului>      uita alegerile de mana ale unui canal din lista
#   POST /api/limbi-uita-toate?confirmat=1            uita alegerile de pe toate canalele
#   GET  /limbi                                       pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; apelurile sunt scurte (fisierele alegerilor au cel mult
# cativa MB si se citesc numai cand s-au schimbat). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe
# PC dau modulul lor (L), setarile lor si sesiunea lor.

SETARI_AUDIO = ("audio1", "audio2", "audio3")
SETARI_SUB = ("sub1", "sub2", "sub3")
DA_NU = ("fara_subtitrari", "tradu_orice")
SETARI = SETARI_AUDIO + ("fara_subtitrari",) + SETARI_SUB + ("tradu_orice",)


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# textele randurilor, aceleasi ca pe televizor (Screens/HdsPisteLimbi.py, _faLista)
ETICHETE = {
	"audio1": N_("Sunet, prima alegere"),
	"audio2": N_("Sunet, a doua alegere"),
	"audio3": N_("Sunet, a treia alegere"),
	"fara_subtitrari": N_("Fără subtitrări niciodată"),
	"sub1": N_("Subtitrare, prima alegere"),
	"sub2": N_("Subtitrare, a doua alegere"),
	"sub3": N_("Subtitrare, a treia alegere"),
	"tradu_orice": N_("Tradu automat din orice subtitrare disponibilă"),
}

# tipurile de serviciu incercate pentru numele unui canal din cheie (cheia nu tine tipul): TV HD, TV SD, alte HD, radio
TIPURI_NUME = (0x19, 1, 0x16, 0x1f, 2)
MAX_CANALE_LISTA = 300
MAX_CHEIE = 200


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _l(L=None):
	if L is not None:
		return L
	from Components import HdsPisteLimbi
	return HdsPisteLimbi


def _salveazaFisierul(configfile=None):
	if configfile is None:
		from Components.config import configfile
	configfile.save()


def _numeCanal(L, cheie):
	"""Numele canalului pentru o cheie din fisierul alegerilor: din lista de canale a receptorului; la fluxuri, adresa."""
	if cheie.startswith("url:"):
		return cheie[4:]
	try:
		from ServiceReference import ServiceReference
	except Exception:
		return ""
	for tip in TIPURI_NUME:
		ref = L.referintaDinCheie(cheie, tip)
		if not ref:
			return ""
		try:
			nume = ServiceReference(ref).getServiceName()
		except Exception:
			nume = ""
		if nume:
			# semnele de evidentiere DVB (0x86, 0x87) din numele venite de la emitator nu se arata
			return nume.replace(u"\u0086", u"").replace(u"\u0087", u"")
	return ""


def _ceSeTineMinte(L, memorat, parte_de_mana):
	"""Partile tinute minte pe un canal, cu textele ecranului de pe televizor (_arataMemoria)."""
	parti = []
	if "a" in memorat:
		parti.append(_t("sunetul ales de mână"))
	if parte_de_mana:
		parti.append(_t("partea sunetului (stânga, stereo sau dreapta) aleasă de mână"))
	if memorat.get("s") == L.OPRIT:
		parti.append(_t("subtitrarea oprită de mână"))
	elif "s" in memorat:
		parti.append(_t("subtitrarea aleasă de mână"))
	return parti


def _canalulDeAcum(L, sesiune):
	"""Ce se tine minte pe canalul care merge acum, cu textele ecranului de pe televizor."""
	if sesiune is None:
		return {"cheie": None, "text": ""}
	try:
		st = L.stareCanal(sesiune)
	except Exception as eroare:
		print("[HdsWebControl] limbi: canalul de acum: %s" % eroare)
		return {"cheie": None, "text": ""}
	cheie = st.get("cheie")
	if cheie is None:
		return {"cheie": None, "text": _t("Pe ce merge acum nu se țin minte alegeri (nu e un canal).")}
	parti = _ceSeTineMinte(L, st.get("memorat") or {}, st.get("parte") == L.PARTE_DE_MANA)
	if parti:
		text = _t("Pe canalul acesta se ține minte: %s.") % u", ".join(parti)
	else:
		text = _t("Pe canalul acesta nu se ține minte nimic, merg alegerile de mai sus.")
	return {"cheie": cheie, "nume": _numeCanal(L, cheie), "text": text}


def _canale(L):
	"""Canalele cu alegeri de mana, cele mai noi intai (cel mult MAX_CANALE_LISTA)."""
	try:
		toate = L.canaleCuAlegeri()
	except Exception as eroare:
		print("[HdsWebControl] limbi: lista canalelor: %s" % eroare)
		return [], 0
	ordonate = sorted(toate.items(), key=lambda kv: (-(kv[1].get("t") or 0), kv[0]))
	rez = []
	for cheie, intrare in ordonate[:MAX_CANALE_LISTA]:
		rez.append({
			"cheie": cheie,
			"nume": _numeCanal(L, cheie),
			"ce": u", ".join(_ceSeTineMinte(L, intrare, bool(intrare.get("parte_de_mana")))),
			"t": int(intrare.get("t") or 0),
		})
	return rez, len(toate)


def _alegeri(element):
	"""[[valoare, text tradus]] din alegerile setarii, in ordinea de pe televizor."""
	rez = []
	for x in element.choices.choices:
		if isinstance(x, tuple):
			rez.append([str(x[0]), _t(x[1])])
		else:
			rez.append([str(x), _t(str(x))])
	return rez


def stare(L=None, sesiune=None):
	"""Pentru GET /api/limbi."""
	L = _l(L)
	c = L.initConfig()
	setari = {}
	for nume in SETARI_AUDIO + SETARI_SUB:
		element = getattr(c, nume)
		setari[nume] = {"eticheta": _t(ETICHETE[nume]), "valoare": str(element.value), "alegeri": _alegeri(element)}
	for nume in DA_NU:
		setari[nume] = {"eticheta": _t(ETICHETE[nume]), "valoare": bool(getattr(c, nume).value)}
	canale, numar = _canale(L)
	return {
		"result": True,
		"ordine": list(SETARI),
		"setari": setari,
		"limba_receptor": L.numeLimba(L.limbaReceptor()),
		"traducere": L.textTraducere(),
		"acum": _canalulDeAcum(L, sesiune),
		"canale": canale,
		"numar_canale": numar,
	}


def _valoareAleasa(element, text):
	"""Valoarea din alegerile setarii care se scrie ca `text`, sau None daca nu e printre ele."""
	for x in element.choices.choices:
		valoare = x[0] if isinstance(x, tuple) else x
		if str(valoare) == text:
			return valoare
	return None


def seteaza(argumente, L=None, sesiune=None, configfile=None):
	"""POST /api/limbi-seteaza: toate valorile primite trebuie sa fie printre alegeri, altfel nu se schimba nimic
	(ConfigSelection ar pune in tacere valoarea implicita). Se salveaza si se aplica pe loc, ca Verde pe televizor."""
	L = _l(L)
	c = L.initConfig()
	noi = {}
	for nume in SETARI_AUDIO + SETARI_SUB:
		if nume in argumente:
			valoare = _valoareAleasa(getattr(c, nume), argumente[nume])
			if valoare is None:
				rez = stare(L, sesiune)
				rez.update({"result": False, "message": _t("Alegerea „%s” nu există pentru „%s”.") % (
					argumente[nume][:40], _t(ETICHETE[nume]))})
				return rez
			noi[nume] = valoare
	for nume in DA_NU:
		if nume not in argumente:
			continue
		if argumente[nume] not in ("0", "1"):
			rez = stare(L, sesiune)
			rez.update({"result": False, "message": _t("„%s” se alege cu 1 (da) sau 0 (nu).") % _t(ETICHETE[nume])})
			return rez
		noi[nume] = argumente[nume] == "1"
	if not noi:
		rez = stare(L, sesiune)
		rez.update({"result": False, "message": _t("Nu s-a trimis nicio setare.")})
		return rez
	for nume, valoare in noi.items():
		element = getattr(c, nume)
		element.value = valoare
		element.save()
	_salveazaFisierul(configfile)
	if sesiune is not None:
		L.reaplicaAcum(sesiune)
	rez = stare(L, sesiune)
	rez.update({"result": True, "message": _t("Salvat. Se aplică și pe canalul de acum.")})
	return rez


def uita(argumente, L=None, sesiune=None):
	"""POST /api/limbi-uita?cheie=...: numai o cheie care e chiar in lista canalelor cu alegeri."""
	L = _l(L)
	cheie = argumente.get("cheie", "")
	if not cheie or cheie not in L.canaleCuAlegeri():
		rez = stare(L, sesiune)
		rez.update({"result": False, "message": _t("Canalul acesta nu are alegeri ținute minte.")})
		return rez
	sterse = L.uitaCheie(cheie)
	acum = _canalulDeAcum(L, sesiune).get("cheie")
	if sterse and sesiune is not None and acum == cheie:
		L.reaplicaAcum(sesiune)
	rez = stare(L, sesiune)
	if sterse:
		rez.update({"result": True, "message": _t("Alegerile de pe canalul acesta au fost uitate.")})
	else:
		rez.update({"result": False, "message": _t("Pe canalul acesta nu era nimic de uitat.")})
	return rez


def uitaToate(argumente, L=None, sesiune=None):
	"""POST /api/limbi-uita-toate?confirmat=1: ca Albastru pe televizor, cu intrebarea puse in pagina."""
	L = _l(L)
	if argumente.get("confirmat") != "1":
		rez = stare(L, sesiune)
		rez.update({"result": False, "message": _t("Se cere confirmarea (confirmat=1).")})
		return rez
	if not L.numarAlegeri():
		rez = stare(L, sesiune)
		rez.update({"result": False, "message": _t("Nu era nimic de uitat.")})
		return rez
	sterse = L.uitaAlegeri(toate=True)
	print("[HdsWebControl] limbi: alegeri uitate pe %d canale (din web)" % sterse)
	if sesiune is not None:
		L.reaplicaAcum(sesiune)
	rez = stare(L, sesiune)
	rez.update({"result": True, "message": _t("Alegerile de pe toate canalele au fost uitate.")})
	return rez


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; numai cheile cunoscute."""
	permise = set(SETARI) | set(("cheie", "confirmat"))
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in permise:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_CHEIE].strip()
	return rez


def rute(baza, resource, sesiune=None, L=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	e o functie care da sesiunea enigma2 (reaplicarea pe canalul care merge)."""

	def _ses():
		try:
			return sesiune() if sesiune is not None else None
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/limbi: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(L, _ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class _Schimba(baza):
		schimbaCeva = True
		lucru = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, type(self).lucru(argumente(request), L=L, sesiune=_ses()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(_Schimba):
		lucru = staticmethod(seteaza)

	class UitaResource(_Schimba):
		lucru = staticmethod(uita)

	class UitaToateResource(_Schimba):
		lucru = staticmethod(uitaToate)

	class PaginaResource(resource.Resource):
		"""GET /limbi: pagina „Limba sunetului și a subtitrărilor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"limbi": StareResource(),
		b"limbi-seteaza": SeteazaResource(),
		b"limbi-uita": UitaResource(),
		b"limbi-uita-toate": UitaToateResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic si /ceas."""
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
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	return _traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__",
		config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("hds_piste_limbi"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Limba sunetului și a subtitrărilor</title>
<style>__STIL_COMUN__
  main{max-width:820px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:.95rem;margin:0 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(160px,260px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.albastru{background:var(--albastru);border-color:var(--albastru);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .acum{font-size:.98rem;line-height:1.45;margin:0 0 8px;}
  .butoane{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;}
  table{width:100%;border-collapse:collapse;font-size:.9rem;}
  td,th{padding:8px 6px;border-bottom:1px solid var(--bordura);text-align:left;vertical-align:middle;}
  th{color:var(--text-slab);font-weight:normal;}
  td.actiune{text-align:right;width:1%;white-space:nowrap;}
  td.nume{word-break:break-word;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} td.actiune{white-space:normal;} }
</style>
</head>
<body>
<main>
<h1>Limba sunetului și a subtitrărilor</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Preferințele</h2>
    <div id="randuri"></div>
    <div class="butoane"><button type="button" class="verde" id="salveaza">Salvează</button></div>
    <p class="nota" id="ajutor"></p>
  </section>
  <section class="card">
    <h2>Canalul de acum</h2>
    <p class="acum" id="acum"></p>
  </section>
  <section class="card">
    <h2>Canale cu alegeri ținute minte</h2>
    <p class="nota" id="numar"></p>
    <table id="tabel"><thead><tr><th>Canalul</th><th>Ce se ține minte</th><th></th></tr></thead><tbody id="canale"></tbody></table>
    <div class="butoane"><button type="button" class="albastru" id="uitaToate">Uită toate canalele</button></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var DATE = null;
var SCHIMBAT = false;
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
function randSelect(nume, s){
  var d = document.createElement("div"); d.className = "rand"; d.id = "rand_" + nume;
  var l = document.createElement("label"); l.setAttribute("for", "s_" + nume); l.textContent = s.eticheta;
  var sel = document.createElement("select"); sel.id = "s_" + nume;
  if(typeof s.valoare === "boolean"){
    [["1", "Da"], ["0", "Nu"]].forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
    sel.value = s.valoare ? "1" : "0";
  } else {
    (s.alegeri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; sel.appendChild(o); });
    sel.value = s.valoare;
  }
  sel.addEventListener("change", function(){ SCHIMBAT = true; ascundeSub(); });
  d.appendChild(l); d.appendChild(sel);
  return d;
}
function ascundeSub(){
  var niciodata = $("s_fara_subtitrari") && $("s_fara_subtitrari").value === "1";
  ["sub1", "sub2", "sub3", "tradu_orice"].forEach(function(n){ var r = $("rand_" + n); if(r){ r.classList.toggle("ascuns", niciodata); } });
}
function arataSetari(d){
  var c = $("randuri"); c.textContent = "";
  (d.ordine || []).forEach(function(n){ c.appendChild(randSelect(n, d.setari[n])); });
  ascundeSub();
  SCHIMBAT = false;
  $("ajutor").textContent = "La fiecare canal pornește prima alegere care există pe canal. Dacă nu există subtitrare în limbile alese, nu pornește nicio subtitrare. Limba receptorului acum: " + d.limba_receptor + ". Ce alegi de mână pe un canal, din ecranul sunetului sau al subtitrărilor, se ține minte pentru canalul acela și are întâietate față de aceste alegeri. " + (d.traducere || "");
}
function arataCanale(d){
  var a = d.acum || {};
  $("acum").textContent = (a.nume ? a.nume + ": " : "") + (a.text || "");
  $("numar").textContent = d.numar_canale ? ("Canale cu alegeri ținute minte: " + d.numar_canale + ".") : "Niciun canal nu are alegeri ținute minte.";
  $("tabel").classList.toggle("ascuns", !d.numar_canale);
  $("uitaToate").disabled = !d.numar_canale;
  var corp = $("canale"); corp.textContent = "";
  (d.canale || []).forEach(function(k){
    var tr = document.createElement("tr");
    var n = document.createElement("td"); n.className = "nume"; n.textContent = k.nume || k.cheie;
    var ce = document.createElement("td"); ce.textContent = k.ce;
    var ac = document.createElement("td"); ac.className = "actiune";
    var b = document.createElement("button"); b.type = "button"; b.textContent = "Uită";
    b.addEventListener("click", function(){ trimite("/api/limbi-uita", {cheie: k.cheie}); });
    ac.appendChild(b); tr.appendChild(n); tr.appendChild(ce); tr.appendChild(ac); corp.appendChild(tr);
  });
}
function arata(d, cuSetari){
  DATE = d;
  if(cuSetari || !SCHIMBAT){ arataSetari(d); }
  arataCanale(d);
}
function citeste(cuSetari){
  return cerere("/api/limbi").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d, cuSetari);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, valori){
  var q = new URLSearchParams();
  Object.keys(valori).forEach(function(k){ q.set(k, valori[k]); });
  mesaj("Se trimite...");
  return cerere(cale, "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.setari){ arata(d, d.result); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
$("salveaza").addEventListener("click", function(){
  var v = {};
  (DATE.ordine || []).forEach(function(n){ var s = $("s_" + n); if(s){ v[n] = s.value; } });
  trimite("/api/limbi-seteaza", v);
});
$("uitaToate").addEventListener("click", function(){
  if(!DATE || !DATE.numar_canale){ return; }
  if(!confirm("Uiți alegerile de mână de pe toate canalele (" + DATE.numar_canale + ")? De acum merg alegerile de mai sus.")){ return; }
  trimite("/api/limbi-uita-toate", {confirmat: "1"});
});
citeste(true);
setInterval(function(){ citeste(false); }, 10000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Limba sunetului și a subtitrărilor"),
		N_("Se citesc setările..."),
		N_("Preferințele"),
		N_("Salvează"),
		N_("Canalul de acum"),
		N_("Canale cu alegeri ținute minte"),
		N_("Canalul"),
		N_("Ce se ține minte"),
		N_("Uită toate canalele"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Da"),
		N_("Nu"),
		N_("La fiecare canal pornește prima alegere care există pe canal. Dacă nu există subtitrare în "
			"limbile alese, nu pornește nicio subtitrare. Limba receptorului acum:"),
		N_(". Ce alegi de mână pe un canal, din ecranul sunetului sau al subtitrărilor, se ține minte "
			"pentru canalul acela și are întâietate față de aceste alegeri."),
		N_("Canale cu alegeri ținute minte:"),
		N_("Niciun canal nu are alegeri ținute minte."),
		N_("Uită"),
		N_("Receptorul nu a putut citi setările."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Uiți alegerile de mână de pe toate canalele ("),
		N_(")? De acum merg alegerile de mai sus."),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# locuri_retea_web.py: "Locuri din rețea" in interfata web (HdsWebControl), perechea ecranelor de pe televizor
# (Screens/HdsLocuriRetea.py, Media > Locuri din retea).
#
# O SINGURA LOGICA: locurile, parolele, montarea, cautarea in casa, rasfoirea si redarea sunt in
# Components/HdsStocareRetea.py; textele si mesajele sunt aceleasi ca pe televizor. Aici: lista locurilor cu starea lor,
# adaugarea si editarea (parola se scrie, nu se arata niciodata: campul ramane gol, iar gol = neschimbata), montarea si
# demontarea, proba pentru inregistrari, stergerea, cautarea serverelor din casa, rasfoirea unui loc si pornirea unui
# film pe televizor, cu subtitrarile de langa el.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/locuri-retea                    locurile (fara parole), cautarea in casa
#   POST /api/locuri-retea-salveaza           adauga (fara id) sau schimba un loc; parola: gol = neschimbata,
#                                             sterge_parola=1 = stearsa
#   POST /api/locuri-retea-fa?fa=monteaza|demonteaza|viteza|sterge&id=...
#   POST /api/locuri-retea-cauta              porneste cautarea in casa (rezultatul in /api/locuri-retea)
#   POST /api/locuri-retea-rasfoieste?id=&cale=   porneste citirea dosarului -> {lucrare}
#   POST /api/locuri-retea-dosare?fel=&gazda=&utilizator=&id=   lista dosarelor serverului (NFS, SMB) -> {lucrare}
#   POST /api/locuri-retea-reda?lucrare=&index=   porneste pe televizor fisierul din dosarul citit de acea lucrare
#   GET  /api/locuri-retea-lucrare?lucrare=   rezultatul unei lucrari (gata sau nu)
#   GET  /locuri-retea                        pagina
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; lucrarile din retea ruleaza pe firele componentei, iar
# rezultatul lor se tine aici (LUCRARI, cel mult MAX_LUCRARI, cele mai vechi pleaca) pana il cere pagina.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau componenta lor (S).

import os
import time

MAX_TEXT = 400
MAX_LUCRARI = 20
CAMPURI = ("id", "fel", "nume", "gazda", "port", "dosar", "utilizator", "parola", "sterge_parola", "pornire", "citire",
	"tls_oricare", "control", "fa", "cale", "lucrare", "index")


def _t(text):
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _s(S=None):
	if S is not None:
		return S
	from Components import HdsStocareRetea
	return HdsStocareRetea


LUCRARI = {}


def _lucrareNoua(fel, date=None):
	if len(LUCRARI) >= MAX_LUCRARI:
		for k in sorted(LUCRARI, key=lambda k: LUCRARI[k]["timp"])[:len(LUCRARI) - MAX_LUCRARI + 1]:
			LUCRARI.pop(k, None)
	cheie = os.urandom(8).hex()
	LUCRARI[cheie] = {"fel": fel, "gata": False, "rez": None, "timp": time.time(), "date": date or {}}
	return cheie


def _gata(cheie):
	def pune(rez):
		if cheie in LUCRARI:
			LUCRARI[cheie]["gata"] = True
			LUCRARI[cheie]["rez"] = rez
	return pune


def _intrarePagina(i):
	"""O intrare din dosar pentru pagina (fara adresele serverului)."""
	return {"nume": i.get("nume") or "", "dosar": bool(i.get("dosar")), "fel": i.get("fel") or "",
		"marime": i.get("marime"), "marime_text": _s().marime(i.get("marime")) if not i.get("dosar") else "",
		"durata": _s().durata(i.get("durata")) if i.get("durata") else "", "cale": i.get("cale") or "",
		"subtitrari": len(i.get("subtitrari") or [])}


def stare(S=None):
	S = _s(S)
	c = S.rezultatCautare()
	return {"result": True, "locuri": S.toate(), "feluri": [{"fel": f, "text": S.textFel(f)} for f in S.FELURI],
		"cautare": {"in_lucru": bool(c.get("in_lucru")), "gasite": c.get("gasite") or [],
			"mesaj": S.textEroare(c["cod"]) if c.get("cod") else ""}}


def salveaza(a, S=None):
	S = _s(S)
	ident = a.get("id") or None
	if a.get("sterge_parola") in ("1", "da", "true"):
		parola = ""
	else:
		parola = a.get("parola") or None
		if parola is None and not ident and a.get("utilizator"):
			parola = ""
	date = dict((k, a.get(k)) for k in ("fel", "nume", "gazda", "port", "dosar", "utilizator", "control") if k in a)
	for k in ("pornire", "citire", "tls_oricare"):
		date[k] = a.get(k) in ("1", "da", "true", "on")
	d, eroare = S.salveaza(date, parola, ident)
	rez = stare(S)
	if d is None:
		rez.update(result=False, message=eroare)
	else:
		rez.update(result=True, message=eroare or (_t("Locul %s a fost salvat.") % d["nume"]), loc=d)
	return rez


def fa(a, S=None):
	"""monteaza, demonteaza, viteza, sterge: pornite aici, rezultatul in starea locului (pagina intreaba din nou)."""
	S = _s(S)
	ident = a.get("id") or ""
	ce = a.get("fa") or ""
	if S.locuri().dupaId(ident) is None:
		rez = stare(S)
		rez.update(result=False, message=S.textEroare("lipsa"))
		return rez
	cheie = _lucrareNoua(ce)
	functii = {"monteaza": S.monteaza, "demonteaza": S.demonteaza, "viteza": S.verificaInregistrari, "sterge": S.sterge}
	if ce not in functii:
		rez = stare(S)
		rez.update(result=False, message=S.textEroare("cerere"))
		return rez
	if ce == "viteza":
		loc = S.locuri().dupaId(ident)
		if loc["fel"] in S.FELURI_MONTATE and not S.esteMontat(loc)[0]:
			# montat intai, apoi proba
			S.monteaza(ident, lambda r: S.verificaInregistrari(ident, _gata(cheie)) if r.get("ok") else _gata(cheie)(r))
		else:
			S.verificaInregistrari(ident, _gata(cheie))
	else:
		functii[ce](ident, _gata(cheie))
	rez = stare(S)
	rez.update(result=True, lucrare=cheie)
	return rez


def cauta(S=None):
	S = _s(S)
	S.cautaInCasa()
	return stare(S)


def rasfoieste(a, S=None):
	S = _s(S)
	ident = a.get("id") or ""
	if S.locuri().dupaId(ident) is None:
		return {"result": False, "message": S.textEroare("lipsa")}
	cheie = _lucrareNoua("rasfoieste", {"id": ident, "cale": a.get("cale") or ""})
	S.listeaza(ident, a.get("cale") or "", _gata(cheie))
	return {"result": True, "lucrare": cheie}


def dosare(a, S=None):
	S = _s(S)
	fel = a.get("fel") or ""
	gazda, _p, _d = S.desparteGazda(a.get("gazda") or "", fel)
	if fel not in S.FELURI_MONTATE or not S.gazdaBuna(gazda):
		return {"result": False, "message": _t("Scrie întâi serverul.")}
	cheie = _lucrareNoua("dosare")
	S.dosareServer(fel, gazda, a.get("utilizator") or "", a.get("id") or None, a.get("parola") or None, _gata(cheie))
	return {"result": True, "lucrare": cheie}


def lucrare(a, S=None):
	"""Rezultatul unei lucrari, pentru pagina: dosarul citit (fara adresele serverului), dosarele, un mesaj."""
	S = _s(S)
	l = LUCRARI.get(a.get("lucrare") or "")
	if l is None:
		return {"result": False, "message": _t("Cererea a expirat. Încearcă încă o dată.")}
	if not l["gata"]:
		return {"result": True, "gata": False}
	r = l["rez"] or {}
	rez = {"result": True, "gata": True, "ok": bool(r.get("ok")), "mesaj": r.get("mesaj") or (
		"" if r.get("ok") else S.textEroare(r.get("cod") or "alta"))}
	if l["fel"] == "rasfoieste":
		rez["intrari"] = [_intrarePagina(i) for i in r.get("intrari") or []]
		rez["cale"] = l["date"].get("cale") or ""
	elif l["fel"] == "dosare":
		rez["dosare"] = r.get("dosare") or []
	return rez


def reda(a, sesiune=None, S=None):
	"""Porneste pe televizor fisierul `index` din dosarul citit de lucrarea data (numai din lista citita, niciodata o
	cale venita din cerere)."""
	S = _s(S)
	l = LUCRARI.get(a.get("lucrare") or "")
	if l is None or l["fel"] != "rasfoieste" or not l["gata"] or not (l["rez"] or {}).get("ok"):
		return {"result": False, "message": _t("Citește din nou dosarul, apoi alege filmul.")}
	try:
		index = int(a.get("index") or -1)
		intrare = l["rez"]["intrari"][index]
	except (ValueError, IndexError, KeyError):
		return {"result": False, "message": _t("Citește din nou dosarul, apoi alege filmul.")}
	if intrare.get("dosar") or index < 0:
		return {"result": False, "message": _t("Alege un film sau o melodie.")}
	cheie = _lucrareNoua("reda")
	ses = sesiune() if callable(sesiune) else sesiune

	def gata(r):
		if r.get("ok"):
			ok, mesaj = S.deschidePeTv(ses, r)
			r = dict(r, ok=ok, mesaj=mesaj)
		_gata(cheie)(r)
	S.pregatesteRedarea(l["date"]["id"], intrare, l["rez"].get("toate") or [], gata)
	return {"result": True, "lucrare": cheie, "message": _t("Se pregătește filmul...")}


def argumente(request):
	"""Argumentele cererii (query si corpul formularului) ca text scurt, numai cheile cunoscute; fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:32]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in CAMPURI:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT] if cheie == "parola" else str(v)[:MAX_TEXT].strip()
	return rez


def rute(baza, resource, sesiune=None, S=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii)."""

	def _eroare(self, request, e):
		return self._eroare(request, _t("Eroare pe receptor: %s") % e, 500)

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(S))
			except Exception as e:
				return _eroare(self, request, e)

	class LucrareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, lucrare(argumente(request), S))
			except Exception as e:
				return _eroare(self, request, e)

	def faraDeGet(functie, cuGet=True):
		"""Resursa unei fapte: POST (din browser, cu CSRF); cuGet=True si GET cu ?token= (scripturi). Rutele care
		primesc o parola sunt numai POST: parola nu ajunge niciodata intr-o adresa."""
		class R(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(argumente(request)))
				except Exception as e:
					return _eroare(self, request, e)

		if cuGet:
			R.render_GET = lambda self, request: self.render_POST(request)
		return R()

	class PaginaResource(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"locuri-retea": StareResource(),
		b"locuri-retea-lucrare": LucrareResource(),
		b"locuri-retea-salveaza": faraDeGet(lambda a: salveaza(a, S), cuGet=False),
		b"locuri-retea-fa": faraDeGet(lambda a: fa(a, S)),
		b"locuri-retea-cauta": faraDeGet(lambda a: cauta(S)),
		b"locuri-retea-rasfoieste": faraDeGet(lambda a: rasfoieste(a, S)),
		b"locuri-retea-dosare": faraDeGet(lambda a: dosare(a, S), cuGet=False),
		b"locuri-retea-reda": faraDeGet(lambda a: reda(a, sesiune, S)),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /stocare."""
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
		config_pagina).replace("__DRUM_MENIU__", _drumMeniu("hds_locuri_retea"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Locuri din rețea</title>
<style>__STIL_COMUN__
  main{max-width:980px;margin:0 auto;}
  .cap{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin:0 0 18px;}
  h1{font-size:1.6rem;margin:0;}
  .cap p{margin:0;color:var(--text-slab);font-size:.95rem;}
  h2{font-size:.85rem;margin:22px 0 10px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.08em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 10px;}
  .loc{display:flex;gap:16px;align-items:center;flex-wrap:wrap;}
  .loc .info{flex:1 1 320px;min-width:0;}
  .loc .nume{font-size:1.15rem;font-weight:600;overflow-wrap:anywhere;}
  .eticheta{display:inline-block;font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:3px 7px;border-radius:4px;background:#1f2b4a;color:#8fb4ff;margin-left:8px;vertical-align:middle;}
  .mic{color:var(--text-slab);font-size:.85rem;margin-top:3px;overflow-wrap:anywhere;}
  .stare{font-size:.9rem;margin-top:5px;}
  .stare.montat{color:#4fd18b;} .stare.eroare{color:#ff8a7a;} .stare.lucreaza{color:#f5b83d;}
  .actiuni{display:flex;gap:8px;flex-wrap:wrap;}
  button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button.albastru{background:#2f4fa8;border-color:#2f4fa8;color:#fff;}
  button.rosu{background:#3a1f22;border-color:#5a2a2e;color:#ffb4a8;}
  button:disabled{opacity:.5;cursor:default;}
  label{display:block;margin:10px 0 4px;color:var(--text-slab);font-size:.88rem;}
  input,select{width:100%;min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#12161c;color:var(--text);font:inherit;}
  .bife label{display:flex;gap:10px;align-items:center;color:var(--text);}
  .bife input{width:auto;min-height:0;}
  .rand{display:grid;grid-template-columns:1fr 1fr;gap:0 14px;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  table{width:100%;border-collapse:collapse;font-size:.92rem;}
  td{padding:8px 6px;border-bottom:1px solid var(--bordura);vertical-align:middle;}
  td.actiune{text-align:right;white-space:nowrap;width:1%;}
  .drum{font-size:.95rem;margin:0 0 8px;overflow-wrap:anywhere;}
  .drum a{color:#7fb8ff;cursor:pointer;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} .actiuni button{flex:1 1 45%;} }
</style>
</head>
<body>
<main>
<div class="cap"><h1>Locuri din rețea</h1><p>Filme, muzică și înregistrări de pe calculatorul cu Windows, NAS, FTP, WebDAV sau serverul media din casă</p></div>
<p class="mesaj" id="incarcare">Se citesc locurile...</p>
<div id="continut" class="ascuns">
  <div id="mesajSus" class="mesaj ascuns"></div>
  <h2>Locurile tale</h2>
  <p class="nota" id="fara">Niciun loc încă. Adaugă unul mai jos sau caută serverele din casă.</p>
  <div id="locuri"></div>
  <section class="card ascuns" id="cardRasfoire">
    <div class="drum" id="drum"></div>
    <p class="mesaj" id="rasfoireStare"></p>
    <table><tbody id="intrari"></tbody></table>
    <p class="nota">Subtitrările de lângă film (același nume, sau dosarul Subs) și cele date de serverul media se iau singure. Pe televizor, tasta SUB le arată pe toate, cu codarea și întârzierea.</p>
  </section>
  <h2>Caută în casă</h2>
  <section class="card">
    <p class="nota">Receptorul întreabă scurt aparatele din rețeaua ta: serverele media (DLNA), calculatoarele cu Windows și NAS-urile cu dosare partajate, serverele care se anunță (NFS, WebDAV, FTP). Nimic nu pleacă în afara rețelei tale și nimic nu se caută singur.</p>
    <div class="actiuni" style="margin-top:10px"><button type="button" class="albastru" id="cauta">Caută serverele din casă</button></div>
    <p class="mesaj" id="cautareStare"></p>
    <table><tbody id="gasite"></tbody></table>
  </section>
  <h2 id="titluFormular">Adaugă un loc</h2>
  <section class="card">
    <form id="formular" autocomplete="off">
      <input type="hidden" id="f_id" value="">
      <input type="hidden" id="f_control" value="">
      <div class="rand">
        <div><label for="f_fel">Felul locului</label><select id="f_fel"></select></div>
        <div><label for="f_nume">Numele (cum apare în listă)</label><input id="f_nume" maxlength="60"></div>
      </div>
      <div class="rand">
        <div><label for="f_gazda">Serverul (nume sau adresă)</label><input id="f_gazda" maxlength="300" placeholder="192.168.1.20"></div>
        <div id="d_dosar"><label for="f_dosar">Dosarul</label><input id="f_dosar" maxlength="400"><div class="actiuni" style="margin-top:6px"><button type="button" id="alegeDosar">Alege din lista serverului</button></div></div>
      </div>
      <div class="rand" id="d_cont">
        <div><label for="f_utilizator">Utilizatorul (gol: fără cont)</label><input id="f_utilizator" maxlength="120" autocomplete="off"></div>
        <div><label for="f_parola">Parola</label><input id="f_parola" type="password" maxlength="256" autocomplete="new-password"><p class="nota ascuns" id="parolaNota">Este salvată o parolă. Lasă câmpul gol ca să rămână aceeași.</p></div>
      </div>
      <div class="rand">
        <div id="d_port"><label for="f_port">Portul (0: cel obișnuit)</label><input id="f_port" type="number" min="0" max="65535" value="0"></div>
        <div></div>
      </div>
      <div class="bife">
        <label id="d_pornire"><input type="checkbox" id="f_pornire"> Montat și după repornire (trebuie pentru înregistrările programate pe el)</label>
        <label id="d_citire"><input type="checkbox" id="f_citire"> Numai citire</label>
        <label id="d_tls"><input type="checkbox" id="f_tls"> Primește un certificat făcut acasă</label>
        <label id="d_sterge" class="ascuns"><input type="checkbox" id="f_sterge"> Șterge parola salvată</label>
      </div>
      <p class="nota" id="ajutorFel"></p>
      <div class="actiuni" style="margin-top:12px"><button type="submit" class="verde" id="salveaza">Salvează locul</button><button type="button" id="renunta" class="ascuns">Renunță</button></div>
      <div id="mesajFormular" class="mesaj"></div>
    </form>
  </section>
  <p class="nota">Locurile SMB și NFS se montează pe receptor: apar și în Player media, ca un disc, și pot ține înregistrări după proba de scriere și viteză. Locul înregistrărilor se alege apoi în <a data-cale="/stocare" href="/stocare" style="color:inherit">Locul înregistrărilor</a>. Parolele stau criptate pe receptor și nu se arată nicăieri.</p>
  <p class="nota">Același ecran este pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var CEAS = null;
var ULTIMA = null;
var RASFOIRE = null;
var AJUTOR = {
  smb: "Calculatorul cu Windows sau NAS-ul: scrie numele dosarului partajat (de pildă Filme). Pe Windows, utilizatorul este contul tău.",
  nfs: "NAS sau Linux: dosarul exportat (de pildă volume1/filme). Fără parolă.",
  ftp: "Server FTP: dosarul de pe server (gol: tot serverul).",
  ftps: "Ca FTP, cu legătura criptată.",
  webdav: "WebDAV: dosarul de pe server, de pildă remote.php/dav/files/nume.",
  webdavs: "Ca WebDAV, cu legătura criptată (HTTPS).",
  dlna: "Serverul media din casă: îl găsești cel mai ușor cu Caută serverele din casă."
};
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
function mesaj(loc, text, eroare){
  var m = $(loc); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); m.classList.toggle("ascuns", !text);
}
function buton(text, clasa, fn){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text; if(clasa){ b.className = clasa; }
  b.addEventListener("click", fn); return b;
}
function arata(d){
  ULTIMA = d;
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var sel = $("f_fel");
  if(!sel.options.length){
    (d.feluri || []).forEach(function(f){ var o = document.createElement("option"); o.value = f.fel; o.textContent = f.text; sel.appendChild(o); });
    potriveste();
  }
  var c = $("locuri"); c.textContent = "";
  var lucreaza = false;
  (d.locuri || []).forEach(function(l){
    if(l.stare === "lucreaza"){ lucreaza = true; }
    var card = document.createElement("section"); card.className = "card loc";
    var info = document.createElement("div"); info.className = "info";
    var n = document.createElement("div"); n.className = "nume"; n.textContent = l.nume;
    var e = document.createElement("span"); e.className = "eticheta"; e.textContent = l.fel_scurt; n.appendChild(e);
    info.appendChild(n);
    var a = document.createElement("div"); a.className = "mic"; a.textContent = l.adresa + (l.utilizator ? " · " + l.utilizator : ""); info.appendChild(a);
    if(l.montat){ var p = document.createElement("div"); p.className = "mic"; p.textContent = l.punct; info.appendChild(p); }
    var s = document.createElement("div"); s.className = "stare " + l.stare; s.textContent = l.stare_text; info.appendChild(s);
    card.appendChild(info);
    var act = document.createElement("div"); act.className = "actiuni";
    act.appendChild(buton("Deschide", "albastru", function(){ rasfoieste(l, ""); }));
    if(l.montabil){
      act.appendChild(buton(l.montat ? "Demontează" : "Montează", "", function(){ fa(l, l.montat ? "demonteaza" : "monteaza"); }));
      act.appendChild(buton("Folosește pt. înregistrări", "verde", function(){ fa(l, "viteza"); }));
    }
    act.appendChild(buton("Editează", "", function(){ editeaza(l); }));
    act.appendChild(buton("Șterge", "rosu", function(){
      if(confirm("Ștergi locul " + l.nume + "? Fișierele de pe server nu se ating.")){ fa(l, "sterge"); }
    }));
    act.querySelectorAll("button").forEach(function(b){ b.disabled = l.stare === "lucreaza"; });
    card.appendChild(act);
    c.appendChild(card);
  });
  $("fara").classList.toggle("ascuns", !!(d.locuri || []).length);
  var cs = d.cautare || {};
  if(cs.in_lucru){ $("cautareStare").textContent = "Se caută serverele din casă..."; lucreaza = true; }
  else if(cs.mesaj){ $("cautareStare").textContent = cs.mesaj; }
  $("cauta").disabled = !!cs.in_lucru;
  var g = $("gasite"); g.textContent = "";
  (cs.gasite || []).forEach(function(x){
    var tr = document.createElement("tr");
    var td = document.createElement("td"); td.textContent = x.nume;
    var m = document.createElement("div"); m.className = "mic"; m.textContent = x.fel_text + " · " + (x.ip || x.gazda); td.appendChild(m);
    var ta = document.createElement("td"); ta.className = "actiune";
    if(x.adaugat){ ta.textContent = "adăugat deja"; }
    else { ta.appendChild(buton("Adaugă", "verde", function(){ dinCautare(x); })); }
    tr.appendChild(td); tr.appendChild(ta); g.appendChild(tr);
  });
  programeaza(lucreaza ? 1000 : 15000);
}
function programeaza(ms){ if(CEAS){ clearTimeout(CEAS); } CEAS = setTimeout(citeste, ms); }
function citeste(){
  return cerere("/api/locuri-retea").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi locurile."; programeaza(10000); return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."; programeaza(10000); });
}
function asteapta(lucrare, gata, pas){
  pas = pas || 0;
  cerere("/api/locuri-retea-lucrare?lucrare=" + encodeURIComponent(lucrare)).then(function(r){
    if(r.result && !r.gata && pas < 240){ setTimeout(function(){ asteapta(lucrare, gata, pas + 1); }, 500); return; }
    gata(r);
  }).catch(function(){ gata({result: false, message: "Receptorul nu răspunde."}); });
}
function fa(l, ce){
  var q = new URLSearchParams(); q.set("id", l.id); q.set("fa", ce);
  mesaj("mesajSus", ce === "viteza" ? "Se verifică scrierea și viteza (până la un minut)..." : "", false);
  cerere("/api/locuri-retea-fa", "POST", q).then(function(d){
    if(!d.result){ mesaj("mesajSus", d.message, true); return; }
    arata(d);
    if(d.lucrare){
      asteapta(d.lucrare, function(r){
        if(r.gata){
          var text = r.mesaj || "";
          if(ce === "viteza" && r.ok){ text += " Acum îl poți alege în Locul înregistrărilor."; }
          if(ce === "sterge" && r.ok){ text = "Locul a fost șters."; }
          mesaj("mesajSus", text, !r.ok);
        }
        citeste();
      });
    }
  });
}
function potriveste(){
  var fel = $("f_fel").value;
  $("d_dosar").classList.toggle("ascuns", fel === "dlna");
  $("d_cont").classList.toggle("ascuns", fel === "dlna" || fel === "nfs");
  $("d_port").classList.toggle("ascuns", fel === "dlna");
  $("d_pornire").classList.toggle("ascuns", fel !== "smb" && fel !== "nfs");
  $("d_citire").classList.toggle("ascuns", fel !== "smb" && fel !== "nfs");
  $("d_tls").classList.toggle("ascuns", fel !== "ftps" && fel !== "webdavs");
  $("alegeDosar").classList.toggle("ascuns", fel !== "smb" && fel !== "nfs");
  $("ajutorFel").textContent = AJUTOR[fel] || "";
}
function goleste(){
  ["f_id", "f_control", "f_nume", "f_gazda", "f_dosar", "f_utilizator", "f_parola"].forEach(function(k){ $(k).value = ""; });
  $("f_port").value = "0"; $("f_pornire").checked = false; $("f_citire").checked = false; $("f_tls").checked = false; $("f_sterge").checked = false;
  $("parolaNota").classList.add("ascuns"); $("d_sterge").classList.add("ascuns"); $("renunta").classList.add("ascuns");
  $("titluFormular").textContent = "Adaugă un loc"; $("f_fel").disabled = false;
  potriveste();
}
function editeaza(l){
  goleste();
  $("f_id").value = l.id; $("f_fel").value = l.fel; $("f_nume").value = l.nume; $("f_gazda").value = l.gazda;
  $("f_dosar").value = l.dosar; $("f_utilizator").value = l.utilizator; $("f_port").value = l.port || 0;
  $("f_pornire").checked = l.pornire; $("f_citire").checked = l.citire; $("f_tls").checked = l.tls_oricare;
  $("parolaNota").classList.toggle("ascuns", !l.are_parola); $("d_sterge").classList.toggle("ascuns", !l.are_parola);
  $("renunta").classList.remove("ascuns");
  $("titluFormular").textContent = "Editează locul " + l.nume;
  potriveste();
  $("formular").scrollIntoView({block: "start"});
}
function dinCautare(x){
  goleste();
  $("f_fel").value = x.fel; $("f_nume").value = x.nume; $("f_gazda").value = x.gazda; $("f_port").value = x.port || 0;
  $("f_control").value = x.control || "";
  potriveste();
  $("formular").scrollIntoView({block: "start"});
  $(x.fel === "smb" ? "f_dosar" : "f_nume").focus();
}
$("f_fel").addEventListener("change", potriveste);
$("renunta").addEventListener("click", function(){ goleste(); mesaj("mesajFormular", "", false); });
$("formular").addEventListener("submit", function(ev){
  ev.preventDefault();
  var q = new URLSearchParams();
  q.set("fel", $("f_fel").value); q.set("nume", $("f_nume").value); q.set("gazda", $("f_gazda").value);
  q.set("dosar", $("f_dosar").value); q.set("utilizator", $("f_utilizator").value); q.set("port", $("f_port").value || "0");
  q.set("control", $("f_control").value);
  if($("f_id").value){ q.set("id", $("f_id").value); }
  if($("f_parola").value){ q.set("parola", $("f_parola").value); }
  if($("f_sterge").checked){ q.set("sterge_parola", "1"); }
  q.set("pornire", $("f_pornire").checked ? "1" : "0"); q.set("citire", $("f_citire").checked ? "1" : "0");
  q.set("tls_oricare", $("f_tls").checked ? "1" : "0");
  $("salveaza").disabled = true;
  cerere("/api/locuri-retea-salveaza", "POST", q).then(function(d){
    $("salveaza").disabled = false;
    $("f_parola").value = "";
    mesaj("mesajFormular", d.message, !d.result);
    if(d.result){ goleste(); }
    if(d.locuri){ arata(d); }
  }).catch(function(){ $("salveaza").disabled = false; mesaj("mesajFormular", "Receptorul nu răspunde.", true); });
});
$("alegeDosar").addEventListener("click", function(){
  var q = new URLSearchParams();
  q.set("fel", $("f_fel").value); q.set("gazda", $("f_gazda").value); q.set("utilizator", $("f_utilizator").value);
  if($("f_id").value){ q.set("id", $("f_id").value); }
  if($("f_parola").value){ q.set("parola", $("f_parola").value); }
  mesaj("mesajFormular", "Se cere lista dosarelor de la server...", false);
  cerere("/api/locuri-retea-dosare", "POST", q).then(function(d){
    if(!d.result){ mesaj("mesajFormular", d.message, true); return; }
    asteapta(d.lucrare, function(r){
      if(!r.gata || !r.ok){ mesaj("mesajFormular", r.mesaj || r.message || "Serverul nu a dat lista dosarelor.", true); return; }
      if(!(r.dosare || []).length){ mesaj("mesajFormular", "Serverul nu a dat niciun dosar.", true); return; }
      var m = $("mesajFormular"); m.textContent = ""; m.classList.remove("eroare", "ascuns");
      r.dosare.forEach(function(x){
        m.appendChild(buton(x, "", function(){ $("f_dosar").value = x.replace(/^\\/+/, ""); if(!$("f_nume").value){ $("f_nume").value = x.replace(/\\/+$/, "").split("/").pop(); } m.textContent = ""; }));
        m.appendChild(document.createTextNode(" "));
      });
    });
  });
});
$("cauta").addEventListener("click", function(){
  $("cauta").disabled = true;
  cerere("/api/locuri-retea-cauta", "POST", new URLSearchParams()).then(function(d){ if(d.locuri){ arata(d); } programeaza(1000); });
});
function rasfoieste(l, cale, drum){
  RASFOIRE = {loc: l, cale: cale, drum: drum || [], lucrare: null};
  $("cardRasfoire").classList.remove("ascuns");
  deseneazaDrum();
  $("rasfoireStare").textContent = "Se citește dosarul...";
  $("intrari").textContent = "";
  var q = new URLSearchParams(); q.set("id", l.id); q.set("cale", cale);
  cerere("/api/locuri-retea-rasfoieste", "POST", q).then(function(d){
    if(!d.result){ $("rasfoireStare").textContent = d.message; return; }
    asteapta(d.lucrare, function(r){
      if(!r.gata || !r.ok){ $("rasfoireStare").textContent = r.mesaj || r.message || "Dosarul nu s-a putut citi."; return; }
      RASFOIRE.lucrare = d.lucrare;
      $("rasfoireStare").textContent = (r.intrari || []).length ? "" : "Dosarul nu are filme, muzică sau alte dosare.";
      var t = $("intrari");
      (r.intrari || []).forEach(function(i, k){
        var tr = document.createElement("tr");
        var td = document.createElement("td"); td.textContent = i.nume;
        var m = document.createElement("div"); m.className = "mic";
        m.textContent = i.dosar ? "Dosar" : [i.durata, i.marime_text].filter(function(x){ return x; }).join(" · ");
        td.appendChild(m);
        var ta = document.createElement("td"); ta.className = "actiune";
        if(i.dosar){ ta.appendChild(buton("Deschide", "", function(){ rasfoieste(l, i.cale, RASFOIRE.drum.concat([{nume: i.nume, cale: i.cale}])); })); }
        else { ta.appendChild(buton("Redă pe televizor", "verde", function(){ reda(k); })); }
        tr.appendChild(td); tr.appendChild(ta); t.appendChild(tr);
      });
    });
  });
}
function deseneazaDrum(){
  var d = $("drum"); d.textContent = "";
  var a = document.createElement("a"); a.textContent = RASFOIRE.loc.nume;
  a.addEventListener("click", function(){ rasfoieste(RASFOIRE.loc, RASFOIRE.loc.fel === "dlna" ? "0" : ""); });
  d.appendChild(a);
  RASFOIRE.drum.forEach(function(p, k){
    d.appendChild(document.createTextNode(" › "));
    var x = document.createElement("a"); x.textContent = p.nume;
    x.addEventListener("click", function(){ rasfoieste(RASFOIRE.loc, p.cale, RASFOIRE.drum.slice(0, k + 1)); });
    d.appendChild(x);
  });
}
function reda(k){
  var q = new URLSearchParams(); q.set("lucrare", RASFOIRE.lucrare); q.set("index", k);
  $("rasfoireStare").textContent = "Se pregătește filmul...";
  cerere("/api/locuri-retea-reda", "POST", q).then(function(d){
    if(!d.result){ $("rasfoireStare").textContent = d.message; return; }
    asteapta(d.lucrare, function(r){ $("rasfoireStare").textContent = r.mesaj || (r.ok ? "" : "Filmul nu a pornit."); });
  });
}
Array.prototype.forEach.call(document.querySelectorAll("a[data-cale]"), function(a){ a.href = adresa(a.getAttribute("data-cale")); });
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Locuri din rețea"),
		N_("Filme, muzică și înregistrări de pe calculatorul cu Windows, NAS, FTP, WebDAV sau serverul media "
			"din casă"),
		N_("Se citesc locurile..."),
		N_("Locurile tale"),
		N_("Niciun loc încă. Adaugă unul mai jos sau caută serverele din casă."),
		N_("Subtitrările de lângă film (același nume, sau dosarul Subs) și cele date de serverul media se iau "
			"singure. Pe televizor, tasta SUB le arată pe toate, cu codarea și întârzierea."),
		N_("Caută în casă"),
		N_("Receptorul întreabă scurt aparatele din rețeaua ta: serverele media (DLNA), calculatoarele cu "
			"Windows și NAS-urile cu dosare partajate, serverele care se anunță (NFS, WebDAV, FTP). Nimic nu "
			"pleacă în afara rețelei tale și nimic nu se caută singur."),
		N_("Caută serverele din casă"),
		N_("Adaugă un loc"),
		N_("Felul locului"),
		N_("Numele (cum apare în listă)"),
		N_("Serverul (nume sau adresă)"),
		N_("Dosarul"),
		N_("Alege din lista serverului"),
		N_("Utilizatorul (gol: fără cont)"),
		N_("Parola"),
		N_("Este salvată o parolă. Lasă câmpul gol ca să rămână aceeași."),
		N_("Portul (0: cel obișnuit)"),
		N_("Montat și după repornire (trebuie pentru înregistrările programate pe el)"),
		N_("Numai citire"),
		N_("Primește un certificat făcut acasă"),
		N_("Șterge parola salvată"),
		N_("Salvează locul"),
		N_("Renunță"),
		N_("Locurile SMB și NFS se montează pe receptor: apar și în Player media, ca un disc, și pot ține "
			"înregistrări după proba de scriere și viteză. Locul înregistrărilor se alege apoi în <a "
			"data-cale=\"/stocare\" href=\"/stocare\" style=\"color:inherit\">Locul înregistrărilor</a>. Parolele stau "
			"criptate pe receptor și nu se arată nicăieri."),
		N_("Același ecran este pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Calculatorul cu Windows sau NAS-ul: scrie numele dosarului partajat (de pildă Filme). Pe Windows, "
			"utilizatorul este contul tău."),
		N_("NAS sau Linux: dosarul exportat (de pildă volume1/filme). Fără parolă."),
		N_("Server FTP: dosarul de pe server (gol: tot serverul)."),
		N_("Ca FTP, cu legătura criptată."),
		N_("WebDAV: dosarul de pe server, de pildă remote.php/dav/files/nume."),
		N_("Ca WebDAV, cu legătura criptată (HTTPS)."),
		N_("Serverul media din casă: îl găsești cel mai ușor cu Caută serverele din casă."),
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Deschide"),
		N_("Demontează"),
		N_("Montează"),
		N_("Folosește pt. înregistrări"),
		N_("Editează"),
		N_("Șterge"),
		N_("Ștergi locul"),
		N_("? Fișierele de pe server nu se ating."),
		N_("Se caută serverele din casă..."),
		N_("adăugat deja"),
		N_("Adaugă"),
		N_("Receptorul nu a putut citi locurile."),
		N_("Receptorul nu răspunde. Verifică dacă este pornit și în aceeași rețea."),
		N_("Receptorul nu răspunde."),
		N_("Se verifică scrierea și viteza (până la un minut)..."),
		N_("Acum îl poți alege în Locul înregistrărilor."),
		N_("Locul a fost șters."),
		N_("Adaugă un loc"),
		N_("Editează locul"),
		N_("Se cere lista dosarelor de la server..."),
		N_("Serverul nu a dat lista dosarelor."),
		N_("Serverul nu a dat niciun dosar."),
		N_("Se citește dosarul..."),
		N_("Dosarul nu s-a putut citi."),
		N_("Dosarul nu are filme, muzică sau alte dosare."),
		N_("Dosar"),
		N_("Redă pe televizor"),
		N_("Se pregătește filmul..."),
		N_("Filmul nu a pornit."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor

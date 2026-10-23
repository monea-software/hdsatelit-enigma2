# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# acces_conditionat_web.py: „Acces condiționat” in interfata web (HdsWebControl), perechea ecranelor „Module de acces
# condiționat” (Screens/CamSetup.py) si „Informații despre decriptare” (Screens/CamInfo.py) din meniul Acces condiționat.
#
# Modulele instalate (scripturile /etc/init.d/<fel>.<x>: intai modulele obisnuite, apoi serverele de carduri), care e
# ales la pornirea receptorului, care ruleaza, procesul care lucreaza si memoria lui; alegerea, pornirea, oprirea si
# repornirea. O SINGURA LOGICA: citirea si comenzile sunt Components/HdsModuleAcces.py (Operatie: pas cu pas, o
# singura comanda deodata pentru televizor si web, numai scripturile modulelor, fara interpretor de comenzi); procesul
# aratat si textele rezultatelor sunt cele ale ecranului (CamSetup.pid_de_aratat, text_rezultat, text_pas).
# Randurile din /tmp/ecm.info nu ajung in pagina (pot avea numele si adresele cititoarelor): pagina spune numai daca
# receptorul decripteaza acum si deschide pe televizor ecranul cu toate detaliile. Pagina nu trece spre modul (fara
# proxy): interfetele web ale modulelor sunt pe /interfete-cam.
# 0.2.8 (perechea butonului Albastru din ecranul de pe televizor): „Deschide pe televizor” pe
# cardul „Pagina web a modulului” deschide interfata web a modulului care ruleaza PE TELEVIZOR, in navigatorul imaginii,
# prin ruta navigatorului (POST /api/navigator-cam, navigator_web.py, aceeasi poarta si acelasi CSRF). Pagina nu afla si
# nu primeste adresa, utilizatorul sau parola interfetei. Textele noi ale cardului se traduc (TEXTE_CAM, 13 limbi);
# restul paginii e scris in romana, ca pana acum.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/acces-conditionat            modulele pe feluri, cine e ales, cine ruleaza, comanda in curs / ultima
#   POST /api/acces-conditionat-comanda?cerere=alege|porneste|opreste|reporneste&fel=<fel>[&sufix=<x>]
#                                          porneste comanda si raspunde pe loc; rezultatul vine apoi prin GET; <fel> e
#                                          numele felului asa cum il da GET (campul "fel"), citit de pe receptor
#   GET  /acces-conditionat                pagina
# „Deschide pe televizor” foloseste ruta meniului: POST /api/meniu-televizor?id=cam_setup|cam_info (meniu_web.py).
# Rutele nu s-au schimbat la trecerea pe nume neutre; numai valoarea lui fel vine acum de pe receptor (aceeasi ca
# inainte pe acelasi receptor), deci paginile si aplicatiile care o iau din GET merg mai departe fara redirectare.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Citirea e cea a ecranului (cateva fisiere mici din
# /etc/init.d si /proc, HdsModuleAcces.citeste); scripturile ruleaza in eConsoleAppContainer, fara sa fie asteptate.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul H (Components.HdsModuleAcces) si
# ecranul E (Screens.CamSetup).
import re
import time

ARGUMENTE = ("cerere", "fel", "sufix")
MAX_VALOARE = 64
# acelasi tipar ca HdsModuleAcces._SUFIX_BUN (Operatie il verifica din nou pe lista citita chiar atunci)
_SUFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


# numele felurilor, ca in meniul de pe televizor: primul fel aratat (al modulelor obisnuite, acelasi msgid ca titlul
# ecranului) si celelalte (serverele de carduri)
ETICHETA_PRINCIPAL = N_("Module de acces condiționat")
ETICHETA_ALTE = N_("Servere de carduri")

# comanda pornita din web: pasul de acum si ultimul rezultat (al oricarei comenzi pornite de aici)
_STARE = {"pas": None, "ultima": None}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsModuleAcces
	return HdsModuleAcces


def _ecran(E=None):
	if E is not None:
		return E
	from Screens import CamSetup
	return CamSetup


def _jurnal(text):
	print("[HdsWebControl] acces conditionat: %s" % text)


def _memorie(H, sistem, pid):
	"""{"kb": VmRSS, "fire": Threads} din /proc/<pid>/status (HdsModuleAcces.memorie), fara valorile care lipsesc"""
	rez = {}
	for r in H.memorie(sistem, pid):
		parti = r.split()
		if len(parti) > 1 and parti[1].isdigit():
			if parti[0] == "VmRSS:":
				rez["kb"] = int(parti[1])
			elif parti[0] == "Threads:":
				rez["fire"] = int(parti[1])
	return rez


def _modul(H, E, sistem, e):
	m = {"sufix": e.sufix, "descriere": e.descriere or "", "ales": bool(e.ales), "ruleaza": bool(e.pids)}
	if e.pids:
		pid = E.pid_de_aratat(sistem, e.pids)
		m["pid"] = pid
		m["procese"] = len(e.pids)
		m["memorie"] = _memorie(H, sistem, pid) if pid is not None else {}
	return m


def _comanda(H):
	o = H.in_curs()
	if o is not None:
		pas = _STARE["pas"] if _STARE["pas"] and _STARE["pas"].get("operatie") == id(o) else None
		return {"in_curs": True, "text": pas["text"] if pas else _t("Așteaptă să se termine comanda de acum.")}
	return {"in_curs": False, "ultima": _STARE["ultima"]}


def stare(H=None, E=None):
	"""Pentru GET /api/acces-conditionat."""
	H = _h(H)
	E = _ecran(E)
	sistem = H.SistemAcces()
	feluri = []
	decripteaza = False
	for i, st in enumerate(H.feluri_de_aratat(sistem)):
		feluri.append({
			"fel": st.fel,
			"eticheta": _t(ETICHETA_PRINCIPAL if i == 0 else ETICHETA_ALTE),
			"niciunul_ales": st.ales_emulator() is None,
			"legatura": st.legatura,
			"module": [_modul(H, E, sistem, e) for e in st.emulatoare],
			"fara_script": list(st.fara_script),
		})
		decripteaza = decripteaza or bool(st.ecm)
	return {"result": True, "feluri": feluri, "sufix_gol": H.SUFIX_GOL, "decripteaza_acum": decripteaza,
		"comanda": _comanda(H)}


def _cuMesaj(rez, reusit, mesaj):
	rez = dict(rez)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


def comanda(argumente, H=None, E=None, ceas=None):
	"""POST /api/acces-conditionat-comanda. Verifica cererea, porneste HdsModuleAcces.Operatie si raspunde pe loc;
	pasii si rezultatul (text_pas, text_rezultat) se tin aici pentru GET. Refuza cand ruleaza deja o comanda (de pe
	televizor sau din web). Felul trebuie sa fie unul de pe receptor (HdsModuleAcces.feluri); fara fel, primul."""
	H = _h(H)
	E = _ecran(E)
	ceas = ceas or time.time
	cerere = argumente.get("cerere") or ""
	feluri_receptor = H.feluri(H.SistemAcces())
	fel = argumente.get("fel") or (feluri_receptor[0] if feluri_receptor else "")
	sufix = argumente.get("sufix") or None
	if cerere not in H.CERERI:
		return _cuMesaj(stare(H, E), False, _t("Comanda „%s” nu există.") % cerere[:MAX_VALOARE])
	if fel not in feluri_receptor or (sufix is not None and not _SUFIX.match(sufix)):
		return _cuMesaj(stare(H, E), False, _t("Modulul ales nu există."))
	if cerere == "alege" and sufix is None:
		return _cuMesaj(stare(H, E), False, _t("Modulul ales nu există."))
	if H.in_curs() is not None:
		return _cuMesaj(stare(H, E), False, _t("Așteaptă să se termine comanda de acum."))
	gata = []
	operatie = [None]

	def laPas(actiune, nume):
		_STARE["pas"] = {"operatie": id(operatie[0]), "text": E.text_pas(actiune, nume)}

	def laFinal(r):
		_STARE["pas"] = None
		_STARE["ultima"] = {"ok": bool(r.get("ok")), "motiv": r.get("motiv") or "", "text": E.text_rezultat(r),
			"cand": int(ceas())}
		_jurnal("%s %s %s: %s" % (cerere, fel, sufix or "-", r.get("motiv")))
		gata.append(r)

	o = H.Operatie(cerere, fel=fel, sufix=sufix, la_pas=laPas, la_final=laFinal)
	operatie[0] = o
	_STARE["pas"] = None
	if not o.porneste() or gata:
		# terminata pe loc (nimic de facut, necunoscut, ocupat) sau fara niciun script de asteptat
		r = gata[0] if gata else (o.rezultat or {})
		return _cuMesaj(stare(H, E), bool(r.get("ok")), E.text_rezultat(r) if r else _t("Comanda nu a pornit."))
	pas = _STARE["pas"]
	return _cuMesaj(stare(H, E), True, pas["text"] if pas else _t("Comanda a pornit."))


def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, numai cheile stiute, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:16]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in ARGUMENTE:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_VALOARE].strip()
	return rez


def rute(baza, resource, H=None, E=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/acces-conditionat: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(H, E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ComandaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, comanda(argumente(request), H, E))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /acces-conditionat: pagina „Acces condiționat”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"acces-conditionat": StareResource(),
		b"acces-conditionat-comanda": ComandaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /ceas, /limbi, /video si /sunet."""
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


# textele cardului „Pagina web a modulului” (0.2.8), traduse la afisare
TEXTE_CAM = {
	"__T_CAM_NOTA__": N_("Pagina web a modulului care rulează se deschide pe televizor, neschimbată, cu toate comenzile ei. Dacă cere utilizator și parolă, receptorul le dă singur, din setările modulului; dacă nu le găsește, le scrii cu telecomanda."),
	"__T_CAM_TV__": N_("Deschide pe televizor"),
	"__T_CAM_FARA__": N_("Niciun modul nu rulează acum, deci nu e nicio pagină web de deschis."),
	"__T_CAM_TELEFON__": N_("Din telefon sau calculator, pagina se deschide din lista interfețelor web:"),
}


def pagina_text(stil, config_pagina):
	import html
	text = _traducePagina(PAGINA)
	for cheie, sablon in TEXTE_CAM.items():
		text = text.replace(cheie, html.escape(_t(sablon), quote=False))
	return text.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina).replace("__DRUM_MENIU__",
		_drumMeniu("cam_setup"))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acces condiționat</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 8px;color:var(--text-slab);font-weight:normal;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .modul{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 12px;padding:12px 0;border-top:1px solid var(--bordura);}
  .modul:first-of-type{border-top:0;padding-top:4px;}
  .modul .stanga{min-width:0;flex:1 1 260px;}
  .modul .nume{font-size:1rem;overflow-wrap:anywhere;}
  .modul .detaliu{color:var(--text-slab);font-size:.875rem;margin-top:3px;overflow-wrap:anywhere;line-height:1.4;}
  .semn{display:inline-block;font-size:.8rem;border-radius:999px;padding:3px 10px;margin-left:6px;white-space:nowrap;background:#242a33;color:var(--text-slab);vertical-align:middle;}
  .semn.pornit{background:var(--verde);color:#fff;}
  .semn.ales{background:#2d3b66;color:#dfe6ff;}
  .butoane{display:flex;gap:8px;flex-wrap:wrap;}
  button{min-height:44px;padding:10px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  button.verde{background:var(--verde);border-color:var(--verde);color:#fff;}
  button:disabled{opacity:.5;cursor:default;}
  .acum{font-size:1.02rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.875rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  .legaturi{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:.9rem;}
  .legaturi a{color:var(--text);}
  @media (max-width:560px){ .butoane button{flex:1 1 auto;} }
</style>
</head>
<body>
<main>
<h1>Acces condiționat</h1>
<p class="mesaj" id="incarcare">Se citesc modulele de pe receptor...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Acum</h2>
    <p class="acum" id="decriptare"></p>
    <p class="nota" id="comanda"></p>
  </section>
  <div id="feluri"></div>
  <section class="card">
    <h2>Pe televizor</h2>
    <div class="butoane">
      <button type="button" data-televizor="cam_setup">Deschide pe televizor: Module de acces condiționat</button>
      <button type="button" data-televizor="cam_info">Deschide pe televizor: Informații despre decriptare</button>
    </div>
    <p class="nota">Ce decriptează acum modulul (canalul, timpul de răspuns) se vede pe televizor, în Informații despre decriptare.</p>
  </section>
  <section class="card">
    <h2>Pagina web a modulului</h2>
    <p class="nota">Unele module au o pagină web proprie (setările, cititoarele, liniile).</p>
    <p class="nota">__T_CAM_NOTA__</p>
    <div class="butoane"><button type="button" id="camTv">__T_CAM_TV__</button></div>
    <p class="nota ascuns" id="camFara">__T_CAM_FARA__</p>
    <p class="nota">__T_CAM_TELEFON__</p>
    <div class="legaturi"><a id="interfete" href="/interfete-cam">Interfețele web ale modulelor</a></div>
  </section>
  <p class="nota">Aceleași comenzi sunt pe televizor, în __DRUM_MENIU__.</p>
  <p class="mesaj" id="mesaj"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var D = null;
var ocupat = false;
var astept = false;     // o comanda trimisa de aici merge inca: la sfarsit, rezultatul ei ia locul mesajului
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
$("interfete").href = adresa("/interfete-cam");
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
function el(tip, clasa, text){
  var e = document.createElement(tip);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = String(text); }
  return e;
}
function mb(kb){ return (kb / 1024).toFixed(1).replace(".", ",") + " MB"; }
function detaliiProces(m){
  if(!m.ruleaza){ return "Nu rulează."; }
  var t = "Rulează, procesul " + m.pid;
  var mem = m.memorie || {};
  if(mem.kb !== undefined){ t += ", memorie " + mb(mem.kb); }
  if(mem.fire !== undefined){ t += ", " + mem.fire + (mem.fire === 1 ? " fir" : (mem.fire < 20 ? " fire" : " de fire")); }
  if(m.procese > 1){ t += " (" + m.procese + " procese)"; }
  return t + ".";
}
function buton(text, clasa, fel, cerereNume, sufix, intrebare){
  var b = el("button", clasa || "", text);
  b.type = "button";
  b.addEventListener("click", function(){
    if(intrebare && !window.confirm(intrebare)){ return; }
    trimite(cerereNume, fel, sufix);
  });
  return b;
}
function randModul(f, m){
  var rand = el("div", "modul");
  var stanga = el("div", "stanga");
  var nume = el("div", "nume", m.sufix);
  if(m.ales){ nume.appendChild(el("span", "semn ales", "ales")); }
  nume.appendChild(el("span", "semn" + (m.ruleaza ? " pornit" : ""), m.ruleaza ? "rulează" : "oprit"));
  stanga.appendChild(nume);
  if(m.descriere){ stanga.appendChild(el("div", "detaliu", m.descriere)); }
  stanga.appendChild(el("div", "detaliu", detaliiProces(m) + (m.ales ? " Pornește la fiecare pornire a receptorului." : "")));
  rand.appendChild(stanga);
  var b = el("div", "butoane");
  if(!m.ales){
    b.appendChild(buton("Alege", "verde", f.fel, "alege", m.sufix,
      "Se alege " + m.sufix + ": modulul de acum se oprește, iar " + m.sufix + " pornește acum și la fiecare pornire a receptorului. Continui?"));
  } else if(!m.ruleaza){
    b.appendChild(buton("Pornește", "verde", f.fel, "porneste", m.sufix));
  }
  if(m.ruleaza){
    b.appendChild(buton("Oprește", "", f.fel, "opreste", m.sufix,
      "Se oprește " + m.sufix + ": canalele criptate nu se mai văd până îl pornești din nou. Continui?"));
  }
  if(m.ales || m.ruleaza){
    b.appendChild(buton("Repornește", "", f.fel, "reporneste", m.sufix));
  }
  rand.appendChild(b);
  return rand;
}
function randNiciunul(f){
  var rand = el("div", "modul");
  var stanga = el("div", "stanga");
  var nume = el("div", "nume", "Niciunul");
  if(f.niciunul_ales){ nume.appendChild(el("span", "semn ales", "ales")); }
  stanga.appendChild(nume);
  stanga.appendChild(el("div", "detaliu", "La pornirea receptorului nu pornește niciun modul."));
  rand.appendChild(stanga);
  if(!f.niciunul_ales){
    var b = el("div", "butoane");
    b.appendChild(buton("Alege", "", f.fel, "alege", D.sufix_gol,
      "La pornirea receptorului nu va mai porni niciun modul, iar cel de acum se oprește. Continui?"));
    rand.appendChild(b);
  }
  return rand;
}
function arata(d){
  D = d;
  $("decriptare").textContent = d.decripteaza_acum
    ? "Receptorul decriptează acum un canal."
    : "Receptorul nu decriptează acum niciun canal (canalul de acum nu este criptat sau niciun modul nu îl decriptează).";
  var c = d.comanda || {};
  ocupat = !!c.in_curs;
  if(c.in_curs){ $("comanda").textContent = c.text || ""; }
  else if(c.ultima){ $("comanda").textContent = "Ultima comandă din pagină: " + c.ultima.text; }
  else { $("comanda").textContent = ""; }
  if(astept && !c.in_curs){
    astept = false;
    if(c.ultima){ mesaj(c.ultima.text, !c.ultima.ok); }
  }
  var loc = $("feluri"); loc.textContent = "";
  (d.feluri || []).forEach(function(f){
    var card = el("section", "card");
    card.appendChild(el("h2", "", f.eticheta));
    if(!f.module.length){
      card.appendChild(el("p", "nota", "Nu este instalat niciun modul de acces condiționat. După ce se instalează pachetul unui modul, acesta apare aici."));
    } else {
      card.appendChild(randNiciunul(f));
      f.module.forEach(function(m){ card.appendChild(randModul(f, m)); });
    }
    if(f.fara_script && f.fara_script.length){
      card.appendChild(el("p", "nota", "Programe fără script de pornire, care nu se pot porni de aici: " + f.fara_script.join(", ")));
    }
    loc.appendChild(card);
  });
  Array.prototype.forEach.call(document.querySelectorAll("#feluri button"), function(b){ b.disabled = ocupat; });
  // pagina web a modulului pe televizor: numai cand ruleaza un modul
  var ruleaza = (d.feluri || []).some(function(f){ return (f.module || []).some(function(m){ return m.ruleaza; }); });
  $("camTv").disabled = !ruleaza;
  $("camFara").classList.toggle("ascuns", ruleaza);
}
$("camTv").addEventListener("click", function(){
  mesaj("Se deschide pe televizor...");
  cerere("/api/navigator-cam", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
});
function citeste(){
  return cerere("/api/acces-conditionat").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi modulele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cerereNume, fel, sufix){
  var q = new URLSearchParams();
  q.set("cerere", cerereNume); q.set("fel", fel);
  if(sufix){ q.set("sufix", sufix); }
  mesaj("Se trimite...");
  cerere("/api/acces-conditionat-comanda", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    astept = !!(d.result && d.comanda && d.comanda.in_curs);
    if(d.feluri){ arata(d); }
    if(ocupat){ setTimeout(citeste, 1500); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
Array.prototype.forEach.call(document.querySelectorAll("[data-televizor]"), function(b){
  b.addEventListener("click", function(){
    var q = new URLSearchParams(); q.set("id", b.getAttribute("data-televizor"));
    mesaj("Se deschide pe televizor...");
    cerere("/api/meniu-televizor", "POST", q).then(function(d){ mesaj(d.message, !d.result); })
      .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
  });
});
function bucla(){
  var pas = ocupat ? 1500 : 5000;
  (document.hidden ? Promise.resolve() : citeste()).then(function(){ setTimeout(bucla, ocupat ? 1500 : pas); });
}
bucla();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Acces condiționat"),
		N_("Se citesc modulele de pe receptor..."),
		N_("Acum"),
		N_("Pe televizor"),
		N_("Deschide pe televizor: Module de acces condiționat"),
		N_("Deschide pe televizor: Informații despre decriptare"),
		N_("Ce decriptează acum modulul (canalul, timpul de răspuns) se vede pe televizor, în Informații "
			"despre decriptare."),
		N_("Pagina web a modulului"),
		N_("Unele module au o pagină web proprie (setările, cititoarele, liniile)."),
		N_("Interfețele web ale modulelor"),
		N_("Aceleași comenzi sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nu rulează."),
		N_("Rulează, procesul"),
		N_(", memorie"),
		N_("fir"),
		N_("fire"),
		N_("de fire"),
		N_("rulează"),
		N_("Pornește la fiecare pornire a receptorului."),
		N_("Alege"),
		N_("Se alege"),
		N_(": modulul de acum se oprește, iar"),
		N_("pornește acum și la fiecare pornire a receptorului. Continui?"),
		N_("Pornește"),
		N_("Oprește"),
		N_("Se oprește"),
		N_(": canalele criptate nu se mai văd până îl pornești din nou. Continui?"),
		N_("Repornește"),
		N_("Niciunul"),
		N_("La pornirea receptorului nu pornește niciun modul."),
		N_("La pornirea receptorului nu va mai porni niciun modul, iar cel de acum se oprește. Continui?"),
		N_("Receptorul decriptează acum un canal."),
		N_("Receptorul nu decriptează acum niciun canal (canalul de acum nu este criptat sau niciun modul "
			"nu îl decriptează)."),
		N_("Ultima comandă din pagină:"),
		N_("Nu este instalat niciun modul de acces condiționat. După ce se instalează pachetul unui modul, "
			"acesta apare aici."),
		N_("Programe fără script de pornire, care nu se pot porni de aici:"),
		N_("Se deschide pe televizor..."),
		N_("Receptorul nu răspunde."),
		N_("Receptorul nu a putut citi modulele."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
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

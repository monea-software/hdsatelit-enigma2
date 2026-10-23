# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# procesor_web.py: „Procesor” in interfata web (HdsWebControl).
#
# Pereche web a ecranului de pe televizor Meniu > Sistem & Dispozitive > Procesor (Screens/HdsProcesor.py), din
# aceeasi logica (Components/HdsProcesor.py): modul de lucru (aceeasi functie seteazaMod, salvat si aplicat pe loc),
# frecventa setata (plafonul; modul e in lista de deasupra) si cea de acum, temperatura, tensiunea, procentul folosit,
# timpul pe fiecare treapta, motivul pentru care plafonul e mai jos (galben; cateva minute dupa revenire, verde, ca
# receptorul s-a racit: citire.racit), pragul pazei driverului si, fara semnul probei de caldura, cand apare modul
# Performanta. Pe un receptor fara cpufreq pagina spune ca frecventa nu se poate citi sau schimba, iar legatura spre
# /procesor nu apare in panou si in /ecrane (faraLegaturaDacaLipseste, chemata din plugin.py), ca intrarea din meniu
# (requires="HdsProcesor"). Cand receptorul nu mai raspunde dupa ce pagina s-a incarcat, mesajul se vede sub modul de
# lucru si citirile raman pe gri pana la urmatoarea citire buna.
#
# Graficul temperaturii, ca pe televizor: /api/procesor da in „grafic” punctele ultimei ore din istoricul pazei
# (HdsProcesor.istoricGrafic: cea mai mare temperatura din minut, frecventa, caldura, modul), orele, textele traduse si,
# pentru fiecare alegere („60”, „30”), scara, bucatile de timp ale modurilor cu pragurile lor si liniile care ajung in
# dreapta, exact ca pe televizor; scriptul face SVG-ul la latimea paginii (si din nou la redimensionare), cu alegerea
# „Ultima oră” / „Ultimele 30 de minute” (doua butoane, alegerea ramane in pagina). Valorile liniilor stau intr-o
# coloana in dreapta, in afara datelor. Fara paza pornita (fara cpufreq) cardul graficului nu apare.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; ce schimba
# ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/procesor                                           modul, modurile, citirile
#   POST /api/procesor-seteaza?mod=automat|racoros|normal|performanta   salveaza si aplica pe loc
#   GET  /procesor                                               pagina (se improspateaza la 2 s numai cat fila se vede)
#
# Modurile din lista sunt exact alegerile setarii de pe televizor (HdsProcesor.moduri dupa initConfig), deci modul
# salvat e mereu printre ele. Etichetele paginii si mesajele din script trec prin _t() (ETICHETE, TEXTE_JS), iar
# lang e limba receptorului. Timpul pe fiecare treapta: procentul si durata, ca pe televizor (HdsProcesor.textTreapta).
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2; o citire (cativa ms pe receptor) se face cel mult o data
# pe secunda (HdsProcesor.citire). Fisierul nu importa nimic la incarcare: probele de pe PC dau modulul lor (M).


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


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsProcesor
	return HdsProcesor


def _modAles(M, d):
	"""Modul salvat in setari (ce arata si televizorul), sau cel din paza daca setarea lipseste."""
	try:
		M.initConfig()
		from Components.config import config
		return config.hds_procesor.mod.value
	except Exception:
		return d.get("mod") or "normal"


def _mhz(khz):
	return int(khz) // 1000 if khz else None


def _legat(text):
	"""Numarul si unitatea de dupa el („85 °C”, „400 MHz”, „1 min”) raman pe acelasi rand in pagina, si pe telefon:
	spatiul dintre ele devine spatiu fara rupere."""
	import re
	return re.sub(u"(\\d) (?=[^\\s\\d.,;:()])", u"\\1\u00a0", text or "")


def _scara(g):
	"""Ce difera intre alegeri: scara, bucatile modurilor (cu pragurile lor) si liniile din dreapta."""
	return {
		"jos": g["jos"],
		"sus": g["sus"],
		"praguri": [{"t": t, "nume": nume, "fel": fel} for t, nume, fel in g["praguri"]],
		"segmente": [{"mod": s["mod"], "nume": s["nume"], "de_la": s["de_la"], "pana_la": s["pana_la"],
			"praguri": [{"t": t, "fel": fel} for t, fel in s["praguri"]]} for s in g.get("segmente") or ()],
	}


def grafic(M):
	"""Graficul pentru pagina, sau None cand paza nu merge. Punctele ultimei ore (alegerea de 30 de minute le ia pe
	cele din fereastra ei) si, pentru fiecare alegere, scara si liniile calculate ca pe televizor (istoricGrafic(60) si
	istoricGrafic(30)): aceeasi alegere arata la fel pe televizor si in web. Numai date simple si texte traduse; SVG-ul
	il face scriptul la latimea paginii."""
	try:
		if not M.procesor().pornit:
			return None
		g = M.istoricGrafic(60)
		g30 = M.istoricGrafic(30)
		rez = {
			"puncte": g["puncte"],
			"fsus": g["fsus"],
			"ore": [{"in_urma": u, "text": text, "zece": bool(zece)} for u, text, zece in g["ore"]],
			"inceput_in_urma": g["inceput_in_urma"],
			"zone": {"galben": M.TEMP_GALBEN, "rosu": M.PAZA_COBORARE},
			"alegeri": {"60": _scara(g), "30": _scara(g30)},
			"texte": {
				"titlu": {"60": M.titluGrafic(60), "30": M.titluGrafic(30)},
				"alegeri": {"60": M.numeGrafic(60), "30": M.numeGrafic(30)},
				"legenda": M.textLegendaGrafic(),
				"memorie": M.textIstoricMemorie(),
				"istoric": {"60": _legat(M.textIstoric(g)), "30": _legat(M.textIstoric(g30))},
			},
		}
		rez.update(rez["alegeri"]["60"])        # jos, sus, praguri, segmente ale orei (si pentru scripturi)
		return rez
	except Exception as eroare:
		print("[procesor_web] graficul: %r" % (eroare,))
		return None


def stare(M=None):
	"""Pentru GET /api/procesor."""
	M = _m(M)
	d = M.citire(1.0)
	t = d.get("temperatura")
	mod = _modAles(M, d)
	toate = M.moduri()
	moduri = [m for m in toate if m.get("disponibil")]
	if mod not in [m["id"] for m in moduri]:
		# nu se intampla cu setarea facuta (modul salvat e o alegere a ei); fara ea, lista nu ramane fara modul ales
		moduri += [dict(m, disponibil=False) for m in toate if m["id"] == mod]
	moduri = [dict(m, descriere=_legat(m.get("descriere")), detaliu=_legat(m.get("detaliu"))) for m in moduri]
	return {
		"result": True,
		"disponibil": bool(d.get("disponibil")),
		"mod": mod,
		"moduri": moduri,
		"citire": {
			"plafon_mhz": _mhz(d.get("plafon_khz")),
			"plafon_mod_mhz": _mhz(d.get("plafon_mod_khz")),
			"frecventa_mhz": _mhz(d.get("frecventa_khz")),
			"temperatura": t,
			"temperatura_culoare": M.temperaturaCuloare(t),
			"tensiune_mv": d.get("tensiune_mv"),
			"folosit_procent": d.get("folosit_procent"),
			"stare_driver": d.get("stare_driver"),
			"motiv": d.get("motiv") or "",
			"racire": bool(d.get("racire")),
			"racit": bool(M.racitCitire(d)),
			"trepte": [{"mhz": _mhz(k), "secunde": int(s), "procent": procent, "durata": M.textDurata(s),
				"text": M.textTreapta(procent, s)} for k, procent, s in M.trepteProcent(d)],
		},
		"texte": {
			# numai plafonul, ca pe televizor: modul e in lista de deasupra
			"setata": M.textFrecventaSetataScurt(d) if d.get("disponibil") else M.textFrecventa(None),
			"acum": M.textFrecventa(d.get("frecventa_khz")),
			"temperatura": M.textTemperatura(t),
			"tensiune": M.textTensiune(d.get("tensiune_mv")),
			"motiv": _legat(M.textMotivCitire(d)),
			"paza_driver": M.textPazaDriver(d.get("paza_driver")),
			"performanta_ascunsa": _legat(M.textPerformantaAscunsa()) if d.get("disponibil") else "",
			"indisponibil": "" if d.get("disponibil") else M.textIndisponibil(),
		},
		"grafic": grafic(M) if d.get("disponibil") else None,
	}


def seteaza(argumente, M=None):
	"""POST /api/procesor-seteaza?mod=...: aceeasi functie ca OK pe televizor; o valoare straina nu schimba nimic."""
	M = _m(M)
	mod = argumente.get("mod")
	if mod not in M.MODURI:
		rez = stare(M)
		# mesaj tehnic pentru scripturi (ca in accel_web si paznic_web), netradus
		rez.update({"result": False, "message": _t("Se alege cu mod=automat, racoros, normal sau performanta.")})
		return rez
	reusit, mesaj = M.seteazaMod(mod)
	rez = stare(M)
	rez.update({"result": bool(reusit), "message": mesaj})
	return rez


LEGATURA = '<a href="/procesor">Procesor</a>'


def faraLegaturaDacaLipseste(pagina, M=None):
	"""Panoul si /ecrane: legatura spre /procesor ramane numai pe un receptor cu cpufreq (meniul si web-ul arata doar
	ce exista pe receptor); aceeasi hotarare ca intrarea din menu.xml (requires="HdsProcesor")."""
	try:
		if _m(M).disponibil():
			return pagina
	except Exception as eroare:
		print("[procesor_web] disponibil: %s" % eroare)
	# dupa adresa, nu dupa text: pagina e tradusa in limba receptorului
	import re
	legatura = r'<a href="%s">[^<]*</a>' % re.escape(re.search(r'href="([^"]+)"', LEGATURA).group(1))
	return re.sub(legatura, "", re.sub("  " + legatura + "\n", "", pagina))


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
		rez[cheie] = str(v)[:20].strip()
	return rez


def rute(baza, resource, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/procesor: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), M))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class PaginaResource(resource.Resource):
		"""GET /procesor: pagina „Procesor”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"procesor": StareResource(),
		b"procesor-seteaza": SeteazaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic si /accel."""
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


def _limba():
	"""Limba receptorului pentru lang (de ex. „de” din „de_DE”); „ro” fara limba citibila (probele de pe PC)."""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


# etichetele fixe ale paginii: __T_<CHEIE>__ in PAGINA, traduse si scapate pentru HTML
ETICHETE = {
	"TITLU": N_("Procesor"),
	"INCARCARE": N_("Se citește starea..."),
	"MOD": N_("Modul de lucru"),
	"SETATA": N_("Frecvența setată"),
	"ACUM": N_("Frecvența de acum"),
	"TEMPERATURA": N_("Temperatura"),
	"TENSIUNEA": N_("Tensiunea"),
	"FOLOSIT": N_("Procesor folosit"),
	"TREPTE": N_("Timp pe fiecare treaptă (de la pornire)"),
	"GRAFIC": N_("Graficul"),
}

# nota de sub citiri: %s e drumul din meniul televizorului (HTML facut de meniu_web.drumHtml)
NOTA_MOD = N_("Modul se salvează și se aplică pe loc. Aceeași setare este pe televizor, în %s.")

# mesajele scriptului, traduse pe receptor si date paginii ca JSON (TXT)
TEXTE_JS = {
	"neasteptat": N_("Receptorul a răspuns neașteptat (HTTP %s)."),
	"necitit": N_("Receptorul nu a putut citi starea."),
	"nu_raspunde_retea": N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
	"nu_raspunde": N_("Receptorul nu răspunde."),
	"se_salveaza": N_("Se salvează..."),
	"nu_se_poate_citi": N_("nu se poate citi"),
}


def _json(obiect):
	"""JSON pentru interiorul lui <script>: fara „</” (nu poate inchide scriptul)."""
	import json
	return json.dumps(obiect, ensure_ascii=False).replace("</", "<\\/")


def pagina_text(stil, config_pagina):
	"""Pagina cu etichetele traduse si scapate pentru HTML; quote=True, pentru ca unele stau in atribute
	(aria-label)."""
	import html
	text = _traducePagina(PAGINA)
	for cheie, eticheta in ETICHETE.items():
		text = text.replace("__T_%s__" % cheie, html.escape(_t(eticheta), quote=True))
	nota = html.escape(_t(NOTA_MOD), quote=True)
	nota = nota.replace("%s", _drumMeniu("hds_procesor"), 1) if "%s" in nota else nota
	return (text.replace("__LIMBA__", _limba()).replace("__NOTA_MOD__", nota)
		.replace("__TEXTE_JS__", _json(dict((k, _t(v)) for k, v in TEXTE_JS.items())))
		.replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina))


PAGINA = """<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_TITLU__</title>
<style>__STIL_COMUN__
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 14px;}
  h2{font-size:1rem;margin:0 0 10px;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,260px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand label{font-size:.98rem;}
  .rand select{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .val{display:grid;grid-template-columns:minmax(120px,1fr) 1.4fr;gap:6px 12px;margin:0;}
  .val dt{color:var(--text-slab);}
  .val dd{margin:0;}
  .galben{color:#ffd24d;}
  .rosu{color:#ff7a6b;}
  .treapta{display:grid;grid-template-columns:72px minmax(40px,1fr) 11em;gap:10px;align-items:center;margin:6px 0;font-size:.92rem;}
  .treapta .mhz{text-align:right;}
  .bara{height:12px;border:1px solid var(--bordura);border-radius:6px;overflow:hidden;background:#0f1216;}
  .bara span{display:block;height:100%;background:#3d8fd6;}
  .descriere{margin:8px 0 0;line-height:1.45;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .nota:empty{display:none;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  #mesaj:empty{display:none;}
  #indisponibil{margin:10px 0 12px;}
  .motiv{color:#ffd24d;margin:8px 0 0;line-height:1.45;}
  .motiv.bine{color:#6fd49a;}
  .eroare{color:#ffb4a8;}
  #continut.vechi .card:not(#alegere){opacity:.55;}
  .alegeri{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 8px;}
  .alegeri button{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;cursor:pointer;}
  .alegeri button.ales{background:#374ea1;border-color:#9fb4ff;}
  .grafic{width:100%;margin:4px 0 0;}
  .grafic svg{display:block;width:100%;height:auto;}
  .g-grila{stroke:#2a3350;stroke-width:1;}
  .g-inceput{stroke:#667085;stroke-width:2;}
  .g-schimbare{stroke:#aeb9cc;stroke-width:2;}
  .g-et{fill:#aeb9cc;}
  .g-f{fill:#5f6d9f;}
  .g-fcald{fill:#f5b83d;}
  .g-prag{stroke-width:2;}
  .g-prag.g-revenire{stroke-dasharray:8 6;}
  .g-mod,.g-revenire{stroke:#f5b83d;fill:#f5b83d;}
  .g-paza,.g-driver{stroke:#ff6b5e;fill:#ff6b5e;}
  .g-max{stroke-width:3.5;stroke-linecap:round;fill:none;}
  .g-normal{stroke:#9fb4ff;fill:#9fb4ff;}
  .g-galben{stroke:#f1c40f;fill:#f1c40f;}
  .g-rosu{stroke:#ff6b5e;fill:#ff6b5e;}
  circle.g-normal,circle.g-galben,circle.g-rosu{stroke:none;}
  text.g-mod,text.g-revenire,text.g-paza,text.g-driver{stroke:none;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} .val{grid-template-columns:1fr;} .val dd{margin:0 0 6px;} }
</style>
</head>
<body>
<main>
<h1>__T_TITLU__</h1>
<p class="mesaj" id="incarcare">__T_INCARCARE__</p>
<div id="continut" class="ascuns">
  <p class="mesaj ascuns" id="indisponibil"></p>
  <section class="card" id="alegere">
    <div class="rand">
      <label for="mod">__T_MOD__</label>
      <select id="mod"></select>
    </div>
    <p class="mesaj" id="mesaj"></p>
    <p class="descriere" id="descriere"></p>
    <p class="nota" id="detaliu"></p>
    <p class="nota" id="performantaAscunsa"></p>
  </section>
  <section class="card">
    <dl class="val">
      <dt id="eSetata">__T_SETATA__</dt><dd id="setata"></dd>
      <dt>__T_ACUM__</dt><dd id="acum"></dd>
      <dt>__T_TEMPERATURA__</dt><dd id="temperatura"></dd>
      <dt>__T_TENSIUNEA__</dt><dd id="tensiune"></dd>
      <dt>__T_FOLOSIT__</dt><dd id="folosit"></dd>
    </dl>
    <p class="motiv" id="motiv"></p>
  </section>
  <section class="card ascuns" id="cardGrafic">
    <h2 id="titluGrafic"></h2>
    <div class="alegeri" role="group" aria-label="__T_GRAFIC__">
      <button type="button" id="g60" class="ales" aria-pressed="true"></button>
      <button type="button" id="g30" aria-pressed="false"></button>
    </div>
    <div class="grafic" id="grafic"></div>
    <p class="nota" id="legendaGrafic"></p>
    <p class="nota" id="istoricGrafic"></p>
    <p class="nota" id="memorieGrafic"></p>
  </section>
  <section class="card" id="cardTrepte">
    <h2>__T_TREPTE__</h2>
    <div id="trepte"></div>
  </section>
  <p class="nota" id="pazaDriver"></p>
  <p class="nota" id="notaMod">__NOTA_MOD__</p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var TXT = __TEXTE_JS__;
var ultim = null;
var GRAFIC = 60;
var eroareCitire = false;
var incarcat = false;
function $(id){ return document.getElementById(id); }
function esc(t){ return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
function n1(v){ return Math.round(v * 10) / 10; }
function zona(g, t){ var z = g.zone || {}; return t >= z.rosu ? "rosu" : (t >= z.galben ? "galben" : "normal"); }
function latimeText(t, f){ return String(t).length * f * 0.62 + 4; }
function pozitii(etichete, rand, f, susLim, josLim){
  // ca HdsProcesor._pozitiiEtichete: fiecare valoare in dreptul liniei ei (liniile se opresc inaintea coloanei); cand
  // doua linii sunt prea aproape, textele se departeaza cat trebuie, in aceeasi ordine
  var departe = 0.84 * f + 2, lo = susLim + rand / 2, hi = josLim - rand / 2, rez = {};
  var ordine = etichete.slice().sort(function(a, b){ return a.y - b.y; });
  var c = ordine.map(function(e){ return Math.min(Math.max(e.y, lo), hi); });
  for(var i = 1; i < c.length; i++){ c[i] = Math.max(c[i], c[i - 1] + departe); }
  if(c.length && c[c.length - 1] > hi){
    c[c.length - 1] = hi;
    for(var j = c.length - 2; j >= 0; j--){ c[j] = Math.min(c[j], c[j + 1] - departe); }
  }
  ordine.forEach(function(e, k){ rez[e.t] = c[k]; });
  return rez;
}
function desenGrafic(g){
  var el = $("grafic");
  var L = Math.max(280, Math.round(el.clientWidth || 640)), mic = L < 560;
  var H = mic ? 250 : 320, f = mic ? 12 : 13, rand = Math.round(f * 1.4), min = GRAFIC;
  var sc = (g.alegeri || {})[String(min)] || g;
  var segmente = (sc.segmente || []).filter(function(s){ return s.de_la > s.pana_la; });
  var fasie = segmente.length > 1 ? rand : 0;
  var st = Math.round(f * 4), col = Math.round(f * 4), x0 = st, x1 = L - col - 6, pw = x1 - x0;
  var sus = fasie + Math.round(rand / 2) + 2, jo = H - rand - 6, banda = mic ? 30 : 40, sb = jo - banda, jg = sb - 8, ph = jg - sus;
  var tj = sc.jos, ts = Math.max(sc.sus, sc.jos + 10);
  function X(u){ return n1(x1 - Math.min(min, Math.max(0, u)) * pw / min); }
  function Y(t){ return n1(jg - (t - tj) * ph / (ts - tj)); }
  function centru(p){ return p.in_urma + p.durata / 2; }
  var titlu = ((g.texte || {}).titlu || {})[String(min)] || "";
  var s = ['<svg xmlns="http://www.w3.org/2000/svg" width="' + L + '" height="' + H + '" viewBox="0 0 ' + L + ' ' + H +
    '" style="font-size:' + f + 'px" role="img" aria-label="' + esc(titlu) + '">'];
  var t, y, x;
  for(t = tj; t <= ts; t += 10){
    y = Y(t);
    s.push('<line class="g-grila" x1="' + x0 + '" y1="' + y + '" x2="' + x1 + '" y2="' + y + '"/>');
    s.push('<text class="g-et" x="' + (st - 6) + '" y="' + y + '" text-anchor="end" dominant-baseline="middle">' + t + ' °C</text>');
  }
  // orele: la o ora din 10 in 10 minute, la 30 de minute din 5 in 5; textul lung (ceasul nepus) numai la fiecare al doilea
  var ore = (g.ore || []).filter(function(o){ return o.in_urma <= min && (min <= 30 || o.zece); });
  var lt = Math.max(f * 3.4, Math.max.apply(null, [0].concat(ore.map(function(o){ return latimeText(o.text, f); }))));
  var sari = lt > pw * (min > 30 ? 10 : 5) / min - 4 ? 2 : 1;
  ore.forEach(function(o, k){
    x = X(o.in_urma);
    s.push('<line class="g-grila" x1="' + x + '" y1="' + sus + '" x2="' + x + '" y2="' + jo + '"/>');
    if(k % sari === 0){
      s.push('<text class="g-et" x="' + x + '" y="' + (jo + 4 + f) + '" text-anchor="middle">' + esc(o.text) + '</text>');
    }
  });
  if(typeof g.inceput_in_urma === "number" && g.inceput_in_urma < min){
    x = X(g.inceput_in_urma);
    s.push('<line class="g-inceput" x1="' + x + '" y1="' + sus + '" x2="' + x + '" y2="' + jo + '"/>');
  }
  // banda frecventei: „MHz” in stanga, treapta de sus in dreapta
  s.push('<text class="g-et" x="' + (st - 6) + '" y="' + (sb + banda / 2) + '" text-anchor="end" dominant-baseline="middle">MHz</text>');
  if(g.fsus){ s.push('<text class="g-et" x="' + (x1 + 6) + '" y="' + (sb + banda / 2) + '" dominant-baseline="middle">' + g.fsus + '</text>'); }
  s.push('<line class="g-grila" x1="' + x0 + '" y1="' + jo + '" x2="' + x1 + '" y2="' + jo + '"/>');
  var puncte = g.puncte || [];
  puncte.forEach(function(p){
    if(!p.fmhz || !g.fsus){ return; }
    var dr = X(p.in_urma) - 1, stg = Math.max(x0, X(p.in_urma + p.durata) + 1);
    if(dr - stg < 1){ return; }
    var h = Math.max(2, Math.round(banda * Math.min(1, p.fmhz / g.fsus)));
    s.push('<rect class="' + (p.caldura ? "g-fcald" : "g-f") + '" x="' + n1(stg) + '" y="' + (jo - h) + '" width="' + n1(dr - stg) + '" height="' + h + '"/>');
  });
  // liniile pragurilor: ale modurilor pe bucata lor de timp (revenirea intrerupta), paza pe toata latimea
  function linie(t, fel, xa, xb){
    if(t < tj || t > ts || xb - xa < 2){ return; }
    var y = Y(t);
    s.push('<line class="g-prag g-' + fel + '" x1="' + n1(xa) + '" y1="' + y + '" x2="' + n1(xb) + '" y2="' + y + '"/>');
  }
  var praguri = sc.praguri || [];
  if(segmente.length){
    segmente.forEach(function(sg){ (sg.praguri || []).forEach(function(p){ linie(p.t, p.fel, X(sg.de_la), X(sg.pana_la)); }); });
    praguri.forEach(function(p){ if(p.fel === "paza" || p.fel === "driver"){ linie(p.t, p.fel, x0, x1); } });
  } else {
    praguri.forEach(function(p){ linie(p.t, p.fel, x0, x1); });
  }
  // bucatile modurilor: linia schimbarii si numele modului sus, numai cand sunt mai multe
  if(fasie){
    segmente.forEach(function(sg, i){
      var xa = X(sg.de_la), xb = X(sg.pana_la);
      if(i > 0){ s.push('<line class="g-schimbare" x1="' + xa + '" y1="0" x2="' + xa + '" y2="' + jo + '"/>'); }
      if(sg.nume && xb - xa - 12 >= latimeText(sg.nume, f)){
        s.push('<text class="g-et" x="' + n1(xa + 6) + '" y="' + n1(fasie / 2) + '" dominant-baseline="middle">' + esc(sg.nume) + '</text>');
      }
    });
  }
  // datele: cea mai mare temperatura din fiecare minut, colorata
  var vazute = puncte.map(function(p){ return centru(p) <= min ? p : null; });
  var ultimul = vazute.length - 1;
  vazute.forEach(function(p, i){
    if(!p || p.tmax === null){ return; }
    var a = i > 0 && p.legat ? vazute[i - 1] : null;
    if(a && a.tmax !== null){
      s.push('<line class="g-max g-' + zona(g, Math.max(a.tmax, p.tmax)) + '" x1="' + X(centru(a)) + '" y1="' + Y(a.tmax) + '" x2="' + X(centru(p)) + '" y2="' + Y(p.tmax) + '"/>');
    } else {
      a = null;
    }
    var u = i < ultimul ? vazute[i + 1] : null;
    var legatUrm = u && u.legat && u.tmax !== null;
    if(i === ultimul || (!a && !legatUrm)){
      s.push('<circle class="g-' + zona(g, p.tmax) + '" cx="' + X(centru(p)) + '" cy="' + Y(p.tmax) + '" r="' + (i === ultimul ? 3.5 : 2.5) + '"/>');
    }
  });
  // coloana din dreapta: valorile liniilor care ajung aici, in afara datelor
  var et = praguri.filter(function(p){ return p.t >= tj && p.t <= ts; }).map(function(p){ return {t: p.t, y: Y(p.t)}; });
  var poz = pozitii(et, rand, f, fasie, jg);
  praguri.forEach(function(p){
    if(poz[p.t] === undefined){ return; }
    s.push('<text class="g-' + p.fel + '" x="' + (x1 + 6) + '" y="' + n1(poz[p.t]) + '" dominant-baseline="middle">' + p.t + ' °C</text>');
  });
  s.push("</svg>");
  el.innerHTML = s.join("");
}
function arataGrafic(g){
  var tx = g.texte || {}, m = String(GRAFIC);
  $("titluGrafic").textContent = (tx.titlu || {})[m] || "";
  ["60", "30"].forEach(function(k){
    var b = $("g" + k);
    b.textContent = (tx.alegeri || {})[k] || "";
    b.classList.toggle("ales", k === m);
    b.setAttribute("aria-pressed", k === m ? "true" : "false");
  });
  $("legendaGrafic").textContent = tx.legenda || "";
  $("istoricGrafic").textContent = (tx.istoric || {})[m] || "";
  $("memorieGrafic").textContent = tx.memorie || "";
  desenGrafic(g);
}
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
    return r.json().catch(function(){ return {result: false, message: TXT.neasteptat.replace("%s", r.status)}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function modul(id){
  var gasit = null;
  ((ultim && ultim.moduri) || []).forEach(function(m){ if(m.id === id){ gasit = m; } });
  return gasit;
}
function descrie(id){
  var m = modul(id);
  $("descriere").textContent = m ? m.descriere : "";
  $("detaliu").textContent = m ? m.detaliu : "";
}
function arata(d){
  ultim = d;
  var c = d.citire || {}, t = d.texte || {};
  $("indisponibil").textContent = t.indisponibil || "";
  $("indisponibil").classList.toggle("ascuns", !!d.disponibil);
  $("alegere").classList.toggle("ascuns", !d.disponibil);
  $("notaMod").classList.toggle("ascuns", !d.disponibil);
  $("cardTrepte").classList.toggle("ascuns", !d.disponibil || !(c.trepte || []).length);
  $("cardGrafic").classList.toggle("ascuns", !d.disponibil || !d.grafic);
  if(d.disponibil && d.grafic){ arataGrafic(d.grafic); }
  var s = $("mod");
  if(document.activeElement !== s){
    s.textContent = "";
    (d.moduri || []).forEach(function(m){ var o = document.createElement("option"); o.value = m.id; o.textContent = m.nume; o.disabled = m.disponibil === false; s.appendChild(o); });
    s.value = d.mod;
    descrie(d.mod);
  }
  $("performantaAscunsa").textContent = t.performanta_ascunsa || "";
  $("setata").textContent = t.setata || "";
  $("acum").textContent = t.acum || "";
  var temp = $("temperatura");
  temp.textContent = t.temperatura || "";
  temp.className = c.temperatura_culoare === "normal" ? "" : c.temperatura_culoare;
  $("tensiune").textContent = t.tensiune || "";
  $("folosit").textContent = (c.folosit_procent === null || c.folosit_procent === undefined) ? TXT.nu_se_poate_citi : c.folosit_procent + "%";
  $("motiv").textContent = t.motiv || "";
  $("motiv").classList.toggle("bine", !!c.racit);
  $("pazaDriver").textContent = t.paza_driver || "";
  var tr = $("trepte"); tr.textContent = "";
  (c.trepte || []).forEach(function(x){
    var r = document.createElement("div"); r.className = "treapta";
    var a = document.createElement("span"); a.className = "mhz"; a.textContent = x.mhz + " MHz";
    var b = document.createElement("div"); b.className = "bara";
    var u = document.createElement("span"); u.style.width = Math.max(0, Math.min(100, x.procent)) + "%"; b.appendChild(u);
    var p = document.createElement("span"); p.textContent = x.text || (x.procent + "%");
    r.appendChild(a); r.appendChild(b); r.appendChild(p); tr.appendChild(r);
  });
}
function nuRaspunde(text){
  // prima incarcare: in locul textului „Se citește...”; dupa aceea, vizibil sub modul de lucru, cu citirile pe gri
  if(!incarcat){ $("incarcare").textContent = text; return; }
  eroareCitire = true;
  mesaj(text, true);
  $("continut").classList.add("vechi");
}
function citeste(){
  return cerere("/api/procesor").then(function(d){
    if(!d.result){ nuRaspunde(d.message || TXT.necitit); return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    incarcat = true;
    if(eroareCitire){ eroareCitire = false; mesaj(""); $("continut").classList.remove("vechi"); }
    arata(d);
  }).catch(function(){ nuRaspunde(TXT.nu_raspunde_retea); });
}
$("mod").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("mod", $("mod").value);
  descrie($("mod").value);
  mesaj(TXT.se_salveaza);
  cerere("/api/procesor-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    $("mod").blur();
    if(d.moduri){ arata(d); }
  }).catch(function(){ mesaj(TXT.nu_raspunde, true); });
});
["60", "30"].forEach(function(k){
  $("g" + k).addEventListener("click", function(){
    GRAFIC = parseInt(k, 10);
    if(ultim && ultim.grafic){ arataGrafic(ultim.grafic); }
  });
});
if(typeof window !== "undefined" && window.addEventListener){
  window.addEventListener("resize", function(){ if(ultim && ultim.grafic){ desenGrafic(ultim.grafic); } });
}
citeste();
setInterval(function(){ if(document.visibilityState === "visible"){ citeste(); } }, 2000);
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
		N_("browser deconectat"),
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

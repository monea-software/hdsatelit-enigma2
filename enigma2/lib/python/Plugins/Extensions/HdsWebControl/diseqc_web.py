# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# diseqc_web.py: "Proba DiSEqC" in interfata web (HdsWebControl), perechea ecranelor de pe televizor Meniu >
# Orientarea si setarea antenei > Proba DiSEqC (entryID hds_antena_proba_diseqc; Plugins/SystemPlugins/DiseqcTester:
# DiseqcTesterNimSelection -> DiseqcTesterTestTypeSelection -> DiseqcTester).
#
# Aceeasi alegere a tunerului (numai tunerele pe care le arata ecranul, cu acelasi text), aceleasi setari ale probei
# (felul, oprirea dupa transpondere esuate sau reusite, jurnalul pe disc numai cu disc), din aceleasi functii ale
# pluginului. Proba ruleaza pe televizor, in ecranul DiseqcTester, exact ca din telecomanda (TuneTest are nevoie de
# ecran: timere, canalul brut, barele de progres); pagina il deschide si ii citeste starea (DiseqcTester.stareWeb),
# deci televizorul si pagina arata acelasi lucru, iar o proba pornita din telecomanda se vede si aici. Oprirea din
# pagina e EXIT-ul ecranului; la inchidere ecranul pune la loc canalul de dinainte. Pornirea muta antena si ia
# tunerul: confirmare in doi pasi, numai din browserul conectat, si regula meniu_comun_web.ocupat (standby, scanare,
# interfata nepornita); in plus nu porneste peste o proba deschisa sau pe un tuner care inregistreaza.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/proba-diseqc[?plan=<n>]        tunerele, alegerile, proba de pe televizor (sau ultima inchisa) cu
#                                            planurile ei; plan=<n>: si rezultatul planului n, textul de pe ecran
#   POST /api/proba-diseqc-porneste?tuner=<slot>&fel=quick|random|complete&esuate=<-1..8>&reusite=<-1..8>&jurnal=0|1
#                                            pas=intreaba -> intrebarea; cod=<cod> -> ecranul probei pe televizor
#   POST /api/proba-diseqc-opreste           inchide proba (ca EXIT); canalul de dinainte porneste din nou
#   GET  /proba-diseqc                       pagina
#
# FIRUL: totul pe firul enigma2, scurt (citeste starea ecranului). Pe PC si in emulator nu exista tuner: probele dau un
# Mediu fals. Fisierul nu importa nimic din enigma2 la incarcare.

ARGUMENTE = ("tuner", "fel", "esuate", "reusite", "jurnal", "plan", "pas", "cod")

# proba deschisa din pagina si ultima stare a unei probe inchise (a paginii sau din telecomanda)
_LUCRU = {"dialog": None, "final": None}


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _comun():
	from . import meniu_comun_web
	return meniu_comun_web


class Mediu(object):
	"""Ce foloseste pagina pe receptor: pluginul probei, sesiunea, ferestrele deschise. Probele dau unul fals."""

	def __init__(self, D=None, sesiune=None, ocupat=None, dialoguri=None, inregistrare=None):
		self._D, self._sesiune, self._ocupat = D, sesiune, ocupat
		self._dialoguri, self._inregistrare = dialoguri, inregistrare

	@property
	def D(self):
		if self._D is None:
			from Plugins.SystemPlugins.DiseqcTester import plugin
			self._D = plugin
		return self._D

	def sesiune(self):
		return self._sesiune() if self._sesiune is not None else _comun().sesiune()

	def ocupat(self, s):
		return self._ocupat(s) if self._ocupat is not None else _comun().ocupat(s)

	def dialoguri(self, s):
		"""ferestrele deschise pe televizor, cea din fata prima (scanare_web._dialoguri)"""
		if self._dialoguri is not None:
			return self._dialoguri(s)
		from .scanare_web import _dialoguri
		return _dialoguri(s)

	def inregistrare(self, slot):
		"""True cand o inregistrare foloseste tunerul (Components/HdsGasireSemnal, ca gasirea semnalului)"""
		if self._inregistrare is not None:
			return self._inregistrare(slot)
		try:
			from Components.HdsGasireSemnal import _inregistrare_pe_tuner
			return _inregistrare_pe_tuner(slot)
		except Exception:
			return False


def argumente(request):
	"""{cheie: text} numai pentru cheile stiute (fara token): codul confirmarii intreg, restul scurt"""
	rez = _comun().argumente(request, ARGUMENTE, 32)
	for cheie in list(rez):
		if cheie != "cod":
			rez[cheie] = rez[cheie][:12]
	return rez


def _dialog(M, s):
	"""(fereastra DiseqcTester deschisa pe televizor, pornita din pagina?) sau (None, False)"""
	if s is None:
		return None, False
	deschise = M.dialoguri(s)
	al_nostru = _LUCRU["dialog"]
	if al_nostru is not None:
		if any(d is al_nostru for d in deschise):
			return al_nostru, True
		_LUCRU["dialog"] = None
	for d in deschise:
		if isinstance(d, M.D.DiseqcTester):
			_urmareste(d)
			return d, False
	return None, False


def _urmareste(dlg):
	"""La inchiderea probei (EXIT pe televizor sau Opreste din pagina) ramane ultima stare, cu rezultatul fiecarui plan,
	ca pagina sa o arate si dupa. Ruleaza inaintea inchiderii ecranului (care opreste proba si pune canalul la loc)."""
	if getattr(dlg, "_hds_web_urmarit", False):
		return
	try:
		dlg._hds_web_urmarit = True

		def laInchidere():
			try:
				final = dlg.stareWeb()
				final["texte"] = [dlg.textPlan(p["index"]) for p in final["planuri"]]
			except Exception as eroare:
				print("[HdsWebControl] proba DiSEqC, starea de la inchidere: %s" % eroare)
				final = {"planuri": [], "texte": []}
			final.update(oprita=bool(final.get("in_curs")), in_curs=False, din_web=_LUCRU["dialog"] is dlg)
			if _LUCRU["dialog"] is dlg:
				_LUCRU["dialog"] = None
			_LUCRU["final"] = final
		dlg.onClose.insert(0, laInchidere)
	except Exception as eroare:
		print("[HdsWebControl] nu pot urmari proba DiSEqC: %s" % eroare)


def _plan(arg):
	try:
		return int(arg.get("plan", ""))
	except ValueError:
		return None


def stare(arg, M):
	"""Corpul lui GET /api/proba-diseqc"""
	D = M.D
	s = M.sesiune()
	rez = {
		"result": True,
		"tunere": D.tuneriProba(),
		"alegeri": {"fel": [[k, t] for k, t in D.alegeriFel()], "oprire": [k for k, _x in D.alegeriOprire()]},
		"implicite": {"fel": "quick", "esuate": D.OPRIRE_ESUATE, "reusite": D.OPRIRE_REUSITE},
		"jurnal_disc": bool(D.jurnalPeDisc()),
		"proba": None,
	}
	n = _plan(arg)
	dlg, din_web = _dialog(M, s)
	if dlg is not None:
		st = dlg.stareWeb()
		st.update(activ=True, din_web=din_web, poate_opri=getattr(s, "current_dialog", None) is dlg)
		if n is not None and 0 <= n < len(st["planuri"]):
			st["text_plan"] = [n, dlg.textPlan(st["planuri"][n]["index"])]
		rez["proba"] = st
	elif _LUCRU["final"] is not None:
		st = dict(_LUCRU["final"])
		texte = st.pop("texte", [])
		st.update(activ=False, poate_opri=False)
		if n is not None and 0 <= n < len(texte):
			st["text_plan"] = [n, texte[n]]
		rez["proba"] = st
	rez["motiv"] = _motivPornire(M, s, dlg)
	return rez


def _motivPornire(M, s, dlg):
	"""de ce nu se poate porni acum o proba (None = se poate)"""
	motiv = M.ocupat(s)
	if motiv:
		return motiv
	if dlg is not None:
		return _t("O probă DiSEqC e deja deschisă pe televizor. Închide-o întâi.")
	return None


def porneste(arg, request, M):
	"""Pornirea probei, in doi pasi: intrebarea, apoi ecranul DiseqcTester pe televizor (ca OK in ecranul setarilor)"""
	D = M.D
	C = _comun()
	tinta = "|".join(arg.get(k, "") for k in ("tuner", "fel", "esuate", "reusite", "jurnal"))
	pas = arg.get("pas", "")
	if pas == "renunta":
		C.uita("proba-diseqc", tinta)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	refuz = C.numaiBrowser(request)
	if refuz:
		return {"result": False, "message": refuz}
	tunere = [t for t in D.tuneriProba() if t["se_alege"]]
	tuner = None
	for t in tunere:
		if str(t["slot"]) == arg.get("tuner", ""):
			tuner = t
	if tuner is None:
		if not tunere:
			return {"result": False, "message": _t("Niciun tuner de satelit potrivit pentru proba DiSEqC.")}
		return {"result": False, "message": _t("Alege unul din tunerele din listă.")}
	fel = arg.get("fel", "")
	if fel not in [k for k, _x in D.alegeriFel()]:
		return {"result": False, "message": _t("Se alege felul probei din listă.")}
	oprire = [k for k, _x in D.alegeriOprire()]
	esuate, reusite = arg.get("esuate", ""), arg.get("reusite", "")
	if esuate not in oprire or reusite not in oprire:
		return {"result": False, "message": _t("Se alege din listă după câte transpondere se trece mai departe.")}
	jurnal = arg.get("jurnal", "0")
	if jurnal not in ("0", "1") or (jurnal == "1" and not D.jurnalPeDisc()):
		return {"result": False, "message": _t("Rezultatele se pot scrie numai cu un disc.")}
	s = M.sesiune()
	dlg, _din_web = _dialog(M, s)
	motiv = _motivPornire(M, s, dlg)
	if motiv:
		return {"result": False, "message": motiv}
	if M.inregistrare(tuner["slot"]):
		return {"result": False, "message": _t("Tunerul înregistrează acum. Proba se poate porni după înregistrare.")}
	if pas == "intreaba":
		return C.raspunsIntrebare("proba-diseqc", tinta, _t("Pornești proba DiSEqC pe %s?") % tuner["nume"],
			_t("Pornește proba"), [
				_t("Proba trece antena prin fiecare poziție DiSEqC și acordează transponderele fiecărui satelit."),
				_t("Dacă tunerul e folosit de canalul de acum, canalul se oprește cât ține proba și pornește din nou "
					"când o închizi."),
				_t("Pe televizor se deschide ecranul probei. Îl închizi de acolo cu EXIT sau din pagină.")])
	cod = arg.get("cod", "")
	if not cod:
		return {"result": False, "message": _t("Proba cere întâi confirmarea din pagină.")}
	if not C.verifica("proba-diseqc", tinta, cod):
		return C.codGresit()
	dlg = D.deschideProba(s, tuner["slot"], fel, esuate, reusite, jurnal == "1")
	_LUCRU["dialog"] = dlg
	_LUCRU["final"] = None
	if dlg is not None:
		_urmareste(dlg)
	return {"result": True, "message": _t("Proba a pornit pe televizor.")}


def opreste(arg, request, M):
	"""Opreste din pagina = EXIT in ecranul probei"""
	s = M.sesiune()
	dlg, _din_web = _dialog(M, s)
	if dlg is None:
		return {"result": False, "message": _t("Nicio probă DiSEqC deschisă pe televizor.")}
	if getattr(s, "current_dialog", None) is not dlg:
		return {"result": False, "message": _t("Pe televizor e deschis un mesaj peste probă. Închide-l cu OK, apoi "
			"încearcă din nou.")}
	dlg.keyCancel()
	return {"result": True, "message": _t("Proba s-a închis. Canalul de dinainte pornește din nou.")}


def rute(baza, resource, mediu=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	def M():
		return mediu if mediu is not None else Mediu()

	class StareResource(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(argumente(request), M()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ActiuneResource(baza):
		schimbaCeva = True
		functie = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.functie(argumente(request), request, M()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	def actiune(f):
		r = ActiuneResource()
		r.functie = f
		return r

	class PaginaResource(resource.Resource):
		"""GET /proba-diseqc"""
		isLeaf = True

		def render_GET(self, request):
			return _comun().pagina(request, pagina_text)

	return ({b"proba-diseqc": StareResource(), b"proba-diseqc-porneste": actiune(porneste),
		b"proba-diseqc-opreste": actiune(opreste)}, {b"proba-diseqc": PaginaResource()})


def pagina_text(stil, config_pagina):
	C = _comun()
	return C.sablon(_traducePagina(PAGINA), stil, config_pagina,
		{"__DRUM_MENIU__": C.drumHtml("hds_antena_proba_diseqc")})


PAGINA = r"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proba DiSEqC</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .tuner-text{white-space:pre-line;}
  progress{width:100%;height:14px;}
  .bara{margin:6px 0 10px;}
  .planuri td,.planuri th{vertical-align:middle;}
  .planuri button{min-height:44px;}
  .planuri .scurt{white-space:nowrap;}
  @media (max-width:560px){ .planuri .ascunde-telefon{display:none;} }
</style>
</head>
<body>
<main>
<h1>Proba DiSEqC</h1>
<p class="nota">Proba trece antena prin fiecare poziție DiSEqC (comutatorul de antene) și acordează pe rând transponderele fiecărui satelit setat pe tuner: arată pe care poziții se recepționează semnalul și pe care nu.</p>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card ascuns" id="faraTuner">
    <p class="intrebare">Niciun tuner de satelit potrivit pentru probă.</p>
    <p class="nota">Proba merge numai pe un tuner DVB-S setat (nu legat de alt tuner și nu nesetat). Tunerele se setează în Orientarea și setarea antenei.</p>
  </section>
  <div id="alegeri">
    <section class="card">
      <h2>Tunerul</h2>
      <div class="rand"><label for="tuner">Tunerul de probat</label><select id="tuner"></select></div>
      <p class="nota tuner-text" id="tunerText"></p>
    </section>
    <section class="card">
      <h2>Setările probei</h2>
      <div class="rand"><label for="fel">Felul probei</label><select id="fel"></select></div>
      <div class="rand"><label for="esuate">Trece la planul următor după transpondere eșuate</label><select id="esuate"></select></div>
      <div class="rand"><label for="reusite">Trece la planul următor după transpondere reușite</label><select id="reusite"></select></div>
      <div class="rand ascuns" id="randJurnal"><label for="jurnal">Scrie rezultatele pe disc</label><select id="jurnal"><option value="0">Nu</option><option value="1">Da</option></select></div>
      <p class="nota">Rapidă: fiecare plan o dată, în ordinea sateliților. La întâmplare: aceleași planuri, în altă ordine. Completă: fiecare trecere de la un plan la altul, ca să se vadă și comutările greșite.</p>
      <div class="butoane"><button type="button" id="porneste" class="principal">Pornește proba</button></div>
      <p class="nota" id="motiv"></p>
    </section>
  </div>
  <section class="card ascuns" id="proba">
    <h2 id="probaTitlu">Proba</h2>
    <p class="intrebare" id="probaText"></p>
    <div class="bara"><span class="nota">Toată proba</span><progress id="total" max="1" value="0"></progress></div>
    <div class="bara"><span class="nota">Planul de acum</span><progress id="planAcum" max="1" value="0"></progress></div>
    <div class="status-linie"><span>Reușite</span><span id="cReusite"></span></div>
    <div class="status-linie"><span>Eșuate</span><span id="cEsuate"></span></div>
    <div class="status-linie"><span>Cu erori</span><span id="cErori"></span></div>
    <div class="status-linie"><span>Netestate</span><span id="cNetestate"></span></div>
    <table class="planuri">
      <thead><tr><th>Planul (satelit, bandă, polarizare)</th><th class="scurt">Starea</th><th class="ascunde-telefon">Transpondere</th><th></th></tr></thead>
      <tbody id="planuri"></tbody>
    </table>
    <pre class="text ascuns" id="textPlan"></pre>
    <div class="butoane"><button type="button" id="opreste">Oprește proba</button></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceeași probă e pe televizor, în __DRUM_MENIU__. Proba pornită din telecomandă se vede și aici.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var D = null, CEAS = null, PLAN = null, PUS = false;
var STARI = {reusit: "reușit", esuat: "eșuat", cu_erori: "cu erori", netestat: "netestat", in_lucru: "în lucru"};
var MOTIVE = {tune_failed: "fără semnal", pids_failed: "alt transponder decât cel așteptat"};
function el(tip, clasa, text){ var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text !== undefined && text !== null){ e.textContent = text; } return e; }
function optiuni(s, lista){ s.textContent = ""; lista.forEach(function(x){ var o = el("option", null, x[1]); o.value = x[0]; if(x[2]){ o.disabled = true; } s.appendChild(o); }); }
function textOprire(k){ return k === "-1" ? "toate cele cunoscute" : k; }
function programeaza(ms){ if(CEAS){ clearTimeout(CEAS); CEAS = null; } if(ms){ CEAS = setTimeout(citeste, ms); } }
function citeste(){
  var q = "/api/proba-diseqc" + (PLAN !== null ? "?plan=" + PLAN : "");
  return cerere(q).then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    D = d; arata(d);
    programeaza(d.proba && d.proba.in_curs ? 1500 : (d.proba && d.proba.activ ? 4000 : 0));
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function arataAlegeri(d){
  var potrivite = d.tunere.filter(function(t){ return t.se_alege; });
  $("faraTuner").classList.toggle("ascuns", potrivite.length > 0);
  $("alegeri").classList.toggle("ascuns", !d.tunere.length);
  if(!PUS){
    optiuni($("tuner"), d.tunere.map(function(t){ return [String(t.slot), t.nume, !t.se_alege]; }));
    if(potrivite.length){ $("tuner").value = String(potrivite[0].slot); }
    optiuni($("fel"), d.alegeri.fel);
    optiuni($("esuate"), d.alegeri.oprire.map(function(k){ return [k, textOprire(k)]; }));
    optiuni($("reusite"), d.alegeri.oprire.map(function(k){ return [k, textOprire(k)]; }));
    $("fel").value = d.implicite.fel; $("esuate").value = d.implicite.esuate; $("reusite").value = d.implicite.reusite;
    PUS = d.tunere.length > 0;
  }
  var t = d.tunere.filter(function(x){ return String(x.slot) === $("tuner").value; })[0];
  $("tunerText").textContent = t ? t.text : "";
  $("randJurnal").classList.toggle("ascuns", !d.jurnal_disc);
  if(!d.jurnal_disc){ $("jurnal").value = "0"; }
  $("porneste").disabled = !!d.motiv || !potrivite.length;
  $("motiv").textContent = d.motiv || "";
}
function numePlan(p){ return p.satelit + " · " + (p.banda_joasa ? "banda joasă" : "banda înaltă") + " · " + (p.orizontala ? "orizontală" : "verticală"); }
function arataProba(d){
  var p = d.proba, c = $("proba");
  c.classList.toggle("ascuns", !p);
  if(!p){ return; }
  var tn = d.tunere.filter(function(x){ return x.slot === p.tuner; })[0];
  $("probaTitlu").textContent = "Proba" + (tn ? " pe " + tn.nume : "");
  var text;
  if(p.fara_tuner){ text = "Tunerul nu se poate folosi acum: îl ține o înregistrare sau alt ecran."; }
  else if(p.in_curs){ text = "Proba merge pe televizor."; }
  else if(p.activ){ text = "Proba s-a terminat. Ecranul ei e încă deschis pe televizor; închide-l ca să pornească din nou canalul."; }
  else if(p.oprita){ text = "Proba a fost oprită înainte de sfârșit."; }
  else { text = "Ultima probă, terminată."; }
  $("probaText").textContent = text;
  $("total").max = Math.max(1, p.total[1]); $("total").value = p.total[0];
  $("planAcum").max = Math.max(1, p.plan[1]); $("planAcum").value = p.plan[0];
  $("cReusite").textContent = p.contoare.reusite; $("cEsuate").textContent = p.contoare.esuate;
  $("cErori").textContent = p.contoare.cu_erori; $("cNetestate").textContent = p.contoare.netestate;
  var tb = $("planuri"); tb.textContent = "";
  p.planuri.forEach(function(x, i){
    var tr = el("tr");
    tr.appendChild(el("td", null, numePlan(x)));
    tr.appendChild(el("td", "scurt" + (x.stare === "esuat" || x.stare === "cu_erori" ? " eroare" : ""), STARI[x.stare] || x.stare));
    var m = Object.keys(x.motive || {}).map(function(k){ return (MOTIVE[k] || k) + ": " + x.motive[k]; });
    tr.appendChild(el("td", "ascunde-telefon", x.reusite + " reușite, " + x.esuate + " eșuate" + (m.length ? " (" + m.join(", ") + ")" : "")));
    var td = el("td");
    if(!p.in_curs && (x.reusite || x.esuate)){
      var b = el("button", null, PLAN === i ? "Ascunde" : "Detalii"); b.type = "button";
      b.addEventListener("click", function(){ PLAN = PLAN === i ? null : i; citeste(); });
      td.appendChild(b);
    }
    tr.appendChild(td); tb.appendChild(tr);
  });
  var tp = p.text_plan;
  $("textPlan").classList.toggle("ascuns", !tp || PLAN === null);
  $("textPlan").textContent = tp ? tp[1] : "";
  $("opreste").classList.toggle("ascuns", !p.activ);
  $("opreste").textContent = p.in_curs ? "Oprește proba" : "Închide proba";
  $("opreste").disabled = !p.poate_opri;
}
function arata(d){ arataAlegeri(d); arataProba(d); }
$("tuner").addEventListener("change", function(){ if(D){ arataAlegeri(D); } });
$("porneste").addEventListener("click", function(){
  var q = new URLSearchParams();
  q.set("tuner", $("tuner").value); q.set("fel", $("fel").value); q.set("esuate", $("esuate").value);
  q.set("reusite", $("reusite").value); q.set("jurnal", D && D.jurnal_disc ? $("jurnal").value : "0");
  PLAN = null;
  cuConfirmare("/api/proba-diseqc-porneste", q, function(){ citeste(); });
});
$("opreste").addEventListener("click", function(){
  mesaj("Se trimite...");
  cerere("/api/proba-diseqc-opreste", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); citeste(); }).catch(nimicNuRaspunde);
});
citeste();
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
		N_("Proba DiSEqC"),
		N_("Proba trece antena prin fiecare poziție DiSEqC (comutatorul de antene) și acordează pe rând "
			"transponderele fiecărui satelit setat pe tuner: arată pe care poziții se recepționează semnalul "
			"și pe care nu."),
		N_("Se citește starea..."),
		N_("Niciun tuner de satelit potrivit pentru probă."),
		N_("Proba merge numai pe un tuner DVB-S setat (nu legat de alt tuner și nu nesetat). Tunerele se "
			"setează în Orientarea și setarea antenei."),
		N_("Tunerul"),
		N_("Tunerul de probat"),
		N_("Setările probei"),
		N_("Felul probei"),
		N_("Trece la planul următor după transpondere eșuate"),
		N_("Trece la planul următor după transpondere reușite"),
		N_("Scrie rezultatele pe disc"),
		N_("Nu"),
		N_("Da"),
		N_("Rapidă: fiecare plan o dată, în ordinea sateliților. La întâmplare: aceleași planuri, în altă "
			"ordine. Completă: fiecare trecere de la un plan la altul, ca să se vadă și comutările greșite."),
		N_("Pornește proba"),
		N_("Proba"),
		N_("Toată proba"),
		N_("Planul de acum"),
		N_("Reușite"),
		N_("Eșuate"),
		N_("Cu erori"),
		N_("Netestate"),
		N_("Planul (satelit, bandă, polarizare)"),
		N_("Starea"),
		N_("Transpondere"),
		N_("Oprește proba"),
		N_("Aceeași probă e pe televizor, în __DRUM_MENIU__. Proba pornită din telecomandă se vede și aici."),
	),
	"js": (
		N_("reușit"),
		N_("eșuat"),
		N_("cu erori"),
		N_("în lucru"),
		N_("fără semnal"),
		N_("alt transponder decât cel așteptat"),
		N_("toate cele cunoscute"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("banda joasă"),
		N_("banda înaltă"),
		N_("orizontală"),
		N_("verticală"),
		N_("Proba"),
		N_("pe"),
		N_("Tunerul nu se poate folosi acum: îl ține o înregistrare sau alt ecran."),
		N_("Proba merge pe televizor."),
		N_("Proba s-a terminat. Ecranul ei e încă deschis pe televizor; închide-l ca să pornească din nou "
			"canalul."),
		N_("Proba a fost oprită înainte de sfârșit."),
		N_("Ultima probă, terminată."),
		N_("reușite,"),
		N_("eșuate"),
		N_("Ascunde"),
		N_("Detalii"),
		N_("Oprește proba"),
		N_("Închide proba"),
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# alimentare_web.py: grupul Meniu > Standby si repornire in interfata web (HdsWebControl), pagina /alimentare.
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor grupul are sase intrari (data/menu.xml):
#   Oprire programata (sleep, Screens/SleepTimerEdit.py), Standby (standby, Screens/Standby.Standby), Reporneste
#   interfata (restart_enigma, TryQuitMainloop 3), Reporneste receptorul (restart, TryQuitMainloop 2), Porneste alte
#   imagini (return_to_flash, Screens/HdsPornireMultipla.py, numai cu SystemInfo["HdsMultiboot"]: Octagon SF8008 si
#   SF8008 MINI; altfel cardul lipseste ca si intrarea) si Oprire completa (deep_standby, TryQuitMainloop 1).
#   Aici: un card pentru fiecare, cu aceleasi setari si actiuni, plus starea receptorului. Meniul web trimite
#   ?f=somn|standby|interfata|receptor|flash|oprire, iar pagina aduce cardul acela primul.
#
# O SINGURA LOGICA: Components/HdsAlimentare.py (ecranul opririi programate o foloseste si el) si, pentru cardul flash
# (imaginile instalate in celelalte locuri si alegerea uneia), Components/HdsPornireMultipla.py, ca ecranul.
#
# Standby-ul, repornirile si oprirea se fac in doi pasi (meniu_comun_web: intrebarea, apoi un cod de unica folosinta),
# numai din browserul conectat (nu cu ?token=). Apoi se deschide pe televizor acelasi ecran ca din meniu, dupa 1,5 s, ca
# raspunsul sa plece inainte. TryQuitMainloop intreaba si pe televizor cand o inregistrare e in curs sau incepe curand
# sau cand lucreaza ceva in fundal: pagina o spune in intrebare si in raspuns. meniu_web.NEDESCHISE ramane: butonul
# "Deschide pe televizor" din /meniu nu opreste receptorul fara confirmare; calea cu confirmare e pagina aceasta.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/alimentare                                   starea receptorului, oprirea programata, cardurile
#   POST /api/alimentare-somn?fapta=porneste&minute=<n>&actiune=shutdown|standby&intreaba=0|1
#                                                          ca OK pe ecran cu Enable timer (actiunea si intrebarea
#                                                          sunt optionale: lipsa = valoarea de acum)
#   POST /api/alimentare-somn?fapta=opreste                ca OK pe ecran cu Disable timer
#   POST /api/alimentare-fa?ce=standby|interfata|receptor|flash|oprire&pas=intreaba   intrebarea si codul
#   POST /api/alimentare-fa?ce=...&cod=<cod>                fapta: ecranul de pe televizor peste 1,5 s
#   POST /api/alimentare-fa?ce=...&pas=renunta              codul nu mai e bun
#   GET  /api/pornire-multipla                             imaginile instalate in locurile din memorie (cardul flash;
#                                                          monteaza partitia userdata, deci nu in starea de la 10 s)
#   POST /api/alimentare-fa?ce=flash&loc=<N>&pas=intreaba / &cod=<cod>   alegerea imaginii din locul N: STARTUP scris
#                                                          (HdsPornireMultipla.reporneste), apoi TryQuitMainloop 2
#   GET  /alimentare[?f=...]                                pagina
#
# FIRUL: totul pe firul enigma2 si scurt (cateva atribute, o cautare in ghidul TV). Fisierul nu importa nimic din
# enigma2 la incarcare: probele de pe PC dau modulul lor (A), sesiunea, config, SystemInfo si Standby.

DUPA_MS = 1500
CONFIRMARE = "alimentare"
CHEI_SOMN = ("fapta", "minute", "actiune", "intreaba")
CHEI_FA = ("ce", "pas", "cod", "loc")
CACHE_IMAGINI_S = 15
# ?f= din meniul web -> cardul paginii (aceleasi chei ca HdsAlimentare.ACTIUNI, plus somn)
CARDURI = ("somn", "standby", "interfata", "receptor", "flash", "oprire")
# entryID-urile din data/menu.xml, pentru drumul de pe televizor al fiecarui card
INTRARI = {"somn": "sleep", "standby": "standby", "interfata": "restart_enigma", "receptor": "restart",
	"flash": "return_to_flash", "oprire": "deep_standby"}


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def _t(text):
	return _mc()._t(text)


def _a(A=None):
	if A is not None:
		return A
	from Components import HdsAlimentare
	return HdsAlimentare


def _pm(PM=None):
	if PM is not None:
		return PM
	from Components import HdsPornireMultipla
	return HdsPornireMultipla


_imagini = {}


def _faraMultiboot():
	return _t("Imaginea nu are altă memorie din care să pornească, deci intrarea nu e nici pe televizor.")


def imagini(PM=None, SystemInfo=None, proaspat=False):
	"""Pentru GET /api/pornire-multipla: imaginile instalate (randurile ca pe receptor) si nota."""
	if not _si(SystemInfo).get("HdsMultiboot"):
		return {"result": False, "message": _faraMultiboot()}
	import time
	PM = _pm(PM)
	acum = time.time()
	if proaspat or not _imagini.get("stare") or acum - _imagini.get("cand", 0) > CACHE_IMAGINI_S:
		_imagini["stare"] = PM.publice(PM.locuri())
		_imagini["cand"] = acum
	rez = {"result": True}
	rez.update(_imagini["stare"])
	return rez


def _faImagine(argumente, PM, sesiune, SI, Standby, job_manager, fabrica_ceas, A):
	"""Cardul flash: alegerea imaginii din locul `loc`, in doi pasi, apoi repornirea in ea."""
	MC = _mc()
	if not SI.get("HdsMultiboot"):
		return {"result": False, "message": _faraMultiboot()}
	loc = argumente.get("loc", "")
	if not (0 < len(loc) <= 2 and loc.isdigit()):
		return {"result": False, "message": _t("Acțiune necunoscută.")}
	tinta = "flash:" + loc
	pas = argumente.get("pas", "")
	if pas == "renunta":
		MC.uita(CONFIRMARE, tinta)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if sesiune is None:
		return {"result": False, "message": _faraSesiune()}
	if getattr(_standby(Standby), "inTryQuitMainloop", False):
		MC.uita(CONFIRMARE, tinta)
		return {"result": False, "message": _t("Pe televizor așteaptă deja o întrebare de oprire sau de repornire. "
			"Răspunde acolo.")}
	PM = _pm(PM)
	if pas == "intreaba":
		stare = imagini(PM, SI, proaspat=True)
		gasit = [l for l in stare.get("locuri", []) if l["fel"] == "emmc" and l["loc"] == loc]
		if not gasit:
			return {"result": False, "message": _t(PM.NEGASIT)}
		if gasit[0]["acum"]:
			return {"result": False, "message": _t(PM.DEJA)}
		if not gasit[0]["alegere"]:
			return {"result": False, "message": _t(PM.REFUZ) % loc}
		r = A.stareReceptor(sesiune, Standby=_standby(Standby), job_manager=job_manager)
		return MC.raspunsIntrebare(CONFIRMARE, tinta, _t(PM.INTREBARE) % gasit[0]["imagine"], _t(PM.BUTON),
			[x for x in _detalii("flash", r)])
	if not MC.verifica(CONFIRMARE, tinta, argumente.get("cod", "")):
		return MC.codGresit()
	intreaba = A.vaIntreba(sesiune)
	ok, text = PM.reporneste(sesiune, loc, dupa_ms=DUPA_MS, fabrica_ceas=fabrica_ceas, Standby=Standby)
	_imagini.clear()
	if not ok:
		return {"result": False, "message": text}
	return {"result": True, "ce": "flash", "intreaba": bool(intreaba), "message": _dupa("flash", intreaba, text)}


def _si(SystemInfo=None):
	if SystemInfo is not None:
		return SystemInfo
	from Components.SystemInfo import SystemInfo
	return SystemInfo


def _standby(Standby=None):
	if Standby is not None:
		return Standby
	from Screens import Standby
	return Standby


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config
	return config


def _faraSesiune():
	return _t("Interfața web nu are încă legătura cu ecranul receptorului. Așteaptă pornirea completă a receptorului, "
		"apoi încearcă din nou.")


def stare(A=None, sesiune=None, config=None, SystemInfo=None, Standby=None, job_manager=None):
	"""Pentru GET /api/alimentare."""
	A = _a(A)
	SI = _si(SystemInfo)
	S = _standby(Standby)
	config = _config(config)
	receptor = A.stareReceptor(sesiune, Standby=S, job_manager=job_manager)
	s = None
	nav = getattr(sesiune, "nav", None)
	if nav is not None:
		s = A.stareSomn(nav, config)
		s["text_actiune"] = A.textActiune(s["actiune"], SI)
		try:
			s["minute_canal"] = A.minuteCanal(nav)
		except Exception as eroare:
			_mc().jurnal("alimentare: timpul canalului: %r" % eroare)
			s["minute_canal"] = None
	minim, maxim = A.limiteMinute(config)
	return {
		"result": True,
		"sesiune": sesiune is not None,
		"receptor": receptor,
		"somn": s,
		"actiuni_somn": A.alegeriActiune(config, SI),
		"minute_min": minim,
		"minute_max": maxim,
		"carduri": [{"ce": c, "vizibil": c != "flash" or bool(SI.get("HdsMultiboot"))} for c in CARDURI],
	}


def somn(argumente, A=None, sesiune=None, config=None, SystemInfo=None, Standby=None, job_manager=None,
		configfile=None):
	"""POST /api/alimentare-somn: ca OK pe ecranul opririi programate. O valoare straina nu schimba nimic."""
	A = _a(A)
	config = _config(config)

	def cu_stare(rezultat, mesaj):
		rez = stare(A, sesiune, config, SystemInfo, Standby, job_manager)
		rez.update(result=rezultat, message=mesaj)
		return rez

	fapta = argumente.get("fapta", "")
	if fapta not in ("porneste", "opreste"):
		return cu_stare(False, _t("Se alege cu fapta=porneste sau fapta=opreste."))
	nav = getattr(sesiune, "nav", None)
	if nav is None:
		return {"result": False, "message": _faraSesiune()}
	if fapta == "opreste":
		A.opreste(nav)
		return cu_stare(True, _t("The sleep timer has been disabled."))
	c = A.initConfig(config)
	minim, maxim = A.limiteMinute(config)
	text = argumente.get("minute", "")
	minute = int(text) if 0 < len(text) <= 12 and all(ch in "0123456789" for ch in text) else None
	if minute is None or minute < minim or minute > maxim:
		return cu_stare(False, _t("Minutele se scriu ca număr întreg, de la %d la %d.") % (minim, maxim))
	actiune = argumente.get("actiune")
	if actiune is not None:
		gasita = [v for v in c.action.choices if str(v) == actiune]
		if not gasita:
			return cu_stare(False, _t("Acțiunea aleasă nu e una dintre cele de pe televizor."))
		actiune = gasita[0]
	intreaba = argumente.get("intreaba")
	if intreaba is not None and intreaba not in ("0", "1"):
		return cu_stare(False, _t("Se alege cu intreaba=1 sau intreaba=0."))
	# ca tastele verde si galben ale ecranului (valoarea pusa -> notificatorii), apoi ca OK (save, temporizatorul)
	if actiune is not None and c.action.value != actiune:
		c.action.value = actiune
	if intreaba is not None and bool(c.ask.value) != (intreaba == "1"):
		c.ask.value = intreaba == "1"
	A.porneste(nav, minute, config)
	_mc().salveazaSetari(configfile)
	return cu_stare(True, _t("The sleep timer has been activated."))


def _intrebare(ce):
	"""Intrebarea de pe televizor (TryQuitMainloop) pentru fiecare actiune; standby-ul nu are una pe televizor."""
	if ce == "standby":
		return _t("Pui receptorul în standby acum?")
	if ce == "oprire":
		return _t("Really shutdown now?")
	if ce == "receptor":
		return _t("Really reboot now?")
	return _t("Really restart now?")


def _buton(ce):
	if ce == "standby":
		return _t("Da, pune în standby")
	if ce == "oprire":
		# alt text decat la oprirea swap-ului (disc_web): in unele limbi verbul difera (es apagar, it spegni)
		return _t("Da, oprește receptorul")
	return _t("Da, repornește")


def _detalii(ce, r):
	"""Ce trebuie stiut inainte de Da: inregistrarile, lucrarile, intrebarea care urmeaza pe televizor."""
	d = []
	if r.get("inregistrari"):
		d.append(_t("Înregistrări în curs: %d.") % r["inregistrari"])
	if r.get("curand"):
		d.append(_t("O înregistrare începe în mai puțin de 6 minute."))
	if r.get("lucrari"):
		d.append(_t("Lucrări în fundal: %d.") % r["lucrari"])
	if ce == "standby":
		if r.get("inregistrari") or r.get("curand"):
			d.append(_t("Înregistrările continuă și în standby."))
		return d
	if r.get("va_intreba"):
		d.append(_t("Pe televizor apare apoi aceeași întrebare: se face numai după ce răspunzi Da acolo sau, la o "
			"înregistrare, singur, după ce se termină."))
		if r.get("standby"):
			d.append(_t("Receptorul e în standby, deci întrebarea de pe televizor nu se vede până nu îl pornești."))
	if ce == "oprire":
		d.append(_t("Receptorul se pornește din nou din butonul de pornire al telecomenzii."))
	elif ce in ("interfata", "receptor"):
		d.append(_t("Pagina se reîncarcă singură când receptorul răspunde din nou."))
	return d


def _dupa(ce, intreaba, imagine=""):
	if intreaba:
		return _t("Pe televizor se cere o confirmare: o înregistrare e în curs sau începe curând, sau lucrează ceva în "
			"fundal. Se face numai dacă răspunzi Da acolo.")
	if ce == "standby":
		return _t("Receptorul trece în standby.")
	if ce == "interfata":
		return _t("Interfața se repornește. Pagina se reîncarcă singură în câteva secunde.")
	if ce == "receptor":
		return _t("Receptorul se repornește. Pagina se reîncarcă singură când răspunde din nou.")
	if ce == "flash":
		return _t("Receptorul repornește în imaginea %s. Interfața web de aici răspunde din nou când pornești înapoi "
			"imaginea HD Satelit.") % imagine
	return _t("Receptorul se oprește.")


def fa(argumente, A=None, sesiune=None, SystemInfo=None, Standby=None, job_manager=None, fabrica_ceas=None, PM=None):
	"""POST /api/alimentare-fa: standby, repornirile si oprirea, in doi pasi. Refuzul pentru ?token= il da resursa."""
	A = _a(A)
	SI = _si(SystemInfo)
	MC = _mc()
	ce = argumente.get("ce", "")
	if ce == "flash":
		return _faImagine(argumente, PM, sesiune, SI, Standby, job_manager, fabrica_ceas, A)
	if ce not in A.CHEI:
		return {"result": False, "message": _t("Acțiune necunoscută.")}
	pas = argumente.get("pas", "")
	if pas == "renunta":
		MC.uita(CONFIRMARE, ce)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if sesiune is None:
		return {"result": False, "message": _faraSesiune()}
	S = _standby(Standby)
	if ce == "standby" and S.inStandby is not None:
		MC.uita(CONFIRMARE, ce)
		return {"result": False, "message": _t("Receptorul este deja în standby.")}
	if ce != "standby" and getattr(S, "inTryQuitMainloop", False):
		MC.uita(CONFIRMARE, ce)
		return {"result": False, "message": _t("Pe televizor așteaptă deja o întrebare de oprire sau de repornire. "
			"Răspunde acolo.")}
	if pas == "intreaba":
		r = A.stareReceptor(sesiune, Standby=S, job_manager=job_manager)
		return MC.raspunsIntrebare(CONFIRMARE, ce, _intrebare(ce), _buton(ce), _detalii(ce, r))
	if not MC.verifica(CONFIRMARE, ce, argumente.get("cod", "")):
		return MC.codGresit()
	intreaba = ce != "standby" and A.vaIntreba(sesiune)
	A.deschide(sesiune, ce, dupa_ms=DUPA_MS, Standby=Standby, fabrica_ceas=fabrica_ceas)
	return {"result": True, "ce": ce, "intreaba": bool(intreaba), "message": _dupa(ce, intreaba)}


def rute(baza, resource, A=None, sesiune=None, config=None, SystemInfo=None, Standby=None, job_manager=None,
		fabrica_ceas=None, configfile=None, PM=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py; `sesiune` e o
	functie care intoarce sesiunea enigma2 (implicit cea tinuta de plugin.py)."""
	MC = _mc()

	def _ses():
		try:
			return sesiune() if sesiune is not None else MC.sesiune()
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/alimentare: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(A, _ses(), config, SystemInfo, Standby, job_manager))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class SomnResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				arg = MC.argumente(request, CHEI_SOMN, 16)
				return self._raspunde(request, somn(arg, A, _ses(), config, SystemInfo, Standby, job_manager,
					configfile))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class FaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			refuz = MC.numaiBrowser(request)
			if refuz:
				return self._eroare(request, refuz, 403)
			try:
				arg = MC.argumente(request, CHEI_FA, 40)
				return self._raspunde(request, fa(arg, A, _ses(), SystemInfo, Standby, job_manager, fabrica_ceas, PM))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # cu ?token= refuzat; din browser poarta cere POST

	class ImaginiResource(baza):
		"""GET /api/pornire-multipla: numai citire (monteaza partitia userdata pentru o clipa)."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, imagini(PM, SystemInfo))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /alimentare: pagina Standby si repornire."""
		isLeaf = True

		def render_GET(self, request):
			return MC.pagina(request, pagina_text)

	api = {
		b"alimentare": StareResource(),
		b"alimentare-somn": SomnResource(),
		b"alimentare-fa": FaResource(),
		b"pornire-multipla": ImaginiResource(),
	}
	return api, {b"alimentare": PaginaResource()}


def pagina_text(stil, config_pagina):
	MC = _mc()
	inlocuiri = {"__DRUM_MENIU__": MC.drumHtml("standby_restart_list")}
	for card, intrare in INTRARI.items():
		inlocuiri["__DRUM_%s__" % card.upper()] = MC.drumHtml(intrare)
	return MC.sablon(_traducePagina(PAGINA), stil, config_pagina, inlocuiri)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Standby și repornire</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .rand input[type=number]{width:100%;}
</style>
</head>
<body>
<main>
<h1>Standby și repornire</h1>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card" id="cardStare">
    <h2>Receptorul acum</h2>
    <div class="status-linie"><span>Starea</span><span id="stStare">-</span></div>
    <div class="status-linie"><span>Înregistrări în curs</span><span id="stInregistrari">-</span></div>
    <div class="status-linie"><span>Următoarea înregistrare</span><span id="stUrmatoarea">-</span></div>
    <div class="status-linie"><span>Lucrări în fundal</span><span id="stLucrari">-</span></div>
    <div class="status-linie"><span>Oprire programată</span><span id="stSomn">-</span></div>
  </section>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <div id="carduri">
    <section class="card" id="card-somn">
      <h2>Oprire programată</h2>
      <div class="status-linie"><span>Starea temporizatorului</span><span id="somnStare">-</span></div>
      <div class="rand">
        <label for="minute">Oprire receptor după (minute)</label>
        <input type="number" id="minute" min="1" step="1" inputmode="numeric">
      </div>
      <div class="rand">
        <label for="actiune">Acțiunea temporizatorului de oprire</label>
        <select id="actiune"></select>
      </div>
      <div class="rand">
        <label for="intreaba">Întreabă înainte de oprire</label>
        <select id="intreaba"><option value="1">Da</option><option value="0">Nu</option></select>
      </div>
      <div class="butoane">
        <button type="button" class="principal" id="somnPorneste">Activare temporizator</button>
        <button type="button" id="somnOpreste">Dezactivare temporizator</button>
        <button type="button" id="somnCanal">Folosire ora canalului curent</button>
      </div>
      <p class="nota" id="somnNota">Minutele rămân propunerea de data viitoare. Ora canalului curent înseamnă minutele până la sfârșitul emisiunii sau al filmului de acum, plus două. Pe televizor: __DRUM_SOMN__.</p>
    </section>
    <section class="card" id="card-standby">
      <h2>Standby</h2>
      <p class="nota">Ecranul se stinge și canalul se oprește; înregistrările continuă. Receptorul se pornește din telecomandă. Pe televizor: __DRUM_STANDBY__.</p>
      <div class="butoane"><button type="button" data-fa="standby">Standby</button></div>
    </section>
    <section class="card" id="card-interfata">
      <h2>Repornește interfața</h2>
      <p class="nota">Repornește numai programul receptorului (interfața); canalul revine după câteva secunde. Pe televizor: __DRUM_INTERFATA__.</p>
      <div class="butoane"><button type="button" class="rosu" data-fa="interfata">Repornește interfața</button></div>
    </section>
    <section class="card" id="card-receptor">
      <h2>Repornește receptorul</h2>
      <p class="nota">Repornește tot receptorul; durează mai mult decât repornirea interfeței. Pe televizor: __DRUM_RECEPTOR__.</p>
      <div class="butoane"><button type="button" class="rosu" data-fa="receptor">Repornește receptorul</button></div>
    </section>
    <section class="card ascuns" id="card-flash">
      <h2>Pornește alte imagini</h2>
      <p class="nota" id="imaginiNota">Caut imaginile instalate...</p>
      <div id="imaginiLista"></div>
      <p class="nota">Receptorul repornește în imaginea aleasă din memoria lui. Pe receptor: __DRUM_FLASH__.</p>
    </section>
    <section class="card" id="card-oprire">
      <h2>Oprire completă</h2>
      <p class="nota">Receptorul se oprește de tot și se pornește din nou din butonul de pornire al telecomenzii. Pe televizor: __DRUM_OPRIRE__.</p>
      <div class="butoane"><button type="button" class="rosu" data-fa="oprire">Oprire completă</button></div>
    </section>
  </div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>__SCRIPT_COMUN__
var D = null, minuteAtinse = false, asteapta = false;
function ora(t){
  if(!t){ return ""; }
  return new Date(t * 1000).toLocaleString("ro-RO", {weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"});
}
function scrie(id, text){ $(id).textContent = text; }
function textSomn(s){
  if(!s){ return "-"; }
  if(!s.activ){ return "Dezactivat"; }
  return "Activat: " + s.text_actiune + " peste " + s.minute + " min" + (s.ora ? " (" + ora(s.ora) + ")" : "");
}
function arata(d){
  D = d;
  var r = d.receptor || {};
  scrie("stStare", r.standby ? "În standby" : "Pornit");
  scrie("stInregistrari", String(r.inregistrari || 0));
  scrie("stUrmatoarea", r.urmatoarea ? ora(r.urmatoarea) : "Niciuna");
  scrie("stLucrari", String(r.lucrari || 0));
  scrie("stSomn", d.somn ? textSomn(d.somn) : "-");
  var s = d.somn;
  ["somnPorneste", "somnOpreste", "minute", "actiune", "intreaba"].forEach(function(id){ $(id).disabled = !s; });
  $("minute").min = String(d.minute_min || 1);
  $("minute").max = String(d.minute_max || 9999);
  if(s){
    scrie("somnStare", s.activ ? "Activat" : "Dezactivat");
    if(document.activeElement !== $("actiune")){
      var a = $("actiune"); a.textContent = "";
      (d.actiuni_somn || []).forEach(function(x){ var o = document.createElement("option"); o.value = x[0]; o.textContent = x[1]; a.appendChild(o); });
      a.value = s.actiune;
    }
    if(document.activeElement !== $("intreaba")){ $("intreaba").value = s.intreaba ? "1" : "0"; }
    if(!minuteAtinse && document.activeElement !== $("minute")){ $("minute").value = String(s.activ ? s.minute : s.minute_propuse); }
    $("somnCanal").disabled = s.minute_canal === null || s.minute_canal === undefined;
  } else {
    scrie("somnStare", "Se poate pune după pornirea completă a receptorului.");
    $("somnCanal").disabled = true;
  }
  (d.carduri || []).forEach(function(c){ var e = $("card-" + c.ce); if(e){ e.classList.toggle("ascuns", !c.vizibil); } });
  if(!imaginiCitite && !$("card-flash").classList.contains("ascuns")){ citesteImagini(); }
  var b = document.querySelector("button[data-fa=standby]"); if(b){ b.disabled = !!r.standby; }
}
var imaginiCitite = false;
function citesteImagini(){
  imaginiCitite = true;
  cerere("/api/pornire-multipla").then(function(d){
    var l = $("imaginiLista"); l.textContent = "";
    $("imaginiNota").textContent = d.result ? d.nota : (d.message || "");
    (d.locuri || []).forEach(function(x, i){
      var r = document.createElement("div"); r.className = "status-linie";
      var s = document.createElement("span"); s.textContent = (d.randuri || [])[i] || x.imagine; r.appendChild(s);
      if(x.alegere){
        var b = document.createElement("button"); b.type = "button"; b.className = "rosu"; b.textContent = "Pornește";
        b.addEventListener("click", function(){ faImagine(x.loc); }); r.appendChild(b);
      }
      l.appendChild(r);
    });
  }).catch(function(){ $("imaginiNota").textContent = "Receptorul nu a putut citi starea."; });
}
function faImagine(loc){
  var q = new URLSearchParams(); q.set("ce", "flash"); q.set("loc", loc);
  cuConfirmare("/api/alimentare-fa", q, function(d){
    if(d.result && d.intreaba){ setTimeout(citeste, 3000); }
    else if(d.result){ asteapta = true; }
  });
}
function citeste(){
  return cerere("/api/alimentare").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ if(!asteapta){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; } });
}
function somn(fapta){
  var q = new URLSearchParams(); q.set("fapta", fapta);
  if(fapta === "porneste"){ q.set("minute", $("minute").value.trim()); q.set("actiune", $("actiune").value); q.set("intreaba", $("intreaba").value); }
  mesaj("Se trimite...");
  cerere("/api/alimentare-somn", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ minuteAtinse = false; }
    if(d.receptor){ arata(d); }
  }).catch(nimicNuRaspunde);
}
function asteaptaRevenirea(){
  // interfata se opreste la 1,5 s dupa raspuns; dupa ce nu mai raspunde si raspunde iar, pagina se reincarca
  asteapta = true;
  var cazut = false, pornit = Date.now();
  function incearca(){
    fetch(adresa("/api/alimentare"), {cache: "no-store", credentials: "same-origin"}).then(function(r){
      if(cazut || Date.now() - pornit > 90000){ location.reload(); return; }
      setTimeout(incearca, 3000);
    }).catch(function(){ cazut = true; setTimeout(incearca, 3000); });
  }
  setTimeout(incearca, 4000);
}
function fa(ce){
  var q = new URLSearchParams(); q.set("ce", ce);
  cuConfirmare("/api/alimentare-fa", q, function(d){
    if(!d.result){ return; }
    if((d.ce === "interfata" || d.ce === "receptor") && !d.intreaba){ asteaptaRevenirea(); }
    else if(d.ce === "standby" || d.intreaba){ setTimeout(citeste, 3000); }
  });
}
$("minute").addEventListener("input", function(){ minuteAtinse = true; });
$("somnPorneste").addEventListener("click", function(){ somn("porneste"); });
$("somnOpreste").addEventListener("click", function(){ somn("opreste"); });
$("somnCanal").addEventListener("click", function(){
  if(D && D.somn && D.somn.minute_canal !== null){ $("minute").value = String(D.somn.minute_canal); minuteAtinse = true; mesaj(""); }
});
Array.prototype.forEach.call(document.querySelectorAll("button[data-fa]"), function(b){
  b.addEventListener("click", function(){ fa(b.getAttribute("data-fa")); });
});
(function(){
  var f = new URLSearchParams(location.search).get("f");
  var card = f && /^[a-z]{3,12}$/.test(f) ? $("card-" + f) : null;
  if(card){ $("carduri").insertBefore(card, $("carduri").firstChild); }
  citeste().then(function(){ if(card && !card.classList.contains("ascuns")){ card.scrollIntoView({block: "start"}); } });
})();
setInterval(function(){ if(!asteapta){ citeste(); } }, 10000);
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
		N_("Standby și repornire"),
		N_("Se citește starea..."),
		N_("Receptorul acum"),
		N_("Starea"),
		N_("Înregistrări în curs"),
		N_("Următoarea înregistrare"),
		N_("Lucrări în fundal"),
		N_("Oprire programată"),
		N_("Starea temporizatorului"),
		N_("Oprire receptor după (minute)"),
		N_("Acțiunea temporizatorului de oprire"),
		N_("Întreabă înainte de oprire"),
		N_("Da"),
		N_("Nu"),
		N_("Activare temporizator"),
		N_("Dezactivare temporizator"),
		N_("Folosire ora canalului curent"),
		N_("Minutele rămân propunerea de data viitoare. Ora canalului curent înseamnă minutele până la "
			"sfârșitul emisiunii sau al filmului de acum, plus două. Pe televizor: __DRUM_SOMN__."),
		N_("Standby"),
		N_("Ecranul se stinge și canalul se oprește; înregistrările continuă. Receptorul se pornește din "
			"telecomandă. Pe televizor: __DRUM_STANDBY__."),
		N_("Repornește interfața"),
		N_("Repornește numai programul receptorului (interfața); canalul revine după câteva secunde. Pe "
			"televizor: __DRUM_INTERFATA__."),
		N_("Repornește receptorul"),
		N_("Repornește tot receptorul; durează mai mult decât repornirea interfeței. Pe televizor: "
			"__DRUM_RECEPTOR__."),
		N_("Pornește alte imagini"),
		N_("Caut imaginile instalate..."),
		N_("Receptorul repornește în imaginea aleasă din memoria lui. Pe receptor: __DRUM_FLASH__."),
		N_("Oprire completă"),
		N_("Receptorul se oprește de tot și se pornește din nou din butonul de pornire al telecomenzii. Pe "
			"televizor: __DRUM_OPRIRE__."),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("Dezactivat"),
		N_("Activat:"),
		N_("peste"),
		N_("În standby"),
		N_("Pornit"),
		N_("Niciuna"),
		N_("Activat"),
		N_("Se poate pune după pornirea completă a receptorului."),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Pornește"),
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

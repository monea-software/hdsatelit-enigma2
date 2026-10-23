# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# parental_web.py: Control parental in interfata web (HdsWebControl). Orice ecran de pe receptor are pereche in web.
#
# Pe televizor: Meniu > Setari > Sistem & Dispozitive > Control parental (Screens/ParentalControlSetup.py, cu
# editoarele de canale si de buchete si schimbarea PIN-urilor). Aici: aceleasi randuri, aratate dupa aceleasi reguli,
# aceleasi config.ParentalControl.*, aceleasi liste (parentalControl din Components/ParentalControl.py). Regulile sunt
# scrise o singura data in Components/HdsControlParental.py.
#
# PIN-ul: cand ecranul de pe televizor cere PIN-ul setarilor la deschidere (Protect setup si Enable parental control
# pornite), pagina il cere si ea inainte sa arate sau sa schimbe ceva, cu aceleasi 3 incercari si aceleasi 15 minute
# de asteptare, numarate impreuna cu televizorul (config.ParentalControl.retries.setuppin). Un PIN bun da paginii un
# bilet (aleator, 10 minute de la ultima folosire, legat de browserul care l-a primit), trimis apoi in antetul
# X-HDS-Bilet; o pagina incarcata din nou cere iar PIN-ul, ca ecranul deschis din nou. PIN-urile nu pleaca niciodata
# spre browser si se primesc numai din corpul cererii (scrise in adresa se ignora).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/control-parental              starea: fara bilet, cand e cerut, numai ca e protejat si incercarile
#   POST /api/control-parental-pin          pin=NNNN -> biletul
#   POST /api/control-parental-seteaza      una din configured, setuppinactive, servicepinactive (0|1), type,
#                                           storeservicepin, storeservicepincancel; pin_nou=&pin_nou2= cand se porneste
#                                           o protectie fara PIN (ca la iesirea din ecran)
#   POST /api/control-parental-pin-nou      fel=setari|canale, pin_vechi= (cand exista unul), pin_nou=, pin_nou2=
#   GET  /api/control-parental-liste        fel=canale[&litera=a] | fel=buchete
#   POST /api/control-parental-blocheaza    fel=canale|buchete, ref=<referinta>, blocat=0|1
#   POST /api/control-parental-reincarca    Reload Black-/Whitelists
#   GET  /control-parental                  pagina
#
# FIRUL: totul pe firul enigma2, scurt; listele de canale se citesc ca in editorul de pe televizor (o lista a
# serviciilor TV). Fisierul nu importa nimic din enigma2 la incarcare.

import time

DURATA_BILET_S = 600
MAX_BILETE = 16
ANTET_BILET = b"x-hds-bilet"

_BILETE = {}


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _M():
	from . import meniu_comun_web
	return meniu_comun_web


def _jurnal(text):
	print("[HdsWebControl] parental: %s" % text)


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsControlParental
	return HdsControlParental


def _pc(pc=None):
	if pc is not None:
		return pc
	from Components.ParentalControl import parentalControl
	return parentalControl


def _bool(text):
	return {"1": True, "0": False}.get(text)


# ------------------------------------------------------------------ biletele
def _curata(acum):
	for b in [b for b, (_c, expira) in _BILETE.items() if expira < acum]:
		_BILETE.pop(b, None)
	while len(_BILETE) >= MAX_BILETE:
		_BILETE.pop(min(_BILETE.items(), key=lambda kv: kv[1][1])[0], None)


def biletNou(cine, acum=None):
	import binascii
	import os
	acum = time.monotonic() if acum is None else acum
	_curata(acum)
	bilet = binascii.hexlify(os.urandom(16)).decode("ascii")
	_BILETE[bilet] = (cine, acum + DURATA_BILET_S)
	return bilet


def biletBun(bilet, cine, acum=None):
	"""True pentru un bilet dat aceluiasi browser, inca valabil; folosirea il prelungeste."""
	import hmac
	acum = time.monotonic() if acum is None else acum
	_curata(acum)
	if not bilet or len(bilet) != 32:
		return False
	x = _BILETE.get(bilet)
	if x is None or not hmac.compare_digest(x[0].encode("utf-8"), cine.encode("utf-8")):
		return False
	_BILETE[bilet] = (cine, acum + DURATA_BILET_S)
	return True


def _cine(request):
	"""Browserul cererii: amprenta secretului sesiunii (cookie sau browser intrat fara cod), "jeton" pentru scripturi."""
	try:
		import hashlib
		from . import plugin as P
		if P.PARAM_JETON in request.args and P._jetonValid(request):
			return "jeton"
		secret, _browser = P._sesiuneDinCerere(request)
		if secret:
			return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:24]
	except Exception as eroare:
		_jurnal("browserul cererii: %r" % eroare)
	return ""


def _biletDinCerere(request, din_adresa):
	try:
		v = request.getHeader(ANTET_BILET)
	except Exception:
		v = None
	if isinstance(v, bytes):
		v = v.decode("ascii", "replace")
	if v:
		return v.strip()[:64]
	if "bilet" in din_adresa:
		return ""
	return _M().argumente(request, ("bilet",), 64).get("bilet", "")


# ------------------------------------------------------------------ starea
def _alegeri(el):
	from .setari_web import _alegeri as a
	return a(el, "alegere")


def stare(c, deblocat=True, acum=None, H=None):
	"""GET /api/control-parental. Fara bilet, cand ecranul cere PIN-ul: numai ca e protejat si incercarile."""
	H = _h(H)
	acum = time.time() if acum is None else acum
	rez = {"result": True, "protejat": H.protejat(c), "deblocat": bool(deblocat or not H.protejat(c))}
	if not rez["deblocat"]:
		ramase, asteapta = H.stareIncercari(c.retries.setuppin, acum)
		rez.update(incercari=ramase, asteapta_s=asteapta)
		return rez
	rez.update(randuri=H.randuri(c), configured=bool(c.configured.value), setuppinactive=bool(c.setuppinactive.value),
		servicepinactive=bool(c.servicepinactive.value), type=str(c.type.value), tipuri=_alegeri(c.type),
		storeservicepin=str(c.storeservicepin.value), storeservicepincancel=str(c.storeservicepincancel.value),
		pastrare=_alegeri(c.storeservicepin), pastrare_renuntare=_alegeri(c.storeservicepincancel), mode=str(c.mode.value),
		pin_setari_setat=H.pinSetat(c.setuppin), pin_canale_setat=H.pinSetat(c.servicepin[0]))
	return rez


def _refuzPin(c, acum, H):
	rez = stare(c, False, acum, H)
	rez.update(result=False, message=_t("Scrie întâi PIN-ul setărilor."))
	return rez


def _mesajAsteptare(secunde):
	return _t("Prea multe încercări greșite. Încearcă din nou peste %d minute.") % max(1, (secunde + 59) // 60)


def intraCuPin(arg, din_adresa, c, cine, acum=None, H=None):
	"""POST /api/control-parental-pin: PIN-ul setarilor, ca la deschiderea ecranului pe televizor."""
	H = _h(H)
	acum = time.time() if acum is None else acum
	if not H.protejat(c):
		rez = stare(c, True, acum, H)
		rez.update(message="", bilet="")
		return rez
	pin = "" if "pin" in din_adresa else arg.get("pin", "")
	if not H.pinBun(pin):
		# pe televizor PIN-ul se trimite singur dupa a patra cifra: altceva nu e o incercare
		rez = stare(c, False, acum, H)
		rez.update(result=False, message=_t("PIN-ul are 4 cifre."))
		return rez
	bun, ramase, asteapta = H.verificaPin(c.retries.setuppin, pin, [c.setuppin.value], acum)
	if bun is None:
		rez = stare(c, False, acum, H)
		rez.update(result=False, message=_mesajAsteptare(asteapta))
		return rez
	if not bun:
		rez = stare(c, False, acum, H)
		if ramase:
			rez.update(result=False, message=_t("PIN-ul e greșit. Încercări rămase: %d.") % ramase)
		else:
			rez.update(result=False, message=_t("PIN-ul e greșit.") + " " + _mesajAsteptare(asteapta))
		_jurnal("PIN gresit pentru control parental din web (%d incercari ramase)" % ramase)
		return rez
	rez = stare(c, True, acum, H)
	rez.update(message="", bilet=biletNou(cine))
	return rez


def seteaza(arg, din_adresa, c, cine, configfile=None, acum=None, H=None):
	"""POST /api/control-parental-seteaza: o singura setare pe cerere, numai pe un rand care se vede pe televizor."""
	H = _h(H)
	acum = time.time() if acum is None else acum
	chei = [k for k in H.SETARI if k in arg]
	if len(chei) != 1:
		rez = stare(c, True, acum, H)
		rez.update(result=False, message=_t("Nu s-a trimis nicio setare."))
		return rez
	cheie = chei[0]
	el = getattr(c, cheie)
	if cheie not in H.randuri(c):
		rez = stare(c, True, acum, H)
		rez.update(result=False, message=_t("Rândul acesta nu se vede acum pe televizor."))
		return rez
	text = arg[cheie]
	if cheie in ("configured", "setuppinactive", "servicepinactive"):
		v = _bool(text)
	else:
		v = text if text in [a[0] for a in _alegeri(el)] else None
	if v is None:
		rez = stare(c, True, acum, H)
		rez.update(result=False, message=_t("Valoarea aleasă nu e una de pe televizor."))
		return rez
	pin_pus = False
	if v is True and H.pinLipsa(c, cheie):
		# ca la iesirea din ecranul de pe televizor: fara PIN, protectia nu ramane pornita
		nou = "" if "pin_nou" in din_adresa else arg.get("pin_nou", "")
		nou2 = "" if "pin_nou2" in din_adresa else arg.get("pin_nou2", "")
		if not (H.pinBun(nou) and nou == nou2):
			rez = stare(c, True, acum, H)
			rez.update(result=False, cere_pin=True, message=_t("Nu există încă un PIN. Scrie PIN-ul nou, din 4 cifre, de "
				"două ori; fără el, protecția rămâne oprită."))
			return rez
		H.puneNou(H.elementPin(c, "setari" if cheie == "setuppinactive" else "canale"), nou)
		pin_pus = True
	protejat_inainte = H.protejat(c)
	if el.value != v:
		el.value = v
	el.save()
	_M().salveazaSetari(configfile)
	rez = stare(c, True, acum, H)
	rez.update(message=_t("PIN-ul a fost pus. Salvat.") if pin_pus else _t("Salvat."))
	if H.protejat(c) and not protejat_inainte:
		# ecranul ramane deschis pe televizor dupa ce pornesti protectia; pagina la fel
		rez["bilet"] = biletNou(cine)
	return rez


def pinNou(arg, din_adresa, c, configfile=None, acum=None, H=None):
	"""POST /api/control-parental-pin-nou: ca Change setup PIN / Change service PIN."""
	H = _h(H)
	acum = time.time() if acum is None else acum
	fel = arg.get("fel", "")
	rand = {"setari": "pin_setari", "canale": "pin_canale"}.get(fel)

	def refuz(mesaj):
		rez = stare(c, True, acum, H)
		rez.update(result=False, message=mesaj)
		return rez

	if rand is None or rand not in H.randuri(c):
		return refuz(_t("Rândul acesta nu se vede acum pe televizor."))
	if fel == "canale" and c.mode.value != "simple":
		return refuz(_t("În modul complex, schimbarea PIN-urilor canalelor nu face nimic nici pe televizor."))
	secrete = dict((k, "" if k in din_adresa else arg.get(k, "")) for k in ("pin_vechi", "pin_nou", "pin_nou2"))
	if not H.pinBun(secrete["pin_nou"]):
		return refuz(_t("PIN-ul nou are 4 cifre."))
	if secrete["pin_nou"] != secrete["pin_nou2"]:
		return refuz(_t("Cele două PIN-uri noi nu sunt la fel."))
	el = H.elementPin(c, fel)
	if H.pinSetat(el):
		if not H.pinBun(secrete["pin_vechi"]):
			return refuz(_t("Scrie și PIN-ul vechi, din 4 cifre."))
		bun, ramase, asteapta = H.verificaPin(c.retries.setuppin, secrete["pin_vechi"], [el.value], acum)
		if bun is None:
			return refuz(_mesajAsteptare(asteapta))
		if not bun:
			if ramase:
				return refuz(_t("PIN-ul vechi e greșit. Încercări rămase: %d.") % ramase)
			return refuz(_t("PIN-ul vechi e greșit.") + " " + _mesajAsteptare(asteapta))
	H.puneNou(el, secrete["pin_nou"])
	_M().salveazaSetari(configfile)
	_jurnal("PIN-ul %s schimbat din web" % ("setarilor" if fel == "setari" else "canalelor"))
	rez = stare(c, True, acum, H)
	rez.update(message=_t("PIN-ul a fost schimbat."))
	return rez


# ------------------------------------------------------------------ listele
def _intrari(H, pc, lista):
	rez = []
	for ref, nume in lista:
		blocat, fel = H.protectie(pc, ref)
		rez.append({"ref": ref, "nume": nume, "blocat": blocat, "fel": fel})
	return rez


def liste(arg, c, pc=None, H=None, canale=None, buchete=None):
	"""GET /api/control-parental-liste: canalele pe litere (ca editorul de pe televizor) sau buchetele."""
	H = _h(H)
	pc = _pc(pc)
	fel = arg.get("fel", "")
	rand = {"canale": "lista_canale", "buchete": "lista_buchete"}.get(fel)
	if rand is None or rand not in H.randuri(c):
		return {"result": False, "message": _t("Rândul acesta nu se vede acum pe televizor.")}
	rez = {"result": True, "fel": fel, "tip": str(c.type.value)}
	if fel == "buchete":
		rez["intrari"] = _intrari(H, pc, buchete() if buchete is not None else H.buchete())
		return rez
	toate = canale() if canale is not None else H.canale()
	grupe = {}
	for ref, nume in toate:
		grupe.setdefault(H.litera(nume), []).append((ref, nume))
	litere = sorted(grupe, key=lambda k: "" if k == H.SPECIAL else k)
	rez["litere"] = [{"litera": k, "numar": len(grupe[k])} for k in litere]
	litera = arg.get("litera", "")
	if litera not in grupe:
		litera = litere[0] if litere else ""
	rez["litera"] = litera
	rez["intrari"] = _intrari(H, pc, grupe.get(litera, []))
	return rez


def blocheaza(arg, c, pc=None, H=None, canale=None, buchete=None):
	"""POST /api/control-parental-blocheaza: un canal sau un buchet din lista, protejat sau nu (ca OK in editor)."""
	H = _h(H)
	pc = _pc(pc)
	fel = arg.get("fel", "")
	rand = {"canale": "lista_canale", "buchete": "lista_buchete"}.get(fel)
	if rand is None or rand not in H.randuri(c):
		return {"result": False, "message": _t("Rândul acesta nu se vede acum pe televizor.")}
	v = _bool(arg.get("blocat", ""))
	ref = arg.get("ref", "")
	if fel == "canale":
		lista = canale() if canale is not None else H.canale()
	else:
		lista = buchete() if buchete is not None else H.buchete()
	if v is None or ref not in dict(lista):
		return {"result": False, "message": _t("Canalul sau buchetul ales nu e în listă.")}
	blocat, de_unde = H.comuta(pc, ref, v)
	return {"result": True, "ref": ref, "blocat": blocat, "fel": de_unde, "message": _t("Salvat.")}


def reincarca(c, pc=None, H=None):
	"""POST /api/control-parental-reincarca: Reload Black-/Whitelists."""
	H = _h(H)
	if "reincarca" not in H.randuri(c):
		return {"result": False, "message": _t("Rândul acesta nu se vede acum pe televizor.")}
	_pc(pc).open()
	return {"result": True, "message": _t("Listele au fost citite din nou.")}


# ------------------------------------------------------------------ resursele
CHEI = ("pin", "configured", "setuppinactive", "servicepinactive", "type", "storeservicepin", "storeservicepincancel",
	"pin_nou", "pin_nou2", "pin_vechi", "fel", "litera", "ref", "blocat")


def _argumente(request):
	return _M().argumente(request, CHEI, 600)


def _dinAdresa(request):
	from .descarcare_subtitrari_web import _cheiDinAdresa
	return _cheiDinAdresa(request)


def rute(baza, resource, config=None, pc=None, H=None, configfile=None, canale=None, buchete=None, ceas=None):
	"""({nume: resursa de sub /api}, {nume: resursa pagina}); restul argumentelor sunt pentru probele de pe PC."""

	def _c():
		return _h(H).cp(config)

	def _acum():
		return ceas() if ceas is not None else time.time()

	def _resursa(functie, schimba, cu_bilet=True):
		class Resursa(baza):
			schimbaCeva = schimba

			def _fa(self, request):
				try:
					c = _c()
					din_adresa = _dinAdresa(request)
					cine = _cine(request)
					if cu_bilet and _h(H).protejat(c) and not biletBun(_biletDinCerere(request, din_adresa), cine):
						return self._raspunde(request, _refuzPin(c, _acum(), _h(H)))
					return self._raspunde(request, functie(request, c, din_adresa, cine))
				except Exception as eroare:
					_jurnal("%s: %r" % (functie.__name__, eroare))
					return self._eroare(request, _t("Eroare pe receptor."), 500)

			if schimba:
				def render_POST(self, request):
					return self._fa(request)

				def render_GET(self, request):
					return self._fa(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
			else:
				def render_GET(self, request):
					return self._fa(request)
		return Resursa()

	def f_stare(request, c, din_adresa, cine):
		return stare(c, biletBun(_biletDinCerere(request, din_adresa), cine), _acum(), H)

	def f_pin(request, c, din_adresa, cine):
		return intraCuPin(_argumente(request), din_adresa, c, cine, _acum(), H)

	def f_seteaza(request, c, din_adresa, cine):
		return seteaza(_argumente(request), din_adresa, c, cine, configfile, _acum(), H)

	def f_pin_nou(request, c, din_adresa, cine):
		return pinNou(_argumente(request), din_adresa, c, configfile, _acum(), H)

	def f_liste(request, c, din_adresa, cine):
		return liste(_argumente(request), c, pc, H, canale, buchete)

	def f_blocheaza(request, c, din_adresa, cine):
		return blocheaza(_argumente(request), c, pc, H, canale, buchete)

	def f_reincarca(request, c, din_adresa, cine):
		return reincarca(c, pc, H)

	api = {
		b"control-parental": _resursa(f_stare, False, False),
		b"control-parental-pin": _resursa(f_pin, True, False),
		b"control-parental-seteaza": _resursa(f_seteaza, True),
		b"control-parental-pin-nou": _resursa(f_pin_nou, True),
		b"control-parental-liste": _resursa(f_liste, False),
		b"control-parental-blocheaza": _resursa(f_blocheaza, True),
		b"control-parental-reincarca": _resursa(f_reincarca, True),
	}

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			return _M().pagina(request, pagina_text)

	return api, {b"control-parental": Pagina()}


def pagina_text(stil, config_pagina):
	M = _M()
	return M.sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": M.drumHtml("parental_setup")})


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Control parental</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .pin{letter-spacing:.4em;font-size:1.2rem;max-width:180px;}
  .litere{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px;}
  .litere button{min-width:44px;padding:8px 10px;}
  .litere button.aleasa{background:var(--accent);border-color:var(--accent);color:#fff;}
  .bifa{display:flex;align-items:center;gap:12px;min-height:44px;padding:4px 0;border-bottom:1px solid var(--bordura);cursor:pointer;}
  .bifa:last-child{border-bottom:0;}
  .bifa span{overflow-wrap:anywhere;}
  .bifa small{color:var(--text-slab);}
  .rand input{width:100%;}
</style>
</head>
<body>
<main>
<h1>Control parental</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<section class="card ascuns" id="cardPin">
  <h2>PIN-ul configurării</h2>
  <p class="intrebare">Configurarea e protejată. Introdu codul PIN corect, ca pe televizor.</p>
  <div class="rand"><label for="pin">PIN (4 cifre)</label>
    <input type="password" id="pin" class="pin" maxlength="4" inputmode="numeric" autocomplete="off" pattern="[0-9]*"></div>
  <div class="butoane"><button type="button" class="principal" id="deschide">Deschide</button></div>
  <p class="nota" id="incercari"></p>
</section>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Configurare control parental</h2>
    <div class="rand" data-rand="configured"><label for="configured">Activare control parental</label>
      <select id="configured"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand" data-rand="setuppinactive"><label for="setuppinactive">Protejare configurare</label>
      <select id="setuppinactive"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand" data-rand="servicepinactive"><label for="servicepinactive">Protejare canale</label>
      <select id="servicepinactive"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand" data-rand="type"><label for="type">Tipul controlului parental</label><select id="type"></select>
      <p class="ajutor nota">Lista neagră: cer PIN numai canalele din listă. Lista albă: cer PIN toate canalele, în afară de cele din listă.</p></div>
    <div class="rand" data-rand="storeservicepin"><label for="storeservicepin">Memorare PIN canale</label><select id="storeservicepin"></select>
      <p class="ajutor nota">Cât timp nu mai cere PIN-ul după ce l-ai scris bine pe un canal.</p></div>
    <div class="rand" data-rand="storeservicepincancel"><label for="storeservicepincancel">Anulare memorare PIN canale</label><select id="storeservicepincancel"></select>
      <p class="ajutor nota">Cât timp nu mai cere PIN-ul după ce ai renunțat să-l scrii pe un canal.</p></div>
    <div class="ascuns card" id="pinLipsa">
      <p class="intrebare">Nu există încă un PIN. Scrie PIN-ul nou de două ori; fără el, protecția rămâne oprită.</p>
      <div class="rand"><label for="lipsaNou">PIN nou</label><input type="password" id="lipsaNou" class="pin" maxlength="4" inputmode="numeric" autocomplete="new-password"></div>
      <div class="rand"><label for="lipsaNou2">Reintrodu PIN-ul nou</label><input type="password" id="lipsaNou2" class="pin" maxlength="4" inputmode="numeric" autocomplete="new-password"></div>
      <div class="butoane"><button type="button" class="principal" id="lipsaPune">Pune PIN-ul și pornește</button><button type="button" id="lipsaRenunta">Renunță</button></div>
    </div>
  </section>
  <section class="card" id="cardPinuri">
    <h2>PIN-uri</h2>
    <div class="butoane"><button type="button" data-rand="pin_setari" id="schimbaSetari">Schimbare PIN configurare</button>
      <button type="button" data-rand="pin_canale" id="schimbaCanale">Schimbare PIN canale</button></div>
    <div class="ascuns" id="formPin">
      <p class="intrebare" id="formPinTitlu"></p>
      <div class="rand" id="randVechi"><label for="pinVechi">Vechiul cod PIN</label><input type="password" id="pinVechi" class="pin" maxlength="4" inputmode="numeric" autocomplete="off"></div>
      <div class="rand"><label for="pinNou">PIN nou</label><input type="password" id="pinNou" class="pin" maxlength="4" inputmode="numeric" autocomplete="new-password"></div>
      <div class="rand"><label for="pinNou2">Reintrodu PIN-ul nou</label><input type="password" id="pinNou2" class="pin" maxlength="4" inputmode="numeric" autocomplete="new-password"></div>
      <div class="butoane"><button type="button" class="principal" id="pinSalveaza">Schimbă PIN-ul</button><button type="button" id="pinRenunta">Renunță</button></div>
    </div>
    <p class="nota" id="pinNota"></p>
  </section>
  <section class="card" id="cardListe">
    <h2>Canale și buchete</h2>
    <div class="butoane"><button type="button" data-rand="lista_canale" id="arataCanale">Editare listă de canale</button>
      <button type="button" data-rand="lista_buchete" id="arataBuchete">Editare listă de buchete</button>
      <button type="button" data-rand="reincarca" id="reincarca">Reîncărcare liste negre/albe</button></div>
    <div class="litere" id="litere"></div>
    <div id="intrari"></div>
    <p class="nota" id="listeNota"></p>
  </section>
  <p class="nota">PIN-urile nu se arată niciodată. Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
<p class="mesaj" id="mesaj"></p>
<div id="confirmare" class="card ascuns"></div>
</main>
<script>
__SCRIPT_COMUN__
var BILET = "", D = null, LISTA = "", LITERA = "", PIN_FEL = "", LIPSA = "";
function cerereP(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(BILET){ optiuni.headers["X-HDS-Bilet"] = BILET; }
  if(date){ optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded"; optiuni.body = date.toString(); }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function arataPin(d){
  $("incarcare").classList.add("ascuns"); $("continut").classList.add("ascuns"); $("cardPin").classList.remove("ascuns");
  var t = d.asteapta_s ? "Prea multe încercări greșite. Încearcă din nou peste " + Math.max(1, Math.ceil(d.asteapta_s / 60)) + " minute." : "Încercări rămase: " + d.incercari + ".";
  $("incercari").textContent = t;
  $("deschide").disabled = !!d.asteapta_s;
  $("pin").focus();
}
function alegeri(id, lista, valoare){
  var s = $(id);
  if(document.activeElement === s){ return; }
  s.textContent = "";
  (lista || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
  s.value = valoare;
}
function arata(d){
  if(d.bilet){ BILET = d.bilet; }
  if(d.protejat && !d.deblocat){ BILET = ""; arataPin(d); return; }
  D = d;
  $("cardPin").classList.add("ascuns"); $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var r = d.randuri || [];
  document.querySelectorAll("[data-rand]").forEach(function(x){ x.classList.toggle("ascuns", r.indexOf(x.getAttribute("data-rand")) === -1); });
  ["configured", "setuppinactive", "servicepinactive"].forEach(function(k){ if(document.activeElement !== $(k)){ $(k).value = d[k] ? "1" : "0"; } });
  alegeri("type", d.tipuri, d.type);
  alegeri("storeservicepin", d.pastrare, d.storeservicepin);
  alegeri("storeservicepincancel", d.pastrare_renuntare, d.storeservicepincancel);
  $("cardPinuri").classList.toggle("ascuns", r.indexOf("pin_setari") === -1 && r.indexOf("pin_canale") === -1);
  $("cardListe").classList.toggle("ascuns", r.indexOf("lista_canale") === -1);
  var n = [];
  if(r.indexOf("pin_setari") !== -1){ n.push(d.pin_setari_setat ? "PIN-ul configurării e pus." : "PIN-ul configurării nu e pus încă."); }
  if(r.indexOf("pin_canale") !== -1){ n.push(d.pin_canale_setat ? "PIN-ul canalelor e pus." : "PIN-ul canalelor nu e pus încă."); }
  if(d.mode === "complex"){ n.push("În modul complex, schimbarea PIN-urilor canalelor nu face nimic nici pe televizor."); }
  $("pinNota").textContent = n.join(" ");
  if(r.indexOf("lista_canale") === -1){ LISTA = ""; $("intrari").textContent = ""; $("litere").textContent = ""; }
}
function raspuns(d){
  if(d.message !== undefined){ mesaj(d.message, !d.result); }
  if(d.randuri || d.protejat !== undefined){ arata(d); }
  return d;
}
function citeste(){
  return cerereP("/api/control-parental").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, q){
  mesaj("Se salvează...");
  return cerereP(cale, "POST", q).then(raspuns).catch(nimicNuRaspunde);
}
$("deschide").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("pin", $("pin").value);
  $("pin").value = "";
  cerereP("/api/control-parental-pin", "POST", q).then(function(d){ mesaj(d.message, !d.result); arata(d); }).catch(nimicNuRaspunde);
});
$("pin").addEventListener("keydown", function(e){ if(e.key === "Enter"){ $("deschide").click(); } });
["configured", "setuppinactive", "servicepinactive", "type", "storeservicepin", "storeservicepincancel"].forEach(function(k){
  $(k).addEventListener("change", function(){
    var q = new URLSearchParams(); q.set(k, $(k).value);
    trimite("/api/control-parental-seteaza", q).then(function(d){
      if(d && d.cere_pin){ LIPSA = k; $("pinLipsa").classList.remove("ascuns"); $("lipsaNou").focus(); }
    });
  });
});
$("lipsaPune").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set(LIPSA, "1"); q.set("pin_nou", $("lipsaNou").value); q.set("pin_nou2", $("lipsaNou2").value);
  $("lipsaNou").value = ""; $("lipsaNou2").value = "";
  trimite("/api/control-parental-seteaza", q).then(function(d){ if(d && d.result){ $("pinLipsa").classList.add("ascuns"); } });
});
$("lipsaRenunta").addEventListener("click", function(){ $("pinLipsa").classList.add("ascuns"); $("lipsaNou").value = ""; $("lipsaNou2").value = ""; mesaj("Nu s-a făcut nimic."); });
function formPin(fel){
  PIN_FEL = fel;
  var setat = fel === "setari" ? D.pin_setari_setat : D.pin_canale_setat;
  $("formPinTitlu").textContent = fel === "setari" ? "Schimbare PIN configurare" : "Schimbare PIN canale";
  $("randVechi").classList.toggle("ascuns", !setat);
  $("formPin").classList.remove("ascuns");
  (setat ? $("pinVechi") : $("pinNou")).focus();
}
function golesteFormPin(){ ["pinVechi", "pinNou", "pinNou2"].forEach(function(k){ $(k).value = ""; }); }
$("schimbaSetari").addEventListener("click", function(){ formPin("setari"); });
$("schimbaCanale").addEventListener("click", function(){ formPin("canale"); });
$("pinRenunta").addEventListener("click", function(){ golesteFormPin(); $("formPin").classList.add("ascuns"); mesaj("Nu s-a făcut nimic."); });
$("pinSalveaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fel", PIN_FEL);
  q.set("pin_vechi", $("pinVechi").value); q.set("pin_nou", $("pinNou").value); q.set("pin_nou2", $("pinNou2").value);
  golesteFormPin();
  trimite("/api/control-parental-pin-nou", q).then(function(d){ if(d && d.result){ $("formPin").classList.add("ascuns"); } });
});
function arataLista(d){
  if(!d.result){ mesaj(d.message, true); if(d.protejat !== undefined){ arata(d); } return; }
  var l = $("litere"); l.textContent = "";
  (d.litere || []).forEach(function(x){
    var b = document.createElement("button"); b.type = "button"; b.textContent = (x.litera === "#" ? "Alte caractere" : x.litera.toUpperCase()) + " (" + x.numar + ")";
    b.classList.toggle("aleasa", x.litera === d.litera);
    b.addEventListener("click", function(){ LITERA = x.litera; incarcaLista(); });
    l.appendChild(b);
  });
  var c = $("intrari"); c.textContent = "";
  (d.intrari || []).forEach(function(x){
    var e = document.createElement("label"); e.className = "bifa";
    var k = document.createElement("input"); k.type = "checkbox"; k.checked = !!x.blocat;
    var s = document.createElement("span"); s.textContent = x.nume;
    var m = document.createElement("small");
    function semn(y){ m.textContent = y.fel === "buchet" && LISTA === "canale" ? " (prin buchet)" : (!y.blocat && y.fel ? " (în lista albă)" : ""); }
    semn(x);
    k.addEventListener("change", function(){
      var q = new URLSearchParams(); q.set("fel", LISTA); q.set("ref", x.ref); q.set("blocat", k.checked ? "1" : "0");
      cerereP("/api/control-parental-blocheaza", "POST", q).then(function(r){
        mesaj(r.message, !r.result);
        if(r.result){ k.checked = !!r.blocat; semn(r); } else { k.checked = !k.checked; if(r.protejat !== undefined){ arata(r); } }
      }).catch(nimicNuRaspunde);
    });
    e.appendChild(k); e.appendChild(s); s.appendChild(m); c.appendChild(e);
  });
  if(!(d.intrari || []).length){ c.appendChild(document.createTextNode("Lista e goală.")); }
  $("listeNota").textContent = d.tip === "whitelist"
    ? "Lista albă: bifat înseamnă că cere PIN. Debifat pune canalul sau buchetul în lista albă."
    : "Lista neagră: bifat înseamnă că cere PIN. Lista se salvează pe receptor la fiecare bifă.";
}
function incarcaLista(){
  var q = "/api/control-parental-liste?fel=" + LISTA + (LISTA === "canale" && LITERA ? "&litera=" + encodeURIComponent(LITERA) : "");
  $("intrari").textContent = "Se citește lista...";
  cerereP(q).then(arataLista).catch(nimicNuRaspunde);
}
$("arataCanale").addEventListener("click", function(){ LISTA = "canale"; incarcaLista(); });
$("arataBuchete").addEventListener("click", function(){ LISTA = "buchete"; LITERA = ""; $("litere").textContent = ""; incarcaLista(); });
$("reincarca").addEventListener("click", function(){
  trimite("/api/control-parental-reincarca", new URLSearchParams()).then(function(){ if(LISTA){ incarcaLista(); } });
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
		N_("Control parental"),
		N_("Se citesc setările..."),
		N_("PIN-ul configurării"),
		N_("Configurarea e protejată. Introdu codul PIN corect, ca pe televizor."),
		N_("PIN (4 cifre)"),
		N_("Deschide"),
		N_("Configurare control parental"),
		N_("Activare control parental"),
		N_("Da"),
		N_("Nu"),
		N_("Protejare configurare"),
		N_("Protejare canale"),
		N_("Tipul controlului parental"),
		N_("Lista neagră: cer PIN numai canalele din listă. Lista albă: cer PIN toate canalele, în afară de "
			"cele din listă."),
		N_("Memorare PIN canale"),
		N_("Cât timp nu mai cere PIN-ul după ce l-ai scris bine pe un canal."),
		N_("Anulare memorare PIN canale"),
		N_("Cât timp nu mai cere PIN-ul după ce ai renunțat să-l scrii pe un canal."),
		N_("Nu există încă un PIN. Scrie PIN-ul nou de două ori; fără el, protecția rămâne oprită."),
		N_("PIN nou"),
		N_("Reintrodu PIN-ul nou"),
		N_("Pune PIN-ul și pornește"),
		N_("Renunță"),
		N_("PIN-uri"),
		N_("Schimbare PIN configurare"),
		N_("Schimbare PIN canale"),
		N_("Vechiul cod PIN"),
		N_("Schimbă PIN-ul"),
		N_("Canale și buchete"),
		N_("Editare listă de canale"),
		N_("Editare listă de buchete"),
		N_("Reîncărcare liste negre/albe"),
		N_("PIN-urile nu se arată niciodată. Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Prea multe încercări greșite. Încearcă din nou peste"),
		N_("minute."),
		N_("Încercări rămase:"),
		N_("PIN-ul configurării e pus."),
		N_("PIN-ul configurării nu e pus încă."),
		N_("PIN-ul canalelor e pus."),
		N_("PIN-ul canalelor nu e pus încă."),
		N_("În modul complex, schimbarea PIN-urilor canalelor nu face nimic nici pe televizor."),
		N_("Receptorul nu a putut citi setările."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se salvează..."),
		N_("Nu s-a făcut nimic."),
		N_("Schimbare PIN configurare"),
		N_("Schimbare PIN canale"),
		N_("Alte caractere"),
		N_("(prin buchet)"),
		N_("(în lista albă)"),
		N_("Lista e goală."),
		N_("Lista albă: bifat înseamnă că cere PIN. Debifat pune canalul sau buchetul în lista albă."),
		N_("Lista neagră: bifat înseamnă că cere PIN. Lista se salvează pe receptor la fiecare bifă."),
		N_("Se citește lista..."),
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

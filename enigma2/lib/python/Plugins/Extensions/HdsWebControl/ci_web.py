# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Sloturile si setarile din Screens.Ci.CiSelection, prin poarta web comuna.

Se citesc stari deja pastrate in memorie. Nu se asteapta raspunsul modulului.
MMI are un singur consumator: getMMIScreen sterge semnul mmiScreenReady.
O citire web ar putea lua mesajul inaintea dialogului de pe televizor.

12.11.2026 (ca in enigma2 OE-Alliance, perechea ecranului de pe televizor): CI pornit/oprit pe slot (butonul
„Oprește slotul” / „Pornește slotul” schimba config.ci[n].enabled; nucleul inchide /dev/ciN), intarzierea DVB CI si
intarzierea pornirii CI (setari comune), codul PIN pastrat, mesajele CI, Relevant PIDs Routing, debitul extra_high.

12.11.2026, CI+ (din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, ca pe televizor):
starea CI+ pe slot, „Dezactivează profilurile operatorului”, „Opțiunile de decriptare”, „Ajutorul CI+” (numai cu
/usr/bin/ciplushelper) si cele patru fisiere ale aparatului (param, root.pem, customer.pem, device.pem) puse de om in
/etc/ciplus. Imaginea nu le are si nu le trimite nicaieri: se scriu numai pe receptor (0600), raspunsul nu le contine.
"""

import base64
import binascii
import json
import os

MAX_SLOTURI = 4
# setarile slotului din formular: numele din config.ci[n] -> textul randului de pe televizor
SETARI = {
	"use_static_pin": "Păstrează codul PIN",
	"show_ci_messages": "Arată mesajele CI",
	"canDescrambleMultipleServices": "Multiple service support",
	"canHandleHighBitrates": "High bitrate support",
	"relevantPidsRouting": "Relevant PIDs Routing",
}
# setarile CI+ ale slotului: numai cand certificatele aparatului sunt puse (fara ele n-ar schimba nimic), ca pe televizor
SETARI_CIPLUS = {
	"disable_operator_profile": "Dezactivează profilurile operatorului",
	"alternative_ca_handling": "Opțiunile de decriptare",
}
COMUNE = {
	"dvbCiDelay": "Întârzierea DVB CI",
	"bootDelay": "Întârzierea pornirii CI",
}
COMUNE_HELPER = {"cihelperenabled": "Ajutorul CI+ (cere repornirea receptorului)"}

# CI+: fisierele aparatului (lib/dvb_ci/dvbci_ccmgr_helper.cpp: param are 592 de octeti, parametrii DH si cheile;
# device.pem tine certificatul si cheia privata a aparatului)
CIPLUS_DOSAR = "/etc/ciplus"
CIPLUS_FISIERE = ("param", "root.pem", "customer.pem", "device.pem")
CIPLUS_PARAM_OCTETI = 592
CIPLUS_PEM_MAXIM = 64 * 1024


def ciplus_lipsa(dosar=None):
	dosar = dosar or CIPLUS_DOSAR
	return [nume for nume in CIPLUS_FISIERE if not os.access(os.path.join(dosar, nume), os.R_OK)]


def verifica_fisier_ciplus(nume, continut):
	"""Textul greselii, sau None cand fisierul are forma ceruta. Nu se verifica lantul (il verifica nucleul)."""
	if nume not in CIPLUS_FISIERE:
		return _t("Fișierul %s nu e unul dintre cele patru ale CI+ (param, root.pem, customer.pem, device.pem).") % nume
	if nume == "param":
		if len(continut) != CIPLUS_PARAM_OCTETI:
			return _t("Fișierul param trebuie să aibă exact %d de octeți.") % CIPLUS_PARAM_OCTETI
		return None
	if not continut or len(continut) > CIPLUS_PEM_MAXIM or b"-----BEGIN CERTIFICATE-----" not in continut:
		return _t("Fișierul %s nu conține un certificat PEM.") % nume
	if nume == "device.pem" and b"PRIVATE KEY-----" not in continut:
		return _t("Fișierul device.pem trebuie să conțină și cheia privată a aparatului.")
	return None


def scrie_fisier_ciplus(nume, continut, dosar=None):
	"""Scrie fisierul in /etc/ciplus: dosarul 0700, fisierul 0600, intai alaturi, apoi mutat peste cel vechi."""
	dosar = dosar or CIPLUS_DOSAR
	os.makedirs(dosar, mode=0o700, exist_ok=True)
	os.chmod(dosar, 0o700)
	tinta = os.path.join(dosar, nume)
	nou = os.path.join(dosar, "." + nume + ".nou")
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
	try:
		os.write(fd, continut)
		os.fsync(fd)
	finally:
		os.close(fd)
	os.chmod(nou, 0o600)
	os.replace(nou, tinta)


def sterge_fisiere_ciplus(dosar=None):
	"""Sterge certificatele si autentificarile tinute minte (ci_auth_slot_N.bin); modulul ramane CI simplu."""
	dosar = dosar or CIPLUS_DOSAR
	sterse = 0
	try:
		nume_toate = os.listdir(dosar)
	except OSError:
		return 0
	for nume in nume_toate:
		if nume in CIPLUS_FISIERE or (nume.startswith("ci_auth_slot_") and nume.endswith(".bin")):
			try:
				os.remove(os.path.join(dosar, nume))
				sterse += 1
			except OSError as eroare:
				print("[HdsWebControl] stergerea %s: %r" % (nume, eroare))
	return sterse


def _ciplus_ecran():
	"""Screens.Ci (textele si repornirea modulului, aceleasi ca pe televizor), sau None."""
	try:
		from Screens import Ci
		return Ci
	except Exception as eroare:
		print("[HdsWebControl] Screens.Ci: %r" % (eroare,))
		return None


def _ciplus_text_lipsa(lipsa):
	ecran = _ciplus_ecran()
	if ecran is not None and hasattr(ecran, "ciplusTextLipsa"):
		return ecran.ciplusTextLipsa(lipsa)
	return _t("Pentru CI+ sunt necesare certificatele aparatului în /etc/ciplus")


def _ciplus_reset(motiv):
	ecran = _ciplus_ecran()
	if ecran is not None and hasattr(ecran, "resetModuleCiplus"):
		ecran.resetModuleCiplus(motiv)


def _ciplus_slot(ui, slot, lipsa):
	if lipsa:
		return _t("CI+: lipsesc certificatele aparatului")
	try:
		cod = ui.getCIPlusState(slot)
	except Exception:
		cod = 0
	return {2: _t("CI+: autentificat, descifrare CI+"), 1: _t("CI+: autentificare în curs")}.get(
		cod, _t("CI+: certificatele sunt puse; modulul lucrează ca CI simplu"))


def _helper_pornit(config, sysinfo):
	"""Ca pe televizor: cu ajutorul CI+ extern pornit, Reset si Init sunt ale lui."""
	if not sysinfo.get("CIPlusHelper"):
		return False
	element = getattr(getattr(config, "cimisc", None), "cihelperenabled", None)
	return element is None or bool(element.value)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	return text


def _alocari():
	from Tools import CIHelper
	return CIHelper


def _slot_alocare(date, ui):
	"""Alocarile tin de slot, nu de modul: orice slot care exista (si cu modulul in initializare sau scos)."""
	text = date.get("slot", "")
	if text not in tuple(str(n) for n in range(MAX_SLOTURI)) or ui.getState(int(text)) == -1:
		raise ValueError("slot")
	return int(text)


def _oprit(config, slot):
	"""Slotul oprit = „CI pornit: Nu” (config.ci[n].enabled), ca pe televizor."""
	try:
		return not bool(config.ci[slot].enabled.value)
	except Exception as eroare:
		print("[HdsWebControl] starea slotului CI %d: %r" % (slot, eroare))
		return False


def alocare(date):
	ui, config, debit = _ci()
	try:
		slot = _slot_alocare(date, ui)
	except ValueError:
		return {"result": False, "message": _t("Modulul CI nu mai este pregătit.")}
	helper = _alocari()
	editor = helper.citesteEditor(slot)
	try:
		cunoscute = helper.caidCunoscute(slot)
	except Exception as eroare:
		print("[HdsWebControl] CAID-urile cunoscute: %r" % (eroare,))
		cunoscute = []
	return dict(editor, result=True, cunoscute=cunoscute, oprit=_oprit(config, slot))


def alegeri(date):
	ui, config, debit = _ci()
	try:
		_slot_alocare(date, ui)
		de_la = int(date.get("de_la", "0"))
		text = date.get("text", "")
		if not 0 <= de_la <= 100000 or len(text) > 60:
			raise ValueError("pagina")
		rezultat = _alocari().alegeriAlocare(date.get("fel", ""), text, de_la, 100)
		return dict(rezultat, result=True)
	except ValueError:
		return {"result": False, "message": _t("Alegere CI nevalidă.")}


def _ci():
	from enigma import eDVBCI_UI
	from Components.config import config
	from Components.SystemInfo import SystemInfo
	return eDVBCI_UI.getInstance(), config, SystemInfo.get("CommonInterfaceSupportsHighBitrates", False)


def _bool(element):
	return isinstance(getattr(element, "value", None), bool)


def _valoare(element):
	if _bool(element):
		return "true" if element.value else "false"
	return str(element.value)


def _alegeri(element):
	if _bool(element):
		return [("true", _t("Yes")), ("false", _t("No"))]
	rezultat = []
	for alegere in getattr(element.choices, "choices", []):
		cheie, text = alegere if isinstance(alegere, tuple) else (alegere, alegere)
		rezultat.append((str(cheie), _t(str(text))))
	return rezultat


def _formular(sursa, nume_texte, debit=True):
	rezultat = {}
	for nume, text in nume_texte.items():
		element = getattr(sursa, nume, None)
		if element is None or (nume == "canHandleHighBitrates" and not debit):
			continue
		rezultat[nume] = {"text": _t(text), "valoare": _valoare(element), "alegeri": _alegeri(element)}
	return rezultat


def _setari(config, slot, debit, ciplus=False):
	setari = dict(SETARI, **SETARI_CIPLUS) if ciplus else SETARI
	return _formular(config.ci[slot], setari, debit)


def _comune(config, helper=False):
	if getattr(config, "cimisc", None) is None:
		return {}
	return _formular(config.cimisc, dict(COMUNE, **COMUNE_HELPER) if helper else COMUNE)


def _sysinfo():
	try:
		from Components.SystemInfo import SystemInfo
		return SystemInfo
	except Exception as eroare:
		print("[HdsWebControl] SystemInfo: %r" % (eroare,))
		return {}


def _pin_pastrat(config, slot):
	element = getattr(config.ci[slot], "static_pin", None)
	return element is not None and str(element.value or "").isdigit()


def stare():
	ui, config, debit = _ci()
	lipsa = ciplus_lipsa()
	sysinfo = _sysinfo()
	helper = _helper_pornit(config, sysinfo)
	sloturi = []
	for slot in range(MAX_SLOTURI):
		cod = ui.getState(slot)
		if cod == -1:
			continue
		text = {0: _t("no module found"), 1: _t("init module"), 2: _t("Modul pregătit."), 3: _t("modul oprit")}
		oprit = _oprit(config, slot)
		sloturi.append({"slot": slot, "titlu": _t("Slot %d") % (slot + 1),
			"stare": cod, "text": text.get(cod, _t("Stare CI necunoscută.")),
			"modul": ui.getAppName(slot) if cod == 2 else "",
			# alocarile tin de slot: si cu modulul in initializare (CI+ neautentificat) sau scos
			"alocare": cod != 3,
			"oprit": oprit,
			"oprit_text": _t("Slot %d oprit: modulul nu primește niciun canal.") % (slot + 1) if oprit else "",
			"pin": _pin_pastrat(config, slot),
			"ciplus": _ciplus_slot(ui, slot, lipsa) if cod != 3 else "",
			"reset_init": cod != 3 and not helper,
			"setari": _setari(config, slot, debit, not lipsa) if cod != 3 else {}})
	return {"result": True, "sloturi": sloturi,
		"comune": _comune(config, bool(sysinfo.get("CIPlusHelper"))) if sloturi else {},
		# CI+: ce fisiere lipsesc (numai numele, niciodata continutul)
		"ciplus": {"lipsa": lipsa, "gata": not lipsa, "text": _ciplus_text_lipsa(lipsa) if lipsa else
			_t("Certificatele aparatului sunt în /etc/ciplus. Un modul CI+ se autentifică singur după pornire.")} if sloturi else {},
		"message": "" if sloturi else _t("Receptorul nu are sloturi CI."),
		"mmi_motiv": _t("Meniul MMI al modulului se folosește pe televizor. "
			"Citirea lui din web ar putea consuma mesajul destinat televizorului.")}


def _salveaza(formular, sursa, date):
	"""Formularul trimite numai ce s-a schimbat, cu valorile citite (initiale): ce s-a schimbat intre timp din alt ecran
	nu se scrie peste. Toate valorile se verifica inainte de prima schimbare si de notificarile ei."""
	chei = set(date) - {"actiune", "slot", "token", "initiale"}
	if not chei or any(k not in formular or date[k] not in [a[0] for a in formular[k]["alegeri"]] for k in chei):
		return {"result": False, "message": _t("Setare CI nevalidă.")}
	try:
		initiale = json.loads(date["initiale"])
		if not isinstance(initiale, dict) or any(n not in initiale for n in chei):
			raise ValueError("initiale")
	except (KeyError, ValueError, TypeError):
		return {"result": False, "message": _t("Recitește setările slotului înainte de salvare.")}
	if any(formular[n]["valoare"] != initiale[n] for n in chei):
		return {"result": False, "message": _t("Setările slotului s-au schimbat din alt ecran. Alegerile tale rămân în formular. Redeschide pagina pentru datele actuale.")}
	for nume in formular:
		if nume in chei:
			element = getattr(sursa, nume)
			element.value = (date[nume] == "true") if _bool(element) else date[nume]
			element.save()
	return None


def comanda_ciplus(date, dosar=None):
	"""Incarcarea unui fisier CI+ (base64 din pagina) sau stergerea tuturor. Raspunsul nu contine niciodata continutul."""
	actiune = date.get("actiune")
	if actiune == "ciplus-sterge":
		if set(date) - {"actiune", "token"}:
			return {"result": False, "message": _t("Comandă CI necunoscută.")}
		sterge_fisiere_ciplus(dosar)
		_ciplus_reset("certificatele CI+ sterse")
		return {"result": True, "lipsa": ciplus_lipsa(dosar),
			"message": _t("Certificatele CI+ au fost șterse. Modulul lucrează ca CI simplu.")}
	if set(date) - {"actiune", "token", "fisier", "date"}:
		return {"result": False, "message": _t("Comandă CI necunoscută.")}
	nume = os.path.basename(date.get("fisier", ""))
	try:
		continut = base64.b64decode(date.get("date", ""), validate=True)
	except (binascii.Error, ValueError):
		return {"result": False, "message": _t("Fișierul nu s-a putut citi. Încearcă din nou.")}
	greseala = verifica_fisier_ciplus(nume, continut)
	if greseala:
		return {"result": False, "message": greseala}
	try:
		scrie_fisier_ciplus(nume, continut, dosar)
	except OSError as eroare:
		print("[HdsWebControl] scrierea fisierului CI+ %s: %r" % (nume, eroare))
		return {"result": False, "message": _t("Fișierul %s nu s-a putut scrie în /etc/ciplus.") % nume}
	lipsa = ciplus_lipsa(dosar)
	if lipsa:
		return {"result": True, "lipsa": lipsa,
			"message": _t("Fișierul %s a fost pus. Mai lipsesc: %s.") % (nume, ", ".join(lipsa))}
	_ciplus_reset("certificatele CI+ puse")
	return {"result": True, "lipsa": [],
		"message": _t("Toate certificatele CI+ sunt puse. Modulul repornește și se autentifică singur.")}


def comanda(date):
	ui, config, debit = _ci()
	if date.get("actiune") in ("ciplus-incarca", "ciplus-sterge"):
		if not any(ui.getState(n) != -1 for n in range(MAX_SLOTURI)):
			return {"result": False, "message": _t("Receptorul nu are sloturi CI.")}
		return comanda_ciplus(date)
	if date.get("actiune") == "salveaza-comune":
		if not any(ui.getState(n) != -1 for n in range(MAX_SLOTURI)):
			return {"result": False, "message": _t("Receptorul nu are sloturi CI.")}
		eroare = _salveaza(_comune(config, bool(_sysinfo().get("CIPlusHelper"))), config.cimisc, date)
		if eroare:
			return eroare
		return {"result": True, "message": _t("Comanda CI a fost trimisă.")}
	text_slot = date.get("slot", "")
	if text_slot not in tuple(str(n) for n in range(MAX_SLOTURI)):
		return {"result": False, "message": _t("Slot CI nevalid.")}
	slot = int(text_slot)
	if ui.getState(slot) == -1:
		return {"result": False, "message": _t("Slot CI nevalid.")}
	actiune = date.get("actiune", "")
	if actiune == "reset":
		ui.setReset(slot)
		try:
			import os
			os.remove("/etc/ciplus/ci_auth_slot_%d.bin" % slot)
		except OSError:
			pass
	elif actiune == "init":
		ui.setInit(slot)
	elif actiune in ("opreste", "porneste"):
		# ca randul „CI pornit” de pe televizor (Screens/Ci.py): o apasare, fara intrebare; nucleul inchide sau
		# deschide /dev/ciN (notificatorul setarii cheama eDVBCI_UI.setEnabled)
		if set(date) - {"actiune", "slot", "token"}:
			return {"result": False, "message": _t("Comandă CI necunoscută.")}
		element = config.ci[slot].enabled
		element.value = actiune == "porneste"
		element.save()
		oprit = _oprit(config, slot)
		stare_noua = (_t("Slot %d oprit: modulul nu primește niciun canal.") if oprit else _t("Slot %d pornit.")) % (slot + 1)
		return {"result": True, "oprit": oprit, "oprit_text": stare_noua if oprit else "", "message": stare_noua}
	elif actiune == "pin":
		pin = date.get("pin", "").strip()
		if set(date) - {"actiune", "slot", "token", "pin"}:
			return {"result": False, "message": _t("Comandă CI necunoscută.")}
		if not pin.isdigit() or not 4 <= len(pin) <= 8:
			return {"result": False, "message": _t("Codul PIN are 4-8 cifre.")}
		config.ci[slot].static_pin.value = pin
		config.ci[slot].static_pin.save()
		return {"result": True, "message": _t("Codul PIN a fost păstrat.")}
	elif actiune == "pin-sterge":
		config.ci[slot].static_pin.value = ""
		config.ci[slot].static_pin.save()
		return {"result": True, "message": _t("Codul PIN păstrat a fost șters.")}
	elif actiune == "salveaza":
		eroare = _salveaza(_setari(config, slot, debit, not ciplus_lipsa()), config.ci[slot], date)
		if eroare:
			return eroare
	elif actiune in ("alocare-salveaza", "alocare-aplica"):
		helper = _alocari()
		try:
			_slot_alocare(date, ui)
			if set(date) - {"actiune", "slot", "token", "reguli", "revizie"}:
				raise ValueError("camp")
			if actiune == "alocare-aplica":
				editor = helper.reaplicaAlocarea(slot, date.get("revizie"))
			else:
				text = date.get("reguli", "")
				if len(text) > 256 * 1024:
					raise ValueError("reguli")
				reguli = helper.valideazaAlocarea(json.loads(text))
				editor = helper.salveazaEditor(slot, reguli, date.get("revizie"))
		except helper.AlocareSchimbata:
			return {"result": False, "message": _t("Alocările CI s-au schimbat din alt ecran. Ciorna rămâne aici. Redeschide editorul pentru datele actuale.")}
		except helper.AlocareNeaplicata as eroare:
			return {"result": False, "salvat": True, "aplicat": False, "revizie": eroare.revizie,
				"message": _t("Salvat, neaplicat. Verifică modulul și alege Reîncearcă aplicarea. Închide păstrează salvarea.")}
		except (ValueError, TypeError):
			return {"result": False, "message": _t("Alocare CI nevalidă.")}
		return {"result": True, "salvat": True, "aplicat": True, "revizie": editor["revizie"],
			"message": _t("Alocările CI au fost salvate. Se folosesc de la următoarea schimbare de canal.")}
	else:
		return {"result": False, "message": _t("Comandă CI necunoscută.")}
	return {"result": True, "message": _t("Comanda CI a fost trimisă.")}


def argumente(request):
	rezultat = {}
	for cheie, valori in (getattr(request, "args", None) or {}).items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		valoare = (valori or [b""])[0]
		if isinstance(valoare, bytes):
			valoare = valoare.decode("utf-8", "replace")
		rezultat[cheie] = str(valoare)
	return rezultat


def rute(baza, resource):
	class Alocare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, alocare(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] citire alocari CI: %r" % (eroare,))
				return self._eroare(request, _t("Alocările CI nu se pot citi. Fișierul existent a fost păstrat."), 503)

	class Alegeri(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, alegeri(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] alegeri CI: %r" % (eroare,))
				return self._eroare(request, _t("Lista de canale nu se poate citi acum."), 503)

	class Stare(baza):
		def render_GET(self, request):
			try:
				return self._raspunde(request, stare())
			except Exception as eroare:
				print("[HdsWebControl] citire CI: %r" % (eroare,))
				return self._eroare(request, _t("Sloturile CI nu se pot citi acum."), 503)

	class Comanda(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, comanda(argumente(request)))
			except Exception as eroare:
				print("[HdsWebControl] comanda CI: %r" % (eroare,))
				return self._eroare(request, _t("Comanda CI nu se poate executa acum."), 503)

		def render_GET(self, request):
			return self._eroare(request, _t("Comenzile CI cer POST."), 405)

	class Pagina(resource.Resource):
		isLeaf = True

		def render_GET(self, request):
			from .meniu_comun_web import pagina
			return pagina(request, pagina_text)

	return ({b"ci": Stare(), b"ci-comanda": Comanda(), b"ci-alocare": Alocare(), b"ci-alegeri": Alegeri()},
		{b"common-interface": Pagina()})


def pagina_text(stil, config_pagina):
	from .meniu_comun_web import sablon
	from .traducere_pagini import traduce
	return sablon(traduce(PAGINA, TEXTE_PAGINA), stil, config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Common Interface</title>
<style>__STIL_COMUN__ __STIL_PAGINI__
.slot select{max-width:100%;min-height:44px;}
.slot label{display:block;margin:12px 0;}
.slot label span{display:block;margin-bottom:6px;}
.slot h2,.slot p{overflow-wrap:anywhere;}
.alocare{margin-top:20px;border-top:1px solid;padding-top:15px;}
.alocare li{margin:8px 0;overflow-wrap:anywhere;}
.alocare li button{margin-left:12px;}
.alocare input,.alocare select{max-width:100%;width:100%;min-height:44px;}
.pin{margin-top:15px;}
.pin input{max-width:12em;min-height:44px;}
.pin button{margin:8px 12px 0 0;}
.ciplus input{max-width:100%;min-height:44px;}
.ciplus button{margin:8px 12px 0 0;}
.ciplus p{white-space:pre-line;overflow-wrap:anywhere;}
</style>
</head>
<body><main>
<h1>Common Interface</h1>
<p id="mesaj" class="mesaj" role="status" aria-live="polite">Se citesc sloturile CI...</p>
<div id="sloturi"></div>
<p id="mmi" class="nota"></p>
</main>
<script>
__SCRIPT_COMUN__
var ocupat = false, modificate = {}, editoare = {}, prima = true;
function el(tip, text){
  var nod = document.createElement(tip);
  if(text !== undefined){ nod.textContent = text; }
  return nod;
}
function trimite(slot, actiune, formular, initiale){
  if(ocupat){ return; }
  ocupat = true;
  var revizie = modificate[slot];
  var date = formular ? new URLSearchParams(new FormData(formular)) : new URLSearchParams();
  if(initiale){
    Object.keys(initiale).forEach(function(n){ if(date.get(n) === initiale[n]){ date.delete(n); } });
    if(!Array.from(date.keys()).length){ delete modificate[slot]; ocupat = false; return; }
    date.set("initiale", JSON.stringify(initiale));
  }
  if(slot !== "comune"){ date.set("slot", slot); }
  date.set("actiune", actiune);
  cerere("/api/ci-comanda", "POST", date).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){
      if(initiale){ Object.keys(initiale).forEach(function(n){ if(date.has(n)){ initiale[n] = date.get(n); } }); }
      if(initiale && modificate[slot] === revizie){ delete modificate[slot]; }
      return citeste();
    }
  }).catch(nimicNuRaspunde).then(function(){ ocupat = false; });
}
function eticheta(text, nod){
  var label = el("label"); label.appendChild(el("span", text)); label.appendChild(nod); return label;
}
function deschideAlocare(s, card, buton){
  if(ocupat || editoare[s.slot]){ return; }
  ocupat = true;
  editoare[s.slot] = {};
  cerere("/api/ci-alocare?slot=" + s.slot).then(function(d){
    if(!d.result){ delete editoare[s.slot]; mesaj(d.message, true); return; }
    var formular = el("form"), lista = el("ul"), draft = {rev:0, salvata:0, revizie:d.revizie, neaplicata:d.neaplicata};
    formular.className = "alocare"; editoare[s.slot] = draft; buton.disabled = true;
    var reguli = d.reguli;
    formular.appendChild(el("h3", "Alocă canale modulului")); formular.appendChild(lista);
    formular.appendChild(el("p", "Decodările multiple se schimbă în setările slotului."));
    var stareEditor = el("p"); stareEditor.setAttribute("role", "status"); formular.appendChild(stareEditor);
    function schimbata(){ draft.rev++; stareSalvare(); }
    function randuri(){
      lista.textContent = "";
      [["servicii", "Canal"], ["furnizori", "Furnizor"], ["caid", "CAID"]].forEach(function(f){
        reguli[f[0]].forEach(function(r, index){
          var text = f[0] === "caid" ? r.toString(16).toUpperCase().padStart(4, "0") : r.name;
          if(f[0] === "furnizori"){ text += " [" + r.namespace.toString(16).toUpperCase().padStart(8, "0") + "]"; }
          var li = el("li", f[1] + ": " + text), sterge = el("button", "Șterge"); sterge.type = "button";
          sterge.addEventListener("click", function(){ reguli[f[0]].splice(index, 1); schimbata(); randuri(); });
          li.appendChild(sterge); lista.appendChild(li);
        });
      });
      if(!lista.children.length){ lista.appendChild(el("li", "Nu sunt alocări. Se păstrează alegerea automată a modulului.")); }
    }
    function adauga(fel, valoare){
      var cheie = JSON.stringify(valoare);
      if(!reguli[fel].some(function(r){ return JSON.stringify(r) === cheie; })){
        reguli[fel].push(valoare); schimbata(); randuri();
      }
    }
    var fel = el("select");
    [["servicii", "Canale"], ["furnizori", "Furnizori"]].forEach(function(v){ var o = el("option", v[1]); o.value = v[0]; fel.appendChild(o); });
    fel.value = "servicii"; formular.appendChild(eticheta("Adaugă din lista receptorului", fel));
    var cautare = el("input"); cautare.type = "search"; cautare.maxLength = 60;
    formular.appendChild(eticheta("Caută după nume", cautare));
    var cauta = el("button", "Caută"), rezultate = el("select"), adaugaAles = el("button", "Adaugă selecția");
    var inapoi = el("button", "Înapoi"), inainte = el("button", "Mai multe"), optiuni = [], deLa = 0, generatie = 0;
    rezultate.size = 6; rezultate.setAttribute("aria-label", "Canale sau furnizori");
    [cauta, adaugaAles, inapoi, inainte].forEach(function(b){ b.type = "button"; });
    adaugaAles.disabled = true; inapoi.disabled = true; inainte.disabled = true;
    function cautaLista(start){
      var numar = ++generatie, tip = fel.value, text = cautare.value;
      adaugaAles.disabled = true; inapoi.disabled = true; inainte.disabled = true; rezultate.disabled = true;
      var date = new URLSearchParams({slot:s.slot, fel:tip, text:text, de_la:start});
      cerere("/api/ci-alegeri?" + date.toString()).then(function(r){
        if(numar !== generatie || editoare[s.slot] !== draft || fel.value !== tip || cautare.value !== text){ return; }
        if(!r.result){ mesaj(r.message, true); return; }
        deLa = start; optiuni = r.alegeri; rezultate.textContent = "";
        optiuni.forEach(function(v, i){
          var nume = v.name + (tip === "furnizori" ? " [" + v.namespace.toString(16).toUpperCase().padStart(8, "0") + "]" : "");
          var o = el("option", nume); o.value = i; rezultate.appendChild(o);
        });
        rezultate.value = "0"; rezultate.dataset.fel = tip;
        rezultate.disabled = false;
        adaugaAles.disabled = !optiuni.length; inapoi.disabled = !start; inainte.disabled = !r.mai_sunt;
      }).catch(function(e){ if(numar === generatie && editoare[s.slot] === draft){ nimicNuRaspunde(e); } });
    }
    cauta.addEventListener("click", function(){ cautaLista(0); });
    cautare.addEventListener("keydown", function(e){ if(e.key === "Enter"){ e.preventDefault(); cautaLista(0); } });
    cautare.addEventListener("input", function(){ generatie++; adaugaAles.disabled = true; inapoi.disabled = true; inainte.disabled = true; });
    fel.addEventListener("change", function(){ cautaLista(0); });
    inapoi.addEventListener("click", function(){ cautaLista(Math.max(0, deLa - 100)); });
    inainte.addEventListener("click", function(){ cautaLista(deLa + 100); });
    adaugaAles.addEventListener("click", function(){ var r = optiuni[Number(rezultate.value)]; if(r){ adauga(rezultate.dataset.fel, r); } });
    [cauta, rezultate, inapoi, inainte, adaugaAles].forEach(function(n){ formular.appendChild(n); });
    var cunoscute = el("select"), manual = el("input"), adaugaCaid = el("button", "Adaugă CAID");
    var scris = el("option", "Scrie CAID (hexazecimal)"); scris.value = ""; cunoscute.appendChild(scris);
    d.cunoscute.forEach(function(c){
      var semne = [];
      if(c.modul){ semne.push("modulul CI"); }
      if(c.acum){ semne.push("canalul pornit"); }
      var hex = c.caid.toString(16).toUpperCase().padStart(4, "0");
      var o = el("option", hex + (c.name ? " - " + c.name : "") + (semne.length ? " (" + semne.join(", ") + ")" : ""));
      o.value = hex; cunoscute.appendChild(o);
    });
    manual.type = "text"; manual.maxLength = 6; manual.placeholder = "0B00"; adaugaCaid.type = "button";
    formular.appendChild(eticheta("CAID cunoscute din canalele scanate și modul", cunoscute));
    formular.appendChild(eticheta("CAID hexazecimal", manual)); formular.appendChild(adaugaCaid);
    adaugaCaid.addEventListener("click", function(){
      var text = (cunoscute.value || manual.value).trim();
      if(!/^(?:0x)?[0-9a-f]{1,4}$/i.test(text) || parseInt(text, 16) === 0){
        mesaj("CAID nevalid. Folosește 1-4 cifre hexazecimale, de exemplu 0B00.", true); return;
      }
      adauga("caid", parseInt(text, 16)); manual.value = "";
    });
    var salveaza = el("button", "Salvează și aplică"), reincearca = el("button", "Reîncearcă aplicarea"), inchide = el("button", "Închide");
    salveaza.type = "submit"; reincearca.type = "button"; inchide.type = "button";
    formular.appendChild(salveaza); formular.appendChild(reincearca); formular.appendChild(inchide);
    formular.appendChild(el("p", "Închide renunță numai la modificările nesalvate. Salvarea trimisă nu se anulează."));
    function stareSalvare(){
      reincearca.hidden = !draft.neaplicata;
      salveaza.disabled = draft.neaplicata && draft.rev === draft.salvata;
      if(draft.neaplicata && !stareEditor.textContent){ stareEditor.textContent = "Salvat, neaplicat. Verifică modulul și alege Reîncearcă aplicarea. Închide păstrează salvarea."; }
    }
    function inchideEditor(){
      if(editoare[s.slot] !== draft){ return; }
      generatie++; delete editoare[s.slot]; card.removeChild(formular); buton.disabled = false;
    }
    inchide.addEventListener("click", inchideEditor);
    function executa(aplicaDoar){
      if(ocupat || (!aplicaDoar && salveaza.disabled)){ return; } ocupat = true; var rev = draft.rev;
      inchide.disabled = true; reincearca.disabled = true; salveaza.disabled = true;
      var date = new URLSearchParams({slot:s.slot, actiune:aplicaDoar ? "alocare-aplica" : "alocare-salveaza", revizie:draft.revizie});
      if(!aplicaDoar){ date.set("reguli", JSON.stringify(reguli)); }
      cerere("/api/ci-comanda", "POST", date).then(function(r){
        if(editoare[s.slot] !== draft){ return; }
        mesaj(r.message, !r.result); stareEditor.textContent = r.message;
        if(r.salvat){
          draft.revizie = r.revizie; draft.neaplicata = !r.aplicat;
          if(!aplicaDoar){ draft.salvata = rev; }
        }
        if(r.result && draft.rev === draft.salvata){ inchideEditor(); return citeste(); }
      }).catch(nimicNuRaspunde).then(function(){
        ocupat = false; inchide.disabled = false; reincearca.disabled = false; stareSalvare();
      });
    }
    formular.addEventListener("submit", function(e){ e.preventDefault(); executa(false); });
    reincearca.addEventListener("click", function(){ executa(true); });
    randuri(); stareSalvare(); card.appendChild(formular); cautaLista(0);
  }).catch(function(e){ delete editoare[s.slot]; nimicNuRaspunde(e); }).then(function(){ ocupat = false; });
}
// Oprește / Pornește slotul: butonul si textul se schimba pe loc din raspuns, si cand citirea sloturilor asteapta
// (un editor deschis sau o setare nesalvata nu lasa pagina sa se redeseneze).
function comutaSlotul(s, buton, text){
  if(ocupat){ return; }
  ocupat = true;
  var date = new URLSearchParams({slot:s.slot, actiune:s.oprit ? "porneste" : "opreste"});
  cerere("/api/ci-comanda", "POST", date).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){
      s.oprit = d.oprit; buton.textContent = d.oprit ? "Pornește slotul" : "Oprește slotul";
      text.textContent = d.oprit_text || ""; text.hidden = !d.oprit;
      return citeste();
    }
  }).catch(nimicNuRaspunde).then(function(){ ocupat = false; });
}
function formularSetari(cheie, setari, actiune){
  var formular = el("form"), initiale = {};
  Object.keys(setari).forEach(function(nume){
    var setare = setari[nume], label = el("label"), select = el("select");
    initiale[nume] = setare.valoare;
    label.appendChild(el("span", setare.text)); select.name = nume;
    setare.alegeri.forEach(function(a){
      var opt = el("option", a[1]); opt.value = a[0]; select.appendChild(opt);
    });
    select.value = setare.valoare; label.appendChild(select); formular.appendChild(label);
    select.addEventListener("change", function(){ modificate[cheie] = (modificate[cheie] || 0) + 1; });
  });
  var salveaza = el("button", "Salvează"); salveaza.type = "submit";
  formular.appendChild(salveaza);
  formular.addEventListener("submit", function(e){ e.preventDefault(); trimite(cheie, actiune, formular, initiale); });
  return formular;
}
// Codul PIN pastrat: modulul il primeste singur cand il cere (ca pe televizor)
function codPin(s, card){
  var bloc = el("div"), camp = el("input"), pastreaza = el("button", "Păstrează codul PIN");
  bloc.className = "pin";
  camp.type = "password"; camp.inputMode = "numeric"; camp.maxLength = 8; camp.autocomplete = "off";
  camp.setAttribute("aria-label", "Codul PIN al cardului");
  pastreaza.type = "button";
  bloc.appendChild(eticheta("Codul PIN al cardului", camp)); bloc.appendChild(pastreaza);
  pastreaza.addEventListener("click", function(){
    var date = new URLSearchParams({slot:s.slot, actiune:"pin", pin:camp.value});
    if(ocupat){ return; } ocupat = true;
    cerere("/api/ci-comanda", "POST", date).then(function(d){
      mesaj(d.message, !d.result); if(d.result){ camp.value = ""; return citeste(); }
    }).catch(nimicNuRaspunde).then(function(){ ocupat = false; });
  });
  if(s.pin){
    var sterge = el("button", "Șterge codul PIN păstrat"); sterge.type = "button";
    sterge.addEventListener("click", function(){ trimite(s.slot, "pin-sterge"); });
    bloc.appendChild(sterge);
  }
  card.appendChild(bloc);
}
// CI+: cele patru fisiere ale aparatului alese odata; fiecare merge pe receptor dupa numele lui (base64, nimic intors)
function cardCiplus(c, loc){
  var card = el("section"); card.className = "card slot ciplus";
  card.appendChild(el("h2", "CI+"));
  card.appendChild(el("p", c.text));
  var alege = el("input"); alege.type = "file"; alege.multiple = true;
  card.appendChild(eticheta("Alege fișierele param, root.pem, customer.pem și device.pem", alege));
  var pune = el("button", "Pune certificatele"); pune.type = "button"; card.appendChild(pune);
  pune.addEventListener("click", function(){
    var fisiere = Array.from(alege.files || []);
    if(ocupat || !fisiere.length){ return; }
    ocupat = true;
    fisiere.reduce(function(pas, f){
      return pas.then(function(){
        return f.arrayBuffer().then(function(buf){
          var octeti = new Uint8Array(buf), text = "";
          for(var i = 0; i < octeti.length; i++){ text += String.fromCharCode(octeti[i]); }
          var date = new URLSearchParams({actiune:"ciplus-incarca", fisier:f.name, date:btoa(text)});
          return cerere("/api/ci-comanda", "POST", date).then(function(r){ mesaj(r.message, !r.result); });
        });
      });
    }, Promise.resolve()).catch(nimicNuRaspunde).then(function(){ ocupat = false; alege.value = ""; return citeste(); });
  });
  if(c.gata){
    var sterge = el("button", "Șterge certificatele CI+"); sterge.type = "button";
    sterge.addEventListener("click", function(){ trimite("comune", "ciplus-sterge"); });
    card.appendChild(sterge);
  }
  loc.appendChild(card);
}
function arata(d){
  var loc = $("sloturi"); loc.textContent = "";
  $("mmi").textContent = d.sloturi.length ? d.mmi_motiv : "";
  if(!d.sloturi.length){ mesaj(d.message); }
  if(d.comune && Object.keys(d.comune).length){
    var comun = el("section"); comun.className = "card slot";
    comun.appendChild(el("h2", "Setări comune"));
    comun.appendChild(formularSetari("comune", d.comune, "salveaza-comune"));
    loc.appendChild(comun);
  }
  if(d.ciplus && d.ciplus.text){ cardCiplus(d.ciplus, loc); }
  d.sloturi.forEach(function(s){
    var card = el("section"); card.className = "card slot";
    card.appendChild(el("h2", s.titlu));
    card.appendChild(el("p", s.text));
    if(s.modul){ card.appendChild(el("p", s.modul)); }
    if(s.ciplus){ card.appendChild(el("p", s.ciplus)); }
    var opritText = el("p", s.oprit_text || ""); opritText.hidden = !s.oprit; card.appendChild(opritText);
    var butoane = el("div"); butoane.className = "butoane";
    // slotul oprit: nucleul nu vorbeste cu modulul, deci Reset, Init si setarile n-ar face nimic (ca pe televizor)
    // cu ajutorul CI+ extern pornit, Reset si Init sunt ale lui (ca pe televizor)
    if(s.stare !== 3 && s.reset_init !== false){
      [["Reset", "reset"], ["Init", "init"]].forEach(function(a){
        var b = el("button", a[0]); b.type = "button";
        b.addEventListener("click", function(){ trimite(s.slot, a[1]); });
        butoane.appendChild(b);
      });
    }
    var oprire = el("button", s.oprit ? "Pornește slotul" : "Oprește slotul"); oprire.type = "button";
    oprire.addEventListener("click", function(){ comutaSlotul(s, oprire, opritText); });
    butoane.appendChild(oprire);
    card.appendChild(butoane);
    if(Object.keys(s.setari).length){ card.appendChild(formularSetari(s.slot, s.setari, "salveaza")); }
    if(s.setari.use_static_pin && s.setari.use_static_pin.valoare === "true"){ codPin(s, card); }
    if(s.alocare){
      var aloca = el("button", "Alocă canale modulului"); aloca.type = "button";
      aloca.addEventListener("click", function(){ deschideAlocare(s, card, aloca); }); card.appendChild(aloca);
    }
    loc.appendChild(card);
  });
}
function citeste(){
  return cerere("/api/ci").then(function(d){
    if(d.result){
      // Un raspuns deja in zbor nu trebuie sa stearga editarile nesalvate.
      if(Object.keys(modificate).length || Object.keys(editoare).length){ return; }
      if(prima){ mesaj(""); prima = false; }
      arata(d);
    } else { mesaj(d.message, true); }
  });
}
// Citirea urmatoare incepe dupa raspuns; nu inlocuieste un formular editat.
function bucla(){
  var editeaza = document.activeElement && /^(SELECT|OPTION|INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
  var pas = document.hidden || ocupat || Object.keys(modificate).length || Object.keys(editoare).length || editeaza
    ? Promise.resolve() : citeste().catch(nimicNuRaspunde);
  pas.then(function(){ setTimeout(bucla, 5000); });
}
bucla();
</script>
</body></html>
"""

TEXTE_PAGINA = {
	"html": (N_("Common Interface"), N_("Se citesc sloturile CI...")),
	"js": (N_("Reset"), N_("Init"), N_("Salvează"), N_("Alocă canale modulului"),
		N_("Șterge"), N_("Canal"), N_("Furnizor"), N_("Nu sunt alocări. Se păstrează alegerea automată a modulului."),
		N_("Canale"), N_("Furnizori"), N_("Adaugă din lista receptorului"), N_("Caută după nume"), N_("Caută"),
		N_("Adaugă selecția"), N_("Înapoi"), N_("Mai multe"), N_("Canale sau furnizori"),
		N_("Adaugă CAID"), N_("Scrie CAID (hexazecimal)"), N_("CAID cunoscute din canalele scanate și modul"),
		N_("CAID hexazecimal"), N_("CAID nevalid. Folosește 1-4 cifre hexazecimale, de exemplu 0B00."),
		N_("Decodările multiple se schimbă în setările slotului."), N_("Reîncearcă aplicarea"),
		N_("Salvat, neaplicat. Verifică modulul și alege Reîncearcă aplicarea. Închide păstrează salvarea."),
		N_("Închide renunță numai la modificările nesalvate. Salvarea trimisă nu se anulează."),
		N_("Salvează și aplică"), N_("Închide"), N_("Oprește slotul"), N_("Pornește slotul"), N_("modulul CI"),
		N_("canalul pornit"), N_("Setări comune"), N_("Păstrează codul PIN"), N_("Codul PIN al cardului"),
		N_("Șterge codul PIN păstrat"), N_("CI+"), N_("Alege fișierele param, root.pem, customer.pem și device.pem"),
		N_("Pune certificatele"), N_("Șterge certificatele CI+")),
}

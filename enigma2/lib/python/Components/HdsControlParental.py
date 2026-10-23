# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsControlParental: regulile ecranului Control parental (Screens/ParentalControlSetup.py, Meniu > Setari > Sistem &
# Dispozitive > Control parental) scrise o singura data, pentru pagina web /control-parental
# (HdsWebControl/parental_web.py): ce randuri se vad, cand cere ecranul PIN-ul, cum se numara incercarile, cand lipseste
# un PIN, schimbarea unui PIN si listele de canale si buchete. Setarile sunt aceleasi config.ParentalControl.* ca pe
# televizor (Components/ParentalControl.py le face la pornire), iar listele sunt ale lui parentalControl.
#
# Regulile, citite din cod:
# - randurile (ParentalControlSetup.createSetup): Enable parental control; cu el pornit, Protect setup (si Change setup
#   PIN cand e pornit) si Protect services; cu Protect services pornit: Parental control type, Change service PIN (in
#   modul simple; in modul complex randul nu face nimic), Remember service PIN, Remember service PIN cancel, Edit
#   services list, Edit bouquets list, Reload Black-/Whitelists;
# - ecranul cere PIN-ul setarilor la deschidere cand Protect setup si Enable parental control sunt pornite (isProtected);
# - incercarile (Screens/InputBox.py PinInput, cu config.ParentalControl.retries.setuppin, ca ecranul): 3 incercari;
#   dupa a treia gresita, 15 minute de la ultima incercare nu se mai poate scrie; dupa ele, iar 3; un PIN bun pune iar
#   3. Fiecare incercare tine minte ora ei. PinInput are regula lui in clasa ecranului, folosita si la canale; aici e
#   aceeasi regula, cu aceleasi setari, deci televizorul si pagina numara impreuna;
# - un PIN nescris are valoarea "aaaa" (ConfigPIN(default=-1)); la iesire, ecranul nu lasa Protect setup sau Protect
#   services pornite fara PIN (ParentalControlSetup.keyCancel): intreaba de PIN, iar fara el le opreste;
# - schimbarea unui PIN (ParentalControlChangePin) cere PIN-ul vechi cand exista unul (pin != "aaaa"), cu aceleasi
#   incercari ale setarilor (si pentru PIN-ul canalelor), apoi PIN-ul nou de doua ori, la fel.
#
# Fisierul nu importa nimic din enigma2 la incarcare.

import re

INCERCARI = 3
ASTEPTARE_S = 15 * 60          # PinInput.waitTime = 15 minute
NESETAT = "aaaa"
MAX_LISTA = 20000

_PIN = re.compile(r"^[0-9]{4}$")

# setarile care se schimba din randuri (in ordinea ecranului); celelalte randuri sunt actiuni
SETARI = ("configured", "setuppinactive", "servicepinactive", "type", "storeservicepin", "storeservicepincancel")


def cp(config=None):
	if config is None:
		from Components.config import config
	return config.ParentalControl


def protejat(c):
	"""Ecranul cere PIN-ul setarilor la deschidere (ParentalControlSetup.isProtected)."""
	return bool(c.setuppinactive.value and c.configured.value)


def pinSetat(el):
	return el.value != NESETAT


def pinBun(text):
	return bool(text) and bool(_PIN.match(text))


def randuri(c):
	"""Cheile randurilor care se vad pe televizor acum, in ordinea lor (ParentalControlSetup.createSetup)."""
	r = ["configured"]
	if c.configured.value:
		r.append("setuppinactive")
		if c.setuppinactive.value:
			r.append("pin_setari")
		r.append("servicepinactive")
		if c.servicepinactive.value:
			r += ["type", "pin_canale", "storeservicepin", "storeservicepincancel", "lista_canale", "lista_buchete",
				"reincarca"]
	return r


# ------------------------------------------------------------------ incercarile (ca PinInput)
def stareIncercari(incercari, acum):
	"""(incercari ramase, secunde de asteptat). Ca PinInput la deschidere: cu 0 incercari si mai putin de 15 minute de
	la ultima, se asteapta; dupa ele, iar 3 (salvat)."""
	if incercari.tries.value == 0:
		ramas = incercari.time.value + ASTEPTARE_S - acum
		if ramas > 0:
			return 0, int(ramas) + (1 if ramas % 1 else 0)
		incercari.tries.value = INCERCARI
		incercari.tries.save()
	return incercari.tries.value, 0


def verificaPin(incercari, text, pinuri, acum):
	"""Un PIN scris (4 cifre) fata de `pinuri` (valorile din config), ca PinInput.go. -> (bun, ramase, asteapta_s);
	bun = None cand nu se mai poate incerca acum (nimic numarat)."""
	ramase, asteapta = stareIncercari(incercari, acum)
	if asteapta:
		return None, 0, asteapta
	incercari.time.value = int(acum)
	incercari.time.save()
	if pinBun(text) and int(text) in pinuri:
		incercari.tries.value = INCERCARI
		incercari.tries.save()
		return True, INCERCARI, 0
	incercari.tries.value = max(0, ramase - 1)
	incercari.tries.save()
	if incercari.tries.value == 0:
		return False, 0, ASTEPTARE_S
	return False, incercari.tries.value, 0


# ------------------------------------------------------------------ PIN-urile
def pinLipsa(c, cheie):
	"""True daca randul `cheie` (setuppinactive / servicepinactive) ar ramane pornit fara PIN (keyCancel il opreste)."""
	if cheie == "setuppinactive":
		return not pinSetat(c.setuppin)
	if cheie == "servicepinactive":
		return not pinSetat(c.servicepin[0])
	return False


def elementPin(c, fel):
	"""fel = "setari" (Change setup PIN) sau "canale" (Change service PIN, servicepin[0])."""
	return c.setuppin if fel == "setari" else c.servicepin[0]


def puneNou(el, text):
	"""PIN-ul nou (deja verificat), ca ParentalControlChangePin.keyOK: valoarea si save()."""
	el.value = int(text)
	el.save()


# ------------------------------------------------------------------ listele
def _lista(refstr, eServiceCenter=None, eServiceReference=None):
	if eServiceCenter is None:
		from enigma import eServiceCenter, eServiceReference
	lista = eServiceCenter.getInstance().list(eServiceReference(refstr))
	if lista is None:
		return []
	return [(str(x[0]), str(x[1])) for x in (lista.getContent("CN", True) or [])[:MAX_LISTA]]


def canale(eServiceCenter=None, eServiceReference=None, service_types_tv=None):
	"""Canalele TV ca in ParentalControlEditor: [(ref, nume)] in ordinea numelui."""
	if service_types_tv is None:
		from Screens.ChannelSelection import service_types_tv
	return _lista("%s ORDER BY name" % service_types_tv, eServiceCenter, eServiceReference)


def buchete(eServiceCenter=None, eServiceReference=None):
	"""Buchetele din bouquets.tv, ca ParentalControlBouquetEditor."""
	return _lista('1:134:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet', eServiceCenter, eServiceReference)


SPECIAL = "#"


def litera(nume):
	"""Grupa de pe televizor: prima litera a..z, altfel caracterele speciale."""
	k = (nume or " ").lower()[0]
	return k if "a" <= k <= "z" else SPECIAL


def protectie(pc, ref):
	"""(blocat, felul) ca getProtectionType: felul = "canal", "buchet" sau "" (de unde vine semnul)."""
	blocat, imagine = pc.getProtectionType(ref)
	fel = ""
	if imagine:
		fel = "buchet" if imagine.endswith("BOUQUET") else "canal"
	return bool(blocat), fel


def comuta(pc, ref, blocat):
	"""Ca OK in editor (ParentalControlList.toggleSelectedLock), dar spre starea ceruta; listele se scriu pe disc."""
	acum = protectie(pc, ref)[0]
	if blocat and not acum:
		pc.protectService(ref)
	elif not blocat and acum:
		pc.unProtectService(ref)
	pc.save()
	return protectie(pc, ref)

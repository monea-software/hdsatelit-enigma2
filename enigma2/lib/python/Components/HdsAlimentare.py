# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAlimentare.py: logica grupului Meniu > Standby si repornire, aceeasi pentru televizor si pentru pagina web
# /alimentare (HdsWebControl/alimentare_web.py).
#
# - Oprirea programata (Screens/SleepTimerEdit.py): setarile config.SleepTimer.action si ask (SleepTimer.py) si
#   defaulttime (aici, initConfig: inainte se facea la importul ecranului, deci nu exista pana la prima deschidere a
#   lui); pornirea (porneste: minutele raman propunerea de data viitoare, actiunea si intrebarea se salveaza, apoi
#   nav.SleepTimer.setSleepTime), oprirea (opreste: nav.SleepTimer.clear), minutele ramase si minutele pana la
#   sfarsitul emisiunii sau al filmului de acum (minuteCanal, tasta albastra a ecranului). Codul e cel al ecranului,
#   mutat aici; ecranul il cheama, deci se poarta la fel.
# - Standby, repornirile si oprirea (deschide): acelasi ecran ca intrarea din meniu (Screens/Standby.py: Standby,
#   TryQuitMainloop cu acelasi numar ca in data/menu.xml), deschis dupa `dupa_ms` milisecunde, ca raspunsul unei cereri
#   web sa plece inainte. TryQuitMainloop intreaba pe televizor cand o inregistrare e in curs sau incepe in mai putin de
#   6 minute sau cand lucreaza ceva in fundal (Components/HdsModSigur.repornireCuIntrebare o spune dinainte).
# - stareReceptor: standby, inregistrarile, urmatoarea inregistrare, lucrarile din fundal, pentru pagina web.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau sesiunea, navigatia si config.

import time

# ce -> (entryID din data/menu.xml, numarul dat lui TryQuitMainloop; None = ecranul Standby)
ACTIUNI = (
	("standby", "standby", None),
	("interfata", "restart_enigma", 3),
	("receptor", "restart", 2),
	("flash", "return_to_flash", 0),
	("oprire", "deep_standby", 1),
)
CHEI = tuple(a[0] for a in ACTIUNI)
MINUTE_IMPLICITE = 30
# cel putin un minut din web: 0 minute ar opri receptorul pe loc, fara confirmare (oprirea pe loc are cardul ei)
MINUTE_MINIM_WEB = 1
INREGISTRARE_CURAND_S = 360

_ceas = {}


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _log(text):
	print("[HdsAlimentare] %s" % text)


def entryID(ce):
	for cheie, intrare, _numar in ACTIUNI:
		if cheie == ce:
			return intrare
	return None


def numar(ce):
	"""Numarul dat lui TryQuitMainloop pentru `ce`; None pentru standby. KeyError pentru o actiune necunoscuta."""
	for cheie, _intrare, n in ACTIUNI:
		if cheie == ce:
			return n
	raise KeyError(ce)


# ------------------------------------------------------------------ oprirea programata

def initConfig(config=None):
	"""config.SleepTimer cu defaulttime (minutele propuse, implicit 30), facut o singura data. action si ask le face
	SleepTimer.py (importat de Navigation la pornire)."""
	if config is None:
		from Components.config import config
	from Components.config import ConfigInteger
	if "SleepTimer" not in config.dict():
		import SleepTimer  # noqa: F401  (face config.SleepTimer.action si ask)
	if "defaulttime" not in config.SleepTimer.dict():
		config.SleepTimer.defaulttime = ConfigInteger(default=MINUTE_IMPLICITE)
	return config.SleepTimer


def textActiune(valoare, SystemInfo=None):
	"""Textul actiunii ca pe butonul verde al ecranului: Deep Standby / Shutdown / Standby."""
	if valoare == "shutdown":
		if SystemInfo is None:
			from Components.SystemInfo import SystemInfo
		if SystemInfo.get("DeepstandbySupport"):
			return _t("Deep Standby")
		return _t("Shutdown")
	if valoare == "standby":
		return _t("Standby")
	return str(valoare)


def alegeriActiune(config=None, SystemInfo=None):
	"""[[valoare, text]] din alegerile lui config.SleepTimer.action, cu textele ecranului."""
	c = initConfig(config)
	return [[str(v), textActiune(v, SystemInfo)] for v in c.action.choices]


def limiteMinute(config=None):
	"""(minim, maxim) pentru minutele din web: limitele lui config.SleepTimer.defaulttime, cel putin MINUTE_MINIM_WEB."""
	c = initConfig(config)
	minim, maxim = c.defaulttime.limits[0]
	return max(MINUTE_MINIM_WEB, int(minim)), int(maxim)


def stareSomn(nav, config=None):
	"""Starea opririi programate: activ, minutele ramase (ca ecranul: getCurrentSleepTime), ora opririi, actiunea,
	intrebarea si minutele propuse."""
	c = initConfig(config)
	st = nav.SleepTimer
	activ = bool(st.isActive())
	rez = {
		"activ": activ,
		"minute": int(st.getCurrentSleepTime()) if activ else None,
		"ora": None,
		"actiune": str(c.action.value),
		"intreaba": bool(c.ask.value),
		"minute_propuse": int(c.defaulttime.value),
	}
	lista = getattr(st, "timer_list", None) or []
	if activ and lista:
		rez["ora"] = int(lista[0].begin)
	return rez


def porneste(nav, minute, config=None):
	"""Ca OK pe ecran cu Enable timer: minutele raman propunerea de data viitoare, actiunea si intrebarea se salveaza,
	temporizatorul porneste de la zero."""
	c = initConfig(config)
	c.defaulttime.setValue(minute)
	c.defaulttime.save()
	c.action.save()
	c.ask.save()
	nav.SleepTimer.setSleepTime(minute)


def opreste(nav):
	"""Ca OK pe ecran cu Disable timer."""
	nav.SleepTimer.clear()


def minuteCanal(nav, epg=None, acum=None):
	"""Tasta albastra a ecranului (Use time of currently running service): minutele pana la sfarsitul filmului sau
	al emisiunii de acum, plus 2; None cand nu se poate afla."""
	remaining = None
	ref = nav.getCurrentlyPlayingServiceReference()
	if ref:
		path = ref.getPath()
		if path:  # film
			service = nav.getCurrentService()
			seek = service and service.seek()
			if seek:
				length = seek.getLength()
				position = seek.getPlayPosition()
				if length and position:
					remaining = length[1] - position[1]
					if remaining > 0:
						remaining = remaining // 90000
		else:  # DVB
			if epg is None:
				from enigma import eEPGCache
				epg = eEPGCache.getInstance()
			event = epg.lookupEventTime(ref, -1, 0)
			if event:
				now = int(time.time() if acum is None else acum)
				start = event.getBeginTime()
				duration = event.getDuration()
				end = start + duration
				remaining = end - now
	if remaining:
		return (remaining // 60) + 2
	return None


# ------------------------------------------------------------------ standby, repornirile, oprirea

def programeaza(functie, dupa_ms, fabrica_ceas=None, nume="t"):
	"""functie() pe firul enigma2 peste `dupa_ms` milisecunde (eTimer pastrat aici, altfel ar disparea inainte)."""
	if fabrica_ceas is None:
		from enigma import eTimer as fabrica_ceas
	t = fabrica_ceas()
	try:
		_ceas[nume + "_legatura"] = t.timeout.connect(functie)
	except AttributeError:
		t.callback.append(functie)
	t.start(int(dupa_ms), True)
	_ceas[nume] = t
	return t


def deschide(sesiune, ce, dupa_ms=0, Standby=None, fabrica_ceas=None):
	"""Ecranul intrarii `ce` pe televizor, ca din meniu: Standby (numai daca nu e deja in standby) sau
	TryQuitMainloop(numar). Cu `dupa_ms` se deschide dupa atatea milisecunde. False fara sesiune."""
	n = numar(ce)
	if sesiune is None:
		return False

	def acum():
		try:
			S = Standby
			if S is None:
				from Screens import Standby as S
			if n is None:
				if S.inStandby is None:
					sesiune.open(S.Standby)
			else:
				sesiune.open(S.TryQuitMainloop, n)
		except Exception as e:
			_log("%s: %r" % (ce, e))

	if dupa_ms <= 0:
		acum()
	else:
		# un ceas pe actiune: o a doua actiune in cele 1,5 s nu o pierde pe prima
		programeaza(acum, dupa_ms, fabrica_ceas, nume="deschide-" + ce)
	return True


def vaIntreba(sesiune):
	"""True cand TryQuitMainloop va intreba pe televizor (aceeasi regula ca ecranul, din HdsModSigur)."""
	if sesiune is None:
		return False
	from Components.HdsModSigur import repornireCuIntrebare
	return bool(repornireCuIntrebare(sesiune))


def stareReceptor(sesiune, Standby=None, job_manager=None):
	"""{standby, intrebare_pe_tv, inregistrari, urmatoarea (ora, 0 = niciuna), curand, lucrari, va_intreba}."""
	if Standby is None:
		from Screens import Standby
	rez = {"standby": Standby.inStandby is not None, "intrebare_pe_tv": bool(getattr(Standby, "inTryQuitMainloop", False)),
		"inregistrari": 0, "urmatoarea": 0, "curand": False, "lucrari": 0, "va_intreba": False}
	nav = getattr(sesiune, "nav", None)
	if nav is not None:
		try:
			rez["inregistrari"] = len(nav.getRecordings() or [])
		except Exception as e:
			_log("inregistrarile: %r" % e)
		try:
			urm = nav.RecordTimer.getNextRecordingTime()
			if urm and urm > 0:
				rez["urmatoarea"] = int(urm)
				rez["curand"] = urm - time.time() < INREGISTRARE_CURAND_S
		except Exception as e:
			_log("urmatoarea inregistrare: %r" % e)
	try:
		if job_manager is None:
			from Components.Task import job_manager
		rez["lucrari"] = len(job_manager.getPendingJobs())
	except Exception as e:
		_log("lucrarile: %r" % e)
	rez["va_intreba"] = vaIntreba(sesiune)
	return rez

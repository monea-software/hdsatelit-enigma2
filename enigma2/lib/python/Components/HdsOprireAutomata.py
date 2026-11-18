# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsOprireAutomata.py: oprirea automata dupa o intarziere aleasa o singura data (0.7.7, OSD; LinuxSat 164182 #970783,
# TODO 15.11 18:41 PSC11: „automatic device shutdown after a set period of time”, cu poza „Auto deep standby / Delay:
# 120 Minutes” din programatorul de alimentare al altei imagini). Oprirea programata (Sleep Timer, SleepTimer.py) e o
# singura oprire, pornita de fiecare data; lipsea setarea aleasa O DATA: dupa atatea ore FARA NICIO TASTA, receptorul
# trece singur in standby sau se opreste complet, si se reia singura dupa fiecare tasta si dupa fiecare pornire (ca
# OE-Alliance: Auto standby / Auto deep standby).
#
# Setarile: config.usage.hds_oprire_auto (minutele, "0" = Nu, din fabrica Nu) si config.usage.hds_oprire_auto_fel
# ("standby" sau "shutdown", aceleasi valori si texte ca la oprirea programata; din fabrica Standby). Pe televizor: doua
# randuri in ecranul Sleep Timer (Screens/SleepTimerEdit.py, Meniu > Standby si repornire); in web: cardul Sleep Timer
# din /alimentare (HdsWebControl/alimentare_web.py, POST /api/alimentare-auto). Ambele folosesc numai functiile de aici.
#
# Cum merge (porneste(session) din mytest.py):
# - un ascultator de taste inaintea tuturor hartilor (prioritatea protectiei ecranului, Screens/ScreenSaver.py) tine
#   minte ora ultimei taste (ceasul monoton: ora corectata la pornire nu-l strica); un singur ceas, pornit pe timpul ramas;
# - la vreme: daca se inregistreaza ceva, incepe o inregistrare sau o comutare in mai putin de INREGISTRARE_CURAND_S,
#   lucreaza ceva in fundal sau se instaleaza pachete, se amana cu AMANARE_S;
# - receptorul in standby: cu Standby nu e nimic de facut; cu Oprire completa se opreste fara intrebare (nu se uita
#   nimeni), prin TryQuitMainloop 1;
# - altfel o fereastra cu numaratoare de NUMARATOARE_S: „... Apasă orice tastă ca receptorul să rămână pornit.” Orice
#   tasta o inchide si reia intervalul intreg (tasta nu face altceva). La sfarsit, verificarile din nou, apoi Standby sau
#   TryQuitMainloop 1 (cu textul de oprire pe ecran, Screens/Standby.py).
# Partea de sus nu importa enigma: se probeaza pe PC.

from __future__ import absolute_import

import time

try:
	monotonic = time.monotonic
except AttributeError:     # Python 2
	monotonic = time.time

MINUTE = (0, 60, 120, 180, 240, 360, 480)
FELURI = ("standby", "shutdown")
FEL_IMPLICIT = "standby"
AMANARE_S = 300
INREGISTRARE_CURAND_S = 900
NUMARATOARE_S = 60
# prioritatea ascultatorului de taste: aceeasi cu a protectiei ecranului (cel mai mic int pe 32 de biti)
PRIO_TASTE = -0x7FFFFFFF - 1
STEAG_APASAT = 0
STEAG_ELIBERAT = 1

_S = {"sesiune": None, "ultima": None, "ceas": None, "legatura": None, "legat": False, "intrebare": None,
	"inghite": None, "pornit": False}


def N_(text):
	"""Marcaj pentru xgettext; textul se traduce la folosire."""
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsOprireAutomata] %s" % text)


# ---------------------------------------------------------------- setarile

def textMinute(minute):
	"""„Nu”, „după 1 oră”, „după 2 ore”..."""
	minute = int(minute)
	if minute <= 0:
		return _t("Nu")
	if minute == 60:
		return _t("după 1 oră")
	if minute % 60 == 0:
		return _t("după %d ore") % (minute // 60)
	return _t("după %d minute") % minute


def textFel(fel, SystemInfo=None):
	"""Acelasi text ca butonul verde al opririi programate (Standby / Deep Standby / Shutdown)."""
	try:
		from Components import HdsAlimentare
		return HdsAlimentare.textActiune(fel, SystemInfo)
	except Exception:
		return _t("Standby") if fel == "standby" else _t("Shutdown")


def alegeriMinute():
	return [(str(m), textMinute(m)) for m in MINUTE]


def alegeriFel(SystemInfo=None):
	return [(f, textFel(f, SystemInfo)) for f in FELURI]


def initConfig(config=None):
	"""config.usage.hds_oprire_auto si hds_oprire_auto_fel, facute o singura data. Intoarce config.usage."""
	if config is None:
		from Components.config import config
	from Components.config import ConfigSelection, ConfigSubsection
	if "usage" not in config.content.items:
		config.usage = ConfigSubsection()
	u = config.usage
	if "hds_oprire_auto" not in u.content.items:
		u.hds_oprire_auto = ConfigSelection(default="0", choices=alegeriMinute())
	if "hds_oprire_auto_fel" not in u.content.items:
		u.hds_oprire_auto_fel = ConfigSelection(default=FEL_IMPLICIT, choices=alegeriFel())
	return u


def minute(config=None):
	try:
		return max(0, int(initConfig(config).hds_oprire_auto.value))
	except (TypeError, ValueError):
		return 0


def fel(config=None):
	v = initConfig(config).hds_oprire_auto_fel.value
	return v if v in FELURI else FEL_IMPLICIT


def seteaza(minute_noi=None, fel_nou=None, config=None, configfile=None):
	"""Aceeasi schimbare pe televizor si din web. Valorile straine nu schimba nimic: ValueError cu textul pentru om.
	Salveaza setarile (configfile.save) cand s-a schimbat ceva. Intoarce True daca s-a schimbat ceva."""
	u = initConfig(config)
	if minute_noi is not None and str(minute_noi) not in [str(m) for m in MINUTE]:
		raise ValueError(_t("Intervalul ales nu e unul dintre cele de pe televizor."))
	if fel_nou is not None and fel_nou not in FELURI:
		raise ValueError(_t("Felul opririi nu e unul dintre cele de pe televizor."))
	schimbat = False
	if fel_nou is not None and u.hds_oprire_auto_fel.value != fel_nou:
		u.hds_oprire_auto_fel.value = fel_nou
		u.hds_oprire_auto_fel.save()
		schimbat = True
	if minute_noi is not None and str(u.hds_oprire_auto.value) != str(minute_noi):
		u.hds_oprire_auto.value = str(minute_noi)
		u.hds_oprire_auto.save()
		schimbat = True
	if schimbat:
		try:
			if configfile is None:
				from Components.config import configfile
			configfile.save()
		except Exception as e:
			_jurnal("setarile nu s-au salvat: %r" % (e,))
	return schimbat


def urmatoareaValoare(valori, valoare, pas=1):
	"""Valoarea de dupa (sau dinainte, pas=-1) in lista, in cerc; prima cand valoarea nu e in lista."""
	valori = [str(v) for v in valori]
	try:
		i = valori.index(str(valoare))
	except ValueError:
		return valori[0]
	return valori[(i + pas) % len(valori)]


def ramasS(acum=None):
	"""Secundele pana la oprire (fara taste de acum incolo), None cand e oprita sau inca nepornita."""
	m = minute()
	if not m or _S["ultima"] is None:
		return None
	acum = monotonic() if acum is None else acum
	return max(0, int(m * 60 - (acum - _S["ultima"])))


def descriere(config=None, SystemInfo=None):
	"""Randul de stare: „Oprire automată: după 2 ore fără nicio tastă (Standby).” sau „Oprirea automată este oprită.”"""
	m = minute(config)
	if not m:
		return _t("Oprirea automată este oprită.")
	return _t("Oprire automată: %s fără nicio tastă (%s).") % (textMinute(m), textFel(fel(config), SystemInfo))


def stare(config=None, SystemInfo=None):
	"""Pentru pagina web (GET /api/alimentare): valorile, alegerile si cat a ramas."""
	initConfig(config)
	r = ramasS()
	return {
		"minute": minute(config),
		"fel": fel(config),
		"alegeri_minute": [[v, t] for v, t in alegeriMinute()],
		"alegeri_fel": [[v, t] for v, t in alegeriFel(SystemInfo)],
		"ramas_s": r,
		"text": descriere(config, SystemInfo),
	}


# ---------------------------------------------------------------- de ce se amana

def motivAmanare(sesiune, acum=None, job_manager=None, instalare=None):
	"""Textul motivului pentru care oprirea se amana, sau "" cand se poate face acum."""
	acum = time.time() if acum is None else acum
	nav = getattr(sesiune, "nav", None)
	if nav is not None:
		try:
			if nav.getRecordings():
				return "inregistrare in curs"
		except Exception:
			pass
		rt = getattr(nav, "RecordTimer", None)
		for nume in ("getNextRecordingTime", "getNextZapTime"):
			try:
				t = getattr(rt, nume)()
			except Exception:
				continue
			if t and t > 0 and t - acum < INREGISTRARE_CURAND_S:
				return "temporizator in curand (%s)" % nume
	try:
		if job_manager is None:
			from Components.Task import job_manager
		if job_manager.getPendingJobs():
			return "lucrari in fundal"
	except Exception:
		pass
	try:
		if instalare is None:
			from Components.HdsActualizari import instalare_in_curs as instalare
		if instalare():
			return "instalare in curs"
	except Exception:
		pass
	try:
		import Screens.Standby as S
		if S.inTryQuitMainloop or getattr(S, "asteaptaInstalarea", False):
			return "o iesire e deja ceruta"
	except Exception:
		pass
	return ""


def _inStandby():
	try:
		from Screens.Standby import inStandby
		return inStandby is not None
	except Exception:
		return False


# ---------------------------------------------------------------- ceasul si tastele

def porneste(session):
	"""Din mytest.py, dupa ce s-a facut sesiunea. Nu arunca."""
	try:
		u = initConfig()
		_S["sesiune"] = session
		if not _S["pornit"]:
			# setarea schimbata pe televizor sau din web: intervalul se socoteste de atunci
			u.hds_oprire_auto.addNotifier(_laSchimbare, initial_call=False)
		_S["pornit"] = True
		_S["ultima"] = monotonic()
		_rearmeaza()
		_jurnal("pornita: %s" % (minute() and ("%d min, %s" % (minute(), fel())) or "oprita"))
	except Exception as e:
		_jurnal("nu a pornit: %r" % (e,))


def _laSchimbare(_element=None):
	"""Setarea schimbata (televizor sau web): intervalul se socoteste de acum."""
	if _S["pornit"]:
		_S["ultima"] = monotonic()
		_rearmeaza()


def _ceas():
	if _S["ceas"] is None:
		from enigma import eTimer
		c = eTimer()
		try:
			c.callback.append(_laCeas)
		except AttributeError:
			_S["legatura"] = c.timeout.connect(_laCeas)
		_S["ceas"] = c
	return _S["ceas"]


def _leagaTastele(da):
	try:
		from enigma import eActionMap
		if da and not _S["legat"]:
			eActionMap.getInstance().bindAction("", PRIO_TASTE, _tasta)
			_S["legat"] = True
		elif not da and _S["legat"]:
			eActionMap.getInstance().unbindAction("", _tasta)
			_S["legat"] = False
	except Exception as e:
		_jurnal("tastele: %r" % (e,))


def _rearmeaza(secunde=None):
	m = minute()
	if not m:
		_leagaTastele(False)
		if _S["ceas"] is not None:
			_S["ceas"].stop()
		return
	_leagaTastele(True)
	if secunde is None:
		secunde = ramasS()
		if secunde is None:
			secunde = m * 60
	_ceas().startLongTimer(max(1, int(secunde)))


def _tasta(key, flag):
	"""Orice tasta socoteste timpul de la capat. Cu fereastra numaratorii pe ecran, tasta numai o inchide: apasarea si
	celelalte steaguri ale aceleiasi taste (repetare, tinere, eliberare) se opresc aici."""
	_S["ultima"] = monotonic()
	if _S["inghite"] is not None:
		if key == _S["inghite"]:
			if flag == STEAG_ELIBERAT:
				_S["inghite"] = None
			return 1
		_S["inghite"] = None
	if _S["intrebare"] is not None:
		dlg, _S["intrebare"] = _S["intrebare"], None
		if flag == STEAG_APASAT:
			_S["inghite"] = key
		_jurnal("o tasta a oprit numaratoarea: receptorul ramane pornit")
		try:
			dlg.close(False)
		except Exception as e:
			_jurnal("fereastra numaratorii: %r" % (e,))
		_rearmeaza()
		return 1
	return 0


def _laCeas():
	m = minute()
	if not m:
		return
	r = ramasS()
	if r is not None and r > 1:
		_rearmeaza(r)
		return
	_vremea()


def _vremea():
	sesiune = _S["sesiune"]
	motiv = motivAmanare(sesiune)
	if motiv:
		_jurnal("amanata %d s: %s" % (AMANARE_S, motiv))
		_rearmeaza(AMANARE_S)
		return
	f = fel()
	if _inStandby():
		if f == "shutdown":
			_jurnal("din standby, oprire completa dupa %d min fara taste" % minute())
			_faOprirea("shutdown")
		else:
			_rearmeaza(minute() * 60)   # deja in standby: nimic de facut pana la urmatoarea tasta
		return
	_intreaba(f)


def textIntrebare(f, m=None):
	m = minute() if m is None else m
	if f == "shutdown":
		inceput = _t("Receptorul se oprește în %d de secunde: nu s-a apăsat nicio tastă %s.")
	else:
		inceput = _t("Receptorul trece în standby în %d de secunde: nu s-a apăsat nicio tastă %s.")
	return (inceput % (NUMARATOARE_S, textDeCand(m))) + "\n" + _t("Apasă orice tastă ca receptorul să rămână pornit.")


def textDeCand(m):
	"""„de o oră”, „de 2 ore”..."""
	if m == 60:
		return _t("de o oră")
	if m % 60 == 0:
		return _t("de %d ore") % (m // 60)
	return _t("de %d minute") % m


def _ascundeProtectia():
	"""Fereastra numaratorii nu ramane sub protectia ecranului (Screens/ScreenSaver.py)."""
	try:
		from Screens.InfoBar import InfoBar
		ib = InfoBar.instance
		ss = getattr(ib, "screenSaver", None)
		if ss is not None and ss.shown:
			ss.hide()
			ib.show()
	except Exception:
		pass


def _intreaba(f):
	sesiune = _S["sesiune"]
	if sesiune is None or _S["intrebare"] is not None:
		return
	try:
		from Screens.MessageBox import MessageBox
		_ascundeProtectia()
		_jurnal("numaratoarea de %d s pornita (%s)" % (NUMARATOARE_S, f))
		dlg = sesiune.openWithCallback(lambda raspuns: _dupaIntrebare(f, raspuns), MessageBox, textIntrebare(f),
			type=MessageBox.TYPE_INFO, timeout=NUMARATOARE_S, timeout_default="acum")
		_S["intrebare"] = dlg
	except Exception as e:
		_jurnal("fereastra numaratorii: %r" % (e,))
		_rearmeaza(AMANARE_S)


def _dupaIntrebare(f, raspuns):
	_S["intrebare"] = None
	if raspuns != "acum":
		_rearmeaza()
		return
	motiv = motivAmanare(_S["sesiune"])
	if motiv:
		_jurnal("amanata %d s la sfarsitul numaratorii: %s" % (AMANARE_S, motiv))
		_rearmeaza(AMANARE_S)
		return
	_faOprirea(f)


def _faOprirea(f):
	sesiune = _S["sesiune"]
	try:
		import Screens.Standby as S
		if f == "shutdown":
			if not S.inTryQuitMainloop:
				sesiune.open(S.TryQuitMainloop, 1)
		elif S.inStandby is None:
			sesiune.open(S.Standby)
		_jurnal("%s dupa %d min fara taste" % (f, minute()))
	except Exception as e:
		_jurnal("oprirea: %r" % (e,))
	_S["ultima"] = monotonic()
	_rearmeaza()

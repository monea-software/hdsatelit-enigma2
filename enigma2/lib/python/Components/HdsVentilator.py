# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsVentilator.py: ventilatorul receptorului si temperatura placii, scris de la zero (0.8.0, RW1).
#
# DIN FABRICA NU SE SCRIE NIMIC: „Automat” lasa ventilatorul in seama driverului si a microcontrolerului din fata, care il
# regleaza singure dupa temperatura, la pornire, in standby si dupa repornire (asa face si imaginea producatorului pe
# modelele de mai jos). Modulul nu scrie in /proc decat dupa ce omul alege altceva; la intoarcerea pe „Automat” pune la
# loc exact valorile citite din driver inainte de prima scriere (VALORI_DRIVER, tinute in setari).
#
# FAMILIILE, dupa nodurile pe care le face driverul (citite din modulele producatorilor, nu probate pe un receptor):
# - „pwm”: /proc/stb/fp/fan_pwm si/sau fan_vlt, de obicei si fan_speed (turatia): Dreambox DM900/DM920 (fp_hwmon.ko),
#   Vu+ Duo2 si Vu+ de dinainte de 4K. Valori hexazecimale 0-ff; „Turație maximă” scrie ff.
# - „mod”: /proc/stb/fp/fan cu „on” / „off” / „auto” (alegerile in fan_choices, unde exista). „Pornit mereu” scrie „on”.
# - „vu”: Vu+ 4K (Duo 4K, Duo 4K SE, Ultimo 4K, Solo 4K, Uno 4K/SE): driverul are tabelul temperaturii si nodurile
#   /proc/stb/system/use_fan_timer, standby_fan_off, fan_on_time, fan_off_time. In 0.8.0 numai se arata starea: nimic
#   nu se scrie acolo.
# - fara niciun nod (de pilda Amiko Viper 4K V20, emulatorul): receptorul n-are ventilator, intrarea din meniu lipseste.
#
# Components/FanControl.py (nucleul enigma2) NU se foloseste: la incarcare scria tensiunea si PWM-ul lui din fabrica (pwm 0)
# si le schimba la standby. Aici temperatura si turatia se citesc direct, iar scrierea e numai cea aleasa de om.
#
# FIRUL: totul pe firul enigma2; citirile sunt cateva fisiere mici din /proc. Fisierul nu importa nimic din enigma2 la
# incarcare: probele de pe PC pun RADACINA pe un dosar cu un /proc fals.

import os
import re

RADACINA = ""

FP = "/proc/stb/fp"
NOD_PWM = FP + "/fan_pwm"
NOD_VLT = FP + "/fan_vlt"
NOD_TURATIE = FP + "/fan_speed"
NOD_MOD = FP + "/fan"
NOD_MOD_ALEGERI = FP + "/fan_choices"
NODURI_VU = ("/proc/stb/system/use_fan_timer", "/proc/stb/system/standby_fan_off", "/proc/stb/system/fan_on_time",
	"/proc/stb/system/fan_off_time")

SENZORI = "/proc/stb/sensors"
TEMPERATURI_FP = ("/proc/stb/fp/temp_sensor_avs", "/proc/stb/fp/temp_sensor")
TERMIC = "/sys/class/thermal"

MAXIM = "ff"
_STANDBY_LEGAT = [False]


def _cale(cale):
	return RADACINA + cale


def _exista(cale):
	return os.path.exists(_cale(cale))


def _citeste(cale):
	try:
		with open(_cale(cale)) as f:
			return f.read().strip()
	except (IOError, OSError, UnicodeDecodeError):
		return None


def _scrie(cale, text):
	try:
		with open(_cale(cale), "w") as f:
			f.write(text)
		_jurnal("%s <- %s" % (cale, text))
		return True
	except (IOError, OSError) as e:
		_jurnal("%s: %r" % (cale, e))
		return False


def _jurnal(text):
	print("[HdsVentilator] %s" % text)


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


# ---------------------------------------------------------------- ce are receptorul

def familie():
	"""„mod”, „pwm”, „vu”, „turatie” (numai turatia) sau „” (fara ventilator)."""
	if _exista(NOD_MOD):
		return "mod"
	if _exista(NOD_PWM) or _exista(NOD_VLT):
		return "pwm"
	for nod in NODURI_VU:
		if _exista(nod):
			return "vu"
	if _exista(NOD_TURATIE):
		return "turatie"
	return ""


def areVentilator():
	return familie() != ""


def alegeriMod():
	"""Ce scrie driverul in fan_choices (gol: nu stim, se incearca „on”)."""
	text = _citeste(NOD_MOD_ALEGERI) or ""
	return text.split()


def alegeri(fam=None):
	"""[(valoare, text)] pentru config.hds_ventilator.mod pe acest receptor; „auto” e mereu primul."""
	fam = familie() if fam is None else fam
	rez = [("auto", _t("Automat, după temperatură (din fabrică)"))]
	if fam == "pwm":
		rez.append(("maxim", _t("Turație maximă")))
	elif fam == "mod":
		pe_driver = alegeriMod()
		if not pe_driver or "on" in pe_driver:
			rez.append(("pornit", _t("Pornit mereu")))
	return rez


def turatie():
	"""Turatia in rotatii pe minut sau None."""
	text = _citeste(NOD_TURATIE)
	if not text:
		return None
	m = re.search(r"\d+", text)
	return int(m.group(0)) if m else None


def _grade(text, impartitor=1):
	try:
		valoare = float(text.split()[0]) / impartitor
	except (ValueError, IndexError, AttributeError):
		return None
	if valoare <= 0 or valoare > 150:
		return None
	return int(round(valoare))


def temperaturi():
	"""[(nume, grade C)]: senzorii placii (/proc/stb/sensors), apoi cel din fata, apoi zonele termice ale SoC-ului."""
	rez = []
	try:
		dosare = sorted(os.listdir(_cale(SENZORI)))
	except OSError:
		dosare = []
	for d in dosare:
		if not d.startswith("temp"):
			continue
		baza = SENZORI + "/" + d
		g = _grade(_citeste(baza + "/value"))
		if g is not None:
			rez.append((_citeste(baza + "/name") or d, g))
	if not rez:
		for cale in TEMPERATURI_FP:
			g = _grade(_citeste(cale))
			if g is not None:
				rez.append((_t("Placa"), g))
				break
	try:
		zone = sorted(z for z in os.listdir(_cale(TERMIC)) if z.startswith("thermal_zone"))
	except OSError:
		zone = []
	for z in zone:
		text = _citeste(TERMIC + "/" + z + "/temp")
		g = _grade(text, 1000 if text and len(text.split()[0]) > 3 else 1)
		if g is not None:
			rez.append((_t("Procesorul") if len(zone) == 1 else "%s %s" % (_t("Procesorul"), z[12:]), g))
	return rez


def valoriDriver():
	"""Ce are driverul acum pe nodurile pe care le-am putea scrie (text, ca in /proc)."""
	rez = {}
	for nume, cale in (("pwm", NOD_PWM), ("vlt", NOD_VLT), ("mod", NOD_MOD)):
		text = _citeste(cale)
		if text is not None:
			rez[nume] = text.split()[0] if text.split() else text
	return rez


def stare():
	"""Pentru ecran si pentru web: tot ce se vede, fara nicio scriere."""
	fam = familie()
	rez = {"familie": fam, "are": fam != "", "temperaturi": temperaturi(), "turatie": turatie(),
		"driver": valoriDriver(), "alegeri": alegeri(fam), "mod": "auto"}
	try:
		rez["mod"] = _cfg().mod.value
	except Exception:
		pass
	if fam == "vu":
		rez["vu"] = dict((n.rsplit("/", 1)[1], _citeste(n)) for n in NODURI_VU if _exista(n))
	return rez


# ---------------------------------------------------------------- setarile

def _cfg():
	from Components.config import config
	return config.hds_ventilator


def initConfig():
	"""config.hds_ventilator si SystemInfo HdsVentilator (intrarea din menu.xml)."""
	from Components.config import config, ConfigSubsection, ConfigSelection, ConfigText
	if "hds_ventilator" not in config.content.items:
		c = ConfigSubsection()
		config.hds_ventilator = c
		c.mod = ConfigSelection(default="auto", choices=alegeri())
		c.driver = ConfigText(default="", fixed_size=False)   # VALORI_DRIVER: „pwm=..;vlt=..;mod=..” de dinainte
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsVentilator"] = areVentilator()
	except Exception as e:
		_jurnal("SystemInfo: %r" % (e,))


def _tineMinteDriver(c):
	if c.driver.value:
		return
	v = valoriDriver()
	c.driver.value = ";".join("%s=%s" % (k, v[k]) for k in sorted(v))
	c.driver.save()


def _valoriTinute(c):
	rez = {}
	for bucata in (c.driver.value or "").split(";"):
		if "=" in bucata:
			k, v = bucata.split("=", 1)
			rez[k] = v
	return rez


def aplica(c=None):
	"""Scrie ce a ales omul. „auto” cu valori tinute minte: le pune la loc si le uita. „auto” fara: nimic."""
	c = c or _cfg()
	mod = c.mod.value
	if mod == "auto":
		tinute = _valoriTinute(c)
		if not tinute:
			return False
		for nume, cale in (("pwm", NOD_PWM), ("vlt", NOD_VLT), ("mod", NOD_MOD)):
			if nume in tinute and _exista(cale):
				_scrie(cale, tinute[nume])
		c.driver.value = ""
		c.driver.save()
		return True
	_tineMinteDriver(c)
	if mod == "maxim":
		scris = False
		for cale in (NOD_VLT, NOD_PWM):
			if _exista(cale):
				scris = _scrie(cale, MAXIM) or scris
		return scris
	if mod == "pornit":
		return _scrie(NOD_MOD, "on")
	return False


def seteaza(valoare, c=None, configfile=None):
	"""Din ecran si din web: valoarea aleasa, salvata si aplicata pe loc. False cand nu e o alegere a receptorului."""
	c = c or _cfg()
	if valoare not in [a[0] for a in alegeri()]:
		return False
	c.mod.value = valoare
	c.mod.save()
	aplica(c)
	if configfile is None:
		try:
			from Components.config import configfile
		except ImportError:
			configfile = None
	if configfile is not None:
		configfile.save()
	return True


def _laStandby(element=None):
	"""Dupa standby driverul isi poate pune iar valorile lui: alegerea omului se scrie din nou la iesire."""
	import sys
	ecran = getattr(sys.modules.get("Screens.Standby"), "inStandby", None)
	if ecran is None:
		return
	try:
		if _laIesireStandby not in ecran.onClose:
			ecran.onClose.append(_laIesireStandby)
	except AttributeError:
		pass


def _laIesireStandby():
	try:
		if _cfg().mod.value != "auto":
			aplica()
	except Exception as e:
		_jurnal("iesirea din standby: %r" % (e,))


def porneste(session=None):
	"""La pornire: numai alegerea omului (din fabrica nimic) si legatura la iesirea din standby."""
	try:
		c = _cfg()
	except Exception:
		return
	if c.mod.value != "auto":
		aplica(c)
	if not _STANDBY_LEGAT[0] and areVentilator():
		from Components.config import config
		config.misc.standbyCounter.addNotifier(_laStandby, initial_call=False)
		_STANDBY_LEGAT[0] = True

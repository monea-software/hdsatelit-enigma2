# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Un singur stapan pentru fiecare parte a afisajului.

import os
import sys
import time
import weakref

RESURSE = ("text", "lcd", "lumina", "live", "pictograme", "alimentare", "leduri")
LCD_RESURSE = tuple(r for r in RESURSE if r != "leduri")
_ocupanti = {}
_summary = set()
_proc_cache = (0, [])
# Cautarea altor programe cu dispozitivul afisajului deschis (/proc/*/fd): o data la atatea secunde. Pe Vu+ Solo SE
# tinea firul principal 3 din 40 de esantioane la pasul vechi de 2 s (raportul de procesor 239122).
PROC_INTERVAL_S = 5
_leduri = weakref.WeakSet()
_ledPermis = None


def N_(text):
	return text


TEXTE = (
	N_("Plugin cu acces direct"), N_("Tema de afisaj aleasa"),
	N_("Pluginul sau tema de afisaj"), N_("Program extern"),
	N_("Afisaj folosit de: %s"), N_("HD Satelit"),
)


def _valoare(obiect, nume, implicit=None):
	# ConfigSubsection.__getattr__ poate crea copii. Citim numai ce exista.
	date = getattr(obiect, "__dict__", {})
	continut = date.get("content")
	items = getattr(continut, "items", {})
	if isinstance(items, dict) and nume in items:
		el = items[nume]
	else:
		el = date.get(nume, implicit)
	return getattr(el, "value", el)


def _anunta():
	m = sys.modules.get("Components.HdsAfisaj")
	a = getattr(m, "_afisaj", None)
	if a is not None and not a.oprit:
		a.timer.start(0, True)


def ocupa(nume, resurse=RESURSE, summary=False):
	"""Un plugin anunta ce foloseste, inainte de prima sa scriere."""
	resurse = tuple(resurse)
	if not nume or any(r not in RESURSE for r in resurse):
		raise ValueError("Resursa de afisaj necunoscuta")
	_ocupanti[str(nume)] = resurse
	if summary:
		_summary.add(str(nume))
	else:
		_summary.discard(str(nume))
	_anunta()


def elibereaza(nume):
	"""Pluginul a terminat scrierile. Afisajul nostru poate reveni."""
	_ocupanti.pop(nume, None)
	_summary.discard(nume)
	_anunta()


def actualizeazaLeduri():
	"""LED-urile proprii revin la starea REC/standby dupa cedare."""
	global _ledPermis
	permis = permite("leduri")
	if permis != _ledPermis:
		_ledPermis = permis
		if permis:
			for led in list(_leduri):
				led.changed()


def _pluginuri():
	"""Nu importam pluginuri: unele scriu chiar in timpul importului."""
	rez = []
	m = sys.modules.get("Plugins.Extensions.LCD4linux.plugin")
	c = getattr(m, "LCD4linux", None)
	if c is not None and _valoare(c, "Enable", False):
		tipuri = {str(_valoare(c, "LCDType%d" % i, "0"))[:1]
			for i in (1, 2, 3)}
		if "9" in tipuri:
			rez.append(("LCD4linux", ("lcd", "text", "lumina", "live", "alimentare")))
		elif "5" in tipuri:
			rez.append(("LCD4linux", ("lcd", "lumina", "live", "alimentare")))
		elif "4" in tipuri:
			# TFT-ul are iesire proprie, dar poate imparti luminozitatea.
			rez.append(("LCD4linux", ("lumina",)))
	m = sys.modules.get("Plugins.SystemPlugins.VFDControl.plugin")
	if getattr(m, "ChannelnumberInstance", None) is not None:
		if hasattr(m, "gigaLED"):
			# Textul MCU este separat; lumina si LED-urile pot fi comune.
			cfg = getattr(sys.modules.get("Components.config"), "config", None)
			giga = _valoare(_valoare(cfg, "plugins"), "VFD_Giga")
			resurse = ("lumina", "leduri") if _valoare(giga, "setLed", False) else ("lumina",)
			rez.append(("GigaBlueVFDControl", resurse))
		else:
			# Off poate scrie in continuare puncte sau spatii. Nu e oprire.
			rez.append(("VFDControl", ("text", "lcd", "live", "alimentare")))
			if hasattr(m, "iniVfd"):
				# Varianta cu LED poate clipi si prin luminozitatea LCD.
				rez.append(("VFDControl", ("lumina",)))
	m = sys.modules.get("Plugins.Extensions.PermanentVfdClock.plugin")
	if getattr(m, "gTimer", None) is not None:
		cfg = getattr(sys.modules.get("Components.config"), "config", None)
		plugins = _valoare(cfg, "plugins")
		ceas = _valoare(plugins, "PermanentVfdClock")
		standby = getattr(sys.modules.get("Screens.Standby"), "inStandby", None)
		if _valoare(ceas, "enabled", False) and not standby:
			rez.append(("PermanentVfdClock", ("text", "lcd", "live", "alimentare")))
	return rez


def _tema():
	m = sys.modules.get("skin")
	f = getattr(m, "afisajExternActiv", None)
	return f() if callable(f) else ""


def _summaryPlugin():
	m = sys.modules.get("Components.HdsAfisaj")
	a = getattr(m, "_afisaj", None)
	s = getattr(getattr(a, "session", None), "summary", None)
	if s is None:
		return False
	if type(s).__module__.startswith("Plugins."):
		return True
	parent = getattr(s, "parent", None)
	return "skinSummary" in getattr(parent, "__dict__", {})


def _lcdBlocat():
	m = sys.modules.get("enigma")
	clasa = getattr(m, "eDBoxLCD", None)
	if clasa is None:
		return False
	lcd = clasa.getInstance()
	return bool(lcd is not None and getattr(lcd, "islocked", lambda: False)())


def _resurseProc(cale):
	if cale == "/proc/stb/power/vfd":
		return ("alimentare",)
	if cale.startswith("/proc/stb/fp/led"):
		return ("leduri",)
	if cale == "/proc/stb/fp/oled_brightness":
		return ("lumina",)
	if cale.startswith(("/proc/stb/lcd/", "/proc/vfd")):
		nume = os.path.basename(cale)
		if "brightness" in nume or "dimm" in nume:
			return ("lumina",)
		if "symbol" in nume or "icon" in nume:
			return ("pictograme",)
		if cale.startswith("/proc/vfd"):
			return ("text",)
		return ("lcd", "live")
	return ()


def _procese():
	"""Alte procese cu dispozitivul deschis; citire rara si limitata."""
	global _proc_cache
	acum = time.monotonic()
	if 0 <= acum - _proc_cache[0] < PROC_INTERVAL_S:
		return _proc_cache[1]
	rez = []
	try:
		piduri = os.listdir("/proc")
	except OSError:
		return []
	dispozitive = {
		os.path.realpath("/dev/dbox/lcd0"): LCD_RESURSE,
		os.path.realpath("/dev/dbox/oled0"): LCD_RESURSE,
		os.path.realpath("/dev/lcd2"): ("lcd", "lumina", "live"),
		os.path.realpath("/dev/vfd"): ("text", "pictograme", "alimentare"),
	}
	for pid in [p for p in piduri if p.isdigit() and p != str(os.getpid())][:128]:
		try:
			dosar = "/proc/%s/fd" % pid
			folosite = set()
			for fd in os.listdir(dosar)[:32]:
				# legatura din /proc/PID/fd e deja calea adevarata a fisierului deschis (nucleul a rezolvat legaturile
				# la deschidere): un singur apel readlink, fata de realpath, care facea lstat pe fiecare bucata a caii
				try:
					cale = os.readlink(os.path.join(dosar, fd))
				except OSError:
					continue
				resurse = dispozitive.get(cale) or _resurseProc(cale)
				if not resurse:
					continue
				try:
					with open("/proc/%s/fdinfo/%s" % (pid, fd)) as f:
						flags = next(l.split()[1] for l in f if l.startswith("flags:"))
					if int(flags, 8) & os.O_ACCMODE == os.O_RDONLY:
						continue
				except (OSError, StopIteration, ValueError):
					pass
				folosite.update(resurse)
			if folosite:
				rez.append(("Program extern", tuple(sorted(folosite))))
		except OSError:
			continue
	_proc_cache = (acum, rez)
	return rez


def stare(color=False, mod=None):
	if mod is None:
		m = sys.modules.get("Components.config")
		c = _valoare(getattr(m, "config", None), "hds_afisaj")
		mod = _valoare(c, "control_afisaj", "auto")
	proprietari = [(n, r) for n, r in _ocupanti.items()]
	pluginuri = _pluginuri()
	procese = _procese()
	proprietari.extend(pluginuri)
	proprietari.extend(procese)
	if _lcdBlocat():
		proprietari.append(("Plugin cu acces direct", LCD_RESURSE))
	tema = _tema()
	if tema:
		# O tema ocupa numai desenul LCD, nu cifrele ori semnele VFD.
		proprietari.append(("Tema de afisaj aleasa", ("lcd", "live")))
	summary = _summaryPlugin()
	if summary:
		proprietari.append(("Pluginul sau tema de afisaj", ("lcd", "live")))
	if mod == "extern":
		proprietari.append(("Pluginul sau tema de afisaj", RESURSE))
	# Separat de lock(): nu deblocam niciodata lacatul altui plugin.
	m = sys.modules.get("enigma")
	clasa = getattr(m, "eDBoxLCD", None)
	if clasa is not None:
		lcd = clasa.getInstance()
		setare = getattr(lcd, "setHdsUpdate", None)
		if callable(setare):
			motor = getattr(sys.modules.get("Components.HdsAfisaj"), "_afisaj", None)
			cifre = motor is not None and not hasattr(motor, "infoColor")
			direct = any("lcd" in rs and n not in _summary
				for n, rs in _ocupanti.items())
			# Tipul 5 deseneaza prin Summary; celelalte scriu direct.
			direct = direct or any("lcd" in rs and "text" in rs
				for n, rs in pluginuri)
			direct = direct or any("lcd" in rs for n, rs in procese)
			direct = direct or (mod == "extern" and not (tema or summary))
			setare(not (cifre or direct))
	folosite = {r for n, rs in proprietari for r in rs}
	continut = "lcd" if color else "text"
	cedat = continut in folosite
	# Traducerea ramane aceeasi pe ecran si in pagina web.
	m = sys.modules.get("Components.HdsAfisaj")
	tr = getattr(m, "_", lambda text: text)
	nume = list(dict.fromkeys(tr(n) for n, r in proprietari))
	if not cedat:
		nume.insert(0, tr("HD Satelit"))
	text = tr("Afisaj folosit de: %s") % ", ".join(nume)
	return {"text": text, "cedat": cedat,
		"proprietari": [{"nume": tr(n), "resurse": list(r)}
			for n, r in proprietari], "resurse": sorted(folosite)}


def permite(resursa, color=None):
	if color is None:
		m = sys.modules.get("Components.HdsAfisaj")
		color = bool(getattr(m, "esteColor", lambda: False)())
	return resursa not in stare(color=color)["resurse"]

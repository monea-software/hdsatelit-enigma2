# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDispozitiveIntrare.py: logica ecranului "Remote Control Setup" (Screens/InputDeviceSetup.py:
# InputDeviceSelection, InputDeviceSetup), aceeasi pe televizor si in interfata web (HdsWebControl/intrari_web.py,
# pagina /dispozitive-intrare):
# - lista(): dispozitivele de intrare gasite la pornire (/dev/input/event*, Components/InputDevice.py), cu felul lor si
#   setarile config.inputDevices.<dispozitiv>.* (enabled, repeat, delay, name);
# - laOprire(): cand "Change repeat and delay settings?" trece pe Nu, intervalul, intarzierea si numele se intorc la
#   valorile implicite;
# - salveazaNumele(): la "Da" pe intrebarea "Use this input device settings?" numele salvat devine numele
#   dispozitivului;
# - aplica(): ce face ecranul de la prima schimbare pana la Verde si Da, intr-un singur pas (pentru web): valorile puse
#   cu dispozitivul ales ca "currentDevice" (notificatorii din InputDevice.py le trimit dispozitivului), numele, apoi
#   save() pe randurile care se vad pe ecran si configfile.save(), ca la inchiderea meniului.
#
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC dau iInputDevices si config).

import re

NUME_DISPOZITIV = re.compile(r"^event[0-9]{1,3}$")


def _d(D=None):
	if D is not None:
		return D
	from Components.InputDevice import iInputDevices
	return iInputDevices


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config
	return config


def sectiune(dispozitiv, config=None):
	"""config.inputDevices.<dispozitiv>, sau None (nume strain, dispozitiv fara setari)."""
	config = _config(config)
	if not isinstance(dispozitiv, str) or not NUME_DISPOZITIV.match(dispozitiv):
		return None
	try:
		if dispozitiv not in config.inputDevices.content.items:
			return None
		return getattr(config.inputDevices, dispozitiv)
	except (AttributeError, KeyError):
		return None


def lista(D=None, config=None):
	"""[(dispozitivul, numele, felul)] in ordinea ecranului de pe televizor, numai cele cu setari."""
	D = _d(D)
	config = _config(config)
	rez = []
	for x in D.getDeviceList():
		if sectiune(x, config) is not None:
			rez.append((x, D.getDeviceName(x), D.getDeviceAttribute(x, "type")))
	return rez


def laOprire(s):
	"""Intervalul, intarzierea si numele la valorile implicite (randul "Change repeat and delay settings?" pe Nu)."""
	s.repeat.setValue(s.repeat.default)
	s.delay.setValue(s.delay.default)
	s.name.setValue(s.name.default)


def salveazaNumele(dispozitiv, D=None, config=None):
	"""Da pe "Use this input device settings?": numele salvat e numele dispozitivului."""
	D = _d(D)
	s = sectiune(dispozitiv, config)
	s.name.setValue(D.getDeviceAttribute(dispozitiv, "name"))
	s.name.save()


def aplica(dispozitiv, activ, repetare=None, intarziere=None, D=None, config=None, configfile=None):
	"""Setarile unui dispozitiv, puse si salvate ca pe televizor. `repetare` / `intarziere` (ms) se pun numai cu
	`activ` (pe televizor randurile lor se vad numai atunci); None = valoarea de acum."""
	D = _d(D)
	config = _config(config)
	s = sectiune(dispozitiv, config)
	vechi = D.currentDevice
	D.currentDevice = dispozitiv
	try:
		s.enabled.setValue(bool(activ))
		if activ:
			if repetare is not None:
				s.repeat.setValue(int(repetare))
			if intarziere is not None:
				s.delay.setValue(int(intarziere))
		else:
			laOprire(s)
		salveazaNumele(dispozitiv, D, config)
		# Verde: save() pe randurile din lista ecranului
		s.enabled.save()
		if activ:
			s.repeat.save()
			s.delay.save()
	finally:
		D.currentDevice = vechi
	if configfile is None:
		from Components.config import configfile
	configfile.save()

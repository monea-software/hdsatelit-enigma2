# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# TempFanControl.py: ecranul „Ventilatorul”: temperatura placii, turatia si purtarea ventilatorului. Cod propriu, scris de
# la zero (0.8.0, RW1).
#
# Totul vine din Components/HdsVentilator.py: din fabrica „Automat” (driverul il regleaza dupa temperatura, nimic scris);
# pe modelele care au de unde, si „Turație maximă” sau „Pornit mereu”, salvate si scrise la VERDE. Valorile se citesc din
# nou la 3 secunde cat e deschis ecranul. Components/FanControl.py (nucleul) nu se mai importa de aici.
#
# Numele „TempFanControl” are panoul gata in skin-ul HDSatelit (HDSatelit/skin.xml): lista „config” in stanga, randurile
# SensorFanText0-9 si SensorTempText0-5 in dreapta, fiecare ascuns cand nu e folosit (conditional=).
# In web: /ventilator (Plugins/Extensions/HdsWebControl/ventilator_web.py), cu aceleasi alegeri.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry
from Components.Sources.StaticText import StaticText
from Components import HdsVentilator as V

RANDURI_VENTILATOR = 10
RANDURI_TEMPERATURA = 6
REIMPROSPATARE_MS = 3000


def randuriVentilator(s):
	"""Textele din dreapta, sus: ce face ventilatorul acum (din stare(), fara scrieri)."""
	if not s["are"]:
		return [_("Niciun ventilator detectat pe acest receptor."), _("Nimic de reglat aici.")]
	rez = []
	if s["mod"] == "auto":
		rez.append(_("Reglat de receptor după temperatură."))
	else:
		rez.append(dict(s["alegeri"]).get(s["mod"], s["mod"]))
	if s["turatie"] is not None:
		rez.append(_("Turație curentă: %d RPM") % s["turatie"])
	d = s.get("driver") or {}
	if "pwm" in d:
		rez.append("PWM: %s" % d["pwm"])
	if "vlt" in d:
		rez.append(_("Tensiune: %s") % d["vlt"])
	if s["familie"] == "vu":
		vu = s.get("vu") or {}
		if vu.get("standby_fan_off") == "1":
			rez.append(_("În standby ventilatorul se oprește."))
	return rez


def randuriTemperatura(s):
	if not s["temperaturi"]:
		return [_("Temperatura nu se poate citi pe acest receptor.")] if s["are"] else []
	return ["%s: %d °C" % (nume, grade) for nume, grade in s["temperaturi"]]


class TempFanControl(Screen, ConfigListScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Ventilatorul"))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		for i in range(RANDURI_VENTILATOR):
			self["SensorFanText%d" % i] = StaticText("")
		for i in range(RANDURI_TEMPERATURA):
			self["SensorTempText%d" % i] = StaticText("")

		V.initConfig()
		self._cfg = V._cfg()
		self._initial = self._cfg.mod.value
		lista = []
		if len(V.alegeri()) > 1:
			lista.append(getConfigListEntry(_("Ventilatorul"), self._cfg.mod))
		self["config"].list = lista

		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.anuleaza,
			"red": self.anuleaza,
			"green": self.salveaza,
			"ok": self.salveaza,
		}, -2)

		from enigma import eTimer
		self._ceas = eTimer()
		self._ceas.callback.append(self.citeste)
		self.onShown.append(self.citeste)
		self.onClose.append(self._ceas.stop)

	def citeste(self):
		try:
			s = V.stare()
			sus, jos = randuriVentilator(s), randuriTemperatura(s)
		except Exception as eroare:
			sus, jos = [_("Eroare la citirea ventilatorului:"), str(eroare)], []
		for i in range(RANDURI_VENTILATOR):
			self["SensorFanText%d" % i].setText(sus[i] if i < len(sus) else "")
		for i in range(RANDURI_TEMPERATURA):
			self["SensorTempText%d" % i].setText(jos[i] if i < len(jos) else "")
		self._ceas.start(REIMPROSPATARE_MS, True)

	def salveaza(self):
		V.seteaza(self._cfg.mod.value, self._cfg)
		self.close(True)

	def anuleaza(self):
		self._cfg.mod.value = self._initial
		self.close(False)

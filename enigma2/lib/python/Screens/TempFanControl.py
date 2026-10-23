# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# TempFanControl.py: Ventilatorul (tensiune/PWM, functionare normala si standby).
# Cod 100% propriu, scris de la zero.
#
# DE CE UN ECRAN NOU, CAND MECANISMUL DEJA EXISTA: `Components/FanControl.py` (cod comun,
# mostenit din arborele Dreambox, NEATINS aici) are deja TOT ce trebuie -- detectie reala a
# ventilatorului (`/proc/stb/fp/fan_vlt`, `fan_pwm`, `fan_speed`), campuri de configurare
# (`config.fans[0].vlt/.pwm/.vlt_standby/.pwm_standby`) CU scriere directa pe driver la fiecare
# schimbare (notifiers deja legate la creare), plus comutare automata intre valorile normale si
# cele de standby. Singurul lucru cu adevarat lipsa era
# ECRANUL -- userul n-avea de unde sa regleze
# aceste valori deja functionale. Acest fisier NU reimplementeaza nimic din mecanism, doar il
# arata.
#
# FARA SKIN PROPRIU, DELIBERAT (gasit cu dovada reala pe emulator, nu presupunere): numele
# "TempFanControl" e deja definit in skin-ul global HDSatelit
# (HDSatelit/skin.xml) -- pregatit ACOLO,
# nefolosit inca de niciun cod Python, ca parte a lucrului de compatibilitate cu alte imagini
# (alte imagini folosesc acelasi nume standard pentru exact aceasta functie). Un `skin = """..."""`
# propriu aici ar fi fost COMPLET IGNORAT de motorul de skin (skin-ul global caștigă la potrivire
# de nume, exact tiparul deja documentat la "HdsSoftwareUpdate") -- ecranul s-ar fi deschis
# FARA nicio eroare, dar INVIZIBIL (asa a fost gasit bug-ul: testat in emulator, titlu si butoane
# vizibile, restul complet gol -- panoul din skin-ul global folosea alte nume de sursa decat cele
# inventate initial aici). Reparat prin ADAPTARE la sursele STANDARD deja pregatite in skin:
# `SensorFanText0`-`SensorFanText9` (cate un rand text per ventilator, pana la 9) si
# `SensorTempText0`-`SensorTempText5` (senzori de temperatura -- NEFOLOSITE aici, FanControl.py
# nu are deloc citire de temperatura, doar turatie/tensiune/PWM). Fiecare rand e `conditional=` pe
# propriul nume de sursa -- randurile nefolosite raman ascunse automat, fara cod suplimentar.
#
# ONESTITATE, cf. codului citit direct in `FanControl.py`: "ATM there's only support for one
# fan" -- un singur ventilator (fanid 0), nu o lista. Daca receptorul nu are deloc ventilator
# (`getFanCount() == 0` -- valabil si pe Amiko Viper 4K V20 daca n-are unul, si intotdeauna in
# emulatorul PC), ecranul spune asta clar, nu arata controale inutile sau false.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry
from Components.Sources.StaticText import StaticText
from Components.FanControl import fancontrol


class TempFanControl(Screen, ConfigListScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Ventilatorul"))

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))

		self._campuri = []
		self.list = []

		try:
			randuri = self._construieste()
		except Exception as eroare:
			# HDSatelit: plasa de siguranta -- daca `Components.FanControl` (cod comun,
			# neatins) se comporta neasteptat pe un driver necunoscut, ecranul arata mesajul, nu
			# ramane gol tacut.
			randuri = [_("Eroare la citirea ventilatorului:"), str(eroare)]

		# SensorFanText0..9: doar cate randuri chiar avem (restul raman ascunse, cf. `conditional=`
		# din skin -- nu trebuie "curatate" explicit, doar nefolosite).
		for i, text in enumerate(randuri[:10]):
			self["SensorFanText%d" % i] = StaticText(text)

		self["config"].list = self.list
		self._initiale = [c.value for c in self._campuri]

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.anuleaza,
				"red": self.anuleaza,
				"green": self.salveaza,
			}, -2)

	def _construieste(self):
		"""Intoarce lista de randuri text (pentru SensorFanTextN) si populeaza self.list/self._campuri
		(pentru config) cat timp face asta."""
		if fancontrol.getFanCount() == 0:
			# randurile din dreapta (SensorFanTextN) sunt `noWrap="1"`, o singura linie scurta
			# fiecare -- de-aici doua randuri scurte, nu unul lung care s-ar taia.
			return [
				_("Niciun ventilator detectat pe acest receptor."),
				_("Nimic de reglat aici."),
			]

		cfg = fancontrol.getConfig(0)
		are_control = fancontrol.hasFanControl(0)
		are_rpm = fancontrol.hasRPMSensor(0)
		randuri = []

		if are_control:
			self.list = [
				getConfigListEntry(_("Tensiune ventilator (funcționare normală)"), cfg.vlt),
				getConfigListEntry(_("PWM ventilator (funcționare normală)"), cfg.pwm),
				getConfigListEntry(_("Tensiune ventilator (standby)"), cfg.vlt_standby),
				getConfigListEntry(_("PWM ventilator (standby)"), cfg.pwm_standby),
			]
			self._campuri = [cfg.vlt, cfg.pwm, cfg.vlt_standby, cfg.pwm_standby]
			randuri.append(_("Se aplică direct pe hardware, la fiecare schimbare."))
			randuri.append(_("„Standby” pornește automat fără nicio înregistrare activă."))
		else:
			randuri.append(_("Senzor de turație prezent, dar fără control tensiune/PWM."))

		if are_rpm:
			try:
				randuri.append(_("Turație curentă: %d RPM") % fancontrol.getFanSpeed(0))
			except (IOError, OSError, ValueError):
				pass

		return randuri

	def salveaza(self):
		for c in self._campuri:
			c.save()
		self.close(True)

	def anuleaza(self):
		for c, valoare in zip(self._campuri, self._initiale):
			c.value = valoare
		self.close(False)

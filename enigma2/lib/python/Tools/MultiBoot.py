# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Tools/MultiBoot.py: numele cerut de pluginurile scrise pentru celelalte imagini Enigma2 (`from Tools.MultiBoot import
# MultiBoot`; interfetele web straine, pluginurile de pornire multipla, copiile de imagine) ca sa afle daca receptorul porneste mai multe imagini si din ce loc
# ruleaza acum (OEA4, 11.11.2026). NUMAI CITIRE: locurile le stie Components/HdsPornireMultipla.py (acelasi lucru il
# arata ecranul nostru Standby si repornire > Alte imagini); alegerea si scrierea unui loc raman numai in ecranul nostru,
# deci aici nu exista nicio functie care scrie pe partitia de pornire.
import os

STARTUP_FILE = "STARTUP"
STARTUP_RECOVERY = "STARTUP_RECOVERY"


class MultiBootClass:
	def _modul(self):
		from Components import HdsPornireMultipla
		return HdsPornireMultipla

	def canMultiBoot(self):
		try:
			return bool(self._modul().disponibil())
		except Exception as e:
			print("[MultiBoot] canMultiBoot: %r" % (e,))
			return False

	def getBootDevice(self):
		try:
			return self._modul().dosarBoot()
		except Exception:
			return None

	def _startupuri(self):
		dosar = self.getBootDevice()
		if not dosar:
			return dosar, []
		try:
			return dosar, self._modul().startupuri(dosar)
		except Exception as e:
			print("[MultiBoot] startupuri: %r" % (e,))
			return dosar, []

	def getBootSlots(self):
		"""{"1": {"startupfile": "STARTUP_1"}, ...}: locurile de pe partitia de pornire, fara sa monteze ceva."""
		if not self.canMultiBoot():
			return {}
		dosar, lista = self._startupuri()
		return dict((n, {"startupfile": nume}) for (n, nume, date) in lista)

	def getCurrentSlotCode(self):
		"""Locul ales acum: STARTUP_N cu acelasi continut ca STARTUP; "" cand nu se stie."""
		dosar, lista = self._startupuri()
		if not dosar:
			return ""
		try:
			with open(os.path.join(dosar, STARTUP_FILE), "rb") as f:
				ales = f.read(4096)
		except (IOError, OSError):
			return ""
		for (n, nume, date) in lista:
			if date == ales:
				return n
		return ""

	def getCurrentSlotAndBootCodes(self):
		return (self.getCurrentSlotCode(), "")

	def getCurrentBootMode(self):
		return ""

	def hasRecovery(self):
		dosar = self.getBootDevice()
		return bool(dosar) and os.path.isfile(os.path.join(dosar, STARTUP_RECOVERY))

	def getBootCodeDescription(self, bootCode=None):
		return ""

	def getStartupFile(self, slotCode=None):
		return "STARTUP_%s" % (slotCode or self.getCurrentSlotCode())

	def hasRootSubdir(self, slotCode=None):
		return False

	def getSlotImageList(self, callback):
		"""Lista imaginilor din locuri o arata ecranul nostru; aici raspunsul e lista goala, imediat."""
		if callback:
			callback({})


MultiBoot = MultiBootClass()

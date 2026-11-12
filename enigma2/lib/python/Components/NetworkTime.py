# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NetworkTime.py: numele pe care pluginurile straine (AutoBouquetsMaker, OpenTV Zapper) il importa ca sa afle cand s-a
# schimbat ora receptorului: `from Components.NetworkTime import ntpsyncpoller` si `ntpsyncpoller.addTimeUpdatedCallback(f)`.
# La noi ora o tine imaginea (Components/HdsCeas.py: transponderele, NTP, HTTPS); modulul acesta nu sincronizeaza nimic,
# numai anunta pluginurile: la fiecare semnal m_timeUpdated din C++ (ora sigura, ora schimbata) cheama functiile lor, o
# data pentru fiecare salt de peste 60 s, ca imaginile pentru care sunt scrise pluginurile.
#   ntpSyncPoller / ntpsyncpoller       acelasi obiect (ambele nume sunt cerute)
#   addTimeUpdatedCallback(f), removeTimeUpdatedCallback(f), onTimeUpdated (lista)
#   startTimer(), stopTimer(), timeCheck()   cerute de unele pluginuri; aici numai verifica saltul orei
from time import time

PRAG_SALT = 60


class NTPSyncPoller:
	def __init__(self):
		self.onTimeUpdated = []
		self.previousTime = time()
		self._legat = False

	def _leaga(self):
		"""m_timeUpdated se leaga la prima cerere a unui plugin (la import enigma poate lipsi, de pilda in probe)"""
		if self._legat:
			return
		try:
			from enigma import eDVBLocalTimeHandler
			eDVBLocalTimeHandler.getInstance().m_timeUpdated.get().append(self.timeCheck)
			self._legat = True
		except Exception as e:
			print("[NetworkTime] m_timeUpdated: %r" % (e,))

	def timeCheck(self):
		acum = time()
		if acum > 10000 and abs(acum - self.previousTime) > PRAG_SALT:
			for f in list(self.onTimeUpdated):
				if callable(f):
					try:
						f()
					except Exception as e:
						print("[NetworkTime] functia pluginului %r: %r" % (f, e))
		self.previousTime = acum

	def startTimer(self):
		self._leaga()

	def stopTimer(self):
		pass

	def addTimeUpdatedCallback(self, func):
		self._leaga()
		if func not in self.onTimeUpdated:
			self.onTimeUpdated.append(func)

	def removeTimeUpdatedCallback(self, func):
		if func in self.onTimeUpdated:
			self.onTimeUpdated.remove(func)


ntpSyncPoller = NTPSyncPoller()
ntpsyncpoller = ntpSyncPoller

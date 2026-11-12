# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Sursele global.OnlineStableUpdateState si global.OnlineUnstableUpdateState, cerute de temele scrise pentru imaginile
# OE-Alliance (12 teme Novum din feedurile OE-A, lotul TOT, 12.11.2026): boolean = exista o actualizare a imaginii.
# Idee din sursele GPL enigma2 (Components/Sources/OnlineUpdate.py); codul e nou: starea vine din actualizarile HD Satelit
# (Components/HdsActualizari: ultima cautare, fara cereri noi in retea). Canalul „unstable” nu exista la noi: e mereu fals.
from Components.Element import cached
from Components.Sources.Source import Source


class OnlineUpdateCheck(Source):
	stabil = True

	def __init__(self):
		Source.__init__(self)
		self._legat = False

	def _actualizari(self):
		try:
			from Components.HdsActualizari import actualizari
		except Exception:
			return None
		if not self._legat:
			self._legat = True
			actualizari.ascultatori.append(self._schimbat)
		return actualizari

	def _schimbat(self):
		self.changed((self.CHANGED_ALL,))

	@cached
	def getBoolean(self):
		if not self.stabil:
			return False
		a = self._actualizari()
		if a is None:
			return False
		try:
			from Components.HdsActualizari import DISPONIBILA
			return (a.rezultat or {}).get("stare") == DISPONIBILA
		except Exception:
			return False

	boolean = property(getBoolean)

	def destroy(self):
		if self._legat:
			try:
				from Components.HdsActualizari import actualizari
				if self._schimbat in actualizari.ascultatori:
					actualizari.ascultatori.remove(self._schimbat)
			except Exception:
				pass
			self._legat = False
		Source.destroy(self)


class OnlineUpdateStableCheck(OnlineUpdateCheck):
	stabil = True


class OnlineUpdateUnstableCheck(OnlineUpdateCheck):
	stabil = False

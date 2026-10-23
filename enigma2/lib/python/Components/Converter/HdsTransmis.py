# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTransmis.py: semnul "in retea" din bara de informatii si din a doua bara, cat canalul de pe televizor e transmis
# acum spre un browser sau un player extern (Components/HdsTransmisie.py, Manager.transmise: exact inregistrarile care
# cedeaza la zap, deci semnul si lista de canale nu se pot desparti).
#   <convert type="HdsTransmis">Activ</convert>   adevarat cat canalul televizorului e transmis (cu ConditionalShowHide)
#   <convert type="HdsTransmis">Text</convert>    textul semnului, cu litere mari, cat e transmis; altfel ""
# Se reciteste la evenimentele sursei (session.CurrentService: zap, pornirea serviciului) si cand porneste sau se
# opreste o transmisie (Manager.urmaresteTransmise, pe firul principal).

from Components.Converter.Converter import Converter
from Components.Element import cached


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _manager():
	"""Managerul transmisiilor, sau None: pe alte imagini (skinul instalat ca extensie) modulul nu exista si semnul
	ramane stins."""
	try:
		from Components import HdsTransmisie
	except ImportError:
		return None
	try:
		return HdsTransmisie.manager()
	except Exception as e:
		print("[HdsTransmis] transmisiile: %r" % (e,))
		return None


class HdsTransmis(Converter):
	def __init__(self, arg):
		Converter.__init__(self, arg)
		self.fel = (arg or "").strip()
		m = _manager()
		self._m = m
		if m is not None:
			m.urmaresteTransmise(self._laSchimbare)

	def _laSchimbare(self):
		Converter.changed(self, (self.CHANGED_ALL,))

	def _refTv(self):
		"""Canalul de pe televizor, ca text: din sursa (session.CurrentService) sau din navigare."""
		nav = getattr(self.source, "navcore", None)
		if nav is None:
			try:
				import NavigationInstance
				nav = NavigationInstance.instance
			except Exception:
				nav = None
		try:
			ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
			return ref.toString() if ref is not None else ""
		except Exception:
			return ""

	def _transmis(self):
		m = self._m
		if m is None:
			return False
		try:
			transmise = m.transmise()
			if not transmise:
				return False
			from Components.HdsTransmisie import refCurata
			ref = refCurata(self._refTv())
			return ref is not None and ref in transmise
		except Exception as e:
			print("[HdsTransmis] %r" % (e,))
			return False

	@cached
	def getBoolean(self):
		return self._transmis()

	boolean = property(getBoolean)

	@cached
	def getText(self):
		if self.fel != "Text" or not self._transmis():
			return ""
		return _("În rețea").upper()

	text = property(getText)

	def destroy(self):
		m, self._m = self._m, None
		if m is not None:
			try:
				m.renuntaTransmise(self._laSchimbare)
			except Exception:
				pass
		Converter.destroy(self)

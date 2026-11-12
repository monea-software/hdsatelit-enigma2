# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Renderer/EGclock.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
# Schimbat de HD Satelit: eGauge lipseste din enigma2-ul imaginii: acul se deseneaza pe eCanvas cand eGauge nu exista.
try:
	from enigma import eGauge
except ImportError:
	eGauge = None
from enigma import eCanvas, eRect, gRGB
import math

from Components.VariableValue import VariableValue
from Components.Renderer.Renderer import Renderer


class EGclock(VariableValue, Renderer):
	GUI_WIDGET = eGauge or eCanvas

	def __init__(self):
		Renderer.__init__(self)
		VariableValue.__init__(self)

	def postWidgetCreate(self, instance):
		self.setValue(0)          # HD Satelit: pe eCanvas (fara eGauge) instance.setValue nu exista

	def changed(self, what):
		if what[0] != self.CHANGED_CLEAR:
			value = self.source.value
			if value is None:
				value = 0
			self.setValue(value)

	def setValue(self, value):
		if self.instance is None:
			return
		if eGauge is not None:
			self.instance.setValue(value)
			return
		# fara eGauge: acul (0-59, ca la ceas) desenat pe eCanvas, din centru spre margine
		marime = self.instance.size()
		r = min(marime.width(), marime.height()) // 2
		self.instance.clear(gRGB(0, 0, 0, 255))
		unghi = math.radians((value or 0) * 6)
		for pas in range(r):
			x = r + int(round(pas * math.sin(unghi)))
			y = r - int(round(pas * math.cos(unghi)))
			self.instance.fillRect(eRect(x, y, 2, 2), gRGB(255, 255, 255))

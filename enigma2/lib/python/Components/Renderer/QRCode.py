# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Renderer/QRCode.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
# Schimbat de HD Satelit: eQRCode lipseste din enigma2-ul imaginii: codul se deseneaza pe eCanvas cu Components.HdsQr.
from enigma import eCanvas

from Components.VariableText import VariableText
from Components.Renderer.Renderer import Renderer


class _Panza(object):
	"""fill()/clear() peste un eCanvas, cum le cere Components.HdsQr.deseneaza"""

	def __init__(self, instanta):
		self.i = instanta

	def clear(self):
		from enigma import gRGB
		self.i.clear(gRGB(0xFFFFFF))

	def fill(self, x, y, latime, inaltime, culoare):
		from enigma import eRect, gRGB
		self.i.fillRect(eRect(x, y, latime, inaltime), gRGB(culoare))


class QRCode(VariableText, Renderer):
	GUI_WIDGET = eCanvas

	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)
		self.desenat = None

	def postWidgetCreate(self, instance):
		self.desenat = None
		self.deseneaza()
		self.updateVisibility(instance)

	def changed(self, what):
		if what[0] == self.CHANGED_CLEAR or not self.source:
			self.text = ""
		else:
			self.text = getattr(self.source, "text", "") or ""
		if self.instance:
			self.deseneaza()
			self.updateVisibility(self.instance)

	def deseneaza(self):
		if not self.instance or not self.text or self.desenat == self.text:
			return
		try:
			from Components.HdsQr import deseneaza
			marime = self.instance.size()
			deseneaza(_Panza(self.instance), self.text, marime.width(), marime.height())
			self.desenat = self.text
		except Exception as e:
			print("[QRCode] codul nu se poate desena: %s" % e)

	def updateVisibility(self, instance):
		if self.text:
			instance.show()
		else:
			instance.hide()

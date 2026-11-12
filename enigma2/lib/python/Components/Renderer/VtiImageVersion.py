# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Renderer/VtiImageVersion.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
# Schimbat de HD Satelit: textul spune numele si versiunea imaginii noastre (BoxInfo), nu al altei imagini.
from enigma import eLabel

from Components.SystemInfo import BoxInfo
from Components.VariableText import VariableText
from Components.Renderer.Renderer import Renderer


class VtiImageVersion(VariableText, Renderer):

	GUI_WIDGET = eLabel

	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)

	def connect(self, source):
		Renderer.connect(self, source)
		self.changed((self.CHANGED_DEFAULT,))

	def changed(self, what):
		if what[0] != self.CHANGED_CLEAR:
			self.text = self.imageVersion()

	def imageVersion(self):
		nume = BoxInfo.getItem("displaydistro") or BoxInfo.getItem("distro") or "HD Satelit"
		return "%s v. %s" % (nume, BoxInfo.getItem("imageversion") or "")

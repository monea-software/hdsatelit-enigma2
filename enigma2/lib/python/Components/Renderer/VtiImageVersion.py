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

	# Schimbat de HD Satelit (MI7, 15.11.2026), ca Label.connect: Renderer.connect cheama deja changed; legatura ca in
	# Element.connect, iar textul se cere o singura data, dupa legatura completa.
	def connect(self, source):
		assert not self.SINGLE_SOURCE or self.source is None
		self.sources.append(source)
		self.source = source
		source.connectDownstream(self)
		self.changed((self.CHANGED_DEFAULT,))

	def changed(self, what):
		if what[0] != self.CHANGED_CLEAR:
			self.text = self.imageVersion()

	def imageVersion(self):
		nume = BoxInfo.getItem("displaydistro") or BoxInfo.getItem("distro") or "HD Satelit"
		return "%s v. %s" % (nume, BoxInfo.getItem("imageversion") or "")

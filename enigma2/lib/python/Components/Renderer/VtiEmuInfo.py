# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Renderer/VtiEmuInfo.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
from enigma import eLabel

from Components.config import config
from Components.VariableText import VariableText
from Components.Renderer.Renderer import Renderer
from Tools.Directories import SCOPE_SYSETC, resolveFilename


class VtiEmuInfo(VariableText, Renderer):

	GUI_WIDGET = eLabel

	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)

	def connect(self, source):
		Renderer.connect(self, source)
		self.changed((self.CHANGED_DEFAULT,))

	def changed(self, what):
		self.text = "not detected Softcam" if what[0] == self.CHANGED_CLEAR else self.getVtiEmuInfo()

	def getVtiEmuInfo(self):
		if config.misc.ecm_info.value:
			try:
				with open(resolveFilename(SCOPE_SYSETC, "/tmp/.emu.info")) as fd:
					emuversion = fd.readline()
				return emuversion
			except OSError:
				return "not detected Softcam"

		else:
			return " "

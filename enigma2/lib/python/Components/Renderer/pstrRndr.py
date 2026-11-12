# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Renderer/pstrRndr.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
# by digiteng...12-2019
# v1.1a 01-2020
from os.path import exists

from enigma import ePixmap, loadJPG

from Components.Renderer.Renderer import Renderer


class pstrRndr(Renderer):
	GUI_WIDGET = ePixmap
	POSTER = "/tmp/poster/poster.jpg"

	def changed(self, what):
		if self.instance:
			if self.source.text and exists(self.POSTER):
				self.instance.setPixmap(loadJPG(self.POSTER))
				self.instance.show()
			else:
				self.instance.hide()

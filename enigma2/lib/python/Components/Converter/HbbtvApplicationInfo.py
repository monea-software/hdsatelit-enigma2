# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Converter/HbbtvApplicationInfo.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
from Components.Element import cached
from Components.Converter.Converter import Converter


class HbbtvApplicationInfo(Converter):
	NAME = 0

	def __init__(self, token):
		Converter.__init__(self, token)
		self.type = self.NAME if token == "Name" else ""

	@cached
	def getText(self):
		return self.source.name if self.type == self.NAME else ""

	text = property(getText)

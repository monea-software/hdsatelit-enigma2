# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Converter/EGAnalogic.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
# Shamelessly copied from BP Project.

from time import localtime

from Components.Element import cached
from Components.Converter.Converter import Converter


class EGAnalogic(Converter):
	def __init__(self, token):
		Converter.__init__(self, token)
		self.type = {
			"Hours": 3,
			"Minutes": 2,
			"Seconds": 1
		}.get(token, -1)

	@cached
	def getValue(self):
		value = 0
		sourceTime = self.source.time
		if sourceTime is not None:
			timeStruct = localtime(sourceTime)
			match self.type:
				case 1:
					value = int((timeStruct.tm_sec * 100) / 60)
				case 2:
					value = int((timeStruct.tm_min * 100) / 60)
				case 3:
					value = int(((timeStruct.tm_hour * 100) / 12) + (timeStruct.tm_min / 8))
				case _:
					value = None
		return value

	value = property(getValue)

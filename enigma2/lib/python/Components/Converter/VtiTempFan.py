# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Converter/VtiTempFan.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor de mai jos raman neschimbate. Adus in imaginea HD Satelit (lotul TOT,
# 12.11.2026) ca temele si pluginurile scrise pentru imaginile OE-Alliance sa-si gaseasca toate componentele.
from Components.Element import cached
from Components.Converter.Converter import Converter
from Components.Converter.Poll import Poll


class VtiTempFan(Poll, Converter):
	TEMPINFO = 1
	FANINFO = 2
	ALL = 5

	def __init__(self, token):
		Poll.__init__(self)
		Converter.__init__(self, token)
		self.poll_interval = 30000
		self.poll_enabled = True
		self.type = {
			"FanInfo": self.FANINFO,
			"TempInfo": self.TEMPINFO
		}.get(token, self.ALL)

	def changed(self, what):
		if what[0] == self.CHANGED_POLL:
			Converter.changed(self, what)

	def fanfile(self):
		text = None
		try:
			with open("/proc/stb/fp/fan_speed") as fd:
				text = f"FAN: {fd.readline().strip()}"
		except OSError:
			pass
		return text

	@cached
	def getText(self):
		text = ""
		match self.type:
			case self.FANINFO:
				text = self.fanfile()
			case self.TEMPINFO:
				text = self.tempfile()
		return text

	text = property(getText)

	def tempfile(self):
		text = None
		try:
			with open("/proc/stb/sensors/temp0/value") as fd:
				temp = fd.readline().strip()
			with open("/proc/stb/sensors/temp0/unit") as fd:
				unit = fd.readline().strip()
			text = f"TEMP: {temp} °{unit}"
		except OSError:
			pass
		return text

# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Argumentele OE-Alliance in plus (11.11.2026): OnlyMinute (numai minutele ramase), OnlyMinute2 (ora de acum si minutele
# ramase), Percentage (cat s-a scurs, in procente) si VFD, VFDWithSeconds, VFDNoSeconds, VFDInSeconds, VFDPercentage (ca cele
# fara VFD). Sursa poate da si trei numere (durata, scurs, ramas): se iau durata si ce a ramas. Cele de dinainte dau acelasi text.
from time import localtime, strftime
from Components.Converter.Converter import Converter
from Components.Element import cached

class RemainingToText(Converter, object):
	DEFAULT = 0
	WITH_SECONDS = 1
	NO_SECONDS = 2
	IN_SECONDS = 3
	ONLY_MINUTE = 4
	ONLY_MINUTE2 = 5
	PERCENTAGE = 6

	TIPURI = {"WithSeconds": WITH_SECONDS, "NoSeconds": NO_SECONDS, "InSeconds": IN_SECONDS, "OnlyMinute": ONLY_MINUTE,
		"OnlyMinute2": ONLY_MINUTE2, "Percentage": PERCENTAGE}

	def __init__(self, type):
		Converter.__init__(self, type)
		nume = (type or "").strip()
		if nume.startswith("VFD"):
			nume = nume[3:]
		self.type = self.TIPURI.get(nume, self.DEFAULT)

	@cached
	def getText(self):
		time = self.source.time
		if time is None:
			return ""

		if len(time) > 2:
			time = (time[0], time[-1])
		(duration, remaining) = time

		if self.type == self.ONLY_MINUTE:
			return "" if remaining is None else "%d" % (remaining // 60)
		elif self.type == self.ONLY_MINUTE2:
			acum = strftime("%H:%M", localtime())
			if remaining is None or remaining // 60 == 0:
				return acum
			return "%s %+d" % (acum, remaining // 60)
		elif self.type == self.PERCENTAGE:
			if not duration or remaining is None:
				return ""
			return "%d%%" % ((duration - remaining) * 100 // duration)

		if self.type == self.WITH_SECONDS:
			if remaining is not None:
				return "%d:%02d:%02d" % (remaining // 3600, (remaining // 60) - ((remaining // 3600) * 60), remaining % 60)
			else:
				return "%02d:%02d:%02d" % (duration // 3600, (duration // 60) - ((duration // 3600) * 60), duration % 60)
		elif self.type == self.NO_SECONDS:
			if remaining is not None:
				return "+%d:%02d" % (remaining // 3600, (remaining // 60) - ((remaining // 3600) * 60))
			else:
				return "%02d:%02d" % (duration // 3600, (duration // 60) - ((duration // 3600) * 60))
		elif self.type == self.IN_SECONDS:
			if remaining is not None:
				return str(remaining)
			else:
				return str(duration)
		elif self.type == self.DEFAULT:
			if remaining is not None:
				return "+%d min" % (remaining // 60)
			else:
				return "%d min" % (duration // 60)
		else:
			return "???"

	text = property(getText)

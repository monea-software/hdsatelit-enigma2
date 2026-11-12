# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Argumentele OE-Alliance in plus (11.11.2026): EndTime (ora la care se termina redarea, %H:%M:%S; %H:%M cu ShowNoSeconds sau
# ShowNoSeconds2), Summary ("MM:SS +Nm"), VFDLength / VFDPosition / VFDRemaining / VFDGauge / VFDSummary (ca fara VFD),
# optiunile ShowNoSeconds2 (ca ShowNoSeconds), OnlyMinute (numai minutele) si 7segment (se trece cu vederea).
# Cele de dinainte dau acelasi text.
from time import localtime, strftime, time as _acum
from .Converter import Converter
from .Poll import Poll
from enigma import iPlayableService
from Components.Element import cached, ElementError

class ServicePosition(Poll, Converter, object):
	TYPE_LENGTH = 0
	TYPE_POSITION = 1
	TYPE_REMAINING = 2
	TYPE_GAUGE = 3
	TYPE_SUMMARY = 4
	TYPE_ENDTIME = 5

	TIPURI = {"Length": TYPE_LENGTH, "Position": TYPE_POSITION, "Remaining": TYPE_REMAINING, "Gauge": TYPE_GAUGE,
		"Summary": TYPE_SUMMARY, "EndTime": TYPE_ENDTIME}

	def __init__(self, type):
		Poll.__init__(self)
		Converter.__init__(self, type)

		args = [a.strip() for a in type.split(',')]
		type = args.pop(0)
		if type.startswith("VFD") and type[3:] in self.TIPURI:
			type = type[3:]

		self.negate = 'Negate' in args
		self.detailed = 'Detailed' in args
		self.showHours = 'ShowHours' in args
		self.showNoSeconds = 'ShowNoSeconds' in args or 'ShowNoSeconds2' in args
		self.onlyMinute = 'OnlyMinute' in args

		self.type = self.TIPURI.get(type)
		if self.type is None:
			raise ElementError("type must be {Length|Position|Remaining|Gauge|Summary|EndTime} with optional arguments {Negate|Detailed|ShowHours|ShowNoSeconds|ShowNoSeconds2|OnlyMinute} for ServicePosition converter")

		if self.detailed:
			self.poll_interval = 100
		elif self.type == self.TYPE_LENGTH:
			self.poll_interval = 2000
		else:
			self.poll_interval = 500

		self.poll_enabled = True

	def getSeek(self):
		s = self.source.service
		return s and s.seek()

	@cached
	def getPosition(self):
		seek = self.getSeek()
		if seek is None:
			return None
		pos = seek.getPlayPosition()
		if pos[0]:
			return 0
		return pos[1]

	@cached
	def getLength(self):
		seek = self.getSeek()
		if seek is None:
			return None
		length = seek.getLength()
		if length[0]:
			return 0
		return length[1]

	@cached
	def getCutlist(self):
		service = self.source.service
		cue = service and service.cueSheet()
		return cue and cue.getCutList()

	@cached
	def getText(self):
		seek = self.getSeek()
		if seek is None:
			return ""
		elif self.type in (self.TYPE_SUMMARY, self.TYPE_ENDTIME):
			lungime, pozitie = self.length, self.position
			if not lungime or lungime < 0 or pozitie is None:
				return ""
			trecut = pozitie // 90000
			ramas = lungime // 90000 - trecut
			if self.type == self.TYPE_SUMMARY:
				return "%02d:%02d +%2dm" % (trecut // 60, trecut % 60, ramas // 60)
			return strftime("%H:%M" if self.showNoSeconds else "%H:%M:%S", localtime(_acum() + ramas))
		else:
			if self.type == self.TYPE_LENGTH:
				l = self.length
			elif self.type == self.TYPE_POSITION:
				l = self.position
			elif self.type == self.TYPE_REMAINING:
				l = self.length - self.position

			if not self.detailed:
				l //= 90000

			if self.negate: l = -l

			if l > 0:
				sign = ""
			else:
				l = -l
				sign = "-"

			if self.onlyMinute and not self.detailed:
				return sign + "%d" % (l // 60)
			if not self.detailed:
				if self.showHours:
					if self.showNoSeconds:
						return sign + "%d:%02d" % (l//3600, l%3600//60)
					else:
						return sign + "%d:%02d:%02d" % (l//3600, l%3600//60, l%60)
				else:
					if self.showNoSeconds:
						return sign + "%d" % (l//60)
					else:
						return sign + "%d:%02d" % (l//60, l%60)
			else:
				if self.showHours:
					return sign + "%d:%02d:%02d:%03d" % ((l//3600//90000), (l//90000)%3600//60, (l//90000)%60, (l%90000)//90)
				else:
					return sign + "%d:%02d:%03d" % ((l//60//90000), (l//90000)%60, (l%90000)//90)

	# range/value are for the Progress renderer
	range = 10000

	@cached
	def getValue(self):
		pos = self.position
		len = self.length
		if pos is None or len is None or len <= 0:
			return None
		return pos * 10000 // len

	position = property(getPosition)
	length = property(getLength)
	cutlist = property(getCutlist)
	text = property(getText)
	value = property(getValue)

	def changed(self, what):
		cutlist_refresh = what[0] != self.CHANGED_SPECIFIC or what[1] in (iPlayableService.evCuesheetChanged,)
		time_refresh = what[0] == self.CHANGED_POLL or what[0] == self.CHANGED_SPECIFIC and what[1] in (iPlayableService.evCuesheetChanged,)

		if cutlist_refresh:
			if self.type == self.TYPE_GAUGE:
				self.downstream_elements.cutlist_changed()

		if time_refresh:
			self.downstream_elements.changed(what)

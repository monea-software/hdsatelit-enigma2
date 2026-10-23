# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Converter.Converter import Converter
from Components.Element import cached

# Name, Description, ExtendedDescription and FullDescription go through the automatic translation of the guide
# (Components/HdsTraducereEpg.py, "Tradu EPG"): the text from memory or the original at once; when the translation
# arrives, hdsTraducereEpg redraws the widget with it. Without that module (other images) the original text.
# A widget on a hidden screen (the channel list, the second bar) asks only for titles; a description is asked for
# when its widget is seen (a 1 s timer looks, only while such widgets wait), so hidden screens do not use the quota.
# The title of the now/next sources of the bar at the bottom (Sources/EventInfo: session.Event_Now / Event_Next) asks
# with bara=True: it is translated also with "Tradu EPG" off, when "Tradu bara de jos" and the translation are on.
try:
	from Components import HdsTraducereEpg as _E
except Exception:
	_E = None
import weakref

_HIDDEN = weakref.WeakSet()
_TIMER = []


def _look():
	for conv in list(_HIDDEN):
		if conv.hdsSeen():
			_HIDDEN.discard(conv)
			conv.changed((conv.CHANGED_ALL,))
	if not _HIDDEN and _TIMER:
		_TIMER[0].stop()


def _wait(conv):
	_HIDDEN.add(conv)
	try:
		if not _TIMER:
			from enigma import eTimer
			_TIMER.append(eTimer())
			_TIMER[0].callback.append(_look)
		if not _TIMER[0].isActive():
			_TIMER[0].start(1000, False)
	except Exception:
		pass


class EventName(Converter, object):
	NAME = 0
	SHORT_DESCRIPTION = 1
	EXTENDED_DESCRIPTION = 2
	ID = 3
	FULL_DESCRIPTION = 4

	def __init__(self, type):
		Converter.__init__(self, type)
		if type == "Description":
			self.type = self.SHORT_DESCRIPTION
		elif type == "ExtendedDescription":
			self.type = self.EXTENDED_DESCRIPTION
		elif type == "FullDescription":
			self.type = self.FULL_DESCRIPTION
		elif type == "ID":
			self.type = self.ID
		else:
			self.type = self.NAME

	def hdsSeen(self):
		"""a widget fed by this converter is on the screen now"""
		for r in self.downstream_elements:
			inst = getattr(r, "instance", None)
			if inst is not None:
				try:
					if inst.isVisible():
						return True
				except Exception:
					return True
		return False

	def hdsBara(self):
		"""the source is the now/next event of the current service (Sources/EventInfo), drawn by the bar at the bottom"""
		return hasattr(getattr(self, "source", None), "now_or_next")

	def _tr(self, fel, text):
		if _E is None or not text:
			return text
		bara = fel == "titlu" and self.hdsBara()
		if not _E.activ(bara):
			return text
		if fel == "titlu" or self.hdsSeen():
			return _E.text(fel, text, self, bara=bara)
		_wait(self)
		return _E.text(fel, text, self, True, False)

	def hdsTraducereEpg(self):
		"""Components/HdsTraducereEpg.py: a translation arrived (or the original was asked for): draw again (only while
		connected to a source)"""
		if getattr(self, "source", None) is not None:
			self.changed((self.CHANGED_ALL,))

	@cached
	def getText(self):
		event = self.source.event
		if event is None:
			return ""

		if self.type == self.NAME:
			return self._tr("titlu", event.getEventName() or "")
		elif self.type == self.SHORT_DESCRIPTION:
			return self._tr("scurta", event.getShortDescription() or "")
		elif self.type == self.EXTENDED_DESCRIPTION:
			return self._tr("lunga", event.getExtendedDescription() or "")
		elif self.type == self.FULL_DESCRIPTION:
			short = event.getShortDescription() or ""
			ext = event.getExtendedDescription() or ""
			if short and ext:
				if short in ext:
					return self._tr("lunga", ext)
				return self._tr("lunga", short + "\n\n" + ext)
			elif ext:
				return self._tr("lunga", ext)
			else:
				return self._tr("scurta", short)
		elif self.type == self.ID:
			try:
				return str(event.getEventId())
			except Exception:
				return ""
		return ""

	text = property(getText)

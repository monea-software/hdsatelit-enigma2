# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Screens.TimerEdit import TimerSanityConflict
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.ScrollLabel import ScrollLabel
from Components.TimerList import TimerList
from Components.UsageConfig import preferredTimerPath
from enigma import eEPGCache, eTimer, eServiceReference
from RecordTimer import RecordTimerEntry, parseEvent, AFTEREVENT
from .TimerEntry import TimerEntry
from time import localtime
from Components.config import config

# The title and the descriptions go through the automatic translation of the guide (Components/HdsTraducereEpg.py,
# "Tradu EPG"): the translation from memory or the original at once, the text is set again when the translation
# arrives (hdsTraducereEpg). INFO with a translated text shows the original (INFO twice from the bar); INFO on the
# original, or without a translation, closes the screen as before (EventViewActions "cancel"; EXIT is OkCancelActions).
# With only "Tradu bara de jos" (titles of the bar), the details are the original, so INFO from the bar shows the
# original; a line says that the bar shows the title translated.
try:
	from Components import HdsTraducereEpg as _E
except Exception:
	_E = None

class EventViewBase:
	ADD_TIMER = 0
	REMOVE_TIMER = 1
	
	def __init__(self, Event, Ref, callback=None, similarEPGCB=None):
		self.similarEPGCB = similarEPGCB
		self.cbFunc = callback
		self.currentService=Ref
		self.isRecording = (not Ref.ref.flags & eServiceReference.isGroup) and Ref.ref.getPath()
		self.event = Event
		self["epg_description"] = ScrollLabel()
		# the HDSatelit skin draws the text in FullDescription (the widget of the newer images); epg_description stays
		# for the other skins. Both get the same text.
		self["FullDescription"] = ScrollLabel()
		self["datetime"] = Label()
		self["channel"] = Label()
		self["duration"] = Label()
		self["key_red"] = Button("")
		if similarEPGCB is not None:
			self.SimilarBroadcastTimer = eTimer()
			self.SimilarBroadcastTimer.callback.append(self.getSimilarEvents)
		else:
			self.SimilarBroadcastTimer = None
		self.key_green_choice = self.ADD_TIMER
		if self.isRecording:
			self["key_green"] = Button("")
		else:
			self["key_green"] = Button(_("Add timer"))
		self["key_yellow"] = Button("")
		self["key_blue"] = Button("")
		self["actions"] = ActionMap(["OkCancelActions", "EventViewActions"],
			{
				"cancel": self.close,
				"ok": self.close,
				"pageUp": self.pageUp,
				"pageDown": self.pageDown,
				"prevEvent": self.prevEvent,
				"nextEvent": self.nextEvent,
				"timerAdd": self.timerAdd,
				"openSimilarList": self.openSimilarList
			})
		self.hdsTradus = False
		self["hdsTraducereActions"] = ActionMap(["EventViewActions"], {"cancel": self.hdsInfo}, -1)
		self.onShown.append(self.onCreate)
		self.onClose.append(self.hdsLaInchidere)

	def hdsInfo(self):
		if _E is not None and self.hdsTradus and not _E.esteOriginal():
			_E.arataOriginal(True)
			self.setEvent(self.event)
			return
		self.close()

	def hdsLaInchidere(self):
		if _E is not None:
			_E.arataOriginal(False)

	def hdsTraducereEpg(self):
		"""Components/HdsTraducereEpg.py: a translation arrived (or the original was asked for); nothing on a closed
		screen (its attributes are gone)"""
		if getattr(self, "event", None) is not None and getattr(self, "shown", False) and "FullDescription" in self:
			self.setEvent(self.event)

	def hdsTexte(self, event):
		"""(title, short, extended, note): translated when "Tradu EPG" is on, with the line that says so"""
		name = event.getEventName() or ""
		short = event.getShortDescription() or ""
		ext = event.getExtendedDescription() or ""
		self.hdsTradus = False
		if _E is None:
			return name, short, ext, ""
		stari = []
		rez = []
		for fel, t in (("titlu", name), ("scurta", short), ("lunga", ext)):
			text, stare = _E.traducere(fel, t, self, False)
			rez.append(text)
			stari.append(stare)
		if _E.STARE_ORIGINAL in stari:
			return name, short, ext, _("Textul original, netradus. INFO: închide.")
		if _E.STARE_TRADUS in stari:
			self.hdsTradus = True
			return rez[0], rez[1], rez[2], _("Tradus automat. INFO: textul original.")
		# only "Tradu bara de jos": the details stay the original; a line says why the bar shows another title (from
		# memory, no new request)
		titluBara = getattr(_E, "titluBara", None)
		if titluBara is not None and titluBara(name):
			return name, short, ext, _("Textul original. Pe bara de jos, titlul e tradus automat.")
		return name, short, ext, ""

	def onCreate(self):
		self.setService(self.currentService)
		self.setEvent(self.event)

	def prevEvent(self):
		if self.cbFunc is not None:
			self.cbFunc(self.setEvent, self.setService, -1)

	def nextEvent(self):
		if self.cbFunc is not None:
			self.cbFunc(self.setEvent, self.setService, +1)

	def removeTimer(self, timer):
		timer.afterEvent = AFTEREVENT.NONE
		self.session.nav.RecordTimer.removeEntry(timer)
		self["key_green"].setText(_("Add timer"))
		self.key_green_choice = self.ADD_TIMER
	
	def timerAdd(self):
		if self.isRecording:
			return
		event = self.event
		serviceref = self.currentService
		if event is None:
			return
		eventid = event.getEventId()
		refstr = serviceref.ref.toString()
		for timer in self.session.nav.RecordTimer.timer_list:
			if timer.eit == eventid and timer.service_ref.ref.toString() == refstr:
				cb_func = lambda ret : not ret or self.removeTimer(timer)
				self.session.openWithCallback(cb_func, MessageBox, _("Do you really want to delete %s?") % event.getEventName())
				break
		else:
			newEntry = RecordTimerEntry(self.currentService, checkOldTimers = True, dirname = preferredTimerPath(), *parseEvent(self.event))
			self.session.openWithCallback(self.finishedAdd, TimerEntry, newEntry)

	def finishedAdd(self, answer):
		print("finished add")
		if answer[0]:
			entry = answer[1]
			simulTimerList = self.session.nav.RecordTimer.record(entry)
			if simulTimerList is not None:
				for x in simulTimerList:
					if x.setAutoincreaseEnd(entry):
						self.session.nav.RecordTimer.timeChanged(x)
				simulTimerList = self.session.nav.RecordTimer.record(entry)
				if simulTimerList is not None:
					self.session.openWithCallback(self.finishSanityCorrection, TimerSanityConflict, simulTimerList)
			self["key_green"].setText(_("Remove timer"))
			self.key_green_choice = self.REMOVE_TIMER
		else:
			self["key_green"].setText(_("Add timer"))
			self.key_green_choice = self.ADD_TIMER
			print("Timeredit aborted")		

	def finishSanityCorrection(self, answer):
		self.finishedAdd(answer)

	def setService(self, service):
		self.currentService=service
		if self.isRecording:
			self["channel"].setText(_("Recording"))
		else:
			name = self.currentService.getServiceName()
			if name is not None:
				self["channel"].setText(name)
			else:
				self["channel"].setText(_("unknown service"))

	def sort_func(self,x,y):
		if x[1] < y[1]:
			return -1
		elif x[1] == y[1]:
			return 0
		else:
			return 1

	def setEvent(self, event):
		self.event = event
		if event is None:
			return
		name, short, ext, note = self.hdsTexte(event)
		text = name
		if note:
			# the line about the translation at the top: a long description would hide it at the end
			text += '\n' + note
		if short and short != name:
			text += '\n\n' + short
		if ext:
			if text:
				text += '\n\n'
			text += ext

		self.setTitle(name)
		self.hdsSetDescription(text)
		self["datetime"].setText(event.getBeginTimeString())
		self["duration"].setText(_("%d min")%(event.getDuration()//60))
		self["key_red"].setText("")
		if self.SimilarBroadcastTimer is not None:
			self.SimilarBroadcastTimer.start(400,True)

		serviceref = self.currentService
		eventid = self.event.getEventId()
		refstr = serviceref.ref.toString()
		isRecordEvent = False
		for timer in self.session.nav.RecordTimer.timer_list:
			if timer.eit == eventid and timer.service_ref.ref.toString() == refstr:
				isRecordEvent = True
				break
		if isRecordEvent and self.key_green_choice != self.REMOVE_TIMER:
			self["key_green"].setText(_("Remove timer"))
			self.key_green_choice = self.REMOVE_TIMER
		elif not isRecordEvent and self.key_green_choice != self.ADD_TIMER:
			self["key_green"].setText(_("Add timer"))
			self.key_green_choice = self.ADD_TIMER


	def hdsSetDescription(self, text):
		self["epg_description"].setText(text)
		self["FullDescription"].setText(text)

	def pageUp(self):
		self["epg_description"].pageUp()
		self["FullDescription"].pageUp()

	def pageDown(self):
		self["epg_description"].pageDown()
		self["FullDescription"].pageDown()

	def getSimilarEvents(self):
	 # search similar broadcastings
		refstr = str(self.currentService)
		id = self.event.getEventId()
		epgcache = eEPGCache.getInstance()
		ret = epgcache.search(('NB', 100, eEPGCache.SIMILAR_BROADCASTINGS_SEARCH, refstr, id))
		if ret is not None:
			descr = self["epg_description"]
			text = descr.getText()
			text += '\n\n' + _('Similar broadcasts:')
			ret.sort(key=lambda x: x[1])
			for x in ret:
				t = localtime(x[1])
				text += '\n%d.%d.%d, %02d:%02d  -  %s'%(t[2], t[1], t[0], t[3], t[4], x[0])
			self.hdsSetDescription(text)
			self["key_red"].setText(_("Similar"))

	def openSimilarList(self):
		if self.similarEPGCB is not None and self["key_red"].getText():
			id = self.event and self.event.getEventId()
			refstr = str(self.currentService)
			if id is not None:
				self.similarEPGCB(id, refstr)

class EventViewSimple(Screen, EventViewBase):
	def __init__(self, session, Event, Ref, callback=None, similarEPGCB=None):
		Screen.__init__(self, session)
		self.skinName = "EventView"
		EventViewBase.__init__(self, Event, Ref, callback, similarEPGCB)

class EventViewEPGSelect(Screen, EventViewBase):
	def __init__(self, session, Event, Ref, callback=None, singleEPGCB=None, multiEPGCB=None, similarEPGCB=None):
		Screen.__init__(self, session)
		self.skinName = "EventView"
		EventViewBase.__init__(self, Event, Ref, callback, similarEPGCB)
		self["key_yellow"].setText(_("Single EPG"))
		self["key_blue"].setText(_("Multi EPG"))
		self["epgactions"] = ActionMap(["EventViewEPGActions"],
			{
				"openSingleServiceEPG": singleEPGCB,
				"openMultiServiceEPG": multiEPGCB,
			})

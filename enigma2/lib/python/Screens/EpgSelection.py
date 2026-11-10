# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.config import config, ConfigClock
from Components.Button import Button
from Components.Pixmap import Pixmap
from Components.Label import Label
from Components.EpgList import EPGList, EPG_TYPE_SINGLE, EPG_TYPE_SIMILAR, EPG_TYPE_MULTI
from Components.ActionMap import ActionMap
from Components.Sources.ServiceEvent import ServiceEvent
from Components.Sources.Event import Event
from Screens.EventView import EventViewSimple
from Screens.ChoiceBox import ChoiceBox
from .TimeDateInput import TimeDateInput
from enigma import eServiceReference
from .TimerEntry import GhidTimer
from Components import HdsInregistrariProgramate as HIP
from ServiceReference import ServiceReference
from time import localtime, time

mepg_config_initialized = False

class EPGSelection(Screen):
	EMPTY = 0
	ADD_TIMER = 1
	REMOVE_TIMER = 2
	
	ZAP = 1

	def __init__(self, session, service, zapFunc=None, eventid=None, bouquetChangeCB=None, serviceChangeCB=None):
		Screen.__init__(self, session)
		self.bouquetChangeCB = bouquetChangeCB
		self.serviceChangeCB = serviceChangeCB
		self.ask_time = -1 #now
		self["key_red"] = Button("")
		self.closeRecursive = False
		self.saved_title = None
		self["Service"] = ServiceEvent()
		self["Event"] = Event()
		if isinstance(service, str) and eventid != None:
			self.type = EPG_TYPE_SIMILAR
			self["key_yellow"] = Button()
			self["key_blue"] = Button()
			self["key_red"] = Button()
			self.currentService=service
			self.eventid = eventid
			self.zapFunc = None
		elif isinstance(service, eServiceReference) or isinstance(service, str):
			self.type = EPG_TYPE_SINGLE
			self["key_yellow"] = Button()
			self["key_blue"] = Button()
			self.currentService=ServiceReference(service)
			self.zapFunc = None
			self.sort_type = 0
			self.setSortDescription()
		else:
			self.skinName = "EPGSelectionMulti"
			self.type = EPG_TYPE_MULTI
			self["key_yellow"] = Button(_("Prev"))
			self["key_blue"] = Button(_("Next"))
			self["now_button"] = Pixmap()
			self["next_button"] = Pixmap()
			self["more_button"] = Pixmap()
			self["now_button_sel"] = Pixmap()
			self["next_button_sel"] = Pixmap()
			self["more_button_sel"] = Pixmap()
			self["now_text"] = Label()
			self["next_text"] = Label()
			self["more_text"] = Label()
			self["date"] = Label()
			self.services = service
			self.zapFunc = zapFunc

		self["key_green"] = Button(_("Înregistrează"))
		self["hds_timer_hint"] = Label(_("MENU: editare, zi și oră.") if self.type == EPG_TYPE_MULTI else
			_("MENU: editează înregistrarea."))
		self.ghidTimer = GhidTimer(session, self.hdsTimerSchimbat)
		self.key_green_choice = self.ADD_TIMER
		self.key_red_choice = self.EMPTY
		self["list"] = EPGList(type = self.type, selChangedCB = self.onSelectionChanged, timer = session.nav.RecordTimer)

		self["actions"] = ActionMap(["EPGSelectActions", "OkCancelActions"],
			{
				"cancel": self.closeScreen,
				"ok": self.eventSelected,
				"timerAdd": self.timerAdd,
				"yellow": self.yellowButtonPressed,
				"blue": self.blueButtonPressed,
				"info": self.infoKeyPressed,
				"red": self.zapTo,
				"input_date_time": self.timerMenu,
				"nextBouquet": self.nextBouquet, # just used in multi epg yet
				"prevBouquet": self.prevBouquet, # just used in multi epg yet
				"nextService": self.nextService, # just used in single epg yet
				"prevService": self.prevService, # just used in single epg yet
			})
		self["actions"].csel = self
		self.onLayoutFinish.append(self.onCreate)
		self.onClose.append(self.hdsTimerInchis)
		self._ghidInchis = False

	def hdsTimerInchis(self):
		self._ghidInchis = True

	def hdsTimerSchimbat(self):
		if not self._ghidInchis:
			self["list"].l.invalidate()
			self.onSelectionChanged()

	def timerMenu(self):
		if self.type == EPG_TYPE_MULTI:
			def ales(ret):
				if ret is not None:
					ret[1]()
			self.session.openWithCallback(ales, ChoiceBox, title=_("Ghid TV"), list=[
				(_("Editează înregistrarea"), self.timerEdit), (_("Alege ziua și ora"), self.enterDateTime)])
		else:
			self.timerEdit()

	def timerEdit(self):
		cur = self["list"].getCurrent()
		if cur is not None:
			self.ghidTimer.editeaza(cur[0], cur[1])

	def nextBouquet(self):
		if self.bouquetChangeCB:
			self.bouquetChangeCB(1, self)

	def prevBouquet(self):
		if self.bouquetChangeCB:
			self.bouquetChangeCB(-1, self)

	def nextService(self):
		if self.serviceChangeCB:
			self.serviceChangeCB(1, self)

	def prevService(self):
		if self.serviceChangeCB:
			self.serviceChangeCB(-1, self)

	def enterDateTime(self):
		if self.type == EPG_TYPE_MULTI:
			global mepg_config_initialized
			if not mepg_config_initialized:
				config.misc.prev_mepg_time=ConfigClock(default = time())
				mepg_config_initialized = True
			self.session.openWithCallback(self.onDateTimeInputClosed, TimeDateInput, config.misc.prev_mepg_time )

	def onDateTimeInputClosed(self, ret):
		if len(ret) > 1:
			if ret[0]:
				self.ask_time=ret[1]
				self["list"].fillMultiEPG(self.services, ret[1])

	def closeScreen(self):
		self.close(self.closeRecursive)

	def infoKeyPressed(self):
		cur = self["list"].getCurrent()
		event = cur[0]
		service = cur[1]
		if event is not None:
			if self.type != EPG_TYPE_SIMILAR:
				self.session.open(EventViewSimple, event, service, self.eventViewCallback, self.openSimilarList)
			else:
				self.session.open(EventViewSimple, event, service, self.eventViewCallback)

	def openSimilarList(self, eventid, refstr):
		self.session.open(EPGSelection, refstr, None, eventid)

	def setServices(self, services):
		self.services = services
		self.onCreate()

	def setService(self, service):
		self.currentService = service
		self.onCreate()

	#just used in multipeg
	def onCreate(self):
		l = self["list"]
		l.recalcEntrySize()
		if self.type == EPG_TYPE_MULTI:
			l.fillMultiEPG(self.services, self.ask_time)
			l.moveToService(self.session.nav.getCurrentlyPlayingServiceReference())
		elif self.type == EPG_TYPE_SINGLE:
			service = self.currentService
			self["Service"].newService(service.ref)
			if self.saved_title is None:
				self.saved_title = self.instance.getTitle()
			title = self.saved_title + ' - ' + service.getServiceName()
			self.instance.setTitle(title)
			l.fillSingleEPG(service)
		else:
			l.fillSimilarList(self.currentService, self.eventid)

	def eventViewCallback(self, setEvent, setService, val):
		l = self["list"]
		old = l.getCurrent()
		if val == -1:
			self.moveUp()
		elif val == +1:
			self.moveDown()
		cur = l.getCurrent()
		if self.type == EPG_TYPE_MULTI and cur[0] is None and cur[1].ref != old[1].ref:
			self.eventViewCallback(setEvent, setService, val)
		else:
			setService(cur[1])
			setEvent(cur[0])

	def zapTo(self): # just used in multiepg
		if self.zapFunc and self.key_red_choice == self.ZAP:
			lst = self["list"]
			count = lst.getCurrentChangeCount()
			if count == 0:
				self.closeRecursive = True
				ref = lst.getCurrent()[1]
				self.zapFunc(ref.ref)

	def eventSelected(self):
		self.infoKeyPressed()

	def yellowButtonPressed(self):
		if self.type == EPG_TYPE_MULTI:
			self["list"].updateMultiEPG(-1)
		elif self.type == EPG_TYPE_SINGLE:
			if self.sort_type == 0:
				self.sort_type = 1
			else:
				self.sort_type = 0
			self["list"].sortSingleEPG(self.sort_type)
			self.setSortDescription()

	def setSortDescription(self):
		if self.sort_type == 1:
			# TRANSLATORS: This must fit into the header button in the EPG-List
			self["key_yellow"].setText(_("Sort Time"))
		else:
			# TRANSLATORS: This must fit into the header button in the EPG-List
			self["key_yellow"].setText(_("Sort A-Z"))

	def blueButtonPressed(self):
		if self.type == EPG_TYPE_MULTI:
			self["list"].updateMultiEPG(1)

	def timerAdd(self):
		cur = self["list"].getCurrent()
		if cur is not None:
			self.ghidTimer.comuta(cur[0], cur[1])

	def moveUp(self):
		self["list"].moveUp()

	def moveDown(self):
		self["list"].moveDown()
	
	def applyButtonState(self, state):
		if state == 0:
			self["now_button"].hide()
			self["now_button_sel"].hide()
			self["next_button"].hide()
			self["next_button_sel"].hide()
			self["more_button"].hide()
			self["more_button_sel"].hide()
			self["now_text"].hide()
			self["next_text"].hide()
			self["more_text"].hide()
		else:
			if state == 1:
				self["now_button_sel"].show()
				self["now_button"].hide()
			else:
				self["now_button"].show()
				self["now_button_sel"].hide()

			if state == 2:
				self["next_button_sel"].show()
				self["next_button"].hide()
			else:
				self["next_button"].show()
				self["next_button_sel"].hide()

			if state == 3:
				self["more_button_sel"].show()
				self["more_button"].hide()
			else:
				self["more_button"].show()
				self["more_button_sel"].hide()

	def onSelectionChanged(self):
		cur = self["list"].getCurrent()
		if cur is None:
			if self.key_green_choice != self.EMPTY:
				self["key_green"].setText("")
				self.key_green_choice = self.EMPTY
			if self.key_red_choice != self.EMPTY:
				self["key_red"].setText("")
				self.key_red_choice = self.EMPTY
			return
		event = cur[0]
		self["Event"].newEvent(event)
		if self.type == EPG_TYPE_MULTI:
			count = self["list"].getCurrentChangeCount()
			if self.ask_time != -1:
				self.applyButtonState(0)
			elif count > 1:
				self.applyButtonState(3)
			elif count > 0:
				self.applyButtonState(2)
			else:
				self.applyButtonState(1)
			days = [ _("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun") ]
			datestr = ""
			if event is not None:
				now = time()
				beg = event.getBeginTime()
				nowTime = localtime(now)
				begTime = localtime(beg)
				if nowTime[2] != begTime[2]:
					datestr = '%s %d.%d.'%(days[begTime[6]], begTime[2], begTime[1])
				else:
					datestr = '%s %d.%d.'%(_("Today"), begTime[2], begTime[1])
			self["date"].setText(datestr)
			if cur[1] is None:
				self["Service"].newService(None)
			else:
				self["Service"].newService(cur[1].ref)

		if cur[1] is None or cur[1].getServiceName() == "":
			if self.key_green_choice != self.EMPTY:
				self["key_green"].setText("")
				self.key_green_choice = self.EMPTY
			if self.key_red_choice != self.EMPTY:
				self["key_red"].setText("")
				self.key_red_choice = self.EMPTY
			return
		elif self.type == EPG_TYPE_MULTI:
			self["key_red"].setText(_("Pornește canalul"))
			self.key_red_choice = self.ZAP

		if event is None:
			if self.key_green_choice != self.EMPTY:
				self["key_green"].setText("")
				self.key_green_choice = self.EMPTY
			return

		isRecordEvent = HIP.cautaEmisiune(self.session.nav.RecordTimer, cur[1], event) is not None
		if isRecordEvent and self.key_green_choice != self.REMOVE_TIMER:
			self["key_green"].setText(_("Șterge programarea"))
			self.key_green_choice = self.REMOVE_TIMER
		elif not isRecordEvent and self.key_green_choice != self.ADD_TIMER:
			self["key_green"].setText(_("Înregistrează"))
			self.key_green_choice = self.ADD_TIMER

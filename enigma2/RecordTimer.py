# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eEPGCache, getBestPlayableServiceReference, \
	eServiceReference, iRecordableService, quitMainloop

from Components.config import config
from Components.UsageConfig import defaultMoviePath
from Components.TimerSanityCheck import TimerSanityCheck

from Screens.MessageBox import MessageBox
import Screens.Standby
from Tools import Directories, Notifications, ASCIItranslit
from Tools.XMLTools import stringToXML

import timer
import xml.etree.ElementTree
import NavigationInstance
from ServiceReference import ServiceReference

from time import localtime, strftime, ctime, time
from bisect import insort

import base64
import os

# XML nu poate purta nici octetii ne-UTF-8 (surogatele \udc80..\udcff ale unui nume de pe stick FAT,
# ajuns aici prin LocationBox sau printr-un EPG stricat de la emitator), nici caracterele de control
# interzise: parserul da ParseError, iar loadTimer muta atunci TOT fisierul in timers.xml_old si se
# pierd toate cronometrele. Deci in atributul obisnuit scriem text XML valid (semnele imposibile
# inlocuite cu '?') si punem octetii adevarati intr-un atribut insotitor <nume>_raw (base64), numai
# cand e nevoie. Un fisier fara astfel de semne iese identic octet cu octet cu inainte, iar cititorii
# din afara (interfata web, importul de setari) vad XML valid si ignora atributul in plus.
def xmlSafeText(text):
	text = str(text)
	need_raw = False
	safe = []
	for ch in text:
		c = ord(ch)
		if c in (0x09, 0x0A, 0x0D):
			safe.append(ch)
		elif c < 0x20 or 0xD800 <= c <= 0xDFFF or c in (0xFFFE, 0xFFFF):
			safe.append('?')
			need_raw = True
		else:
			safe.append(ch)
	safe = ''.join(safe)
	if need_raw:
		return safe, base64.b64encode(text.encode("utf-8", "surrogateescape")).decode("ascii")
	return safe, None

# un atribut XML gata scris, cu insotitorul <nume>_raw numai cand textul nu incape intreg in XML
def xmlAttribute(name, value):
	safe, raw = xmlSafeText(value)
	out = ' ' + name + '="' + stringToXML(safe) + '"'
	if raw is not None:
		out += ' ' + name + '_raw="' + raw + '"'
	return out

# citirea pereche: daca exista <nume>_raw, octetii originali; altfel textul obisnuit (fisiere vechi)
def xmlAttributeValue(node, name):
	raw = node.get(name + "_raw")
	if raw:
		try:
			return base64.b64decode(raw.encode("ascii")).decode("utf-8", "surrogateescape")
		except Exception:
			print("[RecordTimer] %s_raw stricat, se foloseste textul din %s" % (name, name))
	return node.get(name)

# ok, for descriptions etc we have:
# service reference  (to get the service name)
# name               (title)
# description        (description)
# event data         (ONLY for time adjustments etc.)


# parses an event, and gives out a (begin, end, name, duration, eit)-tuple.
# begin and end will be corrected
def parseEvent(ev, description = True):
	if description:
		name = ev.getEventName()
		description = ev.getShortDescription()
	else:
		name = ""
		description = ""
	begin = ev.getBeginTime()
	end = begin + ev.getDuration()
	eit = ev.getEventId()
	begin -= config.recording.margin_before.value * 60
	end += config.recording.margin_after.value * 60
	return (begin, end, name, description, eit)

class AFTEREVENT:
	NONE = 0
	STANDBY = 1
	DEEPSTANDBY = 2
	AUTO = 3

# please do not translate log messages
def hdsTineMinte(ref):
	# HDSatelit: canalul pornit de temporizator pentru om ramane canalul de pornire dupa o repornire a interfetei, ca la
	# zap-ul din lista (Components/HdsCanalTinut.py)
	try:
		from Components.HdsCanalTinut import tine_minte
		tine_minte(ref)
	except Exception as e:
		print("[RecordTimer] HdsCanalTinut: %r" % (e,))

def hdsDecodare():
	# HDSatelit: inregistrarile "Decodează mai târziu" (Components/HdsDecodare.py); None daca modulul lipseste
	try:
		from Components import HdsDecodare
		return HdsDecodare
	except ImportError:
		return None

class RecordTimerEntry(timer.TimerEntry, object):
######### the following static methods and members are only in use when the box is in (soft) standby
	receiveRecordEvents = False

	@staticmethod
	def shutdown():
		quitMainloop(1)

	@staticmethod
	def staticGotRecordEvent(recservice, event):
		if event == iRecordableService.evEnd:
			print("RecordTimer.staticGotRecordEvent(iRecordableService.evEnd)")
			recordings = NavigationInstance.instance.getRecordings()
			if not recordings: # no more recordings exist
				rec_time = NavigationInstance.instance.RecordTimer.getNextRecordingTime()
				if rec_time > 0 and (rec_time - time()) < 360:
					print("another recording starts in", rec_time - time(), "seconds... do not shutdown yet")
				else:
					print("no starting records in the next 360 seconds... immediate shutdown")
					RecordTimerEntry.shutdown() # immediate shutdown
		elif event == iRecordableService.evStart:
			print("RecordTimer.staticGotRecordEvent(iRecordableService.evStart)")

	@staticmethod
	def stopTryQuitMainloop():
		print("RecordTimer.stopTryQuitMainloop")
		NavigationInstance.instance.record_event.remove(RecordTimerEntry.staticGotRecordEvent)
		RecordTimerEntry.receiveRecordEvents = False

	@staticmethod
	def TryQuitMainloop(default_yes = True):
		if not RecordTimerEntry.receiveRecordEvents:
			print("RecordTimer.TryQuitMainloop")
			NavigationInstance.instance.record_event.append(RecordTimerEntry.staticGotRecordEvent)
			RecordTimerEntry.receiveRecordEvents = True
			# send fake event.. to check if another recordings are running or
			# other timers start in a few seconds
			RecordTimerEntry.staticGotRecordEvent(None, iRecordableService.evEnd)
			# send normal notification for the case the user leave the standby now..
			Notifications.AddNotification(Screens.Standby.TryQuitMainloop, 1, onSessionOpenCallback=RecordTimerEntry.stopTryQuitMainloop, default_yes = default_yes)
#################################################################

	def __init__(self, serviceref, begin, end, name, description, eit, disabled = False, justplay = False, afterEvent = AFTEREVENT.AUTO, checkOldTimers = False, dirname = None, tags = None):
		timer.TimerEntry.__init__(self, int(begin), int(end))

		if checkOldTimers == True:
			if self.begin < time() - 1209600:
				self.begin = int(time())
		
		if self.end < self.begin:
			self.end = self.begin
		
		assert isinstance(serviceref, ServiceReference)
		
		if serviceref.isRecordable():
			self.service_ref = serviceref
		else:
			self.service_ref = ServiceReference(None)
			# HDSatelit 0.3.0: referinta refuzata (de pilda un program DVB-T2 din satelit), ca fereastra inregistrarii
			# (Screens/TimerEntry.keyGo) sa spuna de ce nu se poate inregistra, nu „Nu ai ales canalul”
			self.hdsRefNeinregistrabila = serviceref
		self.eit = eit
		self.dontSave = False
		self.name = name
		self.description = description
		self.disabled = disabled
		self.timer = None
		self.__record_service = None
		self.start_prepare = 0
		self.justplay = justplay
		self.afterEvent = afterEvent
		self.dirname = dirname
		self.dirnameHadToFallback = False
		self.autoincrease = False
		self.autoincreasetime = 3600 * 24 # 1 day
		self.tags = tags or []
		# HDSatelit: "Decodează mai târziu" (Components/HdsDecodare.py): din oficiu alegerea din setari, numai cu programul
		# de decodare pe receptor; se aplica la inregistrare tot numai cu el (HdsDecodare.seAplica)
		D = hdsDecodare()
		self.hdsDecodareMaiTarziu = bool(D and D.implicit())

		self.log_entries = []
		self.resetState()
	
	def log(self, code, msg):
		self.log_entries.append((int(time()), code, msg))
		print("[TIMER]", msg)

	def calculateFilename(self):
		service_name = self.service_ref.getServiceName()
		begin_date = strftime("%Y%m%d %H%M", localtime(self.begin))
		begin_shortdate = strftime("%Y%m%d", localtime(self.begin))
		
		print("begin_date: ", begin_date)
		print("service_name: ", service_name)
		print("name:", self.name)
		print("description: ", self.description)
		
		filename = begin_date + " - " + service_name
		if self.name:
			if config.usage.setup_level.index >= 2: # expert+
				if config.recording.filename_composition.value == "short":
					filename = begin_shortdate + " - " + self.name
				elif config.recording.filename_composition.value == "long":
					filename += " - " + self.name + " - " + self.description
				else:
					filename += " - " + self.name # standard
			else:
				filename += " - " + self.name

		if config.recording.ascii_filenames.value:
			filename = ASCIItranslit.legacyEncode(filename)

		if not self.dirname or not Directories.fileExists(self.dirname, 'w'):
			if self.dirname:
				self.dirnameHadToFallback = True
			dirname = defaultMoviePath()
		else:
			dirname = self.dirname
		self.Filename = Directories.getRecordingFilename(filename, dirname)
		self.log(0, "Filename calculated as: '%s'" % self.Filename)
		#begin_date + " - " + service_name + description)

	def tryPrepare(self):
		if self.justplay:
			return True
		else:
			self.calculateFilename()
			if not self.hdsVerificaDisc():
				return False
			rec_ref = self.service_ref and self.service_ref.ref
			if rec_ref and rec_ref.flags & eServiceReference.isGroup:
				rec_ref = getBestPlayableServiceReference(rec_ref, eServiceReference())
				if not rec_ref:
					self.log(1, "'get best playable service for group... record' failed")
					return False
				
			self.record_service = rec_ref and NavigationInstance.instance.recordService(rec_ref)

			if not self.record_service:
				self.log(1, "'record service' failed")
				return False

			# HDSatelit: "Decodează mai târziu": semnul trece la serviciul inregistrarii inainte de prepare (de acordare
			# depinde inscrierea la modulul de acces conditionat)
			D = hdsDecodare()
			if D and D.seAplica(self):
				if D.aplica(self.record_service):
					self.log(18, "recording kept scrambled for decoding later")
				else:
					self.log(18, "the recording service cannot keep the recording scrambled")

			if self.repeated:
				epgcache = eEPGCache.getInstance()
				queryTime=self.begin+(self.end-self.begin)//2
				evt = epgcache.lookupEventTime(rec_ref, queryTime)
				if evt:
					self.description = evt.getShortDescription()
					event_id = evt.getEventId()
				else:
					event_id = -1
			else:
				event_id = self.eit
				if event_id is None:
					event_id = -1

			prep_res=self.record_service.prepare(self.Filename + ".ts", self.begin, self.end, event_id, self.name.replace("\n", ""), self.description.replace("\n", ""), ' '.join(self.tags))
			if prep_res:
				if prep_res == -255:
					self.log(4, "failed to write meta information")
				else:
					self.log(2, "'prepare' failed: error %d" % prep_res)

				# we must calc nur start time before stopRecordService call because in Screens/Standby.py TryQuitMainloop tries to get
				# the next start time in evEnd event handler...
				self.do_backoff()
				self.start_prepare = time() + self.backoff

				NavigationInstance.instance.stopRecordService(self.record_service)
				self.record_service = None
				return False
			return True

	def hdsVerificaDisc(self):
		# HDSatelit: pe Viper 4K V20 /media e un tmpfs de 64 KB, deci locul implicit
		# /hdd/movie/ e memorie RAM, nu disc; verificarea veche (fileExists cu 'w') trecea, inregistrarea pornea si cadea
		# cu „Disk full?”. Acum inregistrarea porneste numai pe un disc adevarat montat (Components/HdsStocare.py), altfel
		# un mesaj limpede, o singura data (id), si o noua incercare mai tarziu (backoff, ca la „prepare” esuat: un stick
		# pus intre timp e luat). Fara intrebarea „Disable TV and try again?”, care nu ajuta aici.
		try:
			from Components import HdsStocare
		except ImportError:
			return True
		loc = os.path.dirname(self.Filename) or "/"
		bun, motiv = HdsStocare.verificaDisc(loc)
		self.hdsFaraDisc = not bun
		if bun:
			self.hdsFaraDiscAratat = False
			# discul pe care porneste inregistrarea devine cel tinut minte (Components/HdsLocInregistrari.tineMinte), si cand
			# locul a fost ales din „Căi de Salvare Înregistrări” sau din fereastra temporizatorului
			try:
				from Components import HdsLocInregistrari
			except ImportError:
				HdsLocInregistrari = None
			if HdsLocInregistrari is not None:
				try:
					HdsLocInregistrari.tineMinte(loc)
				except Exception as eroare:
					print("[RecordTimer] remembered disk: %s" % eroare)
			return True
		self.log(17, "no real disk for the recording in %s (%s)" % (loc, motiv))
		dosar = getattr(self, "dirname", None)
		if motiv != "lipsa" and dosar and loc.rstrip("/") == dosar.rstrip("/"):
			# dosarul ales anume pentru acest temporizator exista, dar nu e pe un disc (RAM, memoria interna, disc prea mic,
			# fara scriere): calculateFilename l-ar lua din nou la fiecare reincercare. Reincercarea merge in locul
			# implicit, pe care alegerea din fundal il muta pe un disc bun
			self.log(17, "the folder of this timer (%s) is not on a real disk: the next attempt uses the default place" % dosar)
			self.dirname = None
			self.dirnameHadToFallback = True
		# discul se alege singur, fara ecran (Components/HdsLocInregistrari.alegeInFundal: discul tinut minte, singurul
		# disc bun sau cel cu cel mai mult loc liber), ca sa mearga si in asteptare sau cu ghidul deschis, unde
		# notificarile nu se arata; la fiecare reincercare, deci si un stick pus mai tarziu e luat. Ecranul „Locul
		# înregistrărilor” (numai fara niciun disc bun) o singura data pentru acest temporizator si unul singur pentru
		# toate (id HdsFaraDisc); reincercarea (backoff) gaseste locul nou prin defaultMoviePath()
		try:
			from Components import HdsLocInregistrari
		except ImportError:
			HdsLocInregistrari = None
		if HdsLocInregistrari is not None:
			if HdsLocInregistrari.alegeInFundal(loc, HdsLocInregistrari.SCOP_TEMPORIZATOR, arata=not getattr(self, "hdsFaraDiscAratat", False)):
				self.hdsFaraDiscAratat = True
		elif not getattr(self, "hdsFaraDiscAratat", False):
			self.hdsFaraDiscAratat = True
			Notifications.AddPopup(text=HdsStocare.mesajInregistrare(motiv, loc), type=MessageBox.TYPE_ERROR, timeout=0, id="HdsFaraDisc")
		self.do_backoff()
		self.start_prepare = time() + self.backoff
		return False

	def do_backoff(self):
		if self.backoff == 0:
			self.backoff = 5
		else:
			self.backoff *= 2
			if self.backoff > 100:
				self.backoff = 100
		self.log(10, "backoff: retry in %d seconds" % self.backoff)

	def activate(self):
		next_state = self.state + 1
		self.log(5, "activating state %d" % next_state)

		if next_state == self.StatePrepared:
			if self.tryPrepare():
				self.log(6, "prepare ok, waiting for begin")
				# create file to "reserve" the filename
				# because another recording at the same time on another service can try to record the same event
				# i.e. cable / sat.. then the second recording needs an own extension... when we create the file
				# here than calculateFilename is happy
				if not self.justplay:
					open(self.Filename + ".ts", "w").close() 
				# fine. it worked, resources are allocated.
				self.next_activation = self.begin
				self.backoff = 0
				return True

			self.log(7, "prepare failed")
			if self.first_try_prepare and not getattr(self, "hdsFaraDisc", False):
				self.first_try_prepare = False
				cur_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
				if cur_ref and not cur_ref.getPath():
					if not config.recording.asktozap.value:
						self.log(8, "asking user to zap away")
						Notifications.AddNotificationWithCallback(self.failureCB, MessageBox, _("A timer failed to record!\nDisable TV and try again?\n"), timeout=20)
					else: # zap without asking
						self.log(9, "zap without asking")
						Notifications.AddNotification(MessageBox, _("In order to record a timer, the TV was switched to the recording service!\n"), type=MessageBox.TYPE_INFO, timeout=20)
						self.failureCB(True)
				elif cur_ref:
					self.log(8, "currently running service is not a live service.. so stop it makes no sense")
				else:
					self.log(8, "currently no service running... so we dont need to stop it")
			return False
		elif next_state == self.StateRunning:
			# if this timer has been cancelled, just go to "end" state.
			if self.cancelled:
				return True

			if self.justplay:
				if Screens.Standby.inStandby:
					self.log(11, "wakeup and zap")
					#set service to zap after standby
					Screens.Standby.inStandby.prev_running_service = self.service_ref.ref
					hdsTineMinte(self.service_ref.ref)
					# HDSatelit: trezirea vine de la temporizator, nu de la om: iesirea HDMI porneste, dar televizorul nu
					# se aprinde prin CEC (Components/HdsStandbyTv.py). Inregistrarile nu ies din standby, deci iesirea
					# HDMI ramane oprita cat inregistreaza.
					try:
						from Components import HdsStandbyTv
						HdsStandbyTv.trezitDeTemporizator()
					except Exception as e:
						print("[RecordTimer] HdsStandbyTv: %r" % (e,))
					#wakeup standby
					Screens.Standby.inStandby.Power()
				else:
					self.log(11, "zapping")
					NavigationInstance.instance.playService(self.service_ref.ref)
					hdsTineMinte(self.service_ref.ref)
				return True
			else:
				self.log(11, "start recording")
				# HDSatelit: "Decodează mai târziu": acelasi serviciu pe televizor la pornire (se noteaza in fisierul
				# alaturat: driverul leaga cheia televizorului si de inregistrare, deci o parte poate iesi clara)
				D = hdsDecodare()
				if D and D.seAplica(self):
					D.aplica(self.record_service, D.peTelevizor(
						NavigationInstance.instance.getCurrentlyPlayingServiceReference(), self.service_ref.ref))
				record_res = self.record_service.start()
				
				if record_res:
					self.log(13, "start record returned %d" % record_res)
					self.do_backoff()
					# retry
					self.begin = time() + self.backoff
					return False

				return True
		elif next_state == self.StateEnded:
			old_end = self.end
			if self.setAutoincreaseEnd():
				self.log(12, "autoincrase recording %d minute(s)" % int((self.end - old_end)//60))
				self.state -= 1
				return True
			self.log(12, "stop recording")
			if not self.justplay:
				NavigationInstance.instance.stopRecordService(self.record_service)
				self.record_service = None
			if self.afterEvent == AFTEREVENT.STANDBY:
				if not Screens.Standby.inStandby: # not already in standby
					Notifications.AddNotificationWithCallback(self.sendStandbyNotification, MessageBox, _("A finished record timer wants to set your\nreceiver to standby. Do that now?"), timeout = 20)
			elif self.afterEvent == AFTEREVENT.DEEPSTANDBY:
				if not Screens.Standby.inTryQuitMainloop: # not a shutdown messagebox is open
					if Screens.Standby.inStandby: # in standby
						RecordTimerEntry.TryQuitMainloop() # start shutdown handling without screen
					else:
						Notifications.AddNotificationWithCallback(self.sendTryQuitMainloopNotification, MessageBox, _("A finished record timer wants to shut down\nyour receiver. Shutdown now?"), timeout = 20)
			return True

	def setAutoincreaseEnd(self, entry = None):
		if not self.autoincrease:
			return False
		if entry is None:
			new_end =  int(time()) + self.autoincreasetime
		else:
			new_end = entry.begin -30

		dummyentry = RecordTimerEntry(self.service_ref, self.begin, new_end, self.name, self.description, self.eit, disabled=True, justplay = self.justplay, afterEvent = self.afterEvent, dirname = self.dirname, tags = self.tags)
		dummyentry.disabled = self.disabled
		timersanitycheck = TimerSanityCheck(NavigationInstance.instance.RecordTimer.timer_list, dummyentry)
		if not timersanitycheck.check():
			simulTimerList = timersanitycheck.getSimulTimerList()
			if simulTimerList is not None and len(simulTimerList) > 1:
				new_end = simulTimerList[1].begin
				new_end -= 30				# 30 Sekunden Prepare-Zeit lassen
		if new_end <= time():
			return False
		self.end = new_end
		return True

	def sendStandbyNotification(self, answer):
		if answer:
			Notifications.AddNotification(Screens.Standby.Standby)

	def sendTryQuitMainloopNotification(self, answer):
		if answer:
			Notifications.AddNotification(Screens.Standby.TryQuitMainloop, 1)

	def getNextActivation(self):
		if self.state == self.StateEnded:
			return self.end
		
		next_state = self.state + 1
		
		return {self.StatePrepared: self.start_prepare, 
				self.StateRunning: self.begin, 
				self.StateEnded: self.end }[next_state]

	def failureCB(self, answer):
		if answer == True:
			self.log(13, "ok, zapped away")
			#NavigationInstance.instance.stopUserServices()
			NavigationInstance.instance.playService(self.service_ref.ref)
			hdsTineMinte(self.service_ref.ref)
		else:
			self.log(14, "user didn't want to zap away, record will probably fail")

	def timeChanged(self):
		old_prepare = self.start_prepare
		self.start_prepare = self.begin - self.prepare_time
		self.backoff = 0
		
		if int(old_prepare) != int(self.start_prepare):
			self.log(15, "record time changed, start prepare is now: %s" % ctime(self.start_prepare))

	def gotRecordEvent(self, record, event):
		# TODO: this is not working (never true), please fix. (comparing two swig wrapped ePtrs)
		if self.__record_service.__deref__() != record.__deref__():
			return
		self.log(16, "record event %d" % event)
		if event == iRecordableService.evRecordWriteError:
			print("WRITE ERROR on recording, disk full?")
			# show notification. the 'id' will make sure that it will be
			# displayed only once, even if more timers are failing at the
			# same time. (which is very likely in case of disk fullness)
			Notifications.AddPopup(text = _("Write error while recording. Disk full?\n"), type = MessageBox.TYPE_ERROR, timeout = 0, id = "DiskFullMessage")
			# ok, the recording has been stopped. we need to properly note 
			# that in our state, with also keeping the possibility to re-try.
			# TODO: this has to be done.
		elif event == iRecordableService.evStart:
			text = _("A record has been started:\n%s") % self.name
			if self.dirnameHadToFallback:
				text = '\n'.join((text, _("Please note that the previously selected media could not be accessed and therefore the default directory is being used instead.")))

			if config.usage.show_message_when_recording_starts.value:
				Notifications.AddPopup(text = text, type = MessageBox.TYPE_INFO, timeout = 3)

	# we have record_service as property to automatically subscribe to record service events
	def setRecordService(self, service):
		if self.__record_service is not None:
			print("[remove callback]")
			NavigationInstance.instance.record_event.remove(self.gotRecordEvent)

		self.__record_service = service

		if self.__record_service is not None:
			print("[add callback]")
			NavigationInstance.instance.record_event.append(self.gotRecordEvent)

	record_service = property(lambda self: self.__record_service, setRecordService)

def createTimer(xml):
	begin = int(xml.get("begin"))
	end = int(xml.get("end"))
	serviceref = ServiceReference(xmlAttributeValue(xml, "serviceref"))
	description = xmlAttributeValue(xml, "description")
	repeated = xml.get("repeated")
	disabled = int(xml.get("disabled") or "0")
	justplay = int(xml.get("justplay") or "0")
	afterevent = str(xml.get("afterevent") or "nothing")
	afterevent = {
		"nothing": AFTEREVENT.NONE,
		"standby": AFTEREVENT.STANDBY,
		"deepstandby": AFTEREVENT.DEEPSTANDBY,
		"auto": AFTEREVENT.AUTO
		}[afterevent]
	eit = xml.get("eit")
	if eit and eit != "None":
		eit = int(eit);
	else:
		eit = None
	location = xmlAttributeValue(xml, "location")
	if location and location != "None":
		location = location
	else:
		location = None
	tags = xmlAttributeValue(xml, "tags")
	if tags and tags != "None":
		tags = tags.split(' ')
	else:
		tags = None

	name = xmlAttributeValue(xml, "name")
	#filename = xml.get("filename")
	entry = RecordTimerEntry(serviceref, begin, end, name, description, eit, disabled, justplay, afterevent, dirname = location, tags = tags)
	entry.repeated = int(repeated)
	# HDSatelit: "Decodează mai târziu" se tine in timers.xml chiar si fara programul de decodare (se aplica numai cu el)
	entry.hdsDecodareMaiTarziu = xml.get("hdsdecodare") == "1"
	
	for l in xml.findall("log"):
		time = int(l.get("time"))
		code = int(l.get("code"))
		msg = xmlAttributeValue(l, "text")
		if msg is None:
			msg = l.text or ""
		msg = msg.strip()
		entry.log_entries.append((time, code, msg))
	
	return entry

class RecordTimer(timer.Timer):
	def __init__(self):
		timer.Timer.__init__(self)
		
		self.Filename = Directories.resolveFilename(Directories.SCOPE_CONFIG, "timers.xml")
		
		try:
			self.loadTimer()
		except IOError:
			print("unable to load timers from file!")

	def doActivate(self, w):
		# when activating a timer which has already passed,
		# simply abort the timer. don't run trough all the stages.
		if w.shouldSkip():
			w.state = RecordTimerEntry.StateEnded
		else:
			# when active returns true, this means "accepted".
			# otherwise, the current state is kept.
			# the timer entry itself will fix up the delay then.
			if w.activate():
				w.state += 1

		self.timer_list.remove(w)

		# did this timer reached the last state?
		if w.state < RecordTimerEntry.StateEnded:
			# no, sort it into active list
			insort(self.timer_list, w)
		else:
			# yes. Process repeated, and re-add.
			if w.repeated:
				w.processRepeated()
				w.state = RecordTimerEntry.StateWaiting
				self.addTimerEntry(w)
			else:
				insort(self.processed_timers, w)
		
		self.stateChanged(w)

	def isRecording(self):
		isRunning = False
		for timer in self.timer_list:
			if timer.isRunning() and not timer.justplay:
				isRunning = True
		return isRunning
	
	def loadTimer(self):
		# TODO: PATH!
		try:
			doc = xml.etree.ElementTree.parse(self.Filename)
		except SyntaxError:
			from Tools.Notifications import AddPopup
			from Screens.MessageBox import MessageBox

			AddPopup(_("The timer file (timers.xml) is corrupt and could not be loaded."), type = MessageBox.TYPE_ERROR, timeout = 0, id = "TimerLoadFailed")

			print("timers.xml failed to load!")
			try:
				import os
				os.rename(self.Filename, self.Filename + "_old")
			except (IOError, OSError):
				print("renaming broken timer failed")
			return
		except IOError:
			print("timers.xml not found!")
			return

		root = doc.getroot()

		# put out a message when at least one timer overlaps
		checkit = True
		for timer in root.findall("timer"):
			newTimer = createTimer(timer)
			if (self.record(newTimer, True, dosave=False) is not None) and (checkit == True):
				from Tools.Notifications import AddPopup
				from Screens.MessageBox import MessageBox
				AddPopup(_("Timer overlap in timers.xml detected!\nPlease recheck it!"), type = MessageBox.TYPE_ERROR, timeout = 0, id = "TimerLoadFailed")
				checkit = False # at moment it is enough when the message is displayed one time

	def saveTimer(self):
		#root_element = xml.etree.ElementTree.Element('timers')
		#root_element.text = "\n"

		#for timer in self.timer_list + self.processed_timers:
			# some timers (instant records) don't want to be saved.
			# skip them
			#if timer.dontSave:
				#continue
			#t = xml.etree.ElementTree.SubElement(root_element, 'timers')
			#t.set("begin", str(int(timer.begin)))
			#t.set("end", str(int(timer.end)))
			#t.set("serviceref", str(timer.service_ref))
			#t.set("repeated", str(timer.repeated))			
			#t.set("name", timer.name)
			#t.set("description", timer.description)
			#t.set("afterevent", str({
			#	AFTEREVENT.NONE: "nothing",
			#	AFTEREVENT.STANDBY: "standby",
			#	AFTEREVENT.DEEPSTANDBY: "deepstandby",
			#	AFTEREVENT.AUTO: "auto"}))
			#if timer.eit is not None:
			#	t.set("eit", str(timer.eit))
			#if timer.dirname is not None:
			#	t.set("location", str(timer.dirname))
			#t.set("disabled", str(int(timer.disabled)))
			#t.set("justplay", str(int(timer.justplay)))
			#t.text = "\n"
			#t.tail = "\n"

			#for time, code, msg in timer.log_entries:
				#l = xml.etree.ElementTree.SubElement(t, 'log')
				#l.set("time", str(time))
				#l.set("code", str(code))
				#l.text = str(msg)
				#l.tail = "\n"

		#doc = xml.etree.ElementTree.ElementTree(root_element)
		#doc.write(self.Filename)

		list = []

		list.append('<?xml version="1.0" ?>\n')
		list.append('<timers>\n')
		
		for timer in self.timer_list + self.processed_timers:
			if timer.dontSave:
				continue

			list.append('<timer')
			list.append(' begin="' + str(int(timer.begin)) + '"')
			list.append(' end="' + str(int(timer.end)) + '"')
			list.append(xmlAttribute('serviceref', timer.service_ref))
			list.append(' repeated="' + str(int(timer.repeated)) + '"')
			list.append(xmlAttribute('name', timer.name))
			list.append(xmlAttribute('description', timer.description))
			list.append(' afterevent="' + str(stringToXML({
				AFTEREVENT.NONE: "nothing",
				AFTEREVENT.STANDBY: "standby",
				AFTEREVENT.DEEPSTANDBY: "deepstandby",
				AFTEREVENT.AUTO: "auto"
				}[timer.afterEvent])) + '"')
			if timer.eit is not None:
				list.append(' eit="' + str(timer.eit) + '"')
			if timer.dirname is not None:
				list.append(xmlAttribute('location', timer.dirname))
			if timer.tags is not None:
				list.append(xmlAttribute('tags', ' '.join(timer.tags)))
			list.append(' disabled="' + str(int(timer.disabled)) + '"')
			list.append(' justplay="' + str(int(timer.justplay)) + '"')
			if getattr(timer, "hdsDecodareMaiTarziu", False):
				list.append(' hdsdecodare="1"')
			list.append('>\n')
			
			if config.recording.debug.value:
				for time, code, msg in timer.log_entries:
					list.append('<log')
					list.append(' code="' + str(code) + '"')
					list.append(' time="' + str(time) + '"')
					safe_msg, raw_msg = xmlSafeText(msg)
					if raw_msg is not None:
						list.append(' text_raw="' + raw_msg + '"')
					list.append('>')
					list.append(stringToXML(safe_msg))
					list.append('</log>\n')
			
			list.append('</timer>\n')

		list.append('</timers>\n')

		# Scriere atomica: nimic nu ramane taiat nici la disc plin, nici la o eroare de codare, nici la
		# caderea curentului. Intai facem tot documentul in memorie (daca ceva ar arunca, fisierul vechi
		# nici nu e atins), apoi scriem intr-un fisier temporar langa el, il ducem pe disc cu fsync si
		# abia la sfarsit il punem in locul celui vechi cu os.replace (o singura miscare, neintrerupta).
		data = "".join(list).encode("utf-8")
		tmpname = self.Filename + ".writing"
		try:
			f = open(tmpname, "wb")
			try:
				f.write(data)
				f.flush()
				os.fsync(f.fileno())
			finally:
				f.close()
			os.replace(tmpname, self.Filename)
		except:
			try:
				os.unlink(tmpname)
			except OSError:
				pass
			raise
		# fara fsync pe dosar, redenumirea insasi se poate pierde la caderea curentului
		try:
			dirfd = os.open(os.path.dirname(self.Filename) or ".", os.O_RDONLY)
			try:
				os.fsync(dirfd)
			finally:
				os.close(dirfd)
		except OSError:
			pass

	def getNextZapTime(self):
		now = time()
		for timer in self.timer_list:
			if not timer.justplay or timer.begin < now:
				continue
			return timer.begin
		return -1

	def getNextRecordingTime(self):
		now = time()
		for timer in self.timer_list:
			next_act = timer.getNextActivation()
			if timer.justplay or next_act < now:
				continue
			return next_act
		return -1

	def isNextRecordAfterEventActionAuto(self):
		now = time()
		t = None
		for timer in self.timer_list:
			if timer.justplay or timer.begin < now:
				continue
			if t is None or t.begin == timer.begin:
				t = timer
				if t.afterEvent == AFTEREVENT.AUTO:
					return True
		return False

	def record(self, entry, ignoreTSC=False, dosave=True):		#wird von loadTimer mit dosave=False aufgerufen
		timersanitycheck = TimerSanityCheck(self.timer_list,entry)
		if not timersanitycheck.check():
			if ignoreTSC != True:
				print("timer conflict detected!")
				print(timersanitycheck.getSimulTimerList())
				return timersanitycheck.getSimulTimerList()
			else:
				print("ignore timer conflict")
		elif timersanitycheck.doubleCheck():
			print("ignore double timer")
			return None
		entry.timeChanged()
		print("[Timer] Record " + str(entry))
		entry.Timer = self
		self.addTimerEntry(entry)
		if dosave:
			self.saveTimer()
			self.hdsLaProgramare(entry)
		return None

	def hdsLaProgramare(self, entry):
		# HDSatelit: un temporizator nou (din ghid, din lista, din web; loadTimer nu trece pe aici): daca locul lui nu e un
		# disc bun, discul se alege acum, nu la ora inregistrarii (Components/HdsLocInregistrari.laProgramare, pe fire;
		# intrebarea sau „niciun disc” apar in notificari)
		if entry.justplay:
			return
		try:
			from Components import HdsLocInregistrari
			HdsLocInregistrari.laProgramare(entry.dirname)
		except Exception as eroare:
			print("[RecordTimer] place of the new timer: %s" % eroare)

	def isInTimer(self, eventid, begin, duration, service):
		time_match = 0
		chktime = None
		chktimecmp = None
		chktimecmp_end = None
		end = begin + duration
		refstr = str(service)
		for x in self.timer_list:
			check = x.service_ref.ref.toString() == refstr
			if not check:
				sref = x.service_ref.ref
				parent_sid = sref.getUnsignedData(5)
				parent_tsid = sref.getUnsignedData(6)
				if parent_sid and parent_tsid: # check for subservice
					sid = sref.getUnsignedData(1)
					tsid = sref.getUnsignedData(2)
					sref.setUnsignedData(1, parent_sid)
					sref.setUnsignedData(2, parent_tsid)
					sref.setUnsignedData(5, 0)
					sref.setUnsignedData(6, 0)
					check = sref.toCompareString() == refstr
					num = 0
					if check:
						check = False
						event = eEPGCache.getInstance().lookupEventId(sref, eventid)
						num = event and event.getNumOfLinkageServices() or 0
					sref.setUnsignedData(1, sid)
					sref.setUnsignedData(2, tsid)
					sref.setUnsignedData(5, parent_sid)
					sref.setUnsignedData(6, parent_tsid)
					for cnt in range(num):
						subservice = event.getLinkageService(sref, cnt)
						if sref.toCompareString() == subservice.toCompareString():
							check = True
							break
			if check:
				if x.repeated != 0:
					if chktime is None:
						chktime = localtime(begin)
						chktimecmp = chktime.tm_wday * 1440 + chktime.tm_hour * 60 + chktime.tm_min
						chktimecmp_end = chktimecmp + (duration // 60)
					time = localtime(x.begin)
					for y in (0, 1, 2, 3, 4, 5, 6):
						if x.repeated & (1 << y) and (x.begin <= begin or begin <= x.begin <= end):
							timecmp = y * 1440 + time.tm_hour * 60 + time.tm_min
							if timecmp <= chktimecmp < (timecmp + ((x.end - x.begin) // 60)):
								time_match = ((timecmp + ((x.end - x.begin) // 60)) - chktimecmp) * 60
							elif chktimecmp <= timecmp < chktimecmp_end:
								time_match = (chktimecmp_end - timecmp) * 60
				else: #if x.eit is None:
					if begin <= x.begin <= end:
						diff = end - x.begin
						if time_match < diff:
							time_match = diff
					elif x.begin <= begin <= x.end:
						diff = x.end - begin
						if time_match < diff:
							time_match = diff
				if time_match:
					break
		return time_match

	def removeEntry(self, entry):
		print("[Timer] Remove " + str(entry))
		
		# avoid re-enqueuing
		entry.repeated = False

		# abort timer.
		# this sets the end time to current time, so timer will be stopped.
		entry.autoincrease = False
		entry.abort()
		
		if entry.state != entry.StateEnded:
			self.timeChanged(entry)
		
		print("state: ", entry.state)
		print("in processed: ", entry in self.processed_timers)
		print("in running: ", entry in self.timer_list)
		# autoincrease instanttimer if possible
		if not entry.dontSave:
			for x in self.timer_list:
				if x.setAutoincreaseEnd():
					self.timeChanged(x)
		# now the timer should be in the processed_timers list. remove it from there.
		self.processed_timers.remove(entry)
		self.saveTimer()

	def shutdown(self):
		self.saveTimer()

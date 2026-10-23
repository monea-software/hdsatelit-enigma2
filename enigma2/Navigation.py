# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eServiceCenter, eServiceReference, pNavigation, getBestPlayableServiceReference, iPlayableService
from Components.ParentalControl import parentalControl
from Tools.BoundFunction import boundFunction
from Tools.DreamboxHardware import setFPWakeuptime, getFPWakeuptime, getFPWasTimerWakeup, clearFPWasTimerWakeup
from time import time, monotonic as _monoton
import RecordTimer
import SleepTimer
import Screens.Standby
import NavigationInstance
import ServiceReference
import sys

# masurarea zap-ului (Components/HdsMasuraZap.py): pasii lui playService si fiecare ascultator, cateva secunde dupa
# fiecare zap, scrisi intr-un fisier din /tmp; fara modul (probele de pe PC), nimic
try:
	from Components.HdsMasuraZap import masura as _masura
except Exception:
	_masura = None

# TODO: remove pNavgation, eNavigation and rewrite this stuff in python.
class Navigation:
	# Punctele de extensie ale zap-ului si ale inregistrarii (atribute de clasa; Hds/DabT2 pune aici DAB+ si DVB-T2).
	# playServiceExtensions: f(nav, playref, event, infobar) -> (playref, asincron) sau numai playref. Se cheama dupa
	# oprirea serviciului vechi (tunerul si playerul sunt liberi), inainte de pornirea playerului. asincron=True: extensia
	# porneste singura serviciul mai tarziu (nav.playService(ref, forceRestart=True)), deci playerul nu porneste acum,
	# iar getCurrentlyPlayingServiceReference() da referinta ceruta. Prima extensie care schimba referinta sau o ia
	# asincron le opreste pe celelalte. O extensie care arunca exceptie e sarita (un rand in jurnal), zap-ul merge.
	# recordServiceExtensions: f(nav, ref) -> ref (None = neschimbata), inainte de pnav.recordService; in cadrul care
	# le cheama variabila locala `simulate` spune daca e doar o verificare.
	playServiceExtensions = []
	recordServiceExtensions = []

	def __init__(self, nextRecordTimerAfterEventActionAuto=False):
		if NavigationInstance.instance is not None:
			raise NavigationInstance.instance
		
		NavigationInstance.instance = self
		self.ServiceHandler = eServiceCenter.getInstance()
		
		import Navigation as Nav
		Nav.navcore = self
		
		self.pnav = pNavigation()
		self.pnav.m_event.get().append(self.dispatchEvent)
		self.pnav.m_record_event.get().append(self.dispatchRecordEvent)
		self.event = [ ]
		self.record_event = [ ]
		self.currentlyPlayingServiceReference = None
		self.currentlyPlayingService = None
		self.RecordTimer = RecordTimer.RecordTimer()
		if getFPWasTimerWakeup():
			clearFPWasTimerWakeup()
			if getFPWasTimerWakeup(): # sanity check to detect if the FP driver is working correct!
				print("buggy fp driver detected!!! please update drivers.... ignore timer wakeup!")
			elif nextRecordTimerAfterEventActionAuto and (len(self.getRecordings()) or abs(self.RecordTimer.getNextRecordingTime() - time()) <= 360):
				if not Screens.Standby.inTryQuitMainloop: # not a shutdown messagebox is open
					RecordTimer.RecordTimerEntry.TryQuitMainloop(False) # start shutdown handling
		self.SleepTimer = SleepTimer.SleepTimer()

	def dispatchEvent(self, i):
		m = _masura
		if m is not None and m.activ():
			t = _monoton()
			for x in self.event:
				a = _monoton()
				x(i)
				m.ascultator(i, x, _monoton() - a)
			m.eveniment(i, t, _monoton() - t)
		else:
			for x in self.event:
				x(i)
		if i == iPlayableService.evEnd:
			self.currentlyPlayingServiceReference = None
			self.currentlyPlayingService = None

	def dispatchRecordEvent(self, rec_service, event):
#		print "record_event", rec_service, event
		for x in self.record_event:
			x(rec_service, event)

	def playService(self, ref, checkParentalControl = True, forceRestart = False):
		m = _masura
		oldref = self.currentlyPlayingServiceReference
		if m is None or not ref or (oldref and ref == oldref and not forceRestart):
			return self._playService(ref, checkParentalControl, forceRestart)
		m.incepe(_refText(ref))
		t = _monoton()
		try:
			return self._playService(ref, checkParentalControl, forceRestart)
		finally:
			m.pas("playService", t, _monoton() - t)

	def _playService(self, ref, checkParentalControl, forceRestart):
		oldref = self.currentlyPlayingServiceReference
		if ref and oldref and ref == oldref and not forceRestart:
			print("ignore request to play already running service(1)")
			return 0
		print("playing", ref and ref.toString())
		if ref is None:
			self.stopService()
			return 0
		if not checkParentalControl or parentalControl.isServicePlayable(ref, boundFunction(self.playService, checkParentalControl = False)):
			if ref.flags & eServiceReference.isGroup:
				if not oldref:
					oldref = eServiceReference()
				playref = getBestPlayableServiceReference(ref, oldref)
				print("playref", playref)
				if playref and oldref and playref == oldref and not forceRestart:
					print("ignore request to play already running service(2)")
					return 0
				if not playref or (checkParentalControl and not parentalControl.isServicePlayable(playref, boundFunction(self.playService, checkParentalControl = False))):
					self.stopService()
					return 0
			else:
				playref = ref
			extensii = bool(self.pnav and Navigation.playServiceExtensions)
			if extensii:
				playref, asincron = self._extensiiZap(playref)
				if asincron:
					return 0
			if self.pnav:
				t = _monoton()
				rez = self.pnav.playService(playref)
				if _masura is not None:
					_masura.pas("pnav.playService", t, _monoton() - t)
				if not rez:
					self.currentlyPlayingServiceReference = playref
					return 0
			if extensii:
				# pornirea a cazut: referinta ceruta pusa inaintea extensiilor nu mai e valabila
				self.currentlyPlayingServiceReference = None
		else:
			self.stopService()
		return 1

	def _extensiiZap(self, playref):
		"""Serviciul vechi se opreste, referinta curenta devine cea ceruta (extensiile care pornesc singure serviciul o
		compara mai tarziu), apoi extensiile pe rand. -> (playref, asincron)."""
		t = _monoton()
		self.pnav.stopService()
		if _masura is not None:
			_masura.pas("oprire", t, _monoton() - t)
		self.currentlyPlayingServiceReference = playref
		infobar = getattr(getattr(sys.modules.get("Screens.InfoBar"), "InfoBar", None), "instance", None)
		t = _monoton()
		try:
			return self._extensiiPeRand(playref, infobar)
		finally:
			if _masura is not None:
				_masura.pas("extensii", t, _monoton() - t)

	def _extensiiPeRand(self, playref, infobar):
		for f in list(Navigation.playServiceExtensions):
			try:
				rez = f(self, playref, None, infobar)
			except Exception as e:
				print("[Navigation] extensia de zap %s a cazut: %s" % (getattr(f, "__name__", "?"), e))
				continue
			if isinstance(rez, tuple):
				nou, asincron = rez[0], bool(rez[1]) if len(rez) > 1 else False
			else:
				nou, asincron = rez, False
			schimbat = nou is not None and nou is not playref and _refText(nou) != _refText(playref)
			if schimbat:
				playref = nou
				self.currentlyPlayingServiceReference = playref
			if asincron or schimbat:
				return playref, asincron
		return playref, False
	
	def getCurrentlyPlayingServiceReference(self):
		return self.currentlyPlayingServiceReference
	
	def recordService(self, ref, simulate=False):
		service = None
		print("recording service: %s" % (str(ref)))
		if isinstance(ref, ServiceReference.ServiceReference):
			ref = ref.ref
		if ref:
			if ref.flags & eServiceReference.isGroup:
				ref = getBestPlayableServiceReference(ref, eServiceReference(), simulate)
			if ref and Navigation.recordServiceExtensions:
				ref = self._extensiiInregistrare(ref, simulate)
			service = ref and self.pnav and self.pnav.recordService(ref, simulate)
			if service is None:
				print("record returned non-zero")
		return service

	def _extensiiInregistrare(self, ref, simulate):
		"""Extensiile inregistrarii, pe rand. `simulate` ramane variabila locala a acestui cadru (o extensie care cedeaza
		tunerul unei inregistrari adevarate o citeste de aici)."""
		for f in list(Navigation.recordServiceExtensions):
			try:
				rez = f(self, ref)
			except Exception as e:
				print("[Navigation] extensia de inregistrare %s a cazut: %s" % (getattr(f, "__name__", "?"), e))
				continue
			if rez is not None:
				ref = rez
		return ref

	def stopRecordService(self, service):
		ret = self.pnav and self.pnav.stopRecordService(service)
		return ret

	def getRecordings(self, simulate=False):
		return self.pnav and self.pnav.getRecordings(simulate)

	def getCurrentService(self):
		if not self.currentlyPlayingService:
			self.currentlyPlayingService = self.pnav and self.pnav.getCurrentService()
		return self.currentlyPlayingService

	def stopService(self):
		print("stopService")
		if self.pnav:
			self.pnav.stopService()
		# evEnd le goleste numai daca rula un player; dupa un zap luat asincron de o extensie nu rula niciunul
		self.currentlyPlayingServiceReference = None
		self.currentlyPlayingService = None

	def pause(self, p):
		return self.pnav and self.pnav.pause(p)

	def shutdown(self):
		self.RecordTimer.shutdown()
		self.ServiceHandler = None
		self.pnav = None

	def stopUserServices(self):
		self.stopService()


def _refText(ref):
	"""Textul unei referinte (eServiceReference sau sir), pentru comparatii; "" daca nu se poate citi."""
	try:
		return ref.toString()
	except Exception:
		return str(ref)

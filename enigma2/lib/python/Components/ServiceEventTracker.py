# Modificat de moneasoftware.com si hdsatelit.com, 2026
from time import monotonic as _monoton

# masurarea zap-ului (Components/HdsMasuraZap.py): cat tine fiecare ecran care urmareste serviciul, in fereastra
# de dupa un zap
try:
	from Components.HdsMasuraZap import masura as _masura
except Exception:
	_masura = None


class InfoBarBase:
	def __init__(self, steal_current_service = False):
		if steal_current_service:
			ServiceEventTracker.setActiveInfoBar(self, None, None)
		else:
			nav = self.session.nav
			ServiceEventTracker.setActiveInfoBar(self, not steal_current_service and nav.getCurrentService(), nav.getCurrentlyPlayingServiceReference())
		self.onClose.append(self.__close)

	def __close(self):
		ServiceEventTracker.popActiveInfoBar()

class ServiceEventTracker:
	"""Tracks service events into a screen"""
	InfoBarStack = [ ]
	InfoBarStackSize = 0
	oldServiceStr = None
	EventMap = { }
	navcore = None

	@staticmethod
	def event(evt):
		set = ServiceEventTracker
		func_list = set.EventMap.setdefault(evt, [])
		if func_list:
			nav = set.navcore
			cur_ref = nav.getCurrentlyPlayingServiceReference()
			old_service_running = set.oldRef and cur_ref and cur_ref == set.oldRef and set.oldServiceStr == nav.getCurrentService().getPtrString()
			if not old_service_running and set.oldServiceStr:
				set.oldServiceStr = None
				set.oldRef = None
			ssize = set.InfoBarStackSize
			stack = set.InfoBarStack
			m = _masura
			activ = m is not None and m.activ()
			for func in func_list:
				if (func[0] or  # let pass all events to screens not derived from InfoBarBase
					(not old_service_running and stack[ssize-1] == func[1]) or # let pass events from currently running service just to current active screen (derived from InfoBarBase)
					(old_service_running and ssize > 1 and stack[ssize-2] == func[1])): # let pass events from old running service just to previous active screen (derived from InfoBarBase)
					if activ:
						a = _monoton()
						func[2]()
						m.ascultator(evt, func[2], _monoton() - a, ecran=True)
					else:
						func[2]()

	@staticmethod
	def setActiveInfoBar(infobar, old_service, old_ref):
		set = ServiceEventTracker
		set.oldRef = old_ref
		set.oldServiceStr = old_service and old_service.getPtrString()
		assert infobar not in set.InfoBarStack, "FATAL: Infobar '" + str(infobar) + "' is already active!"
		set.InfoBarStack.append(infobar)
		set.InfoBarStackSize += 1
#		print "ServiceEventTracker set active '" + str(infobar) + "'"

	@staticmethod
	def hdsPreiaServiciul():
		"""Ecranul scos din stiva a lasat serviciul care merge ecranului din varful ei: playerul de filme inchis de un canal
		pornit peste film (Screens/InfoBar.py) si lista radio separata inchisa pe postul pornit din ea
		(Screens/ChannelSelection.py, ChannelSelectionRadio). popActiveInfoBar tine serviciul care merge drept serviciu
		vechi (oldRef), pentru clipa dintre inchidere si pornirea serviciului de dinainte; cand serviciul ramane,
		evenimentele lui nu mai ajungeau la nimeni cu un singur ecran in stiva (bara canalelor) pana la zapul urmator.
		De acum serviciul e al ecranului din varf, ca dupa un zap. Evenimentele de pornire le-a primit ecranul inchis,
		deci sunetul si subtitrarea le alege din nou bara (InfoBarSubtitleSupport.hdsAlegeDinNou)."""
		set = ServiceEventTracker
		set.oldRef = None
		set.oldServiceStr = None

	@staticmethod
	def popActiveInfoBar():
		set = ServiceEventTracker
		stack = set.InfoBarStack
		if set.InfoBarStackSize:
			nav = set.navcore
			set.InfoBarStackSize -= 1
			del stack[set.InfoBarStackSize]
			old_service = nav.getCurrentService()
			set.oldServiceStr = old_service and old_service.getPtrString()
			set.oldRef = nav.getCurrentlyPlayingServiceReference()
#			if set.InfoBarStackSize:
#				print "ServiceEventTracker reset active '" + str(stack[set.InfoBarStackSize-1]) + "'"

	def __init__(self, screen, eventmap):
		self.__screen = screen
		self.__eventmap = eventmap
		self.__passall = not isinstance(screen, InfoBarBase) # let pass all events to screens not derived from InfoBarBase
		EventMap = ServiceEventTracker.EventMap
		if not len(EventMap):
			screen.session.nav.event.append(ServiceEventTracker.event)
			ServiceEventTracker.navcore = screen.session.nav
		EventMap = EventMap.setdefault
		for x in eventmap.items():
			EventMap(x[0], []).append((self.__passall, screen, x[1]))
		screen.onClose.append(self.__del_event)

	def __del_event(self):
		EventMap = ServiceEventTracker.EventMap.setdefault
		for x in self.__eventmap.items():
			EventMap(x[0], []).remove((self.__passall, self.__screen, x[1]))

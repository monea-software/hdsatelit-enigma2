# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .ChannelSelection import ChannelSelection, BouquetSelector, SilentBouquetSelector

from Components.ActionMap import ActionMap, HelpableActionMap
from Components.ActionMap import NumberActionMap
from Components.Harddisk import harddiskmanager
from Components.Input import Input
from Components.Label import Label
from Components.PluginComponent import plugins
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.Boolean import Boolean
from Components.config import config, ConfigBoolean, ConfigClock, ConfigSelection
from Components.SystemInfo import SystemInfo
from Components.UsageConfig import preferredInstantRecordPath, defaultMoviePath
from .EpgSelection import EPGSelection
from Plugins.Plugin import PluginDescriptor

from .Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.HdsDishMotor import HdsDishMotor
from Screens.EventView import EventViewEPGSelect, EventViewSimple
from Screens.InputBox import InputBox
from Screens.MessageBox import MessageBox
from Screens.MinuteInput import MinuteInput
from Screens.TimerSelection import TimerSelection
from Screens.PictureInPicture import PictureInPicture
from Screens.SubtitleDisplay import SubtitleDisplay
from Screens.RdsDisplay import RdsInfoDisplay, RassInteractive
from Screens.TimeDateInput import TimeDateInput
from Screens.UnhandledKey import UnhandledKey
from Screens.SecondInfoBar import SecondInfoBar
from ServiceReference import ServiceReference

from Tools import Notifications
from Tools.Directories import fileExists

from enigma import eTimer, eServiceCenter, eDVBServicePMTHandler, iServiceInformation, \
	iPlayableService, eServiceReference, eEPGCache, eActionMap

from time import time, localtime, strftime
from bisect import insort

from RecordTimer import RecordTimerEntry, RecordTimer

# hack alert!
from .Menu import MainMenu, mdom

class InfoBarDish:
	def __init__(self):
		# HDSatelit: in loc de chenarul mic cu o poza care clipeste (Screens/Dish.py, pastrat pentru
		# skinurile care il cer pe nume), panoul cu directia, gradele, satelitii si antena care se roteste.
		self.dishDialog = self.session.instantiateDialog(HdsDishMotor)

class InfoBarUnhandledKey:
	def __init__(self):
		self.unhandledKeyDialog = self.session.instantiateDialog(UnhandledKey)
		self.hideUnhandledKeySymbolTimer = eTimer()
		self.hideUnhandledKeySymbolTimer.callback.append(self.unhandledKeyDialog.hide)
		self.checkUnusedTimer = eTimer()
		self.checkUnusedTimer.callback.append(self.checkUnused)
		self.onLayoutFinish.append(self.unhandledKeyDialog.hide)
		eActionMap.getInstance().bindAction('', -0x7FFFFFFF, self.actionA) #highest prio
		eActionMap.getInstance().bindAction('', 0x7FFFFFFF, self.actionB) #lowest prio
		self.flags = (1<<1);
		self.uflags = 0;

	#this function is called on every keypress!
	def actionA(self, key, flag):
		if flag != 4:
			if self.flags & (1<<1):
				self.flags = self.uflags = 0
			self.flags |= (1<<flag)
			if flag == 1: # break
				self.checkUnusedTimer.start(0, True)
		return 0

	#this function is only called when no other action has handled this key
	def actionB(self, key, flag):
		if flag != 4:
			self.uflags |= (1<<flag)

	def checkUnused(self):
		if self.flags == self.uflags:
			self.unhandledKeyDialog.show()
			self.hideUnhandledKeySymbolTimer.start(2000, True)

class InfoBarShowHide:
	""" InfoBar show/hide control, accepts toggleShow and hide actions, might start
	fancy animations. """
	STATE_HIDDEN = 0
	STATE_HIDING = 1
	STATE_SHOWING = 2
	STATE_SHOWN = 3

	def __init__(self):
		self["ShowHideActions"] = ActionMap( ["InfobarShowHideActions"] ,
			{
				"toggleShow": self.toggleShow,
				"hide": self.hide,
			}, 1) # lower prio to make it possible to override ok and cancel..

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.serviceStarted,
			})

		self.__state = self.STATE_SHOWN
		self.__locked = 0

		self.secondInfoBarScreen = self.session.instantiateDialog(SecondInfoBar)
		# HDSatelit: proprietarul barei (InfoBar sau MoviePlayer), pentru alegerea subtitrarii din afisaj
		self.secondInfoBarScreen.hdsProprietar = self
		self.secondInfoBarScreen.hide()

		self.hideTimer = eTimer()
		self.hideTimer.callback.append(self.doTimerHide)
		self.startHideTimer()

		self.onShow.append(self.__onShow)
		self.onHide.append(self.__onHide)
		# instantiateDialog(SecondInfoBar) de mai sus
		# ruleaza in acest mixin, folosit si de MoviePlayer (Screens/InfoBar.py) -- instantiat DIN
		# NOU la fiecare redare de inregistrare, niciodata sters (lipsea perechea deleteDialog),
		# scurgere reala de memorie la redari succesive. InfoBar-ul principal nu se inchide
		# niciodata (onClose nu ruleaza practic acolo), deci reparatia nu-l afecteaza.
		self.onClose.append(self.__hdsCuratenieSecondInfoBar)

	def __hdsCuratenieSecondInfoBar(self):
		if getattr(self, "secondInfoBarScreen", None) is not None:
			self.session.deleteDialog(self.secondInfoBarScreen)
			self.secondInfoBarScreen = None

	# HDSatelit: a doua bara (pagina tehnica, SecondInfoBar) nu mai are durata. Sta pe ecran pana la
	# OK sau EXIT (tastele ei, Screens/SecondInfoBar.py) sau pana se deschide alt ecran (Session.execEnd ascunde
	# InfoBar, deci si pe ea, prin hide() de mai jos). Cronometrul hideTimer e doar al primei bare.
	def _hdsSecondaVizibila(self):
		return bool(getattr(self, "secondInfoBarScreen", None) and self.secondInfoBarScreen.shown)

	def serviceStarted(self):
		# zap cat se vede a doua bara (tasta 0, web, temporizator, zap automat): ramane deschisa si se reface pentru
		# serviciul nou (convertoarele ei primesc evStart; paginile o iau de la 1). Nu o inchidem: s-ar
		# inchide si la o repornire a aceluiasi serviciu, fara ca utilizatorul sa fi apasat OK sau EXIT. doShow() arata
		# si prima bara numai cand cele doua nu se suprapun pe ecran.
		if self.execing:
			if config.usage.show_infobar_on_zap.value:
				self.doShow()

	def __onShow(self):
		self.__state = self.STATE_SHOWN
		self.startHideTimer()

	def startHideTimer(self):
		if self.__state == self.STATE_SHOWN and not self.__locked:
			# secundele din valoarea aleasa (lista are si 12, 15, 20, 30 s, deci pozitia nu mai e numarul de secunde)
			try:
				secunde = int(config.usage.infobar_timeout.value)
			except (TypeError, ValueError):
				secunde = 8
			if secunde > 0:
				self.hideTimer.start(secunde * 1000, True)

	def __onHide(self):
		self.__state = self.STATE_HIDDEN

	def _hdsBareSuprapuse(self):
		"""True cand prima bara si a doua se acopera pe ecran, dupa ferestrele puse de skinul activ (pozitia si marimea
		lor reale). Fara ferestre sau la o eroare: True (prima bara nu se aseaza peste a doua)."""
		try:
			a = self.instance
			b = self.secondInfoBarScreen.instance
			pa, sa, pb, sb = a.position(), a.size(), b.position(), b.size()
			ax, ay, aw, ah = pa.x(), pa.y(), sa.width(), sa.height()
			bx, by, bw, bh = pb.x(), pb.y(), sb.width(), sb.height()
		except Exception:
			return True
		if min(aw, ah, bw, bh) <= 0:
			return True
		return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

	def doShow(self):
		# aratarile automate ale primei bare (zap, emisiune noua, dupa derulare) nu inchid a doua bara. HDSatelit
		# cand skinul le aseaza fara suprapunere (a doua bara ca fereastra sus), prima bara se arata
		# si ea, cu cronometrul ei (doTimerHide ascunde atunci numai prima bara), ca numele canalului nou sa se vada;
		# cand se suprapun (a doua pe tot ecranul) ramane numai a doua, care se reface singura pentru serviciul nou
		# (capul ei are numarul si numele canalului).
		if self._hdsSecondaVizibila() and self._hdsBareSuprapuse():
			return
		self.show()
		self.startHideTimer()

	def doTimerHide(self):
		self.hideTimer.stop()
		# ascunde doar prima bara; a doua se inchide numai din tastele ei
		if self.__state == self.STATE_SHOWN:
			if self._hdsSecondaVizibila():
				Screen.hide(self)
			else:
				self.hide()

	def hide(self):
		if hasattr(self, "secondInfoBarScreen") and self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
		Screen.hide(self)

	def toggleShow(self):
		if self.__state == self.STATE_SHOWN:
			if hasattr(self, "secondInfoBarScreen") and self.secondInfoBarScreen:
				Screen.hide(self)
				self.__state = self.STATE_HIDDEN
				self.secondInfoBarScreen.show()
				self.hideTimer.stop()  # fara durata: sta pana la OK / EXIT
			else:
				self.hide()
				self.hideTimer.stop()
		elif hasattr(self, "secondInfoBarScreen") and self.secondInfoBarScreen and self.secondInfoBarScreen.shown:
			self.secondInfoBarScreen.hide()
			self.hideTimer.stop()
		elif self.__state == self.STATE_HIDDEN:
			self.show()

	def hdsArataADoua(self):
		"""Arata a doua bara fara prima, ca OK din prima bara. Chemat de a doua bara dupa un ecran deschis din ea
		(temporizator, ghid, meniul emisiunii): Session.execEnd a ascuns bara, iar execBegin arata doar prima."""
		second = getattr(self, "secondInfoBarScreen", None)
		if not self.execing or second is None:
			return False
		Screen.hide(self)
		self.__state = self.STATE_HIDDEN
		if not second.shown:
			second.show()
		self.hideTimer.stop()
		return True

	def lockShow(self):
		self.__locked = self.__locked + 1
		if self.execing:
			self.show()
			self.hideTimer.stop()

	def unlockShow(self):
		self.__locked = self.__locked - 1
		if self.execing:
			self.startHideTimer()

#	def startShow(self):
#		self.instance.m_animation.startMoveAnimation(ePoint(0, 600), ePoint(0, 380), 100)
#		self.__state = self.STATE_SHOWN
#
#	def startHide(self):
#		self.instance.m_animation.startMoveAnimation(ePoint(0, 380), ePoint(0, 600), 100)
#		self.__state = self.STATE_HIDDEN

def _hdsAfisajCifre(cifre):
	"""HDSatelit: afisajul din fata arata cifrele tastate (Components/HdsAfisaj.py); None = fereastra s-a inchis."""
	try:
		from Components import HdsAfisaj
		if cifre is None:
			HdsAfisaj.cifreGata()
		else:
			HdsAfisaj.cifre(cifre)
	except Exception as e:
		print("[NumberZap] afisajul din fata: %r" % (e,))

class NumberZap(Screen):
	def quit(self):
		self.Timer.stop()
		_hdsAfisajCifre(None)
		self.close(0)

	def keyOK(self):
		self.Timer.stop()
		_hdsAfisajCifre(None)
		self.close(int(self["number"].getText()))

	def keyNumberGlobal(self, number):
		self.Timer.start(3000, True)		#reset timer
		self.field = self.field + str(number)
		self["number"].setText(self.field)
		_hdsAfisajCifre(self.field)
		if len(self.field) >= 4:
			self.keyOK()

	def __init__(self, session, number):
		Screen.__init__(self, session)
		self.field = str(number)

		self["channel"] = Label(_("Channel:"))

		self["number"] = Label(self.field)
		_hdsAfisajCifre(self.field)

		self["actions"] = NumberActionMap( [ "SetupActions" ],
			{
				"cancel": self.quit,
				"ok": self.keyOK,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				"0": self.keyNumberGlobal
			})

		self.Timer = eTimer()
		self.Timer.callback.append(self.keyOK)
		self.Timer.start(3000, True)

class InfoBarNumberZap:
	""" Handles an initial number for NumberZapping """
	def __init__(self):
		self["NumberActions"] = NumberActionMap( [ "NumberActions"],
			{
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal,
				"0": self.keyNumberGlobal,
			})

	def keyNumberGlobal(self, number):
#		print "You pressed number " + str(number)
		if number == 0:
			if isinstance(self, InfoBarPiP) and self.pipHandles0Action():
				self.pipDoHandle0Action()
			else:
				self.servicelist.recallPrevService()
		else:
			if "TimeshiftActions" in self and not self.timeshift_enabled:
				self.session.openWithCallback(self.numberEntered, NumberZap, number)

	def numberEntered(self, retval):
#		print self.servicelist
		if retval > 0:
			self.zapToNumber(retval)

	def searchNumberHelper(self, serviceHandler, num, bouquet):
		servicelist = serviceHandler.list(bouquet)
		if not servicelist is None:
			while num:
				serviceIterator = servicelist.getNext()
				if not serviceIterator.valid(): #check end of list
					break
				playable = not (serviceIterator.flags & (eServiceReference.isMarker|eServiceReference.isDirectory))
				if playable:
					num -= 1;
			if not num: #found service with searched number ?
				return serviceIterator, 0
		return None, num

	def hdsZapLaNumarRetea(self, number):
		"""HDSatelit: cand lista de acum e lista unei retele (cablul operatorului, in ordinea numerelor lui,
		Components/HdsRetele.py), cifrele duc la canalul cu acel numar al operatorului (23 = TVR 1), ca pe receptorul
		operatorului; un numar pe care reteaua nu il are nu porneste nimic. -> True daca numarul s-a tratat aici."""
		sl = self.servicelist
		if getattr(sl, "hdsReteaRadacinii", None) is None:
			return False
		try:
			root = sl.getRoot()
			if root is None:
				# dupa pornire lista nu e inca umpluta: locul tinut minte, daca e lista unei retele
				capat = [x for x in (sl.lastroot.value or "").split(";") if x][-1:]
				if not capat or sl.hdsReteaRadacinii(eServiceReference(capat[0])) is None:
					return False
				sl.restoreRoot()
				root = sl.getRoot()
			# fisierul retelelor schimbat de la umplerea listei (o scanare, un fisier pus de mana): numerele de acum
			laZi = getattr(sl, "hdsReteaLaZi", None)
			if root is not None and laZi is not None:
				laZi()
				root = sl.getRoot()
			if root is None or sl.hdsReteaRadacinii(root) is None:
				return False
			ref = sl.hdsNumarInRetea(number)
		except Exception as e:
			print("[NumberZap] numarul operatorului: %r" % (e,))
			return False
		if ref is not None:
			sl.setCurrentSelection(ref)
			sl.zap()
		return True

	def zapToNumber(self, number):
		if self.hdsZapLaNumarRetea(number):
			return
		bouquet = self.servicelist.bouquet_root
		service = None
		serviceHandler = eServiceCenter.getInstance()
		if not config.usage.multibouquet.value:
			service, number = self.searchNumberHelper(serviceHandler, number, bouquet)
		else:
			bouquetlist = serviceHandler.list(bouquet)
			if not bouquetlist is None:
				while number:
					bouquet = bouquetlist.getNext()
					if not bouquet.valid(): #check end of list
						break
					if bouquet.flags & eServiceReference.isDirectory:
						service, number = self.searchNumberHelper(serviceHandler, number, bouquet)
		if not service is None:
			# HDSatelit: dupa pornirea pe ultimul canal lista
			# n-are radacina pana la prima deschidere (hds_startup_suprimat), iar comparatia cu None arunca ValueError in
			# SWIG: o cifra apasata atunci oprea enigma2 (bsodFatal). Proba: teste/test_info_scurt.py.
			root = self.servicelist.getRoot()
			if root is None or root != bouquet: #already in correct bouquet?
				self.servicelist.clearPath()
				if self.servicelist.bouquet_root != bouquet:
					self.servicelist.enterPath(self.servicelist.bouquet_root)
				self.servicelist.enterPath(bouquet)
			self.servicelist.setCurrentSelection(service) #select the service in servicelist
			self.servicelist.zap()

config.misc.initialchannelselection = ConfigBoolean(default = True)

# HDSatelit: gasit un bug real -- config.tv.lastservice.value SE SALVEAZA la
# fiecare zap (ChannelSelection.saveChannel), dar NIMIC nu il citea inapoi la pornire. Codul
# de mai jos (firstRun) doar deschide lista de canale, o singura data, DOAR daca lastservice
# e gol (prima pornire vreodata) -- la a doua pornire in sus, nu se intampla nimic deloc, de
# aici ecranul negru raportat la testare. Adaugat startupService(), apelat mereu (nu doar la
# prima pornire), care reacordeaza pe lastservice sau pe optiunea aleasa mai jos.
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: modulul se incarca inaintea limbii alese,
	deci textele alegerilor raman msgid-uri si ConfigSelection le traduce la afisare (getText, getMulti)."""
	return text


config.usage.hds_pornire = ConfigSelection(default="last", choices=[
	("last", N_("Ultimul canal urmărit")),
	("allsat", N_("Lista tuturor sateliților (include și Cablu/Terestru)")),
	("favorite", N_("Favorite")),
	("radio", N_("Radio")),
	("toate", N_("Toate canalele")),
])


class InfoBarChannelSelection:
	""" ChannelSelection - handles the channelSelection dialog and the initial
	channelChange actions which open the channelSelection dialog """
	def __init__(self):
		# HDSatelit: canalul din fisierul mic al canalului tinut minte, cand e mai nou decat settings (o oprire fara
		# iesire curata dupa ce canalul a stat un minut pe ecran), inainte ca lista sa fie facuta si inainte de primul
		# zap (Components/HdsCanalTinut.py)
		try:
			from Components.HdsCanalTinut import la_pornire
			la_pornire()
		except Exception as e:
			print("[InfoBar] HdsCanalTinut: %r" % (e,))
		#instantiate forever
		self.servicelist = self.session.instantiateDialog(ChannelSelection)

		# ecranul negru la pornire:
		# ChannelSelection are propriul mecanism intern (lastChannelRootTimer,
		# 100ms dupa creare -> __onCreate() -> zap() pe config.tv.lastservice), COMPLET independent de
		# startupService() de mai jos. Cele doua se bateau cap in cap: la hds_pornire != "last"
		# (ex. Favorite/Radio/Toate), 100ms mai tarziu acordarea era oricum trasa spre lastservice,
		# ignorand tacut alegerea utilizatorului; la hds_pornire == "last", ambele porneau acelasi
		# playService() aproape simultan (evStart dublu, vezi si bug-ul contorului din
		# InfoBarServiceErrorPopupSupport mai jos). O singura sursa de adevar: HDSatelit e sursa
		# (startupService() de mai jos, cu lantul de rezerva); mecanismul intern se suprima.
		self.servicelist.hds_startup_suprimat = True

		# HDSatelit: BUG REAL, introdus odata cu startupService() de
		# mai jos -- inregistrarea ActionMap ("ChannelSelectActions", tastele Up/Down/zapUp/
		# zapDown/openServiceList) ajunsese, din greseala, in INTERIORUL lui startupService(),
		# deci se inregistra DOAR cand acea metoda chiar rula. La prima pornire vreodata
		# (config.tv.lastservice gol), se ia ramura firstRun() de mai jos, startupService() nu
		# ruleaza niciodata, deci tastele de schimbare canal nu erau legate DELOC -- exact
		# starea "ecran fara serviciu activ, nimic nu raspunde" raportata la testare. Mutat
		# inapoi necondiționat in __init__, unde era inainte sa fie introdus bug-ul.
		self["ChannelSelectActions"] = HelpableActionMap(self, "InfobarChannelSelection",
			{
				"switchChannelUp": (self.switchChannelUp, _("open servicelist(up)")),
				"switchChannelDown": (self.switchChannelDown, _("open servicelist(down)")),
				"zapUp": (self.zapUp, _("previous channel")),
				"zapDown": (self.zapDown, _("next channel")),
				"historyBack": (self.historyBack, _("previous channel in history")),
				"historyNext": (self.historyNext, _("next channel in history")),
				"openServiceList": (self.openServiceList, _("open servicelist")),
			})
		# HDSatelit: ajutorul (HELP) spune ce deschide sageata sus, dupa setare
		try:
			config.usage.hds_sageata_sus.addNotifier(self._hdsAjutorSageata, initial_call=True, immediate_feedback=False)
		except Exception as e:
			print("[InfoBar] sageata sus:", e)

		if config.misc.initialchannelselection.value and not config.tv.lastservice.value:
			print('[InfoBar] pornire: config.tv.lastservice gol -> firstRun (deschide lista, fara auto-play)')
			self.onShown.append(self.firstRun)
		else:
			# Nu e prima pornire -- fara asta ramanea ecran negru la orice pornire ulterioara.
			print('[InfoBar] pornire: config.tv.lastservice=%r -> startupService' % config.tv.lastservice.value)
			self.onShown.append(self.startupService)

	def hdsPornesteInainteaNotificarii(self):
		"""Chemata de InfoBarNotifications.checkNotifications chiar inainte sa deschida o notificare peste bara. La
		pornire, startupService asteapta in onShown, iar bara nu se arata cat notificarea („Ce e nou” dupa o
		actualizare) e deschisa peste ea: canalul pornea abia la inchiderea ei.
		Aici pornirea se face acum, in spatele notificarii, numai cand ar reda direct ultimul canal (alegerea „Ultimul
		canal urmărit”, cu un canal care exista): celelalte alegeri deschid lista de canale, care nu trebuie sa
		acopere notificarea, deci raman la onShown, ca inainte. Fara notificari nu se schimba nimic."""
		if self.startupService not in self.onShown:
			return False
		if (config.usage.hds_pornire.value or "last") != "last":
			return False
		ref_text = config.tv.lastservice.value
		if not ref_text:
			return False
		ref = eServiceReference(ref_text)
		if not ref.valid() or not self._hdsServiciulExista(ref):
			return False
		print("[InfoBar] pornire: notificare la pornire -> canalul porneste in spatele ei")
		self.startupService()
		return True

	def _hdsServiciulExista(self, ref):
		# ref.valid() verifica doar ca stringul se
		# parseaza corect ca eServiceReference, NU ca serviciul chiar mai exista in lamedb/
		# bouquet-urile curente (ex. dupa o rescanare care a sters transponderul respectiv).
		# Cerere statica de informatii (fara acordare): un serviciu disparut nu are nume real.
		try:
			info = eServiceCenter.getInstance().info(ref)
			if info is None:
				return False
			name = info.getName(ref)
			return bool(name) and name != ref.toString()
		except Exception:
			return False

	def _hdsListaAreContinut(self):
		# CORECTIE -- prima presupunere (ref.valid() pe
		# getCurrentSelection()) tot gresita, confirmat cu un al doilea test real cu captura: pe o
		# lista goala, "current selection" e insasi referinta bouquet-ului/radacinii (un marcaj de
		# director, care e "valid()" ca referinta chiar daca nu are NICIUN canal inauntru) -- deci tot
		# ramanea pe Favorite goale. Solutia corecta, gasita citind Components/ServiceList.py:
		# getRootServices() (linia ~179) chiar ENUMERA continutul radacinii curente prin
		# eServiceCenter.list()+getNext() (acelasi API folosit peste tot in acest fisier pentru liste
		# de bouquet-uri) si intoarce o lista Python goala daca radacina n-are nimic -- fara ambiguitate
		# de tip "marcaj vs canal real". self.servicelist e ecranul ChannelSelection; widget-ul
		# ServiceList propriu-zis e self.servicelist.servicelist (vezi ChannelSelectionBase.__init__).
		try:
			return bool(self.servicelist.servicelist.getRootServices())
		except Exception:
			return False

	def startupService(self):
		# apelata fie automat din onShown (pornire normala), fie direct din firstRun() (prima
		# pornire vreodata) -- in al doilea caz nu era adaugata in onShown, deci remove() ar
		# arunca ValueError daca n-am verifica intai ca e chiar acolo.
		if self.startupService in self.onShown:
			self.onShown.remove(self.startupService)
		print('[InfoBar] startupService: alegere=%r lastservice=%r' % (config.usage.hds_pornire.value, config.tv.lastservice.value))
		alegere = config.usage.hds_pornire.value
		if not alegere:
			alegere = "last"

		# ecran gol la pornire pe Favorite fara canale adaugate:
		# daca optiunea aleasa (implicita sau setata de utilizator) duce
		# la o lista goala SAU la un canal disparut din lamedb, nu se mai ramane pe ecran negru --
		# se trece la urmatoarea optiune din lant, pana una chiar are continut. Lantul incepe cu
		# optiunea aleasa, apoi restul, in ordinea din meniul de Setari (fara repetare).
		self._hdsLantPornire = [alegere] + [o for o in ("last", "allsat", "toate", "favorite", "radio") if o != alegere]
		self._hdsIncercarePornire(0)

	def _hdsIncercarePornire(self, index):
		lant = self._hdsLantPornire
		if index >= len(lant):
			# gasit pe o captura reala si confirmat prin
			# emulator cu lamedb chiar gol: lant epuizat -> setModeTv() singur, fara niciun showXxx()
			# explicit dupa el, cade pe radacina implicita din config.tv.lastroot (Favorite) prin
			# restoreRoot() -- exact ecranul "Selectare canal (TV) Favorite" gol din captura, cu titlul
			# identic, confirmat linie cu linie in jurnal). Asta inseamna ca receptorul chiar n-are NICIUN
			# canal scanat nicaieri (nu doar in Favorite) -- mesajul corect nu e "lipsa semnal", ci
			# instiintarea clara de mai jos, nu un ecran gol nemotivat.
			# bug gasit la testarea live a mesajului: session.open(MessageBox, ...) urmat
			# imediat de execDialog(self.servicelist) lasa mesajul ACOPERIT de ecranul de canale (ambele
			# sunt dialoguri pe tot ecranul, cel din urma aratat il acopera pe primul) -- verificat cu
			# captura reala la 5s si la 8s, mesajul nu se vede deloc. Solutia: canalele se arata abia
			# DUPA ce mesajul se inchide (callback), nu concurent.
			print('[InfoBar] startupService: lant epuizat, niciun canal nicaieri -- mesaj catre utilizator')
			self.servicelist.setModeTv()
			self.session.openWithCallback(lambda *a: self.session.execDialog(self.servicelist),
				MessageBox, _("Niciun canal găsit. Mergi la Scanare canale din Meniu."), MessageBox.TYPE_INFO, timeout=10)
			return
		incercare = lant[index]
		if incercare == "last":
			ref_text = config.tv.lastservice.value
			if ref_text:
				ref = eServiceReference(ref_text)
				if ref.valid() and self._hdsServiciulExista(ref):
					self.session.nav.playService(ref)
					return
			self._hdsIncercarePornire(index + 1)  # lastservice gol/invalid/disparut -- urmatoarea
			return
		elif incercare == "allsat":
			self.servicelist.setModeTv()
			self.servicelist.showSatellites()
		elif incercare == "favorite":
			self.servicelist.setModeTv()
			self.servicelist.showFavourites()
		elif incercare == "radio":
			self.servicelist.setModeRadio()
		elif incercare == "toate":
			self.servicelist.setModeTv()
			self.servicelist.showAllServices()
		else:
			self._hdsIncercarePornire(index + 1)
			return
		# CORECTIE (gasita cu teste reale, cu captura): verificarea imediata, sincrona,
		# a continutului (chiar dupa showXxx()) da rezultate corecte pentru datele brute (getRoot/
		# getRootServices citesc corect noua radacina), DAR ecranul CHIAR afisat (titlul, lista
		# vizuala) ramanea, la teste, pe starea VECHE cand doua showXxx() rulau una dupa alta fara
		# nicio pauza -- Enigma2 pare sa aiba nevoie de o tura de bucla principala ca sa desks
		# schimbarea de radacina pana la widget-ul GUI. Un timer scurt (50ms), acelasi tipar deja
		# folosit in acest cod (lastChannelRootTimer, 100ms), rezolva -- verificat direct: cu el,
		# lantul chiar trece de pe Favorite goale pe urmatoarea optiune cu continut real.
		t = eTimer()
		self._hdsTimerPornire = t  # pastrat pe self, altfel garbage-collector-ul l-ar putea sterge
		t.callback.append(boundFunction(self._hdsVerificaSiContinuaPornire, index))
		t.start(50, True)

	def _hdsVerificaSiContinuaPornire(self, index):
		are = self._hdsListaAreContinut()
		print('[InfoBar] startupService: incercare=%r are_continut=%r' % (self._hdsLantPornire[index], are))
		if are:
			self.session.execDialog(self.servicelist)
			return
		self._hdsIncercarePornire(index + 1)

	def showTvChannelList(self, zap=False):
		self.servicelist.setModeTv()
		if zap:
			self.servicelist.zap()
		self.session.execDialog(self.servicelist)

	def showRadioChannelList(self, zap=False):
		self.servicelist.setModeRadio()
		if zap:
			self.servicelist.zap()
		self.session.execDialog(self.servicelist)

	def firstRun(self):
		self.onShown.remove(self.firstRun)
		config.misc.initialchannelselection.value = False
		config.misc.initialchannelselection.save()
		# HDSatelit: inainte deschidea direct lista de canale (switchChannelDown),
		# indiferent de optiunea aleasa de utilizator in "What to show at startup" -- pe o lista
		# complet goala (niciun canal scanat inca, cazul obisnuit la o pornire chiar prima data)
		# asta arata identic cu un ecran gol/negru. Acum foloseste aceeasi logica din
		# startupService() (Favorite/Sateliti/Radio/Toate cand sunt alese), consecvent cu orice
		# pornire ulterioara -- "last" nu are ce reface (nu exista inca niciun lastservice la
		# prima pornire), ramane pe deschiderea listei, ca pana acum.
		self.startupService()

	def historyBack(self):
		self.servicelist.historyBack()

	def historyNext(self):
		self.servicelist.historyNext()

	def _hdsPeRadio(self):
		# lista comuna in modul radio (MODE_RADIO, „Alternative radio mode”)
		return getattr(self.servicelist, "mode", 0) == 1

	def _hdsAjutorSageata(self, element=None):
		from Components.HdsSageti import sageata
		texte = {"radio": _("Lista de canale radio"), "tv": _("Lista de canale TV")}
		sus = texte.get(sageata(True)) or _("next channel")
		jos = texte.get(sageata(False)) or _("previous channel")
		harta = self.get("ChannelSelectActions") if hasattr(self, "get") else None
		for (h, context, actiuni) in getattr(self, "helpList", []):
			if h is harta:
				for i, (actiune, _vechi) in enumerate(actiuni):
					if actiune == "switchChannelUp":
						actiuni[i] = (actiune, sus)
					elif actiune == "switchChannelDown":
						actiuni[i] = (actiune, jos)

	def _hdsSageata(self, sus):
		"""HDSatelit: sagetile SUS si JOS la privit, dupa setarea "Săgețile sus și jos la privit" (Components/HdsSageti.py).
		Lista radio de pe TV: numai lista, cu cursorul pe ultimul post de radio; canalul TV merge pana se alege un post
		(spre deosebire de tasta RADIO, care porneste radioul). Lista TV de pe radio: ca tasta TV. Lista in care esti
		deja: lista de acum, cu un rand mai sus sau mai jos. "Schimbă canalul": SUS canalul urmator, JOS cel anterior."""
		from Components.HdsSageti import sageata
		fel = sageata(sus)
		if fel == "zap":
			if sus:
				self.zapDown()
			else:
				self.zapUp()
			return
		peRadio = self._hdsPeRadio()
		if fel == "radio" and not peRadio and getattr(self, "showRadio", None) is not None:
			self.showRadio(faraPornire=True)
			return
		if fel == "tv" and peRadio and getattr(self, "showTv", None) is not None:
			self.showTv()
			return
		if sus:
			self.servicelist.moveUp()
		else:
			self.servicelist.moveDown()
		self.session.execDialog(self.servicelist)

	def switchChannelUp(self):
		self._hdsSageata(True)

	def switchChannelDown(self):
		self._hdsSageata(False)

	def openServiceList(self):
		self.session.execDialog(self.servicelist)

	def zapUp(self):
		if self.servicelist.inBouquet():
			prev = self.servicelist.getCurrentSelection()
			if prev:
				prev = prev.toString()
				while True:
					if config.usage.quickzap_bouquet_change.value:
						if self.servicelist.atBegin():
							self.servicelist.prevBouquet()
					self.servicelist.moveUp()
					cur = self.servicelist.getCurrentSelection()
					if not cur or (not (cur.flags & 64)) or cur.toString() == prev:
						break
		else:
			self.servicelist.moveUp()
		self.servicelist.zap()

	def zapDown(self):
		if self.servicelist.inBouquet():
			prev = self.servicelist.getCurrentSelection()
			if prev:
				prev = prev.toString()
				while True:
					if config.usage.quickzap_bouquet_change.value and self.servicelist.atEnd():
						self.servicelist.nextBouquet()
					else:
						self.servicelist.moveDown()
					cur = self.servicelist.getCurrentSelection()
					if not cur or (not (cur.flags & 64)) or cur.toString() == prev:
						break
		else:
			self.servicelist.moveDown()
		self.servicelist.zap()

class InfoBarMenu:
	""" Handles a menu action, to open the (main) menu """
	def __init__(self):
		self["MenuActions"] = HelpableActionMap(self, "InfobarMenuActions",
			{
				"mainMenu": (self.mainMenu, _("Enter main menu...")),
			})
		self.session.infobar = None

	def mainMenu(self):
		print("loading mainmenu XML...")
		menu = mdom.getroot()
		if menu.tag == "menuxml":
			# test de adevar direct pe un element XML
			# (ElementTree) in loc de "is not None" -- un Element gasit dar fara copii e FALS la
			# "or" (avertisment Python 3.12+, __bool__ pe Element e deprecat), deci lantul "or" putea
			# sari peste un meniu gasit-dar-gol si alege gresit alternativa urmatoare.
			gasit = menu.find(".//menu[@key='mainmenu']")
			if gasit is None:
				gasit = menu.find("./menu")
			if gasit is None:
				gasit = menu[0]
			menu = gasit
		assert menu.tag == "menu", "root element in menu must be 'menu'!"

		self.session.infobar = self
		# so we can access the currently active infobar from screens opened from within the mainmenu
		# at the moment used from the SubserviceSelection

		self.session.openWithCallback(self.mainMenuClosed, MainMenu, menu)

	def mainMenuClosed(self, *val):
		self.session.infobar = None

class InfoBarSimpleEventView:
	""" Opens the Eventview for now/next """
	def __init__(self):
		self["EPGActions"] = HelpableActionMap(self, "InfobarEPGActions",
			{
				"showEventInfo": (self.openEventView, _("show event details")),
				"showInfobarOrEpgWhenInfobarAlreadyVisible": self.showEventInfoWhenNotVisible,
			})

	def showEventInfoWhenNotVisible(self):
		if self.shown:
			self.openEventView()
		else:
			self.toggleShow()
			return 1

	def openEventView(self):
		epglist = [ ]
		self.epglist = epglist
		service = self.session.nav.getCurrentService()
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		# "service.info()" fara garda ca
		# service nu e None -- crash daca se apasa Info fara niciun serviciu curent redat. Aceeasi
		# garda ca la getNowNext() (linia 736 din acest fisier).
		info = service and service.info()
		ptr = info and info.getEvent(0)
		if ptr:
			epglist.append(ptr)
		ptr = info and info.getEvent(1)
		if ptr:
			epglist.append(ptr)
		if epglist:
			self.session.open(EventViewSimple, epglist[0], ServiceReference(ref), self.eventViewCallback)

	def eventViewCallback(self, setEvent, setService, val): #used for now/next displaying
		epglist = self.epglist
		if len(epglist) > 1:
			tmp = epglist[0]
			epglist[0] = epglist[1]
			epglist[1] = tmp
			setEvent(epglist[0])

class SimpleServicelist:
	def __init__(self, services):
		self.services = services
		self.length = len(services)
		self.current = 0

	def selectService(self, service):
		if not self.length:
			self.current = -1
			return False
		else:
			self.current = 0
			while self.services[self.current].ref != service:
				self.current += 1
				if self.current >= self.length:
					return False
		return True

	def nextService(self):
		if not self.length:
			return
		if self.current+1 < self.length:
			self.current += 1
		else:
			self.current = 0

	def prevService(self):
		if not self.length:
			return
		if self.current-1 > -1:
			self.current -= 1
		else:
			self.current = self.length - 1

	def currentService(self):
		if not self.length or self.current >= self.length:
			return None
		return self.services[self.current]

class InfoBarEPG:
	""" EPG - Opens an EPG list when the showEPGList action fires """
	def __init__(self):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.__evEventInfoChanged,
			})

		self.is_now_next = False
		self.dlg_stack = [ ]
		self.bouquetSel = None
		self.eventView = None
		self["EPGActions"] = HelpableActionMap(self, "InfobarEPGActions",
			{
				"showEventInfo": (self.openEventView, _("show EPG...")),
				"showEventInfoPlugin": (self.showEventInfoPlugins, _("list of EPG views...")),
				"showInfobarOrEpgWhenInfobarAlreadyVisible": self.showEventInfoWhenNotVisible,
			})

	def showEventInfoWhenNotVisible(self):
		if self.shown:
			self.openEventView()
		else:
			self.toggleShow()
			return 1

	def zapToService(self, service):
		if not service is None:
			# HDSatelit: ghidul deschis de INFO scurt imediat
			# dupa pornire vine cu radacina listei None; comparatia cu None arunca ValueError in SWIG („invalid null
			# reference in method 'eServiceReference___ne__'”), deci rosu („Zap”) oprea enigma2 (bsodFatal). La fel din
			# ghidul deschis de Multi EPG (EventView) si din alegerea buchetului. Proba: teste/test_info_scurt.py.
			root = self.servicelist.getRoot()
			if root is None or root != self.epg_bouquet: #already in correct bouquet?
				self.servicelist.clearPath()
				if self.servicelist.bouquet_root != self.epg_bouquet:
					self.servicelist.enterPath(self.servicelist.bouquet_root)
				self.servicelist.enterPath(self.epg_bouquet)
			self.servicelist.setCurrentSelection(service) #select the service in servicelist
			self.servicelist.zap()

	def getBouquetServices(self, bouquet):
		services = [ ]
		servicelist = eServiceCenter.getInstance().list(bouquet)
		if not servicelist is None:
			while True:
				service = servicelist.getNext()
				if not service.valid(): #check if end of list
					break
				if service.flags & (eServiceReference.isDirectory | eServiceReference.isMarker): #ignore non playable services
					continue
				services.append(ServiceReference(service))
		return services

	def openBouquetEPG(self, bouquet, withCallback=True, services=None):
		# HDSatelit: intoarce True cand s-a deschis ghidul (openMultiServiceEPGSilent trece altfel pe ghidul
		# canalului); services = canalele citite deja, ca o lista mare sa nu se parcurga de doua ori
		if services is None:
			services = self.getBouquetServices(bouquet)
		if services:
			self.epg_bouquet = bouquet
			if withCallback:
				self.dlg_stack.append(self.session.openWithCallback(self.closed, EPGSelection, services, self.zapToService, None, self.changeBouquetCB))
			else:
				self.session.open(EPGSelection, services, self.zapToService, None, self.changeBouquetCB)
			return True
		return False

	def changeBouquetCB(self, direction, epg):
		if self.bouquetSel:
			if direction > 0:
				self.bouquetSel.down()
			else:
				self.bouquetSel.up()
			bouquet = self.bouquetSel.getCurrent()
			services = self.getBouquetServices(bouquet)
			if services:
				self.epg_bouquet = bouquet
				epg.setServices(services)

	def closed(self, ret=False):
		closedScreen = self.dlg_stack.pop()
		if self.bouquetSel and closedScreen == self.bouquetSel:
			self.bouquetSel = None
		elif self.eventView and closedScreen == self.eventView:
			self.eventView = None
			# is_now_next nu se reseta aici -- ramanea True
			# dupa ce ecranul se inchidea, iar urmatoarea schimbare de eveniment (__evEventInfoChanged)
			# facea "assert self.eventView" pe None -> AssertionError la orice schimbare de emisiune
			# dupa ce ai inchis un ecran now/next.
			self.is_now_next = False
		if ret:
			dlgs=len(self.dlg_stack)
			if dlgs > 0:
				self.dlg_stack[dlgs-1].close(dlgs > 1)

	def openMultiServiceEPG(self, withCallback=True):
		bouquets = self.servicelist.getBouquetList()
		if bouquets is None:
			cnt = 0
		else:
			cnt = len(bouquets)
		if config.usage.multiepg_ask_bouquet.value:
			self.openMultiServiceEPGAskBouquet(bouquets, cnt, withCallback)
		else:
			self.openMultiServiceEPGSilent(bouquets, cnt, withCallback)

	def openMultiServiceEPGAskBouquet(self, bouquets, cnt, withCallback):
		if cnt > 1: # show bouquet list
			if withCallback:
				self.bouquetSel = self.session.openWithCallback(self.closed, BouquetSelector, bouquets, self.openBouquetEPG, enableWrapAround=True)
				self.dlg_stack.append(self.bouquetSel)
			else:
				self.bouquetSel = self.session.open(BouquetSelector, bouquets, self.openBouquetEPG, enableWrapAround=True)
		elif cnt == 1:
			self.openBouquetEPG(bouquets[0][1], withCallback)

	def openMultiServiceEPGSilent(self, bouquets, cnt, withCallback):
		# bouquets poate fi None (vezi openMultiServiceEPG,
		# cnt=0 dar bouquets ramane None) -- "for bouquet in bouquets" crapa cu TypeError, exact la
		# apasarea Info cand canalul curent n-are EPG (ramura implicita a fluxului).
		bouquets = bouquets or []
		root = self.servicelist.getRoot()
		services = self.getBouquetServices(root) if root is not None else []
		if not services:
			# HDSatelit: dupa pornirea pe ultimul
			# canal lista de canale n-are radacina pana la prima deschidere (hds_startup_suprimat, mai sus), iar
			# root.toCompareString() pe None oprea enigma2 (orice exceptie dintr-o tasta ajunge la bsodFatal:
			# lib/python/python.cpp, main/bsod.cpp). O radacina fara canale („Sateliți”, pusa de lista dupa flash, lista
			# buchetelor dupa FAV, furnizorii) nu deschidea nimic. Acum, in ambele cazuri: buchetul in care e canalul care
			# merge; daca nu e in niciun buchet, ghidul canalului. Proba: teste/test_info_scurt.py.
			root = self.hdsBuchetulCanalului(bouquets)
			if root is None:
				self.openSingleServiceEPG()
				return
			services = None
		rootstr = root.toCompareString()
		current = 0
		for bouquet in bouquets:
			if bouquet[1].toCompareString() == rootstr:
				break
			current += 1
		if current >= cnt:
			current = 0
		if cnt > 1: # create bouquet list for bouq+/-
			# HDSatelit: pozitia buchetului in lista (current), nu numarul primului lui canal
			# (getBouquetNumOffset), care facea ca Buchet+/- din ghid sa porneasca de la alt buchet
			self.bouquetSel = SilentBouquetSelector(bouquets, True, current)
		# HDSatelit: si fara lista de buchete (cnt 0) se deschide ghidul listei; daca tot nu s-a deschis
		# nimic, ghidul canalului: INFO scurt pe un canal fara EPG deschide mereu un ghid
		if not self.openBouquetEPG(root, withCallback, services):
			self.bouquetSel = None
			self.openSingleServiceEPG()

	def hdsBuchetulCanalului(self, bouquets):
		"""buchetul (din lista buchetelor) in care e canalul care merge, sau None"""
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is None:
			return None
		refstr = ref.toCompareString()
		for bouquet in bouquets:
			for service in self.getBouquetServices(bouquet[1]):
				if service.ref.toCompareString() == refstr:
					return bouquet[1]
		return None

	def changeServiceCB(self, direction, epg):
		if self.serviceSel:
			if direction > 0:
				self.serviceSel.nextService()
			else:
				self.serviceSel.prevService()
			epg.setService(self.serviceSel.currentService())

	def SingleServiceEPGClosed(self, ret=False):
		self.serviceSel = None

	def openSingleServiceEPG(self):
		ref=self.session.nav.getCurrentlyPlayingServiceReference()
		if ref:
			if self.servicelist.getMutableList() is not None: # bouquet in channellist
				current_path = self.servicelist.getRoot()
				services = self.getBouquetServices(current_path)
				self.serviceSel = SimpleServicelist(services)
				if self.serviceSel.selectService(ref):
					self.session.openWithCallback(self.SingleServiceEPGClosed, EPGSelection, ref, serviceChangeCB = self.changeServiceCB)
				else:
					self.session.openWithCallback(self.SingleServiceEPGClosed, EPGSelection, ref)
			else:
				self.session.open(EPGSelection, ref)

	def showEventInfoPlugins(self):
		list = [(p.name, boundFunction(self.runPlugin, p)) for p in plugins.getPlugins(where = PluginDescriptor.WHERE_EVENTINFO)]

		if list:
			list.append((_("show single service EPG..."), self.openSingleServiceEPG))
			list.append((_("Multi EPG"), self.openMultiServiceEPG))
			self.session.openWithCallback(self.EventInfoPluginChosen, ChoiceBox, title=_("Please choose an extension..."), list = list, skin_name = "EPGExtensionsList")
		else:
			self.openSingleServiceEPG()

	def runPlugin(self, plugin):
		plugin(session = self.session, servicelist = self.servicelist)
		
	def EventInfoPluginChosen(self, answer):
		if answer is not None:
			answer[1]()

	def openSimilarList(self, eventid, refstr):
		self.session.open(EPGSelection, refstr, None, eventid)

	def getNowNext(self):
		epglist = [ ]
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		ptr = info and info.getEvent(0)
		if ptr:
			epglist.append(ptr)
		ptr = info and info.getEvent(1)
		if ptr:
			epglist.append(ptr)
		self.epglist = epglist

	def __evEventInfoChanged(self):
		if self.is_now_next and len(self.dlg_stack) == 1:
			self.getNowNext()
			assert self.eventView
			if self.epglist:
				self.eventView.setEvent(self.epglist[0])

	def openEventView(self):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		self.getNowNext()
		epglist = self.epglist
		if not epglist:
			self.is_now_next = False
			epg = eEPGCache.getInstance()
			ptr = ref and ref.valid() and epg.lookupEventTime(ref, -1)
			if ptr:
				epglist.append(ptr)
				ptr = epg.lookupEventTime(ref, ptr.getBeginTime(), +1)
				if ptr:
					epglist.append(ptr)
		else:
			self.is_now_next = True
		if epglist:
			self.eventView = self.session.openWithCallback(self.closed, EventViewEPGSelect, self.epglist[0], ServiceReference(ref), self.eventViewCallback, self.openSingleServiceEPG, self.openMultiServiceEPG, self.openSimilarList)
			self.dlg_stack.append(self.eventView)
		else:
			print("no epg for the service avail.. so we show multiepg instead of eventinfo")
			self.openMultiServiceEPG(False)

	def eventViewCallback(self, setEvent, setService, val): #used for now/next displaying
		epglist = self.epglist
		if len(epglist) > 1:
			tmp = epglist[0]
			epglist[0]=epglist[1]
			epglist[1]=tmp
			setEvent(epglist[0])

class InfoBarRdsDecoder:
	"""provides RDS and Rass support/display"""
	def __init__(self):
		self.rds_display = self.session.instantiateDialog(RdsInfoDisplay)
		self.rass_interactive = None

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evEnd: self.__serviceStopped,
				iPlayableService.evUpdatedRassSlidePic: self.RassSlidePicChanged
			})

		self["RdsActions"] = ActionMap(["InfobarRdsActions"],
		{
			"startRassInteractive": self.startRassInteractive
		},-1)

		self["RdsActions"].setEnabled(False)

		self.onLayoutFinish.append(self.rds_display.show)
		self.rds_display.onRassInteractivePossibilityChanged.append(self.RassInteractivePossibilityChanged)

	def RassInteractivePossibilityChanged(self, state):
		self["RdsActions"].setEnabled(state)

	def RassSlidePicChanged(self):
		if not self.rass_interactive:
			service = self.session.nav.getCurrentService()
			decoder = service and service.rdsDecoder()
			if decoder:
				decoder.showRassSlidePicture()

	def __serviceStopped(self):
		if self.rass_interactive is not None:
			rass_interactive = self.rass_interactive
			self.rass_interactive = None
			rass_interactive.close()

	def startRassInteractive(self):
		self.rds_display.hide()
		self.rass_interactive = self.session.openWithCallback(self.RassInteractiveClosed, RassInteractive)

	def RassInteractiveClosed(self, *val):
		if self.rass_interactive is not None:
			self.rass_interactive = None
			self.RassSlidePicChanged()
		self.rds_display.show()

class InfoBarSeek:
	"""handles actions like seeking, pause"""

	SEEK_STATE_PLAY = (0, 0, 0, ">")
	SEEK_STATE_PAUSE = (1, 0, 0, "||")
	SEEK_STATE_EOF = (1, 0, 0, "END")

	def __init__(self, actionmap = "InfobarSeekActions"):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged,
				iPlayableService.evStart: self.__serviceStarted,

				iPlayableService.evEOF: self.__evEOF,
				iPlayableService.evSOF: self.__evSOF,
			})
		self.fast_winding_hint_message_showed = False

		class InfoBarSeekActionMap(HelpableActionMap):
			def __init__(self, screen, *args, **kwargs):
				HelpableActionMap.__init__(self, screen, *args, **kwargs)
				self.screen = screen

			def action(self, contexts, action):
				print("action:", action)
				if action[:5] == "seek:":
					time = int(action[5:])
					self.screen.doSeekRelative(time * 90000)
					return 1
				elif action[:8] == "seekdef:":
					key = int(action[8:])
					time = (-config.seek.selfdefined_13.value, False, config.seek.selfdefined_13.value,
						-config.seek.selfdefined_46.value, False, config.seek.selfdefined_46.value,
						-config.seek.selfdefined_79.value, False, config.seek.selfdefined_79.value)[key-1]
					self.screen.doSeekRelative(time * 90000)
					return 1					
				else:
					return HelpableActionMap.action(self, contexts, action)

		self["SeekActions"] = InfoBarSeekActionMap(self, actionmap,
			{
				"playpauseService": self.playpauseService,
				"pauseService": (self.pauseService, _("pause")),
				"unPauseService": (self.unPauseService, _("continue")),

				"seekFwd": (self.seekFwd, _("skip forward")),
				"seekFwdManual": (self.seekFwdManual, _("skip forward (enter time)")),
				"seekBack": (self.seekBack, _("skip backward")),
				"seekBackManual": (self.seekBackManual, _("skip backward (enter time)"))
			}, prio=-1)
			# give them a little more priority to win over color buttons

		self["SeekActions"].setEnabled(False)

		self.seekstate = self.SEEK_STATE_PLAY
		self.lastseekstate = self.SEEK_STATE_PLAY

		self.onPlayStateChanged = [ ]

		self.lockedBecauseOfSkipping = False

		self.__seekableStatusChanged()

	def makeStateForward(self, n):
		return (0, n, 0, ">> %dx" % n)

	def makeStateBackward(self, n):
		return (0, -n, 0, "<< %dx" % n)

	def makeStateSlowMotion(self, n):
		return (0, 0, n, "/%d" % n)

	def isStateForward(self, state):
		return state[1] > 1

	def isStateBackward(self, state):
		return state[1] < 0

	def isStateSlowMotion(self, state):
		return state[1] == 0 and state[2] > 1

	def getHigher(self, n, lst):
		for x in lst:
			if x > n:
				return x
		return False

	def getLower(self, n, lst):
		lst = lst[:]
		lst.reverse()
		for x in lst:
			if x < n:
				return x
		return False

	def showAfterSeek(self):
		if isinstance(self, InfoBarShowHide):
			self.doShow()

	def up(self):
		pass

	def down(self):
		pass

	def __filmDinFisier(self):
		"""Un film sau o melodie redata de servicemp3 (tipul 4097): decodorul placii nu are incetinire, iar in pauza >> si
		<< pornesc derularea (salturi intre cadrele cheie, lib/service/servicemp3.cpp)."""
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		return ref is not None and ref.type == 4097

	def __mesajFaraDerulare(self, seek):
		"""Salturile cu cifrele merg, derularea nu: un flux de pe internet (fiecare salt asteapta reteaua) sau o
		inregistrare fara imagine inca."""
		if self.fast_winding_hint_message_showed or not (seek.isCurrentlySeekable() & 1):
			return False
		if self.__filmDinFisier():
			text = _("Derularea rapidă nu merge la filmele de pe internet. Poți sări înainte sau înapoi cu tastele 1, 3, 4, 6, 7 și 9.")
		else:
			text = _("Derularea rapidă nu merge acum. Poți sări înainte sau înapoi cu tastele 1, 3, 4, 6, 7 și 9.")
		self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=10)
		self.fast_winding_hint_message_showed = True
		return True

	def getSeek(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None

		seek = service.seek()

		if seek is None or not seek.isCurrentlySeekable():
			return None

		return seek

	def isSeekable(self):
		if self.getSeek() is None:
			return False
		return True

	def __seekableStatusChanged(self):
#		print "seekable status changed!"
		if not self.isSeekable():
			self["SeekActions"].setEnabled(False)
#			print "not seekable, return to play"
			self.setSeekState(self.SEEK_STATE_PLAY)
		else:
			self["SeekActions"].setEnabled(True)
#			print "seekable"

	def __serviceStarted(self):
		self.fast_winding_hint_message_showed = False
		self.seekstate = self.SEEK_STATE_PLAY
		self.__seekableStatusChanged()

	def setSeekState(self, state):
		service = self.session.nav.getCurrentService()

		if service is None:
			return False

		if not self.isSeekable():
			if state not in (self.SEEK_STATE_PLAY, self.SEEK_STATE_PAUSE):
				state = self.SEEK_STATE_PLAY

		pauseable = service.pause()

		if pauseable is None:
			print("not pauseable.")
			state = self.SEEK_STATE_PLAY

		self.seekstate = state

		if pauseable is not None:
			if self.seekstate[0]:
				print("resolved to PAUSE")
				pauseable.pause()
			elif self.seekstate[1]:
				print("resolved to FAST FORWARD")
				pauseable.setFastForward(self.seekstate[1])
			elif self.seekstate[2]:
				print("resolved to SLOW MOTION")
				pauseable.setSlowMotion(self.seekstate[2])
			else:
				print("resolved to PLAY")
				pauseable.unpause()

		for c in self.onPlayStateChanged:
			c(self.seekstate)

		self.checkSkipShowHideLock()

		return True

	def playpauseService(self):
		if self.seekstate != self.SEEK_STATE_PLAY:
			self.unPauseService()
		else:
			self.pauseService()

	def pauseService(self):
		if self.seekstate == self.SEEK_STATE_PAUSE:
			if config.seek.on_pause.value == "play":
				self.unPauseService()
			elif config.seek.on_pause.value == "step":
				self.doSeekRelative(1)
			elif config.seek.on_pause.value == "last":
				self.setSeekState(self.lastseekstate)
				self.lastseekstate = self.SEEK_STATE_PLAY
		else:
			if self.seekstate != self.SEEK_STATE_EOF:
				self.lastseekstate = self.seekstate
			self.setSeekState(self.SEEK_STATE_PAUSE);

	def unPauseService(self):
		print("unpause")
		if self.seekstate == self.SEEK_STATE_PLAY:
			return 0
		self.setSeekState(self.SEEK_STATE_PLAY)

	def doSeek(self, pts):
		seekable = self.getSeek()
		if seekable is None:
			return
		seekable.seekTo(pts)

	def doSeekRelative(self, pts):
		seekable = self.getSeek()
		if seekable is None:
			return
		prevstate = self.seekstate

		if self.seekstate == self.SEEK_STATE_EOF:
			if prevstate == self.SEEK_STATE_PAUSE:
				self.setSeekState(self.SEEK_STATE_PAUSE)
			else:
				self.setSeekState(self.SEEK_STATE_PLAY)
		seekable.seekRelative(pts<0 and -1 or 1, abs(pts))
		if abs(pts) > 100 and config.usage.show_infobar_on_skip.value:
			self.showAfterSeek()

	def seekFwd(self):
		seek = self.getSeek()
		if seek and not (seek.isCurrentlySeekable() & 2):
			if self.__mesajFaraDerulare(seek):
				return
			return 0 # trade as unhandled action
		if self.seekstate == self.SEEK_STATE_PLAY:
			self.setSeekState(self.makeStateForward(int(config.seek.enter_forward.value)))
		elif self.seekstate == self.SEEK_STATE_PAUSE:
			if len(config.seek.speeds_slowmotion.value) and not self.__filmDinFisier():
				self.setSeekState(self.makeStateSlowMotion(config.seek.speeds_slowmotion.value[-1]))
			else:
				self.setSeekState(self.makeStateForward(int(config.seek.enter_forward.value)))
		elif self.seekstate == self.SEEK_STATE_EOF:
			pass
		elif self.isStateForward(self.seekstate):
			speed = self.seekstate[1]
			if self.seekstate[2]:
				speed //= self.seekstate[2]
			speed = self.getHigher(speed, config.seek.speeds_forward.value) or config.seek.speeds_forward.value[-1]
			self.setSeekState(self.makeStateForward(speed))
		elif self.isStateBackward(self.seekstate):
			speed = -self.seekstate[1]
			if self.seekstate[2]:
				speed //= self.seekstate[2]
			speed = self.getLower(speed, config.seek.speeds_backward.value)
			if speed:
				self.setSeekState(self.makeStateBackward(speed))
			else:
				self.setSeekState(self.SEEK_STATE_PLAY)
		elif self.isStateSlowMotion(self.seekstate):
			speed = self.getLower(self.seekstate[2], config.seek.speeds_slowmotion.value) or config.seek.speeds_slowmotion.value[0]
			self.setSeekState(self.makeStateSlowMotion(speed))

	def seekBack(self):
		seek = self.getSeek()
		if seek and not (seek.isCurrentlySeekable() & 2):
			if self.__mesajFaraDerulare(seek):
				return
			return 0 # trade as unhandled action
		seekstate = self.seekstate
		if seekstate == self.SEEK_STATE_PLAY:
			self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
		elif seekstate == self.SEEK_STATE_EOF:
			self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
			self.doSeekRelative(-6)
		elif seekstate == self.SEEK_STATE_PAUSE:
			if self.__filmDinFisier():
				# un film nu are pas cu pas inapoi: << din pauza porneste derularea inapoi
				self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))
			else:
				self.doSeekRelative(-1)
		elif self.isStateForward(seekstate):
			speed = seekstate[1]
			if seekstate[2]:
				speed //= seekstate[2]
			speed = self.getLower(speed, config.seek.speeds_forward.value)
			if speed:
				self.setSeekState(self.makeStateForward(speed))
			else:
				self.setSeekState(self.SEEK_STATE_PLAY)
		elif self.isStateBackward(seekstate):
			speed = -seekstate[1]
			if seekstate[2]:
				speed //= seekstate[2]
			speed = self.getHigher(speed, config.seek.speeds_backward.value) or config.seek.speeds_backward.value[-1]
			self.setSeekState(self.makeStateBackward(speed))
		elif self.isStateSlowMotion(seekstate):
			speed = self.getHigher(seekstate[2], config.seek.speeds_slowmotion.value)
			if speed:
				self.setSeekState(self.makeStateSlowMotion(speed))
			else:
				self.setSeekState(self.SEEK_STATE_PAUSE)

	def seekFwdManual(self):
		self.session.openWithCallback(self.fwdSeekTo, MinuteInput)

	def fwdSeekTo(self, minutes):
		print("Seek", minutes, "minutes forward")
		self.doSeekRelative(minutes * 60 * 90000)

	def seekBackManual(self):
		self.session.openWithCallback(self.rwdSeekTo, MinuteInput)

	def rwdSeekTo(self, minutes):
		print("rwdSeekTo")
		self.doSeekRelative(-minutes * 60 * 90000)

	def checkSkipShowHideLock(self):
		wantlock = self.seekstate != self.SEEK_STATE_PLAY

		if config.usage.show_infobar_on_skip.value:
			if self.lockedBecauseOfSkipping and not wantlock:
				self.unlockShow()
				self.lockedBecauseOfSkipping = False

			if wantlock and not self.lockedBecauseOfSkipping:
				self.lockShow()
				self.lockedBecauseOfSkipping = True

	def calcRemainingTime(self):
		seekable = self.getSeek()
		if seekable is not None:
			len = seekable.getLength()
			try:
				tmp = self.cueGetEndCutPosition()
				if tmp:
					len = [False, tmp]
			except:
				pass
			pos = seekable.getPlayPosition()
			speednom = self.seekstate[1] or 1
			speedden = self.seekstate[2] or 1
			if not len[0] and not pos[0]:
				if len[1] <= pos[1]:
					return 0
				time = (len[1] - pos[1])*speedden//(90*speednom)
				return time
		return False
		
	def __evEOF(self):
		if self.seekstate == self.SEEK_STATE_EOF:
			return

		# if we are seeking forward, we try to end up ~1s before the end, and pause there.
		seekstate = self.seekstate
		if self.seekstate != self.SEEK_STATE_PAUSE:
			self.setSeekState(self.SEEK_STATE_EOF)

		if seekstate not in (self.SEEK_STATE_PLAY, self.SEEK_STATE_PAUSE): # if we are seeking
			seekable = self.getSeek()
			if seekable is not None:
				seekable.seekTo(-1)
		if seekstate == self.SEEK_STATE_PLAY: # regular EOF
			self.doEofInternal(True)
		else:
			self.doEofInternal(False)

	def doEofInternal(self, playing):
		pass		# Defined in subclasses

	def __evSOF(self):
		self.setSeekState(self.SEEK_STATE_PLAY)
		self.doSeek(0)

from Screens.PVRState import PVRState, TimeshiftState

class InfoBarPVRState:
	def __init__(self, screen=PVRState, force_show = False):
		self.onPlayStateChanged.append(self.__playStateChanged)
		self.pvrStateDialog = self.session.instantiateDialog(screen)
		self.onShow.append(self._mayShow)
		self.onHide.append(self.pvrStateDialog.hide)
		self.force_show = force_show

	def _mayShow(self):
		if self.execing and self.seekstate != self.SEEK_STATE_PLAY:
			self.pvrStateDialog.show()

	def __playStateChanged(self, state):
		playstateString = state[3]
		# ">", "||", ">> 8x" sunt semne; sfarsitul filmului se spune in cuvinte
		self.pvrStateDialog["state"].setText(_("Sfârșit") if playstateString == "END" else playstateString)
		
		# if we return into "PLAY" state, ensure that the dialog gets hidden if there will be no infobar displayed
		if not config.usage.show_infobar_on_skip.value and self.seekstate == self.SEEK_STATE_PLAY and not self.force_show:
			self.pvrStateDialog.hide()
		else:
			self._mayShow()

class InfoBarTimeshiftState(InfoBarPVRState):
	def __init__(self):
		InfoBarPVRState.__init__(self, screen=TimeshiftState, force_show = True)
		self.__hideTimer = eTimer()
		self.__hideTimer.callback.append(self.__hideTimeshiftState)

	def _mayShow(self):
		if self.execing and self.timeshift_enabled:
			self.pvrStateDialog.show()
			if self.seekstate == self.SEEK_STATE_PLAY and not self.shown:
				self.__hideTimer.start(5*1000, True)

	def __hideTimeshiftState(self):
		self.pvrStateDialog.hide()

class InfoBarShowMovies:

	# i don't really like this class.
	# it calls a not further specified "movie list" on up/down/movieList,
	# so this is not more than an action map
	def __init__(self):
		self["MovieListActions"] = HelpableActionMap(self, "InfobarMovieListActions",
			{
				"movieList": (self.showMovies, _("movie list")),
				"up": (self.showMovies, _("movie list")),
				"down": (self.showMovies, _("movie list"))
			})

# InfoBarTimeshift requires InfoBarSeek, instantiated BEFORE!

# Hrmf.
#
# Timeshift works the following way:
#                                         demux0   demux1                    "TimeshiftActions" "TimeshiftActivateActions" "SeekActions"
# - normal playback                       TUNER    unused      PLAY               enable                disable              disable
# - user presses "yellow" button.         FILE     record      PAUSE              enable                disable              enable
# - user presess pause again              FILE     record      PLAY               enable                disable              enable
# - user fast forwards                    FILE     record      FF                 enable                disable              enable
# - end of timeshift buffer reached       TUNER    record      PLAY               enable                enable               disable
# - user backwards                        FILE     record      BACK  # !!         enable                disable              enable
#

# in other words:
# - when a service is playing, pressing the "timeshiftStart" button ("yellow") enables recording ("enables timeshift"),
# freezes the picture (to indicate timeshift), sets timeshiftMode ("activates timeshift")
# now, the service becomes seekable, so "SeekActions" are enabled, "TimeshiftEnableActions" are disabled.
# - the user can now PVR around
# - if it hits the end, the service goes into live mode ("deactivates timeshift", it's of course still "enabled")
# the service looses it's "seekable" state. It can still be paused, but just to activate timeshift right
# after!
# the seek actions will be disabled, but the timeshiftActivateActions will be enabled
# - if the user rewinds, or press pause, timeshift will be activated again

# note that a timeshift can be enabled ("recording") and
# activated (currently time-shifting).

class InfoBarTimeshift:
	def __init__(self):
		self["TimeshiftActions"] = HelpableActionMap(self, "InfobarTimeshiftActions",
			{
				"timeshiftStart": (self.startTimeshift, _("start timeshift")),  # the "yellow key"
				"timeshiftStop": (self.stopTimeshift, _("stop timeshift"))      # currently undefined :), probably 'TV'
			}, prio=1)
		self["TimeshiftActivateActions"] = ActionMap(["InfobarTimeshiftActivateActions"],
			{
				"timeshiftActivateEnd": self.activateTimeshiftEnd, # something like "rewind key"
				"timeshiftActivateEndAndPause": self.activateTimeshiftEndAndPause  # something like "pause key"
			}, prio=-1) # priority over record

		self.timeshift_enabled = 0
		self.timeshift_state = 0
		self.ts_rewind_timer = eTimer()
		self.ts_rewind_timer.callback.append(self.rewindService)

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.__serviceStarted,
				iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged
			})

	def getTimeshift(self):
		service = self.session.nav.getCurrentService()
		return service and service.timeshift()

	def hdsLocTimeshiftAles(self, ales=False):
		if ales:
			self.startTimeshift()

	def hdsLocTimeshiftRau(self, loc, motiv, HdsStocare):
		"""Locul pauzei nu e un disc adevarat: ecranul 'Locul inregistrarilor' (Screens/HdsLocInregistrari.py), dupa
		care pauza porneste din nou."""
		try:
			from Screens.HdsLocInregistrari import HdsLocInregistrari
		except ImportError:
			HdsLocInregistrari = None
		if HdsLocInregistrari is None:
			self.session.open(MessageBox, HdsStocare.mesajTimeshift(motiv, loc), MessageBox.TYPE_ERROR)
		else:
			self.session.openWithCallback(self.hdsLocTimeshiftAles, HdsLocInregistrari, loc, motiv, "timeshift")

	def hdsFaraTimeshift(self):
		"""Serviciul nu a dat pauza (getTimeshift() e None). Nucleul spune de ce numai in jurnal
		(lib/service/servicedvb.cpp, eDVBServicePlay::timeshift), deci cauza se cauta aici, in aceeasi ordine
		(Components/HdsStocare.cauzaFaraTimeshift): fara pista video, locul care nu e un disc, sub 1 GB liberi.
		True cand cauza se stie si omul a primit mesajul ei (sau ecranul locului)."""
		try:
			from Components import HdsStocare
			loc = config.usage.timeshift_path.value
			service = self.session.nav.getCurrentService()
			info = service and service.info()
			if info is None:
				return False          # niciun serviciu: mesajul general, nu cel al radioului
			vpid = info.getInfo(iServiceInformation.sVideoPID)
			# aceeasi pista video ca in nucleu (m_have_video_pid: 0 < pid < 0x2000)
			cauza, valoare = HdsStocare.cauzaFaraTimeshift(loc, 0 < vpid < 0x2000)
		except (ImportError, AttributeError, KeyError, TypeError):
			return False
		print("[InfoBarTimeshift] fara pauza: %s %s (%s)" % (cauza or "-", valoare, loc))
		if cauza == HdsStocare.TS_FARA_VIDEO:
			self.session.open(MessageBox, HdsStocare.mesajTimeshiftFaraVideo(), MessageBox.TYPE_INFO)
		elif cauza == HdsStocare.TS_LOC:
			self.hdsLocTimeshiftRau(loc, valoare, HdsStocare)
		elif cauza == HdsStocare.TS_SPATIU:
			self.session.open(MessageBox, HdsStocare.mesajTimeshiftSpatiu(loc, valoare), MessageBox.TYPE_ERROR)
		else:
			return False
		return True

	def startTimeshift(self):
		print("enable timeshift")
		ts = self.getTimeshift()
		if ts is None:
			# HDSatelit: cauza, cand se poate afla (hdsFaraTimeshift); altfel mesajul general
			if self.hdsFaraTimeshift():
				return 0
			# fraza simpla, apoi detaliul tehnic (ca mesajele de ecran negru)
			self.session.open(MessageBox, _("Acest canal nu poate fi pus pe pauză.") + "\n\n" +
				_("Detaliu tehnic: %s") % _("serviciul nu are timeshift"), MessageBox.TYPE_ERROR)
			print("no ts interface")
			return 0
		# HDSatelit: locul implicit al timeshift-ului, /media/hdd/, e in RAM pe Viper 4K V20
		# (tmpfs de 64 KB): numai pe un disc adevarat montat, altfel ecranul „Locul înregistrărilor”
		# (Screens/HdsLocInregistrari.py); dupa alegere timeshift-ul porneste din nou de aici
		if not self.timeshift_enabled:
			try:
				from Components import HdsStocare
				loc = config.usage.timeshift_path.value
				bun, motiv = HdsStocare.verificaDisc(loc)
			except (ImportError, AttributeError, KeyError):
				bun = True
			if not bun:
				self.hdsLocTimeshiftRau(loc, motiv, HdsStocare)
				return 0

		if self.timeshift_enabled:
			print("hu, timeshift already enabled?")
		else:
			if not ts.startTimeshift():
				self.timeshift_enabled = 1

				# we remove the "relative time" for now.
				#self.pvrStateDialog["timeshift"].setRelative(time.time())

				# PAUSE.
				#self.setSeekState(self.SEEK_STATE_PAUSE)
				self.activateTimeshiftEnd(False)

				# enable the "TimeshiftEnableActions", which will override
				# the startTimeshift actions
				self.__seekableStatusChanged()
			else:
				print("timeshift failed")
				try:
					loc = config.usage.timeshift_path.value
				except (AttributeError, KeyError):
					loc = ""
				self.session.open(MessageBox, _("Pauza nu a pornit. Verifică discul sau stick-ul USB ales pentru timeshift.") +
					"\n\n" + _("Detaliu tehnic: %s") % (_("timeshift nu a pornit în %s") % loc), MessageBox.TYPE_ERROR)

	def stopTimeshift(self):
		if not self.timeshift_enabled:
			return 0
		print("disable timeshift")
		ts = self.getTimeshift()
		if ts is None:
			return 0
		self.session.openWithCallback(self.stopTimeshiftConfirmed, MessageBox, _("Stop Timeshift?"), MessageBox.TYPE_YESNO)

	def stopTimeshiftConfirmed(self, confirmed):
		if not confirmed:
			return

		ts = self.getTimeshift()
		if ts is None:
			return

		ts.stopTimeshift()
		self.timeshift_enabled = 0

		# disable actions
		self.__seekableStatusChanged()

	# activates timeshift, and seeks to (almost) the end
	def activateTimeshiftEnd(self, back = True):
		ts = self.getTimeshift()
		print("activateTimeshiftEnd")

		if ts is None:
			return

		if ts.isTimeshiftActive():
			print("!! activate timeshift called - but shouldn't this be a normal pause?")
			self.pauseService()
		else:
			print("play, ...")
			ts.activateTimeshift() # activate timeshift will automatically pause
			self.setSeekState(self.SEEK_STATE_PAUSE)

		if back:
			self.ts_rewind_timer.start(200, 1)

	def rewindService(self):
		self.setSeekState(self.makeStateBackward(int(config.seek.enter_backward.value)))

	# same as activateTimeshiftEnd, but pauses afterwards.
	def activateTimeshiftEndAndPause(self):
		print("activateTimeshiftEndAndPause")
		#state = self.seekstate
		self.activateTimeshiftEnd(False)

	def __seekableStatusChanged(self):
		enabled = False

#		print "self.isSeekable", self.isSeekable()
#		print "self.timeshift_enabled", self.timeshift_enabled

		# when this service is not seekable, but timeshift
		# is enabled, this means we can activate
		# the timeshift
		if not self.isSeekable() and self.timeshift_enabled:
			enabled = True

#		print "timeshift activate:", enabled
		self["TimeshiftActivateActions"].setEnabled(enabled)

	def __serviceStarted(self):
		self.timeshift_enabled = False
		self.__seekableStatusChanged()

from Screens.PiPSetup import PiPSetup

class InfoBarExtensions:
	EXTENSION_SINGLE = 0
	EXTENSION_LIST = 1

	def __init__(self):
		self.list = []

		self["InstantExtensionsActions"] = HelpableActionMap(self, "InfobarExtensions",
			{
				"extensions": (self.showExtensionSelection, _("view extensions...")),
			}, 1) # lower priority

	def addExtension(self, extension, key = None, type = EXTENSION_SINGLE):
		self.list.append((type, extension, key))

	def updateExtension(self, extension, key = None):
		self.extensionsList.append(extension)
		if key is not None:
			if key in self.extensionKeys:
				key = None

		if key is None:
			for x in self.availableKeys:
				if x not in self.extensionKeys:
					key = x
					break

		if key is not None:
			self.extensionKeys[key] = len(self.extensionsList) - 1

	def updateExtensions(self):
		self.extensionsList = []
		self.availableKeys = [ "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "red", "green", "yellow", "blue" ]
		self.extensionKeys = {}
		for x in self.list:
			if x[0] == self.EXTENSION_SINGLE:
				self.updateExtension(x[1], x[2])
			else:
				for y in x[1]():
					self.updateExtension(y[0], y[1])


	def showExtensionSelection(self):
		self.updateExtensions()
		extensionsList = self.extensionsList[:]
		keys = []
		list = []
		for x in self.availableKeys:
			if x in self.extensionKeys:
				entry = self.extensionKeys[x]
				extension = self.extensionsList[entry]
				if extension[2]():
					name = str(extension[0]())
					list.append((extension[0](), extension))
					keys.append(x)
					extensionsList.remove(extension)
				else:
					extensionsList.remove(extension)
		list.extend([(x[0](), x) for x in extensionsList])

		keys += [""] * len(extensionsList)
		if not list:
			# 0.2.6: functiile imaginii sunt in meniu, deci fara extensii puse de om lista
			# e goala: un mesaj in locul unei ferestre fara niciun rand
			self.session.open(MessageBox, _("Nu ai extensii instalate. Le poți adăuga din meniu, la Extensii și aplicații."),
				MessageBox.TYPE_INFO, timeout=8)
			return
		self.session.openWithCallback(self.extensionCallback, ChoiceBox, title=_("Please choose an extension..."), list = list, keys = keys, skin_name = "ExtensionsList")

	def extensionCallback(self, answer):
		if answer is not None:
			answer[1][1]()

from Tools.BoundFunction import boundFunction
import inspect

# depends on InfoBarExtensions

class InfoBarPlugins:
	def __init__(self):
		self.addExtension(extension = self.getPluginList, type = InfoBarExtensions.EXTENSION_LIST)

	def getPluginName(self, name):
		return name

	def getPluginList(self):
		l = []
		for p in plugins.getPlugins(where = PluginDescriptor.WHERE_EXTENSIONSMENU):
		  args = inspect.getfullargspec(p.fnc).args
		  if len(args) == 1 or len(args) == 2 and isinstance(self, InfoBarChannelSelection):
			  l.append(((boundFunction(self.getPluginName, p.name), boundFunction(self.runPlugin, p), lambda: True), None, p.name))
		l.sort(key = lambda e: e[2]) # sort by name
		return l

	def runPlugin(self, plugin):
		if isinstance(self, InfoBarChannelSelection):
			plugin(session = self.session, servicelist = self.servicelist)
		else:
			plugin(session = self.session)

from Components.Task import job_manager
class InfoBarJobman:
	def __init__(self):
		self.addExtension(extension = self.getJobList, type = InfoBarExtensions.EXTENSION_LIST)

	def getJobList(self):
		return [((boundFunction(self.getJobName, job), boundFunction(self.showJobView, job), lambda: True), None) for job in job_manager.getPendingJobs()]

	def getJobName(self, job):
		return "%s: %s (%d%%)" % (job.getStatustext(), job.name, int(100*job.progress/float(job.end)))

	def showJobView(self, job):
		from Screens.TaskView import JobView
		job_manager.in_background = False
		self.session.openWithCallback(self.JobViewCB, JobView, job)
	
	def JobViewCB(self, in_background):
		job_manager.in_background = in_background

# depends on InfoBarExtensions
class InfoBarPiP:
	def __init__(self):
		try:
			self.session.pipshown
		except:
			self.session.pipshown = False
		if SystemInfo.get("NumVideoDecoders", 1) > 1:
			if (self.allowPiP):
				self.addExtension((self.getShowHideName, self.showPiP, lambda: True), "blue")
				self.addExtension((self.getMoveName, self.movePiP, self.pipShown), "green")
				self.addExtension((self.getSwapName, self.swapPiP, self.pipShown), "yellow")
			else:
				self.addExtension((self.getShowHideName, self.showPiP, self.pipShown), "blue")
				self.addExtension((self.getMoveName, self.movePiP, self.pipShown), "green")

	def pipShown(self):
		return self.session.pipshown

	def pipHandles0Action(self):
		return self.pipShown() and config.usage.pip_zero_button.value != "standard"

	def getShowHideName(self):
		if self.session.pipshown:
			return _("Disable Picture in Picture")
		else:
			return _("Activate Picture in Picture")

	def getSwapName(self):
		return _("Swap Services")

	def getMoveName(self):
		return _("Move Picture in Picture")

	def showPiP(self):
		if self.session.pipshown:
			del self.session.pip
			self.session.pipshown = False
		else:
			self.session.pip = self.session.instantiateDialog(PictureInPicture)
			self.session.pip.show()
			newservice = self.session.nav.getCurrentlyPlayingServiceReference()
			if self.session.pip.playService(newservice):
				self.session.pipshown = True
				self.session.pip.servicePath = self.servicelist.getCurrentServicePath()
			else:
				self.session.pipshown = False
				del self.session.pip
			self.session.nav.playService(newservice)

	def swapPiP(self):
		swapservice = self.session.nav.getCurrentlyPlayingServiceReference()
		if self.session.pip.servicePath:
			servicepath = self.servicelist.getCurrentServicePath()
			ref=servicepath[len(servicepath)-1]
			pipref=self.session.pip.getCurrentService()
			self.session.pip.playService(swapservice)
			self.servicelist.setCurrentServicePath(self.session.pip.servicePath)
			if pipref.toString() != ref.toString(): # is a subservice ?
				self.session.nav.stopService() # stop portal
				self.session.nav.playService(pipref) # start subservice
			self.session.pip.servicePath=servicepath

	def movePiP(self):
		self.session.open(PiPSetup, pip = self.session.pip)

	def pipDoHandle0Action(self):
		use = config.usage.pip_zero_button.value
		if "swap" == use:
			self.swapPiP()
		elif "swapstop" == use:
			self.swapPiP()
			self.showPiP()
		elif "stop" == use:
			self.showPiP()

from RecordTimer import parseEvent, RecordTimerEntry

class InfoBarInstantRecord:
	"""Instant Record - handles the instantRecord action in order to
	start/stop instant records"""
	def __init__(self):
		self["InstantRecordActions"] = HelpableActionMap(self, "InfobarInstantRecord",
			{
				"instantRecord": (self.instantRecord, _("Instant Record...")),
			})
		self.recording = []

	def stopCurrentRecording(self, entry = -1):
		if entry is not None and entry != -1:
			self.session.nav.RecordTimer.removeEntry(self.recording[entry])
			self.recording.remove(self.recording[entry])

	def startInstantRecording(self, limitEvent = False):
		serviceref = self.session.nav.getCurrentlyPlayingServiceReference()

		# try to get event info
		event = None
		try:
			service = self.session.nav.getCurrentService()
			epg = eEPGCache.getInstance()
			event = epg.lookupEventTime(serviceref, -1, 0)
			if event is None:
				info = service.info()
				ev = info.getEvent(0)
				event = ev
		except:
			pass

		begin = int(time())
		end = begin + 3600	# dummy
		name = "instant record"
		description = ""
		eventid = None

		if event is not None:
			curEvent = parseEvent(event)
			name = curEvent[2]
			description = curEvent[3]
			eventid = curEvent[4]
			if limitEvent:
				end = curEvent[1]
		else:
			if limitEvent:
				self.session.open(MessageBox, _("No event info found, recording indefinitely."), MessageBox.TYPE_INFO)

		if isinstance(serviceref, eServiceReference):
			serviceref = ServiceReference(serviceref)

		recording = RecordTimerEntry(serviceref, begin, end, name, description, eventid, dirname = preferredInstantRecordPath())
		recording.dontSave = True
		# HDSatelit: inregistrarea pornita de mana se decripteaza mereu pe loc (Components/HdsDecodare.py)
		recording.hdsDecodareMaiTarziu = False

		if event is None or limitEvent == False:
			recording.autoincrease = True
			recording.setAutoincreaseEnd()

		simulTimerList = self.session.nav.RecordTimer.record(recording)

		if simulTimerList is None:	# no conflict
			self.recording.append(recording)
		else:
			if len(simulTimerList) > 1: # with other recording
				name = simulTimerList[1].name
				name_date = ' '.join((name, strftime('%c', localtime(simulTimerList[1].begin))))
				print("[TIMER] conflicts with", name_date)
				recording.autoincrease = True	# start with max available length, then increment
				if recording.setAutoincreaseEnd():
					self.session.nav.RecordTimer.record(recording)
					self.recording.append(recording)
					self.session.open(MessageBox, _("Record time limited due to conflicting timer %s") % name_date, MessageBox.TYPE_INFO)
				else:
					self.session.open(MessageBox, _("Couldn't record due to conflicting timer %s") % name, MessageBox.TYPE_INFO)
			else:
				# HDSatelit 0.3.0: fara referinta bruta in fraza; la DVB-T2 / DAB+ din satelit limita spusa pe intelesul
				# oricui (Components/HdsInregistrariProgramate.mesajNeinregistrabil)
				from Components import HdsInregistrariProgramate as HIP
				self.session.open(MessageBox, HIP.mesajNeinregistrabil(serviceref, _), MessageBox.TYPE_INFO)
			recording.autoincrease = False

	def isInstantRecordRunning(self):
		print("self.recording:", self.recording)
		if self.recording:
			for x in self.recording:
				if x.isRunning():
					return True
		return False

	def recordQuestionCallback(self, answer):
		print("pre:\n", self.recording)

		if answer is None or answer[1] == "no":
			return
		list = []
		recording = self.recording[:]
		for x in recording:
			if not x in self.session.nav.RecordTimer.timer_list:
				self.recording.remove(x)
			elif x.dontSave and x.isRunning():
				list.append((x, False))

		if answer[1] == "changeduration":
			if len(self.recording) == 1:
				self.changeDuration(0)
			else:
				self.session.openWithCallback(self.changeDuration, TimerSelection, list)
		elif answer[1] == "changeendtime":
			if len(self.recording) == 1:
				self.setEndtime(0)
			else:
				self.session.openWithCallback(self.setEndtime, TimerSelection, list)
		elif answer[1] == "stop":
			if len(self.recording) == 1:
				self.stopCurrentRecording(0)
			else:
				self.session.openWithCallback(self.stopCurrentRecording, TimerSelection, list)
		elif answer[1] in ( "indefinitely" , "manualduration", "manualendtime", "event"):
			self.startInstantRecording(limitEvent = answer[1] in ("event", "manualendtime") or False)
			if answer[1] == "manualduration":
				self.changeDuration(len(self.recording)-1)
			elif answer[1] == "manualendtime":
				self.setEndtime(len(self.recording)-1)
		print("after:\n", self.recording)

	def setEndtime(self, entry):
		if entry is not None and entry >= 0:
			self.selectedEntry = entry
			self.endtime=ConfigClock(default = self.recording[self.selectedEntry].end)
			dlg = self.session.openWithCallback(self.TimeDateInputClosed, TimeDateInput, self.endtime)
			dlg.setTitle(_("Please change recording endtime"))

	def TimeDateInputClosed(self, ret):
		if len(ret) > 1:
			if ret[0]:
				localendtime = localtime(ret[1])
				print("stopping recording at", strftime("%c", localendtime))
				if self.recording[self.selectedEntry].end != ret[1]:
					self.recording[self.selectedEntry].autoincrease = False
				self.recording[self.selectedEntry].end = ret[1]
				self.session.nav.RecordTimer.timeChanged(self.recording[self.selectedEntry])

	def changeDuration(self, entry):
		if entry is not None and entry >= 0:
			self.selectedEntry = entry
			self.session.openWithCallback(self.inputCallback, InputBox, title=_("How many minutes do you want to record?"), text="5", maxSize=False, type=Input.NUMBER)

	def inputCallback(self, value):
		if value is not None:
			print("stopping recording after", int(value), "minutes.")
			entry = self.recording[self.selectedEntry]
			if int(value) != 0:
				entry.autoincrease = False
			entry.end = int(time()) + 60 * int(value)
			self.session.nav.RecordTimer.timeChanged(entry)

	def hdsLocAles(self, ales=False):
		if ales:
			self.instantRecord()

	def instantRecord(self):
		# HDSatelit 0.3.0: un program DVB-T2 / post DAB+ din satelit (releul local) nu se poate inca inregistra: limita
		# spusa pe loc, inainte de alegerea discului si de intrebarea „Start recording?”; cu o inregistrare pornita
		# alegerile raman (oprirea ei), iar „add recording” ajunge la acelasi mesaj (startInstantRecording)
		if not self.isInstantRecordRunning():
			from Components import HdsInregistrariProgramate as HIP
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			if HIP.felNeinregistrabil(ref):
				self.session.open(MessageBox, HIP.mesajNeinregistrabil(ref, _), MessageBox.TYPE_INFO)
				return
		dir = preferredInstantRecordPath()
		if not dir or not fileExists(dir, 'w'):
			dir = defaultMoviePath()
		# HDSatelit: numai pe un disc adevarat montat (Components/HdsStocare.verificaDisc: dosarul exista, nu e in RAM,
		# nu e memoria interna); altfel ecranul „Locul înregistrărilor” (Screens/HdsLocInregistrari.py), cu discurile
		# conectate si „Folosește <disc> pentru înregistrări”; dupa alegere inregistrarea porneste din nou de aici.
		# verificaDisc da „lipsa” cand dosarul nu exista, deci acopera si verificarea veche cu stat().
		try:
			from Components import HdsStocare
			bun, motiv = HdsStocare.verificaDisc(dir)
		except ImportError:
			bun, motiv = True, ""
		if not bun:
			try:
				from Screens.HdsLocInregistrari import HdsLocInregistrari
			except ImportError:
				# ecranul nu e instalat: mesajul limpede, fara alegerea discului
				self.session.open(MessageBox, HdsStocare.mesajInregistrare(motiv, dir), MessageBox.TYPE_ERROR)
				return
			self.session.openWithCallback(self.hdsLocAles, HdsLocInregistrari, dir, motiv, "inregistrare")
			return

		if self.isInstantRecordRunning():
			self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, \
				title=_("A recording is currently running.\nWhat do you want to do?"), \
				list=((_("stop recording"), "stop"), \
				(_("add recording (stop after current event)"), "event"), \
				(_("add recording (indefinitely)"), "indefinitely"), \
				(_("add recording (enter recording duration)"), "manualduration"), \
				(_("add recording (enter recording endtime)"), "manualendtime"), \
				(_("change recording (duration)"), "changeduration"), \
				(_("change recording (endtime)"), "changeendtime"), \
				(_("do nothing"), "no")))
		else:
			dlg = self.session.openWithCallback(self.recordQuestionCallback, ChoiceBox, \
				title=_("Start recording?"), \
				list=((_("add recording (stop after current event)"), "event"), \
				(_("add recording (indefinitely)"), "indefinitely"), \
				(_("add recording (enter recording duration)"), "manualduration"), \
				(_("add recording (enter recording endtime)"), "manualendtime"), \
				(_("don't record"), "no")))
			dlg.setTitle(_("Record"))

from Tools.ISO639 import LanguageCodes

class InfoBarAudioSelection:
	# HDSatelit: tasta AUDIO scurta deschide ecranul de sunet, tinuta ~1 s comuta
	# AC3 downmix si arata un mesaj, ca in enigma2-ul mai nou (data/keymap.xml,
	# flags "b" si "l"). Nucleul nostru din 2011 trimite si eliberarea de dupa apasarea
	# lunga (enigma2-ul mai nou o schimba in flagStop), deci ca la tasta POWER (mytest.py, PowerKey): apasarea sterge semnul,
	# apasarea lunga il pune, eliberarea deschide ecranul numai fara semn.
	def __init__(self):
		self["AudioSelectionAction"] = HelpableActionMap(self, "InfobarAudioSelectionActions",
			{
				"audioSelection": (self.audioSelection, _("Audio Options...")),
				"audioSelectionPressed": self.audioSelectionPressed,
				"audioSelectionReleased": (self.audioSelectionReleased, _("Audio Options...")),
				"audioSelectionLong": (self.audioDownmixToggle, _("Toggle AC3 downmix")),
			})
		self.audioLongPressed = False

	def audioSelection(self):
		from Screens.AudioSelection import AudioSelection
		self.session.openWithCallback(self.audioSelected, AudioSelection, infobar=self)

	def audioSelected(self, ret=None):
		print("[infobar::audioSelected]", ret)

	def audioSelectionPressed(self):
		self.audioLongPressed = False

	def audioSelectionReleased(self):
		if self.audioLongPressed:
			self.audioLongPressed = False
		else:
			self.audioSelection()

	def audioDownmixToggle(self):
		self.audioLongPressed = True
		from Components.AVSwitch import toggleAC3Downmix
		downmix = toggleAC3Downmix()
		if downmix is None:
			return
		print("[InfoBarAudioSelection] AC3 downmix is now %s" % (downmix and "on" or "off"))
		if downmix:
			text = _("AC3 downmix on: AC3 sound goes out as stereo.")
		else:
			text = _("AC3 downmix off: AC3 sound goes unchanged to the TV.")
		Notifications.AddPopup(text=text, type=MessageBox.TYPE_INFO, timeout=5, id="AC3DownmixToggle")

# HDSatelit: clasa SubtitleSelection (in Screens/AudioSelection.py) exista deja,
# completa, stil Dreambox standard -- doar nu era legata la nicio tasta/meniu. keymap.xml
# leaga deja KEY_TEXT la actiunea "subtitles" (linia 670), dar nicio clasa InfoBar nu o prindea.
# Adaugat acest mixin minim, dupa modelul InfoBarAudioSelection de mai sus, ca sa lege
# tasta deja existenta la ecranul deja existent, fara sa inventez cod nou de subtitrare.
class InfoBarSubtitleSelection:
	def __init__(self):
		self["SubtitleSelectionAction"] = HelpableActionMap(self, "InfobarSubtitleSelectionActions",
			{
				"subtitles": (self.subtitleSelection, _("Subtitle Options...")),
			})

	def subtitleSelection(self):
		from Screens.AudioSelection import SubtitleSelection
		self.session.openWithCallback(self.subtitleSelected, SubtitleSelection, infobar=self)

	def subtitleSelected(self, ret=None):
		print("[infobar::subtitleSelected]", ret)

class InfoBarSubserviceSelection:
	def __init__(self):
		self["SubserviceSelectionAction"] = HelpableActionMap(self, "InfobarSubserviceSelectionActions",
			{
				"subserviceSelection": (self.subserviceSelection, _("Subservice list...")),
			})

		self["SubserviceQuickzapAction"] = HelpableActionMap(self, "InfobarSubserviceQuickzapActions",
			{
				"nextSubservice": (self.nextSubservice, _("Switch to next subservice")),
				"prevSubservice": (self.prevSubservice, _("Switch to previous subservice"))
			}, -1)
		self["SubserviceQuickzapAction"].setEnabled(False)

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.checkSubservicesAvail
			})

		self.bsel = None

	def checkSubservicesAvail(self):
		service = self.session.nav.getCurrentService()
		subservices = service and service.subServices()
		if not subservices or subservices.getNumberOfSubservices() == 0:
			self["SubserviceQuickzapAction"].setEnabled(False)

	def nextSubservice(self):
		self.changeSubservice(+1)

	def prevSubservice(self):
		self.changeSubservice(-1)

	def changeSubservice(self, direction):
		service = self.session.nav.getCurrentService()
		subservices = service and service.subServices()
		n = subservices and subservices.getNumberOfSubservices()
		if n and n > 0:
			selection = -1
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			idx = 0
			while idx < n:
				if subservices.getSubservice(idx).toString() == ref.toString():
					selection = idx
					break
				idx += 1
			if selection != -1:
				selection += direction
				if selection >= n:
					selection=0
				elif selection < 0:
					selection=n-1
				newservice = subservices.getSubservice(selection)
				if newservice.valid():
					del subservices
					del service
					self.session.nav.playService(newservice, False)

	def subserviceSelection(self):
		service = self.session.nav.getCurrentService()
		subservices = service and service.subServices()
		self.bouquets = self.servicelist.getBouquetList()
		n = subservices and subservices.getNumberOfSubservices()
		selection = 0
		if n and n > 0:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			tlist = []
			idx = 0
			while idx < n:
				i = subservices.getSubservice(idx)
				if i.toString() == ref.toString():
					selection = idx
				tlist.append((i.getName(), i))
				idx += 1

			if self.bouquets and len(self.bouquets):
				keys = ["red", "blue", "",  "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" ] + [""] * n
				if config.usage.multibouquet.value:
					tlist = [(_("Quickzap"), "quickzap", service.subServices()), (_("Add to bouquet"), "CALLFUNC", self.addSubserviceToBouquetCallback), ("--", "")] + tlist
				else:
					tlist = [(_("Quickzap"), "quickzap", service.subServices()), (_("Add to favourites"), "CALLFUNC", self.addSubserviceToBouquetCallback), ("--", "")] + tlist
				selection += 3
			else:
				tlist = [(_("Quickzap"), "quickzap", service.subServices()), ("--", "")] + tlist
				keys = ["red", "",  "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" ] + [""] * n
				selection += 2

			self.session.openWithCallback(self.subserviceSelected, ChoiceBox, title=_("Please select a subservice..."), list = tlist, selection = selection, keys = keys, skin_name = "SubserviceSelection")

	def subserviceSelected(self, service):
		del self.bouquets
		if not service is None:
			if isinstance(service[1], str):
				if service[1] == "quickzap":
					from Screens.SubservicesQuickzap import SubservicesQuickzap
					self.session.open(SubservicesQuickzap, service[2])
			else:
				self["SubserviceQuickzapAction"].setEnabled(True)
				self.session.nav.playService(service[1], False)

	def addSubserviceToBouquetCallback(self, service):
		if len(service) > 1 and isinstance(service[1], eServiceReference):
			self.selectedSubservice = service
			if self.bouquets is None:
				cnt = 0
			else:
				cnt = len(self.bouquets)
			if cnt > 1: # show bouquet list
				self.bsel = self.session.openWithCallback(self.bouquetSelClosed, BouquetSelector, self.bouquets, self.addSubserviceToBouquet)
			elif cnt == 1: # add to only one existing bouquet
				self.addSubserviceToBouquet(self.bouquets[0][1])
				self.session.open(MessageBox, _("Service has been added to the favourites."), MessageBox.TYPE_INFO)

	def bouquetSelClosed(self, confirmed):
		self.bsel = None
		del self.selectedSubservice
		if confirmed:
			self.session.open(MessageBox, _("Service has been added to the selected bouquet."), MessageBox.TYPE_INFO)

	def addSubserviceToBouquet(self, dest):
		self.servicelist.addServiceToBouquet(dest, self.selectedSubservice[1])
		if self.bsel:
			self.bsel.close(True)
		else:
			del self.selectedSubservice

class InfoBarAdditionalInfo:
	def __init__(self):

		self["RecordingPossible"] = Boolean(fixed=harddiskmanager.HDDCount() > 0 and config.misc.rcused.value == 1)
		self["TimeshiftPossible"] = self["RecordingPossible"]
		self["ShowTimeshiftOnYellow"] = Boolean(fixed=(not config.misc.rcused.value == 0))
		self["ShowAudioOnYellow"] = Boolean(fixed=config.misc.rcused.value == 0)
		self["ShowRecordOnRed"] = Boolean(fixed=config.misc.rcused.value == 1)
		self["ExtensionsAvailable"] = Boolean(fixed=1)

class InfoBarNotifications:
	def __init__(self):
		self.onExecBegin.append(self.checkNotifications)
		Notifications.notificationAdded.append(self.checkNotificationsIfExecing)
		self.onClose.append(self.__removeNotification)

	def __removeNotification(self):
		Notifications.notificationAdded.remove(self.checkNotificationsIfExecing)

	def checkNotificationsIfExecing(self):
		if self.execing:
			self.checkNotifications()

	def checkNotifications(self):
		notifications = Notifications.notifications
		if notifications:
			# HDSatelit: canalul de la pornire porneste inaintea notificarii, nu dupa inchiderea ei
			# (InfoBarChannelSelection.hdsPornesteInainteaNotificarii; MoviePlayer nu o are)
			pornire = getattr(self, "hdsPornesteInainteaNotificarii", None)
			if pornire is not None:
				try:
					pornire()
				except Exception as e:
					print("[InfoBar] pornirea inaintea notificarii: %r" % (e,))
			n = notifications[0]

			del notifications[0]
			cb = n[0]

			if "onSessionOpenCallback" in n[3]:
				n[3]["onSessionOpenCallback"]()
				del n[3]["onSessionOpenCallback"]

			if cb is not None:
				dlg = self.session.openWithCallback(cb, n[1], *n[2], **n[3])
			else:
				dlg = self.session.open(n[1], *n[2], **n[3])

			# remember that this notification is currently active
			d = (n[4], dlg)
			Notifications.current_notifications.append(d)
			dlg.onClose.append(boundFunction(self.__notificationClosed, d))

	def __notificationClosed(self, d):
		Notifications.current_notifications.remove(d)

class InfoBarServiceNotifications:
	def __init__(self):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evEnd: self.serviceHasEnded
			})

	def serviceHasEnded(self):
		print("service end!")

		try:
			self.setSeekState(self.SEEK_STATE_PLAY)
		except:
			pass

class InfoBarCueSheetSupport:
	CUT_TYPE_IN = 0
	CUT_TYPE_OUT = 1
	CUT_TYPE_MARK = 2
	CUT_TYPE_LAST = 3

	ENABLE_RESUME_SUPPORT = False

	def __init__(self, actionmap = "InfobarCueSheetActions"):
		self["CueSheetActions"] = HelpableActionMap(self, actionmap,
			{
				"jumpPreviousMark": (self.jumpPreviousMark, _("jump to previous marked position")),
				"jumpNextMark": (self.jumpNextMark, _("jump to next marked position")),
				"toggleMark": (self.toggleMark, _("toggle a cut mark at the current position"))
			}, prio=1)

		self.cut_list = [ ]
		self.is_closing = False
		self.__asteaptaReluarea = False
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.__serviceStarted,
				iPlayableService.evCuesheetChanged: self.__cuesheetChanged,
			})

	def __serviceStarted(self):
		if self.is_closing:
			return
		print("new service started! trying to download cuts!")
		self.downloadCuesheet()
		self.__asteaptaReluarea = False

		if self.ENABLE_RESUME_SUPPORT and not self.__intreabaReluarea():
			# un film din fisier isi citeste semnele pe firul lui (lib/service/servicemp3.cpp): ele vin dupa pornire, cu
			# primul evCuesheetChanged, si intrebarea se pune atunci, o singura data (referinta serviciului nu se stie
			# inca la evStart: Navigation o pune dupa pornire). Ceasul monoton: o corectie a orei (NTP, ora din
			# transponder) intre pornire si citirea semnelor nu pierde intrebarea.
			from time import monotonic
			self.__asteaptaReluarea = monotonic()

	def __cuesheetChanged(self):
		if not self.__asteaptaReluarea or self.is_closing:
			return
		from time import monotonic
		asteptat = monotonic() - self.__asteaptaReluarea
		self.__asteaptaReluarea = False
		self.downloadCuesheet()
		if 0 <= asteptat < 30:
			self.__intreabaReluarea()

	def __textLoc(self, last):
		"""Locul tinut minte ca pe pagina web si pe bara: „30:36” la un film sub o ora, „0:30:36” la unul mai lung."""
		lungime = None
		seek = self.__getSeekable()
		if seek is not None:
			r = seek.getLength()
			if r and not r[0] and r[1] > 0:
				lungime = r[1]
		try:
			from Components.HdsFilmRedare import textTimp
		except ImportError:
			l = last // 90000
			return "%d:%02d:%02d" % (l // 3600, l % 3600 // 60, l % 60)
		return textTimp(last, lungime)

	def __intreabaReluarea(self):
		"""Intrebarea de reluare (sau reluarea directa) dupa ultima pozitie din lista; True daca lista are una. Un film
		pornit din pagina web („Reia” sau „De la început”) aduce raspunsul in hdsPornireFilm = (raspunsul, calea
		filmului), fara intrebare pe televizor; raspunsul se foloseste numai pentru acel film."""
		last = None
		for (pts, what) in self.cut_list:
			if what == self.CUT_TYPE_LAST:
				last = pts
		if last is None:
			return False

		self.resume_point = last
		mod = config.usage.on_movie_start.value
		ales = getattr(self, "hdsPornireFilm", None)
		if ales:
			self.hdsPornireFilm = None
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			if ref is not None and ref.getPath() == ales[1]:
				mod = ales[0]
		if mod == "ask":
			# aceleasi cuvinte ca in lista de filme si pe pagina web („Ai rămas la 1:01:03.”)
			Notifications.AddNotificationWithCallback(self.playLastCB, MessageBox, _("Reiei de unde ai rămas?") + "\n" + (_("Ai rămas la %s.") % self.__textLoc(last)), timeout=10)
		elif mod == "resume":
# TRANSLATORS: The string "Resuming playback" flashes for a moment
# TRANSLATORS: at the start of a movie, when the user has selected
# TRANSLATORS: "Resume from last position" as start behavior.
# TRANSLATORS: The purpose is to notify the user that the movie starts
# TRANSLATORS: in the middle somewhere and not from the beginning.
# TRANSLATORS: (Some translators seem to have interpreted it as a
# TRANSLATORS: question or a choice, but it is a statement.)
			Notifications.AddNotificationWithCallback(self.playLastCB, MessageBox, _("Resuming playback"), timeout=2, type=MessageBox.TYPE_INFO)
		return True

	def playLastCB(self, answer):
		if answer == True:
			self.doSeek(self.resume_point)
		self.hideAfterResume()

	def hideAfterResume(self):
		if isinstance(self, InfoBarShowHide):
			self.hide()

	def __getSeekable(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None
		return service.seek()

	def cueGetCurrentPosition(self):
		seek = self.__getSeekable()
		if seek is None:
			return None
		r = seek.getPlayPosition()
		if r[0]:
			return None
		return int(r[1])

	def cueGetEndCutPosition(self):
		ret = False
		isin = True
		for cp in self.cut_list:
			if cp[1] == self.CUT_TYPE_OUT:
				if isin:
					isin = False
					ret = cp[0]
			elif cp[1] == self.CUT_TYPE_IN:
				isin = True
		return ret
		
	def jumpPreviousNextMark(self, cmp, start=False):
		current_pos = self.cueGetCurrentPosition()
		if current_pos is None:
 			return False
		mark = self.getNearestCutPoint(current_pos, cmp=cmp, start=start)
		if mark is not None:
			pts = mark[0]
		else:
			return False

		self.doSeek(pts)
		return True

	def jumpPreviousMark(self):
		# we add 5 seconds, so if the play position is <5s after
		# the mark, the mark before will be used
		self.jumpPreviousNextMark(lambda x: -x-5*90000, start=True)

	def jumpNextMark(self):
		if not self.jumpPreviousNextMark(lambda x: x-90000):
			self.doSeek(-1)

	def getNearestCutPoint(self, pts, cmp=abs, start=False):
		# can be optimized
		beforecut = True
		nearest = None
		bestdiff = -1
		instate = True
		if start:
			bestdiff = cmp(0 - pts)
			if bestdiff >= 0:
				nearest = [0, False]
		for cp in self.cut_list:
			if beforecut and cp[1] in (self.CUT_TYPE_IN, self.CUT_TYPE_OUT):
				beforecut = False
				if cp[1] == self.CUT_TYPE_IN:  # Start is here, disregard previous marks
					diff = cmp(cp[0] - pts)
					if start and diff >= 0:
						nearest = cp
						bestdiff = diff
					else:
						nearest = None
						bestdiff = -1
			if cp[1] == self.CUT_TYPE_IN:
				instate = True
			elif cp[1] == self.CUT_TYPE_OUT:
				instate = False
			elif cp[1] in (self.CUT_TYPE_MARK, self.CUT_TYPE_LAST):
				diff = cmp(cp[0] - pts)
				if instate and diff >= 0 and (nearest is None or bestdiff > diff):
					nearest = cp
					bestdiff = diff
		return nearest

	def toggleMark(self, onlyremove=False, onlyadd=False, tolerance=5*90000, onlyreturn=False):
		current_pos = self.cueGetCurrentPosition()
		if current_pos is None:
			print("not seekable")
			return

		nearest_cutpoint = self.getNearestCutPoint(current_pos)

		if nearest_cutpoint is not None and abs(nearest_cutpoint[0] - current_pos) < tolerance:
			if onlyreturn:
				return nearest_cutpoint
			if not onlyadd:
				self.removeMark(nearest_cutpoint)
		elif not onlyremove and not onlyreturn:
			self.addMark((current_pos, self.CUT_TYPE_MARK))

		if onlyreturn:
			return None

	def addMark(self, point):
		insort(self.cut_list, point)
		self.uploadCuesheet()
		self.showAfterCuesheetOperation()

	def removeMark(self, point):
		self.cut_list.remove(point)
		self.uploadCuesheet()
		self.showAfterCuesheetOperation()

	def showAfterCuesheetOperation(self):
		if isinstance(self, InfoBarShowHide):
			self.doShow()

	def __getCuesheet(self):
		service = self.session.nav.getCurrentService()
		if service is None:
			return None
		return service.cueSheet()

	def uploadCuesheet(self):
		cue = self.__getCuesheet()

		if cue is None:
			print("upload failed, no cuesheet interface")
			return
		cue.setCutList(self.cut_list)

	def downloadCuesheet(self):
		cue = self.__getCuesheet()

		if cue is None:
			print("download failed, no cuesheet interface")
			self.cut_list = [ ]
		else:
			self.cut_list = cue.getCutList()

class InfoBarFilmRefuz:
	"""Un film din fisier (sau un flux redat de servicemp3, tipul 4097) pe care receptorul nu il poate reda. servicemp3
	da motivul in sUser+15 si anunta cu evUser+10, +11, +12 sau +16; textele sunt in Components/HdsFilmRedare.py.
	Imaginea fara drum spre placa, un format fara componenta, un fisier care nu se citeste sau nu porneste: in playerul
	de filme (leavePlayerConfirmed) fereastra cu mesajul, care sta pana la OK sau EXIT, apoi lista de filme, cu
	cursorul pe filmul de dupa cel refuzat; in bara principala (un canal de pe internet din lista de canale) un mesaj
	care pleaca singur dupa MESAJ_CANAL_S, cu frazele despre canal, iar canalul ramane ales. Numai sunetul fara drum: un
	mesaj scurt, filmul merge mai departe. O singura data pe film (pe canal)."""

	MESAJ_CANAL_S = 8

	def __init__(self):
		self.__filmSpus = False
		self.__filmUrmarire = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: self.__filmPornit,
				iPlayableService.evUser + 10: self.__filmFaraDrum,
				iPlayableService.evUser + 11: self.__filmFaraDrum,
				iPlayableService.evUser + 12: self.__filmFaraDrum,
				iPlayableService.evUser + 16: self.__filmFaraDrum,
			})

	def __filmPornit(self):
		self.__filmSpus = False
		Notifications.RemovePopup(id = "HdsFilm")

	def __filmFaraDrum(self):
		if self.__filmSpus:
			return
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is None or ref.type != 4097:
			return
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		# bara principala: un canal de pe internet din lista de canale, fara lista de filme in spate
		peCanal = getattr(self, "leavePlayerConfirmed", None) is None
		try:
			from Components import HdsFilmRedare
		except ImportError as eroare:
			# fara modulul textelor (o imagine construita fara el) ramane mesajul simplu, fara Traceback
			print("[InfoBarFilmRefuz] fara Components.HdsFilmRedare: %s" % eroare)
			self.__filmSpus = True
			if peCanal:
				Notifications.AddPopup(text = _("Canalul nu se poate reda pe acest receptor."), type = MessageBox.TYPE_ERROR, timeout = self.MESAJ_CANAL_S, id = "HdsFilm")
				return
			Notifications.AddNotificationWithCallback(self.__dupaRefuz, MessageBox, _("Filmul nu se poate reda pe acest receptor."), MessageBox.TYPE_ERROR)
			return
		verdict = HdsFilmRedare.verdictDinInfo(info, ref.getPath(), canal = peCanal)
		if verdict is None:
			return
		self.__filmSpus = True
		print("[InfoBarFilmRefuz] %s, se opreste: %s (%s)" % (verdict.fel, verdict.refuza, verdict.tehnic))
		if peCanal:
			# pe un canal nu se asteapta OK: mesajul pleaca singur (si la canalul urmator, __filmPornit)
			Notifications.RemovePopup(id = "HdsFilm")
			Notifications.AddPopup(text = verdict.text(), type = MessageBox.TYPE_ERROR if verdict.refuza else MessageBox.TYPE_INFO, timeout = self.MESAJ_CANAL_S, id = "HdsFilm")
			return
		if verdict.refuza:
			Notifications.RemovePopup(id = "HdsFilm")
			Notifications.AddNotificationWithCallback(self.__dupaRefuz, MessageBox, verdict.text(), MessageBox.TYPE_ERROR)
		else:
			Notifications.AddPopup(text = verdict.text(), type = MessageBox.TYPE_INFO, timeout = 8, id = "HdsFilm")

	def __dupaRefuz(self, *raspuns):
		# in playerul de filme: inapoi la lista, cu cursorul pe filmul de dupa cel refuzat (un OK in lista nu il mai
		# porneste din nou); in bara principala nimic, canalul ramane ales
		if getattr(self, "is_closing", False):
			return
		leave = getattr(self, "leavePlayerConfirmed", None)
		if leave is not None:
			self.hdsListaUrmatorul = True
			leave((True, "movielist"))


class InfoBarSummary(Screen):
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="global.CurrentTime" render="Label" position="62,46" size="82,18" font="Regular;16" >
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
		<widget source="session.RecordState" render="FixedLabel" text=" " position="62,46" size="82,18" zPosition="1" >
			<convert type="ConfigEntryTest">config.usage.blinking_display_clock_during_recording,True,CheckSourceBoolean</convert>
			<convert type="ConditionalShowHide">Blink</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="6,4" size="120,42" font="Regular;18" >
			<convert type="ServiceName">Name</convert>
		</widget>
		<widget source="session.Event_Now" render="Progress" position="6,46" size="46,18" borderWidth="1" >
			<convert type="EventTime">Progress</convert>
		</widget>
	</screen>"""

# for picon:  (path="piconlcd" will use LCD picons)
#		<widget source="session.CurrentService" render="Picon" position="6,0" size="120,64" path="piconlcd" >
#			<convert type="ServiceName">Reference</convert>
#		</widget>

class InfoBarSummarySupport:
	def __init__(self):
		pass

	def createSummary(self):
		return InfoBarSummary

class InfoBarMoviePlayerSummary(Screen):
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="global.CurrentTime" render="Label" position="62,46" size="64,18" font="Regular;16" halign="right" >
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
		<widget source="session.RecordState" render="FixedLabel" text=" " position="62,46" size="64,18" zPosition="1" >
			<convert type="ConfigEntryTest">config.usage.blinking_display_clock_during_recording,True,CheckSourceBoolean</convert>
			<convert type="ConditionalShowHide">Blink</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="6,4" size="120,42" font="Regular;18" >
			<convert type="ServiceName">Name</convert>
		</widget>
		<widget source="session.CurrentService" render="Progress" position="6,46" size="56,18" borderWidth="1" >
			<convert type="ServicePosition">Position</convert>
		</widget>
	</screen>"""

class InfoBarMoviePlayerSummarySupport:
	def __init__(self):
		pass

	def createSummary(self):
		return InfoBarMoviePlayerSummary

class InfoBarTeletextPlugin:
	def __init__(self):
		self.teletext_plugin = None

		for p in plugins.getPlugins(PluginDescriptor.WHERE_TELETEXT):
			self.teletext_plugin = p

		if self.teletext_plugin is not None:
			self["TeletextActions"] = HelpableActionMap(self, "InfobarTeletextActions",
				{
					"startTeletext": (self.startTeletext, _("View teletext..."))
				})
		else:
			print("no teletext plugin found!")

	def startTeletext(self):
		self.teletext_plugin(session=self.session, service=self.session.nav.getCurrentService())

def _hdsOcr(nume, *argumente):
	# HDSatelit: subtitrarile DVB citite ca text (Components/HdsOcrSubtitrari.py): limba pistei alese
	# (modelul incarcat dinainte), pista oprita, serviciul oprit la standby/iesire. O greseala de aici nu opreste
	# niciodata subtitrarile (fara OCR se arata pozele, ca inainte).
	try:
		from Components import HdsOcrSubtitrari
		return getattr(HdsOcrSubtitrari, nume)(*argumente)
	except Exception as e:
		print("[InfoBarSubtitleSupport] OCR %s: %s" % (nume, e))

class InfoBarSubtitleSupport(object):
	# HDSatelit: la fiecare canal si la
	# fiecare inregistrare, cand pistele se cunosc (evUpdatedInfo), sunetul si subtitrarea se aleg prin
	# Components/HdsPisteLimbi.py: alegerea de mana tinuta minte pe canal, apoi preferintele (sunet: limba
	# receptorului, engleza, pista canalului; subtitrare: numai in limba receptorului, altfel nimic).
	# Sunetul se alege tot aici, nu in InfoBarAudioSelection: toate ecranele care au InfoBarAudioSelection (InfoBar,
	# MoviePlayer, MediaPlayer, SubservicesQuickzap) o au si pe aceasta, iar un singur urmaritor de evenimente ajunge.
	# Subtitrarea tinuta minte de nucleu dupa PID (getCachedSubtitle) nu mai porneste singura: daca nu exista
	# subtitrare in limba aleasa, nu porneste nimic. Fara modul (inca lipsa din Components/Makefile.am) ramane
	# drumul vechi. Semnele tin minte pentru ce piste s-a ales deja, ca alegerea sa nu se repete la fiecare
	# evUpdatedInfo si sa nu se lupte cu ce porneste omul din meniu.
	def __init__(self):
		object.__init__(self)
		self.subtitle_window = self.session.instantiateDialog(SubtitleDisplay)
		self.__subtitles_enabled = False

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evEnd: self.__serviceStopped,
				iPlayableService.evUpdatedInfo: self.__updatedInfo
			})
		self.cached_subtitle_checked = False
		self.__selected_subtitle = None
		self.__semn_sunet = None
		self.__semn_subtitrare = None
		_hdsOcr("urmaresteOprirea")

	def __serviceStopped(self):
		self.cached_subtitle_checked = False
		self.__semn_sunet = None
		self.__semn_subtitrare = None
		if self.__subtitles_enabled:
			self.subtitle_window.hide()
			self.__subtitles_enabled = False
			self.__selected_subtitle = None
			_hdsOcr("pistaOprita")

	def __updatedInfo(self):
		try:
			from Components import HdsPisteLimbi
		except ImportError:
			HdsPisteLimbi = None
		except Exception as e:
			print("[InfoBarSubtitleSupport] Components/HdsPisteLimbi.py nu se poate incarca: %s" % e)
			HdsPisteLimbi = None
		if HdsPisteLimbi is not None:
			try:
				self.__semn_sunet = HdsPisteLimbi.aplicaAudio(self.session, self.__semn_sunet)
			except Exception as e:
				print("[InfoBarSubtitleSupport] sunetul dupa limba nu s-a putut alege: %s" % e)
			try:
				self.__semn_subtitrare = HdsPisteLimbi.aplicaSubtitrare(self, self.__semn_subtitrare)
				self.cached_subtitle_checked = True
				return
			except Exception as e:
				print("[InfoBarSubtitleSupport] subtitrarea dupa limba nu s-a putut alege: %s" % e)
		if not self.cached_subtitle_checked:
			self.cached_subtitle_checked = True
			subtitle = self.getCurrentServiceSubtitle()
			self.setSelectedSubtitle(subtitle and subtitle.getCachedSubtitle())
			if self.__selected_subtitle:
				self.setSubtitlesEnable(True)

	def hdsAlegeDinNou(self):
		"""Sunetul si subtitrarea serviciului care merge, alese din nou ca la pornirea lui (semnele uitate). Pentru bara,
		dupa playerul de filme inchis de un canal pornit peste film (Screens/InfoBar.py, hdsDupaPlayer): evenimentele de
		pornire ale canalului le-a primit playerul, nu bara. Daca lista pistelor nu a sosit inca, alegerea o face
		evUpdatedInfo-ul urmator, ca la orice zap."""
		self.cached_subtitle_checked = False
		self.__semn_sunet = None
		self.__semn_subtitrare = None
		self.__updatedInfo()

	def getCurrentServiceSubtitle(self):
		service = self.session.nav.getCurrentService()
		return service and service.subtitle()

	def setSubtitlesEnable(self, enable=True):
		subtitle = self.getCurrentServiceSubtitle()
		if enable:
			if self.__selected_subtitle:
				if subtitle and not self.__subtitles_enabled:
					subtitle.enableSubtitles(self.subtitle_window.instance, self.selected_subtitle)
					self.subtitle_window.show()
					self.__subtitles_enabled = True
					_hdsOcr("pistaAleasa", self.selected_subtitle)
		else:
			if subtitle:
				subtitle.disableSubtitles(self.subtitle_window.instance)
			self.__selected_subtitle = False
			self.__subtitles_enabled = False
			self.subtitle_window.hide()
			_hdsOcr("pistaOprita")

	def setSelectedSubtitle(self, subtitle):
		self.__selected_subtitle = subtitle

	subtitles_enabled = property(lambda self: self.__subtitles_enabled, setSubtitlesEnable)
	selected_subtitle = property(lambda self: self.__selected_subtitle, setSelectedSubtitle)

class InfoBarServiceErrorPopupSupport:
	def __init__(self):
		self.__event_tracker = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evTuneFailed: self.__tuneFailed,
				iPlayableService.evStart: self.__serviceStarted,
				iPlayableService.evUpdatedInfo: self.__serviceStarted,
				iPlayableService.evUpdatedEventInfo: self.__serviceStarted,
			})
		# sentinel unic (nu None si niciodata un string de referinta reala), ca prima chemare a lui
		# __serviceStarted() de mai jos sa initializeze mereu complet starea (last_error/retry_count),
		# indiferent daca la construire chiar ruleaza deja un serviciu sau nu.
		self.__retry_ref = object()
		self.hdsEcranNegru = None
		self.__hdsPornesteEcranNegru()
		self.__serviceStarted()

	def __hdsPornesteEcranNegru(self):
		"""Mesajul de pe mijlocul ecranului cat canalul ramane negru (Screens/HdsEcranNegru.py), numai pe bara
		canalelor: MoviePlayer foloseste si el acest mixin, dar acolo raman ferestrele de eroare. Harta de taste (OK =
		fapta, EXIT = ascunde) sta pe bara la prioritatea -1, pornita numai cat se vede mesajul; execBegin / execEnd ale
		ei spun mesajului cand bara e ecranul din fata. Fara modul sau cu skinul stricat raman ferestrele de eroare."""
		if not isinstance(self, InfoBarChannelSelection):
			return
		try:
			from Screens import HdsEcranNegru
		except ImportError as e:
			print("[InfoBarGenerics] mesajul de ecran negru lipseste:", e)
			return
		leg = HdsEcranNegru.faLegatura(self)
		if leg is None:
			return
		self.hdsEcranNegru = leg
		self["HdsEcranNegruActions"] = HdsEcranNegru.HartaEcranNegru(leg, {"toggleShow": leg.ok, "hide": leg.iesire}, prio=-1)
		leg.legaHarta(self["HdsEcranNegruActions"])
		# evStart la fiecare pornire, si a aceluiasi canal (trezirea din standby, intoarcerea din MoviePlayer, dupa
		# cautare): __serviceStarted de mai jos cheama laStart numai cand se schimba referinta, iar urmaritorul ar
		# socoti secundele fara imagine de dinainte de oprire
		self.__hds_urmarire = ServiceEventTracker(screen=self, eventmap=
			{
				iPlayableService.evStart: leg.laStart,
				iPlayableService.evTunedIn: lambda: leg.laEveniment("evTunedIn"),
				iPlayableService.evUpdatedInfo: lambda: leg.laEveniment("evUpdatedInfo"),
				iPlayableService.evVideoSizeChanged: lambda: leg.laEveniment("evVideoSizeChanged"),
				iPlayableService.evEnd: lambda: leg.laEveniment("evEnd"),
			})

	def __hdsMesajPornit(self):
		if self.hdsEcranNegru is None:
			return False
		from Components import HdsEcranNegru
		return HdsEcranNegru.pornit()

	def __serviceStarted(self):
		# evStart poate porni din nou pentru ACELASI
		# serviciu (reincercari interne de acordare), nu doar la o schimbare reala de canal --
		# resetarea neconditionata a contorului insemna ca pragul de 3 incercari din __tuneFailed()
		# nu se atingea NICIODATA, mesajul placeholder "Se acordeaza..." aparea 3 secunde si apoi
		# disparea fara sa mai arate eroarea reala (regresie dintr-o reparatie mai veche; inainte
		# arata direct mesajul de eroare). Acum se reseteaza -- si RemovePopup ruleaza -- DOAR cand
		# referinta chiar s-a schimbat (zap real pe alt canal), nu la fiecare evStart pe acelasi
		# canal. Asta repara si suprascrierea prematura a mesajului real de eroare (RemovePopup nu
		# mai rulează in mijlocul unei reincercari pe acelasi canal).
		cur_ref = self.session.nav.getCurrentlyPlayingServiceReference()
		cur_ref_str = cur_ref and cur_ref.toString()
		if cur_ref_str == self.__retry_ref:
			return
		self.__retry_ref = cur_ref_str
		self.last_error = None
		self.__retry_count = 0
		Notifications.RemovePopup(id = "ZapError")
		if self.hdsEcranNegru is not None:
			self.hdsEcranNegru.laStart()

	def __tuneFailed(self):
		# cu mesajul de ecran negru pornit, eroarea apare pe mijlocul ecranului cat canalul ramane negru; radioul, PiP-ul
		# si serviciile care nu primesc verdict (HdsEcranNegru.analizeaza) nu au mesaj pe ecran, deci pentru ele ramane
		# fereastra scurta de eroare de mai jos
		if self.__hdsMesajPornit():
			Notifications.RemovePopup(id = "ZapError")
			self.hdsEcranNegru.laEveniment("evTuneFailed")
			if self.hdsEcranNegru.primesteVerdict():
				return
		try:
			if config.usage.hide_zap_errors.value:
				Notifications.RemovePopup(id = "ZapError")
				return
		except Exception:
			pass

		service = self.session.nav.getCurrentService()
		info = service and service.info()
		error = info and info.getInfo(iServiceInformation.sDVBState)

		self.__retry_count = getattr(self, "_InfoBarServiceErrorPopupSupport__retry_count", 0) + 1

		# Daca inca incearca acordarea (primele incercari), afisam mesaj prietenos
		if error == eDVBServicePMTHandler.eventTuneFailed and self.__retry_count < 3:
			Notifications.AddPopup(text = _("Se acordează... așteaptă"), type = MessageBox.TYPE_INFO, timeout = 3, id = "ZapError")
			return

		if error == self.last_error and self.__retry_count >= 3:
			error = None
		else:
			self.last_error = error

		# textele din Components/HdsEcranNegru.py (aceleasi ca mesajul de pe ecran si ca web-ul): intai fraza pe
		# intelesul oricui, apoi detaliul tehnic, mai mic, in fereastra cu asezarea mesajului (Screens/HdsEcranNegru.py,
		# HdsEcranNegruFereastra); fara ea, MessageBox cu acelasi text
		if error is not None:
			from Components import HdsEcranNegru
			fel = HdsEcranNegru.fel_din_info(info)
			verdict = HdsEcranNegru.verdict_eroare(HdsEcranNegru.eroare_acordare(error), fel, HdsEcranNegru.nume_din_info(info))
			if verdict is not None:
				try:
					from Screens.HdsEcranNegru import HdsEcranNegruFereastra
					Notifications.RemovePopup(id = "ZapError")
					Notifications.AddNotificationWithID("ZapError", HdsEcranNegruFereastra, verdict, 5)
					return
				except Exception as e:
					print("[InfoBarGenerics] fereastra de eroare: %s" % e)
			error = HdsEcranNegru.text_fereastra(verdict) or None

		if error is not None:
			Notifications.AddPopup(text = error, type = MessageBox.TYPE_ERROR, timeout = 5, id = "ZapError")
		else:
			Notifications.RemovePopup(id = "ZapError")

# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import NumberActionMap
from Components.config import config, getConfigListEntry, ConfigNothing, NoSave, ConfigPIN
from Components.ParentalControlList import ParentalControlEntryComponent, ParentalControlList 

from Components.Sources.StaticText import StaticText
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.InputBox import PinInput
from Screens.ChannelSelection import service_types_tv
from Tools.BoundFunction import boundFunction
from enigma import eServiceCenter, eTimer, eServiceReference
from operator import itemgetter
# HDSatelit: regulile ecranului (ce randuri se vad, cand cere PIN-ul, cand lipseste un PIN) stau in
# Components/HdsControlParental.py, aceleasi pentru acest ecran si pentru pagina web /control-parental
# (Plugins/Extensions/HdsWebControl/parental_web.py).
from Components import HdsControlParental

class ProtectedScreen:
	def __init__(self):
		if self.isProtected():
			self.onFirstExecBegin.append(boundFunction(self.session.openWithCallback, self.pinEntered, PinInput, pinList = [self.protectedWithPin()], triesEntry = self.getTriesEntry(), title = self.getPinText(), windowTitle = _("Enter pin code")))

	def getTriesEntry(self):
		return config.ParentalControl.retries.setuppin

	def getPinText(self):
		return _("Please enter the correct pin code")

	def isProtected(self):
		return True

	def protectedWithPin(self):
		return config.ParentalControl.setuppin.value

	def pinEntered(self, result):
		if result is None:
			self.close()
		elif not result:
			self.session.openWithCallback(self.close, MessageBox, _("The pin code you entered is wrong."), MessageBox.TYPE_ERROR)

class ParentalControlSetup(Screen, ConfigListScreen, ProtectedScreen):
	def __init__(self, session):
		Screen.__init__(self, session)
		ProtectedScreen.__init__(self)
		# for the skin: first try ParentalControlSetup, then Setup, this allows individual skinning
		self.skinName = ["ParentalControlSetup", "Setup" ]
		self.setup_title = _("Parental control setup")
		self.onChangedEntry = [ ]

		self.list = []
		ConfigListScreen.__init__(self, self.list, session = self.session, on_change = self.changedEntry)
		self.createSetup()
		
		# HDSatelit: ROSU ("Anulare") si EXIT (cancel) anuleaza, VERDE (save) salveaza; inainte toate trei salvau
		self["actions"] = NumberActionMap(["SetupActions"],
		{
		  "cancel": self.keyCancel,
		  "save": self.keySave
		}, -2)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(self.setup_title)

	def isProtected(self):
		return HdsControlParental.protejat(config.ParentalControl)
	
	def createSetup(self):
		self.editListEntry = None
		self.changePin = None
		self.changeSetupPin = None
		self.editBouquetListEntry = -1
		self.reloadLists = -1
		c = config.ParentalControl
		print("config.ParentalControl.configured.value", c.configured.value)

		self.list = []
		# randurile care se vad, in ordinea lor (HdsControlParental.randuri); "Configuration mode" ramane ascuns
		for cheie in HdsControlParental.randuri(c):
			if cheie == "configured":
				self.list.append(getConfigListEntry(_("Enable parental control"), c.configured))
			elif cheie == "setuppinactive":
				self.list.append(getConfigListEntry(_("Protect setup"), c.setuppinactive))
			elif cheie == "pin_setari":
				self.changeSetupPin = getConfigListEntry(_("Change setup PIN"), NoSave(ConfigNothing()))
				self.list.append(self.changeSetupPin)
			elif cheie == "servicepinactive":
				self.list.append(getConfigListEntry(_("Protect services"), c.servicepinactive))
			elif cheie == "type":
				self.list.append(getConfigListEntry(_("Parental control type"), c.type))
			elif cheie == "pin_canale":
				if c.mode.value == "complex":
					self.changePin = getConfigListEntry(_("Change service PINs"), NoSave(ConfigNothing()))
					self.list.append(self.changePin)
				elif c.mode.value == "simple":
					self.changePin = getConfigListEntry(_("Change service PIN"), NoSave(ConfigNothing()))
					self.list.append(self.changePin)
			elif cheie == "storeservicepin":
				#Added Option to remember the service pin
				self.list.append(getConfigListEntry(_("Remember service PIN"), c.storeservicepin))
			elif cheie == "storeservicepincancel":
				#Added Option to remember the cancellation of service pin entry
				self.list.append(getConfigListEntry(_("Remember service PIN cancel"), c.storeservicepincancel))
			elif cheie == "lista_canale":
				self.editListEntry = getConfigListEntry(_("Edit services list"), NoSave(ConfigNothing()))
				self.list.append(self.editListEntry)
			elif cheie == "lista_buchete":
				#New funtion: Possibility to add Bouquets to whitelist / blacklist
				self.editBouquetListEntry = getConfigListEntry(_("Edit bouquets list"), NoSave(ConfigNothing()))
				self.list.append(self.editBouquetListEntry)
			elif cheie == "reincarca":
				#New option to reload service lists (for example if bouquets have changed)
				self.reloadLists = getConfigListEntry(_("Reload Black-/Whitelists"), NoSave(ConfigNothing()))
				self.list.append(self.reloadLists)

		self["config"].list = self.list
		self["config"].setList(self.list)

	def keyOK(self):
		print("self[\"config\"].l.getCurrentSelection()", self["config"].l.getCurrentSelection())
		if self["config"].l.getCurrentSelection() == self.editListEntry:
			self.session.open(ParentalControlEditor)
		elif self["config"].l.getCurrentSelection() == self.editBouquetListEntry:
			self.session.open(ParentalControlBouquetEditor)
		elif self["config"].l.getCurrentSelection() == self.changePin:
			if config.ParentalControl.mode.value == "complex":
				pass
			else:
				self.session.open(ParentalControlChangePin, config.ParentalControl.servicepin[0], _("service PIN"))
		elif self["config"].l.getCurrentSelection() == self.changeSetupPin:
			self.session.open(ParentalControlChangePin, config.ParentalControl.setuppin, _("setup PIN"))
		elif self["config"].l.getCurrentSelection() == self.reloadLists:
			from Components.ParentalControl import parentalControl
			parentalControl.open()
		else:
			ConfigListScreen.keyRight(self)
			print("current selection:", self["config"].l.getCurrentSelection())
			self.createSetup()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		print("current selection:", self["config"].l.getCurrentSelection())
		self.createSetup()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		print("current selection:", self["config"].l.getCurrentSelection())
		self.createSetup()

	def SetupPinMessageCallback(self, value):
		if value:
			self.session.openWithCallback(self.cancelCB, ParentalControlChangePin, config.ParentalControl.setuppin, _("setup PIN"))
		else:
			config.ParentalControl.setuppinactive.value = False
			self.keySave()

	def ServicePinMessageCallback(self, value):
		if value:
			self.session.openWithCallback(self.cancelCB, ParentalControlChangePin, config.ParentalControl.servicepin[0], _("service PIN"))
		else:
			config.ParentalControl.servicepinactive.value = False
			self.keySave()

	def cancelCB(self,value):
		self.keySave()

	# randurile ecranului care tin o setare (si cele ascunse intre timp de "Enable parental control")
	RANDURI_SETARI = ("configured", "setuppinactive", "servicepinactive", "type", "storeservicepin",
		"storeservicepincancel", "mode")

	def keyCancel(self):
		"""ROSU si EXIT: setarile ecranului se intorc la cele salvate. PIN-urile se schimba (si se salveaza) in ecranul
		lor, cu OK acolo."""
		for nume in self.RANDURI_SETARI:
			element = getattr(config.ParentalControl, nume, None)
			if element is not None and hasattr(element, "cancel"):
				element.cancel()
		for x in self["config"].list:
			x[1].cancel()
		self.close()

	def keySave(self):
		if config.ParentalControl.setuppinactive.value and HdsControlParental.pinLipsa(config.ParentalControl, "setuppinactive"):
			self.session.openWithCallback(self.SetupPinMessageCallback, MessageBox, _("No valid setup PIN found!\nDo you like to change the setup PIN now?\nWhen you say 'No' here the setup protection stay disabled!"), MessageBox.TYPE_YESNO)
		elif config.ParentalControl.servicepinactive.value and HdsControlParental.pinLipsa(config.ParentalControl, "servicepinactive"):
			self.session.openWithCallback(self.ServicePinMessageCallback, MessageBox, _("No valid service PIN found!\nDo you like to change the service PIN now?\nWhen you say 'No' here the service protection stay disabled!"), MessageBox.TYPE_YESNO)
		else:
			for x in self["config"].list:
				x[1].save()
			self.close()

	def keyNumberGlobal(self, number):
		pass

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

SPECIAL_CHAR = 96
class ParentalControlEditor(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.list = []
		self.servicelist = ParentalControlList(self.list)
		self["servicelist"] = self.servicelist;
		#self.onShown.append(self.chooseLetter)
		self.currentLetter = chr(SPECIAL_CHAR)
		self.readServiceList()
		self.chooseLetterTimer = eTimer()
		self.chooseLetterTimer.callback.append(self.chooseLetter)
		self.onLayoutFinish.append(self.LayoutFinished)

		self["actions"] = NumberActionMap(["DirectionActions", "ColorActions", "OkCancelActions", "NumberActions"],
		{
			"ok": self.select,
			"cancel": self.cancel,
			#"left": self.keyLeft,
			#"right": self.keyRight,
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
		}, -1)

	def LayoutFinished(self):
		self.chooseLetterTimer.start(0, True)

	def cancel(self):
		self.chooseLetter()

	def select(self):
		self.servicelist.toggleSelectedLock()

	def keyNumberGlobal(self, number):
		pass

	def readServiceList(self):
		serviceHandler = eServiceCenter.getInstance()
		refstr = '%s ORDER BY name' % (service_types_tv)
		self.root = eServiceReference(refstr)
		self.servicesList = {}
		list = serviceHandler.list(self.root)
		if list is not None:
			services = list.getContent("CN", True) #(servicecomparestring, name)
			for s in services:
				key = s[1].lower()[0]
				if key < 'a' or key > 'z':
					key = chr(SPECIAL_CHAR)
				#key = str(key)
				if key not in self.servicesList:
					self.servicesList[key] = []
				self.servicesList[key].append(s)
			
	def chooseLetter(self):
		print("choose letter")
		mylist = []
		for x in list(self.servicesList.keys()):
			if x == chr(SPECIAL_CHAR):
				x = (_("special characters"), x)
			else:
				x = (x, x)
			mylist.append(x)
		mylist.sort(key=itemgetter(1))
		sel = ord(self.currentLetter) - SPECIAL_CHAR
		self.session.openWithCallback(self.letterChosen, ChoiceBox, title=_("Show services beginning with"), list=mylist, keys = [], selection = sel)

	def letterChosen(self, result):
		from Components.ParentalControl import parentalControl
		if result is not None:
			print("result:", result)
			self.currentLetter = result[1]
			#Replace getProtectionLevel by new getProtectionType
			self.list = [ParentalControlEntryComponent(x[0], x[1], parentalControl.getProtectionType(x[0])) for x in self.servicesList[result[1]]]
			self.servicelist.setList(self.list)
		else:
			parentalControl.save()
			self.close()

class ParentalControlBouquetEditor(Screen):
	#This new class allows adding complete bouquets to black- and whitelists
	#The servicereference that is stored for bouquets is their refstr as listed in bouquets.tv
	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = "ParentalControlEditor"
		self.list = []
		self.bouquetslist = ParentalControlList(self.list)
		self["servicelist"] = self.bouquetslist;
		self.readBouquetList()
		self.onLayoutFinish.append(self.selectBouquet)

		self["actions"] = NumberActionMap(["DirectionActions", "ColorActions", "OkCancelActions"],
		{
			"ok": self.select,
			"cancel": self.cancel
		}, -1)

	def cancel(self):
		from Components.ParentalControl import parentalControl
		parentalControl.save()
		self.close()

	def select(self):
		self.bouquetslist.toggleSelectedLock()

	def readBouquetList(self):
		serviceHandler = eServiceCenter.getInstance()
		refstr = '1:134:1:0:0:0:0:0:0:0:FROM BOUQUET \"bouquets.tv\" ORDER BY bouquet'
		bouquetroot = eServiceReference(refstr)
		self.bouquetlist = {}
		list = serviceHandler.list(bouquetroot)
		if list is not None:
			self.bouquetlist = list.getContent("CN", True)
	
	def selectBouquet(self):
		from Components.ParentalControl import parentalControl
		self.list = [ParentalControlEntryComponent(x[0], x[1], parentalControl.getProtectionType(x[0])) for x in self.bouquetlist]
		self.bouquetslist.setList(self.list)

class ParentalControlChangePin(Screen, ConfigListScreen, ProtectedScreen):
	def __init__(self, session, pin, pinname):
		Screen.__init__(self, session)
		# for the skin: first try ParentalControlChangePin, then Setup, this allows individual skinning
		self.skinName = ["ParentalControlChangePin", "Setup" ]
		self.setup_title = _("Change pin code")
		self.onChangedEntry = [ ]

		self.pin = pin
		self.list = []
		self.pin1 = ConfigPIN(default = 1111, censor = "*")
		self.pin2 = ConfigPIN(default = 1112, censor = "*")
		self.pin1.addEndNotifier(boundFunction(self.valueChanged, 1))
		self.pin2.addEndNotifier(boundFunction(self.valueChanged, 2))
		self.list.append(getConfigListEntry(_("New PIN"), NoSave(self.pin1)))
		self.list.append(getConfigListEntry(_("Reenter new PIN"), NoSave(self.pin2)))
		ConfigListScreen.__init__(self, self.list)
#		print "old pin:", pin
		#if pin.value != "aaaa":
			#self.onFirstExecBegin.append(boundFunction(self.session.openWithCallback, self.pinEntered, PinInput, pinList = [self.pin.value], title = _("please enter the old pin"), windowTitle = _("Change pin code")))
		ProtectedScreen.__init__(self)
		
		self["actions"] = NumberActionMap(["DirectionActions", "ColorActions", "OkCancelActions"],
		{
			"cancel": self.cancel,
			"red": self.cancel,
			"save": self.keyOK,
		}, -1)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(self.setup_title)

	def valueChanged(self, pin, value):
		if pin == 1:
			self["config"].setCurrentIndex(1)
		elif pin == 2:
			self.keyOK()

	def getPinText(self):
		return _("Please enter the old PIN code")

	def isProtected(self):
		return HdsControlParental.pinSetat(self.pin)

	def protectedWithPin(self):
		return self.pin.value

#	def pinEntered(self, result):
		#if result[0] is None:
			#self.close()
		#if not result[0]:
			#print result, "-", self.pin.value
			#self.session.openWithCallback(self.close, MessageBox, _("The pin code you entered is wrong."), MessageBox.TYPE_ERROR)

	def keyOK(self):
		if self.pin1.value == self.pin2.value:
			self.pin.value = self.pin1.value
			self.pin.save()
			self.session.openWithCallback(self.close, MessageBox, _("The PIN code has been changed successfully."), MessageBox.TYPE_INFO)
		else:
			self.session.open(MessageBox, _("The PIN codes you entered are different."), MessageBox.TYPE_ERROR)

	def cancel(self):
		self.close(None)

	def keyNumberGlobal(self, number):
		ConfigListScreen.keyNumberGlobal(self, number)

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

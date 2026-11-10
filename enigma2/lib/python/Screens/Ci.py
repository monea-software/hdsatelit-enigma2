# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ActionMap import NumberActionMap
from Components.Label import Label

from Components.config import config, ConfigSubsection, ConfigSelection, ConfigSubList, getConfigListEntry, KEY_LEFT, KEY_RIGHT, KEY_0, ConfigNothing, ConfigPIN
from Components.ConfigList import ConfigList

from Components.SystemInfo import SystemInfo

from enigma import eTimer, eDVBCI_UI, eDVBCIInterfaces

MAX_NUM_CI = 4

def setCIBitrate(configElement):
	if configElement.value == "no":
		eDVBCI_UI.getInstance().setClockRate(configElement.slotid, eDVBCI_UI.rateNormal)
	else:
		eDVBCI_UI.getInstance().setClockRate(configElement.slotid, eDVBCI_UI.rateHigh)

def InitCiConfig():
	config.ci = ConfigSubList()
	for slot in range(MAX_NUM_CI):
		config.ci.append(ConfigSubsection())
		config.ci[slot].canDescrambleMultipleServices = ConfigSelection(choices = [("auto", _("Auto")), ("no", _("No")), ("yes", _("Yes"))], default = "auto")
		if SystemInfo["CommonInterfaceSupportsHighBitrates"]:
			config.ci[slot].canHandleHighBitrates = ConfigSelection(choices = [("no", _("No")), ("yes", _("Yes"))], default = "no")
			config.ci[slot].canHandleHighBitrates.slotid = slot
			config.ci[slot].canHandleHighBitrates.addNotifier(setCIBitrate)

def _pasiDecriptare(slot, screen):
	"""Mesajul modulului ajunge si in pasii decriptarii (Components/HdsPasiDecriptare.py), numai cu setarea lor
	pornita. enigma2 da ecranul MMI o singura data (getMMIScreen), deci il primesc de aici, nu il cer a doua oara."""
	try:
		from Components import HdsPasiDecriptare
		HdsPasiDecriptare.mesaj_ci(slot, screen)
	except Exception as e:
		print("[Ci] pasii decriptarii: %s" % e)

class MMIDialog(Screen):
	def __init__(self, session, slotid, action, handler = eDVBCI_UI.getInstance(), wait_text = _("wait for ci...") ):
		Screen.__init__(self, session)

		print("MMIDialog with action" + str(action))

		self.mmiclosed = False
		self.tag = None
		self.slotid = slotid

		self.timer = eTimer()
		self.timer.callback.append(self.keyCancel)

		#else the skins fails
		self["title"] = Label("")
		self["subtitle"] = Label("")
		self["bottom"] = Label("")
		self["entries"] = ConfigList([ ])

		self["actions"] = NumberActionMap(["SetupActions"],
			{
				"ok": self.okbuttonClick,
				"cancel": self.keyCancel,
				#for PIN
				"left": self.keyLeft,
				"right": self.keyRight,
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

		self.action = action

		self.handler = handler
		self.wait_text = wait_text

		if action == 2:		#start MMI
			handler.startMMI(self.slotid)
			self.showWait()
		elif action == 3:		#mmi already there (called from infobar)
			self.showScreen()

	def addEntry(self, list, entry):
		if entry[0] == "TEXT":		#handle every item (text / pin only?)
			list.append( (entry[1], ConfigNothing(), entry[2]) )
		if entry[0] == "PIN":
			pinlength = entry[1]
			if entry[3] == 1:
				# masked pins:
				x = ConfigPIN(0, len = pinlength)  # PIN-ul se vede cat il scrii
			else:
				# unmasked pins:
				x = ConfigPIN(0, len = pinlength)
			self["subtitle"].setText(entry[2])
			list.append( getConfigListEntry("", x) )
			self["bottom"].setText(_("please press OK when ready"))

	def okbuttonClick(self):
		self.timer.stop()
		if not self.tag:
			return
		if self.tag == "WAIT":
			print("do nothing - wait")
		elif self.tag == "MENU":
			print("answer MENU")
			cur = self["entries"].getCurrent()
			if cur:
				self.handler.answerMenu(self.slotid, cur[2])
			else:
				self.handler.answerMenu(self.slotid, 0)
			self.showWait()
		elif self.tag == "LIST":
			print("answer LIST")
			self.handler.answerMenu(self.slotid, 0)
			self.showWait()
		elif self.tag == "ENQ":
			cur = self["entries"].getCurrent()
			answer = str(cur[1].value)
			length = len(answer)
			while length < cur[1].getLength():
				answer = '0'+answer
				length+=1
			self.handler.answerEnq(self.slotid, answer)
			self.showWait()

	def closeMmi(self):
		self.timer.stop()
		self.close(self.slotid)

	def keyCancel(self):
		self.timer.stop()
		if not self.tag or self.mmiclosed:
			self.closeMmi()
		elif self.tag == "WAIT":
			self.handler.stopMMI(self.slotid)
			self.closeMmi()
		elif self.tag in ( "MENU", "LIST" ):
			print("cancel list")
			self.handler.answerMenu(self.slotid, 0)
			self.showWait()
		elif self.tag == "ENQ":
			print("cancel enq")
			self.handler.cancelEnq(self.slotid)
			self.showWait()
		else:
			print("give cancel action to ci")

	def keyConfigEntry(self, key):
		self.timer.stop()
		try:
			self["entries"].handleKey(key)
		except:
			pass

	def keyNumberGlobal(self, number):
		self.timer.stop()
		self.keyConfigEntry(KEY_0 + number)

	def keyLeft(self):
		self.timer.stop()
		self.keyConfigEntry(KEY_LEFT)

	def keyRight(self):
		self.timer.stop()
		self.keyConfigEntry(KEY_RIGHT)

	def updateList(self, list):
		List = self["entries"]
		try:
			List.instance.moveSelectionTo(0)
		except:
			pass
		List.l.setList(list)

	def showWait(self):
		self.tag = "WAIT"
		self["title"].setText("")
		self["subtitle"].setText("")
		self["bottom"].setText("")
		list = [ ]
		list.append( (self.wait_text, ConfigNothing()) )
		self.updateList(list)

	def showScreen(self):
		screen = self.handler.getMMIScreen(self.slotid)
		_pasiDecriptare(self.slotid, screen)

		list = [ ]

		self.timer.stop()
		if len(screen) > 0 and screen[0][0] == "CLOSE":
			timeout = screen[0][1]
			self.mmiclosed = True
			if timeout > 0:
				self.timer.start(timeout*1000, True)
			else:
				self.keyCancel()
		else:
			self.mmiclosed = False
			self.tag = screen[0][0]
			for entry in screen:
				if entry[0] == "PIN":
					self.addEntry(list, entry)
				else:
					if entry[0] == "TITLE":
						self["title"].setText(entry[1])
					elif entry[0] == "SUBTITLE":
						self["subtitle"].setText(entry[1])
					elif entry[0] == "BOTTOM":
						self["bottom"].setText(entry[1])
					elif entry[0] == "TEXT":
						self.addEntry(list, entry)
			self.updateList(list)

	def ciStateChanged(self):
		do_close = False
		if self.action == 0:			#reset
			do_close = True
		if self.action == 1:			#init
			do_close = True

		#module still there ?
		if self.handler.getState(self.slotid) != 2:
			do_close = True

		#mmi session still active ?
		if self.handler.getMMIState(self.slotid) != 1:
			do_close = True

		if do_close:
			self.closeMmi()
		elif self.action > 1 and self.handler.availableMMI(self.slotid) == 1:
			self.showScreen()

		#FIXME: check for mmi-session closed

class CiMessageHandler:
	def __init__(self):
		self.session = None
		self.ci = { }
		self.dlgs = { }
		eDVBCI_UI.getInstance().ciStateChanged.get().append(self.ciStateChanged)
		SystemInfo["CommonInterface"] = eDVBCIInterfaces.getInstance().getNumOfSlots() > 0
		try:
			file = open("/proc/stb/tsmux/ci0_tsclk", "r")
			file.close()
			SystemInfo["CommonInterfaceSupportsHighBitrates"] = True
		except:
			SystemInfo["CommonInterfaceSupportsHighBitrates"] = False

	def setSession(self, session):
		self.session = session

	def ciStateChanged(self, slot):
		if slot in self.ci:
			self.ci[slot](slot)
		else:
			if slot in self.dlgs:
				self.dlgs[slot].ciStateChanged()
			elif eDVBCI_UI.getInstance().availableMMI(slot) == 1:
				if self.session:
					self.dlgs[slot] = self.session.openWithCallback(self.dlgClosed, MMIDialog, slot, 3)

	def dlgClosed(self, slot):
		if slot in self.dlgs:
			del self.dlgs[slot]

	def registerCIMessageHandler(self, slot, func):
		self.unregisterCIMessageHandler(slot)
		self.ci[slot] = func

	def unregisterCIMessageHandler(self, slot):
		if slot in self.ci:
			del self.ci[slot]

CiHandler = CiMessageHandler()

class CiSelection(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self["actions"] = ActionMap(["OkCancelActions", "CiSelectionActions"],
			{
				"left": self.keyLeft,
				"right": self.keyLeft,
				"ok": self.okbuttonClick,
				"cancel": self.cancel
			},-1)

		self.dlg = None
		self.state = { }
		self.list = [ ]

		for slot in range(MAX_NUM_CI):
			state = eDVBCI_UI.getInstance().getState(slot)
			if state != -1:
				self.appendEntries(slot, state)
				CiHandler.registerCIMessageHandler(slot, self.ciStateChanged)

		menuList = ConfigList(self.list)
		menuList.list = self.list
		menuList.l.setList(self.list)
		self["entries"] = menuList
		self["entries"].onSelectionChanged.append(self.selectionChanged)
		self["text"] = Label(_("Slot %d")%(1))

	def selectionChanged(self):
		cur = self["entries"].getCurrent()
		if cur and len(cur) > 3:
			self["text"].setText(_("Slot %d") % (cur[3] + 1))

	def keyConfigEntry(self, key):
		try:
			self["entries"].handleKey(key)
			self["entries"].getCurrent()[1].save()
		except:
			pass

	def keyLeft(self):
		self.keyConfigEntry(KEY_LEFT)

	def keyRight(self):
		self.keyConfigEntry(KEY_RIGHT)

	def appendEntries(self, slot, state):
		self.state[slot] = state
		self.list.append( (_("Reset"), ConfigNothing(), 0, slot) )
		self.list.append( (_("Init"), ConfigNothing(), 1, slot) )

		if self.state[slot] == 0:			#no module
			self.list.append( (_("no module found"), ConfigNothing(), 2, slot) )
		elif self.state[slot] == 1:		#module in init
			self.list.append( (_("init module"), ConfigNothing(), 2, slot) )
		elif self.state[slot] == 2:		#module ready
			#get appname
			appname = eDVBCI_UI.getInstance().getAppName(slot)
			self.list.append( (appname, ConfigNothing(), 2, slot) )
			self.list.append((_("Alocă canale modulului"), ConfigNothing(), "alocare", slot))

		self.list.append((_("Multiple service support"), config.ci[slot].canDescrambleMultipleServices, None, slot))
		if SystemInfo["CommonInterfaceSupportsHighBitrates"]:
			self.list.append((_("High bitrate support"), config.ci[slot].canHandleHighBitrates, None, slot))

	def updateState(self, slot):
		lst = self["entries"]
		index = lst.getCurrentIndex()
		self.list = []
		for numar in range(MAX_NUM_CI):
			state = eDVBCI_UI.getInstance().getState(numar)
			if state != -1:
				self.appendEntries(numar, state)
		lst.list = self.list
		lst.l.setList(self.list)
		if getattr(lst, "instance", None) is not None:
			lst.instance.moveSelectionTo(min(index, max(0, len(self.list) - 1)))
		self.selectionChanged()

	def ciStateChanged(self, slot):
		if self.dlg:
			self.dlg.ciStateChanged()
		else:
			state = eDVBCI_UI.getInstance().getState(slot)
			if self.state[slot] != state:
				#print "something happens"
				self.state[slot] = state
				self.updateState(slot)

	def dlgClosed(self, slot):
		self.dlg = None

	def okbuttonClick(self):
		cur = self["entries"].getCurrent()
		if cur and len(cur) > 2:
			action = cur[2]
			slot = cur[3]
			if action == 0:		#reset
				eDVBCI_UI.getInstance().setReset(slot)
			elif action == 1:		#init
				eDVBCI_UI.getInstance().setInit(slot)
			elif action == "alocare" and eDVBCI_UI.getInstance().getState(slot) == 2:
				self.session.open(CiAssignment, slot)
			elif action == 2 and self.state[slot] == 2:
				self.dlg = self.session.openWithCallback(self.dlgClosed, MMIDialog, slot, action)

	def cancel(self):
		for slot in range(MAX_NUM_CI):
			state = eDVBCI_UI.getInstance().getState(slot)
			if state != -1:
				CiHandler.unregisterCIMessageHandler(slot)
		self.close()


class CiAssignment(Screen):
	skin = """<screen name="CiAssignment" position="center,center" size="950,590" title="Common Interface">
		<widget name="entries" position="20,20" size="910,440" scrollbarMode="showOnDemand" />
		<widget name="text" position="20,465" size="910,50" font="Regular;21" />
		<widget name="key_red" position="20,540" size="210,30" font="Regular;22" foregroundColor="#ff5555" />
		<widget name="key_green" position="250,540" size="210,30" font="Regular;22" foregroundColor="#55ff55" />
		<widget name="key_yellow" position="480,540" size="210,30" font="Regular;22" foregroundColor="#ffff55" />
	</screen>"""

	def __init__(self, session, slot):
		Screen.__init__(self, session)
		from Tools import CIHelper
		self.helper = CIHelper
		self.slot = slot
		self.setTitle(_("Alocă canale modulului") + " - " + (_("Slot %d") % (slot + 1)))
		self["entries"] = ConfigList([])
		self["text"] = Label(_("Verde salvează alocările. Decodările multiple se schimbă în setările slotului."))
		self["key_red"] = Label(_("Închide"))
		self["key_green"] = Label(_("Save"))
		self["key_yellow"] = Label(_("Delete"))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.alege, "cancel": self.close, "red": self.close,
			"green": self.salveaza, "yellow": self.sterge,
			"left": lambda: self.schimba(KEY_LEFT), "right": lambda: self.schimba(KEY_RIGHT)}, -1)
		self.revizie = None
		self.neaplicata = False
		self.schimbata = False
		try:
			stare = CIHelper.citesteEditor(slot)
			self.reguli, self.revizie = stare["reguli"], stare["revizie"]
			self.neaplicata = stare["neaplicata"]
			if self.neaplicata:
				self.arataNeaplicata()
		except Exception:
			self.reguli = None
			self["text"].setText(_("Alocările CI nu se pot citi. Fișierul existent a fost păstrat."))
		self.refa()

	def refa(self):
		lista = []
		if self.reguli is not None:
			lista = [(_("Adaugă canal"), ConfigNothing(), "canal"),
				(_("Adaugă furnizor"), ConfigNothing(), "furnizor"),
				(_("Adaugă CAID"), ConfigNothing(), "caid")]
			for fel, eticheta in (("servicii", _("Channel")), ("furnizori", _("Provider")), ("caid", "CAID")):
				for index, valoare in enumerate(self.reguli[fel]):
					text = "%04X" % valoare if fel == "caid" else valoare["name"]
					if fel == "furnizori":
						text += " [%08X]" % valoare["namespace"]
					lista.append((eticheta + ": " + text, ConfigNothing(), fel, index))
		self["entries"].list = lista
		self["entries"].l.setList(lista)

	def schimba(self, tasta):
		self["entries"].handleKey(tasta)

	def alege(self):
		cur = self["entries"].getCurrent()
		if not cur or len(cur) < 3:
			return
		if cur[2] == "canal":
			from Screens.ChannelSelection import SimpleChannelSelection
			self.session.openWithCallback(self.canalAles, SimpleChannelSelection, _("Adaugă canal"))
		elif cur[2] == "furnizor":
			from Screens.ChannelSelection import SimpleChannelSelection
			class AlegeFurnizor(SimpleChannelSelection):
				def __init__(self, session, title):
					SimpleChannelSelection.__init__(self, session, title)
					self.skinName = ["HdsListaCanaleSimpla", "SimpleChannelSelection"]
					self.hdsPornesteCapul()

				def layoutFinished(self):
					self.setTvMode()
					self.showProviders()

				def setModeTv(self):
					self.setTvMode()
					self.showProviders()

				def setModeRadio(self):
					self.setRadioMode()
					self.showProviders()

				def channelSelected(self):
					ref = self.getCurrentSelection()
					if ref is None or not ref.valid():
						return
					if 'provider ==' in ref.getPath():
						self.close(ref)
					else:
						SimpleChannelSelection.channelSelected(self)
			self.session.openWithCallback(self.furnizorAles, AlegeFurnizor, _("Adaugă furnizor"))
		elif cur[2] == "caid":
			from Screens.ChoiceBox import ChoiceBox
			try:
				cunoscute = self.helper.caidCunoscute(self.slot)
			except Exception:
				cunoscute = []
			if not cunoscute:
				self.caidAles((None, None))
				return
			lista = [("%04X - %s" % (c["caid"], c["name"]) if c["name"] else "%04X" % c["caid"], c["caid"]) for c in cunoscute]
			lista.append((_("Scrie CAID (hexazecimal)"), None))
			self.session.openWithCallback(self.caidAles, ChoiceBox, title=_("Adaugă CAID"), list=lista)

	def canalAles(self, ref):
		if ref is None:
			return
		from ServiceReference import ServiceReference
		try:
			self.adauga("servicii", {"ref": ref.toString(), "name": ServiceReference(ref).getServiceName() or ref.toString()})
		except ValueError:
			self.eroare(_("Alege un canal DVB pentru modulul CI."))

	def furnizorAles(self, ref):
		if ref is None:
			return
		from enigma import eServiceCenter, iServiceInformation
		centru = eServiceCenter.getInstance()
		lista = centru.list(ref)
		if lista is None:
			return
		try:
			while True:
				canal = lista.getNext()
				if not canal.valid():
					break
				info = centru.info(canal)
				nume = info.getInfoString(canal, iServiceInformation.sProvider) if info is not None else ""
				if nume:
					self.adauga("furnizori", {"name": nume, "namespace": canal.getUnsignedData(4)})
		except ValueError:
			self.eroare(_("Lista de alocări CI este plină sau conține date nevalide."))

	def caidAles(self, alegere):
		if alegere is None:
			return
		if alegere[1] is not None:
			try:
				self.adauga("caid", alegere[1])
			except ValueError:
				self.eroare(_("Lista de alocări CI este plină sau conține date nevalide."))
		else:
			from Screens.InputBox import InputBox
			self.session.openWithCallback(self.caidScris, InputBox, title=_("Scrie CAID (hexazecimal)"), text="", maxSize=6)

	def caidScris(self, text):
		if text is None:
			return
		try:
			self.adauga("caid", self.helper.caidDinText(text))
		except ValueError:
			self.eroare(_("CAID nevalid. Folosește 1-4 cifre hexazecimale, de exemplu 0B00."))

	def adauga(self, fel, valoare):
		reguli = {k: list(v) for k, v in self.reguli.items()}
		reguli[fel].append(valoare)
		self.reguli = self.helper.valideazaAlocarea(reguli)
		self.marcheazaCiorna()
		self.refa()

	def sterge(self):
		cur = self["entries"].getCurrent()
		if cur and len(cur) > 3 and cur[2] in self.reguli:
			del self.reguli[cur[2]][cur[3]]
			self.marcheazaCiorna()
			self.refa()

	def marcheazaCiorna(self):
		self.schimbata = True
		self["key_green"].setText(_("Save"))
		self["text"].setText(_("Verde salvează ciorna. Închide renunță numai la modificările nesalvate."))

	def arataNeaplicata(self):
		self["key_green"].setText(_("Reîncearcă"))
		self["text"].setText(_("Salvat, neaplicat. Verde reîncearcă aplicarea. Închide păstrează salvarea."))

	def eroare(self, text):
		from Screens.MessageBox import MessageBox
		self.session.open(MessageBox, text, MessageBox.TYPE_ERROR)

	def salveaza(self):
		if self.reguli is None:
			return
		if eDVBCI_UI.getInstance().getState(self.slot) != 2:
			self.eroare(_("Modulul CI nu mai este pregătit."))
			return
		try:
			if self.neaplicata and not self.schimbata:
				self.helper.reaplicaAlocarea(self.slot, self.revizie)
			else:
				self.helper.salveazaEditor(self.slot, self.reguli, self.revizie)
		except self.helper.AlocareSchimbata:
			self["text"].setText(_("Alocările CI s-au schimbat din alt ecran. Ciorna rămâne aici. Redeschide editorul pentru datele actuale."))
			return
		except self.helper.AlocareNeaplicata as eroare:
			self.revizie = eroare.revizie
			self.neaplicata, self.schimbata = True, False
			print("[Ci] aplicare alocari: %s" % eroare)
			self.arataNeaplicata()
			return
		except Exception as eroare:
			print("[Ci] salvare alocari: %s" % eroare)
			self.eroare(_("Alocările CI nu s-au putut aplica. Verifică modulul și încearcă din nou."))
			return
		self.close()

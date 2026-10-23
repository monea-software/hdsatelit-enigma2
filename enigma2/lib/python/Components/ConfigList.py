# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent
from .config import KEY_LEFT, KEY_RIGHT, KEY_HOME, KEY_END, KEY_0, KEY_DELETE, KEY_BACKSPACE, KEY_OK, KEY_TOGGLEOW, KEY_ASCII, KEY_TIMEOUT, KEY_NUMBERS, ConfigElement, ConfigText, ConfigPassword
from Components.ActionMap import NumberActionMap, ActionMap
from enigma import eListbox, eListboxPythonConfigContent, eRCInput, eTimer
from Screens.MessageBox import MessageBox


# HDSatelit: tastatura de pe ecran la orice camp de text. In orice ecran cu ConfigListScreen
# (Setup din setup.xml si ecranele care nu-si leaga singure OK), OK si tasta TEXT pe un camp de text (ConfigText,
# ConfigPassword; nu numerele si nu dosarele) deschid Screens/VirtualKeyBoard cu valoarea de acum (la parola goala:
# parola veche nu se arata, iar o parola goala lasa parola cum era). Scrierea cu cifrele, ca la SMS, ramane. Ecranele
# cu OK propriu cheama deschideTastatura(session, element, titlu, gata).

def esteTextDeScris(el):
	"""True pentru un camp de text care se scrie cu tastatura de pe ecran (ConfigText, ConfigPassword, ConfigSearchText),
	False pentru numere (ConfigNumber), dosare (ConfigDirectory) si restul."""
	clase = [c.__name__ for c in type(el).__mro__]
	if "ConfigNumber" in clase or "ConfigDirectory" in clase:
		return False
	return "ConfigText" in clase


def _dinTastatura():
	"""Ultima tasta a venit de la o tastatura adevarata (Components/HdsTastaturaUsb.py); fara modul, False."""
	try:
		from Components.HdsTastaturaUsb import dinTastatura
	except ImportError:
		return False
	return dinTastatura()


def deschideTastatura(session, el, titlu="", gata=None):
	"""Tastatura de pe ecran pentru campul `el`. La OK valoarea se pune si notificatorii setarii afla (changed); gata
	primeste textul (None la iesire fara schimbare). Fereastra cu literele cifrelor se ascunde cat e deschisa."""
	from Screens.VirtualKeyBoard import VirtualKeyBoard
	parola = "ConfigPassword" in [c.__name__ for c in type(el).__mro__]
	fereastra = getattr(el, "help_window", None)
	if fereastra is not None:
		try:
			fereastra.hide()
		except Exception:
			fereastra = None

	def laInchidere(text=None):
		if fereastra is not None:
			try:
				fereastra.show()
			except Exception:
				pass
		if text is not None and parola and not text:
			text = None              # parola goala: ramane parola de dinainte
		if text is not None:
			el.value = text
			try:
				el.marked_pos = len(el.text)
			except Exception:
				pass
			el.changed()
		if gata is not None:
			gata(text)
	return session.openWithCallback(laInchidere, VirtualKeyBoard, title=titlu, text="" if parola else (el.value or ""))


class ConfigList(HTMLComponent, GUIComponent, object):
	def __init__(self, list, session = None):
		GUIComponent.__init__(self)
		self.l = eListboxPythonConfigContent()
		self.l.setSeperation(200)
		self.timer = eTimer()
		self.list = list
		self.onSelectionChanged = [ ]
		self.current = None
		self.session = session

	def execBegin(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmAscii)
		self.timer.callback.append(self.timeout)

	def execEnd(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmNone)
		self.timer.callback.remove(self.timeout)

	def toggle(self):
		selection = self.getCurrent()
		selection[1].toggle()
		self.invalidateCurrent()

	def handleKey(self, key):
		selection = self.getCurrent()
		if selection and selection[1].enabled:
			selection[1].handleKey(key)
			self.invalidateCurrent()
			if key in KEY_NUMBERS:
				self.timer.start(1000, 1)

	def getCurrent(self):
		return self.l.getCurrentSelection()
	
	def getCurrentIndex(self):
		return self.l.getCurrentSelectionIndex()
	
	def setCurrentIndex(self, index):
		if self.instance is not None:
			self.instance.moveSelectionTo(index)
	
	def invalidateCurrent(self):
		self.l.invalidateEntry(self.l.getCurrentSelectionIndex())

	def invalidate(self, entry):
		# when the entry to invalidate does not exist, just ignore the request.
		# this eases up conditional setup screens a lot.
		if entry in self.__list:
			self.l.invalidateEntry(self.__list.index(entry))

	GUI_WIDGET = eListbox
	
	def selectionChanged(self):
		# randurile cu al treilea element (getConfigListEntry(text, config, cheie)) sunt tot setari: fara >= 2 ecranele
		# cu asemenea randuri nu aflau de mutarea cursorului (descrierea ramanea cea a primului rand)
		if isinstance(self.current,tuple) and len(self.current) >= 2:
			self.current[1].onDeselect(self.session)
		self.current = self.getCurrent()
		if isinstance(self.current,tuple) and len(self.current) >= 2:
			self.current[1].onSelect(self.session)
		else:
			return
		for x in self.onSelectionChanged:
			x()

	def postWidgetCreate(self, instance):
		instance.selectionChanged.get().append(self.selectionChanged)
		instance.setContent(self.l)
	
	def preWidgetRemove(self, instance):
		if isinstance(self.current,tuple) and len(self.current) >= 2:
			self.current[1].onDeselect(self.session)
		instance.selectionChanged.get().remove(self.selectionChanged)
		instance.setContent(None)

	def setList(self, l):
		self.timer.stop()
		self.__list = l
		self.l.setList(self.__list)

		if l is not None:
			for x in l:
				assert len(x) < 2 or isinstance(x[1], ConfigElement), "entry in ConfigList " + str(x[1]) + " must be a ConfigElement"

	def getList(self):
		return self.__list

	list = property(getList, setList)

	def timeout(self):
		self.handleKey(KEY_TIMEOUT)

	def isChanged(self):
		is_changed = False
		for x in self.list:
			is_changed |= x[1].isChanged()

		return is_changed

class ConfigListScreen:
	def __init__(self, list, session = None, on_change = None):
		self["config_actions"] = NumberActionMap(["SetupActions", "InputAsciiActions", "KeyboardInputActions"],
		{
			"gotAsciiCode": self.keyGotAscii,
			"ok": self.keyOK,
			"left": self.keyLeft,
			"right": self.keyRight,
			"home": self.keyHome,
			"end": self.keyEnd,
			"deleteForward": self.keyDelete,
			"deleteBackward": self.keyBackspace,
			"toggleOverwrite": self.keyToggleOW,
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
		}, -1) # to prevent left/right overriding the listbox

		self["VirtualKB"] = ActionMap(["VirtualKeyboardActions"],
		{
			"showVirtualKeyboard": self.KeyText,
		}, -2)
		self["VirtualKB"].setEnabled(False)
		
		self["config"] = ConfigList(list, session = session)
		
		if on_change is not None:
			self.__changed = on_change
		else:
			self.__changed = lambda: None
		
		if not self.handleInputHelpers in self["config"].onSelectionChanged:
			self["config"].onSelectionChanged.append(self.handleInputHelpers)

	def handleInputHelpers(self):
		cur = self["config"].getCurrent()
		# tasta TEXT deschide tastatura pe orice camp de text, si in ecranele fara iconita VKeyIcon (Setup)
		self["VirtualKB"].setEnabled(bool(cur is not None and len(cur) > 1 and esteTextDeScris(cur[1])))
		if self["config"].getCurrent() is not None:
			if isinstance(self["config"].getCurrent()[1], ConfigText) or isinstance(self["config"].getCurrent()[1], ConfigPassword):
				if "VKeyIcon" in self:
					self["VirtualKB"].setEnabled(True)
					self["VKeyIcon"].boolean = True
				if "HelpWindow" in self:
					if self["config"].getCurrent()[1].help_window.instance is not None:
						helpwindowpos = self["HelpWindow"].getPosition()
						from enigma import ePoint
						self["config"].getCurrent()[1].help_window.instance.move(ePoint(helpwindowpos[0],helpwindowpos[1]))
			else:
				if "VKeyIcon" in self:
					self["VirtualKB"].setEnabled(False)
					self["VKeyIcon"].boolean = False
		else:
			if "VKeyIcon" in self:
				self["VirtualKB"].setEnabled(False)
				self["VKeyIcon"].boolean = False

	def KeyText(self):
		cur = self["config"].getCurrent()
		if cur is None or len(cur) < 2 or not esteTextDeScris(cur[1]):
			return
		deschideTastatura(self.session, cur[1], cur[0], self._dupaTastatura)

	def _dupaTastatura(self, text=None):
		if text is not None:
			self["config"].invalidate(self["config"].getCurrent())
			self.__changed()

	def VirtualKeyBoardCallback(self, callback = None):
		if callback is not None and len(callback):
			self["config"].getCurrent()[1].setValue(callback)
			self["config"].invalidate(self["config"].getCurrent())
			
	def keyOK(self):
		cur = self["config"].getCurrent()
		if cur is not None and len(cur) > 1 and esteTextDeScris(cur[1]):
			# Enter de la o tastatura adevarata: textul se scrie direct in camp, fara tastatura de pe ecran
			# (Components/HdsTastaturaUsb.py); OK de pe telecomanda o deschide, ca inainte
			if _dinTastatura():
				self["config"].handleKey(KEY_OK)
				return
			self.KeyText()           # OK pe un camp de text: tastatura de pe ecran
			return
		self["config"].handleKey(KEY_OK)

	def keyLeft(self):
		self["config"].handleKey(KEY_LEFT)
		self.__changed()

	def keyRight(self):
		self["config"].handleKey(KEY_RIGHT)
		self.__changed()

	def keyHome(self):
		self["config"].handleKey(KEY_HOME)
		self.__changed()

	def keyEnd(self):
		self["config"].handleKey(KEY_END)
		self.__changed()

	def keyDelete(self):
		self["config"].handleKey(KEY_DELETE)
		self.__changed()

	def keyBackspace(self):
		self["config"].handleKey(KEY_BACKSPACE)
		self.__changed()

	def keyToggleOW(self):
		self["config"].handleKey(KEY_TOGGLEOW)
		self.__changed()

	def keyGotAscii(self):
		self["config"].handleKey(KEY_ASCII)
		self.__changed()

	def keyNumberGlobal(self, number):
		self["config"].handleKey(KEY_0 + number)
		self.__changed()
		
	def saveAll(self):
		for x in self["config"].list:
			x[1].save()

	# keySave and keyCancel are just provided in case you need them.
	# you have to call them by yourself.
	def keySave(self):
		self.saveAll()
		self.close()
	
	def cancelConfirm(self, result):
		if not result:
			return

		for x in self["config"].list:
			x[1].cancel()
		self.close()

	def keyCancel(self):
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"))
		else:
			self.close()

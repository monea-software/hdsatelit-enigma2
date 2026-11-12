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
	from Components.HdsAsistentaControl import campSecret
	secret = campSecret(el, titlu)
	fereastra = getattr(el, "help_window", None)
	if fereastra is not None:
		try:
			fereastra.hide()
		except Exception:
			fereastra = None

	def laInchidere(text=None):
		if text and secret:
			from Components.HdsAsistentaControl import cereOprirePentruSecret
			if cereOprirePentruSecret(session):
				text = None
		if fereastra is not None:
			try:
				fereastra.show()
			except Exception:
				pass
		if text is not None and parola and not text:
			text = None              # parola goala: ramane parola de dinainte
		if text is not None:
			el.value = text
			if parola:
				# parola scrisa acum: randul o arata in clar pana la salvare (Components/config.ConfigPassword)
				el.scrisa = True
			try:
				el.marked_pos = len(el.text)
			except Exception:
				pass
			el.changed()
		if gata is not None:
			gata(text)
	return session.openWithCallback(laInchidere, VirtualKeyBoard, title=titlu,
		text="" if parola else (el.value or ""), hdsSecret=secret)


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

	def handleKey(self, key, callback=None):
		# callback (alte imagini): chemat dupa ce setarea a primit tasta (ecranele lor ii dau entryChanged)
		selection = self.getCurrent()
		if selection and len(selection) > 1 and selection[1].enabled:
			if getattr(selection[1], "isReadOnly", lambda: False)():
				return False
			if key in KEY_NUMBERS or key == KEY_ASCII:
				from Components.HdsAsistentaControl import campSecret, cereOprirePentruSecret
				if campSecret(selection[1], selection[0]) and cereOprirePentruSecret(self.session):
					return
			selection[1].handleKey(key)
			self.invalidateCurrent()
			if key in KEY_NUMBERS:
				self.timer.start(1000, 1)
			if callback is not None:
				callback()
			return True
		return False

	def getCurrent(self, full=True):
		return self.l.getCurrentSelection()

	# HDSatelit: navigarea cu numele din alte imagini (pluginurile scrise pentru ele le cheama pe self["config"])
	def _muta(self, directie):
		if self.instance is not None:
			self.instance.moveSelection(getattr(self.instance, directie))

	def goTop(self):
		self._muta("moveTop")

	def goPageUp(self):
		self._muta("pageUp")

	def goLineUp(self):
		self._muta("moveUp")

	def goLineDown(self):
		self._muta("moveDown")

	def goPageDown(self):
		self._muta("pageDown")

	def goBottom(self):
		self._muta("moveEnd")

	moveTop = goTop
	pageUp = goPageUp
	moveUp = goLineUp
	moveDown = goLineDown
	pageDown = goPageDown
	moveBottom = goBottom

	def selectionEnabled(self, enabled):
		if self.instance is not None:
			self.instance.setSelectionEnable(enabled)

	def enableAutoNavigation(self, enabled):
		"""La noi lista nativa nu se poate dezlega din Python (vezi MenuList.enableAutoNavigation); se tine alegerea."""
		self.navigareAutomata = bool(enabled)

	def campSecretActual(self):
		from Components.HdsAsistentaControl import campSecret
		rand = self.getCurrent()
		return bool(rand and len(rand) >= 2 and campSecret(rand[1], rand[0]))
	
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
		if hasattr(instance, "setScrollMargin"):
			from Components.Renderer.Listbox import margineDerulare  # aici, nu la incarcare: ConfigList se incarca si fara GUI
			instance.setScrollMargin(margineDerulare())
	
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
			if len(x) > 1:
				is_changed |= x[1].isChanged()

		return is_changed

class ConfigListScreen:
	def __init__(self, list, session = None, on_change = None, fullUI = False, allowDefault = False, **altele):
		# HDSatelit: fullUI/allowDefault (alte imagini) se primesc; la noi tastele ecranului raman cele de azi, iar
		# keyDefault (pune valorile implicite) se poate chema de ecran. Mesajele si notificatorii de salvare ca acolo.
		self.fullUI = fullUI
		self.allowDefault = allowDefault
		if not isinstance(getattr(self, "onSave", None), type([])):
			self.onSave = []
		self.cancelMsg = _("Really close without saving settings?")
		self.restartMsg = _("Repornești interfața acum?")
		self.closeParameters = ()
		self["config_actions"] = NumberActionMap(["SetupActions", "MenuActions", "InputAsciiActions", "KeyboardInputActions"],
		{
			"gotAsciiCode": self.keyGotAscii,
			"ok": self.keyOK,
			"menu": self.keyMenu,
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
		# temele din alte imagini asaza aici „HelpWindow” (poza tastaturii); numai sub o tema straina (HdsNumeStandard)
		try:
			from Components.HdsNumeStandard import adauga
			from Components.Pixmap import Pixmap
			adauga(self, "HelpWindow", Pixmap, ascuns=True)
		except Exception as e:
			print("[ConfigList] HelpWindow: %r" % (e,))

	# numele cerute de pluginuri
	def getCurrentEntry(self):
		cur = self["config"].getCurrent()
		return cur[0] if cur else ""

	def getCurrentItem(self):
		cur = self["config"].getCurrent()
		return cur[1] if cur and len(cur) > 1 else None

	def getCurrentValue(self):
		item = self.getCurrentItem()
		return str(item.getText()) if item is not None else ""

	def getCurrentDescription(self):
		cur = self["config"].getCurrent()
		return cur[2] if cur and len(cur) > 2 else ""

	def changedEntry(self):
		for x in getattr(self, "onChangedEntry", ()):
			x()

	def keySelect(self):
		self.keyOK()

	def keyText(self):
		self.KeyText()

	def _mutaLista(self, directie):
		lista = self["config"].instance
		if lista is not None:
			lista.moveSelection(getattr(lista, directie))

	def keyUp(self):
		self._mutaLista("moveUp")

	def keyDown(self):
		self._mutaLista("moveDown")

	def keyPageUp(self):
		self._mutaLista("pageUp")

	def keyPageDown(self):
		self._mutaLista("pageDown")

	def closeRecursive(self):
		self.close(True)

	def handleInputHelpers(self):
		cur = self["config"].getCurrent()
		# tasta TEXT deschide tastatura pe orice camp de text, si in ecranele fara iconita VKeyIcon (Setup)
		self["VirtualKB"].setEnabled(bool(cur is not None and len(cur) > 1 and esteTextDeScris(cur[1])))
		if self["config"].getCurrent() is not None and len(self["config"].getCurrent()) > 1:
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
		from Components.config import ConfigSelection, ConfigBoolean
		# OK schimba numai valoarea curenta; pagina se salveaza cu VERDE.
		if cur is not None and len(cur) > 1 and isinstance(cur[1], (ConfigSelection, ConfigBoolean)):
			self["config"].handleKey(KEY_RIGHT)
			self.__changed()
			return
		self["config"].handleKey(KEY_OK)

	def keyMenu(self):
		"""MENU: toate valorile unui ConfigSelection, fara salvarea paginii."""
		from Components.config import ConfigSelection
		cur = self["config"].getCurrent()
		if cur is None or len(cur) < 2 or not isinstance(cur[1], ConfigSelection) or not cur[1].enabled:
			return 0
		el = cur[1]
		alegeri = [(_(el.description[v]) or str(v), v) for v in el.choices]
		from Screens.ChoiceBox import ChoiceBox
		def ales(raspuns):
			if raspuns is not None and el.enabled and any(len(r) > 1 and r[1] is el for r in self["config"].list):
				el.value = raspuns[1]
				self["config"].invalidate(cur)
				self.__changed()
		self.session.openWithCallback(ales, ChoiceBox, title=cur[0], list=alegeri, selection=el.index)
		return 1

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
			if len(x) > 1:
				x[1].save()

	# keySave and keyCancel are just provided in case you need them.
	# you have to call them by yourself.
	def keySave(self):
		# notificatorii de salvare (addSaveNotifier, alte imagini) inaintea salvarii
		for notifier in list(self.__dict__.get("onSave", ())):
			notifier()
		self.saveAll()
		self.close()
	
	def cancelConfirm(self, result):
		if not result:
			return

		for x in self["config"].list:
			if len(x) > 1:
				x[1].cancel()
		getattr(self, "cancelConfirmed", self.close)()

	def keyCancel(self):
		# intreaba cand sunt schimbari; inchiderea trece prin cancelConfirmed (subclasele din alte imagini o suprascriu)
		self.closeParameters = ()
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelConfirm, MessageBox, getattr(self, "cancelMsg", None) or _("Really close without saving settings?"))
		else:
			getattr(self, "cancelConfirmed", self.close)()

	# HDSatelit: restul API-ului din alte imagini al ecranelor cu setari (pluginurile scrise pentru el le cheama sau le
	# suprascriu). Iesirea, salvarea si tastele de mai sus merg ca pana acum pe ecranele noastre.
	def closeConfigList(self, closeParameters=()):
		self.closeParameters = closeParameters
		if self["config"].isChanged():
			self.session.openWithCallback(self.cancelConfirm, MessageBox, getattr(self, "cancelMsg", None) or _("Really close without saving settings?"))
		else:
			self.cancelConfirmed()

	def cancelConfirmed(self):
		self.close(*getattr(self, "closeParameters", ()))

	def setCancelMessage(self, msg):
		self.cancelMsg = _("Really close without saving settings?") if msg is None else msg

	def setRestartMessage(self, msg):
		self.restartMsg = _("Repornești interfața acum?") if msg is None else msg

	def addSaveNotifier(self, notifier):
		if not callable(notifier):
			raise TypeError("[ConfigList] notifier must be callable")
		self.__dict__.setdefault("onSave", []).append(notifier)

	def removeSaveNotifier(self, notifier):
		lista = self.__dict__.get("onSave", [])
		while notifier in lista:
			lista.remove(notifier)

	def clearSaveNotifiers(self):
		self.onSave = []

	def entryChanged(self):
		self.__changed()

	def _tastaSetare(self, tasta):
		self["config"].handleKey(tasta)
		self.__changed()

	def keyTop(self):
		self["config"].goTop()

	def keyBottom(self):
		self["config"].goBottom()

	def keyFirst(self):
		self._tastaSetare(KEY_HOME)

	def keyLast(self):
		self._tastaSetare(KEY_END)

	def keyToggle(self):
		self._tastaSetare(KEY_TOGGLEOW)

	def keyErase(self):
		# Alte imagini: sterge textul campului; la noi: un camp de text se goleste, restul nu se schimba
		cur = self.getCurrentItem()
		if cur is not None and esteTextDeScris(cur):
			cur.setValue("")
			self["config"].invalidateCurrent()
			self.__changed()

	def keyDefault(self):
		for rand in self["config"].getList():
			if len(rand) > 1 and hasattr(rand[1], "default"):
				try:
					rand[1].setValue(rand[1].default)
				except Exception:
					continue
				self["config"].invalidate(rand)
		self.__changed()

	def suspendAllActionMaps(self):
		self.actionMapStates = []
		for nume in self.__hartile():
			self.actionMapStates.append((nume, self[nume].enabled))
			self[nume].setEnabled(False)

	def resumeAllActionMaps(self):
		for nume, stare in getattr(self, "actionMapStates", ()):
			if nume in self:
				self[nume].setEnabled(stare)

	def __hartile(self):
		return [k for k in self.keys() if isinstance(self[k], ActionMap)]

	def showHelpWindow(self):
		self.displayHelp(True)

	def hideHelpWindow(self):
		self.displayHelp(False)

	def displayHelp(self, state):
		cur = self.getCurrentItem()
		fereastra = getattr(cur, "help_window", None) if cur is not None else None
		if fereastra is not None:
			fereastra.show() if state else fereastra.hide()

	def noNativeKeys(self):
		"""Alte imagini: lista nu mai muta singura cursorul (la noi lista nativa ramane legata; se tine alegerea)."""
		self["config"].enableAutoNavigation(False)

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

	def run(self):
		self.keySave()

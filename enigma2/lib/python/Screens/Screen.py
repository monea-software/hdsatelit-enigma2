# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Tools.Profile import profile

profile("LOAD:GUISkin")
from Components.GUISkin import GUISkin
profile("LOAD:Source")
from Components.Sources.Source import Source
profile("LOAD:GUIComponent")
from Components.GUIComponent import GUIComponent
profile("LOAD:eRCInput")
from enigma import eRCInput

class Screen(dict, GUISkin):

	SUSPEND_NONE, SUSPEND_STOPS, SUSPEND_PAUSES = list(range(3))
	ALLOW_SUSPEND = False

	global_screen = None

	# steagul ecranelor care primesc raspunsuri de pe un fir din fundal: ecranul pune self.inchis (sau self._inchis)
	# = False in __init__; doClose goleste __dict__, deci un raspuns venit dupa inchidere citeste valoarea clasei (True)
	# si iese, in loc de AttributeError (care opreste enigma2 din ceasul firului)
	inchis = True
	_inchis = True

	def __init__(self, session, parent = None, mandatoryWidgets = None, enableHelp = False):
		dict.__init__(self)
		self.skinName = self.__class__.__name__
		self.session = session
		self.parent = parent
		GUISkin.__init__(self)

		self.onClose = [ ]
		self.onFirstExecBegin = [ ]
		self.onExecBegin = [ ]
		# pluginurile altora isi pun aici functii chemate la iesirea ecranului din executie (ca in celelalte imagini)
		self.onExecEnd = [ ]
		self.onShown = [ ]

		self.onShow = [ ]
		self.onHide = [ ]

		self.execing = False
		
		self.shown = True
		# already shown is false until the screen is really shown (after creation)
		self.already_shown = False

		self.renderer = [ ]

		# in order to support screens *without* a help,
		# we need the list in every screen. how ironic.
		self.helpList = [ ]

		self.close_on_next_exec = None

		# stand alone screens (for example web screens)
		# don't care about having or not having focus.
		self.stand_alone = False
		self.keyboardMode = None

		# pluginurile scrise pentru alte imagini (managerul de fisiere FileCommander):
		# mandatoryWidgets = elementele fara de care, acolo, un ecran din skin se respinge si se ia cel scris in cod;
		# skinurile noastre nu au ecranele acelor pluginuri, deci aici lista doar se pastreaza.
		# enableHelp=True: tasta HELP deschide ajutorul ecranului (helpList), ca la HelpableScreen; key_help e eticheta
		# tastei, pe care o arata skinurile lor. Contextul e al nostru, HelpActions (data/keymap.xml).
		self.mandatoryWidgets = mandatoryWidgets
		if enableHelp:
			from Components.ActionMap import ActionMap
			from Components.Sources.StaticText import StaticText
			self["helpActions"] = ActionMap(["HelpActions"], {"displayHelp": self.showHelp})
			self["key_help"] = StaticText(_("HELP"))

	def showHelp(self):
		"""ajutorul ecranului (randurile puse de HelpableActionMap in helpList), ca HelpableScreen"""
		from Screens.HelpMenu import HelpMenu
		self.session.openWithCallback(self.callHelpAction, HelpMenu, self.helpList)

	def callHelpAction(self, *args):
		if args:
			(actionmap, context, action) = args
			actionmap.action(context, action)

	def saveKeyboardMode(self):
		rcinput = eRCInput.getInstance()
		self.keyboardMode = rcinput.getKeyboardMode()

	def setKeyboardModeAscii(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmAscii)

	def setKeyboardModeNone(self):
		rcinput = eRCInput.getInstance()
		rcinput.setKeyboardMode(rcinput.kmNone)

	def restoreKeyboardMode(self):
		rcinput = eRCInput.getInstance()
		if self.keyboardMode is not None:
			rcinput.setKeyboardMode(self.keyboardMode)

	def execBegin(self):
		self.active_components = [ ]
		if self.close_on_next_exec is not None:
			tmp = self.close_on_next_exec
			self.close_on_next_exec = None
			self.execing = True
			self.close(*tmp)
		else:
			single = self.onFirstExecBegin
			self.onFirstExecBegin = []
			for x in self.onExecBegin + single:
				x()
				if not self.stand_alone and self.session.current_dialog != self:
					return

#			assert self.session == None, "a screen can only exec once per time"
#			self.session = session

			for val in list(self.values()) + self.renderer:
				val.execBegin()
				if not self.stand_alone and self.session.current_dialog != self:
					return
				self.active_components.append(val)

			self.execing = True
	
			for x in self.onShown:
				x()
	
	def execEnd(self):
		active_components = self.active_components
#		for (name, val) in self.items():
		self.active_components = None
		for val in active_components:
			val.execEnd()
#		assert self.session != None, "execEnd on non-execing screen!"
#		self.session = None
		self.execing = False
		for x in list(getattr(self, "onExecEnd", ())):
			x()
	
	# never call this directly - it will be called from the session!
	def doClose(self):
		self.hide()
		for x in self.onClose:
			x()
		
		# fixup circular references
		del self.helpList
		GUISkin.close(self)

		# first disconnect all render from their sources.
		# we might split this out into a "unskin"-call,
		# but currently we destroy the screen afterwards
		# anyway.
		for val in self.renderer:
			val.disconnectAll()  # disconnected converter/sources and probably destroy them. Sources will not be destroyed.

		del self.session
		for (name, val) in list(self.items()):
			val.destroy()
			del self[name]

		self.renderer = [ ]

		# really delete all elements now
		self.__dict__.clear()
	
	def close(self, *retval):
		if not self.execing:
			self.close_on_next_exec = retval
		else:
			self.session.close(self, *retval)

	def setFocus(self, o):
		self.instance.setFocus(o.instance)

	# HDSatelit 0.7.4 (OE-Alliance): animatia ferestrei, ceruta de pluginuri (de obicei setAnimationMode(0) pe ferestrele
	# lor care apar des): 0x00 oprita, 0x01 la aratare, 0x10 la ascundere, 0x11 amandoua (Components/HdsAnimatiiFerestre.py)
	def setAnimationMode(self, mode):
		if self.instance:
			self.instance.setAnimationMode(mode)

	def show(self):
		if (self.shown and self.already_shown) or not self.instance:
			return
		self.shown = True
		self.already_shown = True
		self.instance.show()
		for x in self.onShow:
			x()
		for val in list(self.values()) + self.renderer:
			if isinstance(val, GUIComponent) or isinstance(val, Source):
				val.onShow()

	def hide(self):
		if not self.shown or not self.instance:
			return
		self.shown = False
		self.instance.hide()
		for x in self.onHide:
			x()
		for val in list(self.values()) + self.renderer:
			if isinstance(val, GUIComponent) or isinstance(val, Source):
				val.onHide()

	def __repr__(self):
		return str(type(self))

	# HDSatelit: semnaturile din alte imagini (pluginurile scrise pentru ele): setTitle(title, showPath) (calea meniului nu se
	# arata la noi), poza ecranului (setImage/getImage: numele se tine, skin-urile noastre nu au poza ecranului)
	def setTitle(self, title, showPath=True):
		GUISkin.setTitle(self, title)

	title = property(lambda self: self.getTitle(), lambda self, titlu: self.setTitle(titlu))

	def setImage(self, image, source=None):
		self.screenImage = image
		# temele din alte imagini asaza aici „Image” (poza ecranului); numai sub o tema straina, ascunsa (HdsNumeStandard)
		try:
			from Components.HdsNumeStandard import adauga
			from Components.Pixmap import Pixmap
			adauga(self, "Image", Pixmap, ascuns=True)
		except Exception as e:
			print("[Screen] Image: %r" % (e,))

	def getImage(self):
		return getattr(self, "screenImage", None)

	def callLater(self, function):
		"""function() on the next pass of the main loop"""
		from enigma import eTimer
		self.__ceasMaiTarziu = eTimer()
		self.__ceasMaiTarziu.callback.append(function)
		self.__ceasMaiTarziu.start(0, True)

	def getRelatedScreen(self, name):
		if name == "session":
			return self.session.screen
		elif name == "parent":
			return self.parent
		elif name == "global":
			return self.global_screen
		else:
			return None

class ScreenSummary(Screen):
	"""The small screen of a plugin on the display of the receiver: the clock and the title of the screen, unless the theme has its own <name>Summary."""
	skin = """
	<screen position="0,0" size="132,64">
		<widget source="global.CurrentTime" render="Label" position="0,0" size="132,20" font="Regular;16" halign="center" valign="center">
			<convert type="ClockToText">WithSeconds</convert>
		</widget>
		<widget source="Title" render="Label" position="0,24" size="132,40" font="Regular;18" halign="center" valign="center" />
	</screen>"""

	def __init__(self, session, parent):
		from Components.Sources.StaticText import StaticText
		Screen.__init__(self, session, parent=parent)
		titlu = parent.getTitle() if hasattr(parent, "getTitle") else ""
		self["Title"] = StaticText(titlu)
		nume = parent.skinName if isinstance(parent.skinName, list) else [parent.skinName]
		self.skinName = ["%sSummary" % x for x in nume] + ["%s_summary" % x for x in nume] + ["ScreenSummary"]
		self.skin = parent.__dict__.get("skinSummary", self.skin)

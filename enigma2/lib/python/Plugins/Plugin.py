# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.config import ConfigSubsection, config
from inspect import Parameter, signature
from os.path import isfile
from traceback import print_exc
from Tools.LoadPixmap import LoadPixmap

config.plugins = ConfigSubsection()

_POZITIONALE = (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
_PE_NUME = (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)

class PluginDescriptor:
	"""An object to describe a plugin."""
	
	# where to list the plugin. Note that there are different call arguments,
	# so you might not be able to combine them.
	
	# supported arguments are:
	#   session
	#   servicereference
	#   reason
	
	# you have to ignore unknown kwargs!
	
	# argument: session
	WHERE_EXTENSIONSMENU = 0
	WHERE_MAINMENU = 1
	WHERE_PLUGINMENU  = 2
	# argument: session, serviceref (currently selected)
	WHERE_MOVIELIST = 3
	# argument: menuid. Fnc must return list with menuitems (4-tuple of name, fnc to call, entryid or None, weight or None)
	WHERE_MENU = 4
	
	# reason (0: start, 1: end)
	WHERE_AUTOSTART = 5
	
	# start as wizard. In that case, fnc must be tuple (priority,class) with class being a screen class!
	WHERE_WIZARD = 6
	
	# like autostart, but for a session. currently, only session starts are 
	# delivered, and only on pre-loaded plugins
	WHERE_SESSIONSTART = 7
	
	# start as teletext plugin. arguments: session, serviceref
	WHERE_TELETEXT = 8
	
	# file-scanner, fnc must return a list of Scanners
	WHERE_FILESCAN = 9
	
	# fnc must take an interface name as parameter and return None if the plugin supports an extended setup
	# or return a function which is called with session and the interface name for extended setup of this interface
	WHERE_NETWORKSETUP = 10
	
	# show up this plugin (or a choicebox with all of them) for long INFO keypress
	# or return a function which is called with session and the interface name for extended setup of this interface
	WHERE_EVENTINFO = 11

	# reason (True: Networkconfig read finished, False: Networkconfig reload initiated )
	WHERE_NETWORKCONFIG_READ = 12

	WHERE_AUDIOMENU = 13

	# fnc 'SoftwareSupported' or  'AdvancedSoftwareSupported' must take a parameter and return None
	# if the plugin should not be displayed inside Softwaremanger or return a function which is called with session
	# and 'None' as parameter to call the plugin from the Softwaremanager menus. "menuEntryName" and "menuEntryDescription"
	# should be provided to name and describe the new menu entry.
	WHERE_SOFTWAREMANAGER = 14

	# locurile din celelalte imagini: un plugin care le cere se incarca, iar intrarea lui nu apare acolo unde imaginea nu le cauta
	WHERE_CHANNEL_CONTEXT_MENU = 15
	WHERE_RECORDTIMER = 16
	WHERE_PLAYSERVICE = 17
	WHERE_INFOBARLOADED = 18
	WHERE_SATCONFIGCHANGED = 19
	WHERE_SERVICESCAN = 20
	WHERE_EXTENSIONSINGLE = 21
	WHERE_BUTTONSETUP = 22
	WHERE_INFOBAR_SCREEN = 23
	WHERE_SECONDINFOBAR_SCREEN = 24
	WHERE_NETWORKMOUNTS = 25
	WHERE_SKINCHANGE = 26
	WHERE_EPG_SELECTION_SINGLE_BLUE = 27
	WHERE_EVENTVIEW = 28


	def __init__(self, name = "Plugin", where = [ ], description = "", icon = None, fnc = None, wakeupfnc = None, needsRestart = None, internal = False, weight = 0):
		self.name = name
		self.internal = internal
		self.needsRestart = needsRestart
		self.path = None
		if isinstance(where, list):
			self.where = where
		else:
			self.where = [ where ]
		self.description = description

		if icon is None or isinstance(icon, str):
			self.iconstr = icon
			self.icon = None
		else:
			self.iconstr = None
			self.icon = icon

		self.weight = weight

		self.wakeupfnc = wakeupfnc

		self.fnc = fnc

	def updateIcon(self, path):
		if isinstance(self.iconstr, str):
			cale = '/'.join((path, self.iconstr))
			# HDSatelit: pluginurile scrise pentru alte imagini au si pictograme .svg, pe care imaginea nu le deseneaza; pictograma nu mai
			# opreste incarcarea pluginului: se ia .png-ul cu acelasi nume de langa ea, daca exista, altfel pluginul ramane cu cea implicita
			if cale[-4:] not in ('.png', '.jpg') and cale[-1:] != '.':
				png = cale.rsplit('.', 1)[0] + '.png'
				if isfile(png):
					cale = png
				else:
					print("[Plugin] pictograma %s nu e .png sau .jpg; pluginul %s ramane cu pictograma implicita" % (cale, self.name))
					self.icon = None
					return
			self.icon = LoadPixmap(cale)

	def getWakeupTime(self):
		return self.wakeupfnc and self.wakeupfnc() or -1

	def __call__(self, *args, **kwargs):
		# eroarea unui plugin nu opreste receptorul: jurnal, avertisment, mesaj nemodal
		try:
			return self.fnc(*args, **kwargs)
		except Exception as exc:
			print("[Plugin] error in plugin %s (%s):" % (self.name, self.path))
			print_exc()
			self.reportError(exc)
			return None

	def _parametri(self):
		"""parametrii functiei, fara self la o metoda legata; None cand semnatura nu se poate citi (o functie din C, o adnotare
		care nu se poate evalua in Python 3.14)"""
		try:
			return list(signature(self.fnc).parameters.values())
		except Exception:
			return None

	def cereListaCanale(self):
		"""Pluginul nu poate porni fara lista de canale: al doilea argument obligatoriu sau servicelist obligatoriu. In
		playerul de filme, unde lista nu exista, un astfel de plugin nu apare."""
		parametri = self._parametri()
		if parametri is None:
			return False
		pozitionale = [p for p in parametri if p.kind in _POZITIONALE]
		if len(pozitionale) > 1 and pozitionale[1].default is Parameter.empty:
			return True
		return any(p.name == "servicelist" and p.kind == Parameter.KEYWORD_ONLY and p.default is Parameter.empty for p in parametri)

	def apelDeschidere(self, session, servicelist=None):
		"""(args, kwargs) cu care se deschide pluginul, dupa semnatura lui:
		f(session) session=; f(session, **kw) session=, servicelist=; f(session, servicelist) amandoua pe nume;
		f(session, sl) cu al doilea obligatoriu, alt nume: pozitional amandoua; f(sess) pozitional; f(sess, **kw) pozitional
		si servicelist=; f(*a, **kw) si f(**kw) pe nume; f(*a) pozitional; semnatura necitita: session=.
		Un al doilea argument optional cu alt nume nu e lista de canale si nu primeste nimic. Fara lista de canale (None),
		servicelist nu se da deloc."""
		parametri = self._parametri()
		if parametri is None:
			return (), {"session": session}
		pozitionale = [p for p in parametri if p.kind in _POZITIONALE]
		pe_nume = [p.name for p in parametri if p.kind in _PE_NUME]
		oricate = any(p.kind == Parameter.VAR_POSITIONAL for p in parametri)
		cuvinte = any(p.kind == Parameter.VAR_KEYWORD for p in parametri)
		args, kw = [], {}
		if "session" in pe_nume:
			kw["session"] = session
		elif pozitionale or (oricate and not cuvinte):
			args.append(session)
		elif cuvinte:
			kw["session"] = session
		if servicelist is not None:
			if "servicelist" in pe_nume:
				kw["servicelist"] = servicelist
			elif len(pozitionale) > 1 and pozitionale[1].default is Parameter.empty:
				args, kw = [session, servicelist], {}
			elif cuvinte:
				kw["servicelist"] = servicelist
		return tuple(args), kw

	def deschide(self, session, servicelist=None):
		"""Deschide pluginul din orice lista (tasta albastra, Extensii, pagina web), cu apelul potrivit semnaturii lui. O
		singura incercare: nu se reia aceeasi functie dupa un TypeError, prima incercare poate avea efecte. Eroarea veche se
		sterge aici, iar una noua o pune reportError; deci dupa o deschidere reusita nu mai ramane niciuna."""
		args, kw = self.apelDeschidere(session, servicelist)
		try:
			from Components.PluginComponent import plugins
			plugins.eroriDeschidere.pop(self.path or self.name, None)
		except Exception:
			print_exc()
		return self(*args, **kw)

	def motivDeschidere(self):
		"""textul pentru om cand ultima deschidere a cazut, altfel gol"""
		from Components.PluginComponent import plugins, motivOm
		mesaj = plugins.eroriDeschidere.get(self.path or self.name)
		return _("Nu a putut porni: %s") % motivOm(mesaj) if mesaj else ""

	def motivTaste(self):
		"""textul pentru om cand keymap.xml al pluginului e stricat (pluginul se deschide mai departe), altfel gol"""
		from Components.PluginComponent import plugins
		mesaj = plugins.eroriTaste.get(self.path)
		return _("Problemă cu tastele: %s") % mesaj if mesaj else ""

	def reportError(self, exc):
		try:
			from Components.PluginComponent import plugins
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			plugins.warnings.append((self.name, str(exc)))
			plugins.eroriDeschidere[self.path or self.name] = str(exc) or type(exc).__name__
			# HDSatelit: un modul Python lipsa din feedul nostru se instaleaza singur (Components/HdsModuleLipsa.py)
			try:
				from Components import HdsModuleLipsa
				HdsModuleLipsa.dinExceptie(exc, self.path, self.name)
			except Exception:
				print_exc()
			Notifications.AddPopup(_("Plugin %s stopped with an error:\n%s") % (self.name, exc), MessageBox.TYPE_ERROR, 15, "plugin_error_%s" % self.name)
		except Exception:
			print_exc()

	def __eq__(self, other):
		return isinstance(other, PluginDescriptor) and self.fnc == other.fnc

	def __hash__(self):
		return hash(self.fnc)

# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eActionMap

# Sagetile ecranelor scrise pentru alte imagini (managerul de fisiere FileCommander, editoarele lor de text): acolo
# ecranul isi opreste navigarea proprie a listelor (enableAutoNavigation(False), o metoda C++ a listei) si muta singur
# cursorul din harta lui pe contextul NavigationActions. La noi lista nativa leaga ListboxActions cu prioritatea 0 cand
# se face, deci inaintea hartilor Python legate la deschiderea ecranului, si ar lua ea SUS/JOS. Contextul acesta se leaga
# de aceea cel tarziu cu prioritatea -1 (inaintea listei). Niciun ecran al nostru nu foloseste NavigationActions.
CONTEXT_NAVIGARE = "NavigationActions"

# HDSatelit: tastele pe care pluginurile din alte imagini le asteapta in contextele comune si keymap-ul nostru nu le are
# (SetupActions menu/info, ColorActions redlong..bluelong, EPGSelectActions menu...) stau in keymap.xml sub
# <context>.straine. Contextul acesta il leaga NUMAI hartile facute de codul unui plugin strain, deci ecranele noastre nu
# primesc nici taste noi, nici randuri „unknown action” in jurnal (hotararea din 11.11.2026, varianta 1).
SUFIX_STRAINE = ".straine"

# HDSatelit: apasarea scurta si cea lunga a pluginurilor straine, ca in OE-Alliance. Acolo tasta care are si varianta
# lunga porneste scurta la eliberare (flags="b") si lunga la tinere (flags="l"), iar eliberarea de dupa o apasare lunga
# nu mai porneste nimic (C++-ul lor o trimite ca steagul 5, „stop”). La noi culorile, INFO, HELP si EXIT pornesc scurta
# la apasare (flags="m" in contextele noastre) si C++-ul nostru trimite steagul „stop” numai in plus fata de „b” (OEA16,
# lib/actions/action.cpp: randurile cu „b” pornesc si dupa lunga, ca hartile noastre sa ramana neschimbate): tinuta, tasta pornea intai scurta, apoi
# lunga (EPGSearch: ALBASTRU tinut deschidea exportul AutoTimer, nu lista). Pentru hartile straine (numai ele):
# - <context>.straine are scurta si pe „b”; cand harta are si varianta lunga pe tasta (OEA17, mai jos), scurta nu mai
#   porneste la apasare din contextul nostru, ci la eliberare din .straine;
# - eliberarea de dupa o apasare lunga pe care a folosit-o un plugin strain nu mai porneste scurta. Daca pluginul n-are
#   varianta lunga (ex. are numai „cancel”, nu si „close”), eliberarea porneste scurta, ca tasta sa nu ramana fara efect.
# Tasta si steagul curent le tine _pazitorTasta, legata fara context si inaintea tuturor (intoarce mereu 0, deci nu
# opreste nicio tasta); se leaga la prima harta straina si nu se mai dezleaga. Hartile noastre nu trec pe aici.
# OEA17 (12.11.2026): scurta se amana la eliberare NUMAI cand aceeasi harta a pluginului are si varianta lunga pe
# aceeasi tasta (ex. „blue” si „bluelong”); altfel porneste la apasare, ca tastele obisnuite sa nu intarzie (ROSU al
# unui plugin care n-are „redlong” raspunde ca pe ecranele noastre). In OE-Alliance culorile pornesc mereu la eliberare;
# la noi intarzierea ramane doar unde chiar e nevoie de ea. Eliberarea porneste scurta din <context>.straine numai in
# harta care a amanat-o la apasare (altfel ar porni a doua oara). In sursele pluginurilor OE-Alliance (1151 de harti,
# paralel-1111b/OEA17) nicio harta nu tine varianta lunga fara cea scurta, deci „aceeasi harta” ajunge.
PRIORITATE_PAZITOR = -0x7FFFFFFF - 1
STEAG_APASARE = 1  # bitul lui „m” (1 << flagMake)
STEAG_ELIBERARE = 2  # bitul lui „b” in steagurile din keymap (1 << flagBreak)
STEAG_LUNG = 8  # bitul lui „l” (1 << flagLong)
STEAG_STOP = 32  # bitul lui „s” (1 << 5, „stop”: eliberarea de dupa apasarea lunga, ca in OE-Alliance)
_tasta = {"cod": -1, "steag": -1, "lunga_folosita": False, "amanate": set()}
_pazitor = []


def _pazitorTasta(key, flag):
	try:
		if flag != 4:  # 4 = caracter (tastatura), nu o tasta
			if flag == 0:
				_tasta["lunga_folosita"] = False
				_tasta["amanate"] = set()
			_tasta["cod"] = key
			_tasta["steag"] = flag
	except Exception:
		pass
	return 0


def _areLunga(harta, cod):
	"""True cand harta (straina) are, pe tasta `cod`, o actiune lunga („l”) pe care o poate porni."""
	oprite = getattr(harta, "disbledActions", ())
	for ctx in harta.contexts:
		for c in (ctx, ctx + SUFIX_STRAINE):
			for actiune in harta.actions:
				if actiune in oprite:
					continue
				for tasta, steaguri in queryKeyBinding(c, actiune):
					if tasta == cod and steaguri & STEAG_LUNG:
						return True
	return False


def _legaPazitorul():
	if not _pazitor:
		try:
			eActionMap.getInstance().bindAction("", PRIORITATE_PAZITOR, _pazitorTasta)
			_pazitor.append(_pazitorTasta)
		except Exception as e:
			print("[ActionMap] pazitorul tastelor nu s-a legat: %s" % e)


def _pe(context, action, cod, steag):
	"""True cand `action` e legata in `context` pe tasta `cod` cu steagul (bitul) `steag`."""
	for tasta, steaguri in queryKeyBinding(context, action):
		if tasta == cod and steaguri & steag:
			return True
	return False


def _opritaPentruStraine(harta, context, action):
	"""True cand actiunea unei harti straine nu trebuie pornita acum (vezi mai sus)."""
	if not _pazitor:
		return False
	steag = _tasta["steag"]
	cod = _tasta["cod"]
	if steag == 1:
		if not _tasta["lunga_folosita"]:
			if context.endswith(SUFIX_STRAINE) and _pe(context[:-len(SUFIX_STRAINE)], action, cod, STEAG_APASARE) \
					and _pe(context, action, cod, STEAG_ELIBERARE):
				# OEA17: scurta din .straine porneste la eliberare numai daca harta a amanat-o la apasare; altfel a
				# pornit deja la apasare din contextul nostru (harta n-are varianta lunga)
				return id(harta) not in _tasta["amanate"]
			return False
		# OEA16: randurile cu „s” (steagul 5, „stop”, ex. volumeUpStop) le trimite C++-ul tocmai la eliberarea de dupa lunga
		# (lib/actions/action.cpp); ele pornesc, ca in OE-Alliance
		return not _pe(context, action, cod, STEAG_STOP)
	if steag in (0, 2) and not context.endswith(SUFIX_STRAINE):
		# o alta harta straina a amanat deja aceasta apasare (ea are lunga): o amana si aceasta, ca scurta sa porneasca o
		# singura data, la eliberare, din harta care a amanat-o prima
		if _pe(context + SUFIX_STRAINE, action, cod, STEAG_ELIBERARE) and (_tasta["amanate"] or _areLunga(harta, cod)):
			if steag == 0:
				_tasta["amanate"].add(id(harta))
			return True
	return False


def _hartaStraina():
	"""True cand harta e facuta de codul unui plugin strain: primul cadru din afara acestui fisier e sub /Plugins/ si nu
	e al unui plugin al imaginii (HdsPluginuriImagine.pluginImagine). Orice nelamurire: False (harta ramane a noastra)."""
	import sys
	try:
		cadru = sys._getframe(1)
	except ValueError:
		return False
	aici = __file__.replace("\\", "/").rsplit("/", 1)[-1].split(".")[0]
	cale = ""
	while cadru is not None:
		cale = cadru.f_code.co_filename.replace("\\", "/")
		if cale.rsplit("/", 1)[-1].split(".")[0] != aici:
			break
		cadru = cadru.f_back
	if cadru is None or "/Plugins/" not in cale:
		return False
	try:
		from Components.HdsPluginuriImagine import pluginImagine
		return not pluginImagine(cale)
	except Exception:
		return False

class ActionMap:
	def __init__(self, contexts = [ ], actions = { }, prio=0, parentScreen=None, **altele):
		# HDSatelit: forma din alte imagini: contexts poate fi un singur nume (sir), actions poate lipsi (None),
		# parentScreen (ecranul, numai pentru jurnal) se tine ca nume
		if isinstance(contexts, str):
			contexts = [contexts]
		self.actions = actions if actions is not None else {}
		self.contexts = contexts if contexts is not None else []
		self.parentScreen = parentScreen.__class__.__name__ if parentScreen else "N/A"
		self.disbledActions = []
		self.prio = prio
		self.p = eActionMap.getInstance()
		self.bound = False
		self.exec_active = False
		self.enabled = True
		self.straine = _hartaStraina()

	def setEnabled(self, enabled):
		self.enabled = enabled
		self.checkBind()

	# numele din alte imagini: starea hartii, o actiune oprita sau pornita singura, actiuni adaugate sau scoase dupa facere
	def getEnabled(self):
		return self.enabled

	def setEnabledAction(self, action, enabled):
		oprite = self.__dict__.setdefault("disbledActions", [])
		if action in self.actions:
			if enabled and action in oprite:
				oprite.remove(action)
			elif not enabled and action not in oprite:
				oprite.append(action)

	def addAction(self, action, response):
		self.actions[action] = response

	def removeAction(self, action):
		self.actions.pop(action, None)

	def doBind(self):
		if not self.bound:
			if getattr(self, "straine", False):
				_legaPazitorul()
			for ctx in self.contexts:
				self.p.bindAction(ctx, min(self.prio, 0) - 1 if ctx == CONTEXT_NAVIGARE else self.prio, self.action)
				if getattr(self, "straine", False):
					self.p.bindAction(ctx + SUFIX_STRAINE, self.prio, self.action)
			self.bound = True

	def doUnbind(self):
		if self.bound:
			for ctx in self.contexts:
				self.p.unbindAction(ctx, self.action)
				if getattr(self, "straine", False):
					# unbindAction scoate o singura legare a functiei la fiecare chemare: doua legari, doua dezlegari
					self.p.unbindAction(ctx + SUFIX_STRAINE, self.action)
			self.bound = False

	def checkBind(self):
		if self.exec_active and self.enabled:
			self.doBind()
		else:
			self.doUnbind()

	def execBegin(self):
		self.exec_active = True
		self.checkBind()

	def execEnd(self):
		self.exec_active = False
		self.checkBind()

	def action(self, context, action):
		straina = getattr(self, "straine", False)
		if straina and _opritaPentruStraine(self, context, action):
			print("[ActionMap] %s/%s nepornita acum (harta straina: scurta la eliberare, nimic dupa lunga, ca in OE-Alliance)" % (context, action))
			return 0
		print(" ".join(("action -> ", context, action)))
		if action in self.actions and action not in getattr(self, "disbledActions", ()):
			if straina and _tasta["steag"] == 3:
				_tasta["lunga_folosita"] = True
			res = self.actions[action]()
			if res is not None:
				return res
			return 1
		else:
			print("unknown action %s/%s! typo in keymap?" % (context, action))
			return 0

	def destroy(self):
		pass

class NumberActionMap(ActionMap):
	def action(self, contexts, action):
		numbers = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
		if (action in numbers and action in self.actions):
			res = self.actions[action](int(action))
			if res is not None:
				return res
			return 1
		else:
			return ActionMap.action(self, contexts, action)

class HelpableActionMap(ActionMap):
	"""An Actionmap which automatically puts the actions into the helpList.

	The context can also be a list; the help goes with the first one."""
	
	# sorry for this complicated code.
	# it's not more than converting a "documented" actionmap 
	# (where the values are possibly (function, help)-tuples)
	# into a "classic" actionmap, where values are just functions.
	# the classic actionmap is then passed to the ActionMap constructor,
	# the collected helpstrings (with correct context, action) is
	# added to the screen's "helpList", which will be picked up by
	# the "HelpableScreen".
	def __init__(self, parent, context, actions = None, prio=0, description=None):
		actions = actions or { }
		contexte = list(context) if isinstance(context, (list, tuple)) else [context]
		self.description = description
		alist = [ ]
		adict = { }
		for (action, funchelp) in actions.items():
			# check if this is a tuple
			if isinstance(funchelp, tuple):
				alist.append((action, funchelp[1]))
				adict[action] = funchelp[0]
			else:
				adict[action] = funchelp

		ActionMap.__init__(self, contexte, adict, prio)

		parent.helpList.append((self, contexte[0], alist))

# numele cerute de pluginuri
# Alte imagini tin aici si functiile tastelor legate (la noi in Tools/KeyBindings): aceleasi functii, sub acelasi nume
def queryKeyBinding(context, action):
	from Tools.KeyBindings import queryKeyBinding as q
	return q(context, action)


def addKeyBinding(filename, key, context, mapTo, flags):
	from Tools.KeyBindings import addKeyBinding as a
	return a(filename, key, context, mapTo, flags)


def removeKeyBindings(filename):
	from Tools.KeyBindings import removeKeyBindings as r
	return r(filename)


def loadKeymap(filename, replace=False):
	import keymapparser
	if replace:
		keymapparser.removeKeymap(filename)
	keymapparser.readKeymap(filename)


def removeKeymap(filename):
	import keymapparser
	keymapparser.removeKeymap(filename)


class HelpableNumberActionMap(NumberActionMap, HelpableActionMap):
	def __init__(self, parent, contexts, actions=None, prio=0, description=None):
		# NumberActionMap trateaza tastele 0-9; textele de ajutor le pune HelpableActionMap
		HelpableActionMap.__init__(self, parent, contexts, actions or {}, prio, description)

# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eActionMap

class ActionMap:
	def __init__(self, contexts = [ ], actions = { }, prio=0):
		self.actions = actions
		self.contexts = contexts
		self.prio = prio
		self.p = eActionMap.getInstance()
		self.bound = False
		self.exec_active = False
		self.enabled = True

	def setEnabled(self, enabled):
		self.enabled = enabled
		self.checkBind()

	def doBind(self):
		if not self.bound:
			for ctx in self.contexts:
				self.p.bindAction(ctx, self.prio, self.action)
			self.bound = True

	def doUnbind(self):
		if self.bound:
			for ctx in self.contexts:
				self.p.unbindAction(ctx, self.action)
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
		print(" ".join(("action -> ", context, action)))
		if action in self.actions:
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
		HelpableActionMap.__init__(self, parent, contexts, actions or {}, prio)

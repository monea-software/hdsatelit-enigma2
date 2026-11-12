# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent

from enigma import eListboxPythonStringContent, eListbox

class MenuList(HTMLComponent, GUIComponent):
	def __init__(self, list, enableWrapAround=False, content=eListboxPythonStringContent):
		GUIComponent.__init__(self)
		self.list = list
		self.l = content()
		self.l.setList(self.list)
		self.onSelectionChanged = [ ]
		self.enableWrapAround = enableWrapAround

	def getCurrent(self):
		return self.l.getCurrentSelection()

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)
		if self.enableWrapAround:
			self.instance.setWrapAround(True)
		if hasattr(instance, "setScrollMargin"):
			from Components.Renderer.Listbox import margineDerulare  # aici, nu la incarcare: ConfigList se incarca si fara GUI
			instance.setScrollMargin(margineDerulare())

	def preWidgetRemove(self, instance):
		instance.setContent(None)
		instance.selectionChanged.get().remove(self.selectionChanged)

	def selectionChanged(self):
		for f in self.onSelectionChanged:
			f()

	def getSelectionIndex(self):
		return self.l.getCurrentSelectionIndex()

	def getSelectedIndex(self):
		return self.l.getCurrentSelectionIndex()

	def setList(self, list):
		self.list = list
		self.l.setList(self.list)

	def moveToIndex(self, idx):
		if self.instance is not None:
			self.instance.moveSelectionTo(idx)

	def pageUp(self):
		if self.instance is not None:
			self.instance.moveSelection(self.instance.pageUp)

	def pageDown(self):
		if self.instance is not None:
			self.instance.moveSelection(self.instance.pageDown)

	def up(self):
		if self.instance is not None:
			self.instance.moveSelection(self.instance.moveUp)

	def down(self):
		if self.instance is not None:
			self.instance.moveSelection(self.instance.moveDown)

	def top(self):
		if self.instance is not None:
			self.instance.moveSelection(self.instance.moveTop)

	def bottom(self):
		if self.instance is not None:
			self.instance.moveSelection(self.instance.moveEnd)

	# numele din celelalte imagini
	moveUp = goLineUp = up
	moveDown = goLineDown = down
	goPageUp = pageUp
	goPageDown = pageDown
	moveTop = goTop = top
	moveBottom = goBottom = bottom
	getCurrentIndex = getSelectedIndex

	def setCurrentIndex(self, idx):
		self.moveToIndex(idx)

	# HDSatelit: restul numelor din alte imagini ale listei (pluginurile scrise pentru ele): proprietatile current/index,
	# capetele si paginile (goFirst/goLast/goLeft/goRight; la lista verticala, stanga/dreapta = o pagina), randul de sus
	# al ferestrei si un rand schimbat pe loc
	# o subclasa mai veche care isi tine singura self.current / self.index (inainte de proprietati) le pastreaza: ce
	# pune ea se citeste inapoi; altfel current e randul ales, iar index muta cursorul, ca in alte imagini
	def _getCurrentOea(self):
		return self.__dict__["_hdsCurentPus"] if "_hdsCurentPus" in self.__dict__ else self.getCurrent()

	def _setCurrentOea(self, valoare):
		self.__dict__["_hdsCurentPus"] = valoare

	def _getIndexOea(self):
		if self.instance is None and "_hdsIndexPus" in self.__dict__:
			return self.__dict__["_hdsIndexPus"]
		return self.getSelectedIndex()

	def _setIndexOea(self, idx):
		if self.instance is None:
			self.__dict__["_hdsIndexPus"] = idx
		else:
			self.moveToIndex(idx)

	current = property(_getCurrentOea, _setCurrentOea)
	index = property(_getIndexOea, _setIndexOea)
	goFirst = top
	goLast = bottom
	goLeft = pageUp
	goRight = pageDown

	def getTopIndex(self):
		return self.instance.getTopIndex() if self.instance is not None and hasattr(self.instance, "getTopIndex") else -1

	def setTopIndex(self, idx):
		if self.instance is not None and hasattr(self.instance, "setTopIndex"):
			self.instance.setTopIndex(idx)

	def updateEntry(self, idx, data):
		if self.list and 0 <= idx < len(self.list):
			self.list[idx] = data
			if hasattr(self.l, "updateEntry"):
				self.l.updateEntry(idx, data)
			else:
				vechi = self.getSelectedIndex()
				self.l.setList(self.list)
				self.moveToIndex(vechi)

	def getList(self):
		return self.list

	def count(self):
		return len(self.list)

	def selectionEnabled(self, enabled):
		if self.instance is not None:
			self.instance.setSelectionEnable(enabled)

	def enableAutoNavigation(self, enabled):
		"""Pluginurile scrise pentru alte imagini (FileCommander) opresc asa navigarea proprie a listei si muta cursorul din
		harta lor NavigationActions. La noi lista nativa nu se poate dezlega din Python; harta NavigationActions se leaga
		inaintea ei (Components/ActionMap.py), deci aici ramane numai alegerea."""
		self.navigareAutomata = bool(enabled)

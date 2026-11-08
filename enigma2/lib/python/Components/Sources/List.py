# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Source import Source
from Components.Element import cached

class List(Source, object):
	"""The datasource of a listbox. Currently, the format depends on the used converter. So
if you put a simple string list in here, you need to use a StringList converter, if you are
using a "multi content list styled"-list, you need to use the StaticMultiList converter, and
setup the "fonts". 

This has been done so another converter could convert the list to a different format, for example
to generate HTML."""
	def __init__(self, list = [ ], enableWrapAround = False, item_height = 25, fonts = [ ]):
		Source.__init__(self)
		self.__list = list
		self.onSelectionChanged = [ ]
		self.item_height = item_height
		self.fonts = fonts
		self.disable_callbacks = False
		self.enableWrapAround = enableWrapAround
		self.__style = "default" # style might be an optional string which can be used to define different visualisations in the skin

	def setList(self, list):
		self.__list = list
		self.changed((self.CHANGED_ALL,))

	list = property(lambda self: self.__list, setList)

	def entry_changed(self, index):
		if not self.disable_callbacks:
			self.downstream_elements.entry_changed(index)

	def modifyEntry(self, index, data):
		self.__list[index] = data
		self.entry_changed(index)

	def count(self):
		return len(self.__list)

	def selectionChanged(self, index):
		if self.disable_callbacks:
			return

		# update all non-master targets
		for x in self.downstream_elements:
			if x is not self.master:
				x.index = index

		for x in self.onSelectionChanged:
			x()

	@cached
	def getCurrent(self):
		# HDSatelit: o tema fara lista pentru sursa (numai un convertor ca StringListSelection, care n-are current) nu mai
		# opreste interfata la OK: nu e nimic ales
		return self.master is not None and getattr(self.master, "current", None)

	current = property(getCurrent)

	def setIndex(self, index):
		if self.master is not None:
			self.master.index = index
			self.selectionChanged(index)

	@cached
	def getIndex(self):
		if self.master is not None:
			return self.master.index
		else:
			return None

	setCurrentIndex = setIndex

	index = property(getIndex, setIndex)
	
	def selectNext(self):
		if self.getIndex() + 1 >= self.count():
			if self.enableWrapAround:
				self.index = 0
		else:
			self.index += 1
		self.setIndex(self.index)

	def selectPrevious(self):
		if self.getIndex() - 1 < 0:
			if self.enableWrapAround:
				self.index = self.count() - 1
		else:
			self.index -= 1
		self.setIndex(self.index)

	# la fel ca pe MenuList: pluginurile cheama self["list"].down() indiferent de felul listei
	def up(self):
		if self.master is not None and self.count():
			self.selectPrevious()

	def down(self):
		if self.master is not None and self.count():
			self.selectNext()

	def _instanta(self):
		"""widgetul listei: sursa -> convertor -> render"""
		x = self.master
		while x is not None and getattr(x, "instance", None) is None:
			x = getattr(x, "master", None)
		return x.instance if x is not None else None

	def _muta(self, directie):
		instanta = self._instanta()
		if instanta is not None:
			instanta.moveSelection(getattr(instanta, directie))

	def pageUp(self):
		self._muta("pageUp")

	def pageDown(self):
		self._muta("pageDown")

	def top(self):
		if self.master is not None and self.count():
			self.index = 0

	def bottom(self):
		if self.master is not None and self.count():
			self.index = self.count() - 1

	goTop = moveTop = top
	goBottom = moveBottom = bottom
	goLineUp = moveUp = selectPreviousEntry = up
	goLineDown = moveDown = selectNextEntry = down
	goPageUp = pageUp
	goPageDown = pageDown

	def getCurrentIndex(self):
		return self.getIndex()

	getSelectionIndex = getSelectedIndex = getCurrentIndex

	def getList(self):
		return self.__list

	def selectionEnabled(self, enabled):
		instanta = self._instanta()
		if instanta is not None:
			instanta.setSelectionEnable(enabled)

	@cached
	def getStyle(self):
		return self.__style

	def setStyle(self, style):
		if self.__style != style:
			self.__style = style
			self.changed((self.CHANGED_SPECIFIC, "style"))

	style = property(getStyle, setStyle)

	def updateList(self, list):
		"""Pastreaza selectia la aceeasi lungime; altfel inlocuieste lista."""
		if len(list) != len(self.__list):
			# Pluginurile pot reface meniul cu mai multe sau mai putine randuri.
			self.setList(list)
			return
		old_index = self.index
		self.disable_callbacks = True
		self.list = list
		self.index = old_index
		self.disable_callbacks = False

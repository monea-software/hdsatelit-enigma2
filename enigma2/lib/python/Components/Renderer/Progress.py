# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.VariableValue import VariableValue
try:
	from Components.VariableValue import intSigur
except ImportError:
	# o actualizare oprita la jumatatea dezarhivarii (0.7.3 -> 0.7.4): Renderer/Progress.py e in arhiva inaintea lui
	# VariableValue.py, deci poate fi nou langa VariableValue vechi, fara intSigur; fara copia de mai jos tema nu se
	# incarca si interfata nu mai porneste. Aceeasi functie ca in VariableValue.
	def intSigur(valoare):
		"""valoarea ca int pe 32 de biti (strans la margini); 0 pentru ce nu e numar"""
		try:
			valoare = int(valoare)
		except (TypeError, ValueError, OverflowError):
			return 0
		return max(-2147483648, min(2147483647, valoare))
from .Renderer import Renderer

from enigma import eSlider

class Progress(VariableValue, Renderer):
	def __init__(self):
		Renderer.__init__(self)
		VariableValue.__init__(self)
		self.__start = 0
		self.__end = 100

	GUI_WIDGET = eSlider

	def changed(self, what):
		if what[0] == self.CHANGED_CLEAR:
			(self.range, self.value) = ((0, 1), 0)
			return

		range = intSigur(self.source.range or 100) or 100
		value = intSigur(self.source.value)
		# bara arata numai intre 0 si capat: o pozitie aiurea (timeshift cu PTS-ul nereparat) nu iese din ea
		value = max(0, min(range, value)) if range > 0 else 0
		(self.range, self.value) = ((0, range), value)

	GUI_WIDGET = eSlider

	def postWidgetCreate(self, instance):
		instance.setRange(intSigur(self.__start), intSigur(self.__end))

	def setRange(self, range):
		(self.__start, self.__end) = range
		if self.instance is not None:
			self.instance.setRange(intSigur(self.__start), intSigur(self.__end))

	def getRange(self):
		return (self.__start, self.__end)

	range = property(getRange, setRange)

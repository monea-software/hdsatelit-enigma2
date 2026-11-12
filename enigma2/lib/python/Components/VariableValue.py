# Modificat de moneasoftware.com si hdsatelit.com, 2026
# eSlider.setValue/setRange iau un int pe 32 de biti: o valoare mai mare (de pilda pozitia din timeshift cu PTS-ul
# nereparat, „fixup PTS failed”) dadea OverflowError in poll si oprea interfata (cod 137). Valoarea se strange in int32.
_INT_MIN = -2147483648
_INT_MAX = 2147483647


def intSigur(valoare):
	"""valoarea ca int pe 32 de biti (strans la margini); 0 pentru ce nu e numar"""
	try:
		valoare = int(valoare)
	except (TypeError, ValueError, OverflowError):
		return 0
	return max(_INT_MIN, min(_INT_MAX, valoare))


class VariableValue(object):
	"""VariableValue can be used for components which have a variable value (like eSlider), based on any widget with setValue call"""
	
	def __init__(self):
		self.__value = 0

	def setValue(self, value):
		self.__value = value
		if self.instance:
			try:
				self.instance.setValue(intSigur(self.__value))
			except (TypeError, OverflowError):
				self.instance.setValue(0)

	def getValue(self):
		return self.__value

	def postWidgetCreate(self, instance):
		print(self)
		print(self.GUI_WIDGET)
		self.instance.setValue(intSigur(self.__value))

	value = property(getValue, setValue)

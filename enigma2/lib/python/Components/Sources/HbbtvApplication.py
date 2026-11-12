# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Sursa 'HbbtvApplication' ceruta de skin-urile si pluginurile scrise pentru alte imagini (<widget source="HbbtvApplication">
# cu boolean si name): este o aplicatie HbbTV pe canalul de acum si cum se numeste. Aplicatia HbbTV a imaginii noastre
# isi tine singura starea; aici numele se pune cu setApplicationName (gol = nicio aplicatie).
from Components.Element import cached
from Components.Sources.Source import Source


class HbbtvApplication(Source):
	def __init__(self):
		Source.__init__(self)
		self._nume = ""
		self._foloseste_ait = True

	def setApplicationName(self, name):
		self._nume = name or ""
		self.changed((self.CHANGED_ALL,))

	def getUseAit(self):
		return self._foloseste_ait

	@cached
	def getBoolean(self):
		return bool(self._nume)

	boolean = property(getBoolean)

	@cached
	def getName(self):
		return self._nume

	name = property(getName)

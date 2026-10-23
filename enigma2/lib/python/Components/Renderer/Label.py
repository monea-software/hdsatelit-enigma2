# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.VariableText import VariableText
from .Renderer import Renderer

from enigma import eLabel

class Label(VariableText, Renderer):
	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)

	GUI_WIDGET = eLabel

	def connect(self, source):
		Renderer.connect(self, source)
		self.changed((self.CHANGED_DEFAULT,))

	def changed(self, what):
		if what[0] == self.CHANGED_CLEAR:
			self.text = ""
		else:
			self.text = self.source.text
		self.potrivesteMarit()

	def applySkin(self, desktop, parent):
		ret = Renderer.applySkin(self, desktop, parent)
		self.potrivesteMarit()
		return ret

	# HDSatelit: with a larger text size (config.osd.fontscale over 100, Screens/FontSetup.py) the font of a one-line
	# text stays at the size the viewer chose; a text wider than its box scrolls (lib/gui/elabel.h, eDerulare) instead of
	# getting a smaller font. Nothing is done here any more; the name stays for the callers above.
	def potrivesteMarit(self):
		return


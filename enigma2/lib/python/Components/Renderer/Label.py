# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.VariableText import VariableText
from .Renderer import Renderer

from enigma import eLabel

class Label(VariableText, Renderer):
	def __init__(self):
		Renderer.__init__(self)
		VariableText.__init__(self)

	GUI_WIDGET = eLabel

	# HDSatelit 0.7.6 (TSR, raportul 2152): Renderer.connect (Element.connectUpstream) cheama deja changed, iar aici urma inca
	# unul, deci fiecare eticheta cerea textul convertorului de doua ori cand se construieste ecranul (readSkin). Un convertor de
	# tema care citeste din retea in getText (NOVTemp: 10,4 s la pornire) tinea firul interfetei de doua ori mai mult. Legatura
	# se face ca in Element.connect, fara cererea din mijloc; textul se cere o singura data, dupa ce legatura e completa (ca a
	# doua cerere de pana acum, a carei valoare ramanea).
	def connect(self, source):
		assert not self.SINGLE_SOURCE or self.source is None
		self.sources.append(source)
		self.source = source
		source.connectDownstream(self)
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


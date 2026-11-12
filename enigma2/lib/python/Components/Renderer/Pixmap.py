# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Atributul de skin pixmaps="a.png,b.png" (ca in imaginile OE-Alliance, 11.11.2026): imaginile se cauta in tema activa, iar
# textul numeric al sursei alege imaginea (de la 0; alt numar = nicio imagine). O sursa cu pixmap trece inainte, ca pana acum.
from .Renderer import Renderer

from enigma import ePixmap

class Pixmap(Renderer):
	def __init__(self):
		Renderer.__init__(self)
		self.pixmaps = []

	GUI_WIDGET = ePixmap

	def applySkin(self, desktop, parent):
		atribute = []
		for (attrib, value) in self.skinAttributes:
			if attrib == "pixmaps":
				try:
					from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
					from Tools.LoadPixmap import LoadPixmap
					self.pixmaps = [LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, x.strip())) for x in value.split(",") if x.strip()]
				except Exception as e:
					print("[Pixmap] pixmaps=%s: %s" % (value, e))
			else:
				atribute.append((attrib, value))
		self.skinAttributes = atribute
		rez = Renderer.applySkin(self, desktop, parent)
		if self.pixmaps:
			self.changed((self.CHANGED_DEFAULT,))
		return rez

	def postWidgetCreate(self, instance):
		self.changed((self.CHANGED_DEFAULT,))

	def changed(self, what):
		if what[0] != self.CHANGED_CLEAR:
			if self.pixmaps and self.instance and self.source and hasattr(self.source, "text") and not hasattr(self.source, "pixmap"):
				text = self.source.text
				i = int(text) if text and str(text).strip().isdigit() else 0
				self.instance.setPixmap(self.pixmaps[i] if 0 <= i < len(self.pixmaps) else None)
			if self.source and hasattr(self.source, "pixmap"):
				if self.instance:
					self.instance.setPixmap(self.source.pixmap)


# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.Pixmap import Pixmap

class UnhandledKey(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self["UnhandledKeyPixmap"] = Pixmap()

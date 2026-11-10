# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.VolumeBar import VolumeBar
		
class Volume(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		
		self.volumeBar = VolumeBar()
		
		self["Volume"] = self.volumeBar
		# tema externa: volumul si ca numar, cand tema il cere
		import skin
		if skin.dosareSkinStraine:
			from Components.Label import Label
			self["VolumeText"] = Label("")
		
	def setValue(self, vol):
		self.volumeBar.setValue(vol)
		if "VolumeText" in self:
			self["VolumeText"].setText(str(vol))

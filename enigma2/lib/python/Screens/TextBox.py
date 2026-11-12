from Screens.Screen import Screen

from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.ScrollLabel import ScrollLabel

class TextBox(Screen):
	def __init__(self, session, text = "", title = None, widget = None, skinName = None, label = None, skin_name = None, **altele):
		# HDSatelit: argumentele din alte imagini (pluginurile scrise pentru ele): title = titlul ferestrei, skinName/skin_name =
		# numele ecranului din skin; label sau widget = numele elementului de text (OE-Alliance; WanIP il cere ca „AboutScrollLabel”
		# si il citeste dupa nume). Cu alt nume decat „text”, ecranul TextBox al temei nu se mai ia ca rezerva (are elementul „text”).
		Screen.__init__(self, session)
		element = widget or label or "text"
		nume = skinName or skin_name
		if nume:
			self.skinName = (nume if isinstance(nume, list) else [nume]) + (["TextBox"] if element == "text" else [])
		self.text = text
		self[element] = ScrollLabel(self.text)
		if title:
			self.setTitle(title)
		
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions"], 
				{
					"cancel": self.cancel,
					"ok": self.ok,
					"up": self[element].pageUp,
					"down": self[element].pageDown,
				}, -1)
		
	def ok(self):
		self.close()
	
	def cancel(self):
		self.close()

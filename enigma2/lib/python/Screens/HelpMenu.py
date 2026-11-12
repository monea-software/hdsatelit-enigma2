# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.Pixmap import Pixmap, MovingPixmap
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.HelpMenuList import HelpMenuList
from Screens.Rc import Rc

class HelpMenu(Screen, Rc):
	def __init__(self, session, list):
		Screen.__init__(self, session)
		self.setTitle(_("Ajutor"))
		self.onSelChanged = [ ]
		self["list"] = HelpMenuList(list, self.close)
		self["list"].onSelChanged.append(self.SelectionChanged)
		Rc.__init__(self)
		self["long_key"] = Label("")

		self["actions"] = ActionMap(["WizardActions"], 
		{
			"ok": self["list"].ok,
			"back": self.close,
		}, -1)

		self.onLayoutFinish.append(self.SelectionChanged)

	def SelectionChanged(self):
		self.clearSelectedKeys()
		selection = self["list"].getCurrent()
		if selection:
			selection = selection[3]
		#arrow = self["arrowup"]

		longText = ""
		if selection and len(selection) > 1:
			if selection[1] == "SHIFT":
				self.selectKey("SHIFT")
			elif selection[1] == "long":
				longText = _("Long Keypress")
		self["long_key"].setText(longText)

		if selection:
			self.selectKey(selection[0])
		#if selection is None:
		#	arrow.moveTo(selection[1], selection[2], 1)
		#	arrow.startMoving()
		#	arrow.show()

class HelpableScreen:
	def __init__(self):
		self["helpActions"] = ActionMap( [ "HelpActions" ],
			{
				"displayHelp": self.showHelp,
			})

	def showHelp(self):
		self.session.openWithCallback(self.callHelpAction, HelpMenu, self.helpList)

	def callHelpAction(self, *args):
		if args:
			(actionmap, context, action) = args
			actionmap.action(context, action)


def showDocumentation(session, filename, translateFunc, callback=None):
	"""Documentatia XML a unui plugin din alte imagini (<help caption="..."><page title="..."><text value="..."/></page>):
	aici un ecran de text cu titlul si paginile una dupa alta. Un fisier care nu se poate citi lasa totul cum era."""
	import xml.etree.ElementTree as ET
	tradu = translateFunc if callable(translateFunc) else (lambda t: t)
	try:
		radacina = ET.parse(filename).getroot()
	except Exception as e:
		print("[HelpMenu] documentatia %s: %r" % (filename, e))
		return
	bucati = []
	for pagina in radacina.iter("page"):
		# ca in OE-Alliance: titlul paginii din heading sau title; randurile noi scrise „/n” in valori (MPHelp, AutoTimer)
		titlu_pagina = pagina.get("heading") or pagina.get("title")
		if titlu_pagina:
			bucati.append(tradu(titlu_pagina).replace("/n", "\n"))
		for el in pagina.iter():
			if el is pagina:
				continue
			for text in (el.get("value"), el.get("text"), el.text):
				if text and text.strip():
					bucati.append(tradu(text.strip()).replace("/n", "\n"))
		bucati.append("")
	from Screens.TextBox import TextBox
	titlu = tradu(radacina.get("caption", "")) if radacina.get("caption") else ""
	if callable(callback):
		session.openWithCallback(callback, TextBox, "\n".join(bucati).strip(), title=titlu)
	else:
		session.open(TextBox, "\n".join(bucati).strip(), title=titlu)

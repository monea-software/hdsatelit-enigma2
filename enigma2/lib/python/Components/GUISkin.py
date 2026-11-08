# Modificat de moneasoftware.com si hdsatelit.com, 2026
from traceback import print_exc
from .GUIComponent import GUIComponent
from skin import applyAllAttributes
from Tools.CList import CList
from .Sources.StaticText import StaticText

def _intregi(fabrica):
	"""ePoint/eSize care primesc si numere cu virgula (rotunjite); restul argumentelor trec neschimbate"""
	def fa(*argumente):
		return fabrica(*[int(round(a)) if isinstance(a, float) else a for a in argumente])
	return fa


def _execApplet(cod, g, l):
	"""Codul din skin (applet). Sub o tema externa scrisa pentru Python 2 (pozitii cu "/", deci numere cu virgula, pe
	care ePoint si eSize nu le primesc: "argument 1 of type 'int'") ePoint si eSize rotunjesc, cat ruleaza codul.
	Pe temele noastre codul ruleaza exact ca pana acum."""
	try:
		from skin import altSkinActiv
		extern = altSkinActiv()
	except Exception:
		extern = False
	if not extern:
		exec((cod), g, l)
		return
	import enigma
	vechi = (enigma.ePoint, enigma.eSize)
	enigma.ePoint, enigma.eSize = _intregi(vechi[0]), _intregi(vechi[1])
	g = dict(g)
	g["ePoint"], g["eSize"] = enigma.ePoint, enigma.eSize
	try:
		exec((cod), g, l)
	finally:
		enigma.ePoint, enigma.eSize = vechi


class GUISkin:
	__module__ = __name__

	def __init__(self):
		self["Title"] = StaticText()
		self["ScreenPath"] = StaticText()
		self.onLayoutFinish = [ ]
		self.summaries = CList()
		self.instance = None
		self.desktop = None

	def createGUIScreen(self, parent, desktop, updateonly = False):
		for val in self.renderer:
			if isinstance(val, GUIComponent):
				if not updateonly:
					val.GUIcreate(parent)
				if not val.applySkin(desktop, self):
					print("warning, skin is missing renderer", val, "in", self)

		for key in self:
			val = self[key]
			if isinstance(val, GUIComponent):
				if not updateonly:
					val.GUIcreate(parent)
				depr = val.deprecationInfo
				if val.applySkin(desktop, self):
					if depr:
						print("WARNING: OBSOLETE COMPONENT '%s' USED IN SKIN. USE '%s' INSTEAD!" % (key, depr[0]))
						print("OBSOLETE COMPONENT WILL BE REMOVED %s, PLEASE UPDATE!" % (depr[1]))
				elif not depr:
					print("warning, skin is missing element", key, "in", self)

		for w in self.additionalWidgets:
			if not updateonly:
				w.instance = w.widget(parent)
				# w.instance.thisown = 0
			applyAllAttributes(w.instance, desktop, w.skinAttributes, self.scale)

		# HDSatelit: pictograma internetului ascunsa din setari: vecinii ei la locul lor de dinainte de pictograma
		# (Components/HdsPictogramaBare; numai ecranele cu pictograma au ce muta)
		try:
			from Components.HdsPictogramaBare import aseaza
			aseaza(self)
		except Exception:
			print_exc()

		# HDSatelit: sigla canalului pe bare: vecinii ei (atributul vecini al widgetului Picon) se muta la dreapta numai cat
		# se vede o sigla adevarata (Components/HdsPiconBare; dupa pictograma internetului, ca mutarile sa se adune)
		try:
			from Components.HdsPiconBare import aseaza as aseazaSigla
			aseazaSigla(self)
		except Exception:
			print_exc()

		# HDSatelit: cu textul marit (Marimea textului peste 100 %), etichetele pe un rand mai joase decat literele cresc
		# (textul ramane pe loc), iar textele fixe pe un rand care ies din caseta lor se potrivesc (Components/HdsMarireText);
		# la 100 % nu se face nimic
		# (numai pe televizor: ecranele afisajului din fata, *Summary, au desktopul lor si raman cum sunt)
		try:
			from enigma import getDesktop
			tv = getDesktop(0).size()
			ds = desktop.size() if desktop is not None else tv
			if ds.width() == tv.width() and ds.height() == tv.height():
				from Components.HdsMarireText import potrivesteInaltimile, potrivesteEticheteleFixe
				potrivesteInaltimile(self)
				potrivesteEticheteleFixe(self)
		except Exception:
			print_exc()

		for f in self.onLayoutFinish:
			# codul din skin (applet) sau o functie gresita nu opreste receptorul: jurnal si mai departe
			try:
				if type(f) is not type(self.close): # is this the best way to do this?
					_execApplet(f, globals(), locals())
				else:
					f()
			except Exception:
				print("[Skin] error in onLayoutFinish of %s:" % self.__class__.__name__)
				print_exc()

	def deleteGUIScreen(self):
		for (name, val) in list(self.items()):
			if isinstance(val, GUIComponent):
				val.GUIdelete()

	def close(self):
		self.deleteGUIScreen()

	def createSummary(self):
		return None

	def addSummary(self, summary):
		self.summaries.append(summary)

	def removeSummary(self, summary):
		self.summaries.remove(summary)

	# HDSatelit: titlul ecranului tinut si ca screenTitle, numele din alte imagini; pluginurile lor il citesc pe orice ecran
	screenTitle = ""

	def setTitle(self, title):
		self.screenTitle = title
		if self.instance:
			self.instance.setTitle(title)
		self["Title"].text = title
		self.summaries.setTitle(title)

	def getTitle(self):
		return self["Title"].text

	title = property(getTitle, setTitle)

	def setDesktop(self, desktop):
		self.desktop = desktop

	def applySkin(self):
		z = 0
		baseres = (720, 576) # FIXME: a skin might have set another resolution, which should be the base res
		idx = 0
		skin_title_idx = -1
		title = self.title
		for (key, value) in self.skinAttributes:
			if key == "zPosition":
				z = int(value)
			elif key == "title":
				skin_title_idx = idx
				if title:
					self.skinAttributes[skin_title_idx] = ("title", title)
				else:
					self["Title"].text = value
					self.summaries.setTitle(value)
			elif key == "baseResolution":
				baseres = tuple([int(x) for x in value.split(',')])
			idx += 1
		self.scale = ((baseres[0], baseres[0]), (baseres[1], baseres[1]))

		if not self.instance:
			from enigma import eWindow
			self.instance = eWindow(self.desktop, z)
			# HDSatelit: un ecran al nostru sub alt skin ales (stilHds, pus de skin.readSkin) ia stilul ferestrelor
			# HDSatelit inainte sa se faca elementele lui (care iau stilul ferestrei): fundalul si culorile raman ale noastre
			if getattr(self, "stilHds", False):
				import skin
				skin.puneStilHds(self.instance)

		if skin_title_idx == -1 and title:
			self.skinAttributes.append(("title", title))

		# we need to make sure flags and transparent come first (before size/decorations), and position comes last
		self.skinAttributes.sort(key=lambda a: {"flags": -3, "transparent": -2, "zPosition": -1, "position": 1}.get(a[0], 0))

		applyAllAttributes(self.instance, self.desktop, self.skinAttributes, self.scale)
		self.createGUIScreen(self.instance, self.desktop)

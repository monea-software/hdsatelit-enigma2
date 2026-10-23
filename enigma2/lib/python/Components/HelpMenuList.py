# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .GUIComponent import GUIComponent

from enigma import eListboxPythonMultiContent, eListbox, RT_VALIGN_CENTER
from Tools.KeyBindings import queryKeyBinding, getKeyDescription
from skin import getListFont, getParameterFromSkin
#getKeyPositions

# The rows are drawn here; the skin can set their look (names as used by other enigma2 skins, defaults = 2011):
#   <alias name="HelpMenuList"/>: font and row height; <alias name="HelpMenuListExt0"/> and "HelpMenuListExt1":
#   the two fonts of the rows with two lines (and their height); HelpMenuListHlp, HelpMenuListExtHlp0,
#   HelpMenuListExtHlp1: x,y,w,h of the text of a row with one line and of the two lines

# [ ( actionmap, context, [(action, help), (action, help), ...] ), (actionmap, ... ), ... ]


def cuLiteraMare(text):
	"""Randul din Ajutor incepe cu litera mare, in orice limba: o parte din textele vechi ale actiunilor sunt scrise cu
	litera mica (in romana, de pilda, "afișare EPG pentru un singur canal..."). Prima litera a textului se face mare; in
	turca i mic devine I cu punct."""
	if not text:
		return text
	for i, c in enumerate(text):
		if not c.isalpha():
			continue
		if not c.islower():
			return text
		mare = c.upper()
		if c == "i":
			try:
				from Components.config import config
				if config.osd.language.value.startswith("tr"):
					mare = "\u0130"
			except Exception:
				pass
		return text[:i] + mare + text[i + 1:]
	return text


class HelpMenuList(GUIComponent):
	def __init__(self, helplist, callback):
		GUIComponent.__init__(self)
		self.onSelChanged = [ ]
		self.l = eListboxPythonMultiContent()
		self.callback = callback
		self.extendedHelp = False

		l = [ ]
		# un rand pe fapta: lista arata numai textul, deci doua randuri cu acelasi text (aceeasi fapta pe doua taste, de
		# pilda GALBEN si AUDIO pentru ecranul sunetului) sau aceeasi actiune scrisa de doua ori in lista de ajutor a
		# ecranului ar fi doua randuri la fel; ramane primul
		vazute = set()
		for (actionmap, context, actions) in helplist:
			for (action, help) in actions:
				buttons = queryKeyBinding(context, action)

				# do not display entries which are not accessible from keys
				if not len(buttons):
					continue

				primul = help[0] if isinstance(help, list) else help
				text = cuLiteraMare(primul)
				if (context, action) in vazute or ("text", text) in vazute:
					continue
				vazute.add((context, action))
				vazute.add(("text", text))

				name = None
				flags = 0

				for n in buttons:
					(name, flags) = (getKeyDescription(n[0]), n[1])
					if name is not None:
						break

				# o tasta care lipseste din descrierile telecomenzii nu are nume: randul ramane, fara tasta aratata
				# pe telecomanda
				if name and flags & 8: # for long keypresses, prepend l_ into the key name.
					name = (name[0], "long")
					
				entry = [ (actionmap, context, action, name ) ]

				if isinstance(help, list):
					self.extendedHelp = True
					print("extendedHelpEntry found")
					r0, s0 = getParameterFromSkin("HelpMenuListExtHlp0", (0, 0, 400, 26))
					r1, s1 = getParameterFromSkin("HelpMenuListExtHlp1", (0, 28, 400, 20))
					entry.extend((
						(eListboxPythonMultiContent.TYPE_TEXT, r0[0], r0[1], r0[2], r0[3], 0, s0 and RT_VALIGN_CENTER or 0, cuLiteraMare(help[0])),
						(eListboxPythonMultiContent.TYPE_TEXT, r1[0], r1[1], r1[2], r1[3], 1, s1 and RT_VALIGN_CENTER or 0, help[1])
					))
				else:
					r, s = getParameterFromSkin("HelpMenuListHlp", (0, 0, 400, 28))
					entry.append( (eListboxPythonMultiContent.TYPE_TEXT, r[0], r[1], r[2], r[3], 0, s and RT_VALIGN_CENTER or 0, cuLiteraMare(help)) )

				l.append(entry)

		self.l.setList(l)
		if self.extendedHelp is True:
			font, height = getListFont("HelpMenuListExt0", ("Regular", 24, 50))
			self.l.setFont(0, font)
			self.l.setFont(1, getListFont("HelpMenuListExt1", ("Regular", 18))[0])
			self.l.setItemHeight(height)
		else:
			font, height = getListFont("HelpMenuList", ("Regular", 24, 38))
			self.l.setFont(0, font)
			self.l.setItemHeight(height)

	def ok(self):
		# a list entry has a "private" tuple as first entry...
		l = self.getCurrent()
		if l is None:
			return
		# ...containing (Actionmap, Context, Action, keydata).
		# we returns this tuple to the callback.
		self.callback(l[0], l[1], l[2])

	def getCurrent(self):
		sel = self.l.getCurrentSelection()
		return sel and sel[0]

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)

	def preWidgetRemove(self, instance):
		instance.setContent(None)
		instance.selectionChanged.get().remove(self.selectionChanged)

	def selectionChanged(self):
		for x in self.onSelChanged:
			x()

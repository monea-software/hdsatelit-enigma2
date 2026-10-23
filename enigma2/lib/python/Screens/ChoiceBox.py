# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen
from Components.ActionMap import NumberActionMap
from Components.Label import Label
from Components.ChoiceList import ChoiceEntryComponent, ChoiceList
from Components.Sources.StaticText import StaticText

DIGIT_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

class ChoiceBox(Screen):
	def __init__(self, session, title = "", list = [], keys = None, selection = 0, skin_name = []):
		Screen.__init__(self, session)

		if isinstance(skin_name, str):
			skin_name = [skin_name]
		self.skinName = skin_name + ["ChoiceBox"] 

		self["text"] = Label(title)
		# titlul ferestrei: cel pus de apelant cu setTitle dupa deschidere, altfel unul general (bara de sus nu ramane goala)
		self.setTitle(_("Alege"))
		self.list = []
		self.summarylist = []
		# only a list that gets no key at all from ChoiceBox (no keys from the caller, more rows than digits) lets
		# green pick the highlighted row; see keyGreen
		self.__greenPicksHighlighted = keys is None and len(list) > len(DIGIT_KEYS)
		if keys is None:
			# Without keys from the caller: the digits 1..9, 0 only when the whole list fits in them, a longer list
			# gets no key at all. A key on only some rows moves their text to another margin (ChoicelistName versus
			# ChoicelistNameSingle), and a color key bound to a fixed row picks that row whatever row is highlighted.
			keys = DIGIT_KEYS[:len(list)] if len(list) <= len(DIGIT_KEYS) else []
		self.__keys = keys + (len(list) - len(keys)) * [""]
			
		self.keymap = {}
		pos = 0
		for x in list:
			strpos = str(self.__keys[pos])
			self.list.append(ChoiceEntryComponent(key = strpos, text = x))
			if self.__keys[pos] != "":
				self.keymap[self.__keys[pos]] = list[pos]
			self.summarylist.append((self.__keys[pos],x[0]))
			pos += 1
		self["list"] = ChoiceList(list = self.list, selection = selection)
		self["summary_list"] = StaticText()
		self.updateSummary()
				
		self["actions"] = NumberActionMap(["WizardActions", "InputActions", "ColorActions", "DirectionActions"], 
		{
			"ok": self.go,
			"back": self.cancel,
			"1": self.keyNumberGlobal,
			"2": self.keyNumberGlobal,
			"3": self.keyNumberGlobal,
			"4": self.keyNumberGlobal,
			"5": self.keyNumberGlobal,
			"6": self.keyNumberGlobal,
			"7": self.keyNumberGlobal,
			"8": self.keyNumberGlobal,
			"9": self.keyNumberGlobal,
			"0": self.keyNumberGlobal,
			"red": self.keyRed,
			"green": self.keyGreen,
			"yellow": self.keyYellow,
			"blue": self.keyBlue,
			"up": self.up,
			"down": self.down
		}, -1)
		# cu textul marit randurile cresc (Components/ChoiceList.py) si lista se strange la randuri intregi; fereastra
		# creste ea, ca sa se vada cate randuri se vad la 100 % (hdsRanduriMarite)
		self.onLayoutFinish.append(self.hdsRanduriMarite)

	def hdsRanduriMarite(self):
		"""Textul marit (Marimea textului peste 100 %): lista arata cate randuri arata caseta ei din skin (toate, cand la
		100 % incap toate). Lista creste cu diferenta, ce e sub ea coboara, iar fereastra creste pe acelasi centru, cat
		incape pe ecran. La 100 % nimic nu se schimba."""
		try:
			from Components.HdsMarireText import procent
			from enigma import eSize, ePoint, getDesktop
			p = procent()
			lista = self["list"]
			inst = lista.instance
			if p <= 100 or inst is None or self.instance is None:
				return
			a = dict(lista.skinAttributes or ())
			rand_skin = int(a.get("itemHeight", 0))
			inalt_skin = int(str(a.get("size", "0,0")).split(",")[1])
			if rand_skin <= 0 or inalt_skin <= 0:
				return
			rand = rand_skin * p // 100
			randuri = min(len(self.list), inalt_skin // rand_skin)
			pl, ml = inst.position(), inst.size()
			d = randuri * rand - ml.height()
			if d <= 0:
				return
			fereastra, pozitie = self.instance.size(), self.instance.position()
			ecran = getDesktop(0).size().height()
			# cat incape pe ecran: randuri intregi
			loc = ecran - fereastra.height()
			if d > loc:
				d = max(0, (ml.height() + loc) // rand * rand - ml.height())
				if d <= 0:
					return
			jos = pl.y() + ml.height()
			for x in list(self.values()) + list(self.renderer) + list(self.additionalWidgets):
				w = getattr(x, "instance", None)
				if w is None or w is inst:
					continue
				pw = w.position()
				if pw.y() >= jos:
					w.move(ePoint(pw.x(), pw.y() + d))
			inst.resize(eSize(ml.width(), ml.height() + d))
			y = max(0, min(pozitie.y() - d // 2, ecran - fereastra.height() - d))
			self.instance.resize(eSize(fereastra.width(), fereastra.height() + d))
			self.instance.move(ePoint(pozitie.x(), y))
		except Exception as e:
			print("[ChoiceBox] randurile la textul marit:", e)

	def keyLeft(self):
		pass
	
	def keyRight(self):
		pass
	
	def up(self):
		if len(self["list"].list) > 0:
			while 1:
				self["list"].instance.moveSelection(self["list"].instance.moveUp)
				self.updateSummary(self["list"].l.getCurrentSelectionIndex())
				if self["list"].l.getCurrentSelection()[0][0] != "--" or self["list"].l.getCurrentSelectionIndex() == 0:
					break

	def down(self):
		if len(self["list"].list) > 0:
			while 1:
				self["list"].instance.moveSelection(self["list"].instance.moveDown)
				self.updateSummary(self["list"].l.getCurrentSelectionIndex())
				if self["list"].l.getCurrentSelection()[0][0] != "--" or self["list"].l.getCurrentSelectionIndex() == len(self["list"].list) - 1:
					break

	# runs a number shortcut
	def keyNumberGlobal(self, number):
		self.goKey(str(number))

	# runs the current selected entry
	def go(self):
		cursel = self["list"].l.getCurrentSelection()
		if cursel:
			self.goEntry(cursel[0])
		else:
			self.cancel()

	# runs a specific entry
	def goEntry(self, entry):
		if len(entry) > 2 and isinstance(entry[1], str) and entry[1] == "CALLFUNC":
			# CALLFUNC wants to have the current selection as argument
			arg = self["list"].l.getCurrentSelection()[0]
			entry[2](arg)
		else:
			self.close(entry)

	# lookups a key in the keymap, then runs it
	def goKey(self, key):
		if key in self.keymap:
			entry = self.keymap[key]
			self.goEntry(entry)

	# runs a color shortcut
	def keyRed(self):
		self.goKey("red")

	def keyGreen(self):
		# A long list without keys (see __init__): green picks the highlighted row, like OK. Everywhere else green does
		# only what the caller bound to it, as before: in a short list with digits, a list opened with keys=[] or a
		# question with "Yes" on the first row, green alone never picks a row.
		if self.__greenPicksHighlighted:
			self.go()
		else:
			self.goKey("green")

	def keyYellow(self):
		self.goKey("yellow")

	def keyBlue(self):
		self.goKey("blue")

	def updateSummary(self, curpos=0):
		pos = 0
		summarytext = ""
		for entry in self.summarylist:
			if pos > curpos-2 and pos < curpos+5:
				if pos == curpos:
					summarytext += ">"
				else:
					summarytext += entry[0]
				summarytext += ' ' + entry[1] + '\n'
			pos += 1
		self["summary_list"].setText(summarytext)

	def cancel(self):
		self.close(None)

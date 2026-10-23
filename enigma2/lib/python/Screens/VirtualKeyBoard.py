# -*- coding: UTF-8 -*-
# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_CENTER, RT_VALIGN_CENTER, getPrevAsciiCode
from .Screen import Screen
from Components.Language import language
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label
try:
	# HDSatelit: campul de text pe un rand (cand nu mai incape, se vede coada); fara modul, eticheta obisnuita
	from Components.HdsCampText import CampText
except ImportError:
	CampText = Label
from Components.Pixmap import Pixmap
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap

def _dinTastatura():
	"""Ultima tasta a venit de la o tastatura adevarata (Components/HdsTastaturaUsb.py); fara modul, False."""
	try:
		from Components.HdsTastaturaUsb import dinTastatura
	except ImportError:
		return False
	return dinTastatura()


class VirtualKeyBoardList(MenuList):
	def __init__(self, list, enableWrapAround=False):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		self.l.setFont(0, gFont("Regular", 28))
		self.l.setItemHeight(45)

def VirtualKeyBoardEntryComponent(keys, selectedKey,shiftMode=False):
	key_backspace = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_backspace.png"))
	key_bg = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_bg.png"))
	key_clr = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_clr.png"))
	key_esc = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_esc.png"))
	key_ok = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_ok.png"))
	key_sel = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_sel.png"))
	key_shift = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_shift.png"))
	key_shift_sel = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_shift_sel.png"))
	key_space = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/vkey_space.png"))
	res = [ (keys) ]
	
	x = 0
	count = 0
	if shiftMode:
		shiftkey_png = key_shift_sel
	else:
		shiftkey_png = key_shift
	for key in keys:
		width = None
		if key == "EXIT":
			width = key_esc.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_esc))
		elif key == "BACKSPACE":
			width = key_backspace.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_backspace))
		elif key == "CLEAR":
			width = key_clr.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_clr))
		elif key == "SHIFT":
			width = shiftkey_png.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=shiftkey_png))
		elif key == "SPACE":
			width = key_space.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_space))
		elif key == "OK":
			width = key_ok.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_ok))
		#elif key == "<-":
		#	res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(45, 45), png=key_left))
		#elif key == "->":
		#	res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(45, 45), png=key_right))
		
		else:
			width = key_bg.size().width()
			res.extend((
				MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_bg),
				MultiContentEntryText(pos=(x, 0), size=(width, 45), font=0, text=key, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER)
			))
		
		if selectedKey == count:
			width = key_sel.size().width()
			res.append(MultiContentEntryPixmapAlphaTest(pos=(x, 0), size=(width, 45), png=key_sel))

		if width is not None:
			x += width
		else:
			x += 45
		count += 1
	
	return res


class VirtualKeyBoard(Screen):

	def __init__(self, session, title="", text=""):
		Screen.__init__(self, session)
		self.keys_list = []
		self.shiftkeys_list = []
		self.lang = language.getLanguage()
		self.nextLang = None
		self.shiftMode = False
		self.text = text
		self.selectedKey = 0
		# HDSatelit: cu o tastatura adevarata tastele de pe ecran nu se arata (Components/HdsTastaturaUsb.py): ramane
		# campul de text, Enter = gata, Esc = renunta, Backspace = sterge; o sageata de pe telecomanda le aduce inapoi
		self.modTastatura = False
		# locul si marimea ferestrei din skin (pozitia de dat lui move, marimea fara rama), tinute minte la prima strangere
		self.locSkin = None
		
		self["country"] = StaticText("")
		self["header"] = Label(title)
		# HDSatelit: campul pe un rand; cand textul nu mai incape, se vede coada lui, ce scrii acum
		# (Components/HdsCampText.py)
		self["text"] = CampText(self.text)
		self["list"] = VirtualKeyBoardList([])
		
		self["actions"] = ActionMap(["OkCancelActions", "WizardActions", "ColorActions", "KeyboardInputActions", "InputBoxActions", "InputAsciiActions"],
			{
				"gotAsciiCode": self.keyGotAscii,
				"ok": self.okClicked,
				"cancel": self.exit,
				"left": self.left,
				"right": self.right,
				"up": self.up,
				"down": self.down,
				"red": self.backClicked,
				"green": self.ok,
				"yellow": self.switchLang,
				"deleteBackward": self.backClicked,
				"back": self.exit				
			}, -2)
		self.setLang()
		self.onExecBegin.append(self.setKeyboardModeAscii)
		self.onLayoutFinish.append(self.buildVirtualKeyBoard)
		self.onLayoutFinish.append(self._laDeschidere)

	def _laDeschidere(self):
		if _dinTastatura():
			self.punModTastatura(True)

	def punModTastatura(self, da):
		self.modTastatura = da
		if da:
			self["list"].hide()
		else:
			self["list"].show()
		self._potrivesteFereastra()

	def _josCamp(self):
		"""Marginea de jos a campului de text in fereastra (cu fundalul si linia lui din skin, adica elementele
		eLabel/ePixmap care stau pe aceleasi randuri cu el) plus o margine egala cu cea din stanga campului; None fara
		camp."""
		text = getattr(self["text"], "instance", None)
		if text is None:
			return None
		sus = text.position().y()
		jos = sus + text.size().height()
		stanga = text.position().x()
		elemente = [getattr(w, "instance", None) for w in getattr(self, "additionalWidgets", [])]
		elemente = [e for e in elemente if e is not None]
		for _ in range(2):      # o linie lipita sub fundalul campului se vede abia dupa ce fundalul a crescut josul
			for e in elemente:
				y = e.position().y()
				h = e.size().height()
				if y < jos and y + h > sus:
					jos = max(jos, y + h)
					stanga = min(stanga, e.position().x())
		return jos + max(stanga, 0)

	def _potrivesteFereastra(self):
		"""Fara tastele de pe ecran fereastra se strange pana sub camp: tastele si randurile de sub ele raman in afara
		ei, deci sub camp nu mai ramane loc gol, pe orice skin (marimea vine din locul campului in skin). Fereastra
		ramane pe acelasi mijloc. Cu tastele inapoi (o sageata de pe telecomanda) ia din nou locul si marimea din skin."""
		inst = getattr(self, "instance", None)
		if inst is None:
			return
		try:
			from enigma import eSize, ePoint
		except ImportError:
			return
		if self.locSkin is None:
			# move() adauga deplasarea ramei ferestrei (titlul), iar position() o da cu ea: pozitia de dat lui move()
			# pentru locul din skin se afla mutand fereastra pe locul ei si vazand unde ajunge
			p = inst.position()
			inst.move(p)
			q = inst.position()
			self.locSkin = (ePoint(2 * p.x() - q.x(), 2 * p.y() - q.y()), inst.csize())
		poz, marime = self.locSkin
		h = marime.height()
		if self.modTastatura:
			jos = self._josCamp()
			if jos is not None:
				h = min(h, jos)
		inst.resize(eSize(marime.width(), h))
		inst.move(ePoint(poz.x(), poz.y() + (marime.height() - h) // 2))

	def _sageata(self):
		"""In modul tastatura: True = sageata nu misca nimic (de la tastatura nu are ce misca: campul nu are cursor);
		de la telecomanda tastele de pe ecran se arata din nou."""
		if not self.modTastatura:
			return False
		if not _dinTastatura():
			self.punModTastatura(False)
		return True
	
	def switchLang(self):
		self.lang = self.nextLang
		self.setLang()
		self.buildVirtualKeyBoard()

	def setLang(self):
		if self.lang == 'de_DE':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ü", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "ß", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "Ü", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "OK"]]
			self.nextLang = 'es_ES'
		elif self.lang == 'es_ES':
			#still missing keys (u"ùÙ")
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ú", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ó", "á", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "Ł", "ŕ", "é", "č", "í", "ě", "ń", "ň", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "Ú", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ó", "Á", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Ŕ", "É", "Č", "Í", "Ě", "Ń", "Ň", "OK"]]
			self.nextLang = 'fi_FI'
		elif self.lang == 'fi_FI':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "é", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "ß", "ĺ", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "É", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Ĺ", "OK"]]
			self.nextLang = 'sv_SE'
		elif self.lang == 'sv_SE':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "é", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "@", "ß", "ĺ", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "É", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ö", "Ä", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Ĺ", "OK"]]
			self.nextLang = 'sk_SK'
		elif self.lang =='sk_SK':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ú", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ľ", "@", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "š", "č", "ž", "ý", "á", "í", "é", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "ť", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "ň", "ď", "'"],
				["Á", "É", "Ď", "Í", "Ý", "Ó", "Ú", "Ž", "Š", "Č", "Ť", "Ň"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "ä", "ö", "ü", "ô", "ŕ", "ĺ", "OK"]]
			self.nextLang = 'cs_CZ'
		elif self.lang == 'cs_CZ':
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ú", "+"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "ů", "@", "#"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "ě", "š", "č", "ř", "ž", "ý", "á", "í", "é", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "ť", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "ň", "ď", "'"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "?", "\\", "Č", "Ř", "Š", "Ž", "Ú", "Á", "É", "OK"]]
			self.nextLang = 'ro_RO'
		elif self.lang == 'ro_RO':
			# HDSatelit: tastatura romaneasca (QWERTY, cu a, i, a cu caciula, s si t cu virgula dedesubt), tot 5 randuri de
			# 12 taste, ca restul (skinul are loc numai pentru atat)
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\u0103", "\u00ee"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "\u0219", "\u021b", "\u00e2"],
				["-", "z", "x", "c", "v", "b", "n", "m", ",", ".", "@", "CLEAR"],
				["SHIFT", "SPACE", "_", "/", ":", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "#", "$", "%", "&", "'", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\u0102", "\u00ce"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "\u0218", "\u021a", "\u00c2"],
				["+", "Z", "X", "C", "V", "B", "N", "M", ";", "?", "*", "CLEAR"],
				["SHIFT", "SPACE", "<", ">", "\\", "OK"]]
			self.nextLang = 'en_EN'
		else:
			self.keys_list = [
				["EXIT", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACKSPACE"],
				["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "+", "@"],
				["a", "s", "d", "f", "g", "h", "j", "k", "l", "#", "\\"],
				["<", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "CLEAR"],
				["SHIFT", "SPACE", "OK"]]
			self.shiftkeys_list = [
				["EXIT", "!", '"', "§", "$", "%", "&", "/", "(", ")", "=", "BACKSPACE"],
				["Q", "W", "E", "R", "T", "Z", "U", "I", "O", "P", "*"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", "'", "?"],
				[">", "Y", "X", "C", "V", "B", "N", "M", ";", ":", "_", "CLEAR"],
				["SHIFT", "SPACE", "OK"]]
			self.lang = 'en_EN'
			self.nextLang = 'de_DE'		
		self["country"].setText(self.lang)
		self.max_key=47+len(self.keys_list[4])

	def buildVirtualKeyBoard(self, selectedKey=0):
		list = []
		
		if self.shiftMode:
			self.k_list = self.shiftkeys_list
			for keys in self.k_list:
				if selectedKey < 12 and selectedKey > -1:
					list.append(VirtualKeyBoardEntryComponent(keys, selectedKey,True))
				else:
					list.append(VirtualKeyBoardEntryComponent(keys, -1,True))
				selectedKey -= 12
		else:
			self.k_list = self.keys_list
			for keys in self.k_list:
				if selectedKey < 12 and selectedKey > -1:
					list.append(VirtualKeyBoardEntryComponent(keys, selectedKey))
				else:
					list.append(VirtualKeyBoardEntryComponent(keys, -1))
				selectedKey -= 12
		
		self["list"].setList(list)
	
	def backClicked(self):
		self.text = self["text"].getText()[:-1]
		self["text"].setText(self.text)
			
	def okClicked(self):
		if self.modTastatura:
			return self.ok()
		if self.shiftMode:
			list = self.shiftkeys_list
		else:
			list = self.keys_list
		
		selectedKey = self.selectedKey

		text = None

		for x in list:
			if selectedKey < 12:
				if selectedKey < len(x):
					text = x[selectedKey]
				break
			else:
				selectedKey -= 12

		if text is None:
			return

		if text == "EXIT":
			self.close(None)
		
		elif text == "BACKSPACE":
			self.text = self["text"].getText()[:-1]
			self["text"].setText(self.text)
		
		elif text == "CLEAR":
			self.text = ""
			self["text"].setText(self.text)
		
		elif text == "SHIFT":
			if self.shiftMode:
				self.shiftMode = False
			else:
				self.shiftMode = True
			
			self.buildVirtualKeyBoard(self.selectedKey)
		
		elif text == "SPACE":
			self.text += " "
			self["text"].setText(self.text)
		
		elif text == "OK":
			self.close(self["text"].getText())
		
		else:
			self.text = self["text"].getText()
			self.text += text
			self["text"].setText(self.text)

	def ok(self):
		self.close(self["text"].getText())

	def exit(self):
		self.close(None)

	def left(self):
		if self._sageata():
			return
		self.selectedKey -= 1
		
		if self.selectedKey == -1:
			self.selectedKey = 11
		elif self.selectedKey == 11:
			self.selectedKey = 23
		elif self.selectedKey == 23:
			self.selectedKey = 35
		elif self.selectedKey == 35:
			self.selectedKey = 47
		elif self.selectedKey == 47:
			self.selectedKey = self.max_key
		
		self.showActiveKey()

	def right(self):
		if self._sageata():
			return
		self.selectedKey += 1
		
		if self.selectedKey == 12:
			self.selectedKey = 0
		elif self.selectedKey == 24:
			self.selectedKey = 12
		elif self.selectedKey == 36:
			self.selectedKey = 24
		elif self.selectedKey == 48:
			self.selectedKey = 36
		elif self.selectedKey > self.max_key:
			self.selectedKey = 48
		
		self.showActiveKey()

	def up(self):
		if self._sageata():
			return
		self.selectedKey -= 12
		
		if (self.selectedKey < 0) and (self.selectedKey > (self.max_key-60)):
			self.selectedKey += 48
		elif self.selectedKey < 0:
			self.selectedKey += 60	
		
		self.showActiveKey()

	def down(self):
		if self._sageata():
			return
		self.selectedKey += 12
		
		if (self.selectedKey > self.max_key) and (self.selectedKey > 59):
			self.selectedKey -= 60
		elif self.selectedKey > self.max_key:
			self.selectedKey -= 48
		
		self.showActiveKey()

	def showActiveKey(self):
		self.buildVirtualKeyBoard(self.selectedKey)

	def inShiftKeyList(self,key):
		for KeyList in self.shiftkeys_list:
			for char in KeyList:
				if char == key:
					return True
		return False

	def keyGotAscii(self):
		# caracterele vin numai de la o tastatura adevarata (consola): tastele de pe ecran se ascund si se scrie orice
		# caracter, nu numai cele care sunt pe tastele de pe ecran
		char = chr(getPrevAsciiCode())
		if not self.modTastatura:
			self.punModTastatura(True)
		if char >= " ":
			self.text = self["text"].getText() + char
			self["text"].setText(self.text)

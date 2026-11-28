# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent
from .VariableText import VariableText

from enigma import eLabel

from Tools.NumericalTextInput import NumericalTextInput
import unicodedata

class Input(VariableText, HTMLComponent, GUIComponent, NumericalTextInput):
	TEXT = 0
	PIN = 1
	NUMBER = 2

	# currPos si allMarked ca in enigma2 OE-Alliance: pluginurile (editorul din File Commander) le dau prin InputBox
	def __init__(self, text="", maxSize = False, visible_width = False, type = TEXT, currPos = 0, allMarked = True):
		NumericalTextInput.__init__(self, self.right)
		GUIComponent.__init__(self)
		VariableText.__init__(self)
		self.type = type
		self.allmarked = allMarked and (text != "") and (type != self.PIN)
		self.maxSize = maxSize
		self.currPos = currPos
		self.visible_width = visible_width
		self.offset = 0
		self.overwrite = maxSize
		self.setText(text)
		
	def __len__(self):
		return len(self.text)

	def update(self):
		if self.visible_width:
			if self.currPos < self.offset:
				self.offset = self.currPos
			if self.currPos >= self.offset + self.visible_width:
				if self.currPos == len(self.Text):
					self.offset = self.currPos - self.visible_width
				else:
					self.offset = self.currPos - self.visible_width + 1
			if self.offset > 0 and self.offset + self.visible_width > len(self.Text):
				self.offset = max(0, len(self.Text) - self.visible_width)
		if self.allmarked:
			self.setMarkedPos(-2)
		else:
			self.setMarkedPos(self.currPos-self.offset)
		# si PIN-ul se vede cat il scrii (fara stelute)
		if self.visible_width:
			self.text = self.Text[self.offset:self.offset+self.visible_width] + " "
		else:
			self.text = self.Text + " "

	def setText(self, text):
		if not len(text):
			self.currPos = 0
			self.Text = ""
		else:
			if isinstance(text, bytes):
				text = text.decode("utf-8", "replace")
			self.Text = text
		self.update()

	def getText(self):
		return self.Text

	def createWidget(self, parent):
		if self.allmarked:
			return eLabel(parent, -2)
		else:
			return eLabel(parent, self.currPos-self.offset)

	def getSize(self):
		s = self.instance.calculateSize()
		return (s.width(), s.height())
	
	def innerright(self):
		if self.allmarked:
			self.currPos = 0
			self.allmarked = False
		elif self.maxSize:
			if self.currPos < len(self.Text)-1:
				self.currPos += 1
		else:
			if self.currPos < len(self.Text):
				self.currPos += 1

	def right(self):
		if self.type == self.TEXT:
			self.timeout()
		self.innerright()
		self.update()

	def left(self):
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			if self.maxSize:
				self.currPos = len(self.Text) - 1
			else:
				self.currPos = len(self.Text)
			self.allmarked = False
		elif self.currPos > 0:
			self.currPos -= 1
		self.update()

	def up(self):
		if self._secretOprit():
			return
		self.allmarked = False
		if self.type == self.TEXT:
			self.timeout()
		if self.currPos == len(self.Text) or self.Text[self.currPos] == "9" or self.Text[self.currPos] == " ":
			newNumber = "0"
		else:
			newNumber = str(int(self.Text[self.currPos]) + 1)
		self.Text = self.Text[0:self.currPos] + newNumber + self.Text[self.currPos + 1:]
		self.update()

	def down(self):
		if self._secretOprit():
			return
		self.allmarked = False
		if self.type == self.TEXT:
			self.timeout()
		if self.currPos == len(self.Text) or self.Text[self.currPos] == "0" or self.Text[self.currPos] == " ":
			newNumber = "9"
		else:
			newNumber = str(int(self.Text[self.currPos]) - 1)
		self.Text = self.Text[0:self.currPos] + newNumber + self.Text[self.currPos + 1:]
		self.update()
		
	def home(self):
		self.allmarked = False
		if self.type == self.TEXT:
			self.timeout()
		self.currPos = 0
		self.update()
	
	def end(self):
		self.allmarked = False
		if self.type == self.TEXT:
			self.timeout()
		if self.maxSize:
			self.currPos = len(self.Text) - 1
		else:
			self.currPos = len(self.Text)
		self.update()

	@staticmethod
	def graniteText(text):
		"""Logical editing boundaries, including marks and joined emoji."""
		granite = [0]
		regionale = 0
		for i, c in enumerate(text):
			cod = ord(c)
			regional = 0x1f1e6 <= cod <= 0x1f1ff
			lipit = (unicodedata.category(c).startswith("M") or 0x1f3fb <= cod <= 0x1f3ff
				or c == "\u200d" or (i and text[i - 1] == "\u200d")
				or (i and text[i - 1] == "\r" and c == "\n")
				or (regional and regionale % 2))
			if i and not lipit:
				granite.append(i)
			regionale = regionale + 1 if regional else 0
		if text:
			granite.append(len(text))
		return granite

	def deplaseazaText(self, comanda):
		"""Move in logical text order; never reverse offsets for RTL."""
		if self.type == self.TEXT:
			self.timeout()
		text = self.Text
		poz = max(0, min(self.currPos, len(text)))
		granite = self.graniteText(text)
		poz = max(p for p in granite if p <= poz)
		def cuvant(c):
			return c == "_" or unicodedata.category(c)[0] in "LNM"
		if comanda == "inceput":
			poz = max(text.rfind("\n", 0, poz), text.rfind("\r", 0, poz)) + 1
		elif comanda == "sfarsit":
			poz = min([p for p in (text.find("\n", poz), text.find("\r", poz)) if p >= 0] + [len(text)])
		elif comanda == "cuvant-inapoi":
			while poz and not cuvant(text[poz - 1]):
				poz -= 1
			while poz and cuvant(text[poz - 1]):
				poz -= 1
		elif comanda == "cuvant-inainte":
			while poz < len(text) and not cuvant(text[poz]):
				poz += 1
			while poz < len(text) and cuvant(text[poz]):
				poz += 1
		elif comanda == "caracter-inapoi":
			poz = max([p for p in granite if p < poz] or [0])
		elif comanda == "caracter-inainte":
			poz = min([p for p in granite if p > poz] or [len(text)])
		else:
			return
		poz = min([p for p in granite if p >= poz] or [len(text)])
		limita = max(0, len(text) - 1) if self.maxSize else len(text)
		self.currPos = max(p for p in granite if p <= min(poz, limita))
		self.allmarked = False
		self.update()

	def insereazaText(self, text):
		"""Insert at the logical cursor using the existing input contract."""
		if self._secretOprit():
			return
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		for c in text:
			self.insertChar(c, self.currPos, False, False)
			self.innerright()
		self.update()

	def stergeInainteCursor(self):
		"""Delete one complete editing unit before the cursor."""
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		elif self.currPos > 0:
			poz = min(self.currPos, len(self.Text))
			inceput = max(p for p in self.graniteText(self.Text) if p < poz)
			for _ in range(poz - inceput):
				self.deleteChar(inceput)
			self.currPos = inceput
		self.update()

	def insertChar(self, ch, pos, owr, ins):
		if getattr(self, "hdsSecret", self.type == self.PIN):
			from Components.HdsAsistentaControl import cereOprirePentruSecret
			if cereOprirePentruSecret(getattr(self, "hdsSession", None)):
				return
		if ins and not self.maxSize:
			self.Text = self.Text[0:pos] + ch + self.Text[pos:]
		elif owr or self.overwrite:
			self.Text = self.Text[0:pos] + ch + self.Text[pos + 1:]
		elif self.maxSize:
			self.Text = self.Text[0:pos] + ch + self.Text[pos:-1]
		else:
			self.Text = self.Text[0:pos] + ch + self.Text[pos:]

	def deleteChar(self, pos):
		if not self.maxSize:
			self.Text = self.Text[0:pos] + self.Text[pos + 1:]
		elif self.overwrite:
			self.Text = self.Text[0:pos] + " " + self.Text[pos + 1:]
		else:
			self.Text = self.Text[0:pos] + self.Text[pos + 1:] + " "

	def deleteAllChars(self):
		if self.maxSize:
			self.Text = " " * len(self.Text)
		else:
			self.Text = ""
		self.currPos = 0

	def tab(self):
		if self._secretOprit():
			return
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		else:
			self.insertChar(" ", self.currPos, False, True);
			self.innerright()
		self.update()

	def delete(self):
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		else:
			self.deleteChar(self.currPos);
			if self.maxSize and self.overwrite:
				self.innerright()
		self.update()

	def deleteBackward(self):
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		else:
			if self.currPos > 0:
				self.deleteChar(self.currPos-1);
				if not self.maxSize and self.offset > 0:
					self.offset -= 1
				self.currPos -= 1
		self.update()

	def toggleOverwrite(self):
		if self.type == self.TEXT:
			self.timeout()
		self.overwrite = not self.overwrite
		self.update()

	def handleAscii(self, code):
		if self._secretOprit():
			return
		if self.type == self.TEXT:
			self.timeout()
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		self.insertChar(chr(code), self.currPos, False, False);
		self.innerright()
		self.update()

	def number(self, number):
		if self._secretOprit():
			return
		unic = False
		if self.type == self.TEXT:
			# o tasta cu un singur caracter permis (0 la un CAID hexazecimal, cu useableChars) scrie si trece la pozitia
			# urmatoare, ca la cifre: altfel a doua apasare scria peste aceeasi pozitie si „0B00” iesea „0B0” (CI, 11.11.2026)
			unic = self._tastaCuUnCaracter(number)
			owr = self.lastKey == number and not unic
			newChar = self.getKey(number)
		elif self.type == self.PIN or self.type == self.NUMBER:
			owr = False
			newChar = str(number)
		if self.allmarked:
			self.deleteAllChars()
			self.allmarked = False
		self.insertChar(newChar, self.currPos, owr, False);
		if unic:
			self.nextKey()
			self.innerright()
		elif self.type == self.PIN or self.type == self.NUMBER:
			self.innerright()
		self.update()

	def _tastaCuUnCaracter(self, number):
		"""True cand tasta `number` are, cu useableChars, un singur caracter permis (fara ciclu de litere)"""
		u = getattr(self, "useableChars", None)
		if not u:
			return False
		try:
			return len(set(c for c in self.mapping[number] if c in u)) == 1
		except (IndexError, TypeError):
			return False

	def _secretOprit(self):
		if not getattr(self, "hdsSecret", self.type == self.PIN):
			return False
		from Components.HdsAsistentaControl import cereOprirePentruSecret
		return cereOprirePentruSecret(getattr(self, "hdsSession", None))

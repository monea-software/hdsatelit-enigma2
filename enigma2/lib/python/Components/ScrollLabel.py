# Modificat de moneasoftware.com si hdsatelit.com, 2026
import skin
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent
from enigma import eLabel, eWidget, eSlider, fontRenderClass, ePoint, eSize

class ScrollLabel(HTMLComponent, GUIComponent):
	def __init__(self, text=""):
		GUIComponent.__init__(self)
		self.message = text
		self.instance = None
		self.long_text = None
		self.scrollbar = None
		self.pages = None
		self.total = None
		# showOnDemand (bara numai cand textul are mai multe pagini), showAlways, showNever; din skin
		self.scrollbarMode = "showOnDemand"

	def applySkin(self, desktop, parent):
		ret = False
		if self.skinAttributes is not None:
			# scrollbarMode e al barei de derulare, nu al etichetei: eLabel nu il are („attribute not applied” in jurnal)
			atribute = []
			for (attrib, value) in self.skinAttributes:
				if attrib == "scrollbarMode":
					if value in ("showOnDemand", "showAlways", "showNever"):
						self.scrollbarMode = value
					else:
						skin.skinWarning("ScrollLabel: scrollbarMode=\"%s\" not applied" % value)
				else:
					atribute.append((attrib, value))
			self.skinAttributes = atribute
			skin.applyAllAttributes(self.long_text, desktop, self.skinAttributes, parent.scale)
			widget_attribs = [ ]
			scrollbar_attribs = [ ]
			for (attrib, value) in self.skinAttributes:
				if attrib.find("borderColor") != -1 or attrib.find("borderWidth") != -1:
					scrollbar_attribs.append((attrib,value))
				if attrib.find("transparent") != -1 or attrib.find("backgroundColor") != -1 or attrib == "zPosition":
					widget_attribs.append((attrib,value))
			skin.applyAllAttributes(self.instance, desktop, widget_attribs, parent.scale)
			skin.applyAllAttributes(self.scrollbar, desktop, scrollbar_attribs+widget_attribs, parent.scale)
			ret = True
		s = self.long_text.size()
		self.instance.move(self.long_text.position())
		lineheight=fontRenderClass.getInstance().getLineHeight( self.long_text.getFont() )
		if not lineheight:
			lineheight = 30 # assume a random lineheight if nothing is visible
		lines = (int)(s.height() // lineheight)
		self.pageHeight = (int)(lines * lineheight)
		self.instance.resize(eSize(s.width(), self.pageHeight+(int)(lineheight//6)))
		self.scrollbar.move(ePoint(s.width()-20,0))
		self.scrollbar.resize(eSize(20,self.pageHeight+(int)(lineheight//6)))
		self.scrollbar.setOrientation(eSlider.orVertical);
		self.scrollbar.setRange(0,100)
		self.scrollbar.setBorderWidth(1)
		self.long_text.move(ePoint(0,0))
		self.long_text.resize(eSize(s.width()-30, max(self.pageHeight*64, 32768)))
		self.setText(self.message)
		return ret

	def setText(self, text):
		if text is None:
			text = ""
		elif isinstance(text, str):
			# Filtram caracterele surogate (U+D800 pana la U+DFFF) pentru compatibilitate garantata cu SWIG std::string
			text = "".join(c for c in text if ord(c) < 0xD800 or ord(c) > 0xDFFF)
		elif isinstance(text, bytes):
			text = text.decode("utf-8", "replace")
		else:
			text = str(text)

		self.message = text
		if self.long_text is None:
			return
		self.long_text.move(ePoint(0,0))
		try:
			self.long_text.setText(self.message)
		except Exception as e:
			print("[ScrollLabel setText error]", type(self.message), e)
			try:
				self.long_text.setText(self.message.encode("utf-8", "replace").decode("latin1"))
			except Exception:
				pass
		# HDSatelit (blocaj real gasit si reprodus in emulator, "main thread is non-idle! display
		# spinner!", la LogManagerViewLog): daca applySkin() nu a asezat inca widget-ul (skinAttributes
		# None, de exemplu la primul apel al lui setText() dintr-un ecran nou, inainte ca skin-ul sa fi fost
		# rezolvat), pageHeight poate iesi 0 SAU NEGATIV. Codul vechi verifica doar "if self.pageHeight"
		# (adevarat pentru orice valoare nenula, inclusiv negativa) si intra in bucla de paginare de mai jos
		# -- cu pageHeight negativ, "total" SCADE la fiecare pas in loc sa creasca, deci "while total <
		# text_height" nu se opreste niciodata cand text_height e pozitiv: bucla infinita, thread-ul
		# principal ramane blocat la nesfarsit. Garda de mai jos cere explicit pageHeight POZITIV inainte de
		# a intra in bucla; textul tot s-a asezat mai sus, doar paginarea/scrollbar-ul raman nedisponibile
		# pana la un applySkin ulterior cu geometrie valida.
		if not (self.pageHeight and self.pageHeight > 0):
			if self.scrollbar is not None:
				self.scrollbar.hide()
			self.total = None
			self.pages = None
			return
		text_height=self.long_text.calculateSize().height()
		# HDSatelit: eticheta lunga are cel putin max(pageHeight*64, 32768) puncte
		# (applySkin); un text mai inalt (un jurnal de mii de randuri) se numara pe pagini dupa toata inaltimea lui, dar se
		# desena numai pana la capatul etichetei, deci ultimele pagini ieseau goale. Eticheta creste cat textul; asezarea
		# textului (lib/gdi/font.cpp) nu se opreste oricum la inaltimea etichetei, iar desenul ramane taiat la ce se vede.
		marime = self.long_text.size()
		if text_height + self.pageHeight > marime.height():
			self.long_text.resize(eSize(marime.width(), text_height + self.pageHeight))
		total=self.pageHeight
		pages=1
		while total < text_height:
			total=total+self.pageHeight
			pages=pages+1
		if pages > 1:
			self.total = total
			self.pages = pages
			# getattr: o extensie care mosteneste ScrollLabel fara ScrollLabel.__init__ nu are atributul
			if getattr(self, "scrollbarMode", "showOnDemand") == "showNever":
				self.scrollbar.hide()
			else:
				self.scrollbar.show()
				self.updateScrollbar()
		else:
			self.total = None
			self.pages = None
			if getattr(self, "scrollbarMode", "showOnDemand") == "showAlways":
				self.scrollbar.setStartEnd(0, 100)
				self.scrollbar.show()
			else:
				self.scrollbar.hide()

	def appendText(self, text):
		old_text = self.getText() or ""
		if len(old_text) > 0:
			self.setText(old_text + text)
		else:
			self.setText(text)

	def updateScrollbar(self):
		start = -self.long_text.position().y() * 100 // self.total
		vis = self.pageHeight * 100 // self.total;
		self.scrollbar.setStartEnd(start, start+vis)

	def getText(self):
		return self.message

	def GUIcreate(self, parent):
		self.instance = eWidget(parent)
		self.scrollbar = eSlider(self.instance)
		self.long_text = eLabel(self.instance)

	def GUIdelete(self):
		self.long_text = None
		self.scrollbar = None
		self.instance = None

	def pageUp(self):
		if self.total is not None:
			curPos = self.long_text.position()
			if curPos.y() < 0:
				self.long_text.move( ePoint( curPos.x(), curPos.y() + self.pageHeight ) )
				self.updateScrollbar()

	def pageDown(self):
		if self.total is not None:
			curPos = self.long_text.position()
			if self.total-self.pageHeight >= abs( curPos.y() - self.pageHeight ):
				self.long_text.move( ePoint( curPos.x(), curPos.y() - self.pageHeight ) )
				self.updateScrollbar()

	def firstPage(self):
		if self.total is not None and self.long_text is not None:
			curPos = self.long_text.position()
			self.long_text.move(ePoint(curPos.x(), 0))
			self.updateScrollbar()

	def lastPage(self):
		# HDSatelit: pages is None when the text fits on one page. Python 2 took 1 < None as false;
		# Python 3 raises TypeError, and in Screens.Console (runFinished, called from C++) that ended in bsodFatal.
		if self.pages is None:
			return
		i=1
		while i < self.pages:
			self.pageDown()
			i += 1 
			self.updateScrollbar()

	def produceHTML(self):
		return self.getText()

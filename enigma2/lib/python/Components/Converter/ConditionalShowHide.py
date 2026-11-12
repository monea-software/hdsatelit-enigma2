# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Argumentele ca in imaginile OE-Alliance (11.11.2026): Invert, Blink, despartite de "," sau ";", si un numar = pasul clipirii in
# milisecunde (implicit 500). Convertorul e transparent: ce nu are el (text, value, range, service...) se cere sursei de dinainte,
# ca un ConditionalShowHide pus intre un convertor si un Label sau Progress sa nu le taie datele.
from enigma import eTimer
from .Converter import Converter

class ConditionalShowHide(Converter, object):
	# hdsTrece: un element de dupa a citit prin el ceva al sursei (text, value...): de atunci primeste si schimbarile, ca sa
	# citeasca iar (altfel un Label dupa ConditionalShowHide ar ramane cu textul vechi dupa schimbarea canalului)
	hdsTrece = False

	def __init__(self, argstr):
		Converter.__init__(self, argstr)
		args = [a.strip() for a in (argstr or "").replace(";", ",").split(',')]
		self.invert = "Invert" in args
		self.blink = "Blink" in args
		self.blinktime = 500
		for a in args:
			if a.isdigit() and int(a) > 0:
				self.blinktime = int(a)
		if self.blink:
			self.timer = eTimer()
			self.timer.callback.append(self.blinkFunc)
		else:
			self.timer = None

	def blinkFunc(self):
		if self.blinking == True:
			for x in self.downstream_elements:
				x.visible = not x.visible

	def startBlinking(self):
		self.blinking = True
		self.timer.start(self.blinktime)

	def stopBlinking(self):
		self.blinking = False
		for x in self.downstream_elements:
			if x.visible:
				x.hide()
		self.timer.stop()

	def calcVisibility(self):
		b = self.source.boolean
		if b is None:
			return True
		b ^= self.invert
		return b

	def changed(self, what):
		vis = self.calcVisibility()
		if self.blink:
			if vis:
				self.startBlinking()
			else:
				self.stopBlinking()
		else:
			for x in self.downstream_elements:
				x.visible = vis
		if self.hdsTrece:
			Converter.changed(self, what)

	def connectDownstream(self, downstream):
		Converter.connectDownstream(self, downstream)
		vis = self.calcVisibility()
		if self.blink:
			if vis:
				self.startBlinking()
			else:
				self.stopBlinking()
		else:
			downstream.visible = self.calcVisibility()

	def destroy(self):
		if self.timer:
			self.timer.callback.remove(self.blinkFunc)

	def __getattr__(self, name):
		# numai ce nu gaseste Python pe obiect; source si numele ascunse nu se cer mai departe (fara bucla in __init__)
		if name.startswith("_") or name in ("source", "downstream_elements", "master", "blinking", "timer", "hdsTrece"):
			raise AttributeError(name)
		source = self.__dict__.get("source")
		if source is None:
			raise AttributeError(name)
		valoare = getattr(source, name)
		self.__dict__["hdsTrece"] = True
		return valoare

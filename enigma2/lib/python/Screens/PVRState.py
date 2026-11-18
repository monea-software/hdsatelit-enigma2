# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen

from Components.Label import Label


def pozitiePunct(x_bara, latime_bara, pozitie, lungime):
	"""x-ul punctului PTSSeekPointer ca in OE-Alliance (ptsSeekPointerSetCurrentPos): marginea din stanga a barei PTSSeekBack,
	plus 8, plus procentul intreg redat din latimea barei; temele sunt desenate dupa formula asta. None cand nu se stie lungimea."""
	if pozitie is None or lungime is None or lungime < 1:
		return None
	return int(x_bara) + 8 + int((float(int((pozitie * 100) / lungime)) / 100) * latime_bara)

class PVRState(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self["state"] = Label(text="")
		# temele straine (numele standard ale ferestrei de stare la redare si timeshift): numele emisiunii, viteza,
		# pictograma starii si indicatorul de pozitie; numai sub alta tema decat HD Satelit (HdsNumeStandard)
		from Components.HdsNumeStandard import adauga
		from Components.Pixmap import MultiPixmap, Pixmap
		if adauga(self, "eventname", Label) is not None:
			self.onShow.append(self._numeEmisiune)
		adauga(self, "speed", Label)
		adauga(self, "statusicon", MultiPixmap, ascuns=True)
		adauga(self, "PTSSeekBack", Pixmap, ascuns=True)
		# punctul de pe bara timeshift si bara lui (TSR 0.7.6, wlad-sat: ramaneau ascunse): punctul se muta dupa pozitia redarii
		# cand fereastra se arata si apoi o data pe secunda cat ramane pe ecran (OE-Alliance il muta numai la aratare); fara
		# pozitie raman ascunse
		if adauga(self, "PTSSeekPointer", Pixmap, ascuns=True) is not None:
			from enigma import eTimer
			self.hdsCeasPunct = eTimer()
			self.hdsCeasPunct.callback.append(self.mutaPunct)
			self.onShow.append(self._punctPornit)
			self.onHide.append(self._punctOprit)
			self.onClose.append(self._punctOprit)

	def _punctPornit(self):
		self.mutaPunct()
		self.hdsCeasPunct.start(1000, False)

	def _punctOprit(self):
		self.hdsCeasPunct.stop()

	def _pozitieRedare(self):
		"""(pozitia, lungimea) redarii, in unitatile seek, sau None cand serviciul nu se poate derula"""
		try:
			serviciu = self.session.nav.getCurrentService()
			seek = serviciu and serviciu.seek()
			if seek is None or not seek.isCurrentlySeekable():
				return None
			lungime = seek.getLength()
			pozitie = seek.getPlayPosition()
		except Exception as e:
			print("[PVRState] pozitia redarii: %s" % e)
			return None
		if lungime[0] or pozitie[0]:
			return None
		return pozitie[1], lungime[1]

	def mutaPunct(self):
		"""PTSSeekPointer la pozitia redarii pe bara PTSSeekBack (pozitiePunct); amandoua se vad, ca in OE-Alliance, numai cand
		serviciul se poate derula si se stie lungimea, altfel raman ascunse"""
		punct = self.get("PTSSeekPointer")
		bara = self.get("PTSSeekBack")
		if getattr(punct, "instance", None) is None or getattr(bara, "instance", None) is None:
			return
		x = None
		redare = self._pozitieRedare()
		if redare is not None:
			x = pozitiePunct(bara.instance.position().x(), bara.instance.size().width(), redare[0], redare[1])
		if x is None:
			punct.hide()
			bara.hide()
			return
		punct.setPosition(x, punct.position[1])
		bara.show()
		punct.show()

	def _numeEmisiune(self):
		"""numele emisiunii redate (al inregistrarii sau al canalului din timeshift), cand se stie"""
		nume = ""
		try:
			serviciu = self.session.nav.getCurrentService()
			info = serviciu and serviciu.info()
			ev = info and info.getEvent(0)
			nume = ev and ev.getEventName() or ""
		except Exception:
			pass
		self["eventname"].setText(nume)

	def stareTema(self, stare):
		"""Pictograma starii si viteza pentru temele straine (0.7.5, MOH), dupa textul starii redarii, ca in OE-Alliance:
		poza 0 redare, 1 pauza, 2 sfarsit, 3 inainte, 4 inapoi, 5 incet; viteza "8x" la derulare, "/2" la incet.
		Fara tema straina (statusicon nepus de HdsNumeStandard) nu face nimic."""
		if getattr(self, "hdsCeasPunct", None) is not None:
			self.mutaPunct()
		if "statusicon" not in self:
			return
		viteza = ""
		if stare == ">":
			poza = 0
		elif stare == "||":
			poza = 1
		elif stare == "END":
			poza = 2
		elif stare.startswith(">>") or stare.startswith("<<"):
			poza = 3 if stare.startswith(">>") else 4
			bucati = stare.split()
			viteza = bucati[-1] if len(bucati) > 1 else ""
		elif stare.startswith("/"):
			poza = 5
			viteza = stare
		else:
			return
		try:
			self["statusicon"].setPixmapNum(poza)
			self["statusicon"].show()
		except Exception as e:
			print("[PVRState] statusicon: %s" % e)
		if "speed" in self:
			self["speed"].setText(viteza)

class TimeshiftState(PVRState):
	pass

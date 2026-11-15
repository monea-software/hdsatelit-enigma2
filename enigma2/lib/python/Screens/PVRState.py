# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen

from Components.Label import Label

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
		adauga(self, "PTSSeekPointer", Pixmap, ascuns=True)

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

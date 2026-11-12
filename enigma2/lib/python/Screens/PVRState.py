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

class TimeshiftState(PVRState):
	pass

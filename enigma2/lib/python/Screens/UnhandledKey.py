# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import ePoint, eSize
from .Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap


class UnhandledKey(Screen):
	"""Semnul aratat doua secunde cand tasta apasata nu face nimic pe ecranul de acum (InfoBarGenerics.InfoBarUnhandledKey);
	nu ia focul (e un dialog al sesiunii, ca inainte)."""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["UnhandledKeyPixmap"] = Pixmap()
		# HDSatelit: in locul unui patrat fara explicatie, temele noastre scriu si de ce nu s-a intamplat nimic. Eticheta e chiar panoul (fundalul si colturile rotunjite din tema); o tema care n-o are (temele straine:
		# numai poza) ramane cum era.
		self["UnhandledKeyText"] = Label(_("Tastă nefolosită în acest ecran"))
		self.onLayoutFinish.append(self.potrivesteLatimea)

	def potrivesteLatimea(self):
		"""Panoul cat textul din limba aleasa (de la 380 la 730 px la 1080p): eticheta se strange la textul ei cu tot cu
		marginile (padding) si fereastra o data cu ea, iar marginea dreapta ramane unde a pus-o tema. Un text mai lung decat
		eticheta din tema ramane in eticheta (nimic nu iese din ecran)."""
		eticheta = self["UnhandledKeyText"]
		if eticheta.instance is None or self.instance is None:
			return
		if eticheta.skinAttributes is None:
			# tema n-are eticheta: nimic in plus fata de poza ei
			eticheta.hide()
			return
		e = eticheta.instance
		latimeTema = e.size().width()
		latime = min(latimeTema, e.calculateSize().width() + 2)
		minus = latimeTema - latime
		if minus <= 0:
			return
		inaltime = e.size().height()
		e.resize(eSize(latime, inaltime))
		fereastra = self.instance
		loc, marime = fereastra.position(), fereastra.size()
		fereastra.move(ePoint(loc.x() + minus, loc.y()))
		fereastra.resize(eSize(marime.width() - minus, marime.height()))

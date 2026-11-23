# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen

# VOL8: cu bara de volum la mijloc (Screens/Volume.laMijloc) semnul de mut sta si el la mijloc, in aceeasi fasie: caseta
# de 96x96 centrata, cu chenar rosu (ecranul "MuteMijloc" al temei, daca il are, altfel cel de aici, pe 1920x1080).
SKIN_MIJLOC = ('<screen name="MuteMijloc" resolution="1920,1080" position="912,764" size="96,96" '
	'backgroundColor="hdsPanelDialog" flags="wfNoBorder">'
	'<eLabel position="0,0" size="96,2" backgroundColor="hdsBad" zPosition="1" />'
	'<eLabel position="0,94" size="96,2" backgroundColor="hdsBad" zPosition="1" />'
	'<eLabel position="0,2" size="2,92" backgroundColor="hdsBad" zPosition="1" />'
	'<eLabel position="94,2" size="2,92" backgroundColor="hdsBad" zPosition="1" />'
	'<ePixmap pixmap="icon/mute.png" position="24,24" size="48,48" alphatest="blend" zPosition="2" />'
	'</screen>')


class Mute(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		try:
			from Screens.Volume import laMijloc
			mijloc = laMijloc()
		except Exception:
			mijloc = False
		if mijloc:
			self.skinName = "MuteMijloc"
			self.skin = SKIN_MIJLOC

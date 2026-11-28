# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.VolumeBar import VolumeBar

# VOL8 (ozgurc67, Vu+ Solo SE): bara la mijloc, aleasa in Meniu > Audio & Sound Tracks > Volum și întârziere ("Locul barei
# de volum") sau in web (/volum-intarziere). Numai cu tema HD Satelit (Clasic sau Pro): ecranul "VolumeMijloc" al temei,
# daca il are vreodata, altfel cel scris aici (scris pe 1920x1080; skin.py il mareste la 2K si il micsoreaza la 720p,
# ca pe celelalte ecrane din cod cu resolution=). Cu o tema straina ramane mereu ecranul "Volume" al temei.
# Asezarea (1920x1080): caseta de 960x120 centrata pe orizontala, in treimea de jos (y 752..872), iconita, bara lata si,
# cand e ceruta, numarul (HdsBold 72: "100" are 123 px, 159 px cu Marimea textului la 130%, caseta lui 168: VOL1,
# tamiciav7, 0.8.0; inainte 152, care taia zeroul de la 110%). Semnul de mut la mijloc: Screens/Mute.py.
MIJLOC_X, MIJLOC_Y, MIJLOC_L, MIJLOC_I = 480, 752, 960, 120


def _chenar(l, i, culoare, g=2):
	return "".join('<eLabel position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="1" />' % (x, y, w, h, culoare)
		for x, y, w, h in ((0, 0, l, g), (0, i - g, l, g), (0, g, g, i - 2 * g), (l - g, g, g, i - 2 * g)))


def skinMijloc(cuNumar):
	"""Ecranul barei de volum la mijloc (cu sau fara numar), scris pe 1920x1080."""
	l, i = MIJLOC_L, MIJLOC_I
	capat = 784 - 24 if cuNumar else l - 28
	numar = ('<widget name="VolumeText" conditional="VolumeText" position="768,12" size="168,96" font="HdsBold;72" '
		'foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" halign="right" valign="center" '
		'zPosition="2" />') if cuNumar else ""
	return ('<screen name="VolumeMijloc" resolution="1920,1080" position="%d,%d" size="%d,%d" '
		'backgroundColor="hdsPanelDialog" flags="wfNoBorder">' % (MIJLOC_X, MIJLOC_Y, l, i) +
		_chenar(l, i, "hdsTrack") +
		'<ePixmap pixmap="icon/vol.png" position="28,36" size="48,48" alphatest="blend" zPosition="2" />'
		'<eLabel position="100,48" size="%d,24" backgroundColor="hdsTrack" zPosition="1" />' % (capat - 100) +
		'<widget name="Volume" conditional="Volume" position="102,50" size="%d,20" foregroundColor="hdsBrandLight" '
		'backgroundColor="hdsTrack" zPosition="2" />' % (capat - 104) +
		numar + '</screen>')


def _setari():
	try:
		from Components import HdsSetariSunet
		return HdsSetariSunet
	except Exception as e:
		print("[Volume] Components/HdsSetariSunet.py nu se poate incarca: %s" % e)
		return None


def temaStraina():
	try:
		import skin
		return bool(skin.dosareSkinStraine)
	except Exception:
		return False


def laMijloc():
	"""True cand bara se pune la mijloc: setarea e "La mijloc" si tema e HD Satelit."""
	s = _setari()
	try:
		return s is not None and s.locVolum() == "mijloc" and not temaStraina()
	except Exception:
		return False


def cuNumar():
	"""Numarul langa bara: cu o tema straina cand tema il cere (ca pana atunci), cu tema HD Satelit dupa setare."""
	if temaStraina():
		return True
	s = _setari()
	try:
		return s is not None and s.numarVolum()
	except Exception:
		return False


class Volume(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		
		self.volumeBar = VolumeBar()
		
		self["Volume"] = self.volumeBar
		self.mijloc = laMijloc()
		self.numar = cuNumar()
		if self.mijloc:
			self.skinName = "VolumeMijloc"
			self.skin = skinMijloc(self.numar)
		# volumul si ca numar: tema externa cand il cere, tema HD Satelit cand e ales (VOL8)
		if self.numar:
			from Components.Label import Label
			self["VolumeText"] = Label("")
		
	def setValue(self, vol):
		self.volumeBar.setValue(vol)
		if "VolumeText" in self:
			self["VolumeText"].setText(str(vol))

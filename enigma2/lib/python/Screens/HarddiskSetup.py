# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components import HdsDiscuri
from Tools.ScaledSkin import scaledSkin
from enigma import eTimer

# HDSatelit: lista (hard diskurile si stick-urile USB), intrebarea (ce se pierde, cine foloseste discul acum) si
# lucrarea (formatarea cu ext4 sau, pe un stick, FAT32 ori ext4, FAT32 primul; verificarea fiecarei partitii) trec prin
# Components/HdsDiscuri.py, aceeasi logica ca pagina web /discuri. Lucrarea merge pe un fir separat, iar ecranul de
# asteptare intreaba starea: interfata ramane vie (inregistrarile, evenimentele discului), iar televizorul si pagina nu
# pornesc doua lucrari deodata. Pe televizor omul alege dupa avertisment (inregistrare in curs sau aproape, timeshift,
# fisier deschis); swap-ul pornit pe disc opreste lucrarea, fiindca discul nu s-ar putea demonta.

# Intrebarea: textul (ce se pierde, spus pe nume, si cine foloseste discul) e mai lung decat incape intr-o fereastra
# MessageBox cu raspunsuri, deci are ecranul ei, cu textul derulabil si raspunsul implicit Renunta. Skinul de aici
# (asezat pe 1280, marit la ecran) cu culorile si fonturile skinului HDSatelit, incarcat mereu; un skin care are ecranul
# HdsDiscIntrebare il foloseste pe al lui.
SKIN_INTREBARE = """
<screen name="HdsDiscIntrebare" position="center,center" size="1000,580" backgroundColor="hdsPanelDialog" flags="wfNoBorder">
	<eLabel position="0,0" size="1000,2" backgroundColor="hdsLine" zPosition="1" />
	<widget name="intrebare" position="24,12" size="952,80" font="HdsBold;24" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="center" zPosition="1" />
	<eLabel position="24,96" size="952,1" backgroundColor="hdsLine" zPosition="1" />
	<widget name="detalii" position="24,104" size="952,348" font="HdsRegular;20" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" zPosition="1" />
	<widget name="list" position="24,460" size="952,80" itemHeight="40" textOffset="14,0" valign="center" font="HdsRegular;22" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" zPosition="2" />
	<widget name="nota" position="24,546" size="952,26" font="HdsRegular;16" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="1" />
</screen>"""


class HdsDiscIntrebare(Screen):
	"""Intrebarea formatarii sau a verificarii, cu tot ce trebuie stiut inainte. Sus / Jos aleg raspunsul (implicit
	Renunta), Stanga / Dreapta deruleaza textul, OK alege, EXIT renunta. Se inchide cu True numai la Da."""

	def __init__(self, session, intrebare, detalii, buton):
		self.skin = scaledSkin(SKIN_INTREBARE)
		Screen.__init__(self, session)
		self.skinName = ["HdsDiscIntrebare"]
		self["intrebare"] = Label(intrebare)
		self["detalii"] = ScrollLabel("\n".join(detalii))
		self.raspunsuri = [(_("Renunță"), False), (buton, True)]
		self["list"] = MenuList(self.raspunsuri)
		self["nota"] = Label(_("Sus și Jos aleg răspunsul; Stânga și Dreapta derulează textul."))
		actiuni = {
			"ok": self.ok,
			"cancel": self.renunta,
			"up": self.sus,
			"down": self.jos,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"left": self.inapoi,
			"right": self.inainte,
			"leftRepeated": self.inapoi,
			"rightRepeated": self.inainte,
		}
		# celelalte actiuni din DirectionActions (tasta ridicata) nu fac nimic; fara ele jurnalul scrie "unknown action"
		for nume in ("upUp", "downUp", "leftUp", "rightUp"):
			actiuni[nume] = self.nimic
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions"], actiuni, -1)

	def nimic(self):
		pass

	def sus(self):
		self["list"].up()

	def jos(self):
		self["list"].down()

	def inapoi(self):
		self["detalii"].pageUp()

	def inainte(self):
		self["detalii"].pageDown()

	def renunta(self):
		self.close(False)

	def ok(self):
		ales = self["list"].getCurrent()
		self.close(bool(ales and ales[1]))


class HarddiskWait(Screen):
	# used only when the active skin has no HarddiskWait screen
	skin = """
		<screen name="HarddiskWait" resolution="1920,1080" position="center,center" size="900,140" flags="wfNoBorder">
			<widget name="wait" position="30,20" size="840,100" font="Regular;34" halign="center" valign="center" transparent="1" />
		</screen>"""

	def __init__(self, session, hdd, type, sistem = None):
		Screen.__init__(self, session)
		self.hdd = hdd
		self.sistem = sistem
		if type == HarddiskSetup.HARDDISK_INITIALIZE:
			self.fel = HdsDiscuri.INITIALIZARE
			text = _("Initializing Harddisk...")
		else:
			self.fel = HdsDiscuri.VERIFICARE
			text = _("Checking Filesystem...")
		self["wait"] = Label(text)
		self.pornit = False
		self.timer = eTimer()
		self.timer.callback.append(self.pas)
		self.timer.start(100, True)

	def pas(self):
		if not self.pornit:
			self.pornit = True
			bun, _text = HdsDiscuri.pornesteFir(self.hdd, self.fel, sistem = self.sistem)
			if not bun:
				self.close(None)
				return
			self.timer.start(500, False)
			return
		lucru = HdsDiscuri.stareLucru()
		if lucru is not None and lucru["stare"] == HdsDiscuri.LUCRU_IN_LUCRU:
			return
		self.timer.stop()
		self.close(lucru is not None and lucru["stare"] == HdsDiscuri.LUCRU_GATA)

class HarddiskSetup(Screen):
	HARDDISK_INITIALIZE = 1
	HARDDISK_CHECK = 2

	def __init__(self, session, hdd, type = None):
		Screen.__init__(self, session)
		self.hdd = hdd
		self.sistem = None

		if type not in (self.HARDDISK_INITIALIZE, self.HARDDISK_CHECK):
			self.type = self.HARDDISK_INITIALIZE
		else:
			self.type = type

		self["model"] = Label(_("Model: ") + hdd.model())
		self["capacity"] = Label(_("Capacity: ") + hdd.capacity())
		self["bus"] = Label(_("Bus: ") + hdd.bus())
		self["initialize"] = Pixmap()

		if self.type == self.HARDDISK_INITIALIZE:
			text = _("Initialize")
		else:
			text = _("Check")
		self["initializetext"] = Label(text)

		self["actions"] = ActionMap(["OkCancelActions"],
		{
			"ok": self.close,
			"cancel": self.close
		})

		self["shortcuts"] = ActionMap(["ShortcutActions"],
		{
			"red": self.hddQuestion
		})

	def fel(self):
		return HdsDiscuri.INITIALIZARE if self.type == self.HARDDISK_INITIALIZE else HdsDiscuri.VERIFICARE

	def hddReady(self, result):
		print("Result: " + str(result))
		if result is None:
			self.session.open(MessageBox, _("Se lucrează deja la un disc. Așteaptă să se termine."), MessageBox.TYPE_ERROR)
			return
		if not result:
			self.session.open(MessageBox, HdsDiscuri.textLucru(HdsDiscuri.stareLucru()), MessageBox.TYPE_ERROR)
		else:
			self.close()

	def hddQuestion(self):
		if HdsDiscuri.inLucru():
			self.session.open(MessageBox, _("Se lucrează deja la un disc. Așteaptă să se termine."), MessageBox.TYPE_ERROR)
			return
		self.inregistrari = HdsDiscuri.stareInregistrari()
		swap = [text for cheie, text in HdsDiscuri.folosire(self.hdd.device, self.inregistrari) if cheie == "swap"]
		if swap:
			self.session.open(MessageBox, swap[0], MessageBox.TYPE_ERROR)
			return
		if self.type == self.HARDDISK_INITIALIZE and HdsDiscuri.esteDetasabil(self.hdd):
			alegeri = [(HdsDiscuri.etichetaSistem(s), s) for s in HdsDiscuri.sisteme(self.hdd)]
			self.session.openWithCallback(self.sistemAles, ChoiceBox, title = _("Cu ce sistem de fișiere formatezi "
				"stick-ul?"), list = alegeri)
			return
		self.intreaba(None)

	def sistemAles(self, alegere = None):
		if alegere:
			self.intreaba(alegere[1])

	def intreaba(self, sistem):
		self.sistem = sistem
		q, detalii = HdsDiscuri.intrebare(self.hdd, self.fel(), sistem, self.inregistrari)
		self.session.openWithCallback(self.hddConfirmed, HdsDiscIntrebare, q, detalii, HdsDiscuri.butonDa(self.hdd,
			self.fel()))

	def hddConfirmed(self, confirmed = False):
		if not confirmed:
			return
		if HdsDiscuri.inLucru():
			self.session.open(MessageBox, _("Se lucrează deja la un disc. Așteaptă să se termine."), MessageBox.TYPE_ERROR)
			return

		print("[HarddiskSetup] %s %s" % (self.fel(), self.hdd.device))
		self.session.openWithCallback(self.hddReady, HarddiskWait, self.hdd, self.type, self.sistem)

class HarddiskSelection(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)

		# hard diskurile si stick-urile USB (Components/HdsDiscuri.discuriOferite, ca pagina web /discuri)
		tlist = HdsDiscuri.discuriOferite()
		if not tlist:
			tlist = [(_("Niciun hard disk și niciun stick USB găsit."), 0)]
		self["hddlist"] = MenuList(tlist)

		self["actions"] = ActionMap(["OkCancelActions"],
		{
			"ok": self.okbuttonClick ,
			"cancel": self.close
		})

	def okbuttonClick(self):
		selection = self["hddlist"].getCurrent()
		if selection and selection[1] != 0:
			self.session.open(HarddiskSetup, selection[1], HarddiskSetup.HARDDISK_INITIALIZE)

# This is actually just HarddiskSelection but with correct type
class HarddiskFsckSelection(HarddiskSelection):
	def __init__(self, session):
		HarddiskSelection.__init__(self, session)
		self.skinName = "HarddiskSelection"

	def okbuttonClick(self):
		selection = self["hddlist"].getCurrent()
		if selection and selection[1] != 0:
			self.session.open(HarddiskSetup, selection[1], HarddiskSetup.HARDDISK_CHECK)

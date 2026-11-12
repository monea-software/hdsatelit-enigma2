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
import time

SKIN_ADMIN = """
<screen name="HdsDiscAdministrare" position="center,center" size="1000,380" backgroundColor="hdsPanelDialog" flags="wfNoBorder">
	<widget name="model" position="24,24" size="952,44" font="HdsBold;26" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="capacity" position="24,78" size="952,36" font="HdsRegular;22" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="bus" position="24,122" size="952,36" font="HdsRegular;22" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="staretext" position="24,170" size="952,100" font="HdsRegular;22" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="initializetext" position="24,290" size="450,60" font="HdsRegular;22" foregroundColor="red" backgroundColor="hdsPanelDialog" transparent="1" />
	<widget name="montaretext" position="500,290" size="476,60" font="HdsRegular;22" foregroundColor="yellow" backgroundColor="hdsPanelDialog" transparent="1" />
</screen>"""

class HdsDiscCitire(Screen):
	skin = """<screen name="HdsDiscCitire" resolution="1920,1080" position="center,center" size="900,150" flags="wfNoBorder">
		<widget name="text" position="24,20" size="852,110" font="Regular;26" halign="center" valign="center" />
	</screen>"""

	def __init__(self, session, functie):
		Screen.__init__(self, session)
		from Components.HdsStocareDisc import cere
		self["text"] = Label(_("Se citesc datele discului..."))
		self["actions"] = ActionMap(["OkCancelActions"], {"cancel": self.renunta})
		self.cheie = ("tv-disc", id(self), time.monotonic())
		self.pana = time.monotonic() + 3
		self.initial = cere(self.cheie, functie, termen=3, varsta=5)
		self.timer = eTimer()
		self.timer.callback.append(self.pas)
		self.onClose.append(self.timer.stop)
		self.timer.start(100, False)

	def renunta(self):
		self.close(None)

	def pas(self):
		from Components.HdsStocareDisc import stare
		rez = stare(self.cheie) or self.initial
		if (not rez or rez["stare"] == "asteapta") and time.monotonic() >= self.pana:
			rez = {"stare": "termen", "valoare": None, "eroare": ""}
		if rez and rez["stare"] != "asteapta":
			self.close(rez)

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
		self.onClose.append(self.timer.stop)
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
		self.skin = scaledSkin(SKIN_ADMIN)
		Screen.__init__(self, session)
		self.skinName = ["HdsDiscAdministrare"]
		self.hdd = hdd
		self.sistem = None

		if type not in (self.HARDDISK_INITIALIZE, self.HARDDISK_CHECK):
			self.type = self.HARDDISK_INITIALIZE
		else:
			self.type = type

		self["model"] = Label(_("Se citesc datele discului..."))
		self["capacity"] = Label("")
		self["bus"] = Label("")
		self["staretext"] = Label("")
		self["initialize"] = Pixmap()

		if self.type == self.HARDDISK_INITIALIZE:
			text = _("Initialize")
		else:
			text = _("Check")
		self["initializetext"] = Label(text)
		self["montaretext"] = Label(_("Galben: punct de montare"))

		self["actions"] = ActionMap(["OkCancelActions"],
		{
			"ok": self.close,
			"cancel": self.close
		})

		self["shortcuts"] = ActionMap(["ShortcutActions"],
		{
			"red": self.hddQuestion,
			"yellow": self.alegeMontare
		})
		self.onLayoutFinish.append(self.citesteModel)

	def citesteModel(self):
		self.citeste(lambda: (self.hdd.model(), self.hdd.capacity(), self.hdd.bus()), self.modelGata)

	def modelGata(self, valori):
		from Components.Harddisk import harddiskmanager
		self["model"].setText(_("Model: ") + valori[0])
		self["capacity"].setText(_("Capacity: ") + valori[1])
		self["bus"].setText(_("Bus: ") + valori[2])
		mesaje = []
		for device, eroare in harddiskmanager.mount_errors.items():
			rest = device[len(self.hdd.device):] if device.startswith(self.hdd.device) else ""
			if device == self.hdd.device or rest and (rest.isdigit() or rest.startswith("p") and rest[1:].isdigit()):
				mesaj = eroare.get("motiv", "")
				if mesaj and mesaj not in mesaje:
					mesaje.append(mesaj)
		self["staretext"].setText("\n".join(mesaje))

	def citeste(self, functie, callback):
		def gata(rez):
			if rez is None:
				return
			if rez["stare"] != "gata":
				self.session.open(MessageBox, _("Discul nu răspunde la timp. Încearcă din nou."), MessageBox.TYPE_ERROR)
				return
			callback(rez["valoare"])
		self.session.openWithCallback(gata, HdsDiscCitire, functie)

	def alegeMontare(self):
		from Components.Harddisk import harddiskmanager
		def date():
			def apartine(device):
				if device == self.hdd.device:
					return True
				rest = device[len(self.hdd.device):] if device.startswith(self.hdd.device) else ""
				return bool(rest and (rest.isdigit() or rest.startswith("p") and rest[1:].isdigit()))
			parts = [p for p in list(harddiskmanager.partitions) + list(harddiskmanager.pending.values())
				if p.device and apartine(p.device)]
			rez = [(p.device, harddiskmanager.mediaNameInfo(p.device)) for p in parts]
			return [(device, info) for device, info in rez if info["alegeri"]]
		self.citeste(date, self.partitiiMontare)

	def partitiiMontare(self, parts):
		if not parts:
			self.session.open(MessageBox, _("Discul nu are un UUID cunoscut sau nu mai este conectat."), MessageBox.TYPE_ERROR)
			return
		if len(parts) == 1:
			self.montarePartitie((parts[0][0], parts[0]))
			return
		self.session.openWithCallback(self.montarePartitie, ChoiceBox, title=_("Alege partiția"),
			list=[("/dev/" + device, (device, info)) for device, info in parts])

	def montarePartitie(self, alegere):
		if not alegere:
			return
		device, info = alegere[1]
		self.montare_device = device
		self.session.openWithCallback(self.montareAleasa, ChoiceBox,
			title=_("Punct de montare la următoarea montare"), list=[(text, val) for val, text in info["alegeri"]])

	def montareAleasa(self, alegere):
		if not alegere:
			return
		from Components.Harddisk import harddiskmanager
		pana = time.monotonic() + 3
		self.citeste(lambda: harddiskmanager.setMediaName(self.montare_device, alegere[1], valid=lambda: time.monotonic() < pana),
			lambda rez: self.session.open(MessageBox, rez["message"],
				MessageBox.TYPE_INFO if rez["result"] else MessageBox.TYPE_ERROR))

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
		self.citeste(lambda: HdsDiscuri.folosire(self.hdd.device, self.inregistrari), self.folosireGata)

	def folosireGata(self, folosire):
		swap = [text for cheie, text in folosire if cheie == "swap"]
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
		self.inregistrari = HdsDiscuri.stareInregistrari()
		self.citeste(lambda: HdsDiscuri.intrebare(self.hdd, self.fel(), sistem, self.inregistrari), self.intrebareGata)

	def intrebareGata(self, intrebare):
		q, detalii = intrebare
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
		# titlul din bara de sus: textul intrarii din meniu
		self.setTitle(_("Format Hard Drive"))

		# hard diskurile si stick-urile USB (Components/HdsDiscuri.discuriOferite, ca pagina web /discuri)
		self["hddlist"] = MenuList([(_("Se citesc datele discului..."), 0)])
		self.onLayoutFinish.append(self.citesteLista)

		self["actions"] = ActionMap(["OkCancelActions"],
		{
			"ok": self.okbuttonClick ,
			"cancel": self.close
		})

	def citesteLista(self):
		self.session.openWithCallback(self.listaGata, HdsDiscCitire, HdsDiscuri.discuriOferite)

	def listaGata(self, rez):
		if rez is None:
			return
		if rez["stare"] != "gata":
			self["hddlist"].setList([(_("Discul nu răspunde la timp. Încearcă din nou."), 0)])
			return
		self["hddlist"].setList(rez["valoare"] or [(_("Niciun hard disk și niciun stick USB găsit."), 0)])

	def okbuttonClick(self):
		selection = self["hddlist"].getCurrent()
		if selection and selection[1] != 0:
			self.session.open(HarddiskSetup, selection[1], HarddiskSetup.HARDDISK_INITIALIZE)

# This is actually just HarddiskSelection but with correct type
class HarddiskFsckSelection(HarddiskSelection):
	def __init__(self, session):
		HarddiskSelection.__init__(self, session)
		self.skinName = "HarddiskSelection"
		self.setTitle(_("Check Disk Health"))

	def okbuttonClick(self):
		selection = self["hddlist"].getCurrent()
		if selection and selection[1] != 0:
			self.session.open(HarddiskSetup, selection[1], HarddiskSetup.HARDDISK_CHECK)

# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen
from Components.ActionMap import NumberActionMap
from Components.Input import Input
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.config import config
from Components import HdsAlimentare
from Components import HdsOprireAutomata

HdsAlimentare.initConfig()
HdsOprireAutomata.initConfig()

# 0.7.7 (OSD; LinuxSat 164182, TODO 15.11 18:41 PSC11): sub durate, oprirea automata aleasa o data (Components/
# HdsOprireAutomata.py): „Oprire automată fără taste” si, cand e pornita, „Felul opririi automate”. OK, stanga si dreapta
# schimba valoarea pe loc (se salveaza pe loc, fara alt ecran); in web, acelasi card din /alimentare.
RAND_AUTO = "auto"
RAND_AUTO_FEL = "auto_fel"


class SleepTimerEdit(Screen):
	# Nume nou: skinul vechi nu contine lista de durate. Rezerva ramane folosibila
	# pana cand skinul ales ofera toate elementele ecranului nou.
	skin = """<screen name="HdsSleepTimerEditRapid" position="center,center" size="1000,772" title="Oprire programată">
		<widget name="durate" position="20,16" size="960,308" font="Regular;24" itemHeight="44" scrollbarMode="showOnDemand" />
		<widget name="pretext" position="20,340" size="440,44" font="Regular;24" />
		<widget name="input" position="480,340" size="160,44" font="Regular;28" halign="center" />
		<widget name="aftertext" position="660,340" size="320,44" font="Regular;24" />
		<widget name="current_status" position="20,396" size="960,96" font="Regular;22" />
		<widget name="red_text" position="20,504" size="960,44" font="Regular;22" foregroundColor="#ef7373" />
		<widget name="green_text" position="20,550" size="960,44" font="Regular;22" foregroundColor="#82ce91" />
		<widget name="yellow_text" position="20,596" size="960,44" font="Regular;22" foregroundColor="#eed27d" />
		<widget name="blue_text" position="20,642" size="960,44" font="Regular;22" foregroundColor="#83b5ed" />
		<widget name="indicatii" position="20,700" size="960,56" font="Regular;20" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["HdsSleepTimerEditRapid"]
		# 0.7.7 (OSD): skinul de rezerva, scris pe 1920, potrivit si pe temele de 1280 (cu randurile opririi automate
		# fereastra are 772 de pixeli inaltime)
		try:
			from Tools.ScaledSkin import scaledSkin
			self.skin = scaledSkin(SleepTimerEdit.skin, 1920)
		except Exception:
			pass
		self.setTitle(_("Sleep Timer"))
		for culoare in ("red", "green", "yellow", "blue"):
			self[culoare] = Pixmap()
			self[culoare + "_text"] = Label()
		self["current_status"] = Label()
		self["pretext"] = Label(_("Durată proprie (cifre)"))
		self["aftertext"] = Label(_("minutes"))
		self["indicatii"] = Label(_("Sus/jos: alege rândul. OK: activează durata sau schimbă oprirea automată (și stânga/dreapta). Cifre: durată proprie. EXIT: închide."))
		st = self.session.nav.SleepTimer
		minute = st.getCurrentSleepTime() if st.isActive() else config.SleepTimer.defaulttime.value
		self["input"] = Input(text=str(minute), maxSize=False, type=Input.NUMBER)
		self["durate"] = MenuList([], enableWrapAround=True)
		self._durate = tuple(HdsAlimentare.DURATE_UZUALE) + ("emisiune", "proprie")
		self._randuri = self._durate
		self._selectieInitiala = self._durate.index(minute) if minute in self._durate else len(self._durate) - 1
		self._arataDurate()
		self.onLayoutFinish.append(self._alegeInitial)
		self._arataStare()
		self.updateColors()
		self["actions"] = NumberActionMap([
			"SleepTimerEditorActions", "TextEntryActions", "KeyboardInputActions", "DirectionActions"
		], {
			"exit": self.cancel,
			"select": self.select,
			"1": self.keyNumberGlobal, "2": self.keyNumberGlobal,
			"3": self.keyNumberGlobal, "4": self.keyNumberGlobal,
			"5": self.keyNumberGlobal, "6": self.keyNumberGlobal,
			"7": self.keyNumberGlobal, "8": self.keyNumberGlobal,
			"9": self.keyNumberGlobal, "0": self.keyNumberGlobal,
			"up": self["durate"].up, "down": self["durate"].down,
			"upRepeated": self["durate"].up, "downRepeated": self["durate"].down,
			"selectLeft": self.selectLeft, "selectRight": self.selectRight,
			"left": self.selectLeft, "right": self.selectRight,
			"home": self.selectHome, "end": self.selectEnd,
			"deleteForward": self.deleteForward, "deleteBackward": self.deleteBackward,
			"disableTimer": self.disableTimer,
			"toggleAction": self.toggleAction, "toggleAsk": self.toggleAsk,
			"useServiceTime": self.useServiceTime
		}, -1)

	def _alegeInitial(self):
		self["durate"].moveToIndex(self._selectieInitiala)

	def _randAles(self):
		"""Cheia randului ales: o durata (30, 60, 90), "emisiune", "proprie", RAND_AUTO sau RAND_AUTO_FEL."""
		index = self["durate"].getSelectionIndex()
		if index is None or not 0 <= index < len(self._randuri):
			return None
		return self._randuri[index]

	def _schimbaAuto(self, rand, pas):
		"""OK, stanga sau dreapta pe randurile opririi automate: valoarea urmatoare (sau cea dinainte), salvata pe loc."""
		A = HdsOprireAutomata
		try:
			if rand == RAND_AUTO:
				A.seteaza(minute_noi=A.urmatoareaValoare(A.MINUTE, A.minute(), pas))
			else:
				A.seteaza(fel_nou=A.urmatoareaValoare(A.FELURI, A.fel(), pas))
		except ValueError as e:
			self._arataStare(str(e))
			return
		self._arataDurate()
		self._arataStare()

	def _minuteCanal(self):
		try:
			return HdsAlimentare.minuteCanal(self.session.nav)
		except Exception:
			return None

	def _arataDurate(self):
		selectie = self["durate"].getSelectionIndex()
		randuri = [_("%d minute") % minute for minute in HdsAlimentare.DURATE_UZUALE]
		minute = self._minuteCanal()
		if minute is None:
			randuri.append(_("Până la sfârșitul emisiunii: indisponibil"))
		else:
			randuri.append(_("Până la sfârșitul emisiunii (+2 min): %d min") % minute)
		randuri.append(_("Durată proprie: %s minute") % self["input"].getText())
		A = HdsOprireAutomata
		randuri.append(_("Oprire automată fără taste: %s") % A.textMinute(A.minute()))
		chei = self._durate + (RAND_AUTO,)
		if A.minute():
			randuri.append(_("Felul opririi automate: %s") % A.textFel(A.fel()))
			chei += (RAND_AUTO_FEL,)
		self._randuri = chei
		self["durate"].setList(randuri)
		if selectie is not None and selectie >= 0:
			self["durate"].moveToIndex(selectie)

	def _arataStare(self, rezultat=""):
		st = self.session.nav.SleepTimer
		if st.isActive():
			text = _("Oprire programată activă: %d minute rămase.") % st.getCurrentSleepTime()
		else:
			text = _("Oprirea programată este oprită.")
		text += "\n" + HdsOprireAutomata.descriere()
		self["current_status"].setText((rezultat + "\n" if rezultat else "") + text)

	def updateColors(self):
		self["red_text"].setText(_("ROȘU: oprește temporizatorul"))
		actiune = HdsAlimentare.textActiune(config.SleepTimer.action.value)
		self["green_text"].setText(_("VERDE: tip oprire: %s") % actiune)
		intreaba = _("yes") if config.SleepTimer.ask.value else _("no")
		self["yellow_text"].setText(_("GALBEN: întreabă înainte de oprire: %s") % intreaba)
		self["blue_text"].setText(_("ALBASTRU: activează până la sfârșitul emisiunii (+2 min)"))

	def cancel(self):
		config.SleepTimer.ask.cancel()
		config.SleepTimer.action.cancel()
		self.close()

	def select(self):
		rand = self._randAles()
		if rand in (RAND_AUTO, RAND_AUTO_FEL):
			self._schimbaAuto(rand, 1)
			return
		index = self["durate"].getSelectionIndex()
		if index is None or not 0 <= index < len(self._durate):
			return
		durata = self._durate[index]
		if durata == "emisiune":
			self.useServiceTime()
		else:
			self._porneste(self["input"].getText() if durata == "proprie" else durata)

	def _porneste(self, durata):
		time = HdsAlimentare.minuteValide(durata)
		if time is None:
			minim, maxim = HdsAlimentare.limiteMinute()
			self._arataStare(_("Minutele se scriu ca număr întreg, de la %d la %d.") % (minim, maxim))
			return
		HdsAlimentare.porneste(self.session.nav, time)
		self._arataStare(_("Oprire programată activată: %d minute.") % time)

	def _durataProprie(self):
		self["durate"].moveToIndex(len(self._durate) - 1)

	def keyNumberGlobal(self, number):
		self._durataProprie()
		self["input"].number(number)
		self._arataDurate()

	def selectLeft(self):
		rand = self._randAles()
		if rand in (RAND_AUTO, RAND_AUTO_FEL):
			self._schimbaAuto(rand, -1)
			return
		self._durataProprie()
		self["input"].left()

	def selectRight(self):
		rand = self._randAles()
		if rand in (RAND_AUTO, RAND_AUTO_FEL):
			self._schimbaAuto(rand, 1)
			return
		self._durataProprie()
		self["input"].right()

	def selectHome(self):
		self._durataProprie()
		self["input"].home()

	def selectEnd(self):
		self._durataProprie()
		self["input"].end()

	def deleteForward(self):
		self._durataProprie()
		self["input"].delete()
		self._arataDurate()

	def deleteBackward(self):
		self._durataProprie()
		self["input"].deleteBackward()
		self._arataDurate()

	def disableTimer(self):
		HdsAlimentare.opreste(self.session.nav)
		self._arataStare()

	def toggleAction(self):
		config.SleepTimer.action.value = "standby" if config.SleepTimer.action.value == "shutdown" else "shutdown"
		self.updateColors()

	def toggleAsk(self):
		config.SleepTimer.ask.value = not config.SleepTimer.ask.value
		self.updateColors()

	def useServiceTime(self):
		minute = self._minuteCanal()
		if minute is None:
			self._arataStare(_("Nu se poate afla sfârșitul emisiunii sau al filmului. Alege o durată."))
			return
		self["durate"].moveToIndex(len(HdsAlimentare.DURATE_UZUALE))
		self._porneste(minute)

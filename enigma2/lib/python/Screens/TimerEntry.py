# -*- coding: utf-8 -*-
# Modificat de moneasoftware.com si hdsatelit.com, 2026
#
# TimerEntry.py: fereastra unei inregistrari programate (noua sau modificata) si jurnalul ei (TimerLog).
#
# TimerEntry(session, temporizator) se inchide cu (True, temporizator) la salvare si cu (False,) la renuntare; o
# deschid lista inregistrarilor (TimerEdit.py), ghidul (EpgSelection.py, EventView.py) si a doua bara
# (Components/HdsTemporizare.py). Titlul spune daca e noua sau modificata; sub lista, ajutorul randului ales si locul
# inregistrarii cu spatiul liber (citite pe un fir, Components/HdsInregistrariProgramate.py). Tastele: Verde salveaza,
# Rosu sau EXIT renunta; OK pe Nume sau Descriere deschide tastatura, pe Canal lista de canale, pe Locul inregistrarii
# alegerea dosarului, pe Etichete editorul lor, pe celelalte randuri salveaza. HELP le arata pe toate. Ziua se arata cu
# numele zilei si cifre (strftime ar da numele lunii in engleza). Ajutorul tastelor cu cifre al randurilor cu text
# (NumericalTextInputHelpDialog) se muta langa fereastra, in dreapta ei, cand incape pe ecran: altfel panoul l-ar
# acoperi pe jumatate.
#
# TimerLog: jurnalul inregistrarii, cu ora „ZZ.LL.AAAA HH:MM” si fiecare rand pe intelesul oricui
# (HdsInregistrariProgramate.textJurnal); mesajul tehnic original ramane dedesubt, mai mic. OK deschide lista scurta
# (Șterge rândul, Golește jurnalul, Închide), ca totul sa se atinga numai cu sagetile si OK.
#
# Randul "Decriptarea" ("Decriptează acum" / "Decodează mai târziu", Components/HdsDecodare.py) apare numai la o
# inregistrare (nu la "Doar schimbă canalul") si numai cu programul de decodare pe receptor; fara el temporizatorul isi
# pastreaza alegerea neatinsa.
#
# skinulHds / areEcran / tasta / puneText: tastele colorate ale ecranelor temporizatoarelor (si TimerEdit.py). Cu skinul
# HDSatelit sunt StaticText, iar bara colorata a unei taste fara text nu se deseneaza; pe alte skinuri raman ce asteapta
# ele.

from .Screen import Screen
from . import ChannelSelection
from ServiceReference import ServiceReference
from Components.config import config, ConfigSelection, ConfigText, ConfigSubList, ConfigDateTime, ConfigClock, ConfigYesNo, getConfigListEntry
from Components.ActionMap import HelpableActionMap
from Components.ConfigList import ConfigListScreen
from Components.MenuList import MenuList
from Components.Button import Button
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components.SystemInfo import SystemInfo
from Components.UsageConfig import defaultMoviePath
from Components import HdsInregistrariProgramate as HIP
from Components import HdsDecodare
from Screens.MovieSelection import getPreferredTagEditor
from Screens.LocationBox import MovieLocationBox
from Screens.ChoiceBox import ChoiceBox
from Screens.HelpMenu import HelpableScreen
from Screens.MessageBox import MessageBox
from RecordTimer import AFTEREVENT
from enigma import eEPGCache, eServiceReference
from time import localtime, mktime, time, strftime
from datetime import datetime

# ecranul din skinul HDSatelit dupa care se recunoaste skinul (blocul listei inregistrarilor programate)
ECRAN_HDS = "HdsTimerEditList"
# cat de des (ms) se uita fereastra dupa citirea locului si cat asteapta cel mult (s)
CEAS_LOC_MS = 250
ASTEPTARE_LOC_S = 15
# distanta (px) dintre fereastra si ajutorul tastelor cu cifre mutat langa ea
MARGINE_AJUTOR = 16


def areEcran(nume):
	"""Skinul activ are ecranul `nume` (lookupScreen cauta numai numele, fara disc)."""
	try:
		import skin
		return skin.lookupScreen(nume, 0)[0] is not None
	except Exception:
		return False


def skinulHds():
	"""Skinul activ are ecranele HDSatelit ale temporizatoarelor."""
	return areEcran(ECRAN_HDS)


def tasta(hds, text=""):
	"""Tasta colorata: StaticText pe skinul HDSatelit, Button (text cu cel putin un spatiu) pe celelalte."""
	if hds:
		return StaticText(text)
	return Button(text or " ")


def puneText(element, text):
	if isinstance(element, StaticText):
		element.setText(text)
	else:
		element.setText(text or " ")


def cuMajuscula(text):
	return text[:1].upper() + text[1:]


class ZiConfig(ConfigDateTime):
	"""Ziua cu numele zilei si cifre („Sâmbătă, ZZ.LL.AAAA”), tradusa; stanga / dreapta ca la ConfigDateTime."""

	def getText(self):
		return HIP.ziText(self.value)

	def getMulti(self, selected):
		return ("text", HIP.ziText(self.value))


class TimerEntry(Screen, ConfigListScreen, HelpableScreen):
	def __init__(self, session, timer):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.timer = timer

		self.entryDate = None
		self.entryService = None
		self.entryEndTime = None

		rt = self.session.nav.RecordTimer
		self.existent = timer in rt.timer_list or timer in rt.processed_timers
		self.titlu = _("Modifică înregistrarea programată") if self.existent else _("Înregistrare programată nouă")
		self.setTitle(self.titlu)

		self["oktext"] = Label(_("OK"))
		self["canceltext"] = Label(_("Cancel"))
		self["ok"] = Pixmap()
		self["cancel"] = Pixmap()
		# tastele si textele de sub lista (StaticText: pe skinurile care nu le au nu se scrie nimic in jurnal)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["description"] = StaticText("")
		self["footnote"] = StaticText("")
		self["status"] = StaticText("")

		self.createConfig()

		# prioritatea -2: inaintea hartii lui ConfigListScreen (-1), ca OK, stanga si dreapta sa treaca pe aici
		self["actions"] = HelpableActionMap(self, "SetupActions", {
			"ok": (self.keySelect, _("Scrie numele, alege canalul sau dosarul; altfel salvează")),
			"save": (self.keyGo, _("Salvează înregistrarea")),
			"cancel": (self.keyCancel, _("Închide fără să salveze")),
			"left": (self.keyLeft, _("Valoarea de dinainte a rândului ales")),
			"right": (self.keyRight, _("Valoarea următoare a rândului ales")),
		}, -2)
		self["ore"] = HelpableActionMap(self, "GlobalActions", {
			"volumeUp": (self.incrementStart, _("Ora de început cu un minut mai târziu")),
			"volumeDown": (self.decrementStart, _("Ora de început cu un minut mai devreme")),
		}, -2)
		self["ore_sfarsit"] = HelpableActionMap(self, "PiPSetupActions", {
			"size+": (self.incrementEnd, _("Ora de sfârșit cu un minut mai târziu")),
			"size-": (self.decrementEnd, _("Ora de sfârșit cu un minut mai devreme")),
		}, -2)

		self.list = []
		ConfigListScreen.__init__(self, self.list, session = session)
		self.createSetup("config")
		self["config"].onSelectionChanged.append(self.arataAjutorul)

		from enigma import eTimer
		self._inchis = False
		self._locCale = None
		self._locCerutLa = 0
		self._ceasLoc = eTimer()
		try:
			self._ceasLoc.callback.append(self._bateLoc)
		except AttributeError:
			self._ceasLoc_conn = self._ceasLoc.timeout.connect(self._bateLoc)
		self.onLayoutFinish.append(self._dupaAsezare)
		self.onClose.append(self._laInchidere)

	def _dupaAsezare(self):
		self.setTitle(self.titlu)
		self.arataAjutorul()
		self.citesteLocul()

	def _laInchidere(self):
		self._inchis = True
		self._ceasLoc.stop()

	def createConfig(self):
			justplay = self.timer.justplay

			afterevent = {
				AFTEREVENT.NONE: "nothing",
				AFTEREVENT.DEEPSTANDBY: "deepstandby",
				AFTEREVENT.STANDBY: "standby",
				AFTEREVENT.AUTO: "auto"
				}[self.timer.afterEvent]

			weekday_table = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

			# calculate default values
			day = []
			weekday = 0
			for x in (0, 1, 2, 3, 4, 5, 6):
				day.append(0)
			if self.timer.repeated: # repeated
				type = "repeated"
				if (self.timer.repeated == 31): # Mon-Fri
					repeated = "weekdays"
				elif (self.timer.repeated == 127): # daily
					repeated = "daily"
				else:
					flags = self.timer.repeated
					repeated = "user"
					count = 0
					for x in (0, 1, 2, 3, 4, 5, 6):
						if flags == 1: # weekly
							weekday = x
						if flags & 1 == 1: # set user defined flags
							day[x] = 1
							count += 1
						else:
							day[x] = 0
						flags = flags >> 1
					if count == 1:
						repeated = "weekly"
			else: # once
				type = "once"
				repeated = None
				weekday = (int(strftime("%w", localtime(self.timer.begin))) - 1) % 7
				day[weekday] = 1

			self.timerentry_justplay = ConfigSelection(choices = [("record", _("Înregistrează")), ("zap", _("Doar schimbă canalul"))], default = {0: "record", 1: "zap"}[justplay])
			self.timerentry_afterevent = ConfigSelection(choices = [
				("nothing", cuMajuscula(_(HIP.TEXTE_DUPA[HIP.DUPA_NIMIC]))),
				("standby", cuMajuscula(_(HIP.TEXTE_DUPA[HIP.DUPA_ASTEPTARE]))),
				("deepstandby", cuMajuscula(_(HIP.TEXTE_DUPA[HIP.DUPA_OPRIRE]))),
				("auto", cuMajuscula(_(HIP.TEXTE_DUPA[HIP.DUPA_AUTOMAT])))], default = afterevent)
			self.timerentry_type = ConfigSelection(choices = [("once", _("O singură dată")), ("repeated", _("Se repetă"))], default = type)
			self.timerentry_name = ConfigText(default = self.timer.name, visible_width = 50, fixed_size = False)
			self.timerentry_description = ConfigText(default = self.timer.description, visible_width = 50, fixed_size = False)
			self.timerentry_tags = self.timer.tags[:]
			self.timerentry_tagsset = ConfigSelection(choices = [not self.timerentry_tags and "None" or " ".join(self.timerentry_tags)])

			self.timerentry_repeated = ConfigSelection(default = repeated, choices = [
				("daily", cuMajuscula(HIP.zileRepetare(127))),
				("weekly", _("O dată pe săptămână")),
				("weekdays", cuMajuscula(HIP.zileRepetare(31))),
				("user", _("În zilele alese"))])

			self.timerentry_date = ZiConfig(default = self.timer.begin, formatstring = _("%d.%B %Y"), increment = 86400)
			self.timerentry_starttime = ConfigClock(default = self.timer.begin)
			self.timerentry_endtime = ConfigClock(default = self.timer.end)
			self.timerentry_showendtime = ConfigSelection(default = ((self.timer.end - self.timer.begin) > 4), choices = [(True, _("yes")), (False, _("no"))])

			default = self.timer.dirname or defaultMoviePath()
			tmp = config.movielist.videodirs.value
			if default not in tmp:
				tmp.append(default)
			self.timerentry_dirname = ConfigSelection(default = default, choices = tmp)

			self.timerentry_repeatedbegindate = ZiConfig(default = self.timer.repeatedbegindate, formatstring = _("%d.%B %Y"), increment = 86400)

			self.timerentry_weekday = ConfigSelection(default = weekday_table[weekday], choices = [("mon",_("Monday")), ("tue", _("Tuesday")), ("wed",_("Wednesday")), ("thu", _("Thursday")), ("fri", _("Friday")), ("sat", _("Saturday")), ("sun", _("Sunday"))])

			self.timerentry_day = ConfigSubList()
			for x in (0, 1, 2, 3, 4, 5, 6):
				self.timerentry_day.append(ConfigYesNo(default = day[x]))

			# numele canalului; fara canal pornit (sau cu o referinta straina) randul spune cum se alege unul
			servicename = ""
			try:
				servicename = str(self.timer.service_ref.getServiceName())
			except:
				pass
			if not servicename:
				servicename = _("Apasă OK și alege canalul")
			self.timerentry_service_ref = self.timer.service_ref
			self.timerentry_service = ConfigSelection([servicename])

			# "Decodează mai târziu" numai cu programul de decodare (Components/HdsDecodare.py)
			self.hdsDecodare = HdsDecodare.exista()
			self.timerentry_decodare = ConfigSelection(choices = HdsDecodare.alegeri(),
				default = HdsDecodare.text(getattr(self.timer, "hdsDecodareMaiTarziu", False)))

	def createSetup(self, widget):
		# ajutorul fiecarui rand: {element config: text}
		self.ajutor = {}

		def rand(eticheta, element, ajutor):
			self.ajutor[id(element)] = ajutor
			return getConfigListEntry(eticheta, element)

		self.list = []
		self.list.append(rand(_("Name"), self.timerentry_name,
			_("Numele cu care apare în listă și în fișierul înregistrării. OK deschide tastatura.")))
		self.list.append(rand(_("Description"), self.timerentry_description,
			_("O notă despre emisiune. OK deschide tastatura.")))
		self.timerJustplayEntry = rand(_("Ce face"), self.timerentry_justplay,
			_("Înregistrează: emisiunea se salvează pe stick sau pe hard disk. Doar schimbă canalul: la ora aleasă "
			"receptorul trece pe canal, fără să înregistreze."))
		self.list.append(self.timerJustplayEntry)
		self.timerTypeEntry = rand(_("Când"), self.timerentry_type,
			_("O singură dată sau repetat: în fiecare zi, o dată pe săptămână, de luni până vineri sau în zilele alese."))
		self.list.append(self.timerTypeEntry)

		if self.timerentry_type.value == "once":
			self.frequencyEntry = None
		else: # repeated
			self.frequencyEntry = rand(_("Zilele"), self.timerentry_repeated,
				_("În ce zile se repetă. La „În zilele alese” apare câte un rând pentru fiecare zi."))
			self.list.append(self.frequencyEntry)
			self.repeatedbegindateEntry = rand(_("Începe din ziua"), self.timerentry_repeatedbegindate,
				_("Prima zi din care pornește repetarea. Stânga și dreapta schimbă ziua."))
			self.list.append(self.repeatedbegindateEntry)
			if self.timerentry_repeated.value == "weekly":
				self.list.append(rand(_("Weekday"), self.timerentry_weekday, _("Ziua din săptămână în care se repetă.")))

			if self.timerentry_repeated.value == "user":
				zi_aleasa = _("Da: se repetă și în ziua aceasta.")
				for i, zi in enumerate(HIP.ZILE):
					self.list.append(rand(_(zi), self.timerentry_day[i], zi_aleasa))

		self.entryDate = rand(_("Ziua"), self.timerentry_date, _("Ziua în care pornește. Stânga și dreapta schimbă ziua."))
		if self.timerentry_type.value == "once":
			self.list.append(self.entryDate)

		ajutor_ora = _("Stânga și dreapta schimbă câte un minut; cu cifrele se scrie ora direct.")
		self.entryStartTime = rand(_("StartTime"), self.timerentry_starttime, _("Ora la care pornește.") + " " + ajutor_ora)
		self.list.append(self.entryStartTime)

		self.entryShowEndTime = rand(_("Are oră de sfârșit"), self.timerentry_showendtime,
			_("Da: se ține minte și ora la care se termină emisiunea. Receptorul rămâne pe canal și după."))
		if self.timerentry_justplay.value == "zap":
			self.list.append(self.entryShowEndTime)
		self.entryEndTime = rand(_("EndTime"), self.timerentry_endtime, _("Ora la care se termină.") + " " + ajutor_ora)
		if self.timerentry_justplay.value != "zap" or self.timerentry_showendtime.value:
			self.list.append(self.entryEndTime)

		self.channelEntry = rand(_("Channel"), self.timerentry_service, _("Canalul. OK deschide lista de canale ca să alegi altul."))
		self.list.append(self.channelEntry)

		self.dirname = rand(_("Locul înregistrării"), self.timerentry_dirname,
			_("Dosarul în care se salvează înregistrarea. OK deschide alegerea dosarului."))
		self.tagsSet = rand(_("Tags"), self.timerentry_tagsset, _("Cuvinte după care găsești înregistrarea în lista filmelor. OK le alege."))
		if self.timerentry_justplay.value != "zap":
			# locul se arata la orice nivel al meniului: fara el nu se vede unde merge inregistrarea
			self.list.append(self.dirname)
			if getPreferredTagEditor():
				self.list.append(self.tagsSet)
			if self.hdsDecodare:
				self.list.append(rand(_(HdsDecodare.TXT_RAND), self.timerentry_decodare, _(HdsDecodare.TXT_AJUTOR)))
			self.list.append(rand(_("După înregistrare"), self.timerentry_afterevent,
				_("Ce face receptorul după înregistrare. „Revine cum era înainte”: dacă era oprit și a pornit doar "
				"pentru înregistrare, se oprește din nou.")))

		self[widget].list = self.list
		self[widget].l.setList(self.list)

	def arataAjutorul(self):
		cur = self["config"].getCurrent()
		text = ""
		if cur is not None and len(cur) > 1:
			text = self.ajutor.get(id(cur[1]), "")
		self["description"].setText(text)
		self._mutaAjutorulCifrelor()

	def _mutaAjutorulCifrelor(self):
		"""Ajutorul tastelor cu cifre al randului cu text (NumericalTextInputHelpDialog, facut de ConfigText.onSelect)
		trece in dreapta ferestrei, cand incape pe ecran; asezat de skin peste marginea panoului, i s-ar vedea numai o
		parte."""
		cur = self["config"].getCurrent()
		fereastra = getattr(cur[1], "help_window", None) if cur is not None and len(cur) > 1 else None
		if fereastra is None or getattr(fereastra, "instance", None) is None or self.instance is None:
			return
		try:
			from enigma import ePoint, getDesktop
			x = self.instance.position().x() + self.instance.size().width() + MARGINE_AJUTOR
			if x + fereastra.instance.size().width() <= getDesktop(0).size().width():
				fereastra.instance.move(ePoint(x, fereastra.instance.position().y()))
		except Exception as eroare:
			print("[TimerEntry] ajutorul tastelor cu cifre: %s" % eroare)

	# ------------------------------------------------------------------ locul si spatiul liber

	def citesteLocul(self):
		"""Locul ales si spatiul liber (numai la inregistrare), citite pe un fir; fereastra se uita dupa rezultat."""
		if self._inchis:
			return
		if self.timerentry_justplay.value == "zap":
			self._ceasLoc.stop()
			self._locCale = None
			self["footnote"].setText("")
			self["status"].setText("")
			return
		self._locCale = self.timerentry_dirname.value
		self._locCerutLa = time()
		rez = HIP.cereLoc(self._locCale, din_nou=True)
		if rez is not None:
			self._arataLocul(rez)
		else:
			self["footnote"].setText(_("Se citește locul înregistrărilor..."))
			self["status"].setText("")
		self._ceasLoc.start(CEAS_LOC_MS, False)

	def _bateLoc(self):
		if self._inchis or self._locCale is None:
			self._ceasLoc.stop()
			return
		rez = HIP.cereLoc(self._locCale)
		if rez is not None and rez.get("timp", 0) >= self._locCerutLa:
			self._ceasLoc.stop()
			self._arataLocul(rez)
		elif time() - self._locCerutLa > ASTEPTARE_LOC_S:
			# fara rezultat nou in timp util (disc lent, ceas mutat intre timp): ce se stie, altfel mesajul
			self._ceasLoc.stop()
			if rez is not None:
				self._arataLocul(rez)
			else:
				self["footnote"].setText("")
				self["status"].setText(_("Nu am putut citi locul înregistrărilor."))

	def _arataLocul(self, rez):
		if rez.get("bun"):
			self["footnote"].setText(("%s %s" % (rez.get("text", ""), rez.get("detaliu", ""))).strip())
			self["status"].setText("")
		else:
			self["footnote"].setText("")
			self["status"].setText(rez.get("text", ""))

	# ------------------------------------------------------------------ tastele

	def newConfig(self):
		if self["config"].getCurrent() in (self.timerTypeEntry, self.timerJustplayEntry, self.frequencyEntry, self.entryShowEndTime):
			self.createSetup("config")
		if self["config"].getCurrent() in (self.timerJustplayEntry, self.dirname):
			self.citesteLocul()
		self.arataAjutorul()

	def keyLeft(self):
		if self["config"].getCurrent() in (self.channelEntry, self.tagsSet):
			self.keySelect()
		else:
			ConfigListScreen.keyLeft(self)
			self.newConfig()

	def keyRight(self):
		if self["config"].getCurrent() in (self.channelEntry, self.tagsSet):
			self.keySelect()
		else:
			ConfigListScreen.keyRight(self)
			self.newConfig()

	def keySelect(self):
		cur = self["config"].getCurrent()
		if cur == self.channelEntry:
			self.session.openWithCallback(
				self.finishedChannelSelection,
				ChannelSelection.SimpleChannelSelection,
				_("Alege canalul")
			)
		elif cur == self.dirname:
			self.session.openWithCallback(
				self.pathSelected,
				MovieLocationBox,
				_("Alege dosarul"),
				self.timerentry_dirname.value,
				minFree = 100 # We require at least 100MB free space
			)
		elif getPreferredTagEditor() and cur == self.tagsSet:
			self.session.openWithCallback(
				self.tagEditFinished,
				getPreferredTagEditor(),
				self.timerentry_tags
			)
		elif cur is not None and len(cur) > 1 and cur[1] in (self.timerentry_name, self.timerentry_description):
			# numai cu sagetile si OK: textul se scrie pe tastatura de pe ecran; ajutorul tastelor cu cifre al randului
			# (NumericalTextInputHelpDialog) s-ar suprapune peste ea, deci se ascunde cat e deschisa
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			if getattr(cur[1], "help_window", None):
				cur[1].help_window.hide()
			tastatura = self.session.openWithCallback(self.textScris, VirtualKeyBoard, title = cur[0], text = cur[1].getValue())
			# titlul ferestrei tastaturii (banda de sus): numele randului
			tastatura.setTitle(cur[0])
		else:
			self.keyGo()

	def _ajutorCifre(self, arata):
		cur = self["config"].getCurrent()
		fereastra = getattr(cur[1], "help_window", None) if cur is not None and len(cur) > 1 else None
		if fereastra is not None:
			if arata:
				fereastra.show()
			else:
				fereastra.hide()

	def showHelp(self):
		# lista HELP acopera fereastra; ajutorul tastelor cu cifre (alt dialog) ar ramane peste ea
		self._ajutorCifre(False)
		HelpableScreen.showHelp(self)

	def callHelpAction(self, *args):
		self._ajutorCifre(True)
		HelpableScreen.callHelpAction(self, *args)

	def textScris(self, text = None):
		cur = self["config"].getCurrent()
		if cur is None or len(cur) < 2:
			return
		if text is not None:
			cur[1].setValue(text)
			self["config"].invalidate(cur)
		if getattr(cur[1], "help_window", None):
			cur[1].help_window.show()

	def finishedChannelSelection(self, *args):
		if args:
			self.timerentry_service_ref = ServiceReference(args[0])
			self.timerentry_service.setCurrentText(self.timerentry_service_ref.getServiceName())
			self["config"].invalidate(self.channelEntry)

	def getTimestamp(self, date, mytime):
		d = localtime(date)
		dt = datetime(d.tm_year, d.tm_mon, d.tm_mday, mytime[0], mytime[1])
		return int(mktime(dt.timetuple()))

	def getBeginEnd(self):
		date = self.timerentry_date.value
		endtime = self.timerentry_endtime.value
		starttime = self.timerentry_starttime.value

		begin = self.getTimestamp(date, starttime)
		end = self.getTimestamp(date, endtime)

		# if the endtime is less than the starttime, add 1 day.
		if end < begin:
			end += 86400
		return begin, end

	def selectChannelSelector(self, *args):
		self.session.openWithCallback(
				self.finishedChannelSelectionCorrection,
				ChannelSelection.SimpleChannelSelection,
				_("Alege canalul")
			)

	def finishedChannelSelectionCorrection(self, *args):
		if args:
			self.finishedChannelSelection(*args)
			self.keyGo()

	def keyGo(self, result = None):
		if not self.timerentry_service_ref.isRecordable():
			# HDSatelit 0.3.0: un program DVB-T2 / post DAB+ din satelit ales (sau venit din ghid, referinta pastrata de
			# RecordTimerEntry in hdsRefNeinregistrabila): limita spusa pe intelesul oricui, apoi alegerea altui canal
			ref = self.timerentry_service_ref
			if ref is self.timer.service_ref:
				ref = getattr(self.timer, "hdsRefNeinregistrabila", None) or ref
			if HIP.felNeinregistrabil(ref):
				mesaj = HIP.mesajNeinregistrabil(ref, _) + "\n\n" + _("Alege alt canal din listă.")
			else:
				mesaj = _("Nu ai ales canalul. Alege-l din listă.")
			self.session.openWithCallback(self.selectChannelSelector, MessageBox, mesaj, MessageBox.TYPE_ERROR)
			return
		self.timer.name = self.timerentry_name.value
		self.timer.description = self.timerentry_description.value
		self.timer.justplay = self.timerentry_justplay.value == "zap"
		if self.timerentry_justplay.value == "zap":
			if not self.timerentry_showendtime.value:
				self.timerentry_endtime.value = self.timerentry_starttime.value
		self.timer.resetRepeated()
		self.timer.afterEvent = {
			"nothing": AFTEREVENT.NONE,
			"deepstandby": AFTEREVENT.DEEPSTANDBY,
			"standby": AFTEREVENT.STANDBY,
			"auto": AFTEREVENT.AUTO
			}[self.timerentry_afterevent.value]
		self.timer.service_ref = self.timerentry_service_ref
		self.timer.tags = self.timerentry_tags
		if self.hdsDecodare:
			self.timer.hdsDecodareMaiTarziu = (self.timerentry_justplay.value != "zap" and
				self.timerentry_decodare.value == HdsDecodare.MAI_TARZIU)

		if self.timer.dirname or self.timerentry_dirname.value != defaultMoviePath():
			self.timer.dirname = self.timerentry_dirname.value
			config.movielist.last_timer_videodir.value = self.timer.dirname
			config.movielist.last_timer_videodir.save()

		if self.timerentry_type.value == "once":
			self.timer.begin, self.timer.end = self.getBeginEnd()
		if self.timerentry_type.value == "repeated":
			if self.timerentry_repeated.value == "daily":
				for x in (0, 1, 2, 3, 4, 5, 6):
					self.timer.setRepeated(x)

			if self.timerentry_repeated.value == "weekly":
				self.timer.setRepeated(self.timerentry_weekday.index)

			if self.timerentry_repeated.value == "weekdays":
				for x in (0, 1, 2, 3, 4):
					self.timer.setRepeated(x)

			if self.timerentry_repeated.value == "user":
				for x in (0, 1, 2, 3, 4, 5, 6):
					if self.timerentry_day[x].value:
						self.timer.setRepeated(x)

			self.timer.repeatedbegindate = self.getTimestamp(self.timerentry_repeatedbegindate.value, self.timerentry_starttime.value)
			if self.timer.repeated:
				self.timer.begin = self.getTimestamp(self.timerentry_repeatedbegindate.value, self.timerentry_starttime.value)
				self.timer.end = self.getTimestamp(self.timerentry_repeatedbegindate.value, self.timerentry_endtime.value)
			else:
				# „time” e functia importata din modulul time (from time import time), nu modulul insusi
				self.timer.begin = self.getTimestamp(time(), self.timerentry_starttime.value)
				self.timer.end = self.getTimestamp(time(), self.timerentry_endtime.value)

			# when a timer end is set before the start, add 1 day
			if self.timer.end < self.timer.begin:
				self.timer.end += 86400

		if self.timer.eit is not None:
			event = eEPGCache.getInstance().lookupEventId(self.timer.service_ref.ref, self.timer.eit)
			if event:
				n = event.getNumOfLinkageServices()
				if n > 1:
					tlist = []
					ref = self.session.nav.getCurrentlyPlayingServiceReference()
					parent = self.timer.service_ref.ref
					selection = 0
					for x in range(n):
						i = event.getLinkageService(parent, x)
						if i.toString() == ref.toString():
							selection = x
						tlist.append((i.getName(), i))
					self.session.openWithCallback(self.subserviceSelected, ChoiceBox, title=_("Please select a subservice to record..."), list = tlist, selection = selection)
					return
				elif n > 0:
					parent = self.timer.service_ref.ref
					self.timer.service_ref = ServiceReference(event.getLinkageService(parent, 0))
		self.saveTimer()
		self.close((True, self.timer))

	def incrementStart(self):
		self.timerentry_starttime.increment()
		self["config"].invalidate(self.entryStartTime)

	def decrementStart(self):
		self.timerentry_starttime.decrement()
		self["config"].invalidate(self.entryStartTime)

	def incrementEnd(self):
		if self.entryEndTime is not None:
			self.timerentry_endtime.increment()
			self["config"].invalidate(self.entryEndTime)

	def decrementEnd(self):
		if self.entryEndTime is not None:
			self.timerentry_endtime.decrement()
			self["config"].invalidate(self.entryEndTime)

	def subserviceSelected(self, service):
		if not service is None:
			self.timer.service_ref = ServiceReference(service[1])
		self.saveTimer()
		self.close((True, self.timer))

	def saveTimer(self):
		self.session.nav.RecordTimer.saveTimer()

	def keyCancel(self):
		self.close((False,))

	def pathSelected(self, res):
		if res is not None:
			if config.movielist.videodirs.value != self.timerentry_dirname.choices:
				self.timerentry_dirname.setChoices(config.movielist.videodirs.value, default=res)
			self.timerentry_dirname.value = res
			self["config"].invalidate(self.dirname)
			self.citesteLocul()

	def tagEditFinished(self, ret):
		if ret is not None:
			self.timerentry_tags = ret
			self.timerentry_tagsset.setChoices([not ret and "None" or " ".join(ret)])
			self["config"].invalidate(self.tagsSet)


class TimerLog(Screen, HelpableScreen):
	def __init__(self, session, timer):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.timer = timer
		self.log_entries = self.timer.log_entries[:]
		self.titlu = _("Jurnalul înregistrării")
		self.setTitle(self.titlu)

		self.fillLogList()

		self["loglist"] = MenuList(self.list)
		self["logentry"] = Label()
		# mesajul tehnic original al randului ales, mai mic (numai skinurile care au widgetul il arata)
		self["original"] = StaticText("")

		hds = skinulHds()
		self["key_red"] = tasta(hds, _("Șterge rândul"))
		self["key_green"] = tasta(hds)
		self["key_yellow"] = tasta(hds)
		self["key_blue"] = tasta(hds, _("Golește jurnalul"))

		self.onShown.append(self.updateText)
		self.onLayoutFinish.append(self._dupaAsezare)

		self["actions"] = HelpableActionMap(self, "OkCancelActions", {
			"ok": (self.keyOk, _("Șterge rândul, golește sau închide jurnalul")),
			"cancel": (self.keyClose, _("Închide jurnalul")),
		}, -1)
		self["directii"] = HelpableActionMap(self, "DirectionActions", {
			"up": (self.up, _("Rândul de deasupra")),
			"down": (self.down, _("Rândul de dedesubt")),
			"left": (self.left, _("Pagina de deasupra")),
			"right": (self.right, _("Pagina de dedesubt")),
			# tasta tinuta apasata merge mai departe; ridicarea ei nu face nimic (fara „unknown action” in jurnal)
			"upRepeated": self.up,
			"downRepeated": self.down,
			"leftRepeated": self.left,
			"rightRepeated": self.right,
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -1)
		self["culori"] = HelpableActionMap(self, "ColorActions", {
			"red": (self.deleteEntry, _("Șterge rândul ales")),
			"blue": (self.clearLog, _("Golește jurnalul")),
		}, -1)

	def _dupaAsezare(self):
		self.setTitle(self.titlu)

	def _nimic(self):
		pass

	def keyOk(self):
		lista = []
		if self.list:
			lista.append((_("Șterge rândul"), "sterge"))
			lista.append((_("Golește jurnalul"), "goleste"))
		lista.append((_("Închide"), "inchide"))
		dlg = self.session.openWithCallback(self._dinMeniu, ChoiceBox, title=self.timer.name or
			HIP.numeCanal(self.timer), list=lista)
		dlg.setTitle(self.titlu)

	def _dinMeniu(self, ales):
		if not ales:
			return
		if ales[1] == "sterge":
			self.deleteEntry()
		elif ales[1] == "goleste":
			self.clearLog()
		elif ales[1] == "inchide":
			self.keyClose()

	def deleteEntry(self):
		cur = self["loglist"].getCurrent()
		if cur is None:
			return
		self.log_entries.remove(cur[1])
		self.fillLogList()
		self["loglist"].l.setList(self.list)
		self.updateText()

	def fillLogList(self):
		self.list = [("%s   %s" % (HIP.oraJurnal(x[0]), HIP.textJurnal(x[1], x[2])), x) for x in self.log_entries]

	def clearLog(self):
		self.log_entries = []
		self.fillLogList()
		self["loglist"].l.setList(self.list)
		self.updateText()

	def keyClose(self):
		if self.timer.log_entries != self.log_entries:
			self.timer.log_entries = self.log_entries
			self.close((True, self.timer))
		else:
			self.close((False,))

	def up(self):
		self["loglist"].instance.moveSelection(self["loglist"].instance.moveUp)
		self.updateText()

	def down(self):
		self["loglist"].instance.moveSelection(self["loglist"].instance.moveDown)
		self.updateText()

	def left(self):
		self["loglist"].instance.moveSelection(self["loglist"].instance.pageUp)
		self.updateText()

	def right(self):
		self["loglist"].instance.moveSelection(self["loglist"].instance.pageDown)
		self.updateText()

	def updateText(self):
		cur = self["loglist"].getCurrent() if self.list else None
		if cur:
			x = cur[1]
			self["logentry"].setText(HIP.textJurnal(x[1], x[2]))
			self["original"].setText(str(x[2]))
			puneText(self["key_red"], _("Șterge rândul"))
			puneText(self["key_blue"], _("Golește jurnalul"))
		else:
			self["logentry"].setText(_("Jurnalul este gol."))
			self["original"].setText("")
			puneText(self["key_red"], "")
			puneText(self["key_blue"], "")

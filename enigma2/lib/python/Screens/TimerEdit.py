# -*- coding: utf-8 -*-
# Modificat de moneasoftware.com si hdsatelit.com, 2026
#
# TimerEdit.py: „Înregistrări programate” (tasta TIMER, Meniu > Înregistrări) si fereastra inregistrarilor care se
# suprapun.
#
# TimerEditList: lista temporizatoarelor (Components/TimerList.py deseneaza randurile), sub ea detaliile celui ales si
# locul inregistrarilor noi cu spatiul liber (Components/HdsInregistrariProgramate.stareLocNou: aceeasi logica si
# aceleasi texte ca ecranul „Locul înregistrărilor”, citite pe un fir). Tastele: OK (sau MENU) deschide lista scurta a
# ce se poate face cu inregistrarea aleasa (Modifică, Oprește / Pornește, Șterge, Jurnalul, Adaugă, Șterge cele
# terminate, Locul înregistrărilor), asa ca totul se atinge numai cu sagetile si OK; pe lista goala OK adauga (sau, cand
# locul inregistrarilor nu e bun, intreaba intai: adauga sau alege locul). Verde adauga, Rosu sterge, Galben opreste
# sau porneste din nou, Albastru sterge cele terminate, INFO jurnalul; HELP le arata pe toate (HelpableActionMap). O
# tasta fara efect nu are text; cu skinul HDSatelit (ecranul HdsTimerEditList) tastele sunt StaticText si bara colorata
# a unei taste fara text nu se deseneaza. Pe alte skinuri raman Button, cum le asteapta ele (widget name="key_red"),
# iar ecranul se cauta tot ca TimerEditList. Tastele colorate sunt din ColorActions (o apasare, nu repetate cat e
# tinuta tasta: fiecare apasare salveaza lista pe disc).
#
# Orice intrebare sau lista deschisa pentru o inregistrare ramane legata de acel temporizator (boundFunction), nu de
# randul ales in clipa raspunsului: intre timp pagina web, ghidul sau a doua bara il pot scoate, lista se reface
# (RecordTimer.on_state_change) si alegerea trece pe vecin. Inainte de orice schimbare se verifica daca temporizatorul
# mai e in RecordTimer (HIP.existaInca); timer.py arunca ValueError pe unul scos, iar o exceptie intr-un apel din C++
# inseamna ecranul de eroare.
#
# TimerSanityConflict: „Înregistrări care se suprapun”, deschisa de lista, ghid, a doua bara si inregistrarea
# imediata cu (session, [cea noua, cele suprapuse...]); se inchide cu (True, cea noua) numai dupa o modificare sau o
# oprire (cine a deschis-o incearca din nou) si cu (False, cea noua) la EXIT, cu un mesaj ca inregistrarea noua nu
# s-a pus. Pe skinul HDSatelit (ecranul HdsTimerSanityConflict) cea noua sta sus, neluminata, iar sub ea lista celor
# suprapuse, cu o explicatie; pe alte skinuri raman widgeturile lor (timer1, list, timer2). OK deschide lista scurta a
# ce se poate face.
#
# Ordinea listei, starea, detaliile, locul, orele implicite si oprirea unei inregistrari repetate care merge vin din
# acelasi modul ca pagina web (temporizatoare_web.py).

from Components.ActionMap import HelpableActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components.TimerList import TimerList
from Components.TimerSanityCheck import TimerSanityCheck
from Components.UsageConfig import preferredTimerPath
from Components import HdsInregistrariProgramate as HIP
from RecordTimer import RecordTimerEntry, parseEvent, AFTEREVENT
from .Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.HelpMenu import HelpableScreen
from Screens.MessageBox import MessageBox
from ServiceReference import ServiceReference
from .TimerEntry import TimerEntry, TimerLog, ECRAN_HDS, skinulHds, areEcran, tasta, puneText
from Tools.BoundFunction import boundFunction

# cat de des (ms) se uita ecranul dupa rezultatul citirii locului si cat asteapta cel mult (s)
CEAS_LOC_MS = 250
ASTEPTARE_LOC_S = 15

# ecranul HDSatelit al ferestrei de suprapunere (cea noua sus, cele suprapuse dedesubt)
ECRAN_SUPRAPUNERE_HDS = "HdsTimerSanityConflict"

# ce face Galben pe inregistrarea aleasa
GALBEN_NIMIC = 0
GALBEN_PORNESTE = 1
GALBEN_OPRESTE = 2


def numeInregistrare(t):
	return (getattr(t, "name", "") or HIP.numeCanal(t)) if t is not None else ""


def galbenPentru(t, procesat):
	"""Ce face Galben pe inregistrarea data: o porneste (oprita), o opreste (in asteptare, sau una repetata care merge
	acum: intai cele trei alegeri) sau nimic (terminata, sau una simpla care merge acum)."""
	if t is None:
		return GALBEN_NIMIC
	if t.disabled:
		return GALBEN_PORNESTE
	if procesat:
		return GALBEN_NIMIC
	if t.isRunning() and not t.repeated:
		return GALBEN_NIMIC
	return GALBEN_OPRESTE


class TimerEditList(Screen, HelpableScreen):
	EMPTY = 0
	ENABLE = 1
	DISABLE = 2
	CLEANUP = 3
	DELETE = 4

	def __init__(self, session):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.skinName = [ECRAN_HDS, "TimerEditList"]
		self.titlu = _("Înregistrări programate")
		self.setTitle(self.titlu)

		self.list = []
		self.fillTimerList()
		self["timerlist"] = TimerList(self.list)

		self.key_red_choice = self.EMPTY
		self.key_yellow_choice = self.EMPTY
		self.key_blue_choice = self.EMPTY

		hds = skinulHds()
		self["key_red"] = tasta(hds)
		self["key_green"] = tasta(hds, _("Adaugă"))
		self["key_yellow"] = tasta(hds)
		self["key_blue"] = tasta(hds)
		# sub lista: mesajul listei goale, detaliile celei alese, locul inregistrarilor noi (fraza, problema, detaliul)
		self["lista_goala"] = StaticText("")
		self["detalii"] = StaticText("")
		self["loc"] = StaticText("")
		self["loc_problema"] = StaticText("")
		self["loc_detaliu"] = StaticText("")

		self["actions"] = HelpableActionMap(self, "OkCancelActions", {
			"ok": (self.keyOk, _("Meniul cu ce poți face; pe lista goală, cu locul înregistrărilor bun, o înregistrare nouă")),
			"cancel": (self.leave, _("Închide lista")),
		}, -1)
		self["culori"] = HelpableActionMap(self, "ColorActions", {
			"red": (self.keyRosu, _("Șterge înregistrarea aleasă (întreabă înainte)")),
			"green": (self.addCurrentTimer, _("Adaugă o înregistrare pe canalul de acum")),
			"yellow": (self.keyGalben, _("Oprește înregistrarea aleasă sau o pornește din nou")),
			"blue": (self.keyAlbastru, _("Șterge din listă înregistrările terminate")),
		}, -1)
		self["directii"] = HelpableActionMap(self, "DirectionActions", {
			"up": (self.up, _("Înregistrarea de deasupra")),
			"down": (self.down, _("Înregistrarea de dedesubt")),
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
		self["jurnal"] = HelpableActionMap(self, "TimerEditActions", {
			"log": (self.keyJurnal, _("Jurnalul înregistrării alese")),
		}, -1)
		self["meniu"] = HelpableActionMap(self, "MenuActions", {
			"menu": (self.meniu, _("Meniul cu ce poți face cu înregistrarea aleasă")),
		}, -1)
		self.session.nav.RecordTimer.on_state_change.append(self.onStateChange)

		from enigma import eTimer
		self._inchis = False
		self._loc = None
		self._locCerutLa = 0
		self._ceasLoc = eTimer()
		try:
			self._ceasLoc.callback.append(self._bateLoc)
		except AttributeError:
			self._ceasLoc_conn = self._ceasLoc.timeout.connect(self._bateLoc)
		self.onLayoutFinish.append(self._dupaAsezare)
		self.onShown.append(self.updateState)
		self.onShown.append(self._citesteLocul)
		self.onClose.append(self._laInchidere)

	def _dupaAsezare(self):
		self.setTitle(self.titlu)

	def _nimic(self):
		pass

	def _laInchidere(self):
		self._inchis = True
		self._ceasLoc.stop()
		try:
			self.session.nav.RecordTimer.on_state_change.remove(self.onStateChange)
		except ValueError:
			pass

	# ------------------------------------------------------------------ locul inregistrarilor noi

	def _citesteLocul(self):
		"""La fiecare aratare (si la intoarcerea din alt ecran): ce se stie, apoi o citire noua pe un fir."""
		from time import time
		self._locCerutLa = time()
		self._arataLocul(HIP.stareLocNou(din_nou=True))
		self._ceasLoc.start(CEAS_LOC_MS, False)

	def _bateLoc(self):
		from time import time
		if self._inchis:
			self._ceasLoc.stop()
			return
		rez = HIP.stareLocNou()
		if rez.get("citit") and not rez.get("se_citeste"):
			self._ceasLoc.stop()
			self._arataLocul(rez)
		elif time() - self._locCerutLa > ASTEPTARE_LOC_S:
			# fara rezultat in timp util (disc lent, ceas mutat intre timp): ce se stie, altfel mesajul
			self._ceasLoc.stop()
			if rez.get("citit"):
				self._arataLocul(rez)
			else:
				self._loc = None
				self["loc"].setText("")
				self["loc_problema"].setText(_("Nu am putut citi locul înregistrărilor."))
				self["loc_detaliu"].setText(rez.get("cale") or "")
		elif rez.get("citit"):
			self._arataLocul(rez)

	def _arataLocul(self, rez):
		if not rez.get("citit"):
			self["loc"].setText(rez.get("text", ""))
			self["loc_problema"].setText("")
			self["loc_detaliu"].setText("")
			return
		self._loc = rez
		if rez.get("bun"):
			self["loc"].setText(rez.get("text", ""))
			self["loc_problema"].setText("")
			self["loc_detaliu"].setText(rez.get("detaliu", ""))
		else:
			self["loc"].setText("")
			self["loc_problema"].setText(rez.get("text", ""))
			self["loc_detaliu"].setText(("%s %s" % (rez.get("detaliu", ""), _("OK deschide meniul, cu „Locul înregistrărilor”."))).strip())

	def _locRau(self):
		return self._loc is not None and not self._loc.get("bun")

	def alegeLocul(self):
		"""Ecranul „Locul înregistrărilor” (Screens/HdsLocInregistrari.py) pentru locul inregistrarilor noi; la
		intoarcere lista citeste din nou locul (onShown). Scopul „meniu”: fraza lui de inceput e cea neutra („Nu am unde
		să înregistrez.”), iar dupa alegerea unui disc ramane deschis cu „Gata...”."""
		try:
			from Screens.HdsLocInregistrari import HdsLocInregistrari
		except ImportError:
			self.session.open(MessageBox, _("Alegerea locului nu este în această imagine."), MessageBox.TYPE_INFO,
				timeout=5)
			return
		self.session.open(HdsLocInregistrari, HIP.locNou(), None, "meniu")

	# ------------------------------------------------------------------ miscarea in lista

	def up(self):
		self["timerlist"].instance.moveSelection(self["timerlist"].instance.moveUp)
		self.updateState()

	def down(self):
		self["timerlist"].instance.moveSelection(self["timerlist"].instance.moveDown)
		self.updateState()

	def left(self):
		self["timerlist"].instance.moveSelection(self["timerlist"].instance.pageUp)
		self.updateState()

	def right(self):
		self["timerlist"].instance.moveSelection(self["timerlist"].instance.pageDown)
		self.updateState()

	def _ales(self):
		"""(temporizatorul ales, procesat) sau (None, False)."""
		try:
			sel = self["timerlist"].l.getCurrentSelection()
		except Exception:
			sel = None
		if not sel:
			return None, False
		return sel[0], bool(sel[1])

	def _mai_exista(self, t):
		"""Temporizatorul e inca in RecordTimer; altfel lista se reface (l-a scos altcineva intre timp)."""
		if HIP.existaInca(self.session.nav.RecordTimer, t):
			return True
		self.refill()
		self.updateState()
		return False

	# ------------------------------------------------------------------ OK / MENU: lista scurta

	def keyOk(self):
		cur, _procesat = self._ales()
		if cur is None and not self._locRau():
			self.addCurrentTimer()
		else:
			self.meniu()

	def meniu(self):
		cur, procesat = self._ales()
		lista = []
		if cur is not None:
			lista.append((_("Modifică"), "modifica"))
			galben = galbenPentru(cur, procesat)
			if galben == GALBEN_PORNESTE:
				lista.append((_("Pornește"), "galben"))
			elif galben == GALBEN_OPRESTE:
				lista.append((_("Oprește"), "galben"))
			lista.append((_("Șterge"), "sterge"))
			lista.append((_("Jurnalul înregistrării"), "jurnal"))
		lista.append((_("Adaugă o înregistrare"), "adauga"))
		if HIP.areTerminate(self.list):
			lista.append((_("Șterge cele terminate"), "curata"))
		lista.append((_("Locul înregistrărilor"), "loc"))
		if cur is not None:
			titlu = numeInregistrare(cur)
		elif self._locRau():
			titlu = _("Nu am unde să înregistrez. Alege locul sau adaugă o înregistrare.")
		else:
			titlu = self.titlu
		dlg = self.session.openWithCallback(boundFunction(self._dinMeniu, cur, procesat), ChoiceBox, title=titlu,
			list=lista)
		dlg.setTitle(self.titlu)

	def _dinMeniu(self, t, procesat, ales=None):
		if not ales:
			return
		ce = ales[1]
		if ce == "adauga":
			self.addCurrentTimer()
		elif ce == "curata":
			self.cleanupQuestion()
		elif ce == "loc":
			self.alegeLocul()
		elif t is None or not self._mai_exista(t):
			return
		elif ce == "modifica":
			self.openEdit(t)
		elif ce == "galben":
			self.toggleDisabledState(t)
		elif ce == "sterge":
			self.removeTimerQuestion(t)
		elif ce == "jurnal":
			self.showLog(t)

	# ------------------------------------------------------------------ tastele colorate si INFO

	def keyRosu(self):
		cur, _procesat = self._ales()
		if cur is not None:
			self.removeTimerQuestion(cur)

	def keyGalben(self):
		cur, procesat = self._ales()
		if galbenPentru(cur, procesat) != GALBEN_NIMIC:
			self.toggleDisabledState(cur)

	def keyAlbastru(self):
		if HIP.areTerminate(self.list):
			self.cleanupQuestion()

	def keyJurnal(self):
		cur, _procesat = self._ales()
		if cur is not None:
			self.showLog(cur)

	# ------------------------------------------------------------------ oprire / pornire

	def toggleDisabledState(self, t=None):
		if t is None:
			t, _procesat = self._ales()
		if t is None or not self._mai_exista(t):
			return
		rt = self.session.nav.RecordTimer
		if t.disabled:
			print("[TimerEdit] enable timer")
			t.enable()
			timersanitycheck = TimerSanityCheck(rt.timer_list, t)
			if not timersanitycheck.check():
				t.disable()
				print("[TimerEdit] sanity check failed")
				simulTimerList = timersanitycheck.getSimulTimerList()
				if simulTimerList is not None:
					self.session.openWithCallback(self.finishedEdit, TimerSanityConflict, simulTimerList)
			else:
				if timersanitycheck.doubleCheck():
					t.disable()
		else:
			if t.isRunning():
				if t.repeated:
					dlg = self.session.openWithCallback(boundFunction(self.runningEventCallback, t), ChoiceBox,
						title=HIP.intrebareRepetata(t), list=HIP.alegeriRepetata())
					dlg.setTitle(numeInregistrare(t))
				return
			t.disable()
		rt.timeChanged(t)
		# timeChanged() numai reordoneaza in memorie (timer.py); fara saveTimer() starea noua s-ar pierde la o
		# oprire de curent inainte de urmatoarea salvare
		rt.saveTimer()
		self.refill()
		self.updateState()

	def runningEventCallback(self, t, result=None):
		if result is None or not self._mai_exista(t):
			return
		HIP.opresteRepetata(self.session.nav.RecordTimer, t, result[1])
		self.refill()
		self.updateState()

	# ------------------------------------------------------------------ tastele si textele de sub lista

	def updateState(self):
		cur, procesat = self._ales()
		if cur:
			if self.key_red_choice != self.DELETE:
				puneText(self["key_red"], _("Șterge"))
				self.key_red_choice = self.DELETE
			galben = galbenPentru(cur, procesat)
			if galben == GALBEN_PORNESTE and self.key_yellow_choice != self.ENABLE:
				puneText(self["key_yellow"], _("Pornește"))
				self.key_yellow_choice = self.ENABLE
			elif galben == GALBEN_OPRESTE and self.key_yellow_choice != self.DISABLE:
				puneText(self["key_yellow"], _("Oprește"))
				self.key_yellow_choice = self.DISABLE
			elif galben == GALBEN_NIMIC and self.key_yellow_choice != self.EMPTY:
				puneText(self["key_yellow"], "")
				self.key_yellow_choice = self.EMPTY
			self["lista_goala"].setText("")
			self["detalii"].setText(HIP.detalii(cur, procesat))
		else:
			if self.key_red_choice != self.EMPTY:
				puneText(self["key_red"], "")
				self.key_red_choice = self.EMPTY
			if self.key_yellow_choice != self.EMPTY:
				puneText(self["key_yellow"], "")
				self.key_yellow_choice = self.EMPTY
			# fara „OK” aici: cu locul inregistrarilor rau OK deschide meniul (keyOk), iar asta o spune loc_detaliu
			self["lista_goala"].setText(_("Nu ai nicio înregistrare programată. Apasă VERDE ca să adaugi una sau "
				"alege o emisiune din ghidul TV."))
			self["detalii"].setText("")

		showCleanup = HIP.areTerminate(self.list)
		if showCleanup and (self.key_blue_choice != self.CLEANUP):
			puneText(self["key_blue"], _("Șterge cele terminate"))
			self.key_blue_choice = self.CLEANUP
		elif (not showCleanup) and (self.key_blue_choice != self.EMPTY):
			puneText(self["key_blue"], "")
			self.key_blue_choice = self.EMPTY

	def fillTimerList(self):
		rt = self.session.nav.RecordTimer
		self.list[:] = HIP.listaDin(rt)

	def showLog(self, t=None):
		if t is None:
			t, _procesat = self._ales()
		if t is not None and self._mai_exista(t):
			self.session.openWithCallback(self.finishedEdit, TimerLog, t)

	def openEdit(self, t=None):
		if t is None:
			t, _procesat = self._ales()
		if t is not None and self._mai_exista(t):
			self.session.openWithCallback(self.finishedEdit, TimerEntry, t)

	def cleanupQuestion(self):
		self.session.openWithCallback(self.cleanupTimer, MessageBox, _("Ștergi din listă înregistrările terminate?"),
			default=False)

	def cleanupTimer(self, delete=None):
		if delete:
			self.session.nav.RecordTimer.cleanup()
			# cleanup() schimba numai lista din memorie; fara salvare, cele sterse ar reveni dupa o repornire
			self.session.nav.RecordTimer.saveTimer()
			self.refill()
			self.updateState()

	def removeTimerQuestion(self, cur=None):
		if cur is None:
			cur, _procesat = self._ales()
		if not cur:
			return
		self.session.openWithCallback(boundFunction(self.removeTimer, cur), MessageBox,
			_("Ștergi înregistrarea programată „%s”?") % numeInregistrare(cur), default=False)

	def removeTimer(self, cur, result=None):
		"""„Da” la „Ștergi X?” sterge X (legat la intrebare), niciodata randul ales acum; X scos intre timp = nimic."""
		if not result or cur is None:
			return
		rt = self.session.nav.RecordTimer
		if HIP.existaInca(rt, cur):
			cur.afterEvent = AFTEREVENT.NONE
			rt.removeEntry(cur)
		self.refill()
		self.updateState()

	def refill(self):
		"""Lista din nou din RecordTimer, cu acelasi temporizator ales (daca mai exista)."""
		lst = self["timerlist"]
		ales = lst.getCurrent()
		try:
			index = lst.getCurrentIndex()
		except Exception:
			index = 0
		self.fillTimerList()
		lst.l.setList(self.list)
		if not self.list or lst.instance is None:
			return
		for i, (t, procesat) in enumerate(self.list):
			if t is ales:
				lst.moveToIndex(i)
				return
		lst.moveToIndex(min(index, len(self.list) - 1))

	def addCurrentTimer(self):
		event = None
		service = self.session.nav.getCurrentService()
		if service is not None:
			info = service.info()
			if info is not None:
				event = info.getEvent(0)

		# canalul de acum; fara canal pornit, TimerEntry cere alegerea lui la salvare
		serviceref = ServiceReference(self.session.nav.getCurrentlyPlayingServiceReference())

		if event is None:
			# fara emisiune din ghid: aceleasi ore ca in pagina web (peste cateva minute, o ora)
			inceput, sfarsit = HIP.oreImplicite()
			data = (inceput, sfarsit, "", "", None)
		else:
			data = parseEvent(event, description=False)

		self.addTimer(RecordTimerEntry(serviceref, checkOldTimers=True, dirname=preferredTimerPath(), *data))

	def addTimer(self, timer):
		self.session.openWithCallback(self.finishedAdd, TimerEntry, timer)

	def finishedEdit(self, answer=None):
		if answer and answer[0]:
			entry = answer[1]
			rt = self.session.nav.RecordTimer
			if not HIP.existaInca(rt, entry):
				# scos intre timp (pagina web, ghidul): timeChanged() ar arunca ValueError
				self.refill()
				self.updateState()
				self.session.open(MessageBox, _("Înregistrarea a fost ștearsă între timp, deci schimbarea nu s-a "
					"salvat."), MessageBox.TYPE_INFO, timeout=6)
				return
			timersanitycheck = TimerSanityCheck(rt.timer_list, entry)
			success = False
			if not timersanitycheck.check():
				simulTimerList = timersanitycheck.getSimulTimerList()
				if simulTimerList is not None:
					for x in simulTimerList:
						if x.setAutoincreaseEnd(entry):
							rt.timeChanged(x)
					if not timersanitycheck.check():
						simulTimerList = timersanitycheck.getSimulTimerList()
						if simulTimerList is not None:
							self.session.openWithCallback(self.finishedEdit, TimerSanityConflict, timersanitycheck.getSimulTimerList())
					else:
						success = True
			else:
				success = True
			if success:
				rt.timeChanged(entry)
				# acelasi tipar ca la oprire: timeChanged() fara saveTimer() ar tine modificarea numai in memorie
				rt.saveTimer()

		self.refill()
		self.updateState()

	def finishedAdd(self, answer=None):
		if answer and answer[0]:
			entry = answer[1]
			simulTimerList = self.session.nav.RecordTimer.record(entry)
			if simulTimerList is not None:
				for x in simulTimerList:
					if x.setAutoincreaseEnd(entry):
						self.session.nav.RecordTimer.timeChanged(x)
				simulTimerList = self.session.nav.RecordTimer.record(entry)
				if simulTimerList is not None:
					self.session.openWithCallback(self.finishSanityCorrection, TimerSanityConflict, simulTimerList)
			self.refill()
			self.updateState()

	def finishSanityCorrection(self, answer):
		self.finishedAdd(answer)

	def leave(self):
		self.close()

	def onStateChange(self, entry):
		if self._inchis:
			return
		self.refill()
		self.updateState()


class TimerSanityConflict(Screen, HelpableScreen):
	def __init__(self, session, timer):
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.timer = timer
		self.titlu = _("Înregistrări care se suprapun")
		self.setTitle(self.titlu)
		# o metoda, nu lambda: GUISkin.createGUIScreen cheama direct numai metodele (restul le da lui exec)
		self.onLayoutFinish.append(self._dupaAsezare)
		self.hds = areEcran(ECRAN_SUPRAPUNERE_HDS)

		self.list = []
		self.list2 = []
		for x in timer[1:]:
			self.list2.append((x, False))
		self["timer1"] = TimerList(self.getTimerList(timer[0]))
		self["timer2"] = TimerList(self.list2)
		if self.hds:
			# cea noua sus (neluminata, skinul are selectionDisabled), cele suprapuse dedesubt, o explicatie jos
			self.skinName = [ECRAN_SUPRAPUNERE_HDS, "TimerSanityConflict"]
			self["eticheta_noua"] = StaticText(_("Înregistrarea nouă"))
			self["eticheta_alte"] = StaticText(_("Se suprapune cu") if len(timer) > 1 else "")
			self["explicatie"] = StaticText(self._explicatie())
		else:
			# alte skinuri: widgeturile lor (timer1, list, timer2), randurile listei cu textele noi
			for x in timer[1:]:
				self.list.append((_("Se suprapune cu „%s”") % numeInregistrare(x), x))
			if len(timer) == 1:
				self.list.append(_("Niciun tuner nu poate recepționa acest canal la ora aleasă."))
			self["list"] = MenuList(self.list)

		hds = skinulHds()
		self["key_red"] = tasta(hds, _("Modifică cea nouă"))
		self["key_green"] = tasta(hds)
		self["key_yellow"] = tasta(hds)
		self["key_blue"] = tasta(hds)

		self["actions"] = HelpableActionMap(self, "OkCancelActions", {
			"ok": (self.keyOk, _("Modifică sau oprește o înregistrare")),
			"cancel": (self.leave_cancel, _("Nu pune înregistrarea nouă")),
		}, -1)
		self["culori"] = HelpableActionMap(self, "ColorActions", {
			"red": (self.editTimer1, _("Modifică înregistrarea nouă")),
			"green": (self.keyVerde, _("Oprește sau pornește înregistrarea nouă")),
			"yellow": (self.keyGalben, _("Modifică înregistrarea aleasă din listă")),
			"blue": (self.keyAlbastru, _("Oprește sau pornește înregistrarea aleasă din listă")),
		}, -1)
		self["directii"] = HelpableActionMap(self, "DirectionActions", {
			"up": (self.up, _("Înregistrarea de deasupra")),
			"down": (self.down, _("Înregistrarea de dedesubt")),
			"upRepeated": self.up,
			"downRepeated": self.down,
			# stanga / dreapta si ridicarea tastelor nu au treaba aici (fara „unknown action” in jurnal)
			"left": self._nimic,
			"right": self._nimic,
			"leftRepeated": self._nimic,
			"rightRepeated": self._nimic,
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -1)
		self.onShown.append(self.updateState)

	def _dupaAsezare(self):
		self.setTitle(self.titlu)

	def _explicatie(self):
		if len(self.timer) == 1:
			ce = _("Niciun tuner nu poate recepționa acest canal la ora aleasă.") + " " + \
				_("Verifică antena și tunerele sau alege alt canal.")
		else:
			ce = _("Receptorul nu le poate prinde pe toate deodată. Alege una și apasă OK ca s-o modifici sau s-o "
				"oprești; după schimbare încerc din nou.")
		return ce + " " + _("EXIT: nu pun înregistrarea nouă.")

	def getTimerList(self, timer):
		return [(timer, False)]

	def _nimic(self):
		pass

	def _alta(self):
		"""Inregistrarea aleasa din lista celor suprapuse (sau None)."""
		if len(self.timer) < 2:
			return None
		if self.hds:
			x = self["timer2"].getCurrent()
		else:
			try:
				i = self["list"].getSelectedIndex()
			except Exception:
				i = 0
			x = self.timer[i + 1] if 0 <= i < len(self.timer) - 1 else None
		return x

	def _poateOpri(self, t):
		return t is not None and (t.disabled or not t.isRunning() or t.repeated)

	# ------------------------------------------------------------------ OK: lista scurta

	def keyOk(self):
		t0 = self.timer[0]
		alta = self._alta()
		lista = [(_("Modifică înregistrarea nouă"), ("modifica", t0))]
		if self._poateOpri(t0):
			lista.append(((_("Pornește înregistrarea nouă") if t0.disabled else _("Oprește înregistrarea nouă")),
				("comuta", t0)))
		if alta is not None:
			nume = numeInregistrare(alta)
			lista.append((_("Modifică „%s”") % nume, ("modifica", alta)))
			if self._poateOpri(alta):
				lista.append(((_("Pornește „%s”") if alta.disabled else _("Oprește „%s”")) % nume, ("comuta", alta)))
		lista.append((_("Nu pune înregistrarea nouă"), ("renunta", None)))
		dlg = self.session.openWithCallback(self._dinMeniu, ChoiceBox, title=_("Ce faci cu înregistrările care se "
			"suprapun?"), list=lista)
		dlg.setTitle(self.titlu)

	def _dinMeniu(self, ales=None):
		if not ales:
			return
		ce, t = ales[1]
		if ce == "renunta":
			self.leave_cancel()
		elif ce == "modifica":
			self.session.openWithCallback(self.finishedEdit, TimerEntry, t)
		elif ce == "comuta":
			self._comuta(t)

	# ------------------------------------------------------------------ tastele

	def editTimer1(self):
		self.session.openWithCallback(self.finishedEdit, TimerEntry, self.timer[0])

	def keyVerde(self):
		if self._poateOpri(self.timer[0]):
			self._comuta(self.timer[0])

	def keyGalben(self):
		alta = self._alta()
		if alta is not None:
			self.session.openWithCallback(self.finishedEdit, TimerEntry, alta)

	def keyAlbastru(self):
		alta = self._alta()
		if self._poateOpri(alta):
			self._comuta(alta)

	def _comuta(self, t):
		"""Opreste (sau porneste) inregistrarea data, apoi cine a deschis fereastra incearca din nou."""
		if t.disabled:
			t.disabled = False
		elif not t.isRunning() or t.repeated:
			t.disabled = True
		self._dupaSchimbare(t)

	def finishedEdit(self, answer=None):
		if answer and answer[0]:
			self._dupaSchimbare(answer[1])

	def _dupaSchimbare(self, t):
		# o inregistrare deja pusa, schimbata aici, se reordoneaza si se salveaza; cea noua o pune cine a deschis
		# fereastra, cand incearca din nou
		rt = self.session.nav.RecordTimer
		if t is not self.timer[0] and HIP.existaInca(rt, t):
			try:
				rt.timeChanged(t)
				rt.saveTimer()
			except ValueError as eroare:
				print("[TimerEdit] suprapunere: %s" % eroare)
		self.leave_ok()

	def leave_ok(self):
		self.close((True, self.timer[0]))

	def leave_cancel(self):
		t0 = self.timer[0]
		if HIP.existaInca(self.session.nav.RecordTimer, t0):
			self.close((False, t0))
			return
		alte = ", ".join("„%s”" % numeInregistrare(x) for x in self.timer[1:4])
		if alte:
			text = _("Înregistrarea „%s” nu s-a pus: se suprapune cu %s.") % (numeInregistrare(t0), alte)
		else:
			text = _("Înregistrarea „%s” nu s-a pus: niciun tuner nu poate recepționa canalul la ora aleasă.") % \
				numeInregistrare(t0)
		self.session.openWithCallback(self._dupaMesaj, MessageBox, text, MessageBox.TYPE_INFO, timeout=8)

	def _dupaMesaj(self, *argumente):
		self.close((False, self.timer[0]))

	def up(self):
		if self.hds:
			self["timer2"].instance.moveSelection(self["timer2"].instance.moveUp)
		else:
			self["list"].instance.moveSelection(self["list"].instance.moveUp)
			self["timer2"].moveToIndex(self["list"].getSelectedIndex())
		self.updateState()

	def down(self):
		if self.hds:
			self["timer2"].instance.moveSelection(self["timer2"].instance.moveDown)
		else:
			self["list"].instance.moveSelection(self["list"].instance.moveDown)
			self["timer2"].moveToIndex(self["list"].getSelectedIndex())
		self.updateState()

	def updateState(self):
		t0 = self.timer[0]
		if not self._poateOpri(t0):
			puneText(self["key_green"], "")
		else:
			puneText(self["key_green"], _("Pornește cea nouă") if t0.disabled else _("Oprește cea nouă"))
		alta = self._alta()
		if alta is None:
			# pe skinul HDSatelit tasta fara text nu se vede; pe celelalte ramane numai textul gol
			puneText(self["key_yellow"], "")
			puneText(self["key_blue"], "")
			return
		puneText(self["key_yellow"], _("Modifică cealaltă"))
		if not self._poateOpri(alta):
			puneText(self["key_blue"], "")
		else:
			puneText(self["key_blue"], _("Pornește cealaltă") if alta.disabled else _("Oprește cealaltă"))

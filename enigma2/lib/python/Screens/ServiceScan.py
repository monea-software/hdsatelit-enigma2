# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Screen import Screen
from Components.ServiceScan import ServiceScan as CScan
from Components.ProgressBar import ProgressBar
from Components.Label import Label
from Components.ActionMap import ActionMap
from Components.FIFOList import FIFOList
from Components.Sources.FrontendInfo import FrontendInfo
from enigma import eTimer, ePoint, eSize

class ServiceScanSummary(Screen):
	# HDSatelit: numele de culoare dark era definit doar in vechiul data/skin.xml, care nu se
	# mai incarca (jurnalul de pe receptor: eSlider ... not applied); aici e valoarea lui, scrisa direct
	skin = """
	<screen position="0,0" size="132,64">
		<widget name="Title" position="6,4" size="120,42" font="Regular;16" transparent="1" />
		<widget name="scan_progress" position="6,50" zPosition="1" borderWidth="1" size="56,12" backgroundColor="#25062748" />
		<widget name="Service" position="6,22" size="120,26" font="Regular;12" transparent="1" />
	</screen>"""
	
	def __init__(self, session, parent, showStepSlider = True):
		Screen.__init__(self, session, parent)
		
		self["Title"] = Label(parent.title or "ServiceScan")
		self["Service"] = Label("No Service")
		self["scan_progress"] = ProgressBar()
		
	def updateProgress(self, value):
		self["scan_progress"].setValue(value)

	def updateService(self, name):
		self["Service"].setText(name)

class ServiceScan(Screen):

	# HDSatelit: semn ca se cauta. Pe receptorul real (motor USALS, 19.2E) procentul a stat
	# mult pe loc cat se misca antena si ecranul parea blocat. Widgetul scan_activity arata puncte care
	# cresc de la 1 la 3 cat timp merge cautarea; fiecare cadru incepe cu cel dinainte, deci punctele
	# nu se misca pe loc. La sfarsit se opresc si dispar; rezultatul din scan_state trece in locul lor.
	# Un singur eTimer, doar text (fara imagini, fara texte de tradus).
	ACTIVITY_FRAMES = ("\u2022", "\u2022 \u2022", "\u2022 \u2022 \u2022")
	ACTIVITY_INTERVAL = 400 # ms

	def ok(self):
		print("ok")
		if self["scan"].isDone():
			self.close()
	
	def cancel(self):
		self.close()
		
	def __init__(self, session, scanList):
		Screen.__init__(self, session)
		
		self.scanList = scanList
		# HDSatelit: ecranul nu avea titlu (randul de sus ramanea gol); textul exista deja tradus
		self.setTitle(_("Service Scan"))

		self.session.nav.stopService()
		
		self["scan_progress"] = ProgressBar()
		self["scan_state"] = Label(_("scan state"))
		self["scan_activity"] = Label("")
		# HDSatelit: timpul ramas, transponderele (12 din 89) si rezumatul de la sfarsit
		self["scan_eta"] = Label("")
		self["scan_transponders"] = Label("")
		self["scan_result"] = Label("")
		self["network"] = Label()
		self["transponder"] = Label()
		# HDSatelit: caseta retelei gasite (Components/HdsRetele.py): numele retelei din semnal, frecventele anuntate,
		# canalele cu numarul operatorului; aratata la sfarsit, sub rezumat, numai cand scanarea a citit o retea
		self["scan_network_card"] = Label("")
		self["scan_network_heading"] = Label("")
		self["scan_network_name"] = Label("")
		self["scan_network_facts"] = Label("")
		self["scan_network_hint"] = Label("")
		self.onLayoutFinish.append(self.hdsAscundeReteaua)

		self["pass"] = Label("")
		self["servicelist"] = FIFOList(len=10)
		self["FrontendInfo"] = FrontendInfo()
		
		self["actions"] = ActionMap(["OkCancelActions"], 
			{
				"ok": self.ok,
				"cancel": self.cancel
			})

		# numele activityTimer, nu timer: subclasa DefaultServiceScan isi pune propriul self.timer
		self.activityStep = 0
		self.activityTimer = eTimer()
		self.activityTimer.callback.append(self.updateActivity)
		self.onClose.append(self.stopActivity)
		self.onClose.append(self.hdsPisteDupaScanare)

		self.onFirstExecBegin.append(self.doServiceScan)

	HDS_CASETA = ("scan_network_card", "scan_network_heading", "scan_network_name", "scan_network_facts", "scan_network_hint")
	HDS_CASETA_JOS = 912      # sub ea linia de jos a ferestrei (HdsCadru1240)
	HDS_CASETA_SPATIU = 16    # intre rezumat si caseta, si marginea de sus/jos a casetei

	def hdsAscundeReteaua(self):
		# fundalul casetei: un dreptunghi (Pro) care cuprinde textele, sau o linie subtire deasupra lor (Clasic)
		card = self["scan_network_card"].instance
		self.hdsCasetaLinie = card is not None and card.size().height() <= 2
		for nume in self.HDS_CASETA:
			self[nume].hide()

	def hdsAseazaReteaua(self, arata):
		"""Caseta retelei pusa sub textul rezumatului (care are mai multe sau mai putine randuri, la orice marime a
		textului): titlul, numele, datele si indiciul unul sub altul, fiecare cat ii e textul; fundalul casetei
		cuprinde tot (la Clasic e numai linia de deasupra). Fara loc pana la marginea de jos, ultimele texte se strang."""
		if not arata:
			self.hdsAscundeReteaua()
			return
		from Components import HdsMarireText as MT
		rez = self["scan_result"].instance
		card = self["scan_network_card"].instance
		if rez is None or card is None:
			return
		x, w = card.position().x(), card.size().width()
		pad = self.HDS_CASETA_SPATIU
		y0 = rez.position().y() + MT.inaltimeText(rez) + pad
		y = y0 + pad
		for nume in self.HDS_CASETA[1:]:
			inst = self[nume].instance
			if inst is None:
				continue
			h = MT.inaltimeText(inst) if self[nume].getText() else 0
			h = max(0, min(h, self.HDS_CASETA_JOS - pad - y))
			inst.move(ePoint(inst.position().x(), y))
			inst.resize(eSize(inst.size().width(), max(1, h)))
			if h:
				self[nume].show()
				y += h + 4
			else:
				self[nume].hide()
		card.move(ePoint(x, y0))
		if not getattr(self, "hdsCasetaLinie", False):
			card.resize(eSize(w, max(1, min(y + pad - 4, self.HDS_CASETA_JOS) - y0)))
		self["scan_network_card"].show()

	def doServiceScan(self):
		caseta = {"titlu": self["scan_network_heading"], "nume": self["scan_network_name"], "date": self["scan_network_facts"],
			"indiciu": self["scan_network_hint"], "aseaza": self.hdsAseazaReteaua}
		self["scan"] = CScan(self["scan_progress"], self["scan_state"], self["servicelist"], self["pass"], self.scanList, self["network"], self["transponder"], self["FrontendInfo"], self.session.summary,
			eta=self["scan_eta"], transponders=self["scan_transponders"], result=self["scan_result"], networkCard=caseta)
		self.activityStep = 0
		self["scan_activity"].setText(self.ACTIVITY_FRAMES[0])
		self.activityTimer.start(self.ACTIVITY_INTERVAL)

	def updateActivity(self):
		scan = self.get("scan")
		started = False
		try:
			done = scan is not None and scan.isDone()
			started = scan is not None
		except AttributeError: # starea se pune abia la pornirea cautarii (CScan.doRun)
			done = False
		if done:
			self.stopActivity()
			self.alignResult()
			return
		self.activityStep = (self.activityStep + 1) % len(self.ACTIVITY_FRAMES)
		self["scan_activity"].setText(self.ACTIVITY_FRAMES[self.activityStep])
		# timpul ramas scade si intre doua transpondere (textul se schimba doar din 10 in 10 s)
		if started:
			scan.refreshEta()

	def stopActivity(self):
		self.activityTimer.stop()
		if "scan_activity" in self:
			self["scan_activity"].setText("")

	def alignResult(self):
		# cand punctele stau pe acelasi rand, in fata starii (skinul HDSatelit), rezultatul final
		# trece in locul lor, aliniat cu randurile de deasupra, in loc sa ramana un gol in fata lui
		try:
			(ax, ay) = self["scan_activity"].getPosition()
			(sx, sy) = self["scan_state"].getPosition()
			if ay == sy and ax < sx:
				st = self["scan_state"].instance
				size = st.size()
				st.move(ePoint(ax, ay))
				st.resize(eSize(size.width() + sx - ax, size.height()))
		except AttributeError: # widget fara instanta
			pass

	def hdsPisteDupaScanare(self):
		# HDSatelit (cautarea dupa piste): la inchiderea unei scanari terminate care a gasit
		# canale, cautarea de canale intreaba daca citeste acum pistele canalelor fara piste stiute (teletext,
		# subtitrari, limbi, HbbTV). intreaba_dupa_scanare nu face nimic pe loc (intreaba dupa 0,5 s, cu raspuns „Nu”
		# dupa 30 s), deci iesirea din scanare nu asteapta. Nu intreaba intr-un asistent (scanarea pornita de
		# Wizard.runAsync, sau prima pornire). O eroare de aici nu ajunge la scanare.
		# Intrebarea cuprinde numai ce a trecut prin scanarea aceasta (scanat: pozitiile si transponderele ei): dupa o
		# scanare de cablu, numai canalele de cablu, fara comenzi de mutare a antenei spre sateliti.
		try:
			scan = self.get("scan")
			if scan is None or not scan.isDone() or not getattr(scan, "foundServices", 0):
				return
			if self.hdsDinAsistent():
				return
			ceAScanat = getattr(scan, "hdsCeAScanat", None)
			scanat = ceAScanat() if ceAScanat is not None else None
			from Screens.HdsCautareCanale import intreaba_dupa_scanare
			intreaba_dupa_scanare(self.session, scanat=scanat)
		except Exception as e:
			print("[ServiceScan] pistele dupa scanare: %s" % e)

	def hdsDinAsistent(self):
		try:
			from Components.config import config
			if config.misc.firstrun.value:
				return True
		except (AttributeError, KeyError, ImportError):
			pass
		try:
			from Screens.Wizard import Wizard
		except ImportError:
			return False
		ecrane = [d for (d, _vizibil) in getattr(self.session, "dialog_stack", ())]
		return any(isinstance(d, Wizard) for d in ecrane)

	def createSummary(self):
		print("ServiceScanCreateSummary")
		return ServiceScanSummary
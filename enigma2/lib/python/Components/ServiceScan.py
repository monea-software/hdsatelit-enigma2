# Modificat de moneasoftware.com si hdsatelit.com, 2026
import time
from enigma import eComponentScan, iDVBFrontend
from Components.NimManager import nimmanager as nimmgr


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: motivele erorilor se traduc la afisare."""
	return text


# HDSatelit: timpul ramas si rezumatul de la sfarsitul cautarii.
# Tipurile de serviciu DVB (EN 300 468, service_type) pentru rezumat: TV, din care HD si 4K (UHD), si radio.
# 0x1f (HEVC) e numarat la 4K: pe satelit e folosit aproape numai de canalele UHD.
SERVICE_TYPES_TV = (0x01, 0x11, 0x16, 0x19, 0x1c, 0x1f, 0x20, 0x86, 0xc3)
SERVICE_TYPES_HD = (0x11, 0x19, 0x1c)
SERVICE_TYPES_UHD = (0x1f, 0x20)
SERVICE_TYPES_RADIO = (0x02, 0x0a)

SCAN_ONLY_FREE = eComponentScan.scanOnlyFree

ETA_SAMPLES = 10     # media pe ultimele N transpondere terminate
ETA_STEP = 10        # secunde; estimarea se rotunjeste la 10 s
ETA_MIN = 10         # cat merge cautarea nu se arata niciodata sub 10 s


def hdsTimpCautare():
	"""Components/HdsTimpCautare.py (timpii invatati din cautarile de dinainte), sau None daca lipseste"""
	try:
		from Components import HdsTimpCautare
	except ImportError:
		try:
			import HdsTimpCautare  # pe PC, in teste, Components e chiar dosarul modulului
		except ImportError:
			return None
	return HdsTimpCautare

def durationText(seconds):
	"""3 min 20 s / 45 s / 1 h 5 min; unitatile sunt aceleasi in toate limbile imaginii."""
	seconds = max(0, int(round(seconds)))
	hours, rest = divmod(seconds, 3600)
	minutes, secs = divmod(rest, 60)
	if hours:
		return "%d h %d min" % (hours, minutes) if minutes else "%d h" % hours
	if minutes:
		return "%d min %d s" % (minutes, secs) if secs else "%d min" % minutes
	return "%d s" % secs

def satelliteName(orb_pos):
	try:
		sat_name = str(nimmgr.getSatDescription(orb_pos))
	except KeyError:
		sat_name = ""
	# numele cu pozitia in fata, scrisa ca in restul imaginii (Components/HdsGrade.numeSatelit): '19.2E Astra 1N/1P"
	# din satellites.xml devine '19,2°E Astra 1N/1P"; pozitia din nume, cand numele o are; fara nume, pozitia
	try:
		from Components.HdsGrade import numeSatelit
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		from HdsGrade import numeSatelit
	return numeSatelit(orb_pos, sat_name)

class ServiceScan:

	Idle = 1
	Running = 2
	Done = 3
	Error = 4

	# HDSatelit: motivele se afisau in engleza, fara _(); acum se traduc la afisare (errorText)
	Errors = {
		0: N_("error starting scanning"),
		1: N_("error while scanning"),
		2: N_("no resource manager"),
		3: N_("no channel list")
		}

	def errorText(self, code):
		return _(self.Errors.get(code, "error while scanning"))

	def scanStatusChanged(self):
		if self.state == self.Running:
			self.progressbar.setValue(self.scan.getProgress())
			self.lcd_summary.updateProgress(self.scan.getProgress())
			self.hdsAfisaj(self.scan.getProgress())
			if self.scan.isDone():
				errcode = self.scan.getError()

				if errcode == 0:
					self.state = self.Done
				else:
					self.state = self.Error
					self.errorcode = errcode
				self.network.setText("")
				self.transponder.setText("")
			else:
				self.text.setText(_("scan in progress - %d%% done!") % self.scan.getProgress() + ' ' + _("%d services found!") % (self.foundServices + self.scan.getNumServices()))
				transponder = self.scan.getCurrentTransponder()
				network = ""
				tp_text = ""
				if transponder:
					tp_type = transponder.getSystem()
					if tp_type == iDVBFrontend.feSatellite:
						tp = transponder.getDVBS()
						network = satelliteName(tp.orbital_position)
						tp_text = ("%s %s %d%c / %d / %s") %( { tp.System_DVB_S : "DVB-S",
							tp.System_DVB_S2 : "DVB-S2" }.get(tp.system, tp.System_DVB_S),
							{ tp.Modulation_Auto : "Auto", tp.Modulation_QPSK : "QPSK",
								tp.Modulation_8PSK : "8PSK", tp.Modulation_QAM16 : "QAM16" }.get(tp.modulation, tp.Modulation_QPSK),
							tp.frequency//1000,
							{ tp.Polarisation_Horizontal : 'H', tp.Polarisation_Vertical : 'V', tp.Polarisation_CircularLeft : 'L',
								tp.Polarisation_CircularRight : 'R' }.get(tp.polarisation, tp.Polarisation_Horizontal),
							tp.symbol_rate//1000,
							{ tp.FEC_Auto : "AUTO", tp.FEC_1_2 : "1/2", tp.FEC_2_3 : "2/3",
								tp.FEC_3_4 : "3/4", tp.FEC_5_6 : "5/6", tp.FEC_7_8 : "7/8",
								tp.FEC_8_9 : "8/9", tp.FEC_3_5 : "3/5", tp.FEC_4_5 : "4/5",
								tp.FEC_9_10 : "9/10", tp.FEC_None : "NONE" }.get(tp.fec, tp.FEC_Auto))
					elif tp_type == iDVBFrontend.feCable:
						network = _("Cable")
						tp = transponder.getDVBC()
						tp_text = ("DVB-C %s %d / %d / %s") %( { tp.Modulation_Auto : "AUTO",
							tp.Modulation_QAM16 : "QAM16", tp.Modulation_QAM32 : "QAM32",
							tp.Modulation_QAM64 : "QAM64", tp.Modulation_QAM128 : "QAM128",
							tp.Modulation_QAM256 : "QAM256" }.get(tp.modulation, tp.Modulation_Auto),
							tp.frequency,
							tp.symbol_rate//1000,
							{ tp.FEC_Auto : "AUTO", tp.FEC_1_2 : "1/2", tp.FEC_2_3 : "2/3",
								tp.FEC_3_4 : "3/4", tp.FEC_5_6 : "5/6", tp.FEC_7_8 : "7/8",
								tp.FEC_8_9 : "8/9", tp.FEC_None : "NONE" }.get(tp.fec_inner, tp.FEC_Auto))
					elif tp_type == iDVBFrontend.feTerrestrial:
						network = _("Terrestrial")
						tp = transponder.getDVBT()
						tp_text = ("DVB-T %s %d %s") %( { tp.Modulation_QPSK : "QPSK",
							tp.Modulation_QAM16 : "QAM16", tp.Modulation_QAM64 : "QAM64",
							tp.Modulation_Auto : "AUTO" }.get(tp.modulation, tp.Modulation_Auto),
							tp.frequency,
							{ tp.Bandwidth_8MHz : "Bw 8MHz", tp.Bandwidth_7MHz : "Bw 7MHz", tp.Bandwidth_6MHz : "Bw 6MHz",
								tp.Bandwidth_Auto : "Bw Auto" }.get(tp.bandwidth, tp.Bandwidth_Auto))
					else:
						print("unknown transponder type in scanStatusChanged")
				self.network.setText(network)
				self.transponder.setText(tp_text)
				self.noteProgress(transponder)

		if self.state == self.Done or self.state == self.Error:
			# HDSatelit: numaratorii trecerii se aduna o singura data, la sfarsitul ei
			if not self.passFinished:
				self.finishPass()
			if self.run != len(self.scanList) - 1:
				if self.state == self.Done:
					self.text.setText(_("scan done!") + ' ' + _("%d services found!") % self.foundServices)
				else:
					self.text.setText(_("ERROR - failed to scan (%s)!") % self.errorText(self.errorcode))
				self.execEnd()
				self.run += 1
				self.execBegin()
			else:
				self.hdsOcupat(False)
				self.showResult()

	def __init__(self, progressbar, text, servicelist, passNumber, scanList, network, transponder, frontendInfo, lcd_summary, eta=None, transponders=None, result=None, networkCard=None):
		self.foundServices = 0
		self.progressbar = progressbar
		self.text = text
		self.servicelist = servicelist
		self.passNumber = passNumber
		self.scanList = scanList
		self.frontendInfo = frontendInfo
		self.transponder = transponder
		self.network = network
		self.run = 0
		self.lcd_summary = lcd_summary
		# HDSatelit: etichete optionale (ecranul HDSatelit le are, alte ecrane nu le dau):
		# timpul ramas, "Transpondere: 12 din 89" si rezumatul de la sfarsit
		self.etaLabel = eta
		self.transpondersLabel = transponders
		self.resultLabel = result
		self.startTime = None
		self.durations = []          # secunde pe transponder, ultimele ETA_SAMPLES
		self.etaShown = None         # ultima estimare afisata (secunde, rotunjita)
		self.tpDoneBase = 0          # transpondere terminate in trecerile de dinainte
		self.tpTotalBase = 0         # si cate erau de cautat in ele (la eroare pot fi mai multe)
		self.tpUnavailableBase = 0
		self.unavailableKnown = True
		self.newServices = 0         # None = nu se stie (binar fara getNewServices)
		self.typeCounts = {"tv": 0, "hd": 0, "uhd": 0, "radio": 0, "other": 0}
		self.typesKnown = True
		self.passErrors = []
		self.passFinished = False
		# timpul invatat (Components/HdsTimpCautare.py): ce s-a masurat in trecerea de acum, pe pozitie, se invata la
		# sfarsitul ei; planul fiecarei treceri (felul, pozitiile, cate transpondere) si daca tunerul ei are motor
		self.passMeasured = []       # (pozitia, secunde) pe transponder
		self.plans = {}
		self.motorRuns = {}
		self.posSeen = set()
		self.rotorStart = None
		self.motorCache = None
		# rezultatul scanarii pentru /api/scanare-ultima (Components/HdsScanareUltima.py); None pana la prima trecere
		# sau pe un nucleu fara getFoundServices
		self.hdsUltima = None
		# retelele citite din NIT la sfarsitul scanarii (Components/HdsRetele.rezumat) si caseta lor de pe ecran:
		# {"titlu", "nume", "date", "indiciu"} (etichetele ecranului HDSatelit); fara caseta, randuri in rezumat
		self.hdsRetele = []
		self.networkCard = networkCard or {}

	def doRun(self):
		self.scan = eComponentScan()
		self.frontendInfo.frontend_source = lambda : self.scan.getFrontend()
		self.feid = self.scanList[self.run]["feid"]
		self.flags = self.scanList[self.run]["flags"]
		self.state = self.Idle
		# HDSatelit: numaratorii exacti vin din nucleu (eComponentScan.getTranspondersDone etc.);
		# pe un binar mai vechi, fara ei, numaratoarea se face aici, din transponderul curent
		self.hasCounters = hasattr(self.scan, "getTranspondersDone") and hasattr(self.scan, "getTranspondersTotal")
		if not hasattr(self.scan, "getTranspondersUnavailable"):
			self.unavailableKnown = False
		if not hasattr(self.scan, "getLastServiceType"):
			self.typesKnown = False
		self.passFinished = False
		self.passTypeCounts = {"tv": 0, "hd": 0, "uhd": 0, "radio": 0, "other": 0}
		self.passStart = time.monotonic()
		if self.startTime is None:
			self.startTime = self.passStart
		self.lastCompletion = None   # prima trecere prin transponder nu se masoara (motorul se poate roti un minut)
		self.lastCompletedPos = None
		self.currentPos = None
		self.passDone = 0
		self.passTotal = len(self.scanList[self.run]["transponders"])
		self.fallbackSeen = 0
		self.fallbackKey = None
		self.passMeasured = []
		self.posSeen = set()
		# pozitia antenei la pornirea trecerii (citita o data) si rotirile ramase, calculate din nou numai cand se schimba
		# trecerea, pozitia de acum sau pozitiile atinse (timpul ramas se cere de cateva ori pe secunda)
		self.rotorStart = self.knownRotorPosition() if self.hasMotor(self.run) else None
		self.motorCache = None
		self.scanStatusChanged()

		for x in self.scanList[self.run]["transponders"]:
			self.scan.addInitial(x)

	def updatePass(self):
		size = len(self.scanList)
		if size > 1:
			self.passNumber.setText(_("pass") + " " + str(self.run + 1) + "/" + str(size) + " (" + _("Tuner") + " " + str(self.scanList[self.run]["feid"]) + ")")

	def hdsAfisaj(self, procent):
		# HDSatelit: procentul cautarii pe afisajul din fata (mesajul „Căutarea canalelor” din Components/HdsAfisaj.py,
		# numai daca e ales): tine 15 s dupa fiecare schimbare (cautarea sta uneori mult pe un transponder), 3 s la
		# sfarsit. O eroare de aici nu ajunge la scanare.
		try:
			from Components import HdsAfisaj
			HdsAfisaj.mesaj("evenimente.cautare", max(0, min(100, int(procent))), 15.0 if procent < 100 else 3.0)
		except Exception:
			pass

	def hdsOcupat(self, da):
		# HDSatelit: cat merge scanarea, paznicul receptorului nu reporneste interfata
		# (semnul „ocupat” din Components/HdsPaznic.py, scris pe loc, inainte de acord si de mutarea motorului; altfel
		# paznicul putea opri enigma2 in mijlocul unei scanari cu motor). O eroare de aici nu ajunge la scanare.
		try:
			from Components import HdsPaznic
		except ImportError:
			return
		cheie = "scanare-%d" % id(self)
		if da:
			HdsPaznic.ocupat(cheie, HdsPaznic.MOTIV_SCANARE, HdsPaznic.DURATA_SCANARE_S)
		else:
			HdsPaznic.liber(cheie)

	def execBegin(self):
		self.hdsOcupat(True)
		self.doRun()
		self.hdsUltimaIncepe()
		self.updatePass()
		self.scan.statusChanged.get().append(self.scanStatusChanged)
		self.scan.newService.get().append(self.newService)
		self.servicelist.clear()
		self.state = self.Running
		err = self.scan.start(self.feid, self.flags)
		self.frontendInfo.updateFrontendData()
		if err:
			self.state = self.Error
			self.errorcode = 0
		self.refreshEta()
		self.scanStatusChanged()

	def execEnd(self):
		self.hdsOcupat(False)
		self.scan.statusChanged.get().remove(self.scanStatusChanged)
		self.scan.newService.get().remove(self.newService)
		if not self.isDone():
			print("*** warning *** scan was not finished!")
			# inchisa inainte de capat (Exit, Opreste din web): ce s-a citit pana acum, cu "stare": "oprita"
			self.hdsUltimaTrecere("oprita")

		del self.scan

	def isDone(self):
		return self.state == self.Done or self.state == self.Error

	def newService(self):
		newServiceName = self.scan.getLastServiceName()
		self.servicelist.addItem(newServiceName)
		self.lcd_summary.updateService(newServiceName)
		if self.typesKnown:
			self.countServiceType(self.scan.getLastServiceType())

	def destroy(self):
		pass

	# ---- HDSatelit: timpul ramas ----

	@staticmethod
	def transponderKey(transponder):
		"""Ce deosebeste un transponder de altul, pentru numaratoarea de rezerva si pentru pozitie."""
		if not transponder:
			return None, None
		tp_type = transponder.getSystem()
		if tp_type == iDVBFrontend.feSatellite:
			tp = transponder.getDVBS()
			return (tp_type, tp.orbital_position, tp.frequency, tp.polarisation, tp.symbol_rate), tp.orbital_position
		if tp_type == iDVBFrontend.feCable:
			tp = transponder.getDVBC()
			return (tp_type, tp.frequency, tp.symbol_rate), None
		if tp_type == iDVBFrontend.feTerrestrial:
			tp = transponder.getDVBT()
			return (tp_type, tp.frequency), None
		return None, None

	def noteProgress(self, transponder):
		"""La fiecare schimbare de stare cat merge cautarea (nucleul o trimite cand trece la transponderul
		urmator): tine minte cand s-a terminat fiecare transponder si cat a durat."""
		now = time.monotonic()
		key, pos = self.transponderKey(transponder)
		if self.hasCounters:
			done = self.scan.getTranspondersDone()
			total = self.scan.getTranspondersTotal()
		else:
			if key is not None and key != self.fallbackKey:
				self.fallbackSeen += 1
				self.fallbackKey = key
			done = max(0, self.fallbackSeen - 1)
			total = max(len(self.scanList[self.run]["transponders"]), self.fallbackSeen)
		if done > self.passDone:
			finished = done - self.passDone
			# primul transponder al trecerii si primul de pe alt satelit nu intra in medie: in timpul lor
			# se poate roti motorul antenei (USALS), uneori un minut
			if self.lastCompletion is not None and self.currentPos == self.lastCompletedPos:
				each = (now - self.lastCompletion) / finished
				self.durations.extend([each] * min(finished, ETA_SAMPLES))
				del self.durations[:-ETA_SAMPLES]
				self.passMeasured.extend([(self.currentPos, each)] * finished)
			self.lastCompletion = now
			self.lastCompletedPos = self.currentPos
			self.passDone = done
		self.passTotal = max(total, self.passDone)
		self.currentPos = pos
		if pos is not None:
			self.posSeen.add(pos)
		self.refreshEta(now)

	def futureTransponders(self):
		return sum(len(x["transponders"]) for x in self.scanList[self.run + 1:])

	def overallCounts(self):
		done = self.tpDoneBase + self.passDone
		total = self.tpDoneBase + self.passTotal + self.futureTransponders()
		return done, max(total, done)

	# ---- HDSatelit: timpul invatat din cautarile de dinainte (Components/HdsTimpCautare.py) ----

	def passPlan(self, run):
		"""[(cheia, pozitia sau None, cate transpondere)] pentru trecerea `run`, in ordinea primei aparitii a fiecarei
		pozitii; o singura data pe trecere."""
		if run not in self.plans:
			T = hdsTimpCautare()
			retea = bool(self.scanList[run]["flags"] & getattr(eComponentScan, "scanNetworkSearch", 0))
			plan, index = [], {}
			for tp in self.scanList[run]["transponders"]:
				kind = type(tp).__name__
				if kind.endswith("Satellite"):
					fel, pos = "sat", getattr(tp, "orbital_position", None)
				elif kind.endswith("Cable"):
					fel, pos = "cablu", None
				elif kind.endswith("Terrestrial"):
					fel, pos = "terestru", None
				else:
					continue
				k = T.cheie(fel, pos, retea) if T is not None else fel
				if k not in index:
					index[k] = len(plan)
					plan.append([k, pos, 0])
				plan[index[k]][2] += 1
			self.plans[run] = [tuple(p) for p in plan]
		return self.plans[run]

	def learnedPerTransponder(self, run):
		"""secundele pe transponder invatate pentru trecerea `run` (media pe pozitiile ei, dupa numarul de transpondere);
		None fara modul"""
		T = hdsTimpCautare()
		if T is None:
			return None
		try:
			timpi = T.timpi()
			plan = self.passPlan(run)
			n = sum(c for _k, _p, c in plan)
			if not n:
				return T.PORNIRE_S["sat"]
			return sum(timpi.estimare(k)[0] * c for k, _p, c in plan) / n
		except Exception as e:
			print("[ServiceScan] timpii invatati: %r" % (e,))
			return None

	def hasMotor(self, run):
		if run not in self.motorRuns:
			try:
				from Components import HdsMotorTuner
				feid = self.scanList[run]["feid"]
				self.motorRuns[run] = any(slot == feid for slot, _nume in HdsMotorTuner.tunereCuMotor())
			except Exception:
				self.motorRuns[run] = False
		return self.motorRuns[run]

	def knownRotorPosition(self):
		try:
			from Components import HdsMotorTuner
			p = int(HdsMotorTuner.controlSec().hdsKnownRotorPosition(self.feid))
			return p if 0 <= p < 3600 else None
		except Exception:
			return None

	def motorSecondsLeft(self):
		"""rotirile antenei ramase (secunde), dupa viteza invatata a motorului: pozitiile neatinse ale trecerii de acum si
		ale celor de dupa, in ordine; plecarea necunoscuta nu se numara. Calculate din nou numai cand se schimba trecerea,
		pozitia de acum sau pozitiile atinse."""
		T = hdsTimpCautare()
		if T is None:
			return 0.0
		cheie = (self.run, self.currentPos, len(self.posSeen))
		if self.motorCache is not None and self.motorCache[0] == cheie:
			return self.motorCache[1]
		total = 0.0
		model = None
		prev = self.currentPos if self.currentPos is not None else None
		for run in range(self.run, len(self.scanList)):
			if not self.hasMotor(run):
				continue
			if prev is None and run == self.run:
				prev = self.rotorStart
			for _k, pos, _c in self.passPlan(run):
				if pos is None or (run == self.run and pos in self.posSeen) or pos == prev:
					continue
				if prev is not None:
					model = model or T.modelMotor()
					total += T.secundeMutare(prev, pos, model) or 0.0
				prev = pos
		self.motorCache = (cheie, total)
		return total

	def learnPass(self):
		"""la sfarsitul unei treceri: secundele masurate pe transponder se invata pe cheia pozitiei lor, apoi o scriere"""
		T = hdsTimpCautare()
		if T is None or not self.passMeasured:
			return
		try:
			timpi = T.timpi()
			chei = dict((p, k) for k, p, _c in self.passPlan(self.run))
			grupe = {}
			for pos, each in self.passMeasured:
				k = chei.get(pos) or (self.passPlan(self.run)[0][0] if self.passPlan(self.run) else None)
				if k is not None:
					grupe.setdefault(k, []).append(each)
			for k, secunde in grupe.items():
				print("[ServiceScan] %s: %d transpondere masurate, media invatata %s s" % (k, len(secunde), timpi.invata(k, secunde)))
			timpi.scrie()
		except Exception as e:
			print("[ServiceScan] invatarea timpilor: %r" % (e,))
		self.passMeasured = []

	def etaSeconds(self, now=None):
		"""Secundele ramase, rotunjite. Din transponderele masurate acum si din timpii invatati in cautarile de dinainte
		(Components/HdsTimpCautare.py, cu valori de pornire), plus rotirile antenei dupa viteza invatata a motorului;
		None numai fara masuratori si fara modulul timpilor."""
		learned = self.learnedPerTransponder(self.run)
		if not self.durations and learned is None:
			self.etaShown = None
			return None
		if now is None:
			now = time.monotonic()
		done, total = self.overallCounts()
		future = self.futureTransponders()
		remaining = max(total - done - future, 1)
		if self.durations and learned is not None:
			# ritmul cautarii de acum cantareste tot mai mult cu fiecare transponder masurat
			W = hdsTimpCautare().GREUTATE_INVATAT
			average = (sum(self.durations) + learned * W) / (len(self.durations) + W)
		elif self.durations:
			average = sum(self.durations) / len(self.durations)
		else:
			average = learned
		rest = 0.0
		for run in range(self.run + 1, len(self.scanList)):
			per = self.learnedPerTransponder(run)
			rest += (per if per is not None else average) * len(self.scanList[run]["transponders"])
		rest += self.motorSecondsLeft()
		anchor = self.lastCompletion if self.lastCompletion is not None else self.passStart
		# intre doua transpondere estimarea scade cu timpul, dar nu sub cat ar mai lua cele de dupa
		# transponderul curent; la urmatorul transponder terminat se recalculeaza din media noua
		seconds = max(average * remaining + rest - (now - anchor), average * (remaining - 1) + rest, ETA_MIN)
		# o crestere mai mica decat un pas nu se arata (altfel 30 s -> 40 s -> 30 s la granita rotunjirii);
		# o crestere adevarata (NIT a adus transpondere noi, transpondere mai lente) se arata
		shown = self.etaShown
		if shown is not None and shown < seconds < shown + ETA_STEP:
			return shown
		self.etaShown = int((seconds + ETA_STEP / 2) // ETA_STEP * ETA_STEP) or ETA_MIN
		return self.etaShown

	def refreshEta(self, now=None):
		"""Chemata la fiecare transponder terminat si, din ecran, o data la cateva sute de ms."""
		if self.isDone():
			return
		if self.transpondersLabel is not None:
			done, total = self.overallCounts()
			self.setLabel(self.transpondersLabel, _("Transponders: %d of %d") % (done, total) if total else "")
		if self.etaLabel is not None:
			seconds = self.etaSeconds(now)
			if seconds is None:
				self.setLabel(self.etaLabel, _("Time left: calculating"))
			else:
				self.setLabel(self.etaLabel, _("Time left: about %s") % durationText(seconds))

	@staticmethod
	def setLabel(label, text):
		if label.getText() != text:
			label.setText(text)

	# ---- HDSatelit: rezumatul de la sfarsit ----

	def countServiceType(self, service_type):
		counts = self.passTypeCounts
		if service_type in SERVICE_TYPES_TV:
			counts["tv"] += 1
			if service_type in SERVICE_TYPES_HD:
				counts["hd"] += 1
			elif service_type in SERVICE_TYPES_UHD:
				counts["uhd"] += 1
		elif service_type in SERVICE_TYPES_RADIO:
			counts["radio"] += 1
		else:
			counts["other"] += 1

	def finishPass(self):
		self.passFinished = True
		self.learnPass()
		# la eroare nucleul nu scrie canalele trecerii in lista (insertInto nu se cheama), deci nu se numara
		if self.state == self.Done:
			self.foundServices += self.scan.getNumServices()
			for kind, count in self.passTypeCounts.items():
				self.typeCounts[kind] += count
		if self.hasCounters:
			done = self.scan.getTranspondersDone()
		elif self.state == self.Done:
			done = self.fallbackSeen
		else:
			done = max(0, self.fallbackSeen - 1)
		self.tpDoneBase += done
		self.tpTotalBase += max(self.passTotal, done)
		self.passDone = 0
		self.passTotal = 0
		if self.unavailableKnown:
			self.tpUnavailableBase += self.scan.getTranspondersUnavailable()
		if self.newServices is not None:
			if self.state == self.Error:
				new = 0 # la eroare nucleul nu scrie nimic in lista de canale
			elif hasattr(self.scan, "getNewServices"):
				new = self.scan.getNewServices()
			else:
				new = -1
			self.newServices = self.newServices + new if new >= 0 else None
		if self.state == self.Error:
			self.passErrors.append((self.run + 1, self.scanList[self.run]["feid"], self.errorText(self.errorcode)))
		# rezultatul trecerii, inainte ca pagina sa vada "gata" in /api/scanare-stare (acelasi apel)
		self.hdsUltimaTrecere("terminata" if self.run == len(self.scanList) - 1 else None)

	# ---- HDSatelit: rezultatul ultimei scanari (Components/HdsScanareUltima.py, /api/scanare-ultima) ----

	def hdsUltimaIncepe(self):
		"""La prima trecere: inregistrarea noua ia locul celei de dinainte. La trecerea urmatoare pozitiile ei intra in
		"pozitii"; la o trecere reluata (fereastra ascunsa de alta si aratata din nou, cand nucleul porneste trecerea de
		la capat) cautarea e iar in curs. Numai daca nucleul da lista serviciilor citite; o eroare de aici nu ajunge la
		scanare."""
		try:
			if self.hdsUltima is None:
				if not hasattr(self.scan, "getFoundServices") or not hasattr(self.scan, "getScannedTransponders"):
					return
				from Components import HdsScanareUltima
				self.hdsUltima = HdsScanareUltima.incepe(self.scanList)
				return
			schimbat = False
			if self.hdsUltima.stare != "in_curs":
				self.hdsUltima.stare, self.hdsUltima.sfarsit = "in_curs", None
				schimbat = True
			if self.run + 1 > self.hdsUltima.rulate:
				self.hdsUltima.rulate = self.run + 1
				schimbat = True
			if schimbat:
				self.hdsUltima.publica()
		except Exception as e:
			print("[ServiceScan] rezultatul pentru web: %r" % (e,))

	def hdsUltimaTrecere(self, stare=None):
		"""Ce a citit trecerea de acum (toate serviciile din SDT si transponderele incercate), din nucleu, inainte ca
		obiectul scanarii sa fie sters. `stare` "terminata" sau "oprita" incheie inregistrarea. Lamedb nu se atinge."""
		if self.hdsUltima is None:
			return
		try:
			eroare = None
			try:
				transpondere = self.scan.getScannedTransponders()
				servicii = self.scan.getFoundServices()
			except Exception as e:
				print("[ServiceScan] lista scanarii: %r" % (e,))
				transpondere, servicii, eroare = [], [], "lista scanarii nu s-a putut citi"
			# retelele din NIT (ID, nume, frecventele anuntate, numerele canalelor): numai pe un nucleu care le da;
			# fara ele inregistrarea ramane cea de dinainte
			retele = None
			if hasattr(self.scan, "getNetworks"):
				try:
					retele = self.scan.getNetworks()
				except Exception as e:
					print("[ServiceScan] retelele scanarii: %r" % (e,))
			if self.state == self.Error:
				eroare = "trecerea %d: %s" % (self.run + 1, self.Errors.get(getattr(self, "errorcode", 1), self.Errors[1]))
			self.hdsUltima.trecere(self.run, transpondere, servicii, eroare, retele)
			corp = self.hdsUltima.publica(stare)
		except Exception as e:
			print("[ServiceScan] rezultatul pentru web: %r" % (e,))
			return
		if stare == "terminata":
			self.hdsPastreazaRetele(corp)

	def hdsPastreazaRetele(self, corp):
		"""La sfarsitul scanarii: retelele citite din NIT raman pe receptor (Components/HdsRetele.py, in /etc/enigma2):
		lista retelei in ordinea numerelor operatorului, numele retelei pe bara si in informatii. O scanare fara NIT nu
		schimba nimic. O scanare fara cautare in retea (cablu pe o frecventa, NIT citit numai pentru informatie) a vazut
		numai multiplexul ales: se uneste cu reteaua de dinainte, nu o inlocuieste. O eroare de aici nu ajunge la
		scanare."""
		try:
			from Components import HdsRetele
			self.hdsRetele = HdsRetele.rezumat(corp)
			if self.hdsRetele:
				retea = getattr(eComponentScan, "scanNetworkSearch", 0)
				completa = any(x.get("flags", 0) & retea for x in self.scanList)
				chei = HdsRetele.actualizeaza(corp, completa=completa)
				print("[ServiceScan] retelele pastrate: %s" % (", ".join(chei) or "niciuna (fisierul nu s-a scris)"))
		except Exception as e:
			print("[ServiceScan] retelele scanarii: %r" % (e,))

	def hdsCeAScanat(self):
		"""Ce a trecut prin scanarea aceasta, pentru intrebarea despre piste de la sfarsit
		(Screens/HdsCautareCanale.intreaba_dupa_scanare): {"pozitii": pozitiile din lista de scanare, ca in indexul
		canalelor (pozitia orbitala in zecimi, "cablu", "terestru"), "transpondere": multimea (namespace, tsid, onid) a
		transponderelor care au dat tabele, sau None cand nucleul nu le da}. Dupa o scanare de cablu intrebarea ramane
		la cablu, nu la tot indexul, cu rotirea antenei spre toti satelitii."""
		pozitii = set()
		for x in self.scanList[:self.run + 1]:
			for tp in x["transponders"]:
				kind = type(tp).__name__
				if kind.endswith("Satellite"):
					try:
						pozitii.add(int(tp.orbital_position) % 3600)
					except (AttributeError, TypeError, ValueError):
						pass
				elif kind.endswith("Cable"):
					pozitii.add("cablu")
				elif kind.endswith("Terrestrial"):
					pozitii.add("terestru")
		transpondere = None
		if self.hdsUltima is not None:
			try:
				from Components import HdsScanareUltima
				transpondere = set()
				for numar in sorted(self.hdsUltima.treceri):
					for t in self.hdsUltima.treceri[numar][0]:
						tp = HdsScanareUltima.transponder(t).get("tp")
						if tp:
							ns, tsid, onid = (int(v, 16) for v in tp.split(":"))
							transpondere.add((ns & 0xFFFFFFFF, tsid, onid))
			except Exception as e:
				print("[ServiceScan] transponderele scanarii: %r" % (e,))
				transpondere = None
		return {"pozitii": pozitii, "transpondere": transpondere}

	def scannedPlaces(self):
		"""Satelitii (sau cablul, terestrul) din lista de cautare, in ordinea lor."""
		sats, places = [], []
		for x in self.scanList[:self.run + 1]:
			for tp in x["transponders"]:
				kind = type(tp).__name__
				if kind.endswith("Satellite"):
					name = satelliteName(tp.orbital_position)
					if name not in sats:
						sats.append(name)
				elif kind.endswith("Cable"):
					if _("Cable") not in places:
						places.append(_("Cable"))
				elif kind.endswith("Terrestrial"):
					if _("Terrestrial") not in places:
						places.append(_("Terrestrial"))
		if sats and not places:
			return (_("Satellite: %s") if len(sats) == 1 else _("Satellites: %s")) % ", ".join(sats)
		if sats or places:
			return _("Reception: %s") % ", ".join(sats + places)
		return ""

	def resultLines(self):
		lines = []
		services = self.foundServices
		done = self.tpDoneBase
		unavailable = self.tpUnavailableBase if self.unavailableKnown else None
		if self.state == self.Error and self.errorcode == 0 and not done:
			# cautarea nici n-a pornit: lista goala sau tunerul nu s-a putut rezerva
			if not self.scanList[self.run]["transponders"]:
				lines.append(_("There were no transponders to scan."))
			else:
				lines.append(_("The tuner could not be used. It may be busy with a recording or not configured."))
		if self.state == self.Done and services == 0:
			# de ce nu s-a gasit nimic, din numaratori
			if done == 0:
				lines.append(_("There were no transponders to scan."))
			elif unavailable is not None and unavailable >= done:
				lines.append(_("No transponder had a signal. Check the antenna, the LNB, the cable and the tuner settings (DiSEqC, motor)."))
			elif unavailable is None:
				lines.append(_("No channels were found. Check the antenna and the tuner settings."))
			elif any(x["flags"] & SCAN_ONLY_FREE for x in self.scanList):
				lines.append(_("The transponders had a signal, but no free channels (the scan was for free channels only)."))
			else:
				lines.append(_("The transponders had a signal, but did not send any channels."))
		elif services:
			line = _("Channels found: %d") % services
			if self.newServices is not None:
				line += ", " + _("new: %d") % self.newServices
			lines.append(line)
			if self.typesKnown:
				c = self.typeCounts
				line = _("TV: %d") % c["tv"] + " (" + _("HD: %d") % c["hd"] + ", " + _("4K: %d") % c["uhd"] + "), " + _("radio: %d") % c["radio"]
				if c["other"]:
					line += ", " + _("other services: %d") % c["other"]
				lines.append(line)
		if done or self.state == self.Done:
			line = _("Transponders scanned: %d") % done
			if unavailable is not None:
				line += ", " + _("without signal: %d") % unavailable
			lines.append(line)
		places = self.scannedPlaces()
		# la cablu si terestru caseta retelei spune mai mult decat "Recepție: Cablu" (si lasa loc la textul marit)
		retea = self.hdsReteaPrincipala() if self.hdsAreCaseta() else None
		if places and not (retea is not None and retea.get("sistem") in ("cablu", "terestru") and
				all(x.get("sistem") in ("cablu", "terestru") for x in self.hdsRetele)):
			lines.append(places)
		if self.startTime is not None and (done or self.state == self.Done):
			lines.append(_("Duration: %s") % durationText(time.monotonic() - self.startTime))
		if len(self.scanList) > 1:
			for (number, feid, reason) in self.passErrors:
				lines.append(_("Pass %d, tuner %d: %s") % (number, feid, reason))
		if not self.hdsAreCaseta():
			# ecran fara caseta retelei (alt skin): reteaua gasita in randurile rezumatului
			texte = self.hdsTexteRetea()
			if texte is not None:
				lines.append(_("Rețeaua: %s") % texte["nume"])
				lines.extend(x for x in texte["date"].split("\n") if x)
		return lines

	# ---- HDSatelit: reteaua gasita (Components/HdsRetele.py) ----

	def hdsAreCaseta(self):
		"""Ecranul are caseta retelei (skinul HDSatelit): eticheta numelui cu atribute din skin."""
		nume = self.networkCard.get("nume")
		return nume is not None and bool(getattr(nume, "skinAttributes", None))

	@staticmethod
	def hdsNumeRetea(r):
		return r.get("nume") or _("Rețeaua %d") % r.get("nid", 0)

	def hdsReteaPrincipala(self):
		"""Reteaua din caseta: cea cu cele mai multe canale cu numar, apoi cea cu cele mai multe frecvente anuntate."""
		if not self.hdsRetele:
			return None
		return sorted(self.hdsRetele, key=lambda r: (-r.get("cu_numar", 0), -r.get("frecvente", 0)))[0]

	def hdsCaleLista(self, r):
		"""Unde se gaseste lista retelei in lista de canale: Sateliți › Cablu › <numele retelei>."""
		if r.get("sistem") == "cablu":
			loc = _("Cable")
		elif r.get("sistem") == "terestru":
			loc = _("Terrestrial")
		else:
			loc = satelliteName(r.get("poz", 0)) if r.get("poz") is not None else _("Satellite")
		return u" › ".join((_("Satellites"), loc, self.hdsNumeRetea(r)))

	def hdsTexteRetea(self):
		"""Textele casetei retelei gasite: {"titlu", "nume", "date", "indiciu"} (date si indiciu pe randuri), sau None
		cand scanarea n-a citit nicio retea."""
		r = self.hdsReteaPrincipala()
		if r is None:
			return None
		randuri = [_("Frecvențe anunțate: %d") % r.get("frecvente", 0) + u" · " + _("ID rețea: %d") % r.get("nid", 0)]
		if r.get("cu_numar"):
			randuri.append(_("Canale cu numărul operatorului: %d") % r["cu_numar"] + " (" + _("TV: %d") % r.get("tv", 0) +
				", " + _("radio: %d") % r.get("radio", 0) + ")")
		indiciu = []
		if r.get("cu_numar"):
			indiciu.append(_("Lista în ordinea numerelor: %s") % self.hdsCaleLista(r))
		alte = [self.hdsNumeRetea(x) for x in self.hdsRetele if x is not r]
		if alte:
			indiciu.append(_("Alte rețele: %s") % (u", ".join(alte[:4]) + (u", …" if len(alte) > 4 else u"")))
		return {"titlu": _("Rețeaua operatorului"), "nume": self.hdsNumeRetea(r), "date": "\n".join(randuri),
			"indiciu": "\n".join(indiciu)}

	def hdsArataReteaua(self):
		"""Caseta retelei la sfarsitul scanarii: textele si, prin ecran ("aseaza"), locul ei sub rezumat; fara retea
		caseta ramane ascunsa."""
		if not self.hdsAreCaseta():
			return
		texte = self.hdsTexteRetea()
		for cheie in ("titlu", "nume", "date", "indiciu"):
			eticheta = self.networkCard.get(cheie)
			if eticheta is not None:
				eticheta.setText(texte[cheie] if texte is not None else "")
		aseaza = self.networkCard.get("aseaza")
		if aseaza is not None:
			try:
				aseaza(texte is not None)
			except Exception as e:
				print("[ServiceScan] caseta retelei: %r" % (e,))

	def showResult(self):
		services = self.foundServices
		if self.etaLabel is not None:
			self.etaLabel.setText("")
		if self.transpondersLabel is not None:
			done, total = self.tpDoneBase, max(self.tpTotalBase, self.tpDoneBase)
			self.transpondersLabel.setText(_("Transponders: %d of %d") % (done, total) if done else "")
		if self.resultLabel is None or not getattr(self.resultLabel, "skinAttributes", None):
			# ecran fara locul rezumatului (alt skin; eticheta are totusi o instanta, goala, fara
			# atribute din skin): randul de dinainte, cu numarul corect de canale
			if self.state == self.Error:
				self.text.setText(_("ERROR - failed to scan (%s)!") % self.errorText(self.errorcode))
			else:
				self.text.setText(_("scan done!") + ' ' + _("%d services found!") % services)
			return
		if self.state == self.Error:
			self.text.setText(_("ERROR - failed to scan (%s)!") % self.errorText(self.errorcode))
		elif services:
			self.text.setText(_("Scan finished successfully."))
		else:
			self.text.setText(_("Scan finished, no channels found."))
		self.resultLabel.setText("\n".join(self.resultLines()))
		# rezumatul ia locul listei cu ultimele canale gasite
		self.servicelist.hide()
		self.hdsArataReteaua()

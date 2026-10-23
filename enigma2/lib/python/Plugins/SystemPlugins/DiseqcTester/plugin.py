# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Satconfig import NimSelection
from Screens.Screen import Screen
from Screens.TextBox import TextBox
from Screens.MessageBox import MessageBox

from Plugins.Plugin import PluginDescriptor

from Components.ActionMap import ActionMap, NumberActionMap
from Components.NimManager import nimmanager
from Components.ResourceManager import resourcemanager
from Components.Sources.FrontendStatus import FrontendStatus
from Components.TuneTest import TuneTest
from Components.Sources.List import List
from Components.Sources.Progress import Progress
from Components.Sources.StaticText import StaticText
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, ConfigSelection, ConfigYesNo
from Components.Harddisk import harddiskmanager

import os
import random

# always use:
# setResultType(type)
# setResultParameter(parameter)
# getTextualResult()
class ResultParser:
	def __init__(self):
		pass
	
	TYPE_BYORBPOS = 0
	TYPE_BYINDEX = 1
	TYPE_ALL = 2
	def setResultType(self, type):
		self.type = type
		
	def setResultParameter(self, parameter):
		if self.type == self.TYPE_BYORBPOS:
			self.orbpos = parameter
		elif self.type == self.TYPE_BYINDEX:
			self.index = parameter
			
	def getTextualResultForIndex(self, index, logfulltransponders = False):
		text = ""
		text += "%s:\n" % self.getTextualIndexRepresentation(index)
		
		failed, successful = self.results[index]["failed"], self.results[index]["successful"]
		countfailed = len(failed)
		countsuccessful = len(successful)
		countall = countfailed + countsuccessful
		percentfailed = round(countfailed / float(countall + 0.0001) * 100)
		percentsuccessful = round(countsuccessful / float(countall + 0.0001) * 100)
		text += "Tested %d transponders\n%d (%d %%) transponders succeeded\n%d (%d %%) transponders failed\n" % (countall, countsuccessful, percentsuccessful, countfailed, percentfailed)
		reasons = {}
		completelist = []
		if countfailed > 0:
			for transponder in failed:
				completelist.append({"transponder": transponder[0], "fedata": transponder[-1]})
				reasons[transponder[2]] = reasons.get(transponder[2], [])
				reasons[transponder[2]].append(transponder)
				if transponder[2] == "pids_failed":
					print(transponder[2], "-", transponder[3])
				
			text += "The %d unsuccessful tuning attempts failed for the following reasons:\n" % countfailed
			
			for reason in list(reasons.keys()):
				text += "%s: %d transponders failed\n" % (reason, len(reasons[reason]))
			
			for reason in list(reasons.keys()):
				text += "\n"
				text += "%s previous planes:\n" % reason
				for transponder in reasons[reason]:
					if transponder[1] is not None:
						text += self.getTextualIndexRepresentation(self.getIndexForTransponder(transponder[1]))
					else:
						text += "No transponder tuned"
					text += " ==> " + self.getTextualIndexRepresentation(self.getIndexForTransponder(transponder[0]))
					text += "\n"
					if logfulltransponders:
						text += str(transponder[1])
						text += " ==> "
						text += str(transponder[0])
						text += "\n"
					if reason == "pids_failed":
						text += "(tsid, onid): "
						text += str(transponder[3]['real'])
						text += "(read from sat) != "
						text += str(transponder[3]['expected'])
						text += "(read from file)"
						text += "\n"
					text += "\n"
		if countsuccessful > 0:
			text += "\n"
			text += "Successfully tuned transponders' previous planes:\n" 
			for transponder in successful:
				completelist.append({"transponder": transponder[0], "fedata": transponder[-1]})
				if transponder[1] is not None:
					text += self.getTextualIndexRepresentation(self.getIndexForTransponder(transponder[1]))
				else:
					text += "No transponder tuned"
				text += " ==> " + self.getTextualIndexRepresentation(self.getIndexForTransponder(transponder[0]))
				text += "\n"
		
		text += "------------------------------------------------\n"
		text += "complete transponderlist:\n"
		for entry in completelist:
			text += str(entry["transponder"]) + " -- " + str(entry["fedata"]) + "\n"
		return text

	def getTextualResult(self):
		text = ""
		if self.type == self.TYPE_BYINDEX:
			text += self.getTextualResultForIndex(self.index)
		elif self.type == self.TYPE_BYORBPOS:
			for index in list(self.results.keys()):
				if index[2] == self.orbpos:
					text += self.getTextualResultForIndex(index)
					text += "\n-----------------------------------------------------\n"
		elif self.type == self.TYPE_ALL:
			orderedResults = {}
			for index in list(self.results.keys()):
				orbpos = index[2]
				orderedResults[orbpos] = orderedResults.get(orbpos, [])
				orderedResults[orbpos].append(index)
			ordered_orbpos = list(orderedResults.keys())
			ordered_orbpos.sort()
			for orbpos in ordered_orbpos:
				text += "\n*****************************************\n"
				text += "Orbital position %s:" % str(orbpos)
				text += "\n*****************************************\n"
				for index in orderedResults[orbpos]:
					text += self.getTextualResultForIndex(index, logfulltransponders = True)
					text += "\n-----------------------------------------------------\n"
			
				
		return text

class DiseqcTester(Screen, TuneTest, ResultParser):
	skin = """
		<screen position="90,100" size="520,400" title="DiSEqC Tester" >
		<!--ePixmap pixmap="skin_default/icons/dish_scan.png" position="5,25" zPosition="0" size="119,110" transparent="1" alphatest="on" />
		<widget source="Frontend" render="Label" position="190,10" zPosition="2" size="260,20" font="Regular;19" halign="center" valign="center" transparent="1">
			<convert type="FrontendInfo">SNRdB</convert>
		</widget>
		<eLabel name="snr" text="SNR:" position="120,35" size="60,22" font="Regular;21" halign="right" transparent="1" />
		<widget source="Frontend" render="Progress" position="190,35" size="260,20" pixmap="skin_default/bar_snr.png" borderWidth="2" borderColor="#cccccc">
			<convert type="FrontendInfo">SNR</convert>
		</widget>
		<widget source="Frontend" render="Label" position="460,35" size="60,22" font="Regular;21">
			<convert type="FrontendInfo">SNR</convert>
		</widget>
		<eLabel name="agc" text="AGC:" position="120,60" size="60,22" font="Regular;21" halign="right" transparent="1" />
		<widget source="Frontend" render="Progress" position="190,60" size="260,20" pixmap="skin_default/bar_snr.png" borderWidth="2" borderColor="#cccccc">
			<convert type="FrontendInfo">AGC</convert>
		</widget>
		<widget source="Frontend" render="Label" position="460,60" size="60,22" font="Regular;21">
			<convert type="FrontendInfo">AGC</convert>
		</widget>
		<eLabel name="ber" text="BER:" position="120,85" size="60,22" font="Regular;21" halign="right" transparent="1" />
		<widget source="Frontend" render="Progress" position="190,85" size="260,20" pixmap="skin_default/bar_ber.png" borderWidth="2" borderColor="#cccccc">
			<convert type="FrontendInfo">BER</convert>
		</widget>
		<widget source="Frontend" render="Label" position="460,85" size="60,22" font="Regular;21">
			<convert type="FrontendInfo">BER</convert>
		</widget>
		<eLabel name="lock" text="Lock:" position="120,115" size="60,22" font="Regular;21" halign="right" />
		<widget source="Frontend" render="Pixmap" pixmap="skin_default/icons/lock_on.png" position="190,110" zPosition="1" size="38,31" alphatest="on">
			<convert type="FrontendInfo">LOCK</convert>
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="Frontend" render="Pixmap" pixmap="skin_default/icons/lock_off.png" position="190,110" zPosition="1" size="38,31" alphatest="on">
			<convert type="FrontendInfo">LOCK</convert>
			<convert type="ConditionalShowHide">Invert</convert>
		</widget-->
		<widget source="progress_list" render="Listbox" position="0,0" size="510,150" scrollbarMode="showOnDemand">
			<convert type="TemplatedMultiContent">
				{"template": [
						MultiContentEntryText(pos = (10, 0), size = (330, 25), flags = RT_HALIGN_LEFT, text = 1), # index 1 is the index name,
						MultiContentEntryText(pos = (330, 0), size = (150, 25), flags = RT_HALIGN_RIGHT, text = 2) # index 2 is the status,
					],
				 "fonts": [gFont("Regular", 20)],
				 "itemHeight": 25
				}
			</convert>
		</widget>
		<eLabel name="overall_progress" text="Overall progress:" position="20,162" size="480,22" font="Regular;21" halign="center" transparent="1" />
		<widget source="overall_progress" render="Progress" position="20,192" size="480,20" borderWidth="2" backgroundColor="#254f7497" />
		<eLabel name="overall_progress" text="Progress:" position="20,222" size="480,22" font="Regular;21" halign="center" transparent="1" />
		<widget source="sub_progress" render="Progress" position="20,252" size="480,20" borderWidth="2" backgroundColor="#254f7497" />
		
		<eLabel name="" text="Failed:" position="20,282" size="140,22" font="Regular;21" halign="left" transparent="1" />
		<widget source="failed_counter" render="Label" position="160,282" size="100,20" font="Regular;21" />
		
		<eLabel name="" text="Succeeded:" position="20,312" size="140,22" font="Regular;21" halign="left" transparent="1" />
		<widget source="succeeded_counter" render="Label" position="160,312" size="100,20" font="Regular;21" />
		
		<eLabel name="" text="With errors:" position="20,342" size="140,22" font="Regular;21" halign="left" transparent="1" />
		<widget source="witherrors_counter" render="Label" position="160,342" size="100,20" font="Regular;21" />
		
		<eLabel name="" text="Not tested:" position="20,372" size="140,22" font="Regular;21" halign="left" transparent="1" />
		<widget source="untestable_counter" render="Label" position="160,372" size="100,20" font="Regular;21" />
		
		<widget source="CmdText" render="Label" position="300,282" size="180,200" font="Regular;21" />
		</screen>"""
		
	TEST_TYPE_QUICK = 0
	TEST_TYPE_RANDOM = 1
	TEST_TYPE_COMPLETE = 2
	def __init__(self, session, feid, test_type = TEST_TYPE_QUICK, loopsfailed = 3, loopssuccessful = 1, log = False):
		Screen.__init__(self, session)
		self.feid = feid
		self.test_type = test_type
		self.loopsfailed = loopsfailed
		self.loopssuccessful = loopssuccessful
		self.log = log
		# HDSatelit: canalul oprit de TuneTest cand tunerul e ocupat (TuneTest il tine in oldref numai atunci); pus la
		# loc la inchidere (_laInchidere)
		self.oldref = None
		self.inchis = False
		# TuneTest pune frontend numai cand canalul brut s-a luat; altfel Tuner(self.frontend) cadea la pornire
		self.raw_channel = None
		self.frontend = None
		
		self["actions"] = NumberActionMap(["SetupActions"],
		{
			"ok": self.select,
			"cancel": self.keyCancel,
		}, -2)
		
		TuneTest.__init__(self, feid, stopOnSuccess = self.loopssuccessful, stopOnError = self.loopsfailed)
		#self["Frontend"] = FrontendStatus(frontend_source = lambda : self.frontend, update_interval = 100)
		self["overall_progress"] = Progress()
		self["sub_progress"] = Progress()
		
		self["failed_counter"] = StaticText("0")
		self["succeeded_counter"] = StaticText("0")
		self["witherrors_counter"] = StaticText("0")
		self["untestable_counter"] = StaticText("0")
		
		self.list = []
		self["progress_list"] = List(self.list)
		self["progress_list"].onSelectionChanged.append(self.selectionChanged)
		
		self["CmdText"] = StaticText(_("Please wait while scanning is in progress..."))
				
		self.indexlist = {}
		self.readTransponderList()
		
		self.running = False
		
		self.results = {}
		self.resultsstatus = {}
		# HDSatelit: tunerul nu s-a putut lua (il tine o inregistrare sau alt ecran): proba nu porneste, ecranul spune de ce
		self.faraTuner = self.frontend is None
		
		self.onLayoutFinish.append(self.go)
		self.onClose.append(self._laInchidere)
		
	def getProgressListComponent(self, index, status):
		return (index, self.getTextualIndexRepresentation(index), status)
	
	def clearProgressList(self):
		self.list = []
		self["progress_list"].list = self.list
	
	def addProgressListItem(self, index):
		if index in self.indexlist:
			for entry in self.list:
				if entry[0] == index:
					self.changeProgressListStatus(index, "working")
					return
			self.list.append(self.getProgressListComponent(index, _("working")))
			self["progress_list"].list = self.list
			self["progress_list"].setIndex(len(self.list) - 1)

	def changeProgressListStatus(self, index, status):
		self.newlist = []
		count = 0
		indexpos = 0
		for entry in self.list:
			if entry[0] == index:
				self.newlist.append(self.getProgressListComponent(index, status))
				indexpos = count
			else:
				self.newlist.append(entry)
			count += 1
		self.list = self.newlist
		self["progress_list"].list = self.list
		self["progress_list"].setIndex(indexpos)

	def readTransponderList(self):
		for sat in nimmanager.getSatListForNim(self.feid):
			for transponder in nimmanager.getTransponders(sat[0]):
				#print transponder
				mytransponder = (transponder[1] // 1000, transponder[2] // 1000, transponder[3], transponder[4], transponder[7], sat[0], transponder[5], transponder[6], transponder[8], transponder[9], transponder[10], transponder[11])
				self.analyseTransponder(mytransponder)

	def getIndexForTransponder(self, transponder):
		
		if transponder[0] < 11700:
			band = 1 # low
		else:
			band = 0 # high
		
		polarisation = transponder[2]
		
		sat = transponder[5]
		
		index = (band, polarisation, sat)
		return index

	# sort the transponder into self.transponderlist
	def analyseTransponder(self, transponder):
		index = self.getIndexForTransponder(transponder)
		if index not in self.indexlist:
			self.indexlist[index] = []
		self.indexlist[index].append(transponder)
		#print "self.indexlist:", self.indexlist
	
	# returns a string for the user representing a human readable output for index 
	def getTextualIndexRepresentation(self, index):
		print("getTextualIndexRepresentation:", index)
		text = ""
		
		text += nimmanager.getSatDescription(index[2]) + ", "
		
		if index[0] == 1:
			text += "Low Band, "
		else:
			text += "High Band, "
			
		if index[1] == 0:
			text += "H"
		else:
			text += "V"
		return text
	
	def fillTransponderList(self):
		self.clearTransponder()
		print("----------- fillTransponderList")
		print("index:", self.currentlyTestedIndex)
		keys = list(self.indexlist.keys())
		if self.getContinueScanning():
			print("index:", self.getTextualIndexRepresentation(self.currentlyTestedIndex))
			for transponder in self.indexlist[self.currentlyTestedIndex]:
				self.addTransponder(transponder)
			print("transponderList:", self.transponderlist)
			return True
		else:
			return False
		
	def progressCallback(self, progress):
		if progress[0] != self["sub_progress"].getRange():
			self["sub_progress"].setRange(progress[0])
		self["sub_progress"].setValue(progress[1])

	# logic for scanning order of transponders
	# on go getFirstIndex is called
	def getFirstIndex(self):
		# TODO use other function to scan more randomly
		if self.test_type == self.TEST_TYPE_QUICK:
			self.myindex = 0
			keys = list(self.indexlist.keys())
			keys.sort(key = lambda a: a[2]) # sort by orbpos
			self["overall_progress"].setRange(len(keys))
			self["overall_progress"].setValue(self.myindex)
			return keys[0]
		elif self.test_type == self.TEST_TYPE_RANDOM:
			self.randomkeys = list(self.indexlist.keys())
			random.shuffle(self.randomkeys)
			self.myindex = 0
			self["overall_progress"].setRange(len(self.randomkeys))
			self["overall_progress"].setValue(self.myindex)
			return self.randomkeys[0]
		elif self.test_type == self.TEST_TYPE_COMPLETE:
			keys = list(self.indexlist.keys())
			print("keys:", keys)
			successorindex = {}
			for index in keys:
				successorindex[index] = []
				for otherindex in keys:
					if otherindex != index:
						successorindex[index].append(otherindex)
				random.shuffle(successorindex[index])
			self.keylist = []
			stop = False
			currindex = None
			while not stop:
				if currindex is None or len(successorindex[currindex]) == 0:
					oldindex = currindex
					for index in list(successorindex.keys()):
						if len(successorindex[index]) > 0:
							currindex = index
							self.keylist.append(currindex)
							break
					if currindex == oldindex:
						stop = True
				else:
					currindex = successorindex[currindex].pop()
					self.keylist.append(currindex)
			print("self.keylist:", self.keylist)
			self.myindex = 0
			self["overall_progress"].setRange(len(self.keylist))
			self["overall_progress"].setValue(self.myindex)
			return self.keylist[0]

					
	# after each index is finished, getNextIndex is called to get the next index to scan 
	def getNextIndex(self):
		# TODO use other function to scan more randomly
		if self.test_type == self.TEST_TYPE_QUICK:
			self.myindex += 1
			keys = list(self.indexlist.keys())
			keys.sort(key = lambda a: a[2]) # sort by orbpos
			
			self["overall_progress"].setValue(self.myindex)
			if self.myindex < len(keys):
				return keys[self.myindex]
			else:
				return None
		elif self.test_type == self.TEST_TYPE_RANDOM:
			self.myindex += 1
			keys = self.randomkeys
			
			self["overall_progress"].setValue(self.myindex)
			if self.myindex < len(keys):
				return keys[self.myindex]
			else:
				return None
		elif self.test_type == self.TEST_TYPE_COMPLETE:
			self.myindex += 1
			keys = self.keylist
			
			self["overall_progress"].setValue(self.myindex)
			if self.myindex < len(keys):
				return keys[self.myindex]
			else:
				return None
				
	# after each index is finished and the next index is returned by getNextIndex
	# the algorithm checks, if we should continue scanning
	def getContinueScanning(self):
		if self.test_type == self.TEST_TYPE_QUICK or self.test_type == self.TEST_TYPE_RANDOM:
			return (self.myindex < len(list(self.indexlist.keys())))
		elif self.test_type == self.TEST_TYPE_COMPLETE:
			return (self.myindex < len(self.keylist))
		
	def addResult(self, index, status, failedTune, successfullyTune):
		self.results[index] = self.results.get(index, {"failed": [], "successful": [], "status": None, "internalstatus": None})
		self.resultsstatus[status] = self.resultsstatus.get(status, [])

		oldstatus = self.results[index]["internalstatus"]
		if oldstatus is None:
			self.results[index]["status"] = status
		elif oldstatus == "successful":
			if status == "failed":
				self.results[index]["status"] = "with_errors"
			elif status == "successful":
				self.results[index]["status"] = oldstatus
			elif status == "with_errors":
				self.results[index]["status"] = "with_errors"
			elif status == "not_tested":
				self.results[index]["status"] = oldstatus
		elif oldstatus == "failed":
			if status == "failed":
				self.results[index]["status"] = oldstatus
			elif status == "successful":
				self.results[index]["status"] = "with_errors"
			elif status == "with_errors":
				self.results[index]["status"] = "with_errors"
			elif status == "not_tested":
				self.results[index]["status"] = oldstatus
		elif oldstatus == "with_errors":
			if status == "failed":
				self.results[index]["status"] = oldstatus
			elif status == "successful":
				self.results[index]["status"] = oldstatus
			elif status == "with_errors":
				self.results[index]["status"] = oldstatus
			elif status == "not_tested":
				self.results[index]["status"] = oldstatus
		elif oldstatus == "not_tested":
			self.results[index]["status"] = status
			
		if self.results[index]["status"] != "working":
			self.results[index]["internalstatus"] = self.results[index]["status"] 
		self.results[index]["failed"] = failedTune + self.results[index]["failed"]
		self.results[index]["successful"] = successfullyTune + self.results[index]["successful"]
		
		self.resultsstatus[status].append(index)
	
	def finishedChecking(self):
		print("finishedChecking")
		TuneTest.finishedChecking(self)

		if self.currentlyTestedIndex not in self.results:
			self.results[self.currentlyTestedIndex] = {"failed": [], "successful": [], "status": None, "internalstatus": None}
		
		if len(self.failedTune) > 0 and len(self.successfullyTune) > 0:
			self.changeProgressListStatus(self.currentlyTestedIndex, "with errors")
			self["witherrors_counter"].setText(str(int(self["witherrors_counter"].getText()) + 1))
			self.addResult(self.currentlyTestedIndex, "with_errors", self.failedTune, self.successfullyTune)
		elif len(self.failedTune) == 0 and len(self.successfullyTune) == 0:
			self.changeProgressListStatus(self.currentlyTestedIndex, "not tested")
			self["untestable_counter"].setText(str(int(self["untestable_counter"].getText()) + 1))
			self.addResult(self.currentlyTestedIndex, "untestable", self.failedTune, self.successfullyTune)
		elif len(self.failedTune) > 0:
			self.changeProgressListStatus(self.currentlyTestedIndex, "failed")
			#self["failed_counter"].setText(str(int(self["failed_counter"].getText()) + len(self.failedTune)))
			self["failed_counter"].setText(str(int(self["failed_counter"].getText()) + 1))
			self.addResult(self.currentlyTestedIndex, "failed", self.failedTune, self.successfullyTune)
		else:
			self.changeProgressListStatus(self.currentlyTestedIndex, "successful")
			#self["succeeded_counter"].setText(str(int(self["succeeded_counter"].getText()) + len(self.successfullyTune)))
			self["succeeded_counter"].setText(str(int(self["succeeded_counter"].getText()) + 1))
			self.addResult(self.currentlyTestedIndex, "successful", self.failedTune, self.successfullyTune)
			
			
		#self["failed_counter"].setText(str(int(self["failed_counter"].getText()) + len(self.failedTune)))
		#self["succeeded_counter"].setText(str(int(self["succeeded_counter"].getText()) + len(self.successfullyTune)))
		#if len(self.failedTune) == 0 and len(self.successfullyTune) == 0:
			#self["untestable_counter"].setText(str(int(self["untestable_counter"].getText()) + 1))
			
		self.currentlyTestedIndex = self.getNextIndex()
		self.addProgressListItem(self.currentlyTestedIndex)
		
		if self.fillTransponderList():
			self.run(checkPIDs = True)
		else:
			self.running = False
			self["progress_list"].setIndex(0)
			print("results:", self.results)
			print("resultsstatus:", self.resultsstatus)
			if self.log:
				# HDSatelit: /media/hdd e in RAM pe Viper 4K V20 (tmpfs de 64 KB, poate lipsi):
				# jurnalul merge langa celelalte jurnale, in /home/root/logs
				cale_jurnal = "/home/root/logs/diseqctester.log"
				try:
					os.makedirs(os.path.dirname(cale_jurnal), exist_ok=True)
				except OSError:
					pass
				file = open(cale_jurnal, "w", encoding="utf-8")
				self.setResultType(ResultParser.TYPE_ALL)
				file.write(self.getTextualResult())
				file.close()
				self.session.open(MessageBox, text=_("The results have been written to %s.") % cale_jurnal, type = MessageBox.TYPE_INFO)

	def go(self):
		if self.faraTuner:
			# HDSatelit: inainte timerul TuneTest cadea pe frontend None si proba ramanea agatata, fara niciun mesaj
			self.running = False
			self["CmdText"].setText(_("Tunerul nu se poate folosi acum: îl ține o înregistrare sau alt ecran."))
			return
		self.running = True
		self["failed_counter"].setText("0")
		self["succeeded_counter"].setText("0")
		self["untestable_counter"].setText("0")
		self.currentlyTestedIndex = self.getFirstIndex()
		
		self.clearProgressList()
		self.addProgressListItem(self.currentlyTestedIndex)
		
		if self.fillTransponderList():
			self.run(True)

	def keyCancel(self):
		self.close()

	def updateStatus(self):
		# HDSatelit: dupa inchidere nu se mai acordeaza nimic (timerul sau raspunsul TSID/ONID puteau veni dupa close);
		# Screen.doClose goleste __dict__, deci lipsa atributului inseamna tot inchis
		if getattr(self, "inchis", True):
			return
		TuneTest.updateStatus(self)

	def gotTsidOnid(self, tsid, onid):
		if getattr(self, "inchis", True):
			return
		TuneTest.gotTsidOnid(self, tsid, onid)

	def _laInchidere(self):
		"""HDSatelit: la inchidere (EXIT pe televizor sau Opreste din pagina web) proba se opreste de tot, canalul brut se
		elibereaza si canalul oprit de TuneTest porneste din nou. Inainte timerul mai batea dupa inchidere, tunerul
		ramanea tinut, iar canalul de dinainte nu mai pornea: ecranul ramanea negru pana la o schimbare de canal."""
		self.inchis = True
		self.running = False
		try:
			self.timer.stop()
		except Exception:
			pass
		self.tuner = None
		self.frontend = None
		self.raw_channel = None
		ref, self.oldref = self.oldref, None
		if ref is not None:
			try:
				nav = self.session.nav
				if nav.getCurrentlyPlayingServiceReference() is None:
					nav.playService(ref)
			except Exception as eroare:
				print("[DiseqcTester] canalul de dinainte nu a pornit: %s" % eroare)

	def stareWeb(self):
		"""HDSatelit: starea probei pentru pagina web /proba-diseqc, din aceleasi date pe care le arata ecranul: lista
		planurilor cu starea lor, contoarele, cele doua bare de progres; numai citire."""
		def bara(nume):
			try:
				return [int(self[nume].getValue() or 0), int(self[nume].getRange() or 0)]
			except Exception:
				return [0, 0]
		stari = {"successful": "reusit", "failed": "esuat", "with errors": "cu_erori", "not tested": "netestat"}
		planuri = []
		for intrare in self.list:
			index = intrare[0]
			r = self.results.get(index) or {}
			esuate, reusite = r.get("failed") or [], r.get("successful") or []
			motive = {}
			for x in esuate:
				motive[x[2]] = motive.get(x[2], 0) + 1
			try:
				satelit = nimmanager.getSatDescription(index[2])
			except Exception:
				satelit = str(index[2])
			planuri.append({"index": list(index), "text": intrare[1], "satelit": satelit, "banda_joasa": index[0] == 1,
				"orizontala": index[1] == 0, "stare": stari.get(intrare[2], "in_lucru"), "reusite": len(reusite),
				"esuate": len(esuate), "motive": motive})
		contoare = {}
		for nume, cheie in (("succeeded_counter", "reusite"), ("failed_counter", "esuate"),
				("witherrors_counter", "cu_erori"), ("untestable_counter", "netestate")):
			try:
				contoare[cheie] = int(self[nume].getText() or 0)
			except Exception:
				contoare[cheie] = 0
		fel = {self.TEST_TYPE_QUICK: "quick", self.TEST_TYPE_RANDOM: "random", self.TEST_TYPE_COMPLETE: "complete"}
		return {"in_curs": bool(self.running), "fara_tuner": bool(self.faraTuner), "tuner": self.feid,
			"fel": fel.get(self.test_type, "quick"), "esuate_oprire": self.loopsfailed,
			"reusite_oprire": self.loopssuccessful, "jurnal": bool(self.log), "planuri": planuri, "contoare": contoare,
			"total": bara("overall_progress"), "plan": bara("sub_progress"), "text": self["CmdText"].getText()}

	def textPlan(self, index):
		"""HDSatelit: rezultatul unui plan, acelasi text pe care il arata ecranul la OK (TextBox), pentru pagina web"""
		index = tuple(index)
		if index not in self.results:
			return ""
		return self.getTextualResultForIndex(index)

	def select(self):
		# HDSatelit: lista e goala cand tunerul nu s-a putut lua (faraTuner) sau nu are niciun satelit; OK nu face nimic
		# (getCurrent() da None, iar None[0] in actiunea tastei oprea enigma2)
		cur = self["progress_list"].getCurrent()
		if not cur:
			return
		print("selectedIndex:", cur[0])
		if not self.running:
			index = cur[0]
			#self.setResultType(ResultParser.TYPE_BYORBPOS)
			#self.setResultParameter(index[2])
			self.setResultType(ResultParser.TYPE_BYINDEX)
			self.setResultParameter(index)
			#self.setResultType(ResultParser.TYPE_ALL)
			self.session.open(TextBox, self.getTextualResult())
	
	def selectionChanged(self):
		print("selection changed")
		if len(self.list) > 0 and not self.running:
			self["CmdText"].setText(_("Press OK to get further details for %s") % str(self["progress_list"].getCurrent()[1]))

class DiseqcTesterTestTypeSelection(Screen, ConfigListScreen):

	def __init__(self, session, feid):
		Screen.__init__(self, session)
		# for the skin: first try MediaPlayerSettings, then Setup, this allows individual skinning
		self.skinName = ["DiseqcTesterTestTypeSelection", "Setup" ]
		self.setup_title = _("DiSEqC-Tester settings")
		self.onChangedEntry = [ ]
		self.feid = feid
		
		self.list = []
		ConfigListScreen.__init__(self, self.list, session = self.session, on_change = self.changedEntry)
		
		self["actions"] = ActionMap(["SetupActions"],
			{
				"cancel": self.keyCancel,
				"save": self.keyOK,
				"ok": self.keyOK,
			}, -2)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		
		self.createSetup()
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(self.setup_title)

	def createSetup(self):
		self.testtype = ConfigSelection(choices=dict(alegeriFel()), default = "quick")
		self.testtypeEntry = getConfigListEntry(_("Test Type"), self.testtype)
		self.list.append(self.testtypeEntry)
		
		self.loopsfailed = ConfigSelection(choices=dict(alegeriOprire()), default = OPRIRE_ESUATE)
		self.loopsfailedEntry = getConfigListEntry(_("Stop testing plane after # failed transponders"), self.loopsfailed)
		self.list.append(self.loopsfailedEntry)
		
		self.loopssuccessful = ConfigSelection(choices=dict(alegeriOprire()), default = OPRIRE_REUSITE)
		self.loopssuccessfulEntry = getConfigListEntry(_("Stop testing plane after # successful transponders"), self.loopssuccessful)
		self.list.append(self.loopssuccessfulEntry)
		
		self.log = ConfigYesNo(False)
		if jurnalPeDisc():
			self.logEntry = getConfigListEntry(_("Log results to harddisk"), self.log)
			self.list.append(self.logEntry)
					
		self["config"].list = self.list
		self["config"].l.setList(self.list)
		
	def keyOK(self):
		print(self.testtype.getValue())
		deschideProba(self.session, self.feid, self.testtype.getValue(), self.loopsfailed.value, self.loopssuccessful.value,
			self.log.value)
	
	def keyCancel(self):
		self.close()

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

class DiseqcTesterNimSelection(NimSelection):
	skin = """
		<screen position="160,123" size="400,330" title="Choose Tuner">
		<widget source="nimlist" render="Listbox" position="0,0" size="380,300" scrollbarMode="showOnDemand">
			<convert type="TemplatedMultiContent">
				{"template": [
						MultiContentEntryText(pos = (10, 5), size = (360, 30), flags = RT_HALIGN_LEFT, text = 1), # index 1 is the nim name,
						MultiContentEntryText(pos = (50, 30), size = (320, 30), font = 1, flags = RT_HALIGN_LEFT, text = 2), # index 2 is a description of the nim settings,
					],
				 "fonts": [gFont("Regular", 20), gFont("Regular", 15)],
				 "itemHeight": 70
				}
			</convert>
		</widget>
	</screen>"""
		
	def __init__(self, session, args = None):
		NimSelection.__init__(self, session)

	def setResultClass(self):
		#self.resultclass = DiseqcTester
		self.resultclass = DiseqcTesterTestTypeSelection
		
	def showNim(self, nim):
		return arataTuner(nim)


# ---------------------------------------------------------------- HDSatelit: comune ecranelor si paginii web
# Pagina /proba-diseqc (Plugins/Extensions/HdsWebControl/diseqc_web.py) foloseste aceleasi alegeri, aceeasi lista de
# tunere si acelasi ecran DiseqcTester, deschis pe televizor: proba merge la fel din telecomanda si din pagina.

OPRIRE_ESUATE = "3"
OPRIRE_REUSITE = "1"


def alegeriFel():
	"""felurile probei, (valoare, text), in ordinea de pe ecranul setarilor"""
	return [("quick", _("Quick")), ("random", _("Random")), ("complete", _("Complete"))]


def alegeriOprire():
	"""dupa cate transpondere esuate (sau reusite) se trece la planul urmator; -1 = toate cele cunoscute"""
	return [("-1", "Every known")] + [(str(n), str(n)) for n in range(1, 9)]


def jurnalPeDisc():
	"""randul Log results to harddisk apare numai cu un disc"""
	return harddiskmanager.HDDCount() > 0


def arataTuner(nim):
	"""tunerele din lista probei: DVB-S, fara cele legate de alt tuner sau neconfigurate"""
	nimConfig = nimmanager.getNimConfig(nim.slot)
	if nim.isCompatible("DVB-S"):
		if nimConfig.configMode.value in ("loopthrough", "equal", "satposdepends", "nothing"):
			return False
		if nimConfig.configMode.value == "simple":
			if nimConfig.diseqcMode.value == "positioner":
				return True
		return True
	return False


def tuneriProba():
	"""randurile alegerii tunerului (DiseqcTesterNimSelection): [{slot, nume, text, se_alege}], cu textul de pe ecran
	(Screens/Satconfig.textNim); se_alege ca OK pe ecran (NimSelection.okbuttonClick): un tuner nevid si suportat"""
	from Screens.Satconfig import textNim
	rez = []
	for x in nimmanager.nim_slots:
		if arataTuner(x):
			rez.append({"slot": x.slot, "nume": x.friendly_full_description, "text": textNim(x),
				"se_alege": not x.empty and x.isSupported()})
	return rez


def tipProba(valoare):
	return {"quick": DiseqcTester.TEST_TYPE_QUICK, "random": DiseqcTester.TEST_TYPE_RANDOM,
		"complete": DiseqcTester.TEST_TYPE_COMPLETE}.get(valoare, DiseqcTester.TEST_TYPE_QUICK)


def deschideProba(session, feid, fel, esuate, reusite, jurnal):
	"""ecranul probei pe televizor, ca OK in ecranul setarilor; intoarce fereastra deschisa"""
	return session.open(DiseqcTester, feid = feid, test_type = tipProba(fel), loopsfailed = int(esuate),
		loopssuccessful = int(reusite), log = bool(jurnal))


def DiseqcTesterMain(session, **kwargs):
	session.open(DiseqcTesterNimSelection)
	
def autostart(reason, **kwargs):
	resourcemanager.addResource("DiseqcTester", DiseqcTesterMain)

def Plugins(**kwargs):
	# 0.2.6: proba se deschide numai din meniu, Orientarea și setarea antenei > Proba
	# DiSEqC (data/menu.xml); nu mai apare in lista de extensii
	return [PluginDescriptor(where = PluginDescriptor.WHERE_AUTOSTART, needsRestart = False, fnc = autostart)]

# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
# Satfinder for plugins: the OE-Alliance Satfinder screen (Plugins.SystemPlugins.Satfinder.plugin.Satfinder), kept here
# only so that feed plugins written for OE-Alliance images (FuryBiss, LiveFeed, Satelliweb and others) find the class
# they import or look for, with the attributes they fill: tuning_type ("manual_transponder" / "predefined_transponder"),
# tuning_sat, scan_sat.* (frequency, symbolrate, polarization, fec, fec_s2, system, modulation, rolloff, pilot,
# inversion), satfinder_scan_nims, feid, createConfig, createSetup, newConfig, retune, keyGoScan.
# The image's own signal finder stays Screens/Satfinder.py (menu "Gasire semnal"); this plugin adds no menu entry.
# Source (GPL-2.0): OE-Alliance enigma2, https://github.com/oe-alliance/oe-alliance-enigma2, branch master, file
# lib/python/Plugins/SystemPlugins/Satfinder/plugin.py, last commit of the file e20e0430fb34854582c1971d7912746224c14f71
# (21.06.2014), taken on 13.11.2026. Ported to Python 3 and to this image's ScanSetup (predefined transponder list kept
# in the class, scan started through ScanSetup.startScan so it shows in /api/scanare-ultima, keys as in ScanSetup).
# Modified by moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit), 2026.

from enigma import eDVBResourceManager, eDVBFrontendParametersSatellite

from Screens.ScanSetup import ScanSetup
from Screens.ServiceScan import ServiceScan
from Screens.MessageBox import MessageBox

from Components.Sources.FrontendStatus import FrontendStatus
from Components.ActionMap import NumberActionMap
from Components.NimManager import nimmanager, getConfigSatlist
from Components.config import ConfigSelection, getConfigListEntry
from Components.TuneTest import Tuner


class Satfinder(ScanSetup, ServiceScan):
	def __init__(self, session):
		self.initcomplete = False
		self.frontendData = None
		self.frontend = None
		self.raw_channel = None
		self.tuner = None
		self.transponder = None
		service = session and session.nav.getCurrentService()
		feinfo = service and service.frontendInfo()
		self.frontendData = feinfo and feinfo.getAll(True)
		del feinfo
		del service

		self.typeOfTuningEntry = None
		self.systemEntry = None
		self.satfinderTunerEntry = None
		self.satEntry = None
		self.modulationEntry = None

		ScanSetup.__init__(self, session)
		self.setTitle(_("Satfinder"))
		self["introduction"].setText(_("Press OK to scan"))
		self["Frontend"] = FrontendStatus(frontend_source=lambda: self.frontend, update_interval=100)

		# as in ScanSetup: OkCancelActions + ColorActions, not SetupActions (left/right/digits stay with the list,
		# without "unknown action" in the log at every key)
		self["actions"] = NumberActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.keyGoScan,
			"green": self.keyGoScan,
			"cancel": self.keyCancel,
			"red": self.keyCancel,
		}, -2)

		# Screen.__init__ sets skinName to the class name: the theme's "Satfinder" screen (list, signal bars from
		# "Frontend", the same as the image's signal finder), with the manual scan layout as fallback
		self.skinName = ["Satfinder", "ScanSetup"]

		self.initcomplete = True
		self.session.postScanService = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		self.onClose.append(self.__onClose)
		self.onShow.append(self.prepareFrontend)

	def openFrontend(self):
		res_mgr = eDVBResourceManager.getInstance()
		if res_mgr:
			self.raw_channel = res_mgr.allocateRawChannel(self.feid)
			if self.raw_channel:
				self.frontend = self.raw_channel.getFrontend()
				if self.frontend:
					return True
		return False

	def _luare(self):
		# the image's tuner taking (Components/HdsGasireSemnal.LuareTuner, the one of "Gasire semnal"): stops the channel
		# only if needed, retries for up to 3 s (on HiSilicon the tuner is let go a moment after stopService, so the
		# immediate second try of the original code failed and the screen never tuned), never stops a recording, asks
		# the DAB+/T2-MI coordinator, and puts the channel back at the end
		if getattr(self, "_luareTuner", None) is None:
			try:
				from Components.HdsGasireSemnal import LuareTuner
			except ImportError:
				return None
			self._luareTuner = LuareTuner("satfinder_oea", la_cedare=self._tunerCedat)
		return self._luareTuner

	def prepareFrontend(self):
		self.frontend = None
		self.raw_channel = None
		luare = self._luare()
		if luare is not None:
			luare.ia(self.feid, self._tunerLuat, self.session)
			return
		if not self.openFrontend():
			self.session.nav.stopService()
			if not self.openFrontend():
				if getattr(self.session, "pipshown", False):
					from Screens.InfoBar import InfoBar
					InfoBar.instance and hasattr(InfoBar.instance, "showPiP") and InfoBar.instance.showPiP()
					if not self.openFrontend():
						self.frontend = None
		self.tuner = Tuner(self.frontend)
		self.retune(None)

	def _tunerLuat(self, luat, motiv=""):
		luare = self._luareTuner
		if luat and luare is not None:
			self.raw_channel, self.frontend = luare.canal, luare.frontend
		self.tuner = Tuner(self.frontend)
		self.retune(None)
		if not luat:
			self._tunerOcupat()

	def _tunerCedat(self, motiv=""):
		# an extension asked for the tuner (coordinator): it gets it now
		self.raw_channel = self.frontend = None
		self.tuner = Tuner(None)

	def _tunerOcupat(self):
		msg = _("Sorry that tuner is not available.")
		if self.session.nav.RecordTimer.isRecording():
			msg += _("\nA recording is in progress.")
		self.session.open(MessageBox, msg, MessageBox.TYPE_ERROR)

	def _daDrumulTunerului(self, redaCanalul):
		self.frontend = None
		self.raw_channel = None
		luare = getattr(self, "_luareTuner", None)
		if luare is not None:
			luare.elibereaza(reda_canalul=redaCanalul)
			return True
		return False

	def __onClose(self):
		if not self._daDrumulTunerului(True):
			self.session.nav.playService(self.session.postScanService)

	def createSetup(self):
		self.list = []
		self.satfinderTunerEntry = getConfigListEntry(_("Tuner"), self.satfinder_scan_nims)
		self.list.append(self.satfinderTunerEntry)
		self.tuning_sat = self.scan_satselection[self.getSelectedSatIndex(self.feid)]
		self.satEntry = getConfigListEntry(_("Satellite"), self.tuning_sat)
		self.list.append(self.satEntry)
		self.updatePreDefTransponders()
		self.typeOfTuningEntry = getConfigListEntry(_("Tune"), self.tuning_type)
		self.list.append(self.typeOfTuningEntry)

		nim = nimmanager.nim_slots[self.feid]

		if self.tuning_type.value == "manual_transponder":
			if nim.isCompatible("DVB-S2"):
				self.systemEntry = getConfigListEntry(_("System"), self.scan_sat.system)
				self.list.append(self.systemEntry)
			else:
				self.scan_sat.system.value = eDVBFrontendParametersSatellite.System_DVB_S
			self.list.append(getConfigListEntry(_("Frequency"), self.scan_sat.frequency))
			self.list.append(getConfigListEntry(_("Polarization"), self.scan_sat.polarization))
			self.list.append(getConfigListEntry(_("Symbol rate"), self.scan_sat.symbolrate))
			self.list.append(getConfigListEntry(_("Inversion"), self.scan_sat.inversion))
			if self.scan_sat.system.value == eDVBFrontendParametersSatellite.System_DVB_S:
				self.list.append(getConfigListEntry(_("FEC"), self.scan_sat.fec))
			elif self.scan_sat.system.value == eDVBFrontendParametersSatellite.System_DVB_S2:
				self.list.append(getConfigListEntry(_("FEC"), self.scan_sat.fec_s2))
				self.modulationEntry = getConfigListEntry(_("Modulation"), self.scan_sat.modulation)
				self.list.append(self.modulationEntry)
				self.list.append(getConfigListEntry(_("Roll-off"), self.scan_sat.rolloff))
				self.list.append(getConfigListEntry(_("Pilot"), self.scan_sat.pilot))
		elif self.preDefTransponders and self.tuning_type.value == "predefined_transponder":
			self.list.append(getConfigListEntry(_("Transponder"), self.preDefTransponders))
		self["config"].list = self.list
		self["config"].l.setList(self.list)
		self.retune(None)

	def newConfig(self):
		cur = self["config"].getCurrent()
		if cur in (self.typeOfTuningEntry, self.systemEntry):
			self.createSetup()
		elif cur == self.satfinderTunerEntry:
			self.feid = int(self.satfinder_scan_nims.value)
			self.prepareFrontend()
			self.createSetup()
			# with the image's tuner taking the answer may come later: _tunerLuat shows the message then
			if self.frontend is None and getattr(self, "_luareTuner", None) is None:
				self._tunerOcupat()
		elif cur == self.satEntry:
			self.createSetup()

	def _transponderDinConfig(self):
		# (frequency, sr, pol, fec, inversion, orbpos, system, modulation, rolloff, pilot) from the fields, or None
		if not getattr(self, "tuning_sat", None) or not self.tuning_sat.value:
			return None
		satpos = int(self.tuning_sat.value)
		if self.tuning_type.value == "manual_transponder":
			if self.scan_sat.system.value == eDVBFrontendParametersSatellite.System_DVB_S2:
				fec = self.scan_sat.fec_s2.value
			else:
				fec = self.scan_sat.fec.value
			return (
				self.scan_sat.frequency.value,
				self.scan_sat.symbolrate.value,
				self.scan_sat.polarization.value,
				fec,
				self.scan_sat.inversion.value,
				satpos,
				self.scan_sat.system.value,
				self.scan_sat.modulation.value,
				self.scan_sat.rolloff.value,
				self.scan_sat.pilot.value)
		if self.tuning_type.value == "predefined_transponder" and self.preDefTransponders:
			tps = self._transpondereSatelit(satpos)
			i = self.preDefTransponders.index
			if 0 <= i < len(tps):
				tp = tps[i]
				return (tp[1] // 1000, tp[2] // 1000, tp[3], tp[4], 2, satpos, tp[5], tp[6], tp[8], tp[9])
		return None

	def retune(self, configElement):
		transponder = self._transponderDinConfig()
		if transponder is not None:
			self.tune(transponder)

	def createConfig(self, foo):
		self.preDefTransponders = None
		self.tuning_type = ConfigSelection(choices=[("manual_transponder", _("User defined transponder")),
			("predefined_transponder", _("Predefined transponder"))], default="predefined_transponder")
		self.orbital_position = 192
		if self.frontendData and "orbital_position" in self.frontendData:
			self.orbital_position = self.frontendData["orbital_position"]
		ScanSetup.createConfig(self, self.frontendData)

		for x in (self.tuning_type, self.scan_sat.frequency, self.scan_sat.inversion, self.scan_sat.symbolrate,
				self.scan_sat.polarization, self.scan_sat.fec, self.scan_sat.pilot, self.scan_sat.fec_s2,
				self.scan_sat.modulation, self.scan_sat.rolloff, self.scan_sat.system):
			x.addNotifier(self.retune, initial_call=False)

		satfinder_nim_list = []
		for n in nimmanager.nim_slots:
			if not n.isCompatible("DVB-S"):
				continue
			if n.config_mode in ("loopthrough", "satposdepends", "nothing"):
				continue
			if n.config_mode == "advanced" and len(nimmanager.getSatListForNim(n.slot)) < 1:
				continue
			satfinder_nim_list.append((str(n.slot), n.friendly_full_description))
		self.satfinder_scan_nims = ConfigSelection(choices=satfinder_nim_list)
		self.feid = int(self.satfinder_scan_nims.value) if satfinder_nim_list else 0

		self.satList = []
		self.scan_satselection = []
		for slot in nimmanager.nim_slots:
			if slot.isCompatible("DVB-S"):
				self.satList.append(nimmanager.getSatListForNim(slot.slot))
				self.scan_satselection.append(getConfigSatlist(self.orbital_position, self.satList[slot.slot]))
			else:
				self.satList.append(None)

	def getSelectedSatIndex(self, v):
		index = 0
		none_cnt = 0
		for n in self.satList:
			if self.satList[index] is None:
				none_cnt += 1
			if index == int(v):
				return index - none_cnt
			index += 1
		return -1

	@staticmethod
	def _transpondereSatelit(orbpos):
		# only DVB-S/S2 entries of satellites.xml (type 0), in file order
		return [tp for tp in nimmanager.getTransponders(orbpos) if tp[0] == 0]

	@staticmethod
	def _textTransponder(tp):
		pol = {0: "H", 1: "V", 2: "L", 3: "R"}.get(tp[3], "?")
		return "%d %s %d" % (tp[1] // 1000, pol, tp[2] // 1000)

	def predefinedTranspondersList(self, orbpos):
		# same contract as the OE-Alliance ScanSetup method: fills self.preDefTransponders (ConfigSelection) with the
		# transponders of the satellite and preselects the one matching scan_sat, if any
		default = None
		if orbpos is not None:
			if self.scan_sat.system.value == eDVBFrontendParametersSatellite.System_DVB_S2:
				fec = self.scan_sat.fec_s2.value
			else:
				fec = self.scan_sat.fec.value
			alegeri = []
			for i, tp in enumerate(self._transpondereSatelit(orbpos)):
				if default is None and tp[1] // 1000 == self.scan_sat.frequency.value and \
						tp[2] // 1000 == self.scan_sat.symbolrate.value and tp[3] == self.scan_sat.polarization.value \
						and tp[4] == fec:
					default = str(i)
				alegeri.append((str(i), self._textTransponder(tp)))
			self.preDefTransponders = ConfigSelection(choices=alegeri, default=default) if alegeri else None
		return default

	def updatePreDefTransponders(self):
		self.predefinedTranspondersList(self.tuning_sat.orbital_position)
		if self.preDefTransponders:
			self.preDefTransponders.addNotifier(self.retune, initial_call=False)

	def keyGoScan(self):
		if not self.transponder:
			# a plugin may fill the fields and scan in the same moment, before the tuner is taken (it comes a little
			# later, from a timer): the transponder is then read from the fields
			self.transponder = self._transponderDinConfig()
		if not self.transponder:
			return
		# the scan takes the tuner itself: ours is let go (the channel stopped by us comes back when the screen closes)
		self._daDrumulTunerului(False)
		tlist = []
		self.addSatTransponder(tlist,
			self.transponder[0],  # frequency
			self.transponder[1],  # sr
			self.transponder[2],  # pol
			self.transponder[3],  # fec
			self.transponder[4],  # inversion
			self.tuning_sat.orbital_position,
			self.transponder[6],  # system
			self.transponder[7],  # modulation
			self.transponder[8],  # rolloff
			self.transponder[9])  # pilot
		self.startScan(tlist, self.feid)

	def startScan(self, tlist, feid, *argumente):
		# plugins call it with (tlist, feid) as on OE-Alliance; ScanSetup.keyGo of this image calls (tlist, flags, feid)
		flags = 0
		if argumente:
			flags, feid = feid, argumente[0]
		# the image's own start: the kind of scan for the web page of the last scan, the same window and messages
		manual = getattr(self, "tuning_type", None) is not None and self.tuning_type.value == "manual_transponder"
		self.hdsFel = "satelit/manual" if manual else "satelit/transponder"
		self.finished_cb = self.startScanCallback
		ScanSetup.startScan(self, tlist, flags, feid)

	def startScanCallback(self, answer=None):
		if answer:
			self.doCloseRecursive()

	def keyCancel(self):
		if self.session.postScanService and self.frontend:
			self.frontend = None
			self.raw_channel = None
		self.close(False)

	def doCloseRecursive(self):
		if self.session.postScanService and self.frontend:
			self.frontend = None
			self.raw_channel = None
		self.close(True)

	def tune(self, transponder):
		if self.initcomplete and transponder is not None and self.tuner is not None:
			self.tuner.tune(transponder)
			self.transponder = transponder


def SatfinderMain(session, close=None, **kwargs):
	session.openWithCallback(close, Satfinder)


def Plugins(**kwargs):
	# no menu entry: the image has its own signal finder; the class above is here for other plugins
	return []

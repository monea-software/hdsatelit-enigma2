# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen
from Screens.LocationBox import MovieLocationBox, TimeshiftLocationBox
from Screens.MessageBox import MessageBox
from Components.Label import Label
from Components.config import config, ConfigSelection, getConfigListEntry, configfile
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from Components.UsageConfig import preferredPath
from Components import HdsDosareInregistrari as HDI

# HDSatelit: alegerile randurilor, verificarea dosarului si salvarea sunt in Components/HdsDosareInregistrari.py,
# folosit si de pagina web /locuri-inregistrari (HdsWebControl/disc_web.py).

class RecordPathsSettings(Screen,ConfigListScreen):
	skin = """
		<screen name="RecordPathsSettings" position="160,150" size="450,200" title="Recording paths">
			<ePixmap pixmap="skin_default/buttons/red.png" position="10,0" size="140,40" alphatest="on" />
			<ePixmap pixmap="skin_default/buttons/green.png" position="300,0" size="140,40" alphatest="on" />
			<widget source="key_red" render="Label" position="10,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
			<widget source="key_green" render="Label" position="300,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1" />
			<widget name="config" position="10,44" size="430,146" />
		</screen>"""

	def __init__(self, session):
		from Components.Sources.StaticText import StaticText
		Screen.__init__(self, session)
		# HDSatelit: titlul ecranului (capul ferestrelor Pro il arata; fara el capul ramanea gol), numele din meniu
		self.setTitle(_("Recording Locations"))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))

		ConfigListScreen.__init__(self, [])
		self.initConfigList()

		self["setupActions"] = ActionMap(["SetupActions", "ColorActions"],
		{
		    "green": self.save,
		    "red": self.cancel,
		    "cancel": self.cancel,
		    "ok": self.ok,
		}, -2)

	def checkReadWriteDir(self, configele):
		print("checkReadWrite: ", configele.value)
		if HDI.poateScrie(configele.value):
			configele.last_value = configele.value
			return True
		else:
			dir = configele.value
			configele.value = configele.last_value
			self.session.open(
				MessageBox,
				HDI.textNuSePoateScrie(dir),
				type = MessageBox.TYPE_ERROR
				)
			return False

	def initConfigList(self):
		self.styles = HDI.stiluri()
		default = config.usage.default_path.value
		self.default_dirname = ConfigSelection(default = default, choices = HDI.alegeriImplicit(config, default))
		default = config.usage.timer_path.value
		self.timer_dirname = ConfigSelection(default = default, choices = HDI.alegeriCuStiluri(default, config))
		default = config.usage.instantrec_path.value
		self.instantrec_dirname = ConfigSelection(default = default, choices = HDI.alegeriCuStiluri(default, config))
		default = config.usage.timeshift_path.value
		self.timeshift_dirname = ConfigSelection(default = default, choices = HDI.alegeriTimeshift(default, config))
		self.default_dirname.addNotifier(self.checkReadWriteDir, initial_call=False, immediate_feedback=False)
		self.timer_dirname.addNotifier(self.checkReadWriteDir, initial_call=False, immediate_feedback=False)
		self.instantrec_dirname.addNotifier(self.checkReadWriteDir, initial_call=False, immediate_feedback=False)
		self.timeshift_dirname.addNotifier(self.checkReadWriteDir, initial_call=False, immediate_feedback=False)

		self.list = []
		# acelasi nivel si aceleasi texte ca pagina web (HDI.randuriVazute, HDI.eticheta)
		self.timer_entry = self.instantrec_entry = None
		elemente = {HDI.RAND_IMPLICIT: self.default_dirname, HDI.RAND_TEMPORIZATOR: self.timer_dirname,
			HDI.RAND_IMEDIAT: self.instantrec_dirname, HDI.RAND_TIMESHIFT: self.timeshift_dirname}
		for rand in HDI.randuriVazute(config):
			intrare = getConfigListEntry(HDI.eticheta(rand, config), elemente[rand])
			self.list.append(intrare)
			if rand == HDI.RAND_IMPLICIT:
				self.default_entry = intrare
			elif rand == HDI.RAND_TEMPORIZATOR:
				self.timer_entry = intrare
			elif rand == HDI.RAND_IMEDIAT:
				self.instantrec_entry = intrare
			else:
				self.timeshift_entry = intrare
		self["config"].setList(self.list)

	def ok(self):
		currentry = self["config"].getCurrent()
		self.lastvideodirs = config.movielist.videodirs.value
		self.lasttimeshiftdirs = config.usage.allowed_timeshift_paths.value
		if currentry == self.default_entry:
			self.entrydirname = self.default_dirname
			self.session.openWithCallback(
				self.dirnameSelected,
				MovieLocationBox,
				HDI.titluAlegere(HDI.RAND_IMPLICIT, config),
				preferredPath(self.default_dirname.value)
			)
		elif self.timer_entry is not None and currentry == self.timer_entry:
			self.entrydirname = self.timer_dirname
			self.session.openWithCallback(
				self.dirnameSelected,
				MovieLocationBox,
				HDI.titluAlegere(HDI.RAND_TEMPORIZATOR, config),
				preferredPath(self.timer_dirname.value)
			)
		elif self.instantrec_entry is not None and currentry == self.instantrec_entry:
			self.entrydirname = self.instantrec_dirname
			self.session.openWithCallback(
				self.dirnameSelected,
				MovieLocationBox,
				HDI.titluAlegere(HDI.RAND_IMEDIAT, config),
				preferredPath(self.instantrec_dirname.value)
			)
		elif currentry == self.timeshift_entry:
			self.entrydirname = self.timeshift_dirname
			config.usage.timeshift_path.value = self.timeshift_dirname.value
			self.session.openWithCallback(
				self.dirnameSelected,
				TimeshiftLocationBox
			)

	def dirnameSelected(self, res):
		if res is not None:
			self.entrydirname.value = res
			if config.movielist.videodirs.value != self.lastvideodirs:
				default = self.default_dirname.value
				self.default_dirname.setChoices(HDI.alegeriImplicit(config, default), default=default)
				default = self.timer_dirname.value
				self.timer_dirname.setChoices(HDI.alegeriCuStiluri(default, config), default=default)
				default = self.instantrec_dirname.value
				self.instantrec_dirname.setChoices(HDI.alegeriCuStiluri(default, config), default=default)
				self.entrydirname.value = res
			if config.usage.allowed_timeshift_paths.value != self.lasttimeshiftdirs:
				# era: implicitul luat din instantrec_dirname (greseala veche); acum valoarea de timeshift
				default = self.timeshift_dirname.value
				self.timeshift_dirname.setChoices(HDI.alegeriTimeshift(default, config), default=default)
				self.entrydirname.value = res
			if self.entrydirname.last_value != res:
				self.checkReadWriteDir(self.entrydirname)

	def save(self):
		currentry = self["config"].getCurrent()
		if self.checkReadWriteDir(currentry[1]):
			HDI.salveaza(self.default_dirname.value, self.timer_dirname.value, self.instantrec_dirname.value,
				self.timeshift_dirname.value, config)
			self.close()

	def cancel(self):
		self.close()


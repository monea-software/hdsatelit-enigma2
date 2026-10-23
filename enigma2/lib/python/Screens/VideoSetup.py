# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Video setup for HDSatelit Image: resolution and refresh rate, HDMI color space, color depth and HDR type,
# as offered by the receiver driver, and what the screen shows while the channel changes (zapmode). A new video
# setting must be confirmed; without an answer the previous one comes back, because a TV that does not accept a
# mode stays black.
# The mode is shown as two rows: "Resolution" (2160p, 1080p, ... of the modes the TV accepts, read again when the
# screen opens, plus the saved one) and "Frecventa" (the rates of that resolution, plus "Automat dupa canal" where
# the receiver has the rate files). They are derived from config.av.hds_videomode and "Refresh rate by channel"
# (Components/VideoOutput.py splitMode / joinMode), which stay the only saved values. A confirmed choice is written
# to the settings file at once and applied again at every start. The platform daemon uses a new mode only when a
# video starts, so the playing channel starts again after the mode is written and after it is put back; with
# nothing playing the question says the mode is used when a channel starts. With "Automat dupa canal" a line
# under the list says the TV resynchronizes at every channel with another frame rate. The zapmode row is written
# to the driver at every change; alone it is saved without the question (it cannot leave the TV black). The same for
# the "Imaginea 4:3" row (VideoOutput.policyElement, the driver file policy): it does not change the HDMI format.
# OK saves like Green, so the whole screen works with the arrows and OK. The web page /video (HdsWebControl
# video_web.py) has the same rows and tries a setting the same way (VideoOutput.tryVideo).
# The HDMI colours row (VideoOutput.HdmiColors: YCbCr or RGB) is written only on OK. YCbCr is applied at once, so
# it gets the question too (alone, or together with a new mode); without a "Yes" it is not saved, but the output
# stays YCbCr until the receiver starts again (the driver has no way back). After a "No" (or a refused mode) the
# message of the mode comes alone, then a question offers to start the receiver again now; after the question ran
# out without an answer (the TV may be black) only a message says it. RGB is saved without the question and applied
# at the next start; when the output is YCbCr now, the same question offers to start again now. The messages stay
# MESSAGE_SECONDS, and each one is a box of its own (the message box of the skin has room for two lines at 130 %).
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import NumberActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, configfile, getConfigListEntry, ConfigSelection, NoSave
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components import VideoOutput

CONFIRM_SECONDS = 20
MESSAGE_SECONDS = 10


def confirmText(shown):
	"""the question after a new video setting: shown = the new mode is on screen now (VideoOutput.applyNow)"""
	if shown:
		return _("Is the picture shown correctly?\nWithout an answer the previous setting comes back.")
	return _("The new mode is used when a channel starts. Keep it?\nWithout an answer the previous setting comes back.")


def refusedText():
	return _("The receiver did not accept the new video mode. The previous setting is back.")


def notConfirmedText():
	return _("The new video setting was not confirmed. The previous setting is back.")


def recommendation():
	"""the help line of the "Resolution" and "Frecventa" rows (the same advice as the start wizard)"""
	return _("Recomandat: 1080p 50 Hz (Full HD) sau 2160p 50 Hz (4K UHD); canalele din Europa au 50 Hz.")


def countdownText(seconds):
	"""the last line of the question after a new mode, with the seconds left"""
	return _("Fără răspuns, setarea de dinainte revine în %d s.") % max(0, seconds)


def colorQuestion():
	"""the question after YCbCr was written alone (the HDMI colours row)"""
	return _("Imaginea se vede corect?")


def colorCountdown(seconds):
	"""the last line of colorQuestion: without an answer YCbCr is not saved, but it stays until the next start"""
	return _("Fără răspuns, în %d s setarea nu se păstrează.") % max(0, seconds)


def colorNotKeptText():
	"""after the question of the HDMI colours ran out without an answer: YCbCr stays until the next start"""
	return _("„Ca la calculator” revine la următoarea pornire a receptorului.")


def colorRestartQuestion(kept):
	"""the question to start the receiver again: after a "No" to YCbCr (kept False) or after RGB was saved while the
	output is YCbCr (kept True); only a new start takes the output back to RGB"""
	if kept:
		return _("„Ca la calculator” se aplică numai după o repornire. Repornești receptorul acum?")
	return _("„Ca la calculator” revine numai după o repornire. Repornești receptorul acum?")


def colorLaterText():
	"""YCbCr chosen while the platform daemon or the TV is not ready: the looks of HdmiColors write it when they are"""
	return _("Receptorul sau televizorul nu e gata. „Ca la televizor” se aplică singur când e gata.")


def colorTvText():
	"""YCbCr chosen with a TV that does not declare it: saved, the looks write it when another TV declares it"""
	return _("Televizorul acesta nu primește „Ca la televizor”. Alegerea rămâne salvată.")


class ModeQuestion(MessageBox):
	"""The question after a new mode, with the seconds left in its text: MessageBox writes them in the window title,
	which the HDSatelit skin does not show. The text has its last line from the start, so the window keeps its size
	(MessageBox fits the window to the text when the layout is finished). countdown = the function of that last line
	(countdownText, or colorCountdown for the HDMI colours alone). The skin is the one of MessageBox: the skin
	files have no screen named ModeQuestion, and without a skin the window would be empty (only the timer runs)."""

	countdown = None

	def __init__(self, session, text, *args, **kwargs):
		self.question = text.split("\n")[0]
		self.countdown = kwargs.pop("countdown", None)
		MessageBox.__init__(self, session, self.questionText(kwargs.get("timeout", -1)), *args, **kwargs)
		self.skinName = ["ModeQuestion", "MessageBox"]

	def questionText(self, seconds):
		if seconds is None or seconds < 0:
			return self.question
		return self.question + "\n" + (self.countdown or countdownText)(seconds)

	def timerTick(self):
		MessageBox.timerTick(self)
		if self.timerRunning:
			self["text"].setText(self.questionText(self.timeout))

	def timeoutCallback(self):
		"""the seconds ran out: the answer is None, the default ("no") told apart from a "No". The screen that asked
		cannot read a mark on the window: Screen.doClose empties it before the callback runs."""
		print("[VideoSetup] the question ran out without an answer")
		self.close(None)


def rateWarning():
	"""the line shown when "Refresh rate by channel" is Yes ("Automat dupa canal"), empty otherwise"""
	element = VideoOutput.configElement(VideoOutput.VideoOutput.RATE_ATTR)
	if element is None or not element.value:
		return ""
	return _("At every channel with another refresh rate the TV synchronizes again; on some TVs the picture can disappear for a few seconds or completely.")


def screenModes():
	"""the modes of the "Resolution" and "Frecventa" rows: the list of config.av.hds_videomode (updateModeChoices)"""
	element = VideoOutput.configElement("hds_videomode")
	return list(element.choices) if element is not None else []


class VideoSetup(ConfigListScreen, Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["VideoSetup", "Setup"]
		self.setup_title = _("Video")
		self.onChangedEntry = []
		self.previous = {}
		self.syncing = False
		self.resolution = self.rate = None
		self.rateEntry = self.zapEntry = self.colorEntry = self.policyEntry = None
		self.colorTried = False        # YCbCr written on this OK (the question covers it)
		self.colorText = None          # said when the screen closes (a TV without YCbCr, YCbCr for later)
		self.colorRestart = False      # RGB saved on this OK while the output is YCbCr: the restart question
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))
		self["description"] = Label("")
		actions = {
			"cancel": self.keyCancel,
			"save": self.keySave,
			"ok": self.keySave,
			"left": self.keyLeft,
			"right": self.keyRight,
			# keys of SetupActions without a use here: bound, so the log has no "unknown action"
			"deleteForward": self.keyNothing,
			"deleteBackward": self.keyNothing,
		}
		for digit in "0123456789":
			actions[digit] = self.keyNothing
		self["actions"] = NumberActionMap(["SetupActions"], actions, -2)
		# only the modes the TV accepts (read again now: the TV can be switched on after the receiver started)
		VideoOutput.updateModeChoices()
		# the same for the HDMI colours: a look now, so a TV switched on a moment ago gets YCbCr without waiting
		colors = VideoOutput.colorElement()
		if colors is not None and VideoOutput.hdmiColors() is not None:
			VideoOutput.hdmiColors().resume(colors.value)
		ConfigListScreen.__init__(self, self.buildList(), session=session, on_change=self.changedEntry)
		self["config"].onSelectionChanged.append(self.updateDescription)
		self.onLayoutFinish.append(self.layoutFinished)

	def buildList(self):
		output = VideoOutput.videoOutput
		entries = []
		if output is None:
			return entries
		element = VideoOutput.configElement("hds_videomode")
		if element is not None and output.available("videomode"):
			modes = screenModes()
			group, rate = output.splitMode(modes, element.value, self.byChannel())
			self.resolution = NoSave(ConfigSelection(choices=VideoOutput.resolutionChoices(modes), default=group))
			self.rate = NoSave(ConfigSelection(choices=output.rateRow(modes, group), default=rate))
			self.resolution.addNotifier(self.resolutionChanged, initial_call=False)
			self.rate.addNotifier(self.rateChanged, initial_call=False)
			entries.append(getConfigListEntry(_("Resolution"), self.resolution))
			self.rateEntry = getConfigListEntry(_("Frecvență"), self.rate)
			entries.append(self.rateEntry)
		for name, text in (
				("colorspace", _("HDMI color space")),
				("colordepth", _("Color depth")),
				("hdrtype", _("HDR type"))):
			element = VideoOutput.configElement("hds_" + name)
			if element is not None and output.available(name):
				entries.append(getConfigListEntry(text, element))
		colors = VideoOutput.colorElement()
		if colors is not None:
			self.colorEntry = getConfigListEntry(_("Culorile pe HDMI"), colors)
			entries.append(self.colorEntry)
		policy = VideoOutput.policyElement()
		if policy is not None:
			self.policyEntry = getConfigListEntry(_("Imaginea 4:3"), policy)
			entries.append(self.policyEntry)
		zap = self.zapElement()
		if zap is not None:
			self.zapEntry = getConfigListEntry(_("La schimbarea canalului"), zap)
			entries.append(self.zapEntry)
		return entries

	@staticmethod
	def byChannel():
		element = VideoOutput.configElement(VideoOutput.VideoOutput.RATE_ATTR)
		return element is not None and element.value

	@staticmethod
	def zapElement():
		return VideoOutput.configElement(VideoOutput.ZAP_ATTR)

	def resolutionChanged(self, element):
		"""another resolution: the "Frecventa" row gets its rates (the same rate or "Automat" when it has them)"""
		if self.syncing:
			return
		output = VideoOutput.videoOutput
		modes = screenModes()
		rate = output.rateAfterResolution(modes, element.value, self.rate.value)
		self.syncing = True
		try:
			self.rate.setChoices(output.rateRow(modes, element.value), default=rate)
			self.rate.value = rate
		finally:
			self.syncing = False
		self.storeMode()
		self["config"].invalidate(self.rateEntry)

	def rateChanged(self, element):
		if not self.syncing:
			self.storeMode()

	def storeMode(self):
		"""the two rows into the saved settings (not saved yet): config.av.hds_videomode and "Refresh rate by channel" """
		joined = VideoOutput.videoOutput.joinMode(screenModes(), self.resolution.value, self.rate.value)
		if joined is None:
			return
		mode, byChannel = joined
		VideoOutput.configElement("hds_videomode").value = mode
		element = VideoOutput.configElement(VideoOutput.VideoOutput.RATE_ATTR)
		if element is not None:
			element.value = byChannel

	def showSaved(self):
		"""the two rows again from the settings (after a setting went back)"""
		element = VideoOutput.configElement("hds_videomode")
		if self.resolution is None or element is None:
			return
		output = VideoOutput.videoOutput
		modes = screenModes()
		group, rate = output.splitMode(modes, element.value, self.byChannel())
		self.syncing = True
		try:
			self.resolution.value = group
			self.rate.setChoices(output.rateRow(modes, group), default=rate)
			self.rate.value = rate
		finally:
			self.syncing = False

	def layoutFinished(self):
		title = self.setup_title
		if VideoOutput.videoOutput is not None and VideoOutput.videoOutput.simulation:
			title += " - " + _("simulation, no video driver on this system")
		self.setTitle(title)
		self.updateDescription()

	def updateDescription(self):
		"""under the list: what the zapmode row or the HDMI colours row does when it is the current row, otherwise the
		rate warning; without the warning, the recommended mode on the "Resolution" and "Frecventa" rows"""
		current = self["config"].getCurrent()
		if current is not None and self.zapEntry is not None and current[1] is self.zapEntry[1]:
			self.showDescription(VideoOutput.zapDescription())
			return
		if current is not None and self.policyEntry is not None and current[1] is self.policyEntry[1]:
			self.showDescription(VideoOutput.policyDescription())
			return
		if current is not None and self.colorEntry is not None and current[1] is self.colorEntry[1]:
			colors = VideoOutput.hdmiColors()
			self.showDescription(VideoOutput.colorDescription(colors.tvAccepts() if colors is not None else None))
			return
		text = rateWarning()
		if not text and current is not None and current[1] is not None and current[1] in (self.resolution, self.rate):
			text = recommendation()
		self.showDescription(text)

	def showDescription(self, text):
		"""the help text in the "description" box of the Setup skin (1176x144 in the Clasic theme: 3 whole lines at
		100% and 115%, 2 at 130%, where 38 of the 65 texts in the 13 languages need 3; measured in
		reparatii-tv-0320/iesiri/ajutor-video-masura.txt). Like Screens/Setup.py: a text that does not fit is shown in
		pages that change by themselves every 6 s, with "..." at the end of the pages that go on; one that fits stays
		as it was (lot reparatii-tv-0320)"""
		try:
			from Screens.Setup import Setup
			Setup.arataAjutorul(self, text)
		except Exception as e:
			print("[VideoSetup] the help in pages: %r" % (e,))
			self["description"].setText(text)

	def paginaAjutorUrmatoare(self):
		"""the next page of the help (the timer of Setup.arataAjutorul)"""
		from Screens.Setup import Setup
		Setup.paginaAjutorUrmatoare(self)

	def changedEntry(self):
		self.updateDescription()
		for fnc in self.onChangedEntry:
			fnc()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

	def keyNothing(self, *args):
		pass

	def otherElements(self):
		"""the settings saved with the video mode, without a question of their own: zapmode, the 4:3 picture and the HDMI
		colours"""
		return [element for element in (self.zapElement(), VideoOutput.policyElement(), VideoOutput.colorElement())
			if element is not None]

	def keySave(self):
		output = VideoOutput.videoOutput
		video = VideoOutput.videoChanged()
		colors = VideoOutput.colorElement()
		colorChanged = colors is not None and colors.isChanged()
		if output is None or not (video or any(element.isChanged() for element in self.otherElements())):
			self.close()
			return
		# YCbCr goes to the driver now (the picture changes at once, so it is asked); RGB only at the next start
		self.colorTried = False
		self.colorText = None
		self.colorRestart = False
		hdmi = VideoOutput.hdmiColors()
		if colorChanged and colors.value == VideoOutput.COLOR_YCBCR:
			tried = hdmi.tryNow() if hdmi is not None else VideoOutput.TRY_LATER
			self.colorTried = tried == VideoOutput.TRY_WRITTEN
			if tried == VideoOutput.TRY_TV:
				self.colorText = colorTvText()
			elif tried == VideoOutput.TRY_LATER:
				self.colorText = colorLaterText()
		elif colorChanged:
			# RGB: nothing to start again for when the output is RGB already (a TV without YCbCr, never written)
			self.colorRestart = hdmi is not None and hdmi.ycbcrNow()
		if not video:
			if self.colorTried:
				self.session.openWithCallback(self.confirmed, ModeQuestion, colorQuestion(), MessageBox.TYPE_YESNO,
					timeout=CONFIRM_SECONDS, default=False, countdown=colorCountdown)
				return
			# zapmode (in the driver since the change) and RGB or YCbCr without a new picture: saved without the question
			for element in self.otherElements():
				element.save()
			configfile.save()
			self.closeWith(self.colorText, self.colorRestart)
			return
		# the new values go to the driver and the playing channel starts again, so the new mode is on screen
		# during the question; a mode the driver refused is already back (nothing asked, nothing started again)
		self.previous, shown = VideoOutput.tryVideo(self.session.nav, output)
		if shown is None:
			self.wentBack(refusedText(), self.colorTried)
			return
		self.session.openWithCallback(self.confirmed, ModeQuestion, confirmText(shown),
			MessageBox.TYPE_YESNO, timeout=CONFIRM_SECONDS, default=False)

	def confirmed(self, answer):
		"""the answer to ModeQuestion: True, False ("No") or None (no answer in CONFIRM_SECONDS)"""
		video = VideoOutput.videoChanged()
		timedOut = answer is None
		if answer:
			# on disk at once: the mode is applied again at every start and stays after a zap or a restart
			if video:
				VideoOutput.keepVideo(configfile, self.otherElements())
			else:
				for element in self.otherElements():
					element.save()
				configfile.save()
			self.closeWith(self.colorText, self.colorRestart)
			return
		# every file written (the 50/60/24 Hz files, videomode) goes back to what the driver had, and the channel
		# starts again so the previous mode is on screen at once; YCbCr stays in the driver until the next start
		message = ""
		if video:
			VideoOutput.cancelVideo(self.previous, self.session.nav, True)
			message = notConfirmedText()
		self.wentBack(message, self.colorTried, timedOut)

	def closeWith(self, message, restart=False):
		"""closes the screen: after the restart question when RGB was saved while the output is YCbCr, after a message
		when there is one (a TV without YCbCr, YCbCr for later)"""
		if restart:
			self.askRestart(True, close=True)
			return
		if not message:
			self.close()
			return
		self.session.openWithCallback(lambda *args: self.close(), MessageBox, message, MessageBox.TYPE_INFO,
			timeout=MESSAGE_SECONDS)

	def askRestart(self, kept, close=False):
		"""colorRestartQuestion, "no" first. Yes starts the receiver again (TryQuitMainloop 2: starting only enigma2
		again is not enough, the platform daemon keeps YCbCr; TryQuitMainloop asks first when a recording runs).
		close = the screen closes after a No"""
		def answered(answer=False):
			if answer:
				from Screens.Standby import TryQuitMainloop
				self.session.open(TryQuitMainloop, 2)
			elif close:
				self.close()
		self.session.openWithCallback(answered, MessageBox, colorRestartQuestion(kept), MessageBox.TYPE_YESNO,
			default=False)

	def wentBack(self, message, colorTried=False, timedOut=False):
		"""the saved settings on the rows again, then the message. When YCbCr was written on this OK it stays until the
		receiver starts again: after a "No" or a refused mode the restart question follows the message (a box of its
		own), after a question that ran out only a message says it (the TV may have been black)"""
		for element in self.otherElements():
			element.cancel()
		self.colorTried = False
		self.showSaved()
		for entry in self["config"].list:
			self["config"].invalidate(entry)
		self.updateDescription()
		if not colorTried:
			self.session.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=MESSAGE_SECONDS)
			return
		if timedOut:
			def then(*args):
				self.session.open(MessageBox, colorNotKeptText(), MessageBox.TYPE_INFO, timeout=MESSAGE_SECONDS)
		else:
			def then(*args):
				self.askRestart(False)
		if message:
			self.session.openWithCallback(then, MessageBox, message, MessageBox.TYPE_INFO, timeout=MESSAGE_SECONDS)
		else:
			then()

	def keyCancel(self):
		for element in VideoOutput.videoElements() + self.otherElements():
			element.cancel()
		self.close()

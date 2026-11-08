# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Processing.py: fereastra mica "se lucreaza", cu bara de progres si un rand de text, cum o cer pluginurile altor imagini (navigatorul de retea):
# `from Screens.Processing import Processing`, apoi Processing.instance.showProgress(titlu, progres, endless), setDescription, setProgress,
# hideProgress. O singura fereastra pe sesiune, facuta la prima chemare a lui Processing(session). Cu endless, bara se misca singura pana la
# hideProgress.
from enigma import eTimer
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Screens.Screen import Screen


class ProcessingScreen(Screen):
	skin = """
	<screen name="Processing" position="center,center" size="900,110" zPosition="+99" title="Processing">
		<widget name="progress" position="20,15" size="860,24" />
		<widget name="description" position="20,50" size="860,50" font="Regular;28" halign="center" valign="center" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["Processing"]
		self["progress"] = ProgressBar()
		self["progress"].setRange((0, 100))
		self.description = ""
		self["description"] = Label("")

	def setDescription(self, description):
		self.description = description or ""
		self["description"].setText(self.description)

	def setProgress(self, progress):
		self["progress"].setValue(max(0, min(100, int(progress or 0))))


class Processing(object):
	instance = None

	def __init__(self, session):
		if Processing.instance is not None:
			print("[Processing] exista deja o fereastra; se foloseste aceea")
			return
		Processing.instance = self
		self.processingDialog = session.instantiateDialog(ProcessingScreen)
		self.timer = eTimer()
		self.timer.callback.append(self.updateProgress)
		self.progress = 0

	def showProgress(self, title=None, progress=0, endless=False):
		self.processingDialog.setTitle(title or "")
		self.progress = progress
		self.processingDialog.setProgress(progress)
		self.processingDialog.show()
		if endless:
			self.timer.start(100)

	def updateProgress(self):
		self.progress = (self.progress + 1) % 101
		self.processingDialog.setProgress(self.progress)

	def hideProgress(self):
		self.timer.stop()
		self.processingDialog.hide()

	def setDescription(self, description):
		self.processingDialog.setDescription(description)

	def setProgress(self, progress):
		self.processingDialog.setProgress(progress)

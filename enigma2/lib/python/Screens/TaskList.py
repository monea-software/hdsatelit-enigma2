# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul cere TaskListScreen; lista citeste lucrarile managerului existent.
from Screens.Screen import Screen
from Components.Task import job_manager


class HdsTaskListScreen(Screen):
	skin = """
	<screen name="HdsTaskListScreen" resolution="1920,1080" position="center,center" size="1650,855">
		<widget name="tasklist" position="30,30" size="1590,705" font="Regular;36" itemHeight="60" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,765" size="390,60" font="Regular;36" halign="center" valign="center" backgroundColor="#9f1313" />
		<widget name="key_green" position="450,765" size="390,60" font="Regular;36" halign="center" valign="center" backgroundColor="#1f771f" />
	</screen>"""

	def __init__(self, session, tasklist=None):
		from enigma import eTimer
		from Components.ActionMap import ActionMap
		from Components.Button import Button
		from Components.MenuList import MenuList
		Screen.__init__(self, session)
		self.setTitle(_("Lucrări în fundal"))
		self["tasklist"] = MenuList([])
		self["key_red"] = Button(_("Close"))
		self["key_green"] = Button(_("Info"))
		self["actions"] = ActionMap(["WizardActions", "ColorActions"], {
			"ok": self.keyOK,
			"back": self.close,
			"up": self["tasklist"].up,
			"down": self["tasklist"].down,
			"left": self["tasklist"].pageUp,
			"right": self["tasklist"].pageDown,
			"red": self.close,
			"green": self.keyOK,
		}, -1)
		self._timer = eTimer()
		self._timer.callback.append(self.actualizeaza)
		self.onShow.append(self.porneste)
		self.onHide.append(self.opreste)
		self.onClose.append(self.elibereaza)
		# Argumentul vechi este o fotografie a aceleiasi liste; managerul ramane sursa vie.
		self.actualizeaza()

	def porneste(self):
		self.actualizeaza()
		self._timer.start(1000, False)

	def opreste(self):
		self._timer.stop()

	def elibereaza(self):
		self.opreste()
		if self.actualizeaza in self._timer.callback:
			self._timer.callback.remove(self.actualizeaza)

	def actualizeaza(self, *args):
		lista = self["tasklist"]
		curent = lista.getCurrent()
		ales = curent[1] if curent else None
		index = lista.getSelectionIndex()
		randuri = []
		for job in job_manager.getPendingJobs():
			progres = max(0, min(100, int(100 * job.progress / job.end))) if job.end > 0 else 0
			randuri.append(("%s | %s | %d%%" % (job.name, job.getStatustext(), progres), job))
		lista.setList(randuri or [(_("Lucrări în fundal: %d.") % 0, None)])
		if randuri:
			index = next((n for n, rand in enumerate(randuri) if rand[1] is ales),
				max(0, min(index, len(randuri) - 1)))
			lista.moveToIndex(index)

	def keyOK(self):
		curent = self["tasklist"].getCurrent()
		if curent and curent[1] is not None:
			from Screens.TaskView import JobView
			job_manager.in_background = False
			self.session.openWithCallback(self._dupaDetalii, JobView, curent[1])

	def _dupaDetalii(self, in_background=False):
		job_manager.in_background = bool(in_background)
		self.actualizeaza()


TaskListScreen = HdsTaskListScreen

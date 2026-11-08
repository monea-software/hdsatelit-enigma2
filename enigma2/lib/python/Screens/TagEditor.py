# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul extinde TagEditor si furnizeaza etichetele prin loadTags.
# Ecranul alege etichetele si le intoarce apelantului, fara scriere pe disc.
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.SelectionList import SelectionList
from Components.Sources.StaticText import StaticText

__all__ = ("TagEditor",)


class TagEditor(Screen):
	skin = """
	<screen name="TagEditor" position="center,center" size="600,420">
		<widget name="tags" position="20,20" size="560,320" scrollbarMode="showOnDemand" />
		<widget source="key_red" render="Label" position="20,360" size="250,40" font="Regular;24" />
		<widget source="key_green" render="Label" position="300,360" size="280,40" font="Regular;24" />
	</screen>"""

	def __init__(self, session, tags=None, service=None, parent=None):
		Screen.__init__(self, session)
		self.setTitle(_("Tags"))
		self.tags = list(tags or [])
		self.service = service
		self.parent = parent
		self.allTags = list(dict.fromkeys(list(self.loadTags() or []) + self.tags))
		self["tags"] = SelectionList()
		for index, tag in enumerate(self.allTags):
			self["tags"].addSelection(tag, tag, index, tag in self.tags)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.toggleSelection,
			"cancel": self.cancel,
			"red": self.cancel,
			"green": self.save,
			"up": self["tags"].up,
			"down": self["tags"].down,
			"left": self["tags"].pageUp,
			"right": self["tags"].pageDown,
		}, -1)

	def loadTags(self):
		# Nu este dovedit un catalog local sau un format de fisier pentru etichete.
		return self.tags[:]

	def saveTags(self):
		# Apelantul primeste selectia; nu se presupune o cale de persistenta.
		return None

	def toggleSelection(self):
		if self.allTags:
			self["tags"].toggleSelection()

	def save(self):
		self.tags = [row[1] for row in self["tags"].getSelectionsList()]
		self.saveTags()
		self.close(self.tags[:])

	def cancel(self):
		self.close(None)

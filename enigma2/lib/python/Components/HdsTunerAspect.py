# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Optional classic tuner layout; coordinate drafts never change live settings."""


def initConfig():
	from Components.config import config, ConfigYesNo
	if "hds_tuner_clasic" not in config.usage.content.items:
		config.usage.hds_tuner_clasic = ConfigYesNo(default=False)
	return config.usage.hds_tuner_clasic


def clasic():
	return bool(initConfig().value)


class LocDraft:
	def __init__(self):
		from Components import HdsLocul as L
		from Components.config import ConfigFloat, ConfigSelection, NoSave
		self.initial = L.locul()
		lat, lon = self.initial or (0, 0)
		self.lon = NoSave(ConfigFloat(default=[abs(lon) // 1000, abs(lon) % 1000], limits=[(0, 180), (0, 999)]))
		self.lat = NoSave(ConfigFloat(default=[abs(lat) // 1000, abs(lat) % 1000], limits=[(0, 90), (0, 999)]))
		self.est = NoSave(ConfigSelection([("east", _("Est")), ("west", _("Vest"))], "east" if lon >= 0 else "west"))
		self.nord = NoSave(ConfigSelection([("north", _("Nord")), ("south", _("Sud"))], "north" if lat >= 0 else "south"))
		self.origine = self.valori()

	def valori(self):
		lat = self.lat.value[0] * 1000 + self.lat.value[1]
		lon = self.lon.value[0] * 1000 + self.lon.value[1]
		return (-lat if self.nord.value == "south" else lat, -lon if self.est.value == "west" else lon)

	def schimbat(self):
		return self.valori() != self.origine

	def randuri(self):
		from Components.config import getConfigListEntry
		return [getConfigListEntry(_("Longitudinea (grade)"), self.lon),
			getConfigListEntry(_("Față de Greenwich"), self.est),
			getConfigListEntry(_("Latitudinea (grade)"), self.lat),
			getConfigListEntry(_("Față de ecuator"), self.nord)]

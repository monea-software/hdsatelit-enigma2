# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Ecranele timeshift cer sursa serviciului curent cu un argument pentru ecranul parinte.
from Components.Sources.CurrentService import CurrentService


class PTSCurrentService(CurrentService):
	def __init__(self, navcore, parent):
		self.parent = parent
		CurrentService.__init__(self, navcore)

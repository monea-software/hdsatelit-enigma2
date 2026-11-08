# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile cer ecranele DVD; fara serviciul de redare, ambele arata un refuz explicit (textul deja tradus al imaginii pentru un film
# care nu se poate reda).
from Screens.MessageBox import MessageBox


class HdsDVDIndisponibil(MessageBox):
	def __init__(self, session, dvd_device=None, dvd_filelist=None):
		MessageBox.__init__(self, session,
			_("Filmul nu se poate reda pe acest receptor."),
			type=MessageBox.TYPE_ERROR)


DVDPlayer = HdsDVDIndisponibil
DVDOverlay = HdsDVDIndisponibil

__all__ = ["DVDPlayer", "DVDOverlay"]

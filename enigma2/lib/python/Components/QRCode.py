# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul cere QRCode() fara text; componenta ramane goala pana la o cerinta dovedita.

from Components.GUIComponent import GUIComponent

__all__ = ("QRCode",)


class QRCode(GUIComponent):
	def createWidget(self, parent):
		from enigma import eLabel
		eticheta = eLabel(parent)
		eticheta.setText("")
		return eticheta

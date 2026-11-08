# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# TextBoundary.py: cat loc ia un text scris cu un font, cand latimea e data (marimea data de targetSize). Numele si argumentele sunt cele cerute de
# pluginurile altor imagini (managerul de fisiere, EPG-ul grafic). Se masoara cu o eticheta ascunsa, copil al ferestrei date, care se scoate imediat.
from enigma import eLabel


def getTextBoundarySize(instance, font, targetSize, text):
	eticheta = eLabel(instance)
	try:
		eticheta.hide()
		eticheta.setFont(font)
		eticheta.resize(targetSize)
		eticheta.setText(text)
		return eticheta.calculateSize()
	finally:
		eticheta.hide()

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul cere viteza in octeti pe secunda; aici se formateaza cu unitati Jedec.

_UNITATI = ("B", "KB", "MB", "GB", "TB", "PB", "EB")


class NumberScaler:
	def scale(self, number, style="Jedec", firstScaleIndex=0, maxNumLen=3, decimals=0):
		# Dovezile cer numai Jedec si o valoare initiala exprimata in octeti.
		if style != "Jedec" or firstScaleIndex != 0:
			raise ValueError("Conversia ceruta nu este disponibila")
		valoare = float(number)
		precizie = max(0, int(decimals))
		limita = 10 ** max(1, int(maxNumLen))
		indice = 0
		while abs(valoare) >= limita and indice < len(_UNITATI) - 1:
			valoare /= 1024.0
			indice += 1
		return "%.*f %s" % (precizie, valoare, _UNITATI[indice])

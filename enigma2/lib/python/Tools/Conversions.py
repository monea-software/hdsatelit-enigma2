# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul cere viteza in octeti pe secunda; aici se formateaza cu unitati Jedec.
# Managerul de fisiere FileCommander (scris pentru alte imagini) scrie marimile cu stilurile Si (k, M, G: puteri ale lui
# 1000) si Iec (Ki, Mi, Gi: puteri ale lui 1024): scale(marime, style=None|"Si"|"Iec", maxNumLen=3, decimals=3).
# style=None inseamna Si, iar prima unitate implicita e a doua din tabel (k, Ki), ca la ele; numarul se rotunjeste la
# zecimalele cerute si trece la unitatea urmatoare cat are mai mult de maxNumLen cifre (cel putin 3).

_UNITATI = ("B", "KB", "MB", "GB", "TB", "PB", "EB")

_TABELE = {
	"Si": (("", 1), ("k", 10 ** 3), ("M", 10 ** 6), ("G", 10 ** 9), ("T", 10 ** 12), ("P", 10 ** 15), ("E", 10 ** 18)),
	"Iec": (("", 1), ("Ki", 1024), ("Mi", 1024 ** 2), ("Gi", 1024 ** 3), ("Ti", 1024 ** 4), ("Pi", 1024 ** 5), ("Ei", 1024 ** 6)),
}


class NumberScaler:
	def scale(self, number, style="Jedec", firstScaleIndex=None, maxNumLen=3, decimals=0, suffix="B"):
		if style is None:
			style = "Si"
		tabel = _TABELE.get(style.capitalize()) if isinstance(style, str) else None
		if tabel is not None:
			return self._scaleaza(tabel, number, 1 if firstScaleIndex is None else firstScaleIndex, maxNumLen, decimals, suffix)
		if firstScaleIndex is None:
			firstScaleIndex = 0
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

	@staticmethod
	def _scaleaza(tabel, number, index, maxNumLen, decimals, suffix):
		index = max(0, min(int(index), len(tabel) - 1))
		precizie = max(0, int(decimals))
		limita = 10 ** max(3, int(maxNumLen))
		valoare = float(number)
		negativ = valoare < 0
		valoare = abs(valoare)
		scalat = round(valoare / tabel[index][1], precizie)
		while scalat >= limita and index < len(tabel) - 1:
			index += 1
			scalat = round(valoare / tabel[index][1], precizie)
		if negativ:
			scalat = -scalat
		return "%.*f %s%s" % (precizie, scalat, tabel[index][0], suffix)


def scaleNumber(number, style="Si", suffix="B", format="%.3f"):
	"""Numarul cu unitatea (Si: k, M, G puteri ale lui 1000; Iec: Ki, Mi puteri ale lui 1024; Jedec: K, M puteri ale lui
	1024), cum il cer pluginurile scrise pentru celelalte imagini Enigma2: scaleNumber(1500) = "1.500 kB"."""
	unitati = ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]
	style = (style or "Si").capitalize()
	if style not in ("Si", "Iec", "Jedec"):
		style = "Si"
	if style == "Si":
		unitati[1] = "k"
	negativ = number < 0
	number = -number if negativ else number
	treapta = int((len(str(int(number))) - 1) // 3)
	treapta = min(treapta, len(unitati) - 1)
	valoare = float(number) / (10 ** (treapta * 3) if style == "Si" else 1024 ** treapta)
	if negativ:
		valoare = -valoare
	return "%s %s%s%s" % (format % valoare, unitati[treapta], "i" if style == "Iec" and treapta else "", suffix)

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul cere calea siglei; cautarea si numele raman cele din rendererul imaginii.


class PiconResolver:
	@staticmethod
	def getPngName(sRef, nameCache, findPicon):
		from Components.Renderer.Picon import getPiconName, nume_sigle
		from Tools.Directories import fileExists
		cheie = sRef if isinstance(sRef, str) else sRef.toString() if hasattr(sRef, "toString") else str(sRef)
		png = nameCache.get(cheie, "")
		if png and fileExists(png):
			return png
		nameCache.pop(cheie, None)
		png = getPiconName(cheie)
		# Dosarul ales de plugin se verifica numai prin functia data de el.
		if not png and findPicon is not None:
			for nume in nume_sigle(cheie):
				png = findPicon(nume)
				if png:
					break
		if png:
			nameCache[cheie] = png
		# Lipsa nu se memoreaza: un disc sau o sigla poate aparea mai tarziu.
		return png or ""

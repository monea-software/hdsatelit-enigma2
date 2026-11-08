# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul compara numele subgenului; fara o tabela proprie nu atribuim categorii.


class _Genuri:
	def getGenreLevelTwoText(self, level1, level2, country=None):
		# Imaginea are numai numele genurilor principale, nu subgenuri pe tara.
		return ""


genres = _Genuri()

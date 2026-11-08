# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
from .Label import Label


class RollerCharLCDLong(Label):
	"""Text LCD pe un rand; eLabel deruleaza nativ cand textul nu incape."""

	def applySkin(self, desktop, parent):
		self.skinAttributes = [(n, v) for n, v in (self.skinAttributes or []) if n != "noWrap"]
		self.skinAttributes.append(("noWrap", "1"))
		return Label.applySkin(self, desktop, parent)

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile cer componenta opkg si numele programului; executia ramane cea a imaginii.
from Components.Ipkg import IpkgComponent


class OpkgComponent(IpkgComponent):
	def __init__(self, opkg="opkg"):
		super().__init__(opkg)
		self.opkg = self.ipkg


__all__ = ["OpkgComponent"]

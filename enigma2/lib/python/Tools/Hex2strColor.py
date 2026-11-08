# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Hex2strColor.py: culoarea scrisa in text (\c00rrggbb), numele cerut de pluginuri.


def Hex2strColor(rgb):
	return "\\c%08x" % rgb

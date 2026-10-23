# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Scaling of embedded screen skins for HDSatelit Image.
# An embedded layout is written for LAYOUT_WIDTH pixels and scaled to the
# desktop, so screens that the active skin does not define look right on 720, 1280 and 1920 wide desktops.
import re

from enigma import getDesktop

LAYOUT_WIDTH = 1280
NUMBER_RX = re.compile(r"(?<![#\w])\d+")


def scaleNumbers(template, factor):
	"""positions, sizes and font sizes multiplied by factor; colors (#rrggbb) stay"""
	return NUMBER_RX.sub(lambda m: str(max(1, int(round(int(m.group(0)) * factor)))), template)


def scaledSkin(template, layout_width=LAYOUT_WIDTH):
	"""the template scaled from layout_width to the width of the desktop"""
	try:
		width = getDesktop(0).size().width()
	except Exception:
		width = layout_width
	if width <= 0 or width == layout_width:
		return template
	return scaleNumbers(template, float(width) / layout_width)

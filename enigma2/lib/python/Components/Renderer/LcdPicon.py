# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile cer rendererul pentru ecranul mic si caile siglelor; folosim Picon si aceleasi dosare.
from .Picon import Picon
from Tools.PiconResolver import getPiconPath, resetPiconPath, searchPaths


class LcdPicon(Picon):
	pass


resetLcdPiconPath = resetPiconPath

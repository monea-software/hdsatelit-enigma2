# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.2.6: playerul de fisiere se deschide din meniu, Media > Media player
# (data/menu.xml, entryID media_player), si cu tasta Mplay (Screens/InfoBar.py). Ecranul sta in
# Plugins/Extensions/MediaPlayer/plugin.py: aici numai se numeste, pentru <screen module=...> din menu.xml.
from Plugins.Extensions.MediaPlayer.plugin import MediaPlayer

__all__ = ["MediaPlayer"]

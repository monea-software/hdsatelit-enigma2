# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.2.6: pozele se deschid din meniu, Media > Poze (data/menu.xml, entryID
# hds_poze). Ecranul (picshow) sta in Plugins/Extensions/PicturePlayer/plugin.py: aici numai se numeste, pentru
# <screen module=...> din menu.xml.
from Plugins.Extensions.PicturePlayer.plugin import picshow

__all__ = ["picshow"]

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.3.0.2: setarile descarcarii subtitrarilor (conturile si cheile OpenSubtitles, subs.ro, SubDL) se deschid din meniu,
# langa celelalte intrari ale subtitrarilor (data/menu.xml, entryID hds_descarcare_subtitrari), nu din lista de
# pluginuri. Din 0.3.2 descarcarea face parte din imagine (Components/HdsSubtitrariInternet, inainte pluginul separat
# HdsSubtitleDownloader), deci intrarea se vede mereu. Ecranul sta in Components/HdsSubtitrariInternet/ecrane.py: aici
# numai se numeste, pentru <screen module=...> din menu.xml.
from Components.HdsSubtitrariInternet.ecrane import HdsDescarcareSetari

__all__ = ["HdsDescarcareSetari"]

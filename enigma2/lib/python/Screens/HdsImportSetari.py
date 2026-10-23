# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.2.6: „Import canale și setări” se deschide din meniu, Scanare (data/menu.xml,
# entryID hds_import_setari). <screen module=...> din menu.xml cauta ecranul in Screens, iar ecranul sta in
# Plugins/Extensions/HdsImportSetari/plugin.py: aici numai se numeste, ca in Screens/SkinSelector.py.
from Plugins.Extensions.HdsImportSetari.plugin import HdsImportSetariScreen

__all__ = ["HdsImportSetariScreen"]

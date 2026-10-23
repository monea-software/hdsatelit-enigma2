# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.2.6: panoul skinului HDSatelit se deschide din meniu, Setari > Interfata si aspect
# (data/menu.xml, entryID hds_skin_setari, requires="HdsSkinSetari": intrarea se vede numai cand pachetul
# hdsatelit-skin e pe receptor, Components/SystemInfo.py). Ecranul sta in pachetul skinului
# (Plugins/Extensions/HdsSkinSetari/ecrane.py): aici numai se numeste, pentru <screen module=...> din menu.xml.
from Plugins.Extensions.HdsSkinSetari.ecrane import HdsSkinSetari

__all__ = ["HdsSkinSetari"]

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (pregateste-strat-60.sh il pune peste meta-local). libbluray se construieste pe
# 6.0 numai pentru feed (recipes-local/libbluray, pentru exteplayer3 si ServiceApp); in imagine nu intra. Daca o reteta
# a imaginii ar cere-o, instalarea sistemului se opreste aici (PACKAGE_EXCLUDE), ca inainte, cand reteta era sarita.
PACKAGE_EXCLUDE += "libbluray libbluray2 libbluray3"

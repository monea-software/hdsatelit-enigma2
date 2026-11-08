# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (pregateste-strat-60.sh il pune peste meta-local). libbluray numai pentru FEED:
# o cer exteplayer3 (ServiceApp, fluxurile 5002) si ffmpeg-ext, care stau in feed, nu in imagine. Fara decriptare:
# libaacs si libdvdcss raman scoase (SKIP_RECIPE in conf/distro/hdsatelit.conf) si nu mai sunt cerute aici; libbluray
# le-ar deschide numai la rulare, daca ar exista pe receptor, deci discurile protejate nu se citesc. Imaginea nu o
# primeste: hdsatelit-image.bbappend din acest strat o pune in PACKAGE_EXCLUDE, ca o reteta a imaginii care ar cere-o
# vreodata sa opreasca constructia, nu sa o aduca in tacere.
SKIP_RECIPE[libbluray] = ""
DEPENDS:remove = "libaacs libdvdcss"
RDEPENDS:${PN}:remove = "libaacs libdvdcss"

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Tunerul DVB-C/T2 pe USB VU+ Turbo2 (12.11.2026; dorinelu, forumul 795; Gpiupiu, 801), in feedul modelelor Vu+
# (hdsatelit-drivere-feed). Invelisul OE-A trage driverul producatorului (vuplus-tuner-turbo2, nemodificat) si modulele
# nucleului numai prin RRECOMMENDS; aici aceleasi pachete devin RDEPENDS, ca sa le ia si culegerea feedului (urmeaza numai
# RDEPENDS) si opkg pe orice receptor, chiar cu no_install_recommends. Fara modulele dvb-usb-v2 si cypress-firmware (in
# imagine nu sunt) driverul nu se incarca. Numai pe masinile Vu+ ale noastre, unde e stratul meta-vuplus.
HDS_TURBO_DEP = "kernel-module-dvb-usb kernel-module-dvb-usb-v2 ${DVB_CYPRESS}-cypress-firmware vuplus-tuner-turbo2"
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vuultimo4k = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_TURBO_DEP}"
# fara vuduo4klite (ULT 13.11.2026): vuplus-tuner-turbo/-turbo2 din meta-vuplusde au COMPATIBLE_MACHINE numai vuuno4kse, vuzero4k
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vusolose = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vusolo2 = " ${HDS_TURBO_DEP}"
RDEPENDS:${PN}:append:vuzero = " ${HDS_TURBO_DEP}"

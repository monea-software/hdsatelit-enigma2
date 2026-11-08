# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Receptoarele cu memorie interna mica (suprascrierea hdsflashmic, conf/distro/hdsatelit.conf; Vu+ Solo SE, lotul
# mips-solose, 06.11.2026): reteta meta-python cere python3-pytest la rulare (RDEPENDS:${PN}), iar pytest aduce pygments,
# pluggy, iniconfig, packaging, colorama, unittest si doctest: ~6 MB comprimate in NAND, numai pentru unelte de proba.
# outcome (cerut de trio, cerut de enigma2-hdsatelit) nu importa pytest la rulare: __init__ ia _impl, _util si _version, iar
# _impl numai abc, typing, attr si _util (fisierele din imaginea 0.7.0 V20, 06.11.2026).
# NUMAI pe masinile cu memorie mica; pe celelalte reteta ramane neschimbata.
RDEPENDS:${PN}:remove:hdsflashmic = "python3-pytest"

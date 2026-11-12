# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Reteta meta-python cere python3-pytest la rulare (RDEPENDS:${PN}), iar pytest aduce pygments, pluggy, iniconfig,
# packaging, colorama, unittest si doctest: ~14 MB necomprimat in radacina (pygments 10, _pytest 4), numai pentru unelte
# de proba. outcome (cerut de trio, cerut de enigma2-hdsatelit) nu importa pytest la rulare: __init__ ia _impl, _util si
# _version, iar _impl numai abc, typing, attr si _util (fisierele din imaginea 0.7.0 V20, 06.11.2026). Nimic din codul
# imaginii nu importa pytest sau pygments (cautat in lib/python), iar pygments il cere numai pytest.
# Intai numai pe masinile cu memorie mica (hdsflashmic, Vu+ Solo SE, lotul mips-solose, 06.11.2026; Solo SE 0.7.3 merge
# fara ele). De la 0.7.4 (imaginea mica, 10.11.2026) pe TOATE masinile: radacina SF8008 0.7.3 nu mai incapea in minimul
# masinii (624288 KB), iar fara pytest, pygments, chardet si limbile din feed incape (PROIECT-IMAGINE-MICA.md, P0).
RDEPENDS:${PN}:remove = "python3-pytest"

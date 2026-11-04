# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (pregateste-strat-60.sh il pune langa enigma2-hdsatelit.bb). Codul imaginii
# importa modulul html (27 de fisiere: html.escape in paginile web, HdsWebControl ...) si py_compile; in 0.6.0 (5.6)
# ele veneau intamplator, prin python3-setuptools, cerut de python3-cffi (python3-cryptography). In 6.0 python3-cffi
# nu mai cere setuptools, iar imaginea 0.7.0 iesea fara /usr/lib/python3.14/html si py_compile (comparatia rootfs-ului
# cu 0.6.0, 02.11.2026). Aici devin dependente cerute pe fata. Pe 5.6 reteta ramane neschimbata (aceleasi semnaturi).
RDEPENDS:${PN}:append = " python3-html python3-compile"

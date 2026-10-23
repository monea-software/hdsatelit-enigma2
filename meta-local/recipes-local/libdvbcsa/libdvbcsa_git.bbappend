# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# libdvbcsa (algoritmul comun de cifrare DVB, CSA) in imagine: biblioteca pe care o va folosi programul care descifreaza
# mai tarziu inregistrarile. Programul nu e in acest strat (nimic nu pune /usr/bin/hds-decodare).
# Reteta din meta-oe-alliance (libdvbcsa_git.bb, prioritatea 7, castiga fata de libdvbcsa_1.1.0.bb din meta-multimedia)
# ia varful ramurii master din github.com/oe-mirrors/libdvbcsa (AUTOREV). Aici sursa se fixeaza la comiterea citita
# (b84e790a, AC_INIT 1.1.0), ca imaginea sa aiba exact ce s-a verificat: licenta din COPYING (GPL 2, aceeasi suma ca
# LIC_FILES_CHKSUM) si antetele din src/ ("version 2 of the License, or (at your option) any later version"), adica
# GPL-2.0-or-later, cum scrie si reteta. Pe procesorul receptorului reteta construieste varianta NEON.

SRCREV = "b84e790a9473d09c3c25d3f8d657abe8469f8837"

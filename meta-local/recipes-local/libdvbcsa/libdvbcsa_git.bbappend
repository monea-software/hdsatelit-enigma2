# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# libdvbcsa (algoritmul comun de cifrare DVB, CSA) in imagine: biblioteca pe care o incarca motorul SoftCSA din enigma2
# (lib/dvb/csaengine.cpp, dlopen libdvbcsa.so.1) si pe care o va folosi programul care descifreaza mai tarziu inregistrarile.
# Reteta din meta-oe-alliance (libdvbcsa_git.bb, prioritatea 7, castiga fata de libdvbcsa_1.1.0.bb din meta-multimedia)
# ia varful ramurii master din github.com/oe-mirrors/libdvbcsa (AUTOREV). Aici sursa se fixeaza la comiterea citita, ca
# imaginea sa aiba exact ce s-a verificat: licenta din COPYING (GPL 2, aceeasi suma ca LIC_FILES_CHKSUM) si antetele din src/
# ("version 2 of the License, or (at your option) any later version"), adica GPL-2.0-or-later, cum scrie si reteta.
# Pe procesorul receptorului reteta construieste varianta NEON (ARM) sau uint32 (mips).
#
# 16.11.2026 (RTN, paznicul SoftCSA): de la b84e790a (22.02.2026, 1.1.0) la 6c459854 (15.11.2026, AC_INIT 1.2.0), cu
# reparatiile autorilor: e82c638 (depasirea cu semn in cheia pe 32 de biti, varianta mips; din VideoLAN c1570c7), 79d8f4b
# (pachetele mai lungi decat maxlen nu mai scriu peste locul lor din lot), prefetch la incarcarea lotului, codul fluxului
# unificat (6353b80); restul (AVX2/AVX-512/SSE, NEON ghicit pe aarch64, fisierul .pc, lucrarea GitHub din 6c459854) nu
# schimba ce se construieste aici. Soname-ul ramane libdvbcsa.so.1, antetul public dvbcsa.h neschimbat. Proba: aceiasi
# octeti ca 1.1.0 pe ARM NEON si mips uint32 (ecm 0 si ecm 4), testele autorului trec (si testicam, vectorii iCAM din
# FFdecsa); pe Octagon SF8008 descifrarea e cu ~2% mai lenta (prefetch-ul din 4ef289a sau 79d8f4b; ~91.000 de pachete/s,
# ~137 Mbit/s pe un nucleu).
# PV/PKGV ca in reteta OE-A, cu versiunea din configure.ac (1.2.0): pachetul se numeste dupa ce contine.

SRCREV = "6c459854e737f3149666b3f842fbbe6eca9551eb"
PV = "1.2.0+git"
PKGV = "1.2.0+git${GITPKGV}"

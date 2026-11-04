# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# glibc 2.42 la comiterea 8a2ca6bb41fa de pe ramura release/2.42/master (SRCREV_glibc din conf/distro/hdsatelit.conf;
# in openembedded-core era e34453cd6a8c, cu 81 de comiteri in urma). Versiunea ramane 2.42+git, deci verificarea
# CVE a OE (dupa versiune) le-ar socoti in continuare nereparate: aici, ca in reteta OE, lista celor reparate pe
# ramura, fiecare cu comiterea ei (toate verificate in jurnalul ramurii, intre e34453cd6a8c si 8a2ca6bb41fa):
#   CVE-2026-5450   4ebd33dd scanf %mc (BZ 34008)
#   CVE-2026-5928   b4bca35a ungetwc pe un flux de octeti (BZ 33998)
#   CVE-2026-4046   f13c1bb0 iconv IBM1390, IBM1399
#   CVE-2026-4437   8e863fb1 rezolvarea DNS: numararea inregistrarilor (gethostbyaddr)
#   CVE-2026-4438   42637854 rezolvarea DNS: numele gazdei verificat
#   CVE-2026-0915   453e6b8d getnetbyaddr prin DNS
#   CVE-2026-0861   b0ec8fb6 memalign, aliniere prea mare
#   CVE-2025-15281  cbf39c26 wordexp cu WRDE_REUSE
#   CVE-2026-6368   8be3551c wordexp cu WRDE_APPEND
#   CVE-2026-6791   7414631f wordexp, expandarea ~
#   CVE-2026-5435   299e1d25 ns_sprintrrf
#   CVE-2026-6238   cb4c6244 ns_sprintrrf
#   CVE-2026-19499  6ad255db strfmon
#   CVE-2026-77117  67db60ee iconv SHIFT_JISX0213
#   CVE-2026-80489  87c2795c iconv EUC_JISX0213
#   CVE-2026-18374  2ba6f4c0 fopen cu ccs=
#   CVE-2026-8674   c0c8a45d rezolvarea DNS: lista de cautare trunchiata
#   CVE-2026-89092  9ff7ecb4 nscd (nu e in imagine)
# Peticele openembedded-core si meta-oe-alliance se aplica pe 8a2ca6bb cu fuzz 0 (verificat).

CVE_STATUS_STABLE_BACKPORTS += "CVE-2026-5450 CVE-2026-5928 CVE-2026-4046 CVE-2026-4437 CVE-2026-4438 CVE-2026-0915 \
    CVE-2026-0861 CVE-2025-15281 CVE-2026-6368 CVE-2026-6791 CVE-2026-5435 CVE-2026-6238 CVE-2026-19499 CVE-2026-77117 \
    CVE-2026-80489 CVE-2026-18374 CVE-2026-8674 CVE-2026-89092"

# lista de mai sus e adevarata numai cu comiterea din hdsatelit.conf: altfel constructia se opreste
python () {
    if d.getVar('SRCREV_glibc') != '8a2ca6bb41fa07701f92e56d3d508e4dbbecc733':
        bb.fatal('glibc: SRCREV_glibc nu e 8a2ca6bb41fa (conf/distro/hdsatelit.conf); lista CVE din bbappend nu mai e buna')
}

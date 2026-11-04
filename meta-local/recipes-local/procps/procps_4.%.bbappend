# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# NUMAI pentru stratul OE-Alliance 6.0 (langa procps_%.bbappend al nostru, cel cu kernel.sysrq = 0). In 6.0
# meta-oe-alliance pune in /etc/sysctl.conf doua randuri IPv6 (net.ipv6.conf.all/default.use_tempaddr = 2). Imaginea
# noastra porneste cu IPv6 oprit din fabrica, iar setarile IPv6 le face numai hds-ipv6 cand utilizatorul il porneste
# (verifica-rootfs: nimic din sysctl nu schimba IPv6). Aici cele doua randuri si comentariul lor ies; constructia se
# opreste daca nu erau exact doua sau daca mai ramane vreun rand net.ipv6.
do_install:append() {
	f=${D}${sysconfdir}/sysctl.conf
	n=$(grep -c '^net\.ipv6\.conf\.[a-z]*\.use_tempaddr' "$f" || true)
	[ "$n" = 2 ] || bbfatal "procps: astept doua randuri use_tempaddr in sysctl.conf, sunt $n"
	sed -i -e '/^# Prefer temporary IPv6 addresses/d' -e '/^net\.ipv6\.conf\.[a-z]*\.use_tempaddr/d' "$f"
	if grep -q '^[[:space:]]*net\.ipv6' "$f"; then
		bbfatal "procps: sysctl.conf schimba inca IPv6"
	fi
}

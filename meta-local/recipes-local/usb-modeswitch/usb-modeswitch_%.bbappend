# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# usb-modeswitch fara tcl (0.7.4, agentul WD2, 12.11.2026). Reteta din meta-oe cere tcl (~3,5 MB instalat) numai pentru
# dispecerul ei (usb_modeswitch_dispatcher, scris in Tcl, chemat de regulile din usb-modeswitch-data). Imaginea nu-l
# foloseste: stickurile Wi-Fi Realtek care pornesc ca CD (0bda:1a2b, „ZeroCD”) sunt comutate de regula udev a imaginii
# (40-realtek-zerocd.rules din udev-extraconf), care cheama direct programul C /usr/sbin/usb_modeswitch -KW. usb-modeswitch
# intra in imagine odata cu rtl88x2bu (RTL8812BU/8822BU: TP-Link Archer T3U, T3U Plus, T4U v3; reteta lui il cere), deci fara
# acest rand tcl ar ocupa in imagine mai mult decat driverul. Modemurile 3G/4G pe USB, care au nevoie de dispecer, nu sunt
# tinta imaginii; cine il vrea instaleaza tcl din feed si dispecerul merge la fel. Pachetul din feed are aceeasi lista.
RDEPENDS:${PN}:remove = "tcl"
# Constructia comuna 0.7.4 (CB074, 12.11.2026): fara tcl, verificarea QA file-rdeps oprea pachetul (dispecerul cere /usr/bin/tclsh,
# „no providers found in RDEPENDS”) si deci imaginea pe orice masina cu rtl88x2bu. Dispecerul ramane in pachet, asa cum spune mai sus
# (merge daca omul instaleaza tcl din feed); verificarea se iarta numai pentru dependenta aceea de fisier.
INSANE_SKIP:${PN} += "file-rdeps"

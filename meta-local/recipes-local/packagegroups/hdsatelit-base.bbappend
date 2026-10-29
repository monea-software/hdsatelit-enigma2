# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): nucleul lui (linux-octagon 4.4.35, defconfig sf8008 din
# meta-octagon) are CONFIG_TUN=y, adica driverul tun e in nucleu, nu modul; pachetul kernel-module-tun nu se face pe
# aceasta masina, iar cererea din hdsatelit-base.bb ar opri constructia imaginii. /dev/net/tun exista oricum, deci
# OpenVPN merge la fel ca pe V20 (unde tun e modul). Numai pe sf8008: pe celelalte masini lista ramane neschimbata,
# iar hdsatelit-base.bb nu se atinge (verificarile lui fata de 0.5.0 raman aceleasi).
RDEPENDS:${PN}:remove:sf8008 = "kernel-module-tun"
#
# Octagon SF8008: load-ul producatorului incarca rtk_8822cbtusb.ko pe orice placa sf8008, iar placile cu cipul 8822C
# (Supreme, V3 Supreme) ii cer firmware-ul; imaginile facute pentru masina il au in /lib/firmware (rtl8822cu_fw si
# rtl8822cu_config, reteta OE-Alliance firmware-rtk8822cbtusb). Numai pe sf8008 (MINI nu are cipul).
RDEPENDS:${PN}:append:sf8008 = " firmware-rtk8822cbtusb"
#
# Octagon SF8008 si SF8008 MINI: Wi-Fi USB ca in imaginile facute pentru aceste masini (OE-Alliance,
# recipes-oe-alliance/image/oe-alliance-wifi.bb pune pe sf8008 si sf8008m enigma2-plugin-drivers-network-usb-rtl8821cu,
# -rtl8192eu, -mt7601u, -rtl8822cu si -rtl8188fu). Aici direct pachetele pe care le recomanda acestea (driverul si
# firmware-ul), fiindca o recomandare nu e o dependinta: rt8821cu + linux-firmware-8821cu, rtl8192eu + firmware-rtl8192eu,
# kernel-module-mt7601u (modulul din nucleu, CONFIG_MT7601U=m) + firmware-mt7601u, rt8822cu + firmware-rtk8822cbtusb;
# rt8188fu si firmware-rt8188fu sunt deja in hdsatelit-base.bb. Fara Bluetooth (rtk-btusb nu se recomanda pe sf8008).
HDS_WIFI_OCTAGON = "rt8821cu linux-firmware-8821cu rtl8192eu firmware-rtl8192eu kernel-module-mt7601u firmware-mt7601u rt8822cu"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_OCTAGON}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"

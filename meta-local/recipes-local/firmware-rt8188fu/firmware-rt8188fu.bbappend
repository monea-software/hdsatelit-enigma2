# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# firmware-rt8188fu cu nota de licenta Realtek.
#
# Reteta OE-Alliance scrie LICENSE = "CLOSED" si pune in imagine numai rtlwifi/rtl8188fufw.bin. Fisierul e acelasi,
# octet cu octet, cu cel din linux-firmware (md5 62e540665cf25e682864c1ef67b893ba), unde e dat sub
# LICENCE.rtlwifi_firmware.txt: redistribuirea in forma binara, nemodificata, e permisa daca nota de copyright si
# declinarea raspunderii Realtek insotesc distribuirea. Textul (din linux-firmware, md5
# 00d06cfd3eddd5a2698948ead2ad54a5) sta in files/, langa aceasta reteta; prin LIC_FILES_CHKSUM ajunge in dosarul
# licentelor construirii, deci si in lista licentelor din imagine (clasa hds-licente). Numele licentei e cel din
# reteta linux-firmware din openembedded-core; textul ei nu e in licentele comune, de aici NO_GENERIC_LICENSE.
# PR cu ".hds1", ca pachetul cu licenta schimbata sa se vada in manifest si in "opkg list-installed".

LICENSE = "Firmware-rtlwifi_firmware"
NO_GENERIC_LICENSE[Firmware-rtlwifi_firmware] = "LICENCE.rtlwifi_firmware.txt"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://LICENCE.rtlwifi_firmware.txt"
LIC_FILES_CHKSUM = "file://LICENCE.rtlwifi_firmware.txt;md5=00d06cfd3eddd5a2698948ead2ad54a5"

PR:append = ".hds1"

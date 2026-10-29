# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Licenta firmware-ului rtl8821cu_fw/_config (adaptoarele USB RTL8821CU pe Octagon), in locul lui "CLOSED": sursa git a
# retetei are in radacina LICENCE.rtlwifi_firmware.txt (acelasi text ca linux-firmware si firmware-rt8188fu).
LICENSE = "Firmware-rtlwifi_firmware"
NO_GENERIC_LICENSE[Firmware-rtlwifi_firmware] = "LICENCE.rtlwifi_firmware.txt"
LIC_FILES_CHKSUM = "file://LICENCE.rtlwifi_firmware.txt;md5=00d06cfd3eddd5a2698948ead2ad54a5"

PR:append = ".hds1"

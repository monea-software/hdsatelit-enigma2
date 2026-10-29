# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Licenta firmware-ului rtl8822cu_fw/_config (cipul Realtek 8822C: placile SF8008 Supreme si adaptoarele USB
# RTL8822CU), in locul lui "CLOSED": firmware-ul Realtek din linux-firmware e sub LICENCE.rtlwifi_firmware.txt (acelasi
# text ca la firmware-rt8188fu), in files/.
LICENSE = "Firmware-rtlwifi_firmware"
NO_GENERIC_LICENSE[Firmware-rtlwifi_firmware] = "LICENCE.rtlwifi_firmware.txt"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://LICENCE.rtlwifi_firmware.txt"
LIC_FILES_CHKSUM = "file://LICENCE.rtlwifi_firmware.txt;md5=00d06cfd3eddd5a2698948ead2ad54a5"

PR:append = ".hds1"

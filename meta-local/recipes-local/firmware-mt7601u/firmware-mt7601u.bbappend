# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Licenta firmware-ului mt7601u.bin (Wi-Fi USB MT7601U pe Octagon; acelasi fisier, octet cu octet, ca in linux-firmware,
# al carui WHENCE il da sub LICENCE.ralink_a_mediatek_company_firmware), in locul lui "CLOSED": textul din linux-firmware
# (LICENSES/), in files/.
LICENSE = "Firmware-ralink_a_mediatek_company_firmware"
NO_GENERIC_LICENSE[Firmware-ralink_a_mediatek_company_firmware] = "LICENCE.ralink_a_mediatek_company_firmware"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://LICENCE.ralink_a_mediatek_company_firmware"
LIC_FILES_CHKSUM = "file://LICENCE.ralink_a_mediatek_company_firmware;md5=728f1a85fd53fd67fa8d7afb080bc435"

PR:append = ".hds1"

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Licenta firmware-ului rtlwifi/rtl8192eu_nic.bin (Wi-Fi USB pe Octagon, din linux-firmware: WHENCE il da sub
# LICENCE.rtlwifi_firmware.txt, care e in radacina sursei git a retetei), in locul lui "CLOSED", ca in lista licentelor
# imaginii sa fie textul ei; acelasi text ca la firmware-rt8188fu.
LICENSE = "Firmware-rtlwifi_firmware"
NO_GENERIC_LICENSE[Firmware-rtlwifi_firmware] = "LICENCE.rtlwifi_firmware.txt"
LIC_FILES_CHKSUM = "file://LICENCE.rtlwifi_firmware.txt;md5=00d06cfd3eddd5a2698948ead2ad54a5"

PR:append = ".hds1"

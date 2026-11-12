# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# firmware-rtl8188eu cu nota de licenta Realtek (11.11.2026, agentul WD), ca firmware-rt8188fu.
#
# De ce reteta asta si nu linux-firmware-rtl8188: modulul r8188eu (stickurile RTL8188EUS, 0bda:8179) cere
# rtlwifi/rtl8188eufw.bin; linux-firmware-rtl8188 il are, dar pune si rtlwifi/rtl8188fufw.bin, pe care il pune deja
# firmware-rt8188fu (doua pachete cu acelasi fisier: opkg refuza al doilea). Reteta sursei scrie LICENSE = "CLOSED" si pune
# numai rtlwifi/rtl8188eufw.bin; fisierul e dat in linux-firmware sub LICENCE.rtlwifi_firmware.txt (redistribuirea in forma
# binara, nemodificata, cu nota Realtek). Textul sta in files/ (aceeasi copie ca la firmware-rt8188fu). Pachetul sta in
# feed (hdsatelit-drivere-feed, Vu+ Solo SE), nu in imagine.
LICENSE = "Firmware-rtlwifi_firmware"
NO_GENERIC_LICENSE[Firmware-rtlwifi_firmware] = "LICENCE.rtlwifi_firmware.txt"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://LICENCE.rtlwifi_firmware.txt"
LIC_FILES_CHKSUM = "file://LICENCE.rtlwifi_firmware.txt;md5=00d06cfd3eddd5a2698948ead2ad54a5"

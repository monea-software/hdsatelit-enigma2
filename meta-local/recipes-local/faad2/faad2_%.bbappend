# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: MIT
#
# faad2 (0.7.4): biblioteca de decodare AAC (GPL-2.0-only, meta-oe) intr-un pachet al ei, libfaad2 (libfaad.so.2, ~0,27 MB
# pe ARM), separat de libfaad_drm (Digital Radio Mondiale, ~0,26 MB) si de programul faad, pe care nu le foloseste nimeni
# din imagine. De ce: releul DAB+ din satelit decodeaza AAC-ul DAB+ (cadre de 960, HE-AAC v1/v2) cu libfaad.so.2 pe placile
# care nu-l stiu (Broadcom/Vu+), prin lib/python/Hds/DabT2/sunet_software.py (ctypes). Pachetul faad2 ramane (programul,
# care trage libfaad2), iar gstreamer1.0-plugins-bad-faad isi ia dependinta singur dupa soname.
# PR nou: pachetul faad2 vechi (r0, cu bibliotecile in el) se inlocuieste la actualizare; libfaad2 preia fisierul lui
PR:append = ".hds1"
PACKAGES =+ "libfaad2 libfaad-drm2"
RREPLACES:libfaad2 = "faad2 (< 2.11.4-r0.hds1)"
RREPLACES:libfaad-drm2 = "faad2 (< 2.11.4-r0.hds1)"
RBREAKS:libfaad2 = "faad2 (< 2.11.4-r0.hds1)"
RBREAKS:libfaad-drm2 = "faad2 (< 2.11.4-r0.hds1)"
FILES:libfaad2 = "${libdir}/libfaad.so.*"
FILES:libfaad-drm2 = "${libdir}/libfaad_drm.so.*"
SUMMARY:libfaad2 = "AAC decoding library (libfaad.so.2)"
SUMMARY:libfaad-drm2 = "AAC decoding library with DRM support (libfaad_drm.so.2)"

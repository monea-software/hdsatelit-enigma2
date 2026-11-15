# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# 0.7.5 (MA8, 15.11.2026; TODO 05.11 14:43): pluginul faad (decodorul AAC prin libfaad2, gst-plugins-bad ext/faad) pentru
# egalizatorul imaginii, care decodeaza in procesor posturile AAC (lib/service/hdsegalizator.cpp, elementul "faad").
# Optiunea "faad" exista in reteta din openembedded-core (PACKAGECONFIG[faad] = "-Dfaad=enabled,-Dfaad=disabled,faad2"; faad e
# in GSTREAMER_GPL, deci reteta pune singura -Dgpl=enabled). faad2 are LICENSE_FLAGS commercial, primit deja in hdsatelit.conf
# (LICENSE_FLAGS_ACCEPTED). Se face numai subpachetul gstreamer1.0-plugins-bad-faad; il cere hdsatelit-base numai pe masinile
# care au deja libfaad2 (packagegroups/hdsatelit-base.bbappend). Umbrela plugins-bad nu intra in imagine.
# Fara PR nou: celelalte pachete plugins-bad raman aceleasi; pachetul nou il aduce hdsatelit-base (PR-ul lui urca).
PACKAGECONFIG:append = " faad"

# paza: daca un strat de mai sus scoate optiunea, constructia se opreste aici, nu la receptor
do_install:append() {
	[ -f ${D}${libdir}/gstreamer-1.0/libgstfaad.so ] || bbfatal "gstreamer1.0-plugins-bad: pluginul faad nu s-a construit (PACKAGECONFIG faad)"
}

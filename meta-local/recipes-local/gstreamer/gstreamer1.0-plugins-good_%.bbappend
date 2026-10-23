# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Pluginul soup (souphttpsrc: IPTV si radio prin HTTP) trece de pe libsoup-2.4 (neintretinut, cu gauri nereparate) pe
# libsoup 3 (recipes-local/libsoup/libsoup_3.8.0.bb), iar libsoup-2.4 iese din imagine.
# In gstreamer 1.28 pluginul nu se leaga de libsoup la construire: gstsouploader.c deschide la rulare
# libsoup-3.0.so.0 sau libsoup-2.4.so.1, intai pe cel deja incarcat in proces, altfel il prefera pe 3. Schimbarea e
# deci numai de pachete:
# - bbappend-ul meta-oe-alliance scoate soup3 si pune soup2 (DEPENDS libsoup-2.4); aici scoatem si soup2. -Dsoup=enabled
#   ramane din bbappend-ul meta-oe-alliance (EXTRA_OEMESON), deci pluginul se construieste in continuare;
# - fara soup2 in PACKAGECONFIG, reteta din openembedded-core pune singura RDEPENDS:${PN}-soup = libsoup (3); aici
#   scoatem libsoup-2.4 pus de bbappend-ul meta-oe-alliance.
# PR:append schimba versiunea pachetelor (alte dependinte la aceeasi versiune), ca opkg sa le ia din feed.
PR:append = ".hds1"

PACKAGECONFIG:remove = "soup2"
RDEPENDS:${PN}-soup:remove = "libsoup-2.4"
# libsoup (3) in DEPENDS numai pentru ordinea constructiei si pentru proba QA build-deps (pachetul -soup il cere la
# rulare); pluginul nu se leaga de el
DEPENDS += "libsoup"

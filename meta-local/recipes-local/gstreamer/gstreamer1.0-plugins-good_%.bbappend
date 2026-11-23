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
# .hds2 (13.11.2026, asistenta 743444, Vu+ Solo SE 0.7.4): pe Solo SE niciun flux http/https nu pornea („missing_codec =
# http”): bbappend-ul OE-Alliance scoate libsoup prin :remove, deci -soup nu mai cerea libsoup, iar pe Solo SE navigatorul
# (care o aducea) nu e in imagine. Acum -soup cere ferm libsoup si glib-networking (TLS pentru https, prin GIO; libsoup
# numai o recomanda). Versiunea noua a lui -soup intra singura in „Actualizare” (e instalat pe toate receptoarele), iar
# opkg aduce odata cu ea libsoup, glib-networking si bibliotecile lor din feed.
PR:append = ".hds3"

# Per-playback headers reach detached HLS sources and adaptive2 HTTP downloads.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append = " file://0003-http-antete-pe-toate-cererile.patch"

PACKAGECONFIG:remove = "soup2"
RDEPENDS:${PN}-soup:remove = "libsoup-2.4"
# libsoup (3) si glib-networking in DEPENDS numai pentru ordinea constructiei si pentru proba QA build-deps (pachetul
# -soup le cere la rulare); pluginul nu se leaga de ele
DEPENDS += "libsoup glib-networking"

# Un :append nu poate aduce inapoi ce scoate un :remove; setVar in functia anonima fixeaza valoarea finala (setVar in
# afara citirii sterge operatiile :append/:remove ramase pe variabila), dupa ce s-au aplicat toate.
python __anonymous() {
    cheie = d.expand("RDEPENDS:${PN}-soup")
    dependinte = (d.getVar(cheie) or "").split()
    prefix = d.getVar("MLPREFIX") or ""
    for nume in ("libsoup", "glib-networking"):
        if prefix + nume not in dependinte:
            dependinte.append(prefix + nume)
    d.setVar(cheie, " ".join(dependinte))
}

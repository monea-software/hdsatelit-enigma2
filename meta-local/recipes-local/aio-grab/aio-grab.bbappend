# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# aio-grab (programul grab, capturile de ecran) fara numele altei interfete web si al altei echipe in ce ajunge in
# imagine (regula: nimic din ce iese nu poarta numele altor imagini, interfete, pluginuri sau skinuri; notitele de
# licenta si de autor raman).
#
# Mesajul de eroare al capturii prin ffmpeg (main.c, de doua ori: "could not determine current service input from
# local WebInterface/<numele altei interfete web>") spune "from the local web interface": acelasi inteles, fara nume.
# Se schimba in sursa inainte de compilare (do_configure:prepend), nu printr-un petic: un petic ar purta numele in
# randurile scoase, iar stratul si retetele ies cu oferta de sursa (clasa hds-surse). Comentariile din main.c nu
# intra in binar si raman neatinse. main.c primeste nota GPL-2.0 par. 2a (fisier schimbat), ca in codul imaginii.
#
# MAINTAINER: reteta din care vine pachetul pune numele echipei ei in campul Maintainer din metadatele pachetului
# (control in /var/lib/opkg/info, Packages din feed). Campul spune cine intretine pachetul in distributie; nu e o
# notita de copyright sau de licenta. Ce cere GPL-2.0 ramane: antetul lui main.c, cu autorul codului, si fisierul
# LICENSE, in sursa (oferta de sursa) si in lista licentelor din imagine. Valoarea e cea a distributiei (MAINTAINER din
# conf/distro/hdsatelit.conf), ca la toate retetele fara MAINTAINER propriu.
#
# Sursa vine de pe ramura master (AUTOREV), deci textul se poate schimba: hds_fara_nume (clasa hds-fara-nume) opreste
# construirea daca programul instalat mai poarta un nume.
# PR ".hds1": alt continut si alte metadate la aceeasi versiune, ca opkg sa ia pachetul din feed.
# PR ".hds2" (0.7.5): peticul grab-ecran-mai-mare-decat-hd.patch, mai jos.
MAINTAINER = "Monea Software pentru HD Satelit"
PR:append = ".hds2"

# 0.7.5 (13.11.2026): grab cadea (Segmentation fault) cand interfata e mai mare decat 1920x1080 pe o placa fara e2egl:
# tema la 2560x1440 pe HiSilicon, cu hi_fb peticit (clasa hisi-hifb-wqhd). Memoria capturii era fixa pentru 1920x1080
# puncte, iar getosd() copia tot ecranul (14,7 MB in 8,3 MB). Peticul socoteste memoria si din ecranul de acum (fb0, cel
# mult 3840x2160) si refuza curat un ecran mai mare decat ea. Fara el, la 2K nu merg captura din interfata web si
# capturile din rapoartele beta testerilor si din asistenta. Peticul e scris pe comiterea fixata mai jos (aea30841).
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append = " file://grab-ecran-mai-mare-decat-hd.patch"

# Sursa fixata la comiterea din imaginea 0.6.0 (pachetul aio-grab 2.0+git135+aea30840 din manifestul ei; lotul
# imagine-060-v10): reteta OE-Alliance ia ultima comitere de pe master (AUTOREV), iar dupa 24.10.2026 master a primit
# comiteri noi (capturile altor receptoare), asa ca o constructie noua ar fi pus alt program grab decat cel din imaginea
# lansata. Fixata, orice imagine noua pe stratul 0.6.0 (V20, V30, V40, V10) are acelasi grab ca 0.6.0.
# Cu ":pn-aio-grab", ca la dvbmediasink: distributia pune SRCREV:pn-aio-grab ?= AUTOREV (unstable-versions.inc), iar
# varianta cu override castiga in fata unui SRCREV simplu (probat: cu SRCREV simplu a iesit tot git137).
SRCREV:pn-aio-grab = "aea30841a8a15f534c57bb8474f2f26cd8cf48c8"

inherit hds-fara-nume

do_configure:prepend() {
	grep -q 'Modificat de moneasoftware.com si hdsatelit.com' ${S}/main.c \
		|| sed -i '1i /* Modificat de moneasoftware.com si hdsatelit.com, 2026 (textul unui mesaj de eroare) */' ${S}/main.c
	sed -i 's|from local WebInterface/[[:alnum:]]*\\n"|from the local web interface\\n"|' ${S}/main.c
}

do_install:append() {
	hds_fara_nume ${D}${bindir}/grab
}

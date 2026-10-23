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
MAINTAINER = "Monea Software pentru HD Satelit"
PR:append = ".hds1"

inherit hds-fara-nume

do_configure:prepend() {
	grep -q 'Modificat de moneasoftware.com si hdsatelit.com' ${S}/main.c \
		|| sed -i '1i /* Modificat de moneasoftware.com si hdsatelit.com, 2026 (textul unui mesaj de eroare) */' ${S}/main.c
	sed -i 's|from local WebInterface/[[:alnum:]]*\\n"|from the local web interface\\n"|' ${S}/main.c
}

do_install:append() {
	hds_fara_nume ${D}${bindir}/grab
}

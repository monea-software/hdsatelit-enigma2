# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# volatile-media (scriptul de pornire care pune un tmpfs peste /media) fara numele altei echipe in metadatele
# pachetului (regula: nimic din ce iese nu poarta numele altor imagini, interfete, pluginuri sau skinuri; notitele de
# licenta si de autor raman).
#
# MAINTAINER: reteta din care vine pachetul pune numele echipei ei in campul Maintainer (control in
# /var/lib/opkg/info, Packages din feed). Campul spune cine intretine pachetul in distributie; nu e o notita de
# copyright sau de licenta. Licenta ramane cea a retetei (GPL-2.0-or-later, license-gplv2.inc), cu textul ei in lista
# licentelor; scriptul volatile-media.sh nu are antet de autor. Valoarea e cea a distributiei (MAINTAINER din
# conf/distro/hdsatelit.conf), ca la toate retetele fara MAINTAINER propriu. Continutul pachetului nu se schimba.
# PR ".hds1": alte metadate la aceeasi versiune, ca opkg sa ia pachetul din feed.
MAINTAINER = "Monea Software pentru HD Satelit"
PR:append = ".hds1"

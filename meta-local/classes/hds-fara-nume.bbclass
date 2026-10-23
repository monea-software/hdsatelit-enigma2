# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-fara-nume.bbclass: paza retetelor straine carora stratul le scoate numele altor imagini, interfete web,
# pluginuri sau skinuri din ce ajunge in imagine (regula: nimic din ce iese nu poarta asemenea nume; notitele de
# licenta si de autor raman). O mostenesc bbappend-urile din recipes-local care schimba un text al pachetului
# (tuxbox-common, aio-grab).
#
#   hds_fara_nume <fisier>...   opreste construirea (bbfatal) daca vreunul dintre fisiere mai poarta un asemenea nume;
#                               se cheama la sfarsitul lui do_install, pe fisierele instalate (si pe cele binare).
#
# De ce si aici, nu numai in rootfs: sursa acestor retete vine de pe ramura master (SRCREV = AUTOREV in stratul comun),
# deci textul din amonte se poate schimba intre doua constructii; o inlocuire care nu se mai potriveste sau un nume
# nou se vad la reteta, nu abia in imagine. Cautarea completa, cu exceptiile, ramane cea din rootfs
# (oe-build/cauta-nume-rootfs.py); aici sunt numai numele lungi, fara deosebire de litere mari si mici (doua dintre ele
# numai ca inceput, respectiv sfarsit de cuvant: altfel le-ar prinde si cuvinte obisnuite care le contin).
# Lista e scrisa rot13 (ca in unelte/stb/verifica_fara_concurenti.py): stratul si retetele ies cu oferta de sursa
# (clasa hds-surse, surse_versiune.py), deci nu au voie sa poarte numele; se decodeaza cu tr la rulare.

HDS_FARA_NUME_ROT13 = "bcra[ _-]?(ngi|cyv|ivk|jrovs|ou|fcn|qebvq|ivfvba|uqs|rfv|ase|rvtug|zvcf|efv|kgn|nns)"
HDS_FARA_NUME_ROT13 .= "|oynpx[ _-]?ubyr|grnz[ _-]?oyhr|cher[ _-]?2|qernz[ _-]?(bf|ryvgr)|arjavtzn|rtnzv|fngqernzte"
HDS_FARA_NUME_ROT13 .= "|r2bcracyhtvaf|bbmbba|fngybqtr|arzrfvf|qryvgr([^[:nycun:]]|$)|oyhr[ _-]?cnary|zrgevk[ _-]?uq"
HDS_FARA_NUME_ROT13 .= "|(^|[^[:nycun:]])ngvyr[ _-]?uq|zlzrgevk"

hds_fara_nume() {
	m=$(printf '%s' '${HDS_FARA_NUME_ROT13}' | tr 'A-Za-z' 'N-ZA-Mn-za-m')
	[ -n "$m" ] || bbfatal "hds_fara_nume: lista numelor e goala"
	[ $# -ge 1 ] || bbfatal "hds_fara_nume: niciun fisier de verificat"
	for f in "$@"; do
		[ -f "$f" ] || bbfatal "hds_fara_nume: lipseste $f"
		if grep -a -i -E -q "$m" "$f"; then
			bbfatal "hds_fara_nume: $f poarta numele altei imagini, interfete, plugin sau skin: $(grep -a -i -E -o "$m" "$f" | sort -u | tr '\n' ' ')"
		fi
	done
	bbnote "hds_fara_nume: $# fisiere fara numele altor imagini"
}

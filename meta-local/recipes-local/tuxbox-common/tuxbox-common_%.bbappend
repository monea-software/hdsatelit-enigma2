# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# tuxbox-common cu licenta sursei lui.
#
# Reteta OE-Alliance scrie LICENSE = "CLOSED" (prin license-close.inc), dar depozitul sursei
# (oe-alliance-tuxbox-common) are fisierul LICENSE cu textul GNU GPL versiunea 2. Pachetul pune in imagine listele de
# sateliti, cablu si terestru (/etc/tuxbox/satellites.xml, cables.xml, terrestrial.xml, atsc.xml) si timezone.xml.
# Cu licenta sursei, lista licentelor din imagine (clasa hds-licente) il arata ca GPL, cu textul lui, iar clasa
# hds-surse ii pastreaza sursa. Suma md5 a textului se verifica la do_populate_lic: un LICENSE schimbat in sursa
# opreste construirea.
# PR cu sufixul ".hds" (mai jos), ca pachetul cu licenta schimbata sa se vada in manifest si in "opkg list-installed".

LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://LICENSE;md5=b4a4deb94acc9916ca04ba6c5e4d0700"

# terrestrial.xml fara numele altor imagini (regula: nimic din ce iese nu poarta numele altor imagini, interfete,
# pluginuri sau skinuri; notitele de licenta si de autor raman). Antetul fisierului (comentariul de la inceput, pana la
# primul "-->") explica valorile campurilor; la doua valori spune in paranteza care imagini o folosesc intr-un fel sau
# altul, iar la sfarsit da si depozitul altei imagini. Numai antetul se schimba:
#   - "(OE-Alliance / <alta imagine>)" devine "(OE-Alliance)" (intelesul din imaginile OE-Alliance, ca a noastra);
#   - "6 = 6/4 (<alta imagine>)," si "4 = 7/8 (<alta imagine>)," primesc "(other images)" (antetul e in engleza);
#   - adresa depozitului altei imagini se scoate; ramane cea a depozitului OE-Alliance, de unde vine fisierul;
#   - nota GPL-2.0 par. 2a (fisier schimbat), ca in codul imaginii, pe primul rand al antetului.
# Expresiile nu poarta numele: se potrivesc dupa forma randului. Datele raman neschimbate, si se verifica: antetul
# incepe pe randul 2 in sursa, fisierul se citeste ca XML dupa inlocuiri, tot ce urmeaza dupa antet e identic cu
# fisierul din sursa, iar celelalte patru liste sunt identice cu sursa. Sursa vine de
# pe ramura master (AUTOREV), deci textul se poate schimba: hds_fara_nume (clasa hds-fara-nume) opreste construirea
# daca vreun nume a ramas in listele instalate.
# PR ".hds2" (era ".hds1", al licentei): continutul lui terrestrial.xml s-a schimbat la aceeasi versiune.
PR:append = ".hds2"

inherit hds-fara-nume

do_install:append() {
	f=${D}/etc/tuxbox/terrestrial.xml
	# nota se pune pe randul 3, in antet: antetul trebuie sa inceapa pe randul 2, altfel nimic de aici nu se potriveste
	[ "$(sed -n 2p ${S}/src/terrestrial.xml)" = "<!--" ] \
		|| bbfatal "terrestrial.xml: antetul nu mai incepe pe randul 2 in sursa; inlocuirile de aici trebuie refacute"
	sed -i \
		-e '2a\	Modificat de moneasoftware.com si hdsatelit.com, 2026 (header comments only; data unchanged).' \
		-e '1,/-->/ s|(OE-Alliance / [[:alnum:]]*)|(OE-Alliance)|' \
		-e '1,/-->/ s|= \([0-9]/[0-9]\) ([[:upper:]][[:alnum:]]*),$|= \1 (other images),|' \
		-e '1,/-->/ { /github[.]com[/]/ { /github[.]com[/]oe-alliance[/]/!d } }' \
		"$f"
	python3 -c 'import sys, xml.etree.ElementTree as E; E.parse(sys.argv[1])' "$f" \
		|| bbfatal "terrestrial.xml nu se mai citeste ca XML dupa inlocuiri"
	sed '1,/-->/d' ${S}/src/terrestrial.xml > ${T}/terrestrial-date-sursa
	sed '1,/-->/d' "$f" > ${T}/terrestrial-date-instalat
	cmp -s ${T}/terrestrial-date-sursa ${T}/terrestrial-date-instalat \
		|| bbfatal "terrestrial.xml: s-a schimbat si altceva decat antetul (datele trebuie sa ramana ca in sursa)"
	for i in satellites.xml cables.xml atsc.xml timezone.xml; do
		cmp -s ${S}/src/$i ${D}/etc/tuxbox/$i || bbfatal "$i nu mai e identic cu sursa"
	done
	hds_fara_nume ${D}/etc/tuxbox/satellites.xml ${D}/etc/tuxbox/cables.xml ${D}/etc/tuxbox/terrestrial.xml \
		${D}/etc/tuxbox/atsc.xml ${D}/etc/tuxbox/timezone.xml
}

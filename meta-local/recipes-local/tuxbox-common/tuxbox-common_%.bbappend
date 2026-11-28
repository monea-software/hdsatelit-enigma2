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
# fisierul din sursa, iar cables.xml, atsc.xml si timezone.xml sunt identice cu sursa (satellites.xml: un singur FEC
# schimbat, vezi FEC-UL DE PE 5.0W mai jos). Sursa vine de
# pe ramura master (AUTOREV), deci textul se poate schimba: hds_fara_nume (clasa hds-fara-nume) opreste construirea
# daca vreun nume a ramas in listele instalate.
# PR ".hds2" (era ".hds1", al licentei): continutul lui terrestrial.xml s-a schimbat la aceeasi versiune.
# PR ".hds3" (0.7.5, 15.11.2026, SXP): copia listei satelitilor a imaginii, mai jos.
# PR ".hds4" (0.7.7, 16.11.2026, SAT2): listele de cautare ca fisiere de configurare (CONFFILES, mai jos).
# PR ".hds5" (0.8.0, 26.11.2026, FEC1): 5.0W 12564 V cu FEC 2/3 in loc de 3/4 (FEC-UL DE PE 5.0W, mai jos).
PR:append = ".hds5"

# FEC-UL DE PE 5.0W (0.8.0, 26.11.2026, FEC1): in lista sursei, 5.0W Eutelsat 5 West B 12564 V (DVB-S2 8PSK 35300,
# PLS Gold 131070, fluxurile 1, 3 si 5: Rai) are fec_inner="3" (3/4). Pe un DM920 (BCM45308X) cu antena pe 5.0W,
# acordarea cu 3/4 n-a prins niciodata purtatoarea (de 10 ori, nivel 90%, cand celelalte transpondere de pe 5.0W se
# prindeau); in aceeasi perioada, aceeasi purtatoare s-a prins cu 2/3 (fluxul 11, 452 ms), iar apoi cu 2/3 toate
# trei fluxurile s-au prins in 238-250 ms, cu imagine (Rai 1, Rai 3, TGR). Listele publice nu se potrivesc intre ele
# (2/3 sau 3/4, dupa data); lista sursei are 3/4. Se schimba numai FEC-ul celor trei randuri, numai in blocul -50;
# rata ramane (35300 se prinde), iar celelalte transpondere de pe 5.0W raman cum sunt. Randurile se cauta intregi: daca
# sursa nu le mai are exact asa (de 3 ori cu 3/4, nicio data cu 2/3), construirea se opreste si inlocuirea se reface.
# Dupa inlocuire: fisierul se citeste ca XML, iar cu cele trei FEC-uri puse inapoi e identic cu sursa (nimic altceva
# schimbat). La cine are lista neschimbata, lista noua vine singura (CONFFILES, mai jos); cine si-a schimbat lista o
# pastreaza pe a lui (lista noua sta alaturi, ca satellites.xml-opkg), iar canalele deja cautate tin FEC-ul vechi in
# lamedb pana la o cautare noua pe 5.0W. Inlocuirea e in do_install, intre randurile "FEC 5.0W: inceput" si "sfarsit".

# Listele de cautare ca fisiere de configurare (0.7.7, 16.11.2026, SAT2; forum 1588: un satelit sters nu mai revine singur).
# Fara CONFFILES (asa e reteta OE-Alliance, si la fel in alte imagini), opkg rescrie la orice
# actualizare a pachetului /etc/tuxbox/satellites.xml cu lista din pachet: satelitii stersi de om (de mana sau din editorul de
# canale de pe televizor si din web, care scriu acolo) reveneau o data, la actualizarea imaginii. Cu CONFFILES, opkg 0.10.0
# (libopkg/opkg_install.c, backup_modified_conffiles si resolve_conffiles) pastreaza fisierul schimbat de om si pune lista
# noua alaturi, ca <fisier>-opkg; un fisier neschimbat primeste lista noua; unul sters de om se pune din nou. La trecerea de
# la un pachet fara conffiles (.hds2/.hds3) opkg compara fisierul de pe receptor cu cel din pachetul nou: listele sunt aceleasi
# la acelasi SRCREV, deci numai cine a schimbat ceva isi pastreaza lista. Transponderele noi ale imaginii ajung oricum la
# satelitii omului prin copia de mai jos (Components/HdsSatelitiImagine.py, la pornire). Aceeasi clasa (liste de cautare pe
# care omul le poate schimba): cables.xml, terrestrial.xml, atsc.xml; timezone.xml ramane al pachetului (nu e o lista de
# cautare). Probat cu opkg 0.10.0 pe pachetele adevarate (.hds3 -> .hds4 -> o lista noua; schimbat, neatins, sters).
CONFFILES:${PN} = "${sysconfdir}/tuxbox/satellites.xml ${sysconfdir}/tuxbox/cables.xml ${sysconfdir}/tuxbox/terrestrial.xml \
	${sysconfdir}/tuxbox/atsc.xml"

# Copia listei satelitilor a imaginii: /usr/share/hdsatelit/satellites-imagine.xml, identica cu /etc/tuxbox/satellites.xml
# din pachet. O lista de canale adusa din alt panou scrie satellites.xml-ul ei (de multe ori cu cativa sateliti) peste
# /etc/tuxbox/satellites.xml; celelalte locuri (/etc/satellites.xml, /usr/share/tuxbox/satellites.xml) sunt legaturi spre
# el, deci lista imaginii se pierdea. Copia nu e in /etc (nu e fisier de configurare) si n-o atinge nicio lista de canale;
# din ea enigma2 (Components/HdsSatelitiImagine.py) pune la loc, la pornire, satelitii pe care omul are canale sau ii are
# la tunere, fara sa stearga ce a adus omul, si tot din ea vine "Pune la loc sateliții din imagine" din editorul de canale.
FILES:${PN} += "${datadir}/hdsatelit/satellites-imagine.xml"

# Sursa fixata la comiterea din imaginea 0.6.0 (pachetul tuxbox-common 1.0+git1030+194f4de0 din manifestul ei; lotul
# imagine-060-v10): reteta OE-Alliance ia ultima comitere de pe master (AUTOREV), iar dupa 24.10.2026 master a primit
# cables.xml schimbat, asa ca o constructie noua ar fi pus alte liste de cablu decat imaginea lansata. Fixata, orice
# imagine noua pe stratul 0.6.0 (V20, V30, V40, V10) are aceleasi liste ca 0.6.0; listele noi vin cu o imagine noua.
# Cu ":pn-tuxbox-common", ca la dvbmediasink: distributia pune SRCREV:pn-tuxbox-common ?= AUTOREV
# (unstable-versions.inc), iar varianta cu override castiga in fata unui SRCREV simplu.
SRCREV:pn-tuxbox-common = "194f4de3c3e78d3f4823589f2f65dd0adf15fb32"

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
	# FEC 5.0W: inceput (FEC-UL DE PE 5.0W, mai sus)
	s=${D}/etc/tuxbox/satellites.xml
	tpa='<transponder frequency="12564000" symbol_rate="35300000" polarization="1" fec_inner="'
	tpb='" system="1" modulation="2" is_id="[135]" pls_mode="1" pls_code="131070" />'
	bloc5w='/^[[:space:]]*<sat [^>]*position="-50">$/,/^[[:space:]]*<\/sat>$/'
	[ "$(sed -n "$bloc5w p" ${S}/src/satellites.xml | grep -c "$tpa"3"$tpb")" = 3 ] \
		&& [ "$(sed -n "$bloc5w p" ${S}/src/satellites.xml | grep -c "$tpa"2"$tpb")" = 0 ] \
		|| bbfatal "satellites.xml: 5.0W 12564 V nu mai e in sursa de 3 ori cu fec_inner 3; inlocuirea FEC trebuie refacuta"
	sed -i "$bloc5w s|\($tpa\)3\($tpb\)|\12\2|" "$s"
	python3 -c 'import sys, xml.etree.ElementTree as E; E.parse(sys.argv[1])' "$s" \
		|| bbfatal "satellites.xml nu se mai citeste ca XML dupa inlocuirea FEC"
	[ "$(sed -n "$bloc5w p" "$s" | grep -c "$tpa"2"$tpb")" = 3 ] \
		|| bbfatal "satellites.xml: inlocuirea FEC pe 5.0W 12564 V nu s-a facut la toate trei fluxurile"
	sed "$bloc5w s|\($tpa\)2\($tpb\)|\13\2|" "$s" > ${T}/satellites-inapoi
	cmp -s ${S}/src/satellites.xml ${T}/satellites-inapoi \
		|| bbfatal "satellites.xml: s-a schimbat si altceva decat FEC-ul de pe 5.0W 12564 V"
	# FEC 5.0W: sfarsit
	for i in cables.xml atsc.xml timezone.xml; do
		cmp -s ${S}/src/$i ${D}/etc/tuxbox/$i || bbfatal "$i nu mai e identic cu sursa"
	done
	hds_fara_nume ${D}/etc/tuxbox/satellites.xml ${D}/etc/tuxbox/cables.xml ${D}/etc/tuxbox/terrestrial.xml \
		${D}/etc/tuxbox/atsc.xml ${D}/etc/tuxbox/timezone.xml
	install -d ${D}${datadir}/hdsatelit
	install -m 0644 ${D}/etc/tuxbox/satellites.xml ${D}${datadir}/hdsatelit/satellites-imagine.xml
	cmp -s ${D}/etc/tuxbox/satellites.xml ${D}${datadir}/hdsatelit/satellites-imagine.xml \
		|| bbfatal "copia satellites-imagine.xml nu e identica cu lista instalata"
}

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# enigma2-hdsatelit r2 numai pentru ZGEMMA H8.2H SE (masina h8se) si H8.2H Plus (masina h8): codul versiunii 0.7.8 (acelasi
# SRCREV si acelasi PV), cu HDS_FARA_MEMORIE_ES din reteta (ca r1), plus peticul zgm1-h8-r2.patch cu doua reparatii ale
# tunerelor, fara restul schimbarilor de dupa 0.7.8:
#   - motorul (sec.h, frontend.cpp/.h, hdsrotire.cpp/.h): demodulatorul acestor receptoare nu cauta singur semnalul dupa ce
#     antena ajunge pe pozitie, deci in bucla de dupa comanda, dupa 3 s fara semnal, acordarea se cere din nou;
#   - NimManager.py: un tuner fara randuri Mode si fara satelit (tunerul B al Plus) primeste cablu si terestru dupa ce spune
#     nucleul (DTV_ENUM_DELSYS); tunerele cu randuri Mode isi pastreaza alegerea.
# Sta in alt dosar decat enigma2-hdsatelit.bbappend al stratului (acelasi nume l-ar inlocui), deci se adauga peste el.
# PR r2 trece peste r1 si r0, cu acelasi PV.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:h8 = " file://zgm1-h8-r2.patch"
SRC_URI:append:h8se = " file://zgm1-h8-r2.patch"
PR:h8 = "r2"
PR:h8se = "r2"
hds_h8_r2_verifica() {
	grep -q 'HDS_REACORDARE_ROTOR' ${S}/lib/dvb/sec.h || bbfatal "H8 r2: peticul ZGM1 nu e pus (sec.h fara HDS_REACORDARE_ROTOR)"
	grep -q 'case eSecCommand::HDS_REACORDARE_ROTOR' ${S}/lib/dvb/frontend.cpp || bbfatal "H8 r2: frontend.cpp fara HDS_REACORDARE_ROTOR"
	grep -q '^def hdsSistemeNucleu' ${S}/lib/python/Components/NimManager.py || bbfatal "H8 r2: NimManager.py fara hdsSistemeNucleu"
}
do_configure:append:h8() {
	hds_h8_r2_verifica
}
do_configure:append:h8se() {
	hds_h8_r2_verifica
}

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hdsatelit-drivere-feed: metapachet GOL, numai pentru constructie si culegere (11.11.2026, agentul WD; Eduard 22:07: toate
# driverele USB care au sens pe receptoarele noastre, in feed, instalate singure cand omul baga stickul). NU intra in
# imagine si nu-l instaleaza nimeni: `bitbake hdsatelit-drivere-feed` construieste driverele masinii, culegerea feedului
# (--cu hdsatelit-drivere-feed) le aduna cu dependintele lor (modulul nucleului, firmware-ul), iar unealta
# oe-build/harta_drivere.py (uneltele noastre) citeste lista de aici (campul Depends al pachetului) si face tabela
# ID USB -> pachet pe care o foloseste imaginea (data/hds-drivere-pachete.json, Components/HdsDriverLipsa.py).
#
# Ce e deja in imagine ramane in imagine (hdsatelit-base.bb si .bbappend: rt8188fu, modulele Wi-Fi si de retea USB din nucleu,
# pe familia Octagon/Uclan/GigaBlue si rt8821cu, rtl8192eu, rt8822cu, mt7601u; din 12.11.2026, pe toate masinile ARM, si
# driverele stickurilor Wi-Fi 5 cele mai vandute, HDS_WIFI_VANDUTE: rtl8821au, rtl88x2bu cu usb-modeswitch, rtl88xxau,
# rt8821cu; pe Solo SE numai rtl8821au): ele sunt chiar drumul omului spre internet.
# Aici numai ce lipseste din imagine, hotarat dupa ID-urile USB (un driver din afara nucleului peste unul din nucleu pe
# aceleasi ID-uri ar face doua module pe acelasi stick; harta_drivere.py opreste tabela daca se intampla):
#   - stickurile Wi-Fi 5 si Wi-Fi 6 pe care nucleele noastre (4.4.35, 4.1, 3.14, 3.13) nu le stiu deloc si care nu sunt
#     in imagine: RTL8814AU, RTL8192FU, RTL8832BU/8852BU, RTL8832CU/8852CU, MT7610U (pe Solo SE si RTL8812AU,
#     RTL8812BU/8822BU, RTL8811CU/8821CU);
#   - usb-modeswitch, numai pe Solo SE (pe ARM e in imagine): stickurile Realtek care pornesc ca "CD" (0bda:1a2b) se
#     comuta singure (regula udev a imaginii, 40-realtek-zerocd.rules, cheama /usr/sbin/usb_modeswitch);
#   - pe masinile fara ele in imagine: rtl8192eu, rt8822cu, mt7601u (din afara nucleului, unde nucleul nu-l are);
#   - adaptorul de retea gigabit ASIX AX88179 (in nucleu numai pe u57/u571);
#   - RTL8723AU: modulul din nucleu (staging r8723au) pe HiSilicon 4.4.35, driverul din afara (rt8723a) pe Vu+ 4K;
#   - Vu+ Solo SE (NAND 256 MB, nimic Wi-Fi in imagine): modulele nucleului si firmware-ul lor, plus driverele din afara
#     care se compileaza pe 3.13.5.
# Ce NU intra si de ce (pe larg in lucru-sesiune/paralel-1111b/STADIU-WD-DRIVERE-USB.md):
#   - rt3070, rt3573, rt5572 (Ralink din afara nucleului): rt2800usb din nucleu are RT3573, RT53XX si RT55XX pe toate masinile;
#   - rtl8192cu din afara: rtl8192cu din nucleu e in imagine (in afara de Solo SE, unde intra cel din afara);
#   - r8152 din afara (rt8156): ar inlocui r8152 din nucleu, care e in imagine (RTL8152/8153);
#   - rtk-btusb, rtl8723bt, aic8800 (Bluetooth): imaginea nu are inca bluez si ecran de imperechere;
#   - rtl8723bs, rtl8723ds (SDIO), qcacld-2.0 (Edision OS mio), bcmdhd (placa interna Vu+ Duo4K, deja in imagine de la
#     masina): placi interne ale altor receptoare, nu stickuri.
# Masinile sunt numite una cate una (ca la hdsatelit-base.bbappend): un pachet pe care nucleul unei masini nu-l face ar
# opri constructia, deci o masina noua nu primeste lista fara proba.
SUMMARY = "Driverele USB din feedul imaginii HDSatelit"
DESCRIPTION = "Metapachet gol pentru constructia si culegerea driverelor USB care nu sunt in imagine; receptorul le instaleaza singur cand omul baga stickul."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
PV = "0.1.5"

PACKAGE_ARCH = "${MACHINE_ARCH}"
inherit packagegroup
ALLOW_EMPTY:${PN} = "1"

# Wi-Fi 5 / Wi-Fi 6 fara driver in nucleele noastre, pe toate masinile ARM. Cele mai vandute (rtl8821au, rtl88x2bu,
# rtl88xxau, cu usb-modeswitch, si rt8821cu) sunt din 12.11.2026 in IMAGINE pe toate masinile ARM (hdsatelit-base.bbappend,
# HDS_WIFI_VANDUTE, agentul WD2), deci nu mai stau aici: un driver din feed pe aceleasi ID-uri ca un modul din imagine ar
# opri tabela (harta_drivere.py --manifest).
HDS_DF_WIFI_NOI = "rt8814au rtl8192fu rtl8852bu rtl8852cu mt7610u"
# driverele din afara nucleului pe care familia Octagon/Uclan/GigaBlue le are deja in imagine (rt8821cu e acum in imagine
# pe toate masinile ARM)
HDS_DF_WIFI_OCTAGON = "rtl8192eu rt8822cu"
# Vu+ Solo SE are in imagine numai rtl8821au (NAND mic); celelalte vandute raman in feed acolo
HDS_DF_VANDUTE_SOLOSE = "rtl88xxau rtl88x2bu rt8821cu usb-modeswitch usb-modeswitch-data"

RDEPENDS:${PN} = ""
# Octagon SF8008, SF8008 MINI, Uclan Ustym 4K PRO, GigaBlue UHD TRIO 4K (nucleu 4.4.35, MT7601U in nucleu, in imagine)
RDEPENDS:${PN}:append:sf8008 = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
# Octagon SX88V2 / SX988 (V19; nucleu 4.4.176, MT7601U si R8723AU =m in defconfig): ca pe SF8008
RDEPENDS:${PN}:append:sx88v2 = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
RDEPENDS:${PN}:append:sx988 = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
# AB-COM PULSe 4K si PULSe 4K MINI (MPU, 12.11.2026; linux-abcom 4.4.35: R8723AU=m, MT7601U=m in imagine, fara AX88179); rtl8192eu
# si rt8822cu nu sunt in imaginea lor (ca la Multibox SE), deci si HDS_DF_WIFI_OCTAGON
RDEPENDS:${PN}:append:pulse4k = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} ax88179-178a kernel-module-r8723au"
RDEPENDS:${PN}:append:pulse4kmini = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} ax88179-178a kernel-module-r8723au"
# Amiko Viper 4K (V10): MT7601U in nucleu (in imagine), driverele Octagon nu
RDEPENDS:${PN}:append:viper4k = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} ax88179-178a kernel-module-r8723au"
# Novaler Multibox 4K SE (MNS, 12.11.2026; linux-maxytec 4.4.35): MT7601U si R8723AU =m in nucleu, AX88179 nu; rtl8192eu
# si rt8822cu nu vin cu masina (la imaginea publica a masinii vin din packagegroup-oea-wifi)
RDEPENDS:${PN}:append:multiboxse = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} ax88179-178a kernel-module-r8723au"
# Amiko Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): AX88179 e in nucleu, MT7601U lipseste din nucleu (driverul
# din afara); modulele din afara cu -mlong-calls (bbappend-urile din recipes-local/<reteta>)
RDEPENDS:${PN}:append:u57 = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u kernel-module-r8723au"
RDEPENDS:${PN}:append:u571 = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u kernel-module-r8723au"
# Vu+ Solo4K (3.14.28), Uno4K SE (4.1.20), Duo4K (4.1.45): fara MT7601U si R8723AU in nucleu
# tunerele DVB-C/T2 pe USB VU+ Turbo (2b19:a111) si Turbo2 (b711:1211), pe toate Vu+ (12.11.2026, dorinelu, forumul 795;
# Gpiupiu, 801): invelisurile OE-A (meta-oe enigma2-dvb-drivers), pachete goale pe masina care trag prin Recommends driverul
# producatorului nemodificat (meta-vuplus vuplus-tuner-turbo/-turbo2: modulul + firmware-ul, pe nucleul fiecarui model) si
# modulele nucleului dvb-usb, dvb-usb-v2, cypress-firmware. Numele sunt cele cautate de panourile de drivere si aratate in
# Extensii > Drivere. harta_drivere.py urmeaza Recommends al invelisului si trece pachetele trase in "cu"; tunerul apare in
# Setari tunere dupa repornirea interfetei (puntea vtuner, lib/dvb/hdsvtuner.cpp; HdsDriverLipsa intreaba).
HDS_DF_TURBO = "enigma2-plugin-drivers-dvb-usb-turbo enigma2-plugin-drivers-dvb-usb-turbo2"
HDS_DF_VU4K = "${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a ax88179-178a ${HDS_DF_TURBO}"
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_DF_VU4K}"
RDEPENDS:${PN}:append:vuultimo4k = " ${HDS_DF_VU4K}"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_DF_VU4K}"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_DF_VU4K}"
# Vu+ Duo 4K Lite (ULT 13.11.2026): fara tunerele VU+ Turbo/Turbo2 (vuplus-tuner-turbo din meta-vuplusde are COMPATIBLE_MACHINE
# numai vuuno4kse, vuzero4k; bitbake se oprea cu „Nothing RPROVIDES vuplus-tuner-turbo”)
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a ax88179-178a"
# GigaBlue UHD Quad 4K Pro (ALFA, linux-gigablue 4.1.20: fara MT7601U, R8723AU si AX88179 in nucleu, ca la Vu+ 4K); fara
# tunerele VU+ Turbo (driverul lor e in meta-vuplus, care nu e in straturile masinii)
RDEPENDS:${PN}:append:gbquad4kpro = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a ax88179-178a"
# GigaBlue UHD X3 4K (MGX): gb72604/defconfig nici el fara MT7601U, R8723AU si AX88179_178A
RDEPENDS:${PN}:append:gbx34k = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a ax88179-178a"
# AX HD51 (MHD, linux-gfutures 4.10.12, hd51/defconfig): MT7601U e in nucleu (si in imagine, hdsatelit-base.bbappend), R8723AU
# si AX88179 lipsesc (driverele din afara); fara tunerele VU+ Turbo (meta-vuplus nu e in straturile masinii)
RDEPENDS:${PN}:append:ax51 = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} rt8723a ax88179-178a"
# Edision (MED, linux-edision 5.15): MT7601U si AX88179_178A sunt in nucleu (mt7601u in imagine; ax88179 ca modulul
# nucleului, nu reteta din afara lui, scrisa pentru nucleele 4.x); R8723AU lipseste => rt8723a in feed. mt7610u din
# HDS_DF_WIFI_NOI e scris pentru nucleele vechi; pe 5.15 nucleul are MT76x0U: de urmarit la prima constructie.
RDEPENDS:${PN}:append:osmio4kplus = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} rt8723a kernel-module-ax88179-178a"
RDEPENDS:${PN}:append:osmini4k = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} rt8723a kernel-module-ax88179-178a"
RDEPENDS:${PN}:append:osmio4k = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} rt8723a kernel-module-ax88179-178a"
# Novaler Multibox 4K PRO (MNP, linux-maxytec 4.4.35, multiboxpro/defconfig): MT7601U in nucleu (si in imagine), R8723AU
# in nucleu (modulul staging, ca pe SF8008), AX88179 lipseste (driverul din afara); rtl8192eu si rt8822cu nu sunt in imagine
RDEPENDS:${PN}:append:multiboxpro = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} ax88179-178a kernel-module-r8723au"
# Zgemma H17 COMBO (MH7, linux-airdigital 4.10.12, h17/defconfig): ca la AX HD51, MT7601U e in nucleu, R8723AU si AX88179
# lipsesc (driverele din afara); fara tunerele VU+ Turbo (meta-vuplus nu e in straturile masinii)
RDEPENDS:${PN}:append:zgemmah17combo = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} rt8723a ax88179-178a"
# Dreambox DM900 si DM920 (V10, 13.11.2026; linux-dreambox 3.14, dm900/defconfig si dm920/defconfig): MT7601U nu exista in
# nucleu (a intrat in 3.19), R8723AU si AX88179_178A nesetate => driverele din afara, ca la Vu+ 4K; fara tunerele VU+ Turbo.
# Aceleasi retete se construiesc pe 3.14.28 pentru Vu+ Solo4K (HDS_DF_VU4K); probate la constructia de proba dm920 (DM9).
RDEPENDS:${PN}:append:dm900 = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a ax88179-178a"
RDEPENDS:${PN}:append:dm920 = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a ax88179-178a"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_DF_VU4K}"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_DF_VU4K}"
# Tunerul DVB-T/T2/C pe USB Xbox One Digital TV Tuner (045e:02d5) si stickurile DiBcom dib0700 (13.11.2026, agentul USB;
# schmith, LinuxSat 164155, Uno 4K SE): invelisul OE-A cu bbappend-ul nostru (recipes-local/enigma2-plugin-drivers-dvb-usb-dib0700:
# modulele dib0700, mn88472, tda18250 si firmware-ul linux-firmware-dib0700 prin RDEPENDS). Numai pe nucleele 4.1.20 si 4.1.45,
# care au peticul Xbox (aliasul in dvb-usb-dib0700.ko); NU pe Solo4K, Ultimo4K (3.14.28) si Solo SE (3.13.5), deci nu in HDS_DF_VU4K.
# Octagon SF8008 / SF8008 Mini (linux-octagon 4.4.35; 14.11.2026, agentul PLG; asistenta 821342: "nothing provides
# kernel-module-dib7000p"): dvb-usb-dib0700.ko are si aici aliasul Xbox si xbox_one_attach, iar dib7000p, mn88472 si
# modulele cerute de dib0700 sunt construite (nu erau in feed); TDA18250 e in nucleu (sf8008/defconfig:
# CONFIG_MEDIA_TUNER_TDA18250=y), deci aici nu exista pachetul kernel-module-tda18250. Invelisul il cere numai prin
# RRECOMMENDS, iar unde e modul (Vu+ 4.1, AX HD51, GigaBlue 4.1.20) il numim aici, ca sa intre in culegere.
# Restul familiilor (15.11.2026, agentul XBX; rafejo si darog69, forumul 801): modulele din imaginile 0.7.5 publicate
# (unelte/stb/module_nucleu_imagini.py: modules.order si modules.builtin din rootfs) si peticul Xbox din reteta nucleului
# OE-Alliance (KERNEL_PATCHES_SERIES_4_4_35 -> 0005-xbox-one-tuner-4.4.patch pe linux-uclan, linux-gigablue, linux-amiko
# 4.4.35; 0005-xbox-one-tuner-4.10.patch pe linux-gfutures 4.10.12; KERNEL_PATCH_DVB_XBOX_DIB pe linux-gigablue 4.1.20):
#   ustym4kpro, gbtrio4k, viper4k (4.4.35): dvb-usb-dib0700=m, dib7000p=m, mn88472=m, TDA18250=y (ca SF8008);
#   ax51 (4.10.12) si gbquad4kpro (4.1.20-1.9): dvb-usb-dib0700, dib7000p, mn88472 si tda18250 toate =m.
# NU pe Viper 4K V20/V30/V40 si Protek 4K X2 (u57, u571): nucleul lor n-are DVB deloc (nici dvb-core, nici dvb-usb).
# NU pe Vu+ Solo4K, Ultimo4K (3.14.28), Solo SE, Solo2, Duo2, Zero (3.13.5): fara mn88472 si tda18250 in nucleu.
HDS_DF_XBOX = "enigma2-plugin-drivers-dvb-usb-dib0700"
HDS_DF_XBOX_TDAM = "${HDS_DF_XBOX} kernel-module-tda18250"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:ax51 = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:gbquad4kpro = " ${HDS_DF_XBOX_TDAM}"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_DF_XBOX}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_DF_XBOX}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_DF_XBOX}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_DF_XBOX}"
RDEPENDS:${PN}:append:viper4k = " ${HDS_DF_XBOX}"
# Vu+ Solo SE (3.13.5, mips): modulele nucleului si firmware-ul lor (in imagine nu e niciunul) si driverele din afara care
# se compileaza pe 3.13.5 (toate, probat 11.11.2026). zd1211rw nu: firmware-ul lui (zd1211/zd1211_*) nu-l pune niciun pachet.
# Firmware-ul RTL8188EUS din firmware-rtl8188eu, nu din linux-firmware-rtl8188 (acela pune si fisierul lui firmware-rt8188fu).
HDS_DF_SOLOSE_NUCLEU = "kernel-module-rt2800usb kernel-module-rt73usb kernel-module-rt2500usb kernel-module-r8188eu \
    kernel-module-r8712u kernel-module-ath9k-htc kernel-module-carl9170 kernel-module-rtl8187 \
    linux-firmware-ralink firmware-rtl8188eu linux-firmware-rtl8192su linux-firmware-ath9k linux-firmware-carl9170 \
    kernel-module-r8152 kernel-module-asix kernel-module-cdc-ether kernel-module-cdc-ncm kernel-module-rndis-host \
    kernel-module-smsc95xx kernel-module-dm9601 kernel-module-sr9700"
HDS_DF_SOLOSE_AFARA = "${HDS_DF_WIFI_NOI} ${HDS_DF_VANDUTE_SOLOSE} ${HDS_DF_WIFI_OCTAGON} mt7601u rt8723a rt8188fu firmware-rt8188fu ax88179-178a rtl8192cu"
RDEPENDS:${PN}:append:vusolose = " ${HDS_DF_SOLOSE_NUCLEU} ${HDS_DF_SOLOSE_AFARA} ${HDS_DF_TURBO}"
# Zgemma Star S (MSS, 12.11.2026; linux-airdigital 4.10.12, defconfig sh1): toate modulele din HDS_DF_SOLOSE_NUCLEU sunt =m
# si in sh1 (verificat), MT7601U e in nucleu (modulul lui, cu firmware-ul, ca pe H17), R8723AU si AX88179 lipsesc (driverele
# din afara, ca pe H17 si AX HD51, acelasi nucleu), rt8188fu merge pe 4.x; fara tunerele VU+ Turbo (numai Vu+)
RDEPENDS:${PN}:append:sh1 = " ${HDS_DF_SOLOSE_NUCLEU} ${HDS_DF_WIFI_NOI} ${HDS_DF_VANDUTE_SOLOSE} ${HDS_DF_WIFI_OCTAGON} kernel-module-mt7601u firmware-mt7601u rt8723a rt8188fu firmware-rt8188fu ax88179-178a"
# Vu+ Solo2 (MS2, 12.11.2026): acelasi nucleu 3.13.5 (defconfig_proxy vusolo2: aceleasi module =m), aceleasi drivere
RDEPENDS:${PN}:append:vusolo2 = " ${HDS_DF_SOLOSE_NUCLEU} ${HDS_DF_SOLOSE_AFARA} ${HDS_DF_TURBO}"
# Vu+ Duo2 (V22, 14.11.2026): acelasi nucleu 3.13.5 (defconfig_proxy vuduo2: aceleasi module =m ca vusolose, verificat),
# aceleasi drivere; vuplus-tuner-turbo{,2}_3.13.5 au vuduo2 in COMPATIBLE_MACHINE
RDEPENDS:${PN}:append:vuduo2 = " ${HDS_DF_SOLOSE_NUCLEU} ${HDS_DF_SOLOSE_AFARA} ${HDS_DF_TURBO}"
# Vu+ Zero (MVZ, 12.11.2026): acelasi nucleu 3.13.5 (defconfig vuzero, fara proxy: aceleasi module =m ca Solo SE;
# in plus rtl8192cu.ko in nucleu, care nu se calca cu 8192cu.ko al driverului din afara), aceleasi drivere
RDEPENDS:${PN}:append:vuzero = " ${HDS_DF_SOLOSE_NUCLEU} ${HDS_DF_SOLOSE_AFARA} ${HDS_DF_TURBO}"

# 0.7.7 (SCM, 16.11.2026; dorinelu, forumul nostru 795 #2823, Vu+ Solo4K cu cititorul Smargo 0403:6001; TODO 15.11 23:17):
# adaptoarele seriale USB (FTDI, Prolific PL2303, Silicon Labs CP210x, WCH CH340/CH341, CDC-ACM) sunt in IMAGINE din 0.7.6
# (hdsatelit-base.bbappend, HDS_SERIAL_USB, aceleasi 17 masini, modulele =m in nucleele lor). Receptoarele cu imaginea de baza
# 0.7.0, 0.7.1 sau 0.7.3 nu le primesc insa prin actualizarea din meniu: hdsatelit-base 0.7.6 nu poate merge pe acele baze
# (cere openssl3-compat, libcrypto3, libssl3, pe care garda feedului le refuza: „trebuie imagine noua”; proba uscata SCM).
# Aici stau numai ca sa intre in tabela driverelor (oe-build/harta_drivere.py -> data/hds-drivere-pachete.json) si in culegerea
# bazelor vechi: Components/HdsDriverLipsa.py pune singur modulul cand omul baga adaptorul (sau la pornire, cu el in mufa), iar
# pe bazele 0.7.4 si 0.7.5, unde actualizarea le-a instalat deja, scrie „add” in uevent si udev il incarca, fara repornire.
# E ACELASI pachet si in imagine si aici (nu doua module care se bat pe acelasi ID), deci harta il lasa in tabela.
# kernel-module-usbserial vine singur, ca dependinta.
HDS_DF_SERIAL = "kernel-module-ftdi-sio kernel-module-pl2303 kernel-module-cp210x kernel-module-ch341 kernel-module-cdc-acm"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:viper4k = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:u57 = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:u571 = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vuultimo4k = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:gbquad4kpro = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:ax51 = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:vusolose = " ${HDS_DF_SERIAL}"
# Dreambox DM900 si DM920 (DM9, 16.11.2026): aceleasi module ca in HDS_SERIAL_USB din hdsatelit-base.bbappend (=m in 3.14)
RDEPENDS:${PN}:append:dm900 = " ${HDS_DF_SERIAL}"
RDEPENDS:${PN}:append:dm920 = " ${HDS_DF_SERIAL}"

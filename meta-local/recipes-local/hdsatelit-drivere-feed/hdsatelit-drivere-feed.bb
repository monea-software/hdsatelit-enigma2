# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hdsatelit-drivere-feed: metapachet GOL, numai pentru constructie si culegere (11.11.2026, agentul WD; Eduard 22:07: toate
# driverele USB care au sens pe receptoarele noastre, in feed, instalate singure cand omul baga stickul). NU intra in
# imagine si nu-l instaleaza nimeni: `bitbake hdsatelit-drivere-feed` construieste driverele masinii, culegerea feedului
# (--cu hdsatelit-drivere-feed) le aduna cu dependintele lor (modulul nucleului, firmware-ul), iar unealta
# oe-build/harta_drivere.py (hdsatelit-unelte) citeste lista de aici (campul Depends al pachetului) si face tabela
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
PV = "0.1.2"

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
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_DF_WIFI_NOI} ax88179-178a kernel-module-r8723au"
# Amiko Viper 4K (V10): MT7601U in nucleu (in imagine), driverele Octagon nu
RDEPENDS:${PN}:append:viper4k = " ${HDS_DF_WIFI_NOI} ${HDS_DF_WIFI_OCTAGON} ax88179-178a kernel-module-r8723au"
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
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_DF_VU4K}"
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_DF_VU4K}"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_DF_VU4K}"
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

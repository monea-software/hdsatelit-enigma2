# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Tunerul DVB-T/T2/C pe USB Xbox One Digital TV Tuner (045e:02d5) si stickurile DiBcom dib0700, in feedul modelelor Vu+ 4K
# (hdsatelit-drivere-feed; 13.11.2026, agentul USB; schmith, LinuxSat 164155 #970198, Uno 4K SE, cautare pe cablu).
# Tunerul Xbox = puntea DiBcom 0700C + demodulatorul Panasonic MN88472 + tunerul NXP TDA18250 (peticul nucleului
# 0012-media-dib0700-add-support-for-Xbox-One-Digital-TV-Tu.patch din meta-oe kernel-patches, pus pe linux-vuplus 4.1.20 si
# 4.1.45). Invelisul OE-A trage modulele numai prin RRECOMMENDS; aici cele de care tunerul chiar are nevoie devin RDEPENDS,
# ca sa le ia si culegerea feedului (urmeaza numai RDEPENDS) si opkg cu no_install_recommends (tda18250 a trecut in RRECOMMENDS
# la r1.hds3, mai jos: /etc/opkg/opkg.conf al imaginii n-are no_install_recommends, deci opkg install il pune; unde e modul,
# hdsatelit-drivere-feed il numeste si el, iar pe eMMC metapachetul e in imagine). mn88472 si tda18250 nu sunt
# in Depends-ul modulului dib0700 (le incarca xbox_one_attach prin request_module), deci trebuie numite aici; dib7000p il
# cer celelalte stickuri DiBcom ale tabelei (Hauppauge Nova-T si altele).
# Firmware: numai linux-firmware-dib0700 (linux-firmware, redistribuibil, LICENSE.dib0700). Scoase din Recommends
# firmware-urile OE-A cu licenta inchisa (firmware-mn8847x, firmware-dvb-usb-dibusb-*, firmware-xc3028*) si
# firmware-dvb-usb-dib0700-1.20 (acelasi fisier ca linux-firmware-dib0700: cele doua pachete s-ar bate pe el).
# Firmware-ul demodulatorului, dvb-demod-mn88472-02.fw, NU e in linux-firmware: fara el tunerul Xbox nu prinde semnal;
# hotararea daca il punem in feed e a lui Eduard (STADIU-USB.md, runda 0013).
# Numai pe masinile al caror nucleu stie tunerul Xbox (aliasul usb:v045Ep02D5 in dvb-usb-dib0700.ko, cu mn88472.ko si
# tda18250 ca modul sau in nucleu): vuuno4kse, vuzero4k, vuduo4klite (4.1.20-1.9), vuduo4k, vuduo4kse (4.1.45-1.17), si
# Octagon sf8008, sf8008m (linux-octagon 4.4.35, TDA18250 in nucleu; 14.11.2026, agentul PLG), Uclan ustym4kpro, GigaBlue
# gbtrio4k, Amiko viper4k (4.4.35, TDA18250 in nucleu), AX HD51 ax51 (4.10.12) si GigaBlue gbquad4kpro (4.1.20-1.9)
# (15.11.2026, agentul XBX; lista si dovezile in hdsatelit-drivere-feed.bb). Vu+ Solo4K, Ultimo4K (3.14.28), Solo SE
# (3.13.5) si Viper 4K V20/V30/V40, Protek 4K X2 (fara DVB in nucleu) nu au nici aliasul, nici modulele: acolo nu se pune.
# Pachetul ramane allarch, ca la OE-A, cu aceleasi Depends pe toate masinile (nume Provides, aceleasi pe 4.1.20 si 4.1.45):
# allarch.bbclass pune PACKAGE_ARCH = "all" la RecipePreFinalise cu setVar, care sterge si suprascrierile pe masina
# (probat 14.11 01:16-01:29: PACKAGE_ARCH:<masina> tot _all.ipk), deci nici RDEPENDS:<masina> n-ar fi sigur. Il publicam
# numai in feedul masinilor de mai sus; pe altele nu e in tabela, iar opkg s-ar opri curat (modulele lipsesc).
PR = "r1.hds3"
RRECOMMENDS:${PN}:remove = "firmware-mn8847x firmware-dvb-usb-dib0700-1.20 firmware-dvb-usb-dibusb-5.0.0.11 \
    firmware-dvb-usb-dibusb-6.0.0.8 firmware-dvb-usb-dibusb-an2235-01 firmware-xc3028-v27 firmware-xc3028l-v36"
# kernel-module-tda18250 numai RRECOMMENDS (r1.hds3; 14.11.2026, agentul PLG): pe Octagon SF8008 / SF8008 Mini tunerul e in
# nucleu (CONFIG_MEDIA_TUNER_TDA18250=y, fara pachet), iar un RDEPENDS oprea opkg acolo; pe Vu+ modulul intra in feed prin
# hdsatelit-drivere-feed (HDS_DF_XBOX_TDAM, si pe ax51, gbquad4kpro) si opkg il pune ca recomandare.
HDS_DIB0700_DEP = "kernel-module-dvb-usb-dib0700 kernel-module-dib7000p kernel-module-mn88472 linux-firmware-dib0700"
RDEPENDS:${PN}:append = " ${HDS_DIB0700_DEP}"
RRECOMMENDS:${PN}:append = " kernel-module-tda18250"

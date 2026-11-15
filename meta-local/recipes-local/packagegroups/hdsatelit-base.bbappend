# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): nucleul lui (linux-octagon 4.4.35, defconfig sf8008 din
# meta-octagon) are CONFIG_TUN=y, adica driverul tun e in nucleu, nu modul; pachetul kernel-module-tun nu se face pe
# aceasta masina, iar cererea din hdsatelit-base.bb ar opri constructia imaginii. /dev/net/tun exista oricum, deci
# OpenVPN merge la fel ca pe V20 (unde tun e modul). Numai pe sf8008: pe celelalte masini lista ramane neschimbata,
# iar hdsatelit-base.bb nu se atinge (verificarile lui fata de 0.5.0 raman aceleasi).
RDEPENDS:${PN}:remove:sf8008 = "kernel-module-tun"
#
# Octagon SF8008: load-ul producatorului incarca rtk_8822cbtusb.ko pe orice placa sf8008, iar placile cu cipul 8822C
# (Supreme, V3 Supreme) ii cer firmware-ul; imaginile facute pentru masina il au in /lib/firmware (rtl8822cu_fw si
# rtl8822cu_config, reteta OE-Alliance firmware-rtk8822cbtusb). Numai pe sf8008 (MINI nu are cipul).
RDEPENDS:${PN}:append:sf8008 = " firmware-rtk8822cbtusb"
#
# Octagon SF8008 si SF8008 MINI: Wi-Fi USB ca in imaginile facute pentru aceste masini (OE-Alliance,
# recipes-oe-alliance/image/oe-alliance-wifi.bb pune pe sf8008 si sf8008m enigma2-plugin-drivers-network-usb-rtl8821cu,
# -rtl8192eu, -mt7601u, -rtl8822cu si -rtl8188fu). Aici direct pachetele pe care le recomanda acestea (driverul si
# firmware-ul), fiindca o recomandare nu e o dependinta: rt8821cu + linux-firmware-8821cu, rtl8192eu + firmware-rtl8192eu,
# kernel-module-mt7601u (modulul din nucleu, CONFIG_MT7601U=m) + firmware-mt7601u, rt8822cu + firmware-rtk8822cbtusb;
# rt8188fu si firmware-rt8188fu sunt deja in hdsatelit-base.bb. Fara Bluetooth (rtk-btusb nu se recomanda pe sf8008).
HDS_WIFI_OCTAGON = "rt8821cu linux-firmware-8821cu rtl8192eu firmware-rtl8192eu kernel-module-mt7601u firmware-mt7601u rt8822cu"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_OCTAGON}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"
# Octagon SX88V2 4K DUAL OS si SX988 4K DUAL OS (V19, 14.11.2026; nucleul linux-octagon 4.4.176, CONFIG_TUN=m: kernel-module-tun
# din hdsatelit-base.bb ramane). Wi-Fi USB ca pe familia Octagon (oe-alliance-wifi.bb le da aceleasi drivere). SX88V2 are in
# plus Wi-Fi/Bluetooth intern UNISOC UWE5621 pe SDIO: driverul vine cu pachetul placii (uwe5621_bsp_sdio.ko, uwe5621_wifi.ko,
# incarcate de `load`), iar firmware-ul (wcnmodem.bin, uwewifi/*.ini) e numai RECOMANDAT de masina (firmware-uwe5621 in
# MACHINE_EXTRA_RRECOMMENDS): il cerem aici, altfel Wi-Fi-ul intern nu porneste.
RDEPENDS:${PN}:append:sx88v2 = " ${HDS_WIFI_OCTAGON} firmware-uwe5621"
RDEPENDS:${PN}:append:sx988 = " ${HDS_WIFI_OCTAGON}"
#
# Uclan Ustym 4K PRO (ustym4kpro, geamanul lui SF8008): nucleul linux-uclan are CONFIG_TUN=m (defconfig ustym4kpro), deci
# kernel-module-tun din hdsatelit-base.bb ramane (ca pe V20). Wi-Fi USB ca pe SF8008 MINI: imaginile facute pentru
# masina au rtl8822cu (88x2cu.ko) cu firmware-rtk8822cbtusb, iar celelalte drivere sunt aceleasi ca pe familia Octagon.
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"
#
# GigaBlue UHD TRIO 4K (masina gbmv200, MACHINEBUILD gbtrio4k): nucleul linux-gigablue are CONFIG_TUN=m si
# CONFIG_MT7601U=m (defconfig gbmv200), deci kernel-module-tun din hdsatelit-base.bb ramane (ca pe V20). Wi-Fi USB ca pe
# Ustym (aceleasi drivere din afara nucleului, acelasi nucleu 4.4.35): imaginile facute pentru masina recomanda si ele
# rtl8192eu (packagegroup-oea-wifi.bb, MACHINE_BRAND GigaBlue); celelalte se pun ca pe familia Octagon, ca un stick
# Wi-Fi obisnuit sa mearga la fel pe toata familia libreader.
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"
# Stickurile Wi-Fi Ralink (RT3070, RT2870, RT5370; cerute de un tester pe forum, 08.11.2026): nucleul gbmv200 are
# CONFIG_RT2800USB=m (cu RT33XX, RT35XX, RT53XX), deci modulul rt2800usb si firmware-ul rt*.bin din linux-firmware-ralink.
RDEPENDS:${PN}:append:gbtrio4k = " kernel-module-rt2800usb linux-firmware-ralink"
# Receptoarele cu memorie interna mica (suprascrierea hdsflashmic, conf/distro/hdsatelit.conf; Vu+ Solo SE, lotul
# mips-solose, 06.11.2026): imaginea trebuie sa incapa instalata in NAND-ul de 256 MB (hotararea lui Eduard, 06.11.2026),
# deci pachetele mari care nu tin de televizor stau in feedul imaginii si se instaleaza la cerere: navigatorul
# (hds-navigator: WPE WebKit 34,5 MB si ICU 10,2 MB comprimate), recunoasterea textului (hds-ocr si hds-ocr-modele:
# tesseract, leptonica, modelele de limba, ~14 MB). Wi-Fi USB rt8188fu: driver din afara nucleului, scris pentru nucleele
# 4.x; Solo SE nu are Wi-Fi si nucleul lui e 3.13.5, deci nu intra (masuratorile: lucru-sesiune/oe-60/mips-solose).
RDEPENDS:${PN}:remove:hdsflashmic = "hds-navigator hds-ocr hds-ocr-modele rt8188fu firmware-rt8188fu"
# Partea a doua pe stick (componenta hdsatelit-partea-doua, 06.11.2026 seara): descrierea modelului, sablonul ext4 si
# scriptul de pornire, pe toate masinile cu memorie mica; fiecare are files/modele/<MACHINEBUILD>.conf (altfel reteta e
# sarita si constructia se opreste aici, ca sa nu uitam descrierea unui model nou).
RDEPENDS:${PN}:append:hdsflashmic = " hdsatelit-partea-doua"

# Limite hardware, indiferent de locul sistemului: rt8188fu cere nucleu 4.x.
# Navigatorul si OCR asteapta constructia MIPS si auditul scripturilor.
# Pachetul se scoate din aceasta lista numai dupa acea poarta, apoi se trece
# in HDS_FUNCTII_MIPS_PREGATITE. Nu este o limita a memoriei USB.
HDS_FUNCTII_MIPS_PREGATITE ?= ""
HDS_FUNCTII_MIPS_IN_ASTEPTARE = "hds-navigator hds-ocr hds-ocr-modele"
RDEPENDS:${PN}:remove:vusolose = "rt8188fu firmware-rt8188fu ${@' '.join(p for p in d.getVar('HDS_FUNCTII_MIPS_IN_ASTEPTARE').split() if p not in (d.getVar('HDS_FUNCTII_MIPS_PREGATITE') or '').split())}"
RDEPENDS:${PN}:append:vusolose = " hdsatelit-radacina-usb"
# Zgemma Star S (MSS, 12.11.2026; masina sh1, MIPS, NAND): aceeasi imagine mica si aceleasi limite ca Solo SE
RDEPENDS:${PN}:remove:sh1 = "rt8188fu firmware-rt8188fu ${@' '.join(p for p in d.getVar('HDS_FUNCTII_MIPS_IN_ASTEPTARE').split() if p not in (d.getVar('HDS_FUNCTII_MIPS_PREGATITE') or '').split())}"
RDEPENDS:${PN}:append:sh1 = " hdsatelit-radacina-usb"
# Vu+ Solo2 (MS2, 12.11.2026): aceeasi imagine mica, aceleasi limite (nucleul 3.13.5, MIPS)
RDEPENDS:${PN}:remove:vusolo2 = "rt8188fu firmware-rt8188fu ${@' '.join(p for p in d.getVar('HDS_FUNCTII_MIPS_IN_ASTEPTARE').split() if p not in (d.getVar('HDS_FUNCTII_MIPS_PREGATITE') or '').split())}"
RDEPENDS:${PN}:append:vusolo2 = " hdsatelit-radacina-usb"
# Vu+ Duo2 (V22, 14.11.2026): aceleasi limite MIPS (nucleul 3.13.5); FARA radacina-usb si partea a doua (nu e memorie mica)
RDEPENDS:${PN}:remove:vuduo2 = "rt8188fu firmware-rt8188fu ${@' '.join(p for p in d.getVar('HDS_FUNCTII_MIPS_IN_ASTEPTARE').split() if p not in (d.getVar('HDS_FUNCTII_MIPS_PREGATITE') or '').split())}"
# Vu+ Zero (MVZ, 12.11.2026): aceeasi imagine mica, aceleasi limite (nucleul 3.13.5, MIPS)
RDEPENDS:${PN}:remove:vuzero = "rt8188fu firmware-rt8188fu ${@' '.join(p for p in d.getVar('HDS_FUNCTII_MIPS_IN_ASTEPTARE').split() if p not in (d.getVar('HDS_FUNCTII_MIPS_PREGATITE') or '').split())}"
RDEPENDS:${PN}:append:vuzero = " hdsatelit-radacina-usb"

# Vu+ 4K (lotul a4-boot, 09.11.2026; lazcengiz, Uno4K SE, asistenta 742005): OpenMultiboot, luat de om din alt feed,
# cere pachetul kernel-module-nandsim, iar feedul nostru nu il avea, deci opkg refuza instalarea. Pe Vu+ 4K (eMMC,
# arhive tar.bz2) OpenMultiboot nu incarca nandsim (il foloseste numai la imaginile UBI de pe NAND), dar dependenta din
# reteta lui e neconditionata. Toate nucleele Vu+ 4K au CONFIG_MTD_NAND_NANDSIM=m (defconfig-urile linux-vuplus 3.14.28,
# 4.1.20, 4.1.45), deci modulul se face oricum (~20 KB) si nu se incarca singur. Masinile sunt numite una cate una, nu
# dupa MACHINE_FEATURES omb: o masina al carei nucleu nu face modulul ar opri constructia imaginii.
RDEPENDS:${PN}:append:vusolo4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuuno4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuuno4kse = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuultimo4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuduo4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuduo4kse = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuzero4k = " kernel-module-nandsim"
# Vu+ Duo 4K Lite (VU1): defconfig_initrd al nucleului lui are CONFIG_MTD_NAND_NANDSIM=m
RDEPENDS:${PN}:append:vuduo4klite = " kernel-module-nandsim"
# GigaBlue UHD Quad 4K Pro (ALFA): defconfig_initrd gb7252 (linux-gigablue 4.1.20) are CONFIG_MTD_NAND_NANDSIM=m
RDEPENDS:${PN}:append:gbquad4kpro = " kernel-module-nandsim"
# GigaBlue UHD X3 4K (MGX): gb72604/defconfig (linux-gigablue 4.1.20) are CONFIG_MTD_NAND_NANDSIM=m
RDEPENDS:${PN}:append:gbx34k = " kernel-module-nandsim"
# Vu+ Duo 4K Lite (VU1): vuplus-ddbootup (meta-vuplusde, numai Recommends acolo) scrie la pornire boxtype, vumodel si
# model (driverul nu le da) si porneste afisajul (lcd/mode 1, /dev/dbox/lcd0); garda de model si afisajul color au nevoie de el
RDEPENDS:${PN}:append:vuduo4klite = " vuplus-ddbootup"

# Vu+ Solo4K, Duo4K, Uno4K SE: stickurile Wi-Fi Ralink (RT2870, RT3070, RT5370, RT5372; Bogdanici13, Vu+ Solo4K, forum
# 1024 si asistenta 694576, 10.11.2026: stickul 148f:5372 se vedea pe USB, dar nu aparea nicio placa Wi-Fi). Nucleele
# Vu+ 4K au CONFIG_RT2800USB=m (inventarul drivere-usb-073), deci modulul rt2800usb si firmware-ul rt*.bin din
# linux-firmware-ralink, ca pe gbtrio4k. PR-ul pachetului de grup creste pe aceste masini: actualizarea din meniu ia numai
# pachetele instalate cu versiune noua (HdsActualizari.planul), deci fara el cine actualizeaza nu primea nici driverul,
# nici kernel-module-nandsim de mai sus.
RDEPENDS:${PN}:append:vusolo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuultimo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuduo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuduo4kse = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuuno4kse = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuzero4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuduo4klite = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:gbquad4kpro = " kernel-module-rt2800usb linux-firmware-ralink"
PR:append:vusolo4k = ".1"
PR:append:vuultimo4k = ".1"
PR:append:vuduo4k = ".1"
PR:append:vuduo4kse = ".1"
PR:append:vuuno4kse = ".1"
PR:append:vuzero4k = ".1"
PR:append:vuduo4klite = ".1"

# Stickuri Wi-Fi USB cu driverul in nucleu si adaptoare de retea USB (cererea din 10.11.2026, treapta A1 din
# lucru-sesiune/oe-60/drivere-usb-073/INVENTAR-DRIVERE.md). Raman in imagine, nu in feed: ele sunt chiar legatura la
# internet, iar omul fara cablu n-ar avea de unde lua driverul. Modulele sunt deja construite de nucleul fiecarei masini
# de mai jos (verificat in tmp/deploy/ipk pe toate, 10.11.2026); udev le incarca singur dupa ID-ul USB cand omul baga
# stickul (80-drivers.rules, modules.alias), iar S05modload.sh la pornire, cand stickul a ramas in mufa. Firmware-ul sta in
# /lib/firmware (linux-firmware impartit, arhitectura all). Dependintele (rt2x00, rtlwifi, ath9k-hw, mac80211, usbnet) vin
# singure din pachetele modulelor. Masinile sunt numite una cate una: o masina al carei nucleu nu face un modul ar opri
# constructia (o masina noua nu primeste lista fara verificare).
# rtl8xxxu nu intra: pe 4.4.35 are 59 de ID-uri USB comune cu rtl8192cu si doua module s-ar lega de acelasi stick.
# Firmware-ul 8188EU nu vine din linux-firmware-rtl8188: acela pune si rtl8188fufw.bin, care e deja in firmware-rt8188fu
# (doua pachete cu acelasi fisier opresc imaginea); el vine mai tarziu, din reteta lui (treapta A2 a inventarului).
HDS_WIFI_USB = "kernel-module-rt2800usb kernel-module-rt73usb kernel-module-rt2500usb kernel-module-rtl8192cu \
    kernel-module-r8188eu kernel-module-r8712u kernel-module-ath9k-htc kernel-module-carl9170 kernel-module-zd1211rw \
    kernel-module-rtl8187 linux-firmware-ralink linux-firmware-rtl8192cu linux-firmware-rtl8192su linux-firmware-ath9k \
    linux-firmware-carl9170"
HDS_RETEA_USB = "kernel-module-r8152 kernel-module-asix kernel-module-cdc-ether kernel-module-cdc-ncm kernel-module-rndis-host \
    kernel-module-smsc95xx kernel-module-dm9601 kernel-module-sr9700"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# Amiko Viper 4K (V10): nucleul face si mt7601u (CONFIG_MT7601U=m), ca familia Octagon
RDEPENDS:${PN}:append:viper4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): asix, cdc-ether, cdc-ncm si dm9601 sunt in nucleu, iar rndis-host,
# smsc95xx si sr9700 lipsesc; dintre adaptoarele de retea ramane numai r8152.
RDEPENDS:${PN}:append:u57 = " ${HDS_WIFI_USB} kernel-module-r8152"
RDEPENDS:${PN}:append:u571 = " ${HDS_WIFI_USB} kernel-module-r8152"
# Vu+ 4K (nucleele Vu+ n-au MT7601U)
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuultimo4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# Vu+ Duo 4K Lite (VU1): toate modulele din cele doua liste sunt =m in defconfig_initrd (meta-vuplusde, 12.11.2026)
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# GigaBlue UHD Quad 4K Pro (ALFA): toate modulele din cele doua liste sunt =m in defconfig_initrd gb7252 (12.11.2026)
RDEPENDS:${PN}:append:gbquad4kpro = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# GigaBlue UHD X3 4K (MGX): toate modulele din cele doua liste sunt =m in gb72604/defconfig (12.11.2026)
RDEPENDS:${PN}:append:gbx34k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# Zgemma H9 COMBO si H9 TWIN (MH9, 12.11.2026; masina h9combo, linux-airdigital 4.4.35): toate modulele din cele doua liste
# sunt =m in linux-airdigital-4.4.35/h9combo/defconfig (OE-Alliance 6.0), plus CONFIG_MT7601U=m, ca pe viper4k
RDEPENDS:${PN}:append:h9combo = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Novaler Multibox 4K PRO (MNP, 12.11.2026; masina multiboxpro, linux-maxytec 4.4.35): toate modulele din cele doua liste
# sunt =m in linux-maxytec-4.4.35/multiboxpro/defconfig (OE-Alliance 6.0), plus CONFIG_MT7601U=m, ca pe viper4k si H9
RDEPENDS:${PN}:append:multiboxpro = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Novaler Multibox 4K SE (MNS, 12.11.2026; masina multiboxse, linux-maxytec 4.4.35): toate modulele din cele doua liste
# sunt =m in linux-maxytec-4.4.35/multiboxse/defconfig (OE-Alliance 6.0; identic cu multiboxpro), plus CONFIG_MT7601U=m
RDEPENDS:${PN}:append:multiboxse = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# AB-COM PULSe 4K si PULSe 4K MINI (MPU, 12.11.2026; linux-abcom 4.4.35): toate modulele din cele doua liste sunt =m in
# linux-abcom-4.4.35/pulse4k/defconfig (acelasi fisier si la pulse4kmini, OE-Alliance 6.0), plus CONFIG_MT7601U=m
RDEPENDS:${PN}:append:pulse4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
RDEPENDS:${PN}:append:pulse4kmini = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Zgemma H9 TWIN SE si H9 COMBO SE (MHS, 12.11.2026; masina h9combose): linux-airdigital-4.4.35/h9combose/defconfig e
# identic cu cel h9combo (diff gol), deci aceleasi liste ca la h9combo
RDEPENDS:${PN}:append:h9combose = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# AX HD51 (MHD, 12.11.2026; masina hd51, MACHINEBUILD ax51, linux-gfutures 4.10.12): toate modulele din cele doua liste sunt
# =m in linux-gfutures-4.10.12/hd51/defconfig (OE-Alliance 6.0), plus CONFIG_MT7601U=m, deci mt7601u din nucleu, ca pe
# viper4k. CONFIG_MTD_NAND_NANDSIM lipseste din defconfig: fara kernel-module-nandsim (ar opri constructia).
RDEPENDS:${PN}:append:ax51 = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Edision OS mio 4K+, OS mini 4K, OS mio 4K (MED, 13.11.2026; linux-edision 5.15): toate modulele din cele doua liste
# sunt =m in defconfig-ul 5.15 (acelasi pe toate trei), plus MT7601U=m (in imagine, ca pe ax51). Firmware-ul
# demodulatoarelor availink (avl62x1, avl68x2) e numai RRECOMMENDS in edision-dvb-modules-<masina>: il cerem
# explicit, fara el tunerele nu pornesc.
RDEPENDS:${PN}:append:osmio4kplus = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u linux-firmware-dvb-fe-avl62x1 linux-firmware-dvb-fe-avl68x2"
RDEPENDS:${PN}:append:osmini4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u linux-firmware-dvb-fe-avl62x1 linux-firmware-dvb-fe-avl68x2"
RDEPENDS:${PN}:append:osmio4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u linux-firmware-dvb-fe-avl62x1 linux-firmware-dvb-fe-avl68x2"
# Wi-Fi-ul intern QCA6174 (OS mio 4K+ si OS mio 4K; OS mini 4K nu are): OE-Alliance il pune prin
# packagegroup-oea-wifi (MACHINEBUILD), pe care nu-l folosim; pachetul lui are numai RRECOMMENDS, deci le cerem pe toate
RDEPENDS:${PN}:append:osmio4kplus = " enigma2-plugin-drivers-network-usb-qca6174 wlan-qcacld-20 firmware-qca6174"
RDEPENDS:${PN}:append:osmio4k = " enigma2-plugin-drivers-network-usb-qca6174 wlan-qcacld-20 firmware-qca6174"
# Zgemma H17 COMBO (MH7, 12.11.2026; masina h17, linux-airdigital 4.10.12): defconfig-ul h17 difera de hd51 numai prin 5
# module HID/serial; toate modulele din cele doua liste sunt =m, plus CONFIG_MT7601U=m (si imaginea publica a masinii are
# mt7601u), fara CONFIG_MTD_NAND_NANDSIM
RDEPENDS:${PN}:append:zgemmah17combo = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Dreambox DM900 si DM920 (MDM dm900 wifi, 12.11.2026; linux-dreambox-3.14/dm900/defconfig si dm920/defconfig, OE-Alliance
# 6.0, la fel in afara de numele masinii): toate modulele din cele doua liste sunt =m (r8152 = CONFIG_USB_RTL8152, asix =
# CONFIG_USB_NET_AX8817X), in afara de ath9k-htc (CONFIG_ATH9K_HTC nesetat), scos mai jos ca sa nu opreasca constructia.
# Fara mt7601u (lipseste din nucleu) si fara HDS_WIFI_VANDUTE: driverele din afara nucleului nu sunt probate pe 3.14
# (raman in feed; imaginile OE-Alliance dm900 au 8812au si 8821au, cu alte retete).
RDEPENDS:${PN}:append:dm900 = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:dm920 = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:remove:dm900 = "kernel-module-ath9k-htc"
RDEPENDS:${PN}:remove:dm920 = "kernel-module-ath9k-htc"
# Vu+ Solo SE (NAND 256 MB, nucleu 3.13.5 fara rtl8192cu): nimic.
# Cine actualizeaza din meniu primeste driverele numai prin pachetul de grup: actualizarea ia numai pachetele instalate
# cu versiune noua (HdsActualizari.planul), iar opkg aduce apoi dependintele lui noi din feed. Deci PR-ul lui
# hdsatelit-base creste pe fiecare masina care primeste lista de mai sus; pe Vu+ 4K peste ".1" din 0.7.3 (rt2800usb),
# deci r0.1.1. Pe Solo SE nu se schimba nimic. Pachetele din liste trebuie culese in feedul fiecarei baze (--cu).
PR:append:sf8008 = ".1"
PR:append:sf8008m = ".1"
PR:append:ustym4kpro = ".1"
PR:append:gbtrio4k = ".1"
PR:append:gbquad4kpro = ".1"
PR:append:gbx34k = ".1"
PR:append:h9combo = ".1"
PR:append:multiboxpro = ".1"
PR:append:multiboxse = ".1"
PR:append:pulse4k = ".1"
PR:append:pulse4kmini = ".1"
PR:append:h9combose = ".1"
PR:append:ax51 = ".1"
PR:append:osmio4kplus = ".1"
PR:append:osmini4k = ".1"
PR:append:osmio4k = ".1"
PR:append:zgemmah17combo = ".1"
PR:append:viper4k = ".1"
PR:append:u57 = ".1"
PR:append:u571 = ".1"
PR:append:vusolo4k = ".1"
PR:append:vuultimo4k = ".1"
PR:append:vuduo4k = ".1"
PR:append:vuduo4kse = ".1"
PR:append:vuuno4kse = ".1"
PR:append:vuzero4k = ".1"
PR:append:vuduo4klite = ".1"

# Imaginea mica (0.7.4, 10.11.2026; PROIECT-IMAGINE-MICA.md, treapta T2, hotararea 3 a coordonatorului): recunoasterea
# textului (hds-ocr si hds-ocr-modele: tesseract, leptonica, modelele celor 8 limbi, ~27 MB necomprimat) nu mai sta in
# imagine pe nicio masina. O foloseste numai traducerea subtitrarilor din imagine (subtitrarile DVB desenate,
# Components/HdsOcrSubtitrari.py); cand omul o porneste, receptorul o instaleaza singur din feed, semnat
# (Components/HdsLimbaRestaurare.py, ceriOcr). Pe hdsflashmic era deja scoasa (mai sus).
RDEPENDS:${PN}:remove = "hds-ocr hds-ocr-modele"

# 0.7.4: pachetul real „enigma2” 2.7+hds1 (hds-enigma2-compat.bb) pentru pluginurile scrise pentru alte imagini, in imagine si
# prin actualizare; Provides-ul enigma2 din enigma2-hdsatelit e scos (vezi reteta). Cerut pe numele retetei, nu pe „enigma2”,
# ca nicio alta reteta numita enigma2 sa nu poata intra. Revizia creste pe toate masinile (.2), ca receptoarele cu 0.7.3 sa ia
# noul hdsatelit-base (si deci pachetul) la actualizare, in aceeasi tranzactie cu enigma2-hdsatelit.
RDEPENDS:${PN}:append = " hds-enigma2-compat"
# 0.7.4, constructia comuna (CB074, 12.11.2026): revizia urca la ".3" pe toate masinile, ca receptoarele care au deja o 0.7.4
# de proba (hdsatelit-base r0.1.2 din constructiile de pe 11.11) sa primeasca prin actualizare driverele Wi-Fi din imagine (WD2) si
# openssl3-compat, venite dupa acele constructii. Pentru 0.7.3 -> 0.7.4 nu schimba nimic (tot mai nou).
PR:append = ".3"

# 0.7.4 (Eduard, 11.11.2026 18:56: „il pui in imagine”): openssl3-compat (recipes-local/openssl3-compat: libssl3 si libcrypto3,
# numai bibliotecile OpenSSL 3.5.9, ~4,3 MB instalati pe ARM, fara fisiere comune cu OpenSSL 4 al imaginii) pe toate masinile,
# pentru modulele si pluginurile altora facute pe OpenSSL 3 (OSCam-ul lui Levi45 si preinst-ul lui, care cauta libssl3 si
# libcrypto3 in /var/lib/opkg/status; forumul nostru 768 #1564, STADIU-P3-LIBSSL3.md). Cerut aici, deci vine si prin
# actualizarea din meniu 0.7.3 -> 0.7.4: PR-ul ".2" de mai sus (pachetul enigma2, tot 0.7.4, nepublicat inca) face
# hdsatelit-base mai nou pe toate masinile, iar opkg aduce openssl3-compat, libssl3 si libcrypto3 din feed in aceeasi
# tranzactie (culegerea feedului 0.7.4 trebuie sa ia hdsatelit-base cu --cu, ca pe hds-enigma2-compat).
RDEPENDS:${PN}:append = " openssl3-compat"

# 0.7.4 (Eduard, 11.11.2026: „decodarea sunetului in software pentru orice receptor care nu poate decoda hardware”): sunetul DAB+
# (AAC cu cadre de 960, HE-AAC) decodat de releul DAB in receptor pe placile care nu-l stiu (Vu+ Broadcom); libfaad2 si twolame
# (~0,38 MB) numai pe aceste masini. Pe HiSilicon decodeaza placa (Hds/DabT2/sunet_software.py, agentul DA).
RDEPENDS:${PN}:append:vuuno4kse = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuzero4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuduo4klite = " libfaad2 twolame"
RDEPENDS:${PN}:append:gbquad4kpro = " libfaad2 twolame"
RDEPENDS:${PN}:append:gbx34k = " libfaad2 twolame"
# AX HD51 (MHD): tot Broadcom (bcm7251s, Nexus), aceeasi cale de sunet ca Vu+ 4K
RDEPENDS:${PN}:append:ax51 = " libfaad2 twolame"
RDEPENDS:${PN}:append:osmio4kplus = " libfaad2 twolame"
RDEPENDS:${PN}:append:osmini4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:osmio4k = " libfaad2 twolame"
# Zgemma H17 COMBO (MH7): tot Broadcom (bcm7251s), aceeasi cale de sunet ca AX HD51
RDEPENDS:${PN}:append:zgemmah17combo = " libfaad2 twolame"
# Dreambox DM900 si DM920 (MDM dm900 sunet): tot Broadcom (bcm7252s), aceeasi cale de sunet DAB+ ca Vu+ 4K
RDEPENDS:${PN}:append:dm900 = " libfaad2 twolame"
RDEPENDS:${PN}:append:dm920 = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuduo4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuduo4kse = " libfaad2 twolame"
RDEPENDS:${PN}:append:vusolo4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuultimo4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:vusolose = " libfaad2 twolame"
# Zgemma Star S (MSS): tot Broadcom (BCM7358), aceeasi cale de sunet DAB+ ca Solo SE
RDEPENDS:${PN}:append:sh1 = " libfaad2 twolame"
RDEPENDS:${PN}:append:vusolo2 = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuduo2 = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuzero = " libfaad2 twolame"

# 0.7.4 (agentul WD, 11.11.2026): r8188eu e in imagine, dar fara firmware-ul lui stickurile RTL8188EUS (foarte raspandite) nu porneau;
# firmware-ul (13 KB, recipes-local/firmware-rtl8188eu) intra acolo unde intra driverele Wi-Fi USB.
HDS_WIFI_USB:append = " firmware-rtl8188eu"

# 0.7.4 (agentul WD2, 12.11.2026; Eduard 04:40, „Both”): omul care are NUMAI un stick Wi-Fi si niciun cablu nu putea lua
# driverul din feed (n-are internet fara el). Driverele stickurilor Wi-Fi 5 (AC) cele mai vandute stau deci in imagine;
# restul raman in feed (hdsatelit-drivere-feed), instalate singure la conectare cand receptorul are internet.
# Ales dupa ID-ul USB din modulele construite (tabela data/hds-drivere-pachete.json), nu dupa numele din cutie (acelasi nume
# de produs are alt cip la alta versiune), si dupa clasamentele magazinelor (STADIU-WD2-DRIVERE-IMAGINE-OFFLINE.md):
#   rtl8821au (RTL8811AU/8821AU, AC600): TP-Link Archer T2U Nano, T2U Plus, T2U, Edimax EW-7811UTC; ~3,1 MB instalat;
#   rtl88x2bu (RTL8812BU/8822BU, AC1300): Archer T3U, T3U Nano, T3U Plus, T4U v3, T4U Plus, Comfast CF-812AC; ~4,3 MB;
#     cere usb-modeswitch (stickurile care pornesc ca CD), fara tcl (recipes-local/usb-modeswitch);
#   rtl88xxau (RTL8812AU, AC1200): Archer T4U v1/v2 si stickurile RTL8812AU fara nume; ~2,9 MB;
#   rt8821cu (RTL8811CU/8821CU, AC600 ieftin): Comfast CF-811AC si multe stickuri fara nume; ~3,4 MB; deja in imagine pe
#     familia Octagon/Uclan/GigaBlue (HDS_WIFI_OCTAGON), aici si pe Viper 4K, V20/V30/Protek, V40 si Vu+ 4K.
# Toate sunt driverele comunitatii din organizatia de drivere, nemodificate, GPL-2.0-only (lista licentelor imaginii le ia
# singura); pe u57/u571 cu -mlong-calls (bbappend-urile lor). Locul: radacinile 0.7.4 masurate pe 11.11 aveau 80-132 MB
# liberi (sf8008 79,6, viper4k 97,3, u57 132,4), driverele iau ~10-14 MB. Nu intra: mt7610u (driverul MediaTek, fisiere
# .dat in /etc/Wireless, neprobat inca cu ecranul Wi-Fi), rtl8852bu (Wi-Fi 6, 6,9 MB, cel mai mare), rt8814au, rtl8192fu,
# rtl8852cu (rare). Masinile sunt numite una cate una, ca mai sus. Revizia: PR-ul ".2" de 0.7.4 (nepublicat inca) ajunge;
# culegerea feedului 0.7.4 ia hdsatelit-base cu --cu, deci si driverele, pentru cine actualizeaza din meniu.
HDS_WIFI_VANDUTE = "rtl8821au rtl88x2bu rtl88xxau usb-modeswitch usb-modeswitch-data"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:viper4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:u57 = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:u571 = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuultimo4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:gbquad4kpro = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:gbx34k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:h9combo = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:multiboxpro = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:multiboxse = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:pulse4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:pulse4kmini = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:h9combose = " ${HDS_WIFI_VANDUTE} rt8821cu"
# AX HD51 (MHD): rtl8821au, rtl88x2bu si rtl88xxau se construiesc pe 4.10.12 (imaginea publica OE-Alliance 6.0 pentru ax51
# are 8812au, 8821au si 8822bu din aceleasi retete, comparatia din STADIU-MHD.md); rt8821cu de probat la constructie
RDEPENDS:${PN}:append:ax51 = " ${HDS_WIFI_VANDUTE} rt8821cu"
# Edision (MED): driverele din afara nucleului pe 5.15 (imaginea publica OE-Alliance 6.0 pentru osmio4kplus are deja
# 8812au si 8821au construite pe 5.15.0); rtl88x2bu si rt8821cu NEINCERCATE pe 5.15 la noi: de urmarit la constructie
RDEPENDS:${PN}:append:osmio4kplus = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:osmini4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:osmio4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
# Zgemma H17 COMBO (MH7): acelasi nucleu 4.10.12 ca AX HD51 (imaginea publica OE-Alliance 6.0 a masinii are si
# rtl8192fu, 8812au, 8821au si 8822bu); rt8821cu de probat la constructie
RDEPENDS:${PN}:append:zgemmah17combo = " ${HDS_WIFI_VANDUTE} rt8821cu"
# Vu+ Solo SE (NAND 256 MB, hotararea lui Eduard din 06.11: imaginea incape in NAND, ce e mare sta in feed; ~72 MiB raman
# omului dupa instalare): numai primul, rtl8821au (Archer T2U Nano / T2U Plus, cele mai ieftine si mai vandute AC600; ~3,2 MB
# necomprimat, mai putin in UBIFS). Celelalte trei ar lua inca ~11 MB din locul omului; raman in feed si in pachetul de
# completari de pe stick. De confirmat de coordonator la constructia comuna (limita 150 MiB, verifica-model-nand-070.py).
RDEPENDS:${PN}:append:vusolose = " rtl8821au"
# Zgemma Star S (MSS): ca Solo SE, numai rtl8821au in imagine (se construieste pe 4.10.12, vezi randul ax51)
RDEPENDS:${PN}:append:sh1 = " rtl8821au"
RDEPENDS:${PN}:append:vusolo2 = " rtl8821au"
RDEPENDS:${PN}:append:vuduo2 = " rtl8821au"
RDEPENDS:${PN}:append:vuzero = " rtl8821au"

# 0.7.5 (DSK, 14.11.2026): ntfs-3g a intrat in hdsatelit-base pe toate masinile (comentariul din hdsatelit-base.bb). Revizia
# urca dupa ".3" din 0.7.4, ca receptoarele cu 0.7.4 sa ia noul hdsatelit-base prin actualizarea din meniu, iar opkg sa aduca
# ntfs-3g si libntfs-3g91 din feed in aceeasi tranzactie (culegerea feedului 0.7.5 ia hdsatelit-base cu dependintele, ca la
# openssl3-compat). Pe masinile cu ".1" propriu (mai sus) revizia devine r0.1.3.1, pe celelalte r0.3.1: amandoua mai noi.
PR:append = ".1"

# 0.7.5 (SER, 15.11.2026; dorinelu, forumul nostru 795, Vu+ Solo4K: "modprobe: FATAL: Module ftdi_sio not found in directory
# /lib/modules/3.14.28-1.8", deci nici /dev/ttyUSB0): adaptoarele seriale USB (FTDI, Prolific PL2303, Silicon Labs CP210x,
# WCH CH340/CH341) si placile CDC-ACM (Arduino Uno/Mega, /dev/ttyACM0) pornesc singure in imagine, fara internet.
# Modulele sunt deja construite de nucleul fiecarei masini de mai jos (=m: modules.order din rootfs-ul imaginilor 0.7.5
# publicate, citit cu unelte/stb/module_nucleu_imagini.py; tabelul in runda-0013/STADIU-SER.md), numai ca nu intrau in imagine;
# nucleul nu se schimba. udev le incarca singur dupa ID-ul USB cand omul baga adaptorul (80-drivers.rules, modules.alias),
# S05modload.sh la pornire, iar 60-serial.rules (eudev, deja in imagine) face /dev/serial/by-id si by-path. usbserial vine
# si singur, ca dependinta, aici e scris pentru claritate. ~0,2 MB instalati. Masinile sunt numite una cate una, ca mai sus:
# o masina noua primeste lista numai dupa module_nucleu_imagini.py pe prima ei imagine (pe cele neconstruite inca, ca
# h9combo, multiboxpro, sh1, vusolo2, vuduo2, vuzero, dm900, nu e verificat).
HDS_SERIAL_USB = "kernel-module-usbserial kernel-module-ftdi-sio kernel-module-pl2303 kernel-module-cp210x \
    kernel-module-ch341 kernel-module-cdc-acm"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:viper4k = " ${HDS_SERIAL_USB}"
# Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): verificat pe toate patru
RDEPENDS:${PN}:append:u57 = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:u571 = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vuultimo4k = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vuduo4kse = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vuzero4k = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:gbquad4kpro = " ${HDS_SERIAL_USB}"
RDEPENDS:${PN}:append:ax51 = " ${HDS_SERIAL_USB}"
# Vu+ Solo SE (3.13.5, NAND): ~0,2 MB din ~9 MiB ramasi sub limita de 150 MiB (root_cfe_auto.bin 0.7.5: 141 MiB)
RDEPENDS:${PN}:append:vusolose = " ${HDS_SERIAL_USB}"

# 0.7.5 (SER, 15.11.2026; JAKITAKI, forumul nostru 787, Vu+ Zero4K): comanda blockdev (util-linux-blockdev, ~30 KB), ceruta de
# pluginurile de pornire multipla (MOH Boot o cere ca dependinta). util-linux 2.42.4 e deja construit pe toate arhitecturile
# (util-linux-blkid, -sfdisk, -flock sunt in imagine), deci pe toate masinile, fara override. busybox nu are blockdev la noi.
RDEPENDS:${PN}:append = " util-linux-blockdev"

# Revizia urca dupa ".1" de la DSK (0.7.5), ca receptoarele cu 0.7.4 si 0.7.5 sa ia noul hdsatelit-base prin actualizarea din meniu,
# iar opkg sa aduca modulele seriale si util-linux-blockdev din feed in aceeasi tranzactie (culegerea ia hdsatelit-base cu
# dependintele lui). Pe masinile cu ".1" propriu devine r0.1.3.1.1, pe celelalte r0.3.1.1: amandoua mai noi.
PR:append = ".1"


# 0.7.5 (MA8, 15.11.2026; TODO 05.11 14:43): egalizatorul (lib/service/hdsegalizator.cpp) decodeaza posturile AAC prin elementul
# GStreamer faad, care nu era in imagine: la orice post AAC egalizatorul spunea ca nu e disponibil si sunetul ramanea pe placa.
# gstreamer1.0-plugins-bad-faad (~30 KB, GPL-2.0, recipes-local/gstreamer/gstreamer1.0-plugins-bad_%.bbappend) intra NUMAI pe
# masinile care au deja libfaad2 pentru DAB+ (aceeasi lista ca mai sus), deci nicio biblioteca noua de decodare pe receptor.
# Posturile cu HE-AAC semnalat (SBR/PS in configuratia LATM) le refuza motorul si raman pe placa (aprobarea din 28.09.2026 e numai
# pentru AAC-LC); restul masinilor (HiSilicon) raman fara faad pana hotaraste Eduard (runda-0013/STADIU-MA8.md).
RDEPENDS:${PN}:append:vuuno4kse = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuzero4k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuduo4klite = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:gbquad4kpro = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:gbx34k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:ax51 = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:osmio4kplus = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:osmini4k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:osmio4k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:zgemmah17combo = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:dm900 = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:dm920 = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuduo4k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuduo4kse = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vusolo4k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuultimo4k = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vusolose = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:sh1 = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vusolo2 = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuduo2 = " gstreamer1.0-plugins-bad-faad"
RDEPENDS:${PN}:append:vuzero = " gstreamer1.0-plugins-bad-faad"
# Revizia urca peste ".1" de la SER, ca receptoarele de mai sus sa ia pluginul prin actualizarea din meniu.
PR:append = ".1"

# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Driver Wi-Fi USB din feed (hdsatelit-drivere-feed, 11.11.2026, agentul WD), instalat singur cand omul baga stickul.
# Amiko Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): modulul cu -mlong-calls, ca modulele nucleului (motivul in
# dinobot-kernel/linux-dinobot_%.bbappend: zona modulelor e la 32,25 MB de capatul codului nucleului; un modul care
# nimereste la inceputul ei cade cu "relocation out of range"). Driverul e din afara nucleului, deci KCFLAGS (din
# kcflags.inc, dat lui make prin mediu) atinge numai modulul. Pe celelalte masini reteta ramane neschimbata.
KCFLAGS:append:u57 = " -mlong-calls"
KCFLAGS:append:u571 = " -mlong-calls"

# ZER1: fara depanare in driverul Wi-Fi livrat.
PR:append = ".hdszer1"
EXTRA_OEMAKE:append = " CONFIG_RTW_DEBUG=n"

# WPS6 (asistenta 906594, Octagon SF8008 V3): economia de energie oprita prin optiunile modulului, scrise de
# kernel-module-split in /etc/modprobe.d/88x2cu.conf (pachetul kernel-module-88x2cu). Numele din sursa driverului
# (oe-alliance-drivers/rtl8822cu, os_intfs.c: module_param rtw_power_mgnt, rtw_ips_mode, rtw_enusbss): 0 = PS_MODE_ACTIVE,
# IPS_NONE, fara autosuspend USB. Azi sunt si valorile compilate (Makefile: CONFIG_IPS_MODE = 0, CONFIG_LPS_MODE = 0),
# dar reteta OE-Alliance ia SRCREV ${AUTOREV}: optiunile le tin oprite oricum s-ar schimba sursa.
KERNEL_MODULE_PROBECONF += "88x2cu"
module_conf_88x2cu = "options 88x2cu rtw_power_mgnt=0 rtw_ips_mode=0 rtw_enusbss=0"
PR:append = ".wps6"

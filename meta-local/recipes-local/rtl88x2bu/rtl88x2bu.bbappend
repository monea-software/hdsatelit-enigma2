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

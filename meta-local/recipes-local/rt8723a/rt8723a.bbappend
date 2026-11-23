# Copyright (C) 2026 moneasoftware.com & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# ZER1: acest driver vechi foloseste DBG direct, nu CONFIG_RTW_DEBUG.
PR:append = ".hdszer1"
do_configure:append() {
    sed -i -e 's/^#define DBG[[:space:]]*1$/#define DBG 0/' -e '/^#define CONFIG_DEBUG[[:space:]]/d' ${S}/include/autoconf.h
    if grep -Eq '^#define DBG[[:space:]]+1|^#define CONFIG_DEBUG([[:space:]]|$)' ${S}/include/autoconf.h; then
        bbfatal "Depanarea rt8723a a ramas activa"
    fi
}

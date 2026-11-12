# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Amiko Viper 4K V20, V30, Protek 4K X2 (u57) si Viper 4K V40 (u571), nucleul dinobot 4.4.35: modulele nucleului
# facute cu -mlong-calls, ca sa se incarce oriunde ar cadea in zona modulelor (11.11.2026, agentul MOD).
#
# De ce: patch-ul dinobot muta zona modulelor la PAGE_OFFSET - 24 MB (arch/arm/include/asm/memory.h), iar codul
# nucleului se termina la 0xc0840bac, deci la 32,25 MB de inceputul zonei (0xbe800000). Un salt direct ARM (BL, B)
# ajunge numai la +-32 MB, iar CONFIG_ARM_MODULE_PLTS e oprit. Un modul incarcat in primii ~265 KB ai zonei nu ajunge
# la functiile de la capatul codului (_raw_spin_lock*, mutex_lock, schedule*: .sched.text si .spinlock.text) si cade
# la insmod cu "relocation 28 out of range" ("Invalid module format"). Vazut pe .122 (V20), 11.11.2026: ppp_generic.ko
# din imagine; dupa verifica-salturi-imagine.py, pe u57 sunt 122 de module in pericol, 53 in imagine (tun, cfg80211,
# mac80211, toate driverele Wi-Fi USB, r8152 ...). Pe celelalte modele distanta e sub 32 MB (sigur).
#
# De ce nu ARM_MODULE_PLTS (solutia nucleului): adauga campuri in struct mod_arch_specific, care sta in struct module;
# driverele placii (dinobot-dvb-modules: hi_*.ko, mali.ko) sunt BINARE, facute pe struct module de acum, deci n-ar mai
# porni, iar nucleul ar trebui scris din nou pe receptoare.
#
# Cum: CFLAGS_MODULE pe linia de comanda a lui make. Kbuild 4.4 (scripts/Makefile.build, modkern_cflags) il pune NUMAI
# pe obiectele modulelor; codul nucleului (vmlinux, uImage) se compileaza cu CFLAGS_KERNEL, deci ramane acelasi.
# NU KCFLAGS: acela intra si in vmlinux. Vermagic-ul nu se schimba ("4.4.35 SMP mod_unload ARMv7 p2v8").
# -mlong-calls: apelurile spre functii trec prin adresa intreaga (fara limita de 32 MB). Raman BL numai din asm-ul
# scris de mana in antete (ex. __get_user_*), pe care verifica-salturi-module.py le verifica unul cate unul.
#
# PR cu ".hds1" (numai pe u57/u571), dat prin MACHINE_KERNEL_PR: machine_kernel_pr.bbclass scrie PR din el si ar
# sterge un PR:append. Pachetele kernel-module-* noi trec peste cele din 0.7.3 la Actualizare software.
# kernel-image-uimage primeste si el versiunea noua, dar pachetul numai pune uImage in /tmp (postinst: ln -sf), nu
# scrie nucleul pe receptor.

KERNEL_EXTRA_ARGS:append:u57 = " CFLAGS_MODULE=-mlong-calls"
KERNEL_EXTRA_ARGS:append:u571 = " CFLAGS_MODULE=-mlong-calls"
MACHINE_KERNEL_PR:append:u57 = ".hds1"
MACHINE_KERNEL_PR:append:u571 = ".hds1"

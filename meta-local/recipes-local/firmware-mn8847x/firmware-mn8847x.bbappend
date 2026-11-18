# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# firmware-mn8847x: firmware-ul demodulatoarelor Panasonic MN88472/MN88473, cerut de tunerul USB Xbox One Digital TV Tuner
# (045e:02d5; mn88472.ko cere /lib/firmware/dvb-demod-mn88472-02.fw la fiecare acord). Hotararea lui Eduard (16.11.2026,
# 07:06): il punem in feed si in imagine, cum fac celelalte imagini Enigma2 (agentul FWX).
#
# Reteta e cea OE-Alliance, neschimbata (meta-oe/recipes-kernel/linux-firmwares/firmware-mn8847x.bb, fisierul mn8847x.zip din
# strat); imaginile facute pe OE-Alliance dau acelasi pachet, cu acelasi continut, recomandat de invelisul lor dib0700. Licenta
# ramane cea OE-Alliance (license-close.inc, LicenseRef-Proprietary): nimeni nu da o nota care sa permita redistribuirea
# (fisierul e scos din driverele Windows ale stickurilor Astrometa si nu e in linux-firmware), deci nu avem ce text sa punem
# langa el.
#
# Aici numai suma de control: SRC_URI e un file:// din strat, fara suma, deci dupa do_install se verifica sha256 al fiecarui
# fisier pus in /lib/firmware; alt continut sau alt fisier opreste constructia. dvb-demod-mn88472-02.fw = versiunea 2015
# (driverul Windows 151102), md5 088b891ac9273ff8c6818fca27b24d81, aceeasi cu "latest" de la autorul driverului Linux.
# PR cu ".hds1", ca pachetul construit de noi sa se vada in manifest si in "opkg list-installed".
HDS_MN8847X_SUME = "\
    dvb-demod-mn88472-02.fw:7c5f7cd2675d0c69cae61bc4f0a442d9a0f7907fdc16fbd4c2ca34ab6c8cb94e \
    dvb-demod-mn88473-01.fw:3a9efa01ee9a5a3d05b94c72c93423f647cc2697e597270a019bb643f9f9a3ed \
    mn88472.fw:42845f794903eed6a4fd2c5628655dd258cac1c99cc9ba83af5f0adb575d9e19 \
    mn88473.fw:3a9efa01ee9a5a3d05b94c72c93423f647cc2697e597270a019bb643f9f9a3ed \
"

python hds_mn8847x_suma() {
    import hashlib
    import os
    asteptate = dict(x.split(":", 1) for x in (d.getVar("HDS_MN8847X_SUME") or "").split())
    dosar = d.getVar("D") + d.getVar("nonarch_base_libdir") + "/firmware"
    gasite = sorted(os.listdir(dosar)) if os.path.isdir(dosar) else []
    if gasite != sorted(asteptate):
        bb.fatal("firmware-mn8847x: in %s sunt %s, asteptate %s" % (dosar, gasite, sorted(asteptate)))
    for nume, suma in sorted(asteptate.items()):
        with open(os.path.join(dosar, nume), "rb") as f:
            gasita = hashlib.sha256(f.read()).hexdigest()
        if gasita != suma:
            bb.fatal("firmware-mn8847x: %s are sha256 %s, nu %s (alt fisier in mn8847x.zip)" % (nume, gasita, suma))
    bb.note("firmware-mn8847x: %d fisiere cu suma buna" % len(asteptate))
}
do_install[postfuncs] += "hds_mn8847x_suma"
do_install[vardeps] += "HDS_MN8847X_SUME"

PR:append = ".hds1"

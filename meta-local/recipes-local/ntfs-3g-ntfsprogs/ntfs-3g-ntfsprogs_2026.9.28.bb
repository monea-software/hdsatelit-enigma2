# Reteta copiata din meta-oe-alliance, meta-oe/recipes-filesystems/ntfs-3g-ntfsprogs/ntfs-3g-ntfsprogs_2022.10.3.bb
# (ramane sub licenta stratului meta-oe-alliance), adusa la ntfs-3g 2026.9.28.
# Repara depasirile de memorie din libntfs-3g, la care ajunge orice stick sau disc NTFS montat automat (ca root):
# CVE-2026-42616, CVE-2026-42617, CVE-2026-42618, CVE-2026-46569, CVE-2026-46570, CVE-2026-46571, CVE-2026-46572,
# CVE-2026-56135 si CVE-2026-56136 (2026.7.7), inca opt depasiri de memorie (2026.9.18, versiune de securitate) si o
# regresie adusa de 2026.9.18 (2026.9.28).
# Sursa se ia prin git de la depozitul autorilor de pe GitHub, nu arhiva de pe tuxera.com: certificatul TLS al
# tuxera.com a expirat si fetcher-ul refuza descarcarea. Identitatea sursei o da comiterea etichetei 2026.9.28
# (SRCREV, eticheta simpla, verificata cu git ls-remote); fetcher-ul verifica si ca eticheta duce la aceeasi comitere.
# Arhiva oficiala 2026.9.28 (sha256 350d9415c59f7c3fa74e23985ad2d56423c6a168337368f672e2e362d8f295c8, egal cu cel din
# anuntul versiunii de pe GitHub) a fost verificata separat. Sursa din git n-are configure gata facut; il face
# autoreconf din autotools.bbclass. S ramane cel implicit (${UNPACKDIR}/${BP}, unde despacheteaza fetcher-ul git).
# Schimbari fata de original:
# - SRC_URI prin git cu SRCREV, fara S, cu verificarea versiunilor noi pe etichetele git;
# - fara 0001-unistr.c-Fix-use-after-free-in-ntfs_uppercase_mbs.patch: reparatia e deja in sursa;
# - files/0001-libntfs-3g-Makefile.am-fix-install-failed-while-host.patch e copiat din meta-oe-alliance (se aplica).
# Bbappend-urile ntfs-3g-ntfsprogs_%.bbappend (meta-oe-alliance si al nostru, din acest dosar) se aplica neschimbate.

DESCRIPTION = "The NTFS-3G driver is an open source, freely available NTFS driver for Linux with read and write support."
HOMEPAGE = "http://www.ntfs-3g.org/"
DEPENDS = "fuse libgcrypt"
PROVIDES = "ntfsprogs ntfs-3g"
LICENSE = "GPL-2.0-only & LGPL-2.0-only"
LIC_FILES_CHKSUM = "file://COPYING;md5=59530bdf33659b29e73d4adb9f9f6552 \
                    file://COPYING.LIB;md5=f30a9716ef3762e3467a2f62bf790f0a"

SRC_URI = "git://github.com/tuxera/ntfs-3g;protocol=https;branch=edge;tag=${PV} \
           file://0001-libntfs-3g-Makefile.am-fix-install-failed-while-host.patch \
"
SRCREV = "7f0f841fc52cf719106c5c93bafe465004e36816"

UPSTREAM_CHECK_GITTAGREGEX = "(?P<pver>\d+(\.\d+)+)"

inherit autotools pkgconfig

PACKAGECONFIG ??= ""
PACKAGECONFIG[uuid] = "--with-uuid,--without-uuid,util-linux"

# required or it calls ldconfig at install step
EXTRA_OEMAKE = "LDCONFIG=echo"

PACKAGES =+ "ntfs-3g ntfsprogs libntfs-3g"

FILES:ntfs-3g = "${base_sbindir}/*.ntfs-3g ${bindir}/ntfs-3g* ${base_sbindir}/mount.ntfs"
RDEPENDS:ntfs-3g += "fuse"
RRECOMMENDS:ntfs-3g = "util-linux-mount"

FILES:ntfsprogs = "${base_sbindir}/* ${bindir}/* ${sbindir}/*"
FILES:libntfs-3g = "${libdir}/*${SOLIBS}"

do_install:append() {
    # Standard mount will execute the program /sbin/mount.TYPE when called.
    # Add a symbolic link to let mount find ntfs.
    ln -sf mount.ntfs-3g ${D}${base_sbindir}/mount.ntfs
    rmdir ${D}${libdir}/ntfs-3g

    # Handle when usrmerge is in effect. Some files are installed to /sbin
    # regardless of the value of ${base_sbindir}.
    if [ "${base_sbindir}" != /sbin ] && [ -d ${D}/sbin ]; then
        mkdir -p ${D}${base_sbindir}
        mv ${D}/sbin/* ${D}${base_sbindir}
        rmdir ${D}/sbin
    fi
}

# Satisfy the -dev runtime dependency
ALLOW_EMPTY:${PN} = "1"

CVE_PRODUCT = "tuxera:ntfs-3g"

# HD Satelit: keep the kexec loader when updating a running slot.
# OE-Alliance 4.1.45 installs /tmp/zImage; normal flash updates stay upstream.
MACHINE_KERNEL_PR:append = ".hds1"

# XBS8 (22.11.2026): mn88472 (tunerul USB Xbox One DVB-T2) da puterea, CNR si erorile prin DTV_STAT_*, ca in Linux 4.12;
# acelasi petic ca la 4.1.20 (linux-vuplus_4.1.20.bbappend, acolo explicatia). Numai modulul mn88472.ko se schimba;
# PKGR-ul lui trece peste cel al nucleului (rN.hds1 -> rN.hds1.hds1), kernel-image nu primeste versiune noua.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://mn88472-dvbv5-statistici.patch"
# CST8 (22.11.2026): PKGR pe un pachet facut abia la impachetare (kernel-module-*, din PACKAGES_DYNAMIC) nu intra in
# semnatura sarcinilor, deci un sstate mai vechi cu acelasi petic (constructia de proba XBS8) da pachetul fara .hds1
# (masurat: kernel-module-mn88472-4.1.20-1.9_4.1.20-r12.rginput1). Variabila de mai jos il pune in semnatura lui do_package.
HDS_MN88472_PKGR = "hds1"
do_package[vardeps] += "HDS_MN88472_PKGR"
PKGR:kernel-module-mn88472-4.1.45-1.17 = "${PR}.${HDS_MN88472_PKGR}"

pkg_postinst:kernel-image:prepend() {
    # An offline rootfs must not inspect or change the build host.
    if [ -n "$D" ] || [ ! -d /proc/stb ]; then
        exit 0
    fi
    if [ ! -r /proc/cmdline ]; then
        exit 1
    fi
    HDS_KERNEL_ARGS=$(cat /proc/cmdline) || exit 1
    HDS_KERNEL_KEXEC=0
    HDS_KERNEL_ROOT=
    HDS_KERNEL_PATH=
    HDS_KERNEL_SUBDIR=
    for HDS_KERNEL_ARG in $HDS_KERNEL_ARGS; do
        case "$HDS_KERNEL_ARG" in
            kexec=1) HDS_KERNEL_KEXEC=1 ;;
            root=*) HDS_KERNEL_ROOT="${HDS_KERNEL_ARG#root=}" ;;
            kernel=*) HDS_KERNEL_PATH="${HDS_KERNEL_ARG#kernel=}" ;;
            rootsubdir=*) HDS_KERNEL_SUBDIR="${HDS_KERNEL_ARG#rootsubdir=}" ;;
        esac
    done

    if [ "$HDS_KERNEL_KEXEC" = 1 ]; then
        # Both recovery and a subdirectory slot expose their kernel as /zImage.
        case "$HDS_KERNEL_PATH" in
            /zImage|zImage) ;;
            *)
                if [ -z "$HDS_KERNEL_SUBDIR" ] || {
                    [ "$HDS_KERNEL_PATH" != "$HDS_KERNEL_SUBDIR/zImage" ] &&
                    [ "$HDS_KERNEL_PATH" != "/$HDS_KERNEL_SUBDIR/zImage" ];
                }; then
                    exit 1
                fi
                ;;
        esac
        if [ -d /zImage ] || [ -L /zImage ]; then
            exit 1
        fi
        # A failed copy must leave the old slot kernel and package source intact.
        HDS_KERNEL_NEW=$(mktemp /zImage.hds.XXXXXX) || exit 1
        if ! cp -f /${KERNEL_IMAGEDEST}/${KERNEL_IMAGETYPE} "$HDS_KERNEL_NEW" ||
           ! mv -f "$HDS_KERNEL_NEW" /zImage; then
            rm -f "$HDS_KERNEL_NEW"
            exit 1
        fi
        rm -f /${KERNEL_IMAGEDEST}/${KERNEL_IMAGETYPE} || exit 1
        exit 0
    fi

    # USB roots may update an existing kernel file, never the flash fallback.
    HDS_KERNEL_DEVICE="$HDS_KERNEL_ROOT"
    case "$HDS_KERNEL_DEVICE" in
        UUID=*)
            HDS_KERNEL_DEVICE=$(blkid | awk -v uuid="${HDS_KERNEL_ROOT#UUID=}" '
                index($0, " UUID=\"" uuid "\"") { sub(/:$/, "", $1); print $1; exit }
            ')
            ;;
    esac
    case "$HDS_KERNEL_DEVICE" in
        /dev/mmcblk*) ;;
        /dev/*)
            HDS_KERNEL_MOUNT=$(awk -v dev="$HDS_KERNEL_DEVICE" '
                $1 == dev { print $2; exit }
            ' /proc/mounts)
            if [ -z "$HDS_KERNEL_MOUNT" ] || [ -z "$HDS_KERNEL_PATH" ] ||
               [ ! -f "$HDS_KERNEL_MOUNT/$HDS_KERNEL_PATH" ]; then
                exit 1
            fi
            # Publish only a complete copy on the destination filesystem.
            HDS_KERNEL_NEW=$(mktemp "$HDS_KERNEL_MOUNT/$HDS_KERNEL_PATH.hds.XXXXXX") || exit 1
            if ! cp -f /${KERNEL_IMAGEDEST}/${KERNEL_IMAGETYPE} "$HDS_KERNEL_NEW" ||
               ! mv -f "$HDS_KERNEL_NEW" "$HDS_KERNEL_MOUNT/$HDS_KERNEL_PATH"; then
                rm -f "$HDS_KERNEL_NEW"
                exit 1
            fi
            rm -f /${KERNEL_IMAGEDEST}/${KERNEL_IMAGETYPE} || exit 1
            exit 0
            ;;
        *) exit 1 ;;
    esac
    # Do not inherit these runtime variables from the package manager's caller.
    ROOT_DEST=
    KERNEL_DEST=
}

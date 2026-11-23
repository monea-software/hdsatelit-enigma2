PR:append = ".hds1"

do_install:append() {
    if [ ! -e "${D}${prefix}/softcams" ] && [ ! -L "${D}${prefix}/softcams" ]; then
        install -d -m 0755 "${D}${prefix}/softcams"
    fi
}

FILES:${PN}:append = " ${prefix}/softcams"

# Opkg sterge si legaturile din manifest; pastram intrarile locale la remove.
pkg_prerm:${PN}:append() {
    if [ "$1" = "remove" ] && { [ -L "$D${prefix}/softcams" ] || { [ -e "$D${prefix}/softcams" ] && [ ! -d "$D${prefix}/softcams" ]; }; }; then
        hds_softcams_salvat="$D${localstatedir}/lib/hdsatelit/base-files-softcams"
        if [ -e "$hds_softcams_salvat" ] || [ -L "$hds_softcams_salvat" ]; then
            exit 1
        fi
        mkdir -p "$D${localstatedir}/lib/hdsatelit"
        mv -T -n "$D${prefix}/softcams" "$hds_softcams_salvat" || exit 1
        if [ -e "$D${prefix}/softcams" ] || [ -L "$D${prefix}/softcams" ]; then
            exit 1
        fi
    fi
}

pkg_postrm:${PN}:append() {
    hds_softcams_salvat="$D${localstatedir}/lib/hdsatelit/base-files-softcams"
    if [ "$1" = "remove" ] && { [ -e "$hds_softcams_salvat" ] || [ -L "$hds_softcams_salvat" ]; }; then
        if [ ! -e "$D${prefix}/softcams" ] && [ ! -L "$D${prefix}/softcams" ]; then
            mkdir -p "$D${prefix}"
            mv -T -n "$hds_softcams_salvat" "$D${prefix}/softcams" || exit 1
        fi
    fi
}

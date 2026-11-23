# HD Satelit: Uno4K metadata for the frozen 0.7.7 Python backend.
# These capabilities come from the Uno4K BSP, without importing another image's Python.
# Do not write model/brand/imagedir: preserve the base image's branding and flash policy.
hds_uno4k_boxinfo() {
    f="${IMAGE_ROOTFS}${libdir}/enigma.info"
    test -f "$f" || bbfatal "Uno4K: enigma.info missing"
    sed -i -e '/^checksum=/d' -e '/^\(rcname\|rc_model\|socfamily\|hdmi\|ci\|transcoding\)=/d' "$f"
    printf '%s\n' "rcname='${RCNAME}'" "rc_model='${RCNAME}'" "socfamily='${SOC_FAMILY}'" \
        "hdmi=True" "ci=True" "transcoding=True" >> "$f"
    printf 'checksum=%s\n' "$(md5sum < "$f" | cut -d' ' -f1)" >> "$f"
}
ROOTFS_POSTPROCESS_COMMAND:append:vuuno4k = " hds_uno4k_boxinfo "

# HD Satelit (V21B, 14.11.2026): Dreambox DM8000HD si DM800SE, sistemul pe stick cu pornirea mica in memoria interna.
# 1. Linia nucleului din autoexec.bat (reteta OE-Alliance o alege dupa IMAGE_FSTYPES, care difera intre HDS_VARIANTA=usb,
#    unde e tar.bz2, si constructia NAND): fixata pe jffs2, numai citire (hds-pornire-stick nu scrie in memoria interna),
#    fara autosuspend USB (stickul tine radacina). La dm8000 initramfs-ul OE-Alliance din nucleu citeste root= si rootfstype=.
# 2. kernel-image nu mai monteaza si nu mai scrie partitia boot din memoria interna la instalare sau actualizare (pe aceste
#    masini sistemul de pe stick are pachetul numai ca evidenta): REGULI-FLASH-RECEPTOR, nicio scriere in memoria interna
#    din sistemul pornit. Nucleul se schimba numai cu un .nfi nou al pornirii mici, din modul de salvare.
# Celelalte masini (dm7020hd si restul) raman neatinse: totul e sub :dm8000 / :dm800se.
CMDLINE:dm8000 = "root=/dev/mtdblock3 rootfstype=jffs2 ro usbcore.autosuspend=-1 ${CMDLINE_CONSOLE}"
CMDLINE:dm800se = "root=/dev/mtdblock3 rootfstype=jffs2 ro usbcore.autosuspend=-1 ${CMDLINE_CONSOLE}"

pkg_preinst:kernel-image:dm8000() {
:
}
pkg_prerm:kernel-image:dm8000() {
:
}
pkg_postinst:kernel-image:dm8000() {
:
}
pkg_postrm:kernel-image:dm8000() {
:
}
pkg_preinst:kernel-image:dm800se() {
:
}
pkg_prerm:kernel-image:dm800se() {
:
}
pkg_postinst:kernel-image:dm800se() {
:
}
pkg_postrm:kernel-image:dm800se() {
:
}

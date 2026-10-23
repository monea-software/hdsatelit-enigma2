# HDSatelit, 23.09.2026: scriptul flash-apploader scos din imagine.
#
# De ce: pachetul dinobot-partitions-hisi3798mv200 (meta-dinobot, adus de masina prin
# MACHINE_ESSENTIAL_EXTRA_RDEPENDS din dinobot-oem.inc) pune /etc/init.d/flash-apploader, pornit la fiecare
# pornire (S90). Scriptul compara primii 4 MiB din partitia "loader" (p7, actualizatorul Amiko, adica
# Maintenance Mode) cu /usr/share/apploader.bin si, daca difera sau daca citirea din p7 cade, rescrie p7 cu dd.
# p7 e plasa noastra de siguranta: pe 23.09.2026 receptorul a fost reparat numai prin Maintenance Mode.
# Imaginea noastra nu trebuie sa poata scrie p7 niciodata.
#
# Ce face acest fisier:
#  - INHIBIT_UPDATERCD_BBCLASS: fara postinst/prerm/postrm de update-rc.d, deci fara legatura
#    /etc/rcS.d/S90flash-apploader in imagine;
#  - scriptul se sterge din ${D} dupa instalarea facuta de reteta comuna (fisier comun, citit doar pentru
#    intelegere, nimic copiat); daca in pachet ramane altceva decat
#    /usr/share/apploader.bin (de exemplu scriptul redenumit sau mutat de o versiune noua a retetei comune),
#    compilarea se opreste cu eroare;
#  - /usr/share/apploader.bin ramane (fisier de date, 7,7 MB, nu scrie nimic singur); pachetul ramane si el,
#    ca dependinta ceruta de masina sa fie satisfacuta;
#  - PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed" pe receptor.

PR:append = ".hds1"

INHIBIT_UPDATERCD_BBCLASS = "1"

do_install:append() {
    rm -f ${D}${sysconfdir}/init.d/flash-apploader
    rmdir ${D}${sysconfdir}/init.d ${D}${sysconfdir} 2>/dev/null || true
    # Paza: in pachet trebuie sa ramana un singur fisier, /usr/share/apploader.bin.
    rest=$(find ${D} ! -type d ! -path ${D}/usr/share/apploader.bin)
    if [ -n "$rest" ]; then
        bbfatal "HDSatelit: in pachet a ramas altceva decat /usr/share/apploader.bin: $rest"
    fi
}

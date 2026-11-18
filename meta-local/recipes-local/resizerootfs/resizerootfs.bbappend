# HDSatelit (H51, 16.11.2026): pe AX HD51 / Mut@nt HD51 (masina hd51) /etc/init.d/resizerootfs nu mai formateaza partitia
# userdata la pornire.
#
# De ce: scriptul OE-Alliance (meta-gfutures/recipes-bsp/resizerootfs/resizerootfs, din 15.04.2019; acelasi in toate imaginile
# OE-A pe hd51) ruleaza la prima pornire a fiecarei imagini (S07). Daca `blkid /dev/block/by-name/userdata | grep "ext4"` nu
# gaseste "ext4" (partitie fara sistem de fisiere, alt sistem, blkid care nu raspunde), ruleaza
# `mkfs.ext4 -F /dev/block/by-name/userdata`. Pe HD51 userdata (p8) tine locurile de pornire 2, 3 si 4 (subdosarele
# linuxrootfs2-4, clasa hdemmc_image_multiboot), deci o formatare le sterge pe toate trei. Cand imaginea porneste din locurile
# 2-4, userdata e montata si, dupa sursa e2fsprogs (misc/util.c, check_mount: un singur -F nu trece de o partitie montata sau
# ocupata), mke2fs refuza (neprobat pe receptor); cand porneste din locul 1 (linuxrootfs, p3), userdata nu e montata si
# formatarea trece. Imaginea noastra nu foloseste userdata pentru nimic altceva, iar programul de scriere a imaginilor
# (OE-Alliance, ofgwrite.c, montarea care cade cu EINVAL) formateaza singur userdata cand scrie un loc pe o partitie
# neformatata, deci formatarea de la pornire nu e necesara. Gasit cand un tester a crezut ca scrierea in locul 4 i-a sters
# celelalte imagini (LinuxSat 164155 #970694/#970733; runda-0013/STADIU-H51.md).
#
# Cum: numai pe hd51. In fisierul instalat de reteta comuna (citit doar pentru intelegere, nimic copiat)
# se sterge randul care anunta formatarea, iar randul mkfs devine un mesaj; redimensionarea (resize2fs) cand
# userdata e ext4 ramane neschimbata. Compilarea se opreste cu eroare, nu trece tacut, daca randurile nu sunt gasite exact o
# data sau daca dupa schimbare mai ramane vreun mkfs.
# PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed" pe receptor.

PR:append:hd51 = ".hds1"

do_install:append:hd51() {
    f=${D}${sysconfdir}/init.d/resizerootfs
    if [ "$(grep -c '^ *mkfs.ext4 -F /dev/block/by-name/userdata$' $f)" != "1" ]; then
        bbfatal "HDSatelit: resizerootfs nu are exact o data randul mkfs.ext4 pe userdata (reteta comuna s-a schimbat)"
    fi
    if [ "$(grep -c 'Setup userdata partitions' $f)" != "1" ]; then
        bbfatal "HDSatelit: resizerootfs nu are exact o data randul Setup userdata partitions"
    fi
    sed -i '/Setup userdata partitions/d' $f
    sed -i 's|^\( *\)mkfs.ext4 -F /dev/block/by-name/userdata$|\1echo "userdata is not formatted at start: it holds the images of slots 2, 3 and 4"|' $f
    if grep -q 'mkfs' $f; then
        bbfatal "HDSatelit: resizerootfs inca formateaza ceva"
    fi
    if ! grep -q 'resize2fs /dev/block/by-name/userdata' $f; then
        bbfatal "HDSatelit: resizerootfs a pierdut redimensionarea lui userdata"
    fi
}

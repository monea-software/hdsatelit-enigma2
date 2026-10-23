# HDSatelit, 23.09.2026: scoase ramurile u57 si other1/other2 din /etc/init.d/partitions-by-name.
#
# De ce: scriptul comun (meta-oe/recipes-support/partitions-by-name/files/partitions-by-name.sh, versiunea din
# 23.09.2026) are doua ramuri care, la fiecare pornire (S04), pot scoate protectia la scriere de pe zona ascunsa
# mmcblk0boot1 a eMMC-ului (echo 0 > .../force_ro) si o pot lega ca /dev/block/by-name/others, pentru
# un multiboot pe care imaginea nu il are:
#  - r. 93-98, ramura pentru masina u57 (V20/V30). Pe V20 azi nu apuca sa ruleze (/proc/stb/info/boxtype nu
#    exista inca la S04), dar e o cursa, nu o garantie;
#  - r. 59-64, ramura other1/other2. Nu tine de masina: functia search face legaturi by-name si pentru
#    partitiile de pe stick-uri si discuri (sda..sdd, mmcblk1), dupa numele lor GPT. Un stick cu doua partitii
#    numite other1 si other2, legat la pornire, ar debloca boot1 (gasit la verificarea adversariala din 23.09).
# Imaginea HDSatelit nu are meniu de multiboot si nu foloseste boot1; varianta A2 tine alegerea pe p10.
#
# Cum: ramurile se sterg cu sed din fisierul instalat (fisier comun, citit doar pentru intelegere, nimic
# copiat). Fiecare ramura are 6 randuri, de la 'if ...' pana la primul 'fi' de la
# inceput de rand. Compilarea se opreste cu eroare, nu trece tacut, daca: nu s-au scos exact 12 randuri, "u57"
# sau by-name/other1 mai apar, sau raman alte scrieri force_ro decat cele 3 ale ramurilor dm820/dm7080/dm900/dm920,
# et11000/sf4008 si beyonwizu4 (legate de /proc/stb/info/model si boxtype, care pe u57 nu se potrivesc).
# PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed" pe receptor.

PR:append = ".hds1"

do_install:append() {
    f=${D}${sysconfdir}/init.d/partitions-by-name
    inainte=$(wc -l < $f)
    sed -i '/^if grep -q -E "u57" \/proc\/stb\/info\/boxtype; then$/,/^fi$/d' $f
    sed -i '/^if  \[ -e "\/dev\/block\/by-name\/other1" ] && \[ -e "\/dev\/block\/by-name\/other2" ]; then$/,/^fi$/d' $f
    dupa=$(wc -l < $f)
    # expr, nu aritmetica shell cu paranteze duble: analizorul de shell al lui bitbake nu o stie
    # (NotImplementedError la parsare, vazut pe 23.09.2026)
    if [ "$(expr $inainte - $dupa)" != "12" ]; then
        bbfatal "HDSatelit: ramurile u57 si other1/other2 din partitions-by-name nu au fost scoase exact ($inainte -> $dupa randuri)"
    fi
    if grep -q '"u57"' $f; then
        bbfatal "HDSatelit: partitions-by-name inca pomeneste u57"
    fi
    if grep -q 'by-name/other1' $f; then
        bbfatal "HDSatelit: partitions-by-name inca are ramura other1/other2"
    fi
    if [ "$(grep -c force_ro $f)" != "3" ]; then
        bbfatal "HDSatelit: partitions-by-name scrie force_ro in alte locuri decat ramurile dm*, et11000/sf4008, beyonwizu4"
    fi
}

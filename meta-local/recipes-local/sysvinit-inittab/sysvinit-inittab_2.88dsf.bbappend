# HDSatelit, 21.09.2026 (AGENTS.md, "Decizie a proprietarului... flash direct"; STADIU-PROIECT-IMAGINE.md,
# sectiunea 21.09.2026 "plasa de siguranta pentru pornirea NATIVA"): adauga un proces separat, supravegheat
# direct de init, care hraneste watchdogul hardware (/dev/watchdog) cat timp enigma2 e sanatos -- daca
# enigma2 (sau tot sistemul) se blocheaza complet pe pornirea nativa de pe flash, contorul hardware
# forteaza singur o repornire dura, fara sa mai fie nevoie ca userul sa scoata receptorul din priza.
#
# Folosit STRICT do_install:append() (NU o redefinire completa a do_install) -- reteta de baza e deja
# suprascrisa complet de meta-oe-alliance/meta-oe/recipes-core/sysvinit/sysvinit-inittab_2.88dsf.bbappend
# (fisier comun, citit doar pentru intelegere, nimic copiat -- cf. AGENTS.md regula #0), care instaleaza
# linia "gui:3:respawn:/usr/bin/enigma2.sh". O redefinire completa aici, in stratul nostru (prioritate 100,
# cea mai mare), ar fi INLOCUIT acea functie in loc sa se adauge la ea, pierzand linia "gui" -- do_install
# se aplica in ordinea layerelor, dar :append lucreaza pe orice a rezultat deja din reteta + celelalte
# bbappend-uri, deci e sigur indiferent de ordinea de incarcare a layerelor.

do_install:append() {
    echo "" >> ${D}${sysconfdir}/inittab
    echo "# HDSatelit: paznic watchdog hardware, independent de enigma2 (STADIU-PROIECT-IMAGINE.md, 21.09.2026)" >> ${D}${sysconfdir}/inittab
    echo "wdg:3:respawn:/usr/bin/hds-watchdog.py" >> ${D}${sysconfdir}/inittab
}

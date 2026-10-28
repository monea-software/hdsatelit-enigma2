SUMMARY = "Paznic HDSatelit pentru pornirea nativa (watchdog hardware, independent de enigma2)"
DESCRIPTION = "Proces propriu, supravegheat direct de init (linie 'respawn' separata in /etc/inittab, \
vezi sysvinit-inittab bbappend din acest strat), care hraneste watchdogul hardware (/dev/watchdog, \
driver sp805-wdt) cat timp enigma2 e sanatos si opreste hranirea la un blocaj CONFIRMAT (acelasi fir \
in stare D, acelasi wchan, minute la rand -- semnatura cunoscuta a bug-ului de kernel de la scanare). \
Daca enigma2 sau chiar tot sistemul ingheata complet, contorul hardware forteaza oricum o repornire \
dura, garantat, independent de orice software. Pazeste si ruta blackhole spre 117.78.33.205 pusa de \
hdsatelit-netguard: o verifica la 3 minute, o pune la loc daca lipseste si scrie starea in \
/var/run/hds-netguard.stare. Reporneste curat receptorul, cel mult o data pe ora, cand decodorul video nu mai \
porneste din lipsa de memorie in nucleu, si spune (fara repornire) cand demonul platformei nu si-a putut mapa \
memoria pozelor si a filmelor. Monea Software pentru HD Satelit. Detalii si dovada testarii izolate: \
STADIU-PROIECT-IMAGINE.md, sectiunea 21.09.2026; paza rutei: securitate-showiframe/REPARARE.md (L1, L3)."
LICENSE = "CLOSED"
PV = "0.1.0"
# r1 (24.09.2026): nivelul 4, paza rutei hds-netguard (securitate-showiframe/urmari-paza-progres.md)
# r2: nivelul 3 nu mai reporneste interfata numai pe tacerea web: bataia enigma2
# (Components/HdsPaznic.py, /var/run/hds-paznic.bataie, ceas monoton) si semnul „ocupat” (scanare, citirea pistelor,
# rotirea antenei), setarile config.hds_paznic.*, starea in /var/run/hds-paznic.stare, SIGKILL daca SIGTERM nu ajunge,
# nivelul 2 cu prag de ~5 min cat tine semnul „ocupat”; jurnalele de cadere in /home/root/logs (ultimele 5), nu in
# /media/hdd. Aceleasi module Python ca inainte (fara importuri noi), deci RDEPENDS neschimbat.
# r3 (05.10.2026, lotul paza-cadere-023): nivelul 5, decodorul video fara memorie: jurnalul nucleului (/dev/kmsg, altfel
# /home/root/logs/messages), decodoarele (/proc/msp/vdecNN), bataia enigma2 cu redare= si inregistrare=; o singura
# repornire curata (/sbin/reboot, nu sysrq), cel mult o data pe ora (semnul /home/root/logs/hds-paznic-decodor.repornire),
# cu motivul si in /home/root/logs/hds-caderi.log. Semnul /tmp/hds-paznic.oprire inainte de SIGTERM si SIGKILL, citit de
# enigma2.sh: oprirea ceruta de paznic nu se mai socoteste placii 2D. Tot fara importuri noi (subprocess era folosit),
# deci RDEPENDS neschimbat.
# r4 (05.10.2026): inainte de repornirea dura (sysrq 'b'), sysrq 'w' si copia jurnalului nucleului in
# /home/root/logs/hds-blocaj-*.txt (ultimele 5): stivele firelor blocate, cu numele functiilor; cat ruleaza programul de
# noapte al culegerii (/tmp/hds-culegere.pid), pragul nivelului 2 e cel lung (~5 min), ca la scanare. Import nou: errno
# (din python3-core, RDEPENDS neschimbat).
# r5 (14.10.2026, lotul cadere-radio-2): anuntul memoriei pozelor si a filmelor: cand demonul platformei (showiframe) nu
# si-a putut mapa memoria de 34611200 o (jurnalul nucleului, aceleasi citiri ca nivelul 5, sau /proc/vmallocinfo cel mult
# o data pe minut), memorie_es=lipsa in /var/run/hds-paznic.stare si o linie in jurnal; enigma2 arata mesajul. Nicio
# repornire. Fara importuri noi, deci RDEPENDS neschimbat.
# r6 (lotul cod-0425): nivelul 2 nu mai socoteste blocat un fir care nu e firul principal si care se trezeste intre
# verificari (schimbarile de context din /proc/PID/task/TID/status cresc): pe HiSilicon firul enigma2 care impinge in
# dvr un fisier redat (timeshift, inregistrare) sta in msleep in driver cat tamponul TS e plin, deci in D la fiecare
# verificare, si paznicul repornea dur receptorul dupa ~1 minut de pauza. Firul principal si firele fara numaratori
# citite raman cu regula veche. Fara importuri noi, deci RDEPENDS neschimbat.
# r7 (lotul memorie-0509): lipsa maparii de 33 MB a demonului platformei (fara randurile de esec din jurnalul nucleului)
# se crede numai cu un canal TV sau radio pornit de cel putin 30 s (bataia enigma2, redare=tv sau radio): demonul isi
# face maparea abia cand enigma2 foloseste decodorul, iar dupa o pornire direct in standby paznicul scria
# memorie_es=lipsa si enigma2 0.5.8 arata la trezire mesajul de memorie. Enigma2 nu mai arata niciun mesaj de memorie. Fara importuri noi, deci RDEPENDS neschimbat.
# r8 (versiunea 0.6.7): nivelul 6, serviciile de sistem: D-Bus (dbus-daemon), avahi-daemon si hds-nume-local pornite din
# nou, tacut, cand cad (cel mult de 3 ori pe ora fiecare, numai cele pornite la pornirea receptorului, numai dupa 3 minute
# de la pornire), cu o linie in jurnalul paznicului si starea servicii= in /var/run/hds-paznic.stare. Cel mult o pornire
# la o trecere (dbus, apoi avahi, apoi numele, la verificarile urmatoare), scriptul cu 10 s si asteptare marginita dupa
# kill(), fara sleep: o trecere ramane mult sub pragul de 60 s al watchdogului HW. Import nou: socket
# (il aduce deja python3-netclient, pentru http.client), deci RDEPENDS neschimbat.
PR = "r8"

SRC_URI = "file://hds-watchdog.py"
S = "${UNPACKDIR}"

inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/hds-watchdog.py ${D}${bindir}/hds-watchdog.py
    # paza: scriptul instalat trebuie sa fie Python valid, cu sfarsit de rand LF si cu adresa pazita;
    # altfel constructia se opreste (un paznic care nu porneste nu mai hraneste nici watchdogul HW)
    if grep -q "$(printf '\r')" ${D}${bindir}/hds-watchdog.py; then
        bbfatal "hds-watchdog.py: sfarsit de rand CRLF, nu ar porni pe receptor"
    fi
    grep -q '^NETGUARD_IP = "117\.78\.33\.205"$' ${D}${bindir}/hds-watchdog.py || \
        bbfatal "hds-watchdog.py: lipseste NETGUARD_IP = 117.78.33.205"
    python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' \
        ${D}${bindir}/hds-watchdog.py || bbfatal "hds-watchdog.py: eroare de sintaxa Python"
}

FILES:${PN} = "${bindir}/hds-watchdog.py"

# python3-core: struct/signal/os/sys (module built-in, verificat ca NU au reteta separata in
# python3-manifest.json -- vin cu core). python3-fcntl: verificat DIRECT in python3-manifest.json
# (openembedded-core/meta/recipes-devtools/python/python3/python3-manifest.json, linia ~592) -- "fcntl"
# e subpachet SEPARAT (extensie .so proprie), NU vine automat cu core. python3-netclient (adaugat
# 21.09.2026, pentru sondarea HdsWebControl la blocaj moale): verificat DIRECT in acelasi manifest,
# linia ~829 -- pachetul "netclient" contine "${libdir}/python.../http" (deci http.client), separat de
# core, indiferent de ce alte pachete mai sunt instalate pe imagine.
# python3-misc (24.09.2026, verificarea adversariala a pazei): manifestul pune os/struct/signal/subprocess/
# selectors/threading in "core", dar imaginea noastra are numai .pyc (fara .py) pe primul nivel, care nu se
# potrivesc tiparelor lui core si cad in python3-misc. Dovada e pkgdata din build, nu manifestul:
# tmp/pkgdata/u57/runtime/python3-misc (FILES_INFO) are os.pyc, struct.pyc, signal.pyc, subprocess.pyc,
# selectors.pyc, threading.pyc; python3-core are numai _posixsubprocess, select si fcntl (.so).
# iproute2-ip: /sbin/ip.iproute2 (stie "blackhole" si "show exact"), acelasi ca in hdsatelit-netguard.
RDEPENDS:${PN} = "python3-core python3-misc python3-fcntl python3-netclient iproute2-ip"

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hds-watchdog.py -- paznic HDSatelit pentru pornirea NATIVA (de pe flash), independent de enigma2.

De ce exista: pe pornirea nativa (fara chroot, fara stick), receptorul se poate bloca total (fir de
kernel blocat, ex. "dvb_demux_release", vazut la scanarea de satelit) -- fara SSH, fara telecomanda,
singura recuperare fiind scoaterea din priza. Acest script ruleaza ca proces SEPARAT, supravegheat direct
de init (linie proprie "respawn" in /etc/inittab, cf. STADIU-PROIECT-IMAGINE.md, 21.09.2026)
-- daca enigma2 e complet blocat, codul din interiorul lui nu mai apuca sa ruleze niciodata, de-aici
nevoia unui proces independent.

Mecanism (cinci nivele, independente unul de altul):
  1. Watchdog HARDWARE (/dev/watchdog, driver sp805-wdt, confirmat pe receptor 21.09.2026): odata deschis,
     kernelul asteapta o "hranire" (scriere) la fiecare cel mult TIMEOUT_HW secunde, altfel forteaza
     singur o repornire dura -- la nivel de siliciu, independent de orice proces din userspace, inclusiv
     de ACEST script. Daca sistemul intreg ingheata (inclusiv acest paznic), nimeni nu mai hraneste
     watchdogul si repornirea se intampla oricum, GARANTAT, fara ajutor de la niciun cod.
  2. Detectie de BLOCAJ DUR (acest script): la fiecare PET_INTERVAL secunde, verifica firele procesului
     enigma2 -- daca acelasi fir ramane in starea "D" (uninterruptible sleep, semnatura exacta a bug-ului
     cunoscut) mai multe verificari la rand, considera blocajul CONFIRMAT: nu mai hraneste watchdogul
     (calea de rezerva de mai sus preia, garantat, in max TIMEOUT_HW secunde) SI incearca imediat, activ,
     o repornire dura prin sysrq (cale mai rapida, cand kernelul mai poate raspunde).
     Un fir care NU e firul principal al procesului (tid != pid) si care s-a trezit intre doua verificari (suma
     voluntary_ctxt_switches + nonvoluntary_ctxt_switches din /proc/PID/task/TID/status a crescut) nu e blocat, chiar
     daca e gasit de fiecare data in D cu acelasi wchan: asa arata pe HiSilicon firul enigma2 care impinge in dvr un
     fisier redat (timeshift, inregistrare). Cat tamponul TS al redarii e plin (decodorul in pauza sau mai incet decat
     citirea), driverul il tine in msleep(10) sau msleep(100) la fiecare scriere, deci in D aproape tot timpul, dar firul
     iese din driver de zeci de ori pe secunda. Un fir blocat cu adevarat nu se mai trezeste deloc. Pentru firul
     principal si cand schimbarile nu se pot citi ramane regula de mai sus (oricat s-ar trezi in driver, firul
     principal tinut un minut in D inseamna o interfata inghetata).
  3. Detectie de BLOCAJ MOALE (adaugat 21.09.2026, gol real gasit la investigarea fundatiei GStreamer):
     un tip DIFERIT de blocaj -- firele enigma2 raman toate in stare "S" (asteptare intreruptibila, NU
     "D"), deci nivelul 2 de mai sus NU-l vede NICIODATA (verificat cu dovada directa, vezi
     STADIU-PROIECT-IMAGINE.md, "bucla EBUSY pe dvb_audio_open" -- o bucla de reincercare pe deschiderea
     unui dispozitiv hardware, cu asteptari intre incercari, nu un blocaj de kernel). Semnul vizibil pentru
     user: interfata nu mai raspunde deloc la telecomanda, dar receptorul "pare pornit". Recuperarea: SIGTERM
     STRICT catre procesul enigma2 (respawn curat prin inittab in ~8s, verificat de doua ori), iar daca procesul
     nu iese in SIGKILL_DUPA_S secunde, SIGKILL -- NU repornire dura.
     Semnul NU mai e numai tacerea interfetei web 60 de secunde: asa paznicul oprea enigma2 in mijlocul unei
     scanari de mai multi sateliti cu motor (o operatie lunga pe firul principal face si web-ul sa taca: aceeasi
     bucla). Acum:
       - semnul principal e BATAIA scrisa de enigma2 (Components/HdsPaznic.py) in BATAIE_PATH la fiecare 10 s,
         cu pid-ul si ceasul MONOTON (CLOCK_MONOTONIC, comun proceselor; ora de perete se poate muta cu ore la
         pornire prin NTP sau transponder, deci nici data fisierului, nici time.time() nu se folosesc);
       - bataia poarta semnul „ocupat” (scanare, citirea pistelor, rotirea antenei) cu un termen pe acelasi ceas
         monoton: cat tine termenul, interfata nu se reporneste, chiar daca bataia s-a oprit;
       - interfata se reporneste numai cand bataia procesului enigma2 de acum e mai veche decat asteptarea din
         setari (config.hds_paznic.asteptare: 60, 120 sau 300 s, implicit 120), fara semn „ocupat” valabil, SI
         interfata web nu raspunde (sau e oprita din setari); fara nicio bataie de la procesul de acum (pornire,
         imagine veche) paznicul NU reporneste nimic numai pe tacerea web;
       - config.hds_paznic.interfata=false (ecranul „Paznicul receptorului” sau /paznic) opreste nivelul 3;
       - hotararea e o functie fara efecte (hotarare_blocaj_moale), testata separat (teste/test_paznic_sistem.py);
       - inainte de SIGTERM (si de SIGKILL) se scrie OPRIRE_PATH (/tmp/hds-paznic.oprire, in RAM): pid-ul, parintele
         (enigma2.sh, care asteapta procesul), uptime-ul si, inainte de SIGKILL, sigkill=. tools/enigma2.sh.in il citeste
         dupa iesire: 143 (sau 137 cu sigkill=) al enigma2-ului lui, in cel mult 5 minute de la semn, e oprirea ceruta de
         paznic, nu o cadere, deci nu se socoteste placii 2D si nu opreste accelerarea (lotul paza-cadere-023).
  4. Paza rutei hds-netguard (adaugat 24.09.2026, securitate-showiframe/REPARARE.md, limitele L1 si L3):
     hds-netguard (rcS S41) pune o singura data ruta "blackhole 117.78.33.205/32", ca showiframe (Dinobot)
     sa nu poata trimite MAC-ul si id-ul cipului la serverul strain. Aici, la pornire si apoi la fiecare
     NETGUARD_INTERVAL_S secunde, se citeste "ip -4 route show exact 117.78.33.205/32"; daca vreun rand nu
     e "blackhole" fara "tos" (lipsa, alt tip, alta cale, sau un blackhole cu tos care ascunde o ruta via),
     ruta se pune la loc cu "ip -4 route replace blackhole ..."; daca alta intrare ramane, "ip -4 route
     flush exact ..." si din nou "replace".
     Comenzile se dau ca lista de argumente (fara shell), cu limita de timp, si nu se asteapta niciodata
     fara limita dupa ele: un "ip" blocat in nucleu (stare D, de ex. rtnl_mutex tinut de un driver agatat)
     nu moare la SIGKILL; el se tine minte si nu se porneste altul pana nu iese (vezi _ng_ruleaza).
     Cel mai rau caz al unui pas: sub 6 comenzi x NETGUARD_IP_TIMEOUT_S + 0,5 s.
     In jurnal intra o linie numai la schimbare (ruta repusa, stare noua), nu la fiecare verificare.
     Nu se repune ruta cand: /etc/init.d/hds-netguard lipseste (pachetul dezinstalat dinadins) sau exista
     semnul de pauza NETGUARD_PAUZA_PATH mai nou de NETGUARD_PAUZA_MAX_S (portita pentru un cip
     neprovizionat, SECURITATE.md S1: "touch /var/run/hds-netguard.pauza" inainte de "hds-netguard stop",
     "rm" dupa "start"; dupa 30 de minute sau la repornire ruta revine oricum).
     Starea pentru interfata: NETGUARD_STARE_PATH (/var/run e in RAM pe receptor, /var/volatile/run;
     /run e dosar pe flash, p10, deci nu se foloseste). Fisierul se rescrie numai la schimbare, atomic
     (.nou + rename), cu randuri "cheie=valoare":
       stare=pusa|esec|necunoscut|fara-ip|pauza|neinstalat
         pusa        ruta blackhole e la locul ei (verificata)
         esec        ruta lipsea si nu s-a putut pune la loc (showiframe poate iesi in retea)
         necunoscut  "ip ... show" n-a raspuns (timp depasit sau eroare)
         fara-ip     nu exista /sbin/ip.iproute2 si nici /sbin/ip
         pauza       semnul de pauza e prezent si proaspat, ruta nu se atinge
         neinstalat  hdsatelit-netguard nu e instalat, ruta nu se atinge
       adresa=117.78.33.205
       detaliu=<text scurt, un rand>
       schimbat=<secunde epoch, ultima schimbare de stare sau repunere>
       repuneri=<de cate ori a fost pusa la loc de la pornirea acestui proces>
       ultima_repunere=<secunde epoch, 0 daca niciodata>
       pid=<pid-ul acestui paznic; daca procesul nu mai exista, starea e veche>
  5. Decodorul video fara memorie (adaugat 05.10.2026, lotul paza-cadere-023). Pe 04.10.2026, dupa o serie de caderi ale
     enigma2, nucleul a ramas fara spatiu vmalloc: „vmap allocation for size 17043456 failed”, „Remap VFMW_SCD failed”,
     „VDEC_Chan_AllocMem err , no memory!”, „HI_DRV_VDEC_ChanStart ... Start err”. Niciun canal nu mai avea imagine pana
     la repornirea receptorului, iar interfata raspundea, deci nivelul 3 nu vedea nimic. Aici:
       - jurnalul nucleului se citeste din /dev/kmsg (numai inregistrarile noi, fiecare cu ceasul ei; nu tine nimic de
         dinaintea unei reporniri), iar daca nu se poate deschide, coada lui /home/root/logs/messages; citirea e marginita
         pe verificare (randuri, timp, octeti), ca hranirea sa nu intarzie;
       - randurile unui esec vin in ~20 ms si fac un grup; grupul e SIGUR numai cu „VDEC_Chan_AllocMem ... no memory”,
         cu „DmxAllocNonSecureAVBuf ... failed”, sau cu „Start err” impreuna cu „vmap ... failed” / „Remap ... failed”;
         un rand izolat nu se numara. Lipsa e „de acum” cu cel putin DEC_PRAG grupuri sigure in DEC_FEREASTRA_S, ultimul
         de cel mult DEC_ULTIMUL_MAX_S secunde; numai atunci se citesc decodoarele (/proc/msp/vdec00 si vdec01, „Work
         State”), programul de noapte al culegerii (/tmp/hds-culegere.pid) si semnul de pe disc;
       - receptorul se reporneste o singura data (REBOOT_BIN, repornire curata, ca enigma2.sh la codul 2; nu sysrq) numai
         cu toate: repornirea interfetei pornita din setari (config.hds_paznic.interfata), bataia enigma2 de acum vie si
         fara semn „ocupat”, culegerea de noapte oprita, redare=tv si inregistrare=0 in bataie (Components/HdsPaznic.py),
         niciun decodor video in RUN de cel putin DEC_CONFIRMARE_S secunde (si niciunul vazut in RUN dupa ultimul esec:
         atunci memoria a ajuns si se asteapta un esec nou) si nicio repornire pentru decodor in ultima ora
         (DECODOR_SEMN_PATH, pe memoria interna, scris cu fsync inainte de reboot). Un semn lipsa sau necitit = numai o
         linie in jurnal. Motivul intra si in /home/root/logs/hds-caderi.log;
       - hotararea e o functie fara efecte (hotarare_decodor), testata in teste/test_paza_cadere_023.py.
  Pe langa nivele, ANUNTUL memoriei pozelor si a filmelor (adaugat 14.10.2026, lotul cadere-radio-2). Demonul
     platformei (showiframe, pornit de enigma2.sh odata cu enigma2) isi mapeaza la pornire in nucleu o memorie de
     34611200 o, prin care driverul video primeste poza posturilor de radio si filmele (video0, audio0). Cand spatiul
     vmalloc e farmitat maparea esueaza („vmap allocation for size 34611200 failed”, apoi „[HI_DRV_SMMU_Map] Remap buf
     failed”), iar prima scriere in video0 sau audio0 ar opri nucleul (caderea din 14.10.2026 00:12). enigma2 nu mai
     scrie atunci (lib/dvb/hdspazavideo.h), dar poza radio si filmele nu merg pana la repornirea receptorului. Aici:
       - cele doua randuri in acelasi grup (din acelasi cititor al jurnalului nucleului ca nivelul 5) dupa pornirea
         demonului de acum, sau nicio mapare de 34611200 o in /proc/vmallocinfo la cel putin ES_PORNIRE_S de la
         pornirea lui = memoria lipseste; vmallocinfo se citeste cel mult o data pe minut (si pe loc la un esec nou).
         Lipsa maparii, fara randurile de esec, se crede numai cu un canal TV sau radio pornit de cel putin
         ES_PORNIRE_S (bataia enigma2 spune redare=tv sau radio; vmallocinfo se reciteste cand starea asta se schimba):
         demonul isi face maparea abia cand enigma2 foloseste decodorul, deci dupa o pornire direct in standby
         (repornirea in standby) ea lipseste pana la trezire;
       - starea (memorie_es=lipsa|ok|nesigur, memorie_es_cheie=pid-ul demonului) intra in STARE_PATH, de unde enigma2
         (Components/HdsPaznic.py) arata un rand de informatie pe ecranul si pagina paznicului (niciun mesaj pe
         televizor) si o socoteste la repornirea in standby (Components/HdsMemorieDriver.py); o linie in jurnalul
         paznicului la schimbare;
       - NU se reporneste nimic; hotararea e o functie fara efecte (hotarare_memorie_es), testata in
         teste/test_cadere_radio_2.py.

  6. Serviciile de sistem (adaugat 25.10.2026, versiunea 0.6.7): D-Bus de sistem (dbus-daemon), avahi-daemon si
     publicarea numelui hdsatelit.local (hds-nume-local). Pe 25.10.2026 dbus-daemon s-a oprit singur, iar odata cu el
     avahi-daemon si hds-nume-local: hdsatelit.local nu mai raspundea, desi interfata web mergea pe adresa IP. Aici, la
     SERVICII_INTERVAL_S secunde si numai dupa SERVICII_PORNIRE_S de la pornirea receptorului (pana atunci le porneste
     rc5):
       - si numai dupa ce scripturile de pornire s-au terminat (r16, 0.7.6, asistenta 430032 15.11.2026): cat mai ruleaza
         /etc/init.d/rc sau rcS (rc_in_lucru, dupa linia de comanda din /proc), un serviciu care inca nu e pornit nu
         e cazut, ci la rand. O pornire lenta (reteaua, discurile, reparatia actualizarii) trecea de 180 s, iar paznicul
         pornea avahi in paralel cu rc, care il pornea si el. Cel mult SERVICII_RC_MAX_S de la pornire: un script de
         pornire agatat nu lasa hdsatelit.local cazut pentru totdeauna;
       - avahi-daemon si hds-nume-local sunt cazute numai cand lipsesc la DOUA verificari la rand (r16): interfata le
         opreste si le porneste singura la schimbarea retelei (Components/Network.py: avahi-daemon stop, ifdown/ifup,
         avahi-daemon start), iar o verificare cazuta intre ele pornea avahi in paralel cu ea. dbus ramane cu regula lui;
       - dbus merge cand exista un proces dbus-daemon si soclul sistemului (DBUS_SOCLURI) primeste o conexiune; fara
         proces, sau cu soclul refuzat SERVICII_CONFIRMARI verificari la rand, se porneste din nou cu scriptul lui
         (/etc/init.d/dbus-1 start; restart cand procesul a ramas, dar nu raspunde);
       - avahi-daemon si hds-nume-local se pornesc din nou numai daca sunt pornite la pornirea receptorului (o legatura
         S..<nume> in /etc/rc[2-5].d: omul care le-a oprit dinadins le gaseste oprite) si numai cu dbus mergand
         (avahi are nevoie de el; hds-nume-local de avahi);
       - fiecare serviciu se porneste de cel mult SERVICII_MAX_ORA ori pe ora (o cadere in bucla nu tine receptorul
         ocupat); scripturile ruleaza ca lista de argumente, fara shell, cu SERVICII_TIMEOUT_S;
       - CEL MULT O PORNIRE LA O VERIFICARE, in ordinea dbus, avahi, numele local (ce mai lipseste se porneste la
         verificarile urmatoare, la SERVICII_INTERVAL_S): hranirea watchdogului HW se face o data pe trecere, iar o
         trecere nu are voie sa stea aproape de pragul de 60 s; fara sleep si fara asteptarea soclului. Scriptul
         ruleaza ca la _ng_ruleaza: dupa timpul depasit kill() si o asteptare de cel mult 0,5 s; un script ramas
         agatat in nucleu (stare D) se tine minte si pana nu iese nu se mai porneste altul. Cel mai rau caz al
         nivelului 6 intr-o trecere: SERVICII_TIMEOUT_S + 0,5 s + citirea soclurilor (SERVICII_SOCLU_S pe soclu);
       - TACUT: nicio fereastra pe televizor; o linie in jurnalul paznicului (pe disc) la fiecare pornire si la fiecare
         schimbare, iar starea (servicii=ok|repornit|esec, servicii_detaliu, servicii_ora, servicii_reporniri) intra in
         STARE_PATH, de unde enigma2 (Components/HdsPaznic.py) o arata in "Informatii jurnale" si in pagina web
         /jurnale-sistem;
       - hotararea e o functie fara efecte (hotarare_servicii), testata in teste/test_gasite_0607.py (clasa
         Servicii), impreuna cu limita de timp a unei treceri.
       - DE CE (r17, 0.7.6, asistenta 430032 15.11.2026): cand avahi sau numele local e socotit cazut (a doua
         verificare fara proces), o data pe cadere, un rand "<cheie> cazut, de ce: ..." in jurnalul paznicului si in
         SERVICII_JURNAL_PATH (motiv_lipsa): uptime-ul, fisierul pid (ramas cu procesul mort = oprit brusc sau cazut;
         lipsa lui = oprit curat, de pilda de Network.py, sau nepornit) si ultimele MOTIV_RANDURI randuri ale lui din
         coada lui MESAJE_PATH (cel mult MOTIV_MESAJE_OCTETI, citita numai atunci). Inainte se scria numai "avahi
         cazut" si cauza lipsei nu ramanea nicaieri;
       - randul de pornire al paznicului (rand_pornire, r17) spune uptime-ul si daca ceasul e inca ora salvata
         (fake-hwclock, nesincronizat), numai in jurnalul paznicului (in SERVICII_JURNAL_PATH ar face fisierul pe
         orice receptor sanatos, trimis apoi de HdsBetaTester ca jurnal de eroare). Fara el, randurile a doua
         porniri, ambele plecate de la aceeasi ora salvata, se citeau ca o singura pornire (asistenta 430032: "avahi
         cazut" la 39 s dupa o cerere de iesire, citit ca "4 s dupa rc5" al pornirii urmatoare).

  Cat ruleaza opkg (r14, versiunea 0.7.4): orice proces cu numele opkg (actualizarea din meniu sau din web,
     Extensii, SSH, reparatia actualizarii de la pornire) face bataia „ocupat” cu motivul „actualizare” (opkg_in_lucru,
     bataie_cu_opkg): nivelul 3 nu opreste enigma2, nivelul 5 nu reporneste receptorul, nivelul 2 are pragul lung.
     O iesire a enigma2 in timpul unei instalari din interfata opreste opkg la jumatate (fisiere amestecate, status
     vechi, interfata care nu mai porneste: SF8008 cu radacina pe stick, 10.11.2026). Cel mult OPKG_MAX_S pe proces.
     Tot in r14, anuntul memoriei pozelor: lipsa citita din vmallocinfo se crede numai dupa ES_CITIRI_LIPSA citiri la
     rand fara mapare (numara_citiri_zero); o singura citire falsa, noaptea, nu mai da anuntul. Testat in
     teste/test_paznic_opkg_074.py.

Testat izolat pe receptorul de test, 21.09.2026 -- vezi STADIU-PROIECT-IMAGINE.md pentru
dovada (toate cele trei ramuri: pastreaza receptorul pornit cand enigma2 e sanatos; chiar reporneste dur
cand un proces tinta e absent/blocat cu fire D, fortat prin variabile de mediu de test; chiar trimite
SIGTERM cand API-ul local nu mai raspunde, reprodus real cu bucla EBUSY pe dvb_audio_open).
"""

import errno
import fcntl
import http.client
import os
import signal
import stat
import struct
import subprocess
import sys
import time

# ---- parametri, editabili doar prin variabile de mediu (folosite azi STRICT pentru testarea izolata,
# cf. tiparului deja folosit la plugin-pornire-stick/porneste.sh cu "proces-care-nu-exista-niciodata") ----
TARGET_PROCESS = os.environ.get("HDS_WATCHDOG_TARGET", "enigma2")
LOG_PATH = os.environ.get("HDS_WATCHDOG_LOG", "/home/root/hds-watchdog.log")
DEVICE_PATH = os.environ.get("HDS_WATCHDOG_DEVICE", "/dev/watchdog")

PET_INTERVAL_S = 15          # cat de des verificam + hranim (mult sub jumatate din timeout-ul HW)
CONFIRM_HANG_CHECKS = 4      # acelasi fir, aceeasi stare D, acelasi wchan, de atatea ori la rand
                              # (~60s la 15s/verificare) inainte sa declaram blocaj CONFIRMAT
LOG_MAX_BYTES = 262144       # 256 KB -- jurnalul se scurteaza singur peste acest prag

# Firele lasate deoparte de enigma2 (r9, 02.11.2026): pe familia libreader (SF8008, SF8008 MINI, V10) citirea si
# scrierea HDMI-CEC merg pe un fir de fundal tocmai fiindca driverul hi_hdmicec le poate tine in D pentru totdeauna
# (placa SF8008 din 2024; Components/HdsStandbyTv.py in depozitul imaginii, comiterile 3b8d8397d si 89866b154):
# enigma2 opreste atunci CEC si merge mai departe. Un astfel de fir, care nu e firul principal, nu e un blocaj al
# interfetei. Inainte de r9 paznicul il lua drept unul si repornea dur receptorul la ~1 minut dupa pornire, la fiecare
# pornire (raportul 867222: SF8008 V3, 0.6.23, interfata pornita dupa 12 s, tid=5106 in hdmicec_write, sysrq la 62 s).
# Firul principal in D ramane blocaj, oricare i-ar fi wchan-ul.
# r11: iertarea tine numai cat firul principal e viu. Cand enigma2 iese (repornirea interfetei, SIGTERM-ul nivelului 3,
# o cadere), un fir ramas in D nu poate muri, firul principal ramane „Z” (zombie) si procesul nu se termina, deci init nu
# porneste alta interfata: atunci firul CEC ramas e chiar blocajul si se socoteste ca orice alt fir (repornirea dura e
# singura iesire; fara ea ecranul ar ramane negru pana la oprirea de la comutator).
WCHAN_FIRE_LASATE_DEOPARTE = ("hdmicec_",)
STARI_FIR_PRINCIPAL_MORT = ("Z", "X")

# ---- nivelul 3, blocaj moale (bataia enigma2 + HdsWebControl) ----
SETTINGS_PATH = os.environ.get("HDS_WATCHDOG_SETTINGS", "/etc/enigma2/settings")
WEBCONTROL_PORT_IMPLICIT = 80       # HdsWebControl/plugin.py, ConfigInteger(default=PORT_IMPLICIT)
# portul pe care asculta interfata acum (il scrie HdsWebControl la pornire; 8080 cand 80 e tinut de alt program)
WEBCONTROL_PORT_ACUM_PATH = os.environ.get("HDS_WATCHDOG_PORT_ACUM", "/var/run/hdswebcontrol.port")
WEBCONTROL_CALE_PROBA = "/api/statusinfo"
SOFT_PROBE_TIMEOUT_S = 5     # un raspuns sanatos vine aproape instant; 5s e deja generos
# Bataia si starea: /var/run e in RAM pe receptor (/var/volatile/run), ca NETGUARD_STARE_PATH.
BATAIE_PATH = os.environ.get("HDS_WATCHDOG_BATAIE", "/var/run/hds-paznic.bataie")
STARE_PATH = os.environ.get("HDS_WATCHDOG_STARE", "/var/run/hds-paznic.stare")
# Aceleasi valori implicite ca in Components/HdsPaznic.py din hdsatelit-image (config.hds_paznic.*); enigma2 scrie in
# settings numai valorile schimbate, deci aici trebuie sa fie aceleasi (testul test_paznic_sistem le compara).
INTERFATA_IMPLICIT = True
ASTEPTARE_IMPLICITA_S = 120
ASTEPTARI_PERMISE_S = (60, 120, 300)
OCUPAT_MAX_S = 3600          # un semn „ocupat” cu termen mai departe de atat de bataia lui nu se crede (fisier stricat)
CONFIRM_HANG_CHECKS_OCUPAT = 20  # nivelul 2 cat tine semnul „ocupat”: ~5 min (un acord lung sau o cautare oarba pot
                                 # tine un fir in D mai mult de un minut); fara semn raman CONFIRM_HANG_CHECKS (~1 min)
SIGKILL_DUPA_S = 30          # enigma2 care nu iese la SIGTERM (firul principal blocat nu mai ajunge la iesire)

_sigterm = None              # (pid, ceas monoton) al ultimului SIGTERM al nivelului 3, pentru SIGKILL
_reporniri_interfata = 0     # de cate ori a repornit nivelul 3 interfata de la pornirea acestui paznic
_ultima_actiune = ("", 0)    # (text, ora de perete) pentru ecran si web
_placa_secunde = 0           # timpul watchdog-ului hardware raportat de driver (0 = necitit)
_fara_bataie_anuntat = None  # pid-ul pentru care s-a scris deja „fara bataie” in jurnal
_web_raspunde_anuntat = None # pid-ul pentru care s-a scris deja „bataia oprita, web-ul raspunde”
_ocupat_anuntat = None       # (pid, motiv) pentru care s-a scris deja „astept, e ocupat”

# ---- r14 (0.7.4): cat ruleaza opkg nu se reporneste nimic (LinuxSat 164125 #969426, SF8008 cu radacina pe stick) ----
# opkg pornit din interfata (actualizarea, Extensii, modulele lipsa) e copilul enigma2: la iesirea enigma2 primeste
# SIGKILL (~eConsoleAppContainer, lib/base/console.cpp), iar dupa un SIGKILL al enigma2 moare la urmatorul rand scris
# (SIGPIPE). Dezarhivarea ramane la jumatate, status-ul opkg (scris numai la iesire) ramane pe versiunea veche si
# interfata nu mai porneste. Cat exista un proces opkg (de oriunde: meniul, web, SSH, reparatia de la pornire), bataia
# se socoteste „ocupat” cu motivul OPKG_MOTIV: nivelul 3 nu trimite SIGTERM, nivelul 5 nu reporneste receptorul, iar
# nivelul 2 are pragul lung (~5 min); un blocaj adevarat de nucleu tot se prinde si watchdogul HW ramane. Procesul se
# cauta dupa nume (/proc/PID/comm, gaseste_opkg), nu dupa lacatul lui opkg: o proba de lacat l-ar putea lua chiar cand
# porneste un opkg, care ar cadea atunci cu „Could not lock”. Cel mult OPKG_MAX_S pe proces: un opkg agatat (un
# postinst care nu mai iese) nu tine paznicul departe pe veci.
OPKG_NUME = os.environ.get("HDS_WATCHDOG_OPKG", "opkg")
OPKG_MOTIV = "actualizare"   # acelasi motiv ca MOTIV_ACTUALIZARE din Components/HdsPaznic.py (textul lui pe ecran si web)
OPKG_MAX_S = 3600
OPKG_OCUPAT_S = 2 * PET_INTERVAL_S   # termenul pus in bataie; se reinnoieste la fiecare verificare cat opkg ruleaza
_opkg_vazut = {}             # pid -> [ceasul monoton la care s-a vazut prima oara, termenul depasit deja anuntat]

# ---- jurnalele de cadere ale enigma2: aceeasi cale ca in main/bsod.cpp (CRASH_LOG_DIR) ----
CRASH_LOG_DIR = os.environ.get("HDS_WATCHDOG_CRASH_DIR", "/home/root/logs")
CRASH_LOG_PASTRATE = 5       # ~100 KB fiecare; o cadere in bucla nu umple memoria interna

# ---- stivele Python ale enigma2 inainte de SIGTERM (mytest.py le leaga de faulthandler pe STIVE_SEMNAL) ----
STIVE_SEMNAL = int(getattr(signal, "SIGRTMIN", 34)) + 7   # 41 pe receptor; getattr: probele pe Windows
STIVE_PATH = os.environ.get("HDS_WATCHDOG_STIVE", "/tmp/enigma2-stive.txt")
STIVE_ASTEPTARE_S = 2.0      # scrierea stivelor ia cateva milisecunde; termenul e numai pentru un proces care nu raspunde
STIVE_PREFIX = "enigma2-stive-"
# 0.7.7 (STV): stivele tuturor firelor le scrie intai firul de stive al enigma2 (Components/HdsPaznic.StiveLaCerere),
# citite din Python, la o cerere pe teava lui; faulthandler (STIVE_SEMNAL: numai firul principal, STIVE_TOATE_SEMNAL:
# toate firele) numai daca firul nu raspunde in STIVE_PYTHON_S, adica lacatul Python e tinut si niciun alt fir nu ruleaza
# cod Python. Toate firele citite din semnal cat alt fir rula cod Python au oprit enigma2 (SIGSEGV in libpython, 1 din
# ~318 pe receptorul de proba), iar la pornirea fara bataie procesul nici nu era oprit dupa aceea.
STIVE_TOATE_SEMNAL = int(getattr(signal, "SIGRTMIN", 34)) + 9   # 43 pe receptor; numai enigma2 0.7.7 si mai nou il prinde
STIVE_CERERE = os.environ.get("HDS_WATCHDOG_STIVE_CERERE", "/tmp/hds-stive-%d.cerere")   # %d = pid-ul enigma2
STIVE_PYTHON_S = 2.0         # cat asteapta raspunsul firului de stive; un fir care poate rula raspunde in milisecunde
STIVE_SFARSIT = "# sfarsit cererea "   # ultimul rand al raspunsului (SFARSIT_STIVE din Components/HdsPaznic.py)
STIVE_MAX_OCTETI = 262144

# ---- semnul pentru enigma2.sh: iesirea care urmeaza e ceruta de paznic (lotul paza-cadere-023, 05.10.2026) ----
# aceeasi cale ca HDS_PAZNIC_OPRIRE in tools/enigma2.sh.in (hdsatelit-image); /tmp e in RAM pe receptor
OPRIRE_PATH = os.environ.get("HDS_WATCHDOG_OPRIRE", "/tmp/hds-paznic.oprire")
UPTIME_PATH = os.environ.get("HDS_WATCHDOG_UPTIME", "/proc/uptime")

# ---- viata enigma2 (071): numai jurnal si stive, fara o hotarare noua de repornire ----
IESIRE_PATH = os.environ.get("HDS_WATCHDOG_IESIRE", "/tmp/hds-enigma2.iesire")  # HDS_IESIRE in enigma2.sh
IESIRE_MAX_OCTETI = 4096     # semnul mic din RAM se citeste marginit, chiar daca fisierul e stricat

# ---- 0.7.6 (WDG): iesirea ceruta care nu se mai termina (asistenta 430032, 15.11.2026) ----
# Components/HdsPaznic.iesireInceputa scrie semnul imediat dupa runReactor() din mytest.py (bucla oprita: Reporneste
# interfata, schimbarea temei, o actualizare) si sterge bataia putin dupa. La un SF8008 cu o tema straina pornita,
# procesul ramanea viu dupa "reached rl -1" (5 din 5 reporniri ale interfetei, intre 40 s si 26 de minute): nivelul 3
# vedea numai "fara bataie" si astepta, iar init nu avea ce reporni. Pe celelalte receptoare iesirea se termina in
# 10-30 s. Daca procesul semnului e tot viu dupa IESIRE_CERUTA_S secunde: un rand in hds-caderi.log (codul, tema,
# ecranele, firele ramase), stivele, semnul opririi pentru enigma2.sh (motiv=iesire-ceruta), SIGTERM si, dupa
# IESIRE_SIGKILL_DUPA_S secunde, SIGKILL (dupa bucla, SIGTERM-ul nu mai are cine sa-l trateze). Codul necunoscut
# (quitMainloop chemat direct de un plugin) da tot o repornire a interfetei.
# r18 (0.7.7, UPD, dorinelu forum 795 #2668, Vu+ Solo4K): si iesirile dupa care enigma2.sh opreste sau reporneste
# receptorul (1, 2), scrie afisajul din fata (4) sau porneste Kodi (15): un enigma2 care nu mai iesea la o repornire a
# receptorului ceruta din meniu tinea receptorul agatat pana la buton. enigma2.sh pune apoi la loc codul cerut (din
# acelasi semn al iesirii, pid= si cod=) si face ce s-a cerut. Numai caderea (5) ramane neatinsa.
IESIRE_CERUTA_PATH = os.environ.get("HDS_WATCHDOG_IESIRE_CERUTA", "/var/run/hds-paznic.iesire")
IESIRE_CERUTA_S = 45
IESIRE_SIGKILL_DUPA_S = 5
IESIRE_CODURI_NEATINSE = (5,)
_iesire_oprita = None        # [pid, ceas monoton al SIGTERM-ului, SIGKILL trimis] pentru iesirea ceruta oprita
PRIMA_BATAIE_LUNGA_S = 90    # numai o prima bataie mai tarzie de atat are rand propriu in jurnal
STIVE_FARA_BATAIE_S = 180    # prima copie a stivelor, de la pornirea procesului, daca nu a batut deloc
STIVE_FARA_BATAIE_DIN_NOU_S = 600  # a doua si ultima copie pentru acelasi proces fara nicio bataie

_viata_enigma2 = None        # pid, parinte, pornit_la (/proc/uptime), prima_bataie (intarziere), stive (0..2)
# 0.7.5 (PRN): uptime-ul primei treceri a acestui paznic. Un enigma2 pornit inainte de el (paznicul repornit de
# actualizarea pachetului lui, pkg_postinst, de obicei la cateva minute dupa pornirea receptorului) care bate deja nu
# are prima bataie masurabila: bataia din fisier e ultima, nu prima (pachetele SF8008 1185, 753: „prima bataie dupa
# 199/193 s” false). Atunci prima_bataie = PRIMA_BATAIE_NECUNOSCUTA si niciun rand. Pus numai de main() (probele
# care cheama direct pas_viata_enigma2 il lasa None: regula nu se aplica).
_paznic_pornit_la = None
PRIMA_BATAIE_NECUNOSCUTA = -1
_ultimul_nucleu = ""         # rezumatul firului principal enigma2 vazut de nucleu la ultima cerere de stive

# ---- nivelul 5, decodorul video fara memorie (lotul paza-cadere-023, 05.10.2026) ----
KMSG_PATH = os.environ.get("HDS_WATCHDOG_KMSG", "/dev/kmsg")
MESAJE_PATH = os.environ.get("HDS_WATCHDOG_MESAJE", "/home/root/logs/messages")
VDEC_DOSARE = tuple(os.environ.get("HDS_WATCHDOG_VDEC", os.pathsep.join(("/proc/msp", "/proc/hisi/msp")))
                    .split(os.pathsep))
CULEGERE_PID_PATH = os.environ.get("HDS_WATCHDOG_CULEGERE_PID", "/tmp/hds-culegere.pid")
# stivele nucleului inainte de repornirea dura (r4): pe receptor /proc/PID/stack nu da stiva unui fir care doarme,
# dar sysrq 'w' scrie in jurnalul nucleului stivele firelor blocate (stare D), cu numele functiilor (KALLSYMS)
SYSRQ_TRIGGER_PATH = os.environ.get("HDS_WATCHDOG_SYSRQ", "/proc/sysrq-trigger")
BLOCAJ_PREFIX = "hds-blocaj-"
BLOCAJ_PASTRATE = 5          # fisiere hds-blocaj-*.txt pastrate in CRASH_LOG_DIR
BLOCAJ_CONTEXT = 120         # randuri din jurnalul nucleului de dinainte de sysrq 'w'
BLOCAJ_ASTEPTARE_S = 1.5     # cat lasam nucleul sa scrie stivele dupa 'w'
BLOCAJ_TERMEN_S = 4.0        # tot drumul (citire, scriere); apoi repornirea oricum
DECODOR_SEMN_PATH = os.environ.get("HDS_WATCHDOG_DECODOR_SEMN", "/home/root/logs/hds-paznic-decodor.repornire")
# acelasi jurnal mic al opririlor ca HDS_CADERI_JURNAL in tools/enigma2.sh.in
CADERI_JURNAL_PATH = os.environ.get("HDS_WATCHDOG_CADERI_JURNAL", "/home/root/logs/hds-caderi.log")
REBOOT_BIN = os.environ.get("HDS_WATCHDOG_REBOOT", "/sbin/reboot")
DEC_GRUP_S = 5.0             # randurile unui esec vin in ~20 ms; la peste atat de ultimul rand incepe alt esec
DEC_FEREASTRA_S = 600        # esecurile se numara pe ultimele 10 minute
DEC_PRAG = 3                 # atatea esecuri sigure in fereastra
DEC_ULTIMUL_MAX_S = 180      # iar ultimul de cel mult atat: lipsa e de acum, nu de acum 10 minute
DEC_CONFIRMARE_S = 30        # canal TV fara niciun decodor in RUN atatea secunde la rand (2-3 verificari)
DEC_O_DATA_LA_S = 3600       # cel mult o repornire a receptorului pentru decodor pe ora
DEC_SEMN_VIITOR_MAX_S = 86400  # un semn cu ora mai departe de atat in viitor nu se crede (ceas mutat la scriere)
DEC_CITIRE_RANDURI = 4000    # inregistrari citite din /dev/kmsg pe o verificare (nucleul scrie mult: „VIDEO_GET_PTS2 -1”)
DEC_CITIRE_S = 0.5           # si cel mult atat timp; restul ramane pentru verificarea urmatoare
DEC_FISIER_MAX = 262144      # octeti noi cititi din messages pe o verificare (peste: numai coada)
DEC_GRUPURI_MAX = 200

_jurnal_nucleu = None        # JurnalNucleu, deschis la prima verificare
_esecuri = []                # grupurile de randuri: [inceput, sfarsit, set(feluri)], pe ceasul monoton
_dec_fara_imagine_de_la = None  # de cand (ceas monoton) arata toate semnele lipsa; None = nu arata
_dec_imagine_la = None       # ultima verificare (ceas monoton) cu un decodor video in RUN, cat jurnalul arata lipsa
_dec_anuntat = None          # felul nivelului 5 scris ultima data in jurnal
_dec_repornire_ceruta = False  # reboot cerut de acest proces: nu se mai cere altul
_dec_copil = None            # procesul reboot, daca nu a iesit in 2 s

# ---- anuntul memoriei pozelor si a filmelor (lotul cadere-radio-2, 14.10.2026) ----
VMALLOCINFO_PATH = os.environ.get("HDS_WATCHDOG_VMALLOCINFO", "/proc/vmallocinfo")
ES_MARIME = 34611200         # maparea demonului platformei in /proc/vmallocinfo (cu pagina de paza); aceeasi cu
                             # HISI_ES_MAP_SIZE din lib/dvb/hdspazavideo.h al enigma2 (testul test_cadere_radio_2)
ES_DEMON = "showiframe"      # demonul platformei, pornit de enigma2.sh odata cu enigma2
ES_PORNIRE_S = 30            # demonul isi face maparea in primele secunde: mai devreme lipsa ei nu se crede
ES_VERIFICARE_S = 60         # vmallocinfo si demonul, cel mult o data pe minut (si pe loc la un esec nou din jurnal)
ES_TOLERANTA_S = 20          # pornirea procesului (tacuri, ceas ajustat de NTP) fata de ceasul inregistrarilor
                             # nucleului (neajustat): pot fugi cateva secunde in zile; esecul demonului de dinainte
                             # e cu o viata a enigma2 mai vechi (minute); o lipsa scapata aici o prinde vmallocinfo

_es_grupuri = []             # randurile esecului maparii: [inceput, sfarsit, set(feluri)], pe ceasul monoton
_es_esec_vazut = None        # ultimul esec al maparii dupa care s-au citit demonul si vmallocinfo
_es_urmatoarea = 0.0         # urmatoarea citire a demonului si a lui vmallocinfo (ceas monoton)
_es_demon = None             # (pid, pornit_la) al demonului la ultima citire, sau None
_es_mapari = None           # maparile de ES_MARIME la ultima citire, sau None (necitit)
_es_anuntat = None           # (fel, cheie) scris ultima data in jurnal
_es_tv_de = None             # de cand (ceas monoton) bataia enigma2 spune redare=tv sau radio fara intrerupere, sau None
_es_imagine = False          # canalul merge de cel putin ES_PORNIRE_S (la ultima citire a lui vmallocinfo)
# r14 (TODO 03.11, jurnal:254, V20): noaptea paznicul scria „memoria pozelor LIPSESTE” si dupa un minut „din nou mapata”,
# cu acelasi demon: o singura citire a lui vmallocinfo fara mapare, urmata de una buna. Lipsa citita din vmallocinfo se
# crede acum numai dupa ES_CITIRI_LIPSA citiri la rand fara mapare, la cel putin ES_VERIFICARE_S una de alta, cu acelasi
# demon si cu un canal pornit; pana atunci starea e „nesigur” (fara rand pe ecran, fara socoteala la repornirea in
# standby). Esecul maparii din jurnalul nucleului ramane crezut pe loc.
ES_CITIRI_LIPSA = 2
_es_zero = None              # (pid-ul demonului, citiri la rand fara mapare, ceasul ultimei citiri numarate) sau None

# ---- nivelul 4, paza rutei hds-netguard (24.09.2026) ----
NETGUARD_IP = "117.78.33.205"
NETGUARD_INTERVAL_S = 180    # la 3 minute: un proces "ip" scurt, deci practic zero procesor
NETGUARD_IP_TIMEOUT_S = 2    # pe comanda "ip" (raspunde in milisecunde); la primul timp depasit verificarea
                              # se opreste, fara wait() nelimitat, deci hranirea (la 15s, prag HW 60s masurat
                              # prin ioctl pe receptorul de proba) nu intarzie periculos
NETGUARD_PAUZA_MAX_S = 1800  # semnul de pauza tine cel mult 30 de minute de la ultima atingere
NETGUARD_IP_BIN = os.environ.get("HDS_WATCHDOG_IP")  # numai pentru probe; altfel ca in hds-netguard
NETGUARD_INITSCRIPT = os.environ.get("HDS_WATCHDOG_NETGUARD_INITSCRIPT", "/etc/init.d/hds-netguard")
NETGUARD_STARE_PATH = os.environ.get("HDS_WATCHDOG_NETGUARD_STARE", "/var/run/hds-netguard.stare")
NETGUARD_PAUZA_PATH = os.environ.get("HDS_WATCHDOG_NETGUARD_PAUZA", "/var/run/hds-netguard.pauza")

_ng_stare = None             # ultima stare publicata (None = inca nicio verificare)
_ng_repuneri = 0
_ng_ultima_repunere = 0
_ng_copii_blocati = []       # "ip" care nu au murit la SIGKILL (stare D); nu se asteapta niciodata dupa ei

# ---- nivelul 6, serviciile de sistem (0.6.7) ----
SERVICII_INTERVAL_S = 60     # o privire in /proc si o conexiune la un soclu local: practic zero procesor
SERVICII_PORNIRE_S = 180     # dupa pornirea receptorului: pana atunci serviciile le porneste rc5 (S02dbus-1, S21, S22)
SERVICII_RC_MAX_S = 900      # r16: cat ruleaza rc/rcS se asteapta, dar nu mai mult de atat de la pornire (rc agatat)
SERVICII_CONFIRMARI = 3      # soclul D-Bus refuzat de atatea ori la rand, cu procesul inca acolo
SERVICII_MAX_ORA = 3         # porniri ale aceluiasi serviciu in ultima ora
SERVICII_TIMEOUT_S = 10      # scriptul de pornire (dbus-1 se desprinde singur cu --fork, avahi cu -D, numele local
                              # porneste un proces in fundal: toate ies sub o secunda); mult sub pragul HW de 60 s
SERVICII_SOCLU_S = 2.0       # conexiunea de proba la soclul D-Bus
INIT_DIR = os.environ.get("HDS_WATCHDOG_INIT_DIR", "/etc/init.d")
# listele de cai: despartite prin os.pathsep (":" pe receptor), ca VDEC_DOSARE
RC_DIRS = tuple(os.environ.get("HDS_WATCHDOG_RC_DIRS", os.pathsep.join(("/etc/rc2.d", "/etc/rc3.d", "/etc/rc4.d",
    "/etc/rc5.d"))).split(os.pathsep))
DBUS_SOCLURI = tuple(os.environ.get("HDS_WATCHDOG_DBUS_SOCLURI", os.pathsep.join(("/var/run/dbus/system_bus_socket",
    "/run/dbus/system_bus_socket"))).split(os.pathsep))
NUME_LOCAL_PID = os.environ.get("HDS_WATCHDOG_NUME_LOCAL_PID", "/var/run/hds-nume-local.pid")
# urma pornirilor, pe disc, langa jurnalul sistemului (se vede in Informatii > Jurnale si dupa o repornire); mica
SERVICII_JURNAL_PATH = os.environ.get("HDS_WATCHDOG_SERVICII_JURNAL", "/home/root/logs/hds-servicii.log")
SERVICII_JURNAL_MAX = 65536
PROC_DIR = os.environ.get("HDS_WATCHDOG_PROC", "/proc")
# (cheia, scriptul din INIT_DIR, procesul cautat dupa nume; None = dupa fisierul pid NUME_LOCAL_PID)
SERVICII = (
    ("dbus", "dbus-1", "dbus-daemon"),
    ("avahi", "avahi-daemon", "avahi-daemon"),
    ("nume-local", "hds-nume-local", None),
)

_srv_urmatoarea = 0.0        # urmatoarea verificare (ceas monoton)
_srv_refuzuri = 0            # soclul D-Bus refuzat la rand, cu procesul acolo
_srv_porniri = {}            # cheie -> [ceas monoton al fiecarei porniri din ultima ora]
_srv_stare = ("", "", 0)     # (servicii, detaliu, ora de perete) pentru STARE_PATH
_srv_reporniri = 0           # porniri facute de nivelul 6 de la pornirea acestui paznic
_srv_anuntat = None          # ultima stare scrisa in jurnal
_srv_copii_blocati = []      # scripturi de pornire care nu au murit la SIGKILL (stare D); nu se asteapta dupa ei
_srv_lipsa = set()           # r16: avahi / numele local fara proces la verificarea de dinainte (dupa pornirea receptorului)
_srv_motiv_scris = set()     # r17: caderile (avahi / numele local) pentru care s-a scris deja randul "de ce"

# r17: de ce lipseste avahi sau numele local (motiv_lipsa). Fisierul pid ramas cu procesul mort = oprit brusc sau
# cazut; lipsa lui = oprit curat (avahi-daemon -k il sterge) sau nepornit. Cai despartite prin os.pathsep.
AVAHI_PID = tuple(os.environ.get("HDS_WATCHDOG_AVAHI_PID", os.pathsep.join(("/run/avahi-daemon/pid",
    "/var/run/avahi-daemon/pid"))).split(os.pathsep))
MOTIV_MESAJE_OCTETI = 65536  # coada lui MESAJE_PATH citita, numai cand un serviciu e socotit cazut
MOTIV_RANDURI = 3            # ultimele randuri ale serviciului din coada
MOTIV_RAND_MAX = 200         # caractere dintr-un rand
# r17: ora salvata (fake-hwclock, UTC, "%Y-%m-%d %H:%M:%S"), pusa ca ora la pornire cat nu e ceas hardware
FAKE_HWCLOCK_PATH = os.environ.get("HDS_WATCHDOG_FAKE_HWCLOCK", "/etc/fake-hwclock.data")
CEAS_TOLERANTA_S = 300       # pornirea socotita pe ceas (acum - uptime) atat de aproape de ora salvata = ceas nemutat

# ioctl-uri standard <linux/watchdog.h> (stabile de zeci de ani, nu se schimba cu kernelul)
WDIOC_GETSUPPORT = 0x80045700
WDIOC_GETTIMEOUT = 0x80045707
WDIOC_KEEPALIVE = 0x80045705

_tracking = {}          # (pid, tid) -> (wchan, numaratoarea la rand, schimbarile de context sau None)
_running = True


def log(msg):
    line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        try:
            if os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
                with open(LOG_PATH, "rb") as f:
                    f.seek(-LOG_MAX_BYTES // 2, os.SEEK_END)
                    tail = f.read()
                with open(LOG_PATH, "wb") as f:
                    f.write(b"--- jurnal scurtat (peste %d octeti) ---\n" % LOG_MAX_BYTES)
                    f.write(tail)
        except (OSError, ValueError):
            pass
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def read_proc_state(pid, tid):
    """Intoarce (litera_stare, wchan) pentru firul tid al procesului pid, sau (None, None) daca a disparut."""
    try:
        with open("/proc/%d/task/%d/status" % (pid, tid), "r") as f:
            state = None
            for line in f:
                if line.startswith("State:"):
                    # ex: "State:\tD (disk sleep)"
                    state = line.split("\t", 1)[1].strip().split(" ", 1)[0]
                    break
        with open("/proc/%d/task/%d/wchan" % (pid, tid), "r") as f:
            wchan = f.read().strip() or "-"
        return state, wchan
    except OSError:
        return None, None


def read_switches(pid, tid):
    """De cate ori s-a oprit si a fost pornit din nou firul tid al procesului pid de cand exista (voluntary_ctxt_switches
    + nonvoluntary_ctxt_switches din /proc/PID/task/TID/status), sau None cand nu se pot citi amandoua."""
    total = 0
    gasite = 0
    try:
        with open("/proc/%d/task/%d/status" % (pid, tid), "r") as f:
            for line in f:
                if line.startswith("voluntary_ctxt_switches:") or line.startswith("nonvoluntary_ctxt_switches:"):
                    total += int(line.split(":", 1)[1].strip())
                    gasite += 1
    except (OSError, ValueError):
        return None
    return total if gasite == 2 else None


def fir_care_lucreaza(pid, tid, inainte, acum):
    """Un fir in D care s-a trezit intre doua verificari: numai pentru firele care nu sunt firul principal, si numai cu
    ambele numaratori citite (None = nu se stie, deci regula veche)."""
    return tid != pid and inainte is not None and acum is not None and acum != inainte


def find_target_pids(name):
    """Cauta procesele cu Name: == name, fara sa depinda de binarul `pidof` (parsare proprie /proc)."""
    pids = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open("/proc/%d/status" % pid, "r") as f:
                for line in f:
                    if line.startswith("Name:"):
                        if line.split("\t", 1)[1].strip() == name:
                            pids.append(pid)
                        break
        except OSError:
            continue
    return pids


def list_threads(pid):
    try:
        return [int(t) for t in os.listdir("/proc/%d/task" % pid) if t.isdigit()]
    except OSError:
        return []


def _citeste_cheie_setare(nume_cheie):
    """O singura cheie din /etc/enigma2/settings ("cheie=valoare" pe rand, format simplu, acelasi tipar
    deja folosit in main/bsod.cpp pentru citirea directa din acest fisier). None daca fisierul sau cheia
    lipsesc -- fisierul poate sa nu existe inca pe un receptor proaspat, niciodata configurat."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8", errors="replace") as f:
            prefix = nume_cheie + "="
            for linie in f:
                if linie.startswith(prefix):
                    return linie[len(prefix):].strip()
    except OSError:
        pass
    return None


def webcontrol_activ_si_port():
    """(activ, port) -- citite din settings daca exista, altfel valorile implicite din
    HdsWebControl/plugin.py. Daca userul a dezactivat DELIBERAT pluginul din Setari, intoarce
    activ=False -- apelantul trebuie sa sara peste verificarea de blocaj moale in acest caz, ca sa nu
    declanseze fals pe o dezactivare intentionata."""
    activ_raw = _citeste_cheie_setare("config.plugins.hdswebcontrol.activ")
    # implicit True (ConfigYesNo default=True). enigma2 scrie „false” cu litera mica
    # (ConfigBoolean.tostring); comparatia veche cu „False” nu vedea oprirea facuta din meniu.
    activ = not _setare_falsa(activ_raw)
    port_raw = _citeste_cheie_setare("config.plugins.hdswebcontrol.port")
    try:
        port = int(port_raw) if port_raw else WEBCONTROL_PORT_IMPLICIT
    except ValueError:
        port = WEBCONTROL_PORT_IMPLICIT
    # portul pe care interfata chiar asculta la aceasta pornire are intaietate (trecerea pe 8080 cand 80 e ocupat)
    try:
        with open(WEBCONTROL_PORT_ACUM_PATH) as f:
            acum = int(f.read(16).strip())
        if 0 < acum < 65536:
            port = acum
    except (OSError, ValueError):
        pass
    return activ, port


def probeaza_webcontrol(port):
    """True daca /api/statusinfo raspunde (orice cod HTTP -- ne intereseaza doar ca reactorul Twisted
    CHIAR proceseaza o cerere, nu continutul). False la orice eroare (refuzat, timeout, resetat)."""
    conexiune = None
    try:
        conexiune = http.client.HTTPConnection("127.0.0.1", port, timeout=SOFT_PROBE_TIMEOUT_S)
        conexiune.request("GET", WEBCONTROL_CALE_PROBA)
        raspuns = conexiune.getresponse()
        raspuns.read(1)  # confirma ca chiar s-a putut citi ceva din corp, nu doar antetul
        return True
    except (OSError, http.client.HTTPException):
        return False
    finally:
        if conexiune is not None:
            try:
                conexiune.close()
            except OSError:
                pass


def _setare_falsa(valoare):
    """True numai pentru o valoare scrisa ca falsa: enigma2 scrie „false” (ConfigBoolean.tostring), de mana se scrie
    uneori „False”. None (cheia lipseste, deci valoarea implicita) nu e falsa."""
    return valoare is not None and valoare.strip().lower() in ("false", "0", "no")


def setari_paznic():
    """(interfata_pornita, asteptare_s), din settings; valorile implicite ca in Components/HdsPaznic.py."""
    brut = _citeste_cheie_setare("config.hds_paznic.interfata")
    interfata = INTERFATA_IMPLICIT if brut is None else not _setare_falsa(brut)
    brut = _citeste_cheie_setare("config.hds_paznic.asteptare")
    try:
        asteptare = int(brut) if brut else ASTEPTARE_IMPLICITA_S
    except ValueError:
        asteptare = ASTEPTARE_IMPLICITA_S
    if asteptare not in ASTEPTARI_PERMISE_S:
        asteptare = ASTEPTARE_IMPLICITA_S
    return interfata, asteptare


def citeste_bataie():
    """Bataia scrisa de enigma2 (Components/HdsPaznic.py) in BATAIE_PATH: {"pid", "bataie", "ocupat" (lista de
    motive), "ocupat_pana"}, cu ceasuri MONOTONE (time.monotonic() in enigma2), sau None daca lipseste sau e stricata."""
    try:
        with open(BATAIE_PATH, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(1024)
    except OSError:
        return None
    d = {}
    for rand in text.splitlines():
        cheie, semn, valoare = rand.partition("=")
        if semn:
            d[cheie.strip()] = valoare.strip()
    try:
        rez = {
            "pid": int(d["pid"]),
            "bataie": float(d["bataie"]),
            "ocupat": [m for m in d.get("ocupat", "").split(",") if m][:5],
            "ocupat_pana": float(d.get("ocupat_pana") or 0),
        }
    except (KeyError, ValueError):
        return None
    # pentru nivelul 5 (Components/HdsPaznic.py, 05.10.2026): None = campul lipseste (imagine veche) sau nu se stie
    rez["redare"] = d.get("redare") or None
    try:
        rez["inregistrare"] = int(d["inregistrare"]) if int(d["inregistrare"]) in (0, 1) else None
    except (KeyError, ValueError):
        rez["inregistrare"] = None
    return rez


def ocupat_valabil(bataie, acum):
    """(motive, secunde_ramase) cat timp semnul „ocupat” al bataii tine (acum = ceas monoton), altfel ([], 0). Un termen
    mai departe de OCUPAT_MAX_S de bataia lui nu se crede (fisier stricat), ca paznicul sa nu fie oprit pe veci."""
    if not bataie or not bataie["ocupat"]:
        return [], 0
    pana = bataie["ocupat_pana"]
    if pana <= acum or pana - bataie["bataie"] > OCUPAT_MAX_S:
        return [], 0
    return bataie["ocupat"], pana - acum


def gaseste_opkg(proc=None):
    """Pid-urile proceselor vii cu numele OPKG_NUME (PROC_DIR/PID/comm, fara zombie: _procese_cu_numele), fara pidof si
    fara lacatul lui opkg. Separat de find_target_pids (care cauta enigma2), ca o cautare sa nu se ia drept cealalta."""
    return _procese_cu_numele(OPKG_NUME, proc)


def opkg_in_lucru(acum, pids=None):
    """Pid-urile proceselor opkg care tin paznicul departe acum (fiecare cel mult OPKG_MAX_S de cand a fost vazut prima
    oara), cu un rand in jurnal la inceput, la sfarsit si o data la termenul depasit. acum = ceas monoton."""
    global _opkg_vazut
    if pids is None:
        pids = gaseste_opkg()
    vazut = {}
    pazite = []
    for pid in pids:
        intrare = _opkg_vazut.get(pid)
        if intrare is None:
            intrare = [acum, False]
            log("opkg pid=%d ruleaza: pana termina, interfata si receptorul nu se repornesc (nivelul 2 cu pragul lung)"
                % pid)
        vazut[pid] = intrare
        if acum - intrare[0] < OPKG_MAX_S:
            pazite.append(pid)
        elif not intrare[1]:
            intrare[1] = True
            log("opkg pid=%d ruleaza de peste %d s: paznicul nu mai asteapta dupa el" % (pid, OPKG_MAX_S))
    for pid, intrare in _opkg_vazut.items():
        if pid not in vazut:
            log("opkg pid=%d a terminat dupa %d s" % (pid, int(acum - intrare[0])))
    _opkg_vazut = vazut
    return pazite


def bataie_cu_opkg(bataie, acum):
    """Copia bataii cu OPKG_MOTIV in semnul „ocupat” si termenul cel putin acum + OPKG_OCUPAT_S: nivelurile 3 si 5 il
    vad ca pe orice lucru lung al enigma2. Fara bataie intoarce None: fara bataia procesului de acum nivelurile 3 si 5
    nu fac nimic oricum. Un semn al enigma2 care nu se mai crede (ocupat_valabil) nu se pastreaza."""
    if bataie is None:
        return None
    b = dict(bataie)
    motive, _ramas = ocupat_valabil(bataie, acum)
    pana = acum + OPKG_OCUPAT_S
    if motive:
        pana = max(pana, bataie["ocupat_pana"])
    b["ocupat"] = ([OPKG_MOTIV] + [m for m in motive if m != OPKG_MOTIV])[:5]
    b["ocupat_pana"] = pana
    return b


def hotarare_blocaj_moale(acum, pid_enigma2, bataie, interfata_pornita, asteptare_s, web_activ, sonda_web):
    """Hotararea nivelului 3, fara efecte (testata in teste/test_paznic_sistem.py).
    acum: ceas monoton; pid_enigma2: procesul enigma2 de acum (None daca nu ruleaza); bataie: citeste_bataie();
    sonda_web: functie fara argumente, chemata NUMAI cand hotararea depinde de ea (True = HdsWebControl raspunde).
    Intoarce (fel, detaliu), fel fiind:
      oprit         repornirea interfetei e oprita din setari (config.hds_paznic.interfata)
      fara-proces   enigma2 nu ruleaza (init il porneste din nou, respawn)
      fara-bataie   nicio bataie de la procesul de acum (pornire, imagine fara Components/HdsPaznic.py, fisier ramas
                    de dinaintea unei reporniri): NU se reporneste nimic numai pe tacerea web
      viu           bataia e mai noua decat asteptarea din setari
      ocupat        bataia s-a oprit, dar semnul „ocupat” (scanare, citirea pistelor, rotirea antenei) inca tine
      web-raspunde  bataia s-a oprit, dar HdsWebControl raspunde: firul principal merge, deci nu se reporneste
      blocat        de repornit: bataia e mai veche decat asteptarea, fara semn „ocupat”, iar HdsWebControl tace sau e
                    oprit din setari"""
    if not interfata_pornita:
        return "oprit", "repornirea interfetei e oprita din setari"
    if pid_enigma2 is None:
        return "fara-proces", "enigma2 nu ruleaza"
    if bataie is None or bataie["pid"] != pid_enigma2:
        return "fara-bataie", "nicio bataie de la enigma2 pid=%d" % pid_enigma2
    varsta = acum - bataie["bataie"]
    if varsta < -5:
        # ceasul monoton o ia de la zero la pornirea receptorului: o bataie „din viitor” e de dinaintea unei reporniri
        return "fara-bataie", "bataie de dinaintea unei reporniri (pid=%d)" % pid_enigma2
    if varsta < asteptare_s:
        return "viu", "bataie de acum %ds" % max(0, int(varsta))
    motive, ramas = ocupat_valabil(bataie, acum)
    if motive:
        return "ocupat", ("bataia oprita de %ds, dar enigma2 e ocupat (%s) inca %ds"
                          % (int(varsta), ",".join(motive), int(ramas)))
    if web_activ and sonda_web():
        return "web-raspunde", "bataia oprita de %ds, dar HdsWebControl raspunde" % int(varsta)
    return "blocat", ("BLOCAJ MOALE CONFIRMAT: enigma2 pid=%d fara bataie de %ds (prag %ds), fara semn ocupat, %s"
                      % (pid_enigma2, int(varsta), asteptare_s,
                         "HdsWebControl nu raspunde" if web_activ else "HdsWebControl oprit din setari"))


def pas_blocaj_moale(acum, pid_enigma2, bataie):
    """Pasul nivelului 3 din bucla principala: hotararea, o linie in jurnal numai la schimbare si, la „blocat”, SIGTERM.
    Intoarce (fel, detaliu, interfata_pornita, asteptare_s)."""
    global _fara_bataie_anuntat, _web_raspunde_anuntat, _ocupat_anuntat
    interfata, asteptare = setari_paznic()
    activ, port = webcontrol_activ_si_port()
    fel, detaliu = hotarare_blocaj_moale(acum, pid_enigma2, bataie, interfata, asteptare, activ,
                                         lambda: probeaza_webcontrol(port))
    if fel == "fara-bataie":
        if _fara_bataie_anuntat != pid_enigma2:
            _fara_bataie_anuntat = pid_enigma2
            log("nivelul 3: %s; interfata nu se reporneste pana nu vine o bataie" % detaliu)
    elif fel == "web-raspunde":
        if _web_raspunde_anuntat != pid_enigma2:
            _web_raspunde_anuntat = pid_enigma2
            log("nivelul 3: %s; interfata nu se reporneste" % detaliu)
    elif fel == "ocupat":
        cheie = (pid_enigma2, tuple(bataie["ocupat"]) if bataie else ())
        if _ocupat_anuntat != cheie:
            _ocupat_anuntat = cheie
            log("nivelul 3: %s; astept" % detaliu)
    elif fel == "viu":
        _web_raspunde_anuntat = None
        _ocupat_anuntat = None
    elif fel == "blocat":
        if _sigterm is not None and _sigterm[0] == pid_enigma2:
            # SIGTERM deja trimis acestui proces: nu se trimite din nou la fiecare verificare; pas_sigkill hotaraste
            detaliu = "asteapta iesirea enigma2 pid=%d dupa SIGTERM" % pid_enigma2
        else:
            log(detaliu)
            force_soft_recovery(detaliu, acum)
    return fel, detaliu, interfata, asteptare


def pas_sigkill(acum, pids):
    """Daca enigma2 nu a iesit la SIGTERM-ul nivelului 3 in SIGKILL_DUPA_S secunde (firul principal blocat nu mai
    ajunge la iesire), SIGKILL. Numai pentru ACELASI pid si numai cat e tot enigma2 (pid-urile se refolosesc)."""
    global _sigterm
    if _sigterm is None:
        return
    pid, cand = _sigterm
    if pid not in pids:
        _sigterm = None
        return
    if acum - cand < SIGKILL_DUPA_S:
        return
    # dupa SIGKILL nu se mai trimite nimic acestui pid (un proces in stare D iese abia cand iese din nucleu; blocajul de
    # nucleu il prinde nivelul 2); _sigterm se sterge cand pid-ul dispare
    _sigterm = (pid, float("inf"))
    # enigma2.sh crede codul 137 drept oprire a paznicului numai cu sigkill= in semn (137 vine si dupa ecranul de cadere)
    scrie_semn_oprire(pid, sigkill=True)
    try:
        os.kill(pid, signal.SIGKILL)
        log("enigma2 pid=%d nu a iesit la SIGTERM in %ds: SIGKILL trimis" % (pid, int(acum - cand)))
    except OSError as e:
        log("SIGKILL catre pid=%d a esuat: %s" % (pid, e))


def scrie_stare_paznic(acum, fel, detaliu, interfata, asteptare, pid_enigma2, bataie, decodor="", memorie_es=None):
    """Starea pentru ecranul „Paznicul receptorului” si pagina web /paznic (Components/HdsPaznic.stare()), atomic
    (.nou + rename), la fiecare verificare. „verificat” e pe ceasul monoton, ca vechimea sa nu sara cu ora.
    decodor: felul nivelului 5 (hotarare_decodor), pentru cine se uita pe receptor. memorie_es: (fel, detaliu, cheie)
    din pas_memorie_es, sau None (nehotarat): enigma2 arata randul de informatie si o socoteste la repornirea
    in standby cu memorie_es=lipsa."""
    proprie = bataie if (bataie is not None and bataie["pid"] == pid_enigma2) else None
    motive, ramas = ocupat_valabil(proprie, acum)
    varsta = int(acum - proprie["bataie"]) if proprie is not None else -1
    if fel in ("viu", "ocupat"):
        stare = "ocupat" if motive else "supraveghez"
    elif fel == "fara-proces":
        stare = "fara-bataie"
    else:
        stare = fel
    ultima = _ng_scurt(_ultima_actiune[0]) if _ultima_actiune[0] else ""
    es_fel, es_detaliu, es_cheie = memorie_es if memorie_es else ("", "", "")
    continut = ("stare=%s\ndetaliu=%s\ninterfata=%d\nasteptare=%d\nocupat=%s\nocupat_ramas=%d\nbataie_varsta=%d\n"
                "placa=1\nplaca_secunde=%d\nreporniri=%d\nultima_actiune=%s\nultima_actiune_ora=%d\n"
                "verificat=%.3f\npid=%d\ndecodor=%s\nmemorie_es=%s\nmemorie_es_cheie=%s\nmemorie_es_detaliu=%s\n"
                "servicii=%s\nservicii_detaliu=%s\nservicii_ora=%d\nservicii_reporniri=%d\n"
                % (stare, _ng_scurt(detaliu or ""), 1 if interfata else 0, asteptare, ",".join(motive), int(ramas),
                   varsta, _placa_secunde, _reporniri_interfata, ultima, int(_ultima_actiune[1]), acum, os.getpid(),
                   decodor or "", es_fel or "", es_cheie or "", _ng_scurt(es_detaliu or ""),
                   _srv_stare[0], _ng_scurt(_srv_stare[1] or ""), int(_srv_stare[2]), _srv_reporniri))
    nou = STARE_PATH + ".nou"
    try:
        with open(nou, "w") as f:
            f.write(continut)
        os.replace(nou, STARE_PATH)
    except OSError:
        pass


def check_health(prag=None, pids=None):
    """Intoarce (healthy, detaliu). healthy=False DOAR cand blocajul e CONFIRMAT (acelasi fir, acelasi
    wchan, de `prag` ori la rand; implicit CONFIRM_HANG_CHECKS) -- orice altceva (proces absent, D trecator, fire noi)
    conteaza drept sanatos pentru scopul hranirii watchdogului, ca sa nu declansam o repornire falsa pe un
    blocaj temporar sau pe un proces care oricum va fi repornit normal de init.
    Cat tine semnul „ocupat” al bataii (scanare, rotirea antenei), bucla principala da
    prag=CONFIRM_HANG_CHECKS_OCUPAT (~5 min): o cautare oarba sau un acord lung pot tine un fir in D peste un minut,
    iar o repornire dura in mijlocul scanarii nu are voie sa se intample. Un blocaj adevarat de
    nucleu tot se prinde, doar mai tarziu; watchdog-ul hardware ramane neschimbat."""
    global _tracking

    if prag is None:
        prag = CONFIRM_HANG_CHECKS
    if pids is None:
        pids = find_target_pids(TARGET_PROCESS)
    if not pids:
        # Procesul nu ruleaza -- nu e "blocat", e absent (init il reporneste singur, cf. inittab).
        _tracking = {}
        return True, "proces %s absent (normal, respawn separat prin inittab)" % TARGET_PROCESS

    d_state_now = {}   # (pid, tid) -> (wchan, schimbarile de context; None pentru firul principal sau necitite)
    lasate = 0         # fire CEC lasate deoparte (WCHAN_FIRE_LASATE_DEOPARTE), in D, neurmarite
    for pid in pids:
        # firul principal mort (zombie): procesul nu se mai poate termina, deci nimic nu se mai iarta (r11)
        principal_viu = read_proc_state(pid, pid)[0] not in STARI_FIR_PRINCIPAL_MORT
        for tid in list_threads(pid):
            state, wchan = read_proc_state(pid, tid)
            if state == "D":
                if principal_viu and tid != pid and (wchan or "").startswith(WCHAN_FIRE_LASATE_DEOPARTE):
                    lasate += 1
                    continue
                d_state_now[(pid, tid)] = (wchan, read_switches(pid, tid) if tid != pid else None)
        # r12, raportul 481062: un Oops opreste numai firul care l-a facut. Firul principal ramane Z, celelalte fire raman vii
        # si nu sunt in D, deci procesul nu se termina si init nu porneste alta interfata: ecran negru pentru totdeauna
        if not principal_viu and not any(cheie[0] == pid for cheie in d_state_now) and len(list_threads(pid)) > 1:
            d_state_now[(pid, pid)] = ("fir-principal-mort", None)

    new_tracking = {}
    hang_detail = None
    lucreaza = 0
    for key, (wchan, schimbari) in d_state_now.items():
        prev = _tracking.get(key)
        if prev and prev[0] == wchan and not fir_care_lucreaza(key[0], key[1], prev[2], schimbari):
            count = prev[1] + 1
        else:
            count = 1
            if prev and prev[0] == wchan:
                lucreaza += 1
        new_tracking[key] = (wchan, count, schimbari)
        if count >= prag:
            hang_detail = (key, wchan, count)
    _tracking = new_tracking

    if hang_detail:
        (pid, tid), wchan, count = hang_detail
        return False, ("BLOCAJ CONFIRMAT: pid=%d tid=%d stare=D wchan=%s de %d verificari la rand "
                        "(~%ds)" % (pid, tid, wchan, count, count * PET_INTERVAL_S))
    if d_state_now:
        if lucreaza:
            return True, ("fire in D, inca sub prag (%d urmarite, din care %d se trezesc intre verificari)"
                          % (len(d_state_now), lucreaza))
        return True, "fire in D, inca sub prag (%d urmarite)" % len(d_state_now)
    if lasate:
        return True, "sanatos (%d fir CEC lasat deoparte de enigma2, in D)" % lasate
    return True, "sanatos"


def open_watchdog():
    """Deschide watchdogul HW. Daca lipseste sau il tine altcineva (pe unele receptoare Vu+ 4K /dev/watchdog nu e
    al nostru), paznicul merge mai departe fara partea HW: altfel cadea la pornire, init il repornea in bucla
    (respawning too fast) si receptorul ramanea fara paznic, fara niciun rand in jurnal."""
    global _placa_secunde
    try:
        fd = os.open(DEVICE_PATH, os.O_WRONLY)
    except OSError as e:
        log("watchdog HW indisponibil, %s (%s): paznicul merge fara el, repornirea la blocaj numai prin sysrq" % (
            DEVICE_PATH, e))
        return None
    try:
        buf = struct.pack("I", 0)
        buf = fcntl.ioctl(fd, WDIOC_GETTIMEOUT, buf)
        (timeout_s,) = struct.unpack("I", buf)
        _placa_secunde = timeout_s
        log("watchdog HW deschis, %s, timeout activ raportat de driver: %ds" % (DEVICE_PATH, timeout_s))
    except OSError as e:
        log("watchdog HW deschis, %s (nu am putut citi timeout-ul prin ioctl: %s -- "
            "continui cu presupunerea documentata, 60s, sp805_wdt.c DEFAULT_TIMEOUT)" % (DEVICE_PATH, e))
    return fd


def pet(fd):
    if fd is None:
        return
    os.write(fd, b"\0")


def disarm_and_close(fd):
    """Oprire CURATA -- doar la opriri/reporniri normale, intentionate ale sistemului (SIGTERM de la
    init la schimbare de runlevel), NU la blocaj. 'V' (magic close) cere driverului sa dezarmeze."""
    if fd is None:
        return
    try:
        os.write(fd, b"V")
    except OSError:
        pass
    os.close(fd)


def ensure_crash_log_dir():
    """Dosarul jurnalelor de cadere, la pornire, INAINTE ca enigma2 sa apuce sa cada.
    Pe Viper 4K V20 /media e un tmpfs de 64 KB fara /media/hdd: un jurnal scris acolo s-ar pierde la repornire si ar
    umple repede cei 64 KB. bsod.cpp, mytest.py si Screens/HdsCrashlogAutoSubmit.py folosesc CRASH_LOG_DIR
    (/home/root/logs, pe memoria interna, unde stau si celelalte jurnale), deci /media/hdd nu se mai creeaza. Pe
    memoria interna raman numai ultimele CRASH_LOG_PASTRATE jurnale (curata_jurnale_cadere), ca o cadere in bucla sa
    nu umple memoria."""
    try:
        if not os.path.isdir(CRASH_LOG_DIR):
            os.makedirs(CRASH_LOG_DIR, exist_ok=True)
            log("creat %s (lipsea) pentru jurnalele de cadere ale enigma2" % CRASH_LOG_DIR)
    except OSError as e:
        log("nu am putut crea %s: %s -- bsod.cpp scrie atunci jurnalul in /tmp" % (CRASH_LOG_DIR, e))
    curata_jurnale_cadere()


def curata_jurnale_cadere():
    """Pastreaza numai ultimele CRASH_LOG_PASTRATE jurnale enigma2_crash_*.log din CRASH_LOG_DIR (cele mai noi dupa data
    fisierului, apoi dupa nume). Nu arunca niciodata. Intoarce cate a sters."""
    try:
        nume = [n for n in os.listdir(CRASH_LOG_DIR) if n.startswith("enigma2_crash_") and n.endswith(".log")]
    except OSError:
        return 0
    if len(nume) <= CRASH_LOG_PASTRATE:
        return 0

    def cheie(n):
        try:
            return (os.stat(os.path.join(CRASH_LOG_DIR, n)).st_mtime, n)
        except OSError:
            return (0, n)

    nume.sort(key=cheie)
    sterse = 0
    for n in nume[:-CRASH_LOG_PASTRATE]:
        try:
            os.remove(os.path.join(CRASH_LOG_DIR, n))
            sterse += 1
        except OSError:
            pass
    if sterse:
        log("jurnale de cadere: sterse %d vechi din %s, raman ultimele %d" % (sterse, CRASH_LOG_DIR, CRASH_LOG_PASTRATE))
    return sterse


def _prinde_semnalul(pid, sig):
    """True daca procesul are o functie pentru semnalul `sig` (masca SigCgt din /proc/<pid>/status). Un semnal de timp
    real fara functie ar opri procesul, deci fara ea nu se trimite."""
    try:
        with open("/proc/%d/status" % pid) as f:
            for rand in f:
                if rand.startswith("SigCgt:"):
                    return bool((int(rand.split()[1], 16) >> (sig - 1)) & 1)
    except (OSError, ValueError, IndexError):
        pass
    return False


def _marime(cale):
    try:
        return os.path.getsize(cale)
    except OSError:
        return -1


def _trimite_cererea_stivelor(pid, semn):
    """Un rand cu semnul cererii in teava firului de stive al enigma2 pid (STIVE_CERERE). -> True daca a ajuns la un
    cititor; False fara teava, fara cititor (enigma2 mai vechi, firul nepornit, procesul mort) sau cand calea nu e o teava.
    Nu asteapta si nu arunca."""
    cale = STIVE_CERERE % pid if "%d" in STIVE_CERERE else STIVE_CERERE
    try:
        fd = os.open(cale, os.O_WRONLY | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return False
    try:
        if not stat.S_ISFIFO(os.fstat(fd).st_mode):
            return False
        os.write(fd, ("%s\n" % semn).encode("ascii"))
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _asteapta_raspunsul_stivelor(inainte, semn, termen):
    """True cand partea noua a STIVE_PATH (de la octetul inainte) are randul de sfarsit al cererii semn, in cel mult
    termen secunde."""
    sfarsit = (STIVE_SFARSIT + semn).encode("ascii")
    capat = time.monotonic() + termen
    while True:
        try:
            with open(STIVE_PATH, "rb") as f:
                f.seek(inainte)
                if sfarsit in f.read(STIVE_MAX_OCTETI):
                    return True
        except OSError:
            pass
        if time.monotonic() >= capat:
            return False
        time.sleep(0.1)


def alege_semnalul_stivelor(oprire, nou, trimisa):
    """Semnalul faulthandler cand firul de stive n-a raspuns, sau None. oprire: procesul e oprit imediat dupa (SIGTERM);
    nou: enigma2 prinde STIVE_TOATE_SEMNAL (0.7.7+, la el STIVE_SEMNAL da numai firul principal); trimisa: cererea a ajuns
    la firul de stive, deci tacerea lui inseamna lacatul Python tinut."""
    if oprire:
        # toate firele numai cand niciun alt fir nu poate rula cod Python; un enigma2 mai vechi le da oricum pe STIVE_SEMNAL
        return STIVE_TOATE_SEMNAL if (nou and trimisa) else STIVE_SEMNAL
    # diagnostic (procesul merge mai departe): numai firul principal, sigur oricand; la un enigma2 mai vechi nimic
    return STIVE_SEMNAL if nou else None


def cere_stivele(pid, anunta=True, oprire=True):
    """Inainte de SIGTERM (oprire=True) sau la diagnostic (oprire=False, procesul nu e oprit): stivele firelor Python ale
    enigma2 in STIVE_PATH. Intai cererea catre firul de stive al enigma2 (toate firele, citite din Python, sigur oricand);
    daca nu raspunde in STIVE_PYTHON_S, semnalul faulthandler ales de alege_semnalul_stivelor (merge si cu firul principal
    blocat). Partea noua se copiaza in CRASH_LOG_DIR/enigma2-stive-<data>.txt, cu ultimele CRASH_LOG_PASTRATE pastrate.
    -> calea copiei sau None. anunta=False: apelantul scrie randul cu motivul. Nu arunca."""
    global _ultimul_nucleu
    if not _prinde_semnalul(pid, STIVE_SEMNAL):
        return None
    # inainte de cerere si de semnal (semnalul scoate firele din apelul in care stau): ce vede nucleul la fiecare fir
    nucleu, _ultimul_nucleu = fire_in_nucleu(pid)
    inainte = max(_marime(STIVE_PATH), 0)
    semn = "%d" % int(time.monotonic() * 1000)
    trimisa = _trimite_cererea_stivelor(pid, semn)
    if trimisa and _asteapta_raspunsul_stivelor(inainte, semn, STIVE_PYTHON_S):
        cum = "citite din Python"
    else:
        sig = alege_semnalul_stivelor(oprire, _prinde_semnalul(pid, STIVE_TOATE_SEMNAL), trimisa)
        if sig is None:
            return None
        cum = "din semnal, %s" % ("toate firele" if sig == STIVE_TOATE_SEMNAL else "semnalul %d" % sig)
        try:
            os.kill(pid, sig)
        except OSError:
            return None
        capat = time.monotonic() + STIVE_ASTEPTARE_S
        ultima = max(_marime(STIVE_PATH), inainte)
        while time.monotonic() < capat:
            time.sleep(0.2)
            m = _marime(STIVE_PATH)
            if m > inainte and m == ultima:
                break
            ultima = m
    try:
        with open(STIVE_PATH, "rb") as f:
            f.seek(inainte)
            date = f.read(STIVE_MAX_OCTETI)
    except OSError:
        return None
    if not date:
        return None
    try:
        os.makedirs(CRASH_LOG_DIR, exist_ok=True)
        cale = os.path.join(CRASH_LOG_DIR, "%s%s-%d.txt" % (STIVE_PREFIX, time.strftime("%Y%m%d-%H%M%S"), pid))
        with open(cale, "wb") as f:
            if nucleu:
                f.write(("== firele enigma2 vazute de nucleu (inainte de semnal)\n%s\n== stivele Python (%s)\n" %
                         (nucleu, cum)).encode("utf-8", "replace"))
            f.write(date)
        vechi = sorted(n for n in os.listdir(CRASH_LOG_DIR) if n.startswith(STIVE_PREFIX) and n.endswith(".txt"))
        for n in vechi[:-CRASH_LOG_PASTRATE]:
            try:
                os.remove(os.path.join(CRASH_LOG_DIR, n))
            except OSError:
                pass
    except OSError as e:
        log("stivele enigma2 nu s-au putut pastra: %s" % e)
        return None
    if anunta:
        log("stivele firelor Python ale enigma2 pid=%d pastrate in %s (%s)%s" % (pid, cale, cum,
            ("; firul principal in nucleu: %s" % _ultimul_nucleu) if _ultimul_nucleu else ""))
    return cale


# 0.7.5 (PRN): numerele apelurilor de sistem care spun unde sta un fir (ARM EABI si MIPS o32), pentru stivele de mai sus.
# Pachetul 1433 (SF8008, 12.11): firul principal sta in C++ (stiva Python arata numai e2reactor.py poll), deci numai
# nucleul mai poate spune in ce apel si pe ce dispozitiv.
APELURI_SISTEM = {
    3: "read", 4: "write", 5: "open", 54: "ioctl", 142: "select", 162: "nanosleep", 168: "poll", 240: "futex",
    252: "epoll_wait", 322: "openat", 335: "pselect6", 336: "ppoll", 265: "clock_nanosleep",
    4003: "read", 4004: "write", 4005: "open", 4054: "ioctl", 4142: "select", 4166: "nanosleep", 4188: "poll",
    4238: "futex", 4250: "epoll_wait", 4288: "openat", 4301: "pselect6", 4302: "ppoll", 4265: "clock_nanosleep",
}
APELURI_CU_FD = ("read", "write", "ioctl")


def _citeste_scurt(cale, maxim=256):
    try:
        with open(cale) as f:
            return f.read(maxim).strip()
    except (OSError, ValueError):
        return ""


def apel_din_syscall(text, pid, citeste_legatura=None):
    """Randul din /proc/<pid>/task/<tid>/syscall -> text scurt: „ioctl /dev/dvb/adapter0/frontend0 cerere 0x...”, „in
    lucru (cod obisnuit, nu in nucleu)”, „futex” etc. Nu arunca."""
    citeste_legatura = citeste_legatura or os.readlink
    campuri = (text or "").split()
    if not campuri:
        return "necunoscut"
    if campuri[0] == "running":
        return "in lucru (cod obisnuit, nu in nucleu)"
    try:
        nr = int(campuri[0])
    except ValueError:
        return "necunoscut"
    if nr < 0:
        return "in nucleu, fara apel de sistem"
    nume = APELURI_SISTEM.get(nr, "apelul %d" % nr)
    if nume in APELURI_CU_FD and len(campuri) > 1:
        try:
            fd = int(campuri[1], 16)
            tinta = citeste_legatura("/proc/%d/fd/%d" % (pid, fd))
        except (ValueError, OSError):
            tinta = "fd ?"
        nume = "%s %s" % (nume, tinta)
        if nume.startswith("ioctl") and len(campuri) > 2:
            nume += " cerere %s" % campuri[2]
    return nume


def fire_in_nucleu(pid, radacina="/proc"):
    """(textul tuturor firelor: fir nume stare wchan apel, rezumatul firului principal) pentru enigma2 pid. Nu arunca;
    fara /proc -> ("", "")."""
    randuri = []
    principal = ""
    try:
        firele = sorted(int(t) for t in os.listdir("%s/%d/task" % (radacina, pid)) if t.isdigit())
    except (OSError, ValueError):
        return "", ""
    for tid in firele[:64]:
        baza = "%s/%d/task/%d/" % (radacina, pid, tid)
        nume = _citeste_scurt(baza + "comm", 64)
        stat = _citeste_scurt(baza + "stat", 512)
        stare = stat.rsplit(")", 1)[1].split()[0] if ")" in stat and stat.rsplit(")", 1)[1].split() else "?"
        wchan = _citeste_scurt(baza + "wchan", 128) or "0"
        apel = apel_din_syscall(_citeste_scurt(baza + "syscall", 256), pid)
        randuri.append("fir=%d nume=%s stare=%s wchan=%s apel=%s" % (tid, nume, stare, wchan, apel))
        if tid == pid:
            principal = "stare=%s wchan=%s apel=%s" % (stare, wchan, apel)
    return "\n".join(randuri), principal


def uptime_secunde():
    """Secundele intregi din /proc/uptime (acelasi ceas ca enigma2.sh: cut -d. -f1 /proc/uptime), sau None."""
    up = uptime_precis()
    return int(up) if up is not None else None


def uptime_precis():
    """/proc/uptime cu fractiunile de secunda, pentru compararea pornirii procesului cu bataia monotona."""
    try:
        with open(UPTIME_PATH) as f:
            up = float(f.read(64).split()[0])
        return up if 0 <= up < float("inf") else None
    except (OSError, ValueError, IndexError):
        return None


def citeste_pornirea_enigma2(pid):
    """(parinte, pornit_la) din /proc/PID/stat, ori None. Campul 22 e in tacuri SC_CLK_TCK, pe ceasul uptime.
    Numele procesului poate contine spatii si paranteze; campurile se numara numai dupa ultima paranteza."""
    try:
        with open(os.path.join(PROC_DIR, str(pid), "stat")) as f:
            text = f.read(2048)
        campuri = text[text.rindex(")") + 2:].split()
        tata, tacuri = int(campuri[1]), int(campuri[19])
        hz = os.sysconf("SC_CLK_TCK")
        if tata <= 0 or tacuri < 0 or hz <= 0:
            return None
        return tata, tacuri / float(hz)
    except (AttributeError, OSError, ValueError, IndexError, TypeError):
        return None


def citeste_iesirea_enigma2(proces):
    """Semnul enigma2.sh numai pentru parintele vechi si numai dupa pornirea lui; altfel None.
    Nu foloseste mtime sau ora de perete si nu presupune ca pid-ul a fost asteptat de acest paznic."""
    if proces["parinte"] is None or proces["pornit_la"] is None:
        return None
    try:
        with open(IESIRE_PATH, encoding="utf-8", errors="replace") as f:
            text = f.read(IESIRE_MAX_OCTETI)
        d = {}
        for rand in text.splitlines():
            cheie, semn, valoare = rand.partition("=")
            if semn:
                d[cheie.strip()] = valoare.strip()
        cod, tata, up = int(d["cod"]), int(d["parinte"]), int(d["uptime"])
        if tata != proces["parinte"] or not up > proces["pornit_la"] or not 0 <= cod <= 255:
            return None
        return {"cod": cod, "parinte": tata, "uptime": up, "fel": d.get("fel", ""),
                "cauza": d.get("cauza", ""), "motiv_fel": d.get("motiv_fel", "")}
    except (OSError, ValueError, KeyError):
        return None


def descrie_iesirea_enigma2(iesire):
    """Textul codului pentru un singur rand de jurnal; fara efecte si fara newline din semnul shell-ului."""
    if iesire is None:
        return "cod necunoscut"
    cod, fel = iesire["cod"], iesire["fel"]
    if cod == 3:
        descriere = "repornirea interfetei"
    else:
        descriere = {"repornire": "repornirea interfetei", "oprire": "oprire",
                     "receptor": "repornirea receptorului", "semnal": "semnal", "python": "eroare Python"}.get(fel, "")
        if not descriere and cod > 128:
            descriere = "semnal"
        motiv = " ".join((iesire["cauza"] or iesire["motiv_fel"]).split())[:240]
        if motiv:
            descriere = "%s: %s" % (descriere, motiv) if descriere else motiv
    return "cod %d%s" % (cod, " (%s)" % descriere if descriere else "")


def jurnal_iesire_enigma2(proces, uptime_acum):
    """Un singur rand despre procesul vechi; uptime din semnul corelat da durata exacta, nu pasul de 15 s."""
    iesire = citeste_iesirea_enigma2(proces)
    sfarsit = iesire["uptime"] if iesire is not None else uptime_acum
    durata = ("%d s" % max(0, int(sfarsit - proces["pornit_la"]))
              if sfarsit is not None and proces["pornit_la"] is not None else "necunoscut")
    if proces["prima_bataie"] == PRIMA_BATAIE_NECUNOSCUTA:
        prima = "prima bataie inainte de pornirea paznicului"
    else:
        prima = ("prima bataie dupa %d s" % proces["prima_bataie"]
                 if proces["prima_bataie"] is not None else "fara nicio bataie")
    log("enigma2 pid=%d a iesit: %s, a mers %s, %s" %
        (proces["pid"], descrie_iesirea_enigma2(iesire), durata, prima))


def pas_viata_enigma2(acum, pid_enigma2, bataie, diagnostic=True):
    """Observa procesul si prima bataie; stive la 180 si 600 s fara nicio bataie. Nicio recuperare sau asteptare noua.
    acum e monoton (ca bataia); inceputul si durata sunt pe /proc/uptime. Metadatele raman dupa disparitia din /proc.
    O bataie veche, dinaintea procesului ori din viitor, nu poate opri diagnosticul pornirii.
    diagnostic=False pastreaza jurnalul vietii fara a cere stive cand repornirea dura e deja in curs."""
    global _viata_enigma2
    up = uptime_precis()
    pornire = citeste_pornirea_enigma2(pid_enigma2) if pid_enigma2 is not None else None
    vechi = _viata_enigma2
    schimbat = vechi is not None and (pid_enigma2 != vechi["pid"] or (
        pornire is not None and vechi["pornit_la"] is not None and pornire[1] != vechi["pornit_la"]))
    if schimbat:
        _viata_enigma2 = None  # chiar daca jurnalul nu poate fi scris, acelasi proces nu se anunta de doua ori
        jurnal_iesire_enigma2(vechi, up)
    if pid_enigma2 is None:
        return
    if _viata_enigma2 is None:
        _viata_enigma2 = {"pid": pid_enigma2, "parinte": None, "pornit_la": None,
                          "prima_bataie": None, "stive": 0}
    proces = _viata_enigma2
    if proces["pornit_la"] is None and pornire is not None:
        proces["parinte"], proces["pornit_la"] = pornire
    if up is None or proces["pornit_la"] is None:
        return
    varsta = up - proces["pornit_la"]
    if (proces["prima_bataie"] is None and bataie is not None and bataie["pid"] == pid_enigma2
            and _paznic_pornit_la is not None and proces["pornit_la"] < _paznic_pornit_la
            and not proces.get("vazut_fara_bataie")):
        # pornit inainte de acest paznic si bate deja la prima privire: prima bataie nu se poate sti
        proces["prima_bataie"] = PRIMA_BATAIE_NECUNOSCUTA
    if proces["prima_bataie"] is None and (bataie is None or bataie["pid"] != pid_enigma2):
        proces["vazut_fara_bataie"] = True
    if proces["prima_bataie"] is None and bataie is not None and bataie["pid"] == pid_enigma2:
        intarziere = varsta - (acum - bataie["bataie"])
        if 0 <= intarziere <= varsta and bataie["bataie"] <= acum:
            proces["prima_bataie"] = int(round(intarziere))
            if intarziere > PRIMA_BATAIE_LUNGA_S:
                log("enigma2 pid=%d prima bataie dupa %d s de la pornire" % (pid_enigma2, proces["prima_bataie"]))
    if proces["prima_bataie"] is not None or not diagnostic:
        return
    praguri = (STIVE_FARA_BATAIE_S, STIVE_FARA_BATAIE_DIN_NOU_S)
    if proces["stive"] < len(praguri) and varsta >= praguri[proces["stive"]]:
        proces["stive"] += 1  # se incearca o data la fiecare prag, inclusiv daca procesul nu poate da stivele
        cale = cere_stivele(pid_enigma2, anunta=False, oprire=False)
        rezultat = ("stivele firelor Python pastrate in %s" % cale if cale else
                    "stivele firelor Python nu s-au putut pastra")
        log("enigma2 pid=%d fara nicio bataie de %d s de la pornire: %s%s" % (pid_enigma2, int(varsta), rezultat,
            ("; firul principal in nucleu: %s" % _ultimul_nucleu) if cale and _ultimul_nucleu else ""))


def parinte(pid):
    """PPid-ul procesului, din /proc/<pid>/status (pentru enigma2: enigma2.sh, care ii asteapta iesirea), sau None."""
    try:
        with open("/proc/%d/status" % pid) as f:
            for rand in f:
                if rand.startswith("PPid:"):
                    return int(rand.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def scrie_semn_oprire(pid, sigkill=False, motiv="blocaj-moale"):
    """Semnul pentru tools/enigma2.sh.in, inainte de SIGTERM si de SIGKILL catre enigma2: iesirea care urmeaza e ceruta de
    paznic pentru un blocaj moale, deci nu se socoteste placii 2D. Randuri „cheie=valoare”: pid, parinte (enigma2.sh care
    asteapta acest enigma2: $$ acolo), uptime (secunde intregi din /proc/uptime la scriere), motiv; inainte de SIGKILL si
    sigkill=<uptime>. In RAM, atomic (.nou + rename). Fara parinte (sau cu init drept parinte) ori fara ceas nu se scrie
    nimic: enigma2.sh aplica atunci regula de azi. Intoarce True daca s-a scris. Nu arunca."""
    try:
        tata = parinte(pid)
        up = uptime_secunde()
        if tata is None or tata <= 1 or up is None:
            return False
        # motiv: blocaj-moale (nivelul 3) sau iesire-ceruta (0.7.6, pas_iesire_ceruta); enigma2.sh il pune in randul lui
        text = "pid=%d\nparinte=%d\nuptime=%d\nmotiv=%s\n" % (pid, tata, up, motiv)
        if sigkill:
            text += "sigkill=%d\n" % up
        nou = OPRIRE_PATH + ".nou"
        with open(nou, "w") as f:
            f.write(text)
        os.replace(nou, OPRIRE_PATH)
        return True
    except Exception as e:
        log("semnul opririi pentru enigma2.sh nu s-a scris (%s): %r" % (OPRIRE_PATH, e))
        return False


def force_soft_recovery(reason, acum=None):
    """Recuperare BLANDA -- STRICT SIGTERM catre enigma2, nu repornire dura. `init` are deja intrare
    "respawn" pentru enigma2 (/etc/inittab) -- exact recuperarea verificata manual, de
    doua ori, in aceeasi sesiune (STADIU-PROIECT-IMAGINE.md, ancheta EBUSY/dvb_audio_open): proces nou in
    ~8s, uptime-ul sistemului neschimbat. NU atinge watchdogul HW -- kernelul e sanatos in acest caz, doar
    un serviciu al lui enigma2 e blocat. Pid-ul si ora (ceas monoton) se tin minte pentru SIGKILL
    (pas_sigkill), iar repornirea se numara pentru ecran si web."""
    global _sigterm, _reporniri_interfata, _ultima_actiune
    log("recuperare blanda (SIGTERM catre enigma2): %s" % reason)
    pids = find_target_pids(TARGET_PROCESS)
    if not pids:
        log("recuperare blanda: procesul %s a disparut deja intre timp, nimic de facut" % TARGET_PROCESS)
        return
    if acum is None:
        acum = time.monotonic()
    for pid in pids:
        # inaintea oricarui semnal: enigma2.sh afla ca iesirea care urmeaza e ceruta de paznic, nu o cadere a placii 2D
        scrie_semn_oprire(pid)
        cere_stivele(pid)
        try:
            os.kill(pid, signal.SIGTERM)
            log("SIGTERM trimis catre pid=%d" % pid)
            _sigterm = (pid, acum)
        except OSError as e:
            log("SIGTERM catre pid=%d a esuat: %s" % (pid, e))
    _reporniri_interfata += 1
    _ultima_actiune = ("interfata repornita: nu a mai raspuns", time.time())


def citeste_semn_iesire():
    """Semnul iesirii cerute (Components/HdsPaznic.iesireInceputa, IESIRE_CERUTA_PATH): {"pid", "ceruta" (ceas monoton),
    "cod" (None = necunoscut), "tema", "ecrane"}, sau None daca lipseste ori e stricat. Citit marginit."""
    try:
        with open(IESIRE_CERUTA_PATH, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(IESIRE_MAX_OCTETI)
    except OSError:
        return None
    d = {}
    for rand in text.splitlines():
        cheie, semn, valoare = rand.partition("=")
        if semn:
            d[cheie.strip()] = valoare.strip()
    try:
        rez = {"pid": int(d["pid"]), "ceruta": float(d["ceruta"])}
        cod = d.get("cod", "-")
        rez["cod"] = None if cod in ("", "-") else int(cod)
    except (KeyError, ValueError):
        return None
    rez["tema"] = " ".join(d.get("tema", "").split())[:160]
    rez["ecrane"] = " ".join(d.get("ecrane", "").split())[:240]
    return rez


def proces_enigma2_viu(pid, proc=None):
    """True cat procesul pid exista si e tot TARGET_PROCESS (PROC_DIR/<pid>/comm; pid-urile se refolosesc). Un proces cu
    firul principal terminat ("Z") si alte fire inca vii se socoteste viu: exact cel care nu mai iese."""
    try:
        with open(os.path.join(proc or PROC_DIR, str(pid), "comm")) as f:
            return f.read().strip() == TARGET_PROCESS
    except OSError:
        return False


def hotarare_iesire_ceruta(acum, semn, viu, interfata_pornita, opkg):
    """Fara efecte (teste/test_wdg_iesire_ceruta_076.py). acum: ceas monoton; semn: citeste_semn_iesire(); viu: procesul
    semnului inca exista; opkg: un opkg ruleaza (r14: atunci nu se reporneste nimic). -> (fel, detaliu), fel fiind:
      fara        niciun semn
      iesit       procesul semnului nu mai exista (iesirea s-a terminat)
      alt-cod     o iesire pe care paznicul nu o atinge (IESIRE_CODURI_NEATINSE: caderea, 5)
      oprit       repornirea interfetei e oprita din setari (config.hds_paznic.interfata)
      ocupat      un opkg ruleaza
      asteapta    mai putin de IESIRE_CERUTA_S secunde de la semn
      opreste     procesul nu a iesit in IESIRE_CERUTA_S secunde: SIGTERM, apoi SIGKILL"""
    if semn is None:
        return "fara", ""
    pid = semn["pid"]
    if not viu:
        return "iesit", "enigma2 pid=%d a iesit" % pid
    cod = semn["cod"]
    if cod in IESIRE_CODURI_NEATINSE:
        return "alt-cod", "iesirea enigma2 pid=%d cu codul %d nu se atinge" % (pid, cod)
    if not interfata_pornita:
        return "oprit", "repornirea interfetei e oprita din setari"
    varsta = acum - semn["ceruta"]
    if varsta < -5:
        # ceasul monoton o ia de la zero la pornirea receptorului (/var/run e oricum in RAM)
        return "fara", "semnul iesirii de dinaintea unei reporniri (pid=%d)" % pid
    if opkg:
        return "ocupat", "enigma2 pid=%d iese de %ds, dar opkg ruleaza" % (pid, int(varsta))
    if varsta < IESIRE_CERUTA_S:
        return "asteapta", "enigma2 pid=%d iese de %ds" % (pid, max(0, int(varsta)))
    return "opreste", ("enigma2 pid=%d nu a iesit la repornire in %d s (a asteptat %d s; cod %s, tema %s, ecranele: %s)"
                       % (pid, IESIRE_CERUTA_S, int(varsta), "necunoscut" if cod is None else cod,
                          semn["tema"] or "necunoscuta", semn["ecrane"] or "nestiute"))


def firele_ramase(pid, maxim=400):
    """Firele procesului care nu iese, pe un rand: nume (stare, wchan), cel mult maxim caractere."""
    text, _principal = fire_in_nucleu(pid, PROC_DIR)
    parti = []
    for rand in text.splitlines():
        d = dict(c.split("=", 1) for c in rand.split() if "=" in c)
        parti.append("%s (%s, %s)" % (d.get("nume", "?") or "?", d.get("stare", "?"), d.get("wchan", "?")))
    return (", ".join(parti) or "necitite")[:maxim]


def pas_iesire_ceruta(acum, opkg):
    """Pasul iesirii cerute din bucla principala (inainte de nivelul 3): hotararea si, la "opreste", randul in jurnale,
    stivele, semnul opririi si SIGTERM; SIGKILL dupa IESIRE_SIGKILL_DUPA_S. _sigterm primeste pid-ul (cu ceas infinit):
    nivelul 3 nu mai trimite inca un SIGTERM, pas_sigkill nu se amesteca, iar nivelul 5 stie ca o oprire e in curs.
    Intoarce felul hotararii (sau "sigterm"/"sigkill" cat urmareste o oprire)."""
    global _iesire_oprita, _sigterm, _reporniri_interfata, _ultima_actiune
    if _iesire_oprita is not None:
        pid, cand, ucis = _iesire_oprita
        if not proces_enigma2_viu(pid):
            log("enigma2 pid=%d a iesit dupa oprirea paznicului (%d s de la SIGTERM)" % (pid, int(acum - cand)))
            _iesire_oprita = None
            if _sigterm is not None and _sigterm[0] == pid:
                _sigterm = None
            return "iesit"
        if ucis:
            return "sigkill"
        if acum - cand < IESIRE_SIGKILL_DUPA_S:
            return "sigterm"
        _iesire_oprita[2] = True
        scrie_semn_oprire(pid, sigkill=True, motiv="iesire-ceruta")
        try:
            os.kill(pid, signal.SIGKILL)
            log("enigma2 pid=%d nu a iesit nici la SIGTERM in %d s: SIGKILL trimis" % (pid, int(acum - cand)))
        except OSError as e:
            log("SIGKILL catre pid=%d a esuat: %s" % (pid, e))
        return "sigkill"
    semn = citeste_semn_iesire()
    if semn is None:
        return "fara"
    if _sigterm is not None and _sigterm[0] == semn["pid"]:
        return "nivelul-3"        # nivelul 3 a trimis deja SIGTERM acestui proces; pas_sigkill urmeaza
    try:
        interfata, _asteptare = setari_paznic()
    except Exception:
        interfata = INTERFATA_IMPLICIT
    fel, detaliu = hotarare_iesire_ceruta(acum, semn, proces_enigma2_viu(semn["pid"]), interfata, bool(opkg))
    if fel != "opreste":
        return fel
    pid = semn["pid"]
    rand = "%s; firele ramase: %s" % (detaliu, firele_ramase(pid))
    log(rand)
    scrie_jurnal_caderi("%s; oprit de paznic (SIGTERM, apoi SIGKILL)" % rand)
    # inaintea oricarui semnal: enigma2.sh afla ca iesirea care urmeaza e oprirea paznicului (motiv=iesire-ceruta)
    scrie_semn_oprire(pid, motiv="iesire-ceruta")
    cere_stivele(pid)
    try:
        os.kill(pid, signal.SIGTERM)
        log("SIGTERM trimis catre pid=%d (iesirea ceruta nu s-a terminat)" % pid)
    except OSError as e:
        log("SIGTERM catre pid=%d a esuat: %s" % (pid, e))
    _iesire_oprita = [pid, acum, False]
    _sigterm = (pid, float("inf"))
    _reporniri_interfata += 1
    _ultima_actiune = ("interfata repornita: nu iesea dupa repornirea ceruta", time.time())
    return "sigterm"


def _kmsg_randuri(date):
    """Randurile de text din inregistrarile /dev/kmsg („pri,seq,usec,flags;text”), cu ceasul nucleului in fata; fara
    randurile de continuare („ SUBSYSTEM=...”)."""
    rez = []
    for rand in date.decode("utf-8", "replace").split("\n"):
        if not rand or rand.startswith(" "):
            continue
        cap, sep, text = rand.partition(";")
        if sep:
            camp = cap.split(",")
            try:
                rez.append("[%12.6f] %s" % (int(camp[2]) / 1e6, text))
            except (IndexError, ValueError):
                rez.append(text)
        else:
            rez.append(rand)
    return rez


def _kmsg_citeste(fd, termen):
    """Ce se poate citi acum din /dev/kmsg (deschis fara blocare), pana la EAGAIN, sfarsit sau termen. EPIPE = inregistrari
    suprascrise intre timp: citirea urmatoare merge mai departe."""
    parti = []
    while time.time() < termen:
        try:
            b = os.read(fd, 8192)
        except BlockingIOError:
            break
        except OSError as e:
            if e.errno == errno.EPIPE:
                continue
            break
        if not b:
            break
        parti.append(b)
    return b"".join(parti)


def salveaza_firele_blocate(reason, kmsg=None, dosar=None, sysrq=None):
    """Inainte de repornirea dura: contextul din jurnalul nucleului, apoi sysrq 'w' (stivele firelor blocate, cu numele
    functiilor), copiate in CRASH_LOG_DIR/hds-blocaj-AAAALLZZ-HHMMSS.txt pe memoria interna, cu fsync; raman ultimele
    BLOCAJ_PASTRATE. Asa se vede dupa repornire in ce apel de driver a stat firul. Toata treaba tine cel mult
    BLOCAJ_TERMEN_S. Intoarce calea fisierului sau None; nu arunca."""
    kmsg = kmsg or KMSG_PATH
    dosar = dosar or CRASH_LOG_DIR
    sysrq = sysrq or SYSRQ_TRIGGER_PATH
    termen = time.time() + BLOCAJ_TERMEN_S
    fd = None
    try:
        fd = os.open(kmsg, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        context = _kmsg_randuri(_kmsg_citeste(fd, termen - BLOCAJ_ASTEPTARE_S - 0.5))[-BLOCAJ_CONTEXT:]
        try:
            with open(sysrq, "w") as f:
                f.write("w")
        except OSError as e:
            log("sysrq 'w' a esuat (stivele firelor blocate lipsesc): %s" % e)
        time.sleep(BLOCAJ_ASTEPTARE_S)
        stive = _kmsg_randuri(_kmsg_citeste(fd, termen))
    except OSError as e:
        log("jurnalul nucleului nu se poate citi pentru stivele firelor blocate: %s" % e)
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    try:
        os.makedirs(dosar, exist_ok=True)
        cale = os.path.join(dosar, "%s%s.txt" % (BLOCAJ_PREFIX, time.strftime("%Y%m%d-%H%M%S")))
        nou = cale + ".nou"
        with open(nou, "w", encoding="utf-8") as f:
            f.write("motiv: %s\nora: %s\n\n== jurnalul nucleului inainte (ultimele %d randuri)\n"
                    % (reason, time.strftime("%Y-%m-%d %H:%M:%S"), BLOCAJ_CONTEXT))
            f.write("\n".join(context) + "\n\n== sysrq 'w': firele blocate (stare D) si stivele lor\n")
            f.write("\n".join(stive) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(nou, cale)
    except OSError as e:
        log("stivele firelor blocate nu s-au scris in %s: %s" % (dosar, e))
        return None
    try:
        vechi = sorted(n for n in os.listdir(dosar) if n.startswith(BLOCAJ_PREFIX) and n.endswith(".txt"))
        for n in vechi[:-BLOCAJ_PASTRATE]:
            os.remove(os.path.join(dosar, n))
    except OSError:
        pass
    log("stivele firelor blocate salvate in %s (%d randuri dupa sysrq 'w')" % (cale, len(stive)))
    return cale


def force_hard_reboot(reason):
    log("declansez repornire dura (sysrq): %s" % reason)
    # r16 (0.7.6, asistenta 430032): intai randul in jurnalul mic al opririlor (fsync), inainte de orice altceva; jurnalul
    # paznicului (LOG_PATH) nu se citeste din asistenta, iar hds-blocaj-*.txt lipseste cand /dev/kmsg nu se citeste.
    # Asa o repornire dura a paznicului nu mai ramane fara urma in hds-caderi.log. Motivul intreg (firul, starea, wchan),
    # pe un rand, cel mult 400 de semne: e singura urma care ramane sigur pe disc.
    scrie_jurnal_caderi("paznicul reporneste dur receptorul (sysrq): %s" % (" ".join(str(reason).split())[:400] or "gol"))
    try:
        with open("/proc/sys/kernel/sysrq", "w") as f:
            f.write("1")
    except OSError as e:
        log("nu am putut activa sysrq (continui oricum, poate fi deja activ): %s" % e)
    # stivele nucleului inainte de orice: dupa repornire se vede apelul de driver in care a stat firul; nimic de aici nu
    # are voie sa opreasca repornirea
    try:
        salveaza_firele_blocate(reason)
    except Exception as e:
        log("stivele firelor blocate nu s-au salvat: %s" % e)
    # sysrq 's' (emergency sync) instead of os.sync(): a plain sync can block forever on the same hang.
    try:
        with open("/proc/sysrq-trigger", "w") as f:
            f.write("s")
        time.sleep(1)
    except OSError as e:
        log("sysrq 's' a esuat, jurnalul poate pierde ultimele randuri: %s" % e)
    try:
        with open("/proc/sysrq-trigger", "w") as f:
            f.write("b")
    except OSError as e:
        log("scrierea 'b' in sysrq-trigger a esuat: %s -- watchdogul HW ramane singura plasa "
            "(va expira in max %ds de la ultima hranire)" % (e, PET_INTERVAL_S * CONFIRM_HANG_CHECKS))


def _ng_ip_bin():
    """Calea lui "ip", ca in hds-netguard: iproute2 (stie sigur "blackhole" si "exact"), altfel /sbin/ip."""
    if NETGUARD_IP_BIN:
        return NETGUARD_IP_BIN if os.access(NETGUARD_IP_BIN, os.X_OK) else None
    for cale in ("/sbin/ip.iproute2", "/sbin/ip"):
        if os.access(cale, os.X_OK):
            return cale
    return None


def _ng_scurt(text):
    """Un singur rand, scurt, pentru jurnal si pentru fisierul de stare."""
    rand = " ".join(text.split())
    return rand[:160] if rand else "gol"


def _ng_ruleaza(argumente):
    """Ruleaza "ip" cu o lista de argumente (fara shell), cu limita de timp. Intoarce (cod, iesire); cod
    None cand timpul a expirat, programul nu a pornit sau un "ip" de data trecuta e tot blocat (iesire =
    motivul).

    Nu se foloseste subprocess.run(timeout=...): la timp depasit el face kill() si apoi wait() FARA limita.
    Un "ip" blocat in nucleu in stare D nu moare la SIGKILL pana nu iese din nucleu; in 4.4.35
    rtnetlink_rcv ia rtnl_lock() (mutex_lock, neintreruptibil) pentru orice cerere, si pentru "show", deci
    un driver agatat care tine rtnl_mutex ar opri bucla aici, hranirea s-ar opri si watchdogul HW ar reporni
    dur receptorul, fara nicio linie in jurnal (verificarea adversariala din 24.09.2026). Aici asteptarea
    dupa kill() are limita, copilul ramas se tine minte, iar pana nu iese nu se mai porneste altul."""
    for copil in list(_ng_copii_blocati):
        if copil.poll() is not None:
            _ng_copii_blocati.remove(copil)
    if _ng_copii_blocati:
        return None, "ip de data trecuta tot blocat (pid %d)" % _ng_copii_blocati[0].pid
    try:
        copil = subprocess.Popen(argumente, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
    except OSError as e:
        return None, "nu a pornit: %s" % e
    try:
        iesire, _ = copil.communicate(timeout=NETGUARD_IP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        try:
            copil.kill()
        except OSError:
            pass
        try:
            copil.wait(timeout=0.5)  # un "ip" obisnuit moare imediat la SIGKILL
        except subprocess.TimeoutExpired:
            _ng_copii_blocati.append(copil)  # stare D: nu mai asteptam; poll() la verificarile urmatoare
        try:
            copil.stdout.close()
        except OSError:
            pass
        return None, "timp depasit (%ds)" % NETGUARD_IP_TIMEOUT_S
    return copil.returncode, iesire.decode("utf-8", "replace")


def _ng_e_blackhole(iesire):
    """True numai daca exista randuri si FIECARE rand pentru exact aceasta adresa e "blackhole" fara "tos".
    hds-netguard (has_blackhole) se uita numai la primul rand; aici e mai strict, pentru ca nucleul pune
    intrarile cu tos inaintea celor fara: "blackhole ... tos 0x10" urmat de "... via ..." are primul rand
    bun, dar traficul obisnuit (tos 0) ia ruta via; iar un blackhole numai cu tos nu opreste traficul cu
    tos 0 (probat cu nucleu real, verificarea adversariala din 24.09.2026, cazul J)."""
    randuri = [r.split() for r in iesire.splitlines() if r.strip()]
    return bool(randuri) and all(r[0] == "blackhole" and "tos" not in r for r in randuri)


def _ng_pauza_activa(acum):
    try:
        varsta = acum - os.stat(NETGUARD_PAUZA_PATH).st_mtime
    except OSError:
        return False
    # varsta negativa (ceas mutat, semn pus inainte de NTP) nu se crede: ruta ramane pazita
    return 0 <= varsta <= NETGUARD_PAUZA_MAX_S


def verifica_netguard(acum):
    """O verificare a rutei spre NETGUARD_IP, cu repunere daca lipseste; fara jurnal.
    Intoarce (stare, detaliu, repusa)."""
    if not os.path.exists(NETGUARD_INITSCRIPT):
        return "neinstalat", "lipseste %s, ruta nu se atinge" % NETGUARD_INITSCRIPT, False
    if _ng_pauza_activa(acum):
        return ("pauza", "semn de pauza %s (tine cel mult %d min)"
                % (NETGUARD_PAUZA_PATH, NETGUARD_PAUZA_MAX_S // 60), False)
    ip = _ng_ip_bin()
    if ip is None:
        return "fara-ip", "nu exista /sbin/ip.iproute2 si nici /sbin/ip", False

    ruta = NETGUARD_IP + "/32"
    arata = [ip, "-4", "route", "show", "exact", ruta]
    cod, iesire = _ng_ruleaza(arata)
    if cod != 0:
        return "necunoscut", "ip route show: %s" % (iesire if cod is None else "cod %d" % cod), False
    if _ng_e_blackhole(iesire):
        return "pusa", _ng_scurt(iesire), False

    inainte = _ng_scurt(iesire) if iesire.strip() else "lipsea"
    pune = [ip, "-4", "route", "replace", "blackhole", ruta]
    curata = [ip, "-4", "route", "flush", "exact", ruta]
    # 1. "replace" ajunge cand ruta lipseste sau e una singura, de alt tip.
    # 2. Cand alta intrare sta INAINTEA unui blackhole care exista deja ("ip route prepend ... via", sau una
    #    cu tos), nucleul refuza "replace" (EEXIST: blackhole-ul identic e mai jos in lista), probat cu
    #    nucleu real (teste-paza/proba-nucleu.sh, cazul F). La fel cand "replace" merge, dar alta intrare
    #    ramane langa blackhole (via cu metrica mai mare, intrari cu tos; cazurile G, H, J). Atunci se sterg
    #    toate intrarile pentru exact aceasta adresa si blackhole-ul se pune din nou.
    pasi = []
    for comenzi in ([pune], [curata, pune]):
        for comanda in comenzi:
            cod_c, motiv = _ng_ruleaza(comanda)
            pasi.append("%s: %s" % (comanda[3], motiv if cod_c is None else "cod %d" % cod_c))
            if cod_c is None:  # timp depasit: nu mai insistam in aceasta verificare
                return "esec", _ng_scurt("era: %s; %s" % (inainte, "; ".join(pasi))), False
        cod, iesire = _ng_ruleaza(arata)
        if cod == 0 and _ng_e_blackhole(iesire):
            detaliu = "era: %s" % inainte if len(pasi) == 1 else "era: %s; curatat cu flush" % inainte
            return "pusa", _ng_scurt(detaliu), True
        if cod is None:
            break
    return "esec", _ng_scurt("era: %s; %s; acum: %s" % (inainte, "; ".join(pasi), iesire)), False


def _ng_scrie_stare(stare, detaliu, acum):
    """Fisierul de stare pentru interfata, atomic (.nou + rename). Intoarce None sau textul erorii."""
    continut = ("stare=%s\nadresa=%s\ndetaliu=%s\nschimbat=%d\nrepuneri=%d\nultima_repunere=%d\npid=%d\n"
                % (stare, NETGUARD_IP, detaliu, int(acum), _ng_repuneri, int(_ng_ultima_repunere),
                   os.getpid()))
    nou = NETGUARD_STARE_PATH + ".nou"
    try:
        with open(nou, "w") as f:
            f.write(continut)
        os.replace(nou, NETGUARD_STARE_PATH)
    except OSError as e:
        return str(e)
    return None


def pas_netguard():
    """Pasul periodic din bucla principala. Nu arunca niciodata (hranirea watchdogului HW nu are voie sa
    se opreasca din cauza lui). Jurnal si fisier de stare numai la schimbare: ruta repusa sau stare noua."""
    global _ng_stare, _ng_repuneri, _ng_ultima_repunere
    acum = time.time()
    try:
        stare, detaliu, repusa = verifica_netguard(acum)
    except Exception as e:  # plasa pentru un defect neprevazut; bucla merge mai departe
        stare, detaliu, repusa = "necunoscut", _ng_scurt("eroare interna: %r" % (e,)), False
    try:
        if repusa:
            _ng_repuneri += 1
            _ng_ultima_repunere = acum
            log("netguard: ruta blackhole spre %s pusa la loc (%s), repunerea %d"
                % (NETGUARD_IP, detaliu, _ng_repuneri))
        elif stare != _ng_stare:
            log("netguard: stare %s (%s)" % (stare, detaliu))
        if repusa or stare != _ng_stare:
            _ng_stare = stare
            eroare = _ng_scrie_stare(stare, detaliu, acum)
            if eroare:
                log("netguard: nu pot scrie %s: %s" % (NETGUARD_STARE_PATH, eroare))
    except Exception:
        pass


# ---------------------------------------------------------------- nivelul 5: decodorul video fara memorie

def fel_rand_decodor(text):
    """Ce spune un rand din jurnalul nucleului despre memoria redarii video (driverele HiSilicon), sau None:
      memorie  „vmap allocation for size N failed” (spatiul vmalloc) sau „[HI_DRV_SMMU_AllocAndMap] Remap ... failed”:
               cauza, dar singure nu spun cine a cerut memoria;
      decodor  „VDEC_Chan_AllocMem err , no memory!”: decodorul nu-si poate face canalul din lipsa de memorie;
      pornire  „HI_DRV_VDEC_ChanStart[...]:Chan 0 Start err”: canalul video nu porneste (cauza o spune grupul);
      demux    „DmxAllocNonSecureAVBuf ... mmu memory allocate failed”: tamponul audio-video al redarii."""
    if "failed" in text and ("vmap allocation" in text or ("SMMU" in text and "Remap" in text)):
        return "memorie"
    if "VDEC_Chan_AllocMem" in text and "no memory" in text:
        return "decodor"
    if "HI_DRV_VDEC_ChanStart" in text and "Start err" in text:
        return "pornire"
    if "DmxAllocNonSecureAVBuf" in text and "failed" in text:
        return "demux"
    return None


def grup_sigur(feluri):
    """Un grup de randuri (un esec: randurile lui vin in ~20 ms) e un esec SIGUR al pornirii redarii video din lipsa de
    memorie: „decodor” si „demux” spun singure asta, „pornire” numai impreuna cu „memorie”. Un „vmap ... failed” singur
    (alt modul al nucleului) sau un „Start err” fara cauza nu se numara."""
    return "decodor" in feluri or "demux" in feluri or ("pornire" in feluri and "memorie" in feluri)


def adauga_esec(grupuri, t, fel):
    """Randul (t, fel) intra in ultimul grup cand vine la cel mult DEC_GRUP_S de el, altfel incepe alt grup."""
    if grupuri and abs(t - grupuri[-1][1]) <= DEC_GRUP_S:
        grupuri[-1][1] = max(grupuri[-1][1], t)
        grupuri[-1][2].add(fel)
    else:
        grupuri.append([t, t, set([fel])])
    if len(grupuri) > DEC_GRUPURI_MAX:
        del grupuri[:-DEC_GRUPURI_MAX]


def esecuri_sigure(grupuri, acum):
    """Momentele (sfarsitul grupului, ceas monoton) esecurilor sigure din ultimele DEC_FEREASTRA_S secunde, vechi intai.
    Grupurile mai vechi decat fereastra se scot din lista."""
    while grupuri and acum - grupuri[0][1] > DEC_FEREASTRA_S:
        del grupuri[0]
    return [g[1] for g in grupuri if acum - g[1] <= DEC_FEREASTRA_S and grup_sigur(g[2])]


def lipsa_de_memorie(momente, acum):
    """True cand jurnalul arata lipsa de acum: cel putin DEC_PRAG esecuri sigure in fereastra, iar ultimul de cel mult
    DEC_ULTIMUL_MAX_S secunde."""
    return len(momente) >= DEC_PRAG and acum - momente[-1] <= DEC_ULTIMUL_MAX_S


class JurnalNucleu(object):
    """Randurile noi din jurnalul nucleului, de la deschidere incolo. Intai /dev/kmsg: fiecare inregistrare are ceasul ei
    (microsecunde de la pornire, ca ceasul monoton), nu depinde de syslogd si nu tine nimic de dinaintea unei reporniri.
    Daca nu se poate deschide, coada lui MESAJE_PATH: el sta pe memoria interna si pastreaza si esecurile de dinaintea
    repornirii, deci se citeste numai ce se scrie dupa deschidere (un fisier nou dupa rotire, cu alt inode sau mai mic,
    se citeste de la inceput); ceasul unui rand e atunci ora citirii. Citirea e marginita pe verificare
    (DEC_CITIRE_RANDURI inregistrari si DEC_CITIRE_S secunde, DEC_FISIER_MAX octeti), ca hranirea watchdogului HW sa nu
    intarzie; restul ramane pentru verificarea urmatoare. Nu arunca."""

    def __init__(self, kmsg=None, mesaje=None):
        self.kmsg = kmsg or KMSG_PATH
        self.mesaje = mesaje or MESAJE_PATH
        self.sursa = None        # "kmsg", "mesaje" sau None (inca nedeschis)
        self.fd = None
        self.kmsg_stricat = False
        self.fisier = (None, 0)  # (inode, pozitie) in MESAJE_PATH
        self.rest = b""
        self.anuntat = None

    def _anunta(self, text):
        if self.anuntat != text:
            self.anuntat = text
            log("nivelul 5: %s" % text)

    def _deschide(self):
        motiv = "oprit dupa o eroare de citire"
        if not self.kmsg_stricat:
            try:
                fd = os.open(self.kmsg, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            except OSError as e:
                fd, motiv = None, str(e)
            if fd is not None:
                try:
                    os.lseek(fd, 0, os.SEEK_END)    # numai inregistrarile scrise de acum incolo
                    self.fd, self.sursa, self.rest = fd, "kmsg", b""
                    self._anunta("citesc jurnalul nucleului din %s" % self.kmsg)
                    return
                except OSError as e:
                    motiv = str(e)
                    os.close(fd)
        try:
            st = os.stat(self.mesaje)
            self.fisier = (st.st_ino, st.st_size)
        except OSError:
            self.fisier = (None, 0)
        self.sursa, self.rest = "mesaje", b""
        self._anunta("%s nu se poate citi (%s): citesc randurile noi din %s" % (self.kmsg, motiv, self.mesaje))

    def inchide(self):
        """Inchide /dev/kmsg (probele; pe receptor jurnalul ramane deschis cat traieste paznicul)."""
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd, self.sursa = None, None

    def citeste(self, acum):
        """[(t, text)] scrise de la citirea trecuta; t pe ceasul monoton, cel mult acum."""
        try:
            if self.sursa is None:
                self._deschide()
            if self.sursa == "kmsg":
                return self._din_kmsg(acum)
            return self._din_fisier(acum)
        except Exception as e:
            self._anunta("eroare la citirea jurnalului nucleului: %r" % (e,))
            return []

    def _randuri(self, date, acum, kmsg):
        bucati = (self.rest + date).split(b"\n")
        self.rest = bucati.pop()[-4096:]   # o bucata fara sfarsit de rand se intregeste la citirea urmatoare
        rez = []
        for b in bucati:
            if not b or b[:1] == b" ":
                continue                    # randurile de continuare ale unei inregistrari kmsg (" SUBSYSTEM=...")
            text = b.decode("utf-8", "replace")
            t = acum
            if kmsg:
                # "prioritate,numar,microsecunde,steaguri[,...];text"
                antet, semn, rest = text.partition(";")
                campuri = antet.split(",")
                if semn and len(campuri) >= 3:
                    try:
                        tk = int(campuri[2]) / 1e6
                        if 0 < tk <= acum:
                            t = tk
                    except ValueError:
                        pass
                    text = rest
            rez.append((t, text))
        return rez

    def _din_kmsg(self, acum):
        rez = []
        capat = time.monotonic() + DEC_CITIRE_S
        for _i in range(DEC_CITIRE_RANDURI):
            try:
                date = os.read(self.fd, 8192)   # o inregistrare pe citire (sub 1 KB)
            except BlockingIOError:
                break                            # nimic nou
            except (BrokenPipeError, InterruptedError):
                continue                         # inregistrari suprascrise intre doua citiri: urmeaza cea mai veche ramasa
            except OSError as e:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd, self.sursa, self.kmsg_stricat = None, None, True
                self._anunta("%s: %s; trec pe %s" % (self.kmsg, e, self.mesaje))
                break
            if not date:
                break                            # un fisier obisnuit (probele) la sfarsit
            rez.extend(self._randuri(date, acum, True))
            if time.monotonic() > capat:
                break
        return rez

    def _din_fisier(self, acum):
        try:
            st = os.stat(self.mesaje)
        except OSError:
            self.fisier, self.rest = (None, 0), b""
            return []
        inode, poz = self.fisier
        if st.st_ino != inode or st.st_size < poz:
            poz, self.rest = 0, b""              # fisier nou (rotit de syslogd) sau taiat: de la inceput
        if st.st_size - poz > DEC_FISIER_MAX:
            poz, self.rest = st.st_size - DEC_FISIER_MAX, b""
        if st.st_size <= poz:
            self.fisier = (st.st_ino, poz)
            return []
        with open(self.mesaje, "rb") as f:
            f.seek(poz)
            date = f.read(st.st_size - poz)
        self.fisier = (st.st_ino, poz + len(date))
        return self._randuri(date, acum, False)


def decodor_ruleaza(dosare=None):
    """Decodoarele video HiSilicon (/proc/msp/vdecNN, altfel /proc/hisi/msp/vdecNN): True cand vdec00 sau vdec01 are
    „Work State : RUN” (canalul video exista, deci memoria a ajuns); False cand dosarul exista, dar niciun decodor nu
    ruleaza (vdecNN lipsesc sau stau STOP, ca dupa „Chan 0 Start err”); None fara dosar (alt receptor) sau cand starea nu
    se poate citi: atunci nu se reporneste nimic."""
    for dosar in (dosare or VDEC_DOSARE):
        if not os.path.isdir(dosar):
            continue
        for n in (0, 1):
            try:
                with open(os.path.join(dosar, "vdec%02d" % n), "rb") as f:
                    text = f.read(16384).decode("latin-1")
            except FileNotFoundError:
                continue
            except OSError:
                return None
            stare = None
            for rand in text.splitlines():
                if "Work State" in rand:
                    stare = rand.split(":", 1)[1].strip().upper() if ":" in rand else ""
                    break
            if stare is None:
                return None
            if stare.startswith("RUN"):
                return True
        return False
    return None


def culegere_de_noapte():
    """True cat programul de noapte al culegerii canalelor (hds-culegere-noapte.py, separat de enigma2, fara semn in
    bataie) ruleaza: pid-ul din CULEGERE_PID_PATH e al unui proces viu. Un fisier care nu se poate citi conteaza ca
    „ruleaza”."""
    descriptor = None
    try:
        descriptor = os.open(CULEGERE_PID_PATH, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
        stare = os.fstat(descriptor)
        if not stat.S_ISREG(stare.st_mode) or stare.st_uid != 0 or stare.st_size > 64:
            return True
        text = os.read(descriptor, 64).decode("ascii").strip()
    except FileNotFoundError:
        return False
    except (OSError, UnicodeError):
        return True
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    try:
        pid = int(text)
    except ValueError:
        return True
    return pid > 0 and os.path.exists("/proc/%d" % pid)


def citeste_semn_decodor():
    """Ora (secunde epoch) ultimei reporniri pentru decodor, din DECODOR_SEMN_PATH: randul ora=, altfel data fisierului
    (un semn stricat tot opreste o repornire noua in aceeasi ora). None fara semn."""
    try:
        with open(DECODOR_SEMN_PATH) as f:
            for rand in f.read(1024).splitlines():
                if rand.startswith("ora="):
                    return int(rand[4:].strip())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        pass
    try:
        return int(os.stat(DECODOR_SEMN_PATH).st_mtime)
    except OSError:
        return None


def repornire_permisa(ora_acum, ora_semn):
    """Cel mult o repornire pentru decodor pe ora: permisa fara semn, cu un semn de cel putin DEC_O_DATA_LA_S secunde, sau
    cu unul mai departe de DEC_SEMN_VIITOR_MAX_S in viitor (ceas mutat mult la scriere: semn fara inteles). Un semn
    putin in viitor (ceasul a dat inapoi dupa repornire, prin NTP sau transponder) opreste repornirea."""
    if ora_semn is None:
        return True
    varsta = ora_acum - ora_semn
    return varsta >= DEC_O_DATA_LA_S or varsta < -DEC_SEMN_VIITOR_MAX_S


def hotarare_decodor(acum, momente, fel_nivel3, interfata_pornita, bataie, culegere, decodor, fara_imagine_de_la,
                     permisa, imagine_la=None):
    """Hotararea nivelului 5, fara efecte (testata in teste/test_paza_cadere_023.py).
    acum: ceas monoton; momente: esecuri_sigure(); fel_nivel3: felul nivelului 3 („viu” = enigma2 de acum bate);
    interfata_pornita: config.hds_paznic.interfata; bataie: a procesului enigma2 de acum (citeste_bataie) sau None;
    culegere: culegere_de_noapte(); decodor: decodor_ruleaza(); fara_imagine_de_la: de cand (ceas monoton) arata toate
    semnele lipsa, None = abia acum; permisa: repornire_permisa(); imagine_la: ultima verificare cu un decodor in RUN
    (None = niciuna): un decodor pornit dupa ultimul esec arata ca memoria a ajuns, iar lipsa se crede iar abia la un esec
    nou. Intoarce (fel, detaliu), fel fiind:
      liniste     jurnalul nu arata lipsa de acum (sub DEC_PRAG esecuri sigure in fereastra, sau ultimul e vechi)
      oprit       repornirea e oprita din setari (config.hds_paznic.interfata): numai jurnal
      nesigur     un semn lipseste sau nu se poate citi (interfata nu bate, bataia fara redare sau inregistrare, starea
                  decodoarelor necitita sau alt receptor): numai jurnal
      ocupat      scanare, citirea pistelor, rotirea antenei, culegerea de noapte, ori o inregistrare acum sau curand
      fara-tv     interfata nu reda un canal TV (radio, standby, nimic): o repornire nu foloseste acum
      imagine     un decodor video ruleaza, sau a rulat dupa ultimul esec: memoria a ajuns
      prea-des    receptorul a fost repornit pentru decodor in ultima ora: numai jurnal
      asteapta    toate semnele arata lipsa, dar de mai putin de DEC_CONFIRMARE_S
      reporneste  de repornit receptorul"""
    if not lipsa_de_memorie(momente, acum):
        return "liniste", ""
    baza = ("%d esecuri ale decodorului video din lipsa de memorie in nucleu in %d minute, ultimul acum %ds"
            % (len(momente), DEC_FEREASTRA_S // 60, int(acum - momente[-1])))
    if not interfata_pornita:
        return "oprit", baza + "; repornirea e oprita din setari, nu repornesc"
    if fel_nivel3 != "viu" or bataie is None:
        return "nesigur", baza + "; interfata nu bate acum (%s), nu repornesc" % fel_nivel3
    redare, inregistrare = bataie.get("redare"), bataie.get("inregistrare")
    if not redare or inregistrare not in (0, 1):
        return "nesigur", baza + "; bataia nu spune ce se reda sau daca se inregistreaza, nu repornesc"
    motive, _ramas = ocupat_valabil(bataie, acum)
    if motive:
        return "ocupat", baza + "; enigma2 e ocupat (%s), nu repornesc" % ",".join(motive)
    if culegere:
        return "ocupat", baza + "; culegerea de noapte a canalelor ruleaza, nu repornesc"
    if inregistrare == 1:
        return "ocupat", baza + "; o inregistrare merge sau incepe curand, nu repornesc"
    if redare != "tv":
        return "fara-tv", baza + "; nu se reda un canal TV (%s), nu repornesc" % redare
    if decodor is None:
        return "nesigur", baza + "; starea decodoarelor video nu se poate citi, nu repornesc"
    if decodor:
        return "imagine", baza + "; un decodor video ruleaza, nu repornesc"
    if imagine_la is not None and imagine_la >= momente[-1]:
        return "imagine", baza + "; un decodor video a pornit dupa ultimul esec, nu repornesc"
    if not permisa:
        return "prea-des", baza + "; receptorul a fost deja repornit pentru decodor in ultima ora, nu repornesc"
    if fara_imagine_de_la is None or acum - fara_imagine_de_la < DEC_CONFIRMARE_S:
        return "asteapta", baza + "; canal TV fara niciun decodor pornit, mai astept pana la %ds" % DEC_CONFIRMARE_S
    return "reporneste", baza + "; canal TV fara niciun decodor pornit de %ds" % int(acum - fara_imagine_de_la)


def scrie_jurnal_caderi(text):
    """Un rand in jurnalul mic al opririlor (acelasi fisier si acelasi fel de rand ca in tools/enigma2.sh.in:
    „AAAA-LL-ZZ HH:MM:SS text”), cu fsync. Nu arunca."""
    try:
        os.makedirs(os.path.dirname(CADERI_JURNAL_PATH), exist_ok=True)
        with open(CADERI_JURNAL_PATH, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        log("nu pot scrie in %s: %s" % (CADERI_JURNAL_PATH, e))


def scrie_semn_decodor(ora, motiv):
    """Semnul „o data pe ora” pe memoria interna (ramane peste repornire), atomic si cu fsync, inainte de reboot."""
    try:
        os.makedirs(os.path.dirname(DECODOR_SEMN_PATH), exist_ok=True)
        nou = DECODOR_SEMN_PATH + ".nou"
        with open(nou, "w") as f:
            f.write("ora=%d\nuptime=%d\nmotiv=%s\n" % (int(ora), uptime_secunde() or -1, _ng_scurt(motiv)))
            f.flush()
            os.fsync(f.fileno())
        os.replace(nou, DECODOR_SEMN_PATH)
        return True
    except OSError as e:
        log("nu pot scrie semnul repornirii pentru decodor (%s): %s" % (DECODOR_SEMN_PATH, e))
        return False


def reporneste_receptorul(motiv):
    """O singura repornire curata a receptorului: REBOOT_BIN, ca enigma2.sh la codul 2 (nu sysrq). Inainte: motivul in
    jurnalul paznicului si in jurnalul mic al opririlor, semnul de pe disc (o data pe ora). Procesul reboot nu se asteapta
    mai mult de 2 s; hranirea watchdogului HW merge mai departe pana cand init opreste paznicul (SIGTERM: dezarmare
    curata). Intoarce True daca reboot a fost pornit. Nu arunca."""
    global _dec_repornire_ceruta, _ultima_actiune, _dec_copil
    if _dec_repornire_ceruta:
        return False
    _dec_repornire_ceruta = True
    ora = time.time()
    log("nivelul 5: REPORNESC RECEPTORUL (%s): %s" % (REBOOT_BIN, motiv))
    scrie_jurnal_caderi("paznicul reporneste receptorul: decodorul video nu mai porneste din lipsa de memorie in nucleu "
                        "(%s)" % _ng_scurt(motiv))
    scrie_semn_decodor(ora, motiv)
    _ultima_actiune = ("receptorul repornit: decodorul video nu mai pornea din lipsa de memorie", ora)
    try:
        copil = subprocess.Popen([REBOOT_BIN], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
    except OSError as e:
        log("nivelul 5: %s nu a pornit: %s" % (REBOOT_BIN, e))
        return False
    try:
        cod = copil.wait(timeout=2)
        if cod != 0:
            log("nivelul 5: %s a iesit cu codul %d" % (REBOOT_BIN, cod))
    except subprocess.TimeoutExpired:
        _dec_copil = copil
    return True


def pas_decodor(acum, fel_nivel3, interfata, bataie):
    """Pasul nivelului 5 din bucla principala: randurile noi din jurnalul nucleului, hotararea si, la „reporneste”,
    repornirea receptorului. Decodoarele, culegerea de noapte si semnul de pe disc se citesc numai cand jurnalul arata
    lipsa, deci de obicei pasul costa o citire a jurnalului. O linie in jurnalul paznicului la schimbarea felului.
    bataie: a procesului enigma2 de acum, sau None. Intoarce (fel, detaliu)."""
    global _jurnal_nucleu, _dec_fara_imagine_de_la, _dec_anuntat, _dec_imagine_la
    if _jurnal_nucleu is None:
        _jurnal_nucleu = JurnalNucleu()
    for t, text in _jurnal_nucleu.citeste(acum):
        fel = fel_rand_decodor(text)
        if fel:
            adauga_esec(_esecuri, t, fel)
        # anuntul memoriei pozelor si a filmelor (pas_memorie_es) foloseste aceleasi randuri
        fel_es = fel_rand_memorie_es(text)
        if fel_es:
            adauga_esec(_es_grupuri, t, fel_es)
    momente = esecuri_sigure(_esecuri, acum)
    culegere, decodor, permisa = False, None, True
    if lipsa_de_memorie(momente, acum):
        culegere = culegere_de_noapte()
        decodor = decodor_ruleaza()
        if decodor:
            _dec_imagine_la = acum
        permisa = repornire_permisa(time.time(), citeste_semn_decodor())
    fel, detaliu = hotarare_decodor(acum, momente, fel_nivel3, interfata, bataie, culegere, decodor,
                                    _dec_fara_imagine_de_la, permisa, _dec_imagine_la)
    if fel in ("asteapta", "reporneste"):
        if _dec_fara_imagine_de_la is None:
            _dec_fara_imagine_de_la = acum
    else:
        _dec_fara_imagine_de_la = None
    if fel != _dec_anuntat:
        if fel != "liniste":
            log("nivelul 5: %s" % detaliu)
        elif _dec_anuntat is not None:
            log("nivelul 5: jurnalul nucleului nu mai arata lipsa de memorie a decodorului")
        _dec_anuntat = fel
    if fel == "reporneste":
        reporneste_receptorul(detaliu)
    return fel, detaliu


# ---------------------------------------------------------------- anuntul memoriei pozelor si a filmelor

def fel_rand_memorie_es(text):
    """Randurile nucleului cand demonul platformei nu-si poate mapa la pornire memoria pozelor si a filmelor, sau None:
      harta  „vmap allocation for size 34611200 failed” (numai marimea ES_MARIME; alte marimi sunt ale nivelului 5);
      remap  „[HI_DRV_SMMU_Map] Remap buf failed” (nu „[HI_DRV_SMMU_AllocAndMap] Remap VFMW_SCD failed” al decodorului)."""
    if "vmap allocation for size %d failed" % ES_MARIME in text:
        return "harta"
    if "[HI_DRV_SMMU_Map] Remap buf failed" in text:
        return "remap"
    return None


def esec_memorie_es(grupuri):
    """Momentul (sfarsitul grupului, ceas monoton) ultimului esec al maparii: amandoua randurile in acelasi grup (vin in
    acelasi apel al driverului). None fara niciunul."""
    for g in reversed(grupuri):
        if "harta" in g[2] and "remap" in g[2]:
            return g[1]
    return None


def numara_mapari_es(text):
    """Cate randuri din /proc/vmallocinfo („0x<inceput>-0x<sfarsit> <marime> <cine> ...”) au marimea ES_MARIME, ca
    hisiCountEsMaps din lib/dvb/hdspazavideo.h al enigma2."""
    n = 0
    for rand in text.splitlines():
        campuri = rand.split()
        if len(campuri) >= 2 and campuri[0].startswith("0x") and campuri[1] == str(ES_MARIME):
            n += 1
    return n


def citeste_mapari_es():
    """Maparile de ES_MARIME din VMALLOCINFO_PATH, sau None cand fisierul nu se poate citi sau e gol. Nu arunca."""
    try:
        with open(VMALLOCINFO_PATH, "rb") as f:
            date = f.read(8 << 20)
    except OSError:
        return None
    if not date:
        return None
    return numara_mapari_es(date.decode("latin-1"))


def pornire_demon_es():
    """(pid, pornit_la) al demonului platformei (cel mai mic pid cu numele ES_DEMON); pornit_la = secunde de la pornirea
    receptorului (campul 22 din /proc/PID/stat, in tacuri), acelasi ceas cu al inregistrarilor nucleului. None cand nu
    ruleaza sau nu se poate citi. Nu arunca."""
    pids = find_target_pids(ES_DEMON)
    if not pids:
        return None
    pid = min(pids)
    try:
        with open("/proc/%d/stat" % pid, "r") as f:
            text = f.read(2048)
        campuri = text[text.rindex(")") + 2:].split()
        tacuri = int(campuri[19])
        try:
            hz = os.sysconf("SC_CLK_TCK")
        except (AttributeError, ValueError, OSError):
            hz = 100
        return pid, tacuri / float(hz or 100)
    except (OSError, ValueError, IndexError):
        return None


def numara_citiri_zero(inainte, acum, demon, mapari, imagine):
    """Numaratoarea citirilor la rand fara mapare, dupa o citire noua a lui vmallocinfo (r14): (pid, n, ceasul citirii
    numarate) sau None. Creste cu o citire fara mapare a aceluiasi demon, cu un canal pornit si demonul pornit de cel
    putin ES_PORNIRE_S, la cel putin ES_VERIFICARE_S de citirea numarata inainte (o citire pe loc, mai devreme, nu
    schimba nimic); o mapare gasita, alt demon, vmallocinfo necitit sau niciun canal o sterg."""
    if demon is None or mapari != 0 or not imagine or acum - demon[1] < ES_PORNIRE_S:
        return None
    if inainte is None or inainte[0] != demon[0]:
        return (demon[0], 1, acum)
    if acum - inainte[2] >= ES_VERIFICARE_S:
        return (demon[0], inainte[1] + 1, acum)
    return inainte


def hotarare_memorie_es(acum, demon, mapari, esec_la, imagine=True, citiri_zero=ES_CITIRI_LIPSA):
    """Hotararea anuntului, fara efecte (testata in teste/test_cadere_radio_2.py si test_memorie_0509.py). acum: ceas
    monoton (secunde de la pornirea receptorului); demon: pornire_demon_es(); mapari: citeste_mapari_es(); esec_la:
    esec_memorie_es(); imagine: un canal TV sau radio ruleaza de cel putin ES_PORNIRE_S (bataia enigma2, redare=tv
    sau radio); citiri_zero: citirile la rand fara mapare (numara_citiri_zero; r14, teste/test_paznic_opkg_074.py).
    Intoarce (fel, detaliu), fel fiind:
      lipsa    demonul de acum nu are memoria: esecul maparii din jurnal dupa pornirea lui, sau nicio mapare de
               ES_MARIME in vmallocinfo, de ES_CITIRI_LIPSA ori la rand, la cel putin ES_PORNIRE_S de la pornirea lui
               cu un canal pornit; poza radio si filmele nu merg pana la repornirea receptorului
      ok       demonul de acum are memoria
      nesigur  demonul nu ruleaza, abia a pornit, vmallocinfo nu se poate citi, niciun canal inca (standby, nimic:
               demonul isi face maparea abia cand enigma2 foloseste decodorul) sau o singura citire fara mapare (se
               mai citeste o data): nu se spune nimic"""
    if demon is None:
        return "nesigur", "demonul platformei (%s) nu ruleaza sau nu se poate citi" % ES_DEMON
    pid, pornit_la = demon
    if esec_la is not None and esec_la >= pornit_la - ES_TOLERANTA_S:
        return "lipsa", ("%s pid=%d: vmap allocation for size %d failed, Remap buf failed (acum %ds)"
                         % (ES_DEMON, pid, ES_MARIME, max(0, int(acum - esec_la))))
    if mapari is None:
        return "nesigur", "%s nu se poate citi" % VMALLOCINFO_PATH
    if mapari > 0:
        return "ok", "%s pid=%d are maparea de %d o" % (ES_DEMON, pid, ES_MARIME)
    if acum - pornit_la < ES_PORNIRE_S:
        return "nesigur", "%s pid=%d a pornit acum %ds, maparea inca lipseste" % (ES_DEMON, pid, max(0, int(acum - pornit_la)))
    if not imagine:
        return "nesigur", "%s pid=%d fara mapare, dar niciun canal inca (o face la primul canal)" % (ES_DEMON, pid)
    if citiri_zero < ES_CITIRI_LIPSA:
        return "nesigur", ("%s pid=%d fara mapare la %d citire din %d la rand; mai citesc o data"
                           % (ES_DEMON, pid, max(1, citiri_zero), ES_CITIRI_LIPSA))
    return "lipsa", ("%s pid=%d nu are maparea de %d o in %s (%d citiri la rand)"
                     % (ES_DEMON, pid, ES_MARIME, VMALLOCINFO_PATH, citiri_zero))


def pas_memorie_es(acum, canal=True):
    """Pasul anuntului din bucla principala, dupa nivelul 5 (care a citit jurnalul nucleului si a strans grupurile in
    _es_grupuri): demonul si vmallocinfo la ES_VERIFICARE_S, pe loc la un esec nou si cand un canal abia a ajuns la
    ES_PORNIRE_S (sau s-a oprit), hotararea, o linie in jurnalul paznicului cand memoria incepe sa lipseasca (o data pe
    demon) si cand revine. Nu reporneste nimic. canal: bataia enigma2 de acum spune redare=tv sau radio.
    Intoarce (fel, detaliu, cheie); cheie = pid-ul demonului fara memorie, altfel „”."""
    global _es_esec_vazut, _es_urmatoarea, _es_demon, _es_mapari, _es_anuntat, _es_tv_de, _es_imagine, _es_zero
    esec_la = esec_memorie_es(_es_grupuri)
    if canal:
        if _es_tv_de is None or acum < _es_tv_de:
            _es_tv_de = acum
    else:
        _es_tv_de = None
    imagine = _es_tv_de is not None and acum - _es_tv_de >= ES_PORNIRE_S
    if acum >= _es_urmatoarea or esec_la != _es_esec_vazut or imagine != _es_imagine:
        _es_esec_vazut = esec_la
        _es_imagine = imagine
        _es_demon = pornire_demon_es()
        _es_mapari = citeste_mapari_es() if _es_demon is not None else None
        _es_urmatoarea = acum + ES_VERIFICARE_S
        _es_zero = numara_citiri_zero(_es_zero, acum, _es_demon, _es_mapari, imagine)
    fel, detaliu = hotarare_memorie_es(acum, _es_demon, _es_mapari, esec_la, imagine, _es_zero[1] if _es_zero else 0)
    cheie = str(_es_demon[0]) if (fel == "lipsa" and _es_demon is not None) else ""
    if fel == "lipsa" and _es_anuntat != ("lipsa", cheie):
        log("memoria pozelor si a filmelor LIPSESTE (demonul platformei nu si-a putut mapa memoria la pornire): %s; "
            "poza posturilor de radio si filmele nu pornesc pana la repornirea receptorului; nu repornesc, enigma2 "
            "o elibereaza la urmatorul standby" % detaliu)
        _es_anuntat = ("lipsa", cheie)
    elif fel == "ok" and _es_anuntat is not None and _es_anuntat[0] == "lipsa":
        log("memoria pozelor si a filmelor din nou mapata: %s" % detaliu)
        _es_anuntat = ("ok", "")
    return fel, detaliu, cheie


def _procese_cu_numele(nume, proc=None):
    """pid-urile proceselor vii cu numele dat (/proc/<pid>/comm; un proces terminat, "Z", nu se socoteste)"""
    proc = proc or PROC_DIR
    rez = []
    try:
        intrari = os.listdir(proc)
    except OSError:
        return rez
    for x in intrari:
        if not x.isdigit():
            continue
        try:
            with open(os.path.join(proc, x, "comm")) as f:
                if f.read().strip() != nume:
                    continue
            with open(os.path.join(proc, x, "stat")) as f:
                stare = f.read().rsplit(")", 1)[-1].split()
            if stare and stare[0] == "Z":
                continue
        except (OSError, IndexError):
            continue
        rez.append(int(x))
    return rez


def _pid_viu(cale, proc=None):
    proc = proc or PROC_DIR
    try:
        with open(cale) as f:
            pid = int(f.read().strip() or "0")
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        with open(os.path.join(proc, str(pid), "stat")) as f:
            stare = f.read().rsplit(")", 1)[-1].split()
        return not (stare and stare[0] == "Z")
    except (OSError, IndexError):
        return False


def dbus_raspunde(socluri=None):
    """True cand soclul D-Bus de sistem primeste o conexiune (o deschidere si o inchidere; nu se trimite nimic)"""
    import socket
    for cale in socluri or DBUS_SOCLURI:
        if not cale:
            continue
        try:
            if not os.path.exists(cale):
                continue
        except OSError:
            continue
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(SERVICII_SOCLU_S)
        try:
            s.connect(cale)
            return True
        except OSError:
            pass
        finally:
            s.close()
    return False


def pornit_la_pornire(script, rc_dirs=None):
    """serviciul are o legatura S..<script> intr-un dosar rc al nivelurilor 2-5 (pornit la pornirea receptorului)"""
    for d in rc_dirs or RC_DIRS:
        try:
            for x in os.listdir(d):
                if x.startswith("S") and x[3:] == script and x[1:3].isdigit():
                    return True
        except OSError:
            continue
    return False


def citeste_servicii():
    """{cheie: {"instalat", "pornit_la_pornire", "proces", "raspunde"}} pentru SERVICII (numai citiri)"""
    rez = {}
    for cheie, script, proces in SERVICII:
        d = {"instalat": os.path.exists(os.path.join(INIT_DIR, script)),
             "pornit_la_pornire": pornit_la_pornire(script)}
        if proces:
            d["proces"] = bool(_procese_cu_numele(proces))
        else:
            d["proces"] = _pid_viu(NUME_LOCAL_PID)
        d["raspunde"] = dbus_raspunde() if cheie == "dbus" and d["proces"] else d["proces"]
        rez[cheie] = d
    return rez


def rc_in_lucru(proc=None):
    """True cat ruleaza scripturile de pornire: un proces viu cu /etc/init.d/rc sau /etc/init.d/rcS in linia de comanda
    (inittab: "/etc/init.d/rc 3", deci "/bin/sh /etc/init.d/rc 3"; numai citiri din /proc)"""
    proc = proc or PROC_DIR
    try:
        intrari = os.listdir(proc)
    except OSError:
        return False
    for x in intrari:
        if not x.isdigit():
            continue
        try:
            with open(os.path.join(proc, x, "cmdline"), "rb") as f:
                argumente = f.read(512).split(b"\0")
        except OSError:
            continue
        if any(a.endswith((b"/init.d/rc", b"/init.d/rcS")) for a in argumente[:3]):
            try:
                with open(os.path.join(proc, x, "stat")) as f:
                    stare = f.read().rsplit(")", 1)[-1].split()
                if stare and stare[0] == "Z":
                    continue
            except (OSError, IndexError):
                pass
            return True
    return False


def lipsa_procese(stari):
    """Multimea serviciilor (avahi, nume-local) pornite la pornirea receptorului care nu au proces acum (numai citiri)"""
    return set(c for c in ("avahi", "nume-local") if (stari.get(c) or {}).get("instalat") and
               (stari.get(c) or {}).get("pornit_la_pornire") and not (stari.get(c) or {}).get("proces"))


def hotarare_servicii(stari, uptime_s, refuzuri, porniri, acum, rc_ruleaza=False, lipsa_inainte=None):
    """Fara efecte. -> (lista de (cheie, script, actiune), refuzuri noi, starea pentru ecran, detaliu).
    actiune: "start" sau "restart" (dbus cu procesul ramas, dar fara raspuns de SERVICII_CONFIRMARI ori la rand).
    porniri: {cheie: [ceas monoton al pornirilor]}; acum: ceasul monoton.
    rc_ruleaza (r16): scripturile de pornire (rc, rcS) inca ruleaza; pana la SERVICII_RC_MAX_S de la pornire nimic nu e
    cazut, rc ii porneste la randul lor.
    lipsa_inainte (r16): serviciile fara proces la verificarea de dinainte (lipsa_procese); avahi si numele local care
    lipsesc acum, dar nu si atunci, se mai cauta o data. None = fara confirmare (ca inainte de r16)."""
    if uptime_s is not None and uptime_s < SERVICII_PORNIRE_S:
        return [], 0, "", "pornirea receptorului: serviciile le porneste rc5"
    if rc_ruleaza and (uptime_s is None or uptime_s < SERVICII_RC_MAX_S):
        return [], 0, "", "pornirea receptorului: scripturile de pornire (rc) inca ruleaza"
    de_pornit = []
    cazute = []
    limitate = []

    def poate(cheie):
        recente = [t for t in porniri.get(cheie, []) if acum - t < 3600]
        return len(recente) < SERVICII_MAX_ORA

    dbus = stari.get("dbus") or {}
    dbus_bun = True
    if dbus.get("instalat"):
        if not dbus.get("proces"):
            refuzuri = 0
            dbus_bun = False
            cazute.append("dbus")
            if poate("dbus"):
                de_pornit.append(("dbus", "dbus-1", "start"))
            else:
                limitate.append("dbus")
        elif not dbus.get("raspunde"):
            refuzuri += 1
            dbus_bun = False
            if refuzuri >= SERVICII_CONFIRMARI:
                cazute.append("dbus")
                if poate("dbus"):
                    de_pornit.append(("dbus", "dbus-1", "restart"))
                    refuzuri = 0
                else:
                    limitate.append("dbus")
        else:
            refuzuri = 0
    # avahi si numele local: numai cele pornite la pornirea receptorului, numai cu D-Bus mergand (sau pornit acum)
    dbus_va_merge = dbus_bun or any(c == "dbus" for c, _s, _a in de_pornit)
    avahi_va_merge = True
    de_confirmat = []
    for cheie, script in (("avahi", "avahi-daemon"), ("nume-local", "hds-nume-local")):
        d = stari.get(cheie) or {}
        if not d.get("instalat") or not d.get("pornit_la_pornire"):
            continue
        if d.get("proces"):
            continue
        if lipsa_inainte is not None and cheie not in lipsa_inainte:
            # prima verificare fara proces: poate e oprit chiar acum de cine il porneste la loc (schimbarea retelei)
            de_confirmat.append(cheie)
            if cheie == "avahi":
                avahi_va_merge = False
            continue
        cazute.append(cheie)
        if cheie == "avahi":
            avahi_va_merge = False
        if not dbus_va_merge or (cheie == "nume-local" and not avahi_va_merge and not any(
                c == "avahi" for c, _s, _a in de_pornit)):
            continue
        if poate(cheie):
            de_pornit.append((cheie, script, "start"))
        else:
            limitate.append(cheie)
    if de_pornit:
        # cel mult o pornire la o verificare (vezi documentatia nivelului 6); ordinea listei e dbus, avahi, numele local
        stare = "repornit"
        detaliu = "cazute: %s; pornit din nou acum: %s" % (", ".join(cazute), de_pornit[0][0])
        if len(de_pornit) > 1:
            detaliu += "; la verificarile urmatoare: %s" % ", ".join(c for c, _s, _a in de_pornit[1:])
        de_pornit = de_pornit[:1]
    elif limitate:
        stare = "esec"
        detaliu = "cazute: %s; pornite de %d ori in ultima ora, nu mai incerc pana trece ora" % (
            ", ".join(limitate), SERVICII_MAX_ORA)
    elif cazute or (not dbus_bun):
        stare = "esec" if cazute else "ok"
        detaliu = ("cazute: %s (fara D-Bus nu se pot porni)" % ", ".join(cazute)) if cazute else \
            "soclul D-Bus nu raspunde (%d/%d)" % (refuzuri, SERVICII_CONFIRMARI)
    elif de_confirmat:
        stare, detaliu = "ok", "fara proces acum: %s; se verifica din nou la trecerea urmatoare" % ", ".join(de_confirmat)
    else:
        stare, detaliu = "ok", "dbus, avahi si numele local merg"
    return de_pornit, refuzuri, stare, detaliu


def _porneste_serviciul(script, actiune):
    """Ruleaza /etc/init.d/<script> <actiune>. -> (pornit, cod): pornit False cand nu s-a rulat nimic (un script de
    data trecuta e tot agatat sau programul nu a pornit).

    Ca _ng_ruleaza: nu subprocess.run(timeout=...) (dupa timp kill() si wait() FARA limita: un script agatat in nucleu
    ar opri bucla, hranirea si ar reporni dur receptorul). Iesirile merg in /dev/null, nu intr-o teava: demonul pornit
    de script mosteneste descriptorii si o teava ar ramane deschisa cat traieste demonul."""
    for copil in list(_srv_copii_blocati):
        if copil.poll() is not None:
            _srv_copii_blocati.remove(copil)
    if _srv_copii_blocati:
        return False, "script de data trecuta tot agatat (pid %d)" % _srv_copii_blocati[0].pid
    cale = os.path.join(INIT_DIR, script)
    try:
        copil = subprocess.Popen([cale, actiune], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
    except OSError as e:
        return False, "eroare: %s" % e
    try:
        return True, copil.wait(timeout=SERVICII_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        try:
            copil.kill()
        except OSError:
            pass
        try:
            copil.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            _srv_copii_blocati.append(copil)  # stare D: poll() la verificarile urmatoare
        return True, "timp depasit (%ds)" % SERVICII_TIMEOUT_S


def jurnal_servicii(text):
    """un rand in SERVICII_JURNAL_PATH (ora de perete); peste SERVICII_JURNAL_MAX octeti ramane a doua jumatate"""
    rand = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
    try:
        try:
            if os.path.getsize(SERVICII_JURNAL_PATH) > SERVICII_JURNAL_MAX:
                with open(SERVICII_JURNAL_PATH, "rb") as f:
                    f.seek(-SERVICII_JURNAL_MAX // 2, os.SEEK_END)
                    coada = f.read()
                with open(SERVICII_JURNAL_PATH + ".nou", "wb") as f:
                    f.write(coada.split(b"\n", 1)[-1])
                os.replace(SERVICII_JURNAL_PATH + ".nou", SERVICII_JURNAL_PATH)
        except (OSError, ValueError):
            pass
        with open(SERVICII_JURNAL_PATH, "a") as f:
            f.write(rand)
    except OSError:
        pass


def randuri_mesaje(cuvant, cale=None):
    """r17: ultimele MOTIV_RANDURI randuri care contin cuvant din coada lui MESAJE_PATH (cel mult MOTIV_MESAJE_OCTETI
    octeti de la capat, nu tot fisierul: o trecere a nivelului 6 are timp marginit). Fiecare rand taiat la
    MOTIV_RAND_MAX caractere. [] daca fisierul lipseste."""
    cale = cale or MESAJE_PATH
    try:
        with open(cale, "rb") as f:
            f.seek(0, os.SEEK_END)
            marime = f.tell()
            f.seek(max(0, marime - MOTIV_MESAJE_OCTETI))
            date = f.read(MOTIV_MESAJE_OCTETI)
    except OSError:
        return []
    randuri = date.split(b"\n")
    if marime > MOTIV_MESAJE_OCTETI:
        randuri = randuri[1:]  # primul rand e taiat la mijloc
    cuvant_b = cuvant.encode("utf-8")
    gasite = [r for r in randuri if cuvant_b in r][-MOTIV_RANDURI:]
    return [r.decode("utf-8", "replace").strip()[:MOTIV_RAND_MAX] for r in gasite]


def motiv_lipsa(cheie, uptime=None):
    """r17: de ce lipseste avahi-daemon ("avahi") sau hds-nume-local ("nume-local"), intr-un singur rand: uptime-ul,
    fisierul pid si ultimele randuri ale serviciului din messages. Nu arunca niciodata (e chemat din nivelul 6)."""
    try:
        if cheie == "avahi":
            cai, cuvant = AVAHI_PID, "avahi-daemon"
        else:
            cai, cuvant = (NUME_LOCAL_PID,), "hds-nume-local"
        parti = ["uptime=%s" % ("%ds" % uptime if uptime is not None else "?")]
        text_pid = "fisier pid lipsa (oprit curat sau nepornit)"
        for cale in cai:
            try:
                with open(cale) as f:
                    continut = f.read(32).strip()
            except OSError:
                continue
            if continut.isdigit():
                try:
                    with open(os.path.join(PROC_DIR, continut, "comm")) as f:
                        nume = f.read(64).strip()
                except OSError:
                    nume = None
                if nume is None:
                    text_pid = "fisier pid %s ramas, pid %s mort (oprit brusc sau cazut)" % (cale, continut)
                else:
                    text_pid = "fisier pid %s ramas, pid %s folosit acum de %s" % (cale, continut, nume)
            else:
                text_pid = "fisier pid %s ramas, fara pid in el" % cale
            break
        parti.append(text_pid)
        randuri = randuri_mesaje(cuvant)
        parti.append("messages: " + (" | ".join(randuri) if randuri else "nimic despre %s in coada" % cuvant))
        return "; ".join(parti)
    except Exception as e:
        return "motivul nu s-a putut citi: %r" % (e,)


def _secunde_utc(an, luna, zi, ora, minut, secunda):
    """secundele UTC ale unei date (zilele din calendarul gregorian), fara calendar/datetime (RDEPENDS neschimbat)"""
    a = an - (1 if luna <= 2 else 0)
    era = a // 400
    ya = a - era * 400
    zi_an = (153 * (luna + (-3 if luna > 2 else 9)) + 2) // 5 + zi - 1
    ze = ya * 365 + ya // 4 - ya // 100 + zi_an
    zile = era * 146097 + ze - 719468
    return zile * 86400 + ora * 3600 + minut * 60 + secunda


def citeste_ora_salvata(cale=None):
    """r17: ora din FAKE_HWCLOCK_PATH ("%Y-%m-%d %H:%M:%S", UTC) in secunde, sau None"""
    try:
        with open(cale or FAKE_HWCLOCK_PATH) as f:
            text = f.read(64).strip()
        data, ora = text.split()[:2]
        an, luna, zi = (int(x) for x in data.split("-"))
        h, m, s = (int(x) for x in ora.split(":"))
        if not (1 <= luna <= 12 and 1 <= zi <= 31 and 0 <= h < 24 and 0 <= m < 60 and 0 <= s < 61):
            return None
        return _secunde_utc(an, luna, zi, h, m, s)
    except (OSError, ValueError):
        return None


def stare_ceas_pornire(acum, uptime, salvat):
    """r17, fara efecte. acum: ora de perete (time.time()); uptime: secundele de la pornirea receptorului; salvat: ora
    salvata (citeste_ora_salvata) sau None. La pornire ceasul pleaca de la ora salvata; cat nu s-a mutat (NTP, HTTPS,
    transponder), pornirea socotita pe ceas (acum - uptime) cade langa ea (CEAS_TOLERANTA_S).
    Limita: un paznic repornit de init mai tarziu, dupa o ora sigura salvata in primele minute ale aceleiasi porniri,
    poate fi socotit tot "ora salvata"; uptime-ul din rand arata atunci ca nu e pornirea receptorului."""
    if salvat is None:
        return "ceas=necunoscut (fara ora salvata)"
    text = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(salvat))
    if uptime is None:
        return "ceas=? (fara uptime; ora salvata %s UTC)" % text
    abatere = int(round((acum - uptime) - salvat))
    if abs(abatere) <= CEAS_TOLERANTA_S:
        return "ceas=ORA SALVATA, nesincronizat inca (%s UTC + uptime)" % text
    return "ceas=mutat fata de ora salvata (%+d s; ora salvata %s UTC)" % (abatere, text)


def rand_pornire():
    """r17: randul "pornire hds-watchdog.py" cu uptime-ul si starea ceasului (stare_ceas_pornire). Nu arunca: o eroare
    aici ar opri paznicul inainte de /dev/watchdog, iar init l-ar porni in bucla."""
    baza = "pornire hds-watchdog.py (tinta=%s, interval=%ds, prag confirmare=%d verificari, %d cand e ocupat, " \
        "jurnal=%s)" % (TARGET_PROCESS, PET_INTERVAL_S, CONFIRM_HANG_CHECKS, CONFIRM_HANG_CHECKS_OCUPAT, LOG_PATH)
    try:
        up = _paznic_pornit_la if _paznic_pornit_la is not None else uptime_precis()
        up = int(up) if up is not None else None
        return "%s; uptime=%s; %s" % (baza, "%ds" % up if up is not None else "?",
                                      stare_ceas_pornire(time.time(), up, citeste_ora_salvata()))
    except Exception as e:
        return "%s; ceas: %r" % (baza, e)


def pas_servicii(acum):
    """Nivelul 6: o verificare a serviciilor de sistem si pornirile hotarate; o linie in jurnal la fiecare pornire si
    la schimbarea starii. Intoarce starea (servicii, detaliu, ora)."""
    global _srv_refuzuri, _srv_stare, _srv_reporniri, _srv_anuntat, _srv_lipsa, _srv_motiv_scris
    stari = citeste_servicii()
    uptime = uptime_secunde()
    # r16: rc citit numai dupa SERVICII_PORNIRE_S si pana la SERVICII_RC_MAX_S (dupa aceea nu mai conteaza)
    rc = uptime is not None and SERVICII_PORNIRE_S <= uptime < SERVICII_RC_MAX_S and rc_in_lucru()
    de_pornit, _srv_refuzuri, stare, detaliu = hotarare_servicii(stari, uptime, _srv_refuzuri, _srv_porniri, acum,
                                                                 rc_ruleaza=rc, lipsa_inainte=_srv_lipsa)
    lipsa_inainte = _srv_lipsa
    # ce lipseste se tine minte numai dupa pornirea receptorului (in timpul ei serviciile inca pornesc)
    _srv_lipsa = set() if rc or (uptime is not None and uptime < SERVICII_PORNIRE_S) else lipsa_procese(stari)
    # r17: cazute = fara proces si acum, si la verificarea de dinainte (ca in hotarare_servicii); o data pe cadere,
    # inaintea randului pornirii, de ce lipseste
    cazute = _srv_lipsa & lipsa_inainte
    for cheie in sorted(cazute - _srv_motiv_scris):
        motiv = motiv_lipsa(cheie, uptime)
        log("servicii: %s cazut, de ce: %s" % (cheie, motiv))
        jurnal_servicii("%s cazut, de ce: %s" % (cheie, motiv))
    _srv_motiv_scris = cazute
    # hotarare_servicii da cel mult unul; fara sleep si fara asteptarea soclului: ce depinde de el (avahi dupa dbus,
    # numele dupa avahi) se porneste la verificarea urmatoare, cand se vede ca merge
    for cheie, script, actiune in de_pornit[:1]:
        pornit, cod = _porneste_serviciul(script, actiune)
        if pornit:
            _srv_porniri.setdefault(cheie, []).append(acum)
            _srv_porniri[cheie] = [t for t in _srv_porniri[cheie] if acum - t < 3600]
            _srv_reporniri += 1
            log("servicii: %s cazut, %s %s -> %s" % (cheie, script, actiune, cod))
            jurnal_servicii("%s cazut; pornit din nou de paznic (%s %s, cod %s)" % (cheie, script, actiune, cod))
        else:
            log("servicii: %s cazut, nu pornesc acum: %s" % (cheie, cod))
            jurnal_servicii("%s cazut; nu l-am pornit acum: %s" % (cheie, cod))
            stare, detaliu = "esec", "%s cazut; nu l-am pornit: %s" % (cheie, cod)
            de_pornit = []
    if de_pornit or (stare, detaliu) != _srv_anuntat:
        if stare != "ok" or (_srv_anuntat is not None and _srv_anuntat[0] != "ok"):
            log("servicii: %s (%s)" % (stare, detaliu))
            jurnal_servicii("stare %s: %s" % (stare, detaliu))
        _srv_anuntat = (stare, detaliu)
    if stare:
        # ora ramane a ultimei porniri facute de paznic (0 = niciuna de la pornirea lui)
        _srv_stare = (stare, detaliu, int(time.time()) if de_pornit else _srv_stare[2])
    return _srv_stare


def un_pas(fd, confirmed, urmatoarea_netguard):
    """O verificare (la fiecare PET_INTERVAL_S). Intoarce (confirmed, urmatoarea_netguard). Separata de main(),
    ca probele sa poata rula verificari cu /proc, /dev/watchdog si fisierele inlocuite.
    Ordinea: bataia enigma2 (semnul „ocupat” alege pragul nivelului 2), nivelul 2 si hranirea, nivelul 3 si SIGKILL,
    nivelul 5 (decodorul video), anuntul memoriei pozelor si a filmelor, nivelul 4 si curatarea jurnalelor de cadere,
    starea pentru ecran si web."""
    acum = time.monotonic()
    pids = find_target_pids(TARGET_PROCESS)
    pid_enigma2 = min(pids) if pids else None
    bataie = citeste_bataie()
    # r14: cat ruleaza opkg, bataia poarta motivul OPKG_MOTIV (nivelurile 3 si 5 asteapta, nivelul 2 pragul lung)
    try:
        opkg = opkg_in_lucru(acum)
    except Exception as e:
        opkg = []
        log("eroare la cautarea lui opkg: %r" % (e,))
    if opkg:
        bataie = bataie_cu_opkg(bataie, acum)
    proprie = bataie if (bataie is not None and bataie["pid"] == pid_enigma2) else None
    motive, _ramas = ocupat_valabil(proprie, acum)
    # programul de noapte al culegerii (separat de enigma2, fara semn in bataie) muta motorul si acordeaza mereu: pragul
    # lung, ca la scanare (05.10.2026 12:52: un minut in driver la trecerea pe 36,0E a dat repornirea dura)
    lung = bool(motive) or culegere_de_noapte() or bool(opkg)
    healthy, detail = check_health(CONFIRM_HANG_CHECKS_OCUPAT if lung else CONFIRM_HANG_CHECKS, pids)
    if healthy and not confirmed:
        # gardat si pe `not confirmed`, nu doar pe `healthy` (bug gasit 21.09.2026, verificare
        # adversariala separata): fara asta, daca sysrq esueaza sa reporneasca efectiv (ambele
        # scrieri pot da OSError, doar logate) si firul care declansase blocajul se deblocheaza
        # singur mai tarziu, hranirea ar fi reluat -- planul de rezerva "garantat" (watchdogul HW
        # expira oricum) s-ar fi dezactivat tacit. Odata confirmat, NU mai hranim niciodata, orice
        # ar arata `check_health()` dupa -- exact ce zicea deja comentariul de mai jos, acum si in cod.
        pet(fd)
    elif not confirmed:
        confirmed = True
        log(detail)
        force_hard_reboot(detail)
        # NU mai hranim de aici incolo -- fie sysrq a reusit deja (receptorul reporneste),
        # fie watchdogul HW expira oricum, garantat, in max PET_INTERVAL_S * CONFIRM_HANG_CHECKS
        # secunde de la ultima hranire reala de mai sus.

    fel, detaliu = "repornire-dura", detail
    try:
        interfata, asteptare = setari_paznic()
    except Exception:
        interfata, asteptare = INTERFATA_IMPLICIT, ASTEPTARE_IMPLICITA_S
    # Jurnalul vietii vine dupa hranire. Cand repornirea dura e deja ceruta urmarim iesirea, fara stive noi.
    try:
        pas_viata_enigma2(acum, pid_enigma2, bataie, diagnostic=not confirmed)
    except Exception as e:
        log("eroare la jurnalul vietii enigma2: %r" % (e,))

    # Nivelul 3 (blocaj moale) -- independent de nivelul 2 de mai sus, dar sarit daca o repornire
    # dura e deja in curs (fara rost sa mai trimitem SIGTERM catre un sistem care oricum reporneste).
    # O eroare neprevazuta aici nu are voie sa opreasca bucla (hranirea watchdogului HW).
    if not confirmed:
        # 0.7.6 (WDG): iesirea ceruta care nu se termina (semnul din mytest.py dupa runReactor), inainte de nivelul 3
        try:
            pas_iesire_ceruta(acum, opkg)
        except Exception as e:
            log("eroare interna la iesirea ceruta: %r" % (e,))
        try:
            fel, detaliu, interfata, asteptare = pas_blocaj_moale(acum, pid_enigma2, bataie)
            pas_sigkill(acum, pids)
        except Exception as e:
            fel, detaliu = "necunoscut", "eroare interna la nivelul 3: %r" % (e,)
            log(detaliu)

    # Nivelul 5 (decodorul video fara memorie): sarit cand repornirea dura e deja in curs; cat timp un SIGTERM al
    # nivelului 3 asteapta iesirea enigma2, interfata nu se socoteste vie. O eroare aici nu opreste bucla.
    fel5 = ""
    if not confirmed:
        try:
            fel5, _detaliu5 = pas_decodor(acum, fel if _sigterm is None else "sigterm", interfata, proprie)
        except Exception as e:
            fel5 = "eroare"
            try:
                log("eroare interna la nivelul 5: %r" % (e,))
            except Exception:
                pass

    # Anuntul memoriei pozelor si a filmelor (dupa nivelul 5, care a citit jurnalul nucleului): numai starea si jurnalul,
    # nicio repornire. O eroare aici nu opreste bucla.
    memorie_es = None
    if not confirmed:
        try:
            memorie_es = pas_memorie_es(acum, proprie is not None and proprie.get("redare") in ("tv", "radio"))
        except Exception as e:
            try:
                log("eroare interna la anuntul memoriei pozelor si a filmelor: %r" % (e,))
            except Exception:
                pass

    # Nivelul 4 (paza rutei hds-netguard): la pornire, apoi la NETGUARD_INTERVAL_S secunde; sarit si el
    # cand repornirea dura e deja in curs. Tot atunci, curatarea jurnalelor de cadere (o cadere in bucla).
    if not confirmed and time.monotonic() >= urmatoarea_netguard:
        pas_netguard()
        try:
            curata_jurnale_cadere()
        except Exception:
            pass
        urmatoarea_netguard = time.monotonic() + NETGUARD_INTERVAL_S

    # Nivelul 6 (serviciile de sistem): la SERVICII_INTERVAL_S secunde, tacut; sarit cand repornirea dura e in curs.
    global _srv_urmatoarea
    if not confirmed and time.monotonic() >= _srv_urmatoarea:
        try:
            pas_servicii(time.monotonic())
        except Exception as e:
            try:
                log("eroare interna la nivelul 6 (servicii): %r" % (e,))
            except Exception:
                pass
        _srv_urmatoarea = time.monotonic() + SERVICII_INTERVAL_S

    try:
        scrie_stare_paznic(acum, fel, detaliu, interfata, asteptare, pid_enigma2, bataie, fel5, memorie_es)
    except Exception:
        pass
    return confirmed, urmatoarea_netguard


def main():
    global _paznic_pornit_la
    _paznic_pornit_la = uptime_precis()  # 0.7.5 (PRN): vezi PRIMA_BATAIE_NECUNOSCUTA
    # r17: cu uptime-ul si starea ceasului. NUMAI in jurnalul paznicului, nu si in hds-servicii.log: acolo un rand la
    # fiecare pornire ar face fisierul pe orice receptor sanatos, iar HdsBetaTester.doarStareBuna (ultimul rand "stare
    # ok") l-ar trimite ca jurnal de eroare; randul "de ce" de acolo are deja uptime-ul.
    log(rand_pornire())

    fd = open_watchdog()
    ensure_crash_log_dir()

    def on_sigterm(signum, frame):
        global _running
        log("SIGTERM primit (oprire/repornire normala a sistemului) -- dezarmez watchdogul HW curat")
        disarm_and_close(fd)
        _running = False
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_sigterm)
    signal.signal(signal.SIGINT, on_sigterm)

    confirmed = False
    urmatoarea_netguard = 0.0  # prima verificare a rutei chiar la pornire (L3: daca rcS n-a pus-o)
    while _running:
        confirmed, urmatoarea_netguard = un_pas(fd, confirmed, urmatoarea_netguard)
        time.sleep(PET_INTERVAL_S)


if __name__ == "__main__":
    main()

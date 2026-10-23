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

# ---- jurnalele de cadere ale enigma2: aceeasi cale ca in main/bsod.cpp (CRASH_LOG_DIR) ----
CRASH_LOG_DIR = os.environ.get("HDS_WATCHDOG_CRASH_DIR", "/home/root/logs")
CRASH_LOG_PASTRATE = 5       # ~100 KB fiecare; o cadere in bucla nu umple memoria interna

# ---- stivele Python ale enigma2 inainte de SIGTERM (mytest.py le leaga de faulthandler pe STIVE_SEMNAL) ----
STIVE_SEMNAL = int(getattr(signal, "SIGRTMIN", 34)) + 7   # 41 pe receptor; getattr: probele pe Windows
STIVE_PATH = os.environ.get("HDS_WATCHDOG_STIVE", "/tmp/enigma2-stive.txt")
STIVE_ASTEPTARE_S = 2.0      # scrierea stivelor ia cateva milisecunde; termenul e numai pentru un proces care nu raspunde
STIVE_PREFIX = "enigma2-stive-"

# ---- semnul pentru enigma2.sh: iesirea care urmeaza e ceruta de paznic (lotul paza-cadere-023, 05.10.2026) ----
# aceeasi cale ca HDS_PAZNIC_OPRIRE in tools/enigma2.sh.in (hdsatelit-image); /tmp e in RAM pe receptor
OPRIRE_PATH = os.environ.get("HDS_WATCHDOG_OPRIRE", "/tmp/hds-paznic.oprire")
UPTIME_PATH = os.environ.get("HDS_WATCHDOG_UPTIME", "/proc/uptime")

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
                % (stare, _ng_scurt(detaliu or ""), 1 if interfata else 0, asteptare, ",".join(motive), int(ramas),
                   varsta, _placa_secunde, _reporniri_interfata, ultima, int(_ultima_actiune[1]), acum, os.getpid(),
                   decodor or "", es_fel or "", es_cheie or "", _ng_scurt(es_detaliu or "")))
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
    for pid in pids:
        for tid in list_threads(pid):
            state, wchan = read_proc_state(pid, tid)
            if state == "D":
                d_state_now[(pid, tid)] = (wchan, read_switches(pid, tid) if tid != pid else None)

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
    return True, "sanatos"


def open_watchdog():
    global _placa_secunde
    fd = os.open(DEVICE_PATH, os.O_WRONLY)
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
    os.write(fd, b"\0")


def disarm_and_close(fd):
    """Oprire CURATA -- doar la opriri/reporniri normale, intentionate ale sistemului (SIGTERM de la
    init la schimbare de runlevel), NU la blocaj. 'V' (magic close) cere driverului sa dezarmeze."""
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


def cere_stivele(pid):
    """Inainte de SIGTERM: enigma2 scrie stivele tuturor firelor Python in STIVE_PATH (faulthandler, din semnal, merge
    si cu firul principal blocat); partea noua se copiaza in CRASH_LOG_DIR/enigma2-stive-<data>.txt, cu ultimele
    CRASH_LOG_PASTRATE pastrate. -> calea copiei sau None. Nu arunca."""
    if not _prinde_semnalul(pid, STIVE_SEMNAL):
        return None
    inainte = max(_marime(STIVE_PATH), 0)
    try:
        os.kill(pid, STIVE_SEMNAL)
    except OSError:
        return None
    capat = time.monotonic() + STIVE_ASTEPTARE_S
    ultima = inainte
    while time.monotonic() < capat:
        time.sleep(0.2)
        m = _marime(STIVE_PATH)
        if m > inainte and m == ultima:
            break
        ultima = m
    try:
        with open(STIVE_PATH, "rb") as f:
            f.seek(inainte)
            date = f.read(262144)
    except OSError:
        return None
    if not date:
        return None
    try:
        os.makedirs(CRASH_LOG_DIR, exist_ok=True)
        cale = os.path.join(CRASH_LOG_DIR, "%s%s-%d.txt" % (STIVE_PREFIX, time.strftime("%Y%m%d-%H%M%S"), pid))
        with open(cale, "wb") as f:
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
    log("stivele firelor Python ale enigma2 pid=%d pastrate in %s" % (pid, cale))
    return cale


def uptime_secunde():
    """Secundele intregi din /proc/uptime (acelasi ceas ca enigma2.sh: cut -d. -f1 /proc/uptime), sau None."""
    try:
        with open(UPTIME_PATH) as f:
            return int(float(f.read(64).split()[0]))
    except (OSError, ValueError, IndexError):
        return None


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


def scrie_semn_oprire(pid, sigkill=False):
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
        text = "pid=%d\nparinte=%d\nuptime=%d\nmotiv=blocaj-moale\n" % (pid, tata, up)
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
    try:
        with open(CULEGERE_PID_PATH) as f:
            text = f.read(64).strip()
    except FileNotFoundError:
        return False
    except OSError:
        return True
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


def hotarare_memorie_es(acum, demon, mapari, esec_la, imagine=True):
    """Hotararea anuntului, fara efecte (testata in teste/test_cadere_radio_2.py si test_memorie_0509.py). acum: ceas
    monoton (secunde de la pornirea receptorului); demon: pornire_demon_es(); mapari: citeste_mapari_es(); esec_la:
    esec_memorie_es(); imagine: un canal TV sau radio ruleaza de cel putin ES_PORNIRE_S (bataia enigma2, redare=tv
    sau radio).
    Intoarce (fel, detaliu), fel fiind:
      lipsa    demonul de acum nu are memoria: esecul maparii din jurnal dupa pornirea lui, sau nicio mapare de
               ES_MARIME in vmallocinfo la cel putin ES_PORNIRE_S de la pornirea lui cu un canal pornit; poza radio
               si filmele nu merg pana la repornirea receptorului
      ok       demonul de acum are memoria
      nesigur  demonul nu ruleaza, abia a pornit, vmallocinfo nu se poate citi, sau niciun canal inca (standby,
               nimic: demonul isi face maparea abia cand enigma2 foloseste decodorul): nu se spune nimic"""
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
    return "lipsa", "%s pid=%d nu are maparea de %d o in %s" % (ES_DEMON, pid, ES_MARIME, VMALLOCINFO_PATH)


def pas_memorie_es(acum, canal=True):
    """Pasul anuntului din bucla principala, dupa nivelul 5 (care a citit jurnalul nucleului si a strans grupurile in
    _es_grupuri): demonul si vmallocinfo la ES_VERIFICARE_S, pe loc la un esec nou si cand un canal abia a ajuns la
    ES_PORNIRE_S (sau s-a oprit), hotararea, o linie in jurnalul paznicului cand memoria incepe sa lipseasca (o data pe
    demon) si cand revine. Nu reporneste nimic. canal: bataia enigma2 de acum spune redare=tv sau radio.
    Intoarce (fel, detaliu, cheie); cheie = pid-ul demonului fara memorie, altfel „”."""
    global _es_esec_vazut, _es_urmatoarea, _es_demon, _es_mapari, _es_anuntat, _es_tv_de, _es_imagine
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
    fel, detaliu = hotarare_memorie_es(acum, _es_demon, _es_mapari, esec_la, imagine)
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
    proprie = bataie if (bataie is not None and bataie["pid"] == pid_enigma2) else None
    motive, _ramas = ocupat_valabil(proprie, acum)
    # programul de noapte al culegerii (separat de enigma2, fara semn in bataie) muta motorul si acordeaza mereu: pragul
    # lung, ca la scanare (05.10.2026 12:52: un minut in driver la trecerea pe 36,0E a dat repornirea dura)
    lung = bool(motive) or culegere_de_noapte()
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
    # Nivelul 3 (blocaj moale) -- independent de nivelul 2 de mai sus, dar sarit daca o repornire
    # dura e deja in curs (fara rost sa mai trimitem SIGTERM catre un sistem care oricum reporneste).
    # O eroare neprevazuta aici nu are voie sa opreasca bucla (hranirea watchdogului HW).
    if not confirmed:
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

    try:
        scrie_stare_paznic(acum, fel, detaliu, interfata, asteptare, pid_enigma2, bataie, fel5, memorie_es)
    except Exception:
        pass
    return confirmed, urmatoarea_netguard


def main():
    log("pornire hds-watchdog.py (tinta=%s, interval=%ds, prag confirmare=%d verificari, %d cand e ocupat, "
        "jurnal=%s)" % (TARGET_PROCESS, PET_INTERVAL_S, CONFIRM_HANG_CHECKS, CONFIRM_HANG_CHECKS_OCUPAT, LOG_PATH))

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

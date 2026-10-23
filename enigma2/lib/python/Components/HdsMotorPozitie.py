# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMotorPozitie.py - pozitia antenei cu motor, tinuta minte intre porniri.
#
# De ce: la pornire receptorul trimitea de fiecare data comanda de motor, cu "pozitie
# necunoscuta", chiar daca antena era deja pe satelitul ultimului program. Cauza: dupa pornire nucleul nu stie unde e
# antena (frontend.cpp:477-478, sec.cpp:1020-1021), deci primul acord trece de poarta din sec.cpp:735 si trimite 6E.
#
# Ce face:
#   - tine minte, in /etc/enigma2/hds-motor-pozitie.json, perechea (pozitie, comanda) a nucleului pentru fiecare tuner
#     cu motor, numai cand programul de pe acel tuner are semnal (revizia M5: nucleul trece tinta drept stiuta si fara
#     semnal, la expirarea timpului); o pereche noua vazuta fara semnal, o miscare in curs sau o pozitie uitata scriu
#     "necunoscut". Se scrie numai la schimbare (rar), in .nou si apoi os.replace;
#   - la fiecare scriere pune un semn nou (16 cifre hexazecimale la intamplare) in fisier si acelasi semn in FISIER_SEMN
#     (/home/root/hds-motor-pozitie.semn): in afara /etc/enigma2, deci nu intra in copia setarilor (care ia tot
#     dosarul), si pe partitia imaginii, deci un flash il sterge. Intai fisierul, apoi semnul;
#   - la pornire, o singura data, da perechea inapoi nucleului (hdsRestoreRotorPosition) numai daca cele doua semne sunt
#     egale (fisierul l-a scris chiar pornirea dinainte), daca setarile tunerului au aceeasi amprenta si daca nucleul nu
#     stie deja pozitia. Primul acord pe acelasi satelit calculeaza aceeasi comanda, deci nu mai pleaca nimic spre motor;
#     pe alt satelit comanda pleaca, dar cu plecarea stiuta;
#   - copia setarilor de la 04:33 avea 13,0E, antena a fost mutata pe 19,2E
#     inainte de flash, iar dupa flash copia pusa la loc a dat nucleului 13,0E: Magic TV a pornit fara comanda, deci
#     fara semnal. O copie e veche prin natura ei, iar antena se poate misca intre copie si punerea ei la loc. Acum un
#     fisier venit dintr-o copie (dupa flash, din meniu, cu trusa de pe PC) are semnul de la ora copiei, iar dupa flash
#     semnul din /home/root lipseste: pozitia nu se reda si primul acord trimite comanda. Orice cadere intre cele doua
#     scrieri lasa semne diferite: tot "nu se reda", partea sigura. Perechile unui fisier strain nu se cred nici dupa
#     prima scriere (se scriu "necunoscut"); intrarile tunerelor raman (Components/HdsLocul.py, pozitiiExista);
#   - plasa: daca antena a fost miscata cat receptorul era oprit (de mana, cu alt receptor), pozitia redata ar lasa-o
#     fara comanda. Programul de pe tunerul cu motor care sta fara semnal PLASA_S secunde la rand (acelasi satelit;
#     numaratoarea incepe din nou la un program de pe alt satelit si cand tunerul nu mai e al programului), cat nucleul
#     nu a miscat antena, face ca pozitia redata sa se uite si programul sa porneasca din nou o data: oprit,
#     ELIBERARE_CANAL_MS pauza pe eTimer, pornit. O pornire imediata a aceluiasi program ar lua canalul pastrat de
#     nucleu inca 3 s (lib/dvb/dvb.cpp:697-711, ReleaseUse/AddUse 1660-1680), fara acord nou, deci fara comanda de
#     motor: asa a ramas fara semnal (aceeasi capcana, rezolvata la fel, in Components/HdsLnbAplicare.py:32-35 si 55).
#     Orice miscare a nucleului dezarmeaza plasa (atunci comanda a plecat oricum); semnalul o confirma; dupa o folosire
#     nu se mai armeaza pana la urmatoarea pornire (fara bucle). Sub o inregistrare pe antena programul nu se opreste
#     (canalul ei ramane acelasi): pozitia se uita, comanda pleaca la urmatorul acord. Un zap al omului in pauza are
#     intaietate (programul plasei nu mai porneste); standby-ul in pauza primeste programul, ca sa-l porneasca la trezire.
#   - dupa flash primul acord a trimis comanda, iar antena nu a ajuns pe 19,2E;
#     ecranul a stat ~6 minute pe rotire (timpul maxim al nucleului pentru plecarea nestiuta, 360 s), apoi a ramas fara
#     semnal. Doua lucruri noi, in aceeasi bataie:
#       * plafonul: timpul maxim cand plecarea nu se stie se calculeaza din viteza invatata si din arcul vizibil
#         (Components/HdsMotorPlafon.py); se pune la redare, inaintea primului zap, si din bataie cand se schimba
#         ceva (o mutare invatata, locul);
#       * plasa de sosire: o mutare a nucleului terminata fara semnal (hdsRotorArrived = 1: timpul maxim trecut, sau
#         motorul oprit dupa curent), dupa care programul de pe acelasi tuner si de pe acelasi satelit tot nu are semnal
#         la SOSIRE_ASTEPTARE_MS de la oprire: pozitia se uita, iar programul se opreste si porneste din nou dupa
#         ELIBERARE_CANAL_MS (acelasi drum ca plasa de mai sus), deci comanda pleaca inca o data. Cel mult o data pe
#         mutare: mutarea pornita de aceasta reluare nu mai are reluare. Un zap al omului are intaietate (alt satelit,
#         alt program in pauza); sub o inregistrare pe antena, cu tunerul luat de alt ecran sau de comenzile motorului
#         nu se face nimic. Se aplica si primei mutari de dupa pornire sau dupa flash. O blocare confirmata vazuta
#         dupa oprire (cel putin SOSIRE_SEMNAL_MARJA_S), chiar pierduta pana la judecata (transponder slab), spune ca
#         antena a ajuns: comanda nu se mai trimite. Cand antena era pe satelitul plecarii la pornirea mutarii
#         (blocare confirmata acolo cu cel mult PLECARE_DOVEDITA_S inainte; comanda neurmata de motor sau motorul ramas
#         pe drum), pozitia nu se uita, ci se pune pe plecare cu comanda -1: nucleul trimite opririle si comanda cu
#         drumul stiut (de pilda 8,4 grade si ~6 s pe 18 V), nu cu drumul cel mai lung (84 de grade, 43 s pe 18 V
#         spre un transponder vertical, care nu se poate prinde pe 18 V); mutarea aceasta nu intra in invatarea
#         vitezei (HdsMotorViteza.faraInvatare: antena putea fi deja pe drum). Fara aceasta dovada (pozitie redata la
#         pornire, tunerul liber de mult) pozitia se uita, ca inainte; daca nici asa nu vine semnalul, readucerea de
#         mai jos trimite comanda cu drumul cel mai lung.
#   - antena cu motor a fost dusa departe de satelitul canalului de altceva decat
#     receptor (de trei ori intr-o seara; in urma motorului nicio comanda), iar nucleul, care o credea tot acolo, la
#     pierderea semnalului a reacordat fara comanda de motor (goto_omis, sec.cpp). Readucerea: tunerul cu motor fara
#     semnal READUCERE_S secunde la rand, cu motorul oprit si cu pozitia crezuta egala cu satelitul canalului (al
#     programului de pe televizor sau al unei inregistrari de pe acel tuner, si in standby): pozitia se uita si tunerul
#     se acordeaza din nou pe acelasi canal (eDVBSatelliteEquipmentControl.hdsReaduceAntena, ca reacordarea nucleului
#     dupa pierdere), deci pleaca aceeasi secventa ca la un zap (doua opriri, apoi comanda spre acelasi satelit), fara
#     oprirea programului sau a inregistrarii. O comanda spre pozitia pe care motorul o are deja nu il misca. Fara
#     semnal dupa incercare: urmatoarea peste READUCERE_PASI_S, dupa cate incercari la rand nu au adus semnalul (2 min,
#     2 min, 10 min, apoi la 30 min), niciodata in bucla stransa; semnalul tinut READUCERE_STABIL_S dupa o readucere
#     face ca pierderea urmatoare sa inceapa iar de la
#     READUCERE_S (antena a plecat din nou la cateva minute dupa o readucere reusita). Nu se face: pe tunerele fara
#     motor, cat motorul se misca, cu ecranele sau pagina motorului, Gasire semnal, scanarea, proba LNB-ului, lacatul
#     probei, in standby fara nimic pornit, cat lucreaza una dintre plasele de mai sus. Pe televizor nu se spune nimic
#     (panoul automat sta ascuns cat merge mutarea readucerii, ecranul negru ramane la Fara semnal); starea se vede
#     numai in pagina web a antenei si in /api/motor (stareReaducere), iar fiecare pas intra in urma motorului (randul
#     "readucere": pornita, semnal_revenit cu timpul pana la semnal si cat a mers motorul, fara_semnal cu urmatoarea
#     incercare, incheiata, refuzata). Mutarea readucerii nu are reluarea plasei de sosire (are pasii ei).
#   - in urma motorului: incercarea 2 a trimis o singura comanda spre 19,2E (doua opriri si 6E), pe
#     18 V, cu drumul cel mai lung (88,7 grade) si 107 s de asteptare a nucleului, iar antena nu a venit; urmatoarea
#     incercare ar fi venit abia peste 10 min (pasul al doilea, pentru ca semnalul adus de incercarea 1 tinuse numai
#     ~55 s). Aceeasi comanda trimisa din nou a adus semnalul de doua ori (09:45, 20:19), iar readucerea
#     de mana prin 13,0E a mers. Fara masurarea curentului (powerMeasurement) DiSEqC nu are raspuns: nu se vede daca
#     motorul a primit comanda sau daca se misca, singurul semn e semnalul care nu vine nici dupa drumul cel mai lung.
#     De aceea, dupa o incercare fara semnal, urmatoarea vine peste 2 min (nu 10) si, cand se poate, merge prin alta
#     pozitie (ocolirea): programul de pe televizor se opreste (ecranul e oricum negru), tunerul se ia ca la Gasire
#     semnal (HdsGasireSemnal.LuareTuner, cu coordonatorul extensiilor) si se acordeaza pe un transponder al
#     satelitului tunerului cel mai apropiat de al canalului, la cel putin OCOLIRE_MIN_GRADE grade de motor si deasupra
#     orizontului (pe receptorul de proba 13,0E), intai unul orizontal (18 V tot drumul), cu pozitia uitata: doua opriri,
#     comanda si 18 V cat drumul cel mai lung (lib/dvb/hdsrotire.h). La semnalul de acolo, la oprirea mutarii in nucleu
#     sau dupa drumul cel mai lung pana la el (_drumMaximS, aceeasi socoteala ca HdsMotorPlafon) plus
#     OCOLIRE_PRINDERE_S, pozitia se uita din nou si programul porneste iar (fara
#     intrebarea controlului parental, a trecut deja de ea), deci comanda spre satelitul canalului pleaca si ea cu
#     plecarea necunoscuta, 18 V cat drumul cel mai lung; de aici incercarea se judeca la fel ca una directa. Ocolirea
#     se face numai pentru programul de pe televizor, cu nimic altceva pe tuner: nu sub o inregistrare (ar opri-o), nu
#     cu o transmisie in retea sau un client al serverului de fluxuri, nu in standby, nu cu o inregistrare care porneste
#     in OCOLIRE_INREGISTRARE_S; atunci incercarea e directa, ca pana acum. Incercarea 1 e mereu directa, iar pana la
#     semnal se fac cel mult OCOLIRE_MAX ocoliri (un transponder oprit, cu antena la locul ei, arata la fel ca antena
#     plecata; dupa ele raman incercarile directe, la 10 si 30 min, care nu misca motorul daca e deja acolo). Ocolirea se
#     opreste la zap-ul omului (programul lui porneste), la standby (programul il primeste ecranul Standby), la o
#     inregistrare, la un ecran al antenei sau al comenzilor motorului (programul porneste iar, cu pozitia uitata), la
#     cererea tunerului de catre o extensie (programul porneste cand tunerul se elibereaza). In urma motorului: randurile
#     "ocolire", "ocolire_semnal" / "ocolire_fara_semnal" (capatul drumului ocolirii, apoi inapoi), "ocolire_refuzata"
#     (cu cod; incercarea merge direct), "ocolire_oprita"; cererea anuntata nucleului numeste pozitia ("ocolire prin
#     13,0E", "inapoi pe 19,2E"), deci o arata si comenzile de motor din urma. In /api/motor: "ocolire" si "esecuri".
#   - antena se roteste cat mai rar (motorul poate avea apa in el), iar un transponder oprit, cu antena la locul ei,
#     arata la fel ca antena plecata. De aceea, inaintea oricarei mutari a readucerii (directa sau ocolire), tunerul
#     incearca cel mult REFERINTE_MAX transpondere de referinta ale ACELUIASI satelit: intai ale canalelor prinse cel mai
#     recent pe el (notate la blocarea confirmata, o data pe program; fara transponderul canalului de acum), apoi din
#     lista satelitului, in ordinea ocolirii; niciodata unul care are un geaman pe alt satelit al motorului (aceeasi
#     polarizare, frecventa si rata: s-ar prinde si cu antena acolo, _areGeaman). Programul se opreste (ecranul e
#     oricum negru), tunerul se ia ca la
#     ocolire si se acordeaza FARA comanda de motor (HdsMotorTuner.acordFaraMotor; pozitia ramane stiuta), cel mult cat
#     timpul de prindere al nucleului plus marja, pe fiecare referinta. Prinsa una (VERIFICARE_PRINDERI citiri la
#     rand): antena e la locul ei, nicio comanda; programul porneste iar (pozitia stiuta, deci tot fara comanda), pe
#     televizor mesajul spune ca transponderul canalului nu emite acum (transponderNuEmite, Components/HdsEcranNegru.py),
#     iar verificarea se repeta rar (VERIFICARE_PASI_S), tot fara rotire. Niciuna prinsa: incercarea pleaca de aici, cu
#     tunerul in mana (ocolirea direct, altfel pozitia uitata si programul pornit iar, deci comanda spre satelit la
#     acordul lui). Tot asa inaintea comenzii trimise din nou de plasa de sosire (_verificaInainteDeReluare): referintele
#     satelitului tinta; prinsa una, antena a ajuns si nu mai pleaca nicio comanda. Si inaintea plasei pozitiei redate
#     la pornire (_plasaLaVerificare): prinsa una, pozitia redata e buna. Verificarea nu se face (readucerea
#     ramane ca inainte: incercari directe, care nu misca un motor aflat
#     deja acolo, fara ocolire) sub o inregistrare pe antena (o inregistrare nu se opreste niciodata pentru verificare),
#     cu o transmisie in retea, in standby, cu o inregistrare care porneste in OCOLIRE_INREGISTRARE_S, fara nicio
#     referinta. Ocolirea se face cel mult OCOLIRE_MAX ori pe o plecare a antenei: alta numai dupa ce o verificare a
#     aratat antena la locul ei si o verificare de dupa arata ca a plecat iar, sau la alt program (un zap incepe un sir
#     nou). Pierderea inceputa la un zap fara mutarea antenei, de pe un canal blocat pe acelasi satelit (blocare
#     confirmata cu cel mult DUPA_ZAP_S inainte), nu are deloc ocolire (_dupaZap). In urma motorului, randurile
#     "readucere" cu fazele "verificare" (fiecare referinta acordata, numita in cerere), "verificare_prins",
#     "verificare_fara_semnal", "verificare_refuzata", "verificare_oprita", "verificare_zap"; in /api/motor:
#     "verificare", "la_loc", "verificari".
#   - zap-urile pe ACELASI satelit cat lipseste semnalul nu mai amana readucerea: zap-uri la 8 s, toate pe satelitul
#     canalului si toate fara semnal, faceau sir nou la fiecare zap (READUCERE_S numarate iar de la zap) si opreau
#     verificarea, deci comanda spre motor a venit abia dupa ce zap-urile s-au oprit. Acum un zap pe acelasi satelit
#     (aceeasi pozitie orbitala, programul pe acelasi tuner) pastreaza sirul: pierderea se numara de la inceputul ei,
#     verificarile, incercarile, pasii si ocolirile raman, se schimba numai programul sirului (_zapAcelasiSatelit).
#     Programul nou are ZAP_PRINDERE_S sa prinda singur inainte ca o verificare sau o incercare sa-i ia tunerul (zap-uri
#     mai dese de atat amana inca, dar numai cat tin). Dupa ce verificarea a aratat antena la locul ei sau dupa ce
#     semnalul a revenit nu e nicio readucere de amanat: primul zap face sir nou, ca inainte, iar urmatoarele il
#     pastreaza (verificarea programului nou vine la READUCERE_S de la primul zap, nu de la ultimul). Zap-ul pe
#     acelasi satelit in timpul verificarii nu o mai opreste: programul cerut nu poate acorda cat tunerul e al
#     verificarii, deci se opreste si porneste el la capatul ei, in locul celui oprit (cu pozitia stiuta cand antena e
#     la locul ei, cu pozitia uitata, deci cu comanda spre acelasi satelit, cand nu e); randul "verificare_zap" in urma
#     (_zapInVerificare). La fel plasa pozitiei redate la pornire: un zap pe acelasi satelit nu o mai ia de la capat.
#     Zap-ul pe alt satelit sau pe alt tuner, standby-ul, comenzile motorului (ecran, web, meniu), ecranele antenei,
#     o inregistrare opresc in continuare verificarea si readucerea, ca pana acum. Cat merge mutarea unei incercari, un
#     zap pe acelasi satelit (pozitia e uitata) face nucleul sa trimita inca o data comanda spre aceeasi tinta: mutarea
#     lui e tot a readucerii (o judeca ea, nu plasa de sosire). Ocolirea se opreste si ea la un zap, ca pana acum; pe
#     satelitul canalului acordul zap-ului (pozitia e uitata de ocolire) aduce antena inapoi si e judecat ca
#     intoarcerea ocolirii, deci pasii si limitele raman, iar plasa de sosire nu mai trimite comanda din nou.
import json
import os
import sys

from Components import HdsMotorTuner as T

FISIER = "/etc/enigma2/hds-motor-pozitie.json"
FISIER_SEMN = "/home/root/hds-motor-pozitie.semn"
BATAIE_MS = 2000
PLASA_S = 15
# canalul folosit ultima data ramane pastrat 3 s dupa oprire (dvb.cpp:774-790); cu 3,5 s programul ia un canal nou
ELIBERARE_CANAL_MS = 3500
# plasa de sosire: dupa oprirea fara semnal nucleul mai acordeaza o data (SET_FRONTEND, sec.cpp:907-909), iar semnalul
# poate veni si atunci; numai dupa atatea milisecunde fara semnal se trimite comanda din nou
SOSIRE_ASTEPTARE_MS = 8000
# o oprire mai veche de atat (vazuta abia acum) nu se mai judeca
SOSIRE_VECHE_MS = 60000
# aceeasi mutare: aceeasi tinta, aceeasi comanda si pornirea la cel mult atatea milisecunde (ca HdsMotorViteza)
POTRIVIRE_MS = 1500
# mutarea reluarii: cea care porneste pe acelasi tuner, spre aceeasi tinta, in atatea milisecunde de la pornirea
# programului de catre reluare
RELUARE_VALABILA_MS = 30000
# plasa de sosire: o blocare confirmata (motorul oprit, pozitia crezuta = satelitul programului) vazuta la cel putin
# atatea secunde dupa oprire spune ca antena a ajuns, chiar daca la judecata semnalul s-a pierdut din nou (marja: la
# oprire nucleul acordeaza din nou, iar starea citita chiar atunci poate fi a acordului de dinainte)
SOSIRE_SEMNAL_MARJA_S = 1.0
# plecarea mutarii e dovedita de semnal cand programul a avut blocare confirmata pe satelitul plecarii cu cel mult
# atatea secunde inainte de pornirea mutarii (bataia e de 2 s; zap-ul vine imediat dupa)
PLECARE_DOVEDITA_S = 10
# readucerea: atatea secunde fara semnal, cu motorul oprit si antena crezuta pe satelit
READUCERE_S = 15
# dupa o incercare fara semnal, urmatoarea peste 2 min, 2 min, 10 min, apoi la 30 min (de la pornirea incercarii), dupa
# cate incercari la rand nu au adus semnalul: a doua comanda vine repede (in urma motorului: aceeasi comanda trimisa
# din nou a adus antena), apoi rar
READUCERE_PASI_S = (120, 120, 600, 1800)
# semnalul tinut atatea secunde dupa o readucere: pierderea urmatoare incepe iar de la READUCERE_S; o revenire mai
# scurta (semnal care se prinde si se pierde) continua pasii
READUCERE_STABIL_S = 60
# o incercare fara mutare vazuta in nucleu, sau cu motorul in mers de atata timp, se judeca oricum (paza)
READUCERE_JUDECATA_MAX_S = 600
# antena se intoarce de departe in ~55-60 s (masurat: 50-58 s pana la semnal la fiecare readucere de mana): o
# incercare nu se socoteste fara semnal mai devreme de atat de la pornirea ei
READUCERE_JUDECATA_MIN_S = 120
# semnalul venit in timpul mutarii: randul asteapta oprirea motorului (cat a mers) cel mult atatea secunde
READUCERE_OPRIRE_MAX_S = 10
# panoul automat arata o mutare oprita inca HdsMotorStare.MILISECUNDE_DUPA_SOSIRE: dupa readucere ramane ascuns si
# atat, plus marja
READUCERE_PANOU_MARJA_MS = 1000
CERERE_READUCERE = "readucere: incercarea %d"
# ocolirea: satelitul ei e la cel putin atatea grade de motor de al canalului (motorul trebuie sa se miste cu adevarat,
# iar fasciculul satelitului canalului nu se mai prinde acolo)
OCOLIRE_MIN_GRADE = 5.0
# cel mult atatea ocoliri pe o plecare a antenei (dupa ele antena nu se mai plimba, raman incercarile directe, rare); o
# verificare care arata antena la locul ei (sau alt program) le numara iar de la zero
OCOLIRE_MAX = 1
# fara ocolire cand o inregistrare porneste in atatea secunde (tunerul ar fi luat de noi), oprita la mai putin de atat
OCOLIRE_INREGISTRARE_S = 300
OCOLIRE_INREGISTRARE_OPRIRE_S = 60
# tunerul trebuie sa vina in atatea secunde (LuareTuner reincearca 3 s dupa oprirea programului)
OCOLIRE_LUARE_MAX_S = 10
# mutarea nucleului spre ocolire nevazuta dupa atatea secunde si acordul iesit din TUNING: s-a terminat fara mers
OCOLIRE_PORNIRE_S = 5
# drumul spre ocolire cand nu se poate socoti cel mai lung (locul sau viteza nu se stiu)
OCOLIRE_DRUM_IMPLICIT_S = 120
# peste drumul cel mai lung spre ocolire: prinderea semnalului acolo (si, pe un transponder vertical, capatul tinerii pe
# 18 V, socotita de nucleu cu marja lui; proba pe receptor: tinerea 64,4 s, drumul socotit ~61 s)
OCOLIRE_PRINDERE_S = 10
NUME_OCOLIRE = "Readucerea antenei"
# verificarea pe referinte: cate transpondere ale aceluiasi satelit se incearca, cate se tin minte pe satelit
REFERINTE_MAX = 2
REFERINTE_TINUTE = 4
# zap de pe un canal cu semnal: ultima blocare confirmata a canalului de dinainte e cu cel mult atatea secunde inaintea
# primei batai fara semnal pe canalul nou (doua batai de BATAIE_MS si marja)
DUPA_ZAP_S = 5
# zap pe acelasi satelit cat lipseste semnalul: programul ales de om are atatea secunde sa prinda singur (cat asteapta
# si ecranul negru pana la Fara semnal) inainte ca o verificare, o incercare sau plasa sa-i ia tunerul; numaratoarea
# pierderii nu incepe din nou la zap
ZAP_PRINDERE_S = 4
# o referinta e prinsa dupa atatea citiri blocate la rand (o bataie de BATAIE_MS intre ele)
VERIFICARE_PRINDERI = 2
# antena gasita la locul ei: verificarea urmatoare (tot fara rotire) peste 10 min, apoi la 30 min
VERIFICARE_PASI_S = (600, 1800)
# asteptarea prinderii pe o referinta cand timpul nucleului nu se poate citi
VERIFICARE_PRINDERE_S = 8
# doua transpondere sunt acelasi la aceeasi polarizare si frecventa la cel mult atatia kHz
VERIFICARE_TOLERANTA_KHZ = 2000
# geamanul unei referinte pe alt satelit: aceeasi polarizare si rata, frecventa la cel mult atatia kHz (marja de
# prindere a demodulatorului, peste diferentele de cativa kHz dintre liste)
VERIFICARE_GEAMAN_KHZ = 3000
CERERE_VERIFICARE = "readucere: verificarea %d, transponderul %d din %d: %s"
CERERE_VERIFICARE_PRINS = "readucere: verificarea %d, receptionat %s: antena la locul ei"
CERERE_VERIFICARE_FARA = "readucere: verificarea %d, fara semnal pe %s"
CERERE_VERIFICARE_REFUZATA = "readucere: verificarea %d refuzata: %s"
CERERE_VERIFICARE_OPRITA = "readucere: verificarea %d oprita: %s"
CERERE_VERIFICARE_ZAP = "readucere: verificarea %d continua dupa zap pe acelasi satelit"
CERERE_OCOLIRE = "readucere: incercarea %d, ocolire prin %s"
CERERE_INAPOI = "readucere: incercarea %d, inapoi pe %s"
CERERE_OCOLIRE_OPRITA = "readucere: incercarea %d, ocolirea oprita: %s"
# codurile randului "ocolire_refuzata"
OCOLIRE_COD_TUNER = -11      # tunerul nu s-a putut lua (o transmisie, o extensie): programul a fost pus la loc
OCOLIRE_COD_ACORD = -12      # nucleul a refuzat acordul pe transponderul ocolirii
MOTIV_ZAP = "zap"
MOTIV_STANDBY = "standby"
# ecranele care tin tunerul sau setarile antenei (aceleasi ca Components/HdsLnbAplicare.ECRANE_OCUPATE)
ECRANE_ANTENA = ("NimSetup", "ServiceScan", "ScanSetup", "ScanerSatelit", "ScanerMaiMultiSateliti", "Satfinder",
	"HdsDishMotorEcran", "PositionerSetup", "HdsPositionerSetup", "DiseqcTester", "HdsDabPrincipal",
	"HdsT2miPrincipal", "ConfigLNB")

_unic = None


def pozitie():
	global _unic
	if _unic is None:
		_unic = PozitieMotor()
	return _unic


def restaureaza():
	"""chemata o data, la crearea panoului automat (InfoBar), inaintea primului zap (ChannelSelection.py:1241-1243)"""
	try:
		pozitie().restaureaza()
	except Exception as e:
		T.jurnal("pozitia motorului nu a putut fi redata: %r" % (e,))


def inainteDeReconfigurare(sloturi):
	"""din SecConfigure.update(), inainte de sec.clear(): perechile (pozitie, comanda) stiute acum de nucleu, {slot: pereche}.
	clear() (sec.cpp) le pune pe -1 fara nicio urma, iar urmatorul zap pleca cu plecarea nestiuta: comanda spre satelitul
	pe care antena era deja si "Antena se roteste" pe tot timpul arcului (17.10, dupa iesirea din meniul antenei)."""
	try:
		return pozitie().perechiNucleu(sloturi)
	except Exception as e:
		T.jurnal("pozitia motorului inainte de reconfigurarea tunerelor: %r" % (e,))
		return {}


def dupaReconfigurare(perechi):
	"""din SecConfigure.update(), la sfarsit: perechile luate de inainteDeReconfigurare inapoi in nucleu"""
	if not perechi:
		return
	try:
		pozitie().redaDupaReconfigurare(perechi)
	except Exception as e:
		T.jurnal("pozitia motorului dupa reconfigurarea tunerelor: %r" % (e,))


def _navigatie():
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def _textProgram(ref):
	try:
		return ref.toString()
	except Exception:
		return str(ref)


# ---- trecerea pe internet (Components/HdsDvbIRezerva.py): cat imaginea unui canal de satelit fara semnal
# vine de pe internet, tunerul e liber, dar readucerea il socoteste tot al programului de satelit, fara semnal:
# verificarea pe referinte merge fara sa opreasca internetul, iar o rotire cere inapoi programul de satelit. Fara import:
# modulul e incarcat de pluginul DVB-I; lipsa lui lasa totul ca inainte.
def _rezerva():
	return sys.modules.get("Components.HdsDvbIRezerva")


def _rezervaOrbital(slot):
	m = _rezerva()
	try:
		return m.programInlocuit(slot) if m is not None else None
	except Exception:
		return None


def _rezervaRefSatelit():
	m = _rezerva()
	try:
		return m.refSatelit() if m is not None else None
	except Exception:
		return None


def _rezervaEste(ref):
	m = _rezerva()
	try:
		return bool(m is not None and m.esteRefRezerva(_textProgram(ref)))
	except Exception:
		return False


def _rezervaProbaInCurs(slot):
	m = _rezerva()
	try:
		return bool(m is not None and m.probaInCurs(slot))
	except Exception:
		return False


def _rezervaPreda(slot, luare):
	m = _rezerva()
	try:
		return bool(m is not None and m.predaSatelitului(slot, luare))
	except Exception as e:
		T.jurnal("trecerea pe internet nu a predat programul: %r" % (e,))
		return False


def _pereche(intrare):
	"""(pozitie, comanda) dintr-o intrare a fisierului; ce nu e numar = necunoscut"""
	try:
		return int(intrare.get("orbital", -1)), int(intrare.get("cmd", -1))
	except (TypeError, ValueError):
		return -1, -1


def _scrieAtomic(cale, text):
	nou = cale + ".nou"
	with open(nou, "w", encoding="ascii") as f:
		f.write(text)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


class PozitieMotor(object):
	def __init__(self, fisier=FISIER, fisier_semn=FISIER_SEMN):
		self.fisier = fisier
		self.fisier_semn = fisier_semn
		self.restaurat = False
		self.semn = None
		self.scris = self._citeste()
		# fisierul l-a scris pornirea dinainte: numai atunci perechile lui se cred
		self.semn_bun = self.semn is not None and self.semn == self._citesteSemn()
		# altfel perechile lui se uita (raman intrarile tunerelor, cu amprenta): nu se dau nucleului si nu ajung sa para
		# ale noastre cand alt tuner rescrie fisierul cu semnul nou
		self.straine = []
		if not self.semn_bun:
			for slot, intrare in self.scris.items():
				orbital, cmd = _pereche(intrare)
				if orbital >= 0 and cmd >= 0:
					self.straine.append(slot)
				intrare["orbital"], intrare["cmd"] = -1, -1
		self.plasa = {}
		self._t = None
		self._fara_functii = False
		self._de_reluat = None
		self._t_reluare = None
		# plasa de sosire: ultima mutare judecata pe fiecare slot (tinta, comanda, pornirea in ms) si reluarea in curs
		# ({"slot", "la", "pornita_la"}: pornita_la = ora pornirii programului de catre reluare, None cat e in pauza)
		self._judecate = {}
		self._reluare = None
		# ultima blocare confirmata a programului pe fiecare slot: (ora, orbital, program), numai cu motorul oprit si cu
		# pozitia crezuta de nucleu egala cu satelitul programului (in tinerea pe 18 V demodulatorul poate arata inca
		# blocarea transponderului de dinainte, acordul nou vine dupa ea)
		self._blocat = {}
		# referintele verificarii: transponderele prinse cel mai recent pe fiecare satelit (orbital -> [tp], cel mai nou
		# intai) si programul notat ultima data pe fiecare slot (o data pe program)
		self._invatate = {}
		self._invatat_program = {}
		# readucerea: sirul de acum pe fiecare slot, mutarea pornita de ultima incercare (tinta, ora in ms) si motivul
		# opririi spus ultima data in jurnal
		self._readuceri = {}
		self._mutari_readucere = {}
		self._readucere_lipsa = False
		self._readucere_oprita = None
		# panoul automat de eliberat pe slot dupa readucere (_panouLaSfarsit)
		self._panou_pana = {}
		# programul oprit de ocolire si ramas fara stapan dupa cedarea tunerului catre o extensie (_datoratBate)
		self._datorat = None

	# ------------------------------------------------------------------ fisierele

	def _citeste(self):
		try:
			with open(self.fisier, encoding="utf-8") as f:
				date = json.load(f)
			sloturi = date.get("sloturi", {})
			semn = date.get("semn")
			self.semn = semn if isinstance(semn, str) and semn else None
			return dict((str(k), v) for k, v in sloturi.items() if isinstance(v, dict))
		except (IOError, OSError):
			return {}
		except Exception as e:
			T.jurnal("fisierul pozitiei motorului e stricat, il ignor: %r" % (e,))
			return {}

	def _citesteSemn(self):
		try:
			with open(self.fisier_semn, encoding="ascii") as f:
				return f.read(64).strip() or None
		except Exception:
			return None

	def _scrie(self):
		semn = os.urandom(8).hex()
		try:
			# intai fisierul, apoi semnul: o cadere intre ele lasa semne diferite, deci la pornire "nu se reda"
			_scrieAtomic(self.fisier, json.dumps({"semn": semn, "sloturi": self.scris}, sort_keys=True))
		except Exception as e:
			T.jurnal("pozitia motorului nu a putut fi scrisa: %r" % (e,))
			return
		self.semn = semn
		try:
			_scrieAtomic(self.fisier_semn, semn + "\n")
			self.semn_bun = True
		except Exception as e:
			self.semn_bun = False
			T.jurnal("semnul pozitiei motorului nu a putut fi scris (%r); la pornire pozitia nu se reda" % (e,))

	def _amprenta(self, slot):
		"""setarile de care depinde comanda de motor: modul, coordonatele si orientarile (NimManager.py:1457-1461)"""
		try:
			from Components.config import config
			nim = config.Nims[slot]
			mod = nim.configMode.value
			parti = [mod]
			if mod == "simple":
				surse = [nim]
				parti.append(nim.diseqcMode.value)
			else:
				surse = []
				for numar in sorted(set(int(s.lnb.value) for s in list(nim.advanced.sat.values()))):
					if numar and nim.advanced.lnb[numar].diseqcMode.value == "1_2":
						surse.append(nim.advanced.lnb[numar])
						parti.append("lnb%d" % numar)
			for s in surse:
				parti += ["%.3f" % s.latitude.float, s.latitudeOrientation.value, "%.3f" % s.longitude.float,
					s.longitudeOrientation.value]
			return "|".join(parti)
		except Exception:
			return ""

	# ------------------------------------------------------------------ redarea

	def restaureaza(self):
		if self.restaurat:
			return
		self.restaurat = True
		# plafonul asteptarii cu plecarea nestiuta, inaintea primului zap (primul acord dupa flash e chiar acest caz)
		self._plafon()
		sec = T.controlSec()
		for slot, nume in T.tunereCuMotor():
			if str(slot) in self.straine:
				T.jurnal("pozitia tinuta minte pe tunerul %s nu se reda: fisierul nu e scris de pornirea dinainte (o copie "
					"a setarilor pusa la loc sau un flash); primul acord trimite comanda de motor" % nume)
				continue
			intrare = self.scris.get(str(slot))
			if not intrare:
				continue
			orbital, cmd = _pereche(intrare)
			if orbital < 0 or cmd < 0:
				continue
			if intrare.get("amprenta") != self._amprenta(slot):
				T.jurnal("setarile tunerului %s s-au schimbat; pozitia tinuta minte nu se reda" % nume)
				continue
			try:
				if sec.hdsKnownRotorPosition(slot) != -1:
					continue
				sec.hdsRestoreRotorPosition(slot, orbital, cmd)
			except AttributeError:
				self._fara_functii = True
				T.jurnal("nucleul nu are hdsRestoreRotorPosition; pozitia nu se reda")
				return
			self.plasa[slot] = {"pereche": (orbital, cmd), "vazut_la": None, "program": None}
			T.jurnal("pozitia antenei redata pe tunerul %s: %s (inaintea primului zap)" % (nume, orbital))
		# cronometrul porneste abia dupa redare: altfel prima citire (-1 dupa clear) ar scrie "necunoscut" peste fisier
		self._t = T.cronometru(self._bateSigur)
		self._t.start(BATAIE_MS, True)

	def perechiNucleu(self, sloturi):
		sec = T.controlSec()
		perechi = {}
		if sec is None or self._fara_functii:
			return perechi
		for slot in sloturi:
			try:
				pereche = (int(sec.hdsKnownRotorPosition(slot)), int(sec.hdsKnownRotorCmd(slot)))
			except AttributeError:
				return {}
			if pereche[0] >= 0 and pereche[1] >= 0:
				perechi[slot] = pereche
		return perechi

	def redaDupaReconfigurare(self, perechi):
		"""perechea de dinainte de clear() se da inapoi numai daca setarile de care depinde comanda de motor sunt cele cu
		care s-a scris pozitia (aceeasi amprenta ca la pornire) si daca nucleul n-a aflat intre timp alta pozitie; cu alte
		coordonate sau alt mod, comanda calculata ar fi alta, deci pozitia ramane uitata si primul acord trimite comanda"""
		sec = T.controlSec()
		if sec is None:
			return
		for slot, pereche in sorted(perechi.items()):
			nume = T.numeTuner(slot)
			intrare = self.scris.get(str(slot)) or {}
			if intrare.get("amprenta") != self._amprenta(slot):
				T.jurnal("setarile motorului de pe tunerul %s s-au schimbat; pozitia uitata la reconfigurare ramane uitata"
					% nume)
				continue
			if int(sec.hdsKnownRotorPosition(slot)) != -1:
				continue
			sec.hdsRestoreRotorPosition(slot, pereche[0], pereche[1])
			T.jurnal("pozitia antenei pastrata dupa reconfigurarea tunerelor pe %s: %s" % (nume, pereche[0]))

	# ------------------------------------------------------------------ bataia

	def _bateSigur(self):
		try:
			self._bate()
		except Exception as e:
			T.jurnal("pozitia motorului: %r" % (e,))
		if not self._fara_functii and self._t is not None:
			self._t.start(BATAIE_MS, True)

	def _bate(self):
		sec = T.controlSec()
		if sec is None:
			return
		self._plafon()
		self._datoratBate()
		for slot, _nume in T.tunereCuMotor():
			try:
				pereche = (int(sec.hdsKnownRotorPosition(slot)), int(sec.hdsKnownRotorCmd(slot)))
			except AttributeError:
				self._fara_functii = True
				return
			pe_slot, semnal = T.programulCurentPeSlot(slot)
			self._noteazaBlocarea(sec, slot, pereche, pe_slot, semnal)
			self._plasa(sec, slot, pereche, pe_slot, semnal)
			self._sosire(sec, slot, pe_slot, semnal)
			self._readucereSigur(sec, slot, pe_slot, semnal)
			self._tineMinte(slot, pereche, pe_slot, semnal)

	def _noteazaBlocarea(self, sec, slot, pereche, pe_slot, semnal):
		"""ultima blocare confirmata a programului de pe slot (ora, orbital): motorul oprit si pozitia crezuta de nucleu
		egala cu satelitul programului. O blocare citita in mers sau cu pozitia nevalidata nu se noteaza: in tinerea pe
		18 V acordul nou nu e facut inca, iar starea poate fi a transponderului de dinainte."""
		if not (pe_slot and semnal) or pereche[0] < 0:
			return
		try:
			if int(sec.hdsRotorMovingSlot()) == slot:
				return
		except (AttributeError, TypeError, ValueError):
			return
		orbital = _orbitalProgram()
		if orbital is not None and orbital == pereche[0]:
			program = self._programCurent()
			self._blocat[slot] = (T.acum(), orbital, program)
			self._invata(slot, orbital, program)

	def _invata(self, slot, orbital, program):
		"""transponderul programului blocat intra primul in referintele satelitului (o data pe program)"""
		if program is None or self._invatat_program.get(slot) == program:
			return
		self._invatat_program[slot] = program
		try:
			tp, _semnal = T.programPeTuner(slot)
		except Exception:
			return
		if tp and tp.get("orbital_position") == orbital:
			self._invataTp(orbital, tp)

	def _invataTp(self, orbital, tp):
		lista = [x for x in self._invatate.get(orbital, []) if not _acelasiTp(x, tp)]
		self._invatate[orbital] = ([dict(tp)] + lista)[:REFERINTE_TINUTE]

	def _referinte(self, slot, sat, tp_canal):
		"""cel mult REFERINTE_MAX transpondere ale satelitului de incercat, fara cel al canalului: intai cele prinse cel
		mai recent, apoi din lista satelitului, in ordinea ocolirii (orizontale, DVB-S cu rata mare)"""
		if REFERINTE_MAX <= 0:
			return []
		# un transponder care are un geaman pe alt satelit al motorului (aceeasi polarizare, frecventa si rata) s-ar
		# prinde si cu antena oprita acolo: nu dovedeste nimic, deci nu e referinta. Listele celorlalti sateliti se
		# citesc o singura data, numai cand chiar e de judecat un transponder (bucla principala nu are voie sa stea)
		vecini = []

		def bun(tp, alese):
			if (tp_canal and _acelasiTp(tp, tp_canal)) or any(_acelasiTp(tp, x) for x in alese):
				return False
			if not vecini:
				vecini.append(_transpondereVecine(slot, sat))
			return not _areGeaman(tp, vecini[0])
		alese = []
		for tp in self._invatate.get(sat, []):
			if bun(tp, alese):
				alese.append(tp)
				if len(alese) >= REFERINTE_MAX:
					return alese
		for tp in sorted(T.transpondereBune(sat, slot) or [], key=_ordineReferinta):
			if bun(tp, alese):
				alese.append(tp)
				if len(alese) >= REFERINTE_MAX:
					break
		return alese

	def _dupaZap(self, slot, orbital, program, acum):
		"""True cand pierderea incepe la un zap fara mutarea antenei, de pe un canal blocat pe acelasi satelit: ultima
		blocare confirmata e a altui program, pe acelasi satelit, cu cel mult DUPA_ZAP_S in urma"""
		b = self._blocat.get(slot)
		if program is None or b is None or len(b) < 3 or b[2] is None:
			return False
		return b[1] == orbital and b[2] != program and acum - b[0] <= DUPA_ZAP_S

	def _blocatDupa(self, slot, orbital, de_la):
		"""True daca programul de pe slot a avut blocare confirmata pe `orbital` la ora `de_la` sau dupa"""
		b = self._blocat.get(slot)
		return b is not None and b[1] == orbital and b[0] >= de_la

	def _plecareDovedita(self, slot, de_la, la, pornire_ms):
		"""plecarea mutarii (de_la), daca e dovedita de semnal: blocare confirmata pe ea cu cel mult PLECARE_DOVEDITA_S
		inainte de pornirea mutarii; altfel None (pozitie redata la pornire, tunerul liber de mult: antena putea pleca)"""
		if de_la is None or de_la < 0 or de_la == la:
			return None
		b = self._blocat.get(slot)
		if b is None or b[1] != de_la:
			return None
		pornire_s = pornire_ms / 1000.0
		if b[0] < pornire_s - PLECARE_DOVEDITA_S or b[0] > pornire_s + POTRIVIRE_MS / 1000.0:
			return None
		return de_la

	def _plafon(self):
		"""Components/HdsMotorPlafon: timpul maxim al nucleului cand plecarea antenei nu se stie (nu arunca)"""
		try:
			from Components import HdsMotorPlafon
		except Exception as e:
			if not getattr(self, "_plafon_lipsa", False):
				self._plafon_lipsa = True
				T.jurnal("plafonul motorului nu se poate incarca: %r" % (e,))
			return
		HdsMotorPlafon.aplica()

	def _tineMinte(self, slot, pereche, pe_slot, semnal):
		intrare = self.scris.get(str(slot)) or {}
		# perechile unui fisier strain sunt (-1, -1) in memorie (__init__), deci prima pereche cu semnal se scrie, cu
		# semnul nou, chiar daca e aceeasi ca in copie: altfel fiecare pornire ar trimite din nou comanda
		vechi = _pereche(intrare)
		if pereche[0] < 0 or pereche[1] < 0:
			nou = (-1, -1)
		elif pe_slot and semnal:
			nou = pereche
		elif pereche == vechi:
			return
		else:
			nou = (-1, -1)
		if nou == vechi and intrare:
			return
		self.scris[str(slot)] = {"orbital": nou[0], "cmd": nou[1], "amprenta": self._amprenta(slot)}
		self._scrie()

	# ------------------------------------------------------------------ plasa

	def _plasa(self, sec, slot, pereche, pe_slot, semnal):
		p = self.plasa.get(slot)
		if p is None:
			return
		try:
			miscare = sec.hdsRotorMovingSlot() == slot
		except Exception:
			miscare = False
		if miscare or pereche != p["pereche"]:
			# nucleul a trimis o comanda (sau pozitia a fost uitata): plasa nu mai are rost
			del self.plasa[slot]
			return
		if not pe_slot:
			# tunerul nu e al programului (standby, alt tuner, un ecran care l-a luat): numaratoarea incepe din nou
			p["vazut_la"] = None
			p["program"] = None
			return
		if semnal:
			del self.plasa[slot]
			T.jurnal("pozitia redata pe tunerul %s e confirmata de semnal" % T.numeTuner(slot))
			return
		program = self._programCurent()
		acum = T.acum()
		if p["vazut_la"] is None or (program != p["program"] and _orbitalProgram() != p["pereche"][0]):
			p["vazut_la"] = acum
			p["program"] = program
			p["zap_la"] = None
			return
		if program != p["program"]:
			# zap pe acelasi satelit: numaratoarea merge mai departe, programul nou are ZAP_PRINDERE_S sa prinda singur
			p["program"] = program
			p["zap_la"] = acum
		if acum - p["vazut_la"] < PLASA_S:
			return
		if p.get("zap_la") is not None and acum - p["zap_la"] < ZAP_PRINDERE_S:
			return
		del self.plasa[slot]
		if self._plasaLaVerificare(sec, slot):
			return
		T.jurnal("programul de pe tunerul %s e fara semnal de %d s cu pozitia redata: pozitia se uita, programul se "
			"opreste si porneste din nou peste %.1f s, ca nucleul sa trimita comanda de motor"
			% (T.numeTuner(slot), PLASA_S, ELIBERARE_CANAL_MS / 1000.0))
		sec.hdsForgetRotorPosition(slot)
		self._acordaDinNou(slot)

	def _plasaLaVerificare(self, sec, slot):
		"""pozitia redata la pornire, programul fara semnal: intai verificarea pe referinte. Prinsa = pozitia e buna si
		transponderul canalului nu emite (nicio comanda); altfel incercarea readucerii uita pozitia si porneste programul
		iar, deci comanda pleaca la fel ca din plasa. True daca a pornit verificarea."""
		e = self._readuceri.get(slot)
		if e is None or e["fel"] != "televizor" or e.get("verificare") is not None or e.get("ocolire") is not None:
			return False
		referinte, motiv = self._alegeVerificarea(sec, slot, e)
		if not referinte:
			T.jurnal("tunerul %s: pozitia redata fara semnal; plasa merge fara verificarea pe referinte: %s" % (
				T.numeTuner(slot), motiv))
			return False
		T.jurnal("programul de pe tunerul %s e fara semnal de %d s cu pozitia redata: intai verificarea pe alt transponder "
			"al satelitului, fara comanda de motor" % (T.numeTuner(slot), PLASA_S))
		self._pornesteVerificarea(sec, slot, e, T.acum(), referinte)
		return True

	def _programCurent(self):
		try:
			ref = T.programCurent()
		except Exception:
			return None
		# canalul de satelit inlocuit de internet ramane programul sirului (fara "alt program" la trecere)
		sat = _rezervaRefSatelit()
		if sat is not None:
			return sat
		return _textProgram(ref) if ref is not None else None

	# ------------------------------------------------------------------ plasa de sosire

	def _sosire(self, sec, slot, pe_slot, semnal):
		"""O mutare a nucleului terminata fara semnal se judeca o singura data, la SOSIRE_ASTEPTARE_MS de la oprire: daca
		programul tot nu are semnal, comanda se trimite inca o data (_reiaComanda). Mutarea pornita de reluare nu mai are
		reluare (fara bucle)."""
		try:
			if not sec.hdsRotorInfoValid(slot):
				return
			oprit_de = int(sec.hdsRotorStoppedMs(slot))
			if oprit_de < 0:
				return   # in mers, sau comanda notata si motorul inca nepornit
			trecut = int(sec.hdsRotorElapsedMs(slot))
			la = int(sec.hdsRotorToOrbital(slot))
			cmd = int(sec.hdsRotorCmd(slot))
			sosire = int(sec.hdsRotorArrived(slot))
		except (AttributeError, TypeError, ValueError):
			return
		try:
			de_la = int(sec.hdsRotorFromOrbital(slot))
		except (AttributeError, TypeError, ValueError):
			de_la = -1
		pornire = T.acum() * 1000.0 - max(0, trecut) - oprit_de
		vechi = self._judecate.get(slot)
		if vechi is not None and vechi[0] == la and vechi[1] == cmd and abs(vechi[2] - pornire) <= POTRIVIRE_MS:
			return   # judecata deja
		if sosire == 1 and oprit_de < SOSIRE_ASTEPTARE_MS:
			return   # semnalul mai poate veni (nucleul acordeaza din nou dupa oprire); se judeca mai tarziu
		self._judecate[slot] = (la, cmd, pornire)
		r = self._reluare
		a_reluarii = r is not None and r["slot"] == slot and r["la"] == la and r["pornita_la"] is not None and \
			r["pornita_la"] - POTRIVIRE_MS <= pornire <= r["pornita_la"] + RELUARE_VALABILA_MS
		if a_reluarii or (r is not None and r["slot"] == slot and r["pornita_la"] is not None and
				pornire > r["pornita_la"] + RELUARE_VALABILA_MS):
			# mutarea reluarii s-a terminat (sau a trecut de mult fara ea): reluarea s-a incheiat
			self._reluare = None
		if sosire != 1 or oprit_de > SOSIRE_VECHE_MS:
			return   # sosire cu semnal, o oprire care nu e sosire (zap in mers, standby, comenzile manuale) sau veche
		if self._aReaducerii(slot, la, pornire):
			return   # mutarea pornita de readucere: o judeca readucerea, cu pasii ei (fara oprirea programului)
		if pe_slot and semnal:
			return   # semnalul a venit dupa oprire
		if self._blocatDupa(slot, la, T.acum() - oprit_de / 1000.0 + SOSIRE_SEMNAL_MARJA_S):
			# blocarea a venit dupa oprire si s-a pierdut pana la judecata: antena a ajuns (transponder slab); o pierdere
			# mai lunga o judeca readucerea, cu READUCERE_S la rand
			T.jurnal("dupa mutarea spre %s semnalul a venit si s-a pierdut din nou: antena a ajuns, comanda nu se trimite "
				"din nou" % _gradeText(la))
			return
		if a_reluarii:
			T.jurnal("comanda trimisa din nou spre %s a ajuns tot fara semnal; nu se mai trimite" % _gradeText(la))
			return
		self._reiaComanda(sec, slot, la, pe_slot, de_la, pornire)

	def _reiaComanda(self, sec, slot, la, pe_slot, de_la=-1, pornire=0.0):
		nume = T.numeTuner(slot)
		if not pe_slot:
			return   # programul nu e pe acest tuner (standby, alt tuner, un ecran care l-a luat)
		if self._de_reluat is not None or self._reluare is not None:
			return   # o pauza e deja in curs
		if _orbitalProgram() != la:
			return   # programul de acum e pe alt satelit: zap-ul omului are intaietate
		if T.inregistrarePeAntena(slot):
			T.jurnal("fara semnal dupa mutarea spre %s, dar o inregistrare foloseste antena: comanda nu se trimite din "
				"nou" % _gradeText(la))
			return
		if T.tunerLaAltcineva() or _comenziMotorActive():
			T.jurnal("fara semnal dupa mutarea spre %s, dar tunerul e luat de alt ecran: comanda nu se trimite din nou"
				% _gradeText(la))
			return
		if self._verificaInainteDeReluare(sec, slot, la, de_la, pornire):
			return   # verificarea pe alt transponder al tintei hotaraste daca se mai trimite comanda
		self._pozitieReluare(sec, slot, la, de_la, pornire, "programul se opreste si porneste din nou peste %.1f s" % (
			ELIBERARE_CANAL_MS / 1000.0))
		self._reluare = {"slot": slot, "la": la, "pornita_la": None}
		if not self._acordaDinNou(slot):
			self._reluare = None

	def _pozitieReluare(self, sec, slot, la, de_la, pornire, cum):
		"""pozitia de dinaintea comenzii trimise din nou: plecarea, cand e dovedita de semnal (drumul stiut), altfel uitata
		(drumul cel mai lung); `cum` spune in jurnal cum porneste programul iar"""
		nume = T.numeTuner(slot)
		plecare = self._plecareDovedita(slot, de_la, la, pornire)
		pune = getattr(sec, "hdsRestoreRotorPosition", None)
		if plecare is not None and pune is not None:
			# antena era pe satelitul plecarii la pornirea mutarii (semnalul il arata) si n-a ajuns: e intre plecare si
			# tinta. Pozitia crezuta = plecarea, cu comanda -1 (nevalidata): nucleul trimite opririle si comanda, cu
			# drumul stiut (tinerea pe 18 V si timpul maxim pentru aceste grade), nu cu drumul cel mai lung
			T.jurnal("tunerul %s: mutarea spre %s s-a terminat fara semnal; antena era pe %s la pornire, deci pozitia se pune "
				"acolo, %s, ca nucleul sa trimita comanda de motor inca o data, cu drumul stiut" % (nume, _gradeText(la),
				_gradeText(plecare), cum))
			pune(slot, plecare, -1)
			# cu plecarea stiuta mutarea ar parea o masuratoare buna, dar antena putea fi deja pe drum: nu se invata
			try:
				from Components import HdsMotorViteza as V
				V.faraInvatare(slot, la)
			except Exception as ex:
				T.jurnal("reluarea nu s-a putut scoate din invatarea vitezei: %r" % (ex,))
		else:
			T.jurnal("tunerul %s: mutarea spre %s s-a terminat fara semnal; pozitia se uita, %s, ca nucleul sa trimita "
				"comanda de motor inca o data" % (nume, _gradeText(la), cum))
			sec.hdsForgetRotorPosition(slot)

	def _verificaInainteDeReluare(self, sec, slot, la, de_la, pornire):
		"""inaintea comenzii trimise din nou: verificarea pe alt transponder al tintei, fara comanda de motor. Prinsa =
		antena a ajuns, iar transponderul canalului nu emite: nicio comanda. Altfel comanda pleaca de la capatul
		verificarii (_reiaCuTunerul). True daca verificarea a pornit."""
		e = self._readuceri.get(slot)
		if e is None or e["sat"] != la or e.get("verificare") is not None or e.get("ocolire") is not None:
			return False
		referinte, motiv = self._alegeVerificarea(sec, slot, e)
		if not referinte:
			T.jurnal("tunerul %s: comanda spre %s se trimite din nou fara verificarea pe referinte: %s" % (
				T.numeTuner(slot), _gradeText(la), motiv))
			return False
		e["dupa_sosire"] = {"de_la": de_la, "pornire": pornire}
		self._pornesteVerificarea(sec, slot, e, T.acum(), referinte)
		return True

	def _reiaCuTunerul(self, sec, slot, e, acum, luare, ds):
		"""verificarea de dupa o mutare terminata fara semnal nu a prins nimic: comanda se trimite din nou, ca la plasa de
		sosire, cu tunerul luat de verificare: pozitia pusa, tunerul dat inapoi, programul pornit iar (mutarea lui e a
		reluarii, deci nu se mai reia)"""
		la = e["sat"]
		self._pozitieReluare(sec, slot, la, ds["de_la"], ds["pornire"], "programul porneste iar")
		ref = luare.uita_canalul() if luare is not None else None
		if luare is not None:
			luare.elibereaza(reda_canalul=False)
		if ref is None:
			return
		self._reluare = {"slot": slot, "la": la, "pornita_la": acum * 1000.0}
		_pornesteProgramul(ref)

	def _acordaDinNou(self, slot):
		"""programul se opreste acum si porneste abia dupa ELIBERARE_CANAL_MS, pe un canal nou, deci cu acord nou si cu
		comanda de motor (pornit imediat ar lua canalul pastrat de nucleu, fara acord). True daca s-a oprit."""
		nav = _navigatie()
		if nav is None:
			return False
		ref = nav.getCurrentlyPlayingServiceReference()
		if ref is None:
			return False
		if T.inregistrarePeAntena(slot):
			T.jurnal("o inregistrare foloseste antena: programul nu se opreste; comanda pleaca la urmatorul acord")
			return False
		if T.tunerLaAltcineva():
			T.jurnal("tunerul e luat de alt ecran: programul nu se opreste; comanda pleaca la urmatorul acord")
			return False
		nav.stopService()
		self._de_reluat = ref
		if self._t_reluare is None:
			self._t_reluare = T.cronometru(self._reiaSigur)
		self._t_reluare.start(ELIBERARE_CANAL_MS, True)
		return True

	# ------------------------------------------------------------------ readucerea

	def _aReaducerii(self, slot, la, pornire):
		"""True daca mutarea (tinta, pornirea in ms) e cea pornita de ultima incercare de readucere pe slot"""
		for tinta, ms in self._mutari_readucere.get(slot) or ():
			if tinta == la and ms - POTRIVIRE_MS <= pornire <= ms + RELUARE_VALABILA_MS:
				return True
		return False

	def _readucereSigur(self, sec, slot, pe_slot=None, semnal=False):
		if self._readucere_lipsa:
			return
		try:
			self._readucere(sec, slot, pe_slot, semnal)
			self._panouLaSfarsit(sec, slot)
		except Exception as e:
			# o greseala aici nu are voie sa lase panoul automat si mesajul de rotire ascunse pentru totdeauna, nici
			# tunerul luat de ocolire si programul oprit
			self._ocolireDeUrgenta(slot)
			self._panou_pana.pop(slot, None)
			_panouAscuns(False)
			T.jurnal("readucerea antenei: %r" % (e,))

	def _panouLaSfarsit(self, sec, slot):
		"""dupa readucere panoul automat ramane ascuns si cat ar arata el mutarea oprita (HdsMotorStare,
		MILISECUNDE_DUPA_SOSIRE); altfel ar aparea pe televizor "Antena a ajuns" dupa fiecare readucere"""
		if not self._panou_pana.get(slot):
			return
		try:
			if int(sec.hdsRotorMovingSlot()) == slot:
				return
			oprit_de = int(sec.hdsRotorStoppedMs(slot))
		except (AttributeError, TypeError, ValueError):
			oprit_de = -1
		if 0 <= oprit_de <= _dupaSosireMs() + READUCERE_PANOU_MARJA_MS:
			return
		del self._panou_pana[slot]
		_panouAscuns(False)

	def _readucere(self, sec, slot, pe_slot=None, semnal=False):
		acum = T.acum()
		e = self._readuceri.get(slot)
		if e is not None and e.get("ocolire") is not None:
			# programul e oprit de ocolire: tunerul e al nostru pana la intoarcere
			self._ocolireBate(sec, slot, e, acum)
			return
		if e is not None and e.get("verificare") is not None:
			# programul e oprit de verificarea pe referinte: tunerul e al nostru pana la capatul ei
			self._verificareBate(sec, slot, e, acum)
			return
		u = _utilizator(slot, pe_slot, semnal)
		if u is None:
			self._incheie(sec, slot, "tunerul nu mai e folosit de program sau de o inregistrare")
			return
		fel, semnal, orbital = u
		program = self._programCurent() if fel == "televizor" else None
		if e is not None and e["sat"] != orbital:
			self._incheie(sec, slot, "alt satelit")
			e = None
		elif e is not None and e.get("program") is not None and program is not None and program != e["program"]:
			if e.get("la_loc") is not None or e["revenit_la"] is not None:
				# zap pe acelasi satelit dupa ce verificarea a aratat antena la locul ei sau dupa ce semnalul a revenit: nu e
				# nicio readucere de amanat; sir nou pentru programul nou (zap-urile urmatoare il pastreaza)
				self._incheie(sec, slot, "alt program")
				e = None
			else:
				# zap pe acelasi satelit cat readucerea e deschisa: sirul ramane (pierderea se numara de la inceputul ei)
				self._zapAcelasiSatelit(slot, e, program, semnal, acum)
		if semnal:
			if e is not None:
				self._cuSemnal(sec, slot, e, acum)
			return
		if e is None:
			e = {"sat": orbital, "fel": fel, "pierdut_la": acum, "fara_de": None, "incercari": 0,
				"urmatoarea_la": None, "incercarea": None, "ultima_la": None, "revenit_la": None, "ultima": None,
				"esecuri": 0, "ocolire": None, "ocolire_refuz": None, "ocoliri": 0, "program": program,
				"dupa_zap": self._dupaZap(slot, orbital, program, acum), "verificare": None, "verificari": 0,
				"verificare_refuz": None, "la_loc": None, "la_loc_n": 0}
			self._readuceri[slot] = e
		e["fel"] = fel
		if e["revenit_la"] is not None:
			# semnalul adus a tinut mai putin de READUCERE_STABIL_S: pasii continua
			e["revenit_la"] = None
			e["pierdut_la"] = acum
			e["fara_de"] = None
		inc = e["incercarea"]
		if inc is not None and not inc["judecata"]:
			self._judeca(sec, slot, e, acum)
			return
		try:
			miscare = int(sec.hdsRotorMovingSlot()) == slot
			crezuta = int(sec.hdsKnownRotorPosition(slot))
		except (AttributeError, TypeError, ValueError):
			return
		if miscare or crezuta != orbital:
			# motorul merge (atunci asteptam oprirea), sau nucleul nu crede antena pe acest satelit (atunci acordul
			# urmator trimite oricum comanda): numaratoarea incepe din nou
			e["fara_de"] = None
			return
		motiv = self._opritaDe(slot, fel)
		if motiv:
			# numaratoarea incepe din nou dupa ce se termina ce a oprit-o (ecranul inchis, tunerul dat inapoi)
			if motiv != self._readucere_oprita:
				T.jurnal("tunerul %s fara semnal pe %s; readucerea asteapta: %s" % (T.numeTuner(slot), _gradeText(orbital),
					motiv))
			self._readucere_oprita = motiv
			e["fara_de"] = None
			return
		self._readucere_oprita = None
		if e["fara_de"] is None:
			e["fara_de"] = acum
			return
		if acum - e["fara_de"] < READUCERE_S:
			return
		if e["urmatoarea_la"] is not None and acum < e["urmatoarea_la"]:
			return
		if e.get("zap_la") is not None and acum - e["zap_la"] < ZAP_PRINDERE_S:
			return   # programul ales de om abia a acordat: are cateva secunde sa prinda singur
		self._incearca(sec, slot, e, acum)

	def _zapAcelasiSatelit(self, slot, e, program, semnal, acum):
		"""zap pe acelasi satelit cat readucerea e deschisa (antena nedovedita la locul ei, semnalul nerevenit): sirul
		ramane (numaratoarea, verificarile, incercarile, pasii si ocolirile), se schimba numai programul lui; programul nou
		are ZAP_PRINDERE_S sa prinda singur inainte ca o verificare sau o incercare sa-i ia tunerul"""
		e["program"] = program
		e["zap_la"] = acum
		inc = e["incercarea"]
		if inc is not None and not inc["judecata"]:
			# pozitia e uitata de incercare: acordul zap-ului trimite inca o data comanda spre aceeasi tinta; mutarea lui e
			# tot a readucerii (o judeca ea, nu plasa de sosire). Zap-ul a venit cel mult o bataie inainte
			self._mutari_readucere.setdefault(slot, []).append((e["sat"], acum * 1000.0 - BATAIE_MS))
		T.jurnal("tunerul %s: zap pe acelasi satelit (%s) cat lipseste semnalul; readucerea merge mai departe (pierdere "
			"de %d s, %s)" % (T.numeTuner(slot), _gradeText(e["sat"]), int(acum - e["pierdut_la"]),
			"cu semnal acum" if semnal else "programul are %d s sa prinda" % ZAP_PRINDERE_S))

	def _opritaDe(self, slot, fel):
		"""de ce nu se face acum readucerea, sau None"""
		if T.lacatProba():
			return "lacatul probei (fara comenzi de motor)"
		if _comenziMotorActive() or _stapanComenzi():
			return "comenzile motorului (ecranul sau pagina antenei)"
		if _alteEcraneAscund():
			return "un ecran al antenei (Rotirea antenei sau Gasire semnal)"
		if T.tunerLaAltcineva():
			return "tunerul e luat de alt ecran"
		if _rezervaProbaInCurs(slot):
			return "incercarea transponderului canalului, cat imaginea vine de pe internet"
		if _probaLnb():
			return "proba LNB-ului"
		ecran = _ecranAntena()
		if ecran:
			return "ecranul %s" % ecran
		if self._de_reluat is not None or self._reluare is not None:
			return "programul porneste din nou (plasa)"
		if fel == "televizor" and slot in self.plasa:
			return "plasa pozitiei redate la pornire"
		return None

	def _incearca(self, sec, slot, e, acum):
		if getattr(sec, "hdsReaduceAntena", None) is None:
			self._readucere_lipsa = True
			T.jurnal("nucleul nu are hdsReaduceAntena; antena nu se readuce dupa pierderea semnalului")
			return
		# inaintea oricarei mutari: verificarea pe alt transponder al aceluiasi satelit, fara comanda de motor
		referinte, motiv = self._alegeVerificarea(sec, slot, e)
		if referinte:
			e["verificare_refuz"] = None
			self._pornesteVerificarea(sec, slot, e, acum, referinte)
			return
		if motiv != e.get("verificare_refuz"):
			e["verificare_refuz"] = motiv
			T.jurnal("tunerul %s: fara semnal pe %s; readucerea merge fara verificarea pe referinte: %s" % (
				T.numeTuner(slot), _gradeText(e["sat"]), motiv))
		self._incercare(sec, slot, e, acum)

	def _incercare(self, sec, slot, e, acum, luare=None):
		"""o incercare de readucere (directa sau prin ocolire); `luare` = tunerul tinut de verificarea fara semnal"""
		readuce = getattr(sec, "hdsReaduceAntena", None)
		n = e["incercari"] + 1
		e["incercari"] = n
		e["ultima_la"] = acum
		# pasul pana la urmatoarea: dupa cate incercari la rand ar fi fara semnal, cu aceasta
		e["urmatoarea_la"] = acum + READUCERE_PASI_S[min(e["esecuri"] + 1, len(READUCERE_PASI_S)) - 1]
		e["fara_de"] = None
		fara_ms = int((acum - e["pierdut_la"]) * 1000)
		if e["esecuri"]:
			# incercarea de dinainte nu a adus semnalul: aceasta trece prin alta pozitie, daca se poate
			alegere, motiv = self._alegeOcolirea(sec, slot, e, cu_tunerul=luare is not None)
			if alegere is not None:
				e["ocolire_refuz"] = None
				self._pornesteOcolirea(sec, slot, e, acum, n, alegere, fara_ms, luare=luare)
				return
			if motiv != e["ocolire_refuz"]:
				e["ocolire_refuz"] = motiv
				T.jurnal("tunerul %s: incercarea %d spre %s merge direct, fara ocolire: %s" % (T.numeTuner(slot), n,
					_gradeText(e["sat"]), motiv))
		ref = None
		if luare is not None:
			# tunerul e al verificarii: se da inapoi; programul oprit de ea porneste iar cu pozitia uitata, deci acordul
			# lui trimite comanda spre satelit (ca intoarcerea din ocolire)
			ref = luare.uita_canalul()
			luare.elibereaza(reda_canalul=False)
		# cererea intra in randurile nucleului (pozitia uitata, opririle, comanda); apoi randul pornirii
		T.anuntaCererea(CERERE_READUCERE % n)
		self._rand(sec, slot, "pornita", n, e["sat"], fara_ms=fara_ms)
		if ref is not None:
			sec.hdsForgetRotorPosition(slot)
			e["incercarea"] = {"la": acum, "n": n, "judecata": False, "semnal_la": None, "prin": None}
			self._mutari_readucere[slot] = [(e["sat"], acum * 1000.0)]
			self._panou_pana.pop(slot, None)
			_panouAscuns(True)
			T.jurnal("tunerul %s: fara semnal de %d s pe %s, iar verificarea nu a prins nimic: pozitia se uita si programul "
				"porneste iar (incercarea %d), ca nucleul sa trimita comanda de motor" % (T.numeTuner(slot),
				fara_ms // 1000, _gradeText(e["sat"]), n))
			_pornesteProgramul(ref)
			return
		try:
			cod = int(readuce(slot, e["sat"]))
		except Exception as ex:
			T.jurnal("readucerea antenei a dat eroare: %r" % (ex,))
			cod = -9
		urmatoarea = int(round(e["urmatoarea_la"] - acum))
		if cod != 1:
			e["ultima"] = {"faza": "refuzata", "cod": cod}
			self._rand(sec, slot, "refuzata", n, e["sat"], fara_ms=fara_ms, urmatoarea_s=urmatoarea, cod=cod)
			T.jurnal("tunerul %s: readucerea spre %s nu a pornit (cod %d); urmatoarea incercare peste %d s" % (
				T.numeTuner(slot), _gradeText(e["sat"]), cod, urmatoarea))
			return
		e["incercarea"] = {"la": acum, "n": n, "judecata": False, "semnal_la": None, "prin": None}
		self._mutari_readucere[slot] = [(e["sat"], acum * 1000.0)]
		self._panou_pana.pop(slot, None)
		_panouAscuns(True)
		T.jurnal("tunerul %s: fara semnal de %d s pe %s, cu antena crezuta acolo: pozitia se uita si tunerul se acordeaza "
			"din nou pe acelasi canal (incercarea %d), ca nucleul sa trimita comanda de motor" % (T.numeTuner(slot),
			fara_ms // 1000, _gradeText(e["sat"]), n))

	def _mutarea(self, sec, slot, e):
		"""(oprit_de_ms, mers_ms, sosire) pentru mutarea pornita de ultima incercare (oprit_de_ms = -1 cat merge), sau None
		cat nucleul nu arata una (tinta = satelitul sirului, pornita dupa incercare)"""
		inc = e["incercarea"]
		if inc is None:
			return None
		try:
			if not sec.hdsRotorInfoValid(slot):
				return None
			trecut = int(sec.hdsRotorElapsedMs(slot))
			oprit_de = int(sec.hdsRotorStoppedMs(slot))
			la = int(sec.hdsRotorToOrbital(slot))
			sosire = int(sec.hdsRotorArrived(slot))
		except (AttributeError, TypeError, ValueError):
			return None
		if trecut < 0 or la != e["sat"]:
			return None
		pornire = T.acum() * 1000.0 - trecut - max(0, oprit_de)
		if pornire < inc["la"] * 1000.0 - POTRIVIRE_MS:
			return None
		return oprit_de, trecut, sosire

	def _judeca(self, sec, slot, e, acum):
		"""incercarea fara semnal: se judeca cel mai devreme la READUCERE_JUDECATA_MIN_S de la pornire, dupa oprirea
		motorului si SOSIRE_ASTEPTARE_MS (nucleul mai acordeaza o data dupa oprire), sau dupa READUCERE_JUDECATA_MAX_S
		daca nucleul nu arata nicio oprire"""
		inc = e["incercarea"]
		if acum - inc["la"] < READUCERE_JUDECATA_MIN_S:
			return
		m = self._mutarea(sec, slot, e)
		if acum - inc["la"] < READUCERE_JUDECATA_MAX_S:
			if m is None or m[0] < 0 or m[0] < SOSIRE_ASTEPTARE_MS:
				return
		inc["judecata"] = True
		e["esecuri"] += 1
		self._panou_pana[slot] = True
		# fara semnal de la incercare: urmatoarea vine la pasul ei, fara inca READUCERE_S de numarat
		e["fara_de"] = acum - READUCERE_S
		dupa_ms = int((acum - inc["la"]) * 1000)
		mers_ms = m[1] if m is not None and m[0] >= 0 else -1
		urmatoarea = max(0, int(round(e["urmatoarea_la"] - acum)))
		e["ultima"] = {"faza": "fara_semnal", "dupa_ms": dupa_ms, "mers_ms": mers_ms, "prin": inc.get("prin")}
		self._rand(sec, slot, "fara_semnal", inc["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=dupa_ms, mers_ms=mers_ms, urmatoarea_s=urmatoarea)
		T.jurnal("tunerul %s: tot fara semnal dupa readucerea spre %s (incercarea %d); urmatoarea peste %d s" % (
			T.numeTuner(slot), _gradeText(e["sat"]), inc["n"], urmatoarea))

	def _cuSemnal(self, sec, slot, e, acum):
		e["fara_de"] = None
		inc = e["incercarea"]
		if e.get("la_loc") is not None and (inc is None or inc["judecata"]):
			# antena era la locul ei (verificarea), iar transponderul canalului emite iar
			del self._readuceri[slot]
			T.jurnal("tunerul %s: semnalul a revenit pe %s fara nicio rotire (transponderul canalului emite iar)" % (
				T.numeTuner(slot), _gradeText(e["sat"])))
			return
		if inc is not None and not inc["judecata"]:
			if inc["semnal_la"] is None:
				inc["semnal_la"] = acum
			m = self._mutarea(sec, slot, e)
			if m is not None and m[0] < 0 and acum - inc["semnal_la"] < READUCERE_OPRIRE_MAX_S:
				return   # motorul se opreste la semnal (sec.cpp, IF_TUNER_LOCKED_GOTO): randul asteapta cat a mers
			inc["judecata"] = True
			self._panou_pana[slot] = True
			dupa_ms = int((inc["semnal_la"] - inc["la"]) * 1000)
			mers_ms = m[1] if m is not None and m[0] >= 0 else -1
			self._revenit(sec, slot, e, acum, inc["n"], dupa_ms, mers_ms)
			return
		if e["revenit_la"] is None:
			if not e["incercari"]:
				del self._readuceri[slot]   # semnalul a venit singur, fara nicio incercare
				return
			# semnalul a venit dupa o incercare judecata fara semnal (mai tarziu, sau adus de om)
			self._revenit(sec, slot, e, acum, e["incercari"], int((acum - e["ultima_la"]) * 1000), -1)
			return
		if acum - e["revenit_la"] >= READUCERE_STABIL_S:
			del self._readuceri[slot]   # semnalul a tinut: pierderea urmatoare incepe iar de la READUCERE_S

	def _revenit(self, sec, slot, e, acum, n, dupa_ms, mers_ms):
		e["revenit_la"] = acum
		e["incercarea"] = None
		# semnalul a venit: urmatoarea pierdere (si o revenire scurta) incepe iar cu incercari directe si pasi scurti
		e["esecuri"] = 0
		e["ocoliri"] = 0
		e["ultima"] = {"faza": "semnal_revenit", "dupa_ms": dupa_ms, "mers_ms": mers_ms}
		self._rand(sec, slot, "semnal_revenit", n, e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=dupa_ms, mers_ms=mers_ms)
		T.jurnal("tunerul %s: semnalul a revenit pe %s dupa readucere (incercarea %d, la %.1f s; motorul a mers %s)" % (
			T.numeTuner(slot), _gradeText(e["sat"]), n, dupa_ms / 1000.0,
			"%.1f s" % (mers_ms / 1000.0) if mers_ms >= 0 else "?"))

	def _incheie(self, sec, slot, motiv):
		self._ocolireDeUrgenta(slot)
		e = self._readuceri.pop(slot, None)
		if e is None:
			return
		inc = e["incercarea"]
		# zap-ul pe alt satelit sau standby-ul: o mutare a omului se vede pe loc, ca pana acum
		if self._panou_pana.pop(slot, None) or (inc is not None and not inc["judecata"]):
			_panouAscuns(False)
		if e["incercari"] and e["revenit_la"] is None:
			self._rand(sec, slot, "incheiata", e["incercari"], e["sat"],
				fara_ms=int((T.acum() - e["pierdut_la"]) * 1000))
			T.jurnal("tunerul %s: readucerea spre %s s-a incheiat fara semnal: %s" % (T.numeTuner(slot),
				_gradeText(e["sat"]), motiv))

	def _rand(self, sec, slot, faza, n, orbital, fara_ms=-1, dupa_ms=-1, mers_ms=-1, urmatoarea_s=-1, cod=0):
		"""randul "readucere" din urma motorului (lib/dvb/hdsurmamotor.cpp); pe o imagine fara el, nimic"""
		scrie_rand = getattr(sec, "hdsMotorReaducere", None)
		if scrie_rand is None:
			return
		try:
			scrie_rand(int(slot), str(faza), int(n), int(orbital), int(fara_ms), int(dupa_ms), int(mers_ms),
				int(urmatoarea_s), int(cod))
		except Exception as ex:
			T.jurnal("randul readucerii nu s-a scris: %r" % (ex,))

	def stareReaducere(self):
		"""readucerea de acum, numai numere (pagina web a antenei si /api/motor); activa = cel putin o incercare"""
		acum = T.acum()
		for slot in sorted(self._readuceri):
			e = self._readuceri[slot]
			if not e["incercari"] and not e.get("verificari"):
				continue
			inc = e["incercarea"]
			o = e.get("ocolire")
			in_curs = o is not None or (inc is not None and not inc["judecata"])
			asteapta = e["revenit_la"] is None and e["urmatoarea_la"] is not None
			# ocolirea incercarii de acum: drumul spre ea ("luare", "spre") sau intoarcerea pe satelitul canalului
			ocolire = None
			if o is not None:
				ocolire = {"prin": o["prin"], "faza": o["faza"], "secunde": int(acum - o["pornita_la"])}
			elif inc is not None and not inc["judecata"] and inc.get("prin") is not None:
				ocolire = {"prin": inc["prin"], "faza": "inapoi", "secunde": int(acum - inc["la"])}
			if ocolire is not None:
				text = _gradeTextWeb(ocolire["prin"])
				if text:
					ocolire["prin_text"] = text
			# verificarea pe referinte in curs (transponderul incercat acum) si antena gasita la locul ei
			verificare = None
			v = e.get("verificare")
			if v is not None:
				tp = v["refs"][min(v["i"], len(v["refs"]) - 1)] if v["refs"] else None
				verificare = {"n": v["n"], "faza": v["faza"], "tp_text": _tpText(tp) if tp else "",
					"referinta": min(v["i"], len(v["refs"]) - 1) + 1, "referinte": len(v["refs"]),
					"secunde": int(acum - v["pornita_la"])}
			l = e.get("la_loc")
			la_loc = {"tp_text": l["tp_text"], "secunde": int(acum - l["la"])} if l is not None else None
			return {"activa": True, "slot": slot, "sat": e["sat"], "fel": e["fel"], "incercari": e["incercari"],
				"in_curs": in_curs, "semnal_revenit": e["revenit_la"] is not None,
				"fara_semnal_s": int(acum - e["pierdut_la"]) if e["revenit_la"] is None else 0,
				"urmatoarea_s": max(0, int(round(e["urmatoarea_la"] - acum))) if asteapta else None,
				"ultima": dict(e["ultima"]) if e["ultima"] else None, "esecuri": e.get("esecuri", 0), "ocolire": ocolire,
				"verificari": e.get("verificari", 0), "verificare": verificare, "la_loc": la_loc}
		return {"activa": False}

	# ------------------------------------------------------------------ ocolirea

	def _alegeOcolirea(self, sec, slot, e, cu_tunerul=False):
		"""((orbital, transponder, secunde), "") pentru ocolire, sau (None, motiv): numai pentru programul de pe
		televizor, cu nimic altceva pe tuner, cu nucleul care are functiile si cu un alt satelit potrivit.
		`cu_tunerul`: tunerul e deja luat de verificare (programul e oprit de noi)."""
		if e.get("dupa_zap"):
			return None, ("pierderea a inceput la un zap de pe un canal cu semnal pe acelasi satelit, fara mutarea "
				"antenei: fara ocolire")
		if e["ocoliri"] >= OCOLIRE_MAX:
			return None, "ocolirea s-a facut deja de la plecarea antenei (cel mult %d pe o plecare)" % OCOLIRE_MAX
		if e["fel"] != "televizor":
			return None, "tunerul e al unei inregistrari (ocolirea ar opri-o)"
		if T.ecranStandby() is not None:
			return None, "standby"
		if T.inregistrarePeAntena(slot):
			return None, "o inregistrare foloseste antena"
		secunde = T.secundePanaLaInregistrare()
		if secunde is not None and secunde <= OCOLIRE_INREGISTRARE_S:
			return None, "o inregistrare porneste peste %d s" % max(0, int(secunde))
		if _transmisieInRetea():
			return None, "o transmisie in retea foloseste tunerul"
		for nume in ("hdsForgetRotorPosition", "hdsRotorMovingSlot", "hdsRotorArrived"):
			if not hasattr(sec, nume):
				return None, "nucleul nu are %s" % nume
		try:
			_gasire()
		except Exception as ex:
			return None, "luarea tunerului nu se poate incarca (%r)" % (ex,)
		if not cu_tunerul:
			try:
				if T.programCurent() is None:
					return None, "niciun program pe televizor"
			except Exception:
				return None, "programul de pe televizor nu se poate citi"
		alegere = _satelitOcolire(slot, e["sat"])
		if alegere is None:
			return None, ("niciun alt satelit al tunerului, deasupra orizontului, la cel putin %.0f grade de motor si cu "
				"transpondere" % OCOLIRE_MIN_GRADE)
		orbital, tp = alegere
		return (orbital, tp, (_drumMaximS(slot, orbital) or OCOLIRE_DRUM_IMPLICIT_S) + OCOLIRE_PRINDERE_S), ""

	def _pornesteOcolirea(self, sec, slot, e, acum, n, alegere, fara_ms, luare=None):
		orbital, tp, max_s = alegere
		o = {"n": n, "prin": orbital, "tp": tp, "max_s": float(max_s), "faza": "luare", "pornita_la": acum, "la": acum,
			"vazut": False, "luare": None}
		e["ocolire"] = o
		e["ocoliri"] += 1
		e["incercarea"] = None
		self._mutari_readucere[slot] = []
		self._panou_pana.pop(slot, None)
		_panouAscuns(True)
		T.anuntaCererea(CERERE_OCOLIRE % (n, _gradeText(orbital)))
		self._rand(sec, slot, "ocolire", n, e["sat"], fara_ms=fara_ms)
		T.jurnal("tunerul %s: fara semnal de %d s pe %s, incercarea de dinainte fara semnal: incercarea %d trece prin %s "
			"(programul se opreste, tunerul se acordeaza acolo cu pozitia uitata, cel mult %d s, apoi programul porneste "
			"iar)" % (T.numeTuner(slot), fara_ms // 1000, _gradeText(e["sat"]), n, _gradeText(orbital), int(max_s)))
		if luare is not None:
			# tunerul vine de la verificarea fara semnal (programul e deja oprit): acordul ocolirii pe loc
			luare.la_cedare = lambda motiv, s=slot: self._ocolireSigur(s, lambda: self._ocolireCedata(s, motiv))
			o["luare"] = luare
			sec.hdsForgetRotorPosition(slot)
			self._ocolireLuata(slot, True, "")
			return
		luare = _gasire().LuareTuner(NUME_OCOLIRE,
			la_cedare=lambda motiv, s=slot: self._ocolireSigur(s, lambda: self._ocolireCedata(s, motiv)))
		o["luare"] = luare
		# pozitia uitata inainte de luare: daca tunerul nu vine, programul pus la loc trimite oricum comanda spre satelit
		sec.hdsForgetRotorPosition(slot)
		luare.ia(slot, lambda ok, motiv, s=slot: self._ocolireSigur(s, lambda: self._ocolireLuata(s, ok, motiv)),
			T.sesiuneInfoBar())

	def _ocolireSigur(self, slot, functie):
		try:
			functie()
		except Exception as ex:
			T.jurnal("ocolirea antenei: %r" % (ex,))
			self._ocolireDeUrgenta(slot)

	def _ocolireLuata(self, slot, ok, motiv):
		e = self._readuceri.get(slot)
		o = e.get("ocolire") if e is not None else None
		if o is None or o["faza"] != "luare":
			return
		sec = T.controlSec()
		acum = T.acum()
		if not ok:
			# LuareTuner a pus programul la loc; cu pozitia uitata, acordul lui trimite comanda spre satelitul canalului
			self._ocolireRefuzata(sec, slot, e, acum, OCOLIRE_COD_TUNER, "tunerul nu s-a putut lua (%s)" % motiv, True)
			return
		sec.hdsForgetRotorPosition(slot)
		T.anuntaCererea(CERERE_OCOLIRE % (o["n"], _gradeText(o["prin"])))
		try:
			cod = int(_gasire().acordeaza(o["luare"].frontend, o["tp"]))
		except Exception as ex:
			T.jurnal("acordul ocolirii a dat eroare: %r" % (ex,))
			cod = -1
		if cod != 0:
			self._ocolireRefuzata(sec, slot, e, acum, OCOLIRE_COD_ACORD, "nucleul a refuzat acordul (cod %d)" % cod, False)
			return
		o["faza"] = "spre"
		o["la"] = acum
		self._mutari_readucere.setdefault(slot, []).append((o["prin"], acum * 1000.0))

	def _ocolireBate(self, sec, slot, e, acum):
		"""la fiecare bataie cat programul e oprit de ocolire: oprirea ceruta de altceva, apoi capatul drumului spre
		ocolire (semnalul acolo, mutarea oprita in nucleu sau drumul cel mai lung trecut)"""
		o = e["ocolire"]
		motiv = _ocolireOpritaDe(slot)
		if motiv:
			self._ocolireOprita(sec, slot, e, acum, motiv)
			return
		if o["faza"] == "luare":
			if acum - o["la"] > OCOLIRE_LUARE_MAX_S:
				self._ocolireOprita(sec, slot, e, acum, "tunerul nu a venit in %d s" % OCOLIRE_LUARE_MAX_S)
			return
		try:
			misca = int(sec.hdsRotorMovingSlot()) == slot
		except (AttributeError, TypeError, ValueError):
			misca = False
		if misca:
			o["vazut"] = True
		blocat, stare = _stareFrontend(o["luare"].frontend)
		trecut = acum - o["la"]
		if blocat and not misca:
			gata = True
		elif o["vazut"] and not misca:
			gata = _sosireCuSemnal(sec, slot)
		elif not o["vazut"] and trecut >= OCOLIRE_PORNIRE_S and stare != "TUNING":
			gata = False
		elif trecut >= o["max_s"]:
			gata = False
		else:
			return
		self._ocolireInapoi(sec, slot, e, acum, gata)

	def _ocolireInapoi(self, sec, slot, e, acum, semnal):
		o = e["ocolire"]
		dupa_ms = int((acum - o["pornita_la"]) * 1000)
		mers_ms = _mersSpre(sec, slot, o["prin"], o["la"])
		faza = "ocolire_semnal" if semnal else "ocolire_fara_semnal"
		e["ultima"] = {"faza": faza, "prin": o["prin"], "dupa_ms": dupa_ms, "mers_ms": mers_ms}
		# randul spune si pozitia ocolirii (cererea de la pornire a expirat intre timp)
		T.anuntaCererea(CERERE_OCOLIRE % (o["n"], _gradeText(o["prin"])))
		self._rand(sec, slot, faza, o["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000), dupa_ms=dupa_ms,
			mers_ms=mers_ms)
		T.jurnal("tunerul %s: ocolirea prin %s %s dupa %.1f s; acum inapoi spre %s, cu pozitia uitata (incercarea %d)" % (
			T.numeTuner(slot), _gradeText(o["prin"]), "a prins semnal" if semnal else "fara semnal", dupa_ms / 1000.0,
			_gradeText(e["sat"]), o["n"]))
		self._inapoi(sec, slot, e, acum, o, o["prin"])

	def _inapoi(self, sec, slot, e, acum, o, prin):
		"""tunerul dat inapoi si programul pornit iar cu pozitia uitata: comanda spre satelitul canalului pleaca la
		acordul lui, cu 18 V cat drumul cel mai lung; incercarea se judeca de aici ca una directa"""
		e["ocolire"] = None
		luare = o["luare"]
		ref = luare.uita_canalul() if luare is not None else None
		if luare is not None:
			luare.elibereaza(reda_canalul=False)
		sec.hdsForgetRotorPosition(slot)
		T.anuntaCererea(CERERE_INAPOI % (o["n"], _gradeText(e["sat"])) if prin is not None else CERERE_READUCERE % o["n"])
		e["incercarea"] = {"la": acum, "n": o["n"], "judecata": False, "semnal_la": None, "prin": prin}
		self._mutari_readucere.setdefault(slot, []).append((e["sat"], acum * 1000.0))
		if ref is not None:
			_pornesteProgramul(ref)

	def _ocolireRefuzata(self, sec, slot, e, acum, cod, motiv, program_pus):
		o = e["ocolire"]
		self._rand(sec, slot, "ocolire_refuzata", o["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=int((acum - o["pornita_la"]) * 1000), cod=cod)
		e["ultima"] = {"faza": "ocolire_refuzata", "prin": o["prin"], "cod": cod}
		T.jurnal("tunerul %s: ocolirea prin %s nu a pornit: %s; incercarea %d merge direct spre %s" % (T.numeTuner(slot),
			_gradeText(o["prin"]), motiv, o["n"], _gradeText(e["sat"])))
		if program_pus:
			# programul a pornit deja (LuareTuner), cu pozitia uitata: mutarea lui e a incercarii
			e["ocolire"] = None
			e["incercarea"] = {"la": acum, "n": o["n"], "judecata": False, "semnal_la": None, "prin": None}
			self._mutari_readucere.setdefault(slot, []).append((e["sat"], acum * 1000.0))
			return
		self._inapoi(sec, slot, e, acum, o, None)

	def _ocolireOprita(self, sec, slot, e, acum, motiv):
		"""altceva are intaietate: zap-ul omului (programul lui porneste), standby-ul (programul il primeste ecranul
		Standby), altfel programul porneste iar, cu pozitia uitata (incercarea merge direct)"""
		o = e["ocolire"]
		T.anuntaCererea(CERERE_OCOLIRE_OPRITA % (o["n"], motiv))
		self._rand(sec, slot, "ocolire_oprita", o["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=int((acum - o["pornita_la"]) * 1000))
		e["ultima"] = {"faza": "ocolire_oprita", "prin": o["prin"]}
		T.jurnal("tunerul %s: ocolirea prin %s s-a oprit: %s" % (T.numeTuner(slot), _gradeText(o["prin"]), motiv))
		luare = o["luare"]
		if motiv == MOTIV_ZAP:
			# zap-ul omului castiga: programul lui (care nu a putut acorda cat tineam tunerul) porneste acum
			acelasi = _orbitalProgram() == e["sat"]
			e["ocolire"] = None
			if luare is not None:
				luare.elibereaza(reda_canalul=True)
			if acelasi:
				# zap pe satelitul canalului: acordul lui, cu pozitia uitata de ocolire, trimite comanda inapoi spre
				# satelit, adica intoarcerea ocolirii. Incercarea se judeca de aici ca una directa (ca _inapoi), deci
				# pasii raman; mutarea zap-ului (pornita cel mult o bataie inainte) nu o mai judeca plasa de sosire
				e["incercarea"] = {"la": acum, "n": o["n"], "judecata": False, "semnal_la": None, "prin": o["prin"]}
				self._mutari_readucere.setdefault(slot, []).append((e["sat"], acum * 1000.0 - BATAIE_MS))
				return
			self._panou_pana.pop(slot, None)
			_panouAscuns(False)
			return
		if motiv == MOTIV_STANDBY:
			e["ocolire"] = None
			ref = luare.uita_canalul() if luare is not None else None
			if luare is not None:
				luare.elibereaza(reda_canalul=False)
			if ref is not None:
				_daStandbyului(T.ecranStandby(), ref)
			self._panou_pana.pop(slot, None)
			_panouAscuns(False)
			return
		self._inapoi(sec, slot, e, acum, o, None)

	def _ocolireCedata(self, slot, motiv):
		"""chemata SINCRON prin LuareTuner.cedeaza cand coordonatorul da tunerul unei extensii: tunerul e deja dat;
		programul oprit de noi porneste cand tunerul se elibereaza (_datoratBate)"""
		e = self._readuceri.get(slot)
		o = e.get("ocolire") if e is not None else None
		if o is None:
			return
		e["ocolire"] = None
		sec = T.controlSec()
		acum = T.acum()
		T.anuntaCererea(CERERE_OCOLIRE_OPRITA % (o["n"], "tunerul cerut de alta functie"))
		self._rand(sec, slot, "ocolire_oprita", o["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=int((acum - o["pornita_la"]) * 1000))
		e["ultima"] = {"faza": "ocolire_oprita", "prin": o["prin"]}
		T.jurnal("tunerul %s: ocolirea prin %s s-a oprit: %s; programul porneste cand tunerul se elibereaza" % (
			T.numeTuner(slot), _gradeText(o["prin"]), motiv))
		luare = o["luare"]
		ref = luare.uita_canalul() if luare is not None else None
		if ref is not None:
			self._datorat = ref
		self._panou_pana.pop(slot, None)
		_panouAscuns(False)

	def _ocolireDeUrgenta(self, slot):
		"""o greseala sau incheierea readucerii cu ocolirea (sau verificarea) in curs: tunerul dat inapoi si programul
		pornit (fara rand)"""
		e = self._readuceri.get(slot)
		v = e.get("verificare") if e is not None else None
		if v is not None:
			e["verificare"] = None
			e.pop("dupa_sosire", None)
			try:
				luare = v.get("luare")
				ref = luare.uita_canalul() if luare is not None else None
				if luare is not None:
					luare.elibereaza(reda_canalul=False)
				standby = T.ecranStandby()
				if ref is not None and standby is not None:
					_daStandbyului(standby, ref)
				elif ref is not None and T.programCurent() is None:
					_pornesteProgramul(ref)
			except Exception as ex:
				T.jurnal("verificarea nu a putut da tunerul inapoi: %r" % (ex,))
		o = e.get("ocolire") if e is not None else None
		if o is None:
			return
		e["ocolire"] = None
		try:
			luare = o.get("luare")
			ref = luare.uita_canalul() if luare is not None else None
			if luare is not None:
				luare.elibereaza(reda_canalul=False)
			standby = T.ecranStandby()
			if ref is not None and standby is not None:
				_daStandbyului(standby, ref)
			elif ref is not None and T.programCurent() is None:
				_pornesteProgramul(ref)
			elif standby is None and T.programCurent() is not None:
				# programul n-a fost oprit, dar pozitia a fost uitata: fara un acord nou nimic nu mai trimite comanda
				sec = T.controlSec()
				if sec is not None and int(sec.hdsKnownRotorPosition(slot)) < 0:
					sec.hdsReaduceAntena(slot, e["sat"])
		except Exception as ex:
			T.jurnal("ocolirea nu a putut da tunerul inapoi: %r" % (ex,))

	# ------------------------------------------------------------------ verificarea pe referinte

	def _alegeVerificarea(self, sec, slot, e):
		"""([transpondere], "") pentru verificare, sau (None, motiv): numai pentru programul de pe televizor, cu nimic
		altceva pe tuner (o inregistrare nu se opreste niciodata pentru verificare) si cu cel putin o referinta"""
		if e["fel"] != "televizor":
			return None, "tunerul e al unei inregistrari (verificarea ar opri-o)"
		if T.ecranStandby() is not None:
			return None, "standby"
		if T.inregistrarePeAntena(slot):
			return None, "o inregistrare foloseste antena"
		secunde = T.secundePanaLaInregistrare()
		if secunde is not None and secunde <= OCOLIRE_INREGISTRARE_S:
			return None, "o inregistrare porneste peste %d s" % max(0, int(secunde))
		if _transmisieInRetea():
			return None, "o transmisie in retea foloseste tunerul"
		try:
			_gasire()
		except Exception as ex:
			return None, "luarea tunerului nu se poate incarca (%r)" % (ex,)
		try:
			if T.programCurent() is None:
				return None, "niciun program pe televizor"
		except Exception:
			return None, "programul de pe televizor nu se poate citi"
		tp_canal, _semnal = T.programPeTuner(slot)
		referinte = self._referinte(slot, e["sat"], tp_canal)
		if not referinte:
			return None, "niciun alt transponder al satelitului de incercat"
		return referinte, ""

	def _pornesteVerificarea(self, sec, slot, e, acum, referinte):
		e["verificari"] = e.get("verificari", 0) + 1
		e["fara_de"] = None
		v = {"n": e["verificari"], "refs": list(referinte), "i": 0, "faza": "luare", "pornita_la": acum, "la": acum,
			"prinderi": 0, "refuzate": 0, "luare": None}
		e["verificare"] = v
		T.jurnal("tunerul %s: fara semnal de %d s pe %s: inaintea oricarei mutari, verificarea %d pe %s (alt transponder al "
			"aceluiasi satelit, fara comanda de motor; programul se opreste cat tine)" % (T.numeTuner(slot),
			int(acum - e["pierdut_la"]), _gradeText(e["sat"]), v["n"], ", ".join(_tpScurt(tp) for tp in v["refs"])))
		luare = _gasire().LuareTuner(NUME_OCOLIRE,
			la_cedare=lambda motiv, s=slot: self._ocolireSigur(s, lambda: self._verificareCedata(s, motiv)))
		v["luare"] = luare
		luare.ia(slot, lambda ok, motiv, s=slot: self._ocolireSigur(s, lambda: self._verificareLuata(s, ok, motiv)),
			T.sesiuneInfoBar())

	def _verificareLuata(self, slot, ok, motiv):
		e = self._readuceri.get(slot)
		v = e.get("verificare") if e is not None else None
		if v is None or v["faza"] != "luare":
			return
		sec = T.controlSec()
		acum = T.acum()
		if not ok:
			# LuareTuner a pus programul la loc: readucerea merge ca inainte
			self._verificareRefuzata(sec, slot, e, acum, OCOLIRE_COD_TUNER, "tunerul nu s-a putut lua (%s)" % motiv, True)
			return
		self._verificareAcord(sec, slot, e, v, acum)

	def _verificareAcord(self, sec, slot, e, v, acum):
		"""acordul fara comanda de motor pe referinta v["i"] (sau pe urmatoarea, daca nucleul o refuza)"""
		for i in range(v["i"], len(v["refs"])):
			v["i"] = i
			tp = v["refs"][i]
			T.anuntaCererea(CERERE_VERIFICARE % (v["n"], i + 1, len(v["refs"]), _tpText(tp)))
			self._rand(sec, slot, "verificare", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
				dupa_ms=int((acum - v["pornita_la"]) * 1000))
			cod = T.acordFaraMotor(v["luare"].frontend, tp)
			if cod == 0:
				v["faza"] = "acord"
				v["la"] = acum
				v["prinderi"] = 0
				return
			T.jurnal("tunerul %s: verificarea pe %s: nucleul a refuzat acordul (cod %d)" % (T.numeTuner(slot),
				_tpScurt(tp), cod))
			v["refuzate"] += 1
		v["i"] = len(v["refs"]) - 1
		if v["refuzate"] >= len(v["refs"]):
			self._verificareRefuzata(sec, slot, e, acum, OCOLIRE_COD_ACORD, "nucleul a refuzat acordul", False)
			return
		self._verificareFaraSemnal(sec, slot, e, acum)

	def _verificareBate(self, sec, slot, e, acum):
		"""la fiecare bataie cat tine verificarea: oprirea ceruta de altceva, apoi prinderea pe referinta de acum"""
		v = e["verificare"]
		motiv = _ocolireOpritaDe(slot)
		if motiv == MOTIV_ZAP and self._zapInVerificare(sec, slot, e, acum):
			motiv = _ocolireOpritaDe(slot)
		if motiv:
			self._verificareOprita(sec, slot, e, acum, motiv)
			return
		if v["faza"] == "luare":
			if acum - v["la"] > OCOLIRE_LUARE_MAX_S:
				self._verificareOprita(sec, slot, e, acum, "tunerul nu a venit in %d s" % OCOLIRE_LUARE_MAX_S)
			return
		blocat, stare = _stareFrontend(v["luare"].frontend)
		if blocat and stare != "TUNING":
			v["prinderi"] += 1
			if v["prinderi"] >= VERIFICARE_PRINDERI:
				self._verificarePrinsa(sec, slot, e, acum)
			return
		v["prinderi"] = 0
		if acum - v["la"] < _asteptarePrindere(v["refs"][v["i"]]):
			return
		v["i"] += 1
		if v["i"] < len(v["refs"]):
			self._verificareAcord(sec, slot, e, v, acum)
			return
		self._verificareFaraSemnal(sec, slot, e, acum)

	def _zapInVerificare(self, sec, slot, e, acum):
		"""zap-ul omului cat verificarea tine tunerul. Pe acelasi satelit, cu programul cerut fara tuner (nu a putut acorda
		cat tunerul e al verificarii), verificarea merge mai departe: programul cerut se opreste si porneste el la capatul
		ei, in locul celui oprit de verificare (LuareTuner.preia_canalul_cerut). True daca zap-ul a fost preluat; altfel
		(alt satelit, alt tuner, tunerul inca neluat, nu se poate citi) zap-ul castiga, ca inainte."""
		v = e["verificare"]
		luare = v.get("luare")
		if luare is None or not luare.are_tuner() or e["fel"] != "televizor":
			return False
		if _orbitalProgram() != e["sat"] or _tunerProgram() != -1:
			return False
		ref = luare.preia_canalul_cerut()
		if ref is None:
			return False
		e["program"] = _textProgram(ref)
		e["zap_la"] = acum
		dupa_ms = int((acum - v["pornita_la"]) * 1000)
		T.anuntaCererea(CERERE_VERIFICARE_ZAP % v["n"])
		self._rand(sec, slot, "verificare_zap", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=dupa_ms)
		T.jurnal("tunerul %s: zap pe acelasi satelit (%s) in timpul verificarii %d: verificarea merge mai departe, programul "
			"ales porneste la capatul ei" % (T.numeTuner(slot), _gradeText(e["sat"]), v["n"]))
		return True

	def _verificarePrinsa(self, sec, slot, e, acum):
		"""o referinta s-a prins: antena e la locul ei. Nicio comanda; programul porneste iar (pozitia stiuta)"""
		v = e["verificare"]
		e["verificare"] = None
		tp = v["refs"][v["i"]]
		text = _tpText(tp)
		dupa_ms = int((acum - v["pornita_la"]) * 1000)
		T.anuntaCererea(CERERE_VERIFICARE_PRINS % (v["n"], text))
		self._rand(sec, slot, "verificare_prins", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=dupa_ms)
		e["la_loc"] = {"la": acum, "tp_text": text, "program": e.get("program")}
		e["la_loc_n"] = e.get("la_loc_n", 0) + 1
		# antena dovedita la locul ei: o plecare de dupa e plecare noua (incercarea directa intai, apoi o ocolire)
		e["ocoliri"] = 0
		e["esecuri"] = 0
		e["dupa_zap"] = False
		e["fara_de"] = None
		pas = VERIFICARE_PASI_S[min(e["la_loc_n"], len(VERIFICARE_PASI_S)) - 1]
		e["urmatoarea_la"] = acum + pas
		e["ultima"] = {"faza": "verificare_prins", "tp_text": text, "dupa_ms": dupa_ms}
		e.pop("dupa_sosire", None)
		self._invataTp(e["sat"], tp)
		T.jurnal("tunerul %s: verificarea %d a prins %s dupa %.1f s: antena e pe %s, transponderul canalului nu emite acum; "
			"nicio rotire, programul porneste iar; urmatoarea verificare peste %d s" % (T.numeTuner(slot), v["n"], text,
			dupa_ms / 1000.0, _gradeText(e["sat"]), pas))
		luare = v["luare"]
		ref = luare.uita_canalul() if luare is not None else None
		if luare is not None:
			luare.elibereaza(reda_canalul=False)
		if ref is not None:
			_pornesteProgramul(ref)

	def _verificareFaraSemnal(self, sec, slot, e, acum):
		"""nicio referinta prinsa: antena nu e pe satelit; incercarea pleaca de aici, cu tunerul in mana"""
		v = e["verificare"]
		e["verificare"] = None
		texte = ", ".join(_tpScurt(tp) for tp in v["refs"])
		dupa_ms = int((acum - v["pornita_la"]) * 1000)
		T.anuntaCererea(CERERE_VERIFICARE_FARA % (v["n"], texte))
		self._rand(sec, slot, "verificare_fara_semnal", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=dupa_ms)
		e["la_loc"] = None
		e["la_loc_n"] = 0
		e["ultima"] = {"faza": "verificare_fara_semnal", "tp_text": texte, "dupa_ms": dupa_ms}
		ds = e.pop("dupa_sosire", None)
		if _rezervaPreda(slot, v["luare"]):
			T.jurnal("tunerul %s: imaginea venea de pe internet; programul de satelit se pune la loc de tunerul verificarii"
				% T.numeTuner(slot))
		T.jurnal("tunerul %s: verificarea %d fara semnal pe %s dupa %.1f s: antena nu e pe %s, urmeaza %s" % (
			T.numeTuner(slot), v["n"], texte, dupa_ms / 1000.0, _gradeText(e["sat"]),
			"comanda trimisa din nou" if ds is not None else "readucerea"))
		if ds is not None:
			self._reiaCuTunerul(sec, slot, e, acum, v["luare"], ds)
			return
		self._incercare(sec, slot, e, acum, luare=v["luare"])

	def _verificareRefuzata(self, sec, slot, e, acum, cod, motiv, program_pus):
		v = e["verificare"]
		e["verificare"] = None
		T.anuntaCererea(CERERE_VERIFICARE_REFUZATA % (v["n"], motiv))
		self._rand(sec, slot, "verificare_refuzata", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=int((acum - v["pornita_la"]) * 1000), cod=cod)
		e["ultima"] = {"faza": "verificare_refuzata", "cod": cod}
		T.jurnal("tunerul %s: verificarea %d nu a pornit: %s; readucerea merge ca inainte" % (T.numeTuner(slot), v["n"],
			motiv))
		ds = e.pop("dupa_sosire", None)
		if ds is not None and not program_pus:
			self._reiaCuTunerul(sec, slot, e, acum, v["luare"], ds)
			return
		if ds is not None:
			# programul pus la loc de LuareTuner: comanda trimisa din nou ca inainte (oprit, pauza, pornit)
			self._pozitieReluare(sec, slot, e["sat"], ds["de_la"], ds["pornire"],
				"programul se opreste si porneste din nou peste %.1f s" % (ELIBERARE_CANAL_MS / 1000.0))
			self._reluare = {"slot": slot, "la": e["sat"], "pornita_la": None}
			if not self._acordaDinNou(slot):
				self._reluare = None
			return
		self._incercare(sec, slot, e, acum, luare=None if program_pus else v["luare"])

	def _verificareOprita(self, sec, slot, e, acum, motiv):
		"""altceva are intaietate: zap-ul omului (programul lui porneste), standby-ul (programul il primeste ecranul
		Standby), altfel programul porneste iar, cu pozitia stiuta (fara comanda); incercarea nu se face acum"""
		v = e["verificare"]
		e["verificare"] = None
		e["fara_de"] = None
		e.pop("dupa_sosire", None)
		T.anuntaCererea(CERERE_VERIFICARE_OPRITA % (v["n"], motiv))
		self._rand(sec, slot, "verificare_oprita", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=int((acum - v["pornita_la"]) * 1000))
		e["ultima"] = {"faza": "verificare_oprita"}
		T.jurnal("tunerul %s: verificarea %d s-a oprit: %s" % (T.numeTuner(slot), v["n"], motiv))
		luare = v["luare"]
		if motiv == MOTIV_ZAP:
			if luare is not None:
				luare.elibereaza(reda_canalul=True)
			return
		ref = luare.uita_canalul() if luare is not None else None
		if luare is not None:
			luare.elibereaza(reda_canalul=False)
		if ref is None:
			return
		if motiv == MOTIV_STANDBY:
			_daStandbyului(T.ecranStandby(), ref)
			return
		_pornesteProgramul(ref)

	def _verificareCedata(self, slot, motiv):
		"""chemata SINCRON prin LuareTuner.cedeaza cand coordonatorul da tunerul unei extensii: programul oprit de
		verificare porneste cand tunerul se elibereaza (_datoratBate)"""
		e = self._readuceri.get(slot)
		v = e.get("verificare") if e is not None else None
		if v is None:
			return
		e["verificare"] = None
		e["fara_de"] = None
		e.pop("dupa_sosire", None)
		sec = T.controlSec()
		acum = T.acum()
		T.anuntaCererea(CERERE_VERIFICARE_OPRITA % (v["n"], "tunerul cerut de alta functie"))
		self._rand(sec, slot, "verificare_oprita", v["n"], e["sat"], fara_ms=int((acum - e["pierdut_la"]) * 1000),
			dupa_ms=int((acum - v["pornita_la"]) * 1000))
		e["ultima"] = {"faza": "verificare_oprita"}
		T.jurnal("tunerul %s: verificarea %d s-a oprit: %s; programul porneste cand tunerul se elibereaza" % (
			T.numeTuner(slot), v["n"], motiv))
		ref = v["luare"].uita_canalul() if v["luare"] is not None else None
		if ref is not None:
			self._datorat = ref

	def _datoratBate(self):
		"""programul oprit de ocolire si ramas fara stapan dupa o cedare: porneste cand tunerul nu mai e tinut de nimeni
		si nu merge niciun program; in standby il primeste ecranul Standby; un program pornit intre timp ramane"""
		ref = self._datorat
		if ref is None:
			return
		try:
			if T.programCurent() is not None:
				self._datorat = None
				T.jurnal("programul oprit de ocolire ramane oprit: intre timp a pornit alt program")
				return
		except Exception:
			self._datorat = None
			return
		standby = T.ecranStandby()
		if standby is not None:
			self._datorat = None
			_daStandbyului(standby, ref)
			return
		if T.tunerLaAltcineva():
			return
		self._datorat = None
		T.jurnal("tunerul s-a eliberat; programul oprit de ocolire porneste din nou")
		_pornesteProgramul(ref)

	def _reiaSigur(self):
		try:
			self._reia()
		except Exception as e:
			self._reluare = None
			T.jurnal("programul nu a putut porni din nou: %r" % (e,))

	def _reia(self):
		ref, self._de_reluat = self._de_reluat, None
		reluare, self._reluare = self._reluare, None
		if ref is None:
			return
		nav = _navigatie()
		if nav is None:
			return
		if nav.getCurrentlyPlayingServiceReference() is not None:
			# zap-ul omului: mutarea lui e a lui (are dreptul la reluarea ei), nu a noastra
			T.jurnal("in pauza a pornit alt program; plasa nu il schimba")
			return
		standby = T.ecranStandby()
		# un Screen e si dict (Screen.py): unul fara componente ar fi "fals", deci comparatia cu None
		if standby is not None:
			# Standby porneste la trezire numai programul oprit de el (Standby.py:64-92); pe acesta l-am oprit noi, deci
			# i-l dam lui (ca Components/HdsLnbAplicare.py, _reacordeaza), altfel la trezire ecranul ar ramane negru
			try:
				if getattr(standby, "prev_running_service", None) is None and \
						getattr(standby, "paused_service", None) is None:
					standby.prev_running_service = ref
			except Exception as e:
				T.jurnal("programul pentru trezire: %r" % (e,))
			T.jurnal("receptorul a intrat in standby in pauza; programul porneste la trezire")
			return
		if reluare is not None:
			# mutarea care incepe acum e a reluarii: daca se termina tot fara semnal, nu se mai trimite nimic
			reluare["pornita_la"] = T.acum() * 1000.0
			self._reluare = reluare
		# acelasi program care rula (deja trecut de controlul parental), acum pe un canal nou
		nav.playService(ref, checkParentalControl=False)


def _gradeText(orbital):
	"""19,2E / 5,0V pentru jurnal (fara traducere); pozitia ramane in forma nucleului, se schimba numai textul"""
	if orbital is None or orbital < 0:
		return "?"
	from Components.DishMath import orbitalToDegrees
	grade = orbitalToDegrees(orbital)
	return ("%.1f" % abs(grade)).replace(".", ",") + ("E" if grade >= 0 else "V")


def _orbitalProgram():
	"""pozitia orbitala (0..3599) a programului care merge acum, din referinta lui, sau None"""
	try:
		ref = T.programCurent()
	except Exception:
		return None
	if ref is None:
		return None
	try:
		from Components import HdsLocul
		return HdsLocul.orbitalDinReferinta(ref)
	except Exception:
		return None


def _tunerProgram():
	"""tunerul pe care a acordat programul de acum (tuner_number din frontendInfo), -1 cand nu are niciunul (nu a putut
	acorda, de pilda cat tunerul e tinut de verificare), None cand nu se poate citi"""
	nav = _navigatie()
	if nav is None:
		return None
	try:
		serviciu = nav.getCurrentService()
		info = serviciu.frontendInfo() if serviciu is not None else None
		date = (info.getFrontendData() if info else None) or {}
		return int(date.get("tuner_number", -1))
	except Exception:
		return None


def stareReaducere():
	"""readucerea antenei de acum, pentru Components/HdsMotorStare.stareJson; fara import"""
	p = _unic
	if p is None:
		return {"activa": False}
	return p.stareReaducere()


def transponderNuEmite():
	"""transponderul de referinta prins de verificare ("11494 H 22000 DVB-S2 8PSK 2/3") cand antena e la locul ei si
	transponderul programului de acum nu emite, altfel "" (Components/HdsEcranNegru.py, mesajul Fara semnal); fara
	import"""
	p = _unic
	if p is None:
		return ""
	try:
		program = p._programCurent()
		for e in list(p._readuceri.values()):
			l = e.get("la_loc")
			if l is not None and program is not None and l.get("program") == program and e.get("verificare") is None:
				return l.get("tp_text") or ""
	except Exception:
		return ""
	return ""


def _acelasiTp(a, b):
	"""True cand doua transpondere sunt acelasi: aceeasi polarizare, frecventa la cel mult VERIFICARE_TOLERANTA_KHZ"""
	try:
		return a.get("polarisation") == b.get("polarisation") and \
			abs(int(a.get("frequency", 0)) - int(b.get("frequency", 0))) <= VERIFICARE_TOLERANTA_KHZ
	except (AttributeError, TypeError, ValueError):
		return False


def _transpondereVecine(slot, sat):
	"""transponderele celorlalti sateliti ai motorului, din satellites.xml asa cum il are NimManager (fara filtrarea
	scanarii: un geaman se cauta in tot ce emite acolo), asezate dupa (polarizare, frecventa in MHz) -> [(frecventa,
	rata)], ca o cautare sa atinga numai cativa MHz; {} daca nu se pot citi"""
	try:
		from Components.NimManager import nimmanager
	except Exception:
		return {}
	vecine = {}
	for orbital, _nume in T.sateliti(slot):
		if orbital == sat:
			continue
		try:
			for x in nimmanager.getTransponders(orbital) or []:
				if x[0] == 0:
					vecine.setdefault((int(x[3]), int(x[1]) // 1000), []).append((int(x[1]), int(x[2])))
		except Exception:
			continue
	return vecine


def _areGeaman(tp, vecine):
	"""True cand pe alt satelit (vecine: _transpondereVecine) e un transponder cu aceeasi polarizare, frecventa la cel
	mult VERIFICARE_GEAMAN_KHZ si aceeasi rata de simbol (la 1 %): tunerul l-ar prinde si cu antena acolo"""
	try:
		f = int(tp.get("frequency", 0))
		sr = int(tp.get("symbol_rate", 0))
		pol = int(tp.get("polarisation"))
	except (AttributeError, TypeError, ValueError):
		return True
	marja = max(1000, sr // 100)
	mhz = VERIFICARE_GEAMAN_KHZ // 1000 + 1
	for m in range(f // 1000 - mhz, f // 1000 + mhz + 1):
		for vf, vsr in vecine.get((pol, m), ()):
			if abs(vf - f) <= VERIFICARE_GEAMAN_KHZ and abs(vsr - sr) <= marja:
				return True
	return False


def _ordineReferinta(tp):
	"""ordinea referintelor din lista satelitului, ca la ocolire: intai orizontalele, intre ele DVB-S cu rata mare"""
	return (tp.get("polarisation") != 0, not (tp.get("system") == 0 and tp.get("symbol_rate", 0) >= 20000000))


def _tpScurt(tp):
	"""11494 H (frecventa in MHz si polarizarea), pentru jurnal si pentru cererea din urma"""
	try:
		pol = "HVLR"[tp["polarisation"]] if 0 <= tp["polarisation"] <= 3 else "?"
		return "%d %s" % (int(tp["frequency"]) // 1000, pol)
	except (KeyError, TypeError, ValueError):
		return "?"


def _tpText(tp):
	"""11494 H 22000 DVB-S2 8PSK 2/3 (ca in Gasire semnal), sau forma scurta"""
	return T.transponderText(tp) or _tpScurt(tp)


def _asteptarePrindere(tp):
	"""cat se asteapta prinderea pe o referinta: timpul nucleului dupa rata de simbol plus marja (Gasire semnal)"""
	try:
		return float(_gasire().interval_incercare_s(tp))
	except Exception:
		return float(VERIFICARE_PRINDERE_S)


def _utilizator(slot, pe_slot=None, semnal=False):
	"""(fel, are_semnal, orbital) pentru ce tine tunerul cu motor: programul de pe televizor sau, altfel, o inregistrare
	pe acel tuner (si in standby); None daca nu e nimic sau nu se poate citi. Semnalul e tuner_locked (citit din
	driver), nu starea nucleului: o pierdere poate veni si fara evenimentul de pierdere. pe_slot/semnal: citite deja
	de _bate in aceeasi bataie (None = se citesc aici)."""
	if pe_slot is None:
		pe_slot, semnal = T.programulCurentPeSlot(slot)
	if pe_slot:
		orbital = _orbitalProgram()
		return ("televizor", semnal, orbital) if orbital is not None else None
	nav = _navigatie()
	if nav is None:
		return None
	try:
		inregistrari = nav.getRecordings() or []
	except Exception:
		return None
	for rec in inregistrari:
		try:
			info = rec.frontendInfo()
			if not info or (info.getFrontendData() or {}).get("tuner_number", -1) != slot:
				continue
			orbital = int((info.getTransponderData(True) or {}).get("orbital_position", -1))
			if orbital < 0:
				continue
			return "inregistrare", bool(T._stareServiciu(info).get("tuner_locked")), orbital
		except Exception:
			continue
	# canalul de satelit fara semnal, inlocuit acum de internet (HdsDvbIRezerva): tot programul televizorului
	orbital = _rezervaOrbital(slot)
	if orbital is not None:
		return "televizor", False, orbital
	return None


def _gasire():
	"""Components/HdsGasireSemnal: luarea tunerului (LuareTuner) si acordul (acordeaza), scrise o singura data acolo"""
	from Components import HdsGasireSemnal
	return HdsGasireSemnal


def _pornesteProgramul(ref):
	"""programul oprit de ocolire porneste iar; a trecut deja de controlul parental (ca plasa, _reia)"""
	nav = _navigatie()
	if nav is not None:
		nav.playService(ref, checkParentalControl=False)


def _daStandbyului(standby, ref):
	"""Standby porneste la trezire numai programul oprit de el (Standby.py:64-92): pe cel oprit de noi i-l dam lui"""
	try:
		if standby is not None and getattr(standby, "prev_running_service", None) is None and \
				getattr(standby, "paused_service", None) is None:
			standby.prev_running_service = ref
			T.jurnal("programul oprit de ocolire porneste la trezire")
	except Exception as e:
		T.jurnal("programul pentru trezire: %r" % (e,))


def _transmisieInRetea():
	"""True cat o transmisie in retea (Components/HdsTransmisie.py, TV in browser) sau un client al serverului de
	fluxuri al enigma2 tine un canal: pe un receptor cu motor ele merg numai de pe transponderul televizorului, deci
	ocolirea le-ar lua tunerul. Fara import; daca nu se poate citi, True (partea sigura)."""
	m = sys.modules.get("Components.HdsTransmisie")
	manageri = getattr(m, "_MANAGER", None) if m is not None else None
	if manageri:
		try:
			if manageri[0].transmise():
				return True
		except Exception:
			return True
	try:
		from enigma import eStreamServer
	except ImportError:
		return False
	try:
		return bool(eStreamServer.getInstance().getConnectedClients())
	except Exception:
		return True


def _satelitOcolire(slot, sat):
	"""(orbital, transponder) pentru ocolire: dintre satelitii tunerului deasupra orizontului, la cel putin
	OCOLIRE_MIN_GRADE grade de motor (unghiul USALS, ca nucleul la comanda 6E) de satelitul canalului, cel mai apropiat
	care are un transponder bun (T.alegeTransponder); None daca nu e niciunul sau locul nu se stie"""
	loc = T.coordonateUsalsNumere(slot)
	if loc is None:
		return None
	from Components import HdsMotorPlafon as PL
	from Components import HdsMotorViteza as V
	from Components.DishMath import orbitalToDegrees
	u_sat = V.unghiMotor(orbitalToDegrees(sat), loc[0], loc[1])
	if u_sat is None:
		return None
	candidati = []
	for orbital, _nume in T.sateliti(slot):
		if orbital == sat:
			continue
		grade = orbitalToDegrees(orbital)
		if not PL.vizibil(grade, loc[0], loc[1]):
			continue
		u = V.unghiMotor(grade, loc[0], loc[1])
		if u is None or abs(u - u_sat) < OCOLIRE_MIN_GRADE:
			continue
		candidati.append((abs(u - u_sat), orbital))
	for _d, orbital in sorted(candidati):
		tp = _transponderOcolire(T.transpondereBune(orbital, slot))
		if tp:
			return orbital, tp
	return None


def _transponderOcolire(bune):
	"""transponderul ocolirii: intai unul orizontal (18 V tot drumul: motorul merge pe 18 V si semnalul vine cand antena
	ajunge; pe unul vertical nucleul tine 18 V cat drumul cel mai lung, apoi trece pe 13 V), DVB-S cu rata mare cand se
	poate (T.alegeTransponder); fara orizontale, cel ales ca la Mergi la satelit"""
	orizontale = [tp for tp in bune or [] if tp.get("polarisation") == 0]
	return T.alegeTransponder(orizontale) or T.alegeTransponder(bune)


def _drumMaximS(slot, orbital):
	"""secundele celui mai lung drum posibil pana la `orbital` (de la marginea arcului vizibil cea mai departata), cu
	viteza invatata si marja plafonului (Components/HdsMotorPlafon.secunde); None daca locul sau modelul nu se stiu"""
	try:
		from Components import HdsMotorPlafon as PL
		from Components import HdsMotorViteza as V
		from Components.DishMath import orbitalToDegrees
		loc = T.coordonateUsalsNumere(slot)
		if loc is None:
			return None
		arc = PL.arcMaxim(loc[0], loc[1], [orbitalToDegrees(orbital)])
		if arc is None:
			return None
		model = V.calibrare().model(slot)
		viteza = min(model["viteza"]["est"], model["viteza"]["vest"])
		return PL.secunde(arc, viteza, model["t0"])
	except Exception as e:
		T.jurnal("drumul cel mai lung spre %s nu se poate socoti: %r" % (_gradeText(orbital), e))
		return None


def _stareFrontend(fe):
	"""(blocat, starea acordului) pentru frontendul luat de ocolire; (False, "") daca nu se poate citi"""
	if fe is None:
		return False, ""
	try:
		d = {}
		fe.getFrontendStatus(d)
		return bool(d.get("tuner_locked")), str(d.get("tuner_state", ""))
	except Exception:
		return False, ""


def _sosireCuSemnal(sec, slot):
	"""True daca ultima mutare a nucleului pe slot s-a oprit cu semnal (sec.cpp, hdsRotorArrived = 2)"""
	try:
		return int(sec.hdsRotorArrived(slot)) == 2
	except (AttributeError, TypeError, ValueError):
		return False


def _mersSpre(sec, slot, la, dupa):
	"""cat a mers (ms) mutarea nucleului spre `la` pornita dupa `dupa` (secunde, T.acum), sau -1"""
	try:
		if not sec.hdsRotorInfoValid(slot) or int(sec.hdsRotorToOrbital(slot)) != la:
			return -1
		trecut = int(sec.hdsRotorElapsedMs(slot))
		oprit_de = int(sec.hdsRotorStoppedMs(slot))
	except (AttributeError, TypeError, ValueError):
		return -1
	if trecut < 0:
		return -1
	if T.acum() * 1000.0 - trecut - max(0, oprit_de) < dupa * 1000.0 - POTRIVIRE_MS:
		return -1
	return trecut


def _ocolireOpritaDe(slot):
	"""de ce se opreste ocolirea in curs, sau None; tunerul e al ocolirii, deci coordonatorul nu se intreaba (o
	extensie care il cere ajunge la _ocolireCedata)"""
	if T.ecranStandby() is not None:
		return MOTIV_STANDBY
	try:
		curent = T.programCurent()
		# imaginea de pe internet a canalului fara semnal (HdsDvbIRezerva) nu e un zap al omului
		if curent is not None and not _rezervaEste(curent):
			return MOTIV_ZAP
	except Exception:
		return "programul de pe televizor nu se poate citi"
	if T.inregistrarePeAntena(slot):
		return "o inregistrare foloseste antena"
	secunde = T.secundePanaLaInregistrare()
	if secunde is not None and secunde <= OCOLIRE_INREGISTRARE_OPRIRE_S:
		return "o inregistrare porneste"
	if T.lacatProba():
		return "lacatul probei"
	if _comenziMotorActive() or _stapanComenzi():
		return "comenzile motorului"
	if _alteEcraneAscund():
		return "un ecran al antenei"
	if _probaLnb():
		return "proba LNB-ului"
	ecran = _ecranAntena()
	if ecran:
		return "ecranul %s" % ecran
	return None


def _gradeTextWeb(orbital):
	"""19,2 grade Est ca in /api/motor (Components/HdsMotorStare.gradeText, deja incarcat cand se cere starea); fara
	import"""
	m = sys.modules.get("Components.HdsMotorStare")
	f = getattr(m, "gradeText", None) if m is not None else None
	if f is None:
		return ""
	try:
		from Components.DishMath import orbitalToDegrees
		return f(orbitalToDegrees(orbital))
	except Exception:
		return ""


def _panouAscuns(da):
	"""panoul automat de rotire (Screens/HdsDishMotor.py) sta ascuns cat merge mutarea readucerii"""
	try:
		from Components.HdsMotorStare import panou_automat_oprit
		panou_automat_oprit("readucere", da)
	except Exception as e:
		T.jurnal("panoul automat: %r" % (e,))


def _dupaSosireMs():
	"""cat arata panoul automat o mutare oprita (Components/HdsMotorStare.MILISECUNDE_DUPA_SOSIRE)"""
	m = sys.modules.get("Components.HdsMotorStare")
	try:
		return int(getattr(m, "MILISECUNDE_DUPA_SOSIRE", 6000))
	except (TypeError, ValueError):
		return 6000


def _alteEcraneAscund():
	"""True cat Rotirea antenei sau Gasire semnal tin panoul automat ascuns (Components/HdsMotorStare._ascuns_de)"""
	m = sys.modules.get("Components.HdsMotorStare")
	cine = getattr(m, "_ascuns_de", None) if m is not None else None
	return bool(cine) and bool(set(cine) - set(["readucere"]))


def _stapanComenzi():
	"""True cat ecranul sau pagina motorului (stapan ecran/web in Components/HdsMotorComenzi.py) are comenzile"""
	m = sys.modules.get("Components.HdsMotorComenzi")
	c = getattr(m, "_unic", None) if m is not None else None
	return c is not None and getattr(c, "stapan", None) is not None


def _probaLnb():
	"""True cat Configurare LNB are o schimbare in proba sau neconfirmata (Components/HdsLnbAplicare.py)"""
	m = sys.modules.get("Components.HdsLnbAplicare")
	a = getattr(m, "APLICARE", None) if m is not None else None
	return a is not None and getattr(a, "faza", "liber") != "liber"


def _ecranAntena():
	"""numele ecranului de antena, scanare sau setari tuner deschis pe televizor, sau None"""
	sesiune = T.sesiuneInfoBar()
	if not sesiune:
		return None
	try:
		dialoguri = [sesiune.current_dialog] + [x[0] for x in getattr(sesiune, "dialog_stack", [])]
	except Exception:
		return None
	for d in dialoguri:
		if d is not None and d.__class__.__name__ in ECRANE_ANTENA:
			return d.__class__.__name__
	return None


def _comenziMotorActive():
	"""True cat ecranul "Rotirea antenei" (Components/HdsMotorComenzi.py) tine tunerul sau are o comanda in lucru: acolo
	asteptarea si oprirea le face el (laSatelit, _urmaresteNucleul). Fara import: daca modulul nu e incarcat, nu e."""
	m = sys.modules.get("Components.HdsMotorComenzi")
	c = getattr(m, "_unic", None) if m is not None else None
	if c is None:
		return False
	return getattr(c, "tuner", None) is not None or getattr(c, "stare", "liber") not in ("liber", "gata")

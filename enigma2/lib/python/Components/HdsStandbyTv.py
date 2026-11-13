# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStandbyTv.py: iesirea HDMI si televizorul cat receptorul e in standby (config.hds_standby).
#
# Iesirea HDMI: /proc/stb/hdmi/output primeste „off” / „on” (fara „\n”); se citeste gol, deci starea iesirii se ia din
# starea driverului HDMI, /proc/msp/hdmi0: PhyOutputEnable YES / NO (si RunStatus OPEN START / OPEN STOP).
#   - intrarea in standby (Screens/Standby.py, dupa ce inStandby e pus): intai CEC catre televizor (daca e ales), apoi
#     /proc/stb/power/vfd dupa afisajul din fata („1” = afisajul ramane cum e, „0” = afisajul se goleste si textele
#     urmatoare nu se mai arata pana la „on”), apoi „off”. Un semn in /tmp (tmpfs) spune ca iesirea e oprita de noi.
#   - paza: platforma reporneste singura iesirea la fiecare conectare a televizorului (aprinderea televizorului
#     coboara si urca HPD), fara sa tina seama de „off”. Cat standby-ul e deschis si numai dupa un „off” scris de noi,
#     un eTimer citeste hdmi0 la PAZA_MS; daca PhyOutputEnable e iar YES, scrie din nou vfd si „off”. Cel mult
#     PAZA_LIMITA rescrieri pe ora (un televizor care face HPD in bucla nu tine receptorul ocupat), cu un rand in
#     jurnal la depasire. Fara /proc/msp/hdmi0 (alt receptor) nu exista paza.
#   - iesirea din standby (Screens/Standby.py, inaintea pornirii canalului): paza oprita, „on” (numai daca „off” e al
#     nostru), semnul sters, apoi CEC (daca e ales si trezirea nu e de la un temporizator) si o privire HdmiColors
#     curand (Components/VideoOutput.py), ca o scriere YCbCr sa cada in aceleasi secunde cu pornirea iesirii.
#   - pornirea enigma2 (mytest.py): daca receptorul nu e in standby si iesirea e oprita (PhyOutputEnable NO) sau semnul
#     din /tmp exista (enigma2 a iesit cu iesirea oprita), se scrie „on”.
#   - oprirea completa (Screens/Standby.py, TryQuitMainloop cu 1, chiar inainte de quitMainloop; nu la repornire): cu
#     „Stinge si televizorul (CEC)” aleasa, acelasi mesaj ca la intrarea in standby, apoi cel mult OPRIRE_ASTEAPTA_S
#     pana termina scrierea si OPRIRE_LINIE_S cat pleaca mesajul pe fir (la iesirea enigma2 nodul se inchide, iar
#     close() opreste CEC in driver). Din standby nimic: televizorul l-a primit la intrarea in standby.
#
# CEC, scris aici peste nodul driverului /dev/hdmi_cec (un singur deschizator: close() opreste CEC in driver oricine
# l-ar mai tine deschis, deci nimic altceva din imagine nu deschide nodul):
#   - open() porneste CEC in driverul HDMI: driverul isi cauta singur o adresa logica libera si anunta el insusi
#     <Report Physical Address> catre toti; close() opreste CEC;
#   - write(): [destinatia, lungimea (codul + parametrii), codul, parametrii...], sursa o pune driverul; intoarce 0 cand
#     CEC nu e gata (mesaj netrimis, fara eroare), altfel numarul de octeti, fara sa stie daca televizorul a confirmat;
#   - ioctl(fd, 0) goleste coada mesajelor primite; ioctl(fd, 1, 4 octeti) da [adresa logica, adresa fizica (doi
#     octeti), adresa logica];
#   - read(): un flux de octeti cu mesajele primite, inregistrari [destinatia, lungimea (codul + parametrii), codul,
#     parametrii...]; primul octet e destinatia (adresa noastra sau 0x0F), cine a trimis nu se afla; read() intoarce 0
#     cand nu e nimic (nu blocheaza). poll() nu e trezit cand vine un mesaj, deci mesajele se citesc cu un eTimer
#     (CITIRE_MS) cat nodul e deschis. Pe placile familiei libreader (V10, Octagon SF8008 si MINI: driverul hi_hdmicec
#     al SDK-ului producatorului) driverul se poarta altfel (masurat pe un Octagon SF8008 Supreme, 0.7.1):
#       - read() care cere mai mult decat un mesaj (read(fd, 256)) intoarce EFAULT, scrie in jurnalul nucleului
#         "hdmicec_read: no enough data to receive" (kern.warn) si lasa mesajul in coada: asa nu se primea nimic, coada
#         ramanea plina, poll(0) arata mereu un mesaj si citirea la 100 ms dadea 10 randuri pe secunda;
#       - read() pe coada goala asteapta un mesaj (nu tine seama de O_NONBLOCK; "hdmicec read: receive cmd error" cand
#         e intrerupt), iar open, poll, ioctl, write si close pe acelasi nod asteapta dupa el;
#       - poll(0) arata corect daca e un mesaj in coada (nimic pe coada goala, POLLIN|POLLPRI cu un mesaj);
#       - primul octet al mesajului e cel care l-a trimis (0 = televizorul), si la mesajele catre toti.
#     Acolo un mesaj se citeste numai cand poll(0) il arata, cate unul: antetul (2 octeti), apoi exact lungimea lui;
#     dupa fiecare mesaj iar poll(0). Fara citiri "de control" cand poll nu arata nimic: una ar astepta in driver.
#     Tot acolo firul principal nu face NICIUN apel in driver: pe firul principal o citire care asteapta oprea interfata.
#     Toate apelurile pe nod si citirea adresei din /proc/msp/hdmi0_sink le face, pe rand, firul de lucru CEC (FirCec);
#     firul principal pune cererile in coada si ia rezultatele gata la pasii citirii, asteptand cel mult
#     CITIRE_ASTEAPTA_S (pasul citirii nu asteapta: il ia un ceas dupa PRELUARE_MS). Un apel care nu se intoarce in
#     CITIRE_BLOCATA_S opreste CEC pana la repornirea interfetei
#     (nimic nu mai pleaca spre nod, nici ce era in coada; firul ramas in driver e de fundal si nu-l asteapta nimeni)
#     si apare in pagina web ca „nu raspunde”. Adresa fizica se tine minte dupa prima citire buna.
# Numele: cel scris in setari (config.hds_standby.nume_tv) sau, gol, modelul citit pe receptor (model= din
# /etc/hdsatelit-model, altfel /usr/lib/enigma.info), simplificat: fara diacritice, numai ASCII, fara primele cuvinte
# (marca) cat e mai lung de NUME_MAX: "Amiko Viper 4K V20" -> "Viper 4K V20". /proc/stb/info/model nu se foloseste:
# driverul de aici da acolo un nume fals de compatibilitate. Pachetul HDMI SPD (numele sursei in infoframe) nu se
# trimite: driverul il trimite numai cu atributul pus de demonul platformei, care il tine oprit.
# Nodul e deschis tot timpul pe un receptor care il are: numele receptorului pe televizor (lista intrarilor HDMI) vine
# numai prin CEC. Partea pornita din fabrica e cea mai mica de care e nevoie pentru nume si nu schimba nimic pe
# televizor: dupa deschidere (ANUNT_MS) <Report Physical Address> 0x84 si <Set OSD Name> 0x47 (repetate la
# ANUNT_REPETA_MS cat CEC nu e gata), numele din nou la schimbarea setarii, si raspunsuri numai la intrebarile puse
# receptorului: <Give OSD Name> 0x46 -> numele, <Give Physical Address> 0x83 -> 0x84, <Give Device Power Status> 0x8F
# -> <Report Power Status> 0x90 (pornit sau standby), <Get CEC Version> 0x9F -> <CEC Version> 0x9E (1.3a),
# <Give Device Vendor ID> 0x8C -> <Feature Abort> (nu avem un cod de producator). Raspunsurile merg catre televizor
# (0), fiindca sursa intrebarii nu se afla. Mesajele catre toti si celelalte coduri nu primesc raspuns; din calea
# numelui nu pleaca niciodata <Standby>, <Image View On>, <Active Source> sau <Inactive Source>.
# Telecomanda televizorului (setarea "Comanda din telecomanda televizorului", config.hds_standby.cec_telecomanda, Da din
# fabrica): <User Control Pressed> / <User Control Released> de la televizor devin tastele telecomenzii receptorului
# (TASTE_CEC: codul CEC -> codul Linux al tastei Viper) pe calea obisnuita a tastelor (eRCMapper.inject), deci merg in
# toate ecranele si in aplicatia HbbTV; aceeasi tasta din nou = repetarea, iar fara repetare sau ridicare in ELIBERARE_MS
# tasta se ridica singura. OK scurt = OK; OK tinut OK_LUNG_MS = panoul "Mai multe taste" (ChoiceBox), cu tastele
# receptorului pe care telecomanda televizorului nu le are si tabelul tastelor (TextBox). Puterea si volumul de la
# televizor nu se trimit receptorului. <Menu Request> -> <Menu Status>; dupa fiecare <Active Source> al nostru,
# <Menu Status> "activat" (receptorul cere tastele). Versiunea CEC: 1.4. Compatibilitate cu televizorul: vezi
# COMPATIBILITATE_TV (codul de producator si legatura facuta prin comenzile proprii ale televizorului, cat tastele
# televizorului sunt pornite). Sursa activa se afla NUMAI din mesaje (Rsen din
# hdmi0 nu arata intrarea aleasa: ramane YES si cat televizorul e pe sursa lui), cu trei stari (Cec.activ): True = pe
# noi (<Set Stream Path> / <Routing Change> / <Routing Information> spre adresa noastra, o tasta de la televizor),
# False = stiut ca nu (<Active Source> al altcuiva, alta cale, <Standby> de la televizor, intrarea noastra in standby),
# None = nu se stie (la pornirea enigma2, pana vine un mesaj). Dupa primul anunt bun, o data, <Request Active Source>
# 0x85 catre toti: aparatul de pe ecran (sau televizorul, pe tunerul lui) raspunde cu <Active Source> si starea devine
# False; fara raspuns ramane None. <Active Source> numai cand televizorul arata intrarea noastra: la mesajele
# de mai sus, la <Request Active Source> daca suntem sursa, la trezirea facuta de om daca eram sursa la intrarea in
# standby si nimic nu a spus altfel intre timp; la pornire nimic. Nu aprinde si nu muta televizorul. Tipul aparatului
# e Playback: adresa logica o alege driverul (4, 8, 11). Cat setarea e pornita, mesajele se citesc la CITIRE_RAPIDA_MS.
# Setarile de standby (Stinge si televizorul, Porneste televizorul la trezire) folosesc acelasi nod: <Standby> 0x36
# catre televizor la intrarea in standby si la oprirea completa cand receptorul e pe ecran SAU nu se stie (0.7.5:
# inainte numai cand era stiut pe ecran, deci dupa o pornire fara nicio tasta a televizorului pleca numai <Inactive
# Source> si televizorul ramanea aprins, Wlad, forum 948); numai cand se stie ca televizorul arata altceva, doar
# <Inactive Source> 0x9D. <Image View On> 0x04 catre televizor si <Active Source> 0x82 catre toti la iesire. Adresa
# fizica: CECAddr din /proc/msp/hdmi0_sink (EDID-ul televizorului), altfel ioctl 1.
# Televizorul -> receptorul (0.7.5, cererea lui wlad-sat, forum 1209; ca handle_tv_standby / handle_tv_wakeup din
# OE-Alliance, fara setare noua):
#   - receptorul in standby si televizorul alege intrarea lui (<Set Stream Path> / <Routing Change> / <Routing
#     Information> spre adresa noastra, de pilda la aprinderea televizorului pe intrarea receptorului sau din lista
#     SIMPLINK / Anynet+): receptorul se trezeste, cat „Comanda din telecomanda televizorului” e Da (din fabrica);
#   - televizorul se stinge (<Standby> de la televizor, catre toti sau catre noi) cand receptorul era pe ecran sau nu se
#     stie: receptorul intra si el in standby, numai cu „Stinge si televizorul (CEC)” aleasa (se sting impreuna). Nu
#     cat receptorul e deja in standby, se opreste sau tocmai s-a trezit (TREZIT_PAUZA_S: televizorul inca se stinge),
#     si nici cat se incearca aprinderea televizorului (cel mult APRINDERE_TERMEN_S; proba pe Viper 4K V20 + LG: LG-ul
#     care abia se stingea a trimis <Standby> la 23 s dupa trezire, iar receptorul trezit de om intra singur in standby).
#   Pe familia libreader primul octet al mesajului e cel care l-a trimis, deci un mesaj catre toti nu are 0x0F:
#   <Standby> se trateaza la fel, oricare ar fi primul octet. Totul pe firul principal (_primit vine din _preia).
# Aprinderea televizorului (0.7.5 b, Wlad, forum 948 #2116/#2118, V10 + LG: „am pornit receptorul din oprit complet si
# televizorul nu s-a aprins”): cu „Porneste televizorul la trezire (CEC)” aleasa, la trezirea facuta de om SI la pornirea
# reala a receptorului (sistemul pornit de cel mult PORNIRE_UPTIME_S, nu repornirea interfetei, nu trezirea de la ceas,
# nu cand interfata porneste in standby; primul pas dupa PORNIRE_DUPA_MS), <Image View On> + <Active Source> se trimit din
# nou la APRINDERE_REPETA_MS (de la a doua oara si <Give Device Power Status>) pana cand: televizorul spune ca e pornit
# (<Report Power Status> pornit, o tasta a lui, alegerea intrarii noastre), sau HDMI e sus (Rsen YES), adresa fizica se
# stie si mesajul a plecat; ori pana trece APRINDERE_TERMEN_S, receptorul intra in standby sau televizorul arata alta
# intrare. Rsen YES (si cele doua trimiteri bune fara /proc/msp/hdmi0) nu opresc aprinderea daca televizorul a raspuns dupa
# inceput ca e in standby sau abia se aprinde (<Report Power Status> 01/02/03): pe LG-ul de pe .122 Rsen ramane YES si cu
# televizorul stins (proba pe receptor), iar aprinderea se oprea dupa o trimitere, cu televizorul inca stins.
# La LG HPD cade ~5 s cand televizorul se aprinde (AS5): un singur mesaj trimis atunci se pierdea. Un rand in
# jurnal la inceput si unul la sfarsit (ce s-a trimis, de cate ori, de ce s-a oprit), si intrarea „aprindere” in jurnalul CEC.
# Codul televizorului (pentru legatura SIMPLINK): si fara intrebarea noastra, cand e sigur al televizorului (pe familia
# libreader primul octet 0) sau e un cod din COMPATIBILITATE_TV. Altfel, la LG (Wlad, AS5), televizorul isi trimitea codul
# primul, receptorul il arunca si raspundea la <Give Device Vendor ID> cu <Feature Abort>, iar LG dadea apoi numai
# tastele de baza (sageti, OK, inapoi).
#
# Toate scrierile si citirile sunt prinse; erorile merg in jurnal, cel mult JURNAL_PE_CHEIE randuri de acelasi fel.
# Jurnalul CEC (Cec.jurnalCec, in memorie, ultimele JURNAL_CEC_MAX intrari, citit prin jurnalCec() si
# /api/standby-tv?jurnal=1): fiecare mesaj primit si trimis si fiecare tasta data mai departe, cu ora; plus de cate ori
# coada driverului a fost golita dupa un inceput de neinteles (golite). Arata ce trimite televizorul la apasari repezi,
# cand ajung tastele si unde se pierd, fara un al doilea cititor al nodului (care ar fura mesajele).
# 0.7.5: acelasi jurnal (o stare pe un rand, apoi ultimele JURNAL_TMP_RANDURI intrari) si in /tmp/hds-cec.txt, scris
# cel mult o data la JURNAL_TMP_MS dupa o intrare noua (tmpfs). Asistenta il citeste cu operatia existenta „citeste”
# (/tmp e in tiparul ei), deci proba CEC se face la omul care are televizorul, fara web, fara SSH, fara operatie noua.
# Caile se pot muta sub un dosar cu HDS_PROBA_STANDBY_TV (emulatorul si probele de pe PC). Fisierul nu importa nimic
# din enigma2 la incarcare: probele de pe PC il folosesc direct.

import errno
import io
import os
import re
import time
try:
	import unicodedata          # in imagine e in lib-dynload; fara el, numai diacriticele romanesti de mai jos
except ImportError:
	unicodedata = None

# literele romanesti (si s, t cu sedila, scrierea veche) fara semne, cand unicodedata lipseste
FARA_DIACRITICE = dict((ord(a), b) for a, b in zip(
	u"\u0103\u00e2\u00ee\u0219\u021b\u015f\u0163\u0102\u00c2\u00ce\u0218\u021a\u015e\u0162", u"aaiststAAISTST"))

IESIRE_REL = "/proc/stb/hdmi/output"
VFD_REL = "/proc/stb/power/vfd"
HDMI0_REL = "/proc/msp/hdmi0"
SINK_REL = "/proc/msp/hdmi0_sink"
CEC_REL = "/dev/hdmi_cec"
SEMN_REL = "/tmp/hds-hdmi-oprit"
MODEL_REL = "/etc/hdsatelit-model"
ENIGMA_INFO_REL = "/usr/lib/enigma.info"
JURNAL_TMP_REL = "/tmp/hds-cec.txt"     # jurnalul CEC si pentru asistenta (op „citeste”), in tmpfs

OPRIRE_ASTEAPTA_S = 0.5     # oprirea completa: cat asteapta scrierea CEC (firul de lucru CEC) inainte de quitMainloop
OPRIRE_LINIE_S = 0.2        # ... si apoi cat pleaca mesajul pe fir (un <Standby> are ~60 ms, plus o reincercare)
PAZA_MS = 2500
PAZA_LIMITA = 30            # rescrieri ale lui „off” pe ora
CULORI_DUPA_MS = 2000       # privirea HdmiColors dupa „on”
SURSA_DUPA_TREZIRE_MS = 6000  # dupa trezire: <Active Source> din nou (daca eram sursa), cand imaginea a pornit
NUME_DUPA_MS = 2000         # numele nou pleaca la televizor la atat dupa ultima schimbare a setarii
ANUNT_MS = 3000             # anuntul CEC dupa deschiderea nodului
ANUNT_REPETA_MS = 5000      # anuntul din nou cat CEC nu e gata (write = 0)
ANUNT_INCERCARI = 12
CITIRE_MS = 400             # citirea mesajelor primite, cat nodul e deschis
CITIRI_PE_PAS = 8
CITIRE_SIGURA_MS = 5000     # numai citirea pe firul principal cu poll (inFir=False, probele): o citire si cand poll(0) nu
                            # arata nimic; pe firul de lucru CEC (familia libreader) nu: acolo o citire pe coada goala
                            # asteapta in driver
CITIRE_ASTEAPTA_S = 0.01    # familia libreader: cat asteapta firul principal o cerere pusa firului de lucru CEC liber
                            # (scrierile, deschiderea, adresele: rezultatul lor merge la apelant)
PRELUARE_MS = 10            # familia libreader: pasul citirii nu asteapta; rezultatul lui il ia un ceas dupa atat
CITIRE_BLOCATA_S = 1.0      # familia libreader: un apel in driver care nu se intoarce in atat opreste CEC
JURNAL_PE_CHEIE = 5
JURNAL_CEC_MAX = 500        # intrarile jurnalului CEC tinute in memorie (cele mai vechi ies)
JURNAL_TMP_MS = 2000        # jurnalul CEC in JURNAL_TMP_REL: cel mult o scriere la atat dupa o intrare noua
JURNAL_TMP_RANDURI = 200    # ultimele atatea intrari in fisier

NUME_MAX = 14               # <Set OSD Name>: cel mult 14 caractere ASCII
NUME_REZERVA = "HD Satelit"

CEC_TV = 0x00
CEC_TOTI = 0x0F
CEC_LOGICA_IMPLICITA = 0x04  # Playback 1, adresa pe care o ia de obicei driverul
CEC_LUNGIME_MAX = 16         # codul + cel mult 14 parametri (un mesaj CEC are cel mult 16 octeti)
CEC_FEATURE_ABORT = 0x00
CEC_IMAGE_VIEW_ON = 0x04
CEC_STANDBY = 0x36
CEC_GIVE_OSD_NAME = 0x46
CEC_SET_OSD_NAME = 0x47
CEC_ACTIVE_SOURCE = 0x82
CEC_GIVE_PHYSICAL_ADDRESS = 0x83
CEC_REPORT_PHYSICAL_ADDRESS = 0x84
CEC_GIVE_DEVICE_VENDOR_ID = 0x8C
CEC_GIVE_DEVICE_POWER_STATUS = 0x8F
CEC_REPORT_POWER_STATUS = 0x90
CEC_INACTIVE_SOURCE = 0x9D
CEC_CEC_VERSION = 0x9E
CEC_GET_CEC_VERSION = 0x9F
CEC_TIP_PLAYBACK = 0x04
CEC_VERSIUNE_14 = 0x05
CEC_PORNIT = 0x00
CEC_IN_STANDBY = 0x01
CEC_SPRE_PORNIT = 0x02       # <Report Power Status>: in trecere spre pornit
CEC_MOTIV_COD_NECUNOSCUT = 0x00
CEC_GOLESTE = 0
CEC_ADRESA = 1
CEC_DEVICE_VENDOR_ID = 0x87
CEC_VENDOR_COMMAND = 0x89
CEC_GIVE_DECK_STATUS = 0x1A
CEC_DECK_STATUS = 0x1B
CEC_CASETA_ALTA = 0x1F       # <Deck Status>: "alta stare"
CEC_STARE_CERUTA = (0x01, 0x03)   # <Give Deck Status>: "pornit", "o data" (la "oprit" nu se raspunde)

# Compatibilitate cu televizorul. Unele televizoare trimit tastele telecomenzii numai unui aparat cu care au facut
# legatura prin comenzile lor proprii (<Vendor Command>). Pentru ele: la <Give Device Vendor ID> raspundem cu codul
# televizorului, iar la comenzile lui cu raspunsurile de mai jos (probate pe un televizor real). Codul televizorului:
# primul <Device Vendor ID> venit cel mult COD_TV_ASTEPTARE_S dupa intrebarea noastra catre el.
# Legatura LG (SIMPLINK) numai cu setarea „Legătura LG SIMPLINK (toate tastele)” (config.hds_standby.cec_lg_simplink, Nu
# din fabrica): un LG care primeste codul lui de la receptor il trece in lista intrarilor ca aparat LG („LG Cititor DVD”,
# dispozitivul de telecomanda universala gasit singur, cu marca LG si tipul DVD) si nu mai arata numele receptorului
# (vazut in lista intrarilor LG-ului de langa .122, HDMI 1; Octagonul fara legatura, pe HDMI 3, aparea cu numele lui).
# Fara setare: <Feature Abort> la <Give Device Vendor ID> si fara raspuns la comenzile LG, deci numele adevarat si
# tastele de baza ale telecomenzii LG (sagetile, OK, inapoi; restul din panoul „Mai multe taste”, OK tinut).
COMPATIBILITATE_TV = {
	b"\x00\xe0\x91": "lg",       # LG Electronics (registrul IEEE: 00-E0-91; trimis de televizor pe cablu)
}
TREZIT_PAUZA_S = 10.0        # dupa trezirea receptorului, un <Standby> de la televizor nu-l mai pune in standby
COD_TV_ASTEPTARE_S = 2.0
APRINDERE_REPETA_MS = 3000   # aprinderea televizorului: pasul (Image View On + Active Source din nou)
APRINDERE_TERMEN_S = 45.0    # ... cel mult atat de la inceput
PORNIRE_DUPA_MS = 4000       # la pornirea receptorului, primul pas al aprinderii dupa atat (nodul CEC si adresa)
PORNIRE_UPTIME_S = 300.0     # „pornirea receptorului” = sistemul pornit de cel mult atat (nu repornirea interfetei)
COD_TV_REINTREBARE_S = 60.0
LEGATURA_INCEPUT, LEGATURA_CONFIRMARE, LEGATURA_PORNIRE, LEGATURA_CERERE, LEGATURA_MOD = 0x01, 0x02, 0x03, 0x04, 0x05
LEGATURA_RECONECTARE, LEGATURA_STARE = 0x0B, 0xA0
LEGATURA_TIP = 0x05          # in confirmarea inceputului legaturii

NUME_MESAJ = {CEC_STANDBY: "standby", CEC_INACTIVE_SOURCE: "inactive_source", CEC_IMAGE_VIEW_ON: "image_view_on",
	CEC_ACTIVE_SOURCE: "active_source", CEC_REPORT_PHYSICAL_ADDRESS: "report_physical_address",
	CEC_SET_OSD_NAME: "set_osd_name", CEC_GIVE_OSD_NAME: "give_osd_name",
	CEC_GIVE_PHYSICAL_ADDRESS: "give_physical_address", CEC_GIVE_DEVICE_VENDOR_ID: "give_device_vendor_id",
	CEC_GIVE_DEVICE_POWER_STATUS: "give_device_power_status", CEC_REPORT_POWER_STATUS: "report_power_status",
	CEC_GET_CEC_VERSION: "get_cec_version", CEC_CEC_VERSION: "cec_version", CEC_FEATURE_ABORT: "feature_abort",
	0x80: "routing_change", 0x85: "request_active_source", 0x86: "set_stream_path", 0x87: "device_vendor_id",
	0x44: "user_control_pressed", 0x45: "user_control_released", 0x81: "routing_information",
	0x8D: "menu_request", 0x8E: "menu_status", 0x89: "vendor_command", 0xA0: "vendor_command_with_id",
	0x1A: "give_deck_status", 0x1B: "deck_status"}

# ---------------------------------------------------------------- telecomanda televizorului prin CEC

CITIRE_RAPIDA_MS = 100      # citirea cat telecomanda televizorului e pornita (tastele raspund repede)
ELIBERARE_MS = 600          # o tasta fara repetare sau ridicare atata timp se socoteste ridicata (standardul: 550 ms)
OK_LUNG_MS = 900            # OK tinut atat pe telecomanda televizorului deschide panoul "Mai multe taste"
STEAG_APASARE, STEAG_RIDICARE, STEAG_REPETARE = 0, 1, 2
CEC_USER_CONTROL_PRESSED = 0x44
CEC_USER_CONTROL_RELEASED = 0x45
CEC_ROUTING_CHANGE = 0x80
CEC_ROUTING_INFORMATION = 0x81
CEC_REQUEST_ACTIVE_SOURCE = 0x85
CEC_SET_STREAM_PATH = 0x86
CEC_MENU_REQUEST = 0x8D
CEC_MENU_STATUS = 0x8E
CEC_MENU_ACTIV = 0x00
CEC_MENU_INACTIV = 0x01
CEC_MENU_INTREBARE = 0x02
CEC_UI_SELECT = 0x00

# tastele telecomenzii receptorului (codurile Linux, ca in Components/HdsTelecomenziDate.BUTOANE_VIPER)
T_OK, T_SUS, T_JOS, T_STANGA, T_DREAPTA = 352, 103, 108, 105, 106
T_MENU, T_EXIT, T_EPG, T_INFO, T_AUDIO, T_TTX, T_SUBT, T_HELP, T_FAV = 139, 174, 365, 358, 392, 388, 370, 138, 364
T_CH_PLUS, T_CH_MINUS, T_ANTERIOR, T_URMATOR = 402, 403, 412, 407
T_ROSU, T_VERDE, T_GALBEN, T_ALBASTRU = 398, 399, 400, 401
T_REDARE, T_PAUZA, T_STOP, T_INREGISTRARE = 207, 119, 128, 167
T_DERULARE_INAPOI, T_DERULARE_INAINTE, T_SALT_INAPOI, T_SALT_INAINTE = 168, 208, 165, 163
T_EMC, T_MPLAY, T_PORTAL, T_TIMER, T_TV, T_RADIO = 393, 395, 150, 359, 377, 385
T_ECRAN1, T_ECRAN2, T_ECRAN3 = 373, 227, 438
T_CIFRE = (11, 2, 3, 4, 5, 6, 7, 8, 9, 10)          # 0, 1, ... 9

# codul din <User Control Pressed> (standardul HDMI-CEC 1.4, tabelul codurilor) -> tasta receptorului. Puterea,
# volumul si MUTE nu sunt aici: le face televizorul (sau bara de sunet), iar puterea nu pune receptorul in standby.
TASTE_CEC = {
	0x00: T_OK,             # Select
	0x01: T_SUS, 0x02: T_JOS, 0x03: T_STANGA, 0x04: T_DREAPTA,
	0x09: T_MENU,           # Root Menu
	0x0A: T_MENU,           # Setup Menu
	0x0B: T_EMC,            # Contents Menu: inregistrarile
	0x0C: T_FAV,            # Favorite Menu
	0x0D: T_EXIT,           # Exit (BACK pe telecomenzile televizoarelor)
	0x2B: T_OK,             # Enter
	0x30: T_CH_PLUS, 0x31: T_CH_MINUS,
	0x32: T_ANTERIOR,       # Previous Channel: canalul de dinainte
	0x33: T_AUDIO,          # Sound Select
	0x35: T_INFO,           # Display Information
	0x36: T_HELP,
	0x44: T_REDARE, 0x45: T_STOP, 0x46: T_PAUZA, 0x47: T_INREGISTRARE,
	0x48: T_DERULARE_INAPOI, 0x49: T_DERULARE_INAINTE,
	0x4B: T_SALT_INAINTE,   # Forward
	0x4C: T_SALT_INAPOI,    # Backward
	0x51: T_SUBT,           # Sub Picture
	0x53: T_EPG,            # Electronic Program Guide
	0x60: T_REDARE,         # Play Function
	0x61: T_PAUZA,          # Pause-Play Function
	0x62: T_INREGISTRARE,   # Record Function
	0x64: T_STOP,           # Stop Function
	0x71: T_ALBASTRU,       # F1 (Blue)
	0x72: T_ROSU,           # F2 (Red)
	0x73: T_VERDE,          # F3 (Green)
	0x74: T_GALBEN,         # F4 (Yellow)
	0x76: T_TTX,            # Data
}
for _i, _cod in enumerate(T_CIFRE):
	TASTE_CEC[0x20 + _i] = _cod

# panoul "Mai multe taste" (OK tinut pe telecomanda televizorului): toate tastele receptorului afara de cele pe care
# orice telecomanda de televizor le are (sagetile, OK, cifrele, CH+ / CH-) si de cele ale televizorului (POWER, VOL,
# MUTE), in ordinea de pe telecomanda receptorului
PANOU_TASTE = (T_MENU, T_EXIT, T_ECRAN1, T_ECRAN2, T_ECRAN3, T_ANTERIOR, T_URMATOR, T_EPG, T_INFO, T_AUDIO, T_TTX, T_SUBT,
	T_ROSU, T_VERDE, T_GALBEN, T_ALBASTRU, T_EMC, T_PORTAL, T_MPLAY, T_TIMER, T_SALT_INAPOI, T_DERULARE_INAPOI,
	T_DERULARE_INAINTE, T_SALT_INAINTE, T_PAUZA, T_STOP, T_REDARE, T_INREGISTRARE, T_TV, T_HELP, T_FAV, T_RADIO)
# tastele receptorului de care se ocupa televizorul (nu se trimit receptorului prin CEC)
TASTE_TELEVIZOR = (116, 113, 115, 114)          # POWER, MUTE, VOL+, VOL-

RADACINA = None
IESIRE = VFD = HDMI0 = SINK = CEC = SEMN = MODEL = ENIGMA_INFO = JURNAL_TMP = None


def folosesteRadacina(radacina=None):
	"""Caile driverului; `radacina` (sau HDS_PROBA_STANDBY_TV) muta toate caile sub un dosar."""
	global RADACINA, IESIRE, VFD, HDMI0, SINK, CEC, SEMN, MODEL, ENIGMA_INFO, JURNAL_TMP
	if radacina is None:
		radacina = os.environ.get("HDS_PROBA_STANDBY_TV") or ""
	RADACINA = radacina.rstrip("/\\")

	def p(rel):
		return RADACINA + rel if RADACINA else rel
	IESIRE, VFD, HDMI0, SINK, CEC, SEMN = (p(IESIRE_REL), p(VFD_REL), p(HDMI0_REL), p(SINK_REL), p(CEC_REL),
		p(SEMN_REL))
	MODEL, ENIGMA_INFO, JURNAL_TMP = p(MODEL_REL), p(ENIGMA_INFO_REL), p(JURNAL_TMP_REL)


folosesteRadacina()

_SPUSE = {}


def _jurnal(text, cheie=None):
	"""Un rand in jurnal (ASCII); cu `cheie`, cel mult JURNAL_PE_CHEIE randuri de acel fel la o pornire."""
	if cheie is not None:
		n = _SPUSE.get(cheie, 0) + 1
		_SPUSE[cheie] = n
		if n > JURNAL_PE_CHEIE:
			return
		if n == JURNAL_PE_CHEIE:
			text += " (mai departe nu se mai scrie)"
	try:
		print("[HdsStandbyTv] %s" % text)
	except Exception:
		pass


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def citeste_direct(cale):
	"""Textul unui fisier mic (/proc), sau None."""
	try:
		with io.open(cale, "r", encoding="latin-1") as f:
			return f.read()
	except (IOError, OSError, ValueError):
		return None


def citeste(cale):
	"""Ca citeste_direct; fisierele driverului (/proc/msp, /proc/hisi) le citeste pe firul de fundal."""
	return _procFundal(citeste_direct, cale)


def scrie(cale, valoare, cheie=None):
	"""Scrie `valoare` fara „\\n”; True daca a mers. Eroarea merge in jurnal (limitat dupa `cheie`)."""
	try:
		with io.open(cale, "w", encoding="ascii") as f:
			f.write(u"%s" % valoare)
		return True
	except (IOError, OSError, ValueError) as e:
		_jurnal("nu pot scrie %s in %s: %s" % (valoare, cale, e), cheie or ("scrie", cale))
		return False


def camp(text, cheie):
	"""Prima valoare a lui `cheie` intr-un text /proc/msp („Cheie   : valoare”, una sau doua perechi pe rand)."""
	if not text:
		return None
	m = re.search(r"(?:^|\s)%s\s*:\s*(\S+(?: (?:START|STOP))?)" % re.escape(cheie), text, re.M)
	return m.group(1) if m else None


def iesirePornita(text=None):
	"""True / False dupa PhyOutputEnable din hdmi0 (citit acum daca `text` e None); None fara fisier sau camp."""
	if text is None:
		text = citeste(HDMI0)
	v = camp(text, "PhyOutputEnable")
	if v is None:
		return None
	return v.upper() == "YES"


def tvPeIntrare(text=None):
	"""Rsen din hdmi0: True = televizorul tine terminatia pe legatura noastra (aprins); False = stins sau fara
	terminatie; None = nu se stie. NU arata intrarea aleasa (ramane YES si cat televizorul e pe sursa lui), deci nu se
	foloseste pentru sursa activa."""
	if text is None:
		text = citeste(HDMI0)
	v = camp(text, "Rsen")
	if v is None:
		return None
	return v.upper() == "YES"


# tvStins: hdmi0 citit cel mult o data la atatea secunde; (ora ultimei citiri pe ceasul monoton, raspunsul)
TV_STINS_S = 5.0
_TV_STINS = [None, False]


def tvStins(acum=None):
	"""True numai cand driverul HDMI spune sigur ca televizorul nu tine legatura cu receptorul (Rsen NO: stins sau in
	standby, ori cablul scos); False cand e aprins sau cand nu se stie (fara fisier sau camp, de pilda in emulator).
	Pentru lucrul care nu foloseste nimanui cu ecranul stins (recunoasterea si traducerea subtitrarilor). Citit cel mult
	o data la TV_STINS_S secunde."""
	if acum is None:
		acum = time.monotonic()
	if _TV_STINS[0] is None or acum < _TV_STINS[0] or acum - _TV_STINS[0] >= TV_STINS_S:
		_TV_STINS[0] = acum
		_TV_STINS[1] = tvPeIntrare() is False
	return _TV_STINS[1]


def contorHpd(text=None):
	"""Conectarile vazute de driver (coloana HPD din randul WR al tabelului de evenimente), sau None."""
	if text is None:
		text = citeste(HDMI0)
	if not text:
		return None
	cap = re.search(r"^\s*CNT\|(.*)$", text, re.M)
	wr = re.search(r"^\s*WR:\|(.*)$", text, re.M)
	if not cap or not wr:
		return None
	nume = [x.strip() for x in cap.group(1).split("|")]
	valori = [x.strip() for x in wr.group(1).split("|")]
	try:
		return int(valori[nume.index("HPD")])
	except (ValueError, IndexError):
		return None


def adresaDinSink(text=None):
	"""Adresa fizica a receptorului din EDID-ul televizorului (CECAddr „03.00.00.00” = 3.0.0.0), ca doi octeti, sau
	None (EDID nevalid, adresa 0.0.0.0, fisier lipsa)."""
	if text is None:
		text = citeste(SINK)
	valid = camp(text, "CECAddrIsValid")
	if valid is not None and valid.upper() != "YES":
		return None
	v = camp(text, "CECAddr")
	if not v:
		return None
	parti = v.split(".")
	try:
		cifre = [int(x, 16) for x in parti]
	except ValueError:
		return None
	if len(cifre) != 4 or any(c < 0 or c > 15 for c in cifre) or not any(cifre):
		return None
	return bytes(bytearray([(cifre[0] << 4) | cifre[1], (cifre[2] << 4) | cifre[3]]))


def textAdresa(adresa):
	if not adresa or len(adresa) != 2:
		return None
	a, b = bytearray(adresa)
	return "%d.%d.%d.%d" % (a >> 4, a & 15, b >> 4, b & 15)


def cadru(destinatie, cod, parametri=b""):
	"""Octetii pentru write(): [destinatia, lungimea (codul + parametrii), codul, parametrii...]."""
	parametri = bytes(bytearray(parametri))
	return bytes(bytearray([destinatie & 0x0F, 1 + len(parametri), cod & 0xFF])) + parametri


def hexa(date):
	return " ".join("%02x" % x for x in bytearray(date))


# ---------------------------------------------------------------- numele pe televizor

def textAscii(text):
	"""`text` fara diacritice, numai caractere ASCII tiparibile (altele devin spatiu), spatiile stranse."""
	if not text:
		return u""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	text = u"%s" % text
	if unicodedata is not None:
		text = u"".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
	else:
		text = text.translate(FARA_DIACRITICE)
	rez = [c if 0x20 <= ord(c) <= 0x7E else u" " for c in text]
	return u" ".join(u"".join(rez).split())


def simplificaModel(model, maxim=NUME_MAX):
	"""Modelul care incape in `maxim` caractere: fara diacritice, fara primele cuvinte (marca) cat e prea lung, apoi
	taiat. "Amiko Viper 4K V20" -> "Viper 4K V20"."""
	cuvinte = [c for c in textAscii(model).split(u" ") if c]
	while len(cuvinte) > 1 and len(u" ".join(cuvinte)) > maxim:
		cuvinte.pop(0)
	return u" ".join(cuvinte)[:maxim].strip()


def _valoareDin(text, chei):
	"""Prima valoare a uneia din `chei` (in ordinea lor) intr-un text cheie=valoare, fara ghilimele; "" daca lipseste."""
	gasite = {}
	for rand in (text or u"").splitlines():
		rand = rand.strip()
		if not rand or rand.startswith(u"#") or u"=" not in rand:
			continue
		k, v = rand.split(u"=", 1)
		k = k.strip().lower()
		if k in chei and k not in gasite:
			gasite[k] = v.strip().strip(u"'\"").strip()
	for k in chei:
		if gasite.get(k):
			return gasite[k]
	return u""


def areDate(fd):
	"""True cand driverul are un mesaj in coada (poll cu timpul 0), False cand nu, None cand poll() nu merge pe nod"""
	try:
		import select
		p = select.poll()
		p.register(fd, select.POLLIN | select.POLLPRI)
		r = p.poll(0)
		return bool(r) and any(ev & (select.POLLIN | select.POLLPRI) for _f, ev in r)
	except Exception:
		return None


def citireDupaPoll():
	"""True pe placile al caror driver CEC scrie in jurnalul nucleului la fiecare citire goala (familia libreader)"""
	try:
		try:
			from Components import HdsPlatforma
		except ImportError:  # probele de pe PC: modulul incarcat singur, din dosarul Components
			import HdsPlatforma
		return bool(HdsPlatforma.familiaLibreader())
	except Exception:
		return False


def modelReceptor():
	"""Modelul citit pe receptor: model= din /etc/hdsatelit-model (scris de reteta imaginii), altfel displaymodel sau
	model din /usr/lib/enigma.info; "" daca nu se stie."""
	for cale, chei in ((MODEL, ("model",)), (ENIGMA_INFO, ("displaymodel", "model"))):
		try:
			with io.open(cale, "r", encoding="utf-8", errors="replace") as f:
				text = f.read(16384)
		except (IOError, OSError, ValueError):
			continue
		v = _valoareDin(text, chei)
		if v:
			return v
	return u""


def numeImplicit():
	"""Numele cand setarea e goala: modelul simplificat, altfel "HD Satelit"."""
	return simplificaModel(modelReceptor()) or NUME_REZERVA


def numeAles(text):
	"""Numele scris de om, asa cum il primeste televizorul: fara diacritice, cel mult NUME_MAX; "" daca e gol."""
	return textAscii(text)[:NUME_MAX].strip()


def numeTv(text=None):
	"""Numele trimis televizorului: cel din setari sau, gol, numeImplicit()."""
	if text is None:
		try:
			text = _cfg().nume_tv.value
		except Exception:
			text = u""
	return numeAles(text) or numeImplicit()


def _inStandby():
	import sys
	m = sys.modules.get("Screens.Standby")
	return getattr(m, "inStandby", None) is not None


def _seOpreste():
	"""True cat fereastra de oprire / repornire (TryQuitMainloop) e deschisa."""
	import sys
	m = sys.modules.get("Screens.Standby")
	return bool(getattr(m, "inTryQuitMainloop", False))


def _uptime():
	"""Secundele de la pornirea sistemului (/proc/uptime), sau None."""
	try:
		with io.open((RADACINA or "") + "/proc/uptime", "r", encoding="ascii") as f:
			return float(f.read(64).split()[0])
	except Exception:
		return None


def _trezitDeCeas():
	"""True cand receptorul a pornit singur, de la ceas (temporizator); citirea pastrata de Tools.StbHardware."""
	try:
		from Tools.StbHardware import getFPWasTimerWakeup
		return bool(getFPWasTimerWakeup())
	except Exception:
		return False


def _standbyReceptor():
	"""Receptorul in standby, ca la tasta POWER: prin coada notificarilor (o fereastra deschisa pe televizor nu e
	rupta; la trezire Screens/Standby.stergeStandbyDinCoada scoate o cerere ramasa)."""
	if _inStandby():
		return False
	from Tools import Notifications
	from Screens.Standby import Standby
	if any(n[1] is Standby for n in Notifications.notifications):
		return False
	Notifications.AddNotification(Standby)
	return True


def _trezesteReceptorul():
	"""Iesirea din standby, ca la tasta POWER pe ecranul de standby."""
	import sys
	m = sys.modules.get("Screens.Standby")
	ecran = getattr(m, "inStandby", None)
	if ecran is None:
		return False
	ecran.Power()
	return True


def _faTimer(functie):
	from enigma import eTimer
	t = eTimer()
	t.callback.append(functie)
	return t


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_standby si SystemInfo HdsHdmiStandby / HdsCec (randurile din setup.xml)."""
	from Components.config import config
	if "hds_standby" not in config.content.items:
		from Components.config import ConfigSubsection, ConfigYesNo, ConfigText
		c = ConfigSubsection()
		config.hds_standby = c
		c.hdmi_oprit = ConfigYesNo(default=True)      # „Oprește HDMI în standby”
		c.cec_stinge = ConfigYesNo(default=False)     # „Stinge și televizorul (CEC)”
		c.cec_porneste = ConfigYesNo(default=False)   # „Pornește televizorul la trezire (CEC)”
		c.nume_tv = ConfigText(default="", fixed_size=False)   # "Numele receptorului pe televizor" (gol = modelul)
		c.cec_telecomanda = ConfigYesNo(default=True)  # "Comanda din telecomanda televizorului" (tastele prin CEC)
		c.cec_lg_simplink = ConfigYesNo(default=False)  # „Legătura LG SIMPLINK (toate tastele)” (vezi COMPATIBILITATE_TV)
		# pentru /setari (setari_web.py): textul se poate schimba si din web, cel mult NUME_MAX caractere; gol arata
		# numele implicit
		c.nume_tv.web_text_max = NUME_MAX
		c.nume_tv.web_text_gol = numeImplicit
		try:
			_migreaza(config, c)
		except Exception as e:
			_jurnal("setarile vechi CEC: %r" % (e,))
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsHdmiStandby"] = os.path.exists(IESIRE)
		SystemInfo["HdsCec"] = os.path.exists(CEC)
		# meniul „Standby și televizorul” (menu.xml): oricare din cele doua. Vu+ 4K n-au /proc/stb/hdmi/output, dar au
		# CEC (/dev/hdmi_cec); fara asta tot meniul era ascuns, cu randurile CEC cu tot (0.7.4)
		SystemInfo["HdsStandbyTv"] = SystemInfo["HdsHdmiStandby"] or SystemInfo["HdsCec"]
	except Exception as e:
		_jurnal("SystemInfo: %r" % (e,))


def _salvateVechi(config):
	"""Valorile salvate ale ecranului vechi de preferinte CEC (config.hds_hdmicec), ca text."""
	vechi = config.content.items.get("hds_hdmicec")
	if vechi is not None:
		rez = {}
		for nume in ("activ", "porneste_tv"):
			el = vechi.content.items.get(nume)
			if el is not None and el.saved_value is not None:
				rez[nume] = str(el.saved_value)
		return rez
	rez = {}
	for k, v in (config.content.stored_values.get("hds_hdmicec") or {}).items():
		if isinstance(v, tuple):
			v = v[0] if v else None
		if v is not None and not isinstance(v, dict):
			rez[k] = str(v)
	return rez


def _migreaza(config, c):
	"""Cine a pornit „Activează HDMI-CEC” cu „Pornește și TV-ul la ieșirea din standby” in ecranul vechi primeste
	„Pornește televizorul la trezire (CEC)”, pana salveaza altceva (nimic nu se scrie aici)."""
	if c.cec_porneste.saved_value is not None:
		return
	vechi = _salvateVechi(config)
	da = ("true", "1", "yes")
	if vechi.get("activ", "").strip().lower() in da and vechi.get("porneste_tv", "true").strip().lower() in da:
		c.cec_porneste.value = True


def _cfg():
	from Components.config import config
	initConfig()
	return config.hds_standby


def telecomandaPornita():
	"""Setarea "Comanda din telecomanda televizorului" (tastele televizorului prin CEC)."""
	try:
		return bool(_cfg().cec_telecomanda.value)
	except Exception:
		return False


def legaturaPornita(fel):
	"""Legatura proprie a televizorului (COMPATIBILITATE_TV) aleasa de om: la LG setarea „Legătura LG SIMPLINK (toate
	tastele)”, Nu din fabrica (cu ea LG arata receptorul ca aparat LG, nu cu numele lui)."""
	if fel != "lg":
		return True
	try:
		return bool(_cfg().cec_lg_simplink.value)
	except Exception:
		return False


def vfdDorit():
	"""„1” daca afisajul din fata arata ceva in standby (ora, ora si data, inregistrarea), „0” daca e ales „nimic”.
	Fara afisajul nostru: „1” (afisajul ramane cum l-a lasat driverul)."""
	try:
		from Components import HdsAfisaj
		return "1" if HdsAfisaj.arataInAsteptare() else "0"
	except Exception:
		return "1"


# ---------------------------------------------------------------- CEC

class CerereCec(object):
	"""O cerere pentru firul de lucru CEC: functie(*argumente) acolo, dupa(rezultat, eroare) pe firul principal. `ce`
	spune in jurnal ce a ramas in driver; pornit si durata sunt pe ceasul firului."""

	def __init__(self, ce, functie, argumente, dupa):
		self.ce, self.functie, self.argumente, self.dupa = ce, functie, argumente, dupa
		self.pornit = None
		self.durata = 0.0
		self.rezultat = self.eroare = self.raspuns = None
		import threading
		self.gata = threading.Event()


class FirCec(object):
	"""Familia libreader: firul de lucru CEC. Un singur fir de fundal (daemon) face, pe rand, cererile puse de Cec._cere:
	toate apelurile pe nodul CEC si citirea adresei din driverul HDMI. Un apel ramas in driver tine firul pe loc; Cec
	opreste atunci CEC (opreste(): cererile ramase nu se mai fac), iar firul nu-l asteapta nimeni, nici la iesirea
	interfetei."""

	def __init__(self, ceas):
		import queue
		import threading
		self.ceas = ceas
		self.oprit = False
		self.coada = queue.Queue()
		self.fir = threading.Thread(target=self._lucreaza, name="HdsCecLucru")
		self.fir.daemon = True
		self.fir.start()

	def pune(self, cerere):
		self.coada.put(cerere)

	def opreste(self):
		self.oprit = True

	def _lucreaza(self):
		while True:
			c = self.coada.get()
			if not self.oprit:
				c.pornit = self.ceas()
				try:
					c.rezultat = c.functie(*c.argumente)
				except Exception as e:
					c.eroare = e
				c.durata = self.ceas() - c.pornit
			c.gata.set()


# functiile de mai jos ruleaza pe firul de lucru CEC (in stivele interfetei numele lor spune unde a ramas firul)

def _deschideNodul(deschide, ioctl, cale):
	"""open() pe nod (porneste CEC in driver), apoi golirea cozii. Intoarce (fd, eroarea golirii sau None)."""
	fd = deschide(cale, os.O_RDWR | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0))
	try:
		ioctl(fd, CEC_GOLESTE, 0)
	except Exception as e:
		return fd, e
	return fd, None


def _adreseNod(ioctl, fd):
	"""Adresa fizica din EDID-ul televizorului (/proc/msp/hdmi0_sink, citit direct: nu e firul principal) si octetii
	lui ioctl 1 (sau eroarea lui)."""
	sink = adresaDinSink()
	buf = bytearray(4)
	try:
		ioctl(fd, CEC_ADRESA, buf)
	except Exception as e:
		return sink, e
	return sink, buf


def _citesteMesajNod(citeste, fd):
	"""Un mesaj din driverul familiei libreader: antetul (primul octet, lungimea), apoi exact lungimea lui (driverul da
	EFAULT si lasa mesajul in coada la o cerere mai mare decat mesajul). b"" daca nu e nimic."""
	antet = bytearray(citeste(fd, 2) or b"")
	if len(antet) < 2 or not 1 <= antet[1] <= CEC_LUNGIME_MAX:
		return bytes(antet)      # gol, sau un inceput de neinteles: _inregistrare goleste coada
	return bytes(antet) + bytes(bytearray(citeste(fd, antet[1]) or b""))


def _pasCitireNod(citeste, poll, ioctl, fd, cuPoll, adrese, fir):
	"""Un pas al citirii pe firul de lucru CEC (familia libreader). Cu cuPoll un mesaj se citeste numai cand poll(0) il
	arata, apoi iar poll(0) inaintea urmatorului: o citire pe coada goala asteapta in driver. Cel mult CITIRI_PE_PAS
	mesaje (_citesteMesajNod). Fara cuPoll sau cu un poll care nu merge (None), mesaj dupa mesaj pana la primul gol. Cu
	`adrese` si mesaje citite, si adresele (_adreseNod), ca raspunsurile la ele sa plece cu adresa logica buna. Intoarce
	(datele, eroarea lui read(), adresele)."""
	date = bytearray()
	eroare = None
	for _i in range(CITIRI_PE_PAS):
		if fir.oprit or (cuPoll and poll(fd) is False):
			break
		try:
			d = _citesteMesajNod(citeste, fd)
		except (IOError, OSError) as e:
			eroare = e
			break
		if not d:
			break
		date.extend(bytearray(d))
	if adrese and date and not fir.oprit:
		return bytes(date), eroare, _adreseNod(ioctl, fd)
	return bytes(date), eroare, None


class Cec(object):
	"""Nodul CEC al driverului (deschis tot timpul pe un receptor care il are): numele pe televizor, raspunsurile la
	intrebarile televizorului, trimiterea si starea ultimului mesaj."""

	def __init__(self, deschide=None, scrieFd=None, inchide=None, ioctl=None, ceas=None, timer=None, citesteFd=None,
			nume=None, inStandby=None, telecomanda=None, injecteaza=None, panou=None, poll=None, dupaPoll=None,
			inFir=None):
		self.deschideFd = deschide or os.open
		self.pollFd = poll or areDate
		self.dupaPoll = dupaPoll     # None = aflat la deschidere (citireDupaPoll); False dupa un poll care a mintit
		self.citireSigura = None     # cand s-a facut ultima citire de control (familia libreader)
		self.inFir = inFir           # None = ca dupaPoll, aflat o data: apelurile pe nod in firul de lucru CEC
		self.blocat = False          # un apel in driver nu s-a intors: CEC oprit pana la repornirea interfetei
		self._lucru = None           # firul de lucru CEC (FirCec), pornit la prima cerere
		self._cereri = []            # cererile puse firului de lucru, cu rezultatul neluat inca (in ordine)
		self._iau = False            # _iaRezultatele in curs (un dupa(...) care pune alta cerere nu o reia)
		self._citireInCoada = False  # un pas al citirii e la firul de lucru (cel mult unul)
		self._seDeschide = False     # deschiderea e la firul de lucru
		self.scrieFd = scrieFd or os.write
		self.inchideFd = inchide or os.close
		self.citesteFd = citesteFd or os.read
		self.ioctl = ioctl
		self.ceas = ceas or time.time
		self.ceasLucru = ceas or time.monotonic   # cat sta un apel in driver (un salt al orei nu opreste CEC)
		self.faceTimer = timer or _faTimer
		self.nume = nume or numeTv
		self.inStandby = inStandby or _inStandby
		self.fd = None
		self.timerAnunt = None
		self.timerCitire = None
		self.incercariAnunt = 0
		self.tampon = bytearray()
		self.ultimul = None          # {"mesaj", "cand", "trimis"}
		self.raspunde = None         # True = ultimul write a trimis, False = a intors 0 sau a cazut
		self.adresa = None
		self.logica = None           # adresa logica data de driver (ioctl 1)
		self.primite = 0             # mesajele primite de la deschidere
		self.ultimaPrimire = None    # {"mesaj", "cand"}
		self.numeTrimis = None       # {"nume", "cand", "trimis"}
		self.numeCerut = None        # cand a cerut televizorul numele ultima oara (<Give OSD Name>)
		self.telecomanda = telecomanda or telecomandaPornita
		self.injecteaza = injecteaza or _injecteaza
		self.panou = panou or deschidePanou
		self.activ = None            # televizorul arata intrarea receptorului: True, False (stiut ca nu) sau None (nu se
		                             # stie: la pornire, pana vine un mesaj); din mesajele CEC sau din raspunsul nostru
		self.sursaIntrebata = False  # <Request Active Source> trimis dupa primul anunt bun (o data)
		self.trezitLa = None         # cand s-a trezit receptorul ultima oara (ceasul monoton; pauza la <Standby>)
		self.standbyTv = None        # functia care pune receptorul in standby (probele o inlocuiesc)
		self.trezesteReceptorul = None   # functia care trezeste receptorul (probele o inlocuiesc)
		self.activLaStandby = False  # eram sursa la intrarea in standby, si nimic nu a spus altfel intre timp
		self.meniuActiv = True       # <Menu Status> trimis televizorului
		self.codTv = None            # codul de producator al televizorului (3 octeti), cand se stie
		self.codTvIntrebat = None    # cand l-am intrebat ultima oara
		self.tastaTinuta = None      # tasta receptorului apasata acum de pe telecomanda televizorului
		self.okAsteapta = False      # OK apasat, inca nehotarat: scurt (OK) sau tinut (panoul)
		self.okLung = False
		self.timerOk = None
		self.timerEliberare = None
		self.ultimaTasta = None      # {"ui", "cod", "cand"}
		self.stareTv = None          # ultimul <Report Power Status> al televizorului (0 pornit, 1 standby, 2/3 in trecere)
		self.tvPornitLa = None       # ceasul monoton al ultimului semn ca televizorul e pornit (stare, tasta, alegerea noastra)
		self.tvNepornitLa = None     # ceasul monoton al ultimului <Report Power Status> „nu e pornit” (standby, in trecere)
		self.altaSursaLa = None      # ceasul monoton al ultimului mesaj care a spus ca televizorul arata altceva (sau s-a stins)
		self.aprindereActiva = False  # StandbyTv incearca acum sa aprinda televizorul (un <Standby> de la el nu ne stinge)
		self.jurnalCec = []          # jurnalul CEC, cel mult JURNAL_CEC_MAX intrari (cele mai vechi ies)
		self.golite = 0              # golirile cozii driverului dupa un inceput de neinteles
		self.timerJurnalTmp = None   # scrierea jurnalului CEC in JURNAL_TMP (asistenta), cel mult una la JURNAL_TMP_MS
		self.jurnalTmpAsteapta = False

	def _noteaza(self, fel, **campuri):
		"""O intrare in jurnalul CEC: ora, felul (primit, trimis, tasta, golit) si campurile date."""
		try:
			campuri["t"] = round(self.ceas(), 3)
			campuri["fel"] = fel
			self.jurnalCec.append(campuri)
			if len(self.jurnalCec) > JURNAL_CEC_MAX:
				del self.jurnalCec[:len(self.jurnalCec) - JURNAL_CEC_MAX]
		except Exception:
			pass
		self._jurnalTmpCurand()

	def _jurnalTmpCurand(self):
		"""Jurnalul CEC in JURNAL_TMP la JURNAL_TMP_MS dupa prima intrare noua (o rafala de taste = o scriere)."""
		if self.jurnalTmpAsteapta:
			return
		try:
			if self.timerJurnalTmp is None:
				self.timerJurnalTmp = self.faceTimer(self.scrieJurnalTmp)
			self.timerJurnalTmp.start(JURNAL_TMP_MS, True)
			self.jurnalTmpAsteapta = True
		except Exception as e:
			_jurnal("jurnalul CEC in %s: %r" % (JURNAL_TMP, e), "cec-jurnal-tmp")

	def textJurnal(self):
		"""Jurnalul CEC ca text: un rand de stare, apoi ultimele JURNAL_TMP_RANDURI intrari (ora, felul, campurile). Il
		citeste asistenta (op „citeste” pe JURNAL_TMP_REL): ce primeste si ce trimite receptorul, fara web si fara SSH."""
		def ora(t):
			try:
				return time.strftime("%H:%M:%S", time.localtime(t)) + (".%03d" % int(round((t % 1) * 1000) % 1000))
			except Exception:
				return str(t)
		setari = {}
		try:
			c = _cfg()
			setari = {"stinge": bool(c.cec_stinge.value), "porneste": bool(c.cec_porneste.value),
				"telecomanda": bool(c.cec_telecomanda.value)}
		except Exception:
			pass
		stare = [("deschis", self.fd is not None), ("blocat", bool(self.blocat)), ("libreader", self.inFir),
			("logica", self.logica), ("adresa", textAdresa(self.adresaStiuta())),
			("activ", self.activ), ("cod_tv", hexa(bytearray(self.codTv)) if self.codTv else None),
			("primite", self.primite), ("golite", self.golite)] + sorted(setari.items())
		randuri = [u"# HD Satelit: jurnalul CEC (ultimele %d intrari), scris la %s" % (JURNAL_TMP_RANDURI, ora(self.ceas())),
			u"stare: " + u" ".join(u"%s=%s" % (k, v) for k, v in stare)]
		for x in self.jurnalCec[-JURNAL_TMP_RANDURI:]:
			campuri = u" ".join(u"%s=%s" % (k, x[k]) for k in sorted(x) if k not in ("t", "fel"))
			randuri.append(u"%s %s %s" % (ora(x.get("t", 0)), x.get("fel", u"?"), campuri))
		return u"\n".join(randuri) + u"\n"

	def scrieJurnalTmp(self):
		"""Scrie JURNAL_TMP (fisier nou, apoi mutat peste cel vechi: cine citeste nu vede niciodata o jumatate)."""
		self.jurnalTmpAsteapta = False
		try:
			nou = JURNAL_TMP + ".nou"
			with io.open(nou, "w", encoding="utf-8") as f:
				f.write(self.textJurnal())
			os.replace(nou, JURNAL_TMP)
			return True
		except Exception as e:
			_jurnal("jurnalul CEC in %s: %r" % (JURNAL_TMP, e), "cec-jurnal-tmp")
			return False

	def _tasta(self, cod, steag):
		"""O tasta a receptorului data mai departe (injecteaza), trecuta si in jurnal."""
		self._noteaza("tasta", cod=cod, steag=steag)
		self.injecteaza(cod, steag)

	def _ioctlPe(self, fd, cerere, arg=0):
		if self.ioctl is not None:
			return self.ioctl(fd, cerere, arg)
		import fcntl
		return fcntl.ioctl(fd, cerere, arg)

	def _ioctl(self, cerere, arg=0):
		return self._ioctlPe(self.fd, cerere, arg)

	def deschis(self):
		return self.fd is not None

	def deschide(self):
		if self.fd is not None:
			return True
		if not os.path.exists(CEC):
			return False
		if self._cuFir():
			return self._deschideInFir()
		try:
			self.fd = self.deschideFd(CEC, os.O_RDWR | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0))
		except OSError as e:
			_jurnal("nu pot deschide %s: %s" % (CEC, e), "cec-deschide")
			self.fd = None
			return False
		_jurnal("CEC pornit (%s)" % CEC, "cec-pornit")
		self.tampon = bytearray()
		self.incercariAnunt = 0
		try:
			self._ioctl(CEC_GOLESTE)
		except Exception as e:
			_jurnal("golirea cozii CEC: %r" % (e,), "cec-goleste")
		self._pornesteAnuntul()
		self._pornesteCitirea()
		return True

	def _deschideInFir(self):
		"""deschide() pe familia libreader: open() si golirea cozii le face firul de lucru CEC. Ceasul citirii porneste
		acum (pasii lui iau raspunsul, si opresc CEC daca open() ramane in driver), anuntul cand nodul e deschis.
		Intoarce True / False daca raspunsul a venit pe loc, altfel None."""
		if self._seDeschide or self.blocat:
			return None
		self._seDeschide = True
		self._pornesteCitirea()
		return self._cere("deschiderea lui", _deschideNodul, (self.deschideFd, self._ioctlPe, CEC), self._deschisInFir)

	def _deschisInFir(self, rezultat, eroare):
		if not self._seDeschide:
			# inchide() intre timp: nodul deschis acum se inchide la loc
			if eroare is None:
				self._cere("inchiderea lui", self.inchideFd, (rezultat[0],), self._inchis)
			return False
		self._seDeschide = False
		if eroare is not None:
			_jurnal("nu pot deschide %s: %s" % (CEC, eroare), "cec-deschide")
			self._opresteTimer(self.timerCitire)
			return False
		self.fd, eroareGolire = rezultat
		_jurnal("CEC pornit (%s)" % CEC, "cec-pornit")
		self.tampon = bytearray()
		self.incercariAnunt = 0
		if eroareGolire is not None:
			_jurnal("golirea cozii CEC: %r" % (eroareGolire,), "cec-goleste")
		self._pornesteAnuntul()
		return True

	def _pornesteAnuntul(self):
		try:
			if self.timerAnunt is None:
				self.timerAnunt = self.faceTimer(self.anunta)
			self.timerAnunt.start(ANUNT_MS, True)
		except Exception as e:
			_jurnal("anuntul CEC: %r" % (e,), "cec-anunt")

	def _pornesteCitirea(self):
		try:
			if self.timerCitire is None:
				self.timerCitire = self.faceTimer(self._pasCitire)
			self.timerCitire.start(self.intervalCitire(), False)
		except Exception as e:
			_jurnal("citirea CEC: %r" % (e,), "cec-citire-timer")

	def inchide(self):
		self.opresteTastele()
		for t in (self.timerAnunt, self.timerCitire):
			if t is not None:
				try:
					t.stop()
				except Exception:
					pass
		self.tampon = bytearray()
		self._seDeschide = False
		if self.fd is None:
			return
		fd, self.fd = self.fd, None
		if self._cuFir():
			# familia libreader: close() il face firul de lucru CEC, dupa cererile din coada; nu-l asteapta nimeni (dupa
			# oprirea CEC nici nu se mai face: ar astepta acelasi driver)
			self._cere("inchiderea lui", self.inchideFd, (fd,), self._inchis)
		else:
			try:
				self.inchideFd(fd)
			except OSError as e:
				_jurnal("inchiderea CEC: %s" % e, "cec-inchide")
		_jurnal("CEC oprit", "cec-oprit")

	def _inchis(self, rezultat, eroare):
		if eroare is not None:
			_jurnal("inchiderea CEC: %s" % eroare, "cec-inchide")

	def _dinIoctl(self, buf):
		"""Octetii lui ioctl 1: [adresa logica, adresa fizica (doi octeti), adresa logica]. Tine minte adresa logica;
		intoarce adresa fizica (doi octeti) sau None."""
		if 0x01 <= buf[0] <= 0x0E:     # 0 e televizorul, 0x0F nicio adresa: driverul inca nu si-a gasit una
			self.logica = buf[0]
		if (buf[1] or buf[2]) and not (buf[1] == 0xFF and buf[2] == 0xFF):     # 0.0.0.0 si f.f.f.f: nicio adresa
			return bytes(buf[1:3])
		return None

	def _adreseDinDriver(self):
		"""ioctl 1: tine minte adresa logica; intoarce adresa fizica (doi octeti) sau None. Pe familia libreader nimic
		aici: adresele le citeste firul de lucru CEC (la anunt si cu mesajele primite cat nu se stiu)."""
		if self.fd is None or self._cuFir():
			return None
		try:
			buf = bytearray(4)
			self._ioctl(CEC_ADRESA, buf)
		except Exception as e:
			_jurnal("adresa CEC din driver: %r" % (e,), "cec-adresa")
			return None
		return self._dinIoctl(buf)

	def _adreseVenite(self, adrese):
		"""(adresa din EDID, octetii lui ioctl 1 sau eroarea lui), de la firul de lucru: adresa logica si adresa fizica
		tinute minte. Intoarce adresa fizica stiuta."""
		a, buf = adrese
		if isinstance(buf, Exception):
			_jurnal("adresa CEC din driver: %r" % (buf,), "cec-adresa")
		elif buf is not None:
			dinDriver = self._dinIoctl(buf)
			if a is None:
				a = dinDriver
		if a is not None:
			self.adresa = a
		return self.adresa

	def _cereAdresele(self, dupa=None):
		"""Familia libreader: adresele citite de firul de lucru CEC; dupa(adresa fizica) cand vin. Intoarce ce intoarce
		dupa (fara dupa, adresa fizica) daca au venit pe loc, altfel None."""
		def venite(adrese, eroare):
			if eroare is not None:
				_jurnal("adresa CEC: %r" % (eroare,), "cec-adresa")
				a = self.adresa
			else:
				a = self._adreseVenite(adrese)
			return dupa(a) if dupa is not None else a
		return self._cere("citirea adreselor din", _adreseNod, (self._ioctlPe, self.fd), venite)

	def adresaFizica(self):
		"""Adresa fizica (doi octeti): din EDID-ul televizorului, altfel ioctl 1 al driverului; None daca nu se stie. Pe
		familia libreader, cea tinuta minte; pana la prima citire buna o cere firului de lucru (vine pe loc sau mai
		tarziu)."""
		if self._cuFir():
			if self.adresa is None and self.fd is not None and not self.blocat:
				return self._cereAdresele()
			return self.adresa
		a = adresaDinSink()
		if a is None:
			a = self._adreseDinDriver()
		if a is not None:
			self.adresa = a
		return a

	def adresaStiuta(self):
		"""Pentru pagina web: adresa fizica tinuta minte; pe celelalte familii, daca nu e, cea din EDID, citita acum."""
		if self.adresa is not None or self._cuFir():
			return self.adresa
		return adresaDinSink()

	def trimite(self, destinatie, cod, parametri=b"", dupa=None):
		"""Un mesaj; True daca driverul l-a trimis (write > 0). Coada mesajelor primite nu se goleste aici: o intrebare
		a televizorului venita intre doi pasi ai citirii trebuie sa primeasca raspuns. dupa(trimis), daca e dat, se
		cheama cu rezultatul (si cand nodul e inchis sau CEC oprit: False) si trimite intoarce ce intoarce el. Pe familia
		libreader scrierea o face firul de lucru CEC: cat e inca acolo, trimite intoarce None, iar rezultatul se noteaza
		(si dupa se cheama) la un pas urmator al citirii."""
		if self.fd is None or self._oprit():
			return dupa(False) if dupa is not None else False
		date = cadru(destinatie, cod, parametri)
		if self._cuFir():
			return self._cere("scrierea in", self.scrieFd, (self.fd, date),
				lambda n, eroare: self._scris(destinatie, cod, date, n, eroare, dupa))
		try:
			n, eroare = self.scrieFd(self.fd, date), None
		except OSError as e:
			n, eroare = 0, e
		return self._scris(destinatie, cod, date, n, eroare, dupa)

	def _scris(self, destinatie, cod, date, n, eroare=None, dupa=None):
		"""Rezultatul scrierii unui mesaj (n octeti scrisi sau eroarea), notat in jurnal si in starea ultimului mesaj."""
		if eroare is not None:
			_jurnal("trimiterea CEC %s: %s" % (NUME_MESAJ.get(cod, hex(cod)), eroare), "cec-trimite")
			n = 0
		trimis = bool(n and n > 0)
		self._noteaza("trimis", catre=destinatie & 0x0F, mesaj=NUME_MESAJ.get(cod, "%02x" % cod),
			date=hexa(bytearray(date)[2:]), ok=trimis)
		self.ultimul = {"mesaj": NUME_MESAJ.get(cod, "%02x" % cod), "cand": self.ceas(), "trimis": trimis}
		self.raspunde = trimis
		if not trimis:
			_jurnal("CEC: mesajul %s nu s-a trimis (televizorul nu raspunde la CEC)" % self.ultimul["mesaj"],
				"cec-netrimis")
		return dupa(trimis) if dupa is not None else trimis

	def trimiteNumele(self, destinatie=CEC_TV, dupa=None):
		"""<Set OSD Name> cu numele de acum (numeTv: cel din setari sau modelul simplificat); dupa(trimis) ca la
		trimite."""
		try:
			nume = self.nume() or NUME_REZERVA
		except Exception as e:
			_jurnal("numele pe televizor: %r" % (e,), "cec-nume")
			nume = NUME_REZERVA
		nume = numeAles(nume) or NUME_REZERVA

		def trimis(ok):
			self.numeTrimis = {"nume": nume, "cand": self.ceas(), "trimis": ok}
			if ok:
				_jurnal("numele pe televizor: %s" % nume, "cec-nume-trimis")
			return dupa(ok) if dupa is not None else ok
		return self.trimite(destinatie, CEC_SET_OSD_NAME, nume.encode("ascii", "replace"), dupa=trimis)

	def anunta(self):
		"""Dupa deschidere: <Report Physical Address> catre toti si numele catre televizor; din nou la ANUNT_REPETA_MS
		cat CEC nu e gata (write = 0), de cel mult ANUNT_INCERCARI ori. Pe familia libreader adresele le citeste firul de
		lucru CEC, iar anuntul pleaca dupa ele."""
		if self.fd is None or self._oprit():
			return
		if self._cuFir():
			self._cereAdresele(self._anuntaLa)
			return
		self._adreseDinDriver()
		self._anuntaLa(self.adresaFizica())

	def _anuntaLa(self, a):
		"""Anuntul cu adresa fizica `a` (None: fara <Report Physical Address>); restul dupa scrierea numelui."""
		if a is not None:
			self.trimite(CEC_TOTI, CEC_REPORT_PHYSICAL_ADDRESS, a + bytes(bytearray([CEC_TIP_PLAYBACK])))
		self.trimiteNumele(dupa=self._dupaAnunt)

	def _dupaAnunt(self, ok):
		"""Numele a plecat (ok) sau nu (CEC inca negata): anuntul din nou, apoi codul televizorului si sursa activa.
		Nimic dupa oprirea CEC sau inchiderea nodului (ceasul anuntului ramane oprit)."""
		if self.fd is None or self.blocat:
			return
		if not ok and self.incercariAnunt < ANUNT_INCERCARI:
			self.incercariAnunt += 1
			try:
				self.timerAnunt.start(ANUNT_REPETA_MS, True)
			except Exception as e:
				_jurnal("anuntul CEC: %r" % (e,), "cec-anunt")
			return
		try:
			if self.codTv is None and self.telecomanda():
				self.intreabaCodTv()        # televizorul poate sa nu mai intrebe el (si-a tinut minte aparatul)
		except Exception as e:
			_jurnal("codul televizorului: %r" % (e,), "cec-cod-tv")
		self.intreabaSursa()
		self.sursaDacaTvPeNoi()

	def intreabaSursa(self):
		"""O data, dupa primul anunt bun, cat nu se stie ce arata televizorul: <Request Active Source> catre toti. Aparatul
		de pe ecran (sau televizorul, pe tunerul lui) raspunde cu <Active Source>; o adresa care nu e a noastra spune ca
		televizorul arata altceva (activ = False), deci la standby si la oprire pleaca numai <Inactive Source>."""
		if self.sursaIntrebata or self.activ is not None or self.fd is None:
			return False
		self.sursaIntrebata = True
		try:
			return self.trimite(CEC_TOTI, CEC_REQUEST_ACTIVE_SOURCE)
		except Exception as e:
			_jurnal("intrebarea sursei active: %r" % (e,), "cec-sursa")
			return False

	def sursaDacaTvPeNoi(self):
		"""<Active Source> numai cand mesajele spun ca televizorul e pe intrarea receptorului (sursa acum, sau la
		intrarea in standby fara alt mesaj de atunci) si tastele televizorului sunt pornite: televizorul afla cui
		trimite tastele, fara sa fie aprins sau mutat. La pornire, fara mesaje, nimic."""
		try:
			era = self.activ or self.activLaStandby
			self.activLaStandby = False
			if self.fd is not None and self.telecomanda() and not self.inStandby() and era:
				return self.anuntaSursaActiva()
		except Exception as e:
			_jurnal("sursa activa: %r" % (e,), "cec-sursa")
		return False

	# ---- mesajele primite

	def _pasCitire(self):
		try:
			self.citeste()
		except Exception as e:
			_jurnal("citirea CEC: %r" % (e,), "cec-citire")

	def citeste(self):
		"""Tot ce e acum in coada driverului, impartit in inregistrari; fiecare primeste raspunsul ei. Intoarce cate
		inregistrari s-au citit. Nu blocheaza: read() da 0 cand coada e goala (pe familia libreader citirea o face firul
		de lucru CEC, vezi _citesteInFir)."""
		if self.blocat:
			return 0
		if self._cereri or (self.fd is not None and self._cuFir()):
			return self._citesteInFir()
		if self.fd is None:
			return 0
		control = False
		if self.dupaPoll:
			are = self.pollFd(self.fd)
			if are is False:
				acum = self.ceas()
				if self.citireSigura is not None and 0 <= (acum - self.citireSigura) * 1000 < CITIRE_SIGURA_MS:
					return 0
				self.citireSigura = acum
				control = True
		inainte = len(self.tampon)
		for _i in range(CITIRI_PE_PAS):
			try:
				date = self.citesteFd(self.fd, 256)
			except (IOError, OSError) as e:
				if getattr(e, "errno", None) not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
					_jurnal("citirea CEC: %s" % e, "cec-citeste")
				break
			if not date:
				break
			self.tampon.extend(bytearray(date))
		if control and len(self.tampon) > inainte:
			self.dupaPoll = False
			_jurnal("CEC: poll() nu a aratat un mesaj primit; citirea revine la fiecare pas", "cec-poll")
		return self._imparte()

	def _imparte(self):
		"""Inregistrarile intregi din tampon, fiecare cu raspunsul ei; intoarce cate au fost."""
		n = 0
		while True:
			r = self._inregistrare()
			if r is None:
				break
			n += 1
			try:
				self._primit(*r)
			except Exception as e:
				_jurnal("raspunsul CEC: %r" % (e,), "cec-raspuns")
		return n

	def _citesteInFir(self):
		"""citeste() pe familia libreader. Pasul citirii (poll, read, adresele cat nu se stiu) il face firul de lucru CEC,
		cel mult unul odata; aici se iau rezultatele gata (si raspunsul deschiderii), se verifica daca un apel a ramas
		in driver si se impart inregistrarile. Firul principal nu atinge nodul."""
		self._iaRezultatele()
		if self._oprit():
			return 0
		if self.fd is not None and not self._citireInCoada:
			adrese = self.logica is None or self.adresa is None
			self._citireInCoada = True
			self._cere("citirea din", _pasCitireNod, (self.citesteFd, self.pollFd, self._ioctlPe, self.fd,
				bool(self.dupaPoll), adrese, self._firDeLucru()), self._citit, asteapta=False)
		return self._imparte()

	def _citit(self, rezultat, eroare):
		"""Rezultatul unui pas al citirii facut de firul de lucru CEC: datele in tampon, adresele."""
		self._citireInCoada = False
		if eroare is not None:
			_jurnal("citirea CEC: %r" % (eroare,), "cec-citire")
			return
		date, eroareCitire, adrese = rezultat
		if eroareCitire is not None and getattr(eroareCitire, "errno", None) not in (errno.EAGAIN, errno.EWOULDBLOCK,
				errno.EINTR):
			_jurnal("citirea CEC: %s" % eroareCitire, "cec-citeste")
		if adrese is not None:
			self._adreseVenite(adrese)
		if date and self.fd is not None:
			self.tampon.extend(bytearray(date))

	def _cuFir(self):
		"""Familia libreader: toate apelurile pe nod trec prin firul de lucru CEC (inFir, aflat o singura data, inainte
		de primul apel)."""
		if self.inFir is None:
			if self.dupaPoll is None:
				self.dupaPoll = citireDupaPoll()
			self.inFir = bool(self.dupaPoll)
		return self.inFir

	def _firDeLucru(self):
		if self._lucru is None:
			self._lucru = FirCec(self.ceasLucru)
		return self._lucru

	def _cere(self, ce, functie, argumente, dupa, asteapta=True):
		"""Familia libreader: functie(*argumente) pe firul de lucru CEC, dupa cererile puse inainte; dupa(rezultat,
		eroare) pe firul principal, cand s-a terminat. Cu firul liber, firul principal asteapta cel mult CITIRE_ASTEAPTA_S
		(un apel obisnuit ia sub o milisecunda); altfel rezultatul se ia la un pas urmator al citirii. Intoarce ce intoarce
		dupa, sau None cand cererea nu s-a terminat inca (ori CEC e oprit si nu s-a mai pus).
		Cu asteapta=False (pasul citirii, la CITIRE_MS, rezultatul nu merge la apelant) firul principal nu asteapta deloc:
		rezultatul il ia un ceas dupa PRELUARE_MS (_preia), deci mesajele primite (si tastele de pe telecomanda
		televizorului) vin tot in cateva milisecunde, nu la pasul urmator. Raportul 388460 (SF8008, procesorul plin de un
		plugin): asteptarea de 10 ms tinea firul principal 10-19 ms pe pas in medie, cu varfuri de 90-170 ms, fiindca dupa
		ea firul principal isi recapata GIL-ul tarziu (masurat pe Linux cu Python 3.14 si 1-3 fire ocupate)."""
		if self._oprit():
			return None
		c = CerereCec(ce, functie, argumente, dupa)
		liber = not self._cereri
		self._cereri.append(c)
		self._firDeLucru().pune(c)
		if liber and not self._iau:
			if asteapta or not self._preiaDupa(PRELUARE_MS):
				c.gata.wait(CITIRE_ASTEAPTA_S)
				self._iaRezultatele()
		return c.raspuns

	def _preiaDupa(self, ms):
		"""Ceasul (unul singur) care ia rezultatele firului de lucru CEC dupa `ms`. False daca nu se poate face un ceas
		(fara eTimer, probele vechi): atunci _cere asteapta ca inainte."""
		try:
			t = getattr(self, "timerPreluare", None)
			if t is None:
				t = self.timerPreluare = self.faceTimer(self._preia)
			if t is None:
				return False
			t.start(ms, True)
			return True
		except Exception as e:
			_jurnal("preluarea CEC: %r" % (e,), "cec-preluare")
			return False

	def _preia(self):
		"""Rezultatele gata ale firului de lucru CEC (pasul citirii) si inregistrarile venite cu ele, pe firul principal.
		Daca firul de lucru n-a terminat inca, rezultatul il ia pasul urmator al citirii (care verifica si apelurile
		ramase in driver)."""
		try:
			self._iaRezultatele()
			if not self._oprit():
				self._imparte()
		except Exception as e:
			_jurnal("citirea CEC: %r" % (e,), "cec-citire")

	def asteaptaScrierile(self, secunde):
		"""Oprirea completa: cel mult `secunde`, pana termina firul de lucru CEC cererile puse (familia libreader), apoi
		rezultatele lor. Pe celelalte placi scrierile sunt deja facute. Intoarce True daca nu mai e nimic in lucru."""
		termen = time.monotonic() + secunde
		for c in list(self._cereri):
			ramas = termen - time.monotonic()
			if ramas <= 0 or not c.gata.wait(ramas):
				break
		self._iaRezultatele()
		return not self._cereri

	def _iaRezultatele(self):
		"""Familia libreader: rezultatele cererilor terminate de firul de lucru CEC, in ordinea lor, pana la prima
		neterminata; dupa(...) al fiecareia, pe firul principal. Un apel care a stat in driver CITIRE_BLOCATA_S sau mai
		mult opreste CEC, chiar daca s-a intors pana la urma."""
		if self._iau:
			return
		self._iau = True
		try:
			while self._cereri and self._cereri[0].gata.is_set() and not self.blocat:
				c = self._cereri.pop(0)
				if c.durata >= CITIRE_BLOCATA_S:
					self._blocheaza(c.ce, c.durata)
					break
				try:
					c.raspuns = c.dupa(c.rezultat, c.eroare)
				except Exception as e:
					_jurnal("CEC: %r" % (e,), "cec-rezultat")
		finally:
			self._iau = False

	def _oprit(self):
		"""True cand CEC e oprit; pe familia libreader il opreste acum daca apelul la care e firul de lucru nu s-a
		intors de CITIRE_BLOCATA_S."""
		if self.blocat:
			return True
		for c in self._cereri:
			if c.gata.is_set():
				continue
			if c.pornit is not None:
				durata = self.ceasLucru() - c.pornit
				if durata >= CITIRE_BLOCATA_S:
					self._blocheaza(c.ce, durata)
					return True
			break
		return False

	def _blocheaza(self, ce, durata):
		"""Un apel in driver facut de firul de lucru CEC nu s-a intors in CITIRE_BLOCATA_S: CEC oprit pana la repornirea
		interfetei, fara alte apeluri, care ar astepta acelasi driver (nici cele din coada); firul ramas in driver e de
		fundal si nu-l asteapta nimeni."""
		self.blocat = True
		self.raspunde = False
		if self._lucru is not None:
			self._lucru.opreste()
		for t in (self.timerCitire, self.timerAnunt):
			if t is not None:
				try:
					t.stop()
				except Exception:
					pass
		self._noteaza("blocat")
		_jurnal("CEC: %s %s nu s-a intors de %.1f s (driverul asteapta); CEC oprit pana la repornirea interfetei" % (
			ce, CEC, durata), "cec-blocat")

	def _inregistrare(self):
		"""(destinatia, codul, parametrii) de la inceputul tamponului, sau None daca nu e una intreaga. Un inceput de
		neinteles goleste tamponul si coada driverului."""
		b = self.tampon
		if len(b) < 2:
			return None
		dest, lung = b[0], b[1]
		if dest > 0x0F or lung < 1 or lung > CEC_LUNGIME_MAX:
			_jurnal("CEC: mesaj de neinteles (%s), coada golita" % hexa(b[:4]), "cec-stricat")
			self.golite += 1
			self._noteaza("golit", date=hexa(b[:8]))
			self.tampon = bytearray()
			try:
				if self._cuFir():
					self._cere("golirea cozii din", self._ioctlPe, (self.fd, CEC_GOLESTE, 0), lambda r, e: None)
				else:
					self._ioctl(CEC_GOLESTE)
			except Exception:
				pass
			return None
		if len(b) < 2 + lung:
			return None
		cod = b[2]
		parametri = bytes(b[3:2 + lung])
		del b[:2 + lung]
		return dest, cod, parametri

	def _destinatieRaspuns(self, dest):
		"""Cui merge raspunsul: driverul da destinatia mesajului (noi), nu sursa, deci televizorului; daca primul octet
		nu e adresa noastra, e chiar cel care a intrebat."""
		noi = self.logica if self.logica is not None else CEC_LOGICA_IMPLICITA
		return CEC_TV if dest == noi else dest

	def _primit(self, dest, cod, parametri):
		self.primite += 1
		mesaj = NUME_MESAJ.get(cod, "%02x" % cod)
		self._noteaza("primit", dest=dest, mesaj=mesaj, date=hexa(bytearray([cod]) + bytearray(parametri)))
		self.ultimaPrimire = {"mesaj": mesaj, "cand": self.ceas()}
		_jurnal("CEC primit: %s (%s)" % (mesaj, hexa(bytearray([dest, cod]) + bytearray(parametri))), "cec-primit")
		if cod in (CEC_SET_STREAM_PATH, CEC_ROUTING_CHANGE, CEC_ROUTING_INFORMATION) and len(parametri) >= 2:
			self._caleNoua(bytes(parametri[-2:]))
			return
		if cod == CEC_ACTIVE_SOURCE and len(parametri) >= 2:
			if bytes(parametri[:2]) != self.adresaFizica():
				self.activ = False      # alt aparat (sau televizorul insusi) e pe ecran
				self._altaSursa()
				self.activLaStandby = False
				self.opresteTastele()
			return
		if cod == CEC_REQUEST_ACTIVE_SOURCE:
			# raspunde numai cine e pe ecran: noi, numai daca asa spun mesajele
			try:
				if self.telecomanda() and not self.inStandby() and self.activ:
					self.anuntaSursaActiva()
			except Exception as e:
				_jurnal("sursa activa: %r" % (e,), "cec-sursa")
			return
		if cod == CEC_DEVICE_VENDOR_ID and len(parametri) >= 3:
			self._codPrimit(bytes(bytearray(parametri)[:3]), dest)
			return
		if cod == CEC_REPORT_POWER_STATUS and parametri:
			# raspunsul televizorului la <Give Device Power Status> (catre noi; pe libreader primul octet e televizorul)
			self.stareTv = bytearray(parametri)[0]
			if self.stareTv == CEC_PORNIT:
				self._tvPornit()
			else:
				# standby (01) sau in trecere (02, 03): Rsen YES nu mai inseamna ca aprinderea a reusit
				try:
					self.tvNepornitLa = self.ceasLucru()
				except Exception:
					pass
			return
		if cod == CEC_STANDBY:
			# televizorul se stinge: catre toti (V20: primul octet 0x0F) sau, pe familia libreader, cu primul octet al
			# celui care trimite (0); acelasi lucru si catre noi
			self._tvStins()
			return
		if dest == CEC_TOTI:
			return       # catre toti: fara raspuns
		if self.logica is None:
			self._adreseDinDriver()     # o intrebare venita inaintea anuntului: adresa noastra din driver
		catre = self._destinatieRaspuns(dest)
		if cod == CEC_GIVE_OSD_NAME:
			self.numeCerut = self.ceas()
			self.trimiteNumele(catre)
		elif cod == CEC_GIVE_PHYSICAL_ADDRESS:
			a = self.adresaFizica()
			if a is not None:
				self.trimite(CEC_TOTI, CEC_REPORT_PHYSICAL_ADDRESS, a + bytes(bytearray([CEC_TIP_PLAYBACK])))
		elif cod == CEC_GIVE_DEVICE_POWER_STATUS:
			self.trimite(catre, CEC_REPORT_POWER_STATUS,
				bytes(bytearray([CEC_IN_STANDBY if self.inStandby() else CEC_PORNIT])))
		elif cod == CEC_GET_CEC_VERSION:
			self.trimite(catre, CEC_CEC_VERSION, bytes(bytearray([CEC_VERSIUNE_14])))
		elif cod == CEC_GIVE_DEVICE_VENDOR_ID:
			if self.felTv() is not None:
				self.trimite(CEC_TOTI, CEC_DEVICE_VENDOR_ID, self.codTv)
			else:
				self.trimite(catre, CEC_FEATURE_ABORT, bytes(bytearray([cod, CEC_MOTIV_COD_NECUNOSCUT])))
				if self.codTv is None and self.telecomanda():
					self.intreabaCodTv()
		elif cod == CEC_GIVE_DECK_STATUS and parametri:
			if bytearray(parametri)[0] in CEC_STARE_CERUTA:
				self.trimite(catre, CEC_DECK_STATUS, bytes(bytearray([CEC_CASETA_ALTA])))
		elif cod == CEC_VENDOR_COMMAND and parametri:
			if self.felTv() == "lg":
				self._legatura(catre, bytearray(parametri))
		elif cod == CEC_USER_CONTROL_PRESSED and parametri:
			self._tvPornit()
			if self.telecomanda():
				self.activ = True
				self.apasa(bytearray(parametri)[0])
		elif cod == CEC_USER_CONTROL_RELEASED:
			if self.telecomanda():
				self.ridica()
		elif cod == CEC_MENU_REQUEST and parametri:
			if self.telecomanda():
				fel = bytearray(parametri)[0]
				if fel == CEC_MENU_ACTIV:
					self.meniuActiv = True
				elif fel == CEC_MENU_INACTIV:
					self.meniuActiv = False
				stare = CEC_MENU_ACTIV if self.meniuActiv and not self.inStandby() else CEC_MENU_INACTIV
				self.trimite(catre, CEC_MENU_STATUS, bytes(bytearray([stare])))

	# ---- telecomanda televizorului

	def intervalCitire(self):
		"""Citirea la 100 ms cat tastele televizorului sunt pornite (raspund repede), altfel la 400 ms."""
		try:
			return CITIRE_RAPIDA_MS if self.telecomanda() else CITIRE_MS
		except Exception:
			return CITIRE_MS

	def potrivesteCitirea(self):
		"""Ceasul citirii dupa setarea tastelor; oprirea setarii ridica o tasta tinuta."""
		if self.fd is not None and self.timerCitire is not None:
			try:
				self.timerCitire.start(self.intervalCitire(), False)
			except Exception as e:
				_jurnal("citirea CEC: %r" % (e,), "cec-citire-timer")
		try:
			if not self.telecomanda():
				self.opresteTastele()
		except Exception as e:
			_jurnal("telecomanda televizorului: %r" % (e,), "cec-tasta")

	def opresteTastele(self):
		"""Nicio tasta ramasa apasata: la oprirea setarii, la intrarea in standby, la inchiderea nodului."""
		self._opresteTimer(self.timerOk)
		self.okAsteapta = False
		self.okLung = False
		self._elibereaza()

	def _opresteTimer(self, t):
		if t is not None:
			try:
				t.stop()
			except Exception:
				pass

	def _pornesteTimer(self, nume, functie, ms):
		t = getattr(self, nume)
		if t is None:
			t = self.faceTimer(functie)
			setattr(self, nume, t)
		t.start(ms, True)

	def anuntaSursaActiva(self):
		"""<Active Source> catre toti: receptorul e pe ecranul televizorului, deci tastele televizorului vin la el. Cu
		tastele televizorului pornite, dupa el <Menu Status> "activat" (televizorul afla ca receptorul vrea tastele) si,
		la trecerea pe noi, intrebarea starii televizorului."""
		a = self.adresaFizica()
		if a is None:
			return False
		era = self.activ
		self.activ = True
		ok = self.trimite(CEC_TOTI, CEC_ACTIVE_SOURCE, a)
		self._meniuActivat(intreabaStarea=not era)
		return ok

	def _meniuActivat(self, intreabaStarea=False):
		try:
			if not self.telecomanda():
				return
		except Exception:
			return
		self.meniuActiv = True
		self.trimite(CEC_TV, CEC_MENU_STATUS, bytes(bytearray([CEC_MENU_ACTIV])))
		if intreabaStarea:
			self.trimite(CEC_TV, CEC_GIVE_DEVICE_POWER_STATUS)

	# ---- compatibilitate cu televizorul

	def felTv(self):
		"""Felul televizorului din COMPATIBILITATE_TV, sau None (cod necunoscut, fara nevoi aparte, tastele oprite, sau
		legatura lui neleasa de om: la LG setarea „Legătura LG SIMPLINK”, vezi legaturaPornita)."""
		if self.codTv is None:
			return None
		try:
			if not self.telecomanda():
				return None
		except Exception:
			return None
		fel = COMPATIBILITATE_TV.get(self.codTv)
		if fel is not None and not legaturaPornita(fel):
			return None
		return fel

	def intreabaCodTv(self):
		"""<Give Device Vendor ID> catre televizor, cel mult o data la COD_TV_REINTREBARE_S."""
		acum = self.ceas()
		if self.codTvIntrebat is not None and acum - self.codTvIntrebat < COD_TV_REINTREBARE_S:
			return False
		self.codTvIntrebat = acum
		return self.trimite(CEC_TV, CEC_GIVE_DEVICE_VENDOR_ID)

	def _codPrimit(self, cod, dest=None):
		"""<Device Vendor ID> (catre toti): al televizorului daca e sigur al lui (familia libreader: primul octet 0 = cine
		l-a trimis), daca e un cod din COMPATIBILITATE_TV (televizorul isi trimite codul singur, de obicei primul, la
		aprindere) sau daca vine curand dupa intrebarea noastra catre el (V20: driverul nu spune cine l-a trimis)."""
		if self.codTv is not None:
			return
		sigur = (bool(self.inFir) and dest == CEC_TV) or cod in COMPATIBILITATE_TV
		if not sigur and (self.codTvIntrebat is None or self.ceas() - self.codTvIntrebat > COD_TV_ASTEPTARE_S):
			return
		self.codTv = cod
		_jurnal("codul televizorului: %s" % hexa(bytearray(cod)), "cec-cod-tv")

	def _tvPornit(self):
		"""Un semn ca televizorul e pornit (starea lui, o tasta, alegerea intrarii noastre): aprinderea se poate opri."""
		try:
			self.tvPornitLa = self.ceasLucru()
		except Exception:
			pass

	def _altaSursa(self):
		"""Un mesaj spune ca televizorul arata altceva sau s-a stins: o aprindere pornita inainte se opreste (omul a ales
		altceva); un „stiut ca nu” mai vechi decat aprinderea nu o opreste."""
		try:
			self.altaSursaLa = self.ceasLucru()
		except Exception:
			pass

	def _legatura(self, catre, p):
		"""Comenzile proprii ale televizorului pentru legatura cu aparatul (raspunsurile probate pe televizor)."""
		c = p[0]
		if c == LEGATURA_INCEPUT and len(p) == 1:
			self.trimite(catre, CEC_VENDOR_COMMAND, bytes(bytearray([LEGATURA_CONFIRMARE, LEGATURA_TIP])))
		elif c == LEGATURA_CERERE and len(p) == 2:
			# tipul nostru (Playback): cu el televizorul trimite tastele
			self.trimite(catre, CEC_VENDOR_COMMAND, bytes(bytearray([LEGATURA_MOD, CEC_TIP_PLAYBACK])))
			if self.activ:
				self._meniuActivat()
				self.trimite(catre, CEC_REPORT_POWER_STATUS, bytes(bytearray([CEC_PORNIT])))
		elif c in (LEGATURA_RECONECTARE, LEGATURA_STARE) and len(p) == 1:
			self.trimite(catre, CEC_REPORT_POWER_STATUS, bytes(bytearray([CEC_SPRE_PORNIT])))
			self.trimite(catre, CEC_REPORT_POWER_STATUS, bytes(bytearray([CEC_PORNIT])))
		# LEGATURA_PORNIRE si celelalte: fara raspuns (tastele vin si asa)

	def _caleNoua(self, adresa):
		"""<Set Stream Path> / <Routing Change> / <Routing Information>: televizorul arata intrarea `adresa`."""
		if adresa == self.adresaFizica():
			self._tvPornit()
			if self.telecomanda() and self.inStandby():
				# televizorul a ales intrarea receptorului (aprins pe ea sau din lista SIMPLINK / Anynet+): trezirea; la
				# iesirea din standby pleaca <Active Source> (laIesire)
				self.activ = True
				self._trezeste()
			elif self.telecomanda() and not self.inStandby():
				self.anuntaSursaActiva()
			else:
				self.activ = True
		else:
			self.activ = False
			self._altaSursa()
			self.activLaStandby = False
			self.opresteTastele()

	def apasa(self, ui):
		"""<User Control Pressed>: tasta receptorului pe calea obisnuita a tastelor; OK scurt = OK, OK tinut = panoul
		"Mai multe taste"; aceeasi tasta din nou = repetarea (tasta tinuta)."""
		cod = TASTE_CEC.get(ui)
		self.ultimaTasta = {"ui": ui, "cod": cod, "cand": self.ceas()}
		if cod is None:
			_jurnal("telecomanda televizorului: codul CEC %02x nu are tasta pe receptor" % ui, "cec-tasta-fara")
			return
		if cod == T_OK:
			if self.okAsteapta:
				self._pornesteTimer("timerEliberare", self._laEliberare, ELIBERARE_MS)
				return
			self._elibereaza()
			self.okAsteapta = True
			self.okLung = False
			self._pornesteTimer("timerOk", self._laOkLung, OK_LUNG_MS)
			self._pornesteTimer("timerEliberare", self._laEliberare, ELIBERARE_MS)
			return
		if self.okAsteapta:
			self._okGata()
		if self.tastaTinuta == cod:
			self._tasta(cod, STEAG_REPETARE)
		else:
			self._elibereaza()
			self._tasta(cod, STEAG_APASARE)
			self.tastaTinuta = cod
		self._pornesteTimer("timerEliberare", self._laEliberare, ELIBERARE_MS)

	def ridica(self):
		"""<User Control Released>."""
		if self.okAsteapta:
			self._okGata()
		else:
			self._elibereaza()

	def _elibereaza(self):
		self._opresteTimer(self.timerEliberare)
		if self.tastaTinuta is not None:
			cod, self.tastaTinuta = self.tastaTinuta, None
			self._tasta(cod, STEAG_RIDICARE)

	def _okGata(self):
		"""OK ridicat: scurt = OK pe receptor; dupa panou, nimic."""
		self._opresteTimer(self.timerOk)
		self._opresteTimer(self.timerEliberare)
		self.okAsteapta = False
		if not self.okLung:
			self._tasta(T_OK, STEAG_APASARE)
			self._tasta(T_OK, STEAG_RIDICARE)
		self.okLung = False

	def _laOkLung(self):
		if self.okAsteapta and not self.okLung:
			self.okLung = True
			try:
				self.panou()
			except Exception as e:
				_jurnal("panoul Mai multe taste: %r" % (e,), "cec-panou")

	def _laEliberare(self):
		"""Nicio repetare si nicio ridicare in ELIBERARE_MS: tasta se socoteste ridicata."""
		if self.okAsteapta:
			self._okGata()
		else:
			self._elibereaza()

	# ---- televizorul -> receptorul

	def _tvStins(self):
		"""<Standby> de la televizor: tastele oprite; cu „Stinge si televizorul (CEC)” aleasa, receptorul intra si el in
		standby daca era pe ecran sau nu se stie (nu cand televizorul arata altceva), afara de cazurile din seStingeCuTv."""
		era = self.activ
		self.activ = False
		self._altaSursa()
		self.activLaStandby = False
		self.opresteTastele()
		try:
			if era is not False and self.seStingeCuTv():
				_jurnal("CEC: televizorul s-a stins, receptorul intra in standby", "cec-tv-stins")
				self._noteaza("standby", motiv="televizorul s-a stins")
				(self.standbyTv or _standbyReceptor)()
		except Exception as e:
			_jurnal("standby dupa televizor: %r" % (e,), "cec-tv-stins")

	def seStingeCuTv(self):
		"""True daca receptorul urmeaza televizorul in standby acum: setarea aleasa, receptorul pornit, nicio oprire sau
		repornire in curs, nicio trezire in ultimele TREZIT_PAUZA_S (televizorul care se stinge chiar atunci) si nicio
		aprindere a televizorului in curs (cel mult APRINDERE_TERMEN_S: televizorul care abia se stinge cand il aprindem)."""
		try:
			if not _cfg().cec_stinge.value:
				return False
		except Exception:
			return False
		if self.inStandby() or _seOpreste():
			return False
		if self.trezitLa is not None and self.ceasLucru() - self.trezitLa < TREZIT_PAUZA_S:
			return False
		if self.aprindereActiva:
			_jurnal("CEC: <Standby> de la televizor cat il aprindem; receptorul ramane pornit", "cec-tv-stins-aprindere")
			return False
		return True

	def _trezeste(self):
		try:
			_jurnal("CEC: televizorul a ales intrarea receptorului, receptorul se trezeste", "cec-trezire")
			self._noteaza("trezire", motiv="televizorul a ales intrarea receptorului")
			(self.trezesteReceptorul or _trezesteReceptorul)()
		except Exception as e:
			_jurnal("trezirea de la televizor: %r" % (e,), "cec-trezire")

	# ---- standby

	def stingeTv(self, peIntrare):
		"""Intrarea in standby: <Standby> catre televizor, sau numai <Inactive Source> cand se stie ca receptorul nu era
		sursa activa (peIntrare False: sa nu stingem televizorul cuiva care se uita la altceva). None (nu se stie) =
		<Standby>."""
		if peIntrare is False:
			a = self.adresaFizica()
			if a is None:
				return False
			return self.trimite(CEC_TV, CEC_INACTIVE_SOURCE, a)
		return self.trimite(CEC_TV, CEC_STANDBY)

	def pornesteTv(self):
		"""Iesirea din standby: <Image View On> catre televizor, apoi <Active Source> catre toti (intrarea noastra)."""
		ok = self.trimite(CEC_TV, CEC_IMAGE_VIEW_ON)
		a = self.adresaFizica()
		if a is None:
			_jurnal("CEC: adresa fizica nu se stie, fara Active Source", "cec-fara-adresa")
			return ok
		era = self.activ
		self.activ = True
		ok = self.trimite(CEC_TOTI, CEC_ACTIVE_SOURCE, a) and ok
		self._meniuActivat(intreabaStarea=not era)
		return ok


# ---------------------------------------------------------------- tastele televizorului: injectarea, panoul, tabelul

NUME_NATIV = "dreambox advanced remote control (native)"


def _injecteaza(cod, steag):
	"""O tasta pe calea obisnuita a tastelor, ca de pe telecomanda receptorului (eRCMapper.inject, ca telecomanda din
	web): merge in toate ecranele si in aplicatia HbbTV. Fara eRCMapper (binar vechi): eActionMap.keyPressed."""
	try:
		from enigma import eRCMapper
		m = eRCMapper.getInstance()
	except Exception:
		m = None
	if m is not None:
		m.inject(cod, steag)
		return
	from enigma import eActionMap
	eActionMap.getInstance().keyPressed(NUME_NATIV, cod, steag)


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		import builtins
		return builtins.__dict__["_"](text) if "_" in builtins.__dict__ else text
	except Exception:
		return text


def N_(text):
	return text


# numele tastelor de pe telecomanda televizorului, dupa codul CEC pe care il trimite (cum sunt scrise de obicei pe
# telecomenzile televizoarelor); cele cu litere mici se traduc
NUME_TASTA_TV = {0x00: "OK", 0x01: N_("sus"), 0x02: N_("jos"), 0x03: N_("stânga"), 0x04: N_("dreapta"), 0x09: "MENU",
	0x0A: "SETTINGS", 0x0B: "LIST", 0x0C: "FAV", 0x0D: "BACK", 0x2B: "ENTER", 0x30: "CH +", 0x31: "CH -", 0x32: "FLASHBK",
	0x33: "AUDIO", 0x35: "INFO", 0x36: "HELP", 0x44: "PLAY", 0x45: "STOP", 0x46: "PAUSE", 0x47: "REC", 0x48: "REW",
	0x49: "FF", 0x4B: ">>|", 0x4C: "|<<", 0x51: "SUBTITLE", 0x53: "GUIDE", 0x60: "PLAY", 0x61: "PLAY/PAUSE", 0x62: "REC",
	0x64: "STOP", 0x71: N_("albastru"), 0x72: N_("roșu"), 0x73: N_("verde"), 0x74: N_("galben"), 0x76: "TEXT"}
for _i in range(10):
	NUME_TASTA_TV[0x20 + _i] = str(_i)

T_PANOU = N_("Mai multe taste")
T_TABELUL = N_("Ce tastă a televizorului face ce")
T_CALE_PANOU = N_("Mai multe taste (ține apăsat OK)")
T_CALE_TELEVIZOR = N_("o face televizorul")
T_OK_TINUT = N_("ține apăsat: Mai multe taste")


def etichetaTastei(cod):
	"""Numele tastei receptorului (eticheta de pe telecomanda Viper, tradusa)."""
	try:
		from Components import HdsTelecomenziDate as D
		b = D.DUPA_COD.get(cod)
		if b is not None:
			return _t(b[1])
	except Exception:
		pass
	return str(cod)


def tabelTaste():
	"""Tabelul tastelor receptorului: [(cod, eticheta, ce se apasa pe telecomanda televizorului)], in ordinea de pe
	telecomanda receptorului. Pentru ecran (TextBox din panou) si pentru pagina web /telecomanda-tv."""
	try:
		from Components import HdsTelecomenziDate as D
		coduri = [b[2] for b in D.BUTOANE_VIPER]
	except Exception:
		coduri = list(dict.fromkeys(list(TASTE_CEC.values()) + list(PANOU_TASTE) + list(TASTE_TELEVIZOR)))
	rez = []
	for cod in coduri:
		tv = []
		for ui in sorted(TASTE_CEC):
			if TASTE_CEC[ui] == cod:
				n = _t(NUME_TASTA_TV.get(ui, "%02x" % ui))
				if n not in tv:
					tv.append(n)
		if cod in TASTE_TELEVIZOR:
			cale = _t(T_CALE_TELEVIZOR)
		elif tv:
			cale = " / ".join(tv)
			if cod == T_OK:
				cale += " (%s)" % _t(T_OK_TINUT)
			if cod in PANOU_TASTE:
				cale += "; " + _t(T_CALE_PANOU)
		else:
			cale = _t(T_CALE_PANOU)
		rez.append((cod, etichetaTastei(cod), cale))
	return rez


def textTabel():
	return "\n".join("%s:  %s" % (e, c) for _cod, e, c in tabelTaste())


_sesiune = None
_panouDeschis = [False]


def deschidePanou(session=None):
	"""Panoul "Mai multe taste" (lista ChoiceBox din skin): tastele receptorului fara pereche pe telecomanda
	televizorului; primul rand arata tabelul. Nimic in standby sau cat panoul e deja deschis."""
	s = session or _sesiune
	if s is None or _inStandby() or _panouDeschis[0]:
		return False
	from Screens.ChoiceBox import ChoiceBox
	lista = [(_t(T_TABELUL), "tabel")] + [(etichetaTastei(cod), cod) for cod in PANOU_TASTE]
	_panouDeschis[0] = True
	try:
		s.openWithCallback(_dinPanou, ChoiceBox, title=_t(T_PANOU), list=lista)
	except Exception:
		_panouDeschis[0] = False
		raise
	return True


_timerPanou = [None, None]


def _dinPanou(ales=None):
	_panouDeschis[0] = False
	if not ales:
		return
	if ales[1] == "tabel":
		if _sesiune is not None:
			from Screens.TextBox import TextBox
			dlg = _sesiune.open(TextBox, textTabel())
			try:
				dlg.setTitle(_t(T_TABELUL))
			except Exception:
				pass
		return
	# tasta pleaca dupa inchiderea panoului, ca sa ajunga la ecranul de sub el
	_timerPanou[1] = ales[1]
	if _timerPanou[0] is None:
		_timerPanou[0] = _faTimer(_tastaDinPanou)
	_timerPanou[0].start(150, True)


def _tastaDinPanou():
	cod = _timerPanou[1]
	if cod:
		_injecteaza(cod, STEAG_APASARE)
		_injecteaza(cod, STEAG_RIDICARE)



# ---------------------------------------------------------------- iesirea HDMI

class StandbyTv(object):
	"""Starea pentru un enigma2 pornit: iesirea oprita de noi, paza, CEC."""

	def __init__(self, ceas=None, timer=None, cec=None):
		self.ceas = ceas or time.time
		self.faceTimer = timer or _faTimer
		# Cec cu ceasul dat (probele) sau cu ale lui: ora pentru jurnal, ceasul monoton pentru apelurile ramase in driver
		self.cec = cec if cec is not None else Cec(ceas=ceas, timer=self.faceTimer)
		self.oprit = False                # „off” scris de noi in standby-ul de acum
		self.timerPaza = None
		self.pazaPornita = False
		self.rescrieri = []               # momentele rescrierilor din paza (ultima ora)
		self.limitaSpusa = False
		self.ultimaRescriere = None
		self.trezitTemporizator = False
		self.timerCulori = None
		self.timerNume = None
		self.timerSursa = None
		self.legat = False
		self.timerAprindere = None
		self.aprindere = None             # {"motiv", "inceput", "trimiteri", "ok" (trimiteri bune la rand)} cat se aprinde

	# ---- setarile

	def leaga(self):
		"""Notificatorii setarilor: numele nou pleaca la televizor la NUME_DUPA_MS dupa ultima schimbare (nu la fiecare
		litera; si dupa o anulare, care pune la loc numele salvat), iar "Nu" in standby porneste iesirea pe loc."""
		if self.legat:
			return
		c = _cfg()
		c.cec_stinge.addNotifier(self._laCec, initial_call=False)
		c.cec_porneste.addNotifier(self._laCec, initial_call=False)
		c.hdmi_oprit.addNotifier(self._laHdmi, initial_call=False)
		# literele scrise pe televizor (changed), parasirea randului si /setari din web (changedFinal), anularea si
		# salvarea (callNotifiersOnSaveAndCancel: anularea pune la loc numele salvat, care trebuie sa plece si el)
		c.nume_tv.addNotifier(self._laNume, initial_call=False)
		c.nume_tv.addNotifier(self._laNume, initial_call=False, immediate_feedback=False)
		c.nume_tv.callNotifiersOnSaveAndCancel = True
		c.cec_telecomanda.addNotifier(self._laTelecomanda, initial_call=False)
		self.legat = True

	def _laTelecomanda(self, element=None):
		try:
			self.cec.potrivesteCitirea()
		except Exception as e:
			_jurnal("telecomanda televizorului: %r" % (e,), "setare-telecomanda")

	def _laCec(self, element=None):
		self.potrivesteCec()

	def _laNume(self, element=None):
		try:
			if self.timerNume is None:
				self.timerNume = self.faceTimer(self.trimiteNumeleNou)
			self.timerNume.start(NUME_DUPA_MS, True)
		except Exception as e:
			_jurnal("numele pe televizor: %r" % (e,), "setare-nume")

	def trimiteNumeleNou(self):
		"""Numele de acum, numai daca difera de cel trimis ultima oara (sau acela nu a plecat)."""
		try:
			if not self.cec.deschis():
				return False
			u = self.cec.numeTrimis
			if u and u.get("trimis") and u.get("nume") == numeTv():
				return False
			return self.cec.trimiteNumele()
		except Exception as e:
			_jurnal("numele pe televizor: %r" % (e,), "setare-nume")
			return False

	def _laHdmi(self, element=None):
		try:
			if not _cfg().hdmi_oprit.value and self.oprit:
				self._opresteePaza()
				self._pornesteIesirea("setarea a trecut pe Nu")
		except Exception as e:
			_jurnal("setarea HDMI: %r" % (e,), "setare-hdmi")

	def potrivesteCec(self):
		"""Nodul CEC deschis pe orice receptor care il are, oricare ar fi setarile de standby: numele pe televizor vine
		numai prin CEC. Setarile de standby hotarasc numai daca se trimit <Standby> / <Image View On>."""
		try:
			self.cec.deschide()
		except Exception as e:
			_jurnal("CEC: %r" % (e,), "cec-potriveste")

	# ---- scrierile

	def _opresteIesirea(self):
		"""vfd dupa afisaj, apoi „off”; True daca „off” a ajuns la driver."""
		from Components.HdsAfisajCompat import permite
		vfd = os.path.exists(VFD) and permite("alimentare")
		if vfd:
			try:
				from Components.HdsFunctiiImagine import disponibil as functieImagine
			except ImportError:  # probele vechi incarca numai acest modul
				functieImagine = None
			if functieImagine is not None and functieImagine("afisaj"):
				# Afisajul producatorului isi pastreaza propriul mod de standby.
				vfd = False
		if vfd:
			scrie(VFD, vfdDorit(), "vfd")
		if not scrie(IESIRE, "off", "off"):
			if vfd:
				scrie(VFD, "1", "vfd")  # iesirea a ramas pornita: afisajul nu ramane gol
			return False
		try:
			with io.open(SEMN, "w", encoding="ascii") as f:
				f.write(u"off")
		except (IOError, OSError) as e:
			_jurnal("semnul %s: %s" % (SEMN, e), "semn")
		return True

	def _pornesteIesirea(self, motiv):
		ok = scrie(IESIRE, "on", "on")
		try:
			if os.path.exists(SEMN):
				os.remove(SEMN)
		except OSError as e:
			_jurnal("semnul %s: %s" % (SEMN, e), "semn")
		self.oprit = False
		_jurnal("iesirea HDMI pornita (%s)" % motiv, "pornita")
		return ok

	# ---- standby

	def laIntrare(self):
		"""Din Screens/Standby.py, dupa ce inStandby e pus (canalul e deja oprit)."""
		eraActiv = False
		try:
			eraActiv = self.peEcran()           # True, False sau None (nu se stie)
			self.cec.activLaStandby = eraActiv is True
			self.cec.activ = False
			self.cec.opresteTastele()
		except Exception as e:
			_jurnal("tastele la standby: %r" % (e,), "cec-tasta")
		self.trezitTemporizator = False
		self.oprit = False
		self.limitaSpusa = False
		if self.aprindere is not None:
			self._opresteAprinderea("receptorul a intrat in standby")
		c = _cfg()
		if c.cec_stinge.value and self.cec.deschis():
			try:
				# <Standby> daca, dupa mesaje, receptorul era pe ecran sau nu se stie; numai <Inactive Source> cand se
				# stie ca televizorul arata altceva
				self.cec.stingeTv(eraActiv)
				if eraActiv is not False:
					self.cec.activLaStandby = False     # televizorul stins: la trezire nu mai e pe noi
			except Exception as e:
				_jurnal("CEC la standby: %r" % (e,), "cec-intrare")
		# afisajul de 4 cifre in standby (power4x7standby, SF8008 / Ustym 4K PRO) dupa alegerea „In asteptare”, si cand
		# iesirea HDMI ramane pornita: altfel driverul il tine stins (Components/HdsAfisaj.aplicaAfisajInAsteptare)
		try:
			from Components import HdsAfisaj
			HdsAfisaj.aplicaAfisajInAsteptare(forteaza=True)
		except Exception as e:
			_jurnal("afisajul in asteptare: %r" % (e,), "afisaj-asteptare")
		if not c.hdmi_oprit.value or not os.path.exists(IESIRE):
			return
		if self._opresteIesirea():
			self.oprit = True
			_jurnal("iesirea HDMI oprita in standby (vfd %s)" % vfdDorit(), "oprita")
			self._pornestePaza()

	def peEcran(self):
		"""Cec.activ (True, False, None = nu se stie); None devine False cand driverul HDMI spune sigur ca televizorul nu
		tine legatura (Rsen NO: stins, sau intrarea noastra neluata pe televizoarele care o lasa fara terminatie)."""
		a = self.cec.activ
		if a is None:
			try:
				if tvStins():
					return False
			except Exception:
				pass
		return a

	def laOprire(self, dormi=None):
		"""Din Screens/Standby.py, la oprirea completa (TryQuitMainloop 1), chiar inainte de quitMainloop: cu „Stinge si
		televizorul (CEC)” aleasa, ca la intrarea in standby (<Standby> daca receptorul era pe ecran sau nu se stie, numai
		<Inactive Source> cand se stie ca televizorul arata altceva), apoi asteptarea scurta ca mesajul sa plece. Din standby nimic. Intoarce True daca a trimis ceva."""
		if _inStandby():
			return False
		c = _cfg()
		if not c.cec_stinge.value or not self.cec.deschis():
			return False
		trimis = False
		try:
			self.cec.opresteTastele()
			trimis = self.cec.stingeTv(self.peEcran()) is not False      # None (nu se stie) = <Standby>
			self.cec.asteaptaScrierile(OPRIRE_ASTEAPTA_S)
			(dormi or time.sleep)(OPRIRE_LINIE_S)
			_jurnal("CEC la oprirea completa: %s" % ("trimis" if trimis else "netrimis"), "cec-oprire")
		except Exception as e:
			_jurnal("CEC la oprirea completa: %r" % (e,), "cec-oprire")
		return trimis

	# ---- aprinderea televizorului (trezire si pornirea receptorului)

	def aprindeTv(self, motiv, intarziere=0):
		"""<Image View On> + <Active Source> acum (sau dupa `intarziere` ms) si din nou la APRINDERE_REPETA_MS, pana cand
		televizorul e pornit si a primit mesajul (vezi _pasAprindere). Intoarce True daca aprinderea a pornit."""
		if self.aprindere is not None:
			self._opresteAprinderea("inlocuita (%s)" % motiv)
		self.aprindere = {"motiv": motiv, "inceput": self.cec.ceasLucru(), "trimiteri": 0, "ok": 0}
		self.cec.aprindereActiva = True
		if self.timerAprindere is None:
			self.timerAprindere = self.faceTimer(self._pasAprindere)
		if intarziere:
			self.timerAprindere.start(intarziere, True)
		else:
			self._pasAprindere()
		return True

	def _opresteAprinderea(self, motiv):
		a, self.aprindere = self.aprindere, None
		self.cec.aprindereActiva = False
		if self.timerAprindere is not None:
			try:
				self.timerAprindere.stop()
			except Exception:
				pass
		if a is None:
			return
		_jurnal("CEC: aprinderea televizorului (%s) gata: %s; Image View On + Active Source trimise de %d ori" % (
			a["motiv"], motiv, a["trimiteri"]), "cec-aprindere-gata")
		self.cec._noteaza("aprindere", motiv=a["motiv"], rezultat=motiv, trimiteri=a["trimiteri"])

	def _pasAprindere(self):
		a = self.aprindere
		if a is None:
			return
		cec = self.cec
		try:
			if _inStandby():
				return self._opresteAprinderea("receptorul e in standby")
			if cec.altaSursaLa is not None and cec.altaSursaLa > a["inceput"]:
				# numai un mesaj venit dupa inceput: la pornire televizorul poate fi pe tunerul lui (raspunsul la
				# <Request Active Source>), si tocmai atunci trebuie mutat pe receptor
				return self._opresteAprinderea("televizorul arata alta intrare")
			if cec.tvPornitLa is not None and cec.tvPornitLa > a["inceput"]:
				return self._opresteAprinderea("televizorul a raspuns ca e pornit")
			if a["trimiteri"]:
				# rezultatul scrierilor de la pasul trecut (pe familia libreader trimite le face firul de lucru)
				ok = cec.raspunde is True and cec.adresaStiuta() is not None
				a["ok"] = a["ok"] + 1 if ok else 0
				rsen = tvPeIntrare()
				# televizorul a spus dupa inceput ca e in standby / abia se aprinde: Rsen YES (LG il tine si stins) si
				# trimiterile bune nu dovedesc ca s-a aprins; se repeta pana spune „pornit” sau trece termenul
				nepornit = cec.tvNepornitLa is not None and cec.tvNepornitLa >= a["inceput"]
				if ok and rsen is True and not nepornit:
					return self._opresteAprinderea("HDMI sus, adresa fizica luata, mesajul a plecat")
				if rsen is None and a["ok"] >= 2 and not nepornit:
					# fara /proc/msp/hdmi0 (de pilda Vu+ 4K) HDMI nu se vede: doua trimiteri bune la rand ajung
					return self._opresteAprinderea("mesajul a plecat de doua ori (HDMI nu se poate citi)")
			if cec.ceasLucru() - a["inceput"] >= APRINDERE_TERMEN_S:
				return self._opresteAprinderea("termenul de %d s a trecut fara raspunsul televizorului" % APRINDERE_TERMEN_S)
			if cec.deschis() and not cec.blocat:
				if not a["trimiteri"]:
					_jurnal("CEC: aprind televizorul (%s): Image View On + Active Source, din nou la %d s pana raspunde" % (
						a["motiv"], APRINDERE_REPETA_MS // 1000), "cec-aprindere")
				cec.pornesteTv()
				if a["trimiteri"]:
					cec.trimite(CEC_TV, CEC_GIVE_DEVICE_POWER_STATUS)
				a["trimiteri"] += 1
		except Exception as e:
			_jurnal("aprinderea televizorului: %r" % (e,), "cec-aprindere")
		if self.aprindere is a and self.timerAprindere is not None:
			self.timerAprindere.start(APRINDERE_REPETA_MS, True)

	def aprindeLaPornire(self):
		"""Din porneste (mytest.py): la pornirea reala a receptorului, cu „Porneste televizorul la trezire (CEC)” aleasa,
		televizorul se aprinde ca la trezire. Nu la repornirea interfetei (sistemul pornit de mai mult de
		PORNIRE_UPTIME_S), nu cand l-a pornit ceasul (temporizator), nu daca interfata e in standby."""
		try:
			if not _cfg().cec_porneste.value or _inStandby():
				return False
		except Exception:
			return False
		u = _uptime()
		if u is None or u > PORNIRE_UPTIME_S:
			return False
		if _trezitDeCeas():
			_jurnal("CEC: receptorul pornit de ceas, televizorul nu se aprinde", "cec-aprindere")
			return False
		return self.aprindeTv("pornirea receptorului", PORNIRE_DUPA_MS)

	def _pornestePaza(self):
		if not os.path.exists(HDMI0):
			return
		try:
			if self.timerPaza is None:
				self.timerPaza = self.faceTimer(self.pazeste)
			self.timerPaza.start(PAZA_MS, True)
			self.pazaPornita = True
		except Exception as e:
			_jurnal("paza: %r" % (e,), "paza-timer")

	def _opresteePaza(self):
		self.pazaPornita = False
		if self.timerPaza is not None:
			try:
				self.timerPaza.stop()
			except Exception:
				pass

	def pazeste(self):
		"""Un pas al pazei: iesirea pornita de platforma (o conectare a televizorului) se opreste din nou."""
		if not self.pazaPornita:
			return
		if not self.oprit or not _inStandby():
			self._opresteePaza()
			return
		try:
			text = citeste(HDMI0)
			if text is None:
				self._opresteePaza()
				return
			if iesirePornita(text):
				acum = self.ceas()
				self.rescrieri = [t for t in self.rescrieri if acum - t < 3600]
				if len(self.rescrieri) >= PAZA_LIMITA:
					if not self.limitaSpusa:
						_jurnal("paza: %d reporniri ale iesirii intr-o ora, nu mai scriu off pana se rareste" %
							PAZA_LIMITA, "paza-limita")
						self.limitaSpusa = True
				else:
					self.rescrieri.append(acum)
					self.ultimaRescriere = acum
					self.limitaSpusa = False
					if self._opresteIesirea():
						_jurnal("paza: iesirea pornita de platforma (HPD %s), oprita din nou" % contorHpd(text),
							"paza-rescrie")
		except Exception as e:
			_jurnal("paza: %r" % (e,), "paza")
		if self.pazaPornita and self.timerPaza is not None:
			self.timerPaza.start(PAZA_MS, True)

	def laIesire(self):
		"""Din Screens/Standby.py, dupa inStandby = None si inaintea pornirii canalului."""
		try:
			self.cec.trezitLa = self.cec.ceasLucru()    # un <Standby> de la televizor chiar acum nu-l mai stinge
			if self.cec.activ is False:
				# „stiut ca nu” era starea din standby (televizorul stins de noi sau pe altceva); dupa trezire omul poate
				# aprinde televizorul de mana pe receptor fara niciun mesaj CEC, deci iar nu se stie (altfel oprirea
				# completa de dupa trimitea numai <Inactive Source>, ca la Wlad). True (pus chiar acum de alegerea
				# intrarii de la televizor) ramane.
				self.cec.activ = None
				self.cec.sursaIntrebata = False
		except Exception:
			pass
		self._opresteePaza()
		if self.oprit:
			self._pornesteIesirea("iesirea din standby")
		temporizator = self.trezitTemporizator
		self.trezitTemporizator = False
		try:
			c = _cfg()
			if c.cec_porneste.value and not temporizator and self.cec.deschis():
				self.aprindeTv("trezire")      # primul pas pe loc (ca inainte), apoi din nou pana raspunde televizorul
			elif not temporizator and self.cec.deschis() and self.cec.telecomanda():
				# dupa cateva secunde, cand imaginea a pornit: <Active Source> din nou numai daca receptorul era sursa
				# la intrarea in standby si niciun mesaj nu a spus altfel (nu aprinde si nu muta televizorul)
				if self.timerSursa is None:
					self.timerSursa = self.faceTimer(self.cec.sursaDacaTvPeNoi)
				self.timerSursa.start(SURSA_DUPA_TREZIRE_MS, True)
			if self.cec.activ is None and not temporizator and not c.cec_porneste.value and \
					not self.cec.activLaStandby and self.cec.deschis():
				# trezit de om, fara „Porneste televizorul” si fara semn ca eram pe ecran: un televizor pe alta intrare
				# spune asta (<Active Source> al altcuiva); de la temporizator nimic, ca pana acum
				self.cec.intreabaSursa()
		except Exception as e:
			_jurnal("CEC la trezire: %r" % (e,), "cec-iesire")
		self._culoriCurand()

	def _culoriCurand(self):
		"""O privire HdmiColors dupa CULORI_DUPA_MS (nu dupa un minut)."""
		try:
			if self.timerCulori is None:
				self.timerCulori = self.faceTimer(_privesteCulorile)
			self.timerCulori.start(CULORI_DUPA_MS, True)
		except Exception as e:
			_jurnal("culorile HDMI: %r" % (e,), "culori")

	def laPornire(self):
		"""O data, la pornirea enigma2: iesirea lasata oprita (enigma2 iesit in standby) se porneste."""
		if not os.path.exists(IESIRE) or _inStandby():
			return False
		pornita = iesirePornita()
		semn = os.path.exists(SEMN)
		if pornita is False or semn:
			motiv = "la pornire: %s" % ("iesirea era oprita" if pornita is False else "ramasa oprita de enigma2 de dinainte")
			return self._pornesteIesirea(motiv)
		return False

	def stare(self):
		"""Pentru pagina web (standby_tv_web.py)."""
		c = _cfg()
		acum = self.ceas()
		pornita = iesirePornita()
		return {
			"hdmi_disponibil": os.path.exists(IESIRE),
			"hdmi_setare": bool(c.hdmi_oprit.value),
			"in_standby": _inStandby(),
			"oprita_de_noi": bool(self.oprit),
			"iesire": None if pornita is None else ("pornita" if pornita else "oprita"),
			"paza": bool(self.pazaPornita),
			"paza_disponibila": os.path.exists(HDMI0),
			"rescrieri_ora": len([t for t in self.rescrieri if acum - t < 3600]),
			"ultima_rescriere": self.ultimaRescriere,
			"cec_disponibil": os.path.exists(CEC),
			"cec_stinge": bool(c.cec_stinge.value),
			"cec_porneste": bool(c.cec_porneste.value),
			"cec_deschis": self.cec.deschis(),
			"cec_raspunde": self.cec.raspunde,
			"cec_blocat": bool(self.cec.blocat),
			"cec_ultimul": dict(self.cec.ultimul) if self.cec.ultimul else None,
			"cec_primite": self.cec.primite,
			"cec_golite": self.cec.golite,
			"cec_ultima_primire": dict(self.cec.ultimaPrimire) if self.cec.ultimaPrimire else None,
			"nume_tv": numeTv(),
			"nume_implicit": numeImplicit(),
			"nume_trimis": dict(self.cec.numeTrimis) if self.cec.numeTrimis else None,
			"nume_cerut": self.cec.numeCerut,
			"cec_telecomanda": bool(c.cec_telecomanda.value),
			"cec_activ": self.cec.activ,          # True, False sau None (nu se stie)
			"cec_ultima_tasta": self._ultimaTasta(),
			"adresa_fizica": textAdresa(self.cec.adresaStiuta()),
		}

	def _ultimaTasta(self):
		u = self.cec.ultimaTasta
		if not u:
			return None
		return {"cod": u.get("cod"), "ui": u.get("ui"), "cand": u.get("cand"),
			"eticheta": etichetaTastei(u["cod"]) if u.get("cod") else None}


def _privesteCulorile():
	try:
		from Components import VideoOutput
		culori = VideoOutput.hdmiColors()
		if culori is not None:
			culori.afterStandby()
	except Exception as e:
		_jurnal("culorile HDMI: %r" % (e,), "culori")


# ---------------------------------------------------------------- legaturile din enigma2

_tv = None


def instanta():
	global _tv
	if _tv is None:
		_tv = StandbyTv()
	return _tv


def porneste(session=None):
	"""Din mytest.py (runScreenTest): setarile, siguranta la pornire, nodul CEC (numele pe televizor)."""
	global _sesiune
	initConfig()
	if session is not None:
		_sesiune = session
	tv = instanta()
	try:
		tv.leaga()
	except Exception as e:
		_jurnal("notificatorii: %r" % (e,), "leaga")
	try:
		tv.laPornire()
	except Exception as e:
		_jurnal("siguranta la pornire: %r" % (e,), "pornire")
	tv.potrivesteCec()
	try:
		tv.aprindeLaPornire()
	except Exception as e:
		_jurnal("aprinderea la pornire: %r" % (e,), "cec-aprindere")


def laIntrare():
	try:
		instanta().laIntrare()
	except Exception as e:
		_jurnal("intrarea in standby: %r" % (e,), "intrare")


def laIesire():
	try:
		instanta().laIesire()
	except Exception as e:
		_jurnal("iesirea din standby: %r" % (e,), "iesire")


def laOprire():
	"""Din Screens/Standby.py (TryQuitMainloop), numai la oprirea completa, chiar inainte de quitMainloop."""
	try:
		return instanta().laOprire()
	except Exception as e:
		_jurnal("oprirea completa: %r" % (e,), "oprire")
		return False


def trezitDeTemporizator():
	"""Din RecordTimer.py, inaintea trezirii pentru un temporizator de schimbare a canalului: fara CEC la trezire."""
	instanta().trezitTemporizator = True


def stare():
	try:
		return instanta().stare()
	except Exception as e:
		_jurnal("starea: %r" % (e,), "stare")
		return {}


def jurnalCec():
	"""Jurnalul CEC (cele mai vechi intai): [{t, fel, ...}], pentru /api/standby-tv?jurnal=1."""
	try:
		return [dict(x) for x in instanta().cec.jurnalCec]
	except Exception as e:
		_jurnal("jurnalul CEC: %r" % (e,), "jurnal-cec")
		return []

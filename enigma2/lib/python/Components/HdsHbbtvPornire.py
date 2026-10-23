# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Aplicatia HbbTV a canalului redat, pornita la tasta ROSIE, cu obiectele OIPF/HbbTV
din pagina.

ROSU in bara (Screens/InfoBar.py, actiunea „hbbtvRosu” din HdsInfobarActions, data/keymap.xml) cheama apasaRosu(bara):
  - canalul nu are in AIT o aplicatie de pornit: intoarce 0, tasta merge mai departe ca inainte (nimic nou);
  - timeshift pornit: un mesaj, aplicatia nu porneste (in timeshift HbbTV se opreste, hotararea C3 a planului);
  - aplicatia are numai carusel DSM-CC (fara adresa HTTP): caruselul se citeste din semnal, apoi navigatorul porneste la
    adresa locala a aplicatiei (vezi CARUSELUL mai jos);
  - altfel navigatorul web porneste in modul HbbTV (Plugins/Extensions/HdsNavigator/lansator.py, MOD_HBBTV) cu adresa
    intreaga a aplicatiei (HdsHbbtv.url_complet). O aplicatie AUTOSTART primeste un ROSU (VK_RED), ca sa treaca din
    semnul ei in meniu (cu stratul H3: numai daca masca ei de taste are ROSU), o singura data, abia cand e gata: la
    ROSU_DUPA_ARATA_MS dupa Application.show() sau, daca nu se arata singura, la ROSU_FARA_ARATA_MS dupa prima pagina
    (0.2.8: trimis la 1 s dupa prima pagina se pierdea la aplicatiile lente, de pilda ProSieben si SAT.1, care cereau
    a doua apasare); cu aplicatia pe ecran, urmarit (ROSU-UL URMARIT mai jos) si trimis inca o data daca s-a pierdut;
  - inregistrare (OPRESTE_LA_INREGISTRARE) sau memorie libera sub MEMORIE_ROSU_KB: un mesaj, nu porneste.
Memoria: cat ruleaza, o verificare la VERIFICARE_MS: sub MEMORIE_OPRIRE_KB aplicatia se inchide cu un mesaj scurt.
Cache-ul aplicatiilor (DOSAR_CACHE, in memorie) peste CACHE_MAXIM_KB se goleste la pornirea urmatoarei (curata_cache).

CE S-A REPARAT DUPA PARCURGEREA TUTUROR SATELITILOR:
  - VK_RED trimis de receptor care inchide aplicatia: daca ea cere inchiderea (destroyApplication, window.close) la cel
    mult INCHISA_DUPA_ROSU_S dupa el, se incarca din nou o data, fara el (_reiaFaraRosu; REIA_FARA_ROSU);
  - mesajul la inchidere spune ce s-a intamplat: "nu a pornit" numai fara prima pagina, "s-a inchis" dupa ea (cu
    motivul), "s-a inchis singura, inainte sa se arate" la destroyApplication fara nicio aratare; "nu s-a aratat pe
    ecran" (TERMEN_ARATA_MS) nu mai cere al doilea ROSU: aplicatiile fara show() sunt de obicei numai de fundal.

ROSU-UL URMARIT (VK_RED trimis de receptor cu stratul, aplicatia pe ecran si ecranul citibil, Mediu.semn_ecran):
  - unele aplicatii cheama show() inainte sa fie gata de ROSU: SUPER RTL isi arata semnul de ROSU (coltul din dreapta
    jos) la 2-4 s dupa show() si pana atunci ignora tasta, deci omul vedea semnul si trebuia sa apese ROSU a doua oara.
    Altele (sixx si celelalte de pe redbutton.de) nu deseneaza nimic pana la ROSU, dar sunt gata de la show(), iar ARD
    isi are semnul pe ecran chiar la show(). De aceea VK_RED pleaca tot la ROSU_DUPA_ARATA_MS, apoi se urmareste ce
    face ecranul, la ROSU_PAS_MS, dupa cum era in clipa trimiterii (urmare_rosu):
      cu ceva pe ecran: o reactie e ecranul schimbat; nimic schimbat in ROSU_REACTIE_MS -> inca un VK_RED;
      ecranul gol: o reactie e un continut mare (ROSU_SEMN_MARE din ecran: un meniu, un portal); un continut mic
                   (semnul aplicatiei, macar ROSU_DESEN_MINIM puncte) vazut de doua ori la rand -> inca un VK_RED, acum
                   ca aplicatia s-a aratat gata; nimic in ROSU_SEMN_MAXIM_MS -> nimic de facut;
    oricand, reactii sunt si o pagina noua (lansatorul spune INCARCARE: laIncarcare), alta masca de taste (ARD trece
    din 13 in 63 la ROSU), arata, ascunde, distruge, aplicatie, canal, urmator, anterior. Legarea video/broadcast,
    fereastra si o masca pusa din nou cu aceeasi valoare vin si singure, cat aplicatia se pregateste, deci nu sunt
    reactii. Al doilea VK_RED pleaca o singura data; orice tasta trimisa aplicatiei de om opreste urmarirea;
  - ecranul: pagina afisata a /dev/fb0 (cat aplicatia e pe ecran numai navigatorul deseneaza acolo, enigma2 are
    lacatul), un rand din SEMN_PAS si un punct din SEMN_PAS pe rand (alfa > 0) si crc32 al randurilor citite
    (semn_ecran, ca stratul web Plugins/Extensions/HdsWebControl/osd_strat.py; ~14 ms pe Amiko Viper 4K V20);
  - fara ecran citibil (emulatorul, Mediile de proba fara semn_ecran) totul e ca inainte: un singur VK_RED, neurmarit.

COMPATIBILITATEA SI MOTIVUL (Components/HdsHbbtvAplicatii.py):
  - partea HbbTV a User-Agent-ului si localSystem vin din Mediu.agent_pentru(adresa) (compatibilitate cu aplicatiile
    din lista);
  - cand aplicatia nu a pornit (fara prima pagina), s-a inchis singura inainte sa se arate sau nu s-a aratat in
    TERMEN_ARATA_MS, mesajul spune motivul adevarat cand se afla (HdsHbbtvAplicatii.motiv): cercetarea adresei pe un
    fir separat (Mediu.cercetare), asteptata cel mult MOTIV_ASTEPTARE_S, plus listele din fisierul de date si canalul
    criptat; altfel mesajul de pana acum. Motivul ramane si pentru web (ultima(), /api/navigator) si in jurnalul
    erorilor navigatorului. Un Mediu fara cercetare (probele vechi) da mesajul de pana acum, pe loc.

STRATUL H3 (hds-hbbtv.js, pus de lansator in pagina; "HDS-NAV HBBTV strat 1"): obiectele OIPF vorbesc cu acest
controlor prin randurile "HBBTV <comanda> ..." (Controlor.laHbbtv), iar controlorul le raspunde cu partile starii
(app, canal, config, lista, programe, taste: Navigator.hbbtvParte) si cu evenimente (Navigator.hbbtvEv):
  - Application.show()/hide(): aplicatia porneste ASCUNSA (ETSI TS 102 796 cap. 6.2.2.4) si ia ecranul abia la
    show(); fara show() in TERMEN_ARATA_MS dupa prima pagina un mesaj scurt, iar aplicatia ramane pornita, ascunsa
    (urmatorul ROSU ajunge la ea; pana se arata o data primeste numai culorile). hide(): lansatorul goleste ce a
    desenat, enigma2 ia fb0 inapoi (bara si meniurile merg), aplicatia ramane pornita;
  - Keyset.setValue: masca de taste; enigma2 trimite paginii NUMAI tastele din masca (Tabelul 12 al standardului,
    bitii din OIPF DAE 7.2.5; fara setValue: toate cele sustinute, ca in DAE), vezi fel_tasta;
  - video/broadcast: canalul de acum (ccid cu spatiul de nume, ca referinta sa se poata reface), EIT acum/urmeaza,
    setChannel / nextChannel / prevChannel prin zap in enigma2, stop / release (canalul oprit si pornit din nou),
    setFullScreen si pozitia/marimea ferestrei (numai tinute minte aici; imaginea o muta partea de fereastra video);
  - createApplication: dvb://current.ait/<org>.<app> (o aplicatie din AIT-ul canalului) sau http(s) (aplicatie
    independenta de canal: canalul se opreste, cap. 6.2.2.6); destroyApplication si window.close() = EXIT;
  - setChannel(null): aplicatia devine independenta de canal (canalul se opreste).
Fara strat (fisierul scriptului lipseste) totul merge ca in H2: aplicatia se arata la prima pagina, toate tastele
aplicatiei merg la ea.

CAT RULEAZA APLICATIA:
  - navigatorul ruleaza ca utilizatorul fara root UTILIZATOR (facut de reteta hds-navigator), daca exista: lansatorul
    deschide /dev/fb0 ca root, apoi coboara pe el (--utilizator); dosarele lui le face si i le da Mediu.dosare;
  - canalul ramane pornit; navigatorul deseneaza pe /dev/fb0 cu fundal transparent (zonele fara continut lasa canalul
    sa se vada), cu lacatul fbClass ca navigatorul obisnuit; telecomanda ramane a enigma2 (fara eRCInput.lock si fara
    EVIOCGRAB): o legatura pe toate tastele (eActionMap, prioritatea cea mai mare) le imparte dupa fel_tasta:
      aplicatie  tastele din masca (fara strat: sagetile, OK, culorile, cifrele, BACK): trimise navigatorului;
      receptor   volumul, MUTE, P+/P-, POWER: merg mai departe la enigma2 (P+/P- schimba canalul, iar schimbarea
                 facuta de om inchide aplicatia; bara de volum nu se vede cat aplicatia e pe ecran);
      inchide    EXIT: aplicatia se inchide, canalul ramane, telecomanda e libera pe loc (nu a fost apucata);
      nimic      restul (MENU, INFO, EPG ... din afara mastii): nicio urmare cat aplicatia e pe ecran (enigma2 nu poate
                 desena peste ea).
    Cat se incarca (pana la prima pagina si pana la show()) numai EXIT e al aplicatiei (renunta); restul merge la
    enigma2 ca inainte. Cat aplicatia e ascunsa (hide()), tastele din masca ajung la ea numai cand pe ecran e bara
    (televizorul), nu un meniu; EXIT o inchide si merge si la enigma2.
  - se inchide singura la: schimbarea canalului facuta de om (evStart / evEnd), standby, timeshift pornit, memorie
    putina, caderea navigatorului, o schimbare de canal ceruta de aplicatie spre un canal in care aplicatia nu e
    semnalata (AUTOSTART/PRESENT cu acelasi org/app, cap. 6.2.2.2). Dupa inchidere o fereastra transparenta pe tot
    ecranul se arata si se ascunde, ca enigma2 sa-si redeseneze ecranul peste ce a lasat pagina; un canal oprit de
    aplicatie porneste din nou.

TRADUCEREA ("Tradu HbbTV", Components/HdsTraducereTexte.py): la fiecare pornire o cheie noua (secrets); cand setarea
e pornita, partea "config" trimisa pe stdin (_trimite, dupa "HBBTV strat 1") are si "traducere": {port, cheie} (port 0
cand interfata web nu asculta), pentru scriptul din pagina (hds-hbbtv.js). Cu hds-navigator 0.7.0 scriptul cere
traducerile prin puntea lansatorului: randul "HBBTV tradu <id> <base64>" (lansatorul a verificat id-ul, semnele si
debitul), raspunsul pleaca inapoi ca eveniment {"ev": "traducere", "id", "result", "t" | "oprit"} (raspuns_traducere,
acelasi ca la interfata web), deci merge si in paginile https. Cu un lansator mai vechi scriptul cere traducerile la
HdsWebControl/traducere_hbbtv_web.py; acolo cheia se verifica (cheieTraducere). Linia de comanda (starea de pornire)
nu are niciodata cheia. O setare a traducerii schimbata trimite din nou "config" (pornita: textele se traduc; oprita:
originalele se pun la loc).

FEREASTRA VIDEO: video/broadcast legat trimite pozitia si marimea lui ("fereastra x y l i", puncte CSS ale
paginii de 1280x720) si setFullScreen ("ecran-intreg"). Cat aplicatia e pe ecran, imaginea canalului se muta in acel
dreptunghi prin /proc/stb/vmpeg/0/dst_left|top|width|height (hex, 720x576, ca lib/gui/evideo.cpp) + dst_apply
(fereastra_vmpeg, scrie_fereastra_video; masurat pe receptor: driverul o tine si dupa zap, iar o latime sau inaltime 0
inseamna ecran intreg). Imaginea revine OBLIGATORIU pe tot ecranul la: ascunderea aplicatiei, release(), setChannel(null),
un obiect ascuns sau prea mic, orice inchidere (EXIT, zap, cadere, standby, memorie, laOprit) si la pornirea enigma2,
daca a ramas mica dupa o cadere a interfetei (porneste -> video_intreg_la_pornire).

SETAREA PRINCIPALA „HbbTV” (config.plugins.hdsnavigator.hbbtv, 0.2.8, OPRITA din fabrica; omul o porneste daca vrea
de tot, daca i se pare ca ingreuneaza receptorul): oprita, ROSU si Portal nu pornesc nimic
(rosu() intoarce 0), pornirea automata nu se face, o aplicatie deschisa se inchide pe loc (laSetareaHbbtv), semnul rosu
nu se arata (HdsHbbtv.arata_semn) si nucleul nu mai cere filtrul AIT (lib/service/servicedvb.cpp, la urmatorul zap).

PORNIREA AUTOMATA (setarea config.plugins.hdsnavigator.hbbtv_autostart, „Pornirea automată a aplicațiilor
HbbTV”, oprita din fabrica; ascultarea canalului o pune porneste(session), din mytest.py):
  - cu setarea pornita, la AIT-ul canalului redat aplicatia AUTOSTART (cu adresa HTTP) porneste singura, ASCUNSA
    (ETSI TS 102 796 cap. 6.2.2.4): fara fereastra „se porneste”, fara taste (telecomanda ramane toata a enigma2),
    pagina facuta nevazuta pentru WebKit ("vizibil 0": nu deseneaza), show() tinut minte. ROSU o arata pe loc (si ii
    trimite VK_RED, daca masca ei are ROSU); de acolo e ca o aplicatie pornita de om;
  - zap facut de om: aplicatia legata de canal ramane pornita (ascunsa) pana vine AIT-ul canalului nou si ramane numai
    daca e semnalata acolo (acelasi org_id si app_id, AUTOSTART sau PRESENT); altfel se inchide, iar aplicatia
    AUTOSTART a canalului nou porneste ascunsa; pe un canal fara HbbTV nu ramane nimic;
  - paza: nu porneste si se opreste (fara mesaj cat e nevazuta) in standby, in timeshift, cat ruleaza o inregistrare
    (OPRESTE_LA_INREGISTRARE) sau cu MemAvailable sub MEMORIE_AUTOSTART_KB (pornirea) / MEMORIE_FUNDAL_KB (cat e
    nevazuta); dupa o cadere sau o oprire de paza nu se mai incearca pe acelasi canal pana la urmatorul zap;
  - ROSU apasat de om cand paza opreste pornirea: un mesaj limpede (inregistrarea, memoria, timeshift-ul);
  - navigatorul obisnuit, interfata camului si „Șterge datele HbbTV” iau locul unei aplicatii nevazute (cedeaza: oprire
    pe loc), nu se refuza;
  - cu setarea oprita totul e ca in H3 (pornire numai la ROSU, inchidere la zap).

CARUSELUL (aplicatiile care vin numai prin caruselul DSM-CC al canalului, Components/HdsCaruselServer.py): la ROSU,
dupa aceeasi paza (inregistrarea, memoria), Mediu.carusel da sesiunea caruselului (cititorul pe demux-ul televizorului,
numai filtre de sectiuni, si serverul HTTP local, numai pe 127.0.0.1). Cat se incarca, fereastra mica spune ca
aplicatia se incarca din satelit, cu partile venite; EXIT renunta, un zap o opreste. La CARUSEL_PAS_MS,
_verificaCarusel se uita la stare: fisierul de pornire (calea initiala din AIT) pe disc si caruselul intreg (sau
TERMEN_CARUSEL_S trecut) -> navigatorul porneste la adresa locala, iar pagina primeste in config "carusel"
(hds-hbbtv.js rescrie spre server adresele dvb:// ale caruselului); altfel un mesaj: pista fara date (criptata sau fara
semnal), semnal slab, carusel prea mare, fara fisierul de pornire, caruselul pe alt serviciu (CARUSEL). Cat ruleaza
aplicatia, cititorul tine caruselul la zi; la orice inchidere (laOprit), la zap si la renuntare, cititorul si serverul se
opresc si dosarul se sterge (si la pornirea enigma2, porneste). O aplicatie din carusel nu ramane dupa un zap (nici dupa
unul cerut de ea), pornirea automata nu o porneste, iar o pornire cazuta nu se cerceteaza pe internet.

Partea de sus (hotarare_rosu, fel_tasta, taste_din_masca, canal_hbbtv, programe_hbbtv, config_hbbtv, adresa_dvb,
fereastra_valida, fereastra_vmpeg, text_mesaj, text_carusel, semn_ecran, urmare_rosu) nu importa enigma2, iar Controlor
primeste totul printr-un Mediu, deci se probeaza pe PC (test_hbbtv_h2.py, test_hbbtv_h3.py, test_hbbtv_h4_h6.py,
test_hbbtv_rosu_auto.py)."""

from __future__ import absolute_import

import json
import os
import re
import secrets
import shutil
import sys
import time
import zlib

PORNESTE, NIMIC, TIMESHIFT, CARUSEL, FARA_ADRESA = "porneste", "nimic", "timeshift", "carusel", "fara_adresa"
APLICATIE, RECEPTOR, INCHIDE = "aplicatie", "receptor", "inchide"

# codurile tastelor (linux/input-event-codes.h), asa cum le da enigma2 legaturilor eActionMap
KEY_1, KEY_0, KEY_ENTER = 2, 11, 28
KEY_UP, KEY_PAGEUP, KEY_LEFT, KEY_RIGHT, KEY_DOWN, KEY_PAGEDOWN = 103, 104, 105, 106, 108, 109
KEY_MUTE, KEY_VOLUMEDOWN, KEY_VOLUMEUP, KEY_POWER = 113, 114, 115, 116
KEY_PAUSE, KEY_STOP, KEY_PLAYPAUSE, KEY_REWIND, KEY_PLAY, KEY_FASTFORWARD = 119, 128, 164, 168, 207, 208
KEY_BACK, KEY_EXIT, KEY_OK, KEY_SELECT, KEY_INFO = 158, 174, 352, 353, 358
KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE = 398, 399, 400, 401
KEY_CHANNELUP, KEY_CHANNELDOWN, KEY_NEXT, KEY_PREVIOUS = 402, 403, 407, 412

TASTE_APLICATIE = frozenset([KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_OK, KEY_ENTER, KEY_SELECT, KEY_RED, KEY_GREEN,
	KEY_YELLOW, KEY_BLUE, KEY_BACK] + list(range(KEY_1, KEY_0 + 1)))
TASTE_RECEPTOR = frozenset([KEY_MUTE, KEY_VOLUMEDOWN, KEY_VOLUMEUP, KEY_POWER, KEY_CHANNELUP, KEY_CHANNELDOWN])

# Keyset (OIPF DAE 7.2.5.1): bitii mastii si tastele telecomenzii fiecaruia. ALPHA (0x200) nu are taste pe
# telecomanda, OTHER (0x400) nu e in HbbTV 1.5 (anexa A): masca cea mai mare e 0x1FF.
MASCA_RED, MASCA_GREEN, MASCA_YELLOW, MASCA_BLUE = 0x1, 0x2, 0x4, 0x8
MASCA_NAVIGATION, MASCA_VCR, MASCA_SCROLL, MASCA_INFO, MASCA_NUMERIC = 0x10, 0x20, 0x40, 0x80, 0x100
MASCA_MAXIM = 0x1FF
TASTE_PE_BIT = {
	MASCA_RED: (KEY_RED,),
	MASCA_GREEN: (KEY_GREEN,),
	MASCA_YELLOW: (KEY_YELLOW,),
	MASCA_BLUE: (KEY_BLUE,),
	# VK_UP, VK_DOWN, VK_LEFT, VK_RIGHT, VK_ENTER, VK_BACK
	MASCA_NAVIGATION: (KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_OK, KEY_ENTER, KEY_SELECT, KEY_BACK),
	# VK_PLAY, VK_PAUSE, VK_STOP, VK_NEXT, VK_PREV, VK_FAST_FWD, VK_REWIND, VK_PLAY_PAUSE
	MASCA_VCR: (KEY_PLAY, KEY_PAUSE, KEY_STOP, KEY_NEXT, KEY_PREVIOUS, KEY_FASTFORWARD, KEY_REWIND, KEY_PLAYPAUSE),
	MASCA_SCROLL: (KEY_PAGEUP, KEY_PAGEDOWN),
	MASCA_INFO: (KEY_INFO,),
	MASCA_NUMERIC: tuple(range(KEY_1, KEY_0 + 1)),
}

# flagurile enigma2 (apasare, ridicare, repetare) -> valoarea evdev trimisa navigatorului; lunga si ASCII nu se trimit
VALOARE_TASTA = {0: 1, 1: 0, 2: 2}
PRIORITATE_TASTE = -0x7FFFFFFF

VERIFICARE_MS = 2000
MEMORIE_OPRIRE_KB = 50 * 1024
ROSU_DUPA_MS = 1000         # fara strat (H2): VK_RED la atat dupa ce aplicatia e pe ecran
# AUTOSTART cu stratul: VK_RED abia cand aplicatia e gata, adica la ROSU_DUPA_ARATA_MS dupa Application.show() (ARD si
# ZDF cheama show() dupa ce si-au citit configurarea si si-au pus Keyset-ul; un VK_RED mai devreme se pierde, masurat
# pe receptor cu ProSieben si SAT.1), sau, daca aplicatia asteapta ROSU ca sa se arate, la ROSU_FARA_ARATA_MS dupa prima
# pagina. O singura data: ARD comuta ascuns/aratat la fiecare ROSU.
ROSU_DUPA_ARATA_MS = 500
ROSU_FARA_ARATA_MS = 6000
# Unele aplicatii se deschid direct cu tot ecranul si iau ROSU drept "inchide" (Anixe LinearToVOD: Anixe+ s-a aratat si
# s-a inchis singura la ROSU-ul de mai sus). Daca aplicatia se inchide singura (destroyApplication, window.close) la cel
# mult INCHISA_DUPA_ROSU_S dupa VK_RED trimis de receptor, se incarca din nou, o singura data, fara el.
REIA_FARA_ROSU = True
INCHISA_DUPA_ROSU_S = 3
# ROSU-ul urmarit (vezi sus): masurat pe receptor, semnul SUPER RTL = 272 de puncte din 32400 (0,8%), semnul ARD 11%,
# Startleiste ARD, ghidul SUPER RTL si portalul sixx 72-100%
ROSU_PAS_MS = 250            # cat de des se citeste ecranul dupa VK_RED trimis de receptor
ROSU_DESEN_MINIM = 20        # puncte opace (din esantion) de la care pe ecran "e ceva"
ROSU_SEMN_MARE = 0.25        # de atat din ecran incolo e un meniu deschis (o reactie), nu semnul de ROSU
ROSU_REACTIE_MS = 2500       # ecranul avea ceva: neschimbat atat dupa VK_RED -> inca un VK_RED
ROSU_SEMN_MAXIM_MS = 8000    # ecranul era gol: cat se asteapta semnul aplicatiei
SEMN_PAS = 8                 # semn_ecran: un rand din atatea si un punct din atatea pe rand
CURAT_MS = 150
TERMEN_ARATA_MS = 10000      # de la prima pagina pana la Application.show()
TERMEN_ZAP_S = 8             # dupa un zap cerut de aplicatie: pana la AIT-ul canalului nou
IGNORA_ZAP_S = 3             # evenimentele canalului dupa un stop/start/zap cerut de aplicatie nu o inchid
DISTRUGE_DUPA_APLICATIE_S = 5  # destroyApplication() al documentului vechi, imediat dupa createApplication() acceptat
LISTA_MAXIM = 500            # canalele buchetului de acum date paginii (ChannelConfig.channelList)

# pornirea automata si paza ei
AUTOMAT_DUPA_MS = 1500       # dupa AIT-ul canalului (sau o inchidere): verificarea pornirii automate
# inchiderile date de canal, dupa care o aplicatie pornita automat (nevazuta) se poate porni din nou
INCHIDERI_DE_CANAL = ("canalul schimbat", "nesemnalata in canalul nou", "fara AIT in canalul nou",
	"nesemnalata in canalul cerut de ea", "fara AIT in canalul cerut de ea")
MEMORIE_AUTOSTART_KB = 250 * 1024   # pornirea automata numai cu atata memorie libera (o aplicatie ia ~110-200 MB)
MEMORIE_FUNDAL_KB = 120 * 1024      # aplicatia nevazuta se opreste sub atat (lasa memoria, inainte de MEMORIE_OPRIRE_KB)
MEMORIE_ROSU_KB = 150 * 1024        # ROSU apasat de om: sub atat, un mesaj (pragul navigatorului, lansator.MEMORIE_MINIMA_KB)
OPRESTE_LA_INREGISTRARE = True      # cat ruleaza o inregistrare HbbTV nu porneste si se opreste

# caruselul DSM-CC (aplicatiile numai prin carusel)
TERMEN_CARUSEL_S = 30        # de la ROSU: cat se asteapta caruselul intreg (apoi porneste cu ce e, daca are pornirea)
CARUSEL_PAS_MS = 400         # verificarea caruselului cat se incarca
ADRESA_LOCALA = "http://127.0.0.1:"   # adresele serverului local al caruselului

# fereastra video (coordonatele aplicatiilor HbbTV si nodurile decodorului 0)
VIDEO_LATIME_CSS, VIDEO_INALTIME_CSS = 1280, 720
VIDEO_MINIM_CSS = 32         # un dreptunghi mai mic (sau ascuns, 0x0) = imaginea pe tot ecranul
VMPEG = "/proc/stb/vmpeg/0"
# La inchiderea unei aplicatii cu fereastra video: dupa ce imaginea canalului s-a pus pe tot ecranul, navigatorul isi
# goleste stratul abia dupa atatea ms. Decodorul schimba fereastra la o imagine urmatoare (la 50 de imagini pe secunda,
# 20 ms una), iar stratul golit se vede pe loc; fara asteptare imaginea mica ar putea ramane la vedere o imagine-doua.
INCHIDERE_ASTEAPTA_MS = 60

# filmele aplicatiilor (obiectul A/V, OIPF DAE 7.14): starile playState si codurile error ale obiectului
AV_OPRIT, AV_REDA, AV_PAUZA, AV_CONECTARE, AV_ASTEAPTA, AV_GATA, AV_EROARE = 0, 1, 2, 3, 4, 5, 6
AV_ACTIV = (AV_REDA, AV_PAUZA, AV_CONECTARE, AV_ASTEAPTA)
AV_E_FORMAT, AV_E_LEGATURA, AV_E_NESTIUTA, AV_E_RESURSE = 0, 1, 2, 3
# tipurile de film primite (atributul type al obiectului); playerul receptorului (serviciul 4097) le reda pe toate
AV_TIPURI = frozenset(["video/mp4", "audio/mp4", "video/mpeg", "audio/mpeg", "audio/mp3", "application/dash+xml",
	"application/vnd.apple.mpegurl", "application/x-mpegurl"])
AV_TIP_SERVICIU = 4097
AV_ADRESA_MAXIM = 2048
AV_PAS_MS = 500              # cat de des se citesc pozitia si starea playerului cat merge filmul
AV_POZITIE_PAS_MS = 1000     # pozitia trimisa paginii cel mult o data pe atat (o stare noua pleaca pe loc)
AV_TERMEN_CONECTARE_S = 30   # filmul care nu a inceput in atat: eroarea "nu se poate lega"
AV_BUFER_GATA = 100          # procentul tamponului de la care filmul merge din nou (evBuffering)
AV_PISTE_MAXIM = 16

UTILIZATOR = "hdsnav"
DOSAR_ACASA = "/var/lib/hds-navigator"
DOSAR_DATE = "/var/lib/hds-navigator/hbbtv"
DOSAR_CACHE = "/tmp/hds-hbbtv-cache"
# cache-ul WebKit al aplicatiilor sta in /tmp (tmpfs, adica in memoria receptorului) si creste cu fiecare aplicatie
# (82 MB dupa ~400 de aplicatii la parcurgerea satelitilor pe receptor): la pornirea unei aplicatii, peste atat se goleste
CACHE_MAXIM_KB = 32 * 1024
PRODUCATOR = "HD Satelit"


def N_(text):
	return text


def _(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


TEXTE = {
	TIMESHIFT: N_("Aplicațiile HbbTV nu pornesc cât timeshift-ul e pornit."),
	CARUSEL: N_("Aplicația HbbTV a acestui canal vine din semnalul altui canal și receptorul nu o poate încărca de aici."),
	# caruselul DSM-CC: cat se incarca (fereastra mica) si de ce nu a pornit
	"carusel-incarca": N_("HbbTV: se încarcă aplicația din satelit..."),
	"carusel-progres": N_("HbbTV: se încarcă aplicația din satelit (%(gata)d din %(toate)d părți)..."),
	"carusel-criptat": N_("Aplicația HbbTV a acestui canal nu vine din satelit: pista ei e criptată sau semnalul lipsește."),
	"carusel-semnal": N_("Aplicația HbbTV a acestui canal nu s-a încărcat întreagă din satelit: semnalul e prea slab."),
	"carusel-prea-mare": N_("Aplicația HbbTV a acestui canal e prea mare pentru memoria receptorului."),
	"carusel-fara-pornire": N_("Aplicația HbbTV din satelit nu are pagina de pornire anunțată de canal."),
	"carusel-eroare": N_("Aplicația HbbTV din satelit nu se poate citi acum din semnalul canalului."),
	FARA_ADRESA: N_("Aplicația HbbTV a acestui canal nu are o adresă pe internet."),
	"memorie-oprire": N_("Memoria liberă a receptorului a scăzut, așa că aplicația HbbTV s-a închis."),
	"nu-a-pornit": N_("Aplicația HbbTV nu a pornit."),
	# aplicatia pornise (prima pagina venise, de obicei se si vedea) si navigatorul s-a oprit dupa: nu "nu a pornit"
	"s-a-inchis": N_("Aplicația HbbTV s-a închis."),
	# destroyApplication sau window.close() inainte de prima aratare (Anixe, Aristo TV pe 19,2E)
	"s-a-inchis-singura": N_("Aplicația HbbTV a canalului s-a închis singură, înainte să se arate."),
	"ocupat": N_("Navigatorul web e deschis. Închide-l, apoi apasă din nou ROȘU."),
	# parcurgerea tuturor satelitilor (51 de canale): aplicatiile care nu cheama show() sunt de obicei numai de fundal
	# (masurare de audienta) sau pagini goale la post; al doilea ROSU nu le arata
	"nu-s-a-aratat": N_("Aplicația HbbTV a canalului nu s-a arătat pe ecran. Unele aplicații lucrează numai în fundal, fără nimic de arătat."),
	# paza pornirii automate
	"inregistrare": N_("Aplicațiile HbbTV nu pornesc cât rulează o înregistrare."),
	"inregistrare-oprire": N_("A început o înregistrare, așa că aplicația HbbTV s-a închis."),
	"memorie-pornire": N_("Memoria liberă a receptorului nu ajunge acum pentru aplicația HbbTV."),
	# motivul (Components/HdsHbbtvAplicatii.motiv), "motiv-" + cod
	"motiv-audienta": N_("Aplicația HbbTV a acestui canal e folosită numai pentru măsurarea audienței și nu are nimic de arătat pe ecran."),
	"motiv-pagina-goala": N_("Aplicația HbbTV a acestui canal e o pagină goală: postul nu a pus nimic în ea."),
	"motiv-pagina-mutata": N_("Aplicația HbbTV a acestui canal nu mai este la adresa anunțată de post: pagina a fost mutată sau ștearsă."),
	"motiv-adresa-inexistenta": N_("Adresa aplicației HbbTV a acestui canal nu mai există pe internet."),
	"motiv-fara-internet": N_("Receptorul nu are acces la internet, iar aplicațiile HbbTV vin de pe internet."),
	"motiv-numai-televizoare": N_("Aplicația HbbTV a acestui canal se deschide numai pe anumite televizoare și nu a primit receptorul."),
	"motiv-albastru": N_("Aplicația HbbTV a acestui canal pornește cu tasta ALBASTRU. Apasă ALBASTRU."),
	"motiv-consimtamant": N_("Aplicația HbbTV a acestui canal începe cu o întrebare de consimțământ care nu se vede pe ecran. De obicei trece singură în jumătate de minut."),
	"motiv-criptat": N_("Canalul e criptat și receptorul nu îl poate decripta acum, iar aplicația lui HbbTV nu s-a deschis."),
}

# cat asteapta mesajul cercetarea motivului (pe firul ei); apoi se arata ce se stie, iar restul ajunge numai in web
MOTIV_ASTEPTARE_S = 4.0
MOTIV_TOTAL_S = 25.0
MOTIV_PAS_MS = 250


def _jurnal(text):
	print("[HdsHbbtvPornire] %s" % text)


def hotarare_rosu(rez, timeshift=False):
	"""Ce face ROSU pe canalul redat, dupa HdsHbbtv.rezumat(): (PORNESTE, adresa), (NIMIC, "") cand nu e nicio
	aplicatie de pornit (ROSU ramane cum era), (TIMESHIFT, ""), (CARUSEL, "") cand aplicatia vine numai prin carusel
	(sau are o adresa dvb://: Controlor.rosu porneste atunci caruselul, daca e pe acest serviciu), (FARA_ADRESA, "")."""
	if not rez or rez.get("are_hbbtv") is not True or rez.get("aleasa") is None:
		return NIMIC, ""
	if timeshift:
		return TIMESHIFT, ""
	url = rez.get("url") or ""
	if rez.get("numai_carusel") or url.lower().startswith("dvb:"):
		return CARUSEL, ""
	if not url.lower().startswith(("http://", "https://")):
		return FARA_ADRESA, ""
	return PORNESTE, url


def taste_din_masca(masca):
	"""Tastele telecomenzii (coduri evdev) pe care masca Keyset le da aplicatiei."""
	rez = set()
	for bit, taste in TASTE_PE_BIT.items():
		if masca & bit:
			rez.update(taste)
	return frozenset(rez)


def fel_tasta(cod, aratat, masca=None, ascunsa=False):
	"""Unde merge o tasta cat aplicatia e deschisa: APLICATIE, RECEPTOR, INCHIDE sau NIMIC (vezi antetul).
	masca None (fara stratul H3): tastele aplicatiei din H2 (TASTE_APLICATIE); altfel numai tastele din masca.
	aratat: aplicatia e pe ecran; ascunsa: aplicatia ruleaza ascunsa (dupa hide()): tastele din masca merg la ea,
	restul la enigma2. Cat se incarca (nici aratata, nici ascunsa) numai EXIT e al aplicatiei."""
	if cod == KEY_EXIT:
		return INCHIDE
	if cod in TASTE_RECEPTOR:
		return RECEPTOR
	if masca is None:
		if not aratat:
			return RECEPTOR
		return APLICATIE if cod in TASTE_APLICATIE else NIMIC
	if cod in taste_din_masca(masca):
		return APLICATIE if (aratat or ascunsa) else RECEPTOR
	return NIMIC if aratat else RECEPTOR


def text_mesaj(fel, traducere=None):
	t = traducere or (lambda s: s)
	return t(TEXTE[fel]) if fel in TEXTE else ""


def text_carusel(gata, toate, traducere=None):
	"""Fereastra mica cat se incarca aplicatia din carusel: partile (modulele) venite din cate, cand se stie cate sunt,
	apoi "EXIT: renunta"."""
	t = traducere or (lambda s: s)
	x = t(TEXTE["carusel-incarca"])
	if isinstance(toate, int) and toate > 0 and isinstance(gata, int):
		valori = {"gata": min(max(gata, 0), toate), "toate": toate}
		try:
			x = t(TEXTE["carusel-progres"]) % valori
		except (TypeError, ValueError, KeyError):
			x = TEXTE["carusel-progres"] % valori
	return x + "\n" + t("EXIT: renunță")


def text_motiv(fel, cod, baza="", traducere=None, text=None):
	"""Mesajul cu motivul: fel "nu-s-a-aratat" = numai motivul (sau textul de pana acum); "nu-a-pornit" si
	"s-a-inchis-singura" = fraza lor, apoi motivul (sau `baza`, textul erorii navigatorului, deja tradus). `text`: textul
	motivului dat deja tradus (ceasul receptorului, din Components/HdsCeasHttps), in locul celui din TEXTE."""
	t = traducere or (lambda s: s)
	motiv = text or (text_mesaj("motiv-" + cod, t) if cod else "")
	if fel == "nu-s-a-aratat":
		return motiv or text_mesaj(fel, t)
	inceput = text_mesaj(fel, t)
	rest = motiv or baza
	return inceput + ("\n\n" + rest if rest else "")


# ---------------------------------------------------------------- starea data paginii (curat, fara enigma2)

# OIPF DAE 7.13.11.1: Channel.idType si channelType
ID_DVB_C, ID_DVB_S, ID_DVB_T = 10, 11, 12
TYPE_TV, TYPE_RADIO = 0, 1
TIPURI_RADIO = frozenset([0x02, 0x0A])
TIPURI_HD = frozenset([0x11, 0x19, 0x1F, 0x20])
ID_DVB_EVENT = 1

LIMBA_3 = {"ro": "ron", "en": "eng", "de": "deu", "fr": "fra", "it": "ita", "es": "spa", "pt": "por", "hu": "hun",
	"cs": "ces", "pl": "pol", "nl": "nld", "ru": "rus", "tr": "tur", "bg": "bul", "el": "ell", "uk": "ukr", "sk": "slk",
	"sr": "srp", "hr": "hrv", "sl": "slv", "sv": "swe", "da": "dan", "fi": "fin", "no": "nor", "ar": "ara"}
TARA_3 = {"RO": "ROU", "MD": "MDA", "DE": "DEU", "AT": "AUT", "CH": "CHE", "GB": "GBR", "IE": "IRL", "FR": "FRA",
	"BE": "BEL", "IT": "ITA", "ES": "ESP", "PT": "PRT", "HU": "HUN", "CZ": "CZE", "SK": "SVK", "PL": "POL", "NL": "NLD",
	"RU": "RUS", "TR": "TUR", "BG": "BGR", "GR": "GRC", "UA": "UKR", "US": "USA"}
TARA_LIMBII = {"ro": "RO", "en": "GB", "de": "DE", "fr": "FR", "it": "IT", "es": "ES", "pt": "PT", "hu": "HU",
	"cs": "CZ", "pl": "PL", "nl": "NL", "ru": "RU", "tr": "TR"}


def parte_ref(ref):
	"""Referinta unui canal DVB ("1:0:19:283D:3FB:1:C00000:0:0:0:") -> {"tip", "sid", "tsid", "onid", "ns"}, sau None
	pentru orice altceva (dosare, marcaje, fluxuri din retea, fisiere)."""
	p = (ref or "").split(":")
	if len(p) < 10 or p[0] != "1":
		return None
	try:
		v = [int(x or "0", 16) for x in p[1:7]]
	except ValueError:
		return None
	steaguri, tip, sid, tsid, onid, ns = v
	if steaguri & (0x07 | 0x40 | 0x80) or not sid or (len(p) > 10 and p[10]):
		return None
	return {"tip": tip, "sid": sid, "tsid": tsid, "onid": onid, "ns": ns}


def ccid_ref(ref):
	"""ccid-ul unui canal (Channel.ccid): spatiul de nume, onid, tsid, sid in hex, ca referinta sa se poata reface."""
	r = parte_ref(ref)
	return "ccid:%x.%x.%x.%x" % (r["ns"], r["onid"], r["tsid"], r["sid"]) if r else None


def canal_hbbtv(ref, nume="", numar=None):
	"""Canalul pentru pagina (proprietatile Channel din OIPF DAE 7.13.11), sau None pentru ce nu e canal DVB."""
	r = parte_ref(ref)
	if r is None:
		return None
	sus = r["ns"] >> 16
	c = {"channelType": TYPE_RADIO if r["tip"] in TIPURI_RADIO else TYPE_TV,
		"idType": ID_DVB_C if sus == 0xFFFF else ID_DVB_T if sus == 0xEEEE else ID_DVB_S,
		"ccid": ccid_ref(ref), "onid": r["onid"], "tsid": r["tsid"], "sid": r["sid"],
		"name": str(nume or "")[:80], "isHD": r["tip"] in TIPURI_HD}
	if isinstance(numar, int) and numar > 0:
		c["majorChannel"] = numar
	return c


def programe_hbbtv(evenimente, ref):
	"""EIT acum/urmeaza (dictionare {"nume", "scurt", "lung", "inceput", "durata", "id", "varsta"}) -> Programme
	(OIPF DAE 7.16.2: programmeIDType ID_DVB_EVENT, programmeID = dvb://onid.tsid.sid;event in hex)."""
	r = parte_ref(ref)
	rez = []
	for e in evenimente or ():
		if not isinstance(e, dict) or not e.get("nume"):
			continue
		p = {"name": str(e.get("nume"))[:200], "description": str(e.get("scurt") or "")[:500],
			"longDescription": str(e.get("lung") or "")[:2000], "programmeIDType": ID_DVB_EVENT,
			"channelID": ccid_ref(ref), "varsta": e.get("varsta") if isinstance(e.get("varsta"), int) else 0}
		for k, d in (("inceput", "startTime"), ("durata", "duration")):
			if isinstance(e.get(k), int):
				p[d] = e[k]
		if r is not None and isinstance(e.get("id"), int):
			p["programmeID"] = "dvb://%x.%x.%x;%x" % (r["onid"], r["tsid"], r["sid"], e["id"])
		rez.append(p)
	return rez[:2]


def limbi_preferate(preferinte, limba3):
	"""Preferintele de sunet/subtitrare (Components/HdsPisteLimbi: coduri ISO 639-2, "receptor", "canal", "nimic")
	-> "ron,eng" (OIPF DAE 7.3.2: lista de coduri ISO 639-2 despartite prin virgula)."""
	rez = []
	for p in preferinte or ():
		cod = limba3 if p == "receptor" else p
		if isinstance(cod, str) and re.match(r"^[a-z]{3}$", cod) and cod not in rez:
			rez.append(cod)
	return ",".join(rez)


def config_hbbtv(limba, audio=(), subtitrari=(), model="", versiune="", memorie_kb=None, livrare=("DVB_S",),
		producator=PRODUCATOR):
	"""Configuration si LocalSystem pentru pagina: limbile preferate, tara (ISO 3166 alfa-3), producatorul, modelul,
	versiunea, memoria libera (getFreeMem, octeti), sistemele de receptie (ui_profile din xmlCapabilities)."""
	limba = str(limba or "ro")
	lb = limba.split("_")[0].lower()[:2]
	tara2 = limba.split("_")[1].upper() if "_" in limba else ""
	if tara2 not in TARA_3:
		tara2 = TARA_LIMBII.get(lb, "RO")
	limba3 = LIMBA_3.get(lb, "eng")
	return {"preferredAudioLanguage": limbi_preferate(audio, limba3) or limba3,
		"preferredSubtitleLanguage": limbi_preferate(subtitrari, limba3) or limba3,
		"preferredUILanguage": limba3, "countryId": TARA_3[tara2], "tara2": tara2,
		"vendorName": producator, "familyName": producator, "modelName": str(model or "")[:40],
		"softwareVersion": str(versiune or "")[:40], "hardwareVersion": "",
		"memorie": int(memorie_kb) * 1024 if isinstance(memorie_kb, int) and memorie_kb > 0 else 0,
		"livrare": [x for x in livrare if x in ("DVB_S", "DVB_C", "DVB_T")] or ["DVB_S"]}


def lipeste_url(baza, interogare, fragment):
	"""ETSI TS 102 796 cap. 9.2: interogarea din dvb:// se lipeste cu "&" la cea din AIT (sau o inlocuieste cand AIT-ul
	nu are), fragmentul din dvb:// il inlocuieste pe cel din AIT."""
	baza, _d, frag_ait = baza.partition("#")
	if interogare:
		baza += ("&" if "?" in baza else "?") + interogare
	f = fragment if fragment else frag_ait
	return baza + ("#" + f if f else "")


def _server():
	try:
		from Components import HdsCaruselServer as S
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsCaruselServer as S
	return S


def adresa_dvb(url, aplicatii, carusel=None):
	"""createApplication("dvb://current.ait/<org>.<app>[?q][#f]", numere hex): (adresa HTTP a aplicatiei din AIT-ul
	canalului, cu interogarea si fragmentul lipite, aplicatia) sau (None, None) daca nu e in AIT, nu se poate porni
	(KILL, DISABLED) sau vine numai prin carusel. carusel: info() al caruselului servit acum (aplicatia de acum vine din
	el): o aplicatie numai prin acelasi carusel da adresa ei locala, iar o adresa dvb:// intreaga a caruselului
	(dvb://<onid>.<tsid>.<sid>.<tag>/<cale>) da (adresa locala, None)."""
	m = re.match(r"^dvb://current\.ait/([0-9a-fA-F]{1,8})\.([0-9a-fA-F]{1,4})(?:\?([^#]*))?(?:#(.*))?$", url or "", re.I)
	if not m:
		local = _server().din_dvb(url, carusel) if carusel else None
		return (local, None) if local else (None, None)
	org, app = int(m.group(1), 16), int(m.group(2), 16)
	try:
		from Components import HdsHbbtv as H
	except ImportError:
		import HdsHbbtv as H
	for a in aplicatii or ():
		if a.get("org") == org and a.get("id") == app and a.get("cod") in (H.COD_AUTOSTART, H.COD_PRESENT):
			baza = H.url_complet(a)
			if not baza.lower().startswith(("http://", "https://")):
				baza = _server().adresa_aplicatie(a, carusel) if carusel else None
				if not baza:
					return None, None
			return lipeste_url(baza, m.group(3), m.group(4)), a
	return None, None


def de_pornit_prin_dvb(aplicatii, carusel=None):
	"""[[org, app], ...] ale aplicatiilor din AIT pe care createApplication("dvb://current.ait/<org>.<app>") le poate
	porni acum (aceeasi regula ca adresa_dvb), pentru stratul JS (app.ait): o adresa dvb spre o aplicatie care lipseste
	de aici primeste null pe loc, ca pe televizor, iar aplicatia trece singura pe adresa ei http (bara ARD de pe Das
	Erste porneste mediateca cu "dvb://current.ait/13.14?...", aplicatie care nu e in AIT-ul canalului). None cand AIT-ul
	nu are nicio aplicatie de pornit (atunci stratul JS lasa raspunsul pe seama lui adresa_dvb, ca inainte)."""
	lista = []
	for a in aplicatii or ():
		org, app = a.get("org"), a.get("id")
		if not isinstance(org, int) or not isinstance(app, int) or [org, app] in lista:
			continue
		if adresa_dvb("dvb://current.ait/%x.%x" % (org, app), aplicatii, carusel)[0]:
			lista.append([org, app])
	return lista or None


def semnalata(stare_ait, aplicatie):
	"""Aplicatia (org, id) e in AIT-ul citit cu AUTOSTART sau PRESENT (cap. 6.2.2.2/6.2.2.3: numai org si app conteaza)."""
	if not aplicatie:
		return False
	return any(a.get("org") == aplicatie[0] and a.get("id") == aplicatie[1] and a.get("cod") in (0x01, 0x02)
		for a in (stare_ait or {}).get("aplicatii") or ())


def cauta_in_lista(lista, onid, tsid, sid):
	"""Referinta canalului cu onid/sid (si tsid, daca e dat, >= 0) din lista [(referinta, nume)], sau None."""
	for ref, _nume in lista or ():
		r = parte_ref(ref)
		if r and r["onid"] == onid and r["sid"] == sid and (tsid < 0 or r["tsid"] == tsid):
			return ref
	return None


# ---------------------------------------------------------------- fereastra video (curat, fara enigma2)

def fereastra_valida(argumente):
	"""Argumentele comenzii paginii "fereastra x y l i" -> (x, y, l, i) numere intregi (puncte CSS ale paginii de
	1280x720), sau None daca nu sunt exact 4 numere intregi in limite (x, y intre -1 si 2 ecrane, l, i intre 0 si 2
	ecrane). Nimic altceva din pagina nu ajunge la decodor."""
	if not argumente or len(argumente) != 4:
		return None
	v = []
	for a in argumente:
		if not isinstance(a, str) or not re.match(r"^-?[0-9]{1,5}$", a):
			return None
		v.append(int(a))
	x, y, l, i = v
	w, h = VIDEO_LATIME_CSS, VIDEO_INALTIME_CSS
	if not (-w <= x <= 2 * w and -h <= y <= 2 * h and 0 <= l <= 2 * w and 0 <= i <= 2 * h):
		return None
	return x, y, l, i


def fereastra_vmpeg(fereastra):
	"""(x, y, l, i) in puncte CSS 1280x720 -> (left, top, width, height) in 720x576 pentru /proc/stb/vmpeg/0/dst_*, cu
	rotunjirea din lib/gui/evideo.cpp (marginile la punctul cel mai apropiat), taiat la ecran. None = imaginea pe tot
	ecranul: fara fereastra, partea de pe ecran mai mica de VIDEO_MINIM_CSS, sau cat tot ecranul. Latimea si inaltimea nu
	ies niciodata 0 (pentru driver, 0 inseamna ecran intreg)."""
	if not fereastra:
		return None
	x, y, l, i = fereastra
	w, h = VIDEO_LATIME_CSS, VIDEO_INALTIME_CSS
	x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + l, w), min(y + i, h)
	if x1 - x0 < VIDEO_MINIM_CSS or y1 - y0 < VIDEO_MINIM_CSS:
		return None
	left, top = (x0 * 720 + w // 2) // w, (y0 * 576 + h // 2) // h
	right, bottom = (x1 * 720 + w // 2) // w, (y1 * 576 + h // 2) // h
	if left <= 0 and top <= 0 and right >= 720 and bottom >= 576:
		return None
	return left, top, max(1, right - left), max(1, bottom - top)


def scrie_fereastra_video(f, cale=VMPEG):
	"""(left, top, width, height) in 720x576, sau None = ecran intreg (0 0 0 0), in cale/dst_left|top|width|height (hex,
	"%08x", ca lib/gui/evideo.cpp), apoi cale/dst_apply. False fara noduri (emulatorul) sau cand scrierea cade."""
	if not os.path.isdir(cale):
		return False
	try:
		for nume, x in zip(("left", "top", "width", "height"), f or (0, 0, 0, 0)):
			with open(os.path.join(cale, "dst_" + nume), "w", encoding="utf-8") as fisier:
				fisier.write("%08x\n" % x)
		with open(os.path.join(cale, "dst_apply"), "w", encoding="utf-8") as fisier:
			fisier.write("%08x\n" % 1)
		return True
	except (IOError, OSError) as e:
		_jurnal("fereastra video: %s" % e)
		return False


def video_intreg_la_pornire(cale=VMPEG):
	"""La pornirea enigma2: o fereastra video lasata mica (o aplicatie HbbTV deschisa la o cadere a interfetei; driverul
	o tine si peste repornirea enigma2) se pune pe tot ecranul. True daca a fost nevoie."""
	try:
		marimi = []
		for nume in ("width", "height"):
			with open(os.path.join(cale, "dst_" + nume), encoding="utf-8") as fisier:
				marimi.append(int(fisier.read().strip() or "0", 16))
	except (IOError, OSError, ValueError):
		return False
	if not any(marimi):
		return False
	_jurnal("fereastra video ramasa mica (%dx%d din 720x576) pusa pe tot ecranul" % tuple(marimi))
	return scrie_fereastra_video(None, cale)


# ---------------------------------------------------------------- filmele aplicatiilor (curat, fara enigma2)

_AV_ADRESA = re.compile(r"^https?://[^\s/?#@]+(?:[/?#]\S*)?$", re.I)


def av_adresa_buna(url):
	"""Adresa unui film cerut de pagina: http sau https, cel mult AV_ADRESA_MAXIM semne, fara spatii, semne de control
	sau nume si parola in gazda."""
	if not url or len(url) > AV_ADRESA_MAXIM or not _AV_ADRESA.match(url):
		return False
	return not any(ord(c) < 0x21 or ord(c) == 0x7F for c in url)


def av_tip(tip):
	"""Tipul filmului (atributul type al obiectului A/V), daca playerul il reda; altfel None."""
	t = (tip or "").strip().lower()
	return t if t in AV_TIPURI else None


def av_eroare(cod_player, pornit):
	"""Codul error al obiectului A/V dupa eroarea playerului (evUser+10/+11: codec refuzat, +12: element lipsa, +16:
	orice alta eroare) si dupa cum filmul incepuse sau nu."""
	if cod_player in (10, 11, 12):
		return AV_E_FORMAT
	return AV_E_NESTIUTA if pornit else AV_E_LEGATURA


_AV_DESCRIERE_AD = re.compile(r"audiodes|audio ?descr|deskription|\bAD\b|\bqad\b", re.I)


def av_piste_pagina(piste):
	"""Pistele de sunet ale filmului pentru pagina (AVAudioComponent): [{index, limba, ad, canale, cod, activa}]; limba
	ca in pista (de obicei codul ISO 639-2), descrierea audio dupa limba "qad" sau dupa descriere."""
	rez = []
	for p in (piste or [])[:AV_PISTE_MAXIM]:
		try:
			i = int(p.get("index"))
		except (TypeError, ValueError, AttributeError):
			continue
		limba = re.sub(r"[^A-Za-z-]", "", str(p.get("limba") or ""))[:8].lower()
		descriere = str(p.get("descriere") or "")[:40]
		cod = re.sub(r"[^A-Za-z0-9 .+-]", "", descriere)[:16]
		ad = limba == "qad" or bool(_AV_DESCRIERE_AD.search(descriere))
		canale = 6 if re.search(r"5\.1|6ch|ac-?3|e-?ac-?3|dts", descriere, re.I) else 2
		rez.append({"index": i, "limba": limba, "ad": ad, "canale": canale, "cod": cod, "activa": bool(p.get("activa"))})
	return rez


def av_comanda(a):
	"""Argumentele comenzii paginii "av <sub> ..." -> (sub, argumente curate) sau None. sub: porneste <id> <base64>
	<tip>, viteza <0|1>, cauta <ms>, opreste, fereastra <x> <y> <l> <i>, ecran-intreg <0|1>, pista <index>."""
	if not a:
		return None
	sub = a[0]
	if sub == "porneste" and len(a) == 4:
		ident = _intreg(a[1])
		return (sub, [ident, a[2], a[3]]) if ident is not None and ident >= 0 else None
	if sub in ("viteza", "ecran-intreg") and len(a) == 2 and a[1] in ("0", "1"):
		return sub, [int(a[1])]
	if sub in ("cauta", "pista") and len(a) == 2:
		v = _intreg(a[1])
		return (sub, [v]) if v is not None and 0 <= v <= 0x7FFFFFFF else None
	if sub == "opreste" and len(a) == 1:
		return sub, []
	if sub == "fereastra" and len(a) == 5:
		v = fereastra_valida(a[1:])
		return (sub, [v]) if v is not None else None
	return None


def semn_ecran(fb, geometrie, pas=SEMN_PAS):
	"""Ce arata ecranul, pe scurt, pentru ROSU-ul urmarit: (puncte opace, crc32, puncte) pe pagina afisata a
	framebufferului, un rand din `pas` si pe fiecare rand un punct din `pas` (alfa > 0); crc32 peste randurile citite
	intregi, deci se schimba la orice schimbare din ele. `geometrie` = (latime, inaltime, stride, biti, y_pagina), ca
	osd_strat.geometrieDinSys; `fb.rand(y, stride, octeti)` ca osd_strat.Framebuffer. None fara geometrie, la alt format
	decat 32 de biti (BGRA) sau la un rand citit pe jumatate."""
	if not geometrie or pas < 1:
		return None
	latime, inaltime, stride, biti, y_pagina = geometrie
	if biti != 32 or latime <= 0 or inaltime <= 0 or stride < latime * 4:
		return None
	opaci = puncte = crc = 0
	for y in range(0, inaltime, pas):
		rand = fb.rand(y_pagina + y, stride, latime * 4)
		if len(rand) < latime * 4:
			return None
		alfa = rand[3::4 * pas]
		puncte += len(alfa)
		opaci += len(alfa) - alfa.count(0)
		crc = zlib.crc32(rand, crc)
	return (opaci, crc, puncte)


# ce urmeaza dupa un pas al ROSU-lui urmarit
ASTEAPTA, REACTIE, REPETA, RENUNTA = "asteapta", "reactie", "repeta", "renunta"
# cererile paginii care arata ca aplicatia a primit VK_RED (alta vizibilitate, inchiderea, alta aplicatie, alt canal);
# masca de taste numai cand isi schimba valoarea. Nu: leaga, elibereaza, opreste, fereastra, ecran-intreg, tradu (vin si
# singure, cat aplicatia se pregateste).
REACTII_ROSU = ("arata", "ascunde", "distruge", "aplicatie", "canal", "urmator", "anterior")
# cererile paginii dupa care filmul aplicatiei se opreste (canalul sau alta aplicatie iau decodorul)
AV_OPRIT_DE = ("leaga", "canal", "urmator", "anterior", "aplicatie")


def urmare_rosu(gol, semn0, semn, vazut, trecut_ms):
	"""Un pas al ROSU-lui urmarit (vezi ROSU-UL URMARIT): (fapta, vazut). gol: ecranul nu avea nimic la trimitere; semn0,
	semn: semn_ecran atunci si acum; vazut: de cate ori la rand s-a vazut deja semnul aplicatiei (pe ecranul gol);
	trecut_ms: de la trimitere. Fapta: ASTEAPTA, REACTIE (aplicatia a primit tasta), REPETA (inca un VK_RED) sau RENUNTA.
	Pagina noua, masca si cererile paginii le vede controlorul, nu aceasta functie."""
	if semn is None or semn0 is None:
		return RENUNTA, vazut
	if not gol:
		if semn[:2] != semn0[:2]:
			return REACTIE, 0
		return (REPETA if trecut_ms >= ROSU_REACTIE_MS else ASTEAPTA), 0
	opaci, puncte = semn[0], semn[2]
	if puncte and opaci >= puncte * ROSU_SEMN_MARE:
		return REACTIE, 0
	vazut = vazut + 1 if opaci >= ROSU_DESEN_MINIM else 0
	if vazut >= 2:
		return REPETA, vazut
	if trecut_ms >= ROSU_SEMN_MAXIM_MS:
		return RENUNTA, vazut
	return ASTEAPTA, vazut


def curata_cache(dosar=DOSAR_CACHE, maxim_kb=CACHE_MAXIM_KB):
	"""Cache-ul aplicatiilor HbbTV peste maxim_kb (fisierele socotite cu lstat, fara a urma legaturi) se goleste de tot;
	dosarul ramane, cu proprietarul lui. Se cheama numai cand niciun navigator nu ruleaza (Controlor._porneste, dupa
	verificarea lui activ()). Legaturile simbolice se sterg ca legaturi. -> kB socotiti pana la depasire (cel putin
	maxim_kb), sau 0 daca nu a fost nevoie."""
	try:
		intrari = os.listdir(dosar)
	except OSError:
		return 0
	# numaratoarea se opreste la prima depasire (firul enigma2, la ROSU: nu tot cache-ul de fiecare data)
	total, prag = 0, maxim_kb * 1024
	for radacina, _dosare, fisiere in os.walk(dosar):
		for nume in fisiere:
			try:
				total += os.lstat(os.path.join(radacina, nume)).st_size
			except OSError:
				pass
			if total > prag:
				break
		if total > prag:
			break
	if total <= prag:
		return 0
	for nume in intrari:
		cale = os.path.join(dosar, nume)
		try:
			if os.path.isdir(cale) and not os.path.islink(cale):
				shutil.rmtree(cale, ignore_errors=True)
			else:
				os.unlink(cale)
		except OSError:
			pass
	_jurnal("cache-ul aplicatiilor HbbTV golit (peste %d kB)" % maxim_kb)
	return total // 1024


def _textCeas(cod, rez):
	"""Motivul "ceas": textul ajutorului comun (Components/HdsCeasHttps), deja tradus, din cercetare; altfel None."""
	return (rez or {}).get("ceas") if cod == "ceas" else None


def _aplicatii():
	try:
		from Components import HdsHbbtvAplicatii as A
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsHbbtvAplicatii as A
	return A


def _hbbtv():
	try:
		from Components import HdsHbbtv as H
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsHbbtv as H
	return H


class Mediu(object):
	"""Legatura cu enigma2 (sesiunea, serviciul, ecranele); la probele de pe PC se inlocuieste."""

	def __init__(self, session):
		self.session = session

	def lansator(self):
		from Plugins.Extensions.HdsNavigator import lansator
		return lansator

	def setari_navigator(self):
		"""Desenul ales in setarile navigatorului (placa video sau numai procesorul) si setarea "HbbTV clar"."""
		try:
			from Plugins.Extensions.HdsNavigator import setari as S
			c = S.initConfig()
			return {"desen": c.desen.value, "hbbtv_clar": bool(c.hbbtv_clar.value)}
		except Exception:
			return {}

	def rezumat_canal(self):
		"""(rezumatul AIT al canalului redat, referinta lui ca text)."""
		H = _hbbtv()
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		return H.rezumat(self.stare_ait()), (ref.toString() if ref is not None else "")

	def stare_ait(self):
		"""Starea AIT a canalului redat (HdsHbbtv.din_info): pid, versiune, aplicatii."""
		from enigma import iServiceInformation
		service = self.session.nav.getCurrentService()
		return _hbbtv().din_info(service.info() if service is not None else None, iServiceInformation)

	def ref_curent(self):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		return ref.toString() if ref is not None else ""

	def timp(self):
		return time.time()

	def in_timeshift(self, bara=None):
		if bara is None:
			from Screens.InfoBar import InfoBar
			bara = InfoBar.instance
		return bool(getattr(bara, "timeshift_enabled", 0))

	def in_standby(self):
		try:
			from Screens import Standby
			return Standby.inStandby is not None
		except Exception:
			return False

	def bara_libera(self):
		"""Bara e fereastra de sus (nicio alta fereastra deschisa intre timp peste ea)."""
		try:
			from Screens.InfoBar import InfoBar
			return InfoBar.instance is not None and self.session.current_dialog is InfoBar.instance
		except Exception:
			return False

	def ascunde_bara(self):
		try:
			from Screens.InfoBar import InfoBar
			if InfoBar.instance is not None:
				InfoBar.instance.hide()
		except Exception as e:
			_jurnal("bara: %s" % e)

	def agent(self):
		H = _hbbtv()
		model = versiune = ""
		try:
			from Components.About import about
			model = about.getModel()
			versiune = about.getImageVersionString()
		except Exception:
			pass
		return H.agent_hbbtv(PRODUCATOR, model, versiune)

	def date_aplicatii(self):
		return _aplicatii().citeste_date()

	def agent_pentru(self, url):
		"""(partea HbbTV a User-Agent-ului, profilul sau None) pentru aplicatia de la url."""
		A = _aplicatii()
		return A.alege_agent(url, self.agent(), A.citeste_date())

	def cercetare(self, url, agent):
		"""Cercetarea motivului, pe firul ei (Components/HdsHbbtvAplicatii.Cercetare), cu agentul intreg al navigatorului."""
		A = _aplicatii()
		return A.Cercetare(url, A.PREFIX_WEBKIT + " " + agent)

	def canal_criptat(self):
		"""Canalul redat e criptat si nu se vede (verdictul ecranului negru, Components/HdsEcranNegru.py)."""
		try:
			from Components import HdsEcranNegru as E
			v = (E.ultima_stare() or {}).get("verdict") or {}
			return v.get("cod") == E.CRIPTAT
		except Exception:
			return False

	def jurnal_motiv(self, rand):
		"""Un rand in jurnalul erorilor navigatorului (/home/root/logs/hds-navigator.log)."""
		try:
			return self.lansator().Mediu().jurnal_erori(rand + "\n")
		except Exception as e:
			_jurnal("jurnalul erorilor: %s" % e.__class__.__name__)
			return False

	def ceas(self, functie):
		from enigma import eTimer
		t = eTimer()
		t.callback.append(functie)
		return t

	def harta_taste(self):
		from enigma import eActionMap
		return eActionMap.getInstance()

	def evenimente(self):
		from enigma import iPlayableService
		return tuple(x for x in (getattr(iPlayableService, n, None) for n in ("evStart", "evEnd")) if x is not None)

	def evenimente_info(self):
		"""(evenimentele dupa care se reciteste AIT-ul, evenimentele EIT acum/urmeaza)."""
		from enigma import iPlayableService
		ait = tuple(x for x in (getattr(iPlayableService, n, None) for n in ("evUpdatedInfo", "evHBBTVInfo"))
			if x is not None)
		eit = tuple(x for x in (getattr(iPlayableService, "evUpdatedEventInfo", None),) if x is not None)
		return ait, eit

	def asculta_nav(self, functie, da):
		lista = self.session.nav.event
		if da and functie not in lista:
			lista.append(functie)
		elif not da and functie in lista:
			lista.remove(functie)

	def memorie_libera_kb(self):
		return self.lansator().Mediu().memorie_libera_kb()

	# ------------------------------------------------ etapele H4 si H6

	def fereastra_video(self, f):
		"""Fereastra video a decodorului 0 ((left, top, width, height) in 720x576; None: ecran intreg)."""
		return scrie_fereastra_video(f)

	def asteapta_ms(self, ms):
		"""O asteptare scurta pe firul enigma2 (inchiderea cu fereastra video, INCHIDERE_ASTEAPTA_MS)."""
		time.sleep(ms / 1000.0)

	def semn_ecran(self):
		"""Ecranul pe scurt pentru ROSU-ul urmarit (semn_ecran), din /dev/fb0 cu cititorul stratului web (osd_strat: numai
		citire, marimea si pagina afisata din /sys); None fara framebuffer (emulatorul)."""
		from Plugins.Extensions.HdsWebControl import osd_strat as O
		fb = O.Framebuffer()
		try:
			return semn_ecran(fb, O.geometrieDinSys())
		finally:
			fb.inchide()

	# ------------------------------------------------ filmele aplicatiilor (obiectul A/V)

	def _serviciu(self):
		return self.session.nav.getCurrentService()

	def av_reda(self, url):
		"""Filmul de la url pe playerul receptorului (serviciul 4097, GStreamer: MP4, TS, DASH, HLS), in locul canalului,
		pe acelasi decodor si in aceeasi fereastra video. -> referinta lui ca text ("" daca nu a pornit)."""
		from enigma import eServiceReference
		r = eServiceReference(AV_TIP_SERVICIU, 0, url)
		r.setName("HbbTV")
		self.session.nav.playService(r, checkParentalControl=False)
		cur = self.session.nav.getCurrentlyPlayingServiceReference()
		return cur.toString() if cur is not None and cur.type == AV_TIP_SERVICIU else ""

	def av_opreste(self):
		self.session.nav.stopService()

	def av_pozitie(self):
		"""(pozitia, lungimea) filmului redat, in ms (lungimea 0 cand nu se stie, de pilda un flux viu), sau None."""
		s = self._serviciu()
		seek = s.seek() if s is not None else None
		if seek is None:
			return None
		p, l = seek.getPlayPosition(), seek.getLength()
		if not p or p[0]:
			return None
		lung = l[1] // 90 if l and not l[0] and l[1] > 0 else 0
		return max(0, int(p[1] // 90)), max(0, int(lung))

	def av_pauza(self, da):
		s = self._serviciu()
		p = s.pause() if s is not None else None
		if p is None:
			return False
		if da:
			p.pause()
		else:
			p.unpause()
		return True

	def av_cauta(self, ms):
		s = self._serviciu()
		seek = s.seek() if s is not None else None
		if seek is None or not seek.isCurrentlySeekable():
			return False
		seek.seekTo(int(ms) * 90)
		return True

	def av_bufer(self):
		"""Cat la suta din tampon e plin (evBuffering), sau None."""
		s = self._serviciu()
		st = s.streamed() if s is not None else None
		try:
			return int(st.getBufferCharge()[0]) if st is not None else None
		except Exception:
			return None

	def av_piste(self):
		"""Pistele de sunet ale filmului: [{index, limba, descriere, activa}]."""
		s = self._serviciu()
		a = s.audioTracks() if s is not None else None
		if a is None:
			return []
		rez, cur = [], a.getCurrentTrack()
		for i in range(min(a.getNumberOfTracks(), AV_PISTE_MAXIM)):
			info = a.getTrackInfo(i)
			rez.append({"index": i, "limba": info.getLanguage() or "", "descriere": info.getDescription() or "",
				"activa": i == cur})
		return rez

	def av_alege_pista(self, i):
		s = self._serviciu()
		a = s.audioTracks() if s is not None else None
		if a is None or not 0 <= i < a.getNumberOfTracks():
			return False
		a.selectTrack(i)
		return True

	def av_evenimente(self):
		"""Evenimentele playerului: {"eof", "bufer", "info", "erori": {eveniment: cod}} (erorile: evUser+10/11/12/16)."""
		from enigma import iPlayableService as E
		u = getattr(E, "evUser", None)
		erori = dict((u + c, c) for c in (10, 11, 12, 16)) if u is not None else {}
		return {"eof": getattr(E, "evEOF", None), "bufer": getattr(E, "evBuffering", None),
			"info": getattr(E, "evUpdatedInfo", None), "erori": erori}

	def hbbtv_pornit(self):
		"""Setarea principala „HbbTV” (config.plugins.hdsnavigator.hbbtv; HdsHbbtv.hbbtv_pornit)."""
		return _hbbtv().hbbtv_pornit()

	def autostart_pornit(self):
		"""Setarea „Pornirea automată a aplicațiilor HbbTV” (config.plugins.hdsnavigator.hbbtv_autostart)."""
		try:
			from Plugins.Extensions.HdsNavigator import setari as S
			return bool(S.initConfig().hbbtv_autostart.value)
		except Exception:
			return False

	def inregistrare_pornita(self):
		try:
			return bool(self.session.nav.getRecordings())
		except Exception:
			return False

	def utilizator(self):
		"""(nume, uid, gid) al utilizatorului fara root, sau None daca imaginea nu il are."""
		try:
			import pwd
			p = pwd.getpwnam(UTILIZATOR)
		except (ImportError, KeyError):
			return None
		return (UTILIZATOR, p.pw_uid, p.pw_gid) if p.pw_uid != 0 else None

	def dosare(self, utilizator=None):
		"""Dosarul de date (cookie-urile si datele aplicatiilor, pe disc) si cache-ul (in memorie), facute la nevoie si
		date utilizatorului fara root, daca e. Cache-ul peste CACHE_MAXIM_KB se goleste (niciun navigator nu ruleaza
		acum: Controlor._porneste a verificat)."""
		curata_cache(DOSAR_CACHE)
		for d in (DOSAR_ACASA, DOSAR_DATE, DOSAR_CACHE):
			try:
				if not os.path.isdir(d):
					os.makedirs(d, 0o700)
				if utilizator is not None:
					os.chown(d, utilizator[1], utilizator[2])
			except OSError as e:
				_jurnal("dosarul %s: %s" % (d, e))
		return DOSAR_DATE, DOSAR_CACHE

	# ------------------------------------------------ starea pentru stratul H3

	def canal_curent(self):
		"""(referinta canalului redat ca text, numele lui) sau ("", "")."""
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is None:
			return "", ""
		nume = ""
		try:
			from enigma import eServiceCenter
			info = eServiceCenter.getInstance().info(ref)
			nume = info.getName(ref) if info is not None else ""
		except Exception:
			pass
		return ref.toString(), (nume or "").replace("\x86", "").replace("\x87", "")

	def lista_canale(self, limita=LISTA_MAXIM):
		"""Canalele buchetului de acum din lista de canale ([(referinta, nume)]), fara dosare si marcaje."""
		rez = []
		try:
			from enigma import eServiceCenter
			from Screens.InfoBar import InfoBar
			sl = getattr(InfoBar.instance, "servicelist", None) if InfoBar.instance is not None else None
			root = sl.getRoot() if sl is not None else None
			lst = eServiceCenter.getInstance().list(root) if root is not None else None
			for ref, nume in (lst.getContent("SN", True) if lst is not None else None) or ():
				if parte_ref(ref) is not None:
					rez.append((ref, nume or ""))
					if len(rez) >= limita:
						break
		except Exception as e:
			_jurnal("lista canalelor: %s" % e)
		return rez

	def programe_canal(self):
		"""EIT acum si urmeaza pentru canalul redat."""
		rez = []
		try:
			service = self.session.nav.getCurrentService()
			info = service.info() if service is not None else None
			for i in (0, 1):
				ev = info.getEvent(i) if info is not None else None
				if ev is None:
					continue
				varsta = 0
				try:
					p = ev.getParentalData()
					r = p.getRating() if p is not None else 0
					varsta = r + 3 if 0 < r <= 0x0F else 0
				except Exception:
					pass
				rez.append({"nume": ev.getEventName() or "", "scurt": ev.getShortDescription() or "",
					"lung": ev.getExtendedDescription() or "", "inceput": int(ev.getBeginTime()),
					"durata": int(ev.getDuration()), "id": int(ev.getEventId()), "varsta": varsta})
		except Exception as e:
			_jurnal("EIT: %s" % e)
		return rez

	def config_hbbtv(self):
		limba, audio, sub, model, versiune = "ro_RO", (), (), "", ""
		try:
			from Components.Language import language
			limba = language.getLanguage() or limba
		except Exception:
			pass
		try:
			from Components import HdsPisteLimbi as PL
			audio, sub = PL.preferinteAudio(), PL.preferinteSubtitrare()
		except Exception:
			pass
		try:
			from Components.About import about
			model, versiune = about.getModel(), about.getImageVersionString()
		except Exception:
			pass
		livrare = ["DVB_S"]
		try:
			from Components.NimManager import nimmanager
			for tip, nume in (("DVB-C", "DVB_C"), ("DVB-T", "DVB_T")):
				if nimmanager.hasNimType(tip):
					livrare.append(nume)
		except Exception:
			pass
		return config_hbbtv(limba, audio, sub, model, versiune, self.memorie_libera_kb(), livrare)

	def zap_la(self, ref):
		"""Canalul cerut de aplicatie, prin lista de canale (ca ultimul canal si istoria sa ramana la zi) cand e in ea."""
		from enigma import eServiceReference
		r = eServiceReference(ref)
		try:
			from Screens.InfoBar import InfoBar
			sl = getattr(InfoBar.instance, "servicelist", None) if InfoBar.instance is not None else None
			if sl is not None:
				sl.setCurrentSelection(r)
				ales = sl.getCurrentSelection()
				if ales is not None and ales.toString() == r.toString():
					sl.zap()
					return True
		except Exception as e:
			_jurnal("zap prin lista: %s" % e)
		self.session.nav.playService(r)
		return True

	def zap_urmator(self, inainte=True):
		"""nextChannel/prevChannel: ca P+/P- in bara (canalul urmator/anterior din buchet)."""
		from Screens.InfoBar import InfoBar
		if InfoBar.instance is None:
			return False
		if inainte:
			InfoBar.instance.zapDown()
		else:
			InfoBar.instance.zapUp()
		return True

	def opreste_serviciu(self):
		"""video/broadcast stop(), setChannel(null), o aplicatie independenta de canal: canalul se opreste. -> referinta."""
		ref = self.ref_curent()
		if ref:
			self.session.nav.stopService()
		return ref

	def porneste_serviciu(self, ref):
		from enigma import eServiceReference
		self.session.nav.playService(eServiceReference(ref))

	def mesaj(self, text):
		from Screens.MessageBox import MessageBox
		try:
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=6)
		except Exception as e:
			_jurnal("mesaj: %s" % e)

	def arata_incarcare(self, da, text=None):
		"""Fereastra mica "se porneste aplicatia" (nemodala: bara si tastele ei raman active); text: altul
		(caruselul care se incarca), None = cel obisnuit."""
		if da:
			if getattr(self, "_incarcare", None) is None:
				self._incarcare = self.session.instantiateDialog(_ecrane()[0])
			try:
				self._incarcare["text"].setText(text or (_("HbbTV: se pornește aplicația canalului...") + "\n" +
					_("EXIT: renunță")))
			except Exception as e:
				_jurnal("fereastra mica: %s" % e)
			self._incarcare.show()
		elif getattr(self, "_incarcare", None) is not None:
			d, self._incarcare = self._incarcare, None
			d.hide()
			self.session.deleteDialog(d)

	def text_incarcare(self, text):
		"""Fereastra mica cu textul dat (caruselul care se incarca)."""
		self.arata_incarcare(True, text)

	def carusel(self, aplicatie, ref):
		"""Sesiunea caruselului aplicatiei pe canalul redat (Components/HdsCaruselServer.SesiuneCarusel, nepornita):
		demux-ul si PID-ul PMT ale serviciului redat (HdsAnalizaFlux.parametri), onid/tsid/sid din referinta."""
		from Components import HdsAnalizaFlux as AF
		r = parte_ref(ref)
		if r is None:
			return None
		p = AF.parametri(self.session.nav.getCurrentService(), ref)
		return _server().SesiuneCarusel(p.get("demux"), p.get("pmt_pid"), r["onid"], r["tsid"], r["sid"], aplicatie)

	def redeseneaza(self):
		"""Dupa ce enigma2 a luat inapoi fb0: o fereastra transparenta pe tot ecranul, aratata si ascunsa dupa CURAT_MS
		(doua desenari, deci amandoua paginile ecranului), ca nimic din pagina sa nu ramana pe ecran. O fereastra de
		la o redesenare de dinainte, inca aratata, se ascunde intai."""
		if getattr(self, "_curat", (None, None))[0] is not None:
			self._curat[1].stop()
			self._dupaCurat()
		try:
			d = self.session.instantiateDialog(_ecrane()[1])
			d.show()
		except Exception as e:
			_jurnal("redesenare: %s" % e)
			return
		# ceasul si fereastra raman tinute aici pana la ascundere (un eTimer fara referinta s-ar sterge inainte)
		self._curat = (d, self.ceas(self._dupaCurat))
		self._curat[1].start(CURAT_MS, True)

	def _dupaCurat(self):
		d = getattr(self, "_curat", (None, None))[0]
		try:
			if d is not None:
				d.hide()
				self.session.deleteDialog(d)
		except Exception as e:
			_jurnal("redesenare: %s" % e)
		self._curat = (None, None)


_ECRANE = []


def _ecrane():
	"""Ferestrele (facute o data, la prima folosire): HdsHbbtvIncarcare (mica, sus in dreapta) si HdsHbbtvCurat
	(transparenta, pe tot ecranul). Skinul le poate da; altfel cele de aici, dupa marimea ecranului."""
	if _ECRANE:
		return _ECRANE
	from enigma import getDesktop
	from Screens.Screen import Screen
	from Components.Label import Label
	s = getDesktop(0).size()
	latime, inaltime = s.width(), s.height()
	k = latime / 1920.0
	lw, lh = int(820 * k), int(140 * k)

	class HdsHbbtvIncarcare(Screen):
		skin = """<screen name="HdsHbbtvIncarcare" position="%d,%d" size="%d,%d" backgroundColor="#20101820" flags="wfNoBorder">
			<widget name="text" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00f0f0f0" transparent="1" valign="center" />
		</screen>""" % (latime - lw - int(60 * k), int(50 * k), lw, lh, int(20 * k), int(10 * k), lw - int(40 * k),
			lh - int(20 * k), int(28 * k))

		def __init__(self, session):
			Screen.__init__(self, session)
			self["text"] = Label(_("HbbTV: se pornește aplicația canalului...") + "\n" + _("EXIT: renunță"))

	class HdsHbbtvCurat(Screen):
		skin = """<screen name="HdsHbbtvCurat" position="0,0" size="%d,%d" backgroundColor="#ff000000" flags="wfNoBorder" />""" % (
			latime, inaltime)

	_ECRANE[:] = [HdsHbbtvIncarcare, HdsHbbtvCurat]
	return _ECRANE


def _intreg(text, implicit=None):
	try:
		return int(text)
	except (TypeError, ValueError):
		return implicit


class Controlor(object):
	"""Aplicatia HbbTV pornita la ROSU (una singura). Este si ascultatorul navigatorului (lansator.Ascultator)."""

	def __init__(self, mediu):
		self.m = mediu
		self.nav = None
		self.ref = ""
		self.autostart = False
		self.aratat = False
		self._taste = False
		self._mesaj = None
		self._ceas = mediu.ceas(self._verifica)
		self._ceas_rosu = mediu.ceas(self._trimiteRosu)
		self._ceas_rosu_urma = mediu.ceas(self._urmaresteRosu)   # ROSU-ul urmarit, la ROSU_PAS_MS
		self._ceas_arata = mediu.ceas(self._termenArata)
		self._ceas_automat = mediu.ceas(self._verificaAutomat)
		self._ev_canal = mediu.evenimente()
		self._ev_ait, self._ev_eit = self._din_mediu("evenimente_info", ((), ()))
		self._video_pus = None            # fereastra video scrisa de noi (720x576); None = ecran intreg
		self._automat_refuzat = None      # canalul pe care pornirea automata nu se mai incearca (pana la urmatorul zap)
		self._ascultare_automata = False
		self._desen_procesor = False      # GL a cazut o data: urmatoarele aplicatii pornesc direct pe procesor
		# motivul: cercetarea pe firul ei, mesajul care o asteapta, ultimul motiv (web)
		self._diag = None
		self._motiv_asteapta = None
		self._ceas_motiv = mediu.ceas(self._verificaMotiv)
		self._ultima = None
		# caruselul (aplicatia numai prin DSM-CC): sesiunea tine cat se incarca si cat ruleaza aplicatia (nu e in _gol)
		self._car = None
		self._car_asteapta = None      # {"rez", "ref", "inceput"} cat se asteapta fisierul de pornire
		self._car_text = None
		self._ceas_carusel = mediu.ceas(self._verificaCarusel)
		# filmele aplicatiilor (obiectul A/V): ceasul pozitiei si evenimentele playerului
		self._ceas_av = mediu.ceas(self._avPas)
		self._av_ev = self._din_mediu("av_evenimente", {}) or {}
		self._gol()

	def _gol(self):
		"""Starea stratului H3 (aplicatia, masca, canalul oprit de ea, zap-ul cerut de ea)."""
		self.strat = False             # stratul JS e in pagina ("HBBTV strat 1")
		self.masca = None              # masca Keyset (None: fara strat, tastele ca in H2)
		self.pornita = False           # prima pagina a venit
		self._asteapta_arata = False   # prima pagina a venit ascunsa, se asteapta show()
		self._arata_cerut = False      # show() venit inainte de prima pagina sau cat bara nu era libera
		self._rosu_in_asteptare = False
		self._rosu_de_trimis = False    # AUTOSTART: VK_RED inca de trimis (o data)
		self._aratata_vreodata = False  # a chemat show() macar o data (altfel, ascunsa, primeste numai culorile)
		self.aplicatie = None          # (org, id) din AIT; None la o aplicatie independenta pornita din http
		self.legata = True             # legata de canal (broadcast-related)
		self.serviciu_oprit = None     # referinta canalului oprit de aplicatie
		self._zap = None               # zap cerut de aplicatie, in asteptarea AIT-ului canalului nou
		self._ignora_pana = 0
		self.fereastra = None          # pozitia si marimea video/broadcast (puncte CSS 1280x720)
		self.ecran_intreg = False
		self._inchidere = False        # inchide() cerut: imaginea pe tot ecranul, inainte de golirea stratului
		self.video_legat = False       # video/broadcast legat de canal (bindToCurrentChannel / setChannel), fara release
		self.fundal = False            # pornita automat, inca nevazuta (fara taste, fara ecran, show() tinut minte)
		self._zap_om = None            # zap facut de om cu aplicatia pastrata, in asteptarea AIT-ului canalului nou
		self._programe = None
		self._ccid = {}
		self._url = ""                 # adresa de pornire (pentru incarcarea din nou fara VK_RED)
		self._rosu_trimis_la = None    # cand a plecat VK_RED trimis de receptor (nu de om)
		self._aplicatie_noua_la = None # cand a pornit createApplication() o aplicatie noua, pana la documentul ei
		self._reluata = False         # incarcata din nou fara VK_RED (o singura data)
		self._rosu_urmarit = None      # VK_RED trimis de receptor, urmarit pe ecran: {gol, semn, pasi, vazut}
		self._agent = ""               # partea HbbTV a User-Agent-ului aplicatiei de acum
		self._profil = None            # profilul (HdsHbbtvAplicatii.alege_agent), sau None
		self._cheie_trad = None        # cheia pornirii pentru traducerea textelor (traducere_hbbtv_web.py)
		self._av = None                # filmul pornit de aplicatie (obiectul A/V), vezi _avPorneste
		self._av_fereastra = None      # pozitia si marimea obiectului A/V (puncte CSS 1280x720)
		self._av_ecran_intreg = False
		self._av_piste = None          # ultimele piste de sunet trimise paginii

	def _din_mediu(self, nume, implicit, *argumente):
		"""O metoda a Mediului care poate lipsi (Mediile de proba din H2 nu au partea H3)."""
		f = getattr(self.m, nume, None)
		if f is None:
			return implicit
		try:
			return f(*argumente)
		except Exception as e:
			_jurnal("%s: %s" % (nume, e))
			return implicit

	def _timp(self):
		return self._din_mediu("timp", time.time())

	def _agentPentru(self, url):
		"""(partea HbbTV a User-Agent-ului, profilul sau None); Mediile de proba vechi: agentul receptorului."""
		r = self._din_mediu("agent_pentru", None, url)
		if isinstance(r, tuple) and len(r) == 2 and r[0]:
			return r[0], r[1]
		return self.m.agent(), None

	def _config(self):
		"""Configuration/LocalSystem pentru pagina (cu valorile profilului, daca e)."""
		c = self._din_mediu("config_hbbtv", {})
		c = _aplicatii().config_cu_profil(c, self._profil) if self._profil else c
		info = self._infoCarusel()
		return dict(c, carusel=info) if info else c

	def _configPagina(self):
		"""_config, cu "traducere" ({port, cheie}) cand "Tradu HbbTV" e pornita; numai pentru stdin (_trimite)"""
		c = self._config()
		t = traducere_pagina(self._cheie_trad)
		return dict(c, traducere=t) if t else c

	def _laTraducere(self, element=None):
		"""o setare a traducerii s-a schimbat (Components/HdsTraducereTexte.ascultaSchimbarile): config din nou"""
		if self.nav is not None and self.strat:
			self._trimite("config")

	# ------------------------------------------------ ROSU

	def rosu(self, bara=None):
		"""Tasta ROSIE pe televizorul live: 1 daca a facut ceva (porneste, arata aplicatia pornita automat sau spune de ce
		nu), 0 altfel. Cu HbbTV oprit din setari: 0 (tasta merge mai departe, nimic nu porneste)."""
		if not self._din_mediu("hbbtv_pornit", True):
			return 0
		if self._car_asteapta is not None:
			return 1                               # aplicatia se incarca deja din carusel
		if self.nav is not None:
			if self.fundal:
				self._dezvaluie()
			elif self.strat and self.pornita and not self.aratat and not self._asteapta_arata:
				# aplicatia ascunsa (nu s-a aratat sau a chemat hide()) cu masca fara ROSU: ROSU-ul omului tot la ea
				self._rosu_trimis_la = None
				self.nav.tasta(KEY_RED, 1)
				self.nav.tasta(KEY_RED, 0)
			return 1
		try:
			rez, ref = self.m.rezumat_canal()
		except Exception as e:
			_jurnal("AIT-ul canalului: %s" % e)
			return 0
		fel, url = hotarare_rosu(rez, self.m.in_timeshift(bara))
		if fel == NIMIC:
			return 0
		if fel in (PORNESTE, CARUSEL):
			fel = self._pazaRosu() or fel
		if fel == CARUSEL:
			fel = self._pornesteCarusel(rez, ref)
			if fel is None:
				return 1                           # caruselul se incarca; navigatorul porneste din _verificaCarusel
		if fel != PORNESTE:
			_jurnal("ROSU: %s" % fel)
			self.m.mesaj(text_mesaj(fel, _))
			if fel == CARUSEL or fel.startswith("carusel-"):
				self._noteazaUltima(fel, TEXTE[fel])
			return 1
		self._porneste(url, rez, ref)
		return 1

	def _pazaRosu(self):
		"""ROSU apasat de om: inregistrarea care ruleaza sau memoria prea putina opresc pornirea cu un mesaj
		limpede (timeshift-ul il spune hotarare_rosu). None: se poate porni."""
		if OPRESTE_LA_INREGISTRARE and self._din_mediu("inregistrare_pornita", False):
			return "inregistrare"
		mem = self._din_mediu("memorie_libera_kb", None)
		if isinstance(mem, int) and mem < MEMORIE_ROSU_KB:
			_jurnal("memorie libera %d kB, sub pragul de pornire" % mem)
			return "memorie-pornire"
		return None

	# ------------------------------------------------ caruselul DSM-CC

	def _infoCarusel(self):
		""""carusel" pentru configurarea paginii (HdsCaruselServer.SesiuneCarusel.info), sau None."""
		car = getattr(self, "_car", None)
		if car is None:
			return None
		try:
			return car.info()
		except Exception as e:
			_jurnal("caruselul: %s" % e)
			return None

	def _pornesteCarusel(self, rez, ref):
		"""ROSU pe o aplicatie numai prin carusel: sesiunea caruselului porneste (cititorul si serverul), fereastra mica
		spune ca se incarca, EXIT si zap-ul renunta; _verificaCarusel porneste navigatorul. -> None cand a pornit, altfel
		cheia mesajului (CARUSEL: caruselul e pe alt serviciu sau aplicatia nu are transport prin carusel)."""
		if self.m.lansator().activ() is not None:
			return "ocupat"
		a = rez.get("aleasa") or {}
		t = ([x for x in a.get("transporturi") or () if x.get("protocol") == _hbbtv().PROTOCOL_CARUSEL] or [None])[0]
		if t is None or t.get("la_distanta"):
			return CARUSEL
		car = self._din_mediu("carusel", None, a, ref)
		if car is None:
			return "carusel-eroare"
		try:
			car.porneste()
		except Exception as e:
			_jurnal("caruselul nu a pornit: %s" % e)
			return "carusel-eroare"
		self._car = car
		self._car_asteapta = {"rez": rez, "ref": ref, "inceput": self._timp()}
		self._car_text = None
		_jurnal("ROSU: aplicatia se incarca din carusel")
		self._legaTaste(True)                  # EXIT renunta
		self.m.asculta_nav(self._evenimentCanal, True)
		self._textCarusel({})
		self._ceas_carusel.start(CARUSEL_PAS_MS, False)
		return None

	def _textCarusel(self, st):
		text = text_carusel(st.get("module_gata"), st.get("module"), _)
		if text != self._car_text:
			self._car_text = text
			self._din_mediu("text_incarcare", None, text)

	def _verificaCarusel(self):
		"""La CARUSEL_PAS_MS cat se incarca aplicatia din carusel (firul enigma2): textul cu partile venite; fisierul de
		pornire gata -> navigatorul; altfel, la ce nu merge, un mesaj si caruselul se opreste."""
		w = self._car_asteapta
		if w is None or self._car is None:
			self._ceas_carusel.stop()
			return
		try:
			r = self._pasCarusel(w)
		except Exception as e:
			_jurnal("caruselul: %s" % e)
			r = ("carusel-eroare", "eroare")
		if r is None:
			return
		self._ceas_carusel.stop()
		if r != PORNESTE:
			self._anuleazaCarusel(r[0], r[1])
			return
		if self.m.lansator().activ() is not None:
			self._anuleazaCarusel("ocupat", "alt navigator deschis")
			return
		self._car_asteapta = None
		_jurnal("caruselul are pornirea (%.1f s); navigatorul porneste" % (self._timp() - w["inceput"]))
		self._porneste(self._car.adresa(), w["rez"], w["ref"])

	def _pasCarusel(self, w):
		"""Un pas al asteptarii: None (se asteapta), PORNESTE, sau (cheia mesajului sau None, motivul din jurnal)."""
		if self._din_mediu("ref_curent", w["ref"]) != w["ref"]:
			return None, "canalul schimbat"
		if self._din_mediu("in_standby", False) or self._din_mediu("in_timeshift", False):
			return None, "standby sau timeshift"
		if not self._din_mediu("hbbtv_pornit", True):
			return None, "HbbTV oprit din setari"
		if OPRESTE_LA_INREGISTRARE and self._din_mediu("inregistrare_pornita", False):
			return "inregistrare", "inregistrare"
		mem = self._din_mediu("memorie_libera_kb", None)
		if isinstance(mem, int) and mem < MEMORIE_ROSU_KB:
			return "memorie-pornire", "memorie"
		st = self._car.stare() or {}
		trecut = self._timp() - w["inceput"]
		nu_vine = "carusel-semnal" if st.get("sectiuni") else "carusel-criptat"
		if st.get("faza") == "eroare":
			return "carusel-eroare", "eroare la citire"
		if st.get("prea_mare"):
			return "carusel-prea-mare", "prea mare"
		if st.get("faza") == "fara_carusel":
			if st.get("motiv") in ("pmt", "pista"):
				return "carusel-eroare", "fara " + st.get("motiv")
			return nu_vine, "fara DSI"
		if st.get("pornire") and (st.get("complet") or trecut >= TERMEN_CARUSEL_S):
			return PORNESTE
		if st.get("complet"):
			return "carusel-fara-pornire", "fara fisierul de pornire"
		if trecut >= TERMEN_CARUSEL_S:
			return nu_vine, "termen"
		self._textCarusel(st)
		return None

	def _anuleazaCarusel(self, mesaj=None, motiv=""):
		"""Incarcarea din carusel se opreste inainte de navigator: sesiunea (cititorul, serverul, dosarul), tastele,
		ascultarea canalului, fereastra mica; mesajul (cheie din TEXTE) se arata si ramane pentru web."""
		self._ceas_carusel.stop()
		self._car_asteapta = None
		self._opresteCarusel()
		if self.nav is None:
			self._legaTaste(False)
			self.m.asculta_nav(self._evenimentCanal, False)
			self.m.arata_incarcare(False)
		_jurnal("caruselul oprit inainte de pornire (%s)" % (motiv or mesaj or "-"))
		if mesaj:
			self.m.mesaj(text_mesaj(mesaj, _))
			self._noteazaUltima(mesaj, TEXTE.get(mesaj, ""))

	def _opresteCarusel(self):
		car, self._car = self._car, None
		self._car_text = None
		if car is not None:
			try:
				car.opreste()
			except Exception as e:
				_jurnal("oprirea caruselului: %s" % e)

	def _porneste(self, url, rez, ref, automat=False):
		L = self.m.lansator()
		if L.activ() is not None:
			if not automat:
				self.m.mesaj(text_mesaj("ocupat", _))
			return
		utilizator = self.m.utilizator()
		date, cache = self.m.dosare(utilizator)
		self._gol()
		if self._motiv_asteapta is not None:
			self._motiv_asteapta["arata"] = False   # mesajul aplicatiei de dinainte nu mai apare peste cea noua
		self.fundal = bool(automat)
		self.ref = ref
		self._url = url
		self._cheie_trad = secrets.token_urlsafe(18)
		_asculta_traducerea(self)
		self._agent, self._profil = self._agentPentru(url)
		self.autostart = bool(rez.get("autostart"))
		self.aratat = False
		self._mesaj = None
		a = rez.get("aleasa") or {}
		self.aplicatie = (a.get("org"), a.get("id")) if a else None
		self._nume = a.get("nume") or ""
		setari = dict(self.m.setari_navigator() or {})
		if self._desen_procesor:
			setari["desen"] = "procesor"   # GL a cazut la o aplicatie de dinainte (P1c h4-h6): direct pe procesor
		hbbtv = {"agent": self._agent, "utilizator": utilizator[0] if utilizator else ""}
		if setari.pop("hbbtv_clar", False):
			# "HbbTV clar": WebKit deseneaza la marimea intreaga, fara marirea la copiere; oprita, nimic nu se schimba
			# (lansatorul ramane la HBBTV_MARIRE_LA_COPIERE)
			hbbtv["marire_copiere"] = False
		self.nav = L.Navigator(self, L.MOD_HBBTV, url, setari=setari, dosar_date=date,
			dosar_cache=cache, hbbtv=hbbtv, stare_hbbtv=self._parti(lista=False))
		_jurnal("pornire (%s%s, prioritatea %s)" % ("AUTOSTART" if self.autostart else "PRESENT",
			", automata, ascunsa" if automat else "", a.get("prioritate", "-")))
		if not automat:
			self._legaTaste(True)   # pornita automat: telecomanda ramane toata a enigma2 pana la ROSU
		self.m.asculta_nav(self._evenimentCanal, True)
		self._ceas.start(VERIFICARE_MS, False)
		nav = self.nav
		if not nav.porneste() and self.nav is nav:
			# porneste() a refuzat fara laOprit (de exemplu alt navigator deschis intre timp)
			self.laOprit("pornire")

	# ------------------------------------------------ pornirea automata

	def porneste_ascultarea(self):
		"""O singura data, la pornirea enigma2 (porneste): evenimentele canalului redat pentru pornirea automata."""
		if not self._ascultare_automata:
			self._ascultare_automata = True
			self.m.asculta_nav(self._evenimentAutomat, True)

	def _evenimentAutomat(self, ev):
		# chemat din Navigation.dispatchEvent: nicio exceptie nu iese
		try:
			if ev in self._ev_canal:
				self._automat_refuzat = None   # canal nou: pornirea automata se incearca din nou
				self._ceas_automat.stop()
			elif ev in self._ev_ait:
				self._ceas_automat.start(AUTOMAT_DUPA_MS, True)
		except Exception as e:
			_jurnal("pornirea automata: %s" % e)

	def laSetareaHbbtv(self, pornita):
		"""Setarea principala „HbbTV” schimbata: oprita -> orice aplicatie HbbTV se inchide pe loc; pornita -> pornirea
		automata (daca e pornita si ea) se verifica pe canalul de acum."""
		if not pornita:
			self._ceas_automat.stop()
			if self._car_asteapta is not None:
				self._anuleazaCarusel(motiv="HbbTV oprit din setari")
			if self.nav is not None:
				self.inchide(motiv="HbbTV oprit din setari")
		else:
			self._automat_refuzat = None
			self._ceas_automat.start(AUTOMAT_DUPA_MS, True)

	def laSetareaAutomata(self, pornita):
		"""Setarea schimbata (pe televizor sau din web): pornita -> verificarea pe canalul de acum; oprita -> aplicatia
		pornita automat si inca nevazuta se inchide."""
		if pornita:
			self._automat_refuzat = None
			self._ceas_automat.start(AUTOMAT_DUPA_MS, True)
		elif self.nav is not None and self.fundal:
			self.inchide(motiv="pornirea automata oprita din setari")

	def _paza(self):
		"""De ce nu poate porni (sau ramane) o aplicatie nevazuta: "standby", "timeshift", "inregistrare", "memorie", sau
		None. Pragul memoriei: MEMORIE_AUTOSTART_KB la pornire, MEMORIE_FUNDAL_KB cat ruleaza nevazuta."""
		if self._din_mediu("in_standby", False):
			return "standby"
		if self._din_mediu("in_timeshift", False):
			return "timeshift"
		if OPRESTE_LA_INREGISTRARE and self._din_mediu("inregistrare_pornita", False):
			return "inregistrare"
		mem = self._din_mediu("memorie_libera_kb", None)
		prag = MEMORIE_FUNDAL_KB if self.nav is not None else MEMORIE_AUTOSTART_KB
		if isinstance(mem, int) and mem < prag:
			return "memorie"
		return None

	def _verificaAutomat(self):
		"""Canalul redat are in AIT o aplicatie AUTOSTART cu adresa HTTP si setarea e pornita: porneste ascunsa."""
		try:
			if self.nav is not None or not self._din_mediu("autostart_pornit", False):
				return
			if not self._din_mediu("hbbtv_pornit", True):
				return
			if self.m.lansator().activ() is not None:
				return                          # navigatorul obisnuit sau interfata camului e deschisa
			rez, ref = self.m.rezumat_canal()
			if not ref or ref == self._automat_refuzat or not (rez or {}).get("autostart"):
				return
			fel, url = hotarare_rosu(rez, False)
			if fel != PORNESTE:
				return
			motiv = self._paza()
			if motiv:
				_jurnal("pornirea automata nu se face (%s)" % motiv)
				return
			self._porneste(url, rez, ref, automat=True)
		except Exception as e:
			_jurnal("pornirea automata: %s" % e)

	def _vizibil(self, da):
		f = getattr(self.nav, "vizibil", None) if self.nav is not None else None
		if f is not None:
			f(da)

	def _dezvaluie(self):
		"""ROSU pe o aplicatie pornita automat: se arata pe loc (daca a chemat show()) si primeste VK_RED; de aici e ca o
		aplicatie pornita de om (tastele, termenul de show(), inchiderea)."""
		self.fundal = False
		self._automat_refuzat = None
		self._legaTaste(True)
		self._vizibil(True)
		_jurnal("ROSU: aplicatia pornita automat se arata")
		if not self.pornita:
			# inca se incarca: ca la o pornire facuta de om, laPrimaPaginaAscunsa face restul (si ROSU dupa 1 s)
			self.autostart = True
			self.m.arata_incarcare(True)
			return
		self._rosu_de_trimis = True
		if self._arata_cerut:
			self._cereArata()                  # VK_RED la ROSU_DUPA_ARATA_MS dupa aratare
		else:
			self._asteapta_arata = True        # aplicatia se arata singura la ROSU (show()), altfel se inchide cu mesaj
			self._ceas_arata.start(TERMEN_ARATA_MS, True)
			self._trimiteRosu()

	def _treciInFundal(self):
		"""Zap facut de om cu pornirea automata pornita: aplicatia se ascunde (enigma2 ia ecranul si telecomanda inapoi,
		imaginea pe tot ecranul) si ramane pornita, nevazuta, pana la AIT-ul canalului nou."""
		if self.aratat:
			self.aratat = False
			self._arata_cerut = True           # la ROSU se arata din nou cum era
			self.nav.ascunde()
			self._trimite("app")
			self._ev({"ev": "vizibil", "v": False})
		self.fundal = True
		self._asteapta_arata = False
		self._rosu_in_asteptare = False
		self._rosu_de_trimis = False
		self._ceas_arata.stop()
		self._ceas_rosu.stop()
		self._opresteUrmarirea()
		self._legaTaste(False)
		self.m.arata_incarcare(False)
		self._vizibil(False)
		self._aplicaFereastra()

	def _pastreazaLaZap(self):
		"""Zap facut de om: True daca aplicatia ramane pornita pana la AIT-ul canalului nou (pornirea automata pornita,
		aplicatie legata de canal, din AIT, deja incarcata)."""
		if not (self.legata and self.aplicatie and self.pornita and not self.serviciu_oprit):
			return False
		if self._car is not None:
			return False                       # caruselul e al canalului de dinainte
		if not self._din_mediu("autostart_pornit", False):
			return False
		if self._zap_om is None:
			_jurnal("zap facut de om: aplicatia ramane ascunsa pana la AIT-ul canalului nou")
		self._zap_om = {"inceput": self._timp()}
		self._treciInFundal()
		return True

	def _verificaZapOm(self):
		if self._zap_om is None or self.nav is None:
			return
		st = self._din_mediu("stare_ait", {}) or {}
		pid, versiune = st.get("pid", -1), st.get("versiune", -1)
		if pid == 0 or (versiune >= 0 and not semnalata(st, self.aplicatie)):
			self._zap_om = None
			self.inchide(motiv="nesemnalata in canalul nou")
			return
		if versiune >= 0:
			self._zap_om = None
			self.ref = self._din_mediu("ref_curent", self.ref)
			self._automat_refuzat = None
			_jurnal("aplicatia ramane pe canalul nou (semnalata in AIT)")
			self._trimite("app", "canal", "programe")
			self._ev({"ev": "canal-reusit"})
			return
		if self._timp() - self._zap_om["inceput"] > TERMEN_ZAP_S:
			self._zap_om = None
			self.inchide(motiv="fara AIT in canalul nou")

	def _verificaAitAcum(self):
		"""Un AIT nou pe acelasi canal (alta versiune): aplicatia legata de canal care nu mai e semnalata (KILL, scoasa)
		se inchide (ETSI TS 102 796 cap. 6.2.2.3)."""
		if self.nav is None or not self.legata or not self.aplicatie or self.serviciu_oprit:
			return
		st = self._din_mediu("stare_ait", {}) or {}
		if st.get("pid", -1) > 0 and st.get("versiune", -1) >= 0 and not semnalata(st, self.aplicatie):
			self.inchide(motiv="oprita de AIT (nu mai e semnalata)")

	def cedeaza(self):
		"""Navigatorul obisnuit, interfata camului sau „Șterge datele HbbTV” vor locul (lansator.cedeaza): aplicatia
		pornita automat si inca nevazuta se opreste pe loc. True daca locul e liber."""
		if self.nav is None or not self.fundal:
			return self.nav is None
		f = getattr(self.nav, "opresteAcum", None)
		self._automat_refuzat = self.ref       # nu porneste din nou pe acelasi canal pana la urmatorul zap
		self._motiv = "loc pentru alt navigator"
		if f is None:
			self.nav.opreste()
			return False
		f()
		return self.nav is None

	# ------------------------------------------------ filmele aplicatiilor (obiectul A/V)
	#
	# Pagina cere filmul prin obiectul A/V (hds-hbbtv.js, numai cu un lansator care lasa comanda "av"): "av porneste <id>
	# <base64 adresa> <tip>". Filmul merge pe playerul receptorului (Mediu.av_reda: serviciul 4097, GStreamer), pe
	# acelasi decodor ca si canalul: canalul se opreste ca la video/broadcast stop() (serviciu_oprit) si porneste din nou la
	# bindToCurrentChannel, release, la zap-ul cerut de aplicatie sau la iesirea ei. Pozitia si starea se citesc la
	# AV_PAS_MS si pleaca spre pagina ca eveniment {"ev": "av", "id", "joc", "poz", "lung", "viteza", "eroare"?};
	# pistele de sunet ca {"ev": "av-piste", "id", "piste"}. Evenimentele serviciului cat merge filmul (inceputul,
	# sfarsitul, tamponul, erorile, AIT-ul care lipseste) sunt ale filmului, nu un zap; un alt serviciu pornit peste el
	# (zap facut de om) inchide aplicatia ca pana acum, fara sa mai porneasca vechiul canal.

	def _avActiv(self):
		return self._av is not None and self._av["joc"] in AV_ACTIV

	def _avStare(self, **k):
		"""Starea filmului spre pagina, cu id-ul cererii ei (pagina nu amesteca filmele vechi cu cel de acum)."""
		a = self._av
		if a is None:
			return
		ev = {"ev": "av", "id": a["id"], "joc": a["joc"], "poz": a["poz"], "lung": a["lung"], "viteza": a["viteza"]}
		if a["joc"] == AV_EROARE:
			ev["eroare"] = a["eroare"]
		ev.update(k)
		a["trimis_poz"], a["trimis_la"] = a["poz"], self._timp()
		self._ev(ev)

	def _laAv(self, a):
		c = av_comanda(a)
		if c is None:
			_jurnal("cererea av gresita, nefolosita")
			return
		sub, v = c
		if sub == "porneste":
			self._avPorneste(v[0], self.m.lansator().din_b64(v[1]) if v[1] != "-" else "", v[2])
		elif sub == "viteza":
			self._avViteza(v[0])
		elif sub == "cauta":
			self._avCauta(v[0])
		elif sub == "opreste":
			self._avOpreste(anunta=True)
		elif sub == "pista":
			self._avPista(v[0])
		elif sub == "fereastra":
			# fereastra vine de la obiectul activ si tine seama de setFullScreen lui (pe tot ecranul: 0 0 1280 720)
			if v[0] != self._av_fereastra or self._av_ecran_intreg:
				self._av_fereastra, self._av_ecran_intreg = v[0], False
				self._aplicaFereastra()
		elif sub == "ecran-intreg":
			self._av_ecran_intreg = bool(v[0])
			self._aplicaFereastra()

	def _avPorneste(self, ident, url, tip):
		t = av_tip(tip)
		if self._avActiv():
			self._avOpreste(anunta=True)
		if t is None or not av_adresa_buna(url):
			_jurnal("film cerut de aplicatie: %s" % ("tip nesustinut" if t is None else "adresa nefolosibila"))
			self._ev({"ev": "av", "id": ident, "joc": AV_EROARE, "eroare": AV_E_FORMAT, "poz": 0, "lung": 0, "viteza": 0})
			return
		oprit_acum = not self.serviciu_oprit
		self._opresteServiciu()                # un singur decodor: canalul se opreste, ca la video/broadcast stop()
		self._av = {"id": ident, "tip": t, "joc": AV_CONECTARE, "eroare": None, "poz": 0, "lung": 0, "viteza": 1,
			"ref": "", "inceput": self._timp(), "pornit": False, "trimis_poz": 0, "trimis_la": 0}
		self._av_piste = None
		self._ignora_pana = self._timp() + IGNORA_ZAP_S
		ref = self._din_mediu("av_reda", "", url)
		if self._av is None:
			return                             # oprit intre timp (un eveniment al serviciului)
		if not ref:
			self._avGata(AV_EROARE, AV_E_RESURSE)
			if oprit_acum:
				self._pornesteServiciu()       # playerul nu a pornit deloc: canalul oprit acum porneste la loc
			return
		self._av["ref"] = ref
		_jurnal("film pornit de aplicatie (%s)" % t)
		self._avStare()
		self._ceas_av.start(AV_PAS_MS, False)
		self._aplicaFereastra()

	def _avGata(self, joc, eroare=None, anunta=True):
		"""Filmul s-a terminat (AV_GATA), a cazut (AV_EROARE) sau a fost oprit (AV_OPRIT): playerul se opreste (decodorul
		e liber), pagina afla starea; canalul porneste din nou abia la bindToCurrentChannel, release sau la iesire."""
		a = self._av
		if a is None:
			return
		self._ceas_av.stop()
		if a["ref"] and self._din_mediu("ref_curent", "") == a["ref"]:
			self._ignora_pana = self._timp() + IGNORA_ZAP_S
			self._din_mediu("av_opreste", None)
		a["joc"], a["eroare"] = joc, eroare
		if anunta:
			self._avStare()
		self._av = None
		self._aplicaFereastra()
		_jurnal("film %s" % ("terminat" if joc == AV_GATA else "oprit" if joc == AV_OPRIT else "cazut (%s)" % eroare))

	def _avOpreste(self, anunta=False):
		if self._av is not None:
			self._avGata(AV_OPRIT, anunta=anunta)

	def _avViteza(self, v):
		a = self._av
		if not self._avActiv():
			return
		if v != a["viteza"] and self._din_mediu("av_pauza", False, v == 0):
			a["viteza"] = v
			a["joc"] = AV_PAUZA if v == 0 else AV_REDA if a["pornit"] else AV_CONECTARE
		self._avStare()

	def _avCauta(self, ms):
		a = self._av
		if not self._avActiv():
			return
		ok = bool(self._din_mediu("av_cauta", False, ms))
		if ok:
			a["poz"] = min(ms, a["lung"]) if a["lung"] else ms
		self._avStare(cautat=ok)

	def _avPista(self, i):
		if self._avActiv() and self._din_mediu("av_alege_pista", False, i):
			self._avPisteTrimise(mereu=True)

	def _avPisteTrimise(self, mereu=False):
		if self._av is None:
			return
		p = av_piste_pagina(self._din_mediu("av_piste", []) or [])
		if mereu or p != self._av_piste:
			self._av_piste = p
			self._ev({"ev": "av-piste", "id": self._av["id"], "piste": p})

	def _avPas(self):
		"""La AV_PAS_MS cat merge filmul: pozitia, inceputul (prima pozitie peste 0), termenul de legare."""
		a = self._av
		if a is None or self.nav is None or a["joc"] not in AV_ACTIV:
			self._ceas_av.stop()
			return
		try:
			acum = self._timp()
			p = self._din_mediu("av_pozitie", None)
			if p is not None:
				a["poz"], a["lung"] = p
				if p[0] > 0 and not a["pornit"]:
					a["pornit"] = True
					if a["joc"] == AV_CONECTARE:
						a["joc"] = AV_REDA
					_jurnal("filmul aplicatiei a inceput (%d s de la cerere)" % int(acum - a["inceput"]))
					self._avStare()
					self._avPisteTrimise()
					return
			if not a["pornit"] and acum - a["inceput"] > AV_TERMEN_CONECTARE_S:
				self._avGata(AV_EROARE, AV_E_LEGATURA)
				return
			if a["joc"] == AV_REDA and a["poz"] != a["trimis_poz"] and (acum - a["trimis_la"]) * 1000 >= AV_POZITIE_PAS_MS:
				self._avStare()
		except Exception as e:
			_jurnal("film: %s" % e.__class__.__name__)

	def _avEveniment(self, ev):
		"""Un eveniment al serviciului cat merge un film al aplicatiei. True: e al filmului (nu un zap). Un alt serviciu
		pornit peste film (zap facut de om, temporizator): filmul s-a dus, canalul oprit de aplicatie nu mai porneste (omul
		a ales altul); False, ca paza obisnuita sa inchida aplicatia."""
		a, e = self._av, self._av_ev
		if ev in self._ev_canal:
			ref = self._din_mediu("ref_curent", "")
			if not a["ref"] or ref in ("", a["ref"]) or self._timp() < self._ignora_pana:
				return True
			_jurnal("alt serviciu pornit peste filmul aplicatiei")
			self._ceas_av.stop()
			a["joc"] = AV_OPRIT
			self._avStare()
			self._av = None
			self.serviciu_oprit = None
			return False
		if a["joc"] not in AV_ACTIV:
			return True
		if ev is not None and ev == e.get("eof"):
			self._avGata(AV_GATA)
		elif ev in (e.get("erori") or {}):
			self._avGata(AV_EROARE, av_eroare(e["erori"][ev], a["pornit"]))
		elif ev is not None and ev == e.get("bufer") and a["joc"] in (AV_REDA, AV_ASTEAPTA):
			b = self._din_mediu("av_bufer", None)
			nou = a["joc"] if b is None else AV_ASTEAPTA if b < AV_BUFER_GATA else AV_REDA
			if nou != a["joc"]:
				a["joc"] = nou
				self._avStare()
		elif ev is not None and ev == e.get("info") and a["pornit"]:
			self._avPisteTrimise()
		return True                            # AIT-ul si EIT-ul serviciului filmului nu sunt ale aplicatiei

	# ------------------------------------------------ fereastra video

	def _fereastraDorita(self):
		"""Fereastra video de acum (720x576) sau None = tot ecranul: numai cu aplicatia pe ecran, video/broadcast legat,
		fara setFullScreen si fara canal oprit de aplicatie. Cat merge un film al aplicatiei: fereastra obiectului A/V."""
		if self.nav is None or self._inchidere or not self.aratat or self.fundal:
			return None
		if self._avActiv():
			return None if self._av_ecran_intreg else fereastra_vmpeg(self._av_fereastra)
		if self.ecran_intreg:
			return None
		if not self.video_legat or self.serviciu_oprit or not self.legata:
			return None
		return fereastra_vmpeg(self.fereastra)

	def _aplicaFereastra(self, mereu=False):
		f = self._fereastraDorita()
		if f == self._video_pus and not mereu:
			return
		if self._din_mediu("fereastra_video", False, f) is False and f is not None:
			return
		self._video_pus = f
		if f is None:
			_jurnal("imaginea canalului pe tot ecranul")
		else:
			_jurnal("imaginea canalului in fereastra %d,%d %dx%d (720x576)" % f)

	# ------------------------------------------------ starea pentru pagina (stratul H3)

	def _canal(self):
		ref, nume = self._din_mediu("canal_curent", ("", ""))
		c = canal_hbbtv(ref, nume) if self.legata and not self.serviciu_oprit else None
		if c:
			self._ccid[c["ccid"]] = ref
		return c

	def _lista(self):
		rez = []
		for i, (ref, nume) in enumerate(self._din_mediu("lista_canale", [], LISTA_MAXIM) or []):
			c = canal_hbbtv(ref, nume, i + 1)
			if c:
				self._ccid[c["ccid"]] = ref
				rez.append(c)
		return rez

	def _programe_acum(self):
		ref = self._din_mediu("ref_curent", "")
		return programe_hbbtv(self._din_mediu("programe_canal", []), ref) if self.legata else []

	def _app(self):
		org, ident = self.aplicatie if self.aplicatie else (None, None)
		p = {"org": org, "id": ident, "legat": self.legata, "vizibil": self.aratat, "nume": str(getattr(self, "_nume", "") or "")[:40]}
		try:
			ait = de_pornit_prin_dvb((self._din_mediu("stare_ait", {}) or {}).get("aplicatii"), self._infoCarusel())
		except Exception as e:
			_jurnal("lista aplicatiilor din AIT: %s" % e.__class__.__name__)
			ait = None
		if ait:
			p["ait"] = ait
		return p

	def _parti(self, lista=True):
		p = {"app": self._app(), "canal": self._canal(), "config": self._config(),
			"programe": self._programe_acum(), "taste": {"value": MASCA_MAXIM if self.masca is None else self.masca}}
		self._programe = p["programe"]
		if lista:
			p["lista"] = self._lista()
		return p

	def _trimite(self, *chei):
		if self.nav is None or not self.strat:
			return
		for cheie in chei:
			if cheie == "app":
				self.nav.hbbtvParte("app", self._app())
			elif cheie == "canal":
				self.nav.hbbtvParte("canal", self._canal())
			elif cheie == "programe":
				self._programe = self._programe_acum()
				self.nav.hbbtvParte("programe", self._programe)
			elif cheie == "taste":
				self.nav.hbbtvParte("taste", {"value": MASCA_MAXIM if self.masca is None else self.masca})
			elif cheie == "lista":
				self.nav.hbbtvParte("lista", self._lista())
			elif cheie == "config":
				self.nav.hbbtvParte("config", self._configPagina())

	def _ev(self, ev):
		if self.nav is not None and self.strat:
			self.nav.hbbtvEv(ev)

	# ------------------------------------------------ cererile paginii (lansator.Ascultator.laHbbtv)

	def laHbbtv(self, comanda, argumente):
		if self.nav is None:
			return
		try:
			self._laHbbtv(comanda, argumente)
		except Exception as e:
			_jurnal("cererea %s: %s" % (comanda, e.__class__.__name__))

	def _laHbbtv(self, comanda, a):
		if comanda == "strat":
			self.strat = bool(a) and a[0] == "1"
			self._aplicatie_noua_la = None     # de aici, destroyApplication vine de la aplicatia noua
			self._avOpreste()                  # documentul nou nu mai are obiectul A/V care l-a pornit
			if self.strat:
				if self.masca is None:
					self.masca = MASCA_MAXIM
				# la pornire si dupa o repornire a lansatorului (pe procesor): toata starea, si lista canalelor
				self._trimite("app", "canal", "config", "programe", "taste", "lista")
				if self.fundal and self.pornita:
					self._vizibil(False)       # lansatorul repornit e iar vizibil pentru WebKit
			return
		if comanda == "eroare-incarcare":
			_jurnal("aplicatia pornita din alta nu s-a incarcat")
			self.inchide("nu-a-pornit")
			return
		if not self.strat:
			return
		if comanda == "distruge" and self._aplicatie_noua_la is not None and \
				self._timp() - self._aplicatie_noua_la < DISTRUGE_DUPA_APLICATIE_S:
			# "if (app.createApplication(url, false)) app.destroyApplication()": aplicatia de dinainte se inchide pe
			# ea, nu navigatorul, altfel aplicatia noua (mediateca ARD, clipurile RTL) nu mai apuca sa porneasca
			_jurnal("destroyApplication al aplicatiei de dinainte, dupa pornirea celei noi: lasat")
			return
		if comanda in REACTII_ROSU:
			self._reactieRosu(comanda)
		if comanda == "av":
			self._laAv(a)
			return
		if comanda in AV_OPRIT_DE and not (comanda == "canal" and a == ["-"]):
			# un singur decodor: canalul cerut din nou (sau alta aplicatie) ia locul filmului; setChannel(null) nu
			self._avOpreste(anunta=True)
		if comanda == "arata":
			self._cereArata()
		elif comanda == "ascunde":
			self._cereAscunde()
		elif comanda == "taste":
			v = _intreg(a[0] if a else None)
			if v is not None:
				if (v & MASCA_MAXIM) != self.masca:
					self._reactieRosu("masca")
				self.masca = v & MASCA_MAXIM
				self._trimite("taste")
				if self._rosu_in_asteptare and self.masca & MASCA_RED:
					self._rosu_in_asteptare = False
					self._trimiteRosu()
		elif comanda == "distruge":
			if self._reiaFaraRosu():
				return
			self.inchide(motiv="destroyApplication")
		elif comanda == "aplicatie":
			self._aplicatieNoua(self.m.lansator().din_b64(a[0]) if a else "")
		elif comanda == "leaga":
			self.video_legat = True
			self._pornesteServiciu()
			self._aplicaFereastra()
		elif comanda == "elibereaza":
			self.video_legat = False
			if self._avActiv():
				return                         # release() pe video/broadcast nu opreste filmul (canalul porneste dupa el)
			self._pornesteServiciu()
			self._aplicaFereastra()
		elif comanda == "opreste":
			if not self._avActiv():            # canalul e deja oprit cat merge filmul
				self._opresteServiciu()
		elif comanda == "canal":
			if a and a[0] != "-" or len(a) > 1:
				self.video_legat = True        # setChannel(canal) leaga obiectul (DAE 7.13.1)
			self._cereCanal(a)
			self._aplicaFereastra()
		elif comanda in ("urmator", "anterior"):
			inainte = comanda == "urmator"
			self._zapAplicatie(lambda: self._din_mediu("zap_urmator", False, inainte))
		elif comanda == "ecran-intreg":
			self.ecran_intreg = bool(a) and a[0] == "1"
			_jurnal("video pe tot ecranul: %s" % ("da" if self.ecran_intreg else "nu"))
			self._aplicaFereastra()
		elif comanda == "tradu":
			self._tradu(a)
		elif comanda == "fereastra":
			v = fereastra_valida(a)
			if v is None:
				_jurnal("fereastra video ceruta gresit, nefolosita")
			elif v != self.fereastra or self.ecran_intreg:
				self.fereastra = v
				self.video_legat = True        # pagina trimite fereastra numai pentru obiectul legat
				# fereastra vine de la obiectul activ si tine deja seama de setFullScreen lui (pe tot ecranul trimite
				# 0 0 1280 720); un "ecran-intreg 1" ramas de la alt obiect (ProSieben face un al doilea video/broadcast
				# pentru meniu, masurat pe receptor) nu o mai acopera
				self.ecran_intreg = False
				_jurnal("fereastra video ceruta %d,%d %dx%d (puncte CSS)" % v)
				self._aplicaFereastra()

	def _tradu(self, a):
		"""cererea de traducere a paginii prin punte ("tradu <id> <base64 al {t: [texte]}>"): raspunsul pleaca inapoi ca
		eveniment "traducere" cu acelasi id"""
		if len(a) != 2 or not TRADU_ID.match(a[0] or ""):
			return
		try:
			cerere = json.loads(self.m.lansator().din_b64(a[1]))
		except ValueError:
			cerere = None
		r = raspuns_traducere(cerere)
		r.update(ev="traducere", id=a[0])
		self._ev(r)

	def _cereArata(self):
		if self.nav is None or self.aratat:
			return
		if self.fundal:
			self._arata_cerut = True           # pornita automat: se arata abia la ROSU (_dezvaluie)
			return
		if not self.pornita:
			self._arata_cerut = True       # show() inainte de prima pagina: se face la prima pagina
			return
		if not self.m.bara_libera():
			if self._asteapta_arata:
				# ca in H2: alta fereastra a enigma2 peste bara, aplicatia nu se arata
				self.inchide(motiv="alta fereastra peste bara")
				return
			self._arata_cerut = True       # se arata cand bara e din nou libera (_verifica)
			self._ev({"ev": "vizibil", "v": False})
			return
		self._arata_cerut = False
		self._aratata_vreodata = True
		self.m.arata_incarcare(False)
		self.m.ascunde_bara()
		self._asteapta_arata = False
		self._ceas_arata.stop()
		self.aratat = True
		self.nav.reia()
		self._trimite("app")
		self._ev({"ev": "vizibil", "v": True})
		self._aplicaFereastra()
		if self._rosu_de_trimis:
			self._ceas_rosu.start(ROSU_DUPA_ARATA_MS, True)   # aplicatia e gata: acum primeste ROSU-ul omului

	def _cereAscunde(self):
		self._arata_cerut = False
		if self.nav is None or not self.aratat:
			return
		self.aratat = False
		self.nav.ascunde()
		self._trimite("app")
		self._ev({"ev": "vizibil", "v": False})
		self._aplicaFereastra()                # aplicatia ascunsa: imaginea canalului pe tot ecranul

	def _termenArata(self):
		"""Aplicatia nu s-a aratat in TERMEN_ARATA_MS: un mesaj scurt, dar ramane pornita, ascunsa (ETSI TS 102 796 cap.
		6.2.2.4: o aplicatie legata de canal poate sta ascunsa); urmatorul ROSU ajunge la ea, zap-ul sau EXIT o inchid."""
		if self.nav is not None and self._asteapta_arata:
			_jurnal("aplicatia nu a chemat show() in %d s; ramane pornita, ascunsa" % (TERMEN_ARATA_MS // 1000))
			self._asteapta_arata = False
			self.m.arata_incarcare(False)
			if not self._spuneMotivul("nu-s-a-aratat", self._url, self._agent, nav=self.nav):
				self.m.mesaj(text_mesaj("nu-s-a-aratat", _))

	# ------------------------------------------------ motivul

	def _spuneMotivul(self, fel, url, agent, baza="", nav=None):
		"""Mesajul cu motivul adevarat (HdsHbbtvAplicatii.motiv): cercetarea porneste pe firul ei, iar mesajul il arata
		_verificaMotiv cand ea s-a terminat sau dupa MOTIV_ASTEPTARE_S. False cand Mediul nu stie (probele vechi): atunci
		cel care cheama arata mesajul de pana acum."""
		date = self._din_mediu("date_aplicatii", None)
		if date is None or not url or url.startswith(ADRESA_LOCALA):
			return False                       # aplicatia din carusel: nimic de cercetat pe internet
		if self._motiv_asteapta is not None:
			self._inchideMotivul()
		self._diag = self._din_mediu("cercetare", None, url, agent)
		acum = self._timp()
		self._motiv_asteapta = {"fel": fel, "url": url, "baza": baza, "date": date, "nav": nav, "arata": True,
			"ref": self._din_mediu("ref_curent", ""), "pana_la": acum + MOTIV_ASTEPTARE_S, "capat": acum + MOTIV_TOTAL_S}
		self._ceas_motiv.start(MOTIV_PAS_MS, False)
		self._verificaMotiv()
		return True

	def _verificaMotiv(self):
		a = self._motiv_asteapta
		if a is None:
			self._ceas_motiv.stop()
			return
		c = self._diag
		gata = c is None or bool(c.gata())
		acum = self._timp()
		if not gata and acum < a["pana_la"]:
			return
		inchide = gata or acum >= a["capat"]
		if not a["arata"] and not inchide:
			return                                 # mesajul s-a aratat; se asteapta numai sfarsitul cercetarii
		rez = c.rezultat() if c is not None and gata else None
		cod = _aplicatii().motiv(a["fel"], a["url"], rez, a["date"], bool(self._din_mediu("canal_criptat", False)))
		if a["arata"]:
			a["arata"] = False
			self._arataMotivul(a, cod, rez)
		if inchide:
			self._inchideMotivul(cod)

	def _arataMotivul(self, a, cod, rez=None):
		"""Mesajul pe televizor, numai daca nu s-a schimbat nimic intre timp: aceeasi aplicatie (sau niciuna), acelasi
		canal, iar aplicatia care nu se aratase tot nu s-a aratat."""
		if self.nav is not None and self.nav is not a["nav"]:
			return
		if a["fel"] == "nu-s-a-aratat" and (self.aratat or self.nav is None):
			return
		if a["ref"] and self._din_mediu("ref_curent", a["ref"]) != a["ref"]:
			return
		self.m.mesaj(text_motiv(a["fel"], cod, a["baza"], _, text=_textCeas(cod, rez)))

	def _inchideMotivul(self, cod=None):
		"""Cercetarea s-a terminat (sau a trecut prea mult): motivul ramane pentru web si intra in jurnalul erorilor."""
		a, self._motiv_asteapta = self._motiv_asteapta, None
		self._ceas_motiv.stop()
		c, self._diag = self._diag, None
		if a is None:
			return
		rez = c.rezultat() if c is not None and c.gata() else None
		if cod is None:
			cod = _aplicatii().motiv(a["fel"], a["url"], rez, a["date"], False)
		text = _textCeas(cod, rez) or (TEXTE["motiv-" + cod] if cod else TEXTE.get(a["fel"], ""))
		self._noteazaUltima(cod or a["fel"], text)
		self._din_mediu("jurnal_motiv", False, _aplicatii().rand_jurnal(a["fel"], a["url"], cod, rez))

	def _noteazaUltima(self, motiv, text):
		self._ultima = {"motiv": motiv, "text": text, "ora": time.strftime("%H:%M")}

	def _reiaFaraRosu(self):
		"""Aplicatia cere sa se inchida (destroyApplication, window.close) la cel mult INCHISA_DUPA_ROSU_S dupa VK_RED
		trimis de receptor: ROSU-ul nostru a inchis-o (vezi REIA_FARA_ROSU). Se ascunde si se incarca din nou de la
		adresa de pornire, o singura data, fara VK_RED; daca nu se arata, termenul si mesajul obisnuit. True daca s-a
		facut (atunci aplicatia nu se inchide)."""
		la = self._rosu_trimis_la
		if not REIA_FARA_ROSU or la is None or self._reluata or not self._url or self.nav is None:
			return False
		if self._timp() - la > INCHISA_DUPA_ROSU_S:
			return False
		self._reluata = True
		self._rosu_trimis_la = None
		self._rosu_de_trimis = self._rosu_in_asteptare = False
		self._ceas_rosu.stop()
		_jurnal("aplicatia s-a inchis la ROSU-ul trimis de receptor; se incarca din nou, fara el")
		if self.aratat:
			self._cereAscunde()
		self._arata_cerut = False
		self.masca = MASCA_MAXIM
		self.video_legat, self.fereastra, self.ecran_intreg = False, None, False
		self._aplicaFereastra()
		self._trimite("app", "taste")
		self._asteapta_arata = True
		self._ceas_arata.start(TERMEN_ARATA_MS, True)
		if not self.fundal:
			self.m.arata_incarcare(True)
		self.nav.url(self._url)
		return True

	def _opresteServiciu(self):
		if self.serviciu_oprit:
			return
		self._ignora_pana = self._timp() + IGNORA_ZAP_S
		self.serviciu_oprit = self._din_mediu("opreste_serviciu", "") or None
		if self.serviciu_oprit:
			_jurnal("canalul oprit de aplicatie")

	def _pornesteServiciu(self):
		ref, self.serviciu_oprit = self.serviciu_oprit, None
		if ref:
			self._ignora_pana = self._timp() + IGNORA_ZAP_S
			self._din_mediu("porneste_serviciu", None, ref)
			self.ref = ref
			_jurnal("canalul pornit din nou")

	def _cereCanal(self, a):
		if not a:
			return
		if a[0] == "-" and len(a) == 1:
			# setChannel(null): aplicatia devine independenta de canal (cap. 6.2.2.6); cat merge un film, canalul e deja
			# oprit
			self.legata = False
			if not self._avActiv():
				self._opresteServiciu()
			self._trimite("app", "canal", "programe")
			return
		ref = self._ccid.get(a[0]) if a[0] != "-" else None
		if ref is None and len(a) >= 5:
			onid, tsid, sid = _intreg(a[2], -1), _intreg(a[3], -1), _intreg(a[4], -1)
			if onid >= 0 and sid > 0:
				ref = cauta_in_lista(self._din_mediu("lista_canale", [], LISTA_MAXIM), onid, tsid, sid)
		if ref is None:
			self._ev({"ev": "canal-eroare", "cod": 5})
			return
		self._zapAplicatie(lambda: self._din_mediu("zap_la", False, ref))

	def _zapAplicatie(self, functie):
		"""Zap cerut de aplicatie: nu o inchide; ramane numai daca e semnalata in canalul nou (_verificaZap)."""
		if self.nav is None:
			return
		self.serviciu_oprit = None
		self._zap = {"inceput": self._timp()}
		self._ignora_pana = self._timp() + IGNORA_ZAP_S
		ok = False
		try:
			ok = functie()
		except Exception as e:
			_jurnal("zap: %s" % e)
		if not ok:
			self._zap = None
			self._ev({"ev": "canal-eroare", "cod": 100})
			return
		self.ref = self._din_mediu("ref_curent", self.ref)
		if self._car is not None:
			# pistele caruselului sunt ale canalului de dinainte: aplicatia din carusel se inchide dupa zap
			self._zap = None
			self.inchide(motiv="zap cerut de aplicatia din carusel")
			return
		self._verificaZap()

	def _verificaZap(self):
		if self._zap is None or self.nav is None:
			return
		st = self._din_mediu("stare_ait", {}) or {}
		pid, versiune = st.get("pid", -1), st.get("versiune", -1)
		if pid == 0 or (versiune >= 0 and not semnalata(st, self.aplicatie)):
			self._zap = None
			self.inchide(motiv="nesemnalata in canalul cerut de ea")
			return
		if versiune >= 0:
			self._zap = None
			self.legata = True
			self._trimite("app", "canal", "programe")
			self._ev({"ev": "canal-reusit"})
			return
		if self._timp() - self._zap["inceput"] > TERMEN_ZAP_S:
			self._zap = None
			self.inchide(motiv="fara AIT in canalul cerut de ea")

	def _aplicatieNoua(self, url):
		url = (url or "").strip()
		low = url.lower()
		if low.startswith("dvb:"):
			adresa, a = adresa_dvb(url, (self._din_mediu("stare_ait", {}) or {}).get("aplicatii"), self._infoCarusel())
			if not adresa:
				self._ev({"ev": "aplicatie-eroare"})
				return
			self._pornesteServiciu()
			if a is not None:
				self.aplicatie, self._nume = (a.get("org"), a.get("id")), a.get("nume") or ""
			self.legata = True
			if self.aratat:
				self._cereAscunde()       # aplicatia noua, legata de canal, porneste ascunsa (cap. 6.2.2.4)
			self._asteapta_arata = True
			self._ceas_arata.start(TERMEN_ARATA_MS, True)
		elif low.startswith(("http://", "https://")) and len(url) <= 2048 and not any(c in url for c in "\r\n "):
			adresa = url
			self.aplicatie, self.legata, self._nume = None, False, ""
			self._opresteServiciu()        # independenta de canal: canalul nu mai e ales (cap. 6.2.2.6)
		else:
			self._ev({"ev": "aplicatie-eroare"})
			return
		_jurnal("aplicatie noua din cea de acum (%s)" % ("din AIT" if self.legata else "independenta de canal"))
		self._rosu_trimis_la = None        # o inchidere a aplicatiei noi nu tine de VK_RED trimis celei de dinainte
		self.masca = MASCA_MAXIM
		# documentul nou incepe cu video/broadcast nelegat: imaginea pe tot ecranul pana cere altceva
		self.video_legat, self.fereastra, self.ecran_intreg = False, None, False
		self._aplicaFereastra()
		self._trimite("app", "canal", "programe", "taste")
		self.nav.url(adresa)
		self._aplicatie_noua_la = self._timp()
		if not self.legata and not self.aratat:
			self._cereArata()              # aplicatiile independente se vad fara show() (cap. 6.2.2.4)

	# ------------------------------------------------ tastele

	def _legaTaste(self, da):
		if da == self._taste:
			return
		try:
			h = self.m.harta_taste()
			if da:
				h.bindAction("", PRIORITATE_TASTE, self._tasta)
			else:
				h.unbindAction("", self._tasta)
			self._taste = da
		except Exception as e:
			_jurnal("legarea tastelor: %s" % e)

	def _ascunsa(self):
		return self.strat and self.pornita and not self.aratat and not self._asteapta_arata

	def _tasta(self, cod, flag):
		if self.nav is None:
			if self._car_asteapta is not None and cod == KEY_EXIT:
				if flag == 0:
					self._anuleazaCarusel(motiv="EXIT")
				return 1                           # caruselul se incarca: EXIT renunta
			return 0
		ascunsa = self._ascunsa()
		fel = fel_tasta(cod, self.aratat, self.masca if self.strat else None, ascunsa)
		if fel == RECEPTOR:
			return 0
		if fel == INCHIDE:
			if flag == 0:
				self.inchide(motiv="EXIT")
			return 0 if ascunsa else 1
		if fel == APLICATIE:
			if ascunsa and not self.m.bara_libera():
				return 0
			if ascunsa and not self._aratata_vreodata and cod not in (KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE):
				return 0                       # nevazuta inca: OK, sagetile si cifrele raman ale enigma2
			v = VALOARE_TASTA.get(flag)
			if v is not None:
				if cod == KEY_RED:
					self._rosu_trimis_la = None   # ROSU-ul omului: o inchidere dupa el e voita
				self._reactieRosu("tasta omului")    # omul are telecomanda: fara VK_RED repetat de receptor
				self.nav.tasta(cod, v)
		return 1

	def _trimiteRosu(self):
		if self.nav is None:
			return
		if self.strat:
			if not self.pornita or not self._rosu_de_trimis:
				return
			if not (self.masca or 0) & MASCA_RED:
				self._rosu_in_asteptare = True   # trimis cand aplicatia isi pune ROSU in masca
				return
			self._rosu_de_trimis = False
		elif not self.aratat:
			return
		semn = self._din_mediu("semn_ecran", None) if self.strat and self.aratat else None
		self._rosu_trimis_la = self._timp()
		self.nav.tasta(KEY_RED, 1)
		self.nav.tasta(KEY_RED, 0)
		if semn is not None:
			# ROSU-ul urmarit: o aplicatie care inca nu era gata il primeste din nou (o data), vezi urmare_rosu
			gol = semn[0] < ROSU_DESEN_MINIM
			self._rosu_urmarit = {"gol": gol, "semn": semn, "pasi": 0, "vazut": 0}
			self._ceas_rosu_urma.start(ROSU_PAS_MS, False)
			_jurnal("VK_RED trimis, urmarit (ecranul %s)" % ("gol" if gol else "cu ceva"))

	def _opresteUrmarirea(self):
		self._rosu_urmarit = None
		self._ceas_rosu_urma.stop()

	def _reactieRosu(self, motiv):
		"""Aplicatia a facut ceva care arata ca a primit VK_RED (sau omul a luat telecomanda): fara repetare."""
		if self._rosu_urmarit is not None:
			_jurnal("VK_RED primit de aplicatie (%s)" % motiv)
			self._opresteUrmarirea()

	def _urmaresteRosu(self):
		u = self._rosu_urmarit
		if u is None or self.nav is None or not self.aratat or self.fundal:
			self._opresteUrmarirea()
			return
		u["pasi"] += 1
		fapta, u["vazut"] = urmare_rosu(u["gol"], u["semn"], self._din_mediu("semn_ecran", None), u["vazut"],
			u["pasi"] * ROSU_PAS_MS)
		if fapta == ASTEAPTA:
			return
		self._opresteUrmarirea()
		if fapta == REACTIE:
			_jurnal("VK_RED primit de aplicatie (ecranul)")
		elif fapta == REPETA:
			_jurnal("VK_RED trimis din nou dupa %d ms (%s)" % (u["pasi"] * ROSU_PAS_MS,
				"semnul aplicatiei aparut" if u["gol"] else "ecranul neschimbat"))
			self._rosu_trimis_la = self._timp()
			self.nav.tasta(KEY_RED, 1)
			self.nav.tasta(KEY_RED, 0)

	def laIncarcare(self):
		"""Lansatorul incepe o pagina noua (INCARCARE): dupa VK_RED, aplicatia l-a primit si merge mai departe. Filmul
		pornit de pagina de dinainte se opreste (obiectul A/V pleaca odata cu ea)."""
		self._reactieRosu("pagina noua")
		self._avOpreste()

	# ------------------------------------------------ paza

	def _evenimentCanal(self, ev):
		# chemat din Navigation.dispatchEvent: nicio exceptie nu iese
		try:
			if self.nav is None:
				if self._car_asteapta is not None and ev in self._ev_canal:
					self._anuleazaCarusel(motiv="canalul schimbat")
				return
			if self._av is not None and self._avEveniment(ev):
				return
			if ev in self._ev_canal:
				if self._zap is not None or self._timp() < self._ignora_pana:
					return                     # schimbarea ceruta de aplicatie (setChannel, stop, release)
				if self._pastreazaLaZap():
					return                     # ramane (ascunsa) daca e semnalata si in canalul nou
				if self.serviciu_oprit and self._din_mediu("ref_curent", "") not in ("", self.serviciu_oprit):
					self.serviciu_oprit = None     # omul a ales alt canal: cel oprit de aplicatie nu mai porneste
				self.inchide(motiv="canalul schimbat")
			elif ev in self._ev_ait:
				if self._zap is not None:
					self._verificaZap()
				elif self._zap_om is not None:
					self._verificaZapOm()
				else:
					self._verificaAitAcum()
					self._trimite("app")           # app.ait (de pornit prin dvb://current.ait) dupa AIT-ul nou
			elif ev in self._ev_eit and self.strat and self.legata and self._zap is None and self._zap_om is None:
				p = self._programe_acum()
				if p != self._programe:
					self._programe = p
					self.nav.hbbtvParte("programe", p)
					self._ev({"ev": "programe"})
		except Exception as e:
			_jurnal("eveniment: %s" % e)

	def _verifica(self):
		if self.nav is None:
			self._ceas.stop()
			return
		try:
			if self.m.in_standby() or self.m.in_timeshift():
				self.inchide(motiv="standby sau timeshift")
				return
			if OPRESTE_LA_INREGISTRARE and self._din_mediu("inregistrare_pornita", False):
				# inregistrarea are intaietate (nevazuta: fara mesaj)
				self.inchide(None if self.fundal else "inregistrare-oprire", motiv="inregistrare")
				return
			if self.fundal and not self._din_mediu("autostart_pornit", False):
				self.inchide(motiv="pornirea automata oprita din setari")
				return
			if not self._din_mediu("hbbtv_pornit", True):
				self.inchide(motiv="HbbTV oprit din setari")
				return
			if self._zap is not None:
				self._verificaZap()
			elif self._zap_om is not None:
				self._verificaZapOm()
			elif (not self.serviciu_oprit and self._av is None and self._timp() >= self._ignora_pana and
					self.m.ref_curent() != self.ref):
				if not self._pastreazaLaZap():
					self.inchide(motiv="canalul schimbat")
					return
			if self.nav is None:
				return
			if self._arata_cerut and self.pornita and not self._asteapta_arata and not self.fundal and self.m.bara_libera():
				self._cereArata()
			mem = self.m.memorie_libera_kb()
			prag = MEMORIE_FUNDAL_KB if self.fundal else MEMORIE_OPRIRE_KB
			if mem is not None and mem < prag:
				_jurnal("memorie libera %d kB, aplicatia se inchide" % mem)
				self.inchide(None if self.fundal else "memorie-oprire", motiv="memorie")
		except Exception as e:
			_jurnal("verificare: %s" % e)

	def inchide(self, mesaj=None, motiv=None):
		"""Aplicatia se inchide (canalul ramane); `mesaj` (cheie din TEXTE) se arata dupa; `motiv` numai in jurnal."""
		if self.nav is None:
			return
		if mesaj and not self._mesaj:
			self._mesaj = mesaj
		if motiv and not getattr(self, "_motiv", None):
			self._motiv = motiv
		# imaginea canalului pe tot ecranul INAINTE ca navigatorul sa-si goleasca stratul: altfel, intre golire si
		# laOprit (oprirea WebKit, iesirea procesului), se vede o clipa imaginea mica din fereastra aplicatiei (masurat pe
		# receptor: 200 ms)
		mica = self._video_pus is not None
		self._inchidere = True
		self._aplicaFereastra()
		if mica and self._video_pus is None:
			self._din_mediu("asteapta_ms", None, INCHIDERE_ASTEAPTA_MS)
		self.nav.opreste()

	# ------------------------------------------------ lansator.Ascultator

	def laPas(self, pas, procent):
		if self.nav is not None and pas == "pornire" and not self.fundal:
			self.m.arata_incarcare(True)

	def poateArata(self):
		"""Fara strat (H2): prima pagina se arata pe loc, daca bara e libera. O aplicatie pornita automat nu se poate
		tine ascunsa fara strat: se opreste (si nu se mai incearca pe acest canal)."""
		self.m.arata_incarcare(False)
		if self.fundal:
			_jurnal("pornirea automata cere stratul HbbTV; aplicatia se opreste")
			self._automat_refuzat = self.ref
			return False
		if not self.m.bara_libera():
			_jurnal("alta fereastra peste bara; aplicatia nu se arata")
			return False
		self.m.ascunde_bara()
		return True

	def laPrimaPaginaAscunsa(self):
		"""Cu strat: prima pagina a venit, aplicatia ramane ascunsa pana la show() (fereastra mica ramane). Pornita automat
		: ramane nevazuta (fara cadre) pana la ROSU, fara termen si fara VK_RED."""
		if self.nav is None:
			return
		self.pornita = True
		self._verificaDesenul()
		if self.fundal:
			self._vizibil(False)
			_jurnal("aplicatia pornita automat e gata, ascunsa (ROSU o arata)")
			return
		self._asteapta_arata = True
		self._ceas_arata.start(TERMEN_ARATA_MS, True)
		if self.autostart:
			self._rosu_de_trimis = True
			self._ceas_rosu.start(ROSU_FARA_ARATA_MS, True)   # rezerva: aplicatia care se arata abia la ROSU
		if self._arata_cerut:
			self._cereArata()

	def laAratat(self):
		self.aratat = True
		self.pornita = True
		_jurnal("aplicatia e pe ecran")
		if self.autostart and not self.strat:
			self._ceas_rosu.start(ROSU_DUPA_MS, True)

	def laEcranInapoi(self):
		self.m.redeseneaza()

	def laCerere(self, fel, date):
		if self.nav is not None:
			self.nav.reia()

	def laFavorit(self, adresa, titlu):
		pass

	def _verificaDesenul(self):
		"""GL a cazut in procesul web (randul "REZERVA procesor proces-web-cazut": Skia nu merge pe Mali-450):
		aplicatiile urmatoare pornesc direct pe procesor, fara pornirea pierduta (pana la repornirea enigma2)."""
		rezerva = str(getattr(self.nav, "rezerva", "") or "")
		if "proces-web-cazut" in rezerva and not self._desen_procesor:
			self._desen_procesor = True
			_jurnal("GL a cazut: aplicatiile urmatoare pornesc direct pe procesor")

	def laOprit(self, motiv):
		self._verificaDesenul()
		self._legaTaste(False)
		self._ceas.stop()
		self._ceas_rosu.stop()
		self._ceas_rosu_urma.stop()
		self._ceas_arata.stop()
		self.m.asculta_nav(self._evenimentCanal, False)
		self.m.arata_incarcare(False)
		# caruselul aplicatiei (daca a venit din el): cititorul, serverul si dosarul pleaca la orice inchidere
		self._ceas_carusel.stop()
		self._car_asteapta = None
		self._opresteCarusel()
		nav, self.nav = self.nav, None
		# inainte de _gol(): aplicatia pornise (prima pagina venise) sau se vazuse pe ecran macar o data
		pornita, vazuta = self.pornita, self.aratat or self._aratata_vreodata
		self.aratat = False
		nevazuta, ref = self.fundal, self.ref
		mesaj, self._mesaj = self._mesaj, None
		motiv_jurnal, self._motiv = getattr(self, "_motiv", None), None
		url, agent = self._url, self._agent
		self._avOpreste()                      # filmul aplicatiei se opreste odata cu ea
		self._aplicaFereastra()                # imaginea canalului pe tot ecranul la orice inchidere (si la cadere)
		self._pornesteServiciu()
		self._gol()
		_jurnal("inchisa (%s%s)" % (motiv or mesaj or motiv_jurnal or "de om", ", era nevazuta" if nevazuta else ""))
		if nevazuta:
			# pornita automat si nevazuta: niciun mesaj; se reporneste numai dupa o inchidere data de canal (zap); orice
			# alta (destroyApplication, eroare, paza, cadere, locul cedat) o opreste pe acest canal pana la urmatorul zap
			if motiv is not None or mesaj or motiv_jurnal not in INCHIDERI_DE_CANAL:
				self._automat_refuzat = ref
		elif mesaj:
			self.m.mesaj(text_mesaj(mesaj, _))
		elif motiv is not None and nav is not None:
			# "nu a pornit" numai cand chiar nu a pornit; o aplicatie care a pornit (SAT.1 Gold: pe ecran 7 s, apoi
			# caderea navigatorului) "s-a inchis"
			L = self.m.lansator()
			eroare = L.textEroare(motiv, _)
			# fara prima pagina: motivul adevarat, daca se afla (adresa inexistenta, pagina mutata, fara internet ...)
			if pornita or not self._spuneMotivul("nu-a-pornit", url, agent, baza=eroare):
				self.m.mesaj(text_mesaj("s-a-inchis" if pornita else "nu-a-pornit", _) + "\n\n" + eroare)
		elif motiv_jurnal == "destroyApplication" and not vazuta and nav is not None:
			# aplicatia s-a inchis singura inainte sa se arate: altfel omul vede numai fereastra "se porneste" disparand
			if not self._spuneMotivul("s-a-inchis-singura", url, agent):
				self.m.mesaj(text_mesaj("s-a-inchis-singura", _))
		if self._ascultare_automata:
			# ETSI TS 102 796 cap. 6.2.2.3: dupa iesirea aplicatiei porneste din nou cea AUTOSTART (aici ascunsa); dupa un
			# zap, cea a canalului nou
			self._ceas_automat.start(AUTOMAT_DUPA_MS, True)


_CONTROLOR = []
_ASCULTA_TRADUCEREA = []


def traducere_pagina(cheie):
	""""traducere" pentru config-ul paginii: {port, cheie} cand "Tradu HbbTV" e pornita (port 0 cand interfata web nu
	asculta: atunci scriptul paginii traduce numai prin puntea lansatorului 0.7.0), altfel None (fara cheie sau fara
	modulul traducerii: nimic)"""
	if not cheie:
		return None
	try:
		from Components import HdsTraducereTexte
		if not HdsTraducereTexte.poartaDeschisa("hbbtv"):
			return None
		web = sys.modules.get("Plugins.Extensions.HdsWebControl.plugin")
		port = int(web.portFolosit()) if web is not None else 0
	except Exception as e:
		_jurnal("traducerea: %s" % e.__class__.__name__)
		return None
	if not 0 < port < 65536:
		port = 0
	return {"port": port, "cheie": cheie}


TRADU_ID = re.compile(r"^[0-9a-z]{1,16}$")
TRADU_MAX_TEXTE = 60          # ca la HdsWebControl/traducere_hbbtv_web.py
TRADU_MAX_TEXT = 1500


def raspuns_traducere(cerere, X=None):
	"""cererea paginii ({"t": [texte]}) -> raspunsul, ca la interfata web: {"result": True, "t": [traducerea | 0 | None]}
	(0 = ramane originalul, None = inca se traduce: pagina cere din nou mai tarziu), {"result": False, "oprit": True}
	cand setarea e oprita sau niciun serviciu nu e gata, {"result": False} pentru o cerere gresita. Nu arunca."""
	texte = cerere.get("t") if isinstance(cerere, dict) else None
	if not isinstance(texte, list) or len(texte) > TRADU_MAX_TEXTE or not all(isinstance(t, str) and len(t) <= TRADU_MAX_TEXT
			for t in texte):
		return {"result": False}
	try:
		if X is None:
			from Components import HdsTraducereTexte as X
		if not X.poartaDeschisa("hbbtv"):
			return {"result": False, "oprit": True}
		lista, stare = X.traduceri("hbbtv", texte)
	except Exception as e:
		_jurnal("traducerea: %s" % e.__class__.__name__)
		return {"result": False, "oprit": True}
	if stare == X.STARE_OPRIT:
		return {"result": False, "oprit": True}
	rez = []
	for t, v in zip(texte, lista):
		if v is None:
			rez.append(None)
		elif v == t or not v:
			rez.append(0)
		else:
			rez.append(v)
	return {"result": True, "t": rez}


def _asculta_traducerea(c):
	"""o singura data: controlorul afla cand se schimba setarile traducerii (config trimis din nou)"""
	if _ASCULTA_TRADUCEREA:
		return
	try:
		from Components import HdsTraducereTexte
		HdsTraducereTexte.ascultaSchimbarile(c._laTraducere)
		_ASCULTA_TRADUCEREA.append(True)
	except Exception as e:
		_jurnal("traducerea: %s" % e.__class__.__name__)


def cheieTraducere():
	"""cheia aplicatiei HbbTV de acum pentru traducerea textelor (HdsWebControl/traducere_hbbtv_web.py), sau None
	cand nu ruleaza nicio aplicatie"""
	if not _CONTROLOR or _CONTROLOR[0].nav is None:
		return None
	return _CONTROLOR[0]._cheie_trad


def controlor(session):
	if not _CONTROLOR:
		_CONTROLOR.append(Controlor(Mediu(session)))
	return _CONTROLOR[0]


def porneste(session):
	"""O singura data, la pornirea enigma2 (mytest.py): fereastra video lasata mica de o aplicatie HbbTV inainte de o
	cadere a interfetei se pune pe tot ecranul, dosarul caruselului ramas se sterge, iar controlorul asculta canalul redat pentru pornirea automata
	(nu face nimic cat setarea e oprita)."""
	video_intreg_la_pornire()
	try:
		_server().curata()                 # caruselul ramas de la o cadere a interfetei
	except Exception as e:
		_jurnal("caruselul ramas: %s" % e)
	c = controlor(session)
	c.porneste_ascultarea()
	return c


def setari_salvate():
	"""Dupa salvarea setarilor navigatorului (televizorul: ecrane.HdsNavigatorSetari.salveaza; web:
	navigator_web.seteaza): HbbTV oprit -> orice aplicatie HbbTV se inchide pe loc; pornirea automata oprita -> cea
	nevazuta se inchide, pornita -> se verifica pe canalul de acum. Notificarile config nu ajung aici la salvare
	(changedFinal vine din onDeselect, iar din web deloc), de aceea chemarea e directa."""
	if not _CONTROLOR:
		return
	c = _CONTROLOR[0]
	if not c._din_mediu("hbbtv_pornit", True):
		c.laSetareaHbbtv(False)
		return
	c.laSetareaAutomata(c._din_mediu("autostart_pornit", False))


def apasaRosu(bara):
	"""Din Screens/InfoBar.py: 1 cand ROSU a facut ceva, 0 cand tasta trebuie sa mearga mai departe."""
	try:
		return controlor(bara.session).rosu(bara)
	except Exception as e:
		_jurnal("ROSU: %s" % e)
		return 0


def deschisa():
	"""Aplicatia HbbTV e deschisa (sau porneste) acum, pornita de om sau aratata cu ROSU (nu cea pornita automat si inca
	nevazuta)."""
	return bool(_CONTROLOR and _CONTROLOR[0].nav is not None and not _CONTROLOR[0].fundal)


def ultima():
	"""Pentru web (/api/navigator): motivul ultimei aplicatii HbbTV care nu a pornit, s-a inchis singura sau nu s-a
	aratat: {"motiv", "text" (netradus, cheia din TEXTE), "ora"}, sau None. Fara adrese."""
	if not _CONTROLOR or not _CONTROLOR[0]._ultima:
		return None
	return dict(_CONTROLOR[0]._ultima)

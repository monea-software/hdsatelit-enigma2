# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsActualizari.py: "Actualizare software" prin pachete opkg, din feedul imaginii.
# Ecranul e Screens/HdsActualizari.py, pagina web HdsWebControl/actualizari_web.py; amandoua citesc si pornesc totul
# de aici (o singura stare, o singura lucrare odata).
#
# Feedul: https://stb.hdsatelit.com/feed/<canal>/<baza>/<arh>/ (Packages.gz si .ipk) si .../<baza>/stare.json, unde
# <baza> e imaginea scrisa pe receptor (version= din /etc/hdsatelit-model, pus de reteta imaginii si neatins de
# pachete). Sursele opkg: /etc/opkg/hdsatelit-feed.conf (canalul public, din imagine) si
# /etc/opkg/hdsatelit-proba-feed.conf (canalul de proba, numai pe receptoarele noastre, pus de trusa impreuna cu
# parola din /home/root/.netrc). Parola nu sta in adrese: opkg ar scrie-o in "Downloading ..."; wget-ul pornit de opkg
# o ia din $HOME/.netrc (enigma2 are HOME=/, de aceea si legatura /.netrc), iar stare.json se cere de aici cu ea.
#
# Feedul unic (0.7.9, UNF9): baza din adrese (a feedului) si baza scrisa (version= din /etc/hdsatelit-model: nucleul,
# modulele, bibliotecile de baza, care nu vin niciodata prin feed) nu mai sunt neaparat aceeasi. Un feed cu "unic": true
# in stare.json e al tuturor bazelor scrise de la "imagine_minima" incoace, pe linia x.y a bazei lui. Trecerea o
# porunceste stare.json semnat al feedului bazei, cu "feed_unic": <baza feedului unic>: stare_cu_feedul_unic citeste
# atunci stare.json al feedului unic pe acelasi canal si trece numai daca e semnat, e unic, are toate arhitecturile
# receptorului in "indexuri", imagine_minima nu e mai noua decat baza scrisa, iar baza scrisa nu e in "intoarce_baze";
# trecerea rescrie, atomic, numai randurile feedului HD Satelit din CONF_PUBLIC si CONF_PROBA (baza din adresa).
# "intoarce_baze" din feedul unic trimite receptorul inapoi pe feedul bazei lui scrise (adresa se reface din version=).
# Fara texte pe ecran: totul se scrie in jurnal. Verdictul cere stare.json "baza" = baza din adrese si, cand ea nu e
# baza scrisa, "unic": true; imagine_minima se compara cu baza scrisa.
#
# Numaratoarea anonima (0.7.9, UNF9): fiecare cerere stare.json are antetul ANTET_NUMARARE cu un numar aleator al
# instalarii (FISIER_INSTALARE, facut o data cu os.urandom; nu e MAC, serie sau alt semn al aparatului), versiunea care
# ruleaza, baza scrisa si modelul (machinebuild=); serverul numara receptoarele pe versiune
# (unelte/stb/numara_receptoare.py).
#
# Cautarea: stare.json (pe un fir separat), apoi `opkg update`, apoi planul (pe un fir separat): pachetele instalate
# pentru care sursele HD Satelit ale canalului au o versiune mai noua, cu dependintele verificate fata de ce e
# instalat (si fata de numele date prin Provides, ca opkg). Feedul unei baze e comun mai multor masini (V10, SF8008 si
# MINI): pachetele planului se cauta in stare.json dupa nume SI arhitectura (a strofei din listele receptorului, deci
# una din arch.conf), ca acelasi nume facut pentru doua masini sa dea fiecaruia fisierul lui. Instalarea: `opkg install <fisier>` (Semnatura), numai la cererea omului si numai daca verdictul o lasa;
# dupa ea interfata trebuie repornita (fisierele enigma2 de pe disc s-au schimbat sub interfata care ruleaza), deci
# nimic altceva nu mai porneste de aici pana atunci.
#
# Verdictul "imagine noua" (nu se instaleaza, se spune de ce): stare.json o cere, baza feedului alta decat baza
# receptorului, imaginea minima mai mare, un pachet de nucleu, drivere sau biblioteci de baza in plan, o dependinta
# pe care imaginea nu o are, sau mai mult de PRAG_PACHETE pachete. Nu exista "continua totusi".
#
# Versiunile: omul vede numai versiunea (0.3.2), adica partea dinaintea lui "+git"
# din versiunea pachetului enigma2-hdsatelit instalat si campul "versiune" din stare.json; fiecare actualizare prin
# pachete are urmatorul numar (construieste-pachete.sh). Baza (imaginea scrisa de pe stick, /etc/hdsatelit-model) e
# numai a feedului si se arata ca detaliu ("Imaginea de bază" in "Despre" si la avertizarea de imagine noua). Campul
# "actualizare" din stare.json e un numar intern (creste la fiecare publicare): leaga pagina web de rezultatul vazut.
#
# Verificarea zilnica (VerificareZilnica, pornita din mytest.py la fiecare pornire a interfetei, deci si dupa o
# actualizare si la prima pornire a unei imagini noi): numai stare.json, la 5 minute dupa pornire si apoi o data pe zi,
# numai cu internetul activ (FARA_RETEA_S); anunta o singura data fiecare actualizare noua (sau imagine noua); se opreste
# din ecran sau din pagina web (config.hds_actualizari.zilnic). Din 0.8.0 (AUT1), cu Actualizari automate pornite
# (config.hds_actualizari.automat, Da), o versiune noua din feed nu se mai anunta: se instaleaza singura in standby sau
# noaptea, iar la prima folosire de dupa se arata pe scurt ce s-a schimbat (vezi AUTO_CEAS_S).
#
# "Ce e nou": stare.json are si campul "versiuni" (scris de oe-build/feed_actualizare.py din
# jurnalul imaginii): noutatile fiecarei versiuni publicate pe baza aceasta, in romana si in engleza. La cautare se
# pastreaza numai versiunile mai noi decat cea instalata, pana la cea de pe server (de la 0.3.2 la 0.3.5: 0.3.5, 0.3.4
# si 0.3.3), iar ecranul si pagina web le arata grupate, in limba receptorului (noutati, text_noutati). Un stare.json
# fara camp (feedurile de dinainte) sau cu el stricat arata "ce_e_nou" al versiunii de pe server, ca pana acum.
#
# Semnatura: receptorul instaleaza numai ce e semnat de HD Satelit, chiar daca
# serverul feedului ar fi spart. stare.json se primeste numai cu stare.json.sig de langa el, verificata pe octetii
# primiti cu cheile din Components/HdsSemnatura.py; stare.json semnat tine sha256 pentru fiecare <arh>/Packages
# ("indexuri") si pentru fiecare .ipk. Dupa `opkg update`, listele feedului trebuie sa fie chiar cele semnate (altfel se
# sterg). La instalare, pachetele planului se descarca aici, in DOSAR_PACHETE, se verifica (marimea si sha256 semnate)
# si abia apoi le instaleaza opkg din fisier (`opkg install <cale>`: fisierul local are intaietate, deci se instaleaza
# chiar octetii verificati, nu o versiune mai mare din alta sursa). Orice nepotrivire da starea NESEMNATA ("Actualizarea
# nu e semnată de HD Satelit; nu se instalează.") si nimic nu ajunge la opkg. Dupa un `opkg update` al Extensiilor,
# pazeste_listele sterge listele HD Satelit care nu sunt cele din ultima stare.json semnata. opkg 0.8.0 din imagine stie
# semnaturi numai prin gpg (nu e compilat cu el), de aceea verificarea e aici.
#
# "Actualizează rapid" (pagina web, actualizeazaRapid): un singur clic cauta, instaleaza daca e o actualizare de
# instalat si reporneste interfata, totul aici, pe receptor (pagina se poate inchide dupa apasare). Cautarea si
# instalarea sunt chiar cauta() si instaleaza(), cu aceleasi verificari (semnatura, pachetele, verdictul); orice alt
# rezultat (la zi, imagine noua, nesemnata, fara retea, o eroare) opreste modul rapid si lasa mesajul obisnuit.
# Repornirea o da pagina web (TryQuitMainloop 3, calea sigura), numai cand nu ar intreba pe televizor: cat o
# inregistrare e in curs sau incepe in mai putin de 6 minute, cat merge o lucrare in fundal sau cat o intrebare de
# repornire e pe ecran, se asteapta si se incearca din nou, apoi interfata se reporneste singura (ca TryQuitMainloop
# cand nu raspunde nimeni la intrebare).
#
# Reusita instalarii: fiecare pachet al planului are dupa opkg, in status-ul lui, chiar versiunea noua. Codul de iesire
# al lui opkg singur nu hotaraste: `opkg install` configureaza la sfarsit si ORICE alt pachet din receptor ramas
# neconfigurat (o extensie straina al carei postinst a cazut la instalarea ei) si iese cu 255 cand acela cade iar, desi
# actualizarea s-a instalat intreaga. Atunci instalarea e reusita, iar codul si pachetele neconfigurate se scriu numai in
# jurnal (pagina web il arata), nu pe televizor.
#
# Jurnalul (JURNAL) sta in dosarul jurnalelor de pe memoria interna: ramane dupa repornire (de acolo il trimit testerii)
# si se vede in Jurnalele sistemului, pe televizor si in web; cel mult MARIME_JURNAL, apoi trece in <nume>.1.
#
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC: teste/test_actualizari_pachete_*.py,
# teste/test_semnare_actualizari.py, teste/test_actualizare_rapida.py si teste/test_actualizari_arhitectura_provides.py).

import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import threading
import time
import zlib
from functools import cmp_to_key

try:
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError, URLError
except ImportError:  # Python 2 (probe vechi)
	from urllib2 import Request, urlopen, HTTPError, URLError

try:
	from Components import HdsPachete as P
except ImportError:  # probele de pe PC: modulul incarcat singur, din dosarul Components
	import HdsPachete as P


def N_(text):
	"""Marcheaza un text pentru xgettext (--keyword=N_) fara sa-l traduca acum."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


ADRESA_FEED = 'https://stb.hdsatelit.com/feed'
GAZDA_FEED = 'stb.hdsatelit.com'
FISIER_MODEL = '/etc/hdsatelit-model'
CONF_PUBLIC = '/etc/opkg/hdsatelit-feed.conf'
CONF_PROBA = '/etc/opkg/hdsatelit-proba-feed.conf'
NETRC = ('/home/root/.netrc', '/.netrc')
# lacatul lui opkg: opkg 0.10 din imagine il ia in /run/opkg.lock (opkg.conf nu are lock_file; vazut pe receptorul de proba in timpul
# unei instalari, 11.11.2026). /var/run duce in /var/volatile/run, alt dosar, unde opkg nu-l pune niciodata: cu numai
# /var/run/opkg.lock, opkg_ocupat nu vedea nicio instalare (Extensii, SSH). Calea veche ramane a doua (alte versiuni).
LACAT_OPKG = '/run/opkg.lock'
LACATE_OPKG = (LACAT_OPKG, '/var/run/opkg.lock')
JURNAL = P.DOSAR_JURNALE + '/hds-actualizari.log'
MARIME_JURNAL = P.MARIME_JURNAL
PACHET_PRINCIPAL = 'enigma2-hdsatelit'
PRAG_PACHETE = 150
# Starea feedului bazei (stare.json) creste cu fiecare model nou (drivere si completari pe masina, ~15-20 KB pe model):
# 250 KB la 13 modele in 0.7.4 (12.11.2026). 2 MB ajung pentru ~90 de modele; un JSON de 2 MB se citeste usor si pe Solo SE.
MARIME_STARE_MAX = 2 * 1024 * 1024
TIMP_STARE = 20
# pazeste_listele cere stare.json pe firul interfetei, imediat dupa opkg update: timp scurt
TIMP_STARE_PAZA = 6
PRIMA_VERIFICARE = 300
ZI = 24 * 3600
REINCERCARE = 3 * 3600
# 0.8.0 (AUT1, Eduard 27.11.2026 22:03): verificarea numai cu internetul activ. Fara ruta implicita (fara_retea, o citire
# din /proc) nu se cere si nu se anunta nimic, iar verificarea se reia la FARA_RETEA_S; cu ruta, dar fara raspuns de la
# server (routerul fara internet, DNS-ul cazut), la PAUZA_SERVER_S, dublata la fiecare cadere, cel mult REINCERCARE.
FARA_RETEA_S = 60
PAUZA_SERVER_S = 300
# Actualizarile automate (config.hds_actualizari.automat, Da din fabrica): o versiune noua din feed (nu o imagine noua) se
# instaleaza singura pe drumul actualizarii rapide (actualizeazaRapid: semnatura, verdictul, pachetele de pornire si de
# nucleu refuzate, repornirea interfetei cu motiv_asteptare), cand receptorul e in standby sau noaptea (ORE_NOAPTE, ora
# locala, ceasul pus) treaz, dar fara nicio tasta de FARA_TASTE_S. Conditiile se verifica la AUTO_CEAS_S cat e ceva de
# instalat. O singura incercare pe versiune la o pornire: dupa una cazuta ramane anuntul obisnuit.
AUTO_CEAS_S = 180
# dupa o incercare cazuta (retea, verdictul din plan, loc), alta abia la verificarea de dupa REINCERCARE_AUTO_S; pana atunci
# fereastra din HdsImagineOnline (si anuntul) revin pentru versiunea aceea. Un receptor care nu sta in standby si e oprit
# noaptea nu prinde prilejul niciodata: dupa ASTEPTARE_MAX_S de la prima vedere a versiunii (config.hds_actualizari.
# asteptare, ramane peste reporniri) fereastra de azi revine si ea, iar instalarea singura ramane pregatita.
REINCERCARE_AUTO_S = 20 * 3600
ASTEPTARE_MAX_S = 2 * ZI
ORE_NOAPTE = (3, 5)
FARA_TASTE_S = 10 * 60
AN_MINIM = 2024
# dupa o instalare automata reusita (sau una facuta in standby): versiunea si cateva randuri din noutati; la prima tasta de
# dupa pornire, cu receptorul treaz, un mesaj scurt (NOTA_S secunde, nu blocheaza nimic), apoi semnul se sterge
FISIER_NOTA_AUTOMATA = '/etc/enigma2/hds-actualizare-automata.json'
MAX_RANDURI_NOTA = 5
NOTA_S = 30
NOTA_DUPA_TASTA_MS = 3000
TEXT_AUTOMAT_NOTA = N_('Receptorul instalează singur actualizările în standby sau noaptea, apoi arată ce s-a schimbat.')
UA = 'hdsatelit-receptor/1'
FORMAT = 1
RANDURI_JURNAL = 200
# campul "versiuni" din stare.json: aceleasi margini ca in oe-build/feed_actualizare.py (verifica_stare)
MAX_VERSIUNI = 30
MAX_RANDURI_VERSIUNE = 60
MAX_SEMNE_NOUTATE = 400
MAX_DATA = 20
LIMBI_NOUTATI = ('ro', 'en')
# semnatura lui stare.json (langa el), pachetele verificate inainte de opkg si indexurile
# din ultima stare.json semnata (pentru Extensii, pazeste_listele)
NUME_SEMNATURA = 'stare.json.sig'
MARIME_SEMNATURA_MAX = 8 * 1024
SCOP_STARE = 'stare.json'
DOSAR_PACHETE = '/tmp/hds-actualizare'
LOC_IN_PLUS = 16 * 1024 * 1024
TIMP_PACHET = 60
INDEXURI_SEMNATE = '/etc/enigma2/hds-indexuri-semnate.json'
# 0.7.5 (FED, TODO 14.11 02:12): copia listelor HD Satelit facuta chiar inainte de opkg update (pastreaza_listele). Cand
# feedul se republica in timpul descarcarii (listele arhitecturilor vin una dupa alta, stare.json separat), o lista noua
# nepotrivita se inlocuieste cu copia ei veche, numai daca si copia e cea dintr-un stare.json semnat; apoi o singura
# reincercare, dupa REINCERCARE_LISTE_MS (Extensii: opkg update; Actualizare software: cautarea intreaga). In RAM, mica.
DOSAR_LISTE_VECHI = '/tmp/hds-liste-semnate'
REINCERCARE_LISTE_MS = 45000
# rezultatul ultimei pazeste_listele (numele surselor): HdsExtensiiLucru il citeste pentru jurnal si reincercare
ULTIMA_PAZA = {'sterse': [], 'puse_la_loc': []}
# actualizarea rapida: repornirea porneste la atatea ms dupa instalare (pagina web apuca sa vada pasul inainte sa cada
# interfata); cat ar intreba pe televizor, se incearca din nou la atatea ms
REPORNIRE_RAPIDA_MS = 3000
REINCERCARE_RAPIDA_MS = 30000
# 0.7.8 (HB7, Catalin Oancea 18.11.2026, Octagon SF8008 Supreme, dupa 0.7.6 -> 0.7.7 din meniu: HbbTV nu merge, la
# cautarea oarba nu se poate schimba satelitul): actualizarea instalata cu interfata nerepornita (Nu pe televizor,
# repornirea din pagina web neapasata, o inregistrare sau o lucrare in fundal care o amana cat omul foloseste receptorul)
# lasa procesul vechi cu modulele vechi in memorie, iar ce se incarca abia acum vine nou de pe disc: navigatorul (deci
# HbbTV) nu porneste (lansatorul nou cere HdsDecodorWeb.mediu_fara_placa), cautarea oarba nu se deschide sau ramane cea
# veche, fara randul Satelit, desi Despre arata deja versiunea noua (reprodus pe un Octagon; dupa repornire merge tot).
# De aceea: (1) cat repornirea e ceruta, la intrarea in standby interfata se reporneste singura dupa STANDBY_REPORNIRE_MS
# si se intoarce in standby (HdsImagineOnline.STANDBY_DUPA_REPORNIRE), pe aceeasi cale ca repornirea rapida (fara
# inregistrare acum sau curand, fara lucrare in fundal, fara alta intrebare; altfel din nou la STANDBY_REINCERCARE_MS cat
# sta in standby); (2) un ecran cazut in starea asta (mytest.py, handleScreenCrash) reporneste interfata pe aceeasi cale
# (reporneste_dupa_ecran_cazut). Omul nu face si nu confirma nimic; o inregistrare nu se rupe.
STANDBY_REPORNIRE_MS = 60000
STANDBY_REINCERCARE_MS = 300000
# actualizarea oprita la jumatate (0.7.4, LinuxSat 164125 #969426): opkg e copilul enigma2 (Components/Ipkg.py,
# eConsoleAppContainer), iar la orice iesire a enigma2 destructorul ii trimite SIGKILL (lib/base/console.cpp). De aceea:
# SEMN_IN_CURS (pe memoria interna, ramane peste o repornire dura) se scrie inainte de opkg, cu versiunea si pachetele
# planului, si se scoate cand opkg iese singur; tools/hds-actualizare-intrerupta.py (pornit de enigma2.sh inainte de
# enigma2) termina la pornire ce a ramas si scrie REZULTAT_PORNIRE, aratat aici (porneste) pe televizor si in web.
# 0.7.8 (STK, forum 1104 si 1258): opkg oprit de un semnal trimis din afara cat enigma2 merge (un `killall opkg` al altui
# program, lipsa de memorie, o cadere a lui opkg; oprit_de_semnal) NU a iesit singur: status-ul lui nu e scris, iar
# fisierele pot fi amestecate. Atunci semnul ramane si interfata cere repornirea, ca programul de mai sus sa termine
# actualizarea inainte de enigma2. Pe un stick USB lent dezarhivarea tine minute, deci fereastra e cea mai lunga acolo.
# Cat ruleaza opkg, semnul "ocupat" al paznicului (CHEIE_PAZNIC, prelungit de fiecare bataie) tine paznicul departe de
# enigma2, iar Screens/Standby.py TryQuitMainloop asteapta sfarsitul instalarii (instalare_in_curs).
SEMN_IN_CURS = '/etc/enigma2/hds-actualizare.in-curs'
REZULTAT_PORNIRE = '/tmp/hds-actualizare-intrerupta.rezultat'
CHEIE_PAZNIC = 'actualizare'
DURATA_PAZNIC_S = 15 * 60
# cat se instaleaza: mesajul de sub lista (ecranul si pagina web). Pe un stick USB lent dezarhivarea tine minute intregi
# fara niciun rand nou de la opkg; omul care crede ca s-a blocat si opreste receptorul lasa fisierele amestecate
TEXT_INSTALARE = N_('Nu opri receptorul până se termină instalarea. Pe un stick USB poate dura câteva minute.')
TEXTE_PORNIRE = {
	'terminata': N_('Actualizarea %s fusese oprită la jumătate; s-a terminat la pornirea receptorului.'),
	'esuata': N_('Actualizarea %s fusese oprită la jumătate și nu s-a putut termina la pornire. Caută din nou în '
		'Actualizare software; detaliile sunt în jurnalul actualizărilor.'),
	# 0.7.5 (CTU, TODO 15.11 07:08): pachetele Python ale imaginii inlocuite de un pachet strain (modul pachete-pornire);
	# %s = pachetele straine (straine= din rezultat)
	'pornire-reparata': N_('Interfața nu mai pornea: pachetele Python ale imaginii fuseseră înlocuite de un pachet străin '
		'(%s). Le-am pus la loc din actualizările HD Satelit. Pachetul străin a rămas instalat; dacă îl folosești, cere '
		'autorului varianta pentru imaginea aceasta.'),
	'pornire-nereparata': N_('Interfața nu pornea: pachetele Python ale imaginii fuseseră înlocuite de un pachet străin '
		'(%s), iar punerea lor la loc nu a reușit. Detaliile sunt în jurnalul actualizărilor.'),
}
# de ce asteapta repornirea rapida (raspunsul functiei de repornire) si ce se scrie atunci
TEXTE_ASTEPTARE = {
	'inregistrare': N_('Actualizarea s-a instalat. Interfața se repornește singură după înregistrare.'),
	'lucrare': N_('Actualizarea s-a instalat. Interfața se repornește singură după ce se termină lucrarea din fundal.'),
	'intrebare': N_('Actualizarea s-a instalat. Pe televizor se așteaptă un răspuns la întrebarea de repornire.'),
	# 0.7.8 (RIA): omul se uita in urma in timeshift (nu numai tamponul pornit)
	'timeshift': N_('Actualizarea s-a instalat. Interfața se repornește singură după ce ieși din timeshift.'),
}
# 0.7.8 (RIA, dupa HB7: cu interfata nerepornita dupa actualizare unele ecrane cad, iar omul nu afla ca trebuie repornita):
# dupa ORICE actualizare instalata (VERDE din meniu, pagina web, rapida sau Instaleaza, feedul singur, Extensii cand s-a
# schimbat programul imaginii) interfata se reporneste singura pe drumul modului rapid (porneste_repornirea), nu numai
# dupa actualizarea rapida. Treaz, inainte de repornire, fereastra cu textul deja tradus ("Actualizarea s-a instalat.
# Interfata se reporneste acum.", sau al receptorului din HdsMemorieDriver.textRepornire) si numaratoarea de
# NUMARATOARE_S: OK grabeste, EXIT amana pana la urmatoarea intrare in standby (plasa HB7 de mai jos; EXIT nu e
# acceptare). Cand nu se poate acum (motiv_asteptare: inregistrare acum sau curand, timeshift folosit, lucrare in fundal,
# alt opkg, o intrebare deschisa) o singura fereastra scurta cu motivul (TEXTE_ASTEPTARE, ANUNT_S), apoi, cand se
# elibereaza, aceeasi numaratoare. In standby fara nicio fereastra: semnul intoarcerii in standby
# (HdsImagineOnline.STANDBY_DUPA_REPORNIRE), repornirea, receptorul ramane in standby. Setarea
# config.hds_actualizari.repornire_singura (Da din fabrica; purtarea de dinainte ramane pe Nu): pe Nu, in locul
# numaratorii, intrebarea de dinainte ("Actualizarea s-a instalat." / "Repornesti interfata acum?"), iar in pagina web
# butonul Reporneste interfata. Codul care reporneste e cel din memorie: purtarea noua incepe cu actualizarea de dupa
# 0.7.8.
NUMARATOARE_S = 10
ANUNT_S = 8
# 0.7.7 (DRV, Eduard 15.11 22:29, TODO 15.11 12:36): driverul placii adus si prin actualizarea din meniu. Pachetele de drivere
# (TIPARE_IMAGINE_NOUA, „drivere”) raman refuzate, afara de cele din cheia semnata „drivere_placii” a lui stare.json: acolo
# feedul (oe-build/feed_actualizare.py, driver_placii) pune numai pachetul de drivere al placii care difera de cel din
# imagine doar prin hi_fb.ko peticit pentru 2K (aceleasi module, acelasi vermagic, acelasi load), si numai pentru versiunea
# veche data in „de_la” si nucleul dat in „nucleu”. Pachetul NU e in Packages: codul de dinainte de 0.7.7 nu-l vede (altfel
# ar refuza toata actualizarea cu „Actualizarea schimbă driverele receptorului”), deci el il primeste la cautarea de dupa
# instalarea lui 0.7.7. Aici se pune in plan numai cand versiunea instalata e in de_la, nucleul care ruleaza (uname -r) e
# cel cerut si hi_fb.ko de pe disc e cel vechi (hifb_vechi). Fisierul sta in dosarul arhitecturii, ca celelalte pachete.
CHEIE_DRIVERE = 'drivere_placii'
# driverul nou se incarca numai la pornirea receptorului (/etc/init.d/loadmodules, S05), nu la repornirea interfetei: dupa
# instalare semnul tine boot_id-ul pornirii de acum; cat e acelasi, receptorul trebuie repornit (si dupa o repornire a
# interfetei, un Nu pe televizor sau o inregistrare); la alta pornire semnul se sterge singur
SEMN_DRIVER_NOU = '/etc/enigma2/hds-driver-nou.json'
BOOT_ID = '/proc/sys/kernel/random/boot_id'
# titlul driverului in lista pachetelor (ecranul si pagina web), in locul numelui pachetului
TITLU_DRIVER = N_('Driverul plăcii (interfața 2K)')
TEXT_DRIVER_NOU = N_('Actualizarea a schimbat driverul plăcii. Receptorul trebuie repornit ca să-l încarce.')
# 0.7.8 (CM3): acelasi text ca in Components/HdsExtensiiLucru.TEXT_IMAGINE_SCHIMBATA (tradus din 0.7.7), pentru
# repornirea ceruta cand programul imaginii s-a schimbat pe disc pe alt drum decat actualizarea (cere_repornirea_imaginii)
TEXT_IMAGINE_SCHIMBATA = N_('Programul imaginii s-a schimbat. Interfața trebuie repornită ca să-l folosească.')
TEXT_DRIVER_DISPONIBIL = N_('Actualizare software: driverul plăcii pentru interfața 2K e gata de instalat. Îl instalezi din '
	'Actualizare software; la sfârșit receptorul se repornește.')
# 0.7.9 (UNF9): feedul unic (vezi capul fisierului) si numaratoarea anonima
CHEIE_FEED_UNIC = 'feed_unic'
CHEIE_UNIC = 'unic'
CHEIE_INTOARCE = 'intoarce_baze'
FISIER_INSTALARE = '/etc/hds-instalare.id'
ANTET_NUMARARE = 'X-Hds-Numarare'
_NUMARARE = {}
# verificarea zilnica si cea din HdsImagineOnline pornesc deodata: numarul instalarii il face un singur fir
_LACAT_NUMARARE = threading.Lock()
_LUCRARI_NUMARARE = []

_BAZA = re.compile(r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\Z')
# versiunea vazuta de om (si vechile nume x.y.z.N de dinainte de versiunile simple)
_VERSIUNE = re.compile(r'^[0-9]{1,3}(?:\.[0-9]{1,3}){2,3}\Z')
_ADRESA_FEED = re.compile(r'^https://stb\.hdsatelit\.com/feed/(proba|public)/([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})/'
	r'([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
_SHA256 = re.compile(r'^[0-9a-f]{64}\Z')
_FISIER_IPK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9+._~\-]{0,200}\.ipk\Z')
_ARH = re.compile(r'^[a-z0-9][a-z0-9_\-]{0,63}\Z')

# pachetele care nu se schimba prin actualizare (nucleul, driverele, bibliotecile de baza); aceeasi lista o are si
# scriptul care face feedul, deci ele nu ajung niciodata in feed
TIPARE_IMAGINE_NOUA = (
	# driverele inaintea nucleului: kernel-module-* incepe si el cu kernel-
	('drivere', re.compile(r'^(kernel-module-|dinobot-|.*-dvb-modules|firmware-|v4l-dvb-)')),
	('nucleu', re.compile(r'^(kernel$|kernel-|linux-|uimage)')),
	('biblioteci', re.compile(r'^(libc6|libc-|glibc|ld-linux|libgcc|libstdc\+\+|busybox|opkg|update-alternatives|'
		r'python3-core|python3$|libpython3|openssl|libssl|libcrypto|base-files|base-passwd|sysvinit|initscripts|'
		r'eudev|udev|netbase|libz1|zlib)')),
)

# motivele "imagine noua", in ordinea in care se arata
MOTIVE = (
	('baza', N_('Actualizările de pe server sunt pentru altă imagine decât cea de pe receptor.')),
	('imagine-minima', N_('Actualizarea cere o imagine mai nouă decât cea de pe receptor.')),
	('nucleu', N_('Actualizarea schimbă nucleul Linux.')),
	('drivere', N_('Actualizarea schimbă driverele receptorului.')),
	('biblioteci', N_('Actualizarea cere biblioteci de bază pe care imaginea de acum nu le are.')),
	('prea-multe', N_('Actualizarea are prea multe pachete pentru o instalare din meniu.')),
	('alt-motiv', N_('Pentru această actualizare trebuie pusă imaginea nouă.')),
)
TEXT_MOTIV = dict(MOTIVE)
TEXT_STATUS_STRICAT = N_('Nu pot verifica versiunea instalată. Nu s-a instalat nimic. Detaliile sunt în jurnalul '
	'actualizărilor.')
# 0.7.5 (JAK, TODO 13.11 11:20): actualizarea de dinainte a lasat pachete ale imaginii la jumatate in status (o ciocnire
# de fisiere cu un pachet strain, un opkg oprit): cautarea le pune in plan ca reinstalare (planul_reinstalarii)
TEXT_REINSTALARE = N_('Actualizarea de dinainte a rămas neterminată. La instalare pachetele ei se pun din nou, din feedul '
	'HD Satelit.')
PREFIX_IMAGINE = 'hdsatelit-'
# 0.7.7 (UPD, TODO 15.11 18:48 FR11): si half-configured (postinst-ul cazut), ca la programul de la pornire
# (tools/hds-actualizare-intrerupta.py). Fara el, un enigma2-hdsatelit half-configured (si pornirea care a renuntat dupa
# 3 incercari) dadea la FIECARE cautare "Nu pot verifica versiunea instalata. Nu s-a instalat nimic.", deci receptorul nu
# mai ajungea la nicio actualizare; acum cautarea ofera reinstalarea din feedul semnat (--force-reinstall), iar daca
# postinst-ul cade iar, motivul lui se vede la instalare si in jurnal.
STARI_NETERMINATE = ('half-installed', 'unpacked', 'half-configured')
TEXT_IMAGINE_NOUA = N_('Trebuie pusă imaginea nouă de la zero, din „Imagine nouă de pe stick”. Instalată din meniu peste '
	'imaginea de acum, actualizarea poate face receptorul instabil, de aceea aici nu se instalează.')

# starea cautarii (rezultat['stare']) si textul ei
NECAUTAT, LA_ZI, DISPONIBILA, IMAGINE_NOUA, FARA_RETEA, FARA_RASPUNS, FARA_SURSA, FARA_CHEIE, EROARE = (
	'necautat', 'la-zi', 'disponibila', 'imagine-noua', 'fara-retea', 'fara-raspuns', 'fara-sursa', 'fara-cheie',
	'eroare')
# stare.json, listele sau un pachet nu sunt cele semnate de HD Satelit
NESEMNATA = 'nesemnata'
TEXTE_STARE = {
	NECAUTAT: N_('Actualizările nu au fost căutate încă.'),
	LA_ZI: N_('Software-ul este la zi.'),
	DISPONIBILA: N_('Este disponibilă o actualizare.'),
	IMAGINE_NOUA: N_('Actualizarea nu se poate instala din meniu.'),
	FARA_RETEA: N_('Receptorul nu este conectat la internet acum, deci actualizările nu se pot căuta.'),
	FARA_RASPUNS: N_('Serverul de actualizări (stb.hdsatelit.com) nu a răspuns.'),
	FARA_SURSA: N_('Imaginea de pe receptor nu are sursa actualizărilor.'),
	FARA_CHEIE: N_('Canalul de probă cere parola receptorului, care lipsește sau nu mai este bună.'),
	NESEMNATA: N_('Actualizarea nu e semnată de HD Satelit; nu se instalează.'),
	EROARE: N_('Căutarea actualizărilor nu a reușit.'),
}


# ---------------------------------------------------------------- texte si curatenie

def curata(text):
	"""Un rand de opkg sau o eroare, intreg (si numele si parola din adrese: REGULA 0, ASI7, in imagine nu se mascheaza
	nimic pana dupa 1.0), fara caractere de control."""
	text = u'%s' % (text or '')
	return ''.join(c for c in text if c >= ' ' or c == '\t')[:400]


def motiv_eroare(linii, implicit):
	"""Motivul unei erori opkg, numai din ce scrie opkg (fara presupuneri, fara trimiteri la tastele altor ecrane)"""
	t = '\n'.join(linii).lower()
	if 'no space left' in t or ('only have' in t and 'available' in t):
		return _t('Nu mai este loc în memoria receptorului.')
	if 'could not obtain administrative lock' in t or 'could not lock' in t:
		return _t('Alt program instalează pachete acum.')
	try:
		ceas = P._ceas_scurt(linii)
	except Exception:
		ceas = None
	if ceas:
		return ceas
	# solver-ul opkg: un pachet pus din alt feed, cu numele unui pachet al imaginii si versiunea mai mare (downgrade_straine)
	if 'allow downgrade of' in t:
		return _t('Un pachet pus din alt feed are numele unui pachet al imaginii și o versiune mai mare.')
	if 'unknown package' in t or 'cannot find package' in t or 'no candidates to install' in t:
		return _t('Un pachet nu se mai află pe server.')
	if 'incompatible with the architectures' in t or 'not compatible with' in t:
		return _t('Un pachet nu este făcut pentru acest receptor.')
	if 'mismatch' in t:
		return _t('Un fișier descărcat nu se potrivește cu suma din lista serverului.')
	if 'failed to download' in t or 'wget returned' in t:
		return _t('Un fișier nu s-a putut descărca de pe server.')
	# opkg 0.8.0 (check_data_file_clashes): "But that file is already provided by package Y", "But that path is a
	# symlink", "But that path is currently a directory"
	if 'clash' in t or 'file conflicts' in t or 'already provided by package' in t or 'but that path is' in t:
		return _t('Un pachet ar scrie peste fișierele altui pachet.')
	if 'malformed' in t or 'error unpacking' in t or 'not a valid' in t or 'failed to extract' in t:
		return _t('Un fișier descărcat nu se poate citi.')
	return implicit


def text_eroare_instalare(motiv):
	"""Mesajul unei instalari cazute, cu motivul si jurnalul. Motivul se termina cu punct, iar textul pune unul dupa el:
	al motivului se scoate (inainte iesea "...nu a reușit.. Jurnalul")."""
	return _t('Instalarea s-a oprit cu eroare: %s. Jurnalul: %s') % (curata(motiv).rstrip(' .'), JURNAL)


def motiv_imagine_noua(nume):
	for motiv, tipar in TIPARE_IMAGINE_NOUA:
		if tipar.match(nume or ''):
			return motiv
	return None


def versiune_scurta(versiune):
	"""0.3.2+git0+20d834b510-r0 -> 0.3.2 (20d834b510); 0.1.0-r0.hds2 -> 0.1.0-r0.hds2"""
	v = (versiune or '').split(':', 1)[-1]
	m = re.match(r'^([0-9.]+)\+git[0-9]*\+([0-9a-f]{7,40})(?:-.*)?\Z', v)
	if m:
		return '%s (%s)' % (m.group(1), m.group(2)[:10])
	return v


def versiunea_starii(stare):
	"""Versiunea vazuta de om dintr-un stare.json: campul "versiune" (0.3.2); la un stare.json fara el, baza (fara
	actualizari) sau baza.N, cum se numeau inainte de versiunile simple"""
	v = stare.get('versiune')
	if isinstance(v, str) and _VERSIUNE.match(v):
		return v
	n = stare.get('actualizare') or 0
	baza = u'%s' % (stare.get('baza') or '')
	return baza if not n else '%s.%d' % (baza, n)


def versiunea_receptorului(stare, arhitecturi):
	"""Versiunea din stare.json pentru receptorul cu `arhitecturi` (arch.conf): a pachetului imaginii (enigma2-hdsatelit)
	facut pentru arhitectura lui, cand e mai veche decat versiunea feedului. Feedul e comun mai multor modele, iar un model
	lasat pe dinafara unei versiuni (24.11.2026: ZGEMMA H8.2H Plus si SE raman pe 0.7.8 pana la 0.8.0, celelalte au 0.7.9)
	are acolo tot pachetul vechi. Fara arhitecturi sau fara pachetul lor: versiunea_starii, ca inainte."""
	v = versiunea_starii(stare)
	arh = set(arhitecturi or ())
	if not arh or not isinstance(stare, dict):
		return v
	ale_lui = [versiune_din_pachet(p.get('versiune')) for p in stare.get('pachete') or []
		if isinstance(p, dict) and p.get('nume') == PACHET_PRINCIPAL and p.get('arhitectura') in arh]
	ale_lui = [x for x in ale_lui if x and _VERSIUNE.match(x)]
	if not ale_lui:
		return v
	cea_veche = sorted(ale_lui, key=cmp_to_key(P.compara_versiuni))[0]
	return cea_veche if P.compara_versiuni(cea_veche, v) < 0 else v


def imagine_noua_pentru(stare, arhitecturi):
	"""VAN0 (0.8.0): stare.json cere imaginea noua (imagine_noua) si pentru acest receptor. Un model lasat pe dinafara
	unei versiuni (versiunea_receptorului mai veche decat a feedului: pachetul imaginii pentru arhitectura lui a ramas
	cel vechi) nu are imagine noua de pus: nici anuntul zilnic, nici verdictul IMAGINE_NOUA. Fara arhitecturi sau fara
	pachetul lor in stare.json: ca inainte (imagine_noua asa cum e)."""
	if not isinstance(stare, dict) or not stare.get('imagine_noua'):
		return False
	return P.compara_versiuni(versiunea_receptorului(stare, arhitecturi), versiunea_starii(stare)) >= 0


# ---------------------------------------------------------------- receptorul

def _cale(radacina, cale):
	return P._cale(radacina, cale)


def baza_receptorului(radacina='/'):
	"""Imaginea scrisa pe receptor (version= din /etc/hdsatelit-model), '' daca nu se stie"""
	try:
		with open(_cale(radacina, FISIER_MODEL), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f:
				if rand.startswith('version='):
					v = rand.split('=', 1)[1].strip()
					return v if _BAZA.match(v) else ''
	except (IOError, OSError):
		pass
	return ''


def instalate(radacina='/', conf=None):
	"""{nume: versiune} ale pachetelor instalate (status-ul opkg)"""
	conf = conf or P.citeste_configurarea(radacina)
	rez = {}
	for s in P.citeste_strofe(_cale(radacina, conf.status_file)):
		n = s.get('package', '')
		st = s.get('status', '').split()
		if n and 'installed' in st and 'not-installed' not in st:
			rez[n] = s.get('version', '')
	return rez


def _furnizari(text):
	"""Campul Provides al unei strofe: [(nume, versiune)], versiunea '' cand nu e data ("Provides: libdvdread" fata de
	"Provides: foo (= 1.2)")"""
	rez = []
	for parte in (text or '').split(','):
		m = re.match(r'^\s*([A-Za-z0-9+.\-]+)\s*(?:\(\s*=\s*([^)\s]+)\s*\))?\s*$', parte)
		if m:
			rez.append((m.group(1), m.group(2) or ''))
	return rez


def furnizate(radacina='/', conf=None):
	"""{nume: [(versiune, pachet)]}: numele date prin Provides de pachetele instalate (status-ul opkg), de pilda
	libdvdread (dat de libdvdread8) sau showiframe (dat de programul producatorului placii); versiunea '' cand Provides
	nu o spune. opkg le socoteste instalate la dependinte, deci si cautarea."""
	conf = conf or P.citeste_configurarea(radacina)
	rez = {}
	for s in P.citeste_strofe(_cale(radacina, conf.status_file)):
		n = s.get('package', '')
		st = s.get('status', '').split()
		if n and 'installed' in st and 'not-installed' not in st:
			for virtual, v in _furnizari(s.get('provides')):
				rez.setdefault(virtual, []).append((v, n))
	return rez


def versiune_din_pachet(versiune):
	"""Versiunea vazuta de om din versiunea pachetului: 0.3.2+git0+ab-r0 -> 0.3.2 (0.3.0+git0+.. -> 0.3.0, imaginea
	fara actualizari); None cand pachetul nu e facut din git (nu se stie)"""
	v = (versiune or '').split(':', 1)[-1]
	m = re.match(r'^([0-9]{1,3}(?:\.[0-9]{1,3}){2,3})\+git', v)
	return m.group(1) if m else None


def imaginea(radacina='/', conf=None):
	"""{'baza' (imaginea de pe stick), 'versiune' (vazuta de om, None daca nu se stie), 'pachet' (enigma2-hdsatelit),
	'arhitecturi' (arch.conf, pentru versiunea_receptorului; aceeasi configurare pe care o citea si instalate)}"""
	conf = conf or P.citeste_configurarea(radacina)
	baza = baza_receptorului(radacina)
	v = instalate(radacina, conf).get(PACHET_PRINCIPAL, '')
	return {'baza': baza, 'versiune': versiune_din_pachet(v), 'pachet': v,
		'arhitecturi': list(getattr(conf, 'arhitecturi', None) or [])}


def baza_pentru_despre(radacina='/'):
	"""Imaginea de baza, pentru randul "Imaginea de bază" din "Despre imagine": numai cand difera de versiunea care
	ruleaza (s-au instalat actualizari prin pachete; versiunea o arata randul "Versiune HD Satelit"); '' altfel"""
	i = imaginea(radacina)
	if not i['baza'] or not i['versiune'] or i['versiune'] == i['baza']:
		return ''
	return i['baza']


def fara_retea(radacina='/'):
	"""True cand receptorul nu are nicio ruta implicita (IPv4 sau IPv6): fara retea sau fara router"""
	try:
		with open(_cale(radacina, '/proc/net/route'), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f.readlines()[1:]:
				c = rand.split()
				if len(c) > 3 and c[1] == '00000000' and int(c[3], 16) & 2:
					return False
	except (IOError, OSError, ValueError):
		pass
	try:
		with open(_cale(radacina, '/proc/net/ipv6_route'), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f:
				c = rand.split()
				if len(c) > 9 and c[0] == '0' * 32 and c[1] == '00' and c[9] != 'lo' and int(c[8], 16) & 2:
					return False
	except (IOError, OSError, ValueError):
		pass
	return True


def opkg_ocupat(radacina='/'):
	"""True cand ruleaza alt opkg (are lacatul lui, lockf pe unul din LACATE_OPKG); fara fisier, nimic nu ruleaza"""
	tinute = lacate_tinute(_cale(radacina, '/proc/locks'))
	return any(_lacat_tinut(_cale(radacina, cale), tinute) for cale in LACATE_OPKG)


def lacate_tinute(cale='/proc/locks'):
	"""{(major, minor, inode)} ale fisierelor cu un lacat POSIX/OFD/flock tinut acum (/proc/locks), sau None cand nu se
	poate citi"""
	try:
		with open(cale, 'r', encoding='ascii', errors='replace') as f:
			text = f.read(1 << 16)
	except (IOError, OSError):
		return None
	rez = set()
	for rand in text.splitlines():
		p = rand.replace('->', ' ').split()
		if len(p) >= 6 and p[1] in ('POSIX', 'OFDLCK', 'FLOCK'):
			d = p[5].split(':')
			try:
				rez.add((int(d[0], 16), int(d[1], 16), int(d[2])))
			except (ValueError, IndexError):
				pass
	return rez


def _lacat_tinut(cale, tinute=None):
	"""Cu /proc/locks citit (tinute), fara sa ia lacatul: o proba cu lockf il ia o clipa, iar un opkg pornit chiar
	atunci ar cadea cu "Could not lock" (si fisierul ramas dupa un opkg oprit cu SIGKILL ar fi luat la fiecare
	intrebare). Numai fara /proc/locks (probele de pe PC), cu lockf."""
	if not os.path.exists(cale):
		return False
	if tinute is not None and hasattr(os, 'major'):
		try:
			st = os.stat(cale)
		except OSError:
			return False
		return (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino) in tinute
	try:
		import fcntl
		fd = os.open(cale, os.O_RDWR)
	except (ImportError, OSError):
		return False
	try:
		try:
			fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
		except (IOError, OSError):
			return True
		fcntl.lockf(fd, fcntl.LOCK_UN)
		return False
	finally:
		os.close(fd)


def instalare_in_curs(radacina='/'):
	"""True cat se instaleaza o actualizare de aici sau cat ruleaza un opkg (orice instalare, si a Extensiilor): atunci
	iesirea enigma2 ar opri opkg la jumatate (Screens/Standby.py TryQuitMainloop, mytest.py la ecranele protejate)"""
	try:
		if actualizari.faza == 'instalez':
			return True
	except NameError:
		pass
	return opkg_ocupat(radacina)


def scrie_semnul_in_curs(versiune, planificate, radacina='/'):
	"""SEMN_IN_CURS inainte de opkg: versiunea si {pachet: versiunea noua} ale planului, atomic si cu fsync (trebuie sa
	ramana si dupa o repornire dura). False cand nu se poate scrie (instalarea merge oricum, ca inainte)."""
	cale = _cale(radacina, SEMN_IN_CURS)
	d = {'versiune': u'%s' % (versiune or ''), 'ora': int(time.time()),
		'pachete': dict((p['nume'], p['la']) for p in planificate if P.nume_valid(p.get('nume', '')) and p.get('la'))}
	try:
		with open(cale + '.nou', 'w', encoding='utf-8') as f:
			json.dump(d, f, sort_keys=True)
			f.flush()
			os.fsync(f.fileno())
		os.replace(cale + '.nou', cale)
		return True
	except (IOError, OSError, TypeError, ValueError) as e:
		print('[HdsActualizari] semnul instalarii: %s' % e)
		return False


def sterge_semnul_in_curs(radacina='/'):
	try:
		os.remove(_cale(radacina, SEMN_IN_CURS))
	except OSError:
		pass


def oprit_de_semnal(cod):
	"""opkg nu a iesit singur: l-a oprit un semnal trimis din afara. lib/base/console.cpp da atunci 128 + semnalul (137
	la SIGKILL, 143 la SIGTERM, 139 la o cadere); 255 e iesirea obisnuita a lui opkg cu eroare, iar -1 inseamna ca opkg nu a
	pornit sau l-a oprit chiar enigma2 (Ipkg.stop, nefolosit aici), deci nu sunt semnale."""
	return isinstance(cod, int) and not isinstance(cod, bool) and 128 < cod <= 128 + 64


def rezultat_pornire(radacina='/'):
	"""Rezultatul lui tools/hds-actualizare-intrerupta.py de la pornirea aceasta ({stare, versiune, ramase, detaliu}),
	citit o singura data (fisierul se sterge), sau None"""
	cale = _cale(radacina, REZULTAT_PORNIRE)
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as f:
			text = f.read(4096)
	except (IOError, OSError):
		return None
	try:
		os.remove(cale)
	except OSError:
		pass
	d = {}
	for rand in text.splitlines():
		k, semn, v = rand.partition('=')
		if semn:
			d[k.strip()] = curata(v.strip())
	return d if d.get('stare') in TEXTE_PORNIRE else None


def text_rezultat_pornire(rez):
	if rez['stare'].startswith('pornire-'):
		return _t(TEXTE_PORNIRE[rez['stare']]) % (rez.get('straine') or '?')
	return _t(TEXTE_PORNIRE[rez['stare']]) % (rez.get('versiune') or '?')


# ---------------------------------------------------------------- sursele si parola

def citeste_netrc(radacina='/'):
	"""(nume, parola) pentru stb.hdsatelit.com din /home/root/.netrc sau /.netrc; None daca lipseste.
	Python-ul imaginii nu are netrc.py: jetoanele se citesc de mana (machine, login, password, default)."""
	for cale in NETRC:
		try:
			with open(_cale(radacina, cale), 'r', encoding='utf-8', errors='replace') as f:
				jetoane = f.read().split()
		except (IOError, OSError):
			continue
		intrari = []
		i = 0
		while i < len(jetoane):
			j = jetoane[i]
			if j == 'default':
				intrari.append({'gazda': '*'})
				i += 1
			elif j in ('machine', 'login', 'password', 'account') and i + 1 < len(jetoane):
				if j == 'machine':
					intrari.append({'gazda': jetoane[i + 1]})
				elif intrari:
					intrari[-1][j] = jetoane[i + 1]
				i += 2
			else:
				i += 1
		for x in intrari:
			if x.get('gazda') == GAZDA_FEED and x.get('login') and x.get('password'):
				return x['login'], x['password']
	return None


def surse_feed(radacina='/', conf=None):
	"""{'proba': [(nume, adresa, arh)], 'public': [...]}: sursele opkg ale feedului HD Satelit, pe canale, numai cu
	adrese de forma https://stb.hdsatelit.com/feed/<canal>/<baza>/<arh>"""
	conf = conf or P.citeste_configurarea(radacina)
	rez = {'proba': [], 'public': []}
	for nume, adresa in conf.surse:
		m = _ADRESA_FEED.match(adresa or '')
		if m:
			rez[m.group(1)].append((nume, adresa, m.group(3), m.group(2)))
	return rez


def canalul(radacina='/', conf=None):
	"""(canal, surse, baza_feedului): canalul de proba cand are surse si parola, altfel cel public, altfel (None, [], '')"""
	s = surse_feed(radacina, conf)
	if s['proba']:
		if citeste_netrc(radacina) is None:
			return 'proba-fara-cheie', s['proba'], s['proba'][0][3]
		return 'proba', s['proba'], s['proba'][0][3]
	if s['public']:
		return 'public', s['public'], s['public'][0][3]
	return None, [], ''


def adresa_stare(canal, baza):
	return '%s/%s/%s/stare.json' % (ADRESA_FEED, canal, baza)


# ---------------------------------------------------------------- feedul unic (0.7.9, UNF9)

def linia(baza):
	"""x.y al unei baze x.y.z, '' cand nu e o baza"""
	baza = u'%s' % (baza or '')
	return baza.rsplit('.', 1)[0] if _BAZA.match(baza) else ''


def baza_feed_potrivita(baza_feed, baza_scrisa):
	"""Inainte de stare.json: feedul din adrese poate fi al receptorului (baza scrisa) sau un feed unic de pe aceeasi linie
	x.y (atunci stare.json hotaraste, motiv_baza)"""
	if not _BAZA.match(u'%s' % (baza_feed or '')) or not _BAZA.match(u'%s' % (baza_scrisa or '')):
		return False
	return baza_feed == baza_scrisa or linia(baza_feed) == linia(baza_scrisa)


def motiv_baza(stare, baza_feed, baza_scrisa):
	"""'' cand stare.json semnat al feedului din adrese se potriveste cu imaginea scrisa; altfel 'baza' (alta imagine,
	sau feedul altei baze fara "unic") sau 'imagine-minima' (feedul cere o imagine scrisa mai noua)"""
	bf = baza_feed or baza_scrisa
	if not baza_scrisa or stare.get('baza') != bf or (bf != baza_scrisa and stare.get(CHEIE_UNIC) is not True):
		return 'baza'
	if P.compara_versiuni(stare.get('imagine_minima') or baza_scrisa, baza_scrisa) > 0:
		return 'imagine-minima'
	return ''


def intoarce_baze(stare):
	"""Bazele scrise din "intoarce_baze" ale unui feed unic (numai cele x.y.z); [] altfel"""
	x = (stare or {}).get(CHEIE_INTOARCE) if (stare or {}).get(CHEIE_UNIC) is True else None
	return [b for b in x if isinstance(b, str) and _BAZA.match(b)] if isinstance(x, list) else []


def feed_unic_potrivit(unica, baza_unica, canal, baza_scrisa, arhitecturi):
	"""'' cand receptorul poate trece pe feedul unic `baza_unica` (stare.json lui semnat, `unica`); altfel motivul, pentru
	jurnal"""
	if unica.get('baza') != baza_unica:
		return 'stare.json are baza %s, nu %s' % (curata(unica.get('baza')), baza_unica)
	if unica.get(CHEIE_UNIC) is not True:
		return 'feedul %s nu e unic' % baza_unica
	if unica.get('canal') and unica.get('canal') != canal:
		return 'stare.json e al canalului %s, nu %s' % (curata(unica.get('canal')), canal)
	if not baza_scrisa:
		return 'baza scrisa nu se stie'
	if baza_scrisa in intoarce_baze(unica):
		return 'baza %s e in %s' % (baza_scrisa, CHEIE_INTOARCE)
	if P.compara_versiuni(unica.get('imagine_minima') or baza_unica, baza_scrisa) > 0:
		return 'cere imaginea %s, receptorul are %s' % (curata(unica.get('imagine_minima')), baza_scrisa)
	indexuri = unica.get('indexuri')
	lipsa = sorted(set(arhitecturi) - set(indexuri if isinstance(indexuri, dict) else ()))
	if not arhitecturi or lipsa:
		return 'feedul unic nu are arhitecturile %s' % (', '.join(lipsa) or '?')
	return ''


def rescrie_baza_feedului(radacina, de_la, la):
	"""In CONF_PUBLIC si CONF_PROBA, randurile src ale feedului HD Satelit cu baza `de_la` in adresa trec pe `la`, atomic
	(fisier .nou, fsync, rename); celelalte randuri raman cum sunt. Numarul randurilor schimbate."""
	if not _BAZA.match(u'%s' % de_la) or not _BAZA.match(u'%s' % la) or de_la == la:
		return 0
	schimbate = 0
	for conf in (CONF_PUBLIC, CONF_PROBA):
		cale = _cale(radacina, conf)
		try:
			with open(cale, 'r', encoding='utf-8', errors='surrogateescape', newline='') as f:
				randuri = f.read().splitlines(True)
		except (IOError, OSError):
			continue
		noi, aici = [], 0
		for rand in randuri:
			p = rand.split()
			m = _ADRESA_FEED.match(p[2]) if len(p) >= 3 and p[0] in ('src', 'src/gz') else None
			if m and m.group(2) == de_la:
				adresa = '%s/%s/%s/%s' % (ADRESA_FEED, m.group(1), la, m.group(3))
				rand = rand.replace(p[2], adresa, 1)
				aici += 1
			noi.append(rand)
		if not aici:
			continue
		try:
			with open(cale + '.nou', 'w', encoding='utf-8', errors='surrogateescape', newline='') as f:
				f.write(''.join(noi))
				f.flush()
				os.fsync(f.fileno())
			try:
				os.chmod(cale + '.nou', os.stat(cale).st_mode & 0o7777)
			except OSError:
				pass
			os.replace(cale + '.nou', cale)
			schimbate += aici
		except (IOError, OSError) as e:
			print('[HdsActualizari] sursele %s: %s' % (conf, e))
	return schimbate


def stare_cu_feedul_unic(radacina, canal, baza_feed, credentiale=None, muta=True, deschide=None):
	"""stare.json al feedului din adrese, cu trecerea pe feedul unic sau intoarcerea de pe el (capul fisierului). Pe un fir
	separat (cereri de retea). (stare, cod, baza_feedului_dupa, nota): cod ca la descarca_stare; nota ('' cand nu s-a
	intamplat nimic) e pentru jurnal. muta=False (alt opkg lucreaza): numai citirea."""
	stare, cod = descarca_stare(adresa_stare(canal, baza_feed), credentiale, deschide=deschide)
	if cod or not muta or canal not in ('proba', 'public'):
		return stare, cod, baza_feed, ''
	baza_scrisa = baza_receptorului(radacina)
	if not baza_scrisa:
		return stare, cod, baza_feed, ''
	if stare.get(CHEIE_UNIC) is True and P.compara_versiuni(baza_scrisa, baza_feed) < 0 and \
			baza_scrisa in intoarce_baze(stare):
		if not rescrie_baza_feedului(radacina, baza_feed, baza_scrisa):
			return stare, cod, baza_feed, 'intoarcerea pe baza %s: sursele nu s-au putut rescrie' % baza_scrisa
		veche, cod_v = descarca_stare(adresa_stare(canal, baza_scrisa), credentiale, deschide=deschide)
		return veche, cod_v, baza_scrisa, 'intors de pe feedul unic %s pe feedul bazei %s' % (baza_feed, baza_scrisa)
	tinta = u'%s' % (stare.get(CHEIE_FEED_UNIC) or '')
	if not _BAZA.match(tinta) or tinta == baza_feed or (baza_feed != baza_scrisa and stare.get(CHEIE_UNIC) is not True):
		return stare, cod, baza_feed, ''
	arhitecturi = set(s[2] for s in surse_feed(radacina)[canal])
	unica, cod_u = descarca_stare(adresa_stare(canal, tinta), credentiale, deschide=deschide)
	motiv = curata(unica.get('eroare') or cod_u) if cod_u else \
		feed_unic_potrivit(unica, tinta, canal, baza_scrisa, arhitecturi)
	if not motiv:
		if rescrie_baza_feedului(radacina, baza_feed, tinta):
			return unica, None, tinta, 'trecut de pe feedul bazei %s pe feedul unic %s' % (baza_feed, tinta)
		# trecut chiar acum de alta lucrare (verificarea zilnica si cautarea deodata): sursele sunt deja pe feedul unic
		if [s[3] for s in surse_feed(radacina)[canal]][:1] == [tinta]:
			return unica, None, tinta, 'sursele erau deja pe feedul unic %s' % tinta
		motiv = 'sursele nu s-au putut rescrie'
	return stare, cod, baza_feed, 'ramane pe feedul bazei %s (feedul unic %s: %s)' % (baza_feed, tinta, motiv)


# ---------------------------------------------------------------- stare.json

def valideaza_stare(d):
	"""Lista greselilor (goala = bun); aceleasi reguli ca oe-build/feed_actualizare.verifica_stare"""
	g = []
	if not isinstance(d, dict):
		return ['nu e obiect JSON']
	if d.get('format') != FORMAT:
		g.append('format')
	if not _BAZA.match(u'%s' % d.get('baza', '')):
		g.append('baza')
	n = d.get('actualizare')
	if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > 999:
		g.append('actualizare')
	if not _BAZA.match(u'%s' % d.get('imagine_minima', '')):
		g.append('imagine_minima')
	if not isinstance(d.get('imagine_noua'), bool):
		g.append('imagine_noua')
	if 'versiune' in d and not _VERSIUNE.match(u'%s' % d.get('versiune')):
		g.append('versiune')
	if not isinstance(d.get('motive'), list) or not all(isinstance(m, str) for m in d.get('motive') or []):
		g.append('motive')
	ce = d.get('ce_e_nou')
	if not isinstance(ce, list) or len(ce) > 40 or not all(isinstance(x, str) and len(x) <= 300 for x in ce):
		g.append('ce_e_nou')
	if 'canal' in d and d.get('canal') not in ('proba', 'public'):
		g.append('canal')
	indexuri = d.get('indexuri')
	if 'indexuri' in d and (not isinstance(indexuri, dict) or not all(isinstance(a, str) and _ARH.match(a) and
			isinstance(x, dict) and _SHA256.match(u'%s' % x.get('sha256', '')) and isinstance(x.get('marime'), int)
			for a, x in indexuri.items())):
		g.append('indexuri')
	pachete = d.get('pachete')
	if not isinstance(pachete, list):
		g.append('pachete')
	else:
		for p in pachete:
			if not isinstance(p, dict) or not P.nume_valid(p.get('nume')) or not isinstance(p.get('versiune'), str):
				g.append('pachete')
				break
	# 0.7.7 (DRV): optionala; o intrare rea nu strica actualizarea, se lasa deoparte (drivere_din_stare)
	if CHEIE_DRIVERE in d and not isinstance(d.get(CHEIE_DRIVERE), list):
		g.append(CHEIE_DRIVERE)
	return g


# ---------------------------------------------------------------- driverul placii (0.7.7, DRV)

def drivere_din_stare(stare):
	"""Intrarile bune din stare.json „drivere_placii” (vezi CHEIE_DRIVERE): pachet de drivere (TIPARE_IMAGINE_NOUA),
	versiune, arhitectura, fisier, marime, sha256, de_la (lista versiunilor vechi), nucleu; optional hifb_vechi (md5)."""
	rez = []
	for e in (stare or {}).get(CHEIE_DRIVERE) or []:
		if not isinstance(e, dict) or not P.nume_valid(e.get('nume')) or motiv_imagine_noua(e.get('nume')) != 'drivere':
			continue
		de_la, marime = e.get('de_la'), e.get('marime')
		if not isinstance(e.get('versiune'), str) or not isinstance(e.get('arhitectura'), str) or \
				not _ARH.match(e['arhitectura']) or not isinstance(e.get('fisier'), str) or \
				not _FISIER_IPK.match(e['fisier']) or not isinstance(marime, int) or isinstance(marime, bool) or marime <= 0 or \
				not isinstance(e.get('sha256'), str) or not _SHA256.match(e['sha256']) or not isinstance(de_la, list) or \
				not de_la or not all(isinstance(v, str) for v in de_la) or not isinstance(e.get('nucleu'), str) or \
				not e['nucleu']:
			continue
		rez.append(e)
	return rez


def nucleul_care_ruleaza():
	"""uname -r (de pilda 4.4.35); '' cand nu se stie"""
	try:
		return os.uname()[2]
	except (AttributeError, OSError, IndexError):
		return ''


def _md5_fisier(cale):
	h = hashlib.md5()
	try:
		with open(cale, 'rb') as f:
			for bucata in iter(lambda: f.read(1 << 16), b''):
				h.update(bucata)
	except (IOError, OSError):
		return None
	return h.hexdigest()


def planul_driverelor(stare, inst, arhitecturi=None, radacina='/', nucleu=None):
	"""Intrarile de plan (ca planul()) pentru driverele placii din stare.json care se potrivesc receptorului: arhitectura
	lui (arch.conf), pachetul instalat chiar in una din versiunile de_la, versiunea noua mai mare, nucleul care ruleaza
	cel cerut si, cu hifb_vechi, hi_fb.ko de pe disc chiar cel vechi. Marcate driver_placii (verdict nu le refuza)."""
	nucleu = nucleul_care_ruleaza() if nucleu is None else nucleu
	rez = []
	for e in drivere_din_stare(stare):
		n = e['nume']
		if arhitecturi and e['arhitectura'] not in arhitecturi:
			continue
		if n not in inst or inst[n] not in e['de_la'] or P.compara_versiuni(e['versiune'], inst[n]) <= 0:
			continue
		if not nucleu or nucleu != e['nucleu']:
			continue
		if e.get('hifb_vechi'):
			md5 = _md5_fisier(_cale(radacina, '/lib/modules/%s/extra/hi_fb.ko' % nucleu))
			if md5 != e['hifb_vechi']:
				continue
		rez.append({'nume': n, 'titlu': _t(TITLU_DRIVER), 'de_la': inst[n], 'la': e['versiune'], 'marime': e['marime'], 'depends': '',
			'arhitectura': e['arhitectura'], 'driver_placii': True})
	return rez


def driver_din_stare(stare, nume, arhitectura):
	"""Intrarea driverului placii (drivere_din_stare) cu numele si arhitectura date, sau None"""
	gasite = [e for e in drivere_din_stare(stare) if e['nume'] == nume and e['arhitectura'] == arhitectura]
	return gasite[0] if len(gasite) == 1 else None


def _boot_id(radacina='/'):
	try:
		with open(_cale(radacina, BOOT_ID)) as f:
			return f.read().strip()
	except (IOError, OSError):
		return ''


def scrie_semnul_driverului(nume, radacina='/'):
	"""Dupa instalarea unui driver al placii: semnul cu boot_id-ul de acum (receptorul trebuie repornit)"""
	try:
		cale = _cale(radacina, SEMN_DRIVER_NOU)
		with open(cale + '.tmp', 'w') as f:
			json.dump({'boot_id': _boot_id(radacina), 'pachete': list(nume), 'ora': int(time.time())}, f)
		os.rename(cale + '.tmp', cale)
		return True
	except (IOError, OSError, ValueError):
		return False


def repornire_receptor_ceruta(radacina='/'):
	"""True cat un driver al placii instalat la pornirea de acum asteapta repornirea receptorului (SEMN_DRIVER_NOU cu
	acelasi boot_id). La alta pornire driverul nou e deja incarcat: semnul se sterge."""
	cale = _cale(radacina, SEMN_DRIVER_NOU)
	try:
		with open(cale) as f:
			semn = json.load(f)
	except (IOError, OSError, ValueError):
		return False
	acum = _boot_id(radacina)
	if isinstance(semn, dict) and acum and semn.get('boot_id') == acum:
		return True
	try:
		os.remove(cale)
	except OSError:
		pass
	return False


def numar_instalare(radacina='/'):
	"""Numarul aleator al instalarii (FISIER_INSTALARE, 32 de cifre hexa), facut la prima cerere cu os.urandom si tinut
	acolo (in afara /etc/enigma2, deci nu intra in copia setarilor); '' cand nu se poate citi sau scrie"""
	cale = _cale(radacina, FISIER_INSTALARE)
	try:
		with open(cale, 'r', encoding='ascii', errors='replace') as f:
			v = f.read(64).strip()
		if re.match(r'^[0-9a-f]{32}\Z', v):
			return v
	except (IOError, OSError):
		pass
	v = ''.join('%02x' % b for b in bytearray(os.urandom(16)))
	try:
		with open(cale + '.nou', 'w', encoding='ascii') as f:
			f.write(v + '\n')
			f.flush()
			os.fsync(f.fileno())
		os.replace(cale + '.nou', cale)
		# numarul trimis e chiar cel din fisier
		with open(cale, 'r', encoding='ascii', errors='replace') as f:
			citit = f.read(64).strip()
	except (IOError, OSError) as e:
		print('[HdsActualizari] numarul instalarii: %s' % e)
		return ''
	return citit if re.match(r'^[0-9a-f]{32}\Z', citit) else ''


def _model_scris(radacina='/'):
	"""machinebuild= din /etc/hdsatelit-model (numai litere mici, cifre, _ si -), '' cand nu se stie"""
	try:
		with open(_cale(radacina, FISIER_MODEL), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f:
				if rand.startswith('machinebuild='):
					v = rand.split('=', 1)[1].strip()
					return v if re.match(r'^[a-z0-9][a-z0-9_\-]{0,31}\Z', v) else ''
	except (IOError, OSError):
		pass
	return ''


def _versiunea_care_ruleaza(radacina='/'):
	"""x.y.z din /etc/image-version (Components/HdsJurnalVersiuni), fara status-ul opkg; '' cand nu se stie"""
	try:
		try:
			from Components import HdsJurnalVersiuni as J
		except ImportError:
			import HdsJurnalVersiuni as J
		return J.versiune_din_build(J.build_curent(_cale(radacina, J.IMAGE_VERSION))) or ''
	except Exception:
		return ''


def antet_numarare(radacina='/'):
	"""Valoarea lui ANTET_NUMARARE: i=<numar_instalare>;v=<versiunea>;b=<baza scrisa>;m=<modelul>, necunoscutul "-";
	'' fara numarul instalarii. Se afla o data pe proces (dupa o actualizare interfata porneste din nou)."""
	if radacina in _NUMARARE:
		return _NUMARARE[radacina]
	with _LACAT_NUMARARE:
		if radacina not in _NUMARARE:
			numar = numar_instalare(radacina)
			_NUMARARE[radacina] = '' if not numar else 'i=%s;v=%s;b=%s;m=%s' % (numar,
				_versiunea_care_ruleaza(radacina) or '-', baza_receptorului(radacina) or '-', _model_scris(radacina) or '-')
	return _NUMARARE[radacina]


def _cere(adresa, credentiale=None, timp=TIMP_STARE, deschide=None, maxim=MARIME_STARE_MAX, accept='application/json',
		antete_in_plus=None):
	"""(corp, None) sau (None, (cod, eroare)) pentru o cerere GET de cel mult `maxim` octeti; cod: FARA_CHEIE (401,
	403), FARA_RASPUNS (retea, 5xx) sau EROARE"""
	antete = {'User-Agent': UA, 'Accept': accept, 'Cache-Control': 'no-cache'}
	antete.update(antete_in_plus or {})
	if credentiale:
		antete['Authorization'] = 'Basic ' + base64.b64encode(('%s:%s' % credentiale).encode('utf-8')).decode('ascii')
	try:
		cerere = Request(adresa, headers=antete)
		r = (deschide or urlopen)(cerere, timeout=timp)
		try:
			corp = r.read(maxim + 1)
		finally:
			try:
				r.close()
			except Exception:
				pass
	except HTTPError as e:
		if e.code in (401, 403):
			return None, (FARA_CHEIE, 'HTTP %d' % e.code)
		return None, (FARA_RASPUNS if e.code >= 500 else EROARE, 'HTTP %d' % e.code)
	except (URLError, socket.timeout, socket.error, OSError, ValueError) as e:
		return None, (FARA_RASPUNS, curata(getattr(e, 'reason', e)))
	if len(corp) > maxim:
		return None, (EROARE, 'prea mare')
	return corp, None


def _semnatura():
	"""Components/HdsSemnatura (cheile de incredere si verificarea); pe PC, modulul din acelasi dosar"""
	try:
		from Components import HdsSemnatura as S
	except ImportError:
		import HdsSemnatura as S
	return S


def descarca_stare(adresa, credentiale=None, timp=TIMP_STARE, deschide=None):
	"""(stare, cod): cod None = bun: stare.json semnat de HD Satelit (stare.json.sig de langa el, verificat pe octetii
	primiti cu cheile din Components/HdsSemnatura.py) si cu forma buna; altfel FARA_RASPUNS, FARA_CHEIE, NESEMNATA sau
	EROARE (cu textul in stare['eroare']). O semnatura care nu se potriveste se cere inca o data, impreuna cu
	stare.json: publicarea se poate schimba intre cele doua cereri. `deschide` (probele) inlocuieste urlopen."""
	S = _semnatura()
	motiv = ''
	# 0.7.9 (UNF9): numaratoarea anonima, numai la cererea lui stare.json (nu la semnatura)
	try:
		semn = antet_numarare()
	except Exception as e:
		print('[HdsActualizari] numaratoarea: %r' % (e,))
		semn = ''
	in_plus = {ANTET_NUMARARE: semn} if semn else None
	for _incercare in range(2):
		corp, problema = _cere(adresa, credentiale, timp, deschide, antete_in_plus=in_plus)
		if problema:
			return {'eroare': 'stare.json prea mare' if problema[1] == 'prea mare' else problema[1]}, problema[0]
		semnatura, problema = _cere(adresa + '.sig', credentiale, timp, deschide, MARIME_SEMNATURA_MAX, 'text/plain')
		if problema and problema[1] != 'HTTP 404':
			return {'eroare': '%s: %s' % (NUME_SEMNATURA, problema[1])}, problema[0]
		bun, cod_motiv, ident = S.verifica(corp, semnatura, SCOP_STARE)
		if bun:
			break
		motiv = S.text_motiv(cod_motiv, ident)
		if cod_motiv == S.FARA_VERIFICARE:
			break
	if not bun:
		print('[HdsActualizari] stare.json refuzat: %s' % motiv)
		return {'eroare': motiv}, NESEMNATA
	try:
		d = json.loads(corp.decode('utf-8'))
	except (ValueError, UnicodeDecodeError):
		return {'eroare': 'stare.json nu e JSON'}, EROARE
	g = valideaza_stare(d)
	if g:
		return {'eroare': 'stare.json: %s' % ', '.join(g)}, EROARE
	return d, None


# ---------------------------------------------------------------- "Ce e nou" pe versiuni

def _randuri_bune(randuri):
	return isinstance(randuri, list) and len(randuri) <= MAX_RANDURI_VERSIUNE and \
		all(isinstance(t, str) and len(t) <= MAX_SEMNE_NOUTATE for t in randuri)


def versiuni_stare(stare):
	"""Campul "versiuni" din stare.json, verificat: [{versiune, data, ro, en}], de la cea mai noua versiune; None cand
	lipseste sau nu respecta regulile feedului (oe-build/feed_actualizare.verifica_stare: cel mult MAX_VERSIUNI
	versiuni, fiecare o singura data, mai noua decat baza si nu mai noua decat versiunea lui stare.json, randuri text
	cel mult MAX_RANDURI_VERSIUNE de cel mult MAX_SEMNE_NOUTATE semne). Un camp stricat nu opreste cautarea: atunci se
	arata "ce_e_nou", ca la un feed vechi."""
	brute = stare.get('versiuni') if isinstance(stare, dict) else None
	if not isinstance(brute, list) or len(brute) > MAX_VERSIUNI:
		return None
	baza = u'%s' % (stare.get('baza') or '')
	pe_server = versiunea_starii(stare)
	rez = []
	vazute = set()
	for x in brute:
		if not isinstance(x, dict):
			return None
		v = x.get('versiune')
		if not isinstance(v, str) or not _VERSIUNE.match(v) or v in vazute:
			return None
		if P.compara_versiuni(v, baza) <= 0 or P.compara_versiuni(v, pe_server) > 0:
			return None
		data = x.get('data', '')
		if not isinstance(data, str) or len(data) > MAX_DATA:
			return None
		intrare = {'versiune': v, 'data': data}
		for limba in LIMBI_NOUTATI:
			randuri = x.get(limba, [])
			if not _randuri_bune(randuri):
				return None
			intrare[limba] = [t.strip() for t in randuri if t.strip()]
		vazute.add(v)
		rez.append(intrare)
	rez.sort(key=cmp_to_key(lambda a, b: P.compara_versiuni(b['versiune'], a['versiune'])))
	return rez


def versiuni_noi(stare, instalata, pana_la=None):
	"""Versiunile din stare.json mai noi decat cea instalata (toate, cand nu se stie), pana la cea de pe server (sau
	pana la `pana_la`, versiunea_receptorului), de la cea mai noua; None cand stare.json nu are noutatile pe versiuni (sau
	le are stricate)."""
	toate = versiuni_stare(stare)
	if toate is None:
		return None
	pe_server = pana_la or versiunea_starii(stare)
	return [v for v in toate if P.compara_versiuni(v['versiune'], pe_server) <= 0 and
		(not instalata or P.compara_versiuni(v['versiune'], instalata) > 0)]


def limba_noutati():
	"""'ro' cand interfata e in romana, altfel 'en' (noutatile au textele in cele doua limbi, ca jurnalul versiunilor)"""
	try:
		from Components.Language import language
		return 'ro' if str(language.getLanguage() or '').startswith('ro') else 'en'
	except Exception:
		return 'ro'


def noutati(server, limba=None):
	"""Ce e nou, grupat pe versiuni, pentru ecran si pagina web: [(versiune, [randuri])], de la cea mai noua.
	Din server['versiuni'] (alese la cautare), in limba data (engleza, apoi romana, cand lipseste); fara ele, sau cand
	nu ramane nimic, "ce_e_nou" al versiunii de pe server (feedurile de dinainte)."""
	server = server or {}
	limba = limba or limba_noutati()
	rez = []
	for v in server.get('versiuni') or []:
		randuri = v.get(limba) or v.get('en') or v.get('ro') or []
		if randuri:
			rez.append((v.get('versiune', ''), list(randuri)))
	if not rez and server.get('ce_e_nou'):
		rez = [(server.get('versiune', ''), list(server['ce_e_nou']))]
	return rez


def text_noutati(server, limba=None):
	"""noutati() ca text: "Ce e nou în 0.3.5:", randurile cu buline, un rand gol intre versiuni"""
	return '\n\n'.join(_t('Ce e nou în %s:') % v + '\n' + '\n'.join(u'• %s' % r for r in randuri)
		for v, randuri in noutati(server, limba))


# ---------------------------------------------------------------- planul si verdictul

def _dependinte(text):
	rez = []
	for parte in (text or '').split(','):
		alternative = []
		for alt in parte.split('|'):
			m = re.match(r'^\s*([A-Za-z0-9+.\-]+)\s*(?:\(\s*(<<|<=|>=|>>|=|<|>)\s*([^)\s]+)\s*\))?\s*$', alt)
			if m:
				alternative.append((m.group(1), m.group(2) or '', m.group(3) or ''))
		if alternative:
			rez.append(alternative)
	return rez


def _satisface(versiune, operator, ceruta):
	r = P.compara_versiuni(versiune, ceruta)
	return {'<<': r < 0, '<=': r <= 0, '<': r <= 0, '=': r == 0, '>=': r >= 0, '>': r >= 0, '>>': r > 0}.get(operator, False)


def pachete_din_feed(radacina, surse, conf=None):
	"""{nume: strofa} cu cea mai noua versiune din listele surselor feedului (cele descarcate de opkg update)"""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	rez = {}
	for nume_sursa, _adresa, _arh, _b in surse:
		for s in P.citeste_strofe(os.path.join(dosar, nume_sursa)):
			n = s.get('package', '')
			if not P.nume_valid(n):
				continue
			arh = s.get('architecture', '')
			if conf.arhitecturi and arh not in conf.arhitecturi:
				continue
			vechi = rez.get(n)
			if vechi is None or P.compara_versiuni(s.get('version', ''), vechi.get('version', '')) > 0:
				rez[n] = s
	return rez


def planul(feed, inst):
	"""Pachetele instalate pentru care feedul are o versiune mai noua: [{nume, titlu, de_la, la, marime, depends,
	arhitectura}], dupa nume. Cele neinstalate (extensii numai in feed) nu intra: se pun din Extensii. Arhitectura e
	cea a strofei din listele receptorului (pachete_din_feed le ia numai pe ale arhitecturilor lui): dupa ea se alege
	intrarea din stare.json cand feedul are acelasi nume pentru doua masini (pachet_din_stare)."""
	rez = []
	for n, s in feed.items():
		if n in inst and P.compara_versiuni(s.get('version', ''), inst[n]) > 0:
			rez.append({'nume': n, 'titlu': P.nume_scurt(n) if n.startswith(P.PREFIX) else n, 'de_la': inst[n],
				'la': s.get('version', ''), 'marime': P._int(s.get('size')), 'depends': s.get('depends', ''),
				'arhitectura': s.get('architecture', '')})
	rez.sort(key=lambda x: x['nume'])
	return rez


def dependinte_lipsa(plan, inst, feed, furn=None):
	"""Dependintele planului care nu sunt nici instalate, nici in feed, sau nu au versiunea ceruta: ['nume cere ...'].
	Un nume dat prin Provides (furn = furnizate(), ale pachetelor instalate, si Provides din feed) satisface o
	dependinta fara versiune, iar una cu versiune numai cand Provides spune versiunea; Provides-ul instalat al unui
	pachet din plan nu se mai socoteste (dupa instalare ramane cel din feed)."""
	disponibile = dict(inst)
	for n, s in feed.items():
		if n not in disponibile or P.compara_versiuni(s.get('version', ''), disponibile[n]) > 0:
			disponibile[n] = s.get('version', '')
	for x in plan:
		disponibile[x['nume']] = x['la']
	in_plan = set(x['nume'] for x in plan)
	virtuale = {}
	for virtual, date in (furn or {}).items():
		for v, pachet in date:
			if pachet not in in_plan:
				virtuale.setdefault(virtual, []).append(v)
	for s in feed.values():
		for virtual, v in _furnizari(s.get('provides')):
			virtuale.setdefault(virtual, []).append(v)

	def satisfacuta(n, op, v):
		if n in disponibile and (not op or _satisface(disponibile[n], op, v)):
			return True
		return any(not op or (dat and _satisface(dat, op, v)) for dat in virtuale.get(n, ()))
	rez = []
	for x in plan:
		for alternative in _dependinte(x.get('depends')):
			if not any(satisfacuta(n, op, v) for n, op, v in alternative):
				rez.append('%s: %s' % (x['nume'], ' | '.join('%s%s' % (n, ' (%s %s)' % (op, v) if op else '')
					for n, op, v in alternative)))
	return rez


def verdict(stare, baza, plan, lipsa=(), baza_feed=None, arhitecturi=None):
	"""{'motive': [...], 'detalii': [...], 'imagine_noua': bool, 'poate_instala': bool}. baza = baza scrisa, baza_feed =
	baza din adresele feedului (implicit aceeasi; alta numai pentru un feed unic, motiv_baza); arhitecturi: ale
	receptorului (VAN0: imagine_noua numai cand e si pentru el, imagine_noua_pentru)"""
	motive = []
	detalii = []

	def adauga(m, detaliu=None):
		if m not in motive:
			motive.append(m)
		if detaliu:
			detalii.append(detaliu)
	m_baza = motiv_baza(stare, baza_feed or baza, baza)
	if m_baza == 'baza':
		adauga('baza', '%s / %s' % (stare.get('baza'), baza))
	elif m_baza:
		adauga('imagine-minima', stare.get('imagine_minima'))
	if imagine_noua_pentru(stare, arhitecturi):
		for m in stare.get('motive') or ['alt-motiv']:
			adauga(m if m in TEXT_MOTIV else 'alt-motiv')
		for d in stare.get('detalii') or []:
			detalii.append(u'%s' % d)
	for x in plan:
		m = motiv_imagine_noua(x['nume'])
		# 0.7.7 (DRV): driverul placii semnat in „drivere_placii” si potrivit receptorului (planul_driverelor)
		if m and not (m == 'drivere' and x.get('driver_placii')):
			adauga(m, x['nume'])
	if lipsa:
		adauga('biblioteci')
		detalii.extend(lipsa)
	if len(plan) > PRAG_PACHETE:
		adauga('prea-multe', '%d' % len(plan))
	ordine = [m for m, _t in MOTIVE]
	motive.sort(key=lambda m: ordine.index(m) if m in ordine else len(ordine))
	return {'motive': motive, 'detalii': detalii[:20], 'imagine_noua': bool(motive),
		'poate_instala': bool(plan) and not motive}


def stare_pachet_principal(radacina='/', conf=None):
	"""Ce spune status-ul opkg despre enigma2-hdsatelit: 'instalat', starea lui cand nu e instalat de tot (de pilda
	'install ok unpacked' dupa un opkg oprit la jumatate) sau 'lipsa'; plus marimea status-ului (octeti, -1 fara fisier).
	Pentru jurnal si pentru paza de mai jos."""
	conf = conf or P.citeste_configurarea(radacina)
	cale = _cale(radacina, conf.status_file)
	try:
		marime = os.path.getsize(cale)
	except OSError:
		marime = -1
	for s in P.citeste_strofe(cale):
		if s.get('package') == PACHET_PRINCIPAL:
			st = s.get('status', '').split()
			if 'installed' in st and 'not-installed' not in st:
				return 'instalat', marime
			return ' '.join(st) or 'fara stare', marime
	return 'lipsa', marime


def neterminate_imagine(radacina='/', conf=None):
	"""{nume: versiune} ale pachetelor imaginii (enigma2-hdsatelit, hdsatelit-*) cerute la instalare si ramase in status
	half-installed, unpacked sau half-configured; un pachet scos (deinstall, config-files) nu intra"""
	conf = conf or P.citeste_configurarea(radacina)
	rez = {}
	for s in P.citeste_strofe(_cale(radacina, conf.status_file)):
		n = s.get('package', '')
		st = s.get('status', '').split()
		if (n == PACHET_PRINCIPAL or n.startswith(PREFIX_IMAGINE)) and st[:1] == ['install'] and st[-1:] and \
				st[-1] in STARI_NETERMINATE and s.get('version'):
			rez[n] = s['version']
	return rez


def planul_reinstalarii(feed, neterminate):
	"""Intrarile de plan (ca planul()) pentru pachetele imaginii ramase la jumatate, cu versiunea din feed cand e cel putin
	cea din status; 'reinstaleaza' cand e chiar aceeasi: opkg 0.10 cu libsolv o socoteste instalata si nu face nimic
	fara --force-reinstall (JAK pe receptorul de proba, 13.11; AJU, din cale, 15.11)"""
	rez = []
	for n, v in sorted(neterminate.items()):
		s = feed.get(n)
		if s is None or P.compara_versiuni(s.get('version', ''), v) < 0:
			continue
		rez.append({'nume': n, 'titlu': P.nume_scurt(n) if n.startswith(P.PREFIX) else n, 'de_la': v,
			'la': s.get('version', ''), 'marime': P._int(s.get('size')), 'depends': s.get('depends', ''),
			'arhitectura': s.get('architecture', ''), 'reinstaleaza': P.compara_versiuni(s.get('version', ''), v) == 0})
	return rez


# ---------------------------------------------------------------- 0.7.8 (RPR8): „Repară imaginea”
# Fisierele pachetelor imaginii sterse de pe disc (de pilda un plugin al imaginii sters de mana din Plugins/Extensions: nu e
# pachet separat, vine in enigma2-hdsatelit, iar opkg il socoteste instalat si nu-l mai pune) se pun la loc prin reinstalarea
# pachetului lor din feedul semnat, cu aceeasi versiune (--force-reinstall, pe drumul reinstalarii de mai sus). Se cauta
# numai fisierele si legaturile din info/<pachet>.list care lipsesc: opkg 0.10 nu tine sume pentru fisierele obisnuite
# (numai pentru conffiles, care raman ale omului), deci un fisier schimbat, dar prezent, nu se vede. Nu intra: dosarele,
# dosarele golite la pornire sau ale omului (DOSARE_FARA_REPARATIE), conffiles, legaturile de pornire din /etc/rc*.d
# (serviciile oprite raman oprite), un .pyc cu .py langa (pachetele de proba il sterg ca sa ruleze .py-ul peticit), un
# fisier de sub o legatura spre un stick scos (partea a doua) si fisierele care lipsesc si dupa o reinstalare a aceleiasi
# versiuni (FISIER_REPARA: le sterge chiar pachetul; altfel s-ar reinstala la fiecare cautare). Pachetele nucleului, ale
# driverelor si ale bibliotecilor de baza (TIPARE_IMAGINE_NOUA) si cele care au fisiere in /boot sau ale caror scripturi
# scriu pe partitiile de pornire se sar si se spun in jurnal. Pachetele puse de om din alte surse nu sunt in feedul semnat
# cu aceeasi versiune, deci nu se ating. Inainte de opkg, fisierele din /etc ale pachetelor reinstalate si fisierele puse
# de o proba activa (DOSAR_PROBE/*/stare.json) se copiaza, iar dupa opkg se pun inapoi cum erau; .pyc-urile care lipseau
# langa .py se sterg din nou. Reparatia intra in plan la „Repară imaginea” (ecranul, pagina web, operatia
# repara-actualizarea a asistentei) si singura la orice actualizare care are deja pachete de instalat; o cautare fara
# actualizare ramane „la zi”.
FISIER_REPARA = '/etc/enigma2/hds-repara-imaginea.json'
DOSAR_OCROTITE = '/tmp/hds-repara-ocrotite'
DOSAR_PROBE = '/usr/lib/hds-proba'
# cat ruleaza opkg pentru o reparatie care reinstaleaza enigma2-hdsatelit cu aceeasi versiune: preinst-ul lui (PRB8, reteta
# enigma2-hdsatelit.bb) nu mai scoate probele, fiindca nu e o versiune noua (la o actualizare adevarata le scoate, ca pana acum)
MEDIU_REPARA = 'HDS_REPARA_IMAGINEA'
DOSARE_FARA_REPARATIE = ('/tmp/', '/var/volatile/', '/run/', '/var/run/', '/var/lock/', '/var/cache/', '/var/log/',
	'/var/tmp/', '/media/', '/mnt/', '/home/', '/proc/', '/sys/', '/dev/', '/boot/')
_RC_PORNIRE = re.compile(r'^/etc/rc[0-6S]\.d/')
_NUME_PORNIRE = re.compile(r'^(u-?boot|.*bootlogo|.*-bootargs|.*-loader|.*-fastboot|.*-partitions|.*-dtb|.*devicetree|'
	r'.*-recovery|.*-initrd)')
_SCRIPT_PORNIRE = re.compile(r'mmcblk|/dev/mtd|/dev/block/|by-partlabel|by-name|flash_erase|nandwrite|flashcp|ofgwrite|'
	r'flash-kernel|/boot/')
_PLUGIN_DIN_CALE = re.compile(r'/Plugins/[^/]+/([^/]+)/')
MAX_CAI_REPARATIE = 30
MAX_NUME_REPARATIE = 6
TITLU_REPARA = N_('Repară imaginea')
TEXT_REPARA_NOTA = N_('Pune la loc fișierele imaginii care au fost șterse. Setările tale rămân cum sunt.')
TEXT_REPARA_CAUT = N_('Verific fișierele imaginii')
TEXT_REPARA_PUN = N_('Pun la loc fișierele lipsă')
TEXT_REPARA_INTREAGA = N_('Imaginea e întreagă.')
TEXT_REPARA_PUSE = N_('Am pus la loc: %s.')
TEXT_REPARA_NEPUSE = N_('Nu am putut pune la loc: %s.')


def _sub_legatura_rupta(cale, radacina='/'):
	"""True cand un dosar de deasupra caii e o legatura spre ceva ce lipseste (stickul partii a doua, scos)"""
	oprire = os.path.abspath(radacina or '/')
	d = os.path.dirname(cale)
	while d and d != oprire and d != os.path.dirname(d):
		if os.path.islink(d) and not os.path.exists(d):
			return True
		d = os.path.dirname(d)
	return False


def _randuri_info(radacina, conf, nume, fel):
	return P._randuri(os.path.join(_cale(radacina, conf.info_dir), '%s.%s' % (nume, fel)))


def fisiere_lipsa(radacina, conf, nume, ignorate=()):
	"""Fisierele si legaturile pachetului instalat `nume` (info/<nume>.list) care lipsesc de pe disc, fara cele care nu
	intra in reparatie (vezi mai sus) si fara `ignorate`"""
	conffiles = set(r.split()[0] for r in _randuri_info(radacina, conf, nume, 'conffiles') if r.strip())
	rez = []
	for r in _randuri_info(radacina, conf, nume, 'list'):
		parti = r.split('\t')
		cale = parti[0].strip()
		mod = parti[1].strip() if len(parti) > 1 else ''
		if not cale.startswith('/') or mod.startswith('04') or cale in conffiles or cale in ignorate:
			continue
		if cale.startswith(DOSARE_FARA_REPARATIE) or _RC_PORNIRE.match(cale) or '/__pycache__/' in cale:
			continue
		disc = _cale(radacina, cale)
		if os.path.lexists(disc):
			continue
		if cale.endswith(('.pyc', '.pyo')) and os.path.lexists(disc[:-1]):
			continue
		if _sub_legatura_rupta(disc, radacina):
			continue
		rez.append(cale)
	return rez


def pachet_de_pornire(radacina, conf, nume):
	"""True cand pachetul tine de pornirea receptorului (nucleul, bootloaderul, sigla, partitiile), are fisiere in /boot
	sau un script al lui scrie pe partitiile de pornire: reparatia nu-l reinstaleaza"""
	if _NUME_PORNIRE.match(nume) or motiv_imagine_noua(nume) == 'nucleu':
		return True
	for r in _randuri_info(radacina, conf, nume, 'list'):
		if r.startswith('/boot/'):
			return True
	for fel in ('preinst', 'postinst', 'prerm', 'postrm'):
		if any(_SCRIPT_PORNIRE.search(r) for r in _randuri_info(radacina, conf, nume, fel)):
			return True
	return False


def citeste_reparatia(radacina='/'):
	"""FISIER_REPARA: {'ignorate': {nume: {'versiune', 'cai'}}, 'ultima': {'cand', 'puse', 'nepuse'}}"""
	try:
		with open(_cale(radacina, FISIER_REPARA), 'r', encoding='utf-8') as f:
			d = json.load(f)
	except (IOError, OSError, ValueError):
		d = {}
	if not isinstance(d, dict):
		d = {}
	if not isinstance(d.get('ignorate'), dict):
		d['ignorate'] = {}
	return d


def scrie_reparatia(d, radacina='/'):
	cale = _cale(radacina, FISIER_REPARA)
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		with open(cale + '.nou', 'w', encoding='utf-8') as f:
			json.dump(d, f, ensure_ascii=False, sort_keys=True)
		os.replace(cale + '.nou', cale)
	except (IOError, OSError) as e:
		print('[HdsActualizari] reparatia: %s' % e)


def reparatia(radacina, conf, feed, inst, stare, in_plan=(), toate=False, ignorate=None):
	"""Pachetele instalate cu fisiere lipsa (fisiere_lipsa) -> {'plan': intrarile de reinstalare (ca planul_reinstalarii,
	'reinstaleaza'), 'actualizare': [nume] (sunt deja in planul actualizarii, cu alta versiune: numai ea le pune la loc),
	'lipsa': {nume: [cai]}, 'sarite': [nume] (pornirea, nucleul, driverele, bibliotecile de baza), 'fara_feed': [nume]
	(feedul semnat nu le are cu aceeasi versiune)}. Se cauta in pachetele pe care feedul semnat le are cu versiunea
	instalata (si in stare.json, cu arhitectura lor) si in cele din `in_plan`; toate=True (Repară imaginea): in toate
	pachetele instalate, ca sa se spuna si ce nu se poate pune la loc."""
	if ignorate is None:
		ignorate = citeste_reparatia(radacina)['ignorate']
	rez = {'plan': [], 'actualizare': [], 'lipsa': {}, 'sarite': [], 'fara_feed': []}
	for n, v in sorted(inst.items()):
		if n in in_plan:
			lipsa = [] if motiv_imagine_noua(n) else fisiere_lipsa(radacina, conf, n)
			if lipsa:
				rez['lipsa'][n] = lipsa
				rez['actualizare'].append(n)
			continue
		s = feed.get(n)
		din_feed = s is not None and s.get('version') == v and \
			(pachet_din_stare(stare, n, s.get('architecture')) or {}).get('versiune') == v
		if not din_feed and not toate:
			continue
		ign = ignorate.get(n) if isinstance(ignorate.get(n), dict) else {}
		lipsa = fisiere_lipsa(radacina, conf, n, ign.get('cai') or () if ign.get('versiune') == v else ())
		if not lipsa:
			continue
		rez['lipsa'][n] = lipsa
		if motiv_imagine_noua(n) or pachet_de_pornire(radacina, conf, n):
			rez['sarite'].append(n)
		elif not din_feed:
			rez['fara_feed'].append(n)
		else:
			rez['plan'].append({'nume': n, 'titlu': P.nume_scurt(n) if n.startswith(P.PREFIX) else n, 'de_la': v,
				'la': v, 'marime': P._int(s.get('size')), 'depends': s.get('depends', ''),
				'arhitectura': s.get('architecture', ''), 'reinstaleaza': True})
	return rez


def nume_din_cai(cai, cu_fisierul=()):
	"""Ce vede omul din fisierele puse la loc: numele pluginului (Plugins/<fel>/<Nume>/...) sau numele fisierului, fara
	dubluri, cel mult MAX_NUME_REPARATIE si „(+N)” pentru rest; pentru pluginurile din `cu_fisierul`, numele fisierului"""
	nume = []
	for c in cai:
		m = _PLUGIN_DIN_CALE.search(c)
		n = m.group(1) if m and m.group(1) not in cu_fisierul else os.path.basename(c)
		if n and n not in nume:
			nume.append(n)
	text = ', '.join(nume[:MAX_NUME_REPARATIE])
	if len(nume) > MAX_NUME_REPARATIE:
		text += ' (+%d)' % (len(nume) - MAX_NUME_REPARATIE)
	return text


def text_reparatie(puse, nepuse=()):
	"""„Am pus la loc: PicturePlayer, MediaScanner.” (si ce nu s-a putut), tradus; '' cand nu e nimic"""
	texte = []
	if puse:
		texte.append(_t(TEXT_REPARA_PUSE) % nume_din_cai(puse))
	if nepuse:
		# un plugin pus la loc numai in parte: ce lipseste inca se spune pe fisiere
		pluginuri = set(m.group(1) for m in (_PLUGIN_DIN_CALE.search(c) for c in puse) if m)
		texte.append(_t(TEXT_REPARA_NEPUSE) % nume_din_cai(nepuse, pluginuri))
	return ' '.join(texte)


def copiaza_ocrotite(radacina, conf, pachete, dosar=None):
	"""Inainte de reinstalarea pachetelor `pachete`: copiile fisierelor lor din /etc si ale fisierelor lor puse de o proba
	activa -> {'copii': [(cale, copie)], 'pyc': [.pyc care lipseau langa .py], 'probe': [(stare.json, textul lui,
	[(tinta, nou_sha256)])] ale probelor active}"""
	dosar = dosar or _cale(radacina, DOSAR_OCROTITE)
	shutil.rmtree(dosar, ignore_errors=True)
	ale_probelor = set()
	probe = []
	for st in sorted(_glob_stari_probe(radacina)):
		try:
			with open(st, 'r', encoding='utf-8') as f:
				text = f.read()
			s = json.loads(text)
		except (IOError, OSError, ValueError):
			continue
		if isinstance(s, dict) and s.get('activa'):
			tinte = [(x['tinta'], x.get('nou_sha256') or '') for x in s.get('fisiere') or []
				if isinstance(x, dict) and x.get('tinta')]
			ale_probelor.update(c for c, _h in tinte)
			probe.append((st, text, tinte))
	rez = {'copii': [], 'pyc': [], 'probe': probe}
	for n in pachete:
		for r in _randuri_info(radacina, conf, n, 'list'):
			parti = r.split('\t')
			cale = parti[0].strip()
			if not cale.startswith('/') or (len(parti) > 1 and parti[1].strip().startswith('04')):
				continue
			disc = _cale(radacina, cale)
			if cale.endswith('.pyc') and not os.path.lexists(disc) and os.path.lexists(disc[:-1]):
				rez['pyc'].append(disc)
				continue
			if not (cale.startswith('/etc/') or cale in ale_probelor):
				continue
			if os.path.islink(disc) or not os.path.isfile(disc):
				continue
			copie = os.path.join(dosar, cale.lstrip('/'))
			try:
				os.makedirs(os.path.dirname(copie), exist_ok=True)
				shutil.copy2(disc, copie)
				rez['copii'].append((disc, copie))
			except (IOError, OSError) as e:
				print('[HdsActualizari] copia %s: %s' % (cale, e))
	return rez


def _glob_stari_probe(radacina):
	dosar = _cale(radacina, DOSAR_PROBE)
	try:
		return [os.path.join(dosar, d, 'stare.json') for d in os.listdir(dosar)
			if os.path.isfile(os.path.join(dosar, d, 'stare.json'))]
	except OSError:
		return []


def _la_fel(a, b):
	try:
		if os.path.getsize(a) != os.path.getsize(b):
			return False
		with open(a, 'rb') as fa, open(b, 'rb') as fb:
			return fa.read() == fb.read()
	except (IOError, OSError):
		return False


def pune_inapoi_ocrotite(ocrotite, radacina='/'):
	"""Dupa opkg: fisierele copiate de copiaza_ocrotite inapoi, cand opkg le-a schimbat; .pyc-urile care lipseau sterse
	din nou -> cate fisiere s-au pus inapoi"""
	puse = 0
	for disc, copie in (ocrotite or {}).get('copii') or []:
		if _la_fel(disc, copie):
			continue
		try:
			shutil.copy2(copie, disc)
			puse += 1
		except (IOError, OSError) as e:
			print('[HdsActualizari] punerea inapoi %s: %s' % (disc, e))
	for pyc in (ocrotite or {}).get('pyc') or []:
		try:
			os.unlink(pyc)
		except OSError:
			pass
	# paza unei probe inca pornite (pachetele de proba din unelte/proba_receptor, paza.py) vede, cat ruleaza opkg, toate
	# fisierele ei schimbate si isi trece starea pe "restaurat / inlocuit-de-alta-versiune", fara sa atinga fisierele;
	# cand ele sunt iar ale probei (puse inapoi mai sus), starea de dinainte se scrie la loc
	for st, text, tinte in (ocrotite or {}).get('probe') or []:
		try:
			with open(st, 'r', encoding='utf-8') as f:
				s = json.load(f)
			if s.get('activa') or s.get('motiv') != 'inlocuit-de-alta-versiune' or not tinte:
				continue
			if all(h and _sha256_simplu(_cale(radacina, c)) == h for c, h in tinte):
				with open(st + '.nou', 'w', encoding='utf-8') as f:
					f.write(text)
				os.replace(st + '.nou', st)
				print('[HdsActualizari] starea probei pusa la loc: %s' % st)
		except (IOError, OSError, ValueError, AttributeError) as e:
			print('[HdsActualizari] starea probei %s: %s' % (st, e))
	shutil.rmtree(_cale(radacina, DOSAR_OCROTITE), ignore_errors=True)
	return puse


def _sha256_simplu(cale):
	try:
		h = hashlib.sha256()
		with open(cale, 'rb') as f:
			for bucata in iter(lambda: f.read(1024 * 1024), b''):
				h.update(bucata)
		return h.hexdigest()
	except (IOError, OSError):
		return ''


def verifica_reparatia(radacina, conf, lipsa_inainte, inst):
	"""Dupa reinstalare: ce s-a pus la loc si ce lipseste inca, din pachetele reparate (lipsa_inainte = {nume: [cai]},
	cel mult MAX_CAI_REPARATIE pe pachet); tot ce lipseste inca dupa reinstalarea aceleiasi versiuni intra in FISIER_REPARA
	(nu se mai reinstaleaza pentru el), iar rezultatul in 'ultima' (pagina web il arata si dupa repornirea interfetei)
	-> (puse, nepuse)"""
	d = citeste_reparatia(radacina)
	puse, nepuse = [], []
	for n, inainte in sorted((lipsa_inainte or {}).items()):
		vechi = d['ignorate'].get(n) if isinstance(d['ignorate'].get(n), dict) else {}
		stiute = set(vechi.get('cai') or ()) if vechi.get('versiune') == inst.get(n) else set()
		acum = fisiere_lipsa(radacina, conf, n)
		multime = set(acum)
		puse.extend(c for c in inainte if c not in multime)
		nepuse.extend(c for c in acum if c not in stiute)
		if acum and inst.get(n):
			d['ignorate'][n] = {'versiune': inst[n], 'cai': sorted(multime)}
		else:
			d['ignorate'].pop(n, None)
	d['ultima'] = {'cand': int(time.time()), 'puse': puse[:MAX_CAI_REPARATIE * 4], 'nepuse': nepuse[:MAX_CAI_REPARATIE * 4]}
	scrie_reparatia(d, radacina)
	return puse, nepuse


def rezultat_din_liste(radacina, surse, stare, conf=None, repara=False):
	"""Planul si verdictul cautarii din listele surselor feedului descarcate de `opkg update` (verificate inainte fata
	de stare.json semnat), fata de pachetele instalate si de numele date prin Provides. Fara enigma2-hdsatelit instalat
	in status (un status stricat de o repornire dura chiar dupa opkg, o instalare oprita la jumatate) planul ar iesi gol
	si cautarea ar spune "la zi" pe versiunea veche (09.11.2026, darog69, Ustym): atunci cautarea e o eroare cu motivul
	spus, nu "la zi". Din 0.7.5 (JAK): pachetele imaginii ramase la jumatate in status (si enigma2-hdsatelit) intra in
	plan ca reinstalare, cand feedul semnat le are; eroarea ramane numai cand status-ul nu are pachetul principal sau
	feedul nu-l poate pune la loc. Din 0.7.8 (RPR8): pachetele cu fisiere sterse (reparatia) intra in plan ca reinstalare
	cand repara=True (Repară imaginea) sau cand planul are deja o actualizare de instalat; cu repara=True si o actualizare
	care nu se poate instala din meniu, planul are numai reparatia (aceleasi versiuni, deja instalate)."""
	conf = conf or P.citeste_configurarea(radacina)
	principal, marime = stare_pachet_principal(radacina, conf)
	feed = pachete_din_feed(radacina, surse, conf)
	reinstalare = planul_reinstalarii(feed, neterminate_imagine(radacina, conf))
	if principal != 'instalat' and PACHET_PRINCIPAL not in [x['nume'] for x in reinstalare]:
		return {'stare': EROARE, 'eroare': _t(TEXT_STATUS_STRICAT), 'status': '%s, status %d octeti' % (principal, marime)}
	inst = instalate(radacina, conf)
	# 0.7.7 (DRV): driverul placii nu e in liste (codul vechi nu trebuie sa-l vada), ci in stare.json semnat
	plan = planul(feed, inst) + reinstalare
	in_plan = set(x['nume'] for x in plan)
	plan += [x for x in planul_driverelor(stare, inst, conf.arhitecturi, radacina) if x['nume'] not in in_plan]
	plan = sorted(plan, key=lambda x: x['nume'])
	img = imaginea(radacina, conf)
	furn = furnizate(radacina, conf)
	# 0.7.9 (UNF9): baza din adresele surselor (a feedului unic, dupa trecere), pentru verdict
	bf = surse[0][3] if surse else None
	rez = rezultat_cautare(stare, img, plan, dependinte_lipsa(plan, inst, feed, furn), baza_feed=bf)
	if reinstalare:
		rez['reinstalare'] = [x['nume'] for x in reinstalare]
	try:
		rep = reparatia(radacina, conf, feed, inst, stare, set(x['nume'] for x in plan), toate=repara)
	except Exception as e:
		print('[HdsActualizari] reparatia: %s' % e)
		rep = {'plan': [], 'actualizare': [], 'lipsa': {}, 'sarite': [], 'fara_feed': [], 'eroare': curata(e)}
	actualizare = rez['stare'] == DISPONIBILA and rez['poate_instala']
	# "tot": actualizarea si reparatia in aceeasi instalare (pasul automat la orice actualizare; la Repară imaginea numai
	# cand un pachet cu fisiere lipsa are in feed alta versiune, deci numai actualizarea il pune la loc); "reparatia":
	# numai reinstalarile cu aceeasi versiune (Repară imaginea nu aduce alte pachete noi, de pilda o biblioteca tinuta
	# de om la alta versiune)
	# repara='tot' (operatia repara-actualizarea a asistentei) si o actualizare ramasa la jumatate (reinstalare): planul
	# intreg, ca inainte de RPR8, plus reparatia
	tot = repara == 'tot' or bool(rez.get('reinstalare'))
	if repara:
		mod = 'tot' if actualizare and (tot or rep['actualizare']) else ('reparatia' if rep['plan'] else None)
		if not actualizare:
			rep['fara_feed'] = rep['fara_feed'] + rep['actualizare']
			rep['actualizare'] = []
	else:
		mod = 'tot' if actualizare and (rep['plan'] or rep['actualizare']) else None
	if mod == 'tot':
		plan_tot = sorted(plan + rep['plan'], key=lambda x: x['nume'])
		nou = rezultat_cautare(stare, img, plan_tot, dependinte_lipsa(plan_tot, inst, feed, furn), baza_feed=bf)
		if rep['plan'] and not (nou['stare'] == DISPONIBILA and nou['poate_instala']):
			# reparatia nu are voie sa opreasca o actualizare care se putea instala: ramane actualizarea singura
			print('[HdsActualizari] reparatia nu intra in actualizare: %s' % ', '.join(x['nume'] for x in rep['plan']))
			nou = rez
			rep['fara_feed'] = rep['fara_feed'] + [x['nume'] for x in rep['plan']]
			rep['plan'] = []
	elif mod == 'reparatia':
		# numai reparatia: aceleasi versiuni, deja instalate, deci verdictul actualizarii (imagine noua, alta baza) nu o
		# opreste; pachetele nucleului si ale pornirii nu sunt in ea
		nou = rezultat_cautare(stare, img, rep['plan'], (), baza_feed=bf)
		nou.update(stare=DISPONIBILA, motive=[], texte_motive=[], detalii=[], repornire_receptor=False,
			poate_instala=not nou['nepotrivite'])
	if mod:
		for cheie in ('reinstalare',):
			if cheie in rez:
				nou[cheie] = rez[cheie]
		rez = nou
	if rep['lipsa'] or rep.get('eroare'):
		puse = [x['nume'] for x in rep['plan']] + (rep['actualizare'] if mod == 'tot' else []) if mod else []
		rez['reparatie'] = {'pachete': sorted(puse), 'reinstalate': [x['nume'] for x in rep['plan']] if mod else [],
			'lipsa': dict((n, c[:MAX_CAI_REPARATIE]) for n, c in rep['lipsa'].items()),
			'numar': sum(len(c) for c in rep['lipsa'].values()), 'sarite': rep['sarite'], 'fara_feed': rep['fara_feed'],
			'eroare': rep.get('eroare', '')}
	return rez


def pachet_din_stare(stare, nume, arhitectura=None):
	"""Intrarea pachetului `nume` din stare.json ("pachete"). Feedul unei baze e comun mai multor masini (V10, SF8008 si
	MINI), deci acelasi nume poate fi acolo pe doua arhitecturi: se ia numai intrarea arhitecturii date (a strofei din
	listele receptorului); fara arhitectura, numai cand numele e o singura data. O intrare fara camp "arhitectura"
	(forma veche) se ia numai cand e singura cu numele acela; una cu alta arhitectura, niciodata. None cand nu e sau nu
	se poate alege."""
	gasite = [p for p in (stare or {}).get('pachete') or [] if isinstance(p, dict) and p.get('nume') == nume]
	if arhitectura:
		ale_ei = [p for p in gasite if p.get('arhitectura') == arhitectura]
		if not ale_ei and len(gasite) == 1 and not gasite[0].get('arhitectura'):
			ale_ei = gasite
		gasite = ale_ei
	return gasite[0] if len(gasite) == 1 else None


def rezultat_cautare(stare, img, plan, lipsa, cand=None, baza_feed=None):
	"""Rezultatul unei cautari reusite, cum il arata ecranul si pagina web"""
	v = verdict(stare, img['baza'], plan, lipsa, baza_feed, img.get('arhitecturi'))
	# ZGO9 (0.8.0): versiunea pentru arhitectura receptorului; un model lasat pe dinafara nu vede numarul si noutatile
	# versiunii celorlalte
	v_rec = versiunea_receptorului(stare, img.get('arhitecturi'))
	pe_dinafara = P.compara_versiuni(v_rec, versiunea_starii(stare)) < 0
	if v['imagine_noua']:
		cod = IMAGINE_NOUA
	elif plan:
		cod = DISPONIBILA
	else:
		cod = LA_ZI
	pachete = [{'nume': x['nume'], 'titlu': x['titlu'], 'de_la': x['de_la'], 'la': x['la'], 'marime': x['marime'],
		'de_la_scurt': versiune_scurta(x['de_la']), 'la_scurt': versiune_scurta(x['la']),
		'arhitectura': x.get('arhitectura') or '', 'reinstaleaza': bool(x.get('reinstaleaza')),
		'driver_placii': bool(x.get('driver_placii'))} for x in plan]
	# planul trebuie sa fie chiar actualizarea din stare.json (numele, arhitectura si versiunea): altfel listele si
	# stare.json vin din publicari diferite; driverul placii, din „drivere_placii” (0.7.7, DRV)
	nepotrivite = [x['nume'] for x in plan
		if ((driver_din_stare(stare, x['nume'], x.get('arhitectura')) if x.get('driver_placii') else
			pachet_din_stare(stare, x['nume'], x.get('arhitectura'))) or {}).get('versiune') != x['la']]
	r = {
		'stare': cod,
		'server': {'baza': stare.get('baza'), 'actualizare': stare.get('actualizare'),
			'versiune': v_rec,
			'data': '' if pe_dinafara else stare.get('data') or '', 'ce_e_nou': [] if pe_dinafara else list(stare.get('ce_e_nou') or []),
			# alese acum, fata de versiunea instalata la cautare: dupa instalare ea e deja cea noua, iar "Ce e nou"
			# trebuie sa ramana cel vazut inainte
			'versiuni': versiuni_noi(stare, img.get('versiune'), v_rec),
			'imagine_recomandata': stare.get('imagine_recomandata') or ''},
		'pachete': pachete,
		'marime': sum(x['marime'] for x in plan),
		'motive': v['motive'],
		'texte_motive': [TEXT_MOTIV.get(m, TEXT_MOTIV['alt-motiv']) for m in v['motive']],
		'detalii': v['detalii'],
		'poate_instala': v['poate_instala'] and not nepotrivite,
		'nepotrivite': nepotrivite,
		'cautat_la': int(cand or time.time()),
		# 0.7.7 (DRV): planul schimba driverul placii, deci la sfarsit se reporneste receptorul, nu numai interfata
		'repornire_receptor': any(x.get('driver_placii') for x in plan),
	}
	return r


# ---------------------------------------------------------------- semnatura: listele si pachetele

def _sha256_fisier(cale):
	"""(sha256, marime) ale unui fisier; o lista tinuta comprimata de opkg (.gz) se socoteste dezarhivata"""
	h = hashlib.sha256()
	n = 0
	if cale.endswith('.gz'):
		import gzip
		f = gzip.open(cale, 'rb')
	else:
		f = open(cale, 'rb')
	with f:
		while True:
			bucata = f.read(1 << 16)
			if not bucata:
				break
			h.update(bucata)
			n += len(bucata)
	return h.hexdigest(), n


def _lista(dosar, nume):
	"""calea listei descarcate a unei surse (si .gz, cand opkg are compress_list_files), None cand lipseste"""
	for cale in (os.path.join(dosar, nume), os.path.join(dosar, nume + '.gz')):
		if os.path.isfile(cale):
			return cale
	return None


def verifica_listele(radacina, surse, stare, conf=None):
	"""Listele surselor feedului descarcate de `opkg update` (Packages, octet cu octet) fata de "indexuri" din stare.json
	semnat: lista greselilor (goala = bune). Un stare.json fara indexuri sau o sursa fara lista ori fara index semnat e o
	greseala: nimic nesemnat nu ajunge in plan."""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	indexuri = stare.get('indexuri') if isinstance(stare, dict) else None
	if not isinstance(indexuri, dict):
		return ['stare.json nu are indexurile semnate ale listelor']
	g = []
	for nume, _adresa, arh, _baza in surse:
		x = indexuri.get(arh)
		cale = _lista(dosar, nume)
		if not isinstance(x, dict) or cale is None:
			g.append('lista %s nu are index semnat' % arh)
			continue
		try:
			bun = _sha256_fisier(cale) == (x.get('sha256'), x.get('marime'))
		except (IOError, OSError, EOFError, ValueError):
			bun = False
		if not bun:
			g.append('lista pachetelor %s nu e cea semnata' % arh)
	return g


def sterge_listele(radacina, surse, conf=None):
	"""Sterge listele descarcate ale surselor date (si .gz): pachetele lor nu se mai vad in opkg"""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	for nume, _a, _arh, _b in surse:
		for cale in (os.path.join(dosar, nume), os.path.join(dosar, nume + '.gz')):
			try:
				os.remove(cale)
			except OSError:
				pass


def _amprente_tinute(radacina):
	"""amprentele din ultima stare.json semnata tinuta minte ({canal, baza, indexuri}), {} cand lipsesc"""
	try:
		with open(_cale(radacina, INDEXURI_SEMNATE), 'r', encoding='utf-8') as f:
			tinute = json.load(f)
	except (IOError, OSError, ValueError):
		return {}
	return tinute if isinstance(tinute, dict) else {}


def pastreaza_listele(radacina='/', conf=None):
	"""Chiar inainte de opkg update: copia listelor descarcate ale surselor feedului HD Satelit (asa cum le tine opkg, si
	.gz), in DOSAR_LISTE_VECHI, ca o republicare prinsa la jumatatea descarcarii sa nu lase Extensii fara pachetele
	noastre. O copie se pune la loc numai daca e chiar cea dintr-un stare.json semnat (pune_la_loc_sau_sterge); o sursa
	fara lista acum isi pastreaza copia de dinainte. Intoarce numele copiate."""
	try:
		conf = conf or P.citeste_configurarea(radacina)
		dosar = _cale(radacina, conf.lists_dir)
		tinta = _cale(radacina, DOSAR_LISTE_VECHI)
		surse = [s for lista in surse_feed(radacina, conf).values() for s in lista]
	except Exception as e:
		print('[HdsActualizari] copia listelor: %s' % e)
		return []
	copiate = []
	for nume, _a, _arh, _b in surse:
		cale = _lista(dosar, nume)
		if cale is None or os.path.islink(cale):
			continue
		try:
			if not os.path.isdir(tinta):
				os.makedirs(tinta, 0o700)
			copie = os.path.join(tinta, os.path.basename(cale))
			shutil.copyfile(cale, copie + '.nou')
			os.replace(copie + '.nou', copie)
			# o singura copie pe sursa: cea simpla sau cea .gz, dupa cum o tine opkg acum
			alta = copie[:-3] if copie.endswith('.gz') else copie + '.gz'
			if os.path.isfile(alta):
				os.remove(alta)
			copiate.append(nume)
		except (IOError, OSError) as e:
			print('[HdsActualizari] copia listei %s: %s' % (nume, e))
	return copiate


def _pune_copia_la_loc(radacina, dosar, nume, arh, stari):
	"""Copia veche a listei `nume` (pastreaza_listele) in locul celei descarcate, numai daca sha256 si marimea ei sunt
	indexul `arh` dintr-una din `stari` (stare.json semnate sau amprentele tinute minte, fiecare {'indexuri': ...}).
	True cand a pus-o."""
	copie = _lista(_cale(radacina, DOSAR_LISTE_VECHI), nume)
	if copie is None:
		return False
	try:
		amprenta = _sha256_fisier(copie)
	except (IOError, OSError, EOFError, ValueError):
		return False
	semnata = False
	for s in stari:
		ix = s.get('indexuri') if isinstance(s, dict) else None
		x = ix.get(arh) if isinstance(ix, dict) else None
		if isinstance(x, dict) and amprenta == (x.get('sha256'), x.get('marime')):
			semnata = True
			break
	if not semnata:
		return False
	tinta = os.path.join(dosar, os.path.basename(copie))
	try:
		shutil.copyfile(copie, tinta + '.vechi')
		for cale in (os.path.join(dosar, nume), os.path.join(dosar, nume + '.gz')):
			if cale != tinta and os.path.lexists(cale):
				os.remove(cale)
		os.replace(tinta + '.vechi', tinta)
	except (IOError, OSError) as e:
		print('[HdsActualizari] lista %s nu s-a putut pune la loc: %s' % (nume, e))
		return False
	return True


def pune_la_loc_sau_sterge(radacina, surse, stari, conf=None):
	"""Listele nepotrivite ale `surse` ([(nume, adresa, arh, baza)]): copia veche semnata se pune la loc
	(_pune_copia_la_loc, cu `stari`), altfel lista se sterge (sterge_listele). Intoarce (sterse, puse_la_loc)."""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	stari = [s for s in stari if isinstance(s, dict)]
	sterse, puse = [], []
	for nume, a, arh, baza in surse:
		if _pune_copia_la_loc(radacina, dosar, nume, arh, stari):
			puse.append(nume)
		else:
			sterge_listele(radacina, [(nume, a, arh, baza)], conf)
			sterse.append(nume)
	return sterse, puse


def tine_minte_indexurile(radacina, canal, baza, stare):
	"""Indexurile din stare.json semnat (canalul, baza, sha256 si marimea fiecarei liste), pentru pazeste_listele"""
	indexuri = stare.get('indexuri') if isinstance(stare, dict) else None
	if canal not in ('proba', 'public') or not _BAZA.match(u'%s' % baza) or not isinstance(indexuri, dict):
		return False
	cale = _cale(radacina, INDEXURI_SEMNATE)
	try:
		with open(cale + '.nou', 'w', encoding='utf-8') as f:
			json.dump({'canal': canal, 'baza': baza, 'actualizare': stare.get('actualizare'), 'indexuri': indexuri}, f,
				sort_keys=True)
		os.replace(cale + '.nou', cale)
	except (IOError, OSError, TypeError, ValueError) as e:
		print('[HdsActualizari] indexurile semnate: %s' % e)
		return False
	return True


def _stare_pentru_paza(radacina, canal, baza, deschide=None):
	"""stare.json semnat al canalului si bazei, cerut acum pentru pazeste_listele (None cand nu se poate: fara cheia
	canalului de proba, fara raspuns, nesemnat, alt canal). Timp scurt: paza ruleaza pe firul interfetei, la sfarsitul
	lui opkg update, cand serverul tocmai a raspuns."""
	if canal not in ('proba', 'public'):
		return None
	credentiale = citeste_netrc(radacina) if canal == 'proba' else None
	if canal == 'proba' and credentiale is None:
		return None
	noua, cod = descarca_stare(adresa_stare(canal, baza), credentiale, TIMP_STARE_PAZA, deschide)
	if cod is not None or noua.get('canal') not in (None, canal):
		print('[HdsActualizari] paza listelor: stare.json %s/%s nu s-a putut lua (%s)' % (canal, baza,
			noua.get('eroare') or cod))
		return None
	return noua


def pazeste_listele(radacina='/', deschide=None):
	"""Dupa un `opkg update` pornit din alta parte (Extensii): listele surselor feedului HD Satelit care nu sunt chiar
	cele din ultima stare.json semnata (tinute minte de tine_minte_indexurile la cautare si la verificarea zilnica) se
	sterg, ca un pachet pus pe server de altcineva sa nu se vada si sa nu se instaleze de acolo. Intoarce numele
	surselor sterse.

	0.7.4: inainte de stergere, stare.json semnat al canalului si bazei se cere o data (Wlad, Amiko V10, 11.11.2026:
	dupa punerea la loc a copiei setarilor si schimbarea bazei feedului 0.7.1 -> 0.7.0, amprentele tinute minte erau
	ale altei baze si fiecare opkg update al Extensiilor stergea toate listele HD Satelit, deci feedul aparea gol). Se
	sterg numai listele care nu se potrivesc nici cu stare.json semnat proaspat; cand se potrivesc, amprentele lui se
	tin minte. `deschide` (probele) inlocuieste urlopen.

	0.7.5 (FED, TODO 14.11 02:12; omul 945555, 13.11: listele sterse cat se republica feedul): in locul unei liste care nu
	se potriveste se pune copia ei de dinainte de opkg update (pastreaza_listele), numai cand copia e cea semnata
	(amprentele tinute minte sau stare.json proaspat); altfel se sterge, ca pana acum. ULTIMA_PAZA spune ce s-a pus la
	loc si ce s-a sters (Extensii reincearca atunci opkg update o data)."""
	ULTIMA_PAZA['sterse'], ULTIMA_PAZA['puse_la_loc'] = [], []
	conf = P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	tinute = _amprente_tinute(radacina)

	def semnata(nume, arh, canal, baza, amprente):
		cale = _lista(dosar, nume)
		x = None
		if amprente.get('canal') == canal and amprente.get('baza') == baza and isinstance(amprente.get('indexuri'), dict):
			x = amprente['indexuri'].get(arh)
		try:
			return isinstance(x, dict) and _sha256_fisier(cale) == (x.get('sha256'), x.get('marime'))
		except (IOError, OSError, EOFError, ValueError):
			return False

	sterse, puse = [], []
	for canal, surse in surse_feed(radacina, conf).items():
		# pe baze (feed/<canal>/<baza>/<arh>): fiecare baza are stare.json-ul ei
		pe_baze = {}
		for nume, _a, arh, baza in surse:
			if _lista(dosar, nume) is not None and not semnata(nume, arh, canal, baza, tinute):
				pe_baze.setdefault(baza, []).append((nume, arh))
		for baza, rele in pe_baze.items():
			noua = _stare_pentru_paza(radacina, canal, baza, deschide)
			# stari semnate cu care se poate potrivi copia veche: amprentele tinute minte (ale acestei baze) si cele proaspete
			stari = [tinute] if tinute.get('canal') == canal and tinute.get('baza') == baza else []
			if noua is not None:
				stari.append(noua)
				proaspete = {'canal': canal, 'baza': baza, 'indexuri': noua.get('indexuri')}
				bune = [(n, a) for n, a in rele if semnata(n, a, canal, baza, proaspete)]
				if bune and tine_minte_indexurile(radacina, canal, baza, noua):
					tinute = dict(proaspete, actualizare=noua.get('actualizare'))
					print('[HdsActualizari] paza listelor: amprentele %s/%s luate din nou, liste pastrate: %s' % (
						canal, baza, ', '.join(n for n, _a in bune)))
					rele = [x for x in rele if x not in bune]
			s, p = pune_la_loc_sau_sterge(radacina, [(nume, '', arh, baza) for nume, arh in rele], stari, conf)
			sterse.extend(s)
			puse.extend(p)
	if puse:
		print('[HdsActualizari] liste HD Satelit nepotrivite, puse la loc cele semnate de dinainte: %s' % ', '.join(puse))
	if sterse:
		print('[HdsActualizari] liste HD Satelit nesemnate, sterse: %s' % ', '.join(sterse))
	ULTIMA_PAZA['sterse'], ULTIMA_PAZA['puse_la_loc'] = list(sterse), list(puse)
	return sterse


def pachete_semnate(semnat, rezultat):
	"""([{nume, versiune, arhitectura, fisier, marime, sha256}], None) pentru pachetele planului, din stare.json semnat
	al cautarii; (None, motiv) cand unul nu are acolo chiar versiunea din plan, fisierul, marimea si suma. Intrarea se
	alege dupa nume si arhitectura (pachet_din_stare); arhitecturile receptorului le verifica apoi pachete_straine."""
	stare = (semnat or {}).get('stare')
	if not isinstance(stare, dict) or stare.get('actualizare') != (rezultat.get('server') or {}).get('actualizare'):
		return None, 'starea semnata a cautarii lipseste'
	arhitecturi = stare.get('arhitecturi') or []
	rez = []
	for x in rezultat.get('pachete') or []:
		# 0.7.7 (DRV): driverul placii are intrarea in „drivere_placii”, nu in „pachete”
		p = driver_din_stare(stare, x.get('nume'), x.get('arhitectura')) if x.get('driver_placii') else \
			pachet_din_stare(stare, x.get('nume'), x.get('arhitectura'))
		if not p or p.get('versiune') != x.get('la'):
			return None, 'pachetul %s nu e in stare.json semnat' % x.get('nume')
		fisier, arh, marime, sha = p.get('fisier'), p.get('arhitectura'), p.get('marime'), p.get('sha256')
		if not isinstance(fisier, str) or not _FISIER_IPK.match(fisier) or not isinstance(arh, str) or \
				not _ARH.match(arh) or arh not in arhitecturi or not isinstance(marime, int) or isinstance(marime, bool) or \
				marime <= 0 or not isinstance(sha, str) or not _SHA256.match(sha):
			return None, 'pachetul %s nu are fisierul, marimea sau suma semnate' % x.get('nume')
		rez.append({'nume': x['nume'], 'versiune': p['versiune'], 'arhitectura': arh, 'fisier': fisier, 'marime': marime,
			'sha256': sha})
	if not rez:
		return None, 'niciun pachet de instalat'
	return rez, None


def pachete_straine(intrari, arhitecturi_receptor):
	"""Motivul refuzului cand un pachet semnat (pachete_semnate) e pentru o arhitectura pe care receptorul nu o are in
	arch.conf (un pachet al altei masini din feedul comun nu e al lui); None cand toate sunt ale lui sau cand
	arhitecturile receptorului nu se stiu"""
	if not arhitecturi_receptor:
		return None
	for x in intrari or []:
		if x.get('arhitectura') not in arhitecturi_receptor:
			return 'pachetul %s e pentru %s, nu pentru arhitecturile receptorului' % (x.get('nume'), x.get('arhitectura'))
	return None


def goleste_dosarul(dosar=None):
	"""sterge dosarul pachetelor descarcate (dupa instalare sau la o greseala)"""
	try:
		shutil.rmtree(dosar or DOSAR_PACHETE)
	except OSError:
		pass


def loc_liber(dosar):
	"""octetii liberi in sistemul de fisiere al dosarului, None cand nu se stie"""
	try:
		s = os.statvfs(dosar)
	except (AttributeError, OSError):
		return None
	return s.f_bavail * s.f_frsize


def _marime_instalarii(p):
	"""Camp adaugat compatibil in feed; lipsa lui nu inseamna crestere zero."""
	x = p.get('instalare')
	if not isinstance(x, dict) or type(x.get('format')) is not int or x['format'] != 1 or x.get('unitate') != 'octeti':
		return None
	if type(x.get('octeti')) is not int or not 0 <= x['octeti'] <= 2 * 1024 * 1024 * 1024 or \
			type(x.get('intrari')) is not int or not 0 <= x['intrari'] <= 100000:
		return None
	if not x['intrari'] and x['octeti']:
		return None
	return x


def _candidatii_spatiului(stare, radacina, conf):
	"""Listele tuturor surselor, nu numai feedul actualizarii semnate."""
	semnate = [p for p in stare.get('pachete') or [] if isinstance(p, dict) and
		p.get('arhitectura') in conf.arhitecturi]
	disponibile = list(semnate)
	dosar = _cale(radacina, conf.lists_dir)
	try:
		for sursa, _adresa in conf.surse:
			# Daca exista ambele forme, niciuna nu dovedeste absenta din cealalta.
			for nume_lista in (sursa, sursa + '.gz'):
				cale = os.path.join(dosar, nume_lista)
				try:
					os.lstat(cale)
				except FileNotFoundError:
					continue
				# Nu folosi inventarul memorat: listele se pot schimba dupa descarcare.
				with (gzip.open(cale, 'rb') if cale.endswith('.gz') else open(cale, 'rb')) as f:
					date = f.read(32 * 1024 * 1024 + 1)
				if len(date) > 32 * 1024 * 1024:
					return None
				for s in P.strofe_din_text(date.decode('utf-8')):
					if s.get('architecture') not in conf.arhitecturi or not P.nume_valid(s.get('package')):
						continue
					q = {'nume': s['package'], 'versiune': s.get('version', ''),
						'arhitectura': s['architecture'], 'provides': s.get('provides', '')}
					# O versiune ori o furnizare din alt feed nu mosteneste dimensiunea semnata.
					if not any(p['nume'] == q['nume'] and p['versiune'] == q['versiune'] and
							p['arhitectura'] == q['arhitectura'] and p.get('sha256') == s.get('sha256sum') and
							p.get('sha256') and p.get('depends') == ', '.join(s[c] for c in
							('pre-depends', 'depends') if s.get(c)) and p.get('provides') == q['provides'] and
							p.get('recommends') == s.get('recommends', '') for p in semnate):
						disponibile.append(q)
	except (OSError, EOFError, ValueError, zlib.error):
		return None
	return disponibile


def _pachetele_spatiului(stare, rezultat, radacina, conf):
	"""Include dependinte si recomandari, recursiv, cu toate alternativele posibile."""
	rez, coada = {}, list(rezultat.get('pachete') or [])
	inst = instalate(radacina, conf)
	furn = furnizate(radacina, conf)
	programate = {p['nume']: p['la'] for p in coada}
	stari_vazute = {tuple(sorted(programate.items()))}
	analizate, planuri, generatie = {}, {}, 0
	disponibile = _candidatii_spatiului(stare, radacina, conf)
	if disponibile is None:
		return None
	while coada:
		p = coada.pop(0)
		x = driver_din_stare(stare, p.get('nume'), p.get('arhitectura')) if p.get('driver_placii') else \
			pachet_din_stare(stare, p.get('nume'), p.get('arhitectura'))
		if not x or x.get('versiune') != p.get('la') or _marime_instalarii(x) is None or \
				any(not isinstance(x.get(c), str) for c in ('depends', 'provides', 'recommends')):
			return None
		cheie = (x['nume'], x.get('arhitectura'))
		if analizate.get(cheie) == generatie:
			continue
		analizate[cheie] = generatie
		cerinte = []
		for camp in ('depends', 'recommends'):
			if not x[camp].strip():
				continue
			for grup in x[camp].split(','):
				alternative = []
				for alt in grup.split('|'):
					citita = _dependinte(alt)
					if len(citita) != 1 or len(citita[0]) != 1:
						return None
					alternative.extend(citita[0])
				cerinte.append((camp == 'recommends', alternative))
		rez[cheie] = x
		planuri[cheie] = dict(p)
		if len(rez) > PRAG_PACHETE:
			return None
		for optionala, alternative in cerinte:
			def satisfacuta(n, op, v):
				versiune = programate.get(n, inst.get(n))
				if versiune and (not op or _satisface(versiune, op, v)):
					return True
				return any(not op or (dat and _satisface(dat, op, v)) for dat, sursa in furn.get(n, ())
					if sursa not in programate)
			if any(satisfacuta(n, op, v) for n, op, v in alternative):
				continue
			gasite = []
			for n, op, v in alternative:
				for q in disponibile:
					potrivit = q['nume'] == n and (not op or _satisface(q['versiune'], op, v))
					if not potrivit:
						potrivit = any(nume == n and (not op or (dat and _satisface(dat, op, v)))
							for nume, dat in _furnizari(q.get('provides', '')))
					if potrivit:
						if _marime_instalarii(q) is None:
							return None
						gasite.append({'nume': q['nume'], 'la': q['versiune'], 'arhitectura': q['arhitectura']})
			if not gasite:
				if optionala:
					continue
				return None
			nou = dict(programate)
			nou.update((q['nume'], q['la']) for q in gasite)
			if nou != programate:
				stare_noua = tuple(sorted(nou.items()))
				# Un conflict intre versiuni nu trebuie sa tina lucrarea blocata.
				if stare_noua in stari_vazute or len(stari_vazute) > PRAG_PACHETE:
					return None
				stari_vazute.add(stare_noua)
				programate = nou
				generatie += 1
				# O dependinta noua poate inlocui o furnizare deja considerata instalata.
				coada.extend(planuri.values())
			coada.extend(gasite)
	return list(rez.values())


def _feed_fara_dimensiuni(stare):
	"""True cand stare.json e facut fara campurile de instalare (niciun pachet nu are 'instalare'): feedurile bazelor
	0.7.0, 0.7.1 si 0.7.3, unde stare.json trebuie sa ramana sub 256 KiB pentru codul lor (MARIME_STARE_MAX de atunci)."""
	pachete = [p for p in stare.get('pachete') or [] if isinstance(p, dict)]
	return bool(pachete) and not any('instalare' in p for p in pachete)


def verifica_loc_radacina(semnat, rezultat, radacina='/'):
	"""Intoarce (octeti necesari, problema), pentru radacina, separat de descarcare."""
	stare = (semnat or {}).get('stare') or {}
	conf = P.citeste_configurarea(radacina)
	pachete = _pachetele_spatiului(stare, rezultat, radacina, conf)
	if not pachete:
		if _feed_fara_dimensiuni(stare):
			# BLD8 (0.7.8): feedul unei baze vechi (0.7.0, 0.7.1, 0.7.3) n-are dimensiunile de instalare: codul acelor baze
			# citeste cel mult 256 KiB din stare.json, iar campurile le-ar trece peste limita. Ramane purtarea de dinainte:
			# fara verificarea radacinii (locul descarcarii il verifica descarca_pachete), ca actualizarea si Repara imaginea
			# sa mearga si acolo. Un feed care are dimensiunile, dar nu la pachetul cerut, se refuza ca pana acum.
			return None, None
		return None, ('dimensiuni', 'metadate de instalare sau dependinte lipsa ori necunoscute')
	nevoie = LOC_IN_PLUS
	try:
		bloc = max(4096, os.statvfs(radacina).f_frsize)
	except (AttributeError, OSError):
		bloc = 65536
	for x in pachete:
		m = _marime_instalarii(x)
		nou = m['octeti'] + m['intrari'] * bloc
		# Numele sterse nu elibereaza blocurile fisierelor inca deschise sau mapate.
		# Nu putem dovedi ca vreun fisier vechi este eliberat pe durata instalarii.
		nevoie += nou
	liber = loc_liber(radacina)
	if liber is None:
		return nevoie, ('loc-necunoscut', 'statvfs radacina indisponibil')
	if liber < nevoie:
		return nevoie, ('loc', 'radacina: %d octeti liberi, necesari %d' % (liber, nevoie))
	return nevoie, None


def _text_refuz_loc(fel):
	if fel == 'loc':
		return _t('Nu mai este loc în memoria receptorului.')
	if fel == 'dimensiuni':
		return _t('Actualizarea nu are dimensiunile de instalare necesare verificării spațiului. Instalarea este oprită. Încearcă din nou după actualizarea feedului.')
	if fel == 'loc-necunoscut':
		return _t('Nu se poate verifica spațiul liber din memoria receptorului. Instalarea este oprită.')
	return _t('Un fișier nu s-a putut descărca de pe server.')


def descarca_pachete(intrari, adresa_baza, credentiale=None, dosar=None, deschide=None, timp=TIMP_PACHET):
	"""Descarca pachetele (pachete_semnate) in `dosar` (golit intai) si le verifica: (cai, None) sau (None, (fel,
	detaliu)); fel: 'nesemnat' (un pachet nu e chiar cel semnat: alta marime sau alta suma), 'loc' (nu incap) sau
	'descarcare'. Fiecare pachet se scrie in <fisier>.partial, cu sha256 socotit pe drum si cel mult marimea semnata plus
	un octet, si ramane numai daca e chiar cel semnat; la orice greseala dosarul se goleste."""
	dosar = dosar or DOSAR_PACHETE
	goleste_dosarul(dosar)
	try:
		os.makedirs(dosar, 0o700)
	except OSError as e:
		return None, ('descarcare', curata(e))
	nevoie = sum(x['marime'] for x in intrari) + LOC_IN_PLUS
	liber = loc_liber(dosar)
	if liber is not None and liber < nevoie:
		goleste_dosarul(dosar)
		return None, ('loc', '%d MB liberi, trebuie %d MB' % (liber // 1048576, nevoie // 1048576 + 1))
	antete = {'User-Agent': UA, 'Accept': 'application/octet-stream', 'Cache-Control': 'no-cache'}
	if credentiale:
		antete['Authorization'] = 'Basic ' + base64.b64encode(('%s:%s' % credentiale).encode('utf-8')).decode('ascii')
	cai = []
	for x in intrari:
		cale = os.path.join(dosar, x['fisier'])
		h = hashlib.sha256()
		n = 0
		try:
			r = (deschide or urlopen)(Request('%s/%s/%s' % (adresa_baza, x['arhitectura'], x['fisier']), headers=antete),
				timeout=timp)
			try:
				with open(cale + '.partial', 'wb') as f:
					while n <= x['marime']:
						bucata = r.read(min(1 << 16, x['marime'] + 1 - n))
						if not bucata:
							break
						n += len(bucata)
						h.update(bucata)
						f.write(bucata)
			finally:
				try:
					r.close()
				except Exception:
					pass
		except HTTPError as e:
			goleste_dosarul(dosar)
			return None, ('descarcare', '%s: HTTP %d' % (x['fisier'], e.code))
		except (URLError, socket.timeout, socket.error, OSError, ValueError) as e:
			goleste_dosarul(dosar)
			return None, ('descarcare', '%s: %s' % (x['fisier'], curata(getattr(e, 'reason', e))))
		if n != x['marime'] or h.hexdigest() != x['sha256']:
			goleste_dosarul(dosar)
			return None, ('nesemnat', 'pachetul %s nu e cel semnat (%s)' % (x['nume'], 'alta marime' if n != x['marime']
				else 'alta suma'))
		os.replace(cale + '.partial', cale)
		cai.append(cale)
	return cai, None


def argumente_instalare(cai, dosar=None, reinstaleaza=False, downgrade=False):
	"""Argumentele opkg pentru pachetele verificate (install <cale>...), primite numai din dosarul lor: pe receptor /tmp
	e o legatura spre /var/volatile/tmp, iar radacinile implicite din Components/Ipkg.py n-ar primi calea reala. None
	cand o cale e refuzata. reinstaleaza: planul are un pachet ramas la jumatate cu aceeasi versiune (planul_reinstalarii),
	pe care opkg l-ar refuza din cale ("matches the installed version") fara --force-reinstall. downgrade: a doua
	incercare, cand opkg a cerut sa coboare un pachet strain la versiunea din feedul HD Satelit (downgrade_straine)."""
	from Components.Ipkg import opkgArguments
	radacina = os.path.join(os.path.realpath(dosar or DOSAR_PACHETE), '')
	# --force-overwrite (12.11.2026, dupa TM): o tema straina instalata ca in OE-Alliance (--force-overwrite) poate lua un fisier al
	# imaginii in lista ei; fara optiune, actualizarea imaginii ar cadea pe aceeasi ciocnire. Pachetele imaginii sunt semnate si
	# verificate mai sus, deci ele iau fisierul inapoi.
	optiuni = ['--force-overwrite']
	if reinstaleaza:
		optiuni.append('--force-reinstall')
	if downgrade:
		optiuni.append('--force-downgrade')
	return opkgArguments('install', list(cai), tuple(optiuni), (radacina,))


# Pachetele straine cu numele unui pachet al imaginii si versiunea mai mare (14.11.2026, Vu+ Uno 4K SE, pachetele 2081 si
# 2150): ffmpeg-182.all si exteplayer3-182.all, puse din alt feed, opreau actualizarea rapida cu cod 1 de trei ori la rand
# ("problem with installed package ffmpeg-182.all", "Solution 1: allow downgrade of ffmpeg-182.all to
# ffmpeg-9.0.2-r0.hds1.<arh>"). opkg nu coboara singur versiunea, iar --force-downgrade e o optiune pentru toata comanda,
# deci nu se pune de la inceput: numai a doua incercare il are, si numai cand TOATE coborarile cerute de opkg sunt pachete
# straine (versiunea instalata nu e in feedul nostru si e mai mare) duse chiar la versiunea din listele HD Satelit.
_COBORARE = re.compile(r'allow downgrade of (\S+) to (\S+)')


def downgrade_cerute(linii):
	"""[(de_la, la)] din randurile solver-ului opkg ("allow downgrade of <nume>-<versiune>.<arh> to ..."), fara dubluri"""
	rez = []
	for linie in linii or []:
		for m in _COBORARE.finditer(linie or ''):
			if m.groups() not in rez:
				rez.append(m.groups())
	return rez


def _potriveste(text, nume, versiune, arhitecturi):
	"""True cand text e chiar <nume>-<versiune>.<arh> (asa scrie solver-ul opkg un pachet), cu arh una din arhitecturi"""
	inceput = '%s-%s.' % (nume, versiune)
	return bool(versiune) and text.startswith(inceput) and text[len(inceput):] in arhitecturi


def downgrade_straine(linii, feed, inst, arhitecturi):
	"""Coborarile cerute de opkg care sunt pachete straine puse peste numele unui pachet HD Satelit: ([(nume, de_la, la)],
	None) cand fiecare coborare duce un pachet instalat, cu versiunea mai mare decat in feed, chiar la versiunea din
	listele semnate ale feedului nostru (feed = pachete_din_feed); (None, motiv) altfel (nimic cerut, alt pachet, alta
	versiune), iar atunci a doua incercare nu se face."""
	cerute = downgrade_cerute(linii)
	if not cerute:
		return None, 'opkg nu cere nicio coborare de versiune'
	arh = set(arhitecturi or ()) | set(('all', 'noarch'))
	rez = []
	for de_la, la in cerute:
		gasit = None
		for nume, s in feed.items():
			v = s.get('version', '')
			if _potriveste(la, nume, v, arh) and nume in inst and _potriveste(de_la, nume, inst[nume], arh) and \
					P.compara_versiuni(inst[nume], v) > 0:
				gasit = (nume, inst[nume], v)
				break
		if gasit is None:
			return None, 'coborarea %s -> %s nu e a unui pachet strain spre feedul HD Satelit' % (de_la, la)
		rez.append(gasit)
	return rez, None


def text_inlocuite(inlocuite):
	"""Ce afla omul cand actualizarea a pus pachetele HD Satelit peste cele din alt feed (pe televizor si in pagina web)"""
	return _t('Pachetele %s puse din alt feed au fost înlocuite cu cele HD Satelit.') % ', '.join(
		'%s %s' % (n, versiune_scurta(de_la)) for n, de_la, _la in inlocuite[:5])


# ---------------------------------------------------------------- config

def config_actualizari():
	"""config.hds_actualizari: zilnic (verificarea zilnica, pornita din fabrica), anuntat (ce s-a anuntat deja) si, din
	0.7.8 (RIA), repornire_singura (interfata se reporneste singura dupa o actualizare, Da din fabrica)"""
	from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigText
	# nu hasattr(config, ...): Config.__getattr__ din enigma2 arunca KeyError, nu AttributeError, iar hasattr din
	# Python 3 prinde numai AttributeError (gasit in emulator la integrarea 0.3.0.2); ca HdsAfisaj si HdsCalitateImagine
	if 'hds_actualizari' not in config.content.items:
		config.hds_actualizari = ConfigSubsection()
		config.hds_actualizari.zilnic = ConfigYesNo(default=True)
		config.hds_actualizari.anuntat = ConfigText(default='', fixed_size=False)
	# separat: sectiunea poate fi facuta deja de codul din memorie de dinainte de 0.7.8, fara cheia noua
	if 'repornire_singura' not in config.hds_actualizari.content.items:
		config.hds_actualizari.repornire_singura = ConfigYesNo(default=True)
	# 0.8.0 (AUT1): Actualizari automate (Da din fabrica); separat, ca repornire_singura
	if 'automat' not in config.hds_actualizari.content.items:
		config.hds_actualizari.automat = ConfigYesNo(default=True)
	if 'asteptare' not in config.hds_actualizari.content.items:
		# "<cheia versiunii> <ora la care a fost vazuta prima data>" (ASTEPTARE_MAX_S)
		config.hds_actualizari.asteptare = ConfigText(default='', fixed_size=False)
	return config.hds_actualizari


def automat_pornit():
	"""0.8.0 (AUT1): True = versiunile noi din feed se instaleaza singure (standby sau noaptea). Fara setare: True."""
	try:
		return bool(config_actualizari().automat.value)
	except Exception:
		return True


def seteaza_automat(pornit):
	c = config_actualizari()
	c.automat.value = bool(pornit)
	c.automat.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return bool(c.automat.value)


def zilnic_pornit():
	try:
		return bool(config_actualizari().zilnic.value)
	except Exception:
		return True


def seteaza_zilnic(pornit):
	c = config_actualizari()
	c.zilnic.value = bool(pornit)
	c.zilnic.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return bool(c.zilnic.value)


def repornire_singura():
	"""0.7.8 (RIA): True = dupa actualizare interfata se reporneste singura (numaratoarea); False = intrebarea de dinainte.
	Fara setare (o eroare): True, ca din fabrica."""
	try:
		return bool(config_actualizari().repornire_singura.value)
	except Exception:
		return True


def seteaza_repornire_singura(pornit):
	c = config_actualizari()
	c.repornire_singura.value = bool(pornit)
	c.repornire_singura.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return bool(c.repornire_singura.value)


# ---- 0.7.8 (RIA): repornirea singura dupa orice actualizare instalata (vezi NUMARATOARE_S)
def _sesiune_globala():
	"""Sesiunea enigma2, de oriunde (pagina web, Extensii, actualizarea): cea data lui HdsImagineOnline la pornire, altfel a
	barei de canale; None cand nu se poate afla"""
	try:
		from Components.HdsImagineOnline import imagine_online
		if getattr(imagine_online, 'session', None) is not None:
			return imagine_online.session
	except Exception:
		pass
	try:
		from Screens.InfoBar import InfoBar
		if InfoBar.instance is not None:
			return InfoBar.instance.session
	except Exception:
		pass
	return None


def _reporneste_implicit(sesiune_f):
	"""Functia de repornire a modului rapid (Plugins/Extensions/HdsWebControl/actualizari_web.reporneste_rapid), sau None
	fara pagina web (atunci ramane calea veche: intrebarea, butonul, plasa din standby)"""
	try:
		from Plugins.Extensions.HdsWebControl.actualizari_web import reporneste_rapid
	except Exception:
		return None
	return reporneste_rapid(sesiune_f)


def _timeshift_folosit():
	"""True cand omul se uita in urma in timeshift (redarea din fisierul timeshift-ului, nu numai tamponul pornit)"""
	try:
		from Screens.InfoBar import InfoBar
		bara = InfoBar.instance
		ts = bara.getTimeshift() if bara is not None else None
		return bool(ts is not None and ts.isTimeshiftActive())
	except Exception:
		return False


def motiv_asteptare(sesiune, radacina='/'):
	"""De ce asteapta repornirea dupa actualizare ('inregistrare', 'lucrare', 'intrebare', 'timeshift') sau '' cand se
	poate acum. Aceleasi reguli ca actualizari_web.reporneste_rapid (Components/HdsAlimentare.stareReceptor: inregistrare
	acum sau in 6 minute, lucrari in fundal, o intrebare de repornire deschisa), plus alt opkg sau o instalare in curs
	(iesirea interfetei l-ar opri la jumatate) si timeshift-ul folosit. Fara sesiune (probele de pe PC) numai opkg."""
	try:
		if actualizari.faza == 'instalez' or opkg_ocupat(radacina):
			return 'lucrare'
	except Exception:
		pass
	if sesiune is None:
		return ''
	try:
		from Components.HdsAlimentare import stareReceptor
		st = stareReceptor(sesiune)
	except Exception:
		st = {}
	if st.get('intrebare_pe_tv'):
		return 'intrebare'
	if st.get('inregistrari') or st.get('curand'):
		return 'inregistrare'
	if st.get('lucrari'):
		return 'lucrare'
	if _timeshift_folosit():
		return 'timeshift'
	return ''


def _cod_repornire(sesiune):
	"""3 (interfata) sau 2 (receptorul: driverul placii nou sau memoria decodorului farmitata), fara rand in jurnal"""
	try:
		from Components.HdsMemorieDriver import codRepornireDupaActualizare
		return codRepornireDupaActualizare(sesiune, jurnal=lambda text: None)
	except Exception:
		return 3


def _text_repornire(cod):
	"""Textul numaratorii, deja tradus (Components/HdsMemorieDriver.textRepornire)"""
	try:
		from Components.HdsMemorieDriver import textRepornire
		return textRepornire(cod)
	except Exception:
		return _t('Actualizarea s-a instalat. Interfața se repornește acum.')


def _cale_semnului_standby():
	try:
		from Components import HdsImagineOnline as I
		return os.path.join(I._rad(), I.STANDBY_DUPA_REPORNIRE.lstrip('/'))
	except Exception:
		return None


def _scrie_semnul_standby():
	"""Semnul intoarcerii in standby dupa repornire (HdsImagineOnline.dupa_pornire); calea lui, sau None"""
	cale = _cale_semnului_standby()
	if not cale:
		return None
	try:
		with open(cale, 'w') as f:
			f.write('1\n')
		return cale
	except Exception:
		return None


def _sterge_semnul_standby(cale):
	if cale:
		try:
			os.remove(cale)
		except OSError:
			pass


def text_pana_la_repornire(a=None):
	"""0.7.8 (RIA): randul din Informatii > Despre imagine (si pagina web /informatii/despre) cat o actualizare instalata
	asteapta repornirea interfetei: de ce asteapta (TEXTE_ASTEPTARE) sau ca trebuie repornita; '' altfel. Textele sunt
	cele deja traduse."""
	a = a or actualizari
	if not a.repornire:
		return ''
	if repornire_receptor_ceruta(a.radacina):
		return _t(TEXT_DRIVER_NOU)
	if a.rapid and a.rapid_pas in TEXTE_ASTEPTARE:
		return _t(TEXTE_ASTEPTARE[a.rapid_pas])
	if a.rapid:
		return _t('Actualizarea s-a instalat. Interfața se repornește acum.')
	return _t('Actualizarea s-a instalat. Interfața trebuie repornită ca să o folosească.')


def reporneste_dupa_extensii():
	"""0.7.8 (RIA): Extensii (Components/HdsExtensiiLucru.Lucrare, televizorul si pagina web) a schimbat programul imaginii pe
	disc: aceeasi repornire singura ca dupa Actualizare software. True cand a pornit aici sau era deja pornita (modul
	rapid)."""
	return actualizari.porneste_repornirea('extensii') or actualizari.rapid


# ---------------------------------------------------------------- lucrarea (o singura data, pentru ecran si web)

class Actualizari(object):
	"""Starea comuna a ecranului si a paginii web. Toate metodele ruleaza pe firul enigma2; citirile de retea si de
	fisiere merg pe fire separate (HdsPazaModel.LucrareFundal), opkg prin Components/Ipkg.py (lista de argumente)."""

	def __init__(self, radacina='/'):
		self.radacina = radacina
		self.faza = 'liber'          # liber | caut | instalez
		self.pas = ''
		self.progres = (0, 0)
		self.rezultat = {'stare': NECAUTAT}
		self.mesaj = ''
		self.jurnal = []
		self.repornire = False
		self.canal = None
		self.ascultatori = []
		self._lucrari = []
		self._ipkg = None
		self._lista_ipkg = []
		self._de_instalat = []
		# pachetele straine inlocuite la a doua incercare (_incearca_coborarea): [(nume, de_la, la)] sau None
		self._inlocuite = None
		self._neconfigurate_inainte = None
		self._partea_doua_detasa = False
		self._partea_doua_lacat = None
		# stare.json semnat al ultimei cautari (pachetele se verifica cu el la instalare),
		# adresa lui si baza feedului
		self._semnat = None
		self._adresa = ''
		self._baza_feed = ''
		# actualizarea rapida: rapid cat merge (de la apasare pana cade interfata, sau pana se opreste), rapid_pas unde
		# a ajuns (caut, instalez, repornesc, inregistrare, lucrare, intrebare, refuzata); ramane dupa oprire, ca
		# pagina sa vada unde
		self.rapid = False
		self.rapid_pas = ''
		self._reporneste_rapid = None
		self._ceas_rapid = None
		self._legatura_rapid = None
		self.fabrica_ceas = None        # eTimer; probele de pe PC dau altul
		# 0.7.8 (HB7): repornirea in standby a interfetei ramase nerepornite dupa instalare (STANDBY_REPORNIRE_MS)
		self._ceas_standby = None
		self._legatura_standby = None
		self._standby_armat = False
		self.reporneste_standby = None  # functia de repornire din standby; probele de pe PC dau alta
		# 0.7.8 (RIA): sesiunea pentru fereastra dinaintea repornirii (numaratoarea sau intrebarea) si fereastra deschisa;
		# probele de pe PC dau sesiunea lor
		self.sesiune = None
		self._fereastra = None
		# o singura reincercare a cautarii cand listele nu se potrivesc (0.7.5, FED, _reincearca_cautarea)
		self._reincercare_liste = False
		self._ceas_liste = None
		self._legatura_liste = None
		self._generatie_cautare = 0
		self._rezerva_incercata = False
		# rezultatul lui tools/hds-actualizare-intrerupta.py de la pornirea aceasta (rezultat_pornire), sau None
		self.reparare = None
		# imaginea() tinuta minte pentru stare_publica (_imaginea_publica): cheia status-ului opkg cand s-a citit, calea lui
		# si daca o recitire e deja pe firul ei
		self._img = None
		self._img_cheie = None
		self._img_status = None
		self._img_citire = False
		# 0.7.8 (RPR8): „Repară imaginea” in lucru (de la apasare pana la repornire sau oprire), ce s-a pus la loc (pus in
		# fata textului de dinaintea repornirii) si copiile fisierelor ocrotite cat ruleaza opkg (copiaza_ocrotite)
		self.repara = ''
		self._nota_reparatie = ''
		self._ocrotite = None
		self._repara_principal = False
		# 0.8.0 (AUT1): actualizarea rapida pornita de actualizarile automate (VerificareZilnica._incearca_auto)
		self._automat = False

	# ---- ascultatorii (ecranul si pagina web se reimprospateaza singure)
	def _schimbat(self):
		for f in self.ascultatori[:]:
			try:
				f()
			except Exception as e:
				print('[HdsActualizari] ascultator: %s' % e)

	def _jurnal(self, rand):
		rand = curata(rand)
		self.jurnal.append(rand)
		del self.jurnal[:-RANDURI_JURNAL]
		# cu fsync, ca randurile sa ramana si dupa o repornire dura; din 0.7.5 (ASM, TODO 15.11 00:02 (HdsPachete in fir))
		# fsync-ul e pe un fir separat: la fiecare rand scris de opkg in timpul instalarii, firul enigma2 statea 2,8-4 s
		# in el pe Solo SE (tastele intarziau pana la 1,4 s)
		P.scrie_jurnal_rotit(JURNAL, '%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), rand), MARIME_JURNAL,
			sincron=P.SINCRON_FUNDAL)

	def _cheie_status(self):
		"""(inode, marime, mtime) ale status-ului opkg, sau None cand nu exista; calea se afla o data"""
		if self._img_status is None:
			try:
				self._img_status = _cale(self.radacina, P.citeste_configurarea(self.radacina).status_file)
			except Exception:
				return None
		try:
			st = os.stat(self._img_status)
		except OSError:
			return None
		return (st.st_ino, st.st_size, getattr(st, 'st_mtime_ns', st.st_mtime))

	def _imaginea_publica(self):
		"""imaginea() pentru stare_publica fara status-ul opkg citit pe firul enigma2 la fiecare reimprospatare (0.7.5 ASM,
		TODO 15.11 00:02 (HdsPachete in fir)): in timpul instalarii, fiecare rand scris de opkg reimprospata ecranul, care
		citea si despartea tot status-ul (citeste_strofe, strofe_din_text: 2,8-3,5 s pe Solo SE). Prima data se citeste
		pe loc, ca pana acum; apoi numai cand status-ul s-a schimbat (inode, marime, ora), pe un fir separat, iar pana
		atunci ramane valoarea de dinainte; cand opkg lucreaza (faza caut sau instalez) status-ul e pe jumatate scris si
		nu se reciteste deloc. Dupa citire ecranul si pagina se reimprospateaza (_schimbat)."""
		if self._img is None:
			self._img_cheie = self._cheie_status()
			self._img = imaginea(self.radacina)
			return self._img
		if self.faza != 'liber' or self._img_citire:
			return self._img
		cheie = self._cheie_status()
		if cheie == self._img_cheie:
			return self._img
		self._img_citire = True
		radacina = self.radacina

		def gata(rez, eroare):
			self._img_citire = False
			if rez is None or eroare:
				# se reincearca numai cand status-ul se schimba din nou, nu la fiecare reimprospatare
				self._img_cheie = cheie
				print('[HdsActualizari] versiunea instalata: %s' % eroare)
				return
			self._img, self._img_cheie = rez, cheie
			self._schimbat()
		self._lucrare(lambda: imaginea(radacina), gata)
		return self._img

	def ocupat(self):
		return self.faza != 'liber'

	def poate_porni(self):
		"""('' daca se poate porni o cautare sau o instalare, altfel textul de ce nu)"""
		try:
			from Components import HdsParteaDoua
			if HdsParteaDoua.lucrare.ocupat:
				return _t('Asteapta sa se termine instalarea partii a doua pe stick.')
		except ImportError:
			pass
		if self.repornire:
			if repornire_receptor_ceruta(self.radacina):
				return _t(TEXT_DRIVER_NOU)
			return _t('Actualizarea s-a instalat. Repornește interfața înainte de altceva.')
		if self.faza != 'liber':
			return _t('Așteaptă să se termine operația de acum.')
		if opkg_ocupat(self.radacina):
			return _t('Alt program instalează sau descarcă pachete acum. Încearcă după ce termină.')
		from Components.Ipkg import opkgProgram
		if not opkgProgram():
			return _t('Instalarea pachetelor nu este disponibilă în această imagine.')
		return ''

	def _lucrare(self, functie, gata):
		from Components.HdsPazaModel import LucrareFundal
		pastrata = []

		def la_sfarsit(rez, eroare):
			for x in pastrata:
				if x in self._lucrari:
					self._lucrari.remove(x)
			gata(rez, eroare)
		lucrare = LucrareFundal(functie, la_sfarsit)
		pastrata.append(lucrare)
		self._lucrari.append(lucrare)

	# ---- cautarea
	def cauta(self):
		motiv = self.poate_porni()
		if motiv:
			self.mesaj = motiv
			self._schimbat()
			return False
		self.mesaj = ''
		canal, surse, baza_feed = canalul(self.radacina)
		self.canal = canal
		if canal is None:
			self.rezultat = {'stare': FARA_SURSA}
			self._schimbat()
			return False
		if canal == 'proba-fara-cheie':
			self.rezultat = {'stare': FARA_CHEIE}
			self._schimbat()
			return False
		self._generatie_cautare += 1
		generatie = self._generatie_cautare
		if not self._reincercare_liste:
			self._rezerva_incercata = False
		self.faza, self.pas, self.progres = 'caut', _t('Se citește starea actualizărilor de pe server...'), (1, 3)
		self._schimbat()
		credentiale = citeste_netrc(self.radacina) if canal == 'proba' else None
		# numai baza (/etc/hdsatelit-model), nu imaginea(): aceea citea si despartea tot status-ul opkg pe firul enigma2
		# la fiecare cautare, 2-3 s pe Solo SE (0.7.5 FIR, TODO 15.11 05:08 (ASM, cautarea in fir)); versiunea instalata
		# o citeste rezultat_din_liste, in lucrarea de dupa opkg update
		baza = baza_feed or baza_receptorului(self.radacina)
		adresa = adresa_stare(canal, baza)
		self._semnat, self._adresa, self._baza_feed = None, adresa, baza
		radacina = self.radacina

		def citeste():
			# 0.7.9 (UNF9): cu trecerea pe feedul unic (sau intoarcerea), cand stare.json o cere
			return stare_cu_feedul_unic(radacina, canal, baza, credentiale), fara_retea(radacina)

		def gata(rez, eroare):
			if generatie != self._generatie_cautare or self.faza != 'caut':
				return
			if eroare or rez is None:
				return self._cautare_gata({'stare': EROARE, 'eroare': curata(eroare)})
			(stare, cod, baza_dupa, nota), fara = rez
			if nota:
				self._jurnal('feedul: %s' % nota)
			if baza_dupa != baza:
				# sursele s-au rescris: opkg update si verificarea listelor merg pe feedul cel nou
				self._adresa, self._baza_feed = adresa_stare(canal, baza_dupa), baza_dupa
				surse[:] = [s for s in canalul(radacina)[1] if s[3] == baza_dupa]
			if cod == FARA_RASPUNS and fara:
				return self._cautare_gata({'stare': FARA_RETEA})
			if cod:
				return self._cautare_gata({'stare': cod, 'eroare': curata(stare.get('eroare'))})
			# semnat, dar pentru alt canal (de pilda o publicare de proba data receptoarelor de pe canalul public)
			if stare.get('canal') and stare.get('canal') != canal:
				return self._cautare_gata({'stare': NESEMNATA, 'eroare': 'stare.json e al canalului %s, nu %s' % (
					curata(stare.get('canal')), canal)})
			self._opkg_update(stare, surse)
		self._lucrare(citeste, gata)
		return True

	def _opkg_update(self, stare, surse):
		from Components.Ipkg import IpkgComponent
		self.pas, self.progres = _t('Se descarcă lista pachetelor (opkg update)...'), (2, 3)
		self._schimbat()
		self._lista_ipkg = []
		ipkg = self._ipkg = IpkgComponent()
		generatie = self._generatie_cautare
		inceput = time.time()

		def eveniment(e, param):
			if generatie != self._generatie_cautare or self.faza != 'caut' or self._ipkg is not ipkg:
				return
			if e == IpkgComponent.EVENT_LINE:
				if isinstance(param, str) and param.startswith(P.PREFIX_NOTA):
					# OPK1: a skipped dead source or the wait for another opkg, shown as the step on the screen
					self.pas = curata(param[len(P.PREFIX_NOTA):])
					self._schimbat()
				else:
					self._lista_ipkg.append(curata(param))
				self._jurnal(param)
			elif e == IpkgComponent.EVENT_DONE:
				ipkg.removeCallback(eveniment)
				self._ipkg = None
				self._dupa_update(stare, surse, param, inceput)
		ipkg.addCallback(eveniment)
		# listele de acum, ca sa le punem la loc daca feedul se republica in timpul descarcarii (_dupa_update)
		pastreaza_listele(self.radacina)
		self._jurnal('opkg update')
		ipkg.startCmd(IpkgComponent.CMD_UPDATE)

	def _dupa_update(self, stare, surse, cod, inceput, rezerva_verificata=False):
		generatie = self._generatie_cautare
		if cod and not rezerva_verificata and not self._rezerva_incercata:
			# Aceeasi decizie ca in Extensii; citirea si schimbarea sursei raman in fundal.
			self._rezerva_incercata = True
			linii, radacina = list(self._lista_ipkg), self.radacina

			def verifica_rezerva():
				if generatie != self._generatie_cautare or self.faza != 'caut':
					return False
				from Components import HdsPluginuriExterne
				return HdsPluginuriExterne.dupa_update(linii, radacina)

			def dupa_rezerva(reia, eroare):
				if generatie != self._generatie_cautare or self.faza != 'caut':
					return
				if reia and not eroare:
					self._jurnal('reincerc opkg update dupa trecerea feedului extern pe rezerva')
					return self._opkg_update(stare, surse)
				if eroare:
					self._jurnal('rezerva feedului extern: %s' % curata(eroare))
				self._dupa_update(stare, surse, cod, inceput, rezerva_verificata=True)
			self._lucrare(verifica_rezerva, dupa_rezerva)
			return
		# opkg update da cod 255 si cand cade numai o sursa a utilizatorului: conteaza listele feedului nostru
		conf = P.citeste_configurarea(self.radacina)
		dosar = _cale(self.radacina, conf.lists_dir)
		proaspete = []
		for nume, _a, _arh, _b in surse:
			try:
				proaspete.append(os.path.getmtime(os.path.join(dosar, nume)) >= inceput - 2)
			except OSError:
				proaspete.append(False)
		if not proaspete or not all(proaspete):
			motiv = motiv_eroare(self._lista_ipkg, implicit=_t('Lista pachetelor nu s-a putut descărca.'))
			return self._cautare_gata({'stare': EROARE if not fara_retea(self.radacina) else FARA_RETEA,
				'eroare': curata(motiv)})
		self.pas, self.progres = (_t(TEXT_REPARA_CAUT) + '...') if self.repara else _t('Se compară pachetele...'), (3, 3)
		self._schimbat()
		radacina = self.radacina
		canal, adresa, baza = self.canal, self._adresa, self._baza_feed
		repara = self.repara

		def calculeaza():
			c = P.citeste_configurarea(radacina)
			semnata = stare
			# listele descarcate de opkg trebuie sa fie chiar cele din stare.json semnat (indexuri)
			g = verifica_listele(radacina, surse, semnata, c)
			stari = [stare]
			if g:
				# publicarea s-a putut schimba intre stare.json si opkg update: stare.json (semnat) se cere inca o data
				noua, cod = descarca_stare(adresa, citeste_netrc(radacina) if canal == 'proba' else None)
				if cod is None and noua.get('canal') in (None, canal):
					stari.append(noua)
					if not verifica_listele(radacina, surse, noua, c):
						semnata, g = noua, []
			if g:
				# 0.7.5 (FED): listele se pun la loc pe cele semnate de dinainte (copia din _opkg_update), nu se sterg;
				# amprentele tinute minte ale acestei baze sunt si ele dintr-un stare.json semnat
				tinute = _amprente_tinute(radacina)
				if tinute.get('canal') == canal and tinute.get('baza') == baza:
					stari.append(tinute)
				sterse, puse = pune_la_loc_sau_sterge(radacina, surse, stari, c)
				return {'stare': NESEMNATA, 'eroare': curata('; '.join(g[:3])), 'sterse': sterse, 'puse_la_loc': puse}, None
			tine_minte_indexurile(radacina, canal, baza, semnata)
			return rezultat_din_liste(radacina, surse, semnata, c, repara=repara), semnata

		def gata(rez, eroare):
			if generatie != self._generatie_cautare or self.faza != 'caut':
				return
			if rez and not eroare:
				rezultat, semnata = rez
				if rezultat.get('stare') == NESEMNATA and 'puse_la_loc' in rezultat:
					sterse, puse = rezultat.pop('sterse'), rezultat.pop('puse_la_loc')
					self._jurnal('listele nu sunt cele semnate (%s); puse la loc cele de dinainte: %s; sterse: %s' % (
						rezultat.get('eroare'), ', '.join(puse) or '-', ', '.join(sterse) or '-'))
					if self._reincearca_cautarea(rezultat):
						return
				self._semnat = {'stare': semnata} if semnata is not None else None
				return self._cautare_gata(rezultat)
			self._cautare_gata({'stare': EROARE, 'eroare': curata(eroare)})
		self._lucrare(calculeaza, gata)

	def _reincearca_cautarea(self, rezultat):
		"""0.7.5 (FED): listele nu s-au potrivit cu stare.json semnat (feedul se republica chiar acum, de obicei): o
		singura data pe cautare, cautarea intreaga se reia dupa REINCERCARE_LISTE_MS, cu listele semnate de dinainte pe
		disc; pana atunci se vede pasul, nu "nesemnata". False cand s-a reincercat deja sau nu se poate programa."""
		if self._reincercare_liste:
			return False
		fabrica = self.fabrica_ceas
		if fabrica is None:
			try:
				from enigma import eTimer as fabrica
			except ImportError:
				return False

		def acum():
			self._ceas_liste = None
			self.faza = 'liber'
			if not self.cauta():
				# nu s-a putut porni (alt opkg lucreaza): ramane rezultatul primei incercari
				self._cautare_gata(rezultat)
		t = fabrica()
		try:
			self._legatura_liste = t.timeout.connect(acum)
		except AttributeError:
			t.callback.append(acum)
		self._ceas_liste = t
		self._reincercare_liste = True
		self.pas = _t('Lista pachetelor se schimbă chiar acum pe server. Se reîncearcă în mai puțin de un minut...')
		self._jurnal('reincerc cautarea peste %d s' % (REINCERCARE_LISTE_MS // 1000))
		self._schimbat()
		t.start(REINCERCARE_LISTE_MS, True)
		return True

	def _cautare_gata(self, rezultat):
		self._reincercare_liste = False
		rezultat.setdefault('cautat_la', int(time.time()))
		self.rezultat = rezultat
		self.faza, self.pas, self.progres = 'liber', '', (0, 0)
		# motivul unei cautari esuate intra si el in jurnal (adresa fara nume si parola, curata); fara el, din jurnalul unui
		# tester se vedea numai „cautare: eroare”
		eroare = rezultat.get('eroare')
		self._jurnal('cautare: %s%s' % (rezultat.get('stare'), (' (%s)' % curata(eroare)[:200]) if eroare else ''))
		if rezultat.get('status'):
			# enigma2-hdsatelit nu e instalat in status-ul opkg: starea lui si marimea status-ului, pentru cine citeste
			# jurnalul trimis
			self._jurnal('pachetul principal: %s' % curata(rezultat['status'])[:200])
		self._schimbat()
		if self.rapid:
			self._rapid_dupa_cautare(rezultat)

	# ---- instalarea
	def instaleaza(self, actualizare=None):
		"""Instaleaza planul cautarii: pachetele se descarca si se verifica aici (marimea si sha256 din stare.json semnat,
		descarca_pachete), apoi `opkg install <fisier>`. `actualizare` (numarul intern al publicarii, trimis de pagina
		web odata cu versiunea pe care o arata) trebuie sa fie cel din rezultat, ca o pagina veche din browser sa nu
		instaleze altceva decat a vazut."""
		motiv = self.poate_porni()
		r = self.rezultat
		if not motiv and not r.get('poate_instala'):
			motiv = _t('Nu este nimic de instalat sau actualizarea nu se poate instala din meniu.')
		if not motiv and actualizare is not None and actualizare != (r.get('server') or {}).get('actualizare'):
			motiv = _t('Starea s-a schimbat între timp. Caută din nou.')
		nume = [p['nume'] for p in r.get('pachete') or [] if P.nume_valid(p['nume'])]
		from Components.Ipkg import opkgArguments
		if not motiv and (not nume or opkgArguments('upgrade', nume) is None):
			motiv = _t('Un nume de pachet nu este valid. Nu se instalează.')
		if motiv:
			self.mesaj = motiv
			self._schimbat()
			return False
		intrari, problema = pachete_semnate(self._semnat, r)
		if not problema:
			problema = pachete_straine(intrari, P.citeste_configurarea(self.radacina).arhitecturi)
		if problema:
			self._jurnal('instalare refuzata: %s' % problema)
			self.mesaj = ''
			self.rezultat = dict(r, stare=NESEMNATA, poate_instala=False, eroare=curata(problema))
			self._schimbat()
			return False
		self.mesaj = _t(TEXT_INSTALARE)
		self._de_instalat = list(r.get('pachete') or [])
		self.faza, self.pas, self.progres = 'instalez', _t('Se descarcă și se verifică pachetele...'), (0, len(nume))
		self._lista_ipkg = []
		self._schimbat()
		canal = self.canal
		credentiale = citeste_netrc(self.radacina) if canal == 'proba' else None
		adresa = '%s/%s/%s' % (ADRESA_FEED, canal, self._baza_feed)
		# pentru jurnalul trimis de testeri: ce se instaleaza peste ce, pe ce imagine si canal
		img = imaginea(self.radacina)
		self._jurnal('actualizarea %s (publicarea %s, canalul %s) peste %s, imaginea de baza %s' % (
			(r.get('server') or {}).get('versiune') or '?', (r.get('server') or {}).get('actualizare'), canal,
			img.get('versiune') or '?', img.get('baza') or '?'))
		# pachetele ramase neconfigurate de dinainte (None = nu se stie): numai ele pot fi motivul unui cod opkg nenul
		# dupa o instalare a carei pachete au toate versiunea noua
		try:
			self._neconfigurate_inainte = P.pachete_neconfigurate(self.radacina)
		except Exception as e:
			self._neconfigurate_inainte = None
			self._jurnal('pachetele neconfigurate nu se pot citi: %s' % curata(e))
		if self._neconfigurate_inainte:
			self._jurnal('pachete neconfigurate in receptor (opkg le configureaza din nou la sfarsit): %s' %
				', '.join(self._neconfigurate_inainte))
		self._jurnal('descarc si verific: %s' % ' '.join('%s %s' % (x['nume'], x['versiune']) for x in intrari))
		# 0.7.8 (RPR8): pachetele reinstalate pentru fisierele sterse si ce lipsea din ele
		rep = r.get('reparatie') or {}
		reparate = [n for n in rep.get('pachete') or [] if n in nume]
		# numai cele reinstalate cu aceeasi versiune pastreaza fisierele ocrotite (cele actualizate primesc fisierele noi)
		reinstalate = [n for n in rep.get('reinstalate') or [] if n in nume]
		self._ocrotite = None
		self._repara_principal = PACHET_PRINCIPAL in reinstalate
		if reparate:
			self._jurnal('repara imaginea: pun la loc %s (reinstalate: %s); lipseau %s fisiere: %s' % (', '.join(reparate),
				', '.join(reinstalate) or '-', rep.get('numar'),
				', '.join(c for n in reparate for c in (rep.get('lipsa') or {}).get(n, [])[:10])))
		radacina = self.radacina

		def descarca():
			_nevoie, problema = verifica_loc_radacina(self._semnat, r, radacina)
			if problema:
				return None, problema
			rez = descarca_pachete(intrari, adresa, credentiale)
			if reinstalate and rez[1] is None:
				# setarile din /etc ale pachetelor reinstalate si reparatiile de proba raman cum sunt (dupa opkg se pun inapoi)
				self._ocrotite = copiaza_ocrotite(radacina, P.citeste_configurarea(radacina), reinstalate)
			return rez

		def gata(rez, eroare):
			cai, problema = rez if rez and not eroare else (None, ('descarcare', curata(eroare)))
			if problema:
				return self._descarcare_cazuta(problema, nume)
			if self._ocrotite is not None:
				self._jurnal('repara imaginea: %d fisiere ocrotite (din /etc si ale probelor), %d .pyc lipsa raman lipsa' % (
					len(self._ocrotite['copii']), len(self._ocrotite['pyc'])))
			self._porneste_opkg(cai, nume)
		self._lucrare(descarca, gata)
		return True

	def _descarcare_cazuta(self, problema, nume):
		"""Pachetele nu ajung la opkg: unul nu e cel semnat (NESEMNATA), nu incap sau nu s-au descarcat"""
		fel, detaliu = problema
		goleste_dosarul()
		if self._ocrotite is not None:
			# opkg nu a pornit: copiile fisierelor ocrotite nu mai trebuie
			pune_inapoi_ocrotite(self._ocrotite, self.radacina)
			self._ocrotite = None
		self._jurnal('pachetele nu se instaleaza (%s): %s' % (fel, detaliu))
		self.faza, self.pas, self.progres = 'liber', '', (0, 0)
		if fel == 'nesemnat':
			self.mesaj = ''
			self.rezultat = dict(self.rezultat, stare=NESEMNATA, poate_instala=False, eroare=curata(detaliu))
		else:
			motiv = _text_refuz_loc(fel)
			self.rezultat = dict(self.rezultat, stare='eroare-instalare', poate_instala=False, ramase=list(nume))
			self.mesaj = text_eroare_instalare(motiv)
		self._sfarsit_rapid('pachetele nu s-au instalat (%s)' % fel)
		self._schimbat()

	def _porneste_opkg(self, cai, nume):
		"""opkg install pe pachetele verificate (fisierele din DOSAR_PACHETE)"""
		from Components.Ipkg import IpkgComponent
		if any(p.get('reinstaleaza') for p in self._de_instalat or []):
			argumente = argumente_instalare(cai, reinstaleaza=True)
		else:
			argumente = argumente_instalare(cai)
		if argumente is None:
			return self._descarcare_cazuta(('descarcare', 'opkg nu primeste pachetele descarcate'), nume)
		try:
			from Components import HdsLimbaRestaurare
			# Inainte sa dispara vreun pachet, retine ce avea omul.
			HdsLimbaRestaurare.pastreaza(self.radacina, HdsLimbaRestaurare._aleasa())
		except Exception as e:
			return self._descarcare_cazuta(('descarcare', 'Limba nu se poate pastra: %s' % e), nume)
		try:
			from Components import HdsParteaDoua
			if HdsParteaDoua.citesteConf(self.radacina) and HdsParteaDoua.radacinaNand(self.radacina):
				self._partea_doua_lacat = HdsParteaDoua.ocupaOperatia(self.radacina)
				if self._partea_doua_lacat is None:
					return self._descarcare_cazuta(('descarcare', _t('Partea a doua de pe stick este in lucru.')), nume)
			self._partea_doua_detasa = HdsParteaDoua.detaseazaPentruBaza(self.radacina)
		except ImportError:
			pass
		except Exception as e:
			try:
				HdsParteaDoua.dupaActualizareaBazei(self.radacina, actualizeaza=False)
			except Exception as eroare:
				self._jurnal('refacerea legaturilor spre stick: %s' % eroare)
			self._elibereaza_lacatul_partii_doua()
			return self._descarcare_cazuta(('descarcare', 'Legaturile spre stick nu se pot detasa: %s' % e), nume)
		self.pas = _t('Se pregătește instalarea...')
		self._schimbat()
		self._inlocuite = None
		self._verifica_si_ruleaza_opkg(cai, nume, argumente, a_doua=False)

	def _verifica_si_ruleaza_opkg(self, cai, nume, argumente, a_doua):
		"""Citeste listele in fundal si verifica radacina inaintea fiecarei incercari."""
		semnat, radacina = self._semnat, self.radacina
		plan = {'pachete': [dict(p) for p in self._de_instalat]}

		def gata(rez, eroare):
			_necesar, problema = rez if rez and not eroare else (None, ('loc-necunoscut', curata(eroare)))
			if problema:
				return self._refuz_loc_inainte_opkg(problema, nume, a_doua)
			self._ruleaza_opkg(cai, nume, argumente, a_doua)
		self._lucrare(lambda: verifica_loc_radacina(semnat, plan, radacina), gata)

	def _ruleaza_opkg(self, cai, nume, argumente, a_doua):
		"""Ruleaza opkg cu argumentele date; la sfarsit verifica instalarea (_dupa_instalare) sau, o singura data, cand
		opkg cere sa coboare un pachet strain la versiunea din feedul HD Satelit, ruleaza din nou aceleasi pachete
		verificate cu --force-downgrade (_incearca_coborarea). Semnul instalarii in curs si al paznicului raman intre
		cele doua incercari."""
		from Components.Ipkg import IpkgComponent
		ipkg = self._ipkg = IpkgComponent()
		facute = set()
		self._lista_ipkg = []

		def eveniment(e, param):
			if e == IpkgComponent.EVENT_LINE:
				self._lista_ipkg.append(curata(param))
				self._jurnal(param)
				fel, text = P.linie_jurnal(curata(param))
				# pasul arata numai ce face opkg (se instaleaza, se configureaza); o eroare (si a altui pachet din
				# receptor) ramane in jurnal, iar rezultatul il spune mesajul de la sfarsit
				if text and fel == 'pas':
					self.pas = curata(text)
				m = re.match(r'^(?:Upgrading|Installing|Configuring) (\S+?)\.?(?:\s|$)', param or '')
				if m and m.group(1) in nume and param.startswith('Configuring'):
					facute.add(m.group(1))
				self.progres = (len(facute), len(nume))
				self._schimbat()
			elif e == IpkgComponent.EVENT_DONE:
				ipkg.removeCallback(eveniment)
				self._ipkg = None
				# opkg a cerut sa coboare versiunea unui pachet: poate e un pachet strain peste numele unui pachet HD
				# Satelit (downgrade_straine); semnele raman pana se hotaraste a doua incercare. Nu si dupa un semnal: atunci
				# fisierele pot fi amestecate, iar semnul trebuie sa ramana (mai jos)
				if not a_doua and param != 0 and not oprit_de_semnal(param) and downgrade_cerute(self._lista_ipkg):
					return self._incearca_coborarea(cai, nume, param)
				# opkg a iesit singur: rezultatul il spune verificarea de mai jos, deci semnul nu mai trebuie. Oprit de un
				# semnal din afara (oprit_de_semnal): semnul ramane, programul de la pornire termina actualizarea.
				if oprit_de_semnal(param):
					self._sfarsit_opkg(pastreaza_semnul=param)
				else:
					self._sfarsit_opkg()
				self._dupa_instalare(param)
		ipkg.addCallback(eveniment)
		if not a_doua:
			self._inceput_opkg()
		self._jurnal('opkg %s' % ' '.join(argumente))
		ipkg.setCurrentCommand(IpkgComponent.CMD_INSTALL)
		try:
			ipkg.runCmd(argumente)
		except Exception as e:
			ipkg.removeCallback(eveniment)
			self._ipkg = None
			self._sfarsit_opkg()
			self._refa_legaturile_partii_doua()
			self._elibereaza_lacatul_partii_doua()
			self._partea_doua_detasa = False
			return self._descarcare_cazuta(('descarcare', curata(e)), nume)

	def _refuz_loc_inainte_opkg(self, problema, nume, a_doua):
		"""Reface legaturile si elibereaza lacatele inclusiv dupa a doua incercare."""
		if a_doua:
			self._sfarsit_opkg()
			self._jurnal('a doua incercare oprita: %s' % problema[1])
			# Prima incercare poate sa fi schimbat pachete; pastreaza rezultatul ei.
			return self._dupa_instalare(255, refuz_spatiu=problema[0])
		self._refa_legaturile_partii_doua()
		self._elibereaza_lacatul_partii_doua()
		self._partea_doua_detasa = False
		return self._descarcare_cazuta(problema, nume)

	def _incearca_coborarea(self, cai, nume, cod):
		"""opkg a iesit cu `cod` si a cerut o coborare de versiune: pe un fir, se verifica in listele semnate ale feedului
		ca toate coborarile sunt pachete straine duse la versiunea HD Satelit (downgrade_straine); atunci aceleasi pachete
		verificate se instaleaza din nou cu --force-downgrade, altfel rezultatul primei incercari ramane"""
		radacina = self.radacina
		linii = list(self._lista_ipkg)

		def calculeaza():
			conf = P.citeste_configurarea(radacina)
			_canal, surse, _baza = canalul(radacina, conf)
			return downgrade_straine(linii, pachete_din_feed(radacina, surse, conf), instalate(radacina, conf),
				conf.arhitecturi)

		def gata(rez, eroare):
			inlocuite, motiv = rez if rez and not eroare else (None, curata(eroare))
			argumente = None
			if inlocuite:
				argumente = argumente_instalare(cai, reinstaleaza=any(p.get('reinstaleaza') for p in self._de_instalat or []),
					downgrade=True)
				if argumente is None:
					motiv = 'opkg nu primeste pachetele descarcate'
			if not argumente:
				self._jurnal('fara a doua incercare: %s' % motiv)
				self._sfarsit_opkg()
				return self._dupa_instalare(cod)
			self._inlocuite = inlocuite
			self._jurnal('pachete puse din alt feed peste numele unor pachete HD Satelit, cu versiunea mai mare: %s; '
				'a doua incercare cu --force-downgrade' % ', '.join('%s %s -> %s' % x for x in inlocuite))
			self.pas = _t('Se pregătește instalarea...')
			self._schimbat()
			self._verifica_si_ruleaza_opkg(cai, nume, argumente, a_doua=True)
		self._lucrare(calculeaza, gata)

	def _inceput_opkg(self):
		"""Inainte de opkg: semnul pe memoria interna (tools/hds-actualizare-intrerupta.py termina la pornire o instalare
		oprita) si semnul "ocupat" al paznicului (nu reporneste interfata, pragul lung la blocajele de nucleu)"""
		if not scrie_semnul_in_curs((self.rezultat.get('server') or {}).get('versiune'), self._de_instalat, self.radacina):
			self._jurnal('semnul instalarii in curs nu se poate scrie')
		if getattr(self, '_repara_principal', False):
			# 0.7.8 (RPR8): opkg (eConsoleAppContainer) mosteneste mediul interfetei; preinst-ul il citeste
			os.environ[MEDIU_REPARA] = '1'
			self._jurnal('repara imaginea: enigma2-hdsatelit cu aceeasi versiune, probele raman')
		try:
			from Components import HdsPaznic
			HdsPaznic.ocupat(CHEIE_PAZNIC, HdsPaznic.MOTIV_ACTUALIZARE, DURATA_PAZNIC_S)
		except Exception as e:
			print('[HdsActualizari] paznicul: %r' % (e,))

	def _sfarsit_opkg(self, pastreaza_semnul=None):
		"""Paznicul e liber. Semnul instalarii in curs se scoate, afara de cazul in care opkg a fost oprit de un semnal
		(pastreaza_semnul = codul lui): atunci ramane pentru tools/hds-actualizare-intrerupta.py."""
		os.environ.pop(MEDIU_REPARA, None)
		self._repara_principal = False
		if pastreaza_semnul:
			self._jurnal('opkg oprit de semnalul %d (nu a iesit singur): semnul instalarii ramane; actualizarea se '
				'termina la urmatoarea pornire a interfetei' % (pastreaza_semnul - 128))
		else:
			sterge_semnul_in_curs(self.radacina)
		try:
			from Components import HdsPaznic
			HdsPaznic.liber(CHEIE_PAZNIC)
		except Exception as e:
			print('[HdsActualizari] paznicul: %r' % (e,))

	def _refa_legaturile_partii_doua(self):
		if self._partea_doua_detasa:
			try:
				from Components import HdsParteaDoua
				return HdsParteaDoua.dupaActualizareaBazei(self.radacina, actualizeaza=False)
			except Exception as e:
				self._jurnal('refacerea legaturilor spre stick: %s' % curata(e))

	def _elibereaza_lacatul_partii_doua(self):
		if self._partea_doua_lacat is not None:
			try:
				from Components import HdsParteaDoua
				HdsParteaDoua.elibereazaOperatia(self._partea_doua_lacat)
			finally:
				self._partea_doua_lacat = None

	def _dupa_instalare(self, cod, refuz_spatiu=None):
		radacina = self.radacina
		planificate = self._de_instalat
		inainte = self._neconfigurate_inainte
		# 0.7.8 (RPR8): ce lipsea din pachetele reinstalate pentru fisierele sterse si copiile fisierelor ocrotite
		rep = self.rezultat.get('reparatie') or {}
		lipsa_rep = dict((n, (rep.get('lipsa') or {}).get(n, [])) for n in rep.get('pachete') or []
			if n in [p['nume'] for p in planificate])
		ocrotite, self._ocrotite = self._ocrotite, None

		def verifica():
			# setarile din /etc si reparatiile de proba inapoi chiar si dupa un opkg cazut
			inapoi = None
			if ocrotite is not None:
				try:
					inapoi = pune_inapoi_ocrotite(ocrotite, radacina)
				except Exception as e:
					inapoi = curata(e)
			# status-ul opkg si fisierele noi pe eMMC inainte de orice repornire: o repornire dura (watchdogul, curentul)
			# chiar dupa opkg lasa altfel un status vechi sau gol, iar dupa ea cautarea spunea "la zi" pe versiunea
			# veche (09.11.2026, darog69, Ustym)
			try:
				os.sync()
			except (AttributeError, OSError):
				pass
			conf = P.citeste_configurarea(radacina)
			inst = instalate(radacina, conf)
			reparatie = None
			if lipsa_rep:
				try:
					reparatie = verifica_reparatia(radacina, conf, lipsa_rep, inst) + (inapoi,)
				except Exception as e:
					reparatie = ([], [], curata(e))
			elif inapoi is not None:
				reparatie = ([], [], inapoi)
			ramase = [p['nume'] for p in planificate if inst.get(p['nume']) != p['la']]
			try:
				straine = [n for n in P.pachete_neconfigurate(radacina, conf) if n not in ramase]
			except Exception:
				straine = None
			parte2 = (True, '')
			if self._partea_doua_detasa:
				try:
					from Components import HdsParteaDoua
					parte2 = HdsParteaDoua.dupaActualizareaBazei(radacina, actualizeaza=not ramase,
						lacat=self._partea_doua_lacat)
				except Exception as e:
					parte2 = (False, curata(e))
			return ramase, straine, parte2, reparatie

		def gata(rez, eroare):
			ramase, straine, parte2, reparatie = rez if rez and not eroare else (None, None, (False, ''), None)
			nota_rep = ''
			if reparatie is not None:
				puse, nepuse, inapoi = reparatie
				self._jurnal('repara imaginea: fisiere ocrotite puse inapoi: %s' % (inapoi if inapoi is not None else '-'))
				if lipsa_rep:
					self._jurnal('repara imaginea: puse la loc %d (%s); lipsesc inca %d (%s)' % (len(puse),
						', '.join(puse[:20]) or '-', len(nepuse), ', '.join(nepuse[:20]) or '-'))
					nota_rep = text_reparatie(puse, nepuse)
			# Chiar si verificarea status-ului poate esua dupa o instalare partiala.
			self._refa_legaturile_partii_doua()
			self._elibereaza_lacatul_partii_doua()
			self._partea_doua_detasa = False
			# un pachet ramas neconfigurat ACUM, care nu era asa inainte (o dependinta adusa de instalare, al carei
			# postinst a cazut), e o greseala a instalarii, nu un pachet strain
			noi = None if straine is None or inainte is None else [n for n in straine if n not in inainte]
			straine = straine or []
			goleste_dosarul()
			# pachetele descarcate de opkg (dependintele din feed) nu mai trebuie: cache-ul e in RAM (0.6.6)
			try:
				n = P.curata_cache(radacina)
				if n:
					self._jurnal('cache opkg: %s pachete sterse' % n)
			except Exception as e:
				self._jurnal('cache opkg: %s' % e)
			schimbat = len(ramase or []) < len(planificate)
			self.faza, self.progres = 'liber', (0, 0)
			# reusita = toate pachetele planului la versiunea noua (status-ul opkg) si, cand opkg nu iese cu 0, numai
			# pachete neconfigurate de dinainte: opkg iese cu 255 si cand cade numai configurarea altui pachet din
			# receptor (straine), ramas asa de la o instalare de dinainte, nu a actualizarii
			if eroare is None and ramase == [] and (cod == 0 or noi == []):
				self.pas = ''
				self.repornire = True
				self.rezultat = dict(self.rezultat, stare='instalata', poate_instala=False,
					avertismente=list(straine) if cod != 0 else [])
				self.mesaj = _t('Actualizarea s-a instalat. Interfața trebuie repornită ca să o folosească.')
				# 0.7.7 (DRV): driverul placii se incarca numai la pornirea receptorului
				drivere = [p['nume'] for p in planificate if p.get('driver_placii')]
				if drivere:
					scrie_semnul_driverului(drivere, radacina)
					self.mesaj = _t(TEXT_DRIVER_NOU)
					self._jurnal('driverul placii schimbat (%s): receptorul trebuie repornit' % ', '.join(drivere))
				if self._inlocuite:
					self.rezultat['inlocuite'] = [{'nume': n, 'de_la': d, 'la': l} for n, d, l in self._inlocuite]
					self.rezultat['nota_inlocuite'] = text_inlocuite(self._inlocuite)
					self.mesaj += ' ' + self.rezultat['nota_inlocuite']
				if not parte2[0]:
					self.mesaj += ' ' + _t('Partea a doua de pe stick nu s-a actualizat: %s') % parte2[1]
					self._jurnal('partea a doua: ' + parte2[1])
				if nota_rep:
					# 0.7.8 (RPR8): ce a pus la loc reparatia, si in fereastra de dinaintea repornirii
					self.rezultat['nota_reparatie'] = nota_rep
					self._nota_reparatie = nota_rep
					self.mesaj = nota_rep + ' ' + self.mesaj if self.repara else self.mesaj + ' ' + nota_rep
				if cod != 0:
					self._jurnal('opkg a iesit cu %s, dar toate pachetele actualizarii au versiunea noua: instalarea e '
						'reusita; pachete neconfigurate in receptor (nu ale actualizarii): %s' % (cod,
						', '.join(straine) or 'niciunul'))
					# nr. 105 (5), TODO 1094: "instalare: cod 255" vine din scriptul de instalare al unei extensii puse de om
					# (textele "No emu script to this image now", "Broken boxbranding ..." nu sunt in imagine si nici in
					# straturile OE), ramasa neconfigurata; opkg il ruleaza din nou la sfarsitul oricarei instalari. Omul
					# afla o data care extensie e, ca s-o scoata sau s-o puna din nou; actualizarea nu are nicio vina.
					if straine:
						nota = _t('Extensia %s nu se poate configura pe această imagine; nu ține de actualizare.') % \
							', '.join(P.nume_scurt(n) if n.startswith(P.PREFIX) else n for n in straine[:3])
						self.rezultat['nota_straine'] = nota
						self.mesaj += ' ' + nota
			else:
				motiv = _text_refuz_loc(refuz_spatiu) if refuz_spatiu else \
					motiv_eroare(self._lista_ipkg, implicit=_t('Instalarea nu a reușit.'))
				self.pas = ''
				# fisierele unor pachete s-au schimbat: interfata trebuie repornita oricum, inainte de alta operatie. opkg
				# oprit de un semnal nu si-a scris status-ul (pachetele par neschimbate), dar fisierele pot fi amestecate:
				# repornirea porneste intai programul care termina actualizarea (semnul a ramas)
				self.repornire = schimbat or oprit_de_semnal(cod)
				self.rezultat = dict(self.rezultat, stare='eroare-instalare', poate_instala=False,
					ramase=list(ramase or []))
				self.mesaj = text_eroare_instalare(motiv)
				if eroare is not None:
					self._jurnal('verificarea dupa opkg: %s' % curata(eroare))
				if noi:
					self._jurnal('pachete ramase neconfigurate dupa instalare (nu erau inainte): %s' % ', '.join(noi))
				vechi = [n for n in straine if n not in (noi or [])]
				if vechi:
					self._jurnal('pachete neconfigurate in receptor (nu ale actualizarii): %s' % ', '.join(vechi))
			self._jurnal('instalare: cod %s, ramase %s' % (cod, ramase))
			if self.rezultat.get('stare') == 'instalata':
				# 0.8.0 (AUT1): instalata singura (sau in standby): ce s-a schimbat se arata la prima folosire de dupa
				nota_dupa_instalare(self)
			if self.repornire:
				self._armeaza_repornirea_in_standby()
			if self.rapid:
				# numai dupa o instalare reusita; una cazuta (chiar cu repornirea ceruta) opreste modul rapid
				if self.rezultat.get('stare') == 'instalata':
					self.rapid_pas = 'repornesc'
					self.mesaj = _t(TEXT_DRIVER_NOU) if repornire_receptor_ceruta(radacina) else \
						_t('Actualizarea s-a instalat. Interfața se repornește acum.')
					if self.rezultat.get('nota_inlocuite'):
						self.mesaj += ' ' + self.rezultat['nota_inlocuite']
					if self.rezultat.get('nota_straine'):
						self.mesaj += ' ' + self.rezultat['nota_straine']
					if nota_rep:
						self.mesaj = nota_rep + ' ' + self.mesaj
					self._programeaza_repornirea(REPORNIRE_RAPIDA_MS)
				else:
					self._sfarsit_rapid('instalare: %s' % self.rezultat.get('stare'))
			elif self.rezultat.get('stare') == 'instalata':
				# 0.7.8 (RIA): si dupa o instalare pornita altfel (pagina web Instaleaza, ecranul fara pagina web)
				if self.porneste_repornirea('instalare'):
					# textul ca pe drumul modului rapid: driverul placii si notele instalarii (pachetele inlocuite,
					# extensia straina) nu se pierd sub textul repornirii
					if repornire_receptor_ceruta(radacina):
						self.mesaj = _t(TEXT_DRIVER_NOU)
					if self.rezultat.get('nota_inlocuite'):
						self.mesaj += ' ' + self.rezultat['nota_inlocuite']
					if self.rezultat.get('nota_straine'):
						self.mesaj += ' ' + self.rezultat['nota_straine']
			self._schimbat()
		self._lucrare(verifica, gata)

	# ---- actualizarea rapida (pagina web: butonul de actualizare rapida)
	def actualizeazaRapid(self, reporneste):
		"""Cauta; daca e o actualizare de instalat, o instaleaza (numarul publicarii gasite de cautare) si reporneste
		interfata cu reporneste(la_refuz), totul aici. reporneste intoarce 'pornita' (TryQuitMainloop deschis; la_refuz()
		e chemat daca nu reporneste, adica pe televizor s-a raspuns Nu), 'inregistrare', 'lucrare' sau 'intrebare'
		(repornirea ar intreba pe televizor: se incearca din nou la REINCERCARE_RAPIDA_MS) sau '' (nu se poate). False,
		cu mesajul, cand nu porneste: alta operatie in lucru, o actualizare instalata care asteapta repornirea, modul
		rapid deja pornit."""
		if self.rapid:
			self.mesaj = _t('Actualizarea rapidă este deja în lucru.')
			self._schimbat()
			return False
		self.rapid, self.rapid_pas, self._reporneste_rapid = True, 'caut', reporneste
		self._jurnal('actualizare rapida: caut')
		# cu lucrarile sincrone ale probelor, tot drumul se poate termina inainte sa se intoarca cauta(): dupa ea nu
		# se mai schimba nimic aici
		if not self.cauta():
			self._sfarsit_rapid('cautarea nu a pornit')
			self._schimbat()
			return False
		return True

	def reparaImaginea(self, reporneste, tot=False):
		"""0.7.8 (RPR8) „Repară imaginea” (ecranul, pagina web, operatia repara-actualizarea a asistentei): actualizarea
		rapida cu reparatia in plan (rezultat_din_liste, repara=True): cauta, reinstaleaza din feedul semnat pachetele cu
		fisiere sterse (si actualizarea, cand e una de instalat), spune ce a pus la loc si reporneste interfata cu
		numaratoarea obisnuita. Fara nimic de pus la loc: „Imaginea e întreagă.” (sau ce nu se poate pune la loc), fara
		instalare si fara repornire. tot=True (operatia repara-actualizarea a asistentei): si actualizarea gasita, ca inainte
		de RPR8 (actualizeazaRapid), plus fisierele lipsa. False, cu mesajul, cand nu porneste (ca actualizeazaRapid)."""
		if self.rapid:
			self.mesaj = _t('Actualizarea rapidă este deja în lucru.')
			self._schimbat()
			return False
		self.repara, self._nota_reparatie = 'tot' if tot else 'imagine', ''
		self._jurnal('repara imaginea: pornita%s' % (' (cu actualizarea, asistenta)' if tot else ''))
		if not self.actualizeazaRapid(reporneste):
			self.repara = ''
			return False
		return True

	def _rapid_dupa_cautare(self, rezultat):
		rep = rezultat.get('reparatie') or {}
		# operatia asistentei (repara='tot') si o actualizare ramasa la jumatate instaleaza planul intreg si fara fisiere lipsa
		de_instalat = rezultat.get('stare') == DISPONIBILA and rezultat.get('poate_instala') and \
			(self.repara == 'tot' or bool(rezultat.get('reinstalare')))
		if self.repara and rezultat.get('stare') in (LA_ZI, DISPONIBILA, IMAGINE_NOUA) and not rep.get('pachete') and \
				not de_instalat:
			# nimic de pus la loc din feedul semnat: nu se instaleaza nimic (nici o actualizare gasita intre timp)
			nepuse = [c for n in (rep.get('sarite') or []) + (rep.get('fara_feed') or [])
				for c in (rep.get('lipsa') or {}).get(n, [])]
			if rep.get('sarite'):
				self._jurnal('repara imaginea: sarite (pornirea, nucleul, driverele, bibliotecile de baza): %s' %
					', '.join(rep['sarite']))
			if rep.get('fara_feed'):
				self._jurnal('repara imaginea: nu sunt in feedul semnat cu aceeasi versiune: %s' % ', '.join(rep['fara_feed']))
			self.mesaj = text_reparatie((), nepuse) if nepuse else _t(TEXT_REPARA_INTREAGA)
			self.rapid_pas = 'nepusa' if nepuse else 'intreaga'
			self._jurnal('repara imaginea: %s' % ('lipsesc %d fisiere care nu se pot pune la loc: %s' % (len(nepuse),
				', '.join(nepuse[:20])) if nepuse else 'imaginea e intreaga'))
			self._sfarsit_rapid('repara imaginea: nimic de pus la loc')
			self._schimbat()
			return
		if self.repara and rep.get('sarite'):
			self._jurnal('repara imaginea: sarite (pornirea, nucleul, driverele, bibliotecile de baza): %s' %
				', '.join(rep['sarite']))
		if rezultat.get('stare') != DISPONIBILA or not rezultat.get('poate_instala'):
			self._sfarsit_rapid('cautare: %s' % rezultat.get('stare'))
			self._schimbat()
			return
		if self._automat and rezultat.get('repornire_receptor'):
			# 0.8.0 (AUT1): driverul placii cere repornirea receptorului intreg, iar dupa ea semnul intoarcerii in standby
			# (din /tmp) se pierde: receptorul ar porni treaz noaptea. Singur nu se instaleaza; ramane anuntul.
			self._sfarsit_rapid('actualizarea automata: driverul placii cere repornirea receptorului, ramane anuntul')
			self._schimbat()
			return
		self.rapid_pas = 'instalez'
		if not self.instaleaza((rezultat.get('server') or {}).get('actualizare')):
			self._sfarsit_rapid('instalarea nu a pornit')
			self._schimbat()

	def _sfarsit_rapid(self, motiv):
		"""Modul rapid se opreste, fara repornire; rapid_pas ramane"""
		if self.rapid:
			self._jurnal('actualizare rapida oprita: %s' % motiv)
		self.rapid, self._reporneste_rapid = False, None
		self.repara = ''
		self._automat = False
		if self._ceas_rapid is not None:
			self._ceas_rapid.stop()

	def _programeaza_repornirea(self, ms):
		"""Un singur ceas pentru repornire, pastrat aici (pornit din nou si din chemarea lui)"""
		if self._ceas_rapid is None:
			fabrica = self.fabrica_ceas
			if fabrica is None:
				from enigma import eTimer as fabrica
			t = fabrica()
			try:
				self._legatura_rapid = t.timeout.connect(self._incearca_repornirea)
			except AttributeError:
				t.callback.append(self._incearca_repornirea)
			self._ceas_rapid = t
		self._ceas_rapid.stop()
		self._ceas_rapid.start(int(ms), True)

	def _incearca_repornirea(self, fara_fereastra=False):
		if not self.rapid or self._fereastra is not None:
			return
		# 0.7.8 (RIA): intai motivele de asteptare pe care functia de repornire nu le vede (timeshift, alt opkg); treaz,
		# fereastra dinaintea repornirii (numaratoarea sau, pe Nu, intrebarea), care cheama din nou cu fara_fereastra
		motiv = motiv_asteptare(self.sesiunea(), self.radacina)
		if motiv:
			self._asteapta(motiv)
			self._schimbat()
			return
		if not fara_fereastra and self._fereastra_inainte():
			self._schimbat()
			return
		# in standby: semnul intoarcerii in standby (fara el interfata noua pornea treaza dupa o asteptare de inregistrare);
		# treaz: fara el, si cand l-a pus actualizarea pornita din standby (HdsImagineOnline._feed_in_standby), iar omul a
		# trezit receptorul intre timp si a vazut numaratoarea (altfel interfata noua s-ar intoarce singura in standby)
		if e_in_standby():
			semn = _scrie_semnul_standby()
		else:
			semn = None
			_sterge_semnul_standby(_cale_semnului_standby())
		f = self._reporneste_rapid

		def la_refuz(*a):
			_sterge_semnul_standby(semn)
			self._repornire_refuzata(*a)
		try:
			rez = f(la_refuz) if f is not None else ''
		except Exception as e:
			print('[HdsActualizari] repornirea rapida: %s' % e)
			rez = ''
		if rez != 'pornita':
			_sterge_semnul_standby(semn)
		if rez == 'pornita':
			self.rapid_pas = 'repornesc'
			self.mesaj = ((self._nota_reparatie + ' ') if self._nota_reparatie else '') + \
				_t('Actualizarea s-a instalat. Interfața se repornește acum.')
			try:
				# cu memoria decodorului farmitata repornirea a fost a receptorului intreg (HdsMemorieDriver)
				from Components import HdsMemorieDriver
				if HdsMemorieDriver.ultimulCod() == HdsMemorieDriver.COD_RECEPTOR:
					self.mesaj = HdsMemorieDriver.textRepornire(HdsMemorieDriver.COD_RECEPTOR)
			except Exception:
				pass
			self._jurnal('actualizare rapida: repornesc interfata')
		elif rez in TEXTE_ASTEPTARE:
			self._asteapta(rez)
		else:
			self._sfarsit_rapid('repornirea nu s-a putut porni')
			self.mesaj = _t('Actualizarea s-a instalat. Interfața trebuie repornită ca să o folosească.')
		self._schimbat()

	def _asteapta(self, motiv):
		"""Repornirea asteapta (TEXTE_ASTEPTARE): textul in ecran si web, din nou la REINCERCARE_RAPIDA_MS; 0.7.8 (RIA): la
		un motiv nou, o data, si pe televizor (treaz, nu peste o intrebare deschisa)"""
		nou = motiv != self.rapid_pas
		if nou:
			self._jurnal('actualizare rapida: repornirea asteapta (%s)' % motiv)
		self.rapid_pas = motiv
		self.mesaj = _t(TEXTE_ASTEPTARE[motiv])
		if nou and motiv != 'intrebare' and not e_in_standby():
			s = self.sesiunea()
			if s is not None:
				try:
					from Screens.MessageBox import MessageBox
					s.open(MessageBox, self.mesaj, type=MessageBox.TYPE_INFO, timeout=ANUNT_S,
						title=_t('Actualizare software'))
				except Exception as e:
					self._jurnal('anuntul asteptarii: %s' % curata(e))
		self._programeaza_repornirea(REINCERCARE_RAPIDA_MS)

	# ---- 0.7.8 (RIA): repornirea singura dupa orice actualizare instalata (vezi NUMARATOARE_S)
	def sesiunea(self):
		"""Sesiunea enigma2 pentru ferestrele de pe televizor; None pe PC (probele dau self.sesiune)"""
		return self.sesiune if self.sesiune is not None else _sesiune_globala()

	def porneste_repornirea(self, motiv, reporneste=None):
		"""Dupa o actualizare instalata altfel decat prin modul rapid (motiv: 'instalare', 'extensii'): acelasi drum ca
		pasul de repornire al modului rapid (pagina web il urmareste la fel). True cand a pornit; False cand modul rapid e
		deja in lucru sau nu e nicio functie de repornire (atunci ramane ce era: butonul, intrebarea, plasa din standby)."""
		if self.rapid:
			return False
		f = reporneste or _reporneste_implicit(self.sesiunea)
		if f is None:
			return False
		self.repornire = True
		if not self._standby_armat:
			# plasa HB7 pentru o repornire refuzata (Nu, EXIT); dupa Actualizare software e deja armata
			self._armeaza_repornirea_in_standby()
		self.rapid, self.rapid_pas, self._reporneste_rapid = True, 'repornesc', f
		self.mesaj = _t('Actualizarea s-a instalat. Interfața se repornește acum.')
		self._jurnal('repornirea singura dupa actualizare (%s)' % motiv)
		self._programeaza_repornirea(REPORNIRE_RAPIDA_MS)
		self._schimbat()
		return True

	def _fereastra_inainte(self):
		"""Treaz, cu sesiune: numaratoarea (Da) sau intrebarea (Nu) inaintea repornirii; True cand s-a deschis. In standby
		sau fara sesiune (probele vechi): False, repornirea merge mai departe ca pana acum."""
		if e_in_standby():
			return False
		s = self.sesiunea()
		if s is None:
			return False
		cod = _cod_repornire(s)
		try:
			from Screens.MessageBox import MessageBox
			# 0.7.8 (RPR8): deasupra, ce a pus la loc reparatia
			nota = self._nota_reparatie + '\n' if self._nota_reparatie else ''
			if repornire_singura():
				text = nota + _text_repornire(cod)
				self.rapid_pas, self.mesaj = 'repornesc', text
				# titlul ecranului (tradus) in locul lui "Mesaj": omul vede de unde vine repornirea
				self._fereastra = s.openWithCallback(self._dupa_numaratoare, MessageBox, text, type=MessageBox.TYPE_INFO,
					timeout=NUMARATOARE_S, title=_t('Actualizare software'))
				self._jurnal('actualizare rapida: numaratoarea de %s s inainte de repornire' % NUMARATOARE_S)
			else:
				intrebare = _t('Repornești receptorul acum?') if cod == 2 else _t('Repornești interfața acum?')
				self.rapid_pas, self.mesaj = 'intrebare', _t(TEXTE_ASTEPTARE['intrebare'])
				self._fereastra = s.openWithCallback(self._dupa_intrebare, MessageBox, nota + _t('Actualizarea s-a instalat.') +
					'\n' + intrebare, type=MessageBox.TYPE_YESNO, default=True, title=_t('Actualizare software'))
				self._jurnal('actualizare rapida: intreb pe televizor (repornirea singura e oprita din setari)')
		except Exception as e:
			self._fereastra = None
			self._jurnal('fereastra dinaintea repornirii: %s' % curata(e))
			return False
		if self._fereastra is None:
			# un openWithCallback fara fereastra intoarsa (probele) tine locul cu un semn
			self._fereastra = True
		return True

	def _dupa_numaratoare(self, raspuns=None, *_a):
		"""OK sau timpul trecut: repornirea acum (motivele de asteptare se verifica din nou). EXIT: ca Nu la intrebare
		(rapid_pas 'refuzata', pe care il cunoaste si postinst-ul lui enigma2-hdsatelit): repornirea ramane pentru
		urmatoarea intrare in standby (plasa HB7, armata la instalare), fara alta fereastra."""
		self._fereastra = None
		if not self.rapid:
			return
		if raspuns is False:
			self._jurnal('actualizare rapida: numaratoarea oprita pe televizor (EXIT)')
			self._repornire_refuzata()
			return
		self._incearca_repornirea(fara_fereastra=True)

	def _dupa_intrebare(self, da=None, *_a):
		self._fereastra = None
		if not self.rapid:
			return
		if not da:
			self._repornire_refuzata()
			return
		self._incearca_repornirea(fara_fereastra=True)

	def _repornire_refuzata(self, *_a):
		"""TryQuitMainloop s-a inchis fara repornire: pe televizor s-a raspuns Nu"""
		if not self.rapid:
			return
		self._sfarsit_rapid('repornirea refuzata pe televizor')
		self.rapid_pas = 'refuzata'
		self.mesaj = _t('Repornirea a fost refuzată pe televizor. Actualizarea se folosește după ce repornești interfața.')
		self._schimbat()

	# ---- 0.7.8 (HB7): interfata ramasa nerepornita dupa instalare se reporneste in standby
	def _armeaza_repornirea_in_standby(self):
		"""Dupa o instalare care cere repornirea: la fiecare intrare in standby (o singura legatura pe pornire), cat
		repornirea e inca ceruta, ceasul ei porneste. Instalata chiar in standby (HdsImagineOnline._feed_in_standby): ceasul
		porneste acum; modul rapid reporneste oricum mai devreme, iar ceasul il lasa in pace (_repornire_in_standby)."""
		if not self._standby_armat:
			try:
				from Components.config import config
				config.misc.standbyCounter.addNotifier(self._la_standby, initial_call=False)
				self._standby_armat = True
			except Exception as e:
				self._jurnal('repornirea in standby: %s' % curata(e))
		if e_in_standby():
			self._programeaza_standby(STANDBY_REPORNIRE_MS)

	def _la_standby(self, *_a):
		if self.repornire:
			self._programeaza_standby(STANDBY_REPORNIRE_MS)

	def _programeaza_standby(self, ms):
		if self._ceas_standby is None:
			fabrica = self.fabrica_ceas
			if fabrica is None:
				from enigma import eTimer as fabrica
			t = fabrica()
			try:
				self._legatura_standby = t.timeout.connect(self._repornire_in_standby)
			except AttributeError:
				t.callback.append(self._repornire_in_standby)
			self._ceas_standby = t
		self._ceas_standby.stop()
		self._ceas_standby.start(int(ms), True)

	def _repornire_in_standby(self):
		"""Ceasul de standby: interfata nerepornita dupa o actualizare se reporneste aici si se intoarce in standby.
		Trezit intre timp: nimic (urmatoarea intrare in standby porneste din nou ceasul)."""
		if not self.repornire or not e_in_standby():
			return
		# 0.7.8 (RIA): modul rapid cu fereastra dinaintea repornirii lasata deschisa sub standby (omul a intrat in standby in
		# timpul numaratorii sau al intrebarii): ceasul de standby reporneste el, fara mesaj
		if self.ocupat() or (self.rapid and self._fereastra is None):
			self._programeaza_standby(STANDBY_REINCERCARE_MS)
			return
		f = self.reporneste_standby or reporneste_din_standby
		try:
			rez = f()
		except Exception as e:
			self._jurnal('repornirea in standby: %s' % curata(e))
			rez = ''
		if rez == 'pornita':
			self._jurnal('actualizarea instalata asteapta repornirea: repornesc interfata in standby')
		elif rez in TEXTE_ASTEPTARE:
			self._jurnal('repornirea in standby asteapta (%s)' % rez)
			self._programeaza_standby(STANDBY_REINCERCARE_MS)
		else:
			self._jurnal('repornirea in standby nu s-a putut porni')

	# ---- pentru ecran si web
	def stare_publica(self):
		"""Starea ca dict JSON (pagina web si probele): fara adrese, fara parole"""
		img = self._imaginea_publica()
		return {
			'faza': self.faza,
			'pas': self.pas,
			'progres': list(self.progres),
			'canal': self.canal if self.canal else canalul(self.radacina)[0],
			'imagine': img,
			'imagine_text': img['versiune'] or img['baza'] or '',
			'rezultat': self.rezultat,
			'text_stare': _t(TEXTE_STARE.get(self.rezultat.get('stare'), '')) if self.rezultat.get('stare') in
				TEXTE_STARE else '',
			'mesaj': self.mesaj,
			'repornire': self.repornire,
			# 0.7.7 (DRV): driverul placii instalat asteapta repornirea receptorului (nu numai a interfetei)
			'repornire_receptor': bool(self.repornire and repornire_receptor_ceruta(self.radacina)),
			# rezultatul unei actualizari oprite la jumatate, terminate (sau nu) la pornire
			'reparare': self.reparare,
			'rapid': self.rapid,
			'rapid_pas': self.rapid_pas,
			# 0.7.8 (RPR8): „Repară imaginea” in lucru si rezultatul ultimei reparatii (FISIER_REPARA, ramane dupa repornire)
			'repara': self.repara,
			'reparatie_ultima': citeste_reparatia(self.radacina).get('ultima'),
			'zilnic': zilnic_pornit(),
			# 0.8.0 (AUT1)
			'automat': automat_pornit(),
			'jurnal': self.jurnal[-30:],
		}


actualizari = Actualizari()


# ---- 0.7.8 (HB7): repornirea interfetei ramase nerepornite dupa instalare (vezi STANDBY_REPORNIRE_MS)
def e_in_standby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


def _repornire_sigura(sesiune, la_refuz=None):
	"""Repornirea pe calea modului rapid (Plugins/Extensions/HdsWebControl/actualizari_web.reporneste_rapid): 'pornita',
	de ce asteapta ('inregistrare', 'lucrare', 'intrebare') sau '' cand nu se poate."""
	from Plugins.Extensions.HdsWebControl.actualizari_web import reporneste_rapid
	return reporneste_rapid(lambda: sesiune)(la_refuz or (lambda *_a: None))


def reporneste_din_standby():
	"""Din standby: semnul intoarcerii in standby (HdsImagineOnline.dupa_pornire il citeste la pornire), apoi repornirea
	sigura; semnul se scoate cand repornirea nu porneste."""
	from Screens import Standby
	sesiune = getattr(Standby.inStandby, 'session', None)
	if sesiune is None:
		return ''
	from Components import HdsImagineOnline as I
	cale = os.path.join(I._rad(), I.STANDBY_DUPA_REPORNIRE.lstrip('/'))
	try:
		with open(cale, 'w') as f:
			f.write('1\n')
	except (IOError, OSError):
		pass

	def sterge(*_a):
		try:
			os.remove(cale)
		except OSError:
			pass
	rez = _repornire_sigura(sesiune, sterge)
	if rez != 'pornita':
		sterge()
	return rez


def reporneste_dupa_ecran_cazut(sesiune, nume='', repornire=None):
	"""mytest.py (handleScreenCrash): un ecran care nu s-a putut deschide cat o actualizare instalata asteapta repornirea
	(fisierele noi de pe disc nu se potrivesc cu modulele vechi din memorie). True = tratat aici: repornirea a pornit sau
	asteapta o inregistrare, o lucrare ori o intrebare (mesajul ei, deja tradus); False = ca pana acum."""
	a = actualizari
	if not a.repornire or a.ocupat():
		return False
	try:
		rez = (repornire or _repornire_sigura)(sesiune)
	except Exception as e:
		a._jurnal('repornirea dupa ecranul cazut: %s' % curata(e))
		return False
	a._jurnal('ecranul %s a cazut cu actualizarea instalata si interfata nerepornita: repornirea %s' %
		(nume, rez or 'nu a pornit'))
	if rez == 'pornita':
		return True
	if rez in TEXTE_ASTEPTARE:
		a.mesaj = _t(TEXTE_ASTEPTARE[rez])
		try:
			from Screens.MessageBox import MessageBox
			sesiune.open(MessageBox, a.mesaj, type=MessageBox.TYPE_INFO, timeout=8)
		except Exception:
			pass
		a._schimbat()
		return True
	return False


def cere_repornirea_imaginii(motiv=''):
	"""0.7.8 (CM3): programul imaginii (enigma2-hdsatelit) s-a schimbat pe disc sub interfata care ruleaza pe alt drum
	decat actualizarea din meniu (o extensie care il trage, cu ecranul inchis inainte de repornire sau din pagina web; un
	panou strain care instaleaza si reciteste pluginurile; asistenta; linia de comanda): aceeasi stare ca dupa o
	actualizare instalata. Repornirea e ceruta (ecranul si pagina web o arata si o ofera, nicio alta instalare pana atunci),
	interfata se reporneste singura in standby si dupa un ecran cazut (HB7). Din Components/PluginComponent.py si
	Components/HdsExtensiiLucru.reincarcaPluginuri. True cand starea s-a pus acum. Nu arunca."""
	a = actualizari
	try:
		if a.repornire:
			return False
		a.repornire = True
		if not a.mesaj:
			a.mesaj = _t(TEXT_IMAGINE_SCHIMBATA)
		a._jurnal('programul imaginii s-a schimbat pe disc sub interfata (%s): interfata trebuie repornita' % curata(motiv))
		a._armeaza_repornirea_in_standby()
		# 0.7.8 (RIA): si aici repornirea singura de dupa o actualizare instalata (treaz fereastra cu numaratoarea sau, pe
		# Repornire singura = Nu, intrebarea; asteptarea dupa inregistrare, timeshift sau alt opkg; in standby fara mesaj).
		# Nu cat merge o cautare sau o instalare din Actualizare software: sfarsitul ei porneste repornirea. Fara functia de
		# repornire (fara pagina web) sau cu modul rapid deja pornit ramane starea de mai sus.
		if a.faza == 'liber':
			a.porneste_repornirea('imagine')
		a._schimbat()
		return True
	except Exception as e:
		print('[HdsActualizari] repornirea dupa schimbarea programului imaginii: %r' % (e,))
		return False


# ---------------------------------------------------------------- verificarea zilnica (numai anunta)

def text_anunt(stare, img, baza_feed=None):
	"""Textul anuntului zilnic, sau None cand nu e nimic nou de spus; cheia lui (anuntat o singura data). O versiune
	e noua cand e mai mare (ca la opkg) decat versiunea care ruleaza. baza_feed: a adreselor (feedul unic, motiv_baza)."""
	if motiv_baza(stare, baza_feed or img['baza'], img['baza']) == 'baza' or not img['versiune']:
		return None, None
	v = versiunea_receptorului(stare, img.get('arhitecturi'))
	if imagine_noua_pentru(stare, img.get('arhitecturi')):
		cheie = '%s/%s/imagine' % (stare['baza'], v)
		return _t('Actualizare software: pentru noutățile HD Satelit trebuie pusă imaginea nouă de la zero. Detalii '
			'în Actualizare software.'), cheie
	if P.compara_versiuni(v, img['versiune']) > 0:
		cheie = '%s/%s' % (stare['baza'], v)
		return _t('Actualizare software: este disponibilă versiunea %s. O instalezi din Actualizare software.') % v, cheie
	return None, None


def text_anunt_driver(stare, radacina='/', conf=None):
	"""0.7.7 (DRV): anuntul zilnic pentru driverul placii, cand versiunea e deja la zi (driverul vine la cautarea de dupa
	instalarea lui 0.7.7, fara versiune noua); (text, cheie) sau (None, None). Status-ul opkg se citeste numai cand
	stare.json are un driver pe arhitecturile receptorului."""
	drv = drivere_din_stare(stare)
	if not drv:
		return None, None
	conf = conf or P.citeste_configurarea(radacina)
	if conf.arhitecturi and not any(e['arhitectura'] in conf.arhitecturi for e in drv):
		return None, None
	plan = planul_driverelor(stare, instalate(radacina, conf), conf.arhitecturi, radacina)
	if not plan:
		return None, None
	return _t(TEXT_DRIVER_DISPONIBIL), '%s/%s/drivere/%s' % (stare.get('baza'), versiunea_starii(stare),
		','.join(sorted('%s=%s' % (x['nume'], x['la']) for x in plan)))


def _acum():
	"""Ora de acum (probele de pe PC dau alta)"""
	return time.time()


def _monoton():
	"""Ceasul monoton (ora corectata la pornire nu-l strica); probele dau altul"""
	try:
		return time.monotonic()
	except AttributeError:
		return time.time()


# 0.8.0 (AUT1): ultima tasta (orice tasta, ascultator inaintea tuturor hartilor, care nu opreste nimic) si mesajul de dupa
# o instalare automata, cat asteapta prima tasta
_TASTE = {'ultima': _monoton(), 'legat': False, 'nota': None, 'ceas': None, 'legatura': None}
# prioritatea ascultatorului: langa cea a protectiei ecranului (Screens/ScreenSaver.py, Components/HdsOprireAutomata.py)
PRIO_TASTE = -0x7FFFFFFF


def leaga_tastele():
	"""Ascultatorul tastelor (o singura data pe pornire); fara enigma (PC) nimic"""
	if _TASTE['legat']:
		return
	try:
		from enigma import eActionMap
		eActionMap.getInstance().bindAction('', PRIO_TASTE, _tasta)
		_TASTE['legat'] = True
	except Exception as e:
		print('[HdsActualizari] tastele: %r' % (e,))


def _tasta(key, flag):
	"""Tine minte ora; cu un mesaj de dupa o instalare automata in asteptare, il arata la NOTA_DUPA_TASTA_MS (ca trezirea
	din standby sa se termine). Nu opreste tasta (0)."""
	_TASTE['ultima'] = _monoton()
	if _TASTE['nota'] is not None:
		try:
			if _TASTE['ceas'] is None:
				from enigma import eTimer
				t = eTimer()
				try:
					_TASTE['legatura'] = t.timeout.connect(arata_nota_automata)
				except AttributeError:
					t.callback.append(arata_nota_automata)
				_TASTE['ceas'] = t
			_TASTE['ceas'].start(NOTA_DUPA_TASTA_MS, True)
		except Exception as e:
			print('[HdsActualizari] mesajul actualizarii automate: %r' % (e,))
	return 0


def fara_taste_de():
	"""Secundele de la ultima tasta (sau de la pornire)"""
	return max(0, _monoton() - _TASTE['ultima'])


def noaptea(acum=None):
	"""True intre ORE_NOAPTE (ora locala), numai cu ceasul pus (anul cel putin AN_MINIM)"""
	t = time.localtime(_acum() if acum is None else acum)
	return t.tm_year >= AN_MINIM and ORE_NOAPTE[0] <= t.tm_hour < ORE_NOAPTE[1]


def instalare_automata_posibila(a=None):
	"""Actualizarile automate pornite si drumul actualizarii rapide disponibil (functia de repornire a paginii web)"""
	a = a or actualizari
	return automat_pornit() and _reporneste_implicit(a.sesiunea) is not None


def tine_minte_asteptarea(cheie):
	"""Ora la care versiunea `cheie` a fost vazuta prima data (numai cu ceasul pus), in config: ramane peste reporniri"""
	try:
		c = config_actualizari().asteptare
		if (c.value or '').split(' ')[0] == cheie:
			return
		acum = _acum()
		if time.localtime(acum).tm_year < AN_MINIM:
			return
		c.value = '%s %d' % (cheie, int(acum))
		c.save()
	except Exception as e:
		print('[HdsActualizari] asteptarea actualizarii automate: %r' % (e,))


def asteapta_de_prea_mult():
	"""True cand versiunea de instalat singura asteapta de mai mult de ASTEPTARE_MAX_S (prilejul nu vine)"""
	try:
		cheie, cand = config_actualizari().asteptare.value.split(' ')
		v = _verificare[0] if _verificare else None
		if v is not None and v.de_instalat and v.de_instalat != cheie:
			return False
		return _acum() - int(cand) > ASTEPTARE_MAX_S
	except Exception:
		return False


def fereastra_feed_ascunsa():
	"""0.8.0 (AUT1): Components/HdsImagineOnline nu mai deschide treaz fereastra pentru o versiune din feed (ar intreba):
	o instaleaza actualizarile automate. Fereastra revine cand instalarea singura a cazut pentru versiunea aceea sau
	asteapta de prea mult (asteapta_de_prea_mult). Fereastra pentru o imagine noua ramane."""
	try:
		if not instalare_automata_posibila():
			return False
		v = _verificare[0] if _verificare else None
		if v is not None and v.cazuta:
			return False
		return not asteapta_de_prea_mult()
	except Exception:
		return False


def text_nota_automata(versiune, randuri):
	"""„Am actualizat receptorul la versiunea 0.8.1:” si cel mult MAX_RANDURI_NOTA randuri din noutati, cu buline"""
	randuri = [r for r in randuri or [] if r][:MAX_RANDURI_NOTA]
	if not randuri:
		return _t('Am actualizat receptorul la versiunea %s.') % versiune
	return _t('Am actualizat receptorul la versiunea %s:') % versiune + '\n' + '\n'.join(u'• %s' % r for r in randuri)


def scrie_nota_automata(versiune, server, radacina='/', limba=None):
	"""Semnul de dupa o instalare automata: versiunea si primele randuri din noutatile instalate (in limba receptorului),
	scris atomic pe memoria interna (ramane dupa repornire). True cand s-a scris."""
	randuri = []
	for _v, rs in noutati(server or {}, limba):
		randuri.extend(rs)
		if len(randuri) >= MAX_RANDURI_NOTA:
			break
	d = {'versiune': curata(versiune or ''), 'randuri': [curata(r) for r in randuri[:MAX_RANDURI_NOTA]],
		'cand': int(_acum())}
	cale = _cale(radacina, FISIER_NOTA_AUTOMATA)
	try:
		dosar = os.path.dirname(cale)
		if not os.path.isdir(dosar):
			os.makedirs(dosar)
		with open(cale + '.nou', 'w', encoding='utf-8') as f:
			json.dump(d, f, ensure_ascii=False)
			f.flush()
			os.fsync(f.fileno())
		os.replace(cale + '.nou', cale)
		return True
	except Exception as e:
		print('[HdsActualizari] semnul actualizarii automate: %r' % (e,))
		return False


def nota_dupa_instalare(a, versiune=None):
	"""Din _dupa_instalare, la o instalare reusita: semnul mesajului cand a pornit-o actualizarea automata sau cand
	receptorul e in standby (nu se uita nimeni). True cand s-a scris."""
	automata, a._automat = a._automat, False
	if not automata and not e_in_standby():
		return False
	server = (a.rezultat or {}).get('server') or {}
	v = versiune or server.get('versiune') or ''
	if not v:
		return False
	a._jurnal('actualizarea %s instalata singura; ce s-a schimbat se arata la prima folosire' % v)
	return scrie_nota_automata(v, server, a.radacina)


def pregateste_nota_automata(radacina='/'):
	"""La pornire: semnul de dupa o instalare automata asteapta prima tasta (receptorul treaz). True cand e unul."""
	try:
		with open(_cale(radacina, FISIER_NOTA_AUTOMATA), 'r', encoding='utf-8') as f:
			d = json.load(f)
		v = curata(d.get('versiune') or '')
		randuri = [curata(r) for r in d.get('randuri') or [] if isinstance(r, str)]
	except (IOError, OSError, ValueError, AttributeError, TypeError):
		return False
	if not v:
		return False
	_TASTE['nota'] = (radacina, text_nota_automata(v, randuri))
	leaga_tastele()
	return True


def arata_nota_automata(radacina=None):
	"""Mesajul scurt de dupa instalarea automata (AddPopup cu timp, nu blocheaza nimic), o singura data, numai treaz;
	in standby asteapta urmatoarea tasta. Dupa el semnul se sterge."""
	nota = _TASTE['nota']
	if nota is None or e_in_standby():
		return False
	_TASTE['nota'] = None
	rad, text = nota
	try:
		os.remove(_cale(radacina or rad, FISIER_NOTA_AUTOMATA))
	except OSError:
		pass
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, NOTA_S, 'HdsActualizariAutomate')
	except Exception as e:
		print('[HdsActualizari] mesajul actualizarii automate: %r' % (e,))
	return True


class VerificareZilnica(object):
	"""La 5 minute dupa pornire si apoi o data pe zi, numai cu internetul activ: stare.json al canalului; un anunt
	pentru fiecare actualizare noua (o singura data). Nu porneste opkg. Din 0.8.0 (AUT1), cu Actualizari automate
	pornite, o versiune noua din feed se tine minte (de_instalat) si se instaleaza singura cand receptorul e in standby
	sau noaptea, nefolosit (_incearca_auto)."""

	def __init__(self, radacina='/'):
		from enigma import eTimer
		self.radacina = radacina
		self.ceas = eTimer()
		self.ceas_auto = eTimer()
		try:
			self._legatura = self.ceas.timeout.connect(self.verifica)
			self._legatura_auto = self.ceas_auto.timeout.connect(self._incearca_auto)
		except AttributeError:
			self.ceas.callback.append(self.verifica)
			self.ceas_auto.callback.append(self._incearca_auto)
		self._lucrare = None
		# pauza de dupa o cadere a serverului (cu ruta implicita), dublata la fiecare cadere
		self._pauza = 0
		self._fara_retea = False
		# cheia versiunii de instalat singura (ca la anuntat); cea a ultimei incercari cazute si ora ei (o noua incercare
		# abia dupa REINCERCARE_AUTO_S, ca o cadere de retea noaptea sa nu opreasca actualizarea singura pentru totdeauna)
		self.de_instalat = None
		self.cazuta = None
		self.cazuta_la = 0

	def porneste(self, intarziere=PRIMA_VERIFICARE):
		self.ceas.startLongTimer(int(intarziere))

	def _fara_internet(self):
		"""Fara ruta implicita: nimic cerut, nimic anuntat, din nou la FARA_RETEA_S (o citire din /proc)"""
		if not self._fara_retea:
			self._fara_retea = True
			print('[HdsActualizari] verificarea zilnica: fara internet; reiau cand vine')
		self.porneste(FARA_RETEA_S)

	def verifica(self):
		self.ceas.stop()
		if not zilnic_pornit():
			return self.porneste(ZI)
		canal, _surse, baza_feed = canalul(self.radacina)
		if canal not in ('proba', 'public'):
			return self.porneste(ZI)
		if fara_retea(self.radacina):
			return self._fara_internet()
		self._fara_retea = False
		img = imaginea(self.radacina)
		credentiale = citeste_netrc(self.radacina) if canal == 'proba' else None
		baza = baza_feed or img['baza']
		radacina = self.radacina
		# 0.7.9 (UNF9): trecerea pe feedul unic (sau intoarcerea) numai cat nu lucreaza alt opkg sau o cautare de aici
		muta = actualizari.faza == 'liber' and not opkg_ocupat(radacina)
		from Components.HdsPazaModel import LucrareFundal

		def gata(rez, eroare):
			self._lucrare = None
			stare, cod, baza_dupa, nota = rez if rez and not eroare else ({}, EROARE, baza, '')
			if nota:
				actualizari._jurnal('verificarea zilnica, feedul: %s' % nota)
			if not cod and stare.get('canal') and stare.get('canal') != canal:
				stare, cod = {'eroare': 'stare.json e al canalului %s' % curata(stare.get('canal'))}, NESEMNATA
			if cod == FARA_RASPUNS:
				# 0.8.0 (AUT1): internetul a plecat intre timp, sau ruta e, dar internetul nu (serverul nu raspunde)
				if fara_retea(self.radacina):
					return self._fara_internet()
				self._pauza = min(REINCERCARE, self._pauza * 2 if self._pauza else PAUZA_SERVER_S)
				print('[HdsActualizari] verificarea zilnica: %s; reiau peste %d s' % (curata(stare.get('eroare')) or cod,
					self._pauza))
				return self.porneste(self._pauza)
			if cod:
				print('[HdsActualizari] verificarea zilnica: %s' % (curata(stare.get('eroare')) or cod))
				return self.porneste(REINCERCARE)
			self._pauza = 0
			tine_minte_indexurile(self.radacina, canal, baza_dupa, stare)
			text, cheie = text_anunt(stare, img, baza_dupa)
			c = config_actualizari()
			# o versiune noua are fereastra ei pe ecranul obisnuit (Components/HdsImagineOnline.py); ramane anuntul pentru
			# imaginea noua, cand lista imaginilor nu are una pentru acest receptor
			imagine_noua = imagine_noua_pentru(stare, img.get('arhitecturi'))
			# 0.8.0 (AUT1): o versiune noua din feed se instaleaza singura (fara anunt si fara sa intrebe), o singura
			# incercare pe pornire; dupa una cazuta (sau cu actualizarile automate oprite) ramane anuntul de azi
			self.de_instalat = None
			if self.cazuta and (cheie != self.cazuta or _acum() - self.cazuta_la >= REINCERCARE_AUTO_S):
				self.cazuta = None
			if text and cheie and not imagine_noua and cheie != self.cazuta and instalare_automata_posibila():
				self.de_instalat = cheie
				text = None
				tine_minte_asteptarea(cheie)
				actualizari._jurnal('actualizarea automata: versiunea noua (%s) se instaleaza singura in standby sau '
					'noaptea' % cheie)
				self.ceas_auto.start(AUTO_CEAS_S * 1000, True)
			if FEREASTRA_ACTIVA and not imagine_noua:
				text = None
			if not text and not imagine_noua and not actualizari.repornire and not self.de_instalat:
				try:
					text, cheie = text_anunt_driver(stare, self.radacina)
				except Exception as e:
					print('[HdsActualizari] anuntul driverului: %r' % (e,))
					text, cheie = None, None
			if text and cheie != c.anuntat.value:
				c.anuntat.value = cheie
				c.anuntat.save()
				try:
					from Tools import Notifications
					from Screens.MessageBox import MessageBox
					Notifications.AddPopup(text, MessageBox.TYPE_INFO, 20, 'HdsActualizari')
				except Exception as e:
					print('[HdsActualizari] anuntul: %s' % e)
			self.porneste(ZI)
		self._lucrare = LucrareFundal(lambda: stare_cu_feedul_unic(radacina, canal, baza, credentiale, muta), gata)

	# ---- 0.8.0 (AUT1): instalarea singura
	def motiv_auto(self):
		"""De ce nu se instaleaza singura acum, sau '' cand se poate: alta lucrare, o actualizare care asteapta repornirea,
		o imagine care se scrie, o inregistrare (acum sau curand), timeshift, o intrebare deschisa (motiv_asteptare);
		apoi standby, sau noaptea fara taste de FARA_TASTE_S."""
		a = actualizari
		if a.rapid or a.ocupat() or a.repornire:
			return 'ocupat'
		try:
			if a.poate_porni():
				return 'ocupat'
		except Exception:
			return 'ocupat'
		try:
			from Components.HdsImagineOnline import imagine_online
			if imagine_online.ocupat():
				return 'imagine'
		except Exception:
			pass
		s = a.sesiunea()
		if s is None:
			return 'fara sesiune'
		m = motiv_asteptare(s, a.radacina)
		if m:
			return m
		if e_in_standby():
			return ''
		if not noaptea():
			return 'ziua'
		if fara_taste_de() < FARA_TASTE_S:
			return 'folosit'
		return ''

	def _incearca_auto(self):
		self.ceas_auto.stop()
		if not self.de_instalat or not automat_pornit():
			self.de_instalat = None
			return
		if self.motiv_auto():
			self.ceas_auto.start(AUTO_CEAS_S * 1000, True)
			return
		a = actualizari
		f = _reporneste_implicit(a.sesiunea)
		cheie, self.de_instalat = self.de_instalat, None
		if f is None:
			return
		a._jurnal('actualizarea automata: instalez %s (%s)' % (cheie, 'standby' if e_in_standby() else 'noaptea'))

		def cazuta(motiv):
			# fereastra si anuntul de azi revin pentru aceasta versiune (fereastra_feed_ascunsa); alta incercare peste o zi
			a._automat = False
			self.cazuta, self.cazuta_la = cheie, _acum()
			a._jurnal('actualizarea automata nu s-a instalat (%s); ramane anuntul' % motiv)

		def urmareste():
			if a.rapid or a.ocupat():
				return
			if urmareste in a.ascultatori:
				a.ascultatori.remove(urmareste)
			if (a.rezultat or {}).get('stare') != 'instalata':
				cazuta((a.rezultat or {}).get('stare'))
		a.ascultatori.append(urmareste)
		a._automat = True
		try:
			pornita = a.actualizeazaRapid(f)
		except Exception as e:
			print('[HdsActualizari] actualizarea automata: %r' % (e,))
			pornita = False
		if not pornita:
			if urmareste in a.ascultatori:
				a.ascultatori.remove(urmareste)
			cazuta('nu a pornit')


_verificare = []
FEREASTRA_ACTIVA = False


def arata_rezultatul_pornirii(radacina='/'):
	"""O actualizare oprita la jumatate, terminata (sau nu) la pornire de tools/hds-actualizare-intrerupta.py: textul
	ramane in mesajul actualizarilor (ecranul Actualizare software si pagina web) si apare o data pe televizor"""
	rez = rezultat_pornire(radacina)
	if rez is None:
		return None
	text = text_rezultat_pornire(rez)
	actualizari.reparare = dict(rez, text=text)
	actualizari.mesaj = text
	actualizari._jurnal('la pornire: actualizarea %s %s (%s)' % (rez.get('versiune') or '?', rez['stare'],
		rez.get('detaliu') or ''))
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO if rez['stare'] == 'terminata' else MessageBox.TYPE_ERROR, 30,
			'HdsActualizariPornire')
	except Exception as e:
		print('[HdsActualizari] rezultatul pornirii: %s' % e)
	return rez


def porneste():
	"""Din mytest.py, dupa ce s-a facut sesiunea: config-ul, rezultatul unei actualizari terminate la pornire si verificarea
	zilnica. Pornirea nu depinde de el."""
	config_actualizari()
	try:
		arata_rezultatul_pornirii()
	except Exception as e:
		print('[HdsActualizari] rezultatul pornirii: %r' % (e,))
	# 0.7.7 (DRV): driverul placii instalat la pornirea aceasta (interfata repornita, un Nu pe televizor) tot asteapta
	# repornirea receptorului: ecranul si pagina web o cer din nou
	try:
		if repornire_receptor_ceruta():
			actualizari.repornire = True
			actualizari.mesaj = _t(TEXT_DRIVER_NOU)
	except Exception as e:
		print('[HdsActualizari] driverul placii: %r' % (e,))
	if not _verificare:
		v = VerificareZilnica()
		_verificare.append(v)
		v.porneste()
	# 0.8.0 (AUT1): ultima tasta (noaptea se instaleaza numai pe un receptor nefolosit) si mesajul de dupa o instalare
	# automata, aratat la prima tasta
	try:
		leaga_tastele()
		pregateste_nota_automata()
	except Exception as e:
		print('[HdsActualizari] actualizarile automate: %r' % (e,))
	# 0.7.9 (UNF9): antetul numaratorii (si numarul instalarii, la prima pornire) pe un fir separat
	try:
		from Components.HdsPazaModel import LucrareFundal
		_LUCRARI_NUMARARE.append(LucrareFundal(antet_numarare, lambda rez, eroare: None))
	except Exception as e:
		print('[HdsActualizari] numaratoarea: %r' % (e,))

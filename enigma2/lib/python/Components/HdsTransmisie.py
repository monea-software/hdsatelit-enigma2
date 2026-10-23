# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTransmisie.py: transmisia canalelor spre browser (TV in browser, pagina web /tv). Ecranul de pe televizor: Meniu
# > Setari > Retea & Conexiuni > Transmisie in retea (Screens/HdsTransmisie.py); pereche web: HdsWebControl/tv_web.py.
#
# FLUXUL: TS-ul serviciului, fara recodare. Video H.264 (si HEVC, unde browserul il decodeaza) si sunetul canalului
# trec ca atare; mpegts.js le reimpacheteaza in browser. Imaginea MPEG-2 / MPEG-1 (si sunetul MP2 / MP3 / AC-3 al
# acelor canale) o decodeaza playerul wasm din pagina (HdsWebControl/hds-player.js, decodorul FFmpeg in WebAssembly),
# cand browserul il are (wasm=1 de la pagina): receptorul trimite acelasi flux, nimic in plus pe procesorul lui. Tunerul il ia o inregistrare enigma2 facuta direct cu
# eServiceCenter.record (alocarea obisnuita a canalului), scrisa intr-o teava a procesului (/proc/self/fd/N), nu pe
# disc: acelasi drum ca serverul local 8001 (Hds/DabT2/server8001.py). Un fir pe sesiune muta datele din teava in
# soclul browserului, pe pachete TS intregi, si rescrie PAT-ul si PMT-ul pentru mpegts.js (RescrierePsi: un singur
# program, imaginea si o singura pista audio pe care browserul o poate reda). Cat nu e legat niciun browser, firul
# citeste teava in gol (scrierea inregistrarii nu se blocheaza pe o teava plina), iar sesiunea se opreste singura dupa
# config.hds_transmisie.asteptare secunde; o reincarcare a paginii in acest timp gaseste sesiunea vie si nu deschide
# alta inregistrare.
#
# MEMORIA DRIVERULUI (masurat pe Amiko Viper 4K V20, HiSilicon): toti cei care inregistreaza pe acelasi demux impart
# un singur canal de inregistrare al driverului; cand se distruge, tamponul lui (DMX_RecBuf, 4 MB de adrese
# vmalloc) ramane neeliberat pana la repornirea receptorului. Paza demuxului (lib/dvb/hdspazademux.h, PID 0x000F) il
# tine intre sesiuni pe demuxurile 0 si 1: il face prima inregistrare de dupa pornirea enigma2 si se distruge o data, la
# iesirea ei (masurat pe receptor: o singura instanta, DMX_RecBuf neschimbat intre inregistrari).
# Cand vmalloc liber scade prea mult, decodorul video (cere ~17 MB dintr-o bucata) nu mai porneste. De aceea, si ca
# rezerva fara paza: la schimbarea canalului pe acelasi transponder inregistrarea
# noua porneste inainte ca cea veche sa se opreasca (canalul de inregistrare ramane deschis, nu se pierde nimic), iar
# o sesiune fara browser mai traieste `asteptare` secunde (o reincarcare a paginii o refoloseste). Oprirea nu
# elibereaza nimic, deci paza memoriei e la pornire: o sesiune noua se refuza cand dupa ea ar ramane sub
# sesiuni8001.PRAG_LIBER_KB liberi sau un gol mai mic de PRAG_GOL_KB, sau cand sesiuni8001.stare() cere repornirea.
# Fiecare inregistrare noua se numara in contorul comun cu releele DAB+ / DVB-T2 (sesiuni8001.noteaza).
#
# ANTENA CU MOTOR: o transmisie nu porneste
# nimic care cere alt transponder sau alta pozitie a antenei. Pe un receptor cu motor (USALS / DiSEqC 1.2) sau cu un
# singur tuner de satelit, un canal de satelit merge NUMAI de pe transponderul televizorului (in standby, al canalului
# de dinainte): inregistrarea imparte atunci canalul televizorului (eDVBResourceManager il refoloseste), deci nu se
# reacordeaza tunerul si nu pleaca nicio comanda spre motor (comenzile motorului pleaca numai dintr-o acordare, sec.cpp).
# Doua porniri noi (inregistrari noi) au intre ele cel putin PAUZA_COMUTARE_S: comutarile foarte rapide nu mai ajung la
# driver si la modulul de acces ca o rafala.
#
# CANALELE CRIPTATE: inregistrarea unui canal criptat face pe
# demuxul televizorului canale noi pentru PID-urile lui, iar programul de decriptare leaga cheia si pe ele; o oprire
# urmata repede de o pornire (record_stop, record_start dupa 11 s, cheia legata dupa inca 6 s) a blocat placa (12.10,
# fara paza: ultima oprire distrugea canalul de inregistrare, urmatoarea pornire il facea din nou). Cu paza demuxului
# (MEMORIA DRIVERULUI) canalul de inregistrare ramane, dar canalele noi pe PID-urile imaginii si sunetului si legarea
# cheii pe ele vin la fiecare sesiune; comutarile criptate rapide au fost probate pe receptor (pauza si varsta 0 s,
# 22 de sesiuni la 1-2 s, driverul curat), deci serializarea de mai jos ramane, dar cu implicite mici (varsta si
# pauza: setari ascunse, VARSTA_CRIPTAT_S si PAUZA_CRIPTAT_S). Criptatele se transmit
# numai cu setarea ascunsa config.hds_transmisie.criptate (implicit Da, dupa proba pe receptor; nu e pe televizor si nici in pagina) si numai
# serializat:
# - o sesiune criptata nu se opreste mai devreme de varsta (config.hds_transmisie.criptate_varsta, implicit
#   VARSTA_CRIPTAT_S) de la primele date: oprirea ceruta se amana (pentru
#   pagina sesiunea e oprita, inregistrarea mai merge, firul citeste teava in gol; ceasul face oprirea adevarata). Nu se
#   amana: cedeaza (televizorul sau o inregistrare cer tunerul), eroarea inregistrarii, firul incheiat, schimbarea pe un
#   canal de pe alt transponder;
# - nicio pornire criptata cat se amana o oprire si nici mai devreme de pauza (config.hds_transmisie.criptate_pauza,
#   implicit PAUZA_CRIPTAT_S) de la ultima oprire adevarata a unei transmisii criptate;
# - o comutare spre un canal criptat nu se suprapune cu o sesiune criptata (intai oprirea ei, apoi pauza); o sesiune
#   necriptata de pe acelasi transponder se opreste dupa pornire, ca pana acum;
# - cererea care trebuie sa astepte primeste CRIPTAT_ASTEAPTA si nu porneste nimic (secundeCriptat() = cat mai e):
#   pagina intreaba din nou numai pentru canalul ales ultimul, playerele externe asteapta in cerere (asteaptaCriptat;
#   una noua a aceleiasi chei o inlocuieste). Ultima cerere castiga: o sesiune criptata cu oprirea inca amanata se reia
#   daca acelasi browser cere din nou acelasi canal.
# Necriptatele merg ca inainte; oprirea lor nu porneste pauza pornirilor criptate (numai oprirea unei sesiuni criptate,
# sau a uneia aflate criptata dupa pornire, o porneste: _opresteInregistrarea).
#
# URMEAZA TELEVIZORUL: caseta live din panou (si "Vezi live" pe canalul televizorului) urmeaza ce merge pe televizor.
# Pagina tine deschisa o cerere lunga (tv_web /api/tv-urmeaza, urmaresteTv): extensia de zap (_laZap, chemata la
# inceputul fiecarui zap, din orice parte vine) o anunta pe firul principal, dupa zap; ceasul o anunta la standby si la
# termen (URMEAZA_S). Pagina porneste apoi canalul de ACUM al televizorului (tv_web: urmeaza=1). Nimic nu se opreste din
# pagina inaintea unui zap: pe aceeasi frecventa porneste intai inregistrarea noua (canalul de inregistrare al demuxului
# ramane deschis, iar o pornire criptata nu asteapta pauza), pe alta frecventa zap-ul elibereaza singur tunerul
# (cedeaza). Opririle au un cod pentru pagina (oprite: "zap", "standby", "fara_date", "nedecriptat" ...).
# "Vezi live" pe un canal pe care transmisia nu-l poate lua fara televizor (motor, un singur tuner de satelit):
# mutareTv spune daca televizorul poate trece pe el; zap-ul il face pagina canalelor (/api/canale-porneste).
#
# DECRIPTAREA: sesiunea unui canal criptat (sau al carei flux iese criptat) are `decriptare`: "asteapta" cat camul inca
# incearca, "merge" cand imaginea iese clara din inregistrare (bitii transport_scrambling_control ai imaginii, din
# RescrierePsi; firul sesiunii ii citeste si fara browser legat cat nu s-a hotarat), "nu" cand camul a raspuns definitiv
# ca nu poate (JurnalCam: "not found", "rejected", "no matching reader" pe SID-ul canalului, la doua cereri la cel putin
# REFUZ_CICLURI_S una de alta sau dupa REFUZ_TARZIU_S) sau nu raspunde deloc (DECRIPTARE_FARA_RASPUNS_S; cu raspunsuri
# nehotarate, cel mult DECRIPTARE_MAX_S; amandoua socotite dupa TERMENELE DECRIPTARII, de la zap-ul televizorului pe
# canal, cu DECRIPTARE_MIN_S de la primele date; o sesiune criptata fara niciun octet nu se mai opreste ca "fara_date").
# La "nu" sesiunea se opreste (cod "nedecriptat", TEXT_NEDECRIPTAT). Playerele
# externe primesc fluxul abia la "merge" (asteaptaDecriptarea); la "nu", refuzul cu textul.
# Imaginea nu e "clara" nici cand bitii de criptare sunt 0, dar inceputurile PES ale imaginii nu au 00 00 01 (pachete
# nedecriptate sau decriptate cu alta cheie; Chrome scrie atunci "packet_start_code_prefix"): RescrierePsi, CRIPTAT.
# ACEEASI VERIFICARE PE AMBELE CAI: "Vezi live" porneste de obicei un canal pe care televizorul l-a citit deja (canalCriptat
# = Da, "asteapta" de la pornire); pagina care urmeaza televizorul porneste canalul la 0,5-2 s dupa zap, cand PMT-ul
# televizorului n-a venit (sIsCrypted -1), accesul nu e tinut minte, iar lamedb il poate da FTA. Ceasul reciteste atunci
# canalCriptat() pentru sesiunea tanara fara decriptare (_criptatTarziu, pana la DECRIPTARE_FARA_RASPUNS_S de la primele
# date) si o trece pe "asteapta" ca la pornire; canal_criptat (amanarea opririi, serializarea) ramane cel de la pornire.
# Proba de noapte 13-14.10: FRANCE 2, DAZN 2, 13th Street, HISTORY, Cartoon Network stateau fara imagine si fara mesaj.
#
# LISTA DE CANALE SI SEMNUL: inregistrarea fiecarei sesiuni e marcata ca una care cedeaza la zap (setYieldsToZap,
# lib/dvb/hdscedare.h): lista de canale de pe televizor intreaba managerul de tunere ca pentru un zap si nu mai face gri
# canalele de pe alte frecvente numai din cauza transmisiei (la zap transmisia cedeaza, mai jos). O inregistrare
# adevarata nu e marcata: ce nu se poate porni din cauza ei ramane gri. Aceleasi inregistrari dau semnul "in retea"
# (transmise(), urmaresteTransmise): in lista de canale, in barele de informatii si in pagina canalelor din web.
#
# PRIORITATEA: televizorul si inregistrarile castiga. Navigation.playServiceExtensions si recordServiceExtensions
# (puse numai cat exista sesiuni): inainte de un zap sau de o inregistrare adevarata (nu verificarea unui
# temporizator) care nu poate lua un tuner, sesiunile de pe alt transponder se opresc pe loc (tunerul e liber cand se
# intoarce functia), iar pagina primeste motivul. Pe acelasi transponder nu se opreste nimic (tunerul e impartit).
#
# PLAYERELE EXTERNE PLECATE (aparatele din casa: Kodi, Emby, VLC): un player care inchide legatura nu se mai intoarce
# de obicei (oprit, alt canal cerut prin alta cerere). Sesiunea lui nu tine locul altora: de la EXTERN_PREDA_S fara
# legatura nu mai intra in limita de sesiuni (poateIncepe), iar o pornire care are nevoie de loc o opreste (_faLoc); fara
# nimeni se opreste singura dupa EXTERN_FARA_CLIENT_S (cel mult setarea asteptare a browserului). O reconectare scurta
# (proba si apoi redarea unui server media, o pauza) gaseste sesiunea vie si nu porneste nimic nou pe demux.
# ASTEPTARILE PLAYERELOR EXTERNE: o cerere care asteapta pauza dintre porniri (PREA_REPEDE) se reincearca cand trece
# pauza; numai cea care asteapta randul unui canal criptat (CRIPTAT_ASTEAPTA) asteapta si pauza criptatelor.
# Firul sesiunii care s-a incheiat nu mai primeste legaturi (ataseaza, sub lacatul sesiunii), iar sesiunea lui nu se
# mai refoloseste (sesiunePentru): o legatura noua porneste o sesiune noua, nu ramane agatata.
#
# FIRELE: tot ce atinge enigma2 ruleaza pe firul principal; firele sesiunilor cer munca printr-o coada si o teava de
# trezire (eSocketNotifier). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau obiectele lor.

import binascii
import collections
import errno
import math
import os
import re
import select
import threading
import time

ET = "[HdsTransmisie]"

SESIUNI_PERMISE = ("1", "2")
SESIUNI_IMPLICIT = "1"
ASTEPTARI_PERMISE_S = (10, 20, 60)
ASTEPTARE_IMPLICITA_S = 60      # o reincarcare sau o pauza scurta refoloseste sesiunea (nu mai costa 4 MB)

ZONA_KB = 4096                 # un canal de inregistrare nou lasa atat in driver (DMX_RecBuf); cu paza demuxului
                               # numai primul dupa pornirea enigma2, deci socoteala pe fiecare pornire e prudenta
PRAG_GOL_KB = 20 * 1024        # decodorul video cere ~17 MB vmalloc dintr-o bucata
CEAS_MS = 1000
MEMORIE_S = 10                 # cat de des se reciteste memoria cat exista sesiuni (numai pentru pagina)
FARA_DATE_S = 15               # o inregistrare fara niciun octet atata timp se opreste (acord pierdut, tuner luat)
TRIMITERE_S = 1.5              # cat poate astepta un browser lent inainte sa fie lasat (teava s-ar umple)
TEAVA_OCTETI = 1024 * 1024
F_SETPIPE_SZ = 1031
BLOC = 188 * 1024               # citirea din teava, pachete TS intregi
TS = 188
JURNAL_MAX = 20
PREIA_S = 8                    # o sesiune cu spectator acum sau in ultimele PREIA_S secunde e "folosita" de fereastra ei
ALTA_FEREASTRA = "alta_fereastra"
PAUZA_COMUTARE_S = 2.0         # cel putin atat intre doua inregistrari noi (comutarile rapide asteapta)
EXTERN_PREDA_S = 3.0           # un player extern plecat de atat nu mai tine locul (PLAYERELE EXTERNE PLECATE, sus)
EXTERN_FARA_CLIENT_S = 15      # sesiunea unui player extern plecat se opreste dupa atat (browserul: setarea asteptare)
DOAR_FRECVENTA_S = 5.0         # cat se tine minte daca receptorul are motor / un singur tuner de satelit
PREA_REPEDE = "prea_repede"
# transmisia unui canal criptat (cheia modulului de acces legata de inregistrare pe dmx 0) a blocat
# driverul placii, iar receptorul a repornit singur; tot asa la 18:29 (fara semnal pana la repornire). Cu setarea ascunsa
# config.hds_transmisie.criptate pe Nu (implicit Da din) numai canalele necriptate se transmit (browser, playlisturi, playere
# externe); cu Da, criptatele merg serializat (CANALELE CRIPTATE, sus).
CRIPTAT_OPRIT = "criptat_oprit"
CRIPTAT_ASTEAPTA = "criptat_asteapta"   # pornirea criptata asteapta (o oprire amanata sau pauza dupa ultima oprire)
# o sesiune criptata nu se opreste mai devreme de atat de la primele date: prima legare a cheii pe canalele noi ale
# inregistrarii vine la urmatorul cuvant de control (12 si 13.10: la 2, 3, 6 si 7 s dupa pornire; cel mult ~10 s)
# masurat pe receptor (pauza 15, 10 si 0 s, varsta 0 s, 22 de sesiuni criptate la 1-2 s): paza PID 0x000F tine
# instanta inregistrarii, driverul ramane curat; de aceea implicitele sunt mici
VARSTA_CRIPTAT_S = 2.0
VARSTE_CRIPTAT_S = (0, 30)      # limitele setarii ascunse config.hds_transmisie.criptate_varsta
PAUZA_CRIPTAT_S = 2             # implicit: cel putin atat intre ultima oprire criptata si o pornire criptata
# limitele setarii ascunse config.hds_transmisie.criptate_pauza; 0 (si varsta 0) numai pentru probele cu comutari
# rapide; implicitele au venit din probele de comutare rapida (inainte 15 s si 12 s)
PAUZE_CRIPTAT_S = (0, 120)
LAMEDB = "/etc/enigma2/lamedb"
URMEAZA_S = 25                 # cat ramane deschisa cererea lunga a unei pagini care urmeaza televizorul
URMARITORI_MAX = 16            # cate cereri lungi odata (peste: raspuns pe loc, pagina intreaba din nou peste o secunda)
DECRIPTARE_ASTEAPTA = "asteapta"
DECRIPTARE_MERGE = "merge"
DECRIPTARE_NU = "nu"
# TERMENELE DECRIPTARII (proba din 14.10: mesajul venea abia la 60 s, iar un canal fara niciun octet intra in bucla):
# mesajul de canal criptat in cel mult ~30 s de la zap, desi pauza criptatelor (PAUZA_CRIPTAT_S) poate lua primele secunde.
# Termenele se socotesc de la primele date ale sesiunii sau, cand televizorul e pe acelasi canal, de la zap-ul lui
# (modulul de acces lucreaza pentru televizor din clipa zap-ului), dar sesiunea are oricum DECRIPTARE_MIN_S: cheia se
# leaga si pe PID-urile inregistrarii la ~6 s dupa pornirea ei (ProSieben HD: imaginea la ~7,6 s dupa pornire).
DECRIPTARE_FARA_RASPUNS_S = 25  # niciun raspuns al camului pe canal (oprit, blocat, un cam fara jurnal)
DECRIPTARE_MAX_S = 25           # raspunsuri nehotarate (timeout, "found" fara imagine clara): atat, cel mult
DECRIPTARE_MIN_S = 12           # cel putin atat de la primele date ale sesiunii (fara date: de la pornire) inainte de "nu"
# playerele externe (VLC, Kodi) n-au mesajul paginii: raman termenele de dinainte, de la primele date, cu 503 si
# Retry-After cat inca se incearca (tv_web, DECRIPTAREA)
DECRIPTARE_EXTERN_FARA_RASPUNS_S = 30
DECRIPTARE_EXTERN_MAX_S = 60
REFUZ_CICLURI_S = 6             # un refuz e definitiv cand se repeta la o cerere urmatoare a camului...
REFUZ_TARZIU_S = 20             # ...sau cand ramane singurul raspuns atata timp
# jurnalul modulului de acces: fara nume de fisier anume, se ia cel mai nou fisier .log cu "cam" in nume din aceste dosare
DOSARE_JURNALE_CAM = ("/tmp", "/var/log")
TIPAR_JURNAL_CAM = re.compile(r"^[^/]*cam[^/]*\.log$", re.I)
JURNAL_CAM_CITIRE = 256 * 1024  # cel mult atat la o citire (numai ce s-a scris de la citirea trecuta)


def N_(text):
	"""marcheaza textul pentru xgettext (po/Makefile.am --keyword=N_); traducerea se face la folosire, cu _"""
	return text


TEXT_NEDECRIPTAT = N_("Canalul e criptat și receptorul nu-l poate decripta acum (fără card sau fără drepturi pentru el).")

# tipul video din iServiceInformation.sVideoType (lib/dvb/decoder.h)
VIDEO_DIN_TIP = {0: "mpeg2", 1: "h264", 3: "vc1", 4: "mpeg4", 5: "vc1", 6: "mpeg1", 7: "h265"}


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def monoton():
	return time.monotonic()


_LAMEDB_CRIPTATE = {"semn": None, "chei": frozenset()}


def _cheieServiciu(ref):
	"""(sid, namespace, tsid, onid) din referinta, sau None."""
	p = str(ref or "").split(":")
	try:
		return int(p[3], 16), int(p[6], 16), int(p[4], 16), int(p[5], 16)
	except (IndexError, ValueError):
		return None


def criptateDinLamedb(cale=LAMEDB):
	"""Cheile (sid, namespace, tsid, onid) ale serviciilor cu CAID-uri in lamedb (formatul 4: trei randuri pe serviciu,
	al treilea cu ,C:xxxx), citite din nou numai cand fisierul s-a schimbat."""
	try:
		st = os.stat(cale)
	except OSError:
		return frozenset()
	semn = (cale, st.st_mtime, st.st_size)
	if _LAMEDB_CRIPTATE["semn"] == semn:
		return _LAMEDB_CRIPTATE["chei"]
	chei = set()
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			linii = f.read().splitlines()
		i = linii.index("services") + 1
		while i + 2 < len(linii) and linii[i] != "end":
			p = linii[i].split(":")
			if len(p) >= 4 and ",C:" in "," + linii[i + 2]:
				try:
					chei.add((int(p[0], 16), int(p[1], 16), int(p[2], 16), int(p[3], 16)))
				except ValueError:
					pass
			i += 3
	except (OSError, ValueError):
		return frozenset()
	_LAMEDB_CRIPTATE["semn"], _LAMEDB_CRIPTATE["chei"] = semn, frozenset(chei)
	return _LAMEDB_CRIPTATE["chei"]


def canalCriptat(ref):
	"""True cand canalul `ref` e criptat dupa oricare din: serviciul care ruleaza (sIsCrypted), accesul tinut minte
	(HdsAccesCanale) sau CAID-urile din lamedb. Un canal despre care nu se stie nimic trece (cele mai multe sunt FTA)."""
	curata = refCurata(ref) or ref
	try:
		import NavigationInstance
		from enigma import iServiceInformation
		nav = NavigationInstance.instance
		cur = nav.getCurrentlyPlayingServiceReference() if nav else None
		if cur is not None and _aceeasiRef(cur.toString(), curata):
			serv = nav.getCurrentService()
			info = serv and serv.info()
			if info is not None and info.getInfo(iServiceInformation.sIsCrypted) == 1:
				return True
	except Exception:
		pass
	try:
		from Components import HdsAccesCanale
		if HdsAccesCanale.acces(curata, None) == "criptat":
			return True
	except Exception:
		pass
	cheie = _cheieServiciu(curata)
	return cheie is not None and cheie in criptateDinLamedb()


def _jurnal(text):
	print("%s %s" % (ET, text))


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_transmisie: permis (Da), standby (Nu), sesiuni_max (1), asteptare (60 s). Ascunse (nu sunt pe
	televizor si nici in pagina; se schimba in /etc/enigma2/settings cu enigma2 oprit): criptate (Da), criptate_pauza
	(PAUZA_CRIPTAT_S secunde) si criptate_varsta (VARSTA_CRIPTAT_S secunde)."""
	from Components.config import config
	if "hds_transmisie" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigInteger
	config.hds_transmisie = ConfigSubsection()
	config.hds_transmisie.permis = ConfigYesNo(default=True)
	config.hds_transmisie.standby = ConfigYesNo(default=False)
	config.hds_transmisie.sesiuni_max = ConfigSelection(default=SESIUNI_IMPLICIT,
		choices=[(s, s) for s in SESIUNI_PERMISE])
	config.hds_transmisie.asteptare = ConfigSelection(default=str(ASTEPTARE_IMPLICITA_S), choices=alegeriAsteptare())
	config.hds_transmisie.criptate = ConfigYesNo(default=True)
	config.hds_transmisie.criptate_pauza = ConfigInteger(default=PAUZA_CRIPTAT_S, limits=PAUZE_CRIPTAT_S)
	config.hds_transmisie.criptate_varsta = ConfigInteger(default=int(VARSTA_CRIPTAT_S), limits=VARSTE_CRIPTAT_S)


def alegeriAsteptare():
	return [(str(s), textDurata(s)) for s in ASTEPTARI_PERMISE_S]


def textDurata(secunde):
	secunde = int(secunde)
	if secunde == 60:
		return _("un minut")
	return _("%d secunde") % secunde


class Setari(object):
	"""Setarile citite din config (pe receptor) sau date de probe (pe PC)."""

	def __init__(self, config=None):
		self._config = config

	def _c(self):
		if self._config is not None:
			return self._config
		initConfig()
		from Components.config import config
		return config.hds_transmisie

	def permis(self):
		return bool(self._c().permis.value)

	def standby(self):
		return bool(self._c().standby.value)

	def sesiuniMax(self):
		try:
			return max(1, int(self._c().sesiuni_max.value))
		except (TypeError, ValueError):
			return 1

	def asteptare(self):
		try:
			return int(self._c().asteptare.value)
		except (TypeError, ValueError):
			return ASTEPTARE_IMPLICITA_S

	def _ascunsa(self, nume):
		# o configuratie fara cheie (probele vechi; ConfigSubsection da KeyError) inseamna valoarea implicita
		try:
			return getattr(self._c(), nume).value
		except (AttributeError, KeyError):
			return None

	def criptate(self):
		"""Setarea ascunsa config.hds_transmisie.criptate: canalele criptate se transmit (implicit Da din)."""
		return bool(self._ascunsa("criptate"))

	def pauzaCriptat(self):
		"""Setarea ascunsa config.hds_transmisie.criptate_pauza: secundele dintre ultima oprire si o pornire criptata."""
		try:
			v = int(self._ascunsa("criptate_pauza"))
		except (TypeError, ValueError):
			v = PAUZA_CRIPTAT_S
		return max(PAUZE_CRIPTAT_S[0], min(PAUZE_CRIPTAT_S[1], v))

	def varstaCriptat(self):
		"""Setarea ascunsa config.hds_transmisie.criptate_varsta: cat traieste cel putin o sesiune criptata (secunde)."""
		try:
			v = float(int(self._ascunsa("criptate_varsta")))
		except (TypeError, ValueError):
			v = VARSTA_CRIPTAT_S
		return max(float(VARSTE_CRIPTAT_S[0]), min(float(VARSTE_CRIPTAT_S[1]), v))


# ---------------------------------------------------------------- referinte

def campuriRef(ref):
	"""'1:0:19:283D:3FB:1:C00000:0:0:0:' -> (tip, sid, tsid, onid, ns) ca intregi, sau None pentru altceva decat un
	serviciu DVB (cai de fisier, grupuri, marcaje)."""
	p = str(ref or "").split(":")
	if len(p) < 10 or p[0] != "1" or p[1] != "0":
		return None
	try:
		return tuple(int(x, 16) for x in p[2:7])
	except ValueError:
		return None


def refCurata(ref):
	"""Referinta DVB de serviciu cu primele 10 campuri, litere mari, ':' la sfarsit; None pentru orice altceva (cai
	de fisier, nume adaugate, caractere straine)."""
	c = campuriRef(ref)
	if c is None:
		return None
	p = str(ref).split(":")
	if any(len(x) > 8 for x in p[2:10]) or any(x.strip("0123456789abcdefABCDEF") for x in p[2:10]):
		return None
	return ":".join(x.upper() for x in p[:10]) + ":"


def transponder(ref):
	"""(ns, tsid, onid) sau None."""
	c = campuriRef(ref)
	return (c[4], c[2], c[3]) if c else None


def familie(ref):
	"""'sat', 'teren' (0xEEEE), 'cablu' (0xFFFF) sau None: un tuner pe familie la receptoarele cu A satelit si B
	combinat."""
	c = campuriRef(ref)
	if not c:
		return None
	poz = (c[4] >> 16) & 0xFFFF
	if poz == 0xEEEE:
		return "teren"
	if poz == 0xFFFF:
		return "cablu"
	return "sat"


def pozitieSatelit(ref):
	"""Pozitia orbitala din spatiul de nume (in zecimi de grad, peste 1800 = vest) sau None pentru teren / cablu."""
	if familie(ref) != "sat":
		return None
	return (campuriRef(ref)[4] >> 16) & 0xFFFF


# ---------------------------------------------------------------- ce merge in browser

def potrivire(video, audio, hevc=False, ac3=False, wasm=False):
	"""Ce se poate reda in browser fara recodare. `video` = 'h264' | 'h265' | 'mpeg2' | ... | '' (nu se stie),
	`audio` = felurile pistelor ('MPEG', 'AAC', 'AAC-HE', 'AC3', 'AC3+', ...), `hevc` / `ac3` = browserul le decodeaza
	(MediaSource.isTypeSupported in pagina; ac3 si cand pagina decodeaza singura AC-3 cu decodorul wasm, hds-sunet.js),
	`wasm` = pagina are playerul wasm (imaginea MPEG-2 / MPEG-1 si sunetul MP2 / MP3 / AC-3 se decodeaza in browser;
	E-AC-3, AAC si HE-AAC nu sunt in decodorul lui). Cu ac3 si wasm sunetul AC-3 merge sigur. -> (merge, text):
	merge False = refuz, cu motivul; True cu text = merge, cu avertizarea de spus."""
	video = (video or "").lower()
	felurile = [str(a or "").upper() for a in (audio or [])]
	if video in ("mpeg2", "mpeg1"):
		if not wasm:
			return False, _("Acest canal trimite imaginea în MPEG-2, iar acest browser nu o poate reda (îi lipsește WebAssembly sau WebGL). Încearcă Chrome, Edge, Firefox sau Safari nou.")
		# aceleasi alegeri ca RescrierePsi cu wasm: MP2 / MP3, apoi AC-3
		are_mp2_ac3 = any(f in ("MPEG", "MP2", "MP3", "AC3", "AC-3", "DD") for f in felurile)
		if felurile and not are_mp2_ac3:
			return True, _cuImagine(textSunet(felurile, ac3, wasm, video))
		return True, _("Imaginea acestui canal (MPEG-2) se decodează în browser, pe procesorul calculatorului.")
	if video == "h265" and not hevc:
		return False, _("Acest canal trimite imaginea în HEVC, iar acest browser nu o poate reda. Încearcă Chrome sau Edge pe un calculator cu placă video nouă, sau Safari.")
	if video in ("vc1", "mpeg4"):
		return False, _("Acest canal trimite imaginea într-un format pe care browserele nu îl redau.")
	# aceleasi alegeri ca RescrierePsi: MP2 / MP3, AAC ADTS ("AAC"), AC-3 numai daca browserul il reda; HE-AAC LATM
	# ("AAC-HE") si E-AC-3 ("AC3+") ies din PMT
	are_mp2 = any(f in ("MPEG", "MP2", "MP3") for f in felurile)
	are_adts = any(f == "AAC" for f in felurile)
	are_ac3 = any(f in ("AC3", "AC-3", "DD") for f in felurile)
	if felurile and not (are_mp2 or are_adts):
		if are_ac3 and ac3:
			if wasm:
				return True, ""   # pagina are si decodorul wasm al paginii: AC-3 se aude (nativ sau decodat acolo)
			return True, _("Sunetul acestui canal e AC-3. Unele browsere îl redau, altele nu.")
		return True, _cuImagine(textSunet(felurile, ac3, wasm, video))
	if not video:
		if wasm:
			return True, ""   # playerul afla formatul din flux si trece singur pe playerul wasm la MPEG-2
		return True, _("Formatul imaginii nu se știe încă. Dacă nu apare imaginea, canalul e probabil MPEG-2.")
	return True, ""


# felurile pistelor din RescrierePsi (PMT) in numele din potrivire()
_FEL_POTRIVIRE = {"MP2": "MPEG", "AAC": "AAC", "AC3": "AC3", "HE-AAC": "AAC-HE", "E-AC3": "AC3+"}


def _sunet(felurile, ac3=False, wasm=False, video=""):
	"""(textul despre sunet, sunetul nu se aude): aceleasi alegeri ca potrivire() si RescrierePsi. Pe playerul wasm
	(imaginea MPEG-2 / MPEG-1) se aud MP2 / MP3 si AC-3; altfel MP2 / MP3, AAC ADTS si AC-3 numai daca browserul il reda
	(ac3; cu wasm si ac3 il decodeaza pagina, deci se aude fara avertizare).
	Formatul se spune cand se stie: AC-3, E-AC-3, HE-AAC LATM."""
	felurile = [str(a or "").upper() for a in (felurile or [])]
	if not felurile:
		return "", False
	are_ac3 = any(f in ("AC3", "AC-3", "DD") for f in felurile)
	are_eac3 = any(f in ("AC3+", "E-AC3", "E-AC-3", "EAC3", "DD+") for f in felurile)
	are_latm = any(f.startswith("AAC-HE") or f in ("HE-AAC", "LATM") for f in felurile)
	if wasm and (video or "").lower() in ("mpeg2", "mpeg1"):
		if are_ac3 or any(f in ("MPEG", "MP2", "MP3") for f in felurile):
			return "", False
	else:
		if any(f in ("MPEG", "MP2", "MP3", "AAC") for f in felurile):
			return "", False
		if are_ac3 and ac3:
			if wasm:
				return "", False
			return _("Sunetul acestui canal e AC-3. Unele browsere îl redau, altele nu."), False
	if are_ac3:
		return _("Sunetul acestui canal e AC-3 și nu se aude în acest browser."), True
	if are_eac3:
		return _("Sunetul acestui canal (E-AC-3) nu se aude în browser."), True
	if are_latm:
		return _("Sunetul acestui canal (HE-AAC LATM) nu se aude în browser."), True
	return _("Sunetul acestui canal nu se aude în browser."), True


def textSunet(felurile, ac3=False, wasm=False, video=""):
	"""Numai ce se spune despre sunet ("" cand o pista se aude), fara nimic despre imagine."""
	return _sunet(felurile, ac3, wasm, video)[0]


def _cuImagine(text):
	"""Lista canalelor si verificarea: sunetul nu se aude, dar imaginea da (o spune dinainte, dupa format)."""
	return text + " " + _("Imaginea merge.")


def _felurileDinPiste(piste):
	return [_FEL_POTRIVIRE.get(p.get("fel"), p.get("fel") or "") for p in piste or []]


def avertizarePmt(video, piste, ac3=False, wasm=False):
	"""Avertizarea paginii dupa PMT-ul fluxului (RescrierePsi: imaginea si pistele audio care chiar vin). La pornire se
	stie numai ce spune baza de canale, care poate avea alte piste decat are canalul acum (Das Erste HD: numai AC-3 in
	baza, trei piste MP2 si una AC-3 in PMT). Numai sunetul (textSunet, cu formatul) si, la MPEG-2 pe playerul wasm,
	decodarea in browser: "Imaginea merge." o adauga pagina abia cand vin cadre adevarate si o scoate cand se opresc
	(player.js, sunet_lipsa); la un post de radio (PMT fara imagine) nu apare deloc (proba de noapte 13-14.10)."""
	video = (video or "").lower()
	text = textSunet(_felurileDinPiste(piste), ac3, wasm, video)
	if text:
		return text
	if wasm and video in ("mpeg2", "mpeg1"):
		return _("Imaginea acestui canal (MPEG-2) se decodează în browser, pe procesorul calculatorului.")
	return ""


def sunetLipsa(video, piste, ac3=False, wasm=False):
	"""True cand nicio pista din PMT nu se aude in browser (pagina adauga atunci "Imaginea merge." la cadrele adevarate)."""
	return _sunet(_felurileDinPiste(piste), ac3, wasm, video)[1]


def infoCanal(ref, serviciu_tv=None, ref_tv=None, baza=None):
	"""{'video': codec, 'audio': [felurile pistelor]} pentru canalul `ref`. Canalul de pe televizor din serviciul care
	ruleaza (sVideoType, pistele audio); celelalte din baza de canale a imaginii (Components/HdsBazaCanale: vd[6],
	a[*][1]). Ce nu se stie ramane gol.
	Randul dat de HdsBazaCanale.cauta() e desfacut si PLAT: grupa pistelor ("pi") sta in cheile de sus "a", "d", "x",
	"tt" (_ORDINE_CANAL, valoare_grupa(rand, "pi")); inainte se citea rand["pi"]["a"], care nu exista,
	deci canalele care nu erau pe televizor ieseau fara sunet (de exemplu REGIO TV, Baden TV).
	Felul din baza poate avea dupa un spatiu asezarea canalelor ("MPEG 2.0", "AC3 MC", Components/HdsPisteCanale.py):
	se ia numai primul cuvant, ca la canalul televizorului; altfel potrivire() nu recunostea nicio pista (arte HD:
	"Sunetul acestui canal nu se aude in browser" in lista paginii, cu patru piste MP2)."""
	rez = {"video": "", "audio": []}
	if serviciu_tv is not None and ref_tv and _aceeasiRef(ref, ref_tv):
		try:
			from enigma import iServiceInformation
			info = serviciu_tv.info()
			rez["video"] = VIDEO_DIN_TIP.get(info.getInfo(iServiceInformation.sVideoType), "")
		except Exception:
			pass
		try:
			piste = serviciu_tv.audioTracks()
			for i in range(piste.getNumberOfTracks() if piste else 0):
				d = piste.getTrackInfo(i).getDescription()
				if d:
					rez["audio"].append(str(d).split(" ")[0])
		except Exception:
			pass
		if rez["video"] or rez["audio"]:
			return rez
	try:
		if baza is None:
			from Components import HdsBazaCanale
			baza = HdsBazaCanale.baza()
		rand = baza.cauta(ref)
	except Exception:
		rand = None
	if isinstance(rand, dict):
		vd = rand.get("vd")
		if isinstance(vd, (list, tuple)) and len(vd) > 6 and isinstance(vd[6], str):
			rez["video"] = vd[6] if vd[6] in ("mpeg2", "h264", "h265") else ""
		piste = rand.get("a")
		if isinstance(piste, list):
			rez["audio"] = [str(a[1]).split(" ")[0] for a in piste if isinstance(a, (list, tuple)) and len(a) > 1 and a[1]]
	return rez


def _aceeasiRef(a, b):
	return refCurata(a) is not None and refCurata(a) == refCurata(b)


def _acelasiTv(a, b):
	"""Acelasi lucru pe televizor: canalele DVB dupa refCurata, restul (fisiere, adrese) ca text."""
	return (refCurata(a) or (a or "")) == (refCurata(b) or (b or ""))


class _Urmaritor(object):
	"""O pagina care urmeaza televizorul (Manager.urmaresteTv)."""
	__slots__ = ("functie", "ref", "standby", "termen", "cheie")

	def __init__(self, functie, ref, standby, termen, cheie):
		self.functie, self.ref, self.standby, self.termen, self.cheie = functie, ref or "", bool(standby), termen, cheie


class JurnalCam(object):
	"""Raspunsurile camului din jurnalul lui (numai citire; modulele de acces scriu pentru fiecare cerere
	"(CAID@PROVID/CHID/SID/LEN:SUMA): found|not found|rejected ... (N ms)"), pe SID. Jurnalul e gasit dupa tipar, nu dupa
	nume: cel mai nou fisier .log cu "cam" in nume din `dosare` (DOSARE_JURNALE_CAM) care are randuri de cereri, altfel
	cel mai nou; `cai` (probe) da cai anume, luate in ordine. Se citeste numai ce s-a scris de la marcheaza() (pornirea unei sesiuni criptate) incoace, cel mult
	JURNAL_CAM_CITIRE odata, numai cat o sesiune asteapta decriptarea. Fara jurnal (alt cam, jurnalul oprit): niciun
	raspuns, deci hotaraste DECRIPTARE_FARA_RASPUNS_S."""

	RAND = re.compile(r"\(([0-9A-Fa-f]{4})[@&]([0-9A-Fa-f]{1,8})/(?:[0-9A-Fa-f]{4}/)?([0-9A-Fa-f]{4})/[0-9A-Fa-f]{1,4}:"
		r"[0-9A-Fa-f]+\):\s*([A-Za-z][A-Za-z0-9 ]*)")
	TINUT_S = 300

	def __init__(self, cai=None, dosare=DOSARE_JURNALE_CAM):
		self.cai = tuple(cai) if cai is not None else None
		self.dosare = tuple(dosare)
		self._cale = None
		self._poz = None
		self._rest = b""
		self._evenimente = collections.deque(maxlen=2000)   # (cand, sid, fel)

	def _gaseste(self):
		if self.cai is not None:
			for c in self.cai:
				try:
					if os.path.isfile(c):
						return c
				except OSError:
					pass
			return None
		candidati = []
		for dosar in self.dosare:
			try:
				nume = os.listdir(dosar)
			except OSError:
				continue
			for n in nume:
				if not TIPAR_JURNAL_CAM.match(n):
					continue
				cale = os.path.join(dosar, n)
				try:
					if not os.path.isfile(cale):
						continue
					candidati.append((os.path.getmtime(cale), cale))
				except OSError:
					continue
		candidati.sort(reverse=True)
		# intai cel mai nou care are chiar randuri de cereri de decriptare (un alt jurnal cu "cam" in nume nu-l ia locul),
		# altfel cel mai nou: jurnalul unui modul care n-a primit inca nicio cerere e gol
		for _timp, cale in candidati[:5]:
			if self._are_cereri(cale):
				return cale
		return candidati[0][1] if candidati else None

	def _are_cereri(self, cale):
		try:
			with open(cale, "rb") as f:
				f.seek(0, os.SEEK_END)
				f.seek(max(0, f.tell() - 32768))
				return bool(self.RAND.search(f.read().decode("latin-1")))
		except OSError:
			return False

	def marcheaza(self):
		"""De aici incolo (o sesiune criptata a pornit): daca jurnalul nu se citeste acum, citirea incepe de la capatul
		lui de acum (ce era scris inainte nu priveste sesiunea)."""
		if self._poz is not None:
			return
		self._cale = self._gaseste()
		if self._cale is None:
			return
		try:
			self._poz = os.path.getsize(self._cale)
		except OSError:
			self._poz = None
		self._rest = b""

	@staticmethod
	def fel(text):
		"""'gasit' (found, cache), 'refuzat' (not found, rejected, no matching reader) sau 'incearca' (restul: timeout,
		sleeping ...)."""
		t = text.strip().lower()
		if t.startswith("not found") or t.startswith("rejected") or t.startswith("no matching reader"):
			return "refuzat"
		if t.startswith("found") or t.startswith("cache"):
			return "gasit"
		return "incearca"

	def citeste(self, acum):
		"""Randurile noi ale jurnalului (firul principal, de la ceas)."""
		if self._poz is None:
			self.marcheaza()
			if self._poz is None:
				return
		try:
			marime = os.path.getsize(self._cale)
		except OSError:
			self._poz, self._cale = None, None
			return
		if marime < self._poz:
			self._poz, self._rest = 0, b""      # jurnalul a fost golit sau rotit
		if marime == self._poz:
			return
		try:
			with open(self._cale, "rb") as f:
				f.seek(max(self._poz, marime - JURNAL_CAM_CITIRE))
				date = f.read(JURNAL_CAM_CITIRE)
		except (IOError, OSError):
			return
		self._poz = marime
		date = self._rest + date
		randuri = date.split(b"\n")
		self._rest = randuri.pop()[-4096:]
		for r in randuri:
			m = self.RAND.search(r.decode("latin-1", "replace"))
			if m:
				self._evenimente.append((acum, int(m.group(3), 16), self.fel(m.group(4))))
		while self._evenimente and self._evenimente[0][0] < acum - self.TINUT_S:
			self._evenimente.popleft()

	def opreste(self):
		"""Nicio sesiune nu mai asteapta: urmatoarea marcheaza() incepe de la capatul de atunci."""
		self._poz, self._rest = None, b""

	def raspuns(self, sid, de_la, acum, baza):
		"""Ce a raspuns camul pentru `sid` de la `de_la` (ceasul monoton al pornirii sesiunii): 'gasit', 'refuzat'
		(definitiv: la doua cereri la cel putin REFUZ_CICLURI_S una de alta, ori singurul raspuns de la `baza` de cel putin
		REFUZ_TARZIU_S), 'incearca' sau None (nimic)."""
		if sid is None:
			return None
		ev = [(t, f) for t, s, f in self._evenimente if s == sid and t >= de_la - 1.0]
		if not ev:
			return None
		if any(f == "gasit" for _t, f in ev):
			return "gasit"
		refuzuri = [t for t, f in ev if f == "refuzat"]
		if refuzuri and (refuzuri[-1] - refuzuri[0] >= REFUZ_CICLURI_S or acum - baza >= REFUZ_TARZIU_S):
			return "refuzat"
		return "incearca"


def inregistrariPornite():
	"""Referintele (text) inregistrarilor enigma2 pregatite sau pornite acum (temporizatoarele, inclusiv
	inregistrarea pe loc); transmisiile noastre nu sunt aici (inregistrari facute direct, fara temporizator)."""
	try:
		import NavigationInstance
		rez = []
		for t in getattr(getattr(NavigationInstance.instance, "RecordTimer", None), "timer_list", None) or []:
			if getattr(t, "justplay", False) or getattr(t, "state", None) not in (1, 2):   # pregatita, pornita
				continue
			r = getattr(getattr(t, "service_ref", None), "ref", None)
			if r is not None:
				rez.append(_refText(r))
		return rez
	except Exception as e:
		_jurnal("inregistrarile pornite: %r" % (e,))
		return []


def _sincron(date):
	"""Primul octet de unde incep trei pachete TS la rand (0x47 la 0, 188, 376), sau -1."""
	n = len(date)
	i = date.find(b"\x47")
	while 0 <= i and i + 2 * TS < n:
		if date[i + TS] == 0x47 and date[i + 2 * TS] == 0x47:
			return i
		i = date.find(b"\x47", i + 1)
	return -1


# ---------------------------------------------------------------- sesiunea

class Sesiune(object):
	"""Un canal transmis spre un browser. Firul principal: rec, w, starea. Firul sesiunii: r, clientul legat."""

	def __init__(self, sid, ref, nume, cine, browser, adresa, perete, mon):
		self.id = sid
		self.ref = ref
		self.nume = nume
		self.cine = cine                 # cheia browserului (asocierea sau adresa)
		self.browser = browser           # numele de aratat
		self.adresa = adresa
		self.inceput = perete
		self.inceput_mon = mon
		self.rec = None
		self.r = None
		self.w = None
		self.octeti = 0
		self.ultim_octet_mon = None
		self.cu_client = False
		self.fara_spectator_din = mon
		self.motiv = None                # de ce s-a oprit (text pentru om)
		self.oprita = threading.Event()
		self.fir = None
		self.lacat = threading.Lock()
		self.client_nou = None           # (fd, la_plecare), pus de firul principal, luat de firul sesiunii
		self.ac3 = False                 # browserul reda AC-3 (pista AC-3 ramane in PMT, vezi RescrierePsi)
		self.pista = None                # PID-ul pistei audio alese din pagina (None = alegerea obisnuita)
		self.piste = []                  # pistele audio din PMT (puse de firul sesiunii, din RescrierePsi.piste)
		self.pmt_citit = False           # firul sesiunii a citit PMT-ul fluxului (piste si video sunt ale lui)
		self.extern = False              # player extern (VLC, Kodi): PMT-ul trece intreg
		self.fereastra = ""              # fereastra (fila) browserului care a pornit sesiunea; "" = pagina veche, fara id
		self.criptat = None              # imaginea iese criptata (RescrierePsi.criptat), None = nu se stie
		self.wasm = False                # pagina are playerul wasm: la imagine MPEG-2 raman in PMT MP2 / MP3 si AC-3
		self.video = ""                  # formatul imaginii din PMT (RescrierePsi.video): mpeg2, mpeg1, h264, h265
		self.canal_criptat = False       # canalul e criptat (la pornire): oprirea se amana, pornirile se serializeaza
		self.prim_octet_mon = None       # ceasul monoton al primelor date din teava (de aici se socoteste varsta)
		self.reluabila = False           # oprirea amanata se anuleaza daca acelasi browser cere din nou acelasi canal
		self.fir_gata = False            # firul sesiunii s-a incheiat: nimeni nu mai citeste teava
		self.decriptare = None           # canalele criptate: DECRIPTARE_ASTEAPTA, _MERGE sau _NU (DECRIPTAREA); None = FTA
		self.video_pachete = 0           # pachetele imaginii vazute de firul sesiunii (0 = nicio imagine inca)
		self.decriptare_din = None       # de cand asteapta din nou decriptarea (cheia pierduta dupa ce a mers)

	def descriere(self, acum_mon):
		return {
			"id": self.id, "ref": self.ref, "nume": self.nume, "browser": self.browser, "adresa": self.adresa,
			"inceput": int(self.inceput), "secunde": int(max(0, acum_mon - self.inceput_mon)),
			"octeti": int(self.octeti), "cu_spectator": bool(self.cu_client),
			"oprita": self.oprita.is_set(), "motiv": self.motiv or "",
			"piste": list(self.piste or []), "pista": self.pista, "extern": bool(self.extern),
			"fereastra": self.fereastra, "criptat": self.criptat, "video": self.video,
			"decriptare": self.decriptare,
			# avertizarea paginii dupa PMT-ul fluxului (None = PMT-ul nu s-a citit inca; "" = nimic de spus)
			"avertizare": avertizarePmt(self.video, self.piste, self.ac3, self.wasm) if self.pmt_citit else None,
			# sunetul nu se aude: pagina adauga "Imaginea merge." numai cat vin cadre (player.js, paza cadrelor)
			"sunet_lipsa": bool(self.pmt_citit and sunetLipsa(self.video, self.piste, self.ac3, self.wasm)),
			# pachetele imaginii vazute de receptor: pagina deosebeste "canalul nu trimite imagine" de "browserul nu o
			# poate reda" cand nu vin cadre
			"video_pachete": int(self.video_pachete),
			# PMT-ul fluxului (citit sau facut din fluxuri, RescrierePsi, PMT-UL LIPSA): fara el pagina nu stie ce sa redea
			"pmt_citit": bool(self.pmt_citit),
		}

	def folositaDeAlta(self, fereastra, acum_mon):
		"""True cand alta fereastra a aceluiasi browser se uita acum (sau s-a uitat in ultimele PREIA_S secunde)."""
		if not fereastra or not self.fereastra or fereastra == self.fereastra:
			return False
		return bool(self.cu_client) or (acum_mon - self.fara_spectator_din) < PREIA_S


class Manager(object):
	"""Sesiunile procesului. Toate metodele publice se cheama pe firul principal."""

	def __init__(self, setari=None, memorie=None, tuner=None, inregistrare=None, programator=None, ceas=None,
			perete=None, contor=None, tv=None, in_standby=None, navigatie=None, doar_frecventa_tv=None, criptat=None,
			inregistrari=None, jurnal_cam=None):
		self.setari = setari or Setari()
		self.sesiuni = []
		self.jurnal = collections.deque(maxlen=JURNAL_MAX)
		self.oprite = {}                 # cine -> (motiv, cand): ce i se spune paginii dupa o oprire
		self._memorie = memorie or memorieDriver
		self._tuner = tuner or tunerLiber
		self._inregistrare = inregistrare or InregistrareInTeava()
		self._programator = programator  # f(functie): pune functia pe firul principal (probele o cheama pe loc)
		self._ceas = ceas                # obiect cu start(ms) / stop(), sau None (se face un eTimer)
		self._monoton = monoton
		self._perete = perete or time.time
		self._contor = contor or contorSesiuni
		self._tv = tv or refTv
		self._in_standby = in_standby or inStandby
		self._navigatie = navigatie
		self._doar_frecventa_tv = doar_frecventa_tv or doarFrecventaTv
		self._criptat = criptat or canalCriptat
		self._doar_frecventa_citit = (None, True)   # (cand, valoare): /api/tv-canale o cere pentru fiecare canal
		self._ultima_pornire = None      # ceasul monoton al ultimei inregistrari noi
		self.pauza_comutare_s = PAUZA_COMUTARE_S
		self._lacat = threading.Lock()
		self._coada = collections.deque()
		self._trezire = None
		self._notificator = None
		self._extensii = False
		self._ultima_memorie = (None, None)
		self._amanate = []               # sesiuni criptate oprite pentru pagina, cu inregistrarea inca pornita
		self._ultima_oprire = None       # ceasul monoton al ultimei opriri adevarate a unei inregistrari (rec.stop)
		self._asteptari = collections.OrderedDict()   # playerele externe care asteapta: cine -> (functie, termen)
		self._fel_asteptare = {}         # cine -> ce asteapta (PREA_REPEDE / CRIPTAT_ASTEAPTA): ultimul refuz al pornirii
		self._varsta_criptat_s = None    # None = din setarea ascunsa criptate_varsta (varsta_criptat_s, mai jos)
		self.pauza_criptat_s = None      # None = din setarea ascunsa criptate_pauza (probele o pun direct)
		self._inregistrari = inregistrari or inregistrariPornite
		self._urmaritori = []            # paginile care urmeaza televizorul (cererile lungi, _Urmaritor)
		self._jurnal_cam = jurnal_cam if jurnal_cam is not None else JurnalCam()
		self._asteptari_decriptare = {}  # playerele externe care asteapta decriptarea: id sesiune -> (functie, termen)
		self._observatori = []           # cine vrea sa afle cand se schimba transmise() (lista, barele, pagina)
		self._transmise = ()             # transmise() la ultimul anunt
		self._zap_tv = None              # (refCurata, ceasul monoton) al ultimului zap vazut (_laZap): TERMENELE DECRIPTARII

	# ------------------------------------------------------------ firul principal: trezirea si ceasul
	def _pornesteTrezirea(self):
		if self._programator is not None or self._trezire is not None:
			return
		from enigma import eSocketNotifier
		r, w = os.pipe()
		for fd in (r, w):
			_neblocant(fd)
		self._trezire = (r, w)
		self._notificator = eSocketNotifier(r, 1)
		try:
			self._notificator.callback.append(self._trezit)
		except AttributeError:
			self._conexiune_trezire = self._notificator.activated.connect(self._trezit)

	def cere(self, functie, *argumente):
		"""Din orice fir: `functie(*argumente)` ruleaza pe firul principal."""
		if self._programator is not None:
			self._programator(lambda: functie(*argumente))
			return
		with self._lacat:
			self._coada.append((functie, argumente))
		try:
			if self._trezire:
				os.write(self._trezire[1], b".")
		except OSError:
			pass

	def _trezit(self, _ce=None):
		try:
			while os.read(self._trezire[0], 512):
				pass
		except (OSError, TypeError):
			pass
		while True:
			with self._lacat:
				if not self._coada:
					break
				functie, argumente = self._coada.popleft()
			try:
				functie(*argumente)
			except Exception as e:
				_jurnal("munca pe firul principal a cazut: %r" % (e,))

	def _ceasul(self):
		if self._ceas is None:
			from enigma import eTimer
			self._ceas = eTimer()
			try:
				self._ceas.callback.append(self.verifica)
			except AttributeError:
				self._conexiune_ceas = self._ceas.timeout.connect(self.verifica)
		return self._ceas

	def _dupaSchimbare(self):
		# o sesiune cu oprirea amanata tine inca tunerul (prioritatea televizorului ramane pusa) si are nevoie de ceas ca
		# oprirea adevarata sa se faca; playerele externe care asteapta o pornire criptata au nevoie numai de ceas
		vii = [s for s in self.sesiuni if not s.oprita.is_set()]
		# extensia de zap anunta si paginile care urmeaza televizorul (urmaritorii)
		if vii or self._amanate or self._urmaritori:
			self._puneExtensiile()
		else:
			self._scoateExtensiile()
		if vii or self._amanate or self._asteptari or self._urmaritori or self._asteptari_decriptare:
			self._ceasul().start(CEAS_MS, False)
		elif self._ceas is not None:
			self._ceas.stop()

	# ------------------------------------------------------------ starea
	def memorie(self, din_nou=False):
		"""{'liber_kb', 'gol_max_kb', 'ramase', 'trebuie_repornit', 'motiv'} sau None; citita cel mult o data la
		MEMORIE_S secunde (fisierul /proc/vmallocinfo are sute de randuri)."""
		cand, valoare = self._ultima_memorie
		acum = self._monoton()
		if din_nou or cand is None or acum - cand >= MEMORIE_S:
			try:
				valoare = self._memorie()
			except Exception as e:
				_jurnal("memoria driverului nu se citeste: %r" % (e,))
				valoare = None
			self._ultima_memorie = (acum, valoare)
		return valoare

	def vii(self):
		return [s for s in self.sesiuni if not s.oprita.is_set()]

	def sesiunePentru(self, cine):
		# fara sesiunea al carei fir s-a incheiat (inca neaflat pe firul principal): nu mai poate trimite nimic
		for s in self.vii():
			if s.cine == cine and not s.fir_gata:
				return s
		return None

	def stare(self):
		acum = self._monoton()
		return {
			"permis": self.setari.permis(),
			"standby": self.setari.standby(),
			"sesiuni_max": self.setari.sesiuniMax(),
			"asteptare": self.setari.asteptare(),
			"sesiuni": [s.descriere(acum) for s in self.vii()],
			"memorie": self.memorie(),
			"jurnal": list(self.jurnal)[::-1],
			"canale": folosiriCanalelor(),
		}

	# ------------------------------------------------------------ semnul "in retea" (LISTA DE CANALE SI SEMNUL, sus)
	def transmise(self):
		"""Canalele transmise acum (refCurata, sortate): sesiunile cu inregistrarea pornita, vii sau cu oprirea amanata.
		Sunt exact inregistrarile care cedeaza la zap (InregistrareInTeava.porneste, setYieldsToZap), deci semnul si
		canalele albe din lista nu se pot desparti."""
		return tuple(sorted(set(s.ref for s in list(self.sesiuni) + list(self._amanate) if s.rec is not None)))

	def urmaresteTransmise(self, functie):
		"""functie() ruleaza pe firul principal cand se schimba transmise(); aceeasi functie se tine o singura data."""
		if functie not in self._observatori:
			self._observatori.append(functie)

	def renuntaTransmise(self, functie):
		while functie in self._observatori:
			self._observatori.remove(functie)

	def _anuntaTransmise(self):
		"""Chemata unde porneste si unde se opreste inregistrarea unei sesiuni: observatorii afla numai o schimbare."""
		acum = self.transmise()
		if acum == self._transmise:
			return
		self._transmise = acum
		for f in list(self._observatori):
			try:
				f()
			except Exception as e:
				_jurnal("semnul transmisiei: %r" % (e,))

	# ------------------------------------------------------------ canalele criptate: serializarea
	def ceas(self):
		"""Ceasul monoton al managerului (termenele asteptarilor din tv_web)."""
		return self._monoton()

	def _pauzaCriptat(self):
		return self.pauza_criptat_s if self.pauza_criptat_s is not None else self.setari.pauzaCriptat()

	@property
	def varsta_criptat_s(self):
		"""Varsta minima a unei sesiuni criptate: din setarea ascunsa criptate_varsta; probele o pun direct."""
		return self._varsta_criptat_s if self._varsta_criptat_s is not None else self.setari.varstaCriptat()

	@varsta_criptat_s.setter
	def varsta_criptat_s(self, secunde):
		self._varsta_criptat_s = secunde

	def _capatVarsta(self, ses):
		"""Ceasul monoton de la care sesiunea criptata se poate opri: VARSTA_CRIPTAT_S de la primele date (de la pornire
		cat n-a venit nimic)."""
		baza = ses.prim_octet_mon if ses.prim_octet_mon is not None else ses.inceput_mon
		return baza + self.varsta_criptat_s

	def secundeCriptat(self):
		"""Cate secunde mai asteapta o pornire criptata (0 = poate porni acum): cat se amana o oprire, apoi pauza dupa
		ultima oprire adevarata a unei transmisii."""
		acum = self._monoton()
		pauza = self._pauzaCriptat()
		capete = [self._capatVarsta(s) + pauza for s in self._amanate]
		if self._ultima_oprire is not None:
			capete.append(self._ultima_oprire + pauza)
		rest = (max(capete) - acum) if capete else 0
		if self._amanate:
			rest = max(rest, 1)          # cat se amana o oprire nu porneste nimic criptat
		return int(math.ceil(rest)) if rest > 0 else 0

	def _opririAmanate(self):
		"""Opririle amanate care si-au implinit varsta se fac acum (ceasul; si inaintea unei porniri)."""
		acum = self._monoton()
		for s in list(self._amanate):
			if acum >= self._capatVarsta(s):
				self._opresteInregistrarea(s)

	def _reiaAmanata(self, cine, ref, fereastra="", wasm=False, ac3=None):
		"""Ultima cerere castiga: sesiunea criptata a acestui browser pe `ref`, cu oprirea inca amanata, se reia (pe
		demux nu porneste si nu se opreste nimic). -> sesiunea sau None."""
		for s in list(self._amanate):
			if (not cine or s.cine != cine or not s.reluabila or s.fir_gata or not _aceeasiRef(s.ref, ref)
					or self._inregistrare.eroare(s)):
				continue
			self._amanate.remove(s)
			s.motiv, s.reluabila = None, False
			s.oprita.clear()
			s.fara_spectator_din = self._monoton()
			if fereastra:
				s.fereastra = fereastra
			s.wasm = bool(wasm)
			if ac3 is not None:
				s.ac3 = bool(ac3)
			self.oprite.pop(cine, None)
			_jurnal("sesiune criptata reluata %s %s (oprirea amanata s-a anulat)" % (s.id, s.ref))
			self._dupaSchimbare()
			return s
		return None

	def asteaptaCriptat(self, cine, functie, termen_s):
		"""Playerele externe: functie(None) ruleaza pe firul principal cand o pornire criptata poate incepe sau dupa
		`termen_s` secunde (ceasul managerului). O cerere noua a aceluiasi client o inlocuieste pe cea veche (ultima
		castiga): functia veche primeste motivul."""
		vechi = self._asteptari.pop(cine, None)
		self._asteptari[cine] = (functie, self._monoton() + max(0, termen_s))
		self._dupaSchimbare()
		if vechi is not None:
			try:
				vechi[0](_("Ai ales alt canal."))
			except Exception as e:
				_jurnal("asteptarea inlocuita: %r" % (e,))

	def renuntaAsteptarea(self, cine, functie):
		"""Clientul a plecat inainte de pornire."""
		a = self._asteptari.get(cine)
		if a is not None and a[0] is functie:
			del self._asteptari[cine]
			self._fel_asteptare.pop(cine, None)
			self._dupaSchimbare()

	def _asteptariGata(self):
		"""Ceasul: asteptarile carora le-a venit randul (sau termenul) se cheama; fiecare incearca din nou pornirea. Cea
		care asteapta pauza dintre porniri (PREA_REPEDE) are randul cand trece pauza, cea criptata cand trece si pauza
		criptatelor (ASTEPTARILE PLAYERELOR EXTERNE, sus)."""
		for cine, (functie, termen) in list(self._asteptari.items()):
			if self._fel_asteptare.get(cine) == PREA_REPEDE:
				are_randul = self.msPanaLaPornire() == 0
			else:
				are_randul = self.secundeCriptat() == 0
			if not are_randul and self._monoton() < termen:
				continue
			if self._asteptari.get(cine, (None,))[0] is functie:
				del self._asteptari[cine]
				self._fel_asteptare.pop(cine, None)
			try:
				functie(None)
			except Exception as e:
				_jurnal("asteptarea unui player extern: %r" % (e,))

	# ------------------------------------------------------------ urmeaza televizorul (URMEAZA TELEVIZORUL, sus)
	def starePentruUrmarire(self):
		"""(ce merge pe televizor, ca text sau "", in standby) acum."""
		return (self._tv() or "", bool(self._in_standby()))

	def urmaresteTv(self, functie, ref_stiut, standby_stiut, termen_s, cheie=None):
		"""O pagina care urmeaza televizorul: functie(ref, standby) ruleaza o data, pe firul principal, cand televizorul
		nu mai e pe `ref_stiut` sau `standby_stiut` (zap: _laZap, dupa zap; standby: ceasul) ori la termen. Cine cheama
		verifica inainte daca e deja altfel. `cheie` = pagina (browserul si fereastra): o cerere noua a aceleiasi pagini o
		inlocuieste pe cea veche, care primeste starea de acum. -> intrarea (pentru renuntaUrmarirea) sau None cand sunt
		deja URMARITORI_MAX (functia nu se cheama)."""
		ref, standby = self.starePentruUrmarire()
		for vechi in [u for u in self._urmaritori if cheie is not None and u.cheie == cheie]:
			self._urmaritori.remove(vechi)
			self._cheamaUrmaritor(vechi, ref, standby)
		if len(self._urmaritori) >= URMARITORI_MAX:
			return None
		u = _Urmaritor(functie, ref_stiut, standby_stiut, self._monoton() + max(0, termen_s), cheie)
		self._urmaritori.append(u)
		self._pornesteTrezirea()
		self._dupaSchimbare()
		return u

	def renuntaUrmarirea(self, u):
		"""Pagina a plecat (cererea lunga s-a inchis)."""
		if any(x is u for x in self._urmaritori):
			self._urmaritori = [x for x in self._urmaritori if x is not u]
			self._dupaSchimbare()

	def _anuntaUrmaritorii(self):
		"""Urmaritorii carora televizorul li s-a schimbat (alt canal, standby) sau le-a venit termenul primesc starea de
		acum (firul principal: dupa un zap, ceasul)."""
		if not self._urmaritori:
			return
		ref, standby = self.starePentruUrmarire()
		acum = self._monoton()
		gata = [u for u in self._urmaritori if not _acelasiTv(ref, u.ref) or standby != u.standby or acum >= u.termen]
		if not gata:
			return
		self._urmaritori = [u for u in self._urmaritori if all(u is not g for g in gata)]
		for u in gata:
			self._cheamaUrmaritor(u, ref, standby)
		self._dupaSchimbare()

	@staticmethod
	def _cheamaUrmaritor(u, ref, standby):
		try:
			u.functie(ref, standby)
		except Exception as e:
			_jurnal("o pagina care urmeaza televizorul: %r" % (e,))

	def msPanaLaPornire(self):
		"""Cate milisecunde mai sunt pana cand o pornire noua nu mai e PREA_REPEDE (pagina reincearca atunci)."""
		if self._ultima_pornire is None:
			return 0
		rest = self.pauza_comutare_s - (self._monoton() - self._ultima_pornire)
		return int(math.ceil(rest * 1000)) if rest > 0 else 0

	def mutareTv(self, ref, cine=None):
		""""Vezi live" pe un canal de satelit pe care transmisia nu-l poate lua fara televizor (receptor cu motor sau cu
		un singur tuner de satelit, canalul pe alta frecventa sau pe alt satelit decat televizorul): poate televizorul
		trece pe el (zap ca din telecomanda; antena se poate roti, ca la orice zap)? -> None cand nu e cazul (canalul
		merge asa, standby sau alt refuz: setarile, limita, memoria), (True, None), sau (False, motiv) cand o inregistrare
		tine tunerul pe alta frecventa. Playerele externe nu muta niciodata televizorul."""
		curata = refCurata(ref)
		if curata is None or pozitieSatelit(curata) is None or self._in_standby():
			return None
		ok, _motiv = self.poateIncepe(curata, cine, doar_general=True)
		if not ok or not self.doarFrecventaTv():
			return None
		ref_tv = self._tv()
		if ref_tv and transponder(ref_tv) == transponder(curata):
			return None
		tp = transponder(curata)
		alte = [r for r in (self._inregistrari() or []) if transponder(r) is not None and transponder(r) != tp]
		if alte and not self._tuner(curata, ref_tv):
			return False, _("Tunerul e ocupat de o înregistrare pe altă frecvență.")
		return True, None

	# ------------------------------------------------------------ pornirea
	def poateIncepe(self, ref, cine=None, doar_general=False):
		"""(True, None) sau (False, motiv) inainte de orice inregistrare: setarile, standby, limita, memoria, tunerul,
		satelitul. O sesiune vie a aceluiasi browser pe acelasi canal trece (se refoloseste). `doar_general`: fara tuner
		si antena (mutareTv)."""
		curata = refCurata(ref)
		if curata is None:
			return False, _("Alege un canal din listă.")
		if not self.setari.permis():
			return False, _("Transmisia în browser e oprită din setări (pe televizor sau în această pagină).")
		if self._in_standby() and not self.setari.standby():
			return False, _("Receptorul e în standby. Transmisia în standby e oprită din setări.")
		a_mea = self.sesiunePentru(cine) if cine is not None else None
		if a_mea is not None and _aceeasiRef(a_mea.ref, curata):
			return True, None
		# sesiunea unui player extern plecat nu tine locul (PLAYERELE EXTERNE PLECATE, sus): pornirea o opreste (_faLoc)
		# (si nici una al carei fir s-a incheiat: iese din lista la urmatorul pas al firului principal)
		alte = [s for s in self.vii() if s is not a_mea and not s.fir_gata and not self._cedeazaLocul(s, cine)]
		if len(alte) >= self.setari.sesiuniMax():
			nume = ", ".join(s.browser or s.adresa or "?" for s in alte)
			return False, _("Receptorul transmite deja spre %s. Oprește acea transmisie din pagina TV în browser sau de pe televizor.") % nume
		m = self.memorie(din_nou=True)
		if m is not None:
			if m.get("trebuie_repornit"):
				return False, _("Memoria driverului video e pe sfârșite. Repornește receptorul ca să poți transmite din nou.")
			if m.get("ramase") is not None and m["ramase"] < 1:
				return False, _("Memoria driverului video ar ajunge prea jos. Repornește receptorul ca să poți transmite din nou.")
		if doar_general:
			return True, None
		return self.verificaCanal(curata, a_mea)

	def verificaCanal(self, ref, ignora=None):
		"""Numai tunerul si antena (fara setari, limita si memorie): pentru lista de canale a paginii. `ignora` =
		sesiunea pe care pornirea ar inlocui-o (tunerul ei se socoteste liber). -> (True, None) / (False, motiv)."""
		curata = refCurata(ref)
		if curata is None:
			return False, _("Alege un canal din listă.")
		# antena nu se roteste niciodata din browser: un canal de satelit merge numai pe pozitia canalului de pe
		# televizor (sau, in standby, a canalului de dinainte)
		ref_tv = self._tv()
		poz = pozitieSatelit(curata)
		if poz is not None:
			poz_tv = pozitieSatelit(ref_tv) if ref_tv else None
			if poz_tv is None:
				return False, _("Pentru un canal de satelit, pornește întâi pe televizor un canal de pe același satelit. Antena nu se rotește din browser.")
			if poz != poz_tv:
				return False, _("Canalul e pe alt satelit decât televizorul. Antena ar trebui să se rotească.")
			if transponder(curata) != transponder(ref_tv) and self.doarFrecventaTv():
				return False, _("Pe acest receptor (antenă cu motor sau un singur tuner de satelit) transmisia merge numai cu canalele de pe frecvența televizorului: altfel tunerul s-ar reacorda și antena s-ar putea mișca. Schimbă întâi canalul pe televizor.")
		if not self._acelasiTransponderCuOVie(curata, ignora) and not self._tuner(curata, ignora.ref if ignora else None):
			return False, _("Tunerul e folosit acum pe altă frecvență (de televizor sau de o înregistrare). Alege un canal de pe aceeași frecvență cu televizorul.")
		return True, None

	def doarFrecventaTv(self):
		"""Regula antenei cu motor / a unui singur tuner de satelit, citita cel mult o data la DOAR_FRECVENTA_S."""
		cand, valoare = self._doar_frecventa_citit
		acum = self._monoton()
		if cand is None or acum - cand >= DOAR_FRECVENTA_S or acum < cand:
			valoare = bool(self._doar_frecventa_tv())
			self._doar_frecventa_citit = (acum, valoare)
		return valoare

	def _acelasiTransponderCuOVie(self, ref, ignora=None):
		tp = transponder(ref)
		ref_tv = self._tv()
		if ref_tv and transponder(ref_tv) == tp:
			return True
		return any(transponder(s.ref) == tp for s in self.vii() if s is not ignora)

	def porneste(self, ref, nume, cine, browser="", adresa="", ac3=False, extern=False, fereastra="", preia=False,
			wasm=False):
		"""-> (sesiune, None) sau (None, motiv). Aceeasi sesiune daca browserul o are deja pe acelasi canal; altfel
		sesiunea lui veche se opreste si porneste una noua. FERESTRELE: daca sesiunea browserului e folosita acum de alta
		fereastra (alt `fereastra`), fara `preia` raspunsul e (None, ALTA_FEREASTRA): pagina intreaba omul, nu fura
		transmisia pe tacute. Cu `preia`, sesiunea trece la fereastra noua, iar cea veche afla motivul. `wasm` = pagina
		are playerul wasm (RescrierePsi pastreaza atunci sunetul pe care il decodeaza el, la imaginea MPEG-2).
		CANALELE CRIPTATE: (None, CRIPTAT_OPRIT) cu setarea ascunsa criptate pe Nu; altfel (None, CRIPTAT_ASTEAPTA) cat
		pornirea trebuie sa astepte (secundeCriptat()), fara sa porneasca nimic."""
		a_mea = self.sesiunePentru(cine) if cine else None
		if a_mea is not None and a_mea.folositaDeAlta(fereastra, self._monoton()) and not preia:
			return None, ALTA_FEREASTRA
		ok, motiv = self.poateIncepe(ref, cine)
		if not ok:
			return None, motiv
		criptat = bool(self._criptat(ref))
		if criptat and not self.setari.criptate():
			return None, CRIPTAT_OPRIT
		curata = refCurata(ref)
		preluata = a_mea is not None and bool(fereastra) and bool(a_mea.fereastra) and a_mea.fereastra != fereastra
		motiv_vechi = _("Transmisia a fost preluată de altă fereastră.") if preluata else _("Ai ales alt canal.")
		if a_mea is not None and _aceeasiRef(a_mea.ref, curata):
			if fereastra:
				a_mea.fereastra = fereastra
			a_mea.wasm = bool(wasm)          # se aplica la urmatoarea legare a browserului (PMT-ul se rescrie atunci)
			a_mea.ac3 = bool(ac3)            # la fel (pagina fara decodorul de sunet cere din nou cu ac3=0)
			self._anuleazaAsteptarea(cine)
			return a_mea, None
		# ultima cerere castiga: sesiunea criptata a acestui browser pe acest canal, cu oprirea inca amanata, se reia (pe
		# demux nu porneste si nu se opreste nimic)
		reluata = self._reiaAmanata(cine, curata, fereastra, wasm, ac3)
		if reluata is not None:
			if a_mea is not None:
				self._opresteAcum(a_mea, motiv_vechi, reluabila=True)
				self.oprite.pop(cine, None)
			return reluata, None
		self._opririAmanate()
		# locul tinut de un player extern plecat se elibereaza INAINTEA serializarii criptatelor: oprirea lui intra in
		# pauza pornirilor criptate (secundeCriptat), nu se trece peste ea
		self._faLoc(cine)
		if criptat:
			# serializarea (CANALELE CRIPTATE): fara suprapunere cu o sesiune criptata sau de pe alt transponder (intai
			# oprirea ei, amanata daca e prea noua, apoi pauza); una necriptata de pe acelasi transponder se opreste dupa
			# pornire, ca pana acum (canalul de inregistrare al demuxului ramane deschis)
			if a_mea is not None and (a_mea.canal_criptat or transponder(a_mea.ref) != transponder(curata)):
				self._opresteAcum(a_mea, motiv_vechi, reluabila=True)
				self.oprite.pop(cine, None)
				a_mea = None
			secunde = self.secundeCriptat()
			if secunde > 0:
				_jurnal("pornire criptata in asteptare %s (%s): %d s" % (curata, browser or adresa or "-", secunde))
				if cine and extern:
					self._fel_asteptare[cine] = CRIPTAT_ASTEAPTA   # numai playerele externe asteapta in cerere
				return None, CRIPTAT_ASTEAPTA
		# pe acelasi transponder cea veche se opreste abia dupa ce porneste cea noua (canalul de inregistrare al
		# demux-ului ramane deschis); pe alt transponder intai cea veche (tunerul ei)
		# comutarile foarte rapide asteapta (inainte sa se opreasca ceva, ca un refuz sa nu lase browserul fara sesiune)
		acum = self._monoton()
		if self._ultima_pornire is not None and acum - self._ultima_pornire < self.pauza_comutare_s:
			if cine and extern:
				self._fel_asteptare[cine] = PREA_REPEDE
			return None, PREA_REPEDE
		self._ultima_pornire = acum
		inainte = a_mea is not None and transponder(a_mea.ref) == transponder(curata)
		if a_mea is not None and not inainte:
			# tunerul ei trebuie sa fie liber pe loc (o sesiune criptata de acolo e pe alt demux decat televizorul)
			self._opresteAcum(a_mea, motiv_vechi, fortat=True)
		self.oprite.pop(cine, None)
		ses = Sesiune(binascii.hexlify(os.urandom(6)).decode("ascii"), curata, nume or curata, cine, browser, adresa,
			self._perete(), self._monoton())
		ses.ac3 = bool(ac3)
		ses.extern = bool(extern)
		ses.wasm = bool(wasm)
		ses.fereastra = fereastra or ""
		ses.canal_criptat = criptat
		if criptat:
			# DECRIPTAREA: de aici se citesc raspunsurile camului (ce scrie el de acum incolo in jurnal)
			ses.decriptare = DECRIPTARE_ASTEAPTA
			self._jurnal_cam.marcheaza()
		self._pornesteTrezirea()
		eroare = self._inregistrare.porneste(ses)
		if eroare:
			self._opresteInregistrarea(ses)
			self._inchideR(ses)
			_jurnal("sesiune refuzata %s (%s): %s" % (curata, browser or adresa, eroare))
			return None, eroare
		# sesiunea noua intra in lista inaintea opririi celei vechi: semnul "in retea" (transmise()) trece direct pe
		# canalul nou, fara o clipa fara nimic
		self.sesiuni.append(ses)
		if inainte:
			self._opresteAcum(a_mea, motiv_vechi, reluabila=True)
			self.oprite.pop(cine, None)
		if a_mea is None or not inainte:
			self._contor()
		self._anuntaTransmise()
		ses.fir = threading.Thread(target=self._firSesiune, args=(ses,), name="hdstv")
		ses.fir.daemon = True
		ses.fir.start()
		_jurnal("sesiune pornita %s %s spre %s (%s)%s" % (ses.id, curata, browser or "-", adresa or "-",
			", criptata" if criptat else ""))
		self._anuleazaAsteptarea(cine)
		self._dupaSchimbare()
		return ses, None

	def _anuleazaAsteptarea(self, cine):
		"""Dupa o pornire reusita a clientului `cine`: o cerere mai veche a lui care inca asteapta (alt canal) primeste
		motivul, ca sa nu porneasca mai tarziu peste cea noua (ultima cerere castiga)."""
		a = self._asteptari.pop(cine, None) if cine else None
		self._fel_asteptare.pop(cine, None)
		if a is None:
			return
		try:
			a[0](_("Ai ales alt canal."))
		except Exception as e:
			_jurnal("asteptarea inlocuita: %r" % (e,))

	def _asteptareFara(self, ses):
		"""Cat traieste o sesiune fara nimeni legat: setarea asteptare; la un player extern cel mult EXTERN_FARA_CLIENT_S."""
		asteptare = self.setari.asteptare()
		return min(asteptare, EXTERN_FARA_CLIENT_S) if ses.extern else asteptare

	def _cedeazaLocul(self, ses, cine=None):
		"""Sesiunea unui player extern al altui client, fara legatura de cel putin EXTERN_PREDA_S si fara una pe drum: nu
		tine locul altora (PLAYERELE EXTERNE PLECATE, sus)."""
		return (ses.extern and ses.cine != cine and not ses.cu_client and ses.client_nou is None
			and self._monoton() - ses.fara_spectator_din >= EXTERN_PREDA_S)

	def _faLoc(self, cine):
		"""Inaintea unei porniri noi: cat limita de sesiuni e atinsa de altii, sesiunile playerelor externe plecate se
		opresc (cea mai veche plecare intai)."""
		alte = [s for s in self.vii() if s.cine != cine and not s.fir_gata]
		plecate = sorted((s for s in alte if self._cedeazaLocul(s, cine)), key=lambda s: s.fara_spectator_din)
		while plecate and len(alte) >= self.setari.sesiuniMax():
			s = plecate.pop(0)
			alte.remove(s)
			_jurnal("sesiune %s %s: playerul extern a plecat, locul trece la alta transmisie" % (s.id, s.ref))
			self._opresteAcum(s, _("Nimeni nu se mai uita."), cod="fara_spectator")

	def alegePista(self, cine, pid):
		"""Pista audio a fluxului acestui browser (PID din `piste`). Se aplica la urmatoarea legare a browserului (pagina
		reconecteaza fluxul). -> (True, None) sau (False, motiv)."""
		ses = self.sesiunePentru(cine) if cine else None
		if ses is None:
			return False, _("Nu transmite nimic spre acest browser.")
		try:
			pid = int(pid)
		except (TypeError, ValueError):
			return False, _("Pista audio nu e un număr.")
		for p in ses.piste or []:
			if p.get("pid") == pid:
				if not p.get("merge"):
					return False, _("Această pistă audio nu se aude în browser.")
				ses.pista = pid
				return True, None
		return False, _("Pista audio nu există (poate s-a schimbat emisiunea).")

	# ------------------------------------------------------------ browserul
	def ataseaza(self, ses, fd, la_plecare):
		"""Leaga soclul `fd` (al nostru, cu antetul HTTP deja trimis) de sesiune; un browser legat inainte e lasat
		(`la_plecare` lui ruleaza pe firul principal). -> False daca sesiunea s-a oprit intre timp."""
		if ses.oprita.is_set() or ses not in self.sesiuni:
			return False
		with ses.lacat:
			if ses.fir_gata:
				# firul s-a incheiat (inca neaflat aici): legatura n-ar mai lua-o nimeni
				return False
			vechi, ses.client_nou = ses.client_nou, (fd, la_plecare)
		if vechi is not None:
			_inchideFd(vechi[0])
			self._cheamaPlecarea(vechi[1])
		ses.cu_client = True
		return True

	def _cheamaPlecarea(self, la_plecare):
		if la_plecare is None:
			return
		try:
			la_plecare()
		except Exception as e:
			_jurnal("inchiderea legaturii: %r" % (e,))

	# ------------------------------------------------------------ oprirea
	def opreste(self, sid, motiv=None):
		for s in self.vii():
			if s.id == sid:
				self._opresteAcum(s, motiv or _("Transmisia a fost oprită."), reluabila=True, cod="oprita")
				return True
		return False

	def opresteToate(self, motiv):
		n = 0
		for s in self.vii():
			self._opresteAcum(s, motiv)
			n += 1
		return n

	def _opresteAcum(self, ses, motiv, fortat=False, reluabila=False, cod=None):
		"""Firul principal: inregistrarea se opreste pe loc (tunerul e liber cand se intoarce functia); firul sesiunii
		vede teava inchisa, lasa browserul si incheie. O sesiune criptata mai noua de VARSTA_CRIPTAT_S (fara `fortat`):
		pentru pagina e oprita acum (browserul e lasat), dar inregistrarea se opreste abia la varsta ei (ceasul,
		_opririAmanate); pana atunci firul citeste teava in gol. `reluabila` = oprirea amanata se anuleaza daca acelasi
		browser cere din nou acelasi canal. `cod` = de ce, pentru pagina (oprite[cine][2]: "zap", "inregistrare",
		"standby", "setari", "tuner", "fara_date", "fara_spectator", "oprita", "nedecriptat"; None = altceva)."""
		if ses.motiv is None:
			ses.motiv = motiv
		if ses.cine:
			self.oprite[ses.cine] = (motiv, self._perete(), cod)
		self._decriptareGata(ses, motiv or _("Transmisia s-a oprit."))
		if not fortat and ses.canal_criptat and ses.rec is not None and self._monoton() < self._capatVarsta(ses):
			ses.reluabila = bool(reluabila)
			if ses not in self._amanate:
				self._amanate.append(ses)
				_jurnal("oprire amanata %s %s: %.1f s pana la varsta minima" % (ses.id, ses.ref,
					self._capatVarsta(ses) - self._monoton()))
		else:
			self._opresteInregistrarea(ses)
		ses.oprita.set()
		self._dupaSchimbare()

	def _opresteInregistrarea(self, ses):
		"""Oprirea adevarata (rec.stop si capatul de scriere al tevii); ora ei porneste pauza pornirilor criptate."""
		if ses in self._amanate:
			self._amanate.remove(ses)
		avea = ses.rec is not None
		self._inregistrare.opreste(ses)
		self._anuntaTransmise()
		# numai oprirea unei sesiuni criptate (sau aflate criptata dupa pornire: decriptare stiuta) porneste pauza
		# pornirilor criptate; o oprire necriptata nu leaga chei
		if avea and (ses.canal_criptat or ses.decriptare is not None):
			self._ultima_oprire = self._monoton()
			_jurnal("inregistrare criptata oprita %s %s" % (ses.id, ses.ref))

	def _sesiuneTerminata(self, ses):
		"""Firul principal, chemat de firul sesiunii la sfarsit."""
		if not ses.oprita.is_set():
			self._opresteAcum(ses, ses.motiv or _("Transmisia s-a oprit."), fortat=True)
		# o oprire amanata nu mai asteapta: nimeni nu mai citeste teava
		self._opresteInregistrarea(ses)
		if ses in self.sesiuni:
			self.sesiuni.remove(ses)
			durata = int(max(0, self._monoton() - ses.inceput_mon))
			self.jurnal.append({"ora": int(self._perete()), "browser": ses.browser, "adresa": ses.adresa,
				"canal": ses.nume, "secunde": durata, "octeti": int(ses.octeti), "motiv": ses.motiv or ""})
			_jurnal("sesiune incheiata %s %s: %s, %d octeti in %d s" % (ses.id, ses.ref, ses.motiv or "-", ses.octeti,
				durata))
		self._dupaSchimbare()

	def verifica(self):
		"""Ceasul (firul principal, cat exista sesiuni, opriri amanate sau asteptari): opririle amanate ajunse la varsta,
		standby, setarea oprita, inregistrari cazute (oprire pe loc), sesiuni fara date, sesiuni fara spectator, apoi
		playerele externe carora le-a venit randul."""
		acum = self._monoton()
		standby = self._in_standby()
		self._opririAmanate()
		for s in self.vii():
			if s.id in self._asteptari_decriptare:
				s.fara_spectator_din = acum      # un player extern asteapta decriptarea: se uita cineva
			if not self.setari.permis():
				self._opresteAcum(s, _("Transmisia în browser a fost oprită din setări."), cod="setari")
			elif standby and not self.setari.standby():
				self._opresteAcum(s, _("Receptorul a intrat în standby."), cod="standby")
			elif self._inregistrare.eroare(s):
				self._opresteAcum(s, _("Canalul nu mai poate fi primit (tunerul s-a pierdut sau a fost luat)."),
					fortat=True, cod="tuner")
			elif (s.ultim_octet_mon or s.inceput_mon) + FARA_DATE_S < acum and not self._faraDateCriptat(s):
				self._opresteAcum(s, _("Canalul nu mai trimite date."), cod="fara_date")
			elif not s.cu_client and s.fara_spectator_din + self._asteptareFara(s) < acum:
				self._opresteAcum(s, _("Nimeni nu se mai uita."), cod="fara_spectator")
		self._decriptarea()
		self._asteptariDecriptariiLaTermen()
		self._asteptariGata()
		self._anuntaUrmaritorii()
		self._dupaSchimbare()

	# ------------------------------------------------------------ decriptarea (DECRIPTAREA, sus)
	def _decriptarea(self):
		"""Ceasul: sesiunile care asteapta decriptarea. Imaginea clara = "merge"; un refuz definitiv al camului sau niciun
		raspuns (DECRIPTARE_FARA_RASPUNS_S; cu raspunsuri nehotarate DECRIPTARE_MAX_S; amandoua dupa TERMENELE
		DECRIPTARII, sus, cel mai devreme la DECRIPTARE_MIN_S de la primele date) = "nu" si oprirea. Un canal stiut
		necriptat al carui flux iese criptat intra si el aici."""
		acum = self._monoton()
		asteapta = []
		for s in self.vii():
			if s.decriptare is None and s.criptat is not True and self._criptatTarziu(s, acum):
				# ACEEASI VERIFICARE PE AMBELE CAI (sus): canalul pornit ca necriptat se arata acum criptat
				s.decriptare = DECRIPTARE_ASTEAPTA
				self._jurnal_cam.marcheaza()
				_jurnal("sesiune %s %s: canal criptat, aflat dupa pornire" % (s.id, s.ref))
			if s.decriptare is None and s.criptat is True:
				s.decriptare = DECRIPTARE_ASTEAPTA
				self._jurnal_cam.marcheaza()
			if s.decriptare == DECRIPTARE_MERGE and s.criptat is True:
				s.decriptare = DECRIPTARE_ASTEAPTA      # cheia s-a pierdut (alt cuvant de control, cardul scos)
				s.decriptare_din = acum
			if s.decriptare == DECRIPTARE_ASTEAPTA:
				asteapta.append(s)
		if not asteapta:
			self._jurnal_cam.opreste()
			return
		self._jurnal_cam.citeste(acum)
		for s in asteapta:
			if s.criptat is False or (s.criptat is None and s.piste and not s.video):
				# imaginea iese clara (sau canalul n-are imagine: un post de radio nu se judeca dupa ea)
				s.decriptare = DECRIPTARE_MERGE
				_jurnal("sesiune %s %s: decriptata" % (s.id, s.ref))
				self._decriptareGata(s, None)
				continue
			c = campuriRef(s.ref)
			baza = s.decriptare_din or (s.prim_octet_mon if s.prim_octet_mon is not None else s.inceput_mon)
			trecut = acum - baza
			raspuns = self._jurnal_cam.raspuns(c[1] if c else None, s.inceput_mon, acum, baza)
			# TERMENELE DECRIPTARII (sus): de la zap-ul televizorului pe acest canal, cand e mai devreme; nu si cand
			# cheia s-a pierdut dupa ce a mers (decriptare_din), atunci numai de acolo
			if s.extern:
				tot, minim = trecut, 0
				termen = DECRIPTARE_EXTERN_FARA_RASPUNS_S if raspuns is None else DECRIPTARE_EXTERN_MAX_S
			else:
				tot, minim = acum - (baza if s.decriptare_din else self._bazaDecriptare(s, baza)), DECRIPTARE_MIN_S
				termen = DECRIPTARE_FARA_RASPUNS_S if raspuns is None else DECRIPTARE_MAX_S
			if raspuns == "refuzat" or (trecut >= minim and tot >= termen):
				s.decriptare = DECRIPTARE_NU
				_jurnal("sesiune %s %s: nedecriptata (%s, %.0f s, %.0f s de la zap)" % (s.id, s.ref,
					raspuns or "fara raspuns", trecut, tot))
				self._opresteAcum(s, _(TEXT_NEDECRIPTAT), cod="nedecriptat")

	def _bazaDecriptare(self, s, baza):
		"""Ceasul monoton de la care se socotesc termenele decriptarii: `baza` (primele date ale sesiunii) sau zap-ul
		televizorului pe acelasi canal, daca a fost mai devreme si televizorul e tot acolo."""
		zap = self._zap_tv
		if zap is None or zap[1] >= baza or not _aceeasiRef(zap[0], s.ref):
			return baza
		try:
			if not _acelasiTv(self._tv(), s.ref):
				return baza
		except Exception as e:
			_jurnal("canalul televizorului: %r" % (e,))
			return baza
		return zap[1]

	def _faraDateCriptat(self, s):
		"""Sesiunea unui canal criptat la care inregistrarea n-a dat inca niciun octet (proba din 14.10: Sky Sport UHD,
		octeti 0): nu e "Canalul nu mai trimite date." (oprire, pagina pornea din nou, iar pauza criptatelor facea o
		bucla), ci un canal pe care receptorul nu-l poate decripta; il opreste _decriptarea, la termenele ei."""
		return (s.decriptare == DECRIPTARE_ASTEAPTA and s.prim_octet_mon is None and not s.decriptare_din
			and not s.extern)

	def _criptatTarziu(self, s, acum):
		"""Sesiunea pornita ca necriptata: canalCriptat() spune acum Da (PMT-ul televizorului a venit, accesul s-a tinut
		minte)? Numai cat sesiunea e tanara: pana la DECRIPTARE_FARA_RASPUNS_S de la primele date (fara date: de la pornire)."""
		baza = s.prim_octet_mon if s.prim_octet_mon is not None else s.inceput_mon
		if acum - baza > DECRIPTARE_FARA_RASPUNS_S:
			return False
		try:
			return bool(self._criptat(s.ref))
		except Exception as e:
			_jurnal("criptat dupa pornire: %r" % (e,))
			return False

	def asteaptaDecriptarea(self, ses, functie, termen_s):
		"""Playerele externe: functie(None) cand imaginea sesiunii iese clara (fluxul poate pleca), functie(motiv) cand
		camul nu o decripteaza, sesiunea se opreste sau trece termenul (motiv = None si la termen: atunci cine asteapta
		hotaraste). O cerere noua pe aceeasi sesiune o inlocuieste pe cea veche."""
		vechi = self._asteptari_decriptare.pop(ses.id, None)
		self._asteptari_decriptare[ses.id] = (functie, self._monoton() + max(0, termen_s))
		self._dupaSchimbare()
		if vechi is not None:
			try:
				vechi[0](_("Ai ales alt canal."))
			except Exception as e:
				_jurnal("asteptarea decriptarii inlocuita: %r" % (e,))

	def renuntaDecriptarea(self, ses, functie):
		a = self._asteptari_decriptare.get(ses.id)
		if a is not None and a[0] is functie:
			del self._asteptari_decriptare[ses.id]
			self._dupaSchimbare()

	def _decriptareGata(self, ses, motiv):
		"""Asteptarea decriptarii a sesiunii se incheie: motiv None = imaginea e clara, altfel de ce nu pleaca fluxul."""
		a = self._asteptari_decriptare.pop(ses.id, None)
		if a is None:
			return
		try:
			a[0](motiv)
		except Exception as e:
			_jurnal("asteptarea decriptarii: %r" % (e,))

	def _asteptariDecriptariiLaTermen(self):
		acum = self._monoton()
		for sid, (functie, termen) in list(self._asteptari_decriptare.items()):
			if acum < termen:
				continue
			del self._asteptari_decriptare[sid]
			try:
				functie(None)
			except Exception as e:
				_jurnal("asteptarea decriptarii la termen: %r" % (e,))

	# ------------------------------------------------------------ prioritatea televizorului si a inregistrarilor
	def cedeaza(self, ref, motiv, cod=None):
		"""Inainte ca enigma2 sa porneasca `ref` (zap sau inregistrare): daca nu are tuner liber, sesiunile de pe alt
		transponder se opresc pe loc. -> cate s-au oprit."""
		tp = transponder(ref)
		if tp is None:
			return 0
		# si sesiunile cu oprirea amanata: inregistrarea lor tine inca tunerul; aici nimic nu se amana
		alte = [s for s in self.vii() + self._amanate if transponder(s.ref) != tp]
		if not alte or self._tuner(refCurata(ref) or ref, None):
			return 0
		for s in alte:
			if s.oprita.is_set():
				self._opresteInregistrarea(s)
			else:
				self._opresteAcum(s, motiv, fortat=True, cod=cod)
		self._dupaSchimbare()
		_jurnal("%d sesiuni oprite pentru %s: %s" % (len(alte), ref, motiv))
		return len(alte)

	def _laZap(self, nav, playref, *rest):
		try:
			# TERMENELE DECRIPTARII: de cand e televizorul pe canal
			self._zap_tv = (refCurata(_refText(playref)), self._monoton())
		except Exception as e:
			_jurnal("zap, ora: %r" % (e,))
		try:
			self.cedeaza(_refText(playref), _("Transmisia s-a oprit: televizorul a trecut pe un canal de pe altă frecvență."),
				cod="zap")
		except Exception as e:
			_jurnal("zap: %r" % (e,))
		if self._urmaritori:
			# paginile care urmeaza televizorul afla dupa zap (pe firul principal, cand s-a intors playService)
			self.cere(self._anuntaUrmaritorii)
		return playref

	def _laInregistrare(self, nav, ref, *rest):
		simulare = False
		try:
			import sys
			simulare = bool(sys._getframe(1).f_locals.get("simulate", False))
		except Exception:
			simulare = False
		if not simulare:
			try:
				self.cedeaza(_refText(ref), _("Transmisia s-a oprit: a pornit o înregistrare pe altă frecvență."),
					cod="inregistrare")
			except Exception as e:
				_jurnal("inregistrare: %r" % (e,))
		return ref

	def _listeNavigatie(self):
		nav = self._navigatie
		if nav is None:
			try:
				from Navigation import Navigation as nav
			except Exception:
				return ()
		return ((getattr(nav, "playServiceExtensions", None), self._laZap),
			(getattr(nav, "recordServiceExtensions", None), self._laInregistrare))

	def _puneExtensiile(self):
		if self._extensii:
			return
		for lista, f in self._listeNavigatie():
			if isinstance(lista, list) and f not in lista:
				lista.insert(0, f)
		self._extensii = True

	def _scoateExtensiile(self):
		if not self._extensii:
			return
		self._extensii = False
		for lista, f in self._listeNavigatie():
			while isinstance(lista, list) and f in lista:
				lista.remove(f)

	# ------------------------------------------------------------ firul sesiunii
	def _firSesiune(self, ses):
		r = ses.r
		client, la_plecare, sincron, rest = None, None, False, b""
		c = campuriRef(ses.ref)
		sid = c[1] if c else None
		pat = RescrierePsi(sid, ses.ac3, ses.pista, ses.extern, ses.wasm)
		try:
			while True:
				# browserul nou se ia si inainte, si dupa asteptare: datele venite imediat dupa legare ajung la el
				with ses.lacat:
					nou, ses.client_nou = ses.client_nou, None
				if nou is not None:
					if client is not None:
						self._lasaClientul(ses, client, la_plecare, legat_altul=True)
					client, la_plecare = nou
					sincron, rest = False, b""
					ses.cu_client = True
					# fiecare browser legat primeste PAT-ul si PMT-ul de la capat, cu pista aleasa acum
					pat = RescrierePsi(sid, ses.ac3, ses.pista, ses.extern, ses.wasm)
				citite = [r] if client is None else [r, client]
				try:
					gata = select.select(citite, [], [], 0.5)[0]
				except (OSError, ValueError, select.error) as e:
					if getattr(e, "errno", None) == errno.EINTR:
						continue
					break
				with ses.lacat:
					nou, ses.client_nou = ses.client_nou, None
				if nou is not None:
					if client is not None:
						self._lasaClientul(ses, client, la_plecare, legat_altul=True)
					client, la_plecare = nou
					sincron, rest = False, b""
					ses.cu_client = True
					# fiecare browser legat primeste PAT-ul si PMT-ul de la capat, cu pista aleasa acum
					pat = RescrierePsi(sid, ses.ac3, ses.pista, ses.extern, ses.wasm)
					gata = [x for x in gata if x == r]
				if client is not None and ses.oprita.is_set():
					# oprita pentru pagina (oprirea criptata amanata): browserul e lasat, teava se citeste in gol
					self._lasaClientul(ses, client, la_plecare)
					client, la_plecare = None, None
				if client is not None and client in gata:
					# soclul e neblocant (descriptorul copiat al Twisted-ului): EAGAIN nu inseamna plecare
					try:
						b = os.read(client, 4096)
					except OSError as e:
						b = None if e.errno in (errno.EAGAIN, errno.EINTR) else b""
					if b is None:
						pass
					elif not b:
						self._lasaClientul(ses, client, la_plecare)
						client, la_plecare = None, None
						continue
				if r not in gata:
					continue
				try:
					b = os.read(r, BLOC)
				except OSError as e:
					if e.errno in (errno.EAGAIN, errno.EINTR):
						continue
					break
				if not b:
					break
				ses.ultim_octet_mon = monoton()
				if ses.prim_octet_mon is None:
					ses.prim_octet_mon = ses.ultim_octet_mon
				# fara browser legat fluxul se citeste in gol; cat nu s-a hotarat decriptarea (DECRIPTAREA) se cerceteaza
				# totusi (PMT-ul si bitii de criptare ai imaginii), ca un player extern care asteapta sa afle cand pleaca
				if client is None and ses.decriptare != DECRIPTARE_ASTEAPTA:
					continue
				rest += b
				if not sincron:
					i = _sincron(rest)
					if i < 0:
						rest = rest[-3 * TS:]
						continue
					rest, sincron = rest[i:], True
				k = len(rest) - len(rest) % TS
				if not k:
					continue
				date, rest = rest[:k], rest[k:]
				if date[0] != 0x47:
					rest, sincron = date + rest, False
					continue
				date = pat.filtreaza(date)
				if pat.video and ses.video != pat.video:
					ses.video = pat.video
				if pat.pmt_citit:
					# un PMT nou: pistele adevarate ale fluxului, pentru pagina (lista pistelor si avertizarea din
					# Sesiune.descriere; imaginea e pusa inainte)
					pat.pmt_citit = False
					ses.piste = pat.piste
					ses.pmt_citit = True
				if pat.criptat is not None:
					ses.criptat = pat.criptat
				ses.video_pachete = pat.video_pachete
				if client is None:
					continue
				if not _trimiteTot(client, date):
					self._lasaClientul(ses, client, la_plecare)
					client, la_plecare = None, None
					continue
				ses.octeti += len(date)
		except Exception as e:
			ses.motiv = ses.motiv or (_("Eroare la transmisie: %s") % e)
		finally:
			if client is not None:
				self._lasaClientul(ses, client, la_plecare)
			# sub acelasi lacat cu ataseaza: dupa el nicio legatura nu mai intra in client_nou
			with ses.lacat:
				nou, ses.client_nou = ses.client_nou, None
				ses.fir_gata = True
			if nou is not None:
				_inchideFd(nou[0])
				self.cere(self._cheamaPlecarea, nou[1])
			self._inchideR(ses)
			self.cere(self._sesiuneTerminata, ses)

	def _lasaClientul(self, ses, fd, la_plecare, legat_altul=False):
		"""Firul sesiunii: soclul nostru se inchide; legatura Twisted se inchide pe firul principal."""
		_inchideFd(fd)
		with ses.lacat:
			asteapta_altul = ses.client_nou is not None
		if not legat_altul and not asteapta_altul:
			ses.cu_client = False
			ses.fara_spectator_din = monoton()
		self.cere(self._cheamaPlecarea, la_plecare)

	@staticmethod
	def _inchideR(ses):
		r, ses.r = ses.r, None
		if r is not None:
			_inchideFd(r)


def _refText(ref):
	if ref is None:
		return ""
	try:
		return ref.toString()
	except AttributeError:
		return str(ref)


def _inchideFd(fd):
	try:
		os.close(fd)
	except (OSError, TypeError):
		pass


def _neblocant(fd):
	import fcntl
	fl = fcntl.fcntl(fd, fcntl.F_GETFL)
	fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


def _asteaptaScriere(fd, secunde):
	try:
		return bool(select.select([], [fd], [], secunde)[1])
	except (OSError, ValueError, select.error):
		return False


def _trimiteTot(fd, date):
	"""Soclul e neblocant (al Twisted-ului): scrie tot, asteptand cel mult TRIMITERE_S de fiecare data."""
	vedere = memoryview(date)
	while len(vedere):
		try:
			n = os.write(fd, vedere)
		except OSError as e:
			if e.errno in (errno.EAGAIN, errno.EINTR):
				if not _asteaptaScriere(fd, TRIMITERE_S):
					return False
				continue
			return False
		vedere = vedere[n:]
	return True


trimiteTot = _trimiteTot


class SectiuniPsi(object):
	"""Sectiunile PSI ale unui PID, adunate din pachetele TS. O sectiune poate trece peste mai multe pachete (PMT-ul cu
	multe fluxuri: Das Erste HD, 19,2E, are 12 fluxuri, 191 de octeti, pe doua pachete), iar un pachet poate avea
	sfarsitul uneia si inceputul alteia (campul pointer spune unde incepe prima sectiune noua; ce e inaintea ei incheie
	sectiunea de dinainte). pune(pachet) -> sectiunile terminate in acest pachet, fiecare (octetii, bun): bun = CRC32-ul
	ei e bun (o sectiune la fel cu ultima buna nu se mai socoteste; PSI-ul se repeta de cateva ori pe secunda).
	Sectiunea inceputa se lasa deoparte (`rupte` creste) la contorul de continuitate rupt, la un pachet cu eroare de
	transport, la indicatorul de discontinuitate si la o lungime peste SECTIUNE_MAX. Un pachet repetat (acelasi contor,
	aceiasi octeti) nu se adauga a doua oara; pachetele fara date (numai camp de adaptare) nu schimba nimic."""

	SECTIUNE_MAX = 1024          # PSI: section_length cel mult 1021 (ISO/IEC 13818-1)

	def __init__(self):
		self._buf = None             # sectiunea inceputa (bytearray), None = niciuna
		self._cc = None
		self._ultimul = None         # ultimul pachet primit (pentru pachetele repetate)
		self._buna = None            # ultima sectiune cu CRC-ul bun
		self.rupte = 0

	def _lasa(self):
		if self._buf is not None:
			self.rupte += 1
			self._buf = None

	def pune(self, pachet):
		rez = []
		if pachet[1] & 0x80:                         # transport_error_indicator
			self._lasa()
			self._cc = self._ultimul = None
			return rez
		afc = (pachet[3] >> 4) & 0x03
		if not afc & 0x01:                           # fara date: contorul nu creste
			return rez
		cc = pachet[3] & 0x0F
		inceput = 4
		if afc & 0x02:
			if pachet[4] and pachet[5] & 0x80:       # discontinuity_indicator
				self._lasa()
				self._cc = None
			inceput += 1 + pachet[4]
		if self._cc is not None and cc == self._cc:
			if pachet == self._ultimul:
				return rez                           # pachet repetat
			self._lasa()
		elif self._cc is not None and cc != ((self._cc + 1) & 0x0F):
			self._lasa()
		self._cc, self._ultimul = cc, pachet
		if inceput >= TS:
			self._lasa()
			return rez
		corp = pachet[inceput:]
		if not pachet[1] & 0x40:
			if self._buf is not None:
				self._adauga(corp, rez)
			return rez
		pointer = corp[0]
		if 1 + pointer > len(corp):
			self._lasa()
			return rez
		if self._buf is not None:
			self._adauga(corp[1:1 + pointer], rez)
			self._lasa()                             # neterminata cand incepe alta: stricata
		rest = corp[1 + pointer:]
		while rest and rest[0] != 0xFF:
			self._buf = bytearray()
			rest = self._adauga(rest, rez)
		return rez

	def _adauga(self, octeti, rez):
		"""Adauga la sectiunea inceputa; cand se termina, o pune in `rez` si intoarce ce urmeaza dupa ea in `octeti`."""
		self._buf += octeti
		if len(self._buf) < 3:
			return b""
		lungime = 3 + (((self._buf[1] & 0x0F) << 8) | self._buf[2])
		if lungime > self.SECTIUNE_MAX:
			self._lasa()
			return b""
		if len(self._buf) < lungime:
			return b""
		s, rest = bytes(self._buf[:lungime]), bytes(self._buf[lungime:])
		self._buf = None
		bun = s == self._buna or crc32Mpeg(s) == 0
		if bun:
			self._buna = s
		rez.append((s, bun))
		return rest


class RescrierePsi(object):
	"""PAT-ul si PMT-ul fluxului spre browser, rescrise pentru mpegts.js.

	PAT: inregistrarea enigma2 copiaza PAT-ul intreg al transponderului (toate programele), dar numai PMT-ul serviciului
	inregistrat; mpegts.js alege primul program din PAT si ar astepta un PMT care nu vine. Fiecare sectiune PAT buna se
	inlocuieste cu un PAT cu un singur program, serviciul nostru, cu PID-ul PMT-ului lui (un PAT pe mai multe sectiuni:
	PID-ul PMT se ia din sectiunea care are serviciul).
	PMT: mpegts.js ia prima pista audio din PMT si, cat nu ii intelege cadrele, nu porneste nici imaginea (masurat: sunetul
	HE-AAC LATM, tipul 0x11, de pe 19,2E). Raman imaginea (H.264, HEVC, MPEG-2) si o singura pista audio, in ordinea
	MP2 / MP3, AAC ADTS, apoi AC-3 numai daca browserul il reda (`ac3`; AC-3 DVB, 0x06 cu descriptorul 0x6A, se scrie ca
	0x81, singurul pe care mpegts.js il recunoaste). LATM, E-AC-3, subtitrarile, teletextul si datele ies din PMT (pachetele
	lor trec mai departe, mpegts.js nu le citeste). Fara nicio pista buna ramane numai imaginea. Numai PMT-ul programului
	nostru (program_number = serviciul): alte PMT-uri de pe acelasi PID nu mai pleaca.
	SECTIUNILE LUNGI: PAT-ul si PMT-ul se aduna pe mai multe pachete (SectiuniPsi: contorul de continuitate, campul
	pointer, section_length, CRC32 verificat); PMT-ul rescris se scrie pe cate pachete trebuie (de obicei unul) in locul
	pachetului care termina sectiunea originala, iar celelalte pachete ale ei nu mai pleaca. Cat nu exista inca nimic al
	nostru (inainte de prima sectiune buna, serviciul lipsa din PAT, playerele externe), pachetele trec cum vin: o sectiune
	stricata nu lasa browserul fara PMT (mpegts.js isi aduna singur sectiunile si o lasa pe cea neterminata cand vine
	inceputul alteia). Pachetele unei sectiuni stricate dupa ce avem PAT-ul / PMT-ul nostru nu pleaca.
	PISTA ALEASA (tv-osd-suprapus): `pista` = PID-ul pistei audio cerute din pagina; daca e o pista pe care
	browserul o poate reda, ea ramane in PMT in locul celei de mai sus. `piste` = pistele audio ale serviciului din ultimul
	PMT citit ([{"pid", "fel", "limba", "rol", "merge", "aleasa"}], `rol`: "descriere" = descriere audio, "clar" = vorbire
	clara, "" = obisnuita; vezi _limbaSiRol), pentru pagina; `pmt_citit` = s-a citit un PMT nou (il sterge firul sesiunii).
	Rescrierea se face din nou la fiecare browser legat (firul sesiunii), deci o pista noua inseamna o reconectare a
	paginii, nu o schimbare de PMT in mijlocul fluxului.
	PMT INTREG (`intreg`, playerele externe ca VLC si Kodi): numai PAT-ul se rescrie; PMT-ul trece neschimbat, cu toate
	pistele audio, subtitrarile si teletextul (playerul alege singur si decodeaza si MPEG-2); pistele se citesc totusi.
	PLAYERUL WASM (`wasm`): pagina decodeaza singura imaginea MPEG-2 / MPEG-1 si sunetul MP2 / MP3
	si AC-3 (decodorul FFmpeg in WebAssembly, fara E-AC-3, AAC si HE-AAC). Cand PMT-ul are imagine MPEG-2 / MPEG-1, raman
	pistele MP2 / MP3, apoi AC-3 (fara `ac3`: o decodeaza pagina); la H.264 / HEVC alegerea e cea de mai sus. `video` =
	formatul imaginii din PMT ("mpeg2", "mpeg1", "h264", "h265" sau ""), pentru pagina (trece singura pe playerul wasm
	cand formatul nu se stia la pornire).
	CRIPTAT: `criptat` = True cand din ultimele pachete ale imaginii (cel mult CRIPTAT_ESANTION pe bucata)
	cele mai multe au bitii transport_scrambling_control pusi: canalul iese din inregistrare tot criptat (camul nu-l
	decripteaza pentru transmisie), iar browserul n-ar putea arata nimic. None = nu se stie inca.
	Si cu bitii 0, imaginea e clara numai daca inceputurile ei PES (pachetele cu payload_unit_start, toate din bucata) au
	00 00 01: din ultimele PES_FEREASTRA (fereastra plina) cele mai multe stricate = True; PES_CLAR_MINIM la rand bune si
	niciunul stricat = False mai devreme; altfel None (nu se stie inca). Proba de noapte 13-14.10: FRANCE 2, DAZN 2,
	13th Street ieseau din inregistrare cu bitii 0 si imaginea stricata. Pachetele cu transport_error_indicator nu se
	socotesc (un semnal slab nu face criptat un canal FTA). O hotarare ramane pana la urmatoarea.
	Pana la primul PAT, sau daca serviciul nu e in PAT, datele trec neschimbate. Datele primite sunt pachete TS intregi,
	aliniate.
	PMT-UL LIPSA (proba din 14.10, EBS+HD pe 9,0E: PAT-ul spune PMT pe 0x1B1, dar niciun pachet 0x1B1 in inregistrare;
	pagina n-a stiut niciodata ce sa redea): cat avem PAT-ul nostru si niciun PMT al serviciului, inceputurile PES clare
	(fara biti de criptare, cu 00 00 01) spun ce flux e pe fiecare PID (_felFlux: imaginea MPEG-2, H.264, HEVC dupa codurile
	de start; sunetul MPEG, AAC ADTS, LATM, AC-3, E-AC-3 dupa sincronul cadrelor, de doua ori la rand). Dupa PMT_LIPSA_S
	secunde de flux (dupa PTS) fara PMT, PMT-ul se face din ele (`pmt_facut`) si trece prin aceeasi alegere ca unul
	adevarat; pleaca pe loc, apoi dupa fiecare PAT al nostru. Un PMT adevarat venit mai tarziu il inlocuieste. Un flux
	criptat nu da nimic (pagina spune atunci ca n-a primit descrierea canalului)."""

	VIDEO = (0x01, 0x02, 0x1B, 0x24)
	VIDEO_FEL = {0x01: "mpeg1", 0x02: "mpeg2", 0x1B: "h264", 0x24: "h265"}
	MP2 = (0x03, 0x04)
	ADTS = 0x0F
	AC3 = 0x81

	LATM = 0x11
	EAC3 = 0x87
	CRIPTAT_FEREASTRA = 300       # cate pachete ale imaginii se socotesc (cele mai noi)
	CRIPTAT_MINIM = 100           # sub atatea pachete numarate nu se spune nimic
	CRIPTAT_ESANTION = 64         # cel mult atatea pachete ale imaginii se cerceteaza intr-o bucata (bitii de criptare)
	# inceputurile PES ale imaginii (un PES pe imagine: 25-50 pe secunda): fereastra plina = 1-2 s; dupa un canal criptat
	# primele 8-20 de PES-uri pot veni inca stricate (proba de noapte 13-14.10, sectiunea 4), deci nu fac majoritatea
	PES_FEREASTRA = 50
	# "clar" mai devreme: atatea inceputuri cu 00 00 01 si niciunul stricat (intr-un flux stricat 00 00 01 vine din
	# intamplare o data la 2^24 de inceputuri)
	PES_CLAR_MINIM = 8
	# PMT-UL LIPSA (sus): cat flux (dupa PTS) se asteapta PMT-ul adevarat; un PID cu PES de imagine (0xE0-0xEF) inca
	# nerecunoscut se mai asteapta pana la PMT_LIPSA_IMAGINE_S; dupa PMT_CAUTARI_MAX pachete cercetate fara PMT (un flux
	# criptat nu da niciun PES clar, deci nici PTS: ~1 minut de flux la 5 Mbit/s) cautarea se lasa, ca firul sesiunii sa nu
	# treaca prin fiecare pachet cat traieste sesiunea
	PMT_LIPSA_S = 3
	PMT_LIPSA_IMAGINE_S = 6
	PMT_CAUTARI_MAX = 200000

	def __init__(self, sid, ac3=False, pista=None, intreg=False, wasm=False):
		self.sid = sid
		self.ac3 = bool(ac3)
		self.pista = pista
		self.intreg = bool(intreg)
		self.wasm = bool(wasm)
		self.piste = []
		self.pmt_citit = False
		self.video = ""
		self.pid_video = None
		self.criptat = None
		self.video_pachete = 0           # cate pachete ale imaginii s-au cercetat (0 = nicio imagine inca)
		self._ultimele = collections.deque(maxlen=self.CRIPTAT_FEREASTRA)
		self._pes = collections.deque(maxlen=self.PES_FEREASTRA)   # 1 = inceput PES stricat, 0 = cu 00 00 01
		self.pmt_pid = None
		self.pat_original = {}           # section_number -> ultima sectiune PAT citita
		self.pat_sectiune = None         # section_number al sectiunii PAT cu serviciul nostru
		self.pat_nou = None              # PAT-ul nostru (un pachet), fara contorul de continuitate
		self.pmt_original = None
		self.pmt_nou = None              # PMT-ul nostru: pachetele lui, fara contorul de continuitate
		self.sectiuni = {0: SectiuniPsi()}
		self.cc = {0: 0}
		self.pmt_facut = False           # PMT-UL LIPSA: PMT-ul de acum e facut din fluxuri, nu citit
		self._fluxuri = {}               # PMT-UL LIPSA: PID -> {"sid", "tip", "voturi"}
		self._pts = None                 # PMT-UL LIPSA: (primul PTS, ultimul PTS) de la PAT-ul nostru incoace
		self._pcr = None                 # PMT-UL LIPSA: primul PID vazut cu PCR
		self._cautari = 0

	def filtreaza(self, date):
		if self.sid is None:
			return date
		pid_jos = date[2::TS]
		if self.pid_video is not None:
			self._numaraCriptate(date, pid_jos)
		# PMT-UL LIPSA: PMT-ul facut acum pleaca inaintea bucatii (contoarele lui inaintea PAT-urilor din ea)
		inainte = b""
		if self.pat_nou is not None and self.pmt_original is None and self._cautari < self.PMT_CAUTARI_MAX:
			self._cautaFluxuri(date)
			if self.pmt_facut and self.pmt_nou is not None:
				inainte = self._cuCc(self.pat_nou, 0) + b"".join(self._cuCc(p, self.pmt_pid) for p in self.pmt_nou)
		pozitii = self._pozitii(date, pid_jos)
		if not pozitii:
			return inainte + date
		# intai PAT-urile bucatii: PID-ul PMT aflat din ele prinde si pachetele PMT dinaintea lor (la inceputul unei
		# legari PMT-ul poate veni inaintea primului PAT); adunarea e pe PID, deci ordinea dintre PID-uri nu conteaza
		inlocuiri = {}
		pmt_inainte = self.pmt_pid
		for i, pid in pozitii:
			if pid == 0:
				inlocuiri[i] = self._pachet(date[i * TS:i * TS + TS], 0)
		if self.pmt_pid != pmt_inainte:
			pozitii = self._pozitii(date, pid_jos)
		for i, pid in pozitii:
			if pid != 0:
				inlocuiri[i] = self._pachet(date[i * TS:i * TS + TS], pid)
		bucati, ultim = [], 0
		for i in sorted(inlocuiri):
			a = i * TS
			bucati.append(date[ultim:a])
			bucati.append(inlocuiri[i])
			ultim = a + TS
		bucati.append(date[ultim:])
		return inainte + b"".join(bucati)

	# ------------------------------------------------------------ PMT-UL LIPSA (sus)
	@staticmethod
	def _felFlux(sid, date, a, p):
		"""Felul fluxului dupa inceputul PES de la `p` (pachetul de la `a`): tipul de flux din PMT (0x02, 0x1B, 0x24,
		0x03/0x04, 0x0F, 0x11, 0x81, 0x87), "" pentru un flux care nu intra in PMT (teletext, subtitrari) sau None (nu se
		stie inca din acest pachet). Imaginea: primul cod de start hotarator (00 00 01 nu apare in interiorul datelor nici
		la MPEG-2, nici la H.264 / HEVC); sunetul: primul antet de cadru valid din sarcina."""
		capat = a + TS
		if p + 9 > capat:
			return None
		inceput = p + 9 + date[p + 8]
		if inceput >= capat:
			return None
		if 0xE0 <= sid <= 0xEF:
			i = date.find(b"\x00\x00\x01", inceput, capat - 4)
			while i >= 0:
				c, c2 = date[i + 3], date[i + 4]
				if c in (0xB3, 0xB5, 0xB8):
					return 0x02
				if c in (0x09, 0x27, 0x47, 0x67, 0x28, 0x48, 0x68):
					return 0x1B
				if c in (0x40, 0x42, 0x44, 0x46) and c2 == 0x01:
					return 0x24
				i = date.find(b"\x00\x00\x01", i + 3, capat - 4)
			return None
		if 0xC0 <= sid <= 0xDF:
			i = date.find(b"\xff", inceput, capat - 3)
			while i >= 0:
				b1, b2 = date[i + 1], date[i + 2]
				if b1 & 0xF6 == 0xF0 and (b2 >> 2) & 0x0F < 13:
					return 0x0F                                  # AAC ADTS
				if (b1 & 0xE0 == 0xE0 and (b1 >> 3) & 3 != 1 and (b1 >> 1) & 3 and (b2 >> 4) not in (0, 15)
						and (b2 >> 2) & 3 != 3):
					return 0x03 if (b1 >> 3) & 3 == 3 else 0x04  # MPEG audio (MPEG-1 / MPEG-2)
				i = date.find(b"\xff", i + 1, capat - 3)
			i = date.find(b"\x56", inceput, capat - 2)
			while i >= 0:
				if date[i + 1] & 0xE0 == 0xE0:
					return 0x11                                  # LATM
				i = date.find(b"\x56", i + 1, capat - 2)
			return None
		if sid == 0xBD:
			if 0x10 <= date[inceput] <= 0x1F or date[inceput:inceput + 2] == b"\x20\x00":
				return ""                                        # teletext, subtitrari DVB
			i = date.find(b"\x0b\x77", inceput, capat - 6)
			while i >= 0:
				bsid = date[i + 5] >> 3
				if bsid <= 8:
					return 0x81
				if 11 <= bsid <= 16:
					return 0x87
				i = date.find(b"\x0b\x77", i + 1, capat - 6)
			return None
		return ""

	def _cautaFluxuri(self, date):
		"""PMT-UL LIPSA: inceputurile PES clare ale bucatii (si PCR-ul), apoi, la timp, PMT-ul facut din ele."""
		octet1 = date[1::TS]
		self._cautari += len(octet1)            # PMT_CAUTARI_MAX: toate pachetele cercetate, si cele criptate
		for k in range(len(octet1)):
			b1 = octet1[k]
			if b1 & 0x80:
				continue
			a = k * TS
			b3 = date[a + 3]
			if b3 & 0x20 and date[a + 4] and date[a + 5] & 0x10 and self._pcr is None:
				self._pcr = ((b1 & 0x1F) << 8) | date[a + 2]
			if not b1 & 0x40 or b3 & 0xC0 or not b3 & 0x10:
				continue
			pid = ((b1 & 0x1F) << 8) | date[a + 2]
			if pid == 0 or pid == self.pmt_pid or pid == 0x1FFF:
				continue
			p = a + 4 + (1 + date[a + 4] if b3 & 0x20 else 0)
			if p + 14 > a + TS or date[p:p + 3] != b"\x00\x00\x01":
				continue
			sid = date[p + 3]
			if date[p + 7] & 0x80:
				self._notaPts((((date[p + 9] >> 1) & 7) << 30) | (date[p + 10] << 22) | ((date[p + 11] >> 1) << 15) | (
					date[p + 12] << 7) | (date[p + 13] >> 1))
			f = self._fluxuri.get(pid)
			if f is None:
				f = self._fluxuri[pid] = {"sid": sid, "tip": None, "voturi": {}}
			if f["tip"] is not None:
				continue
			tip = self._felFlux(sid, date, a, p)
			if tip is None:
				continue
			f["voturi"][tip] = f["voturi"].get(tip, 0) + 1
			# imaginea: un cod de start ajunge; sunetul: acelasi fel la doua PES-uri
			if tip == "" or tip in self.VIDEO or f["voturi"][tip] >= 2:
				f["tip"] = tip
		self._poateFacePmt()

	def _notaPts(self, pts):
		"""Cat flux a trecut, dupa PTS: (reperul, cel mai departe); un PTS dinaintea reperului (cadre B, sunetul in urma
		imaginii) nu muta nimic, un salt de peste o ora face alt reper."""
		if self._pts is None:
			self._pts = (pts, pts)
			return
		reper, departe = self._pts
		d = (pts - reper) % (1 << 33)
		if d >= (1 << 32):
			return
		if d > 3600 * 90000:
			self._pts = (pts, pts)
		elif d > (departe - reper) % (1 << 33):
			self._pts = (reper, pts)

	def _poateFacePmt(self):
		if self._pts is None:
			return
		trecut = ((self._pts[1] - self._pts[0]) % (1 << 33)) / 90000.0
		if trecut < self.PMT_LIPSA_S:
			return
		imagine = [p for p, f in self._fluxuri.items() if 0xE0 <= f["sid"] <= 0xEF]
		if any(self._fluxuri[p]["tip"] is None for p in imagine) and trecut < self.PMT_LIPSA_IMAGINE_S:
			return
		alese = sorted((p, f["tip"]) for p, f in self._fluxuri.items() if f["tip"])
		video = [(p, t) for p, t in alese if t in self.VIDEO][:1]
		sunet = [(p, t) for p, t in alese if t not in self.VIDEO]
		if not video and not sunet:
			return
		pcr = self._pcr if self._pcr is not None else (video or sunet)[0][0]
		intrari = b"".join(bytes([t, 0xE0 | (p >> 8), p & 0xFF, 0xF0, 0x00]) for p, t in video + sunet)
		lungime = 9 + len(intrari) + 4
		corp = bytes([0x02, 0xB0 | (lungime >> 8), lungime & 0xFF, (self.sid >> 8) & 0xFF, self.sid & 0xFF, 0xC1, 0x00, 0x00,
			0xE0 | (pcr >> 8), pcr & 0xFF, 0xF0, 0x00]) + intrari
		crc = crc32Mpeg(corp)
		s = corp + bytes([(crc >> 24) & 0xFF, (crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF])
		self._citestePmt(s)
		if self.intreg:
			self.pmt_nou = self._pacheteDin(self.pmt_pid, corp)
		self.pmt_facut = True
		_jurnal("serviciul %d: PMT-ul lipseste din flux dupa %.1f s, facut din fluxuri: %s" % (self.sid, trecut,
			", ".join("0x%X/0x%02X" % (p, t) for p, t in video + sunet)))

	def _numaraCriptate(self, date, pid_jos):
		jos = self.pid_video & 0xFF
		sus = (self.pid_video >> 8) & 0x1F
		n = 0
		i = pid_jos.find(jos)
		while i >= 0 and n < self.CRIPTAT_ESANTION:
			a = i * TS
			b1 = date[a + 1]
			if (b1 & 0x1F) == sus and not b1 & 0x80:
				self._ultimele.append(1 if (date[a + 3] & 0xC0) else 0)
				n += 1
			i = pid_jos.find(jos, i + 1)
		self.video_pachete += n
		# inceputurile PES ale imaginii din toata bucata: al doilea octet = payload_unit_start, fara eroare, PID-ul de sus
		# (transport_priority 0 sau 1); sunt putine (cate unul pe imagine), deci cautarea e ieftina
		octet1 = date[1::TS]
		for cap in (0x40 | sus, 0x60 | sus):
			i = octet1.find(cap)
			while i >= 0:
				if pid_jos[i] == jos:
					self._inceputPes(date, i * TS)
				i = octet1.find(cap, i + 1)
		self._hotaraste()

	def _inceputPes(self, date, a):
		"""Pachetul de la `a` incepe un PES al imaginii: 1 (stricat: bitii de criptare pusi sau fara 00 00 01) sau 0."""
		b3 = date[a + 3]
		if not b3 & 0x10:
			return                                   # numai camp de adaptare, fara sarcina utila
		inceput = 4 + (1 + date[a + 4] if b3 & 0x20 else 0)
		if inceput + 3 > TS:
			return
		self._pes.append(1 if (b3 & 0xC0) or date[a + inceput:a + inceput + 3] != b"\x00\x00\x01" else 0)

	def _hotaraste(self):
		"""CRIPTAT (sus): bitii pusi = True; bitii 0 = False numai cand si inceputurile PES spun clar."""
		if len(self._ultimele) < self.CRIPTAT_MINIM:
			return
		if sum(self._ultimele) * 2 > len(self._ultimele):
			self.criptat = True
			return
		rele, n = sum(self._pes), len(self._pes)
		if n >= self.PES_FEREASTRA:
			self.criptat = rele * 2 > n
		elif n >= self.PES_CLAR_MINIM and not rele:
			self.criptat = False
		elif not n and len(self._ultimele) >= self.CRIPTAT_FEREASTRA:
			# niciun inceput de PES intr-o fereastra plina a bitilor (un flux fara payload_unit_start pe imagine): ramane
			# judecata bitilor, ca inainte
			self.criptat = False

	def _pozitii(self, date, pid_jos):
		"""(index, PID) pentru pachetele PAT si PMT; intai octetul de jos al PID-ului, pe felii (rapid)."""
		pmt = self.pmt_pid
		jos_pmt = pmt & 0xFF if pmt is not None else -1
		rez = []
		for i, v in enumerate(pid_jos):
			if v == 0 or v == jos_pmt:
				pid = ((date[i * TS + 1] & 0x1F) << 8) | v
				if pid == 0 or pid == pmt:
					rez.append((i, pid))
		return rez

	def _pachet(self, pachet, pid):
		"""-> ce pleaca in locul pachetului: PAT-ul / PMT-ul nostru cand pachetul termina o sectiune buna, nimic cand
		avem deja al nostru (bucatile sectiunilor originale nu mai pleaca), pachetul insusi cand nu avem nimic al nostru."""
		adunare = self.sectiuni.get(pid)
		if adunare is None:
			adunare = self.sectiuni[pid] = SectiuniPsi()
		iesire = []
		for s, bun in adunare.pune(pachet):
			if not bun or len(s) < 8:
				continue
			if pid == 0:
				if s[0] == 0x00:
					self._citestePat(s)
					if self.pat_nou is not None:
						iesire.append(self._cuCc(self.pat_nou, 0))
						if self.pmt_facut and self.pmt_nou is not None:
							# PMT-UL LIPSA: PMT-ul facut pleaca dupa fiecare PAT al nostru (altul nu vine)
							iesire.extend(self._cuCc(p, self.pmt_pid) for p in self.pmt_nou)
			elif s[0] == 0x02 and ((s[3] << 8) | s[4]) == self.sid:
				self._citestePmt(s)
				if self.pmt_nou is not None:
					iesire.extend(self._cuCc(p, pid) for p in self.pmt_nou)
		if (self.pat_nou if pid == 0 else self.pmt_nou) is None:
			# trece cum vine; pachetele noastre de dupa el ii continua contorul (fara ruptura la iesire)
			self.cc[pid] = ((pachet[3] & 0x0F) + 1) & 0x0F
			return pachet
		return b"".join(iesire)

	def _cuCc(self, pachet, pid):
		cc = self.cc.get(pid, 0)
		self.cc[pid] = (cc + 1) & 0x0F
		return pachet[:3] + bytes([(pachet[3] & 0xF0) | cc]) + pachet[4:]

	@staticmethod
	def _sectiune(pachet, partial=False):
		"""Sectiunea PSI care incepe in pachet (dupa campul pointer), sau None daca nu incape intreaga in el (probele o
		folosesc ca sa citeasca PAT-ul si PMT-ul rescrise). Cu partial=True: (inceputul ei din acest pachet, True daca e
		intreaga)."""
		inceput = 4
		if (pachet[3] >> 4) & 0x02:              # camp de adaptare
			inceput += 1 + pachet[4]
		if inceput >= TS:
			return (None, False) if partial else None
		inceput += 1 + pachet[inceput]           # campul pointer
		if inceput + 3 > TS:
			return (None, False) if partial else None
		lungime = ((pachet[inceput + 1] & 0x0F) << 8) | pachet[inceput + 2]
		sectiune = pachet[inceput:inceput + 3 + lungime]
		intreaga = len(sectiune) == 3 + lungime
		if partial:
			return sectiune, intreaga
		return sectiune if intreaga else None

	@staticmethod
	def _pacheteDin(pid, corp):
		"""Sectiunea `corp` (fara CRC) cu CRC-ul ei, pe cate pachete TS trebuie: primul cu inceput de sectiune si campul
		pointer 0, restul continuari; contorul de continuitate il pune _cuCc la trimitere."""
		crc = crc32Mpeg(corp)
		date = bytes(corp) + bytes([(crc >> 24) & 0xFF, (crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF])
		pachete = []
		while date or not pachete:
			antet = bytes([0x47, (0x00 if pachete else 0x40) | ((pid >> 8) & 0x1F), pid & 0xFF, 0x10])
			if not pachete:
				antet += b"\x00"
			loc = TS - len(antet)
			bucata, date = date[:loc], date[loc:]
			pachete.append(antet + bucata + b"\xff" * (loc - len(bucata)))
		return pachete

	@staticmethod
	def _pachetDin(pid, corp):
		return b"".join(RescrierePsi._pacheteDin(pid, corp))

	def _citestePat(self, s):
		# un PAT pe mai multe sectiuni (foarte multe programe): PID-ul PMT vine din sectiunea care are serviciul; o alta
		# sectiune fara el nu sterge PAT-ul nostru
		numar = s[6]
		if len(s) < 12 or s == self.pat_original.get(numar):
			return
		self.pat_original[numar] = s
		pmt = None
		for j in range(8, len(s) - 4, 4):
			if ((s[j] << 8) | s[j + 1]) == self.sid:
				pmt = ((s[j + 2] & 0x1F) << 8) | s[j + 3]
				break
		if pmt is None:
			if self.pat_sectiune is None or self.pat_sectiune == numar:
				self.pat_nou, self.pat_sectiune = None, None
			return
		self.pat_sectiune = numar
		if pmt != self.pmt_pid:
			if self.pmt_pid is not None:
				self.sectiuni.pop(self.pmt_pid, None)
			self.pmt_pid, self.pmt_original, self.pmt_nou = pmt, None, None
			# PMT-UL LIPSA: alt PID al PMT-ului = alta cautare
			self.pmt_facut, self._fluxuri, self._pts, self._pcr, self._cautari = False, {}, None, None, 0
		corp = bytes([0x00, 0xB0, 0x0D]) + s[3:5] + bytes([0xC1 | (s[5] & 0x3E), 0x00, 0x00,
			(self.sid >> 8) & 0xFF, self.sid & 0xFF, 0xE0 | ((pmt >> 8) & 0x1F), pmt & 0xFF])
		self.pat_nou = self._pacheteDin(0, corp)[0]

	def _videoDin(self, s, sfarsit):
		"""Formatul primului flux video din sectiunea PMT `s` (intrarile pana la `sfarsit`), sau ''."""
		if len(s) < 12:
			return ""
		k = 12 + (((s[10] & 0x0F) << 8) | s[11])
		while k + 5 <= sfarsit:
			if s[k] in self.VIDEO:
				return self.VIDEO_FEL[s[k]]
			k += 5 + (((s[k + 3] & 0x0F) << 8) | s[k + 4])
		return ""

	def _citestePmt(self, s):
		if len(s) < 16 or s == self.pmt_original:
			return
		self.pmt_original = s
		self.pmt_facut = False           # un PMT adevarat il inlocuieste pe cel facut (_poateFacePmt il pune iar)
		info = ((s[10] & 0x0F) << 8) | s[11]
		j, sfarsit = 12 + info, len(s) - 4
		video, audio, piste = [], [], []
		# imaginea (primul flux video): la MPEG-2 / MPEG-1 cu playerul wasm, sunetul il decodeaza pagina
		self.video = self._videoDin(s, sfarsit)
		cu_wasm = self.wasm and self.video in ("mpeg2", "mpeg1")
		while j + 5 <= sfarsit:
			tip = s[j]
			pid = ((s[j + 1] & 0x1F) << 8) | s[j + 2]
			lung_d = ((s[j + 3] & 0x0F) << 8) | s[j + 4]
			intrare = s[j:j + 5 + lung_d]
			descriptori = s[j + 5:j + 5 + lung_d]
			fel = None
			if tip in self.VIDEO:
				video.append(intrare)
				if self.pid_video is None or len(video) == 1:
					self.pid_video = pid
			elif tip in self.MP2:
				fel = "MP2"
			elif tip == self.ADTS:
				fel = "AAC"
			elif tip == self.AC3 or (tip == 0x06 and _areDescriptor(descriptori, 0x6A)):
				fel, intrare = "AC3", bytes([self.AC3]) + intrare[1:]
			elif tip == self.LATM:
				fel = "HE-AAC"
			elif tip == self.EAC3 or (tip == 0x06 and _areDescriptor(descriptori, 0x7A)):
				fel = "E-AC3"
			if fel is not None:
				if cu_wasm:
					merge = fel in ("MP2", "AC3")
				else:
					merge = fel in ("MP2", "AAC") or (fel == "AC3" and self.ac3)
				limba, rol = _limbaSiRol(descriptori)
				piste.append({"pid": pid, "fel": fel, "limba": limba, "rol": rol, "merge": merge, "aleasa": False})
				if merge:
					audio.append((fel, pid, intrare))
			j += 5 + lung_d
		ales = None
		for fel, pid, intrare in audio:
			if self.pista is not None and pid == self.pista:
				ales = (pid, intrare)
		for dorit in (("MP2", "AC3") if cu_wasm else ("MP2", "AAC", "AC3")):
			for fel, pid, intrare in audio:
				if ales is None and fel == dorit:
					ales = (pid, intrare)
		for p in piste:
			p["aleasa"] = ales is not None and p["pid"] == ales[0] and not self.intreg
		self.piste = piste
		self.pmt_citit = True
		if self.intreg:
			return   # playerele externe primesc PMT-ul neschimbat (pmt_nou ramane None)
		intrari = b"".join(video[:1]) + (ales[1] if ales else b"")
		corp = bytearray(s[:12 + info]) + intrari
		lungime = len(corp) - 3 + 4
		corp[1] = (corp[1] & 0xF0) | ((lungime >> 8) & 0x0F)
		corp[2] = lungime & 0xFF
		self.pmt_nou = self._pacheteDin(self.pmt_pid, bytes(corp))


def _codLimba(octeti):
	try:
		text = bytes(octeti).decode("ascii").strip().lower()
	except UnicodeDecodeError:
		return ""
	return text if len(text) == 3 and text.isalpha() else ""


def _limba(descriptori):
	"""Limba pistei din descriptorul ISO 639 (0x0A): trei litere ('deu', 'ron'), sau ''."""
	k = 0
	while k + 2 <= len(descriptori):
		if descriptori[k] == 0x0A and descriptori[k + 1] >= 3 and k + 5 <= len(descriptori):
			return _codLimba(descriptori[k + 2:k + 5])
		k += 2 + descriptori[k + 1]
	return ""


def _limbaSiRol(descriptori):
	"""(limba, rol) ale unei piste audio, din descriptorii ei. Limba: din descriptorul ISO 639 (0x0A) sau, cand o are,
	din supplementary_audio_descriptor (0x7F cu extensia 0x06, EN 300 468), care o inlocuieste (Das Erste HD: "mis" si
	"qks" in ISO 639, "deu" in el). Rolul: "descriere" = descriere audio pentru nevazatori (editorial_classification 1,
	sau audio_type 3 in ISO 639), "clar" = vorbire clara pentru cei care aud greu (editorial_classification 2, sau
	audio_type 2), "" = pista obisnuita. supplementary_audio_descriptor, cand exista, hotaraste rolul."""
	limba, rol_iso, rol_sup = _limba(descriptori), "", None
	k = 0
	while k + 2 <= len(descriptori):
		eticheta, lung = descriptori[k], descriptori[k + 1]
		d = descriptori[k + 2:k + 2 + lung]
		if eticheta == 0x0A and len(d) >= 4 and not rol_iso:
			rol_iso = {0x02: "clar", 0x03: "descriere"}.get(d[3], "")
		elif eticheta == 0x7F and len(d) >= 2 and d[0] == 0x06:
			rol_sup = {1: "descriere", 2: "clar"}.get((d[1] >> 2) & 0x1F, "")
			if d[1] & 0x01 and len(d) >= 5:
				limba = _codLimba(d[2:5]) or limba
		k += 2 + lung
	return limba, rol_sup if rol_sup is not None else rol_iso


def _areDescriptor(descriptori, eticheta):
	k = 0
	while k + 2 <= len(descriptori):
		if descriptori[k] == eticheta:
			return True
		k += 2 + descriptori[k + 1]
	return False


def _tabelCrc():
	tabel = []
	for i in range(256):
		crc = i << 24
		for _j in range(8):
			crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
		tabel.append(crc)
	return tabel


_TABEL_CRC = _tabelCrc()


def crc32Mpeg(date):
	"""CRC-32/MPEG-2 al sectiunilor PSI (polinomul 0x04C11DB7, fara reflexie, initial 0xFFFFFFFF), pe tabel (un pas pe
	octet). Peste o sectiune intreaga, cu CRC-ul ei la coada, da 0 cand sectiunea e buna."""
	crc = 0xFFFFFFFF
	for b in bytearray(date):
		crc = ((crc << 8) & 0xFFFFFFFF) ^ _TABEL_CRC[(crc >> 24) ^ b]
	return crc


# ---------------------------------------------------------------- legaturile cu enigma2 (firul principal)

class InregistrareInTeava(object):
	"""Inregistrarea enigma2 scrisa intr-o teava (ca Hds/DabT2/server8001.py)."""

	def porneste(self, ses):
		"""-> None daca merge, altfel motivul (text pentru om)."""
		try:
			from enigma import eServiceCenter, eServiceReference
		except ImportError:
			return _("Transmisia merge numai pe receptor.")
		r, w = os.pipe()
		ses.r, ses.w = r, w
		try:
			import fcntl
			fcntl.fcntl(w, F_SETPIPE_SZ, TEAVA_OCTETI)
		except Exception:
			pass
		try:
			rec = eServiceCenter.getInstance().record(eServiceReference(ses.ref))
		except Exception as e:
			return _("Canalul nu se poate porni: %s") % e
		if rec is None:
			return _("Canalul nu se poate porni (nu e în lista receptorului).")
		ses.rec = rec
		cedeazaLaZap(rec)
		# -255: numai fisierul .meta nu se poate face langa /proc/self/fd/N; inregistrarea e pregatita
		rez = rec.prepare("/proc/self/fd/%d" % w, int(time.time()), -1, -1, "HDSatelit TV", "", "")
		if rez not in (0, -255):
			return _("Tunerul nu poate primi acest canal acum (%d).") % rez
		rez = rec.start()
		if rez:
			return _("Canalul nu pornește (%d).") % rez
		if self.eroare(ses):
			return _("Tunerul nu se poate folosi acum.")
		return None

	def opreste(self, ses):
		rec, ses.rec = ses.rec, None
		if rec is not None:
			try:
				rec.stop()
			except Exception as e:
				_jurnal("oprirea inregistrarii: %r" % (e,))
		w, ses.w = ses.w, None
		if w is not None:
			_inchideFd(w)

	@staticmethod
	def eroare(ses):
		rec = ses.rec
		if rec is None:
			return 0
		try:
			e = rec.getError()
		except Exception:
			return 0
		if isinstance(e, (tuple, list)):
			e = e[-1] if e else 0
		try:
			return int(e or 0)
		except (TypeError, ValueError):
			return 0


def folosiriCanalelor():
	"""Canalele tunerelor ocupate acum, cu folosirile lor (eDVBResourceManager.getChannelUseCounts, lib/dvb/hdscedare.h):
	[{"tsid", "onid", "ns" (hex), "folosiri", "cedabile" (ale inregistrarilor care cedeaza la zap), "cache"}].
	Un PMT handler tine 2 folosiri (al lui si scanarea SDT), cache-ul managerului inca 1. None fara nucleul care le da
	(alt enigma2, probele de pe PC)."""
	try:
		from enigma import eDVBResourceManager
		citire = getattr(eDVBResourceManager.getInstance(), "getChannelUseCounts", None)
		if citire is None:
			return None
		return [{"tsid": "%X" % c[0], "onid": "%X" % c[1], "ns": "%X" % c[2], "folosiri": int(c[3]),
			"cedabile": int(c[4]), "cache": bool(c[5])} for c in citire()]
	except Exception:
		return None


def cedeazaLaZap(rec):
	"""Marcheaza inregistrarea `rec` ca una care cedeaza la zap (iRecordableService.setYieldsToZap, lib/dvb/hdscedare.h),
	inainte de prepare: lista de canale socoteste atunci tunerul ei liber pentru televizor. Numai pentru cine chiar se
	opreste inainte de un zap care are nevoie de tuner (aici: cedeaza / _laZap; server8001: extensia de zap a releelor).
	Cu un enigma2 fara functie nu face nimic (lista ramane ca pana acum). -> True daca s-a pus."""
	pune = getattr(rec, "setYieldsToZap", None)
	if pune is None:
		return False
	try:
		return pune(True) == 0
	except Exception as e:
		_jurnal("cedarea la zap: %r" % (e,))
		return False


def doarFrecventaTv():
	"""True cand receptorul are o antena cu motor pe un tuner de satelit sau un singur tuner de satelit: atunci transmisia
	ia numai canale de pe transponderul televizorului. Daca nu se poate afla, True (paza cea mai sigura)."""
	try:
		from Components import HdsMotorTuner, HdsLnb
		if HdsMotorTuner.tunereCuMotor():
			return True
		return len(HdsLnb.tunereSatelit()) <= 1
	except Exception as e:
		_jurnal("motorul si tunerele nu se pot citi (%r): numai frecventa televizorului" % (e,))
		return True


def tunerLiber(ref, ignora=None):
	"""enigma2 poate porni `ref` acum fara sa opreasca nimic (managerul de tunere, canAllocateChannel); canalul
	`ignora` (sesiunea pe care o inlocuieste) se socoteste liber."""
	try:
		from enigma import eServiceCenter, eServiceReference
		sref = eServiceReference(ref)
		info = eServiceCenter.getInstance().info(sref)
		return bool(info and info.isPlayable(sref, eServiceReference(ignora) if ignora else eServiceReference()))
	except Exception as e:
		_jurnal("verificarea tunerului: %r" % (e,))
		return False


def refTv():
	"""Canalul de pe televizor (text) sau, in standby, canalul de dinainte; None daca nu se stie."""
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
		if ref is None:
			from Screens import Standby
			if Standby.inStandby is not None:
				ref = getattr(Standby.inStandby, "prev_running_service", None)
		text = _refText(ref)
		return text or None
	except Exception:
		return None


def serviciuTv():
	try:
		import NavigationInstance
		return NavigationInstance.instance.getCurrentService()
	except Exception:
		return None


def inStandby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


def memorieDriver():
	"""Memoria vmalloc a driverului, din Hds/DabT2/sesiuni8001.py (aceleasi praguri ca releele DAB+ / DVB-T2)."""
	from Hds.DabT2 import sesiuni8001 as S
	st = S.stare()
	v = st.get("vmalloc") or {}
	liber, gol = v.get("liber_kb"), v.get("gol_max_kb")
	ramase = None
	if liber is not None:
		ramase = max(0, (liber - S.PRAG_LIBER_KB) // ZONA_KB)
		# gol 0 = adresele ascunse (kptr_restrict, unele nuclee): nu se stie, nu "plin"
		if gol and gol < PRAG_GOL_KB + ZONA_KB:
			ramase = 0
	if st.get("scurse") is not None:
		pana_la_prag = max(0, S.PRAG_SESIUNI - int(st["scurse"]))
		ramase = pana_la_prag if ramase is None else min(ramase, pana_la_prag)
	return {"liber_kb": liber, "gol_max_kb": gol, "zone": v.get("zone"), "scurse": st.get("scurse"),
		"ramase": ramase, "trebuie_repornit": bool(st.get("trebuie_repornit")), "motiv": st.get("motiv", "")}


def contorSesiuni():
	try:
		from Hds.DabT2 import sesiuni8001 as S
		S.noteaza("tv-browser")
	except Exception as e:
		_jurnal("contorul sesiunilor: %r" % (e,))


_MANAGER = []


def manager():
	if not _MANAGER:
		_MANAGER.append(Manager())
	return _MANAGER[0]

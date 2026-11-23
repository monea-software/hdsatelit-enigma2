# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsBetaTester.py: programul de beta testeri al imaginii. Logica pentru ecranele de pe televizor
# (Screens/HdsBetaTester.py) si pentru pagina web /beta-tester (Plugins/Extensions/HdsWebControl/betatester_web.py).
#
# Ce face:
# - setarile config.hds_beta: pornit, bifele pe feluri de date (FELURI, toate bifate din fabrica), numele si e-mailul
#   optionale, identificatorul intamplator (32 de cifre hexa, os.urandom, nimic din receptor), versiunea notei de
#   confidentialitate acceptata (nota), data acordului, raspunsul la intrebare, adresa serverului (ascunsa);
# - contorul orei de functionare cumulate (fara standby): fisierul mic ORE, scris la 15 minute numai pana la intrebare,
#   apoi la 60 de minute numai cat programul e pornit; tot acolo numaratoarea ecranelor, a schimbarilor de canal si a
#   inregistrarilor (felul „utilizare”);
# - intrebarea, o singura data, dupa o ora cumulata, numai peste televizorul in direct (bara de sus, fara film, fara
#   inregistrare in curs, fara decalaj, fara standby); Nu = nu mai apare niciodata. In afara de ea, programul pune singur
#   pe ecran numai anuntul notei noi (cine a acceptat o nota mai veche nu mai trimite nimic pana la acordul nou): la
#   prima pornire dupa actualizare, in aceleasi conditii ca intrebarea, apoi cel mult o data pe zi, pana la acord
#   (anuntNotaDatorat, Screens/HdsBetaTester.HdsBetaNotaNoua; in web, sus pe orice pagina). Trimiterile, erorile si
#   coada plina raman in jurnal si in „Ce am trimis”;
# - culegerea pe feluri (jurnale, canale, sistem, utilizare, receptor), curatarea (curata()), pachetul JSON comprimat
#   gzip, coada pe disc (cel mult COADA_MAX pachete si COADA_OCTETI), trimiterea HTTPS pe un fir, ultimul pachet tinut
#   pentru „Ce trimit acum”, lista „Ce am trimis”, mesajele testerului, raspunsurile echipei, profilul public si
#   legarea unui cont prin coduri.
#
# Anonimizarea: fara adresa IP, MAC, serie, parole, chei, jetoane, liste de canale personale (favorite, fluxuri de pe
# internet), numele retelei Wi-Fi, numele fisierelor din filme si inregistrari; nimic despre accesul conditionat
# (randurile despre el se scot din jurnale, ecranele lui nu se numara, lista canalelor nu are PID-uri si nici CAID-uri).
# Modelul vine numai din paza modelului (Components/HdsPazaModel.py, verdictul „potrivit”), nu de la om.
#
# Firul: tic() ruleaza pe firul enigma2 la un minut (eTimer din porneste()); tot ce citeste fisiere mari sau vorbeste
# cu serverul ruleaza pe firul Lucru, care primeste un instantaneu al setarilor (fara config din fir).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il incarca fara receptor. DOSAR, caile din
# /proc si /sys si functia de trimitere se pot schimba pentru probe (HDS_BETA_DOSAR, argumentul `radacina`,
# Trimitere(posteaza=...)).

import base64
import gzip
import hashlib
import io
import json
import os
import re
import threading
import time

try:
	from Components.HdsListeText import text_lista
except ImportError:
	from HdsListeText import text_lista

# Nota 4: identificatorul anonim ramane local si dupa stergerea datelor personale.
# Nota 3: modulele de acces si pauza; pragul NOTA_MODULE ramane separat.
NOTA = 4
PROTOCOL = 1
SERVER = "https://stb.hdsatelit.com/api/testeri/"
ADRESA_NOTA = "https://stb.hdsatelit.com/testeri/confidentialitate/"
ADRESA_NOTA_EN = "https://stb.hdsatelit.com/en/testeri/confidentialitate/"
ADRESA_NOTA_SCURTA = "stb.hdsatelit.com/testeri/confidentialitate"

DOSAR = os.environ.get("HDS_BETA_DOSAR") or "/home/root/hds-beta"
CALE_LOGS = "/home/root/logs"
CALE_LAMEDB = "/etc/enigma2/lamedb"
CALE_PAZNIC = "/home/root/hds-watchdog.log"
# rezultatul ultimei rulari a probelor receptorului (le scrie modulul probelor, ecranul „Probele receptorului”)
CALE_PROBE = "/home/root/hds-beta-probe.json"
CALE_SERVER_PROBA = "/tmp/hds-beta-server"

FELURI = ("jurnale", "canale", "sistem", "utilizare", "receptor", "probe")
FELURI_MESAJ = ("greseala", "idee", "intrebare")
# mesajul scris PRIMUL de echipa (bin/mesaje.php scrie, TODO 15.11 10:33): vine ca raspuns, fara text al testerului
FEL_ECHIPA = "echipa"

ORA_S = 3600
TIC_S = 60
SCRIERE_PANA_LA_INTREBARE_S = 900
SCRIERE_DUPA_S = 3600
ESANTION_S = 600
FEREASTRA_PROCESOR_S = 3 * TIC_S      # cel mult atat intre cele doua citiri /proc/stat ale procesorului ocupat
PRIMA_CULEGERE_S = 300
JURNALE_LA_S = 6 * 3600
ZI_S = 24 * 3600
SAPTAMANA_S = 7 * ZI_S
REINCERCARE_S = 3600
REINCERCARE_INTREBARE_S = 60

COADA_MAX = 20
COADA_OCTETI = 1024 * 1024
PACHET_MAX = 512 * 1024
TRIMISE_MAX = 100
TIMP_CERERE_S = 20
JURNAL_MAX = 64 * 1024
JURNALE_PE_ZI = 3
# stivele interfetei pastrate de paznic la un blocaj moale, stivele blocajului dur (hds-blocaj-*, scrise inainte de
# repornirea dura) si caderile enigma2 au limita lor pe zi si pleaca INAINTEA jurnalelor obisnuite: la 0.6.24, trei
# jurnale hds-*.log mai noi le luau locul (pachetul 225, SF8008, doua blocaje moi fara nicio stiva)
CADERI_PE_ZI = 6
# jurnalele rare care spun ce au facut actualizarea, imaginea noua de pe internet si punerea la loc a copiei au si ele
# limita lor pe zi, in afara celor obisnuite: altfel cele scrise des (hds-interfata, hds-zap, hds-tuner, hds-hdmi) le luau
# locul si nu ajungeau niciodata la noi (greselile 1122 si 1123, Uclan Ustym 4K PRO, 09.11.2026)
JURNALE_RARE = ("hds-actualizari", "hds-actualizare", "hds-imagine-online", "hds-restaurare")
RARE_PE_ZI = 2
# urma comenzilor de motor (lib/dvb/hdsurmamotor.cpp) are si ea locul ei pe zi: fara ea nu se vede cine a mutat antena si cand
# a ajuns (Viper 4K V40, pachetul 1719: o cautare cu motorul cu "fara semnal" in rafala, iar hds-motor.log pierdea cele 3
# locuri in fata lui hds-interfata, hds-zap si hds-tuner). Separat de cele rare: pe un receptor cu motor se schimba des.
JURNALE_MOTOR = ("hds-motor.log",)
MOTOR_PE_ZI = 2
PAZNIC_RANDURI = 1000
ECRANE_MAX = 150
MESAJE_PE_ZI = 10
TEXT_MAX = 4000
ECRAN_MAX = 120
NUME_MAX = 60
EMAIL_MAX = 120
NUME_PUBLIC_MIN = 2
NUME_PUBLIC_MAX = 40
CAPTURA_MAX = 400 * 1024
PROBE_MAX = 128 * 1024
CAPTURA_LATIME = 960
CAPTURA_ASTEPTARE_S = 15
STARE_LEGARE_S = 5
LEGARE_MAX_S = 600

_ID = re.compile(r"\A[0-9a-f]{32}\Z")
_COD6 = re.compile(r"\A[0-9]{6}\Z")
_NUME_PUBLIC = re.compile(r"\A[^\W_][\w .-]*\Z", re.U)
_EMAIL = re.compile(r"\A[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s.]{2,24}\Z")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _t(text):
	"""Traducerea enigma2, sau textul insusi (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsBetaTester] %s" % text)


# ------------------------------------------------------------------ textele comune (televizor, web, nota)

ETICHETE = {
	"jurnale": (N_("Jurnalele de cădere și de erori"),
		N_("Ce s-a întâmplat când interfața s-a oprit sau un ecran a căzut, fără setările și fără rețeaua ta.")),
	"canale": (N_("Canalele scanate"),
		N_("Sateliții, frecvențele și numele canalelor găsite la scanare, pentru baza de date a tuturor receptoarelor "
			"și pentru SatBase. Fără favorite, fără cablu și terestru.")),
	"sistem": (N_("Memoria, procesorul, temperatura și pornirea"),
		N_("Cât de încărcat e receptorul în timpul zilei și cât durează pornirea.")),
	"utilizare": (N_("Ecranele și funcțiile folosite"),
		N_("Ce ecrane deschizi și de câte ori, ca să știm ce să îmbunătățim întâi.")),
	"receptor": (N_("Datele receptorului"),
		N_("Memoria, tunerele, plăcile de rețea (fără adresa MAC), ieșirea HDMI, driverele și modulele de acces "
			"instalate, ca să adaptăm imaginea și lista de receptoare.")),
	"probe": (N_("Rezultatele probelor"),
		N_("Ce au găsit probele pornite de tine din meniul testerului: ce merge și ce nu pe modelul tău.")),
}
AUTOMAT = (N_("Trimite automat în fiecare zi"),
	N_("O dată pe zi, noaptea, numai felurile bifate, și imediat după o oprire neașteptată a interfeței sau o "
		"actualizare care nu a reușit. Fără bifă pleacă numai ce trimiți tu cu „Trimite acum”."))
ANTET_ACORD = N_("Datele sunt anonime: receptorul primește un identificator întâmplător, fără adresa IP, fără parole și "
	"fără listele tale de canale. Le folosim numai ca să îmbunătățim imaginea pe modelul tău de receptor. Numele și "
	"e-mailul sunt opționale.")
BIFA_NOTA = N_("Am citit Nota de confidențialitate și sunt de acord să trimit datele bifate mai sus.")
INTREBARE = N_("Vrei să ajuți la îmbunătățirea imaginii pe care o folosești acum?")
INTREBARE_RAND = N_("Ai folosit cu interes imaginea E2 HD Satelit peste o oră. Ca beta tester ne trimiți date anonime, "
	"numai cele alese de tine.")
NOTA_SCURTA = N_("Datele le primește Eduard Monea, persoană fizică (mărcile Monea Software și HD Satelit), "
	"contact@hdsatelit.com. Pleacă numai felurile bifate de tine, cu un identificator întâmplător și o amprentă "
	"calculată din placă, ca receptorul să fie numărat o singură dată (din ea nu se pot afla adresa MAC sau "
	"seria), fără adresa IP, fără parole și fără listele tale de canale, numai ca să îmbunătățim imaginea pe "
	"modelul tău de receptor. Jurnalele se păstrează 6 luni, celelalte date 12 luni. Poți debifa oricând un fel de "
	"date sau poți ieși din program cu ștergerea datelor. La o pornire ratată, receptorul trimite singur un raport "
	"tehnic anonim, fără date personale. Dacă scrii pe forumul receptorului, mesajul tău apare public, cu numele "
	"ales de tine sau cu un nume automat. Nota întreagă e la adresa de mai jos. "
	"Identificatorul anonim rămâne pe receptor pe termen nedeterminat, inclusiv după ștergerea datelor personale.")
IDENTITATE_PASTRATA = N_("Identificatorul anonim, ales întâmplător, rămâne pe receptor pe termen nedeterminat, "
	"inclusiv după ștergerea datelor. Numele, e-mailul, numele public, legarea contului, cheia profilului și "
	"pachetele personale se șterg; identificatorul păstrat nu păstrează profilul sau înscrierea de pe server.")
# anuntul notei noi (receptor si web): titlul, mesajul, ce e nou fata de nota de dinainte (paragrafele notei
# situl-imaginii/date/nota-testeri.json, cuvant cu cuvant), starea din meniul testerului si butoanele
NOTA_ANUNT_TITLU = N_("Nota de confidențialitate s-a schimbat")
NOTA_ANUNT = N_("Nota de confidențialitate a beta testerilor s-a schimbat. Ca receptorul să trimită mai departe "
	"jurnalele, citește ce e nou și acceptă.")
# Noutatile includ si nota 3, pentru cine vine de la o nota mai veche.
NOTA_NOUTATI = (
	N_("Modulele de acces instalate: pentru fiecare, numele pachetului și versiunea lui, feedul din care se poate lua "
		"aceeași versiune, dacă e modulul ales și dacă rulează. Fără fișierele lor de configurare, chei, servere, "
		"cititoare sau canalele deschise cu ele."),
	IDENTITATE_PASTRATA,
)
NOTA_ACCEPT_RAND = N_("Cu Accept ești de acord cu nota nouă și receptorul trimite din nou datele bifate de tine până acum.")
NOTA_OPRITA = N_("Trimiterea e oprită până accepți nota nouă.")
NOTA_BUTOANE = {
	"citeste": (N_("Citește nota întreagă"), N_("Pe ecran, cu săgețile. EXIT te întoarce aici.")),
	"accept": (N_("Accept"), N_("Datele bifate de tine pleacă din nou, ca până acum.")),
	"mai_tarziu": (N_("Mai târziu"), N_("Îți amintim mâine.")),
}
NOTA_ACCEPTATA = N_("Mulțumim. Receptorul trimite din nou datele bifate.")
# dupa prima activare (televizor si web, acelasi text din acceptaAcord) si in intrebarea de la iesire: multi porneau si
# opreau des Beta tester, crezand ca e asistenta de la distanta
DUPA_ACTIVARE = N_("Lasă Beta tester pornit: lucrează singur, în fundal. Dacă ieși din program cu ștergerea datelor, "
	"datele personale se șterg și pierzi statutul de beta tester de pe site. Identificatorul anonim rămâne pe receptor.")
NU_E_ASISTENTA = N_("Asistența de la distanță e altceva: o pornești numai când ai nevoie, din Meniu > Setări > "
	"Asistență de la distanță.")
LA_IESIRE = N_("Pierzi statutul de beta tester de pe site. Identificatorul anonim rămâne pe receptor pe termen "
	"nedeterminat; numele, e-mailul, legarea contului, cheia profilului și pachetele personale se șterg.")
STERGERE_DISC = N_("Ștergerea nu s-a încheiat pe receptor din cauza unei erori de scriere. "
	"Cererea salvată se reia automat; până atunci nu se trimit date personale.")
CHEIE_DISC = N_("Cheia profilului nu poate fi citită sau salvată pe receptor. Profilul nu a fost schimbat.")
# randul scurt de sub fiecare rand al meniului testerului si al celui neinscris (pe receptor si in web): exact ce
# face randul
RANDURI_MENIU = {
	"forum": N_("Ce scriu testerii acestui receptor; scrii și tu, cu capturi."),
	"mesaj": N_("O greșeală, o idee sau o întrebare, direct echipei."),
	"raport_canal": N_("Canalul de acum nu merge: datele lui tehnice pleacă pe loc."),
	"trimite_acum": N_("Datele bifate pleacă imediat."),
	"trimise": N_("Ultimele pachete plecate și starea fiecăruia."),
	"raspunsuri": N_("Ce ți-a răspuns echipa la mesaje."),
	"date": N_("Alegi ce date pleacă, numele și e-mailul."),
	"acum": N_("Tot ce a plecat în ultimul pachet."),
	"probe": N_("Probe pe receptor: ce merge și ce nu."),
	"canal_testeri": N_("Versiunile noi ajung întâi la tine."),
	"public": N_("Numele cu care apari pe forum și pe site."),
	"nota": N_("Ce date pleacă, cine le primește, cât se păstrează."),
	"pauza": N_("Nu mai trimite nimic; pornești din nou cu aceeași înscriere."),
	"iesire": N_("Serverul șterge datele acestei înscrieri. Înscrierile din alte sloturi rămân."),
	"nota_noua": NOTA_OPRITA,
}
RANDURI_VIZITATOR = {
	"acord": N_("Alegi ce date trimiți; sunt anonime."),
	"reia": N_("Aceeași înscriere: numele public și punctele XP rămân."),
	"forum": N_("Citește ce scriu testerii acestui receptor."),
}
# avantajele aratate celui care nu e inscris (pe receptor si in web): (cheie, pictograma, titlu, rand); apar primele
# AVANTAJE_ARATATE adevarate pe receptorul lui (cheile canal_testeri, forum numai daca exista modulul)
AVANTAJE = (
	("canal_testeri", "actualizare", N_("Primești versiunile noi înaintea tuturor"),
		N_("Din meniul testerului alegi să primești întâi versiunile pentru testeri.")),
	("forum", "traducere", N_("Scrii pe forumul receptorului, cu capturi de ecran"),
		N_("Forumul traduce singur mesajele pentru fiecare cititor.")),
	("date", "noutati", N_("Imaginea merge mai bine pe modelul tău"),
		N_("Trimiți date anonime, numai cele bifate de tine.")),
	("raspunsuri", "informatii", N_("Echipa îți răspunde la mesaje"),
		N_("Greșeli, idei, întrebări: răspunsul vine în meniul testerului.")),
)
AVANTAJE_ARATATE = 3


def avantaje(exista):
	"""Avantajele adevarate pe acest receptor, traduse: [(cheie, pictograma, titlu, rand)], cel mult AVANTAJE_ARATATE.
	exista = {cheie: bool} pentru avantajele legate de un modul (canal_testeri, forum)."""
	rez = [(cheie, glif, _t(titlu), _t(rand)) for cheie, glif, titlu, rand in AVANTAJE if exista.get(cheie, True)]
	return rez[:AVANTAJE_ARATATE]


FELURI_MESAJ_TEXT = {
	"greseala": N_("Greșeală"),
	"idee": N_("Idee"),
	"intrebare": N_("Întrebare"),
}
STARI_TRIMISE = {
	"coada": N_("în coadă"),
	"trimis": N_("trimis"),
	"pierdut": N_("pierdut, coada era plină"),
	"refuzat": N_("refuzat de server"),
}
STARI_MESAJ = {
	"nou": N_("nou"),
	"citit": N_("citit"),
	"raspuns": N_("are răspuns"),
	"inchis": N_("închis"),
}
NUME_FEL_PACHET = {
	"acord": N_("Acordul"),
	"sterge": N_("Ștergerea datelor"),
	"iesire": N_("Pauza"),
	"mesaj": N_("Mesaj"),
}


def eticheta(fel):
	return _t(ETICHETE[fel][0])


def randScurt(fel):
	return _t(ETICHETE[fel][1])


def textIntrebare():
	return _t(INTREBARE) + "\n\n" + _t(INTREBARE_RAND)


def numeFelPachet(fel):
	if fel in ETICHETE:
		return eticheta(fel)
	return _t(NUME_FEL_PACHET.get(fel, fel))


# ------------------------------------------------------------------ fisierele

def cale(nume, dosar=None):
	return os.path.join(dosar or DOSAR, nume)


def _asiguraDosar(dosar):
	try:
		os.makedirs(dosar, exist_ok=True)
		os.chmod(dosar, 0o700)
	except OSError:
		pass


def scrieAtomic(cale_fisier, octeti, mod=None):
	"""Fisier temporar langa cel bun, fsync, os.replace (o cadere nu lasa un fisier pe jumatate)."""
	_asiguraDosar(os.path.dirname(cale_fisier))
	nou = cale_fisier + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		if mod is not None:
			os.chmod(nou, mod)
		os.replace(nou, cale_fisier)
	except BaseException:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def citesteJson(cale_fisier, implicit=None):
	try:
		with open(cale_fisier, "r", encoding="utf-8") as f:
			return json.load(f)
	except (OSError, IOError, ValueError):
		return implicit


def scrieJson(cale_fisier, obiect):
	scrieAtomic(cale_fisier, json.dumps(obiect, ensure_ascii=False, sort_keys=True,
		separators=(",", ":")).encode("utf-8"))


def _syncDosar(dosar):
	"""Persist directory entries before advancing a deletion barrier."""
	if os.name == "posix":
		fd = os.open(dosar, os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)


def _sterge(cale_fisier):
	try:
		os.remove(cale_fisier)
	except OSError:
		pass


def _citesteText(cale_fisier, maxim=65536):
	try:
		with open(cale_fisier, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (OSError, IOError):
		return None


def _cale(radacina, cale_fisier):
	if not radacina:
		return cale_fisier
	return os.path.join(radacina, cale_fisier.lstrip("/"))


def oraUtc(secunde=None):
	"""„AAAA-LL-ZZTHH:MMZ”, la minut, in UTC (fara fusul orar al omului)."""
	return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() if secunde is None else secunde))


def ziUtc(secunde=None):
	return time.strftime("%Y-%m-%d", time.gmtime(time.time() if secunde is None else secunde))


# ------------------------------------------------------------------ amprenta receptorului
# Identificatorul (id) e nou la fiecare acord, deci acelasi receptor instalat in mai multe sloturi, reinstalat sau intrat
# din nou in program ar parea mai multi testeri. Amprenta il leaga de aparat fara sa-l arate: PBKDF2-HMAC-SHA256 din
# adresa MAC a lui eth0 (litere mici, aa:bb:...) si CID-ul memoriei eMMC, despartite de |, cu o sare fixa; 16 octeti in
# hexa (32 de semne). MAC-ul si CID-ul nu pleaca niciodata de pe receptor; din amprenta nu se pot afla. Se face o data pe
# proces (pe fir, fara retea) si se tine in memorie. Fara MAC si fara CID: amprenta e goala.
CALE_MAC = "/sys/class/net/eth0/address"
CALE_CID = "/sys/block/mmcblk0/device/cid"
SARE_AMPRENTA = b"hds-receptor-amprenta-v1"
ITERATII_AMPRENTA = 100000
_amprenta = None
_LACAT_AMPRENTA = threading.Lock()


def calculeazaAmprenta(mac, cid):
	"""Amprenta din MAC si CID (texte; lipsa = gol): 32 de semne hexa, sau "" cand lipsesc amandoua."""
	mac = (mac or "").strip().lower()
	if mac.replace(":", "").replace("0", "") == "":
		mac = ""
	cid = "".join((cid or "").split()).lower()
	if not mac and not cid:
		return ""
	return hashlib.pbkdf2_hmac("sha256", ("%s|%s" % (mac, cid)).encode("utf-8"), SARE_AMPRENTA, ITERATII_AMPRENTA,
		16).hex()


def amprenta(radacina=""):
	"""Amprenta acestui receptor, facuta o singura data pe proces."""
	global _amprenta
	with _LACAT_AMPRENTA:
		if _amprenta is None:
			_amprenta = calculeazaAmprenta(_citesteText(_cale(radacina, CALE_MAC), 64),
				_citesteText(_cale(radacina, CALE_CID), 128))
		return _amprenta


def _notaAcceptata():
	if threading.current_thread() is threading.main_thread():
		try:
			return int(_b(None).nota.value)
		except Exception:
			return 0
	return _NOTA_LOCALA


def cuAmprenta(corp):
	"""Corpul unui pachet cu amprenta langa id (o copie). Amprenta pleaca numai cu nota 2 (cea care o descrie): nota din
	corp sau, la corpurile fara nota (stergerea, profilul), nota acceptata pe receptor. Corpurile fara id raman cum sunt."""
	if not isinstance(corp, dict) or "id" not in corp or "amprenta" in corp:
		return corp
	try:
		nota = int(corp["nota"]) if "nota" in corp else _notaAcceptata()
	except (TypeError, ValueError):
		nota = 0
	if nota < 2:
		return corp
	c = dict(corp)
	c["amprenta"] = amprenta()
	return c


def identificatorNou():
	"""32 de cifre hexa intamplatoare: nimic din receptor (MAC, serie, antetul placii)."""
	return os.urandom(16).hex()


def idValid(text):
	return bool(text) and bool(_ID.match(text))


# ------------------------------------------------------------------ setarile

def initConfig(config=None):
	"""config.hds_beta, facut la prima folosire."""
	global _NOTA_LOCALA
	if config is None:
		from Components.config import config
	if "hds_beta" in config.content.items:
		_NOTA_LOCALA = int(config.hds_beta.nota.value)
		_reiaStergerea(config.hds_beta)
		return config.hds_beta
	from Components.config import ConfigSubsection, ConfigYesNo, ConfigText, ConfigInteger
	b = ConfigSubsection()
	b.activ = ConfigYesNo(default=False)
	for fel in FELURI:
		setattr(b, fel, ConfigYesNo(default=True))
	b.nume = ConfigText(default="", fixed_size=False)
	b.email = ConfigText(default="", fixed_size=False)
	# "" = intrebarea nepusa inca, "da", "nu" (nu mai apare niciodata), "setari" (inscris singur din Setari)
	b.intrebare = ConfigText(default="", fixed_size=False)
	b.id = ConfigText(default="", fixed_size=False)
	b.nota = ConfigInteger(default=0, limits=(0, 9999))
	b.acord = ConfigText(default="", fixed_size=False)
	b.acord_ora = ConfigYesNo(default=False)
	b.server = ConfigText(default=SERVER, fixed_size=False)
	b.public = ConfigText(default="", fixed_size=False)
	b.automat = ConfigYesNo(default=True)
	config.hds_beta = b
	# 0.7.8 punea Beta tester pornit din fabrica si il scria pe disc; fara identificator nu e o alegere a omului (acordul
	# face mereu identificatorul), deci ramane oprit, ca pe orice receptor neinscris
	if b.activ.value and not idValid(b.id.value):
		b.activ.value = False
		b.activ.save()
	_NOTA_LOCALA = int(b.nota.value)
	_reiaStergerea(b)
	return b


def _b(b=None):
	return b if b is not None else initConfig()


def salveaza(b=None):
	"""Setarile pe disc pe loc (o cadere nu face intrebarea sa apara din nou)."""
	global _NOTA_LOCALA, _REVIZIE_ACORD
	b = _b(b)
	_NOTA_LOCALA = int(b.nota.value)
	_REVIZIE_ACORD += 1
	try:
		b.save()
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("salvarea setarilor: %s" % e)


def bife(b=None):
	b = _b(b)
	return dict((fel, bool(getattr(b, fel).value)) for fel in FELURI)


def inscris(b=None):
	"""Programul pornit, cu identificator si cu nota de acum acceptata (meniul testerului)."""
	b = _b(b)
	return (_STERGERE_DOSAR == DOSAR and _STERGERE is not None and _STERGERE.gata and _STERGERE.ok and
		bool(b.activ.value) and idValid(b.id.value) and int(b.nota.value) >= NOTA)


def notaVeche(b=None):
	"""Inscris cu o nota mai veche: nimic nu mai pleaca pana la acordul nou (afara de stergere)."""
	b = _b(b)
	return bool(b.activ.value) and idValid(b.id.value) and int(b.nota.value) < NOTA


def serverValid(adresa):
	"""https:// oriunde; http:// numai spre 127.0.0.1 sau o adresa din reteaua locala (probele)."""
	adresa = (adresa or "").strip()
	if adresa.startswith("https://") and len(adresa) > 12:
		return True
	m = re.match(r"\Ahttp://([0-9.]+)(?::\d{1,5})?/", adresa)
	if not m:
		return False
	ip = m.group(1)
	return ip == "127.0.0.1" or ip.startswith("10.") or ip.startswith("192.168.") or \
		bool(re.match(r"\A172\.(1[6-9]|2\d|3[01])\.", ip))


def adresaServer(b=None):
	"""Adresa serverului din setarea ascunsa. Pentru probe, un fisier in RAM (CALE_SERVER_PROBA, pierdut la repornire)
	poate da un server de proba, numai http:// spre 127.0.0.1 sau reteaua locala."""
	b = _b(b)
	return _adresaServer(b.server.value)


def _adresaServer(valoare):
	"""Resolve a captured setting; also usable without config objects on a worker."""
	proba = (_citesteText(CALE_SERVER_PROBA, 256) or "").strip()
	if proba.startswith("http://") and serverValid(proba):
		return proba if proba.endswith("/") else proba + "/"
	adresa = (valoare or "").strip()
	if not serverValid(adresa):
		return SERVER
	return adresa if adresa.endswith("/") else adresa + "/"


def textNume(text, maxim):
	"""Un text scris de om: fara caractere de control, fara spatii la capete, taiat."""
	text = "".join(c for c in (text or "") if c >= " " and c != "\x7f").strip()
	return text[:maxim]


def emailValid(text):
	return not text or bool(_EMAIL.match(text))


def numePublicValid(text):
	text = textNume(text, NUME_PUBLIC_MAX + 1)
	return NUME_PUBLIC_MIN <= len(text) <= NUME_PUBLIC_MAX and bool(_NUME_PUBLIC.match(text))


def acceptaAcord(feluri, nume="", email="", b=None, de_unde="setari", acum=None, automat=True):
	"""„Sunt de acord” (televizor sau web): bifele, numele si e-mailul, identificatorul (nou daca lipseste), nota de
	acum. Setarile se scriu pe loc; acordul pleaca la server prin coada. -> (reusit, mesaj)"""
	b = _b(b)
	if not _reiaStergerea(b):
		if _STERGERE is not None and not _STERGERE.gata:
			return False, _t("Se verifică datele programului în fundal. Așteaptă puțin.")
		return False, _t(STERGERE_DISC)
	email = textNume(email, EMAIL_MAX)
	if not emailValid(email):
		return False, _t("Adresa de e-mail nu pare bună.")
	for fel in FELURI:
		getattr(b, fel).value = bool(feluri.get(fel, False))
	b.nume.value = textNume(nume, NUME_MAX)
	b.email.value = email
	b.automat.value = bool(automat)
	if not idValid(b.id.value):
		b.id.value = identificatorNou()
	prima_activare = not b.activ.value
	b.activ.value = True
	b.nota.value = NOTA
	b.acord.value = oraUtc(acum)
	if b.intrebare.value not in ("da", "nu"):
		b.intrebare.value = de_unde
	# acordul de acum are deja ora de functionare: nu se mai retrimite la prima ora
	c = _starea.get("contor")
	if c is not None and c.secunde >= ORA_S:
		b.acord_ora.value = True
	salveaza(b)

	def dupaAcord(s):
		s["nota_veche"] = False
		s["fara_acord"] = False
		# culegerea de acum tine loc de trimiterea zilnica de azi (nu a doua oara peste cateva minute)
		s["ultim_auto"] = int(time.time())
	schimbaStare(dupaAcord)
	_ceruteAcum["acord"] = True
	_ceruteAcum["culegere"] = True
	# numarul de testeri ai modelului se cere din nou (acum il numara si pe el)
	_starea["numar_cand"] = None
	text = _t("Felicitări, ești beta tester. Datele bifate pleacă de acum.")
	if prima_activare:
		_canalDupaPauza()
		text += "\n\n" + _t(DUPA_ACTIVARE) + "\n\n" + _t(NU_E_ASISTENTA)
	return True, text


def schimbaBife(feluri, nume=None, email=None, b=None, automat=None):
	"""Bifele schimbate din meniul testerului: pleaca un acord nou (serverul refuza apoi felurile debifate)."""
	b = _b(b)
	if not inscris(b):
		return False, _t("Nu ești înscris în programul de beta testeri.")
	if email is not None:
		email = textNume(email, EMAIL_MAX)
		if not emailValid(email):
			return False, _t("Adresa de e-mail nu pare bună.")
		b.email.value = email
	if nume is not None:
		b.nume.value = textNume(nume, NUME_MAX)
	if automat is not None:
		b.automat.value = bool(automat)
	for fel in FELURI:
		if fel in feluri:
			getattr(b, fel).value = bool(feluri[fel])
	b.acord.value = oraUtc()
	salveaza(b)
	_ceruteAcum["acord"] = True
	return True, _t("Salvat. Serverul primește alegerile noi cu următoarea trimitere.")


def raspundeIntrebarii(da, b=None):
	"""Raspunsul la intrebare, scris pe loc. Nu: nu mai apare niciodata."""
	b = _b(b)
	b.intrebare.value = "da" if da else "nu"
	salveaza(b)


def modulCanalTesteri():
	"""Components.HdsActualizari cu bifa canalului testerilor (Primeste intai versiunile pentru testeri), sau None:
	randul din meniul testerului (TV si web) nu apare. Modulul exista si in 0.6.7, fara bifa, deci se verifica numele,
	nu numai importul; importul e aici, nu sus (HdsActualizari intreaba si el acest modul)."""
	try:
		from Components import HdsActualizari as A
		if hasattr(A, "testeri_pornit") and hasattr(A, "TEXT_BIFA_TESTERI") and hasattr(getattr(A, "actualizari", None),
				"testeri"):
			return A
	except Exception as e:
		_jurnal("canalul testerilor: %s" % e)
	return None


def canalTesteriPornit(A=None):
	"""Bifa canalului testerilor e pusa? (False fara modul)"""
	A = A or modulCanalTesteri()
	try:
		return bool(A is not None and A.testeri_pornit())
	except Exception:
		return False


def opresteCanalTesteri():
	"""Cine iese din program nu mai primeste versiunile testerilor: bifa canalului testerilor se opreste.
	Fara modulul acela sau fara bifa pornita nu face nimic."""
	A = modulCanalTesteri()
	if A is None or not canalTesteriPornit(A):
		return
	try:
		if A.actualizari.testeri(False):
			_jurnal("canalul testerilor oprit la iesire")
		else:
			_jurnal("canalul testerilor la iesire: %s" % (getattr(A.actualizari, "mesaj", "") or "nu s-a putut"))
	except Exception as e:
		_jurnal("canalul testerilor la iesire: %s" % e)


def iesire(b=None, gata=None):
	"""Start local deletion; completion and config access stay on main."""
	global _STERGERE, _STERGERE_DOSAR, _GENERATIE
	b = _b(b)
	corp = {"v": PROTOCOL, "id": b.id.value if idValid(b.id.value) else "", "nota": int(b.nota.value)}
	if _STERGERE is not None and not _STERGERE.gata:
		if gata is not None:
			_STERGERE.dupa.append(gata)
		if _STERGERE.corp is None:
			_STERGERE.cerere_noua = corp
		return _STERGERE
	_GENERATIE += 1
	_STERGERE_DOSAR = DOSAR
	_STERGERE = StergereLocala(b, corp, gata)
	return _STERGERE


def _reiaStergerea(b):
	"""Only schedule IO here, never read the disk in initConfig or tic."""
	global _STERGERE, _STERGERE_DOSAR
	if _STERGERE_DOSAR != DOSAR or _STERGERE is None or (_STERGERE.gata and not _STERGERE.ok):
		_STERGERE_DOSAR = DOSAR
		_STERGERE = StergereLocala(b)
	return _STERGERE.gata and _STERGERE.ok


class StergereLocala:
	"""Durable intent, main-thread reset, verified byte write, then private-file cleanup."""
	def __init__(self, b, corp=None, gata=None):
		self.b = b
		self.gata = self.ok = False
		self.mesaj = ""
		self.dupa = [gata] if gata is not None else []
		self.rezervare = None
		self.corp = corp
		self.cerere_noua = None
		self.durabila = False
		self._lucru(self._pregateste, self._pregatita)

	def _lucru(self, functie, dupa):
		from Components.HdsPazaModel import LucrareFundal
		self.lucrare = LucrareFundal(functie, dupa)

	def _pregateste(self):
		with _LACAT:
			if self.corp is None:
				try:
					with open(cale("stergere.json"), "r", encoding="utf-8") as f:
						corp = json.load(f)
				except FileNotFoundError:
					try:
						_syncDosar(DOSAR)
					except FileNotFoundError:
						pass
					citesteStare()
					return None
			else:
				corp = cuAmprenta(self.corp)
				corp.pop("nota", None)
				scrieJson(cale("stergere.json"), corp)
				_syncDosar(DOSAR)
			self.durabila = True
			if not isinstance(corp, dict) or not isinstance(corp.get("id"), str) or \
					(corp["id"] and not idValid(corp["id"])):
				raise OSError("Invalid local deletion intent")
			if not re.fullmatch(r"[0-9a-f]{16}", str(corp.get("cerere_locala", ""))):
				corp["cerere_locala"] = os.urandom(8).hex()
				scrieJson(cale("stergere.json"), corp)
				_syncDosar(DOSAR)
			return corp

	def _pregatita(self, corp, eroare):
		global _GENERATIE, _NOTA_LOCALA
		if eroare:
			self._termina(False)
			return
		if corp is None:
			if self.cerere_noua is not None:
				self.corp, self.cerere_noua = self.cerere_noua, None
				self._lucru(self._pregateste, self._pregatita)
				return
			self._termina(True)
			return
		self.corp = corp
		_GENERATIE += 1
		b = self.b
		# Stop personal work immediately, including when the disk must be retried.
		b.activ.value = False
		_ceruteAcum.clear()
		_ceruteAcum["trimite"] = True
		_starea.update({"activ": False, "numar_cand": None, "cerere_raspunsuri": None,
			"raspunsuri_datorat": False, "de_anuntat": False})
		opresteCanalTesteri()
		import sys
		forum = sys.modules.get("Components.HdsForumReceptor")
		if forum is not None:
			with forum._lacat_jeton:
				forum._jeton.update({"jeton": "", "id": "", "expira": 0.0, "nume": "", "cont": None})
		try:
			from Components.config import config, configfile, TranzactieSetari, _octetiSetari
			self.rezervare = TranzactieSetari()
			b.id.value = corp["id"]
			b.nota.value = 0
			_NOTA_LOCALA = 0
			b.acord.value = ""
			b.acord_ora.value = False
			b.nume.value = b.email.value = b.public.value = ""
			b.automat.value = True
			for fel in FELURI:
				getattr(b, fel).value = True
			if b.intrebare.value == "":
				b.intrebare.value = "nu"
			b.save()
			self.fisier = configfile.CONFIG_FILE
			self.octeti = _octetiSetari(config.pickle())
			self._lucru(self._scrie, self._scrisa)
		except Exception:
			self._termina(False)

	def _scrie(self):
		from Components.config import _scrieSigur
		if not self.rezervare.ruleaza(_scrieSigur, self.fisier, self.octeti):
			raise OSError("Settings write failed")
		with open(self.fisier, "rb") as f:
			if f.read() != self.octeti:
				raise OSError("Settings verification failed")

	def _scrisa(self, rezultat, eroare):
		if eroare:
			self._termina(False)
			return
		try:
			# Drain unrelated saves using fresh main-thread snapshots before releasing the reservation.
			cereri = self.rezervare.preia()
			if cereri:
				self._lucru(lambda: self.rezervare.termina(cereri), self._scrisa)
				return
			self.rezervare.inchide()
			self.rezervare = None
			self._lucru(self._curata, self._curatata)
		except Exception:
			self._termina(False)

	def _curata(self):
		with _LACAT:
			golesteCoada(pastreaza_stergerea=True, strict=True)
			for nume in ("ultimul.json", "trimise.json", "raspunsuri.json", "stare.json", "cheie", "forum-vazut.json"):
				try:
					os.remove(cale(nume))
				except FileNotFoundError:
					pass
			if idValid(self.corp["id"]):
				marcaj = self.corp["cerere_locala"]
				gasita = False
				for f in _fisiereCoada(strict=True):
					if "-sterge-" in f and f.split("-", 1)[0].endswith(marcaj):
						with gzip.open(os.path.join(dosarCoada(), f), "rt", encoding="utf-8") as fi:
							gasita = json.load(fi).get("id") == self.corp["id"] or gasita
				if not gasita:
					corp = {k: v for k, v in self.corp.items() if k != "cerere_locala"}
					puneInCoada("sterge", "sterge", corp, marcaj=marcaj)
				_syncDosar(dosarCoada())
			os.remove(cale("stergere.json"))
			_syncDosar(DOSAR)

	def _curatata(self, rezultat, eroare):
		self._termina(not eroare)

	def _termina(self, ok):
		if self.rezervare is not None:
			self.rezervare.inchide(fortat=True)
			self.rezervare = None
		self.ok = ok
		if ok:
			self.mesaj = _t("Ai ieșit din program. Cererea de ștergere pleacă la server când ai internet. "
				"Datele personale au fost șterse de pe receptor; identificatorul anonim rămâne pe termen nedeterminat.")
		elif self.durabila:
			self.mesaj = _t(STERGERE_DISC)
		else:
			self.mesaj = _t("Cererea de ștergere nu a putut fi salvată pe receptor. Încearcă din nou.")
		self.gata = True
		for dupa in self.dupa:
			try:
				dupa(self.ok, self.mesaj)
			except Exception as e:
				_jurnal("stergere, dupa: %s" % e.__class__.__name__)
		self.dupa = []



def _canalDupaPauza():
	"""Pornirea din nou dupa pauza (TODO 1391 b): canalul testerilor pus la loc cum era inainte de pauza."""
	try:
		if not citesteStare().get("canal_testeri_pauza"):
			return
		schimbaStare(lambda st: st.pop("canal_testeri_pauza", None))
		A = modulCanalTesteri()
		if A is not None and not canalTesteriPornit(A):
			A.actualizari.testeri(True)
			_jurnal("canalul testerilor pus la loc dupa pauza")
	except Exception as e:
		_jurnal("canalul testerilor dupa pauza: %s" % e)


def inPauza(b=None):
	"""Beta tester pus pe pauza (TODO 1391 b): oprit, dar cu identificatorul si nota pastrate."""
	b = _b(b)
	return not b.activ.value and idValid(b.id.value) and int(b.nota.value or 0) > 0


def pauza(b=None):
	"""„Pune pe pauză (păstrezi înscrierea)” (TODO 1391 b; Eduard 30.10.2026 11:10-11:13: oamenii pornesc si opresc des
	Beta tester). Receptorul nu mai trimite nimic si iese din numaratoare prin ruta „iesire” a serverului (Api::iesire:
	fara stergere, datele raman pana la termenele lor), dar pastreaza identificatorul, nota, bifele, numele, e-mailul,
	numele public si cheia profilului. Pornirea din nou (acceptaAcord) foloseste acelasi identificator, iar serverul
	intoarce aceeasi inscriere (iesit = NULL). Coada celorlalte pachete se goleste. -> (reusit, mesaj)"""
	b = _b(b)
	if _STERGERE_DOSAR == DOSAR and _STERGERE is not None and not _STERGERE.gata:
		return False, _t("Se verifică datele programului în fundal. Așteaptă puțin.")
	if not b.activ.value or not idValid(b.id.value):
		return False, _t("Nu ești înscris în programul de beta testeri.")
	golesteCoada(pastreaza_stergerea=True)
	puneInCoada("iesire", "iesire", {"v": PROTOCOL, "id": b.id.value})
	b.activ.value = False
	salveaza(b)
	_jurnal("pauza (inscrierea pastrata)")
	# canalul testerilor se opreste pe pauza si se pune la loc la pornirea din nou (acceptaAcord), daca era pornit
	canal = canalTesteriPornit()
	schimbaStare(lambda st: st.__setitem__("canal_testeri_pauza", canal))
	opresteCanalTesteri()
	_ceruteAcum["trimite"] = True
	_starea["numar_cand"] = None
	_starea["activ"] = False
	return True, _t("Beta tester e pe pauză: receptorul nu mai trimite nimic. Îl pornești din nou din meniul Beta "
		"tester, cu aceeași înscriere.")


# ------------------------------------------------------------------ nota noua: anuntul si acordul dintr-o apasare
# Cine a acceptat o nota mai veche (notaVeche) nu mai trimite nimic. Anuntul ii spune: pe receptor la prima pornire dupa
# actualizare (cand bara canalului e libera, ca la intrebare, si la cel putin NOTA_ANUNT_DUPA_S de la pornire), apoi
# cel mult o data pe zi (ziua locala in stare.json: nota_anunt_zi pe receptor, nota_web_zi pentru „Mai tarziu” din
# web); in web sus pe orice pagina, pana la acord. „Accept” = acordul nou cu bifele, numele, e-mailul si trimiterea
# automata de dinainte. Textul intreg al notei e in imagine (CALE_NOTA, copia lui situl-imaginii/date/nota-testeri.json
# fara campul „despre”), ca omul sa-l citeasca pe receptor fara navigator.

NOTA_ANUNT_DUPA_S = 120
CEAS_BUN_DUPA = 1700000000      # ceasul receptorului e pus (dupa 2023); inainte de ora din retea nu se stie ziua
CALE_NOTA = os.environ.get("HDS_BETA_NOTA") or "/usr/share/enigma2/nota-testeri.json"
NOTA_TEXT_MAX = 256 * 1024


def ziLocala(secunde=None):
	"""Ziua dupa ora receptorului, „AAAA-LL-ZZ”; "" cat ceasul nu e pus."""
	secunde = time.time() if secunde is None else secunde
	if secunde < CEAS_BUN_DUPA:
		return ""
	return time.strftime("%Y-%m-%d", time.localtime(secunde))


def anuntNotaDatorat(b=None, stare=None, acum=None, cheie="nota_anunt_zi"):
	"""Anuntul notei noi e de aratat azi? Numai cu nota veche, cu ceasul pus si daca nu s-a aratat (sau amanat) azi.
	`cheie`: nota_anunt_zi (receptorul) sau nota_web_zi (banda din web)."""
	if not notaVeche(b):
		return False
	zi = ziLocala(acum)
	if not zi:
		return False
	stare = citesteStare() if stare is None else stare
	return stare.get(cheie) != zi


def amanaAnuntNota(acum=None, cheie="nota_anunt_zi"):
	"""Anuntul aratat azi sau „Mai tarziu”: revine a doua zi."""
	zi = ziLocala(acum)
	if zi:
		schimbaStare(lambda s: s.__setitem__(cheie, zi))
	return True, _t("Îți amintim mâine.")


def acceptaNotaNoua(b=None):
	"""„Accept” din anunt (receptor sau web): acordul pe nota de acum, cu alegerile de dinainte. -> (reusit, mesaj)"""
	b = _b(b)
	if not notaVeche(b):
		return False, _t("Nu ești înscris în programul de beta testeri.")
	ok, mesaj_ = acceptaAcord(bife(b), b.nume.value, b.email.value, b, de_unde="setari", automat=bool(b.automat.value))
	if not ok:
		return False, mesaj_
	_jurnal("nota %d acceptata din anunt" % NOTA)
	return True, _t(NOTA_ACCEPTATA)


def noutatiNota():
	"""Ce e nou in nota de acum, tradus: [text]."""
	return [_t(t) for t in NOTA_NOUTATI]


def limbaNotei(limba_=None):
	"""Nota intreaga e in romana si engleza: romana pentru meniurile in romana, engleza pentru restul."""
	limba_ = limba() if limba_ is None else limba_
	return "ro" if (limba_ or "").lower().startswith("ro") else "en"


def adresaNotei(limba_=None):
	return ADRESA_NOTA if limbaNotei(limba_) == "ro" else ADRESA_NOTA_EN


def _randuriNota(valoare):
	"""Textul unui camp al unei sectiuni: paragrafele, randurile tabelului (eticheta: text), listele. Legaturile nu:
	textul lor e deja in paragrafe."""
	rez = []
	for x in valoare if isinstance(valoare, list) else []:
		if isinstance(x, str):
			rez.append(x)
		elif isinstance(x, list) and x and all(isinstance(y, str) for y in x):
			rez.append(": ".join(x))
	return rez


def textNota(limba_=None, cale_nota=None):
	"""Nota intreaga, din copia din imagine, in limba notei: (titlu, text), sau None cand copia lipseste, nu se poate
	citi sau e a altei versiuni decat NOTA (atunci ecranul deschide pagina notei in navigator)."""
	cale_nota = cale_nota or CALE_NOTA
	try:
		if os.path.getsize(cale_nota) > NOTA_TEXT_MAX:
			return None
		with open(cale_nota, "rb") as f:
			d = json.loads(f.read().decode("utf-8"))
	except (OSError, IOError, ValueError):
		return None
	if not isinstance(d, dict) or d.get("versiune") != NOTA:
		return None
	n = d.get(limbaNotei(limba_)) or {}
	if not isinstance(n, dict) or not isinstance(n.get("sectiuni"), list):
		return None
	parti = [n.get("versiune_text") or "", n.get("rezumat") or ""]
	for s in n["sectiuni"]:
		if not isinstance(s, dict):
			continue
		parti.append((s.get("titlu") or "").upper())
		for camp in ("paragrafe", "tabel", "lista", "pasi", "paragrafe_dupa"):
			lista = _randuriNota(s.get(camp))
			if camp in ("tabel", "lista"):
				lista = ["•  " + x for x in lista]
			elif camp == "pasi":
				lista = ["%d. %s" % (k + 1, x) for k, x in enumerate(lista)]
			parti.extend(lista)
	text = "\n\n".join(p for p in parti if p)
	return (n.get("titlu") or _t("Nota de confidențialitate")), text


# cererile facute din ecran sau din web, culese de tic() pe firul enigma2
_ceruteAcum = {}


# ------------------------------------------------------------------ contorul orei si numaratoarea

class Contor(object):
	"""Orele de functionare cumulate (fara standby) si numaratoarea folosirii, in fisierul ORE (un JSON mic)."""

	def __init__(self, cale_fisier=None, ceas=None):
		self.cale = cale_fisier or cale("ore.json")
		self.ceas = ceas or time.monotonic
		self.secunde = 0.0
		self.ecrane = {}
		self.zapuri = 0
		self.inregistrari = 0
		self._ultim = None
		self._scris = None
		self.citeste()

	def citeste(self):
		d = citesteJson(self.cale, {}) or {}
		try:
			self.secunde = max(0.0, float(d.get("secunde", 0)))
		except (TypeError, ValueError):
			self.secunde = 0.0
		ecrane = d.get("ecrane") or {}
		self.ecrane = dict((str(k)[:60], int(v)) for k, v in list(ecrane.items())[:ECRANE_MAX]
			if isinstance(v, int) and v > 0)
		self.zapuri = int(d.get("zapuri", 0) or 0)
		self.inregistrari = int(d.get("inregistrari", 0) or 0)

	def tic(self, standby, acum=None):
		acum = self.ceas() if acum is None else acum
		if self._ultim is not None and not standby:
			pas = acum - self._ultim
			if 0 < pas < 10 * TIC_S:
				self.secunde += pas
		self._ultim = acum
		if self._scris is None:
			self._scris = acum

	def ore(self):
		return round(self.secunde / 3600.0, 1)

	def trebuieScris(self, interval, acum=None):
		acum = self.ceas() if acum is None else acum
		return self._scris is not None and acum - self._scris >= interval

	def scrie(self, acum=None):
		self._scris = self.ceas() if acum is None else acum
		try:
			scrieJson(self.cale, {"secunde": int(self.secunde), "ecrane": self.ecrane, "zapuri": self.zapuri,
				"inregistrari": self.inregistrari})
		except (OSError, IOError) as e:
			_jurnal("contorul orei: %s" % e)

	def numaraEcran(self, nume):
		if not nume or esteEcranDeAcces(nume):
			return
		nume = nume[:60]
		if nume in self.ecrane or len(self.ecrane) < ECRANE_MAX:
			self.ecrane[nume] = self.ecrane.get(nume, 0) + 1

	def utilizare(self):
		"""Datele felului „utilizare” de pana acum; dupa trimitere se pune la zero (zeroUtilizare)."""
		return {"ecrane": dict(self.ecrane), "zapuri": self.zapuri, "inregistrari": self.inregistrari}

	def zeroUtilizare(self):
		self.ecrane = {}
		self.zapuri = 0
		self.inregistrari = 0


def trebuieIntrebat(b, contor):
	"""Intrebarea: inca nepusa, programul oprit, peste o ora cumulata."""
	return b.intrebare.value == "" and not bool(b.activ.value) and contor.secunde >= ORA_S


def potIntreba(stare):
	"""Numai peste televizorul in direct: `stare` = {standby, bara_libera, film, inregistrare, decalaj}."""
	return (not stare.get("standby") and stare.get("bara_libera") and not stare.get("film")
		and not stare.get("inregistrare") and not stare.get("decalaj"))


# ------------------------------------------------------------------ curatarea textelor

# despre accesul conditionat, fara numele modulelor: orice cuvant terminat in „cam” / „camd” (cu cifre dupa), si cand e lipit
# de urmatorul cu litera mare („SoftcamSetup”, „CamInfo”: „camera” ramane), numele lipite de orice („softcammanager”), cartelele,
# ECM / EMM / CAID, interfetele CI, descifrarea, cuvintele de trei litere „?box” si protocoalele „cs123x”
_ACCES = re.compile(r"[a-z0-9]*cams?d?[0-9]*(?!(?-i:[a-z]))|softcam|oscam|ncam|cccam|card|cartel|(?<![a-z])ecm|(?<![a-z])emm|caid|provid|"
	r"(?<![a-z])ca[_ ]?(?:pmt|info|service|handler|descr)|(?<![a-z])ci[0-9+_ ]|ci\+|ciplus|dvbapi|descifr|decript|"
	r"decrypt|descramb|scrambl|criptat|biss|(?<![a-z])cw(?![a-z])|(?<![a-z])[a-z]box(?![a-z])|(?<![a-z])cs[0-9]{3}x|"
	r"(?<![a-z])sc[0-9]|abonament|subscription|reader|keyserver", re.I)
_SECRET = re.compile(r"pass(?:word|wd)?|pwd|parol|(?<![a-z])psk|wpa|ssid|token|jeton|secret|(?<![a-z])key(?![a-z])|"
	r"apikey|api_key|(?<![a-z])pin(?![a-z])|cookie|authoriz|bearer|credential|cheie|eyJ[\w-]{8,}\.[\w-]{8,}", re.I)
_IP4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IP6 = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}(?![0-9A-Fa-f:])")
# forma prescurtata, cu „::” (fe80::1234, mesajele nucleului despre IPv6 din hds-blocaj-*.txt; 02.11.2026): la stanga
# si la dreapta nicio litera, ca std::string sau un „::” singur sa ramana
_IP6_SCURT = re.compile(r"(?<![0-9A-Za-z:])(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?::"
	r"(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?(?![0-9A-Za-z:])")
_MAC = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
_EMAIL_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"\b(?:https?|rtsp|rtmp|rtp|udp|ftp|mms|smb|nfs)://[^\s\"'<>]+", re.I)
_FILM = re.compile(r"/(?:media|run/media|mnt|hdd|autofs|home/root/movie|movie)/[^\s\"'<>:]+")
_REF_IPTV = re.compile(r"(?:4097|5001|5002|8193|8739):0:[0-9A-Fa-f:]+%3a[^\s\"']*", re.I)


def esteDeAcces(text):
	"""Un rand sau un nume de ecran despre accesul conditionat (nu se trimite)."""
	return bool(_ACCES.search(text or ""))


def esteEcranDeAcces(nume):
	"""Numele clasei unui ecran despre accesul conditionat (HdsInterfeteCam, CiSelection, HdsModuleAcces...): cuvintele
	lipite se despart intai."""
	cuvinte = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", nume or "")
	return esteDeAcces(cuvinte) or bool(re.search(r"(?<![a-z])(?:acces|access|module)(?![a-z])", cuvinte, re.I))


def curata(text):
	"""Textul integral pentru echipa."""
	return text or ""


# hds-zap.log (0.7.7, lib/service/hdsjurnalzap.cpp): si randurile zap-urilor reusite au la coada „| canal: nume=... ref=...”
# (pentru asistenta, unde omul a cerut ajutorul). In pachetele testerilor canalul ramane numai pe randurile cu esec
# („canalul care nu merge”, din nota 2); pe cele reusite (INFO) coada se taie, altfel jurnalul ar fi lista canalelor
# privite, iar nota spune „fără listele tale de canale”.
_ZAP_REUSIT_CANAL = re.compile(r"^(.*\[INFO\] \[zap\] .*?) \| canal: .*$")


def faraCanaleReusite(text):
	"""Textul integral pentru echipa."""
	return text or ""


def coada(text, maxim=JURNAL_MAX):
	"""Ultima parte a unui text (eroarea e de obicei la sfarsit)."""
	if len(text) <= maxim:
		return text
	return "[...]\n" + text[-maxim:]


_CHEI_EXCEPTIE = (r"pass(?:word|wd)?|pwd|parol(?:a|e)?|token|jeton|secret|key|cheie|api[_-]?key|access[_-]?key|"
	r"private|psk|pin|auth|authorization|authentication|bearer|user(?:name|s)?|login|utilizator|ssid|wpa|wifi|wlan[0-9]*|essid|serial|s/n|sn|cpuid|"
	r"chip_?id|die.?id|uuid|cid|cw|control.?word|biss|ecm|emm|cookie|session")
_VALOARE_EXCEPTIE = re.compile(r"(?<![a-z0-9_])[a-z0-9_.-]*(?:" + _CHEI_EXCEPTIE +
	r")(?:[_-][a-z0-9_-]+)?[\"']?\s*[=:]\s*(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\n]*)", re.I)
_CAMP_EXCEPTIE = re.compile(r"(?<![a-z0-9_])(?:" + _CHEI_EXCEPTIE + r")\s+[^\n]*", re.I)


def curataExceptie(text):
	"""Textul integral pentru echipa."""
	return text or ""


# ------------------------------------------------------------------ felul „jurnale”

_CDATA_JURNAL = re.compile(r"<enigma2crashlog>\s*<!\[CDATA\[(.*?)\]\]>\s*</enigma2crashlog>", re.S)
_VERSIUNE_XML = re.compile(r"<version>(.*?)</version>", re.S)
_DATA_XML = re.compile(r"<crashdate>(.*?)</crashdate>", re.S)


def felJurnal(nume, text):
	"""(fel, text de trimis) pentru un jurnal din /home/root/logs: nucleu (scris de bsod), plugin_extern (eroare intr-un
	plugin extern, interfata a mers mai departe: Components/HdsPluginExtern), ecran (ecran cazut), actualizare,
	extensii, eroare."""
	if nume.startswith("enigma2_crash_"):
		if text.startswith("HD Satelit: raport de eroare, plugin extern"):
			return "plugin_extern", text
		if text.startswith("HD Satelit: raport de eroare"):
			return "ecran", text
		m = _CDATA_JURNAL.search(text)
		versiune = _VERSIUNE_XML.search(text)
		data = _DATA_XML.search(text)
		parti = []
		if versiune:
			parti.append("versiune: %s" % versiune.group(1).strip()[:40])
		if data:
			parti.append("data: %s" % data.group(1).strip()[:40])
		if m:
			parti.append(m.group(1).replace("]]]]><![CDATA[>", "]]>"))
		else:
			parti.append(text.split("<image>")[0])
		return "nucleu", "\n".join(parti)
	if nume.startswith("hds-actualizari") or nume.startswith("hds-actualizare"):
		return "actualizare", text
	if nume.startswith("hds-extensii"):
		return "extensii", text
	if nume.startswith("hds-blocaj-"):
		return "blocaj", text
	return "eroare", text


# jurnalele imaginii care spun numai o stare buna (prima pornire fara dosarul SSH pe stick, serviciile merg, nicio copie
# a altei imagini): nu pleaca si nu se numara la limita zilei (JURNALE_PE_ZI), altfel ocupau locul erorilor adevarate
_STARE_BUNA = (
	("hds-ssh", re.compile(r"prima pornire: niciun dosar hdsatelit/ssh pe stick")),
	("hds-servicii", re.compile(r"stare ok\b")),
	("hds-restaurare", re.compile(r"se cauta o copie a altei imagini|0 copii gasite|nicio copie|setarile puse")),
)
_CUVINTE_EROARE = re.compile(r"eroare|esec|eșec|error|fail|cazut|căzut|blocat|timeout|traceback|exception", re.I)


def doarStareBuna(nume, text):
	"""Jurnalul se termina cu o stare buna stiuta si nu are niciun cuvant de eroare (atunci nu se trimite)."""
	randuri = [r for r in (text or "").splitlines() if r.strip()]
	if not randuri:
		return False
	for prefix, buna in _STARE_BUNA:
		if nume.startswith(prefix):
			return bool(buna.search(randuri[-1])) and not _CUVINTE_EROARE.search(text)
	return False


def jurnalPermis(nume):
	"""Jurnalele imaginii din /home/root/logs care pot pleca: cele de cadere, stivele interfetei pastrate de paznic la un
	blocaj si *.log; NU jurnalul sistemului (are adresele retelei si numele Wi-Fi) si nici jurnalele de depanare
	intregi."""
	if not nume or "/" in nume or nume.startswith("."):
		return False
	# Auditul exploratorului ramane local; nici copiile editorului nu pleaca.
	if nume.startswith("hds-fisiere.log") or ".hds-inainte" in nume:
		return False
	# Jurnalul interfetei are doua copii rotite, deja mascate la scriere.
	if nume in ("hds-interfata.log", "hds-interfata.log.1", "hds-interfata.log.2"):
		return True
	if nume.startswith("messages") or nume.startswith("syslog") or nume.startswith("Enigma2-debug"):
		return False
	if nume.startswith("enigma2_crash_") and nume.endswith(".log"):
		return True
	if nume.startswith("enigma2-stive-") and nume.endswith(".txt"):
		return True
	# stivele firelor blocate si coada jurnalului nucleului, scrise de paznic inainte de o repornire dura
	if nume.startswith("hds-blocaj-") and nume.endswith(".txt"):
		return True
	return nume.startswith("hds-") and nume.endswith(".log")


def esteCadere(nume):
	"""Caderile, blocajele si hds-caderi.log (limita CADERI_PE_ZI, inaintea jurnalelor obisnuite)."""
	return (nume == "hds-caderi.log" or nume.startswith("enigma2_crash_") or
		nume.startswith("enigma2-stive-") or nume.startswith("hds-blocaj-"))


def esteRar(nume):
	"""Jurnalele actualizarii, ale imaginii noi si ale punerii la loc (limita RARE_PE_ZI, langa cele obisnuite)."""
	return nume.startswith(JURNALE_RARE)


def esteMotor(nume):
	"""Urma comenzilor de motor (limita MOTOR_PE_ZI, langa cele obisnuite si cele rare)."""
	return nume in JURNALE_MOTOR


# stivele firelor Python ale enigma2 (faulthandler, scrise de paznic inainte sa opreasca o interfata care nu mai
# raspunde): pleaca numai randurile formatului lui, ca in raportul pornirii (hds-raport.sh, rp_stive)
# Antetul unui fir: pana la Python 3.13 "Thread 0x... (most recent call first):"; pe 3.14 cu numele firului intre paranteze
# drepte ("Thread 0x... [hds-procesor] (...)"); un singur fir (faulthandler cu all_threads=False, SIGRTMIN+7 din 0.7.7):
# "Stack (most recent call first):". Firul de stive al imaginii (HdsPaznic.textStive, 0.7.7) scrie antetul fara nume si
# numele pe randul "# fir: <nume>" de imediat dinainte. Copia paznicului spune in cap cum au fost citite ("== stivele
# Python (...)": din Python, deci lacatul Python era liber, sau din semnal); randul pleaca ca "stivele Python: ...", fara
# "== " in fata, care in raportul pornirii incepe o sectiune.
_STIVA_FIR = re.compile(r"^(Current thread|Thread) 0x[0-9A-Fa-f]+( \[(.*)\])? \(most recent call first\):$")
_STIVA_UN_FIR = "Stack (most recent call first):"
_STIVA_NUME = "# fir: "
_STIVA_CUM = re.compile(r"^== stivele Python \((citite din Python|din semnal, toate firele|din semnal, semnalul [0-9]+)\)$")
_STIVA_CADRU = re.compile(r'^  File "([A-Za-z0-9_./-]+)", line ([0-9]+|\?\?\?) in ([A-Za-z0-9_<>]+)$')
_STIVA_PYTHON = re.compile(r"python3(\.[0-9]+)?/")
_STIVA_NUME_SEMNE = re.compile(r"[^A-Za-z0-9 _.()-]")
_STIVA_NUME_IP = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")
# cat se citeste dintr-un fisier de stive: in forma faulthandler cu toate firele firul principal ("Current thread") e
# ULTIMUL, dupa firele vazute de nucleu si celelalte fire; cu 8 KiB se taia tocmai el la o interfata cu multe fire (cea mai
# mare copie reala de pe receptorul de proba, cu 13 fire, are 4,8 KiB)
STIVE_CITITE = 16384


def numeFirStiva(nume):
	"""Numele unui fir din antetul stivei: litere, cifre, spatiu si _ . ( ) -, o adresa IPv4 ca x.x.x.x, cel mult 40 de
	semne; al unui modul de acces (regula cadrelor) e numai "modul-acces"."""
	nume = _STIVA_NUME_IP.sub("x.x.x.x", _STIVA_NUME_SEMNE.sub("", nume or ""))[:40].strip()
	if "cam" in nume.lower() or esteDeAcces(nume):
		return "modul-acces"
	return nume


def stiveCurate(text):
	"""Numai randurile stivei: firele fara adresa (cu numele firului, cand il are), cadrele ca fisier, rand si functie,
	calea taiata la ce urmeaza dupa enigma2/python/ sau python3.N/ (alta cale: "(alt fisier)"); un cadru al unui modul de
	acces e numai "(modul-acces)". Fara curata(): regulile lui scot randuri intregi cu nume obisnuite de functii, iar o
	stiva cu goluri nu spune nimic."""
	rez = []
	nume_fir = ""
	for rand in (text or "")[:STIVE_CITITE].splitlines():
		if rand.startswith(_STIVA_NUME):
			nume_fir = rand[len(_STIVA_NUME):]
			continue
		inainte, nume_fir = nume_fir, ""
		m = _STIVA_FIR.match(rand)
		if m:
			nume = numeFirStiva(m.group(3) if m.group(2) else inainte)
			rez.append("%s%s (most recent call first):" % (m.group(1), (" [%s]" % nume) if nume else ""))
			continue
		if rand in (_STIVA_UN_FIR, "  <no Python frame>"):
			rez.append(rand)
			continue
		m = _STIVA_CUM.match(rand)
		if m:
			rez.append("stivele Python: %s" % m.group(1))
			continue
		m = _STIVA_CADRU.match(rand)
		if not m:
			continue
		if "cam" in rand.lower() or esteDeAcces(rand):
			rez.append("  (modul-acces)")
			continue
		cale = m.group(1)
		i = cale.find("enigma2/python/")
		if i >= 0:
			cale = cale[i:]
		else:
			p = _STIVA_PYTHON.search(cale)
			cale = cale[p.start():] if p else "(alt fisier)"
		rez.append('  File "%s", line %s in %s' % (cale, m.group(2), m.group(3)))
	return "\n".join(rez)


def culegeJurnale(stare, dosar_logs=None, cale_paznic=None, acum=None, maxim=JURNALE_PE_ZI):
	"""Jurnalele noi de la ultima trimitere (numele, marimea si ora tinute in stare["jurnale"]) si randurile noi din
	jurnalul paznicului. -> date (dict) sau None cand nu e nimic nou. `stare` se schimba (se scrie dupa ce pachetul
	e in coada)."""
	dosar_logs = dosar_logs or CALE_LOGS
	vazute = stare.setdefault("jurnale", {})
	zi = ziUtc(acum)
	if stare.get("jurnale_zi") != zi:
		stare["jurnale_zi"] = zi
		stare["jurnale_azi"] = 0
		stare["caderi_azi"] = 0
		stare["rare_azi"] = 0
		stare["motor_azi"] = 0
	ramase = max(0, maxim - int(stare.get("jurnale_azi", 0)))
	ramase_caderi = max(0, CADERI_PE_ZI - int(stare.get("caderi_azi", 0)))
	ramase_rare = max(0, RARE_PE_ZI - int(stare.get("rare_azi", 0)))
	ramase_motor = max(0, MOTOR_PE_ZI - int(stare.get("motor_azi", 0)))
	noi = []
	try:
		nume_fisiere = os.listdir(dosar_logs)
	except OSError:
		nume_fisiere = []
	for nume in nume_fisiere:
		if not jurnalPermis(nume):
			continue
		cale_fisier = os.path.join(dosar_logs, nume)
		try:
			st = os.stat(cale_fisier)
		except OSError:
			continue
		if os.path.islink(cale_fisier) or not os.path.isfile(cale_fisier):
			continue
		semn = [int(st.st_size), int(st.st_mtime)]
		if vazute.get(nume) == semn:
			continue
		noi.append((st.st_mtime, nume, cale_fisier, semn))
	# intai caderile si blocajele (limita lor), apoi jurnalele obisnuite (limita lor); in fiecare grup, cele mai noi intai
	noi.sort(key=lambda x: (not esteCadere(x[1]), -x[0]))
	jurnale = []
	obisnuite = caderi = rare = motor = 0
	for mtime, nume, cale_fisier, semn in noi:
		cadere = esteCadere(nume)
		rar = not cadere and esteRar(nume)
		de_motor = not cadere and not rar and esteMotor(nume)
		if (cadere and caderi >= ramase_caderi) or (rar and rare >= ramase_rare) or 				(de_motor and motor >= ramase_motor) or (not cadere and not rar and not de_motor and obisnuite >= ramase):
			continue
		crash = nume.startswith("enigma2_crash_")
		text = _citesteCadere(cale_fisier) if crash else _citesteCoada(cale_fisier, 4 * JURNAL_MAX)
		if text is None:
			continue
		fel, text = felJurnal(nume, text)
		if fel == "eroare" and doarStareBuna(nume, text):
			vazute[nume] = semn
			continue
		if nume.startswith("enigma2-stive-"):
			text = stiveCurate(text)
		elif crash:
			text = curataExceptie(text)
		else:
			text = curata(text)
			if nume.startswith("hds-zap.log"):
				text = faraCanaleReusite(text)
		jurnale.append({"nume": nume[:120], "fel": fel, "scris": oraUtc(mtime), "text": text if crash else coada(text)})
		vazute[nume] = semn
		if cadere:
			caderi += 1
		elif rar:
			rare += 1
		elif de_motor:
			motor += 1
		else:
			obisnuite += 1
	# numele care nu mai exista ies din stare
	for nume in list(vazute):
		if nume not in nume_fisiere:
			del vazute[nume]
	paznic = _randuriNoiPaznic(stare, cale_paznic or CALE_PAZNIC)
	if not jurnale and not paznic:
		return None
	stare["jurnale_azi"] = int(stare.get("jurnale_azi", 0)) + obisnuite
	stare["caderi_azi"] = int(stare.get("caderi_azi", 0)) + caderi
	stare["rare_azi"] = int(stare.get("rare_azi", 0)) + rare
	stare["motor_azi"] = int(stare.get("motor_azi", 0)) + motor
	return {"jurnale": jurnale, "paznic": paznic}


def _citesteCadere(cale_fisier):
	"""De la inceput pana la sfarsitul enigma2crashlog, fara coada XML si fara limita pe stiva."""
	try:
		parti = []
		bloc = False
		cdata = False
		with open(cale_fisier, encoding="utf-8", errors="replace") as f:
			for rand in f:
				if not bloc and rand.lstrip().startswith(("<image>", "<software>", "<checksums>")):
					break
				if "<enigma2crashlog>" in rand:
					bloc = True
				parti.append(rand)
				# In CDATA, tagurile sunt textul exceptiei, nu structura XML.
				for semn in re.findall(r"<!\[CDATA\[|\]\]>", rand):
					cdata = semn == "<![CDATA["
				if bloc and not cdata and "</enigma2crashlog>" in rand:
					break
		return "".join(parti)
	except OSError:
		return None


def _citesteCoada(cale_fisier, maxim):
	try:
		marime = os.path.getsize(cale_fisier)
		with open(cale_fisier, "rb") as f:
			if marime > maxim:
				f.seek(marime - maxim)
			return f.read(maxim).decode("utf-8", "replace")
	except (OSError, IOError):
		return None


def _randuriNoiPaznic(stare, cale_paznic):
	"""Randurile noi din jurnalul paznicului (de la marimea tinuta minte; un fisier mai mic = rotit, de la inceput)."""
	try:
		marime = os.path.getsize(cale_paznic)
	except OSError:
		return []
	inainte = int(stare.get("paznic", 0) or 0)
	if marime < inainte:
		inainte = 0
	if marime == inainte:
		return []
	try:
		with open(cale_paznic, "rb") as f:
			start = max(inainte, marime - 256 * 1024)
			f.seek(start)
			text = f.read(marime - start).decode("utf-8", "replace")
	except (OSError, IOError):
		return []
	stare["paznic"] = marime
	randuri = [r for r in curata(text).splitlines() if r.strip()]
	return [r[:1000] for r in randuri[-PAZNIC_RANDURI:]]


def ultimulJurnalCadere(dosar_logs=None):
	"""(nume, text curatat) al celui mai nou jurnal de cadere, pentru atasarea la un mesaj; sau None."""
	dosar_logs = dosar_logs or CALE_LOGS
	try:
		gasite = []
		for nume in os.listdir(dosar_logs):
			if nume.startswith("enigma2_crash_") and nume.endswith(".log"):
				c = os.path.join(dosar_logs, nume)
				if os.path.isfile(c) and not os.path.islink(c):
					gasite.append((os.path.getmtime(c), nume, c))
	except OSError:
		return None
	if not gasite:
		return None
	gasite.sort(reverse=True)
	_m, nume, c = gasite[0]
	text = _citesteCadere(c)
	if text is None:
		return None
	_fel, text = felJurnal(nume, text)
	return {"nume": nume[:120], "text": curataExceptie(text)}


# ------------------------------------------------------------------ felul „canale”

def semnaturaLamedb(cale_lamedb=None):
	try:
		st = os.stat(cale_lamedb or CALE_LAMEDB)
		return [int(st.st_mtime), int(st.st_size)]
	except OSError:
		return None


_POL = {0: "h", 1: "v", 2: "l", 3: "r"}
_FEC = {0: "auto", 1: "1/2", 2: "2/3", 3: "3/4", 4: "5/6", 5: "7/8", 6: "8/9", 7: "3/5", 8: "4/5", 9: "9/10",
	10: "6/7", 15: "none"}
_MOD = {0: "auto", 1: "qpsk", 2: "8psk", 3: "qam16", 4: "16apsk", 5: "32apsk"}
_RO = {0: "0.35", 1: "0.25", 2: "0.20", 3: "auto"}
_PIL = {0: "off", 1: "on", 2: "auto"}


def _intreg16(text):
	return int(text, 16)


def canaleDinLamedb(text):
	"""Lista transponderelor de satelit cu serviciile lor, din lamedb (formatul 4): fara cablu si terestru, fara
	PID-uri, fara CAID-uri, fara favorite. Pozitia in zecimi de grad (est pozitiv), frecventa in MHz, rata in kS/s."""
	randuri = text.split("\n")
	n = len(randuri)
	i = 0
	tp = {}
	while i < n and randuri[i].strip() != "transponders":
		i += 1
	i += 1
	while i + 1 < n and randuri[i].strip() != "end":
		cheie = randuri[i].strip()
		date = randuri[i + 1].strip()
		i += 2
		while i < n and randuri[i].strip() not in ("/", "end"):
			i += 1
		if i < n and randuri[i].strip() == "/":
			i += 1
		if not date.startswith("s "):
			continue
		try:
			ns, tsid, onid = [_intreg16(x) for x in cheie.split(":")[:3]]
			c = [int(x) for x in date[2:].split(",")[0].split(":")]
		except ValueError:
			continue
		if len(c) < 6:
			continue
		pos = c[4]
		if pos > 1800:
			pos -= 3600
		v = {"pos": pos, "f": int(round(c[0] / 1000.0)), "sr": int(c[1] // 1000), "pol": _POL.get(c[2], "h"),
			"fec": _FEC.get(c[3], "auto"), "inv": c[5], "sys": "s2" if len(c) > 7 and c[7] == 1 else "s",
			"mod": _MOD.get(c[8], "auto") if len(c) > 8 else "qpsk", "ro": _RO.get(c[9], "0.35") if len(c) > 9 else "0.35",
			"pilot": _PIL.get(c[10], "auto") if len(c) > 10 else "auto", "servicii": []}
		tp[(ns, tsid, onid)] = v
	while i < n and randuri[i].strip() != "services":
		i += 1
	i += 1
	while i + 2 < n and randuri[i].strip() != "end":
		cheie = randuri[i].strip().split(":")
		nume = randuri[i + 1].strip()
		date = randuri[i + 2].strip()
		i += 3
		if len(cheie) < 5:
			continue
		try:
			sid, ns, tsid, onid, tip = [_intreg16(x) for x in cheie[:5]]
		except ValueError:
			continue
		t = tp.get((ns, tsid, onid))
		if t is None or len(t["servicii"]) >= 400:
			continue
		furnizor = ""
		for camp in date.split(","):
			if camp.startswith("p:"):
				furnizor = camp[2:]
				break
		t["servicii"].append({"sid": sid, "tsid": tsid, "onid": onid, "tip": tip,
			"nume": textNume(nume, 80), "furnizor": textNume(furnizor, 80)})
	lista = sorted(tp.values(), key=lambda x: (x["pos"], x["f"], x["pol"]))
	return lista[:4000]


def culegeCanale(stare, cale_lamedb=None, acum=None, cerut=False):
	"""Lista canalelor la inscriere si dupa o scanare (lamedb schimbat), singur cel mult o data pe saptamana; cerut de
	om („Trimite acum”) oricand s-a schimbat."""
	semn = semnaturaLamedb(cale_lamedb)
	if semn is None:
		return None
	acum = time.time() if acum is None else acum
	ultim = float((stare.get("ultim") or {}).get("canale", 0) or 0)
	if stare.get("canale_semn") == semn and ultim:
		return None
	if ultim and acum - ultim < SAPTAMANA_S and not cerut:
		return None
	try:
		with open(cale_lamedb or CALE_LAMEDB, "rb") as f:
			text = text_lista(f.read(16 * 1024 * 1024))
	except (OSError, IOError):
		return None
	stare["canale_semn"] = semn
	return {"transpondere": canaleDinLamedb(text)}


# ------------------------------------------------------------------ felul „sistem”

def _meminfo(radacina=""):
	rez = {}
	for rand in (_citesteText(_cale(radacina, "/proc/meminfo"), 8192) or "").splitlines():
		cheie, _s, rest = rand.partition(":")
		p = rest.split()
		if p and p[0].isdigit():
			rez[cheie.strip()] = int(p[0])
	return rez


def _nuclee(radacina=""):
	text = _citesteText(_cale(radacina, "/proc/cpuinfo"), 32768) or ""
	n = len(re.findall(r"(?m)^processor\s*:", text))
	return n or 1


def _rssInterfata(radacina=""):
	for rand in (_citesteText(_cale(radacina, "/proc/self/status"), 8192) or "").splitlines():
		if rand.startswith("VmRSS:"):
			p = rand.split()
			if len(p) > 1 and p[1].isdigit():
				return int(p[1])
	return None


def _incarcare(radacina=""):
	text = _citesteText(_cale(radacina, "/proc/loadavg"), 256) or ""
	try:
		return float(text.split()[0])
	except (IndexError, ValueError):
		return None


def _sus(radacina=""):
	text = _citesteText(_cale(radacina, "/proc/uptime"), 256) or ""
	try:
		return float(text.split()[0])
	except (IndexError, ValueError):
		return None


# Procesorul ocupat de adevarat (0.7.7). Incarcarea medie (/proc/loadavg) numara si firele care dorm in starea D: pe
# placile HiSilicon (SF8008, Viper) firele driverelor tin load ~12-13 cu procesorul ~85% liber, deci incarcare_medie iese
# ~300% fara sa fie ceva ocupat. ocupat_medie / ocupat_max: procentul folosit al tuturor nucleelor din diferenta /proc/stat
# fata de citirea de la ticul dinainte (fereastra ~TIC_S, fara nicio asteptare pe firul enigma2).
def _statProcesor(radacina=""):
	"""Primul rand "cpu" din /proc/stat: (total, liber) in tick-uri, primele 8 campuri, liber = idle + iowait (ca
	HdsProcesor.parseStat); None daca lipseste."""
	text = _citesteText(_cale(radacina, "/proc/stat"), 1024) or ""
	for rand in text.splitlines():
		if rand.startswith("cpu "):
			try:
				valori = [int(x) for x in rand.split()[1:9]]
			except ValueError:
				return None
			if len(valori) < 5:
				return None
			return sum(valori), valori[3] + valori[4]
	return None


def procentOcupat(inainte, acum):
	"""Procentul folosit al procesorului (toate nucleele, o zecimala) intre doua citiri _statProcesor; None fara
	diferenta (prima citire, contorul luat de la capat)."""
	if inainte is None or acum is None or acum[0] <= inainte[0]:
		return None
	total = acum[0] - inainte[0]
	liber = min(total, max(0, acum[1] - inainte[1]))
	return round(100.0 * (total - liber) / total, 1)


class Esantioane(object):
	"""Esantioanele din zi (in memorie, la ESANTION_S): memoria disponibila, incarcarea, procesorul ocupat, temperatura,
	memoria interfetei. Dupa trimitere se iau de la capat."""

	def __init__(self):
		self.memorie = []
		self.incarcare = []
		self.ocupat = []
		self.temperatura = []
		self.rss_max = None

	def adauga(self, memorie_kb=None, incarcare=None, temperatura=None, rss_kb=None, ocupat=None):
		if memorie_kb is not None:
			self.memorie.append(int(memorie_kb))
		if incarcare is not None:
			self.incarcare.append(float(incarcare))
		if temperatura is not None:
			self.temperatura.append(float(temperatura))
		if rss_kb is not None:
			self.rss_max = max(self.rss_max or 0, int(rss_kb))
		if ocupat is not None:
			self.ocupat.append(float(ocupat))
		for lista in (self.memorie, self.incarcare, self.ocupat, self.temperatura):
			del lista[:-200]

	def citeste(self, radacina="", stat_inainte=None):
		"""Un esantion. stat_inainte: citirea _statProcesor de la ticul dinainte (procesorul ocupat de atunci pana acum;
		None = fara procesor in acest esantion). -> citirea _statProcesor de acum."""
		m = _meminfo(radacina)
		t = None
		try:
			from Components import HdsProcesor
			t = HdsProcesor.citesteTemperatura()[0]
		except Exception:
			t = None
		stat = _statProcesor(radacina)
		self.adauga(m.get("MemAvailable"), _incarcare(radacina), t, _rssInterfata(radacina),
			procentOcupat(stat_inainte, stat))
		return stat

	def gol(self):
		return not (self.memorie or self.incarcare or self.ocupat or self.temperatura)


def _medie(lista, zecimale=1):
	return round(sum(lista) / float(len(lista)), zecimale) if lista else None


def dateSistem(es, pornire_s=None, reporniri=None, radacina=""):
	m = _meminfo(radacina)
	nuclee = _nuclee(radacina)
	sus = _sus(radacina)
	incarcari = [round(100.0 * x / nuclee, 1) for x in es.incarcare]
	return {
		"memorie": {"total_kb": m.get("MemTotal"), "disponibila_kb": m.get("MemAvailable"),
			"minima_kb": min(es.memorie) if es.memorie else None,
			"medie_kb": int(_medie(es.memorie, 0)) if es.memorie else None, "interfata_max_kb": es.rss_max},
		"procesor": {"incarcare_medie": _medie(incarcari), "incarcare_max": max(incarcari) if incarcari else None,
			"nuclee": nuclee, "ocupat_medie": _medie(es.ocupat), "ocupat_max": max(es.ocupat) if es.ocupat else None},
		"temperatura": {"medie": _medie(es.temperatura), "max": max(es.temperatura) if es.temperatura else None},
		"pornire_s": None if pornire_s is None else int(pornire_s),
		"reporniri": reporniri,
		"sus_ore": None if sus is None else round(sus / 3600.0, 1),
	}


# ------------------------------------------------------------------ felul „receptor”

def _txt(text, maxim=80):
	return textNume((text or "").replace("\x00", " "), maxim)


def _citesteMic(cale_fisier):
	t = _citesteText(cale_fisier, 4096)
	return None if t is None else t.strip()


def _idHex(text):
	text = (text or "").strip().lower()
	if text.startswith("0x"):
		text = text[2:]
	return text[-4:].rjust(4, "0") if re.match(r"\A[0-9a-f]{1,8}\Z", text) else ""


def _dispozitiv(cale_dispozitiv):
	"""(magistrala, id vvvv:pppp, nume, driver) pentru dispozitivul unei placi de retea (urmand legatura din /sys)."""
	real = os.path.realpath(cale_dispozitiv).replace(os.sep, "/")
	driver = ""
	try:
		driver = os.path.basename(os.path.realpath(os.path.join(cale_dispozitiv, "driver")))
		if not os.path.exists(os.path.join(cale_dispozitiv, "driver")):
			driver = ""
	except OSError:
		driver = ""
	if "/usb" in real:
		d = real
		for _i in range(4):
			v = _citesteMic(os.path.join(d, "idVendor"))
			if v:
				p = _citesteMic(os.path.join(d, "idProduct")) or ""
				return "usb", "%s:%s" % (_idHex(v), _idHex(p)), _txt(_citesteMic(os.path.join(d, "product"))), driver
			d = os.path.dirname(d)
		return "usb", "", "", driver
	if "/mmc" in real:
		v = _citesteMic(os.path.join(cale_dispozitiv, "vendor"))
		p = _citesteMic(os.path.join(cale_dispozitiv, "device"))
		return "sdio", ("%s:%s" % (_idHex(v), _idHex(p))) if v and p else "", "", driver
	if "/pci" in real:
		v = _citesteMic(os.path.join(cale_dispozitiv, "vendor"))
		p = _citesteMic(os.path.join(cale_dispozitiv, "device"))
		return "pci", ("%s:%s" % (_idHex(v), _idHex(p))) if v and p else "", "", driver
	return "platforma", "", "", driver


def _retea(radacina=""):
	rez = []
	baza = _cale(radacina, "/sys/class/net")
	try:
		nume_placi = sorted(os.listdir(baza))
	except OSError:
		nume_placi = []
	for nume in nume_placi:
		if nume == "lo":
			continue
		dispozitiv = os.path.join(baza, nume, "device")
		if not os.path.exists(dispozitiv):
			continue
		fel = "wifi" if (os.path.isdir(os.path.join(baza, nume, "wireless")) or
			os.path.exists(os.path.join(baza, nume, "phy80211"))) else "eth"
		magistrala, ident, produs, driver = _dispozitiv(dispozitiv)
		rez.append({"fel": fel, "magistrala": magistrala, "id": ident, "nume": produs, "driver": _txt(driver, 40)})
	baza = _cale(radacina, "/sys/class/bluetooth")
	try:
		nume_bt = sorted(os.listdir(baza))
	except OSError:
		nume_bt = []
	for nume in nume_bt:
		dispozitiv = os.path.join(baza, nume, "device")
		if ":" in nume or not os.path.exists(dispozitiv):
			continue
		magistrala, ident, produs, driver = _dispozitiv(dispozitiv)
		rez.append({"fel": "bt", "magistrala": magistrala, "id": ident, "nume": produs, "driver": _txt(driver, 40)})
	return rez[:32]


_CLASE_USB = {"08": "stocare", "e0": "bt"}


def _usb(radacina=""):
	rez = []
	baza = _cale(radacina, "/sys/bus/usb/devices")
	try:
		nume_disp = sorted(os.listdir(baza))
	except OSError:
		nume_disp = []
	for nume in nume_disp:
		if nume.startswith("usb") or ":" in nume:
			continue
		d = os.path.join(baza, nume)
		v = _citesteMic(os.path.join(d, "idVendor"))
		if not v:
			continue
		if (_citesteMic(os.path.join(d, "bDeviceClass")) or "") == "09":
			continue
		clasa = "altul"
		try:
			interfete = sorted(x for x in os.listdir(d) if x.startswith(nume + ":"))
		except OSError:
			interfete = []
		for intf in interfete:
			ci = (_citesteMic(os.path.join(d, intf, "bInterfaceClass")) or "").lower()
			pr = (_citesteMic(os.path.join(d, intf, "bInterfaceProtocol")) or "").lower()
			if os.path.isdir(os.path.join(d, intf, "net")):
				clasa = "wifi"
				break
			if ci == "03":
				clasa = "tastatura" if pr == "01" else ("mouse" if pr == "02" else "altul")
				break
			if ci in _CLASE_USB:
				clasa = _CLASE_USB[ci]
				break
		produs = _txt(_citesteMic(os.path.join(d, "product")))
		if clasa == "altul" and "dvb" in produs.lower():
			clasa = "tuner"
		rez.append({"clasa": clasa, "id": "%s:%s" % (_idHex(v), _idHex(_citesteMic(os.path.join(d, "idProduct")))),
			"nume": produs})
	return rez[:32]


def _tunere(radacina=""):
	rez = []
	slot = None
	for rand in (_citesteText(_cale(radacina, "/proc/bus/nim_sockets"), 16384) or "").splitlines():
		rand = rand.strip()
		m = re.match(r"NIM Socket (\d+):", rand)
		if m:
			slot = {"slot": int(m.group(1)), "fel": "", "nume": "", "moduri": []}
			rez.append(slot)
		elif slot is not None and rand.startswith("Type:"):
			slot["fel"] = _txt(rand[5:], 40)
		elif slot is not None and rand.startswith("Name:"):
			slot["nume"] = _txt(rand[5:], 80)
		elif slot is not None and re.match(r"Mode \d+:", rand) and len(slot["moduri"]) < 8:
			# tunerele cu mai multe feluri (de pilda DVB-T2/C): fiecare mod, cum il spune driverul
			slot["moduri"].append(_txt(rand.split(":", 1)[1], 40))
	for slot in rez:
		if not slot["moduri"]:
			del slot["moduri"]
	return rez[:16]


def _partitii(radacina=""):
	"""(emmc_kib, partitiile discului intern) din /proc/partitions."""
	emmc = None
	lista = []
	for rand in (_citesteText(_cale(radacina, "/proc/partitions"), 16384) or "").splitlines():
		p = rand.split()
		if len(p) != 4 or not p[2].isdigit():
			continue
		nume = p[3]
		if nume == "mmcblk0":
			emmc = int(p[2])
		elif re.match(r"\Ammcblk0p\d+\Z", nume) or re.match(r"\Amtdblock\d+\Z", nume):
			lista.append({"nume": nume, "kib": int(p[2])})
	return emmc, lista[:40]


def _nand(radacina=""):
	total = 0
	for rand in (_citesteText(_cale(radacina, "/proc/mtd"), 16384) or "").splitlines()[1:]:
		p = rand.split()
		if len(p) >= 2:
			try:
				total += int(p[1], 16)
			except ValueError:
				pass
	return total // 1024


def _procesor(radacina=""):
	text = _citesteText(_cale(radacina, "/proc/cpuinfo"), 32768) or ""
	for cheie in ("model name", "Hardware", "system type", "cpu model", "Processor"):
		m = re.search(r"(?mi)^" + re.escape(cheie) + r"\s*:\s*(.+)$", text)
		if m:
			return _txt(m.group(1))
	return ""


def _hdmi(radacina=""):
	moduri = (_citesteMic(_cale(radacina, "/proc/stb/video/videomode_choices")) or "").split()
	hdr = (_citesteMic(_cale(radacina, "/proc/stb/video/hdmi_hdrtype_choices")) or "").split()
	cec = any(os.path.exists(_cale(radacina, c)) for c in ("/dev/hdmi_cec", "/dev/cec0"))
	return {"moduri": [_txt(x, 20) for x in moduri[:32]], "hdr": [_txt(x, 20) for x in hdr[:16]], "cec": cec}


def _afisaj(radacina=""):
	try:
		nume = sorted(os.listdir(_cale(radacina, "/dev/dbox")))
	except OSError:
		return ""
	return _txt(",".join(x for x in nume if x.startswith(("oled", "lcd", "vfd", "fp"))), 80)


def _drivere(radacina=""):
	rez = []
	baza = _cale(radacina, "/var/lib/opkg/info")
	try:
		nume = sorted(x for x in os.listdir(baza) if x.endswith(".control"))
	except OSError:
		nume = []
	for n in nume:
		pachet = n[:-len(".control")]
		if not re.search(r"-dvb-modules-|-libs-|-platform-util-|-hihalt|-showiframe|-dvb-", pachet):
			continue
		text = _citesteText(os.path.join(baza, n), 8192) or ""
		m = re.search(r"(?m)^Version:\s*(\S+)", text)
		rez.append({"pachet": _txt(pachet, 80), "versiune": _txt(m.group(1) if m else "", 80)})
		if len(rez) >= 32:
			break
	return rez


def pacheteNeconfigurate(radacina=""):
	"""Numele pachetelor ramase „unpacked” / „half-configured” / „half-installed” in starea opkg (o extensie straina
	care strica o actualizare), fara cele despre accesul conditionat."""
	text = _citesteText(_cale(radacina, "/var/lib/opkg/status"), 4 * 1024 * 1024) or ""
	rez = []
	for bloc in re.split(r"\n\s*\n", text.replace("\r", "")):
		m = re.search(r"(?m)^Package:\s*(\S+)", bloc)
		s = re.search(r"(?m)^Status:\s*(.+)$", bloc)
		if not m or not s:
			continue
		if re.search(r"\b(?:unpacked|half-configured|half-installed)\b", s.group(1)) and not esteDeAcces(m.group(1)):
			rez.append(_txt(m.group(1), 80))
		if len(rez) >= 32:
			break
	return rez


# TODO 1389 (Eduard 30.10.2026 11:40): „să vedem ca betatester și modulele instalate și ce merge și nu merge”. Lista
# modulelor de acces instalate pleaca in felul „receptor” numai cu nota NOTA_MODULE acceptata (nota 2 spunea „lista
# pachetelor instalate nu pleaca”). Pentru fiecare modul: felul si sufixul scriptului, pachetul, versiunea, feedul din
# care se poate lua aceeasi versiune, daca e ales si daca ruleaza. Fara fisiere de configurare, chei, servere sau
# cititoare: numai ce scrie opkg si ce se vede in /proc (HdsModuleAcces.citeste). Forma: o lista de texte
# „fel.sufix|pachet|versiune|feed|ales|pornit” (ales, pornit = 1 sau 0), fiindca serverul pastreaza fara schimbare
# numai listele de valori simple (Pachete::campuriNoi; o lista de obiecte s-ar pierde pe tacute). Numele modulelor le
# da receptorul la rulare; aici nu e scris niciunul.
NOTA_MODULE = 3
MODULE_MAX = 32
LISTA_FEED_MAX = 16 * 1024 * 1024
_NUME_FEED = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._+-]{0,47}\Z")


def _campModul(text, maxim=60):
	return _txt(text, maxim).replace("|", "/")


def _versiunePachet(sistem, info_dir, pachet):
	try:
		text = sistem.citeste(info_dir.rstrip("/") + "/" + pachet + ".control", 8192)
	except (OSError, IOError):
		return ""
	m = re.search(r"(?m)^Version:\s*(\S+)", text or "")
	return m.group(1) if m else ""


def _feedPachete(sistem, conf, cautate):
	"""{pachet: numele feedului} pentru pachetele `cautate` = {pachet: versiune}: primul feed (in ordinea din
	configurarea opkg) a carui lista descarcata are pachetul cu aceeasi versiune. Un nume de feed ciudat devine „alt”."""
	rez = {}
	for nume in conf.nume_surse():
		if len(rez) >= len(cautate):
			break
		try:
			text = sistem.citeste(conf.lists_dir.rstrip("/") + "/" + nume, LISTA_FEED_MAX)
		except (OSError, IOError):
			continue
		for pachet, versiune in cautate.items():
			if pachet in rez or not versiune:
				continue
			poz = text.find("Package: %s\n" % pachet)
			while poz >= 0:
				if poz == 0 or text[poz - 1] == "\n":
					sfarsit = text.find("\n\n", poz)
					strofa = text[poz:sfarsit if sfarsit >= 0 else len(text)]
					if re.search(r"(?m)^Version:\s*%s\s*$" % re.escape(versiune), strofa):
						rez[pachet] = nume if _NUME_FEED.match(nume) else "alt"
						break
				poz = text.find("Package: %s\n" % pachet, poz + 1)
	return rez


def moduleAcces(radacina="", sistem=None):
	"""Lista modulelor de acces instalate (TODO 1389), ca texte „fel.sufix|pachet|versiune|feed|ales|pornit”; cel mult
	MODULE_MAX. Intai scripturile modulelor (cu pachetul lor, daca au), apoi pachetele de module fara script. Nu
	arunca: la orice eroare, lista goala."""
	try:
		try:
			from Components import HdsInterfeteCam as C, HdsModuleAcces as M
			from Components.HdsPachete import Configurare, citeste_configurarea
		except ImportError:
			import HdsInterfeteCam as C
			import HdsModuleAcces as M
			from HdsPachete import Configurare, citeste_configurarea
		if sistem is None:
			sistem = M.SistemAcces(radacina=radacina or "/")
		try:
			conf = citeste_configurarea(sistem.radacina)
		except Exception:
			conf = Configurare()
		feluri_ = M.feluri(sistem)
		opkg = C.citeste_opkg(sistem, set(), feluri_)
		pachetScript = {}
		for pachet, scripturi in opkg.scripturi.items():
			for s in scripturi:
				pachetScript.setdefault(s, pachet)
		randuri = []
		folosite = set()
		for fel in feluri_:
			st = M.citeste(sistem, fel)
			for e in st.emulatoare:
				pachet = pachetScript.get(e.script, "")
				folosite.add(pachet)
				randuri.append([e.script, pachet, e.ales, bool(e.pids)])
		for pachet in sorted(opkg.pachete_cam):
			if pachet not in folosite:
				randuri.append(["", pachet, False, False])
		randuri = randuri[:MODULE_MAX]
		versiuni = dict((p, _versiunePachet(sistem, conf.info_dir, p)) for _s, p, _a, _r in randuri if p)
		feeduri = _feedPachete(sistem, conf, versiuni) if versiuni else {}
		return ["|".join((_campModul(script, 70), _campModul(pachet, 80), _campModul(versiuni.get(pachet, "")),
			_campModul(feeduri.get(pachet, ""), 48), "1" if ales else "0", "1" if ruleaza else "0"))
			for script, pachet, ales, ruleaza in randuri]
	except Exception as e:
		_jurnal("lista modulelor: %s" % e)
		return []


def dateReceptor(model="", paza=None, radacina="", cu_module=False):
	"""Datele receptorului (felul „receptor”): fara serii, fara MAC, fara numele retelei, fara IP. `cu_module`: si lista
	modulelor de acces (numai cu nota NOTA_MODULE acceptata)."""
	paza = paza or {}
	emmc, partitii = _partitii(radacina)
	dt = ""
	try:
		with open(_cale(radacina, "/proc/device-tree/compatible"), "rb") as f:
			dt = _txt(",".join(x.decode("ascii", "replace") for x in f.read(512).split(b"\0") if x))
	except (OSError, IOError):
		dt = ""
	# versiunea placii data de driver (pe SF8008 „1.2V-20240104103144” la placa din 2024): numai primul rand, fara serie
	versiune_placa = _txt((_citesteMic(_cale(radacina, "/proc/stb/info/version")) or "").strip().split("\n")[0], 60)
	d = {
		"placa": {"machinebuild": model, "cip": paza.get("cip", ""), "boxtype": paza.get("boxtype", ""), "dt": dt,
			"procesor": _procesor(radacina), "nuclee": _nuclee(radacina), "versiune_placa": versiune_placa},
		"memorie": {"ram_kb": _meminfo(radacina).get("MemTotal"), "emmc_kib": emmc, "nand_kib": _nand(radacina),
			"partitii": partitii},
		"tunere": _tunere(radacina),
		"retea": _retea(radacina),
		"hdmi": _hdmi(radacina),
		"afisaj": _afisaj(radacina),
		"telecomanda": _txt(_citesteMic(_cale(radacina, "/proc/stb/ir/rc/type")) or "", 40),
		"drivere": _drivere(radacina),
		"usb": _usb(radacina),
		"pachete_neconfigurate": pacheteNeconfigurate(radacina),
	}
	if cu_module:
		d["module"] = moduleAcces(radacina)
	return d


def sumaDate(date):
	return hashlib.sha256(json.dumps(date, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ felul „probe”

def culegeProbe(stare, cale_probe=None):
	"""Rezultatul ultimei rulari a probelor, numai cand s-a schimbat (suma fisierului)."""
	cale_probe = cale_probe or CALE_PROBE
	try:
		if os.path.islink(cale_probe) or os.path.getsize(cale_probe) > PROBE_MAX:
			return None
		with open(cale_probe, "rb") as f:
			octeti = f.read(PROBE_MAX + 1)
	except (OSError, IOError):
		return None
	suma = hashlib.sha256(octeti).hexdigest()
	if suma == stare.get("probe_suma"):
		return None
	try:
		obiect = json.loads(octeti.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	if not isinstance(obiect, dict):
		return None
	stare["probe_suma"] = suma
	return {"probe": obiect}


def trimiteProbe(rezultate, b=None):
	"""Din modulul probelor („Trimite rezultatele”): pachetul `probe` in coada, numai pentru un tester inscris, cu
	felul bifat. -> (reusit, mesaj)"""
	b = _b(b)
	if not inscris(b):
		return False, _t("Nu ești înscris în programul de beta testeri.")
	if not b.probe.value:
		return False, _t("Felul „Rezultatele probelor” e debifat în „Datele pe care le trimit”.")
	if not isinstance(rezultate, dict):
		return False, _t("Rezultatele probelor nu au forma bună.")
	model, paza = _modelTinut()
	inst = instantaneu(b, contor(), model, paza, versiuneImagine(), limba())
	corp = antet(inst, "probe")
	corp["date"] = {"probe": rezultate}
	if len(json.dumps(rezultate, ensure_ascii=False).encode("utf-8")) > PROBE_MAX or \
			not puneInCoada("date", "probe", corp):
		return False, _t("Rezultatele probelor sunt prea mari.")
	_ceruteAcum["trimite"] = True
	return True, _t("Rezultatele probelor au intrat în coadă și pleacă îndată ce receptorul are internet.")


# ------------------------------------------------------------------ modelul si antetul pachetelor

def modelSiPaza(radacina=None):
	"""(model, paza) din paza modelului: modelul numai cu verdictul „potrivit” (machinebuild din reguli)."""
	try:
		from Components import HdsPazaModel as P
	except ImportError:
		try:
			import HdsPazaModel as P
		except ImportError:
			return "", {"stare": "", "treapta": 0, "cip": "", "boxtype": "", "emmc_gb": None}
	try:
		v = P.verdict(radacina)
	except Exception as e:
		_jurnal("paza modelului: %s" % e)
		return "", {"stare": "", "treapta": 0, "cip": "", "boxtype": "", "emmc_gb": None}
	a = v.get("amprenta_verdict") or v.get("amprenta") or {}
	try:
		emmc_gb = int(round(int(a.get("emmc_kib") or 0) / 1048576.0)) or None
	except (TypeError, ValueError):
		emmc_gb = None
	paza = {"stare": v.get("stare", ""), "treapta": int(v.get("treapta") or 0), "cip": a.get("cip", "") or "",
		"boxtype": a.get("boxtype", "") or "", "emmc_gb": emmc_gb}
	model = ""
	if v.get("stare") == "potrivit" and v.get("reguli"):
		model = (v["reguli"].get("machinebuild") or "").strip()
		if not re.match(r"\A[a-z0-9_]{1,40}\Z", model):
			model = ""
		else:
			_starea["nume_model"] = textNume(v["reguli"].get("model") or "", 60)
	return model, paza


def versiuneImagine(radacina=None):
	try:
		from Components import HdsPazaModel as P
		return (P.versiuneAcum(radacina) or "")[:40]
	except Exception:
		return ""


def antet(instantaneu, fel=None):
	"""Campurile comune ale pachetelor `date`: {v, id, nota, fel, model, paza, versiune, limba, ore, cules}."""
	a = {"v": PROTOCOL, "id": instantaneu["id"], "nota": instantaneu["nota"], "model": instantaneu["model"],
		"paza": instantaneu["paza"], "versiune": instantaneu["versiune"], "limba": instantaneu["limba"],
		"ore": instantaneu["ore"], "cules": oraUtc()}
	if fel:
		a["fel"] = fel
	return a


def corpAcord(instantaneu):
	return {"v": PROTOCOL, "id": instantaneu["id"], "nota": instantaneu["nota"], "acord": instantaneu["acord"] or None,
		"feluri": dict(instantaneu["bife"]), "model": instantaneu["model"], "paza": instantaneu["paza"],
		"versiune": instantaneu["versiune"], "limba": instantaneu["limba"], "ore": instantaneu["ore"],
		"nume": instantaneu["nume"], "email": instantaneu["email"]}


def instantaneu(b, contor, model="", paza=None, versiune="", limba=""):
	"""Ce trebuie firului de lucru din setari, citit pe firul enigma2."""
	return {"id": b.id.value, "nota": int(b.nota.value), "acord": b.acord.value, "bife": bife(b),
		"nume": b.nume.value, "email": b.email.value, "model": model, "paza": paza or {}, "versiune": versiune,
		"limba": limba, "ore": contor.ore(), "server": adresaServer(b), "inscris": inscris(b)}


# ------------------------------------------------------------------ coada, „Ce am trimis”, „Ce trimit acum”

_LACAT = threading.RLock()
_RETEA = threading.RLock()
_GENERATIE = 0
_STERGERE = None
_STERGERE_DOSAR = None
_NOTA_LOCALA = 0
_REVIZIE_ACORD = 0
_ACORD_TRIMIS = {}
# Immutable display snapshot, replaced under the disk lock but read without it.
_ULTIMA_TRIMITERE = (None, None, None)


def cerereActuala(cerere):
	"""Un rezultat dinaintea stergerii nu mai poate reface datele, nici dupa reinscrierea cu acelasi id."""
	return (getattr(cerere, "generatie", _GENERATIE) == _GENERATIE and
		getattr(cerere, "revizie", _REVIZIE_ACORD) == _REVIZIE_ACORD)


def _semnaturaAcord(corp):
	"""Only consent fields, so viewing a profile never renews an unchanged consent."""
	return sumaDate({k: corp.get(k) for k in ("id", "nota", "acord", "feluri", "nume", "email")})


def dosarCoada():
	return cale("coada")


def citesteStare():
	with _LACAT:
		generatie = _GENERATIE
		stare = citesteJson(cale("stare.json"), {}) or {}
		if not isinstance(stare, dict):
			stare = {}
		_tineUltimaTrimitere(stare, generatie)
		return stare


def _tineUltimaTrimitere(stare, generatie):
	"""Publish only a scalar, never the mutable state dictionary or config objects."""
	global _ULTIMA_TRIMITERE
	secunde = stare.get("ultima_trimitere")
	if not isinstance(secunde, (int, float)):
		secunde = None
	elif secunde:
		try:
			time.localtime(secunde)
		except (ValueError, OverflowError, OSError):
			secunde = None
	if cerereActuala(threading.current_thread()):
		_ULTIMA_TRIMITERE = (DOSAR, generatie, secunde)


def scrieStare(stare):
	with _LACAT:
		if not cerereActuala(threading.current_thread()):
			return
		generatie = _GENERATIE
		try:
			scrieJson(cale("stare.json"), stare)
			_tineUltimaTrimitere(stare, generatie)
		except (OSError, IOError) as e:
			_jurnal("starea: %s" % e)


def schimbaStare(functie):
	"""Citeste starea, o schimba cu `functie(stare)` si o scrie, totul sub lacat (doua fire o pot schimba)."""
	with _LACAT:
		stare = citesteStare()
		functie(stare)
		scrieStare(stare)
		return stare


def comprima(corp):
	brut = json.dumps(corp, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
	b = io.BytesIO()
	with gzip.GzipFile(fileobj=b, mode="wb", mtime=0) as g:
		g.write(brut)
	return brut, b.getvalue()


def _fisiereCoada(strict=False):
	try:
		return sorted(x for x in os.listdir(dosarCoada()) if _pachetPropriu(x))
	except FileNotFoundError:
		return []
	except OSError:
		if strict:
			raise
		return []


def _pachetPropriu(nume):
	"""Ignore unrelated files, including archives left by a person in this folder."""
	return re.fullmatch(r"[0-9]{13}(?:[0-9a-f]{16})?-(?:acord-acord|iesire-iesire|sterge-sterge|mesaj-mesaj|"
		r"date-(?:jurnale|canale|sistem|utilizare|receptor|probe))\.gz", nume) is not None


def puneInCoada(ruta, fel, corp, limita=PACHET_MAX, marcaj=None):
	"""Pachetul in coada: `ruta` = acord, date, mesaj, sterge. Peste limita pachetului nu intra (rand in jurnal);
	peste COADA_MAX sau COADA_OCTETI pleaca intai cele mai vechi (nu si stergerea). -> numele fisierului sau None."""
	brut, gz = comprima(cuAmprenta(corp))
	if len(gz) > limita:
		_jurnal("pachetul %s are %d octeti comprimat, peste %d: nu pleaca" % (fel, len(gz), limita))
		adaugaTrimis(fel, len(gz), "refuzat")
		return None
	with _LACAT:
		if not cerereActuala(threading.current_thread()):
			return None
		_asiguraDosar(dosarCoada())
		prefix = "%013d" % int(time.time() * 1000)
		if ruta == "sterge":
			prefix += marcaj or os.urandom(8).hex()
		nume = "%s-%s-%s.gz" % (prefix, ruta, fel)
		scrieAtomic(os.path.join(dosarCoada(), nume), gz)
		_taieCoada()
		adaugaTrimis(fel, len(gz), "coada", nume)
	return nume


def _taieCoada():
	fisiere = _fisiereCoada()
	marimi = {}
	for f in fisiere:
		try:
			marimi[f] = os.path.getsize(os.path.join(dosarCoada(), f))
		except OSError:
			marimi[f] = 0
	pastrate = list(fisiere)
	while pastrate and (len(pastrate) > COADA_MAX or sum(marimi[f] for f in pastrate) > COADA_OCTETI):
		vechi = next((f for f in pastrate if "-sterge-" not in f), None)
		if vechi is None:
			break
		pastrate.remove(vechi)
		_sterge(os.path.join(dosarCoada(), vechi))
		schimbaTrimis(vechi, "pierdut")
		_jurnal("coada plina: %s pierdut" % vechi)


def golesteCoada(pastreaza_stergerea=False, strict=False):
	with _LACAT:
		if strict:
			try:
				fisiere = sorted(x for x in os.listdir(dosarCoada()) if _pachetPropriu(x))
			except FileNotFoundError:
				fisiere = []
		else:
			fisiere = _fisiereCoada()
		for f in fisiere:
			if pastreaza_stergerea and "-sterge-" in f:
				continue
			if strict:
				try:
					os.remove(os.path.join(dosarCoada(), f))
				except FileNotFoundError:
					pass
			else:
				_sterge(os.path.join(dosarCoada(), f))


def coadaGoala():
	return not _fisiereCoada()


def citesteTrimise():
	lista = citesteJson(cale("trimise.json"), []) or []
	return [x for x in lista if isinstance(x, dict)][:TRIMISE_MAX]


def adaugaTrimis(fel, marime, stare, fisier=""):
	with _LACAT:
		lista = citesteTrimise()
		lista.insert(0, {"cand": oraUtc(), "fel": fel, "marime": int(marime), "stare": stare, "fisier": fisier})
		try:
			scrieJson(cale("trimise.json"), lista[:TRIMISE_MAX])
		except (OSError, IOError) as e:
			_jurnal("lista trimiterilor: %s" % e)


def schimbaTrimis(fisier, stare, extra=None):
	with _LACAT:
		lista = citesteTrimise()
		for x in lista:
			if x.get("fisier") == fisier:
				x["stare"] = stare
				x["cand"] = oraUtc()
				if extra:
					x.update(extra)
				break
		try:
			scrieJson(cale("trimise.json"), lista)
		except (OSError, IOError) as e:
			_jurnal("lista trimiterilor: %s" % e)


def oraLocala(text):
	"""„AAAA-LL-ZZTHH:MMZ” (UTC) -> „AAAA-LL-ZZ HH:MM” in ora receptorului; altfel textul ca atare."""
	try:
		import calendar
		return time.strftime("%Y-%m-%d %H:%M", time.localtime(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%MZ"))))
	except (ValueError, OverflowError, TypeError):
		return text or ""


def ultimulPachet():
	"""Octetii desfacuti ai ultimului pachet plecat (ca text JSON frumos), sau None."""
	try:
		with open(cale("ultimul.json"), "rb") as f:
			brut = f.read(8 * 1024 * 1024)
		return json.dumps(json.loads(brut.decode("utf-8")), ensure_ascii=False, indent=1, sort_keys=False)
	except (OSError, IOError, ValueError):
		return None


def randuriTrimise(lista=None):
	"""Randurile „Ce am trimis”: (data locala, felul, marimea, starea), cel mai nou sus."""
	rez = []
	for x in (citesteTrimise() if lista is None else lista):
		cand = oraLocala(x.get("cand", ""))
		rez.append((cand, numeFelPachet(x.get("fel", "")), "%.1f KB" % (int(x.get("marime", 0)) / 1024.0),
			_t(STARI_TRIMISE.get(x.get("stare"), x.get("stare", "")))))
	return rez


# ------------------------------------------------------------------ trimiterea

def _posteazaHttp(url, gz, timp=TIMP_CERERE_S):
	"""POST JSON comprimat; certificatul se verifica (contextul implicit). -> (cod HTTP, octetii raspunsului)."""
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError
	cerere = Request(url, data=gz, method="POST", headers={"Content-Type": "application/json",
		"Content-Encoding": "gzip", "User-Agent": "hdsatelit-receptor/1", "Accept": "application/json"})
	try:
		r = urlopen(cerere, timeout=timp)
		try:
			return r.getcode(), r.read(1024 * 1024)
		finally:
			r.close()
	except HTTPError as e:
		try:
			corp = e.read(65536)
		except Exception:
			corp = b""
		return e.code, corp


def _json(octeti):
	try:
		o = json.loads(octeti.decode("utf-8"))
		return o if isinstance(o, dict) else {}
	except (ValueError, UnicodeDecodeError, AttributeError):
		return {}


# ce face un raspuns: trimis, lasat (refuzat, nu se mai trimite), mai tarziu (ramane in coada)
TRIMIS, LASAT, MAI_TARZIU = "trimis", "lasat", "mai-tarziu"


def hotarareRaspuns(cod, raspuns):
	"""(ce, motiv) dupa codul HTTP: 429 si 5xx si o ruta inca necunoscuta (serverul nepus) = mai tarziu; 413, 400,
	415, 403 fel_oprit = lasat; 409 nota_veche = lasat si oprit; 403 fara_acord = lasat, cu acordul retrimis.
	Raspunsurile 413/429 date de nginx sunt HTML: nu se citeste `eroare` la ele."""
	if 200 <= cod < 300:
		return TRIMIS, ""
	if cod == 429 or cod >= 500 or cod in (404, 405, 408):
		return MAI_TARZIU, str(cod)
	if cod == 413:
		return LASAT, "mare"
	eroare = _json(raspuns).get("eroare", "") if cod in (400, 403, 409, 415) else ""
	if cod == 409:
		return LASAT, eroare or "nota_veche"
	if cod == 403:
		return LASAT, eroare or "fara_acord"
	return LASAT, eroare or str(cod)


class Trimitere(object):
	"""Trimite coada, cel mai vechi intai (stergerea inaintea tuturor). Ruleaza pe firul Lucru."""

	def __init__(self, server, posteaza=None):
		self.generatie = _GENERATIE
		self.server = server
		self.posteaza = posteaza or _posteazaHttp
		self.rezultate = []

	def trimite(self):
		with _RETEA:
			return self._trimite()

	def _trimite(self):
		"""-> (cate au plecat, oprit_pana_mai_tarziu)."""
		fisiere = _fisiereCoada(strict=True)
		fisiere.sort(key=lambda f: (0 if "-sterge-" in f else 1, f))
		plecate = 0
		for f in fisiere:
			if not cerereActuala(self):
				return plecate, False
			parti = f[:-3].split("-", 2)
			if len(parti) != 3:
				_sterge(os.path.join(dosarCoada(), f))
				continue
			ruta, fel = parti[1], parti[2]
			cale_fisier = os.path.join(dosarCoada(), f)
			try:
				with open(cale_fisier, "rb") as fi:
					gz = fi.read(PACHET_MAX + 1)
			except (OSError, IOError):
				if ruta == "sterge":
					return plecate, True
				continue
			try:
				confirmata = False
				if ruta == "sterge":
					confirmare = {"fisier": f, "suma": hashlib.sha256(gz).hexdigest()}
					try:
						with open(cale("stergere-confirmata.json"), "r", encoding="utf-8") as fi:
							confirmata = json.load(fi) == confirmare
					except FileNotFoundError:
						pass
				if confirmata:
					cod, raspuns = 200, b'{}'
				else:
					cod, raspuns = self.posteaza(self.server + ruta, gz)
			except Exception as e:
				_jurnal("trimiterea %s: %s" % (f, _mesajEroare(e)))
				return plecate, True
			with _LACAT:
				if not cerereActuala(self):
					return plecate, False
				ce, motiv = hotarareRaspuns(cod, raspuns)
				if ruta == "sterge" and ce != TRIMIS:
					return plecate, True
				if ruta == "sterge":
					_ACORD_TRIMIS.clear()
				if ce == MAI_TARZIU:
					_jurnal("serverul a raspuns %s la %s: incerc mai tarziu" % (cod, f))
					return plecate, True
				if ruta == "sterge":
					try:
						# A durable acknowledgement also covers a stale queue entry after a crash.
						scrieJson(cale("stergere-confirmata.json"), confirmare)
						_syncDosar(DOSAR)
						os.remove(cale_fisier)
						_syncDosar(dosarCoada())
					except OSError:
						return plecate, True
				else:
					_sterge(cale_fisier)
				if ce == TRIMIS:
					plecate += 1
					if ruta in ("sterge", "iesire"):
						_ACORD_TRIMIS.clear()
					schimbaTrimis(f, "trimis")
					if ruta == "date":
						schimbaStare(lambda s: s.__setitem__("ultima_trimitere", int(time.time())))
					if ruta != "sterge":
						try:
							scrieAtomic(cale("ultimul.json"), gzip.decompress(gz))
						except (OSError, IOError, EOFError) as e:
							_jurnal("ultimul pachet: %s" % e)
					o = _json(raspuns)
					if ruta == "acord" and int(o.get("nota_minima") or 0) > NOTA:
						self.rezultate.append(("nota_veche", ""))
					if ruta == "acord":
						if int(o.get("nota_minima") or 0) <= NOTA:
							corp = _json(gzip.decompress(gz))
							_ACORD_TRIMIS[(self.server, corp.get("id"))] = _semnaturaAcord(corp)
						self.rezultate.append(("acord_trimis", ""))
					if ruta == "mesaj" and o.get("mesaj"):
						self.rezultate.append(("mesaj", o.get("mesaj")))
				else:
					schimbaTrimis(f, "refuzat", {"motiv": motiv})
					_jurnal("serverul a refuzat %s: %s" % (f, motiv))
					if motiv == "nota_veche":
						self.rezultate.append(("nota_veche", ""))
						golesteCoadaAfaraDe("sterge")
						return plecate, False
					if motiv == "fara_acord" and ruta != "acord":
						self.rezultate.append(("fara_acord", ""))
		return plecate, False


def golesteCoadaAfaraDe(ruta_pastrata):
	with _LACAT:
		for f in _fisiereCoada():
			if "-%s-" % ruta_pastrata not in f:
				_sterge(os.path.join(dosarCoada(), f))
				schimbaTrimis(f, "refuzat", {"motiv": "nota_veche"})


def _mesajEroare(e):
	try:
		from Components import HdsCeasHttps
		text = HdsCeasHttps.mesaj(e)
		if text:
			return text
	except Exception:
		pass
	return "%s: %s" % (type(e).__name__, e)


# ------------------------------------------------------------------ culegerea pe fir

def culegeSiPune(inst, sarcini, stare, es=None, utilizare=None, pornire_s=None, reporniri=None, radacina="",
		dosar_logs=None, cale_lamedb=None, cale_paznic=None, acum=None, cale_probe=None, cerut=False):
	"""Pachetele datorate, puse in coada. `sarcini` = felurile de cules acum. -> felurile puse in coada."""
	acum = time.time() if acum is None else acum
	puse = []
	ultim = stare.setdefault("ultim", {})
	bife_ = inst["bife"]
	for fel in sarcini:
		if not bife_.get(fel):
			continue
		date = None
		try:
			if fel == "jurnale":
				date = culegeJurnale(stare, dosar_logs, cale_paznic, acum)
			elif fel == "canale":
				date = culegeCanale(stare, cale_lamedb, acum, cerut)
			elif fel == "sistem":
				if es is not None and not es.gol():
					date = dateSistem(es, pornire_s, reporniri, radacina)
			elif fel == "utilizare":
				if utilizare and (utilizare.get("ecrane") or utilizare.get("zapuri") or utilizare.get("inregistrari")):
					date = utilizare
			elif fel == "receptor":
				d = dateReceptor(inst["model"], inst["paza"], radacina,
					cu_module=int(inst.get("nota") or 0) >= NOTA_MODULE)
				suma = sumaDate(d)
				if suma != stare.get("receptor_suma"):
					date = d
					stare["receptor_suma"] = suma
			elif fel == "probe":
				date = culegeProbe(stare, cale_probe)
		except Exception as e:
			_jurnal("culegerea %s: %s" % (fel, e))
			date = None
		if date is None:
			continue
		corp = antet(inst, fel)
		corp["date"] = date
		if puneInCoada("date", fel, corp):
			puse.append(fel)
			ultim[fel] = int(acum)
	return puse


class Lucru(threading.Thread):
	"""Firul care culege, pune in coada si trimite; rezultatele raman in .rezultate, culese de tic()."""

	def __init__(self, inst, sarcini=(), trimite=True, es=None, utilizare=None, pornire_s=None, reporniri=None,
			acord=False, posteaza=None, auto_zilnic=False):
		threading.Thread.__init__(self, name="hds-beta")
		self.generatie = _GENERATIE
		self.daemon = True
		self.inst = inst
		self.sarcini = tuple(sarcini)
		self.trimite_ = trimite
		self.es = es
		self.utilizare_ = utilizare
		self.pornire_s = pornire_s
		self.reporniri = reporniri
		self.acord = acord
		self.posteaza = posteaza
		self.auto_zilnic = auto_zilnic
		self.rezultate = []
		self.puse = []
		self.mai_tarziu = False
		self.plecate = 0

	def run(self):
		try:
			if not cerereActuala(self):
				return
			inst = self.inst
			if not inst.get("model") and not inst.get("paza"):
				inst["model"], inst["paza"] = modelSiPaza()
				self.rezultate.append(("model", (inst["model"], inst["paza"])))
			if self.acord and inst.get("inscris"):
				puneInCoada("acord", "acord", corpAcord(inst))
			if self.sarcini and inst.get("inscris"):
				stare = citesteStare()
				self.puse = culegeSiPune(inst, self.sarcini, stare, self.es, self.utilizare_, self.pornire_s,
					self.reporniri, cerut=not self.auto_zilnic and len(self.sarcini) > 1)
				chei = ("jurnale", "jurnale_zi", "jurnale_azi", "caderi_azi", "paznic", "canale_semn", "receptor_suma",
					"probe_suma", "ultim")
				auto = self.auto_zilnic

				def uneste(s):
					for cheie in chei:
						if cheie in stare:
							s[cheie] = stare[cheie]
					if auto:
						s["ultim_auto"] = int(time.time())
				schimbaStare(uneste)
			if self.trimite_ and cerereActuala(self) and not coadaGoala():
				t = Trimitere(inst["server"], self.posteaza)
				t.generatie = self.generatie
				self.plecate, self.mai_tarziu = t.trimite()
				self.rezultate.extend(t.rezultate)
		except Exception as e:
			_jurnal("firul de lucru: %s" % e)


class Cerere(threading.Thread):
	"""O cerere directa la server (raspunsuri, profil, legare), fara coada: .gata, .cod, .raspuns (dict)."""

	def __init__(self, server, ruta, corp, posteaza=None):
		threading.Thread.__init__(self, name="hds-beta-cerere")
		self.generatie = _GENERATIE
		self.daemon = True
		self.url = server + ruta
		self.corp = corp
		self.posteaza = posteaza or _posteazaHttp
		self.gata = False
		self.cod = 0
		self.raspuns = {}
		self.eroare = ""
		self.eroare_profil = ""

	def run(self):
		try:
			with _RETEA:
				if not cerereActuala(self):
					return
				acord = getattr(self, "acord", None)
				if acord is not None:
					self.server = _adresaServer(self.server)
					self.url = self.server + self.ruta
					# Keep deletion, consent and profile on the same serialized network lane.
					t = Trimitere(self.server, self.posteaza)
					t.generatie = self.generatie
					_, amanat = t.trimite()
					if amanat or any("-sterge-" in f for f in _fisiereCoada(strict=True)):
						raise OSError("Stergerea datelor asteapta confirmarea serverului")
					if not cerereActuala(self):
						return
					if not acord["model"] and not acord["paza"]:
						acord["model"], acord["paza"] = modelSiPaza()
					acord["versiune"] = versiuneImagine()
					semnatura = _semnaturaAcord(acord)
					if _ACORD_TRIMIS.get((self.server, acord["id"])) != semnatura:
						_, gz = comprima(cuAmprenta(acord))
						cod, octeti = self.posteaza(self.server + "acord", gz)
						if not 200 <= cod < 300 or int(_json(octeti).get("nota_minima") or 0) > NOTA:
							raise OSError("Acordul asteapta confirmarea serverului")
						_ACORD_TRIMIS[(self.server, acord["id"])] = semnatura
					with _LACAT:
						if not cerereActuala(self):
							return
						try:
							cheie = cheieProfil()
						except (OSError, UnicodeError):
							self.eroare_profil = "disc"
							raise OSError("Profile key unavailable") from None
						self.corp = dict(self.corp, cheie=cheie)
						if not getattr(self, "fara_amprenta", False):
							self.corp = cuAmprenta(self.corp)
						self.corp.pop("nota", None)
				_brut, gz = comprima(self.corp)
				if not cerereActuala(self):
					return
				self.cod, octeti = self.posteaza(self.url, gz)
				self.raspuns = _json(octeti)
		except Exception as e:
			self.eroare = _mesajEroare(e)
			_jurnal("cererea %s: %s" % (self.url.rsplit("/", 1)[-1], self.eroare))
		finally:
			self.gata = True


# ------------------------------------------------------------------ mesajele testerului

def mesaj(fel, text, ecran="", cu_jurnal=False, captura=None, b=None, contor=None, acum=None):
	"""Mesajul testerului in coada (Greseala / Idee / Intrebare), cu jurnalul ultimei erori si captura numai daca le-a
	bifat omul. -> (reusit, mesaj)"""
	b = _b(b)
	if not inscris(b):
		return False, _t("Nu ești înscris în programul de beta testeri.")
	if fel not in FELURI_MESAJ:
		return False, _t("Alege felul mesajului.")
	text = (text or "").replace("\r", "").strip()
	text = "".join(c for c in text if c >= " " or c in "\n\t")[:TEXT_MAX]
	if not text:
		return False, _t("Scrie întâi mesajul.")
	stare = citesteStare()
	zi = ziUtc(acum)
	if stare.get("mesaje_zi") != zi:
		stare["mesaje_zi"] = zi
		stare["mesaje_azi"] = 0
	if int(stare.get("mesaje_azi", 0)) >= MESAJE_PE_ZI:
		return False, _t("Ai trimis deja 10 mesaje azi. Mai poți trimite mâine.")
	jurnal = ultimulJurnalCadere() if cu_jurnal else None
	if captura is not None and len(captura) > CAPTURA_MAX:
		captura = None
	model, paza = _modelTinut()
	corp = {"v": PROTOCOL, "id": b.id.value, "nota": int(b.nota.value), "model": model,
		"versiune": versiuneImagine(), "limba": limba(), "ore": contor.ore() if contor else _oreTinute(),
		"local": os.urandom(8).hex(), "fel": fel, "text": text, "ecran": textNume(ecran, ECRAN_MAX),
		"jurnal": jurnal, "captura": base64.b64encode(captura).decode("ascii") if captura else None}
	if not puneInCoada("mesaj", "mesaj", corp, limita=PACHET_MAX):
		return False, _t("Mesajul e prea mare.")
	intrare = {"local": corp["local"], "fel": fel, "cand": oraUtc(acum), "text": text[:200]}

	def adauga(s):
		if s.get("mesaje_zi") != zi:
			s["mesaje_zi"] = zi
			s["mesaje_azi"] = 0
		s["mesaje_azi"] = int(s.get("mesaje_azi", 0)) + 1
		mesaje = s.setdefault("mesaje", [])
		mesaje.insert(0, intrare)
		del mesaje[50:]
	schimbaStare(adauga)
	_ceruteAcum["trimite"] = True
	return True, _t("Mesajul a intrat în coadă și pleacă îndată ce receptorul are internet.")


# grab-ul capturii pentru raport: cel mult atat, apoi oprit, cu asteptarea marginita (HdsCapturi.ruleazaGrab); o
# captura reala dureaza sub 2 s. Cele doua incercari (80/960, apoi 60/640) incap in asteptarea paginii web (30 s).
CAPTURA_GRAB_S = 8
# LucrareFundal-urile capturilor in curs (capturaOsdInFundal), tinute in viata pana la sfarsit
_capturiInLucru = []


def _grabOsd(calitate, lat):
	"""Octetii JPEG ai lui grab -o (numai meniurile), sau None. Niciodata pe firul enigma2: pe HiSilicon grab pornit de
	acolo, cu bucla oprita cat asteapta, trece de termen (vezi Screens/HdsAsistentaSemn.GRAB)."""
	from Components import HdsCapturi
	stare, cod, date = HdsCapturi.ruleazaGrab(["grab", "-q", "-s", "-o", "-j", str(calitate), "-r", str(lat)],
		CAPTURA_GRAB_S)
	if stare != "ok" or cod != 0 or date[:2] != b"\xff\xd8":
		return None
	return date


def _pentruRaport(date, ecrane, marime, calitate):
	"""Copia curatata pentru echipa (fara valorile conturilor), JPEG, sau None la refuz. Pe firul enigma2: curatarea
	citeste ecranele deschise."""
	from Components import HdsAsistentaControl as Control
	date = Control.curataCapturaEchipa(date, ecrane, marime)
	if not date:
		return None
	if date[:2] != b"\xff\xd8":
		# Raportul primeste in continuare JPEG; PNG-ul cu zonele acoperite ramane numai in RAM.
		from PIL import Image
		with Image.open(io.BytesIO(date)) as imagine:
			iesire = io.BytesIO()
			imagine.convert("RGB").save(iesire, format="JPEG", quality=calitate)
			date = iesire.getvalue()
	return date


def capturaOsd(latime=CAPTURA_LATIME, ecrane=None, marime=None):
	"""Captura pentru raportul echipei, fara valorile conturilor; fara context, None. Nu modifica fotografia omului.
	Asteapta grab-ul pe loc: de pe firul enigma2 (ecranul TV, pagina web) se cheama capturaOsdInFundal. `ecrane` si
	`marime` explicite sunt pentru probele pe PC."""
	try:
		if ecrane is None:
			from Screens import HdsAsistentaSemn as Semn
			if Semn._session() is None:
				return None
			ecrane = Semn._stivaAcum()
		if marime is None:
			from enigma import getDesktop
			s = getDesktop(0).size()
			marime = s.width(), s.height()
		for calitate, lat in ((80, latime), (60, 640)):
			brut = _grabOsd(calitate, lat)
			if brut is None:
				return None
			date = _pentruRaport(brut, ecrane, marime, calitate)
			if not date:
				return None
			if len(date) <= CAPTURA_MAX:
				return date
	except Exception as e:
		_jurnal("captura: %s" % e.__class__.__name__)
	return None


def capturaOsdInFundal(gata, latime=CAPTURA_LATIME):
	"""capturaOsd pentru firul enigma2 (ecranul TV si pagina web; 0.7.5 FIR, TODO 15.11 06:15 (TRI, captura in fir)):
	grab-ul pe un fir separat (LucrareFundal), iar stiva ecranelor, compararea ei si curatarea copiei pe firul enigma2,
	ca la asistenta (Screens/HdsAsistentaSemn._captura). gata(octeti sau None) vine pe firul enigma2, o singura data.
	Un ecran deschis sau inchis in timpul grab-ului: fara captura (zonele acoperite ar fi ale altui ecran)."""
	def raspunde(date):
		try:
			gata(date)
		except Exception as e:
			_jurnal("captura, dupa: %s" % e.__class__.__name__)
	try:
		from Screens import HdsAsistentaSemn as Semn
		if Semn._session() is None:
			raspunde(None)
			return
		inainte = [id(e) for e in Semn._stivaAcum()]
		from enigma import getDesktop
		s = getDesktop(0).size()
		marime = s.width(), s.height()
		from Components.HdsPazaModel import LucrareFundal
	except Exception as e:
		_jurnal("captura: %s" % e.__class__.__name__)
		raspunde(None)
		return
	trepte = ((80, latime), (60, 640))

	def incearca(i):
		calitate, lat = trepte[i]
		stare = {"gata": False, "lucrare": None}

		def dupa(brut, eroare):
			stare["gata"] = True
			if stare["lucrare"] in _capturiInLucru:
				_capturiInLucru.remove(stare["lucrare"])
			date = None
			try:
				if brut and not eroare:
					ecrane = Semn._stivaAcum()
					if [id(e) for e in ecrane] != inainte:
						_jurnal("captura: ecranele s-au schimbat in timpul capturii")
					else:
						date = _pentruRaport(brut, ecrane, marime, calitate)
						if date and len(date) > CAPTURA_MAX:
							date = None
							if i + 1 < len(trepte):
								incearca(i + 1)
								return
			except Exception as e:
				_jurnal("captura: %s" % e.__class__.__name__)
				date = None
			raspunde(date)
		lucrare = LucrareFundal(lambda: _grabOsd(calitate, lat), dupa)
		if not stare["gata"]:
			stare["lucrare"] = lucrare
			_capturiInLucru.append(lucrare)
	incearca(0)


def citesteRaspunsuri():
	return citesteJson(cale("raspunsuri.json"), {}) or {}


def tineRaspunsuri(raspuns):
	"""Raspunsul serverului la `raspunsuri`, tinut pe receptor (cu ce a vazut omul pana acum)."""
	vechi = citesteRaspunsuri()
	mesaje = [m for m in (raspuns.get("mesaje") or []) if isinstance(m, dict)][:50]
	try:
		scrieJson(cale("raspunsuri.json"), {"cand": oraUtc(), "mesaje": mesaje, "vazute": vechi.get("vazute") or {},
			"anuntate": vechi.get("anuntate") or {}})
	except (OSError, IOError) as e:
		_jurnal("raspunsurile: %s" % e)


def raspunsuriNoi(r=None):
	r = citesteRaspunsuri() if r is None else r
	vazute = r.get("vazute") or {}
	n = 0
	for m in r.get("mesaje") or []:
		if len(m.get("raspunsuri") or []) > int(vazute.get(str(m.get("mesaj")), 0)):
			n += 1
	return n


def marcheazaVazute():
	r = citesteRaspunsuri()
	r["vazute"] = dict((str(m.get("mesaj")), len(m.get("raspunsuri") or [])) for m in r.get("mesaje") or [])
	try:
		scrieJson(cale("raspunsuri.json"), r)
	except (OSError, IOError) as e:
		_jurnal("raspunsurile: %s" % e)


def _intreg(v):
	try:
		return int(v)
	except (TypeError, ValueError):
		return 0


def deAnuntat(r=None):
	"""Raspunsurile echipei pe care omul nu le-a vazut nici in lista, nici in fereastra: [(mesajul, raspunsurile noi)]."""
	r = citesteRaspunsuri() if r is None else r
	vazute = r.get("vazute") or {}
	anuntate = r.get("anuntate") or {}
	noi = []
	for m in r.get("mesaje") or []:
		if not isinstance(m, dict):
			continue
		cheie = str(m.get("mesaj"))
		rs = [x for x in m.get("raspunsuri") or [] if isinstance(x, dict)]
		deja = max(_intreg(vazute.get(cheie)), _intreg(anuntate.get(cheie)))
		if len(rs) > deja:
			noi.append((m, rs[deja:]))
	return noi


def marcheazaAnuntate():
	"""Ce e acum in raspunsuri.json a fost aratat in fereastra (nu se mai arata; insigna din meniu ramane pana la lista)."""
	r = citesteRaspunsuri()
	r["anuntate"] = dict((str(m.get("mesaj")), len(m.get("raspunsuri") or [])) for m in r.get("mesaje") or []
		if isinstance(m, dict))
	try:
		scrieJson(cale("raspunsuri.json"), r)
	except (OSError, IOError) as e:
		_jurnal("raspunsurile: %s" % e)


def textAnunt(noi):
	"""Textul ferestrei cu raspunsurile noi: mesajul echipei asa cum e, raspunsul cu inceputul mesajului omului."""
	parti = []
	for m, rs in noi:
		texte = "\n\n".join((x.get("text") or "") for x in rs)
		if m.get("fel") == FEL_ECHIPA:
			parti.append(texte)
		else:
			inceput = (m.get("text") or "").strip().replace("\n", " ")
			if len(inceput) > 80:
				inceput = inceput[:79].rstrip() + "..."
			parti.append(_t("La mesajul tău „%s”:") % inceput + "\n" + texte)
	parti.append(_t("Mesajele echipei rămân în meniul Beta tester, la „Răspunsurile echipei”."))
	return "\n\n".join(parti)


def textRaspunsuri(r=None):
	"""Textul „Raspunsurile echipei”: fiecare mesaj cu starea lui si raspunsurile, cel mai nou sus."""
	r = citesteRaspunsuri() if r is None else r
	mesaje = r.get("mesaje") or []
	locale = dict((m.get("local"), m) for m in citesteStare().get("mesaje") or [])
	if not mesaje and not locale:
		return _t("Nu ai trimis încă niciun mesaj.")
	parti = []
	vazute = set()
	for m in mesaje:
		vazute.add(m.get("local"))
		if m.get("fel") == FEL_ECHIPA:
			rs = [x for x in m.get("raspunsuri") or [] if isinstance(x, dict)]
			primul = rs[0] if rs else {}
			parti.append("%s (%s)\n%s" % (_t("Mesaj de la echipă"), (primul.get("cand") or m.get("primit") or "")[:10],
				primul.get("text") or ""))
			for rasp in rs[1:]:
				parti.append("    %s %s: %s" % (_t("Echipa"), (rasp.get("cand") or "")[:10], rasp.get("text") or ""))
			continue
		cap = "%s (%s), %s" % (_t(FELURI_MESAJ_TEXT.get(m.get("fel"), m.get("fel", ""))), (m.get("primit") or "")[:10],
			_t(STARI_MESAJ.get(m.get("stare"), m.get("stare", ""))))
		parti.append(cap + "\n" + (m.get("text") or ""))
		for rasp in m.get("raspunsuri") or []:
			parti.append("    %s %s: %s" % (_t("Echipa"), (rasp.get("cand") or "")[:10], rasp.get("text") or ""))
	for local, m in locale.items():
		if local not in vazute:
			parti.append("%s (%s), %s\n%s" % (_t(FELURI_MESAJ_TEXT.get(m.get("fel"), "")), (m.get("cand") or "")[:10],
				_t("încă neprimit de server"), m.get("text") or ""))
	return "\n\n".join(parti)


# ------------------------------------------------------------------ profilul public si legarea

def citesteCheie():
	t = _citesteText(cale("cheie"), 128)
	t = (t or "").strip()
	return t if re.match(r"\A[0-9a-f]{64}\Z", t) else ""


def cheieProfil():
	"""Cheia receptorului pentru profil: facuta la prima nevoie, tinuta numai in DOSAR/cheie (0600), niciodata
	aratata."""
	try:
		with open(cale("cheie"), "r", encoding="ascii") as f:
			c = f.read(129).strip()
	except FileNotFoundError:
		pass
	else:
		if not re.fullmatch(r"[0-9a-f]{64}", c):
			raise OSError("Invalid saved profile key")
		return c
	c = os.urandom(32).hex()
	try:
		scrieAtomic(cale("cheie"), c.encode("ascii"), 0o600)
		with open(cale("cheie"), "rb") as f:
			if f.read(129) != c.encode("ascii"):
				raise OSError("Profile key verification failed")
	except (OSError, IOError) as e:
		_jurnal("cheia profilului: %s" % e)
		raise
	return c


def corpProfil(ruta, b=None, **campuri):
	"""Corpul unei cereri de profil (profil, profil-stare, cod-legare, leaga, dezleaga)."""
	b = _b(b)
	corp = cuAmprenta({"v": PROTOCOL, "id": b.id.value, "cheie": cheieProfil()})
	corp.update(campuri)
	return corp


def contextProfil(b=None):
	"""Capture config on main, without disk access; workers receive plain data."""
	b = _b(b)
	server = b.server.value
	model, paza = _modelTinut()
	acord = {"v": PROTOCOL, "id": b.id.value, "nota": int(b.nota.value), "acord": b.acord.value or None,
		"feluri": bife(b), "model": model, "paza": paza, "ore": _oreTinute(), "limba": limba(),
		"nume": b.nume.value, "email": b.email.value}
	return {"server": server, "acord": acord, "generatie": _GENERATIE, "revizie": _REVIZIE_ACORD}


def cerereProfilContext(ctx, ruta, posteaza=None, **campuri):
	"""Prepare an unstarted request using a main-thread snapshot, also for the forum."""
	acord = ctx["acord"]
	c = Cerere(ctx["server"], ruta, dict({"v": PROTOCOL, "id": acord["id"], "nota": acord["nota"]}, **campuri), posteaza)
	c.server = ctx["server"]
	c.acord = dict(acord)
	c.ruta = ruta
	c.generatie = ctx["generatie"]
	c.revizie = ctx["revizie"]
	return c


def cerereProfil(ruta, b=None, posteaza=None, **campuri):
	"""Porneste cererea (pe fir) si o intoarce; ecranul sau pagina asteapta .gata."""
	b = _b(b)
	if not inscris(b):
		return None
	c = cerereProfilContext(contextProfil(b), ruta, posteaza, **campuri)
	c.start()
	return c


def textProfil(profil):
	"""Starea profilului public pe intelesul omului."""
	if not profil:
		return _t("Nu apari public. Poți alege un nume public mai jos.")
	parti = []
	if profil.get("nume_public"):
		parti.append(_t("Apari public ca „%s”.") % profil["nume_public"])
	else:
		parti.append(_t("Nu apari public."))
	if profil.get("cont"):
		parti.append(_t("Legat de contul „%s” de pe forum.") % profil["cont"])
	if profil.get("email") == "trimis":
		parti.append(_t("Ți-am trimis pe e-mail legătura de confirmare."))
	elif profil.get("email") == "confirmat":
		parti.append(_t("E-mailul e confirmat."))
	return " ".join(parti)


def mesajRaspunsProfil(cerere):
	"""Mesajul pentru om dupa o cerere de profil terminata."""
	if not cerereActuala(cerere):
		if getattr(cerere, "generatie", _GENERATIE) == _GENERATIE:
			return False, _t("Setările programului s-au schimbat între timp. Cererea nu mai este valabilă.")
		return False, _t("Cererea este de dinaintea ștergerii datelor și nu mai este valabilă.")
	if getattr(cerere, "eroare_profil", "") == "disc":
		return False, _t(CHEIE_DISC)
	if cerere.eroare or not cerere.cod:
		return False, _t("Serverul nu răspunde acum. Încearcă mai târziu.")
	if 200 <= cerere.cod < 300:
		return True, ""
	eroare = cerere.raspuns.get("eroare", "")
	texte = {
		"nume_luat": _t("Numele public e deja folosit de alt tester. Alege altul."),
		"cod_gresit": _t("Codul nu e bun sau a expirat. Cere un cod nou de pe site."),
		"prea_multe": _t("Prea multe încercări. Mai încearcă peste o oră."),
		"fara_acord": _t("Serverul nu are încă acordul tău. Mai încearcă peste câteva minute."),
		"cheie": _t("Profilul e legat de alt receptor."),
	}
	if cerere.cod == 429:
		return False, texte["prea_multe"]
	return False, texte.get(eroare, _t("Serverul a refuzat cererea (%s).") % (eroare or cerere.cod))


# ------------------------------------------------------------------ pornirea pe receptor

def limba():
	try:
		from Components.config import config
		return (config.osd.language.value or "")[:10]
	except Exception:
		return ""


_starea = {"contor": None, "es": None, "pornire_s": None, "model": None, "nume_model": "", "lucru": None,
	"mai_tarziu_pana": 0.0, "pornit_mono": None, "ultim_esantion": None, "intrebare_pana": 0.0, "sesiune": None,
	"timer": None, "activ": False, "abatere_s": 0, "auto_pana": 0.0, "jurnale_pornire": False, "numar": None,
	"numar_cand": None, "cerere_numar": None, "fir_model": None, "legare_forum": False, "email_forum": False,
	"cerere_raspunsuri": None, "raspunsuri_pornire": False, "raspunsuri_datorat": False, "de_anuntat": False,
	"stat_procesor": None}


def _modelTinut():
	m = _starea.get("model")
	if m:
		return m
	return "", {}


def _oreTinute():
	c = _starea.get("contor")
	return c.ore() if c else 0.0


def contor():
	if _starea["contor"] is None:
		_starea["contor"] = Contor()
	return _starea["contor"]


def numaraEcran(ecran):
	"""Din Session.open (mytest.py): numele clasei ecranului deschis, numai cat programul e pornit."""
	if not _starea["activ"]:
		return
	try:
		nume = getattr(ecran, "__name__", None) or type(ecran).__name__
		contor().numaraEcran(str(nume))
	except Exception:
		pass


def ultimulEcranTitlu(sesiune=None):
	"""Titlul ecranului de sub meniul testerului (completarea „ecranul sau functia” din formular)."""
	sesiune = sesiune or _starea.get("sesiune")
	try:
		for dlg, _arata in reversed(getattr(sesiune, "dialog_stack", []) or []):
			nume = type(dlg).__name__
			if nume.startswith("HdsBeta") or nume in ("Menu", "MenuDale", "InfoBar"):
				continue
			titlu = ""
			try:
				titlu = dlg.getTitle()
			except Exception:
				titlu = ""
			return textNume(titlu or nume, ECRAN_MAX)
	except Exception:
		pass
	return ""


def _stareTelevizor(sesiune):
	rez = {"standby": False, "bara_libera": False, "film": False, "inregistrare": False, "decalaj": False}
	try:
		from Screens import Standby
		rez["standby"] = Standby.inStandby is not None
	except Exception:
		pass
	try:
		from Screens.InfoBar import InfoBar
		bara = InfoBar.instance
		rez["bara_libera"] = bara is not None and sesiune.current_dialog is bara
		rez["decalaj"] = bool(getattr(bara, "timeshift_enabled", 0))
	except Exception:
		pass
	try:
		rez["inregistrare"] = bool(sesiune.nav.getRecordings())
	except Exception:
		pass
	try:
		ref = sesiune.nav.getCurrentlyPlayingServiceReference()
		rez["film"] = bool(ref is not None and ref.getPath())
	except Exception:
		pass
	return rez


# ------------------------------------------------------------------ cati beta testeri are modelul acesta

NUMAR_PRIMA_S = 120
NUMAR_LA_S = 12 * 3600
NUMAR_VECHI_S = 6 * 3600


class CerereGet(threading.Thread):
	"""GET la server (starea publica: numarul de testeri pe model), pe un fir: .gata, .cod, .raspuns."""

	def __init__(self, url, citeste=None):
		threading.Thread.__init__(self, name="hds-beta-stare")
		self.daemon = True
		self.url = url
		self.citeste = citeste or _citesteHttp
		self.gata = False
		self.cod = 0
		self.raspuns = {}

	def run(self):
		try:
			self.cod, octeti = self.citeste(self.url)
			self.raspuns = _json(octeti)
		except Exception as e:
			_jurnal("starea serverului: %s" % _mesajEroare(e))
		self.gata = True


def _citesteHttp(url, timp=TIMP_CERERE_S):
	from urllib.request import Request, urlopen
	r = urlopen(Request(url, headers={"User-Agent": "hdsatelit-receptor/1", "Accept": "application/json"}),
		timeout=timp)
	try:
		return r.getcode(), r.read(256 * 1024)
	finally:
		r.close()


def numarDinStare(raspuns, model):
	"""Numarul de testeri ai modelului din raspunsul `stare`; None cand raspunsul nu e bun (randul nu apare)."""
	if not model or not isinstance(raspuns, dict):
		return None
	modele = raspuns.get("modele")
	if not isinstance(modele, dict):
		return None
	m = modele.get(model)
	if m is None:
		return 0
	n = m.get("testeri") if isinstance(m, dict) else None
	return n if isinstance(n, int) and 0 <= n < 1000000 else None


def textNumarModel(n, nume_model=""):
	"""Randul cu numarul de beta testeri ai modelului, sau "" (numar necunoscut: randul nu apare)."""
	if n is None:
		return ""
	if n == 0:
		return _t("Pe acest receptor nu e încă niciun beta tester. Vrei să fii primul?")
	nume = nume_model or _t("acest model")
	if n == 1:
		return _t("Pe %s este deja un beta tester.") % nume
	if n % 100 >= 20 or n % 100 == 0:
		return _t("Pe %s sunt deja %d de beta testeri.") % (nume, n)
	return _t("Pe %s sunt deja %d beta testeri.") % (nume, n)


def randNumar(b=None):
	"""Randul de acum (din memorie), sau "". Un tester inscris nu primeste „fii primul” (serverul inca nu l-a numarat):
	la zero, pentru el, randul lipseste."""
	n = _starea.get("numar")
	if n == 0:
		try:
			if inscris(b):
				return ""
		except Exception:
			pass
	return textNumarModel(n, _starea.get("nume_model") or "")


def ceNumar(acum=None, vechime=NUMAR_VECHI_S, citeste=None):
	"""Porneste cererea numarului daca cel stiut e mai vechi decat `vechime` (ecranul nu asteapta)."""
	acum = time.monotonic() if acum is None else acum
	model = _modelTinut()[0]
	if not model or _starea.get("cerere_numar") is not None:
		return
	cand = _starea.get("numar_cand")
	if cand is not None and acum - cand < vechime:
		return
	b = initConfig()
	c = CerereGet(adresaServer(b) + "stare?model=" + model, citeste)
	_starea["cerere_numar"] = c
	_starea["numar_cand"] = acum
	c.start()


def _culegeNumar():
	c = _starea.get("cerere_numar")
	if c is None or not c.gata:
		return
	_starea["cerere_numar"] = None
	n = numarDinStare(c.raspuns, _modelTinut()[0]) if 200 <= c.cod < 300 else None
	if n is not None or _starea.get("numar") is None:
		_starea["numar"] = n
	if 200 <= c.cod < 300 and isinstance(c.raspuns, dict):
		_starea["legare_forum"] = c.raspuns.get("legare_forum") is True
		_starea["email_forum"] = c.raspuns.get("email_forum") is True


# TODO 1860 b (Eduard 29.10.2026 16:26: „«Nu ai internet? Trimite prin cod QR» ar trebui să apară doar dacă chiar nu
# are net”): o proba scurta la serverul testerilor, in fundal, cu timp limita; rezultatul tinut minte PROBA_SERVER_S.
# Randul din meniul Beta tester (si cardul din web) apare numai cand proba a esuat.
PROBA_SERVER_S = 300
PROBA_SERVER_TIMP_S = 8


def probaServer(acum=None, citeste=None):
	"""Porneste proba serverului daca rezultatul e mai vechi de PROBA_SERVER_S (ecranul nu asteapta)."""
	acum = time.monotonic() if acum is None else acum
	c = _starea.get("cerere_proba")
	if c is not None:
		if c.gata:
			_starea["cerere_proba"] = None
			_starea["server_ok"] = 200 <= c.cod < 500
			_starea["server_ok_cand"] = acum
		return
	cand = _starea.get("server_ok_cand")
	if cand is not None and acum - cand < PROBA_SERVER_S:
		return
	model = _modelTinut()[0] or "proba"
	c = CerereGet(adresaServer(initConfig()) + "stare?model=" + model,
		citeste or (lambda url: _citesteHttp(url, PROBA_SERVER_TIMP_S)))
	_starea["cerere_proba"] = c
	_starea["server_ok_cand"] = acum
	c.start()


def serverFaraRaspuns():
	"""True numai cand ultima proba a serverului a esuat (fara retea, fara DNS, timp depasit, 5xx)."""
	c = _starea.get("cerere_proba")
	if c is not None and c.gata:
		probaServer()
	return _starea.get("server_ok") is False


def legareForum():
	"""Drumurile cu contul de pe forum (codul QR, cele 6 cifre) se arata numai cand serverul spune ca le are
	(„legare_forum”: true in raspunsul `stare`); pana atunci numai numele public."""
	return bool(_starea.get("legare_forum"))


def emailForum():
	"""Campul „E-mailul pentru cont” (contul de forum facut prin e-mailul de confirmare) se arata numai cand serverul
	spune si „email_forum”: true. Legarea poate merge fara partea de e-mail: atunci serverul lasa adresa deoparte, iar
	omul ar astepta degeaba legatura de confirmare (greseala 1217). E-mailul din acord, pentru raspunsurile echipei,
	ramane oricum."""
	return legareForum() and bool(_starea.get("email_forum"))


def _calculeazaModel():
	"""Modelul, paza si numele modelului, o data, pe un fir (paza citeste fisiere mici, dar nu pe firul enigma2)."""
	def lucru():
		model, paza = modelSiPaza()
		_starea["model"] = (model, paza)
	t = threading.Thread(target=lucru, name="hds-beta-model")
	t.daemon = True
	_starea["fir_model"] = t
	t.start()


# ------------------------------------------------------------------ trimiterea automata zilnica

ORA_AUTO = 3
FEREASTRA_AUTO_S = 3 * 3600
ABATERE_AUTO_S = 120 * 60
AUTO_MINIM_S = 20 * 3600
AUTO_PIERDUT_S = 26 * 3600
AUTO_PORNIRE_MIN_S = 300
AUTO_PORNIRE_MAX_S = 35 * 60
AUTO_AMANARE_S = 600
BLOCURI_OPKG = ("/run/opkg.lock", "/var/lib/opkg/lock", "/tmp/opkg.lock")


def opkgLucreaza(blocuri=BLOCURI_OPKG):
	return any(os.path.exists(c) for c in blocuri)


def secundaZilei(acum_utc=None):
	t = time.localtime(time.time() if acum_utc is None else acum_utc)
	return t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec


def autoDatorat(ultim_auto, acum_utc, sus_s, abatere_s, secunda=None):
	"""Trimiterea zilnica e datorata acum? In fereastra linistita (ORA_AUTO + abaterea, cel mult FEREASTRA_AUTO_S),
	la cel putin AUTO_MINIM_S de la ultima; sau, peste AUTO_PIERDUT_S (receptorul oprit noaptea), la pornire, dupa
	AUTO_PORNIRE_MIN_S + abaterea (cel mult AUTO_PORNIRE_MAX_S)."""
	secunda = secundaZilei(acum_utc) if secunda is None else secunda
	trecut = acum_utc - float(ultim_auto or 0)
	if trecut < AUTO_MINIM_S:
		return False
	start = ORA_AUTO * 3600 + abatere_s % ABATERE_AUTO_S
	if start <= secunda < ORA_AUTO * 3600 + FEREASTRA_AUTO_S:
		return True
	pornire = AUTO_PORNIRE_MIN_S + abatere_s % (AUTO_PORNIRE_MAX_S - AUTO_PORNIRE_MIN_S)
	return trecut >= AUTO_PIERDUT_S and sus_s >= pornire


def textUltimaTrimitere(secunde, acum=None):
	"""„Ultima trimitere: azi, 04:12” / „ieri, 04:12” / data; "" daca nu a plecat nimic."""
	if not secunde:
		return _t("Ultima trimitere: încă nimic.")
	acum = time.time() if acum is None else acum
	t = time.localtime(secunde)
	azi = time.localtime(acum)
	ora = time.strftime("%H:%M", t)
	if (t.tm_year, t.tm_yday) == (azi.tm_year, azi.tm_yday):
		return _t("Ultima trimitere: azi, %s") % ora
	ieri = time.localtime(acum - 86400)
	if (t.tm_year, t.tm_yday) == (ieri.tm_year, ieri.tm_yday):
		return _t("Ultima trimitere: ieri, %s") % ora
	return _t("Ultima trimitere: %s") % time.strftime("%Y-%m-%d %H:%M", t)


def randUltimaTrimitere():
	dosar, generatie, secunde = _ULTIMA_TRIMITERE
	return textUltimaTrimitere(secunde if dosar == DOSAR and generatie == _GENERATIE else None)


def trimiteAcum():
	"""„Trimite acum”: toate felurile bifate pe loc in coada, apoi trimiterea."""
	b = initConfig()
	if not inscris(b):
		return False, _t("Nu ești înscris în programul de beta testeri.")
	_ceruteAcum["culegere"] = True
	_ceruteAcum["trimite"] = True
	_starea["mai_tarziu_pana"] = 0.0
	return True, _t("Se adună datele bifate și pleacă îndată ce receptorul are internet.")


# ------------------------------------------------------------------ porneste, tic, opreste

def porneste(sesiune):
	"""Din mytest.py, la pornire: contorul, intrebarea, culegerea si trimiterea, pe un eTimer de un minut."""
	b = initConfig()
	_starea["sesiune"] = sesiune
	_starea["contor"] = Contor()
	_starea["es"] = Esantioane()
	_starea["pornit_mono"] = time.monotonic()
	_starea["pornire_s"] = _sus()
	_starea["activ"] = bool(b.activ.value)
	_starea["abatere_s"] = int.from_bytes(os.urandom(4), "big")
	_calculeazaModel()
	try:
		from enigma import eTimer
		t = eTimer()
		t.callback.append(tic)
		t.start(TIC_S * 1000, False)
		_starea["timer"] = t
	except Exception as e:
		_jurnal("pornirea: %s" % e)
		return
	try:
		from enigma import iPlayableService
		sesiune.nav.event.append(lambda ev: _laEveniment(ev, iPlayableService.evStart))
		sesiune.nav.record_event.append(_laInregistrare)
	except Exception as e:
		_jurnal("numaratoarea canalelor: %s" % e)


def _laEveniment(ev, ev_start):
	if ev == ev_start and _starea["activ"]:
		contor().zapuri += 1


def _laInregistrare(serviciu, ev):
	try:
		from enigma import iRecordableService
		if ev == iRecordableService.evStart and _starea["activ"]:
			contor().inregistrari += 1
	except Exception:
		pass


def opreste():
	"""Din mytest.py, la iesirea interfetei: contorul scris (numai daca programul il mai scrie)."""
	try:
		b = initConfig()
		c = _starea.get("contor")
		if c is not None and (b.intrebare.value == "" or b.activ.value):
			c.scrie()
	except Exception as e:
		_jurnal("oprirea: %s" % e)


def _reporniri():
	try:
		from Components import HdsPaznic
		r = HdsPaznic.stare().get("reporniri")
		return int(r) if r is not None else None
	except Exception:
		return None


def tic(acum=None):
	"""La un minut, pe firul enigma2."""
	try:
		_tic(acum)
	except Exception as e:
		_jurnal("tic: %s" % e)


def _tic(acum=None):
	b = initConfig()
	if not _reiaStergerea(b):
		return
	acum = time.monotonic() if acum is None else acum
	sesiune = _starea.get("sesiune")
	stare_tv = _stareTelevizor(sesiune) if sesiune is not None else {"standby": True}
	c = contor()
	c.tic(stare_tv.get("standby"), acum)
	_starea["activ"] = bool(b.activ.value)
	pornit = _starea["pornit_mono"] or acum
	# contorul: la 15 minute pana la intrebare, apoi la 60 numai cat programul e pornit
	if b.intrebare.value == "":
		if c.trebuieScris(SCRIERE_PANA_LA_INTREBARE_S, acum):
			c.scrie(acum)
	elif b.activ.value and c.trebuieScris(SCRIERE_DUPA_S, acum):
		c.scrie(acum)
	# numarul de testeri ai modelului: la 2 minute dupa pornire, apoi la 12 ore (numai in memorie)
	_culegeNumar()
	if acum - pornit >= NUMAR_PRIMA_S:
		ceNumar(acum, NUMAR_LA_S)
	# intrebarea
	if trebuieIntrebat(b, c) and acum >= _starea["intrebare_pana"]:
		if potIntreba(stare_tv):
			_intreaba(sesiune)
		else:
			_starea["intrebare_pana"] = acum + REINCERCARE_INTREBARE_S
	_culegeRezultate(b)
	if not b.activ.value or not idValid(b.id.value):
		if not coadaGoala() and acum >= _starea["mai_tarziu_pana"] and _starea["lucru"] is None:
			_pornesteLucru(b, (), acord=False)
		return
	# esantioanele felului "sistem"; procesorul ocupat din diferenta /proc/stat fata de ticul dinainte (o citire tinuta aici,
	# nu in Esantioane, care se ia de la capat la fiecare trimitere; mai veche de FEREASTRA_PROCESOR_S nu se foloseste)
	inainte = _starea.get("stat_procesor")
	if inainte is not None and not (0 < acum - inainte[0] <= FEREASTRA_PROCESOR_S):
		inainte = None
	if _starea["ultim_esantion"] is None or acum - _starea["ultim_esantion"] >= ESANTION_S:
		_starea["ultim_esantion"] = acum
		_starea["stat_procesor"] = (acum, _starea["es"].citeste(stat_inainte=inainte[1] if inainte else None))
	else:
		_starea["stat_procesor"] = (acum, _statProcesor())
	if notaVeche(b):
		# nimic nu pleaca; anuntul notei noi, cand omul e la televizor (o data pe zi)
		if acum - pornit >= NOTA_ANUNT_DUPA_S and potIntreba(stare_tv) and anuntNotaDatorat(b):
			_anuntaNota(sesiune)
		return
	if inscris(b):
		_verificaRaspunsuri(b, acum, pornit, stare_tv, sesiune)
	# acordul retrimis la prima ora (cine s-a inscris singur inainte de o ora)
	if not b.acord_ora.value and c.secunde >= ORA_S:
		b.acord_ora.value = True
		salveaza(b)
		_ceruteAcum["acord"] = True
	if _starea["lucru"] is not None:
		return
	sarcini = []
	auto_zilnic = False
	if _ceruteAcum.pop("culegere", False):
		sarcini = list(FELURI)
	elif b.automat.value and acum >= _starea["auto_pana"]:
		ocupat = stare_tv.get("inregistrare") or opkgLucreaza()
		sus_s = acum - pornit
		if not _starea["jurnale_pornire"] and sus_s >= PRIMA_CULEGERE_S:
			# dupa o cadere a interfetei sau o actualizare cazuta: jurnalele noi, imediat
			if ocupat:
				_starea["auto_pana"] = acum + AUTO_AMANARE_S
			else:
				_starea["jurnale_pornire"] = True
				sarcini.append("jurnale")
		elif autoDatorat(citesteStare().get("ultim_auto"), time.time(), sus_s, _starea["abatere_s"]):
			if ocupat:
				_starea["auto_pana"] = acum + AUTO_AMANARE_S
			else:
				sarcini = list(FELURI)
				auto_zilnic = True
	acord = _ceruteAcum.pop("acord", False)
	trimite = _ceruteAcum.pop("trimite", False) or acum >= _starea["mai_tarziu_pana"]
	if sarcini or acord or (trimite and not coadaGoala()):
		_pornesteLucru(b, sarcini, acord=acord, auto_zilnic=auto_zilnic)


def _pornesteLucru(b, sarcini, acord=False, auto_zilnic=False):
	c = contor()
	model = _starea.get("model") or ("", {})
	inst = instantaneu(b, c, model[0], model[1], versiuneImagine(), limba())
	es = utilizare = None
	if "sistem" in sarcini:
		es = _starea["es"]
		_starea["es"] = Esantioane()
	if "utilizare" in sarcini:
		utilizare = c.utilizare()
		c.zeroUtilizare()
	if _starea.get("model") is None:
		inst["model"], inst["paza"] = "", {}
	lucru = Lucru(inst, sarcini, True, es, utilizare, _starea["pornire_s"], _reporniri(), acord=acord,
		auto_zilnic=auto_zilnic)
	_starea["lucru"] = lucru
	lucru.start()


def _culegeRezultate(b):
	lucru = _starea.get("lucru")
	if lucru is None or lucru.is_alive():
		return
	_starea["lucru"] = None
	if not cerereActuala(lucru):
		return
	if getattr(lucru, "plecate", 0):
		_starea["raspunsuri_datorat"] = True
	if lucru.mai_tarziu:
		_starea["mai_tarziu_pana"] = time.monotonic() + REINCERCARE_S
	for fel, valoare in lucru.rezultate:
		if fel == "model":
			_starea["model"] = valoare
		elif fel == "nota_veche":
			b.nota.value = 0
			salveaza(b)
		elif fel == "fara_acord":
			_ceruteAcum["acord"] = True
		elif fel == "acord_trimis":
			# numarul de testeri ai modelului se cere din nou, acum ca serverul are acordul
			_starea["numar_cand"] = None


def _verificaRaspunsuri(b, acum, pornit, stare_tv, sesiune):
	"""Raspunsurile echipei (si mesajul scris primul de echipa) cerute la contactele care oricum au loc: o data la
	PRIMA_CULEGERE_S dupa pornire si dupa fiecare trimitere cu pachete plecate, fara alt ceas. Ce e nou si nevazut apare
	intr-o fereastra o singura data (anuntate, in raspunsuri.json: nici dupa o repornire), numai peste televizorul in
	direct; altfel asteapta tic-ul urmator. Apoi ramane in lista Raspunsurile echipei."""
	c = _starea.get("cerere_raspunsuri")
	if c is not None:
		if not c.gata:
			return
		_starea["cerere_raspunsuri"] = None
		if cerereActuala(c) and 200 <= c.cod < 300 and isinstance(c.raspuns, dict):
			tineRaspunsuri(c.raspuns)
			_starea["de_anuntat"] = bool(deAnuntat())
	elif _starea["raspunsuri_datorat"] or (not _starea["raspunsuri_pornire"] and acum - pornit >= PRIMA_CULEGERE_S):
		_starea["raspunsuri_pornire"] = True
		_starea["raspunsuri_datorat"] = False
		c = Cerere(adresaServer(b), "raspunsuri", {"v": PROTOCOL, "id": b.id.value})
		_starea["cerere_raspunsuri"] = c
		c.start()
		return
	if _starea["de_anuntat"] and sesiune is not None and potIntreba(stare_tv):
		_starea["de_anuntat"] = False
		_anuntaRaspunsuri(sesiune)


def _anuntaRaspunsuri(sesiune):
	"""Fereastra cu raspunsurile noi; anuntate se scrie inainte (o cadere a ecranului nu o repeta la un minut)."""
	noi = deAnuntat()
	if not noi:
		return
	marcheazaAnuntate()
	titlu = _t("Mesaj de la echipă") if any(m.get("fel") == FEL_ECHIPA for m, _rs in noi) else _t("Răspunsurile echipei")
	try:
		from Screens.HdsBetaTester import HdsBetaText
		sesiune.open(HdsBetaText, titlu, textAnunt(noi))
	except Exception as e:
		_jurnal("fereastra raspunsurilor: %s" % e)


def _intreaba(sesiune):
	"""Intrebarea Da/Nu, o singura data. Raspunsul se scrie pe loc; Da deschide ecranul acordului. Cu numarul de
	testeri ai modelului, cand e stiut (altfel fara randul lui)."""
	b = initConfig()
	b.intrebare.value = "pusa"
	salveaza(b)
	text = textIntrebare()
	rand = randNumar()
	if rand:
		text += " " + rand
	try:
		from Screens.MessageBox import MessageBox
		sesiune.openWithCallback(_dupaIntrebare, MessageBox, text, MessageBox.TYPE_YESNO, default=True)
	except Exception as e:
		_jurnal("intrebarea: %s" % e)


def _anuntaNota(sesiune):
	"""Anuntul notei noi pe ecran; ziua se scrie inainte (o cadere a ecranului nu-l repeta la un minut)."""
	amanaAnuntNota()
	try:
		from Screens.HdsBetaTester import HdsBetaNotaNoua
		sesiune.open(HdsBetaNotaNoua)
	except Exception as e:
		_jurnal("anuntul notei noi: %s" % e)


def _dupaIntrebare(raspuns):
	raspundeIntrebarii(bool(raspuns))
	if raspuns:
		try:
			from Screens.HdsBetaTester import HdsBetaAcord
			_starea["sesiune"].open(HdsBetaAcord)
		except Exception as e:
			_jurnal("ecranul acordului: %s" % e)

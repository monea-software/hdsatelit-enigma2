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
#   inregistrare in curs, fara decalaj, fara standby); Nu = nu mai apare niciodata. E singurul mesaj pe care programul
#   il pune singur pe ecran: trimiterile, erorile si coada plina raman in jurnal si in „Ce am trimis”;
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

# versiunea Notei de confidentialitate (situl-imaginii/date/nota-testeri.json); 2 = cu amprenta receptorului
NOTA = 2
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

ORA_S = 3600
TIC_S = 60
SCRIERE_PANA_LA_INTREBARE_S = 900
SCRIERE_DUPA_S = 3600
ESANTION_S = 600
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
		N_("Memoria, tunerele, plăcile de rețea (fără adresa MAC), ieșirea HDMI și driverele, ca să adaptăm imaginea "
			"și lista de receptoare.")),
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
	"ales de tine sau cu un nume automat. Nota întreagă e la adresa de mai jos.")
# randul scurt de sub fiecare rand al meniului testerului si al celui neinscris (pe receptor si in web): exact ce
# face randul
RANDURI_MENIU = {
	"forum": N_("Ce scriu testerii acestui receptor; scrii și tu, cu capturi."),
	"mesaj": N_("O greșeală, o idee sau o întrebare, direct echipei."),
	"trimite_acum": N_("Datele bifate pleacă imediat."),
	"trimise": N_("Ultimele pachete plecate și starea fiecăruia."),
	"raspunsuri": N_("Ce ți-a răspuns echipa la mesaje."),
	"date": N_("Alegi ce date pleacă, numele și e-mailul."),
	"acum": N_("Tot ce a plecat în ultimul pachet."),
	"probe": N_("Probe pe receptor: ce merge și ce nu."),
	"asistenta": N_("Ne lași să vedem starea receptorului, cât alegi tu."),
	"canal_testeri": N_("Versiunile noi ajung întâi la tine."),
	"public": N_("Numele cu care apari pe forum și pe site."),
	"nota": N_("Ce date pleacă, cine le primește, cât se păstrează."),
	"iesire": N_("Serverul șterge tot ce a trimis acest receptor."),
}
RANDURI_VIZITATOR = {
	"acord": N_("Alegi ce date trimiți; sunt anonime."),
	"forum": N_("Citește ce scriu testerii acestui receptor."),
}
# avantajele aratate celui care nu e inscris (pe receptor si in web): (cheie, pictograma, titlu, rand); apar primele
# AVANTAJE_ARATATE adevarate pe receptorul lui (cheile canal_testeri, forum, asistenta numai daca exista modulul)
AVANTAJE = (
	("canal_testeri", "actualizare", N_("Primești versiunile noi înaintea tuturor"),
		N_("Din meniul testerului alegi să primești întâi versiunile pentru testeri.")),
	("forum", "traducere", N_("Scrii pe forumul receptorului, cu capturi de ecran"),
		N_("Forumul traduce singur mesajele pentru fiecare cititor.")),
	("asistenta", "conexiune", N_("La o problemă, ne lași să ne uităm la receptor, cât vrei tu"),
		N_("Asistența de la distanță: o pornești tu și o oprești oricând.")),
	("date", "noutati", N_("Imaginea merge mai bine pe modelul tău"),
		N_("Trimiți date anonime, numai cele bifate de tine.")),
	("raspunsuri", "informatii", N_("Echipa îți răspunde la mesaje"),
		N_("Greșeli, idei, întrebări: răspunsul vine în meniul testerului.")),
)
AVANTAJE_ARATATE = 3


def avantaje(exista):
	"""Avantajele adevarate pe acest receptor, traduse: [(cheie, pictograma, titlu, rand)], cel mult AVANTAJE_ARATATE.
	exista = {cheie: bool} pentru avantajele legate de un modul (canal_testeri, forum, asistenta)."""
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
	try:
		return int(_b(None).nota.value)
	except Exception:
		return 0


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
	if config is None:
		from Components.config import config
	if "hds_beta" in config.content.items:
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
	return b


def _b(b=None):
	return b if b is not None else initConfig()


def salveaza(b=None):
	"""Setarile pe disc pe loc (o cadere nu face intrebarea sa apara din nou)."""
	b = _b(b)
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
	return bool(b.activ.value) and idValid(b.id.value) and int(b.nota.value) >= NOTA


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
	proba = (_citesteText(CALE_SERVER_PROBA, 256) or "").strip()
	if proba.startswith("http://") and serverValid(proba):
		return proba if proba.endswith("/") else proba + "/"
	adresa = (b.server.value or "").strip()
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
	return True, _t("Felicitări, ești beta tester. Datele bifate pleacă de acum.")


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


def iesire(b=None):
	"""„Iesi din program si sterge datele”: cererea de stergere intra prima in coada (si ramane pana ajunge), coada
	celorlalte pachete se goleste, setarile se fac ca din fabrica (intrebarea ramane raspunsa)."""
	b = _b(b)
	ident = b.id.value
	cheie = citesteCheie()
	if idValid(ident):
		golesteCoada()
		corp = {"v": PROTOCOL, "id": ident}
		puneInCoada("sterge", "sterge", corp)
	# forum-vazut.json: mesajele de pe forum vazute de tester (Components/HdsForumReceptor.FISIER_VAZUT)
	for nume in ("ultimul.json", "trimise.json", "raspunsuri.json", "stare.json", "cheie", "forum-vazut.json"):
		_sterge(cale(nume))
	b.activ.value = False
	b.id.value = ""
	b.nota.value = 0
	b.acord.value = ""
	b.acord_ora.value = False
	b.nume.value = ""
	b.email.value = ""
	b.public.value = ""
	b.automat.value = True
	for fel in FELURI:
		getattr(b, fel).value = True
	if b.intrebare.value == "":
		b.intrebare.value = "nu"
	salveaza(b)
	_jurnal("iesire din program%s" % (" (cu cheia profilului stearsa)" if cheie else ""))
	opresteCanalTesteri()
	_ceruteAcum["trimite"] = True
	_starea["numar_cand"] = None
	_starea["activ"] = False
	return True, _t("Ai ieșit din program. Cererea de ștergere pleacă la server; pe receptor nu mai rămâne nimic.")


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

# despre accesul conditionat, fara numele modulelor: orice cuvant terminat in „cam” / „camd” (cu cifre dupa), cartelele,
# ECM / EMM / CAID, interfetele CI, descifrarea, cuvintele de trei litere „?box” si protocoalele „cs123x”
_ACCES = re.compile(r"[a-z0-9]*cams?d?[0-9]*(?![a-z])|card|cartel|(?<![a-z])ecm|(?<![a-z])emm|caid|provid|"
	r"(?<![a-z])ca[_ ]?(?:pmt|info|service|handler|descr)|(?<![a-z])ci[0-9+_ ]|ci\+|ciplus|dvbapi|descifr|decript|"
	r"decrypt|descramb|scrambl|criptat|biss|(?<![a-z])cw(?![a-z])|(?<![a-z])[a-z]box(?![a-z])|(?<![a-z])cs[0-9]{3}x|"
	r"(?<![a-z])sc[0-9]|abonament|subscription|reader|keyserver", re.I)
_SECRET = re.compile(r"pass(?:word|wd)?|parol|(?<![a-z])psk|wpa|ssid|token|jeton|secret|(?<![a-z])key(?![a-z])|"
	r"apikey|api_key|(?<![a-z])pin(?![a-z])|cookie|authoriz|bearer|credential|cheie", re.I)
_IP4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IP6 = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}(?![0-9A-Fa-f:])")
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
	"""Textul unui jurnal fara nimic al omului: randurile despre accesul conditionat si cele cu parole, chei, jetoane,
	Wi-Fi scoase; adresele IP, MAC, e-mailurile, adresele web si caile spre filme inlocuite cu un semn."""
	rez = []
	for rand in (text or "").splitlines():
		if esteDeAcces(rand) or _SECRET.search(rand):
			continue
		rand = _URL.sub("<adresa>", rand)
		rand = _REF_IPTV.sub("<flux>", rand)
		rand = _EMAIL_TEXT.sub("<e-mail>", rand)
		rand = _MAC.sub("<mac>", rand)
		rand = _IP6.sub("<ip>", rand)
		rand = _IP4.sub(lambda m: m.group(0) if m.group(0).startswith(("0.", "127.")) else "<ip>", rand)
		rand = _FILM.sub("<fisier>", rand)
		rez.append(rand[:1000])
	return "\n".join(rez)


def coada(text, maxim=JURNAL_MAX):
	"""Ultima parte a unui text (eroarea e de obicei la sfarsit)."""
	if len(text) <= maxim:
		return text
	return "[...]\n" + text[-maxim:]


# ------------------------------------------------------------------ felul „jurnale”

_CDATA_JURNAL = re.compile(r"<enigma2crashlog>\s*<!\[CDATA\[(.*?)\]\]>", re.S)
_VERSIUNE_XML = re.compile(r"<version>(.*?)</version>", re.S)
_DATA_XML = re.compile(r"<crashdate>(.*?)</crashdate>", re.S)


def felJurnal(nume, text):
	"""(fel, text de trimis) pentru un jurnal din /home/root/logs: nucleu (scris de bsod), ecran (ecran cazut),
	actualizare, extensii, eroare."""
	if nume.startswith("enigma2_crash_"):
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
			parti.append(m.group(1))
		else:
			parti.append(text.split("<image>")[0])
		return "nucleu", "\n".join(parti)
	if nume.startswith("hds-actualizari") or nume.startswith("hds-actualizare"):
		return "actualizare", text
	if nume.startswith("hds-extensii"):
		return "extensii", text
	return "eroare", text


def jurnalPermis(nume):
	"""Jurnalele imaginii din /home/root/logs care pot pleca: cele de cadere si *.log; NU jurnalul sistemului (are
	adresele retelei si numele Wi-Fi) si nici jurnalele de depanare intregi."""
	if not nume or "/" in nume or nume.startswith("."):
		return False
	if nume.startswith("messages") or nume.startswith("syslog") or nume.startswith("Enigma2-debug"):
		return False
	if nume.startswith("enigma2_crash_") and nume.endswith(".log"):
		return True
	return nume.startswith("hds-") and nume.endswith(".log")


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
	ramase = max(0, maxim - int(stare.get("jurnale_azi", 0)))
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
	noi.sort(reverse=True)
	jurnale = []
	for mtime, nume, cale_fisier, semn in noi:
		if len(jurnale) >= ramase:
			break
		text = _citesteCoada(cale_fisier, 4 * JURNAL_MAX)
		if text is None:
			continue
		fel, text = felJurnal(nume, text)
		jurnale.append({"nume": nume[:120], "fel": fel, "scris": oraUtc(mtime), "text": coada(curata(text))})
		vazute[nume] = semn
	# numele care nu mai exista ies din stare
	for nume in list(vazute):
		if nume not in nume_fisiere:
			del vazute[nume]
	paznic = _randuriNoiPaznic(stare, cale_paznic or CALE_PAZNIC)
	if not jurnale and not paznic:
		return None
	stare["jurnale_azi"] = int(stare.get("jurnale_azi", 0)) + len(jurnale)
	return {"jurnale": jurnale, "paznic": paznic}


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
	text = _citesteCoada(c, 4 * JURNAL_MAX)
	if text is None:
		return None
	_fel, text = felJurnal(nume, text)
	return {"nume": nume[:120], "text": coada(curata(text))}


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
			text = f.read(16 * 1024 * 1024).decode("utf-8", "replace")
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


class Esantioane(object):
	"""Esantioanele din zi (in memorie, la ESANTION_S): memoria disponibila, incarcarea, temperatura, memoria
	interfetei. Dupa trimitere se iau de la capat."""

	def __init__(self):
		self.memorie = []
		self.incarcare = []
		self.temperatura = []
		self.rss_max = None

	def adauga(self, memorie_kb=None, incarcare=None, temperatura=None, rss_kb=None):
		if memorie_kb is not None:
			self.memorie.append(int(memorie_kb))
		if incarcare is not None:
			self.incarcare.append(float(incarcare))
		if temperatura is not None:
			self.temperatura.append(float(temperatura))
		if rss_kb is not None:
			self.rss_max = max(self.rss_max or 0, int(rss_kb))
		for lista in (self.memorie, self.incarcare, self.temperatura):
			del lista[:-200]

	def citeste(self, radacina=""):
		m = _meminfo(radacina)
		t = None
		try:
			from Components import HdsProcesor
			t = HdsProcesor.citesteTemperatura()[0]
		except Exception:
			t = None
		self.adauga(m.get("MemAvailable"), _incarcare(radacina), t, _rssInterfata(radacina))

	def gol(self):
		return not (self.memorie or self.incarcare or self.temperatura)


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
			"nuclee": nuclee},
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
			slot = {"slot": int(m.group(1)), "fel": "", "nume": ""}
			rez.append(slot)
		elif slot is not None and rand.startswith("Type:"):
			slot["fel"] = _txt(rand[5:], 40)
		elif slot is not None and rand.startswith("Name:"):
			slot["nume"] = _txt(rand[5:], 80)
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


def dateReceptor(model="", paza=None, radacina=""):
	"""Datele receptorului (felul „receptor”): fara serii, fara MAC, fara numele retelei, fara IP."""
	paza = paza or {}
	emmc, partitii = _partitii(radacina)
	dt = ""
	try:
		with open(_cale(radacina, "/proc/device-tree/compatible"), "rb") as f:
			dt = _txt(",".join(x.decode("ascii", "replace") for x in f.read(512).split(b"\0") if x))
	except (OSError, IOError):
		dt = ""
	return {
		"placa": {"machinebuild": model, "cip": paza.get("cip", ""), "boxtype": paza.get("boxtype", ""), "dt": dt,
			"procesor": _procesor(radacina), "nuclee": _nuclee(radacina)},
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


def dosarCoada():
	return cale("coada")


def citesteStare():
	with _LACAT:
		return citesteJson(cale("stare.json"), {}) or {}


def scrieStare(stare):
	with _LACAT:
		try:
			scrieJson(cale("stare.json"), stare)
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


def _fisiereCoada():
	try:
		return sorted(x for x in os.listdir(dosarCoada()) if x.endswith(".gz"))
	except OSError:
		return []


def puneInCoada(ruta, fel, corp, limita=PACHET_MAX):
	"""Pachetul in coada: `ruta` = acord, date, mesaj, sterge. Peste limita pachetului nu intra (rand in jurnal);
	peste COADA_MAX sau COADA_OCTETI pleaca intai cele mai vechi (nu si stergerea). -> numele fisierului sau None."""
	brut, gz = comprima(cuAmprenta(corp))
	if len(gz) > limita:
		_jurnal("pachetul %s are %d octeti comprimat, peste %d: nu pleaca" % (fel, len(gz), limita))
		adaugaTrimis(fel, len(gz), "refuzat")
		return None
	with _LACAT:
		_asiguraDosar(dosarCoada())
		nume = "%013d-%s-%s.gz" % (int(time.time() * 1000), ruta, fel)
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


def golesteCoada():
	with _LACAT:
		for f in _fisiereCoada():
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
		self.server = server
		self.posteaza = posteaza or _posteazaHttp
		self.rezultate = []

	def trimite(self):
		"""-> (cate au plecat, oprit_pana_mai_tarziu)."""
		fisiere = _fisiereCoada()
		fisiere.sort(key=lambda f: (0 if "-sterge-" in f else 1, f))
		plecate = 0
		for f in fisiere:
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
				continue
			try:
				cod, raspuns = self.posteaza(self.server + ruta, gz)
			except Exception as e:
				_jurnal("trimiterea %s: %s" % (f, _mesajEroare(e)))
				return plecate, True
			ce, motiv = hotarareRaspuns(cod, raspuns)
			if ce == MAI_TARZIU:
				_jurnal("serverul a raspuns %s la %s: incerc mai tarziu" % (cod, f))
				return plecate, True
			_sterge(cale_fisier)
			if ce == TRIMIS:
				plecate += 1
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
				d = dateReceptor(inst["model"], inst["paza"], radacina)
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

	def run(self):
		try:
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
				chei = ("jurnale", "jurnale_zi", "jurnale_azi", "paznic", "canale_semn", "receptor_suma", "probe_suma",
					"ultim")
				auto = self.auto_zilnic

				def uneste(s):
					for cheie in chei:
						if cheie in stare:
							s[cheie] = stare[cheie]
					if auto:
						s["ultim_auto"] = int(time.time())
				schimbaStare(uneste)
			if self.trimite_ and not coadaGoala():
				t = Trimitere(inst["server"], self.posteaza)
				_plecate, self.mai_tarziu = t.trimite()
				self.rezultate.extend(t.rezultate)
		except Exception as e:
			_jurnal("firul de lucru: %s" % e)


class Cerere(threading.Thread):
	"""O cerere directa la server (raspunsuri, profil, legare), fara coada: .gata, .cod, .raspuns (dict)."""

	def __init__(self, server, ruta, corp, posteaza=None):
		threading.Thread.__init__(self, name="hds-beta-cerere")
		self.daemon = True
		self.url = server + ruta
		self.corp = corp
		self.posteaza = posteaza or _posteazaHttp
		self.gata = False
		self.cod = 0
		self.raspuns = {}
		self.eroare = ""

	def run(self):
		try:
			_brut, gz = comprima(self.corp)
			self.cod, octeti = self.posteaza(self.url, gz)
			self.raspuns = _json(octeti)
		except Exception as e:
			self.eroare = _mesajEroare(e)
			_jurnal("cererea %s: %s" % (self.url.rsplit("/", 1)[-1], self.eroare))
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


def capturaOsd(latime=CAPTURA_LATIME):
	"""Captura numai a meniurilor (grab -o: fara imaginea canalului), JPEG, cel mult CAPTURA_MAX; sau None."""
	try:
		import subprocess
		p = subprocess.run(["grab", "-q", "-s", "-o", "-j", "80", "-r", str(latime)], stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL, timeout=20)
		date = p.stdout
		if p.returncode == 0 and date[:2] == b"\xff\xd8" and len(date) <= CAPTURA_MAX:
			return date
		if len(date) > CAPTURA_MAX:
			p = subprocess.run(["grab", "-q", "-s", "-o", "-j", "60", "-r", "640"], stdout=subprocess.PIPE,
				stderr=subprocess.DEVNULL, timeout=20)
			if p.returncode == 0 and p.stdout[:2] == b"\xff\xd8" and len(p.stdout) <= CAPTURA_MAX:
				return p.stdout
	except Exception as e:
		_jurnal("captura: %s" % e)
	return None


def citesteRaspunsuri():
	return citesteJson(cale("raspunsuri.json"), {}) or {}


def tineRaspunsuri(raspuns):
	"""Raspunsul serverului la `raspunsuri`, tinut pe receptor (cu ce a vazut omul pana acum)."""
	vechi = citesteRaspunsuri()
	mesaje = [m for m in (raspuns.get("mesaje") or []) if isinstance(m, dict)][:50]
	try:
		scrieJson(cale("raspunsuri.json"), {"cand": oraUtc(), "mesaje": mesaje, "vazute": vechi.get("vazute") or {}})
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
	c = citesteCheie()
	if c:
		return c
	c = os.urandom(32).hex()
	try:
		scrieAtomic(cale("cheie"), c.encode("ascii"), 0o600)
	except (OSError, IOError) as e:
		_jurnal("cheia profilului: %s" % e)
	return c


def corpProfil(ruta, b=None, **campuri):
	"""Corpul unei cereri de profil (profil, profil-stare, cod-legare, leaga, dezleaga)."""
	b = _b(b)
	corp = cuAmprenta({"v": PROTOCOL, "id": b.id.value, "cheie": cheieProfil()})
	corp.update(campuri)
	return corp


def cerereProfil(ruta, b=None, posteaza=None, **campuri):
	"""Porneste cererea (pe fir) si o intoarce; ecranul sau pagina asteapta .gata."""
	b = _b(b)
	if not inscris(b):
		return None
	c = Cerere(adresaServer(b), ruta, corpProfil(ruta, b, **campuri), posteaza)
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
	"numar_cand": None, "cerere_numar": None, "fir_model": None, "legare_forum": False}


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


def legareForum():
	"""Drumurile cu e-mail si cu contul de pe forum se arata numai cand serverul spune ca le are („legare_forum”:
	true in raspunsul `stare`); pana atunci numai numele public."""
	return bool(_starea.get("legare_forum"))


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
	return textUltimaTrimitere(citesteStare().get("ultima_trimitere"))


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
	# esantioanele felului „sistem”
	if _starea["ultim_esantion"] is None or acum - _starea["ultim_esantion"] >= ESANTION_S:
		_starea["ultim_esantion"] = acum
		_starea["es"].citeste()
	if notaVeche(b):
		return
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


def _dupaIntrebare(raspuns):
	raspundeIntrebarii(bool(raspuns))
	if raspuns:
		try:
			from Screens.HdsBetaTester import HdsBetaAcord
			_starea["sesiune"].open(HdsBetaAcord)
		except Exception as e:
			_jurnal("ecranul acordului: %s" % e)

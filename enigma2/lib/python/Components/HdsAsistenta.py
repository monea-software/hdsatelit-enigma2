# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistenta.py: "Asistenta de la distanta", versiunea 1, pentru oricine. Oprita din fabrica; nu ruleaza nimic,
# nicio cheie, nicio legatura pana nu o porneste omul: Meniu > Setari > Asistenta de la distanta (ecranul
# Screens/HdsAsistenta.py: o pagina cu randul bifat "Accept termenii și condițiile" si Start) sau din pagina web
# /asistenta (aceeasi pagina). O singura logica pentru receptor si pentru web.
# Modelul vine din Tools.HardwareInfo, versiunea din programul de testeri,
# fara sa ceara inscrierea in program. Din 0.6.21 se trimit
# si amprenta receptorului, iar la un beta tester inscris si inscrierea (8 cifre) si numele (_cine, spuse in
# informare: TEXT_CINE), ca echipa sa stie cine cere ajutor.
#
# Cum merge (fara tunel, fara shell): dupa consimtamant, receptorul se inregistreaza prin HTTPS la serverul HD Satelit,
# primeste un cod de 6 cifre si intreaba din cateva in cateva secunde daca are o cerere. Codul ramane intern, intre
# receptor, server si echipa (serverul trimite echipei un anunt cu el si cu "Cu ce te ajutam?"); omului nu i se arata
# nicaieri. O cerere e numai una din catalogul fix (Components/HdsAsistentaCatalog.py), SEMNATA cu cheia noastra;
# cheia publica sta in pachet (CHEI_ASISTENTA), nu vine de la server, deci un server spart nu poate cere nimic.
# Fiecare cerere si raspuns apar pe ecranul omului (jurnalul sesiunii) si in web. Pe receptor se scriu numai dosarul
# temporar al sesiunii (jurnalul) si fisierul ei de stare (STARE_FISIER), sterse amandoua la oprire, si (din 0.6.21)
# copia setarilor facuta cand intra echipa (DOSAR_COPIE, „Pune înapoi cum era”, ramane dupa oprire). Durata: 2 ore
# implicit, pana la o luna, sau permanent (de pe pagina de pornire: DURATA_IMPLICITA_MIN); echipa intra oricand cat e
# pornita (codul nu are termen de aprobare). Se opreste oricand (o tasta, pagina web, banda din web) si singura la
# sfarsitul duratei alese (niciodata la "permanent").
#
# Cererea semnata: octetii EXACTI ai JSON-ului {"args":[...],"id":...,"op":...,"seq":N} (chei sortate, fara spatii),
# semnati pe PC cu cheia operator, stocati verbatim pe server, verificati aici cu Components/HdsSemnatura.verifica
# (scop „asistenta-cerere"), apoi parsati. Receptorul refuza: id != id-ul sesiunii, seq <= ultimul vazut, op in afara
# catalogului, argumente care pica tiparul. Fara termen pe ceasul receptorului (id de sesiune + seq ajung impotriva
# reluarii unei cereri vechi).
#
# Firul: inregistrarea, intrebarea serverului si rularea operatiilor merg pe un fir separat, ca sa nu tina interfata;
# serverul se intreaba des (PAS_INTREBARE_S) cat e ceva de facut si rar (PAS_RAR_S) dupa ACTIV_S fara nimic, ca o
# asistenta pornita o luna sau permanent sa nu incarce reteaua. Starea sesiunii (id, secretul de la server, ora de
# sfarsit) sta in STARE_FISIER, pe disc: dupa o repornire a interfetei SAU a receptorului intreg, mytest.py reia firul
# cu aceeasi durata si aceeasi ora de sfarsit, iar semnul reapare (nimic pornit din fabrica: fisierul exista numai cat
# omul a pornit-o). Partea de sus nu importa nimic din enigma2: probele de pe PC dau stratul HTTP (_RETEA) si ceasul
# (_acum, _oraPerete) lor.

import base64
import gzip
import json
import os
import re
import shutil
import threading
import time

from Components import HdsAsistentaCatalog as Catalog
from Components import HdsAsistentaBroker as Broker

try:
	from Components import HdsSemnatura
except Exception:
	HdsSemnatura = None


# ---------------------------------------------------------------- cheile noastre si serverul

# cheile publice HD Satelit (Ed25519) cu care se semneaza cererile Asistentei; vin in pachet, se schimba prin
# actualizare (o cheie noua sau o revocare = un rand aici). Partea privata a cheii operatorului sta numai pe
# calculatorul echipei (unelte/asistenta/fa_chei_operator.py), niciodata in depozit, in imagine sau pe server.
CHEI_ASISTENTA = (
	("2b7f1de656d7370f", "1725406d53f66fbc6a78f2d461e42786d4da33b698cd467f7afd4318c1664291", "principala"),
)
REVOCATE_ASISTENTA = ()
SCOP_CERERE = "asistenta-cerere"

SERVER = "https://stb.hdsatelit.com/asistenta/v1/"
# jurnalul sesiunii (in memorie si aici; se sterge la oprire)
DOSAR_SESIUNE = "/tmp/hds-asistenta"
# starea sesiunii pornite (id, secretul de la server, durata, ora de sfarsit), 0600, ca asistenta pornita pentru mult
# timp sau permanent sa ramana pornita si dupa repornirea receptorului; se sterge la oprire
DOSAR_STARE = "/home/root/hds-asistenta"
STARE_FISIER = os.path.join(DOSAR_STARE, "stare.json")
# concluziile echipei (op "concluzii"): ultimele primite, cu ora si sesiunea; raman dupa oprire, ca omul sa le
# poata reciti (ecranul asistentei si pagina web); fiecare concluzie noua o inlocuieste pe cea de dinainte
CONCLUZII_FISIER = os.path.join(DOSAR_STARE, "concluzii.json")
CONCLUZII_MAX = 2000
# „Pune înapoi cum era” (0.6.21): copia setarilor (Components/HdsCopieSetari.fa_copia) facuta o data pe sesiune, cand
# echipa intra (starea "conectat"), inaintea primei cereri, aici, in memoria receptorului (in afara DOSAR_STARE). O
# singura copie de asistenta pe receptor: dosarul intreg se sterge inaintea celei noi. Ramane dupa oprire, ca omul sa
# poata pune setarile inapoi oricand (ecranul asistentei si pagina web); punerea o face enigma2.sh
# (HdsCopieSetari.pornire, care verifica toata copia) la repornirea interfetei. Pachetele instalate sau scoase in
# sesiune NU intra in v1: le scoate echipa, cu op "dezinstaleaza".
DOSAR_COPIE = "/home/root/hds-asistenta-copie"
IMAGE_VERSION = "/etc/image-version"

PROTOCOL = 1
# versiunea textului de informare aratat omului (scrisa in prima linie a jurnalului sesiunii); se schimba odata cu el
# Regula curenta: toate meniurile sunt vizibile; valorile conturilor nu pleaca spre echipa.
# v8 (0.6.21): informarea spune si ce trimite _cine (TEXT_CINE)
VERSIUNE_TEXT = 9
# durate alese de om (minute): 2 ore (implicit), 12 ore, o zi, o saptamana, o luna, permanent (DURATA_PERMANENTA:
# fara sfarsit, pana o opreste omul); serverul le primeste pe toate (si pe cele vechi, 30 de minute pana la 4 ore)
DURATA_PERMANENTA = 0
DURATE_MIN = (120, 720, 1440, 10080, 43200, DURATA_PERMANENTA)
DURATA_IMPLICITA_MIN = 120
# B: asistenta completa (citirile, probele si controlul: tastele telecomenzii, textul in campuri, setarile, canalele,
# instalarile din feed, repornirea), singura care se porneste din 0.6.16 (citirea fara control e a programului Beta
# tester); A ("numai citiri") ramane numai pentru o sesiune reluata dintr-un fisier de stare vechi
NIVELE = ("A", "B")
NIVEL_PORNIRE = "B"
PAS_INTREBARE_S = 3                    # cat de des intreaba serverul cat e ceva de facut
PAS_RAR_S = 30                         # cat de des, dupa ACTIV_S fara nicio cerere (asistenta pornita mult timp)
ACTIV_S = 10 * 60
TIMP_CERERE_S = 20
RASPUNS_SERVER_MAX = 512 * 1024
TIMP_DNS_PORNIRE_S = 2
TIMP_HTTPS_PORNIRE_S = 3

# starile sesiunii
OPRIT, VERIFICARE, INREGISTRARE, ASTEAPTA, CONECTAT, SE_OPRESTE = (
	"oprit", "verificare", "inregistrare", "asteapta", "conectat", "se-opreste")


def _jurnal(text):
	print("[HdsAsistenta] %s" % text)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


TEXT_VERIFICA = N_("Se verifică legătura pentru asistență...")
TEXT_SETARI_INTERNET = N_("Setările de internet")
ERORI_PORNIRE = {
	"retea": N_("Asistența nu poate porni: receptorul nu are internet. "
		"Verifică setările rețelei."),
	"cablu": N_("Asistența nu poate porni: cablul de rețea nu este conectat. "
		"Verifică și routerul."),
	"wifi": N_("Asistența nu poate porni: receptorul nu este conectat la Wi-Fi. "
		"Verifică rețeaua Wi-Fi și parola."),
	"dns": N_("Asistența nu poate porni: receptorul nu poate afla "
		"adresa stb.hdsatelit.com (DNS). "
		"Verifică setările de internet."),
	"server": N_("Asistența nu poate porni: serverul HD Satelit are o problemă temporară. "
		"Încearcă din nou mai târziu."),
	"internet": N_("Asistența nu poate porni: receptorul nu ajunge la serverul HD Satelit. "
		"Verifică internetul și încearcă din nou."),
	"https": N_("Asistența nu poate porni: legătura sigură HTTPS a fost refuzată. "
		"Verifică data și ora receptorului; dacă sunt corecte, încearcă mai târziu."),
	"refuz": N_("Asistența nu poate porni: serverul HD Satelit a refuzat cererea. "
		"Încearcă din nou mai târziu."),
}


# Informarea, aceeasi pe televizor si in web: accesul echipei, protejarea conturilor, pastrarea datelor si oprirea.
INFORMARE = N_(
	"Asistența de la distanță îi lasă pe oamenii de la HD Satelit să vadă, prin internet, starea tehnică a "
	"receptorului tău, ca să găsească și să repare mai repede defectele imaginii pe modelul tău.\n"
	"\n"
	"Este numai pentru cine vrea să ne ajute. Nu e nevoie de ea ca receptorul să meargă. Este oprită până o "
	"pornești tu, de fiecare dată din nou.\n"
	"\n"
	"Cum merge: receptorul tău întreabă serverul HD Satelit, printr-o legătură criptată, dacă avem o cerere "
	"pentru el. Asistența e completă: echipa HD Satelit vede ecranele, setările și imaginea canalului și poate "
	"controla receptorul prin toate meniurile, inclusiv cele ale modulelor de acces. Numele de utilizator, parolele, "
	"PIN-urile și cheile nu ajung la echipă. Înainte să scrii o parolă sau o cheie, oprește asistența. O poți porni "
	"din nou după ce salvezi. Poți opri oricând.\n"
	"\n"
	"Cât timp e pornită vezi un semn pe ecran. O oprești oricând de aici sau din pagina web, iar după timpul ales "
	"se oprește singură.\n"
	"\n"
	"Ce date ajung la noi: modelul și versiunea receptorului, țara, ora și durata sesiunii și răspunsurile la "
	"cererile din jurnal (jurnalele pot arăta, între altele, ce canale s-au deschis și când). Nu păstrăm adresa "
	"ta de internet. Nu citim parole, chei, setări ale cartelelor de acces sau fișierele tale. Datele stau pe "
	"serverul nostru (Hetzner, Germania; legătura trece prin Cloudflare) 30 de zile, apoi se șterg. Le folosim "
	"numai ca să reparăm imaginea și nu le dăm altora.\n"
	"\n"
	"Operatorul datelor: Monea Eduard (HD Satelit), contact@hdsatelit.com. Ne poți cere oricând să vezi sau să "
	"ștergem datele sesiunii tale. Folosește funcția numai dacă ai cel puțin 16 ani sau ai acordul unui părinte.")


# despre durata, pus dupa paragraful "Cât timp e pornită..." al informarii (in web si pe receptor)
TEXT_DURATE = N_("Start o pornește pentru 2 ore. O oprești oricând, de pe receptor sau din pagina web. Cât e "
	"pornită, echipa poate intra oricând, dar face numai ce e în lista fixă.")

# cine cere ajutor (din 0.6.21, _cine): pus dupa paragraful "Ce date ajung la noi..." al informarii, inaintea
# operatorului datelor (in web si pe receptor); aceleasi cuvinte despre amprenta ca nota testerilor (NOTA_SCURTA)
TEXT_CINE = N_("Ca să știm ce receptor cere ajutor, trimite și o amprentă calculată din placă, aceeași ca la "
	"programul de beta testeri (din ea nu se pot afla adresa MAC sau seria). Dacă ești beta tester, trimite și "
	"numele dat la înscriere sau, fără el, numele tău public.")

# Regula unica pentru pornire, informare si pagina web.
TEXT_CUM_MERGE = N_(
	"Echipa HD Satelit vede ecranele, setările și imaginea canalului și poate controla receptorul prin toate meniurile. "
	"Numele de utilizator, parolele, PIN-urile și cheile nu ajung la echipă. Oprește asistența cât scrii o parolă sau "
	"o cheie, până o salvezi. Poți opri oricând.")


def textInformare():
	parti = _t(INFORMARE).split("\n\n")
	parti.insert(min(4, len(parti)), _t(TEXT_DURATE))
	# inaintea ultimului paragraf (operatorul datelor), deci dupa "Ce date ajung la noi..."
	parti.insert(max(len(parti) - 1, 0), _t(TEXT_CINE))
	return "\n\n".join(parti)


# Pagina de pornire (pe receptor si in web): numai randul scurt TEXT_SCURT, randul bifat dinainte TEXT_ACCEPT si Start.
# Termenii si conditiile intregi (textTermeni) se deschid la cerere: OK pe rand (receptor) sau legatura din fraza (web).
TEXT_SCURT = TEXT_CUM_MERGE
# banda de sus cat echipa apasa taste sau scrie (op-urile de control)
TEXT_LUCREAZA = N_("HD Satelit lucrează acum pe receptorul tău")
# cat ramane banda "lucrează acum" dupa ultimul op de control (secunde)
LUCREAZA_S = 20
TEXT_ACCEPT = N_("Accept termenii și condițiile")
TEXT_TERMENI = N_("Termenii și condițiile")
TEXT_FARA_BIFA = N_("Fără bifă, asistența nu pornește.")
TEXT_NIVEL = TEXT_CUM_MERGE
TEXT_ACORD = N_("Cu rândul bifat, Start confirmă că ești de acord cu aceste condiții și că ai cel puțin 16 ani sau "
	"acordul unui părinte.")


def textTermeni():
	"""Textul intreg al termenilor si conditiilor (fereastra derulanta de pe receptor si din web): informarea, nivelul
	si ce confirma Start (varsta)."""
	return "\n\n".join((textInformare(), _t(TEXT_ACORD)))


# "Cu ce te ajutam?": optional, pe ecranul de pornire si in pagina web. Cheia aleasa (lista inchisa, aceeasi ca pe
# server: unelte/asistenta/asistenta_lib.NEVOI) si un rand de text liber se trimit serverului odata cu inregistrarea
# si ajung in anuntul echipei; fara alegere si fara text, cererea e exact cea de dinainte. NEVOIE_NIMIC ("") e
# alegerea implicita: omul apasa Verde si porneste, fara pasi in plus.
NEVOIE_NIMIC = ""
NEVOI = (
	("wifi", N_("Wi-Fi și rețea")),
	("imagine", N_("Imaginea sau sunetul")),
	("canale", N_("Canale și scanare")),
	("pornire", N_("Pornirea receptorului")),
	("altceva", N_("Altceva")),
)
TEXT_NEVOIE_NIMIC = N_("Nimic anume")
DETALII_MAX = 200
# caracterele de control si de formatare (si cele care intorc sensul scrisului): nu pleaca la server
_FARA_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff\ufff0-\ufffb"
	r"\ud800-\udfff]")


def alegeriNevoie():
	"""[(cheie, text tradus)] pentru ecranul de pornire si pentru pagina web; prima e "nimic anume" (implicita)."""
	return [(NEVOIE_NIMIC, _t(TEXT_NEVOIE_NIMIC))] + [(cheie, _t(text)) for cheie, text in NEVOI]


def curataNevoie(nevoie, detalii):
	"""(cheie, text) gata de trimis: o cheie din afara listei devine NEVOIE_NIMIC; textul: spatiile albe (si randurile
	noi) devin un spatiu, fara caractere de control sau de formatare, spatiile adunate, cel mult DETALII_MAX semne."""
	cheie = nevoie if isinstance(nevoie, str) and nevoie in dict(NEVOI) else NEVOIE_NIMIC
	if isinstance(detalii, bytes):
		detalii = detalii.decode("utf-8", "replace")
	text = detalii if isinstance(detalii, str) else ""
	text = "".join(" " if ch.isspace() else ch for ch in text[:DETALII_MAX * 4])
	text = " ".join(_FARA_CONTROL.sub("", text).split())[:DETALII_MAX].strip()
	return cheie, text


# duratele cu nume (restul in ore sau minute)
TEXTE_DURATE = {
	DURATA_PERMANENTA: N_("permanent"),
	1440: N_("o zi"),
	10080: N_("o săptămână"),
	43200: N_("o lună"),
}


def textDurata(minute):
	minute = int(minute)
	if minute in TEXTE_DURATE:
		return _t(TEXTE_DURATE[minute])
	if minute < 60:
		return _t("%d minute") % minute
	ore = minute // 60
	return _t("o oră") if ore == 1 else _t("%d ore") % ore


# pana cand e pornita, pe ecranul asistentei si in web (TEXT_PORNITA_*) si in benzile de sus (TEXT_BANDA_*)
TEXT_PORNITA_PANA = N_("Pornită până la %s.")
TEXT_PORNITA_PERMANENT = N_("Pornită, fără sfârșit; o poți opri oricând.")
TEXT_BANDA_PANA = N_("Asistență de la distanță pornită până la %s")
TEXT_BANDA_PERMANENT = N_("Asistență de la distanță pornită, fără sfârșit")


def oraSfarsit(moment):
	"""Ziua si ora de sfarsit, scurt ("ZZ.LL, HH:MM"), in ora receptorului."""
	return time.strftime("%d.%m, %H:%M", time.localtime(moment))


def textPana(ses, banda=False):
	"""Pana cand e pornita sesiunea ses: "Pornită până la ZZ.LL, HH:MM." sau, la permanent, "Pornită, fără sfârșit;
	o poți opri oricând." (banda=True: textele benzii de sus)."""
	if not getattr(ses, "id", True):
		return _t("Se oprește...") if ses.stare == SE_OPRESTE else _t(TEXT_VERIFICA)
	if ses.permanenta():
		return _t(TEXT_BANDA_PERMANENT if banda else TEXT_PORNITA_PERMANENT)
	pana = ses.pana_la_ora if ses.pana_la_ora is not None else _oraPerete() + ses.durata_min * 60
	return _t(TEXT_BANDA_PANA if banda else TEXT_PORNITA_PANA) % oraSfarsit(pana)


def drumMeniu(scurt=False):
	"""Calea de pe receptor spre ecran (pentru semnul de pe ecran si pentru pagina web), in limba receptorului: randul
	"Asistență de la distanță" din Setari, pentru oricine. scurt ramane pentru cine il da (calea e aceeasi)."""
	return " > ".join(_t(p) for p in ("Menu", "Settings", "Asistență de la distanță"))


# de ce s-a oprit o sesiune, pe intelesul omului (randul "oprită (...)" din jurnal); cheile sunt motivele din cod
MOTIVE_OPRIRE = {
	"de om": N_("de om"),
	"de om (web)": N_("din pagina web"),
	"fara-server": N_("serverul nu răspunde"),
	"inregistrare-refuzata": N_("înregistrare refuzată"),
	"termen": N_("s-a terminat timpul ales"),
	"respins": N_("cererea a fost respinsă"),
	"inchis": N_("cererea a fost închisă"),
	"expirat": N_("s-a terminat timpul ales"),
}

# de unde a pornit o sesiune, pe intelesul omului (randul "pornită (...)" din jurnal); cheile sunt valorile de_la
ORIGINI = {
	"televizor": N_("de pe receptor"),
	"web": N_("din pagina web"),
}


def textMotiv(motiv):
	"""Motivul opririi pentru jurnal: textul lui tradus, altfel (eroare: ...) cuvantul "eroare" tradus si numele."""
	if motiv in MOTIVE_OPRIRE:
		return _t(MOTIVE_OPRIRE[motiv])
	if motiv.startswith("eroare: "):
		return "%s: %s" % (_t("eroare"), motiv[len("eroare: "):])
	return motiv


def _acum():
	"""Ceasul (monoton), inlocuit in probe."""
	return time.monotonic()


def _oraPerete():
	return time.time()


def disponibil():
	"""Functia merge numai daca verificarea semnaturii se poate face pe receptor (python3-cryptography)."""
	if HdsSemnatura is None:
		return False
	try:
		import cryptography  # noqa: F401
		return True
	except Exception:
		return False


# ---------------------------------------------------------------- cererea semnata

def octetiCerere(id_sesiune, seq, op, args):
	"""Octetii canonici care se semneaza/verifica: JSON cu chei sortate, fara spatii, numai ASCII. Aceeasi functie e
	si in unealta de pe PC (unelte/asistenta/asistenta_lib.py); o proba verifica potrivirea octet cu octet."""
	obj = {"id": str(id_sesiune), "seq": int(seq), "op": str(op), "args": [str(a) for a in (args or [])]}
	return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def verificaCerere(exterior, id_sesiune, ultim_seq, chei=None, revocate=None):
	"""(bun, date, motiv): verifica o cerere transportata ({"c": base64(octeti), "s": textul .sig}). date e
	{"seq","op","args"} cand e buna. motiv (pentru jurnal) cand nu: forma, semnatura:<...>, alta-sesiune, seq-vechi,
	<motivul catalogului>."""
	if HdsSemnatura is None:
		return False, None, "fara-verificare"
	if not isinstance(exterior, dict):
		return False, None, "forma"
	b64 = exterior.get("c")
	sig = exterior.get("s")
	if not isinstance(b64, str) or not isinstance(sig, str):
		return False, None, "forma"
	try:
		octeti = base64.b64decode(b64.encode("ascii"), validate=True)
	except Exception:
		return False, None, "forma"
	if len(octeti) > 4096:
		return False, None, "forma"
	chei = CHEI_ASISTENTA if chei is None else chei
	revocate = REVOCATE_ASISTENTA if revocate is None else revocate
	bun, motiv, _id = HdsSemnatura.verifica(octeti, sig, SCOP_CERERE, chei=chei, revocate=revocate)
	if not bun:
		return False, None, "semnatura:" + motiv
	try:
		o = json.loads(octeti.decode("ascii"))
	except Exception:
		return False, None, "forma"
	if not isinstance(o, dict):
		return False, None, "forma"
	if str(o.get("id", "")) != str(id_sesiune):
		return False, None, "alta-sesiune"
	try:
		seq = int(o.get("seq"))
	except Exception:
		return False, None, "forma"
	if seq <= int(ultim_seq):
		return False, None, "seq-vechi"
	op = o.get("op")
	args = o.get("args", [])
	bun, mot = Catalog.valideaza(op, args)
	if not bun:
		return False, None, mot
	return True, {"seq": seq, "op": op, "args": list(args)}, ""


# ---------------------------------------------------------------- stratul HTTP (inlocuit in probe)

def _motivRetea(eroare):
	import socket
	import ssl
	from urllib.error import URLError
	if isinstance(eroare, URLError):
		eroare = eroare.reason
	if isinstance(eroare, socket.gaierror):
		return "dns"
	if isinstance(eroare, ssl.SSLError):
		return "https"
	return "internet"


def _inTermen(functie, secunde):
	# Rezolvarea DNS a sistemului poate astepta mult. Nu tine pornirea pe loc.
	gata = threading.Event()
	rezultat = []

	def lucru():
		try:
			rezultat.append((True, functie()))
		except Exception as e:
			rezultat.append((False, e))
		finally:
			gata.set()
	fir = threading.Thread(target=lucru, name="HdsAsistentaVerifica")
	fir.daemon = True
	fir.start()
	if not gata.wait(secunde):
		raise TimeoutError("verificarea a durat prea mult")
	bun, valoare = rezultat[0]
	if not bun:
		raise valoare
	return valoare


def _httpsPornire(adrese):
	import http.client
	import socket
	import ssl
	from urllib.parse import urlsplit
	url = urlsplit(SERVER)
	limita = _acum() + TIMP_HTTPS_PORNIRE_S
	context = ssl.create_default_context()
	ultima = None
	adrese = adrese[:3]

	def ramas():
		secunde = pana - _acum()
		if secunde <= 0:
			raise TimeoutError("verificarea a durat prea mult")
		return secunde

	# Foloseste adresa deja aflata, fara o a doua asteptare DNS.
	for index, (familie, tip, protocol, _nume, adresa) in enumerate(adrese):
		# O adresa care nu raspunde lasa timp si pentru celelalte.
		acum = _acum()
		pana = acum + (limita - acum) / (len(adrese) - index)
		conexiune = http.client.HTTPSConnection(url.hostname, timeout=ramas())
		brut = None
		try:
			brut = socket.socket(familie, tip, protocol)
			brut.settimeout(ramas())
			brut.connect(adresa)
			brut.settimeout(ramas())
			conexiune.sock = context.wrap_socket(brut, server_hostname=url.hostname)
			conexiune.sock.settimeout(ramas())
			# Numai antetele: nu deschide o sesiune si nu descarca o pagina.
			conexiune.request("HEAD", url.path or "/", headers={"User-Agent": "hdsatelit-receptor/1"})
			conexiune.sock.settimeout(ramas())
			raspuns = conexiune.getresponse()
			return raspuns.status
		except ssl.SSLError:
			raise
		except OSError as e:
			ultima = e
		finally:
			conexiune.close()
			if brut is not None:
				brut.close()
	if ultima is not None:
		raise ultima
	raise OSError("fara adrese")


def verificaPornire():
	"""Motiv scurt sau sir gol: reteaua, DNS si HTTPS, inainte de inregistrare."""
	import socket
	from urllib.parse import urlsplit
	from Components import HdsStareRetea as R
	legatura = R.legatura()
	if legatura.get("fizic") is False:
		return "wifi" if legatura.get("fel") == R.WIFI else "cablu"
	if R.fara_router_pasiv(legatura):
		return "retea"
	gazda = urlsplit(SERVER).hostname
	try:
		adrese = _inTermen(lambda: socket.getaddrinfo(gazda, 443, 0, socket.SOCK_STREAM), TIMP_DNS_PORNIRE_S)
		if not adrese:
			return "dns"
	except Exception:
		return "dns"
	try:
		cod = _inTermen(lambda: _httpsPornire(adrese), TIMP_HTTPS_PORNIRE_S)
		# Un server care nu accepta HEAD raspunde 405; HTTPS tot a reusit.
		return "server" if cod >= 500 or cod == 0 else ""
	except Exception as e:
		return _motivRetea(e)


_ultimaEroareHttp = threading.local()


def _posteazaHttp(url, metoda, corp_octeti, antete, timp=TIMP_CERERE_S):
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError
	h = {"User-Agent": "hdsatelit-receptor/1", "Accept": "application/json"}
	h.update(antete or {})
	cerere = Request(url, data=corp_octeti, method=metoda, headers=h)
	_ultimaEroareHttp.motiv = ""
	try:
		r = urlopen(cerere, timeout=timp)
		try:
			return r.getcode(), r.read(RASPUNS_SERVER_MAX)
		finally:
			r.close()
	except HTTPError as e:
		try:
			corp = e.read(65536)
		except Exception:
			corp = b""
		return e.code, corp
	except Exception as e:
		_ultimaEroareHttp.motiv = _motivRetea(e)
		_jurnal("retea: %s" % type(e).__name__)
		return 0, b""


# probele de pe PC pun aici functia lor
_RETEA = _posteazaHttp


def _ceruta(url, metoda, corp, antete):
	octeti = None
	if corp is not None:
		octeti = json.dumps(corp, ensure_ascii=False).encode("utf-8")
		antete = dict(antete or {})
		antete["Content-Type"] = "application/json"
	cod, raspuns = _RETEA(url, metoda, octeti, antete)
	try:
		o = json.loads((raspuns or b"").decode("utf-8")) if raspuns else {}
		if not isinstance(o, dict):
			o = {}
	except Exception:
		o = {}
	return cod, o


# ---------------------------------------------------------------- modelul si versiunea

def _beta():
	"""Components.HdsBetaTester (modelul si versiunea, la fel ca programul de testeri), sau None fara el."""
	try:
		from Components import HdsBetaTester
		return HdsBetaTester
	except Exception:
		return None


def _model():
	"""Acelasi model ca in rapoartele pluginurilor, fara numele vechi din driver."""
	from Tools.HardwareInfo import getModelName
	model = getModelName()
	if model != "unknown":
		return model
	# Rezerva pentru o sesiune care stie deja modelul, dar nu are fisierele.
	B = _beta()
	if B is not None:
		try:
			model = (B._modelTinut() or ("",))[0] or B.modelSiPaza()[0]
			if model:
				return str(model)[:40]
		except Exception as e:
			_jurnal("modelul: %s" % e)
	return "necunoscut"


def _versiuneImagine():
	"""Versiunea imaginii (ex. 0.6.10), aceeasi ca la programul de testeri; altfel randul version= din
	/etc/image-version."""
	B = _beta()
	if B is not None:
		try:
			v = B.versiuneImagine()
			if v:
				return str(v)[:40]
		except Exception as e:
			_jurnal("versiunea: %s" % e)
	try:
		with open(IMAGE_VERSION) as f:
			for rand in f:
				if rand.startswith("version="):
					return rand.split("=", 1)[1].strip()[:40]
	except Exception:
		pass
	return "necunoscut"


NUME_TESTER_MAX = 60


def _numePublic(b):
	"""Numele public al testerului: cel dat de forum, altfel cel tinut in setari (ca betatester_web.numeForum)."""
	try:
		from Components import HdsForumReceptor
		nume = HdsForumReceptor.numePublic()
	except Exception:
		nume = ""
	return nume or b.public.value or ""


def _cine():
	"""Cine cere ajutor, cu datele programului de testeri (Components/HdsBetaTester.py), spuse in informare
	(TEXT_CINE): "amprenta" = amprenta receptorului (PBKDF2 din MAC si CID, din care acestea nu se pot afla; aceeasi
	ca in pachetele testerilor, unde primele 8 cifre sunt „Receptorul”); la un beta tester inscris (programul pornit, cu
	acordul pe nota de acum) si "tester" = primele 8 cifre ale identificatorului inscrierii („Înscrierea”; identificatorul
	intreg e cheia lui la serverul testerilor si nu pleaca) si "nume" = numele dat la inscriere sau, fara el, numele
	public. Ce nu se poate afla lipseste; fara nimic, corpul e cel de dinainte. Pe firul sesiunii (amprenta se calculeaza
	o data pe proces)."""
	rez = {}
	B = _beta()
	if B is None:
		return rez
	try:
		amprenta = B.amprenta()
		if amprenta:
			rez["amprenta"] = str(amprenta)[:32]
	except Exception as e:
		_jurnal("amprenta: %s" % e)
	try:
		b = B.initConfig()
		if B.inscris(b):
			rez["tester"] = str(b.id.value)[:8]
			nume = B.textNume(b.nume.value, NUME_TESTER_MAX) or B.textNume(_numePublic(b), NUME_TESTER_MAX)
			if nume:
				rez["nume"] = nume
	except Exception as e:
		_jurnal("beta tester: %s" % e)
	return rez


# ---------------------------------------------------------------- jurnalul sesiunii (in memorie + dosar temporar)

class Jurnal(object):
	"""Randurile sesiunii, cu ora locala, in memorie (vazute pe TV si in web) si oglindite intr-un fisier din dosarul
	temporar al sesiunii; totul se sterge la oprire."""

	MAX_RANDURI = 500

	def __init__(self, dosar):
		self.randuri = []
		self.cale = os.path.join(dosar, "jurnal.log") if dosar else None
		self._lacat = threading.Lock()

	def adauga(self, text):
		rand = "%s  %s" % (time.strftime("%H:%M:%S"), text)
		with self._lacat:
			self.randuri.append(rand)
			if len(self.randuri) > self.MAX_RANDURI:
				self.randuri = self.randuri[-self.MAX_RANDURI:]
			if self.cale:
				try:
					with open(self.cale, "a", encoding="utf-8") as f:
						f.write(rand + "\n")
				except Exception:
					pass
		return rand

	def ultimele(self, n=40):
		with self._lacat:
			return list(self.randuri[-n:])


# ---------------------------------------------------------------- sesiunea si firul

class Sesiune(object):
	"""O sesiune de asistenta. Tine starea, codul, termenul, jurnalul si firul care intreaba serverul."""

	def __init__(self, nivel, durata_min, limba, server, de_la="televizor", versiune_text=VERSIUNE_TEXT, ctx=None,
			nevoie=NEVOIE_NIMIC, detalii=""):
		self.nivel = nivel if nivel in NIVELE else NIVEL_PORNIRE
		self.durata_min = int(durata_min) if int(durata_min) in DURATE_MIN else DURATA_IMPLICITA_MIN
		self.limba = (limba or "ro")[:8]
		self.server = server if server.endswith("/") else server + "/"
		self.de_la = de_la
		self.versiune_text = int(versiune_text)
		self.ctx = ctx or {}
		# "Cu ce te ajutam?": pleaca o singura data, la inregistrare (nu se tine in fisierul de stare)
		self.nevoie, self.detalii = curataNevoie(nevoie, detalii)
		self.id = None
		self.secret = None
		self.cod = None
		self.stare = OPRIT
		self.motiv_oprire = ""
		self.ultim_seq = 0
		self.pana_la_ora = None            # ora peretelui la care se opreste singura (None la permanent)
		self.copie_pentru = None           # id-ul sesiunii pentru care s-a incercat copia setarilor (_copia_inainte)
		self._activ = _acum()              # ultima data cand s-a intamplat ceva (pornire, conectare, cerere)
		self.dosar = None
		self.jurnal = None
		self._fir = None
		self._stop = threading.Event()
		self._lacat = threading.Lock()

	# -------- ajutoare de stare

	def permanenta(self):
		return self.durata_min == DURATA_PERMANENTA

	def ramasS(self):
		"""Secundele ramase pana la sfarsitul duratei alese; None la permanent."""
		if self.permanenta():
			return None
		if self.pana_la_ora is None:
			return self.durata_min * 60
		return max(0, int(self.pana_la_ora - _oraPerete()))

	def expirata(self):
		"""A trecut durata aleasa? (niciodata la permanent)"""
		return not self.permanenta() and self.ramasS() <= 0

	def activa(self):
		return self.stare in (VERIFICARE, INREGISTRARE, ASTEAPTA, CONECTAT)

	def _pas(self):
		"""Cat asteapta pana intreaba iar serverul: des cat e ceva de facut, rar dupa ACTIV_S fara nimic."""
		if _acum() - self._activ < ACTIV_S:
			return PAS_INTREBARE_S
		return max(PAS_INTREBARE_S, PAS_RAR_S)

	def _pune_stare(self, stare):
		self.stare = stare
		_anunta()

	# -------- pornire / oprire

	def porneste(self):
		self.dosar = os.path.join(DOSAR_SESIUNE, "s-%d" % int(_oraPerete()))
		try:
			os.makedirs(self.dosar, mode=0o700, exist_ok=True)
		except Exception:
			self.dosar = None
		self.jurnal = Jurnal(self.dosar)
		self.jurnal.adauga(_t(TEXT_VERIFICA))
		self._pune_stare(VERIFICARE)
		self._fir = threading.Thread(target=self._ruleaza, name="HdsAsistenta")
		self._fir.daemon = True
		self._fir.start()

	def opreste(self, motiv="de om"):
		self.motiv_oprire = motiv
		self._stop.set()
		self._pune_stare(SE_OPRESTE)

	def _curata(self):
		# anunta serverul si sterge dosarul temporar (cheia/jurnalul dispar)
		if self.id and self.secret:
			try:
				_ceruta(self.server + "inchide?id=" + self.id, "POST", {}, {"X-Secret": self.secret})
			except Exception:
				pass
		if self.dosar:
			try:
				shutil.rmtree(self.dosar, ignore_errors=True)
			except Exception:
				pass
		try:
			if os.path.exists(STARE_FISIER):
				os.remove(STARE_FISIER)
		except Exception:
			pass

	# -------- fisierul de stare (reluare dupa repornirea interfetei)

	def _scrie_stare(self):
		try:
			os.makedirs(os.path.dirname(STARE_FISIER), mode=0o700, exist_ok=True)
			nou = STARE_FISIER + ".nou"
			fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
			with os.fdopen(fd, "w", encoding="utf-8") as f:
				json.dump({"v": PROTOCOL, "id": self.id, "secret": self.secret, "server": self.server,
					"nivel": self.nivel, "durata_min": self.durata_min, "pana_la_ora": self.pana_la_ora,
					"ultim_seq": self.ultim_seq, "limba": self.limba, "dosar": self.dosar, "cod": self.cod,
					"asteapta": self.stare == ASTEAPTA, "copie": self.copie_pentru}, f)
			os.replace(nou, STARE_FISIER)
		except Exception:
			pass

	# -------- firul

	def _ruleaza(self):
		try:
			motiv = verificaPornire()
			if self._stop.is_set():
				return
			if motiv:
				self._esecPornire(motiv)
				return
			self._pune_stare(INREGISTRARE)
			if not self._inregistreaza():
				return
			if not self._asteapta_aprobare():
				return
			self._bucla_cereri()
		except Exception as e:
			_jurnal("firul: %s" % e)
			if not self.id:
				self._esecPornire(_motivRetea(e))
			else:
				self.opreste("eroare: %s" % type(e).__name__)
		finally:
			self.jurnal.adauga(_t("oprită (%s)") % textMotiv(self.motiv_oprire) if self.motiv_oprire else _t("oprită"))
			self._pune_stare(OPRIT)
			self._curata()
			_uita(self)

	def _esecPornire(self, motiv):
		global _eroare_pornire
		_eroare_pornire = motiv
		self.jurnal.adauga(_t(ERORI_PORNIRE.get(motiv, ERORI_PORNIRE["internet"])))
		self.opreste("fara-server")

	def _inregistreaza(self):
		corp = {"v": PROTOCOL, "model": _model(), "imagine": _versiuneImagine(), "nivel": self.nivel,
			"durata_min": self.durata_min, "limba": self.limba}
		# cine cere ajutor (amprenta; la un beta tester si inscrierea si numele), ca echipa sa stie al cui e receptorul
		corp.update(_cine())
		# campurile optionale numai cand omul a spus ceva: altfel corpul e cel de dinainte
		if self.nevoie:
			corp["nevoie"] = self.nevoie
		if self.detalii:
			corp["detalii"] = self.detalii
		cod, o = _ceruta(self.server + "inregistreaza", "POST", corp, {})
		if cod == 0 or cod >= 500 or cod == 404:
			motiv = getattr(_ultimaEroareHttp, "motiv", "") if cod == 0 else "server"
			self._esecPornire(motiv or "internet")
			return False
		if not (200 <= cod < 300) or not o.get("id") or not o.get("secret") or not o.get("cod"):
			self._esecPornire("refuz")
			return False
		self.id = str(o["id"])[:64]
		self.secret = str(o["secret"])[:128]
		self.cod = re.sub(r"\D", "", str(o["cod"]))[:6]
		self.pana_la_ora = None if self.permanenta() else _oraPerete() + self.durata_min * 60
		self.stare = ASTEAPTA
		self._scrie_stare()
		self._pune_stare(ASTEAPTA)
		self.jurnal.adauga(_t("pornită (%s, nivel %s, %d minute, text v%d)")
			% (_t(ORIGINI[self.de_la]) if self.de_la in ORIGINI else self.de_la,
			self.nivel, self.durata_min, self.versiune_text))
		self.jurnal.adauga(_t("cerere trimisă, aștept echipa"))
		return True

	def _asteapta_aprobare(self):
		# fara termen de aprobare: echipa intra oricand cat e pornita; se opreste numai la sfarsitul duratei alese
		while not self._stop.is_set():
			if self.expirata():
				self.jurnal.adauga(_t("s-a terminat timpul ales"))
				self.opreste("termen")
				return False
			cod, o = _ceruta(self.server + "stare?id=" + self.id, "GET", None, {"X-Secret": self.secret})
			stare = o.get("stare")
			if stare == "conectat":
				self._activ = _acum()
				self._pune_stare(CONECTAT)
				self._scrie_stare()
				self.jurnal.adauga(_t("conectat"))
				return True
			if stare in ("respins", "inchis", "expirat"):
				self.jurnal.adauga(textMotiv(stare))
				self.opreste(stare)
				return False
			self._asteapta_pas(self._pas())
		return False

	def _copia_inainte(self):
		"""O data pe sesiune, cand echipa a intrat, inaintea primei cereri: copia setarilor (faCopieAsistenta), pentru
		„Pune înapoi cum era”. Numai la nivelul B (A nu schimba nimic) si numai cu ctx-ul receptorului
		(Screens/HdsAsistentaSemn.ctxReceptor), care da ctx["setari_acum"]: settings de acum (config.pickle() pe firul
		enigma2); daca el nu raspunde la timp (None), fa_copia ia fisierul de pe disc. O sesiune reluata cu acelasi id
		(fisierul de stare, "copie") nu o mai face; copie_pentru se scrie dupa incercare, reusita sau nu, inaintea
		primei cereri: dupa ce echipa a schimbat ceva, o copie noua n-ar mai fi „cum era”. O copie ratata e numai un
		rand in jurnal; sesiunea merge mai departe."""
		if self.nivel != "B" or not self.id or self.copie_pentru == self.id or self._stop.is_set():
			return
		setari_acum = self.ctx.get("setari_acum")
		if setari_acum is None:
			return
		try:
			text = setari_acum()
			if text is not None and not isinstance(text, str):
				text = None
		except Exception as e:
			_jurnal("setarile de acum: %s" % type(e).__name__)
			text = None
		try:
			ok, motiv = faCopieAsistenta(text)
		except Exception as e:
			ok, motiv = False, type(e).__name__
		self.copie_pentru = self.id
		self._scrie_stare()
		if ok:
			self.jurnal.adauga(_t(TEXT_COPIE_FACUTA))
		else:
			self.jurnal.adauga(_t(TEXT_COPIE_RATATA) % motiv)

	def _bucla_cereri(self):
		# copia setarilor inaintea primei cereri (si la o sesiune reluata dupa repornire, daca n-a fost incercata)
		try:
			self._copia_inainte()
		except Exception as e:
			_jurnal("copia setarilor: %s" % type(e).__name__)
		while not self._stop.is_set():
			if self.expirata():
				self.jurnal.adauga(_t("s-a terminat timpul ales"))
				self.opreste("termen")
				return
			url = "%scereri?id=%s&dupa=%d" % (self.server, self.id, self.ultim_seq)
			cod, o = _ceruta(url, "GET", None, {"X-Secret": self.secret})
			if o.get("stare") in ("inchis", "expirat", "respins"):
				self.opreste(o.get("stare"))
				return
			for exterior in (o.get("cereri") or [])[:20]:
				if self._stop.is_set():
					break
				self._face_cerere(exterior)
				self._activ = _acum()
			self._asteapta_pas(self._pas())

	def _face_cerere(self, exterior):
		bun, date, motiv = verificaCerere(exterior, self.id, self.ultim_seq)
		if not bun:
			self.jurnal.adauga(_t("cerere refuzată: %s") % motiv)
			# o cerere cu seq nou dar refuzata nu trebuie sa blocheze: o sarim daca are un seq citibil. Mutam ultim_seq
			# dupa un seq NEVERIFICAT: in modelul cutiei postale asta nu slabeste apararea (un server rau poate oricum
			# sa nu livreze cereri); apararea impotriva reluarii e ca fiecare cerere e semnata cu id+seq si verificata.
			seq = _seq_din(exterior)
			if seq is not None and seq > self.ultim_seq:
				# si echipa afla ca a fost refuzata (altfel ar astepta un raspuns care nu vine niciodata): un raspuns scurt
				# cu motivul, numai pentru un seq nou (o cerere reluata nu primeste nimic)
				try:
					self._trimite_raspuns(seq, _op_din(exterior), Broker.Rezultat(1,
						text="(cerere refuzata de receptor: %s)" % motiv))
				except Exception as e:
					_jurnal("raspunsul la cererea refuzata: %s" % type(e).__name__)
				self.ultim_seq = seq
				self._scrie_stare()
			return
		seq, op, args = date["seq"], date["op"], date["args"]
		intrare = Catalog.gaseste(op)
		fel_cat = intrare["fel"] if intrare else ""
		fel = {"citire": _t("citire"), "control": _t("control")}.get(fel_cat, _t("probă"))
		eticheta = _t(intrare["text"]) if intrare else op
		if op == "taste" and args:
			# omul vede ce taste apasa echipa
			eticheta = "%s: %s" % (eticheta, args[0])
		elif op == "text" and args:
			eticheta = "%s: %s" % (eticheta, _t("%d semne") % len(args[0]))
		elif op == "citeste" and args:
			# omul vede ce fisier sau dosar citeste echipa
			eticheta = "%s: %s" % (eticheta, args[0])
		if fel_cat == "control" and self.nivel != "B":
			self.jurnal.adauga(_t("cerere refuzată: %s") % _t("control oprit"))
			rez = Broker.Rezultat(1, text=Broker.TEXT_FARA_CONTROL)
		else:
			self.jurnal.adauga("%s: %s" % (fel, eticheta))
			if fel_cat == "control":
				_ultimControl[0] = _acum()
			if op == "reporneste":
				# seq-ul se scrie INAINTE de repornire: sesiunea reluata dupa ea nu trebuie sa reporneasca din nou
				self.ultim_seq = seq
				self._scrie_stare()
			_anunta()
			rez = Broker.ruleaza(op, args, dict(self.ctx, nivel=self.nivel))
			if fel_cat == "control":
				_ultimControl[0] = _acum()
		self.jurnal.adauga(_t("    răspuns: cod %d, %d octeți") % (rez.cod_iesire, rez.marime()))
		self._trimite_raspuns(seq, op, rez)
		self.ultim_seq = seq
		self._scrie_stare()

	def _trimite_raspuns(self, seq, op, rez):
		if self._stop.is_set():
			return
		if rez.octeti is not None:
			date = rez.octeti
			tip = rez.tip
		else:
			date = (rez.text or "").encode("utf-8", "replace")
			tip = "text"
		gz = base64.b64encode(gzip.compress(date)).decode("ascii")
		corp = {"v": PROTOCOL, "seq": seq, "op": op, "cod_iesire": rez.cod_iesire, "tip": tip,
			"marime": len(date), "raspuns_gz": gz}
		self._ceruta_raspuns(corp)

	def _ceruta_raspuns(self, corp):
		if self._stop.is_set():
			return
		try:
			_ceruta(self.server + "raspuns?id=" + self.id, "POST", corp, {"X-Secret": self.secret})
		except Exception as e:
			_jurnal("raspuns: %s" % type(e).__name__)

	def _asteapta_pas(self, s):
		self._stop.wait(s)


# cand a rulat ultimul op de control (ceasul monoton): banda de sus arata TEXT_LUCREAZA cat timp e proaspat
_ultimControl = [None]


def lucreazaAcum():
	"""True cat echipa lucreaza pe receptor (un op de control in ultimele LUCREAZA_S secunde)."""
	t = _ultimControl[0]
	return t is not None and _acum() - t < LUCREAZA_S


def _seq_din(exterior):
	try:
		octeti = base64.b64decode((exterior or {}).get("c", "").encode("ascii"), validate=True)
		return int(json.loads(octeti.decode("ascii")).get("seq"))
	except Exception:
		return None


def _op_din(exterior):
	"""Numele op-ului dintr-o cerere NEVERIFICATA (numai pentru raspunsul de refuz), sau "?" cand nu are forma unui op."""
	try:
		octeti = base64.b64decode((exterior or {}).get("c", "").encode("ascii"), validate=True)
		op = json.loads(octeti.decode("ascii")).get("op")
	except Exception:
		return "?"
	return op if isinstance(op, str) and re.match(r"^[a-z][a-z0-9-]{0,31}\Z", op) else "?"


# ---------------------------------------------------------------- starea globala (o sesiune deodata) si observatorii

_sesiune = None
_eroare_pornire = ""
_observatori = []
_lacat = threading.Lock()


def _anunta():
	# observatorii ating interfata enigma2 (ferestre, eTimer, setText): enigma2 NU e sigur intre fire, deci chemam
	# observatorii NUMAI pe firul principal. Schimbarile facute de firul sesiunii se vad oricum: si banda, si ecranul
	# citesc starea la fiecare secunda din ceasul lor. Primul _anunta (INREGISTRARE) e inca pe firul principal (din
	# porneste(), inainte de pornirea firului), deci porneste ceasul benzii.
	if threading.current_thread() is not threading.main_thread():
		return
	for f in list(_observatori):
		try:
			f()
		except Exception:
			pass


def adaugaObservator(f):
	if f not in _observatori:
		_observatori.append(f)


def scoateObservator(f):
	if f in _observatori:
		_observatori.remove(f)


def _uita(ses):
	global _sesiune
	with _lacat:
		if _sesiune is ses:
			_sesiune = None
	_anunta()


def sesiune():
	return _sesiune


def porneste(nivel=NIVEL_PORNIRE, durata_min=DURATA_IMPLICITA_MIN, limba="ro", de_la="televizor", versiune_text=VERSIUNE_TEXT,
		ctx=None, nevoie=NEVOIE_NIMIC, detalii=""):
	"""(reusit, mesaj): porneste o sesiune daca nu merge deja una si daca functia e disponibila. Fara efect daca o
	sesiune e deja activa. nevoie/detalii: "Cu ce te ajutam?" (optionale, vezi curataNevoie)."""
	global _sesiune, _eroare_pornire
	if not disponibil():
		return False, _t("Funcția nu e disponibilă pe această imagine.")
	# asistenta porneste si cu pagina unui modul deschisa in navigator (captura e refuzata cat navigatorul e pe ecran,
	# deci echipa nu o vede)
	with _lacat:
		if _sesiune is not None and _sesiune.activa():
			return False, _t("Asistența merge deja.")
		_eroare_pornire = ""
		ses = Sesiune(nivel, durata_min, limba, SERVER, de_la=de_la, versiune_text=versiune_text, ctx=ctx,
			nevoie=nevoie, detalii=detalii)
		_sesiune = ses
	ses.porneste()
	return True, _t("Asistența a pornit.") if ses.id else _t(TEXT_VERIFICA)


def opreste(motiv="de om"):
	"""(reusit, mesaj): opreste sesiunea de acum, daca exista."""
	ses = _sesiune
	if ses is None or not ses.activa():
		return False, _t("Asistența nu merge.")
	ses.opreste(motiv)
	return True, _t("Asistența s-a oprit. Cheia a fost ștearsă.")


# ---------------------------------------------------------------- concluziile echipei (op "concluzii")

TEXT_CONCLUZII = N_("Ce am găsit și ce am făcut")
TEXT_MULTUMIM = N_("Mulțumim că ne-ai lăsat să te ajutăm.")
TEXT_ULTIMELE_CONCLUZII = N_("Ultimele concluzii")


def curataConcluzii(text):
	"""Textul concluziilor gata de aratat: randurile pastrate, fara caractere de control sau de formatare, spatiile
	de la capetele randurilor scoase, cel mult doua randuri goale la rand, cel mult CONCLUZII_MAX semne."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	if not isinstance(text, str):
		return ""
	randuri = []
	for rand in text[:CONCLUZII_MAX * 2].replace("\r\n", "\n").replace("\r", "\n").split("\n"):
		rand = " ".join(_FARA_CONTROL.sub("", rand.replace("\t", " ")).split())
		if not rand and randuri[-2:] == ["", ""]:
			continue
		randuri.append(rand)
	return "\n".join(randuri).strip()[:CONCLUZII_MAX].strip()


def salveazaConcluzii(text, id_sesiune=None):
	"""Scrie concluziile (curatate) in CONCLUZII_FISIER (0600) si intoarce intrarea {"text", "ora", "id"}, sau None
	cand textul e gol. Chemata de pe firul sesiunii (op "concluzii")."""
	text = curataConcluzii(text)
	if not text:
		return None
	if id_sesiune is None:
		ses = _sesiune
		id_sesiune = ses.id if ses is not None else None
	intrare = {"v": 1, "text": text, "ora": int(_oraPerete()), "id": id_sesiune}
	try:
		os.makedirs(os.path.dirname(CONCLUZII_FISIER), mode=0o700, exist_ok=True)
		nou = CONCLUZII_FISIER + ".nou"
		fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			json.dump(intrare, f, ensure_ascii=False)
		os.replace(nou, CONCLUZII_FISIER)
	except Exception as e:
		_jurnal("concluzii: %s" % e)
	return intrare


def ultimeleConcluzii():
	"""Ultimele concluzii primite ({"text", "ora", "id"}) sau None."""
	try:
		with open(CONCLUZII_FISIER, encoding="utf-8") as f:
			o = json.load(f)
	except Exception:
		return None
	if not isinstance(o, dict) or not isinstance(o.get("text"), str) or not o["text"].strip():
		return None
	try:
		ora = int(o.get("ora") or 0)
	except (TypeError, ValueError):
		ora = 0
	return {"text": curataConcluzii(o["text"]), "ora": ora, "id": o.get("id")}


def textConcluzii(intrare):
	"""Textul ferestrei: concluziile, apoi multumirile."""
	if not intrare:
		return ""
	return "%s\n\n%s" % (intrare.get("text") or "", _t(TEXT_MULTUMIM))


def stareConcluzii():
	"""Pentru pagina web: {"text", "ora_text"} sau None."""
	c = ultimeleConcluzii()
	if not c:
		return None
	return {"text": c["text"], "ora_text": oraSfarsit(c["ora"]) if c["ora"] else ""}


# ---------------------------------------------------------------- copia setarilor: „Pune înapoi cum era”

# tasta Albastra pe receptor si butonul din pagina web
TEXT_PUNE_INAPOI = N_("Pune înapoi cum era")
# ziua si ora copiei, sus in textul ecranului si in pagina web, cat exista copia (si dupa oprire)
TEXT_COPIE_DIN = N_("Copia setărilor făcută când a intrat echipa: %s.")
# randurile jurnalului sesiunii, dupa incercarea copiei
TEXT_COPIE_FACUTA = N_("copia setărilor făcută înainte de orice schimbare")
TEXT_COPIE_RATATA = N_("copia setărilor nu s-a putut face: %s")


def _copie():
	"""Components.HdsCopieSetari (copia, lista copiilor, cererea de punere la loc), sau None fara el; probele de pe PC
	pun modulul lor in sys.modules."""
	try:
		from Components import HdsCopieSetari
		return HdsCopieSetari
	except Exception as e:
		_jurnal("copia setarilor: %s" % e)
		return None


def mediuCopie():
	"""Locul copiei de asistenta, in forma mediilor lui HdsCopieSetari (copii(), cere_punerea): medii() da numai
	stickurile si discurile montate, deci acesta se da de aici."""
	return {"punct": DOSAR_COPIE, "id": DOSAR_COPIE, "fel": "disc", "eticheta": "", "dispozitiv": "",
		"actualizare": False, "nume": _t("Asistență de la distanță")}


# copia gasita (dictul lui HdsCopieSetari.copii), tinuta cat nu se schimba dosarul copiilor: stare() e chemata in
# fiecare secunda de ecran si la 3 secunde de pagina web
_copieTinuta = {"cheie": None, "copie": None}


def copieAsistenta():
	"""Copia setarilor facuta de asistenta ({"id", "data_text", "acest", ...} ca in HdsCopieSetari.copii), sau None."""
	C = _copie()
	if C is None:
		return None
	dosar = os.path.join(DOSAR_COPIE, *C.DOSAR_PE_MEDIU.split("/"))
	try:
		cheie = (os.stat(dosar).st_mtime_ns, tuple(sorted(os.listdir(dosar))))
	except OSError:
		_copieTinuta.update(cheie=None, copie=None)
		return None
	if cheie != _copieTinuta["cheie"]:
		lista = C.copii([mediuCopie()])
		_copieTinuta.update(cheie=cheie, copie=lista[0] if lista else None)
	return _copieTinuta["copie"]


def faCopieAsistenta(text_setari=None):
	"""Copia setarilor in DOSAR_COPIE, cu HdsCopieSetari.fa_copia (garda de spatiu a ei ramane: fara loc, nimic scris).
	Intai dosarul intreg se sterge (copia veche si un .part ramas dupa o cadere de curent), apoi se face din nou (0700:
	copia are parolele Wi-Fi). fel "automata": citeste_descriere arata orice alta valoare decat "automata" ca „făcută de
	mână”. Pe firul sesiunii. -> (ok, motiv scurt pentru jurnal)."""
	C = _copie()
	if C is None:
		return False, "HdsCopieSetari"
	_copieTinuta.update(cheie=None, copie=None)
	try:
		if os.path.islink(DOSAR_COPIE):
			os.remove(DOSAR_COPIE)
		shutil.rmtree(DOSAR_COPIE, ignore_errors=True)
		os.makedirs(DOSAR_COPIE, mode=0o700, exist_ok=True)
		rez = C.fa_copia(DOSAR_COPIE, text_setari, "automata")
	except Exception as e:
		_jurnal("copia setarilor: %s" % e)
		return False, type(e).__name__
	finally:
		_copieTinuta.update(cheie=None, copie=None)
	if isinstance(rez, dict) and rez.get("ok"):
		return True, ""
	mesaje = (rez.get("mesaje") if isinstance(rez, dict) else None) or ["?"]
	return False, str(mesaje[0]).strip().rstrip(".")


def stareCopie():
	"""Pentru ecran si pagina web: {"data_text", "text" (ziua si ora copiei), "intrebare" (aceeasi ca la „Copia
	setărilor”: HdsCopieSetari.text_intrebare_punere)} sau None cand nu e copie."""
	c = copieAsistenta()
	C = _copie()
	if c is None or C is None:
		return None
	return {"data_text": c.get("data_text", ""), "text": _t(TEXT_COPIE_DIN) % c.get("data_text", ""),
		"intrebare": C.text_intrebare_punere(c)}


def cerePunereaInapoi():
	"""„Pune înapoi cum era”: cererea de punere la loc a copiei de asistenta (HdsCopieSetari.cere_punerea). Repornirea
	interfetei o cere cel care cheama (ecranul sau pagina web, ca la „Copia setărilor”); copia o pune la loc enigma2.sh
	(HdsCopieSetari.pornire), fara cod nou de punere. Sesiunea nu se opreste: jurnalul ei spune ce s-a cerut, iar dupa
	repornire se reia singura (fisierul de stare ramane). -> (ok, mesaj)."""
	C = _copie()
	c = copieAsistenta()
	if C is None or c is None:
		return False, _t("Copia nu mai este pe mediu.")
	ok, mesaj = C.cere_punerea(c["id"], [c])
	ses = _sesiune
	if ok and ses is not None and ses.activa() and ses.jurnal is not None:
		ses.jurnal.adauga("%s: %s" % (_t(TEXT_PUNE_INAPOI), mesaj))
	return ok, mesaj


def _stareCopie():
	try:
		return stareCopie()
	except Exception as e:
		_jurnal("copia setarilor: %s" % e)
		return None


def stare():
	"""Starea pentru ecran si pentru pagina web; "copie": copia pentru „Pune înapoi cum era” (stareCopie) sau None."""
	ses = _sesiune
	if ses is None:
		return {"stare": OPRIT, "disponibil": disponibil(), "durate": list(DURATE_MIN),
			"eroare_pornire": _t(ERORI_PORNIRE.get(_eroare_pornire, "")),
			"durata_implicita": DURATA_IMPLICITA_MIN, "are_concluzii": ultimeleConcluzii() is not None,
			"copie": _stareCopie()}
	return {
		"copie": _stareCopie(),
		"are_concluzii": ultimeleConcluzii() is not None,
		"stare": ses.stare,
		"disponibil": True,
		"nivel": ses.nivel,
		"cod": ses.cod if ses.stare == ASTEAPTA else None,
		"ramas_s": ses.ramasS(),
		"permanent": ses.permanenta(),
		"pana_la": ses.pana_la_ora,
		"pana_text": textPana(ses),
		"jurnal": ses.jurnal.ultimele(40) if ses.jurnal else [],
		"durate": list(DURATE_MIN),
		"durata_implicita": DURATA_IMPLICITA_MIN,
	}


# ---------------------------------------------------------------- reluarea dupa repornirea interfetei

def reia(ctx=None):
	"""Chemat de mytest.py la pornirea interfetei: daca exista un fisier de stare cu ora de sfarsit inca nevenita (sau
	o sesiune permanenta), reia sesiunea cu aceeasi durata si aceeasi ora de sfarsit, si dupa o repornire a interfetei,
	si dupa una a receptorului intreg. Nu face niciun apel decat daca omul a pornit asistenta si n-a oprit-o
	(fisierul exista numai atunci)."""
	global _sesiune
	if _sesiune is not None:
		return
	try:
		with open(STARE_FISIER, encoding="utf-8") as f:
			s = json.load(f)
	except Exception:
		return
	if not s.get("id") or not s.get("secret"):
		return
	pana = s.get("pana_la_ora")
	if pana is not None and pana - _oraPerete() <= 0:
		try:
			os.remove(STARE_FISIER)
		except Exception:
			pass
		return
	try:
		durata = int(s.get("durata_min", DURATA_IMPLICITA_MIN))
	except (TypeError, ValueError):
		durata = DURATA_IMPLICITA_MIN
	if durata == DURATA_PERMANENTA and pana is not None:
		durata = DURATA_IMPLICITA_MIN          # o stare stricata nu face o sesiune permanenta
	ses = Sesiune(s.get("nivel", "A"), durata, s.get("limba", "ro"), s.get("server", SERVER),
		de_la="reluare", ctx=ctx)
	if pana is None and not ses.permanenta():
		pana = _oraPerete() + ses.durata_min * 60
	ses.id = s["id"]
	ses.secret = s["secret"]
	ses.ultim_seq = int(s.get("ultim_seq", 0))
	ses.pana_la_ora = pana
	# copia setarilor deja incercata pentru aceasta sesiune: nu se mai face (Sesiune._copia_inainte)
	ses.copie_pentru = s.get("copie") if isinstance(s.get("copie"), str) else None
	# dupa o repornire a receptorului intreg dosarul temporar al jurnalului nu mai exista: altul nou
	ses.dosar = s.get("dosar")
	if not ses.dosar or not os.path.isdir(ses.dosar):
		ses.dosar = os.path.join(DOSAR_SESIUNE, "s-%d" % int(_oraPerete()))
		try:
			os.makedirs(ses.dosar, mode=0o700, exist_ok=True)
		except Exception:
			ses.dosar = None
	ses.jurnal = Jurnal(ses.dosar)
	ses.jurnal.adauga(_t("reluată după repornire"))
	asteapta = bool(s.get("asteapta")) and bool(s.get("cod"))
	if asteapta:
		# repornirea a venit inainte de aprobare: codul ramane acelasi, receptorul asteapta mai departe
		ses.cod = re.sub(r"\D", "", str(s.get("cod")))[:6]
	with _lacat:
		_sesiune = ses
	ses._pune_stare(ASTEAPTA if asteapta else CONECTAT)
	ses._fir = threading.Thread(target=ses._bucla_dupa_reluare, name="HdsAsistenta")
	ses._fir.daemon = True
	ses._fir.start()


def _bucla_dupa_reluare(self):
	try:
		if self.stare == ASTEAPTA and not self._asteapta_aprobare():
			return
		self._bucla_cereri()
	except Exception as e:
		_jurnal("reluare: %s" % e)
		self.opreste("eroare: %s" % type(e).__name__)
	finally:
		self._pune_stare(OPRIT)
		self._curata()
		_uita(self)


Sesiune._bucla_dupa_reluare = _bucla_dupa_reluare

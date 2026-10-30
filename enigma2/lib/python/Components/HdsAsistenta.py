# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistenta.py: "Asistenta de la distanta", versiunea 1, pentru oricine. Oprita din fabrica; nu ruleaza nimic,
# nicio cheie, nicio legatura pana nu o porneste omul: Meniu > Setari > Asistenta de la distanta (ecranul
# Screens/HdsAsistenta.py: o pagina cu randul bifat "Accept termenii și condițiile" si Start) sau din pagina web
# /asistenta (aceeasi pagina). O singura logica pentru receptor si pentru web. Modelul si versiunea trimise serverului
# sunt cele ale programului de testeri (Components/HdsBetaTester.py), fara sa ceara inscrierea in program.
#
# Cum merge (fara tunel, fara shell): dupa consimtamant, receptorul se inregistreaza prin HTTPS la serverul HD Satelit,
# primeste un cod de 6 cifre si intreaba din cateva in cateva secunde daca are o cerere. Codul ramane intern, intre
# receptor, server si echipa (serverul trimite echipei un anunt cu el si cu "Cu ce te ajutam?"); omului nu i se arata
# nicaieri. O cerere e numai una din catalogul fix (Components/HdsAsistentaCatalog.py), SEMNATA cu cheia noastra;
# cheia publica sta in pachet (CHEI_ASISTENTA), nu vine de la server, deci un server spart nu poate cere nimic.
# Fiecare cerere si raspuns apar pe ecranul omului (jurnalul sesiunii) si in web. Pe receptor se scriu numai dosarul
# temporar al sesiunii (jurnalul) si fisierul ei de stare (STARE_FISIER), sterse amandoua la oprire. Durata: 2 ore
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
IMAGE_VERSION = "/etc/image-version"

PROTOCOL = 1
# versiunea textului de informare aratat omului (scrisa in prima linie a jurnalului sesiunii); se schimba odata cu el
# (5: randul "Control complet", nivelul B; 6: asistenta numai completa, fara rand de ales)
VERSIUNE_TEXT = 6
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

# starile sesiunii
OPRIT, INREGISTRARE, ASTEAPTA, CONECTAT, SE_OPRESTE = "oprit", "inregistrare", "asteapta", "conectat", "se-opreste"


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


# Textul de informare (consimtamantul), acelasi pe televizor si in web. Spune numai ce face versiunea 1 (fara tunel,
# fara comenzi): ce vedem, ce pastram si cat, cine primeste datele, cum opresti, varsta, contactul.
INFORMARE = N_(
	"Asistența de la distanță îi lasă pe oamenii de la HD Satelit să vadă, prin internet, starea tehnică a "
	"receptorului tău, ca să găsească și să repare mai repede defectele imaginii pe modelul tău.\n\n"
	"Este numai pentru cine vrea să ne ajute. Nu e nevoie de ea ca receptorul să meargă. Este oprită până o pornești "
	"tu, de fiecare dată din nou.\n\n"
	"Cum merge: receptorul tău întreabă serverul HD Satelit, printr-o legătură criptată, dacă avem o cerere pentru el. "
	"Putem cere numai operații dintr-o listă fixă, scrisă în imagine: citiri ale stării și ale jurnalelor, o captură a "
	"meniurilor și un mesaj scris pe ecran. Nu putem rula comenzi, nu putem schimba setări sau fișiere și nu putem "
	"ajunge la alte aparate din casa ta. Fiecare cerere apare în jurnal, pe ecran.\n\n"
	"Cât timp e pornită vezi un semn pe ecran. O oprești oricând de aici sau din pagina web, iar după timpul ales se "
	"oprește singură.\n\n"
	"Ce date ajung la noi: modelul și versiunea receptorului, țara, ora și durata sesiunii și răspunsurile la "
	"cererile din jurnal (jurnalele pot arăta, între altele, ce canale s-au deschis și când). Nu păstrăm adresa ta de "
	"internet. Nu citim parole, chei, setări ale cartelelor de acces sau fișierele tale. Datele stau pe serverul "
	"nostru (Hetzner, Germania; legătura trece prin Cloudflare) 30 de zile, apoi se șterg. Le folosim numai ca să "
	"reparăm imaginea și nu le dăm altora.\n\n"
	"Operatorul datelor: Monea Eduard (HD Satelit), contact@hdsatelit.com. Ne poți cere oricând să vezi sau să "
	"ștergem datele sesiunii tale. Folosește funcția numai dacă ai cel puțin 16 ani sau ai acordul unui părinte.")


# despre durata, pus dupa paragraful "Cât timp e pornită..." al informarii (in web si pe receptor)
TEXT_DURATE = N_("Start o pornește pentru 2 ore. O oprești oricând, de pe receptor sau din pagina web. Cât e "
	"pornită, echipa poate intra oricând, dar face numai ce e în lista fixă.")

# paragraful "Cum merge" al informarii, cu controlul (nivelul B); inlocuieste la afisare paragraful al treilea din
# INFORMARE (acela spune numai ce face nivelul A), ca restul textului sa ramana cu traducerile lui
TEXT_CUM_MERGE = N_("Cum merge: receptorul tău întreabă serverul HD Satelit, printr-o legătură criptată, dacă avem o "
	"cerere pentru el. Putem cere numai operații dintr-o listă fixă, scrisă în imagine: citiri ale stării, ale "
	"jurnalelor și ale textului de pe ecran, o captură a meniurilor, un mesaj scris pe ecran, tastele telecomenzii și "
	"textul din câmpuri, ca să mergem prin meniuri, să schimbăm setări, să căutăm canale și să instalăm din feedul "
	"oficial, ca și cum am ține telecomanda. Nu putem rula "
	"comenzi libere și nu putem ajunge la alte aparate din casa ta. Ecranele modulelor de acces, ale parolelor, ale "
	"accesului SSH, ale rețelei Wi-Fi și ale datelor tale personale rămân închise: acolo echipa nu vede nimic și poate "
	"doar ieși. Fiecare cerere apare în jurnal, pe ecran.")
# al catelea paragraf din INFORMARE e "Cum merge" (numaratoarea de la 0)
_PARAGRAF_CUM_MERGE = 2


def textInformare():
	parti = _t(INFORMARE).split("\n\n")
	if len(parti) > _PARAGRAF_CUM_MERGE:
		parti[_PARAGRAF_CUM_MERGE] = _t(TEXT_CUM_MERGE)
	parti.insert(min(4, len(parti)), _t(TEXT_DURATE))
	return "\n\n".join(parti)


# Pagina de pornire (pe receptor si in web): numai randul scurt TEXT_SCURT, randul bifat dinainte TEXT_ACCEPT si Start.
# Termenii si conditiile intregi (textTermeni) se deschid la cerere: OK pe rand (receptor) sau legatura din fraza (web).
TEXT_SCURT = N_("Echipa HD Satelit intră prin internet pe receptorul tău, ca să te ajute: poate naviga în meniuri, "
	"schimba setări, căuta canale și instala din feedul oficial, fără cheile și liniile modulelor de acces și fără "
	"datele tale personale. O oprești oricând.")
# banda de sus cat echipa apasa taste sau scrie (op-urile de control)
TEXT_LUCREAZA = N_("HD Satelit lucrează acum pe receptorul tău")
# cat ramane banda "lucrează acum" dupa ultimul op de control (secunde)
LUCREAZA_S = 20
TEXT_ACCEPT = N_("Accept termenii și condițiile")
TEXT_TERMENI = N_("Termenii și condițiile")
TEXT_FARA_BIFA = N_("Fără bifă, asistența nu pornește.")
TEXT_NIVEL = N_("Asistența e completă: citiri, probe și controlul receptorului prin meniuri, din lista fixă. O "
	"captură arată numai meniurile, nu imaginea canalului. Ecranele private rămân închise. Poți opri oricând.")
TEXT_ACORD = N_("Cu rândul bifat, Start confirmă că ești de acord cu aceste condiții și că ai cel puțin 16 ani sau "
	"acordul unui părinte.")


def textTermeni():
	"""Textul intreg al termenilor si conditiilor (fereastra derulanta de pe receptor si din web): informarea, nivelul
	si ce confirma Start (varsta)."""
	return "\n\n".join((textInformare(), _t(TEXT_NIVEL), _t(TEXT_ACORD)))


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

def _posteazaHttp(url, metoda, corp_octeti, antete, timp=TIMP_CERERE_S):
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError
	h = {"User-Agent": "hdsatelit-receptor/1", "Accept": "application/json"}
	h.update(antete or {})
	cerere = Request(url, data=corp_octeti, method=metoda, headers=h)
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
	"""Modelul receptorului, acelasi ca la programul de testeri: machinebuild-ul din paza modelului (verdictul
	„potrivit”), tinut minte de HdsBetaTester sau calculat aici (suntem pe firul sesiunii); altfel cel spus de
	sistem."""
	B = _beta()
	if B is not None:
		try:
			m = (B._modelTinut() or ("",))[0] or B.modelSiPaza()[0]
			if m:
				return str(m)[:40]
		except Exception as e:
			_jurnal("modelul: %s" % e)
	try:
		from boxbranding import getMachineBuild
		m = getMachineBuild()
		if m:
			return str(m)[:40]
	except Exception:
		pass
	for cale in ("/proc/stb/info/model", "/proc/stb/info/boxtype"):
		try:
			with open(cale) as f:
				v = f.read().strip()
			if v:
				return v[:40]
		except Exception:
			continue
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
		return self.stare in (INREGISTRARE, ASTEAPTA, CONECTAT)

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
		self.jurnal.adauga(_t("pornită (%s, nivel %s, %d minute, text v%d)")
			% (_t(ORIGINI[self.de_la]) if self.de_la in ORIGINI else self.de_la, self.nivel, self.durata_min,
			self.versiune_text))
		self._pune_stare(INREGISTRARE)
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
					"asteapta": self.stare == ASTEAPTA}, f)
			os.replace(nou, STARE_FISIER)
		except Exception:
			pass

	# -------- firul

	def _ruleaza(self):
		try:
			if not self._inregistreaza():
				return
			if not self._asteapta_aprobare():
				return
			self._bucla_cereri()
		except Exception as e:
			_jurnal("firul: %s" % e)
			self.opreste("eroare: %s" % type(e).__name__)
		finally:
			self.jurnal.adauga(_t("oprită (%s)") % textMotiv(self.motiv_oprire) if self.motiv_oprire else _t("oprită"))
			self._pune_stare(OPRIT)
			self._curata()
			_uita(self)

	def _inregistreaza(self):
		corp = {"v": PROTOCOL, "model": _model(), "imagine": _versiuneImagine(), "nivel": self.nivel,
			"durata_min": self.durata_min, "limba": self.limba}
		# campurile optionale numai cand omul a spus ceva: altfel corpul e cel de dinainte
		if self.nevoie:
			corp["nevoie"] = self.nevoie
		if self.detalii:
			corp["detalii"] = self.detalii
		cod, o = _ceruta(self.server + "inregistreaza", "POST", corp, {})
		if cod == 0 or cod >= 500 or cod == 404:
			self.jurnal.adauga(_t("nu pot ajunge la serverul de asistență"))
			self.opreste("fara-server")
			return False
		if not (200 <= cod < 300) or not o.get("id") or not o.get("secret") or not o.get("cod"):
			self.jurnal.adauga(_t("serverul a refuzat înregistrarea (%s)") % cod)
			self.opreste("inregistrare-refuzata")
			return False
		self.id = str(o["id"])[:64]
		self.secret = str(o["secret"])[:128]
		self.cod = re.sub(r"\D", "", str(o["cod"]))[:6]
		self.pana_la_ora = None if self.permanenta() else _oraPerete() + self.durata_min * 60
		self.stare = ASTEAPTA
		self._scrie_stare()
		self._pune_stare(ASTEAPTA)
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

	def _bucla_cereri(self):
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


# ---------------------------------------------------------------- starea globala (o sesiune deodata) si observatorii

_sesiune = None
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
	global _sesiune
	if not disponibil():
		return False, _t("Funcția nu e disponibilă pe această imagine.")
	with _lacat:
		if _sesiune is not None and _sesiune.activa():
			return False, _t("Asistența merge deja.")
		ses = Sesiune(nivel, durata_min, limba, SERVER, de_la=de_la, versiune_text=versiune_text, ctx=ctx,
			nevoie=nevoie, detalii=detalii)
		_sesiune = ses
	ses.porneste()
	return True, _t("Asistența a pornit.")


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


def stare():
	"""Starea pentru ecran si pentru pagina web."""
	ses = _sesiune
	if ses is None:
		return {"stare": OPRIT, "disponibil": disponibil(), "durate": list(DURATE_MIN),
			"durata_implicita": DURATA_IMPLICITA_MIN, "are_concluzii": ultimeleConcluzii() is not None}
	return {
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

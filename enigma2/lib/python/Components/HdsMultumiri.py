# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HdsMultumiri: randul de multumiri pentru toti beta testerii, jos in "Despre imagine" (Screens/Information.py,
HdsAbout.populate; pagina web /informatii/despre ia acelasi text).

Numele vin de pe server (https://stb.hdsatelit.com/forum/testeri.json, lista publica a testerilor), deja in ordinea
lor: cele mai multe XP de tester primul, la XP egal cine s-a inscris mai devreme. Imaginea ia numai campul "nume", in
ordinea primita (fara sortare proprie), deci un tester nou apare fara imagine noua. Numai numele alese de testeri pe
site si pe forum; serverul nu trimite altceva.

Doua copii, aceeasi forma {"v": 1, "actualizat": <unix, de pe server>, "nume": [...]}:
  - in imagine: ${datadir}/enigma2/multumiri-testeri.json (data/multumiri-testeri.json, refacuta la fiecare versiune
    de unealta multumiri_versiune.py --despre), pentru receptorul fara internet;
  - pe receptor: /etc/enigma2/hds-multumiri.json, scrisa atomic de actualizeaza(). Se arata copia cu "actualizat" mai
    nou; la egalitate, cea de pe receptor.
actualizeaza() cere lista cel mult o data pe zi (copia de pe receptor mai veche de o zi, socotita dupa ora scrierii
ei, si nicio incercare in ultima zi de la pornirea interfetei); un raspuns rau sau lipsa retelei nu schimba nimic.
porneste() o cheama pe un fir separat cand se deschide "Despre imagine" (pe televizor sau in web); ecranul arata ce
are, iar o lista noua se vede la urmatoarea deschidere. Fara dosarul copiei de pe receptor (pe PC) nu cere nimic.

Numele se curata: fara caractere de control sau de format (directie, latime zero), spatiile unite intr-unul (altfel
tabelul ar despica randul in eticheta / valoare), cel mult LUNGIME_MAX semne (unul mai lung se scurteaza cu "..."
tipografic, ca testerul sa ramana pe lista), cel mult NUME_MAX nume.

Albastrul, ca pe pagina /testeri/ a site-ului: beta testerii care si-au trimis propriul receptor la HD Satelit
(campul "receptor_trimis": true din testeri.json, pus de echipa in moderarea forumului) au numele ca o eticheta, text
albastru pe fundal alb (acelasi fundal si pe tema inchisa), iar sub rand sta legenda (LEGENDA), cu aceeasi eticheta ca
exemplu (bucati_legenda), numai cand e macar unul. Copia primeste cheia "trimis" (numele lor, curate ca
restul, numai cele din "nume"); fara niciunul cheia lipseste, deci copiile vechi raman bune. lista() da numele si pe cei
albastri din aceeasi copie; bucati_albastre() da tabelului de pe televizor si paginii web randul pe bucati
[(text, albastru)] si legenda, ca sa le deseneze colorate (textul enigma2 nu are coduri de culoare).

Producatorii care ne ajuta: producatori() citeste lista din imagine (data/multumiri-producatori.json) si
da firmele cu motivele; HdsAbout.populate le pune in sectiunea „Mulțumiri”, inaintea randului testerilor.

Contributorii (cine ne trimite cod, corecturi, pluginuri sau grafica folosite in imagine e trecut la contributori, pe site
si in imagine): contributori(limba) da [(nume, ce a adus, in limba receptorului)], sub
producatori, ca sectiunea Contributori de pe pagina /dezvoltatori/ a site-ului. Aceeasi lista din doua copii, ca la
testeri: ${datadir}/enigma2/contributori.json (data/contributori.json, refacuta la fiecare versiune de
multumiri_versiune.py --despre din situl-imaginii/date/contributori.json) si /etc/enigma2/hds-contributori.json, luata o
data pe zi de pe https://stb.hdsatelit.com/contributori.json (scris de fa_situl.py), ca un contributor nou sau unul scos
la cererea lui sa se vada fara imagine noua. Forma: {"v": 1, "actualizat": "AAAA-LL-ZZ HH:MM", "contributori": [{"nume",
"data", "ce": {limba: text}}]}; se arata copia cu "actualizat" mai nou (la egalitate cea de pe receptor), deci o lista
mai scurta trece si ea; o lista goala e buna (sectiunea nu apare). Textul „ce” vine din fisier in limba receptorului,
altfel in engleza, altfel in romana; numele nu se traduc.

Modul curat (fara enigma la incarcare): probele pe PC in test_multumiri_testeri_0621.py,
test_testeri_albastri_0611.py, test_multumiri_producatori_mu_074.py si test_ctb_contributori_077.py.
"""

import json
import os
import re
import threading
import time

NUME_IMAGINE = "multumiri-testeri.json"
CALE_IMAGINE = None                       # None: ${datadir}/enigma2/multumiri-testeri.json; probele pun alta cale
CALE_RECEPTOR = "/etc/enigma2/hds-multumiri.json"
URL = "https://stb.hdsatelit.com/forum/testeri.json"
TIMP = 10.0                               # secunde, pentru conectare si fiecare citire
MARIME_MAX = 2 * 1024 * 1024              # octetii raspunsului si ai unei copii
NUME_MAX = 1000
LUNGIME_MAX = 40
ZI = 24 * 3600

NOU = "nou"
SARIT = "sarit"
EROARE = "eroare"

# caracterele de control (C0, C1) si de format (directia textului, latime zero, separatorii de rand si paragraf)
_ASCUNSE = re.compile(u"[\x00-\x1f\x7f-\x9f­؜᠎​-‏ -‮⁠-⁯﻿￹-￻]")
_STARE = {"incercare": None, "incercare_contributori": None, "fir": None}


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


TEXT = N_("Mulțumim tuturor beta testerilor care au participat la realizarea imaginii HD Satelit: %s.")
LEGENDA = N_("Cu albastru: beta testerii care și-au trimis propriul receptor la HD Satelit, pentru probe și pentru "
	"îmbunătățirea imaginii E2 HD Satelit.")


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsMultumiri] %s" % text)


def cale_imagine():
	"""Copia venita cu imaginea: ${datadir}/enigma2/multumiri-testeri.json."""
	if CALE_IMAGINE:
		return CALE_IMAGINE
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/" + NUME_IMAGINE)
	except Exception:
		return "/usr/share/enigma2/" + NUME_IMAGINE


# ---------------------------------------------------------------- numele

def curat(nume):
	"""Un nume curat, sau "" (nu e sir sau nu ramane nimic din el)."""
	if not isinstance(nume, str):
		return ""
	nume = " ".join(_ASCUNSE.sub(" ", nume).split())
	if len(nume) > LUNGIME_MAX:
		nume = nume[:LUNGIME_MAX - 1].rstrip() + u"…"
	return nume


def curata(lista):
	"""Numele curate, in ordinea primita, cel mult NUME_MAX; cele care nu raman nimic se sar."""
	rez = []
	for n in lista if isinstance(lista, list) else []:
		n = curat(n)
		if n:
			rez.append(n)
			if len(rez) >= NUME_MAX:
				break
	return rez


def _actualizat(valoare, rezerva=0):
	if isinstance(valoare, bool) or not isinstance(valoare, (int, float)) or valoare <= 0:
		return int(rezerva)
	return int(valoare)


def _albastri(lista, nume):
	"""Numele albastre curate, numai cele care sunt si in `nume`, fara dubluri, in ordinea din `nume`."""
	ale = set(curata(lista))
	return [n for i, n in enumerate(nume) if n in ale and n not in nume[:i]]


def copie_din_raspuns(corp, acum=None):
	"""Raspunsul serverului (octeti) -> octetii copiei {"v": 1, "actualizat", "nume"[, "trimis"]}, sau None: raspuns
	rau (prea mare, JSON stricat, fara lista "testeri", niciun nume). "trimis" = numele testerilor cu
	"receptor_trimis": true (numai true), numai cand e macar unul. Folosita si de unealta care face copia din imagine."""
	if not isinstance(corp, bytes) or len(corp) > MARIME_MAX:
		return None
	try:
		d = json.loads(corp.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	if not isinstance(d, dict) or not isinstance(d.get("testeri"), list):
		return None
	testeri = [t for t in d["testeri"] if isinstance(t, dict)]
	nume = curata([t.get("nume") for t in testeri])
	if not nume:
		return None
	copie = {"v": 1, "actualizat": _actualizat(d.get("actualizat"), time.time() if acum is None else acum),
		"nume": nume}
	trimis = _albastri([t.get("nume") for t in testeri if t.get("receptor_trimis") is True], nume)
	if trimis:
		copie["trimis"] = trimis
	return (json.dumps(copie, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _citeste_copie(cale):
	"""(actualizat, nume, trimis) dintr-o copie, sau None (lipseste, stricata, fara niciun nume); trimis = [] cand
	cheia lipseste (copiile de dinainte de albastru)."""
	try:
		with open(cale, "rb") as f:
			date = f.read(MARIME_MAX + 1)
		if len(date) > MARIME_MAX:
			return None
		d = json.loads(date.decode("utf-8"))
	except (IOError, OSError, ValueError, UnicodeDecodeError):
		return None
	if not isinstance(d, dict) or d.get("v") != 1:
		return None
	nume = curata(d.get("nume"))
	if not nume:
		return None
	trimis = d.get("trimis")
	return _actualizat(d.get("actualizat")), nume, _albastri(trimis if isinstance(trimis, list) else [], nume)


def lista():
	"""(nume, trimis) de aratat, din aceeasi copie: cea de pe receptor, altfel cea din imagine (si cea din imagine cand
	e mai noua, dupa o versiune noua pe un receptor fara internet), altfel ([], [])."""
	receptor = _citeste_copie(CALE_RECEPTOR)
	imagine = _citeste_copie(cale_imagine())
	if receptor and (not imagine or receptor[0] >= imagine[0]):
		return receptor[1], receptor[2]
	return (imagine[1], imagine[2]) if imagine else ([], [])


def nume():
	"""Numele de aratat (lista()), fara cei albastri."""
	return lista()[0]


def _sablon(traducere=None):
	"""Fraza tradusa, daca are un singur %s si niciun alt %; altfel cea romaneasca."""
	try:
		tradus = (traducere or _t)(TEXT)
	except Exception:
		tradus = TEXT
	if not isinstance(tradus, str) or tradus.count("%") != 1 or tradus.count("%s") != 1:
		return TEXT
	return tradus


def text(lista=None, traducere=None):
	"""Fraza tradusa cu numele unite prin ", "; fara niciun nume, "" (randul nu apare)."""
	lista = nume() if lista is None else lista
	if not lista:
		return ""
	insiruire = ", ".join(lista)
	try:
		return (traducere or _t)(TEXT) % insiruire
	except (TypeError, ValueError):
		return TEXT % insiruire


def legenda(trimis, traducere=None):
	"""Legenda de sub rand, tradusa; "" cand nu e niciun nume albastru (legenda nu apare)."""
	if not trimis:
		return ""
	try:
		rez = (traducere or _t)(LEGENDA)
	except Exception:
		rez = LEGENDA
	return rez if isinstance(rez, str) and rez else LEGENDA


def segmente(lista, trimis, traducere=None):
	"""Randul de multumiri pe bucati [(text, albastru)], lipite la loc = text(lista): numele din `trimis` albastre,
	restul (fraza, virgulele) nu. Bucatile vecine de acelasi fel se unesc; fara niciun nume, []."""
	if not lista:
		return []
	inainte, dupa = _sablon(traducere).split("%s")
	albastri = set(trimis or [])
	rez = []

	def pune(bucata, albastru):
		if not bucata:
			return
		if rez and rez[-1][1] == albastru:
			rez[-1] = (rez[-1][0] + bucata, albastru)
		else:
			rez.append((bucata, albastru))

	pune(inainte, False)
	for i, n in enumerate(lista):
		if i:
			pune(", ", False)
		pune(n, n in albastri)
	pune(dupa, False)
	return rez


def bucati_albastre(traducere=None):
	"""Pentru tabelul de pe televizor (Screens/Information.py) si pagina web /informatii/despre: {text: bucati} cu
	randul de multumiri si legenda, fiecare cum il scrie populate() (fara " • "), si bucatile lui [(text, albastru)];
	{} cand nu e niciun nume albastru (nimic de colorat). Randul se potriveste numai daca textul e acelasi, deci o copie
	schimbata intre timp nu coloreaza nimic gresit."""
	lista_nume, trimis = lista()
	if not lista_nume or not trimis:
		return {}
	rand = text(lista_nume, traducere)
	bucati = segmente(lista_nume, trimis, traducere)
	if "".join(b for b, _a in bucati) != rand:
		# o traducere cu alt % decat %s: randul ramane, dar fara albastru
		return {}
	leg = legenda(trimis, traducere)
	return {rand: bucati, leg: bucati_legenda(leg)}


def bucati_legenda(leg):
	"""Legenda pe bucati: ce sta inainte de primele doua puncte („Cu albastru”) e eticheta-exemplu, ca numele din rand
	(text albastru pe fundal alb), restul text obisnuit, fara spatiul de la inceput (eticheta isi are marginea ei).
	Fara doua puncte, toata legenda e eticheta."""
	inainte, sep, dupa = leg.partition(":")
	if not sep or not inainte.strip() or not dupa.strip():
		return [(leg, True)]
	return [(inainte.strip(), True), (dupa.strip(), False)]


# ---------------------------------------------------------------- producatorii care ne ajuta

# Sectiunea „Mulțumiri” din „Despre imagine”: firmele care ne ajuta, fiecare cu motivul scurt. Lista sta in imagine,
# in ${datadir}/enigma2/multumiri-producatori.json (data/multumiri-producatori.json), date simple:
# {"v": 1, "producatori": [{"nume", "sigla", "unicable", "receptoare"}]}; un camp de ajutor are data (AAAA-LL-ZZ) sau
# ramane gol. Cand sosesc receptoarele unui producator se scrie data in campul lui "receptoare", nimic
# altceva. Numai numele firmelor (marca si firma), niciun nume de persoana; numele nu se traduc, motivele da.
NUME_PRODUCATORI = "multumiri-producatori.json"
CALE_PRODUCATORI = None                   # None: ${datadir}/enigma2/multumiri-producatori.json; probele pun alta cale
PRODUCATORI_MAX = 50
TITLU_MULTUMIRI = N_("Mulțumiri")
SUBTITLU_PRODUCATORI = N_("Producători care ne ajută")
SUBTITLU_TESTERI = N_("Beta testeri")
# campul din fisier -> motivul aratat, in aceasta ordine
MOTIVE = (
	("sigla", N_("acordul pentru siglă în ecranele de pornire")),
	("unicable", N_("datele convertoarelor Unicable")),
	("receptoare", N_("receptoarele trimise pentru probe")),
)


def cale_producatori():
	"""Lista din imagine: ${datadir}/enigma2/multumiri-producatori.json."""
	if CALE_PRODUCATORI:
		return CALE_PRODUCATORI
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/" + NUME_PRODUCATORI)
	except Exception:
		return "/usr/share/enigma2/" + NUME_PRODUCATORI


def _are(valoare):
	"""Un camp de ajutor e completat: un sir cu ceva in el (data) sau true."""
	return valoare is True or (isinstance(valoare, str) and bool(valoare.strip()))


def producatori(traducere=None):
	"""[(nume, motive)] din lista din imagine, in ordinea din fisier: motivele traduse, unite prin ", ". Se sar intrarile
	fara nume sau fara niciun camp completat; lista lipsa, stricata sau de alta forma da [] (sectiunea nu apare)."""
	try:
		with open(cale_producatori(), "rb") as f:
			date = f.read(MARIME_MAX + 1)
		if len(date) > MARIME_MAX:
			return []
		d = json.loads(date.decode("utf-8"))
	except (IOError, OSError, ValueError, UnicodeDecodeError):
		return []
	if not isinstance(d, dict) or d.get("v") != 1 or not isinstance(d.get("producatori"), list):
		return []
	tr = traducere or _t
	rez = []
	for p in d["producatori"]:
		if not isinstance(p, dict):
			continue
		nume = curat(p.get("nume"))
		motive = []
		for camp, motiv in MOTIVE:
			if _are(p.get(camp)):
				try:
					motive.append(tr(motiv) or motiv)
				except Exception:
					motive.append(motiv)
		if nume and motive:
			rez.append((nume, ", ".join(motive)))
			if len(rez) >= PRODUCATORI_MAX:
				break
	return rez


# ---------------------------------------------------------------- codul deschis luat de la altii

# Proiectele de cod deschis din care imaginea a luat cod, date sau idei (citate in fisierele lor, cu licenta si commitul),
# in „Despre imagine”, sectiunea „Mulțumiri”, sub producatori; pagina web /informatii/despre arata acelasi text. Numele nu se
# traduc, ce am luat da. Regula (12.11.2026): un lot care citeaza o sursa noua in fisiere adauga aici un rand scurt.
SUBTITLU_SURSE = N_("Cod deschis folosit în imagine")
SURSE = (
	("OE-Alliance", N_("componentele și convertoarele cerute de teme și pluginuri, ecranul Common Interface")),
	("VU+ (open-vuplus)", N_("ora trimisă modulului CI, sfârșitul redării din fișier, plăcile Vu+")),
	("DimitarCC (e2-boxlogos)", N_("siglele receptoarelor din teme (BoxLogo)")),
	("VDR", N_("forma răspunsului cu ora pentru modulul CI")),
	("Material Symbols (Google)", N_("desenele fontului de pictograme")),
	("fissix", N_("traducerea pluginurilor scrise pentru Python 2")),
	("oZeta", N_("forma convertorului ReceiverInfo")),
	("polywasm (Evan Wallace)", N_("WebAssembly pentru aplicațiile HbbTV pe receptoarele care nu-l au")),
	# autorii pluginurilor construite de noi din sursa lor pentru feedul extern (retetele din
	# meta-pluginuri-externe citeaza depozitul, autorul si licenta; pachetul are licenta si sursa langa el)
	("Taapat", N_("pluginul YouTube din feedul nostru")),
	("Anders Holst", N_("pluginul MovieCut din feedul nostru")),
	("Maros Ondrasek (mx3L)", N_("pluginul SubsSupport din feedul nostru")),
	("Coolman, betonme, Swiss-MAD", N_("pluginul Enhanced Movie Center din feedul nostru")),
	("KiddaC", N_("pluginurile XStreamity și Jedi EPG XStream din feedul nostru")),
	("Lululla", N_("pluginurile Command Center, TV Garden, freearhey, Smart TV Channel List, RSS Reader, Filmon și mmPicons din feedul nostru")),
	("mMark", N_("piconurile și temele pe care le descarcă mmPicons")),
	("dorinelu (DG Labs), pQu4k3r", N_("pluginul KidsSafe Bouquets din feedul nostru")),
	("VicTuS59", N_("pluginul GT IPTV Player Pro din feedul nostru")),
)


def surse(traducere=None):
	"""[(proiectul, ce am luat, tradus)], in ordinea din SURSE."""
	tr = traducere or _t
	rez = []
	for nume, ce in SURSE:
		try:
			rez.append((nume, tr(ce) or ce))
		except Exception:
			rez.append((nume, ce))
	return rez


def subtitluSurse(traducere=None):
	try:
		return (traducere or _t)(SUBTITLU_SURSE) or SUBTITLU_SURSE
	except Exception:
		return SUBTITLU_SURSE


def subtitluContributori(traducere=None):
	try:
		return (traducere or _t)(SUBTITLU_CONTRIBUTORI) or SUBTITLU_CONTRIBUTORI
	except Exception:
		return SUBTITLU_CONTRIBUTORI


# ---------------------------------------------------------------- contributorii (oameni care ne-au trimis ceva)

NUME_CONTRIBUTORI = "contributori.json"
CALE_CONTRIBUTORI = None                  # None: ${datadir}/enigma2/contributori.json; probele pun alta cale
CALE_CONTRIBUTORI_RECEPTOR = "/etc/enigma2/hds-contributori.json"
URL_CONTRIBUTORI = "https://stb.hdsatelit.com/contributori.json"
MARIME_MAX_CONTRIBUTORI = 256 * 1024
CONTRIBUTORI_MAX = 200
CE_MAX = 400                              # semnele textului „ce” intr-o limba
LIMBI_MAX = 40
SUBTITLU_CONTRIBUTORI = N_("Contributori")
_ACTUALIZAT_CONTRIBUTORI = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
_DATA_ZI = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COD_LIMBA = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")


def cale_contributori():
	"""Copia venita cu imaginea: ${datadir}/enigma2/contributori.json."""
	if CALE_CONTRIBUTORI:
		return CALE_CONTRIBUTORI
	try:
		from enigma import eEnv
		return eEnv.resolve("${datadir}/enigma2/" + NUME_CONTRIBUTORI)
	except Exception:
		return "/usr/share/enigma2/" + NUME_CONTRIBUTORI


def curat_text(text, maxim=CE_MAX):
	"""Un text curat (fara semne ascunse, spatiile unite), cel mult `maxim` semne (unul mai lung se scurteaza cu „…”),
	sau "" (nu e sir sau nu ramane nimic din el)."""
	if not isinstance(text, str):
		return ""
	text = " ".join(_ASCUNSE.sub(" ", text).split())
	if len(text) > maxim:
		text = text[:maxim - 1].rstrip() + u"…"
	return text


def curat_nume_contributor(nume):
	"""Numele ca la testeri (curat), fara „:” (in tabel numele e eticheta, iar „: ” ar despica randul in doua)."""
	return curat(" ".join(nume.replace(":", " ").split()) if isinstance(nume, str) else nume)


def contributori_din_raspuns(corp):
	"""Octetii unei liste (raspunsul serverului sau fisierul site-ului) -> octetii copiei curate {"v": 1, "actualizat",
	"contributori": [{"nume", "data"?, "ce"}]}, sau None: prea mare, JSON stricat, alta forma, "actualizat" lipsa sau gresit.
	Se sar intrarile fara nume sau fara niciun text „ce”; o lista goala e buna (cineva a cerut sa fie scos). Campurile
	interne (de pilda "_despre") nu trec. Folosita si de unealta care face copia din imagine."""
	if not isinstance(corp, bytes) or len(corp) > MARIME_MAX_CONTRIBUTORI:
		return None
	try:
		d = json.loads(corp.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None
	if not isinstance(d, dict) or d.get("v") != 1 or not isinstance(d.get("contributori"), list):
		return None
	actualizat = d.get("actualizat")
	if not isinstance(actualizat, str) or not _ACTUALIZAT_CONTRIBUTORI.match(actualizat):
		return None
	lista = []
	for c in d["contributori"]:
		if not isinstance(c, dict) or not isinstance(c.get("ce"), dict):
			continue
		nume = curat_nume_contributor(c.get("nume"))
		ce = {}
		for limba, text in c["ce"].items():
			text = curat_text(text)
			if isinstance(limba, str) and _COD_LIMBA.match(limba) and text and len(ce) < LIMBI_MAX:
				ce[limba] = text
		if not nume or not ce:
			continue
		intrare = {"nume": nume}
		if isinstance(c.get("data"), str) and _DATA_ZI.match(c["data"]):
			intrare["data"] = c["data"]
		intrare["ce"] = ce
		lista.append(intrare)
		if len(lista) >= CONTRIBUTORI_MAX:
			break
	copie = {"v": 1, "actualizat": actualizat, "contributori": lista}
	return (json.dumps(copie, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _citeste_contributori(cale):
	"""(actualizat, lista curata) dintr-o copie, sau None (lipseste, stricata, alta forma)."""
	try:
		with open(cale, "rb") as f:
			date = f.read(MARIME_MAX_CONTRIBUTORI + 1)
	except (IOError, OSError):
		return None
	octeti = contributori_din_raspuns(date)
	if octeti is None:
		return None
	d = json.loads(octeti.decode("utf-8"))
	return d["actualizat"], d["contributori"]


def lista_contributori():
	"""Intrarile de aratat: copia de pe receptor, altfel cea din imagine (si cea din imagine cand e mai noua, dupa o versiune
	noua pe un receptor fara internet), altfel []."""
	receptor = _citeste_contributori(CALE_CONTRIBUTORI_RECEPTOR)
	imagine = _citeste_contributori(cale_contributori())
	if receptor and (not imagine or receptor[0] >= imagine[0]):
		return receptor[1]
	return imagine[1] if imagine else []


def _text_in_limba(ce, limba):
	"""Textul „ce” in limba receptorului (ro_RO, apoi ro), altfel in engleza, altfel in romana, altfel primul."""
	limba = limba if isinstance(limba, str) else ""
	for cheie in (limba, limba.split("_")[0].lower(), "en", "ro"):
		if cheie and ce.get(cheie):
			return ce[cheie]
	return next(iter(ce.values()), "")


def contributori(limba=None):
	"""[(nume, ce a adus)] in ordinea din lista; `limba` = limba receptorului (language.getLanguage(), de pilda "pl_PL"),
	data de ecran ca modulul sa ramana fara enigma; fara ea, engleza."""
	return [(c["nume"], _text_in_limba(c["ce"], limba)) for c in lista_contributori()]


def titluri(traducere=None):
	"""(titlul sectiunii, subtitlul producatorilor, subtitlul testerilor), traduse."""
	tr = traducere or _t
	rez = []
	for text in (TITLU_MULTUMIRI, SUBTITLU_PRODUCATORI, SUBTITLU_TESTERI):
		try:
			rez.append(tr(text) or text)
		except Exception:
			rez.append(text)
	return tuple(rez)


# ---------------------------------------------------------------- actualizarea de pe server

def _citeste_url(url, timp, limita):
	from urllib.request import Request, urlopen
	cerere = Request(url, headers={"User-Agent": "hdsatelit-receptor/1", "Accept-Encoding": "identity",
		"Accept": "application/json"})
	r = urlopen(cerere, timeout=timp)
	try:
		lung = r.headers.get("Content-Length")
		if lung and lung.isdigit() and int(lung) > limita:
			raise ValueError("prea mare (%s octeti)" % lung)
		date = r.read(limita + 1)
	finally:
		r.close()
	if len(date) > limita:
		raise ValueError("prea mare (peste %d octeti)" % limita)
	return date


def _scrie_atomic(cale, octeti):
	"""Fisier temporar langa cel bun, fsync, os.replace; o cadere lasa copia veche neatinsa."""
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except BaseException:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _e_timpul(cale, cheie, acum=None):
	"""Se cere lista acum? Numai pe receptor (dosarul copiei `cale` exista), cel mult o incercare pe zi de la pornirea
	interfetei (_STARE[cheie]), si numai cand copia de pe receptor lipseste, e mai veche de o zi sau are ora in viitor
	(ceasul pus abia dupa scriere)."""
	acum = time.time() if acum is None else acum
	if not os.path.isdir(os.path.dirname(cale) or "."):
		return False
	ultima = _STARE.get(cheie)
	if ultima is not None and 0 <= acum - ultima < ZI:
		return False
	try:
		varsta = acum - os.path.getmtime(cale)
	except OSError:
		return True
	return not 0 <= varsta < ZI


def e_timpul(acum=None):
	"""Lista testerilor (_e_timpul pe copia de pe receptor CALE_RECEPTOR)."""
	return _e_timpul(CALE_RECEPTOR, "incercare", acum)


def e_timpul_contributori(acum=None):
	"""Lista contributorilor (_e_timpul pe CALE_CONTRIBUTORI_RECEPTOR, cu incercarea ei separata)."""
	return _e_timpul(CALE_CONTRIBUTORI_RECEPTOR, "incercare_contributori", acum)


def actualizeaza(acum=None, citeste_url=None):
	"""Lista de pe server, scrisa atomic in copia de pe receptor cand e buna. Blocanta (fir separat).
	-> (stare, mesaj): NOU (scrisa), SARIT (nu e timpul) sau EROARE (nimic schimbat)."""
	acum = time.time() if acum is None else acum
	if not e_timpul(acum):
		return SARIT, "nu e timpul"
	_STARE["incercare"] = acum
	try:
		corp = (citeste_url or _citeste_url)(URL, TIMP, MARIME_MAX)
	except Exception as e:
		return EROARE, "%s: %s" % (type(e).__name__, e)
	octeti = copie_din_raspuns(corp, acum)
	if octeti is None:
		return EROARE, "raspuns respins"
	try:
		_scrie_atomic(CALE_RECEPTOR, octeti)
	except (IOError, OSError) as e:
		return EROARE, "scriere: %s" % e
	return NOU, "%d nume" % len(json.loads(octeti.decode("utf-8"))["nume"])


def actualizeaza_contributori(acum=None, citeste_url=None):
	"""Lista contributorilor de pe server, scrisa atomic in copia de pe receptor cand e buna (si goala). Blocanta (fir
	separat), independenta de lista testerilor. -> (stare, mesaj): NOU, SARIT sau EROARE (nimic schimbat)."""
	acum = time.time() if acum is None else acum
	if not e_timpul_contributori(acum):
		return SARIT, "nu e timpul"
	_STARE["incercare_contributori"] = acum
	try:
		corp = (citeste_url or _citeste_url)(URL_CONTRIBUTORI, TIMP, MARIME_MAX_CONTRIBUTORI)
	except Exception as e:
		return EROARE, "%s: %s" % (type(e).__name__, e)
	octeti = contributori_din_raspuns(corp)
	if octeti is None:
		return EROARE, "raspuns respins"
	try:
		_scrie_atomic(CALE_CONTRIBUTORI_RECEPTOR, octeti)
	except (IOError, OSError) as e:
		return EROARE, "scriere: %s" % e
	return NOU, "%d contributori" % len(json.loads(octeti.decode("utf-8"))["contributori"])


def _lucreaza():
	# testerii, apoi contributorii; o cadere la una nu o opreste pe cealalta
	try:
		stare, mesaj = actualizeaza()
	except Exception as e:
		stare, mesaj = EROARE, "%s: %s" % (type(e).__name__, e)
	if stare != SARIT:
		_jurnal("%s (%s)" % (stare, mesaj))
	try:
		stare, mesaj = actualizeaza_contributori()
	except Exception as e:
		stare, mesaj = EROARE, "%s: %s" % (type(e).__name__, e)
	if stare != SARIT:
		_jurnal("contributori: %s (%s)" % (stare, mesaj))


def _fir_daemon(functie):
	t = threading.Thread(target=functie, name="hds-multumiri")
	t.daemon = True
	t.start()
	return t


def porneste(fir=None):
	"""Din "Despre imagine" (ecranul si pagina web): actualizarea pe un fir separat, cand e timpul pentru lista
	testerilor sau pentru cea a contributorilor si nu merge deja una. -> True daca a pornit."""
	vechi = _STARE["fir"]
	if vechi is not None and vechi.is_alive():
		return False
	if not e_timpul() and not e_timpul_contributori():
		return False
	_STARE["fir"] = (fir or _fir_daemon)(_lucreaza)
	return True

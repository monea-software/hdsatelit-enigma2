# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAfisaj.py: afisajul din fata al receptorului (4 cifre de 7 segmente): ce arata, in ce ordine si cat.
#
# Driverul (Viper 4K V20, FD650 prin firedtv.ko): /dev/dbox/oled0 e legatura udev spre dispozitivul misc oled0. Fiecare
# octet scris aprinde pe pozitia lui o forma fixa din tabela driverului; octetii ii da Components/HdsAfisajLitere.py
# (octeti()), dupa tabelul nostru de litere. Se scriu mereu 4 octeti (o pozitie nescrisa nu ramane goala), niciodata
# „:” (un sir cu „:” nu se afiseaza deloc). In asteptare, Components/HdsStandbyTv.py scrie „off” in
# /proc/stb/hdmi/output; inainte scrie in /proc/stb/power/vfd „1” cand asteptarea arata ceva (arataInAsteptare), ca
# driverul sa lase afisajul aprins, si „0” la „nimic” (driverul goleste afisajul si nu mai primeste texte pana la „on”).
# La iesirea din asteptare ultimul sir se uita, deci textul se scrie din nou dupa „on”. Calea se poate schimba cu
# HDS_AFISAJ_DISPOZITIV (emulatorul scrie intr-un fisier).
#
# Ce arata (config.hds_afisaj):
#   - lista: lista de rotire, alegeri din Components/HdsAfisajDate.py („grupa.nume:format”), fiecare cu durata ei
#     („@secunde”; 0 = automat: 5 s un text care incape, cat tine derularea unul lung) si, optional, cu eticheta scurta
#     inainte („+e”, 1 s). O alegere fara valoare acum (nu se inregistreaza, nu e radio) se sare; cand nicio alegere
#     nu are valoare, afisajul arata ora. O singura alegere in lista sta pe afisaj; un text lung trece pana iese si reia.
#   - evenimente: mesajele scurte care trec in fata listei (volumul, mut, cifrele tastate, canalul nou, REC, USB,
#     semnalul pierdut, pornirea interfetei), fiecare cu formatul ales; in asteptare nu se arata.
#   - asteptare: ora, ora si data pe rand, ora si urmatoarea inregistrare, sau nimic.
#   - viteza derularii, luminozitatea (ziua si noaptea, cu orele noptii) si textul tau.
# Setarea veche „functionare” (ora, numarul canalului, nimic), salvata, trece o data in lista (initConfig).
#
# Modul „Personaj” (Components/HdsAfisajPersonaj.py, config.hds_afisaj.personaj*): ochi si o gura desenate din segmente.
# O expresie trece ca un mesaj scurt cu sursa „personaj”, la evenimente (pornirea, asteptarea, zap-ul, semnalul pierdut,
# eroarea, inregistrarea, volumul, noaptea) si la intamplare; un mesaj scurt adevarat are intaietate, iar dupa expresie
# afisajul revine la ce arata, ca dupa orice mesaj. Planificarea o face HdsAfisajPersonaj.Personaj, pe acelasi ceas.
#
# FIRUL: un singur eTimer, pe firul enigma2. La fiecare pas: cadrul urmator al desenului (calculat o data, cand se
# schimba valoarea), o scriere de 4 octeti numai cand difera de ultima, apoi ceasul se pune pana la urmatoarea
# schimbare (cadrul urmator, sfarsitul alegerii, reimprospatarea valorii, cel mult DORMI_MAXIM_S). Valorile se citesc
# numai pentru alegerea aratata acum si cel mult cu perioada din catalog; citirile de disc (Lucru) merg pe un fir
# separat, iar afisajul ia rezultatul la pasul urmator. Nimic nu se scrie pe eMMC: setarile se salveaza numai din
# seteaza() (ecranul si pagina web, la OK). Numarul canalului se numara o data pe zap, numai cand lista il foloseste,
# pe lista C++ a buchetului (cel mult MAX_CANALE_NUMARATE intrari); o lista care nu e buchet nu se numara deloc.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os
import threading
import time

try:
	from Components import HdsAfisajLitere as L
	from Components import HdsAfisajDate as D
	from Components import HdsAfisajPersonaj as P
except ImportError:     # probele de pe PC incarca modulele singure
	import HdsAfisajLitere as L
	import HdsAfisajDate as D
	import HdsAfisajPersonaj as P

DISPOZITIV = os.environ.get("HDS_AFISAJ_DISPOZITIV") or "/dev/dbox/oled0"
LUMINOZITATE = "/proc/stb/lcd/oled_brightness"
LATIME = L.LATIME
GOL = " " * LATIME
MAX_CANALE_NUMARATE = 5000
MAX_LISTA = 24

LISTA_IMPLICITA = "ceas.ora:24"
# mesajele pornite implicit: volumul, mutul, cifrele tastate, canalul nou (numarul, apoi numele derulat), antena care se
# roteste, inregistrarea care porneste, cautarea canalelor si actualizarea imaginii (procentul)
EVENIMENTE_IMPLICITE = ("evenimente.volum:n,evenimente.mut:mut,evenimente.cifre:cifre,evenimente.zap:numar_nume,"
	"evenimente.motor:sageti_grade,evenimente.rec:rec,evenimente.cautare:pr,evenimente.actualizare:upd")
ORA = "ceas.ora:24"
ASTEPTARE = ("ora", "ora_data", "rec", "stins")
ASTEPTARE_IMPLICIT = "ora"
ALEGERE_ASTEPTARE = {"ora": "asteptare.ora:24", "ora_data": "asteptare.ora_data:alternat",
	"rec": "asteptare.rec:alternat", "stins": "asteptare.stins:gol"}
# alegerile de dinainte de lista de rotire: raman pentru setarile salvate si pentru scripturi (?functionare=)
FUNCTIONARE = ("ora", "canal", "stins")
FUNCTIONARE_IMPLICIT = "ora"
LISTA_DIN_FUNCTIONARE = {"ora": "ceas.ora:24", "canal": "canal.numar:dreapta", "stins": "texte.nimic:gol"}
VITEZE = ("200", "300", "450", "600")
VITEZA_IMPLICITA = "300"
DURATE = (0, 2, 3, 5, 8, 10, 15, 30)       # secunde; 0 = automat
DURATA_FIXA_S = 5.0          # automat, pentru un text care incape
DURATA_BUCLA_S = 4.0         # automat, cel putin atat pentru inel, sageti, alternat
ETICHETA_MS = 1000
MESAJ_S = 3.0
CIFRE_S = 3.5                # cifrele tastate raman atat dupa ultima cifra (ca fereastra NumberZap)
CIFRE_DUPA_OK_S = 1.0        # dupa OK cifrele raman pana la zap (evStart le incheie), cel mult atat
MOTOR_ASTEAPTA_S = 5.0       # dupa un zap, cat se urmareste daca porneste antena cu motor
MOTOR_PAS_S = 1.0            # cat merge antena: starea ei, o data pe secunda
MOTOR_MESAJ_S = 2.0          # mesajul antenei tine atat dupa ultima stare „se misca”
DORMI_MAXIM_S = 60.0
TOLERANTA_S = 0.005          # un pas venit cu atat mai devreme (rotunjirea ceasului) conteaza ca la timp
# luminozitatea: sirurile hex care aleg cele 7 trepte ale FD650 (driverul imparte valoarea la 37)
TREPTE_LUMINA = ("0", "4a", "6f", "de", "103", "128", "21e")
LUMINA_NESCHIMBATA = "neschimbat"
NOAPTE_LA_FEL = "la_fel"
ORE_NOAPTE_DE_LA = ("18", "19", "20", "21", "22", "23", "0")
ORE_NOAPTE_PANA_LA = ("5", "6", "7", "8", "9")
NOAPTE_DE_LA_IMPLICIT = "22"
NOAPTE_PANA_LA_IMPLICIT = "7"
MAX_TEXT = 60
MINUTAR_MINUTE = (0, 1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 90, 120)
CRONOMETRU = ("porneste", "opreste", "zero")
RENUMARARE_S = 30.0          # pagina web: numarul canalului numarat din nou cel mult atat de des

# deschiderea dispozitivului: fara blocare si fara terminal de control (steagurile lipsesc pe PC, in probe)
_DESCHIDERE = os.O_WRONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0)

# id-urile care cer numarul canalului (numararea trece prin buchet: numai cand trebuie)
_CER_NUMARUL = ("canal.numar", "canal.numar_nume", "canal.cate")
# mesajele canalului de dinainte, incheiate la zap
_SE_INCHEIE_LA_ZAP = ("evenimente.cifre", "evenimente.zap", "evenimente.fara_semnal")
# evenimentele serviciului dupa care informatiile lui (imaginea, sunetul, emisiunea) se citesc din nou
_EV_INFO = ("evUpdatedInfo", "evUpdatedEventInfo", "evVideoSizeChanged", "evVideoFramerateChanged",
	"evVideoProgressiveChanged", "evVideoGammaChanged")
# mesajele scurte care sunt si evenimente ale personajului (expresia trece dupa mesaj, cand mesajul e ales)
_PERSONAJ_LA_MESAJ = {"evenimente.pornire": "pornire", "evenimente.eroare": "eroare", "evenimente.rec": "rec",
	"evenimente.volum": "volum", "evenimente.mut": "mut"}
# evenimentele unei inregistrari care a esuat; dupa unul, sfarsitul inregistrarii nu mai aduce zambetul
_REC_ESUAT = ("evRecordFailed", "evRecordWriteError", "evRecordAborted")
REC_ESUAT_S = 120.0


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsAfisaj] %s" % text)


# ---------------------------------------------------------------- lista de rotire

class Intrare(object):
	"""O alegere din lista de rotire: data, formatul, durata (secunde, 0 = automat) si eticheta scurta inainte."""
	__slots__ = ("d", "f", "durata", "eticheta")

	def __init__(self, d, f, durata=0, eticheta=False):
		self.d = d
		self.f = f
		self.durata = durata
		self.eticheta = eticheta

	def id(self):
		return D.idAlegere(self.d, self.f)

	def text(self):
		t = self.id()
		if self.durata:
			t += "@%d" % self.durata
		if self.eticheta:
			t += "+e"
		return t

	def __eq__(self, alt):
		return isinstance(alt, Intrare) and self.text() == alt.text()

	def __ne__(self, alt):
		return not self.__eq__(alt)

	__hash__ = None


def durataPotrivita(durata):
	"""Cea mai apropiata durata dintre DURATE."""
	try:
		durata = int(durata)
	except (TypeError, ValueError):
		return 0
	return min(DURATE, key=lambda x: (abs(x - durata), -x))


def _parteLista(parte):
	"""„grupa.nume:format@durata+e” -> Intrare sau None."""
	parte = parte.strip()
	eticheta = parte.endswith("+e")
	if eticheta:
		parte = parte[:-2]
	alegerea, _sep, durata = parte.partition("@")
	d, f = D.alegere(alegerea)
	if d is None or d.grupa in (D.GRUPA_EVENIMENTE, D.GRUPA_ASTEPTARE):
		return None
	return Intrare(d, f, durataPotrivita(durata) if durata else 0, eticheta and D.areEticheta(d, f))


def citesteLista(text):
	"""Lista de rotire din textul salvat; ce nu se mai cunoaste se sare."""
	rez = []
	for parte in (text or "").split(","):
		if not parte.strip():
			continue
		i = _parteLista(parte)
		if i is not None:
			rez.append(i)
		if len(rez) >= MAX_LISTA:
			break
	return rez


def scrieLista(intrari):
	return ",".join(i.text() for i in intrari)


def valideazaLista(text):
	"""(lista, None) sau (None, mesajul) pentru un text venit din ecran sau din web: o alegere necunoscuta nu schimba
	nimic."""
	rez = []
	for parte in (text or "").split(","):
		if not parte.strip():
			continue
		i = _parteLista(parte)
		if i is None:
			return None, _("Alegerea „%s” nu există.") % parte.strip()[:40]
		rez.append(i)
	if len(rez) > MAX_LISTA:
		return None, _("Lista de rotire poate avea cel mult %d alegeri.") % MAX_LISTA
	return rez, None


def citesteEvenimente(text):
	"""{id data: Format} pentru mesajele scurte alese."""
	rez = {}
	for parte in (text or "").split(","):
		d, f = D.alegere(parte.strip())
		if d is not None and d.grupa == D.GRUPA_EVENIMENTE:
			rez[d.id] = f
	return rez


def valideazaEvenimente(text):
	rez = {}
	for parte in (text or "").split(","):
		if not parte.strip():
			continue
		d, f = D.alegere(parte.strip())
		if d is None or d.grupa != D.GRUPA_EVENIMENTE:
			return None, _("Alegerea „%s” nu există.") % parte.strip()[:40]
		rez[d.id] = f
	return rez, None


def scrieEvenimente(evenimente):
	"""Textul salvat, in ordinea catalogului (ca doua salvari la fel sa dea acelasi text)."""
	return ",".join(D.idAlegere(d, evenimente[d.id]) for d in D.CATALOG if d.id in evenimente)


def textDurata(durata):
	if not durata:
		return _("automat")
	return _("%d s") % durata


# ---------------------------------------------------------------- setarile

def alegeriFunctionare():
	return [("ora", _("Ora")), ("canal", _("Numărul canalului")), ("stins", _("Nimic (afișaj stins)"))]


def alegeriAsteptare():
	return [("ora", _("Ora")), ("ora_data", _("Ora și data, pe rând")), ("rec", _("Ora și următoarea înregistrare")),
		("stins", _("Nimic (afișaj stins)"))]


def alegeriViteza():
	return [("200", _("Repede")), ("300", _("Normală")), ("450", _("Încet")), ("600", _("Foarte încet"))]


def alegeriLuminozitate():
	return [(LUMINA_NESCHIMBATA, _("Neschimbată"))] + [(str(i), _("Treapta %d din 7") % i) for i in range(1, 8)]


def alegeriLuminozitateNoapte():
	return [(NOAPTE_LA_FEL, _("La fel ca ziua"))] + [(str(i), _("Treapta %d din 7") % i) for i in range(1, 8)]


def alegeriNoapteDeLa():
	return [(h, _("de la ora %s") % h) for h in ORE_NOAPTE_DE_LA]


def alegeriNoaptePanaLa():
	return [(h, _("până la ora %s") % h) for h in ORE_NOAPTE_PANA_LA]


def alegeriOras():
	"""Fusurile pentru „Ora din alt oraș” (lista imaginii, /etc/timezone.xml), cu „niciunul” intai."""
	return [("", _("niciunul"))] + D.fusurile()


def alegeriMinutar():
	return [("0", _("Oprit"))] + [(str(m), _("%d minute") % m) for m in MINUTAR_MINUTE if m]


def alegeriCronometru():
	return [("porneste", _("Pornește")), ("opreste", _("Oprește")), ("zero", _("De la zero"))]


def textMinutar(acum=None):
	"""Starea minutarului, ca text: „oprit” sau timpul ramas."""
	s = D.minutarRamas(time.time() if acum is None else acum)
	if s is None:
		return _("oprit")
	return _("rămas %s") % ("%d:%02d" % divmod(s, 60))


def textCronometru(acum=None):
	v = D.cronometruScurs(time.time() if acum is None else acum)
	if v is None:
		return _("la zero, oprit")
	text = "%d:%02d" % divmod(v[0], 60)
	return (_("merge: %s") if v[1] else _("oprit la %s")) % text


def minutar(minute):
	"""Porneste minutarul de pe afisaj (0 = il opreste). Intoarce (reusit, mesaj)."""
	try:
		minute = int(minute)
	except (TypeError, ValueError):
		return False, _("Valoarea „%s” nu se poate alege aici.") % ("%s" % minute)[:20]
	if minute not in MINUTAR_MINUTE:
		return False, _("Valoarea „%s” nu se poate alege aici.") % ("%d" % minute)
	D.pornesteMinutar(minute)
	actualizeaza()
	return True, (_("Minutarul numără %d minute.") % minute) if minute else _("Minutarul e oprit.")


def cronometru(ce):
	"""Cronometrul de pe afisaj: „porneste”, „opreste”, „zero”. Intoarce (reusit, mesaj)."""
	if ce not in CRONOMETRU:
		return False, _("Valoarea „%s” nu se poate alege aici.") % ("%s" % ce)[:20]
	D.cronometru(ce)
	actualizeaza()
	return True, textCronometru()


def disponibil(cale=None):
	"""Receptorul are afisaj in fata (dispozitivul exista)."""
	return os.path.exists(cale or DISPOZITIV)


def _migreaza(c):
	"""Setarea veche „functionare”, salvata (numarul canalului sau nimic), trece o singura data in lista de rotire;
	apoi se goleste, ca sa nu treaca din nou. Se scrie pe disc la urmatoarea salvare a setarilor."""
	vechi = c.functionare.saved_value
	if c.lista.saved_value is None and vechi in LISTA_DIN_FUNCTIONARE and vechi != FUNCTIONARE_IMPLICIT:
		c.lista.value = LISTA_DIN_FUNCTIONARE[vechi]
		c.lista.save()
		_jurnal("setarea veche functionare=%s trece in lista: %s" % (vechi, c.lista.value))
	if vechi is not None:
		c.functionare.value = FUNCTIONARE_IMPLICIT
		c.functionare.save()


def initConfig():
	"""config.hds_afisaj si SystemInfo["HdsAfisaj"] (intrarea din meniu)."""
	from Components.config import config
	if "hds_afisaj" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigSelection, ConfigText
	c = ConfigSubsection()
	config.hds_afisaj = c
	c.lista = ConfigText(default=LISTA_IMPLICITA, fixed_size=False)
	c.functionare = ConfigSelection(default=FUNCTIONARE_IMPLICIT, choices=alegeriFunctionare())
	c.asteptare = ConfigSelection(default=ASTEPTARE_IMPLICIT, choices=alegeriAsteptare())
	c.evenimente = ConfigText(default=EVENIMENTE_IMPLICITE, fixed_size=False)
	c.viteza = ConfigSelection(default=VITEZA_IMPLICITA, choices=alegeriViteza())
	c.luminozitate = ConfigSelection(default=LUMINA_NESCHIMBATA, choices=alegeriLuminozitate())
	c.luminozitate_noapte = ConfigSelection(default=NOAPTE_LA_FEL, choices=alegeriLuminozitateNoapte())
	c.noapte_de_la = ConfigSelection(default=NOAPTE_DE_LA_IMPLICIT, choices=alegeriNoapteDeLa())
	c.noapte_pana_la = ConfigSelection(default=NOAPTE_PANA_LA_IMPLICIT, choices=alegeriNoaptePanaLa())
	c.text = ConfigText(default="", fixed_size=False)
	c.oras = ConfigText(default="", fixed_size=False)        # fusul orei din alt oras (de ex. „Asia/Tokyo”)
	c.personaj = ConfigSelection(default=P.PORNIT_IMPLICIT, choices=P.alegeriPornit())
	c.personaj_ritm = ConfigSelection(default=P.RITM_IMPLICIT, choices=P.alegeriRitm())
	c.personaj_noaptea = ConfigSelection(default=P.NOAPTEA_IMPLICIT, choices=P.alegeriNoaptea())
	try:
		_migreaza(c)
	except Exception as e:
		_jurnal("setarea veche: %r" % (e,))
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsAfisaj"] = disponibil()
	except Exception as e:
		_jurnal("SystemInfo: %r" % (e,))


def _cfg():
	from Components.config import config
	initConfig()
	return config.hds_afisaj


# valorile permise ale setarilor cu alegeri (ecranul si pagina web)
VALORI = {
	"asteptare": ASTEPTARE,
	"viteza": VITEZE,
	"luminozitate": (LUMINA_NESCHIMBATA,) + tuple(str(i) for i in range(1, 8)),
	"luminozitate_noapte": (NOAPTE_LA_FEL,) + tuple(str(i) for i in range(1, 8)),
	"noapte_de_la": ORE_NOAPTE_DE_LA,
	"noapte_pana_la": ORE_NOAPTE_PANA_LA,
	"personaj": P.PORNIT,
	"personaj_ritm": P.RITMURI,
	"personaj_noaptea": P.NOAPTEA,
}


def seteaza(lista=None, asteptare=None, evenimente=None, viteza=None, luminozitate=None, luminozitate_noapte=None,
		noapte_de_la=None, noapte_pana_la=None, text=None, functionare=None, oras=None, personaj=None, personaj_ritm=None,
		personaj_noaptea=None):
	"""Schimba, salveaza si aplica pe loc (ecranul si pagina web). Intoarce (reusit, mesaj); o valoare straina nu
	schimba nimic."""
	from Components.config import configfile
	c = _cfg()
	if functionare is not None:
		if functionare not in FUNCTIONARE:
			return False, _("Alegerea pentru receptorul pornit nu există.")
		lista = LISTA_DIN_FUNCTIONARE[functionare]
	noi = {}
	if lista is not None:
		intrari, eroare = valideazaLista(lista)
		if eroare:
			return False, eroare
		noi["lista"] = scrieLista(intrari)
	if evenimente is not None:
		ev, eroare = valideazaEvenimente(evenimente)
		if eroare:
			return False, eroare
		noi["evenimente"] = scrieEvenimente(ev)
	valori = {"asteptare": asteptare, "viteza": viteza, "luminozitate": luminozitate,
		"luminozitate_noapte": luminozitate_noapte, "noapte_de_la": noapte_de_la, "noapte_pana_la": noapte_pana_la,
		"personaj": personaj, "personaj_ritm": personaj_ritm, "personaj_noaptea": personaj_noaptea}
	for cheie in sorted(VALORI):
		v = valori[cheie]
		if v is None:
			continue
		if v not in VALORI[cheie]:
			if cheie == "asteptare":
				return False, _("Alegerea pentru așteptare nu există.")
			return False, _("Valoarea „%s” nu se poate alege aici.") % v[:20]
		noi[cheie] = v
	if text is not None:
		noi["text"] = u"".join(ch for ch in u"%s" % text if ch >= u" ")[:MAX_TEXT].strip()
	if oras is not None:
		if oras and oras not in dict(D.fusurile()):
			return False, _("Valoarea „%s” nu se poate alege aici.") % oras[:20]
		noi["oras"] = oras
	for cheie, v in noi.items():
		el = getattr(c, cheie)
		el.value = v
		el.save()
	configfile.save()
	if _afisaj is None:
		return True, _("Salvat.")
	_afisaj.citesteSetarile()
	_afisaj.previzualizare = None
	_afisaj.previzualizareAsteptare = None
	_afisaj.previzualizarePana = None
	_afisaj.lumina = None
	_afisaj.reporneste()
	if _afisaj.eroare is not None:
		return True, _("Salvat, dar afișajul nu primește textul. Repornește receptorul.")
	return True, _("Salvat. Afișajul s-a schimbat pe loc.")


def previzualizeaza(lista=None, asteptare=None, termen=None):
	"""Ecranul de alegere si pagina web: afisajul adevarat arata lista de pe ecran inainte de salvare (None = inapoi la
	cea salvata). `termen` (secunde, pagina web): previzualizarea se stinge singura daca nu vine alta cerere pana atunci
	(o pagina inchisa fara „Salvează” sau „Renunță” nu lasa afisajul pe lista nesalvata)."""
	if _afisaj is None:
		return
	intrari = citesteLista(lista) if lista is not None else None
	asteptare = asteptare if lista is not None else None
	pana = (_afisaj.ceas() + termen) if (termen and lista is not None) else None
	if intrari is not None and intrari == _afisaj.previzualizare and asteptare == _afisaj.previzualizareAsteptare:
		_afisaj.previzualizarePana = pana       # aceeasi lista (pagina o reinnoieste): numai termenul, fara reluare
		return
	_afisaj.previzualizare = intrari
	_afisaj.previzualizareAsteptare = asteptare
	_afisaj.previzualizarePana = pana
	_afisaj.reporneste()


def arePrevizualizare():
	"""Afisajul arata acum o lista nesalvata (ecranul sau pagina web)."""
	return _afisaj is not None and _afisaj.previzualizare is not None


# ---------------------------------------------------------------- numarul canalului

def _numarDinLista(referinte, cheie, deplasare, cheieDe, esteCanal):
	"""Numarul canalului `cheie` intr-un buchet: deplasare + pozitia lui printre canale (1, 2, ...), sau None."""
	n = 0
	for i, r in enumerate(referinte):
		if i >= MAX_CANALE_NUMARATE:
			return None
		if not esteCanal(r):
			continue
		n += 1
		if cheieDe(r) == cheie:
			return deplasare + n
	return None


def _cateDinLista(referinte, esteCanal):
	"""Cate canale are buchetul (fara marcaje si dosare), sau None peste MAX_CANALE_NUMARATE intrari."""
	n = 0
	for i, r in enumerate(referinte):
		if i >= MAX_CANALE_NUMARATE:
			return None
		if esteCanal(r):
			n += 1
	return n


def esteBuchet(radacina, dosar):
	"""Lista de pe televizor are numere numai intr-un buchet, cu aceeasi conditie ca ChannelSelection.setRoot: calea are
	„FROM BOUQUET”, nu e lista buchetelor („FROM BOUQUET "bouquets.”) si radacina e un dosar. Toate canalele, satelitii
	si furnizorii nu au numere."""
	try:
		cale = radacina.getPath()
		return "FROM BOUQUET" in cale and 'FROM BOUQUET "bouquets.' not in cale and bool(radacina.flags & dosar)
	except Exception:
		return False


def _serviciulRedat(session):
	"""Referinta serviciului redat: Navigation are, dupa versiune, getCurrentlyPlayingServiceOrGroup sau numai
	getCurrentlyPlayingServiceReference (cea din imagine)."""
	nav = getattr(session, "nav", None)
	citeste = getattr(nav, "getCurrentlyPlayingServiceOrGroup", None) or getattr(nav,
		"getCurrentlyPlayingServiceReference", None)
	return citeste() if citeste is not None else None


def numarSiCate(session, cate=False):
	"""(numarul canalului redat, cate canale are buchetul listei) din lista de canale de pe televizor; None unde nu se
	poate afla (niciodata o exceptie: il cheama si ecranul, si afisajul). Canalele se numara numai cu cate=True."""
	try:
		from enigma import eServiceCenter, eServiceReference
		from Screens.InfoBar import InfoBar
	except ImportError:
		return None, None
	try:
		infobar = InfoBar.instance
		lista = getattr(infobar, "servicelist", None) if infobar else None
		ref = _serviciulRedat(session)
	except Exception as e:
		_jurnal("serviciul redat: %r" % (e,))
		return None, None
	if lista is None or ref is None:
		return None, None
	try:
		radacina = lista.getRoot()
		# lista unei retele de cablu (Components/HdsRetele.py): numarul dat de operator, ca pe bara si in lista
		retea = getattr(lista, "hdsReteaRadacinii", None)
		generatie = _fisierulRetelelor(radacina) if retea is not None else None
		cheie = retea(radacina) if (retea is not None and radacina is not None) else None
		if cheie is not None:
			return _numarInRetea(lista, cheie, ref, cate, generatie)
		if radacina is None or not esteBuchet(radacina, eServiceReference.isDirectory):
			return None, None
		continut = eServiceCenter.getInstance().list(radacina)
		if continut is None:
			return None, None
		referinte = continut.getContent("R", False)
		deplasare = lista.getBouquetNumOffset(radacina)
	except Exception as e:
		_jurnal("numarul canalului: %r" % (e,))
		return None, None
	fara = eServiceReference.isDirectory | eServiceReference.isMarker
	try:
		esteCanal = lambda r: not (r.flags & fara)
		numar = _numarDinLista(referinte, ref.toCompareString(), deplasare, lambda r: r.toCompareString(), esteCanal)
		return numar, (_cateDinLista(referinte, esteCanal) if cate else None)
	except Exception as e:
		_jurnal("numararea canalelor: %r" % (e,))
		return None, None


def _fisierulRetelelor(radacina):
	"""Versiunea fisierului retelelor (Components/HdsRetele.generatie: fisierul privit chiar acum, citit numai daca s-a
	schimbat) cand radacina listei e lista unei retele, altfel None. Pentru celelalte liste fisierul nu se priveste."""
	try:
		from Components import HdsRetele
		if radacina is not None and HdsRetele.e_cale_de_retea(radacina.getPath()):
			return HdsRetele.generatie()
	except Exception as e:
		_jurnal("fisierul retelelor: %r" % (e,))
	return None


def _numarInRetea(lista, cheie, ref, cate, generatie=None):
	"""(numarul operatorului al canalului redat, cate canale cu numar are lista retelei) sau (None, ...), dupa fisierul
	retelelor de acum (`generatie`, din _fisierulRetelelor). Un zap care ocoleste lista (din web, din ghid) dupa o
	scanare noua sau un fisier pus de mana: numarul vine din fisierul nou, iar lista retelei, umpluta din fisierul de
	dinainte, se umple din nou o data (hdsReteaLaZi), ca numaratoarea sa fie cea noua. Fisier neschimbat: numai
	privirea fisierului (os.stat), fara citire si fara umplerea listei."""
	try:
		from Components import HdsRetele
		info = HdsRetele.pentru_ref(ref.toString())
	except Exception as e:
		_jurnal("numarul operatorului: %r" % (e,))
		return None, None
	numar = info.get("lcn") if info and info.get("cheie_retea") == cheie else None
	if not cate:
		return (numar or None), None
	laZi = getattr(lista, "hdsReteaLaZi", None)
	if generatie is not None and laZi is not None and getattr(lista, "hdsGeneratieRetea", None) != generatie:
		try:
			laZi()
		except Exception as e:
			_jurnal("lista retelei la zi: %r" % (e,))
	return (numar or None), len(getattr(lista, "hdsNumereRetea", None) or {})


def numarCanal(session):
	"""Numarul canalului redat (cifrele telecomenzii duc la el), sau None."""
	return numarSiCate(session)[0]


# ---------------------------------------------------------------- afisajul

class _Arata(object):
	"""Ce sta pe afisaj: desenul unei alegeri, cadrul lui, cand s-a citit valoarea si pana cand sta."""
	__slots__ = ("intrare", "desen", "cadru", "cadruLa", "pana", "cititLa", "pereche", "repeta", "sursa")

	def __init__(self, intrare, desen, pereche, acum, sursa):
		self.intrare = intrare
		self.desen = desen
		self.pereche = pereche
		self.cadru = 0
		self.cadruLa = acum
		self.cititLa = acum
		self.pana = None
		self.repeta = desen.bucla
		self.sursa = sursa

	def masti(self):
		return self.desen.cadre[self.cadru]


class _DataPersonaj(object):
	__slots__ = ("id", "perioada")

	def __init__(self, id_):
		self.id = id_
		self.perioada = 0


class _IntrarePersonaj(object):
	"""O expresie a personajului pe afisaj, in locul alegerii unui mesaj scurt: id-ul „personaj.<expresia>”."""
	__slots__ = ("d", "expresie")

	def __init__(self, expresie):
		self.expresie = expresie
		self.d = _DataPersonaj("personaj." + expresie.id)

	def id(self):
		return self.d.id


def cuEticheta(d, desen):
	"""Eticheta scurta a datei (1 s), apoi desenul valorii."""
	scurt = D.SCURT.get(d.id)
	if not scurt or desen.bucla:
		return desen
	cadre = [L.potrivit(scurt)] + desen.cadre
	durate = [ETICHETA_MS] + desen.durate
	return D.Desen(cadre, durate, derulat=True)


class Afisaj(object):
	"""Tine afisajul la zi: rotirea, derularea, mesajele scurte, asteptarea si luminozitatea."""

	def __init__(self, session, cale=None, ceas=None):
		self.session = session
		self.cale = cale or DISPOZITIV
		self.ceas = ceas or time.time
		self.ctx = D.Context(session, self.ceas)
		self.ultim = None           # ultimul sir scris cu succes (octetii, ca text latin-1)
		self.eroare = None          # ultima eroare de scriere (o singura data in jurnal)
		self.inAsteptare = False
		self.lista = []
		self.evenimente = {}
		self.previzualizare = None  # lista de pe ecranul de alegere, inainte de salvare
		self.previzualizareAsteptare = None
		self.previzualizarePana = None  # pagina web: pana cand tine previzualizarea fara o cerere noua
		self.index = 0
		self.arata = None           # alegerea de pe afisaj (lista sau asteptarea)
		self.mesajul = None         # mesajul scurt, peste lista
		self.zap = False
		self.pierdut = False        # tunerul a pierdut semnalul (evTuneFailed)
		self.motorPana = None       # pana cand se urmareste antena cu motor (dupa un zap), sau None
		self.motorMergea = False
		self.reciteste = False
		self.lumina = None          # treapta de luminozitate scrisa
		self.eroareLumina = False
		self.lucrari = {}           # citirile de disc: cheie -> {"rezultat", "cand", "lucreaza"}
		self.zavor = threading.Lock()
		self.firPeLoc = False       # probele de pe PC: citirea de disc pe loc, fara fir
		self.legatVolum = False
		self.oprit = False
		self.pastreazaLaOprire = False  # actualizarea imaginii: „UPD” ramane pe afisaj dupa oprirea interfetei
		self.personaj = P.Personaj()    # modul „Personaj”: ce expresie si cand (setarile in citesteSetarile)
		self.scrisLa = None             # cand s-a scris ultima data (expresiile tin CADRU_MINIM_S intre scrieri)
		self.recEsuatLa = None          # cand a esuat ultima data o inregistrare
		from enigma import eTimer
		self.timer = eTimer()
		self.timer.callback.append(self._laCeas)
		self.citesteSetarile()
		if session is not None:
			nav = session.nav
			nav.event.append(self._laEveniment)
			if isinstance(getattr(nav, "record_event", None), list):
				nav.record_event.append(self._laInregistrare)
		from Components.config import config
		# setarile nu au notificari aici: ecranul si pagina web le schimba prin seteaza(), care aplica pe loc
		config.misc.standbyCounter.addNotifier(self._intraInAsteptare, initial_call=False)
		self._legaUsb(True)

	# ---- setarile ----

	def citesteSetarile(self):
		c = _cfg()
		self.lista = citesteLista(c.lista.value)
		self.evenimente = citesteEvenimente(c.evenimente.value)
		self.personaj.seteaza(c.personaj.value == "pornit", c.personaj_ritm.value, c.personaj_noaptea.value,
			self.ceas())

	def listaActiva(self):
		lista = self.previzualizare if self.previzualizare is not None else self.lista
		return lista or citesteLista(ORA)

	def viteza(self):
		try:
			return int(_cfg().viteza.value)
		except (ValueError, AttributeError):
			return int(VITEZA_IMPLICITA)

	def _trebuieNumar(self):
		ids = set(i.d.id for i in self.listaActiva())
		if ids.intersection(_CER_NUMARUL):
			return True
		f = self.evenimente.get("evenimente.zap")
		return f is not None and f.id in ("numar_nume", "numar")

	# ---- oprirea ----

	def opreste(self):
		self.oprit = True
		self.timer.stop()
		if self.session is not None:
			nav = self.session.nav
			if self._laEveniment in nav.event:
				nav.event.remove(self._laEveniment)
			rec = getattr(nav, "record_event", None)
			if isinstance(rec, list) and self._laInregistrare in rec:
				rec.remove(self._laInregistrare)
		from Components.config import config
		notificari = config.misc.standbyCounter.notifiers
		if self._intraInAsteptare in notificari:
			notificari.remove(self._intraInAsteptare)
		self._legaVolumul(False)
		self._legaUsb(False)
		if not self.pastreazaLaOprire:
			self.scrie(GOL)

	# ---- scrierea ----

	def scrie(self, sir):
		"""Scrie sirul de LATIME octeti (text latin-1, din HdsAfisajLitere.octeti) in dispozitiv."""
		sir = (sir + GOL)[:LATIME]
		try:
			fd = os.open(self.cale, _DESCHIDERE)
			try:
				os.write(fd, sir.encode("latin-1"))
			finally:
				os.close(fd)
		except (OSError, UnicodeError) as e:
			if self.eroare != getattr(e, "errno", -1):
				_jurnal("nu pot scrie in %s: %s" % (self.cale, e))
			self.eroare = getattr(e, "errno", -1)
			return False
		self.eroare = None
		self.ultim = sir
		return True

	def masti(self):
		"""Mastile de pe afisaj acum (dupa ultimul sir scris)."""
		return mastiDinSir(self.ultim)

	# ---- pasul ----

	def _laCeas(self):
		if self.oprit:
			return
		try:
			ms = self.pas()
		except Exception as e:
			_jurnal("pasul afisajului: %r" % (e,))
			ms = int(DORMI_MAXIM_S * 1000)
		self.timer.start(ms, True)

	def acum(self):
		"""Un pas pe loc (dupa o schimbare), apoi ceasul se pune din nou."""
		self.timer.stop()
		self._laCeas()

	actualizeaza = acum

	def reporneste(self):
		"""Alegerea de acum se ia de la capat (setarile s-au schimbat)."""
		self.arata = None
		self.index = 0
		self.acum()

	def pas(self, acum=None):
		"""Un pas: cadrul de acum pe afisaj; intoarce cate ms pana la pasul urmator."""
		acum = self.ceas() if acum is None else acum
		self._legaVolumul(True)
		if self.previzualizarePana is not None and acum + TOLERANTA_S >= self.previzualizarePana:
			# pagina web care a previzualizat s-a inchis fara „Salvează” sau „Renunță”: inapoi la lista salvata
			self.previzualizare = None
			self.previzualizareAsteptare = None
			self.previzualizarePana = None
			self.arata = None
			self.index = 0
		if self.zap:
			self._zapul(acum)
		if self.pierdut:
			self._pierdutul()
		if self.motorPana is not None:
			self._motorul(acum)
		if self.mesajul is not None and acum + TOLERANTA_S >= self.mesajul.pana:
			self.mesajul = None
			self.arata = None      # alegerea intrerupta reia de la capat
		self._personajul(acum)
		if self.mesajul is not None:
			a = self.mesajul
		elif self.inAsteptare:
			a = self._asteptare(acum)
		else:
			a = self._rotire(acum)
		self._avanseaza(a, acum)
		sir = L.octeti(a.masti()).decode("latin-1")
		# dupa o scriere cazuta se incearca din nou, chiar daca sirul e acelasi cu ultimul scris
		if sir != self.ultim or self.eroare is not None:
			if self.scrie(sir):
				self.scrisLa = acum
		self._lumineaza(acum)
		return self._pana(a, acum)

	def _pana(self, a, acum):
		"""Milisecundele pana la pasul urmator: cadrul urmator, sfarsitul alegerii, recitirea valorii, cel mult
		DORMI_MAXIM_S (luminozitatea de noapte, alegerile care reapar)."""
		cand = [acum + DORMI_MAXIM_S]
		ms = a.desen.durate[a.cadru]
		if len(a.desen.cadre) > 1 and ms > 0 and (a.repeta or a.cadru + 1 < len(a.desen.cadre)):
			cand.append(a.cadruLa + ms / 1000.0)
		if a.pana is not None:
			cand.append(a.pana)
		if self.previzualizarePana is not None:
			cand.append(self.previzualizarePana)
		if self.motorPana is not None:
			cand.append(acum + MOTOR_PAS_S)
		if self.mesajul is None:
			r = self._candCiteste(a)
			if r is not None:
				cand.append(r)
		r = self._personajCand(acum)
		if r is not None:
			cand.append(r)
		return max(20, int((min(cand) - acum) * 1000.0 + 0.5))

	def _avanseaza(self, a, acum):
		n = len(a.desen.cadre)
		pasi = 0
		while n > 1 and pasi <= n:
			ms = a.desen.durate[a.cadru]
			if ms <= 0:
				break
			sfarsit = a.cadruLa + ms / 1000.0
			if acum + TOLERANTA_S < sfarsit:
				break
			if a.cadru + 1 < n:
				a.cadru += 1
			elif a.repeta:
				a.cadru = 0
			else:
				break
			a.cadruLa = sfarsit
			pasi += 1
		if pasi > n:
			a.cadruLa = acum     # ceasul a intarziat mult: nu se prind din urma toti pasii

	# ---- valorile ----

	def _valoare(self, d):
		v = D.citeste(d, self.ctx)
		if isinstance(v, D.Lucru):
			return self._dinFir(v, d)
		return v

	def _dinFir(self, lucru, d):
		acum = self.ceas()
		with self.zavor:
			st = self.lucrari.get(lucru.cheie)
			vechi = st is None or (not st["lucreaza"] and acum - st["cand"] >= max(1.0, d.perioada))
		if vechi:
			self._pornesteLucrul(lucru)
			with self.zavor:
				st = self.lucrari.get(lucru.cheie)
		if st is None or st["rezultat"] is None:
			return None
		try:
			return lucru.transforma(st["rezultat"])
		except Exception:
			return None

	def _pornesteLucrul(self, lucru):
		with self.zavor:
			st = self.lucrari.setdefault(lucru.cheie, {"rezultat": None, "cand": 0.0, "lucreaza": False})
			if st["lucreaza"]:
				return
			st["lucreaza"] = True
		ceas = self.ceas

		def lucreaza():
			try:
				r = lucru.functie()
			except Exception:
				r = None
			with self.zavor:
				st["rezultat"] = r
				st["cand"] = ceas()
				st["lucreaza"] = False
		if self.firPeLoc:
			lucreaza()
			return
		fir = threading.Thread(target=lucreaza, name="HdsAfisaj")
		fir.daemon = True
		fir.start()

	def _candCiteste(self, a):
		p = a.intrare.d.perioada
		if p <= 0:
			return None
		if p == 60:
			return (int(a.cititLa // 60) + 1) * 60.0 + 0.2     # inceputul minutului urmator
		if p == 1:
			return int(a.cititLa) + 1.05
		return a.cititLa + p

	def _fa(self, intrare, acum, singur, sursa):
		"""Citeste valoarea si face desenul unei alegeri; None cand nu e nimic de aratat."""
		v = self._valoare(intrare.d)
		per = D.pereche(intrare.d, intrare.f, v)
		desen = D.deseneaza(per, self.viteza(), singur)
		if desen is None:
			return None
		if intrare.eticheta:
			desen = cuEticheta(intrare.d, desen)
		a = _Arata(intrare, desen, per, acum, sursa)
		a.repeta = singur or intrare.durata > 0 or desen.bucla
		if not singur:
			a.pana = acum + self._durata(intrare, desen)
		return a

	def _durata(self, intrare, desen):
		if intrare.durata:
			return float(intrare.durata)
		if desen.fix():
			return DURATA_FIXA_S
		total = desen.durataTotala() / 1000.0
		if desen.bucla:
			return max(DURATA_BUCLA_S, total)
		if desen.durate[-1] <= 0:
			return total + DURATA_FIXA_S
		return total

	def _reciteste(self, a, acum, singur):
		"""Valoarea alegerii de pe afisaj, citita din nou. False cand nu mai e nimic de aratat."""
		a.cititLa = acum
		v = self._valoare(a.intrare.d)
		per = D.pereche(a.intrare.d, a.intrare.f, v)
		if per is None:
			return False
		if per == a.pereche:
			return True
		desen = D.deseneaza(per, self.viteza(), singur)
		if desen is None:
			return False
		if a.intrare.eticheta:
			desen = cuEticheta(a.intrare.d, desen)
		a.pereche = per
		if desen.cadre == a.desen.cadre:
			return True
		if not (a.desen.fix() and desen.fix()):
			a.cadru = 0
			a.cadruLa = acum
		a.desen = desen
		return True

	def _deCitit(self, a, acum):
		r = self._candCiteste(a)
		return r is not None and acum + TOLERANTA_S >= r

	# ---- lista si asteptarea ----

	def _rotire(self, acum):
		lista = self.listaActiva()
		a = self.arata
		if a is None or a.sursa != "rotire":
			return self._porneste(lista, self.index, acum)
		if a.pana is not None and acum + TOLERANTA_S >= a.pana:
			return self._porneste(lista, self.index + 1, acum)
		if self.reciteste or self._deCitit(a, acum):
			self.reciteste = False
			if not self._reciteste(a, acum, len(lista) == 1):
				return self._porneste(lista, self.index + 1, acum)
		return a

	def _porneste(self, lista, start, acum):
		n = len(lista)
		for k in range(n):
			i = (start + k) % n
			a = self._fa(lista[i], acum, n == 1, "rotire")
			if a is not None:
				self.index = i
				self.arata = a
				return a
		# nimic de aratat acum: ora, pana la urmatoarea incercare
		d, f = D.alegere(ORA)
		a = self._fa(Intrare(d, f), acum, True, "rotire")
		a.pana = acum + DURATA_FIXA_S
		self.index = (start - 1) % n if n else 0     # urmatoarea incercare porneste tot de la `start`
		self.arata = a
		return a

	def _asteptare(self, acum):
		a = self.arata
		if a is not None and a.sursa == "asteptare" and not self.reciteste and not self._deCitit(a, acum):
			return a
		self.reciteste = False
		cheie = self.previzualizareAsteptare or _cfg().asteptare.value
		d, f = D.alegere(ALEGERE_ASTEPTARE.get(cheie, ALEGERE_ASTEPTARE[ASTEPTARE_IMPLICIT]))
		nou = self._fa(Intrare(d, f), acum, True, "asteptare")
		if nou is None:
			d, f = D.alegere(ALEGERE_ASTEPTARE["ora"])
			nou = self._fa(Intrare(d, f), acum, True, "asteptare")
		if a is not None and a.sursa == "asteptare" and nou.desen.cadre == a.desen.cadre:
			a.cititLa = acum       # acelasi desen: animatia (ora si data pe rand) merge mai departe
			return a
		self.arata = nou
		return nou

	# ---- mesajele scurte ----

	def mesaj(self, id_data, valoare, secunde=None):
		"""Un mesaj scurt peste lista (volumul, cifrele tastate, canalul nou...), numai daca e ales si receptorul nu e
		in asteptare. Intoarce True daca s-a aratat. Unele mesaje sunt si evenimente ale personajului: expresia lor
		trece dupa mesaj (sau singura, cand mesajul nu e ales)."""
		self._personajEveniment(_PERSONAJ_LA_MESAJ.get(id_data), valoare)
		if not self._puneMesaj(id_data, valoare, secunde):
			return False
		self.acum()
		return True

	def _puneMesaj(self, id_data, valoare, secunde=None):
		f = self.evenimente.get(id_data)
		d = D.DUPA_ID.get(id_data)
		if f is None or d is None or self.inAsteptare or self.oprit:
			return False
		per = D.pereche(d, f, valoare)
		acum = self.ceas()
		m = self.mesajul
		if m is not None and m.intrare.d.id == id_data and m.pereche == per and per is not None and (m.desen.bucla or
				m.desen.fix()):
			# acelasi mesaj, aceeasi valoare, desen fix sau in bucla (antena care merge, progresul care sta): numai tine
			# mai mult, fara sa reia animatia de la capat
			m.pana = max(m.pana, acum + (secunde if secunde is not None else MESAJ_S))
			return True
		desen = D.deseneaza(per, self.viteza())
		if desen is None:
			return False
		if secunde is None:
			if desen.derulat and not desen.bucla:
				secunde = desen.durataTotala() / 1000.0
			else:
				secunde = MESAJ_S
		a = _Arata(Intrare(d, f), desen, per, acum, "mesaj")
		a.pana = acum + secunde
		self.mesajul = a
		return True

	def gataMesaj(self, id_data, dupa=0.0):
		"""Mesajul `id_data` (daca e pe afisaj) se incheie acum, sau peste `dupa` secunde."""
		if self.mesajul is not None and self.mesajul.intrare.d.id == id_data:
			self.mesajul.pana = min(self.mesajul.pana, self.ceas() + dupa)
			self.acum()

	# ---- evenimentele ----

	def _laEveniment(self, ev):
		try:
			from enigma import iPlayableService
		except ImportError:
			return
		if ev == iPlayableService.evStart:
			# lista de canale e deja pe canalul nou dupa ce bucla termina zap-ul: numararea se face atunci, o data;
			# la evEnd nu se scrie nimic (intre doua numere ar aparea ora)
			self.zap = True
			self.timer.start(0, True)
		elif ev == iPlayableService.evTuneFailed:
			# semnalul s-a pierdut (la zap sau pe acelasi canal): numai „----”, daca e ales; canalul e acelasi
			self.pierdut = True
			self.timer.start(0, True)
		elif ev is not None and ev in [getattr(iPlayableService, n, None) for n in _EV_INFO]:
			self.ctx.laInfo()
			self.reciteste = True
			self.timer.start(0, True)

	def _pierdutul(self):
		self.pierdut = False
		self.ctx.laInfo()
		self.reciteste = True
		self._puneMesaj("evenimente.fara_semnal", True)
		self._personajEveniment("semnal", pas=False)

	def _zapul(self, acum=None):
		self.zap = False
		self.ctx.laZap()
		if self._trebuieNumar():
			ids = set(i.d.id for i in self.listaActiva())
			numar, cate = numarSiCate(self.session, "canal.cate" in ids)
			self.ctx.numar = numar
			self.ctx.cate = cate
			self.ctx.numarAflat = True
		if self.arata is not None and self.arata.sursa == "rotire":
			self.arata = None          # alegerea de acum, cu valorile canalului nou
		if self.mesajul is not None and self.mesajul.intrare.d.id in _SE_INCHEIE_LA_ZAP:
			self.mesajul = None        # cifrele tastate au dus aici; numele si semnalul canalului vechi nu mai sunt
		if "evenimente.motor" in self.evenimente:
			self.motorPana = (self.ceas() if acum is None else acum) + MOTOR_ASTEAPTA_S
		if "evenimente.zap" in self.evenimente:
			self._puneMesaj("evenimente.zap", (self.ctx.numar, self.ctx.numeServiciu()))
		self._personajEveniment("canal", pas=False)

	def _motorul(self, acum):
		"""Antena cu motor, dupa un zap: cat se misca, mesajul ei (sagetile sau pozitia); la sosire, pozitia. Starea
		vine din Components/HdsMotorStare.py (o intrebare in nucleu), o data pe secunda, numai in fereastra de dupa zap
		si cat merge antena."""
		s = D.stareMotor()
		if s is not None and s.get("misca"):
			self.motorMergea = True
			self.motorPana = acum + MOTOR_PAS_S * 2
			self._puneMesaj("evenimente.motor", s, MOTOR_MESAJ_S)
			return
		if self.motorMergea:
			self.motorMergea = False
			self.motorPana = None
			if s is not None and s.get("grade") is not None and self._puneMesaj("evenimente.motor", s, MESAJ_S):
				return
			if self.mesajul is not None and self.mesajul.intrare.d.id == "evenimente.motor":
				self.mesajul.pana = acum
			return
		if acum + TOLERANTA_S >= self.motorPana:
			self.motorPana = None

	def _dupaZap(self):
		"""Zap-ul, pe loc (acelasi drum ca dupa evStart)."""
		self.zap = True
		self.acum()

	def _laInregistrare(self, serviciu, ev):
		try:
			from enigma import iRecordableService
		except ImportError:
			return
		if ev == getattr(iRecordableService, "evStart", None):
			if not self.mesaj("evenimente.rec", True):
				self.reciteste = True
				self.timer.start(0, True)
		elif ev == getattr(iRecordableService, "evEnd", None):
			# inregistrarea s-a terminat: zambetul, afara de cazul ca a esuat de curand
			acum = self.ceas()
			if self.recEsuatLa is None or not 0.0 <= acum - self.recEsuatLa <= REC_ESUAT_S:
				self._personajEveniment("rec_gata", pas=False)
			self.reciteste = True
			self.timer.start(0, True)
		elif ev in [getattr(iRecordableService, n, None) for n in _REC_ESUAT]:
			self.recEsuatLa = self.ceas()
			self._personajEveniment("rec_esuat")

	def _laPartitie(self, actiune, partitie):
		if actiune == "add" and getattr(partitie, "is_hotplug", False):
			self.mesaj("evenimente.usb", True)

	def _legaUsb(self, leaga):
		try:
			from Components.Harddisk import harddiskmanager
			lista = harddiskmanager.on_partition_list_change
		except Exception:
			return
		if leaga and self._laPartitie not in lista:
			lista.append(self._laPartitie)
		elif not leaga and self._laPartitie in lista:
			lista.remove(self._laPartitie)

	def _legaVolumul(self, leaga):
		"""Volumul (notificatorul config.audio.volume, scris de VolumeControl la fiecare schimbare) si mutul (fereastra
		Mute). VolumeControl apare dupa pornirea afisajului, deci legarea se incearca la fiecare pas pana reuseste."""
		if leaga == self.legatVolum:
			return
		try:
			from Components.config import config
			from Components.VolumeControl import VolumeControl
			vc = VolumeControl.instance
			volum = config.audio.volume
		except Exception:
			return
		if vc is None:
			return
		mut = getattr(getattr(vc, "muteDialog", None), "onShow", None)
		if leaga:
			volum.addNotifier(self._laVolum, initial_call=False)
			if isinstance(mut, list):
				mut.append(self._laMut)
		else:
			if self._laVolum in volum.notifiers:
				volum.notifiers.remove(self._laVolum)
			if isinstance(mut, list) and self._laMut in mut:
				mut.remove(self._laMut)
		self.legatVolum = leaga

	def _laVolum(self, element):
		try:
			self.mesaj("evenimente.volum", int(element.value))
		except (TypeError, ValueError):
			pass

	def _laMut(self):
		self.mesaj("evenimente.mut", True)

	def _intraInAsteptare(self, element):
		try:
			from Screens.Standby import inStandby
		except ImportError:
			inStandby = None
		if inStandby is None:
			return
		self.inAsteptare = True
		self.mesajul = None
		self.arata = None
		if self._iesiDinAsteptare not in inStandby.onClose:
			inStandby.onClose.append(self._iesiDinAsteptare)
		self._personajEveniment("asteptare", pas=False)
		self.acum()

	def _iesiDinAsteptare(self):
		self.inAsteptare = False
		self.arata = None
		# o scriere din asteptare poate fi aruncata de driver (vfd 0 si „off”): urmatorul sir se scrie oricum
		self.ultim = None
		self._personajEveniment("iesire_asteptare", pas=False)
		self.acum()

	# ---- personajul ----

	def _starePersonaj(self, acum):
		"""Ce trebuie sa stie HdsAfisajPersonaj.Personaj la pasul de acum (HdsAfisajPersonaj.Stare)."""
		m = self.mesajul
		stins = False
		if self.inAsteptare:
			stins = (self.previzualizareAsteptare or _cfg().asteptare.value) == "stins"
		return P.Stare(ocupat=m is not None and m.sursa != "personaj", inExpresie=m is not None and m.sursa == "personaj",
			inAsteptare=self.inAsteptare, stins=stins, noapte=self.esteNoapte(acum),
			previzualizare=self.previzualizare is not None,
			scrieDe=(self.scrisLa + P.CADRU_MINIM_S) if self.scrisLa is not None else 0.0)

	def _personajul(self, acum):
		"""Expresia personajului care incepe acum (a unui eveniment sau la intamplare), ca mesaj cu sursa „personaj”."""
		if not self.personaj.pornit:
			return
		e = self.personaj.pas(acum, self._starePersonaj(acum))
		if e is not None:
			self._puneExpresia(e, acum)

	def _puneExpresia(self, e, acum):
		desen = P.desen(e)
		a = _Arata(_IntrarePersonaj(e), desen, ("personaj", e.id), acum, "personaj")
		a.pana = acum + desen.durataTotala() / 1000.0
		self.mesajul = a

	def _personajCand(self, acum):
		"""Cand vine urmatoarea expresie (pentru ceasul motorului), sau None."""
		if not self.personaj.pornit:
			return None
		return self.personaj.cand(acum, self._starePersonaj(acum))

	def _personajEveniment(self, nume, valoare=None, pas=True):
		"""Un eveniment al personajului. pas=True: in afara pasului motorului, deci pasul se face imediat dupa."""
		if nume is None or self.oprit or not self.personaj.pornit:
			return
		if self.personaj.eveniment(nume, self.ceas(), valoare) and pas:
			self.timer.start(0, True)

	def arataExpresia(self, e):
		"""Previzualizarea din ecran si din pagina web: expresia pe afisaj acum, o data (si cu modul oprit)."""
		self._puneExpresia(e, self.ceas())
		self.acum()

	# ---- luminozitatea ----

	def esteNoapte(self, acum=None):
		"""Ora de acum e in noaptea afisajului („Noaptea începe”, „Noaptea se termină”): luminozitatea si personajul."""
		c = _cfg()
		h = time.localtime(self.ceas() if acum is None else acum).tm_hour
		try:
			de_la, pana_la = int(c.noapte_de_la.value), int(c.noapte_pana_la.value)
		except ValueError:
			de_la, pana_la = int(NOAPTE_DE_LA_IMPLICIT), int(NOAPTE_PANA_LA_IMPLICIT)
		return (h >= de_la or h < pana_la) if de_la > pana_la else (de_la <= h < pana_la)

	def treaptaDorita(self, acum=None):
		"""Treapta de luminozitate (1-7) pentru ora de acum, sau None: nu se scrie nimic."""
		c = _cfg()
		zi, noapte = c.luminozitate.value, c.luminozitate_noapte.value
		if zi == LUMINA_NESCHIMBATA and noapte == NOAPTE_LA_FEL:
			return None
		noaptea = self.esteNoapte(acum)
		if noaptea and noapte != NOAPTE_LA_FEL:
			return int(noapte)
		# ziua „neschimbata” dupa o noapte mai slaba: inapoi la treapta cea mai mare
		return int(zi) if zi != LUMINA_NESCHIMBATA else len(TREPTE_LUMINA)

	def _lumineaza(self, acum):
		treapta = self.treaptaDorita(acum)
		if treapta is None or treapta == self.lumina:
			return
		self.lumina = treapta
		if not os.path.exists(LUMINOZITATE):
			return
		try:
			with open(LUMINOZITATE, "w", encoding="ascii") as f:
				f.write(TREPTE_LUMINA[max(1, min(len(TREPTE_LUMINA), treapta)) - 1])
			self.eroareLumina = False
		except (IOError, OSError) as e:
			if not self.eroareLumina:
				_jurnal("nu pot scrie luminozitatea: %s" % e)
			self.eroareLumina = True

	# ---- starea, pentru ecran si web ----

	def textAcum(self):
		"""Ce arata afisajul, ca text de citit (ecranul si pagina web): textul intreg al alegerii, fara derulare."""
		a = self.mesajul or self.arata
		if a is None or not a.pereche:
			return u""
		fel, continut = a.pereche
		if fel in ("fix", "dreapta", "derulat", "punct"):
			return L.transcrie(continut)
		if fel == "bara":
			return u"%d%%" % int(round(max(0.0, min(1.0, float(continut))) * 100))
		if fel == "alternat":
			return u" / ".join(L.transcrie(x) for x in continut)
		if fel == "secventa":
			return u" ".join(L.transcrie(x[1]) for x in continut)
		if fel == "personaj":
			return P.textAcum(continut)
		return u""

	def ceArata(self):
		"""(sursa, id-ul alegerii) de pe afisaj acum: sursa e „rotire”, „asteptare” sau „mesaj”."""
		a = self.mesajul or self.arata
		if a is None:
			return None, None
		return a.sursa, a.intrare.id()


# citirile care fac diferente intre doua momente (procesorul, reteaua, debitul frecventei): o citire la deschidere, ca
# prima valoare aratata sa aiba deja una de dinainte
_CU_DIFERENTA = ("receptor.incarcare", "retea.viteza", "semnal.debit")


class Valori(object):
	"""Valorile de acum pentru ecranul de alegere si pentru pagina web: citite cu un Context al lor (numarul canalului
	numarat o data, la deschidere); citirile de disc raman cele tinute de afisaj (sau lipsesc, si se arata exemplul).
	O data se citeste o singura data pe moment (cel mult o data pe secunda, sau cat perioada ei, cel mult VALOARE_S):
	formatele aceleiasi date dintr-o grupa au aceeasi valoare, iar o citire cu diferenta nu se face de doua ori la rand."""

	VALOARE_S = 5.0

	def __init__(self, session):
		self.session = session
		self.ctx = D.Context(session)
		self.numaratLa = 0.0
		self._memo = {}
		for id_ in _CU_DIFERENTA:
			d = D.DUPA_ID.get(id_)
			if d is not None:
				D.citeste(d, self.ctx)

	def reimprospateaza(self):
		"""Inaintea unei noi citiri (pagina web, la cateva secunde): informatiile serviciului se citesc din nou, iar
		citirile care fac diferente (procesorul, reteaua) raman legate de cea de dinainte; numarul canalului se
		numara din nou cel mult o data la RENUMARARE_S."""
		self.ctx.laInfo()
		if self.ctx.ceas() - self.numaratLa >= RENUMARARE_S:
			self.ctx.numarAflat = False
			for id_ in _CER_NUMARUL:
				self._memo.pop(id_, None)

	def _numara(self):
		"""Numarul canalului si cate canale are buchetul: de la afisaj, daca le-a numarat, altfel o data aici."""
		if self.ctx.numarAflat:
			return
		self.ctx.numarAflat = True
		self.numaratLa = self.ctx.ceas()
		a = _afisaj
		if a is not None and a.ctx.numarAflat and a.ctx.cate is not None:
			self.ctx.numar, self.ctx.cate = a.ctx.numar, a.ctx.cate
			return
		try:
			self.ctx.numar, self.ctx.cate = numarSiCate(self.session, True)
		except Exception as e:
			_jurnal("numarul canalului: %r" % (e,))

	def valoare(self, d):
		acum = self.ctx.ceas()
		m = self._memo.get(d.id)
		if m is not None and acum - m[0] < min(self.VALOARE_S, max(1.0, d.perioada)) and acum >= m[0]:
			return m[1]
		v = self._citeste(d)
		self._memo[d.id] = (acum, v)
		return v

	def _citeste(self, d):
		if d.id in _CER_NUMARUL:
			self._numara()
		v = D.citeste(d, self.ctx)
		if isinstance(v, D.Lucru):
			a = _afisaj
			st = a.lucrari.get(v.cheie) if a is not None else None
			if not st or st.get("rezultat") is None:
				return None
			try:
				return v.transforma(st["rezultat"])
			except Exception:
				return None
		return v

	def desen(self, d, f, viteza, singur=False):
		"""(Desen, exemplu) pentru o alegere: valoarea de acum, altfel exemplul (exemplu=True)."""
		desen = D.deseneaza(D.pereche(d, f, self.valoare(d)), viteza, singur)
		if desen is not None:
			return desen, False
		return D.desenExemplu(d, f, viteza, singur), True


def mastiDinSir(sir):
	"""Mastile pe care le aprinde un sir scris in afisaj (inversul lui HdsAfisajLitere.octeti)."""
	if not sir:
		return [L.GOL] * LATIME
	invers = _inversOcteti()
	return [invers.get(ord(c), L.GOL) for c in (sir + GOL)[:LATIME]]


_INVERS = {}


def _inversOcteti():
	if not _INVERS:
		for m, o in L.OCTET_PENTRU_FORMA.items():
			_INVERS[o] = m
	return _INVERS


_afisaj = None


def porneste(session):
	"""Din mytest.py, dupa ce exista sesiunea. Fara afisaj nu face nimic."""
	global _afisaj
	initConfig()
	if _afisaj is not None or not disponibil():
		return
	_afisaj = Afisaj(session)
	_afisaj.acum()
	_afisaj.mesaj("evenimente.pornire", True)


def opreste():
	"""La iesirea din enigma2: afisajul ramane gol (in oprirea completa il tine microcontrolerul)."""
	global _afisaj
	if _afisaj is not None:
		_afisaj.opreste()
		_afisaj = None


def actualizeaza():
	if _afisaj is not None:
		_afisaj.acum()


def arataInAsteptare():
	"""False numai cand asteptarea e „nimic” (stins); pentru /proc/stb/power/vfd (Components/HdsStandbyTv.py)."""
	try:
		return _cfg().asteptare.value != "stins"
	except Exception as e:
		_jurnal("asteptarea: %r" % (e,))
		return True


def motorPornit():
	"""Pentru comenzile motorului date fara zap (rotirea din ecranul antenei): rotirea se urmareste pe afisaj de acum,
	ca dupa un zap. Nu arunca."""
	if _afisaj is None:
		return
	try:
		if "evenimente.motor" in _afisaj.evenimente and not _afisaj.inAsteptare:
			_afisaj.motorPana = _afisaj.ceas() + MOTOR_ASTEAPTA_S
			_afisaj.timer.start(0, True)
	except Exception as e:
		_jurnal("motorul: %r" % (e,))


ACTUALIZARE_S = 3600.0


def actualizare(pornita=True, procent=None):
	"""Actualizarea imaginii (ecranul de actualizare, inainte de scriere): „UPD” (sau U si procentul) pe afisaj, daca
	mesajul „Actualizarea imaginii” e ales, si afisajul nu se mai goleste la oprirea interfetei (scrierea merge cu
	enigma2 oprit, deci „UPD” ramane cat scrie). pornita=False: scrierea nu a pornit, afisajul revine. Nu arunca."""
	if _afisaj is None:
		return False
	try:
		if not pornita:
			_afisaj.pastreazaLaOprire = False
			_afisaj.gataMesaj("evenimente.actualizare")
			return True
		arata = _afisaj.mesaj("evenimente.actualizare", True if procent is None else int(procent), ACTUALIZARE_S)
		_afisaj.pastreazaLaOprire = bool(arata)
		return arata
	except Exception as e:
		_jurnal("actualizarea: %r" % (e,))
		return False


def arataExpresia(id_expresie):
	"""Ecranul si pagina web: expresia aleasa a personajului pe afisaj, acum, o data (si cu modul oprit). Intoarce
	(reusit, mesaj)."""
	e = P.expresie(id_expresie)
	if e is None:
		return False, _("Valoarea „%s” nu se poate alege aici.") % ("%s" % id_expresie)[:20]
	if _afisaj is None:
		return False, _("Afișajul pornește după ce receptorul termină pornirea.")
	try:
		_afisaj.arataExpresia(e)
	except Exception as eroare:
		_jurnal("expresia %s: %r" % (e.id, eroare))
		return False, _("Afișajul nu primește textul. Repornește receptorul.")
	return True, P.textArata(e)


def mesaj(id_data, valoare, secunde=None):
	"""Pentru alte module: un mesaj scurt pe afisaj (de ex. progresul unei cautari). Nu arunca."""
	if _afisaj is None:
		return False
	try:
		return _afisaj.mesaj(id_data, valoare, secunde)
	except Exception as e:
		_jurnal("mesaj %s: %r" % (id_data, e))
		return False


def cifre(text):
	"""Cifrele tastate pe telecomanda (fereastra NumberZap), pana la ultima + CIFRE_S."""
	return mesaj("evenimente.cifre", text, CIFRE_S)


def cifreGata():
	"""Fereastra NumberZap s-a inchis: cifrele raman cel mult CIFRE_DUPA_OK_S, pana la zap (evStart le incheie), ca
	intre cifre si canalul nou sa nu apara valorile canalului vechi."""
	if _afisaj is not None:
		try:
			_afisaj.gataMesaj("evenimente.cifre", CIFRE_DUPA_OK_S)
		except Exception as e:
			_jurnal("cifrele: %r" % (e,))


def stare():
	"""Pentru ecran si pentru GET /api/afisaj."""
	c = _cfg()
	if _afisaj is not None:
		masti = _afisaj.masti() if _afisaj.ultim is not None else [L.GOL] * LATIME
		in_asteptare = _afisaj.inAsteptare
		scris = _afisaj.eroare is None and _afisaj.ultim is not None
		sursa, alegerea = _afisaj.ceArata()
		text = _afisaj.textAcum()
	else:
		masti = [L.GOL] * LATIME
		in_asteptare = False
		scris = False
		sursa, alegerea = None, None
		text = u""
	return {
		"disponibil": disponibil(),
		"pornit": _afisaj is not None,
		"in_asteptare": in_asteptare,
		"scris": scris,
		"masti": list(masti),
		"desen": L.desenText(masti),
		"text": text,
		"sursa": sursa,
		"alegerea": alegerea,
		"lista": scrieLista(citesteLista(c.lista.value)),
		"evenimente": scrieEvenimente(citesteEvenimente(c.evenimente.value)),
		"asteptare": c.asteptare.value,
		"viteza": c.viteza.value,
		"luminozitate": c.luminozitate.value,
		"luminozitate_noapte": c.luminozitate_noapte.value,
		"noapte_de_la": c.noapte_de_la.value,
		"noapte_pana_la": c.noapte_pana_la.value,
		"text_tau": c.text.value,
		"oras": c.oras.value,
		"personaj": c.personaj.value,
		"personaj_ritm": c.personaj_ritm.value,
		"personaj_noaptea": c.personaj_noaptea.value,
		"minutar": D.minutarRamas(time.time()),
		"minutar_text": textMinutar(),
		"cronometru_text": textCronometru(),
	}

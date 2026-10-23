# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Culegerea canal cu canal: trecerea prin toate serviciile din lamedb (TV si radio), pornite pe rand, ca culegerea la
vizionare (Components/HdsCulegereCanale.py) sa noteze in baza unica tot ce se afla numai cand canalul chiar ruleaza:
imaginea (latime, inaltime, progresiv, cadre, codec), accesul (CAID-uri, PID-uri ECM), PID-urile si pistele.
Pe ecran si in web numele e „Scanare detaliată”; in cod ramane culegerea (fisierele, clasele, cheile, starea,
CHEIE_PAZNIC), ca setarile si reluarea sa nu se strice.

CE FACE MODULUL (in baza noteaza culegerea obisnuita, cu pragul si bugetul ei de scrieri; trecerea cere o singura
scriere, la sfarsit, ca „Actualizează pistele”):
  planul      serviciile de satelit din lamedb (HdsIndexCanale.citeste_lamedb: aceleasi excluderi ca lista de cautare,
              fara serviciile ascunse si purtatoarele T2-MI / ETI), alese dupa pozitie (toate sau una) si acces (toate
              sau numai FTA), in ordinea pozitiei si a transponderului: de la pozitia de acum spre capatul mai apropiat
              al arcului, apoi spre celalalt (antena trece o singura data prin fiecare pozitie); pe transponder intai
              TV, apoi radio, dupa SID. Fluxurile (DAB+ si DVB-T2 prin releu, internet) nu sunt in lamedb si nu intra.
  necunoscute  canalele carora baza nu le stie PMT-ul si accesul, iar la TV imaginea (inaltimea, sau numai codecul la
              un canal criptat); filtrul se face o data, la pornire, din randurile bazei.
  judecata    cand canalul e gata (judeca_note, dupa notele culegerii; judeca_vazut, dupa ce se vede din afara, pentru
              programul de noapte al imaginilor fara acest modul), cu termen pe canal si rabdare pentru motor;
              „fara semnal” sare tot transponderul.
  reluarea    starea (cheia urmatorului canal, numaratorile, transponderele fara semnal, mediile) intr-un fisier mic,
              scris rar si atomic; o trecere oprita continua de la acelasi canal cu aceleasi alegeri si acelasi lamedb.
  estimarea   secundele ramase: canalele ramase pe fel (mediile masurate in trecere) si mutarile motorului (modelul
              lui Components/HdsMotorViteza.py: T = t0 + grade / viteza).
  textele     aceleasi pentru ecran (Screens/HdsCulegereTotala.py) si pagina web (HdsWebControl/culegere_canale_web.py).

Partea de sus e curata (fara enigma): se probeaza pe PC
si o foloseste si programul de noapte pornit separat pe receptor. Trecerea pe receptor
(Trecere, cu eTimer, navigatia, ascultatorul de taste) e mai jos, cu importuri tarzii.
"""

from __future__ import absolute_import

import json
import os
import time

try:
	from Components import HdsIndexCanale as X
	from Components import HdsBazaCanale as B
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsIndexCanale as X
	import HdsBazaCanale as B

# timpii culegerii la vizionare (Components/HdsCulegereCanale.py: LINISTE_MS, VIDEO_MS, VIDEO_PORNIRE_MS)
LINISTE_S = 2.5
VIDEO_S = 1.5
VIDEO_PORNIRE_S = 6.0
# peste timpii culegerii: nota cade la capatul lor, pe firul enigma2, dupa alte evenimente
MARJA_S = 1.0

# termenele pe canal, de la pornirea lui (plus rabdarea pentru motor)
TERMEN_ZAP_S = 4.0          # referinta redata nu e cea ceruta (programul de noapte): canalul n-a pornit
TERMEN_PMT_S = 12.0         # fara PMT: fara semnal (sau fara serviciu pe transponder, cand semnalul e prins)
SEMNAL_MIN_S = 5.0          # „fara semnal” spus de imagine se crede abia dupa atat (acordarea normala ia sub o secunda)
TERMEN_IMAGINE_S = 10.0     # TV liber fara niciun cadru la atatea secunde dupa PMT: fara imagine
MOTOR_MARJA_S = 10.0
MOTOR_MAX_S = 120.0

# mediile de pornire (secunde pe canal), inlocuite de cele masurate in trecere
MEDIE_TV_S = 8.0
MEDIE_RADIO_S = 5.0
PONDERE_MEDIE = 0.1
# modelul motorului cand nu e niciun fisier (aceleasi presupuneri ca HdsMotorViteza)
MOTOR_T0_S = 2.0
MOTOR_VITEZA = 1.2

# starea: scrisa rar (atomic), la cel mult atatea canale sau secunde, si la oprire
CALE_STARE = "/etc/enigma2/hds-culegere-canale.json"
FEL_STARE = "hds-culegere-canale"
SCRIERE_CANALE = 100
SCRIERE_S = 600
MAX_STARE = 256 * 1024
MAX_TP_FARA_SEMNAL = 4000
MAX_LAMEDB = 32 * 1024 * 1024

# rezultatele unui canal
CULES = "cules"                 # tot ce se poate nota (imaginea la TV)
CRIPTAT = "criptat"             # canal criptat nedecodat: accesul si codecul
FARA_IMAGINE = "fara_imagine"   # TV liber fara cadre (canal de date, imagine oprita)
FARA_SEMNAL = "fara_semnal"     # transponderul nu se prinde; restul canalelor de pe el se sar
FARA_DATE = "fara_date"         # semnal prins, dar serviciul nu e pe transponder (PMT lipsa)
REFUZAT = "refuzat"             # canalul nu a pornit (de ex. control parental)
SARIT = "sarit"                 # sarit fara pornire (protejat, sau transponder fara semnal)
REZULTATE = (CULES, CRIPTAT, FARA_IMAGINE, FARA_SEMNAL, FARA_DATE, REFUZAT, SARIT)

# de ce s-a oprit trecerea
GATA = "gata"
OPRIT_TASTA = "tasta"
OPRIT_CERUT = "cerut"
OPRIT_INREGISTRARE = "inregistrare"
OPRIT_STANDBY = "standby"
OPRIT_ALT_CANAL = "alt_canal"
OPRIT_ORA = "ora"
OPRIT_EROARE = "eroare"


def _(text):
	"""Traducerea imaginii (builtins._); pe PC si in programul de noapte, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la afisare."""
	return text


def _jurnal(text):
	print("[HdsCulegereTotala] %s" % text)


def _monoton():
	return getattr(time, "monotonic", time.time)()


# ---------------------------------------------------------------- serviciile din lamedb

class Serviciu(object):
	"""Un serviciu de satelit din lamedb, cu ce trebuie planului."""
	__slots__ = ("ref", "cheie", "nume", "radio", "poz", "tp", "sid", "frecventa", "pol", "criptat")

	def __init__(self, ref, cheie, nume, radio, poz, tp, sid, frecventa=0, pol=0, criptat=False):
		self.ref = ref
		self.cheie = cheie
		self.nume = nume
		self.radio = radio
		self.poz = poz
		self.tp = tp            # (ns, tsid, onid)
		self.sid = sid
		self.frecventa = frecventa
		self.pol = pol
		self.criptat = criptat

	def cheie_tp(self):
		return "%x:%x:%x" % self.tp


def frecvente_lamedb(text):
	"""{(ns, tsid, onid): (frecventa kHz, polarizare)} pentru transponderele de satelit din lamedb (formatul 4 sau 5:
	„s frecventa:sr:pol:fec:pozitie:...”). Un rand care nu se intelege se sare."""
	rez = {}
	randuri = text.split("\n")
	n = len(randuri)
	i = 0
	while i < n and randuri[i].strip() != "transponders":
		i += 1
	i += 1
	while i + 1 < n and randuri[i].strip() != "end":
		cheie = randuri[i].strip().split(":")
		date = randuri[i + 1].strip()
		if date.startswith("s ") and len(cheie) >= 3:
			try:
				tp = (int(cheie[0], 16), int(cheie[1], 16), int(cheie[2], 16))
				campuri = date[2:].split(":")
				rez[tp] = (int(campuri[0]), int(campuri[2]))
			except (ValueError, IndexError):
				pass
		i += 1
		while i < n and randuri[i].strip() not in ("/", "end"):
			i += 1
		if i < n and randuri[i].strip() == "/":
			i += 1
	return rez


def servicii_din_lamedb(text):
	"""Textul lamedb -> [Serviciu] de satelit (TV si radio), fara cele ascunse si fara purtatoarele de fluxuri."""
	frecvente = frecvente_lamedb(text)
	rez = []
	for c in X.citeste_lamedb(text):
		if not isinstance(c.poz, int) or not c.cheie_mas:
			continue
		try:
			sid, ns, tsid, onid = [int(p, 16) for p in c.cheie_mas.split(":")]
		except ValueError:
			continue
		f, pol = frecvente.get((ns, tsid, onid), (0, 0))
		rez.append(Serviciu(c.ref, c.cheie_mas, c.nume, c.tip == "radio", c.poz, (ns, tsid, onid), sid, f, pol,
			c.acces == "criptat"))
	return rez


def citeste_lamedb(cale=None):
	"""(text, semnatura [mtime, marime]) al lamedb-ului, sau ("", None)."""
	cale = cale or os.path.join(X.DIRECTOR, "lamedb")
	try:
		st = os.stat(cale)
		with open(cale, "rb") as f:
			text = f.read(MAX_LAMEDB).decode("utf-8", "replace")
	except (IOError, OSError):
		return "", None
	return text, [int(st.st_mtime), int(st.st_size)]


# ---------------------------------------------------------------- alegerea si ordinea

def grade_semnate(poz):
	"""Pozitia orbitala (zecimi, 0-3599) -> zecimi cu semn, est pozitiv (30,0W = -300)."""
	return poz if poz <= 1800 else poz - 3600


def pozitii(servicii):
	"""[(pozitie, canale)] de la vest la est."""
	numar = {}
	for s in servicii:
		numar[s.poz] = numar.get(s.poz, 0) + 1
	return sorted(numar.items(), key=lambda e: grade_semnate(e[0]))


def alege(servicii, pozitie=None, numai_fta=False):
	"""Serviciile unei pozitii (None = toate) si, la cerere, numai cele fara CAID-uri in lamedb."""
	return [s for s in servicii if (pozitie is None or s.poz == pozitie) and not (numai_fta and s.criptat)]


def ordinea_pozitiilor(pozitii_, poz_start=None):
	"""Pozitiile in ordinea trecerii: de la cea de acum spre capatul mai apropiat al arcului, apoi spre celalalt.
	Drumul antenei e (distanta pana la capatul apropiat) + (lungimea arcului), cel mai scurt care trece prin toate."""
	sortate = sorted(set(pozitii_), key=grade_semnate)
	if not sortate or poz_start is None:
		return sortate
	s0 = grade_semnate(poz_start)
	vest = [p for p in sortate if grade_semnate(p) <= s0]
	est = [p for p in sortate if grade_semnate(p) > s0]
	vest.reverse()
	if not est or not vest:
		return vest + est
	if s0 - grade_semnate(vest[-1]) <= grade_semnate(est[-1]) - s0:
		return vest + est
	# capatul de est e mai aproape: intai spre est (pozitia de acum, daca are canale, ramane prima)
	acum = [p for p in vest if p == poz_start]
	return acum + est + [p for p in vest if p != poz_start]


def ordoneaza(servicii, poz_start=None):
	"""Planul: pozitiile in ordinea trecerii, apoi transponderele dupa frecventa si polarizare, apoi TV inaintea
	radioului, dupa SID."""
	rang = dict((p, i) for i, p in enumerate(ordinea_pozitiilor([s.poz for s in servicii], poz_start)))
	return sorted(servicii, key=lambda s: (rang.get(s.poz, 0), s.frecventa, s.pol, s.tp, s.radio, s.sid))


# ---------------------------------------------------------------- ce stie baza

def cunoscut(rec, radio):
	"""Baza stie tot ce poate aduce o vizionare: PMT-ul si accesul; la TV si imaginea (inaltimea, sau numai codecul la un
	canal criptat). rec = randul desfacut al bazei (HdsBazaCanale.BazaCanale.cauta) sau None."""
	if not rec:
		return False
	pmt = B.valoare_grupa(rec, "pmt")
	ca = B.valoare_grupa(rec, "ca")
	if not pmt or not ca:
		return False
	if radio:
		return True
	vd = B.valoare_grupa(rec, "vd")
	if not isinstance(vd, list) or len(vd) < 7:
		return False
	if isinstance(vd[1], int) and vd[1] > 0:
		return True
	return bool(ca[0] == 1 and vd[6])


def criptat_in_baza(baza, cheie):
	"""Baza a notat canalul ca criptat (grupa ca, primul camp 1)."""
	try:
		ca = B.valoare_grupa(baza.cauta(cheie), "ca")
	except Exception:
		return False
	return isinstance(ca, list) and bool(ca) and ca[0] == 1


def necunoscute(baza, servicii):
	"""Serviciile pe care baza nu le stie (cunoscut). Randurile se desfac numai pentru cheile care au textul grupelor
	cerute (chei_cu, alegere larga, fara desfacere): restul sunt necunoscute fara nicio citire."""
	cu_pmt = set(baza.chei_cu(("pmt",)))
	rez = []
	for s in servicii:
		if s.cheie not in cu_pmt:
			rez.append(s)
			continue
		if not cunoscut(baza.cauta(s.cheie), s.radio):
			rez.append(s)
	return rez


# ---------------------------------------------------------------- judecata pe canal

class Observatie(object):
	"""Ce se stie despre canalul pornit acum. Timpii sunt ai ceasului monoton al trecerii."""
	__slots__ = ("t0", "radio", "rabdare", "t_ref", "t_pmt", "criptat", "t_imagine", "inaltime", "fara_semnal",
		"vd_notat", "vd_inaltime")

	def __init__(self, t0, radio, rabdare=0.0):
		self.t0 = t0
		self.radio = radio
		self.rabdare = rabdare      # secundele in plus pentru o mutare a motorului
		self.t_ref = None           # cand canalul redat a devenit cel cerut
		self.t_pmt = None           # cand s-a vazut PMT-ul (sau nota culegerii)
		self.criptat = None         # True / False / None (nu se stie)
		self.t_imagine = None       # cand imaginea a inceput sa curga (cadre noi)
		self.inaltime = 0
		self.fara_semnal = None     # True / False / None: ce spune imaginea despre semnal
		self.vd_notat = False       # nota culegerii pe grupa vd (orice valoare)
		self.vd_inaltime = 0        # inaltimea din nota vd


def _fara_pmt(o, acum):
	"""Judecata cat PMT-ul lipseste: fara semnal, fara date sau inca nimic."""
	trecut = acum - o.t0
	if o.fara_semnal and trecut >= SEMNAL_MIN_S + o.rabdare:
		return FARA_SEMNAL
	if trecut >= TERMEN_PMT_S + o.rabdare:
		return FARA_DATE if o.fara_semnal is False else FARA_SEMNAL
	return None


def judeca_note(o, acum, asteapta_imagine=True):
	"""Pe receptor, dupa notele culegerii pe cheia canalului (HdsCulegereCanale.asculta): None = inca nu. PMT-ul si
	accesul se noteaza impreuna; imaginea in nota vd. Criptat nedecodat: culegerea noteaza codecul la VIDEO_PORNIRE_S
	dupa pornire sau, cand baza stie deja inaltimea, nimic; deci gata la nota vd sau dupa acel timp. asteapta_imagine=
	False (decodorul nu a dat imagine pe niciun canal liber): un TV liber se judeca precum unul criptat."""
	if o.t_pmt is None:
		return _fara_pmt(o, acum)
	if o.radio:
		return CULES
	if o.vd_inaltime > 0:
		return CULES
	# dupa PMT antena a ajuns: rabdarea motorului nu mai conteaza
	if o.criptat or not asteapta_imagine:
		if o.vd_notat or acum - o.t0 >= VIDEO_PORNIRE_S + MARJA_S:
			return CRIPTAT if o.criptat else FARA_IMAGINE
		return None
	if acum - o.t_pmt >= TERMEN_IMAGINE_S:
		return FARA_IMAGINE
	return None


def judeca_vazut(o, acum, imagine_min_s=0.0, asteapta_imagine=True):
	"""Din afara imaginii (programul de noapte): culegerea noteaza la timpii ei, deci se asteapta timpii plus MARJA_S
	dupa semnele vazute. PMT-ul nu se vede din afara (pistele si accesul vin intai din memoria canalului): t_pmt e
	prinderea semnalului plus o repetitie a PMT-ului, pusa de apelant. Cadrele noi = imagine; CAID-urile = criptat.
	imagine_min_s: cel mai devreme dupa pornire pentru o imagine. asteapta_imagine=False (decodorul nu da imagine pe
	niciun canal): un TV liber se judeca precum unul criptat, la VIDEO_PORNIRE_S, cand culegerea noteaza codecul."""
	trecut = acum - o.t0
	if o.t_ref is None:
		return REFUZAT if trecut >= TERMEN_ZAP_S else None
	if o.t_pmt is None:
		return _fara_pmt(o, acum)
	if acum - o.t_pmt < LINISTE_S + MARJA_S:
		return None
	if o.radio:
		return CULES
	if o.t_imagine is not None and o.inaltime > 0:
		if acum - o.t_imagine >= VIDEO_S + MARJA_S and trecut >= imagine_min_s:
			return CULES
		return None
	if o.criptat or not asteapta_imagine:
		if trecut >= VIDEO_PORNIRE_S + MARJA_S:
			return CRIPTAT if o.criptat else FARA_IMAGINE
		return None
	if acum - o.t_pmt >= TERMEN_IMAGINE_S:
		return FARA_IMAGINE
	return None


# ---------------------------------------------------------------- motorul si estimarea

def model_motor(esantioane=None):
	"""Modelul timpului unei mutari {t0, viteza} din mutarile masurate (HdsMotorViteza.potriveste), sau presupunerile."""
	if esantioane:
		try:
			try:
				from Components import HdsMotorViteza as V
			except ImportError:
				import HdsMotorViteza as V
			m = V.potriveste(esantioane)
			v = m["viteza"]
			return {"t0": float(m["t0"]), "viteza": (float(v["est"]) + float(v["vest"])) / 2.0}
		except Exception as e:
			_jurnal("modelul motorului: %s" % e)
	return {"t0": MOTOR_T0_S, "viteza": MOTOR_VITEZA}


def secunde_mutare(de_la, la, model=None):
	"""Cat ia mutarea antenei intre doua pozitii (zecimi): t0 + grade / viteza; 0 pe aceeasi pozitie."""
	if de_la is None or la is None or de_la == la:
		return 0.0
	model = model or model_motor()
	grade = abs(grade_semnate(la) - grade_semnate(de_la)) / 10.0
	return model["t0"] + grade / max(0.1, model["viteza"])


def rabdare_motor(de_la, la, motor, model=None):
	"""Secundele in plus pe primul canal de pe alta pozitie (mutarea prezisa plus o marja, cel mult MOTOR_MAX_S)."""
	if not motor or de_la == la:
		return 0.0
	if de_la is None:
		# pozitia de plecare nu se stie: cel mult un drum de la un capat la altul
		return MOTOR_MAX_S / 2
	return min(MOTOR_MAX_S, secunde_mutare(de_la, la, model) + MOTOR_MARJA_S)


def secunde_ramase(servicii, medii=None, motor=False, model=None, poz_acum=None):
	"""Estimarea pentru serviciile ramase (in ordinea planului): mediile pe fel si mutarile motorului."""
	medii = medii or {}
	tv = float(medii.get("tv") or MEDIE_TV_S)
	radio = float(medii.get("radio") or MEDIE_RADIO_S)
	total = 0.0
	poz = poz_acum
	for s in servicii:
		if motor and s.poz != poz:
			total += secunde_mutare(poz, s.poz, model) if poz is not None else 0.0
		poz = s.poz
		total += radio if s.radio else tv
	return total


def actualizeaza_media(medii, radio, secunde):
	"""Media pe fel, cu pondere pe ultimele canale (fara mutarile motorului)."""
	cheie = "radio" if radio else "tv"
	vechi = medii.get(cheie)
	medii[cheie] = secunde if vechi is None else vechi + PONDERE_MEDIE * (secunde - vechi)
	return medii


# ---------------------------------------------------------------- textele (ecranul si pagina web)

TITLU = N_("Scanare detaliată")
DESCRIERE = N_("Receptorul pornește pe rând fiecare canal din listă și notează ce se află numai când canalul chiar "
	"rulează: rezoluția, cadrele pe secundă, codarea imaginii, accesul (liber sau criptat), PID-urile și pistele de "
	"sunet și subtitrare. Cât merge, televizorul e ocupat: imaginea se schimbă singură. Orice tastă de pe telecomandă "
	"oprește scanarea detaliată, iar receptorul revine la canalul de dinainte. Data viitoare scanarea detaliată "
	"continuă de unde a rămas.")
T_SATELITI = N_("Sateliți")
T_TOTI = N_("Toți")
T_CANALE = N_("Canale")
T_TOATE = N_("Toate")
T_NUMAI_FTA = N_("Numai cele libere (FTA)")
T_CARE = N_("Care canale")
T_NECUNOSCUTE = N_("Numai cele nescanate încă")
T_DIN_NOU = N_("Toate, din nou")
T_PLAN = N_("De scanat: %s, cam %s.")
T_PLAN_MOTOR = N_("Antena se rotește pe rând la %s.")
T_NIMIC = N_("Nimic de scanat cu aceste alegeri.")
T_RELUARE = N_("Ultima scanare detaliată s-a oprit la canalul %d din %d. Poți continua de acolo sau o poți lua de "
	"la capăt.")
T_DE_LA_CAPAT = N_("De la capăt")
T_PORNESTE = N_("Pornește")
T_CONTINUA = N_("Continuă")
T_OPRESTE = N_("Oprește")
T_MERGE = N_("Canalul %d din %d")
T_RAMAS = N_("rămas cam %s")
T_NUMARATORI = N_("scanate %d, criptate %d, fără semnal %d")
T_INDICIU = N_("Orice tastă oprește scanarea detaliată și revine la canalul de dinainte.")
T_ROTIRE = N_("Antena se rotește spre %s")
T_GATA = N_("Scanarea detaliată s-a terminat.")
T_OPRIT = N_("Scanarea detaliată s-a oprit la canalul %d din %d. Data viitoare continuă de acolo.")
T_REZULTAT = N_("Scanate: %d. Criptate (accesul și codarea): %d. Fără imagine: %d. Fără semnal: %d. Sărite: %d.")
T_MOTIV = {
	OPRIT_TASTA: N_("Ai apăsat o tastă."),
	OPRIT_CERUT: N_("Oprită la cerere."),
	OPRIT_INREGISTRARE: N_("Începe o înregistrare."),
	OPRIT_STANDBY: N_("Receptorul a intrat în standby."),
	OPRIT_ALT_CANAL: N_("Altcineva a schimbat canalul."),
	OPRIT_ORA: N_("A venit ora de oprire."),
	OPRIT_EROARE: N_("O eroare pe receptor."),
}
T_MERGE_DEJA = N_("Scanarea detaliată merge deja.")
T_INREGISTRARE_ACUM = N_("În timpul unei înregistrări nu se poate: tunerul e ocupat.")
T_INREGISTRARE_CURAND = N_("O înregistrare începe în curând. Pornește scanarea detaliată după ea.")
T_ACTUALIZARE = N_("Acum merge citirea pistelor. Pornește scanarea detaliată după ea.")
T_STANDBY = N_("Receptorul e în standby. Pornește-l întâi.")
T_FARA_LAMEDB = N_("Lista de canale nu se poate citi.")
T_PORNITA = N_("Scanarea detaliată a pornit pe televizor.")
T_NIMIC_NU_MERGE = N_("Nicio scanare detaliată nu merge acum.")
T_OPRIT_WEB = N_("Oprită. Receptorul revine la canalul de dinainte.")


def text_durata(secunde):
	"""„45 de minute”, „3 ore și 20 de minute”; sub un minut, „un minut”."""
	m = int(round(max(0.0, secunde) / 60.0))
	if m <= 1:
		return _("un minut")
	if m < 60:
		return X.ngettext("%d minut", "%d minute", m) % m
	ore, m = divmod(m, 60)
	t_ore = X.ngettext("%d oră", "%d ore", ore) % ore
	if not m:
		return t_ore
	return _("%s și %s") % (t_ore, X.ngettext("%d minut", "%d minute", m) % m)


def text_plan(servicii, secunde, motor=False):
	"""Ce se culege si cat ia, pentru ecran si web."""
	if not servicii:
		return _(T_NIMIC)
	text = _(T_PLAN) % (X.text_numar(len(servicii)), text_durata(secunde))
	if motor:
		poz = []
		for s in servicii:
			if s.poz not in poz:
				poz.append(s.poz)
		if len(poz) > 1:
			text += u" " + _(T_PLAN_MOTOR) % (X.ngettext("%d poziție", "%d poziții", len(poz)) % len(poz))
	return text


def texte_mers(stare):
	"""(randul canalului, randul detaliilor) cat merge trecerea: aceleasi pe televizor si in web."""
	if stare.get("rotire"):
		linie = _(T_ROTIRE) % stare.get("pozitie", u"")
	else:
		linie = u" · ".join(x for x in (_(T_MERGE) % (stare.get("pas", 0), stare.get("total", 0)),
			stare.get("canal", u""), stare.get("pozitie", u"")) if x)
	n = stare.get("numar") or {}
	detalii = u" · ".join(x for x in (_(T_RAMAS) % stare["ramas"] if stare.get("ramas") else u"",
		_(T_NUMARATORI) % (n.get(CULES, 0), n.get(CRIPTAT, 0), n.get(FARA_SEMNAL, 0))) if x)
	return linie, detalii


def text_rezultat(stare):
	"""Sfarsitul unei treceri: ce s-a oprit si numaratorile."""
	n = stare.get("numar") or {}
	randuri = []
	motiv = stare.get("motiv")
	if motiv == GATA:
		randuri.append(_(T_GATA))
	else:
		randuri.append(_(T_OPRIT) % (stare.get("pas") or stare.get("facute", 0), stare.get("total", 0)))
		if motiv in T_MOTIV:
			randuri.append(_(T_MOTIV[motiv]))
	randuri.append(_(T_REZULTAT) % (n.get(CULES, 0), n.get(CRIPTAT, 0), n.get(FARA_IMAGINE, 0), n.get(FARA_SEMNAL, 0),
		n.get(SARIT, 0) + n.get(REFUZAT, 0) + n.get(FARA_DATE, 0)))
	return u"\n".join(randuri)


# ---------------------------------------------------------------- starea (reluarea)

def stare_goala(optiuni, semn, poz_start):
	return {"fel": FEL_STARE, "v": 1, "optiuni": dict(optiuni), "semn": semn, "poz_start": poz_start,
		"urmatorul": None, "facute": 0, "total": 0, "numar": dict((r, 0) for r in REZULTATE), "fara_semnal_tp": [],
		"medii": {}, "lucrat_s": 0.0, "inceput": 0, "actualizat": 0, "motiv": None, "activ": False}


def citeste_stare(cale=None):
	"""Starea scrisa, sau None (lipsa, stricata, alt fel)."""
	cale = cale or CALE_STARE
	try:
		with open(cale, "rb") as f:
			date = f.read(MAX_STARE + 1)
	except (IOError, OSError):
		return None
	if len(date) > MAX_STARE:
		return None
	try:
		d = json.loads(date.decode("utf-8"))
	except (ValueError, UnicodeDecodeError, RecursionError):
		return None
	if not isinstance(d, dict) or d.get("fel") != FEL_STARE or d.get("v") != 1:
		return None
	return d


def scrie_stare(d, cale=None):
	"""Atomic: .nou, fsync, os.replace. Nu arunca; -> True daca s-a scris."""
	cale = cale or CALE_STARE
	nou = cale + ".nou"
	try:
		date = json.dumps(d, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
		if len(date) > MAX_STARE:
			d = dict(d)
			d["fara_semnal_tp"] = list(d.get("fara_semnal_tp") or [])[-MAX_TP_FARA_SEMNAL // 4:]
			date = json.dumps(d, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
		return True
	except Exception as e:
		_jurnal("starea nu s-a putut scrie: %s" % e)
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def se_poate_relua(stare, optiuni, semn):
	"""Aceleasi alegeri, acelasi lamedb si o trecere neterminata: oprita (motivul scris) sau intrerupta fara sa apuce
	sa scrie motivul (curentul, repornirea interfetei, kill -9: starea scrisa pe drum are motiv None)."""
	return bool(stare) and stare.get("optiuni") == dict(optiuni) and stare.get("semn") == semn and \
		bool(stare.get("urmatorul")) and stare.get("motiv") != GATA


def plan_complet(servicii_toate, optiuni, poz_start=None, baza=None, stare=None):
	"""{"rest": planul ramas, "i0": indexul primului canal in planul intreg, "total", "intreg"}. Planul intreg e ordinea
	tuturor serviciilor alese; o reluare porneste de la cheia `urmatorul` a starii. Filtrul necunoscutelor si
	transponderele fara semnal ale reluarii se aplica numai restului."""
	alese = alege(servicii_toate, optiuni.get("pozitie"), bool(optiuni.get("fta")))
	if optiuni.get("fta") and baza is not None:
		# lamedb tine CAID-urile numai cand scanarea le-a vazut in SDT; accesul notat in baza le completeaza (randurile
		# fara grupa ca nu se desfac)
		cu_ca = set(baza.chei_cu(("ca",)))
		alese = [s for s in alese if s.cheie not in cu_ca or not criptat_in_baza(baza, s.cheie)]
	intreg = ordoneaza(alese, poz_start)
	i0 = 0
	if stare and stare.get("urmatorul"):
		for i, s in enumerate(intreg):
			if s.cheie == stare["urmatorul"]:
				i0 = i
				break
	rest = intreg[i0:]
	if stare:
		fara = set(stare.get("fara_semnal_tp") or ())
		if fara:
			rest = [s for s in rest if s.cheie_tp() not in fara]
	if optiuni.get("necunoscute") and baza is not None:
		rest = necunoscute(baza, rest)
	return {"rest": rest, "i0": i0, "total": len(intreg), "intreg": intreg}


def plan(servicii_toate, optiuni, poz_start=None, baza=None, stare=None):
	"""(planul ramas, i0, totalul planului intreg), ca plan_complet."""
	p = plan_complet(servicii_toate, optiuni, poz_start, baza, stare)
	return p["rest"], p["i0"], p["total"]


# ---------------------------------------------------------------- pe receptor (enigma2; importuri tarzii)

TIC_MS = 400
VERIFICARI_S = 30.0             # inregistrarile, citirea pistelor
INREGISTRARE_INAINTE_S = 300    # o inregistrare care incepe in atatea secunde opreste trecerea
PAZNIC_REINNOIRE_S = 3600.0     # semnul „ocupat” al paznicului se ia din nou (HdsPaznic il uita dupa 6 ore)
TASTE_DUPA_PORNIRE_S = 1.5      # ridicarea tastei care a pornit trecerea nu o opreste
ZAP_ASTEPTARE_S = 2.0           # dupa playService, alt canal redat decat cel cerut inseamna ca omul a schimbat canalul
PROBA_DECODOR = 4               # canale TV libere fara imagine, fara niciuna vazuta: decodorul e socotit fara imagine
CHEIE_PAZNIC = "culegere-canale"

_LAMEDB = {"semn": None, "servicii": []}
_RULARE = {"trecere": None, "ultima": None}


def _cheie_ref(ref):
	return X.cheie_din_ref(ref or "") or ""


def semnatura_lamedb(cale=None):
	cale = cale or os.path.join(X.DIRECTOR, "lamedb")
	try:
		st = os.stat(cale)
	except OSError:
		return None
	return [int(st.st_mtime), int(st.st_size)]


def servicii_curente(cale=None):
	"""(servicii, semnatura) din lamedb, citit din nou numai cand s-a schimbat (marime, data)."""
	semn = semnatura_lamedb(cale)
	if semn is None:
		return [], None
	if semn != _LAMEDB["semn"]:
		text, semn = citeste_lamedb(cale)
		_LAMEDB["servicii"] = servicii_din_lamedb(text) if text else []
		_LAMEDB["semn"] = semn
	return _LAMEDB["servicii"], _LAMEDB["semn"]


def optiuni_implicite():
	return {"pozitie": None, "fta": False, "necunoscute": True}


def optiuni_din(pozitie=None, fta=False, necunoscute=True):
	"""Alegerile ca dict (aceeasi forma ca in fisierul starii, ca reluarea sa le recunoasca)."""
	try:
		pozitie = int(pozitie) if pozitie not in (None, "", "toti") else None
	except (TypeError, ValueError):
		pozitie = None
	if pozitie is not None and not 0 <= pozitie < 3600:
		pozitie = None
	return {"pozitie": pozitie, "fta": bool(fta), "necunoscute": bool(necunoscute)}


def alegeri_pozitii(servicii):
	"""[(None, „Toți (N)”), (pozitie, „19,2°E (N)”), ...] de la vest la est, pentru ecran si web."""
	rez = [(None, u"%s (%d)" % (_(T_TOTI), len(servicii)))]
	for p, n in pozitii(servicii):
		rez.append((p, u"%s (%d)" % (X.text_pozitie(p), n)))
	return rez


class Receptor(object):
	"""Ce atinge trecerea pe receptor (navigatia, semnalul, standby-ul, inregistrarile, tastele, paznicul, notele
	culegerii), intr-un singur loc; probele de pe PC dau unul fals."""

	def __init__(self, nav):
		self.nav = nav

	def ceas(self, functie):
		from enigma import eTimer
		t = eTimer()
		t.callback.append(functie)
		return t

	def ref_curent(self):
		try:
			r = self.nav.getCurrentlyPlayingServiceReference()
			return r.toString() if r is not None else ""
		except Exception:
			return ""

	def ref_obiect(self):
		try:
			return self.nav.getCurrentlyPlayingServiceReference()
		except Exception:
			return None

	def porneste_ref(self, ref, din_nou=False):
		"""ref: text sau eServiceReference. Fara intrebarea codului: canalele protejate se sar inainte. din_nou: si cand
		e chiar canalul redat (Navigation.playService ar ignora cererea, iar culegerea n-ar mai nota nimic)."""
		try:
			if isinstance(ref, str):
				from enigma import eServiceReference
				ref = eServiceReference(ref)
			try:
				self.nav.playService(ref, checkParentalControl=False, forceRestart=din_nou)
			except TypeError:
				self.nav.playService(ref)
		except Exception as e:
			_jurnal("pornirea canalului: %s" % e)

	def semnal_prins(self):
		"""True / False dupa starea tunerului canalului redat; None cand nu se stie."""
		try:
			service = self.nav.getCurrentService()
			fe = service.frontendInfo() if service is not None else None
			d = fe.getFrontendStatus() if fe is not None else None
		except Exception:
			return None
		if not d:
			return None
		stare = str(d.get("tuner_state") or "").upper()
		if stare == "LOCKED":
			return True
		if stare in ("FAILED", "LOSTLOCK"):
			return False
		prins = d.get("tuner_locked")
		return None if prins is None else bool(prins)

	def standby(self):
		try:
			from Screens import Standby
			return Standby.inStandby is not None
		except Exception:
			return False

	def inregistrare_acum(self):
		try:
			return bool(self.nav.getRecordings())
		except Exception:
			return False

	def inregistrare(self):
		"""True cand o inregistrare merge sau incepe (ori schimba canalul) in INREGISTRARE_INAINTE_S."""
		if self.inregistrare_acum():
			return True
		try:
			from Components import HdsMotorTuner
			s = HdsMotorTuner.secundePanaLaInregistrare()
			return s is not None and s <= INREGISTRARE_INAINTE_S
		except Exception:
			return False

	def actualizare_pistelor(self):
		"""„Actualizează pistele” (Screens/HdsCautareCanale.py) merge acum."""
		try:
			from Screens import HdsCautareCanale
			return HdsCautareCanale._actualizare.get("ecran") is not None
		except Exception:
			return False

	def protejat(self, ref):
		"""Canalul e sub controlul parental (atunci nu se porneste: ar cere codul)."""
		try:
			from Components.config import config
			pc = config.ParentalControl
			if not (pc.configured.value and pc.servicepinactive.value):
				return False
		except Exception:
			return False
		try:
			from Components.ParentalControl import parentalControl
			from enigma import eServiceReference
			return parentalControl.getProtectionLevel(eServiceReference(ref).toCompareString()) != -1
		except Exception:
			return True

	def paznic(self, da):
		try:
			from Components import HdsPaznic
		except ImportError:
			return
		HdsPaznic.liber(CHEIE_PAZNIC)
		if da:
			HdsPaznic.ocupat(CHEIE_PAZNIC, HdsPaznic.MOTIV_PISTE, HdsPaznic.DURATA_PISTE_S)

	def asculta_note(self, functie, da):
		try:
			from Components import HdsCulegereCanale as C
		except ImportError:
			return
		(C.asculta if da else C.nu_mai_asculta)(functie)

	def culegerea_merge(self):
		try:
			from Components import HdsCulegereCanale as C
			return C.activ()
		except Exception:
			return False

	def taste(self, functie, da):
		try:
			from enigma import eActionMap
			if da:
				eActionMap.getInstance().bindAction("", -0x7FFFFFFF, functie)
			else:
				eActionMap.getInstance().unbindAction("", functie)
		except Exception as e:
			_jurnal("tastele: %s" % e)

	def motor(self):
		try:
			from Components import HdsPisteCanale
			return HdsPisteCanale.are_motor()
		except Exception:
			return False

	def model_motor(self):
		try:
			from Components import HdsMotorViteza
			for v in HdsMotorViteza.calibrare().sloturi.values():
				if v.get("esantioane"):
					return model_motor(v["esantioane"])
		except Exception as e:
			_jurnal("viteza motorului: %s" % e)
		return model_motor()

	def pozitie(self):
		"""Pozitia antenei de acum: cea stiuta de nucleu pentru motor, altfel a canalului redat; None."""
		try:
			from Components import HdsMotorTuner
			sec = HdsMotorTuner.controlSec()
			for slot, _nume in HdsMotorTuner.tunereCuMotor():
				p = int(sec.hdsKnownRotorPosition(slot))
				if 0 <= p < 3600:
					return p
		except Exception:
			pass
		k = _cheie_ref(self.ref_curent()).split(":")
		if len(k) == 4:
			try:
				p = int(k[1], 16) >> 16
				return p if 0 < p < 3600 else None
			except ValueError:
				return None
		return None

	def baza(self):
		return B.baza()

	def salveaza_baza(self):
		"""Scrierea bazei la sfarsitul trecerii (motivul ACTUALIZARE: fara prag, numarata in bugetul zilei)."""
		try:
			b = B.baza_existenta()
			if b is not None:
				b.salveaza(B.ACTUALIZARE)
		except Exception as e:
			_jurnal("scrierea bazei: %s" % e)


def plan_receptor(optiuni, de_la_capat=False, receptor=None, cale_stare=None, cale_lamedb=None):
	"""Planul pentru ecran, web si pornire: {rest, i0, total, intreg, stare, relua, semn, poz_start, motor, model,
	secunde, text, text_reluare, servicii}."""
	servicii, semn = servicii_curente(cale_lamedb)
	stare = None if de_la_capat else citeste_stare(cale_stare)
	relua = se_poate_relua(stare, optiuni, semn)
	poz_start = stare.get("poz_start") if relua else (receptor.pozitie() if receptor is not None else None)
	baza = receptor.baza() if receptor is not None and (optiuni.get("necunoscute") or optiuni.get("fta")) else None
	p = plan_complet(servicii, optiuni, poz_start, baza, stare if relua else None)
	motor = receptor.motor() if receptor is not None else False
	model = receptor.model_motor() if receptor is not None and motor else model_motor()
	medii = (stare.get("medii") or {}) if relua else {}
	secunde = secunde_ramase(p["rest"], medii, motor, model, poz_start)
	p.update({"stare": stare, "relua": relua, "semn": semn, "poz_start": poz_start, "motor": motor, "model": model,
		"secunde": secunde, "servicii": servicii, "text": text_plan(p["rest"], secunde, motor),
		"text_reluare": (_(T_RELUARE) % (p["i0"] + 1, p["total"])) if relua else u""})
	return p


def motiv_refuz(receptor):
	"""Textul (netradus) pentru care trecerea nu poate porni acum, sau None."""
	if _RULARE["trecere"] is not None:
		return T_MERGE_DEJA
	if receptor.standby():
		return T_STANDBY
	if receptor.actualizare_pistelor():
		return T_ACTUALIZARE
	if receptor.inregistrare_acum():
		return T_INREGISTRARE_ACUM
	if receptor.inregistrare():
		return T_INREGISTRARE_CURAND
	return None


def porneste(nav, optiuni, de_la_capat=False, la_pas=None, la_sfarsit=None, receptor=None, cale_stare=None,
		cale_lamedb=None):
	"""-> (trecerea, None) sau (None, textul tradus pentru om)."""
	receptor = receptor or Receptor(nav)
	motiv = motiv_refuz(receptor)
	if motiv:
		return None, _(motiv)
	info = plan_receptor(optiuni, de_la_capat, receptor, cale_stare, cale_lamedb)
	if info["semn"] is None:
		return None, _(T_FARA_LAMEDB)
	if not info["rest"]:
		return None, _(T_NIMIC)
	t = Trecere(receptor, info, optiuni, la_pas, la_sfarsit, cale_stare)
	_RULARE["trecere"] = t
	t.porneste()
	return t, None


def opreste(motiv=OPRIT_CERUT):
	t = _RULARE["trecere"]
	if t is None:
		return False
	t.opreste(motiv)
	return True


def in_curs():
	return _RULARE["trecere"] is not None


def stare_rulare():
	"""Trecerea in curs (stare()), altfel ultima, cu textul rezultatului; None daca n-a fost niciuna de la pornire."""
	t = _RULARE["trecere"]
	if t is not None:
		return t.stare()
	return _RULARE["ultima"]


class Trecere(object):
	"""Trecerea pe receptor: porneste canalele pe rand si trece mai departe dupa judeca_note. Se opreste la o tasta, la
	o inregistrare (care merge sau incepe curand), la standby, la alt canal pus de altcineva, la „Actualizează pistele”
	sau la cerere; la sfarsit pune inapoi canalul de dinainte (numai peste canalul pus de ea) si scrie starea."""

	def __init__(self, receptor, info, optiuni, la_pas=None, la_sfarsit=None, cale_stare=None,
			ceasornic=None):
		self.r = receptor
		self.rest = list(info["rest"])
		self.total = info["total"]
		self.ordine = dict((s.cheie, i) for i, s in enumerate(info["intreg"]))
		self.motor, self.model = info["motor"], info["model"]
		self.poz = info["poz_start"]
		self.la_pas = la_pas
		self.la_sfarsit = la_sfarsit
		self.cale_stare = cale_stare
		self.ceasornic = ceasornic or _monoton
		if info["relua"]:
			st = info["stare"]
		else:
			st = stare_goala(optiuni, info["semn"], info["poz_start"])
		st["total"] = self.total
		st["motiv"] = None
		st["activ"] = True
		st["inceput"] = int(time.time())
		if not isinstance(st.get("medii"), dict):
			st["medii"] = {}
		numar = st.get("numar") if isinstance(st.get("numar"), dict) else {}
		st["numar"] = dict((r, int(numar.get(r, 0) or 0)) for r in REZULTATE)
		self.st = st
		self.fara_tp = set(st.get("fara_semnal_tp") or ())
		self.tacute = {}
		self.k = -1
		self.s = None
		self.o = None
		self.gata = False
		self.original = None
		self.pornit_la = 0.0
		self.ultima_verificare = 0.0
		self.paznic_la = 0.0
		self.ultima_scriere = 0.0
		self.facute_acum = 0
		self.imagini = 0
		self.fara_imagine_libere = 0
		self.asteapta_imagine = True
		self.ceas = receptor.ceas(self._tic)
		self.ceasOprire = receptor.ceas(self._oprireDinTasta)

	# ---- pornirea si oprirea
	def porneste(self):
		self.pornit_la = self.ceasornic()
		self.ultima_scriere = self.pornit_la
		self.ultima_verificare = self.pornit_la
		self.original = self.r.ref_obiect()
		self.r.paznic(True)
		self.paznic_la = self.pornit_la
		self.r.asculta_note(self._nota, True)
		self.r.taste(self._tasta, True)
		_jurnal("pornita: %d canale de pornit din %d, pozitia de plecare %s, motor %s, culegerea %s" % (
			len(self.rest), self.total, self.poz, self.motor, self.r.culegerea_merge()))
		self._urmatorul()
		if not self.gata:
			self.ceas.start(TIC_MS, False)

	def opreste(self, motiv=OPRIT_CERUT):
		self._termina(motiv, True)

	def _tasta(self, key, flag):
		# chemata din C++ (eActionMap) pentru orice tasta: nimic greu aici, oprirea vine din ceasul ei
		try:
			if flag == 0 and not self.gata and self.ceasornic() - self.pornit_la >= TASTE_DUPA_PORNIRE_S:
				self.ceasOprire.start(0, True)
		except Exception:
			pass
		return 0

	def _oprireDinTasta(self):
		self._termina(OPRIT_TASTA, True)

	def _termina(self, motiv, pune_inapoi):
		if self.gata:
			return
		self.gata = True
		self.ceas.stop()
		self.r.taste(self._tasta, False)
		self.r.asculta_note(self._nota, False)
		self.r.paznic(False)
		if pune_inapoi and self.original is not None and self.s is not None and \
				_cheie_ref(self.r.ref_curent()) == self.s.cheie:
			self.r.porneste_ref(self.original)
		if motiv == GATA:
			self.st["urmatorul"] = None
		self.st["motiv"] = motiv
		self.st["activ"] = False
		self.st["actualizat"] = int(time.time())
		scrie_stare(self.st, self.cale_stare)
		# o singura scriere a bazei la sfarsitul trecerii (ca la „Actualizează pistele”): fara ea, ce s-a cules dupa ultimul
		# prag s-ar pierde la o cadere de curent; pe drum scrie numai culegerea obisnuita, la pragul ei
		self.r.salveaza_baza()
		stare = self.stare()
		stare["text"] = text_rezultat(stare)
		_RULARE["ultima"] = stare
		if _RULARE["trecere"] is self:
			_RULARE["trecere"] = None
		_jurnal("sfarsit: %s, %d canale acum, %s" % (motiv, self.facute_acum, self.st["numar"]))
		if self.la_sfarsit is not None:
			try:
				self.la_sfarsit(stare)
			except Exception as e:
				_jurnal("la sfarsit: %s" % e)

	# ---- canalele
	def _urmatorul(self):
		while not self.gata:
			self.k += 1
			if self.k >= len(self.rest):
				self._termina(GATA, True)
				return
			s = self.rest[self.k]
			self.st["urmatorul"] = s.cheie
			self.st["facute"] = self.ordine.get(s.cheie, 0)
			if s.cheie_tp() in self.fara_tp or self.r.protejat(s.ref):
				self.st["numar"][SARIT] += 1
				continue
			rabdare = rabdare_motor(self.poz, s.poz, self.motor, self.model)
			self.s = s
			self.o = Observatie(self.ceasornic(), s.radio, rabdare)
			self.r.porneste_ref(s.ref, din_nou=True)
			self._anunta()
			return

	def _nota(self, k, grupe):
		o, s = self.o, self.s
		if o is None or s is None or k != s.cheie or self.gata:
			return
		if "pmt" in grupe and o.t_pmt is None:
			o.t_pmt = self.ceasornic()
		ca = grupe.get("ca")
		if isinstance(ca, (list, tuple)) and ca:
			o.criptat = ca[0] == 1
		vd = grupe.get("vd")
		if isinstance(vd, (list, tuple)) and len(vd) > 1:
			o.vd_notat = True
			if isinstance(vd[1], int) and vd[1] > 0:
				o.vd_inaltime = vd[1]

	def _tic(self):
		try:
			self._pas()
		except Exception as e:
			_jurnal("pasul: %s" % e)
			self._termina(OPRIT_EROARE, True)

	def _pas(self):
		if self.gata or self.o is None:
			return
		acum = self.ceasornic()
		o, s = self.o, self.s
		if self.r.standby():
			self._termina(OPRIT_STANDBY, False)
			return
		if acum - o.t0 >= ZAP_ASTEPTARE_S and _cheie_ref(self.r.ref_curent()) != s.cheie:
			self._termina(OPRIT_ALT_CANAL, False)
			return
		if acum - self.ultima_verificare >= VERIFICARI_S:
			self.ultima_verificare = acum
			if self.r.inregistrare():
				self._termina(OPRIT_INREGISTRARE, True)
				return
			if self.r.actualizare_pistelor():
				self._termina(OPRIT_CERUT, False)
				return
		if acum - self.paznic_la >= PAZNIC_REINNOIRE_S:
			self.paznic_la = acum
			self.r.paznic(True)
		prins = self.r.semnal_prins()
		if prins is True:
			o.fara_semnal = False
		elif prins is False and o.t_pmt is None and acum - o.t0 >= SEMNAL_MIN_S + o.rabdare:
			o.fara_semnal = True
		r = judeca_note(o, acum, self.asteapta_imagine)
		if r is not None:
			self._rezultat(r, acum)
		elif self.la_pas is not None and int(acum * 1000 / TIC_MS) % 5 == 0:
			self._anunta()

	def _rezultat(self, r, acum):
		o, s = self.o, self.s
		durata = acum - o.t0
		self.st["numar"][r] += 1
		if r == FARA_SEMNAL:
			tp = s.cheie_tp()
			# un canal tacut conteaza numai cand starea tunerului se stia (altfel tacerea nu spune nimic despre transponder)
			if o.fara_semnal is not None:
				self.tacute[tp] = self.tacute.get(tp, 0) + 1
			if o.fara_semnal or self.tacute.get(tp, 0) >= 2:
				self.fara_tp.add(tp)
				self.st["fara_semnal_tp"] = sorted(self.fara_tp)[-MAX_TP_FARA_SEMNAL:]
		if not o.rabdare and r in (CULES, CRIPTAT, FARA_IMAGINE):
			actualizeaza_media(self.st["medii"], s.radio, durata)
		if not s.radio and not o.criptat and o.t_pmt is not None:
			if r == CULES:
				self.imagini += 1
				if not self.asteapta_imagine:
					_jurnal("decodorul da iar imagine")
				self.asteapta_imagine = True
			elif r == FARA_IMAGINE and self.imagini == 0:
				self.fara_imagine_libere += 1
				if self.asteapta_imagine and self.fara_imagine_libere >= PROBA_DECODOR:
					self.asteapta_imagine = False
					_jurnal("decodorul nu da imagine pe niciun canal liber (%d); TV liber judecat la codec" %
						self.fara_imagine_libere)
		self.facute_acum += 1
		self.st["lucrat_s"] = float(self.st.get("lucrat_s") or 0) + durata
		self.poz = s.poz
		self.st["urmatorul"] = self.rest[self.k + 1].cheie if self.k + 1 < len(self.rest) else None
		if self.facute_acum % SCRIERE_CANALE == 0 or acum - self.ultima_scriere >= SCRIERE_S:
			self.ultima_scriere = acum
			self.st["actualizat"] = int(time.time())
			scrie_stare(self.st, self.cale_stare)
		self._urmatorul()

	# ---- starea pentru ecran si web
	def ramase_s(self):
		ramase = self.rest[self.k + 1:] if self.k >= 0 else self.rest
		curent = 0.0
		if self.s is not None and self.o is not None and not self.gata:
			curent = max(0.0, (MEDIE_RADIO_S if self.s.radio else MEDIE_TV_S) - (self.ceasornic() - self.o.t0))
		return secunde_ramase(ramase, self.st.get("medii"), self.motor, self.model, self.poz) + curent

	def stare(self):
		s, o = self.s, self.o
		ramas = self.ramase_s() if not self.gata else 0.0
		rotire = bool(o is not None and o.rabdare and o.t_pmt is None and not self.gata)
		return {
			"activ": not self.gata,
			"pas": int(self.st.get("facute", 0)) + 1,
			"total": self.total,
			"facute": int(self.st.get("facute", 0)) + (1 if self.gata and self.st.get("motiv") == GATA else 0),
			"canal": s.nume if s is not None else u"",
			"pozitie": X.text_pozitie(s.poz) if s is not None else u"",
			"radio": bool(s.radio) if s is not None else False,
			"rotire": rotire,
			"ramas_s": int(ramas),
			"ramas": text_durata(ramas) if not self.gata else u"",
			"numar": dict(self.st["numar"]),
			"motiv": self.st.get("motiv"),
			"acum": self.facute_acum,
		}

	def _anunta(self):
		if self.la_pas is not None:
			try:
				self.la_pas(self.stare())
			except Exception as e:
				_jurnal("progres: %s" % e)

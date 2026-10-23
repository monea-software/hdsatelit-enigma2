# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAfisajPersonaj.py: modul „Personaj” al afisajului din fata (Components/HdsAfisaj.py): doi ochi si o gura desenate
# din segmentele celor 4 cifre, care clipesc, se uita in jur, zambesc, se mira. O expresie apare la un eveniment
# (pornirea, asteptarea, canalul nou, semnalul pierdut, eroarea, inregistrarea, volumul, noaptea) si, pe langa ele, la
# intamplare, cu ritmul ales.
#
# Desenele: driverul aprinde numai cele 53 de forme din HdsAfisajLitere.OCTET_PENTRU_FORMA (nu segmente alese liber),
# deci fiecare cadru e facut numai din mastile acelea. Ochii stau pe pozitiile 1 si 2; privirea in laturi ii muta pe
# 0-1 sau pe 2-3; gura foloseste segmentele de jos (zambetul ia ochii si gura pe aceleasi doua pozitii, rasul ia toate
# patru). Fiecare cadru tine cel putin CADRU_MINIM_MS, deci in timpul unei animatii afisajul primeste cel mult 4
# scrieri pe secunda, iar intre expresii nimic in plus.
#
# Personaj (planificarea, fara enigma2): motorul afisajului il intreaba la fiecare pas ce expresie porneste acum
# (pas()) si cand sa-l trezeasca din nou (cand()); expresia ruleaza in motor ca un mesaj scurt, deci dupa ea afisajul
# revine singur la ce arata. Un mesaj scurt are intaietate: expresia evenimentului asteapta sa se termine mesajul (cel
# mult ASTEAPTA_S), iar cea la intamplare nu porneste peste un mesaj. Noaptea (orele afisajului) cu „doarme” ales:
# nicio expresie, afara de „Casca” la inceputul noptii.
#
# Aici sunt si toate textele modului (setarile, numele expresiilor, notele ecranului si ale paginii web): ecranul
# (Screens/HdsAfisaj.py) si pagina /afisaj (HdsWebControl/afisaj_web.py) le iau de aici.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import random

try:
	from Components import HdsAfisajLitere as L
	from Components import HdsAfisajDate as D
except ImportError:     # probele de pe PC incarca modulele singure
	import HdsAfisajLitere as L
	import HdsAfisajDate as D


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la afisare."""
	return text


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


CADRU_MINIM_MS = 250         # cel mult 4 scrieri pe secunda in timpul unei animatii
CADRU_MINIM_S = CADRU_MINIM_MS / 1000.0
ASTEAPTA_S = 20.0            # expresia unui eveniment asteapta atat dupa un mesaj scurt, apoi se lasa
PAUZA_MINIMA_S = 2.0         # intre sfarsitul unei expresii si urmatoarea la intamplare
VOLUM_LINISTE_S = 0.8        # volumul: expresia vine dupa atata liniste de la ultima schimbare
TOLERANTA_S = 0.005

# setarile (config.hds_afisaj.personaj*)
CHEI = ("personaj", "personaj_ritm", "personaj_noaptea")
PORNIT = ("oprit", "pornit")
PORNIT_IMPLICIT = "oprit"
RITMURI = ("30", "60", "300", "900", "0")     # cel mult atatea secunde intre doua expresii; 0 = numai la evenimente
RITM_IMPLICIT = "60"
NOAPTEA = ("doarme", "treaz")
NOAPTEA_IMPLICIT = "doarme"

# ---------------------------------------------------------------- desenele

_m = L.masca
GOL = L.GOL
OCHI = _m("abfg")            # ochi deschis: patratul de sus
OCHI_MARE = _m("abcdef")     # ochi mare (mirat): tot conturul
INCHIS = _m("g")             # ochi inchis: linia din mijloc
SOMN = _m("d")               # ochi lasat de somn: linia de jos
JOS = _m("cdeg")             # privire in jos: patratul de jos
VESEL = _m("ceg")            # ochi vesel: arcul „n”
LITERA_Z = _m("abdeg")       # „z” de somn
ZAMBET_ST = _m("abdefg")     # ochiul stang cu coltul stang si jumatatea gurii
ZAMBET_DR = _m("abcdfg")     # ochiul drept cu jumatatea gurii si coltul drept
GURA_ST = _m("adef")         # gura mare: marginea stanga
GURA_DINTI = _m("adg")       # gura mare: buzele si dintii
GURA_DR = _m("abcd")         # gura mare: marginea dreapta
ROTIRE = (_m("a"), _m("b"), _m("g"), _m("f"))  # un segment care se roteste in patratul de sus (ameteala)

F_DESCHISI = (GOL, OCHI, OCHI, GOL)
F_INCHISI = (GOL, INCHIS, INCHIS, GOL)
F_MARI = (GOL, OCHI_MARE, OCHI_MARE, GOL)
F_JOS = (GOL, JOS, JOS, GOL)
F_VESELI = (GOL, VESEL, VESEL, GOL)
F_STANGA = (OCHI, OCHI, GOL, GOL)
F_DREAPTA = (GOL, GOL, OCHI, OCHI)
F_CU_OCHIUL = (GOL, INCHIS, OCHI, GOL)
F_ZAMBET = (GOL, ZAMBET_ST, ZAMBET_DR, GOL)
F_RAS = (GURA_ST, GURA_DINTI, GURA_DINTI, GURA_DR)
F_CASCAT = (GOL, GURA_ST, GURA_DR, GOL)
F_TRIST = (VESEL, INCHIS, INCHIS, VESEL)
F_SOMN = (GOL, SOMN, SOMN, GOL)
F_SOMN_Z = (GOL, SOMN, SOMN, LITERA_Z)


class Expresie(object):
	"""O expresie: id-ul, numele, cand apare, cadrele (fiecare LATIME masti), duratele lor in ms si cadrul care o
	arata cel mai bine intr-un desen mic (`fata`)."""
	__slots__ = ("id", "nume", "cand", "cadre", "durate", "fata")

	def __init__(self, id_, nume, cand, pasi, fata=0):
		self.id = id_
		self.nume = nume
		self.cand = cand
		self.cadre = [list(c) for c, _ms in pasi]
		self.durate = [int(ms) for _c, ms in pasi]
		self.fata = fata

	def durata(self):
		"""Secundele expresiei, de la primul cadru pana la intoarcerea afisajului."""
		return sum(self.durate) / 1000.0


def _rotire(ori, ms):
	pasi = []
	for _i in range(ori):
		for s in ROTIRE:
			pasi.append(((GOL, s, s, GOL), ms))
	return pasi


EXPRESII = [
	Expresie("clipit", N_("Clipește"), N_("La întâmplare"), [
		(F_DESCHISI, 800), (F_INCHISI, 250), (F_DESCHISI, 1000), (F_INCHISI, 250), (F_DESCHISI, 500)]),
	Expresie("priveste", N_("Se uită în jur"), N_("La întâmplare"), [
		(F_DESCHISI, 600), (F_STANGA, 800), (F_DESCHISI, 350), (F_DREAPTA, 800), (F_DESCHISI, 500), (F_INCHISI, 250),
		(F_DESCHISI, 500)], fata=1),
	Expresie("zambeste", N_("Zâmbește"), N_("La întâmplare și după o înregistrare reușită"), [
		(F_DESCHISI, 500), (F_ZAMBET, 1800), (F_VESELI, 700)], fata=1),
	Expresie("rade", N_("Râde"), N_("La întâmplare"), [
		(F_VESELI, 500), (F_RAS, 350), (F_ZAMBET, 350), (F_RAS, 350), (F_ZAMBET, 350), (F_RAS, 350), (F_VESELI, 600)],
		fata=1),
	Expresie("se_mira", N_("Se miră"), N_("La schimbarea canalului"), [
		(F_DESCHISI, 300), (F_MARI, 1400), (F_INCHISI, 250), (F_MARI, 500), (F_DESCHISI, 500)], fata=1),
	Expresie("face_cu_ochiul", N_("Face cu ochiul"), N_("Când pornește o înregistrare"), [
		(F_DESCHISI, 500), (F_CU_OCHIUL, 500), (F_DESCHISI, 400), (F_ZAMBET, 900)], fata=1),
	Expresie("cauta_semnalul", N_("Caută semnalul"), N_("Când se pierde semnalul"), [
		(F_STANGA, 400), (F_DREAPTA, 400), (F_STANGA, 400), (F_DREAPTA, 400), (F_JOS, 900), (F_TRIST, 900),
		(F_JOS, 500)], fata=5),
	Expresie("ameteste", N_("Amețește"), N_("La o eroare sau la o înregistrare eșuată"),
		_rotire(2, 350) + [(F_JOS, 600), (F_TRIST, 900), (F_JOS, 400)], fata=9),
	# cadrele de aici sunt exemplul (ochii trec de la volumul mic la cel mare); la eveniment se face expresieVolum()
	Expresie("urmareste_volumul", N_("Urmărește volumul"), N_("La schimbarea volumului"), [
		((JOS, JOS, GOL, GOL), 600), (F_STANGA, 500), (F_DESCHISI, 500), (F_DREAPTA, 500),
		((GOL, GOL, OCHI_MARE, OCHI_MARE), 900), (F_DESCHISI, 600)], fata=3),
	Expresie("inchide_ochii", N_("Închide ochii"), N_("Când oprești sunetul"), [
		(F_DESCHISI, 300), (F_INCHISI, 1600), (F_DESCHISI, 400)], fata=1),
	Expresie("se_trezeste", N_("Se trezește"), N_("La pornire, la ieșirea din așteptare, dimineața"), [
		(F_SOMN, 600), (F_INCHISI, 400), (F_DESCHISI, 300), (F_INCHISI, 250), (F_DESCHISI, 500), (F_STANGA, 500),
		(F_DREAPTA, 500), (F_DESCHISI, 400), (F_VESELI, 600)], fata=8),
	Expresie("adoarme", N_("Adoarme"), N_("La intrarea în așteptare"), [
		(F_DESCHISI, 500), (F_INCHISI, 400), (F_DESCHISI, 300), (F_INCHISI, 600), (F_SOMN, 800), (F_SOMN_Z, 900)],
		fata=5),
	Expresie("casca", N_("Cască"), N_("Când începe noaptea"), [
		(F_DESCHISI, 400), (F_INCHISI, 300), (F_CASCAT, 1300), (F_INCHISI, 400), (F_SOMN, 700), (F_SOMN_Z, 800)],
		fata=2),
	Expresie("doarme", N_("Doarme"), N_("La întâmplare, în așteptare"), [
		(F_SOMN, 1000), (F_SOMN_Z, 900), (F_SOMN, 700), (F_SOMN_Z, 900)], fata=1),
]

DUPA_ID = dict((e.id, e) for e in EXPRESII)

# expresiile la intamplare si cat de des iese fiecare (pondere)
LA_INTAMPLARE = (("clipit", 5), ("priveste", 3), ("zambeste", 2), ("rade", 1))
IN_ASTEPTARE = (("doarme", 1),)

# evenimentul -> expresia lui; volumul se face din valoare (expresieVolum)
EVENIMENTE = {
	"pornire": "se_trezeste",
	"iesire_asteptare": "se_trezeste",
	"dimineata": "se_trezeste",
	"asteptare": "adoarme",
	"noapte": "casca",
	"canal": "se_mira",
	"semnal": "cauta_semnalul",
	"eroare": "ameteste",
	"rec": "face_cu_ochiul",
	"rec_gata": "zambeste",
	"rec_esuat": "ameteste",
	"volum": "urmareste_volumul",
	"mut": "inchide_ochii",
}
# cat asteapta un eveniment inainte de expresie (volumul: pana se opreste apasarea)
AMANARE = {"volum": VOLUM_LINISTE_S}


def expresie(id_):
	return DUPA_ID.get(id_)


def ochiVolum(volum):
	"""Ochii (LATIME masti) asezati dupa volum: jos in stanga la volumul mic, mari in dreapta la cel mare."""
	try:
		v = int(volum)
	except (TypeError, ValueError):
		v = 50
	if v < 20:
		return [JOS, JOS, GOL, GOL]
	if v < 40:
		return list(F_STANGA)
	if v < 60:
		return list(F_DESCHISI)
	if v < 80:
		return list(F_DREAPTA)
	return [GOL, GOL, OCHI_MARE, OCHI_MARE]


def expresieVolum(volum):
	"""„Urmărește volumul” pentru o valoare: ochii la locul volumului, o clipire acolo, apoi inca putin."""
	ochi = ochiVolum(volum)
	inchisi = [INCHIS if m != GOL else GOL for m in ochi]
	baza = DUPA_ID["urmareste_volumul"]
	return Expresie(baza.id, baza.nume, baza.cand, [(ochi, 1500), (inchisi, 250), (ochi, 500)])


def expresieLaEveniment(nume, valoare=None):
	"""Expresia unui eveniment (Expresie) sau None."""
	id_ = EVENIMENTE.get(nume)
	if id_ is None:
		return None
	if id_ == "urmareste_volumul":
		return expresieVolum(valoare)
	return DUPA_ID.get(id_)


def desen(e):
	"""Desenul (HdsAfisajDate.Desen) unei expresii: cadrele una dupa alta, o singura data."""
	return D.Desen(e.cadre, e.durate)


def ritmSecunde(ritm):
	try:
		return max(0, int(ritm))
	except (TypeError, ValueError):
		return int(RITM_IMPLICIT)


# ---------------------------------------------------------------- planificarea

class Stare(object):
	"""Ce stie motorul afisajului la un pas, pentru Personaj: un mesaj scurt e pe afisaj (ocupat), o expresie e pe
	afisaj, asteptarea (si daca afisajul e stins in ea), noaptea, o lista previzualizata si de cand se poate scrie din
	nou (ultima scriere + CADRU_MINIM_S)."""
	__slots__ = ("ocupat", "inExpresie", "inAsteptare", "stins", "noapte", "previzualizare", "scrieDe")

	def __init__(self, ocupat=False, inExpresie=False, inAsteptare=False, stins=False, noapte=False,
			previzualizare=False, scrieDe=0.0):
		self.ocupat = ocupat
		self.inExpresie = inExpresie
		self.inAsteptare = inAsteptare
		self.stins = stins
		self.noapte = noapte
		self.previzualizare = previzualizare
		self.scrieDe = scrieDe


class Personaj(object):
	"""Ce expresie porneste si cand: expresia unui eveniment (una singura asteapta, ultima venita) si urmatoarea la
	intamplare. Nu scrie nimic: motorul afisajului arata expresia intoarsa de pas()."""

	def __init__(self, aleator=None):
		self.rnd = aleator or random.Random()
		self.pornit = False
		self.ritm = ritmSecunde(RITM_IMPLICIT)
		self.doarmeNoaptea = True
		self.urmatoarea = None      # cand vine expresia la intamplare
		self.asteapta = None        # (Expresie, nu inainte de, pana cand, evenimentul)
		self.noaptea = None         # noaptea la pasul de dinainte (evenimentele „noapte” si „dimineata”)
		self.ultima = None          # id-ul ultimei expresii pornite

	def seteaza(self, pornit, ritm, noaptea, acum):
		"""Setarile (din config, la pornire si dupa fiecare salvare). Un ritm schimbat sau modul pornit acum incep
		numaratoarea de la capat."""
		ritm = ritmSecunde(ritm)
		schimbat = (bool(pornit), ritm) != (self.pornit, self.ritm)
		self.pornit = bool(pornit)
		self.ritm = ritm
		self.doarmeNoaptea = noaptea != "treaz"
		if not self.pornit:
			self.urmatoarea = None
			self.asteapta = None
			self.noaptea = None
		elif schimbat or self.urmatoarea is None:
			self._programeaza(acum)

	def _programeaza(self, acum, dupa=None):
		"""Urmatoarea expresie la intamplare: intre jumatate din ritm si ritm de acum (si cel putin PAUZA_MINIMA_S dupa
		`dupa`, sfarsitul expresiei care tocmai porneste)."""
		if not self.pornit or self.ritm <= 0:
			self.urmatoarea = None
			return
		t = acum + self.rnd.uniform(self.ritm * 0.5, float(self.ritm))
		if dupa is not None:
			t = max(t, dupa + PAUZA_MINIMA_S)
		self.urmatoarea = t

	def eveniment(self, nume, acum, valoare=None):
		"""Un eveniment cu expresie: ea asteapta sa fie aratata (in locul celei care astepta). True daca s-a pus."""
		if not self.pornit:
			return False
		e = expresieLaEveniment(nume, valoare)
		if e is None:
			return False
		de_la = acum + AMANARE.get(nume, 0.0)
		self.asteapta = (e, de_la, de_la + ASTEAPTA_S, nume)
		return True

	def _doarme(self, noapte):
		return noapte and self.doarmeNoaptea

	def _alege(self, ponderi):
		total = sum(p for _i, p in ponderi)
		x = self.rnd.uniform(0, total)
		for id_, p in ponderi:
			x -= p
			if x <= 0:
				return DUPA_ID[id_]
		return DUPA_ID[ponderi[-1][0]]

	def _porneste(self, e, acum):
		self.ultima = e.id
		self._programeaza(acum, acum + e.durata())
		return e

	def pas(self, acum, s):
		"""Expresia de pornit acum (Expresie) sau None. `s` e Stare."""
		if not self.pornit:
			return None
		if self.noaptea is None:
			self.noaptea = s.noapte
		elif s.noapte != self.noaptea:
			self.noaptea = s.noapte
			self.eveniment("noapte" if s.noapte else "dimineata", acum)
		if self.asteapta is not None:
			e, de_la, pana, nume = self.asteapta
			if acum > pana + TOLERANTA_S or s.stins or (self._doarme(s.noapte) and nume != "noapte"):
				self.asteapta = None
			elif acum + TOLERANTA_S >= de_la and not s.ocupat and acum + TOLERANTA_S >= s.scrieDe:
				self.asteapta = None
				return self._porneste(e, acum)
			else:
				return None         # expresia evenimentului trece inaintea celei la intamplare
		if self.urmatoarea is None:
			self._programeaza(acum)
			return None
		if acum + TOLERANTA_S < self.urmatoarea or s.ocupat or s.inExpresie or acum + TOLERANTA_S < s.scrieDe:
			return None
		if self._doarme(s.noapte) or s.previzualizare or s.stins:
			self._programeaza(acum)
			return None
		return self._porneste(self._alege(IN_ASTEPTARE if s.inAsteptare else LA_INTAMPLARE), acum)

	def cand(self, acum, s):
		"""Cand trebuie trezit motorul pentru urmatoarea expresie, sau None (nimic de asteptat; cat e un mesaj scurt pe
		afisaj, motorul se trezeste oricum la sfarsitul lui). Niciodata un moment trecut cat afisajul e ocupat."""
		if not self.pornit or s.ocupat:
			return None
		if self.asteapta is not None:
			return max(self.asteapta[1], s.scrieDe, acum)
		if self.urmatoarea is not None and not s.inExpresie:
			return max(self.urmatoarea, s.scrieDe, acum)
		return None


# ---------------------------------------------------------------- textele (ecranul si pagina web)

TITLU = N_("Personaj")
SETARI = (
	("personaj", N_("Personajul pe afișaj")),
	("personaj_ritm", N_("Expresii la întâmplare")),
	("personaj_noaptea", N_("Noaptea")),
)
NOTA_GRUPA = N_("Doi ochi și o gură din segmentele afișajului: clipesc, se uită în jur, zâmbesc. Apar la "
	"evenimente și, pe lângă ele, la întâmplare.")
DETALIU_PORNIT = N_("Pornit: %s")
DETALIU_OPRIT = N_("Oprit. Îl pornești din primul rând.")
NOTA_SETARE = N_("OK alege valoarea. Se aplică după salvare.")
NOTA_RITM = N_("Pe lângă expresiile de la evenimente. OK alege valoarea; se aplică după salvare.")
NOTA_NOAPTEA = N_("Noaptea e cea din Setări: „Noaptea începe” și „Noaptea se termină”. Se aplică după salvare.")
APARE = N_("Apare: %s")
NOTA_EXPRESIE = N_("OK o arată acum pe afișaj, o dată.")
TEXT_ACUM = N_("Personajul (%s)")
ARATA = N_("Afișajul arată acum: %s.")

# etichetele paginii web: __P_<CHEIE>__ in pagina
ETICHETE_WEB = {
	"TITLU": TITLU,
	"PORNIT": SETARI[0][1],
	"RITM": SETARI[1][1],
	"NOAPTEA": SETARI[2][1],
	"NOTA": NOTA_GRUPA,
	"EXPRESII": N_("Expresiile: alegi una și o vezi aici și pe afișaj"),
	"NOTA_NOAPTEA": NOTA_NOAPTEA,
}


def alegeriPornit():
	return [("oprit", _("Oprit")), ("pornit", _("Pornit"))]


def alegeriRitm():
	return [("30", _("Des, de două ori pe minut")), ("60", _("O dată pe minut")), ("300", _("La câteva minute")),
		("900", _("Rar, cam la un sfert de oră")), ("0", _("Numai la evenimente"))]


def alegeriNoaptea():
	return [("doarme", _("Doarme, fără expresii")), ("treaz", _("Rămâne treaz"))]


ALEGERI = {"personaj": alegeriPornit, "personaj_ritm": alegeriRitm, "personaj_noaptea": alegeriNoaptea}
VALORI = {"personaj": PORNIT, "personaj_ritm": RITMURI, "personaj_noaptea": NOAPTEA}
IMPLICIT = {"personaj": PORNIT_IMPLICIT, "personaj_ritm": RITM_IMPLICIT, "personaj_noaptea": NOAPTEA_IMPLICIT}


def titlu():
	return _(TITLU)


def etichetaSetare(cheie):
	return _(dict(SETARI).get(cheie, cheie))


def textSetare(cheie, valoare):
	"""Valoarea unei setari, ca text tradus ("" fara valoare)."""
	if valoare is None:
		return u""
	fn = ALEGERI.get(cheie)
	return dict(fn()).get(valoare, valoare) if fn is not None else valoare


def notaSetare(cheie):
	if cheie == "personaj_ritm":
		return _(NOTA_RITM)
	if cheie == "personaj_noaptea":
		return _(NOTA_NOAPTEA)
	return _(NOTA_SETARE)


def notaGrupa():
	return _(NOTA_GRUPA)


def detaliuGrupa(setari):
	"""Starea modului intr-un rand: „Pornit: O dată pe minut” sau „Oprit...”."""
	if (setari or {}).get("personaj") != "pornit":
		return _(DETALIU_OPRIT)
	return _(DETALIU_PORNIT) % textSetare("personaj_ritm", setari.get("personaj_ritm"))


def nume(e):
	return _(e.nume)


def cand(e):
	"""Cand apare expresia (randul ei pe ecran si in pagina web)."""
	return _(e.cand)


def textCand(e):
	"""Cand apare expresia, cu „Apare:” inainte (detaliul de sus al ecranului)."""
	return _(APARE) % _(e.cand)


def notaExpresie():
	return _(NOTA_EXPRESIE)


def textAcum(id_):
	"""Ce arata afisajul cand e o expresie pe el (ecranul si pagina web)."""
	e = DUPA_ID.get(id_)
	return _(TEXT_ACUM) % (_(e.nume) if e is not None else id_)


def textArata(e):
	return _(ARATA) % _(e.nume)


def pentruWeb():
	"""Expresiile pentru pagina web: id, nume, cand apare, desenul (cadre si durate) si cadrul desenului mic."""
	return [{"id": e.id, "nume": _(e.nume), "cand": cand(e), "fata": e.fata,
		"desen": {"cadre": [list(c) for c in e.cadre], "durate": list(e.durate), "bucla": False}} for e in EXPRESII]

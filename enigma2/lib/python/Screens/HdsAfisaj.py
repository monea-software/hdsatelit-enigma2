# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAfisaj.py: ecranul „Afișajul din față”, pe tot ecranul. Meniu > Setări > Setări Sistem & Dispozitive.
#
# Sus: desenul exact al celor 4 cifre (segmentele din tabelul literelor, Components/HdsAfisajLitere.py) pentru randul
# ales, animat ca pe afisaj (derularea cu viteza aleasa, alternarea, inelul), si numele, formatul si nota lui.
# Dedesubt, trei coloane:
#   - grupele (Components/HdsAfisajDate.GRUPE), cu „Caută” deasupra, „Personaj”, „Setări” si „Salvează și ieși”
#     dedesubt; langa fiecare grupa, cate alegeri are bifate;
#   - alegerile grupei, fiecare cu numele datei pe prima linie si formatul pe a doua, cu desenul ei mic pentru valoarea
#     de acum (sau pentru exemplu, mai sters, cand acum nu are valoare) si cu casuta bifata cand e in lista; la „Mesaje
#     scurte” casuta spune ca mesajul e pornit, la „În așteptare” se alege una singura; la „Setări”, fiecare setare cu
#     valoarea ei pe a doua linie; la „Personaj” (Components/HdsAfisajPersonaj.py) cele trei setari ale modului si
#     expresiile, fiecare cu desenul ei mic; pe expresia aleasa desenul mare o arata cadru cu cadru, iar OK o trece o
#     data pe afisajul adevarat;
#   - lista de rotire: numarul si numele fiecarei alegeri, formatul si durata pe a doua linie, desenul ei mic.
# Fiecare text sta pe linia lui, scurtat cu „…” dupa latimea masurata a fontului (tabelele de latimi din
# Components/Converter/HdsCommon.py, cu marimea desenata, deci si cu „Mărime fonturi” din setarile imaginii); textul
# intreg e sus, in randul ales. Inaltimea randurilor creste cu marimea fonturilor (skin.getListFont).
# Numai sagetile si OK: Stanga/Dreapta trec intre coloane, Sus/Jos in coloana, OK face treaba randului (bifeaza,
# deschide cautarea sau o setare, salveaza, iar pe lista de rotire deschide mutarea, durata, eticheta si scoaterea).
# CH+/CH- si tastele < > sar o pagina. Tastele colorate sunt numai scurtaturi (Rosu inchide, Verde salveaza, Galben
# muta randul listei in sus, Albastru cauta). EXIT cu schimbari intreaba daca se salveaza.
#
# Afisajul adevarat arata lista de pe ecran inca dinainte de salvare (HdsAfisaj.previzualizeaza); la iesirea fara
# salvare revine la lista salvata, numai daca ecranul a previzualizat ceva. Salvarea trece prin HdsAfisaj.seteaza,
# aceeasi functie ca pagina web /afisaj.
#
# FIRUL: valorile se citesc numai pentru randurile vizibile (cu o pagina in jur), o singura data pe moment
# (HdsAfisaj.Valori); celelalte randuri au desenul exemplului pana ajunge cursorul la ele. Un rand desenat se tine
# minte, deci dupa un OK se face din nou numai randul schimbat. Randurile vizibile se reimprospateaza la
# REIMPROSPATARE_MS, desenul mare la durata cadrului lui, valoarea randului ales cel mult o data pe secunda; ceasurile
# merg numai cat ecranul e aratat. Desenele mici au numai segmentele aprinse; cel mare le are pe toate.
# Skinul din clasa e pentru celelalte skinuri (asezat pentru 1280x720 si socotit pentru ecranul de acum);
# HDSatelit/skin.xml are blocul „HdsAfisaj” (1920x1080).

import re
import time

from enigma import eListboxPythonMultiContent, eTimer, getDesktop, gFont, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, \
	RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import HelpableActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.Sources.StaticText import StaticText
from Components import HdsAfisaj as A
from Components import HdsAfisajDate as D
from Components import HdsAfisajLitere as L
from Components import HdsAfisajPersonaj as P

A.initConfig()

AMANARE_MS = 150            # coloana alegerilor se deseneaza dupa ce cursorul sta atat pe o grupa
RECITIRE_S = 1.0            # valoarea randului ales, cel mult atat de des
PAS_STATIC_MS = 1000        # desenul mare fara animatie: o bataie pe secunda (valoarea care se schimba)
REIMPROSPATARE_MS = 10000   # randurile vizibile din coloane, cu valorile de acum
MARGINE_DREAPTA = 44        # pixeli (la 1920) lasati in dreapta randului pentru bara de derulare (si desenul mic)
MARGINE_GRUPE = 28          # la grupe (fara desene) ajunge loc pentru bara de derulare
RAND_DUBLU = 1.25           # randul pe doua linii, fata de inaltimea randului din skin (56 -> 70: 8 randuri in 560)
PAS_LINIE = 1.17            # inaltimea unei linii de text, fata de marimea literei
LATIME_FARA_TABEL = 0.55    # latimea medie a unei litere fata de marimea ei, pentru un font fara tabel de latimi
ELIPSA = u"…"
SEPARATOR = u" · "

CAUTA = "__cauta"
PERSONAJ = "__personaj"
SETARI = "__setari"
SALVEAZA = "__salveaza"
COL_GRUPE, COL_ALEGERI, COL_ROTIRE = 0, 1, 2
# felurile randurilor din mijloc care nu sunt alegeri din catalog (o setare, un ceas, o setare a personajului, o expresie)
_FARA_DATA = ("setare", "actiune", "psetare", "expresie")

# culorile din skinul HDSatelit si rezerva pentru un alt skin (0xRRGGBB, opac)
CULORI = {
	"text": ("hdsText", 0xF2F4F8),
	"text2": ("hdsText2", 0xC9D2E3),
	"eticheta": ("hdsLabel", 0xAEB9CC),
	"stins": ("hdsDisabled", 0x667085),
	"bun": ("hdsGood", 0x4FD18B),
	"chihlimbar": ("hdsAmber", 0xF5B83D),
	"alb": ("white", 0xFFFFFF),
	"casuta": ("hdsTrack", 0x2A3350),
	"chenar": ("hdsLabel", 0xAEB9CC),
}
# culorile afisajului (rosu, ca desenele din pagina web)
SEG_APRINS = 0xFF3B30
SEG_EXEMPLU = 0x9A2F29
SEG_STINS = 0x2A1414
SEG_FUNDAL = 0x0B0B0B

# fonturile etichetelor de sus din blocul skinului HDSatelit (pentru masurare; celelalte skinuri: „Regular”)
FONTURI_ETICHETE = {
	"ales": ("HdsBold", 38),
	"detaliu": ("HdsRegular", 30),
	"titlu_grupe": ("HdsBold", 28),
	"titlu_alegeri": ("HdsBold", 28),
	"titlu_rotire": ("HdsBold", 28),
}
FONTURI_CLASA = {"ales": 26, "detaliu": 20, "titlu_grupe": 20, "titlu_alegeri": 20, "titlu_rotire": 20}

# setarile din „Setări”: (cheia din config.hds_afisaj, eticheta, alegerile)
SETARILE = (
	("viteza", "Viteza derulării", A.alegeriViteza),
	("luminozitate", "Luminozitatea, ziua", A.alegeriLuminozitate),
	("luminozitate_noapte", "Luminozitatea, noaptea", A.alegeriLuminozitateNoapte),
	("noapte_de_la", "Noaptea începe", A.alegeriNoapteDeLa),
	("noapte_pana_la", "Noaptea se termină", A.alegeriNoaptePanaLa),
	("text", "Textul tău", None),
	("oras", "Ora din alt oraș", A.alegeriOras),
)
# randurile din „Setări” care fac ceva pe loc, fara salvare (ceasurile afisajului): (cheia, eticheta, alegerile)
ACTIUNI = (
	("minutar", "Minutarul", A.alegeriMinutar),
	("cronometru", "Cronometrul", A.alegeriCronometru),
)


def N_(text):
	return text


# etichetele setarilor, pentru xgettext (SETARILE le da fara _() ca sa fie traduse la afisare)
_ETICHETE_SETARI = (N_("Viteza derulării"), N_("Luminozitatea, ziua"), N_("Luminozitatea, noaptea"),
	N_("Noaptea începe"), N_("Noaptea se termină"), N_("Textul tău"), N_("Ora din alt oraș"), N_("Minutarul"),
	N_("Cronometrul"))


def _jurnal(text):
	print("[HdsAfisaj] %s" % text)


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			return v & 0xFFFFFF if (v >> 24) == 0xFF else v
	except Exception:
		pass
	return implicit


SCARA_CLASA = 1280.0 / 1920.0     # skinul din clasa e asezat pentru 1280x720: fonturile si marginile la 2/3


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


LATIME_GRUPE = 400.0        # latimea coloanei grupelor in blocul skinului HDSatelit (1920)


def scara(latime_grupe=None):
	"""Scara randurilor desenate din cod, dupa latimea coloanei grupelor fata de blocul skinului HDSatelit: 1 acolo,
	2/3 in skinul din clasa (1280x720). Fara latime (inainte de asezare): dupa ecran."""
	if latime_grupe:
		return max(0.4, min(1.5, latime_grupe / LATIME_GRUPE))
	return _factor()


def procentFonturi():
	"""„Mărime fonturi” din setarile imaginii (skin.getFontScalePercent), 100 pe celelalte imagini."""
	try:
		import skin
		fn = getattr(skin, "getFontScalePercent", None)
		return int(fn()) if callable(fn) else 100
	except Exception:
		return 100


def _font(alias, nume, marime, inaltime, f):
	"""(gFont, inaltimea randului) din aliasul skinului (<alias name="HdsAfisaj..."/>) cand ecranul foloseste blocul
	skinului (scara aproape 1): skin.getListFont mareste si litera si randul cu „Mărime fonturi”. Altfel `nume` la scara
	`f` (skinul din clasa)."""
	if f >= 0.9:
		try:
			import skin
			if alias in skin.fonts:
				v = skin.fonts[alias]
				lista = getattr(skin, "getListFont", None)
				if lista is not None:
					font, h = lista(alias, (nume, marime, inaltime))
					return font, int(h or (v[2] or inaltime) * procentFonturi() // 100)
				return skin.parseFont(alias, ((1, 1), (1, 1))), int((v[2] or inaltime) * procentFonturi() // 100)
		except Exception:
			pass
	p = procentFonturi()
	return gFont(nume, int(marime * f) * p // 100), int(inaltime * f) * p // 100


def numeSiMarime(g, nume, marime):
	"""(familia, marimea in pixeli) a unui gFont (in probe, perechea (nume, marime))."""
	if isinstance(g, tuple) and len(g) >= 2:
		return g[0], int(g[1])
	try:
		return (getattr(g, "family", None) or nume), int(getattr(g, "pointSize", None) or marime)
	except Exception:
		return nume, int(marime)


def inaltimeLinie(marime):
	return int(round(marime * PAS_LINIE))


# ---------------------------------------------------------------- latimea textelor si scurtarea cu „…”

_TABELE = {"index": None}
_LATIMI = {}


def _index():
	idx = _TABELE["index"]
	if idx is None:
		idx = {}
		try:
			from Components.Converter import HdsCommon as C
			k = 0
			for a, b in C.FIT_RANGES:
				for c in range(a, b + 1):
					idx[c] = k
					k += 1
		except Exception:
			pass
		_TABELE["index"] = idx
	return idx


def _tabel(familie, marime):
	"""(tabelul de latimi, factorul, latimea celei mai late litere) al fontului skinului `familie` cel mai apropiat de
	`marime` (Components/Converter/HdsCommon.FIT_TABLES, facute din fisierele .ttf ale skinului), sau (None, 1, 0)."""
	cheie = (familie, marime)
	if cheie in _TABELE:
		return _TABELE[cheie]
	rez = (None, 1.0, 0)
	try:
		from Components.Converter import HdsCommon as C
		best = None
		for (f, s), tab in C.FIT_TABLES.items():
			if f == familie and (best is None or abs(s - marime) < abs(best[0] - marime)):
				best = (s, tab)
		if best is not None and _index():
			rez = (best[1], float(marime) / best[0], max(ord(c) - 48 for c in best[1] if c != u"/"))
	except Exception:
		rez = (None, 1.0, 0)
	_TABELE[cheie] = rez
	return rez


def latimeText(text, familie, marime):
	"""Latimea in pixeli a textului pe un rand, cu fontul `familie` desenat la `marime` pixeli. O litera pe care
	tabelul nu o are se socoteste cat cea mai lata, deci textul iese mai scurt, niciodata taiat."""
	cheie = (text, familie, marime)
	w = _LATIMI.get(cheie)
	if w is not None:
		return w
	tab, k, maxim = _tabel(familie, marime)
	if tab is None:
		w = len(text) * marime * LATIME_FARA_TABEL
	else:
		idx = _index()
		s = 0
		for c in text:
			i = idx.get(ord(c))
			s += maxim if (i is None or tab[i] == u"/") else ord(tab[i]) - 48
		w = s * k
	if len(_LATIMI) > 20000:
		_LATIMI.clear()
	_LATIMI[cheie] = w
	return w


def scurteaza(text, familie, marime, latime):
	"""Textul scurtat cu „…” ca sa incapa pe un rand in `latime` pixeli (cu o margine pentru rotunjirile desenarii)."""
	text = u"%s" % (text or u"")
	loc = latime - max(6, latime // 40)
	if not text or latimeText(text, familie, marime) <= loc:
		return text
	loc -= latimeText(ELIPSA, familie, marime)
	lo, hi = 0, len(text)
	while lo < hi:
		mijloc = (lo + hi + 1) // 2
		if latimeText(text[:mijloc], familie, marime) <= loc:
			lo = mijloc
		else:
			hi = mijloc - 1
	taiat = text[:lo].rstrip(u" ,;:-·")
	return (taiat + ELIPSA) if taiat else ELIPSA


def imparte(text, familie, marime, latime):
	"""Textul pe cel mult doua linii, rupt la cuvinte (a doua scurtata cu „…” daca tot nu incape)."""
	cuvinte = (text or u"").split()
	loc = latime - max(6, latime // 40)
	prima = u""
	for i, c in enumerate(cuvinte):
		incearca = (prima + u" " + c) if prima else c
		if prima and latimeText(incearca, familie, marime) > loc:
			return [prima, scurteaza(u" ".join(cuvinte[i:]), familie, marime, latime)]
		prima = incearca
	return [scurteaza(prima, familie, marime, latime)]


# ---------------------------------------------------------------- desenul segmentelor

# segmentele unei pozitii in unitati de 1/100 din inaltime: (bitul, x, y, latime, inaltime); celula 56 x 100, pasul 74
_SEGMENTE = (
	(0x01, 8, 0, 40, 10),
	(0x02, 46, 8, 10, 38),
	(0x04, 46, 54, 10, 38),
	(0x08, 8, 90, 40, 10),
	(0x10, 0, 54, 10, 38),
	(0x20, 0, 8, 10, 38),
	(0x40, 8, 45, 40, 10),
	(0x80, 60, 88, 10, 12),
)
_PAS = 74
_MARGINE = 14


def latimeDesen(inaltime, pozitii=L.LATIME):
	"""Latimea in pixeli a desenului celor `pozitii` cifre la inaltimea data (cu marginea fundalului)."""
	u = inaltime / 100.0
	return int(round((2 * _MARGINE + _PAS * (pozitii - 1) + 70) * u))


def dreptunghiuriDesen(masti, x, y, inaltime, stinse=True):
	"""Dreptunghiurile (x, y, latime, inaltime, aprins) ale segmentelor; cu stinse=False numai cele aprinse."""
	u = inaltime / 100.0
	rez = []
	for i, m in enumerate(masti):
		x0 = x + (_MARGINE + i * _PAS) * u
		for bit, sx, sy, sl, si in _SEGMENTE:
			aprins = bool(m & bit)
			if not aprins and not stinse:
				continue
			rez.append((int(round(x0 + sx * u)), int(round(y + sy * u)), max(1, int(round(sl * u))),
				max(1, int(round(si * u))), aprins))
	return rez


def intrariDesen(masti, x, y, inaltime, exemplu=False, stinse=True):
	"""Intrarile MultiContent pentru desenul celor 4 cifre: fundalul, apoi segmentele."""
	lat = latimeDesen(inaltime, len(masti))
	fundal = int(round(inaltime * 1.24))
	sus = y - int(round(inaltime * 0.12))
	e = [MultiContentEntryText(pos=(x, sus), size=(lat, fundal), font=0, text="", backcolor=SEG_FUNDAL,
		backcolor_sel=SEG_FUNDAL)]
	aprins = SEG_EXEMPLU if exemplu else SEG_APRINS
	for dx, dy, dl, di, a in dreptunghiuriDesen(masti, x, y, inaltime, stinse):
		c = aprins if a else SEG_STINS
		e.append(MultiContentEntryText(pos=(dx, dy), size=(dl, di), font=0, text="", backcolor=c, backcolor_sel=c))
	return e


# ---------------------------------------------------------------- starea de pe ecran (fara enigma: probata pe PC)

class Lucru(object):
	"""Alegerile de pe ecran, inainte de salvare: lista de rotire, mesajele scurte, asteptarea si setarile."""

	def __init__(self, c=None):
		c = c or _cfg()
		self.lista = A.citesteLista(c.lista.value)
		self.evenimente = A.citesteEvenimente(c.evenimente.value)
		self.asteptare = c.asteptare.value
		self.setari = dict((k, getattr(c, k).value) for k, _e, _a in SETARILE)
		self.personaj = dict((k, getattr(c, k).value) for k in P.CHEI)

	def cheie(self):
		return (A.scrieLista(self.lista), A.scrieEvenimente(self.evenimente), self.asteptare,
			tuple(sorted(self.setari.items())), tuple(sorted(self.personaj.items())))

	def bifat(self, d, f):
		"""Alegerea e in lista (sau mesajul e pornit cu formatul acesta, sau e asteptarea aleasa)."""
		if d.grupa == D.GRUPA_EVENIMENTE:
			ales = self.evenimente.get(d.id)
			return ales is not None and ales.id == f.id
		if d.grupa == D.GRUPA_ASTEPTARE:
			return A.ALEGERE_ASTEPTARE.get(self.asteptare) == D.idAlegere(d, f)
		id_ = D.idAlegere(d, f)
		return any(i.id() == id_ for i in self.lista)

	def comuta(self, d, f):
		"""OK pe o alegere: o pune sau o scoate. Intoarce un mesaj pentru randul de jos (sau "")."""
		if d.grupa == D.GRUPA_EVENIMENTE:
			if self.bifat(d, f):
				del self.evenimente[d.id]
				return _("Mesajul e oprit.")
			self.evenimente[d.id] = f
			return _("Mesajul e pornit.")
		if d.grupa == D.GRUPA_ASTEPTARE:
			for cheie, ales in A.ALEGERE_ASTEPTARE.items():
				if ales == D.idAlegere(d, f):
					self.asteptare = cheie
			return _("Așa arată afișajul în așteptare.")
		id_ = D.idAlegere(d, f)
		if self.bifat(d, f):
			self.lista = [i for i in self.lista if i.id() != id_]
			return _("Scos din lista de rotire.")
		if len(self.lista) >= A.MAX_LISTA:
			return _("Lista de rotire poate avea cel mult %d alegeri.") % A.MAX_LISTA
		self.lista.append(A.Intrare(d, f))
		return _("Pus la sfârșitul listei de rotire.")

	def muta(self, i, pas):
		j = i + pas
		if 0 <= i < len(self.lista) and 0 <= j < len(self.lista):
			self.lista[i], self.lista[j] = self.lista[j], self.lista[i]
			return j
		return i

	def numarBifate(self, grupa):
		return len([1 for d, f in D.alegeriGrupa(grupa) if self.bifat(d, f)])

	def argumente(self):
		"""Argumentele pentru HdsAfisaj.seteaza (aceleasi ca in pagina web)."""
		rez = dict(self.setari)
		rez.update(self.personaj)
		rez["lista"] = A.scrieLista(self.lista)
		rez["evenimente"] = A.scrieEvenimente(self.evenimente)
		rez["asteptare"] = self.asteptare
		return rez


def _cfg():
	from Components.config import config
	A.initConfig()
	return config.hds_afisaj


def textActiune(cheie):
	"""Starea de acum a unui ceas al afisajului (minutarul, cronometrul), ca text."""
	return A.textMinutar() if cheie == "minutar" else A.textCronometru()


def textSetare(cheie, valoare):
	"""Valoarea unei setari, ca text (alegerea tradusa, textul tau intre ghilimele, orasul fara fusul orar)."""
	if cheie == "oras":
		if not valoare:
			return _("niciunul")
		return D.orasDinNume(dict(D.fusurile()).get(valoare, valoare))
	for k, _e, alegeri in SETARILE:
		if k != cheie:
			continue
		if alegeri is None:
			return (u"„%s”" % valoare) if valoare else _("nescris")
		return dict(alegeri()).get(valoare, valoare)
	return valoare


def textIntrare(i):
	"""Randul listei de rotire intr-un singur text (titlul meniului unei alegeri din lista): numele si formatul."""
	return D.textAlegere(i.d, i.f)


def textStare(s):
	"""Ce arata afisajul acum (dupa HdsAfisaj.stare()), sau de ce nu arata nimic."""
	if not s.get("disponibil"):
		return _("Receptorul acesta nu are afișaj în față.")
	if not s.get("pornit"):
		return _("Afișajul pornește după ce receptorul termină pornirea.")
	if not s.get("scris"):
		return _("Afișajul nu primește textul. Repornește receptorul.")
	if s.get("text"):
		if s.get("in_asteptare"):
			return _("În așteptare, afișajul arată: %s") % s["text"]
		return _("Acum afișajul arată: %s") % s["text"]
	return _("Acum afișajul este stins.")


def notaAlegere(d, exemplu):
	"""Nota de sub numele alegerii: nota datei, cand acum nu are valoare ca desenul e un exemplu (nu la mesajele scurte
	si la asteptare: acolo desenul arata mereu cum va fi) si costul citirii."""
	parti = []
	if exemplu and d.grupa not in (D.GRUPA_EVENIMENTE, D.GRUPA_ASTEPTARE):
		parti.append(_("Acum nu are ce arăta; desenul e un exemplu."))
	if d.nota:
		parti.append(_(d.nota))
	cost = D.notaCost(d)
	if cost:
		parti.append(cost)
	return u" ".join(parti)


def titluGrupa(g):
	"""Titlul coloanei din mijloc pentru randul ales in stanga."""
	if g == CAUTA:
		return _("Caută")
	if g == PERSONAJ:
		return P.titlu()
	if g == SETARI:
		return _("Setări")
	if g == SALVEAZA:
		return _("Salvează și ieși")
	return D.numeGrupa(g)


def notaGrupa(g):
	"""Nota de sus pentru un rand din coloana grupelor (sau pentru o grupa fara randuri de ales in mijloc)."""
	if g == CAUTA:
		return _("Caută o alegere (de ex. temperatura, canal)")
	if g == SALVEAZA:
		return _("OK salvează alegerile și închide ecranul.")
	if g == PERSONAJ:
		return P.notaGrupa()
	if g == D.GRUPA_EVENIMENTE:
		return _("Mesajele scurte trec în fața listei câteva secunde, când se întâmplă ceva.")
	if g == D.GRUPA_ASTEPTARE:
		return _("În așteptare: alegi una")
	return _("Săgețile mută, OK bifează. Stânga și dreapta trec între coloane. Alegerile bifate trec pe "
		"rând, fiecare cât ai ales; un text lung se derulează.")


def texteSus(fel, ob, exemplu=False, setari=None, stare=None, personaj=None):
	"""(numele, detaliul, nota) de sus pentru randul ales: ("alegere", (d, f)), ("rotire", Intrare), ("setare", cheie),
	("psetare", cheie), ("expresie", id), ("grupa", g). Textele intregi; ecranul le scurteaza cu „…” numai daca tot nu
	incap. `personaj`: setarile personajului de pe ecran."""
	if fel == "psetare":
		return P.etichetaSetare(ob), P.textSetare(ob, (personaj or {}).get(ob)), P.notaSetare(ob)
	if fel == "expresie":
		e = P.expresie(ob)
		return P.nume(e), P.textCand(e), P.notaExpresie()
	if fel == "alegere":
		d, f = ob
		if d.grupa == D.GRUPA_EVENIMENTE:
			detaliu = _("Mesaj scurt: %s") % _(f.eticheta)
		elif len(d.formate) > 1:
			detaliu = _(f.eticheta)
		else:
			detaliu = D.numeGrupa(d.grupa)
		nota = notaAlegere(d, exemplu)
		if not nota and d.grupa in (D.GRUPA_EVENIMENTE, D.GRUPA_ASTEPTARE):
			nota = notaGrupa(d.grupa)       # ce inseamna un mesaj scurt, sau ca in asteptare se alege una
		return _(d.eticheta), detaliu, nota
	if fel == "rotire":
		i = ob
		parti = []
		if len(i.d.formate) > 1:
			parti.append(_(i.f.eticheta))
		parti.append(_("Durata: %s") % A.textDurata(i.durata))
		if i.eticheta:
			parti.append(_("eticheta „%s”") % D.SCURT.get(i.d.id, u""))
		if D.areEticheta(i.d, i.f):
			nota = _("OK: mută, durata, eticheta sau scoate.")
		else:
			nota = _("OK: mută, durata sau scoate.")
		return _(i.d.eticheta), SEPARATOR.join(parti), nota
	if fel == "actiune":
		eticheta = _([e for k, e, _a in ACTIUNI if k == ob][0])
		return eticheta, textActiune(ob), _("OK pornește sau oprește, pe loc. Se vede când e în lista de rotire "
			"(grupa „Ora și data”).")
	if fel == "setare":
		eticheta = _([e for k, e, _a in SETARILE if k == ob][0])
		detaliu = textSetare(ob, (setari or {}).get(ob)) or u""
		if ob == "text":
			nota = _("OK deschide tastatura. Textul apare când „Textul tău” e în lista de rotire.")
		elif ob in ("luminozitate", "luminozitate_noapte", "noapte_de_la", "noapte_pana_la"):
			nota = _("OK alege valoarea. Luminozitatea se aplică după salvare.")
		elif ob == "oras":
			nota = _("OK alege orașul. Ora lui apare când „Ora din alt oraș” e în lista de rotire.")
		else:
			nota = _("OK alege valoarea.")
		return eticheta, detaliu, nota
	if fel == "grupa":
		g = ob
		if g in (CAUTA, SALVEAZA):
			return titluGrupa(g), notaGrupa(g), u""
		if g == SETARI:
			return _("Setări"), _("Viteza, luminozitatea, textul tău, alt oraș, minutarul și cronometrul."), \
				_("OK alege valoarea.")
		if g == PERSONAJ:
			return P.titlu(), P.detaliuGrupa(personaj), P.notaGrupa()
		detaliu = textStare(stare) if stare is not None else u""
		return _("Acum pe afișaj"), detaliu, notaGrupa(g)
	return u"", u"", u""


SCARA_REZERVA = 0.94        # skinul din clasa pe alt ecran: cat din el, ca bara de titlu sa incapa


def skinRezerva(latime, inaltime):
	"""Skinul din clasa (asezat pentru 1280x720) socotit pentru ecranul de acum, pentru skinurile fara blocul
	„HdsAfisaj”: pozitiile, marimile, literele si randurile cresc cu ecranul, la fel pe amandoua axele, cu loc pentru
	bara de titlu a ferestrei (pe care o deseneaza skinul, deasupra ferestrei)."""
	fx = fy = min(latime / 1280.0, inaltime / 720.0) * SCARA_REZERVA

	def numere(valoare, factori):
		parti = valoare.split(",")
		if len(parti) != len(factori) or not all(p.strip().isdigit() for p in parti):
			return valoare
		return ",".join("%d" % int(round(int(p) * k)) for p, k in zip(parti, factori))

	def inlocuieste(m):
		nume, valoare = m.group(1), m.group(2)
		if nume in ("position", "size"):
			valoare = numere(valoare, (fx, fy))
		elif nume == "itemHeight":
			valoare = numere(valoare, (fy,))
		elif nume == "font" and ";" in valoare:
			familie, marime = valoare.split(";", 1)
			if marime.isdigit():
				valoare = "%s;%d" % (familie, int(round(int(marime) * fy)))
		return '%s="%s"' % (nume, valoare)
	return re.sub(r'\b(position|size|itemHeight|font)="([^"]*)"', inlocuieste, HdsAfisaj.skin)


# ---------------------------------------------------------------- ecranul

class HdsAfisaj(Screen, HelpableScreen):
	skin = """
	<screen name="HdsAfisaj" position="center,center" size="1260,700" title="Afișajul din față">
		<widget name="previzualizare" position="10,10" size="360,120" itemHeight="120" selectionDisabled="1" scrollbarMode="showNever" transparent="0" zPosition="2" />
		<widget name="ales" position="386,10" size="864,36" font="Regular;26" foregroundColor="#00F2F4F8" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="detaliu" position="386,48" size="864,30" font="Regular;20" foregroundColor="#00C9D2E3" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="nota" position="386,80" size="864,50" font="Regular;18" foregroundColor="#00AEB9CC" transparent="1" zPosition="2" />
		<eLabel position="10,138" size="1240,1" backgroundColor="#00505a6a" zPosition="1" />
		<widget name="titlu_grupe" position="10,144" size="270,28" font="Regular;20" foregroundColor="#00AEB9CC" valign="center" noWrap="1" zPosition="2" />
		<widget name="grupe" position="10,174" size="270,444" itemHeight="37" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget name="titlu_alegeri" position="292,144" size="560,28" font="Regular;20" foregroundColor="#00AEB9CC" valign="center" noWrap="1" zPosition="2" />
		<widget name="alegeri" position="292,174" size="560,444" itemHeight="37" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget name="titlu_rotire" position="864,144" size="386,28" font="Regular;20" foregroundColor="#00AEB9CC" valign="center" noWrap="1" zPosition="2" />
		<widget name="rotire" position="864,174" size="386,444" itemHeight="37" scrollbarMode="showOnDemand" transparent="0" zPosition="2" />
		<widget source="key_red" render="Label" position="10,656" size="300,34" font="Regular;19" backgroundColor="#9f1313" halign="center" valign="center" zPosition="1" />
		<widget source="key_green" render="Label" position="322,656" size="300,34" font="Regular;19" backgroundColor="#1f771f" halign="center" valign="center" zPosition="1" />
		<widget source="key_yellow" render="Label" position="634,656" size="300,34" font="Regular;19" backgroundColor="#a08500" halign="center" valign="center" zPosition="1" />
		<widget source="key_blue" render="Label" position="946,656" size="304,34" font="Regular;19" backgroundColor="#18188b" halign="center" valign="center" zPosition="1" />
	</screen>
	"""

	def __init__(self, session):
		try:
			marime = getDesktop(0).size()
			if marime.width() != 1280:
				self.skin = skinRezerva(marime.width(), marime.height())
		except Exception:
			pass
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.setTitle(_("Afișajul din față"))
		self.lucru = Lucru()
		self.salvat = self.lucru.cheie()
		self.previzualizat = False         # ecranul a trimis afisajului o lista nesalvata
		self.valori = A.Valori(session)
		self.coloana = COL_GRUPE
		self.randuriGrupe = [CAUTA] + [g for g, _n in D.GRUPE] + [PERSONAJ, SETARI, SALVEAZA]
		self.grupa = D.GRUPE[0][0]         # grupa aratata in coloana din mijloc
		self.cautat = u""
		self.randuriAlegeri = []           # (d, f) sau ("setare", cheie)
		self.desenMare = None              # (Desen, exemplu, sursa) pentru desenul de sus
		self.cadru = 0
		self.citit = 0.0
		self.inchis = False
		self.dimensiuni = {}
		self.vizibile = {}
		self.desene = {}                   # id alegere -> (masti, exemplu, citit la)
		self.randuriFacute = {}            # randurile desenate, dupa tot ce le schimba
		self.exemple = {}

		for nume in ("previzualizare", "grupe", "alegeri", "rotire"):
			self[nume] = MenuList([], content=eListboxPythonMultiContent)
		for nume in ("ales", "detaliu", "nota", "titlu_grupe", "titlu_alegeri", "titlu_rotire"):
			self[nume] = Label("")
		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_("Salvează"))
		self["key_yellow"] = StaticText(_("Mută mai sus"))
		self["key_blue"] = StaticText(_("Caută"))

		# ordinea hartilor conteaza: enigma2 da o tasta hartilor in ordinea legarii; tastele colorate sunt si in
		# ChannelSelectBaseActions, deci „culori” sta inaintea „pagini”, iar „pagini” are toate actiunile contextului ei
		self["actiuni"] = HelpableActionMap(self, "OkCancelActions", {
			"ok": (self.keyOk, _("Bifează alegerea sau deschide rândul ales")),
			"cancel": (self.keyInapoi, _("Închide (întreabă dacă salvezi)")),
		}, -1)
		self["directii"] = HelpableActionMap(self, "DirectionActions", {
			"up": (self.keySus, _("Rândul de sus")),
			"down": (self.keyJos, _("Rândul de jos")),
			"left": (self.keyStanga, _("Coloana din stânga")),
			"right": (self.keyDreapta, _("Coloana din dreapta")),
			"upRepeated": self.keySus,
			"downRepeated": self.keyJos,
			"leftRepeated": self._nimic,
			"rightRepeated": self._nimic,
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -1)
		self["culori"] = HelpableActionMap(self, "ColorActions", {
			"red": (self.keyInapoi, _("Închide (întreabă dacă salvezi)")),
			"green": (self.keySalveaza, _("Salvează și închide")),
			"yellow": (self.keyGalben, _("Mută mai sus alegerea din lista de rotire")),
			"blue": (self.keyCauta, _("Caută o alegere după nume")),
		}, -1)
		self["pagini"] = HelpableActionMap(self, "ChannelSelectBaseActions", {
			"nextBouquet": (self.keyPaginaSus, _("O pagină mai sus")),
			"prevBouquet": (self.keyPaginaJos, _("O pagină mai jos")),
			"prevMarker": self.keyPaginaSus,
			"nextMarker": self.keyPaginaJos,
			"showAllServices": self.keyInapoi,
			"showSatellites": self.keySalveaza,
			"showProviders": self.keyGalben,
			"showFavourites": self.keyCauta,
		}, -1)

		self.timer = eTimer()
		self.timer.callback.append(self._bate)
		self.amanare = eTimer()
		self.amanare.callback.append(self._arataGrupa)
		self.reimprospatare = eTimer()
		self.reimprospatare.callback.append(self._reimprospateaza)
		self.onLayoutFinish.append(self._pregateste)
		self.onShown.append(self._pornesteCeasul)
		self.onHide.append(self._opresteCeasurile)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------ pregatire si oprire

	def _pregateste(self):
		try:
			self.f = scara(self["grupe"].instance.size().width())
		except Exception:
			self.f = scara()
		# textul marit (Marimea textului peste 100 %): nota de sus are loc si pentru cozile ultimului rand, din cei 8 px
		# liberi pana la linia de dedesubt (la 130 % se taiau); la 100 % nimic
		try:
			from Components import HdsMarireText as MT
			MT.locPentruCozi(self["nota"].instance, int(8 * self.f))
		except Exception as e:
			print("[HdsAfisaj] textul marit: %s" % e)
		self.fontRand, self.inaltime = _font("HdsAfisajRand", "Regular", 28, 56, self.f)
		self.fontMic, _h = _font("HdsAfisajMic", "Regular", 24, 56, self.f)
		self.fonturi = {0: numeSiMarime(self.fontRand, "Regular", int(28 * self.f)),
			1: numeSiMarime(self.fontMic, "Regular", int(24 * self.f))}
		self.inaltime2 = max(int(round(self.inaltime * RAND_DUBLU)),
			inaltimeLinie(self.fonturi[0][1]) + inaltimeLinie(self.fonturi[1][1]) + 6)
		self.c = dict((k, _culoare(k)) for k in CULORI)
		for nume in ("grupe", "alegeri", "rotire", "previzualizare"):
			try:
				s = self[nume].instance.size()
				self.dimensiuni[nume] = (s.width(), s.height())
			except Exception:
				f = self.f
				self.dimensiuni[nume] = {"grupe": (int(400 * f), int(560 * f)), "alegeri": (int(700 * f), int(560 * f)),
					"rotire": (int(572 * f), int(560 * f)), "previzualizare": (int(540 * f), int(196 * f))}[nume]
		# randurile umplu lista intreaga (fara un rand taiat jos cand literele sunt marite): inaltimea potrivita la
		# cate randuri intregi incap
		self.inaltime = self._potrivit("grupe", self.inaltime)
		self.inaltime2 = self._potrivit("alegeri", self.inaltime2)
		inaltimi = {"grupe": self.inaltime, "alegeri": self.inaltime2, "rotire": self.inaltime2}
		for nume in ("grupe", "alegeri", "rotire", "previzualizare"):
			lista = self[nume]
			lista.l.setFont(0, self.fontRand)
			lista.l.setFont(1, self.fontMic)
			if nume != "previzualizare":
				lista.l.setItemHeight(inaltimi[nume])
				self.vizibile[nume] = max(1, self.dimensiuni[nume][1] // max(1, inaltimi[nume]))
		self.etichete = {}
		for nume, (familie, marime) in FONTURI_ETICHETE.items():
			if self.f >= 0.9 and familie:
				fm = (familie, marime * procentFonturi() // 100)
			else:
				fm = ("Regular", int(FONTURI_CLASA[nume] * max(1.0, self.f / SCARA_CLASA) * procentFonturi() // 100))
			try:
				lat = self[nume].instance.size().width()
			except Exception:
				lat = {"ales": 1144, "detaliu": 1144, "titlu_grupe": 400, "titlu_alegeri": 700, "titlu_rotire": 572}[nume]
				lat = int(lat * self.f)
			self.etichete[nume] = (fm[0], fm[1], lat)
		try:
			self["previzualizare"].l.setItemHeight(self.dimensiuni["previzualizare"][1])
		except Exception:
			pass
		self["previzualizare"].selectionEnabled(False)
		self._eticheta("titlu_grupe", _("Grupe"))
		self._deseneazaGrupe()
		self["grupe"].moveToIndex(1)      # prima grupa; „Caută” sta deasupra
		self._arataGrupa()
		self._deseneazaRotirea()
		self._focus()

	def _potrivit(self, nume, h):
		"""Inaltimea randului `h` crescuta cat sa intre un numar intreg de randuri in lista `nume`."""
		inalt = self.dimensiuni.get(nume, (0, 0))[1]
		if inalt <= 0 or h <= 0:
			return h
		return max(h, inalt // max(1, inalt // h))

	def _pornesteCeasul(self):
		self._bate()
		self.reimprospatare.start(REIMPROSPATARE_MS, False)

	def _opresteCeasurile(self):
		self.timer.stop()
		self.reimprospatare.stop()

	def _laInchidere(self):
		self.inchis = True
		self.timer.stop()
		self.amanare.stop()
		self.reimprospatare.stop()
		for t, f in ((self.timer, self._bate), (self.amanare, self._arataGrupa),
				(self.reimprospatare, self._reimprospateaza)):
			try:
				t.callback.remove(f)
			except ValueError:
				pass

	def _nimic(self):
		pass

	def _eticheta(self, nume, text):
		"""O eticheta de sus pe un singur rand, cu textul intreg: cand nu incape, deruleaza (lib/gui/elabel.h)."""
		self[nume].setText(u"%s" % (text or u""))

	# ------------------------------------------------------------ randurile

	def _latime(self, nume):
		return self.dimensiuni.get(nume, (600, 560))[0]

	def _text(self, x, y, w, h, text, font, culoare, culoareAleasa=None, dreapta=False):
		steaguri = (RT_HALIGN_RIGHT if dreapta else RT_HALIGN_LEFT) | RT_VALIGN_CENTER
		return MultiContentEntryText(pos=(x, y), size=(max(10, w), h), font=font, flags=steaguri,
			text=u"%s" % (text or u""), color=culoare, color_sel=culoareAleasa or self.c["alb"])

	def _rand(self, w, h, linii, casuta=None, desen=None, exemplu=False, dreapta=u"", culoareDreapta=None,
			margine=MARGINE_DREAPTA):
		"""Un rand: casuta (None = fara, True/False = bifata sau nu), una sau doua linii de text [(text, font, culoare)],
		un text mic la dreapta (pe a doua linie cand sunt doua) si desenul mic. Primul element nu e None: randul se
		poate alege (eListboxPythonMultiContent)."""
		c = self.c
		f = self.f
		e = [linii[0][0] or u" "]
		x = int(12 * f)
		if casuta is not None:
			lat = int(min(h, self.inaltime) * 0.46)
			sus = (h - lat) // 2
			b = max(2, lat // 10)
			e.append(MultiContentEntryText(pos=(x, sus), size=(lat, lat), font=0, text="", backcolor=c["chenar"],
				backcolor_sel=c["alb"]))
			e.append(MultiContentEntryText(pos=(x + b, sus + b), size=(lat - 2 * b, lat - 2 * b), font=0, text="",
				backcolor=c["casuta"], backcolor_sel=c["casuta"]))
			if casuta:
				m = max(3, lat // 4)
				e.append(MultiContentEntryText(pos=(x + m, sus + m), size=(lat - 2 * m, lat - 2 * m), font=0, text="",
					backcolor=c["bun"], backcolor_sel=c["bun"]))
			x += lat + int(14 * f)
		capat = w - int(margine * f)     # loc pentru bara de derulare a listei
		if desen is not None:
			hd = int(min(h, self.inaltime) * 0.56)
			ld = latimeDesen(hd)
			capat -= ld
			e.extend(intrariDesen(desen, capat, (h - hd) // 2, hd, exemplu, stinse=False))
			capat -= int(12 * f)
		cd = culoareDreapta or c["eticheta"]
		if len(linii) == 1:
			sus, jos = 0, h
		else:
			sus = int(h * 0.54)
			jos = h - sus + int(2 * f)
		ldr = 0
		if dreapta:
			familie, marime = self.fonturi[1]
			ldr = min(int(latimeText(dreapta, familie, marime)) + int(8 * f), (capat - x) // 2)
			y = 0 if len(linii) == 1 else sus - int(2 * f)
			e.append(self._text(capat - ldr, y, ldr, jos if len(linii) > 1 else h, dreapta, 1, cd, dreapta=True))
		text, font, culoare = linii[0]
		lat1 = capat - x - (ldr + int(8 * f) if ldr and len(linii) == 1 else 0)
		e.append(self._text(x, 0, lat1, sus if len(linii) > 1 else h, text, font, culoare or c["text"]))
		if len(linii) > 1:
			text, font, culoare = linii[1]
			lat2 = capat - x - (ldr + int(8 * f) if ldr else 0)
			e.append(self._text(x, sus - int(2 * f), lat2, jos, text, font, culoare or c["eticheta"],
				culoareAleasa=0xDDE3EE))
		return e

	def _randMesaj(self, w, h, text, culoare):
		"""Un rand cu un mesaj (lista goala, OK salveaza): pe o linie daca incape, altfel pe doua, cu literele mici."""
		familie, marime = self.fonturi[0]
		loc = w - int((12 + MARGINE_DREAPTA) * self.f)
		if latimeText(text, familie, marime) <= loc - max(6, loc // 40) or h < inaltimeLinie(self.fonturi[1][1]) * 2:
			return self._rand(w, h, [(text, 0, culoare)])
		familie, marime = self.fonturi[1]
		bucati = imparte(text, familie, marime, loc)
		return self._rand(w, h, [(b, 1, culoare) for b in bucati])

	def _facut(self, cheie, fa):
		"""Randul desenat pentru `cheie` (tot ce il schimba), facut o singura data."""
		r = self.randuriFacute.get(cheie)
		if r is None:
			if len(self.randuriFacute) > 2000:
				self.randuriFacute.clear()
			r = fa()
			self.randuriFacute[cheie] = r
		return r

	def _desenMic(self, d, f, citeste):
		"""(mastile, exemplu) pentru randul unei alegeri: valoarea de acum pentru randurile vizibile (citita cel mult o
		data la REIMPROSPATARE_MS), altfel ultima citita sau exemplul."""
		cheie = D.idAlegere(d, f)
		st = self.desene.get(cheie)
		acum = time.time()
		if citeste and (st is None or st[2] is None or acum - st[2] >= REIMPROSPATARE_MS / 1000.0 or acum < st[2]):
			desen, exemplu = self.valori.desen(d, f, self._viteza())
			st = ((desen.cadre[0] if desen is not None else [L.GOL] * L.LATIME), exemplu, acum)
			self.desene[cheie] = st
		elif st is None:
			cheieEx = (cheie, self._viteza())
			masti = self.exemple.get(cheieEx)
			if masti is None:
				desen = D.desenExemplu(d, f, self._viteza())
				masti = desen.cadre[0] if desen is not None else [L.GOL] * L.LATIME
				self.exemple[cheieEx] = masti
			return masti, True
		return st[0], st[1]

	def _fereastra(self, nume, n):
		"""(de la, pana la) randurile vizibile ale listei `nume`, cu o pagina in jurul lor."""
		v = self.vizibile.get(nume, 10)
		i = self[nume].getSelectionIndex() or 0
		return max(0, i - v), min(n, i + v + 1)

	def _deseneazaGrupe(self):
		w, h = self._latime("grupe"), self.inaltime
		randuri = []
		for g in self.randuriGrupe:
			if g == CAUTA:
				text = _("Caută…") if not self.cautat else _("Caută: %s") % self.cautat
				randuri.append(self._facut(("g", g, text), lambda: self._rand(w, h, [(text, 0, self.c["chihlimbar"])],
					margine=MARGINE_GRUPE)))
			elif g in (SETARI, SALVEAZA):
				culoare = self.c["chihlimbar"] if g == SETARI else self.c["bun"]
				randuri.append(self._facut(("g", g), lambda: self._rand(w, h, [(titluGrupa(g), 0, culoare)],
					margine=MARGINE_GRUPE)))
			elif g == PERSONAJ:
				# in dreapta „Pornit”, cand modul e pornit pe ecran
				pornit = P.textSetare("personaj", "pornit") if self.lucru.personaj.get("personaj") == "pornit" else u""
				randuri.append(self._facut(("g", g, pornit), lambda: self._rand(w, h, [(titluGrupa(g), 0, None)],
					dreapta=pornit, culoareDreapta=self.c["bun"], margine=MARGINE_GRUPE)))
			else:
				n = self.lucru.numarBifate(g)
				randuri.append(self._facut(("g", g, n), lambda: self._rand(w, h, [(D.numeGrupa(g), 0, None)],
					dreapta=u"%d" % n if n else u"", culoareDreapta=self.c["bun"], margine=MARGINE_GRUPE)))
		lista = self["grupe"]
		idx = lista.getSelectionIndex() or 0
		lista.setList(randuri)
		lista.moveToIndex(min(idx, len(randuri) - 1))

	def _grupaDinCursor(self):
		i = self["grupe"].getSelectionIndex() or 0
		return self.randuriGrupe[max(0, min(i, len(self.randuriGrupe) - 1))]

	def _arataGrupa(self):
		"""Coloana din mijloc pentru randul ales in stanga (grupa, cautarea sau setarile)."""
		if self.inchis:
			return
		g = self._grupaDinCursor()
		if g == CAUTA:
			if self.cautat:
				self.randuriAlegeri = list(D.cauta(self.cautat))
				titlu = _("Găsite pentru „%s”: %d") % (self.cautat, len(self.randuriAlegeri))
			else:
				self.randuriAlegeri = []
				titlu = titluGrupa(g)
		elif g == SETARI:
			self.randuriAlegeri = [("setare", k) for k, _e, _a in SETARILE] + [("actiune", k) for k, _e, _a in ACTIUNI]
			titlu = titluGrupa(g)
		elif g == PERSONAJ:
			self.randuriAlegeri = [("psetare", k) for k in P.CHEI] + [("expresie", e.id) for e in P.EXPRESII]
			titlu = titluGrupa(g)
		elif g == SALVEAZA:
			self.randuriAlegeri = []
			titlu = titluGrupa(g)
		else:
			self.randuriAlegeri = D.alegeriGrupa(g)
			titlu = titluGrupa(g)
		alta = g != self.grupa
		self.grupa = g
		self._eticheta("titlu_alegeri", titlu)
		self._deseneazaAlegeri(pastreaza=not alta)
		self._actualizeazaDetaliul()

	def _randAlegere(self, w, h, d, f, bifat, masti, exemplu):
		cheie = ("a", D.idAlegere(d, f), bifat, tuple(masti), exemplu)

		def fa():
			linii = [(_(d.eticheta), 0, None)]
			if len(d.formate) > 1:
				linii.append((_(f.eticheta), 1, None))
			return self._rand(w, h, linii, casuta=bifat, desen=masti, exemplu=exemplu)
		return self._facut(cheie, fa)

	def _randSetare(self, w, h, cheie, actiune=False):
		if actiune:
			eticheta = [e for k, e, _a in ACTIUNI if k == cheie][0]
			valoare = textActiune(cheie)
		else:
			eticheta = [e for k, e, _a in SETARILE if k == cheie][0]
			valoare = textSetare(cheie, self.lucru.setari.get(cheie))
		return self._facut(("s", cheie, valoare), lambda: self._rand(w, h, [(_(eticheta), 0, None),
			(valoare, 1, self.c["text2"])]))

	def _randPersonaj(self, w, h, cheie):
		"""O setare a personajului: numele, valoarea de pe ecran pe a doua linie."""
		eticheta = P.etichetaSetare(cheie)
		valoare = P.textSetare(cheie, self.lucru.personaj.get(cheie))
		return self._facut(("p", cheie, valoare), lambda: self._rand(w, h, [(eticheta, 0, None),
			(valoare, 1, self.c["text2"])]))

	def _randExpresie(self, w, h, id_):
		"""O expresie a personajului: numele, cand apare, desenul mic al cadrului ei de cap."""
		e = P.expresie(id_)
		return self._facut(("e", id_), lambda: self._rand(w, h, [(P.nume(e), 0, None), (P.cand(e), 1, None)],
			desen=e.cadre[e.fata]))

	def _deseneazaAlegeri(self, pastreaza=True):
		w, h = self._latime("alegeri"), self.inaltime2
		lista = self["alegeri"]
		idx = (lista.getSelectionIndex() or 0) if pastreaza else 0
		if not pastreaza:
			lista.moveToIndex(0)
		de_la, pana_la = self._fereastra("alegeri", len(self.randuriAlegeri))
		randuri = []
		for i, r in enumerate(self.randuriAlegeri):
			if r[0] in ("setare", "actiune"):
				randuri.append(self._randSetare(w, h, r[1], r[0] == "actiune"))
				continue
			if r[0] == "psetare":
				randuri.append(self._randPersonaj(w, h, r[1]))
				continue
			if r[0] == "expresie":
				randuri.append(self._randExpresie(w, h, r[1]))
				continue
			d, f = r
			masti, exemplu = self._desenMic(d, f, de_la <= i < pana_la)
			randuri.append(self._randAlegere(w, h, d, f, self.lucru.bifat(d, f), masti, exemplu))
		if not randuri:
			if self.grupa == SALVEAZA:
				gol = _("OK salvează alegerile și închide ecranul.")
			elif self.grupa == CAUTA:
				gol = _("Caută: OK deschide tastatura de pe ecran")
			else:
				gol = _("Nimic de arătat aici.")
			culoare = self.c["bun"] if self.grupa == SALVEAZA else self.c["chihlimbar"]
			randuri.append(self._facut(("m", gol), lambda: self._randMesaj(w, h, gol, culoare)))
		lista.setList(randuri)
		lista.moveToIndex(min(idx, len(randuri) - 1))

	def _randRotire(self, w, h, n, i, masti, exemplu):
		parti = []
		if len(i.d.formate) > 1:
			parti.append(_(i.f.eticheta))
		if i.eticheta:
			parti.append(D.SCURT.get(i.d.id, u""))
		durata = A.textDurata(i.durata)
		cheie = ("r", n, i.text(), tuple(masti), exemplu)
		linii = [(u"%d. %s" % (n, _(i.d.eticheta)), 0, None), (SEPARATOR.join(parti) or u" ", 1, None)]
		return self._facut(cheie, lambda: self._rand(w, h, linii, desen=masti, exemplu=exemplu, dreapta=durata))

	def _deseneazaRotirea(self):
		w, h = self._latime("rotire"), self.inaltime2
		de_la, pana_la = self._fereastra("rotire", len(self.lucru.lista))
		randuri = []
		for n, i in enumerate(self.lucru.lista):
			masti, exemplu = self._desenMic(i.d, i.f, de_la <= n < pana_la)
			randuri.append(self._randRotire(w, h, n + 1, i, masti, exemplu))
		if not randuri:
			gol = _("Lista e goală: afișajul arată ora.")
			randuri.append(self._facut(("m", gol), lambda: self._randMesaj(w, h, gol, self.c["stins"])))
		lista = self["rotire"]
		idx = lista.getSelectionIndex() or 0
		lista.setList(randuri)
		lista.moveToIndex(min(idx, len(randuri) - 1))
		self._eticheta("titlu_rotire", _("Lista de rotire (%d)") % len(self.lucru.lista))

	def _reimprospateaza(self):
		"""Randurile vizibile cu valorile de acum (ceasul, temperatura), o data la REIMPROSPATARE_MS."""
		if self.inchis:
			return
		self.valori.reimprospateaza()
		self._deseneazaAlegeri()
		self._deseneazaRotirea()

	def _focus(self):
		for col, nume in ((COL_GRUPE, "grupe"), (COL_ALEGERI, "alegeri"), (COL_ROTIRE, "rotire")):
			self[nume].selectionEnabled(col == self.coloana)
		self._actualizeazaDetaliul()

	# ------------------------------------------------------------ randul ales si desenul mare

	def _viteza(self):
		try:
			return int(self.lucru.setari.get("viteza") or A.VITEZA_IMPLICITA)
		except ValueError:
			return int(A.VITEZA_IMPLICITA)

	def _randAles(self):
		"""(felul, obiectul) randului ales: ("alegere", (d, f)), ("setare", cheie), ("rotire", Intrare), ("grupa", g)."""
		if self.coloana == COL_ALEGERI:
			i = self["alegeri"].getSelectionIndex() or 0
			if 0 <= i < len(self.randuriAlegeri):
				r = self.randuriAlegeri[i]
				return (r[0], r[1]) if r[0] in _FARA_DATA else ("alegere", r)
			return None, None
		if self.coloana == COL_ROTIRE:
			i = self["rotire"].getSelectionIndex() or 0
			if 0 <= i < len(self.lucru.lista):
				return "rotire", self.lucru.lista[i]
			return None, None
		return "grupa", self._grupaDinCursor()

	def _actualizeazaDetaliul(self):
		fel, ob = self._randAles()
		viteza = self._viteza()
		self.desenMare = None
		exemplu = False
		stare = None
		if fel == "alegere":
			d, f = ob
			desen, exemplu = self.valori.desen(d, f, viteza, singur=True)
			self.desenMare = (desen, exemplu, (d, f, False))
		elif fel == "rotire":
			desen, exemplu = self.valori.desen(ob.d, ob.f, viteza, singur=True)
			if desen is not None and ob.eticheta:
				desen = A.cuEticheta(ob.d, desen)
			self.desenMare = (desen, exemplu, (ob.d, ob.f, ob.eticheta))
		elif fel == "expresie":
			# expresia cadru cu cadru, ca pe afisaj; nu are valoare de recitit
			self.desenMare = (P.desen(P.expresie(ob)), False, None)
		elif fel is None:
			# coloana din mijloc fara randuri de ales (Caută inainte de cautare, Salvează și ieși): textele grupei
			fel, ob = "grupa", self.grupa
		if fel == "grupa" and ob not in (CAUTA, SALVEAZA, SETARI, PERSONAJ):
			try:
				stare = A.stare()
			except Exception as e:
				_jurnal("starea: %r" % (e,))
				stare = {}
		ales, detaliu, nota = texteSus(fel, ob, exemplu, self.lucru.setari, stare, self.lucru.personaj)
		self._eticheta("ales", ales)
		self._eticheta("detaliu", detaliu)
		self["nota"].setText(nota)
		self.cadru = 0
		self.citit = 0.0
		self._deseneazaMare()

	def _masti(self):
		"""Mastile desenului mare acum: randul ales sau, pe grupe si setari, ce e pe afisajul adevarat."""
		if self.desenMare is None or self.desenMare[0] is None:
			try:
				return A.stare()["masti"], False
			except Exception:
				return [L.GOL] * L.LATIME, False
		desen, exemplu, _s = self.desenMare
		return desen.cadre[self.cadru % len(desen.cadre)], exemplu

	def _deseneazaMare(self):
		masti, exemplu = self._masti()
		w, h = self.dimensiuni.get("previzualizare", (520, 190))
		hd = int(h * 0.72)
		ld = latimeDesen(hd)
		x = max(0, (w - ld) // 2)
		e = [None] + intrariDesen(masti, x, (h - hd) // 2, hd, exemplu, stinse=True)
		self["previzualizare"].setList([e])

	def _bate(self):
		"""Animatia desenului mare: cadrul urmator la durata lui; valoarea se reciteste cel mult o data pe secunda."""
		if self.inchis:
			return
		ms = PAS_STATIC_MS
		if self.desenMare is not None and self.desenMare[0] is not None:
			desen = self.desenMare[0]
			if len(desen.cadre) > 1:
				ms = desen.durate[self.cadru % len(desen.cadre)] or PAS_STATIC_MS
				self.cadru = (self.cadru + 1) % len(desen.cadre)
			acum = time.time()
			if self.desenMare[2] is not None and acum - self.citit >= RECITIRE_S and self.cadru == 0:
				self.citit = acum
				d, f, eticheta = self.desenMare[2]
				self.valori.reimprospateaza()
				nou, exemplu = self.valori.desen(d, f, self._viteza(), singur=True)
				if nou is not None and eticheta:
					nou = A.cuEticheta(d, nou)
				if nou is not None and nou != desen:
					self.desenMare = (nou, exemplu, self.desenMare[2])
		self._deseneazaMare()
		self.timer.start(max(100, ms), True)

	# ------------------------------------------------------------ schimbarile

	def _schimbat(self, mesaj=u""):
		"""Dupa o schimbare: coloanele (numai randurile schimbate se fac din nou), numaratoarea din stanga si afisajul
		adevarat (previzualizarea)."""
		self._deseneazaGrupe()
		self._deseneazaAlegeri()
		self._deseneazaRotirea()
		try:
			A.previzualizeaza(A.scrieLista(self.lucru.lista), self.lucru.asteptare)
			self.previzualizat = True
		except Exception as e:
			_jurnal("previzualizarea: %r" % (e,))
		self._actualizeazaDetaliul()
		if mesaj:
			self["nota"].setText(mesaj)

	def keyOk(self):
		fel, ob = self._randAles()
		if self.coloana == COL_GRUPE:
			if ob == CAUTA:
				self.keyCauta()
				return
			if ob == SALVEAZA:
				self.keySalveaza()
				return
			self.coloana = COL_ALEGERI
			self._focus()
			return
		if fel is None and self.coloana == COL_ALEGERI:
			# randul unic din mijloc spune ce face OK: salveaza, sau deschide tastatura cautarii
			if self.grupa == SALVEAZA:
				self.keySalveaza()
			elif self.grupa == CAUTA:
				self.keyCauta()
			return
		if fel == "alegere":
			d, f = ob
			if d.id == "texte.liber" and not self.lucru.setari.get("text") and not self.lucru.bifat(d, f):
				self._cereText(lambda: self._schimbat(self.lucru.comuta(d, f)))
				return
			self._schimbat(self.lucru.comuta(d, f))
		elif fel == "setare":
			self._alegeSetarea(ob)
		elif fel == "actiune":
			self._alegeActiunea(ob)
		elif fel == "psetare":
			self._alegePersonaj(ob)
		elif fel == "expresie":
			# o data pe afisajul adevarat, acum (si cu modul oprit)
			_reusit, mesaj = A.arataExpresia(ob)
			self["nota"].setText(mesaj)
		elif fel == "rotire":
			self._meniuRotire()

	def _alegePersonaj(self, cheie):
		"""O setare a personajului: alegerile ei; se salveaza cu celelalte."""
		alegeri = P.ALEGERI[cheie]()
		acum = self.lucru.personaj.get(cheie)
		valori = [v for v, _t in alegeri]
		sel = valori.index(acum) if acum in valori else 0

		def gata(r):
			if r is None:
				return
			self.lucru.personaj[cheie] = r[1]
			self._schimbat()
		self.session.openWithCallback(gata, ChoiceBox, title=P.etichetaSetare(cheie), list=[(t, v) for v, t in alegeri],
			selection=sel)

	def _alegeActiunea(self, cheie):
		"""Minutarul sau cronometrul: pornit sau oprit pe loc (sunt ceasuri ale afisajului, nu setari)."""
		eticheta, alegeri = [(e, a) for k, e, a in ACTIUNI if k == cheie][0]
		lista = [(t, v) for v, t in alegeri()]

		def gata(r):
			if r is None:
				return
			if cheie == "minutar":
				reusit, mesaj = A.minutar(r[1])
			else:
				reusit, mesaj = A.cronometru(r[1])
			self._deseneazaAlegeri()
			self._actualizeazaDetaliul()
			self["nota"].setText(mesaj)
		self.session.openWithCallback(gata, ChoiceBox, title=_(eticheta), list=lista)

	def _cereText(self, dupa=None):
		def gata(text):
			if text is None:
				return
			self.lucru.setari["text"] = u"".join(c for c in text if c >= u" ")[:A.MAX_TEXT].strip()
			if dupa is not None and self.lucru.setari["text"]:
				dupa()
			else:
				self._schimbat()
		self.session.openWithCallback(gata, VirtualKeyBoard, title=_("Textul tău pe afișaj (derulat dacă e lung)"),
			text=self.lucru.setari.get("text") or u"")

	def _alegeSetarea(self, cheie):
		if cheie == "text":
			self._cereText()
			return
		alegeri = [a for k, _e, a in SETARILE if k == cheie][0]()
		acum = self.lucru.setari.get(cheie)
		lista = [(t, v) for v, t in alegeri]
		sel = max(0, [v for v, _t in alegeri].index(acum)) if acum in [v for v, _t in alegeri] else 0

		def gata(r):
			if r is None:
				return
			self.lucru.setari[cheie] = r[1]
			self._schimbat()
		titlu = _([e for k, e, _a in SETARILE if k == cheie][0])
		self.session.openWithCallback(gata, ChoiceBox, title=titlu, list=lista, selection=sel)

	def _meniuRotire(self):
		i = self["rotire"].getSelectionIndex() or 0
		if not 0 <= i < len(self.lucru.lista):
			return
		intrare = self.lucru.lista[i]
		lista = [(_("Mută mai sus"), "sus"), (_("Mută mai jos"), "jos")]
		if D.areEticheta(intrare.d, intrare.f):
			if intrare.eticheta:
				lista.append((_("Fără eticheta înainte"), "fara_eticheta"))
			else:
				lista.append((_("Cu eticheta „%s” înainte, 1 s") % D.SCURT[intrare.d.id], "eticheta"))
		lista.append((_("Scoate din listă"), "scoate"))
		sel = len(lista)
		for k, dur in enumerate(A.DURATE):
			if dur == intrare.durata:
				sel = len(lista) + k
		lista += [((_("Durata: %s (acum)") if dur == intrare.durata else _("Durata: %s")) % A.textDurata(dur),
			"d%d" % dur) for dur in A.DURATE]

		def gata(r):
			if r is None:
				return
			ce = r[1]
			if ce in ("sus", "jos"):
				j = self.lucru.muta(i, -1 if ce == "sus" else 1)
				self["rotire"].moveToIndex(j)
				self._schimbat()
			elif ce.startswith("d"):
				intrare.durata = int(ce[1:])
				self._schimbat()
			elif ce == "eticheta":
				intrare.eticheta = True
				self._schimbat()
			elif ce == "fara_eticheta":
				intrare.eticheta = False
				self._schimbat()
			elif ce == "scoate":
				del self.lucru.lista[i]
				self._schimbat(_("Scos din lista de rotire."))
		self.session.openWithCallback(gata, ChoiceBox, title=textIntrare(intrare), list=lista, selection=sel)

	def keyGalben(self):
		if self.coloana != COL_ROTIRE:
			return
		i = self["rotire"].getSelectionIndex() or 0
		j = self.lucru.muta(i, -1)
		if j != i:
			self["rotire"].moveToIndex(j)
			self._schimbat()

	def keyCauta(self):
		def gata(text):
			if text is None:
				return
			self.cautat = text.strip()[:40]
			self["grupe"].moveToIndex(0)
			self._deseneazaGrupe()
			self._arataGrupa()
			if self.randuriAlegeri:
				self.coloana = COL_ALEGERI
				self["alegeri"].moveToIndex(0)
			self._focus()
		self.session.openWithCallback(gata, VirtualKeyBoard, title=_("Caută o alegere (de ex. temperatura, canal)"),
			text=self.cautat)

	# ------------------------------------------------------------ navigarea

	def _listaFocus(self):
		return self[("grupe", "alegeri", "rotire")[self.coloana]]

	def _mutat(self):
		if self.coloana == COL_GRUPE:
			self.amanare.start(AMANARE_MS, True)
		elif self.coloana == COL_ALEGERI and self._faraCitire("alegeri", self.randuriAlegeri):
			self._deseneazaAlegeri()
		elif self.coloana == COL_ROTIRE and self._faraCitire("rotire", [(i.d, i.f) for i in self.lucru.lista]):
			self._deseneazaRotirea()
		self._actualizeazaDetaliul()

	def _faraCitire(self, nume, randuri):
		"""Randurile vizibile au inca desenul exemplului (necitite): se citesc cand ajunge cursorul la ele."""
		de_la, pana_la = self._fereastra(nume, len(randuri))
		for r in randuri[de_la:pana_la]:
			if r[0] in _FARA_DATA:
				continue
			st = self.desene.get(D.idAlegere(r[0], r[1]))
			if st is None or st[2] is None:
				return True
		return False

	def keySus(self):
		self._listaFocus().up()
		self._mutat()

	def keyJos(self):
		self._listaFocus().down()
		self._mutat()

	def keyPaginaSus(self):
		self._listaFocus().pageUp()
		self._mutat()

	def keyPaginaJos(self):
		self._listaFocus().pageDown()
		self._mutat()

	def keyStanga(self):
		if self.coloana > COL_GRUPE:
			self.coloana -= 1
			self._focus()

	def keyDreapta(self):
		if self.coloana == COL_GRUPE:
			self.amanare.stop()
			self._arataGrupa()
		if self.coloana < COL_ROTIRE:
			self.coloana += 1
			self._focus()

	# ------------------------------------------------------------ salvarea

	def schimbari(self):
		return self.lucru.cheie() != self.salvat

	def keySalveaza(self):
		reusit, mesaj = A.seteaza(**self.lucru.argumente())
		if not reusit:
			self["nota"].setText(mesaj)
			return
		self.salvat = self.lucru.cheie()
		self.previzualizat = False
		self.close()

	def keyInapoi(self):
		if not self.schimbari():
			self._renunta()
			return

		def gata(r):
			if r is None or r[1] == "ramai":
				return
			if r[1] == "salveaza":
				self.keySalveaza()
			else:
				self._renunta()
		self.session.openWithCallback(gata, ChoiceBox, title=_("Ai schimbat afișajul. Salvezi?"), list=[
			(_("Da, salvează"), "salveaza"), (_("Nu, lasă cum era"), "renunta"), (_("Înapoi la alegeri"), "ramai")])

	def _renunta(self):
		# numai previzualizarea acestui ecran se opreste (nu a paginii web deschise in acelasi timp)
		if self.previzualizat:
			try:
				A.previzualizeaza(None)
			except Exception as e:
				_jurnal("previzualizarea: %r" % (e,))
		self.close()

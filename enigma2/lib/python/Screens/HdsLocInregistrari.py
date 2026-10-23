# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocInregistrari.py: ecranul „Locul înregistrărilor”: unde se salveaza inregistrarile si ce discuri sunt
# conectate. Se deschide:
# - de la tasta rosie (scop „inregistrare”) si de la timeshift (scop „timeshift”), cand locul nu e un disc bun, si din
#   notificari (scop „temporizator”: o inregistrare programata care nu poate porni; scop „programare”: una tocmai pusa
#   din ghid, din lista sau din web). Aici ecranul lucreaza singur, dupa Components/HdsLocInregistrari.decizie: cauta
#   discurile; discul tinut minte sau singurul disc bun se pregateste fara intrebare (dosarul movie, setarile), cu un
#   mesaj scurt, apoi ecranul se inchide cu True, iar cine l-a deschis porneste din nou inregistrarea; cu mai multe
#   discuri intreaba o data pe care (numele, locul liber si marimea pe rand); fara niciun disc spune sa conectezi un
#   stick sau un hard disk, iar unul pus cat e deschis ecranul duce mai departe singur;
# - din meniu (scop „meniu”): locul de acum sau discul care va fi folosit la prima inregistrare, spatiul liber si
#   discurile; nu face nimic singur; ramane deschis dupa o alegere;
# - numai cu un mesaj (`mesaj` = (text, detaliu)): ce a ales receptorul in fundal (Components/HdsLocInregistrari
#   .anuntaScurt), cu randul „Închide”; se inchide singur dupa MESAJ_FUNDAL_S, fara nicio citire.
# Numai sagetile si OK. Logica si textele sunt in Components/HdsLocInregistrari.py (aceleasi in pagina web /stocare):
# citirea discurilor si pregatirea discului ales merg pe fire, ecranul le culege dintr-un eTimer. Un disc pus sau scos
# cat timp ecranul e deschis se vede pe loc (harddiskmanager.on_partition_list_change).
#
# Ecranul care lucreaza singur ia decizia numai dupa o citire terminata, pornita dupa deschidere (sau dupa un disc pus
# ori scos): citirea tinuta de dinainte poate spune altceva decat verificarea care a deschis ecranul.
#
# Mesajele scurte (refuzul, eroarea pregatirii, „Gata” din meniu) raman pe ecran peste citirile care urmeaza, pana la
# o sageata, un OK sau MESAJ_MS: fara asta, citirea noua pornita dupa ele le-ar rescrie la bataia urmatoare a ceasului.
# Dupa o alegere din meniu, cursorul ramane pe discul ales. Din meniu, la prima aratare a discurilor, cursorul sta pe
# randul locului de acum („aici se salvează acum”) sau al discului ales singur („aici se vor salva”), niciodata pe un
# rand care muta inregistrarile pe alt disc: un OK dat din reflex nu schimba nimic.
#
# Ecranul care lucreaza singur nu are rand „Închide” cat cauta discurile sau pregateste discul ales, in primele
# FARA_IESIRE_S secunde: OK-ul dat din reflex dupa tasta rosie nu renunta la inregistrare. Dupa atat (o citire care
# tine mult) randul apare, ca iesirea sa se poata alege cu sagetile si OK; EXIT renunta oricand.
#
# Skinul: blocul <screen name="HdsLocInregistrari"> din skinul HDSatelit (1920x1080). Pentru alte skinuri, skinul de
# rezerva de mai jos, facut la deschidere dupa marimea ecranului, numai cu fontul „Regular” si culori scrise direct.

from time import time

from enigma import eTimer, getDesktop

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components import HdsLocInregistrari as L

# cat de des se culege citirea discurilor sau pregatirea discului ales
PAS_MS = 250
# cat ramane pe ecran „Gata. ...” inainte ca ecranul sa se inchida singur
GATA_MS = 1500
# cat ramane pe ecran mesajul de dupa o alegere facuta singur sau la intrebare (unde se salveaza, de ce, unde se
# schimba): se citeste mai mult decat „Gata”; OK il inchide imediat
AUTOMAT_MS = 4000
# cat ramane pe ecran un mesaj scurt (refuz, eroare, „Gata” din meniu) daca nu se apasa nicio tasta
MESAJ_MS = 10000
# cat timp (secunde) ecranul care lucreaza singur nu are rand „Închide” cat cauta sau pregateste un disc
FARA_IESIRE_S = 5

# asezarea din skinul HDSatelit (1920x1080), aceeasi in skinul de rezerva: text 3 randuri de 34 px, detaliu 5 randuri
# de 26 px (textele cele mai lungi, in germana si rusa, au 5 randuri), lista 5 randuri de 48 px cu textul la 16 px de
# marginea barei, explicatia randului ales 2 randuri de 26 px
ASEZARE = {
	"pl": 1200, "ph": 764, "linie": 2,
	"mx": 40, "cl": 1120,
	"ty": 24, "th": 60, "tf": 42,
	"xy": 92, "xh": 140, "xf": 34,
	"dy": 236, "dh": 180, "df": 26,
	"ly": 428, "lh": 240, "li": 48, "lf": 32, "lo": 16,
	"ry": 676, "rh": 72,
}


def skinRezerva(latime, inaltime):
	"""Skinul folosit cand skinul ales nu are blocul HdsLocInregistrari: aceeasi asezare ca in skinul HDSatelit,
	micsorata cu un singur factor pentru latimi, inaltimi si fonturi (textele se rup pe aceleasi randuri ca la
	1920x1080), fereastra in mijloc. Factorul e dat de inaltime (1080 de randuri), cat timp fereastra de 1200 incape in
	latimea ecranului cu 20 de puncte de fiecare parte: la 1280x720 0,667, la 720x576 0,533 (fereastra de 640, fonturi de
	18 si 14 puncte; cu latimea/1920 ar fi fost 0,375 si fonturi de 10 puncte)."""
	f = min(inaltime / 1080.0, (latime - 40) / 1200.0)
	valori = dict((k, max(1, int(round(v * f)))) for k, v in ASEZARE.items())
	# lista are exact 5 randuri dupa rotunjire (altfel apare bara de derulare la 5 randuri), restul se aseaza sub ea
	valori["lh"] = valori["li"] * 5
	valori["ry"] = valori["ly"] + valori["lh"] + max(1, int(round(8 * f)))
	valori["ph"] = valori["ry"] + valori["rh"] + max(1, int(round(16 * f)))
	return """
	<screen name="HdsLocInregistrari" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Locul înregistrărilor">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="text" render="Label" position="%(mx)d,%(xy)d" size="%(cl)d,%(xh)d" font="Regular;%(xf)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="detaliu" render="Label" position="%(mx)d,%(dy)d" size="%(cl)d,%(dh)d" font="Regular;%(df)d" valign="top" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="list" position="%(mx)d,%(ly)d" size="%(cl)d,%(lh)d" itemHeight="%(li)d" font="Regular;%(lf)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" textOffset="%(lo)d,0" zPosition="2" />
		<widget source="rand" render="Label" position="%(mx)d,%(ry)d" size="%(cl)d,%(rh)d" font="Regular;%(df)d" valign="top" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % valori


class HdsLocInregistrari(Screen):
	"""cale: dosarul inregistrarilor care nu a mers (None din meniu: locul de acum); motiv: ce a spus
	HdsStocare.verificaDisc despre el; scop: unul din Components.HdsLocInregistrari.SCOPURI; mesaj: (text, detaliu)
	pentru ecranul care numai spune ce s-a ales in fundal."""

	def __init__(self, session, cale=None, motiv=None, scop=None, mesaj=None):
		marime = getDesktop(0).size()
		self.skin = skinRezerva(marime.width(), marime.height())
		Screen.__init__(self, session)
		if scop not in L.SCOPURI:
			scop = L.SCOP_INREGISTRARE if cale else L.SCOP_MENIU
		self._scop = scop
		# in afara meniului ecranul alege singur (discul tinut minte sau singurul disc bun)
		self._singur = scop != L.SCOP_MENIU
		self._cale = cale
		self._motiv = motiv
		self._doarMesaj = mesaj
		self._cand = []
		self._necit = []
		self._randuri = []
		self._lucreaza = False
		self._ales = False
		# pregatirea pornita singur a cazut: de acum alege omul (toate discurile bune in lista)
		self._automatOprit = False
		# textele ultimei citiri (pentru reafisare dupa un mesaj), mesajul tinut (text, detaliu), discul ales cu OK
		# (cursorul ramane pe el) si discul pe care se salveaza acum dupa o alegere din meniu, cat se citeste din nou
		self._ultimele = None
		self._mesaj = None
		self._punctAles = None
		self._folositAcum = None
		# omul a mutat cursorul (din meniu, cursorul nu se mai pune singur pe randul locului de acum); de cand se cauta sau
		# se pregateste un disc (randul „Închide” lipseste FARA_IESIRE_S secunde)
		self._mutat = False
		self._asteaptaDin = time()
		titlu = _("Locul înregistrărilor")
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["text"] = StaticText("")
		self["detaliu"] = StaticText("")
		self["list"] = MenuList([])
		self["rand"] = StaticText("")
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.ok,
			"cancel": self.inchide,
			"up": self._sus,
			"down": self._jos,
		}, -1)
		self["list"].onSelectionChanged.append(self._randAles)
		self._ceas = eTimer()
		self._ceas.callback.append(self._verifica)
		self._ceasGata = eTimer()
		self._ceasGata.callback.append(self._inchideDupaAlegere)
		self._ceasMesaj = eTimer()
		self._ceasMesaj.callback.append(self._mesajExpirat)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------------ citirea

	def _loc(self):
		if self._cale:
			return self._cale
		if self._scop == L.SCOP_TIMESHIFT:
			return L.locTimeshift()
		return L.locInregistrari()

	def _discuri(self):
		self._cand = L.candidati()
		self._necit = L.necitite()

	def _porneste(self):
		# textul marit (Marimea textului peste 100 %): randul listei (48 px) creste cu procentul, ca fontul (de la 120 %
		# literele randului se taiau jos); la 100 % nimic
		try:
			from Components import HdsMarireText as MT
			MT.randuriMarite(self["list"])
		except Exception as e:
			print("[HdsLocInregistrari] textul marit: %s" % e)
		self._asteaptaDin = time()
		if self._doarMesaj is not None:
			# ce s-a ales in fundal: fraza, explicatia, „Închide”; fara citiri, se inchide singur
			self._ales = True
			text, detaliu = self._doarMesaj
			self["text"].setText(text)
			self["detaliu"].setText(detaliu)
			self._randuri = [{"text": _("Închide"), "actiune": L.ACT_INCHIDE, "punct": None, "detaliu": ""}]
			self["list"].setList([r["text"] for r in self._randuri])
			self._randAles()
			self._ceasGata.start(L.MESAJ_FUNDAL_S * 1000, True)
			return
		try:
			from Components.Harddisk import harddiskmanager
			harddiskmanager.on_partition_list_change.append(self._discuriSchimbate)
		except (ImportError, AttributeError):
			pass
		self._discuri()
		self._citeste(True)

	def _citeste(self, din_nou=False):
		cale = self._loc()
		stare, se_citeste = L.cereStare(self._cand, cale, din_nou)
		if self._singur and se_citeste:
			# ecranul care alege singur asteapta citirea noua: cea tinuta poate fi de dinainte ca discul sa fie pus sau scos
			stare = None
		if stare is not None:
			# citirea noua spune singura unde se salveaza
			self._folositAcum = None
			if self._singur and not self._automatOprit and not self._lucreaza and not self._ales:
				if self._actioneaza(stare, cale):
					return
		self._arata(L.texte(stare, self._cand, self._necit, self._scop, cale, self._motiv, se_citeste,
			self._folositAcum, automat_oprit=self._automatOprit))
		if se_citeste:
			self._ceas.start(PAS_MS, True)

	def _actioneaza(self, stare, cale):
		"""Decizia de dupa o citire noua, in afara meniului. True daca ecranul a facut ceva (s-a inchis sau pregateste
		un disc); False: se arata textele (intrebarea sau „niciun disc”)."""
		dec = L.decizie(stare, L.discRetinut(), self._scop)
		if dec is None:
			return False
		if dec["fel"] == L.DEC_BUN:
			# locul a devenit bun (un disc pus chiar atunci): cine a deschis ecranul merge mai departe
			if L.inchidereBunPermisa(cale):
				self.close(True)
				return True
			return False
		if dec["fel"] != L.DEC_DISC:
			return False
		d = dec["disc"]
		pornit, mesaj = L.foloseste(d["punct"], self._cand, self._scop, de_ce=dec["de_ce"])
		if not pornit:
			# alt disc se pregateste chiar acum (din pagina web): se citeste din nou dupa el
			self["text"].setText(mesaj)
			self["detaliu"].setText("")
			self._ceas.start(PAS_MS * 4, True)
			return True
		self._incepeLucrul(d["punct"])
		return True

	def _incepeLucrul(self, punct):
		self._lucreaza = True
		self._punctAles = punct
		self._asteaptaDin = time()
		text, detaliu = L.textLucru(L.stareLucru())
		self["text"].setText(text)
		self["detaliu"].setText(detaliu)
		self._randuriLucru()
		self._ceas.start(PAS_MS, True)

	def _faraIesire(self):
		"""Ecranul care lucreaza singur, in primele FARA_IESIRE_S secunde ale unei cautari sau pregatiri."""
		return self._singur and self._doarMesaj is None and time() - self._asteaptaDin < FARA_IESIRE_S

	def _randuriLucru(self):
		"""Randurile ecranului care lucreaza singur cat se pregateste discul: niciunul la inceput (OK nu face nimic),
		apoi „Închide”. Din meniu raman randurile discurilor, iar OK asteapta pregatirea."""
		if not self._singur:
			return
		if self._faraIesire():
			randuri = []
		else:
			randuri = [{"text": _("Închide"), "actiune": L.ACT_INCHIDE, "punct": None, "detaliu": ""}]
		if [r["actiune"] for r in randuri] != [r["actiune"] for r in self._randuri]:
			self._randuri = randuri
			self["list"].setList([r["text"] for r in randuri])
			self._randAles()

	def _discuriSchimbate(self, *argumente):
		if self._lucreaza or self._ales:
			return
		if self._scop == L.SCOP_MENIU:
			# din meniu locul nu se stie pana la citirea noua (discul lui poate fi cel scos)
			self._motiv = None
		# alt disc pus: se poate alege din nou singur
		self._automatOprit = False
		self._folositAcum = None
		self._asteaptaDin = time()
		self._discuri()
		self._citeste(True)

	def _verifica(self):
		if self._lucreaza:
			self._urmaresteLucrul()
		else:
			self._citeste()

	# ------------------------------------------------------------------ afisarea

	def _arata(self, t=None):
		if t is not None:
			self._ultimele = t
		t = self._ultimele
		if t is None:
			return
		text, detaliu = self._mesaj if self._mesaj is not None else (t["text"], t["detaliu"])
		self["text"].setText(text)
		self["detaliu"].setText(detaliu)
		index = self["list"].getSelectionIndex() if self._randuri else 0
		ales = self._randuri[index]["punct"] if 0 <= index < len(self._randuri) else None
		if self._punctAles is not None:
			ales = self._punctAles
		continua = any(r["actiune"] == L.ACT_CONTINUA for r in self._randuri)
		self._randuri = t["randuri"]
		if t.get("cauta") and self._faraIesire():
			# cat se cauta: fara „Închide” (OK-ul dat din reflex dupa tasta rosie nu renunta la inregistrare)
			self._randuri = [r for r in self._randuri if r["actiune"] != L.ACT_INCHIDE]
		self["list"].setList([r["text"] for r in self._randuri])
		if not continua and self._randuri and self._randuri[0]["actiune"] == L.ACT_CONTINUA:
			# locul tocmai a devenit bun: „Continuă” e ales, un OK duce mai departe
			self["list"].moveToIndex(0)
		elif ales is None and not self._mutat and self._scop == L.SCOP_MENIU:
			# din meniu, prima aratare a discurilor: cursorul pe locul de acum sau pe discul ales singur, nu pe un rand care
			# muta inregistrarile pe alt disc
			for i, r in enumerate(self._randuri):
				if r["actiune"] == L.ACT_ACTUAL or (t.get("automat") and r["punct"] == t["automat"]):
					self["list"].moveToIndex(i)
					break
		else:
			# ramane ales acelasi disc dupa o citire noua (dupa o alegere: discul ales, pe randul lui „aici se salveaza”)
			for i, r in enumerate(self._randuri):
				if ales is not None and r["punct"] == ales:
					self["list"].moveToIndex(i)
					if r["actiune"] == L.ACT_ACTUAL:
						self._punctAles = None
					break
		self._randAles()

	def _randAles(self):
		index = self["list"].getSelectionIndex()
		if 0 <= index < len(self._randuri):
			self["rand"].setText(self._randuri[index]["detaliu"])
		else:
			self["rand"].setText("")

	def _mesajNou(self, text, detaliu=""):
		"""Un mesaj tinut peste textele citirilor pana la o tasta sau MESAJ_MS."""
		self._mesaj = (text, detaliu)
		self._ceasMesaj.start(MESAJ_MS, True)
		self["text"].setText(text)
		self["detaliu"].setText(detaliu)

	def _stergeMesaj(self):
		if self._mesaj is not None:
			self._mesaj = None
			self._ceasMesaj.stop()
			self._arata()

	def _mesajExpirat(self):
		self._mesaj = None
		self._arata()

	def _sus(self):
		# omul muta singur cursorul: nu mai e nevoie sa ramana pe discul ales inainte
		self._punctAles = None
		self._mutat = True
		self._stergeMesaj()
		self["list"].up()

	def _jos(self):
		self._punctAles = None
		self._mutat = True
		self._stergeMesaj()
		self["list"].down()

	# ------------------------------------------------------------------ alegerea

	def ok(self):
		if self._ales:
			self._inchideDupaAlegere()
			return
		index = self["list"].getSelectionIndex()
		r = self._randuri[index] if 0 <= index < len(self._randuri) else None
		if self._lucreaza:
			# cat se pregateste discul, numai „Închide” (dupa FARA_IESIRE_S): pregatirea merge mai departe, dar ecranul
			# renunta (tasta rosie nu mai porneste inregistrarea)
			if r is not None and r["actiune"] == L.ACT_INCHIDE:
				self.inchide()
			return
		self._stergeMesaj()
		if r is None:
			return
		if r["actiune"] == L.ACT_INCHIDE:
			self.inchide()
		elif r["actiune"] == L.ACT_CONTINUA:
			self.close(True)
		elif r["actiune"] == L.ACT_FORMATEAZA:
			self._formateaza(r.get("disc"))
		elif r["actiune"] == L.ACT_ACTUAL:
			if self._scop == L.SCOP_MENIU:
				self._mesajNou(_("Înregistrările se salvează deja aici."))
			else:
				# locul e bun: ca „Continuă”
				self.close(True)
		elif r["actiune"] == L.ACT_FOLOSESTE:
			# in afara meniului, o alegere la intrebare se tine minte si se spune ca atare; din meniu, „Gata”
			de_ce = None if self._scop == L.SCOP_MENIU else L.DE_CE_ALES
			pornit, mesaj = L.foloseste(r["punct"], self._cand, self._scop, de_ce=de_ce)
			if not pornit:
				# lista din nou (discul poate sa fi fost scos), apoi refuzul, tinut peste ea
				self._punctAles = None
				self._discuri()
				self._citeste(True)
				self._mesajNou(mesaj)
				return
			self._incepeLucrul(r["punct"])

	def _formateaza(self, disc):
		"""Randul 'Formatează' al unui stick necitit: ecranul de formatare existent (Screens/HarddiskSetup.py) pentru
		discul lui, cu alegerea sistemului de fisiere si intrebarea care spune ce se sterge; fara discul in lista de
		formatare, lista tuturor discurilor. La intoarcere discurile se citesc din nou (un stick formatat se monteaza
		singur, iar ecranul care lucreaza singur merge mai departe cu el)."""
		from Screens.HarddiskSetup import HarddiskSetup, HarddiskSelection
		hdd = None
		if disc:
			try:
				from Components import HdsDiscuri
				hdd = HdsDiscuri.discul(disc)
			except Exception as e:
				print("[HdsLocInregistrari] discul %s pentru formatare: %s" % (disc, e))
		if hdd is not None:
			self.session.openWithCallback(self._dupaFormatare, HarddiskSetup, hdd, HarddiskSetup.HARDDISK_INITIALIZE)
		else:
			self.session.openWithCallback(self._dupaFormatare, HarddiskSelection)

	def _dupaFormatare(self, *rezultat):
		if self._lucreaza or self._ales:
			return
		self._automatOprit = False
		self._folositAcum = None
		self._asteaptaDin = time()
		self._discuri()
		self._citeste(True)

	def _urmaresteLucrul(self):
		# culegerea o face si ceasul modulului; aici se culege imediat, ca raspunsul sa nu astepte un pas in plus
		lucru = L.culege()
		if lucru is None:
			self._lucreaza = False
			self._citeste(True)
			return
		text, detaliu = L.textLucru(lucru)
		if lucru["stare"] == L.LUCRU_IN_LUCRU or (lucru["stare"] == L.LUCRU_GATA and not lucru["aplicat"]):
			self["text"].setText(text)
			self._randuriLucru()
			self._ceas.start(PAS_MS, True)
			return
		self._lucreaza = False
		if lucru["stare"] == L.LUCRU_GATA:
			if self._scop == L.SCOP_MENIU:
				# locul e bun acum, pe discul ales: cat se citeste din nou, lista il arata „aici se salveaza”, iar
				# confirmarea ramane pe ecran
				self._motiv = ""
				self._folositAcum = lucru.get("punct")
				self._discuri()
				self._citeste(True)
				self._mesajNou(text, detaliu)
				return
			self._ales = True
			self["text"].setText(text)
			self["detaliu"].setText(detaliu)
			self._randuri = [{"text": _("Continuă"), "actiune": L.ACT_INCHIDE, "punct": None, "detaliu": ""}]
			self["list"].setList([r["text"] for r in self._randuri])
			self._randAles()
			# dupa o alegere facuta singur sau la intrebare, textul spune si unde se schimba locul: mai mult timp
			self._ceasGata.start(AUTOMAT_MS if lucru.get("de_ce") else GATA_MS, True)
			return
		# nu a mers: lista din nou (discul poate sa fi fost scos), cu mesajul tinut peste ea; de acum alege omul
		self._automatOprit = True
		self._discuri()
		self._citeste(True)
		self._punctAles = None
		self._mesajNou(text, detaliu)

	def _inchideDupaAlegere(self):
		self._ceasGata.stop()
		self.close(True)

	def inchide(self):
		self.close(self._ales)

	def _laInchidere(self):
		self._ceas.stop()
		self._ceasGata.stop()
		self._ceasMesaj.stop()
		try:
			from Components.Harddisk import harddiskmanager
			if self._discuriSchimbate in harddiskmanager.on_partition_list_change:
				harddiskmanager.on_partition_list_change.remove(self._discuriSchimbate)
		except (ImportError, AttributeError, ValueError):
			pass

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocuriRetea.py: ecranele "Locuri din retea" de pe televizor (Media > Locuri din retea, si din meniul playerului):
#   - HdsLocuriRetea: locurile omului (calculatorul cu Windows, NAS-ul, serverul FTP, WebDAV sau media din casa), cu
#     starea fiecaruia; OK deschide locul, VERDE adauga, GALBEN monteaza sau demonteaza, ALBASTRU cauta serverele din
#     casa, MENU: editeaza, foloseste pentru inregistrari (proba de scriere si viteza), sterge;
#   - HdsLocReteaEditare: datele locului (felul, numele, serverul, dosarul, utilizatorul, parola, montat si dupa
#     repornire, numai citire, certificat facut acasa); GALBEN alege dosarul din lista serverului (exporturile NFS,
#     partajarile SMB); parola nu se arata niciodata (dupa salvare ramane goala: gol = neschimbata);
#   - HdsLocReteaCautare: serverele gasite in casa (SSDP, NetBIOS, mDNS), numai la cerere; OK adauga serverul ales;
#   - HdsLocReteaRasfoire: dosarele si filmele unui loc; OK intra in dosar sau porneste filmul (cu subtitrarile de
#     langa el), INAPOI urca un dosar.
# Toata logica e in Components/HdsStocareRetea.py (aceeasi in pagina web /locuri-retea): ecranele pornesc lucrarile,
# care merg pe fire si in procese copil, si citesc starea la CITIRE_MS cat lucreaza ceva. Nimic din retea nu ruleaza pe
# firul enigma2.
# Designul: acelasi tipar ca "Ce aparate sunt in retea" (Screens/HdsUnelteRetea.py, din ecranul Stitch al proiectului
# HD Satelit): lista in stanga, caseta cu explicatia si detaliile in dreapta, tastele colorate jos; un bloc cu acelasi
# nume in HDSatelit/skin.xml are intaietate (culorile temei). Editarea are skin propriu cu ambele note.

from enigma import eListboxPythonMultiContent, eTimer, ePoint, eSize, getDesktop, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import ConfigSelection, ConfigText, ConfigPassword, ConfigNumber, ConfigYesNo, \
	getConfigListEntry
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.Sources.StaticText import StaticText
from Components import HdsStocareRetea as S
from Components import HdsMarireText as MT
from Components.HdsPlural import ngettext
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard

CITIRE_MS = 700
# raspunsul ecranului cautarii cand omul alege GALBEN (adauga de mana un server care nu a aparut)
DE_MANA = "de_mana"
# NMS6 (NMT, 17.11): randurile listei locurilor de sub locurile salvate: serverele gasite in casa (cheia ("gasit", k)),
# cautarea in curs si "Adauga de mana"; cheile locurilor salvate sunt texte (id-ul locului), deci nu se amesteca
RAND_GASIT = "gasit"
RAND_CAUTA = ("cauta",)
RAND_DE_MANA = ("de_mana",)
CULOARE_STARE ={"montat": 0x4FD18B, "eroare": 0xFF8A7A, "lucreaza": 0xF5B83D, "nemontat": 0xAEB9CC}


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


def _fontHds(nume):
	try:
		import skin
		return skin.fontHds(nume)
	except Exception:
		return nume


_TASTE = """
		<widget zPosition="1" source="key_red" render="Label" position="80,998" size="300,54" font="Regular;28" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00B3261E" />
		<widget zPosition="1" source="key_green" render="Label" position="400,998" size="300,54" font="Regular;28" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#00137A44" />
		<widget zPosition="1" source="key_yellow" render="Label" position="720,998" size="360,54" font="Regular;28" halign="center" valign="center" foregroundColor="#000B1020" backgroundColor="#00E0B000" />
		<widget zPosition="1" source="key_blue" render="Label" position="1100,998" size="360,54" font="Regular;28" halign="center" valign="center" foregroundColor="#00FFFFFF" backgroundColor="#001F4FA8" />"""


def _skin(nume):
	return """
	<screen name="%s" resolution="1920,1080" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000E1323">
		<widget zPosition="1" name="titlu" position="80,40" size="1760,60" font="Regular;44" noWrap="1" foregroundColor="#00F2F4F8" backgroundColor="#000E1323" transparent="1" />
		<widget zPosition="1" name="subtitlu" position="80,104" size="1760,40" font="Regular;28" noWrap="1" foregroundColor="#00AEB9CC" backgroundColor="#000E1323" transparent="1" />
		<eLabel position="80,160" size="1240,2" backgroundColor="#00F5B83D" />
		<widget zPosition="1" name="lista" position="80,170" size="1240,810" scrollbarMode="showOnDemand" backgroundColor="#000E1323" foregroundColor="#00F2F4F8" backgroundColorSelected="#003A4658" foregroundColorSelected="#00FFF6E0" transparent="1" />
		<eLabel position="1360,160" size="480,560" backgroundColor="#0010162A" />
		<eLabel position="1360,160" size="480,3" backgroundColor="#00F5B83D" />
		<widget zPosition="1" name="cum_titlu" position="1384,180" size="432,40" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="1" name="cum" position="1384,226" size="432,480" font="Regular;24" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" />
		<widget zPosition="1" name="detalii" position="1360,740" size="480,240" font="Regular;24" foregroundColor="#00C9D2E3" backgroundColor="#000E1323" transparent="1" />
		%s
	</screen>""" % (nume, _TASTE)


class _Nota(Label):
	"""Protejeaza numai afisarea barelor; eTextPara ignora CR real pus dupa fiecare bara."""
	def setText(self, text):
		self.original = text or u""
		Label.setText(self, self.original.replace("\\", "\\\r"))
		aseaza = getattr(self, "aseaza", None)
		if aseaza is not None:
			aseaza()

	def getText(self):
		return self.original


def _rect(inst):
	p, s = inst.position(), inst.size()
	return p.x(), p.y(), s.width(), s.height()


def _pune(inst, x, y, w, h):
	inst.move(ePoint(int(x), int(y)))
	inst.resize(eSize(max(1, int(w)), max(1, int(h))))


def _masoara(inst):
	inst.setNoWrap(False)
	inst.setVAlign(0)
	return max(MT.marimeFont(inst) * 3 // 2, MT.inaltimeText(inst))


_FORMULAR = """
	<screen name="HdsLocReteaEditare" resolution="1920,1080" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000E1323">
		<widget source="Title" render="Label" position="80,40" size="1760,80" font="Regular;40" foregroundColor="#00F2F4F8" transparent="1" />
		<widget name="config" position="80,160" size="1760,520" scrollbarMode="showOnDemand" />
		<widget name="description" position="80,700" size="1760,170" font="Regular;28" foregroundColor="#00F2F4F8" transparent="1" />
		<widget name="footnote" position="80,880" size="1760,100" font="Regular;24" foregroundColor="#00AEB9CC" transparent="1" />
		%s
	</screen>""" % _TASTE



class _ParolaLoc(ConfigPassword):
	def __init__(self):
		ConfigPassword.__init__(self, default=u"", fixed_size=False)

class _Lista(Screen):
	"""Baza celor trei ecrane cu lista: randuri de doua linii puse din cod (fonturile urmeaza Marimea textului)."""
	INALTIME = 78

	def __init__(self, session):
		Screen.__init__(self, session)
		self["titlu"] = Label("")
		self["subtitlu"] = Label("")
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["cum_titlu"] = Label("")
		self["cum"] = _Nota("")
		self["detalii"] = _Nota("")
		self["cum"].aseaza = self._aseazaNote
		self["detalii"].aseaza = self._aseazaNote
		self["key_red"] = StaticText("")
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")
		self.f = _factor()
		self.ceas = eTimer()
		self.ceas.callback.append(self.citeste)
		self.inchis = False
		self.onClose.append(self.ceas.stop)
		self.onClose.append(self._inchis)
		self.onLayoutFinish.append(self._asezare)

	def _inchis(self):
		self.inchis = True

	def viu(self, functie):
		"""Raspunsul unei lucrari (vine pe firul enigma2, uneori dupa ce omul a inchis ecranul): ignorat cu ecranul
		inchis, ca nimic sa nu se mai scrie pe widgeturi distruse."""
		def raspuns(*argumente):
			if not self.inchis:
				functie(*argumente)
		return raspuns

	def _asezare(self):
		f = self.f
		l = self["lista"].l
		l.setFont(0, MT.fontCod(_fontHds("Regular"), int(30 * f)))
		l.setFont(1, MT.fontCod(_fontHds("Regular"), int(22 * f)))
		l.setItemHeight(self._y(self.INALTIME))
		MT.randuriCod(self["lista"], self._y(self.INALTIME))
		self["lista"].onSelectionChanged.append(self.detalii)
		self.pornit()
		self._aseazaNote()

	def _aseazaNote(self):
		# Masuram dupa aplicarea temei, inclusiv la 100 la suta si sub teme externe.
		cum, detalii = self["cum"].instance, self["detalii"].instance
		if cum is None or detalii is None:
			return
		if not getattr(self, "_note_asezare", None):
			self._note_asezare = (_rect(cum), _rect(detalii))
		(x, y, w, h), (dx, dy, dw, dh) = self._note_asezare
		gap = max(4, int(12 * self.f))
		jos = dy + dh
		nevoie = _masoara(cum)
		inaltime = min(max(h, nevoie), max(h, jos - y - gap - MT.marimeFont(detalii) * 2))
		_pune(cum, x, y, w, inaltime)
		dy = max(dy, y + inaltime + gap)
		_pune(detalii, dx, dy, dw, jos - dy)

	def _y(self, v):
		return MT.inaltimeCod(int(v * self.f))

	def _latime(self):
		try:
			return self["lista"].instance.size().width()
		except Exception:
			return int(1240 * self.f)

	def rand(self, cheie, sus, jos, dreapta=u"", culoare_dreapta=None, culoare_jos=0xB7C4FF):
		f, y = self.f, self._y
		w = self._latime()
		dr = int(330 * f)
		r = [cheie,
			MultiContentEntryText(pos=(int(12 * f), 0), size=(w - dr - int(24 * f), y(44)), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=sus),
			MultiContentEntryText(pos=(int(12 * f), y(44)), size=(w - dr - int(24 * f), y(30)), font=1,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=jos, color=culoare_jos)]
		if dreapta:
			r.append(MultiContentEntryText(pos=(w - dr, 0), size=(dr - int(12 * f), y(self.INALTIME)), font=1,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=dreapta, color=culoare_dreapta or 0xAEB9CC))
		return r

	def curent(self):
		c = self["lista"].getCurrent()
		return c[0] if c else None

	def pornit(self):
		pass

	def citeste(self):
		pass

	def detalii(self):
		pass


# ------------------------------------------------------------------ lista locurilor

class HdsLocuriRetea(_Lista):
	skin = _skin("HdsLocuriRetea")

	def __init__(self, session):
		_Lista.__init__(self, session)
		self.setTitle(_("Locuri din rețea"))
		self["titlu"].setText(_("Locuri din rețea"))
		self["cum_titlu"].setText(_("Cum merge"))
		self["cum"].setText(_("Locurile SMB și NFS se montează: apar și în Player media, ca un disc, și pot ține "
			"înregistrări. FTP, WebDAV și DLNA se răsfoiesc de aici.\nNimic nu se montează singur. Parolele stau "
			"criptate pe receptor."))
		self["key_red"].setText(_("Închide"))
		self["key_green"].setText(_("Adaugă"))
		self["key_blue"].setText(_("Caută în casă"))
		self.locuri = []
		self.gasite = []
		self.mesaj = u""
		self.cautare_initiala = False
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions"], {
			"ok": self.deschide,
			"cancel": self.close,
			"red": self.close,
			"green": self.adauga,
			"yellow": self.monteazaSauDemonteaza,
			"blue": self.cauta,
			"menu": self.meniu,
		}, -1)

	def pornit(self):
		# NMS6: cautarea serverelor din casa porneste in fundal la deschidere (Components/HdsStocareRetea, pe fir), iar
		# serverele gasite apar direct in lista, sub locurile salvate; fara al doilea ecran. Nimic nu se monteaza singur.
		if not self.cautare_initiala:
			self.cautare_initiala = True
			S.cautaInCasa()
		self.citeste()

	def citeste(self):
		# NMS6: un pas al ceasului (cautarea in fundal) venit dupa inchidere nu mai atinge widgeturile distruse
		if self.inchis:
			return
		ales = self.curent()
		try:
			self.locuri = S.toate()
		except Exception as e:
			print("[HdsLocuriRetea] lista: %s" % e)
			self.locuri = []
		try:
			c = S.rezultatCautare()
		except Exception as e:
			print("[HdsLocuriRetea] cautarea: %s" % e)
			c = {"in_lucru": False, "gasite": []}
		self.gasite = [g for g in c.get("gasite") or [] if not g.get("adaugat")]
		lucreaza = any(l["stare"] == "lucreaza" for l in self.locuri) or bool(c.get("in_lucru"))
		montate = len([l for l in self.locuri if l["montat"]])
		if not self.locuri:
			sub = _("Niciun loc încă. Serverele găsite în casă apar mai jos: OK pe unul îl adaugă.")
		else:
			sub = ngettext("%d loc", "%d locuri", len(self.locuri)) % len(self.locuri)
			if montate:
				sub += u" · " + (ngettext("%d loc montat", "%d locuri montate", montate) % montate)
		self["subtitlu"].setText(self.mesaj or sub)
		randuri = []
		for l in self.locuri:
			# in rand numai felul si serverul (adresa intreaga, care poate fi lunga, sta in detalii)
			gazda = l["gazda"].split("/")[2] if l["fel"] == "dlna" and "//" in l["gazda"] else l["gazda"]
			randuri.append(self.rand(l["id"], l["nume"], u"%s · %s" % (l["fel_scurt"], gazda), l["stare_scurt"],
				CULOARE_STARE.get(l["stare"])))
		for k, g in enumerate(self.gasite):
			randuri.append(self.rand((RAND_GASIT, k), _("Găsit în casă: %s") % g["nume"],
				u"%s · %s" % (g["fel_text"], g.get("ip") or g["gazda"]), _("OK: adaugă")))
		if c.get("in_lucru"):
			randuri.append(self.rand(RAND_CAUTA, _("Se caută serverele din casă..."), _("Cele găsite apar aici."),
				culoare_jos=0xAEB9CC))
		elif c.get("cod") and not self.gasite:
			randuri.append(self.rand(RAND_CAUTA, _("Căutarea în casă nu a mers"), S.textEroare(c["cod"]),
				culoare_jos=0xFF8A7A))
		randuri.append(self.rand(RAND_DE_MANA, _("Adaugă de mână"), _("Un server care nu apare, cu adresa lui")))
		self["lista"].setList(randuri)
		if ales:
			for i, rnd in enumerate(randuri):
				if rnd[0] == ales:
					self["lista"].moveToIndex(i)
					break
		self.detalii()
		if lucreaza:
			self.ceas.start(CITIRE_MS, True)

	def loc(self):
		ident = self.curent()
		for l in self.locuri:
			if l["id"] == ident:
				return l
		return None

	def _gasit(self):
		"""Serverul gasit de sub cursor, sau None."""
		k = self.curent()
		if isinstance(k, tuple) and len(k) == 2 and k[0] == RAND_GASIT and k[1] < len(self.gasite):
			return self.gasite[k[1]]
		return None

	def detalii(self):
		l = self.loc()
		if l is None:
			g = self._gasit()
			if g is not None:
				self["detalii"].setText(u"\n".join([g["nume"], g["fel_text"], g.get("ip") or g["gazda"],
					_("OK: îl adaugi; la SMB și NFS, VERDE îl salvează și îl montează.")]))
			elif self.curent() == RAND_DE_MANA:
				self["detalii"].setText(_("Scrii singur serverul (adresa sau numele lui), dosarul și, dacă trebuie, "
					"utilizatorul și parola."))
			else:
				self["detalii"].setText(u"")
			self["key_yellow"].setText(u"")
			return
		linii = [l["fel_text"], l["adresa"]]
		if l["utilizator"]:
			linii.append(_("Utilizator: %s") % l["utilizator"] + u" · " + (l.get("parola", "") if l["are_parola"]
				else _("fără parolă salvată")))
		if l["montat"]:
			linii.append(_("Montat în %s") % l["punct"])
		if l["inregistrari"]:
			linii.append(_("Bun pentru înregistrări (%s MB/s la scriere)") % S.numar(l["viteza"]))
		if l["pornire"]:
			linii.append(_("Se montează și după repornire"))
		if l["stare"] == "eroare" and l["mesaj"]:
			linii.append(l["mesaj"])
		self["detalii"].setText(u"\n".join(linii))
		if l["montabil"]:
			self["key_yellow"].setText(_("Demontează") if l["montat"] else _("Montează"))
		else:
			self["key_yellow"].setText(_("Deschide"))

	def _arata(self, text):
		self.mesaj = text or u""
		self.citeste()

	def deschide(self):
		l = self.loc()
		if l is not None:
			self.session.openWithCallback(lambda *a: self.citeste(), HdsLocReteaRasfoire, l["id"])
			return
		g = self._gasit()
		if g is not None:
			self.adauga(S.dinCautare(g))
		elif self.curent() == RAND_DE_MANA:
			self.adauga()

	def monteazaSauDemonteaza(self):
		l = self.loc()
		if l is None:
			return
		if not l["montabil"]:
			self.deschide()
			return
		self.mesaj = u""
		if l["montat"]:
			S.demonteaza(l["id"], self.viu(lambda r: self._arata(r.get("mesaj") if not r.get("ok") else _("Locul %s a fost "
				"demontat.") % l["nume"])), numai_liber=True, sesiune=self.session)
		else:
			S.monteaza(l["id"], self.viu(lambda r: self._arata(r.get("mesaj") if not r.get("ok") else _("Locul %s este montat. "
				"Îl găsești și în Player media.") % l["nume"])))
		self.citeste()
		self.ceas.start(CITIRE_MS, True)

	def adauga(self, date=None):
		self.session.openWithCallback(self._dupaEditare, HdsLocReteaEditare, None, date)

	def _dupaEditare(self, rez=None):
		self.mesaj = rez or u""
		self.citeste()

	def cauta(self):
		# NMS6: ALBASTRU (si MENU > Cauta) cauta din nou in fundal, in aceeasi lista (fara al doilea ecran)
		S.cautaInCasa()
		self.citeste()

	def _ales(self, g=None):
		if g == DE_MANA:
			self.adauga()
		elif g:
			self.adauga(S.dinCautare(g))
		else:
			self.citeste()

	def meniu(self):
		l = self.loc()
		lista = [(_("Adaugă un loc"), "adauga"), (_("Caută serverele din casă"), "cauta")]
		if l is not None:
			lista = [(_("Deschide"), "deschide")]
			if l["montabil"]:
				lista.append((_("Demontează") if l["montat"] else _("Montează"), "monteaza"))
				lista.append((_("Folosește pentru înregistrări (verifică scrierea și viteza)"), "inregistrari"))
			lista += [(_("Editează"), "editeaza"), (_("Șterge"), "sterge"), (_("Adaugă un loc"), "adauga"),
				(_("Caută serverele din casă"), "cauta")]
		self.session.openWithCallback(self._dinMeniu, ChoiceBox, title=_("Locuri din rețea"), list=lista)

	def _dinMeniu(self, ales):
		if not ales:
			return
		l = self.loc()
		a = ales[1]
		if a == "adauga":
			self.adauga()
		elif a == "cauta":
			self.cauta()
		elif l is None:
			return
		elif a == "deschide":
			self.deschide()
		elif a == "monteaza":
			self.monteazaSauDemonteaza()
		elif a == "editeaza":
			self.session.openWithCallback(self._dupaEditare, HdsLocReteaEditare, l["id"])
		elif a == "sterge":
			self.session.openWithCallback(self._sterge, MessageBox, _("Ștergi locul %s? Fișierele de pe server nu se "
				"ating.") % l["nume"], MessageBox.TYPE_YESNO, default=False)
		elif a == "inregistrari":
			self._inregistrari(l)

	def _sterge(self, da):
		l = self.loc()
		if da and l is not None:
			S.sterge(l["id"], self.viu(lambda r: self._arata(_("Locul %s a fost șters.") % l["nume"] if r.get("ok") else
				r.get("mesaj"))), sesiune=self.session)

	def _inregistrari(self, l):
		self.mesaj = _("Se verifică scrierea și viteza (până la un minut)...")
		S.folosesteInregistrari(l["id"], self.viu(lambda r: self._arata(r.get("mesaj"))), sesiune=self.session)
		self.citeste()
		self.ceas.start(CITIRE_MS, True)


# ------------------------------------------------------------------ cautarea in casa

class HdsLocReteaCautare(_Lista):
	skin = _skin("HdsLocReteaCautare")

	def __init__(self, session):
		_Lista.__init__(self, session)
		self.setTitle(_("Caută serverele din casă"))
		self["titlu"].setText(_("Caută serverele din casă"))
		self["cum_titlu"].setText(_("Cum se caută"))
		self["cum"].setText(_("Receptorul întreabă scurt aparatele din rețeaua ta: servere media, calculatoare cu "
			"Windows, NAS-uri. Nimic nu pleacă în afara rețelei.\nUn calculator care nu apare se adaugă de mână, cu "
			"adresa lui."))
		self["key_red"].setText(_("Închide"))
		self["key_green"].setText(_("Caută din nou"))
		# un NAS care nu raspunde la cautare se adauga de aici, si cat inca se cauta (fara Inchide, apoi VERDE dedesubt)
		self["key_yellow"].setText(_("Adaugă un loc"))
		self.gasite = []
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.alege,
			"cancel": self.close,
			"red": self.close,
			"green": self.cauta,
			"yellow": self.deMana,
		}, -1)

	def pornit(self):
		self.cauta()

	def cauta(self):
		S.cautaInCasa()
		self.citeste()

	def citeste(self):
		c = S.rezultatCautare()
		if c["in_lucru"]:
			self["subtitlu"].setText(_("Se caută serverele din casă..."))
			self.ceas.start(CITIRE_MS, True)
			return
		if c.get("cod"):
			self["subtitlu"].setText(S.textEroare(c["cod"]))
		self.gasite = c["gasite"]
		if not self.gasite and not c.get("cod"):
			self["subtitlu"].setText(_("Nu s-a găsit niciun server. Verifică dacă e pornit sau adaugă-l de mână."))
		elif self.gasite:
			self["subtitlu"].setText(ngettext("%d server găsit", "%d servere găsite", len(self.gasite)) %
				len(self.gasite) + u" · " + _("OK: îl adaugi"))
		randuri = []
		for k, g in enumerate(self.gasite):
			adresa = g.get("ip") or g["gazda"]
			randuri.append(self.rand(k, g["nume"], u"%s · %s" % (g["fel_text"], adresa),
				_("adăugat deja") if g.get("adaugat") else u""))
		self["lista"].setList(randuri)
		self.detalii()

	def detalii(self):
		k = self.curent()
		if k is None or k >= len(self.gasite):
			self["detalii"].setText(u"")
			return
		g = self.gasite[k]
		self["detalii"].setText(u"\n".join([g["nume"], g["fel_text"], g.get("ip") or g["gazda"]]))

	def alege(self):
		k = self.curent()
		if k is not None and k < len(self.gasite):
			self.close(self.gasite[k])

	def deMana(self):
		self.close(DE_MANA)


# ------------------------------------------------------------------ rasfoirea unui loc

class HdsLocReteaRasfoire(_Lista):
	skin = _skin("HdsLocReteaRasfoire")

	def __init__(self, session, ident):
		_Lista.__init__(self, session)
		self.ident = ident
		self.loc = S.locuri().dupaId(ident) or {"nume": u"", "fel": u""}
		self.drum = []          # [(nume afisat, cale)] pana la dosarul de acum
		self.intrari = []
		self.toate = []
		self.lucreaza = False
		self.generatie = 0
		self.setTitle(self.loc["nume"])
		self["titlu"].setText(self.loc["nume"])
		self["cum_titlu"].setText(_("Ce poți face"))
		self["cum"].setText(_("OK: intri în dosar sau pornești filmul.\nINAPOI: dosarul de mai sus.\nSubtitrările de lângă "
			"film se iau singure; tasta SUB le arată pe toate și caută pe internet."))
		self["key_red"].setText(_("Înapoi"))
		self["key_green"].setText(_("Redă"))
		self["key_yellow"].setText(_("Reîncarcă"))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.inapoi,
			"red": self.inapoi,
			"green": self.reda,
			"yellow": self.incarca,
		}, -1)

	def pornit(self):
		self.incarca()

	def cale(self):
		if self.loc.get("fel") == "dlna":
			return self.drum[-1][1] if self.drum else (self.loc.get("dosar") or u"0")
		return self.drum[-1][1] if self.drum else u""

	def _subtitlu(self, text=None):
		if text is None:
			if self.drum:
				text = u" › ".join([self.loc["nume"]] + [d[0] for d in self.drum])
			else:
				text = S._adresaAfisata(self.loc) if self.loc.get("fel") != "dlna" else S.textFel("dlna")
		self["subtitlu"].setText(text)

	def _lucrare(self, functie):
		"""Raspunsul lucrarii de acum (generatia ei); unul venit dupa INAPOI sau dupa inchidere se ignora."""
		self.generatie += 1
		g = self.generatie

		def raspuns(r):
			if not self.inchis and g == self.generatie:
				self.lucreaza = False
				functie(r)
		return raspuns

	def incarca(self):
		self.lucreaza = True
		self._subtitlu(_("Se citește dosarul..."))
		S.listeaza(self.ident, self.cale(), self._lucrare(self._listat))

	def _listat(self, r):
		if not r.get("ok"):
			self._subtitlu(r.get("mesaj") or S.textEroare("alta"))
			self.intrari = []
			self["lista"].setList([])
			self.detalii()
			return
		self.intrari = r["intrari"]
		self.toate = r.get("toate") or []
		self._subtitlu()
		randuri = []
		for k, i in enumerate(self.intrari):
			if i.get("dosar"):
				jos = _("Dosar")
				dreapta = u""
			else:
				jos = _("Film") if i.get("fel") == "film" else _("Muzică")
				dreapta = S.marime(i.get("marime"))
				if i.get("durata"):
					dreapta = S.durata(i["durata"]) + (u" · " + dreapta if dreapta else u"")
			randuri.append(self.rand(k, i["nume"], jos, dreapta))
		self["lista"].setList(randuri)
		if not randuri:
			self._subtitlu(_("Dosarul nu are filme, muzică sau alte dosare."))
		self.detalii()

	def intrare(self):
		k = self.curent()
		if k is None or k >= len(self.intrari):
			return None
		return self.intrari[k]

	def detalii(self):
		i = self.intrare()
		if i is None:
			self["detalii"].setText(u"")
			return
		linii = [i["nume"]]
		if not i.get("dosar"):
			if i.get("marime"):
				linii.append(S.marime(i["marime"]))
			subs = S.subtitrariLangaFilm(i["nume"], self.toate)[0] if self.loc.get("fel") != "dlna" else \
				i.get("subtitrari") or []
			if subs:
				linii.append(ngettext("%d subtitrare lângă film", "%d subtitrări lângă film", len(subs)) % len(subs))
		self["detalii"].setText(u"\n".join(linii))

	def ok(self):
		i = self.intrare()
		if i is None:
			return
		if i.get("dosar"):
			self.drum.append((i["nume"], i["cale"]))
			self.incarca()
		else:
			self.reda()

	def inapoi(self):
		# merge si cat se citeste un dosar (un server care nu mai raspunde nu tine omul pe ecran): raspunsul vechi se
		# ignora
		if self.lucreaza:
			self.generatie += 1
			self.lucreaza = False
		if self.drum:
			self.drum.pop()
			self.incarca()
		else:
			self.close()

	def reda(self):
		i = self.intrare()
		if i is None or i.get("dosar") or self.lucreaza:
			return
		self.lucreaza = True
		self._subtitlu(_("Se pregătește filmul..."))
		S.pregatesteRedarea(self.ident, i, self.toate, self._lucrare(self._gata))

	def _gata(self, r):
		self._subtitlu()
		if not r.get("ok"):
			self.session.open(MessageBox, r.get("mesaj") or S.textEroare("alta"), MessageBox.TYPE_ERROR, timeout=10)
			return
		try:
			from Screens.InfoBar import MoviePlayer
			ref = S.referinta(r)
			self.session.openWithCallback(self._dupaFilm, MoviePlayer, ref)
		except Exception as e:
			print("[HdsLocuriRetea] redarea: %s" % e)
			S.dupaRedare()

	def _dupaFilm(self, *a):
		S.dupaRedare()


# ------------------------------------------------------------------ adaugarea si editarea unui loc


class HdsLocReteaEditare(ConfigListScreen, Screen):
	"""ident None: loc nou (date: din cautarea in casa). Inchis cu textul de aratat in lista, sau None."""
	skin = _FORMULAR

	def __init__(self, session, ident=None, date=None):
		Screen.__init__(self, session)
		self.skinName = ["HdsLocReteaEditare"]
		self.ident = ident
		vechi = S.locuri().dupaId(ident) if ident else None
		d = dict(vechi or {})
		d.update(date or {})
		self.control = d.get("control") or u""
		self.setTitle(_("Editează locul") if vechi else _("Adaugă un loc din rețea"))
		self.fel = ConfigSelection(choices=[(f, S.textFel(f)) for f in S.FELURI], default=d.get("fel") or "smb")
		self.nume = ConfigText(default=d.get("nume") or u"", fixed_size=False)
		self.gazda = ConfigText(default=d.get("gazda") or u"", fixed_size=False)
		self.port = ConfigNumber(default=int(d.get("port") or 0))
		self.dosar = ConfigText(default=d.get("dosar") or u"", fixed_size=False)
		self.utilizator = ConfigText(default=d.get("utilizator") or u"", fixed_size=False)
		self.parola = _ParolaLoc()
		# un loc nou: Montat si dupa repornire ramane din fabrica Nu, ca pana in 0.7.6 (regula 17.11 16:08: ce era ramane,
		# omul il bifeaza daca vrea); cel salvat ramane cum l-a lasat omul
		self.pornire = ConfigYesNo(default=bool(d.get("pornire")) if (vechi or "pornire" in d) else False)
		self.citire = ConfigYesNo(default=bool(d.get("citire")))
		self.tls = ConfigYesNo(default=bool(d.get("tls_oricare")))
		self.are_parola = bool(vechi and vechi.get("utilizator") and S.parole().are(ident))
		self.parola.value = S.parole().parola(ident) or ""
		self["description"] = _Nota(u"")
		self["footnote"] = _Nota(u"")
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Salvează"))
		self["key_yellow"] = StaticText(u"")
		self["key_blue"] = StaticText(_("Tastatura"))
		self._note_pregatite = False
		ConfigListScreen.__init__(self, [], session=session, on_change=self._schimbat)
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"cancel": self.renunta,
			"red": self.renunta,
			"green": self.salveaza,
			"save": self.salveaza,
			"yellow": self.alegeDosarul,
			"blue": self.tastatura,
			"ok": self.ok,
		}, -2)
		self.inchis = False
		self.salvare = False
		self.onClose.append(self._inchis)
		self.fel.addNotifier(self._felSchimbat, initial_call=False)
		self._randuri()
		self["config"].onSelectionChanged.append(self._descriere)
		self.onLayoutFinish.append(self._descriere)
		self.onLayoutFinish.append(self._noteDinSkin)
		self["description"].aseaza = self._aseazaNote
		self["footnote"].aseaza = self._aseazaNote
		# serverul ales din cautarea in casa (SMB, NFS): lista dosarelor se cere singura, ca omul sa aleaga dosarul din ea;
		# la prima executie (lista e alt ecran, Session.open o refuza din onLayoutFinish)
		if not vechi and date and d.get("gazda") and d.get("fel") in S.FELURI_MONTATE and not d.get("dosar"):
			self.onFirstExecBegin.append(lambda: self.alegeDosarul(automat=True))

	def _inchis(self):
		self.inchis = True

	def _noteDinSkin(self):
		# setContent anunta selectia inainte de ConfigList.applySkin. Dimensiunile
		# initiale nu trebuie pastrate ca marime definitiva a formularului.
		self._note_pregatite = True
		self._aseazaNote()

	def _aseazaNote(self):
		if not self._note_pregatite:
			return
		config = getattr(self["config"], "instance", None)
		desc, nota = self["description"].instance, self["footnote"].instance
		if config is None or desc is None or nota is None:
			return
		if not getattr(self, "_note_asezare", None):
			self._note_asezare = (_rect(config), _rect(desc), _rect(nota))
		(cx, cy, cw, ch), (dx, dy, dw, dh), (nx, ny, nw, nh) = self._note_asezare
		gap = max(4, int(12 * _factor()))
		# Tastele StaticText nu au widget propriu; geometria este la renderer.
		jos = min(self.instance.size().height() - gap, max(dy + dh, ny + nh))
		taste = [self[n] for n in ("key_red", "key_green", "key_yellow", "key_blue")]
		for renderer in getattr(self, "renderer", ()):
			if getattr(renderer, "source", None) in taste:
				inst = getattr(renderer, "instance", None)
				if inst is not None and inst.position().y() > cy:
					jos = min(jos, inst.position().y() - gap)
		for nume in ("key_red", "key_green", "key_yellow", "key_blue"):
			inst = getattr(self[nume], "instance", None)
			if inst is not None and inst.position().y() > cy:
				jos = min(jos, inst.position().y() - gap)
		dh, nh = _masoara(desc), _masoara(nota)
		ny = jos - nh
		dy = ny - gap - dh
		_pune(config, cx, cy, cw, min(ch, dy - gap - cy))
		_pune(desc, dx, dy, dw, dh)
		_pune(nota, nx, ny, nw, nh)

	def _randuri(self):
		fel = self.fel.value
		r = [getConfigListEntry(_("Felul locului"), self.fel, "fel"),
			getConfigListEntry(_("Numele (cum apare în listă)"), self.nume, "nume")]
		if fel == "dlna":
			r.append(getConfigListEntry(_("Adresa serverului media"), self.gazda, "gazda"))
		else:
			r.append(getConfigListEntry(_("Serverul (nume sau adresă)"), self.gazda, "gazda"))
			r.append(getConfigListEntry(_("Dosarul partajat") if fel == "smb" else (_("Dosarul exportat") if fel == "nfs"
				else _("Dosarul (gol: tot serverul)")), self.dosar, "dosar"))
		if fel not in ("dlna", "nfs"):
			r.append(getConfigListEntry(_("Utilizatorul (gol: fără cont)"), self.utilizator, "utilizator"))
			r.append(getConfigListEntry(_("Parola"), self.parola, "parola"))
		if fel != "dlna":
			r.append(getConfigListEntry(_("Portul (0: cel obișnuit)"), self.port, "port"))
		if fel in S.FELURI_MONTATE:
			r.append(getConfigListEntry(_("Montat și după repornire"), self.pornire, "pornire"))
			r.append(getConfigListEntry(_("Numai citire"), self.citire, "citire"))
		if fel in ("ftps", "webdavs"):
			r.append(getConfigListEntry(_("Primește un certificat făcut acasă"), self.tls, "tls"))
		self["config"].list = r
		self["config"].l.setList(r)
		self["key_yellow"].setText(_("Alege dosarul") if fel in S.FELURI_MONTATE else u"")
		# NMS6: la SMB si NFS salvarea il si monteaza (S.salveazaSiConecteaza), deci tasta o spune
		self["key_green"].setText(_("Salvează și montează") if fel in S.FELURI_MONTATE else _("Salvează"))

	def _felSchimbat(self, element):
		self._randuri()

	def _schimbat(self):
		self._descriere()

	def _cheie(self):
		c = self["config"].getCurrent()
		return c[2] if c and len(c) > 2 else ""

	def _mergiLa(self, cheie):
		for i, rand in enumerate(self["config"].list):
			if len(rand) > 2 and rand[2] == cheie:
				self["config"].setCurrentIndex(i)
				return

	def _descriere(self):
		k = self._cheie()
		fel = self.fel.value
		texte = {
			"fel": _("SMB: calculatorul cu Windows sau NAS-ul (dosarele partajate). NFS: NAS sau Linux. FTP și WebDAV: "
				"servere de fișiere. DLNA: serverul media din casă (folosește Caută în casă)."),
			"nume": _("Un nume ușor de recunoscut, de pildă NAS sufragerie."),
			"gazda": _("Numele calculatorului sau adresa lui, de pildă 192.168.1.20. Merge și \\\\NAS\\Filme sau "
				"nas:/volume1/filme: se despart singure."),
			"dosar": _("SMB: numele dosarului partajat, de pildă Filme. NFS: dosarul exportat, de pildă volume1/filme. "
				"GALBEN: lista de pe server."),
			"utilizator": _("Contul de pe server. Pe Windows: numele contului sau CASA\\nume. Gol: fără cont "
				"(oaspete)."),
			"parola": _("Se păstrează criptată pe receptor și se vede după salvare. Gol: rămâne parola de acum.")
				if self.are_parola else _("Se păstrează criptată pe receptor și se vede după salvare."),
			"port": _("0 înseamnă portul obișnuit al felului ales."),
			"pornire": _("Da: locul se montează singur la 30 de secunde după pornire, în fundal. Trebuie pentru "
				"înregistrările programate pe el."),
			"citire": _("Da: pe loc nu se scrie nimic (nici înregistrări)."),
			"tls": _("Da numai pentru un server din casă cu certificat făcut de tine (NAS)."),
		}
		self["description"].setText(texte.get(k, u""))
		self["footnote"].setText(textFelScurt(fel))

	def ok(self):
		if self._cheie() in ("nume", "gazda", "dosar", "utilizator", "parola"):
			self.tastatura()
		elif self._cheie() == "fel":
			self.keyRight()

	def tastatura(self):
		c = self["config"].getCurrent()
		if not c or not isinstance(c[1], ConfigText):
			return
		element = c[1]
		text = element.value
		self.session.openWithCallback(lambda t: self._scris(element, t), VirtualKeyBoard,
			title=c[0], text=text, hdsSecret=element is self.parola)

	def _scris(self, element, text):
		if text is None:
			return
		element.value = text
		if element is self.parola:
			# parola scrisa acum: se vede in clar pana la salvare
			element.scrisa = True
		self["config"].invalidateCurrent()
		self._descriere()

	def _date(self):
		return {"fel": self.fel.value, "nume": self.nume.value, "gazda": self.gazda.value, "port": self.port.value,
			"dosar": self.dosar.value, "utilizator": self.utilizator.value, "pornire": self.pornire.value,
			"citire": self.citire.value, "tls_oricare": self.tls.value, "control": self.control}

	def salveaza(self):
		if self.salvare:
			return
		parola = self.parola.value
		if not parola:
			parola = None if self.are_parola else (u"" if self.utilizator.value else None)
		self.salvare = True
		self["footnote"].setText(_("Se salvează și se conectează locul..."))
		S.salveazaSiConecteaza(self._date(), parola, self.ident, self._salvat, sesiune=self.session)

	def _salvat(self, r):
		self.salvare = False
		if self.inchis:
			return
		if not r.get("ok"):
			self.ident = (r.get("loc") or {}).get("id") or self.ident
			self.parola.value = u""
			self.are_parola = bool(self.ident and S.parole().are(self.ident))
			self._descriere()
			self["footnote"].setText(r.get("mesaj") or S.textEroare("alta"))
			return
		self.close(r.get("mesaj"))

	def renunta(self):
		self.close(None)

	def alegeDosarul(self, automat=False):
		fel = self.fel.value
		if fel not in S.FELURI_MONTATE:
			return
		gazda, _p, _d = S.desparteGazda(self.gazda.value, fel)
		if not S.gazdaBuna(gazda):
			if not automat:
				self.session.open(MessageBox, _("Scrie întâi serverul."), MessageBox.TYPE_INFO, timeout=6)
			return
		self["footnote"].setText(_("Se cere lista dosarelor de la server..."))
		parola = self.parola.value or None
		S.dosareServer(fel, gazda, self.utilizator.value, self.ident if not parola else None, parola,
			lambda r: self._dosare(r, automat), port=self.port.value)

	def _dosare(self, r, automat=False):
		if self.inchis:       # raspunsul a venit dupa ce omul a inchis ecranul
			return
		self._descriere()
		if automat and (not r.get("ok") or not r.get("dosare")):
			# cererea singura, dupa cautare: fara fereastra; o eroare sta in nota de jos, iar cursorul merge pe randul de
			# completat: utilizatorul cand serverul SMB cere cont, serverul cand nu raspunde, altfel dosarul
			if r.get("ok"):
				rand = "dosar"
			elif r.get("cod") in ("acces", "parola") and self.fel.value == "smb":
				rand = "utilizator"
			elif r.get("cod") in ("server", "nume", "termen"):
				rand = "gazda"
			else:
				rand = "dosar"
			self._mergiLa(rand)
			self["footnote"].setText(r.get("mesaj") or (S.textEroare(r.get("cod") or "alta") if not r.get("ok") else
				_("Serverul nu a dat niciun dosar.")))
			return
		if not r.get("ok"):
			self.session.open(MessageBox, r.get("mesaj") or S.textEroare("alta"), MessageBox.TYPE_ERROR, timeout=10)
			return
		dosare = r.get("dosare") or []
		if not dosare:
			self.session.open(MessageBox, _("Serverul nu a dat niciun dosar."), MessageBox.TYPE_INFO, timeout=8)
			return
		self.session.openWithCallback(self._dosarAles, ChoiceBox, title=_("Dosarele serverului"),
			list=[(d, d) for d in dosare])

	def _dosarAles(self, ales):
		if ales:
			self.dosar.value = ales[1].strip("/")
			if not self.nume.value:
				self.nume.value = ales[1].strip("/").rsplit("/", 1)[-1]
			self["config"].l.setList(self["config"].list)
			self._descriere()


def textFelScurt(fel):
	return {
		"smb": _("Se montează pe receptor: apare în Player media și poate ține înregistrări."),
		"nfs": _("Se montează pe receptor: apare în Player media și poate ține înregistrări."),
		"ftp": _("Se răsfoiește din Locuri din rețea; filmele merg cu salturi și subtitrări."),
		"ftps": _("Ca FTP, cu legătura criptată."),
		"webdav": _("Se răsfoiește din Locuri din rețea; filmele merg cu salturi și subtitrări."),
		"webdavs": _("Ca WebDAV, cu legătura criptată (HTTPS)."),
		"dlna": _("Se răsfoiește ca pe server; subtitrările date de server se iau singure."),
	}.get(fel, u"")


def deschide(session, **kwargs):
	session.open(HdsLocuriRetea)

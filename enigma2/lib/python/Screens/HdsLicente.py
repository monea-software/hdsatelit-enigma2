# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLicente.py: ecranul „Licențe” (Meniu > Informații sistem > Licențe, langa „Despre imagine”): programele din
# imagine si licentele lor, componentele din pachetele fabricantului, fonturile, listele de canale, al cui e imaginea
# si adresa codului sursa al versiunii. OK pe un rand deschide textul licentei (HdsLicenteText). Numai sagetile si OK:
# Sus/Jos randul, Stanga/Dreapta pagina, OK textul, EXIT inchide.
#
# Datele si textele sunt in Components/HdsLicente.py (aceleasi in pagina web /licente). Lista din imagine si starea
# pachetelor (instalate dupa construire, alt build) se citesc pe un fir; ecranul le culege dintr-un eTimer (pana atunci
# „Se citește...”) si pune pachetele noi primele in lista. O lista citita o data ramane in memorie.
#
# Textul unei licente se citeste cand e aratat, cate unul (nu toate textele randului la deschidere): un text lung se
# imparte in parti de cel mult RANDURI_PARTE randuri, iar Stanga/Dreapta trec prin parti si apoi prin textele randului.
#
# Skinul: blocurile <screen name="HdsLicente"> si <screen name="HdsLicenteText"> din skinul HDSatelit (1920x1080).
# Pentru alte skinuri, skinul de rezerva de mai jos, facut la deschidere dupa marimea ecranului, numai cu fontul
# „Regular” si culori scrise direct.

from enigma import eTimer, getDesktop

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components import HdsLicente as L

# cat de des se culege starea citita pe fir
PAS_MS = 250

# asezarea din skinul HDSatelit (1920x1080), aceeasi in skinul de rezerva. Marimea literelor aleasa de om (80-130 %)
# mareste fontul, nu casetele, deci casetele tin textul si la 130 %:
#   text: 2 randuri de 32 px (starea listei; la lista veche numai ce s-a schimbat), cu loc si pentru literele de
#     130 % (2 randuri de 42 px);
#   autor, detaliu: cate un rand de 26 px (al cui e imaginea, adresa codului sursa);
#   lista: 10 randuri de 48 px;
#   rand: explicatia randului ales, 4 randuri de 26 px (3 la 130 %);
#   ajutor: 1 rand de 24 px.
ASEZARE = {
	"px": 120, "py": 48, "pl": 1680, "ph": 984, "linie": 2,
	"mx": 40, "cl": 1600,
	"ty": 24, "th": 60, "tf": 42,
	"xy": 88, "xh": 114, "xf": 32,
	"uy": 202, "uh": 36,
	"dy": 238, "dh": 36, "df": 26,
	"ly": 276, "lh": 480, "li": 48, "lf": 30,
	"ry": 764, "rh": 160,
	"ay": 932, "ah": 36, "af": 24,
}
RANDURI_LISTA = 10

ASEZARE_TEXT = {
	"px": 120, "py": 48, "pl": 1680, "ph": 984, "linie": 2,
	"mx": 40, "cl": 1600,
	"ty": 24, "th": 60, "tf": 42,
	"sy": 88, "sh": 40, "sf": 26,
	"xy": 140, "xh": 780, "xf": 30,
	"ay": 932, "ah": 36, "af": 24,
}


def _scalat(asezare, latime, inaltime):
	"""Aceeasi asezare micsorata cu un singur factor (dat de inaltime, cat timp fereastra incape in latime), fereastra
	in mijloc."""
	f = min(inaltime / 1080.0, (latime - 40) / float(asezare["pl"]))
	return dict((k, max(1, int(round(v * f)))) for k, v in asezare.items())


def skinRezerva(latime, inaltime):
	"""Skinul listei cand skinul ales nu are blocul HdsLicente."""
	v = _scalat(ASEZARE, latime, inaltime)
	# lista are exact RANDURI_LISTA randuri dupa rotunjire (altfel apare bara de derulare mai devreme)
	v["lh"] = v["li"] * RANDURI_LISTA
	v["ry"] = v["ly"] + v["lh"] + max(1, int(round(8 * v["li"] / 48.0)))
	v["ay"] = v["ry"] + v["rh"] + max(1, int(round(8 * v["li"] / 48.0)))
	v["ph"] = v["ay"] + v["ah"] + max(1, int(round(16 * v["li"] / 48.0)))
	return """
	<screen name="HdsLicente" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Licențe">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget source="text" render="Label" position="%(mx)d,%(xy)d" size="%(cl)d,%(xh)d" font="Regular;%(xf)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="autor" render="Label" position="%(mx)d,%(uy)d" size="%(cl)d,%(uh)d" font="Regular;%(df)d" valign="center" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget source="detaliu" render="Label" position="%(mx)d,%(dy)d" size="%(cl)d,%(dh)d" font="Regular;%(df)d" valign="center" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget name="list" position="%(mx)d,%(ly)d" size="%(cl)d,%(lh)d" itemHeight="%(li)d" font="Regular;%(lf)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<widget source="rand" render="Label" position="%(mx)d,%(ry)d" size="%(cl)d,%(rh)d" font="Regular;%(df)d" valign="top" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="ajutor" render="Label" position="%(mx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" valign="center" foregroundColor="#00a0a8b8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
	</screen>""" % v


def skinRezervaText(latime, inaltime):
	"""Skinul textului unei licente cand skinul ales nu are blocul HdsLicenteText."""
	v = _scalat(ASEZARE_TEXT, latime, inaltime)
	return """
	<screen name="HdsLicenteText" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Licențe">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget source="parte" render="Label" position="%(mx)d,%(sy)d" size="%(cl)d,%(sh)d" font="Regular;%(sf)d" valign="center" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget name="text" position="%(mx)d,%(xy)d" size="%(cl)d,%(xh)d" font="Regular;%(xf)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="ajutor" render="Label" position="%(mx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" valign="center" foregroundColor="#00a0a8b8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
	</screen>""" % v


def _nimic():
	pass


class HdsLicente(Screen):
	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = skinRezerva(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = _("Licențe")
		self.setTitle(titlu)
		self._lista, self._eroare, self._citit = L.listaTinuta()
		self._stare = None
		self._randuri = []
		# omul a mutat cursorul: dupa o citire noua ramane pe acelasi rand; altfel cursorul sta pe primul rand (pachetele
		# instalate dupa construire sunt la sfarsitul listei, Components/HdsLicente.py)
		self._mutat = False
		self["titlu"] = StaticText(titlu)
		self["text"] = StaticText("")
		self["autor"] = StaticText(L.textAutor())
		self["detaliu"] = StaticText("")
		self["list"] = MenuList([])
		self["rand"] = StaticText("")
		self["ajutor"] = StaticText(_("OK: textul licenței    Stânga/Dreapta: pagina    EXIT: închide"))
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"up": self._sus,
			"down": self._jos,
			"left": self._paginaSus,
			"right": self._paginaJos,
			"upRepeated": self._sus,
			"downRepeated": self._jos,
			"leftRepeated": self._paginaSus,
			"rightRepeated": self._paginaJos,
			# ridicarea tastei: nimic de facut, dar legata, ca jurnalul sa nu scrie „unknown action”
			"upUp": _nimic,
			"downUp": _nimic,
			"leftUp": _nimic,
			"rightUp": _nimic,
		}, -1)
		self["list"].onSelectionChanged.append(self._randAles)
		self._ceas = eTimer()
		self._ceas.callback.append(self._culege)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)

	def _porneste(self):
		self._randuriMarite()
		self._arata()
		self._culege()

	def _randuriMarite(self):
		"""Textul marit (Marimea textului peste 100 %): randul listei (itemHeight din skin, care nu se mareste) creste cu
		procentul, ca fontul lui; la 130 % textul randului ales iesea din banda (jos taiat). La 100 % nu se schimba
		nimic."""
		try:
			from Components import HdsMarireText as MT
			MT.randuriMarite(self["list"])
		except Exception as e:
			print("[HdsLicente] textul marit: %s" % e)

	def _culege(self):
		# lista citita de fir se ia din memorie (listaTinuta face numai un stat); cat nu e citita, i se cere firului
		# (un fir care merge deja nu se porneste a doua oara)
		schimbat = False
		if not self._citit:
			self._lista, self._eroare, self._citit = L.listaTinuta()
			schimbat = self._citit
		st, se_citeste = L.cereStare(din_nou=not self._citit)
		if st is not None and st != self._stare:
			self._stare = st
			schimbat = True
		if schimbat:
			self._arata()
		if se_citeste or not self._citit:
			self._ceas.start(PAS_MS, True)

	def _arata(self):
		if not self._citit:
			sus = {"stare": L.STARE_CITESTE}
		elif self._lista is None:
			sus = {"stare": self._eroare}
		else:
			sus = self._stare
		text, detaliu = L.texteSus(self._lista if self._citit else None, sus)
		self["text"].setText(text)
		self["detaliu"].setText(detaliu)
		ales = None
		index = self["list"].getSelectionIndex() if self._randuri else 0
		if 0 <= index < len(self._randuri):
			ales = self._randuri[index]["id"]
		noi = (self._stare or {}).get("pachete_noi") or []
		self._randuri = L.randuri(self._lista, noi)
		if self._randuri:
			self["list"].setList([r["scurt"] for r in self._randuri])
			self["ajutor"].setText(_("OK: textul licenței    Stânga/Dreapta: pagina    EXIT: închide"))
		elif self._citit:
			# lista lipsa sau stricata: un rand care spune unde sunt licentele, in locul listei goale
			self["list"].setList([L.randFaraLista()])
			self["ajutor"].setText(_("EXIT: închide"))
		else:
			self["list"].setList([])
			self["ajutor"].setText(_("EXIT: închide"))
		if not self._mutat:
			self["list"].moveToIndex(0)
		else:
			for i, r in enumerate(self._randuri):
				if ales is not None and r["id"] == ales:
					self["list"].moveToIndex(i)
					break
		self._randAles()

	def _randAles(self):
		index = self["list"].getSelectionIndex()
		if 0 <= index < len(self._randuri):
			self["rand"].setText(self._randuri[index]["detaliu"])
		else:
			self["rand"].setText("")

	def _sus(self):
		self._mutat = True
		self["list"].up()

	def _jos(self):
		self._mutat = True
		self["list"].down()

	def _paginaSus(self):
		self._mutat = True
		self["list"].pageUp()

	def _paginaJos(self):
		self._mutat = True
		self["list"].pageDown()

	def ok(self):
		index = self["list"].getSelectionIndex()
		if 0 <= index < len(self._randuri):
			self.session.open(HdsLicenteText, self._randuri[index])

	def _laInchidere(self):
		self._ceas.stop()


class HdsLicenteText(Screen):
	"""Textul licentei unui rand: fiecare fisier de licenta e un text (un text lung, mai multe parti). Numai textul
	aratat e citit din imagine. Stanga/Dreapta trec la partea sau la textul de alaturi, Sus/Jos deruleaza, OK sau EXIT
	se intoarce la lista. Un rand fara texte arata explicatia lui (ce e, fisierul, pachetul, licenta)."""

	def __init__(self, session, rand):
		marime = getDesktop(0).size()
		self.skin = skinRezervaText(marime.width(), marime.height())
		Screen.__init__(self, session)
		self._rand = rand
		titlu = ("%s %s" % (rand.get("nume") or "", rand.get("versiune") or "")).strip()
		self.setTitle(titlu)
		self._texte = L.textePentru(rand)
		self._k = 0
		self._bucati = None
		self._j = 0
		self["titlu"] = StaticText(titlu)
		self["parte"] = StaticText("")
		self["text"] = ScrollLabel("")
		self["ajutor"] = StaticText("")
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.close,
			"cancel": self.close,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
			"left": self._inapoi,
			"right": self._inainte,
			"upRepeated": self["text"].pageUp,
			"downRepeated": self["text"].pageDown,
			"leftRepeated": self._inapoi,
			"rightRepeated": self._inainte,
			"upUp": _nimic,
			"downUp": _nimic,
			"leftUp": _nimic,
			"rightUp": _nimic,
		}, -1)
		self.onLayoutFinish.append(self._arata)

	def _citesteTextul(self, k, ultima=False):
		"""Citeste textul k (numai pe el) si alege prima parte, sau ultima cand se vine inapoi."""
		self._k = k
		self._bucati = L.partiText(self._texte[k][1])
		self._j = len(self._bucati) - 1 if ultima else 0

	def _mai_multe(self):
		return len(self._texte) > 1 or len(self._bucati or []) > 1

	def _arata(self):
		if not self._texte:
			self["parte"].setText("")
			self["text"].setText(L.explicatieFaraText(self._rand))
			self["ajutor"].setText(_("OK sau EXIT: înapoi"))
			return
		if self._bucati is None:
			self._citesteTextul(self._k)
		nume = self._texte[self._k][0]
		self["parte"].setText(L.linieParte(nume, self._k, len(self._texte), self._j, len(self._bucati)))
		self["text"].setText(self._bucati[self._j])
		if self._mai_multe():
			self["ajutor"].setText(_("Sus/Jos: derulare    Stânga/Dreapta: alt text    OK sau EXIT: înapoi"))
		else:
			self["ajutor"].setText(_("Sus/Jos: derulare    OK sau EXIT: înapoi"))

	def _inapoi(self):
		if not self._texte or not self._mai_multe():
			return
		if self._j > 0:
			self._j -= 1
		else:
			self._citesteTextul((self._k - 1) % len(self._texte), ultima=True)
		self._arata()

	def _inainte(self):
		if not self._texte or not self._mai_multe():
			return
		if self._j + 1 < len(self._bucati):
			self._j += 1
		else:
			self._citesteTextul((self._k + 1) % len(self._texte))
		self._arata()

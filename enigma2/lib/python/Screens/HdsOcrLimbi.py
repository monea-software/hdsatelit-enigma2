# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsOcrLimbi.py: ecranul „Limbile recunoașterii textului” (din „Aspectul subtitrărilor”, randul „Limbile
# recunoașterii”, cu OCR ales) si fereastra de intrebare a modelelor OCR.
#
# Lista are toate limbile pentru care receptorul poate citi ca text subtitrarile DVB: intai cele din imagine, apoi cele
# descarcate (sau care se descarca), apoi cele care se pot descarca, fiecare grupa dupa nume. Pe fiecare rand: numele
# limbii, marimea modelului si starea in cuvinte („în imagine”, „descărcat, pe stick”, „se descarcă, 45%”,
# „de descărcat”). Sub lista, randul ales explicat (unde merge descarcarea si cat loc e acolo). Numai sagetile si OK:
#   - OK pe o limba de descarcat: descarcarea porneste (pe stick sau disc; fara ele, intrebarea pentru memoria interna,
#     cu locul liber aratat);
#   - OK pe o limba care se descarca: intrebarea daca se opreste (cursorul pe „Nu”);
#   - OK pe o limba descarcata: intrebarea daca se sterge (cursorul pe „Nu”);
#   - OK pe o limba al carei stick lipseste: descarcarea din nou sau scoaterea din lista;
#   - pe o limba din imagine OK nu face nimic (randul de jos spune ca merge fara descarcare);
#   - cand omul a spus „Nu mai întreba” pentru unele limbi, primul rand le arata, iar OK pe el il face sa fie intrebat
#     din nou.
# Descarcarea merge mai departe si cu ecranul inchis. O limba care se descarca ramane in locul ei din lista, cu starea
# „se descarcă, 45%”; cand trece in alta grupa (descarcata), cursorul ramane in locul lui, pe randul de langa, nu sare
# dupa limba.
#
# Datele si textele sunt in Components/HdsOcrModele.py (aceleasi in pagina web /ocr-limbi). Starea stickurilor se
# citeste pe un fir; ecranul o culege dintr-un eTimer (PAS_MS). Randurile se socotesc din nou numai cand s-a schimbat
# starea citita, generatia modelelor sau o lucrare (masurat pe x86: 0,6 ms pentru 55 de randuri), iar lista se
# deseneaza din nou numai cand difera ceva pe ea. Descarcarea pornita de propunere (descarca=True) asteapta ca ecranul
# sa fie dialogul curent: intrebarea memoriei interne se deschide numai dintr-un ecran pornit (Session.open).
#
# HdsOcrIntrebare: textul intrebarii si alegerile ei (lista), pentru propunerea de descarcare de la alegerea unei piste
# DVB (HdsOcrModele.propune, prin Tools.Notifications) si pentru intrebarile acestui ecran. OK alege, EXIT = nu.
#
# Skinul: facut la deschidere dupa marimea ecranului, numai cu fontul „Regular” si culori scrise direct; un skin care
# are blocurile <screen name="HdsOcrLimbi"> si <screen name="HdsOcrIntrebare"> le poate inlocui.

from enigma import eTimer, getDesktop

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText

from Components import HdsOcrModele as OM

PAS_MS = 500
RANDURI_LISTA = 10

# randul „Întreabă din nou pentru: ...” (primul din lista, numai cand exista limbi fara intrebare)
S_INTREABA = "intreaba"

# textul de sus are trei randuri (in franceza si rusa fraza despre memoria interna le ia pe toate)
ASEZARE = {
	"px": 120, "py": 48, "pl": 1680, "ph": 984, "linie": 2,
	"mx": 40, "cl": 1600,
	"ty": 24, "th": 60, "tf": 42,
	"xy": 88, "xh": 126, "xf": 30,
	"ly": 222, "lh": 480, "li": 48, "lf": 32,
	"ry": 714, "rh": 124, "rf": 28,
	"my": 842, "mh": 80, "mf": 28,
	"ay": 932, "ah": 36, "af": 24,
}

ASEZARE_INTREBARE = {
	"pl": 1280, "ph": 560, "linie": 2,
	"mx": 48, "cl": 1184,
	"ty": 24, "th": 56, "tf": 38,
	"xy": 96, "xh": 228, "xf": 32,
	"ly": 336, "lh": 168, "li": 56, "lf": 32,
	"ay": 512, "ah": 36, "af": 24,
}


def _scalat(asezare, latime, inaltime):
	f = min(inaltime / 1080.0, (latime - 40) / float(asezare["pl"]))
	return dict((k, max(1, int(round(v * f)))) for k, v in asezare.items())


def skinLimbi(latime, inaltime):
	v = _scalat(ASEZARE, latime, inaltime)
	v["lh"] = v["li"] * RANDURI_LISTA
	return """
	<screen name="HdsOcrLimbi" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Limbile recunoașterii textului">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget source="text" render="Label" position="%(mx)d,%(xy)d" size="%(cl)d,%(xh)d" font="Regular;%(xf)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="list" position="%(mx)d,%(ly)d" size="%(cl)d,%(lh)d" itemHeight="%(li)d" font="Regular;%(lf)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<widget source="rand" render="Label" position="%(mx)d,%(ry)d" size="%(cl)d,%(rh)d" font="Regular;%(rf)d" valign="top" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" valign="top" foregroundColor="#00f5c95c" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="ajutor" render="Label" position="%(mx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" valign="center" foregroundColor="#00a0a8b8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
	</screen>""" % v


def skinIntrebare(latime, inaltime):
	v = _scalat(ASEZARE_INTREBARE, latime, inaltime)
	return """
	<screen name="HdsOcrIntrebare" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Recunoașterea textului">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
		<widget source="text" render="Label" position="%(mx)d,%(xy)d" size="%(cl)d,%(xh)d" font="Regular;%(xf)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="list" position="%(mx)d,%(ly)d" size="%(cl)d,%(lh)d" itemHeight="%(li)d" font="Regular;%(lf)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" zPosition="2" />
		<widget source="ajutor" render="Label" position="%(mx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" valign="center" foregroundColor="#00a0a8b8" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="1" />
	</screen>""" % v


def _nimic():
	pass


def _actiuniDirectie(ecran):
	return {
		"up": ecran._sus, "down": ecran._jos, "left": ecran._paginaSus, "right": ecran._paginaJos,
		"upRepeated": ecran._sus, "downRepeated": ecran._jos, "leftRepeated": ecran._paginaSus,
		"rightRepeated": ecran._paginaJos,
		# ridicarea tastei: legata, ca jurnalul sa nu scrie „unknown action”
		"upUp": _nimic, "downUp": _nimic, "leftUp": _nimic, "rightUp": _nimic,
	}


def textRand(r):
	"""randul listei: „Slovakian  ·  4,4 MB  ·  de descărcat” (numele tradus)"""
	return u"  ·  ".join(x for x in (r["nume"], r["marime_text"], r["stare_text"]) if x)


def _grupa(r):
	return -1 if r["stare"] == S_INTREABA else OM.GRUPA.get(r["stare"], 3)


class HdsOcrIntrebare(Screen):
	"""O intrebare cu alegerile ei: (text, valoare). OK intoarce valoarea aleasa, EXIT intoarce None. `ales` = randul
	pe care sta cursorul la deschidere (la stergere si oprire, „Nu”)."""

	def __init__(self, session, text, alegeri, titlu=None, ales=0):
		marime = getDesktop(0).size()
		self.skin = skinIntrebare(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = titlu or _("Recunoașterea textului")
		self.setTitle(titlu)
		self.alegeri = list(alegeri)
		self._ales = ales if 0 <= ales < len(self.alegeri) else 0
		self["titlu"] = StaticText(titlu)
		self["text"] = StaticText(text)
		self["list"] = MenuList([a[0] for a in self.alegeri])
		self["ajutor"] = StaticText(_("Sus/Jos: alegi    OK: confirmi    EXIT: nu"))
		actiuni = _actiuniDirectie(self)
		actiuni.update({"ok": self.ok, "cancel": self.nu})
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], actiuni, -1)
		if self._ales:
			self.onLayoutFinish.append(self._alegeLaInceput)

	def _alegeLaInceput(self):
		self["list"].moveToIndex(self._ales)

	def _sus(self):
		self["list"].up()

	def _jos(self):
		self["list"].down()

	def _paginaSus(self):
		self["list"].pageUp()

	def _paginaJos(self):
		self["list"].pageDown()

	def ok(self):
		i = self["list"].getSelectionIndex()
		self.close(self.alegeri[i][1] if 0 <= i < len(self.alegeri) else None)

	def nu(self):
		self.close(None)


class HdsOcrLimbi(Screen):
	def __init__(self, session, alege=None, descarca=False, depozit=None):
		marime = getDesktop(0).size()
		self.skin = skinLimbi(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = _("Limbile recunoașterii textului")
		self.setTitle(titlu)
		self.dep = depozit or OM.depozit()
		self._randuri = []
		self._semn = None
		self._cheie = None
		# modelul pe care sta cursorul la deschidere si daca descarcarea lui porneste singura (propunerea de la pista)
		self._alege = alege
		self._deFacut = alege if descarca else None
		# modelul ultimei lucrari pornite de aici: cand se termina, randul galben spune cum s-a terminat
		self._urmarit = None
		self["titlu"] = StaticText(titlu)
		self["text"] = StaticText(_("Se caută stickurile și discurile..."))
		self["list"] = MenuList([])
		self["rand"] = StaticText(u"")
		self["mesaj"] = StaticText(u"")
		self["ajutor"] = StaticText(_("OK: descarci, oprești sau ștergi modelul    EXIT: închide"))
		actiuni = _actiuniDirectie(self)
		actiuni.update({"ok": self.ok, "cancel": self.close})
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], actiuni, -1)
		self["list"].onSelectionChanged.append(self._randAles)
		self._ceas = eTimer()
		self._ceas.callback.append(self._culege)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------------ starea
	def _porneste(self):
		self.dep.cereStare(din_nou=True)
		self._culege()

	def _pornit(self):
		"""ecranul e dialogul curent (Session.open a trecut de execBegin): de aici se pot deschide alte ferestre. La
		onLayoutFinish nu e inca (session.open ar arunca RuntimeError)."""
		return getattr(self, "execing", True)

	def _culege(self):
		inst, se_citeste = self.dep.cereStare()
		fara = OM.faraIntrebare()
		cheie = (inst is not None and inst.get("cand"), self.dep.generatie(), repr(sorted(self.dep.lucrari().items())),
			tuple(fara))
		if cheie != self._cheie:
			self._cheie = cheie
			randuri = self.dep.randuri(inst)
			if fara:
				randuri.insert(0, {"model": u"", "nume": OM.textRandFaraIntrebare(fara), "marime_text": u"",
					"stare_text": u"", "stare": S_INTREABA, "descarcabil": False, "mesaj": u"",
					"detaliu": _("Pentru limbile acestea ai ales „Nu mai întreba pentru limba asta”. OK: te întreb din "
						"nou când apare o subtitrare în ele.")})
			semn = (inst is not None and inst.get("cand"), tuple((r["model"], r["nume"], r["stare_text"], r["detaliu"])
				for r in randuri))
			if semn != self._semn:
				self._semn = semn
				self._arata(inst, randuri)
		if self._deFacut and inst is not None and self._pornit():
			model, self._deFacut = self._deFacut, None
			self._alege = model                  # descarcarea din propunere: cursorul ramane pe limba ei
			self._descarca(model)
		if self._urmarit:
			l = self.dep.lucrari().get(self._urmarit)
			if l and l["stare"] in ("gata", "eroare", "oprita"):
				self._urmarit = None
				self._mesaj(l["mesaj"])
		self._ceas.start(PAS_MS, True)

	def _textSus(self, inst):
		sus = _("Limbile pentru care receptorul citește ca text subtitrările DVB: %s.") % self.dep.textScurt()
		p = self.dep.plan(0, inst) if inst is not None else None
		return sus + u" " + OM.textLocSus(p)

	def _arata(self, inst, randuri):
		vechi = self._randuri
		i = self["list"].getSelectionIndex() if vechi else -1
		ales = vechi[i] if 0 <= i < len(vechi) else None
		tinta = self._alege
		self._alege = None
		if tinta is None and ales is not None:
			tinta = ales["model"]
			nou = [r for r in randuri if r["model"] == tinta]
			if not nou or _grupa(nou[0]) != _grupa(ales):
				# randul a trecut in alta grupa (sau a disparut): cursorul ramane pe locul lui, pe randul vecin
				vecini = vechi[i + 1:] + vechi[:i][::-1]
				modele = set(r["model"] for r in randuri)
				tinta = next((r["model"] for r in vecini if r["model"] in modele and r["model"] != ales["model"]), None)
		self._randuri = randuri
		self["text"].setText(self._textSus(inst))
		self["list"].setList([textRand(r) for r in randuri])
		for j, r in enumerate(randuri):
			if r["model"] == tinta:
				self["list"].moveToIndex(j)
				break
		self._randAles()

	def _randCurent(self):
		i = self["list"].getSelectionIndex() if self._randuri else -1
		return self._randuri[i] if 0 <= i < len(self._randuri) else None

	def _randAles(self):
		r = self._randCurent()
		d = r["detaliu"] if r else u""
		m = r.get("mesaj") if r else u""
		if m and r["stare"] == OM.S_EROARE and self["mesaj"].getText() == m and d.startswith(m + u" "):
			d = d[len(m) + 1:]                 # eroarea e deja in randul galben: o singura data pe ecran
		self["rand"].setText(d)

	# ------------------------------------------------------------------ tastele
	def _sus(self):
		self["list"].up()

	def _jos(self):
		self["list"].down()

	def _paginaSus(self):
		self["list"].pageUp()

	def _paginaJos(self):
		self["list"].pageDown()

	def _mesaj(self, text):
		self["mesaj"].setText(text or u"")
		self._randAles()

	def ok(self):
		r = self._randCurent()
		if r is None or r["stare"] == OM.S_IMAGINE or r["stare"] == OM.S_STERGE:
			return
		m = r["model"]
		if r["stare"] == S_INTREABA:
			self._rezultat(OM.intreabaDinNou())
			return
		if r["stare"] in (OM.S_MERGE, OM.S_ASTEAPTA):
			self.session.openWithCallback(lambda v=None: v == "da" and self._rezultat(self.dep.opreste(m), m), HdsOcrIntrebare,
				_("%s: oprești descărcarea modelului?") % r["nume"], [(_("Da, oprește descărcarea"), "da"),
				(_("Nu, las-o să meargă"), "nu")], ales=1)
			return
		if r["stare"] == OM.S_DESCARCAT:
			self.session.openWithCallback(lambda v=None: v == "da" and self._rezultat(self.dep.sterge(m), m), HdsOcrIntrebare,
				_("%s: ștergi modelul (%s)? Subtitrările în limba asta rămân imagine până îl descarci din nou.")
				% (r["nume"], r["marime_text"]), [(_("Da, șterge modelul"), "da"), (_("Nu"), "nu")], ales=1)
			return
		if r["stare"] == OM.S_LIPSESTE:
			self.session.openWithCallback(lambda v=None: self._laLipsa(v, m), HdsOcrIntrebare,
				_("%s: stickul sau discul cu modelul nu e pus acum. Îl descarci din nou, sau îl scoți din listă?")
				% r["nume"], [(_("Descarcă-l din nou"), "descarca"), (_("Scoate-l din listă"), "scoate"),
				(_("Nu acum"), "nu")], ales=2)
			return
		if r["descarcabil"]:
			self._descarca(m)

	def _laLipsa(self, v, model):
		if v == "descarca":
			self._descarca(model)
		elif v == "scoate":
			self._rezultat(self.dep.sterge(model))

	def _descarca(self, model, intern=False):
		rez = self.dep.descarca(model, intern=intern)
		if rez.get("cere_intern"):
			self.session.openWithCallback(lambda v=None: v == "da" and self._descarca(model, True), HdsOcrIntrebare,
				rez["intrebare"], [(_("Da, pune-l în memoria internă"), "da"), (_("Nu"), "nu")])
			return
		if rez.get("asteapta"):
			self._deFacut = model
		self._rezultat(rez, model)

	def _rezultat(self, rez, model=None):
		self._mesaj(rez.get("message"))
		if rez.get("result") and model:
			self._urmarit = model
		self._semn = self._cheie = None
		self._culege()

	def _laInchidere(self):
		self._ceas.stop()

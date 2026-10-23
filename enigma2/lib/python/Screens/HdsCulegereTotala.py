# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCulegereTotala.py: ecranele „Scanare detaliată” (in cod: culegerea canal cu canal). Meniu > Scanare.
#
# HdsCulegereTotala      alegerile (satelitii, toate canalele sau numai cele libere, numai cele neculese sau toate din
#                        nou), ce face si cat dureaza (planul si estimarea, refacute la 300 ms dupa ultima schimbare),
#                        reluarea unei treceri oprite; Verde porneste (sau continua), Galben o ia de la capat.
# HdsCulegereTotalaMers  progresul, jos pe ecran, peste imagine: canalul, pozitia, rotirea antenei, cat a ramas si
#                        numaratorile; orice tasta opreste (ascultatorul de taste al trecerii), la sfarsit rezultatul.
# Toata logica (planul, judecata, oprirea, textele, starea) e in Components/HdsCulegereTotala.py; aceeasi pereche in
# interfata web: /scanare-detaliata si adresa veche /culegere-canale (HdsWebControl/culegere_canale_web.py), care
# porneste trecerea tot pe televizor, prin porneste_pe_televizor de mai jos.

import time

from enigma import eTimer, getDesktop

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.config import ConfigSelection, getConfigListEntry
from Components import HdsCulegereTotala as C

TOTI = "toti"
TOATE = "toate"
FTA = "fta"
NECUNOSCUTE = "necunoscute"
DIN_NOU = "din_nou"
# Tasta care inchide mesajul de la sfarsitul trecerii (OK sau EXIT) ajunge, in aceeasi apasare, si la ecranul de alegere
# care tocmai s-a intors: OK ar porni din nou scanarea, EXIT ar inchide si ecranul. Atat timp dupa intoarcere, OK, Verde,
# Galben, EXIT si Rosu nu fac nimic.
PAUZA_INTOARCERE_S = 0.8

_ecran = {"mers": None}


def _factor():
	try:
		return getDesktop(0).size().width() / 1920.0
	except Exception:
		return 1.0


def porneste_pe_televizor(session, optiuni, de_la_capat=False):
	"""Din web: ecranul de progres pe televizor, cu aceleasi alegeri. -> None sau textul pentru om (tradus)."""
	if session is None:
		return _("Receptorul nu e gata.")
	motiv = C.motiv_refuz(C.Receptor(session.nav))
	if motiv:
		return _(motiv)
	session.open(HdsCulegereTotalaMers, optiuni, de_la_capat)
	return None


def opreste_de_oriunde():
	"""Din web: oprirea trecerii in curs (canalul de dinainte pus inapoi)."""
	return C.opreste(C.OPRIT_CERUT)


class HdsCulegereTotala(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsCulegereTotala" resolution="1920,1080" position="72,40" size="1240,1000" title="Scanare detaliată" backgroundColor="#0D10162A" flags="wfNoBorder">
		<panel name="HdsCadru1240" />
		<widget name="config" position="32,104" size="1176,180" itemHeight="60" font="HdsRegular;32" secondfont="HdsBold;30" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" transparent="1" scrollbarMode="showOnDemand" enableWrapAround="1" zPosition="2" />
		<eLabel position="32,300" size="1176,1" backgroundColor="#D9FFFFFF" zPosition="1" />
		<widget source="plan" render="Label" position="32,316" size="1176,44" font="HdsBold;30" foregroundColor="#00F5B83D" backgroundColor="#0D10162A" transparent="1" valign="top" noWrap="1" zPosition="2" />
		<widget source="descriere" render="Label" position="32,368" size="1176,300" font="HdsRegular;28" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" valign="top" zPosition="2" />
		<widget source="reluare" render="Label" position="32,684" size="1176,80" font="HdsRegular;28" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="top" zPosition="2" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_(C.TITLU))
		self.receptor = C.Receptor(session.nav)
		self.info = None
		self["key_red"] = StaticText(_("Închide"))
		self["key_green"] = StaticText(_(C.T_PORNESTE))
		self["key_yellow"] = StaticText("")
		# panoul HdsCadru1240 arata o tasta StaticText (cu bara ei colorata) numai pe ecranele cu ScreenPath, si numai cand
		# textul ei nu e gol (Galben apare numai la reluare)
		self["ScreenPath"] = StaticText("")
		self["plan"] = StaticText(_("Se citește lista de canale…"))
		self["reluare"] = StaticText("")
		self.descriere = _(C.DESCRIERE)
		self["descriere"] = StaticText(self.descriere)
		servicii, _semn = C.servicii_curente()
		vechi = C.citeste_stare() or {}
		opt = vechi.get("optiuni") if isinstance(vechi.get("optiuni"), dict) else C.optiuni_implicite()
		alegeri = [(TOTI if p is None else str(p), t) for p, t in C.alegeri_pozitii(servicii)]
		poz = str(opt.get("pozitie")) if opt.get("pozitie") is not None else TOTI
		if poz not in [a[0] for a in alegeri]:
			poz = TOTI
		self.sateliti = ConfigSelection(choices=alegeri, default=poz)
		self.canale = ConfigSelection(choices=[(TOATE, _(C.T_TOATE)), (FTA, _(C.T_NUMAI_FTA))],
			default=FTA if opt.get("fta") else TOATE)
		self.care = ConfigSelection(choices=[(NECUNOSCUTE, _(C.T_NECUNOSCUTE)), (DIN_NOU, _(C.T_DIN_NOU))],
			default=NECUNOSCUTE if opt.get("necunoscute", True) else DIN_NOU)
		self.list = [getConfigListEntry(_(C.T_SATELITI), self.sateliti), getConfigListEntry(_(C.T_CANALE), self.canale),
			getConfigListEntry(_(C.T_CARE), self.care)]
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keyPorneste,
			"green": self.keyPorneste,
			"yellow": self.keyDeLaCapat,
			"cancel": self.keyInchide,
			"red": self.keyInchide,
		}, -2)
		self.intors = 0.0
		self.ceasPlan = eTimer()
		self.ceasPlan.callback.append(self.refaPlanul)
		self.onClose.append(self.ceasPlan.stop)
		self.onLayoutFinish.append(self._laLayout)

	def _laLayout(self):
		self.ceasPlan.start(50, True)

	def optiuni(self):
		v = self.sateliti.value
		return C.optiuni_din(None if v == TOTI else v, self.canale.value == FTA, self.care.value == NECUNOSCUTE)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.ceasPlan.start(300, True)

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.ceasPlan.start(300, True)

	def refaPlanul(self):
		try:
			self.info = C.plan_receptor(self.optiuni(), receptor=self.receptor)
		except Exception as e:
			print("[HdsCulegereTotala] planul: %r" % (e,))
			self.info = None
			self["plan"].setText(_(C.T_FARA_LAMEDB))
			return
		self["plan"].setText(self.info["text"])
		self["reluare"].setText(self.info["text_reluare"])
		self["key_green"].setText(_(C.T_CONTINUA) if self.info["relua"] else _(C.T_PORNESTE))
		self["key_yellow"].setText(_(C.T_DE_LA_CAPAT) if self.info["relua"] else "")
		self._textMarit()

	def _eticheta(self, nume):
		sursa = self.get(nume)
		for r in getattr(self, "renderer", ()):
			if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
				return r.instance
		return None

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): planul (un rand), descrierea si randul
		reluarii se pun unul sub altul, fiecare cat ii cere textul, pana deasupra tastelor (de la 120 % se pierdea ultimul
		rand al descrierii, desi dedesubt e loc liber, iar planului i se taiau cozile literelor). La 100 % nu se schimba
		nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			if getattr(self, "_asezare", None) is None:
				self._asezare = MT.Asezare(self)
			plan, desc, rel = self._eticheta("plan"), self._eticheta("descriere"), self._eticheta("reluare")
			if None in (plan, desc, rel):
				return
			MT.potrivesteStiva(self._asezare, [(plan, lambda: MT.marimeFont(plan) * 140 // 100),
				(desc, lambda: MT.inaltimeText(desc)), (rel, lambda: MT.inaltimeText(rel))], 920, (desc, rel))
		except Exception as e:
			print("[HdsCulegereTotala] textul marit: %s" % e)

	def abiaIntors(self):
		"""Adevarat in PAUZA_INTOARCERE_S dupa intoarcerea din trecere (tasta care a inchis mesajul de sfarsit)."""
		return time.time() - self.intors < PAUZA_INTOARCERE_S

	def keyPorneste(self):
		if self.abiaIntors():
			return
		self._porneste(False)

	def keyDeLaCapat(self):
		if self.abiaIntors():
			return
		if self.info is not None and self.info["relua"]:
			self._porneste(True)

	def keyInchide(self):
		if self.abiaIntors():
			return
		self.close()

	def _porneste(self, de_la_capat):
		if self.info is None or not self.info["rest"]:
			return
		motiv = C.motiv_refuz(self.receptor)
		if motiv:
			self.session.open(MessageBox, _(motiv), MessageBox.TYPE_INFO, timeout=10)
			return
		self.session.openWithCallback(self._dupa, HdsCulegereTotalaMers, self.optiuni(), de_la_capat)

	def _dupa(self, *rezultat):
		self.intors = time.time()
		self.ceasPlan.start(100, True)


class HdsCulegereTotalaMers(Screen):
	"""Progresul trecerii, jos pe ecran, peste imagine. Skinul HDSatelit nu are ecranul, deci se foloseste cel de aici."""
	skin = """
	<screen name="HdsCulegereTotalaMers" resolution="1920,1080" position="center,center" size="1240,190" title="Scanare detaliată" flags="wfNoBorder" backgroundColor="#1010162A">
		<widget name="titlu" position="24,12" size="1192,44" font="HdsBold;32" foregroundColor="#00F2F4F8" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="stare" position="24,60" size="1192,40" font="HdsBold;28" foregroundColor="#00F5B83D" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="detalii" position="24,104" size="1192,36" font="HdsRegular;26" foregroundColor="#00C9D2E3" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="indiciu" position="24,146" size="1192,32" font="HdsCond;24" foregroundColor="#00AEB9CC" backgroundColor="#1010162A" transparent="1" valign="center" noWrap="1" />
	</screen>"""

	def __init__(self, session, optiuni, de_la_capat=False):
		Screen.__init__(self, session)
		self.setTitle(_(C.TITLU))
		self.optiuni = optiuni
		self.de_la_capat = de_la_capat
		self.trecere = None
		self["titlu"] = Label(_(C.TITLU))
		self["stare"] = Label(_("Se pregătește lista…"))
		self["detalii"] = Label("")
		self["indiciu"] = Label(_(C.T_INDICIU))
		self["actiuni"] = ActionMap(["OkCancelActions"], {"cancel": self.keyOpreste, "ok": self.keyOpreste}, -1)
		self.ceasPornire = eTimer()
		self.ceasPornire.callback.append(self._porneste)
		self.onLayoutFinish.append(self._laLayout)
		self.onClose.append(self._laInchidere)
		_ecran["mers"] = self

	def _laLayout(self):
		try:
			from enigma import ePoint
			d = getDesktop(0).size()
			s = self.instance.size()
			self.instance.move(ePoint((d.width() - s.width()) // 2, d.height() - s.height() - int(60 * _factor())))
		except Exception:
			pass
		# pornirea dupa ce ecranul se vede: planul (lamedb, baza) ia o clipa
		self.ceasPornire.start(200, True)

	def _porneste(self):
		self.trecere, eroare = C.porneste(self.session.nav, self.optiuni, self.de_la_capat, la_pas=self._pas,
			la_sfarsit=self._sfarsit)
		if eroare:
			self["stare"].setText(eroare)
			self.session.openWithCallback(lambda *a: self.close(None), MessageBox, eroare, MessageBox.TYPE_INFO,
				timeout=10)

	def _pas(self, stare):
		linie, detalii = C.texte_mers(stare)
		self["stare"].setText(linie)
		self["detalii"].setText(detalii)

	def _sfarsit(self, stare):
		if stare.get("motiv") == C.OPRIT_STANDBY:
			self.close(stare)
			return
		self.session.openWithCallback(lambda *a: self.close(stare), MessageBox, stare.get("text", ""),
			MessageBox.TYPE_INFO, timeout=30)

	def keyOpreste(self):
		if self.trecere is not None:
			self.trecere.opreste(C.OPRIT_CERUT)
		else:
			self.ceasPornire.stop()
			self.close(None)

	def _laInchidere(self):
		self.ceasPornire.stop()
		if _ecran["mers"] is self:
			_ecran["mers"] = None
		if self.trecere is not None and not self.trecere.gata:
			self.trecere.opreste(C.OPRIT_CERUT)

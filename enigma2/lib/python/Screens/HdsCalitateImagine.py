# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCalitateImagine.py: ecranul „Calitatea imaginii”. Meniu > Setări > Video & Display Settings, langa setarile video.
# Logica e in Components/HdsCalitateImagine.py (aceeasi ca in pagina web /calitate-imagine).
#
# Ecranul sta in partea de jos a televizorului, ca imaginea de deasupra sa se vada cat se regleaza. Randurile:
# - „Reglajele după canal” (Da / Nu): Nu = imaginea ca din fabrica;
# - „Profilul”: care dintre cele 9 profiluri (SD, HD, 4K x SDR, HDR10, HLG) se regleaza; la deschidere cel al canalului
#   de acum, cu semnul „(acum)”;
# - reglajele profilului ales, numai cele pe care placa le foloseste pe clasa lui (pe HD si 4K mai putine);
# - „Ieșire HDR”, numai cand receptorul o are si televizorul declara HDR, cu alegerile primite de televizor.
# Stanga / dreapta pe un reglaj al profilului de acum il scrie pe loc in placa (previzualizare), fara sa-l salveze.
# Verde sau OK pastreaza; o iesire HDR noua reporneste canalul si intreaba pe televizor (fara raspuns revine). Rosu sau
# EXIT renunta si pune la loc ce era salvat. Galben: „Înapoi la implicite” (profilul ales sau toate). Albastru:
# comparatia pe jumatate de ecran pentru reglajul ales (dreapta cu el, stanga fara), oprita la iesire.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.config import config, getConfigListEntry, ConfigSelection, NoSave
from Components import HdsCalitateImagine as M

PROFIL_FARA_IMAGINE = "hd_sdr"


class HdsCalitateImagine(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsCalitateImagine" position="center,520" size="1240,520" title="Calitatea imaginii">
		<widget source="acum" render="Label" position="20,8" size="1200,30" font="Regular;22" halign="left" valign="center" foregroundColor="#00ffd24d" />
		<widget name="config" position="20,44" size="1200,240" itemHeight="40" font="Regular;24" secondfont="Regular;16" scrollbarMode="showOnDemand" />
		<widget source="descriere" render="Label" position="20,292" size="1200,84" font="Regular;21" halign="left" valign="top" />
		<widget source="nota" render="Label" position="20,380" size="1200,60" font="Regular;19" halign="left" valign="top" foregroundColor="#00a8a8a8" />
		<widget source="key_red" render="Label" position="20,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="320,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="620,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="0" />
		<widget source="key_blue" render="Label" position="920,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	# the small window in the top left corner (row "Fereastra"), for a foreign theme; the HD Satelit theme has its own
	# block HdsCalitateImagineColt in HDSatelit/skin.xml
	skinColt = """
	<screen name="HdsCalitateImagineColt" position="40,60" size="780,400" title="Calitatea imaginii">
		<widget source="acum" render="Label" position="12,6" size="756,28" font="Regular;19" halign="left" valign="center" foregroundColor="#00ffd24d" />
		<widget name="config" position="12,38" size="756,240" itemHeight="40" font="Regular;22" secondfont="Regular;22" scrollbarMode="showOnDemand" />
		<widget source="nota" render="Label" position="12,284" size="756,56" font="Regular;17" halign="left" valign="top" foregroundColor="#00a8a8a8" />
		<widget source="key_red" render="Label" position="12,354" size="180,34" zPosition="1" font="Regular;17" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="204,354" size="180,34" zPosition="1" font="Regular;17" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="396,354" size="180,34" zPosition="1" font="Regular;17" halign="center" valign="center" backgroundColor="#a08500" transparent="0" />
		<widget source="key_blue" render="Label" position="588,354" size="180,34" zPosition="1" font="Regular;17" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session, peFereastra=False):
		Screen.__init__(self, session)
		M.initConfig()
		if config.hds_calitate.fereastra.value == M.FEREASTRA_COLT:
			self.skinName = ["HdsCalitateImagineColt"]
			self.skin = self.skinColt
		self.c = M.calitate()
		self.setTitle(_("Calitatea imaginii"))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Înapoi la implicite"))
		self["key_blue"] = StaticText("")
		self["acum"] = StaticText("")
		self["descriere"] = StaticText("")
		self["nota"] = StaticText("")
		self.acum = self.c.profilAcum()
		self.profil = self.acum or PROFIL_FARA_IMAGINE
		self.alegereProfil = NoSave(ConfigSelection(default=self.profil, choices=[
			(p, M.numeProfil(p) + ((" " + _("(acum)")) if p == self.acum else "")) for p in M.PROFILURI]))
		alegeri = self.c.alegeriHdr()
		self.hdr = None
		if alegeri:
			salvat = config.hds_calitate.iesire_hdr.value
			implicit = salvat if salvat in alegeri else "none"
			self.hdr = NoSave(ConfigSelection(default=implicit, choices=[(v, M.numeIesireHdr(v)) for v in alegeri]))
		ConfigListScreen.__init__(self, [], session=session)
		try:
			self["config"].onSelectionChanged.append(self.arata)
		except AttributeError:
			pass
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keySave,
			"save": self.keySave,
			"green": self.keySave,
			"cancel": self.keyCancel,
			"red": self.keyCancel,
			"yellow": self.keyImplicite,
			"blue": self.keyComparatie,
		}, -2)
		self.onClose.append(self.c.opresteComparatia)
		self.construieste()
		if peFereastra:
			# reopened after the window moved: the cursor stays on the "Fereastra" row (once, when first shown: at
			# onLayoutFinish the list is still put back on its first row afterwards)
			self.onShown.append(self._peFereastra)

	# ---- randurile

	def construieste(self, pastreaza=None):
		randuri = [getConfigListEntry(_("Reglajele după canal"), config.hds_calitate.pornit)]
		if config.hds_calitate.pornit.value:
			randuri.append(getConfigListEntry(_("Profilul"), self.alegereProfil))
			for cheie, e in M.elementeProfil(self.profil):
				randuri.append(getConfigListEntry(_(M.REGLAJ[cheie][4]), e))
		if self.hdr is not None:
			randuri.append(getConfigListEntry(_("Ieșire HDR"), self.hdr))
		randuri.append(getConfigListEntry(_("Fereastra"), config.hds_calitate.fereastra))
		self["config"].list = randuri
		if pastreaza is not None:
			for i, r in enumerate(randuri):
				if r[1] is pastreaza:
					self["config"].setCurrentIndex(i)
					break
		self.arata()

	def _rand(self):
		try:
			return self["config"].getCurrent()
		except (AttributeError, KeyError):
			return None

	def _cheieRand(self):
		"""Cheia reglajului de pe randul ales, sau None."""
		r = self._rand()
		if r is None:
			return None
		for cheie, e in M.elementeProfil(self.profil):
			if r[1] is e:
				return cheie
		return None

	def arata(self):
		self["acum"].setText(self.c.textAcum())
		r = self._rand()
		cheie = self._cheieRand()
		el = r[1] if r is not None else None
		if el is config.hds_calitate.pornit:
			text = _("Da: receptorul pune singur profilul canalului, după rezoluție și după felul imaginii trimise la televizor. Nu: imaginea rămâne ca din fabrică.")
		elif el is self.alegereProfil:
			text = _("Alegi profilul pe care îl reglezi. SD, HD și 4K sunt rezoluția canalului; SDR, HDR10 și HLG sunt felul imaginii trimise la televizor.")
		elif cheie is not None:
			text = _(M.REGLAJ[cheie][5]) + " " + _("Din fabrică: %s.") % M.FABRICA
		elif el is config.hds_calitate.fereastra:
			text = _("Unde stă fereastra pe televizor: jos, pe toată lățimea, sau mică, sus în stânga, ca să vezi mai mult din imagine.")
		elif el is not None and el is self.hdr:
			text = _("Automat: canalele HDR ies în HDR, celelalte în SDR. Mereu HDR10 sau HLG: și meniurile și canalele SDR ies în HDR, fără clipire la schimbarea canalului. Se aplică la tasta verde, cu o întrebare pe televizor.")
		else:
			text = ""
		self["descriere"].setText(text)
		self["nota"].setText(self._nota(cheie))
		self["key_blue"].setText(_("Comparație") if self._comparatiePosibila(cheie) else "")

	def _nota(self, cheie):
		if not config.hds_calitate.pornit.value:
			return ""
		if self.acum is None:
			return _("Acum nu e nicio imagine: reglajele se văd când pornești un canal TV.")
		if self.profil != self.acum:
			return _("Profilul acesta nu e al canalului de acum: îl vezi când pornești un canal %s.") % M.numeProfil(self.profil)
		if self.c.comparatie is not None:
			return _("Comparația e pornită: în dreapta imaginea are reglajul „%s”, în stânga nu. Albastru o oprește.") % _(M.REGLAJ[self.c.comparatie][4])
		return _("Ce schimbi se vede pe loc în imaginea de deasupra.")

	def _comparatiePosibila(self, cheie):
		return cheie is not None and self.profil == self.acum and self.c.comparatieOferita(cheie)

	# ---- tastele

	def _dupaSchimbare(self):
		r = self._rand()
		if r is None:
			return
		el = r[1]
		if el is config.hds_calitate.fereastra:
			self._mutaFereastra()
			return
		if el is config.hds_calitate.pornit:
			self.c.opresteComparatia()
			self.construieste(pastreaza=el)
			self._previzualizeaza()
			return
		if el is self.alegereProfil:
			self.c.opresteComparatia()
			self.profil = el.value
			self.construieste(pastreaza=el)
			return
		if self._cheieRand() is not None:
			self._previzualizeaza()
		self.arata()

	def _mutaFereastra(self):
		"""The window place is saved at once and the screen opens again in the other layout, on top of this one (hidden);
		when it closes, this one closes too. Close-then-open in the same call would fail: Session.close ends exec at once
		and the pop comes later, so Session.open raises "modal open are allowed only from a screen which is modal!".
		Unsaved adjustments stay in memory (the new screen shows them and keeps the preview)."""
		from Components.config import configfile
		config.hds_calitate.fereastra.save()
		configfile.save()
		self.c.opresteComparatia()
		self.hide()
		self.session.openWithCallback(self._dupaMutare, HdsCalitateImagine, peFereastra=True)

	def _peFereastra(self):
		if self._peFereastra in self.onShown:
			self.onShown.remove(self._peFereastra)
		self.construieste(pastreaza=config.hds_calitate.fereastra)

	def _dupaMutare(self, *rezultat):
		self.close()

	def _previzualizeaza(self):
		if self.acum is None:
			return
		if config.hds_calitate.pornit.value:
			self.c.incearca(self.acum, M.valoriProfil(self.acum))
		else:
			self.c.incearca(self.acum, M.valoriFabrica(self.acum.split("_")[0]))

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self._dupaSchimbare()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self._dupaSchimbare()

	def keyHome(self):
		ConfigListScreen.keyHome(self)
		self._dupaSchimbare()

	def keyEnd(self):
		ConfigListScreen.keyEnd(self)
		self._dupaSchimbare()

	def keyImplicite(self):
		from Screens.ChoiceBox import ChoiceBox
		lista = [(_("Numai profilul %s") % M.numeProfil(self.profil), self.profil), (_("Toate profilurile"), None)]
		self.session.openWithCallback(self._implicite, ChoiceBox, title=_("Pui înapoi valorile din fabrică?"),
			list=lista)

	def _implicite(self, ales):
		if ales is None:
			return
		M.implicite(ales[1])
		r = self._rand()
		self.construieste(pastreaza=r[1] if r is not None else None)
		self._previzualizeaza()

	def keyComparatie(self):
		cheie = self._cheieRand()
		if self.c.comparatie is not None:
			opreste = self.c.comparatie == cheie
			self.c.opresteComparatia()
			if opreste:
				self.arata()
				return
		if self._comparatiePosibila(cheie):
			self.c.pornesteComparatia(cheie)
		self.arata()

	def keySave(self):
		self.c.opresteComparatia()
		M.salveaza()
		nou = self.hdr.value if self.hdr is not None else None
		salvat = config.hds_calitate.iesire_hdr.value
		if nou is not None and nou != salvat:
			pornit, mesaj = M.incearcaHdr(self.session, nou, laSfarsit=self._dupaHdr)
			if pornit:
				return
			self["nota"].setText(mesaj)
			return
		self.close()

	def _dupaHdr(self, pastrat, mesaj):
		if pastrat:
			self.close()
			return
		self.hdr.value = config.hds_calitate.iesire_hdr.value
		self.construieste(pastreaza=self.hdr)
		self["nota"].setText(mesaj)

	def keyCancel(self):
		M.anuleaza()
		self.close()


# ---------------------------------------------------------------- PQ2 (0.8.0): placile fara /proc/msp/pq
# Acelasi rand de meniu „Calitatea imaginii” pe placile al caror driver are /proc/stb/vmpeg/0/pep_* (Broadcom, ZGEMMA
# H8.2H Plus): un rand pentru fiecare reglaj pe care placa il are (Components/HdsReglajeImagine.py). Stanga / dreapta
# scrie pe loc in placa (imaginea de deasupra se schimba imediat), fara sa salveze. Verde sau OK pastreaza; rosu sau
# EXIT pune la loc ce era salvat; galben: valorile din fabrica (vazute pe loc, pastrate cu verde). Foloseste blocul
# HdsCalitateImagine al temei HD Satelit (aceleasi elemente).

class HdsReglajeImagine(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsReglajeImagine" position="center,520" size="1240,520" title="Calitatea imaginii">
		<widget source="acum" render="Label" position="20,8" size="1200,30" font="Regular;22" halign="left" valign="center" foregroundColor="#00ffd24d" />
		<widget name="config" position="20,44" size="1200,240" itemHeight="40" font="Regular;24" secondfont="Regular;16" scrollbarMode="showOnDemand" />
		<widget source="descriere" render="Label" position="20,292" size="1200,84" font="Regular;21" halign="left" valign="top" />
		<widget source="nota" render="Label" position="20,380" size="1200,60" font="Regular;19" halign="left" valign="top" foregroundColor="#00a8a8a8" />
		<widget source="key_red" render="Label" position="20,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="320,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="620,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="0" />
		<widget source="key_blue" render="Label" position="920,470" size="280,36" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#18188b" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components import HdsReglajeImagine as R
		self.R = R
		R.initConfig()
		self.skinName = ["HdsReglajeImagine", "HdsCalitateImagine"]
		self.setTitle(_("Calitatea imaginii"))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Înapoi la implicite"))
		self["key_blue"] = StaticText("")
		self["acum"] = StaticText("")
		self["descriere"] = StaticText("")
		self["nota"] = StaticText("")
		ConfigListScreen.__init__(self, [], session=session)
		try:
			self["config"].onSelectionChanged.append(self.arata)
		except AttributeError:
			pass
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keySave,
			"save": self.keySave,
			"green": self.keySave,
			"cancel": self.keyCancel,
			"red": self.keyCancel,
			"yellow": self.keyImplicite,
		}, -2)
		self["config"].list = [getConfigListEntry(_(R.REGLAJ[c][4]), R.element(c)) for c in R.reglaje().chei()]
		self.arata()

	def _cheie(self):
		try:
			r = self["config"].getCurrent()
		except (AttributeError, KeyError):
			return None
		if r is None:
			return None
		for c in self.R.reglaje().chei():
			if r[1] is self.R.element(c):
				return c
		return None

	def arata(self):
		cheie = self._cheie()
		r = self.R.reglaje()
		if cheie is not None:
			fabrica = self.R.textPozitie(cheie, r.pozitieFabrica(cheie))
			self["descriere"].setText(_(self.R.REGLAJ[cheie][5]) + " " + _("Din fabrică: %s.") % fabrica)
		else:
			self["descriere"].setText("")
		self["nota"].setText(r.eroare or _("Ce schimbi se vede pe loc în imaginea de deasupra."))

	def _previzualizeaza(self):
		cheie = self._cheie()
		if cheie is not None:
			self.R.incearca(cheie, int(self.R.element(cheie).value))
		self.arata()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self._previzualizeaza()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self._previzualizeaza()

	def keyHome(self):
		ConfigListScreen.keyHome(self)
		self._previzualizeaza()

	def keyEnd(self):
		ConfigListScreen.keyEnd(self)
		self._previzualizeaza()

	def keyImplicite(self):
		from Screens.MessageBox import MessageBox
		self.session.openWithCallback(self._implicite, MessageBox, _("Pui înapoi valorile din fabrică?"),
			MessageBox.TYPE_YESNO, default=False)

	def _implicite(self, da):
		if not da:
			return
		self.R.implicite(salveaza_acum=False)
		self["config"].list = self["config"].list   # the rows show the factory values again
		self.arata()

	def keySave(self):
		self.R.salveaza()
		self.close()

	def keyCancel(self):
		self.R.anuleaza()
		self.close()

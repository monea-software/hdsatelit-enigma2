# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTransmisie.py: ecranul "Transmisie in retea". Meniu > Setari > Retea & Conexiuni (menu.xml: "Network &
# Internet").
#
# Transmisiile canalelor spre browser (pagina web /tv, Components/HdsTransmisie.py): cine se uita, la ce canal, de
# cand, cat s-a trimis; ROSU opreste toate transmisiile. Setarile: transmisia permisa (implicit Da), permisa si in
# standby (implicit Nu), cel mult cate transmisii odata (1 sau 2, implicit 1), oprirea cand nu se mai uita nimeni (10
# s, 20 s, 1 minut; implicit 1 minut). Dedesubt: cate canale noi se mai pot deschide pana la repornirea receptorului
# (memoria driverului video) si ultimele transmisii incheiate, cu motivul. Aceleasi setari, aceeasi lista si acelasi
# buton in interfata web: /tv (HdsWebControl/tv_web.py).
#
# GALBEN: aparatele din casa care au adrese fixe (lista de canale si ghidul TV, HdsWebControl/aparate_web.py): numele,
# canalele, ultima folosire; alegerea unuia intreaba daca se revoca ("Nu" ales). Revocarea opreste si transmisia lui in
# curs. Aparatele se adauga din interfata web (pagina /tv), unde se dau adresele.

import time

from .Screen import Screen
from .ChoiceBox import ChoiceBox
from .MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry
from Components import HdsTransmisie as T

T.initConfig()


def textOcteti(n):
	if n >= 1024 * 1024 * 1024:
		return "%.1f GB" % (n / 1073741824.0)
	if n >= 1024 * 1024:
		return "%d MB" % (n // 1048576)
	return "%d KB" % (n // 1024)


def textDurata(s):
	s = int(max(0, s))
	if s >= 3600:
		return _("%d h %d min") % (s // 3600, (s % 3600) // 60)
	if s >= 60:
		return _("%d min") % (s // 60)
	return _("%d s") % s


def textAdresa():
	"""Adresa paginii pentru browser (http://<ip>/tv), sau un text fara adresa daca nu se stie."""
	try:
		from Plugins.Extensions.HdsWebControl.plugin import adresaWeb
		a = adresaWeb()
	except Exception:
		a = None
	if a:
		return _("Din browser: %s/tv") % a
	return _("Din browser: pagina TV în browser a interfeței web (/tv).")


def _magazinAparate():
	"""Cheile playerelor externe (HdsWebControl/acces_extern.py: nu importa nimic din enigma2)."""
	from Plugins.Extensions.HdsWebControl import acces_extern
	return acces_extern.magazin()


def textData(t):
	return time.strftime("%d.%m.%Y %H:%M", time.localtime(t)) if t else ""


def textAparat(a):
	"""Un rand din lista aparatelor: numele, canalele si ultima folosire."""
	if a.get("folosit"):
		return _("%s (canale: %s; folosit ultima dată %s)") % (a.get("nume", ""), a.get("sursa") or "?",
			textData(a["folosit"]))
	return _("%s (canale: %s; încă nefolosit)") % (a.get("nume", ""), a.get("sursa") or "?")


def textEcran(st, adresa_text, aparate=0):
	"""Textul de sub setari: transmisiile, memoria si ultimele transmisii incheiate."""
	randuri = [adresa_text]
	if aparate:
		randuri.append(_("Aparate din casă cu adrese fixe: %d. Tasta galbenă: lista și revocarea.") % aparate)
	sesiuni = st.get("sesiuni") or []
	if sesiuni:
		randuri.append(_("Transmisii acum:"))
		for s in sesiuni:
			cine = s.get("browser") or s.get("adresa") or "?"
			if s.get("adresa") and s.get("adresa") != cine:
				cine = "%s (%s)" % (cine, s["adresa"])
			fara = "" if s.get("cu_spectator") else _(", fără spectator acum")
			randuri.append(_("  %s, spre %s, de %s, %s%s") % (s.get("nume", ""), cine, textDurata(s.get("secunde", 0)),
				textOcteti(s.get("octeti", 0)), fara))
	else:
		randuri.append(_("Nicio transmisie acum."))
	m = st.get("memorie")
	if m and m.get("ramase") is not None:
		if m["ramase"] > 0:
			randuri.append(_("Porniri noi în browser care se mai pot face până la repornirea receptorului: %d.") % m["ramase"])
		else:
			randuri.append(_("Memoria driverului video e pe sfârșite: transmisiile noi pornesc după repornirea receptorului."))
	jurnal = st.get("jurnal") or []
	if jurnal:
		randuri.append(_("Ultimele transmisii:"))
		for j in jurnal[:4]:
			randuri.append("  %s  %s, %s: %s" % (time.strftime("%H:%M", time.localtime(j.get("ora", 0))), j.get("canal", ""),
				textDurata(j.get("secunde", 0)), j.get("motiv", "")))
	return "\n".join(r for r in randuri if r)


class HdsTransmisie(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsTransmisie" resolution="1920,1080" position="center,center" size="1100,660" title="Transmisie în rețea">
		<widget name="config" position="30,25" size="1040,170" scrollbarMode="showOnDemand" font="Regular;22" secondfont="Regular;16" itemHeight="40" />
		<widget source="descriere" render="Label" position="30,205" size="1040,80" font="Regular;18" halign="left" valign="top" />
		<widget source="stare" render="Label" position="30,290" size="1040,305" font="Regular;18" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,610" size="260,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,610" size="220,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="550,610" size="260,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="0" />
	</screen>
	"""

	def __init__(self, session, manager=None):
		Screen.__init__(self, session)
		self.manager = manager or T.manager()
		self.setTitle(_("Transmisie în rețea"))
		self["key_red"] = StaticText(_("Oprește transmisiile"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Aparate din casă"))
		self["descriere"] = StaticText(_("Canalele se pot vedea într-un browser din rețeaua de acasă, fără recodare: "
			"merg cele cu imagine H.264 sau MPEG-2 (și HEVC, unde browserul îl redă). Televizorul și înregistrările au "
			"prioritate: "
			"o transmisie se oprește singură când au nevoie de tunerul ei."))
		self["stare"] = StaticText("")
		self.adresa = textAdresa()
		self.list = []
		ConfigListScreen.__init__(self, self.list, session=session)
		# left / right tot aici: harta cu SetupActions are prioritate fata de cea a listei, iar o actiune lipsa din ea
		# lasa in jurnal "unknown action SetupActions/left"
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keySave,
			"green": self.keySave,
			"cancel": self.keyCancel,
			"yellow": self.aparate,
			"left": self.keyLeft,
			"right": self.keyRight,
		}, -2)
		# ROSU = "Opreste transmisiile", ca pe eticheta. In data/keymap.xml SetupActions da KEY_RED -> "cancel" (in toate
		# ecranele de setari ROSU inchide fara salvare), iar eActionMap ia legaturile dupa prioritate, apoi in ordinea
		# contextelor: in harta de mai sus ROSU ar fi "cancel" (ecranul se inchidea, transmisia mergea mai departe; proba
		# din 14.10). Harta lui ROSU are deci prioritatea inaintea ei; keymap.xml ramane neschimbat.
		self["actiuni_rosu"] = ActionMap(["ColorActions"], {
			"red": self.opresteToate,
		}, -3)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		self.onClose.append(self.ceas.stop)
		self.creeaza()
		self.actualizeaza()
		self.ceas.start(2000, False)
		getattr(self, "onLayoutFinish", []).append(self._textMarit)

	def _eticheta(self, nume):
		sursa = self.get(nume)
		for r in getattr(self, "renderer", ()):
			if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
				return r.instance
		return None

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): descrierea de sub lista creste cat ii
		cere textul, iar starea de sub ea coboara si se scurteaza (marginea ei de jos ramane deasupra tastelor); de la
		120 % se pierdea ultimul rand al descrierii. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			desc, stare = self._eticheta("descriere"), self._eticheta("stare")
			sk = a.dinSkin(stare) if stare is not None else None
			if desc is None or sk is None:
				return
			a.creste(desc, MT.inaltimeText(desc), sk[1] + sk[3], maxim=sk[3] // 2)
		except Exception as e:
			print("[%s] textul marit: %s" % (self.__class__.__name__, e))

	def creeaza(self):
		c = config.hds_transmisie
		self.list = [getConfigListEntry(_("Permite transmisia în browser"), c.permis)]
		if c.permis.value:
			self.list.extend([
				getConfigListEntry(_("Permite transmisia în standby"), c.standby),
				getConfigListEntry(_("Cel mult transmisii odată"), c.sesiuni_max),
				getConfigListEntry(_("Oprire când nu se mai uită nimeni, după"), c.asteptare),
			])
		self["config"].list = self.list
		self["config"].setList(self.list)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.creeaza()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.creeaza()

	def numarAparate(self):
		try:
			return len(_magazinAparate().aparate())
		except Exception as e:
			print("[HdsTransmisie] aparatele: %r" % (e,))
			return 0

	def actualizeaza(self):
		try:
			self["stare"].setText(textEcran(self.manager.stare(), self.adresa, self.numarAparate()))
		except Exception as e:
			print("[HdsTransmisie] starea: %r" % (e,))
		# o setare schimbata din pagina web (aceleasi elemente config) se vede si aici; randurile ascunse sau aratate
		# de "Permite" se refac numai cand se schimba
		try:
			if (len(self.list) > 1) != bool(config.hds_transmisie.permis.value):
				self.creeaza()
			else:
				for e in self.list:
					self["config"].invalidate(e)
		except Exception as e:
			print("[HdsTransmisie] lista: %r" % (e,))

	def opresteToate(self):
		n = self.manager.opresteToate(_("Transmisia a fost oprită de pe televizor."))
		if n:
			self.actualizeaza()

	def aparate(self):
		"""GALBEN: lista aparatelor din casa; unul ales se revoca dupa intrebare."""
		try:
			lista = _magazinAparate().aparate()
		except Exception as e:
			print("[HdsTransmisie] aparatele: %r" % (e,))
			lista = []
		if not lista:
			self.session.open(MessageBox, _("Niciun aparat din casă nu are adrese fixe. Le adaugi din interfața web, în pagina TV în browser."), MessageBox.TYPE_INFO)
			return
		self.session.openWithCallback(self._aparatAles, ChoiceBox, title=_("Aparate din casă"),
			list=[(textAparat(a), a) for a in lista])

	def _aparatAles(self, ales):
		if not ales:
			return
		a = ales[1]
		self.session.openWithCallback(lambda da: self._revoca(a, da), MessageBox,
			_("Revoci aparatul %s? Nu mai primește canalele și ghidul TV, iar adresele lui nu mai merg niciodată. Dacă îl vrei din nou, îl adaugi din nou.") % a.get("nume", ""),
			MessageBox.TYPE_YESNO, default=False)

	def _revoca(self, a, da):
		if not da:
			return
		motiv = _("Aparatul a fost revocat. Adresele lui nu mai merg.")
		try:
			revocat = _magazinAparate().revoca(a.get("id"))
		except Exception as e:
			print("[HdsTransmisie] revocarea: %r" % (e,))
			revocat = False
		if revocat:
			ses = self.manager.sesiunePentru("x:%s" % a.get("id"))
			if ses is not None:
				self.manager.opreste(ses.id, motiv)
			self.session.open(MessageBox, motiv, MessageBox.TYPE_INFO, timeout=5)
		self.actualizeaza()

	def _elemente(self):
		c = config.hds_transmisie
		return (c.permis, c.standby, c.sesiuni_max, c.asteptare)

	def keySave(self):
		for e in self._elemente():
			e.save()
		configfile.save()
		self.close()

	def keyCancel(self):
		for e in self._elemente():
			e.cancel()
		self.close()

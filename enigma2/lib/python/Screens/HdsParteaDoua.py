# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Ecranul si oferta dupa asistent folosesc motorul comun cu pagina web.
from Components import HdsParteaDoua as P
from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from enigma import eTimer


class HdsParteaDoua(Screen):
	skin = """<screen name="HdsParteaDoua" position="center,center" size="980,560" title="Partea a doua pe stick">
		<widget name="text" position="30,25" size="920,430" font="Regular;26" />
		<widget name="key_red" position="30,490" size="200,45" font="Regular;24" />
		<widget name="key_green" position="250,490" size="460,45" font="Regular;24" />
		<widget name="key_yellow" position="730,490" size="220,45" font="Regular;24" />
	</screen>"""

	def __init__(self, session, candidat=None, ident=None):
		Screen.__init__(self, session)
		self.setTitle(_("Partea a doua pe stick"))
		self["text"] = Label("")
		self["key_red"] = Label(_("Inapoi"))
		self["key_green"] = Label(_("Instaleaza / actualizeaza"))
		self["key_yellow"] = Label(_("Reciteste"))
		self._candidatDirect = None
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close, "red": self.close, "ok": self.porneste,
			"green": self.porneste, "yellow": self.arata}, -1)
		self.ceas = eTimer()
		# callback.append, ca in restul imaginii: pe un SF8008 0.7.2 timeout.connect a dat „'eTimer' object has no attribute
		# 'connect'” (raportul 530155, 09.11.2026)
		self.ceas.callback.append(self.arata)
		self.onClose.append(self.ceas.stop)
		self.onLayoutFinish.append(self.arata)
		if candidat is not None:
			self.onLayoutFinish.append(lambda: self._incepe(candidat, ident))
		self.ceas.start(2000)

	def arata(self):
		d = P.starePublica()
		self._candidatDirect = d.get("stick_unic")
		stare = _("Stick montat") if d.get("montat") else _("Niciun stick legat")
		if d.get("legat") and not d.get("montat"):
			stare = _(P.MESAJ_LIPSA)
		text = [stare]
		mesaj = _(d.get("mesaj") or "")
		if mesaj and mesaj != stare:
			text += ["", mesaj]
		if d.get("descris"):
			text += ["", _(P.MESAJ_LIMITA), d.get("explicatie_stick", "")]
		if d.get("descris") and not d.get("legat"):
			text += ["", _("Se folosesc %d MiB pe stick, fara stergerea fisierelor existente.") % d.get("marime_mib", 1024)]
			if not d.get("candidati"):
				text += [_("Pune un stick USB montat, cu loc liber suficient.")]
		if not d.get("descris"):
			self["text"].setText("\n".join(text))
			self["key_green"].setText("")
			return
		if self._candidatDirect:
			text += ["", d["actiune_unic"]]
		self["text"].setText("\n".join(text))
		self["key_green"].setText(_("Asteapta...") if d.get("ocupat") else
			(_("Actualizeaza partea a doua") if d.get("montat") else
				(_("Folosește stickul") if self._candidatDirect else (_("Alege stickul") if d.get("candidati") else ""))))

	def porneste(self):
		d = P.starePublica()
		if d.get("ocupat") or not d.get("descris"):
			return
		if d.get("montat"):
			return self._incepe(None)
		# O comandă văzută pentru un stick nu poate porni pe altul după recitire.
		unic = d.get("stick_unic")
		if self._candidatDirect or unic:
			if unic and self._candidatDirect and all(self._candidatDirect.get(k) == unic.get(k) for k in ("punct", "ident")):
				return self._incepe(unic["punct"], unic.get("ident"))
			return self.arata()
		c = d.get("candidati") or []
		if not c:
			return self.arata()
		self.session.openWithCallback(self._ales, ChoiceBox,
			title=_("Alege stickul pentru partea a doua"),
			list=[(_("%s (%d MiB liberi)") % (x["punct"], x["liber_mib"]), x) for x in c])

	def _ales(self, alegere):
		if alegere:
			c = alegere[1]
			self.session.openWithCallback(lambda da: self._incepe(c["punct"], c.get("ident")) if da else None,
				MessageBox, (_("Folosesc spațiu pe stickul %s pentru limbile suplimentare? Fișierele existente rămân.") %
					c["punct"]) + "\n\n" + _(P.MESAJ_STICK_NECESAR),
				type=MessageBox.TYPE_YESNO, default=False)

	def _incepe(self, punct, ident=None):
		if not P.lucrare.porneste(punct, ident=ident):
			self.session.open(MessageBox, _("Alta operatie este in lucru sau interfata trebuie repornita."),
				type=MessageBox.TYPE_INFO)
		self.arata()


_pornire = None


def pornesteParteaDoua(session):
	"""Chemata numai dupa deschiderea InfoBar, deci dupa ultimul asistent."""
	global _pornire
	if _pornire is not None:
		return
	ceas = eTimer()
	def verifica():
		if getattr(getattr(session, "current_dialog", None), "__class__", type(None)).__name__ != "InfoBar":
			ceas.start(5000, True)
			return
		d = P.oferta()
		if d.get("descris") and d.get("legat") and not d.get("montat"):
			session.open(MessageBox, _(P.MESAJ_LIPSA), type=MessageBox.TYPE_INFO)
			return
		c = d.get("candidati") or []
		if not c:
			return
		def raspuns(da):
			if not da:
				P.refuza(c)
			elif len(c) == 1:
				session.open(HdsParteaDoua, candidat=c[0]["punct"], ident=c[0].get("ident"))
			else:
				session.open(HdsParteaDoua)
		text = _("Receptorul are memorie interna putina. Folosesc %d MiB de pe stick pentru limbile suplimentare?") % d.get("marime_mib", 1024)
		da = _("Da")
		if len(c) == 1:
			da = _("Folosește stickul %s") % c[0]["punct"]
			text += "\n\n" + da
		text += "\n\n" + _(P.MESAJ_STICK_NECESAR)
		session.openWithCallback(raspuns, MessageBox, text,
			type=MessageBox.TYPE_YESNO, default=False, list=[(da, True), (_("Nu acum"), False)])
	ceas.callback.append(verifica)
	_pornire = ceas
	ceas.start(5000, True)

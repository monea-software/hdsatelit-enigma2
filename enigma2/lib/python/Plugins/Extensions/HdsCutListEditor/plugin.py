# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCutListEditor -- editor de marcaje (cut list) pentru o inregistrare aflata in redare.
# Cod 100% propriu, scris de la zero.
#
# CONTEXT (in locul lui "CutListEditor" din doc/REMOVED-FILES, scos pentru licenta CC BY-NC-SA 3.0):
# infrastructura de baza NU lipseste -- e cod
# Dreambox upstream complet, deja in acest depozit si deja in productie:
#   - lib/service/iservice.h: interfata iCueSheet (getCutList/setCutList/setCutListEnable);
#     lib/service/servicedvb.cpp o implementeaza deja complet, cu fisier ".cuts" insotitor
#     pentru fiecare inregistrare (citit doar pentru intelegere, e cod propriu deja in
#     depozit, nu cod al altei echipe).
#   - lib/python/Screens/InfoBarGenerics.py, clasa InfoBarCueSheetSupport: deja amestecata in
#     Screens/InfoBar.py -> MoviePlayer (redarea unei inregistrari), cu addMark/removeMark si
#     sarituri intre marcaje (taste deja legate, deja in productie) -- dar acea clasa stie sa
#     puna DOAR un singur tip de marcaj simplu (CUT_TYPE_MARK), nu perechi START/STOP taiere.
# Ce lipsea cu adevarat: un ECRAN dedicat care arata TOATE marcajele intr-o lista, poate
# adauga puncte START/STOP taiere (nu doar marcaj simplu) si poate sterge un marcaj ales.
# Ecranul de fata vorbeste DIRECT cu serviciul curent (session.nav.getCurrentService()),
# fara sa atinga InfoBar.py/MoviePlayer deloc -- functioneaza LANGA mecanismul existent, nu
# il inlocuieste si nu risca sa il strice.
#
# Din 0.2.6 se deschide din lista tastei albastre a playerului
# inregistrarilor (Screens/InfoBar.py, MoviePlayer.hdsEditorMarcaje), numai cand ce merge are
# marcaje; nu mai e in lista de extensii si nici in bara TV. Daca totusi nu exista o redare cu
# suport de marcaje, arata un mesaj clar, nu cade si nu ofera controale care n-ar face nimic.
#
# CORECTIE DE SENS (verificata citind eDVBServicePlay::
# cutlistToCuesheet() in servicedvb.cpp + eCueSheet::addSourceSpan()/m_source_span in dvb.cpp,
# nu presupusa): textul initial al acestui ecran descria START/STOP ca "aici incepe/se termina
# PORTIUNEA DE SARIT" -- INVERS fata de mecanismul real. Fiecare pereche START->STOP adaugata de
# `cutlistToCuesheet()` devine un `addSourceSpan(in, out)` = o portiune care CHIAR SE REDA; tot
# ce NU e acoperit de o astfel de portiune (inainte de primul START, intre un STOP si urmatorul
# START, dupa ultimul STOP) e SARIT la redare (confirmat si in dvb.cpp, functia care alege ce
# bloc se citeste: "current_offset < aligned_start" -> sare inainte la urmatoarea portiune).
# Cu textul vechi, un user care ar fi marcat START/STOP exact ca i se spunea (in jurul unei
# reclame, ca sa o sara) ar fi obtinut EXACT opusul: reclama ar fi fost REDATA, iar tot restul
# emisiunii SARIT. Text corectat mai jos ca sa descrie mecanismul real -- constantele
# CUT_TYPE_IN/CUT_TYPE_OUT raman neschimbate (sunt chiar valorile asteptate de eCueSheet).

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button

CUT_TYPE_IN = 0
CUT_TYPE_OUT = 1
CUT_TYPE_MARK = 2
CUT_TYPE_LAST = 3


def _numeTip():
	"""Legat abia la apel: `_()` (gettext) nu e neaparat gata la importul modulului."""
	return {
		CUT_TYPE_IN: _("START păstrare"),
		CUT_TYPE_OUT: _("STOP păstrare"),
		CUT_TYPE_MARK: _("marcaj"),
		CUT_TYPE_LAST: _("ultima poziție văzută"),
	}


def _formatTimp(pts):
	"""pts (ceas MPEG, 90 kHz) -> "H:MM:SS" sau "M:SS" daca sub o ora. None -> "?"."""
	if pts is None:
		return "?"
	secunde = int(pts) // 90000
	h, rest = divmod(secunde, 3600)
	m, s = divmod(rest, 60)
	if h:
		return "%d:%02d:%02d" % (h, m, s)
	return "%d:%02d" % (m, s)


class HdsCutListEditor(Screen):
	skin = """
	<screen name="HdsCutListEditor" resolution="1920,1080" position="center,center" size="1000,600" title="Editor marcaje">
		<widget name="detaliu" position="30,20" size="940,60" font="Regular;20" />
		<widget name="lista" position="30,90" size="940,400" font="Regular;22" itemHeight="40" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,520" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="260,520" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="490,520" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget name="key_blue" position="720,520" size="220,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#185090" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Editor marcaje"))
		self._service = session.nav.getCurrentService()
		self._cue = self._service.cueSheet() if self._service is not None else None
		self._seek = self._service.seek() if self._service is not None else None
		self._cut_list = []

		self["detaliu"] = Label("")
		self["lista"] = MenuList([])
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Adaugă marcaj aici"))
		self["key_yellow"] = Button(_("START/STOP păstrare aici"))
		self["key_blue"] = Button(_("Șterge selecția"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions"],
			{
				"cancel": self.close,
				"red": self.close,
				"ok": self._sariLaSelectie,
				"green": self._adaugaMarcaj,
				"yellow": self._adaugaStartStop,
				"blue": self._stergeSelectie,
				"up": self._sus,
				"down": self._jos,
			}, -2)

		if self._cue is None:
			self["detaliu"].setText(_("Acest ecran nu are marcaje: serviciul curent nu suportă tăieri (de exemplu, televiziune live)."))
			self["key_green"].setText("")
			self["key_yellow"].setText("")
			self["key_blue"].setText("")
		else:
			self.onLayoutFinish.append(self._reincarca)

	def _sus(self):
		if self._cue is not None:
			self["lista"].up()

	def _jos(self):
		if self._cue is not None:
			self["lista"].down()

	# -------------------------------------------------------------- pozitie curenta

	def _pozitiaCurenta(self):
		if self._seek is None:
			return None
		rezultat = self._seek.getPlayPosition()
		if rezultat[0]:
			return None
		return int(rezultat[1])

	# -------------------------------------------------------------- lista

	def _reincarca(self):
		try:
			self._cut_list = sorted(self._cue.getCutList() or [])
		except Exception as eroare:
			self._cut_list = []
			self["detaliu"].setText(_("Nu am putut citi marcajele: %s") % eroare)
			return
		nume_tip = _numeTip()
		if self._cut_list:
			randuri = ["%s · %s" % (_formatTimp(pts), nume_tip.get(tip, str(tip))) for (pts, tip) in self._cut_list]
			self["detaliu"].setText(_("%d marcaj(e). OK = sari acolo, Albastru = șterge selecția.") % len(self._cut_list))
		else:
			randuri = [_("Niciun marcaj încă.")]
			self["detaliu"].setText(_("Poziția curentă: %s; Verde adaugă un marcaj simplu, Galben adaugă START/STOP păstrare (ce nu e acoperit de o pereche START-STOP e SĂRIT la redare).") % _formatTimp(self._pozitiaCurenta()))
		self["lista"].setList(randuri)

	def _selectat(self):
		index = self["lista"].getSelectionIndex()
		if self._cut_list and 0 <= index < len(self._cut_list):
			return self._cut_list[index]
		return None

	# -------------------------------------------------------------- actiuni

	def _scrie(self):
		"""Trimite lista curenta la serviciu -- persista automat in fisierul .cuts (cf. servicedvb.cpp,
		cod propriu deja in depozit, doar citit pentru intelegere)."""
		self._cue.setCutList(self._cut_list)

	def _adaugaPunct(self, tip):
		pos = self._pozitiaCurenta()
		if pos is None:
			self["detaliu"].setText(_("Nu pot afla poziția curentă (serviciul nu e derulabil acum)."))
			return
		punct = (pos, tip)
		if punct not in self._cut_list:
			self._cut_list.append(punct)
			self._cut_list.sort()
			self._scrie()
		self._reincarca()

	def _adaugaMarcaj(self):
		if self._cue is not None:
			self._adaugaPunct(CUT_TYPE_MARK)

	def _adaugaStartStop(self):
		if self._cue is None:
			return
		self.session.openWithCallback(
			self._alesStartStop,
			ChoiceBox,
			title=_("Ce fel de marcaj la poziția curentă?"),
			list=[
				(_("START păstrare (de-aici se redă)"), CUT_TYPE_IN),
				(_("STOP păstrare (până aici se redă)"), CUT_TYPE_OUT),
			]
		)

	def _existaStartInainte(self, pos_nou):
		"""HDSatelit (confirmat in
		eDVBServicePlay::cutlistToCuesheet(), servicedvb.cpp): un STOP fara niciun START inainte de el
		in lista pastreaza DOAR [0, pos_stop] -- tot restul inregistrarii, dupa acel punct, e sarit la
		redare, fara nicio eroare vizibila. Verificare simpla (nu simuleaza tot automatul C++, doar
		prinde exact acest caz): exista vreun START la o pozitie mai mica decat cea noua?"""
		return any(tip == CUT_TYPE_IN and pts < pos_nou for pts, tip in self._cut_list)

	def _alesStartStop(self, ales):
		if ales is None:
			return
		tip = ales[1]
		if tip == CUT_TYPE_OUT:
			pos = self._pozitiaCurenta()
			if pos is not None and not self._existaStartInainte(pos):
				self.session.openWithCallback(
					lambda confirmare: self._adaugaPunct(tip) if confirmare else None,
					MessageBox,
					_("Nu există niciun START înainte de această poziție.\n"
						"Fără el, acest STOP va păstra doar de la începutul înregistrării până aici -- "
						"tot restul, după acest punct, va fi SĂRIT la redare.\n\n"
						"Adaugi oricum acest STOP?"),
					MessageBox.TYPE_YESNO,
					default=False,
				)
				return
		self._adaugaPunct(tip)

	def _stergeSelectie(self):
		if self._cue is None:
			return
		punct = self._selectat()
		if punct is None:
			return
		# HDSatelit: stergerea nu cerea confirmare,
		# spre deosebire de restul ecranelor noi din acest depozit (HdsCrashlogAutoSubmit etc.) --
		# adaugata acum, acelasi tipar. `punct` (nu doar indexul) e capturat aici si trimis prin
		# callback, ca sa ramana corect chiar daca selectia se schimba intre timp.
		self.session.openWithCallback(
			lambda confirmare: self._dupaConfirmareStergere(confirmare, punct),
			MessageBox,
			_("Ștergi marcajul selectat (%s)?") % _formatTimp(punct[0]),
			MessageBox.TYPE_YESNO,
			default=False,
		)

	def _dupaConfirmareStergere(self, confirmare, punct):
		if not confirmare:
			return
		if punct in self._cut_list:
			self._cut_list.remove(punct)
			self._scrie()
		self._reincarca()

	def _sariLaSelectie(self):
		if self._cue is None:
			return
		punct = self._selectat()
		if punct is None or self._seek is None:
			return
		self._seek.seekTo(punct[0])
		self._reincarca()


def deschide(session, **kwargs):
	service = session.nav.getCurrentService()
	if service is None:
		session.open(MessageBox, _("Nu rulează nicio redare acum; deschide acest ecran în timp ce te uiți la o înregistrare."), MessageBox.TYPE_INFO, timeout=6)
		return
	session.open(HdsCutListEditor)


def Plugins(**kwargs):
	# 0.2.6: editorul e al playerului inregistrarilor, nu o extensie. Se deschide din
	# lista tastei albastre a playerului (Screens/InfoBar.py, MoviePlayer), numai cand ce merge are marcaje; nu mai
	# apare in lista de extensii si nici la tasta albastra din bara TV, unde nu avea ce face.
	return []

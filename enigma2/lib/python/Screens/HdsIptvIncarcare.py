# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvIncarcare: fereastra mica de deasupra imaginii cat se incarca un canal de internet: mesajul, bara si viteza. Nemodala, sub bare si meniuri.
# Bara arata procentul cand se stie; cand nu se stie, un segment care se plimba, ca sa se vada ca receptorul lucreaza. Ce arata hotaraste
# Components/HdsIptvRedare.py, din evenimentele playerului.

from .Screen import Screen
from Components.Label import Label
from Components.ProgressBar import ProgressBar

PAS_ANIMATIE = 7


class HdsIptvIncarcare(Screen):
	skin = """
	<screen name="HdsIptvIncarcare" position="center,150" size="760,130" backgroundColor="#00141a30" flags="wfNoBorder" zPosition="1">
		<eLabel position="0,0" size="760,3" backgroundColor="#00374ea1" />
		<widget name="text" position="28,18" size="500,46" font="Regular;32" foregroundColor="#00f2f4f8" backgroundColor="#00141a30" transparent="1" valign="center" noWrap="1" />
		<widget name="mic" position="532,18" size="200,46" font="Regular;26" foregroundColor="#00aeb9cc" backgroundColor="#00141a30" transparent="1" halign="right" valign="center" noWrap="1" />
		<widget name="bara" position="28,84" size="704,14" foregroundColor="#004fd18b" backgroundColor="#002a3350" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["text"] = Label("")
		self["mic"] = Label("")
		self["bara"] = ProgressBar()
		self.vizibil = False
		self.pas = 0

	def arata(self, text, procent, mic):
		if self["text"].getText() != text:
			self["text"].setText(text)
		if self["mic"].getText() != mic:
			self["mic"].setText(mic)
		if procent is None:
			# procentul nu se stie: bara se umple si se goleste, ca sa se vada ca merge
			self.pas = (self.pas + PAS_ANIMATIE) % 100
			self["bara"].setValue(self.pas)
		else:
			self["bara"].setValue(max(0, min(100, int(procent))))
		if not self.vizibil:
			self.vizibil = True
			self.show()

	def ascunde(self):
		if self.vizibil:
			self.vizibil = False
			self.hide()

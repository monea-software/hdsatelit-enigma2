# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRaportCanal.py (ecranele): "Raporteaza canalul asta" din meniul Beta tester. Un singur pas pentru om: tastatura
# cu un rand optional (OK cu randul gol trimite la fel), apoi raportul pleaca si un mesaj scurt spune ca a intrat in
# coada. Fara tastatura (alt skin, alt mediu) raportul pleaca fara rand. Logica: Components/HdsRaportCanal.py.

from Screens.MessageBox import MessageBox

from Components import HdsRaportCanal as R


def deschide(session):
	"""Tastatura (randul omului, optional), apoi trimiterea; EXIT pe tastatura nu trimite nimic."""
	def gata(text):
		if text is None:
			return
		_ok, mesaj = R.trimite(session, text)
		session.open(MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=6)
	try:
		from Screens.VirtualKeyBoard import VirtualKeyBoard
	except ImportError:
		gata("")
		return
	session.openWithCallback(gata, VirtualKeyBoard,
		title=_("Ce nu merge la canalul ăsta? Poți lăsa gol și apăsa OK."), text="")

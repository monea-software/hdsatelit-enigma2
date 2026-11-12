# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile scrise pentru alte imagini (managerul de fisiere, la sfarsitul unei copieri; un ghid TV, cand are o versiune noua) arata un
# mesaj scurt, care pleaca singur: Toast.instance.showToast(text, tip, timeout); la fel session.showInfo/showWarning/showError (mytest.py),
# ca in OE-Alliance. Mesajul e fereastra de mesaj a imaginii, aratata PE LOC peste ecranul deschis (FastScan il da din meniul de cautare,
# PiconBrowser din ecranul lui), fara sa intre in sirul ecranelor: nu ia tastele, ecranul de dedesubt merge mai departe si se poate inchide
# oricand; pleaca singur dupa timeout. Un mesaj nou il inlocuieste pe cel de dinainte. Cand nu se poate arata asa (inainte de bara
# canalului, la pornire), merge prin coada notificarilor (Notifications.AddPopup), ca inainte.


class _Toast:
	TYPE_INFO = 0
	TYPE_WARNING = 1
	TYPE_ERROR = 2
	TYPE_SUCCESS = 3

	def __init__(self):
		self._mesaj = None  # (sesiunea, fereastra) aratata acum
		self._ceas = None

	def showToast(self, text, toastType=TYPE_INFO, timeout=5, *args, **kwargs):
		try:
			from Screens.MessageBox import MessageBox
			fel = MessageBox.TYPE_ERROR if toastType == self.TYPE_ERROR else MessageBox.TYPE_WARNING if toastType == self.TYPE_WARNING else MessageBox.TYPE_INFO
			durata = int(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else 5
			if self._arataPeLoc(str(text), fel, durata):
				return
			from Tools import Notifications
			Notifications.AddPopup(str(text), fel, durata, "HdsToast")
		except Exception as e:
			print("[Toast] %r" % (e,))

	def _arataPeLoc(self, text, fel, durata):
		"""Fereastra de mesaj instantiata (nu deschisa cu session.open: nu intra in sirul ecranelor, deci un plugin care isi
		inchide ecranul imediat dupa mesaj nu da peste alt ecran curent), aratata si stearsa de ceasul ei. -> False cand nu e
		inca o sesiune (bara canalului neconstruita)."""
		try:
			from Screens.InfoBar import InfoBar
			sesiune = getattr(InfoBar.instance, "session", None)
		except Exception:
			sesiune = None
		if sesiune is None:
			return False
		from Screens.MessageBox import MessageBox
		from enigma import eTimer
		self._ascunde()
		# timeout=-1: ceasul ferestrei ar inchide-o prin session.close (ar cere sa fie ecranul curent); aici o inchide ceasul nostru.
		# zPosition peste ecrane (temele le pun intre 0 si 10): altfel fereastra ar sta sub ecranul deschis (emulator, 12.11.2026)
		# enable_input=False: fara banda „OK Închide” (tastele merg la ecranul de dedesubt, mesajul pleaca singur)
		fereastra = sesiune.instantiateDialog(MessageBox, text, fel, timeout=-1, close_on_any_key=False, enable_input=False, zPosition=100)
		fereastra.show()
		self._mesaj = (sesiune, fereastra)
		self._ceas = eTimer()
		self._ceas.callback.append(self._ascunde)
		self._ceas.start(durata * 1000, True)
		return True

	def _ascunde(self):
		mesaj, self._mesaj = self._mesaj, None
		if self._ceas is not None:
			self._ceas.stop()
			self._ceas = None
		if mesaj is not None:
			sesiune, fereastra = mesaj
			try:
				fereastra.hide()
				sesiune.deleteDialog(fereastra)
			except Exception as e:
				print("[Toast] inchiderea mesajului: %r" % (e,))


class Toast(_Toast):
	instance = None


Toast.instance = Toast()

__all__ = ["Toast"]

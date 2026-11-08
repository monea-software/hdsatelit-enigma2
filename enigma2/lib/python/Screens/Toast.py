# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile scrise pentru alte imagini (managerul de fisiere, la sfarsitul unei copieri; un ghid TV, cand are o versiune noua) arata un
# mesaj scurt, care pleaca singur: Toast.instance.showToast(text, tip, timeout). Aici mesajul e fereastra nemodala a imaginii
# (Notifications.AddPopup), care se inchide singura sau la orice tasta; nu opreste ce face omul.


class _Toast:
	TYPE_INFO = 0
	TYPE_WARNING = 1
	TYPE_ERROR = 2
	TYPE_SUCCESS = 3

	def showToast(self, text, toastType=TYPE_INFO, timeout=5, *args, **kwargs):
		try:
			from Screens.MessageBox import MessageBox
			from Tools import Notifications
			fel = MessageBox.TYPE_ERROR if toastType == self.TYPE_ERROR else MessageBox.TYPE_WARNING if toastType == self.TYPE_WARNING else MessageBox.TYPE_INFO
			durata = int(timeout) if isinstance(timeout, (int, float)) and timeout > 0 else 5
			Notifications.AddPopup(str(text), fel, durata, "HdsToast")
		except Exception as e:
			print("[Toast] %r" % (e,))


class Toast(_Toast):
	instance = None


Toast.instance = Toast()

__all__ = ["Toast"]

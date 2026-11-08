# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginurile trimit mesaje sau obiecte; jurnalul merge in print, ca in imagine.
from Tools.LogConfig import LOG_TYPE_INFO, LOG_TYPE_WARNING, LOG_TYPE_ERROR


class Log:
	@staticmethod
	def _log(logType, msg, callframe=None):
		# Cadrul apelantului este acceptat, fara sa fie retinut sau cercetat.
		print("[Log %s] %s" % (logType, msg))

	@staticmethod
	def i(msg):
		Log._log(LOG_TYPE_INFO, msg)

	@staticmethod
	def w(msg):
		Log._log(LOG_TYPE_WARNING, msg)

	@staticmethod
	def e(msg):
		Log._log(LOG_TYPE_ERROR, msg)

	@staticmethod
	def d(msg):
		Log._log("D", msg)

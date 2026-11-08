# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Interfata web cere marca si modelul; citim aceleasi date ca boxbranding.


def getOEMShowDisplayModel():
	from boxbranding import getDisplayModel
	return getDisplayModel()


def getOEMShowDisplayBrand():
	from boxbranding import getMachineBrand
	return getMachineBrand()


def getOEMShowModel():
	from boxbranding import getBoxType
	return getBoxType()

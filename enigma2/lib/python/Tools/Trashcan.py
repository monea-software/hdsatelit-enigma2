# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Trashcan.py: dosarul .Trash de langa filme, numele cerute de pluginuri. Imaginea nu are cos pentru filme: dosarul numai se creeaza si se arata, nimic nu se sterge singur.
import os


def getTrashFolder(path=None):
	if not path or not os.path.isdir(path):
		return None
	return os.path.join(path, ".Trash")


def createTrashFolder(path=None):
	cale = getTrashFolder(path)
	if cale is None:
		return None
	os.makedirs(cale, exist_ok=True)
	return cale

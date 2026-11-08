# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ce vine cu imaginea se deschide din meniu, separat de pluginurile puse de om.

Manifestul licentelor pastreaza pachetele de la constructie. Listele opkg spun
ce dosare de pluginuri le apartin, inclusiv cele ale producatorului. In lipsa
acestor date recunoastem numai dosarele proprii, fara sa ghicim dupa nume sau ora.
Incarcatorul de pluginuri si raportul erorilor isi pastreaza inventarul intreg.
"""
import os
import posixpath

try:
	from Components.HdsPluginExtern import PLUGINURI_IMAGINE
except ImportError:  # probe pe PC, modulul incarcat singur
	from HdsPluginExtern import PLUGINURI_IMAGINE


def _modSigur():
	try:
		from Components import HdsModSigur
	except ImportError:  # probe pe PC
		import HdsModSigur
	return HdsModSigur


def _cale(radacina, cale):
	return os.path.join(radacina, cale.lstrip('/')) if radacina and radacina != '/' else cale


def pacheteImagine(radacina=''):
	"""Pachetele puse la constructie, din acelasi manifest ca modul sigur."""
	m = _modSigur()
	pachete, _sursa = m._pacheteImagine(_cale(radacina, m.LISTA_LICENTE))
	return frozenset(pachete)


def _cheie(cale):
	if not isinstance(cale, str) or not cale:
		return ''
	cale = posixpath.normpath(cale.replace('\\', '/'))
	if '/Plugins/' in cale:
		cale = cale.rsplit('/Plugins/', 1)[1]
	parti = cale.split('/')
	if len(parti) < 2 or parti[0] not in ('Extensions', 'SystemPlugins') or parti[1] in ('', '.', '..'):
		return ''
	return '/'.join(parti[:2])


def pluginImagine(cale, radacina=''):
	"""True pentru un dosar sau fisier al imaginii; accepta si cheia Fel/Nume.

	Radacina este numai pentru probele pe PC. Cu o radacina explicita nu folosim
	cache-ul procesului, care descrie sistemul pornit, nu imaginea examinata.
	"""
	cheie = _cheie(cale)
	if not cheie:
		return False
	if cheie in PLUGINURI_IMAGINE:
		return True
	m = _modSigur()
	if radacina and radacina != '/':
		pluginuri, _sursa = m.pluginuriImagine(lista=_cale(radacina, m.LISTA_LICENTE),
			info=_cale(radacina, m.OPKG_INFO))
	else:
		pluginuri, _sursa = m.pluginuriImagine()
	return pluginuri is not None and cheie in pluginuri


def meniuriUtilizator(plugins, menuid):
	"""Intrarile de meniu adaugate de pluginurile omului, in ordinea lor."""
	from Plugins.Plugin import PluginDescriptor
	rez = []
	for plugin in plugins.getPlugins(PluginDescriptor.WHERE_MENU):
		if not pluginImagine(getattr(plugin, 'path', '')):
			rez += plugin(menuid) or []
	return rez

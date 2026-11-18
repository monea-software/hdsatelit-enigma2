# -*- coding: utf-8 -*-
# Luat din sursele GPL-2.0 ale unui enigma2 public (commitul 73ab10edaeee, 15.11.2026), fisierul
# lib/python/Components/Renderer/YWeatherPicon.py. Licenta GPL-2.0 (ca enigma2); nota autorului de mai jos ramane.
# Adus in imaginea HD Satelit (TPF, 15.11.2026) pentru temele care il cer (1 tema din feeduri, 5 folosiri): poza vremii dupa
# textul sursei (de pilda <convert type="YWeather"> al imaginii), din dosarul piconYWeather al temei sau al pluginului de vreme.
#
# Schimbat pentru imaginea HD Satelit: fara trecerea prin poza picon_default.png din dosarul relativ (LoadPixmap pe o cale
# relativa intorcea None si setPixmap(None) la fiecare schimbare); poza se pune direct din fisier.
#
# (c) 2boom mod 2012

from Components.Renderer.Renderer import Renderer
from enigma import ePixmap
from Tools.Directories import fileExists, SCOPE_SKIN_IMAGE, SCOPE_CURRENT_SKIN, resolveFilename


class YWeatherPicon(Renderer):
	__module__ = __name__
	searchPaths = ('/usr/lib/enigma2/python/Plugins/Extensions/iSkin/Weather/%s/', '/usr/lib/enigma2/python/Plugins/Extensions/YahooWeather/%s/', '/usr/share/enigma2/%s/', '/media/cf/%s/', '/media/sda1/%s/', '/media/usb/%s/', '/media/hdd/%s/')

	def __init__(self):
		Renderer.__init__(self)
		self.path = 'piconYWeather'
		self.nameCache = {}
		self.pngname = ''

	def applySkin(self, desktop, parent):
		attribs = []
		for (attrib, value,) in self.skinAttributes:
			if (attrib == 'path'):
				self.path = value
			else:
				attribs.append((attrib, value))
		self.skinAttributes = attribs
		return Renderer.applySkin(self, desktop, parent)

	GUI_WIDGET = ePixmap

	def changed(self, what):
		if self.instance:
			pngname = ''
			if (what[0] != self.CHANGED_CLEAR):
				sname = self.source.text or ''
				pngname = self.nameCache.get(sname, '')
				if (pngname == '') and sname:
					pngname = self.findPicon(sname)
					if (pngname != ''):
						self.nameCache[sname] = pngname
			if (pngname == ''):
				pngname = self.nameCache.get('default', '')
				if (pngname == ''):
					pngname = self.findPicon('picon_default')
					if (pngname == ''):
						tmp = resolveFilename(SCOPE_CURRENT_SKIN, 'picon_default.png')
						if fileExists(tmp):
							pngname = tmp
						else:
							pngname = resolveFilename(SCOPE_SKIN_IMAGE, 'skin_default/picon_default.png')
					self.nameCache['default'] = pngname
			if (self.pngname != pngname):
				self.pngname = pngname
				self.instance.setScale(1)
				self.instance.setPixmapFromFile(self.pngname)

	def findPicon(self, serviceName):
		for path in self.searchPaths:
			pngname = (((path % self.path) + serviceName) + '.png')
			if fileExists(pngname):
				return pngname
		return ''

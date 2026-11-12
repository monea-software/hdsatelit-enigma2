# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .ConditionalWidget import ConditionalWidget
from .GUIComponent import GUIComponent

from enigma import ePixmap, eTimer, eLabel

from Tools.Directories import resolveFilename, SCOPE_SKIN_IMAGE
from os import path
from skin import loadPixmap, parseColor

class Pixmap(GUIComponent):
	GUI_WIDGET = ePixmap

	def getSize(self):
		s = self.instance.size()
		return s.width(), s.height()

	def setPixmap(self, pixmap):
		if self.instance is not None:
			self.instance.setPixmap(pixmap)

class PixmapConditional(ConditionalWidget, Pixmap):
	def __init__(self, withTimer = True):
		ConditionalWidget.__init__(self)
		Pixmap.__init__(self)

class MovingPixmap(Pixmap):
	def __init__(self):
		Pixmap.__init__(self)
		
		self.moving = False
		
		# TODO: get real values
		self.x = 0.0
		self.y = 0.0
		
		self.clearPath()
		
		self.moveTimer = eTimer()
		self.moveTimer.callback.append(self.doMove)
		
	def clearPath(self, repeated = False):
		if (self.moving):
			self.moving = False
			self.moveTimer.stop()
			
		self.path = []
		self.currDest = 0
		self.repeated = repeated
		
	def addMovePoint(self, x, y, time = 20):
		self.path.append((x, y, time))
	
	def moveTo(self, x, y, time = 20):
		self.clearPath()
		self.addMovePoint(x, y, time)
		
	def startMoving(self):
		if not self.moving:
			self.time = self.path[self.currDest][2]
			self.stepX = (self.path[self.currDest][0] - self.x) / float(self.time)
			self.stepY = (self.path[self.currDest][1] - self.y) / float(self.time)

			self.moving = True
			self.moveTimer.start(100)
			
	def stopMoving(self):
		self.moving = False
		self.moveTimer.stop()
		
	def doMove(self):
		self.x += self.stepX
		self.y += self.stepY
		self.time -= 1
		try:
			self.move(int(self.x), int(self.y))
		except: # moving not possible... widget not there any more... stop moving
			self.stopMoving()
			
		if (self.time == 0):
			self.currDest += 1
			self.moveTimer.stop()
			self.moving = False
			if (self.currDest >= len(self.path)): # end of path
				if (self.repeated):
					self.currDest = 0
					self.moving = False
					self.startMoving()
			else:
				self.moving = False
				self.startMoving()

class MultiPixmap(Pixmap):
	def __init__(self):
		Pixmap.__init__(self)
		self.pixmaps = []
		# modul cu glife al temelor straine (iconFont + iconGlyphs [+ iconColors]): un text cu un caracter din fontul de
		# pictograme in locul pozei; indexul din setPixmapNum alege caracterul (si culoarea), ca la poze
		self.iconGlyphs = None
		self.iconColors = None

	def _glife(self):
		"""(font, coduri, culori sau None) cand tema cere modul cu glife cu valori bune, altfel None (raman pozele)"""
		if not self.skinAttributes:
			return None
		a = dict(self.skinAttributes)
		font, glife = a.get("iconFont"), a.get("iconGlyphs")
		if not font or not glife:
			return None
		try:
			coduri = [int(g.strip(), 0) for g in glife.split(",") if g.strip()]
		except ValueError:
			return None
		if not coduri or any(c <= 0 or c > 0x10FFFF or 0xD800 <= c <= 0xDFFF for c in coduri):
			return None
		culori = [c.strip() for c in (a.get("iconColors") or "").split(",") if c.strip()]
		return font, coduri, (culori if len(culori) == len(coduri) else None)

	def createWidget(self, parent):
		if self._glife() is not None:
			return eLabel(parent)
		return Pixmap.createWidget(self, parent)

	def applySkin(self, desktop, screen):
		glife = self._glife()
		if glife is not None:
			font, self.iconGlyphs, culori = glife
			self.iconColors = None
			if culori:
				try:
					self.iconColors = [parseColor(c) for c in culori]
				except Exception as e:
					print("[MultiPixmap] iconColors: %s" % e)
			scoase = ("pixmap", "pixmaps", "iconFont", "iconGlyphs", "iconColors", "alphatest", "alphaTest", "scale", "scaleFlags")
			self.skinAttributes = [(k, v) for (k, v) in self.skinAttributes if k not in scoase] + [("font", font)]
			rezultat = GUIComponent.applySkin(self, desktop, screen)
			self.setPixmapNum(0)
			return rezultat
		if self.skinAttributes is not None:
			skin_path_prefix = getattr(screen, "skin_path", path)
			pixmap = None
			attribs = [ ]
			for (attrib, value) in self.skinAttributes:
				if attrib == "pixmaps":
					pixmaps = value.split(',')
					for p in pixmaps:
						# o poza lipsa din lista (des la temele straine) nu mai face sa cada tot ecranul: locul ei ramane
						# gol (indexurile raman la fel), iar prima poza care exista e cea de inceput
						cale = resolveFilename(SCOPE_SKIN_IMAGE, p.strip(), path_prefix=skin_path_prefix)
						try:
							self.pixmaps.append(loadPixmap(cale, desktop))
						except Exception as e:
							self.pixmaps.append(None)
							print("[MultiPixmap] %s" % e)
							continue
						if not pixmap:
							pixmap = cale
				elif attrib == "pixmap":
					pixmap = resolveFilename(SCOPE_SKIN_IMAGE, value, path_prefix=skin_path_prefix)
				else:
					attribs.append((attrib,value))
			if pixmap:
				attribs.append(("pixmap", pixmap))
			self.skinAttributes = attribs
		return GUIComponent.applySkin(self, desktop, screen)

	def setPixmapNum(self, x):
		if self.iconGlyphs is not None:
			if self.instance and 0 <= x < len(self.iconGlyphs):
				self.instance.setText(chr(self.iconGlyphs[x]))
				if self.iconColors:
					self.instance.setForegroundColor(self.iconColors[x])
			return
		if self.instance:
			if len(self.pixmaps) > x:
				if self.pixmaps[x] is not None:
					self.instance.setPixmap(self.pixmaps[x])
			elif self.pixmaps:
				# a skin without pixmaps draws this widget in another way: nothing to switch
				print("setPixmapNum(%d) failed! defined pixmaps:" %(x), self.pixmaps)

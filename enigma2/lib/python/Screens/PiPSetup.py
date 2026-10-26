# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen
from Components.ActionMap import NumberActionMap
from Components.Label import Label

# marginile ferestrei in coordonatele ecranului interfetei (ca Screens/PictureInPicture.py): cu valorile vechi
# (720x576) o fereastra a unei teme 1920x1080 se muta numai in coltul din stanga sus
def _limite():
	"""(MAX_X, MAX_Y, MAX_W, MAX_H, MIN_W, MIN_H) dupa marimea ecranului interfetei"""
	try:
		from enigma import getDesktop
		d = getDesktop(0).size()
		mx, my = (d.width(), d.height()) if d.width() > 0 and d.height() > 0 else (720, 576)
	except Exception:
		mx, my = 720, 576
	return mx, my, mx * 3 // 4, my * 3 // 4, mx // 8, my // 8

def clip(val, min, max):
	if min <= val <= max:
		return val
	if min <= val:
		return max
	return min

class PiPSetup(Screen):
	def __init__(self, session, pip):
		Screen.__init__(self, session)
		
		self.pip = pip
		
		self.pos = (self.pip.instance.position().x(), self.pip.instance.position().y())
		self.size = self.pip.getSize()

		self.orgpos = self.pos
		self.orgsize = self.size
		
		self.resize = 100

		self["text"] = Label(_("Please use direction keys to move the PiP window.\nPress Bouquet +/- to resize the window.\nPress OK to go back to the TV mode or EXIT to cancel the moving."))

		self["actions"] = NumberActionMap(["PiPSetupActions", "NumberActions"], 
		{
			"ok": self.go,
			"cancel": self.cancel,
			"up": self.up,
			"down": self.down,
			"left": self.left,
			"right": self.right,
			"size+": self.bigger,
			"size-": self.smaller,
			"1": self.keyNumberGlobal,
			"2": self.keyNumberGlobal,
			"3": self.keyNumberGlobal,
			"4": self.keyNumberGlobal,
			"5": self.keyNumberGlobal,
			"6": self.keyNumberGlobal,
			"7": self.keyNumberGlobal,
			"8": self.keyNumberGlobal,
			"9": self.keyNumberGlobal,
			"0": self.keyNumberGlobal
		}, -1)
		
	def go(self):
		self.close()
	
	def cancel(self):
		self.pos = self.orgpos
		self.size = self.orgsize
		self.setPiPPosition()
		self.close()
	
	def setPiPPosition(self):
		self.pip.move(self.pos[0], self.pos[1])
		self.pip.resize(self.size[0], self.size[1])

	def resizePiP(self, resize):
		resize += 100 # resize is in percent, so resize=+20 means: 120%
		
		oldsize = self.size
		_mx, _my, max_w, max_h, min_w, min_h = _limite()
		w = clip(self.size[0] * resize // 100, min_w, max_w)
		h = clip(self.size[1] * resize // 100, min_h, max_h)
		
		# calculate offset from center
		mx = (oldsize[0] - w) // 2
		my = (oldsize[1] - h) // 2
		
		self.size = (w, h)
		# reclip, account for new center
		self.moveRelative(x=mx, y=my)
	
	def moveRelative(self, x=0, y=0):
		max_x, max_y = _limite()[:2]
		self.pos = (clip(self.pos[0] + x, 0, max_x - self.size[0]), clip(self.pos[1] + y, 0, max_y - self.size[1]))
		self.setPiPPosition()
	
	def up(self):
		self.moveRelative(y=-32 * _limite()[1] // 576)

	def down(self):
		self.moveRelative(y=+32 * _limite()[1] // 576)
	
	def left(self):
		self.moveRelative(x=-24 * _limite()[0] // 720)
	
	def right(self):
		self.moveRelative(x=+24 * _limite()[0] // 720)
	
	def bigger(self):
		self.resizePiP(+10)
	
	def smaller(self):
		self.resizePiP(-10)
	
	def keyNumberGlobal(self, number):
		
		if number > 0:
			max_x, max_y = _limite()[:2]
			colsize = max_x // 3
			rowsize = max_y // 3
			col = (number-1) % 3
			row = (number-1) // 3

			# un sfert din latimea ecranului (180x135 pe 720x576)
			self.size = (max_x // 4, max_y * 135 // 576)

			# offset to keep center
			ox = (colsize - self.size[0]) // 2
			oy = (rowsize - self.size[1]) // 2

			self.pos = (col * colsize + ox, row * rowsize + oy)
		else:
			# restore old position
			self.pos = self.orgpos
			self.size = self.orgsize
		# reclip
		self.moveRelative()

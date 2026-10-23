# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .Source import Source

class CanvasSource(Source):
	def __init__(self):
		Source.__init__(self)
		self.sequence = 0
		self.clear()

	def clear(self):
		self.sequence += 1
		self._drawlist = (self.sequence, [ ])

	def get_drawlist(self):
		return self._drawlist

	drawlist = property(get_drawlist)

	def fill(self, x, y, width, height, color):
		self.drawlist[1].append((1, x, y, width, height, color))

	def writeText(self, x, y, width, height, fg, bg, font, text, flags = 0):
		self.drawlist[1].append((2, x, y, width, height, fg, bg, font, text, flags))

	# HDSatelit: forme cu margini netede (eCanvas.drawLine/drawArc/drawRing/fillCircle/fillPolygon, desenate
	# in C++ de lib/gdi/desennetezit.cpp). Coordonate cu zecimale; unghiuri in grade, 0 = dreapta, pozitiv =
	# in sensul acelor de ceas pe ecran (90 = jos, 270 = sus); culoarea ca la fill (0x00rrggbb = opac).
	def drawLine(self, x0, y0, x1, y1, width, color):
		self.drawlist[1].append((3, x0, y0, x1, y1, width, color))

	def drawArc(self, cx, cy, radius, width, startAngle, sweepAngle, color, roundCaps=1):
		self.drawlist[1].append((4, cx, cy, radius, width, startAngle, sweepAngle, color, roundCaps))

	def drawRing(self, cx, cy, radius, width, color):
		self.drawlist[1].append((5, cx, cy, radius, width, color))

	def fillCircle(self, cx, cy, radius, color):
		self.drawlist[1].append((6, cx, cy, radius, color))

	def fillPolygon(self, points, color):
		# points: [x0, y0, x1, y1, ...] sau [(x0, y0), (x1, y1), ...]
		self.drawlist[1].append((7, list(points), color))

	def flush(self):
		self.changed((self.CHANGED_DEFAULT,))

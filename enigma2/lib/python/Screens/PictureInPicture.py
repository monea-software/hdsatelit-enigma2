# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen
from enigma import ePoint, eSize, eServiceCenter, getBestPlayableServiceReference, eServiceReference, getDesktop
from Components.VideoWindow import VideoWindow
from Components.config import config, ConfigPosition

pip_config_initialized = False


def _desktop():
	"""(latimea, inaltimea) ecranului interfetei (1920x1080 in tema noastra); 720x576 cand nu se poate citi"""
	try:
		d = getDesktop(0).size()
		if d.width() > 0 and d.height() > 0:
			return d.width(), d.height()
	except Exception:
		pass
	return 720, 576

class PictureInPicture(Screen):
	def __init__(self, session):
		global pip_config_initialized
		Screen.__init__(self, session)
		# fereastra video in coordonatele ecranului interfetei: cu marimea veche (720x576) o fereastra a unei teme
		# 1920x1080 iesea in afara si ajungea cu latimea 0 (/proc/stb/vmpeg/1/dst_width = 0, imaginea in imagine
		# pornea fara sa se vada)
		latime, inaltime = _desktop()
		self["video"] = VideoWindow(fb_width=latime, fb_height=inaltime)
		self.currentService = None
		if not pip_config_initialized:
			config.av.pip = ConfigPosition(default=[-1, -1, -1, -1], args=(latime - 1, inaltime - 1, latime, inaltime))
			pip_config_initialized = True
		self.onLayoutFinish.append(self.LayoutFinished)

	def LayoutFinished(self):
		self.onLayoutFinish.remove(self.LayoutFinished)
		x = config.av.pip.value[0]
		y = config.av.pip.value[1]
		w = config.av.pip.value[2]
		h = config.av.pip.value[3]
		if x != -1 and y != -1 and w != -1 and h != -1:
			self.move(x, y)
			self.resize(w, h)

	def move(self, x, y):
		config.av.pip.value[0] = x
		config.av.pip.value[1] = y
		config.av.pip.save()
		self.instance.move(ePoint(x, y))

	def resize(self, w, h):
		config.av.pip.value[2] = w
		config.av.pip.value[3] = h
		config.av.pip.save()
		self.instance.resize(eSize(*(w, h)))
		self["video"].instance.resize(eSize(*(w, h)))

	def getPosition(self):
		return ((self.instance.position().x(), self.instance.position().y()))

	def getSize(self):
		return (self.instance.size().width(), self.instance.size().height())

	def playService(self, service):
		if service and (service.flags & eServiceReference.isGroup):
			ref = getBestPlayableServiceReference(service, eServiceReference())
		else:
			ref = service
		if ref:
			self.pipservice = eServiceCenter.getInstance().play(ref)
			if self.pipservice and not self.pipservice.setTarget(1):
				self.pipservice.start()
				self.currentService = service
				return True
			else:
				self.pipservice = None
		return False

	def getCurrentService(self):
		return self.currentService


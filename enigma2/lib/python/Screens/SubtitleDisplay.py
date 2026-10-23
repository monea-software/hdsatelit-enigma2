# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Screens.Screen import Screen

class SubtitleDisplay(Screen):
	# the window of the subtitles (the service puts an eSubtitleWidget in it)
	def __init__(self, session, *args, **kwargs):
		Screen.__init__(self, session, *args, **kwargs)
		# HDSatelit: the look of the text subtitles chosen by the user (Components/HdsSubtitrariAspect.py:
		# font, weight, size and color of the letters, outline, shadow, background, height, line spacing), set before
		# the first subtitle. Never stops the subtitles.
		try:
			from Components import HdsSubtitrariAspect
			HdsSubtitrariAspect.pornire()
		except Exception as e:
			print("[SubtitleDisplay] the look of the text subtitles was not set: %s" % e)
		# HDSatelit: the DVB subtitle pictures read as text (OCR, Components/HdsOcrSubtitrari.py) when
		# "Magnification of DVB subtitles" = OCR; set now and again on every change of that setting. Never stops the
		# subtitles: without it the pictures are shown, as before.
		try:
			from Components import HdsOcrSubtitrari
			HdsOcrSubtitrari.legaNucleul()
		except Exception as e:
			print("[SubtitleDisplay] OCR of the DVB subtitles was not set up: %s" % e)
		# automatic translation of the text subtitles (teletext, files, the text read from DVB pages;
		# Components/HdsTraducereSubtitrari.py) when it is turned on; set now and again on every change of its settings.
		# Never stops the subtitles: without it the original text is shown, as before.
		try:
			from Components import HdsTraducereSubtitrari
			HdsTraducereSubtitrari.legaNucleul()
		except Exception as e:
			print("[SubtitleDisplay] the translation of the subtitles was not set up: %s" % e)

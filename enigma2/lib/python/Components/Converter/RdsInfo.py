# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import iRdsDecoder, iPlayableService
from Components.Converter.Converter import Converter
from Components.Element import cached
from Components import HdsRdsText

class RdsInfo(Converter, object):
	RASS_INTERACTIVE_AVAILABLE = 0
	RTP_TEXT_CHANGED = 1
	RADIO_TEXT_CHANGED = 2

	def __init__(self, type):
		Converter.__init__(self, type)
		self.type, self.interesting_events = {
				"RadioText": (self.RADIO_TEXT_CHANGED, (iPlayableService.evUpdatedRadioText,)),
				"RtpText": (self.RTP_TEXT_CHANGED, (iPlayableService.evUpdatedRtpText,)),
				"RasInteractiveAvailable": (self.RASS_INTERACTIVE_AVAILABLE, (iPlayableService.evUpdatedRassInteractivePicMask,))
			}[type]

	def _text(self, decoder):
		# textul radio si piesa trec prin Components/HdsRdsText.py: numai dupa un mesaj anuntat de decodor pentru
		# serviciul care merge si numai text valid, decodat in setul lui de caractere (EBU Latin, ISO-8859, UTF-8)
		HdsRdsText.urmareste(getattr(self.source, "navcore", None))
		fel = HdsRdsText.TEXT if self.type == self.RADIO_TEXT_CHANGED else HdsRdsText.PIESA
		return HdsRdsText.text_decodor(decoder, fel, iRdsDecoder)

	@cached
	def getText(self):
		decoder = self.source.decoder
		text = ""
		if decoder:
			if self.type in (self.RADIO_TEXT_CHANGED, self.RTP_TEXT_CHANGED):
				text = self._text(decoder)
			else:
				print("unknown RdsInfo Converter type", self.type)
		return text

	text = property(getText)

	@cached
	def getBoolean(self):
		decoder = self.source.decoder
		if self.type == self.RASS_INTERACTIVE_AVAILABLE:
			mask = decoder and decoder.getRassInteractiveMask()
			return (mask and mask[0] & 1 and True) or False
		elif self.type in (self.RADIO_TEXT_CHANGED, self.RTP_TEXT_CHANGED):
			return bool(decoder and self._text(decoder))
	boolean = property(getBoolean)

	def changed(self, what):
		if what[0] != self.CHANGED_SPECIFIC or what[1] in self.interesting_events:
			Converter.changed(self, what)

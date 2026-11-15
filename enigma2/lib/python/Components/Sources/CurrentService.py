# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.PerServiceDisplay import PerServiceBase
from enigma import iPlayableService
from .Source import Source
from Components.Element import cached

class CurrentService(PerServiceBase, Source):
	def __init__(self, navcore):
		Source.__init__(self)
		evenimente = {
				iPlayableService.evStart: self.serviceEvent,
				iPlayableService.evEnd: self.serviceEvent,
				# FIXME: we should check 'interesting_events'
				# which is not always provided.
				iPlayableService.evUpdatedInfo: self.serviceEvent,
				iPlayableService.evUpdatedEventInfo: self.serviceEvent,
				iPlayableService.evCuesheetChanged: self.serviceEvent,
				iPlayableService.evVideoSizeChanged: self.serviceEvent
			}
		# AIT-ul HbbTV citit, schimbat sau disparut (lib/dvb/pmt.cpp): vine DUPA evUpdatedInfo (PMT-ul), deci convertoarele
		# care depind de el (HdsInfo HbbtvRosu, semnul rosu din bara) trebuie sa-l primeasca, altfel raman pe starea de la
		# PMT, cand AIT-ul nu era inca citit. Pe nucleele fara eveniment nu se adauga nimic.
		ev_hbbtv = getattr(iPlayableService, "evHBBTVInfo", None)
		if ev_hbbtv is not None:
			evenimente[ev_hbbtv] = self.serviceEvent
		# PMT-ul canalului citit din nou (lib/service/servicedvb.cpp, dupa evUpdatedInfo, ca in OE-Alliance): convertoarele
		# temelor facute pentru OE-Alliance isi recitesc atunci datele tunerului (MercPliExtraInfo: updateFEdata).
		# Numerele negative puse de HdsEnigmaCompat pe nucleele fara eveniment nu vin niciodata: nu se adauga.
		ev_pmt = getattr(iPlayableService, "evNewProgramInfo", None)
		if ev_pmt is not None and ev_pmt >= 0:
			evenimente[ev_pmt] = self.serviceEvent
		PerServiceBase.__init__(self, navcore, evenimente, with_event=True)
		self.navcore = navcore

	def serviceEvent(self, event):
		self.changed((self.CHANGED_SPECIFIC, event))

	@cached
	def getCurrentService(self):
		return self.navcore.getCurrentService()

	service = property(getCurrentService)

	@cached
	def getCurrentServiceRef(self):
		"""Referinta canalului cerut (cu numarul lui din lista, getChannelNum), ca in OE-Alliance: temele si convertoarele
		facute pentru OE-Alliance citesc session.CurrentService.serviceref (numarul canalului inaintea numelui,
		ServiceNumber, VfdDisplay). Fara ea numarul lipsea din tema (darog69, forum 1455, TCN 15.11.2026)."""
		citeste = getattr(self.navcore, "getCurrentServiceReferenceOriginal", None) or getattr(self.navcore, "getCurrentlyPlayingServiceReference", None)
		return citeste() if citeste is not None else None

	serviceref = property(getCurrentServiceRef)

	def destroy(self):
		PerServiceBase.destroy(self)
		Source.destroy(self)


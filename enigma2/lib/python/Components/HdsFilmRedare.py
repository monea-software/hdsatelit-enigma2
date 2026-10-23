# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFilmRedare.py: de ce nu se poate reda un film din fisier si ce i se spune omului.
#
# servicemp3 (lib/service/servicemp3.cpp) pune motivul in sUser+15, ca text „fel|capuri|video|detaliu”:
#   fel      lipsa       o pista nu are niciun element care sa o duca spre placa (restul filmului merge)
#            componenta  pipeline-ul s-a oprit pentru ca lipseste un element (de exemplu demultiplexorul MPEG-PS)
#            video/sunet decodorul receptorului nu primeste formatul (eroare de la dvbvideosink/dvbaudiosink)
#            negociere   imaginea sau sunetul decodat nu are drum spre placa (Theora, decodata in cadre brute)
#            format      fisierul nu se poate desface; fisier: nu se poate citi (la un flux: reteaua)
#            pornire     filmul nu a pornit si nu s-a miscat in 30 s; nimic: nicio pista de redat
#            pipeline    playbin lipseste; eroare: orice alta eroare GStreamer
#            decodor     receptorul HiSilicon nu mai are memoria decodorului pentru fisiere (maparea demonului platformei
#                        a esuat la pornire): pipeline-ul nu se face, altfel prima scriere a sinkurilor in video0 sau audio0
#                        ar opri nucleul (lib/dvb/hdspazavideo.h); trece numai la repornirea receptorului. Nu e un
#                        defect de spus omului (niciun defect intern pe televizor): receptorul isi reface singur
#                        memoria, cu pazele repornirii in standby, si filmul porneste dupa repornire
#                        (Components/HdsMemorieDriver.py, refacereFilm); pe ecran numai TXT_PORNESTE, iar cand o paza
#                        opreste repornirea, numai TXT_NU_ACUM
#   capuri   tipul GStreamer fara drum (video/x-av1, audio/x-wma, video/mpeg...), poate fi gol
#   video    1 = imaginea merge, 0 = nu, ? = nu se stie inca
#   detaliu  mesajul GStreamer, englezeste (pentru jurnal si pentru randul tehnic)
# Evenimentele: evUser+10 / +11 sunetul / imaginea refuzate de sinkuri, evUser+12 un element lipsa, evUser+16 orice
# alt motiv (textul GStreamer nu ajunge niciodata pe ecran, numai in randul tehnic).
# Aici: numele formatului pe intelesul oricui (un tip fara nume cunoscut e „un format necunoscut”, tipul GStreamer
# ramane numai in randul tehnic), verdictul (filmul se opreste sau merge fara sunet) si textele. Le folosesc playerul
# (Screens/InfoBarGenerics.py, InfoBarFilmRefuz), pagina web (HdsWebControl/filme_web.py) si probele de pe PC.
# Fisierul nu importa nimic din enigma2 la incarcare.

# eServiceFactoryMP3::id: filmele si muzica din fisiere, fluxurile de pe internet
TIP_FILM = 4097
MAX_NUME = 20		# numele unui format in mesajul de pe televizor
FLUXURI = ("http://", "https://", "udp://", "rtp://", "rtsp://", "rtspt://", "mms://")


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _tFilm(text):
	return _t(text)


def _tCanal(text):
	"""Ca _t, cu fraza despre canal in locul celei despre film (PENTRU_CANAL), unde exista."""
	return _t(PENTRU_CANAL.get(text, text))


# tipul GStreamer -> numele aratat (prefixul cel mai lung intai); numele formatelor nu se traduc
FORMATE_VIDEO = (
	("video/x-av1", "AV1"),
	("video/x-theora", "Theora"),
	("video/x-h266", "H.266 (VVC)"),
	("video/x-cavs", "AVS"),
	("video/x-pn-realvideo", "RealVideo"),
	("video/x-wmv", "WMV"),
	("video/x-vp6-flash", "VP6"),
	("video/x-vp6-alpha", "VP6"),
	("video/x-vp6", "VP6"),
	("video/x-vp8", "VP8"),
	("video/x-vp9", "VP9"),
	("video/x-dirac", "Dirac"),
	("video/x-prores", "ProRes"),
	("video/x-ffv", "FFV1"),
	("video/x-h264", "H.264"),
	("video/x-h265", "H.265 (HEVC)"),
	("video/x-divx", "DivX"),
	("video/x-xvid", "Xvid"),
	("video/x-3ivx", "3ivx"),
	("video/x-msmpeg", "MS-MPEG4"),
	("video/x-h263", "H.263"),
	("video/x-flash-video", "Flash (Sorenson)"),
	("video/x-svq", "Sorenson"),
	("video/x-cinepak", "Cinepak"),
	("video/x-indeo", "Indeo"),
	("video/x-huffyuv", "HuffYUV"),
	("video/x-dnxhd", "DNxHD"),
	("video/x-jpeg", "MJPEG"),
	("image/jpeg", "MJPEG"),
	("image/png", "PNG"),
	("video/mpeg", "MPEG"),
)
FORMATE_SUNET = (
	("audio/x-wma", "WMA"),
	("audio/x-true-hd", "Dolby TrueHD"),
	("audio/x-truehd", "Dolby TrueHD"),
	("audio/AMR-WB", "AMR-WB"),
	("audio/AMR", "AMR"),
	("audio/x-ape", "APE"),
	("audio/x-wavpack", "WavPack"),
	("audio/x-alac", "ALAC"),
	("audio/x-pn-realaudio", "RealAudio"),
	("audio/x-eac3", "E-AC-3"),
	("audio/x-ac3", "AC-3"),
	("audio/x-dts", "DTS"),
	("audio/x-opus", "Opus"),
	("audio/x-vorbis", "Vorbis"),
	("audio/x-flac", "FLAC"),
	("audio/x-speex", "Speex"),
	("audio/x-nellymoser", "Nellymoser"),
	("audio/x-adpcm", "ADPCM"),
	("audio/x-lpcm", "LPCM"),
	("audio/x-private1-lpcm", "LPCM"),
	("audio/x-raw", "PCM"),
	("audio/mpeg", "MPEG"),
)
# containerele fara demultiplexor in imagine: ce fisiere sunt
CONTAINERE = (
	("video/mpeg,systemstream=(boolean)true", N_("MPG și VOB")),
	("video/mpeg,systemstream=true", N_("MPG și VOB")),
	("video/x-ms-asf", N_("WMV și ASF")),
	("application/vnd.rn-realmedia", N_("RM și RMVB")),
)
# numele din etichetele fisierului (GST_TAG_VIDEO_CODEC, litere mici), pentru „negociere”, cand tipul fara drum nu se
# stie: imaginea acestor formate nu are drum spre decodorul placii (decodata in cadre brute, pe care nu le ia nimeni)...
IMAGINE_FARA_DRUM = ("theora", "av1", "vvc", "h.266", "h266", "prores", "dirac", "ffv", "realvideo", "jpeg", "png",
	"cinepak", "indeo", "huffyuv", "dnxhd", "snow", "avs")
# ...iar a acestora are (dvbvideosink): cand imaginea e una dintre ele, sunetul e cel fara drum
IMAGINE_CU_DRUM = ("h.264", "h264", "avc", "h.265", "h265", "hevc", "mpeg", "divx", "xvid", "3ivx", "vc-1", "vc1",
	"wmv", "vp8", "vp9", "h.263", "h263", "sorenson", "flash")

TXT_REFUZ = N_("Filmul nu se poate reda pe acest receptor.")
TXT_FARA_IMAGINE = N_("Filmul nu se poate afișa pe acest receptor.")
TXT_FARA_SUNET = N_("Filmul merge fără sunet.")
TXT_INCA_NU = N_("Filmul nu se poate reda încă.")
TXT_FORMAT_IMAGINE = N_("Imaginea este în formatul %s, pe care receptorul nu îl cunoaște.")
TXT_FORMAT_SUNET = N_("Sunetul este în formatul %s, pe care receptorul nu îl cunoaște.")
TXT_IMAGINE_NECUNOSCUTA = N_("Imaginea este într-un format pe care receptorul nu îl cunoaște.")
TXT_SUNET_NECUNOSCUT = N_("Sunetul este într-un format pe care receptorul nu îl cunoaște.")
TXT_FORMATE_NECUNOSCUTE = N_("Imaginea sau sunetul este într-un format pe care receptorul nu îl cunoaște.")
TXT_UNUL = N_("Receptorul nu cunoaște unul dintre aceste formate.")
TXT_CONTAINER = N_("Fișierele %s au nevoie de o componentă care nu este încă în programul receptorului.")
TXT_NEDESCHIS = N_("Fișierul nu se poate deschide: poate fi deteriorat sau într-un format necunoscut.")
TXT_NECITIT = N_("Fișierul nu se poate citi. Verifică dacă stick-ul sau discul este încă legat la receptor.")
TXT_RETEA = N_("Legătura cu serverul filmului s-a întrerupt. Verifică rețeaua și încearcă încă o dată.")
TXT_NEPORNIT = N_("Filmul nu a pornit în 30 de secunde, așa că a fost oprit. Încearcă încă o dată.")
TXT_NIMIC = N_("Fișierul nu are imagine sau sunet pe care receptorul să le poată reda.")
TXT_FARA_REDARE = N_("Redarea filmelor nu este pregătită: lipsește o componentă din programul receptorului.")
TXT_FORMATE = N_("Imagine: %s. Sunet: %s.")
TXT_NU_ACUM = N_("Filmul nu poate porni acum.")
# lipsa memoriei decodorului (felul "decodor"): receptorul o reface singur, deci pe ecran numai textul scurt, fara defect
TXT_PORNESTE = N_("Filmul pornește imediat.")
# un canal de pe internet din lista de canale (tipul 4097 in bara principala): aceleasi verdicte, spuse despre canal
TXT_CANAL_REFUZ = N_("Canalul nu se poate reda pe acest receptor.")
TXT_CANAL_FARA_SUNET = N_("Canalul merge fără sunet.")
TXT_CANAL_RETEA = N_("Legătura cu serverul canalului s-a întrerupt. Verifică rețeaua și încearcă încă o dată.")
TXT_CANAL_NEPORNIT = N_("Canalul nu a pornit în 30 de secunde, așa că a fost oprit. Încearcă încă o dată.")
TXT_CANAL_NEDESCHIS = N_("Fluxul canalului nu se poate desface: poate fi într-un format necunoscut.")
TXT_CANAL_NIMIC = N_("Canalul nu trimite imagine sau sunet pe care receptorul să le poată reda.")
TXT_CANAL_NU_ACUM = N_("Canalul nu poate porni acum.")
TXT_CANAL_PORNESTE = N_("Canalul pornește imediat.")
PENTRU_CANAL = {
	TXT_REFUZ: TXT_CANAL_REFUZ,
	TXT_FARA_IMAGINE: TXT_CANAL_REFUZ,
	TXT_INCA_NU: TXT_CANAL_REFUZ,
	TXT_FARA_SUNET: TXT_CANAL_FARA_SUNET,
	TXT_RETEA: TXT_CANAL_RETEA,
	TXT_NEPORNIT: TXT_CANAL_NEPORNIT,
	TXT_NEDESCHIS: TXT_CANAL_NEDESCHIS,
	TXT_NIMIC: TXT_CANAL_NIMIC,
	TXT_NU_ACUM: TXT_CANAL_NU_ACUM,
	TXT_PORNESTE: TXT_CANAL_PORNESTE,
}


class Verdict(object):
	"""Ce se spune: titlul (o fraza), detaliul (fraza a doua), randul tehnic (englezeste, poate lipsi) si daca filmul se
	opreste (refuza) sau merge mai departe."""
	__slots__ = ("fel", "refuza", "titlu", "detaliu", "tehnic")

	def __init__(self, fel, refuza, titlu, detaliu, tehnic=""):
		self.fel = fel
		self.refuza = refuza
		self.titlu = titlu
		self.detaliu = detaliu
		self.tehnic = tehnic

	def text(self):
		"""Textul ferestrei de pe televizor: fraza simpla pe primul rand, explicatia sub ea. Caseta de mesaj a skinului
		HDSatelit are loc de trei randuri (1036x148, HdsRegular;34), toate folosite de titlu si explicatie, deci randul
		tehnic nu intra aici: el ramane in jurnal si pe pagina web."""
		if self.detaliu:
			return self.titlu + "\n" + self.detaliu
		return self.titlu

	def dict(self):
		return {"fel": self.fel, "refuza": self.refuza, "titlu": self.titlu, "detaliu": self.detaliu,
			"tehnic": self.tehnic}


def desparte(motiv):
	"""„fel|capuri|video|detaliu” -> tuplul celor patru (siruri goale unde lipsesc)."""
	parti = (motiv or "").split("|", 3)
	while len(parti) < 4:
		parti.append("")
	return tuple(p.strip() for p in parti)


def _fara_spatii(text):
	return "".join((text or "").split())


def _cauta(tabel, capuri):
	c = _fara_spatii(capuri)
	for prefix, nume in tabel:
		if c == prefix or c.startswith(prefix + ","):
			return nume
	return ""


def numeContainer(capuri):
	"""Fisierele fara demultiplexor in imagine („MPG și VOB”), tradus, sau „”."""
	c = _fara_spatii(capuri)
	for prefix, nume in CONTAINERE:
		if c == prefix or c.startswith(prefix + ","):
			return _t(nume)
	return ""


def _fourcc(capuri):
	"""Codul de patru litere al unei piste necunoscute (fourcc=(string)XQZW sau fourcc=(int)N, cu literele in ordinea
	din fisier), sau „”."""
	c = _fara_spatii(capuri)
	i = c.find("fourcc=")
	if i < 0:
		return ""
	valoare = c[i + 7:].split(",", 1)[0]
	tip = ""
	if valoare.startswith("("):
		tip, _sep, valoare = valoare[1:].partition(")")
	if tip in ("int", "uint", "guint") or valoare.isdigit():
		try:
			n = int(valoare)
		except ValueError:
			return ""
		valoare = "".join(chr((n >> (8 * k)) & 0xFF) for k in range(4))
	if len(valoare) == 4 and all(32 < ord(x) < 127 for x in valoare):
		return valoare
	return ""


def numeFormat(capuri):
	"""Numele formatului dintr-un tip GStreamer; o pista AVI necunoscuta dupa codul ei de patru litere; „” pentru un tip
	fara nume cunoscut (audio/x-unknown, un tip nou): pe ecran el devine „un format necunoscut”."""
	c = _fara_spatii(capuri)
	if not c:
		return ""
	nume = _cauta(FORMATE_VIDEO, c) or _cauta(FORMATE_SUNET, c)
	if nume:
		return nume
	return _fourcc(c)


def _scurt(nume):
	# numele din etichetele fisierului pot fi lungi („MPEG-4 AAC audio, High Efficiency”): taiate, ca mesajul sa incapa
	return (nume or "").strip()[:MAX_NUME]


def _formateCunoscute(codec_video, codec_sunet):
	v = _scurt(codec_video)
	s = _scurt(codec_sunet)
	if not v and not s:
		return ""
	return _t(TXT_FORMATE) % (v or "-", s or "-")


def _are(nume, lista):
	n = (nume or "").lower()
	return bool(n) and any(x in n for x in lista)


def _imagine(nume):
	"""Explicatia pentru imaginea fara drum: cu numele formatului, sau „un format necunoscut”."""
	return _t(TXT_FORMAT_IMAGINE) % nume if nume else _t(TXT_IMAGINE_NECUNOSCUTA)


def _sunet(nume):
	return _t(TXT_FORMAT_SUNET) % nume if nume else _t(TXT_SUNET_NECUNOSCUT)


def verdict(motiv, codec_video="", codec_sunet="", flux=False, canal=False):
	"""Verdictul pentru motivul din sUser+15 (None cand nu e nimic de spus). codec_video si codec_sunet sunt etichetele
	din fisier (sTagVideoCodec, sTagAudioCodec), folosite cand tipul fara drum nu se stie; flux: filmul vine de pe
	internet (o eroare de citire e atunci reteaua, nu stick-ul); canal: un canal din lista de canale (bara principala),
	deci frazele spun 'canalul', nu 'filmul' (PENTRU_CANAL)."""
	_t = _tCanal if canal else _tFilm
	fel, capuri, video, detaliu = desparte(motiv)
	if not fel:
		return None
	if fel == "decodor":
		# nu fisierul e de vina: memoria decodorului lipseste pana la repornirea receptorului. Niciun defect intern pe
		# ecran: playerul cere refacerea (HdsMemorieDriver.refacereFilm) si arata atunci verdictRefacere(); cand o paza o
		# opreste, ramane numai fraza scurta. Motivul tehnic ramane in randul tehnic si in jurnal.
		return Verdict(fel, True, _t(TXT_NU_ACUM), "", detaliu)
	formate = _formateCunoscute(codec_video, codec_sunet)
	container = numeContainer(capuri)
	nume = numeFormat(capuri)
	e_sunet = capuri.startswith("audio/")
	if container and fel in ("lipsa", "componenta", "video", "sunet"):
		# nu receptorul nu poate: lipseste o componenta din programul lui
		return Verdict(fel, True, _t(TXT_INCA_NU), _t(TXT_CONTAINER) % container, capuri or detaliu)
	if fel == "lipsa":
		if e_sunet and video == "1":
			return Verdict(fel, False, _t(TXT_FARA_SUNET), _sunet(nume), capuri)
		if e_sunet:
			return Verdict(fel, True, _t(TXT_REFUZ), _sunet(nume), capuri)
		return Verdict(fel, True, _t(TXT_FARA_IMAGINE), _imagine(nume or _scurt(codec_video)), capuri)
	if fel in ("componenta", "video", "sunet"):
		if fel == "sunet" or e_sunet:
			return Verdict(fel, True, _t(TXT_REFUZ), _sunet(nume or _scurt(codec_sunet)), capuri or detaliu)
		return Verdict(fel, True, _t(TXT_FARA_IMAGINE), _imagine(nume or _scurt(codec_video)), capuri or detaliu)
	if fel == "negociere":
		# care pista nu are drum, dupa numele din fisier: o imagine fara decodor pe placa (Theora, AV1), altfel sunetul
		# langa o imagine care are drum; cand nu se stie, amandoua numele
		if _are(codec_video, IMAGINE_FARA_DRUM):
			return Verdict(fel, True, _t(TXT_FARA_IMAGINE), _imagine(_scurt(codec_video)), detaliu)
		if codec_sunet and _are(codec_video, IMAGINE_CU_DRUM):
			return Verdict(fel, True, _t(TXT_REFUZ), _sunet(_scurt(codec_sunet)), detaliu)
		if formate:
			return Verdict(fel, True, _t(TXT_REFUZ), formate + " " + _t(TXT_UNUL), detaliu)
		return Verdict(fel, True, _t(TXT_REFUZ), _t(TXT_FORMATE_NECUNOSCUTE), detaliu)
	if fel == "format":
		return Verdict(fel, True, _t(TXT_REFUZ), _t(TXT_NEDESCHIS), detaliu)
	if fel == "fisier":
		return Verdict(fel, True, _t(TXT_REFUZ), _t(TXT_RETEA) if flux else _t(TXT_NECITIT), detaliu)
	if fel == "pornire":
		return Verdict(fel, True, _t(TXT_REFUZ), _t(TXT_NEPORNIT), formate)
	if fel == "nimic":
		return Verdict(fel, True, _t(TXT_REFUZ), _t(TXT_NIMIC), formate)
	if fel == "pipeline":
		return Verdict(fel, True, _t(TXT_REFUZ), _t(TXT_FARA_REDARE), "")
	return Verdict(fel, True, _t(TXT_REFUZ), formate, detaliu)


def verdictRefacere(tehnic="", canal=False):
	"""Ce se spune cand receptorul isi reface memoria decodorului ca sa porneasca filmul (sau canalul): o fraza scurta,
	fara defect; filmul nu se opreste de mana (refuza False), receptorul se reporneste si il porneste apoi."""
	_t = _tCanal if canal else _tFilm
	return Verdict("decodor", False, _t(TXT_PORNESTE), "", tehnic)


def esteDecodor(verdict_):
	"""Verdictul spune ca lipseste memoria decodorului (felul "decodor")."""
	return verdict_ is not None and getattr(verdict_, "fel", "") == "decodor"


def verdictDinInfo(info, cale="", canal=False):
	"""Verdictul filmului care merge (info = iServiceInformation, cale = calea sau adresa filmului), sau None. canal:
	un canal din lista de canale (bara principala), cu frazele despre canal."""
	if info is None:
		return None
	try:
		from enigma import iServiceInformation
		motiv = info.getInfoString(iServiceInformation.sUser + 15)
		video = info.getInfoString(iServiceInformation.sTagVideoCodec)
		sunet = info.getInfoString(iServiceInformation.sTagAudioCodec)
	except Exception as e:
		print("[HdsFilmRedare] motivul nu se poate citi: %s" % e)
		return None
	return verdict(motiv, video, sunet, esteFlux(cale) or canal, canal)


def esteFilm(ref):
	"""Un serviciu redat de servicemp3 (fisier sau flux)."""
	try:
		return ref is not None and ref.type == TIP_FILM
	except Exception:
		return False


def esteFlux(cale):
	return (cale or "").lower().startswith(FLUXURI)


def textTimp(pts, lungime=None):
	"""Pozitia sau lungimea (pts, 90 kHz) ca „1:02:03” sau „2:03”; cu lungimea filmului de peste o ora, si pozitiile
	mici cu ore („0:41:01” langa „1:05:00”), ca pe televizor; „-” pentru o valoare necunoscuta."""
	if pts is None or pts < 0:
		return "-"
	s = int(pts // 90000)
	if s >= 3600 or (lungime is not None and lungime >= 3600 * 90000):
		return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)
	return "%d:%02d" % (s // 60, s % 60)

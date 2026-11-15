# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Sport azi: meciurile, cursele si galele de azi din ghidul deja primit, cu canalul si ora, fara internet.

- Canalele: cele TV din toate listele omului (buchetele din bouquets.tv), fara separatori, cel mult MAX_CANALE.
- Evenimentele: din eEPGCache, de acum pana la miezul noptii (dar cel putin ORE_MINIM ore inainte, ca seara sa se vada si
  noaptea), cerute pe loturi.
- Ce e sport: tot ce e pe un canal de sport (dupa nume) si, pe celelalte canale, emisiunile cu un cuvant de sport in titlu
  (fotbal, liga, tenis, Formula 1, handbal...). Genul DVB nu e in ghidul nostru, deci dupa nume si cuvinte.
- Aceeasi emisiune pe mai multe canale (HD, SD, alt operator) apare o data, cu celelalte canale langa.
- "In direct" dupa cuvintele din titlu sau din textul scurt (live, direct, en vivo, (L)).
Ecranul: Screens/HdsSportAzi.py; pagina web: /sport-azi (sport_azi_web.py)."""
import re
import time

MAX_CANALE = 1500
LOT = 80
ORE_MINIM = 6
MAX_RANDURI = 400

_CANAL_SPORT = re.compile(r"(?i)(sport|eurosport|\bespn|\bdazn|setanta|\bbein\b|eleven|\barena\s*(sport|fight|\d)|"
	r"\bmatch!|\bpremier\s*sports|\bmotor\s*vision|\bmotorvision|\bextreme\s*sports|\bgolf\b|\btennis\b|\bnba\s*tv|"
	r"\bnfl\s*network|\bchelsea\s*tv|\bmutv\b|\blfc\s*tv|\bfightbox|\bfight\s*sports|\bsportdigital|\bsportklub|"
	r"\bss\s*\d|\btring\s*sport|\btvp\s*sport|\bpolsat\s*sport|\bnova\s*sport|\bcosmote\s*sport|\bcanal\+\s*sport|"
	r"\bsky\s*sport|\brmc\s*sport|\bdigi\s*sport|\bprima\s*sport|\blook\s*sport|\borange\s*sport)")
_CUVINTE_SPORT = re.compile(r"(?i)\b(fotbal|football|fu(ss|ß)ball|soccer|calcio|futbol|f[uú]tbol|pi[lł]ka\s+no[zż]na|"
	r"liga\s+(1|2|i|ii|a|campionilor)|ligue\s+1|bundesliga|serie\s+a|la\s+liga|premier\s+league|superliga|ekstraklasa|"
	r"eredivisie|champions\s+league|nations\s+league|europa\s+league|conference\s+league|uefa|fifa|cupa\s+\w+|"
	r"world\s+cup|coupe\s+de|copa\s+del?|dfb-pokal|coppa\s+italia|puchar|"
	r"meci|meciul|partido|partita|derby|derbi|"
	r"tenis|tennis|atp|wta|roland\s+garros|wimbledon|us\s+open|australian\s+open|"
	r"formula\s*1|formel\s*1|f1|motogp|moto\s*gp|grand\s+prix|marele\s+premiu|nascar|indycar|wrc|raliu|rally|dakar|"
	r"baschet|basketball|basket|nba|euroleague|handbal|handball|hochei|hockey|nhl|volei|volleyball|rugby|nfl|"
	r"box(?=\s*:)|gala\s+de\s+box|box\s+profesionist|boxing|boxe|ufc|mma|kickbox|snooker|darts|ciclism|cycling|tour\s+de\s+france|giro\s+d|vuelta|"
	r"atletism|athletics|leichtathletik|schi|ski|biatlon|biathlon|s[aă]rituri|patinaj|skating|"
	r"golf|waterpolo|nata[tț]ie|swimming|olimpic|olympic|olimpiad|campionat|championship|meisterschaft|"
	r"weltmeisterschaft|mondial|euro\s+20\d\d)\b")
_DIRECT = re.compile(r"(?i)(\blive\b|\bin\s+direct\b|\bîn\s+direct\b|\bdirect\b|\bdirekt\b|\ben\s+vivo\b|\bdiretta\b|"
	r"\bna\s+żywo\b|\bna\s+zywo\b|\blive:|\(l\)|\(live\)|\(d\))")
_FARA = re.compile(r"(?i)\b(stiri|știri|news|nachrichten|telejurnal|jurnal|reclam|teleshopping|meteo|wetter)\b")


def esteCanalSport(nume):
	return bool(_CANAL_SPORT.search(nume or ""))


def esteSport(titlu, scurt=u"", canal=u""):
	"""Emisiunea e sport? Pe canalele de sport tot (in afara stirilor si reclamelor); pe celelalte, dupa titlu."""
	titlu = titlu or u""
	if not titlu.strip():
		return False
	if esteCanalSport(canal):
		return not _FARA.search(titlu)
	if _FARA.search(titlu):
		return False
	return bool(_CUVINTE_SPORT.search(titlu))


def inDirect(titlu, scurt=u""):
	return bool(_DIRECT.search(titlu or u"") or _DIRECT.search((scurt or u"")[:120]))


def sfarsitZi(acum):
	"""Miezul noptii de azi, dar cel putin ORE_MINIM ore de acum."""
	t = time.localtime(acum)
	miezul = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 23, 59, 59, 0, 0, -1)) + 1
	return int(max(miezul, acum + ORE_MINIM * 3600))


def _cheieTitlu(titlu):
	return re.sub(r"[^0-9a-z]+", u" ", (titlu or u"").lower()).strip()


def alege(evenimente, acum, sfarsit=None):
	"""evenimente: [(ref, canal, id, inceput, durata, titlu, scurt)] -> randurile de sport, in ordinea orei.
	Fiecare rand: {ref, canal, id, inceput, durata, titlu, scurt, acum, direct, alte}."""
	sfarsit = sfarsit or sfarsitZi(acum)
	unice = {}
	for ref, canal, eid, inceput, durata, titlu, scurt in evenimente:
		if not titlu or inceput is None or durata is None:
			continue
		if inceput + durata <= acum or inceput >= sfarsit:
			continue
		if not esteSport(titlu, scurt, canal):
			continue
		k = (_cheieTitlu(titlu), int(inceput) // 300)
		if k in unice:
			if canal and canal not in unice[k]["alte"] and canal != unice[k]["canal"]:
				unice[k]["alte"].append(canal)
			continue
		unice[k] = {"ref": ref, "canal": canal or u"", "id": eid, "inceput": int(inceput), "durata": int(durata),
			"titlu": titlu, "scurt": scurt or u"", "acum": inceput <= acum, "direct": inDirect(titlu, scurt), "alte": []}
	randuri = sorted(unice.values(), key=lambda r: (r["inceput"], not r["direct"], r["canal"].lower()))
	return randuri[:MAX_RANDURI]


def canaleTv():
	"""[(ref, nume)] din toate listele TV ale omului, fara dubluri si separatori."""
	from enigma import eServiceCenter, eServiceReference
	sc = eServiceCenter.getInstance()
	rez, vazute = [], set()
	radacina = sc.list(eServiceReference('1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet'))
	buchete = radacina.getContent("SN", True) if radacina else []
	for bref, bnume in buchete or []:
		lista = sc.list(eServiceReference(bref))
		for ref, nume in (lista.getContent("SN", True) if lista else []) or []:
			parti = ref.split(":")
			# steagurile: 1 = dosar (buchet), 64 = separator (si cei ascunsi sau numerotati: 320, 576, 832)
			steag = int(parti[1]) if len(parti) >= 10 and parti[1].isdigit() else 1
			if steag & 65 or ref in vazute:
				continue
			vazute.add(ref)
			rez.append((ref, nume or u""))
			if len(rez) >= MAX_CANALE:
				return rez
	return rez


def evenimente(canale, acum, sfarsit):
	"""Din eEPGCache, pe loturi: [(ref, canal, id, inceput, durata, titlu, scurt)]."""
	from enigma import eEPGCache
	epg = eEPGCache.getInstance()
	nume = dict(canale)
	minute = max(1, int((sfarsit - acum) // 60))
	rez = []
	for i in range(0, len(canale), LOT):
		cerere = ["RIBDTS"] + [(ref, 0, int(acum), minute) for ref, n in canale[i:i + LOT]]
		for e in epg.lookupEvent(cerere) or []:
			if not e or len(e) < 6 or not e[4]:
				continue
			rez.append((e[0], nume.get(e[0], u""), e[1], e[2], e[3], e[4], e[5] or u""))
	return rez


def sportAzi(acum=None):
	"""Pe firul enigma2 (eEPGCache): randurile de sport de acum pana la sfarsitul zilei."""
	acum = int(acum or time.time())
	sfarsit = sfarsitZi(acum)
	return alege(evenimente(canaleTv(), acum, sfarsit), acum, sfarsit)


def ora(t):
	return time.strftime("%H:%M", time.localtime(t))


def textRand(r):
	"""Randul din lista: ora, semnul, titlul, canalul."""
	semn = _t("ACUM") if r["acum"] else ora(r["inceput"])
	direct = u"  " + _t("în direct") if r["direct"] else u""
	alte = (u"  +%d" % len(r["alte"])) if r["alte"] else u""
	return u"%s   %s%s   %s%s" % (semn, r["titlu"], direct, r["canal"], alte)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIstoricCanale.py: lista canalelor vazute de curand (istoricul listei de canale, ChannelSelection.history, cel mult
# HISTORYSIZE = 20 de cai), din care omul alege direct un canal, fara sa apese < de mai multe ori (cererea unui tester pe
# forumul nostru, subiectul 795). Ecranul: Screens/HdsIstoricCanale.py (apasare lunga pe <, sau orice tasta din Alocarea
# tastelor cu actiunea channel_history); pagina web: HdsWebControl/istoric_web.py (/api/istoric).
#
# Partea curata (fara enigma2, se probeaza pe PC): intrari() face din istoric randurile listei, cel mai nou intai, fiecare
# canal o singura data (cea mai noua aparitie); alege() muta canalul ales la coada istoricului, ca un zap nou: < duce dupa
# aceea la canalul vazut inainte, iar canalele mai noi raman in lista (cu history_pos mutat inapoi, primul zap nou le-ar
# fi sters din istoric, ca la tastele < > pas cu pas).
# Partea enigma2: numele canalului si emisiunea de acum (randuri()), zap-ul (porneste()).

MAX_RANDURI = 20


def _cheie(cale, cheie_ref):
	try:
		return cheie_ref(cale[-1])
	except Exception:
		return None


def intrari(istoric, pozitie, cheie_ref=lambda r: r.toString()):
	"""Randurile listei din istoric (lista de cai; ultimul element al caii e canalul), cel mai nou intai.
	-> [{"index": pozitia in istoric, "cheie": referinta ca text, "acum": canalul de pe ecran}], fara dubluri."""
	vazute = set()
	rez = []
	for i in range(len(istoric) - 1, -1, -1):
		cheie = _cheie(istoric[i], cheie_ref)
		if not cheie or cheie in vazute:
			continue
		vazute.add(cheie)
		rez.append({"index": i, "cheie": cheie, "acum": False})
		if len(rez) >= MAX_RANDURI:
			break
	cheie_acum = _cheie(istoric[pozitie], cheie_ref) if 0 <= pozitie < len(istoric) else None
	for r in rez:
		r["acum"] = r["cheie"] == cheie_acum
	return rez


def rand_initial(randuri):
	"""Randul pe care sta cursorul la deschidere: primul care nu e canalul de acum (canalul de dinainte)."""
	for i, r in enumerate(randuri):
		if not r["acum"]:
			return i
	return 0


def alege(istoric, index, cheie_ref=lambda r: r.toString()):
	"""Muta calea `index` la coada istoricului (si scoate celelalte aparitii ale aceluiasi canal).
	-> pozitia noua (ultima), sau -1 cand indexul nu e bun. Lista se schimba pe loc."""
	if not 0 <= index < len(istoric):
		return -1
	ales = istoric[index]
	cheie = _cheie(ales, cheie_ref)
	istoric[:] = [c for c in istoric if c is not ales and (cheie is None or _cheie(c, cheie_ref) != cheie)]
	istoric.append(ales)
	return len(istoric) - 1


def gaseste(istoric, cheie, cheie_ref=lambda r: r.toString()):
	"""Indexul celei mai noi aparitii a canalului `cheie` in istoric, sau -1 (pentru web)."""
	for i in range(len(istoric) - 1, -1, -1):
		if _cheie(istoric[i], cheie_ref) == cheie:
			return i
	return -1


# ---------------------------------------------------------------- partea enigma2

def _lista(sesiune_sau_infobar):
	"""Lista de canale (ChannelSelection) a barei."""
	lista = getattr(sesiune_sau_infobar, "servicelist", None)
	if lista is None:
		try:
			from Screens.InfoBar import InfoBar
			lista = InfoBar.instance and InfoBar.instance.servicelist
		except Exception:
			lista = None
	return lista


def _emisiune(ref):
	try:
		from enigma import eEPGCache
		ev = eEPGCache.getInstance().lookupEventTime(ref, -1)
		return (ev and ev.getEventName() or "").strip()
	except Exception:
		return ""


def _nume(ref):
	try:
		from enigma import eServiceCenter
		info = eServiceCenter.getInstance().info(ref)
		nume = info and info.getName(ref) or ""
	except Exception:
		nume = ""
	nume = nume.replace(u"\x86", u"").replace(u"\x87", u"")   # semnele de evidentiere din numele DVB
	return nume.strip() or ref.toString()


def randuri(infobar=None):
	"""Randurile pentru ecran si web: intrari() plus numele canalului si emisiunea de acum."""
	lista = _lista(infobar)
	istoric = getattr(lista, "history", None) or []
	rez = intrari(istoric, getattr(lista, "history_pos", -1))
	for r in rez:
		ref = istoric[r["index"]][-1]
		r["nume"] = _nume(ref)
		r["emisiune"] = _emisiune(ref)
	return rez


def porneste(cheie, infobar=None):
	"""Zap pe canalul `cheie` din istoric, ca un zap nou (alege(), apoi setHistoryPath). -> True daca a pornit."""
	lista = _lista(infobar)
	istoric = getattr(lista, "history", None)
	if not istoric:
		return False
	i = gaseste(istoric, cheie)
	if i < 0:
		return False
	pos = getattr(lista, "history_pos", -1)
	if 0 <= pos < len(istoric) and _cheie(istoric[pos], lambda r: r.toString()) == cheie:
		return True   # canalul de acum: nimic de facut
	lista.history_pos = alege(istoric, i)
	lista.setHistoryPath()
	return True

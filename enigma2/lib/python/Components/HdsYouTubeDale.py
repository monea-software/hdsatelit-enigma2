# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""The tile grid of the native YouTube screen (0.8.x, YTN3), without the screen: what the PC tests use directly.

Like YouTube on a TV: every shelf of a page (the "raft" rows of Components/HdsYouTube.elemente_tv) is one row of tiles
that moves sideways; a page without shelves (Home, search results, a channel) is cut into rows of COLOANE tiles. Each
row has a strip for the shelf's title above its pictures (empty on the rows of a page without shelves).

The list widget is given only the visible rows (the list engine jumps by pages; the window moves here one row at a
time, as in Components/HdsDale.py of the tile menu), and a move inside the window redraws only the two tiles that
changed (eListbox.entryPartChanged).

Geometry at 1920x1080 (the screen scales it to the desktop), everything inside the title-safe area (5 % from each edge:
96 px left/right, 54 px top/bottom; a TV that does not show the whole picture cut the top and bottom rows);
the picture is 288x162, YouTube's 320x180 mqdefault thumbnail made smaller by the decoder. No enigma2
import here.
"""
COLOANE = 5
RANDURI_VIZIBILE = 3
MARGINE = 1                       # the next row (and the one before) stays visible while moving

# one row of the list (coordinates inside the row; the list starts at GRILA_X, GRILA_Y)
GRILA_X, GRILA_Y = 91, 106        # the list starts CHENAR px left of the first picture (its frame)
LATIME_GRILA = 1738
RAND_H = 282                      # three rows: 106-952, inside the safe area with the two lines under them
PAS_X = 360                       # tile width 288 + 72 between tiles (five tiles across the 1728 px of the safe area)
POZA_L, POZA_H = 288, 162
RAFT_Y, RAFT_H = 0, 28            # the shelf title
POZA_Y = 32
CHENAR = 5                        # the white frame around the chosen tile's picture
TITLU_Y, TITLU_H = 198, 60        # two lines of the 22 px font (a line is 1.36 x the size, lib/gdi/font.cpp)
AUTOR_Y, AUTOR_H = 258, 24
FONT_TITLU, FONT_AUTOR, FONT_RAFT, FONT_ETICHETA, FONT_MARE = 22, 20, 24, 18, 26
ETICHETA_H = 26                   # the duration / live label on the picture
REZERVA = 8                       # measured widths and the engine's may differ by a few px


def x_dala(k):
	"""left edge of the visible tile k (0..COLOANE-1) in the row"""
	return CHENAR + k * PAS_X


def zona_dala(k):
	"""(x, width) of what a tile draws, frame included: the part of the row redrawn when only this tile changed"""
	return k * PAS_X, POZA_L + 2 * CHENAR


# ---------------------------------------------------------------------------------------------------------------- rows
def construieste(elemente, coloane=COLOANE):
	"""the rows of a list of items: [{"raft": title, "dale": [items], "inceput": first visible, "polita": bool}];
	a "raft" item starts a shelf (one row, moves sideways), items outside shelves fill rows of `coloane`"""
	randuri = []
	adauga(randuri, elemente, coloane)
	return randuri


def adauga(randuri, elemente, coloane=COLOANE):
	"""more items at the end (the next page of the same list): they continue the last row when it has room"""
	for e in elemente:
		if not isinstance(e, dict):
			continue
		fel = e.get("fel")
		if fel == "mai":
			continue
		if fel == "raft":
			randuri.append({"raft": e.get("titlu") or "", "dale": [], "inceput": 0, "polita": True})
			continue
		ultim = randuri[-1] if randuri else None
		if ultim is not None and (ultim["polita"] or len(ultim["dale"]) < coloane):
			ultim["dale"].append(e)
		else:
			randuri.append({"raft": "", "dale": [e], "inceput": 0, "polita": False})
	# a shelf without tiles (all its tiles were shown already) leaves no empty row
	randuri[:] = [r for r in randuri if r["dale"]]
	return randuri


def fereastra(rand, inceput, total, vizibile=RANDURI_VIZIBILE, margine=MARGINE):
	"""the first visible row after the chosen row becomes `rand`: the window moves as little as possible, but the row
	after the chosen one stays visible (and the one before), without leaving the grid at either end"""
	m = max(0, min(margine, (vizibile - 1) // 2))
	if rand < inceput + m:
		inceput = rand - m
	elif rand > inceput + vizibile - 1 - m:
		inceput = rand - vizibile + 1 + m
	return max(0, min(inceput, max(0, total - vizibile)))


class Grila(object):
	"""the chosen tile, the window, the moves. muta() tells the screen what to redraw:
	{"fereastra": the visible rows changed (all rebuilt), "randuri": rows whose tuple changed, "dale": [(row, visible
	column)] when only these tiles need drawing, "iesire": "sus" when UP left the first row (to the tab row)}"""

	def __init__(self, elemente=(), coloane=COLOANE, vizibile=RANDURI_VIZIBILE):
		self.coloane, self.vizibile = coloane, vizibile
		self.randuri = construieste(elemente, coloane)
		self.r = self.c = 0                    # chosen row, chosen tile in it (index in the row's tiles)
		self.sus = 0                           # first visible row

	def __len__(self):
		return len(self.randuri)

	def adauga(self, elemente):
		vechi = len(self.randuri)
		adauga(self.randuri, elemente, self.coloane)
		return vechi != len(self.randuri)

	def ales(self):
		if not self.randuri:
			return None
		d = self.randuri[self.r]["dale"]
		return d[self.c] if 0 <= self.c < len(d) else None

	def raftAles(self):
		return self.randuri[self.r]["raft"] if self.randuri else ""

	def vizibile_randuri(self):
		return list(range(self.sus, min(len(self.randuri), self.sus + self.vizibile)))

	def coloana(self, r=None):
		"""the visible column (0..coloane-1) of the chosen tile"""
		r = self.r if r is None else r
		return self.c - self.randuri[r]["inceput"]

	def pune(self, r, c=0):
		"""choose a tile directly (after a list loads, or back from a channel): the window follows"""
		if not self.randuri:
			self.r = self.c = self.sus = 0
			return
		self.r = max(0, min(int(r), len(self.randuri) - 1))
		rand = self.randuri[self.r]
		self.c = max(0, min(int(c), len(rand["dale"]) - 1))
		if self.c < rand["inceput"]:
			rand["inceput"] = self.c
		elif self.c >= rand["inceput"] + self.coloane:
			rand["inceput"] = self.c - self.coloane + 1
		self.sus = fereastra(self.r, self.sus, len(self.randuri), self.vizibile)

	def puneIndex(self, i):
		"""choose the tile with index i among all the tiles (shelf titles not counted), as pozitie() gives it"""
		n = 0
		for r, rand in enumerate(self.randuri):
			if i < n + len(rand["dale"]):
				self.pune(r, max(0, i - n))
				return
			n += len(rand["dale"])
		if self.randuri:
			self.pune(len(self.randuri) - 1, len(self.randuri[-1]["dale"]) - 1)

	def aproape_de_capat(self, randuri=2):
		"""True when the chosen row is among the last `randuri`: the next page loads before the end is reached"""
		return bool(self.randuri) and self.r >= len(self.randuri) - randuri

	def capat_raft(self):
		"""True on the last tile of a shelf row"""
		return bool(self.randuri) and self.c >= len(self.randuri[self.r]["dale"]) - 1

	def muta(self, directie):
		rez = {"fereastra": False, "randuri": set(), "dale": [], "iesire": None}
		if not self.randuri:
			if directie == "sus":
				rez["iesire"] = "sus"
			return rez
		r0, c0 = self.r, self.c
		rand = self.randuri[r0]
		k0 = c0 - rand["inceput"]
		if directie in ("stanga", "dreapta"):
			c = c0 + (1 if directie == "dreapta" else -1)
			if c < 0 or c >= len(rand["dale"]):
				rez["iesire"] = directie
				return rez
			self.c = c
			rez["randuri"].add(r0)
			if c < rand["inceput"] or c >= rand["inceput"] + self.coloane:
				# the shelf moves sideways by one tile: the whole row is drawn again
				rand["inceput"] += 1 if directie == "dreapta" else -1
			else:
				rez["dale"] = [(r0, k0), (r0, c - rand["inceput"])]
			return rez
		pas = 1 if directie == "jos" else -1
		r = r0 + pas
		if r < 0:
			rez["iesire"] = "sus"
			return rez
		if r >= len(self.randuri):
			rez["iesire"] = "jos"
			return rez
		nou = self.randuri[r]
		# the same visible column on the next row (its last tile when it is shorter)
		self.r = r
		self.c = max(0, min(nou["inceput"] + k0, len(nou["dale"]) - 1))
		sus = fereastra(r, self.sus, len(self.randuri), self.vizibile)
		rez["randuri"].update((r0, r))
		if sus != self.sus:
			self.sus = sus
			rez["fereastra"] = True
		else:
			rez["dale"] = [(r0, k0), (r, self.c - nou["inceput"])]
		return rez

	def pozitie(self):
		"""(index in the whole list of items, number of items) of the chosen tile"""
		n = i = 0
		for k, rand in enumerate(self.randuri):
			if k == self.r:
				i = n + self.c
			n += len(rand["dale"])
		return i, n


# ------------------------------------------------------------------------------------------------------------- texts
class Latimi(object):
	"""text widths with one measurement per character (a hidden label on the receiver, a fixed width on the PC):
	measuring every word prefix of every title on a weak receiver is too slow, the sum of the letters is close enough
	(REZERVA covers the kerning)"""

	def __init__(self, masoara):
		self.masoara = masoara
		self.cache = {}

	def __call__(self, text):
		c = self.cache
		w = 0
		for ch in text:
			v = c.get(ch)
			if v is None:
				try:
					v = int(self.masoara(ch))
				except Exception:
					v = 0
				if v <= 0:
					v = 12
				c[ch] = v
			w += v
		return w


def rupe_titlu(text, latime, maxim, randuri=2):
	"""(the title broken on words into at most `randuri` lines joined by "\\n", cut) : cut = True when the title did not
	fit and the last line ends with "…". A word wider than the box is cut by letters."""
	cuvinte = (text or "").split()
	linii = []
	cur, wc = "", 0
	spatiu = latime(" ")
	for cuv in cuvinte:
		wc_cuv = latime(cuv)
		if cur and wc + spatiu + wc_cuv <= maxim:
			cur, wc = cur + " " + cuv, wc + spatiu + wc_cuv
			continue
		if cur:
			linii.append(cur)
			if len(linii) > randuri:
				break
		cur, wc = cuv, wc_cuv
		while wc > maxim and len(cur) > 1:
			k = len(cur) - 1
			while k > 1 and latime(cur[:k]) > maxim:
				k -= 1
			linii.append(cur[:k])
			cur = cur[k:]
			wc = latime(cur)
	if cur and len(linii) <= randuri:
		linii.append(cur)
	taiat = len(linii) > randuri
	linii = linii[:randuri]
	if taiat and linii:
		ultim = linii[-1]
		while ultim and latime(ultim + u"…") > maxim:
			ultim = ultim[:-1].rstrip()
		linii[-1] = ultim + u"…"
	return u"\n".join(linii), taiat


def taie_rand(text, latime, maxim):
	"""one line cut with "…" when wider than `maxim`"""
	text = text or ""
	if latime(text) <= maxim:
		return text
	while text and latime(text + u"…") > maxim:
		text = text[:-1]
	return text.rstrip() + u"…"


def fara_taiere(text):
	"""a no-break space before a starting J/j: the hook of the image's font goes left of the box and is cut (seen on a
	ZGEMMA: "Jocuri" drawn as "locuri"; a thin space is dropped by the text engine, a no-break space is not)"""
	return u" " + text if text and text[0] in u"Jj" else text


def eticheta_latime(text, latime):
	"""the width of the duration / live label: the text and 12 px on each side (the bold capitals measure narrow)"""
	return latime(text) + 24


def poza_dala(e):
	"""the thumbnail address of a tile: for a film always YouTube's 320x180 mqdefault (the size of the tile, nothing
	to resize; the list answers give anything from 168x94 to 480x360), else the item's own (channel, playlist)"""
	if not isinstance(e, dict):
		return ""
	if e.get("fel") == "film" and e.get("id"):
		return "https://i.ytimg.com/vi/%s/mqdefault.jpg" % e["id"]
	return e.get("poza") or ""


def detalii(e):
	"""the line under the grid for the chosen tile: the whole title, then what does not fit on the tile"""
	if not isinstance(e, dict):
		return ""
	parti = [e.get("titlu") or ""]
	for k in ("vizionari", "data"):
		if e.get(k):
			parti.append(e[k])
	return u"  ·  ".join(p for p in parti if p)


def de_descarcat(grila, extra=1):
	"""the tiles whose pictures are needed now, in order: the chosen one, its row, the other visible rows, then
	`extra` rows below the window (only the visible part of each row)"""
	if not grila.randuri:
		return []
	ordine = [grila.r] + [r for r in grila.vizibile_randuri() if r != grila.r]
	ultim = grila.sus + grila.vizibile
	ordine += [r for r in range(ultim, min(len(grila.randuri), ultim + extra))]
	gasite, vazute = [], set()
	for r in ordine:
		rand = grila.randuri[r]
		dale = rand["dale"][rand["inceput"]:rand["inceput"] + grila.coloane]
		if r == grila.r:
			k = grila.coloana()
			dale = dale[k:k + 1] + dale[:k] + dale[k + 1:]
		for e in dale:
			u = poza_dala(e)
			if u and u not in vazute:
				vazute.add(u)
				gasite.append(e)
	return gasite

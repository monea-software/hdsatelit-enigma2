# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Numele standard ale elementelor ecranelor, asteptate de temele straine intregi (OEA8, 0.7.4).

O tema scrisa pentru celelalte imagini Enigma2 aseaza elemente cu nume pe care ecranul le creeaza in Python (de pilda
<widget name="chosenletter"> in MovieSelection, <widget name="icon" pixmaps="..."> in MessageBox). Cand ecranul nostru nu
are numele, elementul temei nu se deseneaza si jurnalul scrie „component ... not found”. Aici se pun acele nume, cu
acelasi fel de componenta (Label, Pixmap, MultiPixmap, StaticText), NUMAI cand e aleasa alta tema decat HD Satelit si NUMAI
daca ecranul nu are deja numele: sub temele noastre nu se schimba nimic (nici „skin is missing element” in jurnal).
"""


def temaStraina():
	"""True cand interfata a pornit cu alta tema decat HD Satelit (skin.altSkinActiv)."""
	try:
		import skin
		return bool(skin.altSkinActiv())
	except Exception:
		return False


def adauga(ecran, nume, fabrica, ascuns=False):
	"""ecran[nume] = fabrica(), sub o tema straina, daca ecranul nu are numele; intoarce componenta pusa sau None."""
	if not temaStraina() or nume in ecran:
		return None
	try:
		componenta = fabrica()
	except Exception as e:
		print("[HdsNumeStandard] %s: %s" % (nume, e))
		return None
	ecran[nume] = componenta
	if ascuns:
		try:
			componenta.hide()
		except Exception:
			pass
	return componenta

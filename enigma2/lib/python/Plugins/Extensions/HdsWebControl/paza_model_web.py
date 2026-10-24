# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# paza_model_web.py: „Paza de model” in interfata web (HdsWebControl).
#
# Pe televizor: pe alt receptor decat cel pentru care e construita imaginea, interfata arata numai mesajul
# (Screens/HdsPazaModel.py). Aici: acelasi mesaj, in limba receptorului, si pe orice receptor amprenta dupa care s-a dat
# verdictul fata de cea ceruta de imagine (procesorul, placa, partitiile, tipul placii din driver si din eticheta), plus
# ce se arata numai informativ (eticheta intreaga din memoria receptorului, versiunea placii din driver, arborele
# dispozitivului, tunerele). Ce se citeste acum altfel decat la pornire se arata separat, sub „Citit acum”.
#
# O SINGURA LOGICA: regulile, citirea si comparatia sunt in Components/HdsPazaModel.py.
#
# Rute:
#   GET /api/paza-model   verdictul, textele si amprenta (poarta comuna a HdsJsonResource)
#   GET /paza-model       pagina, numai din reteaua locala si FARA asociere: pe alt receptor interfata de pe televizor
#                         nu porneste, deci nu se poate asocia niciun browser; pagina numai citeste si nu arata nimic
#                         secret (adresa MAC nu se citeste, jetonul nu apare).
# inPaza() e pentru panoul principal (plugin.py): pe alt receptor, in locul panoului se arata aceasta pagina. Citeste
# numai regulile si verdictul garzii din RAM (fara amprenta), fiindca panoul il cheama la fiecare cerere.
#
# FIRUL: totul ruleaza pe firul enigma2; citirea amprentei inseamna cativa KiB din /proc si din antetul partitiei
# deviceinfo (sub o milisecunda pe PC), numai pentru /paza-model si /api/paza-model. Fisierul nu importa nimic din
# enigma2 la incarcare: probele de pe PC dau modulul lor (M) si receptorul lor fals (radacina).

import re

try:
	from html import escape as _escape
except ImportError:  # Python 2 (probele vechi)
	from cgi import escape as _escape


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _m(M=None):
	if M is not None:
		return M
	from Components import HdsPazaModel
	return HdsPazaModel


def _limba():
	"""Codul limbii interfetei pentru <html lang> („ro”, „de” ...), „ro” daca nu se poate afla"""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	cod = re.sub(r"[^a-z]", "", cod)[:3]
	return cod or "ro"


def inPaza(M=None, radacina=None, cale_stare=None):
	"""True pe alt receptor (sau cu amprenta necitita): panoul arata pagina aceasta"""
	try:
		return _m(M).inPaza(radacina, cale_stare)
	except Exception as eroare:
		print("[HdsWebControl] paza de model: %s" % eroare)
		return False


def stare(M=None, radacina=None, cale_stare=None):
	"""Pentru GET /api/paza-model si pentru pagina. Randurile amprentei vin din aceeasi sursa ca verdictul (fisierul
	garzii de la pornire, cand exista); „acum” are ce se citeste acum altfel."""
	M = _m(M)
	v = M.verdict(radacina, cale_stare)
	reguli = v.get("reguli") or {}
	a = v.get("amprenta") or {}
	a_verdict = v.get("amprenta_verdict") or a
	titlu, fraze, tehnice = M.mesajStare(v)
	nep = dict((c, g) for c, _e, g in (v.get("nepotriviri") or []))
	# un model neconfirmat (treapta a doua): ce difera, dar nu opreste nimic
	avert = dict((c, g) for c, _e, g in (v.get("avertismente") or []))
	etichete = M.eticheteAmprenta()
	amprenta = []
	if v["stare"] != M.STARE_NU_SE_APLICA:
		for cheie in M.CHEI_AMPRENTA:
			if cheie == "emmc" and M.limiteEmmc(reguli) is None:
				# memoria interna se verifica numai la modelele care au limite (V20 fata de V30)
				continue
			gasit = nep[cheie] if cheie in nep else avert[cheie] if cheie in avert else M.valoareGasita(a_verdict, cheie)
			if not gasit:
				gasit = _t("lipsește (nu se verifică)") if cheie == "eticheta" else _t("nu s-a putut citi")
			amprenta.append({"cheie": cheie, "eticheta": etichete[cheie], "asteptat": M.asteptat_text(reguli, cheie),
				"gasit": gasit, "bun": cheie not in nep and cheie not in avert, "avertisment": cheie in avert})
	informativ = []
	if a:
		for eticheta, valoare in (
				(_t("Eticheta din memoria receptorului (numele din ea nu e dovadă)"), a.get("eticheta")),
				(_t("Versiunea plăcii spusă de driver (aceeași pe toate plăcile u57)"), a.get("board_revision")),
				(_t("Arborele dispozitivului"), a.get("dt")),
				(_t("Tunere"), ", ".join(a.get("tunere") or []))):
			if valoare:
				informativ.append({"eticheta": eticheta, "valoare": valoare})
	# imaginea scrisa pe receptor, cand o actualizare prin pachete a adus alta versiune (0.6.2; versiunea de acum e in
	# fraza de sus, din etc/image-version)
	if v.get("versiune_baza"):
		informativ.append({"eticheta": _t("Imaginea de bază"), "valoare": "HD Satelit %s" % v["versiune_baza"]})
	return {
		"result": True,
		"stare": v["stare"],
		"treapta": v.get("treapta", 1),
		"sursa": v.get("sursa", "acum"),
		"titlu": titlu,
		"fraze": fraze,
		"tehnice": tehnice,
		"acum": M.randuriAcum(v),
		"model": reguli.get("model", ""),
		"versiune": v.get("versiune") or reguli.get("version", ""),
		"versiune_baza": v.get("versiune_baza") or "",
		"amprenta": amprenta,
		"informativ": informativ,
	}


def rute(baza, resource, M=None, radacina=None, cale_stare=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	class StareResource(baza):
		"""GET /api/paza-model: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(M, radacina, cale_stare))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /paza-model: pagina „Paza de model”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request, M, radacina, cale_stare)

	return {b"paza-model": StareResource()}, PaginaResource()


def pagina(request, M=None, radacina=None, cale_stare=None):
	"""Numai din reteaua locala (aceeasi verificare ca panoul), fara asociere."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	try:
		date = stare(M, radacina, cale_stare)
	except Exception as eroare:
		date = {"stare": "", "titlu": _t("Paza de model"), "fraze": [_t("Receptorul nu a putut citi starea: %s") % eroare],
			"tehnice": [], "amprenta": [], "informativ": []}
	return pagina_text(P._STIL_COMUN, date, _limba()).encode("utf-8", "replace")


def _e(text):
	return _escape(u"%s" % (text or ""), True)


def _ev(text):
	"""Ca _e, cu un loc de rupere dupa fiecare virgula (listele de partitii nu au spatii)"""
	return _e(text).replace(",", ",<wbr>")


def pagina_text(stil, date, limba="ro"):
	"""Pagina facuta pe receptor, cu datele scrise direct (fara scripturi: se vede si fara asociere). Pe alt receptor
	(„nepotrivit”) „/” da tot aceasta pagina, deci legatura spre panou nu se pune."""
	clasa = {"nepotrivit": "rau", "potrivit": "bun"}.get(date.get("stare"), "neutru")
	fraze = "".join(u"<p>%s</p>" % _e(f) for f in date.get("fraze") or [])
	tehnice = "".join(u"<li>%s</li>" % _ev(t) for t in date.get("tehnice") or [])
	acum = "".join(u"<li>%s</li>" % _ev(t) for t in date.get("acum") or [])
	t_cerut, t_citit = _e(_t("Cerut de software")), _e(_t("Citit pe receptor"))
	randuri = "".join(u'<tr class="%s"><td>%s</td><td data-cap="%s">%s</td><td data-cap="%s">%s</td></tr>' % (
		"bun" if r.get("bun") else "rau", _e(r.get("eticheta")), t_cerut, _ev(r.get("asteptat")), t_citit,
		_ev(r.get("gasit"))) for r in date.get("amprenta") or [])
	info = "".join(u"<tr><td>%s</td><td>%s</td></tr>" % (_e(r.get("eticheta")), _ev(r.get("valoare")))
		for r in date.get("informativ") or [])
	amprenta = (u'<table class="amprenta"><thead><tr><th>%s</th><th>%s</th><th>%s</th></tr></thead><tbody>%s</tbody>'
		u'</table>' % (_e(_t("Ce se verifică")), t_cerut, t_citit, randuri) if randuri else
		u'<p class="nota">%s</p>' % _e(_t("Nu se verifică nimic aici.")))
	valori = {
		"STIL_COMUN": stil,
		"LIMBA": _e(limba or "ro"),
		"CLASA": clasa,
		"T_PAZA": _e(_t("Paza de model")),
		"INAPOI": u"" if date.get("stare") == "nepotrivit" else
			u'<p><a class="inapoi" href="/">%s</a></p>' % _e(_t("Înapoi la panou")),
		"T_AMPRENTA": _e(_t("Amprenta receptorului")),
		"T_NOTA": _e(_t("Amprenta se citește din procesor, din antetul de fabrică al partiției deviceinfo, din tabela "
			"partițiilor dată la pornire și din tipul plăcii (spus de driver și scris în eticheta receptorului). Numele "
			"modelului din etichetă nu intră în verificare.")),
		"INFO": (u'<section class="card"><h2>%s</h2><table><tbody>%s</tbody></table></section>' % (
			_e(_t("Numai informativ")), info)) if info else u"",
		"T_TV": _e(_t("Pe televizor: pe alt receptor, mesajul de mai sus apare singur, în locul interfeței.")),
		"TITLU": _e(date.get("titlu")),
		"FRAZE": fraze,
		"TEHNICE": u'<ul class="tehnic">%s</ul>' % tehnice if tehnice else "",
		"ACUM": (u'<p class="nota">%s</p><ul class="tehnic">%s</ul>' % (_e(_t("Citit acum, după pornire:")), acum))
			if acum else u"",
		"AMPRENTA": amprenta,
	}
	# o singura trecere: un text venit de pe receptor (de exemplu eticheta) nu poate fi luat drept semn __X__
	return re.sub(r"__([A-Z_]+)__", lambda m: valori.get(m.group(1), m.group(0)), PAGINA)


PAGINA = u"""<!DOCTYPE html>
<html lang="__LIMBA__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__T_PAZA__</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  .sus{font-size:.85rem;margin:0 0 4px;color:var(--text-slab);text-transform:uppercase;letter-spacing:.05em;}
  h1{font-size:1.45rem;line-height:1.3;margin:0 0 12px;color:var(--text);}
  h2{font-size:1rem;margin:0 0 10px;color:var(--text);}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card.rau{border-color:#f5b83d;}
  .card.bun{border-color:var(--verde);}
  .card p{font-size:1.02rem;line-height:1.5;margin:0 0 10px;}
  .card p.nota,.nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  ul.tehnic{margin:6px 0 0;padding-left:18px;color:var(--text-slab);font-size:.86rem;line-height:1.45;}
  table{width:100%;border-collapse:collapse;font-size:.9rem;}
  td,th{padding:8px 6px;border-bottom:1px solid var(--bordura);text-align:left;vertical-align:top;overflow-wrap:break-word;}
  th{color:var(--text-slab);font-weight:normal;}
  table.amprenta td:first-child{width:34%;}
  tr.rau td:last-child{color:#ffb4a8;}
  tr.bun td:last-child{color:#a8e6b4;}
  a.inapoi{color:var(--text-slab);font-size:.9rem;}
  @media (max-width:600px){
    table.amprenta thead{display:none;}
    table.amprenta tr{display:block;padding:8px 0;border-bottom:1px solid var(--bordura);}
    table.amprenta td{display:block;width:auto;border:0;padding:2px 0;}
    table.amprenta td:first-child{width:auto;font-weight:bold;}
    table.amprenta td[data-cap]::before{content:attr(data-cap) ": ";color:var(--text-slab);}
  }
</style>
</head>
<body>
<main>
__INAPOI__
<p class="sus">__T_PAZA__</p>
<section class="card __CLASA__">
  <h1>__TITLU__</h1>
  __FRAZE__
  __TEHNICE__
  __ACUM__
</section>
<section class="card">
  <h2>__T_AMPRENTA__</h2>
  __AMPRENTA__
  <p class="nota">__T_NOTA__</p>
</section>
__INFO__
<p class="nota">__T_TV__</p>
</main>
</body>
</html>
"""

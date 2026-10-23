# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLatimeText.py: lățimea în pixeli a unui text scris cu fonturile skinului HDSatelit și scurtarea lui după lățime.
#
# Listele desenate de TemplatedMultiContent și de listele din Python (rândurile ferestrei de alegere a scanerelor,
# valorile din coloana din dreapta) taie textul la marginea coloanei, fără semn. Numărul de litere nu spune cât loc
# ia un text („MMM” e de două ori mai lat ca „iii”), deci textele care pot fi lungi (nume de operatori, de regiuni, de
# copii de pe stick) se măsoară: suma avansurilor literelor, cum le așază lib/gdi/font.cpp (FreeType, cu hinting,
# fără kerning, care la fonturile acestea doar apropie literele, deci suma e cel mult cu câțiva pixeli mai mare).
#
# TABELE: pentru fiecare font și mărime folosită, avansul fiecărei litere din CARACTERE (ASCII, Latin-1, Latin
# Extended-A, ș ț cu virgulă, chirilica de bază, ghilimelele, liniuțele și „…”), în pixeli întregi, scris ca
# chr(48 + lățime). Tabelele se fac din fișierele .ttf ale skinului (HDSatelit/fonts) cu FreeType; proba
# teste/test_latime_text.py le recalculează și cade dacă fonturile se schimbă. O literă din afara tabelului se
# socotește cât cea mai lată literă a fontului, deci textul iese mai scurt decât ar trebui, niciodată tăiat.
# Mărirea fonturilor (Screens/FontSetup.py) nu schimbă aceste liste: TemplatedMultiContent și aliasul ChoiceList au
# mărimile lor fixe. Fișierul nu importă nimic din enigma2: probele de pe PC îl folosesc direct.

INTERVALE = ((0x20, 0x7E), (0xA0, 0x17F), (0x218, 0x21B), (0x400, 0x45F), (0x2013, 0x2014), (0x2018, 0x201E),
	(0x2022, 0x2022), (0x2026, 0x2026))
CARACTERE = "".join(chr(c) for a, b in INTERVALE for c in range(a, b + 1))

TABELE = {
	('HdsRegular', 32): (
		'88=EBJG799BB8:8<BBBBBBBBBB88BBB>MDEDGBAGH99DAMHICIDBBGCNBBB:<:B>9BD?DB;AD88A8NDCDD=?;D@IA@?<B<B88BBB'
		'BB@CK;@B:K@>B;;9DE87;<@HII>DDDDDDLDBBBB9999GHIIIIIBIGGGGBCDBBBBBBL?BBBB8888CDCCCCCBCDDDD@D@DBDBDBD?D'
		'?D?D?GDGDBBBBBBBBBBGAGAGAGAHDHD9898989898B@98DAAA8A8A8A8A8HDHDHDFHDICICICNND=D=D=B?B?B?B?B;B;B;GDGDG'
		'DGDGDGDNIB@BB?B?B?:B?B;BBGADB999NOGDHDGDDEAFBKCHHDGMHIGCDBDJBHFQQFKDDRDBCB>BBH?DDABGDCDD??@GADCLMFIC'
		'@KBBBD>@?888KLDAD@D@P5585;;=<I'
	),
	('HdsBold', 30): (
		'88=CAJF7::@A8:8<AAAAAAAAAA88AAA>KDDCFA@FG99C@LHHBHCAAFCLCBA:<:A=:AC?CA;AC88A8MCBCC=?<C@HA@><A<A88AAA'
		'AA?BI;AA:I?=A;;:CD86;;AHIH>DDDDDDKCAAAA9999FHHHHHHAHFFFFBBDAAAAAAK?AAAA8888BCBBBBBABCCCC@C@DADADAC?C'
		'?C?C?FCFCAAAAAAAAAAFAFAFAFAGCGC9898989898BA98CAA@8@8@8@9@8HCHCHCFHCHBHBHBLMC=C=C=A?A?A?A?A<A<A<FCFCF'
		'CFCFCFCLHB@BA>A>A>;A?A<AAG@DA999MMGCHCFDCD@FAKBHHCFLGHFBCACICGEPPEJCCPCABB>CAH@DDABHCBCC??@GADCLLEHB'
		'?JAAAC>??888JKCAD@C?N6686<<>;I'
	),
	('HdsCond', 26): (
		'67:?=D@688<=686:==========77===:D>?>@=<AA77><EAA>A>=<@>F==<8:8=;7=>;>=8<>66<6E>>>>:;8><B<<::<:=67==?'
		'=<;>F9==8F<:=997>?6599=CDD:>>>>>>D>====7777@AAAAAA=A@@@@=>?======D;====6666>>>>>>>=>>>>><><>=>=>=>;>'
		';>;>;@>@>==========A<A<A<A<A>A>7676767676>=76><<<6<6<6<7<7A>A>A>@A>A>A>A>EF>:>:>:=;=;=;=;<8<8<8@>@>@'
		'>@>@>@>FB=<=<:<:<:7=;<8==@<>=777EFA>B>@>>?<@=D>BB>@EAA@>><>C=A@GH@D>>G>=>=:>=B;??<=A>>>>;;<A<?>DE?B='
		';C===>:;;666CD><?<>=J5565::::C'
	),
	('HdsCond', 28): (
		'67;@>EA688=>787;>>>>>>>>>>77>>>;F@@?B==BB77?=GCC?C?>=B?G>>=9;9><8>?<?>9=?77=7G????:<9?=D==;:=:>67>>@'
		'>=<?G9>>8G=;>998?@769:>EFE;@@@@@@E?====7777BCCCCCC>CBBBB>?@>>>>>>E<>>>>7777???????>?????=?=@>@>@>?<?'
		'<?<?<B?B?=>=>=>=>=>B=B=B=B=B?B?7777777777?=77?===7=7=7=8=7C?C?C?AC?C?C?C?FG?:?:?:><><><><=9=9=9B?B?B'
		'?B?B?B?GD>=>=;=;=;8><=9==B=@>777GHB?C?B@?@=A=E?CC?AGBCB??=?D>BAIJAF??I@>?>;?>C<@@=>C@???<;=B=@?FF@D>'
		'<E>>>?;<<777EF?=@=?>L5575::;;E'
	),
	('HdsCond', 29): (
		'67<@?FB699>?797;??????????77???;G@A@B>=CC87@=HDC?C@>>B?H?>>9;9?=8>@<@>9>@77>7H@?@@;<9@=D==;;>;?67??@'
		'?>=@H:>?9H>;?::8@A76::>FGF;@@@@@@F@>>>>8888BDCCCCC?CBBBB>?@>>>>>>F<>>>>7777?@???????@@@@=@=@>@>@>@<@'
		'<@<@<B@B@>>>>>>>>>>C>C>C>C>C@C@8787878787?>77@>>=7=7=7=8=7D@D@D@BD@C?C?C?GH@;@;@;><><><><>9>9>9B@B@B'
		'@B@B@B@HD>=>>;>;>;8><>9>>B=@>887HHC@D?B@@A=B>F?DD@BHCCB?@>?E?CBJKBF@@J@>??;?>D<AA>?C@?@@<<=C=@@GGAD?'
		'=E>>>@;=<777EF@>A=@?M5575;;<;F'
	),
	('HdsCond', 32): (
		'78=B@HD7::?@8:8<@@@@@@@@@@88@@@<IBBAD??DE88A?JFEAEB??DAK@@?:<:@>9@A>A@:?A88?8JAAAA<=:A>G?>=<?<@78@@B'
		'@?>BK;@@:K?=@;;9BB87;;@HII<BBBBBBHA????8888DFEEEEE@EDDDD@AB@@@@@@I>@@@@8888AAAAAAA@AAAAA>A>B@B@B@A>A'
		'>A>A>DADA?@?@?@?@?@D?D?D?D?EAEA8888888888A?88A???8?8?8?9?8FAFAFADFAEAEAEAJKB<B<B<?=?=?=?=?:?:?:DADAD'
		'ADADADAKG@>@?=?=?=9?=?:??D?B?888JKDAFADBAB?D?HAFFADJEEDAA?AG@EDMMDIBBMB@A@<A@F>BB?AEBABA>=>E?BAIICF@'
		'>H@@@A<>=888HIA?B>B@P6686<<=<H'
	),
	('HdsCond', 33): (
		'78=BAID7::@A8:8<AAAAAAAAAA88AAA=JBCBE@?EE98B?KFFAFB@@EBKA@@;<;A>9@B>B@:@B88@8KBABB<>;B?G??=<@<A78AAC'
		'A@?BK;@A:K@=A;;9BC87;;@IJI=BBBBBBIB@@@@9999EFFFFFFAFEEEE@AB@@@@@@I>@@@@8888ABAAAAAABBBBB?B?B@B@B@B>B'
		'>B>B>EBEB@@@@@@@@@@E@E@E@E@EBEB9898989898A@88B@@?8?8?8?9?8FBFBFBDFBFAFAFAJKB<B<B<@>@>@>@>@;@;@;EBEBE'
		'BEBEBEBKG@?@@=@=@=9@>@;@@E?B@998KLEBFAEBBC?D@IAFFBDKEFEAB@AHAFDNNDJBBNB@AA=A@F>CC@AFBABB>=?F?CBJJCGA'
		'>H@@@B=>>888HJB@C?BAQ6686<<=<I'
	),
	('HdsCond', 36): (
		'89>DBLF8;;AB9;9>BBBBBBBBBB99BBB>LDEDGA@GG99D@MHHCHDAAGCNBBA<><B@:BD?DB;AD99A9MDCDD=?<D@IA@>=A=B89BBD'
		'BA@DN<BB;NA>B<<:DD97<<BKLL>DDDDDDKDAAAA9999GHHHHHHBHGGGGBCDBBBBBBL?BBBB9999CDCCCCCBCDDDD@D@DBDBDBD?D'
		'?D?D?GDGDABABABABABGAGAGAGAGDGD9999999999CA99DAA@9@9@9@:A9HDHDHDFHDHCHCHCMND=D=D=A?A?A?A?A<A<A<GDGDG'
		'DGDGDGDNIB@BA>A>A>:A?A<AAG@DA999NNGCHCGDCE@FAKCHHCFMGHGCDACJBHFPQFLDDPDBCB>CBH@EEACHDCDD??@HADCLMEIB'
		'@KBBBD>@?999KLDAE@DBT7797==>>K'
	),
	('HdsBold', 28): (
		'78<B@HE799?@898;@@@@@@@@@@88@@@=ICBBE@?DE98B?JFFAFB?@EAJAA@9;9@<9@A>A@:@B88@8KBAAA<>;B?G??=;?;@78@@@'
		'@?>AG:@@9G><@::9BB86:;@FGG=CCCCCCIB@@@@9999EFFFFFF@FEEEEAAC@@@@@@I>@@@@8888ABAAAAA@ABBBB?A?C@C@C@B>B'
		'>B>B>EAEB@@@@@@@@@@D@D@D@D@EBEB9898989898A@88B@@?8?8?8?9?8FBFBFBDFBFAFAFAKKB<B<B<?>?>?>?>@;@;@;EBEBE'
		'BEBEBEBJGA?A@=@=@=:?>@;@@F?B?998KKFBFBECBB?D@IAFFBDJEFEAB@BGAEDNNDIBBNB@AA=A@G?CC@AFBABA>>?E?BBJJDGA'
		'>H@@@B=>>888HIB@C?B>L5575;;=;G'
	),
	('HdsBold', 32): (
		'89>EBLH8::BB9:9<BBBBBBBBBB99BBB?MEEDGBAGH::DAMIIDIDBBHDNDCB;<;B>:CD@DB<BD99B9ODDDD>@=DAJBA?<B<B89BBB'
		'BB@CK<BB:K@>B<<:DE97<<BIJJ?EEEEEEMDBBBB::::GIIIIIIBIHHHHCDECCCCCCL@BBBB9999DDDDDDDBDDDDDADAECECECD@D'
		'@D@D@GDGDBBBBBBBBBBGBGBGBGBHDHD:9:9:9:9:9CB:9DBBA9A9A9A:A9IDIDIDGIDIDIDIDNOD>D>D>B@B@B@B@B=B=B=HDHDH'
		'DHDHDHDNJCACB?B?B?;B@B=BBIAEB:::OOIEIEHEDEAGBMDIIEGMHIHDDBEKDHGRRGLDERECCC?DBJAFFBCIEDDD@@AHBEDNNFJC'
		'@KBBBD?@@999LLDBFAE@P6686==?<J'
	),
	('HdsBold', 36): (
		'9:@GEOK9;;DE:<:>EEEEEEEEEE::EEE@PHHGJDCJK;;GDQLLFLGDDKFRFEE<><E?<EFBFE=DG::E:RGFFF@B>GCMDCA>D>E9:EEE'
		'EDBEN=DE<NB?E==<GH:8=>DLNM@HHHHHHQGDDDD;;;;JLLLLLLELKKKKEFHEEEEEEPBEEEE::::FGFFFFFEFGGGGCFCHEHEHEGBG'
		'BGBGBJFJGDEDEDEDEDEJDJDJDJDKGKG;:;:;:;:;:FD;:GEED:D:D:D;D:LGLGLGJLGLFLFLFRSG@G@G@DBDBDBDBD>D>D>KGKGK'
		'GKGKGKGRMECEEAEAEA=DBD>DDLCHD;;;SSLGMGKHGHCJDPFMMGJQKLKFGDGNFKJVWIPGGVGEFF@FEMCHHDFLGFGFBBCLDHGQRIMF'
		'BOEEEG@BB:::OPGDHCGBT77:7>>A>M'
	),
}

PUNCTE = "\u2026"   # „…”

# Randul ferestrei de alegere a scanerelor (HdsAlegereScaner, Screens/ScanerCablu.AlegereDinLista): parametrul
# HdsAlegereScanerRand din skin.xml, 1133 px, cu aliasul ChoiceList (HdsRegular 32). Randurile de sub un titlu de
# grupa incep cu INDENT.
LATIME_RAND_ALEGERE = 1133
FONT_RAND_ALEGERE = ("HdsRegular", 32)
INDENT = "   "


def _latimi(font, marime):
	"""{literă: lățime} pentru fontul și mărimea date (calculat o dată), plus lățimea celei mai late litere."""
	cheie = (font, marime)
	gata = _CACHE.get(cheie)
	if gata is None:
		text = TABELE.get(cheie)
		if text is None:
			# o mărime fără tabel: cea mai apropiată a aceluiași font, înmulțită cu raportul mărimilor
			alte = sorted((m for f, m in TABELE if f == font), key=lambda m: abs(m - marime)) or [32]
			baza = TABELE.get((font, alte[0])) or TABELE[("HdsRegular", 32)]
			raport = float(marime) / alte[0]
			latimi = [int((ord(c) - 48) * raport + 0.999) for c in baza]
		else:
			latimi = [ord(c) - 48 for c in text]
		gata = (dict(zip(CARACTERE, latimi)), max(latimi))
		_CACHE[cheie] = gata
	return gata


_CACHE = {}


def latime(text, font="HdsRegular", marime=32):
	"""Lățimea textului în pixeli, pe un singur rând."""
	tabel, maxim = _latimi(font, marime)
	return sum(tabel.get(c, maxim) for c in text or "")


def incape(text, latime_max, font="HdsRegular", marime=32):
	return latime(text, font, marime) <= latime_max


def scurteaza(text, latime_max, font="HdsRegular", marime=32):
	"""Textul întreg dacă încape; altfel tăiat la dreapta, cu „…” după ultima literă care încape (fără spațiu,
	virgulă sau paranteză deschisă chiar înaintea lui „…”)."""
	text = text or ""
	tabel, maxim = _latimi(font, marime)
	if sum(tabel.get(c, maxim) for c in text) <= latime_max:
		return text
	loc = latime_max - tabel.get(PUNCTE, maxim)
	total = 0
	taiat = 0
	for i, c in enumerate(text):
		total += tabel.get(c, maxim)
		if total > loc:
			taiat = i
			break
	return text[:taiat].rstrip(" ,;:-(\u2013") + PUNCTE


def text_incapator(nume, sufix="", latime_rand=LATIME_RAND_ALEGERE, font=FONT_RAND_ALEGERE):
	"""nume + sufix pe un rand al ferestrei de alegere, dupa INDENT: cand randul nu incape, numele se scurteaza cu
	„…”, iar sufixul (numarul de frecvente, pozitia, nota) ramane intreg."""
	loc = latime_rand - latime(INDENT, *font)
	if latime(nume + sufix, *font) <= loc:
		return nume + sufix
	return scurteaza(nume, loc - latime(sufix, *font), *font) + sufix


def fara_paranteza(text, latime_max, font="HdsRegular", marime=32):
	"""Pentru valorile care au la sfârșit o explicație în paranteză: textul întreg dacă încape, apoi fără paranteza
	de la sfârșit, apoi tăiat la dreapta (scurteaza)."""
	if incape(text, latime_max, font, marime):
		return text
	if text.endswith(")") and " (" in text:
		text = text[:text.rindex(" (")]
	return scurteaza(text, latime_max, font, marime)

/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Ecranul de pornire facut din poza utilizatorului, si semnatura scrisa peste poza de pornire.
 *
 * Drumul intreg: poza (de pe stick sau urcata din interfata web) -> suprafata 1920x1080 umpluta si
 * decupata simetric, fara deformare -> (numai daca se cere un rand: fasia de jos intunecata cat trebuie si
 * randul scris peste ea) -> codorul MPEG-2 (saveMVI din lib/gdi/emvi.h, singurul loc unde se face trecerea
 * BGRA -> planuri Y/Cb/Cr) -> fisierul cerut.
 *
 * Imaginea nu mai scrie niciun rand in poze: randul cu siturile si versiunea imaginii se deseneaza pe OSD,
 * peste poza pusa de showiframe, cat se incarca interfata (deseneazaSemnaturaPornire, la sfarsitul fisierului,
 * chemata din Components/HdsSemnaturaPornire.py). Randul scris in poza ramane pentru un text dat anume:
 * HdsRegular 34 px, centrat, literele terminate la 44 de pixeli de marginea de jos, umbra moale dedesubt,
 * fasia hotarata dupa cel mai luminos pixel de sub litere (nu dupa media benzii) si un contur intunecat
 * subtire, ca sa se citeasca peste orice poza.
 *
 * Ce s-a aflat citind codul din jur, ca sa nu se mai caute o data:
 *  - NU se foloseste ePicLoad: resizePic() incadreaza poza intreaga si lasa bare in loc sa decupeze
 *    (picload.cpp 764-785), reglajele lui se pot pune numai prin setPara(PyObject*), deci nu din C++,
 *    iar getData() numara barele de sus si de jos cu ox in loc de max_x (picload.cpp 1006 si 1045),
 *    deci la o poza si mai ingusta, si mai scunda, barele ies gresit.
 *  - loadJPG si loadPNG pot intoarce 8 biti pe pixel: poze alb-negru (epng.cpp 208) si PNG cu paleta
 *    (epng.cpp 67-68). Citirea pixelilor le trateaza anume, altfel o poza alb-negru ar iesi aiurea.
 *  - Textul se deseneaza cu eTextPara, nu cu gPainter: comenzile gPainter intra intr-o coada catre
 *    firul gRC (grc.cpp 54-92) si nu se poate astepta terminarea lor; eTextPara::blit deseneaza pe loc.
 *  - eTextPara::blit nu amesteca cu ce era dedesubt, ci scrie o culoare gata amestecata intre fundal si
 *    scris (font.cpp 736-757), deci textul se deseneaza intai pe o ciorna alba pe negru si se ia din ea
 *    numai acoperirea, din octetul rosu; acoperirea deplina acolo este 239, nu 255.
 *  - Un gDC proaspat facut are zona de taiere GOALA (grc.cpp 602-605), iar blit face
 *    "clip = dc.getClip() & area" (font.cpp 765): fara sa i se puna zona de taiere nu s-ar desena nimic.
 *  - Marimea pozei se citeste din antet (JPEG SOFn, PNG IHDR) INAINTE de decodare: o poza uriasa ar cere
 *    o alocare care poate cadea, iar un new cazut ar lua enigma2 cu el.
 *  - Pozele facute cu telefonul tinut vertical vin culcate: se intoarce dupa eticheta EXIF (picexif.cpp
 *    430-431 tine numarul 1..8 in m_exifinfo->Orient).
 */

#include <lib/gdi/ecranpornire.h>

#include <vector>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <lib/base/eerror.h>
#include <lib/gdi/emvi.h>
#include <lib/gdi/epng.h>
#include <lib/gdi/font.h>
#include <lib/gdi/gfont.h>
#include <lib/gdi/gmaindc.h>
#include <lib/gdi/grc.h>
#include <lib/gdi/mpeg2intra.h>
#include <lib/gdi/picexif.h>
#include <lib/gdi/region.h>
#include <lib/gui/ewidget.h>
#include <lib/gui/ewidgetdesktop.h>

/* marimea ecranului de pornire: aceeasi ca la ecranele gata facute si ca in antetul MPEG-2 */
static const int LATIME = mpeg2intra::LATIME;
static const int INALTIME = mpeg2intra::INALTIME;

/* randul de jos, masurat pe ecranele facute cu compune-modern.py */
static const int MARIME_FONT = 34;
static const int LITERE_DE_JOS = 44;		/* de la marginea de jos pana sub litere */
/* Ciorna in care se deseneaza randul: 96 de pixeli. NU se micsoreaza. Randul de baza al textului cade
   la inaltimea de urcare a fontului (in jur de 27 de pixeli), deci literele se termina pe la 35, iar
   umbra estompata se intinde inca vreo 15 pixeli in jurul lor: are loc si deasupra, si dedesubt. */
static const int INALTIME_FASIE = 96;
static const int RAZA_UMBRA = 5;		/* trei treceri cu raza asta = o estompare cat sigma 6 */
static const int UMBRA_TARIE = 220;
static const int TEXT_TARIE = 245;
static const int TEXT_B = 246, TEXT_G = 226, TEXT_R = 214;

/* Conturul intunecat al literelor: harta literelor latita cu un disc mic (DISC_CONTUR, mai jos) si
   amestecata spre negru. Pixelii lipiti de litere ies intotdeauna intunecati, deci literele se citesc si
   pe o poza foarte framantata (dungi, frunze, multime), nu numai pe una luminoasa. Pe o poza intunecata
   nu se vede. */
static const int CONTUR_TARIE = 255;
static const int RAZA_CONTUR = 2;

/* Fasia intunecata de sub text: numai daca poza e deschisa acolo unde cad literele si umbra lor, si numai
   cat trebuie (vezi umbreste_fasia). Culoarea si trecerea lina sunt cele din compune-modern.py. */
static const int FASIE_SUS = 160;		/* de la marginea de jos: unde incepe trecerea lina */
static const int FASIE_PLIN = 80;		/* de la marginea de jos: de unde e deplina */
static const int FASIE_B = 18, FASIE_G = 8, FASIE_R = 4;
static const int FASIE_CEL_MAI_DESCHIS = 18;	/* cel mai mare canal al culorii fasiei */
/* Cat de luminos poate ramane, dupa fasie, oricare canal al oricarui pixel din jurul literelor. Literele
   ies (205, 217, 237), cu luminanta relativa 0,687; un gri de 77 (tinta plus 1, din impartirea care taie)
   are 0,074, deci cel mai rau caz e (0,687 + 0,05) / (0,074 + 0,05) = 5,9:1, peste cele 4,5:1 cerute de
   WCAG AA. Nu 88 (4,9:1 pe hartie): codarea MPEG-2 ia literelor putin (croma pe jumatate) si adauga
   fundalului 3-4 trepte de zgomot, iar la 88 un gri uniform de 100 ajungea la televizor la 4,3:1.
   Masurat pe martori si pe cadrul desfacut. */
static const int FASIE_TINTA = 76;
/* pana unde se masoara lumina pozei in jurul literelor: cat se intinde umbra (3 treceri cu raza 5), plus 1 */
static const int MARGINE_LITERE = 3 * RAZA_UMBRA + 1;

/* peste atat nu se mai poate cere cuantizare mai buna: fisierul trebuie sa incapa in showiframe */
static const int MARIME_MAXIMA = 400 * 1024;

static const int FEL_JPEG = 1;
static const int FEL_PNG = 2;

/* acoperirea deplina a unei glife, asa cum o scrie eTextPara::blit pe 32 de biti: BLEND(0,255,240) */
static const int ACOPERIRE_PLINA = 239;

/* ------------------------------------------------------- masurarea pozei, inainte de decodare */

/* Marimea pozei, citita din antet, fara sa se decodeze nimic. Intoarce 0, sau codul din ecranpornire.h. */
static int masoara_fisierul(const char *cale, int &latime, int &inaltime, int &fel)
{
	unsigned char cap[32];
	FILE *f = fopen(cale, "rb");
	if (!f)
		return -1;
	size_t citit = fread(cap, 1, sizeof(cap), f);
	if (citit < 24)
	{
		fclose(f);
		return -2;
	}
	static const unsigned char semn_png[8] = { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A };
	if (!memcmp(cap, semn_png, sizeof(semn_png)) && !memcmp(cap + 12, "IHDR", 4))
	{
		/* citit ca unsigned: cap[16] << 24 pe int ar fi depasire cu semn (purtare nedefinita) chiar in
		   poarta de siguranta. PNG lasa pana la 2^31-1 pe latura; peste atat, refuzam. */
		unsigned int lw = ((unsigned int)cap[16] << 24) | ((unsigned int)cap[17] << 16)
			| ((unsigned int)cap[18] << 8) | cap[19];
		unsigned int lh = ((unsigned int)cap[20] << 24) | ((unsigned int)cap[21] << 16)
			| ((unsigned int)cap[22] << 8) | cap[23];
		fel = FEL_PNG;
		fclose(f);
		if (lw < 1 || lh < 1 || lw > 0x7fffffffu || lh > 0x7fffffffu)
			return -2;
		latime = (int)lw;
		inaltime = (int)lh;
		return 0;
	}
	if (cap[0] != 0xFF || cap[1] != 0xD8)
	{
		fclose(f);
		return -2;
	}
	/* JPEG: se sare din segment in segment pana la primul SOFn, care poarta marimea. Sincronizarea pe
	   marcaje e IDENTICA cu next_marker din libjpeg (jdmarker.c), altfel scanerul si decodorul ar putea
	   citi marimi diferite: un marcaj adevarat e 0xFF urmat de codul lui; octetii care nu sunt 0xFF se
	   sar, 0xFF-urile de umplutura se inghit, iar un 0x00 dupa 0xFF e octet ascuns (FF00) in datele
	   imaginii, nu un marcaj. Fara asta, un fisier facut anume ar fi pus dupa un segment octetii unui SOF
	   fals FARA 0xFF inainte, iar scanerul l-ar fi crezut pe cand libjpeg ar fi decodat alta marime, si
	   poarta s-ar fi facut pe cifre false (verificare-siguranta.md, G2a). */
	if (fseek(f, 2, SEEK_SET))
	{
		fclose(f);
		return -1;
	}
	for (;;)
	{
		int c = fgetc(f);
		while (c != 0xFF)		/* sari peste tot ce nu e 0xFF (junk dinaintea marcajului) */
		{
			if (c == EOF)
			{
				fclose(f);
				return -2;
			}
			c = fgetc(f);
		}
		do				/* inghite 0xFF-urile de umplutura dintre marcaje */
			c = fgetc(f);
		while (c == 0xFF);
		if (c == EOF)
		{
			fclose(f);
			return -2;
		}
		if (c == 0x00)
			continue;		/* FF00: octet ascuns in date, nu un marcaj */
		int marcaj = c;
		if (marcaj == 0x01 || (marcaj >= 0xD0 && marcaj <= 0xD8))
			continue;		/* TEM, RSTn, SOI: marcaje fara continut */
		if (marcaj == 0xD9 || marcaj == 0xDA)
			break;			/* EOI / SOS: a inceput poza propriu-zisa, SOFn nu mai vine */
		unsigned char lungime[2];
		if (fread(lungime, 1, 2, f) != 2)
			break;
		int lung = (lungime[0] << 8) | lungime[1];
		if (lung < 2)
			break;
		/* SOF0..SOF15 poarta marimea; C4 = DHT, C8 = JPG, CC = DAC nu sunt SOF. Progresivul e SOF2 (C2). */
		bool sofn = marcaj >= 0xC0 && marcaj <= 0xCF
			&& marcaj != 0xC4 && marcaj != 0xC8 && marcaj != 0xCC;
		if (sofn)
		{
			unsigned char masura[5];
			if (lung < 7 || fread(masura, 1, 5, f) != 5)
				break;
			inaltime = (masura[1] << 8) | masura[2];
			latime = (masura[3] << 8) | masura[4];
			fel = FEL_JPEG;
			fclose(f);
			return (latime > 0 && inaltime > 0) ? 0 : -2;
		}
		if (fseek(f, lung - 2, SEEK_CUR))
			break;
	}
	fclose(f);
	return -2;
}

/* Cum trebuie privita poza, dupa eticheta EXIF (1..8; 1 sau lipsa = asa cum e in fisier). */
static int orientarea_pozei(const char *cale, int fel)
{
	if (fel != FEL_JPEG)
		return 1;
	int orient = 1;
	Cexif exif;
	if (exif.DecodeExif(cale, 0))
	{
		if (exif.m_exifinfo->IsExif && exif.m_exifinfo->Orient >= 1 && exif.m_exifinfo->Orient <= 8)
			orient = exif.m_exifinfo->Orient;
		exif.ClearExif();
	}
	return orient;
}

/* ------------------------------------------------------- poza, adusa la marimea ecranului */

/* Un pixel din poza decodata, oricum ar fi ea: 32 de biti B,G,R,A, 8 biti cu paleta sau 8 biti gri. */
static inline void ia_pixelul(const gSurface *s, const unsigned char *rand, int x, int &b, int &g, int &r)
{
	if (s->bypp >= 4)
	{
		const unsigned char *p = rand + x * s->bypp;
		b = p[0];
		g = p[1];
		r = p[2];
		return;
	}
	int v = rand[x * s->bypp];
	if (s->clut.data && v < s->clut.colors)
	{
		b = s->clut.data[v].b;
		g = s->clut.data[v].g;
		r = s->clut.data[v].r;
		return;
	}
	b = g = r = v;
}

/* Din pozitia asa cum se vede poza (dupa EXIF) in pozitia din fisier. Cele opt orientari sunt numai
   oglindiri si rotiri de cate un sfert, deci se schimba doar indicii, fara nicio poza intermediara. */
static inline void catre_sursa(int orient, int rw, int rh, int lx, int ly, int &rx, int &ry)
{
	switch (orient)
	{
	case 2: rx = rw - 1 - lx; ry = ly; break;
	case 3: rx = rw - 1 - lx; ry = rh - 1 - ly; break;
	case 4: rx = lx; ry = rh - 1 - ly; break;
	case 5: rx = ly; ry = lx; break;
	/* 6 = "randul 0 e la dreapta, coloana 0 e sus" (telefonul tinut vertical, cea mai deasa
	   valoare); 8 = "randul 0 e la stanga, coloana 0 e jos". Nu se confunda intre ele: ar iesi
	   poza intoarsa cu 180 de grade. */
	case 6: rx = ly; ry = rh - 1 - lx; break;
	case 7: rx = rw - 1 - ly; ry = rh - 1 - lx; break;
	case 8: rx = rw - 1 - ly; ry = lx; break;
	default: rx = lx; ry = ly; break;
	}
}

static inline void ia_logic(const gSurface *ss, int orient, int rw, int rh, int lx, int ly,
	int &b, int &g, int &r)
{
	int rx = 0, ry = 0;
	catre_sursa(orient, rw, rh, lx, ly, rx, ry);
	const unsigned char *rand = ((const unsigned char *)ss->data) + (long)ry * ss->stride;
	ia_pixelul(ss, rand, rx, b, g, r);
}

/* Micsorare: fiecare pixel al ecranului e media pixelilor de poza care cad in el. Asa nu apar treptele
   si licaririle pe care le-ar da luarea unui singur pixel din patru. */
static void micsoreaza(const gSurface *ss, gSurface *ts, int orient, int rw, int rh,
	int cx, int cy, int cw, int ch)
{
	int tw = ts->x, th = ts->y;
	for (int y = 0; y < th; y++)
	{
		int ly0 = cy + (int)(((long long)y * ch) / th);
		int ly1 = cy + (int)(((long long)(y + 1) * ch) / th);
		if (ly1 <= ly0)
			ly1 = ly0 + 1;
		unsigned char *dst = ((unsigned char *)ts->data) + (long)y * ts->stride;
		for (int x = 0; x < tw; x++)
		{
			int lx0 = cx + (int)(((long long)x * cw) / tw);
			int lx1 = cx + (int)(((long long)(x + 1) * cw) / tw);
			if (lx1 <= lx0)
				lx1 = lx0 + 1;
			int rx0, ry0, rx1, ry1;
			catre_sursa(orient, rw, rh, lx0, ly0, rx0, ry0);
			catre_sursa(orient, rw, rh, lx1 - 1, ly1 - 1, rx1, ry1);
			if (rx1 < rx0) { int t = rx0; rx0 = rx1; rx1 = t; }
			if (ry1 < ry0) { int t = ry0; ry0 = ry1; ry1 = t; }
			unsigned int sb = 0, sg = 0, sr = 0, n = 0;
			for (int sy = ry0; sy <= ry1; sy++)
			{
				const unsigned char *rand = ((const unsigned char *)ss->data) + (long)sy * ss->stride;
				for (int sx = rx0; sx <= rx1; sx++)
				{
					int b, g, r;
					ia_pixelul(ss, rand, sx, b, g, r);
					sb += b;
					sg += g;
					sr += r;
					n++;
				}
			}
			unsigned char *p = dst + x * 4;
			p[0] = (unsigned char)(sb / n);
			p[1] = (unsigned char)(sg / n);
			p[2] = (unsigned char)(sr / n);
			p[3] = 0xFF;
		}
	}
}

/* Marire (poza mai mica decat ecranul): amestec intre cei patru pixeli vecini, ca sa nu iasa patratele. */
static void mareste(const gSurface *ss, gSurface *ts, int orient, int rw, int rh,
	int cx, int cy, int cw, int ch)
{
	int tw = ts->x, th = ts->y;
	for (int y = 0; y < th; y++)
	{
		long long fy = (((long long)(2 * y + 1) * ch * 32768) / th) - 32768;
		if (fy < 0)
			fy = 0;
		if (fy > ((long long)(ch - 1) << 16))
			fy = (long long)(ch - 1) << 16;
		int ly0 = (int)(fy >> 16);
		int wy = (int)(fy & 0xFFFF);
		int ly1 = (ly0 + 1 < ch) ? ly0 + 1 : ly0;
		unsigned char *dst = ((unsigned char *)ts->data) + (long)y * ts->stride;
		for (int x = 0; x < tw; x++)
		{
			long long fx = (((long long)(2 * x + 1) * cw * 32768) / tw) - 32768;
			if (fx < 0)
				fx = 0;
			if (fx > ((long long)(cw - 1) << 16))
				fx = (long long)(cw - 1) << 16;
			int lx0 = (int)(fx >> 16);
			int wx = (int)(fx & 0xFFFF);
			int lx1 = (lx0 + 1 < cw) ? lx0 + 1 : lx0;
			int b00, g00, r00, b01, g01, r01, b10, g10, r10, b11, g11, r11;
			ia_logic(ss, orient, rw, rh, cx + lx0, cy + ly0, b00, g00, r00);
			ia_logic(ss, orient, rw, rh, cx + lx1, cy + ly0, b01, g01, r01);
			ia_logic(ss, orient, rw, rh, cx + lx0, cy + ly1, b10, g10, r10);
			ia_logic(ss, orient, rw, rh, cx + lx1, cy + ly1, b11, g11, r11);
			unsigned char *p = dst + x * 4;
			p[0] = (unsigned char)((((b00 * (65536 - wx) + b01 * wx) >> 16) * (65536 - wy)
				+ ((b10 * (65536 - wx) + b11 * wx) >> 16) * wy) >> 16);
			p[1] = (unsigned char)((((g00 * (65536 - wx) + g01 * wx) >> 16) * (65536 - wy)
				+ ((g10 * (65536 - wx) + g11 * wx) >> 16) * wy) >> 16);
			p[2] = (unsigned char)((((r00 * (65536 - wx) + r01 * wx) >> 16) * (65536 - wy)
				+ ((r10 * (65536 - wx) + r11 * wx) >> 16) * wy) >> 16);
			p[3] = 0xFF;
		}
	}
}

/* Poza umple tot ecranul, fara deformare: se pastreaza bucata de 16:9 din mijloc, iar ce depaseste se
   taie in parti egale. Asa face si unealta de pe calculator (compune-modern.py), nu bare negre. */
static void umple_si_decupeaza(gPixmap &sursa, gPixmap &tinta, int orient)
{
	const gSurface *ss = sursa.surface;
	gSurface *ts = tinta.surface;
	int rw = ss->x, rh = ss->y;
	int lw = (orient >= 5) ? rh : rw;	/* marimea asa cum se vede poza */
	int lh = (orient >= 5) ? rw : rh;
	int tw = ts->x, th = ts->y;
	int cw = lw, ch = lh;
	if ((long long)lw * th > (long long)lh * tw)
		cw = (int)(((long long)lh * tw) / th);	/* mai lata: se taie din stanga si din dreapta */
	else
		ch = (int)(((long long)lw * th) / tw);	/* mai inalta: se taie de sus si de jos */
	if (cw < 1)
		cw = 1;
	if (ch < 1)
		ch = 1;
	int cx = (lw - cw) / 2, cy = (lh - ch) / 2;
	if (cw >= tw)
		micsoreaza(ss, ts, orient, rw, rh, cx, cy, cw, ch);
	else
		mareste(ss, ts, orient, rw, rh, cx, cy, cw, ch);
}

/* ------------------------------------------------------- fasia de jos si randul de jos */

/* Fasia de jos se intuneca numai daca poza e deschisa CHIAR ACOLO unde cad literele si umbra lor
   (dreptunghiul x0..x1, y0..y1 de pe ecran), si numai atat cat sa se citeasca randul.
   Se ia cel mai luminos canal al ORICARUI pixel din dreptunghi, nu media: o pata luminoasa exact sub
   litere (o lampa, zapada, un perete alb) nu misca media unei benzi intunecate, dar sterge literele (masurat:
   1,26:1 cu media). Nici o medie pe petice nu ajunge: la dungi fine
   alb-negru media e 127, dar jumatate din pixelii de langa litere sunt albi.
   Canalul cel mai mare, nu luma BT.601: un verde curat are luma 149, dar se vede mult mai luminos. Daca
   toate canalele ajung sub FASIE_TINTA, orice culoare ajunge acolo.
   Taria se socoteste din tinta: cat trebuie amestecat spre culoarea fasiei ca cel mai luminos canal sa
   coboare la FASIE_TINTA. Sub tinta nu se pune nimic; peste ea, exact cat trebuie. Pe calculator marginea
   de sus a fasiei e estompata cu o gaussiana; aici e o trecere lina, care se vede la fel. */
static void umbreste_fasia(gSurface *s, int x0, int y0, int x1, int y1)
{
	int inaltime = s->y, latime = s->x;
	if (x0 < 0)
		x0 = 0;
	if (y0 < 0)
		y0 = 0;
	if (x1 > latime - 1)
		x1 = latime - 1;
	if (y1 > inaltime - 1)
		y1 = inaltime - 1;
	int varf = 0;
	for (int y = y0; y <= y1; y++)
	{
		const unsigned char *rand = ((const unsigned char *)s->data) + (long)y * s->stride;
		for (int x = x0; x <= x1; x++)
		{
			const unsigned char *p = rand + x * 4;
			if (p[0] > varf)
				varf = p[0];
			if (p[1] > varf)
				varf = p[1];
			if (p[2] > varf)
				varf = p[2];
		}
	}
	if (varf <= FASIE_TINTA)
		return;
	/* rotunjit in sus; amestecul de mai jos taie spre zero, deci canalul iese cel mult cu 1 peste tinta */
	int tarie = (255 * (varf - FASIE_TINTA) + (varf - FASIE_CEL_MAI_DESCHIS) - 1)
		/ (varf - FASIE_CEL_MAI_DESCHIS);
	if (tarie > 255)
		tarie = 255;
	/* literele si umbra lor stau toate in partea deplina: daca dreptunghiul incepe mai sus, urca si
	   trecerea lina */
	int plin = inaltime - FASIE_PLIN;
	if (y0 < plin)
		plin = y0;
	int sus = plin - (FASIE_SUS - FASIE_PLIN);
	if (sus < 0)
		sus = 0;
	for (int y = sus; y < inaltime; y++)
	{
		int a = (y >= plin) ? tarie : tarie * (y - sus) / (plin - sus);
		if (a <= 0)
			continue;
		unsigned char *rand = ((unsigned char *)s->data) + (long)y * s->stride;
		for (int x = 0; x < latime; x++)
		{
			unsigned char *p = rand + x * 4;
			p[0] = (unsigned char)(p[0] + (FASIE_B - p[0]) * a / 255);
			p[1] = (unsigned char)(p[1] + (FASIE_G - p[1]) * a / 255);
			p[2] = (unsigned char)(p[2] + (FASIE_R - p[2]) * a / 255);
		}
	}
}

/* Estompare: trei treceri cu media pe o fereastra, cat o gaussiana de sigma 6, ca umbra textului sa fie
   moale si pe o poza incarcata. */
static void estompeaza(unsigned char *harta, unsigned char *ajutor, int latime, int inaltime, int raza)
{
	int fereastra = 2 * raza + 1;
	for (int trecere = 0; trecere < 3; trecere++)
	{
		for (int y = 0; y < inaltime; y++)
		{
			const unsigned char *rand = harta + (long)y * latime;
			unsigned char *iesire = ajutor + (long)y * latime;
			int suma = 0;
			for (int x = -raza; x <= raza; x++)
				suma += rand[x < 0 ? 0 : (x >= latime ? latime - 1 : x)];
			for (int x = 0; x < latime; x++)
			{
				iesire[x] = (unsigned char)(suma / fereastra);
				int iese = x - raza, intra = x + raza + 1;
				suma -= rand[iese < 0 ? 0 : iese];
				suma += rand[intra >= latime ? latime - 1 : intra];
			}
		}
		for (int x = 0; x < latime; x++)
		{
			int suma = 0;
			for (int y = -raza; y <= raza; y++)
				suma += ajutor[(long)(y < 0 ? 0 : (y >= inaltime ? inaltime - 1 : y)) * latime + x];
			for (int y = 0; y < inaltime; y++)
			{
				harta[(long)y * latime + x] = (unsigned char)(suma / fereastra);
				int iese = y - raza, intra = y + raza + 1;
				suma -= ajutor[(long)(iese < 0 ? 0 : iese) * latime + x];
				suma += ajutor[(long)(intra >= inaltime ? inaltime - 1 : intra) * latime + x];
			}
		}
	}
}

/* Discul cu care se lateste harta literelor ca sa iasa conturul: deplasarea si greutatea (din 256).
   Plin pana la un pixel si jumatate de marginea literei, apoi o margine moale pana la RAZA_CONTUR, ca
   marginea conturului sa nu iasa in trepte. */
struct PunctDisc
{
	int dx, dy, greutate;
};
static const PunctDisc DISC_CONTUR[] = {
	{ 0, 0, 256 }, { -1, 0, 256 }, { 1, 0, 256 }, { 0, -1, 256 }, { 0, 1, 256 },
	{ -1, -1, 256 }, { 1, -1, 256 }, { -1, 1, 256 }, { 1, 1, 256 },
	{ -2, 0, 128 }, { 2, 0, 128 }, { 0, -2, 128 }, { 0, 2, 128 },
	{ -2, -1, 64 }, { -2, 1, 64 }, { 2, -1, 64 }, { 2, 1, 64 },
	{ -1, -2, 64 }, { 1, -2, 64 }, { -1, 2, 64 }, { 1, 2, 64 },
};

/* Randul de jos, centrat. Textul se deseneaza intai singur, alb pe negru, pe o ciorna deoparte, pentru
   ca eTextPara::blit nu amesteca cu ce era dedesubt (font.cpp 736-757): desenat de-a dreptul peste poza
   ar lasa un contur de culoarea fundalului dat. Din ciorna se ia numai cat de tare acopera literele
   fiecare pixel (harta), si cu ea se pune peste poza, in ordine: fasia (masurata sub litere), umbra
   moale, conturul intunecat, textul. */
static int scrie_randul_de_jos(gPixmap &ecran, const std::string &text)
{
	if (!fontRenderClass::getInstance())
	{
		eDebug("[EcranPornire] the font engine is not up");
		return -6;
	}
	gSurface *es = ecran.surface;
	ePtr<gPixmap> ciorna = new gPixmap(eSize(es->x, INALTIME_FASIE), 32);
	gSurface *cs = ciorna->surface;
	memset(cs->data, 0, (size_t)cs->stride * cs->y);

	ePtr<gDC> dc = new gDC(ciorna);
	dc->getClip() = gRegion(eRect(0, 0, cs->x, cs->y));	/* un gDC nou are zona de taiere goala */

	ePtr<eTextPara> para = new eTextPara(eRect(0, 0, cs->x, cs->y));
	ePtr<gFont> font = new gFont("HdsRegular", MARIME_FONT);
	para->setFont(font);
	if (para->renderString(text.c_str(), 0) < 0)
	{
		/* skinul nostru inregistreaza si numele obisnuit; un skin strain poate sa nu aiba HdsRegular */
		para = new eTextPara(eRect(0, 0, cs->x, cs->y));
		font = new gFont("Regular", MARIME_FONT);
		para->setFont(font);
		if (para->renderString(text.c_str(), 0) < 0)
		{
			eDebug("[EcranPornire] no font for the bottom line");
			return -6;
		}
	}
	para->realign(eTextPara::dirCenter);
	para->blit(*dc, ePoint(0, 0), gRGB(0, 0, 0, 255), gRGB(255, 255, 255, 255));

	eRect litere = para->getBoundBox();
	if (litere.height() <= 0 || litere.width() <= 0)
		return -6;
	int deplasare = (es->y - LITERE_DE_JOS) - litere.bottom();

	int pixeli = cs->x * cs->y;
	std::vector<unsigned char> harta(pixeli), umbra(pixeli), ajutor(pixeli);
	/* dreptunghiul literelor se ia din acoperire, cu marginea moale a literelor cu tot */
	int lx0 = cs->x, ly0 = cs->y, lx1 = -1, ly1 = -1;
	for (int y = 0; y < cs->y; y++)
	{
		const unsigned char *rand = ((const unsigned char *)cs->data) + (long)y * cs->stride;
		unsigned char *iesire = &harta[(long)y * cs->x];
		for (int x = 0; x < cs->x; x++)
		{
			int a = rand[x * 4 + 2] * 255 / ACOPERIRE_PLINA;	/* scrisul e alb: acoperirea e in rosu */
			iesire[x] = (unsigned char)(a > 255 ? 255 : a);
			if (a)
			{
				if (x < lx0)
					lx0 = x;
				if (x > lx1)
					lx1 = x;
				if (y < ly0)
					ly0 = y;
				ly1 = y;
			}
		}
	}
	if (lx1 < 0)
	{
		eDebug("[EcranPornire] the bottom line drew no pixels");
		return -6;
	}

	/* fasia se masoara unde cad pe ecran literele si umbra lor (ciorna are latimea ecranului) */
	umbreste_fasia(es, lx0 - MARGINE_LITERE, ly0 + deplasare - MARGINE_LITERE,
		lx1 + MARGINE_LITERE, ly1 + deplasare + MARGINE_LITERE);

	umbra = harta;
	estompeaza(&umbra[0], &ajutor[0], cs->x, cs->y, RAZA_UMBRA);

	/* conturul se face in "ajutor", de care estomparea nu mai are nevoie: harta latita cu DISC_CONTUR,
	   numai in jurul literelor */
	std::vector<unsigned char> &contur = ajutor;
	memset(&contur[0], 0, (size_t)pixeli);
	int puncte = (int)(sizeof(DISC_CONTUR) / sizeof(DISC_CONTUR[0]));
	int cy0 = ly0 - RAZA_CONTUR < 0 ? 0 : ly0 - RAZA_CONTUR;
	int cy1 = ly1 + RAZA_CONTUR >= cs->y ? cs->y - 1 : ly1 + RAZA_CONTUR;
	int cx0 = lx0 - RAZA_CONTUR < 0 ? 0 : lx0 - RAZA_CONTUR;
	int cx1 = lx1 + RAZA_CONTUR >= cs->x ? cs->x - 1 : lx1 + RAZA_CONTUR;
	for (int y = cy0; y <= cy1; y++)
	{
		unsigned char *iesire = &contur[(long)y * cs->x];
		for (int x = cx0; x <= cx1; x++)
		{
			int cel_mai_mare = 0;
			for (int k = 0; k < puncte; k++)
			{
				int sx = x + DISC_CONTUR[k].dx, sy = y + DISC_CONTUR[k].dy;
				if (sx < 0 || sy < 0 || sx >= cs->x || sy >= cs->y)
					continue;
				int v = harta[(long)sy * cs->x + sx] * DISC_CONTUR[k].greutate / 256;
				if (v > cel_mai_mare)
					cel_mai_mare = v;
			}
			iesire[x] = (unsigned char)cel_mai_mare;
		}
	}

	for (int y = 0; y < cs->y; y++)
	{
		int ey = y + deplasare;
		if (ey < 0 || ey >= es->y)
			continue;
		unsigned char *rand = ((unsigned char *)es->data) + (long)ey * es->stride;
		const unsigned char *mu = &umbra[(long)y * cs->x];
		const unsigned char *mc = &contur[(long)y * cs->x];
		const unsigned char *mt = &harta[(long)y * cs->x];
		for (int x = 0; x < cs->x && x < es->x; x++)
		{
			unsigned char *p = rand + x * 4;
			int a = mu[x] * UMBRA_TARIE / 255;
			if (a)
			{
				p[0] = (unsigned char)(p[0] - p[0] * a / 255);
				p[1] = (unsigned char)(p[1] - p[1] * a / 255);
				p[2] = (unsigned char)(p[2] - p[2] * a / 255);
			}
			a = mc[x] * CONTUR_TARIE / 255;
			if (a)
			{
				p[0] = (unsigned char)(p[0] - p[0] * a / 255);
				p[1] = (unsigned char)(p[1] - p[1] * a / 255);
				p[2] = (unsigned char)(p[2] - p[2] * a / 255);
			}
			a = mt[x] * TEXT_TARIE / 255;
			if (a)
			{
				p[0] = (unsigned char)(p[0] + (TEXT_B - p[0]) * a / 255);
				p[1] = (unsigned char)(p[1] + (TEXT_G - p[1]) * a / 255);
				p[2] = (unsigned char)(p[2] + (TEXT_R - p[2]) * a / 255);
			}
		}
	}
	return 0;
}

/* ------------------------------------------------------- functiile chemate din Python */

int pregatesteEcranPornire(ePtr<gPixmap> &iesire, const std::string &poza, const std::string &rand_de_jos)
{
	iesire = 0;
	int latime = 0, inaltime = 0, fel = 0;
	int stare = masoara_fisierul(poza.c_str(), latime, inaltime, fel);
	if (stare)
		return stare;
	if ((long long)latime * inaltime > (long long)ECRAN_PORNIRE_MAXIM_PIXELI)
	{
		eDebug("[EcranPornire] %s is %dx%d, too big to decode", poza.c_str(), latime, inaltime);
		return -3;
	}
	/* enigma2 se compileaza cu -fno-exceptions, deci o alocare cazuta nu se poate prinde, ci opreste
	   receptorul; de aceea poarta de mai sus opreste pozele prea mari INAINTE de a se cere memoria. */
	ePtr<gPixmap> sursa;
	if (fel == FEL_JPEG)
		loadJPG(sursa, poza.c_str());
	else
		loadPNG(sursa, poza.c_str());
	if (!sursa || !sursa->surface || !sursa->surface->data
		|| sursa->surface->x < 1 || sursa->surface->y < 1)
		return -4;
	/* A doua poarta: dupa decodare, marimea ADEVARATA a pozei (data de libjpeg / libpng), nu cea citita
	   din antet de masoara_fisierul. Daca cele doua nu se potrivesc (un JPEG facut anume ca sa pacaleasca
	   scanerul din antet), oprim AICI, inainte de gPixmap-ul ecranului si de prelucrare. */
	if ((long long)sursa->surface->x * sursa->surface->y > (long long)ECRAN_PORNIRE_MAXIM_PIXELI)
	{
		eDebug("[EcranPornire] %s decoded to %dx%d, over the pixel limit", poza.c_str(),
			sursa->surface->x, sursa->surface->y);
		return -3;
	}
	ePtr<gPixmap> ecran = new gPixmap(eSize(LATIME, INALTIME), 32);
	umple_si_decupeaza(*sursa, *ecran, orientarea_pozei(poza.c_str(), fel));
	sursa = 0;				/* poza intreaga nu mai trebuie: se elibereaza acum */
	/* Textul gol inseamna poza fara niciun rand scris in ea: randul cu siturile si versiunea il scrie interfata
	   peste poza, la pornire (deseneazaSemnaturaPornire, mai jos). Un text dat se scrie jos, centrat, cu fasia
	   pusa de scrie_randul_de_jos dupa ce stie unde cad literele. */
	if (!rand_de_jos.empty())
	{
		stare = scrie_randul_de_jos(*ecran, rand_de_jos);
		if (stare)
			return stare;
	}
	iesire = ecran;
	return 0;
}

/* Conversia propriu-zisa: poza -> suprafata 1920x1080 -> cadru I MPEG-2 in fisierul cerut. */
static int fa_ecran_pornire(const std::string &poza, const std::string &fisier, const std::string &rand_de_jos,
	int cod_cuantizare)
{
	ePtr<gPixmap> ecran;
	int stare = pregatesteEcranPornire(ecran, poza, rand_de_jos);
	if (stare)
		return stare;
	if (cod_cuantizare < 1)
		cod_cuantizare = 1;
	if (cod_cuantizare > 31)
		cod_cuantizare = 31;

	/* Bucla merge pana cand fisierul intra sub MARIME_MAXIMA sau pana cand cuantizarea ajunge la 31 (cea
	   mai aspra). showiframe primeste fisierul intreg in memorie, iar o poza cu mult detaliu (iarba,
	   frunze, multime, zapada batuta de soare) da un fisier mult mai mare decat ecranele noastre
	   desenate. La fiecare pas cuantizarea se dubleaza (4 -> 8 -> 16 -> 31), deci cel mult patru treceri
	   de la pornirea obisnuita. Daca nici la 31 nu incape, NU lasam un fisier peste prag pe disc:
	   showiframe l-ar putea refuza si receptorul ar porni fara ecran; il stergem si refuzam. Trecerea
	   BGRA -> planuri se face din nou la fiecare incercare, inauntrul lui saveMVI, dar e o plimbare
	   liniara peste pixeli, mult mai ieftina decat codarea. */
	for (;;)
	{
		int raspuns = saveMVI(fisier.c_str(), ecran, cod_cuantizare);
		if (raspuns)
		{
			eDebug("[EcranPornire] saveMVI answered %d (quantiser code %d)", raspuns, cod_cuantizare);
			return (raspuns == -7 || raspuns == -8) ? -8 : -7;
		}
		struct stat masura;
		if (stat(fisier.c_str(), &masura))
			return -8;
		if ((long long)masura.st_size <= MARIME_MAXIMA)
		{
			eDebug("[EcranPornire] %s: %d bytes, quantiser code %d", fisier.c_str(),
				(int)masura.st_size, cod_cuantizare);
			return 0;
		}
		if (cod_cuantizare >= 31)
		{
			/* nici la cuantizarea cea mai aspra nu incape: nu lasam un fisier peste prag pe disc */
			eDebug("[EcranPornire] %s: %d bytes even at quantiser code 31, over %d; refusing",
				fisier.c_str(), (int)masura.st_size, MARIME_MAXIMA);
			unlink(fisier.c_str());
			return -9;
		}
		int urmator = cod_cuantizare * 2;
		if (urmator > 31)
			urmator = 31;
		eDebug("[EcranPornire] %d bytes at quantiser code %d, trying %d",
			(int)masura.st_size, cod_cuantizare, urmator);
		cod_cuantizare = urmator;
	}
}

int faEcranPornire(const std::string &poza, const std::string &fisier, const std::string &rand_de_jos,
	int cod_cuantizare)
{
	/* Se cheama din Python, de pe un fir separat (ecranul de pe televizor, interfata web). Legaturile SWIG se fac cu
	   -nothreads, deci fara pasul de mai jos GIL-ul ar ramane luat toata conversia (secunde pe ARM), iar firul
	   enigma2 (tastele, ceasurile, web-ul) ar astepta dupa ea. Fara text de scris in poza (cum le face imaginea
	   acum), nimic din conversie nu atinge Python sau motorul de fonturi al interfetei: decodarea, aducerea la
	   1920x1080, codarea si scrierea fisierului lucreaza numai cu memoria lor, iar eDebug merge din orice fir. Deci
	   GIL-ul se elibereaza cat tine conversia. Cu un text dat, scrie_randul_de_jos foloseste fontRenderClass, pe
	   care il foloseste si firul enigma2 cand deseneaza: atunci GIL-ul ramane luat, ca pana acum. La fel cand
	   functia e chemata fara GIL (din C++). */
	if (!rand_de_jos.empty() || !Py_IsInitialized() || !PyGILState_Check())
		return fa_ecran_pornire(poza, fisier, rand_de_jos, cod_cuantizare);
	int stare;
	Py_BEGIN_ALLOW_THREADS
	stare = fa_ecran_pornire(poza, fisier, rand_de_jos, cod_cuantizare);
	Py_END_ALLOW_THREADS
	return stare;
}

/* ------------------------------------------------------- semnatura de pe poza de pornire */

/* Masurile semnaturii, pe un ecran de 1920x1080: capsula intunecata, pe jumatate straveziei, cu textul centrat in
   ea, centrata jos. Pe alt OSD (720x576 inainte de incarcarea skinului, 1280x720) capsula se face la aceste masuri
   si se pune micsorata, deci dupa ce placa video intinde OSD-ul pe tot ecranul arata la fel. */
static const int SEMN_FONT = 30;
static const int SEMN_INALTIME = 56;
static const int SEMN_MARGINE_TEXT = 32;	/* stanga si dreapta textului, in capsula */
static const int SEMN_JOS = 40;			/* de la marginea de jos a ecranului pana sub capsula */
static const int SEMN_LATIME_MAXIMA = 1800;
static const int SEMN_FUNDAL_R = 10, SEMN_FUNDAL_G = 14, SEMN_FUNDAL_B = 26;
static const int SEMN_FUNDAL_OPAC = 184;	/* 0 stravezie, 255 plina */
static const int SEMN_TEXT_R = 240, SEMN_TEXT_G = 246, SEMN_TEXT_B = 252;

/* locul ultimei semnaturi pe OSD, ca ascundeSemnaturaPornire() sa ceara redesenarea numai acolo */
static eRect semnatura_zona;

/* Textul asezat pe un rand, cu primul font care il poate scrie: aliasul inregistrat de Components/HdsSemnaturaPornire.py
   (HdsSemnatura), apoi fontul obisnuit al skinului (Regular). */
static ePtr<eTextPara> semnatura_text(const std::string &text, int latime, int inaltime)
{
	static const char *fonturi[] = { "HdsSemnatura", "Regular" };
	for (unsigned int i = 0; i < sizeof(fonturi) / sizeof(fonturi[0]); i++)
	{
		ePtr<eTextPara> para = new eTextPara(eRect(0, 0, latime, inaltime));
		ePtr<gFont> font = new gFont(fonturi[i], SEMN_FONT);
		para->setFont(font);
		if (para->renderString(text.c_str(), 0) >= 0 && para->getBoundBox().width() > 0)
			return para;
	}
	return 0;
}

/* Cat din pixelul (x, y) cade in dreptunghiul cu colturi rotunde latime x inaltime, raza r (0..256): marginea
   rotunjita e netezita pe o jumatate de pixel. */
static int acoperire_capsula(int x, int y, int latime, int inaltime, int r)
{
	int cx = x < r ? r : (x >= latime - r ? latime - r - 1 : x);
	int cy = y < r ? r : (y >= inaltime - r ? inaltime - r - 1 : y);
	if (cx == x || cy == y)
		return 256;
	float dx = (float)x + 0.5f - ((float)cx + 0.5f), dy = (float)y + 0.5f - ((float)cy + 0.5f);
	float d = sqrtf(dx * dx + dy * dy);
	float a = (float)r - d + 0.5f;
	if (a <= 0.0f)
		return 0;
	if (a >= 1.0f)
		return 256;
	return (int)(a * 256.0f);
}

int deseneazaSemnaturaPornire(const std::string &text)
{
	if (text.empty())
		return -1;
	if (!fontRenderClass::getInstance())
		return -6;
	ePtr<gMainDC> dc;
	if (gMainDC::getInstance(dc) || !dc)
		return -1;
	eSize ecran = dc->size();
	if (ecran.width() < 64 || ecran.height() < 64)
		return -1;

	ePtr<eTextPara> para = semnatura_text(text, SEMN_LATIME_MAXIMA, SEMN_INALTIME);
	if (!para)
	{
		eDebug("[EcranPornire] no font for the start signature");
		return -6;
	}
	eRect litere = para->getBoundBox();
	int latime = litere.width() + 2 * SEMN_MARGINE_TEXT;
	if (latime > SEMN_LATIME_MAXIMA)
		latime = SEMN_LATIME_MAXIMA;

	/* capsula, la masurile pentru 1920x1080: fundalul cu colturi rotunde, scris de-a dreptul in pixeli (ARGB pe
	   32 de biti, alfa 255 = plin) */
	ePtr<gPixmap> capsula = new gPixmap(eSize(latime, SEMN_INALTIME), 32);
	gSurface *cs = capsula->surface;
	for (int y = 0; y < cs->y; y++)
	{
		unsigned int *rand = (unsigned int *)(((unsigned char *)cs->data) + (long)y * cs->stride);
		for (int x = 0; x < cs->x; x++)
		{
			int a = SEMN_FUNDAL_OPAC * acoperire_capsula(x, y, cs->x, cs->y, SEMN_INALTIME / 2) / 256;
			rand[x] = ((unsigned int)a << 24) | (SEMN_FUNDAL_R << 16) | (SEMN_FUNDAL_G << 8) | SEMN_FUNDAL_B;
		}
	}

	/* textul, centrat in capsula: eTextPara::blit scrie direct in pixeli culoarea amestecata intre fundal si scris,
	   cu tot cu alfa (font.cpp, bpp 32), deci fundalul dat e chiar culoarea capsulei (gRGB: alfa 0 = plin) */
	ePtr<eTextPara> asezat = semnatura_text(text, latime, SEMN_INALTIME);
	if (!asezat)
		return -6;
	asezat->realign(eTextPara::dirCenter);
	eRect cutie = asezat->getBoundBox();
	ePtr<gDC> cdc = new gDC(capsula);
	cdc->getClip() = gRegion(eRect(0, 0, cs->x, cs->y));	/* un gDC nou are zona de taiere goala */
	int dy = (SEMN_INALTIME - cutie.height()) / 2 - cutie.top();
	asezat->blit(*cdc, ePoint(0, dy),
		gRGB(SEMN_FUNDAL_R, SEMN_FUNDAL_G, SEMN_FUNDAL_B, 255 - SEMN_FUNDAL_OPAC),
		gRGB(SEMN_TEXT_R, SEMN_TEXT_G, SEMN_TEXT_B, 0));

	/* pe OSD, jos, centrat, la scara OSD-ului de acum */
	int w = latime * ecran.width() / LATIME;
	int h = SEMN_INALTIME * ecran.height() / INALTIME;
	int x = (ecran.width() - w) / 2;
	int y = ecran.height() - (SEMN_JOS + SEMN_INALTIME) * ecran.height() / INALTIME;
	eRect zona(x, y, w, h);
	gPainter p(dc);
	p.resetClip(gRegion(eRect(ePoint(0, 0), ecran)));
	if (w == latime && h == SEMN_INALTIME)
		p.blit(capsula, ePoint(x, y));
	else
		p.blitScale(capsula, zona);
	p.flush();
	semnatura_zona = zona;
	eDebug("[EcranPornire] start signature at %d,%d %dx%d on a %dx%d OSD", x, y, w, h, ecran.width(), ecran.height());
	return 0;
}

void ascundeSemnaturaPornire()
{
	if (semnatura_zona.empty())
		return;
	eWidgetDesktop *desktop = getDesktop(0);
	if (desktop)
		desktop->invalidate(gRegion(semnatura_zona));
	semnatura_zona = eRect();
}

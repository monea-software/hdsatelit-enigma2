/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/gui/esubtitle.h>
#include <lib/gdi/grc.h>
#include <lib/gdi/font.h>
#include <lib/base/eerror.h>

#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/*
 * Subtitrarile TEXT (teletext, subtitrarile din fisiere si textul citit din subtitrarile DVB).
 *
 * Inainte, textul se scria cu painter.renderText, iar „umbra" era acelasi text, negru, mutat cu shadow_offset
 * (skin.py face din borderWidth=3 un shadowOffset 3,3). Comenzile gPainter merg printr-o coada catre firul gRC
 * (grc.cpp), deci pixelii nu se pot lua inapoi pentru o umbra estompata. Acum, ca la randul de jos al ecranului
 * de pornire (lib/gdi/ecranpornire.cpp), pagina se compune o singura data, cand vine (setPage), intr-o poza ARGB
 * a ei: fundalul randurilor (la alegere), umbra moale, conturul si literele. La desenare (evtPaint) se pune numai
 * poza: copie pe fereastra subtitrarilor (curatata transparent chiar inainte), amestec pe un widget transparent
 * (cel al previzualizarii din setari, peste ce e in spatele lui).
 *
 * Ce s-a aflat citind codul din jur:
 *  - eTextPara::blit nu amesteca cu ce era dedesubt, scrie o culoare gata amestecata intre fundal si scris
 *    (font.cpp 736-757), in 16 trepte; de aceea literele se scriu alb pe negru pe o ciorna si se ia din ea numai
 *    acoperirea, din octetul rosu (deplina = 239).
 *  - Un gDC nou are zona de taiere goala (grc.cpp 602-605): fara ea blit nu deseneaza nimic.
 *  - gPainter::blit tine poza (AddRef, grc.cpp 409) pana o deseneaza firul gRC, deci fiecare pagina primeste o
 *    poza noua si cea veche traieste cat trebuie.
 *  - Un element de teletext e textul de aceeasi culoare, cu randurile lipite prin spatiu (teletext.cpp,
 *    addSubtitleString); element nou la schimbarea culorii si la „- " (dialog). Aici fiecare element se imparte
 *    din nou in randuri dupa latimea ecranului; doua randuri se fac cat mai egale.
 *  - Randurile stau stivuite de jos in sus, ultimul la inaltimea aleasa de om (inainte: jumatatea de jos impartita
 *    in benzi egale, cate una pe element, deci doua randuri cadeau departe unul de altul).
 *  - m_visible_region se face cu gRegion(dreptunghi), ca sa aiba si marginile (extends) puse: numai asa invalidate
 *    reface doar locul textului. Cu rects.push_back singur, extends ramane nevalid si se reface tot ecranul
 *    (asa ramane la paginile DVB, ca inainte).
 *  - Viteza: conturul luat punct cu punct din disc, impartirile pe fiecare pixel si ciorna
 *    curatata toata la fiecare rand dadeau, pe un Cortex-A55 (cat receptorul, putin mai rapid), 62 ms pentru doua
 *    randuri si 1,2-1,4 s la 200% cu contur gros, pe firul principal. Acum aceiasi pixeli, octet cu octet, ies din
 *    treceri cu 8 sau 16 pixeli deodata (contureaza, estompeaza, compunerea); masuratorile sunt in verificare.md.
 *  - Stilul literelor (si al textului citit din subtitrarile DVB): setStyle alege fontul (unul inregistrat cu addFont: al skinului, al imaginii, Tiresias, unul descarcat
 *    de pe Google), grosimea (varianta groasa a fontului sau, cand nu are, literele latite pe orizontala), marimea,
 *    culorile literelor, conturului, umbrei si fundalului, grosimea conturului, umbra (directia din 8, distanta, moale
 *    sau tare), fundalul (pe fiecare rand sau o cutie pentru toate, cu opacitatea lui), inaltimea si distanta dintre
 *    randuri. Cu valorile de la inceput poza iese octet cu octet ca inainte (umbra jos-dreapta 2, 3 la 50 de pixeli,
 *    raza 3; conturul si umbra negre).
 *  - Un font ales caruia ii lipsesc litere din text (Tiresias are numai Latin-1: fara ă, ș, ț) ar lasa golul
 *    (renderString sare litera fara glifa si scrie doar in jurnal): elementul acela ramane pe fontul skinului.
 *    eTextPara::missingGlyphs (font.cpp) spune cate litere lipsesc, cu fontul de inlocuire socotit, ca la desenare.
 */

eSubtitleWidget::eSubtitleStyle eSubtitleWidget::subtitleStyles[Subtitle_MAX];
/* font, font_bold, weight, size, color, outline, outline_color, shadow, shadow_color, shadow_direction, shadow_distance,
   shadow_softness, background, background_color, background_opacity, bottom, line_spacing: ca in skin, contur normal
   negru, umbra moale neagra jos-dreapta, fara fundal, la 8% de jos (ce era inainte de setStyle) */
eSubtitleWidget::eTextStyle eSubtitleWidget::s_style = { "", "", 0, 100, -1, 2, 0, 1, 0, 3, 100, 1, 0, 0, 60, 8, 100 };
std::list<eSubtitleWidget*> eSubtitleWidget::s_widgets;
/* OCR-ul paginilor DVB: functia din Python (Components/HdsOcrSubtitrari.py, pentruNucleu), numaratoarea paginilor
   trimise (una pentru toate widgeturile) si cat se asteapta textul unei pagini afisate inainte sa se arate poza */
ePyObject eSubtitleWidget::s_ocr_handler;
int eSubtitleWidget::s_ocr_generation = 0;
int eSubtitleWidget::s_ocr_wait_ms = 500;
/* traducerea paginilor text: functia din Python (Components/HdsTraducereSubtitrari.py, pentruNucleu), numaratoarea
   paginilor date la traducere (una pentru toate widgeturile), traducerea in locul originalului (0) sau sub el (1), cat
   asteapta cel mult o pagina (cu ecranul gol) textul si traducerea ei inainte sa se arate originalul cu semnul, semnul
   si timpul de citire (vezi „coada de afisare”, la sfarsitul fisierului) */
ePyObject eSubtitleWidget::s_translation_handler;
int eSubtitleWidget::s_translation_generation = 0;
int eSubtitleWidget::s_translation_under = 0;
int eSubtitleWidget::s_translation_wait_ms = 2000;
std::string eSubtitleWidget::s_translation_mark;
int eSubtitleWidget::s_reading_base_ms = 700;
int eSubtitleWidget::s_reading_char_ms = 60;
int eSubtitleWidget::s_reading_min_ms = 1500;
int eSubtitleWidget::s_reading_max_ms = 7000;

static long long ceasMonoton()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
long long (*eSubtitleWidget::s_clock)() = ceasMonoton;
/* culoarea traducerii afisate sub original: galben cald, deschis, „Crem" (#fff3b0) din paleta subtitrarilor
   (Components/HdsSubtitrariAspect.py, PALETA); cand originalul are chiar aceasta culoare, traducerea se scrie alb */
static const int CULOARE_TRADUCERE_SUB_ORIGINAL = 0xfff3b0;
static const int CULOARE_TRADUCERE_REZERVA = 0xffffff;

/* acoperirea deplina a unei glife, asa cum o scrie eTextPara::blit pe 32 de biti: BLEND(0,255,240) */
static const int ACOPERIRE_PLINA = 239;
/* raza conturului pentru o litera de 50 de pixeli (cat da skinul): fara, subtire, normal, gros, foarte gros */
static const int CONTUR_LA_50[5] = { 0, 2, 3, 4, 6 };
/* umbra, pentru o litera de 50 de pixeli, la distanta obisnuita (100%): deplasarea in zecimi de pixel pe cele 8
   directii (sus, sus-dreapta, dreapta, jos-dreapta, jos, jos-stanga, stanga, sus-stanga). Jos-dreapta e 2, 3, umbra
   de dinainte de setStyle; celelalte au aceeasi lungime, cam 3,6 pixeli, iar cele piezise sunt la fel de aplecate. */
static const int UMBRA_DIRECTII[8][2] = { { 0, -36 }, { 20, -30 }, { 36, 0 }, { 20, 30 }, { 0, 36 }, { -20, 30 },
	{ -36, 0 }, { -20, -30 } };
/* estomparea umbrei, tot pentru 50 de pixeli: tare (niciuna), moale, foarte moale; trei treceri de medie = aproape o
   gaussiana */
static const int UMBRA_RAZA_LA_50[3] = { 0, 3, 6 };
static const int UMBRA_TARIE = 190;		/* cat de opaca e umbra moale sub o litera plina, din 255; umbra tare e opaca */
static const int MARGINE_LATERALA = 5;	/* procente din latime lasate libere in stanga si in dreapta */
static const int RANDURI_MAXIME = 32;

eSubtitleWidget::eSubtitleWidget(eWidget *parent)
	: eWidget(parent), m_hide_subtitles_timer(eTimer::create(eApp))
{
	setBackgroundColor(gRGB(0,0,0,255));
	m_dvb_page_ok = 0;
	m_text_ok = 0;
	m_text_top = false;
	m_ocr_generation = 0;
	m_ocr_timer = eTimer::create(eApp);
	m_translation_timer = eTimer::create(eApp);
	m_queue_ids = 0;
	m_queue_on_screen = false;
	m_queue_busy = false;
	m_queue_again = false;
	/* the hide timer: without translation the page goes (clearPage, as before); with the display queue it only says
	   when the original of the last page would have gone (hideTimeout) */
	CONNECT(m_hide_subtitles_timer->timeout, eSubtitleWidget::hideTimeout);
	CONNECT(m_ocr_timer->timeout, eSubtitleWidget::ocrWaitOver);
	CONNECT(m_translation_timer->timeout, eSubtitleWidget::queueAdvance);
	s_widgets.push_back(this);
}

eSubtitleWidget::~eSubtitleWidget()
{
	s_widgets.remove(this);
	while (!m_ocr_prefetch.empty())
		dropPrefetch(m_ocr_prefetch.begin());
}

/* ------------------------------------------------------------------ textul, fara marcaje */

/* Subtitrarile din fisiere vin cu marcaje simple (<i>, <b>, <u>, <font ...>, si cele pango): litera se alege dupa
   un marcaj pus chiar la inceput, toate marcajele se scot, iar entitatile se fac inapoi litere. Un „<" care nu
   incepe un marcaj („<3", „a < b") ramane. Inainte, orice „<" din text ducea la text.at(1) si substr(3, len-7):
   un rand „<3" iesea din sir, deci std::out_of_range, iar enigma2 e fara exceptii (oprire). Aici nu se citeste
   nimic dincolo de capatul textului. */
static std::string faraMarcaje(const std::string &in, int &italic, int &bold)
{
	italic = bold = 0;
	if (in.size() >= 3 && in[0] == '<' && in[2] == '>')
	{
		int c = tolower((unsigned char)in[1]);
		if (c == 'i')
			italic = 1;
		else if (c == 'b')
			bold = 1;
	}
	std::string fara;
	fara.reserve(in.size());
	size_t i = 0, n = in.size();
	while (i < n)
	{
		if (in[i] == '<')
		{
			size_t j = i + 1;
			if (j < n && in[j] == '/')
				++j;
			if (j < n && isalpha((unsigned char)in[j]))
			{
				size_t k = j;
				while (k < n && k - i < 256 && in[k] != '>' && in[k] != '<')
					++k;
				if (k < n && in[k] == '>')
				{
					i = k + 1;
					continue;
				}
			}
		}
		fara += in[i++];
	}
	/* entitatile, intr-o singura trecere ("&amp;lt;" ramane "&lt;") */
	static const char *entitati[5] = { "&apos;", "&quot;", "&amp;", "&lt;", "&gt;" };
	static const char litere[5] = { 39, 34, 38, 60, 62 };
	std::string iesire;
	iesire.reserve(fara.size());
	for (i = 0; i < fara.size(); )
	{
		int gasit = -1;
		if (fara[i] == '&')
			for (int e = 0; e < 5; ++e)
				if (fara.compare(i, strlen(entitati[e]), entitati[e]) == 0)
				{
					gasit = e;
					break;
				}
		if (gasit >= 0)
		{
			iesire += litere[gasit];
			i += strlen(entitati[gasit]);
		}
		else
			iesire += fara[i++];
	}
	return iesire;
}

/* ------------------------------------------------------------------ paginile */

void eSubtitleWidget::setPage(const eDVBTeletextSubtitlePage &p)
{
	std::vector<eTextElement> elemente;
	for (unsigned int i = 0; i < p.m_elements.size(); ++i)
	{
		eTextElement e;
		e.text = p.m_elements[i].m_text;
		e.face = Subtitle_TTX;
		e.color = p.m_elements[i].m_color;
		e.have_color = 1;
		elemente.push_back(e);
	}
	if (s_translation_handler)
	{
		/* translation on: the page goes to the display queue; what is on screen stays until its time is up. An empty
		   page (the erase of the subtitle) only ends the original of the page before it. */
		if (elemente.empty())
			m_hide_subtitles_timer->stop();
		else
			m_hide_subtitles_timer->start(7500, true);
		queueText(elemente, 0, false);
		return;
	}
	m_pixmap = 0;
	m_dvb_page_ok = 0;
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	m_text_top = false;
	showTextPage(elemente, 0);
	m_hide_subtitles_timer->start(7500, true);
}

void eSubtitleWidget::setPage(const eDVBSubtitlePage &p)
{
	eDebug("setPage");
	if (s_translation_handler)
	{
		/* translation on: the DVB page goes to the display queue (its text is read, then translated); a page without
		   regions only ends the original of the page before it */
		if (p.m_regions.empty())
			m_hide_subtitles_timer->stop();
		else
			m_hide_subtitles_timer->start(7500, true);
		queueDvb(p);
		return;
	}
	m_dvb_page = p;
	m_text_ok = 0;
	m_text_pixmap = 0;
	m_text_elements.clear();
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	invalidate(m_visible_region);  // invalidate old visible regions
	/* a new region, not only rects.clear(): a text page leaves a region with its extents set */
	m_visible_region = gRegion();
	for (std::list<eDVBSubtitleRegion>::iterator it(m_dvb_page.m_regions.begin()); it != m_dvb_page.m_regions.end(); ++it)
	{
		eDebug("add %d %d %d %d", it->m_position.x(), it->m_position.y(), it->m_pixmap->size().width(), it->m_pixmap->size().height());
		eDebug("disp width %d, disp height %d", p.m_display_size.width(), p.m_display_size.height());
		eRect r = eRect(it->m_position, it->m_pixmap->size());
		r.scale(size().width(), p.m_display_size.width(), size().height(), p.m_display_size.height());
		m_visible_region.rects.push_back(r);
	}
	m_hide_subtitles_timer->start(7500, true);
	/* OCR: the page goes to Components/HdsOcrSubtitrari.py (or went there when it arrived, prefetchPage); while the
	   text is awaited nothing is shown (at most s_ocr_wait_ms, then the picture), the text comes through setOcrText,
	   a refusal through showOcrBitmap; a page whose answer is already here is shown at once */
	int ocr = askOcr();
	if (ocr == 2)
		return;
	if (ocr == 1)
	{
		m_dvb_page_ok = 0;
		if (s_ocr_wait_ms > 0)
		{
			m_ocr_timer->start(s_ocr_wait_ms, true);
			return;
		}
	}
	m_dvb_page_ok = 1;
	invalidate(m_visible_region);  // invalidate new regions
}

void eSubtitleWidget::setPage(const ePangoSubtitlePage &p)
{
	std::vector<eTextElement> elemente;
	for (unsigned int i = 0; i < p.m_elements.size(); ++i)
	{
		const ePangoSubtitlePageElement &element = p.m_elements[i];
		int italic, bold;
		eTextElement e;
		e.text = faraMarcaje(element.m_pango_line, italic, bold);
		e.face = italic ? Subtitle_Italic : (bold ? Subtitle_Bold : Subtitle_Regular);
		e.color = element.m_color;
		e.have_color = element.m_have_color ? 1 : 0;
		elemente.push_back(e);
	}
	int timeout_ms = p.m_timeout;
	/* a text of unknown length (GST_CLOCK_TIME_NONE) came as 0 ms and was hidden at once */
	if (timeout_ms <= 0)
		timeout_ms = 7500;
	if (s_translation_handler)
	{
		/* translation on: the display queue (the hide timer then only says when the original would have gone) */
		m_hide_subtitles_timer->start(timeout_ms, true);
		queueText(elemente, 1, p.m_top);
		return;
	}
	m_pixmap = 0;
	m_dvb_page_ok = 0;
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	m_text_top = p.m_top;
	showTextPage(elemente, 1);
	m_hide_subtitles_timer->start(timeout_ms, true);
}

void eSubtitleWidget::setPageTimeout(int timeout_ms)
{
	m_hide_subtitles_timer->start(timeout_ms > 0 ? timeout_ms : 7500, true);
}

void eSubtitleWidget::showSample(const std::string &text)
{
	showTranslationSample(text, std::string());
}

void eSubtitleWidget::showTranslationSample(const std::string &original, const std::string &translation)
{
	std::vector<eTextElement> elemente;
	const std::string *parti[2] = { &original, &translation };
	for (int parte = 0; parte < 2; ++parte)
	{
		const std::string &text = *parti[parte];
		size_t inceput = 0;
		while (inceput < text.size())
		{
			size_t sfarsit = text.find(char(10), inceput);
			if (sfarsit == std::string::npos)
				sfarsit = text.size();
			eTextElement e;
			e.text = text.substr(inceput, sfarsit - inceput);
			e.face = Subtitle_TTX;
			e.color = gRGB(255, 255, 255);	/* teletext white: what "the broadcast colors" show most of the time */
			e.have_color = 1;
			e.translated = parte;
			if (!e.text.empty())
				elemente.push_back(e);
			inceput = sfarsit + 1;
		}
	}
	m_hide_subtitles_timer->stop();
	queueClear();
	m_pixmap = 0;
	m_dvb_page_ok = 0;
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	m_text_top = false;
	setTextElements(elemente);
}

/* everything off the screen now, the display queue too (servicemp3: a jump in the film, the end; the preview) */
void eSubtitleWidget::clearPage()
{
	eDebug("subtitle timeout... hide");
	queueClear();
	m_dvb_page_ok = 0;
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	m_text_ok = 0;
	m_text_pixmap = 0;
	m_text_elements.clear();
	invalidate(m_visible_region);
	m_visible_region = gRegion();
}

void eSubtitleWidget::setTextElements(const std::vector<eTextElement> &elements)
{
	invalidate(m_visible_region);  // invalidate old visible regions
	m_visible_region = gRegion();
	m_text_elements = elements;
	m_text_ok = 1;
	layoutText();
	if (m_text_pixmap)
		m_visible_region = gRegion(eRect(m_text_position, m_text_pixmap->size()));
	invalidate(m_visible_region);  // invalidate new regions
}

void eSubtitleWidget::setPixmap(ePtr<gPixmap> &pixmap, gRegion changed, eRect pixmap_dest)
{
	m_pixmap = pixmap;
	m_pixmap_dest = pixmap_dest; /* this is in a virtual 720x576 cage */

		/* incoming "changed" regions are relative to the physical pixmap area, so they have to be scaled to the virtual pixmap area, then to the screen */
	changed.scale(m_pixmap_dest.width(), 720, m_pixmap_dest.height(), 576);
	changed.moveBy(ePoint(m_pixmap_dest.x(), m_pixmap_dest.y()));

	if (pixmap->size().width() && pixmap->size().height())
		changed.scale(size().width(), pixmap->size().width(), size().height(), pixmap->size().height());

	invalidate(changed);
}

/* ------------------------------------------------------------------ asezarea si compunerea textului */

/* latimea cernelii unui text scris intr-un singur rand; -1 daca fontul nu merge */
static int latimeText(gFont *litera, const std::string &text)
{
	ePtr<eTextPara> para = new eTextPara(eRect(0, 0, 16000, 4000));
	para->setFont(litera);
	if (para->renderString(text.c_str(), 0) < 0)
		return -1;
	return para->getBoundBox().width();
}

/* Imparte un paragraf in randuri de cel mult `latime` pixeli, pe cuvinte. Latimile se masoara o data pe cuvant
   (nu pe fiecare inceput de rand), ca un text lung dintr-un fisier sa nu coste cat patratul lungimii lui. Cand
   iese in doua randuri, taietura se muta acolo unde randul mai lung e cel mai scurt: doua randuri cat de cat
   egale se citesc mai usor decat unul plin si unul cu un cuvant. Un cuvant mai lat decat ecranul sta singur
   pe rand (se taie la margini). */
static void imparte(gFont *litera, const std::string &paragraf, int latime, std::vector<std::string> &randuri)
{
	std::vector<std::string> cuvinte;
	size_t i = 0;
	while (i < paragraf.size())
	{
		while (i < paragraf.size() && (paragraf[i] == ' ' || paragraf[i] == char(9) || paragraf[i] == char(13)))
			++i;
		size_t j = i;
		while (j < paragraf.size() && paragraf[j] != ' ' && paragraf[j] != char(9) && paragraf[j] != char(13))
			++j;
		if (j > i)
			cuvinte.push_back(paragraf.substr(i, j - i));
		i = j;
	}
	if (cuvinte.empty())
		return;
	std::string tot = cuvinte[0];
	for (i = 1; i < cuvinte.size(); ++i)
		tot += " " + cuvinte[i];
	if (cuvinte.size() == 1 || latimeText(litera, tot) <= latime)
	{
		randuri.push_back(tot);
		return;
	}
	size_t n = cuvinte.size();
	std::vector<int> lat(n);
	for (i = 0; i < n; ++i)
	{
		lat[i] = latimeText(litera, cuvinte[i]);
		if (lat[i] < 0)
			lat[i] = 0;
	}
	int spatiu = latimeText(litera, "x x") - latimeText(litera, "xx");
	if (spatiu < 1)
		spatiu = litera->pointSize / 4 + 1;

	std::vector<size_t> inceputuri;
	int curent = -1;
	for (i = 0; i < n; ++i)
	{
		if (curent < 0 || curent + spatiu + lat[i] > latime)
		{
			inceputuri.push_back(i);
			curent = lat[i];
		}
		else
			curent += spatiu + lat[i];
	}
	if (inceputuri.size() == 2)
	{
		int total = 0;
		for (i = 0; i < n; ++i)
			total += lat[i] + (i ? spatiu : 0);
		int sus = 0, cel_mai_bun = -1;
		size_t taietura = inceputuri[1];
		for (size_t k = 1; k < n; ++k)
		{
			sus += lat[k - 1] + (k > 1 ? spatiu : 0);
			int jos = total - sus - spatiu;
			int mai_lung = sus > jos ? sus : jos;
			if (cel_mai_bun < 0 || mai_lung < cel_mai_bun)
			{
				cel_mai_bun = mai_lung;
				taietura = k;
			}
		}
		inceputuri[1] = taietura;
	}
	for (size_t r = 0; r < inceputuri.size(); ++r)
	{
		size_t de_la = inceputuri[r], pana_la = (r + 1 < inceputuri.size()) ? inceputuri[r + 1] : n;
		std::string rand = cuvinte[de_la];
		for (size_t k = de_la + 1; k < pana_la; ++k)
			rand += " " + cuvinte[k];
		randuri.push_back(rand);
	}
}

/* Vectori de 16 octeti (cat un registru NEON q pe receptor, cat unul SSE2 pe PC). Singur, la -O2, GCC nu vectorizeaza
   buclele cu lungime necunoscuta; fara ei conturul, umbra si compunerea ar merge octet cu octet. Tipurile raman de
   16 octeti (sau 8): cele mai mari nu incap in cele 16 registre NEON si ajung pe stiva. */
typedef unsigned char v16u8 __attribute__((vector_size(16)));
typedef unsigned char v8u8 __attribute__((vector_size(8)));
typedef unsigned short v8u16 __attribute__((vector_size(16)));
typedef unsigned int v4u32 __attribute__((vector_size(16)));

static inline v16u8 incarca16(const unsigned char *p)
{
	v16u8 v;
	memcpy(&v, p, 16);
	return v;
}

static inline void pune16(unsigned char *p, v16u8 v)
{
	memcpy(p, &v, 16);
}

static inline v8u16 incarca8(const unsigned char *p)
{
	v8u8 v;
	memcpy(&v, p, 8);
	return __builtin_convertvector(v, v8u16);
}

static inline void pune8(unsigned char *p, v8u16 v)
{
	v8u8 o = __builtin_convertvector(v, v8u8);
	memcpy(p, &o, 8);
}

static inline v16u8 max16(v16u8 a, v16u8 b)
{
	return a > b ? a : b;
}

/* x / 255 (restul aruncat) pentru 0 <= x <= 65534, fara impartire */
static inline v8u16 imparte255(v8u16 x)
{
	return (x + 1 + (x >> 8)) >> 8;
}

/* (s * inm) >> 20 pe 8 sume de 16 biti, cu produsul pe 32 de biti (jumatatile, cate 4) */
typedef unsigned short v4u16 __attribute__((vector_size(8)));
static inline v8u16 inmultesteSiDeplaseaza(v8u16 s, unsigned int inm)
{
	v4u16 j, s2;
	memcpy(&j, &s, 8);
	memcpy(&s2, ((const unsigned char *)&s) + 8, 8);
	v4u16 rj = __builtin_convertvector((__builtin_convertvector(j, v4u32) * inm) >> 20, v4u16);
	v4u16 rs = __builtin_convertvector((__builtin_convertvector(s2, v4u32) * inm) >> 20, v4u16);
	v8u16 r;
	memcpy(&r, &rj, 8);
	memcpy(((unsigned char *)&r) + 8, &rs, 8);
	return r;
}

/* d[x] = cel mai mare dintre d[x] si s[x] */
static inline void maximIn(unsigned char *d, const unsigned char *s, int n)
{
	int x = 0;
	for (; x + 16 <= n; x += 16)
		pune16(d + x, max16(incarca16(d + x), incarca16(s + x)));
	for (; x < n; x++)
		d[x] = s[x] > d[x] ? s[x] : d[x];
}

/* n / f pentru 0 <= n <= 255 * f, f impar de la 3 la 63: (n * inm) >> 20, cu inm = 2^20 / f rotunjit in sus.
   Acelasi cat ca impartirea (eroarea n * (inm * f - 2^20) < 2^20), iar produsul incape in 32 de biti. */
static const int IMPARTIRE_BITI = 20;
static const int UMBRA_RAZA_MAXIMA = 31;

/* Estompare: trei treceri cu media pe o fereastra (ca in ecranpornire.cpp), cat o gaussiana: umbra moale. Aceleasi
   valori ca media luata pixel cu pixel (marginile se repeta, restul impartirii se arunca), dar cate 8 pixeli
   deodata: pe orizontala suma ferestrei din randul prelungit cu marginile, pe verticala o suma pe fiecare coloana,
   mutata rand cu rand; sumele incap in 16 biti (cel mult 255 * 63), impartirea e o inmultire.
   raza de la 1 la UMBRA_RAZA_MAXIMA. */
static void estompeaza(unsigned char *harta, unsigned char *ajutor, int latime, int inaltime, int raza)
{
	int fereastra = 2 * raza + 1;
	unsigned int inm = ((1u << IMPARTIRE_BITI) + fereastra - 1) / fereastra;
	std::vector<unsigned char> prelungit(latime + 2 * raza + 8);
	std::vector<unsigned short> sume(latime);
	for (int trecere = 0; trecere < 3; trecere++)
	{
		/* pe orizontala, din harta in ajutor */
		for (int y = 0; y < inaltime; y++)
		{
			const unsigned char *rand = harta + (long)y * latime;
			unsigned char *iesire = ajutor + (long)y * latime;
			memset(&prelungit[0], rand[0], raza);
			memcpy(&prelungit[raza], rand, latime);
			memset(&prelungit[raza + latime], rand[latime - 1], raza + 8);
			int x = 0;
			for (; x + 8 <= latime; x += 8)
			{
				v8u16 s = incarca8(&prelungit[x]);
				for (int k = 1; k < fereastra; k++)
					s += incarca8(&prelungit[x + k]);
				pune8(iesire + x, inmultesteSiDeplaseaza(s, inm));
			}
			for (; x < latime; x++)
			{
				unsigned int s = 0;
				for (int k = 0; k < fereastra; k++)
					s += prelungit[x + k];
				iesire[x] = (unsigned char)((s * inm) >> IMPARTIRE_BITI);
			}
		}
		/* pe verticala, din ajutor inapoi in harta */
		for (int x = 0; x < latime; x++)
			sume[x] = 0;
		for (int y = -raza; y <= raza; y++)
		{
			const unsigned char *rand = ajutor + (long)(y < 0 ? 0 : (y >= inaltime ? inaltime - 1 : y)) * latime;
			for (int x = 0; x < latime; x++)
				sume[x] += rand[x];
		}
		for (int y = 0; y < inaltime; y++)
		{
			int iese = y - raza, intra = y + raza + 1;
			const unsigned char *scos = ajutor + (long)(iese < 0 ? 0 : iese) * latime;
			const unsigned char *adaugat = ajutor + (long)(intra >= inaltime ? inaltime - 1 : intra) * latime;
			unsigned char *iesire = harta + (long)y * latime;
			int x = 0;
			for (; x + 8 <= latime; x += 8)
			{
				v8u16 s;
				memcpy(&s, &sume[x], 16);
				pune8(iesire + x, inmultesteSiDeplaseaza(s, inm));
				s += incarca8(adaugat + x);
				s -= incarca8(scos + x);
				memcpy(&sume[x], &s, 16);
			}
			for (; x < latime; x++)
			{
				iesire[x] = (unsigned char)((sume[x] * inm) >> IMPARTIRE_BITI);
				sume[x] = (unsigned short)(sume[x] + adaugat[x] - scos[x]);
			}
		}
	}
}

/* fasiile unui rand: f0 + h * latime = maximul randului pe [x-h, x+h], h de la 0 la h_max, fiecare din cea dinainte */
static void fasiiRand(const unsigned char *rand, unsigned char *f0, int latime, int h_max)
{
	memcpy(f0, rand, latime);
	for (int h = 1; h <= h_max; h++)
	{
		const unsigned char *v = f0 + (size_t)(h - 1) * latime;
		unsigned char *f = f0 + (size_t)h * latime;
		if (latime == 1)
		{
			f[0] = v[0];
			continue;
		}
		f[0] = v[0] > v[1] ? v[0] : v[1];
		int x = 1;
		for (; x + 17 <= latime; x += 16)
			pune16(f + x, max16(max16(incarca16(v + x - 1), incarca16(v + x)), incarca16(v + x + 1)));
		for (; x < latime - 1; x++)
		{
			unsigned char m = v[x - 1] > v[x] ? v[x - 1] : v[x];
			f[x] = m > v[x + 1] ? m : v[x + 1];
		}
		f[latime - 1] = v[latime - 2] > v[latime - 1] ? v[latime - 2] : v[latime - 1];
	}
}

/* Conturul: fiecare pixel ia cel mai mare litere[s] * greutate / 256 dintr-un disc in jurul lui; greutatea e 256
   inauntru, scade pe inelul de la margine (marginea moale, rotunda) si e 0 afara. Rezultatul e acelasi, pixel cu
   pixel, ca la parcurgerea discului punct cu punct, dar rand cu rand, cate 16 pixeli deodata, cu randurile de care
   e nevoie tinute la indemana (pe ARM, 150% cu contur gros lua secunde pe pagina):
   - partea plina a discului (greutatea 256) e pe fiecare rand dy o fasie [-h, h]: maximul ei e maximul pe latimea h
     al randului y+dy. Pentru fiecare rand al literelor, maximele pe latimile 0, 1, 2, ... se fac o data, una din
     alta (3 citiri pe pixel), si se tin cat e nevoie de ele (2R+1 randuri);
   - punctele inelului au putine greutati (cate una pe departare). Pentru fiecare greutate w, cel mai mare
     litere[s] dintre punctele ei, M, da M * w / 256, adica exact cel mai mare dintre litere[s] * w / 256.
   Un punct plin care n-ar sta in fasia randului lui (nu se intampla: greutatea scade cu departarea) intra cu
   greutatea 256 la inel, deci rezultatul nu depinde de asta. */
static void contureaza(const unsigned char *litere, unsigned char *contur, int latime, int inaltime, int raza)
{
	struct Punct
	{
		int dx, dy;
	};
	int R = raza + 1, randuri_disc = 2 * R + 1;
	std::vector<int> plin(randuri_disc, -1), greutati(randuri_disc);	/* plin: jumatatea fasiei, -1 = niciuna */
	std::vector<int> inel_greutati;
	std::vector<std::vector<Punct> > inel_puncte;
	for (int dy = -R; dy <= R; dy++)
	{
		for (int dx = -R; dx <= R; dx++)
		{
			float d = sqrtf((float)(dx * dx + dy * dy));
			int w = (int)((raza + 0.5f - d) * 256.0f + 0.5f);
			greutati[dx + R] = w > 256 ? 256 : (w > 0 ? w : 0);
		}
		int h = -1;
		while (h + 1 <= R && greutati[R + h + 1] == 256 && greutati[R - h - 1] == 256)
			h++;
		plin[dy + R] = h;
		for (int dx = -R; dx <= R; dx++)
		{
			int w = greutati[dx + R];
			if (w <= 0 || (dx >= -h && dx <= h))
				continue;
			size_t k = 0;
			while (k < inel_greutati.size() && inel_greutati[k] != w)
				k++;
			if (k == inel_greutati.size())
			{
				inel_greutati.push_back(w);
				inel_puncte.push_back(std::vector<Punct>());
			}
			Punct pt = { dx, dy };
			inel_puncte[k].push_back(pt);
		}
	}
	int h_max = 0;
	for (int k = 0; k < randuri_disc; k++)
		if (plin[k] > h_max)
			h_max = plin[k];

	/* fasiile randului sursa s (latimile 0..h_max) stau in locul s % randuri_disc */
	std::vector<unsigned char> fasii((size_t)randuri_disc * (h_max + 1) * latime), cel_mai_mare(latime);
	for (int s = 0; s < inaltime && s < R; s++)
		fasiiRand(litere + (size_t)s * latime, &fasii[(size_t)(s % randuri_disc) * (h_max + 1) * latime], latime, h_max);
	for (int y = 0; y < inaltime; y++)
	{
		/* randul sursa y + R intra (locul lui era al randului y - R - 1, de care nu mai e nevoie) */
		int s = y + R;
		if (s < inaltime && s >= R)
			fasiiRand(litere + (size_t)s * latime, &fasii[(size_t)(s % randuri_disc) * (h_max + 1) * latime], latime, h_max);
		unsigned char *o = contur + (size_t)y * latime;
		memset(o, 0, latime);
		/* partea plina */
		for (int k = 0; k < randuri_disc; k++)
		{
			int sy = y + k - R;
			if (plin[k] < 0 || sy < 0 || sy >= inaltime)
				continue;
			maximIn(o, &fasii[((size_t)(sy % randuri_disc) * (h_max + 1) + plin[k]) * latime], latime);
		}
		/* inelul, cate o greutate */
		for (size_t k = 0; k < inel_puncte.size(); k++)
		{
			memset(&cel_mai_mare[0], 0, latime);
			int atins = 0;
			for (size_t q = 0; q < inel_puncte[k].size(); q++)
			{
				int dx = inel_puncte[k][q].dx, sy = y + inel_puncte[k][q].dy;
				int x0 = dx < 0 ? -dx : 0, x1 = dx > 0 ? latime - dx : latime;
				if (sy < 0 || sy >= inaltime || x1 <= x0)
					continue;
				maximIn(&cel_mai_mare[x0], litere + (size_t)sy * latime + x0 + dx, x1 - x0);
				atins = 1;
			}
			if (!atins)
				continue;
			unsigned short w = (unsigned short)inel_greutati[k];
			int x = 0;
			for (; x + 8 <= latime; x += 8)
			{
				v8u16 m = (incarca8(&cel_mai_mare[x]) * w) >> 8, c = incarca8(o + x);
				pune8(o + x, m > c ? m : c);
			}
			for (; x < latime; x++)
			{
				int v = cel_mai_mare[x] * w / 256;
				if (v > o[x])
					o[x] = (unsigned char)v;
			}
		}
	}
}

/* Literele unui text, ca puncte de cod, pentru intrebarea „are fontul toate literele?". Se citeste UTF-8 ca in
   eTextPara::renderString (un octet de inceput fara toate continuarile lui e luat ca Latin-1); spatiile si semnele de
   control (si cele din DVB: 0x86, 0x87, 0x8A, 0xE086...) nu se deseneaza, deci nu conteaza; cratima moale si cratima
   se deseneaza cu „-". */
static void puncteDeCod(const std::string &text, std::vector<unsigned long> &coduri)
{
	coduri.clear();
	size_t i = 0, n = text.size();
	while (i < n)
	{
		unsigned long cod = (unsigned char)text[i++];
		if (cod & 0x80)
		{
			int urmeaza = ((cod & 0xE0) == 0xC0) ? 1 : ((cod & 0xF0) == 0xE0) ? 2 : ((cod & 0xF8) == 0xF0) ? 3 : 0;
			int k = 0;
			while (k < urmeaza && i + k < n && (((unsigned char)text[i + k]) & 0xC0) == 0x80)
				++k;
			if (urmeaza && k == urmeaza)
			{
				cod &= 0xFF >> (urmeaza + 2);
				for (k = 0; k < urmeaza; ++k)
					cod = (cod << 6) | ((unsigned char)text[i++] & 0x3F);
			}
		}
		if (cod <= 0x20 || cod == 0x7F || (cod >= 0x80 && cod <= 0xA0) || cod == 0x200B || (cod >= 0xE080 && cod <= 0xE09F))
			continue;
		if (cod == 0xAD || cod == 0x2010)
			cod = 0x2D;
		coduri.push_back(cod);
	}
}

/* deplasarea umbrei pe o axa: zecimi de pixel la 50 de pixeli si distanta 100%, dus la litera `marime` si la distanta
   `procent`, rotunjit; cel putin un pixel cand directia merge pe axa aceea. Pentru jos-dreapta la 100%:
   (2 * marime + 25) / 50 si (3 * marime + 25) / 50, exact ca umbra de dinainte. */
static int deplasareUmbra(int zecimi, int procent, int marime)
{
	if (!zecimi)
		return 0;
	int n = ((zecimi < 0 ? -zecimi : zecimi) * procent * marime + 25000) / 50000;
	if (n < 1)
		n = 1;
	return zecimi < 0 ? -n : n;
}

/* Ingrosarea desenata, pentru un font fara varianta groasa (fonturile descarcate au numai greutatea 400): fiecare pixel
   ia cel mai mare dintre vecinii lui pe orizontala, pana la h de fiecare parte, deci trasaturile verticale se latesc
   cu h pixeli pe fiecare latura, ca ingrosarea literelor pe ecrane. Harta (latime x inaltime) creste cu h pixeli in
   stanga si in dreapta. */
static void ingroasa(std::vector<unsigned char> &harta, int latime, int inaltime, int h)
{
	int noua = latime + 2 * h;
	std::vector<unsigned char> iesire((size_t)noua * inaltime), rand(noua), fasii((size_t)(h + 1) * noua);
	for (int y = 0; y < inaltime; y++)
	{
		memset(&rand[0], 0, noua);
		memcpy(&rand[h], &harta[(size_t)y * latime], latime);
		fasiiRand(&rand[0], &fasii[0], noua, h);
		memcpy(&iesire[(size_t)y * noua], &fasii[(size_t)h * noua], noua);
	}
	harta.swap(iesire);
}

/* Cursivul desenat: harta (latime x inaltime) inclinata spre dreapta, cate `panta` / 1024 pixeli pe rand de la baza in
   sus (212/1024 = cam 12 grade, cat au fetele cursive obisnuite); fiecare rand se muta cu o parte intreaga si una
   fractionara, amestecata intre doi pixeli vecini, ca marginile sa ramana netede. Harta se lateste cu cat se muta
   randul de sus; intoarce latimea noua. */
static int inclina(std::vector<unsigned char> &harta, int latime, int inaltime, int panta)
{
	int extra = ((inaltime - 1) * panta + 1023) / 1024 + 1;
	int noua = latime + extra;
	std::vector<unsigned char> iesire((size_t)noua * inaltime, 0);
	for (int y = 0; y < inaltime; y++)
	{
		int mutare = (inaltime - 1 - y) * panta;	/* in 1/1024 de pixel */
		int intreg = mutare >> 10, fractie = mutare & 1023;
		const unsigned char *sursa = &harta[(size_t)y * latime];
		unsigned char *tinta = &iesire[(size_t)y * noua + intreg];
		/* pixelul x ajunge in x + intreg (partea 1 - fractie) si in x + intreg + 1 (partea fractie) */
		int rest = 0;
		for (int x = 0; x < latime; x++)
		{
			int v = sursa[x];
			int aici = v * (1024 - fractie);
			tinta[x] = (unsigned char)((aici + rest + 512) >> 10);
			rest = v * fractie;
		}
		tinta[latime] = (unsigned char)((rest + 512) >> 10);
	}
	harta.swap(iesire);
	return noua;
}

static inline bool eNegru(const gRGB &c)
{
	return !c.r && !c.g && !c.b;
}

static inline gRGB culoareRGB(int rgb)
{
	return gRGB((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF);
}

/* Un strat opac de culoarea c, cu acoperirea a, peste ce e deja, pe 8 pixeli; culori premultiplicate, aceleasi calcule
   si rotunjiri ca peste(): (c * a + x * (255 - a) + 127) / 255. Cand stratul e negru si sub el nu e nicio culoare,
   R, G, B raman 0 si nu se mai calculeaza (culoare = false). */
static inline void strat(v8u16 &A, v8u16 &R, v8u16 &G, v8u16 &B, v8u16 a, const gRGB &c, bool culoare)
{
	v8u16 rest = 255 - a;
	if (culoare)
	{
		R = imparte255(a * (unsigned short)c.r + R * rest + 127);
		G = imparte255(a * (unsigned short)c.g + G * rest + 127);
		B = imparte255(a * (unsigned short)c.b + B * rest + 127);
	}
	A = a + imparte255(A * rest + 127);
}

/* un strat peste ce e deja („over"), cu culorile premultiplicate, toate 0..255 */
static inline void peste(int &a, int &r, int &g, int &b, int sa, const gRGB &c)
{
	if (sa <= 0)
		return;
	int rest = 255 - sa;
	r = (c.r * sa + r * rest + 127) / 255;
	g = (c.g * sa + g * rest + 127) / 255;
	b = (c.b * sa + b * rest + 127) / 255;
	a = sa + (a * rest + 127) / 255;
}

struct eRandAsezat
{
	std::string text;
	int element;
	int marime;				/* marimea literei, pixeli */
	int inaltime_rand;		/* inaltimea randului dupa font */
	int pas;				/* inaltimea randului cu tot cu spatiul de sus si de jos */
	int spatiu_sus;			/* de la sus-ul randului pana la sus-ul literelor (cu randuri foarte apropiate: sub 0) */
	int sus;				/* sus-ul randului pe ecran */
	int x0, y0, x1, y1;		/* cerneala, pe ecran */
	std::vector<unsigned char> acoperire;	/* (x1-x0+1) x (y1-y0+1), goala daca randul nu are cerneala */
};

void eSubtitleWidget::layoutText()
{
	m_text_pixmap = 0;
	int W = size().width(), H = size().height();
	if (W <= 0 || H <= 0 || m_text_elements.empty())
		return;
	fontRenderClass *motor = fontRenderClass::getInstance();
	if (!motor)
	{
		eDebug("[eSubtitleWidget] the font engine is not up");
		return;
	}
	const eTextStyle a = s_style;

	/* familia din skin si marimea literelor fiecarui fel, la marimea aleasa; fara stil in skin: "Regular", cat a 22-a
	   parte din inaltime */
	std::string familie_skin[Subtitle_MAX];
	int marime_fel[Subtitle_MAX];
	for (int f = 0; f < Subtitle_MAX; ++f)
	{
		const eSubtitleStyle &stil = subtitleStyles[f];
		familie_skin[f] = stil.font ? stil.font->family : std::string("Regular");
		int marime = stil.font ? stil.font->pointSize : H / 22;
		marime = marime * a.size / 100;
		if (marime < 10)
			marime = 10;
		marime_fel[f] = marime;
	}

	/* Ce familie si cata ingrosare desenata ia un fel de litera, cu fonturile skinului (ales = false) sau cu fontul ales.
	   Grosimea: 0 ca in skin (teletextul si <b> cu varianta groasa, restul obisnuit), 1 normala (numai <b> gros),
	   2 groasa, 3 foarte groasa (varianta groasa si inca o ingrosare desenata). Fara varianta groasa, fontul ales se
	   ingroasa desenat. Cursivul foloseste fontul obisnuit (asa face si skinul HDSatelit) si se inclina desenat, mai jos. */
	struct Alegere
	{
		std::string familie;
		int ingrosare;
	};
	auto alege = [&](int fel, bool ales) -> Alegere
	{
		Alegere r;
		bool gros = a.weight == 0 ? (fel == Subtitle_TTX || fel == Subtitle_Bold) : (a.weight == 1 ? fel == Subtitle_Bold : true);
		r.ingrosare = a.weight == 3 ? 1 : 0;
		if (!ales)
		{
			if (a.weight == 0)
				r.familie = familie_skin[fel];
			else if (gros)
				r.familie = familie_skin[Subtitle_Bold];
			else
				r.familie = familie_skin[fel == Subtitle_Italic ? Subtitle_Italic : Subtitle_Regular];
		}
		else if (gros && !a.font_bold.empty())
			r.familie = a.font_bold;
		else
		{
			r.familie = a.font;
			if (gros)
				r.ingrosare++;
		}
		return r;
	};

	/* litera fiecarui element; unui element cu litere pe care fontul ales nu le are (nici fontul de inlocuire) ii ramane
	   fontul skinului: altfel literele acelea n-ar aparea deloc */
	size_t elemente = m_text_elements.size();
	std::vector<ePtr<gFont> > litere_element(elemente);
	std::vector<int> ingrosare_element(elemente);
	/* cursivul (<i>) fara o fata cursiva adevarata (skinul da acelasi font ca la Regular, sau fontul ales de om, care
	   nu are varianta cursiva) se inclina desenat, dupa acoperirea randului */
	std::vector<bool> inclinat_element(elemente, false);
	const bool skin_cursiv = familie_skin[Subtitle_Italic] != familie_skin[Subtitle_Regular];
	std::vector<unsigned long> coduri;
	for (size_t i = 0; i < elemente; ++i)
	{
		const eTextElement &e = m_text_elements[i];
		Alegere al = alege(e.face, !a.font.empty());
		if (!a.font.empty())
		{
			puncteDeCod(e.text, coduri);
			if (!coduri.empty() && eTextPara::missingGlyphs(al.familie, coduri) != 0)
				al = alege(e.face, false);
		}
		litere_element[i] = new gFont(al.familie, marime_fel[e.face]);
		ingrosare_element[i] = al.ingrosare;
		inclinat_element[i] = e.face == Subtitle_Italic && !(skin_cursiv && al.familie == familie_skin[Subtitle_Italic]);
	}

	/* culoarea literelor pentru fiecare element */
	std::vector<gRGB> culori(elemente);
	for (unsigned int i = 0; i < elemente; ++i)
	{
		const eTextElement &e = m_text_elements[i];
		const eSubtitleStyle &stil = subtitleStyles[e.face];
		if (a.color >= 0)
			culori[i] = culoareRGB(a.color);
		else if (e.face == Subtitle_TTX)
			culori[i] = stil.have_foreground_color ? stil.foreground_color : e.color;
		else if (!stil.have_foreground_color && e.have_color)
			culori[i] = e.color;
		else if (stil.font)
			culori[i] = stil.foreground_color;
		else
			culori[i] = gRGB(255, 255, 255);
		if (e.translated)
		{
			/* traducerea sub original: culoarea ei, ca sa se deosebeasca de originalul de deasupra */
			const gRGB galben = culoareRGB(CULOARE_TRADUCERE_SUB_ORIGINAL);
			const bool ca_originalul = culori[i].r == galben.r && culori[i].g == galben.g && culori[i].b == galben.b;
			culori[i] = culoareRGB(ca_originalul ? CULOARE_TRADUCERE_REZERVA : CULOARE_TRADUCERE_SUB_ORIGINAL);
		}
	}
	const gRGB culoare_contur = culoareRGB(a.outline_color), culoare_umbra = culoareRGB(a.shadow_color),
		culoare_fundal = culoareRGB(a.background_color);

	/* randurile, de sus in jos */
	int latime_max = W - 2 * (W * MARGINE_LATERALA / 100);
	std::vector<eRandAsezat> randuri;
	int marime_max = 0, inaltime_max = 0;
	for (unsigned int i = 0; i < elemente && (int)randuri.size() < RANDURI_MAXIME; ++i)
	{
		gFont *litera = litere_element[i];
		int inaltime = (int)ceilf(motor->getLineHeight(*litera));
		if (inaltime <= 0)
			inaltime = litera->pointSize * 5 / 4;
		std::vector<std::string> bucati;
		const std::string &text = m_text_elements[i].text;
		size_t inceput = 0;
		while (inceput < text.size())
		{
			size_t sfarsit = text.find(char(10), inceput);
			if (sfarsit == std::string::npos)
				sfarsit = text.size();
			imparte(litera, text.substr(inceput, sfarsit - inceput), latime_max, bucati);
			inceput = sfarsit + 1;
		}
		for (unsigned int k = 0; k < bucati.size() && (int)randuri.size() < RANDURI_MAXIME; ++k)
		{
			eRandAsezat r;
			r.text = bucati[k];
			r.element = i;
			r.marime = litera->pointSize;
			r.inaltime_rand = inaltime;
			/* la 100%: inaltimea randului si cate 8% din litera deasupra si dedesubt */
			r.pas = ((inaltime + 2 * (litera->pointSize * 8 / 100)) * a.line_spacing + 50) / 100;
			r.spatiu_sus = (r.pas - inaltime) / 2;
			r.sus = 0;
			r.x0 = r.y0 = r.x1 = r.y1 = 0;
			randuri.push_back(r);
			if (litera->pointSize > marime_max)
				marime_max = litera->pointSize;
			if (inaltime > inaltime_max)
				inaltime_max = inaltime;
		}
	}
	if (randuri.empty())
		return;

	/* de jos in sus: ultimul rand se termina la inaltimea aleasa; textul citit (OCR) dintr-o pagina DVB care statea
	   in partea de sus a imaginii ramane sus: primul rand incepe la aceeasi distanta de marginea de sus */
	int jos = H - H * a.bottom / 100;
	int total = 0;
	for (unsigned int i = 0; i < randuri.size(); ++i)
		total += randuri[i].pas;
	int y = m_text_top ? H * a.bottom / 100 : jos - total;
	for (unsigned int i = 0; i < randuri.size(); ++i)
	{
		randuri[i].sus = y;
		y += randuri[i].pas;
	}

	/* marimile efectelor, dupa litera cea mai mare */
	int raza_contur = (CONTUR_LA_50[a.outline] * marime_max + 25) / 50;
	if (a.outline && raza_contur < 1)
		raza_contur = 1;
	int umbra_dx = 0, umbra_dy = 0, umbra_raza = 0;
	if (a.shadow)
	{
		umbra_dx = deplasareUmbra(UMBRA_DIRECTII[a.shadow_direction][0], a.shadow_distance, marime_max);
		umbra_dy = deplasareUmbra(UMBRA_DIRECTII[a.shadow_direction][1], a.shadow_distance, marime_max);
		if (a.shadow_softness)
		{
			umbra_raza = (UMBRA_RAZA_LA_50[a.shadow_softness] * marime_max + 25) / 50;
			if (umbra_raza < 1)
				umbra_raza = 1;
			if (umbra_raza > UMBRA_RAZA_MAXIMA)
				umbra_raza = UMBRA_RAZA_MAXIMA;	/* estompeaza: fereastra de cel mult 63, adica o litera de peste 250 de pixeli */
		}
	}
	int umbra_tarie = umbra_raza ? UMBRA_TARIE : 255;
	int umbra_departe = abs(umbra_dx) > abs(umbra_dy) ? abs(umbra_dx) : abs(umbra_dy);
	int fundal_x = marime_max * 35 / 100;
	int fundal_alfa = a.background ? (a.background_opacity * 255 + 50) / 100 : 0;
	int margine = raza_contur + (a.shadow ? umbra_departe + 3 * umbra_raza : 0) + 2;

	/* fiecare rand, alb pe negru, pe o ciorna: de acolo se ia numai acoperirea literelor */
	int ciorna_latime = W + 2 * marime_max, ciorna_inaltime = 3 * inaltime_max;
	ePtr<gPixmap> ciorna = new gPixmap(eSize(ciorna_latime, ciorna_inaltime), 32);
	gSurface *cs = ciorna->surface;
	ePtr<gDC> dc = new gDC(ciorna);
	dc->getClip() = gRegion(eRect(0, 0, cs->x, cs->y));	/* un gDC nou are zona de taiere goala */

	int cx0 = W, cy0 = H, cx1 = -1, cy1 = -1;	/* ce acopera poza compusa, pe ecran */
	for (unsigned int i = 0; i < randuri.size(); ++i)
	{
		eRandAsezat &r = randuri[i];
		ePtr<eTextPara> para = new eTextPara(eRect(marime_max, inaltime_max, W, r.inaltime_rand));
		para->setFont(litere_element[r.element]);
		if (para->renderString(r.text.c_str(), 0) < 0)
			continue;
		/* numai locul literelor se curata si se cerceteaza, nu toata ciorna (ar fi 1,6 MB curatati si 400 000 de
		   pixeli cititi la fiecare rand): pe inaltime cutia glifelor (exact cat se deseneaza), pe latime cu o litera
		   intreaga in plus de fiecare parte (in cutie, latimea unei glife e pasul ei, iar o litera cursiva trece de el) */
		const eRect &cutie = para->getBoundBox();
		int zx0 = cutie.left() - marime_max, zx1 = (cutie.right() > cutie.left() ? cutie.right() : cutie.left()) + marime_max;
		int zy0 = cutie.top() - 2, zy1 = (cutie.bottom() > cutie.top() ? cutie.bottom() : cutie.top()) + 2;
		if (zx0 < 0)
			zx0 = 0;
		if (zy0 < 0)
			zy0 = 0;
		if (zx1 > cs->x)
			zx1 = cs->x;
		if (zy1 > cs->y)
			zy1 = cs->y;
		if (zx1 <= zx0 || zy1 <= zy0)
			continue;
		for (int yy = zy0; yy < zy1; yy++)
			memset(((unsigned char *)cs->data) + (long)yy * cs->stride + zx0 * 4, 0, (size_t)(zx1 - zx0) * 4);
		para->blit(*dc, ePoint(0, 0), gRGB(0, 0, 0, 255), gRGB(255, 255, 255, 255));

		int lx0 = cs->x, ly0 = cs->y, lx1 = -1, ly1 = -1;
		for (int yy = zy0; yy < zy1; yy++)
		{
			const unsigned char *rand = ((const unsigned char *)cs->data) + (long)yy * cs->stride;
			for (int xx = zx0; xx < zx1; xx++)
				if (rand[xx * 4 + 2])
				{
					if (xx < lx0)
						lx0 = xx;
					if (xx > lx1)
						lx1 = xx;
					if (yy < ly0)
						ly0 = yy;
					ly1 = yy;
				}
		}
		if (lx1 < 0)
			continue;	/* numai spatii */
		int lw = lx1 - lx0 + 1, lh = ly1 - ly0 + 1;
		r.acoperire.resize((size_t)lw * lh);
		for (int yy = 0; yy < lh; yy++)
		{
			const unsigned char *rand = ((const unsigned char *)cs->data) + (long)(yy + ly0) * cs->stride;
			for (int xx = 0; xx < lw; xx++)
			{
				int v = rand[(xx + lx0) * 4 + 2] * 255 / ACOPERIRE_PLINA;
				r.acoperire[(size_t)yy * lw + xx] = (unsigned char)(v > 255 ? 255 : v);
			}
		}
		/* ingrosarea desenata: la 50 de pixeli un pixel de fiecare parte (cam cat varianta groasa fata de cea
		   obisnuita), crescand cu litera */
		int ingrosare = ingrosare_element[r.element] * ((r.marime + 24) / 48 > 1 ? (r.marime + 24) / 48 : 1);
		if (ingrosare > 0)
		{
			ingroasa(r.acoperire, lw, lh, ingrosare);
			lx0 -= ingrosare;
			lx1 += ingrosare;
			lw += 2 * ingrosare;
		}
		if (inclinat_element[r.element])
		{
			int noua = inclina(r.acoperire, lw, lh, 212);
			lx1 += noua - lw;
			lw = noua;
		}
		/* cerneala centrata pe latime; sus-ul zonei textului din ciorna (inaltime_max) cade la sus + spatiul de sus */
		int dx = W / 2 - (lx0 + lx1 + 1) / 2;
		int dy = r.sus + r.spatiu_sus - inaltime_max;
		r.x0 = lx0 + dx;
		r.x1 = lx1 + dx;
		r.y0 = ly0 + dy;
		r.y1 = ly1 + dy;
		int ex0 = r.x0 - margine, ey0 = r.y0 - margine, ex1 = r.x1 + margine, ey1 = r.y1 + margine;
		if (fundal_alfa)
		{
			if (r.x0 - fundal_x < ex0)
				ex0 = r.x0 - fundal_x;
			if (r.x1 + fundal_x > ex1)
				ex1 = r.x1 + fundal_x;
			if (r.sus < ey0)
				ey0 = r.sus;
			if (r.sus + r.pas - 1 > ey1)
				ey1 = r.sus + r.pas - 1;
		}
		if (ex0 < cx0)
			cx0 = ex0;
		if (ey0 < cy0)
			cy0 = ey0;
		if (ex1 > cx1)
			cx1 = ex1;
		if (ey1 > cy1)
			cy1 = ey1;
	}
	if (cx0 < 0)
		cx0 = 0;
	if (cy0 < 0)
		cy0 = 0;
	if (cx1 > W - 1)
		cx1 = W - 1;
	if (cy1 > H - 1)
		cy1 = H - 1;
	if (cx1 < cx0 || cy1 < cy0)
		return;
	int cw = cx1 - cx0 + 1, ch = cy1 - cy0 + 1;
	size_t pixeli = (size_t)cw * ch;

	/* literele puse pe poza, si al carui element e fiecare pixel (pentru culoare) */
	std::vector<unsigned char> litere(pixeli, 0), al_cui(pixeli, 0);
	for (unsigned int i = 0; i < randuri.size(); ++i)
	{
		const eRandAsezat &r = randuri[i];
		if (r.acoperire.empty())
			continue;
		int lw = r.x1 - r.x0 + 1, lh = r.y1 - r.y0 + 1;
		for (int yy = 0; yy < lh; yy++)
		{
			int py = r.y0 + yy - cy0;
			if (py < 0 || py >= ch)
				continue;
			/* xx cu r.x0 + xx - cx0 in poza; unde litera noua e mai tare, ea si elementul ei */
			int xa = cx0 - r.x0 > 0 ? cx0 - r.x0 : 0, xb = cw + cx0 - r.x0 < lw ? cw + cx0 - r.x0 : lw;
			if (xb <= xa)
				continue;
			const unsigned char *sursa = &r.acoperire[(size_t)yy * lw + xa];
			unsigned char *pe_poza = &litere[(size_t)py * cw + r.x0 + xa - cx0], *al = &al_cui[(size_t)py * cw + r.x0 + xa - cx0];
			unsigned char element = (unsigned char)r.element;
			v16u8 elementul = v16u8{} + element;
			int n = xb - xa, xx = 0;
			for (; xx + 16 <= n; xx += 16)
			{
				v16u8 v = incarca16(sursa + xx), l = incarca16(pe_poza + xx);
				pune16(pe_poza + xx, v > l ? v : l);
				pune16(al + xx, v > l ? elementul : incarca16(al + xx));
			}
			for (; xx < n; xx++)
				if (sursa[xx] > pe_poza[xx])
				{
					pe_poza[xx] = sursa[xx];
					al[xx] = element;
				}
		}
	}

	/* fundalul: cate un dreptunghi pe rand (cat textul plus putin in lateral, cat tot randul in sus) sau o cutie pentru
	   toate randurile; cu randuri foarte apropiate, dreptunghiul acopera macar literele */
	std::vector<unsigned char> fundal;
	if (fundal_alfa)
	{
		fundal.assign(pixeli, 0);
		int bx0 = cw, by0 = ch, bx1 = -1, by1 = -1;
		for (unsigned int i = 0; i < randuri.size(); ++i)
		{
			const eRandAsezat &r = randuri[i];
			if (r.acoperire.empty())
				continue;
			int fx0 = r.x0 - fundal_x - cx0, fx1 = r.x1 + fundal_x - cx0;
			int fy0 = (r.sus < r.y0 ? r.sus : r.y0) - cy0, fy1 = (r.sus + r.pas - 1 > r.y1 ? r.sus + r.pas - 1 : r.y1) - cy0;
			if (a.background == 2)
			{
				/* cutia: se strang marginile tuturor randurilor, se umple o data la sfarsit */
				if (fx0 < bx0)
					bx0 = fx0;
				if (fy0 < by0)
					by0 = fy0;
				if (fx1 > bx1)
					bx1 = fx1;
				if (fy1 > by1)
					by1 = fy1;
				continue;
			}
			if (fx0 < 0)
				fx0 = 0;
			if (fy0 < 0)
				fy0 = 0;
			if (fx1 > cw - 1)
				fx1 = cw - 1;
			if (fy1 > ch - 1)
				fy1 = ch - 1;
			if (fx1 < fx0)
				continue;
			for (int yy = fy0; yy <= fy1; yy++)
				memset(&fundal[(size_t)yy * cw + fx0], fundal_alfa, fx1 - fx0 + 1);
		}
		if (a.background == 2 && bx1 >= 0)
		{
			if (bx0 < 0)
				bx0 = 0;
			if (by0 < 0)
				by0 = 0;
			if (bx1 > cw - 1)
				bx1 = cw - 1;
			if (by1 > ch - 1)
				by1 = ch - 1;
			for (int yy = by0; yy <= by1 && bx1 >= bx0; yy++)
				memset(&fundal[(size_t)yy * cw + bx0], fundal_alfa, bx1 - bx0 + 1);
		}
	}

	/* conturul: literele latite cu un disc cu marginea moale (rotund, fara trepte) */
	std::vector<unsigned char> contur;
	if (raza_contur > 0)
	{
		contur.resize(pixeli);
		contureaza(&litere[0], &contur[0], cw, ch, raza_contur);
	}

	/* umbra: forma literelor (cu contur, daca e) mutata pe directia aleasa, apoi estompata (umbra moale) */
	std::vector<unsigned char> umbra;
	if (a.shadow)
	{
		umbra.assign(pixeli, 0);
		/* pe fiecare rand, pixelii [x0, x1) ai umbrei vin din x - umbra_dx, randul yy din yy - umbra_dy */
		int x0 = umbra_dx > 0 ? umbra_dx : 0, x1 = umbra_dx < 0 ? cw + umbra_dx : cw;
		int n = x1 - x0;
		for (int yy = 0; yy < ch && n > 0; yy++)
		{
			int sy = yy - umbra_dy;
			if (sy < 0 || sy >= ch)
				continue;
			size_t s = (size_t)sy * cw + x0 - umbra_dx;
			unsigned char *d = &umbra[(size_t)yy * cw + x0];
			memcpy(d, &litere[s], n);
			if (!contur.empty())
				maximIn(d, &contur[s], n);
		}
		if (umbra_raza > 0)
		{
			std::vector<unsigned char> ajutor(pixeli);
			estompeaza(&umbra[0], &ajutor[0], cw, ch, umbra_raza);
		}
	}

	/* compunerea, de jos in sus: fundal, umbra, contur, litere; in poza, alfa drept (0xFF = opac). Acelasi rezultat ca
	   stratul peste strat, pixel cu pixel (peste(), cu aceleasi rotunjiri), dar:
	   - cu litere fara transparenta (fundalul, umbra si conturul sunt opace, cu acoperirea lor), cate 8 pixeli
	     deodata (strat()); un strat negru peste nimic colorat lasa R, G, B pe 0 si nu le mai calculeaza (asa e la
	     valorile de la inceput: umbra si conturul negre); x / 255 fara impartire (imparte255);
	   - din premultiplicat in drept se imparte numai unde trebuie (alfa intre 1 si 254 si o culoare), prin
	     inmultire cu inversul: n / A == (n * inversul[A]) >> 24 pentru orice n < 65536 si A de la 1 la 255
	     (inversul rotunjit in sus: n * eroare < 2^24);
	   - altfel (litere cu transparenta, din skin), pixel cu pixel, cu scurtaturi pentru pixelii goi si cei acoperiti
	     de tot. */
	ePtr<gPixmap> poza = new gPixmap(eSize(cw, ch), 32);
	gSurface *ps = poza->surface;
	unsigned int inversul[256];
	inversul[0] = 0;
	for (unsigned int k = 1; k < 256; k++)
		inversul[k] = ((1u << 24) + k - 1) / k;
	bool repede = true;
	bool o_culoare = true;
	for (unsigned int i = 0; i < culori.size(); ++i)
	{
		if (culori[i].a)
			repede = false;
		if (culori[i].r != culori[0].r || culori[i].g != culori[0].g || culori[i].b != culori[0].b)
			o_culoare = false;
	}
	/* care straturi calculeaza R, G, B: unul colorat, sau unul negru peste ceva colorat */
	bool rgb_fundal = !fundal.empty() && !eNegru(culoare_fundal);
	bool colorat = rgb_fundal;
	bool rgb_umbra = !umbra.empty() && (colorat || !eNegru(culoare_umbra));
	colorat = colorat || rgb_umbra;
	bool rgb_contur = !contur.empty() && (colorat || !eNegru(culoare_contur));
	colorat = colorat || rgb_contur;
	/* culoarea literelor pe fiecare pixel, cand pe pagina sunt mai multe (teletext cu vorbitori colorati) */
	std::vector<unsigned char> litera_r, litera_g, litera_b;
	if (repede && !o_culoare)
	{
		litera_r.assign(pixeli, 0);
		litera_g.assign(pixeli, 0);
		litera_b.assign(pixeli, 0);
		for (size_t p = 0; p < pixeli; p++)
			if (litere[p])
			{
				const gRGB &c = culori[al_cui[p]];
				litera_r[p] = c.r;
				litera_g[p] = c.g;
				litera_b[p] = c.b;
			}
	}
	for (int yy = 0; yy < ch; yy++)
	{
		unsigned char *rand = ((unsigned char *)ps->data) + (long)yy * ps->stride;
		int xx = 0;
		if (repede)
			for (; xx + 8 <= cw; xx += 8)
			{
				size_t p = (size_t)yy * cw + xx;
				v8u16 li = incarca8(&litere[p]);
				v8u16 A = v8u16{}, R = v8u16{}, G = v8u16{}, B = v8u16{};
				if (!fundal.empty())
					strat(A, R, G, B, incarca8(&fundal[p]), culoare_fundal, rgb_fundal);
				if (!umbra.empty())
					strat(A, R, G, B, imparte255(incarca8(&umbra[p]) * (unsigned short)umbra_tarie), culoare_umbra, rgb_umbra);
				if (!contur.empty())
					strat(A, R, G, B, incarca8(&contur[p]), culoare_contur, rgb_contur);
				v8u16 cr, cg, cb;
				if (o_culoare)
				{
					cr = v8u16{} + (unsigned short)culori[0].r;
					cg = v8u16{} + (unsigned short)culori[0].g;
					cb = v8u16{} + (unsigned short)culori[0].b;
				}
				else
				{
					cr = incarca8(&litera_r[p]);
					cg = incarca8(&litera_g[p]);
					cb = incarca8(&litera_b[p]);
				}
				if (colorat)
				{
					v8u16 rest = 255 - li;
					R = imparte255(cr * li + R * rest + 127);
					G = imparte255(cg * li + G * rest + 127);
					B = imparte255(cb * li + B * rest + 127);
				}
				else
				{
					R = imparte255(cr * li + 127);
					G = imparte255(cg * li + 127);
					B = imparte255(cb * li + 127);
				}
				A = li + imparte255(A * (255 - li) + 127);
				/* B, G, R, A in ordinea din memorie: bg = B | G << 8 si ra = R | A << 8, intretesute */
				v8u16 bg = B | (G << 8), ra = R | (A << 8);
				v8u16 p0 = __builtin_shuffle(bg, ra, (v8u16){ 0, 8, 1, 9, 2, 10, 3, 11 });
				v8u16 p1 = __builtin_shuffle(bg, ra, (v8u16){ 4, 12, 5, 13, 6, 14, 7, 15 });
				unsigned char *o = rand + xx * 4;
				memcpy(o, &p0, 16);
				memcpy(o + 16, &p1, 16);
				/* alfa 255: culoarea e chiar R, G, B; fara culoare: 0. Numai pe marginea literelor, peste ceva
				   semitransparent, se imparte */
				v8u16 de_impartit = (v8u16)((A != 255) & ((R | G | B) != 0));
				unsigned long long jumatati[2];
				memcpy(jumatati, &de_impartit, 16);
				if (!(jumatati[0] | jumatati[1]))
					continue;
				for (int k = 0; k < 8; k++)
				{
					if (!de_impartit[k])
						continue;
					unsigned long long inv = inversul[A[k]];
					int r = (int)(((unsigned long long)(R[k] * 255 + A[k] / 2) * inv) >> 24);
					int g = (int)(((unsigned long long)(G[k] * 255 + A[k] / 2) * inv) >> 24);
					int b = (int)(((unsigned long long)(B[k] * 255 + A[k] / 2) * inv) >> 24);
					o[k * 4 + 0] = (unsigned char)(b > 255 ? 255 : b);
					o[k * 4 + 1] = (unsigned char)(g > 255 ? 255 : g);
					o[k * 4 + 2] = (unsigned char)(r > 255 ? 255 : r);
				}
			}
		for (; xx < cw; xx++)
		{
			size_t p = (size_t)yy * cw + xx;
			unsigned char *o = rand + xx * 4;
			int li = litere[p], co = contur.empty() ? 0 : contur[p];
			const gRGB &c = culori[al_cui[p]];
			if (li == 255 && c.a == 0)
			{
				o[0] = c.b;
				o[1] = c.g;
				o[2] = c.r;
				o[3] = 255;
				continue;
			}
			if (li == 0 && co == 255)
			{
				o[0] = culoare_contur.b;
				o[1] = culoare_contur.g;
				o[2] = culoare_contur.r;
				o[3] = 255;
				continue;
			}
			int fa = fundal.empty() ? 0 : fundal[p], um = umbra.empty() ? 0 : umbra[p];
			if (!li && !co && !fa && !um)
			{
				o[0] = o[1] = o[2] = o[3] = 0;
				continue;
			}
			int A = 0, R = 0, G = 0, B = 0;
			peste(A, R, G, B, fa, culoare_fundal);
			peste(A, R, G, B, um * umbra_tarie / 255, culoare_umbra);
			peste(A, R, G, B, co, culoare_contur);
			if (li)
				peste(A, R, G, B, li * (255 - c.a) / 255, c);
			if (A <= 0)
			{
				o[0] = o[1] = o[2] = o[3] = 0;
				continue;
			}
			unsigned long long inv = inversul[A > 255 ? 255 : A];
			int r = (int)(((unsigned long long)(R * 255 + A / 2) * inv) >> 24);
			int g = (int)(((unsigned long long)(G * 255 + A / 2) * inv) >> 24);
			int b = (int)(((unsigned long long)(B * 255 + A / 2) * inv) >> 24);
			o[0] = (unsigned char)(b > 255 ? 255 : b);
			o[1] = (unsigned char)(g > 255 ? 255 : g);
			o[2] = (unsigned char)(r > 255 ? 255 : r);
			o[3] = (unsigned char)(A > 255 ? 255 : A);
		}
	}
	m_text_pixmap = poza;
	m_text_position = ePoint(cx0, cy0);
}

/* ------------------------------------------------------------------ desenarea */

int eSubtitleWidget::event(int event, void *data, void *data2)
{
	switch (event)
	{
	case evtPaint:
	{
		ePtr<eWindowStyle> style;
		gPainter &painter = *(gPainter*)data2;

		getStyle(style);
		eWidget::event(event, data, data2);

		if (m_pixmap)
		{
			eRect r = m_pixmap_dest;
			r.scale(size().width(), 720, size().height(), 576);
			painter.blitScale(m_pixmap, r);
		} else if (m_text_ok)
		{
			/* the subtitle window was just cleared (transparent): a copy keeps the alpha exactly. A transparent
			   widget (the settings preview) is drawn over what is behind it, so there the text is blended. */
			if (m_text_pixmap)
				painter.blit(m_text_pixmap, m_text_position, eRect(), isTransparent() ? gPainter::BT_ALPHABLEND : 0);
		}
		else if (m_dvb_page_ok)
		{
			for (std::list<eDVBSubtitleRegion>::iterator it(m_dvb_page.m_regions.begin()); it != m_dvb_page.m_regions.end(); ++it)
			{
				eRect r = eRect(it->m_position, it->m_pixmap->size());
				r.scale(size().width(), m_dvb_page.m_display_size.width(), size().height(),  m_dvb_page.m_display_size.height());
				painter.blitScale(it->m_pixmap, r);
			}
		}
		return 0;
	}
	default:
		return eWidget::event(event, data, data2);
	}
}

void eSubtitleWidget::setFontStyle(subfont_t face, gFont *font, int haveColor, const gRGB &col, const gRGB &shadowCol, const ePoint &shadowOffset)
{
	/* only real styles: Subtitle_MAX is the number of styles, writing there would hit the memory after the table */
	if (face < Subtitle_TTX || face >= Subtitle_MAX)
	{
		eWarning("[eSubtitleWidget] subtitle style %d ignored (valid styles are 0..%d)", (int)face, (int)Subtitle_MAX - 1);
		return;
	}
	subtitleStyles[face].font = font;
	subtitleStyles[face].have_foreground_color = haveColor;
	subtitleStyles[face].foreground_color = col;
	subtitleStyles[face].shadow_color = shadowCol;
	subtitleStyles[face].shadow_offset = shadowOffset;
}

static int inInterval(const char *what, int value, int lowest, int highest)
{
	if (value < lowest || value > highest)
	{
		eWarning("[eSubtitleWidget] text subtitle %s %d is out of range %d..%d", what, value, lowest, highest);
		return value < lowest ? lowest : highest;
	}
	return value;
}

/* true daca aliasul e al unui font dat lui addFont (skinul, fonturile imaginii, cele descarcate) */
static bool fontInregistrat(const std::string &alias)
{
	fontRenderClass *motor = fontRenderClass::getInstance();
	if (!motor || alias.empty())
		return false;
	ePtr<Font> font;
	motor->getFont(font, alias, 20);
	return (bool)font;
}

bool eSubtitleWidget::eTextStyle::operator==(const eTextStyle &o) const
{
	return font == o.font && font_bold == o.font_bold && weight == o.weight && size == o.size && color == o.color
		&& outline == o.outline && outline_color == o.outline_color && shadow == o.shadow
		&& shadow_color == o.shadow_color && shadow_direction == o.shadow_direction
		&& shadow_distance == o.shadow_distance && shadow_softness == o.shadow_softness && background == o.background
		&& background_color == o.background_color && background_opacity == o.background_opacity && bottom == o.bottom
		&& line_spacing == o.line_spacing;
}

void eSubtitleWidget::setStyle(const std::string &font, const std::string &font_bold, int weight, int size, int color,
	int outline, int outline_color, int shadow, int shadow_color, int shadow_direction, int shadow_distance,
	int shadow_softness, int background, int background_color, int background_opacity, int bottom, int line_spacing)
{
	eTextStyle a;
	/* fontul se cauta o data, aici: unul neinregistrat (sters, alt skin) ar lasa randurile goale, deci se ia al skinului */
	a.font = font;
	a.font_bold = font_bold;
	if (!a.font.empty() && !fontInregistrat(a.font))
	{
		eWarning("[eSubtitleWidget] text subtitle font '%s' is not registered, the skin fonts are used", a.font.c_str());
		a.font.clear();
	}
	if (a.font.empty())
		a.font_bold.clear();
	else if (!a.font_bold.empty() && !fontInregistrat(a.font_bold))
	{
		eWarning("[eSubtitleWidget] text subtitle bold font '%s' is not registered, '%s' is thickened", a.font_bold.c_str(), a.font.c_str());
		a.font_bold.clear();
	}
	a.weight = inInterval("weight", weight, 0, 3);
	a.size = inInterval("size", size, 50, 200);
	a.color = inInterval("color", color, -1, 16777215);
	a.outline = inInterval("outline", outline, 0, 4);
	a.outline_color = inInterval("outline_color", outline_color, 0, 16777215);
	a.shadow = inInterval("shadow", shadow, 0, 1);
	a.shadow_color = inInterval("shadow_color", shadow_color, 0, 16777215);
	a.shadow_direction = inInterval("shadow_direction", shadow_direction, 0, 7);
	a.shadow_distance = inInterval("shadow_distance", shadow_distance, 25, 400);
	a.shadow_softness = inInterval("shadow_softness", shadow_softness, 0, 2);
	a.background = inInterval("background", background, 0, 2);
	a.background_color = inInterval("background_color", background_color, 0, 16777215);
	a.background_opacity = inInterval("background_opacity", background_opacity, 0, 100);
	a.bottom = inInterval("bottom", bottom, 0, 40);
	a.line_spacing = inInterval("line_spacing", line_spacing, 50, 200);
	bool la_fel = a == s_style;
	s_style = a;
	eDebug("[eSubtitleWidget] text subtitles: font '%s' / '%s', weight %d, size %d%%, color %d, outline %d #%06x, "
		"shadow %d #%06x direction %d distance %d%% softness %d, background %d #%06x %d%%, bottom %d%%, line spacing %d%%",
		a.font.c_str(), a.font_bold.c_str(), a.weight, a.size, a.color, a.outline, a.outline_color, a.shadow,
		a.shadow_color, a.shadow_direction, a.shadow_distance, a.shadow_softness, a.background, a.background_color,
		a.background_opacity, a.bottom, a.line_spacing);
	/* nothing changed (Cancel in the settings sends one notification per setting): the text stays as it is */
	if (la_fel)
		return;
	/* the text already on screen (a teletext page, the preview) is laid out again with the new look */
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		if ((*it)->m_text_ok)
		{
			std::vector<eTextElement> elemente = (*it)->m_text_elements;
			(*it)->setTextElements(elemente);
		}
}

/* ------------------------------------------------------------------ OCR-ul paginilor DVB (textul citit din poze) */

/*
 * Subtitrarile DVB citite ca text si desenate cu „Aspectul subtitrărilor”. Recunoasterea o face serviciul hds-ocr
 * (proces separat: libtesseract e Apache-2.0), cu care vorbeste Components/HdsOcrSubtitrari.py; aici numai: pagina
 * DVB data functiei din Python, apoi textul primit desenat ca teletextul (setTextElements + layoutText) sau poza,
 * daca textul nu e destul de sigur.
 *  - Widgetul e facut de serviciu (eDVBServicePlay::enableSubtitles), nu de Python: de aceea functiile sunt statice,
 *    iar raspunsul isi gaseste pagina dupa generatie (o numaratoare pentru toate widgeturile, niciodata 0).
 *  - Pixelii se copiaza in Python cand pagina e data: parserul poate scrie mai tarziu in aceeasi poza a regiunii.
 *  - O pagina DVB soseste inainte de momentul afisarii (serviciul o tine in coada pana la PTS-ul ei). Cu
 *    prefetchPage, serviciul o da aici la sosire: cererea pleaca atunci, iar raspunsul (text sau poza) se tine langa
 *    pagina pana o afiseaza setPage; o pagina cu textul gata se afiseaza direct ca text, fara asteptare. O pagina
 *    care nu a venit pe drumul acesta se cere la afisare, ca inainte.
 *  - Functia din Python poate raspunde chiar in timpul apelului (o pagina pe care modulul o stie deja): generatia
 *    e pusa inainte de apel, deci raspunsul isi gaseste pagina si atunci.
 *  - Nimic nu asteapta aici. Pana vine textul unei pagini afisate nu se arata nimic, cel mult s_ocr_wait_ms; apoi
 *    poza, iar textul, daca mai vine, ii ia locul. Un raspuns pentru o pagina care nu mai e pe ecran sau in
 *    asteptare (alta pagina, stearsa, widget distrus) nu schimba nimic.
 *  - Orice greseala din Python (exceptie, raspuns stricat) = poza, ca fara OCR; eroarea Python nu ramane pusa.
 */

/* cate pagini sosite si neafisate inca se tin (cu raspunsul lor); la un sir mai lung, cele mai vechi pleaca */
static const unsigned int OCR_PREFETCH_MAX = 8;
/* peste atat, momentul afisarii nu e de crezut (serviciul DVB arata atunci pagina pe loc) */
static const int OCR_PREFETCH_MAX_DELAY_MS = 20000;

void eSubtitleWidget::setOcrHandler(ePyObject handler)
{
	ePyObject nou;
	if (handler && (PyObject*)handler != Py_None)
	{
		if (PyCallable_Check(handler))
			nou = handler;
		else
			eWarning("[eSubtitleWidget] OCR handler is not callable, OCR stays off");
	}
	if (nou)
		Py_INCREF(nou);
	if (s_ocr_handler)
		Py_DECREF(s_ocr_handler);
	s_ocr_handler = nou;
	eDebug("[eSubtitleWidget] OCR of the DVB subtitles %s", s_ocr_handler ? "on" : "off");
	if (!s_ocr_handler)
	{
		/* paginile care inca asteptau textul arata poza; cele sosite si neafisate o vor arata la afisare */
		for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		{
			if ((*it)->m_ocr_generation)
				(*it)->showDvbBitmap();
			for (std::list<eOcrPrefetch>::iterator p = (*it)->m_ocr_prefetch.begin(); p != (*it)->m_ocr_prefetch.end(); ++p)
				if (p->state == OCR_WAITING)
					p->state = OCR_PICTURE;
		}
	}
}

void eSubtitleWidget::setOcrWait(int ms)
{
	s_ocr_wait_ms = inInterval("OCR wait", ms, 0, 5000);
}

int eSubtitleWidget::nextOcrGeneration()
{
	/* niciodata 0 (0 = nicio pagina in asteptare) */
	s_ocr_generation = s_ocr_generation >= 0x3FFFFFFF ? 1 : s_ocr_generation + 1;
	return s_ocr_generation;
}

/* regiunile paginii, pentru functia din Python: [(x, y, latime, inaltime, pas, paleta, pixeli)]; o referinta noua, sau
   nula daca pagina nu se poate da (numai poze de 8 biti cu paleta, asa cum le face eDVBSubtitleParser) */
ePyObject eSubtitleWidget::ocrRegions(const eDVBSubtitlePage &page)
{
	ePyObject regiuni = PyList_New(0);
	if (!regiuni)
	{
		PyErr_Clear();
		return ePyObject();
	}
	for (std::list<eDVBSubtitleRegion>::const_iterator it(page.m_regions.begin()); it != page.m_regions.end(); ++it)
	{
		gSurface *s = it->m_pixmap ? it->m_pixmap->surface : 0;
		if (!s || s->bpp != 8 || !s->data || s->x <= 0 || s->y <= 0 || s->stride < s->x || s->clut.colors <= 0
			|| s->clut.colors > 256 || !s->clut.data)
		{
			Py_DECREF(regiuni);
			return ePyObject();
		}
		ePyObject paleta = PyList_New(s->clut.colors);
		ePyObject pixeli = PyBytes_FromStringAndSize((const char*)s->data, (Py_ssize_t)s->stride * s->y);
		ePyObject regiune = PyTuple_New(7);
		if (!paleta || !pixeli || !regiune)
		{
			PyErr_Clear();
			Py_XDECREF(paleta);
			Py_XDECREF(pixeli);
			Py_XDECREF(regiune);
			Py_DECREF(regiuni);
			return ePyObject();
		}
		for (int i = 0; i < s->clut.colors; ++i)
		{
			const gRGB &c = s->clut.data[i];
			ePyObject culoare = PyTuple_New(4);
			PyTuple_SET_ITEM(culoare, 0, PyLong_FromLong(c.r));
			PyTuple_SET_ITEM(culoare, 1, PyLong_FromLong(c.g));
			PyTuple_SET_ITEM(culoare, 2, PyLong_FromLong(c.b));
			PyTuple_SET_ITEM(culoare, 3, PyLong_FromLong(c.a));
			PyList_SET_ITEM(paleta, i, culoare);
		}
		PyTuple_SET_ITEM(regiune, 0, PyLong_FromLong(it->m_position.x()));
		PyTuple_SET_ITEM(regiune, 1, PyLong_FromLong(it->m_position.y()));
		PyTuple_SET_ITEM(regiune, 2, PyLong_FromLong(s->x));
		PyTuple_SET_ITEM(regiune, 3, PyLong_FromLong(s->y));
		PyTuple_SET_ITEM(regiune, 4, PyLong_FromLong(s->stride));
		PyTuple_SET_ITEM(regiune, 5, paleta);
		PyTuple_SET_ITEM(regiune, 6, pixeli);
		PyList_Append(regiuni, regiune);
		Py_DECREF(regiune);
	}
	return regiuni;
}

/* functia din Python cu (generatie, regiuni, intarziere); ia referinta lui `regions`. true = raspunsul vine (sau a
   venit deja, in timpul apelului) prin setOcrText / showOcrBitmap */
bool eSubtitleWidget::callOcrHandler(int generation, ePyObject regions, int delay_ms)
{
	if (!s_ocr_handler)
	{
		Py_DECREF(regions);
		return false;
	}
	ePyObject argumente = PyTuple_New(3);
	PyTuple_SET_ITEM(argumente, 0, PyLong_FromLong(generation));
	PyTuple_SET_ITEM(argumente, 1, regions);
	PyTuple_SET_ITEM(argumente, 2, PyLong_FromLong(delay_ms));
	/* the handler is kept alive during the call even if it replaces itself (setOcrHandler from Python) */
	ePyObject functie = s_ocr_handler;
	Py_INCREF(functie);
	ePyObject rezultat = PyObject_CallObject(functie, argumente);
	Py_DECREF(functie);
	Py_DECREF(argumente);
	if (!rezultat)
	{
		eWarning("[eSubtitleWidget] the OCR handler failed, the picture is shown");
		PyErr_Print();
		return false;
	}
	int da = PyObject_IsTrue(rezultat);
	Py_DECREF(rezultat);
	if (da < 0)
		PyErr_Clear();
	return da == 1;
}

void eSubtitleWidget::dropPrefetch(std::list<eOcrPrefetch>::iterator it)
{
	if (it->state == OCR_TEXT && it->lines)
		Py_DECREF(it->lines);
	m_ocr_prefetch.erase(it);
}

/* pagina sosita, data functiei din Python acum; raspunsul se tine langa ea pana o afiseaza setPage */
void eSubtitleWidget::prefetchPage(const eDVBSubtitlePage &p, int delay_ms)
{
	if (!s_ocr_handler || p.m_regions.empty())
		return;
	ePyObject regiuni = ocrRegions(p);
	if (!regiuni)
		return;
	while (m_ocr_prefetch.size() >= OCR_PREFETCH_MAX)
		dropPrefetch(m_ocr_prefetch.begin());
	eOcrPrefetch e;
	e.generation = nextOcrGeneration();
	e.show_time = p.m_show_time;
	for (std::list<eDVBSubtitleRegion>::const_iterator it(p.m_regions.begin()); it != p.m_regions.end(); ++it)
	{
		e.pictures.push_back(it->m_pixmap);
		e.positions.push_back(it->m_position);
	}
	e.state = OCR_WAITING;
	m_ocr_prefetch.push_back(e);
	int generatie = e.generation;
	if (delay_ms < 0 || delay_ms > OCR_PREFETCH_MAX_DELAY_MS)
		delay_ms = 0;
	bool da = callOcrHandler(generatie, regiuni, delay_ms);
	if (!da)
	{
		/* fara OCR pentru pagina asta: la afisare, poza pe loc */
		for (std::list<eOcrPrefetch>::iterator it = m_ocr_prefetch.begin(); it != m_ocr_prefetch.end(); ++it)
			if (it->generation == generatie && it->state == OCR_WAITING)
				it->state = OCR_PICTURE;
	}
}

/* Pagina DVB de acum (m_dvb_page), la afisare. 0 = fara OCR (poza), 1 = raspunsul vine mai tarziu (m_ocr_generation
   pus), 2 = raspunsul a venit deja (text sau poza puse). Intai pagina sosita inainte (prefetchPage), apoi cererea. */
int eSubtitleWidget::askOcr()
{
	if (m_dvb_page.m_regions.empty())
		return 0;
	/* pagina e una sosita inainte? (acelasi moment al afisarii, aceleasi poze in aceleasi locuri) */
	for (std::list<eOcrPrefetch>::iterator it = m_ocr_prefetch.begin(); it != m_ocr_prefetch.end(); ++it)
	{
		if (it->show_time != m_dvb_page.m_show_time || it->pictures.size() != m_dvb_page.m_regions.size())
			continue;
		bool aceeasi = true;
		unsigned int k = 0;
		for (std::list<eDVBSubtitleRegion>::iterator r(m_dvb_page.m_regions.begin()); r != m_dvb_page.m_regions.end(); ++r, ++k)
			if ((gPixmap*)it->pictures[k] != (gPixmap*)r->m_pixmap || it->positions[k] != r->m_position)
			{
				aceeasi = false;
				break;
			}
		if (!aceeasi)
			continue;
		int generatie = it->generation;
		int stare = it->state;
		ePyObject linii = it->lines;
		it->state = OCR_WAITING;	/* referinta liniilor trece aici */
		/* paginile sosite inaintea ei si neafisate nu se mai afiseaza */
		while (m_ocr_prefetch.begin() != it)
			dropPrefetch(m_ocr_prefetch.begin());
		m_ocr_prefetch.erase(it);
		if (stare == OCR_TEXT)
		{
			showOcrText(linii);
			Py_DECREF(linii);
			return 2;
		}
		if (stare == OCR_PICTURE)
			return 0;
		m_ocr_generation = generatie;
		return 1;
	}
	if (!s_ocr_handler)
		return 0;
	ePyObject regiuni = ocrRegions(m_dvb_page);
	if (!regiuni)
		return 0;
	int generatie = nextOcrGeneration();
	m_ocr_generation = generatie;
	bool da = callOcrHandler(generatie, regiuni, -1);
	if (m_ocr_generation != generatie)
		return 2;			/* setOcrText / showOcrBitmap in timpul apelului */
	if (!da)
	{
		m_ocr_generation = 0;
		return 0;
	}
	return 1;
}

/* timpul de asteptare a trecut: se arata poza; textul, daca mai vine, ii ia locul */
void eSubtitleWidget::ocrWaitOver()
{
	if (!m_ocr_generation || m_dvb_page_ok || m_text_ok)
		return;
	m_dvb_page_ok = 1;
	invalidate(m_visible_region);
}

/* poza paginii DVB, fara text (OCR refuzat sau oprit) */
void eSubtitleWidget::showDvbBitmap()
{
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	if (m_dvb_page_ok)
		return;
	m_text_ok = 0;
	m_text_pixmap = 0;
	m_text_elements.clear();
	invalidate(m_visible_region);
	m_visible_region = gRegion();
	for (std::list<eDVBSubtitleRegion>::iterator it(m_dvb_page.m_regions.begin()); it != m_dvb_page.m_regions.end(); ++it)
	{
		eRect r = eRect(it->m_position, it->m_pixmap->size());
		r.scale(size().width(), m_dvb_page.m_display_size.width(), size().height(), m_dvb_page.m_display_size.height());
		m_visible_region.rects.push_back(r);
	}
	m_dvb_page_ok = 1;
	invalidate(m_visible_region);
}

/* numar intreg dintr-un obiect Python; false (si eroarea stearsa) daca nu e numar */
static bool numarPython(PyObject *o, long &valoare)
{
	if (!o || !PyLong_Check(o))
		return false;
	valoare = PyLong_AsLong(o);
	if (valoare == -1 && PyErr_Occurred())
	{
		PyErr_Clear();
		return false;
	}
	return true;
}

/* randurile citite: (text, x, y, latime, inaltime, baza, ARGB); orice greseala = poza */
void eSubtitleWidget::showOcrText(ePyObject lines)
{
	std::vector<eTextElement> elemente;
	bool sus = false;
	if (!ocrElements(lines, m_dvb_page, elemente, sus))
	{
		eWarning("[eSubtitleWidget] OCR text not usable, the picture is shown");
		showDvbBitmap();
		return;
	}
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	m_dvb_page_ok = 0;
	m_text_top = sus;
	showTextPage(elemente, 2);
}

/* randurile citite din raspunsul OCR, ca elemente de text, si locul lor (sus = textul era in partea de sus a paginii
   DVB); false = raspunsul nu se poate folosi (atunci se arata poza) */
bool eSubtitleWidget::ocrElements(ePyObject lines, const eDVBSubtitlePage &page, std::vector<eTextElement> &elemente,
	bool &top)
{
	long y_min = 0, y_max = 0;
	bool bun = PyList_Check(lines) || PyTuple_Check(lines);
	Py_ssize_t n = bun ? PySequence_Size(lines) : 0;
	for (Py_ssize_t i = 0; bun && i < n && i < RANDURI_MAXIME; ++i)
	{
		PyObject *rand = PyList_Check(lines) ? PyList_GET_ITEM((PyObject*)lines, i) : PyTuple_GET_ITEM((PyObject*)lines, i);
		if (!rand || !PyTuple_Check(rand) || PyTuple_GET_SIZE(rand) < 7)
		{
			bun = false;
			break;
		}
		PyObject *campuri[7];
		for (int k = 0; k < 7; ++k)
			campuri[k] = PyTuple_GET_ITEM(rand, k);
		PyObject *text = campuri[0];
		long x, y, w, h, baza;
		if (!PyUnicode_Check(text) || !numarPython(campuri[1], x) || !numarPython(campuri[2], y)
			|| !numarPython(campuri[3], w) || !numarPython(campuri[4], h) || !numarPython(campuri[5], baza)
			|| !PyLong_Check(campuri[6]))
		{
			bun = false;
			break;
		}
		unsigned long argb = PyLong_AsUnsignedLongMask(campuri[6]);
		if (PyErr_Occurred())
		{
			PyErr_Clear();
			bun = false;
			break;
		}
		Py_ssize_t lungime = 0;
		const char *utf8 = PyUnicode_AsUTF8AndSize(text, &lungime);
		if (!utf8)
		{
			PyErr_Clear();
			bun = false;
			break;
		}
		eTextElement e;
		e.text.assign(utf8, (size_t)lungime);
		e.face = Subtitle_TTX;
		/* culoarea literelor din poza (A = opacitate); o culoare aproape transparenta (nestiuta) = alb */
		int opacitate = (int)((argb >> 24) & 0xFF);
		if (opacitate < 128)
			e.color = gRGB(255, 255, 255);
		else
			e.color = gRGB((int)((argb >> 16) & 0xFF), (int)((argb >> 8) & 0xFF), (int)(argb & 0xFF), 255 - opacitate);
		e.have_color = 1;
		if (e.text.find_first_not_of(" ") == std::string::npos)
			continue;
		if (elemente.empty() || y < y_min)
			y_min = y;
		if (elemente.empty() || y + h > y_max)
			y_max = y + h;
		elemente.push_back(e);
	}
	if (!bun || elemente.empty())
		return false;
	/* sus sau jos, dupa locul textului in pagina DVB: mijlocul randurilor in primele 40% = sus */
	int inaltime_pagina = page.m_display_size.height() > 0 ? page.m_display_size.height() : 576;
	top = (y_min + y_max) / 2 < inaltime_pagina * 40 / 100;
	return true;
}

void eSubtitleWidget::setOcrText(int generation, ePyObject lines)
{
	if (!generation)
		return;
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		if ((*it)->m_ocr_generation == generation)
		{
			(*it)->showOcrText(lines);
			return;
		}
	/* o pagina din coada de afisare (traducerea pornita) care isi astepta textul */
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		for (std::list<eQueuedPage>::iterator q = (*it)->m_queue.begin(); q != (*it)->m_queue.end(); ++q)
			if (q->ocr_generation == generation)
			{
				if (q->state == Q_OCR)
				{
					q->ocr_generation = 0;
					(*it)->queueOcrLines(q->id, lines);
				}
				return;
			}
	/* o pagina sosita si neafisata inca: randurile se tin pana la afisare */
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		for (std::list<eOcrPrefetch>::iterator p = (*it)->m_ocr_prefetch.begin(); p != (*it)->m_ocr_prefetch.end(); ++p)
			if (p->generation == generation)
			{
				if (p->state == OCR_WAITING && lines)
				{
					Py_INCREF(lines);
					p->lines = lines;
					p->state = OCR_TEXT;
				}
				return;
			}
}

void eSubtitleWidget::showOcrBitmap(int generation)
{
	if (!generation)
		return;
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		if ((*it)->m_ocr_generation == generation)
		{
			(*it)->showDvbBitmap();
			return;
		}
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		for (std::list<eQueuedPage>::iterator q = (*it)->m_queue.begin(); q != (*it)->m_queue.end(); ++q)
			if (q->ocr_generation == generation)
			{
				if (q->state == Q_OCR)
				{
					q->ocr_generation = 0;
					(*it)->queuePicture(*q, s_clock());
					(*it)->queueAdvance();
				}
				return;
			}
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		for (std::list<eOcrPrefetch>::iterator p = (*it)->m_ocr_prefetch.begin(); p != (*it)->m_ocr_prefetch.end(); ++p)
			if (p->generation == generation)
			{
				if (p->state == OCR_WAITING)
					p->state = OCR_PICTURE;
				return;
			}
}

/* ------------------------------------------------------------------ traducerea paginilor text */

/*
 * Traducerea automata a subtitrarilor TEXT (Components/HdsTraducereSubtitrari.py): cu functia pusa, fiecare pagina
 * text (teletext, fisier, textul citit din pagina DVB) merge la Python inainte de desenare; traducerea gata (din
 * memorie) vine inapoi pe loc, altfel mai tarziu prin setTranslation. In locul originalului, culoarea si felul
 * literelor raman ale elementului tradus. Sub original: elementele traduse vin dupa toate cele originale (randurile se
 * stivuiesc de jos in sus, deci traducerea e dedesubt), cu felul literelor al originalului si culoarea traducerii
 * (CULOARE_TRADUCERE_SUB_ORIGINAL); originalul ramane cu culoarea lui.
 *
 * COADA DE AFISARE. Inainte, traducerea se punea peste pagina de pe ecran, iar pagina
 * pleca la momentul originalului (pagina goala de stergere, pagina urmatoare): o subtitrare de 1-1,5 s ramanea tradusa
 * 0,3-0,6 s (cat ramanea din ea dupa ce venea traducerea); dupa 2 s de asteptare se vedea originalul si apoi
 * traducerea peste el; la DVB poza aparea dupa 0,5 s, apoi disparea si venea traducerea. Acum, cu functia pusa, fiecare
 * pagina (teletext, fisier, DVB) intra in m_queue cu momentul ei (s_clock):
 *  - pagina goala (stergerea teletextului, pagina DVB fara regiuni) si ceasul de ascundere nu sterg ecranul: spun numai
 *    cand s-ar fi terminat originalul ultimei pagini (original_end); pagina urmatoare il termina si ea;
 *  - prima pagina din coada se arata numai cand e GATA: traducerea, sau originalul hotarat. Pana atunci ecranul e gol:
 *    originalul nu apare niciodata inaintea traducerii lui;
 *  - traducerea care nu vine in s_translation_wait_ms de la momentul paginii, sau la care Python renunta (lista goala,
 *    None, functia cazuta) = originalul cu semnul s_translation_mark in fata; o traducere venita dupa aceea nu se mai
 *    pune (nu se schimba niciodata originalul in traducere pe ecran);
 *  - o pagina DVB isi asteapta intai textul (OCR), in acelasi termen; OCR refuzat sau termenul trecut = poza ei
 *    (originalul); textul venit dupa ce s-a hotarat poza nu se mai foloseste;
 *  - pagina de pe ecran sta cel putin cat ar fi stat originalul (original_end - arrival, numarat de cand apare ea) si
 *    cel putin timpul ei de citire (min_ms, numai la traduceri: readingTime); urmatoarea, cand e gata, ii ia locul dupa
 *    timpul de citire; ordinea se pastreaza, nicio pagina nu se sare;
 *  - ca intarzierea sa nu creasca fara capat sub subtitrari foarte dese: urmatoarea gata nu asteapta mai mult de
 *    COADA_URMATOAREA_MAX_MS, iar pagina tradusa de pe ecran sta oricum COADA_MINIM_MS;
 *  - doua pagini lipite (fara pagina goala intre ele): cea de pe ecran ramane pana e gata urmatoarea, cel mult
 *    COADA_PRELUNGIRE_MS peste timpul ei, ca intre doua randuri sa nu clipeasca ecranul gol;
 *  - aceeasi pagina trimisa din nou (acelasi text, lipita de cea de dinainte: teletextul repetat, DVB repetat) nu face o
 *    pagina noua; una care o repeta pe cea de dinainte si adauga la ea (randuri venite pe rand) o inlocuieste: cea
 *    neafisata inca pleaca, cea de pe ecran ii lasa locul cand e gata cea noua, fara timpul de citire;
 *  - clearPage (servicemp3: salt, oprire), proba din setari si functia scoasa golesc coada; peste COADA_MAX pagini
 *    (un flux stricat) pleaca cea mai veche.
 * Functiile din Python pot raspunde chiar in timpul apelului (setOcrText, setTranslation): o pagina se cauta din nou
 * dupa id dupa fiecare apel in Python, iar queueAdvance nu se cheama in el insusi (m_queue_busy; se reia la sfarsit).
 */

static const int TRADUCERE_ASTEPTARE_MAXIMA_MS = 15000;
static const int COADA_URMATOAREA_MAX_MS = 2000;
static const int COADA_MINIM_MS = 1000;
static const int COADA_PRELUNGIRE_MS = 2000;
static const unsigned int COADA_MAX = 32;

void eSubtitleWidget::setTranslationHandler(ePyObject handler)
{
	ePyObject nou;
	if (handler && (PyObject*)handler != Py_None)
	{
		if (PyCallable_Check(handler))
			nou = handler;
		else
			eWarning("[eSubtitleWidget] translation handler is not callable, translation stays off");
	}
	if (nou)
		Py_INCREF(nou);
	if (s_translation_handler)
		Py_DECREF(s_translation_handler);
	s_translation_handler = nou;
	eDebug("[eSubtitleWidget] translation of the text subtitles %s", s_translation_handler ? "on" : "off");
	if (!s_translation_handler)
	{
		/* coada de afisare se goleste; ultima pagina text, al carei original inca ar fi pe ecran, ramane in original */
		for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		{
			eSubtitleWidget *w = *it;
			if (w->m_queue.empty())
				continue;
			eQueuedPage ultima = w->m_queue.back();
			w->queueClear();
			w->showNothing();
			if (ultima.original_end < 0 && ultima.content == Q_TEXT && !ultima.original.empty())
			{
				w->m_pixmap = 0;
				w->m_text_top = ultima.top;
				w->setTextElements(ultima.original);
			}
		}
	}
}

void eSubtitleWidget::setTranslationMode(int under)
{
	s_translation_under = under ? 1 : 0;
}

void eSubtitleWidget::setTranslationWait(int ms)
{
	s_translation_wait_ms = inInterval("translation wait", ms, 0, TRADUCERE_ASTEPTARE_MAXIMA_MS);
}

void eSubtitleWidget::setTranslationMark(const std::string &text)
{
	/* un semn scurt; un text lung (greseala) se taie la o litera intreaga */
	std::string semn = text;
	if (semn.size() > 64)
	{
		size_t n = 64;
		while (n > 0 && (((unsigned char)semn[n]) & 0xC0) == 0x80)
			--n;
		semn.resize(n);
	}
	s_translation_mark = semn;
}

void eSubtitleWidget::setReadingTime(int base_ms, int per_char_ms, int min_ms, int max_ms)
{
	s_reading_base_ms = inInterval("reading base", base_ms, 0, 5000);
	s_reading_char_ms = inInterval("reading per letter", per_char_ms, 0, 500);
	s_reading_min_ms = inInterval("reading minimum", min_ms, 0, 15000);
	s_reading_max_ms = inInterval("reading maximum", max_ms, s_reading_min_ms, 20000);
}

/* textele elementelor, pentru Python: [str]; o referinta noua, sau nula */
ePyObject eSubtitleWidget::translationTexts(const std::vector<eTextElement> &elements)
{
	ePyObject texte = PyList_New(elements.size());
	if (!texte)
	{
		PyErr_Clear();
		return ePyObject();
	}
	for (unsigned int i = 0; i < elements.size(); ++i)
	{
		PyObject *t = PyUnicode_DecodeUTF8(elements[i].text.data(), (Py_ssize_t)elements[i].text.size(), "replace");
		if (!t)
		{
			PyErr_Clear();
			Py_DECREF(texte);
			return ePyObject();
		}
		PyList_SET_ITEM((PyObject*)texte, i, t);
	}
	return texte;
}

/* functia din Python cu (generatie, texte, fel, intarziere); ia referinta lui `texts`; intoarce rezultatul (o
   referinta noua) sau nula daca functia a cazut */
ePyObject eSubtitleWidget::callTranslationHandler(int generation, ePyObject texts, int kind, int delay_ms)
{
	if (!s_translation_handler)
	{
		Py_DECREF(texts);
		return ePyObject();
	}
	ePyObject argumente = PyTuple_New(4);
	if (!argumente)
	{
		PyErr_Clear();
		Py_DECREF(texts);
		return ePyObject();
	}
	PyTuple_SET_ITEM(argumente, 0, PyLong_FromLong(generation));
	PyTuple_SET_ITEM(argumente, 1, texts);
	PyTuple_SET_ITEM(argumente, 2, PyLong_FromLong(kind));
	PyTuple_SET_ITEM(argumente, 3, PyLong_FromLong(delay_ms));
	/* the handler is kept alive during the call even if it replaces itself */
	ePyObject functie = s_translation_handler;
	Py_INCREF(functie);
	ePyObject rezultat = PyObject_CallObject(functie, argumente);
	Py_DECREF(functie);
	Py_DECREF(argumente);
	if (!rezultat)
	{
		eWarning("[eSubtitleWidget] the translation handler failed, the original is shown");
		PyErr_Print();
		return ePyObject();
	}
	return rezultat;
}

/* o pagina text de afisat acum, pe drumul fara coada; cu functia traducerii pusa intre timp (textul OCR al unei pagini
   DVB venit dupa pornirea traducerii) pagina intra in coada de afisare */
void eSubtitleWidget::showTextPage(const std::vector<eTextElement> &elements, int kind)
{
	if (s_translation_handler)
	{
		queueText(elements, kind, m_text_top);
		return;
	}
	setTextElements(elements);
}

/* ------------------------------------------------------------------ coada de afisare */

std::list<eSubtitleWidget::eQueuedPage>::iterator eSubtitleWidget::queueFind(int id)
{
	for (std::list<eQueuedPage>::iterator q = m_queue.begin(); q != m_queue.end(); ++q)
		if (q->id == id)
			return q;
	return m_queue.end();
}

/* timpul de citire al unei pagini traduse: s_reading_base_ms + s_reading_char_ms pe semn, intre s_reading_min_ms si
   s_reading_max_ms. Semnele: ale traducerii (la „Sub original” numai elementele traduse), o litera UTF-8 = un semn,
   spatiile dintre cuvinte numarate, cele de la margini nu. Din fabrica 0,7 s + 60 ms pe semn (cam 17 semne pe
   secunda, viteza din ghidurile obisnuite de subtitrare), intre 1,5 s (traducerea vine decalata de vorbire: si un
   rand de un cuvant trebuie observat) si 7 s (plafonul obisnuit). */
int eSubtitleWidget::readingTime(const std::vector<eTextElement> &elements)
{
	bool numai_traduse = false;
	for (unsigned int i = 0; i < elements.size(); ++i)
		if (elements[i].translated)
			numai_traduse = true;
	long semne = 0;
	for (unsigned int i = 0; i < elements.size(); ++i)
	{
		const std::string &t = elements[i].text;
		if (numai_traduse && !elements[i].translated)
			continue;
		size_t a = t.find_first_not_of(" "), b = t.find_last_not_of(" ");
		if (a == std::string::npos)
			continue;
		for (size_t k = a; k <= b; ++k)
			if ((((unsigned char)t[k]) & 0xC0) != 0x80)
				++semne;
	}
	long ms = s_reading_base_ms + semne * s_reading_char_ms;
	if (ms < s_reading_min_ms)
		ms = s_reading_min_ms;
	if (ms > s_reading_max_ms)
		ms = s_reading_max_ms;
	return (int)ms;
}

void eSubtitleWidget::queueClear()
{
	m_queue.clear();
	m_translation_timer->stop();
	m_queue_on_screen = false;
}

/* ecranul gol (coada ramane) */
void eSubtitleWidget::showNothing()
{
	m_dvb_page_ok = 0;
	m_text_ok = 0;
	m_text_pixmap = 0;
	m_text_elements.clear();
	invalidate(m_visible_region);
	m_visible_region = gRegion();
}

/* originalul ultimei pagini din coada se termina acum: prin pagina urmatoare (by_next) sau prin pagina goala, ceasul
   de ascundere */
void eSubtitleWidget::queueEnd(bool by_next, long long now)
{
	if (m_queue.empty())
		return;
	eQueuedPage &u = m_queue.back();
	if (u.original_end >= 0)
		return;
	u.original_end = now;
	u.ended_by_next = by_next;
}

/* o pagina noua la sfarsitul cozii (originalul celei de dinainte se termina acum) -> id-ul ei */
int eSubtitleWidget::queueNew(long long now)
{
	queueEnd(true, now);
	while (m_queue.size() >= COADA_MAX)
	{
		eWarning("[eSubtitleWidget] the subtitle display queue is full, the oldest page goes");
		if (m_queue_on_screen)
		{
			showNothing();
			m_queue_on_screen = false;
		}
		m_queue.pop_front();
	}
	eQueuedPage q;
	m_queue_ids = m_queue_ids >= 0x3FFFFFFF ? 1 : m_queue_ids + 1;
	q.id = m_queue_ids;
	q.state = Q_TRANSLATION;
	q.content = Q_TEXT;
	q.kind = 0;
	q.top = false;
	q.arrival = now;
	q.original_end = -1;
	q.ended_by_next = false;
	q.superseded = false;
	q.deadline = now + s_translation_wait_ms;
	q.ready_at = -1;
	q.shown_at = -1;
	q.min_ms = 0;
	q.ocr_generation = 0;
	q.translation_generation = 0;
	m_queue.push_back(q);
	return q.id;
}

/* traducerea pornita cat era pe ecran o pagina a drumului fara coada (sau una isi astepta textul OCR acolo): pagina
   aceea pleaca, iar ecranul ramane gol pana vine traducerea (altfel originalul ar ramane pe ecran, fara ceas, cat se
   asteapta traducerea paginii urmatoare) */
void eSubtitleWidget::queueStart()
{
	if (!m_queue.empty() || m_queue_on_screen)
		return;
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	if (m_text_ok || m_dvb_page_ok)
		showNothing();
}

/* o pagina text (teletext, fisier) venita acum; fara niciun text = pagina goala (numai sfarsitul originalului) */
void eSubtitleWidget::queueText(const std::vector<eTextElement> &elements, int kind, bool top)
{
	queueStart();
	long long acum = s_clock();
	bool are_text = false;
	for (unsigned int i = 0; i < elements.size(); ++i)
		if (elements[i].text.find_first_not_of(" ") != std::string::npos)
			are_text = true;
	if (!are_text)
		queueEnd(false, acum);
	else
		queueTextKnown(queueNew(acum), elements, kind, top);
	queueAdvance();
}

/* o pagina DVB venita acum: intai textul ei (OCR: venit deja din prefetchPage, cerut acum, sau niciunul = poza) */
void eSubtitleWidget::queueDvb(const eDVBSubtitlePage &p)
{
	queueStart();
	long long acum = s_clock();
	if (p.m_regions.empty())
	{
		queueEnd(false, acum);
		queueAdvance();
		return;
	}
	int id = queueNew(acum);
	std::list<eQueuedPage>::iterator q = queueFind(id);
	q->dvb = p;
	q->state = Q_OCR;
	q->kind = 2;
	int raspuns = 0;		/* 0 poza, 1 textul vine mai tarziu, 2 textul e aici (linii) */
	ePyObject linii;
	bool gasita = false;
	for (std::list<eOcrPrefetch>::iterator it = m_ocr_prefetch.begin(); it != m_ocr_prefetch.end(); ++it)
	{
		if (it->show_time != q->dvb.m_show_time || it->pictures.size() != q->dvb.m_regions.size())
			continue;
		bool aceeasi = true;
		unsigned int k = 0;
		for (std::list<eDVBSubtitleRegion>::iterator r(q->dvb.m_regions.begin()); r != q->dvb.m_regions.end(); ++r, ++k)
			if ((gPixmap*)it->pictures[k] != (gPixmap*)r->m_pixmap || it->positions[k] != r->m_position)
			{
				aceeasi = false;
				break;
			}
		if (!aceeasi)
			continue;
		int generatie = it->generation;
		int stare = it->state;
		linii = it->lines;
		it->state = OCR_WAITING;	/* referinta liniilor trece aici */
		while (m_ocr_prefetch.begin() != it)
			dropPrefetch(m_ocr_prefetch.begin());
		m_ocr_prefetch.erase(it);
		if (stare == OCR_TEXT)
			raspuns = 2;
		else if (stare == OCR_WAITING)
		{
			q->ocr_generation = generatie;
			raspuns = 1;
		}
		gasita = true;
		break;
	}
	if (!gasita && s_ocr_handler)
	{
		ePyObject regiuni = ocrRegions(q->dvb);
		if (regiuni)
		{
			int generatie = nextOcrGeneration();
			q->ocr_generation = generatie;
			bool da = callOcrHandler(generatie, regiuni, -1);
			/* raspunsul poate fi venit in timpul apelului (setOcrText, showOcrBitmap au gasit pagina in coada) */
			q = queueFind(id);
			if (q == m_queue.end() || q->state != Q_OCR || q->ocr_generation != generatie)
			{
				queueAdvance();
				return;
			}
			if (da)
				raspuns = 1;
			else
				q->ocr_generation = 0;
		}
	}
	if (raspuns == 2)
	{
		queueOcrLines(id, linii);
		Py_DECREF(linii);
		return;
	}
	if (raspuns == 0)
		queuePicture(*q, acum);
	queueAdvance();
}

/* textul OCR al unei pagini din coada: elementele, apoi traducerea; un raspuns stricat = poza */
void eSubtitleWidget::queueOcrLines(int id, ePyObject lines)
{
	std::list<eQueuedPage>::iterator q = queueFind(id);
	if (q != m_queue.end())
	{
		std::vector<eTextElement> elemente;
		bool sus = false;
		if (!ocrElements(lines, q->dvb, elemente, sus))
		{
			eWarning("[eSubtitleWidget] OCR text not usable, the picture is shown");
			queuePicture(*q, s_clock());
		}
		else
			queueTextKnown(id, elemente, 2, sus);
	}
	queueAdvance();
}

/* poza paginii DVB (OCR refuzat sau termenul trecut): originalul, gata de aratat la randul lui */
void eSubtitleWidget::queuePicture(eQueuedPage &q, long long now)
{
	q.state = Q_READY;
	q.content = Q_PICTURE;
	q.ocr_generation = 0;
	q.ready_at = now;
	q.min_ms = 0;
}

/* originalul, gata de aratat: cu semnul (nu s-a tradus) sau asa cum e (e deja in limba tinta) */
void eSubtitleWidget::queueOriginal(eQueuedPage &q, bool mark, long long now)
{
	q.state = Q_READY;
	q.content = Q_TEXT;
	q.shown = q.original;
	if (mark && !s_translation_mark.empty() && !q.shown.empty())
		q.shown[0].text = s_translation_mark + " " + q.shown[0].text;
	q.ready_at = now;
	q.min_ms = 0;
}

/* traducerea unei pagini din coada; false = nu se poate folosi (lista goala = renunt, alta lungime, alt fel de valori):
   atunci cel care cheama pune originalul cu semnul */
bool eSubtitleWidget::queueTranslated(eQueuedPage &q, ePyObject texts, long long now)
{
	if (!texts || !(PyList_Check(texts) || PyTuple_Check(texts)))
		return false;
	Py_ssize_t n = PySequence_Size(texts);
	if (n <= 0)
		return false;
	if (n != (Py_ssize_t)q.original.size())
	{
		eWarning("[eSubtitleWidget] translation with %d texts for %d elements, the original is shown", (int)n,
			(int)q.original.size());
		return false;
	}
	std::vector<eTextElement> traduse;
	for (Py_ssize_t i = 0; i < n; ++i)
	{
		PyObject *t = PyList_Check(texts) ? PyList_GET_ITEM((PyObject*)texts, i) : PyTuple_GET_ITEM((PyObject*)texts, i);
		if (!t || !PyUnicode_Check(t))
			return false;
		Py_ssize_t lungime = 0;
		const char *utf8 = PyUnicode_AsUTF8AndSize(t, &lungime);
		if (!utf8)
		{
			PyErr_Clear();
			return false;
		}
		std::string text(utf8, (size_t)lungime);
		if (text.find_first_not_of(" ") == std::string::npos)
			continue;
		eTextElement e = q.original[i];
		e.text = text;
		/* in locul originalului: culorile elementului (ale teletextului) raman; sub original: culoarea traducerii */
		e.translated = s_translation_under ? 1 : 0;
		traduse.push_back(e);
	}
	if (traduse.empty())
	{
		/* toate goale: originalul asa cum e, ca inainte */
		queueOriginal(q, false, now);
		return true;
	}
	q.state = Q_READY;
	q.content = Q_TEXT;
	if (s_translation_under)
	{
		q.shown = q.original;
		q.shown.insert(q.shown.end(), traduse.begin(), traduse.end());
	}
	else
		q.shown = traduse;
	q.ready_at = now;
	q.min_ms = readingTime(q.shown);
	return true;
}

/* textul paginii e stiut (teletext, fisier: la sosire; DVB: cand vine textul OCR): pagina de dinainte pe care a
   inlocuit-o e cercetata (aceeasi pagina trimisa din nou / o repeta si adauga), apoi pagina merge la traducere */
void eSubtitleWidget::queueTextKnown(int id, const std::vector<eTextElement> &elements, int kind, bool top)
{
	std::list<eQueuedPage>::iterator q = queueFind(id);
	if (q == m_queue.end())
		return;
	long long acum = s_clock();
	q->original = elements;
	q->kind = kind;
	q->top = top;
	q->content = Q_TEXT;
	q->state = Q_TRANSLATION;
	q->ocr_generation = 0;
	if (q != m_queue.begin())
	{
		std::list<eQueuedPage>::iterator p = q;
		--p;
		if (p->ended_by_next && p->original_end == q->arrival && p->content == Q_TEXT && !p->original.empty())
		{
			/* textul paginii: elementele lipite cu un spatiu, fara spatiile de la margini */
			auto textul = [](const std::vector<eTextElement> &elemente) -> std::string
			{
				std::string tot;
				for (unsigned int i = 0; i < elemente.size(); ++i)
				{
					const std::string &t = elemente[i].text;
					size_t a = t.find_first_not_of(" "), b = t.find_last_not_of(" ");
					if (a == std::string::npos)
						continue;
					if (!tot.empty())
						tot += " ";
					tot += t.substr(a, b - a + 1);
				}
				return tot;
			};
			std::string inainte = textul(p->original), acum_text = textul(q->original);
			if (inainte == acum_text)
			{
				/* aceeasi subtitrare, trimisa din nou: originalul ei continua */
				p->original_end = q->original_end;
				p->ended_by_next = q->ended_by_next;
				m_queue.erase(q);
				return;
			}
			if (!inainte.empty() && acum_text.size() > inainte.size() && acum_text.compare(0, inainte.size(), inainte) == 0
				&& acum_text[inainte.size()] == ' ')
			{
				/* o repeta si adauga: cea neafisata pleaca, cea de pe ecran ii lasa locul cand e gata cea noua */
				if (p->shown_at < 0)
					m_queue.erase(p);
				else
					p->superseded = true;
			}
		}
	}
	ePyObject texte = translationTexts(q->original);
	if (!texte)
	{
		queueOriginal(*q, true, acum);
		return;
	}
	s_translation_generation = s_translation_generation >= 0x3FFFFFFF ? 1 : s_translation_generation + 1;
	int generatie = s_translation_generation;
	q->translation_generation = generatie;
	ePyObject rezultat = callTranslationHandler(generatie, texte, kind, -1);
	/* setTranslation in timpul apelului (sau pagina plecata): pagina e deja hotarata */
	q = queueFind(id);
	if (q == m_queue.end() || q->state != Q_TRANSLATION || q->translation_generation != generatie)
	{
		if (rezultat)
			Py_DECREF(rezultat);
		return;
	}
	if (!rezultat || (PyObject*)rezultat == Py_None)
		queueOriginal(*q, true, acum);			/* nu se traduce (pauza, eroare, functia cazuta) */
	else if (PyList_Check(rezultat) || PyTuple_Check(rezultat))
	{
		if (!queueTranslated(*q, rezultat, acum))
			queueOriginal(*q, true, acum);
	}
	else
	{
		int vine = PyObject_IsTrue(rezultat);
		if (vine < 0)
		{
			PyErr_Clear();
			vine = 0;
		}
		if (vine != 1)
			queueOriginal(*q, false, acum);		/* deja in limba tinta: originalul asa cum e */
	}
	if (rezultat)
		Py_DECREF(rezultat);
}

void eSubtitleWidget::setTranslation(int generation, ePyObject texts)
{
	if (!generation)
		return;
	for (std::list<eSubtitleWidget*>::iterator it = s_widgets.begin(); it != s_widgets.end(); ++it)
		for (std::list<eQueuedPage>::iterator q = (*it)->m_queue.begin(); q != (*it)->m_queue.end(); ++q)
			if (q->translation_generation == generation)
			{
				/* numai o pagina care inca asteapta: dupa original, traducerea nu se mai pune */
				if (q->state == Q_TRANSLATION)
				{
					long long acum = s_clock();
					if (!(*it)->queueTranslated(*q, texts, acum))
						(*it)->queueOriginal(*q, true, acum);
					(*it)->queueAdvance();
				}
				return;
			}
}

/* o pagina din coada pe ecran: textul ei (traducerea sau originalul) sau poza paginii DVB */
void eSubtitleWidget::queueShow(const eQueuedPage &q)
{
	m_pixmap = 0;
	m_ocr_generation = 0;
	m_ocr_timer->stop();
	if (q.content == Q_PICTURE)
	{
		m_text_ok = 0;
		m_text_pixmap = 0;
		m_text_elements.clear();
		invalidate(m_visible_region);
		m_dvb_page = q.dvb;
		m_visible_region = gRegion();
		for (std::list<eDVBSubtitleRegion>::iterator it(m_dvb_page.m_regions.begin()); it != m_dvb_page.m_regions.end(); ++it)
		{
			eRect r = eRect(it->m_position, it->m_pixmap->size());
			r.scale(size().width(), m_dvb_page.m_display_size.width(), size().height(), m_dvb_page.m_display_size.height());
			m_visible_region.rects.push_back(r);
		}
		m_dvb_page_ok = 1;
		invalidate(m_visible_region);
		return;
	}
	m_dvb_page_ok = 0;
	m_text_top = q.top;
	setTextElements(q.shown);
}

/* ceasul de ascundere: fara coada, pagina pleaca (ca inainte); cu coada, originalul ultimei pagini s-ar fi terminat */
void eSubtitleWidget::hideTimeout()
{
	if (m_queue.empty())
	{
		clearPage();
		return;
	}
	queueEnd(false, s_clock());
	queueAdvance();
}

/* sfarsitul randului de subtitrare, spus de servicemp3 (fisierul de subtitrari, pagina goala PGS/DVB a filmului): fara
   coada, pagina pleaca pe loc (ca inainte, clearPage); cu coada, numai originalul ultimei pagini s-a terminat */
void eSubtitleWidget::endPage()
{
	if (m_queue.empty())
	{
		clearPage();
		return;
	}
	m_hide_subtitles_timer->stop();
	queueEnd(false, s_clock());
	queueAdvance();
}

/* Coada merge mai departe: asteptarile trecute de termen se hotarasc (originalul cu semnul, poza), pagina de pe ecran
   pleaca cand i-a venit timpul, prima pagina gata se arata; ceasul se pune pentru urmatoarea schimbare. */
void eSubtitleWidget::queueAdvance()
{
	if (m_queue_busy)
	{
		m_queue_again = true;
		return;
	}
	m_queue_busy = true;
	do
	{
		m_queue_again = false;
		long long acum = s_clock();
		long long trezire = -1;
		for (std::list<eQueuedPage>::iterator q = m_queue.begin(); q != m_queue.end(); ++q)
		{
			if (q->state == Q_OCR && acum >= q->deadline)
				queuePicture(*q, acum);
			else if (q->state == Q_TRANSLATION && acum >= q->deadline)
				queueOriginal(*q, true, acum);
		}
		while (!m_queue.empty())
		{
			eQueuedPage &f = m_queue.front();
			if (f.shown_at < 0)
			{
				if (f.state != Q_READY)
					break;		/* prima pagina asteapta: ecranul ramane gol */
				f.shown_at = acum;
				queueShow(f);
				m_queue_on_screen = true;
			}
			std::list<eQueuedPage>::iterator urm = m_queue.begin();
			++urm;
			long long pleaca = -1;		/* -1: ramane (originalul ei nu s-a terminat inca) */
			if (urm != m_queue.end() && urm->state == Q_READY)
			{
				if (f.superseded)
					pleaca = f.shown_at;
				else
				{
					/* timpul de citire; urmatoarea gata nu asteapta mai mult de COADA_URMATOAREA_MAX_MS, dar o traducere
					   sta oricum COADA_MINIM_MS */
					long long jos = f.shown_at + (f.min_ms < COADA_MINIM_MS ? f.min_ms : COADA_MINIM_MS);
					pleaca = f.shown_at + f.min_ms;
					if (urm->ready_at + COADA_URMATOAREA_MAX_MS < pleaca)
						pleaca = urm->ready_at + COADA_URMATOAREA_MAX_MS;
					if (pleaca < jos)
						pleaca = jos;
				}
			}
			else if (f.original_end >= 0)
			{
				/* cat ar fi stat originalul, numarat de cand a aparut ea, si cel putin timpul de citire */
				long long durata = f.original_end - f.arrival;
				if (durata < 0)
					durata = 0;
				pleaca = f.shown_at + (durata > f.min_ms ? durata : f.min_ms);
				if (f.ended_by_next && urm != m_queue.end())
					pleaca += COADA_PRELUNGIRE_MS;	/* pana e gata urmatoarea, lipita de ea */
			}
			if (pleaca < 0 || acum < pleaca)
			{
				trezire = pleaca;
				break;
			}
			m_queue.pop_front();
		}
		if ((m_queue.empty() || m_queue.front().shown_at < 0) && m_queue_on_screen)
		{
			showNothing();
			m_queue_on_screen = false;
		}
		for (std::list<eQueuedPage>::iterator q = m_queue.begin(); q != m_queue.end(); ++q)
			if ((q->state == Q_OCR || q->state == Q_TRANSLATION) && (trezire < 0 || q->deadline < trezire))
				trezire = q->deadline;
		if (trezire >= 0)
		{
			long long ms = trezire - acum;
			if (ms < 1)
				ms = 1;
			m_translation_timer->start((long)ms, true);
		}
		else
			m_translation_timer->stop();
	} while (m_queue_again);
	m_queue_busy = false;
}

/* pagina teletext sosita inainte de momentul afisarii: textele merg la traducere acum (numai un semn; raspunsul se
   foloseste la afisare, din memoria traducerilor) */
void eSubtitleWidget::prefetchText(const eDVBTeletextSubtitlePage &p, int delay_ms)
{
	if (!s_translation_handler || p.m_elements.empty())
		return;
	std::vector<eTextElement> elemente;
	for (unsigned int i = 0; i < p.m_elements.size(); ++i)
	{
		eTextElement e;
		e.text = p.m_elements[i].m_text;
		e.face = Subtitle_TTX;
		e.have_color = 0;
		elemente.push_back(e);
	}
	ePyObject texte = translationTexts(elemente);
	if (!texte)
		return;
	ePyObject rezultat = callTranslationHandler(0, texte, 0, delay_ms < 0 ? 0 : delay_ms);
	if (rezultat)
		Py_DECREF(rezultat);
}

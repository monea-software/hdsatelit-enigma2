/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdssubimagini: picture subtitles of films, decoded into rectangles of 8-bit colour indexes with their palettes:
 *  - DVD (VobSub): subpicture units (SPU) with 4 colours, run-length coded on 2 bits in two fields (even and odd
 *    lines), control sequences with the colours (0x03), the transparency (0x04), the place (0x05), the field
 *    addresses (0x06), start (0x01, 0x00 forced) and stop (0x02); the times are in units of 1024/90000 s. The 16
 *    colours of the film come from the .idx header ("palette:"), the same text as the CodecPrivate of an MKV track;
 *  - Blu-ray (PGS): display sets of segments PCS 0x16 (composition: size of the picture, objects and their place),
 *    WDS 0x17 (windows), PDS 0x14 (palette, Y Cr Cb and opacity, BT.709), ODS 0x15 (object, run-length coded on 8 bits,
 *    possibly in several fragments) and END 0x80. The palettes and objects stay known between display sets (only an
 *    epoch start clears them). In .sup files each segment starts with "PG", the PTS and the DTS; in MKV not.
 * Written after the public descriptions of the formats. Plain C++ without enigma2 types, so that it can be checked on
 * a PC against files made for the test (teste/date-subtitrari/fa_poze.py) and against FFmpeg; servicemp3 turns a page
 * into an eDVBSubtitlePage and shows it like a DVB subtitle.
 */
#ifndef __lib_service_hdssubimagini_h
#define __lib_service_hdssubimagini_h

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

struct eHdsDreptunghi
{
	int x, y, w, h;
	std::vector<uint8_t> pixeli;	/* w * h colour indexes */
	uint32_t paleta[256];		/* 0xAARRGGBB, AA = 0xFF opaque, 0x00 transparent */
	int culori;
};

struct eHdsPaginaImagine
{
	int latime, inaltime;		/* the picture the places refer to: 720x576, 1920x1080 */
	int start_ms, stop_ms;		/* from the time of the packet; stop_ms < 0: until the next page */
	bool gol;			/* no rectangle: the page clears the screen */
	std::vector<eHdsDreptunghi> dreptunghiuri;
	eHdsPaginaImagine() : latime(720), inaltime(576), start_ms(0), stop_ms(-1), gol(true) {}
};

class eHdsVobSub
{
public:
	eHdsVobSub();
	/* the 16 colours, 0xRRGGBB */
	void paleta(const uint32_t rgb[16]);
	/* "palette: rrggbb, ..." and "size: WxH" from the .idx header (or the CodecPrivate of the MKV track);
	   true if a palette was found */
	bool dinIdx(const std::string &text);
	void marime(int latime, int inaltime) { m_latime = latime; m_inaltime = inaltime; }
	/* one SPU packet (all of it) -> the page; false if the packet is broken */
	bool decodeaza(const uint8_t *date, size_t lungime, eHdsPaginaImagine &pagina) const;
private:
	uint32_t m_paleta[16];
	int m_latime, m_inaltime;
};

class eHdsPgs
{
public:
	eHdsPgs();
	void reset();
	/* segments of one or more display sets; a page is added for every END segment. .sup framing ("PG") is found
	   by itself. Returns how many pages were added, -1 if the data are broken (the state is then reset). */
	int adauga(const uint8_t *date, size_t lungime, std::vector<eHdsPaginaImagine> &pagini);
private:
	struct Obiect
	{
		int w, h;
		std::vector<uint8_t> rle;
		size_t asteptat;	/* the announced length of the coded data (fragments are joined) */
	};
	struct Compozitie
	{
		int obiect, fereastra, x, y;
		bool taiat;
		int tx, ty, tw, th;
	};
	int m_latime, m_inaltime;
	int m_paleta_id;
	std::map<int, std::vector<uint32_t> > m_palete;
	std::map<int, Obiect> m_obiecte;
	std::vector<Compozitie> m_compozitie;
	bool m_are_pcs;
	void segment(int tip, const uint8_t *d, size_t n, std::vector<eHdsPaginaImagine> &pagini, int &adaugate);
	void pagina(std::vector<eHdsPaginaImagine> &pagini);
};

/* PGS run-length data of one object -> w * h indexes; false if the data do not fill the object */
bool hdsPgsRle(const uint8_t *d, size_t n, int w, int h, std::vector<uint8_t> &pixeli);
/* VobSub: one field of 2-bit run-length data from `start` (in bytes) for the lines `linie0`, `linie0 + 2`, ... */
bool hdsSpuCamp(const uint8_t *d, size_t n, size_t start, int w, int h, int linie0, std::vector<uint8_t> &pixeli);
/* VobSub .sub file: one SPU packet from the MPEG-2 PS packs that start at the beginning of `ps` (private stream 1,
   substream 0x2x), the payloads joined until the length the packet announces */
bool hdsSpuDinPs(const std::vector<uint8_t> &ps, std::vector<uint8_t> &spu);

/* The packets of a picture subtitle file (.idx+.sub or .sup), read and decoded on a thread of their own: a film on a
   network share or a slow disk never stops the main loop. The owner asks for a packet (ia); the answer is ready at
   a later call. The packet asked for last and the one after it are read, a few decoded pages are kept. The thread
   and its state outlive the object while a read is still under way (the object only tells it to stop), so closing
   a film never waits for a slow read. */
class eHdsCititorImagini
{
public:
	struct Intrare
	{
		int start_ms;
		long long offset;
		int length;		/* PGS: the bytes of the display set; VobSub: 0, the PS packs say how long */
	};
	enum { VobSub = 5, Pgs = 6 };	/* the same numbers as the subtitle types of servicemp3 */
	eHdsCititorImagini();
	~eHdsCititorImagini();
	/* the file to read; the pages of an earlier file are forgotten */
	void configureaza(int fel, const std::string &cale, const std::string &info, const std::vector<Intrare> &intrari);
	bool configurat(int fel, const std::string &cale, size_t cate) const;
	void goleste();
	/* 1 = the page of packet `index` is ready (copied into `pagina`), -1 = it could not be read, 0 = still being read
	   (asked for now, with the packet after it) */
	int ia(int index, eHdsPaginaImagine &pagina);
	/* read ahead, if not read yet */
	void cere(int index);
	/* the read itself, on any thread: `fisier` stays open between calls for the same file */
	static bool citeste(FILE *&fisier, std::string &deschis, int fel, const std::string &cale, const std::string &info,
		const std::vector<Intrare> &intrari, int index, eHdsPaginaImagine &pagina);
	struct Stare;
private:
	std::shared_ptr<Stare> m_stare;
	eHdsCititorImagini(const eHdsCititorImagini &);
	eHdsCititorImagini &operator=(const eHdsCititorImagini &);
};

#endif

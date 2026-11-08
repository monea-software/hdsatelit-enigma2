/* Copyright (C) 2026 moneasoftware.com si hdsatelit.com. GPL-2.0-only. */
#ifndef HDS_LISTE_TEXT_H
#define HDS_LISTE_TEXT_H

#include <string>

namespace hdslistetext
{
	/* UTF8 valid ramane intact. Numai octetii invalizi devin CP1252/Latin1. */
	inline std::string textUtf8(const std::string &text)
	{
		static const unsigned short cp1252[] = {
			0x20ac, 0x81, 0x201a, 0x192, 0x201e, 0x2026, 0x2020, 0x2021,
			0x2c6, 0x2030, 0x160, 0x2039, 0x152, 0x8d, 0x17d, 0x8f,
			0x90, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014,
			0x2dc, 0x2122, 0x161, 0x203a, 0x153, 0x9d, 0x17e, 0x178
		};
		std::string rez;
		for (size_t i = 0; i < text.size();)
		{
			unsigned char c = text[i];
			size_t n = c < 0x80 ? 1 : c >= 0xc2 && c <= 0xdf ? 2 :
				c >= 0xe0 && c <= 0xef ? 3 : c >= 0xf0 && c <= 0xf4 ? 4 : 0;
			bool valid = n && n <= text.size() - i;
			for (size_t j = 1; valid && j < n; ++j)
				valid = ((unsigned char)text[i + j] & 0xc0) == 0x80;
			if (valid && n >= 3)
			{
				unsigned char b = text[i + 1];
				valid = !(c == 0xe0 && b < 0xa0) && !(c == 0xed && b >= 0xa0) &&
					!(c == 0xf0 && b < 0x90) && !(c == 0xf4 && b >= 0x90);
			}
			if (valid)
			{
				rez.append(text, i, n);
				i += n;
				continue;
			}
			unsigned int u = c >= 0x80 && c < 0xa0 ? cp1252[c - 0x80] : c;
			if (u >= 0x800)
				rez += (char)(0xe0 | (u >> 12));
			rez += (char)((u >= 0x800 ? 0x80 : 0xc0) | ((u >> 6) & 0x3f));
			rez += (char)(0x80 | (u & 0x3f));
			++i;
		}
		return rez;
	}
}

#endif

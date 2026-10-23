/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/eerror.h>
#include <lib/dvb/radiotext.h>
#include <lib/dvb/idemux.h>
#include <lib/dvb/hdsspectru.h>
#include <lib/gdi/gpixmap.h>

DEFINE_REF(eDVBRdsDecoder);

/* RDS of AAC stations. Some stations (for example the ARD radio stations on 19.2E, AAC in LATM / LOAS) put the UECP
   stream into the data_stream_element (DSE) of the AAC frames, bytes in order (not from the frame end as in MPEG
   ancillary data). DSE usually follows the audio elements, which have no length fields, so every frame is walked element
   by element (lib/dvb/hdsspectru.cpp, CititorDse, without the band levels). A LATM frame may cross a PES packet
   boundary: the payload is collected here and cut into whole frames. */
struct eDVBRdsDecoder::AacRds
{
	enum { BUFFER = 16384, DETECT_MAX = 65536, FRAMES_PER_PACKET = 32 };
	int kind;                               /* hdsspectru::FEL_LATM / FEL_ADTS once three frames in a row were seen */
	int examined;                           /* payload bytes looked at while detecting */
	bool gaveUp;                            /* no AAC in DETECT_MAX bytes: the stream is not AAC, stop looking */
	int len;
	hdsspectru::CititorDse *reader;
	unsigned char buf[BUFFER];
	unsigned char dse[2048];
	AacRds(): kind(0), examined(0), gaveUp(false), len(0), reader(0) { }
	~AacRds() { hdsspectru::distrugeDse(reader); }
};

static size_t aacFrameLength(int kind, const unsigned char *d, size_t n)
{
	return hdsspectru::lungimeAac(kind, d, n);
}

/* three whole frames of `kind` in a row from d -> true */
static bool aacThreeFrames(int kind, const unsigned char *d, size_t n)
{
	size_t pos = 0;
	for (int k = 0; k < 3; k++)
	{
		size_t l = aacFrameLength(kind, d + pos, n - pos);
		if (!l || pos + l > n)
			return false;
		pos += l;
	}
	return true;
}

eDVBRdsDecoder::eDVBRdsDecoder(iDVBDemux *demux, int type)
	:msgPtr(0), bsflag(0), qdar_pos(0), t_ptr(0), qdarmvi_show(0), state(0)
	,m_type(type), m_pid(-1), m_aac(0), m_abortTimer(eTimer::create(eApp))
{
	setStreamID(0xC0, 0xC0);

	/* getRadioText() and getRtpText() are read before any message arrives (a station without RDS, AAC audio where
	   no MPEG frame is ever parsed): every text buffer starts empty, never with what the heap held before (the
	   decoder is created anew for each service and malloc hands back the same block, so stale bytes looked like the
	   same text on different stations) */
	memset(message, 0, sizeof(message));
	memset(lastmessage, 0, sizeof(lastmessage));
	memset(datamessage, 0, sizeof(datamessage));
	memset(rtp_buf, 0, sizeof(rtp_buf));
	memset(rtplus_osd, 0, sizeof(rtplus_osd));
	memset(rass_picture_mask, 0, sizeof(rass_picture_mask));
	memset(rtp_item, 0, sizeof(rtp_item));
	leninfo = text_len = text_len2 = 0;
	crc16 = 0;
	crc = 0xFFFF;
	part = parts = 0;
	partcnt = -1;

	if (demux->createPESReader(eApp, m_pes_reader))
		eDebug("failed to create PES reader!");
	else if (type == 0)
		m_pes_reader->connectRead(sigc::mem_fun(*this, &eDVBRdsDecoder::processData), m_read_connection);
	else
		m_pes_reader->connectRead(sigc::mem_fun(*this, &eDVBRdsDecoder::gotAncillaryData), m_read_connection);
	CONNECT(m_abortTimer->timeout, eDVBRdsDecoder::abortNonAvail);
}

eDVBRdsDecoder::~eDVBRdsDecoder()
{
	delete m_aac;
	// delete cached rass slides
	for (int page=0; page < 10; ++page)
	{
		unsigned char mask = rass_picture_mask[(page*4)/8];
		if (page % 2)
			mask >>= 4;
		int subpage=0;
		while(mask)
		{
			if (mask & 1)
			{
				std::string filename = getRassPicture(page, subpage);
				if (filename.length())
					remove(filename.c_str());
			}
			mask >>= 1;
			++subpage;
		}
	}
	remove("/tmp/RassLast.mvi");
}

#define SWAP(x)	((x<<8)|(x>>8))
#define LO(x)	(x&0xFF)

static inline unsigned short crc_ccitt_byte( unsigned short crc, unsigned char c )
{
	crc = SWAP(crc) ^ c;
	crc = crc ^ (LO(crc) >> 4);
	crc = crc ^ (SWAP(LO(crc)) << 4) ^ (LO(crc) << 5);
	return crc;
}

static int bitrate[3][3][16] = {
	{
		// MPEG-2, L3
		{-1,8000,16000,24000,32000,40000,48000,56000,64000,80000,96000,112000,128000,144000,160000,0}, 
		// MPEG-2, L2
		{-1,8000,16000,24000,32000,40000,48000,56000,64000,80000,96000,112000,128000,144000,160000,0},
		// MPEG-2, L1
		{-1,32000,48000,56000,64000,80000,96000,112000,128000,144000,160000,176000,192000,224000,256000,0}
	},
	{
		// MPEG-1, L3
		{-1,32000,40000,48000,56000,64000,80000,96000,112000,128000,160000,192000,224000,256000,320000,0}, 
		// MPEG-1, L2
		{-1,32000,48000,56000,64000,80000,96000,112000,128000,160000,192000,224000,256000,320000,384000,0},
		// MPEG-1, L1
		{-1,32000,64000,96000,128000,160000,192000,224000,256000,288000,320000,352000,384000,416000,448000,0}
	},
	{
		//MPEG-2.5, L3??
		{-1,6000,8000,10000,12000,16000,20000,24000,28000,320000,40000,48000,56000,64000,80000,0},
		//MPEG-2.5, L2
		{-1,6000,8000,10000,12000,16000,20000,24000,28000,320000,40000,48000,56000,64000,80000,0},
		//MPEG-2.5, L1
		{-1,8000,12000,16000,20000,24000,32000,40000,48000,560000,64000,80000,96000,112000,128000,0}
	}
};

static int frequency[3][4] = {
	// MPEG2 - 22.05, 24, 16khz
	{ 22050,24000,16000,0 },
	// MPEG1 - 44.1, 48, 32khz
	{ 44100,48000,32000,0 },
	// MPEG2.5 - 11.025, 12, 8khz
	{ 11025,12000,8000,0 }
};

void eDVBRdsDecoder::connectEvent(const sigc::slot<void(int)> &slot, ePtr<eConnection> &connection)
{
	connection = new eConnection(this, m_event.connect(slot));
}

void eDVBRdsDecoder::addToPictureMask(int id)
{
	int page = id / 1000;
	int tmp = page > 0 ? id / page : id;
	int subpage = 0;
	while(tmp > 1000)
	{
		++subpage;
		tmp -= 1000;
		tmp *= 10;
	}
	int index = (page*4+subpage)/8;
	int val = (page%2) ? 16 * (1 << subpage) : (1 << subpage);
	if (rass_picture_mask[index] & val) // already have this picture
		return;
	rass_picture_mask[index] |= val;
	/* emit */ m_event(RassInteractivePicMaskChanged);
}

void eDVBRdsDecoder::removeFromPictureMask(int id)
{
	int page = id / 1000;
	int tmp = page > 0 ? id / page : id;
	int subpage = 0;
	while(tmp > 1000)
	{
		++subpage;
		tmp -= 1000;
		tmp *= 10;
	}
	int index = (page*4)/8;
	int val = (page%2) ? 16 * (1 << subpage) : (1 << subpage);
	if (rass_picture_mask[index] & val) // have this picture
	{
		rass_picture_mask[index] &= ~val;
		/* emit */ m_event(RassInteractivePicMaskChanged);
	}
}

void eDVBRdsDecoder::processPESPacket(__u8 *data, int len)
{
	int pos=9+data[8];// skip pes header

	if (pos >= len)
		return;
	/* AAC (LATM / LOAS, ADTS): once recognised the stream stays AAC; MPEG audio packets start with an MPEG frame
	   (layer bits not 00, so never taken for ADTS) and keep the path below */
	if (m_aac && m_aac->kind)
	{
		processAac(data + pos, len - pos);
		return;
	}
	bool mpeg = pos + 1 < len && data[pos] == 0xFF && (data[pos + 1] & 0xE0) == 0xE0 && (data[pos + 1] & 0x06);
	if (!mpeg && detectAac(data + pos, len - pos))
		return;

	while (pos < len)
	{
		if ((0xFF & data[pos]) != 0xFF || (0xF0 & data[pos + 1]) != 0xF0)
			return;

		int padding_bit = (data[pos + 2]>>1) & 1;
		int mode = (data[pos + 3]>>6) & 3;
		int channel = mode == 3 ? 1 : 2;
		int id = (data[pos + 1] >> 3) & 1;
		int emphasis_bit = data[pos + 3] & 3;
		//int protection_bit = data[pos + 1] & 1;
		int rate = -1;
		int sample_freq = -1;
		int layer = -1;

		if (emphasis_bit == 2 && id == 1 )
			id = 2;

		if ((layer = (data[pos + 1]>>1) & 3) < 1)
			return;

		if ((rate = bitrate[id][layer - 1][(data[pos + 2]>>4) & 0xf]) < 1)
			return;

		if ((sample_freq = frequency[id][(data[pos + 2]>>2) & 3]) == 0)
			return;

		if (id == 1 && layer == 2)
		{
			if (rate / channel < 32000)
				return;
			if (rate / channel > 192000)
				return;
		}

		int frame_size = layer < 3 ?
			(144 * rate / sample_freq) + padding_bit :
			((12 * rate / sample_freq) * 4) + (4 * padding_bit);

		pos += frame_size;

#if 0
//		eDebug("protection_bit ? %d", protection_bit);
//		int offs = protection_bit ? pos - 1 : pos - 3;
//		if (data[offs] != 0xFD)
//			offs += 2;
//		eDebug("%02x %02x %02x %02x %02x", data[offs-2], data[offs-1], data[offs], data[offs+1], data[offs+2]);
#else
		int offs = pos - 1;
#endif

		if (data[offs] == 0xFD)
		{
			m_abortTimer->stop();
			int ancillary_len = 1 + data[offs - 1];
			offs -= ancillary_len;
			gotAncillaryData(data+offs, ancillary_len-1);
		}
	}
}

/* Collects payload of packets that do not start with an MPEG frame and looks for three LATM / LOAS or ADTS frames in a
   row. -> true when the stream is AAC (the collected frames are then read at once). */
bool eDVBRdsDecoder::detectAac(const __u8 *data, int len)
{
	if (!m_aac)
	{
		m_aac = new AacRds();
		if (!m_aac)
			return false;
	}
	AacRds &a = *m_aac;
	if (a.gaveUp)
		return false;
	int n = len;
	/* only the newest bytes are kept (three frames fit: a frame is at most hdsspectru::DSE_CADRU_MAX long) */
	if (n >= AacRds::BUFFER)
	{
		data += n - AacRds::BUFFER;
		n = AacRds::BUFFER;
		a.len = 0;
	}
	else if (a.len + n > AacRds::BUFFER)
	{
		int drop = a.len + n - AacRds::BUFFER;
		memmove(a.buf, a.buf + drop, a.len - drop);
		a.len -= drop;
	}
	memcpy(a.buf + a.len, data, n);
	a.len += n;
	a.examined += len;
	for (int i = 0; i + 7 <= a.len; i++)
	{
		int kind = 0;
		if (a.buf[i] == 0x56 && (a.buf[i + 1] & 0xE0) == 0xE0)
			kind = hdsspectru::FEL_LATM;
		else if (a.buf[i] == 0xFF && (a.buf[i + 1] & 0xF6) == 0xF0)
			kind = hdsspectru::FEL_ADTS;
		if (kind && aacThreeFrames(kind, a.buf + i, a.len - i))
		{
			memmove(a.buf, a.buf + i, a.len - i);
			a.len -= i;
			a.kind = kind;
			a.reader = hdsspectru::creeazaDse();
			eDebug("radiotext: AAC audio (%s), RDS from the DSE elements", kind == hdsspectru::FEL_LATM ? "LATM" : "ADTS");
			processAac(0, 0);
			return true;
		}
	}
	if (a.examined > AacRds::DETECT_MAX)
	{
		a.gaveUp = true;
		a.len = 0;
	}
	return false;
}

/* Whole AAC frames from the collected payload: the DSE bytes of each one go to the UECP decoder, in order. After a lost
   sync the next frame start is searched byte by byte. */
void eDVBRdsDecoder::processAac(const __u8 *data, int len)
{
	AacRds &a = *m_aac;
	if (len > 0)
	{
		if (len > AacRds::BUFFER - a.len)
		{
			/* more than a buffer without a whole frame: sync lost, start again from the new data */
			a.len = 0;
			if (len > AacRds::BUFFER)
			{
				data += len - AacRds::BUFFER;
				len = AacRds::BUFFER;
			}
		}
		memcpy(a.buf + a.len, data, len);
		a.len += len;
	}
	int pos = 0;
	int frames = 0;
	while (pos + 7 <= a.len && frames < AacRds::FRAMES_PER_PACKET)
	{
		size_t l = aacFrameLength(a.kind, a.buf + pos, a.len - pos);
		if (!l)
		{
			++pos;
			continue;
		}
		if (pos + (int)l > a.len)
			break;
		++frames;
		int n = a.reader ? hdsspectru::dse(a.reader, a.kind, a.buf + pos, l, a.dse, sizeof(a.dse)) : -1;
		if (n < 0)
		{
			/* a frame that cannot be read (LATM before its first configuration) is skipped whole when the next frame
			   starts right after it; otherwise it was a false sync: one byte further */
			if (pos + (int)l == a.len || aacFrameLength(a.kind, a.buf + pos + l, a.len - pos - l))
				pos += l;
			else
				++pos;
			continue;
		}
		if (n > 0)
		{
			/* a UECP start in the data: RDS is here, the reader stays on */
			if (memchr(a.dse, 0xFE, n))
				m_abortTimer->stop();
			ancillary(a.dse, n, true);
		}
		pos += l;
	}
	if (pos > 0)
	{
		memmove(a.buf, a.buf + pos, a.len - pos);
		a.len -= pos;
	}
}

void eDVBRdsDecoder::process_qdar(unsigned char *buf)
{
	if (buf[0] == 0x40 && buf[1] == 0xDA)
	{
		unsigned int item,cnt,ctrl,item_type;
		unsigned long item_length,id,item_no,ptr,tmp;
		unsigned short crc_qdar,crc_read;
		char fname[50];
		ptr=4;cnt=0;
		item=buf[2]<<8; // Number of Items
		item|=buf[3];
		
		while ( cnt++ < item ) //read in items
		{
			id=buf[ptr++]<<8; //QDarID
			id|=buf[ptr++];
			
			item_no=buf[ptr++]<<8; // Item Number
			item_no|=buf[ptr++];
			
			ctrl=buf[ptr++]; //controlbyte
			item_type=buf[ptr++]; //item type
			
			item_length=buf[ptr++]<<24; // Item length
			item_length|=buf[ptr++]<<16;
			item_length|=buf[ptr++]<<8;
			item_length|=buf[ptr++];
			
			ptr=ptr+4; // rfu Bytes ... not used
			tmp=ptr; // calc crc
			crc_qdar=0xFFFF;
			while (tmp < ptr+item_length)
				crc_qdar = crc_ccitt_byte(crc_qdar, buf[tmp++]);
		
			crc_read=buf[ptr+item_length]<<8;
			crc_read|=buf[ptr+item_length+1];
			//eDebug("[RDS/Rass] CRC read: %04X calculated: %04X",crc_read,crc_qdar^0xFFFF);

			if (crc_read == (crc_qdar^0xFFFF)) // process item
			{
				switch(item_type)
				{
					case 0x01: //Stillframe
						if (ctrl&0x01) // display slide
						{
							sprintf(fname,"/tmp/RassLast.mvi");
							FILE *fh=fopen(fname,"wb");
							fwrite(buf+ptr,1,item_length-2,fh);
							fclose(fh);
							/*emit*/ m_event(RecvRassSlidePic);
							qdarmvi_show=1;
						}
						if (ctrl&0x02) // save slide for interactive mode
						{
							if (id == 0 || id >= 1000)
							{
								sprintf(fname,"/tmp/Rass%04d.mvi",(int)id);
								FILE *fh=fopen(fname,"wb");
								fwrite(buf+ptr,1,item_length-2,fh);
								fclose(fh);
								addToPictureMask(id);
							}
							else
								eDebug("ignore recv interactive picture id %lu", id);
						}
						if (ctrl&0x04) // display slide if nothing had been displayed yet
						{
							if (qdarmvi_show != 1)
							{
								sprintf(fname,"/tmp/RassLast.mvi");
								FILE *fh=fopen(fname,"wb");
								fwrite(buf+ptr,1,item_length-2,fh);
								fclose(fh);
								/*emit*/ m_event(RecvRassSlidePic);
								qdarmvi_show=1;
							}
						}
						if (ctrl&0x08) // delete slide
						{
							eDebug("delete slide id %lu, item_no %lu", id, item_no);
							if (id == 0 || id >= 1000)
							{
								eDebug("delete %lu", id);
								removeFromPictureMask(id);
								sprintf(fname,"/tmp/Rass%04d.mvi",(int)id); // was item_no ? ! ?
								remove(fname);
							}
							else
								eDebug("ignore del interactive picture id %lu", id);
						}
						break;
					default: //nothing more yet defined
						break;
				}
			} 
			else
			{
				eDebug("[RDS/Rass] CRC error, skip Rass-Qdar-Item");
			}
			
			ptr=+item_length;
		}
	}
	else
	{
		eDebug("[RDS/Rass] No Rass-QDAR archive (%02X %02X) so skipping !\n",buf[0],buf[1]);
	}
}

void eDVBRdsDecoder::gotAncillaryData(const __u8 *buf, int len)
{
	ancillary(buf, len, m_type != 0);
}

void eDVBRdsDecoder::ancillary(const __u8 *buf, int len, bool forward)
{
	if (len <= 0)
		return;
	int pos = forward ? 0 : len-1;
	while ( len )
	{
		unsigned char c = buf[pos];

		pos += forward ? 1 : -1;

		--len;

		if (bsflag == 1) // byte stuffing
		{
			bsflag=2;
			switch (c)
			{
				case 0x00: c=0xFD; break;
				case 0x01: c=0xFE; break;
				case 0x02: c=0xFF; break;
			}
		}

		if (c == 0xFD && bsflag ==0) 
			bsflag=1;
		else
			bsflag=0;
					
		if (bsflag == 0) 
		{
			if ( state == 1 )
				crc=0xFFFF;
			if (( state >= 1 && state < 11 ) || ( state >=26 && state < 36 ))
				crc = crc_ccitt_byte(crc, c);

			switch (state)
			{
				case 0:
					if ( c==0xFE )  // Startkennung
						state=1;
					break;
				case 1: // 10bit Site Address + 6bit Encoder Address
				case 2:
				case 3: // Sequence Counter
					++state;
					break;
				case 4:
					leninfo=c;
					++state;
					break;
				case 5:
					switch (c)
					{
						case 0x0A: // Radiotext
							++state;
							break;
						case 0x46: // Radiotext Plus tags
							state=38;
							break;
						case 0xDA: // Rass
							state=26;
							break;
						default: // reset to state 0
							state=0;
					}
					break;

					// process Radiotext
				case 6: // Data Set Number ... ignore
				case 7: // Program Service Number ... ignore
					++state;
					break;
				case 8: // Message Element Length
					text_len=c;
					if ( !text_len || text_len > 65 || text_len > leninfo-4)
						state=0;
					else
					{
						++state;
						text_len-=2;
						msgPtr=0;
					}
					break;
				case 9: // Radio Text Status bit:
					// 0   = AB-flagcontrol
					// 1-4 = Transmission-Number
					// 5-6 = Buffer-Config
					++state; // ignore ...
					break;
				case 10:
					/* the bytes are kept as sent: the character set (EBU Latin by the standard, ISO-8859-x or
					   UTF-8 from some encoders) is chosen on the whole message by the reader
					   (lib/python/Components/HdsRdsText.py); getText() hands them over one byte per character */
					message[msgPtr++]=c;
					if(text_len)
						--text_len;
					else
						++state;
					break;
				case 11:
					crc16=c<<8;
					++state;
					break;
				case 12:
					crc16|=c;
					message[msgPtr--]=0;
					while(message[msgPtr] == ' ' && msgPtr > 0)
						message[msgPtr--] = 0;
					if ( crc16 == (crc^0xFFFF) )
					{
						eDebug("radiotext: (%s)", message);
						/*emit*/ m_event(RadioTextChanged);
						memcpy(lastmessage,message,66);
					}
					else
						eDebug("invalid radiotext crc (%s)", message);
					state=0;
					break;

				// process Rass
				case 26: //MEL
					text_len = c;
					text_len2 = c;
					++state;
					text_len-=9;
					text_len2-=9;
					t_ptr=0;
					break;
				case 27: // SID not used atm
					++state;
					break;
				case 28: // SID not used atm
					++state;
					break;
				case 29: // PNR packet number
					part=c<<16;
					++state;
					break;
				case 30: // PNR packet number
					part|=c<<8;
					++state;
					break;
				case 31: // PNR packet number
					part|=c;
					++state;
					break;
				case 32: // NOP number of packets
					parts=c<<16;
					++state;
					break;
				case 33: // NOP number of packets
					parts|=c<<8;
					++state;
					break;
				case 34: // NOP number of packets
					parts|=c;
					++state;
					break;
				case 35:
					datamessage[t_ptr++]=c;
					if(text_len) 
						--text_len;
					else
						++state;
					break;
				case 36:
					crc16=c<<8;
					++state;
					break;
				case 37:
					crc16|=c;
					//eDebug("[RDS/Rass] CRC read: %04X CRC calculated: %04X",crc16,crc^0xFFFF);
					state=0;
					if ( crc16 == (crc^0xFFFF) ) 
					{
						if (partcnt == -1) 
							partcnt=1;
						if (partcnt == part)
						{
							memcpy(qdar+qdar_pos,datamessage,text_len2+1);
							qdar_pos=qdar_pos+text_len2+1;
							if (partcnt == parts)
							{
								process_qdar(qdar); // decode qdar archive
								qdar_pos=0;
								partcnt=-1;
							}
							else
								++partcnt;
						}
						else
						{
							qdar_pos=0;
							partcnt=-1;
						}
					}
					else
					{
						eDebug("[RDS/Rass] CRC error, skip Rass-Qdar-Packet");
						eDebug("[RDS/Rass] CRC read: %04X CRC calculated: %04X",crc16,crc^0xFFFF);
						partcnt=-1;
					}
					state=0;
					break;

				// process RT plus tags ... 
				case 38: // Message Element Length
					text_len=c;	
					++state;
					break;
				case 39: // Application ID 
				case 40: // always 0x4BD7 so we ignore it ;)
				case 41: // Applicationgroup Typecode/PTY ... ignore
					++state;
					break;
				case 42:
					rtp_buf[0]=c;
					++state;
					break;
				case 43:
					rtp_buf[1]=c;
					++state;
					break;
				case 44:
					rtp_buf[2]=c;
					++state;
					break;
				case 45:
					rtp_buf[3]=c;
					++state;
					break;
				case 46: // bit 10#4 = Item Togglebit
					// bit 10#3 = Item Runningbit
					// Tag1: bit 10#2..11#5 = Contenttype, 11#4..12#7 = Startmarker, 12#6..12#1 = Length
					rtp_buf[4]=c;
					if (lastmessage[0] == 0) // no rds message till now ? quit ...
					{
						/* back to waiting for a message start: staying in this state would take every later byte
						   for RT+ tag data (an RT+ message arriving before the first radiotext stopped all RDS) */
						state=0;
						break;
					}
					int rtp_typ[2],rtp_start[2],rtp_len[2];
					rtp_typ[0]   = (0x38 & rtp_buf[0]<<3) | rtp_buf[1]>>5;
					rtp_start[0] = (0x3e & rtp_buf[1]<<1) | rtp_buf[2]>>7;
					rtp_len[0]   = 0x3f & rtp_buf[2]>>1;
					// Tag2: bit 12#0..13#3 = Contenttype, 13#2..14#5 = Startmarker, 14#4..14#0 = Length(5bit)
					rtp_typ[1]   = (0x20 & rtp_buf[2]<<5) | rtp_buf[3]>>3;
					rtp_start[1] = (0x38 & rtp_buf[3]<<3) | rtp_buf[4]>>5;
					rtp_len[1]   = 0x1f & rtp_buf[4];
									
					unsigned char rtplus_osd_tmp[64];
					rtplus_osd_tmp[0] = 0; /* empty when there is no artist: it is printed below in any case */
					
					if (rtp_start[0] < 66 && (rtp_len[0]+rtp_start[0]) < 66 && rtp_len[0] < 63) /* len+1 bytes and the terminator fit the 64 byte item */
					{
						memcpy(rtp_item[rtp_typ[0]],lastmessage+rtp_start[0],rtp_len[0]+1);
						rtp_item[rtp_typ[0]][rtp_len[0]+1]=0;
					}
									
					if (rtp_typ[0] != rtp_typ[1])
					{
						if (rtp_start[1] < 66 && (rtp_len[1]+rtp_start[1]) < 66)
						{
							memcpy(rtp_item[rtp_typ[1]],lastmessage+rtp_start[1],rtp_len[1]+1);
							rtp_item[rtp_typ[1]][rtp_len[1]+1]=0;
						}
					}

					// main RTPlus item_types used by the radio stations:
					// 1 title
					// 4 artist
					// 24 info.date_time
					// 31 stationname
					// 32 program.now
					// 39 homepage
					// 41 phone.hotline
					// 46 email.hotline
					// todo: make a window to display all saved items ...
	
					//create RTPlus OSD for title/artist
					rtplus_osd[0]=0;
								
					if ( rtp_item[4][0] != 0 )//artist
						if (snprintf((char*)rtplus_osd_tmp, sizeof(rtplus_osd_tmp), " (%s)", rtp_item[4]) < 0) rtplus_osd_tmp[0] = 0;
								
					if ( rtp_item[1][0] != 0 )//title
						if (snprintf((char*)rtplus_osd, sizeof(rtplus_osd), "%s%s", rtp_item[1], rtplus_osd_tmp) < 0) rtplus_osd[0] = 0;
									
					if ( rtplus_osd[0] != 0 )
					{
						/*emit*/ m_event(RtpTextChanged);
						eDebug("RTPlus: %s",rtplus_osd);
					}
						
					state=0;
					break;
			}
		}
	}
}

std::string eDVBRdsDecoder::getRassPicture(int page, int subpage)
{
	int val=0;
	
	switch(subpage)
	{
		case 0:
			val=page*1000;
			break;
		case 1:
			val=page*1100;
			break;
		case 2:
			val=page*1110;
			break;
		case 3:
			val=page*1111;
			break;
	}
	char fname[50];
	sprintf(fname,"/tmp/Rass%04d.mvi",val);
	return fname;
}

int eDVBRdsDecoder::start(int pid)
{
	int ret = -1;
	if (m_pes_reader && !(ret = m_pes_reader->start(pid)) && m_type == 0)
		m_abortTimer->startLongTimer(20);
	m_pid = pid;
	return ret;
}

void eDVBRdsDecoder::abortNonAvail()
{
	eDebug("no ancillary data in audio stream... abort radiotext pes parser");
	if (m_pes_reader)
		m_pes_reader->stop();
}

ePyObject eDVBRdsDecoder::getRassPictureMask()
{
	ePyObject ret = PyTuple_New(5);
	PyTuple_SET_ITEM(ret, 0, PyLong_FromLong(rass_picture_mask[0]));
	PyTuple_SET_ITEM(ret, 1, PyLong_FromLong(rass_picture_mask[1]));
	PyTuple_SET_ITEM(ret, 2, PyLong_FromLong(rass_picture_mask[2]));
	PyTuple_SET_ITEM(ret, 3, PyLong_FromLong(rass_picture_mask[3]));
	PyTuple_SET_ITEM(ret, 4, PyLong_FromLong(rass_picture_mask[4]));
	return ret;
}

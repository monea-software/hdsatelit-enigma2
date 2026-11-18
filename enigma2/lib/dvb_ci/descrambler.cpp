/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/descrambler.cpp;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: legarea de slotul si jurnalul nostru
   (dvbci_hds_compat.h); eroarea driverului (errno) in jurnal si intoarsa ca -errno; deschiderea unui caN anume si
   alegerea lui dupa lib/dvb_ci/hdscica.h (dispozitivul care primeste cheia CI+, AX HD51, forumul 479); a doua forma a
   cererilor, „OE 2.2”, pentru driverele care o refuza pe prima (descrambler_oe22_*). */
#include <lib/dvb_ci/dvbci_hds_compat.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <lib/dvb_ci/descrambler.h>
#include <lib/dvb_ci/hdscica.h>
#include <lib/base/eerror.h>

enum ca_descr_data_type
{
	CA_DATA_IV,
	CA_DATA_KEY,
};

enum ca_descr_parity
{
	CA_PARITY_EVEN,
	CA_PARITY_ODD,
};

struct ca_descr_data
{
	unsigned int index;
	enum ca_descr_parity parity;
	enum ca_descr_data_type data_type;
	unsigned int length;
	unsigned char *data;
};

struct vu_ca_descr_data
{
	int slot_id;
	int fix1; // = 0x6f7c
	int demux_id;
	int tunernum;
	int use_count;
	int program_number;
	int reserved1;
	int fix2; // = 0x1 -> add pids
	int video_pid;
	int audio_pid;
	int reserved2;
	int fix3; // = 0x12345678
	int reserved3;
	int key_register;
	int use_aes; // 0x2 for AES
	unsigned char key[16];
	unsigned char iv[16];
	int audio_number;
	int audio_pids[16];
};

#define CA_SET_DESCR_DATA _IOW('o', 137, struct ca_descr_data)

int descrambler_set_key(int &desc_fd, eDVBCISlot *slot, int parity, unsigned char *data)
{
	bool vuIoctlSuccess = false;
#ifdef DESCRAMBLER_VU
	if (slot->getTunerNum() > 7 || slot->getTunerNum() == -1) // might be VU box with 2 FBC tuners or VU offline decryption -> try to use VU ioctl
	{
		struct vu_ca_descr_data d;

		d.slot_id = slot->getSlotID();
		d.fix1 = 0x6f7c;
		d.demux_id = slot->getCADemuxID();
		d.tunernum = slot->getTunerNum();
		d.use_count = slot->getUseCount();
		d.program_number = slot->getProgramNumber();
		d.fix2 = 0x1;
		d.video_pid = slot->getVideoPid();
		d.audio_pid = slot->getAudioPid();
		d.fix3 = 0x12345678;
		d.key_register = parity;
		d.use_aes = 0x2; // AES
		memcpy(d.key, data, 16);
		memcpy(d.iv, data + 16, 16);
		d.audio_number = slot->getAudioNumber();
		memcpy(d.audio_pids, slot->getAudioPids(), 16 * 4);

		unsigned int ret = ioctl(slot->getFd(), 0x10, &d);
		if (ret == 0)
		{
			vuIoctlSuccess = true;
			descrambler_deinit(desc_fd); // don't set pids for VU ioctl
			desc_fd = -1;
		}
		eDebug("[CI%d] descrambler_set_key vu ret %u", slot->getSlotID(), ret);
	}
#endif
	if (!vuIoctlSuccess)
	{
		struct ca_descr_data d;

		if (desc_fd < 0)
			return -EBADF;

		d.index = slot->getSlotID();
		d.parity = (enum ca_descr_parity)parity;
		d.data_type = CA_DATA_KEY;
		d.length = 16;
		d.data = data;

		if (ioctl(desc_fd, CA_SET_DESCR_DATA, &d) == -1)
		{
			int eroare = errno;
			eWarning("[CI%d descrambler] set key failed: %s (errno %d)", slot->getSlotID(), strerror(eroare), eroare);
			return eroare > 0 ? -eroare : -1;
		}

		d.index = slot->getSlotID();
		d.parity = (enum ca_descr_parity)parity;
		d.data_type = CA_DATA_IV;
		d.length = 16;
		d.data = data + 16;

		if (ioctl(desc_fd, CA_SET_DESCR_DATA, &d) == -1)
		{
			int eroare = errno;
			eWarning("[CI%d descrambler] set iv failed: %s (errno %d)", slot->getSlotID(), strerror(eroare), eroare);
			return eroare > 0 ? -eroare : -1;
		}
	}

	return 0;
}

int descrambler_set_pid(int desc_fd, eDVBCISlot *slot, int enable, int pid)
{
	struct ca_pid p = {};
	unsigned int flags = 0x80;
	eDebug("[CI descrambler]1 index: %x enable: %x pid: %x", slot->getSlotID(), enable, pid);
	if (desc_fd < 0)
		return -1;

	if (slot->getSlotID())
		flags |= 0x40;

	if (enable)
		flags |= 0x20;

	p.pid = pid;
	p.index = flags;
	eDebug("[CI descrambler]2 index: %x enable: %x flags: %x pid: %x", slot->getSlotID(), enable, flags, pid);
	if (ioctl(desc_fd, CA_SET_PID, &p) == -1)
	{
		int eroare = errno;
		if (slot->getDescramblingOptions() > 0)
			return 0;
		eWarning("[CI%d descrambler] set pid failed: %s (errno %d)", slot->getSlotID(), strerror(eroare), eroare);
		return eroare > 0 ? -eroare : -1;
	}

	return 0;
}

/* HD Satelit: forma „OE 2.2” a cererilor de descifrare, API-ul extins al driverelor OE-Alliance, acelasi pe care il
   folosesc OSCam cu extended_cw_api = 1 (sursele GPL: module-dvbapi.h, struct ca_descr_mode si ca_descr_data;
   module-dvbapi.c, dvbapi_set_pid si scrierea cheii AES128) si tvheadend la „Extended (OE 2.2)” (src/descrambler/capmt.c:
   „CA_SET_DESCR_MODE before CA_SET_DESCR”): CA_SET_PID leaga fiecare PID de un descifrator prin indexul lui simplu
   (-1 = dezlegat), CA_SET_DESCR_MODE alege AES-128 CBC pentru acel index, apoi CA_SET_DESCR_DATA da IV-ul si cheia.
   Forma de mai sus (enigma2 OE-Alliance, venita de la Dreambox) pune in CA_SET_PID indexul 0x80|0x40|0x20 si nu alege
   algoritmul; driverul AX HD51 o refuza cu EINVAL si la cheie, si la PID (forumul 479; asistentele 425241 si 452351).
   Aceasta forma se incearca NUMAI dupa ce prima e refuzata pe toate dispozitivele (dvbci_ccmgr.cpp, incearcaOe22). */
struct hds_ca_descr_info
{
	unsigned int num;
	unsigned int type;
};

struct hds_ca_descr_mode
{
	unsigned int index;
	unsigned int algo;        /* 0 DVB-CSA, 1 DES, 2 AES-128 (enum ca_descr_algo din OSCam) */
	unsigned int cipher_mode; /* 0 ECB, 1 CBC */
};

#define HDS_CA_GET_DESCR_INFO _IOR('o', 131, struct hds_ca_descr_info)
#define HDS_CA_SET_DESCR_MODE _IOW('o', 136, struct hds_ca_descr_mode)
#define HDS_CA_ALGO_AES128 2
#define HDS_CA_MODE_CBC 1

/* indexul descifratorului folosit de slot: de sus in jos (numarul dat de CA_GET_DESCR_INFO), departe de indexii pe care
   modulele de acces ii iau de la 0; cand driverul nu spune cate are, numarul slotului */
int descrambler_oe22_index(int desc_fd, eDVBCISlot *slot)
{
	struct hds_ca_descr_info info = {};
	int slotid = slot->getSlotID();
	if (desc_fd >= 0 && ioctl(desc_fd, HDS_CA_GET_DESCR_INFO, &info) == 0)
	{
		eDebug("[CI%d descrambler] OE 2.2: CA_GET_DESCR_INFO num %u type %u", slotid, info.num, info.type);
		if (info.num > (unsigned int)slotid && info.num <= 64)
			return (int)info.num - 1 - slotid;
	}
	else
		eDebug("[CI%d descrambler] OE 2.2: CA_GET_DESCR_INFO: %s", slotid, strerror(errno));
	return slotid;
}

int descrambler_oe22_set_pid(int desc_fd, eDVBCISlot *slot, int index, int enable, int pid)
{
	struct ca_pid p = {};
	if (desc_fd < 0)
		return -EBADF;
	p.pid = pid;
	p.index = enable ? index : -1;
	if (ioctl(desc_fd, CA_SET_PID, &p) == -1)
	{
		int eroare = errno;
		eWarning("[CI%d descrambler] OE 2.2 set pid %x index %d failed: %s (errno %d)", slot->getSlotID(), pid, p.index,
			strerror(eroare), eroare);
		return eroare > 0 ? -eroare : -1;
	}
	return 0;
}

int descrambler_oe22_set_key(int desc_fd, eDVBCISlot *slot, int index, int parity, unsigned char *data, bool *mod_pus)
{
	if (mod_pus)
		*mod_pus = false;
	if (desc_fd < 0)
		return -EBADF;
	struct hds_ca_descr_mode m = {};
	m.index = index;
	m.algo = HDS_CA_ALGO_AES128;
	m.cipher_mode = HDS_CA_MODE_CBC;
	const char *pas = "mode";
	int rezultat = ioctl(desc_fd, HDS_CA_SET_DESCR_MODE, &m);
	struct ca_descr_data d;
	if (rezultat != -1)
	{
		if (mod_pus)
			*mod_pus = true;
		pas = "iv";
		d.index = index;
		d.parity = (enum ca_descr_parity)parity;
		d.data_type = CA_DATA_IV;
		d.length = 16;
		d.data = data + 16;
		rezultat = ioctl(desc_fd, CA_SET_DESCR_DATA, &d);
	}
	if (rezultat != -1)
	{
		pas = "key";
		d.index = index;
		d.parity = (enum ca_descr_parity)parity;
		d.data_type = CA_DATA_KEY;
		d.length = 16;
		d.data = data;
		rezultat = ioctl(desc_fd, CA_SET_DESCR_DATA, &d);
	}
	if (rezultat == -1)
	{
		int eroare = errno;
		eWarning("[CI%d descrambler] OE 2.2 set %s index %d failed: %s (errno %d)", slot->getSlotID(), pas, index,
			strerror(eroare), eroare);
		return eroare > 0 ? -eroare : -1;
	}
	return 0;
}

/* o incercare OE 2.2 pe un dispozitiv deschis: PID-urile legate de index, apoi modul, IV-ul si cheia; la refuz PID-urile se
   dezleaga si, daca modul AES fusese primit, indexul se pune inapoi pe DVB-CSA (sa nu ramana stricat pentru altcineva) */
static int descrambler_oe22_pe_dispozitiv(int fd, eDVBCISlot *slot, int index, const std::vector<uint16_t> &piduri, int parity,
	unsigned char *data, const char **pas)
{
	size_t legate = 0;
	int rezultat = 0;
	*pas = "pid";
	for (; legate < piduri.size(); legate++)
	{
		rezultat = descrambler_oe22_set_pid(fd, slot, index, 1, piduri[legate]);
		if (rezultat != 0)
			break;
	}
	bool mod_pus = false;
	if (rezultat == 0)
	{
		*pas = "cheie";
		rezultat = descrambler_oe22_set_key(fd, slot, index, parity, data, &mod_pus);
	}
	if (rezultat != 0)
	{
		for (size_t k = 0; k < legate; k++)
			descrambler_oe22_set_pid(fd, slot, index, 0, piduri[k]);
		if (mod_pus)
		{
			struct hds_ca_descr_mode m = {};
			m.index = index;
			ioctl(fd, HDS_CA_SET_DESCR_MODE, &m);
		}
	}
	return rezultat;
}

/* HD Satelit: forma OE 2.2 pe dispozitivele potrivite canalului, in ordinea ca<demux>, ca<demuxul decodorului>,
   ca<demux+1> (dispozitivul deschis acum se foloseste asa cum e). true cand toata secventa e primita: fd_nou (ramas deschis),
   ca_nou, fel_nou si index_nou spun unde; altfel false, nimic ramas legat, dispozitivele deschise aici inchise, iar in
   incercate se adauga ce a raspuns driverul (; caN OE 2.2 index I pas: eroarea). Chemata de dvbci_ccmgr.cpp numai dupa ce
   forma de azi e refuzata pe toate dispozitivele. */
bool descrambler_oe22_incearca(eDVBCISlot *slot, int fd_curent, int ca_curent, const std::vector<uint16_t> &piduri, int parity,
	unsigned char *data, int *fd_nou, int *ca_nou, int *fel_nou, int *index_nou, char *incercate, size_t marime)
{
	int ca[HDS_CA_FELURI], fel[HDS_CA_FELURI];
	int n = hdsCaCandidati(HDS_CA_AUTOMAT, -1, HDS_CA_DATE, slot->getCADemuxID(), slot->getCADecodeDemuxID(), ca, fel,
		HDS_CA_FELURI);
	for (int i = 0; i < n; i++)
	{
		size_t l = strlen(incercate);
		bool nou = (fd_curent < 0 || ca[i] != ca_curent);
		int fd = nou ? descrambler_open_ca(slot, ca[i]) : fd_curent;
		if (fd < 0)
		{
			snprintf(incercate + l, marime > l ? marime - l : 0, "; ca%d OE 2.2: nu se deschide", ca[i]);
			continue;
		}
		int index = descrambler_oe22_index(fd, slot);
		const char *pas = "pid";
		int rezultat = descrambler_oe22_pe_dispozitiv(fd, slot, index, piduri, parity, data, &pas);
		if (rezultat == 0)
		{
			*fd_nou = fd;
			*ca_nou = ca[i];
			*fel_nou = fel[i];
			*index_nou = index;
			return true;
		}
		snprintf(incercate + l, marime > l ? marime - l : 0, "; ca%d OE 2.2 index %d %s: %s", ca[i], index, pas,
			strerror(-rezultat));
		if (nou)
			descrambler_deinit(fd);
	}
	return false;
}

/* deschide /dev/dvb/adapter0/ca<ca>; -1 cand nu se poate */
int descrambler_open_ca(eDVBCISlot *slot, int ca)
{
	std::string filename = "/dev/dvb/adapter0/ca" + std::to_string(ca);
	int desc_fd = open(filename.c_str(), O_RDWR | O_NONBLOCK | O_CLOEXEC);
	if (desc_fd == -1)
	{
		int eroare = errno;
		eWarning("[CI%d descrambler] can not open %s: %s", slot->getSlotID(), filename.c_str(), strerror(eroare));
		return -1;
	}
	eDebug("[CI%d descrambler] using ca device %s", slot->getSlotID(), filename.c_str());
	return desc_fd;
}

/* primul dispozitiv care se deschide, din cele potrivite canalului (hdsCaCandidati: cu optiunile 0-3 alese de mana numai
   cel din OE-Alliance; cu „Automat” intai cel care a primit cheia ultima data, apoi felul placii, ca<demux>, demuxul
   decodorului, ca<demux+1>); ca_ales si fel_ales (daca nu sunt nule) primesc caN si felul lui */
int descrambler_init(eDVBCISlot *slot, uint8_t ca_demux_id, int *ca_ales, int *fel_ales)
{
	int ca[HDS_CA_FELURI], fel[HDS_CA_FELURI];
	int n = hdsCaCandidati(slot->getDescramblingOptions(), slot->getCaAles(), HDS_CA_INTAI_PLACA, ca_demux_id,
		slot->getCADecodeDemuxID(), ca, fel, HDS_CA_FELURI);
	for (int i = 0; i < n; i++)
	{
		int desc_fd = descrambler_open_ca(slot, ca[i]);
		if (desc_fd < 0)
			continue;
		if (ca_ales)
			*ca_ales = ca[i];
		if (fel_ales)
			*fel_ales = fel[i];
		return desc_fd;
	}
	return -1;
}

/* HD Satelit: cheia refuzata pe ca<ca_curent>: celelalte dispozitive potrivite canalului, in ordinea din hdsCaCandidati
   (ca la Automat); true cand unul a primit cheia (fd_nou ramane deschis, ca_nou si fel_nou spun care), altfel false. In
   incercate se adauga ce a raspuns fiecare (; caN: eroarea). Si cu optiunile 0-3 alese de mana (0.7.6): dispozitivul
   ales de mana ramane primul deschis (descrambler_init, ca in OE-Alliance), iar celelalte se incearca NUMAI cand driverul
   ii refuza cheia; altfel imaginea statea (darog69, AX HD51: optiunea 3 ramasa de pe 0.7.4, ca1 cu errno 22). */
bool descrambler_set_key_alt(eDVBCISlot *slot, int ca_curent, int parity, unsigned char *data, int *fd_nou, int *ca_nou,
	int *fel_nou, char *incercate, size_t marime)
{
	int ca[HDS_CA_FELURI], fel[HDS_CA_FELURI];
	int n = hdsCaCandidati(HDS_CA_AUTOMAT, slot->getCaAles(), HDS_CA_INTAI_PLACA, slot->getCADemuxID(),
		slot->getCADecodeDemuxID(), ca, fel, HDS_CA_FELURI);
	for (int i = 0; i < n; i++)
	{
		if (ca[i] == ca_curent)
			continue;
		size_t l = strlen(incercate);
		int fd = descrambler_open_ca(slot, ca[i]);
		if (fd < 0)
		{
			snprintf(incercate + l, marime > l ? marime - l : 0, "; ca%d: nu se deschide", ca[i]);
			continue;
		}
		int rezultat = descrambler_set_key(fd, slot, parity, data);
		if (rezultat == 0)
		{
			*fd_nou = fd;
			*ca_nou = ca[i];
			*fel_nou = fel[i];
			return true;
		}
		snprintf(incercate + l, marime > l ? marime - l : 0, "; ca%d: %s", ca[i], strerror(-rezultat));
		descrambler_deinit(fd);
	}
	return false;
}

void descrambler_deinit(int desc_fd)
{
	if (desc_fd >= 0)
		close(desc_fd);
	desc_fd = -1;
}

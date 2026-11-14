/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/descrambler.cpp;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: legarea de slotul si jurnalul nostru
   (dvbci_hds_compat.h); eroarea driverului (errno) in jurnal si intoarsa ca -errno; deschiderea unui caN anume si
   alegerea lui dupa lib/dvb_ci/hdscica.h (dispozitivul care primeste cheia CI+, AX HD51, forumul 479). */
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

/* HD Satelit: cheia refuzata pe ca<ca_curent>. Numai cu „Automat”: celelalte dispozitive potrivite canalului, in
   ordinea din hdsCaCandidati; true cand unul a primit cheia (fd_nou ramane deschis, ca_nou si fel_nou spun care),
   altfel false. In incercate se adauga ce a raspuns fiecare („; caN: eroarea”). */
bool descrambler_set_key_alt(eDVBCISlot *slot, int ca_curent, int parity, unsigned char *data, int *fd_nou, int *ca_nou,
	int *fel_nou, char *incercate, size_t marime)
{
	if (slot->getDescramblingOptions() != HDS_CA_AUTOMAT)
		return false;
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

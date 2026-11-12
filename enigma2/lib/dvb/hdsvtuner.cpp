/*
 * hdsvtuner.cpp: puntea vtuner, eDVBUsbAdapter (tunerele DVB pe USB in Setari tunere si la vizionare).
 *
 * Dupa enigma2 OE-Alliance, lib/dvb/dvb.cpp (eDVBUsbAdapter, vtunerPump; GPL-2.0, autorii enigma2).
 * Modificat de moneasoftware.com si hdsatelit.com, 2026:
 *  - tunerele USB se tin minte in harta puntii si in /tmp/hds_tunere_usb (nu dupa sirul "VTUNER" din nim_sockets);
 *  - firul pompei (poll) se opreste singur cand stickul dispare si inchide demuxul lui, ca deconectarea USB sa se termine;
 *  - partile fara enigma2 sunt in hdsvtuner.h, probate pe PC.
 *
 * Cum merge: stickul are /dev/dvb/adapterN cu frontend0 si demux0. Puntea deschide primul /dev/misc/vtunerK liber al
 * placii si ii spune numele, tipul, FE_INFO, sistemele si adaptorul; driverul vtuner face un frontend virtual pe adapter0.
 * La cautarea frontend-urilor adapter0 (eDVBAdapterLinux), frontend-ul virtual primeste ca dispozitiv frontend-ul USB
 * (harta mappedFrontendName), deci enigma2 acordeaza stickul direct, iar demuxul placii primeste ca sursa frontend-ul
 * virtual. Firul vtunerPump asculta ce PID-uri cere placa (MSG_PIDLIST), le pune pe demuxul stickului si muta fluxul TS
 * din el in vtuner.
 */
#include <lib/base/eerror.h>
#include <lib/dvb/dvb.h>
#include <lib/dvb/hdsvtuner.h>

#include <linux/ioctl.h>
#include <linux/dvb/frontend.h>
#include <linux/dvb/dmx.h>

#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <poll.h>

#if _IOC_NONE > 0               /* MIPS (Vu+ Solo SE): _IOC_NONE = 1 */
#define VTUNER_GET_MESSAGE      1
#define VTUNER_SET_RESPONSE     2
#define VTUNER_SET_NAME         3
#define VTUNER_SET_TYPE         4
#define VTUNER_SET_HAS_OUTPUTS  5
#define VTUNER_SET_FE_INFO      6
#define VTUNER_SET_NUM_MODES    7
#define VTUNER_SET_MODES        8
#else                           /* ARM: _IOC_NONE = 0 */
#define VTUNER_GET_MESSAGE     11
#define VTUNER_SET_RESPONSE    12
#define VTUNER_SET_NAME        13
#define VTUNER_SET_TYPE        14
#define VTUNER_SET_HAS_OUTPUTS 15
#define VTUNER_SET_FE_INFO     16
#define VTUNER_SET_NUM_MODES   17
#define VTUNER_SET_MODES       18
#endif
#define VTUNER_SET_DELSYS      32
#define VTUNER_SET_ADAPTER     33

#define MSG_PIDLIST            14

std::map<std::string, std::string> eDVBAdapterLinux::mappedFrontendName;
std::vector<hdsvtuner::Legatura> eDVBUsbAdapter::s_legaturi;

bool eDVBAdapterLinux::isusb(int nr)
{
	return hdsvtuner::esteUsb("", nr);
}

static ssize_t hdsCitesteO(int fd, void *buf, size_t n)
{
	ssize_t r;
	do
		r = ::read(fd, buf, n);
	while (r < 0 && errno == EINTR);
	return r;
}

static ssize_t hdsScrieTot(int fd, const unsigned char *buf, size_t n)
{
	size_t scris = 0;
	while (scris < n)
	{
		ssize_t r = ::write(fd, buf + scris, n - scris);
		if (r < 0)
		{
			if (errno == EINTR)
				continue;
			return -1;
		}
		if (r == 0)
			return scris;
		scris += r;
	}
	return scris;
}

DEFINE_REF(eDVBUsbAdapter);

eDVBUsbAdapter::eDVBUsbAdapter(int nr)
	: eDVBAdapterLinux(nr, false), m_running(false), m_pumpThread(0), m_pumpStarted(false), m_demuxFd(-1), m_vtunerFd(-1)
{
	m_pipeFd[0] = m_pipeFd[1] = -1;
	memset(m_pidList, 0xff, sizeof(m_pidList));

	struct dvb_frontend_info fe_info;
	memset(&fe_info, 0, sizeof(fe_info));
	struct dtv_property prop[1];
	memset(prop, 0, sizeof(prop));
	struct dtv_properties props;
	memset(&props, 0, sizeof(props));
	char filename[256];
	char name[128] = {0};
	int vtunerid = nr - 1;
	const char *type = 0;

	/* frontend-ul virtual pe care il va face vtuner: urmatorul indice liber de pe adapter0 */
	int virtual_fe = hdsvtuner::numaraFrontenduri("", 0);
	snprintf(filename, sizeof(filename), "/dev/dvb/adapter0/frontend%d", virtual_fe);
	m_virtualFrontendName = filename;

	/* numele stickului */
	snprintf(filename, sizeof(filename), "/sys/class/dvb/dvb%d.frontend0/device/product", nr);
	int file = ::open(filename, O_RDONLY | O_CLOEXEC);
	if (file < 0)
	{
		snprintf(filename, sizeof(filename), "/sys/class/dvb/dvb%d.frontend0/device/manufacturer", nr);
		file = ::open(filename, O_RDONLY | O_CLOEXEC);
	}
	if (file >= 0)
	{
		ssize_t len = hdsCitesteO(file, name, sizeof(name) - 1);
		name[len > 0 ? len : 0] = 0;
		::close(file);
	}

	snprintf(filename, sizeof(filename), "/dev/dvb/adapter%d/frontend0", nr);
	int frontend = ::open(filename, O_RDWR | O_CLOEXEC);
	if (frontend < 0)
	{
		eWarning("[eDVBUsbAdapter] adapter%d: frontend0 nu se deschide (%m)", nr);
		return;
	}
	if (::ioctl(frontend, FE_GET_INFO, &fe_info) < 0)
	{
		eWarning("[eDVBUsbAdapter] adapter%d: FE_GET_INFO (%m)", nr);
		::close(frontend);
		return;
	}
	prop[0].cmd = DTV_ENUM_DELSYS;
	props.num = 1;
	props.props = prop;
	if (::ioctl(frontend, FE_GET_PROPERTY, &props) < 0)
	{
		eDebug("[eDVBUsbAdapter] adapter%d: DTV_ENUM_DELSYS (%m)", nr);
		prop[0].u.buffer.len = 0;
	}
	::close(frontend);
	m_usbFrontendName = filename;

	std::string nume = hdsvtuner::curataNume(name);
	if (nume.empty())
	{
		char din_info[sizeof(fe_info.name) + 1];
		memcpy(din_info, fe_info.name, sizeof(fe_info.name));
		din_info[sizeof(fe_info.name)] = 0;
		nume = hdsvtuner::curataNume(din_info);
	}
	if (nume.empty())
		nume = "USB frontend";

	type = hdsvtuner::tipVtuner(fe_info.type, (fe_info.caps & FE_CAN_2G_MODULATION) != 0);
	if (!type)
	{
		eWarning("[eDVBUsbAdapter] adapter%d: tipul 0x%x nu e suportat", nr, fe_info.type);
		return;
	}

	snprintf(filename, sizeof(filename), "/dev/dvb/adapter%d/demux0", nr);
	m_demuxFd = ::open(filename, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if (m_demuxFd < 0)
	{
		eWarning("[eDVBUsbAdapter] adapter%d: demux0 nu se deschide (%m)", nr);
		return;
	}

	while (m_vtunerFd < 0 && vtunerid >= 0)
	{
		snprintf(filename, sizeof(filename), "/dev/misc/vtuner%d", vtunerid);
		if (::access(filename, F_OK) < 0)
			break;
		m_vtunerFd = ::open(filename, O_RDWR | O_CLOEXEC);
		if (m_vtunerFd < 0)
			vtunerid++;
	}
	if (m_vtunerFd < 0)
	{
		eWarning("[eDVBUsbAdapter] adapter%d (%s): placa nu are vtuner liber (/dev/misc/vtuner%d); tunerul USB nu se poate folosi",
			nr, nume.c_str(), vtunerid);
		::close(m_demuxFd);
		m_demuxFd = -1;
		return;
	}

	eDebug("[eDVBUsbAdapter] adapter%d/frontend0 (%s, %s) legat de vtuner%d, frontend virtual %s",
		nr, nume.c_str(), type, vtunerid, m_virtualFrontendName.c_str());

	char nume_ioctl[128];
	snprintf(nume_ioctl, sizeof(nume_ioctl), "%s", nume.c_str());
	char tip_ioctl[8] = {0};
	snprintf(tip_ioctl, sizeof(tip_ioctl), "%s", type);
	::ioctl(m_vtunerFd, VTUNER_SET_NAME, nume_ioctl);
	::ioctl(m_vtunerFd, VTUNER_SET_TYPE, tip_ioctl);
	::ioctl(m_vtunerFd, VTUNER_SET_FE_INFO, &fe_info);
	if (prop[0].u.buffer.len > 0)
		::ioctl(m_vtunerFd, VTUNER_SET_DELSYS, prop[0].u.buffer.data);
	::ioctl(m_vtunerFd, VTUNER_SET_HAS_OUTPUTS, "no");
	::ioctl(m_vtunerFd, VTUNER_SET_ADAPTER, nr);

	if (::pipe(m_pipeFd) == -1)
	{
		eWarning("[eDVBUsbAdapter] pipe (%m)");
		m_pipeFd[0] = m_pipeFd[1] = -1;
		::close(m_vtunerFd);
		m_vtunerFd = -1;
		::close(m_demuxFd);
		m_demuxFd = -1;
		return;
	}

	mappedFrontendName[m_virtualFrontendName] = m_usbFrontendName;
	hdsvtuner::Legatura legatura;
	legatura.virtual_fe = virtual_fe;
	legatura.usb = m_usbFrontendName;
	legatura.nume = nume;
	legatura.sisteme = hdsvtuner::textSisteme(prop[0].u.buffer.data,
		prop[0].u.buffer.len < sizeof(prop[0].u.buffer.data) ? prop[0].u.buffer.len : sizeof(prop[0].u.buffer.data), type);
	s_legaturi.push_back(legatura);

	m_running = true;
	if (pthread_create(&m_pumpThread, NULL, threadproc, (void*)this) == 0)
		m_pumpStarted = true;
	else
	{
		m_running = false;
		eWarning("[eDVBUsbAdapter] firul pompei nu porneste (%m)");
	}
}

eDVBUsbAdapter::~eDVBUsbAdapter()
{
	m_running = false;
	if (m_pipeFd[1] >= 0)
	{
		::close(m_pipeFd[1]);
		m_pipeFd[1] = -1;
	}
	if (m_pumpStarted)
		pthread_join(m_pumpThread, NULL);
	if (m_pipeFd[0] >= 0)
		::close(m_pipeFd[0]);
	if (m_vtunerFd >= 0)
		::close(m_vtunerFd);
	if (m_demuxFd >= 0)
		::close(m_demuxFd);
}

void *eDVBUsbAdapter::threadproc(void *arg)
{
	eDVBUsbAdapter *user = (eDVBUsbAdapter*)arg;
	return user->vtunerPump();
}

void *eDVBUsbAdapter::vtunerPump()
{
	int pidcount = 0;
	if (m_vtunerFd < 0 || m_demuxFd < 0 || m_pipeFd[0] < 0)
		return NULL;

	struct vtuner_message
	{
		int type;
		unsigned short int pidlist[hdsvtuner::PIDURI];
		unsigned char pad[64]; /* driverul poate copia mai mult decat stim: loc in plus */
	};

#define DEMUX_BUFFER_SIZE (16 * 1024 * 188) /* 3 MB */
	::ioctl(m_demuxFd, DMX_SET_BUFFER_SIZE, DEMUX_BUFFER_SIZE);

	std::vector<unsigned short> scoase, puse;
	while (m_running)
	{
		struct pollfd pfd[3];
		pfd[0].fd = m_pipeFd[0];
		pfd[0].events = POLLIN;
		pfd[1].fd = m_vtunerFd;
		pfd[1].events = POLLPRI;        /* cererile placii (MSG_PIDLIST) */
		pfd[2].fd = m_demuxFd;
		pfd[2].events = POLLIN;
		pfd[0].revents = pfd[1].revents = pfd[2].revents = 0;
		int gata = ::poll(pfd, 3, -1);
		if (gata < 0)
		{
			if (errno == EINTR)
				continue;
			eWarning("[eDVBUsbAdapter] %s: poll (%m), pompa se opreste", m_usbFrontendName.c_str());
			break;
		}
		if (pfd[0].revents)
			break; /* oprire ceruta (destructorul a inchis capatul de scriere) */
		if (pfd[1].revents & (POLLERR | POLLHUP | POLLNVAL))
		{
			eWarning("[eDVBUsbAdapter] %s: vtuner raspunde cu eroare (0x%x), pompa se opreste", m_usbFrontendName.c_str(),
				pfd[1].revents);
			break;
		}
		/* stickul scos sau desprins de driver: dvb-core (dmxdev) da numai POLLERR, fara POLLIN, iar citirea fara blocare
		   da EAGAIN; cu POLLERR si POLLIN e numai depasirea tamponului (citirea da EOVERFLOW, merge mai departe) */
		if ((pfd[2].revents & (POLLHUP | POLLNVAL)) || ((pfd[2].revents & POLLERR) && !(pfd[2].revents & POLLIN)))
		{
			eWarning("[eDVBUsbAdapter] %s: demuxul stickului nu mai raspunde (0x%x), pompa se opreste (tunerul USB revine la "
				"repornirea interfetei)", m_usbFrontendName.c_str(), pfd[2].revents);
			break;
		}
		if (pfd[1].revents & POLLPRI)
		{
			struct vtuner_message message;
			memset(&message, 0, sizeof(message));
			memset(message.pidlist, 0xff, sizeof(message.pidlist));
			::ioctl(m_vtunerFd, VTUNER_GET_MESSAGE, &message);

			if (message.type == MSG_PIDLIST)
			{
				hdsvtuner::schimbariPid(m_pidList, message.pidlist, scoase, puse);
				for (size_t i = 0; i < scoase.size(); ++i)
				{
					if (pidcount > 1)
					{
						::ioctl(m_demuxFd, DMX_REMOVE_PID, &scoase[i]);
						pidcount--;
					}
					else if (pidcount == 1)
					{
						::ioctl(m_demuxFd, DMX_STOP);
						pidcount = 0;
					}
				}
				for (size_t i = 0; i < puse.size(); ++i)
				{
					if (pidcount)
					{
						::ioctl(m_demuxFd, DMX_ADD_PID, &puse[i]);
						pidcount++;
					}
					else
					{
						struct dmx_pes_filter_params filter;
						memset(&filter, 0, sizeof(filter));
						filter.input = DMX_IN_FRONTEND;
						filter.flags = 0;
						filter.pid = puse[i];
						filter.output = DMX_OUT_TSDEMUX_TAP;
						filter.pes_type = DMX_PES_OTHER;
						if (::ioctl(m_demuxFd, DMX_SET_PES_FILTER, &filter) >= 0 && ::ioctl(m_demuxFd, DMX_START) >= 0)
							pidcount = 1;
					}
				}
				memcpy(m_pidList, message.pidlist, sizeof(m_pidList));
			}
		}
		if (pfd[2].revents & (POLLIN | POLLERR))
		{
			ssize_t size = hdsCitesteO(m_demuxFd, m_buffer, sizeof(m_buffer));
			if (size > 0)
			{
				if (hdsScrieTot(m_vtunerFd, m_buffer, size) <= 0)
				{
					eWarning("[eDVBUsbAdapter] %s: scrierea in vtuner (%m), pompa se opreste", m_usbFrontendName.c_str());
					break;
				}
			}
			else if (size == 0 || (errno != EAGAIN && errno != EOVERFLOW))
			{
				eWarning("[eDVBUsbAdapter] %s: citirea demuxului (%s), pompa se opreste (tunerul USB revine la repornirea "
					"interfetei)", m_usbFrontendName.c_str(), size == 0 ? "sfarsit" : strerror(errno));
				break;
			}
		}
	}
	/* demuxul stickului se inchide pe orice iesire: la scoaterea stickului nucleul (dvb_dmxdev_release) asteapta pana il
	   inchid toti, iar pana atunci deconectarea USB (si desprinderea facuta de librtlsdr pentru DAB+) ar ramane agatata.
	   vtuner ramane deschis, ca frontend-ul virtual si randul din nim_sockets sa nu dispara sub interfata. */
	if (m_demuxFd >= 0)
	{
		::close(m_demuxFd);
		m_demuxFd = -1;
	}
	m_running = false;
	return NULL;
}

void eDVBUsbAdapter::scrieLista()
{
	if (hdsvtuner::scrieLista(hdsvtuner::LISTA, s_legaturi) < 0)
		eWarning("[eDVBUsbAdapter] lista %s nu se scrie (%m)", hdsvtuner::LISTA);
}

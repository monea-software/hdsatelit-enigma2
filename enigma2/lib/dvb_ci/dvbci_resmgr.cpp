/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
/* DVB CI Resource Manager */

#include <lib/base/eerror.h>
#include <lib/dvb_ci/dvbci_resmgr.h>
#include <lib/base/hdsjurnal.h>
#include <lib/dvb_ci/dvbci.h>
#include <lib/dvb_ci/dvbci_ccmgr_helper.h>

int eDVBCIResourceManagerSession::receivedAPDU(const unsigned char *tag,const void *data, int len)
{
	eDebugNoNewLine("SESSION(%d) %02x %02x %02x: ", session_nb, tag[0], tag[1], tag[2]);
	for (int i=0; i<len; i++)
		eDebugNoNewLine("%02x ", ((const unsigned char*)data)[i]);
	eDebug("%s", "");
	if ((tag[0]==0x9f) && (tag[1]==0x80))
	{
		switch (tag[2])
		{
		case 0x10:  // profile enquiry
			eDebug("cam fragt was ich kann.");
			state=stateProfileEnquiry;
			return 1;
			break;
		case 0x11: // Tprofile
			eDebugNoNewLine("mein cam kann: ");
			if (!len)
				eDebug("nichts");
			else
				for (int i=0; i<len; i++)
					eDebugNoNewLine("%02x ", ((const unsigned char*)data)[i]);

			if (state == stateFirstProfileEnquiry)
			{
				// profile change
				return 1;
			}
			state=stateFinal;
			break;
		default:
			eDebug("unknown APDU tag 9F 80 %02x", tag[2]);
		}
	}
	
	return 0;
}

int eDVBCIResourceManagerSession::doAction()
{
	switch (state)
	{
	case stateStarted:
	{
		const unsigned char tag[3]={0x9F, 0x80, 0x10}; // profile enquiry
		sendAPDU(tag);
		state = stateFirstProfileEnquiry;
		return 0;
	}
	case stateFirstProfileEnquiry:
	{
		const unsigned char tag[3]={0x9F, 0x80, 0x12}; // profile change
		sendAPDU(tag);
		state=stateProfileChange;
		return 0;
	}
	case stateProfileChange:
	{
		eDebug("bla kaputt");
		break;
	}
	case stateProfileEnquiry:
	{
		const unsigned char tag[3]={0x9F, 0x80, 0x11};
		const unsigned char data[][4]=
			{
				{0x00, 0x01, 0x00, 0x41},
				{0x00, 0x02, 0x00, 0x41},
				{0x00, 0x03, 0x00, 0x41},
//				{0x00, 0x20, 0x00, 0x41}, // host control
				{0x00, 0x24, 0x00, 0x41},
				{0x00, 0x40, 0x00, 0x41},
//				{0x00, 0x10, 0x00, 0x41}, // auth.
			};
		/* CI+ (din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4,
		   lib/dvb_ci/dvbci_resmgr.cpp): resursele CI+ se anunta numai cand omul a pus certificatele aparatului in
		   /etc/ciplus (param, root.pem, customer.pem, device.pem). Fara ele modulul vede gazda veche si lucreaza ca
		   CI simplu, daca poate (exact ca pana acum). */
		const unsigned char data_v2[][4]=
			{
				{0x00, 0x01, 0x00, 0x41}, // res mgr 1
				{0x00, 0x02, 0x00, 0x41}, // app mgr 1
				{0x00, 0x02, 0x00, 0x42}, // app mgr 2
				{0x00, 0x02, 0x00, 0x43}, // app mgr 3
				{0x00, 0x02, 0x00, 0x45}, // app mgr 5
				{0x00, 0x03, 0x00, 0x41}, // ca mgr
				{0x00, 0x20, 0x00, 0x41}, // host ctrl 1
				{0x00, 0x20, 0x00, 0x42}, // host ctrl 2
				{0x00, 0x20, 0x00, 0x43}, // host ctrl 3
				{0x00, 0x24, 0x00, 0x41}, // datetime
				{0x00, 0x40, 0x00, 0x41}, // mmi
				{0x00, 0x41, 0x00, 0x41}, // app mmi 1
				{0x00, 0x41, 0x00, 0x42}, // app mmi 2
				{0x00, 0x8c, 0x10, 0x01}, // content ctrl 1
				{0x00, 0x8c, 0x10, 0x02}, // content ctrl 2
				{0x00, 0x8c, 0x10, 0x04}, // content ctrl 4
				{0x00, 0x8d, 0x10, 0x01}, // host language & country
				{0x00, 0x8e, 0x10, 0x01}, // cam upgrade
				{0x00, 0x8f, 0x10, 0x01}, // operator profile 1 (ultimele doua randuri: scoase cu „Dezactivează profilurile operatorului”)
				{0x00, 0x8f, 0x10, 0x02}, // operator profile 2
			};
		if (ciplus_cert_param_files_exists())
		{
			bool fara_operator = slot->getIsOperatorProfileDisabled();
			hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d CI+ anuntat modulului (certificatele din /etc/ciplus)%s",
				slot->getSlotID(), fara_operator ? ", fara profilurile operatorului" : "");
			sendAPDU(tag, data_v2, sizeof(data_v2) - (fara_operator ? 2 * sizeof(data_v2[0]) : 0));
		}
		else
		{
			hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d fara certificatele CI+ in /etc/ciplus: modulul lucreaza ca CI simplu", slot->getSlotID());
			sendAPDU(tag, data, sizeof(data));
		}
		state=stateFinal;
		return 0;
	}
	case stateFinal:
		eDebug("stateFinal und action! kann doch garnicht sein ;)");
	default:
		break;
	}
	return 0;
}

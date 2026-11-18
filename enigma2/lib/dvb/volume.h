#ifndef __volume_h
#define __volume_h

#include <lib/base/ebase.h>

class eDVBVolumecontrol
{
private:
	static eDVBVolumecontrol *instance;
	eDVBVolumecontrol();
#ifdef SWIG
	~eDVBVolumecontrol();
#endif
	int openMixer();
	void closeMixer(int fd);
	
	bool muted;
	bool pistaPlaciiTacuta;   /* egalizatorul la canalele TV (HiSilicon): vezi setPistaPlaciiTacuta */
	int leftVol, rightVol;
	
	int checkVolume(int vol);
	
public:
	static eDVBVolumecontrol* getInstance();

	void volumeUp(int left = 5, int right = 5);
	void volumeDown(int left = 5, int right = 5);

	void setVolume(int left, int right);

	void volumeMute();
	void volumeUnMute();	
	void volumeToggleMute();
	/* egalizatorul (lib/service/servicedvb.cpp, numai HiSilicon): cat sunetul unui canal TV trece prin procesor, pista
	   decodorului placii tace (AUDIO_SET_MUTE), iar decodorul ramane pe PID-ul adevarat. Tacerea omului ramane a lui:
	   volumeUnMute nu reda pista placii cat e tacuta aici, iar isMuted spune numai tacerea omului. */
	void setPistaPlaciiTacuta(bool tacuta);
			
	int getVolume();
	bool isMuted();
};

#endif //__volume_h

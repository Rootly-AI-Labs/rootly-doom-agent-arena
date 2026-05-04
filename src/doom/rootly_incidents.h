//
// Rootly incident visualization mode.
//

#ifndef __ROOTLY_INCIDENTS__
#define __ROOTLY_INCIDENTS__

#include "doomtype.h"
#include "info.h"
#include "p_mobj.h"

#define ROOTLY_MAX_INCIDENTS 24
#define ROOTLY_INCIDENT_LABEL_MAX 64

typedef struct
{
    char severity[8];
    mobjtype_t type;
    char label[ROOTLY_INCIDENT_LABEL_MAX];
    int x;
    int y;
    int angle;
} rootly_incident_t;

boolean Rootly_IncidentModeEnabled(void);
void Rootly_LoadIncidents(void);
void Rootly_SpawnIncidents(void);
int Rootly_IncidentCount(void);
const char *Rootly_IncidentSeverity(int incident_index);
void Rootly_BuildRemainingSummary(char *buffer, int buffer_size);

#endif
